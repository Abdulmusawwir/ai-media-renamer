# -*- mode: python ; coding: utf-8 -*-
# v2 build spec: bundles the FastAPI backend + built React frontend (frontend/dist)
# into a single standalone Windows executable (AIMediaRenamer.exe).

import os
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

block_cipher = None

ROOT = Path(os.path.abspath(SPECPATH))

# The frontend must be built first (`npm run build` in frontend/), producing
# frontend/dist. Bundle it so the server can serve the SPA at "/".
datas = [
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "config.json"), "."),
    (str(ROOT / "config.default.json"), "."),
    (str(ROOT / "icon.ico"), "."),
]

# Heavy, optional media libraries are lazy-imported inside engine.py only when a
# matching asset is actually analyzed. Excluding them keeps the test build lean;
# they can be added back for a full release build.
excludes = [
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "av",
    "pdfplumber",
    "pdfminer",
    "pdfminer.six",
    "docx",
    "openpyxl",
    "pptx",
    "imagehash",
    "huggingface_hub",
    "pandas",
    "plotly",
    "tkinter",
    "pywebview",
    "webview",
    "streamlit",
    "torch",
    "rich",
    "pyarrow",
    "tokenizers",
]

a = Analysis(
    [str(ROOT / "launch.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "engine",
        "server",
        "server.main",
        "server.routes",
        "server.routes.analysis",
        "server.routes.assets",
        "server.routes.browse",
        "server.routes.commit",
        "server.routes.config",
        "server.routes.environment",
        "server.routes.models",
        "server.routes.sessions",
        "server.routes.staging",
        "server.routes.updates",
        "server.ws",
        "server.security",
        "server.schemas",
        "server.deps",
        "server.auth",
        "fastapi",
        "starlette",
        "uvicorn",
        "jwt",
        "pydantic",
        "openai",
        "requests",
        "numpy",
        "PIL",
        "PIL.Image",
        "multipart",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AIMediaRenamer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "icon.ico"),
)
