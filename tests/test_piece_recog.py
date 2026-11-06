"""Figuren-Erkennung: Profil aus Screenshot 1 lernen, alle Stellungen prüfen (auch skaliert)."""

import os
import sys
import time

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chesslens.board_detect import extract_cells, find_board  # noqa: E402
from chesslens.piece_recog import (classify, grid_to_fen, learn_profile, screen_to_grid)  # noqa: E402
from tests.ground_truth import SHOTS, UPLOADS  # noqa: E402
from tests.test_board_detect import fake_desktop  # noqa: E402

BOTTOM_WHITE = False  # in allen Screenshots steht Schwarz unten


def recognized_fen(img, profile):
    rect = find_board(img)
    assert rect is not None
    cells = extract_cells(img, rect)
    res, occ = classify(cells, profile)
    screen = [[res[r][c].piece for c in range(8)] for r in range(8)]
    grid = screen_to_grid(screen, BOTTOM_WHITE)
    return grid_to_fen(grid), res


def diff_fens(a: str, b: str) -> str:
    from chesslens.piece_recog import fen_grid
    ga, gb = fen_grid(a), fen_grid(b)
    out = []
    for r in range(8):
        for c in range(8):
            if ga[r][c] != gb[r][c]:
                out.append(f"{'abcdefgh'[c]}{8 - r}: ist {ga[r][c] or '-'} soll {gb[r][c] or '-'}")
    return ", ".join(out)


def main() -> None:
    fname0, fen0, _ = SHOTS[0]
    img0 = cv2.imread(os.path.join(UPLOADS, fname0))
    rect0 = find_board(img0)
    cells0 = extract_cells(img0, rect0)
    prof = learn_profile(cells0, fen0, BOTTOM_WHITE, "test", rect0.light, rect0.dark)
    assert prof is not None, "Profil konnte nicht gelernt werden"
    print(f"Profil gelernt: white_lum={prof.white_lum:.0f} black_lum={prof.black_lum:.0f}")

    ok = 0
    for fname, fen, _ in SHOTS:
        img = cv2.imread(os.path.join(UPLOADS, fname))
        t0 = time.time()
        got, res = recognized_fen(img, prof)
        dt = (time.time() - t0) * 1000
        good = got == fen
        ok += good
        print(f"{fname}: {'OK' if good else 'FEHLER ' + diff_fens(got, fen)} ({dt:.0f} ms)")
    print(f"\nOriginalgröße: {ok}/{len(SHOTS)}")

    ok2 = tot2 = 0
    for fname, fen, _ in SHOTS[1::2]:
        img = cv2.imread(os.path.join(UPLOADS, fname))
        for sc in (0.3, 0.5, 0.75, 1.4):
            desk, _ = fake_desktop(img, scale=sc) if sc <= 1.0 else (cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC), None)
            got, res = recognized_fen(desk, prof)
            tot2 += 1
            good = got == fen
            ok2 += good
            if not good:
                print(f"skaliert x{sc} {fname}: FEHLER {diff_fens(got, fen)}")
    print(f"Skaliert: {ok2}/{tot2}")


if __name__ == "__main__":
    main()
