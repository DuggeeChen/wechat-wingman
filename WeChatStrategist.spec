# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Administrator.DESKTOP-FMFEI6G/Documents/Codex/2026-10-05/zhuo/work/github-v26/wx_helper.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/Administrator.DESKTOP-FMFEI6G/Documents/Codex/2026-10-05/zhuo/work/github-v26/assets', 'assets'), ('C:/Users/Administrator.DESKTOP-FMFEI6G/Documents/Codex/2026-10-05/zhuo/work/github-v26/config.example.json', '.'), ('C:/Users/Administrator.DESKTOP-FMFEI6G/Documents/Codex/2026-10-05/zhuo/work/github-v26/LICENSE', '.'), ('C:/Users/Administrator.DESKTOP-FMFEI6G/Documents/Codex/2026-10-05/zhuo/work/github-v26/README.zh-CN.md', '.')],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='WeChatStrategist',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/Administrator.DESKTOP-FMFEI6G/Documents/Codex/2026-10-05/zhuo/work/github-v26/assets/wingman.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WeChatStrategist',
)
