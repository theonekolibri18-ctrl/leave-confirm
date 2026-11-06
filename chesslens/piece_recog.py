"""Figuren-Erkennung über Profile (Vorlagen), die aus der Grundstellung gelernt werden.

Ablauf:
  1. Jede Zelle wird 48x48 skaliert. Die Hintergrundfarbe der Zelle schätzen wir
     aus den vier Ecken (dort steht fast nie eine Figur, und Zug-Hervorhebungen
     verändern die ganze Zelle gleichmäßig).
  2. Vordergrundmaske = Pixel, die deutlich von der Hintergrundfarbe abweichen.
  3. Figurenfarbe = Median-Helligkeit der Vordergrundpixel (weiß hell, schwarz dunkel).
  4. Figurentyp = beste Übereinstimmung (Masken-IoU + normierte Kreuzkorrelation)
     mit den Vorlagen gleicher Farbe aus dem Profil.

Ein Profil entsteht automatisch, sobald die Grundstellung auf dem Brett steht –
dann wissen wir für alle 32 Figuren, was sie darstellen.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

CELL = 48
PIECE_KEYS = [c + t for c in "wb" for t in "KQRBNP"]
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


@dataclass
class Profile:
    name: str
    light: tuple[int, int, int] = (0, 0, 0)
    dark: tuple[int, int, int] = (0, 0, 0)
    white_lum: float = 220.0
    black_lum: float = 50.0
    templates: dict[str, list[tuple[np.ndarray, np.ndarray]]] = field(default_factory=dict)
    white_feat: tuple[float, float, float] = (200.0, 230.0, 250.0)  # Perzentile 25/50/75 der Figurenhelligkeit
    black_feat: tuple[float, float, float] = (20.0, 40.0, 70.0)

    def piece_color(self, feat: tuple[float, float, float]) -> str:
        dw = sum(abs(a - b) for a, b in zip(feat, self.white_feat))
        db = sum(abs(a - b) for a, b in zip(feat, self.black_feat))
        return "w" if dw <= db else "b"

    # ---- Persistenz -------------------------------------------------------
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        arrays = {}
        meta = {"name": self.name, "light": list(self.light), "dark": list(self.dark),
                "white_lum": self.white_lum, "black_lum": self.black_lum, "counts": {},
                "white_feat": list(self.white_feat), "black_feat": list(self.black_feat)}
        for key, lst in self.templates.items():
            meta["counts"][key] = len(lst)
            for i, (g, m) in enumerate(lst):
                arrays[f"{key}_{i}_g"] = g.astype(np.float32)
                arrays[f"{key}_{i}_m"] = m.astype(np.uint8)
        np.savez_compressed(path, meta=json.dumps(meta), **arrays)

    @staticmethod
    def load(path: str) -> "Profile":
        data = np.load(path, allow_pickle=False)
        meta = json.loads(str(data["meta"]))
        p = Profile(meta["name"], tuple(meta["light"]), tuple(meta["dark"]), meta["white_lum"], meta["black_lum"])
        if "white_feat" in meta:
            p.white_feat = tuple(meta["white_feat"])
            p.black_feat = tuple(meta["black_feat"])
        else:  # alte Profile: aus den Medianen ableiten
            p.white_feat = (p.white_lum - 30, p.white_lum, min(255.0, p.white_lum + 15))
            p.black_feat = (max(0.0, p.black_lum - 15), p.black_lum, p.black_lum + 30)
        for key, n in meta["counts"].items():
            p.templates[key] = [(data[f"{key}_{i}_g"], data[f"{key}_{i}_m"].astype(bool)) for i in range(n)]
        return p

    def complete(self) -> bool:
        return all(self.templates.get(k) for k in PIECE_KEYS)

    def color_distance(self, light, dark) -> float:
        a = np.abs(np.array(self.light, np.float32) - np.array(light, np.float32)).max()
        b = np.abs(np.array(self.dark, np.float32) - np.array(dark, np.float32)).max()
        return float(max(a, b))


# ----------------------------------------------------------------------------
# Zellanalyse
# ----------------------------------------------------------------------------

def _bg_color(cell: np.ndarray) -> np.ndarray:
    """Hintergrundfarbe = Median eines Rings am Zellrand (ohne die äußersten Pixel).

    Figuren berühren den Rand selten, Hervorhebungs-Rahmen liegen ganz außen
    und werden durch den Abstand ausgeschlossen.
    """
    n = cell.shape[0]
    m = max(2, int(round(n * 0.08)))
    k = max(m + 2, int(round(n * 0.25)))
    ring = np.concatenate([
        cell[m:k, m : n - m].reshape(-1, 3),  # oben
        cell[n - k : n - m, m : n - m].reshape(-1, 3),  # unten
        cell[k : n - k, m:k].reshape(-1, 3),  # links
        cell[k : n - k, n - k : n - m].reshape(-1, 3),  # rechts
    ], axis=0)
    return np.median(ring, axis=0)


def foreground_mask(cell: np.ndarray, thr: float = 42.0, weak: float = 18.0) -> tuple[np.ndarray, np.ndarray]:
    """(Maske der Figurenpixel, Hintergrundfarbe).

    Zwei Schwellen (Hysterese): deutlich abweichende Pixel sind sichere Figurenpixel,
    schwach abweichende zählen nur, wenn sie mit sicheren zusammenhängen. So werden
    auch weiße Figuren auf hellen Feldern komplett erfasst (nicht nur ihre Umrisse).
    Anschließend werden Löcher gefüllt (Figuren haben geschlossene Umrisse).
    """
    n = cell.shape[0]
    bg = _bg_color(cell)
    dist = np.abs(cell.astype(np.float32) - bg[None, None, :]).max(axis=2)
    strong = dist > thr
    weak_m = (dist > weak).astype(np.uint8)
    # Äußeren Rand ignorieren (Rahmen von Hervorhebungen, Brettlinien, Bildrand)
    b = max(2, int(round(n * 0.08)))
    weak_m[:b, :] = 0
    weak_m[-b:, :] = 0
    weak_m[:, :b] = 0
    weak_m[:, -b:] = 0
    strong[:b, :] = False
    strong[-b:, :] = False
    strong[:, :b] = False
    strong[:, -b:] = False
    n_lab, lab, stats, _ = cv2.connectedComponentsWithStats(weak_m, connectivity=8)
    keep_ids = np.unique(lab[strong])
    keep_ids = keep_ids[keep_ids != 0]
    # Rahmen von Hervorhebungen: dünner Ring, der fast die ganze Zelle umspannt -> keine Figur
    ring_ids = [i for i in keep_ids
                if stats[i, cv2.CC_STAT_WIDTH] >= 0.8 * n and stats[i, cv2.CC_STAT_HEIGHT] >= 0.8 * n
                and stats[i, cv2.CC_STAT_AREA] < 0.3 * stats[i, cv2.CC_STAT_WIDTH] * stats[i, cv2.CC_STAT_HEIGHT]]
    keep_ids = np.array([i for i in keep_ids if i not in ring_ids], dtype=lab.dtype)
    mask = np.isin(lab, keep_ids)
    # Löcher füllen: alles, was vom Zellrand aus nicht erreichbar ist, gehört zur Figur
    inv = (~mask).astype(np.uint8)
    n_inv, lab_inv = cv2.connectedComponents(inv, connectivity=4)
    border_ids = np.unique(np.concatenate([lab_inv[0, :], lab_inv[-1, :], lab_inv[:, 0], lab_inv[:, -1]]))
    holes = inv.astype(bool) & ~np.isin(lab_inv, border_ids)
    mask = mask | holes
    # Kleine Störungen entfernen (Koordinaten-Buchstaben, Antialiasing)
    m8 = mask.astype(np.uint8)
    n_lab, lab, stats, _ = cv2.connectedComponentsWithStats(m8, connectivity=8)
    keep = np.zeros_like(m8)
    area_min = 0.012 * m8.size
    for i in range(1, n_lab):
        if stats[i, cv2.CC_STAT_AREA] >= area_min:
            keep[lab == i] = 1
    return keep.astype(bool), bg


def is_occupied(mask: np.ndarray) -> bool:
    n = mask.shape[0]
    frac = mask.mean()
    if frac < 0.06:
        return False
    c0, c1 = int(n * 0.2), int(n * 0.8)
    center = mask[c0:c1, c0:c1].mean()
    return center > 0.05


def _neutralized(cell: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Graustufenbild, in dem der Hintergrund durch Mittelgrau ersetzt ist."""
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY).astype(np.float32)
    m = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    out = np.full_like(gray, 128.0)
    out[m] = gray[m]
    return out


def piece_features(cell: np.ndarray, mask: np.ndarray) -> tuple[float, float, float]:
    """Helligkeits-Perzentile (25/50/75) der Figurenpixel – robust gegen Umrisse und Details."""
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    vals = gray[mask]
    if vals.size < 5:
        return (128.0, 128.0, 128.0)
    p = np.percentile(vals, [25, 50, 75])
    return (float(p[0]), float(p[1]), float(p[2]))


def piece_luminance(cell: np.ndarray, mask: np.ndarray) -> float:
    return piece_features(cell, mask)[1]


def _match(g: np.ndarray, m: np.ndarray, tg: np.ndarray, tm: np.ndarray) -> float:
    inter = np.logical_and(m, tm).sum()
    union = np.logical_or(m, tm).sum()
    iou = inter / union if union else 0.0
    # Kreuzkorrelation mit ±3 px Verschiebungstoleranz
    pad = 3
    cand = cv2.copyMakeBorder(g, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=128.0)
    res = cv2.matchTemplate(cand, tg, cv2.TM_CCOEFF_NORMED)
    ncc = float(res.max()) if res.size else 0.0
    return 0.45 * iou + 0.55 * max(0.0, ncc)


# ----------------------------------------------------------------------------
# Klassifikation
# ----------------------------------------------------------------------------

@dataclass
class CellResult:
    piece: str = ""  # '' = leer, sonst z.B. 'wK'
    confidence: float = 0.0
    lum: float = 0.0


def analyze_cells(cells: np.ndarray) -> tuple[list[list[np.ndarray]], np.ndarray, np.ndarray]:
    """Masken, Belegung (8x8 bool) und Figurenhelligkeit (8x8 x 3 Perzentile) für alle Zellen."""
    masks: list[list[np.ndarray]] = [[None] * 8 for _ in range(8)]  # type: ignore[list-item]
    occ = np.zeros((8, 8), bool)
    lum = np.zeros((8, 8, 3), np.float32)
    for r in range(8):
        for c in range(8):
            m, _ = foreground_mask(cells[r, c])
            masks[r][c] = m
            occ[r, c] = is_occupied(m)
            lum[r, c] = piece_features(cells[r, c], m) if occ[r, c] else 0.0
    return masks, occ, lum


def classify(cells: np.ndarray, profile: Profile) -> tuple[list[list[CellResult]], np.ndarray]:
    """Erkennt alle 64 Felder mit einem Profil. Liefert Ergebnisse und Belegungsmaske."""
    masks, occ, lum = analyze_cells(cells)
    out = [[CellResult() for _ in range(8)] for _ in range(8)]
    for r in range(8):
        for c in range(8):
            if not occ[r, c]:
                continue
            color = profile.piece_color(tuple(lum[r, c]))
            g = _neutralized(cells[r, c], masks[r][c])
            best_key, best_s, second = "", -1.0, -1.0
            for t in "KQRBNP":
                key = color + t
                s = -1.0
                for tg, tm in profile.templates.get(key, []):
                    s = max(s, _match(g, masks[r][c], tg, tm))
                if s > best_s:
                    second, best_s, best_key = best_s, s, key
                elif s > second:
                    second = s
            if best_key:
                out[r][c] = CellResult(best_key, max(0.0, best_s - max(0.0, second)) + 0.5 * best_s, float(lum[r, c, 1]))
    return out, occ


# ----------------------------------------------------------------------------
# Lernen (Kalibrierung)
# ----------------------------------------------------------------------------

def fen_grid(fen_board: str) -> list[list[str]]:
    """FEN-Stellungsteil -> 8x8 Gitter (Zeile 0 = Reihe 8, Spalte 0 = Linie a), '' = leer."""
    rows = []
    for rank in fen_board.split("/"):
        row: list[str] = []
        for ch in rank:
            if ch.isdigit():
                row.extend([""] * int(ch))
            else:
                row.append(("w" if ch.isupper() else "b") + ch.upper())
        rows.append(row)
    return rows


def grid_to_screen(grid: list[list[str]], bottom_is_white: bool) -> list[list[str]]:
    """Dreht ein FEN-Gitter in Bildschirm-Orientierung (row 0 oben, col 0 links)."""
    if bottom_is_white:
        return [list(r) for r in grid]
    return [list(reversed(r)) for r in reversed(grid)]


def screen_to_grid(screen: list[list[str]], bottom_is_white: bool) -> list[list[str]]:
    return grid_to_screen(screen, bottom_is_white)  # Spiegelung ist ihre eigene Umkehrung


def grid_to_fen(grid: list[list[str]]) -> str:
    parts = []
    for row in grid:
        s, empty = "", 0
        for p in row:
            if not p:
                empty += 1
            else:
                if empty:
                    s += str(empty)
                    empty = 0
                s += p[1].upper() if p[0] == "w" else p[1].lower()
        if empty:
            s += str(empty)
        parts.append(s)
    return "/".join(parts)


def start_pattern_matches(occ: np.ndarray) -> bool:
    exp = np.zeros((8, 8), bool)
    exp[0:2, :] = True
    exp[6:8, :] = True
    return bool((occ == exp).sum() >= 63)


def guess_bottom_is_white(cells: np.ndarray, occ: np.ndarray, lum: np.ndarray) -> Optional[bool]:
    """Grundstellung: Die hellere Figurengruppe ist Weiß."""
    top = lum[0:2][occ[0:2]][:, 2]  # 75. Perzentil: weiße Figuren sind hier klar hell
    bot = lum[6:8][occ[6:8]][:, 2]
    if top.size < 10 or bot.size < 10:
        return None
    t, b = float(np.median(top)), float(np.median(bot))
    if abs(t - b) < 25:
        return None
    return b > t


def learn_profile(cells: np.ndarray, fen_board: str, bottom_is_white: bool, name: str,
                  light=(0, 0, 0), dark=(0, 0, 0), max_per_piece: int = 4) -> Optional[Profile]:
    """Erzeugt ein Profil aus einer bekannten Stellung."""
    screen = grid_to_screen(fen_grid(fen_board), bottom_is_white)
    masks, occ, lum = analyze_cells(cells)
    prof = Profile(name, tuple(int(v) for v in light), tuple(int(v) for v in dark))
    w_l, b_l = [], []
    for r in range(8):
        for c in range(8):
            key = screen[r][c]
            if not key:
                if occ[r, c]:
                    log.debug("Kalibrierung: Feld (%d,%d) sollte leer sein, ist belegt", r, c)
                continue
            if not occ[r, c]:
                log.debug("Kalibrierung: Feld (%d,%d) sollte %s sein, wirkt leer", r, c, key)
                continue
            g = _neutralized(cells[r, c], masks[r][c])
            prof.templates.setdefault(key, [])
            if len(prof.templates[key]) < max_per_piece:
                prof.templates[key].append((g, masks[r][c]))
            (w_l if key[0] == "w" else b_l).append(lum[r, c].copy())
    if not prof.complete():
        missing = [k for k in PIECE_KEYS if not prof.templates.get(k)]
        log.debug("Kalibrierung unvollständig, fehlt: %s", missing)
        return None
    w_arr, b_arr = np.array(w_l), np.array(b_l)
    prof.white_feat = tuple(float(v) for v in np.median(w_arr, axis=0))
    prof.black_feat = tuple(float(v) for v in np.median(b_arr, axis=0))
    prof.white_lum = prof.white_feat[1]
    prof.black_lum = prof.black_feat[1]
    if sum(abs(a - b) for a, b in zip(prof.white_feat, prof.black_feat)) < 60:
        return None
    return prof


def merge_profiles(old: Profile, new: Profile, max_per_piece: int = 6) -> Profile:
    """Neue Vorlagen zu einem bestehenden Profil hinzufügen (z.B. andere Fenstergröße)."""
    out = Profile(old.name, new.light, new.dark, (old.white_lum + new.white_lum) / 2, (old.black_lum + new.black_lum) / 2)
    out.white_feat = tuple((a + b) / 2 for a, b in zip(old.white_feat, new.white_feat))
    out.black_feat = tuple((a + b) / 2 for a, b in zip(old.black_feat, new.black_feat))
    for key in PIECE_KEYS:
        lst = list(new.templates.get(key, [])) + list(old.templates.get(key, []))
        out.templates[key] = lst[:max_per_piece]
    return out


# ----------------------------------------------------------------------------
# Plausibilität
# ----------------------------------------------------------------------------

def position_plausible(grid: list[list[str]]) -> bool:
    """Grobe Prüfung: genau ein König je Farbe, keine Bauern auf Grundreihen, Stückzahlen ok."""
    counts: dict[str, int] = {}
    for r, row in enumerate(grid):
        for p in row:
            if p:
                counts[p] = counts.get(p, 0) + 1
                if p[1] == "P" and r in (0, 7):
                    return False
    if counts.get("wK", 0) != 1 or counts.get("bK", 0) != 1:
        return False
    for col in "wb":
        if counts.get(col + "P", 0) > 8:
            return False
        total = sum(v for k, v in counts.items() if k[0] == col)
        if total > 16:
            return False
    return True
