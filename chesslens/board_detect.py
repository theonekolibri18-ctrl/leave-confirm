"""Automatische Erkennung eines 8x8-Schachbretts in einem Screenshot.

Idee: Leere Felder sind gleichmäßig gefärbte Quadrate. Wir suchen flache
(kantenarme) quadratische Flächen gleicher Größe, legen ein Gitter hindurch und
prüfen, ob die Feldfarben im Schachbrettmuster abwechseln. Das funktioniert für
praktisch jede Plattform – unabhängig von Farben, Figurensatz oder Fenstergröße.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import logging

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class BoardRect:
    """Position des Bretts im (vollaufgelösten) Screenshot."""

    x: float
    y: float
    size: float  # Kantenlänge des Bretts in Pixeln (8 Felder)
    light: tuple[int, int, int] = (200, 200, 200)  # BGR
    dark: tuple[int, int, int] = (100, 100, 100)  # BGR
    score: float = 0.0  # 0..1, Anteil der Felder mit passender Farbe

    @property
    def cell(self) -> float:
        return self.size / 8.0

    def as_int(self) -> tuple[int, int, int]:
        return int(round(self.x)), int(round(self.y)), int(round(self.size))

    def cell_rect(self, row: int, col: int) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) einer Zelle, row 0 = oben, col 0 = links."""
        c = self.cell
        x0 = int(round(self.x + col * c))
        y0 = int(round(self.y + row * c))
        x1 = int(round(self.x + (col + 1) * c))
        y1 = int(round(self.y + (row + 1) * c))
        return x0, y0, x1, y1


# ----------------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------------

def _corner_color(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    """Median-Farbe der vier Ecken einer Zelle (dort steht fast nie eine Figur)."""
    w = max(2, int((x1 - x0) * 0.14))
    h = max(2, int((y1 - y0) * 0.14))
    patches = [
        img[y0 : y0 + h, x0 : x0 + w],
        img[y0 : y0 + h, x1 - w : x1],
        img[y1 - h : y1, x0 : x0 + w],
        img[y1 - h : y1, x1 - w : x1],
    ]
    px = np.concatenate([p.reshape(-1, 3) for p in patches if p.size], axis=0)
    return np.median(px, axis=0)


def _color_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.max(np.abs(a.astype(np.float32) - b.astype(np.float32))))


def cell_colors(img: np.ndarray, rect: BoardRect) -> np.ndarray:
    """(8, 8, 3) Hintergrundfarbe jeder Zelle (aus den Ecken geschätzt)."""
    out = np.zeros((8, 8, 3), np.float32)
    H, W = img.shape[:2]
    for r in range(8):
        for c in range(8):
            x0, y0, x1, y1 = rect.cell_rect(r, c)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(W, x1), min(H, y1)
            if x1 - x0 < 3 or y1 - y0 < 3:
                continue
            out[r, c] = _corner_color(img, x0, y0, x1, y1)
    return out


def checker_score(img: np.ndarray, rect: BoardRect) -> tuple[float, np.ndarray, np.ndarray]:
    """Wie gut passt das Schachbrettmuster an dieser Position?

    Liefert (Anteil passender Felder, helle Farbe, dunkle Farbe).
    """
    H, W = img.shape[:2]
    m = rect.cell * 0.35  # kleine Toleranz, falls das Brett ganz am Bildrand klebt
    if rect.x < -m or rect.y < -m or rect.x + rect.size > W + m or rect.y + rect.size > H + m:
        return 0.0, np.zeros(3), np.zeros(3)
    cols = cell_colors(img, rect)
    par = (np.add.outer(np.arange(8), np.arange(8)) % 2) == 0
    a = cols[par].reshape(-1, 3)
    b = cols[~par].reshape(-1, 3)
    ca = np.median(a, axis=0)
    cb = np.median(b, axis=0)
    if _color_dist(ca, cb) < 18:  # beide Farbgruppen gleich -> kein Brett
        return 0.0, ca, cb
    tol = max(28.0, 0.35 * _color_dist(ca, cb))
    ok = 0
    for r in range(8):
        for c in range(8):
            exp = ca if par[r, c] else cb
            if _color_dist(cols[r, c], exp) <= tol:
                ok += 1
    light, dark = (ca, cb) if ca.mean() > cb.mean() else (cb, ca)
    return ok / 64.0, light, dark


def _refine_edges(img: np.ndarray, rect: BoardRect) -> BoardRect:
    """Brettposition anhand der 7 inneren Feldgrenzen nachjustieren.

    Die inneren Grenzen sind eindeutig (angrenzende Felder haben immer verschiedene
    Farben), die Außenkante dagegen oft von einem Rahmen überlagert.
    """
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    c = rect.cell
    band = max(2, int(c * 0.12))
    x0, y0 = rect.x, rect.y
    x1, y1 = rect.x + rect.size, rect.y + rect.size
    ys0, ys1 = max(0, int(y0 + c * 0.5)), min(H, int(y1 - c * 0.5))
    xs0, xs1 = max(0, int(x0 + c * 0.5)), min(W, int(x1 - c * 0.5))
    if ys1 - ys0 < 8 or xs1 - xs0 < 8:
        return rect
    # Anteil der Linienlänge mit deutlicher Kante: Feldgrenzen ~1.0, Figurenkanten deutlich weniger
    gx = (np.abs(np.diff(gray[ys0:ys1, :], axis=1)) > 10).mean(axis=0)  # Kante zwischen Spalte i und i+1 -> Position i+1
    gy = (np.abs(np.diff(gray[:, xs0:xs1], axis=0)) > 10).mean(axis=1)

    def fit(profile: np.ndarray, origin: float) -> Optional[tuple[float, float]]:
        ks, ps = [], []
        for k in range(1, 8):
            e = origin + k * c
            lo, hi = int(round(e - band)), int(round(e + band))
            lo, hi = max(lo, 0), min(hi, len(profile) - 1)
            if hi <= lo:
                continue
            seg = profile[lo : hi + 1]
            j = int(np.argmax(seg))
            if seg[j] < 0.5:
                continue
            ks.append(k)
            ps.append(lo + j + 1.0)
        if len(ks) < 4:
            return None
        A = np.vstack([np.ones(len(ks)), np.array(ks, np.float64)]).T
        sol, *_ = np.linalg.lstsq(A, np.array(ps, np.float64), rcond=None)
        o, p = float(sol[0]), float(sol[1])
        resid = np.abs(A @ sol - np.array(ps))
        if resid.max() > band or abs(p - c) > 0.08 * c:
            return None
        return o, p

    fx = fit(gx, x0)
    fy = fit(gy, y0)
    if fx is None or fy is None:
        return rect
    (nx0, px), (ny0, py) = fx, fy
    if abs(px - py) > 0.03 * c:
        return rect
    pitch = (px + py) / 2.0
    cand = BoardRect(nx0, ny0, pitch * 8)
    s_new, _, _ = checker_score(img, cand)
    s_old, _, _ = checker_score(img, rect)
    return cand if s_new >= s_old - 0.02 else rect


# ----------------------------------------------------------------------------
# Hauptfunktion
# ----------------------------------------------------------------------------

def verify_board(img: np.ndarray, rect: BoardRect, min_score: float = 0.86) -> Optional[BoardRect]:
    """Schneller Check, ob ein bekanntes Brett noch an derselben Stelle ist."""
    score, light, dark = checker_score(img, rect)
    if score < min_score:
        return None
    return BoardRect(rect.x, rect.y, rect.size, tuple(int(v) for v in light), tuple(int(v) for v in dark), score)


def find_board(img: np.ndarray, min_cell: int = 18, max_cell: int = 400) -> Optional[BoardRect]:
    """Sucht das Schachbrett im Bild. Liefert None, wenn keins gefunden wurde."""
    H, W = img.shape[:2]
    scale = 1.0
    work = img
    if max(H, W) > 2200:
        scale = 2200.0 / max(H, W)
        work = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = work.shape[:2]

    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    gxg = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    gyg = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gxg, gyg)
    flat = (mag < 40).astype(np.uint8)
    # Kleine Störungen (Antialiasing, Koordinaten-Buchstaben) wegschleifen
    flat = cv2.morphologyEx(flat, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    n, labels, stats, cents = cv2.connectedComponentsWithStats(flat, connectivity=4)
    lo = max(6, int(min_cell * scale * 0.7))
    hi = int(max_cell * scale * 1.1)
    cand = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bw < lo or bh < lo or bw > hi or bh > hi:
            continue
        ar = bw / float(bh)
        if ar < 0.82 or ar > 1.22:
            continue
        fill = area / float(bw * bh)
        if fill < 0.5:
            continue
        cand.append((cents[i][0], cents[i][1], bw, bh, fill))
    if len(cand) < 8:
        return None
    cand_arr = np.array(cand, dtype=np.float32)

    # Häufigste Quadratgröße finden (in log-Bins, damit große und kleine Felder fair behandelt werden)
    sizes = (cand_arr[:, 2] + cand_arr[:, 3]) / 2.0
    order = np.argsort(sizes)
    best_group = None
    best_cnt = 0
    for i in order:
        s = sizes[i]
        tol = max(s * 0.1, 2.0)
        sel = np.where((sizes >= s - tol) & (sizes <= s + tol * 1.2))[0]
        if len(sel) > best_cnt:
            best_cnt = len(sel)
            best_group = sel
    results = []
    tried = set()
    # Mehrere Größengruppen probieren (größte Gruppen zuerst), falls z.B. Icons dominieren
    groups = []
    rem = np.ones(len(sizes), bool)
    for _ in range(4):
        idx = np.where(rem)[0]
        if len(idx) < 8:
            break
        bc, bg = 0, None
        for i in idx:
            s = sizes[i]
            tol = max(s * 0.1, 2.0)
            sel = idx[(sizes[idx] >= s - tol) & (sizes[idx] <= s + tol * 1.2)]
            if len(sel) > bc:
                bc, bg = len(sel), sel
        if bg is None or bc < 8:
            break
        groups.append(bg)
        rem[bg] = False

    for grp in groups:
        g = cand_arr[grp]
        s0 = float(np.median((g[:, 2] + g[:, 3]) / 2.0))
        cx, cy = g[:, 0], g[:, 1]
        # Rasterabstand aus Nachbar-Abständen schätzen
        diffs = []
        for arr in (cx, cy):
            d = np.abs(arr[:, None] - arr[None, :])
            dd = d[(d > s0 * 0.85) & (d < s0 * 1.3)]
            diffs.extend(dd.tolist())
        pitch = float(np.median(diffs)) if len(diffs) >= 3 else s0 * 1.02
        if pitch < lo:
            continue

        rtol = max(pitch * 0.12, 2.5)

        def consensus_offset(vals: np.ndarray) -> float:
            # Offset so, dass vals - p/2 - off ≈ k*pitch
            phases = np.mod(vals - pitch / 2.0, pitch)
            best_o, best_n = 0.0, -1
            for ph in phases:
                dist = np.abs(((phases - ph + pitch / 2.0) % pitch) - pitch / 2.0)
                nn = int((dist < rtol).sum())
                if nn > best_n:
                    best_n, best_o = nn, float(ph)
            sel = np.abs(((phases - best_o + pitch / 2.0) % pitch) - pitch / 2.0) < rtol
            # Mittelwert der passenden Phasen (zirkulär genähert)
            adj = phases[sel]
            adj = np.where(adj - best_o > pitch / 2.0, adj - pitch, adj)
            adj = np.where(best_o - adj > pitch / 2.0, adj + pitch, adj)
            return float(np.mean(adj)) % pitch

        ox = consensus_offset(cx)
        oy = consensus_offset(cy)
        ix = np.round((cx - pitch / 2.0 - ox) / pitch).astype(int)
        iy = np.round((cy - pitch / 2.0 - oy) / pitch).astype(int)
        resx = np.abs(cx - (ox + ix * pitch + pitch / 2.0))
        resy = np.abs(cy - (oy + iy * pitch + pitch / 2.0))
        good = (resx < rtol) & (resy < rtol)
        log.debug('lattice: pitch=%.2f ox=%.1f oy=%.1f good=%d/%d', pitch, ox, oy, int(good.sum()), len(good))
        if good.sum() < 8:
            continue
        ix, iy = ix[good], iy[good]

        # Kandidaten-Fenster (8x8): die Fenster mit den meisten leeren Feldern darin
        # (robust gegen Ausreißer wie Taskleisten-Icons, die zufällig ins Raster passen)
        gx0, gy0 = int(ix.min()) - 7, int(iy.min()) - 7
        gw, gh = int(ix.max()) - gx0 + 1, int(iy.max()) - gy0 + 1
        hist = np.zeros((gh + 8, gw + 8), np.int32)
        for a, b in zip(ix, iy):
            hist[b - gy0, a - gx0] += 1
        cs = np.cumsum(np.cumsum(hist, axis=0), axis=1)
        cs = np.pad(cs, ((1, 0), (1, 0)))
        counts = cs[8:, 8:] - cs[:-8, 8:] - cs[8:, :-8] + cs[:-8, :-8]  # counts[sy-gy0, sx-gx0]
        maxc = int(counts.max())
        if maxc < 8:
            continue
        ys, xs = np.where(counts >= max(8, int(0.6 * maxc)))
        order2 = np.argsort(-counts[ys, xs])[:12]
        best = None
        for k in order2:
            sx, sy = int(xs[k]) + gx0, int(ys[k]) + gy0
            key = (round(ox + sx * pitch), round(oy + sy * pitch), round(pitch * 8))
            if key in tried:
                continue
            tried.add(key)
            bx = (ox + sx * pitch) / scale
            by = (oy + sy * pitch) / scale
            bs = pitch * 8 / scale
            m = bs / 8 * 0.35
            if bx < -m or by < -m or bx + bs > W + m or by + bs > H + m:
                continue
            rect = BoardRect(bx, by, bs)
            score, light, dark = checker_score(img, rect)
            inside = int(counts[ys[k], xs[k]])
            total = score + 0.002 * inside
            if best is None or total > best[0]:
                best = (total, rect, score, light, dark)
        log.debug('best window: %s', None if best is None else (round(best[2], 3), best[1].as_int()))
        if best is not None and best[2] >= 0.84:
            total, rect, score, light, dark = best
            rect = _refine_edges(img, rect)
            score, light, dark = checker_score(img, rect)
            rect.light = tuple(int(v) for v in light)
            rect.dark = tuple(int(v) for v in dark)
            rect.score = score
            results.append((score + 0.002 * best_cnt, rect))

    if not results:
        return None
    results.sort(key=lambda t: t[0], reverse=True)
    return results[0][1]


def extract_cells(img: np.ndarray, rect: BoardRect, size: int = 48) -> np.ndarray:
    """(8, 8, size, size, 3) BGR-Ausschnitte aller Felder, row 0 = oben, col 0 = links."""
    H, W = img.shape[:2]
    out = np.zeros((8, 8, size, size, 3), np.uint8)
    for r in range(8):
        for c in range(8):
            x0, y0, x1, y1 = rect.cell_rect(r, c)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(W, x1), min(H, y1)
            if x1 - x0 < 2 or y1 - y0 < 2:
                continue
            patch = img[y0:y1, x0:x1]
            out[r, c] = cv2.resize(patch, (size, size), interpolation=cv2.INTER_AREA)
    return out
