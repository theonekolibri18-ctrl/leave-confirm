"""Bildschirmaufnahme über mss (schnell, mehrere Monitore)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class MonitorInfo:
    index: int  # mss-Index (1..n); 0 = alle Monitore zusammen
    left: int
    top: int
    width: int
    height: int

    def label(self) -> str:
        return f"Monitor {self.index} – {self.width}×{self.height} @ ({self.left},{self.top})"


class ScreenCapture:
    def __init__(self) -> None:
        self._sct = None

    def _ensure(self):
        if self._sct is None:
            import mss
            self._sct = mss.mss()
        return self._sct

    def monitors(self) -> list[MonitorInfo]:
        try:
            sct = self._ensure()
            out = []
            for i, m in enumerate(sct.monitors):
                if i == 0:
                    continue
                out.append(MonitorInfo(i, m["left"], m["top"], m["width"], m["height"]))
            return out
        except Exception as e:  # noqa: BLE001
            log.error("Monitore konnten nicht gelesen werden: %s", e)
            return []

    def grab(self, index: int) -> Optional[np.ndarray]:
        """BGR-Bild des Monitors oder None."""
        try:
            sct = self._ensure()
            if index < 1 or index >= len(sct.monitors):
                index = 1
            shot = sct.grab(sct.monitors[index])
            arr = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)
            return np.ascontiguousarray(arr[:, :, :3])
        except Exception as e:  # noqa: BLE001
            log.error("Screenshot fehlgeschlagen: %s", e)
            # mss-Instanz verwerfen (z.B. nach Monitorwechsel)
            self._sct = None
            return None
