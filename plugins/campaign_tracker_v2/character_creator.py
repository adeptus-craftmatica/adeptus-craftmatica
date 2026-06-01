"""
Campaign Tracker v2 — D&D 5e Character Creator Wizard.

A 10-step guided character creation dialog.
"""
from __future__ import annotations

import json
import re
import random
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QStackedWidget, QScrollArea,
    QLineEdit, QComboBox, QTextEdit, QListWidget, QListWidgetItem,
    QSpinBox, QGridLayout, QCheckBox, QButtonGroup, QRadioButton,
    QSizePolicy, QMessageBox, QSplitter, QApplication,
)

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

# ── D&D 5e Embedded Data ───────────────────────────────────────────────────────

DND5E_CLASSES = {
    "Artificer":  {"hit_die": 8,  "saves": ["CON", "INT"], "caster": "half",  "skill_count": 2, "skills": ["Arcana", "History", "Investigation", "Medicine", "Nature", "Perception", "Sleight of Hand"]},
    "Barbarian":  {"hit_die": 12, "saves": ["STR", "CON"], "caster": None,    "skill_count": 2, "skills": ["Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival"]},
    "Bard":       {"hit_die": 8,  "saves": ["DEX", "CHA"], "caster": "full",  "skill_count": 3, "skills": "any"},
    "Cleric":     {"hit_die": 8,  "saves": ["WIS", "CHA"], "caster": "full",  "skill_count": 2, "skills": ["History", "Insight", "Medicine", "Persuasion", "Religion"]},
    "Druid":      {"hit_die": 8,  "saves": ["INT", "WIS"], "caster": "full",  "skill_count": 2, "skills": ["Arcana", "Animal Handling", "Insight", "Medicine", "Nature", "Perception", "Religion", "Survival"]},
    "Fighter":    {"hit_die": 10, "saves": ["STR", "CON"], "caster": None,    "skill_count": 2, "skills": ["Acrobatics", "Animal Handling", "Athletics", "History", "Insight", "Intimidation", "Perception", "Survival"]},
    "Monk":       {"hit_die": 8,  "saves": ["STR", "DEX"], "caster": None,    "skill_count": 2, "skills": ["Acrobatics", "Athletics", "History", "Insight", "Religion", "Stealth"]},
    "Paladin":    {"hit_die": 10, "saves": ["WIS", "CHA"], "caster": "half",  "skill_count": 2, "skills": ["Athletics", "Insight", "Intimidation", "Medicine", "Persuasion", "Religion"]},
    "Ranger":     {"hit_die": 10, "saves": ["STR", "DEX"], "caster": "half",  "skill_count": 3, "skills": ["Animal Handling", "Athletics", "Insight", "Investigation", "Nature", "Perception", "Stealth", "Survival"]},
    "Rogue":      {"hit_die": 8,  "saves": ["DEX", "INT"], "caster": None,    "skill_count": 4, "skills": ["Acrobatics", "Athletics", "Deception", "Insight", "Intimidation", "Investigation", "Perception", "Performance", "Persuasion", "Sleight of Hand", "Stealth"]},
    "Sorcerer":   {"hit_die": 6,  "saves": ["CON", "CHA"], "caster": "full",  "skill_count": 2, "skills": ["Arcana", "Deception", "Insight", "Intimidation", "Persuasion", "Religion"]},
    "Warlock":    {"hit_die": 8,  "saves": ["WIS", "CHA"], "caster": "pact",  "skill_count": 2, "skills": ["Arcana", "Deception", "History", "Intimidation", "Investigation", "Nature", "Religion"]},
    "Wizard":     {"hit_die": 6,  "saves": ["INT", "WIS"], "caster": "full",  "skill_count": 2, "skills": ["Arcana", "History", "Insight", "Investigation", "Medicine", "Religion"]},
}

ALL_SKILLS = {
    "Acrobatics": "DEX", "Animal Handling": "WIS", "Arcana": "INT",
    "Athletics": "STR", "Deception": "CHA", "History": "INT",
    "Insight": "WIS", "Intimidation": "CHA", "Investigation": "INT",
    "Medicine": "WIS", "Nature": "INT", "Perception": "WIS",
    "Performance": "CHA", "Persuasion": "CHA", "Religion": "INT",
    "Sleight of Hand": "DEX", "Stealth": "DEX", "Survival": "WIS",
}

ALIGNMENTS = [
    "Lawful Good", "Neutral Good", "Chaotic Good",
    "Lawful Neutral", "True Neutral", "Chaotic Neutral",
    "Lawful Evil", "Neutral Evil", "Chaotic Evil", "Unaligned",
]

STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]

POINT_BUY_COST = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}

ABILITY_NAMES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
ABILITY_FULL = {
    "STR": "Strength", "DEX": "Dexterity", "CON": "Constitution",
    "INT": "Intelligence", "WIS": "Wisdom", "CHA": "Charisma",
}

PROF_BONUS = {
    1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 3, 8: 3,
    9: 4, 10: 4, 11: 4, 12: 4, 13: 5, 14: 5, 15: 5, 16: 5,
    17: 6, 18: 6, 19: 6, 20: 6,
}

FULL_CASTER_SLOTS = {
    1:  [2, 0, 0, 0, 0, 0, 0, 0, 0],  2:  [3, 0, 0, 0, 0, 0, 0, 0, 0],
    3:  [4, 2, 0, 0, 0, 0, 0, 0, 0],  4:  [4, 3, 0, 0, 0, 0, 0, 0, 0],
    5:  [4, 3, 2, 0, 0, 0, 0, 0, 0],  6:  [4, 3, 3, 0, 0, 0, 0, 0, 0],
    7:  [4, 3, 3, 1, 0, 0, 0, 0, 0],  8:  [4, 3, 3, 2, 0, 0, 0, 0, 0],
    9:  [4, 3, 3, 3, 1, 0, 0, 0, 0],  10: [4, 3, 3, 3, 2, 0, 0, 0, 0],
    11: [4, 3, 3, 3, 2, 1, 0, 0, 0],  12: [4, 3, 3, 3, 2, 1, 0, 0, 0],
    13: [4, 3, 3, 3, 2, 1, 1, 0, 0],  14: [4, 3, 3, 3, 2, 1, 1, 0, 0],
    15: [4, 3, 3, 3, 2, 1, 1, 1, 0],  16: [4, 3, 3, 3, 2, 1, 1, 1, 0],
    17: [4, 3, 3, 3, 2, 1, 1, 1, 1],  18: [4, 3, 3, 3, 3, 1, 1, 1, 1],
    19: [4, 3, 3, 3, 3, 2, 1, 1, 1],  20: [4, 3, 3, 3, 3, 2, 2, 1, 1],
}

SPELL_SCHOOLS = [
    "Abjuration", "Conjuration", "Divination", "Enchantment",
    "Evocation", "Illusion", "Necromancy", "Transmutation",
]

# ── Lazy data cache ────────────────────────────────────────────────────────────

_dnd_cache: dict = {}


def _load_dnd(filename: str) -> list:
    if filename not in _dnd_cache:
        import sys
        from pathlib import Path
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).parent.parent.parent
        path = base / "game_system_data" / "dungeons_and_dragons" / filename
        try:
            _dnd_cache[filename] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            _dnd_cache[filename] = []
    return _dnd_cache[filename]


# ── Helper ─────────────────────────────────────────────────────────────────────

def _mod(score: int) -> str:
    m = (score - 10) // 2
    return f"+{m}" if m >= 0 else str(m)


def _compute_spell_slots(classes: list[dict]) -> dict:
    """Compute spell slots for a given class list using multiclass rules."""
    total_level = sum(c["level"] for c in classes)
    if total_level < 1:
        total_level = 1

    caster_level = 0
    for c in classes:
        cdata = DND5E_CLASSES.get(c["name"], {})
        caster_type = cdata.get("caster")
        lvl = c["level"]
        if caster_type == "full":
            caster_level += lvl
        elif caster_type == "half":
            caster_level += lvl // 2
        elif caster_type == "pact":
            caster_level += lvl

    slots = {}
    if caster_level > 0:
        caster_level = min(caster_level, 20)
        slot_list = FULL_CASTER_SLOTS.get(caster_level, [0] * 9)
        for i, count in enumerate(slot_list):
            slots[str(i + 1)] = {"max": count, "used": 0}
    else:
        for i in range(1, 10):
            slots[str(i)] = {"max": 0, "used": 0}
    return slots


# ── Shared stylesheet helpers ──────────────────────────────────────────────────

def _base_style() -> str:
    return f"""
        QDialog, QWidget {{
            background: {_BG};
            color: {_FG};
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }}
        QLabel {{
            background: transparent;
            color: {_FG};
        }}
        QLineEdit, QTextEdit, QComboBox, QSpinBox {{
            background: {_BG3};
            color: {_FG};
            border: 1px solid {_BORDER2};
            border-radius: 4px;
            padding: 4px 8px;
            selection-background-color: {_ACCENT};
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {_ACCENT};
        }}
        QComboBox::drop-down {{
            border: none;
        }}
        QComboBox QAbstractItemView {{
            background: {_BG3};
            color: {_FG};
            border: 1px solid {_BORDER2};
            selection-background-color: {_ACCENT};
        }}
        QListWidget {{
            background: {_BG2};
            color: {_FG};
            border: 1px solid {_BORDER};
            border-radius: 4px;
        }}
        QListWidget::item {{
            padding: 6px 10px;
        }}
        QListWidget::item:selected {{
            background: {_ACCENT};
            color: white;
        }}
        QListWidget::item:hover {{
            background: {_BG3};
        }}
        QPushButton {{
            background: {_BG3};
            color: {_FG_MID};
            border: 1px solid {_BORDER};
            border-radius: 5px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            background: {_BORDER2};
            color: {_FG};
        }}
        QPushButton[accent="true"] {{
            background: {_ACCENT};
            color: white;
            border: none;
            font-weight: bold;
        }}
        QPushButton[accent="true"]:hover {{
            background: #6aadff;
        }}
        QPushButton[danger="true"] {{
            background: {_DANGER};
            color: white;
            border: none;
        }}
        QScrollBar:vertical {{
            background: {_BG2};
            width: 8px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: {_BORDER2};
            border-radius: 4px;
            min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: {_BG2};
            height: 8px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: {_BORDER2};
            border-radius: 4px;
            min-width: 20px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QCheckBox {{
            color: {_FG};
            spacing: 6px;
        }}
        QRadioButton {{
            color: {_FG};
            spacing: 6px;
        }}
        QFrame[frameShape="4"], QFrame[frameShape="5"] {{
            color: {_BORDER};
        }}
    """


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; letter-spacing:1.5px; font-weight:bold; background:transparent;")
    return lbl


# ══════════════════════════════════════════════════════════════════════════════
# Page 0 — Concept
# ══════════════════════════════════════════════════════════════════════════════

class ConceptPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        title = QLabel("Character Concept")
        title.setStyleSheet(f"color:{_FG}; font-size:20px; font-weight:bold; background:transparent;")
        lay.addWidget(title)

        sub = QLabel("Give your character a name and basic identity.")
        sub.setStyleSheet(f"color:{_FG_MID}; font-size:13px; background:transparent;")
        lay.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{_BORDER};")
        lay.addWidget(sep)

        form = QGridLayout()
        form.setSpacing(10)
        form.setColumnStretch(1, 1)

        row = 0
        lbl = QLabel("Character Name *")
        lbl.setStyleSheet(f"color:{_FG_MID}; background:transparent;")
        form.addWidget(lbl, row, 0)
        self._name = QLineEdit()
        self._name.setPlaceholderText("Enter character name...")
        form.addWidget(self._name, row, 1)

        row += 1
        lbl2 = QLabel("Character Type")
        lbl2.setStyleSheet(f"color:{_FG_MID}; background:transparent;")
        form.addWidget(lbl2, row, 0)
        self._role = QComboBox()
        self._role.addItems([
            "Player Character", "Non-Player Character", "DMPC",
            "Villain", "Boss", "Minion", "Ally",
        ])
        form.addWidget(self._role, row, 1)

        row += 1
        lbl3 = QLabel("Alignment")
        lbl3.setStyleSheet(f"color:{_FG_MID}; background:transparent;")
        form.addWidget(lbl3, row, 0)
        self._alignment = QComboBox()
        self._alignment.addItems(ALIGNMENTS)
        form.addWidget(self._alignment, row, 1)

        lay.addLayout(form)

        lbl4 = QLabel("Appearance Notes")
        lbl4.setStyleSheet(f"color:{_FG_MID}; background:transparent;")
        lay.addWidget(lbl4)
        self._appearance = QTextEdit()
        self._appearance.setPlaceholderText("Describe your character's appearance (optional)...")
        self._appearance.setFixedHeight(90)
        lay.addWidget(self._appearance)

        lay.addStretch()

    def validate(self) -> tuple[bool, str]:
        if not self._name.text().strip():
            return False, "Character name is required."
        return True, ""

    def get_data(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "character_role": self._role.currentText(),
            "alignment": self._alignment.currentText(),
            "appearance_notes": self._appearance.toPlainText().strip(),
        }

    def set_data(self, d: dict):
        if "name" in d:
            self._name.setText(d["name"])
        if "character_role" in d:
            idx = self._role.findText(d["character_role"])
            if idx >= 0:
                self._role.setCurrentIndex(idx)
        if "alignment" in d:
            idx = self._alignment.findText(d["alignment"])
            if idx >= 0:
                self._alignment.setCurrentIndex(idx)
        if "appearance_notes" in d:
            self._appearance.setPlainText(d["appearance_notes"])


# ══════════════════════════════════════════════════════════════════════════════
# Page 1 — Species
# ══════════════════════════════════════════════════════════════════════════════

class SpeciesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        self._species_data = []
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Left panel
        left = QFrame()
        left.setFixedWidth(260)
        left.setStyleSheet(f"background:{_BG2}; border-right:1px solid {_BORDER};")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 16, 12, 12)
        ll.setSpacing(8)

        lbl = _section_label("Species")
        ll.addWidget(lbl)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search species...")
        self._search.textChanged.connect(self._filter_list)
        ll.addWidget(self._search)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select)
        ll.addWidget(self._list, 1)

        lay.addWidget(left)

        # Right panel
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(20, 20, 20, 20)
        rl.setSpacing(10)

        self._name_lbl = QLabel("Select a species")
        self._name_lbl.setStyleSheet(f"color:{_FG}; font-size:18px; font-weight:bold; background:transparent;")
        self._name_lbl.setWordWrap(True)
        rl.addWidget(self._name_lbl)

        self._desc = QTextEdit()
        self._desc.setReadOnly(True)
        self._desc.setStyleSheet(f"background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER}; border-radius:4px;")
        rl.addWidget(self._desc, 1)

        lay.addWidget(right, 1)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._load_species()

    def _load_species(self):
        self._species_data = _load_dnd("species.json")
        seen = set()
        unique = []
        for s in self._species_data:
            n = s.get("name", "")
            if n and n not in seen:
                seen.add(n)
                unique.append(s)
        self._species_data = sorted(unique, key=lambda x: x.get("name", ""))
        self._populate_list(self._species_data)

    def _populate_list(self, data: list):
        self._list.clear()
        for s in data:
            item = QListWidgetItem(s.get("name", ""))
            item.setData(Qt.UserRole, s)
            self._list.addItem(item)

    def _filter_list(self, text: str):
        q = text.lower()
        filtered = [s for s in self._species_data if q in s.get("name", "").lower()]
        self._populate_list(filtered)

    def _on_select(self, item: QListWidgetItem, _=None):
        if item is None:
            return
        s = item.data(Qt.UserRole)
        if s is None:
            return
        self._name_lbl.setText(s.get("name", ""))
        self._desc.setPlainText(s.get("description", "No description available."))

    def validate(self) -> tuple[bool, str]:
        if self._list.currentItem() is None:
            return False, "Please select a species."
        return True, ""

    def get_data(self) -> dict:
        item = self._list.currentItem()
        if item is None:
            return {"race": "", "species_description": ""}
        s = item.data(Qt.UserRole) or {}
        return {
            "race": item.text(),
            "species_description": s.get("description", ""),
        }

    def set_data(self, d: dict):
        name = d.get("race", "")
        if not name:
            return
        for i in range(self._list.count()):
            if self._list.item(i).text() == name:
                self._list.setCurrentRow(i)
                break


# ══════════════════════════════════════════════════════════════════════════════
# Page 2 — Class
# ══════════════════════════════════════════════════════════════════════════════

class _ClassRow(QFrame):
    removed = Signal(object)

    def __init__(self, all_class_names: list, parent=None):
        super().__init__(parent)
        self._all_names = all_class_names
        self._build()

    def _build(self):
        self.setStyleSheet(f"background:{_BG3}; border:1px solid {_BORDER}; border-radius:6px;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(10)

        self._cls_combo = QComboBox()
        self._cls_combo.addItems(self._all_names)
        self._cls_combo.currentTextChanged.connect(self._update_hit_die)
        self._cls_combo.setMinimumWidth(140)
        lay.addWidget(self._cls_combo)

        self._level = QSpinBox()
        self._level.setRange(1, 20)
        self._level.setValue(1)
        self._level.setFixedWidth(65)
        lay.addWidget(self._level)

        lbl_lvl = QLabel("levels")
        lbl_lvl.setStyleSheet(f"color:{_FG_MID}; background:transparent;")
        lay.addWidget(lbl_lvl)

        self._hd_lbl = QLabel("d8")
        self._hd_lbl.setStyleSheet(f"color:{_ACCENT}; font-weight:bold; background:transparent;")
        self._hd_lbl.setFixedWidth(30)
        lay.addWidget(self._hd_lbl)

        lay.addStretch()

        self._del_btn = QPushButton("x")
        self._del_btn.setFixedSize(28, 28)
        self._del_btn.setStyleSheet(f"background:{_DANGER}; color:white; border:none; border-radius:4px; font-weight:bold;")
        self._del_btn.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(self._del_btn)

        self._update_hit_die(self._cls_combo.currentText())

    def _update_hit_die(self, class_name: str):
        cdata = DND5E_CLASSES.get(class_name, {})
        hd = cdata.get("hit_die", 8)
        self._hd_lbl.setText(f"d{hd}")

    def set_delete_enabled(self, enabled: bool):
        self._del_btn.setEnabled(enabled)
        self._del_btn.setVisible(enabled)

    def get_class_name(self) -> str:
        return self._cls_combo.currentText()

    def get_level(self) -> int:
        return self._level.value()

    def set_class(self, name: str):
        idx = self._cls_combo.findText(name)
        if idx >= 0:
            self._cls_combo.setCurrentIndex(idx)

    def set_level(self, lvl: int):
        self._level.setValue(lvl)


class ClassPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list = []
        self._all_class_names: list = []
        self._loaded = False
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel("Class & Level")
        title.setStyleSheet(f"color:{_FG}; font-size:20px; font-weight:bold; background:transparent;")
        lay.addWidget(title)

        sub = QLabel("Choose your class(es) and level. You can multiclass up to 3 classes with a total level of 20.")
        sub.setStyleSheet(f"color:{_FG_MID}; background:transparent;")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container.setStyleSheet(f"background:{_BG};")
        self._rows_layout = QVBoxLayout(container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        self._rows_layout.addStretch()

        scroll.setWidget(container)
        lay.addWidget(scroll, 1)

        self._add_btn = QPushButton("+ Add Multiclass")
        self._add_btn.setStyleSheet(f"background:{_BG3}; color:{_ACCENT}; border:1px dashed {_ACCENT}; border-radius:5px; padding:6px 14px;")
        self._add_btn.clicked.connect(self._add_row)
        lay.addWidget(self._add_btn)

        summary_frame = QFrame()
        summary_frame.setStyleSheet(f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;")
        sl = QGridLayout(summary_frame)
        sl.setContentsMargins(16, 12, 16, 12)
        sl.setSpacing(8)

        def _stat_lbl(text, col=0, row=0):
            l = QLabel(text)
            l.setStyleSheet(f"color:{_FG_MID}; background:transparent; font-size:12px;")
            sl.addWidget(l, row, col)
            return l

        def _val_lbl(col=1, row=0):
            l = QLabel("--")
            l.setStyleSheet(f"color:{_FG}; font-weight:bold; background:transparent;")
            sl.addWidget(l, row, col)
            return l

        _stat_lbl("Total Level", 0, 0)
        self._lbl_total_level = _val_lbl(1, 0)
        _stat_lbl("Proficiency Bonus", 2, 0)
        self._lbl_prof = _val_lbl(3, 0)
        _stat_lbl("Est. Max HP", 0, 1)
        self._lbl_hp = _val_lbl(1, 1)
        _stat_lbl("Caster Type", 2, 1)
        self._lbl_caster = _val_lbl(3, 1)

        self._spell_note = QLabel()
        self._spell_note.setStyleSheet(f"color:{_ACCENT}; background:transparent; font-size:12px;")
        sl.addWidget(self._spell_note, 2, 0, 1, 4)

        lay.addWidget(summary_frame)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._load_classes()

    def _load_classes(self):
        extra = _load_dnd("classes.json")
        names = list(DND5E_CLASSES.keys())
        for c in extra:
            n = c.get("name", "")
            if n and n not in names:
                names.append(n)
        self._all_class_names = sorted(names)
        self._add_row()

    def _add_row(self):
        if len(self._rows) >= 3:
            return
        row = _ClassRow(self._all_class_names, self)
        row.removed.connect(self._remove_row)
        row.set_delete_enabled(len(self._rows) > 0)
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
        self._rows.append(row)

        row._cls_combo.currentTextChanged.connect(self._update_summary)
        row._level.valueChanged.connect(self._update_summary)
        row.removed.connect(lambda _: self._update_summary())

        self._update_delete_buttons()
        self._update_add_btn()
        self._update_summary()

    def _remove_row(self, row):
        if len(self._rows) <= 1:
            return
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.deleteLater()
        self._update_delete_buttons()
        self._update_add_btn()
        self._update_summary()

    def _update_delete_buttons(self):
        for row in self._rows:
            row.set_delete_enabled(len(self._rows) > 1)

    def _update_add_btn(self):
        self._add_btn.setEnabled(len(self._rows) < 3)

    def _update_summary(self):
        classes = self._get_classes()
        total = sum(c["level"] for c in classes)
        prof = PROF_BONUS.get(min(total, 20), 2)
        self._lbl_total_level.setText(str(total))
        self._lbl_prof.setText(f"+{prof}")

        hp = 0
        for c in classes:
            cdata = DND5E_CLASSES.get(c["name"], {})
            hd = cdata.get("hit_die", 8)
            avg = (hd // 2 + 1)
            hp += (hd + 5) + (avg + 5) * (c["level"] - 1) if c["level"] > 0 else 0
        self._lbl_hp.setText(str(hp))

        caster_types = []
        is_caster = False
        for c in classes:
            cdata = DND5E_CLASSES.get(c["name"], {})
            ct = cdata.get("caster")
            if ct:
                is_caster = True
                if ct not in caster_types:
                    caster_types.append(ct)
        if caster_types:
            self._lbl_caster.setText(", ".join(caster_types))
            self._spell_note.setText("Lightning Spellcasting available")
        else:
            self._lbl_caster.setText("None")
            self._spell_note.setText("")

    def _get_classes(self) -> list:
        return [{"name": r.get_class_name(), "level": r.get_level()} for r in self._rows]

    def validate(self) -> tuple[bool, str]:
        classes = self._get_classes()
        total = sum(c["level"] for c in classes)
        if total > 20:
            return False, "Total level cannot exceed 20."
        if total < 1:
            return False, "Total level must be at least 1."
        return True, ""

    def get_data(self) -> dict:
        classes = self._get_classes()
        total = sum(c["level"] for c in classes)
        primary = classes[0]["name"] if classes else ""
        is_caster = any(DND5E_CLASSES.get(c["name"], {}).get("caster") for c in classes)
        return {
            "classes": classes,
            "total_level": total,
            "primary_class": primary,
            "is_caster": is_caster,
        }

    def set_data(self, d: dict):
        classes = d.get("classes", [])
        if not classes:
            return
        for row in list(self._rows):
            self._remove_row(row)
        for i, c in enumerate(classes):
            if i >= len(self._rows):
                self._add_row()
            if i < len(self._rows):
                self._rows[i].set_class(c["name"])
                self._rows[i].set_level(c["level"])


# ══════════════════════════════════════════════════════════════════════════════
# Page 3 — Background
# ══════════════════════════════════════════════════════════════════════════════

def _parse_bg_prop(val) -> str:
    """Convert a data-* property value (string or list) to a bullet-list string."""
    if isinstance(val, list):
        return "\n".join(f"• {x}" for x in val if str(x).strip())
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return "\n".join(f"• {x}" for x in parsed if str(x).strip())
            return str(parsed)
        except Exception:
            return val
    return str(val) if val else ""


def _parse_bg_desc(desc: str, keyword: str) -> str:
    """
    Extract a personality section from a D&D 5e background description.

    Most backgrounds store personality data inline as:
        "d8 Personality Trait 1 First trait. 2 Second trait. ..."
    This parser finds the section and returns each numbered entry as a bullet.
    """
    # Match "d6 Personality Traits" / "d8 Bond" / "d6 Ideal" / "d6 Flaw" etc.
    m = re.search(rf'd\d+\s+{re.escape(keyword)}s?\b', desc, re.IGNORECASE)
    if not m:
        # Try without dice prefix — some backgrounds omit the die
        m = re.search(rf'\b{re.escape(keyword)}s?\b', desc, re.IGNORECASE)
        if not m:
            return ""

    # Grab up to 1000 chars after the section header
    chunk = desc[m.end(): m.end() + 1000]

    # Stop at the next section header (another dN keyword or "Feature:")
    stop = re.search(
        r'd\d+\s+(?:Personality\s+Trait|Ideal|Bond|Flaw|Feature|Specialty|Equipment|Skill)',
        chunk, re.IGNORECASE,
    )
    if stop:
        chunk = chunk[:stop.start()]

    chunk = chunk.strip()

    # Split on "1 text 2 text …" numbered entries
    # Use a lookahead so each item runs until the next number
    raw_items = re.split(r'(?<!\w)(\d{1,2})\s+', chunk)

    items = []
    i = 1
    while i < len(raw_items) - 1:
        if re.fullmatch(r'\d{1,2}', raw_items[i]):
            text = raw_items[i + 1].strip()
            text = re.sub(r'\s+', ' ', text).strip()
            if text and len(text) > 4:
                items.append(f"• {text}")
            i += 2
        else:
            i += 1

    if items:
        return "\n".join(items[:10])

    # Fallback — return raw chunk trimmed
    return chunk[:300]


class BackgroundPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        self._bg_data = []
        self._current_bg = {}
        self._build()

    def _build(self):
        from PySide6.QtWidgets import QTabWidget
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Left: search + list ───────────────────────────────────────────────
        left = QFrame()
        left.setFixedWidth(240)
        left.setStyleSheet(f"background:{_BG2}; border-right:1px solid {_BORDER};")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 16, 12, 12)
        ll.setSpacing(8)
        ll.addWidget(_section_label("Background"))

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search backgrounds…")
        self._search.textChanged.connect(self._filter_list)
        ll.addWidget(self._search)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select)
        ll.addWidget(self._list, 1)
        lay.addWidget(left)

        # ── Right: name + tabs ────────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet(f"background:{_BG};")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(20, 16, 20, 16)
        rl.setSpacing(10)

        self._name_lbl = QLabel("Select a background from the list")
        self._name_lbl.setStyleSheet(
            f"color:{_FG}; font-size:17px; font-weight:bold; background:transparent;"
        )
        self._name_lbl.setWordWrap(True)
        rl.addWidget(self._name_lbl)

        # Tab widget — Description | Personality
        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane{{background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;}}"
            f"QTabBar::tab{{background:{_BG3}; color:{_FG_MID}; padding:6px 18px;"
            f"border:1px solid {_BORDER}; border-bottom:none; margin-right:2px; border-radius:4px 4px 0 0;}}"
            f"QTabBar::tab:selected{{background:{_BG2}; color:{_FG};}}"
        )

        # ── Tab 1: Description ────────────────────────────────────────────────
        desc_tab = QWidget()
        desc_tab.setStyleSheet(f"background:{_BG2};")
        dt = QVBoxLayout(desc_tab)
        dt.setContentsMargins(12, 12, 12, 12)
        self._desc = QTextEdit()
        self._desc.setReadOnly(True)
        self._desc.setPlaceholderText("Select a background to see its description…")
        self._desc.setStyleSheet(
            f"QTextEdit{{background:{_BG2}; color:{_FG_MID}; border:none;"
            f"font-size:12px; line-height:1.5;}}"
        )
        dt.addWidget(self._desc)
        tabs.addTab(desc_tab, "📖  Description")

        # ── Tab 2: Personality ────────────────────────────────────────────────
        pers_tab = QWidget()
        pers_tab.setStyleSheet(f"background:{_BG2};")
        pt = QGridLayout(pers_tab)
        pt.setContentsMargins(12, 12, 12, 12)
        pt.setSpacing(10)

        _txt_style = (
            f"QTextEdit{{background:{_BG3}; color:{_FG}; border:1px solid {_BORDER};"
            f"border-radius:4px; font-size:12px; padding:6px;}}"
            f"QTextEdit:focus{{border-color:{_ACCENT};}}"
        )
        _lbl_style = f"color:{_FG_MID}; font-size:12px; font-weight:600; background:transparent;"

        for col, (attr, label, placeholder) in enumerate([
            ("_traits_txt", "Personality Traits", "What mannerisms and attitudes define this character?"),
            ("_ideals_txt", "Ideals",              "What principles does this character believe in?"),
        ]):
            lbl = QLabel(label)
            lbl.setStyleSheet(_lbl_style)
            pt.addWidget(lbl, 0, col)
            txt = QTextEdit()
            txt.setPlaceholderText(placeholder)
            txt.setStyleSheet(_txt_style)
            setattr(self, attr, txt)
            pt.addWidget(txt, 1, col)

        for col, (attr, label, placeholder) in enumerate([
            ("_bonds_txt", "Bonds",  "Who or what does this character care about most?"),
            ("_flaws_txt", "Flaws",  "What weakness or vice holds this character back?"),
        ]):
            lbl = QLabel(label)
            lbl.setStyleSheet(_lbl_style)
            pt.addWidget(lbl, 2, col)
            txt = QTextEdit()
            txt.setPlaceholderText(placeholder)
            txt.setStyleSheet(_txt_style)
            setattr(self, attr, txt)
            pt.addWidget(txt, 3, col)

        pt.setRowStretch(1, 1)
        pt.setRowStretch(3, 1)
        pt.setColumnStretch(0, 1)
        pt.setColumnStretch(1, 1)

        hint = QLabel("Pre-filled from the selected background — edit freely to personalise.")
        hint.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent;")
        hint.setWordWrap(True)
        pt_outer = QVBoxLayout()
        pt_outer.setContentsMargins(0, 0, 0, 0)
        pt_outer.setSpacing(4)
        pt_outer.addWidget(pers_tab, 1)
        pt_outer.addWidget(hint)

        pers_container = QWidget()
        pers_container.setStyleSheet(f"background:{_BG2};")
        pers_container.setLayout(pt_outer)
        tabs.addTab(pers_container, "✏  Personality")

        rl.addWidget(tabs, 1)
        lay.addWidget(right, 1)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._load_backgrounds()

    def _load_backgrounds(self):
        raw = _load_dnd("backgrounds.json")
        seen = set()
        unique = []
        for b in raw:
            n = b.get("name", "")
            if n and n not in seen:
                seen.add(n)
                unique.append(b)
        self._bg_data = sorted(unique, key=lambda x: x.get("name", ""))
        self._populate_list(self._bg_data)

    def _populate_list(self, data: list):
        self._list.clear()
        for b in data:
            item = QListWidgetItem(b.get("name", ""))
            item.setData(Qt.UserRole, b)
            self._list.addItem(item)

    def _filter_list(self, text: str):
        q = text.lower()
        filtered = [b for b in self._bg_data if q in b.get("name", "").lower()]
        self._populate_list(filtered)

    def _on_select(self, item: QListWidgetItem, _=None):
        if item is None:
            return
        b = item.data(Qt.UserRole)
        if b is None:
            return
        self._current_bg = b
        self._name_lbl.setText(b.get("name", ""))
        desc = b.get("description", "")
        self._desc.setPlainText(desc)

        props = b.get("properties", {})
        if not isinstance(props, dict):
            props = {}

        # 1. Try structured data-* property keys (only ~5 PHB backgrounds have these)
        # 2. Fall back to parsing the numbered lists from the description text
        # 3. If neither has data, leave blank for user to fill in

        def _get(prop_key: str, desc_keyword: str) -> str:
            val = _parse_bg_prop(props.get(prop_key, ""))
            if val.strip():
                return val
            return _parse_bg_desc(desc, desc_keyword)

        self._traits_txt.setPlainText(_get("data-Personality Traits", "Personality Trait"))
        self._ideals_txt.setPlainText(_get("data-Ideals",              "Ideal"))
        self._bonds_txt.setPlainText( _get("data-Bonds",               "Bond"))
        self._flaws_txt.setPlainText( _get("data-Flaws",               "Flaw"))

    def validate(self) -> tuple[bool, str]:
        if self._list.currentItem() is None:
            return False, "Please select a background."
        return True, ""

    def get_data(self) -> dict:
        item = self._list.currentItem()
        if item is None:
            return {
                "background": "", "bg_traits": "", "bg_ideals": "",
                "bg_bonds": "", "bg_flaws": "", "bg_equipment": "", "bg_gold": 0,
            }
        props = self._current_bg.get("properties", {})
        if not isinstance(props, dict):
            props = {}
        return {
            "background": item.text(),
            "bg_traits": self._traits_txt.toPlainText(),
            "bg_ideals": self._ideals_txt.toPlainText(),
            "bg_bonds": self._bonds_txt.toPlainText(),
            "bg_flaws": self._flaws_txt.toPlainText(),
            "bg_equipment": json.dumps(props.get("data-Equipment", "")),
            "bg_gold": props.get("data-Starting Gold", 0),
        }

    def set_data(self, d: dict):
        name = d.get("background", "")
        if not name:
            return
        for i in range(self._list.count()):
            if self._list.item(i).text() == name:
                self._list.setCurrentRow(i)
                break


# ══════════════════════════════════════════════════════════════════════════════
# Page 4 — Ability Scores
# ══════════════════════════════════════════════════════════════════════════════

class AbilityScoresPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._class_data: list = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel("Ability Scores")
        title.setStyleSheet(f"color:{_FG}; font-size:20px; font-weight:bold; background:transparent;")
        lay.addWidget(title)

        method_row = QHBoxLayout()
        self._btn_standard = QRadioButton("Standard Array")
        self._btn_pointbuy = QRadioButton("Point Buy")
        self._btn_manual   = QRadioButton("Manual Entry")
        self._btn_standard.setChecked(True)
        for rb in (self._btn_standard, self._btn_pointbuy, self._btn_manual):
            rb.setStyleSheet(f"color:{_FG}; background:transparent;")
            method_row.addWidget(rb)
        method_row.addStretch()
        lay.addLayout(method_row)

        self._btn_standard.toggled.connect(self._method_changed)
        self._btn_pointbuy.toggled.connect(self._method_changed)
        self._btn_manual.toggled.connect(self._method_changed)

        self._pb_info = QLabel("Points spent: 0 / 27 -- 27 remaining")
        self._pb_info.setStyleSheet(f"color:{_ACCENT}; background:transparent; font-size:12px;")
        self._pb_info.setVisible(False)
        lay.addWidget(self._pb_info)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)

        headers = ["Ability", "Score", "Modifier", "Saving Throw"]
        for col, h in enumerate(headers):
            hl = QLabel(h)
            hl.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; font-weight:bold; background:transparent; letter-spacing:1px;")
            grid.addWidget(hl, 0, col)

        self._combos: list = []
        self._spins:  list = []
        self._mod_lbls: list = []
        self._save_lbls: list = []

        for i, ab in enumerate(ABILITY_NAMES):
            row = i + 1
            ab_lbl = QLabel(f"{ABILITY_FULL[ab]}")
            ab_lbl.setStyleSheet(f"color:{_FG}; background:transparent;")
            grid.addWidget(ab_lbl, row, 0)

            combo = QComboBox()
            combo.addItems([str(v) for v in STANDARD_ARRAY])
            combo.setFixedWidth(80)
            combo.currentIndexChanged.connect(self._on_standard_changed)
            self._combos.append(combo)
            grid.addWidget(combo, row, 1)

            spin = QSpinBox()
            spin.setRange(8, 15)
            spin.setValue(8)
            spin.setFixedWidth(80)
            spin.setVisible(False)
            spin.valueChanged.connect(self._on_spin_changed)
            self._spins.append(spin)
            grid.addWidget(spin, row, 1)

            mod_lbl = QLabel("+0")
            mod_lbl.setStyleSheet(f"color:{_SUCCESS}; font-weight:bold; background:transparent;")
            self._mod_lbls.append(mod_lbl)
            grid.addWidget(mod_lbl, row, 2)

            save_lbl = QLabel("--")
            save_lbl.setStyleSheet(f"color:{_FG_MID}; background:transparent; font-size:12px;")
            self._save_lbls.append(save_lbl)
            grid.addWidget(save_lbl, row, 3)

        lay.addLayout(grid)

        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;")
        sl = QHBoxLayout(stats_frame)
        sl.setContentsMargins(16, 10, 16, 10)
        sl.setSpacing(20)

        self._stat_lbls: dict = {}
        for key in ["Max HP", "Initiative", "Passive Perception", "Carrying Capacity"]:
            vl = QVBoxLayout()
            vl.setSpacing(2)
            k_lbl = QLabel(key)
            k_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; background:transparent;")
            v_lbl = QLabel("--")
            v_lbl.setStyleSheet(f"color:{_FG}; font-weight:bold; background:transparent;")
            vl.addWidget(k_lbl)
            vl.addWidget(v_lbl)
            self._stat_lbls[key] = v_lbl
            sl.addLayout(vl)

        lay.addWidget(stats_frame)
        lay.addStretch()

        self._init_standard_combos()
        self._update_mods()

    def _init_standard_combos(self):
        for i, combo in enumerate(self._combos):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems([str(v) for v in STANDARD_ARRAY])
            combo.setCurrentIndex(i)
            combo.blockSignals(False)
        self._refresh_standard_options()
        self._update_mods()

    def _refresh_standard_options(self):
        current_vals = []
        for combo in self._combos:
            try:
                current_vals.append(int(combo.currentText()))
            except Exception:
                current_vals.append(-1)

        for idx, combo in enumerate(self._combos):
            combo.blockSignals(True)
            own_val = current_vals[idx]
            others = [v for i, v in enumerate(current_vals) if i != idx]
            available = [v for v in STANDARD_ARRAY if v not in others or v == own_val]
            combo.clear()
            combo.addItems([str(v) for v in sorted(set(available), reverse=True)])
            best = combo.findText(str(own_val))
            if best >= 0:
                combo.setCurrentIndex(best)
            combo.blockSignals(False)

    def _on_standard_changed(self):
        self._refresh_standard_options()
        self._update_mods()

    def _on_spin_changed(self):
        if self._btn_pointbuy.isChecked():
            self._update_pb_counter()
        self._update_mods()

    def _update_pb_counter(self):
        total_cost = sum(POINT_BUY_COST.get(spin.value(), 0) for spin in self._spins)
        remaining = 27 - total_cost
        self._pb_info.setText(f"Points spent: {total_cost} / 27 -- {max(0, remaining)} remaining")
        for spin in self._spins:
            cost_at_next = POINT_BUY_COST.get(min(spin.value() + 1, 15), 99)
            would_exceed = (total_cost - POINT_BUY_COST.get(spin.value(), 0) + cost_at_next) > 27
            spin.setMaximum(15 if not would_exceed else spin.value())

    def _method_changed(self):
        is_standard = self._btn_standard.isChecked()
        is_pb       = self._btn_pointbuy.isChecked()
        is_manual   = self._btn_manual.isChecked()

        self._pb_info.setVisible(is_pb)

        for combo in self._combos:
            combo.setVisible(is_standard)
        for spin in self._spins:
            spin.setVisible(not is_standard)
            if is_pb:
                spin.setRange(8, 15)
            elif is_manual:
                spin.setRange(1, 30)
                spin.setMaximum(30)

        if is_pb:
            self._update_pb_counter()
        self._update_mods()

    def _get_scores(self) -> dict:
        scores = {}
        if self._btn_standard.isChecked():
            for i, ab in enumerate(ABILITY_NAMES):
                try:
                    scores[ab] = int(self._combos[i].currentText())
                except Exception:
                    scores[ab] = 10
        else:
            for i, ab in enumerate(ABILITY_NAMES):
                scores[ab] = self._spins[i].value()
        return scores

    def _update_mods(self):
        scores = self._get_scores()
        class_saves = set()
        for c in self._class_data:
            cdata = DND5E_CLASSES.get(c.get("name", ""), {})
            for s in cdata.get("saves", []):
                class_saves.add(s)

        total_level = sum(c.get("level", 1) for c in self._class_data) or 1
        prof = PROF_BONUS.get(min(total_level, 20), 2)

        for i, ab in enumerate(ABILITY_NAMES):
            score = scores[ab]
            m = (score - 10) // 2
            mod_str = f"+{m}" if m >= 0 else str(m)
            self._mod_lbls[i].setText(mod_str)
            color = _SUCCESS if m >= 0 else _DANGER
            self._mod_lbls[i].setStyleSheet(f"color:{color}; font-weight:bold; background:transparent;")

            if ab in class_saves:
                sv = m + prof
                sv_str = f"+{sv}" if sv >= 0 else str(sv)
                self._save_lbls[i].setText(f"{sv_str} (prof)")
                self._save_lbls[i].setStyleSheet(f"color:{_SUCCESS}; background:transparent; font-size:12px;")
            else:
                self._save_lbls[i].setText(mod_str)
                self._save_lbls[i].setStyleSheet(f"color:{_FG_MID}; background:transparent; font-size:12px;")

        dex_mod = (scores["DEX"] - 10) // 2
        con_mod = (scores["CON"] - 10) // 2
        wis_mod = (scores["WIS"] - 10) // 2
        str_score = scores["STR"]

        if self._class_data:
            hp = 0
            for c in self._class_data:
                cdata = DND5E_CLASSES.get(c.get("name", ""), {})
                hd = cdata.get("hit_die", 8)
                lvl = c.get("level", 1)
                avg = hd // 2 + 1
                hp += (hd + con_mod) + (avg + con_mod) * (lvl - 1)
        else:
            hp = 8 + con_mod

        self._stat_lbls["Max HP"].setText(str(max(1, hp)))
        self._stat_lbls["Initiative"].setText(f"+{dex_mod}" if dex_mod >= 0 else str(dex_mod))
        self._stat_lbls["Passive Perception"].setText(str(10 + wis_mod))
        self._stat_lbls["Carrying Capacity"].setText(f"{str_score * 15} lbs")

    def update_class_data(self, classes: list):
        self._class_data = classes
        self._update_mods()

    def validate(self) -> tuple[bool, str]:
        if self._btn_pointbuy.isChecked():
            total_cost = sum(POINT_BUY_COST.get(spin.value(), 0) for spin in self._spins)
            if total_cost > 27:
                return False, "Point buy total exceeds 27 points."
        return True, ""

    def get_data(self) -> dict:
        scores = self._get_scores()
        con_mod = (scores["CON"] - 10) // 2
        hp = 8 + con_mod
        if self._class_data:
            hp = 0
            for c in self._class_data:
                cdata = DND5E_CLASSES.get(c.get("name", ""), {})
                hd = cdata.get("hit_die", 8)
                lvl = c.get("level", 1)
                avg = hd // 2 + 1
                hp += (hd + con_mod) + (avg + con_mod) * (lvl - 1)
        return {"stats": scores, "max_hp": max(1, hp)}

    def set_data(self, d: dict):
        stats = d.get("stats", {})
        if not stats:
            return
        if self._btn_standard.isChecked():
            for i, ab in enumerate(ABILITY_NAMES):
                val = stats.get(ab, STANDARD_ARRAY[i])
                idx = self._combos[i].findText(str(val))
                if idx >= 0:
                    self._combos[i].setCurrentIndex(idx)
        else:
            for i, ab in enumerate(ABILITY_NAMES):
                self._spins[i].setValue(stats.get(ab, 10))
        self._update_mods()


# ══════════════════════════════════════════════════════════════════════════════
# Page 5 — Skills
# ══════════════════════════════════════════════════════════════════════════════

class SkillsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._max_choices = 2
        self._checkboxes: dict = {}
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel("Skill Proficiencies")
        title.setStyleSheet(f"color:{_FG}; font-size:20px; font-weight:bold; background:transparent;")
        lay.addWidget(title)

        self._sub = QLabel("Choose your skill proficiencies based on your class.")
        self._sub.setStyleSheet(f"color:{_FG_MID}; background:transparent;")
        self._sub.setWordWrap(True)
        lay.addWidget(self._sub)

        self._counter = QLabel(f"Choose {self._max_choices} more skills")
        self._counter.setStyleSheet(f"color:{_ACCENT}; font-weight:bold; background:transparent;")
        lay.addWidget(self._counter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container.setStyleSheet(f"background:{_BG};")
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        skills_sorted = sorted(ALL_SKILLS.keys())
        for idx, skill in enumerate(skills_sorted):
            ab = ALL_SKILLS[skill]
            col = idx % 2
            row = idx // 2

            row_widget = QWidget()
            row_widget.setStyleSheet(f"background:{_BG2}; border-radius:4px;")
            rh = QHBoxLayout(row_widget)
            rh.setContentsMargins(8, 6, 8, 6)
            rh.setSpacing(6)

            cb = QCheckBox()
            cb.toggled.connect(self._on_check)
            self._checkboxes[skill] = cb
            rh.addWidget(cb)

            skill_lbl = QLabel(skill)
            skill_lbl.setStyleSheet(f"color:{_FG}; background:transparent;")
            rh.addWidget(skill_lbl)

            ab_lbl = QLabel(f"({ab})")
            ab_lbl.setStyleSheet(f"color:{_FG_DIM}; background:transparent; font-size:11px;")
            rh.addWidget(ab_lbl)

            rh.addStretch()
            grid.addWidget(row_widget, row, col)

        scroll.setWidget(container)
        lay.addWidget(scroll, 1)

    def _on_check(self):
        checked = [s for s, cb in self._checkboxes.items() if cb.isChecked()]
        remaining = self._max_choices - len(checked)
        if remaining > 0:
            self._counter.setText(f"Choose {remaining} more skill{'s' if remaining != 1 else ''}")
        else:
            self._counter.setText(f"{len(checked)} of {self._max_choices} skills chosen")
        at_limit = len(checked) >= self._max_choices
        for skill, cb in self._checkboxes.items():
            if not cb.isChecked():
                cb.setEnabled(not at_limit)

    def update_class_data(self, classes: list):
        total_skill_count = sum(
            DND5E_CLASSES.get(c.get("name", ""), {}).get("skill_count", 2)
            for c in classes
        )
        self._max_choices = total_skill_count
        self._counter.setText(f"Choose {self._max_choices} more skills")
        self._on_check()

    def validate(self) -> tuple[bool, str]:
        return True, ""

    def get_data(self) -> dict:
        return {
            "skill_proficiencies": [s for s, cb in self._checkboxes.items() if cb.isChecked()]
        }

    def set_data(self, d: dict):
        profs = d.get("skill_proficiencies", [])
        for skill, cb in self._checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(skill in profs)
            cb.blockSignals(False)
        self._on_check()


# ══════════════════════════════════════════════════════════════════════════════
# Page 6 — Spells
# ══════════════════════════════════════════════════════════════════════════════

class SpellsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        self._spells_data = []
        self._selected_spells: list = []
        self._caster_classes: list = []
        self._total_level = 1
        self._is_caster = False
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr = QWidget()
        hdr.setStyleSheet(f"background:{_BG2}; border-bottom:1px solid {_BORDER};")
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(20, 12, 20, 12)
        hl.setSpacing(4)

        title = QLabel("Select Spells")
        title.setStyleSheet(f"color:{_FG}; font-size:18px; font-weight:bold; background:transparent;")
        hl.addWidget(title)

        self._slots_lbl = QLabel("")
        self._slots_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:12px; background:transparent;")
        self._slots_lbl.setWordWrap(True)
        hl.addWidget(self._slots_lbl)

        lay.addWidget(hdr)

        filter_bar = QWidget()
        filter_bar.setStyleSheet(f"background:{_BG3}; border-bottom:1px solid {_BORDER};")
        fl = QHBoxLayout(filter_bar)
        fl.setContentsMargins(12, 8, 12, 8)
        fl.setSpacing(8)

        self._class_filter = QComboBox()
        self._class_filter.setFixedWidth(140)
        self._class_filter.currentTextChanged.connect(self._apply_filters)
        fl.addWidget(self._class_filter)

        self._level_filter = QComboBox()
        self._level_filter.addItems(["All Levels", "Cantrip", "1", "2", "3", "4", "5", "6", "7", "8", "9"])
        self._level_filter.setFixedWidth(100)
        self._level_filter.currentTextChanged.connect(self._apply_filters)
        fl.addWidget(self._level_filter)

        self._school_filter = QComboBox()
        self._school_filter.addItem("All Schools")
        self._school_filter.addItems(SPELL_SCHOOLS)
        self._school_filter.setFixedWidth(130)
        self._school_filter.currentTextChanged.connect(self._apply_filters)
        fl.addWidget(self._school_filter)

        self._spell_search = QLineEdit()
        self._spell_search.setPlaceholderText("Search spells...")
        self._spell_search.textChanged.connect(self._apply_filters)
        fl.addWidget(self._spell_search, 1)

        lay.addWidget(filter_bar)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(4)

        self._spell_list = QListWidget()
        self._spell_list.currentItemChanged.connect(self._on_spell_select)
        ll.addWidget(self._spell_list)

        add_btn = QPushButton("Add to Spellbook  ->")
        add_btn.setProperty("accent", "true")
        add_btn.clicked.connect(self._add_spell)
        ll.addWidget(add_btn)

        splitter.addWidget(left)

        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(12, 12, 12, 12)
        ml.setSpacing(8)

        self._spell_name_lbl = QLabel("Select a spell")
        self._spell_name_lbl.setStyleSheet(f"color:{_FG}; font-size:16px; font-weight:bold; background:transparent;")
        self._spell_name_lbl.setWordWrap(True)
        ml.addWidget(self._spell_name_lbl)

        self._spell_meta_lbl = QLabel("")
        self._spell_meta_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:11px; background:transparent;")
        self._spell_meta_lbl.setWordWrap(True)
        ml.addWidget(self._spell_meta_lbl)

        self._spell_desc = QTextEdit()
        self._spell_desc.setReadOnly(True)
        self._spell_desc.setStyleSheet(f"background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER}; border-radius:4px; font-size:12px;")
        ml.addWidget(self._spell_desc, 1)

        splitter.addWidget(mid)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 8, 8, 8)
        rl.setSpacing(4)

        lbl = QLabel("Spellbook")
        lbl.setStyleSheet(f"color:{_FG_MID}; font-size:12px; font-weight:bold; background:transparent;")
        rl.addWidget(lbl)

        self._spellbook_list = QListWidget()
        rl.addWidget(self._spellbook_list, 1)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.setStyleSheet(f"background:{_DANGER}; color:white; border:none; border-radius:4px; padding:5px;")
        remove_btn.clicked.connect(self._remove_spell)
        rl.addWidget(remove_btn)

        splitter.addWidget(right)
        splitter.setSizes([250, 350, 200])

        lay.addWidget(splitter, 1)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._load_spells()

    def _load_spells(self):
        self._spells_data = _load_dnd("spells.json")
        self._apply_filters()

    def update_wizard_data(self, classes: list, total_level: int, is_caster: bool):
        self._total_level = total_level
        self._is_caster = is_caster
        self._caster_classes = [
            c["name"] for c in classes
            if DND5E_CLASSES.get(c["name"], {}).get("caster")
        ]

        self._class_filter.blockSignals(True)
        self._class_filter.clear()
        self._class_filter.addItem("All Classes")
        for name in self._caster_classes:
            self._class_filter.addItem(name)
        self._class_filter.blockSignals(False)

        spell_slots = _compute_spell_slots(classes)
        parts = []
        for lvl_str, slot in spell_slots.items():
            if slot["max"] > 0:
                lvl_name = "Cantrip" if lvl_str == "0" else f"Level {lvl_str}"
                parts.append(f"{lvl_name}: {slot['max']} slots")
        self._slots_lbl.setText("Spell slots: " + ", ".join(parts) if parts else "No spell slots available")

        if self._loaded:
            self._apply_filters()

    def _apply_filters(self):
        class_f  = self._class_filter.currentText() if self._class_filter.count() > 0 else "All Classes"
        level_f  = self._level_filter.currentText()
        school_f = self._school_filter.currentText()
        search_q = self._spell_search.text().lower()

        filtered = []
        for spell in self._spells_data:
            name = spell.get("name", "")
            desc = spell.get("description", "")

            if class_f != "All Classes":
                if class_f.lower() not in desc.lower():
                    continue

            if level_f not in ("All Levels", ""):
                spell_lvl = self._extract_spell_level(desc)
                if level_f == "Cantrip" and spell_lvl != 0:
                    continue
                elif level_f != "Cantrip":
                    try:
                        if spell_lvl != int(level_f):
                            continue
                    except ValueError:
                        pass

            if school_f != "All Schools":
                if school_f.lower() not in desc.lower():
                    continue

            if search_q and search_q not in name.lower() and search_q not in desc.lower():
                continue

            filtered.append(spell)

        self._spell_list.clear()
        for spell in filtered[:500]:
            item = QListWidgetItem(spell.get("name", ""))
            item.setData(Qt.UserRole, spell)
            self._spell_list.addItem(item)

    def _extract_spell_level(self, desc: str) -> int:
        desc_lower = desc.lower()
        if "cantrip" in desc_lower[:100]:
            return 0
        for lvl in range(1, 10):
            suffixes = ["st-level", "nd-level", "rd-level", "th-level"]
            for suf in suffixes:
                if f"{lvl}{suf}" in desc_lower[:100]:
                    return lvl
        return -1

    def _on_spell_select(self, item: QListWidgetItem, _=None):
        if item is None:
            return
        spell = item.data(Qt.UserRole)
        if spell is None:
            return
        self._spell_name_lbl.setText(spell.get("name", ""))
        self._spell_desc.setPlainText(spell.get("description", ""))
        desc = spell.get("description", "")
        lines = desc.split("\n")
        meta = lines[0][:200] if lines else ""
        self._spell_meta_lbl.setText(meta)

    def _add_spell(self):
        item = self._spell_list.currentItem()
        if item is None:
            return
        spell = item.data(Qt.UserRole)
        if spell is None:
            return
        name = spell.get("name", "")
        if any(s["name"] == name for s in self._selected_spells):
            return
        desc = spell.get("description", "")
        lvl = self._extract_spell_level(desc)
        if lvl < 0:
            lvl = 0
        school = next((sc for sc in SPELL_SCHOOLS if sc.lower() in desc.lower()), "Unknown")
        self._selected_spells.append({"name": name, "level": lvl, "school": school, "prepared": True})
        self._refresh_spellbook()

    def _remove_spell(self):
        item = self._spellbook_list.currentItem()
        if item is None:
            return
        name = item.data(Qt.UserRole)
        self._selected_spells = [s for s in self._selected_spells if s["name"] != name]
        self._refresh_spellbook()

    def _refresh_spellbook(self):
        self._spellbook_list.clear()
        for spell in self._selected_spells:
            lvl_str = "Cantrip" if spell["level"] == 0 else f"Level {spell['level']}"
            item = QListWidgetItem(f"{spell['name']}  [{lvl_str}]")
            item.setData(Qt.UserRole, spell["name"])
            self._spellbook_list.addItem(item)

    def validate(self) -> tuple[bool, str]:
        return True, ""

    def get_data(self) -> dict:
        return {"spells": self._selected_spells}

    def set_data(self, d: dict):
        self._selected_spells = d.get("spells", [])
        self._refresh_spellbook()


# ══════════════════════════════════════════════════════════════════════════════
# Page 7 — Equipment
# ══════════════════════════════════════════════════════════════════════════════

class EquipmentPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        self._items_data = []
        self._equipment: list = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr = QWidget()
        hdr.setStyleSheet(f"background:{_BG2}; border-bottom:1px solid {_BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 12, 20, 12)
        title = QLabel("Equipment")
        title.setStyleSheet(f"color:{_FG}; font-size:18px; font-weight:bold; background:transparent;")
        hl.addWidget(title)
        lay.addWidget(hdr)

        main = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(6)

        lbl1 = _section_label("Browse Items")
        ll.addWidget(lbl1)

        self._item_search = QLineEdit()
        self._item_search.setPlaceholderText("Search items...")
        self._item_search.textChanged.connect(self._apply_filter)
        ll.addWidget(self._item_search)

        self._type_filter = QComboBox()
        self._type_filter.addItem("All Types")
        self._type_filter.currentTextChanged.connect(self._apply_filter)
        ll.addWidget(self._type_filter)

        self._item_list = QListWidget()
        self._item_list.currentItemChanged.connect(self._on_item_select)
        ll.addWidget(self._item_list, 1)

        self._item_desc = QTextEdit()
        self._item_desc.setReadOnly(True)
        self._item_desc.setFixedHeight(80)
        self._item_desc.setStyleSheet(f"background:{_BG3}; color:{_FG_DIM}; border:1px solid {_BORDER}; border-radius:4px; font-size:11px;")
        ll.addWidget(self._item_desc)

        main.addWidget(left)

        center = QWidget()
        center.setFixedWidth(100)
        cl = QVBoxLayout(center)
        cl.setContentsMargins(8, 8, 8, 8)
        cl.setSpacing(8)
        cl.addStretch()

        qty_lbl = QLabel("Qty")
        qty_lbl.setStyleSheet(f"color:{_FG_MID}; background:transparent; font-size:11px;")
        qty_lbl.setAlignment(Qt.AlignCenter)
        cl.addWidget(qty_lbl)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 999)
        self._qty_spin.setValue(1)
        cl.addWidget(self._qty_spin)

        add_btn = QPushButton("Add ->")
        add_btn.setProperty("accent", "true")
        add_btn.clicked.connect(self._add_item)
        cl.addWidget(add_btn)

        cl.addStretch()
        main.addWidget(center)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 10, 10, 10)
        rl.setSpacing(6)

        lbl2 = _section_label("Character Equipment")
        rl.addWidget(lbl2)

        self._equip_list = QListWidget()
        rl.addWidget(self._equip_list, 1)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.setStyleSheet(f"background:{_DANGER}; color:white; border:none; border-radius:4px; padding:5px;")
        remove_btn.clicked.connect(self._remove_item)
        rl.addWidget(remove_btn)

        custom_frame = QFrame()
        custom_frame.setStyleSheet(f"background:{_BG3}; border:1px solid {_BORDER}; border-radius:6px;")
        cfl = QVBoxLayout(custom_frame)
        cfl.setContentsMargins(10, 8, 10, 8)
        cfl.setSpacing(6)

        clbl = QLabel("Custom Item")
        clbl.setStyleSheet(f"color:{_FG_MID}; font-size:11px; font-weight:bold; background:transparent;")
        cfl.addWidget(clbl)

        cname_row = QHBoxLayout()
        self._custom_name = QLineEdit()
        self._custom_name.setPlaceholderText("Item name...")
        cname_row.addWidget(self._custom_name)

        qty_lbl2 = QLabel("Qty")
        qty_lbl2.setStyleSheet(f"color:{_FG_MID}; background:transparent; font-size:11px;")
        cname_row.addWidget(qty_lbl2)
        self._custom_qty = QSpinBox()
        self._custom_qty.setRange(1, 999)
        self._custom_qty.setFixedWidth(60)
        cname_row.addWidget(self._custom_qty)
        cfl.addLayout(cname_row)

        ctype_row = QHBoxLayout()
        self._custom_type = QComboBox()
        self._custom_type.addItems(["Gear", "Weapon", "Armor", "Potion", "Magic Item", "Tool", "Other"])
        ctype_row.addWidget(self._custom_type)
        custom_add = QPushButton("Add Custom")
        custom_add.setProperty("accent", "true")
        custom_add.clicked.connect(self._add_custom)
        ctype_row.addWidget(custom_add)
        cfl.addLayout(ctype_row)

        rl.addWidget(custom_frame)
        main.addWidget(right)

        main.setSizes([300, 100, 260])
        lay.addWidget(main, 1)

        curr_frame = QFrame()
        curr_frame.setStyleSheet(f"background:{_BG2}; border-top:1px solid {_BORDER};")
        curl = QHBoxLayout(curr_frame)
        curl.setContentsMargins(20, 10, 20, 10)
        curl.setSpacing(16)

        self._currency: dict = {}
        for coin in ["CP", "SP", "EP", "GP", "PP"]:
            vl = QVBoxLayout()
            vl.setSpacing(2)
            lbl = QLabel(coin)
            lbl.setStyleSheet(f"color:{_FG_MID}; font-size:11px; background:transparent;")
            lbl.setAlignment(Qt.AlignCenter)
            spin = QSpinBox()
            spin.setRange(0, 999999)
            spin.setFixedWidth(80)
            self._currency[coin.lower()] = spin
            vl.addWidget(lbl)
            vl.addWidget(spin)
            curl.addLayout(vl)

        curl.addStretch()
        lay.addWidget(curr_frame)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._load_items()

    def _load_items(self):
        self._items_data = _load_dnd("items.json")
        types = set()
        for item in self._items_data:
            props = item.get("properties", {})
            if isinstance(props, dict):
                t = props.get("Item Type", "")
                if t:
                    types.add(t)
        for t in sorted(types):
            self._type_filter.addItem(t)
        self._apply_filter()

    def _apply_filter(self):
        q = self._item_search.text().lower()
        type_f = self._type_filter.currentText()

        self._item_list.clear()
        count = 0
        for item in self._items_data:
            if count >= 500:
                break
            name = item.get("name", "")
            props = item.get("properties", {})
            if not isinstance(props, dict):
                props = {}
            item_type = props.get("Item Type", "Other")

            if type_f != "All Types" and item_type != type_f:
                continue
            if q and q not in name.lower():
                continue

            li = QListWidgetItem(name)
            li.setData(Qt.UserRole, item)
            self._item_list.addItem(li)
            count += 1

    def _on_item_select(self, item: QListWidgetItem, _=None):
        if item is None:
            return
        data = item.data(Qt.UserRole)
        if data is None:
            return
        desc = data.get("description", "")
        self._item_desc.setPlainText(desc[:400])

    def _add_item(self):
        item = self._item_list.currentItem()
        if item is None:
            return
        data = item.data(Qt.UserRole) or {}
        name = data.get("name", item.text())
        qty = self._qty_spin.value()
        props = data.get("properties", {})
        if not isinstance(props, dict):
            props = {}
        item_type = props.get("Item Type", "Gear")
        self._add_to_equipment(name, qty, item_type)

    def _add_custom(self):
        name = self._custom_name.text().strip()
        if not name:
            return
        qty = self._custom_qty.value()
        item_type = self._custom_type.currentText()
        self._add_to_equipment(name, qty, item_type)
        self._custom_name.clear()

    def _add_to_equipment(self, name: str, qty: int, item_type: str):
        for e in self._equipment:
            if e["name"] == name:
                e["quantity"] += qty
                self._refresh_equipment()
                return
        self._equipment.append({"name": name, "quantity": qty, "item_type": item_type})
        self._refresh_equipment()

    def _remove_item(self):
        item = self._equip_list.currentItem()
        if item is None:
            return
        name = item.data(Qt.UserRole)
        self._equipment = [e for e in self._equipment if e["name"] != name]
        self._refresh_equipment()

    def _refresh_equipment(self):
        self._equip_list.clear()
        for e in self._equipment:
            li = QListWidgetItem(f"{e['name']}  x{e['quantity']}")
            li.setData(Qt.UserRole, e["name"])
            self._equip_list.addItem(li)

    def validate(self) -> tuple[bool, str]:
        return True, ""

    def get_data(self) -> dict:
        currency = {coin: spin.value() for coin, spin in self._currency.items()}
        return {"equipment": self._equipment, "currency": currency}

    def set_data(self, d: dict):
        self._equipment = d.get("equipment", [])
        self._refresh_equipment()
        currency = d.get("currency", {})
        for coin, spin in self._currency.items():
            spin.setValue(currency.get(coin, 0))


# ══════════════════════════════════════════════════════════════════════════════
# Page 8 — Personality
# ══════════════════════════════════════════════════════════════════════════════

class PersonalityPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_data: dict = {}
        self._active_field: Optional[QTextEdit] = None
        self._build()

    def _build(self):
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setStyleSheet(f"background:{_BG};")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        title = QLabel("Personality & Traits")
        title.setStyleSheet(f"color:{_FG}; font-size:20px; font-weight:bold; background:transparent;")
        lay.addWidget(title)

        self._bg_label = QLabel("Suggestions from background:")
        self._bg_label.setStyleSheet(f"color:{_FG_MID}; font-size:12px; background:transparent;")
        lay.addWidget(self._bg_label)

        self._chips_frame = QFrame()
        self._chips_frame.setStyleSheet(f"background:{_BG2}; border:1px solid {_BORDER}; border-radius:6px;")
        self._chips_layout = QVBoxLayout(self._chips_frame)
        self._chips_layout.setContentsMargins(10, 8, 10, 8)
        self._chips_layout.setSpacing(4)
        lay.addWidget(self._chips_frame)

        self._fields: dict = {}
        self._roll_btns: dict = {}
        self._bg_suggestions: dict = {
            "traits": [], "ideals": [], "bonds": [], "flaws": [],
        }

        sections = [
            ("traits",  "Personality Traits",  "What are your character's defining traits?"),
            ("ideals",  "Ideals",               "What beliefs drive your character?"),
            ("bonds",   "Bonds",                "Who or what is your character devoted to?"),
            ("flaws",   "Flaws",                "What are your character's weaknesses?"),
        ]

        for key, label, placeholder in sections:
            section_frame = QFrame()
            section_frame.setStyleSheet(f"background:{_BG3}; border:1px solid {_BORDER}; border-radius:6px;")
            sf = QVBoxLayout(section_frame)
            sf.setContentsMargins(12, 10, 12, 10)
            sf.setSpacing(6)

            hrow = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{_FG}; font-weight:bold; background:transparent;")
            hrow.addWidget(lbl)
            hrow.addStretch()

            roll_btn = QPushButton("Roll / Suggest")
            roll_btn.setStyleSheet(f"background:{_BG2}; color:{_ACCENT}; border:1px solid {_BORDER2}; border-radius:4px; padding:3px 10px; font-size:11px;")
            roll_btn.clicked.connect(lambda checked=False, k=key: self._roll_suggest(k))
            self._roll_btns[key] = roll_btn
            hrow.addWidget(roll_btn)
            sf.addLayout(hrow)

            txt = QTextEdit()
            txt.setPlaceholderText(placeholder)
            txt.setFixedHeight(70)
            txt.focusInEvent = lambda e, t=txt: self._set_active(t)
            self._fields[key] = txt
            sf.addWidget(txt)

            lay.addWidget(section_frame)

        lay.addStretch()
        outer.setWidget(content)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.addWidget(outer)

    def _set_active(self, field: QTextEdit):
        self._active_field = field

    def _roll_suggest(self, key: str):
        suggestions = self._bg_suggestions.get(key, [])
        if suggestions:
            pick = random.choice(suggestions)
            if self._fields[key]:
                current = self._fields[key].toPlainText().strip()
                if current:
                    self._fields[key].setPlainText(current + "\n" + pick)
                else:
                    self._fields[key].setPlainText(pick)

    def _parse_suggestions(self, raw_val) -> list:
        if isinstance(raw_val, str):
            try:
                parsed = json.loads(raw_val)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
                return [str(parsed)]
            except Exception:
                return [raw_val] if raw_val else []
        elif isinstance(raw_val, list):
            return [str(x) for x in raw_val]
        return []

    def update_background_data(self, bg_data: dict):
        self._bg_data = bg_data
        props = bg_data.get("properties", {})
        if not isinstance(props, dict):
            props = {}

        bg_name = bg_data.get("name", "Background")
        self._bg_label.setText(f"Suggestions from {bg_name}:")

        self._bg_suggestions = {
            "traits": self._parse_suggestions(props.get("data-Personality Traits", [])),
            "ideals": self._parse_suggestions(props.get("data-Ideals", [])),
            "bonds":  self._parse_suggestions(props.get("data-Bonds", [])),
            "flaws":  self._parse_suggestions(props.get("data-Flaws", [])),
        }

        for i in reversed(range(self._chips_layout.count())):
            widget = self._chips_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        key_map = {"traits": "Traits", "ideals": "Ideals", "bonds": "Bonds", "flaws": "Flaws"}
        for key, label in key_map.items():
            suggestions = self._bg_suggestions[key]
            if not suggestions:
                continue
            row_lbl = QLabel(f"{label}:")
            row_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent;")
            self._chips_layout.addWidget(row_lbl)

            chips_row = QWidget()
            chips_row.setStyleSheet("background:transparent;")
            cl = QHBoxLayout(chips_row)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(4)
            for sug in suggestions[:3]:
                chip = QPushButton(sug[:40] + ("..." if len(sug) > 40 else ""))
                chip.setStyleSheet(f"background:{_BG}; color:{_ACCENT}; border:1px solid {_BORDER2}; border-radius:4px; padding:3px 8px; font-size:10px;")
                chip.setToolTip(sug)
                chip.clicked.connect(lambda checked=False, k=key, s=sug: self._insert_suggestion(k, s))
                cl.addWidget(chip)
            cl.addStretch()
            self._chips_layout.addWidget(chips_row)

    def _insert_suggestion(self, key: str, text: str):
        field = self._fields.get(key)
        if field:
            current = field.toPlainText().strip()
            field.setPlainText((current + "\n" + text).strip())

    def validate(self) -> tuple[bool, str]:
        return True, ""

    def get_data(self) -> dict:
        return {
            "personality": {
                "traits": self._fields["traits"].toPlainText().strip(),
                "ideals": self._fields["ideals"].toPlainText().strip(),
                "bonds":  self._fields["bonds"].toPlainText().strip(),
                "flaws":  self._fields["flaws"].toPlainText().strip(),
            },
            "notes": "",
        }

    def set_data(self, d: dict):
        p = d.get("personality", {})
        for key, field in self._fields.items():
            field.setPlainText(p.get(key, ""))


# ══════════════════════════════════════════════════════════════════════════════
# Page 9 — Review
# ══════════════════════════════════════════════════════════════════════════════

class ReviewPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setStyleSheet(f"background:{_BG};")
        self._lay = QVBoxLayout(content)
        self._lay.setContentsMargins(24, 20, 24, 20)
        self._lay.setSpacing(16)

        self._placeholder = QLabel("Complete the previous steps to see your character summary.")
        self._placeholder.setStyleSheet(f"color:{_FG_MID}; background:transparent;")
        self._lay.addWidget(self._placeholder)
        self._lay.addStretch()

        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _clear_layout(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh(self, data: dict):
        self._clear_layout()

        # Hero banner
        banner = QFrame()
        banner.setStyleSheet(f"background:{_BG2}; border:1px solid {_BORDER2}; border-radius:8px;")
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(6)

        name = data.get("name", "Unknown Hero")
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color:{_FG}; font-size:26px; font-weight:bold; background:transparent;")
        bl.addWidget(name_lbl)

        role = data.get("character_role", "Player Character")
        race = data.get("race", "Unknown")
        classes = data.get("classes", [])
        alignment = data.get("alignment", "")
        total_level = data.get("total_level", 1)

        if classes:
            class_str = " / ".join(f"{c['name']} {c['level']}" for c in classes)
            class_str += f" (Level {total_level})"
        else:
            class_str = "No class selected"

        race_class_lbl = QLabel(f"{race}  {class_str}")
        race_class_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:14px; background:transparent;")
        bl.addWidget(race_class_lbl)

        meta_row = QHBoxLayout()
        role_badge = QLabel(role)
        role_badge.setStyleSheet(f"background:{_ACCENT}; color:white; border-radius:4px; padding:2px 8px; font-size:11px;")
        meta_row.addWidget(role_badge)

        if alignment:
            align_lbl = QLabel(alignment)
            align_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:12px; background:transparent;")
            meta_row.addWidget(align_lbl)
        meta_row.addStretch()
        bl.addLayout(meta_row)

        self._lay.addWidget(banner)

        # Stats grid
        stats = data.get("stats", {})
        if stats:
            stats_frame = QFrame()
            stats_frame.setStyleSheet(f"background:{_BG3}; border:1px solid {_BORDER}; border-radius:6px;")
            sl = QGridLayout(stats_frame)
            sl.setContentsMargins(16, 12, 16, 12)
            sl.setSpacing(10)

            for i, ab in enumerate(ABILITY_NAMES):
                col = i
                score = stats.get(ab, 10)
                mod_str = _mod(score)

                ab_lbl = QLabel(ab)
                ab_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; font-weight:bold; background:transparent; letter-spacing:1px;")
                ab_lbl.setAlignment(Qt.AlignCenter)
                sl.addWidget(ab_lbl, 0, col)

                score_lbl = QLabel(str(score))
                score_lbl.setStyleSheet(f"color:{_FG}; font-size:20px; font-weight:bold; background:transparent;")
                score_lbl.setAlignment(Qt.AlignCenter)
                sl.addWidget(score_lbl, 1, col)

                mod_lbl = QLabel(mod_str)
                color = _SUCCESS if not mod_str.startswith("-") else _DANGER
                mod_lbl.setStyleSheet(f"color:{color}; font-size:13px; font-weight:bold; background:transparent;")
                mod_lbl.setAlignment(Qt.AlignCenter)
                sl.addWidget(mod_lbl, 2, col)

            self._lay.addWidget(stats_frame)

        # Proficiencies
        skills = data.get("skill_proficiencies", [])
        if skills:
            self._add_section("Skill Proficiencies", ", ".join(skills))

        saves_from_classes = set()
        for c in classes:
            cdata = DND5E_CLASSES.get(c.get("name", ""), {})
            for s in cdata.get("saves", []):
                saves_from_classes.add(s)
        if saves_from_classes:
            self._add_section("Saving Throw Proficiencies", ", ".join(sorted(saves_from_classes)))

        # Max HP
        max_hp = data.get("max_hp", 0)
        if max_hp:
            self._add_section("Max Hit Points", str(max_hp))

        # Spells
        spells = data.get("spells", [])
        if spells:
            by_level: dict = {}
            for sp in spells:
                lvl = sp.get("level", 0)
                by_level.setdefault(lvl, []).append(sp["name"])
            parts = []
            if 0 in by_level:
                parts.append(f"Cantrips: {', '.join(by_level[0])}")
            for lvl in sorted(k for k in by_level if k > 0):
                parts.append(f"Level {lvl}: {', '.join(by_level[lvl])}")
            self._add_section("Spells", "\n".join(parts))

        # Equipment
        equipment = data.get("equipment", [])
        if equipment:
            equip_str = ", ".join(f"{e['name']} x{e['quantity']}" for e in equipment)
            self._add_section("Equipment", equip_str)

        # Currency
        currency = data.get("currency", {})
        if any(v > 0 for v in currency.values()):
            curr_parts = [f"{v} {k.upper()}" for k, v in currency.items() if v > 0]
            self._add_section("Currency", ", ".join(curr_parts))

        # Personality
        personality = data.get("personality", {})
        if personality:
            traits = personality.get("traits", "")
            if traits:
                self._add_section("Personality", traits[:200] + ("..." if len(traits) > 200 else ""))

        # Appearance
        appearance = data.get("appearance_notes", "")
        if appearance:
            self._add_section("Appearance", appearance[:300])

        self._lay.addStretch()

    def _add_section(self, label: str, value: str):
        frame = QFrame()
        frame.setStyleSheet(f"background:{_BG3}; border:1px solid {_BORDER}; border-radius:6px;")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(4)

        lbl = QLabel(label.upper())
        lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; letter-spacing:1.5px; font-weight:bold; background:transparent;")
        fl.addWidget(lbl)

        val = QLabel(value)
        val.setStyleSheet(f"color:{_FG}; background:transparent;")
        val.setWordWrap(True)
        fl.addWidget(val)

        self._lay.addWidget(frame)

    def validate(self) -> tuple[bool, str]:
        return True, ""

    def get_data(self) -> dict:
        return {}

    def set_data(self, d: dict):
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Main Wizard
# ══════════════════════════════════════════════════════════════════════════════

_STEP_NAMES = [
    "Concept",
    "Species",
    "Class",
    "Background",
    "Ability Scores",
    "Skills",
    "Spells",
    "Equipment",
    "Personality",
    "Review",
]


class CharacterCreatorWizard(QDialog):
    character_created = Signal(dict)

    def __init__(self, campaign_id: int, service, parent=None):
        super().__init__(parent)
        self._campaign_id = campaign_id
        self._service = service
        self._data: dict = {}
        self._current = 0

        self.setWindowTitle("D&D 5e Character Creator")
        self.setMinimumSize(900, 700)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.setStyleSheet(_base_style())

        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"background:{_SIDEBAR}; border-right:1px solid {_BORDER};")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        logo_frame = QFrame()
        logo_frame.setStyleSheet(f"background:{_BG2}; border-bottom:1px solid {_BORDER};")
        lf = QVBoxLayout(logo_frame)
        lf.setContentsMargins(16, 16, 16, 16)
        logo_lbl = QLabel("Character Creator")
        logo_lbl.setStyleSheet(f"color:{_FG}; font-size:13px; font-weight:bold; background:transparent;")
        logo_lbl.setWordWrap(True)
        lf.addWidget(logo_lbl)
        sl.addWidget(logo_frame)

        self._step_btns: list = []
        steps_container = QWidget()
        steps_container.setStyleSheet(f"background:{_SIDEBAR};")
        scl = QVBoxLayout(steps_container)
        scl.setContentsMargins(0, 8, 0, 8)
        scl.setSpacing(0)

        for i, name in enumerate(_STEP_NAMES):
            btn = QPushButton(f"  {i + 1}.  {name}")
            btn.setFixedHeight(38)
            btn.setStyleSheet(self._step_style(i, active=False))
            btn.setEnabled(False)
            self._step_btns.append(btn)
            scl.addWidget(btn)

        scl.addStretch()
        sl.addWidget(steps_container, 1)
        root.addWidget(sidebar)

        # Content area
        content_area = QVBoxLayout()
        content_area.setContentsMargins(0, 0, 0, 0)
        content_area.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background:{_BG};")

        self._pages: list = [
            ConceptPage(),
            SpeciesPage(),
            ClassPage(),
            BackgroundPage(),
            AbilityScoresPage(),
            SkillsPage(),
            SpellsPage(),
            EquipmentPage(),
            PersonalityPage(),
            ReviewPage(),
        ]

        for page in self._pages:
            self._stack.addWidget(page)

        content_area.addWidget(self._stack, 1)

        # Navigation bar
        nav_frame = QFrame()
        nav_frame.setStyleSheet(f"background:{_BG2}; border-top:1px solid {_BORDER};")
        nav_frame.setFixedHeight(56)
        nl = QHBoxLayout(nav_frame)
        nl.setContentsMargins(20, 0, 20, 0)
        nl.setSpacing(12)

        self._back_btn = QPushButton("<- Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.clicked.connect(self._go_back)
        nl.addWidget(self._back_btn)

        nl.addStretch()

        self._step_counter = QLabel(f"Step 1 of {len(_STEP_NAMES)}")
        self._step_counter.setStyleSheet(f"color:{_FG_MID}; background:transparent;")
        nl.addWidget(self._step_counter)

        nl.addStretch()

        self._next_btn = QPushButton("Next ->")
        self._next_btn.setFixedWidth(160)
        self._next_btn.setProperty("accent", "true")
        self._next_btn.clicked.connect(self._go_next)
        nl.addWidget(self._next_btn)

        content_area.addWidget(nav_frame)
        root.addLayout(content_area)

        self._update_sidebar()
        self._update_nav()

    def _step_style(self, idx: int, active: bool) -> str:
        if active:
            return (
                f"background:{_BG3}; color:{_ACCENT}; "
                f"border:none; border-left:3px solid {_ACCENT}; "
                f"text-align:left; padding-left:13px; font-weight:bold;"
            )
        return (
            f"background:transparent; color:{_FG_MID}; "
            f"border:none; border-left:3px solid transparent; "
            f"text-align:left; padding-left:13px;"
        )

    def _update_sidebar(self):
        for i, btn in enumerate(self._step_btns):
            btn.setStyleSheet(self._step_style(i, active=(i == self._current)))

    def _update_nav(self):
        self._back_btn.setEnabled(self._current > 0)
        self._step_counter.setText(f"Step {self._current + 1} of {len(_STEP_NAMES)}")

        is_last = (self._current == len(_STEP_NAMES) - 1)
        self._next_btn.setText("Create Character" if is_last else "Next ->")

    def _is_caster(self) -> bool:
        class_data = self._data.get("classes", [])
        return any(DND5E_CLASSES.get(c.get("name", ""), {}).get("caster") for c in class_data)

    def _go_next(self):
        page = self._pages[self._current]

        ok, msg = page.validate()
        if not ok:
            QMessageBox.warning(self, "Validation", msg)
            return

        page_data = page.get_data()
        self._data.update(page_data)

        if self._current == len(_STEP_NAMES) - 1:
            self._create_character()
            return

        next_idx = self._current + 1
        if next_idx == 6 and not self._is_caster():
            next_idx = 7

        self._propagate_data(next_idx)

        self._current = next_idx
        self._stack.setCurrentIndex(self._current)
        self._update_sidebar()
        self._update_nav()

    def _go_back(self):
        if self._current == 0:
            return
        prev_idx = self._current - 1
        if prev_idx == 6 and not self._is_caster():
            prev_idx = 5
        self._current = prev_idx
        self._stack.setCurrentIndex(self._current)
        self._update_sidebar()
        self._update_nav()

    def _propagate_data(self, next_idx: int):
        if next_idx == 4:
            classes = self._data.get("classes", [])
            self._pages[4].update_class_data(classes)

        elif next_idx == 5:
            classes = self._data.get("classes", [])
            self._pages[5].update_class_data(classes)

        elif next_idx == 6:
            classes = self._data.get("classes", [])
            total_level = self._data.get("total_level", 1)
            is_caster = self._data.get("is_caster", False)
            self._pages[6].update_wizard_data(classes, total_level, is_caster)

        elif next_idx == 8:
            bg_name = self._data.get("background", "")
            if bg_name:
                bg_list = _load_dnd("backgrounds.json")
                for bg in bg_list:
                    if bg.get("name") == bg_name:
                        self._pages[8].update_background_data(bg)
                        break

        elif next_idx == 9:
            self._pages[9].refresh(self._data)

    def _create_character(self):
        try:
            data = self._data
            name = data.get("name", "Unnamed")
            role = data.get("character_role", "Player Character")
            race = data.get("race", "")
            primary_class = data.get("primary_class", "")
            total_level = data.get("total_level", 1)
            background = data.get("background", "")
            stats = data.get("stats", {})
            max_hp = data.get("max_hp", 10)
            appearance_notes = data.get("appearance_notes", "")
            personality = data.get("personality", {})
            personality_traits = personality.get("traits", "")

            dex_mod = (stats.get("DEX", 10) - 10) // 2
            ac = 10 + dex_mod

            classes = data.get("classes", [])
            spell_slots_dict = _compute_spell_slots(classes)

            char_id = self._service.create_character(
                self._campaign_id,
                name,
                character_role=role,
                character_class=primary_class,
                race=race,
                level=total_level,
                background=background,
                stats_json=json.dumps(stats),
                max_hit_points=max_hp,
                hit_points=max_hp,
                armor_class=ac,
                stat_style="D&D 5e",
                traits=personality_traits,
                notes=appearance_notes,
                spell_slots_json=json.dumps(spell_slots_dict),
            )

            if char_id:
                for spell in data.get("spells", []):
                    try:
                        self._service.add_character_spell(
                            char_id,
                            spell["name"],
                            spell["level"],
                        )
                    except Exception:
                        pass

                for item in data.get("equipment", []):
                    try:
                        self._service.add_inventory_item(
                            char_id,
                            item["name"],
                            item.get("quantity", 1),
                            item.get("item_type", "Gear"),
                        )
                    except Exception:
                        pass

                skill_profs = data.get("skill_proficiencies", [])
                saves = []
                for c in classes:
                    cdata = DND5E_CLASSES.get(c.get("name", ""), {})
                    for s in cdata.get("saves", []):
                        if s not in saves:
                            saves.append(s)

                ext_data = {
                    "classes": classes,
                    "skills": skill_profs,
                    "saving_throws": saves,
                    "personality": personality,
                    "features": [],
                    "appearance": appearance_notes,
                    "proficiencies": {
                        "skills": skill_profs,
                        "saving_throws": saves,
                        "armor": [],
                        "weapons": [],
                        "tools": [],
                        "languages": [],
                    },
                    "currency": data.get("currency", {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}),
                    "alignment": data.get("alignment", ""),
                    "background": background,
                    "species_description": data.get("species_description", ""),
                    "stat_method": "Standard Array",
                }

                try:
                    self._service.save_character_ext(char_id, ext_data)
                except Exception:
                    pass

            self.character_created.emit(data)
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error Creating Character", str(e))
