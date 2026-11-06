"""Kurzer Hinweiston bei neuem Vorschlag (Windows: winsound, sonst stumm)."""

from __future__ import annotations

import logging
import os
import platform
import sys

log = logging.getLogger(__name__)


def _asset_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "chesslens", "assets")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def sound_path() -> str:
    return os.path.join(_asset_dir(), "sounds", "ding.wav")


def play_ding() -> None:
    path = sound_path()
    if not os.path.isfile(path):
        return
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception as e:  # noqa: BLE001
        log.debug("Ton konnte nicht abgespielt werden: %s", e)


def generate_wav(path: str) -> None:
    """Erzeugt einen weichen Zwei-Ton-Klang (wird einmalig beim Build aufgerufen)."""
    import struct
    import wave

    import numpy as np

    sr = 44100
    t1 = np.linspace(0, 0.09, int(sr * 0.09), False)
    t2 = np.linspace(0, 0.16, int(sr * 0.16), False)
    a = np.sin(2 * np.pi * 880 * t1) * np.exp(-t1 * 18)
    b = np.sin(2 * np.pi * 1318.5 * t2) * np.exp(-t2 * 12)
    sig = np.concatenate([a, b]) * 0.35
    data = (sig * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack("<" + "h" * len(data), *data))
