"""Farben, Schrift und Stylesheet. Dunkle, ruhige Oberfläche – das Brett ist der Star."""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QColor, QFont, QFontDatabase

BG = "#131920"
SURFACE = "#1A222C"
SURFACE_2 = "#222D39"
LINE = "#2C3846"
TEXT = "#E9EEF3"
MUTED = "#92A0B0"
FAINT = "#5C6B7B"

ACCENT = "#2FD28B"       # bester Zug / Nutzer am Zug
ACCENT_DIM = "#1D8F60"
ALT2 = "#F2B541"         # zweitbester Zug
ALT3 = "#7EA6D9"         # drittbester Zug
OPPONENT = "#F0705E"     # Zug des Gegners / Gefahr
WARN = "#F2B541"
PAUSE = "#92A0B0"

BOARD_LIGHT = QColor("#E4D4AF")
BOARD_DARK = QColor("#9C7956")
BOARD_LAST = QColor(242, 181, 65, 115)
BOARD_CHECK = QColor(240, 112, 94, 170)
COORD_ON_LIGHT = QColor("#8C6B47")
COORD_ON_DARK = QColor("#E9DCC0")

FONT_FAMILY = "Manrope"


def _asset_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "chesslens", "assets")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def load_fonts() -> str:
    """Lädt Manrope; fällt auf Segoe UI / Systemschrift zurück."""
    global FONT_FAMILY
    path = os.path.join(_asset_dir(), "fonts", "Manrope-Variable.ttf")
    fid = QFontDatabase.addApplicationFont(path) if os.path.isfile(path) else -1
    fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    if fams:
        FONT_FAMILY = fams[0]
    else:
        FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "Sans Serif"
    return FONT_FAMILY


def font(size: int, weight: int = QFont.Weight.Normal) -> QFont:
    f = QFont(FONT_FAMILY, size)
    f.setWeight(QFont.Weight(weight))
    return f


def stylesheet() -> str:
    return f"""
    QWidget {{ background: {BG}; color: {TEXT}; font-family: "{FONT_FAMILY}"; font-size: 14px; }}
    QMainWindow, QDialog {{ background: {BG}; }}
    QLabel {{ background: transparent; }}
    QLabel#muted {{ color: {MUTED}; }}
    QLabel#faint {{ color: {FAINT}; font-size: 12px; }}
    QLabel#headline {{ font-size: 44px; font-weight: 800; letter-spacing: -1px; }}
    QLabel#words {{ font-size: 17px; color: {MUTED}; }}
    QLabel#section {{ font-size: 13px; font-weight: 700; color: {MUTED}; margin-top: 6px; }}
    QLabel#bullet {{ font-size: 15px; line-height: 1.4; }}
    QLabel#chip {{ padding: 4px 10px; border-radius: 10px; background: {SURFACE_2}; color: {TEXT}; font-weight: 600; }}
    QFrame#panel {{ background: {SURFACE}; border-radius: 14px; }}
    QFrame#topbar {{ background: {SURFACE}; border-radius: 14px; }}
    QFrame#altrow {{ background: transparent; border-radius: 8px; }}
    QFrame#altrow:hover {{ background: {SURFACE_2}; }}
    QPushButton {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 9px; padding: 7px 12px; font-weight: 600; }}
    QPushButton:hover {{ border-color: {MUTED}; }}
    QPushButton:pressed {{ background: {LINE}; }}
    QPushButton#primary {{ background: {ACCENT}; color: #0D1A14; border: none; }}
    QPushButton#primary:hover {{ background: #45E39E; }}
    QPushButton#segment {{ background: transparent; border: none; border-radius: 8px; padding: 6px 12px; color: {MUTED}; }}
    QPushButton#segment:checked {{ background: {SURFACE_2}; color: {TEXT}; }}
    QPushButton#segment:hover {{ color: {TEXT}; }}
    QFrame#segments {{ background: {BG}; border-radius: 10px; }}
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 10px; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {SURFACE_2}; selection-background-color: {LINE}; border: 1px solid {LINE}; }}
    QSlider::groove:horizontal {{ height: 6px; background: {LINE}; border-radius: 3px; }}
    QSlider::handle:horizontal {{ width: 18px; height: 18px; margin: -6px 0; border-radius: 9px; background: {TEXT}; }}
    QSlider::sub-page:horizontal {{ background: {ACCENT_DIM}; border-radius: 3px; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {MUTED}; background: {SURFACE_2}; }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
    QListWidget {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 8px; }}
    QListWidget::item:selected {{ background: {LINE}; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QStatusBar {{ color: {FAINT}; font-size: 12px; }}
    QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {LINE}; padding: 6px; }}
    QGroupBox {{ border: 1px solid {LINE}; border-radius: 10px; margin-top: 14px; padding: 10px; font-weight: 700; color: {MUTED}; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
    """
