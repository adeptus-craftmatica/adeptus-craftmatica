"""Shopping List 1.0 — Main UI."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile

log = logging.getLogger(__name__)

from PySide6.QtCore    import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QDialog, QDialogButtonBox, QSizePolicy, QLineEdit,
    QComboBox, QDoubleSpinBox, QTextEdit, QCheckBox, QTabWidget,
    QListWidget, QListWidgetItem, QApplication, QFileDialog,
    QMessageBox, QMenu, QInputDialog,
)

from .models import ShoppingItem, ShoppingSection, CATEGORIES, CATEGORY_ICONS
from .service import ShoppingService

# ── Design tokens ─────────────────────────────────────────────────────────────

_C = {
    "bg_deep": "#141414", "bg_base": "#1c1c1c", "bg_card": "#1e1e1e",
    "bg_raised": "#212121", "bg_input": "#2a2a2a", "bg_hover": "#2e2e2e",
    "bg_active": "#333333", "border_lo": "#282828", "border": "#363636",
    "border_hi": "#484848", "text_hi": "#f0f0f0", "text_mid": "#d8d8d8",
    "text_lo": "#909090", "text_dim": "#606060", "accent": "#0078d4",
    "accent_hi": "#1a8ee8", "accent_lo": "#0f4a7a", "accent_text": "#60b0ff",
    "danger": "#e05555", "danger_hi": "#eb6868", "danger_lo": "#2a1515",
    "success": "#3dba6e", "success_lo": "#0f2a1a", "warning": "#e07800",
    "warning_lo": "#2a1800",
}
_FS = {"xs": "10px", "sm": "11px", "base": "12px", "lg": "13px",
       "xl": "15px", "2xl": "20px", "3xl": "28px"}
_R  = {"xs": "3px", "sm": "5px", "base": "7px", "lg": "10px", "pill": "999px"}


def _label(text: str, size: str = "base", color: str = "text_mid",
           bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    weight = "600" if bold else "400"
    lbl.setStyleSheet(
        f"color:{_C[color]}; font-size:{_FS[size]}; font-weight:{weight};"
        f" background:transparent; border:none;"
    )
    return lbl


def _combo(parent=None) -> QComboBox:
    """Return a styled QComboBox that matches every other dropdown in the app."""
    cb = QComboBox(parent)
    cb.setFixedHeight(32)
    cb.setStyleSheet(
        f"QComboBox{{background:{_C['bg_input']}; color:{_C['text_hi']};"
        f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
        f"padding:5px 10px; font-size:{_FS['base']}; min-height:28px;}}"
        f"QComboBox:focus{{border-color:{_C['accent']};}}"
        f"QComboBox:hover{{border-color:{_C['border_hi']};}}"
        f"QComboBox::drop-down{{border:none; width:22px;}}"
        f"QComboBox::down-arrow{{image:none; width:0; height:0;}}"
        f"QComboBox QAbstractItemView{{background:{_C['bg_card']}; color:{_C['text_hi']};"
        f"border:1px solid {_C['border']}; selection-background-color:{_C['accent_lo']};"
        f"selection-color:{_C['accent_text']}; outline:none; padding:4px;}}"
    )
    return cb


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.NoFrame)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{_C['border']}; border:none;")
    return f


def _btn(text: str, kind: str = "default", h: int = 30) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(h)
    if kind == "primary":
        b.setStyleSheet(
            f"QPushButton{{background:{_C['accent']}; color:#fff; border:none;"
            f"border-radius:{_R['sm']}; font-size:{_FS['base']}; font-weight:600;"
            f"padding:0 14px;}}"
            f"QPushButton:hover{{background:{_C['accent_hi']};}}"
        )
    elif kind == "danger":
        b.setStyleSheet(
            f"QPushButton{{background:{_C['danger_lo']}; color:{_C['danger']};"
            f"border:1px solid {_C['danger']}; border-radius:{_R['sm']};"
            f"font-size:{_FS['base']}; padding:0 12px;}}"
            f"QPushButton:hover{{background:{_C['danger']}; color:#fff;}}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; color:{_C['text_mid']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"font-size:{_FS['base']}; padding:0 12px;}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; color:{_C['text_hi']};"
            f"border-color:{_C['border_hi']};}}"
        )
    return b


# ── Item Row ──────────────────────────────────────────────────────────────────

class _ItemRow(QFrame):
    """Single shopping item row with checkbox, details, and action buttons."""

    purchased_toggled = Signal(int, bool)   # (item_id, purchased)
    edit_requested    = Signal(object)       # ShoppingItem
    delete_requested  = Signal(int)          # item_id

    def __init__(self, item: ShoppingItem, parent=None):
        super().__init__(parent)
        self._item = item
        self.setObjectName("ShopItemRow")
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._build()

    def _build(self):
        purchased = self._item.purchased
        self.setStyleSheet(
            f"QFrame#ShopItemRow{{background:{_C['bg_card']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; margin:1px 0;}}"
            f"QFrame#ShopItemRow:hover{{background:{_C['bg_hover']}; border-color:{_C['border_hi']};}}"
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(8)

        # Checkbox
        chk = QCheckBox()
        chk.setChecked(purchased)
        chk.setStyleSheet(
            f"QCheckBox::indicator{{width:16px; height:16px;"
            f"border:1px solid {_C['border_hi']}; border-radius:3px;"
            f"background:{_C['bg_input']};}}"
            f"QCheckBox::indicator:checked{{background:{_C['success']};"
            f"border-color:{_C['success']};}}"
        )
        chk.toggled.connect(lambda v: self.purchased_toggled.emit(self._item.id, v))
        outer.addWidget(chk, 0, Qt.AlignmentFlag.AlignVCenter)

        # Icon
        icon_lbl = QLabel(self._item.icon())
        icon_lbl.setFixedWidth(22)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background:transparent; border:none; font-size:14px;")
        outer.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        # Text block
        txt = QVBoxLayout()
        txt.setContentsMargins(0, 2, 0, 2)
        txt.setSpacing(2)

        strike = "line-through " if purchased else ""
        name_color = _C["text_dim"] if purchased else _C["text_hi"]
        name_lbl = QLabel(self._item.name)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(
            f"color:{name_color}; font-size:{_FS['base']}; font-weight:500;"
            f"text-decoration:{strike}; background:transparent; border:none;"
        )
        txt.addWidget(name_lbl)

        # Meta: qty · category · notes hint
        meta_parts = [self._item.qty_display()]
        if self._item.category and self._item.category != "Other":
            meta_parts.append(self._item.category)
        if self._item.source_plugin:
            meta_parts.append(f"from {self._item.source_plugin.replace('_', ' ')}")
        if self._item.notes:
            meta_parts.append(f"📝 {self._item.notes[:40]}")
        meta_lbl = QLabel(" · ".join(meta_parts))
        meta_lbl.setWordWrap(True)
        meta_lbl.setStyleSheet(
            f"color:{_C['text_dim']}; font-size:{_FS['xs']};"
            f"background:transparent; border:none;"
        )
        txt.addWidget(meta_lbl)

        outer.addLayout(txt, stretch=1)

        # Action buttons
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(3)
        btn_col.setAlignment(Qt.AlignmentFlag.AlignTop)

        edit_btn = QPushButton("✎")
        edit_btn.setFixedSize(24, 24)
        edit_btn.setToolTip("Edit item")
        edit_btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['xs']}; color:{_C['text_lo']}; font-size:{_FS['sm']};}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; color:{_C['accent_text']};"
            f"border-color:{_C['accent']};}}"
        )
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._item))
        btn_col.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("Remove item")
        del_btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['xs']}; color:{_C['text_dim']}; font-size:{_FS['xs']};}}"
            f"QPushButton:hover{{background:{_C['danger_lo']}; color:{_C['danger']};"
            f"border-color:{_C['danger']};}}"
        )
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._item.id))
        btn_col.addWidget(del_btn)

        outer.addLayout(btn_col)


# ── Section Widget ────────────────────────────────────────────────────────────

class _SectionWidget(QFrame):
    """Collapsible section header + item rows."""

    item_purchased_toggled = Signal(int, bool)
    item_edit_requested    = Signal(object)
    item_delete_requested  = Signal(int)
    section_rename_requested = Signal(int, str)
    section_delete_requested = Signal(int)
    add_item_requested     = Signal(int)   # section_id

    def __init__(self, section: ShoppingSection, parent=None):
        super().__init__(parent)
        self._section = section
        self._collapsed = section.collapsed
        self.setStyleSheet(
            f"QFrame{{background:transparent; border:none;}}"
        )
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(0)

        # ── Section header row ────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"QFrame{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['base']};}}"
        )
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(10, 0, 8, 0)
        hdr_row.setSpacing(8)

        self._toggle_btn = QPushButton("▾" if not self._collapsed else "▸")
        self._toggle_btn.setFixedSize(18, 18)
        self._toggle_btn.setStyleSheet(
            f"QPushButton{{background:transparent; border:none; color:{_C['text_lo']};"
            f"font-size:{_FS['sm']};}}"
            f"QPushButton:hover{{color:{_C['text_hi']};}}"
        )
        self._toggle_btn.clicked.connect(self._toggle)
        hdr_row.addWidget(self._toggle_btn)

        title_lbl = _label(self._section.title.upper(), "xs", "text_lo", bold=True)
        title_lbl.setStyleSheet(
            title_lbl.styleSheet() + " letter-spacing:1px;"
        )
        hdr_row.addWidget(title_lbl)

        count = len(self._section.items)
        if count:
            purchased = sum(1 for i in self._section.items if i.purchased)
            badge_txt = f"{purchased}/{count}" if purchased else str(count)
            badge = QLabel(badge_txt)
            badge.setStyleSheet(
                f"background:{_C['bg_active']}; color:{_C['text_lo']};"
                f"font-size:{_FS['xs']}; padding:1px 6px; border-radius:{_R['pill']};"
                f"border:none;"
            )
            hdr_row.addWidget(badge)

        hdr_row.addStretch()

        # Add item button
        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(22)
        add_btn.setStyleSheet(
            f"QPushButton{{background:transparent; border:1px solid {_C['border']};"
            f"color:{_C['text_lo']}; border-radius:{_R['xs']}; font-size:{_FS['xs']};"
            f"padding:0 8px;}}"
            f"QPushButton:hover{{border-color:{_C['accent']}; color:{_C['accent_text']};}}"
        )
        add_btn.clicked.connect(lambda: self.add_item_requested.emit(self._section.id))
        hdr_row.addWidget(add_btn)

        # Section menu
        menu_btn = QPushButton("Section Options")
        menu_btn.setFixedHeight(22)
        menu_btn.setStyleSheet(
            f"QPushButton{{background:transparent; border:1px solid {_C['border']};"
            f"color:{_C['text_lo']}; border-radius:{_R['xs']}; font-size:{_FS['xs']};"
            f"padding:0 8px;}}"
            f"QPushButton:hover{{border-color:{_C['border_hi']}; color:{_C['text_hi']};}}"
        )
        menu_btn.clicked.connect(self._show_menu)
        hdr_row.addWidget(menu_btn)

        root.addWidget(hdr)

        # ── Items container ───────────────────────────────────────────────────
        self._items_widget = QWidget()
        self._items_widget.setStyleSheet("background:transparent;")
        self._items_layout = QVBoxLayout(self._items_widget)
        self._items_layout.setContentsMargins(0, 3, 0, 0)
        self._items_layout.setSpacing(2)

        for item in self._section.items:
            self._add_item_row(item)

        if not self._section.items:
            empty = _label("No items in this section.", "xs", "text_dim")
            empty.setContentsMargins(8, 4, 0, 0)
            self._items_layout.addWidget(empty)

        self._items_widget.setVisible(not self._collapsed)
        root.addWidget(self._items_widget)

    def _add_item_row(self, item: ShoppingItem):
        row = _ItemRow(item)
        row.purchased_toggled.connect(self.item_purchased_toggled)
        row.edit_requested.connect(self.item_edit_requested)
        row.delete_requested.connect(self.item_delete_requested)
        self._items_layout.addWidget(row)

    def _toggle(self):
        self._collapsed = not self._collapsed
        self._toggle_btn.setText("▸" if self._collapsed else "▾")
        self._items_widget.setVisible(not self._collapsed)

    def _show_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; color:{_C['text_hi']}; padding:4px;}}"
            f"QMenu::item{{padding:6px 20px 6px 12px; border-radius:{_R['xs']};}}"
            f"QMenu::item:selected{{background:{_C['bg_hover']};}}"
        )
        rename_act = menu.addAction("✏  Rename section")
        menu.addSeparator()
        delete_act = menu.addAction("🗑  Delete section")
        act = menu.exec(self.mapToGlobal(self._toggle_btn.pos()))
        if act == rename_act:
            self.section_rename_requested.emit(
                self._section.id, self._section.title
            )
        elif act == delete_act:
            self.section_delete_requested.emit(self._section.id)


# ── Item Dialog ───────────────────────────────────────────────────────────────

class _ItemDialog(QDialog):
    """Add / edit a shopping list item."""

    def __init__(self, sections: list[ShoppingSection],
                 item: ShoppingItem | None = None,
                 default_section_id: int = 0,
                 parent=None):
        super().__init__(parent)
        self._sections = sections
        self._item     = item
        self._result_item: ShoppingItem | None = None
        self.setWindowTitle("Edit Item" if item else "Add Item")
        self.setMinimumWidth(420)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog{{background:{_C['bg_base']}; color:{_C['text_hi']};}}"
            f"QLabel{{color:{_C['text_mid']}; font-size:{_FS['base']};"
            f"background:transparent; border:none;}}"
            f"QLineEdit, QDoubleSpinBox, QTextEdit{{"
            f"background:{_C['bg_input']}; color:{_C['text_hi']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"padding:4px 8px; font-size:{_FS['base']};}}"
            f"QLineEdit:focus, QDoubleSpinBox:focus, QTextEdit:focus{{"
            f"border-color:{_C['accent']};}}"
        )
        self._build(default_section_id)

    def _build(self, default_section_id: int):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        def _lbl(t): return QLabel(t)

        # Name
        root.addWidget(_lbl("Item Name *"))
        self._name = QLineEdit()
        self._name.setFixedHeight(34)
        self._name.setPlaceholderText("e.g. Vallejo Black Primer")
        root.addWidget(self._name)

        # Category + Quantity row
        cq_row = QHBoxLayout()
        cq_row.setSpacing(10)

        cat_col = QVBoxLayout()
        cat_col.setSpacing(3)
        cat_col.addWidget(_lbl("Category"))
        self._category = _combo()
        for cat in CATEGORIES:
            self._category.addItem(f"{CATEGORY_ICONS.get(cat,'📦')} {cat}", cat)
        cat_col.addWidget(self._category)
        cq_row.addLayout(cat_col, stretch=2)

        qty_col = QVBoxLayout()
        qty_col.setSpacing(3)
        qty_col.addWidget(_lbl("Quantity"))
        self._quantity = QDoubleSpinBox()
        self._quantity.setFixedHeight(34)
        self._quantity.setRange(0.01, 9999)
        self._quantity.setSingleStep(1)
        self._quantity.setValue(1)
        self._quantity.setDecimals(2)
        qty_col.addWidget(self._quantity)
        cq_row.addLayout(qty_col, stretch=1)

        unit_col = QVBoxLayout()
        unit_col.setSpacing(3)
        unit_col.addWidget(_lbl("Unit (optional)"))
        self._unit = QLineEdit()
        self._unit.setFixedHeight(34)
        self._unit.setPlaceholderText("e.g. ml, pcs")
        unit_col.addWidget(self._unit)
        cq_row.addLayout(unit_col, stretch=1)

        root.addLayout(cq_row)

        # Section
        root.addWidget(_lbl("Section"))
        self._section_combo = _combo()
        for sec in self._sections:
            self._section_combo.addItem(sec.title, sec.id)
        root.addWidget(self._section_combo)

        # Notes
        root.addWidget(_lbl("Notes (optional)"))
        self._notes = QTextEdit()
        self._notes.setFixedHeight(64)
        self._notes.setPlaceholderText("Brand, colour code, any reminders…")
        root.addWidget(self._notes)

        root.addWidget(_hline())

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = btns.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setText("Save Changes" if self._item else "Add Item")
        save_btn.setStyleSheet(
            f"QPushButton{{background:{_C['accent']}; color:#fff; border:none;"
            f"border-radius:{_R['sm']}; padding:6px 18px; font-size:{_FS['base']};"
            f"font-weight:600;}}"
            f"QPushButton:hover{{background:{_C['accent_hi']};}}"
        )
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; color:{_C['text_mid']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"padding:6px 14px; font-size:{_FS['base']};}}"
            f"QPushButton:hover{{background:{_C['bg_hover']};}}"
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        # Pre-fill if editing
        if self._item:
            self._name.setText(self._item.name)
            self._quantity.setValue(self._item.quantity)
            self._unit.setText(self._item.unit)
            self._notes.setPlainText(self._item.notes)
            for i in range(self._category.count()):
                if self._category.itemData(i) == self._item.category:
                    self._category.setCurrentIndex(i)
                    break
            for i in range(self._section_combo.count()):
                if self._section_combo.itemData(i) == self._item.section_id:
                    self._section_combo.setCurrentIndex(i)
                    break
        else:
            for i in range(self._section_combo.count()):
                if self._section_combo.itemData(i) == default_section_id:
                    self._section_combo.setCurrentIndex(i)
                    break

    def _save(self):
        name = self._name.text().strip()
        if not name:
            self._name.setStyleSheet(
                self._name.styleSheet() + f" border-color:{_C['danger']};"
            )
            self._name.setFocus()
            return
        category = self._category.currentData() or "Other"
        quantity = self._quantity.value()
        unit     = self._unit.text().strip()
        notes    = self._notes.toPlainText().strip()
        section_id = self._section_combo.currentData() or 0

        if self._item:
            self._result_item = ShoppingItem(
                id=self._item.id, list_id=self._item.list_id,
                section_id=section_id, name=name,
                category=category, quantity=quantity, unit=unit,
                notes=notes, purchased=self._item.purchased,
                source_plugin=self._item.source_plugin,
                source_item_id=self._item.source_item_id,
                project_id=self._item.project_id,
            )
        else:
            self._result_item = ShoppingItem(
                name=name, section_id=section_id, category=category,
                quantity=quantity, unit=unit, notes=notes,
            )
        self.accept()

    def result_item(self) -> ShoppingItem | None:
        return self._result_item


# ── Inventory Picker Dialog ───────────────────────────────────────────────────

class _InventoryPickerDialog(QDialog):
    """Pick items from existing inventory plugins to add to the shopping list."""

    def __init__(self, context, list_id: int,
                 sections: list[ShoppingSection], parent=None):
        super().__init__(parent)
        self._context    = context
        self._list_id    = list_id
        self._sections   = sections
        self._selections: list[dict] = []
        self.setWindowTitle("Add from Inventory")
        self.setMinimumSize(580, 500)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog{{background:{_C['bg_base']}; color:{_C['text_hi']};}}"
            f"QTabWidget::pane{{border:1px solid {_C['border']};"
            f"background:{_C['bg_card']}; border-radius:{_R['sm']};}}"
            f"QTabBar::tab{{background:{_C['bg_raised']}; color:{_C['text_lo']};"
            f"padding:6px 14px; border:1px solid {_C['border']};"
            f"border-bottom:none; margin-right:2px; border-radius:4px 4px 0 0;}}"
            f"QTabBar::tab:selected{{background:{_C['bg_card']}; color:{_C['text_hi']};}}"
            f"QListWidget{{background:{_C['bg_card']}; border:none; color:{_C['text_hi']};"
            f"font-size:{_FS['base']}; outline:none;}}"
            f"QListWidget::item{{padding:6px 8px; border-radius:{_R['xs']};}}"
            f"QListWidget::item:selected{{background:{_C['accent_lo']};"
            f"color:{_C['accent_text']};}}"
            f"QListWidget::item:hover{{background:{_C['bg_hover']};}}"
        )
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addWidget(_label("Select items to add to your shopping list:", "base", "text_mid"))

        self._tabs = QTabWidget()
        self._tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self._tabs.tabBar().setExpanding(False)
        self._list_widgets: dict[str, tuple[QListWidget, str, str]] = {}

        inventories = self._discover_inventories()
        if inventories:
            for tab_name, items, category, source_plugin in inventories:
                lw = QListWidget()
                lw.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
                for display, meta in items:
                    li = QListWidgetItem(display)
                    li.setData(Qt.ItemDataRole.UserRole, meta)
                    lw.addItem(li)
                self._tabs.addTab(lw, tab_name)
                self._list_widgets[tab_name] = (lw, category, source_plugin)
        else:
            lbl = _label("No inventory services are currently loaded.", "base", "text_lo")
            lbl.setContentsMargins(12, 12, 12, 12)
            self._tabs.addTab(lbl, "No inventory")

        root.addWidget(self._tabs)

        # Target section
        sec_row = QHBoxLayout()
        sec_row.setSpacing(8)
        sec_row.addWidget(_label("Add to section:", "sm", "text_lo"))
        self._sec_combo = _combo()
        for sec in self._sections:
            self._sec_combo.addItem(sec.title, sec.id)
        sec_row.addWidget(self._sec_combo, stretch=1)
        root.addLayout(sec_row)

        root.addWidget(_hline())

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Add Selected")
        ok_btn.setStyleSheet(
            f"QPushButton{{background:{_C['accent']}; color:#fff; border:none;"
            f"border-radius:{_R['sm']}; padding:6px 18px; font-size:{_FS['base']};"
            f"font-weight:600;}}"
            f"QPushButton:hover{{background:{_C['accent_hi']};}}"
        )
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; color:{_C['text_mid']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"padding:6px 14px; font-size:{_FS['base']};}}"
            f"QPushButton:hover{{background:{_C['bg_hover']};}}"
        )
        btns.accepted.connect(self._collect)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _discover_inventories(self) -> list:
        """Return list of (tab_name, [(display, meta_dict)], category, source_plugin)."""
        results = []

        # Paint inventory
        svc = self._context.services.try_get("paint_service")
        if svc:
            try:
                paints = svc.get_all_paints() if hasattr(svc, 'get_all_paints') else []
                items = []
                for p in paints:
                    name = f"{getattr(p,'brand','')} {getattr(p,'name',p.name)}".strip()
                    display = f"🎨 {name}"
                    meta = {"name": name, "category": "Paint",
                            "source_plugin": "paint_tracker",
                            "source_item_id": str(getattr(p, 'id', ''))}
                    items.append((display, meta))
                if items:
                    results.append(("🎨 Paints", items, "Paint", "paint_tracker"))
            except Exception:
                pass

        # Tool inventory
        svc = self._context.services.try_get("tool_service")
        if svc:
            try:
                tools = svc.get_all_tools() if hasattr(svc, 'get_all_tools') else (
                    svc.get_all() if hasattr(svc, 'get_all') else []
                )
                items = []
                for t in tools:
                    name = getattr(t, 'name', str(t))
                    display = f"🔧 {name}"
                    meta = {"name": name, "category": "Tool",
                            "source_plugin": "tool_tracker",
                            "source_item_id": str(getattr(t, 'id', ''))}
                    items.append((display, meta))
                if items:
                    results.append(("🔧 Tools", items, "Tool", "tool_tracker"))
            except Exception:
                pass

        # Materials inventory
        svc = self._context.services.try_get("material_service")
        if svc:
            try:
                materials = svc.get_all_materials() if hasattr(svc, 'get_all_materials') else (
                    svc.get_all() if hasattr(svc, 'get_all') else []
                )
                items = []
                for m in materials:
                    name = getattr(m, 'name', str(m))
                    display = f"🧱 {name}"
                    meta = {"name": name, "category": "Material",
                            "source_plugin": "materials_tracker",
                            "source_item_id": str(getattr(m, 'id', ''))}
                    items.append((display, meta))
                if items:
                    results.append(("🧱 Materials", items, "Material", "materials_tracker"))
            except Exception:
                pass

        # Model/miniature inventory
        for key in ("model_service", "miniature_service"):
            svc = self._context.services.try_get(key)
            if svc:
                try:
                    models = (svc.get_all_models() if hasattr(svc, 'get_all_models')
                              else svc.get_all() if hasattr(svc, 'get_all') else [])
                    items = []
                    for m in models:
                        name = getattr(m, 'name', str(m))
                        display = f"⚔️ {name}"
                        meta = {"name": name, "category": "Miniature",
                                "source_plugin": "model_tracker",
                                "source_item_id": str(getattr(m, 'id', ''))}
                        items.append((display, meta))
                    if items:
                        results.append(("⚔️ Miniatures", items, "Miniature", "model_tracker"))
                    break
                except Exception:
                    pass

        return results

    def _collect(self):
        self._selections = []
        section_id = self._sec_combo.currentData() or 0
        for tab_name, (lw, category, source_plugin) in self._list_widgets.items():
            for li in lw.selectedItems():
                meta = li.data(Qt.ItemDataRole.UserRole) or {}
                self._selections.append({
                    **meta,
                    "section_id": section_id,
                    "list_id": self._list_id,
                })
        self.accept()

    def selections(self) -> list[dict]:
        return self._selections


# ── Export Dialog ─────────────────────────────────────────────────────────────

class _ExportDialog(QDialog):
    """Export/share shopping list."""

    def __init__(self, service: ShoppingService, list_id: int, list_name: str,
                 parent=None):
        super().__init__(parent)
        self._service  = service
        self._list_id  = list_id
        self._list_name = list_name
        self.setWindowTitle("Export / Share")
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog{{background:{_C['bg_base']}; color:{_C['text_hi']};}}"
            f"QTextEdit{{background:{_C['bg_input']}; color:{_C['text_hi']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"font-family:monospace; font-size:{_FS['sm']}; padding:8px;}}"
        )
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        # Format selector
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(_label("Format:", "base", "text_lo"))
        self._fmt_combo = _combo()
        self._fmt_combo.addItems(["Plain Text", "CSV", "JSON"])
        self._fmt_combo.currentIndexChanged.connect(self._refresh_preview)
        fmt_row.addWidget(self._fmt_combo, stretch=1)
        root.addLayout(fmt_row)

        root.addWidget(_label("Preview:", "sm", "text_lo"))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        root.addWidget(self._preview)

        root.addWidget(_hline())

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        copy_btn = _btn("📋 Copy to Clipboard", "default")
        copy_btn.clicked.connect(self._copy)
        btn_row.addWidget(copy_btn)

        save_btn = _btn("💾 Save to File", "default")
        save_btn.clicked.connect(self._save_file)
        btn_row.addWidget(save_btn)

        share_btn = _btn("📤 Open with System", "default")
        share_btn.clicked.connect(self._system_share)
        btn_row.addWidget(share_btn)

        btn_row.addStretch()
        close_btn = _btn("Close", "primary")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)
        self._refresh_preview()

    def _get_content(self) -> tuple[str, str]:
        fmt = self._fmt_combo.currentText()
        if fmt == "CSV":
            return self._service.export_csv(self._list_id), "csv"
        if fmt == "JSON":
            return self._service.export_json(self._list_id), "json"
        return self._service.export_txt(self._list_id), "txt"

    def _refresh_preview(self):
        content, _ = self._get_content()
        self._preview.setPlainText(content)

    def _copy(self):
        content, _ = self._get_content()
        QApplication.clipboard().setText(content)

    def _save_file(self):
        content, ext = self._get_content()
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_"
                            for c in self._list_name)
        default_name = f"{safe_name}.{ext}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Shopping List", default_name,
            f"{ext.upper()} Files (*.{ext});;All Files (*)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def _system_share(self):
        content, ext = self._get_content()
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=f".{ext}", delete=False,
                encoding="utf-8", prefix="shopping_list_"
            ) as f:
                f.write(content)
                tmp_path = f.name
            if os.name == "posix":
                subprocess.Popen(["open", tmp_path])
            else:
                os.startfile(tmp_path)
        except Exception as e:
            QMessageBox.warning(self, "Share failed",
                                f"Could not open system share: {e}")


# ── Main Shopping List UI ─────────────────────────────────────────────────────

class ShoppingListUI(QWidget):
    """Shopping List 1.0 — main container widget."""

    def __init__(self, service: ShoppingService, context, parent=None):
        super().__init__(parent)
        self._service  = service
        self._context  = context
        self._active_list_id: int | None = None
        self._search_text = ""
        self._filter_category = "All"

        self.setStyleSheet(f"background:{_C['bg_base']}; color:{_C['text_hi']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_stats_strip())
        root.addWidget(self._build_content(), stretch=1)

        self._init_list()

    # ── Build: Header ─────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(
            f"background:{_C['bg_card']}; border-bottom:1px solid {_C['border']};"
        )
        row = QHBoxLayout(hdr)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(12)

        row.addWidget(_label("🛒  Shopping List", "xl", "text_hi", bold=True))
        row.addStretch()

        # List selector
        self._list_combo = QComboBox()
        self._list_combo.setMinimumWidth(180)
        self._list_combo.setFixedHeight(30)
        self._list_combo.setStyleSheet(
            f"QComboBox{{background:{_C['bg_raised']}; color:{_C['text_hi']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"padding:0 8px; font-size:{_FS['base']};}}"
            f"QComboBox:focus{{border-color:{_C['accent']};}}"
            f"QComboBox::drop-down{{border:none; width:18px;}}"
            f"QComboBox::down-arrow{{image:none;}}"
            f"QComboBox QAbstractItemView{{background:{_C['bg_raised']};"
            f"color:{_C['text_hi']}; border:1px solid {_C['border']};"
            f"selection-background-color:{_C['accent']};}}"
        )
        self._list_combo.currentIndexChanged.connect(self._on_list_changed)
        row.addWidget(self._list_combo)

        new_list_btn = _btn("+ New List", "default", h=30)
        new_list_btn.clicked.connect(self._new_list)
        row.addWidget(new_list_btn)

        menu_btn = QPushButton("List Options")
        menu_btn.setFixedHeight(30)
        menu_btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; color:{_C['text_lo']}; font-size:{_FS['base']};"
            f"padding:0 12px;}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; color:{_C['text_hi']};"
            f"border-color:{_C['border_hi']};}}"
        )
        menu_btn.clicked.connect(self._show_list_menu)
        row.addWidget(menu_btn)

        return hdr

    # ── Build: Toolbar ────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"background:{_C['bg_raised']}; border-bottom:1px solid {_C['border']};"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 6, 16, 6)
        row.setSpacing(8)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search items…")
        self._search.setFixedHeight(30)
        self._search.setStyleSheet(
            f"QLineEdit{{background:{_C['bg_input']}; color:{_C['text_hi']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"font-size:{_FS['base']}; padding:0 10px;}}"
            f"QLineEdit:focus{{border-color:{_C['accent']};}}"
        )
        self._search.textChanged.connect(self._on_search)
        row.addWidget(self._search, stretch=2)

        # Category filter
        self._cat_filter = QComboBox()
        self._cat_filter.setFixedHeight(30)
        self._cat_filter.setMinimumWidth(130)
        self._cat_filter.setStyleSheet(
            f"QComboBox{{background:{_C['bg_input']}; color:{_C['text_hi']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"padding:0 8px; font-size:{_FS['sm']};}}"
            f"QComboBox::drop-down{{border:none; width:14px;}}"
            f"QComboBox::down-arrow{{image:none;}}"
            f"QComboBox QAbstractItemView{{background:{_C['bg_raised']};"
            f"color:{_C['text_hi']}; border:1px solid {_C['border']};"
            f"selection-background-color:{_C['accent']};}}"
        )
        self._cat_filter.addItem("All Categories", "All")
        for cat in CATEGORIES:
            self._cat_filter.addItem(f"{CATEGORY_ICONS.get(cat,'')} {cat}", cat)
        self._cat_filter.currentIndexChanged.connect(self._on_filter)
        row.addWidget(self._cat_filter)

        row.addStretch()

        add_btn = _btn("+ Add Item", "primary", h=30)
        add_btn.clicked.connect(self.open_add_dialog)
        row.addWidget(add_btn)

        inv_btn = _btn("📥 From Inventory", "default", h=30)
        inv_btn.clicked.connect(self._open_inventory_picker)
        row.addWidget(inv_btn)

        add_sec_btn = _btn("+ Section", "default", h=30)
        add_sec_btn.clicked.connect(self._new_section)
        row.addWidget(add_sec_btn)

        export_btn = _btn("📤 Export", "default", h=30)
        export_btn.clicked.connect(self._open_export)
        row.addWidget(export_btn)

        return bar

    # ── Build: Stats strip ────────────────────────────────────────────────────

    def _build_stats_strip(self) -> QWidget:
        self._stats_widget = QWidget()
        self._stats_widget.setFixedHeight(38)
        self._stats_widget.setStyleSheet(
            f"background:{_C['bg_deep']}; border-bottom:1px solid {_C['border_lo']};"
        )
        row = QHBoxLayout(self._stats_widget)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(0)

        self._stat_total     = self._stat_cell("0", "TOTAL")
        self._stat_remaining = self._stat_cell("0", "REMAINING")
        self._stat_purchased = self._stat_cell("0", "PURCHASED")

        for w in (self._stat_total, self._stat_remaining, self._stat_purchased):
            row.addWidget(w)
            div = QFrame()
            div.setFrameShape(QFrame.Shape.VLine)
            div.setFixedHeight(20)
            div.setStyleSheet(f"color:{_C['border']}; background:{_C['border']}; max-width:1px;")
            row.addWidget(div)

        row.addStretch()

        # Quick actions on right
        rem_purch_btn = QPushButton("✓ Remove Purchased")
        rem_purch_btn.setFixedHeight(24)
        rem_purch_btn.setStyleSheet(
            f"QPushButton{{background:transparent; border:1px solid {_C['border']};"
            f"color:{_C['text_lo']}; border-radius:{_R['xs']}; font-size:{_FS['xs']};"
            f"padding:0 10px;}}"
            f"QPushButton:hover{{border-color:{_C['success']}; color:{_C['success']};}}"
        )
        rem_purch_btn.clicked.connect(self._remove_purchased)
        row.addWidget(rem_purch_btn)

        row.addSpacing(8)

        clear_btn = QPushButton("🗑 Clear All")
        clear_btn.setFixedHeight(24)
        clear_btn.setStyleSheet(
            f"QPushButton{{background:transparent; border:1px solid {_C['border']};"
            f"color:{_C['text_lo']}; border-radius:{_R['xs']}; font-size:{_FS['xs']};"
            f"padding:0 10px;}}"
            f"QPushButton:hover{{border-color:{_C['danger']}; color:{_C['danger']};}}"
        )
        clear_btn.clicked.connect(self._clear_all)
        row.addWidget(clear_btn)

        return self._stats_widget

    def _stat_cell(self, value: str, label: str) -> QWidget:
        w = QWidget()
        w.setFixedWidth(90)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(0)
        val_lbl = _label(value, "lg", "text_hi", bold=True)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_lbl = _label(label, "xs", "text_dim")
        lbl_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(val_lbl)
        lay.addWidget(lbl_lbl)
        w.setProperty("_val_lbl", val_lbl)
        return w

    def _update_stats(self):
        if self._active_list_id is None:
            return
        s = self._service.get_stats(self._active_list_id)
        self._stat_total.property("_val_lbl").setText(str(s["total"]))
        self._stat_remaining.property("_val_lbl").setText(str(s["remaining"]))
        self._stat_purchased.property("_val_lbl").setText(str(s["purchased"]))

    # ── Build: Content ────────────────────────────────────────────────────────

    def _build_content(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{_C['bg_base']}; border:none;}}"
            f"QScrollBar:vertical{{background:{_C['bg_base']}; width:6px; margin:0;}}"
            f"QScrollBar::handle:vertical{{background:{_C['border_hi']}; border-radius:3px;}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{{height:0;}}"
        )
        self._inner = QWidget()
        self._inner.setStyleSheet(f"background:{_C['bg_base']};")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(16, 12, 16, 20)
        self._inner_layout.setSpacing(6)
        scroll.setWidget(self._inner)
        return scroll

    # ── Init & Refresh ────────────────────────────────────────────────────────

    def _init_list(self):
        lists = self._service.get_all_lists()
        if not lists:
            sl = self._service.create_list("My Shopping List")
            lists = [sl]

        self._list_combo.blockSignals(True)
        self._list_combo.clear()
        for sl in lists:
            self._list_combo.addItem(sl.name, sl.id)
        self._list_combo.blockSignals(False)

        self._active_list_id = lists[0].id
        self._list_combo.setCurrentIndex(0)
        self.refresh()

    def refresh(self):
        """Rebuild the entire content area."""
        self._update_list_combo()

        while self._inner_layout.count():
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._active_list_id is None:
            return

        sections = self._service.get_sections(self._active_list_id)

        # Apply search/filter
        q   = self._search_text.lower()
        cat = self._filter_category

        filtered_sections = []
        for sec in sections:
            items = sec.items
            if q:
                items = [i for i in items
                         if q in i.name.lower() or q in i.notes.lower()]
            if cat and cat != "All":
                items = [i for i in items if i.category == cat]
            sec.items = items
            filtered_sections.append(sec)

        if not any(sec.items for sec in filtered_sections) and (q or cat != "All"):
            empty = _label(
                f"No items match your search.",
                "base", "text_dim"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 40, 0, 0)
            self._inner_layout.addWidget(empty)
        elif not sections:
            empty = _label(
                "No shopping list items yet.\nAdd a custom item or pull one from your inventory.",
                "base", "text_dim"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 40, 0, 0)
            self._inner_layout.addWidget(empty)
        else:
            for sec in filtered_sections:
                sec_widget = _SectionWidget(sec)
                sec_widget.item_purchased_toggled.connect(self._on_purchased_toggled)
                sec_widget.item_edit_requested.connect(self._on_edit_item)
                sec_widget.item_delete_requested.connect(self._on_delete_item)
                sec_widget.section_rename_requested.connect(self._on_rename_section)
                sec_widget.section_delete_requested.connect(self._on_delete_section)
                sec_widget.add_item_requested.connect(self._on_section_add_item)
                self._inner_layout.addWidget(sec_widget)

        self._inner_layout.addStretch()
        self._update_stats()

    def _update_list_combo(self):
        lists = self._service.get_all_lists()
        current_id = self._active_list_id
        self._list_combo.blockSignals(True)
        self._list_combo.clear()
        target_idx = 0
        for i, sl in enumerate(lists):
            self._list_combo.addItem(sl.name, sl.id)
            if sl.id == current_id:
                target_idx = i
        self._list_combo.setCurrentIndex(target_idx)
        self._list_combo.blockSignals(False)

    # ── Interaction handlers ──────────────────────────────────────────────────

    def _on_list_changed(self, idx: int):
        if idx < 0:
            return
        list_id = self._list_combo.itemData(idx)
        if list_id:
            self._active_list_id = list_id
            self.refresh()

    def _on_search(self, text: str):
        self._search_text = text
        self.refresh()

    def _on_filter(self, _):
        self._filter_category = self._cat_filter.currentData() or "All"
        self.refresh()

    def _on_purchased_toggled(self, item_id: int, purchased: bool):
        self._service.set_purchased(item_id, purchased)
        self._context.event_bus.emit("shopping_item_updated", {"item_id": item_id})
        self._update_stats()

    def _on_edit_item(self, item: ShoppingItem):
        sections = self._service.get_sections(self._active_list_id)
        dlg = _ItemDialog(sections, item=item, parent=self)
        if dlg.exec():
            result = dlg.result_item()
            if result:
                result.list_id = self._active_list_id
                self._service.update_item(result)
                self._context.event_bus.emit("shopping_item_updated",
                                             {"item_id": result.id})
                self.refresh()

    def _on_delete_item(self, item_id: int):
        self._service.delete_item(item_id)
        self._context.event_bus.emit("shopping_item_removed", {"item_id": item_id})
        self.refresh()

    def _on_rename_section(self, section_id: int, current_title: str):
        title, ok = QInputDialog.getText(
            self, "Rename Section", "Section name:", text=current_title
        )
        if ok and title.strip():
            try:
                self._service.rename_section(section_id, title.strip())
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _on_delete_section(self, section_id: int):
        reply = QMessageBox.question(
            self, "Delete Section",
            "Delete this section and all its items?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.delete_section(section_id)
            self.refresh()

    def _on_section_add_item(self, section_id: int):
        self.open_add_dialog(default_section_id=section_id)

    def open_add_dialog(self, default_section_id: int = 0):
        if self._active_list_id is None:
            return
        sections = self._service.get_sections(self._active_list_id)
        if not sections:
            self._service.create_section(self._active_list_id, "General")
            sections = self._service.get_sections(self._active_list_id)
        if not default_section_id and sections:
            default_section_id = sections[0].id
        dlg = _ItemDialog(sections, default_section_id=default_section_id, parent=self)
        if dlg.exec():
            result = dlg.result_item()
            if result:
                result.list_id = self._active_list_id
                item, merged = self._service.add_item(result, merge_duplicates=True)
                self._context.event_bus.emit("shopping_item_added",
                                             {"item_id": item.id, "merged": merged})
                self.refresh()

    def _open_inventory_picker(self):
        if self._active_list_id is None:
            return
        sections = self._service.get_sections(self._active_list_id)
        if not sections:
            self._service.create_section(self._active_list_id, "General")
            sections = self._service.get_sections(self._active_list_id)
        dlg = _InventoryPickerDialog(
            self._context, self._active_list_id, sections, parent=self
        )
        if dlg.exec():
            for sel in dlg.selections():
                item = ShoppingItem(
                    name=sel.get("name", ""),
                    list_id=self._active_list_id,
                    section_id=sel.get("section_id", sections[0].id if sections else 0),
                    category=sel.get("category", "Other"),
                    quantity=1.0,
                    source_plugin=sel.get("source_plugin", ""),
                    source_item_id=sel.get("source_item_id", ""),
                )
                if item.name:
                    self._service.add_item(item, merge_duplicates=True)
            self.refresh()

    def _new_section(self):
        if self._active_list_id is None:
            return
        title, ok = QInputDialog.getText(
            self, "New Section", "Section name:"
        )
        if ok and title.strip():
            try:
                self._service.create_section(self._active_list_id, title.strip())
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _open_export(self):
        if self._active_list_id is None:
            return
        sl = self._service._repo.get_list(self._active_list_id)
        name = sl.name if sl else "Shopping List"
        dlg = _ExportDialog(self._service, self._active_list_id, name, parent=self)
        dlg.exec()

    def _new_list(self):
        name, ok = QInputDialog.getText(
            self, "New Shopping List", "List name:"
        )
        if ok and name.strip():
            try:
                sl = self._service.create_list(name.strip())
                self._active_list_id = sl.id
                self._update_list_combo()
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _show_list_menu(self):
        if self._active_list_id is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; color:{_C['text_hi']}; padding:4px;}}"
            f"QMenu::item{{padding:6px 20px 6px 12px; border-radius:{_R['xs']};}}"
            f"QMenu::item:selected{{background:{_C['bg_hover']};}}"
        )
        rename_act = menu.addAction("✏  Rename this list")
        menu.addSeparator()
        delete_act = menu.addAction("🗑  Delete this list")
        act = menu.exec(self.cursor().pos())
        if act == rename_act:
            self._rename_current_list()
        elif act == delete_act:
            self._delete_current_list()

    def _rename_current_list(self):
        lists = self._service.get_all_lists()
        current = next((sl for sl in lists if sl.id == self._active_list_id), None)
        if not current:
            return
        name, ok = QInputDialog.getText(
            self, "Rename List", "New name:", text=current.name
        )
        if ok and name.strip():
            try:
                self._service.rename_list(self._active_list_id, name.strip())
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _delete_current_list(self):
        lists = self._service.get_all_lists()
        if len(lists) <= 1:
            QMessageBox.information(
                self, "Cannot Delete",
                "You must have at least one shopping list."
            )
            return
        reply = QMessageBox.question(
            self, "Delete List",
            "Permanently delete this shopping list and all its items?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.delete_list(self._active_list_id)
            self._active_list_id = None
            self._init_list()

    def _remove_purchased(self):
        if self._active_list_id is None:
            return
        self._service.delete_purchased(self._active_list_id)
        self._context.event_bus.emit("shopping_list_cleared",
                                     {"list_id": self._active_list_id, "type": "purchased"})
        self.refresh()

    def _clear_all(self):
        reply = QMessageBox.question(
            self, "Clear All Items",
            "Remove all items from this shopping list? Section headers will remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.clear_list(self._active_list_id)
            self._context.event_bus.emit("shopping_list_cleared",
                                         {"list_id": self._active_list_id, "type": "all"})
            self.refresh()
