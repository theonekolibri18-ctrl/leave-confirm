"""Regelbasierte Erklärungen auf Deutsch, warum ein Zug gut ist."""

from __future__ import annotations

import chess

from . import chess_util as cu
from .engine import MATE_CP, Line
from .styles import Choice


def _sq(sq: int) -> str:
    return chess.square_name(sq)


def _piece_at(board: chess.Board, sq: int) -> str:
    p = board.piece_at(sq)
    return cu.PIECE_DE[p.piece_type] if p else "Figur"


def eval_words(cp: int, mate: int | None, pov_is_user: bool = True) -> str:
    """Kurze Einschätzung aus Sicht des Nutzers."""
    who = "Du" if pov_is_user else "Der Gegner"
    if mate is not None:
        if mate > 0:
            return f"{who} {'setzt' if not pov_is_user else 'setzt'} Matt in {abs(mate)}!" if pov_is_user else f"Gegner hat Matt in {abs(mate)}"
        return f"{'Du wirst' if pov_is_user else 'Gegner wird'} in {abs(mate)} mattgesetzt"
    v = cp / 100.0
    a = abs(v)
    if a < 0.3:
        return "Ausgeglichen"
    if v > 0:
        if a < 1.0:
            return "Du stehst etwas besser"
        if a < 2.5:
            return "Du stehst klar besser"
        return "Du stehst auf Gewinn"
    if a < 1.0:
        return "Du stehst etwas schlechter"
    if a < 2.5:
        return "Du stehst klar schlechter"
    return "Du stehst auf Verlust"


def explain(board: chess.Board, choice: Choice, all_lines: list[Line] | None = None) -> list[str]:
    """Liefert 2–4 kurze Sätze zu `choice.line.move` in der Stellung `board`."""
    line = choice.line
    mv = line.move
    me = board.turn
    out: list[str] = []
    after = board.copy()
    after.push(mv)
    piece = board.piece_at(mv.from_square)
    pname = cu.PIECE_DE[piece.piece_type] if piece else "Figur"

    # Matt
    if line.mate is not None:
        if line.mate > 0:
            out.append("Matt in 1!" if line.mate == 1 else f"Erzwungenes Matt in {line.mate} Zügen.")
        else:
            out.append("Die Stellung ist verloren – dieser Zug hält am längsten durch.")
    if after.is_checkmate():
        return ["Schachmatt! Partie gewonnen."]

    # Schlagen / Material
    if board.is_capture(mv):
        victim_sq = mv.to_square
        victim = board.piece_at(victim_sq)
        vname = cu.PIECE_DE_AKK[victim.piece_type] if victim else "den Bauern (en passant)"
        bal_now = cu.material_balance(board, me)
        b2 = board.copy()
        for m in line.pv[:2]:
            if m in b2.legal_moves:
                b2.push(m)
        b4 = board.copy()
        for m in line.pv[:4]:
            if m in b4.legal_moves:
                b4.push(m)
        gain2 = cu.material_balance(b2, me) - bal_now
        gain4 = cu.material_balance(b4, me) - bal_now
        gain = gain4 if len(line.pv) >= 4 else gain2
        if gain >= 250:
            out.append(f"Schlägt {vname} auf {_sq(victim_sq)} und gewinnt eine Figur.")
        elif gain >= 80:
            out.append(f"Schlägt {vname} auf {_sq(victim_sq)} und gewinnt einen Bauern.")
        elif gain > -80:
            out.append(f"Schlägt {vname} auf {_sq(victim_sq)} – ein Abtausch, der die Stellung vereinfacht.")
        else:
            out.append(f"Schlägt {vname} auf {_sq(victim_sq)} – ein Opfer, das Angriff bringt.")

    # Rochade / Umwandlung / Schach
    if board.is_castling(mv):
        out.append("Bringt den König in Sicherheit und holt den Turm ins Spiel.")
    if mv.promotion:
        out.append(f"Wandelt in {'eine Dame' if mv.promotion == chess.QUEEN else cu.PIECE_DE[mv.promotion]} um.")
    if after.is_check() and not after.is_checkmate():
        out.append("Gibt Schach – der Gegner muss erst reagieren.")

    # Gabel / Fesselung / Drohung
    forks = cu.forked_pieces(after, mv.to_square, me)
    if len(forks) >= 2:
        names = " und ".join(f"{_piece_at(after, s)} {_sq(s)}" for s in forks[:2])
        out.append(f"Gabel: greift {names} gleichzeitig an.")
    else:
        pins_before = set(cu.pinned_by_move(board, me))
        pins_after = set(cu.pinned_by_move(after, me))
        new_pins = pins_after - pins_before
        if new_pins:
            sq, _ = next(iter(new_pins))
            out.append(f"Fesselt {cu.PIECE_DE_AKK[after.piece_at(sq).piece_type]} auf {_sq(sq)} an den König.")
        hang_before = set(cu.hanging_pieces(board, not me))
        hang_after = set(cu.hanging_pieces(after, not me))
        new_threats = [s for s in hang_after - hang_before if s in after.attacks(mv.to_square)]
        if new_threats and not board.is_capture(mv):
            s = max(new_threats, key=lambda q: cu.VALUE[after.piece_at(q).piece_type])
            out.append(f"Droht, {cu.PIECE_DE_AKK[after.piece_at(s).piece_type]} auf {_sq(s)} zu schlagen.")

    # Verteidigung
    my_hang_before = set(cu.hanging_pieces(board, me))
    my_hang_after = set(cu.hanging_pieces(after, me))
    if mv.from_square in my_hang_before and mv.to_square not in my_hang_after:
        out.append(f"Bringt {cu.PIECE_DE_AKK[piece.piece_type]} aus dem Angriff in Sicherheit.")
    else:
        saved = [s for s in my_hang_before if s not in my_hang_after and s != mv.from_square]
        if saved and not board.is_capture(mv):
            s = saved[0]
            out.append(f"Deckt {cu.PIECE_DE_AKK[after.piece_at(s).piece_type]} auf {_sq(s)}, der/die angegriffen war.")

    # Entwicklung / Zentrum
    if cu.is_developing_move(board, mv):
        out.append(f"Entwickelt {cu.PIECE_DE_AKK[piece.piece_type]} und bereitet die Rochade vor.")
    if piece and piece.piece_type == chess.PAWN and mv.to_square in (chess.D4, chess.E4, chess.D5, chess.E5, chess.C4, chess.C5):
        out.append("Kämpft ums Zentrum.")

    # Falle (Spielstil 'trickreich')
    if choice.trap is not None:
        reply, gain = choice.trap
        out.append(f"Falle: Spielt der Gegner das naheliegende {cu.san_de(after, reply)}, gewinnst du etwa {gain / 100:.1f} Bauerneinheiten.")

    # Idee aus der Hauptvariante
    if len(line.pv) >= 3:
        b = after.copy()
        reply = cu.san_de(b, line.pv[1])
        b.push(line.pv[1])
        nxt = cu.san_de(b, line.pv[2])
        out.append(f"Idee: Auf {reply} folgt {nxt}.")

    # Warnung: weiterhin hängende eigene Figur
    still = [s for s in my_hang_after if s != mv.to_square]
    if still and (line.mate is None or line.mate < 0):
        s = max(still, key=lambda q: cu.VALUE[after.piece_at(q).piece_type])
        out.append(f"Achtung: {cu.PIECE_DE[after.piece_at(s).piece_type]} auf {_sq(s)} bleibt angegriffen – im Blick behalten.")

    if not out:
        out.append(f"Verbessert die Stellung von {pname} – laut Engine der beste Zug.")
    # Doppelte Aussagen vermeiden, maximal 4 Punkte
    seen, final = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            final.append(s)
    return final[:4]


def opponent_threats(board: chess.Board, user_color: bool) -> list[str]:
    """Was droht der Gegner gerade (hängende eigene Figuren)?"""
    out = []
    for s in cu.hanging_pieces(board, user_color)[:2]:
        p = board.piece_at(s)
        out.append(f"{cu.PIECE_DE[p.piece_type]} {_sq(s)} ist angegriffen")
    return out
