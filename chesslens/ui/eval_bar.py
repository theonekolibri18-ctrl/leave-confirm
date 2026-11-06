"""Vertikaler Bewertungsbalken (weißer Anteil = Vorteil Weiß), weich animiert."""

from __future__ import annotations

import math

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from . import theme


def win_fraction(cp_white: float) -> float:
    """cp aus Sicht von Weiß -> Anteil 0..1 (lichess-Formel)."""
    cp = max(-2000, min(2000, cp_white))
    return 1.0 / (1.0 + math.exp(-0.00368208 * cp))


class EvalBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._frac = 0.5
        self._target = 0.5
        self.white_bottom = True
        self.label = "0.0"
        self.setFixedWidth(30)
        self._anim = QPropertyAnimation(self, b"frac", self)
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def get_frac(self) -> float:
        return self._frac

    def set_frac(self, v: float) -> None:
        self._frac = v
        self.update()

    frac = Property(float, get_frac, set_frac)

    def set_eval(self, cp_white: float, mate_white: int | None, white_bottom: bool) -> None:
        self.white_bottom = white_bottom
        if mate_white is not None:
            target = 1.0 if mate_white > 0 else 0.0
            self.label = f"M{abs(mate_white)}"
        else:
            target = win_fraction(cp_white)
            self.label = f"{abs(cp_white) / 100:.1f}"
        self._anim.stop()
        self._anim.setStartValue(self._frac)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = QRectF(0, 0, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2A2A2A"))
        p.drawRoundedRect(r, 7, 7)
        white_h = h * self._frac
        p.setBrush(QColor("#F3F3F3"))
        if self.white_bottom:
            p.drawRoundedRect(QRectF(0, h - white_h, w, white_h), 7, 7)
            p.drawRect(QRectF(0, h - white_h, w, min(7, white_h)))
        else:
            p.drawRoundedRect(QRectF(0, 0, w, white_h), 7, 7)
            p.drawRect(QRectF(0, max(0, white_h - 7), w, min(7, white_h)))
        # Beschriftung im größeren Teil
        p.setFont(theme.font(10, 700))
        white_big = self._frac >= 0.5
        if white_big:
            p.setPen(QColor("#222"))
            rect = QRectF(0, h - white_h, w, white_h) if self.white_bottom else QRectF(0, 0, w, white_h)
            align = Qt.AlignmentFlag.AlignHCenter | (Qt.AlignmentFlag.AlignBottom if self.white_bottom else Qt.AlignmentFlag.AlignTop)
        else:
            p.setPen(QColor("#DDD"))
            rect = QRectF(0, 0, w, h - white_h) if self.white_bottom else QRectF(0, white_h, w, h - white_h)
            align = Qt.AlignmentFlag.AlignHCenter | (Qt.AlignmentFlag.AlignTop if self.white_bottom else Qt.AlignmentFlag.AlignBottom)
        p.drawText(rect.adjusted(0, 4, 0, -4), align, self.label)
        p.end()
