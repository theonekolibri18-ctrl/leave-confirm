"""Stockfish-Anbindung: läuft in einem eigenen Thread, liefert Zwischenergebnisse.

Die Analyse wird abgebrochen, sobald eine neue Stellung ankommt.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import chess
import chess.engine

log = logging.getLogger(__name__)

MATE_CP = 100_000


@dataclass
class Line:
    move: chess.Move
    score_cp: int  # aus Sicht des Spielers am Zug; Matt -> ±(MATE_CP - n)
    mate: Optional[int]  # Matt in n (positiv = wir setzen matt), sonst None
    pv: list[chess.Move]
    depth: int

    def score_str(self) -> str:
        if self.mate is not None:
            return f"M{abs(self.mate)}" if self.mate > 0 else f"-M{abs(self.mate)}"
        return f"{self.score_cp / 100:+.2f}"


@dataclass
class AnalysisResult:
    board_fen: str
    lines: list[Line] = field(default_factory=list)
    depth: int = 0
    nodes: int = 0
    nps: int = 0
    done: bool = False


def _bundle_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def find_stockfish() -> Optional[str]:
    """Sucht die passende Stockfish-Binary (gebündelt, neben der .exe oder im PATH)."""
    bases = [_bundle_dir()]
    if getattr(sys, "frozen", False):
        bases.append(os.path.dirname(sys.executable))
    cands = []
    if platform.system() == "Windows":
        for base in bases:
            cands += [
                os.path.join(base, "stockfish", "stockfish-windows-x86-64-avx2.exe"),
                os.path.join(base, "stockfish", "stockfish-windows-x86-64-sse41-popcnt.exe"),
                os.path.join(base, "stockfish", "stockfish-windows-x86-64.exe"),
                os.path.join(base, "stockfish", "stockfish.exe"),
            ]
    else:
        base = bases[0]
        cands += [
            os.path.join(base, "stockfish", "stockfish-ubuntu-x86-64-avx2"),
            os.path.join(base, "stockfish", "stockfish"),
            "/tmp/stockfish/stockfish-ubuntu-x86-64-avx2",
            "/usr/games/stockfish",
            "/usr/bin/stockfish",
        ]
    env = os.environ.get("CHESSLENS_STOCKFISH")
    if env:
        cands.insert(0, env)
    for c in cands:
        if os.path.isfile(c) and _engine_starts(c):
            return c
    return None


def _engine_starts(path: str) -> bool:
    """Prüft, ob die Binary auf dieser CPU läuft (AVX2-Build stürzt sonst sofort ab)."""
    try:
        flags = 0
        if platform.system() == "Windows":
            flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        p = subprocess.run([path], input=b"uci\nquit\n", capture_output=True, timeout=8, creationflags=flags)
        return p.returncode == 0 and b"uciok" in p.stdout
    except Exception:  # noqa: BLE001
        return False


class EngineWorker:
    """Analysiert immer nur die zuletzt übergebene Stellung."""

    def __init__(self, path: str, threads: int = 2, hash_mb: int = 256) -> None:
        self.path = path
        self.threads = threads
        self.hash_mb = hash_mb
        self._engine: Optional[chess.engine.SimpleEngine] = None
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._request: Optional[tuple[chess.Board, int, float, int]] = None
        self._analysis = None
        self._stop = False
        self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
        self.on_update: Optional[Callable[[AnalysisResult], None]] = None
        self._gen = 0

    def start(self) -> None:
        self._thread.start()

    def _open(self) -> None:
        popen_args = {}
        if platform.system() == "Windows":
            popen_args["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self._engine = chess.engine.SimpleEngine.popen_uci(self.path, **popen_args)
        opts = {"Threads": self.threads, "Hash": self.hash_mb}
        try:
            self._engine.configure(opts)
        except chess.engine.EngineError as e:
            log.warning("Engine-Optionen: %s", e)

    def set_options(self, threads: int, hash_mb: int) -> None:
        self.threads, self.hash_mb = threads, hash_mb
        with self._cv:
            self._gen += 1
            if self._analysis is not None:
                try:
                    self._analysis.stop()
                except Exception:  # noqa: BLE001
                    pass
        # Optionen werden vor der nächsten Analyse gesetzt

    def analyse(self, board: chess.Board, multipv: int = 3, seconds: float = 2.5, max_depth: int = 40) -> None:
        with self._cv:
            self._request = (board.copy(), multipv, seconds, max_depth)
            self._gen += 1
            if self._analysis is not None:
                try:
                    self._analysis.stop()
                except Exception:  # noqa: BLE001
                    pass
            self._cv.notify()

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            if self._analysis is not None:
                try:
                    self._analysis.stop()
                except Exception:  # noqa: BLE001
                    pass
            self._cv.notify()
        self._thread.join(timeout=3)
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            self._open()
        except Exception as e:  # noqa: BLE001
            log.exception("Stockfish konnte nicht gestartet werden: %s", e)
            return
        applied_opts = (self.threads, self.hash_mb)
        while True:
            with self._cv:
                while self._request is None and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                board, multipv, seconds, max_depth = self._request
                self._request = None
                gen = self._gen
            if (self.threads, self.hash_mb) != applied_opts:
                try:
                    self._engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
                    applied_opts = (self.threads, self.hash_mb)
                except Exception as e:  # noqa: BLE001
                    log.warning("Engine-Optionen: %s", e)
            try:
                self._analyse_one(board, multipv, seconds, max_depth, gen)
            except chess.engine.EngineTerminatedError:
                log.error("Engine beendet – Neustart")
                try:
                    self._open()
                except Exception:  # noqa: BLE001
                    time.sleep(1)
            except Exception as e:  # noqa: BLE001
                log.exception("Analysefehler: %s", e)

    def _analyse_one(self, board: chess.Board, multipv: int, seconds: float, max_depth: int, gen: int) -> None:
        result = AnalysisResult(board.fen())
        if board.is_game_over():
            result.done = True
            if self.on_update:
                self.on_update(result)
            return
        n_legal = board.legal_moves.count()
        multipv = max(1, min(multipv, n_legal))
        limit = chess.engine.Limit(time=seconds, depth=max_depth)
        last_emit = 0.0
        with self._engine.analysis(board, limit, multipv=multipv) as analysis:
            with self._cv:
                self._analysis = analysis
            lines: dict[int, Line] = {}
            for info in analysis:
                if gen != self._gen:
                    break
                if "pv" not in info or "score" not in info:
                    continue
                idx = info.get("multipv", 1)
                sc = info["score"].pov(board.turn)
                mate = sc.mate()
                cp = sc.score(mate_score=MATE_CP)
                lines[idx] = Line(info["pv"][0], int(cp), mate, list(info["pv"]), info.get("depth", 0))
                result.depth = info.get("depth", result.depth)
                result.nodes = info.get("nodes", result.nodes)
                result.nps = info.get("nps", result.nps)
                now = time.time()
                if self.on_update and now - last_emit > 0.15:
                    result.lines = [lines[k] for k in sorted(lines)]
                    self.on_update(result)
                    last_emit = now
            with self._cv:
                self._analysis = None
        if gen == self._gen:
            result.lines = [lines[k] for k in sorted(lines)]
            result.done = True
            if self.on_update:
                self.on_update(result)


class SyncEngine:
    """Zweite, kleine Engine-Instanz für kurze synchrone Bewertungen (Spielstile)."""

    def __init__(self, path: str, threads: int = 1) -> None:
        popen_args = {}
        if platform.system() == "Windows":
            popen_args["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self.engine = chess.engine.SimpleEngine.popen_uci(path, **popen_args)
        try:
            self.engine.configure({"Threads": threads, "Hash": 64})
        except chess.engine.EngineError:
            pass
        self.lock = threading.Lock()

    def best(self, board: chess.Board, depth: int = 8, multipv: int = 1) -> list[Line]:
        with self.lock:
            infos = self.engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
        out = []
        for info in infos:
            if "pv" not in info or "score" not in info:
                continue
            sc = info["score"].pov(board.turn)
            out.append(Line(info["pv"][0], int(sc.score(mate_score=MATE_CP)), sc.mate(), list(info["pv"]), info.get("depth", 0)))
        return out

    def evaluate(self, board: chess.Board, depth: int = 8) -> int:
        """Bewertung aus Sicht des Spielers am Zug (cp)."""
        if board.is_checkmate():
            return -MATE_CP
        if board.is_stalemate() or board.is_insufficient_material():
            return 0
        with self.lock:
            info = self.engine.analyse(board, chess.engine.Limit(depth=depth))
        return int(info["score"].pov(board.turn).score(mate_score=MATE_CP))

    def quit(self) -> None:
        try:
            self.engine.quit()
        except Exception:  # noqa: BLE001
            pass
