"""
Dashboard 2.0 — Premium adaptive UI
═════════════════════════════════════
Layout:
  Header         — greeting · date · streak · [Refresh] [Customize]
  QScrollArea    — adaptive 2-column widget grid
    ┌─ Stats Strip ─────────────────────────────────────┐  (full width)
    ├─ Active Projects ───┬─ Quick Actions ─────────────┤
    ├─ Recommendations ───┼─ Notifications ─────────────┤
    ├─ Paint Intel ───────┼─ Activity Feed ─────────────┤
    └─ Calendar ────────────────────────────────────────┘  (full width, if loaded)
"""
from __future__ import annotations

import json
import logging
log = logging.getLogger(__name__)

from datetime import date, datetime

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui  import QColor, QPainter, QPen, QBrush, QLinearGradient, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QGridLayout, QDialog, QDialogButtonBox,
    QSizePolicy, QListWidget, QListWidgetItem, QAbstractItemView,
    QCheckBox, QToolButton,
)

# ── Design system ─────────────────────────────────────────────────────────────

_C = {
    "bg_deep":     "#0c0c0c",
    "bg_base":     "#121212",
    "bg_card":     "#1a1a1a",
    "bg_raised":   "#1f1f1f",
    "bg_input":    "#252525",
    "bg_hover":    "#2a2a2a",
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

_SEV: dict[str, str] = {
    "accent":  _C["accent_text"],
    "success": _C["success"],
    "warning": _C["warning"],
    "danger":  _C["danger"],
    "info":    _C["accent_text"],
    "critical":_C["danger"],
}

_SEV_BG: dict[str, str] = {
    "accent":  _C["accent_lo"],
    "success": _C["success_lo"],
    "warning": _C["warning_lo"],
    "danger":  _C["danger_lo"],
    "info":    _C["accent_lo"],
    "critical":_C["danger_lo"],
}

_SEV_ICONS: dict[str, str] = {
    "info":     "ℹ",
    "success":  "✓",
    "warning":  "⚠",
    "danger":   "✕",
    "critical": "🔴",
}

_PRIORITY_COLOR = {1: _C["danger"], 2: _C["warning"], 3: _C["accent_text"]}


# ── Widget catalogue ──────────────────────────────────────────────────────────

_WIDGET_CATALOG: dict[str, dict] = {
    "stats_strip": {
        "title": "Command Overview", "icon": "⚡",
        "width": "full", "service": None,
        "desc": "Key metrics at a glance from all your plugins",
    },
    "active_projects": {
        "title": "Active Projects", "icon": "📁",
        "width": "half", "service": None,
        "desc": "In-progress projects with completion bars",
    },
    "quick_actions": {
        "title": "Quick Actions", "icon": "🚀",
        "width": "half", "service": None,
        "desc": "One-click shortcuts to common tasks",
    },
    "recommendations": {
        "title": "Recommended Actions", "icon": "💡",
        "width": "half", "service": None,
        "desc": "Smart next-step suggestions powered by your plugins",
    },
    "notifications": {
        "title": "Notifications", "icon": "🔔",
        "width": "half", "service": None,
        "desc": "Alerts and warnings from all installed plugins",
    },
    "paint_intel": {
        "title": "Paint Intelligence", "icon": "🎨",
        "width": "half", "service": "paint_service",
        "desc": "Low-stock alerts, recent additions, and brand breakdown",
    },
    "activity_feed": {
        "title": "Recent Activity", "icon": "📜",
        "width": "half", "service": None,
        "desc": "Chronological activity log across all plugins",
    },
    "calendar": {
        "title": "Today's Agenda", "icon": "📅",
        "width": "full", "service": "calendar_service",
        "desc": "Today's events, upcoming week, and overdue items",
    },
}

_DEFAULT_ORDER = [
    "stats_strip",
    "active_projects", "quick_actions",
    "recommendations", "notifications",
    "paint_intel",     "activity_feed",
    "calendar",
]

_SETTINGS_ORDER_KEY  = "dashboard_v2.widget_order"
_SETTINGS_HIDDEN_KEY = "dashboard_v2.hidden_widgets"


# ══════════════════════════════════════════════════════════════════════════════
# Helper utilities
# ══════════════════════════════════════════════════════════════════════════════

def _sev_color(key: str) -> str:
    return _SEV.get(key, _C["accent_text"])


def _sev_bg(key: str) -> str:
    return _SEV_BG.get(key, _C["accent_lo"])


def _ghost_btn(text: str, parent=None) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {_C['text_lo']};
            border: 1px solid {_C['border']}; border-radius: {_R['sm']};
            padding: 4px 10px; font-size: {_FS['sm']};
        }}
        QPushButton:hover {{
            background: {_C['bg_hover']}; color: {_C['text_mid']};
            border-color: {_C['border_hi']};
        }}
        QPushButton:pressed {{ background: {_C['bg_active']}; }}
    """)
    return btn


def _primary_btn(text: str, parent=None) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {_C['accent']}; color: #ffffff;
            border: none; border-radius: {_R['sm']};
            padding: 4px 12px; font-size: {_FS['sm']}; font-weight: 600;
        }}
        QPushButton:hover {{ background: {_C['accent_hi']}; }}
        QPushButton:pressed {{ background: {_C['accent']}; }}
    """)
    return btn


def _small_link_btn(text: str, parent=None) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {_C['accent_text']};
            border: none; padding: 2px 4px; font-size: {_FS['xs']};
        }}
        QPushButton:hover {{ color: {_C['accent_hi']}; }}
    """)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def _pill_badge(text: str, fg: str, bg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        color: {fg}; background: {bg}; border-radius: {_R['pill']};
        padding: 1px 7px; font-size: {_FS['xs']}; font-weight: 600;
    """)
    return lbl


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {_C['border_lo']}; border: none;")
    return line


def _empty_state(message: str) -> QLabel:
    lbl = QLabel(message)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(
        f"color: {_C['text_dim']}; font-size: {_FS['sm']}; "
        f"font-style: italic; padding: 20px;"
    )
    lbl.setWordWrap(True)
    return lbl


def _relative_time(iso_ts: str) -> str:
    """Turn an ISO timestamp into 'just now / 5m ago / 3h ago / yesterday / date'."""
    try:
        dt   = datetime.fromisoformat(iso_ts)
        now  = datetime.now()
        diff = now - dt
        s    = int(diff.total_seconds())
        if s < 60:
            return "just now"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        if s < 172800:
            return "yesterday"
        return dt.strftime("%d %b")
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# QPainter widgets
# ══════════════════════════════════════════════════════════════════════════════

class _ProgressBar(QWidget):
    """Bleed-safe progress bar drawn with QPainter."""

    def __init__(self, value: float = 0.0, color: str = _C["accent"],
                 height: int = 6, parent=None):
        super().__init__(parent)
        self._value = max(0.0, min(1.0, value))
        self._color = color
        self.setFixedHeight(height)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_value(self, v: float, color: str | None = None):
        self._value = max(0.0, min(1.0, v))
        if color:
            self._color = color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = 3
        w, h = self.width(), self.height()

        # Track
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_C["bg_hover"]))
        p.drawRoundedRect(0, 0, w, h, r, r)

        # Fill
        fill_w = max(r * 2, int(w * self._value))
        p.setBrush(QColor(self._color))
        p.drawRoundedRect(0, 0, fill_w, h, r, r)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
# Base dashboard widget card
# ══════════════════════════════════════════════════════════════════════════════

class _DashWidget(QFrame):
    """
    Base card for the dashboard grid.

    Subclass and override ``refresh()`` to populate the content area.
    """
    action_requested = Signal(str, dict)

    def __init__(self, widget_id: str, parent=None):
        super().__init__(parent)
        meta = _WIDGET_CATALOG.get(widget_id, {})
        self._widget_id = widget_id
        self._title     = meta.get("title", widget_id)
        self._icon      = meta.get("icon", "◆")

        self.setObjectName(f"dashCard_{widget_id}")
        self.setStyleSheet(f"""
            QFrame#dashCard_{widget_id} {{
                background: {_C['bg_card']};
                border: 1px solid {_C['border']};
                border-radius: {_R['lg']};
            }}
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        self._hdr = QFrame()
        self._hdr.setFixedHeight(40)
        self._hdr.setObjectName(f"dashCardHdr_{widget_id}")
        self._hdr.setStyleSheet(f"""
            QFrame#dashCardHdr_{widget_id} {{
                background: {_C['bg_raised']};
                border-radius: {_R['lg']} {_R['lg']} 0 0;
                border-bottom: 1px solid {_C['border_lo']};
            }}
        """)
        hdr_lay = QHBoxLayout(self._hdr)
        hdr_lay.setContentsMargins(14, 0, 12, 0)
        hdr_lay.setSpacing(8)

        icon_lbl = QLabel(self._icon)
        icon_lbl.setStyleSheet(f"font-size: 14px; background: transparent; border: none;")
        hdr_lay.addWidget(icon_lbl)

        self._title_lbl = QLabel(self._title)
        self._title_lbl.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['base']}; "
            f"font-weight: 600; background: transparent; border: none;"
        )
        hdr_lay.addWidget(self._title_lbl)
        hdr_lay.addStretch()

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
            f"background: transparent; border: none;"
        )
        self._count_lbl.setVisible(False)
        hdr_lay.addWidget(self._count_lbl)

        root.addWidget(self._hdr)

        # ── Content ───────────────────────────────────────────────────────────
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(14, 12, 14, 14)
        self._content_lay.setSpacing(6)
        root.addWidget(self._content, stretch=1)

    def _set_count(self, n: int):
        if n > 0:
            self._count_lbl.setText(str(n))
            self._count_lbl.setVisible(True)
        else:
            self._count_lbl.setVisible(False)

    def _clear_content(self):
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh(self, *args, **kwargs):
        """Override in subclasses."""
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Stats Strip Widget
# ══════════════════════════════════════════════════════════════════════════════

class _StatCard(QFrame):
    """One stat tile inside the stats strip."""

    def __init__(self, stat, parent=None):
        super().__init__(parent)
        color    = _sev_color(stat.color)
        bg_color = _sev_bg(stat.color)

        self.setMinimumWidth(120)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_C['bg_raised']};
                border: 1px solid {_C['border']};
                border-radius: {_R['base']};
            }}
        """)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left accent bar (3px, QPainter-safe separate widget)
        bar = QFrame()
        bar.setFixedWidth(3)
        bar.setStyleSheet(
            f"background: {color}; border: none; "
            f"border-radius: {_R['xs']} 0 0 {_R['xs']};"
        )
        outer.addWidget(bar)

        # Card content
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(inner)
        cl.setContentsMargins(10, 10, 10, 10)
        cl.setSpacing(2)

        # Icon + value row
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        if stat.icon:
            icon_lbl = QLabel(stat.icon)
            icon_lbl.setStyleSheet(
                f"font-size: 18px; background: transparent; border: none;"
            )
            top_row.addWidget(icon_lbl)

        val_lbl = QLabel(stat.value)
        val_lbl.setStyleSheet(
            f"color: {color}; font-size: {_FS['2xl']}; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        top_row.addWidget(val_lbl)
        top_row.addStretch()
        cl.addLayout(top_row)

        # Label
        label_lbl = QLabel(stat.label)
        label_lbl.setStyleSheet(
            f"color: {_C['text_mid']}; font-size: {_FS['sm']}; "
            f"font-weight: 500; background: transparent; border: none;"
        )
        cl.addWidget(label_lbl)

        # Subtitle
        if stat.subtitle:
            sub_lbl = QLabel(stat.subtitle)
            sub_lbl.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            sub_lbl.setWordWrap(True)
            cl.addWidget(sub_lbl)

        cl.addStretch()
        outer.addWidget(inner, stretch=1)


class _StatsStripWidget(_DashWidget):

    def __init__(self, parent=None):
        super().__init__("stats_strip", parent)
        self._content_lay.setContentsMargins(12, 12, 12, 12)
        self._content_lay.setSpacing(0)
        # Grid will be added dynamically
        self._grid: QGridLayout | None = None

    def refresh(self, stats: list):
        self._clear_content()

        if not stats:
            self._content_lay.addWidget(
                _empty_state("No statistics available yet — try installing more plugins.")
            )
            return

        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(grid_widget)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)

        cols = 4
        for i, stat in enumerate(stats):
            row = i // cols
            col = i % cols
            card = _StatCard(stat)
            self._grid.addWidget(card, row, col)

        # Stretch empty columns
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)

        self._content_lay.addWidget(grid_widget)


# ══════════════════════════════════════════════════════════════════════════════
# Active Projects Widget
# ══════════════════════════════════════════════════════════════════════════════

class _ProjectCard(QFrame):
    """One project entry card."""
    open_requested = Signal(str, dict)

    def __init__(self, card, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_C['bg_raised']};
                border: 1px solid {_C['border']};
                border-radius: {_R['base']};
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        # Row 1: plugin badge + title + open button
        top = QHBoxLayout()
        top.setSpacing(8)

        if card.plugin_label:
            badge = _pill_badge(
                card.plugin_label,
                _C["accent_text"], _C["accent_lo"],
            )
            top.addWidget(badge)

        title = QLabel(card.title)
        title.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['base']}; "
            f"font-weight: 600; background: transparent; border: none;"
        )
        title.setWordWrap(False)
        top.addWidget(title, stretch=1)

        if card.last_active:
            last = QLabel(card.last_active)
            last.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            top.addWidget(last)

        open_btn = _small_link_btn(f"{card.action_label} →")
        open_btn.clicked.connect(
            lambda _, e=card.action_event, p=card.action_payload:
                self.open_requested.emit(e, p)
        )
        top.addWidget(open_btn)
        lay.addLayout(top)

        # Row 2: subtitle
        if card.subtitle:
            sub = QLabel(card.subtitle)
            sub.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            sub.setWordWrap(True)
            lay.addWidget(sub)

        # Row 3: progress bar + status
        if card.progress >= 0:
            pct = int(card.progress * 100)
            bar_color = (
                _C["success"] if pct >= 80 else
                _C["accent"]  if pct >= 40 else
                _C["warning"]
            )
            pb_row = QHBoxLayout()
            pb_row.setSpacing(8)

            bar = _ProgressBar(card.progress, bar_color, height=5)
            pb_row.addWidget(bar, stretch=1)

            pct_lbl = QLabel(f"{pct}%")
            pct_lbl.setStyleSheet(
                f"color: {bar_color}; font-size: {_FS['xs']}; "
                f"font-weight: 600; background: transparent; border: none;"
            )
            pb_row.addWidget(pct_lbl)
            lay.addLayout(pb_row)

        # Row 4: detail lines
        for line in card.detail_lines[:2]:
            dl = QLabel(f"• {line}")
            dl.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            lay.addWidget(dl)


class _ActiveProjectsWidget(_DashWidget):

    def __init__(self, parent=None):
        super().__init__("active_projects", parent)
        self.setMinimumHeight(220)

    def refresh(self, cards: list):
        self._clear_content()
        self._set_count(len(cards))

        if not cards:
            self._content_lay.addWidget(
                _empty_state("No active projects found.\nStart a project in any plugin to see it here.")
            )
            return

        for card in cards[:6]:
            pc = _ProjectCard(card)
            pc.open_requested.connect(self.action_requested)
            self._content_lay.addWidget(pc)

        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Quick Actions Widget
# ══════════════════════════════════════════════════════════════════════════════

class _QuickActionsWidget(_DashWidget):

    def __init__(self, parent=None):
        super().__init__("quick_actions", parent)
        self.setMinimumHeight(160)

    def refresh(self, actions: list):
        self._clear_content()

        if not actions:
            self._content_lay.addWidget(
                _empty_state("No quick actions available.")
            )
            return

        grid = QGridLayout()
        grid.setSpacing(8)
        cols = 3

        for i, action in enumerate(actions):
            btn = QPushButton(f"{action.icon}\n{action.label}")
            btn.setFixedHeight(56)
            color = _sev_color(action.color)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_C['bg_raised']};
                    border: 1px solid {_C['border']};
                    border-radius: {_R['base']};
                    color: {_C['text_mid']};
                    font-size: {_FS['xs']};
                    padding: 4px;
                }}
                QPushButton:hover {{
                    background: {_C['bg_hover']};
                    border-color: {color};
                    color: {_C['text_hi']};
                }}
                QPushButton:pressed {{ background: {_C['bg_active']}; }}
            """)
            btn.clicked.connect(
                lambda _, e=action.event, p=action.payload:
                    self.action_requested.emit(e, p)
            )
            row = i // cols
            col = i % cols
            grid.addWidget(btn, row, col)

        for c in range(cols):
            grid.setColumnStretch(c, 1)

        self._content_lay.addLayout(grid)
        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Recommendations Widget
# ══════════════════════════════════════════════════════════════════════════════

class _RecRow(QFrame):
    """One recommendation row."""
    action_requested = Signal(str, dict)

    def __init__(self, rec, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_C['bg_raised']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        # Priority dot
        dot = QLabel("●")
        dot.setFixedWidth(12)
        color = _PRIORITY_COLOR.get(rec.priority, _C["accent_text"])
        dot.setStyleSheet(
            f"color: {color}; font-size: 10px; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(dot)

        # Text block
        main_lbl = QLabel(f"<b>{rec.action}</b>: {rec.target}")
        main_lbl.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['sm']}; "
            f"background: transparent; border: none;"
        )
        main_lbl.setWordWrap(True)

        text_block = QVBoxLayout()
        text_block.setSpacing(1)
        text_block.addWidget(main_lbl)

        if rec.context:
            ctx_lbl = QLabel(rec.context)
            ctx_lbl.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            text_block.addWidget(ctx_lbl)

        lay.addLayout(text_block, stretch=1)

        # Action button
        if rec.action_event:
            view_btn = _small_link_btn(rec.action_label)
            view_btn.clicked.connect(
                lambda _, e=rec.action_event, p=rec.action_payload:
                    self.action_requested.emit(e, p)
            )
            lay.addWidget(view_btn)


class _RecommendationsWidget(_DashWidget):

    def __init__(self, parent=None):
        super().__init__("recommendations", parent)
        self.setMinimumHeight(200)

    def refresh(self, recs: list):
        self._clear_content()

        # Sort by priority
        recs = sorted(recs, key=lambda r: r.priority)
        self._set_count(len(recs))

        if not recs:
            self._content_lay.addWidget(
                _empty_state("All caught up — no pending recommendations.")
            )
            return

        for rec in recs[:8]:
            row = _RecRow(rec)
            row.action_requested.connect(self.action_requested)
            self._content_lay.addWidget(row)

        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Notifications Widget
# ══════════════════════════════════════════════════════════════════════════════

class _NotifRow(QFrame):
    """One notification row."""
    action_requested = Signal(str, dict)

    def __init__(self, notif, parent=None):
        super().__init__(parent)
        sev   = notif.severity
        color = _sev_color(sev)
        bg    = _sev_bg(sev)

        self.setStyleSheet(f"""
            QFrame {{
                background: {_C['bg_raised']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
            }}
        """)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left severity bar
        sev_bar = QFrame()
        sev_bar.setFixedWidth(3)
        sev_bar.setStyleSheet(
            f"background: {color}; border: none; "
            f"border-radius: {_R['xs']} 0 0 {_R['xs']};"
        )
        outer.addWidget(sev_bar)

        # Content
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        cl = QHBoxLayout(inner)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(10)

        # Icon
        sev_icon = QLabel(_SEV_ICONS.get(sev, "ℹ"))
        sev_icon.setStyleSheet(
            f"color: {color}; font-size: 13px; "
            f"background: transparent; border: none;"
        )
        sev_icon.setFixedWidth(16)
        cl.addWidget(sev_icon)

        # Text
        text_block = QVBoxLayout()
        text_block.setSpacing(1)

        title = QLabel(notif.title)
        title.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['sm']}; "
            f"font-weight: 600; background: transparent; border: none;"
        )
        title.setWordWrap(True)
        text_block.addWidget(title)

        if notif.body:
            body = QLabel(notif.body)
            body.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            body.setWordWrap(True)
            text_block.addWidget(body)

        cl.addLayout(text_block, stretch=1)

        if notif.action_event:
            view_btn = _small_link_btn(notif.action_label)
            view_btn.clicked.connect(
                lambda _, e=notif.action_event, p=notif.action_payload:
                    self.action_requested.emit(e, p)
            )
            cl.addWidget(view_btn)

        outer.addWidget(inner, stretch=1)


class _NotificationsWidget(_DashWidget):

    def __init__(self, parent=None):
        super().__init__("notifications", parent)
        self.setMinimumHeight(200)

    def refresh(self, notifs: list):
        self._clear_content()

        # Sort by severity (critical first)
        _order = {"critical": 0, "danger": 1, "warning": 2, "info": 3, "success": 4}
        notifs = sorted(notifs, key=lambda n: _order.get(n.severity, 99))
        self._set_count(len(notifs))

        if not notifs:
            self._content_lay.addWidget(
                _empty_state("No notifications — everything looks good!")
            )
            return

        for notif in notifs[:8]:
            row = _NotifRow(notif)
            row.action_requested.connect(self.action_requested)
            self._content_lay.addWidget(row)

        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Paint Intelligence Widget
# ══════════════════════════════════════════════════════════════════════════════

class _PaintIntelWidget(_DashWidget):

    def __init__(self, parent=None):
        super().__init__("paint_intel", parent)
        self.setMinimumHeight(220)

    def refresh(self, low: list, recent: list, brands: dict):
        self._clear_content()

        if not low and not recent and not brands:
            self._content_lay.addWidget(
                _empty_state("Paint Tracker not loaded or no paints recorded yet.")
            )
            return

        # ── Low stock section ─────────────────────────────────────────────────
        if low:
            sec_lbl = QLabel("Low Stock")
            sec_lbl.setStyleSheet(
                f"color: {_C['warning']}; font-size: {_FS['sm']}; "
                f"font-weight: 700; background: transparent;"
            )
            self._content_lay.addWidget(sec_lbl)

            for p in low[:5]:
                row = QHBoxLayout()
                row.setSpacing(8)

                qty = getattr(p, "quantity", -1)
                dot_color = _C["danger"] if qty == 0 else _C["warning"]
                dot = QLabel("●")
                dot.setStyleSheet(
                    f"color: {dot_color}; font-size: 9px; "
                    f"background: transparent; border: none;"
                )
                dot.setFixedWidth(10)
                row.addWidget(dot)

                brand = getattr(p, "brand", "")
                name  = getattr(p, "name", str(p))
                name_lbl = QLabel(f"{brand} {name}".strip())
                name_lbl.setStyleSheet(
                    f"color: {_C['text_mid']}; font-size: {_FS['xs']}; "
                    f"background: transparent; border: none;"
                )
                name_lbl.setWordWrap(False)
                row.addWidget(name_lbl, stretch=1)

                qty_str = "Empty" if qty == 0 else f"{qty} left"
                qty_lbl = QLabel(qty_str)
                qty_lbl.setStyleSheet(
                    f"color: {dot_color}; font-size: {_FS['xs']}; "
                    f"font-weight: 600; background: transparent; border: none;"
                )
                row.addWidget(qty_lbl)
                self._content_lay.addLayout(row)

            if len(low) > 5:
                more = QLabel(f"+ {len(low) - 5} more low-stock paints")
                more.setStyleSheet(
                    f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                    f"font-style: italic; background: transparent;"
                )
                self._content_lay.addWidget(more)

            self._content_lay.addWidget(_hline())

        # ── Brand breakdown ───────────────────────────────────────────────────
        if brands:
            sec_lbl2 = QLabel("Brand Breakdown")
            sec_lbl2.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"font-weight: 700; background: transparent; "
                f"letter-spacing: 0.5px; text-transform: uppercase;"
            )
            self._content_lay.addWidget(sec_lbl2)

            total = sum(brands.values()) or 1
            top_brands = sorted(brands.items(), key=lambda x: -x[1])[:5]

            for brand_name, count in top_brands:
                br = QVBoxLayout()
                br.setSpacing(2)

                label_row = QHBoxLayout()
                b_lbl = QLabel(brand_name)
                b_lbl.setStyleSheet(
                    f"color: {_C['text_mid']}; font-size: {_FS['xs']}; "
                    f"background: transparent; border: none;"
                )
                label_row.addWidget(b_lbl, stretch=1)
                c_lbl = QLabel(str(count))
                c_lbl.setStyleSheet(
                    f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                    f"background: transparent; border: none;"
                )
                label_row.addWidget(c_lbl)
                br.addLayout(label_row)

                bar = _ProgressBar(count / total, _C["accent_text"], height=4)
                br.addWidget(bar)
                self._content_lay.addLayout(br)

        elif recent:
            # Fallback: recently added paints
            sec_lbl3 = QLabel("Recently Added")
            sec_lbl3.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"font-weight: 700; background: transparent; "
                f"letter-spacing: 0.5px;"
            )
            self._content_lay.addWidget(sec_lbl3)

            for p in recent:
                brand = getattr(p, "brand", "")
                name  = getattr(p, "name", str(p))
                row = QLabel(f"+ {brand} {name}".strip())
                row.setStyleSheet(
                    f"color: {_C['text_mid']}; font-size: {_FS['xs']}; "
                    f"background: transparent; border: none;"
                )
                self._content_lay.addWidget(row)

        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Activity Feed Widget
# ══════════════════════════════════════════════════════════════════════════════

class _ActivityWidget(_DashWidget):

    def __init__(self, parent=None):
        super().__init__("activity_feed", parent)
        self.setMinimumHeight(220)

    def refresh(self, items: list):
        self._clear_content()
        self._set_count(len(items))

        if not items:
            self._content_lay.addWidget(
                _empty_state("No activity recorded yet.\nEvents from all plugins will appear here.")
            )
            return

        from datetime import timedelta as _td
        today_str     = date.today().isoformat()
        yesterday_str = (date.today() - _td(days=1)).isoformat()

        current_group = None

        for item in items[:20]:
            # Group header
            ts  = item.get("timestamp", "")
            day = ts[:10] if ts else ""
            if day and day != current_group:
                current_group = day
                if day == today_str:
                    group_label = "Today"
                elif day == yesterday_str:
                    group_label = "Yesterday"
                else:
                    try:
                        group_label = datetime.fromisoformat(day).strftime("%d %b")
                    except Exception:
                        group_label = day

                g_lbl = QLabel(group_label)
                g_lbl.setStyleSheet(
                    f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                    f"font-weight: 600; background: transparent; "
                    f"text-transform: uppercase; letter-spacing: 0.5px; "
                    f"padding-top: 6px;"
                )
                self._content_lay.addWidget(g_lbl)

            # Activity row
            row = QHBoxLayout()
            row.setSpacing(8)

            icon = QLabel(item.get("icon", "•"))
            icon.setStyleSheet(
                f"font-size: 13px; background: transparent; border: none;"
            )
            icon.setFixedWidth(18)
            row.addWidget(icon)

            desc = QLabel(item.get("description", ""))
            desc.setStyleSheet(
                f"color: {_C['text_mid']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            desc.setWordWrap(False)
            row.addWidget(desc, stretch=1)

            time_str = _relative_time(ts)
            if time_str:
                time_lbl = QLabel(time_str)
                time_lbl.setStyleSheet(
                    f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                    f"background: transparent; border: none;"
                )
                row.addWidget(time_lbl)

            self._content_lay.addLayout(row)

        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Calendar Widget
# ══════════════════════════════════════════════════════════════════════════════

class _CalendarWidget(_DashWidget):

    def __init__(self, parent=None):
        super().__init__("calendar", parent)
        self.setMinimumHeight(120)

    def refresh(self, today_events, week_events, milestones, overdue):
        self._clear_content()

        has_content = bool(today_events or week_events or milestones or overdue)
        if not has_content:
            self._content_lay.addWidget(
                _empty_state("No upcoming events or milestones scheduled.")
            )
            return

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        col = 0

        # ── Today ──────────────────────────────────────────────────────────────
        if today_events:
            col_w = self._make_cal_section("Today", today_events[:4], "📅", _C["accent_text"])
            grid.addWidget(col_w, 0, col)
            col += 1

        # ── Overdue ────────────────────────────────────────────────────────────
        if overdue:
            col_w = self._make_cal_section("Overdue", overdue[:4], "⚠", _C["danger"])
            grid.addWidget(col_w, 0, col)
            col += 1

        # ── This Week ──────────────────────────────────────────────────────────
        if week_events and col < 3:
            col_w = self._make_cal_section("Upcoming", week_events[:4], "🗓", _C["text_mid"])
            grid.addWidget(col_w, 0, col)
            col += 1

        # ── Milestones ─────────────────────────────────────────────────────────
        if milestones and col < 3:
            col_w = self._make_cal_section("Milestones", milestones[:4], "🏆", _C["gold"])
            grid.addWidget(col_w, 0, col)

        self._content_lay.addLayout(grid)

    def _make_cal_section(self, label: str, events: list,
                           icon: str, color: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(4)
        i_lbl = QLabel(icon)
        i_lbl.setStyleSheet(f"font-size: 12px; background: transparent;")
        hdr.addWidget(i_lbl)
        h_lbl = QLabel(label)
        h_lbl.setStyleSheet(
            f"color: {color}; font-size: {_FS['xs']}; font-weight: 700; "
            f"background: transparent; text-transform: uppercase;"
        )
        hdr.addWidget(h_lbl)
        hdr.addStretch()
        lay.addLayout(hdr)

        for ev in events:
            title = (getattr(ev, "title", None) or
                     getattr(ev, "name", None) or str(ev))
            time_str = ""
            start = getattr(ev, "start_time", None) or getattr(ev, "date", None)
            if start:
                try:
                    dt = datetime.fromisoformat(str(start))
                    time_str = dt.strftime("%H:%M") if dt.hour else dt.strftime("%d %b")
                except Exception:
                    time_str = str(start)[:10]

            ev_row = QHBoxLayout()
            ev_row.setSpacing(6)

            dot = QLabel("–")
            dot.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            dot.setFixedWidth(8)
            ev_row.addWidget(dot)

            ev_lbl = QLabel(title)
            ev_lbl.setStyleSheet(
                f"color: {_C['text_mid']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            ev_lbl.setWordWrap(False)
            ev_row.addWidget(ev_lbl, stretch=1)

            if time_str:
                t_lbl = QLabel(time_str)
                t_lbl.setStyleSheet(
                    f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                    f"background: transparent; border: none;"
                )
                ev_row.addWidget(t_lbl)

            lay.addLayout(ev_row)

        lay.addStretch()
        return w


# ══════════════════════════════════════════════════════════════════════════════
# Customize Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _CustomizeDialog(QDialog):
    """
    Lets the user show/hide widgets and drag them up/down to reorder.
    Unavailable widgets (required service not loaded) are shown greyed out.
    """

    def __init__(self, widget_order: list[str], hidden_set: set[str],
                 available_set: set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Dashboard")
        self.setMinimumSize(440, 520)
        self.setStyleSheet(f"""
            QDialog {{
                background: {_C['bg_base']};
            }}
            QLabel {{
                color: {_C['text_hi']};
                background: transparent;
            }}
            QListWidget {{
                background: {_C['bg_card']};
                border: 1px solid {_C['border']};
                border-radius: {_R['base']};
                outline: none;
                color: {_C['text_hi']};
            }}
            QListWidget::item {{
                border-bottom: 1px solid {_C['border_lo']};
                padding: 0;
            }}
            QListWidget::item:selected {{
                background: {_C['bg_hover']};
            }}
            QDialogButtonBox QPushButton {{
                background: {_C['bg_raised']};
                color: {_C['text_hi']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
                padding: 6px 16px;
                font-size: {_FS['sm']};
            }}
            QDialogButtonBox QPushButton:hover {{
                background: {_C['bg_hover']};
                border-color: {_C['border_hi']};
            }}
        """)

        self._available = available_set
        # Build ordered list: available items first (in given order), then
        # any unavailable ones at the bottom
        all_ids = list(widget_order)
        for wid in _WIDGET_CATALOG:
            if wid not in all_ids:
                all_ids.append(wid)
        self._order = all_ids

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # Title
        title = QLabel("Customize Dashboard")
        title.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['xl']}; font-weight: 700;"
        )
        root.addWidget(title)

        sub = QLabel(
            "Check widgets to show them. Use the arrows to reorder. "
            "Greyed items require a plugin that isn't currently loaded."
        )
        sub.setStyleSheet(
            f"color: {_C['text_lo']}; font-size: {_FS['xs']};"
        )
        sub.setWordWrap(True)
        root.addWidget(sub)

        # List + arrow buttons side by side
        list_row = QHBoxLayout()
        list_row.setSpacing(8)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.NoDragDrop)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        list_row.addWidget(self._list, stretch=1)

        arrow_col = QVBoxLayout()
        arrow_col.setSpacing(4)
        arrow_col.addStretch()

        self._up_btn   = _ghost_btn("▲")
        self._down_btn = _ghost_btn("▼")
        self._up_btn.setFixedWidth(36)
        self._down_btn.setFixedWidth(36)
        self._up_btn.clicked.connect(self._move_up)
        self._down_btn.clicked.connect(self._move_down)
        arrow_col.addWidget(self._up_btn)
        arrow_col.addWidget(self._down_btn)
        arrow_col.addStretch()
        list_row.addLayout(arrow_col)

        root.addLayout(list_row, stretch=1)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        # Style the OK button blue
        ok = btns.button(QDialogButtonBox.Ok)
        if ok:
            ok.setStyleSheet(f"""
                QPushButton {{
                    background: {_C['accent']}; color: white;
                    border: none; border-radius: {_R['sm']};
                    padding: 6px 20px; font-weight: 600;
                }}
                QPushButton:hover {{ background: {_C['accent_hi']}; }}
            """)
        root.addWidget(btns)

        self._populate_list(hidden_set)

    def _populate_list(self, hidden_set: set[str]):
        self._list.clear()
        for wid in self._order:
            meta      = _WIDGET_CATALOG.get(wid, {})
            title     = meta.get("title", wid)
            icon      = meta.get("icon", "◆")
            desc      = meta.get("desc", "")
            available = wid in self._available

            item = QListWidgetItem()
            item.setData(Qt.UserRole, wid)

            # Build item widget
            iw = QWidget()
            iw.setStyleSheet("background: transparent;")
            iw.setFixedHeight(50)
            il = QHBoxLayout(iw)
            il.setContentsMargins(8, 4, 8, 4)
            il.setSpacing(10)

            chk = QCheckBox()
            chk.setChecked(wid not in hidden_set and available)
            chk.setEnabled(available)
            chk.setStyleSheet(f"""
                QCheckBox::indicator {{
                    width: 16px; height: 16px;
                    border: 1px solid {_C['border_hi']};
                    border-radius: {_R['xs']};
                    background: {_C['bg_input']};
                }}
                QCheckBox::indicator:checked {{
                    background: {_C['accent']};
                    border-color: {_C['accent']};
                }}
            """)
            il.addWidget(chk)

            text_col = QVBoxLayout()
            text_col.setSpacing(1)

            title_row = QHBoxLayout()
            title_row.setSpacing(6)
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
            title_row.addWidget(icon_lbl)
            title_lbl = QLabel(title)
            title_color = _C["text_hi"] if available else _C["text_dim"]
            title_lbl.setStyleSheet(
                f"color: {title_color}; font-size: {_FS['sm']}; "
                f"font-weight: 600; background: transparent;"
            )
            title_row.addWidget(title_lbl)
            if not available:
                lock = QLabel("(plugin not loaded)")
                lock.setStyleSheet(
                    f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                    f"font-style: italic; background: transparent;"
                )
                title_row.addWidget(lock)
            title_row.addStretch()
            text_col.addLayout(title_row)

            if desc:
                desc_lbl = QLabel(desc)
                desc_lbl.setStyleSheet(
                    f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                    f"background: transparent;"
                )
                text_col.addWidget(desc_lbl)

            il.addLayout(text_col, stretch=1)

            # Store checkbox reference on item for retrieval
            item.setData(Qt.UserRole + 1, chk)

            self._list.addItem(item)
            self._list.setItemWidget(item, iw)
            item.setSizeHint(QSize(0, 52))

    def _move_up(self):
        row = self._list.currentRow()
        if row <= 0:
            return
        item = self._list.takeItem(row)
        self._list.insertItem(row - 1, item)
        self._list.setCurrentRow(row - 1)
        # Re-build widget (takeItem removes the widget)
        self._reattach_item_widget(item)

    def _move_down(self):
        row = self._list.currentRow()
        if row < 0 or row >= self._list.count() - 1:
            return
        item = self._list.takeItem(row)
        self._list.insertItem(row + 1, item)
        self._list.setCurrentRow(row + 1)
        self._reattach_item_widget(item)

    def _reattach_item_widget(self, item: QListWidgetItem):
        """After takeItem/insertItem the itemWidget is gone — rebuild it."""
        wid  = item.data(Qt.UserRole)
        meta = _WIDGET_CATALOG.get(wid, {})
        # Determine current checked state from UserRole+1 (the old checkbox — may be gone)
        # We'll just re-check state from self._get_hidden() during rebuild.
        # Simpler: remember checked state as UserRole+2 bool
        checked  = item.data(Qt.UserRole + 2)  # may be None first time
        available = wid in self._available

        iw = QWidget()
        iw.setStyleSheet("background: transparent;")
        iw.setFixedHeight(50)
        il = QHBoxLayout(iw)
        il.setContentsMargins(8, 4, 8, 4)
        il.setSpacing(10)

        chk = QCheckBox()
        chk.setChecked(bool(checked) if checked is not None else (available and wid not in set()))
        chk.setEnabled(available)
        chk.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {_C['border_hi']};
                border-radius: {_R['xs']};
                background: {_C['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background: {_C['accent']};
                border-color: {_C['accent']};
            }}
        """)
        chk.stateChanged.connect(
            lambda state, i=item: i.setData(Qt.UserRole + 2, state == 2)
        )
        il.addWidget(chk)

        title  = meta.get("title", wid)
        icon   = meta.get("icon", "◆")
        desc   = meta.get("desc", "")

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
        title_row.addWidget(icon_lbl)
        title_lbl = QLabel(title)
        title_color = _C["text_hi"] if available else _C["text_dim"]
        title_lbl.setStyleSheet(
            f"color: {title_color}; font-size: {_FS['sm']}; "
            f"font-weight: 600; background: transparent;"
        )
        title_row.addWidget(title_lbl)
        if not available:
            lock = QLabel("(plugin not loaded)")
            lock.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                f"font-style: italic; background: transparent;"
            )
            title_row.addWidget(lock)
        title_row.addStretch()
        text_col.addLayout(title_row)
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent;"
            )
            text_col.addWidget(desc_lbl)
        il.addLayout(text_col, stretch=1)

        item.setData(Qt.UserRole + 1, chk)
        self._list.setItemWidget(item, iw)
        item.setSizeHint(QSize(0, 52))

    def get_order(self) -> list[str]:
        return [
            self._list.item(i).data(Qt.UserRole)
            for i in range(self._list.count())
        ]

    def get_hidden(self) -> set[str]:
        hidden = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            wid  = item.data(Qt.UserRole)
            iw   = self._list.itemWidget(item)
            if iw:
                chk = iw.findChild(QCheckBox)
                if chk and not chk.isChecked():
                    hidden.add(wid)
            else:
                # fallback from UserRole+2
                checked = item.data(Qt.UserRole + 2)
                if checked is False:
                    hidden.add(wid)
        return hidden


# ══════════════════════════════════════════════════════════════════════════════
# Main Dashboard V2 UI
# ══════════════════════════════════════════════════════════════════════════════

class DashboardV2UI(QWidget):
    """
    Adaptive dashboard — single scrollable page with a 2-column widget grid.
    """
    action_requested = Signal(str, dict)
    customize_clicked = Signal()
    refresh_clicked   = Signal()

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        self.setStyleSheet(f"background: {_C['bg_base']};")
        self.setMinimumSize(400, 300)

        # Widget instances cache
        self._widgets: dict[str, _DashWidget] = {}
        # Layout state
        self._widget_order: list[str] = []
        self._hidden_widgets: set[str] = set()
        self._load_layout()

        # Pending data (populated by refresh_* before grid is built)
        self._pending: dict[str, tuple] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        self._header = self._build_header()
        root.addWidget(self._header)

        # Separator
        root.addWidget(_hline())

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {_C['bg_base']}; border: none; }}
            QScrollBar:vertical {{
                background: {_C['bg_deep']}; width: 6px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {_C['border_hi']}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet(f"background: {_C['bg_base']};")
        self._grid_container_lay = QVBoxLayout(self._grid_container)
        self._grid_container_lay.setContentsMargins(16, 16, 16, 20)
        self._grid_container_lay.setSpacing(0)

        # The actual QGridLayout lives inside the container
        self._grid = QGridLayout()
        self._grid.setSpacing(12)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._grid_container_lay.addLayout(self._grid)
        self._grid_container_lay.addStretch()

        self._scroll.setWidget(self._grid_container)
        root.addWidget(self._scroll, stretch=1)

        # Build initial grid
        self._rebuild_grid()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QFrame:
        hdr = QFrame()
        hdr.setFixedHeight(76)
        hdr.setStyleSheet(f"background: {_C['bg_deep']}; border: none;")

        lay = QVBoxLayout(hdr)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(4)

        # Row 1: branding + buttons
        top = QHBoxLayout()
        top.setSpacing(10)

        # Gold accent dot
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {_C['gold']}; font-size: 10px; background: transparent;")
        top.addWidget(dot)

        title_lbl = QLabel("Dashboard")
        title_lbl.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['xl']}; "
            f"font-weight: 700; background: transparent;"
        )
        top.addWidget(title_lbl)

        top.addStretch()

        self._refresh_btn = _ghost_btn("↻  Refresh")
        self._refresh_btn.clicked.connect(self.refresh_clicked)
        top.addWidget(self._refresh_btn)

        self._customize_btn = _ghost_btn("⚙  Customize")
        self._customize_btn.clicked.connect(self.customize_clicked)
        top.addWidget(self._customize_btn)

        lay.addLayout(top)

        # Row 2: greeting + date + streak
        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        self._greeting_lbl = QLabel("Welcome back!")
        self._greeting_lbl.setStyleSheet(
            f"color: {_C['text_mid']}; font-size: {_FS['base']}; "
            f"background: transparent;"
        )
        bottom.addWidget(self._greeting_lbl)

        # Bullet separator
        sep1 = QLabel("·")
        sep1.setStyleSheet(f"color: {_C['text_dim']}; background: transparent;")
        bottom.addWidget(sep1)

        # Date
        today_str = datetime.now().strftime("%A, %d %B %Y")
        date_lbl = QLabel(today_str)
        date_lbl.setStyleSheet(
            f"color: {_C['text_lo']}; font-size: {_FS['sm']}; "
            f"background: transparent;"
        )
        bottom.addWidget(date_lbl)

        # Streak (hidden initially)
        sep2 = QLabel("·")
        sep2.setStyleSheet(f"color: {_C['text_dim']}; background: transparent;")
        sep2.setVisible(False)
        bottom.addWidget(sep2)

        self._streak_lbl = QLabel()
        self._streak_lbl.setStyleSheet(
            f"color: {_C['success']}; font-size: {_FS['sm']}; "
            f"font-weight: 600; background: transparent;"
        )
        self._streak_lbl.setVisible(False)
        bottom.addWidget(self._streak_lbl)

        self._streak_sep = sep2
        bottom.addStretch()
        lay.addLayout(bottom)

        return hdr

    # ── Grid management ───────────────────────────────────────────────────────

    def _rebuild_grid(self):
        """Clear and re-populate the widget grid from current order/visibility."""
        # Remove all widgets from grid (keep Python refs in self._widgets)
        for w in list(self._widgets.values()):
            self._grid.removeWidget(w)
            w.setVisible(False)
            w.setParent(None)

        # Clear layout items
        while self._grid.count():
            self._grid.takeAt(0)

        # Build visible list
        visible = [
            wid for wid in self._widget_order
            if wid not in self._hidden_widgets
            and self._is_widget_available(wid)
        ]

        row_num = 0
        i = 0
        while i < len(visible):
            wid  = visible[i]
            meta = _WIDGET_CATALOG.get(wid, {})
            w    = self._get_widget(wid)
            w.setVisible(True)

            if meta.get("width") == "full":
                self._grid.addWidget(w, row_num, 0, 1, 2)
                i += 1
            else:
                self._grid.addWidget(w, row_num, 0)
                i += 1
                # Pair with next half widget
                if (i < len(visible) and
                        _WIDGET_CATALOG.get(visible[i], {}).get("width") != "full"):
                    w2 = self._get_widget(visible[i])
                    w2.setVisible(True)
                    self._grid.addWidget(w2, row_num, 1)
                    i += 1

            row_num += 1

        # Re-apply any pending data, then clear the queue
        pending = dict(self._pending)
        self._pending.clear()
        for method_name, args in pending.items():
            try:
                getattr(self, method_name)(*args)
            except Exception as e:
                log.debug(f"[DASH V2] pending flush {method_name}: {e}")

    def _is_widget_available(self, widget_id: str) -> bool:
        """True if the widget's required service is loaded (or has no requirement)."""
        req = _WIDGET_CATALOG.get(widget_id, {}).get("service")
        if not req:
            return True
        return self._ctx.services.try_get(req) is not None

    def _get_available_set(self) -> set[str]:
        return {wid for wid in _WIDGET_CATALOG if self._is_widget_available(wid)}

    def _get_widget(self, widget_id: str) -> _DashWidget:
        if widget_id not in self._widgets:
            w = self._create_widget(widget_id)
            self._widgets[widget_id] = w
        return self._widgets[widget_id]

    def _create_widget(self, widget_id: str) -> _DashWidget:
        creators = {
            "stats_strip":     _StatsStripWidget,
            "active_projects": _ActiveProjectsWidget,
            "quick_actions":   _QuickActionsWidget,
            "recommendations": _RecommendationsWidget,
            "notifications":   _NotificationsWidget,
            "paint_intel":     _PaintIntelWidget,
            "activity_feed":   _ActivityWidget,
            "calendar":        _CalendarWidget,
        }
        cls = creators.get(widget_id)
        if cls:
            w = cls()
        else:
            w = _DashWidget(widget_id)
        w.action_requested.connect(self.action_requested)
        return w

    # ── Layout persistence ────────────────────────────────────────────────────

    def _load_layout(self):
        settings = self._ctx.services.get("settings") if self._ctx else None
        order_raw  = settings.get(_SETTINGS_ORDER_KEY,  "[]")  if settings else "[]"
        hidden_raw = settings.get(_SETTINGS_HIDDEN_KEY, "[]")  if settings else "[]"

        try:
            saved_order = json.loads(order_raw) if isinstance(order_raw, str) else []
        except Exception:
            saved_order = []

        try:
            hidden_list = json.loads(hidden_raw) if isinstance(hidden_raw, str) else []
        except Exception:
            hidden_list = []

        # Merge saved order with defaults (add new widgets at end)
        if saved_order:
            merged = list(saved_order)
            for wid in _DEFAULT_ORDER:
                if wid not in merged:
                    merged.append(wid)
        else:
            merged = list(_DEFAULT_ORDER)

        self._widget_order   = merged
        self._hidden_widgets = set(hidden_list)

    def _save_layout(self):
        settings = self._ctx.services.get("settings") if self._ctx else None
        if not settings:
            return
        settings.set(_SETTINGS_ORDER_KEY,  json.dumps(self._widget_order))
        settings.set(_SETTINGS_HIDDEN_KEY, json.dumps(list(self._hidden_widgets)))

    # ── Customize dialog ──────────────────────────────────────────────────────

    def open_customize_dialog(self):
        dlg = _CustomizeDialog(
            widget_order  = self._widget_order,
            hidden_set    = self._hidden_widgets,
            available_set = self._get_available_set(),
            parent        = self,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        self._widget_order   = dlg.get_order()
        self._hidden_widgets = dlg.get_hidden()
        self._save_layout()
        self._rebuild_grid()

    # ── Public setters ────────────────────────────────────────────────────────

    def set_greeting(self, text: str):
        self._greeting_lbl.setText(text)

    def set_streak(self, n: int):
        if n > 0:
            self._streak_lbl.setText(f"🔥 {n}-day streak")
            self._streak_lbl.setVisible(True)
            self._streak_sep.setVisible(True)
        else:
            self._streak_lbl.setVisible(False)
            self._streak_sep.setVisible(False)

    # ── Refresh methods ───────────────────────────────────────────────────────

    def refresh_stats(self, stats: list):
        w = self._widgets.get("stats_strip")
        if w:
            w.refresh(stats)
        else:
            self._pending["refresh_stats"] = (stats,)

    def refresh_projects(self, cards: list):
        w = self._widgets.get("active_projects")
        if w:
            w.refresh(cards)
        else:
            self._pending["refresh_projects"] = (cards,)

    def refresh_quick_actions(self, actions: list):
        w = self._widgets.get("quick_actions")
        if w:
            w.refresh(actions)
        else:
            self._pending["refresh_quick_actions"] = (actions,)

    def refresh_recommendations(self, recs: list):
        w = self._widgets.get("recommendations")
        if w:
            w.refresh(recs)
        else:
            self._pending["refresh_recommendations"] = (recs,)

    def refresh_notifications(self, notifs: list):
        w = self._widgets.get("notifications")
        if w:
            w.refresh(notifs)
        else:
            self._pending["refresh_notifications"] = (notifs,)

    def refresh_paint_intel(self, low: list, recent: list, brands: dict):
        w = self._widgets.get("paint_intel")
        if w:
            w.refresh(low, recent, brands)
        else:
            self._pending["refresh_paint_intel"] = (low, recent, brands)

    def refresh_activity(self, items: list):
        w = self._widgets.get("activity_feed")
        if w:
            w.refresh(items)
        else:
            self._pending["refresh_activity"] = (items,)

    def refresh_calendar(self, today_events, week_events, milestones, overdue):
        w = self._widgets.get("calendar")
        if w:
            w.refresh(today_events, week_events, milestones, overdue)
        else:
            self._pending["refresh_calendar"] = (
                today_events, week_events, milestones, overdue
            )
