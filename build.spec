# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['bootstrap.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('.streamlit', '.streamlit'),
        ('app.py', '.'),
        ('engine.py', '.'),
        ('config.json', '.'),
        ('icon.ico', '.'),
    ],
    hiddenimports=[
        'ollama',
        'streamlit',
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
    ],
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
