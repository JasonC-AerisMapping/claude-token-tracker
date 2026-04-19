# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=(
        [('prompt_ledger/ui', 'prompt_ledger/ui')]
        + collect_data_files('tzdata')
    ),
    hiddenimports=(
        collect_submodules('webview')
        + collect_submodules('clr_loader')
        + ['clr', 'pythonnet', 'tzdata']
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PromptLedger',
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
)
