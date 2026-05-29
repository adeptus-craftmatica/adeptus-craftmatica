# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — Adeptus Craftmatica (macOS)
#
# Build:
#   pyinstaller Adeptus_Craftmatica.spec
#
# Or use the convenience script:
#   ./build_macos.sh

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

# ── Plugins to exclude from the release build ────────────────────────────────
EXCLUDE_PLUGINS = {'dev_tools', '__pycache__'}

# ── Collect every plugin except the excluded ones ────────────────────────────
all_datas     = []
all_binaries  = []
all_hidden    = []

plugins_root = Path('plugins')
for entry in sorted(plugins_root.iterdir()):
    if not entry.is_dir() or entry.name in EXCLUDE_PLUGINS:
        continue

    # Explicitly copy the entire plugin folder into the bundle as data.
    # This guarantees the filesystem structure (plugins/<name>/) exists at
    # runtime so the plugin manager's directory scan works correctly.
    all_datas.append((str(entry), f'plugins/{entry.name}'))

    # Also collect compiled modules and hidden imports via collect_all
    pkg = f'plugins.{entry.name}'
    try:
        d, b, h = collect_all(pkg)
        all_datas    += d
        all_binaries += b
        all_hidden   += h
        print(f'  [spec] collected plugin: {entry.name}')
    except Exception as e:
        print(f'  [spec] WARNING — could not collect {pkg}: {e}')

# ── Collect core and ui packages ─────────────────────────────────────────────
for pkg in ('core', 'ui'):
    all_datas.append((pkg, pkg))   # preserve directory on disk
    d, b, h = collect_all(pkg)
    all_datas    += d
    all_binaries += b
    all_hidden   += h

# ── Static data directories and files ────────────────────────────────────────
static_assets = [
    ('themes',           'themes'),
    ('game_system_data', 'game_system_data'),
    ('paints.csv',       '.'),
]
# Include assets/ only if it contains files
assets_dir = Path('assets')
if assets_dir.exists() and any(assets_dir.iterdir()):
    static_assets.append(('assets', 'assets'))

all_datas += [(src, dst) for src, dst in static_assets if Path(src).exists()]

# ── Extra hidden imports ──────────────────────────────────────────────────────
all_hidden += [
    # Timezone data used by calendar settings
    'zoneinfo',
    'zoneinfo._tzpath',
    'zoneinfo._common',
    # Standard library modules PyInstaller sometimes misses
    'sqlite3',
    'json',
    'pathlib',
    'logging',
    'importlib',
    'importlib.util',
]

# ── Icon — .icns on macOS, .ico on Windows ───────────────────────────────────
if sys.platform == 'win32':
    ICON = 'assets/icon.ico'  if Path('assets/icon.ico').exists()  else None
else:
    ICON = 'assets/icon.icns' if Path('assets/icon.icns').exists() else None

# ─────────────────────────────────────────────────────────────────────────────

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/runtime_hook_craftmatica.py'],
    excludes=['dev_tools'],
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
    name='Adeptus Craftmatica',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can cause issues with Qt on macOS
    console=False,      # No terminal window
    disable_windowed_traceback=False,
    target_arch=None,   # None = build for current arch (arm64 on Apple Silicon)
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Adeptus Craftmatica',
)

# BUNDLE is macOS-only — skip on Windows
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Adeptus Craftmatica.app',
        icon=ICON,
        bundle_identifier='com.adeptus.craftmatica',
        info_plist={
            'CFBundleDisplayName':        'Adeptus Craftmatica',
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleVersion': '0.1.0',
            'NSPrincipalClass':           'NSApplication',
            'NSHighResolutionCapable':    True,
            'NSAppleScriptEnabled':       False,
            'LSMinimumSystemVersion':     '11.0',
        },
    )
