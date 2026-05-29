"""
release_windows.py — Build, tag, and publish a new Adeptus Craftmatica Windows release.

Run directly in PyCharm (right-click → Run 'release_windows') or from the terminal:
    python release_windows.py

What it does:
    1. Asks for a version number
    2. Checks dependencies are installed
    3. Builds the .exe via PyInstaller
    4. Packages the output into a .zip
    5. Updates the version in the spec file
    6. Commits any uncommitted changes
    7. Tags the release (vX.Y.Z)
    8. Pushes the commit + tag to GitHub
       → GitHub Actions picks up the tag and attaches the ZIP to a GitHub Release
"""

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

APP_NAME  = "Adeptus Craftmatica"
SPEC_FILE = "Adeptus_Craftmatica.spec"
ZIP_NAME  = "Adeptus_Craftmatica_Windows.zip"

ROOT = Path(__file__).parent

# ── Helpers ───────────────────────────────────────────────────────────────────

def _print(msg, prefix="-> "):  print(f"{prefix} {msg}")
def success(msg):  _print(msg, "OK ")
def info(msg):     _print(msg, "-> ")
def warn(msg):     _print(msg, "!! ")

def die(msg):
    print(f"\nERROR: {msg}\n")
    sys.exit(1)

def run(cmd: list, check: bool = True):
    return subprocess.run(cmd, cwd=ROOT, check=check)

def run_output(cmd: list) -> str:
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
    info("Checking dependencies...")

    if not shutil.which("pyinstaller"):
        warn("PyInstaller not found — installing now...")
        run([sys.executable, "-m", "pip", "install", "-r", "build_requirements.txt"])

    if not shutil.which("git"):
        die("git not found.")

    remote = run_output(["git", "remote", "get-url", "origin"])
    if not remote:
        die("No git remote 'origin' configured.")

    success("Dependencies OK")


def build_exe():
    info("Running PyInstaller (this takes a few minutes)...")

    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(ROOT / "dist",  ignore_errors=True)

    result = subprocess.run(
        ["pyinstaller", SPEC_FILE, "--noconfirm"],
        cwd=ROOT
    )
    if result.returncode != 0:
        die("PyInstaller build failed.")

    exe_dir = ROOT / "dist" / APP_NAME
    if not exe_dir.exists():
        die(f"Build output not found at {exe_dir}")

    success("Executable built")
    return exe_dir


def create_zip(exe_dir: Path) -> Path:
    info("Creating ZIP...")

    zip_path = ROOT / "dist" / ZIP_NAME

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in exe_dir.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(exe_dir.parent))

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    success(f"ZIP created  ({size_mb:.0f} MB)")
    return zip_path


def update_spec_version(version: str):
    info(f"Updating version in spec to {version}...")
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

    info("Staging changes...")
    run(["git", "add", "-A"])

    status = run_output(["git", "diff", "--cached", "--name-only"])
    if status:
        info("Committing...")
        run(["git", "commit", "-m", f"chore: release {tag}"])
        success("Changes committed")
    else:
        info("Nothing new to commit — working tree already clean.")

    info(f"Creating tag {tag}...")
    run(["git", "tag", tag])
    success(f"Tag {tag} created")

    info("Pushing to GitHub...")
    run(["git", "push", "origin", "HEAD"])
    run(["git", "push", "origin", tag])
    success("Pushed to GitHub")

    return tag


def print_summary(version: str, zip_path: Path):
    tag        = f"v{version}"
    remote_url = run_output(["git", "remote", "get-url", "origin"])
    remote_url = remote_url.replace("git@github.com:", "https://github.com/").removesuffix(".git")

    print()
    print("================================================")
    print(f"  Release {tag} published!")
    print("================================================")
    print()
    print(f"  Local ZIP:      dist\\{ZIP_NAME}")
    print(f"  Size:           {zip_path.stat().st_size / (1024*1024):.0f} MB")
    print()
    print("  GitHub Actions is now building the release.")
    print(f"  Watch progress: {remote_url}/actions")
    print(f"  Releases page:  {remote_url}/releases")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("================================================")
    print("  Adeptus Craftmatica -- Windows Release Builder")
    print("================================================")
    print()

    version = ask_version()
    tag     = f"v{version}"

    print()
    info(f"Building release {tag}...")
    print()

    check_tag(tag)
    check_dependencies()

    exe_dir  = build_exe()
    zip_path = create_zip(exe_dir)

    update_spec_version(version)
    commit_and_tag(version)
    print_summary(version, zip_path)


if __name__ == "__main__":
    main()
