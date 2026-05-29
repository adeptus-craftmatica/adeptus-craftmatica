"""
release.py — Build, tag, and publish a new Adeptus Craftmatica release.

Run directly in PyCharm (right-click → Run 'release') or from the terminal:
    python release.py

What it does:
    1. Asks for a version number
    2. Checks dependencies are installed
    3. Builds the .app bundle via PyInstaller
    4. Packages it into a .dmg
    5. Updates the version in the spec file
    6. Commits any uncommitted changes
    7. Tags the release (vX.Y.Z)
    8. Pushes the commit + tag to GitHub
       → GitHub Actions picks up the tag and attaches the DMG to a GitHub Release
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

APP_NAME  = "Adeptus Craftmatica"
SPEC_FILE = "Adeptus_Craftmatica.spec"
DMG_NAME  = "Adeptus_Craftmatica.dmg"

# Root of the project (same directory as this script)
ROOT = Path(__file__).parent

# ── Helpers ───────────────────────────────────────────────────────────────────

def _print(msg: str, prefix: str = "→ "):
    print(f"{prefix} {msg}")

def success(msg: str):  _print(msg, "✅")
def info(msg: str):     _print(msg, "→ ")
def warn(msg: str):     _print(msg, "⚠️ ")

def die(msg: str):
    print(f"\n❌  {msg}\n")
    sys.exit(1)

def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess from the project root."""
    return subprocess.run(cmd, cwd=ROOT, check=check, capture_output=False)

def run_output(cmd: list[str]) -> str:
    """Run a subprocess and return stdout as a string."""
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return result.stdout.strip()

# ── Steps ─────────────────────────────────────────────────────────────────────

def ask_version() -> str:
    last_tag = run_output(["git", "describe", "--tags", "--abbrev=0"]) or "none"
    print(f"  Last release tag: {last_tag}")
    print()

    while True:
        version = input("  Enter version number (e.g. 1.0.0): ").strip().lstrip("v")
        if re.match(r"^\d+\.\d+\.\d+$", version):
            return version
        warn("Please use the format X.Y.Z  (e.g.  1.2.0)")


def check_tag(tag: str):
    result = subprocess.run(
        ["git", "rev-parse", tag],
        cwd=ROOT, capture_output=True
    )
    if result.returncode == 0:
        die(f"Tag {tag} already exists. Choose a different version.")


def check_dependencies():
    info("Checking dependencies…")

    if not shutil.which("pyinstaller"):
        warn("PyInstaller not found — installing now…")
        run([sys.executable, "-m", "pip", "install", "-r", "build_requirements.txt"])

    if not shutil.which("git"):
        die("git not found.")

    remote = run_output(["git", "remote", "get-url", "origin"])
    if not remote:
        die("No git remote 'origin' configured.")

    success("Dependencies OK")


def build_app():
    info("Running PyInstaller (this takes a few minutes)…")

    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(ROOT / "dist",  ignore_errors=True)

    result = subprocess.run(
        ["pyinstaller", SPEC_FILE, "--noconfirm"],
        cwd=ROOT
    )
    if result.returncode != 0:
        die("PyInstaller build failed.")

    app_path = ROOT / "dist" / f"{APP_NAME}.app"
    if not app_path.exists():
        die(f".app bundle not found at {app_path}")

    success("App bundle created")
    return app_path


def inject_plugins(app_path: Path):
    """
    Manually copy plugins into the bundle.
    PyInstaller doesn't reliably preserve the plugins/ directory structure
    for dynamically-loaded local packages, so we inject them directly.
    """
    info("Injecting plugins into bundle…")

    EXCLUDE = {'dev_tools', '__pycache__'}

    resources = app_path / "Contents" / "Resources"
    plugins_dest = resources / "plugins"
    plugins_src  = ROOT / "plugins"

    if plugins_dest.exists():
        shutil.rmtree(plugins_dest)
    plugins_dest.mkdir()

    count = 0
    for plugin_dir in sorted(plugins_src.iterdir()):
        if plugin_dir.is_dir() and plugin_dir.name not in EXCLUDE:
            shutil.copytree(
                plugin_dir,
                plugins_dest / plugin_dir.name,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'),
            )
            count += 1

    success(f"Plugins injected  ({count} plugins)")


def create_dmg(app_path: Path) -> Path:
    info("Creating DMG…")

    dmg_path = ROOT / "dist" / DMG_NAME

    if shutil.which("create-dmg"):
        result = subprocess.run([
            "create-dmg",
            "--volname",        APP_NAME,
            "--window-pos",     "200", "140",
            "--window-size",    "660", "400",
            "--icon-size",      "120",
            "--icon",           f"{APP_NAME}.app", "180", "170",
            "--hide-extension", f"{APP_NAME}.app",
            "--app-drop-link",  "480", "170",
            "--no-internet-enable",
            str(dmg_path),
            str(app_path),
        ], cwd=ROOT)
        if result.returncode != 0:
            warn("create-dmg reported an issue — falling back to hdiutil.")
            dmg_path.unlink(missing_ok=True)

    if not dmg_path.exists():
        # Built-in macOS fallback
        run([
            "hdiutil", "create",
            "-volname", APP_NAME,
            "-srcfolder", str(app_path),
            "-ov", "-format", "UDZO",
            str(dmg_path),
        ])

    if not dmg_path.exists():
        die("DMG creation failed.")

    size_bytes = dmg_path.stat().st_size
    size_mb    = size_bytes / (1024 * 1024)
    success(f"DMG created  ({size_mb:.0f} MB)")
    return dmg_path


def update_spec_version(version: str):
    info(f"Updating version in spec to {version}…")
    spec = (ROOT / SPEC_FILE).read_text()
    spec = re.sub(
        r"'CFBundleShortVersionString':\s*'[^']*'",
        f"'CFBundleShortVersionString': '{version}'",
        spec,
    )
    spec = re.sub(
        r"'CFBundleVersion':\s*'[^']*'",
        f"'CFBundleVersion': '{version}'",
        spec,
    )
    (ROOT / SPEC_FILE).write_text(spec)


def commit_and_tag(version: str):
    tag = f"v{version}"

    info("Staging changes…")
    run(["git", "add", "-A"])

    status = run_output(["git", "diff", "--cached", "--name-only"])
    if status:
        info("Committing…")
        run(["git", "commit", "-m", f"chore: release {tag}"])
        success("Changes committed")
    else:
        info("Nothing new to commit — working tree already clean.")

    info(f"Creating tag {tag}…")
    run(["git", "tag", tag])
    success(f"Tag {tag} created")

    info("Pushing to GitHub…")
    run(["git", "push", "origin", "HEAD"])
    run(["git", "push", "origin", tag])
    success("Pushed to GitHub")

    return tag


def print_summary(version: str, dmg_path: Path):
    tag        = f"v{version}"
    remote_url = run_output(["git", "remote", "get-url", "origin"])
    remote_url = remote_url.replace("git@github.com:", "https://github.com/").removesuffix(".git")

    print()
    print("╔══════════════════════════════════════════════╗")
    print(f"║       Release {tag} published!               ║")
    print("╚══════════════════════════════════════════════╝")
    print()
    print(f"  Local DMG:      dist/{DMG_NAME}")
    print(f"  Size:           {dmg_path.stat().st_size / (1024*1024):.0f} MB")
    print()
    print("  GitHub Actions is now building the release.")
    print(f"  Watch progress: {remote_url}/actions")
    print(f"  Releases page:  {remote_url}/releases")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║   Adeptus Craftmatica — Release Publisher    ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    version = ask_version()
    tag     = f"v{version}"

    print()
    info(f"Building release {tag}…")
    print()

    check_tag(tag)
    check_dependencies()

    app_path = build_app()
    inject_plugins(app_path)
    dmg_path = create_dmg(app_path)

    update_spec_version(version)
    commit_and_tag(version)
    print_summary(version, dmg_path)


if __name__ == "__main__":
    main()
