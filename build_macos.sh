#!/usr/bin/env bash
# build_macos.sh — Build a macOS release of Adeptus Craftmatica
#
# Usage:
#   ./build_macos.sh              # build app + DMG
#   ./build_macos.sh --app-only   # build .app only, skip DMG
#
# Requirements:
#   pip install -r build_requirements.txt
#   (Optional, for nicer DMG): brew install create-dmg

set -euo pipefail

APP_NAME="Adeptus Craftmatica"
DMG_NAME="Adeptus_Craftmatica.dmg"
SPEC_FILE="Adeptus_Craftmatica.spec"
APP_ONLY=false

for arg in "$@"; do
  [[ "$arg" == "--app-only" ]] && APP_ONLY=true
done

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Adeptus Craftmatica — macOS Build      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Sanity checks ─────────────────────────────────────────────────────────────
if ! command -v pyinstaller &>/dev/null; then
    echo "❌  PyInstaller not found."
    echo "    Run: pip install -r build_requirements.txt"
    exit 1
fi

# ── Clean previous build ──────────────────────────────────────────────────────
echo "→  Cleaning previous build artefacts…"
rm -rf build dist

# ── Build .app bundle ─────────────────────────────────────────────────────────
echo "→  Running PyInstaller…"
pyinstaller "$SPEC_FILE" --noconfirm

APP_PATH="dist/${APP_NAME}.app"

if [[ ! -d "$APP_PATH" ]]; then
    echo "❌  Build failed — ${APP_PATH} not found."
    exit 1
fi

echo "✅  App bundle created: ${APP_PATH}"

if $APP_ONLY; then
    echo ""
    echo "Done (--app-only). Output: ${APP_PATH}"
    exit 0
fi

# ── Create DMG ────────────────────────────────────────────────────────────────
echo "→  Creating DMG…"

if command -v create-dmg &>/dev/null; then
    # Polished DMG with drag-to-Applications layout
    create-dmg \
        --volname "$APP_NAME" \
        --volicon "assets/icon.icns" \
        --window-pos 200 140 \
        --window-size 660 400 \
        --icon-size 120 \
        --icon "${APP_NAME}.app" 180 170 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 480 170 \
        --no-internet-enable \
        "dist/${DMG_NAME}" \
        "$APP_PATH" || {
            # create-dmg exits non-zero if no code signature; fall through to hdiutil
            echo "  (create-dmg warning — falling back to hdiutil)"
            _use_hdiutil=true
        }
else
    _use_hdiutil=true
fi

if [[ "${_use_hdiutil:-false}" == "true" ]]; then
    # Built-in macOS DMG creation
    hdiutil create \
        -volname "$APP_NAME" \
        -srcfolder "$APP_PATH" \
        -ov \
        -format UDZO \
        "dist/${DMG_NAME}"
fi

if [[ -f "dist/${DMG_NAME}" ]]; then
    SIZE=$(du -sh "dist/${DMG_NAME}" | cut -f1)
    echo ""
    echo "✅  Release ready!"
    echo "    dist/${DMG_NAME}  (${SIZE})"
    echo ""
else
    echo "❌  DMG creation failed."
    exit 1
fi
