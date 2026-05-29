#!/usr/bin/env bash
# release.sh — Build, tag, and publish a new Adeptus Craftmatica release.
#
# Usage:
#   ./release.sh
#
# What it does:
#   1. Asks for a version number
#   2. Checks everything looks sane (git status, dependencies)
#   3. Builds the .app bundle via PyInstaller
#   4. Packages it into a .dmg
#   5. Commits any uncommitted changes
#   6. Tags the release (vX.Y.Z)
#   7. Pushes the commit + tag to GitHub
#      → GitHub Actions picks up the tag and attaches the DMG to a GitHub Release

set -euo pipefail

APP_NAME="Adeptus Craftmatica"
SPEC_FILE="Adeptus_Craftmatica.spec"
DMG_NAME="Adeptus_Craftmatica.dmg"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}→  $*${RESET}"; }
success() { echo -e "${GREEN}✅  $*${RESET}"; }
warn()    { echo -e "${YELLOW}⚠️   $*${RESET}"; }
die()     { echo -e "${RED}❌  $*${RESET}"; exit 1; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   Adeptus Craftmatica — Release Publisher    ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ── Step 1: Version number ────────────────────────────────────────────────────
# Show the last tag so the user knows where they left off
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")
echo -e "Last release tag: ${YELLOW}${LAST_TAG}${RESET}"
echo ""

while true; do
    read -rp "$(echo -e "${BOLD}Enter version number (e.g. 1.0.0): ${RESET}")" VERSION
    VERSION="${VERSION#v}"   # strip leading 'v' if they typed it
    if [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        break
    fi
    warn "Please use the format X.Y.Z (e.g. 1.2.0)"
done

TAG="v${VERSION}"

# Check the tag doesn't already exist
if git rev-parse "$TAG" &>/dev/null; then
    die "Tag ${TAG} already exists. Choose a different version."
fi

echo ""
info "Building release ${TAG}…"
echo ""

# ── Step 2: Sanity checks ─────────────────────────────────────────────────────
info "Checking dependencies…"

if ! command -v pyinstaller &>/dev/null; then
    warn "PyInstaller not found — installing now…"
    pip install -r build_requirements.txt || die "Failed to install build dependencies."
fi

if ! command -v git &>/dev/null; then
    die "git not found."
fi

# Check we have a remote to push to
if ! git remote get-url origin &>/dev/null; then
    die "No git remote 'origin' configured."
fi

success "Dependencies OK"

# ── Step 3: Build .app ────────────────────────────────────────────────────────
echo ""
info "Running PyInstaller (this takes a few minutes)…"
rm -rf build dist
pyinstaller "$SPEC_FILE" --noconfirm || die "PyInstaller build failed."

APP_PATH="dist/${APP_NAME}.app"
[[ -d "$APP_PATH" ]] || die ".app bundle not found after build."
success "App bundle created"

# ── Step 4: Create DMG ────────────────────────────────────────────────────────
echo ""
info "Creating DMG…"

_use_hdiutil=false
FORCE_HDIUTIL=false

if command -v create-dmg &>/dev/null; then
    create-dmg \
        --volname "$APP_NAME" \
        --window-pos 200 140 \
        --window-size 660 400 \
        --icon-size 120 \
        --icon "${APP_NAME}.app" 180 170 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 480 170 \
        --no-internet-enable \
        "dist/${DMG_NAME}" \
        "$APP_PATH" 2>/dev/null || _use_hdiutil=true
else
    _use_hdiutil=true
fi

if $FORCE_HDIUTIL || $_use_hdiutil; then
    hdiutil create \
        -volname "$APP_NAME" \
        -srcfolder "$APP_PATH" \
        -ov -format UDZO \
        "dist/${DMG_NAME}" || die "DMG creation failed."
fi

[[ -f "dist/${DMG_NAME}" ]] || die "DMG not found after packaging."
DMG_SIZE=$(du -sh "dist/${DMG_NAME}" | cut -f1)
success "DMG created  (${DMG_SIZE})"

# ── Step 5: Update version in spec ───────────────────────────────────────────
# Patch the version string inside the .spec so the app bundle reports correctly
info "Updating version in spec to ${VERSION}…"
sed -i '' \
    "s/'CFBundleShortVersionString': '[^']*'/'CFBundleShortVersionString': '${VERSION}'/" \
    "$SPEC_FILE"
sed -i '' \
    "s/'CFBundleVersion': '[^']*'/'CFBundleVersion': '${VERSION}'/" \
    "$SPEC_FILE"

# ── Step 6: Commit ────────────────────────────────────────────────────────────
echo ""
info "Committing changes…"

# Stage everything except build artefacts (covered by .gitignore)
git add -A

# Only commit if there's something to commit
if git diff --cached --quiet; then
    info "Nothing new to commit — working tree already clean."
else
    git commit -m "chore: release ${TAG}"
    success "Changes committed"
fi

# ── Step 7: Tag ───────────────────────────────────────────────────────────────
info "Creating tag ${TAG}…"
git tag "$TAG"
success "Tag ${TAG} created"

# ── Step 8: Push ──────────────────────────────────────────────────────────────
info "Pushing to GitHub…"
git push origin HEAD
git push origin "$TAG"
success "Pushed to GitHub"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║            Release ${TAG} published!           ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Local DMG:   ${CYAN}dist/${DMG_NAME}${RESET}"
echo ""
REMOTE_URL=$(git remote get-url origin | sed 's/\.git$//' | sed 's/git@github.com:/https:\/\/github.com\//')
echo -e "  GitHub Actions is now building the release."
echo -e "  Watch progress: ${CYAN}${REMOTE_URL}/actions${RESET}"
echo -e "  Releases page:  ${CYAN}${REMOTE_URL}/releases${RESET}"
echo ""
