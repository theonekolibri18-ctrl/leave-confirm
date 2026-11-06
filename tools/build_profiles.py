"""Erzeugt die mitgelieferten Erkennungsprofile in chesslens/assets/profiles/.

  * angelo-app   – aus dem ersten Partie-Screenshot (Stellung nach 1.e4, Schwarz unten)
  * lichess-std  – aus einem mit python-chess gerenderten Brett (cburnett-Figuren,
                   Standardfarben wie lichess "brown")
"""

import os
import sys

import cv2
import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from chesslens.board_detect import extract_cells, find_board  # noqa: E402
from chesslens.piece_recog import START_FEN, learn_profile  # noqa: E402

OUT = os.path.join(ROOT, "chesslens", "assets", "profiles")


def build_from_image(img, fen, bottom_is_white, name):
    rect = find_board(img)
    assert rect is not None, f"{name}: Brett nicht gefunden"
    cells = extract_cells(img, rect)
    prof = learn_profile(cells, fen, bottom_is_white, name, rect.light, rect.dark)
    assert prof is not None, f"{name}: Profil unvollständig"
    prof.save(os.path.join(OUT, f"{name}.npz"))
    print(f"{name}: gespeichert (white_lum={prof.white_lum:.0f}, black_lum={prof.black_lum:.0f}, light={prof.light}, dark={prof.dark})")


def render_svg_board(size=640):
    """Grundstellung mit python-chess als SVG rendern und mit Qt rastern."""
    import chess
    import chess.svg
    from PySide6.QtCore import QByteArray
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    svg = chess.svg.board(chess.Board(), size=size, coordinates=True)
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    r.render(p)
    p.end()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, np.uint8).reshape(size, size, 4)[:, :, :3].copy()
    return arr


def main():
    os.makedirs(OUT, exist_ok=True)
    shot = "/mnt/user-data/uploads/f6852466-image.png"
    if os.path.exists(shot):
        img = cv2.imread(shot)
        build_from_image(img, "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR", False, "angelo-app")
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        board = render_svg_board()
        cv2.imwrite("/tmp/lichess_render.png", board)
        build_from_image(board, START_FEN, True, "lichess-std")
    except Exception as e:  # noqa: BLE001
        print("lichess-std übersprungen:", e)


if __name__ == "__main__":
    main()
