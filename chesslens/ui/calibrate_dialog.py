"""Brett von Hand festlegen: Rechteck über den Screenshot ziehen."""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme


def np_to_qimage(img: np.ndarray) -> QImage:
    h, w = img.shape[:2]
    rgb = np.ascontiguousarray(img[:, :, ::-1])
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class RubberBand(QWidget):
    def __init__(self, pix: QPixmap, parent=None) -> None:
        super().__init__(parent)
        self.pix = pix
        self.start: Optional[QPoint] = None
        self.end: Optional[QPoint] = None
        self.setFixedSize(pix.size())
        self.setCursor(Qt.CursorShape.CrossCursor)

    def rect(self) -> Optional[QRect]:
        if self.start is None or self.end is None:
            return None
        r = QRect(self.start, self.end).normalized()
        s = max(r.width(), r.height())
        return QRect(r.x(), r.y(), s, s)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self.start = e.position().toPoint()
        self.end = self.start
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self.start is not None:
            self.end = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self.end = e.position().toPoint()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(0, 0, self.pix)
        r = self.rect()
        if r is not None:
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.setBrush(QColor(47, 210, 139, 40))
            p.drawRect(r)
            cell = r.width() / 8
            p.setPen(QPen(QColor(47, 210, 139, 150), 1))
            for i in range(1, 8):
                p.drawLine(int(r.x() + i * cell), r.y(), int(r.x() + i * cell), r.bottom())
                p.drawLine(r.x(), int(r.y() + i * cell), r.right(), int(r.y() + i * cell))
        p.end()


class CalibrateDialog(QDialog):
    def __init__(self, frame: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Brett von Hand festlegen")
        self.result_rect: Optional[list[float]] = None
        H, W = frame.shape[:2]
        qi = np_to_qimage(frame)
        maxw, maxh = 1500, 850
        self.scale = min(1.0, maxw / W, maxh / H)
        pix = QPixmap.fromImage(qi).scaled(int(W * self.scale), int(H * self.scale), Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
        lay = QVBoxLayout(self)
        info = QLabel("Zieh mit der Maus ein Quadrat genau über die 64 Felder (ohne Rahmen und Koordinaten). "
                      "Das Raster zeigt dir, ob es passt.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.band = RubberBand(pix)
        lay.addWidget(self.band)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_auto = QPushButton("Wieder automatisch erkennen")
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_ok = QPushButton("Übernehmen")
        self.btn_ok.setObjectName("primary")
        row.addWidget(self.btn_auto)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept)
        self.btn_auto.clicked.connect(self._auto)
        self.use_auto = False

    def _accept(self) -> None:
        r = self.band.rect()
        if r is None or r.width() < 40:
            return
        self.result_rect = [r.x() / self.scale, r.y() / self.scale, r.width() / self.scale]
        self.accept()

    def _auto(self) -> None:
        self.use_auto = True
        self.accept()
