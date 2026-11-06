"""Kleine Schach-Hilfsfunktionen (deutsch) rund um python-chess."""

from __future__ import annotations

import chess

PIECE_DE = {
    chess.KING: "König", chess.QUEEN: "Dame", chess.ROOK: "Turm",
    chess.BISHOP: "Läufer", chess.KNIGHT: "Springer", chess.PAWN: "Bauer",
}
PIECE_DE_AKK = {  # Akkusativ ("den Springer")
    chess.KING: "den König", chess.QUEEN: "die Dame", chess.ROOK: "den Turm",
    chess.BISHOP: "den Läufer", chess.KNIGHT: "den Springer", chess.PAWN: "den Bauern",
}
LETTER_DE = {chess.KING: "K", chess.QUEEN: "D", chess.ROOK: "T", chess.BISHOP: "L", chess.KNIGHT: "S", chess.PAWN: ""}
VALUE = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


def san_de(board: chess.Board, move: chess.Move) -> str:
    """SAN mit deutschen Figurenbuchstaben (K D T L S)."""
    san = board.san(move)
    out = []
    for ch in san:
        out.append({"N": "S", "B": "L", "R": "T", "Q": "D", "K": "K"}.get(ch, ch))
    return "".join(out)


def move_words(board: chess.Board, move: chess.Move) -> str:
    """Z.B. 'Springer g8 → f6', 'Kurze Rochade', 'Bauer e7 → e8 = Dame'."""
    if board.is_castling(move):
        return "Kurze Rochade (O-O)" if board.is_kingside_castling(move) else "Lange Rochade (O-O-O)"
    piece = board.piece_at(move.from_square)
    name = PIECE_DE.get(piece.piece_type, "Figur") if piece else "Figur"
    s = f"{name} {chess.square_name(move.from_square)} → {chess.square_name(move.to_square)}"
    if move.promotion:
        s += f" = {PIECE_DE[move.promotion]}"
    return s


def material(board: chess.Board, color: bool) -> int:
    return sum(VALUE[p.piece_type] for p in board.piece_map().values() if p.color == color)


def material_balance(board: chess.Board, color: bool) -> int:
    return material(board, color) - material(board, not color)


def attackers_value_min(board: chess.Board, color: bool, square: int) -> int:
    """Wert des günstigsten Angreifers von `color` auf `square` (0 = keiner)."""
    vals = [VALUE[board.piece_at(sq).piece_type] or 10_000 for sq in board.attackers(color, square)]
    return min(vals) if vals else 0


def hanging_pieces(board: chess.Board, color: bool) -> list[int]:
    """Figuren von `color`, die angegriffen und ungedeckt sind oder von billigerer Figur angegriffen werden."""
    out = []
    for sq, p in board.piece_map().items():
        if p.color != color or p.piece_type == chess.KING:
            continue
        att = attackers_value_min(board, not color, sq)
        if not att:
            continue
        defended = bool(board.attackers(color, sq))
        if not defended or att < VALUE[p.piece_type]:
            out.append(sq)
    return out


def king_zone(board: chess.Board, color: bool) -> list[int]:
    k = board.king(color)
    if k is None:
        return []
    zone = [k]
    f, r = chess.square_file(k), chess.square_rank(k)
    for df in (-1, 0, 1):
        for dr in (-1, 0, 1):
            if (df or dr) and 0 <= f + df < 8 and 0 <= r + dr < 8:
                zone.append(chess.square(f + df, r + dr))
    return zone


def king_zone_pressure(board: chess.Board, attacker: bool) -> int:
    """Wie viele Angriffe hat `attacker` auf die Felder um den gegnerischen König?"""
    return sum(len(board.attackers(attacker, sq)) for sq in king_zone(board, not attacker))


def pawn_weaknesses(board: chess.Board, color: bool) -> int:
    """Anzahl isolierter + Doppelbauern."""
    files = [0] * 8
    for sq in board.pieces(chess.PAWN, color):
        files[chess.square_file(sq)] += 1
    weak = 0
    for f in range(8):
        if files[f] == 0:
            continue
        if files[f] > 1:
            weak += files[f] - 1
        left = files[f - 1] if f > 0 else 0
        right = files[f + 1] if f < 7 else 0
        if left == 0 and right == 0:
            weak += 1
    return weak


def is_developing_move(board: chess.Board, move: chess.Move) -> bool:
    p = board.piece_at(move.from_square)
    if p is None or p.piece_type not in (chess.KNIGHT, chess.BISHOP):
        return False
    home = {chess.WHITE: {chess.B1, chess.G1, chess.C1, chess.F1}, chess.BLACK: {chess.B8, chess.G8, chess.C8, chess.F8}}
    return move.from_square in home[p.color]


def forked_pieces(board_after: chess.Board, square: int, color: bool) -> list[int]:
    """Welche wertvollen/ungedeckten gegnerischen Figuren greift die Figur auf `square` an?"""
    p = board_after.piece_at(square)
    if p is None:
        return []
    targets = []
    my_val = VALUE[p.piece_type] or 10_000
    for t in board_after.attacks(square):
        q = board_after.piece_at(t)
        if q is None or q.color == color:
            continue
        if q.piece_type == chess.KING:
            targets.append(t)
            continue
        defended = bool(board_after.attackers(not color, t))
        if VALUE[q.piece_type] > my_val or not defended:
            targets.append(t)
    return targets


def pinned_by_move(board_after: chess.Board, color: bool) -> list[tuple[int, int]]:
    """(gefesselte Figur, Figur dahinter) für gegnerische Figuren, die jetzt gefesselt sind."""
    out = []
    for sq, p in board_after.piece_map().items():
        if p.color == color or p.piece_type == chess.KING:
            continue
        if board_after.is_pinned(not color, sq):
            out.append((sq, board_after.king(not color)))
    return out
