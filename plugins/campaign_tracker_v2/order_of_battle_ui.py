"""
Campaign Tracker v2 — Order of Battle UI.

Provides a persistent unit roster per campaign connecting the Rules Library
to the Army Builder.  Supports 40K, AoS, D&D 5e, and custom game systems.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QListWidget, QListWidgetItem, QSplitter, QDialog,
    QDialogButtonBox, QLineEdit, QComboBox, QSpinBox, QTextEdit,
    QStackedWidget, QCheckBox, QFormLayout, QMessageBox, QApplication,
    QSizePolicy, QGroupBox, QTabWidget,
)
from PySide6.QtGui import QFont

log = logging.getLogger(__name__)

# ── Palette ───────────────────────────────────────────────────────────────────
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

# System accent colors for the unit card left strip
_SYS_COLORS = {
    "wh40k":  _DANGER,
    "aos":    _SUCCESS,
    "dnd5e":  "#9b59b6",
    "custom": _ACCENT,
}

_SCROLLBAR_STYLE = f"""
    QScrollBar:vertical {{
        background: {_BG}; width: 6px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {_BORDER2}; border-radius: 3px; min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
"""

# ── System roles ──────────────────────────────────────────────────────────────

SYSTEM_ROLES = {
    "wh40k": [
        "HQ", "Troops", "Elites", "Fast Attack", "Heavy Support",
        "Flyer", "Dedicated Transport", "Lord of War", "Allied Units", "Other",
    ],
    "aos": ["Leader", "Battleline", "Artillery", "Behemoth", "Other"],
    "dnd5e": ["Player Character", "NPC", "Monster", "Vehicle", "Other"],
    "custom": ["Commander", "Infantry", "Support", "Elite", "Special", "Other"],
}

ALL_ROLES = [
    "HQ", "Troops", "Elites", "Fast Attack", "Heavy Support",
    "Flyer", "Dedicated Transport", "Lord of War", "Allied Units",
    "Leader", "Battleline", "Artillery", "Behemoth",
    "Player Character", "NPC", "Monster", "Vehicle",
    "Commander", "Infantry", "Support", "Elite", "Special", "Other",
]


def get_roles_for_system(system_id: str) -> list[str]:
    return SYSTEM_ROLES.get(system_id, SYSTEM_ROLES["custom"])


# ── Shared stat-block widget helpers (duplicated from rules_library_ui.py) ────

def _section_header(title: str) -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        f"background: {_BG3}; border-left: 4px solid {_ACCENT}; "
        f"border-radius: 2px;"
    )
    lay = QHBoxLayout(f)
    lay.setContentsMargins(12, 6, 12, 6)
    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        f"color: {_FG_DIM}; font-size: 10px; font-weight: 700; "
        f"letter-spacing: 2px; background: transparent; border: none;"
    )
    lay.addWidget(lbl)
    lay.addStretch()
    return f


def _stat_cell(label: str, value: str, accent_color: str = _ACCENT) -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        f"background: {_BG3}; border: 1px solid {_BORDER}; border-radius: 4px;"
    )
    lay = QVBoxLayout(f)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(2)
    val_lbl = QLabel(str(value) if value else "—")
    val_lbl.setAlignment(Qt.AlignCenter)
    val_lbl.setStyleSheet(
        f"color: {_FG}; font-size: 18px; font-weight: 700; "
        f"background: transparent; border: none;"
    )
    key_lbl = QLabel(label)
    key_lbl.setAlignment(Qt.AlignCenter)
    key_lbl.setStyleSheet(
        f"color: {accent_color}; font-size: 9px; font-weight: 600; "
        f"letter-spacing: 1px; background: transparent; border: none;"
    )
    lay.addWidget(val_lbl)
    lay.addWidget(key_lbl)
    return f


def _weapons_table(headers: list[str], rows: list[list[str]]) -> QFrame:
    from PySide6.QtWidgets import QGridLayout
    f = QFrame()
    f.setStyleSheet(f"background: {_BG2}; border: none;")
    grid = QGridLayout(f)
    grid.setSpacing(0)
    grid.setContentsMargins(0, 0, 0, 0)
    for col, h in enumerate(headers):
        lbl = QLabel(h)
        lbl.setStyleSheet(
            f"background: {_BG3}; color: {_FG_DIM}; font-size: 10px; "
            f"font-weight: 600; padding: 4px 8px; border: none;"
        )
        lbl.setAlignment(Qt.AlignCenter)
        grid.addWidget(lbl, 0, col)
    for row_idx, row in enumerate(rows):
        bg = _BG2 if row_idx % 2 == 0 else _BG3
        for col, val in enumerate(row):
            lbl = QLabel(str(val) if val else "—")
            if col == 0:
                lbl.setStyleSheet(
                    f"background: {bg}; color: {_FG}; font-size: 11px; "
                    f"padding: 5px 8px; border: none; font-weight: 500;"
                )
                lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            else:
                lbl.setStyleSheet(
                    f"background: {bg}; color: {_FG_MID}; font-size: 11px; "
                    f"padding: 5px 8px; border: none;"
                )
                lbl.setAlignment(Qt.AlignCenter)
            grid.addWidget(lbl, row_idx + 1, col)
    grid.setColumnStretch(0, 2)
    return f


def _divider() -> QFrame:
    d = QFrame()
    d.setStyleSheet(
        f"background: {_BORDER}; border: none; min-height: 1px; max-height: 1px;"
    )
    return d


def _badge(text: str, color: str = _ACCENT) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background: {color}22; color: {color}; border: 1px solid {color}44; "
        f"border-radius: 3px; font-size: 10px; font-weight: 600; padding: 2px 6px;"
    )
    return lbl


def _ability_card(name: str, effect: str) -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        f"background: {_BG3}; border-left: 3px solid {_ACCENT}; "
        f"border-radius: 3px; margin-bottom: 4px;"
    )
    lay = QVBoxLayout(f)
    lay.setContentsMargins(10, 8, 10, 8)
    lay.setSpacing(3)
    if name:
        n = QLabel(f"✦  {name}")
        n.setStyleSheet(
            f"color: {_FG}; font-size: 12px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        n.setWordWrap(True)
        lay.addWidget(n)
    if effect:
        e = QLabel(effect)
        e.setStyleSheet(
            f"color: {_FG_MID}; font-size: 11px; background: transparent; border: none;"
        )
        e.setWordWrap(True)
        lay.addWidget(e)
    return f


# ── Stat block builders ───────────────────────────────────────────────────────

def _build_wh40k_detail(entity: dict) -> QWidget:
    from PySide6.QtWidgets import QGridLayout
    data = entity.get("data", {})
    w = QWidget()
    w.setStyleSheet(f"background: {_BG2};")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)

    # Core stats row
    stat_keys = [
        ("M",  "Move"),
        ("T",  "Toughness"),
        ("SV", "Save"),
        ("W",  "Wounds"),
        ("LD", "Leadership"),
        ("OC", "OC"),
    ]
    stats_row = QHBoxLayout()
    stats_row.setSpacing(4)
    for key, label in stat_keys:
        val = str(data.get(key, data.get(key.lower(), "—")))
        stats_row.addWidget(_stat_cell(label, val, _DANGER))
    lay.addLayout(stats_row)

    # Ranged weapons
    ranged = data.get("rangedWeapons", data.get("ranged_weapons", []))
    if ranged:
        lay.addWidget(_section_header("Ranged Weapons"))
        headers = ["Weapon", "Range", "A", "BS", "S", "AP", "D", "Keywords"]
        rows = []
        for wep in ranged:
            if isinstance(wep, dict):
                rows.append([
                    wep.get("name", ""),
                    wep.get("range", "—"),
                    str(wep.get("attacks", wep.get("A", "—"))),
                    str(wep.get("bs", wep.get("BS", "—"))),
                    str(wep.get("strength", wep.get("S", "—"))),
                    str(wep.get("ap", wep.get("AP", "—"))),
                    str(wep.get("damage", wep.get("D", "—"))),
                    ", ".join(wep.get("keywords", [])) if isinstance(wep.get("keywords"), list) else str(wep.get("keywords", "")),
                ])
        if rows:
            lay.addWidget(_weapons_table(headers, rows))

    # Melee weapons
    melee = data.get("meleeWeapons", data.get("melee_weapons", []))
    if melee:
        lay.addWidget(_section_header("Melee Weapons"))
        headers = ["Weapon", "Range", "A", "WS", "S", "AP", "D", "Keywords"]
        rows = []
        for wep in melee:
            if isinstance(wep, dict):
                rows.append([
                    wep.get("name", ""),
                    wep.get("range", "Melee"),
                    str(wep.get("attacks", wep.get("A", "—"))),
                    str(wep.get("ws", wep.get("WS", "—"))),
                    str(wep.get("strength", wep.get("S", "—"))),
                    str(wep.get("ap", wep.get("AP", "—"))),
                    str(wep.get("damage", wep.get("D", "—"))),
                    ", ".join(wep.get("keywords", [])) if isinstance(wep.get("keywords"), list) else str(wep.get("keywords", "")),
                ])
        if rows:
            lay.addWidget(_weapons_table(headers, rows))

    # Abilities
    abilities = data.get("abilities", [])
    if abilities:
        lay.addWidget(_section_header("Abilities"))
        for ab in abilities:
            if isinstance(ab, dict):
                lay.addWidget(_ability_card(ab.get("name", ""), ab.get("effect", ab.get("description", ""))))
            elif isinstance(ab, str):
                lay.addWidget(_ability_card("", ab))

    # Keywords
    kw = data.get("keywords", [])
    faction_kw = data.get("factionKeywords", data.get("faction_keywords", []))
    if kw or faction_kw:
        lay.addWidget(_section_header("Keywords"))
        kw_row = QHBoxLayout()
        kw_row.setSpacing(6)
        all_kw = (kw if isinstance(kw, list) else [kw]) + (faction_kw if isinstance(faction_kw, list) else [])
        for k in all_kw:
            if k:
                kw_row.addWidget(_badge(str(k), _FG_DIM))
        kw_row.addStretch()
        lay.addLayout(kw_row)

    lay.addStretch()
    return w


def _build_aos_detail(entity: dict) -> QWidget:
    data = entity.get("data", {})
    w = QWidget()
    w.setStyleSheet(f"background: {_BG2};")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)

    # Core stats
    stat_keys = [
        ("Move",       "Move"),
        ("Health",     "Health"),
        ("Save",       "Save"),
        ("Bravery",    "Bravery"),
        ("Wounds",     "Wounds"),
    ]
    stats_row = QHBoxLayout()
    stats_row.setSpacing(4)
    for key, label in stat_keys:
        val = str(data.get(key, data.get(key.lower(), "—")))
        stats_row.addWidget(_stat_cell(label, val, _SUCCESS))
    lay.addLayout(stats_row)

    # Weapons / attacks
    attacks = data.get("attacks", data.get("weapons", []))
    if attacks:
        lay.addWidget(_section_header("Attacks"))
        headers = ["Weapon", "Range", "Attacks", "Hit", "Wound", "Rend", "Dmg"]
        rows = []
        for wep in attacks:
            if isinstance(wep, dict):
                rows.append([
                    wep.get("name", ""),
                    wep.get("range", "—"),
                    str(wep.get("attacks", "—")),
                    str(wep.get("hit", "—")),
                    str(wep.get("wound", "—")),
                    str(wep.get("rend", "—")),
                    str(wep.get("damage", "—")),
                ])
        if rows:
            lay.addWidget(_weapons_table(headers, rows))

    # Abilities
    abilities = data.get("abilities", [])
    if abilities:
        lay.addWidget(_section_header("Abilities"))
        for ab in abilities:
            if isinstance(ab, dict):
                lay.addWidget(_ability_card(ab.get("name", ""), ab.get("effect", ab.get("description", ""))))
            elif isinstance(ab, str):
                lay.addWidget(_ability_card("", ab))

    # Keywords
    kw = data.get("keywords", [])
    if kw:
        lay.addWidget(_section_header("Keywords"))
        kw_row = QHBoxLayout()
        kw_row.setSpacing(6)
        for k in (kw if isinstance(kw, list) else [kw]):
            if k:
                kw_row.addWidget(_badge(str(k), _SUCCESS))
        kw_row.addStretch()
        lay.addLayout(kw_row)

    lay.addStretch()
    return w


def _build_dnd_detail(entity: dict) -> QWidget:
    data = entity.get("data", {})
    w = QWidget()
    w.setStyleSheet(f"background: {_BG2};")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)

    # Ability scores
    abilities_data = data.get("abilityScores", data.get("ability_scores", {}))
    if abilities_data and isinstance(abilities_data, dict):
        ab_keys = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
        stats_row = QHBoxLayout()
        stats_row.setSpacing(4)

        def _mod(score):
            try:
                return int(score)
            except Exception:
                return 10

        for ab in ab_keys:
            score = abilities_data.get(ab, abilities_data.get(ab.lower(), "—"))
            try:
                mod_val = (_mod(score) - 10) // 2
                mod_str = f"+{mod_val}" if mod_val >= 0 else str(mod_val)
                display = f"{score}\n({mod_str})"
            except Exception:
                display = str(score)
            stats_row.addWidget(_stat_cell(ab, display, "#9b59b6"))
        lay.addLayout(stats_row)

    # Core stats row
    meta_keys = [
        ("AC",          "ac",           "Armor Class"),
        ("HP",          "hp",           "Hit Points"),
        ("Speed",       "speed",        "Speed"),
        ("CR",          "cr",           "Challenge"),
        ("Prof Bonus",  "profBonus",    "Prof. Bonus"),
    ]
    meta_row = QHBoxLayout()
    meta_row.setSpacing(4)
    for label, key, full_label in meta_keys:
        val = str(data.get(key, data.get(label, "—")))
        meta_row.addWidget(_stat_cell(full_label, val, "#9b59b6"))
    lay.addLayout(meta_row)

    # Actions
    actions = data.get("actions", [])
    if actions:
        lay.addWidget(_section_header("Actions"))
        for act in actions:
            if isinstance(act, dict):
                lay.addWidget(_ability_card(act.get("name", ""), act.get("desc", act.get("description", ""))))
            elif isinstance(act, str):
                lay.addWidget(_ability_card("", act))

    # Traits / Special Abilities
    traits = data.get("specialAbilities", data.get("traits", data.get("special_abilities", [])))
    if traits:
        lay.addWidget(_section_header("Traits & Special Abilities"))
        for tr in traits:
            if isinstance(tr, dict):
                lay.addWidget(_ability_card(tr.get("name", ""), tr.get("desc", tr.get("description", ""))))
            elif isinstance(tr, str):
                lay.addWidget(_ability_card("", tr))

    lay.addStretch()
    return w


def _build_generic_detail(entity: dict) -> QWidget:
    data = entity.get("data", {})
    w = QWidget()
    w.setStyleSheet(f"background: {_BG2};")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)

    # Render all top-level string/int fields as a simple grid
    from PySide6.QtWidgets import QGridLayout
    stat_items = [(k, v) for k, v in data.items()
                  if isinstance(v, (str, int, float)) and k not in ("id",)]
    if stat_items:
        stats_row = QHBoxLayout()
        stats_row.setSpacing(4)
        for k, v in stat_items[:8]:
            stats_row.addWidget(_stat_cell(str(k), str(v)))
        lay.addLayout(stats_row)

    # Abilities / notes as generic list
    for field in ("abilities", "traits", "notes", "description"):
        items = data.get(field, [])
        if isinstance(items, str) and items:
            lay.addWidget(_section_header(field.title()))
            lbl = QLabel(items)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {_FG_MID}; font-size: 11px; background: transparent;")
            lay.addWidget(lbl)
        elif isinstance(items, list) and items:
            lay.addWidget(_section_header(field.title()))
            for item in items:
                if isinstance(item, dict):
                    lay.addWidget(_ability_card(item.get("name", ""), item.get("effect", item.get("description", item.get("desc", "")))))
                elif isinstance(item, str):
                    lay.addWidget(_ability_card("", item))

    lay.addStretch()
    return w


# ── Unit Card ─────────────────────────────────────────────────────────────────

class _UnitCard(QFrame):
    """Custom styled card for a single OoB roster entry."""

    selected = Signal(dict)

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self._entry = entry
        self.setObjectName("unitCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(72)
        self.setMaximumHeight(80)
        self._build()
        self._apply_style(False)

    def _build(self):
        entry = self._entry
        sys_id = entry.get("system_id", "custom")
        accent = _SYS_COLORS.get(sys_id, _ACCENT)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left accent strip
        strip = QFrame()
        strip.setFixedWidth(4)
        strip.setStyleSheet(f"background: {accent}; border: none;")
        root.addWidget(strip)

        # Main content
        main = QWidget()
        main.setStyleSheet("background: transparent;")
        main_lay = QVBoxLayout(main)
        main_lay.setContentsMargins(12, 8, 12, 8)
        main_lay.setSpacing(3)

        # Row 1: name + points badge
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        name_text = entry.get("custom_name") or "Unnamed Unit"
        qty = entry.get("quantity", 1)
        if qty > 1:
            name_text = f"{name_text} ×{qty}"
        name_lbl = QLabel(name_text)
        name_lbl.setStyleSheet(
            f"color: {_FG}; font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        name_lbl.setMinimumWidth(0)
        name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row1.addWidget(name_lbl)

        pts = entry.get("points_cost", 0) * qty
        if pts:
            pts_lbl = QLabel(f"{pts:,} pts")
            pts_lbl.setStyleSheet(
                f"background: {_ACCENT}22; color: {_ACCENT}; "
                f"border: 1px solid {_ACCENT}44; border-radius: 3px; "
                f"font-size: 10px; font-weight: 600; padding: 1px 5px; "
            )
            row1.addWidget(pts_lbl)
        main_lay.addLayout(row1)

        # Row 2: role · faction + supply badge
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        meta_parts = []
        if entry.get("unit_role"):
            meta_parts.append(entry["unit_role"])
        if entry.get("faction"):
            meta_parts.append(entry["faction"])
        meta_lbl = QLabel("  ·  ".join(meta_parts) if meta_parts else "—")
        meta_lbl.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        meta_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row2.addWidget(meta_lbl)

        supply = entry.get("supply_used", 1) * qty
        if supply:
            sup_lbl = QLabel(f"⚡ {supply}")
            sup_lbl.setStyleSheet(
                f"color: {_WARN}; font-size: 10px; font-weight: 600; "
                f"background: transparent; border: none;"
            )
            row2.addWidget(sup_lbl)
        main_lay.addLayout(row2)

        root.addWidget(main, 1)

    def _apply_style(self, hovered: bool):
        bg = _BG3 if hovered else _BG2
        self.setStyleSheet(
            f"QFrame#unitCard {{ background: {bg}; border: 1px solid {_BORDER}; "
            f"border-radius: 4px; }}"
        )

    def enterEvent(self, event):
        self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._entry)
        super().mousePressEvent(event)

    def update_entry(self, entry: dict):
        self._entry = entry


# ── Add / Edit Unit Dialog ────────────────────────────────────────────────────

class _AddUnitDialog(QDialog):
    """Browse the Rules Library and configure a unit for the Order of Battle."""

    def __init__(self, rules_lib_svc, campaign_id: int, system_hint: str = "",
                 prefill: dict = None, parent=None):
        super().__init__(parent)
        self._rules_lib_svc = rules_lib_svc
        self._campaign_id   = campaign_id
        self._system_hint   = system_hint
        self._prefill       = prefill or {}
        self._selected_entity: dict | None = None

        self.setWindowTitle("Add Unit to Order of Battle" if not prefill else "Edit Unit")
        self.setMinimumSize(920, 620)
        self._build()
        if prefill:
            self._apply_prefill()
        else:
            self._search_entities()

    def _build(self):
        self.setStyleSheet(f"""
            QDialog {{ background: {_BG}; color: {_FG}; }}
            QLabel  {{ color: {_FG}; }}
            QLineEdit, QComboBox, QSpinBox, QTextEdit {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 3px; padding: 4px 8px;
            }}
            QListWidget {{
                background: {_BG2}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 3px;
            }}
            QListWidget::item:selected {{ background: {_ACCENT}33; }}
            QListWidget::item:hover {{ background: {_BG3}; }}
            QPushButton {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 3px; padding: 5px 12px;
            }}
            QPushButton:hover {{ background: {_BORDER}; }}
            QPushButton#accentBtn {{
                background: {_ACCENT}; color: white; border: none;
            }}
            QPushButton#accentBtn:hover {{ background: #3d8be8; }}
            QFormLayout QLabel {{ color: {_FG_MID}; font-size: 12px; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QFrame()
        title_bar.setStyleSheet(f"background: {_BG3}; border-bottom: 1px solid {_BORDER};")
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(20, 14, 20, 14)
        title_lbl = QLabel(self.windowTitle())
        title_lbl.setStyleSheet(f"color: {_FG}; font-size: 15px; font-weight: 700; border: none;")
        tb_lay.addWidget(title_lbl)
        tb_lay.addStretch()
        root.addWidget(title_bar)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {_BORDER}; width: 1px; }}")

        # ── Left: Browse panel ─────────────────────────────────────────────
        browse_w = QWidget()
        browse_w.setMinimumWidth(300)
        browse_lay = QVBoxLayout(browse_w)
        browse_lay.setContentsMargins(16, 14, 12, 14)
        browse_lay.setSpacing(8)

        browse_title = QLabel("Browse Rules Library")
        browse_title.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 2px; text-transform: uppercase; border: none;"
        )
        browse_lay.addWidget(browse_title)

        # System filter
        sys_row = QHBoxLayout()
        sys_row.setSpacing(6)
        sys_lbl = QLabel("System:")
        sys_lbl.setFixedWidth(52)
        sys_lbl.setStyleSheet(f"color: {_FG_MID}; font-size: 11px; border: none;")
        self._sys_filter = QComboBox()
        self._sys_filter.addItems(["All", "40K", "AoS", "D&D 5e", "Custom"])
        if self._system_hint in ("wh40k",):
            self._sys_filter.setCurrentText("40K")
        elif self._system_hint == "aos":
            self._sys_filter.setCurrentText("AoS")
        elif self._system_hint == "dnd5e":
            self._sys_filter.setCurrentText("D&D 5e")
        self._sys_filter.currentIndexChanged.connect(self._on_filter_changed)
        sys_row.addWidget(sys_lbl)
        sys_row.addWidget(self._sys_filter, 1)
        browse_lay.addLayout(sys_row)

        # Faction filter
        fac_row = QHBoxLayout()
        fac_row.setSpacing(6)
        fac_lbl = QLabel("Faction:")
        fac_lbl.setFixedWidth(52)
        fac_lbl.setStyleSheet(f"color: {_FG_MID}; font-size: 11px; border: none;")
        self._fac_filter = QComboBox()
        self._fac_filter.addItem("All Factions")
        self._fac_filter.currentIndexChanged.connect(self._on_filter_changed)
        fac_row.addWidget(fac_lbl)
        fac_row.addWidget(self._fac_filter, 1)
        browse_lay.addLayout(fac_row)

        # Search
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search units…")
        self._search_edit.textChanged.connect(self._on_filter_changed)
        browse_lay.addWidget(self._search_edit)

        # Results list
        self._result_list = QListWidget()
        self._result_list.currentItemChanged.connect(self._on_entity_selected)
        browse_lay.addWidget(self._result_list, 1)

        self._result_count = QLabel("")
        self._result_count.setStyleSheet(f"color: {_FG_DIM}; font-size: 10px; border: none;")
        browse_lay.addWidget(self._result_count)

        splitter.addWidget(browse_w)

        # ── Middle: Preview panel ──────────────────────────────────────────
        preview_w = QWidget()
        preview_w.setMinimumWidth(260)
        preview_w.setMaximumWidth(340)
        preview_lay = QVBoxLayout(preview_w)
        preview_lay.setContentsMargins(12, 14, 12, 14)
        preview_lay.setSpacing(8)

        preview_title = QLabel("Preview")
        preview_title.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 2px; border: none;"
        )
        preview_lay.addWidget(preview_title)

        self._preview_scroll = QScrollArea()
        self._preview_scroll.setWidgetResizable(True)
        self._preview_scroll.setFrameShape(QFrame.NoFrame)
        self._preview_scroll.setStyleSheet(_SCROLLBAR_STYLE)
        self._preview_placeholder = QLabel("Select a unit to preview")
        self._preview_placeholder.setAlignment(Qt.AlignCenter)
        self._preview_placeholder.setStyleSheet(f"color: {_FG_DIM}; font-size: 12px; border: none;")
        self._preview_scroll.setWidget(self._preview_placeholder)
        preview_lay.addWidget(self._preview_scroll, 1)

        splitter.addWidget(preview_w)

        # ── Right: Configuration panel ─────────────────────────────────────
        config_w = QWidget()
        config_w.setMinimumWidth(280)
        config_lay = QVBoxLayout(config_w)
        config_lay.setContentsMargins(12, 14, 16, 14)
        config_lay.setSpacing(8)

        cfg_title = QLabel("Configuration")
        cfg_title.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 2px; border: none;"
        )
        config_lay.addWidget(cfg_title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Leave blank to use library name")
        form.addRow("Name override:", self._name_edit)

        self._role_combo = QComboBox()
        self._role_combo.addItems(ALL_ROLES)
        form.addRow("Role:", self._role_combo)

        self._pts_spin = QSpinBox()
        self._pts_spin.setRange(0, 9999)
        self._pts_spin.setSuffix(" pts")
        form.addRow("Points cost:", self._pts_spin)

        self._pr_spin = QSpinBox()
        self._pr_spin.setRange(0, 30)
        form.addRow("Power Rating:", self._pr_spin)

        self._supply_spin = QSpinBox()
        self._supply_spin.setRange(1, 20)
        self._supply_spin.setValue(1)
        form.addRow("Supply cost:", self._supply_spin)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 20)
        self._qty_spin.setValue(1)
        form.addRow("Quantity:", self._qty_spin)

        config_lay.addLayout(form)
        config_lay.addStretch()

        splitter.addWidget(config_w)
        splitter.setSizes([300, 300, 280])

        root.addWidget(splitter, 1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 10, 16, 14)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self._add_btn = QPushButton("Add to Roster")
        self._add_btn.setObjectName("accentBtn")
        self._add_btn.clicked.connect(self._try_accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._add_btn)
        root.addLayout(btn_row)

    def _apply_prefill(self):
        p = self._prefill
        self._name_edit.setText(p.get("custom_name", ""))
        roles = ALL_ROLES
        role = p.get("unit_role", "")
        idx = roles.index(role) if role in roles else 0
        self._role_combo.setCurrentIndex(idx)
        self._pts_spin.setValue(p.get("points_cost", 0))
        self._pr_spin.setValue(p.get("power_rating", 0))
        self._supply_spin.setValue(p.get("supply_used", 1))
        self._qty_spin.setValue(p.get("quantity", 1))
        self._add_btn.setText("Save Changes")

    def _sys_filter_to_id(self) -> str:
        mapping = {"All": "all", "40K": "wh40k", "AoS": "aos", "D&D 5e": "dnd5e", "Custom": "custom"}
        return mapping.get(self._sys_filter.currentText(), "all")

    def _on_filter_changed(self):
        # Reload faction dropdown when system changes
        sys_id = self._sys_filter_to_id()
        self._fac_filter.blockSignals(True)
        prev_fac = self._fac_filter.currentText()
        self._fac_filter.clear()
        self._fac_filter.addItem("All Factions")
        if self._rules_lib_svc and sys_id != "all":
            try:
                factions = self._rules_lib_svc.get_factions(sys_id)
                self._fac_filter.addItems(factions)
                idx = self._fac_filter.findText(prev_fac)
                if idx >= 0:
                    self._fac_filter.setCurrentIndex(idx)
            except Exception:
                pass
        self._fac_filter.blockSignals(False)
        self._search_entities()

    def _search_entities(self):
        if not self._rules_lib_svc:
            return
        sys_id  = self._sys_filter_to_id()
        faction = self._fac_filter.currentText()
        search  = self._search_edit.text().strip()
        try:
            entities = self._rules_lib_svc.get_entities(
                system_id=sys_id if sys_id != "all" else None,
                faction=faction if faction != "All Factions" else None,
                search=search or None,
                limit=200,
            )
        except Exception as e:
            log.error(f"[OoB AddDialog] search error: {e}")
            entities = []

        self._result_list.clear()
        if not entities:
            sys_id = self._sys_filter_to_id()
            has_any = False
            if self._rules_lib_svc:
                try:
                    has_any = self._rules_lib_svc.has_data(sys_id) if sys_id != "all" else bool(
                        self._rules_lib_svc.get_stats().get("total", 0)
                    )
                except Exception:
                    pass
            placeholder = QListWidgetItem(
                "No data imported for this system.\n"
                "Go to Rules Library → Import Data to load your rulebooks."
                if not has_any else
                "No units match your search."
            )
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            from PySide6.QtGui import QColor
            placeholder.setForeground(QColor(_FG_DIM))
            self._result_list.addItem(placeholder)
            self._result_count.setText("0 results")
            return

        from PySide6.QtGui import QColor
        for ent in entities:
            sys_color = _SYS_COLORS.get(ent.get("system_id", "custom"), _FG_DIM)
            item = QListWidgetItem(
                f"{ent.get('name', '—')}  ·  {ent.get('faction', '')}  ·  {ent.get('entity_type', '')}"
            )
            item.setData(Qt.UserRole, ent)
            item.setForeground(QColor(sys_color))
            self._result_list.addItem(item)
        self._result_count.setText(f"{len(entities)} results")

    def _on_entity_selected(self, current, previous):
        if not current:
            return
        entity = current.data(Qt.UserRole)
        if not entity:
            return
        self._selected_entity = entity

        # Pre-fill config from entity
        if not self._name_edit.text():
            self._name_edit.setPlaceholderText(entity.get("name", ""))
        pts = entity.get("data", {}).get("points", 0)
        if pts:
            try:
                self._pts_spin.setValue(int(pts))
            except Exception:
                pass

        # Set role based on entity_type and system
        entity_type = entity.get("entity_type", "")
        sys_id = entity.get("system_id", "custom")
        roles = get_roles_for_system(sys_id)
        # Try to match entity type to a role
        matched = next((r for r in roles if entity_type.lower() in r.lower() or r.lower() in entity_type.lower()), None)
        if matched and matched in ALL_ROLES:
            self._role_combo.setCurrentText(matched)

        # Build preview
        sys_id = entity.get("system_id", "custom")
        try:
            if sys_id == "wh40k":
                preview_w = _build_wh40k_detail(entity)
            elif sys_id == "aos":
                preview_w = _build_aos_detail(entity)
            elif sys_id == "dnd5e":
                preview_w = _build_dnd_detail(entity)
            else:
                preview_w = _build_generic_detail(entity)
            preview_w.setStyleSheet(f"background: {_BG2};")
            self._preview_scroll.setWidget(preview_w)
        except Exception as e:
            log.error(f"[OoB preview] {e}")

    def _try_accept(self):
        self.accept()

    def result_data(self) -> dict:
        entity = self._selected_entity or {}
        name_override = self._name_edit.text().strip()
        final_name = name_override or entity.get("name", "Custom Unit")
        return {
            "library_entity_id": entity.get("id"),
            "custom_name":       final_name,
            "unit_role":         self._role_combo.currentText(),
            "faction":           entity.get("faction", self._prefill.get("faction", "")),
            "system_id":         entity.get("system_id", self._prefill.get("system_id", "custom")),
            "points_cost":       self._pts_spin.value(),
            "power_rating":      self._pr_spin.value(),
            "supply_used":       self._supply_spin.value(),
            "quantity":          self._qty_spin.value(),
        }


# ── Link Army Dialog ──────────────────────────────────────────────────────────

class _LinkArmyDialog(QDialog):
    """Manage army list links for a campaign."""

    def __init__(self, oob_svc, army_svc, campaign_id: int,
                 campaign_system: str = "", parent=None):
        super().__init__(parent)
        self._oob_svc    = oob_svc
        self._army_svc   = army_svc
        self._camp_id    = campaign_id
        self._camp_sys   = campaign_system
        self.setWindowTitle("Manage Army Lists")
        self.setMinimumSize(560, 440)
        self._build()
        self._refresh_linked()

    def _build(self):
        self.setStyleSheet(f"""
            QDialog {{ background: {_BG}; color: {_FG}; }}
            QLabel  {{ color: {_FG}; border: none; }}
            QLineEdit, QComboBox {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 3px; padding: 4px 8px;
            }}
            QPushButton {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 3px; padding: 5px 12px;
            }}
            QPushButton:hover {{ background: {_BORDER}; }}
            QPushButton#accentBtn {{
                background: {_ACCENT}; color: white; border: none;
            }}
            QPushButton#accentBtn:hover {{ background: #3d8be8; }}
            QPushButton#dangerBtn {{
                background: transparent; color: {_DANGER}; border: 1px solid {_DANGER}44;
                border-radius: 3px; padding: 3px 8px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(14)

        title = QLabel("Army Lists")
        title.setStyleSheet(f"color: {_FG}; font-size: 15px; font-weight: 700;")
        lay.addWidget(title)

        # Currently linked
        linked_title = QLabel("LINKED ARMY LISTS")
        linked_title.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 2px;"
        )
        lay.addWidget(linked_title)

        self._linked_scroll = QScrollArea()
        self._linked_scroll.setWidgetResizable(True)
        self._linked_scroll.setFrameShape(QFrame.NoFrame)
        self._linked_scroll.setMinimumHeight(140)
        self._linked_scroll.setMaximumHeight(180)
        self._linked_container = QWidget()
        self._linked_container.setStyleSheet(f"background: {_BG2};")
        self._linked_lay = QVBoxLayout(self._linked_container)
        self._linked_lay.setContentsMargins(8, 8, 8, 8)
        self._linked_lay.setSpacing(4)
        self._linked_scroll.setWidget(self._linked_container)
        lay.addWidget(self._linked_scroll)

        lay.addWidget(_divider())

        # Link existing army
        link_title = QLabel("LINK EXISTING ARMY")
        link_title.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 2px;"
        )
        lay.addWidget(link_title)

        link_row = QHBoxLayout()
        link_row.setSpacing(8)
        self._existing_combo = QComboBox()
        self._existing_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("Label (optional)")
        self._label_edit.setFixedWidth(160)
        link_btn = QPushButton("Link")
        link_btn.setObjectName("accentBtn")
        link_btn.clicked.connect(self._link_existing)
        link_row.addWidget(self._existing_combo, 1)
        link_row.addWidget(self._label_edit)
        link_row.addWidget(link_btn)
        lay.addLayout(link_row)

        # Load existing armies into combo
        self._all_armies = []
        if self._army_svc:
            try:
                self._all_armies = self._army_svc.get_all_armies()
                for a in self._all_armies:
                    self._existing_combo.addItem(f"{a.name}  ({a.game_system})", userData=a.id)
            except Exception:
                pass

        lay.addWidget(_divider())

        # Create new army
        create_title = QLabel("CREATE & LINK NEW ARMY")
        create_title.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 2px;"
        )
        lay.addWidget(create_title)

        create_row = QHBoxLayout()
        create_row.setSpacing(8)
        self._new_name_edit = QLineEdit()
        self._new_name_edit.setPlaceholderText("Army name…")
        self._new_faction_edit = QLineEdit()
        self._new_faction_edit.setPlaceholderText("Faction…")
        create_btn = QPushButton("Create & Link")
        create_btn.setObjectName("accentBtn")
        create_btn.clicked.connect(self._create_and_link)
        create_row.addWidget(self._new_name_edit, 1)
        create_row.addWidget(self._new_faction_edit, 1)
        create_row.addWidget(create_btn)
        lay.addLayout(create_row)

        lay.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignRight)

    def _refresh_linked(self):
        # Clear
        while self._linked_lay.count():
            item = self._linked_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        linked = self._oob_svc.get_linked_army_lists(self._camp_id)

        if not linked:
            empty = QLabel("No army lists linked yet.")
            empty.setStyleSheet(f"color: {_FG_DIM}; font-size: 12px;")
            empty.setAlignment(Qt.AlignCenter)
            self._linked_lay.addWidget(empty)
            return

        # Build army_id → name map
        army_names: dict[int, str] = {}
        if self._army_svc:
            try:
                for a in self._army_svc.get_all_armies():
                    army_names[a.id] = a.name
            except Exception:
                pass

        for link in linked:
            row_w = QFrame()
            row_w.setStyleSheet(
                f"QFrame {{ background: {_BG3}; border: 1px solid {_BORDER}; border-radius: 3px; }}"
            )
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(10, 6, 10, 6)
            row_lay.setSpacing(8)

            army_name = army_names.get(link["army_id"], f"Army #{link['army_id']}")
            label_text = f"  [{link['label']}]" if link.get("label") else ""
            lbl = QLabel(f"{army_name}{label_text}")
            lbl.setStyleSheet(f"color: {_FG}; font-size: 12px; border: none;")
            row_lay.addWidget(lbl, 1)

            if link.get("is_primary"):
                prim = QLabel("★ Primary")
                prim.setStyleSheet(f"color: {_WARN}; font-size: 10px; border: none;")
                row_lay.addWidget(prim)

            unlink_btn = QPushButton("Unlink")
            unlink_btn.setObjectName("dangerBtn")
            unlink_btn.clicked.connect(lambda _, aid=link["army_id"]: self._unlink(aid))
            row_lay.addWidget(unlink_btn)

            self._linked_lay.addWidget(row_w)

        self._linked_lay.addStretch()

    def _link_existing(self):
        army_id = self._existing_combo.currentData()
        if army_id is None:
            return
        label = self._label_edit.text().strip()
        try:
            self._oob_svc.link_army_list(self._camp_id, army_id, label=label)
            self._label_edit.clear()
            self._refresh_linked()
        except Exception as e:
            log.error(f"[LinkArmyDialog] link_existing: {e}")

    def _create_and_link(self):
        name    = self._new_name_edit.text().strip()
        faction = self._new_faction_edit.text().strip()
        if not name or not self._army_svc:
            return
        try:
            # Map campaign system_id to army builder game_system string
            sys_map = {
                "wh40k":  "Warhammer 40,000",
                "aos":    "Warhammer: Age of Sigmar",
                "dnd5e":  "Dungeons & Dragons",
                "custom": "Custom",
            }
            game_sys = sys_map.get(self._camp_sys, "Custom")
            army = self._army_svc.create_army(
                name=name,
                game_system=game_sys,
                faction=faction or "Unknown",
                format="Open Play",
                points_limit=0,
            )
            self._oob_svc.link_army_list(self._camp_id, army.id, label="")
            self._new_name_edit.clear()
            self._new_faction_edit.clear()
            # Refresh combo
            self._existing_combo.addItem(f"{army.name}  ({army.game_system})", userData=army.id)
            self._refresh_linked()
        except Exception as e:
            log.error(f"[LinkArmyDialog] create_and_link: {e}")
            QMessageBox.warning(self, "Error", f"Failed to create army: {e}")

    def _unlink(self, army_id: int):
        try:
            self._oob_svc.unlink_army_list(self._camp_id, army_id)
            self._refresh_linked()
        except Exception as e:
            log.error(f"[LinkArmyDialog] unlink: {e}")


# ── Add to Army Dialog ────────────────────────────────────────────────────────

class _AddToArmyDialog(QDialog):
    """Add an OoB entry to a linked army list."""

    def __init__(self, entry: dict, linked_armies: list[dict], army_svc, parent=None):
        super().__init__(parent)
        self._entry         = entry
        self._linked_armies = linked_armies
        self._army_svc      = army_svc
        self.setWindowTitle(f"Add  {entry.get('custom_name', 'Unit')}  to Army List")
        self.setMinimumWidth(400)
        self._build()

    def _build(self):
        self.setStyleSheet(f"""
            QDialog {{ background: {_BG}; color: {_FG}; }}
            QLabel  {{ color: {_FG}; border: none; }}
            QComboBox, QSpinBox {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 3px; padding: 4px 8px;
            }}
            QPushButton {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 3px; padding: 5px 12px;
            }}
            QPushButton#accentBtn {{ background: {_ACCENT}; color: white; border: none; }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(12)

        title = QLabel(f"Add  \"{self._entry.get('custom_name', 'Unit')}\"  to Army List")
        title.setStyleSheet(f"color: {_FG}; font-size: 14px; font-weight: 700;")
        title.setWordWrap(True)
        lay.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self._army_combo = QComboBox()
        # Build army id→name map
        army_names: dict[int, str] = {}
        if self._army_svc:
            try:
                for a in self._army_svc.get_all_armies():
                    army_names[a.id] = a.name
            except Exception:
                pass
        for link in self._linked_armies:
            name = army_names.get(link["army_id"], f"Army #{link['army_id']}")
            self._army_combo.addItem(name, userData=link["army_id"])
        form.addRow("Army list:", self._army_combo)

        self._role_combo = QComboBox()
        self._role_combo.addItems(ALL_ROLES)
        pre_role = self._entry.get("unit_role", "")
        if pre_role in ALL_ROLES:
            self._role_combo.setCurrentText(pre_role)
        form.addRow("Role:", self._role_combo)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 20)
        self._qty_spin.setValue(self._entry.get("quantity", 1))
        form.addRow("Quantity:", self._qty_spin)

        pts = self._entry.get("points_cost", 0)
        pts_lbl = QLabel(f"{pts:,} pts per unit")
        pts_lbl.setStyleSheet(f"color: {_FG_MID}; font-size: 12px;")
        form.addRow("Points:", pts_lbl)

        lay.addLayout(form)
        lay.addStretch()

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        add_btn = QPushButton("Add to Army List")
        add_btn.setObjectName("accentBtn")
        add_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel)
        btn_row.addStretch()
        btn_row.addWidget(add_btn)
        lay.addLayout(btn_row)

    def result_data(self) -> dict:
        return {
            "army_id":   self._army_combo.currentData(),
            "unit_role": self._role_combo.currentText(),
            "quantity":  self._qty_spin.value(),
        }


# ── Main Order of Battle Widget ───────────────────────────────────────────────

class OrderOfBattleUI(QWidget):

    def __init__(self, oob_service, rules_lib_service, army_service, context, parent=None):
        super().__init__(parent)
        self._svc      = oob_service
        self._rl_svc   = rules_lib_service
        self._army_svc = army_service
        self._ctx      = context

        self._camp_id: Optional[int] = None
        self._current_entry: Optional[dict] = None
        self._role_filter: Optional[str] = None

        # Notes debounce timer
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.timeout.connect(self._flush_notes_save)
        self._pending_notes_entry_id: Optional[int] = None

        self._build()
        self._apply_theme()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("oobHeader")
        header.setMinimumHeight(52)
        header.setMaximumHeight(52)
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(20, 0, 16, 0)
        hdr_lay.setSpacing(12)

        title_lbl = QLabel("⚔  Order of Battle")
        title_lbl.setObjectName("pageTitle")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()

        self._stats_lbl = QLabel("")
        self._stats_lbl.setObjectName("oobStats")
        hdr_lay.addWidget(self._stats_lbl)
        hdr_lay.addSpacing(16)

        self._add_btn = QPushButton("＋  Add Unit")
        self._add_btn.setObjectName("accentBtn")
        self._add_btn.clicked.connect(self._on_add_unit)
        hdr_lay.addWidget(self._add_btn)

        self._armies_btn = QPushButton("⚑  Army Lists")
        self._armies_btn.clicked.connect(self._on_army_lists)
        if not self._army_svc:
            self._armies_btn.setVisible(False)
        hdr_lay.addWidget(self._armies_btn)

        root.addWidget(header)

        # ── Main content: splitter ────────────────────────────────────────
        self._splitter = QSplitter(Qt.Horizontal)

        # Left panel
        left = QFrame()
        left.setObjectName("oobLeft")
        left.setMinimumWidth(280)
        left.setMaximumWidth(360)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        # Role filter strip
        self._role_filter_frame = QFrame()
        self._role_filter_frame.setObjectName("roleFilterStrip")
        self._role_filter_lay = QHBoxLayout(self._role_filter_frame)
        self._role_filter_lay.setContentsMargins(8, 6, 8, 6)
        self._role_filter_lay.setSpacing(4)
        self._role_btns: dict[str | None, QPushButton] = {}
        self._build_role_filters([])
        left_lay.addWidget(self._role_filter_frame)

        # Unit list scroll area
        self._unit_scroll = QScrollArea()
        self._unit_scroll.setWidgetResizable(True)
        self._unit_scroll.setFrameShape(QFrame.NoFrame)
        self._unit_scroll.setStyleSheet(_SCROLLBAR_STYLE)
        self._unit_list_container = QWidget()
        self._unit_list_container.setObjectName("unitListContainer")
        self._unit_list_lay = QVBoxLayout(self._unit_list_container)
        self._unit_list_lay.setContentsMargins(8, 8, 8, 8)
        self._unit_list_lay.setSpacing(6)
        self._unit_list_lay.addStretch()
        self._unit_scroll.setWidget(self._unit_list_container)
        left_lay.addWidget(self._unit_scroll, 1)

        self._splitter.addWidget(left)

        # Right panel: stacked
        self._right_stack = QStackedWidget()

        # Page 0: empty state
        empty_w = QWidget()
        empty_lay = QVBoxLayout(empty_w)
        empty_lay.setAlignment(Qt.AlignCenter)
        empty_lay.setSpacing(12)
        empty_icon = QLabel("⚔")
        empty_icon_font = QFont()
        empty_icon_font.setPointSize(42)
        empty_icon.setFont(empty_icon_font)
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_icon.setStyleSheet(f"color: {_FG_DIM};")
        empty_lay.addWidget(empty_icon)
        empty_title = QLabel("Select a unit to view its details")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_title.setStyleSheet(f"color: {_FG_MID}; font-size: 14px; font-weight: 600;")
        empty_lay.addWidget(empty_title)
        empty_sub = QLabel("Or add units from the Rules Library to begin\nbuilding your campaign roster.")
        empty_sub.setAlignment(Qt.AlignCenter)
        empty_sub.setWordWrap(True)
        empty_sub.setStyleSheet(f"color: {_FG_DIM}; font-size: 12px;")
        empty_lay.addWidget(empty_sub)
        empty_add_btn = QPushButton("＋  Add Unit from Library")
        empty_add_btn.setObjectName("accentBtn")
        empty_add_btn.clicked.connect(self._on_add_unit)
        empty_lay.addWidget(empty_add_btn, alignment=Qt.AlignCenter)
        self._right_stack.addWidget(empty_w)  # page 0

        # Page 1: detail panel (placeholder, replaced dynamically)
        self._detail_placeholder = QWidget()
        self._right_stack.addWidget(self._detail_placeholder)  # page 1

        self._splitter.addWidget(self._right_stack)
        self._splitter.setSizes([300, 600])
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {_BORDER}; width: 1px; }}"
        )

        root.addWidget(self._splitter, 1)

        # No-campaign state (shown when camp_id is None)
        self._no_camp_w = QWidget()
        nc_lay = QVBoxLayout(self._no_camp_w)
        nc_lay.setAlignment(Qt.AlignCenter)
        nc_lbl = QLabel("Select a campaign to view its Order of Battle")
        nc_lbl.setAlignment(Qt.AlignCenter)
        nc_lbl.setStyleSheet(f"color: {_FG_DIM}; font-size: 14px;")
        nc_lay.addWidget(nc_lbl)
        self._no_camp_w.setVisible(False)
        root.addWidget(self._no_camp_w)

    def _build_role_filters(self, roles: list[str]):
        # Clear existing buttons
        while self._role_filter_lay.count():
            item = self._role_filter_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._role_btns.clear()

        all_btn = QPushButton("All")
        all_btn.setObjectName("roleFilterBtn")
        all_btn.setCheckable(True)
        all_btn.setChecked(self._role_filter is None)
        all_btn.clicked.connect(lambda: self._set_role_filter(None))
        self._role_filter_lay.addWidget(all_btn)
        self._role_btns[None] = all_btn

        for role in roles:
            btn = QPushButton(role)
            btn.setObjectName("roleFilterBtn")
            btn.setCheckable(True)
            btn.setChecked(self._role_filter == role)
            btn.clicked.connect(lambda _, r=role: self._set_role_filter(r))
            self._role_filter_lay.addWidget(btn)
            self._role_btns[role] = btn

        self._role_filter_lay.addStretch()

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QWidget {{ background: {_BG}; color: {_FG}; }}
            QFrame#oobHeader {{
                background: {_BG3}; border-bottom: 1px solid {_BORDER};
            }}
            QLabel#pageTitle {{ color: {_FG}; font-size: 14px; font-weight: 700; }}
            QLabel#oobStats  {{ color: {_FG_MID}; font-size: 12px; }}
            QFrame#oobLeft   {{ background: {_BG2}; border-right: 1px solid {_BORDER}; }}
            QFrame#roleFilterStrip {{ background: {_BG3}; border-bottom: 1px solid {_BORDER}; }}
            QPushButton#roleFilterBtn {{
                background: transparent; color: {_FG_MID};
                border: 1px solid {_BORDER}; border-radius: 3px;
                padding: 3px 8px; font-size: 11px;
            }}
            QPushButton#roleFilterBtn:checked {{
                background: {_ACCENT}22; color: {_ACCENT};
                border: 1px solid {_ACCENT}66;
            }}
            QPushButton#roleFilterBtn:hover {{ background: {_BG3}; }}
            QWidget#unitListContainer {{ background: {_BG2}; }}
            QPushButton#accentBtn {{
                background: {_ACCENT}; color: white; border: none;
                border-radius: 3px; padding: 5px 14px;
            }}
            QPushButton#accentBtn:hover {{ background: #3d8be8; }}
            QPushButton#ghostBtn {{
                background: transparent; color: {_FG_MID};
                border: 1px solid {_BORDER}; border-radius: 3px; padding: 4px 10px;
            }}
            QPushButton#ghostBtn:hover {{ background: {_BG3}; }}
            QPushButton#dangerBtn {{
                background: transparent; color: {_DANGER};
                border: 1px solid {_DANGER}44; border-radius: 3px; padding: 4px 10px;
            }}
            QPushButton#dangerBtn:hover {{ background: {_DANGER}22; }}
            QScrollArea {{ background: {_BG2}; border: none; }}
            QTextEdit {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 3px;
            }}
            QCheckBox {{ color: {_FG}; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                background: {_BG3}; border: 1px solid {_BORDER}; border-radius: 2px;
            }}
            QCheckBox::indicator:checked {{
                background: {_ACCENT}; border: 1px solid {_ACCENT};
            }}
            QComboBox, QSpinBox {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 3px; padding: 4px 8px;
            }}
        """)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, campaign_id: int = None):
        if campaign_id is not None:
            self._camp_id = campaign_id
        if self._camp_id is None:
            self._splitter.setVisible(False)
            self._no_camp_w.setVisible(True)
            return
        self._no_camp_w.setVisible(False)
        self._splitter.setVisible(True)
        self._role_filter = None
        self._current_entry = None
        self._right_stack.setCurrentIndex(0)
        self._load_units()
        self._refresh_stats()

    # ── Internal loaders ──────────────────────────────────────────────────────

    def _load_units(self, role_filter: str = None):
        self._role_filter = role_filter

        if self._camp_id is None:
            return

        all_entries = self._svc.get_order_of_battle(self._camp_id)

        # Collect roles present
        roles = list(dict.fromkeys(e.get("unit_role", "") for e in all_entries if e.get("unit_role")))
        self._build_role_filters(roles)

        # Filter
        if role_filter:
            entries = [e for e in all_entries if e.get("unit_role") == role_filter]
        else:
            entries = all_entries

        # Clear list
        while self._unit_list_lay.count():
            item = self._unit_list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not entries:
            label_text = f"No {role_filter} units" if role_filter else "No units in this roster yet."
            empty_lbl = QLabel(label_text)
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet(f"color: {_FG_DIM}; font-size: 12px; padding: 20px;")
            self._unit_list_lay.addWidget(empty_lbl)
        else:
            for entry in entries:
                card = _UnitCard(entry)
                card.selected.connect(self._on_unit_selected)
                self._unit_list_lay.addWidget(card)

        self._unit_list_lay.addStretch()

    def _refresh_stats(self):
        if self._camp_id is None:
            self._stats_lbl.setText("")
            return
        try:
            stats = self._svc.get_oob_stats(self._camp_id)
            units  = stats.get("total_units", 0)
            pts    = stats.get("total_points", 0)
            supply = stats.get("total_supply", 0)
            self._stats_lbl.setText(
                f"{units:,} unit{'s' if units != 1 else ''}  ·  "
                f"{pts:,} pts  ·  "
                f"{supply:,}⚡ supply"
            )
        except Exception as e:
            log.error(f"[OoB] _refresh_stats: {e}")

    def _set_role_filter(self, role: Optional[str]):
        self._role_filter = role
        for r, btn in self._role_btns.items():
            btn.setChecked(r == role)
        self._load_units(role)

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _on_unit_selected(self, entry: dict):
        self._current_entry = entry
        detail = self._build_detail_panel(entry)
        # Replace page 1
        old = self._right_stack.widget(1)
        if old:
            self._right_stack.removeWidget(old)
            old.deleteLater()
        self._right_stack.insertWidget(1, detail)
        self._right_stack.setCurrentIndex(1)

    def _build_detail_panel(self, entry: dict) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(_SCROLLBAR_STYLE)

        container = QWidget()
        container.setStyleSheet(f"background: {_BG};")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(20, 16, 20, 20)
        lay.setSpacing(10)

        # ── Header row ────────────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(10)
        name_text = entry.get("custom_name") or "Unnamed Unit"
        name_lbl = QLabel(name_text)
        name_lbl.setStyleSheet(
            f"color: {_FG}; font-size: 18px; font-weight: 700;"
        )
        name_lbl.setWordWrap(True)
        hdr_row.addWidget(name_lbl, 1)

        edit_btn = QPushButton("✏  Edit")
        edit_btn.setObjectName("ghostBtn")
        edit_btn.clicked.connect(lambda: self._on_edit_unit(entry))
        hdr_row.addWidget(edit_btn)

        remove_btn = QPushButton("🗑  Remove")
        remove_btn.setObjectName("dangerBtn")
        remove_btn.clicked.connect(lambda: self._on_remove_unit(entry["id"]))
        hdr_row.addWidget(remove_btn)
        lay.addLayout(hdr_row)

        # ── Meta strip ────────────────────────────────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        if entry.get("unit_role"):
            meta_row.addWidget(_badge(entry["unit_role"], _FG_DIM))
        if entry.get("faction"):
            meta_row.addWidget(_badge(entry["faction"], _FG_DIM))
        sys_id = entry.get("system_id", "custom")
        sys_labels = {"wh40k": "40K", "aos": "AoS", "dnd5e": "D&D 5e", "custom": "Custom"}
        sys_color  = _SYS_COLORS.get(sys_id, _ACCENT)
        meta_row.addWidget(_badge(sys_labels.get(sys_id, sys_id), sys_color))
        pts = entry.get("points_cost", 0) * entry.get("quantity", 1)
        if pts:
            meta_row.addWidget(_badge(f"{pts:,} pts", _ACCENT))
        meta_row.addStretch()
        lay.addLayout(meta_row)
        lay.addWidget(_divider())

        # ── Stat block from Rules Library ─────────────────────────────────
        entity = None
        if entry.get("library_entity_id") and self._rl_svc:
            try:
                entity = self._rl_svc.get_entity(entry["library_entity_id"])
            except Exception:
                pass

        if entity:
            stat_title = _section_header("Stat Block")
            lay.addWidget(stat_title)
            try:
                if sys_id == "wh40k":
                    stat_w = _build_wh40k_detail(entity)
                elif sys_id == "aos":
                    stat_w = _build_aos_detail(entity)
                elif sys_id == "dnd5e":
                    stat_w = _build_dnd_detail(entity)
                else:
                    stat_w = _build_generic_detail(entity)
                lay.addWidget(stat_w)
            except Exception as e:
                log.error(f"[OoB detail] stat block: {e}")
        lay.addWidget(_divider())

        # ── Loadout ───────────────────────────────────────────────────────
        lay.addWidget(_section_header("LOADOUT"))

        try:
            loadout = json.loads(entry.get("loadout_json") or "[]")
        except Exception:
            loadout = []

        if sys_id == "wh40k" and entity:
            # Render wargear options as checkboxes
            data = entity.get("data", {})
            wargear_opts = data.get("wargearOptions", data.get("wargear_options", []))
            if isinstance(wargear_opts, list) and wargear_opts:
                checked_map: dict[str, bool] = {}
                for item in loadout:
                    if isinstance(item, dict) and "option" in item:
                        checked_map[item["option"]] = item.get("chosen", False)

                self._loadout_checks: list[QCheckBox] = []
                for opt in wargear_opts:
                    opt_str = str(opt)
                    cb = QCheckBox(opt_str)
                    cb.setChecked(checked_map.get(opt_str, False))
                    lay.addWidget(cb)
                    self._loadout_checks.append(cb)

                save_loadout_btn = QPushButton("Save Loadout")
                save_loadout_btn.setObjectName("accentBtn")
                save_loadout_btn.clicked.connect(
                    lambda _, eid=entry["id"]: self._save_loadout_from_checks(eid)
                )
                lay.addWidget(save_loadout_btn)
            else:
                # Fallback for 40K without wargear in data
                self._loadout_edit = QTextEdit()
                self._loadout_edit.setPlaceholderText("Loadout notes…")
                self._loadout_edit.setFixedHeight(80)
                if loadout and isinstance(loadout[0], dict) and "notes" in loadout[0]:
                    self._loadout_edit.setPlainText(loadout[0].get("notes", ""))
                save_loadout_btn2 = QPushButton("Save Loadout")
                save_loadout_btn2.setObjectName("accentBtn")
                save_loadout_btn2.clicked.connect(
                    lambda _, eid=entry["id"]: self._save_loadout_text(eid)
                )
                lay.addWidget(self._loadout_edit)
                lay.addWidget(save_loadout_btn2)
        else:
            # AoS / D&D / custom: free text
            self._loadout_edit = QTextEdit()
            self._loadout_edit.setPlaceholderText("Loadout notes…")
            self._loadout_edit.setFixedHeight(80)
            if loadout and isinstance(loadout[0], dict) and "notes" in loadout[0]:
                self._loadout_edit.setPlainText(loadout[0].get("notes", ""))
            save_loadout_btn3 = QPushButton("Save Loadout")
            save_loadout_btn3.setObjectName("accentBtn")
            save_loadout_btn3.clicked.connect(
                lambda _, eid=entry["id"]: self._save_loadout_text(eid)
            )
            lay.addWidget(self._loadout_edit)
            lay.addWidget(save_loadout_btn3)

        lay.addWidget(_divider())

        # ── Army List section ─────────────────────────────────────────────
        if self._army_svc:
            lay.addWidget(_section_header("ARMY LIST"))
            army_add_lbl = QLabel("Add this unit to an army list:")
            army_add_lbl.setStyleSheet(f"color: {_FG_MID}; font-size: 12px;")
            lay.addWidget(army_add_lbl)

            linked = self._svc.get_linked_army_lists(self._camp_id) if self._camp_id else []
            if linked:
                add_army_btn = QPushButton("＋  Add to Army List")
                add_army_btn.setObjectName("accentBtn")
                add_army_btn.clicked.connect(lambda _, e=entry: self._on_add_to_army_list(e))
                lay.addWidget(add_army_btn)
            else:
                no_armies_lbl = QLabel("No army lists linked. Use Army Lists to link one.")
                no_armies_lbl.setStyleSheet(f"color: {_FG_DIM}; font-size: 11px;")
                no_armies_lbl.setWordWrap(True)
                lay.addWidget(no_armies_lbl)

            lay.addWidget(_divider())

        # ── Notes ─────────────────────────────────────────────────────────
        lay.addWidget(_section_header("NOTES"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Campaign notes for this unit…")
        self._notes_edit.setMinimumHeight(90)
        self._notes_edit.setPlainText(entry.get("notes", ""))
        self._notes_edit.textChanged.connect(
            lambda: self._schedule_notes_save(entry["id"])
        )
        lay.addWidget(self._notes_edit)

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_add_unit(self):
        if self._camp_id is None:
            return
        # Determine campaign system hint
        sys_hint = ""
        try:
            camp = self._svc.get_campaign(self._camp_id)
            if camp:
                sys_hint = getattr(camp, "game_system", "") or ""
                # Normalise: map system display names to system_id keys
                sys_map_rev = {
                    "Warhammer 40,000": "wh40k",
                    "Warhammer: Age of Sigmar": "aos",
                    "Dungeons & Dragons": "dnd5e",
                }
                sys_hint = sys_map_rev.get(sys_hint, sys_hint)
        except Exception:
            pass

        dlg = _AddUnitDialog(
            self._rl_svc, self._camp_id, system_hint=sys_hint, parent=self
        )
        if dlg.exec() == QDialog.Accepted:
            data = dlg.result_data()
            entry_id = self._svc.add_to_order_of_battle(self._camp_id, **data)
            if entry_id:
                self._load_units(self._role_filter)
                self._refresh_stats()

    def _on_edit_unit(self, entry: dict):
        dlg = _AddUnitDialog(
            self._rl_svc, self._camp_id,
            system_hint=entry.get("system_id", ""),
            prefill=entry,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            data = dlg.result_data()
            # Remove non-updatable keys
            data.pop("library_entity_id", None)
            self._svc.update_oob_entry(entry["id"], **data)
            self._load_units(self._role_filter)
            self._refresh_stats()
            # Refresh detail panel with updated entry
            updated = self._svc.get_order_of_battle(self._camp_id)
            for e in updated:
                if e["id"] == entry["id"]:
                    self._on_unit_selected(e)
                    break

    def _on_remove_unit(self, entry_id: int):
        reply = QMessageBox.question(
            self, "Remove Unit",
            "Remove this unit from the Order of Battle?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._svc.remove_from_order_of_battle(entry_id)
        self._right_stack.setCurrentIndex(0)
        self._current_entry = None
        self._load_units(self._role_filter)
        self._refresh_stats()

    def _on_army_lists(self):
        if self._camp_id is None:
            return
        sys_hint = ""
        try:
            camp = self._svc.get_campaign(self._camp_id)
            if camp:
                sys_hint = getattr(camp, "game_system", "") or ""
        except Exception:
            pass
        dlg = _LinkArmyDialog(
            self._svc, self._army_svc, self._camp_id,
            campaign_system=sys_hint, parent=self,
        )
        dlg.exec()

    def _on_add_to_army_list(self, entry: dict):
        if not self._army_svc or self._camp_id is None:
            return
        linked = self._svc.get_linked_army_lists(self._camp_id)
        if not linked:
            QMessageBox.information(
                self, "No Army Lists",
                "Link an army list first using the Army Lists button.",
            )
            return
        dlg = _AddToArmyDialog(entry, linked, self._army_svc, parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.result_data()
            army_id = data.get("army_id")
            if army_id is None:
                return

            # Build wargear notes from loadout
            loadout_summary = ""
            try:
                loadout = json.loads(entry.get("loadout_json") or "[]")
                if loadout:
                    if isinstance(loadout[0], dict) and "option" in loadout[0]:
                        chosen = [l["option"] for l in loadout if l.get("chosen")]
                        loadout_summary = ", ".join(chosen)
                    elif isinstance(loadout[0], dict) and "notes" in loadout[0]:
                        loadout_summary = loadout[0].get("notes", "")
            except Exception:
                pass

            try:
                self._army_svc.add_unit(
                    army_id=army_id,
                    unit_name=entry.get("custom_name", "Unit"),
                    unit_role=data["unit_role"],
                    points_cost=float(entry.get("points_cost", 0)),
                    quantity=data["quantity"],
                    wargear_notes=loadout_summary or None,
                )
            except Exception as e:
                log.error(f"[OoB] add_to_army: {e}")
                QMessageBox.warning(self, "Error", f"Failed to add to army: {e}")

    def _save_loadout_from_checks(self, entry_id: int):
        if not hasattr(self, "_loadout_checks"):
            return
        loadout = [
            {"option": cb.text(), "chosen": cb.isChecked()}
            for cb in self._loadout_checks
        ]
        self._save_loadout(entry_id, json.dumps(loadout))

    def _save_loadout_text(self, entry_id: int):
        if not hasattr(self, "_loadout_edit"):
            return
        text = self._loadout_edit.toPlainText().strip()
        loadout = json.dumps([{"notes": text}])
        self._save_loadout(entry_id, loadout)

    def _save_loadout(self, entry_id: int, loadout_json: str):
        try:
            self._svc.update_oob_entry(entry_id, loadout_json=loadout_json)
        except Exception as e:
            log.error(f"[OoB] save_loadout: {e}")

    def _schedule_notes_save(self, entry_id: int):
        self._pending_notes_entry_id = entry_id
        self._notes_timer.start(500)

    def _flush_notes_save(self):
        if self._pending_notes_entry_id is None:
            return
        if not hasattr(self, "_notes_edit"):
            return
        notes = self._notes_edit.toPlainText()
        self._save_notes(self._pending_notes_entry_id, notes)
        self._pending_notes_entry_id = None

    def _save_notes(self, entry_id: int, notes: str):
        try:
            self._svc.update_oob_entry(entry_id, notes=notes)
        except Exception as e:
            log.error(f"[OoB] save_notes: {e}")
