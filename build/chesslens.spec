# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für ChessLens (Windows, onedir).

    pyinstaller build/chesslens.spec --noconfirm
"""

import os

root = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(root, "chesslens", "assets"), os.path.join("chesslens", "assets")),
]
sf_dir = os.path.join(root, "stockfish")
if os.path.isdir(sf_dir):
    datas.append((sf_dir, "stockfish"))

a = Analysis(
    [os.path.join(root, "run_chesslens.py")],
    pathex=[root],
    binaries=[],
    datas=datas,
    hiddenimports=["PySide6.QtSvg", "chess.engine", "chess.svg", "mss", "mss.windows", "keyboard"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "scipy", "pandas", "IPython", "jupyter", "PIL.ImageQt",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQuickWidgets",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
        "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
        "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtWebSockets", "PySide6.QtWebChannel",
        "PySide6.QtHttpServer", "PySide6.QtNetworkAuth", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
        "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSpatialAudio", "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
        "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtPrintSupport", "PySide6.QtConcurrent", "PySide6.QtDBus",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChessLens",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(root, "chesslens", "assets", "icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ChessLens",
)
