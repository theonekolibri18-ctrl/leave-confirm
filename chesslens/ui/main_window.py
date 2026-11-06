"""Hauptfenster: verbindet Scanner, Engine, Spielstile und Anzeige."""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import chess
from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow, QStatusBar, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from .. import chess_util as cu
from ..controller import PositionUpdate, ProfileStore, Scanner
from ..engine import AnalysisResult, EngineWorker, SyncEngine, find_stockfish
from ..explain import eval_words, explain
from ..settings import Settings
from ..sound import play_ding
from ..styles import STYLES, Choice, rank_choices
from . import theme
from .board_widget import Arrow, BoardWidget
from .calibrate_dialog import CalibrateDialog
from .eval_bar import EvalBar
from .panels import MovePanel, TopBar
from .settings_dialog import SettingsDialog

log = logging.getLogger(__name__)


class EngineBridge(QObject):
    result = Signal(object)


class StyleBridge(QObject):
    ranked = Signal(str, object)  # (fen, list[Choice])


class HotkeyBridge(QObject):
    fired = Signal(str)


GLOBAL_HOTKEYS = {"pause": "ctrl+alt+p", "redetect": "ctrl+alt+b", "turn": "ctrl+alt+z", "flip": "ctrl+alt+d"}


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1180, 760)
        self.store = ProfileStore()

        # --- Layout -----------------------------------------------------------
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 14, 14, 10)
        outer.setSpacing(12)
        self.topbar = TopBar(settings.style)
        outer.addWidget(self.topbar)
        body = QHBoxLayout()
        body.setSpacing(14)
        self.eval_bar = EvalBar()
        self.board = BoardWidget()
        self.panel = MovePanel()
        body.addWidget(self.eval_bar)
        body.addWidget(self.board, 1)
        body.addWidget(self.panel)
        outer.addLayout(body, 1)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_engine = QLabel("Engine startet …")
        self.lbl_engine.setObjectName("faint")
        self.lbl_detect = QLabel("")
        self.lbl_detect.setObjectName("faint")
        self.status_bar.addWidget(self.lbl_engine, 1)
        self.status_bar.addPermanentWidget(self.lbl_detect)
        self.panel.show_waiting("Suche das Schachbrett", "Öffne dein Schachspiel auf dem ersten Monitor. Sobald die Grundstellung "
                                "zu sehen ist, lerne ich die Figuren automatisch.")

        # --- Zustand ----------------------------------------------------------
        self.current_board: Optional[chess.Board] = None
        self.current_update: Optional[PositionUpdate] = None
        self.last_result: Optional[AnalysisResult] = None
        self.choices: list[Choice] = []
        self.paused = False
        self._sounded_fen = ""
        self._style_thread: Optional[threading.Thread] = None

        # --- Scanner ------------------------------------------------------------
        self.scanner = Scanner(settings, self.store)
        self.scanner.position_changed.connect(self.on_position)
        self.scanner.status.connect(self.on_status)
        self.scanner.board_state.connect(self.on_board_state)
        self.scanner.calibrated.connect(self.on_calibrated)
        self.scanner.frame_ready.connect(self.on_frame)
        self.scanner.stats.connect(self.lbl_detect.setText)

        # --- Engine -----------------------------------------------------------------
        self.engine_bridge = EngineBridge()
        self.engine_bridge.result.connect(self.on_engine_result)
        self.style_bridge = StyleBridge()
        self.style_bridge.ranked.connect(self.on_style_ranked)
        self.engine: Optional[EngineWorker] = None
        self.sync: Optional[SyncEngine] = None
        path = find_stockfish()
        if path:
            threads = settings.engine_threads or max(1, (os.cpu_count() or 4) - 2)
            self.engine = EngineWorker(path, threads=threads, hash_mb=settings.engine_hash_mb)
            self.engine.on_update = self.engine_bridge.result.emit
            self.engine.start()
            try:
                self.sync = SyncEngine(path)
            except Exception as e:  # noqa: BLE001
                log.warning("Zweite Engine-Instanz nicht verfügbar: %s", e)
            self.lbl_engine.setText(f"Stockfish bereit · {threads} Kerne")
        else:
            self.lbl_engine.setText("Stockfish nicht gefunden – bitte stockfish-Ordner neben der .exe prüfen")
            self.panel.show_waiting("Stockfish fehlt", "Der Ordner „stockfish“ mit der Engine fehlt. Bitte das komplette ZIP entpacken "
                                    "und ChessLens aus dem entpackten Ordner starten.")

        # --- Signale der Leiste ---------------------------------------------------
        self.topbar.pause_clicked.connect(self.toggle_pause)
        self.topbar.redetect_clicked.connect(self.scanner.redetect)
        self.topbar.flip_turn_clicked.connect(self.scanner.flip_turn)
        self.topbar.flip_board_clicked.connect(self.scanner.flip_board)
        self.topbar.settings_clicked.connect(self.open_settings)
        self.topbar.style_changed.connect(self.on_style_changed)

        # --- Tastenkürzel -------------------------------------------------------------
        for keys, fn in (("F9", self.toggle_pause), ("F10", self.scanner.redetect), ("F11", self.scanner.flip_turn),
                         ("F12", self.scanner.flip_board), ("Ctrl+Alt+P", self.toggle_pause),
                         ("Ctrl+Alt+B", self.scanner.redetect), ("Ctrl+Alt+Z", self.scanner.flip_turn),
                         ("Ctrl+Alt+D", self.scanner.flip_board)):
            QShortcut(QKeySequence(keys), self, fn)
        self.hotkey_bridge = HotkeyBridge()
        self.hotkey_bridge.fired.connect(self._on_hotkey)
        self._global_hotkeys()

        self._place_on_display_monitor()
        self.scanner.start()
        self._excl_timer = QTimer(self)
        self._excl_timer.timeout.connect(self._update_exclusion)
        self._excl_timer.start(1000)
        self._update_exclusion()

    # ----------------------------------------------------------------------
    # Fenster / Monitore
    # ----------------------------------------------------------------------
    def _place_on_display_monitor(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return
        target = None
        if 0 <= self.settings.display_monitor < len(screens):
            target = screens[self.settings.display_monitor]
        else:
            # Automatisch: ein anderer Bildschirm als der Capture-Monitor
            mons = {m.index: m for m in self.scanner.capture.monitors()}
            cap = mons.get(self.settings.capture_monitor)
            for s in screens:
                g = s.geometry()
                if cap is None or (g.x(), g.y()) != (cap.left, cap.top):
                    target = s
                    break
            if target is None:
                target = screens[-1]
        g = target.availableGeometry()
        if self.settings.window_geometry and len(self.settings.window_geometry) == 4:
            x, y, w, h = self.settings.window_geometry
            if g.contains(QRect(x, y, w, h).center()):
                self.setGeometry(x, y, w, h)
                return
        w = min(1180, int(g.width() * 0.9))
        h = min(760, int(g.height() * 0.9))
        self.setGeometry(g.x() + (g.width() - w) // 2, g.y() + (g.height() - h) // 2, w, h)

    def _update_exclusion(self) -> None:
        """Eigenes Fenster nur dann aus der Aufnahme ausblenden, wenn es auf dem Capture-Monitor liegt."""
        scr = self.screen()
        if scr is None:
            self.scanner.set_exclusion(None)
            return
        dpr = scr.devicePixelRatio()
        sg = scr.geometry()
        mons = {m.index: m for m in self.scanner.capture.monitors()}
        mon = mons.get(self.settings.capture_monitor)
        if mon is None:
            self.scanner.set_exclusion(None)
            return
        same = abs(sg.x() * dpr - mon.left) < 4 and abs(sg.y() * dpr - mon.top) < 4
        if not same:
            self.scanner.set_exclusion(None)
            return
        fg = self.frameGeometry()
        # Fensterposition relativ zum Bildschirm, in physischen Pixeln (mss)
        x = mon.left + int((fg.x() - sg.x()) * dpr)
        y = mon.top + int((fg.y() - sg.y()) * dpr)
        self.scanner.set_exclusion((x, y, int(fg.width() * dpr), int(fg.height() * dpr)))

    def _global_hotkeys(self) -> None:
        if not self.settings.hotkeys:
            return
        try:
            import keyboard  # type: ignore

            for name, combo in GLOBAL_HOTKEYS.items():
                keyboard.add_hotkey(combo, lambda n=name: self.hotkey_bridge.fired.emit(n))
        except Exception as e:  # noqa: BLE001
            log.info("Globale Tastenkürzel nicht verfügbar: %s", e)

    def _on_hotkey(self, name: str) -> None:
        {"pause": self.toggle_pause, "redetect": self.scanner.redetect,
         "turn": self.scanner.flip_turn, "flip": self.scanner.flip_board}[name]()

    def closeEvent(self, event) -> None:  # noqa: N802
        g = self.geometry()
        self.settings.window_geometry = [g.x(), g.y(), g.width(), g.height()]
        self.settings.save()
        self.scanner.stop()
        if self.engine:
            self.engine.stop()
        if self.sync:
            self.sync.quit()
        super().closeEvent(event)

    # ----------------------------------------------------------------------
    # Scanner-Ereignisse
    # ----------------------------------------------------------------------
    def on_status(self, text: str, kind: str) -> None:
        self.topbar.status.set_status(text, kind)
        if kind in ("search", "warn") and self.current_board is None:
            self.panel.show_waiting(text if kind == "warn" else "Suche das Schachbrett",
                                    "" if kind == "warn" else "Öffne dein Schachspiel auf dem ersten Monitor.")
            self.board.set_dimmed(True)

    def on_board_state(self, rect) -> None:
        if rect is None:
            self.board.set_dimmed(True)

    def on_calibrated(self, name: str) -> None:
        self.status_bar.showMessage(f"Figuren gelernt – Profil „{name}“ gespeichert", 4000)

    def on_frame(self, frame) -> None:
        dlg = CalibrateDialog(frame, self)
        if dlg.exec():
            if dlg.use_auto:
                self.scanner.set_manual_rect(None)
            elif dlg.result_rect:
                self.scanner.set_manual_rect(dlg.result_rect)
            self.settings.save()

    def on_position(self, upd: PositionUpdate) -> None:
        board = chess.Board(upd.fen)
        self.current_board = board
        self.current_update = upd
        last = chess.Move.from_uci(upd.last_move) if upd.last_move else None
        self.board.set_position(board, upd.bottom_is_white, last)
        self.board.set_arrows([])
        self.board.set_dimmed(False)
        self.choices = []
        self.last_result = None
        if board.is_game_over():
            res = board.result()
            txt = "Schachmatt" if board.is_checkmate() else "Remis"
            who = ""
            if board.is_checkmate():
                who = "Du hast gewonnen!" if board.turn != (chess.WHITE if upd.bottom_is_white else chess.BLACK) else "Der Gegner hat gewonnen."
            self.panel.show_waiting(txt, f"{who} ({res})")
            return
        kicker = "Analysiere …"
        self.panel.show_analysis(kicker, "…", "Stockfish rechnet", "", "", [], [],
                                 hint="Zugrecht geschätzt – mit „Zugrecht“ (F11) tauschen, falls falsch." if not upd.synced and upd.resynced else "")
        if self.engine and not self.paused:
            multipv = 3 if self.settings.style == "engine" else 5
            self.engine.analyse(board, multipv=multipv, seconds=self.settings.engine_seconds)

    # ----------------------------------------------------------------------
    # Engine-Ereignisse
    # ----------------------------------------------------------------------
    def on_engine_result(self, result: AnalysisResult) -> None:
        if self.current_board is None or result.board_fen != self.current_board.fen():
            return
        self.last_result = result
        self.lbl_engine.setText(f"Tiefe {result.depth} · {result.nodes / 1e6:.1f} Mio. Knoten · {result.nps / 1e6:.1f} Mio./s"
                                + ("" if result.done else " · rechnet …"))
        if not result.lines:
            return
        style = self.settings.style
        if style == "trickreich" and self.sync is not None:
            # Fallen-Suche braucht Rechenzeit -> im Hintergrund, sobald die Analyse fertig ist
            engine_order = rank_choices(self.current_board, result.lines, "engine")
            self._render(engine_order, final=False, style_pending=True)
            if result.done:
                self._rank_async(result)
            return
        choices = rank_choices(self.current_board, result.lines, style, self.settings.risk_cp, self.sync)
        self._render(choices, final=result.done)

    def _rank_async(self, result: AnalysisResult) -> None:
        board = self.current_board.copy()
        fen = board.fen()
        lines = list(result.lines)
        style = self.settings.style
        risk = self.settings.risk_cp
        sync = self.sync

        def work() -> None:
            try:
                ch = rank_choices(board, lines, style, risk, sync)
            except Exception as e:  # noqa: BLE001
                log.exception("Spielstil-Berechnung: %s", e)
                ch = rank_choices(board, lines, "engine")
            self.style_bridge.ranked.emit(fen, ch)

        self._style_thread = threading.Thread(target=work, daemon=True)
        self._style_thread.start()

    def on_style_ranked(self, fen: str, choices: list[Choice]) -> None:
        if self.current_board is None or fen != self.current_board.fen():
            return
        self._render(choices, final=True)

    def on_style_changed(self, key: str) -> None:
        self.settings.style = key
        self.settings.save()
        if self.current_board is not None and self.engine and not self.current_board.is_game_over():
            multipv = 3 if key == "engine" else 5
            self.engine.analyse(self.current_board, multipv=multipv, seconds=self.settings.engine_seconds)

    # ----------------------------------------------------------------------
    # Darstellung
    # ----------------------------------------------------------------------
    def _render(self, choices: list[Choice], final: bool, style_pending: bool = False) -> None:
        if not choices or self.current_board is None or self.current_update is None:
            return
        board = self.current_board
        upd = self.current_update
        self.choices = choices
        best = choices[0]
        user_turn = upd.user_to_move
        accent = theme.ACCENT if user_turn else theme.OPPONENT

        # Pfeile: Empfehlung dick, Alternativen (nach Engine-Reihenfolge) dünn
        arrows = [Arrow(best.line.move, QColor(accent), 0.22, 235)]
        if self.settings.show_alternatives:
            by_score = sorted(choices, key=lambda c: -c.line.score_cp)
            alt_cols = [theme.ALT2, theme.ALT3]
            k = 0
            for c in by_score:
                if c.line.move == best.line.move:
                    continue
                if k >= 2:
                    break
                arrows.append(Arrow(c.line.move, QColor(alt_cols[k]), 0.12, 150))
                k += 1
        self.board.set_arrows(arrows)

        # Bewertung aus Sicht von Weiß für den Balken
        cp_user = best.line.score_cp
        sign = 1 if board.turn == chess.WHITE else -1
        cp_white = sign * cp_user
        mate_white = None if best.line.mate is None else sign * best.line.mate
        self.eval_bar.set_eval(cp_white, mate_white, upd.bottom_is_white)

        # Text aus Sicht des Nutzers
        user_color = chess.WHITE if upd.bottom_is_white else chess.BLACK
        pov_sign = 1 if board.turn == user_color else -1
        cp_pov = pov_sign * cp_user
        mate_pov = None if best.line.mate is None else pov_sign * best.line.mate
        eval_text = f"{best.line.score_str() if user_turn else _flip_score(best.line)} · {eval_words(cp_pov, mate_pov)}"

        san = cu.san_de(board, best.line.move)
        words = cu.move_words(board, best.line.move)
        if user_turn:
            kicker = "Dein bester Zug" if self.settings.style == "engine" else f"Dein Zug ({STYLES[self.settings.style]})"
            bullets = explain(board, best)
        else:
            kicker = "Gegner am Zug – wahrscheinlich kommt"
            bullets = explain(board, best)
        style_tag = ""
        if self.settings.style != "engine" and user_turn:
            if style_pending:
                style_tag = "Fallen werden gesucht …"
            elif best.tags:
                style_tag = ", ".join(dict.fromkeys(best.tags))
            elif best.line.move != max(choices, key=lambda c: c.line.score_cp).line.move:
                style_tag = STYLES[self.settings.style]
        alts = []
        by_score = sorted(choices, key=lambda c: -c.line.score_cp)
        for c in by_score[:3]:
            b2 = board.copy()
            pv_parts = []
            for m in c.line.pv[:5]:
                if m not in b2.legal_moves:
                    break
                pv_parts.append(cu.san_de(b2, m))
                b2.push(m)
            alts.append((cu.san_de(board, c.line.move), c.line.score_str(), " ".join(pv_parts),
                         c.line.score_cp >= by_score[0].line.score_cp - 50))
        hint = ""
        if not upd.synced and upd.resynced:
            hint = "Zugrecht geschätzt – mit „Zugrecht tauschen“ (F11) korrigieren, falls falsch."
        elif not final:
            hint = "Analyse läuft …"
        self.panel.show_analysis(kicker, san, words, eval_text, style_tag, bullets, alts, hint, accent)

        if final and user_turn and self.settings.sound and self._sounded_fen != board.fen():
            self._sounded_fen = board.fen()
            play_ding()

    # ----------------------------------------------------------------------
    # Aktionen
    # ----------------------------------------------------------------------
    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.scanner.paused = self.paused
        self.topbar.set_paused(self.paused)
        if self.paused:
            self.topbar.status.set_status("Pausiert (F9 zum Fortsetzen)", "pause")
        elif self.current_board is not None and self.engine:
            self.engine.analyse(self.current_board, multipv=3 if self.settings.style == "engine" else 5,
                                seconds=self.settings.engine_seconds)

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self.scanner.capture.monitors(), sorted(self.store.profiles),
                             self.settings.active_profile, self)
        dlg.calibrate_requested.connect(lambda: (dlg.accept(), self.scanner.request_frame()))
        dlg.dump_requested.connect(lambda: (dlg.accept(), self.scanner.request_dump()))
        dlg.profile_deleted.connect(self._delete_profile)
        dlg.profile_selected.connect(self._select_profile)
        if dlg.exec():
            old_cap = self.settings.capture_monitor
            dlg.apply()
            self.settings.save()
            if self.engine:
                threads = self.settings.engine_threads or max(1, (os.cpu_count() or 4) - 2)
                self.engine.set_options(threads, self.settings.engine_hash_mb)
            if old_cap != self.settings.capture_monitor:
                self.scanner.redetect()
            if self.current_board is not None and self.engine:
                self.engine.analyse(self.current_board, multipv=3 if self.settings.style == "engine" else 5,
                                    seconds=self.settings.engine_seconds)
            self._place_on_display_monitor()

    def _delete_profile(self, name: str) -> None:
        self.store.delete(name)
        if self.scanner.active is not None and self.scanner.active.name == name:
            self.scanner.active = None

    def _select_profile(self, name: str) -> None:
        self.scanner.set_active_profile(name)
        self.settings.save()


def _flip_score(line) -> str:
    """Bewertung des Gegnerzugs aus Nutzersicht (Vorzeichen gedreht)."""
    if line.mate is not None:
        return f"-M{abs(line.mate)}" if line.mate > 0 else f"M{abs(line.mate)}"
    return f"{-line.score_cp / 100:+.2f}"
