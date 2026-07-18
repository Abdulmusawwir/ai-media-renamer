# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

block_cipher = None

# Collect ALL Streamlit submodules — manual listing misses dynamic imports like magic_funcs
_streamlit_submodules = collect_submodules('streamlit')

# Collect frontend assets for Streamlit component packages
_autorefresh_data = collect_data_files('streamlit_autorefresh')

# Locate Streamlit's static assets (index.html, JS bundles, CSS, etc.)
_streamlit_static = os.path.join(
    os.path.dirname(__import__("streamlit").__file__), "static"
)

a = Analysis(
    ['bootstrap.py'],
    pathex=[],
    binaries=[],
    datas=copy_metadata('streamlit') + [
        (_streamlit_static, os.path.join("streamlit", "static")),
        ('.streamlit', '.streamlit'),
        ('app.py', '.'),
        ('engine.py', '.'),
        ('config.json', '.'),
        ('icon.ico', '.'),
    ] + _autorefresh_data,
    hiddenimports=[
        'ollama',
        'PIL',
        'PIL._tkinter_finder',
        'tkinter',
        'webview',
        'pywebview',
        'requests',
        'pandas',
        'plotly',
        'openai',
        'anthropic',
        'keyring',
        'streamlit_autorefresh',
    ] + _streamlit_submodules,
    hookspath=['hooks'],
    runtime_hooks=[],
    excludes=[],
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
    name='AIMediaRenamer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
