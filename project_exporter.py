#!/usr/bin/env python3
"""
Studio Project Exporter + Architecture Mapper

Exports:
• Directory tree
• Source files
• File sizes
• Line counts
• Binary asset listing
• Project statistics
• Python module dependency graph

Automatically excludes:
    .venv
    __pycache__
    git folders
    build folders
"""

import os
import ast
from pathlib import Path
from datetime import datetime
import argparse

# ------------------------------------------------
# Directory Exclusions
# ------------------------------------------------

EXCLUDED_DIRS = {
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".git",
    ".github",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    "coverage",
}

# ------------------------------------------------
# Text File Types (export contents)
# ------------------------------------------------

TEXT_EXTENSIONS = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".txt",
    ".rst",
    ".html",
    ".css",
    ".scss",
    ".js",
    ".ts",
    ".sql",
    ".xml",
    ".qss",
    ".sh",
    ".bat",
}

# ------------------------------------------------
# Binary Asset Types (listed only)
# ------------------------------------------------

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".wav",
    ".mp3",
    ".ogg",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
}

# ------------------------------------------------
# Helpers
# ------------------------------------------------

def should_skip_dir(name: str):
    return name in EXCLUDED_DIRS


def is_text_file(path: Path):
    return path.suffix.lower() in TEXT_EXTENSIONS


def is_binary_asset(path: Path):
    return path.suffix.lower() in BINARY_EXTENSIONS


# ------------------------------------------------
# Directory Tree
# ------------------------------------------------

def build_tree(directory: Path, prefix=""):

    lines = []

    try:
        items = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        return lines

    items = [i for i in items if not (i.is_dir() and should_skip_dir(i.name))]

    for index, item in enumerate(items):

        connector = "└── " if index == len(items) - 1 else "├── "
        lines.append(prefix + connector + item.name)

        if item.is_dir():
            extension = "    " if index == len(items) - 1 else "│   "
            lines.extend(build_tree(item, prefix + extension))

    return lines


# ------------------------------------------------
# File Scanner
# ------------------------------------------------

def scan_project(root: Path):

    text_files = []
    binary_files = []

    for current_root, dirs, files in os.walk(root):

        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        for name in files:

            if name.startswith("project_export"):
                continue

            path = Path(current_root) / name

            if is_text_file(path):
                text_files.append(path)

            elif is_binary_asset(path):
                binary_files.append(path)

    return sorted(text_files), sorted(binary_files)


# ------------------------------------------------
# File Reader
# ------------------------------------------------

def read_text(path: Path):

    encodings = ["utf-8", "latin-1", "cp1252"]

    for enc in encodings:

        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue

    return "[unable to decode file]"


# ------------------------------------------------
# Line Counter
# ------------------------------------------------

def count_lines(text):
    return len(text.splitlines())


# ------------------------------------------------
# Dependency Analyzer
# ------------------------------------------------

def analyze_dependencies(root: Path, text_files):

    dependencies = {}

    for file in text_files:

        if file.suffix != ".py":
            continue

        rel = file.relative_to(root)

        module = (
            str(rel)
            .replace("\\", ".")
            .replace("/", ".")
            .replace(".py", "")
        )

        try:
            tree = ast.parse(read_text(file))
        except:
            continue

        imports = []

        for node in ast.walk(tree):

            if isinstance(node, ast.Import):

                for alias in node.names:
                    imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):

                if node.module:
                    imports.append(node.module)

        dependencies[module] = sorted(set(imports))

    return dependencies


# ------------------------------------------------
# Export
# ------------------------------------------------

def export_project(root: Path, output_file=None):

    if output_file is None:

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"project_export_{timestamp}.txt"

    output_path = root / output_file

    print("Scanning project...")

    text_files, binary_files = scan_project(root)

    dependencies = analyze_dependencies(root, text_files)

    tree = [root.name + "/"]
    tree.extend(build_tree(root))

    total_lines = 0

    print("Writing export...")

    with open(output_path, "w", encoding="utf-8") as out:

        out.write("=" * 80 + "\n")
        out.write("PROJECT EXPORT\n")
        out.write("=" * 80 + "\n")

        out.write(f"Project : {root.name}\n")
        out.write(f"Path    : {root.absolute()}\n")
        out.write(f"Date    : {datetime.now()}\n\n")

        # ------------------------------------------------
        # Statistics
        # ------------------------------------------------

        out.write("=" * 80 + "\n")
        out.write("PROJECT STATISTICS\n")
        out.write("=" * 80 + "\n")

        out.write(f"Text files   : {len(text_files)}\n")
        out.write(f"Binary assets: {len(binary_files)}\n\n")

        # ------------------------------------------------
        # Directory Tree
        # ------------------------------------------------

        out.write("=" * 80 + "\n")
        out.write("DIRECTORY TREE\n")
        out.write("=" * 80 + "\n\n")

        out.write("\n".join(tree))
        out.write("\n\n")

        # ------------------------------------------------
        # Binary Assets
        # ------------------------------------------------

        out.write("=" * 80 + "\n")
        out.write("BINARY ASSETS\n")
        out.write("=" * 80 + "\n\n")

        for file in binary_files:

            size_kb = file.stat().st_size / 1024
            rel = file.relative_to(root)

            out.write(f"{rel}  ({size_kb:.1f} KB)\n")

        out.write("\n\n")

        # ------------------------------------------------
        # Architecture Map
        # ------------------------------------------------

        out.write("=" * 80 + "\n")
        out.write("PROJECT ARCHITECTURE\n")
        out.write("=" * 80 + "\n\n")

        for module, imports in dependencies.items():

            out.write(module + "\n")

            for imp in imports:
                out.write(f" └─ {imp}\n")

            out.write("\n")

        # ------------------------------------------------
        # Source Files
        # ------------------------------------------------

        out.write("=" * 80 + "\n")
        out.write("SOURCE FILES\n")
        out.write("=" * 80 + "\n")

        for file in text_files:

            rel = file.relative_to(root)

            content = read_text(file)

            lines = count_lines(content)

            total_lines += lines

            out.write("\n")
            out.write("=" * 80 + "\n")
            out.write(f"FILE: {rel}\n")
            out.write(f"Lines: {lines}\n")
            out.write(f"Size : {file.stat().st_size / 1024:.1f} KB\n")
            out.write("=" * 80 + "\n\n")

            out.write(content)

            if not content.endswith("\n"):
                out.write("\n")

    print("\nExport complete")
    print("Text files :", len(text_files))
    print("Binary     :", len(binary_files))
    print("Lines      :", total_lines)

    return output_path


# ------------------------------------------------
# CLI
# ------------------------------------------------

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        default=".",
        help="Project root directory"
    )

    parser.add_argument(
        "--output",
        help="Output filename"
    )

    args = parser.parse_args()

    export_project(Path(args.root), args.output)