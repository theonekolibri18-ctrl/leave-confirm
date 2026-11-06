"""Einstellungen: Monitore, Engine, Spielstil-Risiko, Ton, Profile."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
                               QPushButton, QSlider, QSpinBox, QVBoxLayout)

from ..capture import MonitorInfo
from ..settings import Settings


class SettingsDialog(QDialog):
    calibrate_requested = Signal()
    profile_deleted = Signal(str)
    profile_selected = Signal(str)

    def __init__(self, settings: Settings, monitors: list[MonitorInfo], profile_names: list[str],
                 active_profile: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumWidth(520)
        self.settings = settings
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        # --- Monitore ---------------------------------------------------------
        g1 = QGroupBox("Monitore")
        f1 = QFormLayout(g1)
        self.cb_capture = QComboBox()
        for m in monitors:
            self.cb_capture.addItem(m.label(), m.index)
        idx = self.cb_capture.findData(settings.capture_monitor)
        self.cb_capture.setCurrentIndex(max(0, idx))
        self.cb_display = QComboBox()
        self.cb_display.addItem("Automatisch (der andere Monitor)", -1)
        for i, s in enumerate(QGuiApplication.screens()):
            g = s.geometry()
            self.cb_display.addItem(f"Bildschirm {i + 1} – {g.width()}×{g.height()} @ ({g.x()},{g.y()})", i)
        idx = self.cb_display.findData(settings.display_monitor)
        self.cb_display.setCurrentIndex(max(0, idx))
        f1.addRow("Schach läuft auf", self.cb_capture)
        f1.addRow("ChessLens anzeigen auf", self.cb_display)
        self.btn_calib = QPushButton("Brett von Hand festlegen …")
        self.btn_calib.clicked.connect(self.calibrate_requested)
        self.lbl_calib = QLabel("Brett wird automatisch gesucht" if not settings.manual_rect else "Brett ist von Hand festgelegt")
        self.lbl_calib.setObjectName("muted")
        row = QHBoxLayout()
        row.addWidget(self.btn_calib)
        row.addWidget(self.lbl_calib, 1)
        f1.addRow("Erkennung", row)
        lay.addWidget(g1)

        # --- Engine ---------------------------------------------------------
        g2 = QGroupBox("Engine")
        f2 = QFormLayout(g2)
        self.sl_time = QSlider(Qt.Orientation.Horizontal)
        self.sl_time.setRange(3, 100)  # Zehntelsekunden
        self.sl_time.setValue(int(settings.engine_seconds * 10))
        self.lbl_time = QLabel()
        self.sl_time.valueChanged.connect(lambda v: self.lbl_time.setText(f"{v / 10:.1f} s pro Stellung"))
        self.lbl_time.setText(f"{self.sl_time.value() / 10:.1f} s pro Stellung")
        r2 = QHBoxLayout()
        r2.addWidget(self.sl_time, 1)
        r2.addWidget(self.lbl_time)
        f2.addRow("Rechenzeit", r2)
        self.sp_threads = QSpinBox()
        self.sp_threads.setRange(0, max(1, os.cpu_count() or 4))
        self.sp_threads.setValue(settings.engine_threads)
        self.sp_threads.setSpecialValueText("Automatisch")
        f2.addRow("CPU-Kerne", self.sp_threads)
        self.sl_risk = QSlider(Qt.Orientation.Horizontal)
        self.sl_risk.setRange(10, 200)
        self.sl_risk.setValue(settings.risk_cp)
        self.lbl_risk = QLabel()
        self.sl_risk.valueChanged.connect(lambda v: self.lbl_risk.setText(f"bis {v / 100:.2f} Bauern schlechter"))
        self.lbl_risk.setText(f"bis {self.sl_risk.value() / 100:.2f} Bauern schlechter")
        r3 = QHBoxLayout()
        r3.addWidget(self.sl_risk, 1)
        r3.addWidget(self.lbl_risk)
        f2.addRow("Spielstil darf", r3)
        lay.addWidget(g2)

        # --- Anzeige ----------------------------------------------------------
        g3 = QGroupBox("Anzeige")
        v3 = QVBoxLayout(g3)
        self.ck_alts = QCheckBox("Zweit- und drittbesten Zug als dünne Pfeile zeigen")
        self.ck_alts.setChecked(settings.show_alternatives)
        self.ck_sound = QCheckBox("Ton, wenn ein neuer Vorschlag da ist")
        self.ck_sound.setChecked(settings.sound)
        self.ck_hotkeys = QCheckBox("Globale Tastenkürzel (F9 Pause, F10 Brett suchen, F11 Zugrecht, F12 drehen)")
        self.ck_hotkeys.setChecked(settings.hotkeys)
        v3.addWidget(self.ck_alts)
        v3.addWidget(self.ck_sound)
        v3.addWidget(self.ck_hotkeys)
        lay.addWidget(g3)

        # --- Profile ----------------------------------------------------------
        g4 = QGroupBox("Erkennungsprofile (werden aus der Grundstellung automatisch gelernt)")
        v4 = QVBoxLayout(g4)
        self.lst = QListWidget()
        for n in profile_names:
            self.lst.addItem(n + ("   ← aktiv" if n == active_profile else ""))
        self.lst.setMaximumHeight(120)
        v4.addWidget(self.lst)
        r4 = QHBoxLayout()
        self.btn_use = QPushButton("Profil verwenden")
        self.btn_del = QPushButton("Profil löschen")
        r4.addWidget(self.btn_use)
        r4.addWidget(self.btn_del)
        r4.addStretch(1)
        v4.addLayout(r4)
        self.btn_use.clicked.connect(self._use)
        self.btn_del.clicked.connect(self._delete)
        lay.addWidget(g4)

        # --- Buttons ----------------------------------------------------------
        rb = QHBoxLayout()
        rb.addStretch(1)
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_ok = QPushButton("Speichern")
        self.btn_ok.setObjectName("primary")
        rb.addWidget(self.btn_cancel)
        rb.addWidget(self.btn_ok)
        lay.addLayout(rb)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)

    def _selected_name(self) -> str:
        it = self.lst.currentItem()
        return it.text().split("   ←")[0] if it else ""

    def _use(self) -> None:
        n = self._selected_name()
        if n:
            self.profile_selected.emit(n)

    def _delete(self) -> None:
        n = self._selected_name()
        if n:
            self.profile_deleted.emit(n)
            self.lst.takeItem(self.lst.currentRow())

    def apply(self) -> None:
        s = self.settings
        s.capture_monitor = int(self.cb_capture.currentData() or 1)
        s.display_monitor = int(self.cb_display.currentData())
        s.engine_seconds = self.sl_time.value() / 10
        s.engine_threads = self.sp_threads.value()
        s.risk_cp = self.sl_risk.value()
        s.show_alternatives = self.ck_alts.isChecked()
        s.sound = self.ck_sound.isChecked()
        s.hotkeys = self.ck_hotkeys.isChecked()
