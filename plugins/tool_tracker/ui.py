"""
Tool Tracker — UI
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QMessageBox, QFileDialog, QTabWidget,
    QSizePolicy, QGroupBox, QMenu,
)

from .models import (
    Tool, ToolFilter, ToolStatistics,
    TOOL_TYPES, TOOL_CONDITIONS, CONDITION_COLORS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


def _section(title: str) -> QLabel:
    lbl = QLabel(title)
    lbl.setObjectName("fieldLabel")
    return lbl


# ── Main UI widget ─────────────────────────────────────────────────────────────

class ToolUI(QWidget):
    """Top-level widget for the Tool Tracker tab."""

    COL_BRAND     = 0
    COL_NAME      = 1
    COL_TYPE      = 2
    COL_CONDITION = 3
    COL_QTY       = 4
    COL_NOTES     = 5
    COLUMNS       = ["Brand", "Name", "Type", "Condition", "Qty", "Notes"]

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx          = context
        self._tools:  list[Tool] = []
        self._editing_id: Optional[int] = None
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status)

        self._build_ui()
        self._connect_signals()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Page title
        title_bar = QWidget()
        title_row = QHBoxLayout(title_bar)
        title_row.setContentsMargins(20, 16, 20, 6)
        title_lbl = QLabel("Tool Tracker")
        title_lbl.setObjectName("pageTitle")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        root.addWidget(title_bar)

        # Tab bar
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_collection_tab(), "Collection")
        self._tabs.addTab(self._build_statistics_tab(), "Statistics")
        root.addWidget(self._tabs, stretch=1)

    # ── Collection tab ────────────────────────────────────────────────────────

    def _build_collection_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # ── Add / Edit form ────────────────────────────────────────────────
        form_group = QWidget()
        form_group.setObjectName("formGroup")
        form_lay = QVBoxLayout(form_group)
        form_lay.setContentsMargins(14, 10, 14, 12)
        form_lay.setSpacing(8)

        form_lbl = QLabel("Add / Edit Tool")
        form_lbl.setObjectName("sectionTitle")
        form_lay.addWidget(form_lbl)

        # Row 1: Brand | Name
        r1 = QHBoxLayout()
        r1.setSpacing(10)
        b1 = QVBoxLayout()
        b1.addWidget(_section("Brand"))
        self.brand_input = QComboBox()
        self.brand_input.setEditable(True)
        self.brand_input.setPlaceholderText("e.g. Citadel, Xuron…")
        self.brand_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        b1.addWidget(self.brand_input)
        r1.addLayout(b1, stretch=1)

        b2 = QVBoxLayout()
        b2.addWidget(_section("Name *"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Monopose Clippers")
        b2.addWidget(self.name_input)
        r1.addLayout(b2, stretch=2)
        form_lay.addLayout(r1)

        # Row 2: Type | Condition | Qty
        r2 = QHBoxLayout()
        r2.setSpacing(10)

        b3 = QVBoxLayout()
        b3.addWidget(_section("Type *"))
        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.addItems(TOOL_TYPES)
        b3.addWidget(self.type_combo)
        r2.addLayout(b3, stretch=2)

        b4 = QVBoxLayout()
        b4.addWidget(_section("Condition"))
        self.condition_combo = QComboBox()
        self.condition_combo.addItems(TOOL_CONDITIONS)
        self.condition_combo.setCurrentText("Good")
        b4.addWidget(self.condition_combo)
        r2.addLayout(b4, stretch=1)

        b5 = QVBoxLayout()
        b5.addWidget(_section("Qty"))
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(0, 999)
        self.qty_spin.setValue(1)
        b5.addWidget(self.qty_spin)
        r2.addLayout(b5)
        form_lay.addLayout(r2)

        # Row 3: Notes
        r3 = QVBoxLayout()
        r3.addWidget(_section("Notes"))
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Optional notes…")
        r3.addWidget(self.notes_input)
        form_lay.addLayout(r3)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._add_btn    = QPushButton("Add Tool")
        self._add_btn.setProperty("class", "primary")
        self._update_btn = QPushButton("Save Changes")
        self._update_btn.setProperty("class", "primary")
        self._update_btn.setVisible(False)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setVisible(False)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setProperty("class", "danger")
        self._delete_btn.setVisible(False)
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("fieldLabel")

        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._update_btn)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._status_lbl)
        form_lay.addLayout(btn_row)

        lay.addWidget(form_group)

        # ── Filter / search bar ────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        filter_row.addWidget(QLabel("Search:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Name, brand or notes…")
        self._search_input.setClearButtonEnabled(True)
        filter_row.addWidget(self._search_input, stretch=2)

        filter_row.addWidget(QLabel("Type:"))
        self._type_filter = QComboBox()
        self._type_filter.addItem("All Types")
        self._type_filter.addItems(TOOL_TYPES)
        self._type_filter.setMinimumWidth(160)
        filter_row.addWidget(self._type_filter)

        filter_row.addWidget(QLabel("Condition:"))
        self._cond_filter = QComboBox()
        self._cond_filter.addItem("All Conditions")
        self._cond_filter.addItems(TOOL_CONDITIONS)
        self._cond_filter.setMinimumWidth(130)
        filter_row.addWidget(self._cond_filter)

        self._export_btn = QPushButton("Export CSV…")
        filter_row.addWidget(self._export_btn)

        lay.addLayout(filter_row)

        # ── Tools table ────────────────────────────────────────────────────
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_BRAND,     QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_NAME,      QHeaderView.Stretch)
        hh.setSectionResizeMode(self.COL_TYPE,      QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_CONDITION, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_QTY,       QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_NOTES,     QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.setSortingEnabled(True)
        lay.addWidget(self.table, stretch=1)

        # Count label
        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("fieldLabel")
        lay.addWidget(self._count_lbl)

        return w

    # ── Statistics tab ────────────────────────────────────────────────────────

    def _build_statistics_tab(self) -> QWidget:
        outer = QWidget()
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(16)

        # Stat cards
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.stat_total_label     = QLabel("0")
        self.stat_types_label     = QLabel("0")
        self.stat_brands_label    = QLabel("0")
        self.stat_attention_label = QLabel("0")
        cards.addWidget(self._stat_card("Total Tools",    self.stat_total_label))
        cards.addWidget(self._stat_card("Categories",     self.stat_types_label))
        cards.addWidget(self._stat_card("Brands",         self.stat_brands_label))
        cards.addWidget(self._stat_card("Need Attention", self.stat_attention_label,
                                        warn_color=True))
        lay.addLayout(cards)

        # Distribution tables
        dist = QHBoxLayout()
        dist.setSpacing(12)
        self.type_dist_table  = self._dist_table(["Type",      "Count"])
        self.cond_dist_table  = self._dist_table(["Condition", "Count"])
        self.brand_dist_table = self._dist_table(["Brand",     "Count"])
        dist.addWidget(self._dist_group("By Type",      self.type_dist_table))
        dist.addWidget(self._dist_group("By Condition", self.cond_dist_table))
        dist.addWidget(self._dist_group("By Brand",     self.brand_dist_table))
        lay.addLayout(dist, stretch=1)

        return outer

    def _stat_card(self, title: str, value_lbl: QLabel,
                   warn_color: bool = False) -> QGroupBox:
        box = QGroupBox(title)
        lyt = QVBoxLayout(box)
        lyt.setAlignment(Qt.AlignCenter)
        color = "#e07820" if warn_color else "#0078d4"
        value_lbl.setStyleSheet(
            f"font-size: 42px; font-weight: 700; color: {color};"
        )
        value_lbl.setAlignment(Qt.AlignCenter)
        lyt.addWidget(value_lbl)
        return box

    def _dist_table(self, headers: list) -> QTableWidget:
        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        t.setShowGrid(False)
        return t

    def _dist_group(self, title: str, table: QTableWidget) -> QGroupBox:
        box = QGroupBox(title)
        QVBoxLayout(box).addWidget(table)
        return box

    # ── Signal wiring ──────────────────────────────────────────────────────────

    def _connect_signals(self):
        self._add_btn.clicked.connect(self._handle_add)
        self._update_btn.clicked.connect(self._handle_update)
        self._cancel_btn.clicked.connect(self._cancel_edit)
        self._delete_btn.clicked.connect(self._handle_delete)
        self._export_btn.clicked.connect(self._handle_export)
        self._search_input.textChanged.connect(self._emit_filter)
        self._type_filter.currentTextChanged.connect(self._emit_filter)
        self._cond_filter.currentTextChanged.connect(self._emit_filter)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

    # ── Public API (called by plugin) ──────────────────────────────────────────

    def display_tools(self, tools: list[Tool], brands: list[str] = None):
        self._tools = tools

        # Refresh brand combo from live data
        if brands is not None:
            current_brand = self.brand_input.currentText()
            self.brand_input.blockSignals(True)
            self.brand_input.clear()
            self.brand_input.addItems(brands)
            self.brand_input.setCurrentText(current_brand)
            self.brand_input.blockSignals(False)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for tool in tools:
            row = self.table.rowCount()
            self.table.insertRow(row)

            items = [
                QTableWidgetItem(tool.brand or ""),
                QTableWidgetItem(tool.name),
                QTableWidgetItem(tool.tool_type),
                QTableWidgetItem(tool.condition),
                QTableWidgetItem(str(tool.quantity)),
                QTableWidgetItem(tool.notes or ""),
            ]

            # Condition color highlight for Worn / Replace rows
            row_bg = None
            if tool.condition == "Replace":
                row_bg = QColor("#3d1515")
            elif tool.condition == "Worn":
                row_bg = QColor("#362410")

            for col, item in enumerate(items):
                item.setData(Qt.UserRole, tool.id)
                if row_bg:
                    item.setBackground(row_bg)
                self.table.setItem(row, col, item)

            # Color the condition cell text to match condition
            cond_item = self.table.item(row, self.COL_CONDITION)
            color_hex = CONDITION_COLORS.get(tool.condition, "")
            if color_hex and cond_item:
                cond_item.setForeground(QColor(color_hex))

        self.table.setSortingEnabled(True)
        total = len(tools)
        replace_count = sum(1 for t in tools if t.condition in ("Worn", "Replace"))
        text = f"{total} tool{'s' if total != 1 else ''}"
        if replace_count:
            text += f"  ·  ⚠ {replace_count} need attention"
        self._count_lbl.setText(text)

    def update_statistics(self, stats: ToolStatistics):
        self.stat_total_label.setText(str(stats.total_count))
        self.stat_types_label.setText(str(stats.unique_types))
        self.stat_brands_label.setText(str(stats.unique_brands))
        self.stat_attention_label.setText(str(stats.needs_replacement))

        def _fill(t, data):
            t.setRowCount(len(data))
            for i, (k, v) in enumerate(sorted(data.items())):
                t.setItem(i, 0, QTableWidgetItem(k or "(None)"))
                t.setItem(i, 1, QTableWidgetItem(str(v)))

        _fill(self.type_dist_table,  stats.types_distribution)
        _fill(self.cond_dist_table,  stats.conditions_distribution)
        _fill(self.brand_dist_table, stats.brands_distribution)

    # ── Form helpers ──────────────────────────────────────────────────────────

    def _clear_form(self):
        self.name_input.clear()
        self.brand_input.setCurrentText("")
        self.type_combo.setCurrentIndex(0)
        self.condition_combo.setCurrentText("Good")
        self.qty_spin.setValue(1)
        self.notes_input.clear()
        self._editing_id = None
        self._add_btn.setVisible(True)
        self._update_btn.setVisible(False)
        self._cancel_btn.setVisible(False)
        self._delete_btn.setVisible(False)
        self.table.clearSelection()

    def _populate_form(self, tool: Tool):
        self.name_input.setText(tool.name)
        self.brand_input.setCurrentText(tool.brand or "")
        self.type_combo.setCurrentText(tool.tool_type)
        self.condition_combo.setCurrentText(tool.condition)
        self.qty_spin.setValue(tool.quantity)
        self.notes_input.setText(tool.notes or "")
        self._editing_id = tool.id
        self._add_btn.setVisible(False)
        self._update_btn.setVisible(True)
        self._cancel_btn.setVisible(True)
        self._delete_btn.setVisible(True)

    def _form_payload(self) -> dict:
        return {
            "name":      self.name_input.text().strip(),
            "tool_type": self.type_combo.currentText().strip(),
            "brand":     self.brand_input.currentText().strip(),
            "condition": self.condition_combo.currentText(),
            "quantity":  self.qty_spin.value(),
            "notes":     self.notes_input.text().strip() or None,
        }

    # ── Action handlers ────────────────────────────────────────────────────────

    def _handle_add(self):
        payload = self._form_payload()
        if not payload["name"]:
            self._show_error("Name is required")
            return
        if not payload["tool_type"]:
            self._show_error("Type is required")
            return
        self._ctx.event_bus.emit("tool_added", payload)

    def _handle_update(self):
        if self._editing_id is None:
            return
        payload = self._form_payload()
        payload["id"] = self._editing_id
        if not payload["name"]:
            self._show_error("Name is required")
            return
        self._ctx.event_bus.emit("tool_updated", payload)

    def _handle_delete(self):
        if self._editing_id is None:
            return
        tool = next((t for t in self._tools if t.id == self._editing_id), None)
        label = f'"{tool.name}"' if tool else "this tool"
        reply = QMessageBox.question(
            self, "Delete Tool",
            f"Delete {label}? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            self._ctx.event_bus.emit("tool_removed", {"id": self._editing_id})
            self._cancel_edit()

    def _cancel_edit(self):
        self._clear_form()

    def _handle_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Tools", "tools.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Brand", "Name", "Type", "Condition", "Qty", "Notes"])
                for tool in self._tools:
                    writer.writerow([
                        tool.brand, tool.name, tool.tool_type,
                        tool.condition, tool.quantity, tool.notes or "",
                    ])
            self._show_success(f"Exported {len(self._tools)} tool(s)")
        except Exception as e:
            self._show_error(f"Export failed: {e}")

    # ── Selection & context menu ───────────────────────────────────────────────

    def _on_selection_changed(self):
        rows = self.table.selectedItems()
        if not rows:
            self._clear_form()
            return
        tool_id = self.table.item(self.table.currentRow(), 0).data(Qt.UserRole)
        tool = next((t for t in self._tools if t.id == tool_id), None)
        if tool:
            self._populate_form(tool)

    def _show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        tool_id = self.table.item(row, 0).data(Qt.UserRole)
        tool = next((t for t in self._tools if t.id == tool_id), None)
        if not tool:
            return

        menu = QMenu(self)

        # Condition shortcuts
        cond_menu = menu.addMenu("Set Condition")
        for cond in TOOL_CONDITIONS:
            act = cond_menu.addAction(cond)
            act.triggered.connect(
                lambda checked=False, t=tool, c=cond: self._quick_set_condition(t, c)
            )
        menu.addSeparator()

        qty_up   = menu.addAction("+1 Quantity")
        qty_down = menu.addAction("−1 Quantity")
        qty_up.triggered.connect(lambda: self._quick_qty(tool, 1))
        qty_down.triggered.connect(lambda: self._quick_qty(tool, -1))
        menu.addSeparator()

        edit_act   = menu.addAction("Edit…")
        delete_act = menu.addAction("Delete")
        edit_act.triggered.connect(lambda: self._populate_form(tool))
        delete_act.triggered.connect(lambda: self._handle_delete_tool(tool))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _quick_set_condition(self, tool: Tool, condition: str):
        self._ctx.event_bus.emit("tool_updated", {
            "id":        tool.id,
            "name":      tool.name,
            "tool_type": tool.tool_type,
            "brand":     tool.brand,
            "condition": condition,
            "quantity":  tool.quantity,
            "notes":     tool.notes,
        })

    def _quick_qty(self, tool: Tool, delta: int):
        new_qty = max(0, tool.quantity + delta)
        self._ctx.event_bus.emit("tool_updated", {
            "id":        tool.id,
            "name":      tool.name,
            "tool_type": tool.tool_type,
            "brand":     tool.brand,
            "condition": tool.condition,
            "quantity":  new_qty,
            "notes":     tool.notes,
        })

    def _handle_delete_tool(self, tool: Tool):
        reply = QMessageBox.question(
            self, "Delete Tool",
            f'Delete "{tool.name}"? This cannot be undone.',
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            self._ctx.event_bus.emit("tool_removed", {"id": tool.id})
            self._cancel_edit()

    # ── Filter emission ────────────────────────────────────────────────────────

    def _emit_filter(self):
        f = ToolFilter(
            search_text=self._search_input.text().strip() or None,
            tool_type=(
                self._type_filter.currentText()
                if self._type_filter.currentText() != "All Types" else None
            ),
            condition=(
                self._cond_filter.currentText()
                if self._cond_filter.currentText() != "All Conditions" else None
            ),
        )
        self._ctx.event_bus.emit("tools_filter_changed", {"filter": f})

    # ── Status messages ────────────────────────────────────────────────────────

    def _show_success(self, msg: str):
        self._status_lbl.setStyleSheet("color: #3dba6e; font-size: 12px;")
        self._status_lbl.setText(f"✓ {msg}")
        self._status_timer.start(3000)

    def _show_error(self, msg: str):
        self._status_lbl.setStyleSheet("color: #e05555; font-size: 12px;")
        self._status_lbl.setText(f"✗ {msg}")
        self._status_timer.start(5000)

    def _clear_status(self):
        self._status_lbl.setText("")
