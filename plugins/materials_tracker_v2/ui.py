"""
Materials Tracker 2.0 — Premium UI
Clean card grid with stock-level indicators, type icons, and inline quick-add.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

import csv
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize, Signal
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QGridLayout, QSpinBox, QTextEdit, QMessageBox, QFileDialog,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)

from plugins.materials_tracker.models import (
    Material, MaterialFilter, MATERIAL_TYPES, STOCK_LEVELS,
)
from plugins.materials_tracker.models import ValidationError

# ── Card geometry ──────────────────────────────────────────────────────────────
_CARD_W    = 176
_CARD_H    = 186
_CARD_GAP  = 12

# ── Stock colours ──────────────────────────────────────────────────────────────
_STOCK_FG: dict[str, str] = {
    "Full":     "#3dba6e",
    "Good":     "#4f9eff",
    "Low":      "#e07800",
    "Empty":    "#e05555",
    "On Order": "#a855f7",
}
_STOCK_BG: dict[str, str] = {
    "Full":     "rgba(61,186,110,0.13)",
    "Good":     "rgba(79,158,255,0.13)",
    "Low":      "rgba(224,120,0,0.18)",
    "Empty":    "rgba(224,85,85,0.20)",
    "On Order": "rgba(168,85,247,0.15)",
}

# ── Type icons ─────────────────────────────────────────────────────────────────
_TYPE_ICONS: dict[str, str] = {
    "Static Grass":    "🌱",
    "Tufts":           "🌿",
    "Sand / Ballast":  "🏖",
    "Gravel / Grit":   "🪨",
    "Stones / Rocks":  "⛰",
    "Leaves / Foliage":"🍂",
    "Moss / Lichen":   "🟢",
    "Bark / Cork":     "🪵",
    "Snow Effect":     "❄️",
    "Water Effect":    "💧",
    "Texture Medium":  "🎨",
    "Technical Paint": "🖌",
    "Pigment Powder":  "✨",
    "Resin / Epoxy":   "💎",
    "Foam":            "🧽",
    "Flock":           "🌾",
    "Scenic Bits":     "🎭",
    "Basing Kit":      "📦",
    "Other":           "📦",
}


def _type_icon(t: str) -> str:
    return _TYPE_ICONS.get(t, "📦")

def _stock_fg(s: str) -> str:
    return _STOCK_FG.get(s, "#808080")

def _stock_bg(s: str) -> str:
    return _STOCK_BG.get(s, "rgba(128,128,128,0.12)")


# ══════════════════════════════════════════════════════════════════════════════
#  Material Card
# ══════════════════════════════════════════════════════════════════════════════

class _MaterialCard(QFrame):
    edit_requested   = Signal(object)
    delete_requested = Signal(object)

    # Card colours — match paint_tracker_v2 exactly for visual cohesion
    _BG        = "#1c1c1c"
    _BG_HOVER  = "#252525"
    _BORDER    = "#2e2e2e"
    _BORDER_HV = "#3a3a3a"
    _DIV       = "#2a2a2a"
    _FG_HI     = "#f0f0f0"
    _FG_LO     = "#686868"

    def __init__(self, material: Material, parent=None):
        super().__init__(parent)
        self._mat = material
        self._build()

    def _build(self):
        self.setObjectName("matCard")
        self.setFixedSize(_CARD_W, _CARD_H)
        self.setCursor(Qt.PointingHandCursor)

        self.setStyleSheet(f"""
            QFrame#matCard {{
                background-color: {self._BG};
                border: 1px solid {self._BORDER};
                border-radius: 12px;
            }}
            QFrame#matCard:hover {{
                background-color: {self._BG_HOVER};
                border-color: {self._BORDER_HV};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(0)

        # ── Top row: icon  ·  spacer  ·  stock chip ───────────────────────────
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(0)

        icon_lbl = QLabel(_type_icon(self._mat.material_type))
        icon_lbl.setStyleSheet(
            "font-size: 24px; background: transparent; border: none; padding: 0;"
        )
        top.addWidget(icon_lbl)
        top.addStretch()

        sfg = _stock_fg(self._mat.stock)
        sbg = _stock_bg(self._mat.stock)
        stock_chip = QLabel(self._mat.stock)
        stock_chip.setStyleSheet(f"""
            color: {sfg};
            background: {sbg};
            font-size: 9px;
            font-weight: bold;
            letter-spacing: 0.3px;
            padding: 2px 7px;
            border-radius: 5px;
            border: none;
        """)
        stock_chip.setAlignment(Qt.AlignCenter)
        top.addWidget(stock_chip)
        root.addLayout(top)

        root.addSpacing(10)

        # ── Name ───────────────────────────────────────────────────────────────
        name_lbl = QLabel(self._mat.name)
        name_lbl.setStyleSheet(f"""
            font-size: 13px;
            font-weight: 700;
            color: {self._FG_HI};
            background: transparent;
            border: none;
        """)
        name_lbl.setWordWrap(True)
        # Allow exactly 2 lines max
        name_lbl.setMaximumHeight(38)
        root.addWidget(name_lbl)

        root.addSpacing(4)

        # ── Brand · Variant ────────────────────────────────────────────────────
        brand_parts = [x for x in [self._mat.brand, self._mat.color] if x]
        sub_str = " · ".join(brand_parts) if brand_parts else ""
        if sub_str:
            sub_lbl = QLabel(sub_str)
            sub_lbl.setStyleSheet(f"""
                font-size: 11px;
                color: {self._FG_LO};
                background: transparent;
                border: none;
            """)
            sub_lbl.setWordWrap(True)
            sub_lbl.setMaximumHeight(28)
            root.addWidget(sub_lbl)

        root.addStretch()

        # ── Divider ────────────────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background: {self._DIV}; border: none; max-height: 1px;")
        div.setFixedHeight(1)
        root.addWidget(div)

        root.addSpacing(8)

        # ── Bottom row: type label · spacer · qty ──────────────────────────────
        bot = QHBoxLayout()
        bot.setContentsMargins(0, 0, 0, 0)
        bot.setSpacing(0)

        type_lbl = QLabel(self._mat.material_type)
        type_lbl.setStyleSheet(f"""
            font-size: 10px;
            color: {self._FG_LO};
            background: transparent;
            border: none;
        """)
        bot.addWidget(type_lbl)

        bot.addStretch()

        if self._mat.quantity != 1:
            qty_lbl = QLabel(f"×{self._mat.quantity}")
            qty_lbl.setStyleSheet(f"""
                font-size: 11px;
                font-weight: 600;
                color: {self._FG_LO};
                background: transparent;
                border: none;
            """)
            bot.addWidget(qty_lbl)

        root.addLayout(bot)

    def mouseDoubleClickEvent(self, event):
        self.edit_requested.emit(self._mat)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        edit_act   = menu.addAction("✏  Edit")
        menu.addSeparator()
        delete_act = menu.addAction("🗑  Delete")
        act = menu.exec(event.globalPos())
        if act == edit_act:
            self.edit_requested.emit(self._mat)
        elif act == delete_act:
            self.delete_requested.emit(self._mat)


# ══════════════════════════════════════════════════════════════════════════════
#  Quick-Add Bar
# ══════════════════════════════════════════════════════════════════════════════

class _QuickAddBar(QWidget):
    submitted = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._build()
        self.setVisible(False)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("quickAddCard")
        cl = QVBoxLayout(self._card)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(10)

        # Row 1 — Name + Type
        r1 = QHBoxLayout()
        r1.setSpacing(8)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Material name *")
        self._name_edit.setMinimumWidth(200)
        r1.addWidget(self._name_edit, 3)

        self._type_combo = QComboBox()
        self._type_combo.addItems(MATERIAL_TYPES)
        r1.addWidget(self._type_combo, 2)
        cl.addLayout(r1)

        # Row 2 — Brand + Variant + Stock + Qty
        r2 = QHBoxLayout()
        r2.setSpacing(8)
        self._brand_edit = QLineEdit()
        self._brand_edit.setPlaceholderText("Brand")
        r2.addWidget(self._brand_edit, 2)

        self._variant_edit = QLineEdit()
        self._variant_edit.setPlaceholderText("Variant / colour")
        r2.addWidget(self._variant_edit, 2)

        self._stock_combo = QComboBox()
        self._stock_combo.addItems(STOCK_LEVELS)
        self._stock_combo.setCurrentText("Good")
        r2.addWidget(self._stock_combo, 1)

        qty_lbl = QLabel("Qty")
        qty_lbl.setFixedWidth(24)
        r2.addWidget(qty_lbl)
        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(0, 9999)
        self._qty_spin.setValue(1)
        self._qty_spin.setFixedWidth(64)
        r2.addWidget(self._qty_spin)
        cl.addLayout(r2)

        # Row 3 — Notes + buttons
        r3 = QHBoxLayout()
        r3.setSpacing(8)
        self._notes_edit = QLineEdit()
        self._notes_edit.setPlaceholderText("Notes (optional)")
        r3.addWidget(self._notes_edit, 1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.collapse)
        r3.addWidget(cancel_btn)

        self._add_btn = QPushButton("Add Material")
        self._add_btn.setObjectName("primaryBtn")
        self._add_btn.setFixedWidth(120)
        self._add_btn.clicked.connect(self._on_submit)
        r3.addWidget(self._add_btn)
        cl.addLayout(r3)

        lay.addWidget(self._card)
        self._name_edit.returnPressed.connect(self._on_submit)

    def expand(self):
        self._expanded = True
        self.setVisible(True)
        self._name_edit.clear()
        self._brand_edit.clear()
        self._variant_edit.clear()
        self._notes_edit.clear()
        self._qty_spin.setValue(1)
        self._stock_combo.setCurrentText("Good")
        QTimer.singleShot(50, self._name_edit.setFocus)

    def collapse(self):
        self._expanded = False
        self.setVisible(False)

    def is_expanded(self) -> bool:
        return self._expanded

    def _on_submit(self):
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setFocus()
            self._name_edit.setStyleSheet("border: 1px solid #e05555;")
            return
        self._name_edit.setStyleSheet("")
        self.submitted.emit({
            "name":          name,
            "material_type": self._type_combo.currentText(),
            "brand":         self._brand_edit.text().strip(),
            "color":         self._variant_edit.text().strip(),
            "stock":         self._stock_combo.currentText(),
            "quantity":      self._qty_spin.value(),
            "notes":         self._notes_edit.text().strip() or None,
        })
        self.collapse()


# ══════════════════════════════════════════════════════════════════════════════
#  Edit Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _EditDialog(QDialog):
    def __init__(self, material: Optional[Material] = None, context=None, parent=None):
        super().__init__(parent)
        self._mat     = material
        self._context = context
        self.setWindowTitle("Edit Material" if material else "Add Material")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build()
        if material:
            self._populate(material)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(14)

        title = QLabel("Edit Material" if self._mat else "Add Material")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(title)

        form = QGridLayout()
        form.setSpacing(10)
        form.setColumnStretch(1, 1)
        form.setColumnMinimumWidth(0, 110)

        def _row(label, widget, row):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.50);")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.addWidget(lbl,    row, 0)
            form.addWidget(widget, row, 1)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Required")
        _row("Name *", self._name_edit, 0)

        self._type_combo = QComboBox()
        self._type_combo.addItems(MATERIAL_TYPES)
        _row("Type *", self._type_combo, 1)

        self._brand_edit = QLineEdit()
        self._brand_edit.setPlaceholderText("e.g. Vallejo, GW, Army Painter")
        _row("Brand", self._brand_edit, 2)

        self._variant_edit = QLineEdit()
        self._variant_edit.setPlaceholderText("e.g. Dark Ochre, Fine Grade")
        _row("Variant / Colour", self._variant_edit, 3)

        self._stock_combo = QComboBox()
        self._stock_combo.addItems(STOCK_LEVELS)
        _row("Stock Level", self._stock_combo, 4)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(0, 9999)
        self._qty_spin.setValue(1)
        _row("Quantity", self._qty_spin, 5)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Any notes about this material…")
        self._notes_edit.setFixedHeight(68)
        _row("Notes", self._notes_edit, 6)

        lay.addLayout(form)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        lay.addWidget(div)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _populate(self, m: Material):
        self._name_edit.setText(m.name)
        idx = self._type_combo.findText(m.material_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._brand_edit.setText(m.brand or "")
        self._variant_edit.setText(m.color or "")
        sidx = self._stock_combo.findText(m.stock)
        if sidx >= 0:
            self._stock_combo.setCurrentIndex(sidx)
        self._qty_spin.setValue(m.quantity)
        self._notes_edit.setPlainText(m.notes or "")

    def _validate_and_accept(self):
        if not self._name_edit.text().strip():
            self._name_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name":          self._name_edit.text().strip(),
            "material_type": self._type_combo.currentText(),
            "brand":         self._brand_edit.text().strip(),
            "color":         self._variant_edit.text().strip(),
            "stock":         self._stock_combo.currentText(),
            "quantity":      self._qty_spin.value(),
            "notes":         self._notes_edit.toPlainText().strip() or None,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Toast
# ══════════════════════════════════════════════════════════════════════════════

class _Toast(QLabel):
    def __init__(self, message: str, parent=None, *, action_label: str = "", action_cb=None):
        super().__init__(parent)
        self._action_cb    = action_cb
        self._action_label = action_label
        self._build(message)
        QTimer.singleShot(4000, self._fade)

    def _build(self, message: str):
        self.setObjectName("toastLabel")
        full = message
        if self._action_label:
            full += f"   <a href='action' style='color:#4f9eff;'>{self._action_label}</a>"
            self.setTextFormat(Qt.RichText)
            self.linkActivated.connect(self._on_link)
        self.setText(full)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel#toastLabel {
                background: rgba(22,22,30,0.96);
                color: #e8e8ee;
                font-size: 12px;
                padding: 9px 20px;
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.10);
            }
        """)
        self.adjustSize()

    def _on_link(self, href):
        if href == "action" and self._action_cb:
            self._action_cb()
            self.hide()

    def _fade(self):
        self.hide()
        self.deleteLater()


# ══════════════════════════════════════════════════════════════════════════════
#  Main UI
# ══════════════════════════════════════════════════════════════════════════════

class MaterialsTrackerV2UI(QWidget):

    # sort column indices
    _COL_ICON    = 0
    _COL_NAME    = 1
    _COL_BRAND   = 2
    _COL_VARIANT = 3
    _COL_TYPE    = 4
    _COL_STOCK   = 5
    _COL_QTY     = 6
    _COL_NOTES   = 7

    def __init__(self, service, context=None, parent=None):
        super().__init__(parent)
        self._svc              = service
        self._ctx              = context
        self._all_materials:   list[Material] = []
        self._filtered:        list[Material] = []
        self._view_mode        = "table"
        self._undo_material: Optional[Material] = None
        self._sort_col         = self._COL_NAME
        self._sort_desc        = False

        self._build()
        self._apply_theme()
        QTimer.singleShot(0, self.refresh)

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        self._quick_add = _QuickAddBar()
        self._quick_add.submitted.connect(self._on_quick_add)
        root.addWidget(self._quick_add)
        root.addWidget(self._build_filter_bar())

        self._stack = QStackedWidget()
        self._cards_page = self._build_cards_page()
        self._table_page = self._build_table_page()
        self._stack.addWidget(self._cards_page)
        self._stack.addWidget(self._table_page)
        root.addWidget(self._stack, stretch=1)

        root.addWidget(self._build_status_bar())

        # Start in table view
        self._stack.setCurrentIndex(1)

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("matHeader")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(22, 14, 16, 14)
        lay.setSpacing(12)

        # Title block
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title_col.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Materials")
        title.setStyleSheet("font-size: 18px; font-weight: 700; letter-spacing: -0.3px;")
        title_col.addWidget(title)

        subtitle = QLabel("Basing materials & scenic supplies")
        subtitle.setObjectName("matSubtitle")
        subtitle.setStyleSheet("font-size: 11px;")
        title_col.addWidget(subtitle)

        lay.addLayout(title_col)
        lay.addStretch()

        # View toggle group
        toggle_frame = QFrame()
        toggle_frame.setObjectName("viewToggleGroup")
        toggle_lay = QHBoxLayout(toggle_frame)
        toggle_lay.setContentsMargins(3, 3, 3, 3)
        toggle_lay.setSpacing(2)

        self._card_view_btn = QPushButton("⊞")
        self._card_view_btn.setObjectName("viewToggle")          # inactive — starts in table mode
        self._card_view_btn.setFixedSize(30, 26)
        self._card_view_btn.setToolTip("Card view")
        self._card_view_btn.clicked.connect(lambda: self._set_view("cards"))
        toggle_lay.addWidget(self._card_view_btn)

        self._table_view_btn = QPushButton("☰")
        self._table_view_btn.setObjectName("viewToggleActive")   # active — table is default
        self._table_view_btn.setFixedSize(30, 26)
        self._table_view_btn.setToolTip("Table view")
        self._table_view_btn.clicked.connect(lambda: self._set_view("table"))
        toggle_lay.addWidget(self._table_view_btn)

        lay.addWidget(toggle_frame)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        lay.addWidget(sep)

        export_btn = QPushButton("⬇  Export")
        export_btn.setObjectName("secondaryBtn")
        export_btn.setFixedHeight(32)
        export_btn.setToolTip("Export filtered list to CSV")
        export_btn.clicked.connect(self._export_csv)
        lay.addWidget(export_btn)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setFixedWidth(1)
        lay.addWidget(sep2)

        add_btn = QPushButton("＋  Add Material")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self.handle_quick_create)
        lay.addWidget(add_btn)

        return bar

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("matFilterBar")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        # Preset chips
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        chip_row.setContentsMargins(0, 0, 0, 0)
        self._preset_btns: dict[str, QPushButton] = {}
        for key, label in [
            ("all",      "All"),
            ("low",      "Low Stock"),
            ("empty",    "Out of Stock"),
            ("on_order", "On Order"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("chipActive" if key == "all" else "chip")
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda _, k=key: self._apply_preset_chip(k))
            self._preset_btns[key] = btn
            chip_row.addWidget(btn)
        chip_row.addStretch()
        lay.addLayout(chip_row)

        # Search + filters
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.setContentsMargins(0, 0, 0, 0)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search…")
        self._search_edit.setObjectName("searchInput")
        self._search_edit.setMinimumWidth(180)
        self._search_edit.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._search_edit, 2)

        self._type_filter = QComboBox()
        self._type_filter.addItem("All Types")
        self._type_filter.addItems(MATERIAL_TYPES)
        self._type_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._type_filter, 2)

        self._brand_filter = QComboBox()
        self._brand_filter.addItem("All Brands")
        self._brand_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._brand_filter, 1)

        self._stock_filter = QComboBox()
        self._stock_filter.addItem("All Stock")
        self._stock_filter.addItems(STOCK_LEVELS)
        self._stock_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._stock_filter, 1)

        lay.addLayout(filter_row)
        return bar

    def _build_cards_page(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidget(QWidget())
        lay.addWidget(self._scroll)
        return page

    def _card_cols(self) -> int:
        vp_w = self._scroll.viewport().width()
        if vp_w < _CARD_W:
            vp_w = max(_CARD_W, self.width() - 32)
        return max(1, (vp_w - _CARD_GAP) // (_CARD_W + _CARD_GAP))

    def _build_table_page(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "", "Name", "Brand", "Variant", "Type", "Stock", "Qty", "Notes",
        ])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(self._COL_ICON,    QHeaderView.Fixed)
        hdr.setSectionResizeMode(self._COL_NAME,    QHeaderView.Stretch)
        hdr.setSectionResizeMode(self._COL_BRAND,   QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_VARIANT, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_TYPE,    QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_STOCK,   QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_QTY,     QHeaderView.Fixed)
        hdr.setSectionResizeMode(self._COL_NOTES,   QHeaderView.Fixed)
        self._table.setColumnWidth(self._COL_ICON,  36)
        self._table.setColumnWidth(self._COL_QTY,   52)
        self._table.setColumnWidth(self._COL_NOTES, 52)

        # Sortable headers — click a column header to sort
        hdr.setSectionsClickable(True)
        hdr.sectionClicked.connect(self._on_header_clicked)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(self._COL_NAME, Qt.AscendingOrder)

        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setIconSize(QSize(20, 20))
        self._table.doubleClicked.connect(self._on_table_double_click)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

        # Keyboard shortcuts: Del → delete, Enter → edit
        self._table.keyPressEvent = self._table_key_press

        lay.addWidget(self._table)
        return page

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("matStatusBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 6, 20, 7)
        lay.setSpacing(0)

        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("statusCount")
        lay.addWidget(self._status_lbl)

        lay.addStretch()

        # Stock distribution dots
        self._stock_pills: dict[str, QLabel] = {}
        for i, stock in enumerate(STOCK_LEVELS):
            if i > 0:
                sep = QLabel("·")
                sep.setStyleSheet("color: rgba(255,255,255,0.15); font-size: 11px; padding: 0 4px;")
                lay.addWidget(sep)
                sep.hide()
                sep.setObjectName(f"stockSep_{stock}")

            pill = QLabel()
            fg = _stock_fg(stock)
            pill.setStyleSheet(f"""
                color: {fg};
                font-size: 11px;
                font-weight: 600;
                padding: 0;
                background: transparent;
            """)
            pill.hide()
            lay.addWidget(pill)
            self._stock_pills[stock] = pill

        return bar

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(self):
        try:
            self._all_materials = self._svc.get_all_materials()
            self._update_brand_filter()
            self._apply_filters()
        except Exception as e:
            log.error(f"[MATERIALS V2 UI] refresh: {e}")

    def handle_quick_create(self):
        if not self._quick_add.is_expanded():
            self._quick_add.expand()
        else:
            self._quick_add.collapse()

    def apply_preset(self, preset: str):
        if preset == "add":
            self.handle_quick_create()
            return
        self._apply_preset_chip(preset)

    # ── Preset chips ──────────────────────────────────────────────────────────

    def _apply_preset_chip(self, key: str):
        for k, btn in self._preset_btns.items():
            active = (k == key)
            btn.setObjectName("chipActive" if active else "chip")
            btn.setChecked(active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        mapping = {"all": "All Stock", "low": "Low", "empty": "Empty", "on_order": "On Order"}
        target = mapping.get(key, "All Stock")
        idx = self._stock_filter.findText(target)
        if idx >= 0:
            self._stock_filter.blockSignals(True)
            self._stock_filter.setCurrentIndex(idx)
            self._stock_filter.blockSignals(False)
        self._apply_filters()

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _on_filter_changed(self, *_):
        stock_val = self._stock_filter.currentText()
        preset_map = {"Low": "low", "Empty": "empty", "On Order": "on_order"}
        active_chip = preset_map.get(stock_val, "all") if stock_val != "All Stock" else "all"
        for k, btn in self._preset_btns.items():
            active = (k == active_chip)
            btn.setObjectName("chipActive" if active else "chip")
            btn.setChecked(active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._apply_filters()

    def _apply_filters(self):
        search    = self._search_edit.text().strip().lower()
        type_val  = self._type_filter.currentText()
        brand_val = self._brand_filter.currentText()
        stock_val = self._stock_filter.currentText()

        filtered = self._all_materials
        if search:
            filtered = [
                m for m in filtered
                if search in m.name.lower()
                or search in (m.brand or "").lower()
                or search in (m.color or "").lower()
                or search in m.material_type.lower()
            ]
        if type_val and type_val != "All Types":
            filtered = [m for m in filtered if m.material_type == type_val]
        if brand_val and brand_val != "All Brands":
            filtered = [m for m in filtered if m.brand == brand_val]
        if stock_val and stock_val != "All Stock":
            filtered = [m for m in filtered if m.stock == stock_val]

        self._filtered = filtered
        self._render_cards()
        self._render_table()
        self._update_status()

    def _update_brand_filter(self):
        current = self._brand_filter.currentText()
        self._brand_filter.blockSignals(True)
        self._brand_filter.clear()
        self._brand_filter.addItem("All Brands")
        brands = sorted({m.brand for m in self._all_materials if m.brand})
        self._brand_filter.addItems(brands)
        idx = self._brand_filter.findText(current)
        self._brand_filter.setCurrentIndex(max(0, idx))
        self._brand_filter.blockSignals(False)

    # ── Render: cards ─────────────────────────────────────────────────────────

    def _render_cards(self):
        cols  = self._card_cols()
        inner = QWidget()
        grid  = QGridLayout(inner)
        grid.setContentsMargins(18, 14, 18, 18)
        grid.setSpacing(_CARD_GAP)

        for c in range(cols):
            grid.setColumnStretch(c, 0)
        grid.setColumnStretch(cols, 1)

        if not self._filtered:
            ph = QLabel("No materials found.\nTry adjusting your filters or add a new material.")
            ph.setAlignment(Qt.AlignCenter)
            ph.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.28); padding: 60px;")
            ph.setWordWrap(True)
            grid.addWidget(ph, 0, 0, 1, max(cols, 1))
        else:
            row = col = 0
            for mat in self._filtered:
                card = _MaterialCard(mat)
                card.edit_requested.connect(self._on_edit)
                card.delete_requested.connect(self._on_delete)
                grid.addWidget(card, row, col, Qt.AlignTop)
                col += 1
                if col >= cols:
                    col = 0
                    row += 1
            if col != 0:
                row += 1
            grid.setRowStretch(row, 1)

        self._scroll.setWidget(inner)

    def showEvent(self, event):
        super().showEvent(event)
        if self._filtered:
            QTimer.singleShot(0, self._render_cards)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._filtered:
            self._render_cards()
        for child in self.findChildren(_Toast):
            self._position_toast(child)

    # ── Render: table ─────────────────────────────────────────────────────────

    def _render_table(self):
        # Sort the current filtered list before rendering
        sort_key_map = {
            self._COL_ICON:    lambda m: _type_icon(m.material_type),
            self._COL_NAME:    lambda m: (m.name or "").lower(),
            self._COL_BRAND:   lambda m: (m.brand or "").lower(),
            self._COL_VARIANT: lambda m: (m.color or "").lower(),
            self._COL_TYPE:    lambda m: (m.material_type or "").lower(),
            self._COL_STOCK:   lambda m: STOCK_LEVELS.index(m.stock) if m.stock in STOCK_LEVELS else 99,
            self._COL_QTY:     lambda m: m.quantity,
            self._COL_NOTES:   lambda m: bool(m.notes),
        }
        key_fn = sort_key_map.get(self._sort_col, sort_key_map[self._COL_NAME])
        sorted_mats = sorted(self._filtered, key=key_fn, reverse=self._sort_desc)

        self._table.setRowCount(0)
        self._table.setRowCount(len(sorted_mats))
        for row, mat in enumerate(sorted_mats):
            self._table.setRowHeight(row, 34)
            fg = _stock_fg(mat.stock)

            icon_item = QTableWidgetItem(_type_icon(mat.material_type))
            icon_item.setTextAlignment(Qt.AlignCenter)
            icon_item.setData(Qt.UserRole, mat)
            self._table.setItem(row, self._COL_ICON, icon_item)

            name_item = QTableWidgetItem(mat.name)
            name_item.setData(Qt.UserRole, mat)
            self._table.setItem(row, self._COL_NAME, name_item)

            brand_item = QTableWidgetItem(mat.brand or "")
            brand_item.setData(Qt.UserRole, mat)
            self._table.setItem(row, self._COL_BRAND, brand_item)

            variant_item = QTableWidgetItem(mat.color or "")
            variant_item.setData(Qt.UserRole, mat)
            self._table.setItem(row, self._COL_VARIANT, variant_item)

            type_item = QTableWidgetItem(mat.material_type or "")
            type_item.setData(Qt.UserRole, mat)
            self._table.setItem(row, self._COL_TYPE, type_item)

            stock_item = QTableWidgetItem(mat.stock)
            stock_item.setForeground(QColor(fg))
            stock_item.setTextAlignment(Qt.AlignCenter)
            stock_item.setData(Qt.UserRole, mat)
            self._table.setItem(row, self._COL_STOCK, stock_item)

            qty_item = QTableWidgetItem(str(mat.quantity))
            qty_item.setTextAlignment(Qt.AlignCenter)
            qty_item.setData(Qt.UserRole, mat)
            self._table.setItem(row, self._COL_QTY, qty_item)

            notes_item = QTableWidgetItem("●" if mat.notes else "")
            notes_item.setTextAlignment(Qt.AlignCenter)
            notes_item.setData(Qt.UserRole, mat)
            if mat.notes:
                notes_item.setForeground(QColor("#4f9eff"))
                notes_item.setToolTip(mat.notes)
            self._table.setItem(row, self._COL_NOTES, notes_item)

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _update_status(self):
        total = len(self._filtered)
        all_n = len(self._all_materials)
        if total == all_n:
            self._status_lbl.setText(f"{total} material{'s' if total != 1 else ''}")
        else:
            self._status_lbl.setText(f"{total} of {all_n} materials")

        dist: dict[str, int] = {}
        for m in self._filtered:
            dist[m.stock] = dist.get(m.stock, 0) + 1

        visible_stocks = [s for s in STOCK_LEVELS if dist.get(s, 0) > 0]
        for i, stock in enumerate(STOCK_LEVELS):
            pill = self._stock_pills[stock]
            sep  = self.findChild(QLabel, f"stockSep_{stock}")
            count = dist.get(stock, 0)
            if count:
                pill.setText(f"{count} {stock}")
                pill.show()
                if sep and stock in visible_stocks and visible_stocks.index(stock) > 0:
                    sep.show()
                elif sep:
                    sep.hide()
            else:
                pill.hide()
                if sep:
                    sep.hide()

    # ── View toggle ────────────────────────────────────────────────────────────

    def _set_view(self, mode: str):
        self._view_mode = mode
        if mode == "cards":
            self._stack.setCurrentIndex(0)
            self._card_view_btn.setObjectName("viewToggleActive")
            self._table_view_btn.setObjectName("viewToggle")
        else:
            self._stack.setCurrentIndex(1)
            self._card_view_btn.setObjectName("viewToggle")
            self._table_view_btn.setObjectName("viewToggleActive")
        for btn in (self._card_view_btn, self._table_view_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def _on_quick_add(self, data: dict):
        try:
            self._svc.add_material(**data)
            self.refresh()
            self._show_toast(f"✓  Added {data['name']}")
            if self._ctx:
                self._ctx.event_bus.emit("material_added", data)
        except ValidationError as e:
            self._show_toast(f"{e}", error=True)
        except Exception as e:
            self._show_toast(f"Error: {e}", error=True)

    def _on_edit(self, mat: Material):
        dlg = _EditDialog(mat, self._ctx, parent=self)
        self._apply_dialog_theme(dlg)
        if dlg.exec():
            try:
                data = dlg.get_data()
                self._svc.update_material(mat.id, **data)
                self.refresh()
                self._show_toast(f"✓  Updated {data['name']}")
                if self._ctx:
                    self._ctx.event_bus.emit("material_updated", {"id": mat.id, **data})
            except (ValidationError, ValueError) as e:
                self._show_toast(f"{e}", error=True)
            except Exception as e:
                self._show_toast(f"Error: {e}", error=True)

    def _on_delete(self, mat: Material):
        reply = QMessageBox.question(
            self, "Delete Material",
            f"Delete <b>{mat.name}</b>?<br>This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            self._undo_material = mat
            try:
                self._svc.remove_material(mat.id)
                self.refresh()
                self._show_toast(f"Deleted {mat.name}",
                                 action_label="Undo", action_cb=self._undo_delete)
                if self._ctx:
                    self._ctx.event_bus.emit("material_removed", {"id": mat.id})
            except Exception as e:
                self._show_toast(f"Error: {e}", error=True)

    def _undo_delete(self):
        m = self._undo_material
        if not m:
            return
        try:
            self._svc.add_material(
                name=m.name, material_type=m.material_type,
                brand=m.brand, color=m.color,
                stock=m.stock, quantity=m.quantity, notes=m.notes,
            )
            self._undo_material = None
            self.refresh()
            self._show_toast(f"✓  Restored {m.name}")
        except Exception as e:
            self._show_toast(f"Could not restore: {e}", error=True)

    # ── Table interaction ──────────────────────────────────────────────────────

    def _on_table_double_click(self, index):
        item = self._table.item(index.row(), self._COL_NAME)
        if item:
            mat = item.data(Qt.UserRole)
            if mat:
                self._on_edit(mat)

    def _on_table_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        item = self._table.item(row, self._COL_NAME)
        if not item:
            return
        mat = item.data(Qt.UserRole)
        if not mat:
            return
        menu = QMenu(self)
        edit_act   = menu.addAction("✏  Edit")
        menu.addSeparator()
        delete_act = menu.addAction("🗑  Delete")
        act = menu.exec(self._table.viewport().mapToGlobal(pos))
        if act == edit_act:
            self._on_edit(mat)
        elif act == delete_act:
            self._on_delete(mat)

    def _table_key_press(self, event):
        """Keyboard shortcuts for the table: Enter = edit, Del = delete."""
        key = event.key()
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            QTableWidget.keyPressEvent(self._table, event)
            return
        row = rows[0].row()
        item = self._table.item(row, self._COL_NAME)
        mat = item.data(Qt.UserRole) if item else None
        if mat:
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._on_edit(mat)
                return
            elif key == Qt.Key_Delete:
                self._on_delete(mat)
                return
        QTableWidget.keyPressEvent(self._table, event)

    def _on_header_clicked(self, col: int):
        """Toggle sort direction if same column, otherwise sort ascending."""
        if col == self._COL_ICON:
            return  # icon column — not meaningful to sort by
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col  = col
            self._sort_desc = False
        hdr = self._table.horizontalHeader()
        hdr.setSortIndicator(col, Qt.DescendingOrder if self._sort_desc else Qt.AscendingOrder)
        self._render_table()

    def _export_csv(self):
        """Export the currently filtered list to a CSV file chosen by the user."""
        if not self._filtered:
            self._show_toast("Nothing to export — no materials match the current filter.", error=True)
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"materials_{timestamp}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Materials to CSV",
            os.path.join(os.path.expanduser("~"), default_name),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Name", "Type", "Brand", "Variant", "Stock", "Quantity", "Notes"])
                for m in self._filtered:
                    writer.writerow([
                        m.name,
                        m.material_type,
                        m.brand or "",
                        m.color or "",
                        m.stock,
                        m.quantity,
                        m.notes or "",
                    ])
            fname = os.path.basename(path)
            self._show_toast(f"✓  Exported {len(self._filtered)} materials to {fname}")
        except Exception as e:
            self._show_toast(f"Export failed: {e}", error=True)

    # ── Toast helpers ──────────────────────────────────────────────────────────

    def _show_toast(self, message: str, *, error: bool = False,
                    action_label: str = "", action_cb=None):
        toast = _Toast(message, parent=self,
                       action_label=action_label, action_cb=action_cb)
        if error:
            toast.setStyleSheet("""
                QLabel#toastLabel {
                    background: rgba(200,60,60,0.94);
                    color: #fff;
                    font-size: 12px;
                    padding: 9px 20px;
                    border-radius: 8px;
                    border: 1px solid rgba(255,255,255,0.12);
                }
            """)
        toast.show()
        self._position_toast(toast)

    def _position_toast(self, toast: _Toast):
        toast.adjustSize()
        x = (self.width()  - toast.width())  // 2
        y =  self.height() - toast.height()  - 36
        toast.move(x, y)

    # ── Theme ──────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        if not self._ctx:
            return
        try:
            tm = self._ctx.services.try_get("theme_manager")
            if not tm:
                return
            bg  = tm.token("bg_base")
            bg2 = tm.token("bg_card")
            fg  = tm.token("text_hi")
            fg2 = tm.token("text_lo")
            brd = tm.token("border")
            acc = tm.token("accent")
            inp = tm.token("bg_input")

            self.setStyleSheet(f"""
                QWidget {{
                    background: {bg};
                    color: {fg};
                    font-family: system-ui, -apple-system, sans-serif;
                }}

                /* ── Header ── */
                QWidget#matHeader {{
                    background: {bg2};
                    border-bottom: 1px solid {brd};
                }}
                QLabel#matSubtitle {{
                    color: {fg2};
                }}

                /* ── View toggle group ── */
                QFrame#viewToggleGroup {{
                    background: {inp};
                    border: 1px solid {brd};
                    border-radius: 7px;
                }}
                QPushButton#viewToggle {{
                    background: transparent;
                    color: {fg2};
                    border: none;
                    border-radius: 5px;
                    font-size: 14px;
                }}
                QPushButton#viewToggle:hover {{
                    color: {fg};
                    background: rgba(255,255,255,0.05);
                }}
                QPushButton#viewToggleActive {{
                    background: {acc};
                    color: #fff;
                    border: none;
                    border-radius: 5px;
                    font-size: 14px;
                }}

                /* ── Filter bar ── */
                QWidget#matFilterBar {{
                    background: {bg};
                    border-bottom: 1px solid {brd};
                }}

                /* ── Chips ── */
                QPushButton#chip {{
                    background: transparent;
                    color: {fg2};
                    border: 1px solid {brd};
                    border-radius: 13px;
                    padding: 3px 13px;
                    font-size: 12px;
                }}
                QPushButton#chip:hover {{
                    color: {fg};
                    border-color: rgba(255,255,255,0.22);
                }}
                QPushButton#chipActive {{
                    background: {acc};
                    color: #fff;
                    border: none;
                    border-radius: 13px;
                    padding: 3px 13px;
                    font-size: 12px;
                    font-weight: 600;
                }}

                /* ── Quick-add card ── */
                QFrame#quickAddCard {{
                    background: {bg2};
                    border: 1px solid {brd};
                    border-radius: 8px;
                    margin: 8px 18px 4px 18px;
                }}

                /* ── Primary / secondary buttons ── */
                QPushButton#primaryBtn {{
                    background: {acc};
                    color: #fff;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-weight: 600;
                    font-size: 13px;
                }}
                QPushButton#primaryBtn:hover {{
                    border: 1px solid rgba(255,255,255,0.18);
                }}
                QPushButton#secondaryBtn {{
                    background: {inp};
                    color: {fg};
                    border: 1px solid {brd};
                    border-radius: 6px;
                    padding: 5px 12px;
                    font-size: 12px;
                }}
                QPushButton#secondaryBtn:hover {{
                    border-color: {acc};
                    color: {acc};
                }}

                /* ── Inputs ── */
                QLineEdit, QComboBox, QSpinBox, QTextEdit {{
                    background: {inp};
                    color: {fg};
                    border: 1px solid {brd};
                    border-radius: 5px;
                    padding: 5px 9px;
                    font-size: 12px;
                    selection-background-color: {acc};
                }}
                QLineEdit:focus, QComboBox:focus,
                QSpinBox:focus, QTextEdit:focus {{
                    border-color: {acc};
                }}
                QComboBox::drop-down {{ border: none; padding-right: 6px; }}
                QComboBox QAbstractItemView {{
                    background: {bg2};
                    color: {fg};
                    border: 1px solid {brd};
                    selection-background-color: {acc};
                    selection-color: #fff;
                }}

                /* ── Table ── */
                QTableWidget {{
                    background: {bg};
                    alternate-background-color: {bg2};
                    color: {fg};
                    border: none;
                    font-size: 12px;
                    gridline-color: transparent;
                }}
                QTableWidget::item {{ padding: 0 4px; }}
                QTableWidget::item:selected {{
                    background: {acc};
                    color: #fff;
                }}
                QHeaderView::section {{
                    background: {bg2};
                    color: {fg2};
                    border: none;
                    border-bottom: 1px solid {brd};
                    padding: 6px 8px;
                    font-size: 11px;
                    font-weight: 600;
                    letter-spacing: 0.3px;
                    text-transform: uppercase;
                }}

                /* ── Status bar ── */
                QWidget#matStatusBar {{
                    background: {bg2};
                    border-top: 1px solid {brd};
                }}
                QLabel#statusCount {{
                    font-size: 11px;
                    color: {fg2};
                }}

                /* ── Scrollbar ── */
                QScrollBar:vertical {{
                    background: transparent;
                    width: 5px;
                    margin: 0;
                }}
                QScrollBar::handle:vertical {{
                    background: {brd};
                    border-radius: 2px;
                    min-height: 24px;
                }}
                QScrollBar::add-line:vertical,
                QScrollBar::sub-line:vertical {{ height: 0; }}

                /* ── Separator lines ── */
                QFrame[frameShape="5"] {{
                    background: {brd};
                    border: none;
                    max-width: 1px;
                }}
            """)
        except Exception as e:
            log.error(f"[MATERIALS V2 UI] theme error: {e}")

    def _apply_dialog_theme(self, dlg: QDialog):
        if not self._ctx:
            return
        try:
            tm = self._ctx.services.try_get("theme_manager")
            if not tm:
                return
            bg  = tm.token("bg_base")
            bg2 = tm.token("bg_card")
            fg  = tm.token("text_hi")
            fg2 = tm.token("text_lo")
            brd = tm.token("border")
            acc = tm.token("accent")
            inp = tm.token("bg_input")
            dlg.setStyleSheet(f"""
                QDialog {{ background: {bg}; color: {fg}; }}
                QLabel  {{ background: transparent; color: {fg}; }}
                QLabel[style*="0.50"] {{ color: {fg2}; }}
                QLineEdit, QComboBox, QSpinBox, QTextEdit {{
                    background: {inp}; color: {fg};
                    border: 1px solid {brd}; border-radius: 5px;
                    padding: 5px 8px; font-size: 12px;
                }}
                QLineEdit:focus, QComboBox:focus,
                QSpinBox:focus, QTextEdit:focus {{ border-color: {acc}; }}
                QComboBox::drop-down {{ border: none; padding-right: 6px; }}
                QComboBox QAbstractItemView {{
                    background: {bg2}; color: {fg};
                    border: 1px solid {brd};
                    selection-background-color: {acc}; selection-color: #fff;
                }}
                QPushButton {{
                    background: {inp}; color: {fg};
                    border: 1px solid {brd}; border-radius: 5px;
                    padding: 6px 18px; font-size: 13px;
                }}
                QPushButton[default="true"], QPushButton:default {{
                    background: {acc}; color: #fff;
                    border: none; font-weight: 600;
                }}
                QPushButton:hover {{ border-color: {acc}; color: {acc}; }}
                QPushButton[default="true"]:hover, QPushButton:default:hover {{
                    color: #fff; border: 1px solid rgba(255,255,255,0.18);
                }}
                QFrame[frameShape="4"] {{
                    background: {brd}; border: none; max-height: 1px;
                }}
            """)
        except Exception:
            pass

    # ── v1 compat ──────────────────────────────────────────────────────────────

    def _show_success(self, msg: str):
        self._show_toast(f"✓  {msg}")

    def _show_error(self, msg: str):
        self._show_toast(msg, error=True)

    def display_materials(self, materials, **_):
        self._all_materials = list(materials)
        self._apply_filters()

    def update_statistics(self, stats):
        pass
