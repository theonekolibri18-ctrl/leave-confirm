"""Führt die Partie (chess.Board) anhand der erkannten Stellungen nach.

Aus zwei aufeinanderfolgenden Stellungen wird der gespielte Zug rekonstruiert
(inkl. Rochade, en passant, Umwandlung). Passt kein legaler Zug, wird die
Stellung neu gesetzt ("Resync") und die Zugfarbe geschätzt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import chess

from .piece_recog import START_FEN, fen_grid, grid_to_fen, screen_to_grid

log = logging.getLogger(__name__)

PIECE_FROM_KEY = {
    "K": chess.KING, "Q": chess.QUEEN, "R": chess.ROOK,
    "B": chess.BISHOP, "N": chess.KNIGHT, "P": chess.PAWN,
}


def piece_map_from_grid(grid: list[list[str]]) -> dict[int, chess.Piece]:
    """FEN-Gitter (Zeile 0 = Reihe 8) -> {square: Piece}."""
    out: dict[int, chess.Piece] = {}
    for r in range(8):
        for c in range(8):
            key = grid[r][c]
            if key:
                sq = chess.square(c, 7 - r)
                out[sq] = chess.Piece(PIECE_FROM_KEY[key[1]], key[0] == "w")
    return out


def same_position(a: chess.Board, pm: dict[int, chess.Piece]) -> bool:
    return a.piece_map() == pm


def orientation_score(grid: list[list[str]]) -> int:
    """Wie plausibel ist dieses FEN-Gitter (Weiß unten)? Höher = plausibler."""
    pm = piece_map_from_grid(grid)
    score = 0
    for sq, p in pm.items():
        rank = chess.square_rank(sq)  # 0 = Reihe 1
        if p.piece_type == chess.KING:
            if p.color == chess.WHITE:
                score += 3 if rank <= 1 else (1 if rank <= 3 else -3)
            else:
                score += 3 if rank >= 6 else (1 if rank >= 4 else -3)
        elif p.piece_type == chess.PAWN:
            if p.color == chess.WHITE:
                score += 1 if rank <= 3 else -1
            else:
                score += 1 if rank >= 4 else -1
        elif p.piece_type in (chess.ROOK, chess.QUEEN, chess.BISHOP, chess.KNIGHT):
            if p.color == chess.WHITE:
                score += 1 if rank <= 2 else 0
            else:
                score += 1 if rank >= 5 else 0
    return score


def guess_orientation(screen_grid: list[list[str]], current_bottom_is_white: bool) -> bool:
    """Prüft, ob die Stellung mit Weiß oder Schwarz unten plausibler ist."""
    a = orientation_score(screen_to_grid(screen_grid, True))
    b = orientation_score(screen_to_grid(screen_grid, False))
    if abs(a - b) < 3:
        return current_bottom_is_white
    return a > b


@dataclass
class UpdateResult:
    changed: bool = False
    new_game: bool = False
    resynced: bool = False
    moves: list[chess.Move] = field(default_factory=list)
    message: str = ""


class GameTracker:
    def __init__(self) -> None:
        self.board = chess.Board()
        self.bottom_is_white = True
        self.synced = True  # True = Zugfolge ab Partiestart bekannt
        self.last_move: Optional[chess.Move] = None
        self._pending_grid: Optional[list[list[str]]] = None
        self._pending_count = 0
        self.stable_frames = 2  # so oft muss dieselbe Stellung hintereinander erkannt werden

    # ------------------------------------------------------------------
    @property
    def user_color(self) -> bool:
        return chess.WHITE if self.bottom_is_white else chess.BLACK

    def flip_turn(self) -> None:
        self.board.turn = not self.board.turn
        self.board.clear_stack()
        self.synced = False

    def set_orientation(self, bottom_is_white: bool) -> None:
        self.bottom_is_white = bottom_is_white

    # ------------------------------------------------------------------
    def update_from_screen(self, screen_grid: list[list[str]]) -> UpdateResult:
        """screen_grid: 8x8 in Bildschirm-Orientierung ('' oder 'wK' ...)."""
        if not self.synced or self.board.fullmove_number == 1 and not self.board.move_stack:
            # Orientierung unbekannt/unsicher: aus der Stellung schätzen
            guess = guess_orientation(screen_grid, self.bottom_is_white)
            if guess != self.bottom_is_white:
                log.info("Orientierung geändert: Weiß unten = %s", guess)
                self.bottom_is_white = guess
        grid = screen_to_grid(screen_grid, self.bottom_is_white)
        # Entprellen: erst reagieren, wenn die Stellung mehrmals gleich erkannt wurde
        if grid == self._pending_grid:
            self._pending_count += 1
        else:
            self._pending_grid = grid
            self._pending_count = 1
        if self._pending_count < self.stable_frames:
            return UpdateResult()
        return self._apply(grid)

    def _apply(self, grid: list[list[str]]) -> UpdateResult:
        pm = piece_map_from_grid(grid)
        if same_position(self.board, pm):
            return UpdateResult()

        fen_board = grid_to_fen(grid)
        if fen_board == START_FEN:
            self.board = chess.Board()
            self.synced = True
            self.last_move = None
            return UpdateResult(changed=True, new_game=True, message="Neue Partie")

        # 1 Halbzug?
        for mv in self.board.legal_moves:
            self.board.push(mv)
            ok = same_position(self.board, pm)
            self.board.pop()
            if ok:
                self.board.push(mv)
                self.last_move = mv
                return UpdateResult(changed=True, moves=[mv])

        # 2 Halbzüge (eigener Zug + schnelle Antwort zwischen zwei Scans)?
        for mv1 in list(self.board.legal_moves):
            self.board.push(mv1)
            found = None
            for mv2 in self.board.legal_moves:
                self.board.push(mv2)
                if same_position(self.board, pm):
                    found = mv2
                self.board.pop()
                if found:
                    break
            self.board.pop()
            if found:
                self.board.push(mv1)
                self.board.push(found)
                self.last_move = found
                return UpdateResult(changed=True, moves=[mv1, found])

        # Kein Zug passt -> Stellung übernehmen, Zugfarbe schätzen
        turn = self._guess_turn(pm)
        self._set_position(pm, turn)
        return UpdateResult(changed=True, resynced=True, message="Stellung neu übernommen")

    # ------------------------------------------------------------------
    def _guess_turn(self, pm: dict[int, chess.Piece]) -> bool:
        old = self.board.piece_map()
        moved = {chess.WHITE: False, chess.BLACK: False}
        for color in (chess.WHITE, chess.BLACK):
            old_sq = {sq for sq, p in old.items() if p.color == color}
            new_sq = {sq for sq, p in pm.items() if p.color == color}
            # Figuren dieser Farbe stehen woanders (nicht nur weniger) -> hat gezogen
            if new_sq - old_sq:
                moved[color] = True
        if moved[chess.WHITE] != moved[chess.BLACK]:
            return chess.BLACK if moved[chess.WHITE] else chess.WHITE
        return self.user_color  # unklar: im Zweifel ist der Nutzer dran

    def _set_position(self, pm: dict[int, chess.Piece], turn: bool) -> None:
        b = chess.Board(None)
        for sq, p in pm.items():
            b.set_piece_at(sq, p)
        b.turn = turn
        rights = ""
        if b.piece_at(chess.E1) == chess.Piece(chess.KING, True):
            if b.piece_at(chess.H1) == chess.Piece(chess.ROOK, True):
                rights += "K"
            if b.piece_at(chess.A1) == chess.Piece(chess.ROOK, True):
                rights += "Q"
        if b.piece_at(chess.E8) == chess.Piece(chess.KING, False):
            if b.piece_at(chess.H8) == chess.Piece(chess.ROOK, False):
                rights += "k"
            if b.piece_at(chess.A8) == chess.Piece(chess.ROOK, False):
                rights += "q"
        try:
            b.set_castling_fen(rights or "-")
        except ValueError:
            pass
        self.board = b
        self.synced = False
        self.last_move = None

    def set_position_fen(self, fen: str) -> None:
        self.board = chess.Board(fen)
        self.synced = False
        self.last_move = None

    def san_history(self) -> list[str]:
        """Zugliste (SAN) ab dem Beginn des bekannten Verlaufs."""
        b = self.board.copy()
        moves = []
        while b.move_stack:
            moves.append(b.pop())
        moves.reverse()
        out = []
        for mv in moves:
            out.append(b.san(mv))
            b.push(mv)
        return out
