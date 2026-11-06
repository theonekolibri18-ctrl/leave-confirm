"""Scanner-Thread: Bildschirm → Brett → Figuren → Partie. Meldet Änderungen per Qt-Signal."""

from __future__ import annotations

import glob
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal

from .board_detect import BoardRect, extract_cells, find_board, verify_board
from .capture import ScreenCapture
from .game_tracker import GameTracker
from .piece_recog import (START_FEN, Profile, analyze_cells, classify, grid_to_fen, guess_bottom_is_white,
                          learn_profile, merge_profiles, position_plausible, screen_to_grid, start_pattern_matches)
from .settings import Settings, profiles_dir

log = logging.getLogger(__name__)


def bundled_profiles_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "chesslens", "assets", "profiles")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "profiles")


class ProfileStore:
    def __init__(self) -> None:
        self.profiles: dict[str, Profile] = {}
        self.reload()

    def reload(self) -> None:
        self.profiles.clear()
        for d in (bundled_profiles_dir(), profiles_dir()):
            for p in glob.glob(os.path.join(d, "*.npz")):
                try:
                    prof = Profile.load(p)
                    self.profiles[prof.name] = prof
                except Exception as e:  # noqa: BLE001
                    log.warning("Profil %s unlesbar: %s", p, e)
        log.info("Profile geladen: %s", list(self.profiles))

    def save(self, prof: Profile) -> None:
        self.profiles[prof.name] = prof
        prof.save(os.path.join(profiles_dir(), f"{prof.name}.npz"))

    def delete(self, name: str) -> None:
        self.profiles.pop(name, None)
        p = os.path.join(profiles_dir(), f"{name}.npz")
        if os.path.exists(p):
            os.remove(p)

    def closest(self, light, dark, max_dist: float = 10_000) -> Optional[Profile]:
        best, bd = None, max_dist
        for prof in self.profiles.values():
            d = prof.color_distance(light, dark)
            if d < bd:
                best, bd = prof, d
        return best

    def by_colors(self, light, dark, tol: float = 24) -> Optional[Profile]:
        return self.closest(light, dark, tol)


@dataclass
class PositionUpdate:
    fen: str
    bottom_is_white: bool
    last_move: str  # uci oder ''
    synced: bool
    new_game: bool
    resynced: bool
    user_to_move: bool


class Scanner(QThread):
    position_changed = Signal(object)  # PositionUpdate
    status = Signal(str, str)  # (text, kind: 'ok'|'warn'|'search'|'pause')
    board_state = Signal(object)  # BoardRect oder None
    calibrated = Signal(str)  # Profilname
    frame_ready = Signal(object)  # np.ndarray (nur auf Anfrage, für Kalibrier-Dialog)
    stats = Signal(str)

    def __init__(self, settings: Settings, store: ProfileStore) -> None:
        super().__init__()
        self.settings = settings
        self.store = store
        self.capture = ScreenCapture()
        self.tracker = GameTracker()
        self.tracker.set_orientation(settings.bottom_is_white)
        self.rect: Optional[BoardRect] = None
        self.active: Optional[Profile] = None
        if settings.active_profile in store.profiles:
            self.active = store.profiles[settings.active_profile]
        self.paused = False
        self._stop = False
        self._misses = 0
        self._learned_start = False
        self._want_frame = False
        self._exclude: Optional[tuple[int, int, int, int]] = None  # globales Rechteck des eigenen Fensters
        self._force_redetect = False
        self._last_status = ("", "")
        self._bad_frames = 0
        self._last_scan_ms = 0.0
        self._last_fp: Optional[np.ndarray] = None

    # ---- Steuerung von außen ----------------------------------------------
    def request_frame(self) -> None:
        self._want_frame = True

    def set_exclusion(self, rect_global: Optional[tuple[int, int, int, int]]) -> None:
        self._exclude = rect_global

    def redetect(self) -> None:
        self._force_redetect = True

    def set_manual_rect(self, rect: Optional[list[float]]) -> None:
        self.settings.manual_rect = list(rect) if rect else []
        self.rect = None
        self._force_redetect = True

    def flip_turn(self) -> None:
        self.tracker.flip_turn()
        self._emit_position(new_game=False, resynced=True)

    def flip_board(self) -> None:
        self.tracker.auto_orient = False  # Nutzer hat entschieden
        self.tracker.set_orientation(not self.tracker.bottom_is_white)
        self.settings.bottom_is_white = self.tracker.bottom_is_white
        # Stellung aus Sicht der neuen Orientierung neu lesen
        self.tracker.board.clear_stack()
        self.tracker.synced = False
        self._pending_reset()

    def set_active_profile(self, name: str) -> None:
        self.active = self.store.profiles.get(name)
        self.settings.active_profile = name if self.active else ""

    def set_position_fen(self, fen: str) -> None:
        self.tracker.set_position_fen(fen)
        self._emit_position(new_game=False, resynced=True)

    def stop(self) -> None:
        self._stop = True
        self.wait(3000)

    def _pending_reset(self) -> None:
        self.tracker._pending_grid = None
        self.tracker._pending_count = 0

    # ---- Hilfen -------------------------------------------------------------
    def _set_status(self, text: str, kind: str) -> None:
        if (text, kind) != self._last_status:
            self._last_status = (text, kind)
            self.status.emit(text, kind)

    def _emit_position(self, new_game: bool, resynced: bool, last_move: str = "") -> None:
        b = self.tracker.board
        self.position_changed.emit(PositionUpdate(
            fen=b.fen(), bottom_is_white=self.tracker.bottom_is_white,
            last_move=last_move or (self.tracker.last_move.uci() if self.tracker.last_move else ""),
            synced=self.tracker.synced, new_game=new_game, resynced=resynced,
            user_to_move=(b.turn == self.tracker.user_color)))

    def _mask_own_window(self, img: np.ndarray, mon) -> None:
        if self._exclude is None or mon is None:
            return
        x, y, w, h = self._exclude
        x0, y0 = x - mon.left, y - mon.top
        x1, y1 = x0 + w, y0 + h
        H, W = img.shape[:2]
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1 > x0 and y1 > y0:
            img[y0:y1, x0:x1] = 0

    # ---- Hauptschleife ----------------------------------------------------
    def run(self) -> None:  # noqa: C901
        log.info("Scanner gestartet")
        while not self._stop:
            t0 = time.time()
            try:
                self._tick()
            except Exception as e:  # noqa: BLE001
                log.exception("Scanner-Fehler: %s", e)
                self._set_status(f"Fehler: {e}", "warn")
            self._last_scan_ms = (time.time() - t0) * 1000
            delay = max(0.05, self.settings.scan_interval - (time.time() - t0))
            for _ in range(int(delay / 0.05) + 1):
                if self._stop:
                    break
                time.sleep(0.05)

    def _tick(self) -> None:  # noqa: C901
        if self.paused:
            self._set_status("Pausiert (F9 zum Fortsetzen)", "pause")
            return
        mons = {m.index: m for m in self.capture.monitors()}
        mon = mons.get(self.settings.capture_monitor)
        img = self.capture.grab(self.settings.capture_monitor)
        if img is None:
            self._set_status("Monitor konnte nicht aufgenommen werden", "warn")
            return
        if self._want_frame:
            self._want_frame = False
            self.frame_ready.emit(img.copy())
        self._mask_own_window(img, mon)

        # --- Brett finden ---------------------------------------------------
        if self.settings.manual_rect:
            x, y, s = self.settings.manual_rect
            rect = BoardRect(x, y, s)
            v = verify_board(img, rect, min_score=0.5)
            rect = v or rect
        else:
            rect = None
            if self.rect is not None and not self._force_redetect:
                rect = verify_board(img, self.rect)
                if rect is None:
                    self._misses += 1
                    if self._misses <= 2:
                        return  # kurze Störung (Animation, Tooltip) abwarten
            if rect is None:
                self._force_redetect = False
                rect = find_board(img)
                if rect is None:
                    self.rect = None
                    self.board_state.emit(None)
                    self._set_status(f"Suche Schachbrett auf Monitor {self.settings.capture_monitor} …", "search")
                    return
                self._misses = 0
                self.board_state.emit(rect)
        self.rect = rect
        self._misses = 0

        # --- Zellen / Grundstellung -----------------------------------------
        cells = extract_cells(img, rect)
        # Unverändertes Brettbild? Dann Erkennung sparen (nur den Entprell-Zähler weiterzählen)
        fp = cells.reshape(64, -1, 3).mean(axis=1).astype(np.float32)
        if self._last_fp is not None and np.abs(fp - self._last_fp).max() < 2.0 and self.tracker._pending_count >= self.tracker.stable_frames:
            return
        self._last_fp = fp
        masks, occ, lum = analyze_cells(cells)
        if start_pattern_matches(occ):
            if not self._learned_start:
                bottom_white = guess_bottom_is_white(cells, occ, lum)
                if bottom_white is not None:
                    name = f"auto-{rect.light[2]:02x}{rect.light[1]:02x}{rect.light[0]:02x}-{rect.dark[2]:02x}{rect.dark[1]:02x}{rect.dark[0]:02x}"
                    existing = self.store.by_colors(rect.light, rect.dark)
                    if existing is not None and not existing.name.startswith("auto-"):
                        name = existing.name
                    prof = learn_profile(cells, START_FEN, bottom_white, name, rect.light, rect.dark)
                    if prof is not None:
                        if existing is not None and existing.name == name:
                            prof = merge_profiles(existing, prof)
                        self.store.save(prof)
                        self.active = prof
                        self.settings.active_profile = prof.name
                        self.tracker.set_orientation(bottom_white)
                        self.tracker.auto_orient = True
                        self.settings.bottom_is_white = bottom_white
                        self._learned_start = True
                        self.calibrated.emit(prof.name)
                        log.info("Profil gelernt: %s (Weiß unten: %s)", prof.name, bottom_white)
        else:
            self._learned_start = False

        # --- Profil wählen ----------------------------------------------------
        if self.active is None or self.active.color_distance(rect.light, rect.dark) > 40:
            cand = self.store.by_colors(rect.light, rect.dark) or self.store.closest(rect.light, rect.dark)
            if cand is not None and cand is not self.active:
                self.active = cand
                self.settings.active_profile = cand.name
                log.info("Profil gewählt: %s", cand.name)
        if self.active is None:
            self._set_status("Bitte eine neue Partie starten (Grundstellung), damit ich die Figuren lernen kann", "search")
            return

        # --- Figuren erkennen -------------------------------------------------
        res, _ = classify(cells, self.active)
        screen = [[res[r][c].piece for c in range(8)] for r in range(8)]
        grid = screen_to_grid(screen, self.tracker.bottom_is_white)
        if not position_plausible(grid):
            self._bad_frames += 1
            if self._bad_frames > 6:
                self._set_status("Stellung unklar – ggf. neue Partie starten oder Profil wechseln", "warn")
            return
        self._bad_frames = 0
        upd = self.tracker.update_from_screen(screen)
        if self.tracker.bottom_is_white != self.settings.bottom_is_white:
            self.settings.bottom_is_white = self.tracker.bottom_is_white
        self.stats.emit(f"Brett {int(rect.size)} px · Profil {self.active.name} · Scan {self._last_scan_ms:.0f} ms")
        if upd.changed:
            self._emit_position(upd.new_game, upd.resynced, upd.moves[-1].uci() if upd.moves else "")
        b = self.tracker.board
        if b.is_checkmate():
            self._set_status("Schachmatt", "ok")
        elif b.turn == self.tracker.user_color:
            self._set_status("Du bist am Zug", "ok")
        else:
            self._set_status("Gegner am Zug", "wait")
