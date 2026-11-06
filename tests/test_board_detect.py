"""Brett-Erkennung an den Screenshots testen – pur und auf einen simulierten Desktop gelegt."""

import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chesslens.board_detect import find_board, verify_board  # noqa: E402
from tests.ground_truth import SHOTS, UPLOADS  # noqa: E402

rng = np.random.default_rng(1)


def fake_desktop(board_img: np.ndarray, W: int = 1920, H: int = 1080, scale: float = 1.0) -> tuple[np.ndarray, tuple]:
    """Legt den Screenshot auf einen 'Desktop' mit Störelementen (Icons, Fenster, Text)."""
    canvas = np.full((H, W, 3), (40, 36, 32), np.uint8)
    # Fenster-Rahmen und Taskleiste
    cv2.rectangle(canvas, (0, H - 48), (W, H), (60, 60, 60), -1)
    for i in range(12):  # Taskleisten-Icons (quadratisch -> Störquelle)
        x = 20 + i * 52
        cv2.rectangle(canvas, (x, H - 40), (x + 32, H - 8), tuple(int(v) for v in rng.integers(60, 230, 3)), -1)
    # Ein zweites Raster aus Kacheln (z.B. ein Dateimanager)
    for r in range(3):
        for c in range(5):
            x, y = 1400 + c * 90, 80 + r * 90
            col = (80, 120, 160) if (r + c) % 2 == 0 else (90, 130, 170)
            cv2.rectangle(canvas, (x, y), (x + 70, y + 70), col, -1)
    for i in range(30):  # Textzeilen
        cv2.putText(canvas, "Lorem ipsum dolor sit amet " * 2, (1300, 400 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    b = board_img
    if scale != 1.0:
        b = cv2.resize(b, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    bh, bw = b.shape[:2]
    ox, oy = int(rng.integers(0, max(1, W - bw - 400))), int(rng.integers(0, max(1, H - bh - 60)))
    canvas[oy : oy + bh, ox : ox + bw] = b
    return canvas, (ox, oy, bw, bh)


def main() -> None:
    ok = 0
    total = 0
    for fname, fen, _ in SHOTS:
        img = cv2.imread(os.path.join(UPLOADS, fname))
        t0 = time.time()
        rect = find_board(img)
        dt = (time.time() - t0) * 1000
        total += 1
        if rect is None:
            print(f"{fname}: NICHT gefunden ({dt:.0f} ms)")
            continue
        x, y, s = rect.as_int()
        # Im Screenshot füllt das Brett fast das ganze Bild: Kante ~ Bildgröße minus Rand
        exp = min(img.shape[:2]) - 8
        good = abs(s - exp) < 0.03 * exp
        ok += good
        print(f"{fname}: rect=({x},{y},{s}) score={rect.score:.2f} erwartet~{exp} {'OK' if good else 'ABWEICHUNG'} ({dt:.0f} ms)")

    print(f"\nPur: {ok}/{total}")

    # Desktop-Simulation in verschiedenen Skalierungen
    ok2 = 0
    tot2 = 0
    for i, (fname, fen, _) in enumerate(SHOTS[::3]):
        img = cv2.imread(os.path.join(UPLOADS, fname))
        for sc in (0.35, 0.6, 1.0):
            desk, (ox, oy, bw, bh) = fake_desktop(img, scale=sc)
            t0 = time.time()
            rect = find_board(desk)
            dt = (time.time() - t0) * 1000
            tot2 += 1
            if rect is None:
                print(f"desk {fname} x{sc}: NICHT gefunden ({dt:.0f} ms)")
                continue
            x, y, s = rect.as_int()
            exp = (min(bw, bh) - 8 * sc)
            good = abs(s - exp) < 0.04 * exp and abs(x - ox) < 0.05 * bw and abs(y - oy) < 0.05 * bh
            ok2 += good
            print(f"desk {fname} x{sc}: rect=({x},{y},{s}) board@({ox},{oy},{bw}) score={rect.score:.2f} {'OK' if good else 'ABWEICHUNG'} ({dt:.0f} ms)")
            if i == 0 and sc == 0.6:
                dbg = desk.copy()
                for k in range(9):
                    cv2.line(dbg, (int(x + k * s / 8), int(y)), (int(x + k * s / 8), int(y + s)), (0, 0, 255), 1)
                    cv2.line(dbg, (int(x), int(y + k * s / 8)), (int(x + s), int(y + k * s / 8)), (0, 0, 255), 1)
                cv2.imwrite("/tmp/detect_debug.png", dbg)
            # Schnell-Verifikation
            v = verify_board(desk, rect)
            assert v is not None, "verify_board sollte das gefundene Brett bestätigen"
    print(f"Desktop: {ok2}/{tot2}")


if __name__ == "__main__":
    main()
