# ui/plugin_manager_dialog.py
"""
Plugin Manager Dialog
─────────────────────
Lets the user:
  • Reorder plugin tabs (▲ / ▼)
  • Rename plugin tabs (inline edit)
  • Enable / disable non-core plugins (checkbox)

All changes — order, labels, enable/disable — apply immediately.
MainWindow._open_plugin_manager() handles live load/unload via PluginManager.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QLineEdit, QCheckBox,
    QMessageBox, QSizePolicy,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: a single plugin row
# ─────────────────────────────────────────────────────────────────────────────

class _PluginRow(QFrame):
    """One row in the plugin list: [☑] [▲][▼]  Label (editable)  [description]"""

    def __init__(
        self,
        plugin_id: str,
        display_name: str,
        current_label: str,
        description: str,
        is_core: bool,
        is_enabled: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.plugin_id    = plugin_id
        self.is_core      = is_core
        self._is_enabled  = is_core or is_enabled   # core always enabled

        self.setObjectName("pluginRow")
        self.setFixedHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        # ── Enable / disable checkbox ─────────────────────────────────────────
        self._enabled_chk = QCheckBox()
        self._enabled_chk.setChecked(self._is_enabled)
        self._enabled_chk.setToolTip(
            "This is a core plugin and cannot be disabled." if is_core
            else "Toggle to enable or disable this plugin immediately."
        )
        if is_core:
            self._enabled_chk.setEnabled(False)
        lay.addWidget(self._enabled_chk)

        # ── Reorder buttons ───────────────────────────────────────────────────
        btn_up = QPushButton("▲")
        btn_up.setObjectName("reorderBtn")
        btn_up.setFixedSize(26, 26)
        btn_up.setToolTip("Move up")
        btn_up.clicked.connect(self._move_up)

        btn_dn = QPushButton("▼")
        btn_dn.setObjectName("reorderBtn")
        btn_dn.setFixedSize(26, 26)
        btn_dn.setToolTip("Move down")
        btn_dn.clicked.connect(self._move_down)

        if is_core:
            btn_up.setEnabled(False)
            btn_dn.setEnabled(False)

        reorder_col = QVBoxLayout()
        reorder_col.setSpacing(2)
        reorder_col.setContentsMargins(0, 0, 0, 0)
        reorder_col.addWidget(btn_up)
        reorder_col.addWidget(btn_dn)
        lay.addLayout(reorder_col)

        # ── Names column ──────────────────────────────────────────────────────
        names_col = QVBoxLayout()
        names_col.setSpacing(2)
        names_col.setContentsMargins(0, 0, 0, 0)

        # Editable label
        self._label_edit = QLineEdit(current_label or display_name)
        self._label_edit.setObjectName("pluginLabelEdit")
        self._label_edit.setPlaceholderText(display_name)
        self._label_edit.setFixedHeight(26)
        self._label_edit.setMinimumWidth(160)
        self._label_edit.setToolTip("Tab label — edit to rename this tab")
        if is_core:
            self._label_edit.setEnabled(False)
        names_col.addWidget(self._label_edit)

        # Description / plugin ID sub-text
        sub = f"{display_name}  ·  id: {plugin_id}"
        sub_lbl = QLabel(sub)
        sub_lbl.setObjectName("pluginSubLabel")
        sub_lbl.setToolTip(description or "No description available")
        names_col.addWidget(sub_lbl)

        lay.addLayout(names_col, stretch=1)

        # ── Core badge ────────────────────────────────────────────────────────
        if is_core:
            core_badge = QLabel("CORE")
            core_badge.setObjectName("coreBadge")
            core_badge.setFixedHeight(20)
            lay.addWidget(core_badge)

    # ── Public accessors ──────────────────────────────────────────────────────

    @property
    def label(self) -> str:
        return self._label_edit.text().strip()

    @property
    def enabled(self) -> bool:
        return self._enabled_chk.isChecked()

    # ── Move helpers (delegate to parent list) ────────────────────────────────

    def _move_up(self):
        p = self.parent()
        if hasattr(p, "_move_row_up"):
            p._move_row_up(self)

    def _move_down(self):
        p = self.parent()
        if hasattr(p, "_move_row_down"):
            p._move_row_down(self)


# ─────────────────────────────────────────────────────────────────────────────
# Scrollable container that holds all rows and handles reordering
# ─────────────────────────────────────────────────────────────────────────────

class _RowContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)
        self._lay.addStretch()

    # ── Row management ────────────────────────────────────────────────────────

    def add_row(self, row: _PluginRow):
        # Insert before the trailing stretch
        self._lay.insertWidget(self._lay.count() - 1, row)

    def rows(self) -> list[_PluginRow]:
        result = []
        for i in range(self._lay.count()):
            item = self._lay.itemAt(i)
            if item and isinstance(item.widget(), _PluginRow):
                result.append(item.widget())
        return result

    def _move_row_up(self, row: _PluginRow):
        rows = self.rows()
        idx = rows.index(row)
        if idx <= 0:
            return
        # Swap with previous (skip core row — always first)
        if rows[idx - 1].is_core:
            return
        self._swap(idx, idx - 1)

    def _move_row_down(self, row: _PluginRow):
        rows = self.rows()
        idx = rows.index(row)
        if idx >= len(rows) - 1:
            return
        self._swap(idx, idx + 1)

    def _swap(self, i: int, j: int):
        rows = self.rows()
        # Remove both, re-insert in swapped positions
        stretch_idx = self._lay.count() - 1  # the trailing stretch
        self._lay.removeWidget(rows[i])
        self._lay.removeWidget(rows[j])
        # Re-add in correct order
        if i < j:
            self._lay.insertWidget(min(i, stretch_idx - 1), rows[j])
            self._lay.insertWidget(min(i + 1, stretch_idx), rows[i])
        else:
            self._lay.insertWidget(min(j, stretch_idx - 1), rows[i])
            self._lay.insertWidget(min(j + 1, stretch_idx), rows[j])


# ─────────────────────────────────────────────────────────────────────────────
# Main dialog
# ─────────────────────────────────────────────────────────────────────────────

class PluginManagerDialog(QDialog):
    """
    Plugin Manager Dialog.

    Usage:
        dialog = PluginManagerDialog(context, plugins, parent)
        if dialog.exec():
            order, labels, disabled = dialog.get_result()
    """

    def __init__(self, context, plugins: list, parent=None):
        super().__init__(parent)

        self._context  = context
        self._plugins  = plugins
        self._result_order:    list[str]      = []
        self._result_labels:   dict[str, str] = {}
        self._result_disabled: list[str]      = []

        self.setWindowTitle("Manage Plugins")
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)
        self.setModal(True)

        self._build_ui()
        self._populate()
        self._apply_styles()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setObjectName("dialogTitleBar")
        title_bar.setFixedHeight(52)
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("⚙ Manage Plugins")
        title_lbl.setObjectName("dialogTitle")
        tb_lay.addWidget(title_lbl)
        tb_lay.addStretch()
        root.addWidget(title_bar)

        # Subtitle
        sub_lbl = QLabel(
            "Reorder tabs by using ▲▼ arrows  ·  Rename a tab by editing its label  ·  "
            "Check or uncheck to enable / disable plugins instantly"
        )
        sub_lbl.setObjectName("dialogSubtitle")
        sub_lbl.setWordWrap(True)
        sub_lbl.setContentsMargins(20, 8, 20, 4)
        root.addWidget(sub_lbl)

        # Scroll area containing the rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = _RowContainer()
        scroll.setWidget(self._container)
        root.addWidget(scroll, stretch=1)

        # Footer
        footer = QWidget()
        footer.setObjectName("dialogFooter")
        footer.setFixedHeight(52)
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(16, 0, 16, 0)
        f_lay.setSpacing(10)

        self._reset_btn = QPushButton("↺  Reset to Defaults")
        self._reset_btn.setObjectName("secondaryBtn")
        self._reset_btn.clicked.connect(self._on_reset)
        f_lay.addWidget(self._reset_btn)

        f_lay.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("secondaryBtn")
        self._cancel_btn.clicked.connect(self.reject)
        f_lay.addWidget(self._cancel_btn)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setObjectName("primaryBtn")
        self._apply_btn.setDefault(True)
        self._apply_btn.clicked.connect(self._on_apply)
        f_lay.addWidget(self._apply_btn)

        root.addWidget(footer)

    def _populate(self):
        settings = self._context.services.get("settings") if self._context else None
        pm       = self._context.services.get("plugin_manager") if self._context else None

        saved_labels:   dict = {}
        saved_disabled: list = []
        saved_order:    list = []

        if settings:
            try:
                saved_labels   = settings.get("plugin_layout.labels",   {}) or {}
                saved_disabled = settings.get("plugin_layout.disabled", []) or []
                saved_order    = settings.get("plugin_layout.order",    []) or []
            except Exception:
                pass

        # ── Build a combined view of ALL plugins (loaded + disabled) ──────────
        # Loaded plugins come from self._plugins
        loaded_map: dict[str, object] = {
            getattr(p, "plugin_id", ""): p for p in self._plugins
        }

        # All discovered plugins come from plugin_manager.all_manifests
        # (includes ones that were disabled and never loaded)
        all_manifests: dict = {}
        if pm and hasattr(pm, "all_manifests"):
            all_manifests = pm.all_manifests  # {plugin_name: (path, data)}

        # Merge: start with manifest keys, fall back to loaded_map
        all_ids = set(loaded_map.keys()) | set(all_manifests.keys())
        all_ids.discard("")  # remove empty-string key if any

        # ── Determine display order: saved → rest, dashboard always first ─────
        ordered = [pid for pid in saved_order if pid in all_ids]
        ordered += sorted(pid for pid in all_ids if pid not in ordered)
        if "dashboard" in ordered and ordered[0] != "dashboard":
            ordered.remove("dashboard")
            ordered.insert(0, "dashboard")

        # ── Add a row for each plugin ─────────────────────────────────────────
        for pid in ordered:
            # Prefer info from the loaded plugin object; fall back to manifest
            plugin = loaded_map.get(pid)
            manifest_data: dict = {}
            if pid in all_manifests:
                _, manifest_data = all_manifests[pid]

            display_name  = (
                getattr(plugin, "display_name", None)
                or manifest_data.get("name", pid)
            )
            description = (
                getattr(plugin, "description", None)
                or manifest_data.get("description", "")
            )
            current_label = saved_labels.get(pid, "")

            # Core check: dashboard pid, or manifest category == "core"
            is_core = (
                pid == "dashboard"
                or manifest_data.get("category") == "core"
                or manifest_data.get("id") == "dashboard"
            )

            is_enabled = pid not in saved_disabled

            row = _PluginRow(
                plugin_id=pid,
                display_name=display_name,
                current_label=current_label,
                description=description,
                is_core=is_core,
                is_enabled=is_enabled,
            )
            self._container.add_row(row)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_apply(self):
        rows = self._container.rows()

        self._result_order = [r.plugin_id for r in rows]
        self._result_labels = {
            r.plugin_id: r.label
            for r in rows
            if r.label and r.label != self._default_name(r.plugin_id)
        }
        self._result_disabled = [
            r.plugin_id for r in rows
            if not r.enabled and not r.is_core
        ]

        # No confirmation needed — all changes are applied live by MainWindow.
        self.accept()

    def _on_reset(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Reset to Defaults")
        msg.setText(
            "This will reset all tab labels to their default names and "
            "restore the original plugin order.\n\nContinue?"
        )
        msg.setIcon(QMessageBox.Question)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        if msg.exec() != QMessageBox.Yes:
            return

        # Clear labels (empty string = use default) and re-populate
        for row in self._container.rows():
            row._label_edit.setText("")

        # Persist empty labels immediately so get_result() returns empty dict
        settings = self._context.services.get("settings") if self._context else None
        if settings:
            try:
                settings.set("plugin_layout.labels", {})
                settings.set("plugin_layout.order", [])
            except Exception:
                pass

    # ── Public result accessor ─────────────────────────────────────────────────

    def get_result(self) -> tuple[list[str], dict[str, str], list[str]]:
        """Returns (order, labels, disabled) after the dialog is accepted."""
        return self._result_order, self._result_labels, self._result_disabled

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _default_name(self, plugin_id: str) -> str:
        for p in self._plugins:
            if getattr(p, "plugin_id", "") == plugin_id:
                return getattr(p, "display_name", plugin_id)
        # Fall back to manifest name for disabled plugins
        pm = self._context.services.get("plugin_manager") if self._context else None
        if pm and hasattr(pm, "all_manifests") and plugin_id in pm.all_manifests:
            _, data = pm.all_manifests[plugin_id]
            return data.get("name", plugin_id)
        return plugin_id

    # ── Styles ────────────────────────────────────────────────────────────────

    def _apply_styles(self):
        tm = self._context.services.get("theme_manager") if self._context else None

        accent    = tm.token("accent")    if tm else "#0078d4"
        bg        = tm.token("bg_base")   if tm else "#1a1a1a"
        bg_raised = tm.token("bg_raised") if tm else "#1e1e1e"
        bg_input  = tm.token("bg_input")  if tm else "#252525"
        border    = tm.token("border")    if tm else "#2a2a2a"
        text_hi   = tm.token("text_hi")   if tm else "#ffffff"
        text_lo   = tm.token("text_lo")   if tm else "#686868"
        text_dim  = tm.token("text_dim")  if tm else "#484848"

        self.setStyleSheet(f"""
            QDialog {{
                background: {bg};
            }}

            /* ── Title bar ─────────────────────────────────────────────── */
            QWidget#dialogTitleBar {{
                background: {bg_raised};
                border-bottom: 1px solid {border};
            }}
            QLabel#dialogTitle {{
                color: {text_hi};
                font-size: 15px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#dialogSubtitle {{
                color: {text_lo};
                font-size: 11px;
                background: transparent;
                padding: 0 20px;
            }}

            /* ── Plugin rows ───────────────────────────────────────────── */
            QFrame#pluginRow {{
                background: {bg_raised};
                border: 1px solid {border};
                border-radius: 8px;
                margin: 0 16px;
            }}
            QFrame#pluginRow:hover {{
                border-color: {accent};
            }}

            QLineEdit#pluginLabelEdit {{
                background: {bg_input};
                border: 1px solid {border};
                border-radius: 4px;
                color: {text_hi};
                font-size: 13px;
                font-weight: 600;
                padding: 2px 8px;
            }}
            QLineEdit#pluginLabelEdit:focus {{
                border-color: {accent};
            }}
            QLineEdit#pluginLabelEdit:disabled {{
                color: {text_dim};
                background: {bg};
            }}

            QLabel#pluginSubLabel {{
                color: {text_lo};
                font-size: 11px;
                background: transparent;
            }}

            /* Core badge */
            QLabel#coreBadge {{
                background: {accent}33;
                color: {accent};
                border: 1px solid {accent}55;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 700;
                padding: 2px 8px;
            }}

            /* ── Reorder buttons ──────────────────────────────────────── */
            QPushButton#reorderBtn {{
                background: {bg_input};
                border: 1px solid {border};
                border-radius: 4px;
                color: {text_lo};
                font-size: 11px;
            }}
            QPushButton#reorderBtn:hover {{
                background: {bg_raised};
                border-color: {accent};
                color: {text_hi};
            }}
            QPushButton#reorderBtn:disabled {{
                color: {text_dim};
                border-color: {bg_input};
            }}

            /* ── Footer ───────────────────────────────────────────────── */
            QWidget#dialogFooter {{
                background: {bg_raised};
                border-top: 1px solid {border};
            }}

            /* ── Buttons ──────────────────────────────────────────────── */
            QPushButton#primaryBtn {{
                background: {accent};
                border: none;
                border-radius: 6px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 600;
                padding: 6px 20px;
                min-width: 80px;
            }}
            QPushButton#primaryBtn:hover {{
                background: {accent}cc;
            }}
            QPushButton#primaryBtn:pressed {{
                background: {accent}99;
            }}

            QPushButton#secondaryBtn {{
                background: {bg_input};
                border: 1px solid {border};
                border-radius: 6px;
                color: {text_lo};
                font-size: 13px;
                padding: 6px 20px;
                min-width: 80px;
            }}
            QPushButton#secondaryBtn:hover {{
                border-color: {accent};
                color: {text_hi};
            }}

            /* Scrollbar */
            QScrollBar:vertical {{
                background: {bg};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {border};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
