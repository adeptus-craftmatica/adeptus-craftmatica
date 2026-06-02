"""
Campaign Tracker v2 — Crusade Records / Campaign Progression UI.

Provides the full progression tracking layer:
  Tab 0 — Force Overview   (stats, CP/RP, supply, requisition log, notes)
  Tab 1 — Unit Records     (XP, ranks, battle honours, scars, warlord)
  Tab 2 — Battle Log       (history, VP, narrative, unit XP grants)
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QListWidget, QListWidgetItem, QSplitter, QDialog,
    QDialogButtonBox, QLineEdit, QComboBox, QSpinBox, QTextEdit,
    QStackedWidget, QCheckBox, QFormLayout, QMessageBox, QApplication,
    QSizePolicy, QTabWidget, QProgressBar, QDateEdit, QGroupBox,
    QInputDialog,
)
from PySide6.QtGui import QFont

log = logging.getLogger(__name__)

# ── Palette ────────────────────────────────────────────────────────────────────
_BG      = "#1c1c1c"
_BG2     = "#212121"
_BG3     = "#282828"
_SIDEBAR = "#161616"
_BORDER  = "#2e2e2e"
_BORDER2 = "#3a3a3a"
_FG      = "#f0f0f0"
_FG_MID  = "#a0a0a0"
_FG_DIM  = "#606060"
_ACCENT  = "#4f9eff"
_SUCCESS = "#3dba6e"
_DANGER  = "#e05555"
_WARN    = "#e07800"
_GOLD    = "#f0c040"

# ── Game data ─────────────────────────────────────────────────────────────────

XP_RANKS = [
    (0,  "Fresh Recruit", 0),
    (5,  "Blooded",       1),
    (10, "Veteran",       2),
    (15, "Elite",         3),
    (20, "Legendary",     4),
]

HONOUR_TYPES = [
    "Battle Trait",
    "Weapon Enhancement",
    "Crusade Relic",
    "Mark of Greatness",
    "Psychic Fortitude",
    "Agendas",
    "Other",
]

SCAR_TYPES = [
    "Damaged Armoury",
    "Horrific Losses",
    "Forsaken Hero",
    "Mark of Shame",
    "Battle-weary",
    "Legendary Name",
    "Other",
]

REQUISITION_ACTIONS = [
    ("Increase Supply Limit",      1, "Increase your Supply Limit by 5"),
    ("Repair and Recuperate",      2, "Remove one Battle Scar from a unit"),
    ("Veteran Reinforcements",     1, "Add a new unit to your Order of Battle"),
    ("Fresh Starts",               1, "Remove all Crusade XP from a unit"),
    ("Specialist Reinforcements",  2, "Add a Specialist unit to your Order of Battle"),
    ("Strategic Reserve",          2, "Add a unique asset to your force"),
    ("Earn RP",                    0, "Gain Requisition Points (custom amount)"),
]

GLORY_RANKS = [
    (0,   "Challenger"),
    (10,  "Aspirant"),
    (20,  "Champion"),
    (40,  "Conqueror"),
    (60,  "Warlord"),
    (100, "Legend"),
]


# ── XP helpers ────────────────────────────────────────────────────────────────

def _get_rank_info(xp: int) -> tuple[str, int, int, int]:
    """Return (rank_name, honour_slots, rank_min, next_threshold)."""
    rank_name    = "Fresh Recruit"
    honour_slots = 0
    rank_min     = 0
    next_thresh  = 5
    for i, (thresh, name, slots) in enumerate(XP_RANKS):
        if xp >= thresh:
            rank_name    = name
            honour_slots = slots
            rank_min     = thresh
            if i + 1 < len(XP_RANKS):
                next_thresh = XP_RANKS[i + 1][0]
            else:
                next_thresh = thresh
    return rank_name, honour_slots, rank_min, next_thresh


def _rank_color(rank_name: str) -> str:
    colors = {
        "Legendary":     _GOLD,
        "Elite":         _ACCENT,
        "Veteran":       _ACCENT,
        "Blooded":       _FG_MID,
        "Fresh Recruit": _FG_DIM,
    }
    return colors.get(rank_name, _FG_MID)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{_FG_DIM}; font-size:10px; font-weight:700; letter-spacing:2px; "
        f"background:transparent; border:none; padding-top:12px; padding-bottom:4px;"
    )
    return lbl


def _h_line() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"background:{_BORDER}; border:none; max-height:1px;")
    return line


def _stat_card(label: str, value: str, color: str = _FG) -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:8px;"
    )
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 12, 16, 12)
    lay.setSpacing(4)
    val = QLabel(str(value))
    val.setAlignment(Qt.AlignmentFlag.AlignCenter)
    val.setStyleSheet(
        f"color:{color}; font-size:28px; font-weight:700; "
        f"background:transparent; border:none;"
    )
    lbl = QLabel(label)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"color:{_FG_DIM}; font-size:10px; font-weight:600; letter-spacing:1px; "
        f"background:transparent; border:none;"
    )
    lay.addWidget(val)
    lay.addWidget(lbl)
    return f


def _progress_bar(value: int, maximum: int, color: str = _ACCENT) -> QProgressBar:
    pb = QProgressBar()
    pb.setRange(0, max(maximum, 1))
    pb.setValue(min(value, maximum))
    pb.setTextVisible(False)
    pb.setFixedHeight(6)
    pb.setStyleSheet(
        f"QProgressBar {{background:{_BG3}; border-radius:3px; border:none;}}"
        f"QProgressBar::chunk {{background:{color}; border-radius:3px;}}"
    )
    return pb


# ══════════════════════════════════════════════════════════════════════════════
#  Add Honour / Scar dialogs
# ══════════════════════════════════════════════════════════════════════════════

class _AddHonourDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Battle Honour")
        self.setMinimumWidth(420)
        self._build()

    def result_data(self) -> dict:
        return {
            "type":   self._type.currentText(),
            "name":   self._name.text().strip(),
            "effect": self._effect.toPlainText().strip(),
        }

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)
        self._type = QComboBox()
        self._type.addItems(HONOUR_TYPES)
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Unyielding")
        self._effect = QTextEdit()
        self._effect.setPlaceholderText("Describe the honour's effect…")
        self._effect.setFixedHeight(72)
        form.addRow("Type", self._type)
        form.addRow("Name", self._name)
        form.addRow("Effect", self._effect)
        lay.addLayout(form)

        btns = QDialogButtonBox()
        add_btn = btns.addButton("Add Honour", QDialogButtonBox.AcceptRole)
        btns.addButton("Cancel", QDialogButtonBox.RejectRole)
        add_btn.setObjectName("accentBtn")
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _try_accept(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Required", "Please enter a name for this honour.")
            return
        self.accept()


class _AddScarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Battle Scar")
        self.setMinimumWidth(420)
        self._build()

    def result_data(self) -> dict:
        return {
            "type":   self._type.currentText(),
            "name":   self._name.text().strip(),
            "effect": self._effect.toPlainText().strip(),
        }

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)
        self._type = QComboBox()
        self._type.addItems(SCAR_TYPES)
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Damaged Optics")
        self._effect = QTextEdit()
        self._effect.setPlaceholderText("Describe the scar's effect…")
        self._effect.setFixedHeight(72)
        form.addRow("Type", self._type)
        form.addRow("Name", self._name)
        form.addRow("Effect", self._effect)
        lay.addLayout(form)

        btns = QDialogButtonBox()
        add_btn = btns.addButton("Add Scar", QDialogButtonBox.AcceptRole)
        btns.addButton("Cancel", QDialogButtonBox.RejectRole)
        add_btn.setObjectName("dangerBtn")
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _try_accept(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Required", "Please enter a name for this scar.")
            return
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  Requisition dialogs
# ══════════════════════════════════════════════════════════════════════════════

class _EarnRequisitionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Earn Requisition Points")
        self.setMinimumWidth(360)
        self._build()

    def result_data(self) -> dict:
        return {
            "amount":      self._amount.value(),
            "reason":      self._reason.text().strip(),
        }

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(10)
        self._amount = QSpinBox()
        self._amount.setRange(1, 20)
        self._amount.setValue(1)
        self._reason = QLineEdit()
        self._reason.setPlaceholderText("e.g. Battle reward, campaign milestone…")
        form.addRow("Amount (RP)", self._amount)
        form.addRow("Reason", self._reason)
        lay.addLayout(form)
        btns = QDialogButtonBox()
        ok_btn = btns.addButton("Add RP", QDialogButtonBox.AcceptRole)
        ok_btn.setObjectName("accentBtn")
        btns.addButton("Cancel", QDialogButtonBox.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)


class _SpendRequisitionDialog(QDialog):
    def __init__(self, current_rp: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spend Requisition Points")
        self.setMinimumWidth(480)
        self._current_rp = current_rp
        self._build()

    def result_data(self) -> dict:
        row = self._list.currentRow()
        if row < 0:
            return {}
        name, cost, _ = REQUISITION_ACTIONS[row]
        actual_cost = self._custom_amount.value() if name == "Earn RP" else cost
        return {
            "action":      name,
            "cost":        actual_cost,
            "description": self._desc.text().strip(),
        }

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)

        rp_lbl = QLabel(f"Available RP: {self._current_rp}")
        rp_lbl.setStyleSheet(f"color:{_GOLD}; font-size:14px; font-weight:700;")
        lay.addWidget(rp_lbl)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;}}"
            f"QListWidget::item {{padding:8px 12px; border-bottom:1px solid {_BORDER};}}"
            f"QListWidget::item:selected {{background:{_ACCENT}20; color:{_FG};}}"
        )
        for name, cost, desc in REQUISITION_ACTIONS:
            cost_text = "free" if cost == 0 else f"{cost} RP"
            item = QListWidgetItem(f"{name}  [{cost_text}]  —  {desc}")
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        lay.addWidget(self._list)

        self._custom_row = QWidget()
        cr_lay = QHBoxLayout(self._custom_row)
        cr_lay.setContentsMargins(0, 0, 0, 0)
        cr_lay.addWidget(QLabel("Custom RP amount:"))
        self._custom_amount = QSpinBox()
        self._custom_amount.setRange(1, 20)
        cr_lay.addWidget(self._custom_amount)
        cr_lay.addStretch()
        self._custom_row.setVisible(False)
        lay.addWidget(self._custom_row)

        form = QFormLayout()
        self._desc = QLineEdit()
        self._desc.setPlaceholderText("Optional description…")
        form.addRow("Description", self._desc)
        lay.addLayout(form)

        btns = QDialogButtonBox()
        ok_btn = btns.addButton("Confirm", QDialogButtonBox.AcceptRole)
        ok_btn.setObjectName("accentBtn")
        btns.addButton("Cancel", QDialogButtonBox.RejectRole)
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_selection_changed(self, row: int):
        if row < 0:
            return
        name, cost, _ = REQUISITION_ACTIONS[row]
        self._custom_row.setVisible(name == "Earn RP")

    def _try_accept(self):
        row = self._list.currentRow()
        if row < 0:
            return
        name, cost, _ = REQUISITION_ACTIONS[row]
        actual_cost = self._custom_amount.value() if name == "Earn RP" else cost
        if name != "Earn RP" and actual_cost > self._current_rp:
            QMessageBox.warning(
                self, "Insufficient RP",
                f"This action costs {actual_cost} RP but you only have {self._current_rp}.",
            )
            return
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  Log Battle dialog
# ══════════════════════════════════════════════════════════════════════════════

class _LogBattleDialog(QDialog):
    def __init__(self, oob_units: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Battle")
        self.setMinimumSize(560, 640)
        self._oob_units = oob_units
        self._honours: list[str] = []
        self._build()

    def result_data(self) -> dict:
        # Collect selected unit IDs
        selected_ids = []
        for i in range(self._units_list.count()):
            item = self._units_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_ids.append(item.data(Qt.UserRole))

        return {
            "battle_date":      self._date.date().toString("yyyy-MM-dd"),
            "mission":          self._mission.text().strip(),
            "opponent":         self._opponent.text().strip(),
            "points_played":    self._points.value(),
            "result":           self._result.currentText(),
            "vp_scored":        self._vp_us.value(),
            "vp_opponent":      self._vp_them.value(),
            "narrative_notes":  self._narrative.toPlainText().strip(),
            "units_json":       json.dumps(selected_ids),
            "honours_awarded":  json.dumps(self._honours),
        }

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        title = QLabel("Log Battle")
        title.setStyleSheet(f"color:{_FG}; font-size:16px; font-weight:700;")
        lay.addWidget(title)

        # Row 1: Date + Mission
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        date_form = QFormLayout()
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        date_form.addRow("Date", self._date)
        row1.addLayout(date_form)
        mission_form = QFormLayout()
        self._mission = QLineEdit()
        self._mission.setPlaceholderText("e.g. Sweep and Clear")
        mission_form.addRow("Mission", self._mission)
        row1.addLayout(mission_form)
        lay.addLayout(row1)

        # Row 2: Opponent + Points
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        opp_form = QFormLayout()
        self._opponent = QLineEdit()
        self._opponent.setPlaceholderText("Opponent name / army")
        opp_form.addRow("Opponent", self._opponent)
        row2.addLayout(opp_form)
        pts_form = QFormLayout()
        self._points = QSpinBox()
        self._points.setRange(0, 9999)
        self._points.setValue(1000)
        pts_form.addRow("Points", self._points)
        row2.addLayout(pts_form)
        lay.addLayout(row2)

        # Row 3: Result + VPs
        row3 = QHBoxLayout()
        row3.setSpacing(12)
        res_form = QFormLayout()
        self._result = QComboBox()
        self._result.addItems(["Victory", "Defeat", "Draw"])
        res_form.addRow("Result", self._result)
        row3.addLayout(res_form)
        vp_form = QFormLayout()
        self._vp_us = QSpinBox()
        self._vp_us.setRange(0, 200)
        vp_form.addRow("Our VP", self._vp_us)
        row3.addLayout(vp_form)
        vp_them_form = QFormLayout()
        self._vp_them = QSpinBox()
        self._vp_them.setRange(0, 200)
        vp_them_form.addRow("Opponent VP", self._vp_them)
        row3.addLayout(vp_them_form)
        lay.addLayout(row3)

        # Units section
        lay.addWidget(_section_header("PARTICIPATING UNITS"))
        self._units_list = QListWidget()
        self._units_list.setStyleSheet(
            f"QListWidget {{background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px; max-height:120px;}}"
            f"QListWidget::item {{padding:4px 8px;}}"
        )
        for unit in self._oob_units:
            item = QListWidgetItem(unit.get("custom_name", "Unknown Unit"))
            item.setData(Qt.UserRole, unit.get("id", 0))
            item.setCheckState(Qt.Unchecked)
            self._units_list.addItem(item)
        lay.addWidget(self._units_list)

        # Honours awarded
        lay.addWidget(_section_header("HONOURS AWARDED THIS BATTLE"))
        honours_row = QHBoxLayout()
        self._honours_list = QListWidget()
        self._honours_list.setStyleSheet(
            f"QListWidget {{background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px; max-height:80px;}}"
            f"QListWidget::item {{padding:4px 8px;}}"
        )
        honours_row.addWidget(self._honours_list, 1)
        hon_btns = QVBoxLayout()
        add_hon = QPushButton("+ Add")
        add_hon.setFixedWidth(60)
        add_hon.clicked.connect(self._add_honour_entry)
        rem_hon = QPushButton("Remove")
        rem_hon.setFixedWidth(60)
        rem_hon.clicked.connect(self._remove_honour_entry)
        hon_btns.addWidget(add_hon)
        hon_btns.addWidget(rem_hon)
        hon_btns.addStretch()
        honours_row.addLayout(hon_btns)
        lay.addLayout(honours_row)

        # Narrative
        lay.addWidget(_section_header("BATTLE NARRATIVE"))
        self._narrative = QTextEdit()
        self._narrative.setPlaceholderText("Describe the battle…")
        self._narrative.setFixedHeight(80)
        lay.addWidget(self._narrative)

        # Buttons
        btns = QDialogButtonBox()
        ok_btn = btns.addButton("Log Battle", QDialogButtonBox.AcceptRole)
        ok_btn.setObjectName("accentBtn")
        btns.addButton("Cancel", QDialogButtonBox.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _add_honour_entry(self):
        text, ok = QInputDialog.getText(
            self, "Add Honour",
            "Format: Unit Name — Honour Name",
            text="",
        )
        if ok and text.strip():
            self._honours.append(text.strip())
            self._honours_list.addItem(text.strip())

    def _remove_honour_entry(self):
        row = self._honours_list.currentRow()
        if row >= 0:
            self._honours_list.takeItem(row)
            if row < len(self._honours):
                self._honours.pop(row)


# ══════════════════════════════════════════════════════════════════════════════
#  Unit list card widget
# ══════════════════════════════════════════════════════════════════════════════

class _UnitListCard(QFrame):
    clicked = Signal(dict)   # emits the unit record dict

    def __init__(self, unit: dict, parent=None):
        super().__init__(parent)
        self._unit = unit
        self.setFixedHeight(80)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame {{background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;}}"
            f"QFrame:hover {{border:1px solid {_BORDER2}; background:{_BG3};}}"
        )
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)

        xp   = self._unit.get("experience_points", 0)
        name = self._unit.get("custom_name") or self._unit.get("legendary_name") or "Unknown Unit"
        is_ooa = self._unit.get("is_out_of_action", False)
        honours = self._unit.get("honours_json", [])
        scars   = self._unit.get("scars_json", [])

        # Row 1: name + OoA indicator
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color:{'#606060' if is_ooa else _FG}; font-weight:600; font-size:12px; "
            f"{'text-decoration:line-through;' if is_ooa else ''}"
            f"background:transparent; border:none;"
        )
        row1.addWidget(name_lbl, 1)
        if is_ooa:
            ooa_lbl = QLabel("⚠ OOA")
            ooa_lbl.setStyleSheet(f"color:{_DANGER}; font-size:10px; font-weight:700; background:transparent; border:none;")
            row1.addWidget(ooa_lbl)
        lay.addLayout(row1)

        # Row 2: rank badge + XP bar
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        rank_name, slots, rank_min, next_thresh = _get_rank_info(xp)
        rank_lbl = QLabel(rank_name.upper())
        rank_lbl.setStyleSheet(
            f"color:{_rank_color(rank_name)}; font-size:9px; font-weight:700; "
            f"letter-spacing:1px; background:transparent; border:none;"
        )
        row2.addWidget(rank_lbl)

        # XP progress bar
        if next_thresh > rank_min:
            bar_val = xp - rank_min
            bar_max = next_thresh - rank_min
        else:
            bar_val = 1
            bar_max = 1
        pb = _progress_bar(bar_val, bar_max, _rank_color(rank_name))
        pb.setFixedWidth(80)
        row2.addWidget(pb)
        xp_lbl = QLabel(f"{xp} XP")
        xp_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; background:transparent; border:none;")
        row2.addWidget(xp_lbl)
        row2.addStretch()
        lay.addLayout(row2)

        # Row 3: honours + scars count
        row3 = QHBoxLayout()
        row3.setSpacing(10)
        h_lbl = QLabel(f"🏅 {len(honours)} Honours")
        h_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:10px; background:transparent; border:none;")
        row3.addWidget(h_lbl)
        if scars:
            s_lbl = QLabel(f"⚠ {len(scars)} Scar{'s' if len(scars) != 1 else ''}")
            s_lbl.setStyleSheet(f"color:{_WARN}; font-size:10px; background:transparent; border:none;")
            row3.addWidget(s_lbl)
        row3.addStretch()
        lay.addLayout(row3)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._unit)
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  Battle list card widget
# ══════════════════════════════════════════════════════════════════════════════

class _BattleListCard(QFrame):
    clicked = Signal(dict)

    def __init__(self, battle: dict, parent=None):
        super().__init__(parent)
        self._battle = battle
        self.setFixedHeight(64)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame {{background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;}}"
            f"QFrame:hover {{border:1px solid {_BORDER2}; background:{_BG3};}}"
        )
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)

        result = self._battle.get("result", "Draw")
        result_color = {
            "Victory": _SUCCESS,
            "Defeat":  _DANGER,
            "Draw":    _FG_MID,
        }.get(result, _FG_MID)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        result_badge = QLabel(result.upper())
        result_badge.setStyleSheet(
            f"color:{result_color}; font-size:10px; font-weight:700; "
            f"background:{result_color}20; border:1px solid {result_color}60; "
            f"border-radius:3px; padding:1px 5px;"
        )
        row1.addWidget(result_badge)
        mission = self._battle.get("mission", "") or "Unknown Mission"
        mission_lbl = QLabel(mission)
        mission_lbl.setStyleSheet(f"color:{_FG}; font-weight:600; font-size:12px; background:transparent; border:none;")
        row1.addWidget(mission_lbl, 1)
        date_lbl = QLabel(self._battle.get("battle_date", ""))
        date_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; background:transparent; border:none;")
        row1.addWidget(date_lbl)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        opponent = self._battle.get("opponent", "") or "Unknown Opponent"
        opp_lbl = QLabel(f"vs {opponent}")
        opp_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:11px; background:transparent; border:none;")
        row2.addWidget(opp_lbl, 1)
        pts = self._battle.get("points_played", 0)
        pts_lbl = QLabel(f"{pts}pts")
        pts_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; background:transparent; border:none;")
        row2.addWidget(pts_lbl)
        lay.addLayout(row2)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._battle)
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  Main CrusadeUI widget
# ══════════════════════════════════════════════════════════════════════════════

class CrusadeUI(QWidget):

    def __init__(self, crusade_service, oob_service, context, parent=None):
        super().__init__(parent)
        self._crusade_svc  = crusade_service
        self._oob_svc      = oob_service
        self._context      = context
        self._campaign_id: Optional[int] = None
        self._system_id    = "wh40k"
        self._force: dict  = {}
        self._selected_unit: Optional[dict] = None
        self._selected_battle: Optional[dict] = None

        # Debounce timers
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.timeout.connect(self._save_force_notes)

        self._build()
        self._apply_theme()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"background:{_BG2}; border-bottom:1px solid {_BORDER};"
        )
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(20, 0, 16, 0)
        hdr_lay.setSpacing(12)

        title_lbl = QLabel("Campaign Records")
        title_lbl.setStyleSheet(
            f"color:{_FG}; font-size:16px; font-weight:700; background:transparent;"
        )
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()

        self._system_badge = QLabel("Warhammer 40K Crusade")
        self._system_badge.setStyleSheet(
            f"color:{_FG_MID}; font-size:11px; background:transparent;"
        )
        hdr_lay.addWidget(self._system_badge)

        self._log_battle_btn = QPushButton("+ Log Battle")
        self._log_battle_btn.setObjectName("accentBtn")
        self._log_battle_btn.clicked.connect(self._on_log_battle)
        hdr_lay.addWidget(self._log_battle_btn)

        root.addWidget(header)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.setStyleSheet(
            f"QTabWidget::pane{{background:{_BG}; border:none;}}"
            f"QTabBar::tab{{background:{_BG2}; color:{_FG_MID}; padding:8px 20px;"
            f"border:none; border-bottom:2px solid transparent; font-size:12px;}}"
            f"QTabBar::tab:selected{{color:{_FG}; border-bottom:2px solid {_ACCENT}; background:{_BG};}}"
            f"QTabBar::tab:hover{{color:{_FG};}}"
        )

        self._overview_tab  = self._build_force_overview_tab()
        self._unit_tab      = self._build_unit_records_tab()
        self._battle_tab    = self._build_battle_log_tab()

        self._tabs.addTab(self._overview_tab, "🏴  Force Overview")
        self._tabs.addTab(self._unit_tab,     "🎖  Unit Records")
        self._tabs.addTab(self._battle_tab,   "⚔  Battle Log")

        root.addWidget(self._tabs, 1)

        # Empty state overlay (shown when no campaign)
        self._empty_state = QLabel("Select a campaign to view its records.")
        self._empty_state.setAlignment(Qt.AlignCenter)
        self._empty_state.setStyleSheet(
            f"color:{_FG_DIM}; font-size:14px; background:{_BG};"
        )
        root.addWidget(self._empty_state)
        self._empty_state.setVisible(False)

    # ── Tab 0: Force Overview ─────────────────────────────────────────────────

    def _build_force_overview_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 16, 20, 20)
        lay.setSpacing(16)

        # Battle stats bar
        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(12)
        self._stat_fought = _stat_card("BATTLES FOUGHT", "0")
        self._stat_won    = _stat_card("WON", "0", _SUCCESS)
        self._stat_lost   = _stat_card("LOST", "0", _DANGER)
        self._stat_drawn  = _stat_card("DRAWN", "0", _FG_MID)
        for card in (self._stat_fought, self._stat_won, self._stat_lost, self._stat_drawn):
            self._stats_row.addWidget(card, 1)
        lay.addLayout(self._stats_row)

        # Force resources row
        resources_row = QHBoxLayout()
        resources_row.setSpacing(12)

        # Left: Crusade / Glory Points
        self._cp_panel = QFrame()
        self._cp_panel.setStyleSheet(
            f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:8px;"
        )
        cp_lay = QVBoxLayout(self._cp_panel)
        cp_lay.setContentsMargins(16, 14, 16, 14)
        cp_lay.setSpacing(6)
        self._cp_title = QLabel("Crusade Points")
        self._cp_title.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; font-weight:700; letter-spacing:1px; background:transparent; border:none;")
        self._cp_big = QLabel("0")
        self._cp_big.setStyleSheet(f"color:{_GOLD}; font-size:32px; font-weight:700; background:transparent; border:none;")
        self._cp_sub = QLabel("0 earned · 0 spent")
        self._cp_sub.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none;")
        self._cp_bar = _progress_bar(0, 1, _GOLD)
        add_cp_btn = QPushButton("+ Add CP")
        add_cp_btn.setObjectName("ghostBtn")
        add_cp_btn.setFixedWidth(90)
        add_cp_btn.clicked.connect(self._on_add_cp)
        cp_lay.addWidget(self._cp_title)
        cp_lay.addWidget(self._cp_big)
        cp_lay.addWidget(self._cp_sub)
        cp_lay.addWidget(self._cp_bar)
        cp_lay.addWidget(add_cp_btn, alignment=Qt.AlignLeft)
        resources_row.addWidget(self._cp_panel, 1)

        # Right: Requisition Points (hidden for AoS/DnD)
        self._rp_panel = QFrame()
        self._rp_panel.setStyleSheet(
            f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:8px;"
        )
        rp_lay = QVBoxLayout(self._rp_panel)
        rp_lay.setContentsMargins(16, 14, 16, 14)
        rp_lay.setSpacing(6)
        rp_title = QLabel("Requisition Points")
        rp_title.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; font-weight:700; letter-spacing:1px; background:transparent; border:none;")
        self._rp_big = QLabel("5")
        self._rp_big.setStyleSheet(f"color:{_ACCENT}; font-size:32px; font-weight:700; background:transparent; border:none;")
        rp_btn_row = QHBoxLayout()
        earn_rp_btn = QPushButton("+ Earn RP")
        earn_rp_btn.setObjectName("accentBtn")
        earn_rp_btn.clicked.connect(self._on_earn_rp)
        spend_rp_btn = QPushButton("Spend RP")
        spend_rp_btn.setObjectName("ghostBtn")
        spend_rp_btn.clicked.connect(self._on_spend_rp)
        rp_btn_row.addWidget(earn_rp_btn)
        rp_btn_row.addWidget(spend_rp_btn)
        rp_btn_row.addStretch()
        rp_lay.addWidget(rp_title)
        rp_lay.addWidget(self._rp_big)
        rp_lay.addLayout(rp_btn_row)
        resources_row.addWidget(self._rp_panel, 1)

        lay.addLayout(resources_row)

        # Supply section (40K only)
        self._supply_frame = QFrame()
        self._supply_frame.setStyleSheet(
            f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:8px;"
        )
        sup_lay = QVBoxLayout(self._supply_frame)
        sup_lay.setContentsMargins(16, 12, 16, 12)
        sup_lay.setSpacing(6)
        sup_hdr = QHBoxLayout()
        self._supply_lbl = QLabel("Supply Used: 0 / 50")
        self._supply_lbl.setStyleSheet(f"color:{_FG}; font-size:13px; font-weight:600; background:transparent; border:none;")
        sup_hdr.addWidget(self._supply_lbl, 1)
        inc_sup_btn = QPushButton("Increase Supply Limit (1 RP)")
        inc_sup_btn.setObjectName("ghostBtn")
        inc_sup_btn.clicked.connect(self._on_increase_supply)
        sup_hdr.addWidget(inc_sup_btn)
        self._supply_bar = _progress_bar(0, 50, _SUCCESS)
        sup_lay.addLayout(sup_hdr)
        sup_lay.addWidget(self._supply_bar)
        lay.addWidget(self._supply_frame)

        # Requisition log
        self._req_log_frame = QFrame()
        self._req_log_frame.setStyleSheet(
            f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:8px;"
        )
        rql_lay = QVBoxLayout(self._req_log_frame)
        rql_lay.setContentsMargins(16, 12, 16, 12)
        rql_lay.setSpacing(6)
        rql_lay.addWidget(_section_header("REQUISITION LOG"))
        self._req_log_scroll = QScrollArea()
        self._req_log_scroll.setWidgetResizable(True)
        self._req_log_scroll.setFrameShape(QFrame.NoFrame)
        self._req_log_scroll.setFixedHeight(160)
        self._req_log_container = QWidget()
        self._req_log_inner = QVBoxLayout(self._req_log_container)
        self._req_log_inner.setContentsMargins(0, 0, 0, 0)
        self._req_log_inner.setSpacing(2)
        self._req_log_inner.addStretch()
        self._req_log_scroll.setWidget(self._req_log_container)
        rql_lay.addWidget(self._req_log_scroll)
        lay.addWidget(self._req_log_frame)

        # Notes section
        notes_frame = QFrame()
        notes_frame.setStyleSheet(
            f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:8px;"
        )
        notes_lay = QVBoxLayout(notes_frame)
        notes_lay.setContentsMargins(16, 12, 16, 12)
        notes_lay.setSpacing(6)
        notes_lay.addWidget(_section_header("FORCE NOTES"))
        self._force_notes = QTextEdit()
        self._force_notes.setPlaceholderText("Campaign notes, force background, objectives…")
        self._force_notes.setFixedHeight(100)
        self._force_notes.textChanged.connect(self._on_notes_changed)
        notes_lay.addWidget(self._force_notes)
        lay.addWidget(notes_frame)

        lay.addStretch()
        scroll.setWidget(w)
        return scroll

    # ── Tab 1: Unit Records ───────────────────────────────────────────────────

    def _build_unit_records_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            f"QSplitter::handle {{background:{_BORDER};}}"
        )

        # Left: unit list
        left = QWidget()
        left.setMinimumWidth(280)
        left.setMaximumWidth(320)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        list_header = QFrame()
        list_header.setStyleSheet(f"background:{_BG2}; border-bottom:1px solid {_BORDER};")
        list_header.setFixedHeight(40)
        lh_lay = QHBoxLayout(list_header)
        lh_lay.setContentsMargins(12, 0, 8, 0)
        lh_lay.addWidget(QLabel("Units"))
        lh_lay.addStretch()
        left_lay.addWidget(list_header)

        unit_scroll = QScrollArea()
        unit_scroll.setWidgetResizable(True)
        unit_scroll.setFrameShape(QFrame.NoFrame)
        self._unit_list_container = QWidget()
        self._unit_list_inner = QVBoxLayout(self._unit_list_container)
        self._unit_list_inner.setContentsMargins(8, 8, 8, 8)
        self._unit_list_inner.setSpacing(6)
        self._unit_list_inner.addStretch()
        unit_scroll.setWidget(self._unit_list_container)
        left_lay.addWidget(unit_scroll, 1)

        splitter.addWidget(left)

        # Right: unit crusade card
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        self._unit_card_widget = QWidget()
        self._unit_card_lay = QVBoxLayout(self._unit_card_widget)
        self._unit_card_lay.setContentsMargins(20, 16, 20, 20)
        self._unit_card_lay.setSpacing(0)
        self._unit_empty_lbl = QLabel("Select a unit to view its Crusade record.")
        self._unit_empty_lbl.setAlignment(Qt.AlignCenter)
        self._unit_empty_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:13px;")
        self._unit_card_lay.addWidget(self._unit_empty_lbl)
        self._unit_card_lay.addStretch()
        right_scroll.setWidget(self._unit_card_widget)
        splitter.addWidget(right_scroll)

        splitter.setSizes([290, 600])
        return splitter

    # ── Tab 2: Battle Log ─────────────────────────────────────────────────────

    def _build_battle_log_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            f"QSplitter::handle {{background:{_BORDER};}}"
        )

        # Left: battle list
        left = QWidget()
        left.setMinimumWidth(280)
        left.setMaximumWidth(320)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        list_header = QFrame()
        list_header.setStyleSheet(f"background:{_BG2}; border-bottom:1px solid {_BORDER};")
        list_header.setFixedHeight(40)
        lh_lay = QHBoxLayout(list_header)
        lh_lay.setContentsMargins(12, 0, 8, 0)
        lh_lay.addWidget(QLabel("Battles"))
        lh_lay.addStretch()
        log_btn = QPushButton("+ Log")
        log_btn.setObjectName("accentBtn")
        log_btn.setFixedHeight(26)
        log_btn.clicked.connect(self._on_log_battle)
        lh_lay.addWidget(log_btn)
        left_lay.addWidget(list_header)

        battle_scroll = QScrollArea()
        battle_scroll.setWidgetResizable(True)
        battle_scroll.setFrameShape(QFrame.NoFrame)
        self._battle_list_container = QWidget()
        self._battle_list_inner = QVBoxLayout(self._battle_list_container)
        self._battle_list_inner.setContentsMargins(8, 8, 8, 8)
        self._battle_list_inner.setSpacing(6)
        self._battle_list_inner.addStretch()
        battle_scroll.setWidget(self._battle_list_container)
        left_lay.addWidget(battle_scroll, 1)

        splitter.addWidget(left)

        # Right: battle detail
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        self._battle_detail_widget = QWidget()
        self._battle_detail_lay = QVBoxLayout(self._battle_detail_widget)
        self._battle_detail_lay.setContentsMargins(20, 16, 20, 20)
        self._battle_detail_lay.setSpacing(0)
        self._battle_empty_lbl = QLabel("Select a battle to view its details.")
        self._battle_empty_lbl.setAlignment(Qt.AlignCenter)
        self._battle_empty_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:13px;")
        self._battle_detail_lay.addWidget(self._battle_empty_lbl)
        self._battle_detail_lay.addStretch()
        right_scroll.setWidget(self._battle_detail_widget)
        splitter.addWidget(right_scroll)

        splitter.setSizes([290, 600])
        return splitter

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, campaign_id: Optional[int] = None):
        self._campaign_id = campaign_id
        if campaign_id is None:
            self._show_no_campaign()
            return
        self._tabs.setVisible(True)
        self._log_battle_btn.setVisible(True)
        self._empty_state.setVisible(False)

        try:
            self._force = self._crusade_svc.get_or_create_force(campaign_id)
        except Exception as e:
            log.error(f"[CRUSADE UI] get_or_create_force: {e}")
            self._force = {}

        self._system_id = self._force.get("system_id", "wh40k")
        self._update_system_badge()
        self._refresh_overview(self._force)
        self._refresh_unit_records()
        self._refresh_battle_log()

    def _show_no_campaign(self):
        self._tabs.setVisible(False)
        self._log_battle_btn.setVisible(False)
        self._empty_state.setVisible(True)

    # ── Overview refresh ──────────────────────────────────────────────────────

    def _refresh_overview(self, force: dict):
        # Battle stats
        self._update_stat_card(self._stat_fought, str(force.get("battles_fought", 0)))
        self._update_stat_card(self._stat_won,    str(force.get("battles_won", 0)))
        self._update_stat_card(self._stat_lost,   str(force.get("battles_lost", 0)))
        self._update_stat_card(self._stat_drawn,  str(force.get("battles_drawn", 0)))

        # CP
        cp_earned = force.get("crusade_points_earned", 0)
        cp_spent  = force.get("crusade_points_spent", 0)
        cp_net    = cp_earned - cp_spent
        self._cp_big.setText(str(cp_net))
        self._cp_sub.setText(f"{cp_earned} earned · {cp_spent} spent")
        if cp_earned > 0:
            self._cp_bar.setMaximum(cp_earned)
            self._cp_bar.setValue(cp_earned - cp_spent)

        # RP
        rp = force.get("requisition_points", 0)
        self._rp_big.setText(str(rp))

        # Supply
        supply_limit = force.get("supply_limit", 50)
        oob_units = []
        try:
            oob_units = self._oob_svc.get_order_of_battle(self._campaign_id) or []
        except Exception:
            pass
        supply_used = sum(
            int(u.get("supply_used", 1)) * int(u.get("quantity", 1))
            for u in oob_units
        )
        self._supply_lbl.setText(f"Supply Used: {supply_used} / {supply_limit}")
        self._supply_bar.setMaximum(max(supply_limit, 1))
        self._supply_bar.setValue(min(supply_used, supply_limit))

        # Supply bar color
        ratio = supply_used / max(supply_limit, 1)
        bar_color = _SUCCESS if ratio < 0.8 else (_WARN if ratio < 1.0 else _DANGER)
        self._supply_bar.setStyleSheet(
            f"QProgressBar {{background:{_BG3}; border-radius:3px; border:none;}}"
            f"QProgressBar::chunk {{background:{bar_color}; border-radius:3px;}}"
        )

        # System visibility
        is_40k = self._system_id in ("wh40k", "wh30k", "custom")
        self._rp_panel.setVisible(is_40k)
        self._supply_frame.setVisible(is_40k)
        self._req_log_frame.setVisible(is_40k)

        # CP title for system
        if self._system_id == "aos":
            self._cp_title.setText("GLORY POINTS")
        else:
            self._cp_title.setText("CRUSADE POINTS")

        # Requisition log
        self._refresh_req_log()

        # Notes (block signal to avoid re-triggering save)
        self._notes_timer.stop()
        prev = self._force_notes.blockSignals(True)
        self._force_notes.setPlainText(force.get("notes", ""))
        self._force_notes.blockSignals(prev)

    def _update_stat_card(self, card: QFrame, value: str):
        labels = card.findChildren(QLabel)
        if labels:
            labels[0].setText(value)

    def _refresh_req_log(self):
        # Clear old items
        while self._req_log_inner.count() > 1:
            item = self._req_log_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            entries = self._crusade_svc.get_requisition_log(self._campaign_id) or []
        except Exception:
            entries = []

        for entry in entries:
            rp_change = entry.get("rp_change", 0)
            action    = entry.get("action", "")
            desc      = entry.get("description", "")
            log_date  = entry.get("log_date", "")
            color     = _SUCCESS if rp_change > 0 else _WARN
            sign      = "+" if rp_change > 0 else ""
            text      = f"{log_date}  |  {action}  |  {sign}{rp_change} RP"
            if desc:
                text += f"  —  {desc}"
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color:{color}; font-size:11px; background:transparent; border:none; "
                f"padding:2px 0;"
            )
            self._req_log_inner.insertWidget(self._req_log_inner.count() - 1, lbl)

        if not entries:
            placeholder = QLabel("No requisition transactions yet.")
            placeholder.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none;")
            self._req_log_inner.insertWidget(0, placeholder)

    # ── Unit records refresh ──────────────────────────────────────────────────

    def _refresh_unit_records(self):
        # Clear old cards
        while self._unit_list_inner.count() > 1:
            item = self._unit_list_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            # Get all OoB entries, then get/create crusade records for each
            oob_entries = self._oob_svc.get_order_of_battle(self._campaign_id) or []
        except Exception as e:
            log.error(f"[CRUSADE UI] get_order_of_battle: {e}")
            oob_entries = []

        # Merge OoB info with crusade records
        units = []
        for oob in oob_entries:
            try:
                record = self._crusade_svc.get_unit_crusade_record(oob["id"])
            except Exception:
                record = {}
            merged = dict(record)
            merged["custom_name"] = oob.get("custom_name", "")
            merged["unit_role"]   = oob.get("unit_role", "")
            merged["faction"]     = oob.get("faction", "")
            merged["points_cost"] = oob.get("points_cost", 0)
            merged["oob_entry_id"] = oob["id"]
            units.append(merged)

        # Sort by crusade_points desc
        units.sort(key=lambda u: (u.get("crusade_points", 0), u.get("experience_points", 0)), reverse=True)

        for unit in units:
            card = _UnitListCard(unit)
            card.clicked.connect(self._show_unit_card)
            self._unit_list_inner.insertWidget(self._unit_list_inner.count() - 1, card)

        # Restore selected unit if possible
        if self._selected_unit:
            for unit in units:
                if unit.get("oob_entry_id") == self._selected_unit.get("oob_entry_id"):
                    self._show_unit_card(unit)
                    return

        # Show empty state in card panel
        self._clear_unit_card()

    def _clear_unit_card(self):
        while self._unit_card_lay.count() > 0:
            item = self._unit_card_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._unit_card_lay.addWidget(self._unit_empty_lbl)
        self._unit_card_lay.addStretch()
        self._unit_empty_lbl.setVisible(True)
        self._selected_unit = None

    def _show_unit_card(self, unit: dict):
        self._selected_unit = unit
        # Clear current card
        while self._unit_card_lay.count() > 0:
            item = self._unit_card_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._unit_empty_lbl.setVisible(False)

        oob_id   = unit.get("oob_entry_id", 0)
        xp       = unit.get("experience_points", 0)
        name     = unit.get("custom_name") or "Unknown Unit"
        is_ooa   = unit.get("is_out_of_action", False)
        honours  = unit.get("honours_json", [])
        scars    = unit.get("scars_json", [])
        is_warlord = unit.get("is_warlord", False)

        rank_name, honour_slots, rank_min, next_thresh = _get_rank_info(xp)

        # Out of Action banner
        if is_ooa:
            ooa_banner = QLabel("  OUT OF ACTION")
            ooa_banner.setFixedHeight(32)
            ooa_banner.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            ooa_banner.setStyleSheet(
                f"background:{_DANGER}30; color:{_DANGER}; font-size:11px; "
                f"font-weight:700; border:1px solid {_DANGER}60; border-radius:4px; "
                f"padding-left:8px;"
            )
            self._unit_card_lay.addWidget(ooa_banner)
            self._unit_card_lay.addSpacing(8)

        # Unit name header
        name_row = QHBoxLayout()
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color:{'#606060' if is_ooa else _FG}; font-size:18px; font-weight:700; "
            f"background:transparent; border:none; "
            f"{'text-decoration:line-through;' if is_ooa else ''}"
        )
        name_row.addWidget(name_lbl, 1)
        ooa_check = QCheckBox("Out of Action")
        ooa_check.setChecked(is_ooa)
        ooa_check.stateChanged.connect(
            lambda state, eid=oob_id: self._on_ooa_toggled(eid, bool(state))
        )
        name_row.addWidget(ooa_check)
        self._unit_card_lay.addLayout(name_row)

        role_lbl = QLabel(f"{unit.get('unit_role', '')}  ·  {unit.get('faction', '')}")
        role_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none;")
        self._unit_card_lay.addWidget(role_lbl)
        self._unit_card_lay.addSpacing(16)
        self._unit_card_lay.addWidget(_h_line())

        # Experience section
        self._unit_card_lay.addWidget(_section_header("EXPERIENCE"))
        xp_frame = QFrame()
        xp_frame.setStyleSheet(f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;")
        xp_lay = QVBoxLayout(xp_frame)
        xp_lay.setContentsMargins(12, 10, 12, 10)
        xp_lay.setSpacing(8)

        # Rank + XP row
        rank_row = QHBoxLayout()
        rank_badge = QLabel(rank_name.upper())
        rank_badge.setStyleSheet(
            f"color:{_rank_color(rank_name)}; font-size:11px; font-weight:700; "
            f"letter-spacing:1px; background:{_rank_color(rank_name)}20; "
            f"border:1px solid {_rank_color(rank_name)}60; border-radius:3px; "
            f"padding:2px 8px;"
        )
        rank_row.addWidget(rank_badge)

        xp_pb_label = QLabel(f"XP: {xp}")
        xp_pb_label.setStyleSheet(f"color:{_FG_MID}; font-size:11px; background:transparent; border:none;")
        rank_row.addWidget(xp_pb_label)

        if next_thresh > rank_min:
            bar_val = xp - rank_min
            bar_max = next_thresh - rank_min
            xp_bar = _progress_bar(bar_val, bar_max, _rank_color(rank_name))
            xp_bar.setFixedWidth(100)
            rank_row.addWidget(xp_bar)
            # Next rank name
            next_rank_name = "Max"
            for thresh, name, _slots in XP_RANKS:
                if thresh == next_thresh:
                    next_rank_name = name
                    break
            toward = QLabel(f"{bar_val}/{bar_max} → {next_rank_name}")
            toward.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; background:transparent; border:none;")
            rank_row.addWidget(toward)
        rank_row.addStretch()
        xp_lay.addLayout(rank_row)

        # Stats row
        stats_row = QHBoxLayout()
        cp_val = unit.get("crusade_points", 0)
        bf_val = unit.get("battles_fought", 0)
        td_val = unit.get("times_destroyed", 0)
        for label, val in [
            ("Crusade Points", str(cp_val)),
            ("Battles", str(bf_val)),
            ("Destroyed", str(td_val)),
        ]:
            col = QVBoxLayout()
            v = QLabel(val)
            v.setStyleSheet(f"color:{_FG}; font-size:16px; font-weight:700; background:transparent; border:none;")
            l = QLabel(label)
            l.setStyleSheet(f"color:{_FG_DIM}; font-size:9px; font-weight:600; letter-spacing:1px; background:transparent; border:none;")
            col.addWidget(v)
            col.addWidget(l)
            stats_row.addLayout(col)
        stats_row.addStretch()
        xp_lay.addLayout(stats_row)

        # XP buttons
        xp_btn_row = QHBoxLayout()
        for label, amount in [("+ 1 XP", 1), ("+ 4 XP", 4)]:
            btn = QPushButton(label)
            btn.setObjectName("ghostBtn")
            btn.setFixedHeight(28)
            btn.clicked.connect(
                lambda _, eid=oob_id, amt=amount: self._on_add_xp(eid, amt)
            )
            xp_btn_row.addWidget(btn)
        custom_xp_btn = QPushButton("Custom XP")
        custom_xp_btn.setObjectName("ghostBtn")
        custom_xp_btn.setFixedHeight(28)
        custom_xp_btn.clicked.connect(lambda _, eid=oob_id: self._on_custom_xp(eid))
        xp_btn_row.addWidget(custom_xp_btn)
        xp_btn_row.addStretch()
        xp_lay.addLayout(xp_btn_row)

        self._unit_card_lay.addWidget(xp_frame)
        self._unit_card_lay.addSpacing(16)
        self._unit_card_lay.addWidget(_h_line())

        # Battle Honours
        slots_used = len(honours)
        slots_available = honour_slots
        slots_full = slots_used >= slots_available and slots_available > 0

        hon_hdr_row = QHBoxLayout()
        hon_hdr_lbl = QLabel(
            f"BATTLE HONOURS  ({slots_used}/{max(slots_available, 0)} slots used)"
        )
        hon_hdr_lbl.setStyleSheet(
            f"color:{_WARN if slots_full else _FG_DIM}; font-size:10px; font-weight:700; "
            f"letter-spacing:2px; background:transparent; border:none; "
            f"padding-top:12px; padding-bottom:4px;"
        )
        hon_hdr_row.addWidget(hon_hdr_lbl, 1)
        add_hon_btn = QPushButton("+ Add Honour")
        add_hon_btn.setObjectName("ghostBtn")
        add_hon_btn.setFixedHeight(26)
        add_hon_btn.setEnabled(not slots_full or slots_available == 0)
        add_hon_btn.clicked.connect(lambda _, eid=oob_id: self._on_add_honour(eid))
        hon_hdr_row.addWidget(add_hon_btn)
        self._unit_card_lay.addLayout(hon_hdr_row)

        if slots_full:
            warn_lbl = QLabel("Honour slot limit reached.")
            warn_lbl.setStyleSheet(
                f"color:{_WARN}; font-size:10px; background:{_WARN}10; "
                f"border:1px solid {_WARN}40; border-radius:3px; padding:3px 8px;"
            )
            self._unit_card_lay.addWidget(warn_lbl)

        for idx, honour in enumerate(honours):
            h_frame = self._build_honour_card(honour, idx, oob_id, is_honour=True)
            self._unit_card_lay.addWidget(h_frame)

        if not honours:
            no_hon = QLabel("No battle honours yet.")
            no_hon.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none; padding:4px 0;")
            self._unit_card_lay.addWidget(no_hon)

        self._unit_card_lay.addSpacing(16)
        self._unit_card_lay.addWidget(_h_line())

        # Battle Scars
        scar_hdr_row = QHBoxLayout()
        scar_hdr_lbl = QLabel("BATTLE SCARS")
        scar_hdr_lbl.setStyleSheet(
            f"color:{_FG_DIM}; font-size:10px; font-weight:700; letter-spacing:2px; "
            f"background:transparent; border:none; padding-top:12px; padding-bottom:4px;"
        )
        scar_hdr_row.addWidget(scar_hdr_lbl, 1)
        add_scar_btn = QPushButton("+ Add Scar")
        add_scar_btn.setObjectName("dangerBtn")
        add_scar_btn.setFixedHeight(26)
        add_scar_btn.clicked.connect(lambda _, eid=oob_id: self._on_add_scar(eid))
        scar_hdr_row.addWidget(add_scar_btn)
        self._unit_card_lay.addLayout(scar_hdr_row)

        for idx, scar in enumerate(scars):
            s_frame = self._build_honour_card(scar, idx, oob_id, is_honour=False)
            self._unit_card_lay.addWidget(s_frame)

        if not scars:
            no_scar = QLabel("No battle scars.")
            no_scar.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none; padding:4px 0;")
            self._unit_card_lay.addWidget(no_scar)

        self._unit_card_lay.addSpacing(16)
        self._unit_card_lay.addWidget(_h_line())

        # Warlord section
        self._unit_card_lay.addWidget(_section_header("WARLORD"))
        wl_frame = QFrame()
        wl_frame.setStyleSheet(f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;")
        wl_lay = QVBoxLayout(wl_frame)
        wl_lay.setContentsMargins(12, 10, 12, 10)
        wl_lay.setSpacing(8)

        wl_row = QHBoxLayout()
        wl_check = QCheckBox("Mark as Warlord")
        wl_check.setChecked(is_warlord)
        wl_check.stateChanged.connect(
            lambda state, eid=oob_id: self._on_warlord_toggled(eid, bool(state))
        )
        wl_row.addWidget(wl_check)
        wl_row.addStretch()
        wl_lay.addLayout(wl_row)

        leg_form = QFormLayout()
        leg_form.setSpacing(6)
        leg_name_edit = QLineEdit(unit.get("legendary_name", ""))
        leg_name_edit.setPlaceholderText("e.g. The Undying")
        leg_name_edit.editingFinished.connect(
            lambda eid=oob_id, w=leg_name_edit: self._on_legendary_name_changed(eid, w.text())
        )
        wl_trait_edit = QLineEdit(unit.get("warlord_trait", ""))
        wl_trait_edit.setPlaceholderText("e.g. Tenacious Survivor")
        wl_trait_edit.editingFinished.connect(
            lambda eid=oob_id, w=wl_trait_edit: self._on_warlord_trait_changed(eid, w.text())
        )
        leg_form.addRow("Legendary Name", leg_name_edit)
        leg_form.addRow("Warlord Trait",  wl_trait_edit)
        wl_lay.addLayout(leg_form)
        self._unit_card_lay.addWidget(wl_frame)

        self._unit_card_lay.addSpacing(16)
        self._unit_card_lay.addWidget(_h_line())

        # Notes
        self._unit_card_lay.addWidget(_section_header("NOTES"))
        unit_notes = QTextEdit(unit.get("notes", ""))
        unit_notes.setPlaceholderText("Unit notes, background, special rules…")
        unit_notes.setFixedHeight(80)

        _unit_notes_timer = QTimer(self)
        _unit_notes_timer.setSingleShot(True)
        _unit_notes_timer.timeout.connect(
            lambda eid=oob_id, w=unit_notes: self._save_unit_notes(eid, w.text() if hasattr(w, 'text') else w.toPlainText())
        )
        unit_notes.textChanged.connect(
            lambda t=_unit_notes_timer: (t.stop(), t.start(800))
        )
        self._unit_card_lay.addWidget(unit_notes)

        self._unit_card_lay.addStretch()

    def _build_honour_card(self, item: dict, idx: int, oob_id: int, is_honour: bool) -> QFrame:
        f = QFrame()
        border_color = _ACCENT if is_honour else _DANGER
        f.setStyleSheet(
            f"QFrame {{background:{_BG2}; border:1px solid {border_color}40; border-radius:6px; margin-top:4px;}}"
        )
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        type_lbl = QLabel(item.get("type", ""))
        type_lbl.setStyleSheet(f"color:{border_color}; font-size:9px; font-weight:700; letter-spacing:1px; background:transparent; border:none;")
        hdr.addWidget(type_lbl)
        hdr.addStretch()
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setStyleSheet(
            f"QPushButton {{background:transparent; color:{_FG_DIM}; border:none; font-size:11px;}}"
            f"QPushButton:hover {{color:{_DANGER};}}"
        )
        if is_honour:
            remove_btn.clicked.connect(lambda _, eid=oob_id, i=idx: self._on_remove_honour(eid, i))
        else:
            remove_btn.clicked.connect(lambda _, eid=oob_id, i=idx: self._on_remove_scar(eid, i))
        hdr.addWidget(remove_btn)
        lay.addLayout(hdr)

        name_lbl = QLabel(item.get("name", ""))
        name_lbl.setStyleSheet(f"color:{_FG}; font-size:12px; font-weight:600; background:transparent; border:none;")
        lay.addWidget(name_lbl)

        effect = item.get("effect", "")
        if effect:
            effect_lbl = QLabel(effect)
            effect_lbl.setWordWrap(True)
            effect_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:11px; background:transparent; border:none;")
            lay.addWidget(effect_lbl)

        return f

    # ── Battle log refresh ────────────────────────────────────────────────────

    def _refresh_battle_log(self):
        while self._battle_list_inner.count() > 1:
            item = self._battle_list_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            battles = self._crusade_svc.get_battles(self._campaign_id) or []
        except Exception as e:
            log.error(f"[CRUSADE UI] get_battles: {e}")
            battles = []

        for battle in battles:
            card = _BattleListCard(battle)
            card.clicked.connect(self._show_battle_detail)
            self._battle_list_inner.insertWidget(self._battle_list_inner.count() - 1, card)

        if self._selected_battle:
            for battle in battles:
                if battle.get("id") == self._selected_battle.get("id"):
                    self._show_battle_detail(battle)
                    return

        self._clear_battle_detail()

    def _clear_battle_detail(self):
        while self._battle_detail_lay.count() > 0:
            item = self._battle_detail_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._battle_detail_lay.addWidget(self._battle_empty_lbl)
        self._battle_detail_lay.addStretch()
        self._battle_empty_lbl.setVisible(True)
        self._selected_battle = None

    def _show_battle_detail(self, battle: dict):
        self._selected_battle = battle
        while self._battle_detail_lay.count() > 0:
            item = self._battle_detail_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._battle_empty_lbl.setVisible(False)

        battle_id = battle.get("id", 0)
        result    = battle.get("result", "Draw")
        result_color = {
            "Victory": _SUCCESS,
            "Defeat":  _DANGER,
            "Draw":    _FG_MID,
        }.get(result, _FG_MID)

        # Header
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet(f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:8px;")
        hdr_lay = QVBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(16, 14, 16, 14)
        hdr_lay.setSpacing(6)

        top_row = QHBoxLayout()
        result_badge = QLabel(f"  {result.upper()}  ")
        result_badge.setStyleSheet(
            f"background:{result_color}30; color:{result_color}; "
            f"font-size:12px; font-weight:700; border:1px solid {result_color}80; "
            f"border-radius:4px; padding:2px 6px;"
        )
        top_row.addWidget(result_badge)
        date_lbl = QLabel(battle.get("battle_date", ""))
        date_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:11px; background:transparent; border:none;")
        top_row.addWidget(date_lbl)
        top_row.addStretch()
        pts_lbl = QLabel(f"{battle.get('points_played', 0)} pts")
        pts_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none;")
        top_row.addWidget(pts_lbl)
        hdr_lay.addLayout(top_row)

        mission_lbl = QLabel(battle.get("mission", "") or "Unknown Mission")
        mission_lbl.setStyleSheet(f"color:{_FG}; font-size:16px; font-weight:700; background:transparent; border:none;")
        hdr_lay.addWidget(mission_lbl)

        opp_lbl = QLabel(f"vs  {battle.get('opponent', '') or 'Unknown Opponent'}")
        opp_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:12px; background:transparent; border:none;")
        hdr_lay.addWidget(opp_lbl)

        vp_row = QHBoxLayout()
        vp_us   = battle.get("vp_scored", 0)
        vp_them = battle.get("vp_opponent", 0)
        vp_lbl  = QLabel(f"VP  {vp_us}  —  {vp_them}")
        vp_lbl.setStyleSheet(f"color:{_GOLD}; font-size:13px; font-weight:600; background:transparent; border:none;")
        vp_row.addWidget(vp_lbl)
        vp_row.addStretch()
        hdr_lay.addLayout(vp_row)

        self._battle_detail_lay.addWidget(hdr_frame)

        # Participating units
        self._battle_detail_lay.addWidget(_section_header("PARTICIPATING UNITS"))
        units_data = battle.get("units_json", [])
        if isinstance(units_data, list) and units_data:
            try:
                oob_entries = self._oob_svc.get_order_of_battle(self._campaign_id) or []
                oob_map = {e["id"]: e for e in oob_entries}
            except Exception:
                oob_map = {}

            for uid in units_data:
                oob_entry = oob_map.get(uid, {})
                unit_name = oob_entry.get("custom_name", f"Unit #{uid}")
                unit_row = QHBoxLayout()
                u_lbl = QLabel(f"• {unit_name}")
                u_lbl.setStyleSheet(f"color:{_FG}; font-size:12px; background:transparent; border:none;")
                unit_row.addWidget(u_lbl, 1)
                xp_btn = QPushButton("+ XP")
                xp_btn.setObjectName("ghostBtn")
                xp_btn.setFixedHeight(24)
                xp_btn.setFixedWidth(50)
                xp_btn.clicked.connect(
                    lambda _, eid=uid: self._on_add_xp(eid, 4)
                )
                unit_row.addWidget(xp_btn)
                self._battle_detail_lay.addLayout(unit_row)
        else:
            no_units = QLabel("No units recorded for this battle.")
            no_units.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none;")
            self._battle_detail_lay.addWidget(no_units)

        # Honours awarded
        honours_data = battle.get("honours_awarded", [])
        if honours_data:
            self._battle_detail_lay.addWidget(_section_header("HONOURS AWARDED"))
            for hon in honours_data:
                hon_lbl = QLabel(f"• {hon}")
                hon_lbl.setStyleSheet(f"color:{_GOLD}; font-size:11px; background:transparent; border:none;")
                self._battle_detail_lay.addWidget(hon_lbl)

        # Narrative
        narrative = battle.get("narrative_notes", "")
        if narrative:
            self._battle_detail_lay.addWidget(_section_header("BATTLE NARRATIVE"))
            narr_frame = QFrame()
            narr_frame.setStyleSheet(f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;")
            narr_lay = QVBoxLayout(narr_frame)
            narr_lay.setContentsMargins(12, 10, 12, 10)
            narr_lbl = QLabel(narrative)
            narr_lbl.setWordWrap(True)
            narr_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:12px; background:transparent; border:none; line-height:1.5;")
            narr_lay.addWidget(narr_lbl)
            self._battle_detail_lay.addWidget(narr_frame)

        # Edit + Delete buttons
        self._battle_detail_lay.addSpacing(16)
        btn_row = QHBoxLayout()
        edit_btn = QPushButton("Edit Battle")
        edit_btn.setObjectName("ghostBtn")
        edit_btn.clicked.connect(lambda _, bid=battle_id: self._on_edit_battle(bid))
        del_btn = QPushButton("Delete Battle")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(lambda _, bid=battle_id: self._on_delete_battle(bid))
        btn_row.addWidget(edit_btn)
        btn_row.addStretch()
        btn_row.addWidget(del_btn)
        self._battle_detail_lay.addLayout(btn_row)
        self._battle_detail_lay.addStretch()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _update_system_badge(self):
        labels = {
            "wh40k":  "Warhammer 40K Crusade",
            "wh30k":  "Horus Heresy Crusade",
            "aos":    "Age of Sigmar Path to Glory",
            "dnd5e":  "D&D 5e Campaign",
            "pf2e":   "Pathfinder 2e Campaign",
            "custom": "Custom Campaign",
        }
        text = labels.get(self._system_id, "Campaign Records")
        self._system_badge.setText(text)

    def _on_notes_changed(self):
        self._notes_timer.stop()
        self._notes_timer.start(800)

    def _save_force_notes(self):
        if not self._campaign_id:
            return
        try:
            text = self._force_notes.toPlainText()
            self._crusade_svc.update_crusade_force(self._campaign_id, notes=text)
        except Exception as e:
            log.error(f"[CRUSADE UI] save_force_notes: {e}")

    def _save_unit_notes(self, oob_id: int, text: str):
        try:
            self._crusade_svc.update_unit_crusade_record(oob_id, notes=text)
        except Exception as e:
            log.error(f"[CRUSADE UI] save_unit_notes: {e}")

    def _on_add_cp(self):
        if not self._campaign_id:
            return
        val, ok = QInputDialog.getInt(
            self, "Add Crusade Points", "Points to add:", 1, 0, 100
        )
        if ok and val > 0:
            current_cp = self._force.get("crusade_points_earned", 0)
            try:
                self._crusade_svc.update_crusade_force(
                    self._campaign_id,
                    crusade_points_earned=current_cp + val,
                )
            except Exception as e:
                log.error(f"[CRUSADE UI] add_cp: {e}")
            self.refresh(self._campaign_id)

    def _on_earn_rp(self):
        if not self._campaign_id:
            return
        dlg = _EarnRequisitionDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.result_data()
            try:
                self._crusade_svc.add_requisition(
                    self._campaign_id, data["amount"],
                    "Earn RP", data["reason"],
                )
            except Exception as e:
                log.error(f"[CRUSADE UI] earn_rp: {e}")
            self.refresh(self._campaign_id)

    def _on_spend_rp(self):
        if not self._campaign_id:
            return
        rp = self._force.get("requisition_points", 0)
        dlg = _SpendRequisitionDialog(rp, self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.result_data()
            if not data:
                return
            action = data["action"]
            cost   = data["cost"]
            desc   = data["description"]
            try:
                if action == "Earn RP":
                    self._crusade_svc.add_requisition(
                        self._campaign_id, cost, action, desc
                    )
                else:
                    ok = self._crusade_svc.spend_requisition(
                        self._campaign_id, cost, action, desc
                    )
                    if not ok:
                        QMessageBox.warning(self, "Insufficient RP", "Not enough Requisition Points.")
                    elif action == "Increase Supply Limit":
                        # Also increase supply limit
                        new_limit = self._force.get("supply_limit", 50) + 5
                        self._crusade_svc.update_crusade_force(
                            self._campaign_id, supply_limit=new_limit
                        )
            except Exception as e:
                log.error(f"[CRUSADE UI] spend_rp: {e}")
            self.refresh(self._campaign_id)

    def _on_increase_supply(self):
        if not self._campaign_id:
            return
        rp = self._force.get("requisition_points", 0)
        if rp < 1:
            QMessageBox.warning(self, "Insufficient RP", "Increasing Supply Limit costs 1 RP.")
            return
        reply = QMessageBox.question(
            self, "Increase Supply Limit",
            "Spend 1 RP to increase your Supply Limit by 5?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                ok = self._crusade_svc.spend_requisition(
                    self._campaign_id, 1, "Increase Supply Limit",
                    "Supply Limit +5"
                )
                if ok:
                    new_limit = self._force.get("supply_limit", 50) + 5
                    self._crusade_svc.update_crusade_force(
                        self._campaign_id, supply_limit=new_limit
                    )
            except Exception as e:
                log.error(f"[CRUSADE UI] increase_supply: {e}")
            self.refresh(self._campaign_id)

    def _on_add_xp(self, oob_id: int, amount: int):
        try:
            self._crusade_svc.add_unit_experience(oob_id, amount)
        except Exception as e:
            log.error(f"[CRUSADE UI] add_xp: {e}")
        self._refresh_unit_records()

    def _on_custom_xp(self, oob_id: int):
        val, ok = QInputDialog.getInt(self, "Add Experience", "XP to add:", 1, 1, 100)
        if ok and val > 0:
            self._on_add_xp(oob_id, val)

    def _on_ooa_toggled(self, oob_id: int, is_ooa: bool):
        try:
            self._crusade_svc.update_unit_crusade_record(oob_id, is_out_of_action=int(is_ooa))
        except Exception as e:
            log.error(f"[CRUSADE UI] ooa_toggled: {e}")
        self._refresh_unit_records()

    def _on_warlord_toggled(self, oob_id: int, is_warlord: bool):
        try:
            self._crusade_svc.update_unit_crusade_record(oob_id, is_warlord=int(is_warlord))
        except Exception as e:
            log.error(f"[CRUSADE UI] warlord_toggled: {e}")

    def _on_legendary_name_changed(self, oob_id: int, name: str):
        try:
            self._crusade_svc.update_unit_crusade_record(oob_id, legendary_name=name)
        except Exception as e:
            log.error(f"[CRUSADE UI] legendary_name: {e}")

    def _on_warlord_trait_changed(self, oob_id: int, trait: str):
        try:
            self._crusade_svc.update_unit_crusade_record(oob_id, warlord_trait=trait)
        except Exception as e:
            log.error(f"[CRUSADE UI] warlord_trait: {e}")

    def _on_add_honour(self, oob_id: int):
        dlg = _AddHonourDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.result_data()
            try:
                self._crusade_svc.add_unit_honour(
                    oob_id, data["type"], data["name"], data["effect"]
                )
            except Exception as e:
                log.error(f"[CRUSADE UI] add_honour: {e}")
            self._refresh_unit_records()

    def _on_remove_honour(self, oob_id: int, index: int):
        reply = QMessageBox.question(
            self, "Remove Honour",
            "Remove this Battle Honour?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                self._crusade_svc.remove_unit_honour(oob_id, index)
            except Exception as e:
                log.error(f"[CRUSADE UI] remove_honour: {e}")
            self._refresh_unit_records()

    def _on_add_scar(self, oob_id: int):
        dlg = _AddScarDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.result_data()
            try:
                self._crusade_svc.add_unit_scar(
                    oob_id, data["type"], data["name"], data["effect"]
                )
            except Exception as e:
                log.error(f"[CRUSADE UI] add_scar: {e}")
            self._refresh_unit_records()

    def _on_remove_scar(self, oob_id: int, index: int):
        reply = QMessageBox.question(
            self, "Remove Scar",
            "Remove this Battle Scar?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                self._crusade_svc.remove_unit_scar(oob_id, index)
            except Exception as e:
                log.error(f"[CRUSADE UI] remove_scar: {e}")
            self._refresh_unit_records()

    def _on_log_battle(self):
        if not self._campaign_id:
            return
        try:
            oob_units = self._oob_svc.get_order_of_battle(self._campaign_id) or []
        except Exception:
            oob_units = []

        dlg = _LogBattleDialog(oob_units, self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.result_data()
            try:
                self._crusade_svc.add_battle(self._campaign_id, **data)
            except Exception as e:
                log.error(f"[CRUSADE UI] log_battle: {e}")
                return

            # Offer XP grant
            participating_ids = json.loads(data.get("units_json", "[]"))
            if participating_ids:
                reply = QMessageBox.question(
                    self, "Grant Experience",
                    "Grant +4 XP to all participating units?\n"
                    "(+4 XP each is standard for a battle survived)",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                )
                if reply == QMessageBox.Yes:
                    for uid in participating_ids:
                        try:
                            self._crusade_svc.add_unit_experience(uid, 4)
                        except Exception as e:
                            log.error(f"[CRUSADE UI] post-battle xp: {e}")
                elif reply == QMessageBox.No:
                    # Custom XP per unit
                    custom_reply = QMessageBox.question(
                        self, "Custom XP",
                        "Assign custom XP amounts instead?",
                        QMessageBox.Yes | QMessageBox.No,
                    )
                    if custom_reply == QMessageBox.Yes:
                        oob_map = {e["id"]: e for e in oob_units}
                        for uid in participating_ids:
                            unit_name = oob_map.get(uid, {}).get("custom_name", f"Unit #{uid}")
                            xp_val, ok = QInputDialog.getInt(
                                self, f"XP for {unit_name}",
                                f"XP to grant to {unit_name}:",
                                4, 0, 50,
                            )
                            if ok and xp_val > 0:
                                try:
                                    self._crusade_svc.add_unit_experience(uid, xp_val)
                                except Exception as e:
                                    log.error(f"[CRUSADE UI] custom xp: {e}")

            self.refresh(self._campaign_id)
            self._tabs.setCurrentIndex(2)

    def _on_edit_battle(self, battle_id: int):
        try:
            battle = self._crusade_svc.get_battles(self._campaign_id)
            battle = next((b for b in battle if b["id"] == battle_id), None)
        except Exception:
            battle = None
        if not battle:
            return

        try:
            oob_units = self._oob_svc.get_order_of_battle(self._campaign_id) or []
        except Exception:
            oob_units = []

        dlg = _LogBattleDialog(oob_units, self)
        dlg.setWindowTitle("Edit Battle")
        # Pre-fill fields
        dlg._date.setDate(QDate.fromString(battle.get("battle_date", ""), "yyyy-MM-dd"))
        dlg._mission.setText(battle.get("mission", ""))
        dlg._opponent.setText(battle.get("opponent", ""))
        dlg._points.setValue(battle.get("points_played", 0))
        result_idx = ["Victory", "Defeat", "Draw"].index(battle.get("result", "Draw"))
        dlg._result.setCurrentIndex(result_idx)
        dlg._vp_us.setValue(battle.get("vp_scored", 0))
        dlg._vp_them.setValue(battle.get("vp_opponent", 0))
        dlg._narrative.setPlainText(battle.get("narrative_notes", ""))

        if dlg.exec() == QDialog.Accepted:
            data = dlg.result_data()
            try:
                self._crusade_svc.update_battle(battle_id, **data)
            except Exception as e:
                log.error(f"[CRUSADE UI] edit_battle: {e}")
            self.refresh(self._campaign_id)

    def _on_delete_battle(self, battle_id: int):
        reply = QMessageBox.question(
            self, "Delete Battle",
            "Delete this battle record? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                self._crusade_svc.delete_battle(battle_id)
            except Exception as e:
                log.error(f"[CRUSADE UI] delete_battle: {e}")
            self._selected_battle = None
            self.refresh(self._campaign_id)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        self.setStyleSheet(f"""
* {{ font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; color: {_FG}; }}
QWidget  {{ background: {_BG}; }}
QLabel, QCheckBox {{ background: transparent; }}

QPushButton {{
    background: {_BG3};
    color: {_FG};
    border: 1px solid {_BORDER2};
    border-radius: 5px;
    padding: 5px 14px;
    font-size: 12px;
}}
QPushButton:hover  {{ background: {_BG2}; border-color: {_ACCENT}; }}
QPushButton:pressed {{ background: {_SIDEBAR}; }}
QPushButton[objectName="accentBtn"] {{
    background: {_ACCENT};
    color: white;
    border: 1px solid {_ACCENT};
    font-weight: 600;
}}
QPushButton[objectName="accentBtn"]:hover {{ background: #3a8ae8; }}
QPushButton[objectName="ghostBtn"] {{
    background: transparent;
    color: {_FG_MID};
    border: 1px solid {_BORDER2};
}}
QPushButton[objectName="ghostBtn"]:hover {{ color: {_FG}; border-color: {_ACCENT}; }}
QPushButton[objectName="dangerBtn"] {{
    background: {_DANGER}20;
    color: {_DANGER};
    border: 1px solid {_DANGER}60;
}}
QPushButton[objectName="dangerBtn"]:hover {{ background: {_DANGER}40; }}

QScrollArea {{ background: {_BG}; border: none; }}
QScrollBar:vertical {{
    background: {_BG2};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {_BORDER2};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QLineEdit, QComboBox, QSpinBox, QTextEdit, QDateEdit {{
    background: {_BG2};
    border: 1px solid {_BORDER2};
    border-radius: 4px;
    padding: 4px 8px;
    color: {_FG};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QTextEdit:focus, QDateEdit:focus {{
    border-color: {_ACCENT};
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background: {_BG2};
    border: 1px solid {_BORDER2};
    selection-background-color: {_ACCENT}40;
    color: {_FG};
}}

QSplitter::handle {{ background: {_BORDER}; }}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {_BORDER2};
    border-radius: 3px;
    background: {_BG2};
}}
QCheckBox::indicator:checked {{
    background: {_ACCENT};
    border-color: {_ACCENT};
}}

QListWidget {{
    background: {_BG2};
    border: 1px solid {_BORDER};
    border-radius: 4px;
}}
QListWidget::item {{ padding: 4px 8px; }}
QListWidget::item:selected {{ background: {_ACCENT}30; color: {_FG}; }}
QListWidget::item:hover {{ background: {_BG3}; }}

QFormLayout QLabel {{ color: {_FG_MID}; font-size: 12px; }}

QMessageBox {{ background: {_BG2}; }}
QDialog {{ background: {_BG}; }}
""")
