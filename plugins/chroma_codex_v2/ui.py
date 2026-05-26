"""
Chroma Codex 2.0 — Premium UI
═══════════════════════════════
Layout:
  Header  — accent dot · "Chroma Codex" · scheme count
  Splitter (horizontal, non-collapsible)
    Left   — search bar + scrollable saved-scheme cards
    Right  — generator controls + results grid + save/link bar
  Status bar
"""
from __future__ import annotations

import json
import logging
log = logging.getLogger(__name__)

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QSize
from PySide6.QtGui  import QColor, QPainter, QPen, QBrush, QPalette, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QSizePolicy, QSplitter, QColorDialog, QMessageBox, QListWidget,
    QListWidgetItem, QSlider, QGridLayout, QTextEdit,
)

# Import the pure-Python colour engine (no Qt — always safe)
from plugins.paint_scheme.chroma_codex import (
    engine      as chroma_engine,
    SCHEME_STYLES, STYLE_DESCRIPTIONS, ROLES, ROLE_META,
    RoleRecommendation, PaintMatch, ChromaResult,
    hex_to_hsl, hsl_to_hex, _target_hsl, color_distance,
    _GOOD_MATCH, _ALT_COUNT,
)

# ── Design system (matches model_tracker_v2 / paint_scheme_v2) ───────────────

_C = {
    "bg_deep":     "#0c0c0c",
    "bg_base":     "#121212",
    "bg_card":     "#1a1a1a",
    "bg_raised":   "#1f1f1f",
    "bg_input":    "#252525",
    "bg_hover":    "#2a2a2a",
    "bg_active":   "#2f2f2f",
    "border_lo":   "#1c1c1c",
    "border":      "#2a2a2a",
    "border_hi":   "#3a3a3a",
    "text_hi":     "#f2f2f2",
    "text_mid":    "#c2c2c2",
    "text_lo":     "#848484",
    "text_dim":    "#484848",
    "accent":      "#0078d4",
    "accent_hi":   "#1a8ee8",
    "accent_lo":   "#0a2a4a",
    "accent_text": "#60b0ff",
    "danger":      "#e05555",
    "danger_hi":   "#eb6868",
    "danger_lo":   "#2a1515",
    "success":     "#3dba6e",
    "success_lo":  "#0f2a1a",
    "warning":     "#e07800",
    "warning_lo":  "#2a1800",
    "gold":        "#c8960c",
    "gold_lo":     "#2a1e00",
}
_FS = {
    "xs":  "10px", "sm": "11px", "base": "12px", "lg": "13px",
    "xl":  "15px", "2xl": "20px", "3xl": "28px",
}
_R = {"xs": "3px", "sm": "5px", "base": "7px", "lg": "10px", "pill": "999px"}

# Match-quality colours
_MATCH_COLORS = {
    "excellent": "#3dba6e",
    "good":      "#f5a623",
    "fair":      "#e07c35",
    "none":      "#e05555",
}

COMMON_GAME_SYSTEMS = [
    "", "Warhammer 40,000", "Warhammer: Age of Sigmar",
    "Warhammer: The Old World", "Horus Heresy", "Kill Team", "Necromunda",
    "Middle Earth Strategy Battle Game", "Dungeons & Dragons",
    "Pathfinder", "Gundam", "Star Wars: Legion",
    "Marvel Crisis Protocol", "Bolt Action", "Other",
]

PERSONALITIES: list[str] = [
    "",
    "Regal", "Grimdark", "Noble", "Savage", "Ancient",
    "Corrupted", "Holy", "Industrial", "Arcane", "Feral",
    "Spectral", "Veteran", "Pristine", "Forsaken",
]

_PERSONALITY_META: dict[str, tuple[str, str, str]] = {
    "Regal":      ("#3a1854", "#d4a0f0", "👑"),
    "Grimdark":   ("#1c1c1c", "#909090", "💀"),
    "Noble":      ("#122040", "#7ab0f0", "⚜"),
    "Savage":     ("#3d1005", "#f08050", "🔥"),
    "Ancient":    ("#2e1e05", "#c8a040", "🏛"),
    "Corrupted":  ("#0a1e0a", "#5ec85e", "☣"),
    "Holy":       ("#2c2808", "#f0e060", "✝"),
    "Industrial": ("#14181c", "#8090a0", "⚙"),
    "Arcane":     ("#14083a", "#9868f0", "🔮"),
    "Feral":      ("#121e08", "#80a040", "🐾"),
    "Spectral":   ("#08121e", "#60c0f8", "👻"),
    "Veteran":    ("#1e1008", "#a07840", "🎖"),
    "Pristine":   ("#08202e", "#60d8f8", "⭐"),
    "Forsaken":   ("#120828", "#9060a8", "🌑"),
}


# ── Style helpers ─────────────────────────────────────────────────────────────

def _input_ss() -> str:
    return (
        f"QLineEdit, QTextEdit, QComboBox {{"
        f" background: {_C['bg_input']}; color: {_C['text_hi']};"
        f" border: 1px solid {_C['border']}; border-radius: {_R['sm']};"
        f" padding: 5px 10px; font-size: {_FS['base']}; }}"
        f"QLineEdit:focus, QTextEdit:focus, QComboBox:focus"
        f" {{ border-color: {_C['accent']}; background: {_C['bg_hover']}; }}"
        f"QComboBox::drop-down {{ border: none; width: 22px; }}"
        f"QComboBox QAbstractItemView {{"
        f" background: {_C['bg_card']}; color: {_C['text_hi']};"
        f" border: 1px solid {_C['border']};"
        f" selection-background-color: {_C['accent_lo']};"
        f" selection-color: {_C['accent_text']}; }}"
    )

def _primary_btn_ss(small: bool = False) -> str:
    pad = "4px 12px" if small else "6px 18px"
    fs  = _FS["sm"] if small else _FS["base"]
    return (
        f"QPushButton {{ background: {_C['accent']}; color: #fff; border: none;"
        f" border-radius: {_R['sm']}; padding: {pad}; font-size: {fs};"
        f" font-weight: 600; }}"
        f"QPushButton:hover {{ background: {_C['accent_hi']}; }}"
        f"QPushButton:disabled {{ background: {_C['bg_hover']};"
        f" color: {_C['text_dim']}; }}"
    )

def _secondary_btn_ss(small: bool = False) -> str:
    pad = "4px 10px" if small else "6px 14px"
    fs  = _FS["sm"] if small else _FS["base"]
    return (
        f"QPushButton {{ background: {_C['bg_card']}; color: {_C['text_mid']};"
        f" border: 1px solid {_C['border']}; border-radius: {_R['sm']};"
        f" padding: {pad}; font-size: {fs}; }}"
        f"QPushButton:hover {{ background: {_C['bg_hover']};"
        f" border-color: {_C['border_hi']}; color: {_C['text_hi']}; }}"
        f"QPushButton:disabled {{ color: {_C['text_dim']}; }}"
    )

def _danger_btn_ss(small: bool = False) -> str:
    pad = "4px 10px" if small else "6px 14px"
    fs  = _FS["sm"] if small else _FS["base"]
    return (
        f"QPushButton {{ background: {_C['danger_lo']}; color: {_C['danger']};"
        f" border: 1px solid {_C['danger_lo']}; border-radius: {_R['sm']};"
        f" padding: {pad}; font-size: {fs}; }}"
        f"QPushButton:hover {{ background: {_C['danger']}; color: #fff;"
        f" border-color: {_C['danger']}; }}"
        f"QPushButton:disabled {{ color: {_C['text_dim']}; }}"
    )

def _ghost_btn_ss(size: str = "12px") -> str:
    return (
        f"QPushButton {{ background: transparent; border: none;"
        f" color: {_C['text_lo']}; border-radius: {_R['xs']};"
        f" font-size: {size}; padding: 3px 6px; }}"
        f"QPushButton:hover {{ background: rgba(255,255,255,0.07);"
        f" color: {_C['text_mid']}; }}"
    )

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: {_FS['xs']}; font-weight: 700; color: {_C['text_lo']};"
        f" letter-spacing: 1px; background: transparent; border: none;"
    )
    return lbl

def _hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {_C['border_lo']}; border: none;")
    return f

def _swatch_label(hex_color: str, size: int = 14) -> QLabel:
    """Simple stylesheet swatch — safe on non-background child labels."""
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    c = hex_color if (hex_color and hex_color.startswith("#") and len(hex_color) == 7) else "#3a3a3a"
    lbl.setStyleSheet(
        f"background: {c}; border-radius: {size // 2}px;"
        f" border: 1px solid rgba(255,255,255,0.15);"
    )
    lbl.setToolTip(c)
    return lbl


# ── Colour math helpers (reused from v1 pattern) ──────────────────────────────

def _derive_palette_swatches(
    primary_hex: str, style: str,
    overrides: dict[str, str] | None = None,
    roles: tuple = ("primary", "armor_trim", "cloth", "shade", "highlight", "glow",
                    "weapons", "leather", "base"),
) -> list[str]:
    try:
        ph, ps, pl = hex_to_hsl(primary_hex)
        result = []
        for r in roles:
            if overrides and r in overrides:
                result.append(overrides[r])
            else:
                result.append(hsl_to_hex(*_target_hsl(r, ph, ps, pl, style)))
        return result
    except Exception:
        return [primary_hex] * len(roles)


def _apply_overrides_to_result(
    result: ChromaResult,
    overrides: dict[str, str],
    owned_paints: list,
) -> ChromaResult:
    for role, hex_override in overrides.items():
        rec = result.recommendations.get(role)
        if rec is None:
            continue
        scored: list[tuple[float, PaintMatch]] = []
        for p in owned_paints:
            color = getattr(p, "color", None)
            if not color or not color.startswith("#"):
                continue
            dist = color_distance(hex_override, color)
            qty  = getattr(p, "quantity", 1) or 1
            scored.append((dist, PaintMatch(
                paint_id   = p.id,
                paint_name = getattr(p, "name", "?"),
                brand      = getattr(p, "brand", ""),
                color_hex  = color,
                distance   = round(dist, 4),
                quantity   = qty,
                level      = getattr(p, "level", None),
                is_low     = qty <= 1,
            )))
        scored.sort(key=lambda x: x[0])
        best = scored[0][1] if scored and scored[0][0] < _GOOD_MATCH else None
        alts = [pm for _, pm in scored[1: _ALT_COUNT + 1]] if scored else []
        result.recommendations[role] = RoleRecommendation(
            role=role, icon=rec.icon, label=rec.label,
            target_hex=hex_override,
            best_match=best,
            alternatives=alts,
        )
    return result


# ── QPainter-based widgets (no stylesheet background — avoids palette bleed) ──

class _ColorSwatchWidget(QWidget):
    """Large colour preview rendered entirely with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color    = QColor("#888888")
        self._hex_text = "#888888"
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_color(self, hex_str: str):
        self._color    = QColor(hex_str)
        self._hex_text = hex_str.upper()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = self.palette().color(QPalette.Window)
        p.fillRect(self.rect(), bg)
        inner = self.rect().adjusted(2, 2, -2, -2)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(inner, 8, 8)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawRoundedRect(inner, 8, 8)
        r, g, b    = self._color.red(), self._color.green(), self._color.blue()
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        text_qc    = QColor("#111111") if brightness > 145 else QColor("#f0f0f0")
        p.setPen(text_qc)
        f = QFont(self.font())
        f.setPointSize(10)
        f.setBold(True)
        p.setFont(f)
        p.drawText(inner, Qt.AlignCenter, self._hex_text)
        p.end()


class _PaintChip(QWidget):
    """22×22 colour chip painted with QPainter."""

    def __init__(self, hex_str: str = "#888888", parent=None):
        super().__init__(parent)
        self._color = QColor(hex_str)
        self.setFixedSize(24, 24)

    def set_color(self, hex_str: str):
        self._color = QColor(hex_str)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = self.palette().color(QPalette.Window)
        p.fillRect(self.rect(), bg)
        inner = self.rect().adjusted(1, 1, -1, -1)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(inner, 4, 4)
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(inner, 4, 4)
        p.end()


class _PaletteBannerStrip(QWidget):
    """Seamless multi-colour banner strip rendered with QPainter."""

    def __init__(self, swatches: list[str], height: int = 20, parent=None):
        super().__init__(parent)
        self._swatches = [s for s in swatches if s] or ["#3a3a3a"]
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_swatches(self, swatches: list[str]):
        self._swatches = [s for s in swatches if s] or ["#3a3a3a"]
        self.update()

    def paintEvent(self, _event):
        p   = QPainter(self)
        n   = len(self._swatches)
        w   = self.width()
        h   = self.height()
        seg = w / n
        for i, hex_c in enumerate(self._swatches):
            x  = int(i * seg)
            x2 = int((i + 1) * seg) if i < n - 1 else w
            p.fillRect(x, 0, x2 - x, h, QColor(hex_c))
        p.end()


# ── Database layer (same table as v1 — preserves existing data) ───────────────

class _ChromaRepo:
    _CREATE_SQL = """
        CREATE TABLE IF NOT EXISTS chroma_schemes (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT    NOT NULL DEFAULT 'Untitled',
            primary_hex       TEXT    NOT NULL DEFAULT '#888888',
            style             TEXT    NOT NULL DEFAULT 'Complementary',
            personality       TEXT    NOT NULL DEFAULT '',
            notes             TEXT    NOT NULL DEFAULT '',
            game_system       TEXT    NOT NULL DEFAULT '',
            faction           TEXT    NOT NULL DEFAULT '',
            linked_project_id INTEGER,
            owned_count       INTEGER NOT NULL DEFAULT 0,
            total_roles       INTEGER NOT NULL DEFAULT 9,
            role_overrides    TEXT    NOT NULL DEFAULT '{}',
            palette_json      TEXT    NOT NULL DEFAULT '[]',
            created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """
    _MIGRATIONS = [
        ("personality",       "TEXT    NOT NULL DEFAULT ''"),
        ("game_system",       "TEXT    NOT NULL DEFAULT ''"),
        ("faction",           "TEXT    NOT NULL DEFAULT ''"),
        ("linked_project_id", "INTEGER"),
        ("owned_count",       "INTEGER NOT NULL DEFAULT 0"),
        ("total_roles",       "INTEGER NOT NULL DEFAULT 9"),
        ("role_overrides",    "TEXT    NOT NULL DEFAULT '{}'"),
        ("palette_json",      "TEXT    NOT NULL DEFAULT '[]'"),
    ]

    def __init__(self, db):
        self._db = db
        self._db.execute(self._CREATE_SQL)
        for col, defn in self._MIGRATIONS:
            try:
                self._db.execute(f"ALTER TABLE chroma_schemes ADD COLUMN {col} {defn}")
            except Exception:
                pass

    def get_all(self) -> list[dict]:
        rows = self._db.query(
            "SELECT id, name, primary_hex, style, personality, notes, "
            "game_system, faction, linked_project_id, owned_count, total_roles, "
            "role_overrides, palette_json, created_at "
            "FROM chroma_schemes ORDER BY id DESC"
        )
        return [dict(r) for r in rows]

    def get(self, scheme_id: int) -> Optional[dict]:
        rows = self._db.query(
            "SELECT id, name, primary_hex, style, personality, notes, "
            "game_system, faction, linked_project_id, owned_count, total_roles, "
            "role_overrides, palette_json, created_at "
            "FROM chroma_schemes WHERE id=?", (scheme_id,)
        )
        return dict(rows[0]) if rows else None

    def add(self, name: str, primary_hex: str, style: str,
            personality: str = "", notes: str = "",
            game_system: str = "", faction: str = "",
            linked_project_id: Optional[int] = None,
            owned_count: int = 0, total_roles: int = 9,
            role_overrides: Optional[dict] = None,
            palette_json: Optional[list] = None) -> dict:
        cur = self._db.execute(
            "INSERT INTO chroma_schemes "
            "(name, primary_hex, style, personality, notes, "
            " game_system, faction, linked_project_id, owned_count, total_roles, "
            " role_overrides, palette_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, primary_hex, style, personality, notes,
             game_system, faction, linked_project_id, owned_count, total_roles,
             json.dumps(role_overrides or {}),
             json.dumps(palette_json  or [])),
        )
        return self.get(cur.lastrowid)

    def update(self, scheme_id: int, **kwargs) -> Optional[dict]:
        allowed = {
            "name", "primary_hex", "style", "personality", "notes",
            "game_system", "faction", "linked_project_id",
            "owned_count", "total_roles", "role_overrides", "palette_json",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return self.get(scheme_id)
        if "role_overrides" in fields and isinstance(fields["role_overrides"], dict):
            fields["role_overrides"] = json.dumps(fields["role_overrides"])
        if "palette_json" in fields and isinstance(fields["palette_json"], list):
            fields["palette_json"] = json.dumps(fields["palette_json"])
        cols = ", ".join(f"{k}=?" for k in fields)
        self._db.execute(
            f"UPDATE chroma_schemes SET {cols} WHERE id=?",
            list(fields.values()) + [scheme_id],
        )
        return self.get(scheme_id)

    def delete(self, scheme_id: int):
        self._db.execute("DELETE FROM chroma_schemes WHERE id=?", (scheme_id,))


# ══════════════════════════════════════════════════════════════════════════════
#  Left-panel: _SavedSchemeCard
# ══════════════════════════════════════════════════════════════════════════════

class _SavedSchemeCard(QFrame):
    clicked = Signal(int)   # scheme_id

    def __init__(self, scheme: dict, swatches: list[str],
                 selected: bool = False, parent=None):
        super().__init__(parent)
        self._scheme_id = scheme["id"]
        self._build(scheme, swatches, selected)

    def _build(self, scheme: dict, swatches: list[str], selected: bool):
        self.setObjectName("chromaCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Palette banner strip (QPainter — no bleed)
        self._banner = _PaletteBannerStrip(swatches, height=18)
        root.addWidget(self._banner)

        # Content area (accent bar + text)
        body_outer = QHBoxLayout()
        body_outer.setContentsMargins(0, 0, 0, 0)
        body_outer.setSpacing(0)

        # 3px accent bar
        self._accent_bar = QFrame()
        self._accent_bar.setFixedWidth(3)
        body_outer.addWidget(self._accent_bar)

        body = QVBoxLayout()
        body.setContentsMargins(10, 8, 10, 8)
        body.setSpacing(3)

        # Name row
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_lbl = QLabel(scheme.get("name", "Untitled"))
        name_lbl.setStyleSheet(
            f"font-size: {_FS['base']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        name_row.addWidget(name_lbl, 1)

        # Coverage badge
        owned = scheme.get("owned_count", 0)
        total = scheme.get("total_roles", len(ROLES))
        if total > 0:
            all_done   = owned == total
            badge_bg   = _C["success_lo"] if all_done else _C["warning_lo"]
            badge_fg   = _C["success"]    if all_done else _C["warning"]
            badge_lbl  = QLabel(f"{owned}/{total}")
            badge_lbl.setAlignment(Qt.AlignCenter)
            badge_lbl.setStyleSheet(
                f"color: {badge_fg}; background: {badge_bg};"
                f" font-size: {_FS['xs']}; font-weight: 700;"
                f" border-radius: 8px; padding: 1px 6px; border: none;"
            )
            badge_lbl.setToolTip(f"{owned} of {total} roles matched")
            name_row.addWidget(badge_lbl)

        body.addLayout(name_row)

        # Style + personality row
        style      = scheme.get("style", "")
        pers       = scheme.get("personality", "")
        tags: list[str] = []
        if style:
            tags.append(style)
        if pers and pers in _PERSONALITY_META:
            _, _, icon = _PERSONALITY_META[pers]
            tags.append(f"{icon} {pers}")
        if tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(4)
            for tag in tags:
                t = QLabel(tag)
                t.setStyleSheet(
                    f"font-size: {_FS['xs']}; color: {_C['text_lo']};"
                    " background: transparent; border: none;"
                )
                tag_row.addWidget(t)
            tag_row.addStretch(1)
            body.addLayout(tag_row)

        # Faction / game system subtitle
        parts = [x for x in [scheme.get("faction", ""), scheme.get("game_system", "")] if x]
        if parts:
            sub = QLabel(" · ".join(parts))
            sub.setStyleSheet(
                f"font-size: {_FS['xs']}; color: {_C['text_dim']};"
                " background: transparent; border: none;"
            )
            body.addWidget(sub)

        body_outer.addLayout(body, 1)
        root.addLayout(body_outer)

        self._apply_style(selected)

    def _apply_style(self, selected: bool):
        if selected:
            self.setStyleSheet(f"""
                QFrame#chromaCard {{
                    background: {_C['accent_lo']};
                    border: 1px solid {_C['accent']};
                    border-radius: {_R['sm']};
                }}
            """)
            self._accent_bar.setStyleSheet(
                f"background: {_C['accent']}; border: none;"
                f" border-top-left-radius: {_R['sm']};"
                f" border-bottom-left-radius: {_R['sm']};"
            )
        else:
            self.setStyleSheet(f"""
                QFrame#chromaCard {{
                    background: {_C['bg_card']};
                    border: 1px solid {_C['border']};
                    border-radius: {_R['sm']};
                }}
                QFrame#chromaCard:hover {{
                    background: {_C['bg_raised']};
                    border-color: {_C['border_hi']};
                }}
            """)
            self._accent_bar.setStyleSheet(
                f"background: {_C['bg_hover']}; border: none;"
                f" border-top-left-radius: {_R['sm']};"
                f" border-bottom-left-radius: {_R['sm']};"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._scheme_id)
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  Results panel: _RoleCard
# ══════════════════════════════════════════════════════════════════════════════

class _RoleCard(QFrame):
    override_requested = Signal(str, str)   # role, current_hex

    def __init__(self, rec: RoleRecommendation, parent=None):
        super().__init__(parent)
        self.setObjectName("roleCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(f"""
            QFrame#roleCard {{
                background: {_C['bg_raised']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
            }}
        """)
        self._role = rec.role
        self._build(rec)

    @staticmethod
    def _quality_color(d: float) -> str:
        if d < 0.10: return _MATCH_COLORS["excellent"]
        if d < 0.20: return _MATCH_COLORS["good"]
        if d < 0.30: return _MATCH_COLORS["fair"]
        return _MATCH_COLORS["none"]

    def _build(self, rec: RoleRecommendation):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 9, 10, 9)
        lay.setSpacing(6)

        # ── Header row: icon · label · target swatch (clickable) ──────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        icon_lbl = QLabel(rec.icon)
        icon_lbl.setFixedWidth(18)
        icon_lbl.setStyleSheet(f"font-size: 14px; background: transparent; border: none;")
        hdr.addWidget(icon_lbl)

        role_lbl = QLabel(rec.label)
        role_lbl.setStyleSheet(
            f"font-size: {_FS['sm']}; font-weight: 700; color: {_C['text_mid']};"
            " background: transparent; border: none;"
        )
        hdr.addWidget(role_lbl, 1)

        # Clickable target swatch (opens override dialog)
        target_sw = _swatch_label(rec.target_hex, size=22)
        target_sw.setToolTip(f"Target: {rec.target_hex}\nClick to override")
        target_sw.setCursor(Qt.PointingHandCursor)
        target_sw.mousePressEvent = lambda _e, r=rec.role, h=rec.target_hex: \
            self.override_requested.emit(r, h)
        hdr.addWidget(target_sw)

        edit_hint = QLabel("✏")
        edit_hint.setStyleSheet(
            f"font-size: {_FS['xs']}; color: {_C['text_dim']};"
            " background: transparent; border: none;"
        )
        hdr.addWidget(edit_hint)
        lay.addLayout(hdr)

        # ── Separator ─────────────────────────────────────────────────────────
        lay.addWidget(_hline())

        # ── Best match ────────────────────────────────────────────────────────
        if rec.best_match:
            pm = rec.best_match
            match_row = QHBoxLayout()
            match_row.setSpacing(8)

            chip = _PaintChip(pm.color_hex)
            match_row.addWidget(chip)

            info = QVBoxLayout()
            info.setSpacing(1)
            paint_lbl = QLabel(pm.paint_name)
            paint_lbl.setStyleSheet(
                f"font-size: {_FS['sm']}; font-weight: 600; color: {_C['text_hi']};"
                " background: transparent; border: none;"
            )
            paint_lbl.setWordWrap(True)
            brand_lbl = QLabel(pm.brand)
            brand_lbl.setStyleSheet(
                f"font-size: {_FS['xs']}; color: {_C['text_lo']};"
                " background: transparent; border: none;"
            )
            info.addWidget(paint_lbl)
            info.addWidget(brand_lbl)
            match_row.addLayout(info, 1)

            pct   = int((1 - pm.distance) * 100)
            q_col = self._quality_color(pm.distance)
            pct_lbl = QLabel(f"{pct}%")
            pct_lbl.setStyleSheet(
                f"font-size: {_FS['sm']}; font-weight: 700; color: {q_col};"
                " background: transparent; border: none;"
            )
            pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            match_row.addWidget(pct_lbl)
            lay.addLayout(match_row)

            if pm.is_low:
                low_lbl = QLabel("⚠  Low stock")
                low_lbl.setStyleSheet(
                    f"font-size: {_FS['xs']}; color: {_C['warning']};"
                    " background: transparent; border: none;"
                )
                lay.addWidget(low_lbl)
        else:
            no_lbl = QLabel("No match in your collection")
            no_lbl.setStyleSheet(
                f"font-size: {_FS['sm']}; color: {_C['text_dim']}; font-style: italic;"
                " background: transparent; border: none;"
            )
            lay.addWidget(no_lbl)
            hint = QLabel(f"Target: {rec.target_hex}")
            hint.setStyleSheet(
                f"font-size: {_FS['xs']}; color: {_C['text_dim']};"
                " background: transparent; border: none;"
            )
            lay.addWidget(hint)

        # ── Alternatives ──────────────────────────────────────────────────────
        if rec.alternatives:
            alt_title = QLabel("Alternatives")
            alt_title.setStyleSheet(
                f"font-size: {_FS['xs']}; font-weight: 700; color: {_C['text_dim']};"
                " letter-spacing: 1px; background: transparent; border: none; margin-top: 2px;"
            )
            lay.addWidget(alt_title)
            for alt in rec.alternatives[:3]:
                alt_row = QHBoxLayout()
                alt_row.setSpacing(6)
                alt_row.addWidget(_swatch_label(alt.color_hex, size=10))
                alt_name = QLabel(f"{alt.paint_name}  ·  {alt.brand}")
                alt_name.setStyleSheet(
                    f"font-size: {_FS['xs']}; color: {_C['text_lo']};"
                    " background: transparent; border: none;"
                )
                alt_name.setWordWrap(True)
                alt_row.addWidget(alt_name, 1)
                pct_a = QLabel(f"{int((1-alt.distance)*100)}%")
                pct_a.setStyleSheet(
                    f"font-size: {_FS['xs']}; color: {self._quality_color(alt.distance)};"
                    " background: transparent; border: none;"
                )
                alt_row.addWidget(pct_a)
                lay.addLayout(alt_row)


# ══════════════════════════════════════════════════════════════════════════════
#  _MissingBanner
# ══════════════════════════════════════════════════════════════════════════════

class _MissingBanner(QFrame):
    def __init__(self, missing: list[RoleRecommendation], owned: int, total: int,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("missingBanner")

        if not missing:
            bg, fg = _C["success_lo"], _C["success"]
            icon   = "✓"
            text   = f"All {total} roles covered by your collection"
        else:
            bg, fg = _C["warning_lo"], _C["warning"]
            icon   = "◑"
            text   = f"{owned}/{total} roles covered — {len(missing)} need paint"

        self.setStyleSheet(f"""
            QFrame#missingBanner {{
                background: {bg};
                border: 1px solid {fg};
                border-radius: {_R['sm']};
            }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"font-size: 14px; color: {fg}; background: transparent; border: none;"
        )
        row.addWidget(icon_lbl)

        text_lbl = QLabel(text)
        text_lbl.setStyleSheet(
            f"font-size: {_FS['sm']}; font-weight: 600; color: {fg};"
            " background: transparent; border: none;"
        )
        row.addWidget(text_lbl, 1)

        if missing:
            for rec in missing[:6]:
                sw = _swatch_label(rec.target_hex, size=14)
                sw.setToolTip(f"{rec.label}: {rec.target_hex}")
                row.addWidget(sw)


# ══════════════════════════════════════════════════════════════════════════════
#  _PrimaryPickerDialog  (dark-themed, QPainter-based swatch — no bleed)
# ══════════════════════════════════════════════════════════════════════════════

class _PrimaryPickerDialog(QDialog):
    def __init__(self, current_hex: str, context, title: str = "Choose Color",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet(f"background: {_C['bg_base']}; color: {_C['text_hi']};")
        self._context      = context
        self._selected_hex = current_hex
        self._all_paints: list = []
        self._guard        = False
        self._build(current_hex)

    def _build(self, current_hex: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # ── Swatch ────────────────────────────────────────────────────────────
        self._swatch = _ColorSwatchWidget()
        self._swatch.set_color(current_hex)
        root.addWidget(self._swatch)

        # ── Hex input row ─────────────────────────────────────────────────────
        hex_row = QHBoxLayout()
        hex_row.setSpacing(8)
        hex_row.addWidget(_section_label("HEX"))
        self._hex_edit = QLineEdit(current_hex.upper())
        self._hex_edit.setMaxLength(7)
        self._hex_edit.setFixedWidth(100)
        self._hex_edit.setStyleSheet(_input_ss())
        self._hex_edit.editingFinished.connect(self._on_hex_committed)
        hex_row.addWidget(self._hex_edit)

        wheel_btn = QPushButton("Open Color Wheel…")
        wheel_btn.setStyleSheet(_secondary_btn_ss(small=True))
        wheel_btn.clicked.connect(self._open_color_wheel)
        hex_row.addWidget(wheel_btn)
        hex_row.addStretch(1)
        root.addLayout(hex_row)

        # ── HSL sliders ───────────────────────────────────────────────────────
        slider_frame = QFrame()
        slider_frame.setObjectName("sliderFrame")
        slider_frame.setStyleSheet(f"""
            QFrame#sliderFrame {{
                background: {_C['bg_card']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
            }}
        """)
        sf_lay = QVBoxLayout(slider_frame)
        sf_lay.setContentsMargins(12, 10, 12, 10)
        sf_lay.setSpacing(8)

        h0, s0, l0 = hex_to_hsl(current_hex)
        self._sl_h, self._lbl_h = self._make_slider(0, 360, int(round(h0)), "Hue")
        self._sl_s, self._lbl_s = self._make_slider(0, 100, int(round(s0)), "Saturation")
        self._sl_l, self._lbl_l = self._make_slider(0, 100, int(round(l0)), "Lightness")

        for name_str, sl, vl in [
            ("Hue",        self._sl_h, self._lbl_h),
            ("Saturation", self._sl_s, self._lbl_s),
            ("Lightness",  self._sl_l, self._lbl_l),
        ]:
            row = QHBoxLayout()
            row.setSpacing(8)
            n_lbl = QLabel(name_str)
            n_lbl.setFixedWidth(80)
            n_lbl.setStyleSheet(
                f"font-size: {_FS['sm']}; color: {_C['text_lo']};"
                " background: transparent; border: none;"
            )
            row.addWidget(n_lbl)
            row.addWidget(sl, 1)
            vl.setFixedWidth(30)
            vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            vl.setStyleSheet(
                f"font-size: {_FS['sm']}; font-weight: 600; color: {_C['text_mid']};"
                " background: transparent; border: none;"
            )
            row.addWidget(vl)
            sf_lay.addLayout(row)

        self._sl_h.valueChanged.connect(self._on_slider_changed)
        self._sl_s.valueChanged.connect(self._on_slider_changed)
        self._sl_l.valueChanged.connect(self._on_slider_changed)
        root.addWidget(slider_frame)

        # ── From owned paints ─────────────────────────────────────────────────
        root.addWidget(_section_label("FROM OWNED PAINTS"))
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._paint_search = QLineEdit()
        self._paint_search.setPlaceholderText("Filter by name or brand…")
        self._paint_search.setStyleSheet(_input_ss())
        self._paint_search.textChanged.connect(self._filter_paints)
        search_row.addWidget(self._paint_search, 1)
        root.addLayout(search_row)

        self._paint_list = QListWidget()
        self._paint_list.setFixedHeight(130)
        self._paint_list.setStyleSheet(f"""
            QListWidget {{
                background: {_C['bg_card']}; color: {_C['text_hi']};
                border: 1px solid {_C['border']}; border-radius: {_R['sm']};
                font-size: {_FS['base']}; outline: none;
            }}
            QListWidget::item {{
                padding: 4px 10px;
                border-bottom: 1px solid {_C['border_lo']};
            }}
            QListWidget::item:selected {{
                background: {_C['accent_lo']}; color: {_C['accent_text']};
            }}
            QListWidget::item:hover:!selected {{ background: {_C['bg_hover']}; }}
        """)
        self._paint_list.itemClicked.connect(self._on_paint_clicked)
        root.addWidget(self._paint_list)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("Apply Color")
        btn_box.button(QDialogButtonBox.Ok).setStyleSheet(_primary_btn_ss())
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet(_secondary_btn_ss())
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        QTimer.singleShot(0, self._load_paints)

    def _make_slider(self, lo: int, hi: int, val: int, _name: str):
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(val)
        sl.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {_C['bg_hover']}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px; height: 14px; margin: -5px 0;
                background: {_C['accent']}; border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {_C['accent_lo']}; border-radius: 2px;
            }}
        """)
        lbl = QLabel(str(val))
        return sl, lbl

    def _on_slider_changed(self):
        if self._guard:
            return
        h = self._sl_h.value()
        s = self._sl_s.value()
        l = self._sl_l.value()
        self._lbl_h.setText(str(h))
        self._lbl_s.setText(str(s))
        self._lbl_l.setText(str(l))
        new_hex = hsl_to_hex(float(h), float(s), float(l))
        self._selected_hex = new_hex
        self._swatch.set_color(new_hex)
        self._guard = True
        self._hex_edit.setText(new_hex.upper())
        self._guard = False

    def _on_hex_committed(self):
        if self._guard:
            return
        raw = self._hex_edit.text().strip()
        if not raw.startswith("#"):
            raw = "#" + raw
        raw = raw.lower()
        if len(raw) == 7:
            try:
                int(raw[1:], 16)
                self._apply_hex(raw)
                return
            except ValueError:
                pass
        self._hex_edit.setText(self._selected_hex.upper())

    def _apply_hex(self, hex_str: str):
        self._selected_hex = hex_str
        h, s, l = hex_to_hsl(hex_str)
        self._guard = True
        self._sl_h.setValue(int(round(h)))
        self._sl_s.setValue(int(round(s)))
        self._sl_l.setValue(int(round(l)))
        self._lbl_h.setText(str(int(round(h))))
        self._lbl_s.setText(str(int(round(s))))
        self._lbl_l.setText(str(int(round(l))))
        self._hex_edit.setText(hex_str.upper())
        self._guard = False
        self._swatch.set_color(hex_str)

    def _open_color_wheel(self):
        chosen = QColorDialog.getColor(
            QColor(self._selected_hex),
            None,
            "Choose Color",
            QColorDialog.DontUseNativeDialog,
        )
        if chosen.isValid():
            self._apply_hex(chosen.name().lower())

    def _load_paints(self):
        svc = self._context.services.try_get("paint_service")
        if not svc:
            self._paint_list.addItem("Paint Tracker not loaded")
            return
        try:
            self._all_paints = svc.get_all_paints()
        except Exception as e:
            log.error(f"[CHROMA V2] paint load: {e}")
        self._populate_paint_list(self._all_paints)

    def _populate_paint_list(self, paints: list):
        self._paint_list.clear()
        for p in paints:
            color = getattr(p, "color", None)
            if not color or not color.startswith("#"):
                continue
            label = f"  {p.name}  —  {p.brand}"
            pt    = getattr(p, "paint_type", "")
            if pt:
                label += f"  [{pt}]"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, color)
            qc     = QColor(color)
            bright = (qc.red() * 299 + qc.green() * 587 + qc.blue() * 114) / 1000
            item.setBackground(qc)
            item.setForeground(QColor("#000" if bright > 128 else "#fff"))
            self._paint_list.addItem(item)

    def _filter_paints(self, text: str):
        needle = text.strip().lower()
        self._populate_paint_list([
            p for p in self._all_paints
            if not needle
            or needle in p.name.lower()
            or needle in getattr(p, "brand", "").lower()
        ])

    def _on_paint_clicked(self, item: QListWidgetItem):
        color = item.data(Qt.UserRole)
        if color:
            self._apply_hex(color)

    @property
    def selected_hex(self) -> str:
        return self._selected_hex


# ══════════════════════════════════════════════════════════════════════════════
#  _SaveDialog
# ══════════════════════════════════════════════════════════════════════════════

class _SaveDialog(QDialog):
    def __init__(self, parent, primary_hex: str, style: str,
                 existing: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Update Palette" if existing else "Save Palette")
        self.setMinimumWidth(440)
        self.setModal(True)
        self.setStyleSheet(f"background: {_C['bg_base']}; color: {_C['text_hi']};")
        self._build(primary_hex, style, existing or {})

    def _build(self, primary_hex: str, style: str, ex: dict):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 18, 20, 18)

        lay.addWidget(_section_label("PALETTE NAME"))
        self._name = QLineEdit(ex.get("name", f"{style} Palette"))
        self._name.setStyleSheet(_input_ss())
        lay.addWidget(self._name)

        lay.addWidget(_section_label("PERSONALITY"))
        self._pers = QComboBox()
        self._pers.setMinimumWidth(145)
        self._pers.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._pers.setStyleSheet(_input_ss())
        for p in PERSONALITIES:
            if p == "":
                self._pers.addItem("— None —", "")
            else:
                bg, fg, icon = _PERSONALITY_META[p]
                self._pers.addItem(f"{icon}  {p}", p)
        cur_p = ex.get("personality", "")
        idx   = next((i for i in range(self._pers.count())
                      if self._pers.itemData(i) == cur_p), 0)
        self._pers.setCurrentIndex(idx)
        lay.addWidget(self._pers)

        row = QHBoxLayout()
        row.setSpacing(10)

        gs_col = QVBoxLayout()
        gs_col.addWidget(_section_label("GAME SYSTEM"))
        self._gs = QComboBox()
        self._gs.setEditable(True)
        self._gs.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._gs.addItems(COMMON_GAME_SYSTEMS)
        self._gs.setStyleSheet(_input_ss())
        gs_text = ex.get("game_system", "")
        idx = self._gs.findText(gs_text)
        if idx >= 0:
            self._gs.setCurrentIndex(idx)
        else:
            self._gs.setCurrentText(gs_text)
        gs_col.addWidget(self._gs)
        row.addLayout(gs_col, 1)

        fac_col = QVBoxLayout()
        fac_col.addWidget(_section_label("FACTION / ARMY"))
        self._faction = QLineEdit(ex.get("faction", ""))
        self._faction.setPlaceholderText("e.g. Dark Angels")
        self._faction.setStyleSheet(_input_ss())
        fac_col.addWidget(self._faction)
        row.addLayout(fac_col, 1)
        lay.addLayout(row)

        lay.addWidget(_section_label("NOTES  (optional)"))
        self._notes = QLineEdit(ex.get("notes", ""))
        self._notes.setPlaceholderText("Any extra context…")
        self._notes.setStyleSheet(_input_ss())
        lay.addWidget(self._notes)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setStyleSheet(_primary_btn_ss())
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet(_secondary_btn_ss())
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def get_values(self) -> dict:
        return {
            "name":        self._name.text().strip() or "Untitled",
            "personality": self._pers.currentData() or "",
            "game_system": self._gs.currentText().strip(),
            "faction":     self._faction.text().strip(),
            "notes":       self._notes.text().strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  _ProjectPickerDialog
# ══════════════════════════════════════════════════════════════════════════════

class _ProjectPickerDialog(QDialog):
    def __init__(self, projects: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link Palette to Project")
        self.setMinimumWidth(380)
        self.setModal(True)
        self.setStyleSheet(f"background: {_C['bg_base']}; color: {_C['text_hi']};")
        self.selected_id: Optional[int] = None
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.addWidget(_section_label("SELECT PROJECT"))
        self._list = QListWidget()
        self._list.setMinimumHeight(200)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: {_C['bg_card']}; color: {_C['text_hi']};
                border: 1px solid {_C['border']}; border-radius: {_R['sm']};
                font-size: {_FS['base']}; outline: none;
            }}
            QListWidget::item {{
                padding: 7px 12px;
                border-bottom: 1px solid {_C['border_lo']};
            }}
            QListWidget::item:selected {{
                background: {_C['accent_lo']}; color: {_C['accent_text']};
            }}
            QListWidget::item:hover:!selected {{ background: {_C['bg_hover']}; }}
        """)
        for p in projects:
            item = QListWidgetItem(getattr(p, "name", str(p)))
            item.setData(Qt.UserRole, p.id)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)
        lay.addWidget(self._list)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("Link to Project")
        btn_box.button(QDialogButtonBox.Ok).setStyleSheet(_primary_btn_ss())
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet(_secondary_btn_ss())
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _on_accept(self):
        item = self._list.currentItem()
        if item:
            self.selected_id = item.data(Qt.UserRole)
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  _ColorPickerBtn  (shows current hex as a painted button)
# ══════════════════════════════════════════════════════════════════════════════

class _ColorPickerBtn(QPushButton):
    """Shows the chosen colour in a painted button; opens _PrimaryPickerDialog."""

    def __init__(self, initial_hex: str = "#8b1a1a", context=None, parent=None):
        super().__init__(parent)
        self._hex     = initial_hex
        self._context = context
        self.setFixedSize(72, 34)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._open)
        self._refresh()

    def _refresh(self):
        c      = self._hex
        bright = QColor(c).lightness()
        fg     = "#000000" if bright > 128 else "#ffffff"
        self.setText(c.upper())
        self.setStyleSheet(
            f"QPushButton {{ background: {c}; color: {fg};"
            f" border: 1px solid rgba(255,255,255,0.2);"
            f" border-radius: {_R['sm']}; font-size: {_FS['xs']};"
            f" font-weight: 700; padding: 0; }}"
            f"QPushButton:hover {{ border-color: rgba(255,255,255,0.45); }}"
        )

    def _open(self):
        top = self.window()
        dlg = _PrimaryPickerDialog(self._hex, self._context,
                                   title="Choose Primary Color", parent=top)
        if dlg.exec() == QDialog.Accepted:
            self._hex = dlg.selected_hex
            self._refresh()

    def get_hex(self) -> str:
        return self._hex

    def set_hex(self, hex_str: str):
        self._hex = hex_str
        self._refresh()


# ══════════════════════════════════════════════════════════════════════════════
#  _RoleColorRow  — one role inside the manual designer
# ══════════════════════════════════════════════════════════════════════════════

class _RoleColorRow(QFrame):
    color_changed = Signal(str, str)   # role, new_hex

    def __init__(self, role: str, initial_hex: str, context, parent=None):
        super().__init__(parent)
        self._role    = role
        self._hex     = initial_hex
        self._context = context
        self.setObjectName("roleColorRow")
        self.setStyleSheet(f"""
            QFrame#roleColorRow {{
                background: {_C['bg_raised']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
            }}
        """)
        self._build()

    def _build(self):
        icon, label = ROLE_META.get(self._role, ("◉", self._role))
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(18)
        icon_lbl.setStyleSheet(
            f"font-size: 13px; background: transparent; border: none;"
        )
        row.addWidget(icon_lbl)

        name_lbl = QLabel(label)
        name_lbl.setFixedWidth(90)
        name_lbl.setStyleSheet(
            f"font-size: {_FS['sm']}; font-weight: 600; color: {_C['text_mid']};"
            " background: transparent; border: none;"
        )
        row.addWidget(name_lbl)

        # Colour button
        self._color_btn = _ColorPickerBtn(self._hex, context=self._context)
        self._color_btn.clicked.disconnect()   # disconnect default — we handle it
        self._color_btn.clicked.connect(self._open_picker)
        row.addWidget(self._color_btn)

        # Hex label
        self._hex_lbl = QLabel(self._hex.upper())
        self._hex_lbl.setFixedWidth(60)
        self._hex_lbl.setStyleSheet(
            f"font-size: {_FS['xs']}; color: {_C['text_lo']};"
            " background: transparent; border: none; font-family: monospace;"
        )
        row.addWidget(self._hex_lbl)

        row.addStretch(1)

        # Paint match chip + name (updated externally via set_match)
        self._chip = _PaintChip("#888888")
        row.addWidget(self._chip)

        self._match_lbl = QLabel("No paint matched")
        self._match_lbl.setStyleSheet(
            f"font-size: {_FS['xs']}; color: {_C['text_dim']}; font-style: italic;"
            " background: transparent; border: none;"
        )
        self._match_lbl.setMinimumWidth(130)
        row.addWidget(self._match_lbl)

    def _open_picker(self):
        top = self.window()
        dlg = _PrimaryPickerDialog(
            self._hex, self._context,
            title=f"Choose Color — {ROLE_META.get(self._role, ('', self._role))[1]}",
            parent=top,
        )
        if dlg.exec() == QDialog.Accepted:
            self._hex = dlg.selected_hex
            self._color_btn.set_hex(self._hex)
            self._hex_lbl.setText(self._hex.upper())
            self.color_changed.emit(self._role, self._hex)

    def set_match(self, paint_name: str, brand: str, color_hex: str):
        self._chip.set_color(color_hex)
        label = f"{paint_name}  ·  {brand}" if brand else paint_name
        self._match_lbl.setText(label)
        self._match_lbl.setStyleSheet(
            f"font-size: {_FS['xs']}; color: {_C['text_mid']};"
            " background: transparent; border: none;"
        )

    def clear_match(self):
        self._chip.set_color("#888888")
        self._match_lbl.setText("No paint matched")
        self._match_lbl.setStyleSheet(
            f"font-size: {_FS['xs']}; color: {_C['text_dim']}; font-style: italic;"
            " background: transparent; border: none;"
        )

    def get_hex(self) -> str:
        return self._hex


# ══════════════════════════════════════════════════════════════════════════════
#  _ManualPaletteDialog  — hand-design a palette role by role
# ══════════════════════════════════════════════════════════════════════════════

class _ManualPaletteDialog(QDialog):
    """
    Lets the user build a palette entirely by hand — one colour per role,
    with live paint-collection matching shown inline.

    Returns via get_result():
        {
          "name": str, "game_system": str, "faction": str,
          "personality": str, "notes": str,
          "role_hexes": dict[role, hex],
        }
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Design New Palette")
        self.setMinimumWidth(680)
        self.setModal(True)
        self.setStyleSheet(f"background: {_C['bg_base']}; color: {_C['text_hi']};")
        self._context = context
        self._paints: list = []
        # Sensible defaults per role
        self._role_rows: dict[str, _RoleColorRow] = {}
        self._build()
        QTimer.singleShot(0, self._load_paints)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # ── Title ──────────────────────────────────────────────────────────────
        title_lbl = QLabel("Design Your Palette")
        title_lbl.setStyleSheet(
            f"font-size: {_FS['xl']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        root.addWidget(title_lbl)

        sub_lbl = QLabel(
            "Pick a colour for each role. Your paint collection is matched live."
        )
        sub_lbl.setStyleSheet(
            f"font-size: {_FS['sm']}; color: {_C['text_lo']};"
            " background: transparent; border: none;"
        )
        root.addWidget(sub_lbl)

        root.addWidget(_hline())

        # ── Metadata row ───────────────────────────────────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)

        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_col.addWidget(_section_label("PALETTE NAME"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Blood Angels Veterans")
        self._name.setStyleSheet(_input_ss())
        name_col.addWidget(self._name)
        meta_row.addLayout(name_col, 2)

        gs_col = QVBoxLayout()
        gs_col.setSpacing(4)
        gs_col.addWidget(_section_label("GAME SYSTEM"))
        self._gs = QComboBox()
        self._gs.setEditable(True)
        self._gs.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._gs.addItems(COMMON_GAME_SYSTEMS)
        self._gs.setStyleSheet(_input_ss())
        gs_col.addWidget(self._gs)
        meta_row.addLayout(gs_col, 2)

        fac_col = QVBoxLayout()
        fac_col.setSpacing(4)
        fac_col.addWidget(_section_label("FACTION"))
        self._faction = QLineEdit()
        self._faction.setPlaceholderText("e.g. Blood Angels")
        self._faction.setStyleSheet(_input_ss())
        fac_col.addWidget(self._faction)
        meta_row.addLayout(fac_col, 2)

        pers_col = QVBoxLayout()
        pers_col.setSpacing(4)
        pers_col.addWidget(_section_label("PERSONALITY"))
        self._pers = QComboBox()
        self._pers.setMinimumWidth(145)
        self._pers.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._pers.setStyleSheet(_input_ss())
        for p in PERSONALITIES:
            if p == "":
                self._pers.addItem("— None —", "")
            else:
                _, _, icon = _PERSONALITY_META[p]
                self._pers.addItem(f"{icon}  {p}", p)
        pers_col.addWidget(self._pers)
        meta_row.addLayout(pers_col, 2)

        root.addLayout(meta_row)

        root.addWidget(_hline())

        # ── Role rows (scrollable, 1 column) ──────────────────────────────────
        root.addWidget(_section_label("ROLE COLOURS  —  click any swatch to change"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(400)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {_C['border']};"
            f" border-radius: {_R['sm']}; background: {_C['bg_base']}; }}"
        )

        host = QWidget()
        host.setStyleSheet(f"background: {_C['bg_base']};")
        vlay = QVBoxLayout(host)
        vlay.setContentsMargins(8, 8, 8, 8)
        vlay.setSpacing(5)

        # Default starting colours — one sensible hex per role
        defaults = {
            "primary":    "#8b1a1a",
            "armor_trim": "#888888",
            "cloth":      "#2a4a7a",
            "weapons":    "#4a4a4a",
            "leather":    "#5a3a1a",
            "glow":       "#00aaff",
            "shade":      "#1a0808",
            "highlight":  "#e8c8b0",
            "base":       "#5a4a2a",
        }
        for role in ROLES:
            row_widget = _RoleColorRow(
                role, defaults.get(role, "#888888"), self._context
            )
            row_widget.color_changed.connect(self._on_role_color_changed)
            vlay.addWidget(row_widget)
            self._role_rows[role] = row_widget

        vlay.addStretch()
        scroll.setWidget(host)
        root.addWidget(scroll)

        # ── Buttons ────────────────────────────────────────────────────────────
        root.addWidget(_hline())

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._match_status = QLabel("")
        self._match_status.setStyleSheet(
            f"font-size: {_FS['xs']}; color: {_C['text_dim']};"
            " background: transparent; border: none;"
        )
        btn_row.addWidget(self._match_status, 1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_secondary_btn_ss())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Create Palette")
        save_btn.setStyleSheet(_primary_btn_ss())
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        root.addLayout(btn_row)

    # ── Paint loading & matching ──────────────────────────────────────────────

    def _load_paints(self):
        svc = self._context.services.try_get("paint_service")
        if svc:
            try:
                self._paints = svc.get_all_paints()
            except Exception as e:
                log.error(f"[CHROMA V2 MANUAL] paint load: {e}")
        # Match all roles with initial colours
        for role, row in self._role_rows.items():
            self._match_role(role, row.get_hex())
        self._update_match_status()

    def _match_role(self, role: str, hex_str: str):
        row = self._role_rows.get(role)
        if row is None:
            return
        if not self._paints:
            row.clear_match()
            return
        scored = []
        for p in self._paints:
            c = getattr(p, "color", None)
            if not c or not c.startswith("#"):
                continue
            scored.append((color_distance(hex_str, c), p))
        if not scored:
            row.clear_match()
            return
        scored.sort(key=lambda x: x[0])
        best_dist, best_p = scored[0]
        if best_dist < _GOOD_MATCH:
            row.set_match(best_p.name, getattr(best_p, "brand", ""),
                          getattr(best_p, "color", "#888888"))
        else:
            row.clear_match()

    def _on_role_color_changed(self, role: str, hex_str: str):
        self._match_role(role, hex_str)
        self._update_match_status()

    def _update_match_status(self):
        matched = sum(
            1 for role, row in self._role_rows.items()
            if row._match_lbl.text() != "No paint matched"
        )
        total = len(ROLES)
        self._match_status.setText(
            f"{matched}/{total} roles matched to your collection"
        )

    # ── Accept ────────────────────────────────────────────────────────────────

    def _on_save(self):
        if not self._name.text().strip():
            self._name.setFocus()
            self._name.setStyleSheet(
                _input_ss() +
                f" QLineEdit {{ border-color: {_C['danger']}; }}"
            )
            return
        self.accept()

    # ── Result ────────────────────────────────────────────────────────────────

    def get_result(self) -> dict:
        return {
            "name":        self._name.text().strip(),
            "game_system": self._gs.currentText().strip(),
            "faction":     self._faction.text().strip(),
            "personality": self._pers.currentData() or "",
            "notes":       "",
            "role_hexes":  {role: row.get_hex()
                            for role, row in self._role_rows.items()},
        }


# ══════════════════════════════════════════════════════════════════════════════
#  ChromaCodexV2UI  — main widget
# ══════════════════════════════════════════════════════════════════════════════

class ChromaCodexV2UI(QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._context              = context
        self._repo: Optional[_ChromaRepo] = None
        self._current_result: Optional[ChromaResult] = None
        self._current_scheme_id: Optional[int] = None
        self._role_overrides: dict[str, str] = {}
        self._project_lookup: dict[int, str] = {}
        self._scheme_cards: dict[int, _SavedSchemeCard] = {}
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status)

        self._init_repo()
        self._build()
        QTimer.singleShot(0, self._initial_load)

    def _init_repo(self):
        db = self._context.services.try_get("db")
        if db:
            try:
                self._repo = _ChromaRepo(db)
            except Exception as e:
                log.error(f"[CHROMA V2] Repo init: {e}")

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.setStyleSheet(f"""
            QScrollBar:vertical {{
                background: {_C['bg_base']}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {_C['bg_active']}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {_C['border_hi']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: {_C['bg_base']}; height: 6px; border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {_C['bg_active']}; border-radius: 3px; min-width: 20px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

        root.addWidget(self._build_header())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {_C['border_lo']}; }}"
        )
        splitter.addWidget(self._build_left_pane())
        splitter.addWidget(self._build_right_pane())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self._splitter = splitter
        root.addWidget(splitter, 1)

        self._status_bar = QLabel("")
        self._status_bar.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['sm']};"
            f" padding: 4px 16px; border-top: 1px solid {_C['border_lo']};"
            f" background: {_C['bg_base']};"
        )
        root.addWidget(self._status_bar)

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("ccHeader")
        bar.setStyleSheet(f"""
            QFrame#ccHeader {{
                background: {_C['bg_base']};
                border-bottom: 1px solid {_C['border']};
            }}
        """)
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 14, 20, 14)
        row.setSpacing(12)

        dot = QFrame()
        dot.setFixedSize(4, 28)
        dot.setStyleSheet(f"background: {_C['gold']}; border-radius: 2px;")
        row.addWidget(dot)

        title = QLabel("Chroma Codex")
        title.setStyleSheet(
            f"font-size: {_FS['xl']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        row.addWidget(title)

        self._header_count = QLabel("")
        self._header_count.setStyleSheet(
            f"font-size: {_FS['sm']}; color: {_C['text_lo']};"
            " background: transparent; border: none;"
        )
        row.addWidget(self._header_count)
        row.addStretch(1)

        self._new_btn = QPushButton("+ New Palette")
        self._new_btn.setFixedHeight(32)
        self._new_btn.setStyleSheet(_primary_btn_ss(small=True))
        self._new_btn.clicked.connect(self._on_new_palette_clicked)
        row.addWidget(self._new_btn)

        return bar

    def _build_left_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("ccLeftPane")
        pane.setMinimumWidth(260)
        pane.setMaximumWidth(420)
        pane.setStyleSheet(
            f"QWidget#ccLeftPane {{ background: {_C['bg_base']}; border: none; }}"
        )
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(12, 12, 8, 12)
        lay.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search saved palettes…")
        self._search.setStyleSheet(_input_ss())
        self._search.textChanged.connect(self._on_search_changed)
        lay.addWidget(self._search)

        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {_C['bg_base']}; }}"
        )

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet(f"background: {_C['bg_base']};")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._list_empty = QLabel("No palettes saved yet.\n\nGenerate one and click  💾 Save.")
        self._list_empty.setAlignment(Qt.AlignCenter)
        self._list_empty.setWordWrap(True)
        self._list_empty.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['sm']}; font-style: italic;"
            " background: transparent; padding: 24px 12px;"
        )

        self._list_scroll.setWidget(self._list_widget)
        lay.addWidget(self._list_scroll, 1)

        self._del_btn = QPushButton("Delete Selected")
        self._del_btn.setStyleSheet(_danger_btn_ss(small=True))
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._on_delete_saved)
        lay.addWidget(self._del_btn, 0, Qt.AlignRight)

        return pane

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("ccRightPane")
        pane.setStyleSheet(
            f"QWidget#ccRightPane {{ background: {_C['bg_base']}; border: none; }}"
        )
        outer = QVBoxLayout(pane)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_generator_bar())
        outer.addWidget(_hline())

        # Results area (scrollable)
        self._results_scroll = QScrollArea()
        self._results_scroll.setWidgetResizable(True)
        self._results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._results_scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {_C['bg_base']}; }}"
        )

        self._results_host = QWidget()
        self._results_host.setStyleSheet(f"background: {_C['bg_base']};")
        self._results_lay = QVBoxLayout(self._results_host)
        self._results_lay.setContentsMargins(16, 16, 16, 24)
        self._results_lay.setSpacing(12)

        # Placeholder (shown before first generate)
        self._placeholder = QLabel(
            "Pick a primary colour and click  ⚡ Generate  to build your palette."
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['lg']};"
            " padding: 80px 40px; background: transparent;"
        )
        self._results_lay.addWidget(self._placeholder)

        # Palette banner (hidden until generate)
        self._banner_strip  = _PaletteBannerStrip([], height=28)
        self._banner_strip.setVisible(False)
        self._results_lay.addWidget(self._banner_strip)

        # Save + link action row (hidden until result exists)
        self._action_row_widget = self._build_action_row()
        self._action_row_widget.setVisible(False)
        self._results_lay.addWidget(self._action_row_widget)

        # Role cards grid (hidden until generate)
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_lay = QGridLayout(self._grid_widget)
        self._grid_lay.setSpacing(8)
        self._grid_widget.setVisible(False)
        self._results_lay.addWidget(self._grid_widget)

        # Missing banner container (stable slot in layout)
        self._missing_container = QWidget()
        self._missing_container.setStyleSheet("background: transparent;")
        self._missing_vlay = QVBoxLayout(self._missing_container)
        self._missing_vlay.setContentsMargins(0, 0, 0, 0)
        self._missing_vlay.setSpacing(0)
        self._missing_container.setVisible(False)
        self._results_lay.addWidget(self._missing_container)

        self._results_lay.addStretch()
        self._results_scroll.setWidget(self._results_host)
        outer.addWidget(self._results_scroll, 1)

        return pane

    def _build_generator_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("genBar")
        bar.setStyleSheet(f"""
            QFrame#genBar {{
                background: {_C['bg_card']};
                border-bottom: 1px solid {_C['border']};
            }}
        """)
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        # Primary color
        ctrl.addWidget(_section_label("COLOR"))
        self._color_btn = _ColorPickerBtn("#8b1a1a", context=self._context)
        ctrl.addWidget(self._color_btn)

        self._hex_input = QLineEdit("#8B1A1A")
        self._hex_input.setFixedWidth(86)
        self._hex_input.setMaxLength(7)
        self._hex_input.setPlaceholderText("#RRGGBB")
        self._hex_input.setStyleSheet(_input_ss())
        self._hex_input.editingFinished.connect(self._on_hex_input_changed)
        ctrl.addWidget(self._hex_input)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFixedWidth(1)
        sep1.setStyleSheet(f"background: {_C['border']}; border: none;")
        ctrl.addWidget(sep1)

        # Style
        ctrl.addWidget(_section_label("STYLE"))
        self._style_combo = QComboBox()
        self._style_combo.setMinimumWidth(180)   # fits "Accessible Contrast"
        self._style_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._style_combo.setStyleSheet(_input_ss())
        for s in SCHEME_STYLES:
            self._style_combo.addItem(s, s)
        self._style_combo.adjustSize()
        self._style_combo.currentIndexChanged.connect(self._on_style_changed)
        ctrl.addWidget(self._style_combo)

        # Personality
        ctrl.addWidget(_section_label("PERSONALITY"))
        self._pers_combo = QComboBox()
        self._pers_combo.setMinimumWidth(145)    # fits emoji + longest name
        self._pers_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._pers_combo.setStyleSheet(_input_ss())
        for p in PERSONALITIES:
            if p == "":
                self._pers_combo.addItem("— None —", "")
            else:
                _, _, icon = _PERSONALITY_META[p]
                self._pers_combo.addItem(f"{icon}  {p}", p)
        ctrl.addWidget(self._pers_combo)

        ctrl.addStretch(1)

        self._gen_btn = QPushButton("⚡  Generate")
        self._gen_btn.setFixedHeight(34)
        self._gen_btn.setMinimumWidth(110)
        self._gen_btn.setStyleSheet(_primary_btn_ss())
        self._gen_btn.clicked.connect(self._on_generate)
        ctrl.addWidget(self._gen_btn)

        outer.addLayout(ctrl)

        # Style hint
        self._style_hint = QLabel("")
        self._style_hint.setStyleSheet(
            f"font-size: {_FS['xs']}; color: {_C['text_dim']};"
            " background: transparent; border: none;"
        )
        outer.addWidget(self._style_hint)
        self._update_style_hint()

        return bar

    def _build_action_row(self) -> QWidget:
        w = QFrame()
        w.setObjectName("actionRow")
        w.setStyleSheet(f"""
            QFrame#actionRow {{
                background: {_C['bg_card']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
            }}
        """)
        row = QHBoxLayout(w)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)

        self._coverage_lbl = QLabel("")
        self._coverage_lbl.setStyleSheet(
            f"font-size: {_FS['sm']}; font-weight: 600; color: {_C['text_mid']};"
            " background: transparent; border: none;"
        )
        row.addWidget(self._coverage_lbl, 1)

        self._save_btn = QPushButton("💾  Save Palette")
        self._save_btn.setFixedHeight(30)
        self._save_btn.setStyleSheet(_secondary_btn_ss(small=True))
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        row.addWidget(self._save_btn)

        self._link_btn = QPushButton("🔗  Link to Project")
        self._link_btn.setFixedHeight(30)
        self._link_btn.setStyleSheet(_secondary_btn_ss(small=True))
        self._link_btn.setEnabled(False)
        self._link_btn.clicked.connect(self._on_link_to_project)
        row.addWidget(self._link_btn)

        return w

    # ── showEvent: deferred splitter sizing ──────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_splitter_set", False):
            QTimer.singleShot(0, self._set_splitter)

    def _set_splitter(self):
        if getattr(self, "_splitter_set", False):
            return
        w = self._splitter.width()
        if w > 400:
            self._splitter.setSizes([300, w - 300])
            self._splitter_set = True

    # ── Public API ────────────────────────────────────────────────────────────

    def on_paints_changed(self):
        """Called when paint collection changes — regenerate if a result is loaded."""
        if self._current_result:
            primary = self._current_result.primary_hex
            style   = self._current_result.style
            self._run_generate(primary, style)

    # ── Initial load ──────────────────────────────────────────────────────────

    def _initial_load(self):
        self._refresh_project_lookup()
        self._reload_saved_list()

    def _refresh_project_lookup(self):
        svc = self._context.services.try_get("project_service")
        if not svc:
            return
        try:
            self._project_lookup = {p.id: p.name for p in svc.get_all_projects()}
        except Exception:
            pass

    # ── Left-pane list ────────────────────────────────────────────────────────

    def _reload_saved_list(self, restore_id: Optional[int] = None):
        if not self._repo:
            self._list_empty.setText("Database not available.")
            self._list_layout.insertWidget(0, self._list_empty)
            self._list_empty.setVisible(True)
            self._header_count.setText("")
            return

        schemes = self._repo.get_all()
        needle  = self._search.text().strip().lower()
        if needle:
            schemes = [s for s in schemes if any(
                needle in s.get(k, "").lower()
                for k in ("name", "game_system", "faction", "personality")
            )]

        n = len(schemes)
        self._header_count.setText(
            f"{n} palette{'s' if n != 1 else ''}"
        )

        # Clear existing cards
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._scheme_cards.clear()

        if not schemes:
            self._list_layout.insertWidget(0, self._list_empty)
            self._list_empty.setVisible(True)
            self._del_btn.setEnabled(False)
            return

        self._list_empty.setVisible(False)

        target_id = restore_id if restore_id is not None else self._current_scheme_id

        for s in schemes:
            swatches = self._build_swatches_for(s)
            selected = (s["id"] == target_id)
            card     = _SavedSchemeCard(s, swatches, selected=selected)
            card.clicked.connect(self._on_saved_card_clicked)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
            self._scheme_cards[s["id"]] = card

        has_sel = target_id in self._scheme_cards
        self._del_btn.setEnabled(has_sel and self._repo is not None)

    def _build_swatches_for(self, s: dict) -> list[str]:
        stored: list[str] = []
        try:
            stored = json.loads(s.get("palette_json") or "[]")
        except Exception:
            pass
        if stored and all(c.startswith("#") for c in stored):
            return stored
        try:
            overrides = json.loads(s.get("role_overrides") or "{}")
        except Exception:
            overrides = {}
        return _derive_palette_swatches(s["primary_hex"], s["style"], overrides=overrides)

    def _on_search_changed(self, _=None):
        self._reload_saved_list()

    def _on_saved_card_clicked(self, scheme_id: int):
        if not self._repo:
            return
        data = self._repo.get(scheme_id)
        if not data:
            return

        # Update selection visual
        for sid, card in self._scheme_cards.items():
            card._apply_style(sid == scheme_id)
        self._current_scheme_id = scheme_id
        self._del_btn.setEnabled(True)

        primary_hex = data.get("primary_hex", "#888888")
        style       = data.get("style", SCHEME_STYLES[0])
        personality = data.get("personality", "")

        try:
            self._role_overrides = json.loads(data.get("role_overrides") or "{}")
        except Exception:
            self._role_overrides = {}

        self._color_btn.set_hex(primary_hex)
        self._hex_input.setText(primary_hex.upper())

        idx = self._style_combo.findData(style)
        if idx >= 0:
            self._style_combo.blockSignals(True)
            self._style_combo.setCurrentIndex(idx)
            self._style_combo.blockSignals(False)

        p_idx = next(
            (i for i in range(self._pers_combo.count())
             if self._pers_combo.itemData(i) == personality), 0
        )
        self._pers_combo.blockSignals(True)
        self._pers_combo.setCurrentIndex(p_idx)
        self._pers_combo.blockSignals(False)

        self._update_style_hint()
        self._run_generate(primary_hex, style)

    def _on_delete_saved(self):
        sid = self._current_scheme_id
        if not sid or not self._repo:
            return
        data = self._repo.get(sid)
        name = data.get("name", "this palette") if data else "this palette"
        if QMessageBox.question(
            self, "Delete Palette",
            f"Delete '{name}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            self._repo.delete(sid)
            self._current_scheme_id = None
            self._role_overrides.clear()
            self._del_btn.setEnabled(False)
            self._show_results_placeholder()
            self._reload_saved_list()
            self._show_success("Palette deleted.")
        except Exception as e:
            self._show_error(str(e))

    # ── Generator controls ────────────────────────────────────────────────────

    def _on_new_palette_clicked(self):
        """Open the manual palette designer dialog."""
        dlg = _ManualPaletteDialog(self._context, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        result_data = dlg.get_result()
        role_hexes  = result_data.pop("role_hexes")

        # Build overrides for all 9 roles
        self._role_overrides = dict(role_hexes)

        # Use the "primary" role hex as the primary colour
        primary_hex = role_hexes.get("primary", "#888888")
        self._color_btn.set_hex(primary_hex)
        self._hex_input.setText(primary_hex.upper())

        # Point the style combo at "Custom Manual" if available,
        # otherwise leave it on whatever was selected
        for i in range(self._style_combo.count()):
            if self._style_combo.itemData(i) == "Custom Manual":
                self._style_combo.blockSignals(True)
                self._style_combo.setCurrentIndex(i)
                self._style_combo.blockSignals(False)
                break

        # Deselect any saved card — this is a fresh unsaved palette
        for card in self._scheme_cards.values():
            card._apply_style(False)
        self._current_scheme_id = None
        self._del_btn.setEnabled(False)

        # Generate (overrides replace all engine suggestions)
        self._run_generate(primary_hex, self._style_combo.currentData() or SCHEME_STYLES[0])

        # Auto-save with the name/metadata from the dialog
        if self._current_result and self._repo:
            palette_colors = self._collect_palette_colors(self._current_result)
            owned = self._current_result.owned_count
            try:
                scheme = self._repo.add(
                    primary_hex   = primary_hex,
                    style         = "Custom Manual",
                    owned_count   = owned,
                    total_roles   = len(ROLES),
                    role_overrides= self._role_overrides,
                    palette_json  = palette_colors,
                    **result_data,
                )
                self._current_scheme_id = scheme["id"]
                self._refresh_project_lookup()
                self._reload_saved_list(scheme["id"])
                self._show_success(f"Created '{scheme['name']}'")
            except Exception as e:
                self._show_error(str(e))

    def _on_hex_input_changed(self):
        txt = self._hex_input.text().strip()
        if not txt.startswith("#"):
            txt = "#" + txt
        if len(txt) == 7:
            try:
                int(txt[1:], 16)
                self._color_btn.set_hex(txt.lower())
            except ValueError:
                pass

    def _on_style_changed(self, _=None):
        self._update_style_hint()

    def _update_style_hint(self):
        style = self._style_combo.currentData() or ""
        self._style_hint.setText(STYLE_DESCRIPTIONS.get(style, ""))

    def _on_generate(self):
        self._role_overrides.clear()
        primary_hex = self._color_btn.get_hex()
        style       = self._style_combo.currentData() or SCHEME_STYLES[0]
        self._hex_input.setText(primary_hex.upper())
        self._run_generate(primary_hex, style)

    def _run_generate(self, primary_hex: str, style: str):
        owned = self._get_owned_paints()
        try:
            result = chroma_engine.generate(primary_hex, style, owned)
        except Exception as e:
            self._show_error(f"Generation failed: {e}")
            return

        if self._role_overrides:
            result = _apply_overrides_to_result(result, self._role_overrides, owned)

        self._current_result = result
        self._render_results(result)

        n_owned = result.owned_count
        total   = len(ROLES)
        if n_owned == total:
            self._show_success(f"All {total} roles covered by your collection")
        else:
            missing = total - n_owned
            self._show_info(f"{n_owned}/{total} roles covered — {missing} need paint")

        self._save_btn.setEnabled(self._repo is not None)
        self._link_btn.setEnabled(True)

    def _get_owned_paints(self) -> list:
        svc = self._context.services.try_get("paint_service")
        if svc is None:
            return []
        try:
            return svc.get_all_paints()
        except Exception:
            return []

    # ── Override a role's target color ────────────────────────────────────────

    def _on_override_requested(self, role: str, current_hex: str):
        role_label = ROLE_META.get(role, ("", role))[1]
        dlg = _PrimaryPickerDialog(
            current_hex, self._context,
            title=f"Override Target — {role_label}",
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        new_hex = dlg.selected_hex
        if new_hex == current_hex:
            return
        self._role_overrides[role] = new_hex
        if self._current_result:
            self._run_generate(
                self._current_result.primary_hex,
                self._current_result.style,
            )

    # ── Render results ────────────────────────────────────────────────────────

    def _show_results_placeholder(self):
        self._placeholder.setVisible(True)
        self._banner_strip.setVisible(False)
        self._action_row_widget.setVisible(False)
        self._grid_widget.setVisible(False)
        self._missing_container.setVisible(False)
        self._save_btn.setEnabled(False)
        self._link_btn.setEnabled(False)
        self._current_result = None

    def _render_results(self, result: ChromaResult):
        self._placeholder.setVisible(False)

        # Palette banner strip
        swatches = self._collect_palette_colors(result)
        self._banner_strip.set_swatches(swatches)
        self._banner_strip.setVisible(True)

        # Coverage + action row
        owned = result.owned_count
        total = len(ROLES)
        self._coverage_lbl.setText(f"{owned} / {total} roles matched to your collection")
        self._action_row_widget.setVisible(True)

        # Role cards grid
        while self._grid_lay.count():
            item = self._grid_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        COLS = 3
        for idx, role in enumerate(ROLES):
            rec  = result.recommendations.get(role)
            if rec is None:
                continue
            card = _RoleCard(rec)
            card.override_requested.connect(self._on_override_requested)
            row_, col_ = divmod(idx, COLS)
            self._grid_lay.addWidget(card, row_, col_)

        self._grid_widget.setVisible(True)

        # Missing banner — clear container and repopulate
        while self._missing_vlay.count():
            item = self._missing_vlay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        banner = _MissingBanner(result.missing_roles, owned, total)
        self._missing_vlay.addWidget(banner)
        self._missing_container.setVisible(True)

    @staticmethod
    def _collect_palette_colors(result: ChromaResult) -> list[str]:
        colors = []
        for role in ROLES:
            rec = result.recommendations.get(role)
            if rec is None:
                colors.append("#3a3a3a")
            elif rec.best_match:
                colors.append(rec.best_match.color_hex)
            else:
                colors.append(rec.target_hex)
        return colors

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save(self):
        if not self._current_result or not self._repo:
            return

        primary_hex    = self._current_result.primary_hex
        style          = self._current_result.style
        owned          = self._current_result.owned_count
        total          = len(ROLES)
        palette_colors = self._collect_palette_colors(self._current_result)
        personality    = self._pers_combo.currentData() or ""

        if self._current_scheme_id:
            existing = self._repo.get(self._current_scheme_id)
            if existing:
                reply = QMessageBox.question(
                    self, "Update or Save New?",
                    f"Update '{existing['name']}' or save as a new palette?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save,
                )
                if reply == QMessageBox.Cancel:
                    return
                if reply == QMessageBox.Save:
                    dlg = _SaveDialog(self, primary_hex, style, existing)
                    if dlg.exec() != QDialog.Accepted:
                        return
                    vals = dlg.get_values()
                    self._repo.update(
                        self._current_scheme_id,
                        primary_hex=primary_hex, style=style,
                        owned_count=owned, total_roles=total,
                        role_overrides=self._role_overrides,
                        palette_json=palette_colors,
                        **vals,
                    )
                    self._reload_saved_list(self._current_scheme_id)
                    self._show_success(f"Updated '{vals['name']}'")
                    return

        dlg = _SaveDialog(self, primary_hex, style,
                          existing={"personality": personality})
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        try:
            scheme = self._repo.add(
                primary_hex=primary_hex, style=style,
                owned_count=owned, total_roles=total,
                role_overrides=self._role_overrides,
                palette_json=palette_colors,
                **vals,
            )
            self._current_scheme_id = scheme["id"]
            self._refresh_project_lookup()
            self._reload_saved_list(scheme["id"])
            self._show_success(f"Saved '{vals['name']}'")
        except Exception as e:
            self._show_error(str(e))

    # ── Link to project ───────────────────────────────────────────────────────

    def _on_link_to_project(self):
        if not self._current_result:
            return
        svc = self._context.services.try_get("project_service")
        if not svc:
            QMessageBox.warning(self, "No Projects",
                                "Project Tracker is not loaded.")
            return
        try:
            projects = svc.get_all_projects()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load projects: {e}")
            return
        if not projects:
            self._show_error("No projects found — create one in Project Tracker first.")
            return

        dlg = _ProjectPickerDialog(projects, self)
        if dlg.exec() != QDialog.Accepted or dlg.selected_id is None:
            return

        project_id = dlg.selected_id
        paint_ids  = [
            rec.best_match.paint_id
            for rec in self._current_result.recommendations.values()
            if rec.best_match
        ]
        linked = 0
        for pid in set(paint_ids):
            try:
                self._context.event_bus.emit("project_link_entity", {
                    "project_id":  project_id,
                    "entity_type": "paint",
                    "entity_id":   pid,
                    "notes":       f"Chroma Codex 2.0 — {self._current_result.style}",
                })
                linked += 1
            except Exception as e:
                log.error(f"[CHROMA V2] link paint {pid}: {e}")

        if self._current_scheme_id and self._repo:
            try:
                self._repo.update(self._current_scheme_id,
                                  linked_project_id=project_id)
                self._refresh_project_lookup()
                self._reload_saved_list(self._current_scheme_id)
            except Exception:
                pass

        self._show_success(
            f"Linked {linked} paint{'s' if linked != 1 else ''} to project"
        )

    # ── Status bar ────────────────────────────────────────────────────────────

    def _show_success(self, msg: str):
        self._status_bar.setStyleSheet(
            f"color: {_C['success']}; font-size: {_FS['sm']};"
            f" padding: 4px 16px; border-top: 1px solid {_C['border_lo']};"
            f" background: {_C['bg_base']};"
        )
        self._status_bar.setText(f"✓  {msg}")
        self._status_timer.start(3000)

    def _show_error(self, msg: str):
        self._status_bar.setStyleSheet(
            f"color: {_C['danger']}; font-size: {_FS['sm']};"
            f" padding: 4px 16px; border-top: 1px solid {_C['border_lo']};"
            f" background: {_C['bg_base']};"
        )
        self._status_bar.setText(f"✗  {msg}")
        self._status_timer.start(5000)

    def _show_info(self, msg: str):
        self._status_bar.setStyleSheet(
            f"color: {_C['warning']}; font-size: {_FS['sm']};"
            f" padding: 4px 16px; border-top: 1px solid {_C['border_lo']};"
            f" background: {_C['bg_base']};"
        )
        self._status_bar.setText(f"◑  {msg}")
        self._status_timer.start(4000)

    def _clear_status(self):
        self._status_bar.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['sm']};"
            f" padding: 4px 16px; border-top: 1px solid {_C['border_lo']};"
            f" background: {_C['bg_base']};"
        )
        self._status_bar.setText("")
