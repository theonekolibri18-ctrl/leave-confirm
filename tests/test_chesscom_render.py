"""Kontrastarme Figuren: chess.com-Farben mit cburnett-Figuren (gerendert), mehrere Themes, beide Orientierungen."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import chess  # noqa: E402
import chess.svg  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtCore import QByteArray  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

from chesslens.board_detect import extract_cells, find_board  # noqa: E402
from chesslens.game_tracker import guess_orientation  # noqa: E402
from chesslens.piece_recog import (START_FEN, analyze_cells, classify, grid_to_fen, guess_bottom_is_white,  # noqa: E402
                                   learn_profile, screen_to_grid, start_pattern_matches)

app = QGuiApplication.instance() or QGuiApplication([])

THEMES = {
    "chesscom-green": ("#ebecd0", "#739552"),
    "lichess-brown": ("#f0d9b5", "#b58863"),
    "blue": ("#dee3e6", "#8ca2ad"),
    "grey-lowcontrast": ("#f2f2f2", "#9a9a9a"),
    "purple": ("#f0e6f6", "#8877b7"),
}
POSITIONS = [
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
    "r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P1b1/2NP1N2/PPP2PPP/R2Q1RK1 w - - 0 8",
    "8/5k2/3p4/1p1Pp2p/pP2Pp1P/P4P1K/8/8 w - - 0 1",
    "r3k2r/1bq1bppp/p1nppn2/1p6/3NP3/1BN1B3/PPP1QPPP/R4RK1 w kq - 0 11",
]


def render(board, size, light, dark, flipped=False, lastmove=None):
    svg = chess.svg.board(board, size=size, coordinates=True, flipped=flipped, lastmove=lastmove,
                          colors={"square light": light, "square dark": dark,
                                  "square light lastmove": "#f6f669", "square dark lastmove": "#baca2b"})
    r = QSvgRenderer(QByteArray(svg.encode()))
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(0xFF202020)
    p = QPainter(img)
    r.render(p)
    p.end()
    return np.frombuffer(img.constBits(), np.uint8).reshape(size, size, 4)[:, :, :3].copy()


def main():
    ok = tot = 0
    for name, (light, dark) in THEMES.items():
        for size in (420, 824):
            for flipped in (False, True):
                start = render(chess.Board(), size, light, dark, flipped)
                rect = find_board(start)
                assert rect is not None, f"{name} {size}: Brett nicht gefunden"
                cells = extract_cells(start, rect)
                masks, occ, lum = analyze_cells(cells)
                assert start_pattern_matches(occ), f"{name} {size} flipped={flipped}: Grundstellung nicht erkannt"
                bw = guess_bottom_is_white(cells, occ, lum)
                assert bw == (not flipped), f"{name} {size}: Orientierung falsch ({bw})"
                prof = learn_profile(cells, START_FEN, bw, name, rect.light, rect.dark)
                assert prof is not None, f"{name} {size}: Profil unvollständig"
                for fen in POSITIONS:
                    b = chess.Board(fen)
                    lm = next(iter(b.legal_moves))
                    img = render(b, size, light, dark, flipped, lastmove=lm)
                    r2 = find_board(img)
                    res, _ = classify(extract_cells(img, r2), prof)
                    screen = [[res[r][c].piece for c in range(8)] for r in range(8)]
                    got = grid_to_fen(screen_to_grid(screen, bw))
                    tot += 1
                    if got == b.board_fen():
                        ok += 1
                    else:
                        print(f"FEHLER {name} {size} flipped={flipped}: {got} | soll {b.board_fen()}")
                    # Orientierungs-Schätzung aus der Stellung (ohne Grundstellung)
                    if guess_orientation(screen, True) != bw and guess_orientation(screen, False) != bw:
                        print(f"ORIENTIERUNG unklar {name} {size} flipped={flipped} {fen}")
    print(f"Gerenderte Themes: {ok}/{tot}")


if __name__ == "__main__":
    main()
