"""
Army Builder 2.0 — Premium UI
Five sections: Lists · Builder · Paints · Gallery · Statistics
Direct service calls, no event-bus CRUD.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QGridLayout, QSpinBox, QDoubleSpinBox, QTextEdit, QMessageBox,
    QFileDialog, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QListWidget, QListWidgetItem,
    QApplication, QProgressBar, QSplitter, QSizePolicy, QInputDialog,
)

from plugins.army_builder.models import (
    Army, ArmyUnit, ArmyFilter,
    UNIT_ROLES, ARMY_FORMATS,
    get_roles_for_system, get_formats_for_system, parse_points_limit,
    ValidationError,
)

# ── Colours (match paint/materials v2) ────────────────────────────────────────
_BG        = "#1c1c1c"
_BG_HOVER  = "#252525"
_BORDER    = "#2e2e2e"
_BORDER_HV = "#3a3a3a"
_FG_HI     = "#f0f0f0"
_FG_LO     = "#686868"

# ── Points bar colours ────────────────────────────────────────────────────────
def _pts_color(used: float, limit: float) -> str:
    if limit <= 0:
        return "#4f9eff"
    pct = used / limit
    if pct > 1.0:
        return "#e05555"
    if pct >= 0.9:
        return "#3dba6e"
    if pct >= 0.5:
        return "#4f9eff"
    return "#e07800"

def _fmt_pts(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:g}"


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
#  Paint Link Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _PaintLinkDialog(QDialog):
    def __init__(self, context, current_paint_ids: list[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link Paints to Unit")
        self.setMinimumSize(500, 500)
        self._ctx          = context
        self._selected_ids = list(current_paint_ids)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Select paints used for this unit.\nThese appear in the Army Paints view."))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter paints…")
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.NoSelection)
        lay.addWidget(self._list)
        self._populate()
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _populate(self):
        svc = self._ctx.services.try_get("paint_service") if self._ctx else None
        if not svc:
            self._list.addItem(QListWidgetItem("⚠  Paint Tracker not available"))
            return
        try:
            paints = svc.get_all_paints()
        except Exception as e:
            self._list.addItem(QListWidgetItem(f"⚠  {e}"))
            return
        if not paints:
            self._list.addItem(QListWidgetItem("No paints yet — add them in Paint Tracker."))
            return
        for p in paints:
            hint = f"  {p.color}" if (p.color and p.color.startswith("#")) else ""
            item = QListWidgetItem(f"{p.brand} — {p.name}  [{p.paint_type}]{hint}")
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if p.id in self._selected_ids else Qt.Unchecked)
            item.setData(Qt.UserRole, p.id)
            self._list.addItem(item)

    def _filter(self, text: str):
        needle = text.lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(needle not in item.text().lower())

    def _on_ok(self):
        self._selected_ids = [
            self._list.item(i).data(Qt.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.Checked
            and self._list.item(i).data(Qt.UserRole) is not None
        ]
        self.accept()

    def get_selected_ids(self) -> list[int]:
        return self._selected_ids


# ══════════════════════════════════════════════════════════════════════════════
#  Army Edit Dialog (create / edit army metadata)
# ══════════════════════════════════════════════════════════════════════════════

class _ArmyDialog(QDialog):
    def __init__(self, army: Optional[Army] = None, context=None, parent=None):
        super().__init__(parent)
        self._army = army
        self._ctx  = context
        self.setWindowTitle("Edit Army" if army else "New Army")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build()
        if army:
            self._populate(army)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(14)

        title = QLabel("Edit Army" if self._army else "New Army")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(title)

        form = QGridLayout()
        form.setSpacing(10)
        form.setColumnStretch(1, 1)
        form.setColumnMinimumWidth(0, 120)

        def _row(label, widget, row):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.50);")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.addWidget(lbl, row, 0)
            form.addWidget(widget, row, 1)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Iron Warriors — 2000pts")
        _row("List Name *", self._name_edit, 0)

        self._system_combo = QComboBox()
        self._system_combo.setEditable(True)
        self._system_combo.addItems([""] + list(ARMY_FORMATS.keys()))
        self._system_combo.currentTextChanged.connect(self._on_system_changed)
        _row("Game System *", self._system_combo, 1)

        self._faction_edit = QLineEdit()
        self._faction_edit.setPlaceholderText("e.g. Space Marines, Orks")
        _row("Faction *", self._faction_edit, 2)

        self._format_combo = QComboBox()
        self._format_combo.setEditable(True)
        self._format_combo.currentTextChanged.connect(self._on_format_changed)
        _row("Format *", self._format_combo, 3)

        self._pts_spin = QSpinBox()
        self._pts_spin.setRange(0, 99999)
        self._pts_spin.setSpecialValueText("No limit")
        self._pts_spin.setSuffix(" pts")
        _row("Points Limit", self._pts_spin, 4)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Optional notes…")
        self._notes_edit.setFixedHeight(68)
        _row("Notes", self._notes_edit, 5)

        lay.addLayout(form)

        div = QFrame(); div.setFrameShape(QFrame.HLine); div.setFixedHeight(1)
        lay.addWidget(div)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

        self._on_system_changed(self._system_combo.currentText())

    def _on_system_changed(self, system: str):
        formats = get_formats_for_system(system) if system else []
        current = self._format_combo.currentText()
        self._format_combo.blockSignals(True)
        self._format_combo.clear()
        self._format_combo.addItems(formats)
        idx = self._format_combo.findText(current)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)
        self._format_combo.blockSignals(False)
        self._on_format_changed(self._format_combo.currentText())

    def _on_format_changed(self, fmt: str):
        pts = parse_points_limit(fmt)
        if pts > 0:
            self._pts_spin.setValue(pts)

    def _populate(self, a: Army):
        self._name_edit.setText(a.name)
        idx = self._system_combo.findText(a.game_system)
        if idx >= 0:
            self._system_combo.setCurrentIndex(idx)
        else:
            self._system_combo.setCurrentText(a.game_system)
        self._faction_edit.setText(a.faction or "")
        fidx = self._format_combo.findText(a.format)
        if fidx >= 0:
            self._format_combo.setCurrentIndex(fidx)
        else:
            self._format_combo.setCurrentText(a.format)
        self._pts_spin.setValue(a.points_limit)
        self._notes_edit.setPlainText(a.notes or "")

    def _validate_and_accept(self):
        if not self._name_edit.text().strip():
            self._name_edit.setFocus()
            return
        if not self._faction_edit.text().strip():
            self._faction_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name":         self._name_edit.text().strip(),
            "game_system":  self._system_combo.currentText().strip(),
            "faction":      self._faction_edit.text().strip(),
            "format":       self._format_combo.currentText().strip(),
            "points_limit": self._pts_spin.value(),
            "notes":        self._notes_edit.toPlainText().strip() or None,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Unit Edit Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _UnitDialog(QDialog):
    def __init__(self, army: Army, unit: Optional[ArmyUnit] = None,
                 context=None, parent=None):
        super().__init__(parent)
        self._army = army
        self._unit = unit
        self._ctx  = context
        self._linked_paint_ids: list[int] = list(unit.linked_paint_ids) if unit else []
        self.setWindowTitle("Edit Unit" if unit else "Add Unit")
        self.setMinimumWidth(560)
        self.setModal(True)
        self._build()
        if unit:
            self._populate(unit)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(14)

        title = QLabel("Edit Unit" if self._unit else "Add Unit")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(title)

        form = QGridLayout()
        form.setSpacing(10)
        form.setColumnStretch(1, 1)
        form.setColumnMinimumWidth(0, 130)

        def _row(label, widget, row):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.50);")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.addWidget(lbl, row, 0)
            form.addWidget(widget, row, 1)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Tactical Squad, Mage")
        _row("Unit Name *", self._name_edit, 0)

        self._role_combo = QComboBox()
        self._role_combo.setEditable(True)
        roles = get_roles_for_system(self._army.game_system)
        self._role_combo.addItems(roles)
        _row("Role *", self._role_combo, 1)

        pts_row = QHBoxLayout()
        self._pts_spin = QDoubleSpinBox()
        self._pts_spin.setRange(0, 99999)
        self._pts_spin.setDecimals(1)
        self._pts_spin.setSuffix(" pts")
        self._pts_spin.valueChanged.connect(self._update_total)
        pts_row.addWidget(self._pts_spin, 1)

        pts_row.addWidget(QLabel("×"))
        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 9999)
        self._qty_spin.setFixedWidth(72)
        self._qty_spin.valueChanged.connect(self._update_total)
        pts_row.addWidget(self._qty_spin)

        self._total_lbl = QLabel("= 0 pts")
        self._total_lbl.setStyleSheet("color: #4f9eff; font-size: 12px; font-weight: 600;")
        pts_row.addWidget(self._total_lbl)

        pts_widget = QWidget()
        pts_widget.setLayout(pts_row)
        _row("Points / Model", pts_widget, 2)

        self._wargear_edit = QTextEdit()
        self._wargear_edit.setPlaceholderText("Wargear, abilities, loadout details…")
        self._wargear_edit.setFixedHeight(72)
        _row("Wargear / Notes", self._wargear_edit, 3)

        # Model link
        self._model_combo = QComboBox()
        self._model_combo.addItem("— None —", None)
        self._populate_model_combo()
        _row("Linked Model", self._model_combo, 4)

        # Paint links button
        self._paints_btn = QPushButton("Link Paints…")
        self._paints_btn.setObjectName("secondaryBtn")
        self._paints_btn.clicked.connect(self._open_paint_dialog)
        self._paints_lbl = QLabel("None")
        self._paints_lbl.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.45);")

        paints_widget = QWidget()
        pl = QHBoxLayout(paints_widget)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(self._paints_btn)
        pl.addWidget(self._paints_lbl, 1)
        _row("Paints", paints_widget, 5)

        lay.addLayout(form)
        self._refresh_paints_label()

        div = QFrame(); div.setFrameShape(QFrame.HLine); div.setFixedHeight(1)
        lay.addWidget(div)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _populate_model_combo(self):
        svc = self._ctx.services.try_get("model_service") if self._ctx else None
        if not svc:
            return
        try:
            models = svc.get_all_models()
            for m in models:
                self._model_combo.addItem(m.name, m.id)
        except Exception:
            pass

    def _update_total(self):
        total = self._pts_spin.value() * self._qty_spin.value()
        self._total_lbl.setText(f"= {_fmt_pts(total)} pts")

    def _open_paint_dialog(self):
        dlg = _PaintLinkDialog(self._ctx, self._linked_paint_ids, parent=self)
        if dlg.exec():
            self._linked_paint_ids = dlg.get_selected_ids()
            self._refresh_paints_label()

    def _refresh_paints_label(self):
        count = len(self._linked_paint_ids)
        self._paints_lbl.setText(
            f"{count} paint{'s' if count != 1 else ''} linked"
            if count else "None"
        )

    def _populate(self, u: ArmyUnit):
        self._name_edit.setText(u.unit_name)
        idx = self._role_combo.findText(u.unit_role)
        if idx >= 0:
            self._role_combo.setCurrentIndex(idx)
        else:
            self._role_combo.setCurrentText(u.unit_role)
        self._pts_spin.setValue(u.points_cost)
        self._qty_spin.setValue(u.quantity)
        self._wargear_edit.setPlainText(u.wargear_notes or "")
        if u.model_id:
            midx = self._model_combo.findData(u.model_id)
            if midx >= 0:
                self._model_combo.setCurrentIndex(midx)
        self._update_total()
        self._refresh_paints_label()

    def _validate_and_accept(self):
        if not self._name_edit.text().strip():
            self._name_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "unit_name":        self._name_edit.text().strip(),
            "unit_role":        self._role_combo.currentText().strip(),
            "points_cost":      self._pts_spin.value(),
            "quantity":         self._qty_spin.value(),
            "wargear_notes":    self._wargear_edit.toPlainText().strip() or None,
            "model_id":         self._model_combo.currentData(),
            "linked_paint_ids": self._linked_paint_ids,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Export Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _ExportDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Army List")
        self.setMinimumSize(560, 540)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Copy the text below to share your list:"))
        area = QTextEdit()
        area.setPlainText(text)
        area.setReadOnly(True)
        area.setFont(QFont("Courier New", 9))
        lay.addWidget(area)
        self._area = area
        row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setObjectName("primaryBtn")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(copy_btn)
        row.addStretch()
        row.addWidget(close_btn)
        lay.addLayout(row)

    def _copy(self):
        QApplication.clipboard().setText(self._area.toPlainText())


# ══════════════════════════════════════════════════════════════════════════════
#  Army Card (for card grid view in Lists)
# ══════════════════════════════════════════════════════════════════════════════

_CARD_W   = 220
_CARD_H   = 160
_CARD_GAP = 12


class _ArmyCard(QFrame):
    open_requested      = Signal(object)
    edit_requested      = Signal(object)
    duplicate_requested = Signal(object)
    delete_requested    = Signal(object)

    def __init__(self, army: Army, pts_used: float, unit_count: int, parent=None):
        super().__init__(parent)
        self._army      = army
        self._pts_used  = pts_used
        self._unit_count = unit_count
        self._build()

    def _build(self):
        self.setObjectName("armyCard")
        self.setFixedSize(_CARD_W, _CARD_H)
        self.setCursor(Qt.PointingHandCursor)

        limit = self._army.points_limit
        color = _pts_color(self._pts_used, limit)

        self.setStyleSheet(f"""
            QFrame#armyCard {{
                background-color: {_BG};
                border: 1px solid {_BORDER};
                border-radius: 12px;
            }}
            QFrame#armyCard:hover {{
                background-color: {_BG_HOVER};
                border-color: {_BORDER_HV};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(0)

        # Top row: system chip + points chip
        top = QHBoxLayout(); top.setContentsMargins(0,0,0,0); top.setSpacing(6)

        sys_chip = QLabel(self._army.game_system[:14] + ("…" if len(self._army.game_system) > 14 else ""))
        sys_chip.setStyleSheet(f"""
            color: #4f9eff; background: rgba(79,158,255,0.13);
            font-size: 9px; font-weight: 700; letter-spacing: 0.3px;
            padding: 2px 7px; border-radius: 5px; border: none;
        """)
        top.addWidget(sys_chip)
        top.addStretch()

        if limit > 0:
            pct = min(int(self._pts_used / limit * 100), 999)
            pts_chip = QLabel(f"{pct}%")
            pts_chip.setStyleSheet(f"""
                color: {color}; background: rgba(128,128,128,0.10);
                font-size: 9px; font-weight: 700;
                padding: 2px 7px; border-radius: 5px; border: none;
            """)
            top.addWidget(pts_chip)

        root.addLayout(top)
        root.addSpacing(8)

        # Army name
        name_lbl = QLabel(self._army.name)
        name_lbl.setStyleSheet(f"""
            font-size: 13px; font-weight: 700; color: {_FG_HI};
            background: transparent; border: none;
        """)
        name_lbl.setWordWrap(True)
        name_lbl.setMaximumHeight(40)
        root.addWidget(name_lbl)

        root.addSpacing(3)

        # Faction
        faction_lbl = QLabel(self._army.faction)
        faction_lbl.setStyleSheet(f"""
            font-size: 11px; color: {_FG_LO};
            background: transparent; border: none;
        """)
        faction_lbl.setWordWrap(True)
        faction_lbl.setMaximumHeight(28)
        root.addWidget(faction_lbl)

        root.addStretch()

        # Divider
        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background: #2a2a2a; border: none; max-height: 1px;")
        div.setFixedHeight(1)
        root.addWidget(div)
        root.addSpacing(8)

        # Bottom row: units count + points
        bot = QHBoxLayout(); bot.setContentsMargins(0,0,0,0); bot.setSpacing(0)
        units_lbl = QLabel(f"{self._unit_count} unit{'s' if self._unit_count != 1 else ''}")
        units_lbl.setStyleSheet(f"font-size: 10px; color: {_FG_LO}; background: transparent; border: none;")
        bot.addWidget(units_lbl)
        bot.addStretch()

        if self._pts_used > 0 or limit > 0:
            pts_str = _fmt_pts(self._pts_used)
            lim_str = f" / {_fmt_pts(limit)}" if limit > 0 else ""
            pts_lbl = QLabel(f"{pts_str}{lim_str} pts")
            pts_lbl.setStyleSheet(f"""
                font-size: 11px; font-weight: 600; color: {color};
                background: transparent; border: none;
            """)
            bot.addWidget(pts_lbl)

        root.addLayout(bot)

    def mouseDoubleClickEvent(self, event):
        self.open_requested.emit(self._army)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        open_act  = menu.addAction("⚔  Open in Builder")
        menu.addSeparator()
        edit_act  = menu.addAction("✏  Edit Details")
        dup_act   = menu.addAction("⎘  Duplicate")
        menu.addSeparator()
        del_act   = menu.addAction("🗑  Delete")
        act = menu.exec(event.globalPos())
        if act == open_act:
            self.open_requested.emit(self._army)
        elif act == edit_act:
            self.edit_requested.emit(self._army)
        elif act == dup_act:
            self.duplicate_requested.emit(self._army)
        elif act == del_act:
            self.delete_requested.emit(self._army)


# ══════════════════════════════════════════════════════════════════════════════
#  Gallery Thumbnail
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  Army Gallery Stage
# ══════════════════════════════════════════════════════════════════════════════

class _ArmyGalleryStage:
    BEFORE    = "before"
    DURING    = "during"
    AFTER     = "after"
    REFERENCE = "reference"
    COMPLETED = "completed"
    NONE      = ""

    ALL = [BEFORE, DURING, AFTER, REFERENCE, COMPLETED]
    LABELS = {
        BEFORE:    "Before",
        DURING:    "During",
        AFTER:     "After",
        REFERENCE: "Reference",
        COMPLETED: "Completed",
        NONE:      "—",
    }
    COLORS = {
        BEFORE:    "#5c6bc0",
        DURING:    "#e07820",
        AFTER:     "#2e7d32",
        REFERENCE: "#0078d4",
        COMPLETED: "#8338ec",
        NONE:      "#606060",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Army Gallery Card  (hover overlay — View / Edit / Remove)
# ══════════════════════════════════════════════════════════════════════════════

# Gallery card geometry (matches project tracker)
_GALLERY_CARD_W   = 210
_GALLERY_CARD_H   = 245
_GALLERY_THUMB_H  = 158
_GALLERY_CARD_GAP = 12


class _ArmyGalleryCard(QFrame):
    open_requested         = Signal(int)       # list index
    edit_requested         = Signal(object)    # GalleryEntry
    delete_requested       = Signal(object)    # GalleryEntry
    stage_change_requested = Signal(object, str)  # (entry, stage)

    _STAGE_CYCLE = [""] + list(_ArmyGalleryStage.ALL)

    def __init__(self, entry, index: int, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._index = index
        self.setObjectName("galleryCard")
        self.setFixedSize(_GALLERY_CARD_W, _GALLERY_CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 6)
        lay.setSpacing(4)

        # ── Thumbnail ──────────────────────────────────────────────────────
        self._thumb = QLabel()
        self._thumb.setObjectName("galleryThumb")
        self._thumb.setFixedSize(_GALLERY_CARD_W - 8, _GALLERY_THUMB_H)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._load_thumb()
        lay.addWidget(self._thumb)

        # ── Caption (title) ────────────────────────────────────────────────
        caption = (getattr(self._entry, "caption", "") or "").strip()
        if caption:
            cap_lbl = QLabel()
            cap_lbl.setObjectName("galleryCardTitle")
            fm = cap_lbl.fontMetrics()
            cap_lbl.setText(fm.elidedText(caption, Qt.ElideRight, _GALLERY_CARD_W - 16))
            lay.addWidget(cap_lbl)

        # ── Date + stage badge row ─────────────────────────────────────────
        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(4)

        date_str = getattr(self._entry, "created_at", "") or ""
        try:
            date_str = date_str[:10]  # ISO date portion only
            from datetime import date as _date
            date_str = _date.fromisoformat(date_str).strftime("%b %d, %Y")
        except Exception:
            pass
        d_lbl = QLabel(f"📅  {date_str}")
        d_lbl.setObjectName("galleryCardDate")
        meta.addWidget(d_lbl)
        meta.addStretch()

        stage = getattr(self._entry, "progress_stage", "") or ""
        stage_color = _ArmyGalleryStage.COLORS.get(stage, "#606060") if stage else "#404040"
        stage_label = _ArmyGalleryStage.LABELS.get(stage, stage) if stage else "＋ Stage"
        self._stage_btn = QPushButton(stage_label)
        self._stage_btn.setObjectName("galleryStageBtn")
        self._stage_btn.setCursor(Qt.PointingHandCursor)
        self._stage_btn.setToolTip(
            "Left-click to cycle stage  ·  Right-click to choose"
        )
        self._stage_btn.setStyleSheet(
            f"QPushButton#galleryStageBtn {{"
            f"  background: {stage_color}33; color: {stage_color}; "
            f"  border: 1px solid {stage_color}55; border-radius: 3px; "
            f"  padding: 0px 5px; font-size: 10px; font-weight: 700;"
            f"}}"
            f"QPushButton#galleryStageBtn:hover {{"
            f"  background: {stage_color}55;"
            f"}}"
        )
        self._stage_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self._stage_btn.clicked.connect(self._cycle_stage)
        self._stage_btn.customContextMenuRequested.connect(self._stage_menu)
        meta.addWidget(self._stage_btn)
        lay.addLayout(meta)

        # ── Hover overlay — covers thumbnail area only ─────────────────────
        self._overlay = QWidget(self)
        self._overlay.setObjectName("galleryCardOverlay")
        self._overlay.setGeometry(4, 4, _GALLERY_CARD_W - 8, _GALLERY_THUMB_H)
        self._overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._overlay.hide()

        ov_lay = QVBoxLayout(self._overlay)
        ov_lay.setAlignment(Qt.AlignCenter)
        ov_lay.setSpacing(8)

        view_btn = QPushButton("🔍  View")
        view_btn.setObjectName("primaryBtn")
        view_btn.setFixedWidth(100)
        view_btn.clicked.connect(lambda: self.open_requested.emit(self._index))

        edit_btn = QPushButton("✏  Edit")
        edit_btn.setObjectName("secondaryBtn")
        edit_btn.setFixedWidth(100)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._entry))

        del_btn = QPushButton("Remove")
        del_btn.setObjectName("dangerBtn")
        del_btn.setFixedWidth(100)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._entry))

        ov_lay.addWidget(view_btn)
        ov_lay.addWidget(edit_btn)
        ov_lay.addWidget(del_btn)

    def _load_thumb(self):
        try:
            path = getattr(self._entry, "image_path", "")
            if path and os.path.isfile(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    self._thumb.setPixmap(
                        pix.scaled(
                            _GALLERY_CARD_W - 8, _GALLERY_THUMB_H,
                            Qt.KeepAspectRatio, Qt.SmoothTransformation,
                        )
                    )
                    return
        except Exception:
            pass
        self._thumb.setText("📷")
        self._thumb.setStyleSheet("font-size: 28px; color: #555; background: transparent;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(4, 4, self.width() - 8, _GALLERY_THUMB_H)

    def enterEvent(self, event):
        self._overlay.show()
        self._overlay.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._overlay.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_requested.emit(self._index)
        super().mousePressEvent(event)

    # ── Stage cycling ──────────────────────────────────────────────────────

    def _cycle_stage(self):
        current = getattr(self._entry, "progress_stage", "") or ""
        try:
            idx = self._STAGE_CYCLE.index(current)
        except ValueError:
            idx = 0
        new_stage = self._STAGE_CYCLE[(idx + 1) % len(self._STAGE_CYCLE)]
        self.stage_change_requested.emit(self._entry, new_stage)

    def _stage_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        current = getattr(self._entry, "progress_stage", "") or ""

        act_none = menu.addAction("— None")
        act_none.setCheckable(True)
        act_none.setChecked(current == "")
        act_none.triggered.connect(
            lambda: self.stage_change_requested.emit(self._entry, "")
        )
        menu.addSeparator()
        for s in _ArmyGalleryStage.ALL:
            label = _ArmyGalleryStage.LABELS.get(s, s)
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(current == s)
            act.triggered.connect(
                lambda _checked, _s=s:
                    self.stage_change_requested.emit(self._entry, _s)
            )
        menu.exec(self._stage_btn.mapToGlobal(pos))


# ══════════════════════════════════════════════════════════════════════════════
#  Army Photo Lightbox
# ══════════════════════════════════════════════════════════════════════════════

class _ArmyPhotoLightbox(QDialog):
    """Full-size photo viewer with prev/next navigation."""
    edit_requested   = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, entries: list, start_index: int, parent=None):
        super().__init__(parent)
        self._entries = entries
        self._index   = start_index
        self.setObjectName("lightboxDialog")
        self.setModal(True)
        self.setWindowTitle("Army Gallery")
        screen = QApplication.primaryScreen().availableGeometry()
        w = min(1100, int(screen.width()  * 0.88))
        h = min(780,  int(screen.height() * 0.88))
        self.resize(w, h)
        self._build()
        self._show_entry(self._index)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("lightboxHeader")
        header.setFixedHeight(44)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 12, 0)
        self._counter_lbl = QLabel()
        self._counter_lbl.setObjectName("lightboxCounter")
        h_lay.addWidget(self._counter_lbl)
        h_lay.addStretch()
        close_btn = QPushButton("✕  Close")
        close_btn.setObjectName("ghostBtn")
        close_btn.setFixedHeight(28)
        close_btn.clicked.connect(self.accept)
        h_lay.addWidget(close_btn)
        root.addWidget(header)

        # ── Image area ────────────────────────────────────────────────────
        img_row = QHBoxLayout()
        img_row.setContentsMargins(0, 0, 0, 0)
        img_row.setSpacing(0)

        self._prev_btn = QPushButton("‹")
        self._prev_btn.setObjectName("lightboxNavBtn")
        self._prev_btn.setFixedWidth(48)
        self._prev_btn.clicked.connect(self._go_prev)
        img_row.addWidget(self._prev_btn)

        self._image_lbl = QLabel()
        self._image_lbl.setObjectName("lightboxImage")
        self._image_lbl.setAlignment(Qt.AlignCenter)
        self._image_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        img_row.addWidget(self._image_lbl, stretch=1)

        self._next_btn = QPushButton("›")
        self._next_btn.setObjectName("lightboxNavBtn")
        self._next_btn.setFixedWidth(48)
        self._next_btn.clicked.connect(self._go_next)
        img_row.addWidget(self._next_btn)

        root.addLayout(img_row, stretch=1)

        # ── Info panel ────────────────────────────────────────────────────
        info = QWidget()
        info.setObjectName("lightboxInfo")
        info.setFixedHeight(100)
        i_lay = QVBoxLayout(info)
        i_lay.setContentsMargins(24, 10, 24, 10)
        i_lay.setSpacing(4)

        # Caption row + action buttons
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._caption_lbl = QLabel()
        self._caption_lbl.setObjectName("lightboxTitle")
        title_row.addWidget(self._caption_lbl, stretch=1)

        self._edit_btn = QPushButton("✏  Edit")
        self._edit_btn.setObjectName("secondaryBtn")
        self._edit_btn.setFixedHeight(28)
        self._edit_btn.clicked.connect(self._on_edit)
        title_row.addWidget(self._edit_btn)

        self._del_btn = QPushButton("Remove")
        self._del_btn.setObjectName("dangerBtn")
        self._del_btn.setFixedHeight(28)
        self._del_btn.clicked.connect(self._on_delete)
        title_row.addWidget(self._del_btn)
        i_lay.addLayout(title_row)

        # Meta row (date + stage)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(16)
        self._date_lbl = QLabel()
        self._date_lbl.setObjectName("lightboxMeta")
        meta_row.addWidget(self._date_lbl)
        self._stage_lbl = QLabel()
        self._stage_lbl.setObjectName("lightboxMeta")
        meta_row.addWidget(self._stage_lbl)
        meta_row.addStretch()
        i_lay.addLayout(meta_row)
        root.addWidget(info)

    def _show_entry(self, idx: int):
        if not self._entries:
            return
        self._index = max(0, min(idx, len(self._entries) - 1))
        entry = self._entries[self._index]
        n = len(self._entries)

        self._counter_lbl.setText(f"Photo {self._index + 1} of {n}")
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < n - 1)

        # Image
        img_w = self.width()  - 96
        img_h = self.height() - 44 - 100
        try:
            path = getattr(entry, "image_path", "")
            if path and os.path.isfile(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    self._image_lbl.setPixmap(
                        pix.scaled(img_w, img_h,
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                else:
                    self._image_lbl.setText("⚠  Could not load image")
            else:
                self._image_lbl.setText("⚠  Image file not found")
        except Exception:
            self._image_lbl.setText("⚠  Error loading image")

        # Caption
        caption = getattr(entry, "caption", "") or ""
        self._caption_lbl.setText(caption if caption else "Untitled")

        # Date
        date_str = getattr(entry, "created_at", "") or ""
        try:
            from datetime import date as _date
            date_str = _date.fromisoformat(date_str[:10]).strftime("%B %d, %Y")
        except Exception:
            pass
        self._date_lbl.setText(f"📅  {date_str}")

        # Stage
        stage = getattr(entry, "progress_stage", "") or ""
        if stage:
            label = _ArmyGalleryStage.LABELS.get(stage, stage)
            color = _ArmyGalleryStage.COLORS.get(stage, "#606060")
            self._stage_lbl.setText(f"● {label}")
            self._stage_lbl.setStyleSheet(f"color: {color};")
            self._stage_lbl.show()
        else:
            self._stage_lbl.hide()

    def _go_prev(self):
        self._show_entry(self._index - 1)

    def _go_next(self):
        self._show_entry(self._index + 1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self._go_prev()
        elif event.key() == Qt.Key_Right:
            self._go_next()
        elif event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Space):
            self.accept()
        else:
            super().keyPressEvent(event)

    def _on_edit(self):
        self.edit_requested.emit(self._entries[self._index])
        self.accept()

    def _on_delete(self):
        self.delete_requested.emit(self._entries[self._index])
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  Army Add / Edit Photo Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _ArmyAddPhotoDialog(QDialog):
    """Add a new gallery entry or edit an existing one."""

    def __init__(self, entry=None, parent=None):
        super().__init__(parent)
        self._entry       = entry   # None → add mode
        self._source_path: Optional[str] = None
        self._result:      Optional[dict] = None

        self.setWindowTitle("Edit Photo" if entry else "Add Photo")
        self.setModal(True)
        self.setMinimumSize(500, 520)
        self._build()
        if entry:
            self._populate(entry)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # ── Image preview area ────────────────────────────────────────────
        preview_frame = QFrame()
        preview_frame.setObjectName("galleryImgPreviewFrame")
        preview_frame.setFixedHeight(200)
        pf_lay = QVBoxLayout(preview_frame)
        pf_lay.setContentsMargins(0, 0, 0, 0)
        pf_lay.setAlignment(Qt.AlignCenter)

        self._preview_lbl = QLabel("No photo selected")
        self._preview_lbl.setObjectName("galleryImgPreview")
        self._preview_lbl.setAlignment(Qt.AlignCenter)
        self._preview_lbl.setFixedSize(456, 192)
        pf_lay.addWidget(self._preview_lbl)
        root.addWidget(preview_frame)

        # Browse row
        browse_row = QHBoxLayout()
        self._browse_btn = QPushButton("🖼  Browse…")
        self._browse_btn.setObjectName("secondaryBtn")
        self._browse_btn.setFixedHeight(30)
        self._browse_btn.clicked.connect(self._browse)
        browse_row.addWidget(self._browse_btn)
        self._file_lbl = QLabel("No file selected")
        self._file_lbl.setObjectName("metaLabel")
        browse_row.addWidget(self._file_lbl, stretch=1)
        root.addLayout(browse_row)

        # ── Form ──────────────────────────────────────────────────────────
        form = QGridLayout()
        form.setSpacing(8)
        form.setColumnMinimumWidth(0, 90)
        form.setColumnStretch(1, 1)

        form.addWidget(QLabel("Caption"), 0, 0)
        self._caption_input = QLineEdit()
        self._caption_input.setPlaceholderText("Optional — e.g. 'After priming'")
        self._caption_input.setFixedHeight(30)
        form.addWidget(self._caption_input, 0, 1)

        form.addWidget(QLabel("Progress Stage"), 1, 0)
        self._stage_combo = QComboBox()
        self._stage_combo.setFixedHeight(30)
        self._stage_combo.addItem("— None —", "")
        for stage in _ArmyGalleryStage.ALL:
            self._stage_combo.addItem(_ArmyGalleryStage.LABELS.get(stage, stage), stage)
        form.addWidget(self._stage_combo, 1, 1)
        root.addLayout(form)

        root.addStretch()

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("ghostBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._save_btn = QPushButton("Add Photo" if not self._entry else "Save Changes")
        self._save_btn.setObjectName("primaryBtn")
        self._save_btn.setFixedHeight(34)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        root.addLayout(btn_row)

    def _populate(self, entry):
        self._source_path = getattr(entry, "image_path", None)
        self._caption_input.setText(getattr(entry, "caption", "") or "")
        stage = getattr(entry, "progress_stage", "") or ""
        for i in range(self._stage_combo.count()):
            if self._stage_combo.itemData(i) == stage:
                self._stage_combo.setCurrentIndex(i)
                break
        path = getattr(entry, "image_path", "")
        if path and os.path.isfile(path):
            self._load_preview(path)
            self._file_lbl.setText(os.path.basename(path))

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Photo", "",
            "Images (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tiff *.tif)"
        )
        if path:
            self._source_path = path
            self._file_lbl.setText(os.path.basename(path))
            self._load_preview(path)

    def _load_preview(self, path: str):
        try:
            pix = QPixmap(path)
            if not pix.isNull():
                self._preview_lbl.setPixmap(
                    pix.scaled(452, 188, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                return
        except Exception:
            pass
        self._preview_lbl.setText("Preview unavailable")

    def _on_save(self):
        if not self._entry and not self._source_path:
            QMessageBox.warning(self, "No Photo", "Please select a photo first.")
            return
        self._result = {
            "image_path":     self._source_path or (getattr(self._entry, "image_path", "") if self._entry else ""),
            "caption":        self._caption_input.text().strip(),
            "progress_stage": self._stage_combo.currentData() or "",
        }
        self.accept()

    def get_values(self) -> dict:
        return self._result or {}


# ══════════════════════════════════════════════════════════════════════════════
#  Main UI
# ══════════════════════════════════════════════════════════════════════════════

# Section indices
_SEC_LISTS   = 0
_SEC_BUILD   = 1
_SEC_PAINTS  = 2
_SEC_GALLERY = 3
_SEC_STATS   = 4

# (Gallery card geometry lives above — _GALLERY_CARD_W/H/THUMB_H/GAP)

# Lists table columns
_LC_NAME   = 0
_LC_SYSTEM = 1
_LC_FACTION= 2
_LC_FORMAT = 3
_LC_PTS    = 4
_LC_UNITS  = 5

# Roster table columns
_RC_ROLE   = 0
_RC_NAME   = 1
_RC_QTY    = 2
_RC_PTS    = 3
_RC_TOTAL  = 4
_RC_WARGEAR= 5


class ArmyBuilderV2UI(QWidget):

    def __init__(self, service, context=None, parent=None):
        super().__init__(parent)
        self._svc             = service
        self._ctx             = context
        self._all_armies:     list[Army] = []
        self._filtered:       list[Army] = []
        self._pts_cache:      dict[int, float] = {}
        self._unit_cache:     dict[int, int]   = {}
        self._view_mode       = "table"   # "table" or "cards"
        self._sort_col        = _LC_NAME
        self._sort_desc       = False

        # Builder state
        self._current_army:   Optional[Army]           = None
        self._current_units:  list[ArmyUnit]           = []
        self._current_army_id: Optional[int]           = None

        # Paints state
        self._paint_entries:  list[dict] = []

        # Gallery state + repository
        self._gallery_entries:      list = []
        self._gallery_stage_filter: str  = ""    # "" = all stages
        self._gallery_repo = None
        try:
            db = self._ctx.services.get("db") if self._ctx else None
            if db:
                from .gallery_repository import GalleryRepository
                self._gallery_repo = GalleryRepository(db)
        except Exception as e:
            print(f"[ARMY V2 UI] gallery repo init: {e}")

        self._build()
        self._apply_theme()
        QTimer.singleShot(0, self.refresh)

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_filter_bar())

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_lists_page())   # 0  _SEC_LISTS
        self._stack.addWidget(self._build_builder_page()) # 1  _SEC_BUILD
        self._stack.addWidget(self._build_paints_page())  # 2  _SEC_PAINTS
        self._stack.addWidget(self._build_gallery_page()) # 3  _SEC_GALLERY
        self._stack.addWidget(self._build_stats_page())   # 4  _SEC_STATS
        root.addWidget(self._stack, stretch=1)

        root.addWidget(self._build_status_bar())

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("abHeader")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(22, 14, 16, 14)
        lay.setSpacing(12)

        # Title
        title_col = QVBoxLayout(); title_col.setSpacing(1); title_col.setContentsMargins(0,0,0,0)
        title = QLabel("Army Builder")
        title.setStyleSheet("font-size: 18px; font-weight: 700; letter-spacing: -0.3px;")
        title_col.addWidget(title)
        subtitle = QLabel("Army lists for 40K, AoS, Kill Team, D&D and more")
        subtitle.setObjectName("abSubtitle")
        subtitle.setStyleSheet("font-size: 11px;")
        title_col.addWidget(subtitle)
        lay.addLayout(title_col)
        lay.addStretch()

        # Section nav tabs
        nav_frame = QFrame()
        nav_frame.setObjectName("abNavGroup")
        nav_lay = QHBoxLayout(nav_frame)
        nav_lay.setContentsMargins(3, 3, 3, 3)
        nav_lay.setSpacing(2)

        self._nav_btns: dict[int, QPushButton] = {}
        for sec, label in [
            (_SEC_LISTS,   "My Lists"),
            (_SEC_BUILD,   "Builder"),
            (_SEC_PAINTS,  "Paints"),
            (_SEC_GALLERY, "Gallery"),
            (_SEC_STATS,   "Statistics"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("navTabActive" if sec == _SEC_LISTS else "navTab")
            btn.setFixedHeight(28)
            btn.setMinimumWidth(72)
            btn.clicked.connect(lambda _, s=sec: self._set_section(s))
            self._nav_btns[sec] = btn
            nav_lay.addWidget(btn)

        lay.addWidget(nav_frame)

        sep = QFrame(); sep.setFrameShape(QFrame.VLine); sep.setFixedWidth(1)
        lay.addWidget(sep)

        # View toggle (only meaningful on Lists section)
        toggle_frame = QFrame()
        toggle_frame.setObjectName("viewToggleGroup")
        toggle_lay = QHBoxLayout(toggle_frame)
        toggle_lay.setContentsMargins(3, 3, 3, 3)
        toggle_lay.setSpacing(2)

        self._card_view_btn = QPushButton("⊞")
        self._card_view_btn.setObjectName("viewToggle")
        self._card_view_btn.setFixedSize(30, 26)
        self._card_view_btn.setToolTip("Card view")
        self._card_view_btn.clicked.connect(lambda: self._set_view("cards"))
        toggle_lay.addWidget(self._card_view_btn)

        self._table_view_btn = QPushButton("☰")
        self._table_view_btn.setObjectName("viewToggleActive")
        self._table_view_btn.setFixedSize(30, 26)
        self._table_view_btn.setToolTip("Table view")
        self._table_view_btn.clicked.connect(lambda: self._set_view("table"))
        toggle_lay.addWidget(self._table_view_btn)

        lay.addWidget(toggle_frame)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.VLine); sep2.setFixedWidth(1)
        lay.addWidget(sep2)

        add_btn = QPushButton("＋  New Army")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._on_new_army)
        lay.addWidget(add_btn)

        return bar

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("abFilterBar")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        # Preset chips
        chip_row = QHBoxLayout(); chip_row.setSpacing(6); chip_row.setContentsMargins(0,0,0,0)
        self._preset_btns: dict[str, QPushButton] = {}
        for key, label in [("all","All"), ("over_limit","Over Limit"), ("no_units","Empty Lists")]:
            btn = QPushButton(label)
            btn.setObjectName("chipActive" if key == "all" else "chip")
            btn.setCheckable(True); btn.setChecked(key == "all")
            btn.clicked.connect(lambda _, k=key: self._apply_preset_chip(k))
            self._preset_btns[key] = btn
            chip_row.addWidget(btn)
        chip_row.addStretch()
        lay.addLayout(chip_row)

        # Search + filters
        fr = QHBoxLayout(); fr.setSpacing(8); fr.setContentsMargins(0,0,0,0)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search armies…")
        self._search_edit.setObjectName("searchInput")
        self._search_edit.setMinimumWidth(180)
        self._search_edit.textChanged.connect(self._apply_filters)
        fr.addWidget(self._search_edit, 2)

        self._system_filter = QComboBox()
        self._system_filter.addItem("All Systems")
        self._system_filter.currentIndexChanged.connect(self._apply_filters)
        fr.addWidget(self._system_filter, 2)

        self._faction_filter = QComboBox()
        self._faction_filter.addItem("All Factions")
        self._faction_filter.currentIndexChanged.connect(self._apply_filters)
        fr.addWidget(self._faction_filter, 2)

        lay.addLayout(fr)
        return bar

    # ── Lists page ─────────────────────────────────────────────────────────────

    def _build_lists_page(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Table view
        self._lists_table = QTableWidget()
        self._lists_table.setColumnCount(6)
        self._lists_table.setHorizontalHeaderLabels(
            ["Name", "Game System", "Faction", "Format", "Points", "Units"]
        )
        hdr = self._lists_table.horizontalHeader()
        hdr.setSectionResizeMode(_LC_NAME,    QHeaderView.Stretch)
        hdr.setSectionResizeMode(_LC_SYSTEM,  QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_LC_FACTION, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_LC_FORMAT,  QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_LC_PTS,     QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_LC_UNITS,   QHeaderView.Fixed)
        self._lists_table.setColumnWidth(_LC_UNITS, 60)
        hdr.setSectionsClickable(True)
        hdr.sectionClicked.connect(self._on_list_header_clicked)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(_LC_NAME, Qt.AscendingOrder)
        self._lists_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._lists_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._lists_table.setAlternatingRowColors(True)
        self._lists_table.verticalHeader().setVisible(False)
        self._lists_table.setShowGrid(False)
        self._lists_table.doubleClicked.connect(self._on_list_double_click)
        self._lists_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._lists_table.customContextMenuRequested.connect(self._on_list_context_menu)
        self._lists_table.keyPressEvent = self._list_table_key_press

        # Card scroll area
        self._cards_scroll = QScrollArea()
        self._cards_scroll.setWidgetResizable(True)
        self._cards_scroll.setFrameShape(QFrame.NoFrame)
        self._cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cards_scroll.setWidget(QWidget())

        # Stack: 0=table, 1=cards
        self._lists_view_stack = QStackedWidget()
        self._lists_view_stack.addWidget(self._lists_table)  # 0
        self._lists_view_stack.addWidget(self._cards_scroll) # 1
        lay.addWidget(self._lists_view_stack)
        return page

    # ── Builder page ───────────────────────────────────────────────────────────

    def _build_builder_page(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Army info bar
        self._builder_bar = QWidget()
        self._builder_bar.setObjectName("builderBar")
        blay = QHBoxLayout(self._builder_bar)
        blay.setContentsMargins(16, 10, 16, 10)
        blay.setSpacing(12)

        back_btn = QPushButton("← Lists")
        back_btn.setObjectName("secondaryBtn")
        back_btn.setFixedHeight(28)
        back_btn.clicked.connect(lambda: self._set_section(_SEC_LISTS))
        blay.addWidget(back_btn)

        self._bld_name_lbl = QLabel("—")
        self._bld_name_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        blay.addWidget(self._bld_name_lbl)

        self._bld_info_lbl = QLabel("")
        self._bld_info_lbl.setObjectName("abSubtitle")
        blay.addWidget(self._bld_info_lbl)

        blay.addStretch()

        edit_army_btn = QPushButton("✏  Edit Details")
        edit_army_btn.setObjectName("secondaryBtn")
        edit_army_btn.setFixedHeight(28)
        edit_army_btn.clicked.connect(self._on_edit_army_details)
        blay.addWidget(edit_army_btn)

        export_btn = QPushButton("⬇  Export")
        export_btn.setObjectName("secondaryBtn")
        export_btn.setFixedHeight(28)
        export_btn.clicked.connect(self._on_export)
        blay.addWidget(export_btn)

        lay.addWidget(self._builder_bar)

        # Points progress bar
        self._pts_bar_widget = QWidget()
        self._pts_bar_widget.setObjectName("ptsBarWidget")
        pb_lay = QHBoxLayout(self._pts_bar_widget)
        pb_lay.setContentsMargins(16, 6, 16, 8)
        pb_lay.setSpacing(10)

        self._pts_used_lbl = QLabel("0 pts")
        self._pts_used_lbl.setStyleSheet("font-size: 12px; font-weight: 700; min-width: 80px;")
        pb_lay.addWidget(self._pts_used_lbl)

        self._pts_bar = QProgressBar()
        self._pts_bar.setFixedHeight(6)
        self._pts_bar.setTextVisible(False)
        self._pts_bar.setRange(0, 100)
        pb_lay.addWidget(self._pts_bar, 1)

        self._pts_limit_lbl = QLabel("")
        self._pts_limit_lbl.setStyleSheet("font-size: 11px; min-width: 60px; text-align: right;")
        pb_lay.addWidget(self._pts_limit_lbl)

        lay.addWidget(self._pts_bar_widget)

        # Splitter: roster left | unit panel right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # Left: roster table
        roster_widget = QWidget()
        rl = QVBoxLayout(roster_widget)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # Roster toolbar
        rt_bar = QWidget()
        rt_bar.setObjectName("rosterToolbar")
        rt_lay = QHBoxLayout(rt_bar)
        rt_lay.setContentsMargins(12, 8, 12, 8)
        rt_lay.setSpacing(8)

        self._roster_search = QLineEdit()
        self._roster_search.setPlaceholderText("Filter units…")
        self._roster_search.setObjectName("searchInput")
        self._roster_search.textChanged.connect(self._render_roster)
        rt_lay.addWidget(self._roster_search, 1)

        self._role_filter_combo = QComboBox()
        self._role_filter_combo.addItem("All Roles")
        self._role_filter_combo.currentIndexChanged.connect(self._render_roster)
        rt_lay.addWidget(self._role_filter_combo, 1)

        add_unit_btn = QPushButton("＋  Add Unit")
        add_unit_btn.setObjectName("primaryBtn")
        add_unit_btn.setFixedHeight(28)
        add_unit_btn.clicked.connect(self._on_add_unit)
        rt_lay.addWidget(add_unit_btn)

        rl.addWidget(rt_bar)

        self._roster_table = QTableWidget()
        self._roster_table.setColumnCount(6)
        self._roster_table.setHorizontalHeaderLabels(
            ["Role", "Unit Name", "Qty", "Pts/model", "Total Pts", "Wargear"]
        )
        rhdr = self._roster_table.horizontalHeader()
        rhdr.setSectionResizeMode(_RC_ROLE,   QHeaderView.ResizeToContents)
        rhdr.setSectionResizeMode(_RC_NAME,   QHeaderView.Stretch)
        rhdr.setSectionResizeMode(_RC_QTY,    QHeaderView.Fixed)
        rhdr.setSectionResizeMode(_RC_PTS,    QHeaderView.Fixed)
        rhdr.setSectionResizeMode(_RC_TOTAL,  QHeaderView.Fixed)
        rhdr.setSectionResizeMode(_RC_WARGEAR,QHeaderView.ResizeToContents)
        self._roster_table.setColumnWidth(_RC_QTY,   48)
        self._roster_table.setColumnWidth(_RC_PTS,   80)
        self._roster_table.setColumnWidth(_RC_TOTAL, 80)
        self._roster_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._roster_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._roster_table.setAlternatingRowColors(True)
        self._roster_table.verticalHeader().setVisible(False)
        self._roster_table.setShowGrid(False)
        self._roster_table.doubleClicked.connect(self._on_roster_double_click)
        self._roster_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._roster_table.customContextMenuRequested.connect(self._on_roster_context_menu)
        self._roster_table.keyPressEvent = self._roster_key_press
        rl.addWidget(self._roster_table)

        splitter.addWidget(roster_widget)
        splitter.setSizes([700, 1])
        lay.addWidget(splitter, stretch=1)

        return page

    # ── Paints page ────────────────────────────────────────────────────────────

    def _build_paints_page(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Paints toolbar
        pt_bar = QWidget()
        pt_bar.setObjectName("abFilterBar")
        pt_lay = QHBoxLayout(pt_bar)
        pt_lay.setContentsMargins(16, 10, 16, 10)
        pt_lay.setSpacing(8)

        self._paints_army_lbl = QLabel("No army open")
        self._paints_army_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        pt_lay.addWidget(self._paints_army_lbl)

        pt_lay.addStretch()

        self._paints_search = QLineEdit()
        self._paints_search.setPlaceholderText("Filter paints…")
        self._paints_search.setObjectName("searchInput")
        self._paints_search.textChanged.connect(self._render_paints)
        pt_lay.addWidget(self._paints_search, 1)

        self._paints_source_filter = QComboBox()
        self._paints_source_filter.addItems(["All Sources", "Direct", "Via Model"])
        self._paints_source_filter.currentIndexChanged.connect(self._render_paints)
        pt_lay.addWidget(self._paints_source_filter)

        refresh_btn = QPushButton("↺  Refresh")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setFixedHeight(28)
        refresh_btn.clicked.connect(self._refresh_paints_tab)
        pt_lay.addWidget(refresh_btn)

        lay.addWidget(pt_bar)

        self._paints_table = QTableWidget()
        self._paints_table.setColumnCount(6)
        self._paints_table.setHorizontalHeaderLabels(
            ["", "Brand", "Paint Name", "Type", "Used By", "Source"]
        )
        phdr = self._paints_table.horizontalHeader()
        phdr.setSectionResizeMode(0, QHeaderView.Fixed)
        phdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        phdr.setSectionResizeMode(2, QHeaderView.Stretch)
        phdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        phdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        phdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._paints_table.setColumnWidth(0, 44)
        self._paints_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._paints_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._paints_table.setAlternatingRowColors(True)
        self._paints_table.verticalHeader().setVisible(False)
        self._paints_table.setShowGrid(False)
        lay.addWidget(self._paints_table)

        # Summary bar
        self._paints_summary_lbl = QLabel("")
        self._paints_summary_lbl.setObjectName("statusCount")
        self._paints_summary_lbl.setContentsMargins(16, 4, 16, 6)
        lay.addWidget(self._paints_summary_lbl)

        return page

    # ── Gallery page ───────────────────────────────────────────────────────────

    def _build_gallery_page(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Toolbar ───────────────────────────────────────────────────────
        gt_bar = QWidget()
        gt_bar.setObjectName("abFilterBar")
        gt_lay = QHBoxLayout(gt_bar)
        gt_lay.setContentsMargins(16, 10, 16, 10)
        gt_lay.setSpacing(10)

        self._gallery_army_lbl = QLabel("No army open")
        self._gallery_army_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        gt_lay.addWidget(self._gallery_army_lbl)

        self._gallery_count_lbl = QLabel("")
        self._gallery_count_lbl.setObjectName("abSubtitle")
        gt_lay.addWidget(self._gallery_count_lbl)

        gt_lay.addStretch()

        add_photos_btn = QPushButton("📸  Add Photo")
        add_photos_btn.setObjectName("primaryBtn")
        add_photos_btn.setFixedHeight(32)
        add_photos_btn.clicked.connect(self._on_add_photos)
        gt_lay.addWidget(add_photos_btn)

        lay.addWidget(gt_bar)

        # ── Stage filter chips ────────────────────────────────────────────
        chip_bar = QWidget()
        chip_bar.setObjectName("abFilterBar")
        chip_lay = QHBoxLayout(chip_bar)
        chip_lay.setContentsMargins(16, 6, 16, 6)
        chip_lay.setSpacing(6)

        self._gallery_chips: dict[str, QPushButton] = {}

        def _make_chip(label: str, stage_val: str):
            btn = QPushButton(label)
            btn.setObjectName("chipActive" if stage_val == "" else "chip")
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda: self._set_gallery_stage_filter(stage_val))
            self._gallery_chips[stage_val] = btn
            chip_lay.addWidget(btn)

        _make_chip("All", "")
        for s in _ArmyGalleryStage.ALL:
            _make_chip(_ArmyGalleryStage.LABELS[s], s)

        chip_lay.addStretch()
        lay.addWidget(chip_bar)

        # ── Scrollable card grid ──────────────────────────────────────────
        self._gallery_scroll = QScrollArea()
        self._gallery_scroll.setWidgetResizable(True)
        self._gallery_scroll.setFrameShape(QFrame.NoFrame)
        self._gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._gallery_scroll.setWidget(QWidget())
        lay.addWidget(self._gallery_scroll)

        return page

    def _set_gallery_stage_filter(self, stage: str):
        self._gallery_stage_filter = stage
        # Update chip active state
        for val, btn in self._gallery_chips.items():
            btn.setObjectName("chipActive" if val == stage else "chip")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._render_gallery()

    # ── Stats page ─────────────────────────────────────────────────────────────

    def _build_stats_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        lay   = QVBoxLayout(inner)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(20)

        self._stats_overview = QWidget()
        ov_lay = QHBoxLayout(self._stats_overview)
        ov_lay.setContentsMargins(0, 0, 0, 0)
        ov_lay.setSpacing(12)
        lay.addWidget(self._stats_overview)

        self._stats_system_box  = self._make_dist_box("By Game System")
        self._stats_faction_box = self._make_dist_box("By Faction")
        dist_row = QHBoxLayout(); dist_row.setSpacing(16)
        dist_row.addWidget(self._stats_system_box)
        dist_row.addWidget(self._stats_faction_box)
        lay.addLayout(dist_row)

        lay.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return page

    def _make_dist_box(self, title: str) -> QFrame:
        box = QFrame()
        box.setObjectName("statsBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        hdr = QLabel(title)
        hdr.setStyleSheet("font-size: 12px; font-weight: 700; letter-spacing: 0.3px;")
        lay.addWidget(hdr)
        content = QWidget()
        content.setLayout(QVBoxLayout())
        content.layout().setContentsMargins(0, 0, 0, 0)
        content.layout().setSpacing(6)
        lay.addWidget(content)
        box._content = content
        return box

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("abStatusBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 6, 20, 7)
        lay.setSpacing(0)
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("statusCount")
        lay.addWidget(self._status_lbl)
        lay.addStretch()
        return bar

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(self):
        try:
            self._all_armies = self._svc.get_all_armies()
            self._pts_cache  = {a.id: self._svc.get_points_total(a.id) for a in self._all_armies}
            self._unit_cache = {a.id: len(self._svc.get_units_for_army(a.id)) for a in self._all_armies}
            self._update_filter_combos()
            self._apply_filters()
            self._update_stats()
            # Refresh builder if open
            if self._current_army_id:
                self._load_army(self._current_army_id)
        except Exception as e:
            print(f"[ARMY V2 UI] refresh: {e}")

    def apply_preset(self, preset: str):
        if preset == "new":
            self._on_new_army()
        elif preset == "over_limit":
            self._apply_preset_chip("over_limit")
        else:
            self._set_section(_SEC_LISTS)

    def on_model_removed(self, model_id: int):
        if self._current_army_id:
            self._load_army(self._current_army_id)

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _set_section(self, sec: int):
        self._stack.setCurrentIndex(sec)
        for s, btn in self._nav_btns.items():
            btn.setObjectName("navTabActive" if s == sec else "navTab")
            btn.style().unpolish(btn); btn.style().polish(btn)
        # Show/hide filter bar (only for Lists)
        filter_bar = self.findChild(QWidget, "abFilterBar")
        # The filter bar is always visible — we just refresh on section change
        if sec == _SEC_LISTS:
            self._apply_filters()
        elif sec == _SEC_PAINTS and self._current_army_id:
            self._refresh_paints_tab()
        elif sec == _SEC_GALLERY:
            self._load_gallery()
        elif sec == _SEC_STATS:
            self._update_stats()

    def _set_view(self, mode: str):
        self._view_mode = mode
        self._lists_view_stack.setCurrentIndex(0 if mode == "table" else 1)
        self._card_view_btn.setObjectName("viewToggleActive" if mode == "cards" else "viewToggle")
        self._table_view_btn.setObjectName("viewToggleActive" if mode == "table" else "viewToggle")
        for btn in (self._card_view_btn, self._table_view_btn):
            btn.style().unpolish(btn); btn.style().polish(btn)
        if mode == "cards":
            self._render_cards()
        else:
            self._render_lists_table()

    # ── Filtering ──────────────────────────────────────────────────────────────

    def _update_filter_combos(self):
        cur_sys     = self._system_filter.currentText()
        cur_faction = self._faction_filter.currentText()

        self._system_filter.blockSignals(True)
        self._system_filter.clear()
        self._system_filter.addItem("All Systems")
        for s in sorted({a.game_system for a in self._all_armies if a.game_system}):
            self._system_filter.addItem(s)
        idx = self._system_filter.findText(cur_sys)
        self._system_filter.setCurrentIndex(max(0, idx))
        self._system_filter.blockSignals(False)

        self._faction_filter.blockSignals(True)
        self._faction_filter.clear()
        self._faction_filter.addItem("All Factions")
        for f in sorted({a.faction for a in self._all_armies if a.faction}):
            self._faction_filter.addItem(f)
        idx = self._faction_filter.findText(cur_faction)
        self._faction_filter.setCurrentIndex(max(0, idx))
        self._faction_filter.blockSignals(False)

    def _apply_preset_chip(self, key: str):
        for k, btn in self._preset_btns.items():
            active = (k == key)
            btn.setObjectName("chipActive" if active else "chip")
            btn.setChecked(active)
            btn.style().unpolish(btn); btn.style().polish(btn)
        self._apply_filters()

    def _apply_filters(self, *_):
        search  = self._search_edit.text().strip().lower()
        sys_val = self._system_filter.currentText()
        fac_val = self._faction_filter.currentText()

        # Determine active preset chip
        active_chip = next(
            (k for k, b in self._preset_btns.items() if b.isChecked()), "all"
        )

        filtered = self._all_armies
        if search:
            filtered = [
                a for a in filtered
                if search in a.name.lower()
                or search in a.game_system.lower()
                or search in a.faction.lower()
                or search in a.format.lower()
            ]
        if sys_val and sys_val != "All Systems":
            filtered = [a for a in filtered if a.game_system == sys_val]
        if fac_val and fac_val != "All Factions":
            filtered = [a for a in filtered if a.faction == fac_val]

        if active_chip == "over_limit":
            filtered = [
                a for a in filtered
                if (a.points_limit or 0) > 0
                and self._pts_cache.get(a.id, 0) > a.points_limit
            ]
        elif active_chip == "no_units":
            filtered = [a for a in filtered if self._unit_cache.get(a.id, 0) == 0]

        self._filtered = filtered
        self._render_lists_table()
        if self._view_mode == "cards":
            self._render_cards()
        self._update_status()

    # ── Render: lists table ────────────────────────────────────────────────────

    def _render_lists_table(self):
        sort_key_map = {
            _LC_NAME:    lambda a: (a.name or "").lower(),
            _LC_SYSTEM:  lambda a: (a.game_system or "").lower(),
            _LC_FACTION: lambda a: (a.faction or "").lower(),
            _LC_FORMAT:  lambda a: (a.format or "").lower(),
            _LC_PTS:     lambda a: self._pts_cache.get(a.id, 0),
            _LC_UNITS:   lambda a: self._unit_cache.get(a.id, 0),
        }
        key_fn = sort_key_map.get(self._sort_col, sort_key_map[_LC_NAME])
        armies = sorted(self._filtered, key=key_fn, reverse=self._sort_desc)

        self._lists_table.setRowCount(0)
        self._lists_table.setRowCount(len(armies))
        for row, army in enumerate(armies):
            self._lists_table.setRowHeight(row, 34)
            used  = self._pts_cache.get(army.id, 0)
            limit = army.points_limit or 0
            color = _pts_color(used, limit)

            name_item = QTableWidgetItem(army.name)
            name_item.setData(Qt.UserRole, army)
            self._lists_table.setItem(row, _LC_NAME, name_item)

            sys_item = QTableWidgetItem(army.game_system)
            sys_item.setData(Qt.UserRole, army)
            self._lists_table.setItem(row, _LC_SYSTEM, sys_item)

            fac_item = QTableWidgetItem(army.faction)
            fac_item.setData(Qt.UserRole, army)
            self._lists_table.setItem(row, _LC_FACTION, fac_item)

            fmt_item = QTableWidgetItem(army.format)
            fmt_item.setData(Qt.UserRole, army)
            self._lists_table.setItem(row, _LC_FORMAT, fmt_item)

            if limit > 0:
                pts_str = f"{_fmt_pts(used)} / {_fmt_pts(limit)} pts"
            elif used > 0:
                pts_str = f"{_fmt_pts(used)} pts"
            else:
                pts_str = "—"
            pts_item = QTableWidgetItem(pts_str)
            pts_item.setForeground(QColor(color))
            pts_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pts_item.setData(Qt.UserRole, army)
            self._lists_table.setItem(row, _LC_PTS, pts_item)

            cnt = self._unit_cache.get(army.id, 0)
            cnt_item = QTableWidgetItem(str(cnt))
            cnt_item.setTextAlignment(Qt.AlignCenter)
            cnt_item.setData(Qt.UserRole, army)
            self._lists_table.setItem(row, _LC_UNITS, cnt_item)

    def _on_list_header_clicked(self, col: int):
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col  = col
            self._sort_desc = False
        hdr = self._lists_table.horizontalHeader()
        hdr.setSortIndicator(col, Qt.DescendingOrder if self._sort_desc else Qt.AscendingOrder)
        self._render_lists_table()

    # ── Render: cards ──────────────────────────────────────────────────────────

    def _card_cols(self) -> int:
        vp_w = self._cards_scroll.viewport().width()
        if vp_w < _CARD_W:
            vp_w = max(_CARD_W, self.width() - 32)
        return max(1, (vp_w - _CARD_GAP) // (_CARD_W + _CARD_GAP))

    def _render_cards(self):
        from PySide6.QtWidgets import QGridLayout
        cols  = self._card_cols()
        inner = QWidget()
        grid  = QGridLayout(inner)
        grid.setContentsMargins(18, 14, 18, 18)
        grid.setSpacing(_CARD_GAP)
        for c in range(cols):
            grid.setColumnStretch(c, 0)
        grid.setColumnStretch(cols, 1)

        if not self._filtered:
            ph = QLabel("No armies found.\nAdjust your filters or create a new army.")
            ph.setAlignment(Qt.AlignCenter)
            ph.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.28); padding: 60px;")
            ph.setWordWrap(True)
            grid.addWidget(ph, 0, 0, 1, max(cols, 1))
        else:
            row = col = 0
            for army in self._filtered:
                card = _ArmyCard(
                    army,
                    self._pts_cache.get(army.id, 0),
                    self._unit_cache.get(army.id, 0),
                )
                card.open_requested.connect(lambda a: self._open_army(a))
                card.edit_requested.connect(self._on_edit_army)
                card.duplicate_requested.connect(self._on_duplicate_army)
                card.delete_requested.connect(self._on_delete_army)
                grid.addWidget(card, row, col, Qt.AlignTop)
                col += 1
                if col >= cols:
                    col = 0; row += 1
            if col != 0:
                row += 1
            grid.setRowStretch(row, 1)

        self._cards_scroll.setWidget(inner)

    # ── Army CRUD ──────────────────────────────────────────────────────────────

    def _on_new_army(self):
        dlg = _ArmyDialog(context=self._ctx, parent=self)
        self._apply_dialog_theme(dlg)
        if dlg.exec():
            try:
                data  = dlg.get_data()
                army  = self._svc.create_army(**data)
                if self._ctx:
                    self._ctx.event_bus.emit("army_created", army.to_dict())
                self.refresh()
                self._show_toast(f"✓  Created {army.name}")
                self._open_army(army)
            except (ValidationError, Exception) as e:
                self._show_toast(str(e), error=True)

    def _on_edit_army(self, army: Army):
        dlg = _ArmyDialog(army, context=self._ctx, parent=self)
        self._apply_dialog_theme(dlg)
        if dlg.exec():
            try:
                data = dlg.get_data()
                updated = self._svc.update_army(army.id, **data)
                if self._ctx:
                    self._ctx.event_bus.emit("army_updated", updated.to_dict())
                self.refresh()
                self._show_toast(f"✓  Updated {updated.name}")
            except Exception as e:
                self._show_toast(str(e), error=True)

    def _on_edit_army_details(self):
        if self._current_army:
            self._on_edit_army(self._current_army)

    def _on_duplicate_army(self, army: Army):
        try:
            new_army = self._svc.duplicate_army(army.id)
            if self._ctx:
                self._ctx.event_bus.emit("army_duplicated", new_army.to_dict())
            self.refresh()
            self._show_toast(f"✓  Duplicated as {new_army.name}")
        except Exception as e:
            self._show_toast(str(e), error=True)

    def _on_delete_army(self, army: Army):
        reply = QMessageBox.question(
            self, "Delete Army",
            f"Delete <b>{army.name}</b> and all its units?<br>This cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            try:
                self._svc.delete_army(army.id)
                if self._gallery_repo:
                    self._gallery_repo.delete_for_army(army.id)
                if self._ctx:
                    self._ctx.event_bus.emit("army_deleted", {"id": army.id})
                if self._current_army_id == army.id:
                    self._current_army    = None
                    self._current_army_id = None
                    self._current_units   = []
                    self._gallery_entries = []
                    self._set_section(_SEC_LISTS)
                self.refresh()
                self._show_toast(f"Deleted {army.name}")
            except Exception as e:
                self._show_toast(str(e), error=True)

    def _open_army(self, army: Army):
        self._load_army(army.id)
        self._set_section(_SEC_BUILD)

    def _load_army(self, army_id: int):
        try:
            army  = self._svc.get_army(army_id)
            units = self._svc.get_units_for_army(army_id)
            if not army:
                return
            self._current_army    = army
            self._current_army_id = army_id
            self._current_units   = units
            self._update_builder_header()
            self._update_pts_bar()
            self._rebuild_role_filter()
            self._render_roster()
            # Update gallery label count without full reload
            if self._gallery_repo:
                count = self._gallery_repo.count_for_army(army_id)
                self._gallery_army_lbl.setText(f"Gallery — {army.name}")
                self._gallery_count_lbl.setText(
                    f"  {count} photo{'s' if count != 1 else ''}"
                )
        except Exception as e:
            print(f"[ARMY V2 UI] load_army: {e}")

    # ── Builder ────────────────────────────────────────────────────────────────

    def _update_builder_header(self):
        if not self._current_army:
            return
        a = self._current_army
        self._bld_name_lbl.setText(a.name)
        self._bld_info_lbl.setText(f"{a.game_system}  ·  {a.faction}  ·  {a.format}")

    def _update_pts_bar(self):
        if not self._current_army:
            return
        units = self._current_units
        used  = sum(u.points_cost * u.quantity for u in units)
        limit = self._current_army.points_limit or 0
        color = _pts_color(used, limit)

        self._pts_used_lbl.setText(f"{_fmt_pts(used)} pts")
        self._pts_used_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {color}; min-width: 80px;"
        )

        if limit > 0:
            pct = min(int(used / limit * 100), 100)
            self._pts_bar.setValue(pct)
            over = used > limit
            bar_color = "#e05555" if over else ("#3dba6e" if pct >= 90 else "#4f9eff")
            self._pts_bar.setStyleSheet(f"""
                QProgressBar {{ background: #2a2a2a; border-radius: 3px; border: none; }}
                QProgressBar::chunk {{ background: {bar_color}; border-radius: 3px; }}
            """)
            over_str = f"  ⚠ +{_fmt_pts(used - limit)}" if over else ""
            self._pts_limit_lbl.setText(f"{_fmt_pts(limit)} pts{over_str}")
            self._pts_limit_lbl.setStyleSheet(
                f"font-size: 11px; min-width: 60px; color: {'#e05555' if over else '#686868'};"
            )
        else:
            self._pts_bar.setValue(0)
            self._pts_bar.setStyleSheet("""
                QProgressBar { background: #2a2a2a; border-radius: 3px; border: none; }
                QProgressBar::chunk { background: #4f9eff; border-radius: 3px; }
            """)
            self._pts_limit_lbl.setText("No limit")
            self._pts_limit_lbl.setStyleSheet("font-size: 11px; color: #686868;")

    def _rebuild_role_filter(self):
        if not self._current_army:
            return
        current = self._role_filter_combo.currentText()
        roles   = sorted({u.unit_role for u in self._current_units})
        self._role_filter_combo.blockSignals(True)
        self._role_filter_combo.clear()
        self._role_filter_combo.addItem("All Roles")
        self._role_filter_combo.addItems(roles)
        idx = self._role_filter_combo.findText(current)
        self._role_filter_combo.setCurrentIndex(max(0, idx))
        self._role_filter_combo.blockSignals(False)

    def _render_roster(self, *_):
        if not self._current_army:
            return
        search   = self._roster_search.text().strip().lower()
        role_val = self._role_filter_combo.currentText()

        units = self._current_units
        if search:
            units = [u for u in units
                     if search in u.unit_name.lower()
                     or search in u.unit_role.lower()
                     or search in (u.wargear_notes or "").lower()]
        if role_val and role_val != "All Roles":
            units = [u for u in units if u.unit_role == role_val]

        # Sort by role order then sort_order
        role_order = get_roles_for_system(self._current_army.game_system)
        def _sort_key(u: ArmyUnit):
            r_idx = role_order.index(u.unit_role) if u.unit_role in role_order else 999
            return (r_idx, u.sort_order, u.unit_name.lower())
        units.sort(key=_sort_key)

        self._roster_table.setRowCount(0)
        self._roster_table.setRowCount(len(units))
        for row, unit in enumerate(units):
            self._roster_table.setRowHeight(row, 32)

            role_item = QTableWidgetItem(unit.unit_role)
            role_item.setForeground(QColor("#4f9eff"))
            role_item.setData(Qt.UserRole, unit)
            self._roster_table.setItem(row, _RC_ROLE, role_item)

            name_item = QTableWidgetItem(unit.unit_name)
            name_item.setData(Qt.UserRole, unit)
            self._roster_table.setItem(row, _RC_NAME, name_item)

            qty_item = QTableWidgetItem(str(unit.quantity))
            qty_item.setTextAlignment(Qt.AlignCenter)
            qty_item.setData(Qt.UserRole, unit)
            self._roster_table.setItem(row, _RC_QTY, qty_item)

            pts_item = QTableWidgetItem(_fmt_pts(unit.points_cost))
            pts_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pts_item.setData(Qt.UserRole, unit)
            self._roster_table.setItem(row, _RC_PTS, pts_item)

            total_item = QTableWidgetItem(_fmt_pts(unit.total_points))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            total_item.setForeground(QColor("#3dba6e") if unit.total_points > 0 else QColor(_FG_LO))
            total_item.setData(Qt.UserRole, unit)
            self._roster_table.setItem(row, _RC_TOTAL, total_item)

            wg_item = QTableWidgetItem(unit.wargear_notes or "")
            wg_item.setForeground(QColor(_FG_LO))
            wg_item.setData(Qt.UserRole, unit)
            self._roster_table.setItem(row, _RC_WARGEAR, wg_item)

    # ── Unit CRUD ──────────────────────────────────────────────────────────────

    def _on_add_unit(self):
        if not self._current_army:
            self._show_toast("Open an army first.", error=True)
            return
        dlg = _UnitDialog(self._current_army, context=self._ctx, parent=self)
        self._apply_dialog_theme(dlg)
        if dlg.exec():
            try:
                data = dlg.get_data()
                sort_order = max((u.sort_order for u in self._current_units), default=-1) + 1
                unit = self._svc.add_unit(
                    army_id=self._current_army_id,
                    sort_order=sort_order,
                    **data,
                )
                self._load_army(self._current_army_id)
                self.refresh()
                self._show_toast(f"✓  Added {unit.unit_name}")
            except (ValidationError, Exception) as e:
                self._show_toast(str(e), error=True)

    def _on_edit_unit(self, unit: ArmyUnit):
        if not self._current_army:
            return
        dlg = _UnitDialog(self._current_army, unit=unit, context=self._ctx, parent=self)
        self._apply_dialog_theme(dlg)
        if dlg.exec():
            try:
                data = dlg.get_data()
                updated = self._svc.update_unit(
                    unit_id=unit.id,
                    sort_order=unit.sort_order,
                    **data,
                )
                self._load_army(self._current_army_id)
                self.refresh()
                self._show_toast(f"✓  Updated {updated.unit_name}")
            except (ValidationError, Exception) as e:
                self._show_toast(str(e), error=True)

    def _on_delete_unit(self, unit: ArmyUnit):
        reply = QMessageBox.question(
            self, "Remove Unit",
            f"Remove <b>{unit.unit_name}</b> from this list?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            try:
                self._svc.remove_unit(unit.id)
                self._load_army(self._current_army_id)
                self.refresh()
                self._show_toast(f"Removed {unit.unit_name}")
            except Exception as e:
                self._show_toast(str(e), error=True)

    def _on_duplicate_unit(self, unit: ArmyUnit):
        try:
            new_unit = self._svc.duplicate_unit(unit.id)
            self._load_army(self._current_army_id)
            self.refresh()
            self._show_toast(f"✓  Duplicated {new_unit.unit_name}")
        except Exception as e:
            self._show_toast(str(e), error=True)

    def _on_move_unit(self, unit: ArmyUnit, direction: int):
        """direction: -1 = up, +1 = down within role group."""
        try:
            units     = self._svc.get_units_for_army(self._current_army_id)
            same_role = sorted([u for u in units if u.unit_role == unit.unit_role],
                               key=lambda u: u.sort_order)
            idx = next((i for i, u in enumerate(same_role) if u.id == unit.id), None)
            if idx is None:
                return
            swap_idx = idx + direction
            if swap_idx < 0 or swap_idx >= len(same_role):
                return
            target = same_role[swap_idx]
            self._svc.update_unit(unit.id,  unit.unit_name,  unit.unit_role,  unit.points_cost,
                                  unit.quantity,  unit.wargear_notes,  unit.model_id,
                                  unit.linked_paint_ids, sort_order=target.sort_order)
            self._svc.update_unit(target.id, target.unit_name, target.unit_role, target.points_cost,
                                  target.quantity, target.wargear_notes, target.model_id,
                                  target.linked_paint_ids, sort_order=unit.sort_order)
            self._load_army(self._current_army_id)
        except Exception as e:
            self._show_toast(str(e), error=True)

    # ── Export ─────────────────────────────────────────────────────────────────

    def _on_export(self):
        if not self._current_army:
            self._show_toast("No army open to export.", error=True)
            return
        text = self._svc.export_as_text(self._current_army, self._current_units)
        dlg  = _ExportDialog(text, parent=self)
        self._apply_dialog_theme(dlg)
        dlg.exec()

    def _on_export_csv(self, army: Army):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Army List",
            os.path.join(os.path.expanduser("~"), f"army_{timestamp}.csv"),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            units = self._svc.get_units_for_army(army.id)
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Unit Name", "Role", "Pts/model", "Qty", "Total Pts", "Wargear"])
                for u in units:
                    w.writerow([u.unit_name, u.unit_role, u.points_cost,
                                u.quantity, u.total_points, u.wargear_notes or ""])
            self._show_toast(f"✓  Exported {army.name}")
        except Exception as e:
            self._show_toast(f"Export failed: {e}", error=True)

    # ── Paints tab ─────────────────────────────────────────────────────────────

    def _refresh_paints_tab(self):
        if not self._current_army_id:
            return
        try:
            army = self._svc.get_army(self._current_army_id)
            if not army:
                return
            model_svc = self._ctx.services.try_get("model_service") if self._ctx else None
            paint_svc = self._ctx.services.try_get("paint_service") if self._ctx else None

            raw = self._svc.get_army_paint_list(self._current_army_id, model_svc)
            enriched = []
            for entry in raw:
                paint = None
                if paint_svc:
                    try:
                        paint = paint_svc.get_paint(entry["paint_id"])
                    except Exception:
                        pass
                enriched.append({
                    "paint_id":   entry["paint_id"],
                    "paint":      paint,
                    "unit_names": entry["unit_names"],
                    "sources":    entry["sources"],
                })
            self._paint_entries = enriched
            self._paints_army_lbl.setText(f"Paints for: {army.name}")
            self._render_paints()
        except Exception as e:
            print(f"[ARMY V2 UI] refresh_paints_tab: {e}")

    def _render_paints(self, *_):
        search     = self._paints_search.text().strip().lower()
        src_filter = self._paints_source_filter.currentText()

        entries = self._paint_entries
        if search:
            entries = [
                e for e in entries
                if (e["paint"] and (
                    search in (e["paint"].name or "").lower()
                    or search in (e["paint"].brand or "").lower()
                )) or any(search in n.lower() for n in e["unit_names"])
            ]
        if src_filter == "Direct":
            entries = [e for e in entries if "direct" in e["sources"]]
        elif src_filter == "Via Model":
            entries = [e for e in entries if "model" in e["sources"]]

        self._paints_table.setRowCount(0)
        self._paints_table.setRowCount(len(entries))
        out_of_stock = low_stock = 0

        for row, entry in enumerate(entries):
            self._paints_table.setRowHeight(row, 30)
            paint = entry["paint"]

            # Colour swatch — bare QLabel sized to fill the cell
            swatch_lbl = QLabel()
            swatch_lbl.setFixedSize(22, 22)
            swatch_lbl.setAlignment(Qt.AlignCenter)
            if paint and paint.color and paint.color.startswith("#"):
                swatch_lbl.setStyleSheet(
                    f"background-color: {paint.color};"
                    " border-radius: 5px;"
                    " border: 1px solid rgba(255,255,255,0.20);"
                )
                swatch_lbl.setToolTip(paint.color)
            else:
                swatch_lbl.setStyleSheet(
                    "background: #2a2a2a; border-radius: 5px; border: 1px solid #3a3a3a;"
                )

            # Wrap in a transparent widget so the table centres it properly
            swatch_cell = QWidget()
            sc_lay = QHBoxLayout(swatch_cell)
            sc_lay.setContentsMargins(11, 4, 4, 4)
            sc_lay.setSpacing(0)
            sc_lay.addWidget(swatch_lbl)
            swatch_cell.setStyleSheet("background: transparent;")
            self._paints_table.setCellWidget(row, 0, swatch_cell)

            brand_item = QTableWidgetItem(paint.brand if paint else "—")
            brand_item.setData(Qt.UserRole, entry)
            self._paints_table.setItem(row, 1, brand_item)

            name_item = QTableWidgetItem(paint.name if paint else f"Paint #{entry['paint_id']}")
            name_item.setData(Qt.UserRole, entry)
            self._paints_table.setItem(row, 2, name_item)

            type_item = QTableWidgetItem(paint.paint_type if paint else "—")
            self._paints_table.setItem(row, 3, type_item)

            units_item = QTableWidgetItem(", ".join(entry["unit_names"]))
            units_item.setForeground(QColor(_FG_LO))
            self._paints_table.setItem(row, 4, units_item)

            sources = entry["sources"]
            src_str = " + ".join(
                ("Direct" if s == "direct" else "Via Model") for s in sorted(sources)
            )
            src_item = QTableWidgetItem(src_str)
            src_item.setForeground(QColor(
                "#4f9eff" if "direct" in sources and "model" not in sources
                else "#a855f7" if "model" in sources
                else _FG_LO
            ))
            self._paints_table.setItem(row, 5, src_item)

            if paint:
                if getattr(paint, "stock_level", None) == "Out of Stock":
                    out_of_stock += 1
                elif getattr(paint, "stock_level", None) == "Low":
                    low_stock += 1

        parts = [f"{len(entries)} paint{'s' if len(entries) != 1 else ''}"]
        if out_of_stock:
            parts.append(f"{out_of_stock} out of stock")
        if low_stock:
            parts.append(f"{low_stock} low")
        self._paints_summary_lbl.setText("  ·  ".join(parts))

    # ── Gallery ────────────────────────────────────────────────────────────────

    def _load_gallery(self):
        """Fetch entries from the repo and re-render the grid."""
        if not self._gallery_repo:
            self._gallery_entries = []
            self._gallery_army_lbl.setText("Gallery unavailable (no DB)")
            self._render_gallery()
            return

        if not self._current_army_id:
            self._gallery_entries = []
            self._gallery_army_lbl.setText("No army open")
            self._gallery_count_lbl.setText("")
            self._render_gallery()
            return

        try:
            army = self._svc.get_army(self._current_army_id)
            self._gallery_entries = self._gallery_repo.get_for_army(self._current_army_id)
            count = len(self._gallery_entries)
            self._gallery_army_lbl.setText(
                f"Gallery — {army.name}" if army else "Gallery"
            )
            self._gallery_count_lbl.setText(
                f"  {count} photo{'s' if count != 1 else ''}"
            )
        except Exception as e:
            print(f"[ARMY V2 UI] load_gallery: {e}")
            self._gallery_entries = []

        self._render_gallery()

    def _gallery_cols(self) -> int:
        vp_w = self._gallery_scroll.viewport().width()
        if vp_w < _GALLERY_CARD_W:
            vp_w = max(_GALLERY_CARD_W, self.width() - 32)
        return max(1, (vp_w - _GALLERY_CARD_GAP) // (_GALLERY_CARD_W + _GALLERY_CARD_GAP))

    def _render_gallery(self):
        # Filter by stage if set
        entries = self._gallery_entries
        if self._gallery_stage_filter:
            entries = [
                e for e in entries
                if (getattr(e, "progress_stage", "") or "") == self._gallery_stage_filter
            ]

        cols  = self._gallery_cols()
        inner = QWidget()
        grid  = QGridLayout(inner)
        grid.setContentsMargins(18, 14, 18, 18)
        grid.setSpacing(_GALLERY_CARD_GAP)
        for c in range(cols):
            grid.setColumnStretch(c, 0)
        grid.setColumnStretch(cols, 1)

        if not self._current_army_id:
            ph = QLabel("Open an army first, then add photos to its gallery.")
            ph.setAlignment(Qt.AlignCenter)
            ph.setWordWrap(True)
            ph.setStyleSheet(
                "font-size: 13px; color: rgba(255,255,255,0.28); padding: 60px;"
            )
            grid.addWidget(ph, 0, 0, 1, max(cols, 1))
        elif not entries:
            msg = (
                "No photos yet.\n\nClick  📸 Add Photo  to capture your minis, "
                "terrain, and work in progress."
                if not self._gallery_stage_filter else
                "No photos tagged for this stage yet."
            )
            ph = QLabel(msg)
            ph.setAlignment(Qt.AlignCenter)
            ph.setWordWrap(True)
            ph.setStyleSheet(
                "font-size: 13px; color: rgba(255,255,255,0.28); padding: 60px;"
            )
            grid.addWidget(ph, 0, 0, 1, max(cols, 1))
        else:
            row = col = 0
            for idx, entry in enumerate(entries):
                card = _ArmyGalleryCard(entry, idx)
                card.open_requested.connect(self._on_view_photo)
                card.edit_requested.connect(self._on_edit_caption)
                card.delete_requested.connect(self._on_delete_photo)
                card.stage_change_requested.connect(self._on_stage_change)
                grid.addWidget(card, row, col, Qt.AlignTop)
                col += 1
                if col >= cols:
                    col = 0
                    row += 1
            if col != 0:
                row += 1
            grid.setRowStretch(row, 1)

        self._gallery_scroll.setWidget(inner)

    def _on_view_photo(self, index: int):
        entries = self._gallery_entries
        if self._gallery_stage_filter:
            entries = [
                e for e in entries
                if (getattr(e, "progress_stage", "") or "") == self._gallery_stage_filter
            ]
        if not entries:
            return
        dlg = _ArmyPhotoLightbox(entries, index, parent=self)
        self._apply_dialog_theme(dlg)
        dlg.edit_requested.connect(self._on_edit_caption)
        dlg.delete_requested.connect(self._on_delete_photo)
        dlg.exec()

    def _on_add_photos(self):
        if not self._current_army_id:
            self._show_toast("Open an army first to add photos.", error=True)
            return
        if not self._gallery_repo:
            self._show_toast("Gallery unavailable.", error=True)
            return

        dlg = _ArmyAddPhotoDialog(parent=self)
        self._apply_dialog_theme(dlg)
        if dlg.exec():
            vals = dlg.get_values()
            path  = vals.get("image_path", "")
            if not path:
                return
            try:
                self._gallery_repo.add_image(
                    self._current_army_id,
                    path,
                    caption=vals.get("caption", ""),
                    progress_stage=vals.get("progress_stage", ""),
                )
                self._show_toast("✓  Photo added to gallery")
                self._load_gallery()
            except Exception as e:
                self._show_toast(f"Failed to add photo: {e}", error=True)

    def _on_delete_photo(self, entry):
        reply = QMessageBox.question(
            self, "Remove Photo",
            "Remove this photo from the gallery?\n"
            "(The original file on disk will not be deleted.)",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            try:
                self._gallery_repo.delete_image(entry.id)
                self._load_gallery()
                self._show_toast("Photo removed from gallery.")
            except Exception as e:
                self._show_toast(str(e), error=True)

    def _on_edit_caption(self, entry):
        dlg = _ArmyAddPhotoDialog(entry=entry, parent=self)
        self._apply_dialog_theme(dlg)
        if dlg.exec():
            vals = dlg.get_values()
            try:
                self._gallery_repo.update_entry(
                    entry.id,
                    caption=vals.get("caption", ""),
                    progress_stage=vals.get("progress_stage", ""),
                )
                self._load_gallery()
                self._show_toast("✓  Photo updated")
            except Exception as e:
                self._show_toast(str(e), error=True)

    def _on_stage_change(self, entry, new_stage: str):
        if not self._gallery_repo:
            return
        try:
            self._gallery_repo.update_stage(entry.id, new_stage)
            self._load_gallery()
        except Exception as e:
            self._show_toast(str(e), error=True)

    # ── Statistics ─────────────────────────────────────────────────────────────

    def _update_stats(self):
        try:
            stats = self._svc.get_statistics()

            # Clear and rebuild overview cards
            while self._stats_overview.layout().count():
                item = self._stats_overview.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for label, value, sub in [
                ("Total Lists",   str(stats.total_armies), f"{stats.total_armies} armies built"),
                ("Total Units",   str(stats.total_units),  "across all lists"),
                ("Avg Points",    _fmt_pts(stats.average_points), "per army list"),
                ("Largest List",  stats.largest_army_name[:18] if stats.largest_army_name else "—",
                 f"{_fmt_pts(stats.largest_army_points)} pts" if stats.largest_army_points else ""),
            ]:
                card = self._make_stat_card(label, value, sub)
                self._stats_overview.layout().addWidget(card)
            self._stats_overview.layout().addStretch()

            self._render_dist_box(self._stats_system_box, stats.game_system_distribution)
            self._render_dist_box(self._stats_faction_box, stats.faction_distribution)
        except Exception as e:
            print(f"[ARMY V2 UI] update_stats: {e}")

    def _make_stat_card(self, label: str, value: str, sub: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statsCard")
        lay  = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #4f9eff;")
        lay.addWidget(val_lbl)
        lbl_lbl = QLabel(label)
        lbl_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #f0f0f0;")
        lay.addWidget(lbl_lbl)
        sub_lbl = QLabel(sub)
        sub_lbl.setStyleSheet("font-size: 11px; color: #686868;")
        lay.addWidget(sub_lbl)
        return card

    def _render_dist_box(self, box: QFrame, dist: dict):
        content = box._content
        while content.layout().count():
            item = content.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not dist:
            content.layout().addWidget(QLabel("No data yet."))
            return
        total = sum(dist.values())
        for key, count in sorted(dist.items(), key=lambda x: -x[1])[:10]:
            row_w = QWidget()
            rlay  = QHBoxLayout(row_w)
            rlay.setContentsMargins(0, 0, 0, 0)
            rlay.setSpacing(8)

            pct_w = QProgressBar()
            pct_w.setFixedHeight(4)
            pct_w.setTextVisible(False)
            pct_w.setRange(0, total)
            pct_w.setValue(count)
            pct_w.setStyleSheet("""
                QProgressBar { background: #2a2a2a; border-radius: 2px; border: none; }
                QProgressBar::chunk { background: #4f9eff; border-radius: 2px; }
            """)

            name_lbl = QLabel(key[:28])
            name_lbl.setStyleSheet("font-size: 11px; min-width: 120px;")
            cnt_lbl  = QLabel(str(count))
            cnt_lbl.setStyleSheet("font-size: 11px; color: #686868; min-width: 24px;")
            cnt_lbl.setAlignment(Qt.AlignRight)

            rlay.addWidget(name_lbl)
            rlay.addWidget(pct_w, 1)
            rlay.addWidget(cnt_lbl)
            content.layout().addWidget(row_w)

    # ── Table event handlers ───────────────────────────────────────────────────

    def _on_list_double_click(self, index):
        item = self._lists_table.item(index.row(), _LC_NAME)
        if item:
            army = item.data(Qt.UserRole)
            if army:
                self._open_army(army)

    def _on_list_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        row = self._lists_table.rowAt(pos.y())
        if row < 0:
            return
        item = self._lists_table.item(row, _LC_NAME)
        if not item:
            return
        army = item.data(Qt.UserRole)
        if not army:
            return
        menu = QMenu(self)
        open_act  = menu.addAction("⚔  Open in Builder")
        menu.addSeparator()
        edit_act  = menu.addAction("✏  Edit Details")
        dup_act   = menu.addAction("⎘  Duplicate")
        exp_act   = menu.addAction("⬇  Export CSV")
        menu.addSeparator()
        del_act   = menu.addAction("🗑  Delete")
        act = menu.exec(self._lists_table.viewport().mapToGlobal(pos))
        if act == open_act:
            self._open_army(army)
        elif act == edit_act:
            self._on_edit_army(army)
        elif act == dup_act:
            self._on_duplicate_army(army)
        elif act == exp_act:
            self._on_export_csv(army)
        elif act == del_act:
            self._on_delete_army(army)

    def _list_table_key_press(self, event):
        key  = event.key()
        rows = self._lists_table.selectionModel().selectedRows()
        if not rows:
            QTableWidget.keyPressEvent(self._lists_table, event)
            return
        item = self._lists_table.item(rows[0].row(), _LC_NAME)
        army = item.data(Qt.UserRole) if item else None
        if army:
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._open_army(army); return
            elif key == Qt.Key_Delete:
                self._on_delete_army(army); return
        QTableWidget.keyPressEvent(self._lists_table, event)

    def _on_roster_double_click(self, index):
        item = self._roster_table.item(index.row(), _RC_NAME)
        if item:
            unit = item.data(Qt.UserRole)
            if unit:
                self._on_edit_unit(unit)

    def _on_roster_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        row = self._roster_table.rowAt(pos.y())
        if row < 0:
            return
        item = self._roster_table.item(row, _RC_NAME)
        if not item:
            return
        unit = item.data(Qt.UserRole)
        if not unit:
            return
        menu = QMenu(self)
        edit_act  = menu.addAction("✏  Edit")
        dup_act   = menu.addAction("⎘  Duplicate")
        menu.addSeparator()
        up_act    = menu.addAction("↑  Move Up")
        down_act  = menu.addAction("↓  Move Down")
        menu.addSeparator()
        del_act   = menu.addAction("🗑  Remove")
        act = menu.exec(self._roster_table.viewport().mapToGlobal(pos))
        if act == edit_act:
            self._on_edit_unit(unit)
        elif act == dup_act:
            self._on_duplicate_unit(unit)
        elif act == up_act:
            self._on_move_unit(unit, -1)
        elif act == down_act:
            self._on_move_unit(unit, 1)
        elif act == del_act:
            self._on_delete_unit(unit)

    def _roster_key_press(self, event):
        key  = event.key()
        rows = self._roster_table.selectionModel().selectedRows()
        if not rows:
            QTableWidget.keyPressEvent(self._roster_table, event)
            return
        item = self._roster_table.item(rows[0].row(), _RC_NAME)
        unit = item.data(Qt.UserRole) if item else None
        if unit:
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._on_edit_unit(unit); return
            elif key == Qt.Key_Delete:
                self._on_delete_unit(unit); return
        QTableWidget.keyPressEvent(self._roster_table, event)

    # ── Status ─────────────────────────────────────────────────────────────────

    def _update_status(self):
        total = len(self._filtered)
        all_n = len(self._all_armies)
        if total == all_n:
            self._status_lbl.setText(f"{total} arm{'ies' if total != 1 else 'y'}")
        else:
            self._status_lbl.setText(f"{total} of {all_n} armies")

    # ── Toast ──────────────────────────────────────────────────────────────────

    def _show_toast(self, message: str, *, error: bool = False,
                    action_label: str = "", action_cb=None):
        toast = _Toast(message, parent=self,
                       action_label=action_label, action_cb=action_cb)
        if error:
            toast.setStyleSheet("""
                QLabel#toastLabel {
                    background: rgba(200,60,60,0.94); color: #fff;
                    font-size: 12px; padding: 9px 20px;
                    border-radius: 8px; border: 1px solid rgba(255,255,255,0.12);
                }
            """)
        toast.show()
        self._position_toast(toast)

    def _position_toast(self, toast: _Toast):
        toast.adjustSize()
        x = (self.width()  - toast.width())  // 2
        y =  self.height() - toast.height()  - 36
        toast.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for child in self.findChildren(_Toast):
            self._position_toast(child)
        if self._view_mode == "cards":
            self._render_cards()
        if self._stack.currentIndex() == _SEC_GALLERY and self._gallery_entries:
            self._render_gallery()

    def showEvent(self, event):
        super().showEvent(event)
        if self._view_mode == "cards" and self._filtered:
            QTimer.singleShot(0, self._render_cards)

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
                QWidget {{ background: {bg}; color: {fg};
                           font-family: system-ui, -apple-system, sans-serif; }}

                /* ── Header ── */
                QWidget#abHeader {{ background: {bg2}; border-bottom: 1px solid {brd}; }}
                QLabel#abSubtitle {{ color: {fg2}; }}

                /* ── Section nav tabs ── */
                QFrame#abNavGroup {{
                    background: {inp}; border: 1px solid {brd}; border-radius: 7px;
                }}
                QPushButton#navTab {{
                    background: transparent; color: {fg2}; border: none;
                    border-radius: 5px; padding: 4px 12px; font-size: 12px;
                }}
                QPushButton#navTab:hover {{
                    color: {fg}; background: rgba(255,255,255,0.05);
                }}
                QPushButton#navTabActive {{
                    background: {acc}; color: #fff; border: none;
                    border-radius: 5px; padding: 4px 12px; font-size: 12px; font-weight: 600;
                }}

                /* ── View toggle ── */
                QFrame#viewToggleGroup {{
                    background: {inp}; border: 1px solid {brd}; border-radius: 7px;
                }}
                QPushButton#viewToggle {{
                    background: transparent; color: {fg2}; border: none;
                    border-radius: 5px; font-size: 14px;
                }}
                QPushButton#viewToggle:hover {{ color: {fg}; background: rgba(255,255,255,0.05); }}
                QPushButton#viewToggleActive {{
                    background: {acc}; color: #fff; border: none;
                    border-radius: 5px; font-size: 14px;
                }}

                /* ── Filter / toolbar bars ── */
                QWidget#abFilterBar {{ background: {bg}; border-bottom: 1px solid {brd}; }}
                QWidget#rosterToolbar {{ background: {bg}; border-bottom: 1px solid {brd}; }}
                QWidget#builderBar {{ background: {bg2}; border-bottom: 1px solid {brd}; }}
                QWidget#ptsBarWidget {{ background: {bg}; border-bottom: 1px solid {brd}; }}

                /* ── Chips ── */
                QPushButton#chip {{
                    background: transparent; color: {fg2}; border: 1px solid {brd};
                    border-radius: 13px; padding: 3px 13px; font-size: 12px;
                }}
                QPushButton#chip:hover {{ color: {fg}; border-color: rgba(255,255,255,0.22); }}
                QPushButton#chipActive {{
                    background: {acc}; color: #fff; border: none;
                    border-radius: 13px; padding: 3px 13px;
                    font-size: 12px; font-weight: 600;
                }}

                /* ── Primary / secondary buttons ── */
                QPushButton#primaryBtn {{
                    background: {acc}; color: #fff; border: none;
                    border-radius: 6px; padding: 6px 16px; font-weight: 600; font-size: 13px;
                }}
                QPushButton#primaryBtn:hover {{ border: 1px solid rgba(255,255,255,0.18); }}
                QPushButton#secondaryBtn {{
                    background: {inp}; color: {fg}; border: 1px solid {brd};
                    border-radius: 6px; padding: 5px 12px; font-size: 12px;
                }}
                QPushButton#secondaryBtn:hover {{ border-color: {acc}; color: {acc}; }}

                /* ── Inputs ── */
                QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
                    background: {inp}; color: {fg}; border: 1px solid {brd};
                    border-radius: 5px; padding: 5px 9px; font-size: 12px;
                    selection-background-color: {acc};
                }}
                QLineEdit:focus, QComboBox:focus,
                QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
                    border-color: {acc};
                }}
                QComboBox::drop-down {{ border: none; padding-right: 6px; }}
                QComboBox QAbstractItemView {{
                    background: {bg2}; color: {fg}; border: 1px solid {brd};
                    selection-background-color: {acc}; selection-color: #fff;
                }}

                /* ── Tables ── */
                QTableWidget {{
                    background: {bg}; alternate-background-color: {bg2};
                    color: {fg}; border: none; font-size: 12px; gridline-color: transparent;
                }}
                QTableWidget::item {{ padding: 0 4px; }}
                QTableWidget::item:selected {{ background: {acc}; color: #fff; }}
                QHeaderView::section {{
                    background: {bg2}; color: {fg2}; border: none;
                    border-bottom: 1px solid {brd}; padding: 6px 8px;
                    font-size: 11px; font-weight: 600; letter-spacing: 0.3px;
                    text-transform: uppercase;
                }}

                /* ── Stats cards ── */
                QFrame#statsCard {{
                    background: {bg2}; border: 1px solid {brd}; border-radius: 10px;
                }}
                QFrame#statsBox {{
                    background: {bg2}; border: 1px solid {brd}; border-radius: 10px;
                }}

                /* ── Status bar ── */
                QWidget#abStatusBar {{ background: {bg2}; border-top: 1px solid {brd}; }}
                QLabel#statusCount {{ font-size: 11px; color: {fg2}; }}

                /* ── Scrollbar ── */
                QScrollBar:vertical {{
                    background: transparent; width: 5px; margin: 0;
                }}
                QScrollBar::handle:vertical {{
                    background: {brd}; border-radius: 2px; min-height: 24px;
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

                /* ── Vertical separators ── */
                QFrame[frameShape="5"] {{ background: {brd}; border: none; max-width: 1px; }}

                /* ── Gallery cards ── */
                QFrame#galleryCard {{
                    background: {bg2}; border: 1px solid {brd};
                    border-radius: 10px;
                }}
                QFrame#galleryCard:hover {{
                    border-color: {acc};
                }}
                QLabel#galleryThumb {{
                    background: #111; border-radius: 7px;
                }}
                QLabel#galleryCardTitle {{
                    font-size: 11px; font-weight: 600; color: {fg};
                    padding: 0 2px;
                }}
                QLabel#galleryCardDate {{
                    font-size: 10px; color: {fg2}; padding: 0 2px;
                }}
                QWidget#galleryCardOverlay {{
                    background: rgba(0,0,0,0.62); border-radius: 7px;
                }}

                /* ── Lightbox ── */
                QDialog#lightboxDialog {{ background: {bg}; }}
                QWidget#lightboxHeader {{
                    background: {bg2}; border-bottom: 1px solid {brd};
                }}
                QLabel#lightboxCounter {{ font-size: 12px; color: {fg2}; }}
                QLabel#lightboxImage   {{ background: transparent; }}
                QWidget#lightboxInfo   {{
                    background: {bg2}; border-top: 1px solid {brd};
                }}
                QLabel#lightboxTitle {{ font-size: 14px; font-weight: 600; color: {fg}; }}
                QLabel#lightboxMeta  {{ font-size: 11px; color: {fg2}; }}
                QPushButton#lightboxNavBtn {{
                    background: transparent; color: {fg2}; border: none;
                    font-size: 28px; font-weight: 300;
                }}
                QPushButton#lightboxNavBtn:hover {{ color: {fg}; }}
                QPushButton#lightboxNavBtn:disabled {{ color: {brd}; }}
                QPushButton#ghostBtn {{
                    background: transparent; color: {fg2}; border: 1px solid {brd};
                    border-radius: 5px; padding: 3px 12px; font-size: 12px;
                }}
                QPushButton#ghostBtn:hover {{ color: {fg}; border-color: rgba(255,255,255,0.22); }}

                /* ── Gallery add photo dialog ── */
                QFrame#galleryImgPreviewFrame {{
                    background: {bg2}; border: 1px solid {brd}; border-radius: 8px;
                }}
                QLabel#galleryImgPreview {{
                    background: transparent; color: {fg2}; font-size: 12px;
                }}
                QLabel#metaLabel {{ color: {fg2}; font-size: 11px; }}

                /* ── Danger button ── */
                QPushButton#dangerBtn {{
                    background: rgba(224,85,85,0.15); color: #e05555;
                    border: 1px solid rgba(224,85,85,0.30); border-radius: 6px;
                    padding: 5px 12px; font-size: 12px;
                }}
                QPushButton#dangerBtn:hover {{
                    background: rgba(224,85,85,0.28); border-color: #e05555;
                }}
            """)
        except Exception as e:
            print(f"[ARMY V2 UI] theme error: {e}")

    def _apply_dialog_theme(self, dlg: QDialog):
        if not self._ctx:
            return
        try:
            tm = self._ctx.services.try_get("theme_manager")
            if not tm:
                return
            bg  = tm.token("bg_base"); bg2 = tm.token("bg_card")
            fg  = tm.token("text_hi"); fg2 = tm.token("text_lo")
            brd = tm.token("border");  acc = tm.token("accent")
            inp = tm.token("bg_input")
            dlg.setStyleSheet(f"""
                QDialog {{ background: {bg}; color: {fg}; }}
                QLabel  {{ background: transparent; color: {fg}; }}
                QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
                    background: {inp}; color: {fg}; border: 1px solid {brd};
                    border-radius: 5px; padding: 5px 8px; font-size: 12px;
                }}
                QLineEdit:focus, QComboBox:focus,
                QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{ border-color: {acc}; }}
                QComboBox::drop-down {{ border: none; padding-right: 6px; }}
                QComboBox QAbstractItemView {{
                    background: {bg2}; color: {fg}; border: 1px solid {brd};
                    selection-background-color: {acc}; selection-color: #fff;
                }}
                QPushButton {{
                    background: {inp}; color: {fg}; border: 1px solid {brd};
                    border-radius: 5px; padding: 6px 18px; font-size: 13px;
                }}
                QPushButton[default="true"], QPushButton:default {{
                    background: {acc}; color: #fff; border: none; font-weight: 600;
                }}
                QPushButton:hover {{ border-color: {acc}; color: {acc}; }}
                QPushButton[default="true"]:hover, QPushButton:default:hover {{
                    color: #fff; border: 1px solid rgba(255,255,255,0.18);
                }}
                QFrame[frameShape="4"] {{ background: {brd}; border: none; max-height: 1px; }}
                QListWidget {{
                    background: {inp}; color: {fg}; border: 1px solid {brd}; border-radius: 5px;
                }}
                QListWidget::item {{ padding: 4px 8px; }}
                QListWidget::item:hover {{ background: rgba(255,255,255,0.05); }}
            """)
        except Exception:
            pass

    # ── v1 compat shims ────────────────────────────────────────────────────────

    def _show_success(self, msg: str):
        self._show_toast(f"✓  {msg}")

    def _show_error(self, msg: str):
        self._show_toast(msg, error=True)

    def display_armies(self, armies, **_):
        self._all_armies = list(armies)
        self._apply_filters()

    def update_statistics(self, stats):
        pass  # handled via _update_stats()

    def refresh_builder_units(self, units, pts_limit=None):
        self._current_units = list(units)
        if pts_limit is not None and self._current_army:
            self._current_army.points_limit = pts_limit
        self._update_pts_bar()
        self._render_roster()

    def load_army_into_builder(self, army, units):
        self._open_army(army)

    def show_create_success(self, msg: str):
        self._show_toast(f"✓  {msg}")

    def show_create_error(self, msg: str):
        self._show_toast(msg, error=True)

    def show_unit_success(self, msg: str):
        self._show_toast(f"✓  {msg}")

    def show_unit_error(self, msg: str):
        self._show_toast(msg, error=True)

    def show_export_dialog(self, text: str):
        dlg = _ExportDialog(text, parent=self)
        self._apply_dialog_theme(dlg)
        dlg.exec()

    def refresh_paint_list(self, entries, army_name: str = ""):
        self._paint_entries = entries
        if army_name:
            self._paints_army_lbl.setText(f"Paints for: {army_name}")
        self._render_paints()

    def clear_new_army_form(self):
        pass  # handled inline in dialogs

    def populate_unit_form(self, unit):
        self._on_edit_unit(unit)

    @property
    def new_system_combo(self):
        """v1 compat: settings page tries to set the default system."""
        return self._system_filter
