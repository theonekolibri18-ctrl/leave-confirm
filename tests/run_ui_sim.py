"""Startet die komplette App offscreen mit simuliertem Monitor (Screenshots der Partie) und speichert Bilder.

    python tests/run_ui_sim.py            -> /tmp/ui_*.png
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from chesslens import capture  # noqa: E402
from tests.ground_truth import SHOTS, UPLOADS  # noqa: E402
from tests.test_board_detect import fake_desktop  # noqa: E402

FRAMES = []
for fname, fen, _ in SHOTS:
    img = cv2.imread(os.path.join(UPLOADS, fname))
    desk, _ = fake_desktop(img, scale=0.8)
    FRAMES.append(desk)

STATE = {"i": 0, "t0": time.time(), "period": float(os.environ.get("SIM_PERIOD", "4"))}


class FakeCapture:
    def monitors(self):
        return [capture.MonitorInfo(1, 0, 0, 1920, 1080), capture.MonitorInfo(2, 1920, 0, 1920, 1080)]

    def grab(self, index):
        i = min(len(FRAMES) - 1, int((time.time() - STATE["t0"]) / STATE["period"]))
        STATE["i"] = i
        return FRAMES[i].copy()


capture.ScreenCapture = FakeCapture  # noqa: E305

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from chesslens.settings import Settings  # noqa: E402
from chesslens.ui import theme  # noqa: E402
from chesslens.ui.main_window import MainWindow  # noqa: E402


def main():
    app = QApplication(sys.argv)
    theme.load_fonts()
    app.setStyleSheet(theme.stylesheet())
    s = Settings()
    s.engine_seconds = 1.5
    s.style = os.environ.get("SIM_STYLE", "engine")
    s.sound = False
    s.hotkeys = False
    MainWindow._update_exclusion = lambda self: None  # offscreen liegt das Fenster bei (0,0) -> nicht maskieren
    win = MainWindow(s)
    win.resize(1280, 800)
    win.show()
    shots = [(3.0, "/tmp/ui_1.png"), (9.5, "/tmp/ui_2.png"), (26.0, "/tmp/ui_3.png"), (45.0, "/tmp/ui_4.png")]

    def tick():
        el = time.time() - STATE["t0"]
        if shots and el >= shots[0][0]:
            _, path = shots.pop(0)
            win.grab().save(path)
            print("gespeichert", path, "frame", STATE["i"], "fen", win.current_board.fen() if win.current_board else None)
        if not shots:
            win.close()
            app.quit()

    t = QTimer()
    t.timeout.connect(tick)
    t.start(200)
    app.exec()


if __name__ == "__main__":
    main()
