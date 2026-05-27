"""
Model Command 2.0 — Premium UI

Tabs:
  0 — Pipeline      Kanban columns for each status with drag-drop
  1 — Collection    Responsive card grid
  2 — Table         Batch operations table
  3 — Statistics    Stats panel with distribution charts
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

import csv
import io
import os
from typing import Optional

from PySide6.QtCore import (
    Qt, QTimer, QSize, Signal, QPropertyAnimation,
    QEasingCurve, QMimeData, QByteArray, QSettings, QEvent,
)
from PySide6.QtGui import QColor, QCursor, QDrag, QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QGridLayout, QSpinBox, QTextEdit, QMessageBox, QFileDialog,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QGroupBox, QFormLayout, QListWidget,
    QListWidgetItem, QSizePolicy, QToolButton, QScrollBar,
    QTabWidget, QProgressBar, QCheckBox, QApplication,
    QStyledItemDelegate, QStyleOptionButton, QStyle,
)

from plugins.model_tracker.models import (
    VALID_STATUSES, STATUS_COLORS,
    COMMON_GAME_SYSTEMS, COMMON_MODEL_TYPES,
)

from .import_registry import ImportRegistry

# ── Design system ──────────────────────────────────────────────────────────────
_C = {
    # Background scale (darkest → lightest surface)
    "bg_deep":    "#141414",
    "bg_base":    "#1c1c1c",
    "bg_card":    "#1e1e1e",
    "bg_raised":  "#212121",
    "bg_input":   "#2a2a2a",
    "bg_hover":   "#2e2e2e",
    "bg_active":  "#333333",

    # Border scale
    "border_lo":  "#282828",
    "border":     "#363636",
    "border_hi":  "#484848",

    # Text scale
    "text_hi":    "#f0f0f0",
    "text_mid":   "#d8d8d8",
    "text_lo":    "#909090",
    "text_dim":   "#606060",

    # Accent (Windows-blue, matches app theme)
    "accent":     "#0078d4",
    "accent_hi":  "#1a8ee8",
    "accent_lo":  "#0f4a7a",
    "accent_text":"#60b0ff",

    # Semantic
    "danger":     "#e05555",
    "danger_hi":  "#eb6868",
    "danger_lo":  "#2a1515",
    "success":    "#3dba6e",
    "success_lo": "#0f2a1a",
    "warning":    "#e07800",
    "warning_lo": "#2a1800",
    "gold":       "#c8960c",
    "gold_lo":    "#2a1e00",
}

# Typography sizes
_FS = {"xs": "10px", "sm": "11px", "base": "12px", "lg": "13px",
       "xl": "15px", "2xl": "20px", "3xl": "28px", "4xl": "36px"}

# Border-radius values
_R = {"xs": "3px", "sm": "5px", "base": "7px", "lg": "10px", "xl": "14px", "pill": "999px"}

# Card / column geometry
_CARD_MIN_W = 230
_CARD_H     = 215
_KANBAN_W   = 280
_CARD_GAP   = 12


# ── Shared style helpers ───────────────────────────────────────────────────────

def _input_ss() -> str:
    return f"""
        QLineEdit, QSpinBox {{
            background: {_C['bg_input']};
            color: {_C['text_hi']};
            border: 1px solid {_C['border']};
            border-radius: {_R['sm']};
            padding: 5px 10px;
            font-size: {_FS['base']};
            selection-background-color: {_C['accent_lo']};
        }}
        QLineEdit:focus, QSpinBox:focus {{
            border-color: {_C['accent']};
            background: {_C['bg_hover']};
        }}
        QLineEdit:hover, QSpinBox:hover {{
            border-color: {_C['border_hi']};
        }}
    """

def _combo_ss() -> str:
    return f"""
        QComboBox {{
            background: {_C['bg_input']};
            color: {_C['text_hi']};
            border: 1px solid {_C['border']};
            border-radius: {_R['sm']};
            padding: 5px 10px;
            font-size: {_FS['base']};
        }}
        QComboBox:focus {{ border-color: {_C['accent']}; }}
        QComboBox:hover {{ border-color: {_C['border_hi']}; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
        QComboBox QAbstractItemView {{
            background: {_C['bg_card']};
            color: {_C['text_hi']};
            border: 1px solid {_C['border']};
            selection-background-color: {_C['accent_lo']};
            selection-color: {_C['accent_text']};
            outline: none;
        }}
    """

def _primary_btn_ss(small: bool = False) -> str:
    pad = "4px 12px" if small else "6px 18px"
    fs  = _FS['sm'] if small else _FS['base']
    return f"""
        QPushButton {{
            background: {_C['accent']};
            color: #ffffff;
            border: none;
            border-radius: {_R['sm']};
            padding: {pad};
            font-size: {fs};
            font-weight: 600;
        }}
        QPushButton:hover {{ background: {_C['accent_hi']}; }}
        QPushButton:pressed {{ background: {_C['accent']}; }}
        QPushButton:disabled {{ background: {_C['bg_hover']}; color: {_C['text_dim']}; }}
    """

def _secondary_btn_ss(small: bool = False) -> str:
    pad = "4px 10px" if small else "6px 14px"
    fs  = _FS['sm'] if small else _FS['base']
    return f"""
        QPushButton {{
            background: {_C['bg_card']};
            color: {_C['text_mid']};
            border: 1px solid {_C['border']};
            border-radius: {_R['sm']};
            padding: {pad};
            font-size: {fs};
        }}
        QPushButton:hover {{
            background: {_C['bg_hover']};
            border-color: {_C['border_hi']};
            color: {_C['text_hi']};
        }}
    """

def _ghost_btn_ss(size: str = "13px") -> str:
    return f"""
        QPushButton, QToolButton {{
            background: transparent;
            border: none;
            color: {_C['text_dim']};
            border-radius: {_R['xs']};
            font-size: {size};
            padding: 3px 5px;
        }}
        QPushButton:hover, QToolButton:hover {{
            background: rgba(255,255,255,0.07);
            color: {_C['text_lo']};
        }}
        QPushButton:pressed, QToolButton:pressed {{
            background: rgba(255,255,255,0.12);
        }}
    """

def _groupbox_ss(title_color: str | None = None) -> str:
    tc = title_color or _C['text_lo']
    return f"""
        QGroupBox {{
            background: {_C['bg_card']};
            border: 1px solid {_C['border']};
            border-radius: {_R['base']};
            margin-top: 18px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: 2px;
            color: {tc};
            font-size: {_FS['sm']};
            font-weight: 700;
            letter-spacing: 0.5px;
            background: transparent;
        }}
    """


# ── Status appearance constants ───────────────────────────────────────────────

_STATUS_COLORS: dict[str, tuple[str, str]] = {
    "Unassembled": ("#444444", "#aaaaaa"),
    "Assembled":   ("#555555", "#cccccc"),
    "Primed":      ("#666666", "#eeeeee"),
    "WIP":         ("#7a4400", "#ffa040"),
    "Painted":     ("#1a3a6a", "#6699ff"),
    "Based":       ("#1a4a2a", "#44cc66"),
    "Complete":    ("#006633", "#00ff88"),
}

_STATUS_ACCENT: dict[str, str] = {
    "Unassembled": "#444444",
    "Assembled":   "#4a5570",
    "Primed":      "#6655aa",
    "WIP":         "#aa5500",
    "Painted":     "#1155cc",
    "Based":       "#117733",
    "Complete":    "#009944",
}

_STATUS_ORDER = ["Unassembled", "Assembled", "Primed", "WIP", "Painted", "Based", "Complete"]

# Pipeline shows 6 columns — WIP is redundant (use Painted for work-in-progress).
# WIP models are folded into the Painted column for display.
_PIPELINE_STATUSES = ["Unassembled", "Assembled", "Primed", "Painted", "Based", "Complete"]
_WIP_DISPLAY_AS    = "Painted"

_STATUS_ICONS: dict[str, str] = {
    "Unassembled": "📦",
    "Assembled":   "🔧",
    "Primed":      "🎨",
    "WIP":         "⚙️",
    "Painted":     "🖌️",
    "Based":       "🌿",
    "Complete":    "✅",
}

_STATUS_BORDER: dict[str, str] = {s: STATUS_COLORS[s] for s in VALID_STATUSES}


def _next_status(current: str) -> str:
    """Advance to the next pipeline status, skipping WIP."""
    order = _PIPELINE_STATUSES
    # If currently WIP, advance to Painted
    if current == "WIP":
        return "Painted"
    try:
        idx = order.index(current)
        return order[(idx + 1) % len(order)]
    except ValueError:
        return "Unassembled"


# ══════════════════════════════════════════════════════════════════════════════
#  _StatusChip
# ══════════════════════════════════════════════════════════════════════════════

class _StatusChip(QLabel):
    """Display-only colored chip showing status with icon."""

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        icon = _STATUS_ICONS.get(status, "")
        self.setText(f"{icon} {status}")
        bg, fg = _STATUS_COLORS.get(status, ("#555555", "#cccccc"))
        self.setStyleSheet(f"""
            color: {fg};
            background: {bg};
            font-size: {_FS['xs']};
            font-weight: 700;
            letter-spacing: 0.4px;
            padding: 2px 9px;
            border-radius: {_R['pill']};
        """)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(18)


# ══════════════════════════════════════════════════════════════════════════════
#  _Toast
# ══════════════════════════════════════════════════════════════════════════════

class _Toast(QFrame):
    """Auto-dismiss 4s toast — positioned bottom-center of parent."""

    def __init__(self, message: str, parent=None, undo_callback=None):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setStyleSheet(f"""
            QFrame#toast {{
                background: {_C['bg_raised']};
                border: 1px solid {_C['accent']};
                border-left: 3px solid {_C['accent']};
                border-radius: {_R['base']};
            }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(12)

        lbl = QLabel(message)
        lbl.setStyleSheet(f"color: {_C['text_mid']}; font-size: {_FS['base']}; background: transparent; border: none;")
        row.addWidget(lbl)

        if undo_callback:
            undo_btn = QPushButton("Undo")
            undo_btn.setStyleSheet(f"""
                QPushButton {{ color: {_C['accent_text']}; background: transparent; border: none;
                              font-size: {_FS['base']}; font-weight: bold; }}
                QPushButton:hover {{ color: {_C['accent_hi']}; }}
            """)
            undo_btn.clicked.connect(undo_callback)
            undo_btn.clicked.connect(self._dismiss)
            row.addWidget(undo_btn)

        self.adjustSize()
        self._position()
        self.show()
        QTimer.singleShot(4000, self._dismiss)

    def _position(self):
        if self.parent():
            pw = self.parent().width()
            ph = self.parent().height()
            self.adjustSize()
            x = (pw - self.width()) // 2
            y = ph - self.height() - 24
            self.move(x, y)

    def _dismiss(self):
        try:
            self.hide()
            self.deleteLater()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  _ModelCard  (Collection grid)
# ══════════════════════════════════════════════════════════════════════════════

class _ModelCard(QFrame):
    edit_requested    = Signal(int)
    delete_requested  = Signal(int)
    status_cycled     = Signal(int, str)
    focus_toggled     = Signal(int, bool)
    gallery_requested = Signal(int)

    def __init__(self, model, meta: dict, parent=None):
        super().__init__(parent)
        self._model   = model
        self._meta    = meta
        self._focused = meta.get("is_focus", False)
        self._build()

    def _build(self):
        self.setObjectName("modelCard")
        self.setMinimumWidth(_CARD_MIN_W)
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        focus_border = f"border: 1px solid {_C['gold']};" if self._focused else f"border: 1px solid {_C['border']};"
        focus_border_hover = f"border-color: {_C['gold']};" if self._focused else f"border-color: {_C['border_hi']};"
        self.setStyleSheet(f"""
            QFrame#modelCard {{
                background: {_C['bg_card']};
                {focus_border}
                border-radius: {_R['base']};
            }}
            QFrame#modelCard:hover {{
                background: {_C['bg_raised']};
                {focus_border_hover}
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(4)

        # ── Top row: focus pin + name ─────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        name_lbl = QLabel(self._model.name)
        name_lbl.setStyleSheet(
            f"font-size: {_FS['lg']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        name_lbl.setWordWrap(True)
        name_lbl.setMaximumHeight(36)
        top_row.addWidget(name_lbl, 1)

        self._pin_btn = QPushButton("🎯")
        pin_base_ss = _ghost_btn_ss("13px")
        pin_hover_color = _C['gold']
        self._pin_btn.setStyleSheet(pin_base_ss + f"""
            QPushButton:hover {{
                background: {_C['gold_lo']};
                color: {pin_hover_color};
            }}
        """)
        if self._focused:
            self._pin_btn.setStyleSheet(pin_base_ss + f"""
                QPushButton {{
                    color: {_C['gold']};
                    background: {_C['gold_lo']};
                }}
                QPushButton:hover {{
                    background: {_C['gold_lo']};
                    color: {_C['gold']};
                }}
            """)
        self._pin_btn.setToolTip("Toggle focus pin")
        self._pin_btn.clicked.connect(self._on_focus_toggle)
        top_row.addWidget(self._pin_btn)

        root.addLayout(top_row)

        # ── Status chip ───────────────────────────────────────────────────
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(4)
        chip_row.addWidget(_StatusChip(self._model.status))
        if self._model.model_type:
            type_chip = QLabel(self._model.model_type)
            type_chip.setStyleSheet(
                f"background: rgba(255,255,255,0.05); color: {_C['text_lo']};"
                f" border-radius: {_R['xs']}; font-size: {_FS['xs']}; padding: 2px 6px;"
                " border: none;"
            )
            chip_row.addWidget(type_chip)
        chip_row.addStretch()
        root.addLayout(chip_row)

        # ── Subtitle: faction / game system ───────────────────────────────
        subtitle = QLabel(f"{self._model.faction} · {self._model.game_system}")
        subtitle.setStyleSheet(
            f"font-size: {_FS['sm']}; color: {_C['text_lo']}; background: transparent; border: none;"
        )
        subtitle.setWordWrap(True)
        subtitle.setMaximumHeight(28)
        root.addWidget(subtitle)

        # ── Squad / quantity row ──────────────────────────────────────────
        if self._model.quantity > 1 or self._meta.get("squad_name"):
            sq_row = QHBoxLayout()
            sq_row.setContentsMargins(0, 0, 0, 0)
            sq_row.setSpacing(6)

            completed = self._meta.get("completed_count", 0)
            qty       = self._model.quantity

            qty_lbl = QLabel(f"{completed}/{qty} complete")
            qty_lbl.setStyleSheet(
                f"font-size: {_FS['xs']}; color: {_C['text_lo']}; background: transparent; border: none;"
            )
            sq_row.addWidget(qty_lbl)

            if qty > 0:
                prog = QProgressBar()
                prog.setRange(0, qty)
                prog.setValue(min(completed, qty))
                prog.setFixedHeight(6)
                prog.setTextVisible(False)
                prog.setStyleSheet(f"""
                    QProgressBar {{ background: {_C['bg_hover']}; border: none; border-radius: 3px; }}
                    QProgressBar::chunk {{ background: {_C['success']}; border-radius: 3px; }}
                """)
                sq_row.addWidget(prog, 1)

            root.addLayout(sq_row)

            if self._meta.get("squad_name"):
                squad_lbl = QLabel(f"Squad: {self._meta['squad_name']}")
                squad_lbl.setStyleSheet(
                    f"font-size: {_FS['xs']}; color: {_C['text_lo']}; background: transparent; border: none;"
                )
                root.addWidget(squad_lbl)

        root.addStretch()

        # ── Button row ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(4)
        btn_row.addStretch()

        for icon, tip, slot, is_delete in (
            ("📷", "View gallery",  self._on_gallery, False),
            ("✏️", "Edit",          self._on_edit,    False),
            ("🔄", "Cycle status",  self._on_cycle,   False),
            ("🗑️", "Delete",        self._on_delete,  True),
        ):
            b = QPushButton(icon)
            b.setFixedSize(28, 28)
            b.setToolTip(tip)
            if is_delete:
                b.setStyleSheet(_ghost_btn_ss("14px") + f"""
                    QPushButton:hover {{ background: {_C['danger_lo']}; color: {_C['danger']}; }}
                """)
            else:
                b.setStyleSheet(_ghost_btn_ss("14px"))
            b.clicked.connect(slot)
            btn_row.addWidget(b)

        root.addLayout(btn_row)

    def _on_gallery(self):     self.gallery_requested.emit(self._model.id)
    def _on_edit(self):        self.edit_requested.emit(self._model.id)
    def _on_delete(self):      self.delete_requested.emit(self._model.id)
    def _on_cycle(self):       self.status_cycled.emit(self._model.id, self._model.status)
    def _on_focus_toggle(self):
        self._focused = not self._focused
        self.focus_toggled.emit(self._model.id, self._focused)


# ══════════════════════════════════════════════════════════════════════════════
#  _KanbanCard  (Kanban column entry, draggable)
# ══════════════════════════════════════════════════════════════════════════════

class _KanbanCard(QFrame):
    edit_requested    = Signal(int)
    status_cycled     = Signal(int, str)
    focus_toggled     = Signal(int, bool)
    gallery_requested = Signal(int)

    def __init__(self, model, meta: dict, parent=None):
        super().__init__(parent)
        self._model      = model
        self._meta       = meta
        self._focused    = meta.get("is_focus", False)
        self._drag_start = None
        self._build()

    def _build(self):
        self.setObjectName("kCard")
        self.setAcceptDrops(False)
        self.setCursor(Qt.OpenHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Use a simple coloured left accent QFrame + uniform outer border.
        # Avoids border-left shorthand / border-left-color which Qt parses
        # inconsistently across platforms.
        if self._focused:
            self.setStyleSheet(f"""
                QFrame#kCard {{
                    background: {_C['bg_card']};
                    border: 1px solid {_C['gold']};
                    border-radius: {_R['sm']};
                }}
                QFrame#kCard:hover {{ background: {_C['bg_raised']}; }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#kCard {{
                    background: {_C['bg_card']};
                    border: 1px solid {_C['border']};
                    border-radius: {_R['sm']};
                }}
                QFrame#kCard:hover {{
                    background: {_C['bg_raised']};
                    border: 1px solid {_C['border_hi']};
                }}
            """)

        # Outer horizontal layout: left-accent bar | content
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 3 px coloured left bar (gold = focused, accent = normal)
        accent_bar = QFrame()
        accent_bar.setFixedWidth(3)
        bar_colour = _C['gold'] if self._focused else _C['accent_lo']
        accent_bar.setStyleSheet(
            f"background: {bar_colour}; border: none;"
            f" border-top-left-radius: {_R['sm']};"
            f" border-bottom-left-radius: {_R['sm']};"
        )
        outer.addWidget(accent_bar)

        # Card content
        root = QVBoxLayout()
        root.setContentsMargins(9, 8, 9, 8)
        root.setSpacing(4)
        outer.addLayout(root, 1)

        # ── Name row ──────────────────────────────────────────────────────
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(4)

        name_lbl = QLabel(self._model.name)
        name_lbl.setStyleSheet(
            f"font-size: {_FS['sm']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        name_lbl.setWordWrap(True)
        name_row.addWidget(name_lbl, 1)

        if self._focused:
            star = QLabel("★")
            star.setStyleSheet(
                f"color: {_C['gold']}; font-size: 11px;"
                " background: transparent; border: none;"
            )
            star.setFixedWidth(13)
            name_row.addWidget(star)

        root.addLayout(name_row)

        # ── Subtitle: faction · type · system (one line, elided) ─────────
        sub_parts = []
        if getattr(self._model, "faction", None):
            sub_parts.append(self._model.faction)
        if getattr(self._model, "model_type", None):
            sub_parts.append(self._model.model_type)
        if getattr(self._model, "game_system", None):
            sub_parts.append(self._model.game_system)
        if sub_parts:
            sub_lbl = QLabel(" · ".join(sub_parts))
            sub_lbl.setStyleSheet(
                f"font-size: {_FS['xs']}; color: {_C['text_lo']};"
                " background: transparent; border: none;"
            )
            # No word wrap — single elided line keeps card height compact
            sub_lbl.setMaximumHeight(14)
            root.addWidget(sub_lbl)

        # ── Progress bar (multi-model squads) ─────────────────────────────
        if getattr(self._model, "quantity", 1) > 1:
            completed = self._meta.get("completed_count", 0)
            qty       = self._model.quantity
            prog_row  = QHBoxLayout()
            prog_row.setContentsMargins(0, 1, 0, 0)
            prog_row.setSpacing(5)

            qty_lbl = QLabel(f"x{qty}")
            qty_lbl.setStyleSheet(
                f"font-size: {_FS['xs']}; color: {_C['text_dim']};"
                " background: transparent; border: none;"
            )
            qty_lbl.setFixedWidth(28)
            prog_row.addWidget(qty_lbl)

            bar = QProgressBar()
            bar.setRange(0, qty)
            bar.setValue(min(completed, qty))
            bar.setFixedHeight(4)
            bar.setTextVisible(False)
            bar.setStyleSheet(
                f"QProgressBar {{ background: {_C['bg_hover']}; border: none; border-radius: 2px; }}"
                f"QProgressBar::chunk {{ background: {_C['success']}; border-radius: 2px; }}"
            )
            prog_row.addWidget(bar, 1)
            root.addLayout(prog_row)

        # ── Action row: 4 compact buttons, right-aligned ──────────────────
        # Fixed total width: 4 × 20 px + 3 × 3 px spacing = 89 px max.
        # No type chip here — already in subtitle — so no overflow risk.
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 3, 0, 0)
        btn_row.setSpacing(3)
        btn_row.addStretch(1)

        _ghost = (
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {_C['text_dim']}; border-radius: {_R['xs']};"
            f" font-size: 10px; padding: 0px; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.08);"
            f" color: {_C['text_lo']}; }}"
        )

        focus_btn = QPushButton("★" if not self._focused else "✕")
        focus_btn.setFixedSize(20, 20)
        if self._focused:
            focus_btn.setStyleSheet(
                f"QPushButton {{ background: {_C['gold_lo']}; color: {_C['gold']};"
                f" border: none; border-radius: {_R['xs']}; font-size: 10px; padding: 0px; }}"
                f"QPushButton:hover {{ color: {_C['warning']}; }}"
            )
            focus_btn.setToolTip("Remove focus pin")
        else:
            focus_btn.setStyleSheet(
                _ghost +
                f"QPushButton:hover {{ background: {_C['gold_lo']}; color: {_C['gold']}; }}"
            )
            focus_btn.setToolTip("Pin as focus")
        focus_btn.clicked.connect(self._on_focus_toggle)
        btn_row.addWidget(focus_btn)

        gallery_btn = QPushButton("🖼")
        gallery_btn.setFixedSize(20, 20)
        gallery_btn.setStyleSheet(_ghost)
        gallery_btn.setToolTip("Gallery")
        gallery_btn.clicked.connect(self._on_gallery)
        btn_row.addWidget(gallery_btn)

        edit_btn = QPushButton("✏")
        edit_btn.setFixedSize(20, 20)
        edit_btn.setStyleSheet(_ghost)
        edit_btn.setToolTip("Edit")
        edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(edit_btn)

        cycle_btn = QPushButton("→")
        cycle_btn.setFixedSize(20, 20)
        cycle_btn.setToolTip("Advance to next stage")
        cycle_btn.setStyleSheet(
            f"QPushButton {{ background: {_C['accent_lo']}; color: {_C['accent_text']};"
            f" border: none; border-radius: {_R['xs']}; font-size: 13px;"
            f" font-weight: bold; padding: 0px; }}"
            f"QPushButton:hover {{ background: {_C['accent']}; color: #ffffff; }}"
        )
        cycle_btn.clicked.connect(self._on_cycle)
        btn_row.addWidget(cycle_btn)

        root.addLayout(btn_row)

    def _on_cycle(self):
        self.status_cycled.emit(self._model.id, self._model.status)

    def _on_gallery(self):
        self.gallery_requested.emit(self._model.id)

    def _on_edit(self):
        self.edit_requested.emit(self._model.id)

    def _on_focus_toggle(self):
        self.focus_toggled.emit(self._model.id, not self._focused)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_start is not None
            and event.buttons() & Qt.LeftButton
            and (event.position().toPoint() - self._drag_start).manhattanLength() > 8
        ):
            self._start_drag()
            # After drag.exec() the pipeline rebuilds and deletes this card.
            # Return immediately — never call super() on a potentially dead object.
            return
        super().mouseMoveEvent(event)

    def _start_drag(self):
        self.setCursor(Qt.ClosedHandCursor)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(self._model.id))
        mime.setData("application/x-model-id", QByteArray(str(self._model.id).encode()))
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)
        # After drag.exec() returns, this card may have been deleted via
        # deleteLater() if the model was moved (rebuild clears all cards).
        # Guard every post-drag attribute access.
        try:
            self.setCursor(Qt.OpenHandCursor)
            self._drag_start = None
        except RuntimeError:
            pass  # C++ object already deleted — safe to ignore


# ══════════════════════════════════════════════════════════════════════════════
#  _KanbanColumn
# ══════════════════════════════════════════════════════════════════════════════

class _KanbanColumn(QFrame):
    model_dropped = Signal(int, str)   # model_id, new_status

    _COL_W = _KANBAN_W  # kept for compat

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self._status = status
        self._cards: list[_KanbanCard] = []
        self.setObjectName("kanbanCol")
        # Expanding horizontally: columns share available width equally.
        # Preferred vertically: column height = tallest card stack; the
        # pipeline's outer scroll handles overflow as one surface.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumWidth(170)
        self.setAcceptDrops(True)
        self._build()

    def _build(self):
        accent_hex        = _STATUS_ACCENT.get(self._status, "#555555")
        badge_bg, badge_fg = _STATUS_COLORS.get(self._status, ("#444444", "#aaaaaa"))

        # Column outer frame styling — rounded corners, subtle border
        self.setStyleSheet(f"""
            QFrame#kanbanCol {{
                background: {_C['bg_card']};
                border: 1px solid {_C['border']};
                border-radius: {_R['base']};
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Coloured top accent strip ─────────────────────────────────────
        accent_bar = QFrame()
        accent_bar.setObjectName("accentBar")
        accent_bar.setFixedHeight(3)
        accent_bar.setStyleSheet(
            f"QFrame#accentBar {{"
            f"  background: {accent_hex}; border: none;"
            f"  border-top-left-radius: {_R['base']};"
            f"  border-top-right-radius: {_R['base']};"
            f"}}"
        )
        outer.addWidget(accent_bar)

        # ── Column header ─────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("colHeader")
        header.setStyleSheet(
            f"QFrame#colHeader {{ background: {_C['bg_raised']}; border: none; }}"
        )
        hdr_row = QHBoxLayout(header)
        hdr_row.setContentsMargins(11, 8, 10, 8)
        hdr_row.setSpacing(6)

        icon_lbl = QLabel(_STATUS_ICONS.get(self._status, ""))
        icon_lbl.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        hdr_row.addWidget(icon_lbl)

        name_lbl = QLabel(self._status.upper())
        name_lbl.setStyleSheet(
            f"font-size: {_FS['xs']}; font-weight: 700; color: {_C['text_mid']};"
            f" letter-spacing: 1px; background: transparent; border: none;"
        )
        hdr_row.addWidget(name_lbl, 1)

        self._count_lbl = QLabel("0")
        self._count_lbl.setAlignment(Qt.AlignCenter)
        self._count_lbl.setFixedSize(26, 18)
        self._count_lbl.setStyleSheet(f"""
            color: {badge_fg};
            background: {badge_bg};
            font-size: {_FS['xs']};
            font-weight: 700;
            border: none;
            border-radius: 9px;
        """)
        hdr_row.addWidget(self._count_lbl)

        outer.addWidget(header)

        # ── Separator ─────────────────────────────────────────────────────
        sep = QFrame()
        sep.setObjectName("colSep")
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"QFrame#colSep {{ background: {_C['border_lo']}; border: none; }}")
        outer.addWidget(sep)

        # ── Card area — NO inner scroll ───────────────────────────────────
        # Cards stack naturally; the pipeline's outer scroll area handles any
        # overflow as one unified surface (no scroll-inside-scroll).
        self._container = QWidget()
        self._container.setObjectName("colContainer")
        self._container.setStyleSheet(
            f"QWidget#colContainer {{ background: {_C['bg_base']}; border: none; }}"
        )
        self._container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)

        self._empty_lbl = QLabel("— Empty —")
        self._empty_lbl.setObjectName("emptyLbl")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['xs']}; font-style: italic;"
            " background: transparent; border: none; padding: 16px 0;"
        )
        self._layout.addWidget(self._empty_lbl)
        self._layout.addStretch()

        outer.addWidget(self._container, 1)

    # ── Public API ────────────────────────────────────────────────────────────

    def clear(self):
        for card in self._cards:
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._count_lbl.setText("0")
        self._empty_lbl.setVisible(True)

    # ── Drag & drop ───────────────────────────────────────────────────────────

    def _set_drop_highlight(self, active: bool):
        if active:
            self._container.setStyleSheet(
                f"QWidget#colContainer {{"
                f"  background: {_C['accent_lo']};"
                f"  border: 1px dashed {_C['accent']};"
                f"  border-radius: {_R['sm']};"
                f"}}"
            )
        else:
            self._container.setStyleSheet(
                f"QWidget#colContainer {{ background: {_C['bg_base']}; border: none; }}"
            )

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-model-id"):
            self._set_drop_highlight(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-model-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drop_highlight(False)

    def dropEvent(self, event):
        self._set_drop_highlight(False)
        try:
            raw      = event.mimeData().text()
            model_id = int(raw)
            self.model_dropped.emit(model_id, self._status)
            event.acceptProposedAction()
        except (ValueError, TypeError) as e:
            log.warning(f"[KANBAN] Drop failed: {e}")
            event.ignore()


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
#  _QuickAddBar
# ══════════════════════════════════════════════════════════════════════════════

class _QuickAddBar(QWidget):
    model_add_requested = Signal(dict)

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self._service   = service
        self._expanded  = False
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {_C['bg_base']}; border-bottom: 1px solid {_C['border']};")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(16, 6, 16, 6)
        self._root.setSpacing(0)

        # Toggle button row
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        self._toggle_btn = QPushButton("＋ Quick Add")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                color: {_C['text_lo']};
                background: transparent;
                border: none;
                font-size: {_FS['base']};
                text-align: left;
                padding: 6px 0;
                font-weight: 500;
            }}
            QPushButton:hover {{ color: {_C['text_mid']}; }}
            QPushButton:checked {{ color: {_C['accent_text']}; font-weight: 600; }}
        """)
        self._toggle_btn.clicked.connect(self._toggle)
        toggle_row.addWidget(self._toggle_btn)
        toggle_row.addStretch()
        self._root.addLayout(toggle_row)

        # Collapsible form
        self._form_widget = QFrame()
        self._form_widget.setStyleSheet(
            f"background: {_C['bg_raised']}; border: 1px solid {_C['border']};"
            f" border-radius: {_R['base']}; padding: 8px 12px;"
        )
        self._form_widget.setVisible(False)

        form_row = QHBoxLayout(self._form_widget)
        form_row.setContentsMargins(0, 4, 0, 4)
        form_row.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Name *")
        self._name_edit.setMinimumWidth(160)
        self._name_edit.setStyleSheet(_input_ss())
        form_row.addWidget(self._name_edit, 2)

        self._sys_combo = QComboBox()
        self._sys_combo.setEditable(True)
        self._sys_combo.addItems(COMMON_GAME_SYSTEMS)
        self._sys_combo.setCurrentIndex(-1)
        self._sys_combo.setMinimumWidth(160)
        self._sys_combo.lineEdit().setPlaceholderText("Game System *")
        self._sys_combo.setStyleSheet(_combo_ss())
        form_row.addWidget(self._sys_combo, 2)

        self._faction_edit = QLineEdit()
        self._faction_edit.setPlaceholderText("Faction *")
        self._faction_edit.setMinimumWidth(130)
        self._faction_edit.setStyleSheet(_input_ss())
        form_row.addWidget(self._faction_edit, 2)

        self._type_combo = QComboBox()
        self._type_combo.addItems(COMMON_MODEL_TYPES)
        self._type_combo.setMinimumWidth(120)
        self._type_combo.setStyleSheet(_combo_ss())
        form_row.addWidget(self._type_combo, 1)

        self._status_combo = QComboBox()
        self._status_combo.addItems(_STATUS_ORDER)
        self._status_combo.setMinimumWidth(110)
        self._status_combo.setStyleSheet(_combo_ss())
        form_row.addWidget(self._status_combo, 1)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 999)
        self._qty_spin.setValue(1)
        self._qty_spin.setFixedWidth(60)
        self._qty_spin.setStyleSheet(_input_ss())
        form_row.addWidget(self._qty_spin)

        add_btn = QPushButton("Add Model")
        add_btn.setStyleSheet(_primary_btn_ss())
        add_btn.clicked.connect(self._submit)
        form_row.addWidget(add_btn)

        self._root.addWidget(self._form_widget)

        # Escape shortcut
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self._form_widget)
        esc.activated.connect(self._close_form)

        # Enter key
        self._name_edit.returnPressed.connect(self._submit)

    def _toggle(self):
        self._expanded = not self._expanded
        self._form_widget.setVisible(self._expanded)
        if self._expanded:
            self._name_edit.setFocus()

    def _close_form(self):
        self._expanded = False
        self._toggle_btn.setChecked(False)
        self._form_widget.setVisible(False)

    def _submit(self):
        name        = self._name_edit.text().strip()
        game_system = self._sys_combo.currentText().strip()
        faction     = self._faction_edit.text().strip()

        if not name or not game_system or not faction:
            return

        self.model_add_requested.emit({
            "name":        name,
            "game_system": game_system,
            "faction":     faction,
            "model_type":  self._type_combo.currentText(),
            "status":      self._status_combo.currentText(),
            "quantity":    self._qty_spin.value(),
        })

        self._name_edit.clear()
        self._faction_edit.clear()
        self._qty_spin.setValue(1)
        self._name_edit.setFocus()

    def refresh_game_systems(self, systems: list[str]):
        current = self._sys_combo.currentText()
        self._sys_combo.blockSignals(True)
        self._sys_combo.clear()
        self._sys_combo.addItems([s for s in systems if s])
        self._sys_combo.setCurrentText(current)
        self._sys_combo.blockSignals(False)


# ══════════════════════════════════════════════════════════════════════════════
#  _ImportDialog
# ══════════════════════════════════════════════════════════════════════════════

class _ImportDialog(QDialog):
    def __init__(self, service, registry: ImportRegistry, parent=None):
        super().__init__(parent)
        self._service  = service
        self._registry = registry
        self._results: list[dict] = []
        self.setWindowTitle("Import Models")
        self.setMinimumSize(820, 580)
        self.setStyleSheet(f"background: {_C['bg_base']};")
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Left: template list ───────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(6)
        lbl = QLabel("FORMAT")
        lbl.setStyleSheet(
            f"font-size: {_FS['sm']}; font-weight: 700; color: {_C['text_lo']};"
            " letter-spacing: 0.5px;"
        )
        left.addWidget(lbl)

        self._template_list = QListWidget()
        self._template_list.setMinimumWidth(180)
        self._template_list.setMaximumWidth(260)
        self._template_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._template_list.setTextElideMode(Qt.ElideRight)
        self._template_list.setStyleSheet(f"""
            QListWidget {{
                background: {_C['bg_card']};
                border: 1px solid {_C['border']};
                border-radius: {_R['base']};
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                color: {_C['text_mid']};
                border-bottom: 1px solid {_C['border_lo']};
                font-size: {_FS['base']};
            }}
            QListWidget::item:selected {{
                background: {_C['accent_lo']};
                color: {_C['accent_text']};
                border-bottom-color: {_C['accent_lo']};
            }}
            QListWidget::item:hover:!selected {{
                background: {_C['bg_raised']};
            }}
        """)
        for tmpl in self._registry.list_all():
            item = QListWidgetItem(tmpl.name)
            item.setToolTip(tmpl.description)
            item.setData(Qt.UserRole, tmpl.id)
            self._template_list.addItem(item)
        if self._template_list.count():
            self._template_list.setCurrentRow(0)
        left.addWidget(self._template_list, 1)

        auto_btn = QPushButton("🔍 Auto-detect")
        auto_btn.setStyleSheet(_secondary_btn_ss())
        auto_btn.clicked.connect(self._auto_detect)
        left.addWidget(auto_btn)

        root.addLayout(left)

        # ── Right: paste area + preview ───────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(6)

        paste_hdr = QHBoxLayout()
        paste_lbl = QLabel("Paste data or load file:")
        paste_lbl.setStyleSheet(f"font-size: {_FS['base']}; color: {_C['text_mid']};")
        paste_hdr.addWidget(paste_lbl)
        paste_hdr.addStretch()
        browse_btn = QPushButton("📂 Browse File")
        browse_btn.setStyleSheet(_secondary_btn_ss(small=True))
        browse_btn.clicked.connect(self._browse_file)
        paste_hdr.addWidget(browse_btn)
        right.addLayout(paste_hdr)

        self._paste_area = QTextEdit()
        self._paste_area.setPlaceholderText(
            "Paste JSON, CSV, or army builder export here…"
        )
        self._paste_area.setStyleSheet(f"""
            QTextEdit {{
                background: {_C['bg_input']};
                color: {_C['text_hi']};
                border: 1px solid {_C['border']};
                border-radius: {_R['base']};
                font-family: 'Consolas', 'Menlo', monospace;
                font-size: {_FS['sm']};
                selection-background-color: {_C['accent_lo']};
                padding: 8px;
            }}
            QTextEdit:focus {{ border-color: {_C['accent']}; }}
        """)
        self._paste_area.setMinimumHeight(160)
        right.addWidget(self._paste_area, 1)

        parse_btn = QPushButton("▶ Parse Preview")
        parse_btn.setStyleSheet(_primary_btn_ss())
        parse_btn.clicked.connect(self._run_parse)
        right.addWidget(parse_btn)

        # Preview table
        preview_lbl = QLabel("Preview:")
        preview_lbl.setStyleSheet(f"font-size: {_FS['sm']}; color: {_C['text_lo']};")
        right.addWidget(preview_lbl)

        self._preview_table = QTableWidget(0, 6)
        headers = ["Name", "Game System", "Faction", "Type", "Status", "Qty"]
        self._preview_table.setHorizontalHeaderLabels(headers)
        self._preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._preview_table.setStyleSheet(f"""
            QTableWidget {{
                background: {_C['bg_card']};
                color: {_C['text_hi']};
                border: 1px solid {_C['border']};
                border-radius: {_R['base']};
                gridline-color: {_C['border_lo']};
                font-size: {_FS['sm']};
                alternate-background-color: {_C['bg_raised']};
            }}
            QHeaderView::section {{
                background: {_C['bg_raised']};
                color: {_C['text_lo']};
                border: none;
                border-bottom: 1px solid {_C['border']};
                padding: 6px 8px;
                font-size: {_FS['xs']};
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
        """)
        hdr = self._preview_table.horizontalHeader()
        hdr.setTextElideMode(Qt.ElideNone)
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        self._preview_table.setMinimumHeight(140)
        right.addWidget(self._preview_table, 1)

        # Error log
        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(f"color: {_C['danger']}; font-size: {_FS['sm']};")
        self._error_lbl.setWordWrap(True)
        right.addWidget(self._error_lbl)

        root.addLayout(right, 1)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("Import All")
        btn_box.button(QDialogButtonBox.Ok).setStyleSheet(_primary_btn_ss())
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet(_secondary_btn_ss())
        btn_box.accepted.connect(self._confirm_import)
        btn_box.rejected.connect(self.reject)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addLayout(root)
        main_layout.addWidget(btn_box)
        self.setLayout(main_layout)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", "All Supported (*.json *.csv *.txt);;JSON (*.json);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                self._paste_area.setPlainText(fh.read())
        except Exception as e:
            log.error(f"[IMPORT DIALOG] File read failed: {e}")
            self._error_lbl.setText(f"Could not read file: {e}")

    def _get_selected_template(self):
        item = self._template_list.currentItem()
        if not item:
            return None
        return self._registry.get(item.data(Qt.UserRole))

    def _run_parse(self):
        tmpl = self._get_selected_template()
        if not tmpl:
            return
        raw = self._paste_area.toPlainText().strip()
        if not raw:
            self._error_lbl.setText("No data to parse.")
            return
        try:
            self._results = tmpl.parse(raw)
            self._populate_preview(self._results)
            if not self._results:
                self._error_lbl.setText("No rows parsed. Check format and required fields.")
            else:
                self._error_lbl.setText(f"Parsed {len(self._results)} models.")
        except Exception as e:
            log.error(f"[IMPORT DIALOG] Parse error: {e}")
            self._error_lbl.setText(f"Parse error: {e}")

    def _auto_detect(self):
        raw = self._paste_area.toPlainText().strip()
        if not raw:
            self._error_lbl.setText("No data to analyse.")
            return
        best_id    = None
        best_count = 0
        for tmpl in self._registry.list_all():
            try:
                rows = tmpl.parse(raw)
                if len(rows) > best_count:
                    best_count = len(rows)
                    best_id    = tmpl.id
            except Exception:
                pass
        if best_id:
            for i in range(self._template_list.count()):
                item = self._template_list.item(i)
                if item.data(Qt.UserRole) == best_id:
                    self._template_list.setCurrentRow(i)
                    break
            self._run_parse()
        else:
            self._error_lbl.setText("Could not detect a suitable format.")

    def _populate_preview(self, rows: list[dict]):
        self._preview_table.setRowCount(0)
        for row in rows:
            r = self._preview_table.rowCount()
            self._preview_table.insertRow(r)
            for col, key in enumerate(("name", "game_system", "faction", "model_type", "status", "quantity")):
                val = row.get(key, "")
                self._preview_table.setItem(r, col, QTableWidgetItem(str(val)))

    def _confirm_import(self):
        if not self._results:
            self.reject()
            return
        self.accept()

    def get_results(self) -> list[dict]:
        return self._results


# _GalleryDialog removed — v2 delegates to ModelImageGalleryDialog from
# plugins.model_tracker.ui which is the battle-tested gallery implementation.
# See ModelTrackerV2UI._on_open_gallery().

# ══════════════════════════════════════════════════════════════════════════════
#  _EditDialog (placeholder class marker — kept for grep / navigation)
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
#  _EditDialog
# ══════════════════════════════════════════════════════════════════════════════

class _EditDialog(QDialog):
    def __init__(self, model, meta: dict, context, service, parent=None):
        super().__init__(parent)
        self._model   = model
        self._meta    = meta
        self._context = context
        self._service = service
        self._linked_project_ids: list[int]   = []
        self._unlinked_project_ids: list[int] = []
        self._current_project_ids: list[int]  = []
        self.setWindowTitle(f"Edit — {model.name}")
        self.setMinimumSize(700, 640)
        self._build()
        self._load_projects()
        self._load_gallery()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # ── Model Details ─────────────────────────────────────────────────
        details_box = QGroupBox("Model Details")
        details_box.setStyleSheet(_groupbox_ss())
        form = QFormLayout(details_box)
        form.setSpacing(8)

        self._name_edit = QLineEdit(self._model.name)
        self._name_edit.setStyleSheet(_input_ss())
        form.addRow("Name *", self._name_edit)

        self._sys_combo = QComboBox()
        self._sys_combo.setEditable(True)
        self._sys_combo.addItems(COMMON_GAME_SYSTEMS)
        self._sys_combo.setCurrentIndex(-1)
        self._sys_combo.setCurrentText(self._model.game_system)
        self._sys_combo.setStyleSheet(_combo_ss())
        form.addRow("Game System *", self._sys_combo)

        self._faction_edit = QLineEdit(self._model.faction)
        self._faction_edit.setStyleSheet(_input_ss())
        form.addRow("Faction *", self._faction_edit)

        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)
        self._type_combo.addItems(COMMON_MODEL_TYPES)
        self._type_combo.setCurrentText(self._model.model_type)
        self._type_combo.setStyleSheet(_combo_ss())
        form.addRow("Model Type *", self._type_combo)

        self._status_combo = QComboBox()
        self._status_combo.addItems(_STATUS_ORDER)
        self._status_combo.setCurrentText(self._model.status)
        self._status_combo.setStyleSheet(_combo_ss())
        form.addRow("Status", self._status_combo)

        self._scale_edit = QLineEdit(self._model.scale or "")
        self._scale_edit.setPlaceholderText("e.g. 28mm")
        self._scale_edit.setStyleSheet(_input_ss())
        form.addRow("Scale", self._scale_edit)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 999)
        self._qty_spin.setValue(self._model.quantity)
        self._qty_spin.setStyleSheet(_input_ss())
        self._qty_spin.valueChanged.connect(self._on_qty_changed)
        form.addRow("Quantity", self._qty_spin)

        self._notes_edit = QTextEdit(self._model.notes or "")
        self._notes_edit.setMaximumHeight(80)
        self._notes_edit.setPlaceholderText("Optional notes…")
        self._notes_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {_C['bg_input']};
                color: {_C['text_hi']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
                font-size: {_FS['base']};
                selection-background-color: {_C['accent_lo']};
                padding: 5px 10px;
            }}
            QTextEdit:focus {{ border-color: {_C['accent']}; }}
        """)
        form.addRow("Notes", self._notes_edit)

        root.addWidget(details_box)

        # ── Squad Tracking ────────────────────────────────────────────────
        self._squad_box = QGroupBox("Squad Tracking")
        self._squad_box.setStyleSheet(_groupbox_ss())
        squad_form = QFormLayout(self._squad_box)
        squad_form.setSpacing(8)

        self._squad_name_edit = QLineEdit(self._meta.get("squad_name", "") or "")
        self._squad_name_edit.setPlaceholderText("Optional squad / unit name")
        self._squad_name_edit.setStyleSheet(_input_ss())
        squad_form.addRow("Squad Name", self._squad_name_edit)

        self._completed_spin = QSpinBox()
        self._completed_spin.setRange(0, self._model.quantity)
        self._completed_spin.setValue(self._meta.get("completed_count", 0))
        self._completed_spin.setStyleSheet(_input_ss())
        squad_form.addRow("Completed Count", self._completed_spin)

        self._squad_box.setVisible(self._model.quantity > 1)
        root.addWidget(self._squad_box)

        # ── Focus ─────────────────────────────────────────────────────────
        focus_box = QGroupBox("Focus / Priority")
        focus_box.setStyleSheet(_groupbox_ss())
        focus_layout = QVBoxLayout(focus_box)
        self._focus_check = QCheckBox("Mark as focus (floats to top of pipeline)")
        self._focus_check.setChecked(bool(self._meta.get("is_focus", False)))
        self._focus_check.setStyleSheet(f"color: {_C['text_mid']};")
        focus_layout.addWidget(self._focus_check)
        root.addWidget(focus_box)

        # ── Photo Gallery ─────────────────────────────────────────────────
        gallery_box = QGroupBox("Photo Gallery")
        gallery_box.setStyleSheet(_groupbox_ss())
        gallery_v = QVBoxLayout(gallery_box)
        gallery_v.setSpacing(8)

        self._gallery_scroll = QScrollArea()
        self._gallery_scroll.setWidgetResizable(True)
        self._gallery_scroll.setFixedHeight(100)
        self._gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._gallery_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._gallery_scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {_C['bg_input']}; border-radius: {_R['sm']}; }}")
        self._gallery_inner = QWidget()
        self._gallery_inner.setStyleSheet(f"background: {_C['bg_input']};")
        self._gallery_row = QHBoxLayout(self._gallery_inner)
        self._gallery_row.setContentsMargins(6, 6, 6, 6)
        self._gallery_row.setSpacing(6)
        self._gallery_row.addStretch()
        self._gallery_scroll.setWidget(self._gallery_inner)
        gallery_v.addWidget(self._gallery_scroll)

        gallery_btn_row = QHBoxLayout()
        add_img_btn = QPushButton("+ Add Photo")
        add_img_btn.setStyleSheet(_secondary_btn_ss(small=True))
        add_img_btn.clicked.connect(self._add_gallery_image)
        gallery_btn_row.addWidget(add_img_btn)
        gallery_btn_row.addStretch()
        gallery_v.addLayout(gallery_btn_row)
        root.addWidget(gallery_box)

        # ── Linked Projects ───────────────────────────────────────────────
        proj_box = QGroupBox("Linked Projects")
        proj_box.setStyleSheet(_groupbox_ss())
        proj_layout = QVBoxLayout(proj_box)

        self._proj_chips_row = QHBoxLayout()
        self._proj_chips_row.setSpacing(6)
        proj_layout.addLayout(self._proj_chips_row)

        link_btn = QPushButton("+ Link Project")
        link_btn.setStyleSheet(_secondary_btn_ss(small=True))
        link_btn.clicked.connect(self._link_project)
        proj_layout.addWidget(link_btn)
        root.addWidget(proj_box)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setStyleSheet(_primary_btn_ss())
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet(_secondary_btn_ss())
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    def _on_qty_changed(self, val: int):
        self._squad_box.setVisible(val > 1)
        self._completed_spin.setMaximum(val)

    def _load_projects(self):
        ps = self._context.services.try_get("project_service")
        if not ps:
            return
        try:
            linked = ps.get_projects_for_entity("model", self._model.id)
            self._current_project_ids = [p.id for p in linked]
            self._rebuild_proj_chips(linked)
        except Exception as e:
            log.warning(f"[EDIT DIALOG] Could not load projects: {e}")

    def _load_gallery(self):
        """Load and display the model's image gallery."""
        # Clear existing thumbnails (keep stretch at end)
        while self._gallery_row.count() > 1:
            item = self._gallery_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            images = self._service.get_images_for_model(self._model.id)
        except Exception as e:
            log.warning(f"[EDIT DIALOG] Gallery load failed: {e}")
            return

        for img in images:
            self._add_gallery_thumb(img["id"], img["image_path"])

    def _add_gallery_thumb(self, image_id: int, path: str):
        """Add a single thumbnail + delete button to the gallery row."""
        from PySide6.QtGui import QPixmap
        clean_path = os.path.abspath(str(path).strip()) if path else ""
        thumb_frame = QFrame()
        thumb_frame.setStyleSheet(
            f"QFrame {{ background: {_C['bg_raised']}; border: 1px solid {_C['border']}; border-radius: {_R['sm']}; }}"
        )
        vbox = QVBoxLayout(thumb_frame)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(2)

        img_lbl = QLabel()
        img_lbl.setFixedSize(72, 56)
        img_lbl.setAlignment(Qt.AlignCenter)
        img_lbl.setStyleSheet("background: transparent; border: none;")
        px = QPixmap()
        if clean_path and os.path.isfile(clean_path):
            px.load(clean_path)
        if not px.isNull():
            img_lbl.setPixmap(px.scaled(72, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            img_lbl.setText("🖼️")
            img_lbl.setStyleSheet(f"font-size: 22px; color: {_C['text_dim']}; background: transparent; border: none;")
        vbox.addWidget(img_lbl)

        del_btn = QPushButton("✕")
        del_btn.setFixedHeight(16)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_C['text_dim']}; border: none; font-size: 9px; }}"
            f"QPushButton:hover {{ color: {_C['danger']}; }}"
        )
        del_btn.clicked.connect(lambda checked=False, iid=image_id: self._remove_gallery_image(iid))
        vbox.addWidget(del_btn, 0, Qt.AlignCenter)

        # Insert before the stretch
        self._gallery_row.insertWidget(self._gallery_row.count() - 1, thumb_frame)

    def _add_gallery_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Add Photo", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)"
        )
        if not path:
            return
        try:
            image_id = self._service.add_image(self._model.id, path)
            self._add_gallery_thumb(image_id, path)
        except Exception as e:
            log.error(f"[EDIT DIALOG] Add image failed: {e}")

    def _remove_gallery_image(self, image_id: int):
        try:
            self._service.remove_image(image_id)
            self._load_gallery()
        except Exception as e:
            log.error(f"[EDIT DIALOG] Remove image failed: {e}")

    def _rebuild_proj_chips(self, projects):
        # Clear existing chips
        while self._proj_chips_row.count():
            item = self._proj_chips_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for proj in projects:
            chip = QPushButton(f"📁 {proj.name}  ×")
            chip.setStyleSheet(f"""
                QPushButton {{
                    background: {_C['accent_lo']};
                    color: {_C['accent_text']};
                    border-radius: {_R['pill']};
                    padding: 3px 10px;
                    font-size: {_FS['sm']};
                    border: none;
                }}
                QPushButton:hover {{
                    background: {_C['danger_lo']};
                    color: {_C['danger']};
                }}
            """)
            pid = proj.id
            chip.clicked.connect(lambda checked=False, p=pid: self._unlink_project(p))
            self._proj_chips_row.addWidget(chip)

        self._proj_chips_row.addStretch()

    def _link_project(self):
        ps = self._context.services.try_get("project_service")
        if not ps:
            return
        try:
            all_projects = ps.get_all_projects()
            available    = [p for p in all_projects if p.id not in self._current_project_ids]
            if not available:
                return
            dlg = QDialog(self)
            dlg.setWindowTitle("Link Project")
            dlg_layout = QVBoxLayout(dlg)
            lst = QListWidget()
            for p in available:
                item = QListWidgetItem(p.name)
                item.setData(Qt.UserRole, p.id)
                lst.addItem(item)
            dlg_layout.addWidget(lst)
            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            dlg_layout.addWidget(btns)
            if dlg.exec() == QDialog.Accepted and lst.currentItem():
                pid = lst.currentItem().data(Qt.UserRole)
                self._current_project_ids.append(pid)
                if pid in self._unlinked_project_ids:
                    self._unlinked_project_ids.remove(pid)
                else:
                    self._linked_project_ids.append(pid)
                self._load_projects()
        except Exception as e:
            log.warning(f"[EDIT DIALOG] Could not link project: {e}")

    def _unlink_project(self, project_id: int):
        if project_id in self._current_project_ids:
            self._current_project_ids.remove(project_id)
        if project_id in self._linked_project_ids:
            self._linked_project_ids.remove(project_id)
        else:
            self._unlinked_project_ids.append(project_id)
        self._load_projects()

    def _validate_and_accept(self):
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        if not self._sys_combo.currentText().strip():
            QMessageBox.warning(self, "Validation", "Game system is required.")
            return
        if not self._faction_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Faction is required.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "id":           self._model.id,
            "name":         self._name_edit.text().strip(),
            "game_system":  self._sys_combo.currentText().strip(),
            "faction":      self._faction_edit.text().strip(),
            "model_type":   self._type_combo.currentText().strip() or "Other",
            "status":       self._status_combo.currentText(),
            "scale":        self._scale_edit.text().strip(),
            "quantity":     self._qty_spin.value(),
            "notes":        self._notes_edit.toPlainText().strip() or None,
            "linked_paint_ids": self._model.linked_paint_ids,
            "is_focus":     self._focus_check.isChecked(),
            "completed_count": self._completed_spin.value(),
            "squad_name":   self._squad_name_edit.text().strip() or "",
            "linked_project_ids":   self._linked_project_ids,
            "unlinked_project_ids": self._unlinked_project_ids,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  _StatisticsPanel
# ══════════════════════════════════════════════════════════════════════════════

class _StatisticsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {_C['bg_base']}; }}")

        content = QWidget()
        content.setStyleSheet(f"background: {_C['bg_base']};")
        layout  = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Summary stat cards
        self._stat_cards_row = QHBoxLayout()
        self._stat_cards_row.setSpacing(12)
        layout.addLayout(self._stat_cards_row)

        # Status distribution
        dist_box = QGroupBox("Status Distribution")
        dist_box.setStyleSheet(_groupbox_ss())
        self._dist_layout = QVBoxLayout(dist_box)
        self._dist_layout.setSpacing(6)
        layout.addWidget(dist_box)

        # Game system breakdown
        sys_box = QGroupBox("Game Systems")
        sys_box.setStyleSheet(_groupbox_ss())
        self._sys_layout = QVBoxLayout(sys_box)
        layout.addWidget(sys_box)

        # Faction breakdown
        faction_box = QGroupBox("Top Factions")
        faction_box.setStyleSheet(_groupbox_ss())
        self._faction_layout = QVBoxLayout(faction_box)
        layout.addWidget(faction_box)

        layout.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self, stats):
        self._rebuild_stat_cards(stats)
        self._rebuild_dist(stats)
        self._rebuild_sys(stats)
        self._rebuild_factions(stats)

    def _rebuild_stat_cards(self, stats):
        while self._stat_cards_row.count():
            item = self._stat_cards_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total_entries  = stats.total_count
        total_minis    = stats.total_models
        complete_count = stats.status_distribution.get("Complete", 0)
        pct = round((complete_count / total_entries) * 100) if total_entries > 0 else 0

        card_accents = [
            _C['accent'],   # entries
            "#6655aa",       # miniatures
            _C['success'],   # game systems
            _C['gold'],      # completion
        ]

        for (label, value, icon), accent_color in zip(
            (
                ("Model Entries",  str(total_entries),  "🎮"),
                ("Miniatures",     str(total_minis),     "🧱"),
                ("Game Systems",   str(stats.unique_game_systems), "🌐"),
                ("Completion",     f"{pct}%",             "✅"),
            ),
            card_accents,
        ):
            card = self._make_stat_card(label, value, icon, accent_color)
            self._stat_cards_row.addWidget(card, 1)

    def _make_stat_card(self, label: str, value: str, icon: str, accent_color: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"""
            QFrame {{
                background: {_C['bg_card']};
                border: 1px solid {_C['border']};
                border-top: 3px solid {accent_color};
                border-radius: {_R['lg']};
            }}
            QFrame:hover {{
                border-color: {_C['border_hi']};
                border-top-color: {accent_color};
            }}
        """)
        v = QVBoxLayout(f)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(4)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        v.addWidget(icon_lbl)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"font-size: {_FS['4xl']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        v.addWidget(val_lbl)
        name_lbl = QLabel(label.upper())
        name_lbl.setStyleSheet(
            f"font-size: {_FS['xs']}; color: {_C['text_lo']};"
            " letter-spacing: 0.5px; background: transparent; border: none;"
        )
        v.addWidget(name_lbl)
        return f

    def _rebuild_dist(self, stats):
        while self._dist_layout.count():
            item = self._dist_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total = max(stats.total_count, 1)
        for status in _STATUS_ORDER:
            count = stats.status_distribution.get(status, 0)
            if count == 0:
                continue
            row = QHBoxLayout()
            row.setSpacing(8)
            icon_lbl = QLabel(f"{_STATUS_ICONS.get(status,'')} {status}")
            icon_lbl.setFixedWidth(150)
            icon_lbl.setStyleSheet(
                f"font-size: {_FS['sm']}; color: {_C['text_mid']}; background: transparent; border: none;"
            )
            row.addWidget(icon_lbl)
            bar = QProgressBar()
            bar.setRange(0, total)
            bar.setValue(count)
            bar.setFixedHeight(16)
            bar.setTextVisible(False)
            _bg, fg = _STATUS_COLORS.get(status, (_C['bg_hover'], _C['text_lo']))
            bar.setStyleSheet(f"""
                QProgressBar {{ background: {_C['bg_hover']}; border: none; border-radius: 8px; }}
                QProgressBar::chunk {{ background: {fg}; border-radius: 8px; }}
            """)
            row.addWidget(bar, 1)
            cnt_lbl = QLabel(str(count))
            cnt_lbl.setFixedWidth(32)
            cnt_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cnt_lbl.setStyleSheet(
                f"font-size: {_FS['sm']}; color: {_C['text_lo']}; background: transparent; border: none;"
            )
            row.addWidget(cnt_lbl)
            container = QWidget()
            container.setLayout(row)
            self._dist_layout.addWidget(container)

    def _rebuild_sys(self, stats):
        while self._sys_layout.count():
            item = self._sys_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for sys_name, count in sorted(stats.game_system_distribution.items(), key=lambda x: -x[1]):
            row = QHBoxLayout()
            lbl = QLabel(sys_name)
            lbl.setStyleSheet(
                f"font-size: {_FS['sm']}; color: {_C['text_mid']}; background: transparent; border: none;"
            )
            row.addWidget(lbl, 1)
            cnt = QLabel(str(count))
            cnt.setStyleSheet(
                f"font-size: {_FS['sm']}; color: {_C['text_lo']}; background: transparent; border: none;"
            )
            row.addWidget(cnt)
            container = QWidget()
            container.setLayout(row)
            self._sys_layout.addWidget(container)

    def _rebuild_factions(self, stats):
        while self._faction_layout.count():
            item = self._faction_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        top10 = sorted(stats.faction_distribution.items(), key=lambda x: -x[1])[:10]
        for faction, count in top10:
            row = QHBoxLayout()
            lbl = QLabel(faction)
            lbl.setStyleSheet(
                f"font-size: {_FS['sm']}; color: {_C['text_mid']}; background: transparent; border: none;"
            )
            row.addWidget(lbl, 1)
            cnt = QLabel(str(count))
            cnt.setStyleSheet(
                f"font-size: {_FS['sm']}; color: {_C['text_lo']}; background: transparent; border: none;"
            )
            row.addWidget(cnt)
            container = QWidget()
            container.setLayout(row)
            self._faction_layout.addWidget(container)


# ══════════════════════════════════════════════════════════════════════════════
#  _CentredCheckDelegate  — draws the checkbox indicator centred in its cell
# ══════════════════════════════════════════════════════════════════════════════

class _CentredCheckDelegate(QStyledItemDelegate):
    """Draws the checkbox indicator horizontally and vertically centred."""

    def paint(self, painter, option, index):
        # Draw the normal row background (selection highlight, alternating, etc.)
        bg_opt = QStyleOptionButton()
        bg_opt.rect  = option.rect
        bg_opt.state = option.state
        style = option.widget.style() if option.widget else QApplication.style()

        # Paint the row panel (background + selection)
        view_opt = self.createViewItemOption(option, index)
        view_opt.text = ""           # suppress any text
        view_opt.decorationSize = QSize(0, 0)
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, view_opt, painter, option.widget)

        # Build a centred checkbox option
        cb_opt = QStyleOptionButton()
        cb_opt.state = QStyle.StateFlag.State_Enabled
        check = index.data(Qt.ItemDataRole.CheckStateRole)
        if check == Qt.CheckState.Checked:
            cb_opt.state |= QStyle.StateFlag.State_On
        else:
            cb_opt.state |= QStyle.StateFlag.State_Off

        # Use the style's own indicator size so it matches the native look
        indicator_size = style.subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, cb_opt, option.widget
        ).size()
        if not indicator_size.isValid() or indicator_size.isEmpty():
            indicator_size = QSize(14, 14)

        x = option.rect.x() + (option.rect.width()  - indicator_size.width())  // 2
        y = option.rect.y() + (option.rect.height() - indicator_size.height()) // 2
        from PySide6.QtCore import QRect
        cb_opt.rect = QRect(x, y, indicator_size.width(), indicator_size.height())

        style.drawControl(QStyle.ControlElement.CE_CheckBox, cb_opt, painter, option.widget)

    def createViewItemOption(self, option, index):
        from PySide6.QtWidgets import QStyleOptionViewItem
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        return opt

    def editorEvent(self, event, model, option, index):
        # Toggle on left-click anywhere in the cell
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            current = index.data(Qt.ItemDataRole.CheckStateRole)
            new_val = (
                Qt.CheckState.Unchecked
                if current == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
            model.setData(index, new_val, Qt.ItemDataRole.CheckStateRole)
            return True
        return super().editorEvent(event, model, option, index)


# ══════════════════════════════════════════════════════════════════════════════
#  _TableView
# ══════════════════════════════════════════════════════════════════════════════

class _TableView(QWidget):
    edit_requested         = Signal(int)
    delete_requested       = Signal(int)
    batch_status_requested = Signal(list, str)  # model_ids, new_status

    _COLS = ["", "Name", "Game System", "Faction", "Type", "Status", "Qty", "Squad", "Focus"]

    # Default widths (px) for each column index.
    # Col 1 (Name) is the only Stretch column; all others are Interactive.
    _DEFAULT_WIDTHS = {
        0: 36,    # checkbox
        2: 130,   # Game System
        3: 130,   # Faction
        4: 110,   # Type
        5: 115,   # Status — wide enough for "Unassembled"
        6: 48,    # Qty
        7: 120,   # Squad
        8: 52,    # Focus
    }
    _SETTINGS_KEY = "model_tracker_v2/table_col_widths"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._models:  list = []
        self._meta:    dict[int, dict] = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Filter bar ────────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍 Search…")
        self._search_edit.setStyleSheet(_input_ss())
        self._search_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._search_edit, 1)

        self._status_filter = QComboBox()
        self._status_filter.addItems(["All Statuses"] + _STATUS_ORDER)
        self._status_filter.setStyleSheet(_combo_ss())
        self._status_filter.currentTextChanged.connect(self._apply_filter)
        filter_row.addWidget(self._status_filter)

        root.addLayout(filter_row)

        # ── Batch toolbar ─────────────────────────────────────────────────
        batch_row = QHBoxLayout()
        batch_row.setSpacing(6)

        sel_all_btn = QPushButton("Select All")
        sel_all_btn.setFixedHeight(28)
        sel_all_btn.clicked.connect(self._select_all)
        sel_all_btn.setStyleSheet(_secondary_btn_ss(small=True))
        batch_row.addWidget(sel_all_btn)

        desel_btn = QPushButton("Deselect All")
        desel_btn.setFixedHeight(28)
        desel_btn.clicked.connect(self._deselect_all)
        desel_btn.setStyleSheet(_secondary_btn_ss(small=True))
        batch_row.addWidget(desel_btn)

        batch_row.addStretch()

        batch_lbl = QLabel("Batch Status →")
        batch_lbl.setStyleSheet(f"color: {_C['text_lo']}; font-size: {_FS['sm']};")
        batch_row.addWidget(batch_lbl)
        self._batch_status_combo = QComboBox()
        self._batch_status_combo.addItems(_STATUS_ORDER)
        self._batch_status_combo.setStyleSheet(_combo_ss())
        batch_row.addWidget(self._batch_status_combo)

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedHeight(28)
        apply_btn.setStyleSheet(_primary_btn_ss(small=True))
        apply_btn.clicked.connect(self._apply_batch_status)
        batch_row.addWidget(apply_btn)

        root.addLayout(batch_row)

        # ── Table ─────────────────────────────────────────────────────────
        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: {_C['bg_base']};
                color: {_C['text_hi']};
                border: none;
                gridline-color: {_C['border_lo']};
                font-size: {_FS['base']};
                alternate-background-color: {_C['bg_card']};
                selection-background-color: {_C['accent_lo']};
                selection-color: {_C['text_hi']};
            }}
            QHeaderView::section {{
                background: {_C['bg_raised']};
                color: {_C['text_lo']};
                border: none;
                border-bottom: 1px solid {_C['border']};
                border-right: 1px solid {_C['border_lo']};
                padding: 8px;
                font-size: {_FS['xs']};
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
        """)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.verticalHeader().setVisible(False)

        # Centred checkbox delegate for column 0
        self._table.setItemDelegateForColumn(0, _CentredCheckDelegate(self._table))

        hdr = self._table.horizontalHeader()
        hdr.setTextElideMode(Qt.ElideNone)
        # Col 0 (checkbox) — fixed width, no resize handle
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        # Col 1 (Name) — stretches to fill remaining space
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        # All other columns — user-resizable
        for c in range(2, len(self._COLS)):
            hdr.setSectionResizeMode(c, QHeaderView.Interactive)

        # Restore saved widths and sort state, falling back to sensible defaults
        self._restore_column_widths()
        self._restore_sort_state()

        # Persist widths whenever the user drags a section divider
        hdr.sectionResized.connect(self._on_section_resized)
        # Persist sort whenever the user clicks a header
        hdr.sortIndicatorChanged.connect(self._on_sort_changed)

        root.addWidget(self._table, 1)

    # ── Column-width persistence ──────────────────────────────────────────────

    def _restore_column_widths(self):
        settings = QSettings("AdeptusCraftmatica", "ModelCommand2")
        for col, default_w in self._DEFAULT_WIDTHS.items():
            w = settings.value(f"{self._SETTINGS_KEY}/{col}", default_w, type=int)
            self._table.setColumnWidth(col, w)

    def _on_section_resized(self, logical_index: int, _old: int, new_size: int):
        if logical_index == 1:
            return  # Stretch column — Qt controls this, nothing to save
        settings = QSettings("AdeptusCraftmatica", "ModelCommand2")
        settings.setValue(f"{self._SETTINGS_KEY}/{logical_index}", new_size)

    # ── Sort-state persistence ────────────────────────────────────────────────

    def _restore_sort_state(self):
        settings  = QSettings("AdeptusCraftmatica", "ModelCommand2")
        col       = settings.value(f"{self._SETTINGS_KEY}/sort_col",   1, type=int)
        order_int = settings.value(f"{self._SETTINGS_KEY}/sort_order", 0, type=int)
        order     = Qt.SortOrder(order_int)
        self._table.sortByColumn(col, order)
        self._table.horizontalHeader().setSortIndicator(col, order)

    def _on_sort_changed(self, logical_index: int, order: Qt.SortOrder):
        settings = QSettings("AdeptusCraftmatica", "ModelCommand2")
        settings.setValue(f"{self._SETTINGS_KEY}/sort_col",   logical_index)
        settings.setValue(f"{self._SETTINGS_KEY}/sort_order", order.value)

    def refresh(self, models: list, meta: dict[int, dict]):
        self._models = models
        self._meta   = meta
        self._populate(models)

    def _populate(self, models: list):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for m in models:
            r    = self._table.rowCount()
            meta = self._meta.get(m.id, {})
            self._table.insertRow(r)

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, m.id)
            self._table.setItem(r, 0, chk)

            for col, val in enumerate((
                m.name, m.game_system, m.faction, m.model_type,
                m.status, str(m.quantity),
                meta.get("squad_name", "") or "",
                "🎯" if meta.get("is_focus") else "",
            ), start=1):
                item = QTableWidgetItem(str(val))
                item.setData(Qt.UserRole, m.id)
                self._table.setItem(r, col, item)

        self._table.setSortingEnabled(True)

    def _apply_filter(self):
        search = self._search_edit.text().lower()
        status = self._status_filter.currentText()
        if status == "All Statuses":
            status = ""

        filtered = [
            m for m in self._models
            if (not search or search in f"{m.name} {m.game_system} {m.faction}".lower())
            and (not status or m.status == status)
        ]
        self._populate(filtered)

    def _select_all(self):
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item:
                item.setCheckState(Qt.Checked)

    def _deselect_all(self):
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item:
                item.setCheckState(Qt.Unchecked)

    def _get_checked_ids(self) -> list[int]:
        ids: list[int] = []
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item and item.checkState() == Qt.Checked:
                ids.append(item.data(Qt.UserRole))
        return ids

    def _apply_batch_status(self):
        ids    = self._get_checked_ids()
        status = self._batch_status_combo.currentText()
        if ids:
            self.batch_status_requested.emit(ids, status)

    def _on_double_click(self, index):
        row  = index.row()
        item = self._table.item(row, 0)
        if item:
            self.edit_requested.emit(item.data(Qt.UserRole))


# ══════════════════════════════════════════════════════════════════════════════
#  ModelTrackerV2UI  (main widget)
# ══════════════════════════════════════════════════════════════════════════════

class ModelTrackerV2UI(QWidget):
    def __init__(self, service, meta_repo, context, parent=None):
        super().__init__(parent)
        self._service   = service
        self._meta_repo = meta_repo
        self._context   = context
        self._models:   list = []
        self._meta:     dict[int, dict] = {}
        self._import_registry = ImportRegistry()

        # Active filter state
        self._filter_search      = ""
        self._filter_game_system = ""
        self._filter_faction     = ""
        self._filter_model_type  = ""
        self._filter_status      = ""

        self._build()
        QTimer.singleShot(0, self.refresh)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.setStyleSheet(f"""
            QScrollBar:vertical {{
                background: {_C['bg_base']};
                width: 8px;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {_C['bg_active']};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_C['border_hi']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: {_C['bg_base']};
                height: 8px;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {_C['bg_active']};
                border-radius: 4px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {_C['border_hi']};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

        # Header
        root.addWidget(self._build_header())

        # Quick add bar
        self._quick_add = _QuickAddBar(self._service)
        self._quick_add.model_add_requested.connect(self._on_quick_add)
        root.addWidget(self._quick_add)

        # Filter bar
        root.addWidget(self._build_filter_bar())

        # View tabs
        self._tabs = QTabWidget()
        self._tabs.tabBar().setElideMode(Qt.ElideNone)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                border-top: 1px solid {_C['border']};
                background: {_C['bg_base']};
            }}
            QTabBar {{
                background: {_C['bg_base']};
            }}
            QTabBar::tab {{
                background: transparent;
                color: {_C['text_dim']};
                border: none;
                border-bottom: 2px solid transparent;
                padding: 9px 20px;
                font-size: {_FS['base']};
                font-weight: 500;
                min-width: 0;
            }}
            QTabBar::tab:selected {{
                color: {_C['text_hi']};
                border-bottom: 2px solid {_C['accent']};
                font-weight: 600;
            }}
            QTabBar::tab:hover:!selected {{
                color: {_C['text_mid']};
                background: rgba(255,255,255,0.03);
            }}
        """)

        # Pipeline — expanding columns fill the viewport width equally, so the
        # last column's border is never clipped.  Horizontal scrollbar only
        # appears when the window is very narrow (< 6 × 170 px minimum).
        self._pipeline_container = QScrollArea()
        self._pipeline_container.setWidgetResizable(True)
        self._pipeline_container.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._pipeline_container.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._pipeline_container.setStyleSheet(f"QScrollArea {{ border: none; background: {_C['bg_base']}; }}")
        self._pipeline_widget = QWidget()
        self._pipeline_widget.setStyleSheet(f"background: {_C['bg_base']};")
        self._pipeline_layout = QHBoxLayout(self._pipeline_widget)
        self._pipeline_layout.setContentsMargins(14, 14, 14, 14)
        self._pipeline_layout.setSpacing(10)
        self._pipeline_columns: dict[str, _KanbanColumn] = {}
        for status in _PIPELINE_STATUSES:
            col = _KanbanColumn(status)
            col.model_dropped.connect(self._on_model_dropped)
            self._pipeline_columns[status] = col
            self._pipeline_layout.addWidget(col)

        self._pipeline_container.setWidget(self._pipeline_widget)
        self._tabs.addTab(self._pipeline_container, "Pipeline")

        # Collection grid
        self._collection_scroll = QScrollArea()
        self._collection_scroll.setWidgetResizable(True)
        self._collection_scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {_C['bg_base']}; }}")
        self._collection_widget = QWidget()
        self._collection_widget.setStyleSheet(f"background: {_C['bg_base']};")
        self._collection_grid = QGridLayout(self._collection_widget)
        self._collection_grid.setContentsMargins(16, 16, 16, 16)
        self._collection_grid.setSpacing(_CARD_GAP)
        self._collection_scroll.setWidget(self._collection_widget)

        # Empty state for collection
        self._collection_empty = QLabel(
            "No models match your filters.\nTry adjusting the search or use Quick Add above."
        )
        self._collection_empty.setAlignment(Qt.AlignCenter)
        self._collection_empty.setStyleSheet(f"""
            color: {_C['text_dim']};
            font-size: {_FS['lg']};
            background: transparent;
            border: none;
            padding: 40px;
        """)
        self._collection_empty.setWordWrap(True)
        self._collection_empty.setVisible(False)
        self._collection_grid.addWidget(self._collection_empty, 0, 0, 1, 3)

        self._tabs.addTab(self._collection_scroll, "Collection")

        # Table
        self._table_view = _TableView()
        self._table_view.edit_requested.connect(self._on_edit)
        self._table_view.delete_requested.connect(self._on_delete)
        self._table_view.batch_status_requested.connect(self._on_batch_status)
        self._tabs.addTab(self._table_view, "Table")

        # Statistics
        self._stats_panel = _StatisticsPanel()
        self._tabs.addTab(self._stats_panel, "Statistics")

        root.addWidget(self._tabs, 1)

        # Status bar
        self._status_bar = QLabel("Loading…")
        self._status_bar.setStyleSheet(f"""
            color: {_C['text_dim']};
            font-size: {_FS['sm']};
            padding: 5px 16px;
            border-top: 1px solid {_C['border_lo']};
            background: {_C['bg_base']};
        """)
        root.addWidget(self._status_bar)

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("pluginHeader")
        bar.setStyleSheet(f"""
            QFrame#pluginHeader {{
                background: {_C['bg_base']};
                border-bottom: 1px solid {_C['border']};
            }}
        """)
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 14, 20, 14)
        row.setSpacing(12)

        # Accent dot + title
        dot = QFrame()
        dot.setFixedSize(4, 32)
        dot.setStyleSheet(f"background: {_C['accent']}; border-radius: 2px;")
        row.addWidget(dot)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title_col.setContentsMargins(0, 0, 0, 0)
        title_lbl = QLabel("Model Command")
        title_lbl.setStyleSheet(
            f"font-size: {_FS['xl']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        version_lbl = QLabel("2.0")
        version_lbl.setStyleSheet(
            f"font-size: {_FS['xs']}; color: {_C['accent_text']}; background: transparent;"
            " border: none; letter-spacing: 0.5px; font-weight: 600;"
        )
        title_col.addWidget(title_lbl)
        title_col.addWidget(version_lbl)
        row.addLayout(title_col)
        row.addStretch()

        import_btn = QPushButton("↑  Import")
        import_btn.setStyleSheet(_secondary_btn_ss())
        import_btn.clicked.connect(self._open_import_dialog)
        row.addWidget(import_btn)

        export_btn = QPushButton("↓  Export CSV")
        export_btn.setStyleSheet(_secondary_btn_ss())
        export_btn.clicked.connect(self._export_csv)
        row.addWidget(export_btn)

        return bar

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background: {_C['bg_base']}; border-bottom: 1px solid {_C['border']};")
        col = QVBoxLayout(bar)
        col.setContentsMargins(16, 10, 16, 10)
        col.setSpacing(8)

        # Row 1: search + dropdowns
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("  Search by name, faction, game system…")
        self._search_edit.setMinimumWidth(220)
        self._search_edit.setFixedHeight(34)
        self._search_edit.setStyleSheet(_input_ss())
        self._search_edit.textChanged.connect(self._on_search_changed)
        row1.addWidget(self._search_edit, 3)

        self._sys_filter = QComboBox()
        self._sys_filter.setFixedHeight(34)
        self._sys_filter.setStyleSheet(_combo_ss())
        row1.addWidget(self._sys_filter, 1)

        self._faction_filter = QComboBox()
        self._faction_filter.setFixedHeight(34)
        self._faction_filter.setStyleSheet(_combo_ss())
        row1.addWidget(self._faction_filter, 1)

        self._type_filter = QComboBox()
        self._type_filter.setFixedHeight(34)
        self._type_filter.setStyleSheet(_combo_ss())
        row1.addWidget(self._type_filter, 1)

        # Wire signals
        self._sys_filter.addItems(["All Game Systems"])
        self._faction_filter.addItems(["All Factions"])
        self._type_filter.addItems(["All Types"])
        self._sys_filter.currentTextChanged.connect(self._on_filter_changed)
        self._faction_filter.currentTextChanged.connect(self._on_filter_changed)
        self._type_filter.currentTextChanged.connect(self._on_filter_changed)

        clear_btn = QPushButton("✕ Clear")
        clear_btn.setFixedHeight(34)
        clear_btn.setStyleSheet(_secondary_btn_ss(small=True))
        clear_btn.clicked.connect(self._clear_filters)
        row1.addWidget(clear_btn)
        col.addLayout(row1)

        # Row 2: preset chips
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.setContentsMargins(0, 0, 0, 0)

        self._preset_btns = {}
        presets = [
            ("All",         "all",      None),
            ("🎨 Primed",   "primed",   "#6655aa"),
            ("🖌️ Painted",  "painted",  "#1155cc"),
            ("🌿 Based",    "based",    "#117733"),
            ("✅ Complete", "complete", "#009944"),
        ]
        for label, preset, active_color in presets:
            ac = active_color or _C['accent']
            try:
                ar = int(ac[1:3], 16)
                ag = int(ac[3:5], 16)
                ab = int(ac[5:7], 16)
            except (ValueError, IndexError):
                ar, ag, ab = 0, 120, 212
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.setObjectName(f"preset_{preset}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_C['bg_card']};
                    color: {_C['text_lo']};
                    border: 1px solid {_C['border']};
                    border-radius: {_R['pill']};
                    padding: 2px 12px;
                    font-size: {_FS['sm']};
                }}
                QPushButton:hover {{
                    background: {_C['bg_hover']};
                    color: {_C['text_mid']};
                }}
                QPushButton:checked {{
                    background: rgba({ar},{ag},{ab},0.2);
                    color: {ac};
                    border-color: {ac};
                    font-weight: 600;
                }}
            """)
            btn.clicked.connect(lambda checked=False, p=preset: self.apply_preset(p))
            self._preset_btns[preset] = btn
            row2.addWidget(btn)

        row2.addStretch()
        col.addLayout(row2)
        return bar

    # ── Refresh / filter ──────────────────────────────────────────────────────

    def refresh(self):
        try:
            self._models = self._service.get_all_models()
            self._meta   = self._meta_repo.get_all_meta()
            self._update_filter_combos()
            self._apply_current_filter()
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 UI] refresh failed: {e}")

    def _update_filter_combos(self):
        systems  = ["All Game Systems"] + self._service.get_game_systems()
        factions = ["All Factions"]     + self._service.get_factions()
        types    = ["All Types"]        + self._service.get_types()

        for combo, items in (
            (self._sys_filter,     systems),
            (self._faction_filter, factions),
            (self._type_filter,    types),
        ):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            if current in items:
                combo.setCurrentText(current)
            combo.blockSignals(False)

    def apply_filter(
        self,
        search:      str = "",
        game_system: str = "",
        faction:     str = "",
        model_type:  str = "",
        status:      str = "",
    ):
        self._filter_search      = search
        self._filter_game_system = game_system
        self._filter_faction     = faction
        self._filter_model_type  = model_type
        self._filter_status      = status
        self._apply_current_filter()

    def apply_preset(self, preset_name: str):
        status_map = {
            "all":       "",
            "wip":       "WIP",
            "painted":   "Painted",
            "complete":  "Complete",
            "assembled": "Assembled",
            "primed":    "Primed",
            "based":     "Based",
        }
        status = status_map.get(preset_name, "")
        # Update preset button checked states
        if hasattr(self, '_preset_btns'):
            for name, btn in self._preset_btns.items():
                btn.setChecked(name == preset_name)
        self.apply_filter(status=status)

    def _on_search_changed(self, text: str):
        self._filter_search = text
        self._apply_current_filter()

    def _on_filter_changed(self):
        sys_text     = self._sys_filter.currentText()
        faction_text = self._faction_filter.currentText()
        type_text    = self._type_filter.currentText()

        self._filter_game_system = "" if sys_text == "All Game Systems" else sys_text
        self._filter_faction     = "" if faction_text == "All Factions"    else faction_text
        self._filter_model_type  = "" if type_text == "All Types"          else type_text
        self._apply_current_filter()

    def _clear_filters(self):
        self._search_edit.clear()
        self._sys_filter.setCurrentIndex(0)
        self._faction_filter.setCurrentIndex(0)
        self._type_filter.setCurrentIndex(0)
        self._filter_search = self._filter_game_system = ""
        self._filter_faction = self._filter_model_type = self._filter_status = ""
        self._apply_current_filter()

    def _apply_current_filter(self):
        s  = self._filter_search.lower()
        gs = self._filter_game_system.lower()
        fa = self._filter_faction.lower()
        mt = self._filter_model_type.lower()
        st = self._filter_status

        filtered = []
        for m in self._models:
            if s  and s  not in f"{m.name} {m.game_system} {m.faction} {m.model_type}".lower():
                continue
            if gs and gs not in m.game_system.lower():
                continue
            if fa and fa not in m.faction.lower():
                continue
            if mt and mt not in m.model_type.lower():
                continue
            if st and m.status != st:
                continue
            filtered.append(m)

        self._rebuild_pipeline(filtered)
        self._rebuild_collection(filtered)
        self._table_view.refresh(filtered, self._meta)
        self._rebuild_stats()
        self._update_status_bar(filtered)

    def _rebuild_pipeline(self, models: list):
        for col in self._pipeline_columns.values():
            col.clear()

        focus_first = sorted(
            models,
            key=lambda m: (0 if self._meta.get(m.id, {}).get("is_focus") else 1, m.name)
        )
        for m in focus_first:
            # WIP is folded into the Painted column for display
            display_status = _WIP_DISPLAY_AS if m.status == "WIP" else m.status
            col = self._pipeline_columns.get(display_status)
            if not col:
                continue
            meta  = self._meta.get(m.id, {})
            kcard = _KanbanCard(m, meta)
            kcard.edit_requested.connect(self._on_edit)
            kcard.status_cycled.connect(self._on_status_cycle)
            kcard.focus_toggled.connect(self._on_focus_toggle)
            kcard.gallery_requested.connect(self._on_open_gallery)
            col._layout.insertWidget(
                0 if meta.get("is_focus") else col._layout.count() - 1,
                kcard,
            )
            col._cards.append(kcard)
            col._count_lbl.setText(str(len(col._cards)))
            col._empty_lbl.setVisible(False)

    def _rebuild_collection(self, models: list):
        # Remove all cards except the persistent empty-state label
        while self._collection_grid.count():
            item = self._collection_grid.takeAt(0)
            w = item.widget() if item else None
            if w and w is not self._collection_empty:
                w.deleteLater()

        if not models:
            self._collection_empty.setVisible(True)
            self._collection_grid.addWidget(self._collection_empty, 0, 0, 1, 3)
            return

        self._collection_empty.setVisible(False)

        # Focus models first, then alphabetical
        sorted_models = sorted(
            models,
            key=lambda m: (0 if self._meta.get(m.id, {}).get("is_focus") else 1, m.name)
        )

        COLS = 3
        for idx, m in enumerate(sorted_models):
            meta  = self._meta.get(m.id, {})
            card  = _ModelCard(m, meta)
            card.edit_requested.connect(self._on_edit)
            card.delete_requested.connect(self._on_delete)
            card.status_cycled.connect(self._on_status_cycle)
            card.focus_toggled.connect(self._on_focus_toggle)
            card.gallery_requested.connect(self._on_open_gallery)
            row = idx // COLS
            col = idx % COLS
            self._collection_grid.addWidget(card, row, col)

        # Fill remaining columns to avoid stretching
        if models:
            last_col = (len(models) - 1) % COLS
            for c in range(last_col + 1, COLS):
                spacer = QWidget()
                self._collection_grid.addWidget(spacer, (len(models) - 1) // COLS, c)

    def _rebuild_stats(self):
        try:
            stats = self._service.get_statistics()
            self._stats_panel.refresh(stats)
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 UI] stats rebuild failed: {e}")

    def _update_status_bar(self, models: list):
        total   = sum(m.quantity for m in models)
        entries = len(models)
        self._status_bar.setText(f"{entries} model entries · {total} miniatures")

    # ── CRUD handlers ─────────────────────────────────────────────────────────

    def _on_quick_add(self, data: dict):
        try:
            model = self._service.add_model(
                name        = data["name"],
                game_system = data["game_system"],
                faction     = data["faction"],
                model_type  = data.get("model_type", "Other"),
                status      = data.get("status", "Unassembled"),
                quantity    = data.get("quantity", 1),
            )
            self._context.event_bus.emit("model_added", model.to_dict())
            self.refresh()
            _Toast(f"Added: {model.name}", self)
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 UI] quick add failed: {e}")
            _Toast(f"Error: {e}", self)

    def _on_edit(self, model_id: int):
        model = self._service.get_model(model_id)
        if not model:
            return
        meta = self._meta.get(model_id, {"is_focus": False, "completed_count": 0, "squad_name": ""})
        dlg  = _EditDialog(model, meta, self._context, self._service, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.get_data()
        try:
            updated = self._service.update_model(
                model_id    = model_id,
                name        = data["name"],
                game_system = data["game_system"],
                faction     = data["faction"],
                model_type  = data["model_type"],
                status      = data["status"],
                scale       = data.get("scale", ""),
                quantity    = data["quantity"],
                notes       = data.get("notes"),
                linked_paint_ids = data.get("linked_paint_ids", []),
            )
            self._meta_repo.set_meta(
                model_id,
                is_focus        = data["is_focus"],
                completed_count = data["completed_count"],
                squad_name      = data.get("squad_name", ""),
            )
            self._on_project_link_changed(
                model_id,
                data.get("linked_project_ids", []),
                data.get("unlinked_project_ids", []),
            )
            self._context.event_bus.emit("model_updated", updated.to_dict())
            self.refresh()
            _Toast(f"Updated: {updated.name}", self)
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 UI] update failed: {e}")
            _Toast(f"Error: {e}", self)

    def _on_open_gallery(self, model_id: int):
        model = self._service.get_model(model_id)
        if not model:
            return
        try:
            from plugins.model_tracker.ui import ModelImageGalleryDialog
            dlg = ModelImageGalleryDialog(self._context, model, parent=self)
        except Exception as e:
            log.warning(f"[MODEL TRACKER V2] Could not open v1 gallery dialog: {e}")
            return
        dlg.exec()

    def _on_delete(self, model_id: int):
        model = self._service.get_model(model_id)
        name  = model.name if model else f"#{model_id}"
        reply = QMessageBox.question(
            self, "Delete Model",
            f"Delete '{name}'?  This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._service.remove_model(model_id)
            self._meta_repo.delete_meta(model_id)
            self._context.event_bus.emit("model_removed", {"id": model_id})
            self.refresh()
            _Toast(f"Deleted: {name}", self)
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 UI] delete failed: {e}")
            _Toast(f"Error: {e}", self)

    def _on_status_cycle(self, model_id: int, current_status: str):
        new_status = _next_status(current_status)
        model      = self._service.get_model(model_id)
        if not model:
            return
        try:
            updated = self._service.update_model(
                model_id    = model_id,
                name        = model.name,
                game_system = model.game_system,
                faction     = model.faction,
                model_type  = model.model_type,
                status      = new_status,
                scale       = model.scale,
                quantity    = model.quantity,
                notes       = model.notes,
                linked_paint_ids = model.linked_paint_ids,
            )
            self._context.event_bus.emit("model_updated", updated.to_dict())
            self.refresh()
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 UI] status cycle failed: {e}")

    def _on_focus_toggle(self, model_id: int, is_focus: bool):
        try:
            self._meta_repo.set_meta(model_id, is_focus=is_focus)
            self._meta = self._meta_repo.get_all_meta()
            self._apply_current_filter()
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 UI] focus toggle failed: {e}")

    def _on_model_dropped(self, model_id: int, new_status: str):
        model = self._service.get_model(model_id)
        if not model:
            return
        try:
            updated = self._service.update_model(
                model_id    = model_id,
                name        = model.name,
                game_system = model.game_system,
                faction     = model.faction,
                model_type  = model.model_type,
                status      = new_status,
                scale       = model.scale,
                quantity    = model.quantity,
                notes       = model.notes,
                linked_paint_ids = model.linked_paint_ids,
            )
            self._context.event_bus.emit("model_updated", updated.to_dict())
            self.refresh()
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 UI] drag-drop status update failed: {e}")

    def _on_batch_status(self, model_ids: list[int], new_status: str):
        for mid in model_ids:
            model = self._service.get_model(mid)
            if not model:
                continue
            try:
                self._service.update_model(
                    model_id    = mid,
                    name        = model.name,
                    game_system = model.game_system,
                    faction     = model.faction,
                    model_type  = model.model_type,
                    status      = new_status,
                    scale       = model.scale,
                    quantity    = model.quantity,
                    notes       = model.notes,
                    linked_paint_ids = model.linked_paint_ids,
                )
            except Exception as e:
                log.warning(f"[MODEL TRACKER V2 UI] batch status update failed for {mid}: {e}")
        self._context.event_bus.emit("model_updated", {})
        self.refresh()
        _Toast(f"Updated {len(model_ids)} models to {new_status}", self)

    # ── Import / Export ───────────────────────────────────────────────────────

    def _open_import_dialog(self):
        dlg = _ImportDialog(self._service, self._import_registry, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        rows = dlg.get_results()
        if not rows:
            return
        added = 0
        errors = 0
        for data in rows:
            try:
                self._service.add_model(
                    name        = data["name"],
                    game_system = data["game_system"],
                    faction     = data["faction"],
                    model_type  = data.get("model_type", "Other"),
                    status      = data.get("status", "Unassembled"),
                    scale       = data.get("scale", ""),
                    quantity    = data.get("quantity", 1),
                    notes       = data.get("notes"),
                )
                added += 1
            except Exception as e:
                log.warning(f"[IMPORT] add_model failed: {e}")
                errors += 1

        self._context.event_bus.emit("model_added", {"bulk": True, "count": added})
        self.refresh()
        msg = f"Imported {added} models"
        if errors:
            msg += f" ({errors} skipped)"
        _Toast(msg, self)

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Models CSV", "models_export.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            models = self._service.get_all_models()
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=[
                    "id", "name", "game_system", "faction", "model_type",
                    "status", "scale", "quantity", "notes",
                ])
                writer.writeheader()
                for m in models:
                    writer.writerow({
                        "id":          m.id,
                        "name":        m.name,
                        "game_system": m.game_system,
                        "faction":     m.faction,
                        "model_type":  m.model_type,
                        "status":      m.status,
                        "scale":       m.scale,
                        "quantity":    m.quantity,
                        "notes":       m.notes or "",
                    })
            _Toast(f"Exported {len(models)} models to CSV", self)
        except Exception as e:
            log.error(f"[EXPORT] CSV export failed: {e}")
            _Toast(f"Export failed: {e}", self)

    # ── Project linking ───────────────────────────────────────────────────────

    def _on_project_link_changed(
        self,
        model_id:    int,
        linked_ids:  list[int],
        unlinked_ids: list[int],
    ):
        ps = self._context.services.try_get("project_service")
        if not ps:
            return
        for pid in linked_ids:
            try:
                ps.link_entity(pid, "model", model_id)
            except Exception as e:
                log.warning(f"[MODEL TRACKER V2] link project {pid}: {e}")
        for pid in unlinked_ids:
            try:
                ps.unlink_entity(pid, "model", model_id)
            except Exception as e:
                log.warning(f"[MODEL TRACKER V2] unlink project {pid}: {e}")
