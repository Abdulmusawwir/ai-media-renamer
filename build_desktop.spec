# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the AI Media Renamer desktop backend (onedir)."""

import os

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hidden_imports = [
    "engine",
    "bootstrap",
    "desktop_backend",
    "server",
    "server.main",
    "server.desktop",
    "server.deps",
    "server.auth",
    "server.ws",
] + collect_submodules("server.routes") + [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "starlette.routing",
    "starlette.middleware",
    "starlette.staticfiles",
    "pydantic",
    "jwt",
    "openai",
    "requests",
    "numpy",
    "PIL",
    "multipart",
    "tkinter",
    "imagehash",
    "scipy",
    "faster_whisper",
    "ctranslate2",
    "av",
    "pdfplumber",
    "docx",
    "openpyxl",
    "pptx",
    "huggingface_hub",
    "tokenizers",
]

excludes = [
    "pandas",
    "plotly",
    "torch",
    "streamlit",
    "pywebview",
    "rich",
    "pyarrow",
    "pytest",
    "tests",
]

a = Analysis(
    ["desktop_backend.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=[
        ("frontend/dist", "frontend/dist"),
        ("config.default.json", "."),
        ("icon.ico", "."),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
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
    [],
    exclude_binaries=True,
    name="AIMediaRenamerBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AIMediaRenamerBackend",
)
