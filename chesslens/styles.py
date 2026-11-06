"""Spielstile: sortieren die Engine-Kandidaten nach Charakter um.

Die Engine liefert mehrere Varianten (MultiPV). Jeder Stil vergibt Bonuspunkte
(in Bauerneinheiten/100) und wählt unter den Zügen, die höchstens `risk_cp`
schlechter als der objektiv beste sind, den stilistisch passendsten.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import chess

from . import chess_util as cu
from .engine import MATE_CP, Line, SyncEngine

log = logging.getLogger(__name__)

STYLES = {
    "engine": "Engine pur",
    "aggressiv": "Aggressiv",
    "solide": "Solide",
    "trickreich": "Trickreich",
}
STYLE_INFO = {
    "engine": "Objektiv bester Zug laut Stockfish.",
    "aggressiv": "Bevorzugt Schachs, Angriffe auf den König, Opfer und Druck.",
    "solide": "Bevorzugt sichere Züge ohne hängende Figuren und ohne Risiko.",
    "trickreich": "Bevorzugt Züge, bei denen der naheliegende Gegenzug verliert.",
}


@dataclass
class Choice:
    line: Line
    bonus: int = 0
    tags: list[str] = field(default_factory=list)
    trap: Optional[tuple[chess.Move, int]] = None  # (natürliche Antwort, Gewinn in cp)

    @property
    def total(self) -> int:
        return self.line.score_cp + self.bonus


def _mate_like(cp: int) -> bool:
    return abs(cp) > MATE_CP // 2


def _features(board: chess.Board, line: Line) -> dict:
    mv = line.move
    me = board.turn
    after = board.copy()
    after.push(mv)
    f: dict = {}
    f["check"] = after.is_check()
    f["capture"] = board.is_capture(mv)
    f["castle"] = board.is_castling(mv)
    f["develop"] = cu.is_developing_move(board, mv)
    piece = board.piece_at(mv.from_square)
    f["piece"] = piece.piece_type if piece else chess.PAWN
    rank = chess.square_rank(mv.to_square)
    f["into_enemy_half"] = (rank >= 4) if me == chess.WHITE else (rank <= 3)
    f["pressure_before"] = cu.king_zone_pressure(board, me)
    f["pressure_after"] = cu.king_zone_pressure(after, me)
    f["own_hanging_after"] = len(cu.hanging_pieces(after, me))
    f["own_hanging_before"] = len(cu.hanging_pieces(board, me))
    f["enemy_hanging_after"] = len(cu.hanging_pieces(after, not me))
    f["own_king_pressure_after"] = cu.king_zone_pressure(after, not me)
    f["weak_before"] = cu.pawn_weaknesses(board, me)
    f["weak_after"] = cu.pawn_weaknesses(after, me)
    # Material nach 2 Halbzügen der Hauptvariante (Opfer-Erkennung)
    bal_now = cu.material_balance(board, me)
    b2 = board.copy()
    for m in line.pv[:2]:
        if m in b2.legal_moves:
            b2.push(m)
    f["material_after_reply"] = cu.material_balance(b2, me) - bal_now
    b4 = board.copy()
    for m in line.pv[:4]:
        if m in b4.legal_moves:
            b4.push(m)
    f["material_after_4"] = cu.material_balance(b4, me) - bal_now
    f["sacrifice"] = f["material_after_reply"] <= -150 and f["material_after_4"] <= -100
    f["forks"] = cu.forked_pieces(after, mv.to_square, me)
    f["moved_piece_hangs"] = mv.to_square in cu.hanging_pieces(after, me)
    return f


def _aggressive_bonus(f: dict) -> tuple[int, list[str]]:
    b, tags = 0, []
    if f["check"]:
        b += 30
        tags.append("Schach")
    if f["capture"]:
        b += 15
    if f["sacrifice"]:
        b += 45
        tags.append("Opfer")
    dp = f["pressure_after"] - f["pressure_before"]
    if dp > 0:
        b += min(40, 8 * dp)
        tags.append("Druck auf den König")
    if f["into_enemy_half"] and f["piece"] != chess.KING:
        b += 10
    if len(f["forks"]) >= 2:
        b += 25
        tags.append("Gabel")
    if f["castle"]:
        b -= 15
    if f["piece"] == chess.KING and not f["castle"]:
        b -= 20
    return b, tags


def _solid_bonus(f: dict) -> tuple[int, list[str]]:
    b, tags = 0, []
    b -= 35 * f["own_hanging_after"]
    if f["own_hanging_after"] < f["own_hanging_before"]:
        b += 25
        tags.append("sichert eine Figur")
    if f["moved_piece_hangs"]:
        b -= 40
    if f["sacrifice"]:
        b -= 60
    if f["castle"]:
        b += 45
        tags.append("König in Sicherheit")
    if f["develop"]:
        b += 15
        tags.append("Entwicklung")
    b -= 10 * f["own_king_pressure_after"]
    b -= 12 * max(0, f["weak_after"] - f["weak_before"])
    if f["check"] and f["moved_piece_hangs"]:
        b -= 20
    return b, tags


def rank_choices(board: chess.Board, lines: list[Line], style: str, risk_cp: int = 60,
                 sync: Optional[SyncEngine] = None) -> list[Choice]:
    """Liefert die Kandidaten in Stil-Reihenfolge (erstes Element = Empfehlung)."""
    if not lines:
        return []
    best = max(l.score_cp for l in lines)
    choices = [Choice(l) for l in lines]
    if style == "engine" or len(lines) == 1 or _mate_like(best):
        # Bei Matt-Varianten oder 'Engine pur' zählt nur die Objektivität
        return sorted(choices, key=lambda c: -c.line.score_cp)

    eligible = [c for c in choices if c.line.score_cp >= best - risk_cp and not _mate_like(c.line.score_cp)]
    if not eligible:
        return sorted(choices, key=lambda c: -c.line.score_cp)

    for c in eligible:
        try:
            f = _features(board, c.line)
        except Exception as e:  # noqa: BLE001
            log.debug("Feature-Fehler: %s", e)
            continue
        if style == "aggressiv":
            c.bonus, c.tags = _aggressive_bonus(f)
        elif style == "solide":
            c.bonus, c.tags = _solid_bonus(f)
        elif style == "trickreich":
            c.bonus, c.tags = 0, []
            if sync is not None:
                trap = _trap_score(board, c.line, sync)
                if trap is not None and trap[1] >= 120:
                    c.trap = trap
                    c.bonus = int(min(trap[1], 600) * 0.4)
                    c.tags.append("Falle")
            if f["check"]:
                c.bonus += 5
    rest = [c for c in choices if c not in eligible]
    eligible.sort(key=lambda c: -c.total)
    rest.sort(key=lambda c: -c.line.score_cp)
    return eligible + rest


def _natural_replies(board_after: chess.Board, our_move: chess.Move, sync: SyncEngine) -> list[chess.Move]:
    """Was würde ein Mensch 'naheliegend' antworten?"""
    out: list[chess.Move] = []
    legal = list(board_after.legal_moves)
    # 1) Zurückschlagen auf dem Zielfeld
    recaps = [m for m in legal if m.to_square == our_move.to_square and board_after.is_capture(m)]
    if recaps:
        recaps.sort(key=lambda m: cu.VALUE[board_after.piece_at(m.from_square).piece_type])
        out.append(recaps[0])
    # 2) Wertvollste Figur schlagen (mit der billigsten Figur)
    caps = [m for m in legal if board_after.is_capture(m)]
    if caps:
        def gain(m):
            victim = board_after.piece_at(m.to_square)
            v = cu.VALUE[victim.piece_type] if victim else 100  # en passant
            return (-v, cu.VALUE[board_after.piece_at(m.from_square).piece_type])
        caps.sort(key=gain)
        if caps[0] not in out:
            out.append(caps[0])
    # 3) Schach geben
    for m in legal:
        if board_after.gives_check(m):
            if m not in out:
                out.append(m)
            break
    # 4) flache Engine-Antwort (wie ein schneller Spieler)
    try:
        shallow = sync.best(board_after, depth=3)
        if shallow and shallow[0].move not in out:
            out.append(shallow[0].move)
    except Exception:  # noqa: BLE001
        pass
    return out[:4]


def _trap_score(board: chess.Board, line: Line, sync: SyncEngine) -> Optional[tuple[chess.Move, int]]:
    """Wie viel verliert der Gegner, wenn er auf unseren Zug 'naheliegend' antwortet?"""
    after = board.copy()
    after.push(line.move)
    if after.is_game_over():
        return None
    best_reply = None
    best_gain = 0
    for reply in _natural_replies(after, line.move, sync):
        b = after.copy()
        b.push(reply)
        try:
            ev = sync.evaluate(b, depth=9)  # aus unserer Sicht (wir sind wieder am Zug)
        except Exception:  # noqa: BLE001
            continue
        gain = ev - line.score_cp
        if gain > best_gain:
            best_gain, best_reply = gain, reply
    if best_reply is None:
        return None
    return best_reply, best_gain
