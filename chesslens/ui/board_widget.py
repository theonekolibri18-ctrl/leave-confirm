"""Gezeichnetes Schachbrett mit Figuren (SVG aus python-chess), Zug-Markierung und Pfeilen."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import chess
import chess.svg
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme


@dataclass
class Arrow:
    move: chess.Move
    color: QColor
    width_factor: float = 0.22
    alpha: int = 230


class BoardWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.board = chess.Board()
        self.bottom_is_white = True
        self.last_move: Optional[chess.Move] = None
        self.arrows: list[Arrow] = []
        self._pix_cache: dict[tuple[str, int], QPixmap] = {}
        self._renderers: dict[str, QSvgRenderer] = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(240, 240)
        self.dimmed = False

    # ------------------------------------------------------------------
    def set_position(self, board: chess.Board, bottom_is_white: bool, last_move: Optional[chess.Move]) -> None:
        self.board = board.copy()
        self.bottom_is_white = bottom_is_white
        self.last_move = last_move
        self.update()

    def set_arrows(self, arrows: list[Arrow]) -> None:
        self.arrows = arrows
        self.update()

    def set_dimmed(self, dimmed: bool) -> None:
        self.dimmed = dimmed
        self.update()

    # ------------------------------------------------------------------
    def _geom(self) -> tuple[float, float, float]:
        w, h = self.width(), self.height()
        size = min(w, h)
        x0 = (w - size) / 2
        y0 = (h - size) / 2
        return x0, y0, size

    def _square_rect(self, sq: int, x0: float, y0: float, cell: float) -> QRectF:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        if self.bottom_is_white:
            col, row = f, 7 - r
        else:
            col, row = 7 - f, r
        return QRectF(x0 + col * cell, y0 + row * cell, cell, cell)

    def _piece_pixmap(self, piece: chess.Piece, size: int) -> QPixmap:
        key = (piece.symbol(), size)
        pm = self._pix_cache.get(key)
        if pm is not None:
            return pm
        r = self._renderers.get(piece.symbol())
        if r is None:
            svg = chess.svg.piece(piece, size=45)
            r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            self._renderers[piece.symbol()] = r
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p, QRectF(0, 0, size, size))
        p.end()
        self._pix_cache[key] = pm
        return pm

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x0, y0, size = self._geom()
        cell = size / 8.0
        # Rahmen/Schatten
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(QRectF(x0 - 6, y0 - 4, size + 12, size + 14), 10, 10)
        # Felder
        for sq in chess.SQUARES:
            rect = self._square_rect(sq, x0, y0, cell)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            p.setBrush(theme.BOARD_LIGHT if light else theme.BOARD_DARK)
            p.drawRect(rect)
        # Letzter Zug
        if self.last_move is not None:
            p.setBrush(theme.BOARD_LAST)
            p.drawRect(self._square_rect(self.last_move.from_square, x0, y0, cell))
            p.drawRect(self._square_rect(self.last_move.to_square, x0, y0, cell))
        # Schach
        if self.board.is_check():
            k = self.board.king(self.board.turn)
            if k is not None:
                p.setBrush(theme.BOARD_CHECK)
                p.drawRect(self._square_rect(k, x0, y0, cell))
        # Koordinaten
        coord_font = theme.font(max(8, int(cell * 0.17)), 700)
        p.setFont(coord_font)
        for i in range(8):
            # Linienbuchstaben unten
            f = i if self.bottom_is_white else 7 - i
            sq = chess.square(f, 0 if self.bottom_is_white else 7)
            rect = self._square_rect(sq, x0, y0, cell)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            p.setPen(theme.COORD_ON_LIGHT if light else theme.COORD_ON_DARK)
            p.drawText(rect.adjusted(0, 0, -cell * 0.08, -cell * 0.04), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, "abcdefgh"[f])
            # Reihen links
            r = 7 - i if self.bottom_is_white else i
            sq = chess.square(0 if self.bottom_is_white else 7, r)
            rect = self._square_rect(sq, x0, y0, cell)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            p.setPen(theme.COORD_ON_LIGHT if light else theme.COORD_ON_DARK)
            p.drawText(rect.adjusted(cell * 0.08, cell * 0.04, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(r + 1))
        # Figuren
        psize = int(cell * 0.92)
        off = (cell - psize) / 2
        for sq, piece in self.board.piece_map().items():
            rect = self._square_rect(sq, x0, y0, cell)
            p.drawPixmap(QPointF(rect.x() + off, rect.y() + off), self._piece_pixmap(piece, psize))
        # Pfeile
        for arrow in reversed(self.arrows):  # bester Pfeil zuletzt (oben)
            self._draw_arrow(p, arrow, x0, y0, cell)
        if self.dimmed:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(19, 25, 32, 120))
            p.drawRect(QRectF(x0, y0, size, size))
        p.end()

    def _draw_arrow(self, p: QPainter, arrow: Arrow, x0: float, y0: float, cell: float) -> None:
        a = self._square_rect(arrow.move.from_square, x0, y0, cell).center()
        b = self._square_rect(arrow.move.to_square, x0, y0, cell).center()
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        w = cell * arrow.width_factor
        head_len = cell * 0.42
        head_w = w * 2.3
        # Start etwas vom Feldmittelpunkt weg, damit die Figur sichtbar bleibt
        start = QPointF(a.x() + ux * cell * 0.25, a.y() + uy * cell * 0.25)
        end = QPointF(b.x() - ux * cell * 0.08, b.y() - uy * cell * 0.08)
        tip = end
        base = QPointF(tip.x() - ux * head_len, tip.y() - uy * head_len)
        nx, ny = -uy, ux
        path = QPainterPath()
        path.moveTo(start.x() + nx * w / 2, start.y() + ny * w / 2)
        path.lineTo(base.x() + nx * w / 2, base.y() + ny * w / 2)
        path.lineTo(base.x() + nx * head_w / 2, base.y() + ny * head_w / 2)
        path.lineTo(tip)
        path.lineTo(base.x() - nx * head_w / 2, base.y() - ny * head_w / 2)
        path.lineTo(base.x() - nx * w / 2, base.y() - ny * w / 2)
        path.lineTo(start.x() - nx * w / 2, start.y() - ny * w / 2)
        path.closeSubpath()
        col = QColor(arrow.color)
        col.setAlpha(arrow.alpha)
        p.setPen(QPen(QColor(0, 0, 0, 70), 1.5))
        p.setBrush(QBrush(col))
        p.drawPath(path)
