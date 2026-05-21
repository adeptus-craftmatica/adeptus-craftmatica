"""
Tool Tracker 2.0 — Premium UI
Rich card grid with condition tracking, project linking, and inline quick-add.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

import csv
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QGridLayout, QSpinBox, QTextEdit, QMessageBox, QFileDialog,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QGroupBox, QFormLayout, QListWidget,
    QListWidgetItem, QSizePolicy, QToolButton, QScrollBar,
)

from plugins.tool_tracker.models import (
    Tool, ToolFilter, TOOL_TYPES, TOOL_CONDITIONS,
)
from plugins.tool_tracker.models import ValidationError

# ── Card geometry ──────────────────────────────────────────────────────────────
_CARD_MIN_W = 200
_CARD_H     = 196
_CARD_GAP   = 12

# ── Type icons ─────────────────────────────────────────────────────────────────
_TYPE_ICONS: dict[str, str] = {
    "Nippers":              "✂️",
    "Hobby Knife / Blade":  "🔪",
    "File":                 "📐",
    "Sandpaper":            "〰️",
    "Brush":                "🖌️",
    "Airbrush":             "💨",
    "Drill / Pin Vice":     "🔩",
    "Sculpting Tool":       "🗿",
    "Tweezers":             "🩺",
    "Plastic Glue":         "🧴",
    "Super Glue":           "🧪",
    "Green Stuff / Putty":  "🟢",
    "Cutting Mat":          "🟦",
    "Painting Handle":      "🖊️",
    "Spray Can":            "🫧",
    "Other":                "🔧",
}

# ── Condition colours ──────────────────────────────────────────────────────────
_CONDITION_FG: dict[str, str] = {
    "New":     "#ffffff",
    "Good":    "#ffffff",
    "Fair":    "#ffffff",
    "Worn":    "#ffffff",
    "Replace": "#ffffff",
}

_CONDITION_BG: dict[str, str] = {
    "New":     "#2e7d32",
    "Good":    "#388e3c",
    "Fair":    "#f57c00",
    "Worn":    "#d84315",
    "Replace": "#b71c1c",
}

# ── Condition cycle order ──────────────────────────────────────────────────────
_CONDITION_CYCLE = TOOL_CONDITIONS  # ["New", "Good", "Fair", "Worn", "Replace"]


def _type_icon(t: str) -> str:
    return _TYPE_ICONS.get(t, "🔧")

def _cond_fg(c: str) -> str:
    return _CONDITION_FG.get(c, "#ffffff")

def _cond_bg(c: str) -> str:
    return _CONDITION_BG.get(c, "#555555")

def _next_condition(current: str) -> str:
    try:
        idx = _CONDITION_CYCLE.index(current)
        return _CONDITION_CYCLE[(idx + 1) % len(_CONDITION_CYCLE)]
    except ValueError:
        return "Good"


# ══════════════════════════════════════════════════════════════════════════════
#  Tool Card
# ══════════════════════════════════════════════════════════════════════════════

class _ToolCard(QFrame):
    edit_requested      = Signal(object)           # Tool
    delete_requested    = Signal(object)           # Tool
    condition_cycled    = Signal(object, str)      # Tool, new_condition

    _BG        = "#1c1c1c"
    _BG_HOVER  = "#252525"
    _BORDER    = "#2e2e2e"
    _BORDER_HV = "#3a3a3a"
    _DIV       = "#2a2a2a"
    _FG_HI     = "#f0f0f0"
    _FG_LO     = "#686868"

    def __init__(self, tool: Tool, linked_projects: list | None = None, parent=None):
        super().__init__(parent)
        self._tool     = tool
        self._projects = linked_projects or []
        self._overlay: QWidget | None = None
        self._build()

    def _build(self):
        self.setObjectName("toolCard")
        self.setMinimumWidth(_CARD_MIN_W)
        self.setFixedHeight(_CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        self.setStyleSheet(f"""
            QFrame#toolCard {{
                background-color: {self._BG};
                border: 1px solid {self._BORDER};
                border-radius: 8px;
            }}
            QFrame#toolCard:hover {{
                background-color: {self._BG_HOVER};
                border-color: {self._BORDER_HV};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(0)

        # ── Header row: icon · name · condition chip ───────────────────────
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(8)

        icon_lbl = QLabel(_type_icon(self._tool.tool_type))
        icon_lbl.setStyleSheet(
            "font-size: 28px; background: transparent; border: none; padding: 0;"
        )
        icon_lbl.setFixedWidth(36)
        hdr.addWidget(icon_lbl)

        name_lbl = QLabel(self._tool.name)
        name_lbl.setStyleSheet(f"""
            font-size: 13px; font-weight: 700;
            color: {self._FG_HI};
            background: transparent; border: none;
        """)
        name_lbl.setWordWrap(True)
        name_lbl.setMaximumHeight(40)
        hdr.addWidget(name_lbl, 1)

        cond_chip = QLabel(self._tool.condition)
        cfg  = _cond_fg(self._tool.condition)
        cbg  = _cond_bg(self._tool.condition)
        cond_chip.setStyleSheet(f"""
            color: {cfg};
            background: {cbg};
            font-size: 9px;
            font-weight: bold;
            letter-spacing: 0.3px;
            padding: 2px 7px;
            border-radius: 5px;
            border: none;
        """)
        cond_chip.setAlignment(Qt.AlignCenter)
        hdr.addWidget(cond_chip)
        root.addLayout(hdr)

        root.addSpacing(8)

        # ── Meta row: brand · type · qty badge ────────────────────────────
        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(4)

        if self._tool.brand:
            brand_lbl = QLabel(self._tool.brand)
            brand_lbl.setStyleSheet(f"""
                font-size: 10px; color: {self._FG_LO};
                background: rgba(255,255,255,0.06);
                border: none; border-radius: 3px;
                padding: 1px 5px;
            """)
            meta.addWidget(brand_lbl)

        type_lbl = QLabel(self._tool.tool_type)
        type_lbl.setStyleSheet(f"""
            font-size: 10px; color: {self._FG_LO};
            background: transparent; border: none;
        """)
        meta.addWidget(type_lbl)

        meta.addStretch()

        if self._tool.quantity > 1:
            qty_lbl = QLabel(f"×{self._tool.quantity}")
            qty_lbl.setStyleSheet(f"""
                font-size: 11px; font-weight: 600;
                color: {self._FG_LO};
                background: transparent; border: none;
            """)
            meta.addWidget(qty_lbl)

        root.addLayout(meta)

        # ── Projects row ───────────────────────────────────────────────────
        if self._projects:
            root.addSpacing(6)
            proj_row = QHBoxLayout()
            proj_row.setContentsMargins(0, 0, 0, 0)
            proj_row.setSpacing(4)

            shown = self._projects[:2]
            extra = len(self._projects) - 2

            for proj in shown:
                name = getattr(proj, "name", str(proj))
                chip = QLabel(f"📁 {name}")
                chip.setStyleSheet(f"""
                    font-size: 9px; color: {self._FG_LO};
                    background: rgba(255,255,255,0.05);
                    border: none; border-radius: 3px;
                    padding: 1px 5px;
                """)
                proj_row.addWidget(chip)

            if extra > 0:
                more_lbl = QLabel(f"+{extra} more")
                more_lbl.setStyleSheet(f"""
                    font-size: 9px; color: {self._FG_LO};
                    background: transparent; border: none;
                """)
                proj_row.addWidget(more_lbl)

            proj_row.addStretch()
            root.addLayout(proj_row)

        root.addStretch()

        # ── Divider ────────────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background: {self._DIV}; border: none; max-height: 1px;")
        div.setFixedHeight(1)
        root.addWidget(div)

        root.addSpacing(4)

        # ── Action row (always visible, subtle) ────────────────────────────
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(2)
        action_row.addStretch()

        edit_btn  = QToolButton()
        edit_btn.setText("✏️")
        edit_btn.setToolTip("Edit tool")
        edit_btn.setStyleSheet(self._action_btn_style())
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._tool))

        cycle_btn = QToolButton()
        cycle_btn.setText("🔄")
        cycle_btn.setToolTip(f"Cycle condition (next: {_next_condition(self._tool.condition)})")
        cycle_btn.setStyleSheet(self._action_btn_style())
        cycle_btn.clicked.connect(self._on_cycle)

        del_btn = QToolButton()
        del_btn.setText("🗑️")
        del_btn.setToolTip("Delete tool")
        del_btn.setStyleSheet(self._action_btn_style())
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._tool))

        action_row.addWidget(edit_btn)
        action_row.addWidget(cycle_btn)
        action_row.addWidget(del_btn)
        root.addLayout(action_row)

    def _action_btn_style(self) -> str:
        return """
            QToolButton {
                background: transparent;
                border: none;
                font-size: 13px;
                padding: 2px 4px;
                border-radius: 4px;
                color: #555555;
            }
            QToolButton:hover {
                background: rgba(255,255,255,0.08);
                color: #cccccc;
            }
        """

    def _on_cycle(self):
        new_cond = _next_condition(self._tool.condition)
        self.condition_cycled.emit(self._tool, new_cond)

    def mouseDoubleClickEvent(self, event):
        self.edit_requested.emit(self._tool)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu       = QMenu(self)
        edit_act   = menu.addAction("✏  Edit")
        cycle_act  = menu.addAction(f"🔄  Cycle Condition → {_next_condition(self._tool.condition)}")
        menu.addSeparator()
        delete_act = menu.addAction("🗑  Delete")
        act        = menu.exec(event.globalPos())
        if act == edit_act:
            self.edit_requested.emit(self._tool)
        elif act == cycle_act:
            self._on_cycle()
        elif act == delete_act:
            self.delete_requested.emit(self._tool)


# ══════════════════════════════════════════════════════════════════════════════
#  Quick-Add Bar
# ══════════════════════════════════════════════════════════════════════════════

class _QuickAddBar(QWidget):
    tool_submitted = Signal(dict)

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

        # Row 1 — Name + Type + Condition
        r1 = QHBoxLayout()
        r1.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Tool name…")
        self._name_edit.setMinimumWidth(180)
        r1.addWidget(self._name_edit, 3)

        self._type_combo = QComboBox()
        self._type_combo.addItems(TOOL_TYPES)
        self._type_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        r1.addWidget(self._type_combo, 2)

        self._cond_combo = QComboBox()
        self._cond_combo.addItems(TOOL_CONDITIONS)
        self._cond_combo.setCurrentText("Good")
        self._cond_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        r1.addWidget(self._cond_combo, 1)

        cl.addLayout(r1)

        # Row 2 — Brand + Qty + Buttons
        r2 = QHBoxLayout()
        r2.setSpacing(8)

        self._brand_edit = QLineEdit()
        self._brand_edit.setPlaceholderText("Brand (optional)")
        r2.addWidget(self._brand_edit, 2)

        qty_lbl = QLabel("Qty")
        qty_lbl.setFixedWidth(26)
        r2.addWidget(qty_lbl)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 99)
        self._qty_spin.setValue(1)
        self._qty_spin.setFixedWidth(60)
        r2.addWidget(self._qty_spin)

        r2.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.collapse)
        r2.addWidget(cancel_btn)

        self._add_btn = QPushButton("Add Tool")
        self._add_btn.setObjectName("primaryBtn")
        self._add_btn.setFixedWidth(110)
        self._add_btn.clicked.connect(self._on_submit)
        r2.addWidget(self._add_btn)

        cl.addLayout(r2)
        lay.addWidget(self._card)

        self._name_edit.returnPressed.connect(self._on_submit)

    def expand(self):
        self._expanded = True
        self.setVisible(True)
        self._name_edit.clear()
        self._brand_edit.clear()
        self._qty_spin.setValue(1)
        self._type_combo.setCurrentIndex(0)
        self._cond_combo.setCurrentText("Good")
        QTimer.singleShot(50, self._name_edit.setFocus)

    def collapse(self):
        self._expanded = False
        self.setVisible(False)

    def is_expanded(self) -> bool:
        return self._expanded

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.collapse()
        else:
            super().keyPressEvent(event)

    def _on_submit(self):
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setFocus()
            self._name_edit.setStyleSheet("border: 1px solid #e05555;")
            return
        self._name_edit.setStyleSheet("")
        self.tool_submitted.emit({
            "name":      name,
            "tool_type": self._type_combo.currentText(),
            "brand":     self._brand_edit.text().strip(),
            "condition": self._cond_combo.currentText(),
            "quantity":  self._qty_spin.value(),
            "notes":     None,
        })
        self.collapse()


# ══════════════════════════════════════════════════════════════════════════════
#  Project Picker Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _ProjectPickerDialog(QDialog):
    def __init__(self, tool_name: str, already_linked_ids: list[int],
                 project_service, parent=None):
        super().__init__(parent)
        self._proj_svc    = project_service
        self._linked_ids  = set(already_linked_ids)
        self.setWindowTitle(f"Link '{tool_name}' to Projects")
        self.setMinimumSize(400, 360)
        self.setModal(True)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        title = QLabel("Select Projects to Link")
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        lay.addWidget(title)

        if self._proj_svc is None:
            info = QLabel("Projects plugin not installed.")
            info.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px;")
            lay.addWidget(info)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            lay.addWidget(close_btn, alignment=Qt.AlignRight)
            return

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter projects…")
        self._filter_edit.textChanged.connect(self._apply_filter)
        lay.addWidget(self._filter_edit)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.NoSelection)
        lay.addWidget(self._list, stretch=1)

        self._load_projects()

        btns = QDialogButtonBox()
        link_btn   = btns.addButton("Link Selected", QDialogButtonBox.AcceptRole)
        cancel_btn = btns.addButton("Cancel",        QDialogButtonBox.RejectRole)
        link_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        lay.addWidget(btns)

    def _load_projects(self):
        self._all_projects = []
        try:
            self._all_projects = self._proj_svc.get_all_projects()
        except Exception as e:
            log.warning(f"[TOOL TRACKER V2] Could not load projects: {e}")
        self._populate(self._all_projects)

    def _populate(self, projects):
        self._list.clear()
        for proj in projects:
            item = QListWidgetItem(f"📁  {proj.name}")
            item.setData(Qt.UserRole, proj.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if proj.id in self._linked_ids else Qt.Unchecked
            )
            self._list.addItem(item)

    def _apply_filter(self, text: str):
        q = text.strip().lower()
        filtered = [
            p for p in self._all_projects
            if q in p.name.lower()
        ] if q else self._all_projects
        self._populate(filtered)

    def get_selected_ids(self) -> list[int]:
        ids = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.checkState() == Qt.Checked:
                ids.append(item.data(Qt.UserRole))
        return ids


# ══════════════════════════════════════════════════════════════════════════════
#  Edit Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _EditDialog(QDialog):
    def __init__(self, tool: Optional[Tool] = None, context=None, parent=None):
        super().__init__(parent)
        self._tool           = tool
        self._context        = context
        self._linked_proj_ids: list[int]   = []
        self._orig_proj_ids:   list[int]   = []
        self._proj_svc       = None
        self._proj_objects:  dict[int, object] = {}

        # Try to get project_service
        if context:
            try:
                self._proj_svc = context.services.try_get("project_service")
            except Exception:
                pass

        title_str = f"Edit Tool — {tool.name}" if tool else "Add Tool"
        self.setWindowTitle(title_str)
        self.setMinimumSize(540, 480)
        self.setModal(True)
        self._build()
        if tool:
            self._populate(tool)
            self._load_linked_projects()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(14)

        # Title
        title = QLabel(
            f"Edit Tool — {self._tool.name}" if self._tool else "Add Tool"
        )
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(title)

        self._err_lbl = QLabel()
        self._err_lbl.setStyleSheet("color: #e05555; font-size: 11px;")
        self._err_lbl.setVisible(False)
        lay.addWidget(self._err_lbl)

        # ── Tool Details ───────────────────────────────────────────────────
        details_box = QGroupBox("Tool Details")
        form        = QFormLayout(details_box)
        form.setSpacing(10)
        form.setContentsMargins(14, 16, 14, 14)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Required")
        form.addRow("Name *", self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItems(TOOL_TYPES)
        form.addRow("Type *", self._type_combo)

        self._brand_edit = QLineEdit()
        self._brand_edit.setPlaceholderText("e.g. Citadel, Army Painter, Tamiya")
        form.addRow("Brand", self._brand_edit)

        self._cond_combo = QComboBox()
        for cond in TOOL_CONDITIONS:
            self._cond_combo.addItem(cond)
        form.addRow("Condition", self._cond_combo)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 99)
        self._qty_spin.setValue(1)
        form.addRow("Quantity", self._qty_spin)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Any notes about this tool…")
        self._notes_edit.setFixedHeight(68)
        form.addRow("Notes", self._notes_edit)

        lay.addWidget(details_box)

        # ── Linked Projects ────────────────────────────────────────────────
        if self._proj_svc is not None:
            self._proj_box = QGroupBox("Linked Projects")
            proj_lay       = QVBoxLayout(self._proj_box)
            proj_lay.setContentsMargins(14, 14, 14, 14)
            proj_lay.setSpacing(8)

            self._proj_chips_row = QHBoxLayout()
            self._proj_chips_row.setSpacing(6)
            self._proj_chips_row.setContentsMargins(0, 0, 0, 0)

            self._no_proj_lbl = QLabel("No projects linked")
            self._no_proj_lbl.setStyleSheet(
                "font-size: 11px; color: rgba(255,255,255,0.30);"
            )
            self._proj_chips_row.addWidget(self._no_proj_lbl)
            self._proj_chips_row.addStretch()

            proj_lay.addLayout(self._proj_chips_row)

            link_btn = QPushButton("+ Link Project")
            link_btn.setObjectName("secondaryBtn")
            link_btn.setFixedWidth(130)
            link_btn.clicked.connect(self._open_project_picker)
            proj_lay.addWidget(link_btn, alignment=Qt.AlignLeft)

            lay.addWidget(self._proj_box)

        # ── Buttons ────────────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        lay.addWidget(div)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _populate(self, t: Tool):
        self._name_edit.setText(t.name)
        idx = self._type_combo.findText(t.tool_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._brand_edit.setText(t.brand or "")
        cidx = self._cond_combo.findText(t.condition)
        if cidx >= 0:
            self._cond_combo.setCurrentIndex(cidx)
        self._qty_spin.setValue(t.quantity)
        self._notes_edit.setPlainText(t.notes or "")

    def _load_linked_projects(self):
        if not self._proj_svc or not self._tool or self._tool.id is None:
            return
        try:
            projects = self._proj_svc.get_projects_for_entity("tool", self._tool.id)
            self._linked_proj_ids = [p.id for p in projects]
            self._orig_proj_ids   = list(self._linked_proj_ids)
            for p in projects:
                self._proj_objects[p.id] = p
            self._refresh_project_chips()
        except Exception as e:
            log.warning(f"[TOOL TRACKER V2] Could not load linked projects: {e}")

    def _refresh_project_chips(self):
        if not hasattr(self, "_proj_chips_row"):
            return

        # Clear existing chips (keep the no_proj_lbl)
        while self._proj_chips_row.count():
            item = self._proj_chips_row.takeAt(0)
            if item.widget() and item.widget() is not self._no_proj_lbl:
                item.widget().deleteLater()
            elif item.widget():
                item.widget().setParent(None)

        if not self._linked_proj_ids:
            self._proj_chips_row.addWidget(self._no_proj_lbl)
            self._no_proj_lbl.setVisible(True)
            self._proj_chips_row.addStretch()
            return

        self._no_proj_lbl.setVisible(False)
        for pid in self._linked_proj_ids:
            proj = self._proj_objects.get(pid)
            pname = getattr(proj, "name", str(pid)) if proj else str(pid)
            chip  = self._make_project_chip(pid, pname)
            self._proj_chips_row.addWidget(chip)
        self._proj_chips_row.addStretch()

    def _make_project_chip(self, proj_id: int, name: str) -> QWidget:
        chip = QFrame()
        chip.setStyleSheet("""
            QFrame {
                background: rgba(79,158,255,0.12);
                border: 1px solid rgba(79,158,255,0.30);
                border-radius: 4px;
            }
        """)
        row = QHBoxLayout(chip)
        row.setContentsMargins(6, 3, 4, 3)
        row.setSpacing(4)

        lbl = QLabel(f"📁 {name}")
        lbl.setStyleSheet("font-size: 11px; color: #4f9eff; background: transparent; border: none;")
        row.addWidget(lbl)

        x_btn = QToolButton()
        x_btn.setText("×")
        x_btn.setFixedSize(14, 14)
        x_btn.setStyleSheet("""
            QToolButton { background: transparent; border: none; color: #888; font-size: 12px; }
            QToolButton:hover { color: #e05555; }
        """)
        x_btn.clicked.connect(lambda _, pid=proj_id: self._unlink_project(pid))
        row.addWidget(x_btn)
        return chip

    def _unlink_project(self, proj_id: int):
        if proj_id in self._linked_proj_ids:
            self._linked_proj_ids.remove(proj_id)
            self._refresh_project_chips()

    def _open_project_picker(self):
        dlg = _ProjectPickerDialog(
            self._tool.name if self._tool else "New Tool",
            self._linked_proj_ids,
            self._proj_svc,
            parent=self,
        )
        _apply_basic_dialog_theme(dlg)
        if dlg.exec():
            selected = dlg.get_selected_ids()
            # Load objects for new ids we don't have yet
            for pid in selected:
                if pid not in self._proj_objects:
                    try:
                        projs = self._proj_svc.get_all_projects()
                        for p in projs:
                            self._proj_objects[p.id] = p
                    except Exception as e:
                        log.warning(f"[TOOL TRACKER V2] Project lookup error: {e}")
            self._linked_proj_ids = selected
            self._refresh_project_chips()

    def _validate_and_accept(self):
        name = self._name_edit.text().strip()
        if not name:
            self._err_lbl.setText("Tool name is required.")
            self._err_lbl.setVisible(True)
            self._name_edit.setFocus()
            return
        if not self._type_combo.currentText().strip():
            self._err_lbl.setText("Tool type is required.")
            self._err_lbl.setVisible(True)
            return
        self._err_lbl.setVisible(False)
        self.accept()

    def get_data(self) -> dict:
        orig_set    = set(self._orig_proj_ids)
        current_set = set(self._linked_proj_ids)

        linked_new   = list(current_set - orig_set)
        unlinked_old = list(orig_set - current_set)

        return {
            "name":               self._name_edit.text().strip(),
            "tool_type":          self._type_combo.currentText(),
            "brand":              self._brand_edit.text().strip(),
            "condition":          self._cond_combo.currentText(),
            "quantity":           self._qty_spin.value(),
            "notes":              self._notes_edit.toPlainText().strip() or None,
            "linked_project_ids": linked_new,
            "unlinked_project_ids": unlinked_old,
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
#  Shared theme helper (module-level, not a class method)
# ══════════════════════════════════════════════════════════════════════════════

def _apply_basic_dialog_theme(dlg: QDialog):
    dlg.setStyleSheet("""
        QDialog { background: #1a1a1a; color: #f0f0f0; }
        QLabel  { background: transparent; color: #f0f0f0; }
        QLineEdit, QComboBox, QSpinBox, QTextEdit {
            background: #242424; color: #f0f0f0;
            border: 1px solid #333; border-radius: 5px;
            padding: 5px 8px; font-size: 12px;
        }
        QListWidget {
            background: #1e1e1e; color: #f0f0f0;
            border: 1px solid #333; border-radius: 5px;
        }
        QPushButton {
            background: #2a2a2a; color: #f0f0f0;
            border: 1px solid #3a3a3a; border-radius: 5px;
            padding: 6px 18px; font-size: 13px;
        }
        QPushButton:hover { border-color: #4f9eff; color: #4f9eff; }
    """)


# ══════════════════════════════════════════════════════════════════════════════
#  Main UI widget
# ══════════════════════════════════════════════════════════════════════════════

class ToolTrackerV2UI(QWidget):
    # Table column indices
    _COL_ICON      = 0
    _COL_NAME      = 1
    _COL_BRAND     = 2
    _COL_TYPE      = 3
    _COL_CONDITION = 4
    _COL_QTY       = 5
    _COL_PROJECTS  = 6
    _COL_NOTES     = 7

    def __init__(self, service, context=None, parent=None):
        super().__init__(parent)
        self._svc             = service
        self._ctx             = context
        self._all_tools:      list[Tool] = []
        self._filtered:       list[Tool] = []
        self._view_mode       = "table"
        self._undo_tool:      Optional[Tool] = None
        self._sort_col        = self._COL_NAME
        self._sort_desc       = False
        self._active_preset   = "all"
        # Maps tool_id -> list of project objects
        self._tool_projects:  dict[int, list] = {}

        # Try to get the project service
        self._proj_svc = None
        if context:
            try:
                self._proj_svc = context.services.try_get("project_service")
            except Exception:
                pass

        self._build()
        self._apply_theme()

        # Subscribe to theme changes
        if context:
            try:
                context.event_bus.subscribe("theme_changed", self._on_theme_changed)
            except Exception:
                pass

        QTimer.singleShot(0, self.refresh)

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        self._quick_add = _QuickAddBar()
        self._quick_add.tool_submitted.connect(self._on_add)
        root.addWidget(self._quick_add)

        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_status_bar())

        self._stack = QStackedWidget()
        self._cards_page = self._build_cards_page()
        self._table_page = self._build_table_page()
        self._stack.addWidget(self._cards_page)
        self._stack.addWidget(self._table_page)
        root.addWidget(self._stack, stretch=1)

        # Start in table view
        self._stack.setCurrentIndex(1)

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("toolHeader")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(22, 14, 16, 14)
        lay.setSpacing(12)

        # Title block
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title_col.setContentsMargins(0, 0, 0, 0)

        title = QLabel("🔧 Tool Tracker 2.0")
        title.setStyleSheet("font-size: 18px; font-weight: 700; letter-spacing: -0.3px;")
        title_col.addWidget(title)

        subtitle = QLabel("Your Hobby Toolkit")
        subtitle.setObjectName("toolSubtitle")
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

        add_btn = QPushButton("＋  Add Tool")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._handle_quick_create)
        lay.addWidget(add_btn)

        return bar

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("toolFilterBar")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 8)
        lay.setSpacing(8)

        # Preset chips
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        chip_row.setContentsMargins(0, 0, 0, 0)
        self._preset_btns: dict[str, QPushButton] = {}
        presets = [
            ("all",           "All"),
            ("needs_replacing", "Needs Replacing"),
            ("worn",          "Worn"),
            ("brushes",       "Brushes"),
            ("cutting",       "Cutting Tools"),
            ("adhesives",     "Adhesives"),
        ]
        for key, label in presets:
            btn = QPushButton(label)
            btn.setObjectName("chipActive" if key == "all" else "chip")
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda _, k=key: self._apply_preset_chip(k))
            self._preset_btns[key] = btn
            chip_row.addWidget(btn)
        chip_row.addStretch()
        lay.addLayout(chip_row)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.setContentsMargins(0, 0, 0, 0)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍  Search…")
        self._search_edit.setObjectName("searchInput")
        self._search_edit.setMinimumWidth(180)
        self._search_edit.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._search_edit, 2)

        self._type_filter = QComboBox()
        self._type_filter.addItem("All Types")
        self._type_filter.addItems(TOOL_TYPES)
        self._type_filter.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._type_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._type_filter, 2)

        self._brand_filter = QComboBox()
        self._brand_filter.addItem("All Brands")
        self._brand_filter.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._brand_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._brand_filter, 1)

        self._cond_filter = QComboBox()
        self._cond_filter.addItem("All Conditions")
        self._cond_filter.addItems(TOOL_CONDITIONS)
        self._cond_filter.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._cond_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._cond_filter, 1)

        self._sort_combo = QComboBox()
        self._sort_combo.addItems([
            "Name A–Z", "Type", "Brand", "Condition", "Qty ↑", "Qty ↓",
        ])
        self._sort_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._sort_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._sort_combo, 1)

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
        if vp_w < _CARD_MIN_W:
            vp_w = max(_CARD_MIN_W, self.width() - 32)
        return max(1, (vp_w - _CARD_GAP) // (_CARD_MIN_W + _CARD_GAP))

    def _build_table_page(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "", "Name", "Brand", "Type", "Condition", "Qty", "Projects", "Notes",
        ])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(self._COL_ICON,      QHeaderView.Fixed)
        hdr.setSectionResizeMode(self._COL_NAME,      QHeaderView.Stretch)
        hdr.setSectionResizeMode(self._COL_BRAND,     QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_TYPE,      QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_CONDITION, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_QTY,       QHeaderView.Fixed)
        hdr.setSectionResizeMode(self._COL_PROJECTS,  QHeaderView.Fixed)
        hdr.setSectionResizeMode(self._COL_NOTES,     QHeaderView.Fixed)
        self._table.setColumnWidth(self._COL_ICON,     36)
        self._table.setColumnWidth(self._COL_QTY,      52)
        self._table.setColumnWidth(self._COL_PROJECTS, 70)
        self._table.setColumnWidth(self._COL_NOTES,    52)

        hdr.setSectionsClickable(True)
        hdr.sectionClicked.connect(self._on_header_clicked)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(self._COL_NAME, Qt.AscendingOrder)
        hdr.setTextElideMode(Qt.ElideNone)

        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setIconSize(QSize(20, 20))
        self._table.doubleClicked.connect(self._on_table_double_click)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table.keyPressEvent = self._table_key_press

        lay.addWidget(self._table)
        return page

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("toolStatusBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 6, 20, 7)
        lay.setSpacing(8)

        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("statusCount")
        lay.addWidget(self._status_lbl)

        lay.addStretch()

        self._attn_lbl = QLabel()
        self._attn_lbl.setObjectName("attnLabel")
        self._attn_lbl.setVisible(False)
        lay.addWidget(self._attn_lbl)

        return bar

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(self):
        try:
            self._all_tools = self._svc.get_all_tools()
            self._update_brand_filter()
            self._apply_filters()
        except Exception as e:
            log.error(f"[TOOL TRACKER V2 UI] refresh: {e}")

    def apply_preset(self, preset: str):
        if preset in self._preset_btns:
            self._apply_preset_chip(preset)
        else:
            # Try to map unknown presets gracefully
            log.warning(f"[TOOL TRACKER V2 UI] Unknown preset: {preset!r}")

    def display_tools(self, tools, brands=None):
        """Called by v1-compat event handler."""
        self._all_tools = list(tools)
        if brands is not None:
            self._rebuild_brand_filter(brands)
        self._apply_filters()

    def update_statistics(self, stats):
        pass

    # ── Quick create ───────────────────────────────────────────────────────────

    def _handle_quick_create(self):
        if not self._quick_add.is_expanded():
            self._quick_add.expand()
        else:
            self._quick_add.collapse()

    # ── Preset chips ──────────────────────────────────────────────────────────

    def _apply_preset_chip(self, key: str):
        self._active_preset = key
        for k, btn in self._preset_btns.items():
            active = (k == key)
            btn.setObjectName("chipActive" if active else "chip")
            btn.setChecked(active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # Map preset key to filter values
        preset_type_map = {
            "brushes":  "Brush",
            "cutting":  None,  # handled below
            "adhesives": None, # handled below
        }
        preset_cond_map = {
            "needs_replacing": "Replace",
            "worn":            "Worn",
        }

        # Reset filters first
        self._type_filter.blockSignals(True)
        self._cond_filter.blockSignals(True)
        self._type_filter.setCurrentIndex(0)
        self._cond_filter.setCurrentIndex(0)

        if key == "brushes":
            idx = self._type_filter.findText("Brush")
            if idx >= 0:
                self._type_filter.setCurrentIndex(idx)
        elif key == "cutting":
            # Will be handled in _apply_filters with a custom multi-type filter
            pass
        elif key == "adhesives":
            # Will be handled in _apply_filters with a custom multi-type filter
            pass
        elif key in preset_cond_map:
            idx = self._cond_filter.findText(preset_cond_map[key])
            if idx >= 0:
                self._cond_filter.setCurrentIndex(idx)

        self._type_filter.blockSignals(False)
        self._cond_filter.blockSignals(False)
        self._apply_filters()

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _on_filter_changed(self, *_):
        # Sync preset chip state to current condition filter
        cond_val = self._cond_filter.currentText()
        if cond_val == "Replace":
            self._set_active_chip("needs_replacing")
        elif cond_val == "Worn":
            self._set_active_chip("worn")
        elif self._active_preset not in ("brushes", "cutting", "adhesives"):
            self._set_active_chip("all")
        self._apply_filters()

    def _set_active_chip(self, key: str):
        if self._active_preset == key:
            return
        self._active_preset = key
        for k, btn in self._preset_btns.items():
            active = (k == key)
            btn.setObjectName("chipActive" if active else "chip")
            btn.setChecked(active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _apply_filters(self):
        search    = self._search_edit.text().strip().lower()
        type_val  = self._type_filter.currentText()
        brand_val = self._brand_filter.currentText()
        cond_val  = self._cond_filter.currentText()
        sort_val  = self._sort_combo.currentText()

        filtered = list(self._all_tools)

        # Special preset multi-filters
        if self._active_preset == "cutting":
            cutting_types = {"Hobby Knife / Blade", "Nippers", "Cutting Mat", "File", "Sandpaper"}
            filtered = [t for t in filtered if t.tool_type in cutting_types]
        elif self._active_preset == "adhesives":
            adhesive_types = {"Plastic Glue", "Super Glue", "Green Stuff / Putty"}
            filtered = [t for t in filtered if t.tool_type in adhesive_types]

        if search:
            filtered = [
                t for t in filtered
                if search in t.name.lower()
                or search in (t.brand or "").lower()
                or search in t.tool_type.lower()
                or search in (t.notes or "").lower()
            ]
        if type_val and type_val != "All Types":
            filtered = [t for t in filtered if t.tool_type == type_val]
        if brand_val and brand_val != "All Brands":
            filtered = [t for t in filtered if t.brand == brand_val]
        if cond_val and cond_val != "All Conditions":
            filtered = [t for t in filtered if t.condition == cond_val]

        # Sorting
        if sort_val == "Name A–Z":
            filtered.sort(key=lambda t: t.name.lower())
        elif sort_val == "Type":
            filtered.sort(key=lambda t: t.tool_type.lower())
        elif sort_val == "Brand":
            filtered.sort(key=lambda t: (t.brand or "").lower())
        elif sort_val == "Condition":
            order = {c: i for i, c in enumerate(TOOL_CONDITIONS)}
            filtered.sort(key=lambda t: order.get(t.condition, 99))
        elif sort_val == "Qty ↑":
            filtered.sort(key=lambda t: t.quantity)
        elif sort_val == "Qty ↓":
            filtered.sort(key=lambda t: t.quantity, reverse=True)

        self._filtered = filtered
        self._render_cards()
        self._render_table()
        self._update_status()

    def _update_brand_filter(self):
        brands = sorted({t.brand for t in self._all_tools if t.brand})
        self._rebuild_brand_filter(brands)

    def _rebuild_brand_filter(self, brands: list):
        current = self._brand_filter.currentText()
        self._brand_filter.blockSignals(True)
        self._brand_filter.clear()
        self._brand_filter.addItem("All Brands")
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
            ph = QLabel(
                "No tools found.\n"
                "Try adjusting your filters or add a new tool."
            )
            ph.setAlignment(Qt.AlignCenter)
            ph.setStyleSheet(
                "font-size: 13px; color: rgba(255,255,255,0.28); padding: 60px;"
            )
            ph.setWordWrap(True)
            grid.addWidget(ph, 0, 0, 1, max(cols, 1))
        else:
            row = col = 0
            for tool in self._filtered:
                projs = self._tool_projects.get(tool.id, [])
                card  = _ToolCard(tool, projs)
                card.edit_requested.connect(self._on_edit)
                card.delete_requested.connect(self._on_delete)
                card.condition_cycled.connect(self._on_condition_cycle)
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
        sort_key_map = {
            self._COL_ICON:      lambda t: _type_icon(t.tool_type),
            self._COL_NAME:      lambda t: (t.name or "").lower(),
            self._COL_BRAND:     lambda t: (t.brand or "").lower(),
            self._COL_TYPE:      lambda t: (t.tool_type or "").lower(),
            self._COL_CONDITION: lambda t: TOOL_CONDITIONS.index(t.condition)
                                           if t.condition in TOOL_CONDITIONS else 99,
            self._COL_QTY:       lambda t: t.quantity,
            self._COL_PROJECTS:  lambda t: len(self._tool_projects.get(t.id, [])),
            self._COL_NOTES:     lambda t: bool(t.notes),
        }
        key_fn      = sort_key_map.get(self._sort_col, sort_key_map[self._COL_NAME])
        sorted_tools = sorted(self._filtered, key=key_fn, reverse=self._sort_desc)

        self._table.setRowCount(0)
        self._table.setRowCount(len(sorted_tools))
        for row, tool in enumerate(sorted_tools):
            self._table.setRowHeight(row, 34)
            cond_color = QColor(_cond_bg(tool.condition))

            icon_item = QTableWidgetItem(_type_icon(tool.tool_type))
            icon_item.setTextAlignment(Qt.AlignCenter)
            icon_item.setData(Qt.UserRole, tool)
            self._table.setItem(row, self._COL_ICON, icon_item)

            name_item = QTableWidgetItem(tool.name)
            name_item.setData(Qt.UserRole, tool)
            self._table.setItem(row, self._COL_NAME, name_item)

            brand_item = QTableWidgetItem(tool.brand or "")
            brand_item.setData(Qt.UserRole, tool)
            self._table.setItem(row, self._COL_BRAND, brand_item)

            type_item = QTableWidgetItem(tool.tool_type or "")
            type_item.setData(Qt.UserRole, tool)
            self._table.setItem(row, self._COL_TYPE, type_item)

            cond_item = QTableWidgetItem(tool.condition)
            cond_item.setForeground(QColor(_cond_fg(tool.condition)))
            cond_item.setBackground(cond_color)
            cond_item.setTextAlignment(Qt.AlignCenter)
            cond_item.setData(Qt.UserRole, tool)
            self._table.setItem(row, self._COL_CONDITION, cond_item)

            qty_item = QTableWidgetItem(str(tool.quantity))
            qty_item.setTextAlignment(Qt.AlignCenter)
            qty_item.setData(Qt.UserRole, tool)
            self._table.setItem(row, self._COL_QTY, qty_item)

            projs       = self._tool_projects.get(tool.id, [])
            proj_count  = len(projs)
            if proj_count > 0:
                proj_text = f"📁 {proj_count}"
            else:
                proj_text = "—"
            proj_item = QTableWidgetItem(proj_text)
            proj_item.setTextAlignment(Qt.AlignCenter)
            proj_item.setData(Qt.UserRole, tool)
            self._table.setItem(row, self._COL_PROJECTS, proj_item)

            notes_item = QTableWidgetItem("●" if tool.notes else "")
            notes_item.setTextAlignment(Qt.AlignCenter)
            notes_item.setData(Qt.UserRole, tool)
            if tool.notes:
                notes_item.setForeground(QColor("#4f9eff"))
                notes_item.setToolTip(tool.notes)
            self._table.setItem(row, self._COL_NOTES, notes_item)

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _update_status(self):
        total = len(self._filtered)
        all_n = len(self._all_tools)
        if total == all_n:
            self._status_lbl.setText(f"{total} tool{'s' if total != 1 else ''}")
        else:
            self._status_lbl.setText(f"{total} of {all_n} tools")

        # Attention count (worn + replace) from filtered set
        attn = sum(
            1 for t in self._filtered
            if t.condition in ("Worn", "Replace")
        )
        if attn > 0:
            self._attn_lbl.setText(f"{attn} need attention ⚠️")
            self._attn_lbl.setVisible(True)
        else:
            self._attn_lbl.setVisible(False)

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

    def _on_add(self, data: dict):
        try:
            tool = self._svc.add_tool(
                name      = data["name"],
                tool_type = data["tool_type"],
                brand     = data.get("brand", ""),
                condition = data.get("condition", "Good"),
                quantity  = data.get("quantity", 1),
                notes     = data.get("notes"),
            )
            self.refresh()
            self._show_toast(f"✓  Added {tool.name}")
            self._fire("tool_added", {"id": tool.id, **data})
            self._fire("dashboard_provider_updated", {})
        except ValidationError as e:
            self._show_toast(str(e), error=True)
        except Exception as e:
            log.error(f"[TOOL TRACKER V2 UI] _on_add: {e}")
            self._show_toast(f"Error: {e}", error=True)

    def _on_edit(self, tool: Tool):
        dlg = _EditDialog(tool, self._ctx, parent=self)
        self._apply_dialog_theme(dlg)
        if dlg.exec():
            try:
                data = dlg.get_data()
                linked   = data.pop("linked_project_ids", [])
                unlinked = data.pop("unlinked_project_ids", [])

                self._svc.update_tool(tool.id, **data)
                self.refresh()
                self._show_toast(f"✓  Updated {data['name']}")
                self._fire("tool_updated", {"id": tool.id, **data})

                # Handle project link/unlink
                if linked or unlinked:
                    self._on_project_link_changed(tool.id, linked, unlinked)

                self._fire("dashboard_provider_updated", {})
            except (ValidationError, ValueError) as e:
                self._show_toast(str(e), error=True)
            except Exception as e:
                log.error(f"[TOOL TRACKER V2 UI] _on_edit: {e}")
                self._show_toast(f"Error: {e}", error=True)

    def _on_delete(self, tool: Tool):
        reply = QMessageBox.question(
            self, "Delete Tool",
            f"Delete <b>{tool.name}</b>?<br>This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            self._undo_tool = tool
            try:
                self._svc.remove_tool(tool.id)
                self.refresh()
                self._show_toast(
                    f"Deleted {tool.name}",
                    action_label="Undo",
                    action_cb=self._undo_delete,
                )
                self._fire("tool_removed", {"id": tool.id})
                self._fire("dashboard_provider_updated", {})
            except Exception as e:
                log.error(f"[TOOL TRACKER V2 UI] _on_delete: {e}")
                self._show_toast(f"Error: {e}", error=True)

    def _undo_delete(self):
        t = self._undo_tool
        if not t:
            return
        try:
            restored = self._svc.add_tool(
                name=t.name, tool_type=t.tool_type,
                brand=t.brand, condition=t.condition,
                quantity=t.quantity, notes=t.notes,
            )
            self._undo_tool = None
            self.refresh()
            self._show_toast(f"✓  Restored {t.name}")
            self._fire("tool_added", {"id": restored.id})
        except Exception as e:
            log.error(f"[TOOL TRACKER V2 UI] _undo_delete: {e}")
            self._show_toast(f"Could not restore: {e}", error=True)

    def _on_condition_cycle(self, tool: Tool, new_condition: str):
        try:
            self._svc.update_tool(
                tool_id   = tool.id,
                name      = tool.name,
                tool_type = tool.tool_type,
                brand     = tool.brand,
                condition = new_condition,
                quantity  = tool.quantity,
                notes     = tool.notes,
            )
            self.refresh()
            self._show_toast(f"✓  {tool.name} → {new_condition}")
            self._fire("tool_updated", {"id": tool.id, "condition": new_condition})
            self._fire("dashboard_provider_updated", {})
        except (ValidationError, ValueError) as e:
            self._show_toast(str(e), error=True)
        except Exception as e:
            log.error(f"[TOOL TRACKER V2 UI] _on_condition_cycle: {e}")
            self._show_toast(f"Error: {e}", error=True)

    def _on_project_link_changed(
        self, tool_id: int, linked_ids: list[int], unlinked_ids: list[int]
    ):
        if not self._proj_svc:
            return
        try:
            for pid in linked_ids:
                self._proj_svc.link_entity(pid, "tool", tool_id)
            for pid in unlinked_ids:
                self._proj_svc.unlink_entity(pid, "tool", tool_id)
            # Refresh local cache
            try:
                projs = self._proj_svc.get_projects_for_entity("tool", tool_id)
                self._tool_projects[tool_id] = projs
            except Exception as e:
                log.warning(f"[TOOL TRACKER V2 UI] project cache refresh: {e}")
            self._fire("dashboard_provider_updated", {})
        except Exception as e:
            log.error(f"[TOOL TRACKER V2 UI] _on_project_link_changed: {e}")
            self._show_toast(f"Project link error: {e}", error=True)

    # ── Table interaction ──────────────────────────────────────────────────────

    def _on_table_double_click(self, index):
        item = self._table.item(index.row(), self._COL_NAME)
        if item:
            tool = item.data(Qt.UserRole)
            if tool:
                self._on_edit(tool)

    def _on_table_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        item = self._table.item(row, self._COL_NAME)
        if not item:
            return
        tool = item.data(Qt.UserRole)
        if not tool:
            return
        menu      = QMenu(self)
        edit_act  = menu.addAction("✏  Edit")
        cycle_act = menu.addAction(f"🔄  Cycle → {_next_condition(tool.condition)}")
        menu.addSeparator()
        del_act   = menu.addAction("🗑  Delete")
        act       = menu.exec(self._table.viewport().mapToGlobal(pos))
        if act == edit_act:
            self._on_edit(tool)
        elif act == cycle_act:
            self._on_condition_cycle(tool, _next_condition(tool.condition))
        elif act == del_act:
            self._on_delete(tool)

    def _table_key_press(self, event):
        key  = event.key()
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            QTableWidget.keyPressEvent(self._table, event)
            return
        row  = rows[0].row()
        item = self._table.item(row, self._COL_NAME)
        tool = item.data(Qt.UserRole) if item else None
        if tool:
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._on_edit(tool)
                return
            elif key == Qt.Key_Delete:
                self._on_delete(tool)
                return
        QTableWidget.keyPressEvent(self._table, event)

    def _on_header_clicked(self, col: int):
        if col == self._COL_ICON:
            return
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col  = col
            self._sort_desc = False
        hdr = self._table.horizontalHeader()
        hdr.setSortIndicator(
            col, Qt.DescendingOrder if self._sort_desc else Qt.AscendingOrder
        )
        self._render_table()

    # ── CSV export ─────────────────────────────────────────────────────────────

    def _export_csv(self):
        if not self._filtered:
            self._show_toast(
                "Nothing to export — no tools match the current filter.", error=True
            )
            return
        timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"tools_{timestamp}.csv"
        path, _      = QFileDialog.getSaveFileName(
            self, "Export Tools to CSV",
            os.path.join(os.path.expanduser("~"), default_name),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Name", "Type", "Brand", "Condition", "Quantity", "Notes"
                ])
                for t in self._filtered:
                    writer.writerow([
                        t.name,
                        t.tool_type,
                        t.brand or "",
                        t.condition,
                        t.quantity,
                        t.notes or "",
                    ])
            fname = os.path.basename(path)
            self._show_toast(f"✓  Exported {len(self._filtered)} tools to {fname}")
        except Exception as e:
            log.error(f"[TOOL TRACKER V2 UI] export CSV: {e}")
            self._show_toast(f"Export failed: {e}", error=True)

    # ── Toast ──────────────────────────────────────────────────────────────────

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

    def _on_theme_changed(self, payload=None):
        self._apply_theme()

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
                QWidget#toolHeader {{
                    background: {bg2};
                    border-bottom: 1px solid {brd};
                }}
                QLabel#toolSubtitle {{
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
                QWidget#toolFilterBar {{
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
                QWidget#toolStatusBar {{
                    background: {bg2};
                    border-top: 1px solid {brd};
                }}
                QLabel#statusCount {{
                    font-size: 11px;
                    color: {fg2};
                }}
                QLabel#attnLabel {{
                    font-size: 11px;
                    color: #e07800;
                    font-weight: 600;
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
            log.error(f"[TOOL TRACKER V2 UI] theme error: {e}")

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
                QGroupBox {{
                    background: transparent;
                    color: {fg2};
                    border: 1px solid {brd};
                    border-radius: 6px;
                    margin-top: 8px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 4px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 0 6px;
                    color: {fg2};
                }}
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
                QListWidget {{
                    background: {bg2}; color: {fg};
                    border: 1px solid {brd}; border-radius: 5px;
                }}
                QListWidget::item {{ padding: 4px 8px; }}
                QListWidget::item:hover {{ background: rgba(255,255,255,0.05); }}
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
                QPushButton#secondaryBtn {{
                    background: {inp}; color: {fg};
                    border: 1px solid {brd}; border-radius: 5px;
                    font-size: 12px;
                }}
                QPushButton#secondaryBtn:hover {{
                    border-color: {acc}; color: {acc};
                }}
                QFrame[frameShape="4"] {{
                    background: {brd}; border: none; max-height: 1px;
                }}
            """)
        except Exception as e:
            log.error(f"[TOOL TRACKER V2 UI] dialog theme error: {e}")

    # ── Event bus helper ───────────────────────────────────────────────────────

    def _fire(self, event: str, payload: dict | None = None):
        try:
            self._ctx.event_bus.emit(event, payload or {})
        except Exception:
            pass

    # ── v1 compat helpers ──────────────────────────────────────────────────────

    def _show_success(self, msg: str):
        self._show_toast(f"✓  {msg}")

    def _show_error(self, msg: str):
        self._show_toast(msg, error=True)
