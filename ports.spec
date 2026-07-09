# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ports-registry.

Builds a single-file standalone `ports.exe` for Windows users without pip.
Stdlib-only, so the resulting binary is small (~10-15 MB) and fast to start.

Build:
    pip install pyinstaller
    pyinstaller ports.spec --clean --noconfirm

Output:
    dist/ports.exe
"""
from pathlib import Path

block_cipher = None

# Single-file binary, console subsystem (CLI, not GUI).
# --onefile produces one .exe that contains the interpreter + stdlib + script.
# --console keeps stdout/stderr attached for a CLI.
a = Analysis(
    ['ports.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],   # stdlib only — nothing to hide
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim the binary by skipping stdlib modules we don't touch.
        # PyInstaller is conservative; this list is safe to grow.
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
    name='ports',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # UPX compresses the binary if installed; safe to leave on
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # CLI — keep console window attached
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Icon would go here; leaving None for the default Python icon.
    # icon='ports.ico',
)