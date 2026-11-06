"""Seitenleiste (Empfehlung, Erklärung, Alternativen) und obere Leiste."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from ..styles import STYLES, STYLE_INFO
from . import theme


class Dot(QWidget):
    def __init__(self, color: str, parent=None) -> None:
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(12, 12)

    def set_color(self, color: str) -> None:
        self.color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(1, 1, 10, 10)
        p.end()


class StatusChip(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 14, 6)
        lay.setSpacing(8)
        self.dot = Dot(theme.PAUSE)
        self.text = QLabel("Starte …")
        self.text.setFont(theme.font(15, 700))
        lay.addWidget(self.dot)
        lay.addWidget(self.text)
        self.setStyleSheet(f"QFrame {{ background: {theme.SURFACE_2}; border-radius: 12px; }}")

    def set_status(self, text: str, kind: str) -> None:
        color = {"ok": theme.ACCENT, "wait": theme.ALT3, "warn": theme.OPPONENT,
                 "search": theme.WARN, "pause": theme.PAUSE}.get(kind, theme.PAUSE)
        self.dot.set_color(color)
        self.text.setText(text)


class StyleSelector(QFrame):
    changed = Signal(str)

    def __init__(self, current: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("segments")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for key, label in STYLES.items():
            b = QPushButton(label)
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setToolTip(STYLE_INFO[key])
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(key == current)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b

    def set_current(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)


class TopBar(QFrame):
    pause_clicked = Signal()
    redetect_clicked = Signal()
    flip_turn_clicked = Signal()
    flip_board_clicked = Signal()
    settings_clicked = Signal()
    style_changed = Signal(str)

    def __init__(self, style: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("topbar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        self.status = StatusChip()
        lay.addWidget(self.status)
        lay.addStretch(1)
        self.styles = StyleSelector(style)
        self.styles.changed.connect(self.style_changed)
        lay.addWidget(self.styles)
        lay.addStretch(1)
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setToolTip("Erkennung anhalten/fortsetzen (F9, überall: Strg+Alt+P)")
        self.btn_redetect = QPushButton("Brett suchen")
        self.btn_redetect.setToolTip("Brett neu erkennen (F10, überall: Strg+Alt+B)")
        self.btn_turn = QPushButton("Zugrecht")
        self.btn_turn.setToolTip("Falls die Zugfarbe nach einem Neustart falsch geraten wurde (F11, überall: Strg+Alt+Z)")
        self.btn_flip = QPushButton("Drehen")
        self.btn_flip.setToolTip("Wenn Weiß/Schwarz vertauscht angezeigt wird (F12, überall: Strg+Alt+D)")
        self.btn_settings = QPushButton("Einstellungen")
        for b in (self.btn_pause, self.btn_redetect, self.btn_turn, self.btn_flip, self.btn_settings):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b)
        self.btn_pause.clicked.connect(self.pause_clicked)
        self.btn_redetect.clicked.connect(self.redetect_clicked)
        self.btn_turn.clicked.connect(self.flip_turn_clicked)
        self.btn_flip.clicked.connect(self.flip_board_clicked)
        self.btn_settings.clicked.connect(self.settings_clicked)

    def set_paused(self, paused: bool) -> None:
        self.btn_pause.setText("Fortsetzen" if paused else "Pause")


class AltRow(QFrame):
    def __init__(self, color: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("altrow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)
        self.dot = Dot(color)
        self.move = QLabel("–")
        self.move.setFont(theme.font(17, 700))
        self.move.setMinimumWidth(78)
        self.score = QLabel("")
        self.score.setFont(theme.font(14, 700))
        self.score.setMinimumWidth(56)
        self.pv = QLabel("")
        self.pv.setObjectName("muted")
        self.pv.setFont(theme.font(13, 500))
        self.pv.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.dot)
        lay.addWidget(self.move)
        lay.addWidget(self.score)
        lay.addWidget(self.pv, 1)

    def set(self, move: str, score: str, pv: str, good: bool = True) -> None:
        self.move.setText(move)
        self.score.setText(score)
        self.score.setStyleSheet(f"color: {theme.ACCENT if good else theme.MUTED};")
        self.pv.setText(pv)
        self.setVisible(bool(move))


class MovePanel(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setMinimumWidth(340)
        self.setMaximumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(6)

        self.kicker = QLabel("Dein bester Zug")
        self.kicker.setObjectName("section")
        self.headline = QLabel("…")
        self.headline.setObjectName("headline")
        self.headline.setFont(theme.font(44, 800))
        self.words = QLabel("Warte auf das Brett")
        self.words.setObjectName("words")
        self.words.setWordWrap(True)
        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        self.eval_chip = QLabel("")
        self.eval_chip.setObjectName("chip")
        self.style_chip = QLabel("")
        self.style_chip.setObjectName("chip")
        self.style_chip.setStyleSheet(f"QLabel#chip {{ background: {theme.ACCENT_DIM}; color: {theme.TEXT}; }}")
        self.style_chip.hide()
        chip_row.addWidget(self.eval_chip)
        chip_row.addWidget(self.style_chip)
        chip_row.addStretch(1)

        self.why_title = QLabel("Warum dieser Zug")
        self.why_title.setObjectName("section")
        self.bullets = QLabel("")
        self.bullets.setObjectName("bullet")
        self.bullets.setWordWrap(True)
        self.bullets.setTextFormat(Qt.TextFormat.RichText)
        self.bullets.setFont(theme.font(15, 500))

        self.alt_title = QLabel("Alternativen")
        self.alt_title.setObjectName("section")
        self.rows = [AltRow(theme.ACCENT), AltRow(theme.ALT2), AltRow(theme.ALT3)]

        self.hint = QLabel("")
        self.hint.setObjectName("faint")
        self.hint.setWordWrap(True)

        lay.addWidget(self.kicker)
        lay.addWidget(self.headline)
        lay.addWidget(self.words)
        lay.addLayout(chip_row)
        lay.addSpacing(10)
        lay.addWidget(self.why_title)
        lay.addWidget(self.bullets)
        lay.addSpacing(10)
        lay.addWidget(self.alt_title)
        for r in self.rows:
            lay.addWidget(r)
        lay.addStretch(1)
        lay.addWidget(self.hint)

    # ------------------------------------------------------------------
    def show_waiting(self, text: str, sub: str = "") -> None:
        self.kicker.setText("Status")
        self.headline.setText(text)
        self.headline.setFont(theme.font(26, 800))
        self.words.setText(sub)
        self.eval_chip.setText("")
        self.eval_chip.hide()
        self.style_chip.hide()
        self.why_title.hide()
        self.bullets.setText("")
        self.alt_title.hide()
        for r in self.rows:
            r.hide()

    def show_analysis(self, kicker: str, move: str, words: str, eval_text: str, style_tag: str,
                      bullets: list[str], alts: list[tuple[str, str, str, bool]], hint: str = "",
                      accent: str = theme.ACCENT) -> None:
        self.kicker.setText(kicker)
        self.headline.setText(move)
        self.headline.setFont(theme.font(44, 800))
        self.headline.setStyleSheet(f"color: {accent};")
        self.words.setText(words)
        self.eval_chip.setText(eval_text)
        self.eval_chip.setVisible(bool(eval_text))
        self.style_chip.setText(style_tag)
        self.style_chip.setVisible(bool(style_tag))
        self.why_title.setVisible(bool(bullets))
        self.bullets.setText("".join(f"<div style='margin-bottom:6px'>•&nbsp; {b}</div>" for b in bullets))
        self.alt_title.setVisible(bool(alts))
        for i, r in enumerate(self.rows):
            if i < len(alts):
                r.set(*alts[i])
            else:
                r.hide()
        self.hint.setText(hint)
