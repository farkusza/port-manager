# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for port-manager.

Builds a single-file standalone `port-manager.exe` for Windows users without pip.
Zero-dep at the core, so the resulting binary is small (~10-15 MB) and fast to start.

Build:
    pip install pyinstaller
    pyinstaller ports.spec --clean --noconfirm

Output:
    dist/port-manager.exe
"""
from pathlib import Path

block_cipher = None

# Single-file binary, console subsystem (CLI, not GUI).
a = Analysis(
    ['src/port_manager/cli.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim the binary by skipping stdlib modules we don't touch.
        'tkinter',
        'test',
        'unittest',
        'pydoc',
        'doctest',
        'xml',
        'xmlrpc',
        'pdb',
        'lib2to3',
    ],
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
    name='port-manager',
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
)