# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('templates', 'templates'), ('calibrated_coords.json', '.')],
    hiddenimports=['tkinter', 'tkinter.ttk', 'cv2', 'numpy', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'selenium', 'selenium.webdriver.chrome.service', 'selenium.webdriver.chrome.options', 'webdriver_manager', 'webdriver_manager.chrome', 'webdriver_manager.core.os_manager', 'urllib3', 'requests', 'certifi'],
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
    name='AutoScreenshot.exe',
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
# BUNDLE() 是 macOS 专用指令，Windows 构建时删除此行
# app = BUNDLE(
#     exe,
#     name='AutoScreenshot.app',
#     icon=None,
#     bundle_identifier=None,
# )
