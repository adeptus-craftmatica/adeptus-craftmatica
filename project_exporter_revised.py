#!/usr/bin/env python3
"""
Project Exporter Pro  ·  Architecture Intelligence System
=========================================================

Master export script — generates a complete, self-contained snapshot of any
Python project together with architecture analysis, event-bus mapping, plugin
discovery, and health scoring.

Every run produces two files inside  project_exports/ :

  project_exports/project_export_<timestamp>.txt      — full human-readable report
  project_exports/project_export_<timestamp>.txt.zip  — identical content, compressed

Optionally add  --json  to also write:

  project_exports/project_export_<timestamp>.json     — structured data for tooling

Usage
-----
  python project_exporter_revised.py
  python project_exporter_revised.py --root /path/to/project
  python project_exporter_revised.py --json
  python project_exporter_revised.py --no-source     # omit raw file contents
  python project_exporter_revised.py --json --no-source --root ../MyProject
"""

import os
import ast
import json
import re
import zipfile
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional
import argparse

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

EXCLUDED_DIRS = {
    ".venv", "venv", "env",
    "__pycache__",
    ".git", ".github",
    ".idea", ".vscode",
    "node_modules",
    "dist", "build",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "htmlcov", "coverage",
    "project_exports",          # never include our own output folder
}

TEXT_EXTENSIONS = {
    ".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".md", ".txt", ".rst",
    ".html", ".css", ".scss",
    ".js", ".ts", ".jsx", ".tsx",
    ".sql", ".xml", ".qss",
    ".sh", ".bat",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".wav", ".mp3", ".ogg",
    ".ttf", ".otf", ".woff", ".woff2",
    ".db", ".sqlite", ".sqlite3",
    ".pdf", ".zip",
}

# Architecture rules engine
ARCHITECTURE_RULES = {
    "no_plugin_to_plugin": True,   # Plugins must not import each other directly
    "no_core_to_plugin":   True,   # Core must not import plugin code
    "detect_circular":     True,   # Flag circular imports
    "flag_empty_modules":  True,   # Flag near-empty .py files
}

# Event-bus regex patterns (matches common pub/sub conventions)
EVENT_PATTERNS = {
    "emit":      r'\.emit\s*\(\s*["\']([^"\']+)["\']',
    "subscribe": r'\.subscribe\s*\(\s*["\']([^"\']+)["\']',
    "publish":   r'\.publish\s*\(\s*["\']([^"\']+)["\']',
    "on":        r'\.on\s*\(\s*["\']([^"\']+)["\']',
}

# Lines-of-code threshold below which a module is flagged as stub/empty
STUB_THRESHOLD = 5

# Maximum README characters to include in the overview section
README_PREVIEW_CHARS = 2000

# Width of section separators
W = 80


# ═══════════════════════════════════════════════════════════════════════════════
# FORMATTING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _rule(char: str = "═", width: int = W) -> str:
    return char * width


def _header(title: str, char: str = "═") -> str:
    return f"\n{_rule(char)}\n{title}\n{_rule(char)}\n"


def _subheader(title: str) -> str:
    return f"\n{title}\n{'-' * len(title)}\n"


def _box(lines: List[str], width: int = W) -> str:
    """Wrap lines in a simple ASCII box."""
    inner_w = width - 4
    top    = "┌" + "─" * (width - 2) + "┐"
    bottom = "└" + "─" * (width - 2) + "┘"
    rows   = [top]
    for line in lines:
        # Pad or truncate to inner_w
        rows.append("│  " + line[:inner_w].ljust(inner_w) + "  │")
    rows.append(bottom)
    return "\n".join(rows) + "\n"


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def should_skip_dir(name: str) -> bool:
    return name in EXCLUDED_DIRS


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def is_binary_asset(path: Path) -> bool:
    return path.suffix.lower() in BINARY_EXTENSIONS


def read_text(path: Path) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, PermissionError):
            continue
    return "[unable to decode file]"


def count_lines(text: str) -> int:
    return len(text.splitlines())


def human_size(byte_count: int) -> str:
    if byte_count < 1024:
        return f"{byte_count} B"
    if byte_count < 1024 ** 2:
        return f"{byte_count / 1024:.1f} KB"
    return f"{byte_count / (1024 ** 2):.1f} MB"


def extract_module_docstring(content: str) -> str:
    """Return the module-level docstring from Python source, or ''."""
    try:
        tree = ast.parse(content)
        return ast.get_docstring(tree) or ""
    except Exception:
        return ""


def read_readme(root: Path) -> str:
    """Return the content of the first README file found, or ''."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        p = root / name
        if p.is_file():
            return read_text(p)
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# DIRECTORY TREE
# ═══════════════════════════════════════════════════════════════════════════════

def build_tree(directory: Path, prefix: str = "") -> List[str]:
    lines = []
    try:
        items = sorted(
            directory.iterdir(),
            key=lambda x: (not x.is_dir(), x.name.lower()),
        )
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


# ═══════════════════════════════════════════════════════════════════════════════
# FILE SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

def scan_project(root: Path) -> Tuple[List[Path], List[Path]]:
    """Walk the project tree and separate text from binary files."""
    text_files: List[Path] = []
    binary_files: List[Path] = []

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        for name in files:
            path = Path(current_root) / name
            if is_text_file(path):
                text_files.append(path)
            elif is_binary_asset(path):
                binary_files.append(path)

    return sorted(text_files), sorted(binary_files)


# ═══════════════════════════════════════════════════════════════════════════════
# PLUGIN DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

class PluginInfo:
    def __init__(self, path: Path, metadata: dict):
        self.path        = path            # path to plugin.json or plugin.py
        self.name        = metadata.get("name", path.parent.name)
        self.version     = metadata.get("version", "unknown")
        self.entry       = metadata.get("entry", "plugin.py")
        self.description = metadata.get("description", "")
        self.author      = metadata.get("author", "")
        self.dependencies = metadata.get("dependencies", [])
        self.plugin_id   = metadata.get("plugin_id", "")

    @property
    def plugin_dir(self) -> Path:
        return self.path.parent


def detect_plugins(root: Path, text_files: List[Path]) -> List[PluginInfo]:
    """
    Detect plugins using two strategies:
      1. plugin.json files with structured metadata
      2. plugin.py files that define a Plugin class (Python-based plugins)

    Results are merged and deduplicated by directory.
    """
    plugins: Dict[Path, PluginInfo] = {}

    # ── Strategy 1: plugin.json ───────────────────────────────────────────────
    for file in text_files:
        if file.name != "plugin.json":
            continue
        try:
            metadata = json.loads(read_text(file))
        except Exception:
            metadata = {"name": file.parent.name}
        plugins[file.parent] = PluginInfo(file, metadata)

    # ── Strategy 2: plugin.py with Plugin class ───────────────────────────────
    for file in text_files:
        if file.name != "plugin.py":
            continue
        if file.parent in plugins:
            continue   # already found via JSON

        content = read_text(file)
        try:
            tree = ast.parse(content)
        except Exception:
            continue

        # Only treat it as a plugin if there's a class named Plugin
        plugin_class = next(
            (node for node in ast.walk(tree)
             if isinstance(node, ast.ClassDef) and node.name == "Plugin"),
            None,
        )
        if plugin_class is None:
            continue

        # Extract class-level string assignments (name, version, description …)
        meta: dict = {
            "name":        file.parent.name,
            "version":     "1.0.0",
            "entry":       "plugin.py",
            "description": "",
        }
        for node in ast.walk(plugin_class):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Name)
                            and isinstance(node.value, ast.Constant)):
                        meta[target.id] = node.value.value

        # Fall back to module docstring for description
        if not meta["description"]:
            meta["description"] = extract_module_docstring(content)

        plugins[file.parent] = PluginInfo(file, meta)

    return sorted(plugins.values(), key=lambda p: p.name.lower())


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT BUS ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

class EventInfo:
    def __init__(self):
        self.emitters:    Set[str] = set()
        self.subscribers: Set[str] = set()


def analyze_events(root: Path, text_files: List[Path]) -> Dict[str, EventInfo]:
    """Extract all event-bus emit / subscribe patterns from Python source."""
    events: Dict[str, EventInfo] = defaultdict(EventInfo)

    for file in text_files:
        if file.suffix != ".py":
            continue

        rel    = file.relative_to(root)
        module = str(rel).replace("\\", ".").replace("/", ".").removesuffix(".py")
        content = read_text(file)

        for pattern_name, pattern in EVENT_PATTERNS.items():
            for event_name in re.findall(pattern, content):
                if pattern_name in ("emit", "publish"):
                    events[event_name].emitters.add(module)
                else:
                    events[event_name].subscribers.add(module)

    return dict(events)


def classify_events(events: Dict[str, EventInfo]) -> dict:
    """Classify events into connected, orphaned-emits, and dead-subscribers."""
    connected  = {k: v for k, v in events.items() if v.emitters and v.subscribers}
    emit_only  = {k: v for k, v in events.items() if v.emitters and not v.subscribers}
    sub_only   = {k: v for k, v in events.items() if not v.emitters and v.subscribers}
    return {"connected": connected, "emit_only": emit_only, "sub_only": sub_only}


# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCY ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_dependencies(root: Path, text_files: List[Path]) -> Dict[str, List[str]]:
    """Extract import statements from all Python files."""
    dependencies: Dict[str, List[str]] = {}

    for file in text_files:
        if file.suffix != ".py":
            continue

        rel    = file.relative_to(root)
        module = str(rel).replace("\\", ".").replace("/", ".").removesuffix(".py")

        try:
            tree = ast.parse(read_text(file))
        except Exception as e:
            dependencies[module] = [f"[PARSE ERROR: {type(e).__name__}]"]
            continue

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        dependencies[module] = sorted(imports)

    return dependencies


def internal_deps_only(
    dependencies: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    """Filter dependency graph to only internal (project-local) modules."""
    all_modules = set(dependencies.keys())
    result = {}
    for module, imports in dependencies.items():
        internal = [i for i in imports if i in all_modules]
        if internal:
            result[module] = internal
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# EMPTY MODULE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_empty_modules(root: Path, text_files: List[Path]) -> List[Tuple[str, int]]:
    """Find Python files with very few substantive lines (stubs / placeholders)."""
    empty = []
    for file in text_files:
        if file.suffix != ".py":
            continue
        content = read_text(file)
        non_empty = [
            l for l in content.splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        if len(non_empty) <= STUB_THRESHOLD:
            empty.append((str(file.relative_to(root)), count_lines(content)))
    return empty


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCULAR DEPENDENCY DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_circular_imports(dependencies: Dict[str, List[str]]) -> List[List[str]]:
    """Detect circular import chains using DFS."""

    def find_cycles(node: str, path: List[str], visited: Set[str]) -> List[List[str]]:
        if node in path:
            start = path.index(node)
            return [path[start:] + [node]]
        if node in visited:
            return []
        visited.add(node)
        cycles = []
        for dep in dependencies.get(node, []):
            if dep in dependencies:
                cycles.extend(find_cycles(dep, path + [node], visited))
        return cycles

    all_cycles: List[List[str]] = []
    visited_global: Set[str] = set()

    for module in dependencies:
        if module not in visited_global:
            for cycle in find_cycles(module, [], set()):
                min_idx   = cycle.index(min(cycle[:-1]))
                normalized = cycle[min_idx:-1] + cycle[:min_idx] + [cycle[min_idx]]
                if normalized not in all_cycles:
                    all_cycles.append(normalized)
            visited_global.add(module)

    return all_cycles


# ═══════════════════════════════════════════════════════════════════════════════
# ARCHITECTURE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class ArchitectureViolation:
    def __init__(self, rule: str, violator: str, target: str, message: str):
        self.rule     = rule
        self.violator = violator
        self.target   = target
        self.message  = message


def validate_architecture(
    root: Path,
    dependencies: Dict[str, List[str]],
    plugins: List[PluginInfo],
) -> List[ArchitectureViolation]:
    violations: List[ArchitectureViolation] = []

    plugin_prefixes = set()
    for plugin in plugins:
        prefix = str(plugin.plugin_dir.relative_to(root)).replace("\\", ".").replace("/", ".")
        plugin_prefixes.add(prefix)

    core_modules = {
        m for m in dependencies
        if not any(m.startswith(pp) for pp in plugin_prefixes)
    }

    for module, imports in dependencies.items():
        module_plugin = next((pp for pp in plugin_prefixes if module.startswith(pp)), None)

        for imp in imports:
            imp_plugin = next((pp for pp in plugin_prefixes if imp.startswith(pp)), None)

            # Rule 1: no plugin → other plugin
            if (ARCHITECTURE_RULES["no_plugin_to_plugin"]
                    and module_plugin and imp_plugin
                    and module_plugin != imp_plugin):
                violations.append(ArchitectureViolation(
                    "no_plugin_to_plugin", module, imp,
                    f"Plugin '{module_plugin}' directly imports from '{imp_plugin}'"
                ))

            # Rule 2: no core → plugin
            if (ARCHITECTURE_RULES["no_core_to_plugin"]
                    and module in core_modules and imp_plugin):
                violations.append(ArchitectureViolation(
                    "no_core_to_plugin", module, imp,
                    f"Core module '{module}' imports plugin code '{imp}'"
                ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════════
# PLUGIN BOUNDARY MAP
# ═══════════════════════════════════════════════════════════════════════════════

class BoundaryInfo:
    def __init__(self, name: str, is_plugin: bool):
        self.name              = name
        self.is_plugin         = is_plugin
        self.modules:           Set[str]           = set()
        self.internal_imports:  Set[Tuple[str,str]] = set()
        self.external_imports:  Set[Tuple[str,str]] = set()
        self.incoming_cross:    Set[Tuple[str,str]] = set()


def build_boundaries(
    root: Path,
    dependencies: Dict[str, List[str]],
    plugins: List[PluginInfo],
) -> Dict[str, BoundaryInfo]:
    """Assign every module to a boundary (plugin or core) and map cross-boundary traffic."""
    boundaries: Dict[str, BoundaryInfo] = {}

    plugin_prefix_map: Dict[str, str] = {}   # prefix → plugin name
    for plugin in plugins:
        prefix = (
            str(plugin.plugin_dir.relative_to(root))
            .replace("\\", ".").replace("/", ".")
        )
        boundaries[plugin.name] = BoundaryInfo(plugin.name, is_plugin=True)
        plugin_prefix_map[prefix] = plugin.name

    boundaries["core"] = BoundaryInfo("core", is_plugin=False)

    # Assign modules to boundaries
    for module in dependencies:
        assigned = False
        for prefix, pname in plugin_prefix_map.items():
            if module.startswith(prefix):
                boundaries[pname].modules.add(module)
                assigned = True
                break
        if not assigned:
            boundaries["core"].modules.add(module)

    # Classify imports as internal vs cross-boundary
    module_to_boundary: Dict[str, str] = {}
    for bname, binfo in boundaries.items():
        for m in binfo.modules:
            module_to_boundary[m] = bname

    for module, imports in dependencies.items():
        mb = module_to_boundary.get(module)
        if not mb:
            continue
        for imp in imports:
            ib = module_to_boundary.get(imp)
            if not ib:
                continue
            if mb == ib:
                boundaries[mb].internal_imports.add((module, imp))
            else:
                boundaries[mb].external_imports.add((module, imp))
                boundaries[ib].incoming_cross.add((module, imp))

    return boundaries


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH SCORING
# ═══════════════════════════════════════════════════════════════════════════════

def compute_health(
    violations: List[ArchitectureViolation],
    circular_imports: List[List[str]],
    empty_modules: List[Tuple[str, int]],
    events: Dict[str, EventInfo],
) -> Tuple[int, List[str]]:
    """
    Return (score, findings_list).
    Score is 0–100; 100 = perfectly clean.
    """
    score    = 100
    findings = []

    v_penalty = min(len(violations) * 10, 40)
    if v_penalty:
        score -= v_penalty
        findings.append(f"❌  {len(violations)} architecture violation(s)  (-{v_penalty} pts)")

    c_penalty = min(len(circular_imports) * 8, 24)
    if c_penalty:
        score -= c_penalty
        findings.append(f"🔄  {len(circular_imports)} circular import chain(s)  (-{c_penalty} pts)")

    e_penalty = min(len(empty_modules) * 2, 10)
    if e_penalty:
        score -= e_penalty
        findings.append(f"⚠️   {len(empty_modules)} stub/empty module(s)  (-{e_penalty} pts)")

    # Orphaned events (emitted but nobody listens)
    emit_only = [k for k, v in events.items() if v.emitters and not v.subscribers]
    if emit_only:
        penalty = min(len(emit_only) * 1, 6)
        score  -= penalty
        findings.append(f"📡  {len(emit_only)} event(s) emitted but never subscribed  (-{penalty} pts)")

    if not findings:
        findings.append("✅  No issues detected — project is architecturally clean")

    score = max(0, score)
    return score, findings


def health_grade(score: int) -> str:
    if score >= 90: return "A  (Excellent)"
    if score >= 75: return "B  (Good)"
    if score >= 60: return "C  (Fair)"
    if score >= 40: return "D  (Needs attention)"
    return "F  (Critical issues)"


# ═══════════════════════════════════════════════════════════════════════════════
# TECHNOLOGY FINGERPRINTING
# ═══════════════════════════════════════════════════════════════════════════════

def fingerprint_tech(dependencies: Dict[str, List[str]]) -> List[str]:
    """
    Identify major third-party frameworks / libraries from import names.
    Returns a sorted list of human-readable technology names.
    """
    all_imports: Set[str] = set()
    for imps in dependencies.values():
        all_imports.update(imps)

    KNOWN = {
        "PySide6":     "PySide6 (Qt GUI framework)",
        "PyQt5":       "PyQt5 (Qt GUI framework)",
        "PyQt6":       "PyQt6 (Qt GUI framework)",
        "flask":       "Flask (web framework)",
        "fastapi":     "FastAPI (web framework)",
        "django":      "Django (web framework)",
        "sqlalchemy":  "SQLAlchemy (ORM)",
        "sqlite3":     "SQLite3 (built-in SQL database)",
        "requests":    "Requests (HTTP client)",
        "aiohttp":     "aiohttp (async HTTP)",
        "numpy":       "NumPy (numerical computing)",
        "pandas":      "pandas (data analysis)",
        "pytest":      "pytest (testing framework)",
        "pydantic":    "Pydantic (data validation)",
        "celery":      "Celery (task queue)",
        "redis":       "Redis (caching / message broker)",
        "boto3":       "AWS SDK (boto3)",
        "PIL":         "Pillow (image processing)",
        "cv2":         "OpenCV (computer vision)",
    }

    found = []
    for key, label in KNOWN.items():
        # Match as root-level import or submodule import
        if any(i == key or i.startswith(key + ".") for i in all_imports):
            found.append(label)

    return sorted(found)


# ═══════════════════════════════════════════════════════════════════════════════
# PLUGIN CATALOG BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_plugin_catalog(
    root: Path,
    plugins: List[PluginInfo],
    events: Dict[str, EventInfo],
    text_files: List[Path],
) -> List[dict]:
    """
    For each plugin, gather:
      - metadata (name, version, description, author)
      - source files it owns
      - events it emits
      - events it subscribes to
      - its module docstring (from plugin.py)
    """
    catalog = []

    for plugin in plugins:
        pdir = plugin.plugin_dir

        # Files owned by this plugin
        owned_files = sorted(
            f for f in text_files
            if f == plugin.path or f.is_relative_to(pdir)
        )

        # Compute relative paths for display
        owned_rel = [str(f.relative_to(root)) for f in owned_files]

        # Compute relative module prefix for event matching
        prefix = (
            str(pdir.relative_to(root))
            .replace("\\", ".").replace("/", ".")
        )

        # Events this plugin is involved with
        plugin_emits = sorted(
            name for name, info in events.items()
            if any(e.startswith(prefix) for e in info.emitters)
        )
        plugin_subscribes = sorted(
            name for name, info in events.items()
            if any(s.startswith(prefix) for s in info.subscribers)
        )

        # Module docstring from plugin.py
        plugin_py = pdir / "plugin.py"
        module_doc = ""
        if plugin_py.is_file():
            module_doc = extract_module_docstring(read_text(plugin_py))

        catalog.append({
            "name":        plugin.name,
            "version":     plugin.version,
            "description": plugin.description or module_doc,
            "author":      plugin.author,
            "plugin_id":   plugin.plugin_id,
            "entry":       plugin.entry,
            "path":        str(pdir.relative_to(root)),
            "files":       owned_rel,
            "emits":       plugin_emits,
            "subscribes":  plugin_subscribes,
            "file_count":  len(owned_files),
            "line_count":  sum(
                count_lines(read_text(f)) for f in owned_files
                if f.suffix == ".py"
            ),
        })

    return catalog


# ═══════════════════════════════════════════════════════════════════════════════
# JSON EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

def build_json_export(
    root: Path,
    text_files: List[Path],
    binary_files: List[Path],
    dependencies: Dict[str, List[str]],
    plugins: List[PluginInfo],
    events: Dict[str, EventInfo],
    empty_modules: List[Tuple[str, int]],
    circular_imports: List[List[str]],
    violations: List[ArchitectureViolation],
    boundaries: Dict[str, BoundaryInfo],
    plugin_catalog: List[dict],
    health_score: int,
) -> dict:
    total_lines = sum(
        count_lines(read_text(f)) for f in text_files if f.suffix == ".py"
    )
    return {
        "metadata": {
            "project":  root.resolve().name,
            "path":     str(root.resolve()),
            "exported": datetime.now().isoformat(),
            "stats": {
                "text_files":   len(text_files),
                "binary_files": len(binary_files),
                "total_lines":  total_lines,
                "plugins":      len(plugins),
                "events":       len(events),
                "health_score": health_score,
            },
        },
        "plugins": plugin_catalog,
        "events": {
            name: {
                "emitters":    sorted(info.emitters),
                "subscribers": sorted(info.subscribers),
            }
            for name, info in sorted(events.items())
        },
        "dependencies": dependencies,
        "boundaries": {
            name: {
                "is_plugin":        binfo.is_plugin,
                "modules":          sorted(binfo.modules),
                "internal_imports": len(binfo.internal_imports),
                "outgoing_imports": len(binfo.external_imports),
                "incoming_imports": len(binfo.incoming_cross),
            }
            for name, binfo in boundaries.items()
        },
        "issues": {
            "empty_modules": [
                {"file": path, "lines": lines}
                for path, lines in empty_modules
            ],
            "circular_imports":        circular_imports,
            "architecture_violations": [
                {"rule": v.rule, "violator": v.violator,
                 "target": v.target, "message": v.message}
                for v in violations
            ],
        },
        "files": {
            "text":   [str(f.relative_to(root)) for f in text_files],
            "binary": [str(f.relative_to(root)) for f in binary_files],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT EXPORT  ──  the main human-readable report
# ═══════════════════════════════════════════════════════════════════════════════

def write_text_export(
    out,
    root: Path,
    text_files: List[Path],
    binary_files: List[Path],
    dependencies: Dict[str, List[str]],
    plugins: List[PluginInfo],
    events: Dict[str, EventInfo],
    empty_modules: List[Tuple[str, int]],
    circular_imports: List[List[str]],
    violations: List[ArchitectureViolation],
    boundaries: Dict[str, BoundaryInfo],
    plugin_catalog: List[dict],
    health_score: int,
    health_findings: List[str],
    include_source: bool = True,
) -> int:
    """
    Write the full text report to *out* (any file-like object).
    Returns the total Python line count.
    """
    project_name = root.resolve().name
    total_py_lines = sum(
        count_lines(read_text(f)) for f in text_files if f.suffix == ".py"
    )
    tech_stack = fingerprint_tech(dependencies)
    event_classes = classify_events(events)
    readme_text = read_readme(root)

    # ── COVER PAGE ─────────────────────────────────────────────────────────────
    out.write(_rule("═") + "\n")
    out.write("PROJECT EXPORT  ·  Architecture Intelligence System\n")
    out.write(_rule("═") + "\n")
    out.write(f"\n")
    out.write(f"  Project   :  {project_name}\n")
    out.write(f"  Path      :  {root.resolve()}\n")
    out.write(f"  Exported  :  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}\n")
    out.write(f"  Generator :  project_exporter_revised.py\n")
    out.write(f"\n")
    out.write(_rule("─") + "\n\n")

    # ── HOW TO READ THIS DOCUMENT ──────────────────────────────────────────────
    out.write(_header("HOW TO READ THIS DOCUMENT"))
    out.write("""This export is a complete, self-contained description of the project.
It is structured so that a reader with no prior knowledge of the codebase can
understand its full scope, architecture, and current health.

Read in order for the first time:

  §1   Project Overview      — purpose, scale, technology choices
  §2   Health Summary        — overall quality score and any issues
  §3   Plugin Catalog        — each major component explained individually
  §4   Event Bus Map         — how components communicate (pub/sub events)
  §5   Architecture Analysis — rule violations, circular imports, stubs
  §6   Plugin Boundaries     — coupling between architectural zones
  §7   Directory Tree        — filesystem layout at a glance
  §8   Dependency Graph      — internal module imports (project-local only)
  §9   Binary Assets         — non-source files (images, databases, etc.)
  §10  Source Files          — complete, annotated source code

If you only need a quick orientation, read §1–§4 (typically < 5 minutes).
The source code in §10 is the full detail layer — search within it by filename.

Conventions used throughout:
  ✅  Good / complete          ⚠️   Warning / stub / suspect
  ❌  Architecture violation   🔄  Circular dependency
  📡  Event emitted            🔌  Plugin boundary
  ⚙️   Core / shared module     🏁  Nearly complete
""")

    # ── §1  PROJECT OVERVIEW ───────────────────────────────────────────────────
    out.write(_header("§1  PROJECT OVERVIEW"))

    out.write(f"  Name         :  {project_name}\n")
    out.write(f"  Python files :  {len([f for f in text_files if f.suffix == '.py'])}\n")
    out.write(f"  Total lines  :  {total_py_lines:,}\n")
    out.write(f"  All sources  :  {len(text_files)} files\n")
    out.write(f"  Binary assets:  {len(binary_files)} files\n")
    out.write(f"  Plugins      :  {len(plugins)}\n")
    out.write(f"  Event types  :  {len(events)}\n\n")

    if tech_stack:
        out.write("  Technology stack detected:\n")
        for tech in tech_stack:
            out.write(f"    • {tech}\n")
        out.write("\n")

    if readme_text:
        out.write(_subheader("README"))
        preview = readme_text[:README_PREVIEW_CHARS]
        out.write(preview)
        if len(readme_text) > README_PREVIEW_CHARS:
            out.write(f"\n  ... [{len(readme_text) - README_PREVIEW_CHARS} additional characters — see §10 for full file]\n")
        out.write("\n")

    # ── §2  HEALTH SUMMARY ─────────────────────────────────────────────────────
    out.write(_header("§2  PROJECT HEALTH SUMMARY"))

    grade = health_grade(health_score)
    bar_filled = round(health_score / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    out.write(f"  Health Score :  {health_score} / 100\n")
    out.write(f"  Grade        :  {grade}\n")
    out.write(f"  [{bar}]\n\n")

    out.write("  Findings:\n")
    for finding in health_findings:
        out.write(f"    {finding}\n")
    out.write("\n")

    # Quick-reference issue tables
    if violations:
        out.write(f"  Architecture violations  ({len(violations)}):\n")
        for v in violations[:10]:
            out.write(f"    ❌  {v.message}\n")
        if len(violations) > 10:
            out.write(f"    ... and {len(violations)-10} more (see §5)\n")
        out.write("\n")

    if circular_imports:
        out.write(f"  Circular import chains  ({len(circular_imports)}):\n")
        for cycle in circular_imports[:5]:
            out.write(f"    🔄  {' → '.join(cycle)}\n")
        if len(circular_imports) > 5:
            out.write(f"    ... and {len(circular_imports)-5} more (see §5)\n")
        out.write("\n")

    # ── §3  PLUGIN CATALOG ─────────────────────────────────────────────────────
    out.write(_header("§3  PLUGIN CATALOG"))
    out.write(
        f"  {len(plugins)} plugin(s) detected.  Each plugin is a self-contained feature\n"
        f"  module that registers with the core event bus and service registry.\n\n"
    )

    for entry in plugin_catalog:
        # Plugin header
        out.write(f"  ┌─ {entry['name']}")
        if entry['version'] and entry['version'] != "unknown":
            out.write(f"  v{entry['version']}")
        out.write(f"\n")

        # Description
        desc = entry['description']
        if desc:
            # Word-wrap the description at 70 chars
            words = desc.split()
            line, lines_out = [], []
            for w in words:
                if sum(len(x) + 1 for x in line) + len(w) > 68:
                    lines_out.append(" ".join(line))
                    line = [w]
                else:
                    line.append(w)
            if line:
                lines_out.append(" ".join(line))
            for l in lines_out:
                out.write(f"  │  {l}\n")
        else:
            out.write(f"  │  (no description)\n")

        out.write(f"  │\n")
        out.write(f"  │  Path        :  {entry['path']}\n")
        if entry['author']:
            out.write(f"  │  Author      :  {entry['author']}\n")
        out.write(f"  │  Files       :  {entry['file_count']}  "
                  f"({entry['line_count']:,} Python lines)\n")

        # Events
        if entry['emits']:
            out.write(f"  │  Emits ({len(entry['emits'])})  :\n")
            for ev in entry['emits'][:8]:
                out.write(f"  │      📡  {ev}\n")
            if len(entry['emits']) > 8:
                out.write(f"  │      ... and {len(entry['emits'])-8} more\n")

        if entry['subscribes']:
            out.write(f"  │  Listens ({len(entry['subscribes'])}):\n")
            for ev in entry['subscribes'][:8]:
                out.write(f"  │      ←  {ev}\n")
            if len(entry['subscribes']) > 8:
                out.write(f"  │      ... and {len(entry['subscribes'])-8} more\n")

        if not entry['emits'] and not entry['subscribes']:
            out.write(f"  │  (no event-bus activity detected)\n")

        out.write(f"  └─\n\n")

    # ── §4  EVENT BUS MAP ──────────────────────────────────────────────────────
    out.write(_header("§4  EVENT BUS MAP"))

    total_events = len(events)
    connected_count = len(event_classes["connected"])
    orphan_emit     = len(event_classes["emit_only"])
    dead_sub        = len(event_classes["sub_only"])

    out.write(f"  Total event types  :  {total_events}\n")
    out.write(f"  Fully connected    :  {connected_count}  (emitter AND subscriber found)\n")
    if orphan_emit:
        out.write(f"  Emitted, no sub    :  {orphan_emit}  (nobody is listening)\n")
    if dead_sub:
        out.write(f"  Subscribed, no emit:  {dead_sub}  (never fired)\n")
    out.write("\n")

    def _write_event_block(name: str, info: EventInfo):
        out.write(f"  📡  {name}\n")
        for src in sorted(info.emitters):
            out.write(f"       ├─ EMIT  :  {src}\n")
        for dst in sorted(info.subscribers):
            out.write(f"       └─ RECV  :  {dst}\n")
        if not info.emitters and not info.subscribers:
            out.write(f"       (no usage found)\n")
        out.write("\n")

    if event_classes["connected"]:
        out.write(_subheader("Connected events  (both sides present)"))
        for name in sorted(event_classes["connected"]):
            _write_event_block(name, events[name])

    if event_classes["emit_only"]:
        out.write(_subheader("Emitted but never subscribed  (possible dead events)"))
        for name in sorted(event_classes["emit_only"]):
            _write_event_block(name, events[name])

    if event_classes["sub_only"]:
        out.write(_subheader("Subscribed but never emitted  (possible dead subscribers)"))
        for name in sorted(event_classes["sub_only"]):
            _write_event_block(name, events[name])

    # ── §5  ARCHITECTURE ANALYSIS ──────────────────────────────────────────────
    out.write(_header("§5  ARCHITECTURE ANALYSIS"))

    has_issues = empty_modules or circular_imports or violations
    if not has_issues:
        out.write("  ✅  No architecture issues detected.\n\n")
    else:
        if empty_modules:
            out.write(_subheader("⚠️  Stub / Empty Modules"))
            out.write(
                "  These files have very few substantive lines of code.\n"
                "  They may be placeholders that still need implementing.\n\n"
            )
            for path, lines in empty_modules:
                out.write(f"    • {path}  ({lines} lines)\n")
            out.write("\n")

        if circular_imports:
            out.write(_subheader("🔄  Circular Import Chains"))
            out.write(
                "  These modules import each other in a cycle.\n"
                "  Circular imports can cause import errors and tight coupling.\n\n"
            )
            for cycle in circular_imports:
                out.write(f"    • {' → '.join(cycle)}\n")
            out.write("\n")

        if violations:
            out.write(_subheader("❌  Architecture Rule Violations"))
            out.write(
                "  These imports cross boundaries that should remain independent.\n"
                "  Fix by routing communication through the event bus or service registry.\n\n"
            )
            by_rule: Dict[str, List[ArchitectureViolation]] = defaultdict(list)
            for v in violations:
                by_rule[v.rule].append(v)
            for rule, vs in sorted(by_rule.items()):
                out.write(f"  Rule: {rule}  ({len(vs)} violation(s))\n")
                for v in vs:
                    out.write(f"    ❌  {v.message}\n")
                    out.write(f"         {v.violator}\n")
                    out.write(f"         → {v.target}\n")
                out.write("\n")

    # ── §6  PLUGIN BOUNDARIES ──────────────────────────────────────────────────
    out.write(_header("§6  PLUGIN BOUNDARY MAP"))
    out.write(
        "  Each boundary is an architectural zone.  Outgoing imports cross into\n"
        "  another zone; incoming imports mean other zones depend on this one.\n"
        "  High coupling % = strong interdependence (usually undesirable).\n\n"
    )

    sorted_bounds = sorted(boundaries.items(), key=lambda x: (x[1].is_plugin, x[0]))

    for bname, binfo in sorted_bounds:
        icon     = "🔌" if binfo.is_plugin else "⚙️ "
        internal = len(binfo.internal_imports)
        outgoing = len(binfo.external_imports)
        incoming = len(binfo.incoming_cross)
        total    = internal + outgoing
        coupling = (outgoing + incoming) / total * 100 if total else 0.0

        out.write(f"  {icon}  {bname}\n")
        out.write(f"      Modules   :  {len(binfo.modules)}\n")
        out.write(f"      Internal  :  {internal}  imports within this zone\n")
        out.write(f"      Outgoing  :  {outgoing}  imports into other zones\n")
        out.write(f"      Incoming  :  {incoming}  imports from other zones\n")
        out.write(f"      Coupling  :  {coupling:.1f}%\n")

        if binfo.external_imports:
            # Group by destination boundary
            by_target: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
            module_to_bnd = {
                m: bn
                for bn, bi in boundaries.items()
                for m in bi.modules
            }
            for src, dst in binfo.external_imports:
                target_b = module_to_bnd.get(dst, "?")
                by_target[target_b].append((src, dst))

            out.write(f"      Outgoing breakdown:\n")
            for target_b, imp_list in sorted(by_target.items()):
                out.write(f"        → {target_b}  ({len(imp_list)} import(s))\n")
                for src, dst in sorted(imp_list)[:3]:
                    out.write(f"            {src.split('.')[-1]} → {dst.split('.')[-1]}\n")
                if len(imp_list) > 3:
                    out.write(f"            ... and {len(imp_list)-3} more\n")

        out.write("\n")

    # Boundary summary table
    out.write(_subheader("Boundary Summary Table"))
    out.write(
        f"  {'Boundary':<28}  {'Mod':>4}  {'Int':>5}  {'Out':>5}  "
        f"{'In':>5}  {'Coupling':>8}\n"
    )
    out.write(f"  {'-'*28}  {'-'*4}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*8}\n")
    for bname, binfo in sorted_bounds:
        i = len(binfo.internal_imports)
        o = len(binfo.external_imports)
        c = len(binfo.incoming_cross)
        tot = i + o
        coup = f"{(o+c)/tot*100:.1f}%" if tot else "  —"
        out.write(
            f"  {bname:<28}  {len(binfo.modules):>4}  {i:>5}  "
            f"{o:>5}  {c:>5}  {coup:>8}\n"
        )
    out.write("\n")

    # ── §7  DIRECTORY TREE ─────────────────────────────────────────────────────
    out.write(_header("§7  DIRECTORY TREE"))
    out.write("  (Excluded: .venv, __pycache__, .git, project_exports, and similar)\n\n")
    out.write(f"  {root.resolve().name}/\n")
    for line in build_tree(root):
        out.write(f"  {line}\n")
    out.write("\n")

    # ── §8  DEPENDENCY GRAPH (internal only) ──────────────────────────────────
    out.write(_header("§8  DEPENDENCY GRAPH  (internal modules only)"))
    out.write(
        "  Only project-local imports are shown.  Standard library and third-party\n"
        "  packages are filtered out to keep this section navigable.\n\n"
    )
    internal = internal_deps_only(dependencies)
    if internal:
        for module in sorted(internal):
            out.write(f"  {module}\n")
            for dep in sorted(internal[module]):
                out.write(f"    └─ {dep}\n")
            out.write("\n")
    else:
        out.write("  (no internal module-to-module imports found)\n\n")

    # ── §9  BINARY ASSETS ──────────────────────────────────────────────────────
    out.write(_header("§9  BINARY ASSETS"))
    if binary_files:
        total_bytes = sum(f.stat().st_size for f in binary_files)
        out.write(f"  {len(binary_files)} binary file(s)  "
                  f"·  {human_size(total_bytes)} total\n\n")
        for file in binary_files:
            rel      = file.relative_to(root)
            size     = human_size(file.stat().st_size)
            out.write(f"  {rel}  ({size})\n")
    else:
        out.write("  No binary assets found.\n")
    out.write("\n")

    # ── §10  SOURCE FILES ──────────────────────────────────────────────────────
    if include_source:
        out.write(_header("§10  SOURCE FILES"))
        total_source_bytes = sum(f.stat().st_size for f in text_files)
        out.write(
            f"  {len(text_files)} source file(s)  ·  "
            f"{human_size(total_source_bytes)} total  ·  "
            f"{total_py_lines:,} Python lines\n\n"
        )
        out.write(
            "  Each file begins with a header showing its path, size, and line count.\n"
            "  Python files also show their module-level docstring when present.\n\n"
        )

        for file in text_files:
            rel     = file.relative_to(root)
            content = read_text(file)
            lines   = count_lines(content)
            size    = human_size(file.stat().st_size)

            out.write("\n")
            out.write(_rule("─") + "\n")
            out.write(f"FILE  :  {rel}\n")
            out.write(f"Lines :  {lines}  ·  Size: {size}\n")

            # Show docstring for Python files
            if file.suffix == ".py":
                doc = extract_module_docstring(content)
                if doc:
                    doc_preview = doc[:300].replace("\n", "\n  ")
                    out.write(f"Doc   :  {doc_preview}")
                    if len(doc) > 300:
                        out.write("  ...")
                    out.write("\n")

            out.write(_rule("─") + "\n\n")
            out.write(content)
            if not content.endswith("\n"):
                out.write("\n")

    else:
        out.write(_header("§10  SOURCE FILES"))
        out.write("  (source file contents omitted — run without --no-source to include)\n\n")
        for file in text_files:
            rel  = file.relative_to(root)
            size = human_size(file.stat().st_size)
            out.write(f"  {rel}  ({count_lines(read_text(file))} lines, {size})\n")

    # ── FOOTER ─────────────────────────────────────────────────────────────────
    out.write("\n" + _rule("═") + "\n")
    out.write(f"END OF EXPORT  ·  {project_name}  ·  "
              f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    out.write(_rule("═") + "\n")

    return total_py_lines


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXPORT ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

def export_project(
    root: Path,
    include_source: bool = True,
    write_json: bool = False,
) -> dict:
    """
    Run the full analysis pipeline and write both .txt and .txt.zip exports
    to  <root>/project_exports/ .

    Returns a dict with paths to every file written.
    """
    root = root.resolve()

    # ── Create output directory ────────────────────────────────────────────────
    exports_dir = root / "project_exports"
    exports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name  = f"project_export_{timestamp}"
    txt_path   = exports_dir / f"{base_name}.txt"
    zip_path   = exports_dir / f"{base_name}.txt.zip"
    json_path  = exports_dir / f"{base_name}.json"

    # ── Analysis pipeline ──────────────────────────────────────────────────────
    print("🔍  Scanning project files …")
    text_files, binary_files = scan_project(root)

    print(f"    {len(text_files)} text files  ·  {len(binary_files)} binary files")

    print("🔌  Detecting plugins …")
    plugins = detect_plugins(root, text_files)
    print(f"    {len(plugins)} plugin(s) found")

    print("📡  Mapping event bus …")
    events = analyze_events(root, text_files)
    print(f"    {len(events)} event type(s) detected")

    print("🔗  Analyzing dependencies …")
    dependencies = analyze_dependencies(root, text_files)

    print("⚠️   Detecting stub modules …")
    empty_modules = detect_empty_modules(root, text_files)

    print("🔄  Detecting circular imports …")
    circular_imports = detect_circular_imports(dependencies)

    print("🏗️   Validating architecture …")
    violations = validate_architecture(root, dependencies, plugins)

    print("🗺️   Mapping plugin boundaries …")
    boundaries = build_boundaries(root, dependencies, plugins)

    print("📋  Building plugin catalog …")
    plugin_catalog = build_plugin_catalog(root, plugins, events, text_files)

    print("🏥  Computing health score …")
    health_score, health_findings = compute_health(
        violations, circular_imports, empty_modules, events
    )

    # ── Write .txt ─────────────────────────────────────────────────────────────
    print(f"\n📝  Writing text export …")
    with open(txt_path, "w", encoding="utf-8") as f:
        total_lines = write_text_export(
            f, root, text_files, binary_files, dependencies,
            plugins, events, empty_modules, circular_imports, violations,
            boundaries, plugin_catalog, health_score, health_findings,
            include_source=include_source,
        )
    txt_size = human_size(txt_path.stat().st_size)
    print(f"    Written: {txt_path.name}  ({txt_size})")

    # ── Write .zip ─────────────────────────────────────────────────────────────
    print(f"🗜️   Compressing …")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        zf.write(txt_path, arcname=txt_path.name)
    zip_size = human_size(zip_path.stat().st_size)
    ratio    = (1 - zip_path.stat().st_size / txt_path.stat().st_size) * 100
    print(f"    Written: {zip_path.name}  ({zip_size}, {ratio:.0f}% smaller)")

    # ── Write .json (optional) ─────────────────────────────────────────────────
    if write_json:
        print(f"🔧  Writing JSON export …")
        json_data = build_json_export(
            root, text_files, binary_files, dependencies, plugins, events,
            empty_modules, circular_imports, violations, boundaries,
            plugin_catalog, health_score,
        )
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        print(f"    Written: {json_path.name}  ({human_size(json_path.stat().st_size)})")

    # ── Console summary ────────────────────────────────────────────────────────
    print("\n" + "═" * 50)
    print("✅  Export complete!")
    print("═" * 50)
    print(f"  Project      :  {root.name}")
    print(f"  Health score :  {health_score}/100  —  {health_grade(health_score)}")
    print(f"  Source files :  {len(text_files)}")
    print(f"  Python lines :  {total_lines:,}")
    print(f"  Binary assets:  {len(binary_files)}")
    print(f"  Plugins      :  {len(plugins)}")
    print(f"  Events       :  {len(events)}")
    if empty_modules:
        print(f"  ⚠️  Stubs      :  {len(empty_modules)} stub/empty module(s)")
    if circular_imports:
        print(f"  🔄 Circular   :  {len(circular_imports)} import cycle(s)")
    if violations:
        print(f"  ❌ Violations :  {len(violations)} architecture issue(s)")

    print(f"\n  Output folder:  {exports_dir}")
    print(f"  Text report  :  {txt_path.name}")
    print(f"  Compressed   :  {zip_path.name}")
    if write_json:
        print(f"  JSON data    :  {json_path.name}")
    print()

    return {
        "txt":  txt_path,
        "zip":  zip_path,
        "json": json_path if write_json else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Project Exporter Pro  ·  Architecture Intelligence System\n\n"
            "Generates a complete human-readable export of any Python project\n"
            "plus a compressed copy.  Output goes into project_exports/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--root",
        default=".",
        metavar="DIR",
        help="Project root directory  (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also write a structured JSON export alongside the text report",
    )
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="Omit raw source file contents from the report (faster, smaller output)",
    )

    args = parser.parse_args()

    export_project(
        root           = Path(args.root),
        include_source = not args.no_source,
        write_json     = args.json,
    )
