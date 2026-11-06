"""Einstellungen (JSON in %APPDATA%/ChessLens bzw. ~/.config/chesslens)."""

from __future__ import annotations

import json
import logging
import os
import platform
from dataclasses import asdict, dataclass, field, fields

log = logging.getLogger(__name__)


def data_dir() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "ChessLens")
    else:
        d = os.path.join(os.path.expanduser("~"), ".config", "chesslens")
    os.makedirs(d, exist_ok=True)
    return d


def profiles_dir() -> str:
    d = os.path.join(data_dir(), "profiles")
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class Settings:
    capture_monitor: int = 1  # mss-Index (1 = Hauptmonitor)
    display_monitor: int = -1  # Qt-Screen-Index, -1 = automatisch (anderer Monitor als capture)
    engine_seconds: float = 2.5
    engine_threads: int = 0  # 0 = automatisch
    engine_hash_mb: int = 256
    style: str = "engine"
    risk_cp: int = 60
    show_alternatives: bool = True
    sound: bool = True
    scan_interval: float = 0.25
    auto_mode: bool = True
    manual_rect: list[float] = field(default_factory=list)  # [x, y, size] auf dem Capture-Monitor, leer = automatisch
    bottom_is_white: bool = True
    window_geometry: list[int] = field(default_factory=list)
    hotkeys: bool = True
    active_profile: str = ""

    @staticmethod
    def path() -> str:
        return os.path.join(data_dir(), "settings.json")

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            with open(cls.path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            names = {f.name for f in fields(cls)}
            for k, v in data.items():
                if k in names:
                    setattr(s, k, v)
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001
            log.warning("Einstellungen konnten nicht gelesen werden: %s", e)
        return s

    def save(self) -> None:
        try:
            with open(self.path(), "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            log.warning("Einstellungen konnten nicht gespeichert werden: %s", e)
