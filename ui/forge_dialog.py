"""
ui/forge_dialog.py
The Forge — community library hub for Adeptus Craftmatica.

Three tabs:
  Browse & Import  — fetch community master lists, select items, add to trackers
  Contribute       — upload your library to the community repo
  Import Files     — download game data / paint lists from any GitHub repo
"""
from __future__ import annotations

import base64
import csv
import io
import json
import re
import sys
import threading

from PySide6.QtCore import Qt, Signal, QObject, QSignalBlocker
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QProgressBar, QPushButton, QLineEdit, QSizePolicy,
    QStackedWidget, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from ui.github_import_dialog import (
    GitHubImportDialog,
    CommunityLibraryDialog,
    _ssl_context,
    _USER_AGENT,
    _COMMUNITY_REPO,
    _COMMUNITY_BRANCH,
)

# ── Per-tracker browse configuration ──────────────────────────────────────────

_BROWSE_TRACKERS = [
    {
        "svc_key":    "paint_service",
        "label":      "Paints",
        "filename":   "paints.csv",
        "has_swatch": True,
        "filter_key": "type",
        "display_cols": [("Brand", "brand"), ("Name", "name"), ("Type", "type")],
        "getter":     "get_all_paints",
        "owned_key":  lambda r: (r.get("brand", "").lower(), r.get("name", "").lower()),
        "local_key":  lambda p: (p.brand.lower(), p.name.lower()),
    },
    {
        "svc_key":    "material_service",
        "label":      "Materials",
        "filename":   "materials.csv",
        "has_swatch": False,
        "filter_key": "type",
        "display_cols": [("Name", "name"), ("Type", "type"), ("Brand", "brand")],
        "getter":     "get_all_materials",
        "owned_key":  lambda r: (r.get("name", "").lower(), r.get("type", "").lower()),
        "local_key":  lambda m: (m.name.lower(), m.material_type.lower()),
    },
    {
        "svc_key":    "tool_service",
        "label":      "Tools",
        "filename":   "tools.csv",
        "has_swatch": False,
        "filter_key": "type",
        "display_cols": [("Name", "name"), ("Type", "type"), ("Brand", "brand")],
        "getter":     "get_all_tools",
        "owned_key":  lambda r: (r.get("name", "").lower(), r.get("type", "").lower()),
        "local_key":  lambda t: (t.name.lower(), t.tool_type.lower()),
    },
    {
        "svc_key":    "model_service",
        "label":      "Models",
        "filename":   "models.csv",
        "has_swatch": False,
        "filter_key": "game_system",
        "display_cols": [
            ("Name", "name"), ("Game System", "game_system"),
            ("Faction", "faction"), ("Type", "type"),
        ],
        "getter":     "get_all_models",
        "owned_key":  lambda r: (r.get("name", "").lower(), r.get("game_system", "").lower()),
        "local_key":  lambda m: (m.name.lower(), m.game_system.lower()),
    },
]

_TRACKER_BY_LABEL = {t["label"]: t for t in _BROWSE_TRACKERS}

# ── Signal bridge ──────────────────────────────────────────────────────────────

class _Signals(QObject):
    progress = Signal(str)
    done     = Signal(object)


# ══════════════════════════════════════════════════════════════════════════════
# Browse & Import Pane
# ══════════════════════════════════════════════════════════════════════════════

class BrowsePane(QWidget):
    """
    Fetches community master CSV files from GitHub and lets the user pick
    which items to add to their local trackers.
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx         = context
        self._signals     = _Signals()
        self._rows:       list[dict] = []
        self._owned_keys: set        = set()
        self._cfg:        dict | None = None

        self._build_ui()
        self._connect_signals()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 18)
        lay.setSpacing(14)

        # Header
        title = QLabel("Browse & Import from Community Library")
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        sub = QLabel(
            "Fetch the community master list for any tracker, browse the items, "
            "and add what you want to your collection. "
            "Items you already own are highlighted — only new ones get added."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 12px;")
        lay.addWidget(sub)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        lbl = QLabel("Tracker:")
        lbl.setStyleSheet("font-weight: 600;")
        ctrl.addWidget(lbl)

        self._tracker_combo = QComboBox()
        self._tracker_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._tracker_combo.setMinimumWidth(150)
        for t in _BROWSE_TRACKERS:
            self._tracker_combo.addItem(t["label"])
        ctrl.addWidget(self._tracker_combo)

        ctrl.addSpacing(10)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumHeight(32)
        ctrl.addWidget(self._search, stretch=1)

        self._filter_combo = QComboBox()
        self._filter_combo.setMinimumWidth(160)
        self._filter_combo.setMinimumHeight(32)
        self._filter_combo.setEnabled(False)
        ctrl.addWidget(self._filter_combo)

        self._fetch_btn = QPushButton("🔄  Fetch from Community")
        self._fetch_btn.setProperty("class", "primary")
        self._fetch_btn.setMinimumHeight(32)
        ctrl.addWidget(self._fetch_btn)

        lay.addLayout(ctrl)

        # Stacked area
        self._stack = QStackedWidget()

        self._empty_lbl = QLabel(
            "Select a tracker above and click  🔄 Fetch from Community  to load the master list."
        )
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setObjectName("fieldLabel")
        self._empty_lbl.setWordWrap(True)
        self._stack.addWidget(self._empty_lbl)

        self._table = QTableWidget()
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._stack.addWidget(self._table)

        lay.addWidget(self._stack, stretch=1)

        # Selection / status row
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)

        self._sel_all_btn = QPushButton("✓  Select All")
        self._sel_all_btn.setEnabled(False)
        self._sel_all_btn.setMinimumWidth(110)
        self._sel_none_btn = QPushButton("✗  Select None")
        self._sel_none_btn.setEnabled(False)
        self._sel_none_btn.setMinimumWidth(110)
        self._sel_new_btn = QPushButton("★  New Only")
        self._sel_new_btn.setEnabled(False)
        self._sel_new_btn.setMinimumWidth(110)
        self._sel_new_btn.setToolTip(
            "Check only items not already in your collection, uncheck all owned ones"
        )
        self._sel_lbl = QLabel("")
        self._sel_lbl.setObjectName("fieldLabel")
        self._sel_lbl.setStyleSheet("font-size: 12px;")

        sel_row.addWidget(self._sel_all_btn)
        sel_row.addWidget(self._sel_none_btn)
        sel_row.addWidget(self._sel_new_btn)
        sel_row.addSpacing(10)
        sel_row.addWidget(self._sel_lbl)
        sel_row.addStretch()
        lay.addLayout(sel_row)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setMaximumHeight(4)
        self._progress.setVisible(False)
        lay.addWidget(self._progress)

        # Bottom row: status + add button
        bottom = QHBoxLayout()
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("fieldLabel")
        self._status_lbl.setStyleSheet("font-size: 12px;")
        bottom.addWidget(self._status_lbl, stretch=1)

        self._add_btn = QPushButton("+ Add Selected to My Collection")
        self._add_btn.setProperty("class", "primary")
        self._add_btn.setMinimumHeight(36)
        self._add_btn.setMinimumWidth(250)
        self._add_btn.setEnabled(False)
        bottom.addWidget(self._add_btn)
        lay.addLayout(bottom)

    def _connect_signals(self):
        self._tracker_combo.currentTextChanged.connect(self._on_tracker_changed)
        self._search.textChanged.connect(self._apply_filter)
        self._filter_combo.currentTextChanged.connect(self._apply_filter)
        self._fetch_btn.clicked.connect(self._start_fetch)
        self._sel_all_btn.clicked.connect(self._select_all)
        self._sel_none_btn.clicked.connect(self._select_none)
        self._sel_new_btn.clicked.connect(self._select_new_only)
        self._table.itemChanged.connect(self._refresh_sel_label)
        self._add_btn.clicked.connect(self._add_selected)
        self._signals.progress.connect(self._status_lbl.setText)
        self._signals.done.connect(self._on_fetch_done)

    # ── Tracker change ────────────────────────────────────────────────────────

    def _on_tracker_changed(self, label: str):
        self._rows.clear()
        self._owned_keys.clear()
        self._table.clearContents()
        self._table.setRowCount(0)
        self._stack.setCurrentIndex(0)
        self._empty_lbl.setText(
            f"Click  🔄 Fetch from Community  to load the {label} master list."
        )
        self._sel_all_btn.setEnabled(False)
        self._sel_none_btn.setEnabled(False)
        self._sel_new_btn.setEnabled(False)
        self._add_btn.setEnabled(False)
        self._add_btn.setText(f"+ Add Selected to My {label}")
        self._sel_lbl.setText("")
        self._status_lbl.setText("")
        with QSignalBlocker(self._filter_combo):
            self._filter_combo.clear()
            self._filter_combo.addItem("All")
        self._filter_combo.setEnabled(False)

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def _start_fetch(self):
        label = self._tracker_combo.currentText()
        cfg   = _TRACKER_BY_LABEL.get(label)
        if not cfg:
            return

        self._cfg = cfg
        self._rows.clear()
        self._owned_keys.clear()

        # Build owned-key set on the main thread (database lives here)
        svc = self._ctx.services.try_get(cfg["svc_key"])
        if svc:
            try:
                local = getattr(svc, cfg["getter"])()
                self._owned_keys = {cfg["local_key"](item) for item in local}
            except Exception:
                pass

        self._set_busy(True, f"Downloading {label} master list…")
        self._stack.setCurrentIndex(0)
        self._empty_lbl.setText(f"Downloading {label} master list…")

        threading.Thread(
            target=self._fetch_worker, args=(cfg["filename"],), daemon=True
        ).start()

    def _fetch_worker(self, filename: str):
        try:
            url = (f"https://api.github.com/repos/{_COMMUNITY_REPO}"
                   f"/contents/master/{filename}?ref={_COMMUNITY_BRANCH}")
            req = Request(url, headers={
                "User-Agent": _USER_AGENT,
                "Accept":     "application/vnd.github.v3+json",
            })
            with urlopen(req, context=_ssl_context(), timeout=20) as resp:
                data = json.load(resp)

            raw  = base64.b64decode(data["content"].replace("\n", ""))
            text = raw.decode("utf-8-sig", errors="replace")
            rows = [
                {k.strip().lower(): (v or "").strip() for k, v in row.items()}
                for row in csv.DictReader(io.StringIO(text))
                if any(v.strip() for v in row.values())
            ]
            self._signals.done.emit(rows)

        except HTTPError as e:
            if e.code == 404:
                self._signals.done.emit(Exception(
                    "This master file doesn't exist yet.\n\n"
                    "The community library is still being built — be one of the first "
                    "to contribute via the Contribute tab!"
                ))
            elif e.code == 403:
                self._signals.done.emit(Exception(
                    "GitHub rate limit reached (60 requests/hour for anonymous access).\n\n"
                    "Wait a minute and try again."
                ))
            else:
                self._signals.done.emit(Exception(f"GitHub API error {e.code}."))
        except URLError as e:
            self._signals.done.emit(Exception(f"Network error: {e.reason}"))
        except Exception as e:
            self._signals.done.emit(e)

    def _on_fetch_done(self, result):
        self._set_busy(False)

        if isinstance(result, Exception):
            self._empty_lbl.setText(str(result))
            self._stack.setCurrentIndex(0)
            QMessageBox.warning(self, "Could Not Fetch", str(result))
            return

        self._rows = result
        self._rebuild_filter_combo()
        self._populate_table(self._rows)

        n     = len(result)
        owned = sum(1 for r in result
                    if self._cfg and self._cfg["owned_key"](r) in self._owned_keys)
        self._status_lbl.setText(
            f"{n:,} items in community master  —  "
            f"{owned:,} already in your collection,  "
            f"{n - owned:,} new."
        )

    # ── Filter ────────────────────────────────────────────────────────────────

    def _rebuild_filter_combo(self):
        if not self._cfg:
            return
        key    = self._cfg["filter_key"]
        values = sorted({r.get(key, "") for r in self._rows if r.get(key)})
        with QSignalBlocker(self._filter_combo):
            self._filter_combo.clear()
            self._filter_combo.addItem("All")
            for v in values:
                self._filter_combo.addItem(v)
        self._filter_combo.setEnabled(bool(values))

    def _apply_filter(self):
        if not self._rows or not self._cfg:
            return
        query  = self._search.text().lower().strip()
        fval   = self._filter_combo.currentText()
        fkey   = self._cfg["filter_key"]

        visible = [
            r for r in self._rows
            if (not query or any(query in str(v).lower() for v in r.values()))
            and (fval == "All" or r.get(fkey, "") == fval)
        ]
        self._populate_table(visible)

    # ── Table ─────────────────────────────────────────────────────────────────

    def _populate_table(self, rows: list[dict]):
        if not self._cfg:
            return
        cfg        = self._cfg
        has_swatch = cfg["has_swatch"]
        dcols      = cfg["display_cols"]   # [(header, key), ...]

        # Column layout: [checkbox] [swatch?] [data cols...]
        n_cols = 1 + (1 if has_swatch else 0) + len(dcols)
        headers = (
            ["", ""] if has_swatch else [""]
        ) + [h for h, _ in dcols]

        self._table.blockSignals(True)
        self._table.setColumnCount(n_cols)
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(rows))

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 32)
        data_start = 1
        if has_swatch:
            hdr.setSectionResizeMode(1, QHeaderView.Fixed)
            self._table.setColumnWidth(1, 34)
            data_start = 2
        for ci in range(data_start, n_cols):
            hdr.setSectionResizeMode(
                ci,
                QHeaderView.Stretch if ci == data_start else QHeaderView.ResizeToContents
            )

        for ri, r in enumerate(rows):
            owned = self._cfg["owned_key"](r) in self._owned_keys

            # Checkbox
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if owned else Qt.Unchecked)
            chk.setData(Qt.UserRole, r)
            self._table.setItem(ri, 0, chk)

            # Swatch
            if has_swatch:
                sw = QTableWidgetItem()
                sw.setFlags(Qt.ItemIsEnabled)
                color_str = r.get("color", "")
                if color_str and color_str.startswith("#"):
                    sw.setBackground(QColor(color_str))
                self._table.setItem(ri, 1, sw)

            # Data columns
            for ci, (_, key) in enumerate(dcols):
                cell = QTableWidgetItem(r.get(key, ""))
                cell.setFlags(Qt.ItemIsEnabled)
                if owned:
                    cell.setForeground(QColor("#606060"))
                self._table.setItem(ri, data_start + ci, cell)

        self._table.blockSignals(False)
        self._stack.setCurrentIndex(1)

        self._sel_all_btn.setEnabled(True)
        self._sel_none_btn.setEnabled(True)
        self._sel_new_btn.setEnabled(True)
        self._add_btn.setEnabled(True)
        self._add_btn.setText(f"+ Add Selected to My {cfg['label']}")
        self._refresh_sel_label()

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _select_all(self):
        self._table.blockSignals(True)
        for i in range(self._table.rowCount()):
            item = self._table.item(i, 0)
            if item:
                item.setCheckState(Qt.Checked)
        self._table.blockSignals(False)
        self._refresh_sel_label()

    def _select_none(self):
        self._table.blockSignals(True)
        for i in range(self._table.rowCount()):
            item = self._table.item(i, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self._table.blockSignals(False)
        self._refresh_sel_label()

    def _select_new_only(self):
        """Check only items not already in the local collection."""
        if not self._cfg:
            return
        self._table.blockSignals(True)
        for i in range(self._table.rowCount()):
            chk = self._table.item(i, 0)
            if chk:
                row_data = chk.data(Qt.UserRole)
                owned = bool(row_data and self._cfg["owned_key"](row_data) in self._owned_keys)
                chk.setCheckState(Qt.Unchecked if owned else Qt.Checked)
        self._table.blockSignals(False)
        self._refresh_sel_label()

    def _refresh_sel_label(self):
        total   = self._table.rowCount()
        checked = sum(
            1 for i in range(total)
            if self._table.item(i, 0)
            and self._table.item(i, 0).checkState() == Qt.Checked
        )
        self._sel_lbl.setText(f"{checked:,} of {total:,} selected")
        self._add_btn.setEnabled(checked > 0)

    # ── Add selected ──────────────────────────────────────────────────────────

    def _add_selected(self):
        if not self._cfg:
            return
        cfg = self._cfg
        svc = self._ctx.services.try_get(cfg["svc_key"])
        if not svc:
            QMessageBox.warning(self, "Plugin Not Loaded",
                f"The {cfg['label']} plugin is not currently loaded.")
            return

        selected = [
            self._table.item(i, 0).data(Qt.UserRole)
            for i in range(self._table.rowCount())
            if self._table.item(i, 0)
            and self._table.item(i, 0).checkState() == Qt.Checked
        ]

        added = skipped = 0
        for r in selected:
            ok = cfg["owned_key"](r)
            if ok in self._owned_keys:
                skipped += 1
                continue
            try:
                self._add_item(cfg["svc_key"], svc, r)
                self._owned_keys.add(ok)
                added += 1
            except Exception:
                skipped += 1

        parts = []
        if added:
            parts.append(f"{added:,} added")
        if skipped:
            parts.append(f"{skipped:,} already owned / skipped")
        self._status_lbl.setText("✓  " + ",  ".join(parts) + ".")

        # Repaint owned highlights
        self._apply_filter()

        # Fire refresh event so the relevant plugin tab updates
        _events = {
            "paint_service":    "paints_filter_changed",
            "material_service": "materials_filter_changed",
            "tool_service":     "tools_filter_changed",
            "model_service":    "models_filter_changed",
        }
        evt = _events.get(cfg["svc_key"])
        if evt:
            try:
                self._ctx.event_bus.emit(evt, {"filter": None})
            except Exception:
                pass

    def _add_item(self, svc_key: str, svc, r: dict):
        def _qty(v, default=1, minimum=0):
            try:
                return max(minimum, int(v or default))
            except ValueError:
                return default

        if svc_key == "paint_service":
            color = r.get("color", "#808080")
            if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
                color = "#808080"
            svc.add_paint(
                brand=r.get("brand", "Unknown"),
                name=r.get("name", "Unknown"),
                paint_type=r.get("type", "Base"),
                color=color,
                quantity=_qty(r.get("quantity"), 1, 0),
                notes=r.get("notes") or None,
            )
        elif svc_key == "material_service":
            svc.add_material(
                name=r.get("name", "Unknown"),
                material_type=r.get("type", "Other"),
                brand=r.get("brand", ""),
                color=r.get("color", ""),
                stock=r.get("stock", "Good"),
                quantity=_qty(r.get("quantity"), 1, 0),
                notes=r.get("notes") or None,
            )
        elif svc_key == "tool_service":
            svc.add_tool(
                name=r.get("name", "Unknown"),
                tool_type=r.get("type", "Other"),
                brand=r.get("brand", ""),
                condition=r.get("condition", "Good"),
                quantity=_qty(r.get("quantity"), 1, 0),
                notes=r.get("notes") or None,
            )
        elif svc_key == "model_service":
            svc.add_model(
                name=r.get("name", "Unknown"),
                game_system=r.get("game_system", "Other"),
                faction=r.get("faction", "Unknown"),
                model_type=r.get("type", "Other"),
                status=r.get("status", "Unassembled"),
                scale=r.get("scale", ""),
                quantity=_qty(r.get("quantity"), 1, 1),
                notes=r.get("notes") or None,
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool, msg: str = ""):
        self._progress.setVisible(busy)
        self._fetch_btn.setEnabled(not busy)
        self._tracker_combo.setEnabled(not busy)
        if msg:
            self._status_lbl.setText(msg)


# ══════════════════════════════════════════════════════════════════════════════
# The Forge — main dialog
# ══════════════════════════════════════════════════════════════════════════════

class TheForgeDialog(QDialog):
    """
    The Forge: community library hub.

    Embeds three panes in a tab widget:
      1. Browse & Import  — new BrowsePane
      2. Contribute       — existing CommunityLibraryDialog (close btn hidden)
      3. Import Files     — existing GitHubImportDialog (close/community btns hidden)
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        sc = "⌘⇧G" if sys.platform == "darwin" else "Ctrl+Shift+G"
        self.setWindowTitle(f"The Forge  —  {sc}")
        self.setMinimumSize(960, 700)
        self.resize(1060, 800)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Tab widget ────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        # Tab 1: Browse & Import
        self._browse_pane = BrowsePane(self._ctx)
        self._tabs.addTab(self._browse_pane, "🔍  Browse & Import")

        # Tab 2: Contribute (reuse CommunityLibraryDialog as embedded widget)
        self._contribute_pane = CommunityLibraryDialog(self._ctx, parent=None)
        self._contribute_pane._close_btn.hide()
        self._contribute_pane.setMinimumSize(0, 0)
        self._tabs.addTab(self._contribute_pane, "⬆  Contribute")

        # Tab 3: Import Files (reuse GitHubImportDialog as embedded widget)
        self._import_pane = GitHubImportDialog(self._ctx, parent=None)
        self._import_pane._close_btn.hide()
        self._import_pane._community_btn.hide()  # now lives in its own tab
        self._import_pane.setMinimumSize(0, 0)
        self._tabs.addTab(self._import_pane, "📥  Import Files")

        root.addWidget(self._tabs, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QFrame()
        footer.setStyleSheet(
            "QFrame { border-top: 1px solid rgba(255,255,255,0.08); "
            "background: transparent; }"
        )
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(24, 10, 24, 14)

        close_btn = QPushButton("Close")
        close_btn.setMinimumSize(90, 32)
        close_btn.clicked.connect(self.accept)
        footer_lay.addStretch()
        footer_lay.addWidget(close_btn)

        root.addWidget(footer)
