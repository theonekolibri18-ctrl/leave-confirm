"""Einstiegspunkt: python -m chesslens.app  bzw. ChessLens.exe"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def setup_logging() -> None:
    from .settings import data_dir

    log_path = os.path.join(data_dir(), "chesslens.log")
    handlers: list[logging.Handler] = [RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")]
    if not getattr(sys, "frozen", False):
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)


def selftest() -> int:
    """Prüft den gebauten Stand ohne Fenster: Engine, Erkennung, Assets. Exit-Code 0 = ok.

    Schreibt das Ergebnis nach chesslens-selftest.txt (eine Fenster-.exe hat keine Konsole).
    """
    out_path = os.path.join(os.getcwd(), "chesslens-selftest.txt")
    lines: list[str] = []

    def say(*parts) -> None:
        msg = " ".join(str(p) for p in parts)
        lines.append(msg)
        try:
            if sys.stdout:
                print(msg)
        except Exception:  # noqa: BLE001
            pass

    try:
        code = _selftest_impl(say)
    except Exception as e:  # noqa: BLE001
        import traceback
        say("FEHLER:", e)
        say(traceback.format_exc())
        code = 1
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return code


def _selftest_impl(print) -> int:  # noqa: A002
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import cv2
    from PySide6.QtWidgets import QApplication

    from .board_detect import extract_cells, find_board
    from .controller import ProfileStore
    from .engine import EngineWorker, find_stockfish
    from .piece_recog import classify, grid_to_fen, screen_to_grid
    from .ui import theme

    app = QApplication.instance() or QApplication(sys.argv)
    fam = theme.load_fonts()
    print("Schrift:", fam)
    sample = os.path.join(theme._asset_dir(), "sample_board.png")
    img = cv2.imread(sample)
    assert img is not None, f"Beispielbild fehlt: {sample}"
    rect = find_board(img)
    assert rect is not None, "Brett im Beispielbild nicht gefunden"
    store = ProfileStore()
    prof = store.profiles.get("angelo-app")
    assert prof is not None, "Profil angelo-app fehlt"
    res, _ = classify(extract_cells(img, rect), prof)
    fen = grid_to_fen(screen_to_grid([[res[r][c].piece for c in range(8)] for r in range(8)], False))
    print("Erkannt:", fen)
    assert fen == "r1b1k2r/pp1n1ppp/3bpq2/1B1p4/N2P4/5Q2/PPP2PPP/R3K1NR", "Figuren falsch erkannt"
    path = find_stockfish()
    assert path, "Stockfish nicht gefunden"
    print("Stockfish:", path)
    import threading

    import chess
    done = threading.Event()
    got = []
    w = EngineWorker(path, threads=1, hash_mb=32)
    w.on_update = lambda r: (got.append(r), done.set() if r.done else None)
    w.start()
    w.analyse(chess.Board(), multipv=1, seconds=0.5)
    assert done.wait(15), "Engine antwortet nicht"
    w.stop()
    print("Engine ok, bester Zug:", got[-1].lines[0].move.uci())
    print("SELFTEST OK")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    setup_logging()
    log = logging.getLogger("chesslens")
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from . import APP_NAME
        from .settings import Settings
        from .ui import theme
        from .ui.main_window import MainWindow

        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            pass
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        theme.load_fonts()
        app.setStyleSheet(theme.stylesheet())
        icon_path = os.path.join(theme._asset_dir(), "icon.ico")
        if os.path.isfile(icon_path):
            app.setWindowIcon(QIcon(icon_path))
        settings = Settings.load()
        win = MainWindow(settings)
        win.show()
        return app.exec()
    except Exception as e:  # noqa: BLE001
        log.exception("Start fehlgeschlagen: %s", e)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "ChessLens", f"Start fehlgeschlagen:\n{e}\n\nDetails im Log: %APPDATA%\\ChessLens\\chesslens.log")
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
