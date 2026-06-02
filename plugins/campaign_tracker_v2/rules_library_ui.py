"""
Campaign Tracker v2 — Rules Library UI.

Flagship reference panel for game rules data: Warhammer 40K, Age of Sigmar,
D&D 5e, and custom entries.  Stat blocks are rendered as proper structured
layouts — not plain text.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QThread, QObject
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QGridLayout, QTextEdit, QMessageBox, QStackedWidget, QSizePolicy,
    QListWidget, QListWidgetItem, QSplitter, QProgressBar, QApplication,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout,
    QAbstractItemView, QSpinBox,
)

log = logging.getLogger(__name__)

# ── Palette (mirrors ui.py exactly) ──────────────────────────────────────────
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

# System color indicators in list items
_SYS_COLORS = {
    "wh40k":  _DANGER,
    "aos":    _SUCCESS,
    "dnd5e":  "#9b59b6",
    "custom": _ACCENT,
    "all":    _FG_DIM,
}

def _resolve_campaign_system(game_system: str) -> str:
    """Map a campaign's game_system string to a rules library system_id."""
    s = (game_system or "").lower()
    if any(k in s for k in ("d&d", "dnd", "dungeons", "5e")):
        return "dnd5e"
    if any(k in s for k in ("40k", "40,000", "warhammer 40", "wh40k", "astartes")):
        return "wh40k"
    if any(k in s for k in ("age of sigmar", "sigmar", "aos")):
        return "aos"
    if any(k in s for k in ("pathfinder", "pf2")):
        return "pathfinder2e"
    if "necromunda" in s:
        return "necromunda"
    if "kill team" in s:
        return "killteam"
    return "custom"


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
    QScrollBar:horizontal {{
        background: {_BG}; height: 6px; margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {_BORDER2}; border-radius: 3px; min-width: 20px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
"""


# ── Shared widget helpers ─────────────────────────────────────────────────────

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
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    val_lbl.setStyleSheet(
        f"color: {_FG}; font-size: 18px; font-weight: 700; "
        f"background: transparent; border: none;"
    )
    key_lbl = QLabel(label)
    key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    key_lbl.setStyleSheet(
        f"color: {accent_color}; font-size: 9px; font-weight: 600; "
        f"letter-spacing: 1px; background: transparent; border: none;"
    )
    lay.addWidget(val_lbl)
    lay.addWidget(key_lbl)
    return f


def _weapons_table(headers: list[str], rows: list[list[str]]) -> QFrame:
    """Render a clean weapons table with alternating row colors."""
    f = QFrame()
    f.setStyleSheet(f"background: {_BG2}; border: none;")
    grid = QGridLayout(f)
    grid.setSpacing(0)
    grid.setContentsMargins(0, 0, 0, 0)

    # Header row
    for col, h in enumerate(headers):
        lbl = QLabel(h)
        lbl.setStyleSheet(
            f"background: {_BG3}; color: {_FG_DIM}; font-size: 10px; "
            f"font-weight: 600; padding: 4px 8px; border-bottom: 1px solid {_BORDER}; "
            f"border: none;"
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(lbl, 0, col)

    # Data rows with alternating colors
    for row_idx, row in enumerate(rows):
        bg = _BG2 if row_idx % 2 == 0 else _BG3
        for col, val in enumerate(row):
            lbl = QLabel(str(val) if val else "—")
            if col == 0:
                lbl.setStyleSheet(
                    f"background: {bg}; color: {_FG}; font-size: 11px; "
                    f"padding: 5px 8px; border: none; font-weight: 500;"
                )
                lbl.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
            else:
                lbl.setStyleSheet(
                    f"background: {bg}; color: {_FG_MID}; font-size: 11px; "
                    f"padding: 5px 8px; border: none;"
                )
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, row_idx + 1, col)

    # Name column stretches
    grid.setColumnStretch(0, 2)
    return f


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


# ── Detail panel builders ─────────────────────────────────────────────────────

def _build_wh40k_detail(entity: dict) -> QWidget:
    data = entity.get("data", {})
    if not data and entity.get("data_json"):
        try:
            data = json.loads(entity["data_json"])
        except Exception:
            data = {}

    outer = QWidget()
    outer.setStyleSheet(f"background: {_BG2};")
    lay = QVBoxLayout(outer)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(8)

    # ── Header ──────────────────────────────────────────────────────────────
    hdr = QFrame()
    hdr.setStyleSheet(f"background: {_BG3}; border-radius: 6px; padding: 4px;")
    hdr_lay = QVBoxLayout(hdr)
    hdr_lay.setContentsMargins(16, 12, 16, 12)
    hdr_lay.setSpacing(4)

    faction = entity.get("faction", data.get("factionname", ""))
    unit_name = data.get("unitname", entity.get("name", ""))

    # Faction badge + unit name row
    top_row = QHBoxLayout()
    if faction:
        top_row.addWidget(_badge(faction, _DANGER))
    top_row.addStretch()
    hdr_lay.addLayout(top_row)

    name_lbl = QLabel(unit_name)
    name_lbl.setStyleSheet(
        f"color: {_FG}; font-size: 22px; font-weight: 700; "
        f"background: transparent; border: none;"
    )
    name_lbl.setWordWrap(True)
    hdr_lay.addWidget(name_lbl)

    # Keywords
    kw_raw = data.get("keywords", [])
    kw_flat: list[str] = []
    for kw in kw_raw:
        if isinstance(kw, dict):
            kw_flat.extend(kw.get("words", []))
        elif isinstance(kw, str):
            kw_flat.append(kw)
    if kw_flat:
        kw_lbl = QLabel("Keywords: " + " · ".join(kw_flat))
        kw_lbl.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 11px; background: transparent; border: none;"
        )
        kw_lbl.setWordWrap(True)
        hdr_lay.addWidget(kw_lbl)

    lay.addWidget(hdr)

    # ── Stats bar ────────────────────────────────────────────────────────────
    stats_list = data.get("stats", [])
    for stat_block in stats_list:
        unit_label = stat_block.get("unit", "")
        lay.addWidget(_section_header(f"Stats — {unit_label}" if unit_label else "Stats"))

        bar = QHBoxLayout()
        bar.setSpacing(6)
        stat_defs = [
            ("M",  stat_block.get("m", "")),
            ("T",  stat_block.get("t", "")),
            ("SV", stat_block.get("sv", "")),
            ("W",  stat_block.get("w", "")),
            ("LD", stat_block.get("ld", "")),
            ("OC", stat_block.get("oc", "")),
        ]
        for label, val in stat_defs:
            cell = _stat_cell(label, str(val) if val else "")
            bar.addWidget(cell, 1)
        bar_w = QWidget()
        bar_w.setStyleSheet("background: transparent;")
        bar_w.setLayout(bar)
        lay.addWidget(bar_w)

    # ── Weapons ──────────────────────────────────────────────────────────────
    weapons = data.get("weapons", [])
    ranged = [w for w in weapons if w.get("range", "").lower() != "melee" and w.get("range", "")]
    melee  = [w for w in weapons if w.get("range", "").lower() == "melee"]

    if ranged:
        lay.addWidget(_section_header("Ranged Weapons"))
        headers = ["Name", "Rng", "A", "BS", "S", "AP", "D", "Abilities"]
        rows = []
        for w in ranged:
            abilities = " / ".join(w.get("abilities", [])) if w.get("abilities") else ""
            rows.append([
                w.get("name", ""),
                w.get("range", ""),
                w.get("attacks", ""),
                w.get("skill", ""),
                w.get("strength", ""),
                w.get("ap", ""),
                w.get("damage", ""),
                abilities,
            ])
        lay.addWidget(_weapons_table(headers, rows))

    if melee:
        lay.addWidget(_section_header("Melee Weapons"))
        headers = ["Name", "A", "WS", "S", "AP", "D", "Abilities"]
        rows = []
        for w in melee:
            abilities = " / ".join(w.get("abilities", [])) if w.get("abilities") else ""
            rows.append([
                w.get("name", ""),
                w.get("attacks", ""),
                w.get("skill", ""),
                w.get("strength", ""),
                w.get("ap", ""),
                w.get("damage", ""),
                abilities,
            ])
        lay.addWidget(_weapons_table(headers, rows))

    # ── Abilities ────────────────────────────────────────────────────────────
    abilities = data.get("abilities", {})
    if abilities:
        lay.addWidget(_section_header("Abilities"))

        core_abs = abilities.get("core", [])
        faction_abs = abilities.get("faction", [])
        if core_abs or faction_abs:
            simple_f = QFrame()
            simple_f.setStyleSheet(f"background: {_BG3}; border-radius: 4px;")
            sf_lay = QVBoxLayout(simple_f)
            sf_lay.setContentsMargins(12, 8, 12, 8)
            sf_lay.setSpacing(4)
            if core_abs:
                core_lbl = QLabel("CORE: " + " · ".join(core_abs))
                core_lbl.setStyleSheet(
                    f"color: {_FG_MID}; font-size: 11px; "
                    f"background: transparent; border: none;"
                )
                core_lbl.setWordWrap(True)
                sf_lay.addWidget(core_lbl)
            if faction_abs:
                fac_lbl = QLabel("FACTION: " + " · ".join(faction_abs))
                fac_lbl.setStyleSheet(
                    f"color: {_FG_MID}; font-size: 11px; "
                    f"background: transparent; border: none;"
                )
                fac_lbl.setWordWrap(True)
                sf_lay.addWidget(fac_lbl)
            lay.addWidget(simple_f)

        for unit_ab in abilities.get("unit", []):
            ab_name   = unit_ab.get("name", "")
            ab_effect = unit_ab.get("effect", "")
            lay.addWidget(_ability_card(ab_name, ab_effect))

        for wg_ab in abilities.get("wargear", []):
            ab_name   = wg_ab.get("name", "")
            ab_effect = wg_ab.get("effect", "")
            lay.addWidget(_ability_card(f"[Wargear] {ab_name}", ab_effect))

    # ── Invulnerable Save ────────────────────────────────────────────────────
    inv_saves = abilities.get("invulnerablesave", []) if isinstance(abilities, dict) else []
    if inv_saves:
        lay.addWidget(_section_header("Invulnerable Save"))
        for inv in inv_saves:
            save_val = inv.get("save", "") if isinstance(inv, dict) else str(inv)
            lay.addWidget(_ability_card("", f"✦ {save_val} Invulnerable Save"))

    # ── Wargear options ──────────────────────────────────────────────────────
    wargear_opts = data.get("wargearoptions", [])
    filtered_opts = [o for o in wargear_opts if o and o.lower() != "none"]
    if filtered_opts:
        lay.addWidget(_section_header("Wargear Options"))
        for opt in filtered_opts:
            opt_f = QFrame()
            opt_f.setStyleSheet(f"background: {_BG3}; border-radius: 3px;")
            opt_lay = QHBoxLayout(opt_f)
            opt_lay.setContentsMargins(10, 6, 10, 6)
            dot = QLabel("•")
            dot.setStyleSheet(f"color: {_ACCENT}; background: transparent; border: none;")
            txt = QLabel(opt)
            txt.setStyleSheet(
                f"color: {_FG_MID}; font-size: 11px; background: transparent; border: none;"
            )
            txt.setWordWrap(True)
            opt_lay.addWidget(dot)
            opt_lay.addWidget(txt, 1)
            lay.addWidget(opt_f)

    # ── Unit Composition ─────────────────────────────────────────────────────
    unitcompo = data.get("unitcompo", {})
    if unitcompo:
        lay.addWidget(_section_header("Unit Composition"))
        compo_f = QFrame()
        compo_f.setStyleSheet(f"background: {_BG3}; border-radius: 4px;")
        compo_lay = QVBoxLayout(compo_f)
        compo_lay.setContentsMargins(12, 8, 12, 8)
        compo_lay.setSpacing(4)

        for u in unitcompo.get("units", []):
            amount = u.get("amount", "1")
            uname  = u.get("unit", "")
            lbl = QLabel(f"•  {amount}x {uname}")
            lbl.setStyleSheet(
                f"color: {_FG_MID}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
            compo_lay.addWidget(lbl)

        default_wg = unitcompo.get("defaultwargear", "")
        if default_wg:
            lbl = QLabel(default_wg)
            lbl.setStyleSheet(
                f"color: {_FG_DIM}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
            lbl.setWordWrap(True)
            compo_lay.addWidget(lbl)

        for leader in unitcompo.get("leader", []):
            l_lbl = QLabel(f"Leader: {leader}")
            l_lbl.setStyleSheet(
                f"color: {_FG_MID}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
            compo_lay.addWidget(l_lbl)

        transport = unitcompo.get("transport", "")
        if transport:
            t_lbl = QLabel(f"Transport: {transport}")
            t_lbl.setStyleSheet(
                f"color: {_FG_MID}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
            t_lbl.setWordWrap(True)
            compo_lay.addWidget(t_lbl)

        supreme = unitcompo.get("supremecommander", "")
        if supreme:
            s_lbl = QLabel(supreme)
            s_lbl.setStyleSheet(
                f"color: {_WARN}; font-size: 11px; font-weight: 600; "
                f"background: transparent; border: none;"
            )
            s_lbl.setWordWrap(True)
            compo_lay.addWidget(s_lbl)

        lay.addWidget(compo_f)

    # ── Flavour text ─────────────────────────────────────────────────────────
    flavour = data.get("flavortext", "")
    if flavour:
        lay.addWidget(_divider())
        fl = QLabel(flavour)
        fl.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 11px; font-style: italic; "
            f"background: transparent; border: none;"
        )
        fl.setWordWrap(True)
        lay.addWidget(fl)

    lay.addStretch()
    return outer


def _build_aos_detail(entity: dict) -> QWidget:
    data = entity.get("data", {})
    if not data and entity.get("data_json"):
        try:
            data = json.loads(entity["data_json"])
        except Exception:
            data = {}

    outer = QWidget()
    outer.setStyleSheet(f"background: {_BG2};")
    lay = QVBoxLayout(outer)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(8)

    # ── Header ──────────────────────────────────────────────────────────────
    hdr = QFrame()
    hdr.setStyleSheet(f"background: {_BG3}; border-radius: 6px;")
    hdr_lay = QVBoxLayout(hdr)
    hdr_lay.setContentsMargins(16, 12, 16, 12)
    hdr_lay.setSpacing(4)

    faction = entity.get("faction", "")
    unit_name = data.get("name", entity.get("name", ""))

    top_row = QHBoxLayout()
    name_lbl = QLabel(unit_name)
    name_lbl.setStyleSheet(
        f"color: {_FG}; font-size: 22px; font-weight: 700; "
        f"background: transparent; border: none;"
    )
    name_lbl.setWordWrap(True)
    top_row.addWidget(name_lbl, 1)
    if faction:
        top_row.addWidget(_badge(faction, _SUCCESS))
    hdr_lay.addLayout(top_row)

    size = data.get("size", "")
    if size:
        size_lbl = QLabel(f"Base: {size}")
        size_lbl.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 11px; background: transparent; border: none;"
        )
        hdr_lay.addWidget(size_lbl)

    lay.addWidget(hdr)

    # ── Stats bar ────────────────────────────────────────────────────────────
    lay.addWidget(_section_header("Stats"))
    bar = QHBoxLayout()
    bar.setSpacing(6)
    stat_defs = [
        ("Move",    data.get("move", "")),
        ("Wounds",  data.get("wounds", "")),
        ("Save",    data.get("save", "")),
        ("Bravery", data.get("bravery", "")),
    ]
    for label, val in stat_defs:
        bar.addWidget(_stat_cell(label, str(val) if val else "", _SUCCESS), 1)
    bar_w = QWidget()
    bar_w.setStyleSheet("background: transparent;")
    bar_w.setLayout(bar)
    lay.addWidget(bar_w)

    # ── Melee Weapons ────────────────────────────────────────────────────────
    melee_weapons = data.get("melee_weapon", [])
    if melee_weapons:
        lay.addWidget(_section_header("Melee Weapons"))
        headers = ["Name", "Rng", "A", "Hit", "Wound", "Rend", "D"]
        rows = []
        for w in melee_weapons:
            rows.append([
                w.get("name", ""),
                w.get("range", ""),
                w.get("attacks", ""),
                w.get("to_hit", ""),
                w.get("to_wound", ""),
                w.get("rend", ""),
                w.get("damage", ""),
            ])
        lay.addWidget(_weapons_table(headers, rows))

    # ── Missile Weapons ──────────────────────────────────────────────────────
    missile_weapons = data.get("missile_weapon", [])
    if missile_weapons:
        lay.addWidget(_section_header("Ranged Weapons"))
        headers = ["Name", "Rng", "A", "Hit", "Wound", "Rend", "D"]
        rows = []
        for w in missile_weapons:
            rows.append([
                w.get("name", ""),
                w.get("range", ""),
                w.get("attacks", ""),
                w.get("to_hit", ""),
                w.get("to_wound", ""),
                w.get("rend", ""),
                w.get("damage", ""),
            ])
        lay.addWidget(_weapons_table(headers, rows))

    # ── Abilities — handle both AoS typo variants ────────────────────────────
    abilities = data.get("abilites", data.get("abilities", []))
    if abilities:
        lay.addWidget(_section_header("Abilities"))
        for ab in abilities:
            if isinstance(ab, dict):
                lay.addWidget(_ability_card(ab.get("name", ""), ab.get("desc", "")))
            elif isinstance(ab, str):
                lay.addWidget(_ability_card("", ab))

    # ── Command Abilities — handle typo variant ──────────────────────────────
    cmd_abs = data.get("command_abilites", data.get("command_abilities", []))
    if cmd_abs:
        lay.addWidget(_section_header("Command Abilities"))
        for ab in cmd_abs:
            if isinstance(ab, dict):
                lay.addWidget(
                    _ability_card(ab.get("name", "") + " (CMD)", ab.get("desc", ""))
                )
            elif isinstance(ab, str):
                lay.addWidget(_ability_card("(CMD)", ab))

    # ── Keywords ─────────────────────────────────────────────────────────────
    keywords = data.get("keywords", [])
    if keywords:
        lay.addWidget(_section_header("Keywords"))
        kw_f = QFrame()
        kw_f.setStyleSheet(f"background: {_BG3}; border-radius: 4px;")
        kw_lay = QHBoxLayout(kw_f)
        kw_lay.setContentsMargins(12, 8, 12, 8)
        kw_lay.setSpacing(6)
        kw_lay.setAlignment(Qt.AlignmentFlag.AlignLeft)
        for kw in keywords:
            kw_lbl = QLabel(str(kw).upper())
            kw_lbl.setStyleSheet(
                f"background: {_BG2}; color: {_FG_MID}; font-size: 10px; "
                f"font-weight: 600; padding: 2px 6px; border-radius: 2px; "
                f"border: 1px solid {_BORDER2};"
            )
            kw_lay.addWidget(kw_lbl)
        kw_lay.addStretch()
        lay.addWidget(kw_f)

    lay.addStretch()
    return outer


def _build_dnd_detail(entity: dict) -> QWidget:
    data = entity.get("data", {})
    if not data and entity.get("data_json"):
        try:
            data = json.loads(entity["data_json"])
        except Exception:
            data = {}

    outer = QWidget()
    outer.setStyleSheet(f"background: {_BG2};")
    lay = QVBoxLayout(outer)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(8)

    # ── Header ──────────────────────────────────────────────────────────────
    props = data.get("properties", {})
    name = data.get("name", entity.get("name", ""))
    monster_type = props.get("Type", "") or entity.get("faction", "")
    size   = props.get("Size", "")
    align  = props.get("Alignment", "")
    cr     = props.get("Challenge Rating", "")
    pub    = data.get("publisher", "")
    book   = data.get("book", "")

    hdr = QFrame()
    hdr.setStyleSheet(f"background: {_BG3}; border-radius: 6px;")
    hdr_lay = QVBoxLayout(hdr)
    hdr_lay.setContentsMargins(16, 12, 16, 12)
    hdr_lay.setSpacing(4)

    name_lbl = QLabel(name)
    name_lbl.setStyleSheet(
        f"color: {_FG}; font-size: 22px; font-weight: 700; "
        f"background: transparent; border: none;"
    )
    name_lbl.setWordWrap(True)
    hdr_lay.addWidget(name_lbl)

    meta_parts = []
    if size:
        meta_parts.append(size)
    if monster_type:
        meta_parts.append(monster_type.capitalize())
    if align:
        meta_parts.append(align)
    if meta_parts:
        meta_lbl = QLabel(", ".join(meta_parts))
        meta_lbl.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 12px; font-style: italic; "
            f"background: transparent; border: none;"
        )
        hdr_lay.addWidget(meta_lbl)

    if pub or book:
        src_lbl = QLabel(f"Source: {pub} — {book}" if pub and book else pub or book)
        src_lbl.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 11px; background: transparent; border: none;"
        )
        hdr_lay.addWidget(src_lbl)

    lay.addWidget(hdr)

    # ── CR badge row ──────────────────────────────────────────────────────────
    if cr or size or monster_type:
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        if cr:
            badge_row.addWidget(_badge(f"CR: {cr}", "#e07800"))
        if size:
            badge_row.addWidget(_badge(size, _FG_DIM))
        if monster_type:
            badge_row.addWidget(_badge(monster_type.capitalize(), "#9b59b6"))
        badge_row.addStretch()
        bw = QWidget()
        bw.setStyleSheet("background: transparent;")
        bw.setLayout(badge_row)
        lay.addWidget(bw)

    # ── Description ──────────────────────────────────────────────────────────
    description = data.get("description", "")
    if description:
        lay.addWidget(_section_header("Description"))
        desc_f = QFrame()
        desc_f.setStyleSheet(f"background: {_BG3}; border-radius: 4px;")
        desc_lay = QVBoxLayout(desc_f)
        desc_lay.setContentsMargins(12, 10, 12, 10)
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet(
            f"color: {_FG_MID}; font-size: 12px; background: transparent; border: none;"
        )
        desc_lbl.setWordWrap(True)
        desc_lay.addWidget(desc_lbl)
        lay.addWidget(desc_f)

    lay.addStretch()
    return outer


def _build_custom_detail(entity: dict) -> QWidget:
    data = entity.get("data", {})
    if not data and entity.get("data_json"):
        try:
            data = json.loads(entity["data_json"])
        except Exception:
            data = {}

    outer = QWidget()
    outer.setStyleSheet(f"background: {_BG2};")
    lay = QVBoxLayout(outer)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(8)

    # ── Header ──────────────────────────────────────────────────────────────
    hdr = QFrame()
    hdr.setStyleSheet(f"background: {_BG3}; border-radius: 6px;")
    hdr_lay = QVBoxLayout(hdr)
    hdr_lay.setContentsMargins(16, 12, 16, 12)
    hdr_lay.setSpacing(4)

    name_lbl = QLabel(entity.get("name", ""))
    name_lbl.setStyleSheet(
        f"color: {_FG}; font-size: 22px; font-weight: 700; "
        f"background: transparent; border: none;"
    )
    name_lbl.setWordWrap(True)
    hdr_lay.addWidget(name_lbl)

    meta_row = QHBoxLayout()
    meta_row.setSpacing(8)
    meta_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
    etype = entity.get("entity_type", "")
    faction = entity.get("faction", "")
    if etype:
        meta_row.addWidget(_badge(etype, _ACCENT))
    if faction:
        meta_row.addWidget(_badge(faction, _FG_DIM))
    meta_row.addStretch()
    mw = QWidget()
    mw.setStyleSheet("background: transparent;")
    mw.setLayout(meta_row)
    hdr_lay.addWidget(mw)
    lay.addWidget(hdr)

    # ── Stats ────────────────────────────────────────────────────────────────
    stats = data.get("stats", {})
    if stats:
        lay.addWidget(_section_header("Stats"))
        if isinstance(stats, dict):
            bar = QHBoxLayout()
            bar.setSpacing(6)
            for label, val in stats.items():
                bar.addWidget(_stat_cell(label, str(val)), 1)
            bw = QWidget()
            bw.setStyleSheet("background: transparent;")
            bw.setLayout(bar)
            lay.addWidget(bw)

    # ── Abilities ────────────────────────────────────────────────────────────
    abilities = data.get("abilities", [])
    if abilities:
        lay.addWidget(_section_header("Abilities"))
        for ab in abilities:
            if isinstance(ab, dict):
                lay.addWidget(_ability_card(ab.get("name", ""), ab.get("effect", "")))
            elif isinstance(ab, str):
                lay.addWidget(_ability_card("", ab))

    # ── Notes ────────────────────────────────────────────────────────────────
    notes = data.get("notes", "")
    if notes:
        lay.addWidget(_section_header("Notes"))
        notes_f = QFrame()
        notes_f.setStyleSheet(f"background: {_BG3}; border-radius: 4px;")
        notes_lay = QVBoxLayout(notes_f)
        notes_lay.setContentsMargins(12, 10, 12, 10)
        notes_lbl = QLabel(notes)
        notes_lbl.setStyleSheet(
            f"color: {_FG_MID}; font-size: 12px; background: transparent; border: none;"
        )
        notes_lbl.setWordWrap(True)
        notes_lay.addWidget(notes_lbl)
        lay.addWidget(notes_f)

    lay.addStretch()
    return outer


# ── List item widget ──────────────────────────────────────────────────────────

class _EntityItemWidget(QFrame):
    """Custom row widget for the entity list."""

    def __init__(self, entity: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: transparent; border: none;"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 8, 4)
        lay.setSpacing(0)

        # Colored system indicator strip
        sys_id = entity.get("system_id", "")
        color  = _SYS_COLORS.get(sys_id, _FG_DIM)
        strip  = QFrame()
        strip.setFixedWidth(4)
        strip.setStyleSheet(f"background: {color}; border: none; border-radius: 2px;")
        lay.addWidget(strip)
        lay.addSpacing(10)

        # Center: name + faction/type sublabel
        center = QVBoxLayout()
        center.setSpacing(1)
        name_lbl = QLabel(entity.get("name", ""))
        name_lbl.setStyleSheet(
            f"color: {_FG}; font-size: 12px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        name_lbl.setWordWrap(False)
        sub_parts = []
        if entity.get("faction"):
            sub_parts.append(entity["faction"])
        if entity.get("entity_type"):
            sub_parts.append(entity["entity_type"])
        sub_lbl = QLabel(" · ".join(sub_parts) if sub_parts else "")
        sub_lbl.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 10px; background: transparent; border: none;"
        )
        center.addWidget(name_lbl)
        center.addWidget(sub_lbl)
        lay.addLayout(center, 1)

        # Right: source badge
        source = entity.get("source", "")
        if source:
            src_lbl = QLabel(source[:20] + "…" if len(source) > 20 else source)
            src_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            src_lbl.setStyleSheet(
                f"background: {_BG3}; color: {_FG_DIM}; font-size: 9px; "
                f"padding: 1px 4px; border-radius: 2px; border: none;"
            )
            lay.addWidget(src_lbl)

        self.setMinimumHeight(52)


# ── Import Dialog ─────────────────────────────────────────────────────────────

class _ImportDialog(QDialog):

    def __init__(self, service, parent=None, system_id: str = "all"):
        super().__init__(parent)
        self._svc       = service
        self._system_id = system_id  # "all"/"custom" = show all; else filter
        self.setWindowTitle("Import Game Data")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(f"""
            QDialog {{ background: {_BG2}; color: {_FG}; }}
            QGroupBox {{
                background: {_BG3}; border: 1px solid {_BORDER};
                border-radius: 6px; margin-top: 12px; padding-top: 8px;
                color: {_FG}; font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px; left: 10px;
            }}
            QComboBox {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 4px; padding: 4px 8px;
            }}
            QComboBox:focus {{ border-color: {_ACCENT}; }}
            QComboBox QAbstractItemView {{ background: {_BG3}; color: {_FG}; }}
            QLabel {{ background: transparent; border: none; }}
            QPushButton {{
                background: {_ACCENT}; color: #fff; border: none;
                border-radius: 5px; font-weight: 600; padding: 6px 14px;
            }}
            QPushButton:hover {{ background: #6aaeff; }}
            QPushButton:disabled {{ background: {_BG3}; color: {_FG_DIM}; }}
            QPushButton#closeBtn {{
                background: {_BG3}; color: {_FG_MID};
                border: 1px solid {_BORDER};
            }}
            QProgressBar {{
                background: {_BG3}; border: 1px solid {_BORDER};
                border-radius: 4px; color: {_FG};
            }}
            QProgressBar::chunk {{ background: {_ACCENT}; border-radius: 3px; }}
        """)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QLabel("Import Game Data")
        title.setStyleSheet(
            f"color: {_FG}; font-size: 16px; font-weight: 700;"
        )
        root.addWidget(title)

        # Determine which sections to show
        show_all = self._system_id in ("all", "custom")
        show_wh  = show_all or self._system_id == "wh40k"
        show_aos = show_all or self._system_id == "aos"
        show_dnd = show_all or self._system_id == "dnd5e"

        if not show_all:
            sys_names = {"wh40k": "Warhammer 40K", "aos": "Age of Sigmar", "dnd5e": "D&D 5e"}
            hint = QLabel(f"Showing imports for {sys_names.get(self._system_id, self._system_id)} only.")
            hint.setStyleSheet(f"color: {_FG_DIM}; font-size: 11px;")
            root.addWidget(hint)

        # ── Warhammer 40K ─────────────────────────────────────────────────────
        wh_box = QGroupBox("Warhammer 40K 10th Edition")
        wh_lay = QVBoxLayout(wh_box)
        wh_lay.setSpacing(8)

        wh_row = QHBoxLayout()
        self._wh_faction_combo = QComboBox()
        self._wh_faction_combo.addItem("All Factions", None)
        try:
            for fac in self._svc.get_wh40k_factions():
                self._wh_faction_combo.addItem(fac, fac)
        except Exception:
            pass
        wh_row.addWidget(QLabel("Faction:"))
        wh_row.addWidget(self._wh_faction_combo, 1)
        wh_import_btn = QPushButton("Import")
        wh_import_btn.clicked.connect(self._import_wh40k)
        wh_row.addWidget(wh_import_btn)
        wh_lay.addLayout(wh_row)

        self._wh_status = QLabel("Not imported")
        self._wh_status.setStyleSheet(f"color: {_FG_DIM}; font-size: 11px;")
        wh_lay.addWidget(self._wh_status)

        try:
            if self._svc.has_data("wh40k"):
                n = self._svc.get_stats()["wh40k"]
                self._wh_status.setText(f"✅  {n:,} units loaded")
                self._wh_status.setStyleSheet(f"color: {_SUCCESS}; font-size: 11px;")
        except Exception:
            pass

        wh_box.setVisible(show_wh)
        root.addWidget(wh_box)

        # ── Age of Sigmar ─────────────────────────────────────────────────────
        aos_box = QGroupBox("Age of Sigmar")
        aos_lay = QVBoxLayout(aos_box)
        aos_lay.setSpacing(8)

        aos_row = QHBoxLayout()
        self._aos_army_combo = QComboBox()
        self._aos_army_combo.addItem("All Armies", None)
        try:
            for arm in self._svc.get_aos_armies():
                fname = arm.lower().replace(" ", "_") + ".json"
                self._aos_army_combo.addItem(arm, fname)
        except Exception:
            pass
        aos_row.addWidget(QLabel("Army:"))
        aos_row.addWidget(self._aos_army_combo, 1)
        aos_import_btn = QPushButton("Import")
        aos_import_btn.clicked.connect(self._import_aos)
        aos_row.addWidget(aos_import_btn)
        aos_lay.addLayout(aos_row)

        self._aos_status = QLabel("Not imported")
        self._aos_status.setStyleSheet(f"color: {_FG_DIM}; font-size: 11px;")
        aos_lay.addWidget(self._aos_status)

        try:
            if self._svc.has_data("aos"):
                n = self._svc.get_stats()["aos"]
                self._aos_status.setText(f"✅  {n:,} warscrolls loaded")
                self._aos_status.setStyleSheet(f"color: {_SUCCESS}; font-size: 11px;")
        except Exception:
            pass

        aos_box.setVisible(show_aos)
        root.addWidget(aos_box)

        # ── D&D 5e — Rules & Content ──────────────────────────────────────────
        dnd_box = QGroupBox("D&D 5e — Rules & Content")
        dnd_lay = QVBoxLayout(dnd_box)
        dnd_lay.setSpacing(6)

        # Each content type gets its own row: label | status | Import button
        dnd_content = [
            ("Spells",      "5,849 spells",      "D&D 5e — Spells",      "_import_dnd_spells"),
            ("Classes",     "134 classes",        "D&D 5e — Classes",     "_import_dnd_classes"),
            ("Backgrounds", "405 backgrounds",    "D&D 5e — Backgrounds", "_import_dnd_backgrounds"),
            ("Species",     "383 species/races",  "D&D 5e — Species",     "_import_dnd_species"),
            ("Items",       "15,749 items",        "D&D 5e — Items",       "_import_dnd_items"),
            ("Monsters",    "11,463 monsters ⚠",  "D&D 5e — Monsters",    "_import_dnd_monsters"),
        ]
        self._dnd_status_labels: dict[str, QLabel] = {}

        for label, count_hint, source, slot in dnd_content:
            row = QHBoxLayout()
            row.setSpacing(8)

            name_lbl = QLabel(f"{label}  <span style='color:{_FG_DIM}; font-size:10px;'>({count_hint})</span>")
            name_lbl.setTextFormat(Qt.TextFormat.RichText)
            name_lbl.setStyleSheet("background:transparent; border:none;")
            name_lbl.setMinimumWidth(220)
            row.addWidget(name_lbl)

            status_lbl = QLabel("—")
            status_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none;")
            try:
                if self._svc.has_data("dnd5e"):
                    existing = self._svc.get_entities(
                        system_id="dnd5e",
                        entity_type=label.rstrip("s").capitalize() if label != "Species" else "Species",
                        limit=1,
                    )
                    if existing:
                        n = self._svc._repo.count(system_id="dnd5e") if label == "Monsters" else len(
                            self._svc.get_entities(system_id="dnd5e",
                                                   entity_type=label if label != "Species" else "Species",
                                                   limit=99999)
                        )
                        status_lbl.setText(f"✅ loaded")
                        status_lbl.setStyleSheet(f"color:{_SUCCESS}; font-size:11px; background:transparent; border:none;")
            except Exception:
                pass
            self._dnd_status_labels[label] = status_lbl
            row.addWidget(status_lbl)

            row.addStretch()
            import_btn = QPushButton("Import")
            import_btn.setFixedHeight(26)
            import_btn.clicked.connect(lambda _, s=slot, lbl=label: self._import_dnd_type(s.lstrip("_"), lbl))
            row.addWidget(import_btn)

            dnd_lay.addLayout(row)

        dnd_lay.addWidget(_hline_widget())

        all_row = QHBoxLayout()
        all_btn = QPushButton("⬇  Import All D&D 5e Content")
        all_btn.clicked.connect(self._import_dnd_all)
        warn_lbl = QLabel("Large import — may take 60+ seconds")
        warn_lbl.setStyleSheet(f"color:{_WARN}; font-size:11px; background:transparent; border:none;")
        all_row.addWidget(all_btn)
        all_row.addWidget(warn_lbl)
        all_row.addStretch()
        dnd_lay.addLayout(all_row)

        dnd_box.setVisible(show_dnd)
        root.addWidget(dnd_box)

        # ── Progress bar ──────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFixedHeight(12)
        root.addWidget(self._progress)

        # ── Close button ──────────────────────────────────────────────────────
        close_btn = QPushButton("Close")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

    def _set_progress(self, current: int, total: int, name: str):
        self._progress.setVisible(True)
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        QApplication.processEvents()

    def _import_wh40k(self):
        faction = self._wh_faction_combo.currentData()
        self._wh_status.setText("Importing…")
        self._wh_status.setStyleSheet(f"color: {_FG_DIM}; font-size: 11px;")
        self._progress.setValue(0)
        QApplication.processEvents()
        try:
            result = self._svc.import_wh40k(
                faction_filter=faction,
                progress_cb=self._set_progress,
            )
            n = result.get("imported", 0)
            factions_str = f" ({faction})" if faction else ""
            self._wh_status.setText(f"✅  {n:,} units imported{factions_str}")
            self._wh_status.setStyleSheet(f"color: {_SUCCESS}; font-size: 11px;")
        except Exception as e:
            self._wh_status.setText(f"❌  Error: {e}")
            self._wh_status.setStyleSheet(f"color: {_DANGER}; font-size: 11px;")
        self._progress.setVisible(False)

    def _import_aos(self):
        army_file = self._aos_army_combo.currentData()
        army_name = self._aos_army_combo.currentText()
        self._aos_status.setText("Importing…")
        self._aos_status.setStyleSheet(f"color: {_FG_DIM}; font-size: 11px;")
        self._progress.setValue(0)
        QApplication.processEvents()
        try:
            result = self._svc.import_aos(
                army_file=army_file,
                progress_cb=self._set_progress,
            )
            n = result.get("imported", 0)
            label = f" ({army_name})" if army_file else ""
            self._aos_status.setText(f"✅  {n:,} warscrolls imported{label}")
            self._aos_status.setStyleSheet(f"color: {_SUCCESS}; font-size: 11px;")
        except Exception as e:
            self._aos_status.setText(f"❌  Error: {e}")
            self._aos_status.setStyleSheet(f"color: {_DANGER}; font-size: 11px;")
        self._progress.setVisible(False)

    def _import_dnd_type(self, method_slot: str, label: str):
        """Import a single D&D content type by method name."""
        status_lbl = self._dnd_status_labels.get(label)
        if status_lbl:
            status_lbl.setText("Importing…")
            status_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none;")
        self._progress.setVisible(True)
        self._progress.setValue(0)
        QApplication.processEvents()
        try:
            fn = getattr(self._svc, method_slot)
            result = fn(progress_cb=self._set_progress)
            n = result.get("imported", 0)
            if status_lbl:
                status_lbl.setText(f"✅ {n:,} imported")
                status_lbl.setStyleSheet(f"color:{_SUCCESS}; font-size:11px; background:transparent; border:none;")
        except Exception as e:
            if status_lbl:
                status_lbl.setText(f"❌ Error: {e}")
                status_lbl.setStyleSheet(f"color:{_DANGER}; font-size:11px; background:transparent; border:none;")
        self._progress.setVisible(False)

    def _import_dnd_all(self):
        """Import all D&D 5e content types."""
        for lbl in self._dnd_status_labels.values():
            lbl.setText("Queued…")
            lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:11px; background:transparent; border:none;")
        self._progress.setVisible(True)
        self._progress.setValue(0)
        QApplication.processEvents()
        try:
            result = self._svc.import_dnd_all(progress_cb=self._set_progress)
            breakdown = result.get("breakdown", {})
            for content_label, n in breakdown.items():
                lbl = self._dnd_status_labels.get(content_label)
                if lbl:
                    lbl.setText(f"✅ {n:,} imported")
                    lbl.setStyleSheet(f"color:{_SUCCESS}; font-size:11px; background:transparent; border:none;")
        except Exception as e:
            for lbl in self._dnd_status_labels.values():
                lbl.setText(f"❌ Error: {e}")
                lbl.setStyleSheet(f"color:{_DANGER}; font-size:11px; background:transparent; border:none;")
        self._progress.setVisible(False)


def _hline_widget() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{_BORDER}; border:none;")
    return f


# ── Custom Entry Dialog ───────────────────────────────────────────────────────

class _CustomEntryDialog(QDialog):

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self._svc = service
        self.setWindowTitle("Add Custom Entry")
        self.setModal(True)
        self.setMinimumWidth(540)
        self.setMinimumHeight(600)
        self.setStyleSheet(f"""
            QDialog {{ background: {_BG2}; color: {_FG}; }}
            QLabel {{ color: {_FG}; background: transparent; border: none; }}
            QLineEdit, QTextEdit, QComboBox {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                border-radius: 4px; padding: 4px 8px;
            }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
                border-color: {_ACCENT};
            }}
            QComboBox QAbstractItemView {{ background: {_BG3}; color: {_FG}; }}
            QPushButton {{
                background: {_ACCENT}; color: #fff; border: none;
                border-radius: 5px; font-weight: 600; padding: 6px 14px;
            }}
            QPushButton:hover {{ background: #6aaeff; }}
            QPushButton#cancelBtn {{
                background: {_BG3}; color: {_FG_MID};
                border: 1px solid {_BORDER};
            }}
            QPushButton#addStatBtn {{
                background: {_BG3}; color: {_FG_MID};
                border: 1px solid {_BORDER}; font-size: 11px; padding: 4px 10px;
            }}
            QTableWidget {{
                background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER};
                gridline-color: {_BORDER};
            }}
            QTableWidget QHeaderView::section {{
                background: {_BG3}; color: {_FG_DIM}; border: none;
                font-size: 10px; font-weight: 600; padding: 4px;
            }}
        """)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        title = QLabel("Add Custom Entry")
        title.setStyleSheet(
            f"color: {_FG}; font-size: 16px; font-weight: 700;"
        )
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(_SCROLLBAR_STYLE)
        inner = QWidget()
        inner.setStyleSheet(f"background: {_BG2};")
        form = QFormLayout(inner)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # System
        self._sys_combo = QComboBox()
        for label, sid in [
            ("Warhammer 40K", "wh40k"),
            ("Age of Sigmar",  "aos"),
            ("D&D 5e",         "dnd5e"),
            ("Other",          "custom"),
        ]:
            self._sys_combo.addItem(label, sid)
        form.addRow("System:", self._sys_combo)

        # Entity Type
        self._type_edit = QLineEdit()
        self._type_edit.setPlaceholderText("e.g. Unit, Stratagem, Rule")
        form.addRow("Entity Type:", self._type_edit)

        # Faction
        self._faction_edit = QLineEdit()
        self._faction_edit.setPlaceholderText("e.g. Space Marines, Khorne")
        form.addRow("Faction:", self._faction_edit)

        # Name (required)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Required")
        form.addRow("Name *:", self._name_edit)

        # Source
        self._source_edit = QLineEdit()
        self._source_edit.setPlaceholderText("e.g. Homebrew, House Rules")
        form.addRow("Source:", self._source_edit)

        # Notes / Description
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Description, notes, rules text…")
        self._notes_edit.setMinimumHeight(100)
        form.addRow("Notes:", self._notes_edit)

        # Stats table
        stats_lbl = QLabel("Stats:")
        stats_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        stats_lbl.setContentsMargins(0, 6, 0, 0)

        stats_container = QWidget()
        stats_container.setStyleSheet("background: transparent;")
        stats_v = QVBoxLayout(stats_container)
        stats_v.setContentsMargins(0, 0, 0, 0)
        stats_v.setSpacing(4)

        self._stats_table = QTableWidget(0, 2)
        self._stats_table.setHorizontalHeaderLabels(["Stat", "Value"])
        self._stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._stats_table.verticalHeader().setVisible(False)
        self._stats_table.setFixedHeight(120)
        # Add 3 empty rows
        for _ in range(3):
            self._add_stat_row()
        stats_v.addWidget(self._stats_table)

        add_stat_btn = QPushButton("+ Add Stat")
        add_stat_btn.setObjectName("addStatBtn")
        add_stat_btn.clicked.connect(self._add_stat_row)
        stats_v.addWidget(add_stat_btn, 0, Qt.AlignmentFlag.AlignLeft)

        form.addRow(stats_lbl, stats_container)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    def _add_stat_row(self):
        row = self._stats_table.rowCount()
        self._stats_table.insertRow(row)
        self._stats_table.setItem(row, 0, QTableWidgetItem(""))
        self._stats_table.setItem(row, 1, QTableWidgetItem(""))

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Name is required.")
            return

        # Collect stats
        stats: dict[str, str] = {}
        for row in range(self._stats_table.rowCount()):
            key_item = self._stats_table.item(row, 0)
            val_item = self._stats_table.item(row, 1)
            key = key_item.text().strip() if key_item else ""
            val = val_item.text().strip() if val_item else ""
            if key:
                stats[key] = val

        try:
            self._svc.add_custom_entity(
                system_id=self._sys_combo.currentData() or "custom",
                entity_type=self._type_edit.text().strip(),
                faction=self._faction_edit.text().strip(),
                name=name,
                stats=stats,
                abilities=[],
                notes=self._notes_edit.toPlainText().strip(),
                campaign_id=None,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
            return
        self.accept()


# ── Main Rules Library UI ─────────────────────────────────────────────────────

class RulesLibraryUI(QWidget):
    """Full Rules Library panel — stat blocks, import, custom entries."""

    def __init__(self, service, context, parent=None):
        super().__init__(parent)
        self._svc            = service
        self._context        = context
        self._camp_id: Optional[int] = None
        self._active_system  = "all"
        self._campaign_sys   = "all"   # resolved system_id for current campaign
        self._search_timer   = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._reload_list)
        self._build()
        self._apply_theme()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(56)
        header.setStyleSheet(
            f"background: {_BG3}; border-bottom: 1px solid {_BORDER};"
        )
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(20, 0, 20, 0)
        h_lay.setSpacing(12)

        title_lbl = QLabel("\U0001f4da  Rules Library")
        title_lbl.setStyleSheet(
            f"color: {_FG}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        h_lay.addWidget(title_lbl)
        h_lay.addStretch()

        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 11px; background: transparent; border: none;"
        )
        h_lay.addWidget(self._stats_lbl)

        import_btn = QPushButton("⬇  Import Data")
        import_btn.setFixedHeight(32)
        import_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG2}; color: {_FG_MID}; "
            f"border: 1px solid {_BORDER}; border-radius: 5px; "
            f"font-weight: 600; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: {_BG3}; color: {_FG}; }}"
        )
        import_btn.clicked.connect(self._on_import)
        h_lay.addWidget(import_btn)

        add_btn = QPushButton("+ Custom Entry")
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT}; color: #fff; border: none; "
            f"border-radius: 5px; font-weight: 600; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: #6aaeff; }}"
        )
        add_btn.clicked.connect(self._on_add_custom)
        h_lay.addWidget(add_btn)

        root.addWidget(header)

        # ── System tab bar ────────────────────────────────────────────────────
        tab_bar = QFrame()
        tab_bar.setFixedHeight(44)
        tab_bar.setStyleSheet(
            f"background: {_BG2}; border-bottom: 1px solid {_BORDER};"
        )
        t_lay = QHBoxLayout(tab_bar)
        t_lay.setContentsMargins(16, 4, 16, 4)
        t_lay.setSpacing(4)

        self._tab_btns: dict[str, QPushButton] = {}
        tabs = [
            ("all",    "All"),
            ("wh40k",  "⚙  Warhammer 40K"),
            ("aos",    "\U0001f3f0  Age of Sigmar"),
            ("dnd5e",  "⚔  D&D 5e"),
            ("custom", "✏  Custom"),
        ]
        for sys_id, label in tabs:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setCheckable(False)
            btn.clicked.connect(lambda _, s=sys_id: self._on_system_tab(s))
            self._tab_btns[sys_id] = btn
            t_lay.addWidget(btn)
        t_lay.addStretch()

        root.addWidget(tab_bar)

        # ── Filter toolbar ────────────────────────────────────────────────────
        filter_bar = QFrame()
        filter_bar.setFixedHeight(48)
        filter_bar.setStyleSheet(
            f"background: {_BG2}; border-bottom: 1px solid {_BORDER};"
        )
        f_lay = QHBoxLayout(filter_bar)
        f_lay.setContentsMargins(16, 6, 16, 6)
        f_lay.setSpacing(8)

        fac_lbl = QLabel("Faction:")
        fac_lbl.setStyleSheet(f"color: {_FG_DIM}; font-size: 11px;")
        f_lay.addWidget(fac_lbl)

        self._faction_combo = QComboBox()
        self._faction_combo.setFixedWidth(180)
        self._faction_combo.setStyleSheet(
            f"background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER}; "
            f"border-radius: 4px; padding: 3px 8px;"
        )
        self._faction_combo.currentIndexChanged.connect(self._on_filter_changed)
        f_lay.addWidget(self._faction_combo)

        type_lbl = QLabel("Type:")
        type_lbl.setStyleSheet(f"color: {_FG_DIM}; font-size: 11px;")
        f_lay.addWidget(type_lbl)

        self._type_combo = QComboBox()
        self._type_combo.setFixedWidth(140)
        self._type_combo.setStyleSheet(
            f"background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER}; "
            f"border-radius: 4px; padding: 3px 8px;"
        )
        self._type_combo.currentIndexChanged.connect(self._on_filter_changed)
        f_lay.addWidget(self._type_combo)

        f_lay.addStretch()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search by name…")
        self._search_edit.setFixedWidth(220)
        self._search_edit.setStyleSheet(
            f"background: {_BG3}; color: {_FG}; border: 1px solid {_BORDER}; "
            f"border-radius: 4px; padding: 4px 8px;"
        )
        self._search_edit.textChanged.connect(self._on_search_changed)
        f_lay.addWidget(self._search_edit)

        root.addWidget(filter_bar)

        # ── Splitter ──────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {_BORDER}; width: 1px; }}"
        )

        # Left: entity list
        list_panel = QFrame()
        list_panel.setMinimumWidth(300)
        list_panel.setStyleSheet(f"background: {_BG2}; border: none;")
        list_lay = QVBoxLayout(list_panel)
        list_lay.setContentsMargins(0, 0, 0, 0)
        list_lay.setSpacing(0)

        self._entity_list = QListWidget()
        self._entity_list.setStyleSheet(
            f"QListWidget {{ background: {_BG2}; border: none; outline: none; }}"
            f"QListWidget::item {{ padding: 0px; border-bottom: 1px solid {_BORDER}; }}"
            f"QListWidget::item:selected {{ background: {_BG3}; }}"
            f"QListWidget::item:hover {{ background: {_BG3}; }}"
            + _SCROLLBAR_STYLE
        )
        self._entity_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._entity_list.currentItemChanged.connect(self._on_entity_selected)
        list_lay.addWidget(self._entity_list, 1)

        # Count label at bottom of list
        self._count_lbl = QLabel("")
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_lbl.setFixedHeight(24)
        self._count_lbl.setStyleSheet(
            f"background: {_BG3}; color: {_FG_DIM}; font-size: 10px; "
            f"border-top: 1px solid {_BORDER};"
        )
        list_lay.addWidget(self._count_lbl)

        splitter.addWidget(list_panel)

        # Right: detail view
        right_panel = QFrame()
        right_panel.setStyleSheet(f"background: {_BG2}; border: none;")
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self._detail_stack = QStackedWidget()
        self._detail_stack.setStyleSheet(f"background: {_BG2};")
        right_lay.addWidget(self._detail_stack, 1)

        # Empty state
        self._empty_state = self._build_empty_state()
        self._detail_stack.addWidget(self._empty_state)   # index 0

        # Detail scroll area (index 1)
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._detail_scroll.setStyleSheet(
            f"QScrollArea {{ background: {_BG2}; border: none; }}"
            + _SCROLLBAR_STYLE
        )
        self._detail_scroll_inner = QWidget()
        self._detail_scroll_inner.setStyleSheet(f"background: {_BG2};")
        placeholder_lay = QVBoxLayout(self._detail_scroll_inner)
        placeholder_lay.addStretch()
        self._detail_scroll.setWidget(self._detail_scroll_inner)
        self._detail_stack.addWidget(self._detail_scroll)   # index 1

        splitter.addWidget(right_panel)
        splitter.setSizes([380, 620])

        root.addWidget(splitter, 1)

        self._update_tab_styles()

    def _build_empty_state(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {_BG2};")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("\U0001f4da")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_lbl)

        msg = QLabel("Select an entry from the list\nto view its stat block")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 14px; background: transparent; border: none;"
        )
        lay.addWidget(msg)
        return w

    def _build_no_data_state(self, system_id: str) -> QWidget:
        sys_names = {
            "wh40k":  "Warhammer 40K",
            "aos":    "Age of Sigmar",
            "dnd5e":  "D&D 5e",
            "custom": "Custom",
        }
        sys_name = sys_names.get(system_id, system_id)

        w = QWidget()
        w.setStyleSheet(f"background: {_BG2};")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(12)

        icon_lbl = QLabel("\U0001f4e5")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_lbl)

        msg = QLabel(
            f"No {sys_name} data imported yet.\n"
            f"Click Import Data to load rules."
        )
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(
            f"color: {_FG_DIM}; font-size: 14px; background: transparent; border: none;"
        )
        lay.addWidget(msg)

        if system_id != "custom":
            import_btn = QPushButton("⬇  Import Now")
            import_btn.setFixedHeight(36)
            import_btn.setStyleSheet(
                f"QPushButton {{ background: {_ACCENT}; color: #fff; border: none; "
                f"border-radius: 5px; font-weight: 600; padding: 0 20px; }}"
                f"QPushButton:hover {{ background: #6aaeff; }}"
            )
            import_btn.clicked.connect(self._on_import)
            lay.addWidget(import_btn, 0, Qt.AlignmentFlag.AlignCenter)

        return w

    def _apply_theme(self):
        self.setStyleSheet(f"background: {_BG2}; color: {_FG};")

    # ── Tab management ────────────────────────────────────────────────────────

    def _update_tab_styles(self):
        for sys_id, btn in self._tab_btns.items():
            active = sys_id == self._active_system
            if active:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {_ACCENT}; color: #fff; border: none; "
                    f"border-radius: 5px; font-weight: 600; padding: 0 12px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {_BG2}; color: {_FG_MID}; border: none; "
                    f"border-radius: 5px; padding: 0 12px; }}"
                    f"QPushButton:hover {{ background: {_BG3}; color: {_FG}; }}"
                )

    def _on_system_tab(self, system_id: str):
        self._active_system = system_id
        self._update_tab_styles()
        self._update_faction_type_combos()
        self._reload_list()

    def _update_faction_type_combos(self):
        sys_id = self._active_system if self._active_system != "all" else None

        self._faction_combo.blockSignals(True)
        self._faction_combo.clear()
        self._faction_combo.addItem("All Factions", None)
        if sys_id and self._svc:
            try:
                for f in self._svc.get_factions(sys_id):
                    self._faction_combo.addItem(f, f)
            except Exception:
                pass
        self._faction_combo.blockSignals(False)

        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        self._type_combo.addItem("All Types", None)
        if sys_id and self._svc:
            try:
                for t in self._svc.get_entity_types(sys_id):
                    self._type_combo.addItem(t, t)
            except Exception:
                pass
        self._type_combo.blockSignals(False)

    # ── Filters ───────────────────────────────────────────────────────────────

    def _on_filter_changed(self):
        self._reload_list()

    def _on_search_changed(self):
        self._search_timer.start(200)

    # ── List ──────────────────────────────────────────────────────────────────

    def _reload_list(self):
        if not self._svc:
            return

        sys_id      = self._active_system if self._active_system != "all" else None
        faction     = self._faction_combo.currentData()
        entity_type = self._type_combo.currentData()
        search      = self._search_edit.text().strip() or None

        # If filtering to a single system with no data yet, show no-data state
        if sys_id and not self._svc.has_data(sys_id):
            self._entity_list.clear()
            self._count_lbl.setText("0 entries")
            # Replace empty state with no-data widget
            while self._detail_stack.count() > 0:
                self._detail_stack.removeWidget(self._detail_stack.widget(0))
            no_data = self._build_no_data_state(sys_id)
            self._detail_stack.addWidget(no_data)
            self._detail_stack.setCurrentIndex(0)
            return

        # Restore proper stack if we previously showed a no-data page
        if self._detail_stack.count() == 1 and not isinstance(
            self._detail_stack.widget(0), type(self._empty_state)
        ):
            self._detail_stack.removeWidget(self._detail_stack.widget(0))
            self._empty_state = self._build_empty_state()
            self._detail_stack.addWidget(self._empty_state)
            # Re-add scroll area
            if self._detail_stack.count() < 2:
                self._detail_stack.addWidget(self._detail_scroll)

        try:
            entities = self._svc.get_entities(
                system_id=sys_id,
                faction=faction,
                entity_type=entity_type,
                search=search,
                limit=500,
            )
        except Exception as e:
            log.error(f"[RulesLibUI] reload_list error: {e}")
            entities = []

        self._entity_list.clear()
        for ent in entities:
            item = QListWidgetItem()
            widget = _EntityItemWidget(ent)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, ent["id"])
            self._entity_list.addItem(item)
            self._entity_list.setItemWidget(item, widget)

        n = len(entities)
        self._count_lbl.setText(f"{n:,} {'entry' if n == 1 else 'entries'}")

        # Show empty state if nothing selected
        self._show_empty_state()

    # ── Detail ────────────────────────────────────────────────────────────────

    def _on_entity_selected(self, current, previous):
        if not current:
            self._show_empty_state()
            return
        entity_id = current.data(Qt.ItemDataRole.UserRole)
        if entity_id is None:
            self._show_empty_state()
            return
        try:
            entity = self._svc.get_entity(entity_id)
        except Exception as e:
            log.error(f"[RulesLibUI] get_entity error: {e}")
            return
        if not entity:
            return
        self._show_detail(entity)

    def _show_detail(self, entity: dict):
        sys_id = entity.get("system_id", "")

        if sys_id == "wh40k":
            content = _build_wh40k_detail(entity)
        elif sys_id == "aos":
            content = _build_aos_detail(entity)
        elif sys_id == "dnd5e":
            content = _build_dnd_detail(entity)
        else:
            content = _build_custom_detail(entity)

        # Ensure stack has the scroll area at index 1
        self._rebuild_detail_stack_if_needed()

        # Swap content into the scroll area
        old = self._detail_scroll.widget()
        if old:
            old.deleteLater()
        self._detail_scroll.setWidget(content)
        self._detail_stack.setCurrentIndex(1)

    def _rebuild_detail_stack_if_needed(self):
        """Ensure detail_stack has exactly: [0]=empty, [1]=scroll."""
        if self._detail_stack.count() < 2:
            # Re-add missing items
            while self._detail_stack.count() > 0:
                self._detail_stack.removeWidget(self._detail_stack.widget(0))
            self._empty_state = self._build_empty_state()
            self._detail_stack.addWidget(self._empty_state)
            self._detail_stack.addWidget(self._detail_scroll)

    def _show_empty_state(self):
        self._rebuild_detail_stack_if_needed()
        self._detail_stack.setCurrentIndex(0)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_import(self):
        if not self._svc:
            QMessageBox.information(self, "Rules Library", "Service not available.")
            return
        dlg = _ImportDialog(self._svc, self, system_id=self._campaign_sys)
        dlg.exec()
        self.refresh(self._camp_id)

    def _on_add_custom(self):
        if not self._svc:
            return
        dlg = _CustomEntryDialog(self._svc, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh(self._camp_id)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, campaign_id=None):
        """Called by the parent UI whenever this section becomes active."""
        self._camp_id = campaign_id

        # Resolve the campaign's game system so we can filter tabs and imports
        self._campaign_sys = "all"
        if campaign_id is not None:
            try:
                camp_svc = self._context.services.try_get("campaign_service")
                if camp_svc:
                    camp = camp_svc.get_campaign(campaign_id)
                    if camp:
                        self._campaign_sys = _resolve_campaign_system(
                            getattr(camp, "game_system", "") or ""
                        )
            except Exception:
                pass

        self._filter_tabs_for_system(self._campaign_sys)

        # Auto-select the campaign's system tab if it changed
        if self._campaign_sys not in ("all", "custom"):
            self._on_system_tab(self._campaign_sys)
        else:
            self._on_system_tab("all")

        self._update_stats_label()
        self._update_faction_type_combos()
        self._reload_list()

    def _filter_tabs_for_system(self, system_id: str):
        """Show only the relevant system tabs for the current campaign."""
        # Systems that have importable data
        importable = {"wh40k", "aos", "dnd5e"}

        for sid, btn in self._tab_btns.items():
            if system_id in ("all", "custom"):
                # No restriction — show everything
                btn.setVisible(True)
            elif sid == "all" or sid == "custom":
                # Always show All and Custom tabs
                btn.setVisible(True)
            elif sid == system_id:
                # Show the matching system tab
                btn.setVisible(True)
            else:
                # Hide unrelated systems
                btn.setVisible(False)

    def _update_stats_label(self):
        if not self._svc:
            self._stats_lbl.setText("")
            return
        try:
            stats = self._svc.get_stats()
            parts = []
            if stats["wh40k"]:
                parts.append(f"{stats['wh40k']:,} units")
            if stats["aos"]:
                parts.append(f"{stats['aos']:,} warscrolls")
            if stats["dnd5e"]:
                parts.append(f"{stats['dnd5e']:,} monsters")
            if stats["custom"]:
                parts.append(f"{stats['custom']:,} custom")
            self._stats_lbl.setText(" · ".join(parts) if parts else "No data imported")
        except Exception:
            self._stats_lbl.setText("")
