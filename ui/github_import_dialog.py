"""
GitHub Import Dialog

Browse a public GitHub repository and download content directly into Adeptus Craftmatica:
  - JSON files  → game_system_data/<system>/ (game rules, monsters, spells…)
  - CSV files   → paint tracker  (community paint lists)

Uses only Python stdlib (urllib) + certifi — no requests dependency.
Downloads run in a daemon thread so the UI stays responsive.
"""
from __future__ import annotations

import base64
import csv
import datetime
import io
import json
import os
import re
import ssl
import threading
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def _ssl_context() -> ssl.SSLContext:
    """Return an SSL context with verified certs on all platforms."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

from PySide6.QtCore import Qt, Signal, QObject, QSignalBlocker
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
    QProgressBar, QMessageBox, QFrame, QGroupBox,
    QSizePolicy, QStackedWidget, QWidget,
    QScrollArea, QInputDialog,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.parent
_DATA_ROOT    = _PROJECT_ROOT / "game_system_data"

# ── GitHub API helpers ────────────────────────────────────────────────────────

_API_CONTENTS = "https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
_RAW_URL      = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"
_USER_AGENT   = "AdeptusCraftmatica/1.0"

# ── Preset repositories ───────────────────────────────────────────────────────

PRESET_REPOS: list[tuple[str, str]] = [
    ("— choose a preset —",                       ""),
    ("D&D 5e Data  (bagelbits/5e-database)",       "bagelbits/5e-database"),
    ("D&D 5e SRD   (5e-bits/5e-database)",         "5e-bits/5e-database"),
    ("Warhammer 40k Data  (Hoplite-Research/40k)", "Hoplite-Research/40kdata"),
    ("Custom…",                                    "__custom__"),
]

# Extensions we know how to import
_IMPORTABLE_EXT = {".json", ".csv"}

# ── Known game-system folder mapping ─────────────────────────────────────────

_SYSTEM_PRESETS: list[str] = [
    "D&D 5e",
    "Pathfinder 2e",
    "Warhammer 40k",
    "Age of Sigmar",
    "Community",
]

# Map preset display names to folder slugs; anything else gets auto-slugified
_SYSTEM_SLUG_MAP = {
    "D&D 5e":        "dungeons_and_dragons",
    "Pathfinder 2e": "pathfinder_2e",
    "Warhammer 40k": "warhammer_40k",
    "Age of Sigmar": "age_of_sigmar",
    "Community":     "community",
}


def _slugify(text: str) -> str:
    """Convert a display name to a safe folder slug."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text or "custom"


# ── Signal bridge (cross-thread → Qt main thread) ────────────────────────────

class _WorkerSignals(QObject):
    progress = Signal(str)        # status string
    done     = Signal(object)     # list[dict] | dict | Exception


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


class _ImportResultDialog(QDialog):
    """Scrollable import result dialog — replaces QMessageBox for large file lists."""

    def __init__(self, successes: list, errors: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Complete")
        self.setMinimumSize(500, 300)
        self.resize(600, 420)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # Summary line
        parts = []
        if successes:
            parts.append(f"✓  {len(successes)} file{'s' if len(successes) != 1 else ''} imported")
        if errors:
            parts.append(f"✗  {len(errors)} error{'s' if len(errors) != 1 else ''}")
        summary_lbl = QLabel("  ·  ".join(parts))
        summary_lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        lay.addWidget(summary_lbl)

        # Scrollable detail area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        detail_widget = QWidget()
        detail_lay = QVBoxLayout(detail_widget)
        detail_lay.setContentsMargins(4, 4, 4, 4)
        detail_lay.setSpacing(2)

        if successes:
            hdr = QLabel(f"Imported ({len(successes)}):")
            hdr.setStyleSheet("font-weight: 600; color: #3dba5f;")
            detail_lay.addWidget(hdr)
            for name, detail in successes:
                lbl = QLabel(f"  {name}  <span style='color:#686868'>{detail}</span>")
                lbl.setTextFormat(Qt.RichText)
                lbl.setWordWrap(True)
                detail_lay.addWidget(lbl)

        if errors:
            if successes:
                detail_lay.addSpacing(8)
            hdr = QLabel(f"Errors ({len(errors)}):")
            hdr.setStyleSheet("font-weight: 600; color: #d94f4f;")
            detail_lay.addWidget(hdr)
            for name, detail in errors:
                lbl = QLabel(f"  {name}  <span style='color:#d94f4f'>{detail}</span>")
                lbl.setTextFormat(Qt.RichText)
                lbl.setWordWrap(True)
                detail_lay.addWidget(lbl)

        detail_lay.addStretch()
        scroll.setWidget(detail_widget)
        lay.addWidget(scroll, stretch=1)

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.setMinimumWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)


# ── Main dialog ───────────────────────────────────────────────────────────────

class GitHubImportDialog(QDialog):
    """
    Two-phase dialog:
      1. Fetch — walk a repo via GitHub API and list importable files.
      2. Import — download checked files and save / inject them.
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx       = context
        self._signals   = _WorkerSignals()
        self._repo      = ""
        self._branch    = "HEAD"
        self._all_files: list[dict] = []
        self._importing = False
        self._last_json_dest: Path | None = None   # for "Open Folder" button

        self.setWindowTitle("GitHub Import")
        self.setMinimumSize(760, 600)
        self.resize(920, 700)
        self._build_ui()
        self._connect_signals()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        # ── Title ─────────────────────────────────────────────────────────────
        title = QLabel("GitHub Import")
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        sub = QLabel(
            "Browse any public GitHub repository and download game data (JSON) "
            "or paint lists (CSV) directly into the app."
        )
        sub.setObjectName("fieldLabel")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addWidget(_hline())

        # ── Repository group ──────────────────────────────────────────────────
        repo_box = QGroupBox("Repository")
        repo_form = QFormLayout(repo_box)
        repo_form.setContentsMargins(12, 10, 12, 12)
        repo_form.setHorizontalSpacing(10)
        repo_form.setVerticalSpacing(8)
        repo_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Preset row
        self._preset_combo = QComboBox()
        self._preset_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for label, _ in PRESET_REPOS:
            self._preset_combo.addItem(label)
        repo_form.addRow("Preset:", self._preset_combo)

        # Manual repo URL row  (input + Fetch button side by side)
        repo_input_row = QHBoxLayout()
        repo_input_row.setSpacing(8)
        self._repo_input = QLineEdit()
        self._repo_input.setPlaceholderText("owner/repo  or  https://github.com/owner/repo")
        repo_input_row.addWidget(self._repo_input, stretch=1)
        self._fetch_btn = QPushButton("⟳  Fetch Files")
        self._fetch_btn.setProperty("class", "primary")
        self._fetch_btn.setMinimumWidth(120)
        repo_input_row.addWidget(self._fetch_btn)
        repo_form.addRow("Repository:", repo_input_row)

        # Branch row
        self._branch_input = QLineEdit()
        self._branch_input.setPlaceholderText("main  (leave blank to use the repo's default branch)")
        self._branch_input.setMaximumWidth(260)
        repo_form.addRow("Branch:", self._branch_input)

        # Game-system / destination folder row
        system_row = QHBoxLayout()
        system_row.setSpacing(6)

        self._system_combo = QComboBox()
        self._system_combo.setEditable(True)
        self._system_combo.setInsertPolicy(QComboBox.NoInsert)
        self._system_combo.setToolTip(
            "Pick a preset, select an existing folder, or type any name.\n"
            "JSON files will be saved to  game_system_data/<folder>/.\n"
            "Use 'New folder…' to create a brand-new subfolder."
        )
        self._system_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._populate_folder_combo()          # presets + existing on-disk folders
        system_row.addWidget(self._system_combo, stretch=1)

        new_folder_btn = QPushButton("📁 New folder…")
        new_folder_btn.setToolTip("Create a new destination subfolder")
        new_folder_btn.setFixedHeight(self._system_combo.sizeHint().height())
        new_folder_btn.clicked.connect(self._on_new_folder)
        system_row.addWidget(new_folder_btn)

        self._dest_lbl = QLabel()
        self._dest_lbl.setObjectName("fieldLabel")
        self._dest_lbl.setAlignment(Qt.AlignVCenter)
        system_row.addWidget(self._dest_lbl)
        self._refresh_dest_label()
        repo_form.addRow("Save to folder:", system_row)

        lay.addWidget(repo_box)

        # ── File browser group ────────────────────────────────────────────────
        browser_box = QGroupBox("Available Files")
        browser_lay = QVBoxLayout(browser_box)
        browser_lay.setContentsMargins(12, 10, 12, 12)
        browser_lay.setSpacing(8)

        # Filter bar
        f_row = QHBoxLayout()
        f_row.setSpacing(8)
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Search files…")
        self._filter_input.setClearButtonEnabled(True)
        f_row.addWidget(self._filter_input, stretch=1)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["All Types", "JSON  (Game Data)", "CSV  (Paint List)"])
        self._type_combo.setMinimumWidth(160)
        f_row.addWidget(self._type_combo)
        browser_lay.addLayout(f_row)

        # Stacked: empty-state label OR tree
        self._file_stack = QStackedWidget()

        # Page 0 — empty / loading state
        self._empty_lbl = QLabel(
            "Enter a repository above and click  ⟳ Fetch Files  to browse its contents."
        )
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setObjectName("fieldLabel")
        self._empty_lbl.setWordWrap(True)
        self._file_stack.addWidget(self._empty_lbl)

        # Page 1 — file tree
        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["File Path", "Import As", "Size"])
        h = self._tree.header()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setUniformRowHeights(True)
        # Use SingleSelection so the user can arrow-key through rows;
        # checking is driven by our itemClicked handler, not row-selection.
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.setToolTip("Click a row to check / uncheck it. Space toggles the selected row.")
        self._file_stack.addWidget(self._tree)

        self._file_stack.setCurrentIndex(0)
        browser_lay.addWidget(self._file_stack, stretch=1)

        # Selection controls row
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        self._sel_all_btn  = QPushButton("✓  Select All")
        self._sel_all_btn.setMinimumWidth(110)
        self._sel_none_btn = QPushButton("✗  Select None")
        self._sel_none_btn.setMinimumWidth(110)
        self._sel_all_btn.setEnabled(False)
        self._sel_none_btn.setEnabled(False)
        self._sel_lbl = QLabel("")
        self._sel_lbl.setObjectName("fieldLabel")
        sel_row.addWidget(self._sel_all_btn)
        sel_row.addWidget(self._sel_none_btn)
        sel_row.addStretch()
        sel_row.addWidget(self._sel_lbl)
        browser_lay.addLayout(sel_row)

        lay.addWidget(browser_box, stretch=1)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status_lbl = QLabel(
            "Choose a preset or enter a repository path, then click  ⟳ Fetch Files."
        )
        self._status_lbl.setObjectName("fieldLabel")
        self._status_lbl.setWordWrap(True)
        lay.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setMaximumHeight(5)
        self._progress.setVisible(False)
        lay.addWidget(self._progress)

        # ── Bottom action row ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._open_folder_btn = QPushButton("📂  Open Import Folder")
        self._open_folder_btn.setVisible(False)
        self._open_folder_btn.setToolTip("Open the folder where JSON files were saved")
        btn_row.addWidget(self._open_folder_btn)

        self._community_btn = QPushButton("🌐  Community Library")
        self._community_btn.setToolTip(
            "Upload your collection to the community library, or download the latest merged data"
        )
        btn_row.addWidget(self._community_btn)

        btn_row.addStretch()

        self._import_btn = QPushButton("⬇  Import Selected")
        self._import_btn.setProperty("class", "primary")
        self._import_btn.setMinimumWidth(150)
        self._import_btn.setEnabled(False)

        self._close_btn = QPushButton("Close")
        self._close_btn.setMinimumWidth(80)

        btn_row.addWidget(self._import_btn)
        btn_row.addWidget(self._close_btn)
        lay.addLayout(btn_row)

    def _connect_signals(self):
        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self._fetch_btn.clicked.connect(self._start_fetch)
        self._repo_input.returnPressed.connect(self._start_fetch)
        self._branch_input.returnPressed.connect(self._start_fetch)
        self._filter_input.textChanged.connect(self._apply_filter)
        self._type_combo.currentTextChanged.connect(self._apply_filter)
        self._sel_all_btn.clicked.connect(self._select_all)
        self._sel_none_btn.clicked.connect(self._select_none)
        # itemChanged fires when the checkbox indicator is clicked directly.
        # itemClicked fires for all row clicks.  Both are needed — see handlers.
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._import_btn.clicked.connect(self._start_import)
        self._close_btn.clicked.connect(self.accept)
        self._open_folder_btn.clicked.connect(self._open_import_folder)
        self._community_btn.clicked.connect(self._open_community_dialog)
        self._system_combo.currentTextChanged.connect(self._on_system_changed)
        self._signals.progress.connect(self._on_progress)
        self._signals.done.connect(self._on_done)
        # Internal flag: itemChanged fires before itemClicked when the indicator
        # itself is clicked, so we use this to avoid double-toggling.
        self._indicator_just_toggled: bool = False

    # ── System folder helpers ─────────────────────────────────────────────────

    def _current_folder(self) -> str:
        # If the combo has stored userData (an on-disk folder name), use it directly
        idx = self._system_combo.currentIndex()
        user_data = self._system_combo.itemData(idx) if idx >= 0 else None
        if user_data:
            return str(user_data)
        text = self._system_combo.currentText().strip().lstrip("📂").strip()
        return _SYSTEM_SLUG_MAP.get(text) or _slugify(text) or "custom"

    def _refresh_dest_label(self):
        folder = self._current_folder()
        self._dest_lbl.setText(f"→  game_system_data/{folder}/")

    def _on_system_changed(self, _text: str):
        self._refresh_dest_label()

    def _populate_folder_combo(self):
        """Fill the combo with preset names + any existing on-disk subfolders."""
        with QSignalBlocker(self._system_combo):
            self._system_combo.clear()
            self._system_combo.addItems(_SYSTEM_PRESETS)

            # Add a separator then any already-created subfolders
            existing = sorted(
                p.name for p in _DATA_ROOT.iterdir() if p.is_dir()
            ) if _DATA_ROOT.exists() else []
            # Map known presets to their slugs to avoid duplication
            preset_slugs = set(_SYSTEM_SLUG_MAP.values())
            novel = [d for d in existing if d not in preset_slugs and d not in _SYSTEM_PRESETS]
            if novel:
                self._system_combo.insertSeparator(self._system_combo.count())
                for folder in novel:
                    self._system_combo.addItem(f"📂 {folder}", userData=folder)

            self._system_combo.setCurrentText("Community")

    def _on_new_folder(self):
        """Prompt for a new folder name and select it."""
        text, ok = QInputDialog.getText(
            self,
            "New Destination Folder",
            "Folder name (will be created under game_system_data/):\n"
            "Tip: use short names like  skaven  or  old_world",
        )
        if not ok or not text.strip():
            return
        folder_name = _slugify(text.strip())
        if not folder_name:
            QMessageBox.warning(self, "Invalid Name", "The name must contain at least one letter or digit.")
            return
        # Create the folder now so it appears in future lists
        ((_DATA_ROOT / folder_name).mkdir(parents=True, exist_ok=True))
        # Re-populate and select the new folder
        self._populate_folder_combo()
        self._system_combo.setCurrentText(folder_name)
        self._refresh_dest_label()

    # ── Preset ────────────────────────────────────────────────────────────────

    def _on_preset_changed(self, idx: int):
        _, slug = PRESET_REPOS[idx]
        if slug in ("__custom__", ""):
            if slug == "__custom__":
                self._repo_input.setFocus()
            return
        with QSignalBlocker(self._repo_input):
            self._repo_input.setText(slug)
        self._start_fetch()

    # ── Fetch phase ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_repo(text: str) -> str:
        text = text.strip().rstrip("/")
        for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        return text

    def _start_fetch(self):
        if self._importing:
            return
        repo = self._parse_repo(self._repo_input.text())
        if not repo or "/" not in repo:
            QMessageBox.warning(
                self, "Invalid Repository",
                "Enter a valid repository in  owner/repo  format.\n\n"
                "Examples:\n  bagelbits/5e-database\n  https://github.com/owner/repo"
            )
            return
        self._repo   = repo
        self._branch = self._branch_input.text().strip() or "HEAD"
        self._tree.clear()
        self._all_files = []
        self._file_stack.setCurrentIndex(0)
        branch_label = "" if self._branch == "HEAD" else f"  [{self._branch}]"
        self._empty_lbl.setText(f"Scanning {repo}{branch_label}…")
        self._sel_all_btn.setEnabled(False)
        self._sel_none_btn.setEnabled(False)
        self._open_folder_btn.setVisible(False)
        self._set_busy(True, f"Connecting to GitHub API for  {repo}{branch_label} …")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            files = self._walk_repo(self._repo, "", self._branch)
            self._signals.done.emit(files)
        except Exception as exc:
            self._signals.done.emit(exc)

    def _walk_repo(self, repo: str, path: str, branch: str) -> list[dict]:
        url = _API_CONTENTS.format(repo=repo, path=path, branch=branch)
        req = Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/vnd.github.v3+json",
        })
        with urlopen(req, timeout=15, context=_ssl_context()) as resp:
            entries = json.load(resp)

        if not isinstance(entries, list):
            return []

        files = []
        for entry in entries:
            etype = entry.get("type", "")
            name  = entry.get("name", "")
            epath = entry.get("path", "")

            if etype == "file":
                ext = Path(name).suffix.lower()
                if ext not in _IMPORTABLE_EXT:
                    continue
                import_as = "Game Data (JSON)" if ext == ".json" else "Paint List (CSV)"
                files.append({
                    "name":         name,
                    "path":         epath,
                    "size":         entry.get("size", 0),
                    "ext":          ext,
                    "import_as":    import_as,
                    "download_url": (entry.get("download_url") or
                                     _RAW_URL.format(repo=repo, branch=branch, path=epath)),
                })
            elif etype == "dir":
                self._signals.progress.emit(f"Scanning  {epath}/…")
                try:
                    files.extend(self._walk_repo(repo, epath, branch))
                except Exception:
                    pass  # skip inaccessible subdirectories

        return files

    # ── File tree ─────────────────────────────────────────────────────────────

    def _apply_filter(self):
        query    = self._filter_input.text().lower()
        type_flt = self._type_combo.currentText()

        self._tree.blockSignals(True)
        self._tree.clear()

        for f in self._all_files:
            if query and query not in f["path"].lower():
                continue
            if "JSON" in type_flt and f["ext"] != ".json":
                continue
            if "CSV" in type_flt and f["ext"] != ".csv":
                continue

            item = QTreeWidgetItem([f["path"], f["import_as"], self._fmt_size(f["size"])])
            item.setCheckState(0, Qt.Unchecked)
            item.setData(0, Qt.UserRole, f)
            item.setToolTip(0, f["path"])
            self._tree.addTopLevelItem(item)

        self._tree.blockSignals(False)
        self._refresh_sel_label()

    @staticmethod
    def _fmt_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024 ** 2:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024 ** 2:.1f} MB"

    def _select_all(self):
        self._tree.blockSignals(True)
        for i in range(self._tree.topLevelItemCount()):
            self._tree.topLevelItem(i).setCheckState(0, Qt.Checked)
        self._tree.blockSignals(False)
        self._refresh_sel_label()

    def _select_none(self):
        self._tree.blockSignals(True)
        for i in range(self._tree.topLevelItemCount()):
            self._tree.topLevelItem(i).setCheckState(0, Qt.Unchecked)
        self._tree.blockSignals(False)
        self._refresh_sel_label()

    def _on_item_changed(self, _item, _col):
        """Fires when the checkbox indicator is clicked directly by Qt."""
        # Set a flag so _on_item_clicked knows the state is already correct
        # and should NOT toggle again (Qt fires itemChanged before itemClicked).
        self._indicator_just_toggled = True
        self._refresh_sel_label()

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int):
        """Fires for ANY row click.  Toggle the checkbox unless Qt already did it."""
        if self._indicator_just_toggled:
            # The indicator itself was clicked — Qt already toggled; skip.
            self._indicator_just_toggled = False
            return
        # User clicked the row text or any column other than the indicator —
        # toggle the checkbox manually.
        self._toggle_item(item)

    def _toggle_item(self, item: QTreeWidgetItem):
        """Flip an item's check state and refresh the selection count."""
        with QSignalBlocker(self._tree):
            new_state = (
                Qt.Unchecked if item.checkState(0) == Qt.Checked else Qt.Checked
            )
            item.setCheckState(0, new_state)
        self._refresh_sel_label()

    def keyPressEvent(self, event):
        """Space bar toggles the currently selected tree row."""
        if (
            event.key() == Qt.Key_Space
            and self._file_stack.currentIndex() == 1  # tree is visible
        ):
            item = self._tree.currentItem()
            if item:
                self._toggle_item(item)
                event.accept()
                return
        super().keyPressEvent(event)

    def _refresh_sel_label(self):
        total   = self._tree.topLevelItemCount()
        checked = len(self._checked_files())

        if total > 0:
            self._sel_lbl.setText(f"{checked} of {total} selected")
        else:
            self._sel_lbl.setText("")

        self._import_btn.setEnabled(checked > 0)

    def _checked_files(self) -> list[dict]:
        out = []
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                out.append(item.data(0, Qt.UserRole))
        return out

    # ── Import phase ──────────────────────────────────────────────────────────

    def _start_import(self):
        files = self._checked_files()
        if not files:
            return

        # Warn if the folder slug will be auto-generated
        folder = self._current_folder()
        system_text = self._system_combo.currentText().strip()
        if system_text not in _SYSTEM_SLUG_MAP and any(f["ext"] == ".json" for f in files):
            reply = QMessageBox.question(
                self, "Confirm Custom Game System",
                f"JSON files will be saved to:\n\n"
                f"  game_system_data/{folder}/\n\n"
                f"Continue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._importing = True
        self._last_json_dest = None
        self._set_busy(True, f"Importing {len(files)} file(s)…")
        threading.Thread(
            target=self._import_worker, args=(files, folder), daemon=True
        ).start()

    def _import_worker(self, files: list[dict], folder: str):
        successes, errors = [], []
        for f in files:
            try:
                self._signals.progress.emit(f"Downloading  {f['name']}…")
                if f["ext"] == ".json":
                    dest = self._import_json(f, folder)
                    successes.append((f["name"], f"→ {dest}"))
                elif f["ext"] == ".csv":
                    count = self._import_csv(f)
                    successes.append((f["name"], f"→ {count} paints added"))
            except Exception as exc:
                errors.append((f["name"], str(exc)))

        self._signals.done.emit({"successes": successes, "errors": errors})

    # ── Per-type importers ────────────────────────────────────────────────────

    def _download(self, url: str) -> bytes:
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=30, context=_ssl_context()) as resp:
            return resp.read()

    def _import_json(self, f: dict, folder: str) -> str:
        """Download a JSON file into game_system_data/<folder>/."""
        raw = self._download(f["download_url"])
        json.loads(raw)   # validate — raises on invalid JSON

        dest_dir = _DATA_ROOT / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f["name"]
        dest.write_bytes(raw)

        # Remember the last destination so "Open Folder" works
        self._last_json_dest = dest_dir

        # Invalidate GameDataLoader cache so the file is picked up immediately
        try:
            from plugins.campaign_tracker.game_data import GameDataLoader
            GameDataLoader._cache.clear()
        except Exception:
            pass

        return str(dest.relative_to(_PROJECT_ROOT))

    def _import_csv(self, f: dict) -> int:
        """Download a CSV and bulk-import paints into PaintService."""
        raw  = self._download(f["download_url"])
        text = raw.decode("utf-8-sig", errors="replace")

        svc = self._ctx.services.try_get("paint_service")
        if not svc:
            raise RuntimeError(
                "Paint Tracker service is not available.\n"
                "Make sure the Paint Tracker plugin is enabled."
            )

        reader = csv.DictReader(io.StringIO(text))
        count  = 0
        for row in reader:
            norm  = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
            brand = norm.get("brand", "")
            name  = norm.get("name", "")
            if not brand or not name:
                continue
            color = norm.get("color") or norm.get("colour") or "#808080"
            if not (color.startswith("#") and len(color) == 7):
                color = "#808080"
            try:
                qty = max(0, int(norm.get("quantity") or norm.get("qty") or "1"))
            except ValueError:
                qty = 1
            try:
                svc.add_paint(
                    brand=brand,
                    name=name,
                    paint_type=norm.get("type") or norm.get("paint_type") or "Base",
                    color=color,
                    quantity=qty,
                    level=norm.get("level") or None,
                    notes=norm.get("notes") or None,
                )
                count += 1
            except Exception:
                pass  # skip duplicates / validation errors

        if count == 0:
            raise RuntimeError(
                "No valid rows found — check the CSV has  Brand  and  Name  columns."
            )
        return count

    # ── Response handlers ─────────────────────────────────────────────────────

    def _on_progress(self, msg: str):
        self._status_lbl.setText(msg)

    def _on_done(self, result):
        self._set_busy(False, "")

        # ── Fetch result ──────────────────────────────────────────────────────
        if isinstance(result, list):
            self._all_files = result
            self._apply_filter()
            n = len(result)
            if n == 0:
                self._empty_lbl.setText(
                    "No importable files found (.json / .csv).\n\n"
                    "Check the repository URL, or try a different repo."
                )
                self._file_stack.setCurrentIndex(0)
                self._status_lbl.setText("No importable files found in this repository.")
            else:
                json_count = sum(1 for f in result if f["ext"] == ".json")
                csv_count  = sum(1 for f in result if f["ext"] == ".csv")
                parts = []
                if json_count:
                    parts.append(f"{json_count} JSON")
                if csv_count:
                    parts.append(f"{csv_count} CSV")
                self._file_stack.setCurrentIndex(1)
                self._sel_all_btn.setEnabled(True)
                self._sel_none_btn.setEnabled(True)
                self._status_lbl.setText(
                    f"Found {n} importable file{'s' if n != 1 else ''} "
                    f"({', '.join(parts)}).  Check the ones you want, then click  ⬇ Import Selected."
                )
            return

        # ── Fetch error ───────────────────────────────────────────────────────
        if isinstance(result, Exception):
            self._empty_lbl.setText(
                "Could not fetch the repository.\n\nCheck the URL and try again."
            )
            self._file_stack.setCurrentIndex(0)
            msg = str(result)
            if isinstance(result, HTTPError):
                if result.code == 403:
                    msg = (
                        "GitHub API rate limit reached.\n\n"
                        "Wait a minute and try again. "
                        "Unauthenticated requests are limited to 60 per hour."
                    )
                elif result.code == 404:
                    msg = (
                        "Repository not found.\n\n"
                        "Check the owner/repo spelling and make sure the repo is public."
                    )
            elif isinstance(result, URLError):
                reason = str(result.reason)
                if "certificate" in reason.lower() or "ssl" in reason.lower():
                    msg = (
                        f"SSL certificate error: {reason}\n\n"
                        "Try running:  pip install --upgrade certifi\n"
                        "in the project virtual environment."
                    )
                else:
                    msg = (
                        f"Network error: {reason}\n\n"
                        "Check your internet connection and try again."
                    )
            self._status_lbl.setText(f"⚠ Fetch failed — {msg.splitlines()[0]}")
            QMessageBox.critical(self, "Fetch Failed", msg)
            return

        # ── Import result ─────────────────────────────────────────────────────
        if isinstance(result, dict):
            self._importing = False
            successes = result.get("successes", [])   # list[(name, detail)]
            errors    = result.get("errors",    [])   # list[(name, detail)]

            # Scrollable result dialog — replaces QMessageBox for large file lists
            _ImportResultDialog(successes, errors, parent=self).exec()

            done_parts = []
            if successes:
                done_parts.append(f"{len(successes)} imported")
            if errors:
                done_parts.append(f"{len(errors)} errors")
            self._status_lbl.setText("Done — " + ", ".join(done_parts) + ".")

            # Re-populate folder combo so a newly-created folder appears
            self._populate_folder_combo()
            self._system_combo.setCurrentText(self._current_folder())
            self._refresh_dest_label()

            # Show "Open Folder" if any JSON was saved
            if self._last_json_dest is not None:
                self._open_folder_btn.setToolTip(f"Open  {self._last_json_dest}")
                self._open_folder_btn.setVisible(True)

            # Notify the event bus so plugins can refresh their data
            try:
                if any(f["ext"] == ".csv" for f in self._checked_files()):
                    self._ctx.event_bus.emit("paints_filter_changed", {"filter": None})
            except Exception:
                pass

    # ── Open folder ───────────────────────────────────────────────────────────

    def _open_import_folder(self):
        if self._last_json_dest and self._last_json_dest.exists():
            # Cross-platform folder open
            import subprocess, sys
            if sys.platform == "win32":
                os.startfile(str(self._last_json_dest))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self._last_json_dest)])
            else:
                subprocess.Popen(["xdg-open", str(self._last_json_dest)])
        else:
            QMessageBox.information(
                self, "Folder Not Found",
                "The import folder could not be located.\n\n"
                f"Expected: {self._last_json_dest}"
            )

    def _open_community_dialog(self):
        dlg = CommunityLibraryDialog(self._ctx, parent=self)
        dlg.exec()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool, msg: str):
        self._progress.setVisible(busy)
        self._fetch_btn.setEnabled(not busy)
        self._import_btn.setEnabled(not busy and len(self._checked_files()) > 0)
        if msg:
            self._status_lbl.setText(msg)
        if not busy:
            self._refresh_sel_label()


# ══════════════════════════════════════════════════════════════════════════════
# Community Library
# ══════════════════════════════════════════════════════════════════════════════

_COMMUNITY_REPO   = "adeptus-craftmatica/adeptus-craftmatica"
_COMMUNITY_BRANCH = "living-library"

# CSV column schemas
_PAINT_HEADERS    = ["brand", "name", "type", "color"]
_MATERIAL_HEADERS = ["name", "type", "brand", "color"]
_TOOL_HEADERS     = ["name", "type", "brand"]
_MODEL_HEADERS    = ["name", "game_system", "faction", "type", "scale"]

# (svc_key, display_label, filename, csv_headers, getter_method_name)
_UPLOAD_PLUGINS = [
    ("paint_service",    "Paint Tracker",     "paints.csv",    _PAINT_HEADERS,    "get_all_paints"),
    ("material_service", "Materials Tracker", "materials.csv", _MATERIAL_HEADERS, "get_all_materials"),
    ("tool_service",     "Tool Tracker",      "tools.csv",     _TOOL_HEADERS,     "get_all_tools"),
    ("model_service",    "Model Tracker",     "models.csv",    _MODEL_HEADERS,    "get_all_models"),
]


def _to_csv(headers: list, rows: list) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _plugin_to_rows(svc_key: str, items: list) -> list:
    if svc_key == "paint_service":
        return [{"brand": p.brand, "name": p.name, "type": p.paint_type, "color": p.color}
                for p in items]
    if svc_key == "material_service":
        return [{"name": m.name, "type": m.material_type, "brand": m.brand, "color": m.color}
                for m in items]
    if svc_key == "tool_service":
        return [{"name": t.name, "type": t.tool_type, "brand": t.brand}
                for t in items]
    if svc_key == "model_service":
        return [{"name": m.name, "game_system": m.game_system, "faction": m.faction,
                 "type": m.model_type, "scale": m.scale or ""}
                for m in items]
    return []


def _gh_get_sha(repo: str, path: str, branch: str, token: str):
    """Return the SHA of an existing file, or None if it doesn't exist."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    req = Request(url, headers={
        "User-Agent":    _USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github.v3+json",
    })
    try:
        with urlopen(req, context=_ssl_context(), timeout=15) as resp:
            return json.load(resp).get("sha")
    except HTTPError as e:
        if e.code == 404:
            return None
        raise


def _gh_put_file(repo: str, path: str, content: str, message: str, branch: str, token: str):
    """Create or update a file via the GitHub Contents API."""
    sha = _gh_get_sha(repo, path, branch, token)
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    body: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch":  branch,
    }
    if sha:
        body["sha"] = sha
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method="PUT", headers={
        "User-Agent":    _USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github.v3+json",
        "Content-Type":  "application/json",
    })
    with urlopen(req, context=_ssl_context(), timeout=30) as resp:
        return json.load(resp)


# ── Key normalisation (matches merge script logic) ────────────────────────────

def _norm_key(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"\s+", " ", s)


def _existing_lookup(svc_key: str, ctx) -> dict:
    """
    Build {dedup_key: existing_values_dict} from the local service.
    Called on the main thread before spawning the download worker.
    """
    svc = ctx.services.try_get(svc_key) if ctx else None
    if not svc:
        return {}
    getter = {
        "paint_service":    "get_all_paints",
        "material_service": "get_all_materials",
        "tool_service":     "get_all_tools",
        "model_service":    "get_all_models",
    }.get(svc_key)
    if not getter:
        return {}
    try:
        items = getattr(svc, getter)()
    except Exception:
        return {}

    out = {}
    for item in items:
        if svc_key == "paint_service":
            k = (_norm_key(item.brand), _norm_key(item.name))
            out[k] = {"color": getattr(item, "color", "")}
        elif svc_key == "material_service":
            k = (_norm_key(item.name), _norm_key(item.brand))
            out[k] = {"color": getattr(item, "color", "")}
        elif svc_key == "tool_service":
            k = (_norm_key(item.name), _norm_key(item.brand))
            out[k] = {}
        elif svc_key == "model_service":
            k = (_norm_key(item.name), _norm_key(item.game_system))
            out[k] = {"faction": getattr(item, "faction", "")}
    return out


# ── Import Result Dialog ──────────────────────────────────────────────────────

class _ImportResultDialog(QDialog):
    """Structured summary shown after 'Get Latest Community Data'."""

    def __init__(self, stats: dict, parent=None):
        """
        stats: {label: {"imported": int, "skipped": int, "errors": int,
                         "conflicts": list[dict], "status": "ok"|"skip"|"error",
                         "detail": str}}
        """
        super().__init__(parent)
        self.setWindowTitle("Import Complete")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build(stats)

    def _build(self, stats: dict):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        title = QLabel("Import Complete")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        root.addWidget(title)

        all_conflicts = []

        for label, s in stats.items():
            status   = s.get("status", "ok")
            imported = s.get("imported", 0)
            skipped  = s.get("skipped", 0)
            errors   = s.get("errors", 0)
            conflicts= s.get("conflicts", [])
            detail   = s.get("detail", "")

            frame = QFrame()
            frame.setStyleSheet(
                "QFrame { background: rgba(255,255,255,0.03); "
                "border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; }"
            )
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(14, 12, 14, 12)
            fl.setSpacing(4)

            if status == "skip":
                icon = "—"
                color = "#909090"
            elif status == "error":
                icon = "✗"
                color = "#e05555"
            else:
                icon = "✓"
                color = "#3dba6e"

            header = QLabel(f'<span style="color:{color}; font-weight:700;">'
                            f'{icon}  {label}</span>')
            header.setTextFormat(Qt.RichText)
            fl.addWidget(header)

            if status == "skip" or status == "error":
                note = QLabel(detail)
                note.setWordWrap(True)
                note.setStyleSheet("color: #909090; font-size: 12px; padding-left: 18px;")
                fl.addWidget(note)
            else:
                if imported:
                    imp_lbl = QLabel(
                        f"  <span style='color:#3dba6e;'>+{imported:,} new items</span> "
                        f"added to your library"
                    )
                    imp_lbl.setTextFormat(Qt.RichText)
                    imp_lbl.setStyleSheet("font-size: 12px;")
                    fl.addWidget(imp_lbl)
                if skipped:
                    skip_lbl = QLabel(
                        f"  {skipped:,} already in your library"
                    )
                    skip_lbl.setStyleSheet("color: #909090; font-size: 12px;")
                    fl.addWidget(skip_lbl)
                if errors:
                    err_lbl = QLabel(f"  {errors:,} rows could not be read")
                    err_lbl.setStyleSheet("color: #e07800; font-size: 12px;")
                    fl.addWidget(err_lbl)
                if not imported and not skipped and not errors:
                    fl.addWidget(QLabel("  Nothing to import"))

            root.addWidget(frame)
            all_conflicts.extend(conflicts)

        if all_conflicts:
            cf_frame = QFrame()
            cf_frame.setStyleSheet(
                "QFrame { background: rgba(224,120,0,0.08); "
                "border: 1px solid rgba(224,120,0,0.25); border-radius: 6px; }"
            )
            cfl = QVBoxLayout(cf_frame)
            cfl.setContentsMargins(14, 12, 14, 12)
            cfl.setSpacing(4)
            cf_title = QLabel("⚠  Conflicts detected (your existing values kept)")
            cf_title.setStyleSheet("color: #e07800; font-weight: 600; font-size: 12px;")
            cfl.addWidget(cf_title)
            for c in all_conflicts[:10]:
                lbl = QLabel(
                    f"  {c['name']} — {c['field']} differs "
                    f"(yours: {c['existing']}  community: {c['incoming']})"
                )
                lbl.setStyleSheet("color: #d8d8d8; font-size: 11px;")
                lbl.setWordWrap(True)
                cfl.addWidget(lbl)
            if len(all_conflicts) > 10:
                more = QLabel(f"  … and {len(all_conflicts) - 10} more")
                more.setStyleSheet("color: #909090; font-size: 11px;")
                cfl.addWidget(more)
            root.addWidget(cf_frame)

        ok_btn = QPushButton("OK")
        ok_btn.setMinimumSize(80, 32)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(ok_btn)
        root.addLayout(row)


# ── Upload preview dialog ─────────────────────────────────────────────────────

class _UploadPreviewDialog(QDialog):
    """Confirmation step shown before uploading — summarises what will be sent."""

    def __init__(self, payloads: list, handle: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm Upload")
        self.setModal(True)
        self.setMinimumWidth(440)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        title = QLabel("Confirm Upload to Community Library")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        root.addWidget(title)

        sub = QLabel(
            f"The following will be committed to  "
            f"<b>submissions/{handle}/</b>  on the <b>living-library</b> branch:"
        )
        sub.setWordWrap(True)
        sub.setTextFormat(Qt.RichText)
        sub.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        root.addWidget(sub)

        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.03); "
            "border: 1px solid rgba(255,255,255,0.07); border-radius: 8px; }"
        )
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(16, 12, 16, 12)
        fl.setSpacing(9)

        total_rows = 0
        for label, filename, csv_text, row_count in payloads:
            ok = csv_text is not None
            row_lay = QHBoxLayout()
            icon_lbl = QLabel("✓" if ok else "✗")
            icon_lbl.setStyleSheet(
                f"color: {'#3dba6e' if ok else '#e05555'}; font-weight: 700;"
            )
            icon_lbl.setFixedWidth(20)
            row_lay.addWidget(icon_lbl)
            name_lbl = QLabel(f"<b>{label}</b>")
            name_lbl.setTextFormat(Qt.RichText)
            row_lay.addWidget(name_lbl, stretch=1)
            if ok:
                detail_lbl = QLabel(f"{row_count:,} entries  →  {filename}")
                detail_lbl.setStyleSheet("color: #909090; font-size: 12px;")
                row_lay.addWidget(detail_lbl)
                total_rows += row_count
            else:
                err_lbl = QLabel(str(row_count))
                err_lbl.setStyleSheet("color: #e05555; font-size: 12px;")
                row_lay.addWidget(err_lbl)
            fl.addLayout(row_lay)

        root.addWidget(frame)

        total_lbl = QLabel(f"Total:  {total_rows:,} entries across {len(payloads)} tracker(s)")
        total_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        root.addWidget(total_lbl)

        note = QLabel(
            "ℹ  Personal fields (quantity, condition, stock) are <b>never</b> included — "
            "only community-relevant fields are shared."
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.RichText)
        note.setStyleSheet("font-size: 11px; color: #909090;")
        root.addWidget(note)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumSize(80, 32)
        cancel_btn.clicked.connect(self.reject)
        upload_btn = QPushButton("⬆  Upload")
        upload_btn.setMinimumSize(100, 32)
        upload_btn.setDefault(True)
        upload_btn.setStyleSheet(
            "QPushButton { background: #0078d4; color: white; border: none; "
            "border-radius: 5px; font-weight: 600; }"
            "QPushButton:hover { background: #1a8ee8; }"
        )
        upload_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(upload_btn)
        root.addLayout(btn_row)


# ── Community status signals ──────────────────────────────────────────────────

class _StatusSignals(QObject):
    loaded = Signal(object)   # dict | Exception


class CommunityLibraryDialog(QDialog):
    """
    Upload your collection to the community library on GitHub, or download
    the latest merged master files back into your trackers.

    Upload path:  submissions/{handle}/{plugin}.csv  on living-library branch
    Download path: master/{plugin}.csv  on living-library branch
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx         = context
        self._signals     = _WorkerSignals()
        self._status_sigs = _StatusSignals()
        self._settings    = context.services.try_get("settings")

        self.setWindowTitle("Community Library")
        self.setMinimumSize(680, 720)
        self.resize(720, 800)
        self._build_ui()
        self._connect_signals()
        self._load_settings()
        self._refresh_counts()
        self._start_status_fetch()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Scrollable body ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 28, 32, 20)
        lay.setSpacing(24)

        # Title + description
        title = QLabel("Community Library")
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        desc = QLabel(
            "Contribute your collection to the shared library. Your data is uploaded "
            "as CSV files to the <b>living-library</b> branch. Automation will merge "
            "all submissions into master files that anyone can pull down to expand "
            "their own libraries."
        )
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.RichText)
        desc.setStyleSheet("font-size: 13px; line-height: 1.5;")
        lay.addWidget(desc)

        # ── Community Status Panel ────────────────────────────────────────────
        status_box = QGroupBox("Community Library Status")
        status_lay = QVBoxLayout(status_box)
        status_lay.setContentsMargins(18, 14, 18, 16)
        status_lay.setSpacing(8)

        self._status_merge_lbl = QLabel("Last updated: checking…")
        self._status_merge_lbl.setStyleSheet("font-size: 12px; color: #909090;")
        status_lay.addWidget(self._status_merge_lbl)

        self._status_totals_lbl = QLabel("")
        self._status_totals_lbl.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        self._status_totals_lbl.setVisible(False)
        status_lay.addWidget(self._status_totals_lbl)

        self._status_contribution_lbl = QLabel("")
        self._status_contribution_lbl.setStyleSheet("font-size: 12px;")
        self._status_contribution_lbl.setVisible(False)
        status_lay.addWidget(self._status_contribution_lbl)

        status_refresh_row = QHBoxLayout()
        self._status_refresh_btn = QPushButton("↻  Refresh Status")
        self._status_refresh_btn.setFixedHeight(28)
        self._status_refresh_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #63b3ed; border: none; "
            "font-size: 12px; text-decoration: underline; }"
            "QPushButton:hover { color: #90cdf4; }"
        )
        status_refresh_row.addStretch()
        status_refresh_row.addWidget(self._status_refresh_btn)
        status_lay.addLayout(status_refresh_row)

        lay.addWidget(status_box)
        lay.addWidget(_hline())

        # ── Step 1: Get a token ───────────────────────────────────────────────
        step1_box = QGroupBox("Step 1 — Create a GitHub Personal Access Token")
        step1_lay = QVBoxLayout(step1_box)
        step1_lay.setContentsMargins(20, 16, 20, 20)
        step1_lay.setSpacing(12)

        steps_intro = QLabel(
            "You need a token so the app can write files to the community repo on your behalf. "
            "It takes about 2 minutes:"
        )
        steps_intro.setWordWrap(True)
        steps_intro.setStyleSheet("font-size: 12px;")
        step1_lay.addWidget(steps_intro)

        steps_frame = QFrame()
        steps_frame.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.04); "
            "border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; }"
        )
        steps_inner = QVBoxLayout(steps_frame)
        steps_inner.setContentsMargins(18, 14, 18, 14)
        steps_inner.setSpacing(9)

        _steps = [
            ("1", "Go to",
             "<b>github.com</b> and sign in to your account"),
            ("2", "Open",
             "your profile menu (top-right) → <b>Settings</b>"),
            ("3", "Scroll down to",
             "<b>Developer settings</b> (bottom of the left sidebar)"),
            ("4", "Choose",
             "<b>Personal access tokens → Fine-grained tokens</b>"),
            ("5", "Click",
             "<b>Generate new token</b> — give it any name, e.g. <i>Adeptus Craftmatica</i>"),
            ("6", "Under <b>Repository access</b>", "select <i>Only select repositories</i> "
             "and choose <b>adeptus-craftmatica/adeptus-craftmatica</b>"),
            ("7", "Under <b>Permissions → Repository permissions</b>",
             "set <b>Contents</b> to <b>Read and write</b>"),
            ("8", "Click <b>Generate token</b>",
             "then copy it and paste it into the Token field below"),
        ]
        for num, lead, detail in _steps:
            row = QHBoxLayout()
            row.setSpacing(10)
            badge = QLabel(num)
            badge.setFixedSize(22, 22)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background: rgba(99,179,237,0.25); color: #63b3ed; "
                "border-radius: 11px; font-size: 11px; font-weight: 700;"
            )
            row.addWidget(badge)
            lbl = QLabel(f"{lead} {detail}")
            lbl.setTextFormat(Qt.RichText)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size: 12px;")
            row.addWidget(lbl, stretch=1)
            steps_inner.addLayout(row)

        step1_lay.addWidget(steps_frame)

        # Token + handle inputs
        form = QFormLayout()
        form.setContentsMargins(0, 6, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        pat_row = QHBoxLayout()
        pat_row.setSpacing(8)
        self._pat_input = QLineEdit()
        self._pat_input.setEchoMode(QLineEdit.Password)
        self._pat_input.setPlaceholderText("ghp_xxxxxxxxxxxxxxxxxxxx")
        self._pat_input.setMinimumHeight(34)
        pat_row.addWidget(self._pat_input, stretch=1)
        self._pat_show_btn = QPushButton("Show")
        self._pat_show_btn.setFixedSize(58, 34)
        self._pat_show_btn.setCheckable(True)
        pat_row.addWidget(self._pat_show_btn)
        form.addRow("Token:", pat_row)

        handle_row = QHBoxLayout()
        handle_row.setSpacing(8)
        self._handle_input = QLineEdit()
        self._handle_input.setPlaceholderText("your-github-username")
        self._handle_input.setMinimumHeight(34)
        self._handle_input.setMaximumWidth(260)
        handle_row.addWidget(self._handle_input)
        handle_hint = QLabel("Your GitHub username — used as your submission folder.")
        handle_hint.setObjectName("fieldLabel")
        handle_hint.setStyleSheet("font-size: 11px;")
        handle_row.addWidget(handle_hint)
        handle_row.addStretch()
        form.addRow("Handle:", handle_row)

        step1_lay.addLayout(form)
        lay.addWidget(step1_box)

        # ── Step 2: Upload ────────────────────────────────────────────────────
        upload_box = QGroupBox("Step 2 — Upload Your Library")
        upload_lay = QVBoxLayout(upload_box)
        upload_lay.setContentsMargins(20, 16, 20, 20)
        upload_lay.setSpacing(14)

        upload_desc = QLabel(
            "Choose which trackers to include. Each will be committed as a CSV file "
            "to <code>submissions/{handle}/</code> on the <b>living-library</b> branch."
        )
        upload_desc.setWordWrap(True)
        upload_desc.setTextFormat(Qt.RichText)
        upload_desc.setStyleSheet("font-size: 12px;")
        upload_lay.addWidget(upload_desc)

        checks_frame = QFrame()
        checks_frame.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.03); "
            "border: 1px solid rgba(255,255,255,0.07); border-radius: 8px; }"
        )
        checks_lay = QVBoxLayout(checks_frame)
        checks_lay.setContentsMargins(16, 12, 16, 12)
        checks_lay.setSpacing(10)

        self._plugin_checks: dict = {}
        for svc_key, label, *_ in _UPLOAD_PLUGINS:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setStyleSheet("font-size: 13px; padding: 2px 0;")
            if not self._ctx.services.try_get(svc_key):
                cb.setChecked(False)
                cb.setEnabled(False)
                cb.setText(f"{label}  (plugin not loaded)")
            self._plugin_checks[svc_key] = cb
            checks_lay.addWidget(cb)

        upload_lay.addWidget(checks_frame)

        self._upload_btn = QPushButton("⬆  Upload to GitHub")
        self._upload_btn.setProperty("class", "primary")
        self._upload_btn.setMinimumHeight(38)
        self._upload_btn.setStyleSheet("font-size: 13px; font-weight: 600;")
        upload_lay.addWidget(self._upload_btn)

        lay.addWidget(upload_box)

        # ── Get Latest ────────────────────────────────────────────────────────
        dl_box = QGroupBox("Get Latest Community Data")
        dl_lay = QVBoxLayout(dl_box)
        dl_lay.setContentsMargins(20, 16, 20, 20)
        dl_lay.setSpacing(14)

        dl_desc = QLabel(
            "Once the community library has grown, automation will merge all submissions "
            "into master files. Click below to download those files and import any new "
            "entries into your trackers — your existing data is never removed."
        )
        dl_desc.setWordWrap(True)
        dl_desc.setStyleSheet("font-size: 12px;")
        dl_lay.addWidget(dl_desc)

        self._dl_btn = QPushButton("⬇  Download Latest")
        self._dl_btn.setMinimumHeight(38)
        self._dl_btn.setStyleSheet("font-size: 13px;")
        dl_lay.addWidget(self._dl_btn)

        lay.addWidget(dl_box)
        lay.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        # ── Fixed footer ──────────────────────────────────────────────────────
        footer = QFrame()
        footer.setFrameShape(QFrame.NoFrame)
        footer.setStyleSheet(
            "QFrame { border-top: 1px solid rgba(255,255,255,0.08); "
            "background: transparent; }"
        )
        footer_lay = QVBoxLayout(footer)
        footer_lay.setContentsMargins(32, 12, 32, 16)
        footer_lay.setSpacing(8)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setMaximumHeight(4)
        self._progress.setVisible(False)
        footer_lay.addWidget(self._progress)

        status_row = QHBoxLayout()
        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setObjectName("fieldLabel")
        self._status_lbl.setStyleSheet("font-size: 12px;")
        status_row.addWidget(self._status_lbl, stretch=1)

        self._close_btn = QPushButton("Close")
        self._close_btn.setMinimumSize(90, 34)
        status_row.addWidget(self._close_btn)
        footer_lay.addLayout(status_row)

        root.addWidget(footer)

    def _connect_signals(self):
        self._pat_show_btn.toggled.connect(self._toggle_pat_visibility)
        self._pat_input.textChanged.connect(self._save_settings)
        self._handle_input.textChanged.connect(self._save_settings)
        self._upload_btn.clicked.connect(self._start_upload)
        self._dl_btn.clicked.connect(self._start_download)
        self._close_btn.clicked.connect(self.accept)
        self._signals.progress.connect(lambda msg: self._status_lbl.setText(msg))
        self._signals.done.connect(self._on_done)
        self._status_sigs.loaded.connect(self._on_status_loaded)
        self._status_refresh_btn.clicked.connect(self._start_status_fetch)

    def _toggle_pat_visibility(self, checked: bool):
        self._pat_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self._pat_show_btn.setText("Hide" if checked else "Show")

    # ── Community Status ──────────────────────────────────────────────────────

    def _start_status_fetch(self):
        self._status_merge_lbl.setText("Last updated: checking…")
        self._status_totals_lbl.setVisible(False)
        self._status_contribution_lbl.setVisible(False)
        self._status_refresh_btn.setEnabled(False)
        threading.Thread(target=self._status_worker, daemon=True).start()

    def _status_worker(self):
        url = (f"https://api.github.com/repos/{_COMMUNITY_REPO}"
               f"/contents/master/community_status.json?ref={_COMMUNITY_BRANCH}")
        req = Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Accept":     "application/vnd.github.v3+json",
        })
        try:
            with urlopen(req, context=_ssl_context(), timeout=10) as resp:
                data = json.loads(base64.b64decode(
                    json.load(resp)["content"].replace("\n", "")
                ).decode())
            self._status_sigs.loaded.emit(data)
        except HTTPError as e:
            self._status_sigs.loaded.emit(Exception(
                "unavailable" if e.code == 404 else f"HTTP {e.code}"
            ))
        except Exception as e:
            self._status_sigs.loaded.emit(Exception(str(e)))

    def _on_status_loaded(self, result):
        self._status_refresh_btn.setEnabled(True)
        if isinstance(result, Exception):
            msg = str(result)
            if "unavailable" in msg:
                self._status_merge_lbl.setText("Last updated: not yet available")
            else:
                self._status_merge_lbl.setText(f"Last updated: could not load ({msg})")
            return

        # Last merge time
        raw_ts = result.get("last_merge", "")
        if raw_ts:
            try:
                ts = datetime.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                now = datetime.datetime.now(datetime.timezone.utc)
                diff = now - ts
                if diff.days >= 1:
                    age = f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
                elif diff.seconds >= 3600:
                    h = diff.seconds // 3600
                    age = f"{h} hour{'s' if h != 1 else ''} ago"
                else:
                    m = max(1, diff.seconds // 60)
                    age = f"{m} minute{'s' if m != 1 else ''} ago"
                self._status_merge_lbl.setText(f"Last updated: {age}")
            except Exception:
                self._status_merge_lbl.setText(f"Last updated: {raw_ts}")
        else:
            self._status_merge_lbl.setText("Last updated: unknown")

        # Totals
        totals = result.get("totals", {})
        if totals:
            parts = []
            labels = [("paints", "Paints"), ("materials", "Materials"),
                      ("tools", "Tools"), ("models", "Models")]
            for key, name in labels:
                if key in totals:
                    parts.append(f"{name}: {totals[key]:,}")
            if parts:
                self._status_totals_lbl.setText("  ·  ".join(parts))
                self._status_totals_lbl.setVisible(True)

        # Contribution status
        last_upload = ""
        if self._settings:
            last_upload = self._settings.get("community.last_upload", "")
        if last_upload and raw_ts:
            try:
                upload_ts = datetime.datetime.fromisoformat(last_upload.replace("Z", "+00:00"))
                merge_ts  = datetime.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                if upload_ts <= merge_ts:
                    self._status_contribution_lbl.setText(
                        "✅  Your contributions are part of the community library"
                    )
                    self._status_contribution_lbl.setStyleSheet(
                        "font-size: 12px; color: #3dba6e;"
                    )
                else:
                    self._status_contribution_lbl.setText(
                        "⏳  Your submission is pending the next community update"
                    )
                    self._status_contribution_lbl.setStyleSheet(
                        "font-size: 12px; color: #e07800;"
                    )
                self._status_contribution_lbl.setVisible(True)
            except Exception:
                pass

    # ── Settings ──────────────────────────────────────────────────────────────

    def _load_settings(self):
        if not self._settings:
            return
        pat    = self._settings.get("community.github_pat", "")
        handle = self._settings.get("community.handle",     "")
        if pat:
            self._pat_input.setText(pat)
        if handle:
            self._handle_input.setText(handle)

    def _save_settings(self):
        if not self._settings:
            return
        self._settings.set("community.github_pat", self._pat_input.text().strip())
        self._settings.set("community.handle",     self._handle_input.text().strip())

    def _refresh_counts(self):
        """Update checkbox labels with live row counts from each service."""
        plural_map = {
            "paint_service":    "paints",
            "material_service": "materials",
            "tool_service":     "tools",
            "model_service":    "models",
        }
        for svc_key, label, _, _, getter in _UPLOAD_PLUGINS:
            cb = self._plugin_checks[svc_key]
            if not cb.isEnabled():
                continue
            svc = self._ctx.services.try_get(svc_key)
            if not svc:
                continue
            try:
                n = len(getattr(svc, getter)())
                cb.setText(f"{label}  ({n:,} {plural_map[svc_key]})")
            except Exception:
                pass

    # ── Validation ────────────────────────────────────────────────────────────

    def _validated_inputs(self):
        """Return (token, handle) or None if validation fails."""
        token  = self._pat_input.text().strip()
        handle = self._handle_input.text().strip()
        if not token:
            QMessageBox.warning(self, "Missing Token",
                "Please enter a GitHub Personal Access Token.")
            self._pat_input.setFocus()
            return None
        if not handle:
            QMessageBox.warning(self, "Missing Handle",
                "Please enter your handle / username.")
            self._handle_input.setFocus()
            return None
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", handle):
            QMessageBox.warning(self, "Invalid Handle",
                "Handle may only contain letters, numbers, hyphens, underscores, and dots.")
            self._handle_input.setFocus()
            return None
        return token, handle

    # ── Upload ────────────────────────────────────────────────────────────────

    def _start_upload(self):
        inputs = self._validated_inputs()
        if not inputs:
            return
        token, handle = inputs

        selected = [k for k, cb in self._plugin_checks.items()
                    if cb.isChecked() and cb.isEnabled()]
        if not selected:
            QMessageBox.warning(self, "Nothing Selected",
                "Please tick at least one tracker to upload.")
            return

        # Serialize all data on the main thread — SQLite is not thread-safe.
        try:
            plugin_info = {k: (lbl, fn, hdrs, gtr) for k, lbl, fn, hdrs, gtr in _UPLOAD_PLUGINS}
            payloads = []
            for svc_key in selected:
                label, filename, headers, getter = plugin_info[svc_key]
                try:
                    svc   = self._ctx.services.try_get(svc_key)
                    items = getattr(svc, getter)()
                    csv_text = _to_csv(headers, _plugin_to_rows(svc_key, items))
                    payloads.append((label, filename, csv_text, len(items)))
                except Exception as exc:
                    payloads.append((label, filename, None, str(exc)))
        except Exception as exc:
            self._set_busy(False, f"✗  {exc}")
            return

        # Show a preview and ask for confirmation before uploading.
        preview = _UploadPreviewDialog(payloads, handle, parent=self)
        if preview.exec() != QDialog.Accepted:
            return

        self._set_busy(True, f"Uploading for  @{handle}…")
        try:
            threading.Thread(
                target=self._upload_worker, args=(token, handle, payloads), daemon=True
            ).start()
        except Exception as exc:
            self._set_busy(False, f"✗  {exc}")

    def _upload_worker(self, token: str, handle: str, payloads: list):
        results = []
        try:
            self._upload_worker_inner(token, handle, payloads, results)
        except Exception as exc:
            results.append(("Unexpected error", "error", str(exc)))
        self._signals.done.emit({"type": "upload", "results": results, "handle": handle})

    def _upload_worker_inner(self, token: str, handle: str, payloads: list, results: list):

        for label, filename, csv_text, row_count in payloads:
            if csv_text is None:
                # Export failed on the main thread
                results.append((label, "error", str(row_count)))
                continue

            path = f"submissions/{handle}/{filename}"
            self._signals.progress.emit(f"Uploading  {filename}  ({row_count:,} rows)…")
            try:
                _gh_put_file(
                    repo    = _COMMUNITY_REPO,
                    path    = path,
                    content = csv_text,
                    message = f"Community backup: {label} from @{handle}",
                    branch  = _COMMUNITY_BRANCH,
                    token   = token,
                )
                results.append((label, "ok", f"{row_count:,} entries → {path}"))

            except HTTPError as e:
                if e.code == 401:
                    results.append((label, "error",
                        "Authentication failed — check the token has Contents: Write access"))
                    break  # no point continuing if auth is wrong
                elif e.code == 403:
                    results.append((label, "error",
                        "Permission denied — token may lack write access to this repo"))
                    break
                elif e.code == 404:
                    results.append((label, "error",
                        "Repo or branch not found"))
                else:
                    results.append((label, "error", f"GitHub API error {e.code}"))
            except Exception as exc:
                results.append((label, "error", str(exc)))

    # ── Download ──────────────────────────────────────────────────────────────

    def _start_download(self):
        inputs = self._validated_inputs()
        if not inputs:
            return
        token, _ = inputs

        # Serialize all main-thread data before spawning worker (SQLite not thread-safe).
        self._set_busy(True, "Reading your current library…")
        try:
            existing_data = {
                svc_key: _existing_lookup(svc_key, self._ctx)
                for svc_key, *_ in _UPLOAD_PLUGINS
            }
            # Pre-fetch stored SHAs so the worker can do incremental checks.
            last_shas: dict[str, str] = {}
            if self._settings:
                for _, _, filename, _, _ in _UPLOAD_PLUGINS:
                    last_shas[filename] = self._settings.get(
                        f"community.last_sha.{filename}", ""
                    )
            self._set_busy(True, "Fetching latest community master files…")
            threading.Thread(
                target=self._download_worker,
                args=(token, existing_data, last_shas),
                daemon=True,
            ).start()
        except Exception as exc:
            self._set_busy(False, f"✗  {exc}")

    def _download_worker(self, token: str, existing_data: dict, last_shas: dict):
        results  = []
        dl_stats = {}
        new_shas: dict[str, str] = {}   # filename → new SHA to persist after success

        for svc_key, label, filename, _, _ in _UPLOAD_PLUGINS:
            path = f"master/{filename}"
            self._signals.progress.emit(f"Downloading  {filename}…")
            try:
                url = (f"https://api.github.com/repos/{_COMMUNITY_REPO}"
                       f"/contents/{path}?ref={_COMMUNITY_BRANCH}")
                req = Request(url, headers={
                    "User-Agent":    _USER_AGENT,
                    "Authorization": f"Bearer {token}",
                    "Accept":        "application/vnd.github.v3+json",
                })
                with urlopen(req, context=_ssl_context(), timeout=15) as resp:
                    data = json.load(resp)

                file_sha = data.get("sha", "")

                # Incremental: skip import when the file hasn't changed since last download.
                if file_sha and file_sha == last_shas.get(filename, ""):
                    detail = "Already up to date"
                    results.append((label, "skip", detail))
                    dl_stats[label] = {"status": "uptodate", "detail": detail,
                                       "imported": 0, "skipped": 0, "errors": 0, "conflicts": []}
                    continue

                raw      = base64.b64decode(data["content"].replace("\n", ""))
                csv_text = raw.decode("utf-8-sig", errors="replace")
                stats    = self._import_csv(svc_key, label, csv_text,
                                            existing_data.get(svc_key, {}))
                results.append((label, "ok", f"{stats['imported']:,} new items added"))
                dl_stats[label] = {"status": "ok", **stats}
                if file_sha:
                    new_shas[filename] = file_sha

            except HTTPError as e:
                if e.code == 404:
                    detail = "Not yet available — check back once the community grows!"
                    results.append((label, "skip", detail))
                    dl_stats[label] = {"status": "skip", "detail": detail,
                                       "imported": 0, "skipped": 0, "errors": 0, "conflicts": []}
                elif e.code == 401:
                    detail = "Authentication failed — check your token"
                    results.append((label, "error", detail))
                    dl_stats[label] = {"status": "error", "detail": detail,
                                       "imported": 0, "skipped": 0, "errors": 0, "conflicts": []}
                    break
                else:
                    detail = f"Could not download (HTTP {e.code})"
                    results.append((label, "error", detail))
                    dl_stats[label] = {"status": "error", "detail": detail,
                                       "imported": 0, "skipped": 0, "errors": 0, "conflicts": []}
            except Exception as exc:
                detail = str(exc)
                results.append((label, "error", detail))
                dl_stats[label] = {"status": "error", "detail": detail,
                                   "imported": 0, "skipped": 0, "errors": 0, "conflicts": []}

        self._signals.done.emit({
            "type": "download", "results": results,
            "stats": dl_stats, "new_shas": new_shas,
        })

    def _import_csv(self, svc_key: str, label: str, csv_text: str,
                    existing: dict) -> dict:
        """Import rows, skip known items, detect conflicts. Returns stats dict."""
        svc = self._ctx.services.try_get(svc_key)
        if not svc:
            raise RuntimeError(f"{label} plugin is not loaded")

        reader   = csv.DictReader(io.StringIO(csv_text))
        imported = skipped = errors = 0
        conflicts: list[dict] = []

        for row in reader:
            n = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
            try:
                # Compute dedup key
                if svc_key == "paint_service":
                    if not n.get("brand") or not n.get("name"):
                        errors += 1; continue
                    key = (_norm_key(n["brand"]), _norm_key(n["name"]))
                    conflict_field, conflict_val = "color", n.get("color", "")
                elif svc_key == "material_service":
                    if not n.get("name") or not n.get("type"):
                        errors += 1; continue
                    key = (_norm_key(n["name"]), _norm_key(n.get("brand", "")))
                    conflict_field, conflict_val = "color", n.get("color", "")
                elif svc_key == "tool_service":
                    if not n.get("name") or not n.get("type"):
                        errors += 1; continue
                    key = (_norm_key(n["name"]), _norm_key(n.get("brand", "")))
                    conflict_field, conflict_val = None, None
                elif svc_key == "model_service":
                    if not n.get("name") or not n.get("game_system"):
                        errors += 1; continue
                    key = (_norm_key(n["name"]), _norm_key(n["game_system"]))
                    conflict_field, conflict_val = "faction", n.get("faction", "")
                else:
                    errors += 1; continue

                if key in existing:
                    # Detect data conflicts
                    if conflict_field and conflict_val:
                        existing_val = existing[key].get(conflict_field, "")
                        if (existing_val and conflict_val
                                and existing_val.lower() != conflict_val.lower()):
                            conflicts.append({
                                "name":     n.get("name", ""),
                                "field":    conflict_field,
                                "existing": existing_val,
                                "incoming": conflict_val,
                            })
                    skipped += 1
                    continue

                # Add to library
                if svc_key == "paint_service":
                    color = n.get("color", "#808080")
                    if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
                        color = "#808080"
                    svc.add_paint(brand=n["brand"], name=n["name"],
                                  paint_type=n.get("type") or "Base", color=color,
                                  quantity=0, level=None, notes=None)
                elif svc_key == "material_service":
                    svc.add_material(name=n["name"], material_type=n["type"],
                                     brand=n.get("brand", ""), color=n.get("color", ""),
                                     stock="Good", quantity=0, notes=None)
                elif svc_key == "tool_service":
                    svc.add_tool(name=n["name"], tool_type=n["type"],
                                 brand=n.get("brand", ""), condition="Good",
                                 quantity=0, notes=None)
                elif svc_key == "model_service":
                    svc.add_model(name=n["name"], game_system=n["game_system"],
                                  faction=n.get("faction") or "Unknown",
                                  model_type=n.get("type") or "Other",
                                  status="Unassembled", scale=n.get("scale", ""),
                                  quantity=1, notes=None)
                imported += 1

            except Exception:
                errors += 1

        return {"imported": imported, "skipped": skipped,
                "errors": errors, "conflicts": conflicts}

    # ── Result handler ────────────────────────────────────────────────────────

    def _on_done(self, result):
        self._set_busy(False, "")
        if not isinstance(result, dict):
            return

        op_type = result.get("type", "upload")
        results = result.get("results", [])
        ok      = sum(1 for _, s, _ in results if s == "ok")

        if op_type == "upload":
            if ok:
                handle = result.get("handle", "")
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                if self._settings:
                    self._settings.set("community.last_upload", now_iso)
                self._status_lbl.setText(
                    "✔  Your library has been submitted to the community."
                )
                # Refresh status panel to pick up new upload timestamp
                self._start_status_fetch()
            else:
                self._status_lbl.setText("Upload finished with errors — see details.")

            lines = []
            for label, status, detail in results:
                icon = "✓" if status == "ok" else ("—" if status == "skip" else "✗")
                lines.append(f"{icon}  {label}:  {detail}")
            QMessageBox.information(self, "Upload Complete",
                                    "\n".join(lines) or "Nothing to report.")

        elif op_type == "download":
            dl_stats = result.get("stats", {})
            new_shas = result.get("new_shas", {})

            # Persist new SHAs so the next download can skip unchanged files.
            if self._settings and new_shas:
                for filename, sha in new_shas.items():
                    self._settings.set(f"community.last_sha.{filename}", sha)

            total_new = sum(
                s.get("imported", 0) for s in dl_stats.values()
                if s.get("status") == "ok"
            )
            up_to_date = sum(
                1 for s in dl_stats.values() if s.get("status") == "uptodate"
            )
            if total_new:
                self._status_lbl.setText(
                    f"✔  {total_new:,} new item{'s' if total_new != 1 else ''} added."
                )
            elif up_to_date == len(dl_stats):
                self._status_lbl.setText("✔  Everything is already up to date.")
            else:
                self._status_lbl.setText("Download finished.")

            # Build display stats, mapping uptodate → skip for the result dialog.
            display_stats = {
                label: ({**s, "status": "skip"} if s.get("status") == "uptodate" else s)
                for label, s in dl_stats.items()
            }
            dlg = _ImportResultDialog(display_stats, self)
            dlg.exec()
            return

        if op_type == "download" and not ok:
            self._status_lbl.setText("Done.")
        elif not ok and op_type == "upload":
            self._status_lbl.setText("Done.")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool, msg: str):
        self._progress.setVisible(busy)
        self._upload_btn.setEnabled(not busy)
        self._dl_btn.setEnabled(not busy)
        self._close_btn.setEnabled(not busy)
        if msg:
            self._status_lbl.setText(msg)
