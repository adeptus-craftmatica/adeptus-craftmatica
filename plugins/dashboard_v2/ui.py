"""
Dashboard 2.0 — Premium adaptive UI
═════════════════════════════════════
Layout (no outer scroll — everything fits the viewport):

  Header (fixed)
    ● Dashboard 2.0           [↻ Refresh]
    Good evening, Jon! · Mon 26 May · 🔥 5 days

  Stats Strip (fixed ~120px)
    ⚡ key metrics from all loaded plugins

  QTabWidget (fills remaining height)
  ┌── Overview ──────────────────────────────────────────────┐
  │  [🎨 Add Paint] [🗿 Add Model] ...  ← quick action pills │
  │  ┌─ Recommended Actions ─┬─ Notifications ─────────────┐ │
  │  │  (internal scroll)    │  (internal scroll)          │ │
  │  └───────────────────────┴─────────────────────────────┘ │
  ├── Projects ──────────────────────────────────────────────┤
  │  Active Projects — full width, internal scroll           │
  ├── Activity ──────────────────────────────────────────────┤
  │  ┌─ Activity Feed ───────┬─ Calendar ──────────────────┐ │
  │  │                       │  (if calendar loaded)        │ │
  │  └───────────────────────┴─────────────────────────────┘ │
  └── Paint Intel ───────────────────────────────────────────┘
       (tab only shown when paint_service is loaded)
"""
from __future__ import annotations

import json
import logging
log = logging.getLogger(__name__)

from datetime import date, datetime

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui  import QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QGridLayout, QDialog, QDialogButtonBox,
    QSizePolicy, QTabWidget, QTabBar, QListWidget, QListWidgetItem,
    QAbstractItemView, QCheckBox,
)

# ── Design system ─────────────────────────────────────────────────────────────

_C = {
    "bg_deep":     "#141414",
    "bg_base":     "#1c1c1c",
    "bg_card":     "#1e1e1e",
    "bg_raised":   "#212121",
    "bg_input":    "#2a2a2a",
    "bg_hover":    "#2e2e2e",
    "bg_active":   "#333333",
    "border_lo":   "#282828",
    "border":      "#363636",
    "border_hi":   "#484848",
    "text_hi":     "#f0f0f0",
    "text_mid":    "#d8d8d8",
    "text_lo":     "#909090",
    "text_dim":    "#606060",
    "accent":      "#0078d4",
    "accent_hi":   "#1a8ee8",
    "accent_lo":   "#0f4a7a",
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
    "accent":   _C["accent_text"],
    "success":  _C["success"],
    "warning":  _C["warning"],
    "danger":   _C["danger"],
    "info":     _C["accent_text"],
    "critical": _C["danger"],
}
_SEV_BG: dict[str, str] = {
    "accent":   _C["accent_lo"],
    "success":  _C["success_lo"],
    "warning":  _C["warning_lo"],
    "danger":   _C["danger_lo"],
    "info":     _C["accent_lo"],
    "critical": _C["danger_lo"],
}
_SEV_ICONS: dict[str, str] = {
    "info": "ℹ", "success": "✓", "warning": "⚠",
    "danger": "✕", "critical": "🔴",
}
_PRIORITY_COLOR = {1: _C["danger"], 2: _C["warning"], 3: _C["accent_text"]}

_SETTINGS_ORDER_KEY  = "dashboard_v2.widget_order"
_SETTINGS_HIDDEN_KEY = "dashboard_v2.hidden_widgets"

_SCROLL_SS = f"""
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: transparent; width: 5px; margin: 0;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: {_C['border']}; border-radius: 3px; min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


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
    lbl.setStyleSheet(
        f"color: {fg}; background: {bg}; border-radius: {_R['pill']}; "
        f"padding: 1px 7px; font-size: {_FS['xs']}; font-weight: 600;"
    )
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
        f"font-style: italic; padding: 24px;"
    )
    lbl.setWordWrap(True)
    return lbl


def _relative_time(iso_ts: str) -> str:
    try:
        dt   = datetime.fromisoformat(iso_ts)
        diff = datetime.now() - dt
        s    = int(diff.total_seconds())
        if s < 60:      return "just now"
        if s < 3600:    return f"{s // 60}m ago"
        if s < 86400:   return f"{s // 3600}h ago"
        if s < 172800:  return "yesterday"
        return dt.strftime("%d %b")
    except Exception:
        return ""


def _section_header(text: str, color: str = None) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {color or _C['text_dim']}; font-size: {_FS['xs']}; "
        f"font-weight: 700; letter-spacing: 0.8px; "
        f"padding-bottom: 4px; background: transparent;"
    )
    return lbl


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
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_C["bg_hover"]))
        p.drawRoundedRect(0, 0, w, h, r, r)
        fill_w = max(r * 2, int(w * self._value))
        p.setBrush(QColor(self._color))
        p.drawRoundedRect(0, 0, fill_w, h, r, r)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
# Base dashboard widget card  (with internal scrolling)
# ══════════════════════════════════════════════════════════════════════════════

class _DashWidget(QFrame):
    """
    Card with a styled header and an internally-scrollable content area.
    Pass ``scrollable=False`` for widgets whose content should stretch
    naturally (e.g. stats grid, quick-actions strip).
    """
    action_requested = Signal(str, dict)

    def __init__(self, title: str, icon: str, scrollable: bool = True, parent=None):
        super().__init__(parent)
        self._title_text = title
        self._icon_text  = icon

        self.setObjectName("dashCard")
        self.setStyleSheet(f"""
            QFrame#dashCard {{
                background: {_C['bg_card']};
                border: 1px solid {_C['border']};
                border-radius: {_R['lg']};
            }}
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(38)
        hdr.setObjectName("dashCardHdr")
        hdr.setStyleSheet(f"""
            QFrame#dashCardHdr {{
                background: {_C['bg_raised']};
                border-radius: {_R['lg']} {_R['lg']} 0 0;
                border-bottom: 1px solid {_C['border']};
            }}
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 12, 0)
        hl.setSpacing(8)

        il = QLabel(icon)
        il.setStyleSheet(f"font-size: 13px; background: transparent; border: none;")
        hl.addWidget(il)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['base']}; "
            f"font-weight: 600; background: transparent; border: none;"
        )
        hl.addWidget(self._title_lbl)
        hl.addStretch()

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
            f"background: transparent; border: none;"
        )
        self._count_lbl.setVisible(False)
        hl.addWidget(self._count_lbl)

        root.addWidget(hdr)

        # ── Content ───────────────────────────────────────────────────────────
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(14, 12, 14, 12)
        self._content_lay.setSpacing(6)

        if scrollable:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setStyleSheet(_SCROLL_SS)
            scroll.setWidget(self._content)
            root.addWidget(scroll, stretch=1)
        else:
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
            elif item.layout():
                # recursively delete sub-layouts
                self._clear_layout(item.layout())

    def _clear_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def refresh(self, *args, **kwargs):
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Stats Strip  (fixed-height row of metric cards, no inner scroll)
# ══════════════════════════════════════════════════════════════════════════════

class _StatCard(QFrame):
    def __init__(self, stat, parent=None):
        super().__init__(parent)
        color = _sev_color(stat.color)
        self.setMinimumWidth(110)
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

        bar = QFrame()
        bar.setFixedWidth(3)
        bar.setStyleSheet(
            f"background: {color}; border: none; "
            f"border-radius: {_R['xs']} 0 0 {_R['xs']};"
        )
        outer.addWidget(bar)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(inner)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(5)
        if stat.icon:
            il = QLabel(stat.icon)
            il.setStyleSheet(f"font-size: 16px; background: transparent; border: none;")
            top.addWidget(il)
        vl = QLabel(stat.value)
        vl.setStyleSheet(
            f"color: {color}; font-size: {_FS['2xl']}; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        top.addWidget(vl)
        top.addStretch()
        cl.addLayout(top)

        ll = QLabel(stat.label)
        ll.setStyleSheet(
            f"color: {_C['text_mid']}; font-size: {_FS['sm']}; "
            f"font-weight: 500; background: transparent; border: none;"
        )
        cl.addWidget(ll)

        if stat.subtitle:
            sl = QLabel(stat.subtitle)
            sl.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            sl.setWordWrap(True)
            cl.addWidget(sl)

        outer.addWidget(inner, stretch=1)


class _StatsStripWidget(QFrame):
    """
    Horizontal row of stat cards — sits above the tab widget, always visible.
    Not a _DashWidget subclass; no header bar.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statsStrip")
        self.setStyleSheet(f"""
            QFrame#statsStrip {{
                background: {_C['bg_base']};
                border-bottom: 1px solid {_C['border']};
            }}
        """)
        self.setFixedHeight(106)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 10)
        outer.setSpacing(0)

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)

        outer.addWidget(self._grid_container)

        # Placeholder shown before first refresh
        self._placeholder = _empty_state("Loading statistics…")
        outer.addWidget(self._placeholder)

    def refresh(self, stats: list):
        # Hide placeholder, clear old cards
        self._placeholder.setVisible(False)
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = max(4, len(stats))
        for i, stat in enumerate(stats):
            self._grid.addWidget(_StatCard(stat), 0, i)

        for c in range(cols):
            self._grid.setColumnStretch(c, 1)


# ══════════════════════════════════════════════════════════════════════════════
# Quick Action Pills   (compact horizontal strip, not a full card)
# ══════════════════════════════════════════════════════════════════════════════

class _QuickActionPills(QWidget):
    """
    Compact row of pill buttons — sits above the Rec/Notif pair in Overview.
    """
    action_requested = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self._lay.addStretch()

    def refresh(self, actions: list):
        # Remove old buttons (keep trailing stretch)
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        pills = []
        for action in actions[:7]:
            btn = QPushButton(f"{action.icon}  {action.label}")
            color = _sev_color(action.color)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_C['bg_raised']};
                    color: {_C['text_mid']};
                    border: 1px solid {_C['border']};
                    border-radius: {_R['pill']};
                    padding: 5px 14px;
                    font-size: {_FS['sm']};
                }}
                QPushButton:hover {{
                    background: {_C['bg_hover']};
                    color: {_C['text_hi']};
                    border-color: {color};
                }}
                QPushButton:pressed {{ background: {_C['bg_active']}; }}
            """)
            btn.clicked.connect(
                lambda _, e=action.event, p=action.payload:
                    self.action_requested.emit(e, p)
            )
            pills.append(btn)

        # Insert before the trailing stretch
        for i, btn in enumerate(pills):
            self._lay.insertWidget(i, btn)


# ══════════════════════════════════════════════════════════════════════════════
# Active Projects Widget
# ══════════════════════════════════════════════════════════════════════════════

class _ProjectCard(QFrame):
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

        # Row 1: badge + title + last_active + open
        top = QHBoxLayout()
        top.setSpacing(8)

        if card.plugin_label:
            top.addWidget(_pill_badge(card.plugin_label, _C["accent_text"], _C["accent_lo"]))

        title = QLabel(card.title)
        title.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['base']}; "
            f"font-weight: 600; background: transparent; border: none;"
        )
        top.addWidget(title, stretch=1)

        if card.last_active:
            la = QLabel(card.last_active)
            la.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            top.addWidget(la)

        ob = _small_link_btn(f"{card.action_label} →")
        ob.clicked.connect(
            lambda _, e=card.action_event, p=card.action_payload:
                self.open_requested.emit(e, p)
        )
        top.addWidget(ob)
        lay.addLayout(top)

        if card.subtitle:
            sub = QLabel(card.subtitle)
            sub.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            sub.setWordWrap(True)
            lay.addWidget(sub)

        if card.progress >= 0:
            pct = int(card.progress * 100)
            bar_color = (
                _C["success"] if pct >= 80 else
                _C["accent"]  if pct >= 40 else _C["warning"]
            )
            pb_row = QHBoxLayout()
            pb_row.setSpacing(8)
            pb_row.addWidget(_ProgressBar(card.progress, bar_color, height=5), stretch=1)
            pct_lbl = QLabel(f"{pct}%")
            pct_lbl.setStyleSheet(
                f"color: {bar_color}; font-size: {_FS['xs']}; font-weight: 600; "
                f"background: transparent; border: none;"
            )
            pb_row.addWidget(pct_lbl)
            lay.addLayout(pb_row)

        for line in card.detail_lines[:2]:
            dl = QLabel(f"• {line}")
            dl.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            lay.addWidget(dl)


class _ActiveProjectsWidget(_DashWidget):
    def __init__(self, parent=None):
        super().__init__("Active Projects", "📁", scrollable=True, parent=parent)

    def refresh(self, cards: list):
        self._clear_content()
        self._set_count(len(cards))
        if not cards:
            self._content_lay.addWidget(
                _empty_state("No active projects yet.\nStart a project in any plugin to see it here.")
            )
            return
        for card in cards:
            pc = _ProjectCard(card)
            pc.open_requested.connect(self.action_requested)
            self._content_lay.addWidget(pc)
        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Recommendations Widget
# ══════════════════════════════════════════════════════════════════════════════

class _RecRow(QFrame):
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
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        color = _PRIORITY_COLOR.get(rec.priority, _C["accent_text"])

        # Left accent bar (priority colour)
        bar = QFrame()
        bar.setFixedWidth(3)
        bar.setStyleSheet(
            f"background: {color}; border: none; "
            f"border-radius: {_R['xs']} 0 0 {_R['xs']};"
        )
        outer.addWidget(bar)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        cl = QHBoxLayout(inner)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(10)

        if rec.icon:
            ic = QLabel(rec.icon)
            ic.setStyleSheet(f"font-size: 14px; background: transparent; border: none;")
            ic.setFixedWidth(18)
            cl.addWidget(ic)

        tb = QVBoxLayout()
        tb.setSpacing(1)
        ml = QLabel(f"<b>{rec.action}</b>: {rec.target}")
        ml.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['sm']}; "
            f"background: transparent; border: none;"
        )
        ml.setWordWrap(True)
        tb.addWidget(ml)

        if rec.context:
            ctx = QLabel(rec.context)
            ctx.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            tb.addWidget(ctx)

        cl.addLayout(tb, stretch=1)

        if rec.action_event:
            vb = _small_link_btn(rec.action_label)
            vb.clicked.connect(
                lambda _, e=rec.action_event, p=rec.action_payload:
                    self.action_requested.emit(e, p)
            )
            cl.addWidget(vb)

        outer.addWidget(inner, stretch=1)


class _RecommendationsWidget(_DashWidget):
    def __init__(self, parent=None):
        super().__init__("Recommended Actions", "💡", scrollable=True, parent=parent)

    def refresh(self, recs: list):
        self._clear_content()
        recs = sorted(recs, key=lambda r: r.priority)
        self._set_count(len(recs))
        if not recs:
            self._content_lay.addWidget(_empty_state("All caught up — no pending recommendations."))
            return
        for rec in recs:
            row = _RecRow(rec)
            row.action_requested.connect(self.action_requested)
            self._content_lay.addWidget(row)
        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Notifications Widget
# ══════════════════════════════════════════════════════════════════════════════

class _NotifRow(QFrame):
    action_requested = Signal(str, dict)

    def __init__(self, notif, parent=None):
        super().__init__(parent)
        sev   = notif.severity
        color = _sev_color(sev)

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

        bar = QFrame()
        bar.setFixedWidth(3)
        bar.setStyleSheet(
            f"background: {color}; border: none; "
            f"border-radius: {_R['xs']} 0 0 {_R['xs']};"
        )
        outer.addWidget(bar)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        cl = QHBoxLayout(inner)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(10)

        si = QLabel(_SEV_ICONS.get(sev, "ℹ"))
        si.setStyleSheet(f"color: {color}; font-size: 12px; background: transparent; border: none;")
        si.setFixedWidth(16)
        cl.addWidget(si)

        tb = QVBoxLayout()
        tb.setSpacing(1)
        tl = QLabel(notif.title)
        tl.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['sm']}; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        tl.setWordWrap(True)
        tb.addWidget(tl)

        if notif.body:
            bl = QLabel(notif.body)
            bl.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            bl.setWordWrap(True)
            tb.addWidget(bl)

        cl.addLayout(tb, stretch=1)

        if notif.action_event:
            vb = _small_link_btn(notif.action_label)
            vb.clicked.connect(
                lambda _, e=notif.action_event, p=notif.action_payload:
                    self.action_requested.emit(e, p)
            )
            cl.addWidget(vb)

        outer.addWidget(inner, stretch=1)


class _NotificationsWidget(_DashWidget):
    def __init__(self, parent=None):
        super().__init__("Notifications", "🔔", scrollable=True, parent=parent)

    def refresh(self, notifs: list):
        self._clear_content()
        _order = {"critical": 0, "danger": 1, "warning": 2, "info": 3, "success": 4}
        notifs = sorted(notifs, key=lambda n: _order.get(n.severity, 99))
        self._set_count(len(notifs))
        if not notifs:
            self._content_lay.addWidget(_empty_state("No notifications — everything looks good! ✓"))
            return
        for notif in notifs:
            row = _NotifRow(notif)
            row.action_requested.connect(self.action_requested)
            self._content_lay.addWidget(row)
        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Paint Intelligence Widget
# ══════════════════════════════════════════════════════════════════════════════

class _PaintIntelWidget(_DashWidget):
    def __init__(self, parent=None):
        super().__init__("Paint Intelligence", "🎨", scrollable=True, parent=parent)

    def refresh(self, low: list, recent: list, brands: dict):
        self._clear_content()

        if not low and not recent and not brands:
            self._content_lay.addWidget(
                _empty_state("Paint Tracker not loaded or no paints recorded yet.")
            )
            return

        if low:
            self._content_lay.addWidget(_section_header("Low Stock", _C["warning"]))
            for p in low[:6]:
                qty       = getattr(p, "quantity", -1)
                dot_color = _C["danger"] if qty == 0 else _C["warning"]
                brand     = getattr(p, "brand", "")
                name      = getattr(p, "name", str(p))
                qty_str   = "Empty" if qty == 0 else f"{qty} left"

                row = QHBoxLayout()
                row.setSpacing(8)
                dot = QLabel("●")
                dot.setFixedWidth(10)
                dot.setStyleSheet(f"color: {dot_color}; font-size: 8px; background: transparent; border: none;")
                row.addWidget(dot)
                nl = QLabel(f"{brand} {name}".strip())
                nl.setStyleSheet(f"color: {_C['text_mid']}; font-size: {_FS['xs']}; background: transparent; border: none;")
                row.addWidget(nl, stretch=1)
                ql = QLabel(qty_str)
                ql.setStyleSheet(f"color: {dot_color}; font-size: {_FS['xs']}; font-weight: 600; background: transparent; border: none;")
                row.addWidget(ql)
                self._content_lay.addLayout(row)

            if len(low) > 6:
                ml = QLabel(f"+ {len(low) - 6} more")
                ml.setStyleSheet(f"color: {_C['text_dim']}; font-size: {_FS['xs']}; font-style: italic; background: transparent;")
                self._content_lay.addWidget(ml)

            self._content_lay.addWidget(_hline())

        if brands:
            self._content_lay.addWidget(_section_header("By Brand"))
            total = sum(brands.values()) or 1
            for brand_name, count in sorted(brands.items(), key=lambda x: -x[1])[:6]:
                vl = QVBoxLayout()
                vl.setSpacing(2)
                lr = QHBoxLayout()
                bl = QLabel(brand_name)
                bl.setStyleSheet(f"color: {_C['text_mid']}; font-size: {_FS['xs']}; background: transparent; border: none;")
                lr.addWidget(bl, stretch=1)
                cl = QLabel(str(count))
                cl.setStyleSheet(f"color: {_C['text_lo']}; font-size: {_FS['xs']}; background: transparent; border: none;")
                lr.addWidget(cl)
                vl.addLayout(lr)
                vl.addWidget(_ProgressBar(count / total, _C["accent_text"], height=4))
                self._content_lay.addLayout(vl)
        elif recent:
            self._content_lay.addWidget(_section_header("Recently Added"))
            for p in recent:
                brand = getattr(p, "brand", "")
                name  = getattr(p, "name", str(p))
                rl    = QLabel(f"+ {brand} {name}".strip())
                rl.setStyleSheet(f"color: {_C['text_mid']}; font-size: {_FS['xs']}; background: transparent; border: none;")
                self._content_lay.addWidget(rl)

        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Activity Feed Widget
# ══════════════════════════════════════════════════════════════════════════════

class _ActivityWidget(_DashWidget):
    def __init__(self, parent=None):
        super().__init__("Recent Activity", "📜", scrollable=True, parent=parent)

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

        for item in items[:30]:
            ts  = item.get("timestamp", "")
            day = ts[:10] if ts else ""

            if day and day != current_group:
                current_group = day
                group_label   = (
                    "Today" if day == today_str else
                    "Yesterday" if day == yesterday_str else
                    (datetime.fromisoformat(day).strftime("%d %b")
                     if day else day)
                )
                gl = QLabel(group_label)
                gl.setStyleSheet(
                    f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                    f"font-weight: 700; letter-spacing: 0.5px; "
                    f"padding-top: 8px; background: transparent;"
                )
                self._content_lay.addWidget(gl)

            row = QHBoxLayout()
            row.setSpacing(8)

            icon = QLabel(item.get("icon", "•"))
            icon.setStyleSheet(f"font-size: 12px; background: transparent; border: none;")
            icon.setFixedWidth(18)
            row.addWidget(icon)

            desc = QLabel(item.get("description", ""))
            desc.setStyleSheet(
                f"color: {_C['text_mid']}; font-size: {_FS['xs']}; "
                f"background: transparent; border: none;"
            )
            row.addWidget(desc, stretch=1)

            tstr = _relative_time(ts)
            if tstr:
                tl = QLabel(tstr)
                tl.setStyleSheet(
                    f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                    f"background: transparent; border: none;"
                )
                row.addWidget(tl)

            self._content_lay.addLayout(row)

        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Calendar Widget
# ══════════════════════════════════════════════════════════════════════════════

class _CalendarWidget(_DashWidget):
    def __init__(self, parent=None):
        super().__init__("Today's Agenda", "📅", scrollable=True, parent=parent)

    def refresh(self, today_events, week_events, milestones, overdue):
        self._clear_content()

        sections = []
        if overdue:
            sections.append(("Overdue", overdue[:5], "⚠", _C["danger"]))
        if today_events:
            sections.append(("Today", today_events[:5], "📅", _C["accent_text"]))
        if week_events:
            sections.append(("Upcoming", week_events[:5], "🗓", _C["text_mid"]))
        if milestones:
            sections.append(("Milestones", milestones[:5], "🏆", _C["gold"]))

        if not sections:
            self._content_lay.addWidget(_empty_state("No upcoming events or milestones scheduled."))
            return

        first = True
        for label, events, icon, color in sections:
            if not first:
                self._content_lay.addWidget(_hline())
            first = False

            hdr = QHBoxLayout()
            hdr.setSpacing(5)
            il = QLabel(icon)
            il.setStyleSheet(f"font-size: 11px; background: transparent;")
            hdr.addWidget(il)
            hl = QLabel(label)
            hl.setStyleSheet(
                f"color: {color}; font-size: {_FS['xs']}; font-weight: 700; "
                f"letter-spacing: 0.5px; background: transparent;"
            )
            hdr.addWidget(hl)
            hdr.addStretch()
            self._content_lay.addLayout(hdr)

            for ev in events:
                title    = (getattr(ev, "title", None) or getattr(ev, "name", None) or str(ev))
                start    = getattr(ev, "start_time", None) or getattr(ev, "date", None)
                time_str = ""
                if start:
                    try:
                        dt = datetime.fromisoformat(str(start))
                        time_str = dt.strftime("%H:%M") if dt.hour else dt.strftime("%d %b")
                    except Exception:
                        time_str = str(start)[:10]

                ev_row = QHBoxLayout()
                ev_row.setSpacing(6)
                dot = QLabel("–")
                dot.setStyleSheet(f"color: {_C['text_dim']}; font-size: {_FS['xs']}; background: transparent; border: none;")
                dot.setFixedWidth(8)
                ev_row.addWidget(dot)
                el = QLabel(title)
                el.setStyleSheet(f"color: {_C['text_mid']}; font-size: {_FS['xs']}; background: transparent; border: none;")
                ev_row.addWidget(el, stretch=1)
                if time_str:
                    tl = QLabel(time_str)
                    tl.setStyleSheet(f"color: {_C['text_dim']}; font-size: {_FS['xs']}; background: transparent; border: none;")
                    ev_row.addWidget(tl)
                self._content_lay.addLayout(ev_row)

        self._content_lay.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# Custom tab bar — guarantees full text is never clipped
# ══════════════════════════════════════════════════════════════════════════════

class _WideTabBar(QTabBar):
    """
    QTabBar subclass that overrides tabSizeHint so every tab is always
    wide enough for its complete label.

    Qt's CSS min-width for QTabBar::tab is silently ignored on macOS when
    Qt calculates tab geometry internally — this is the reliable fix.
    """
    _H_PAD = 48   # total horizontal padding reserved around the text

    def tabSizeHint(self, index: int) -> QSize:
        size = super().tabSizeHint(index)
        fm   = self.fontMetrics()
        # horizontalAdvance() measures the ASCII portion accurately;
        # each emoji glyph is typically rendered at ~16–18 px on macOS,
        # so add an extra 20 px per emoji character to avoid under-measurement.
        text    = self.tabText(index)
        n_emoji = sum(1 for ch in text if ord(ch) > 0xFFFF or
                      0x2600 <= ord(ch) <= 0x27BF or
                      0x1F300 <= ord(ch) <= 0x1FAFF)
        needed  = fm.horizontalAdvance(text) + n_emoji * 20 + self._H_PAD
        return QSize(max(size.width(), needed), size.height())


# ══════════════════════════════════════════════════════════════════════════════
# Main Dashboard V2 UI
# ══════════════════════════════════════════════════════════════════════════════

_TAB_STYLE = f"""
    QTabWidget::pane {{
        background: {_C['bg_base']};
        border: none;
    }}
    QTabWidget::tab-bar {{
        alignment: left;
    }}
    QTabBar {{
        background: {_C['bg_card']};
        border-bottom: 1px solid {_C['border']};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {_C['text_lo']};
        border: none;
        border-bottom: 2px solid transparent;
        padding: 9px 16px;
        font-size: {_FS['sm']};
        font-weight: 500;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        color: {_C['text_hi']};
        border-bottom: 2px solid {_C['accent']};
        font-weight: 600;
    }}
    QTabBar::tab:hover:!selected {{
        color: {_C['text_mid']};
        background: {_C['bg_hover']};
    }}
"""


class DashboardV2UI(QWidget):
    """
    Adaptive dashboard — fixed stats strip + tabbed panels.
    No outer scrolling; each tab fills the viewport.
    Widget lists scroll internally.
    """
    action_requested = Signal(str, dict)
    customize_clicked = Signal()
    refresh_clicked   = Signal()

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self.setStyleSheet(f"background: {_C['bg_base']};")
        self.setMinimumSize(400, 300)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────────
        root.addWidget(self._build_header())

        # ── Stats strip (always visible) ──────────────────────────────────────
        self._stats_widget = _StatsStripWidget()
        root.addWidget(self._stats_widget)

        # ── Tab widget ─────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setTabBar(_WideTabBar())
        self._tabs.setStyleSheet(_TAB_STYLE)
        self._tabs.tabBar().setExpanding(False)
        root.addWidget(self._tabs, stretch=1)

        self._build_tabs()

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self) -> QFrame:
        hdr = QFrame()
        hdr.setFixedHeight(68)
        hdr.setStyleSheet(f"background: {_C['bg_card']}; border-bottom: 1px solid {_C['border']};")

        lay = QVBoxLayout(hdr)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.setSpacing(4)

        # Row 1: branding + buttons
        top = QHBoxLayout()
        top.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {_C['gold']}; font-size: 9px; background: transparent;")
        top.addWidget(dot)

        title = QLabel("Dashboard")
        title.setStyleSheet(
            f"color: {_C['text_hi']}; font-size: {_FS['xl']}; "
            f"font-weight: 700; background: transparent;"
        )
        top.addWidget(title)
        top.addStretch()

        self._customize_btn = _ghost_btn("⚙  Customize")
        self._customize_btn.clicked.connect(self.customize_clicked)
        top.addWidget(self._customize_btn)

        self._refresh_btn = _ghost_btn("↻  Refresh")
        self._refresh_btn.clicked.connect(self.refresh_clicked)
        top.addWidget(self._refresh_btn)

        lay.addLayout(top)

        # Row 2: greeting · date · streak
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        self._greeting_lbl = QLabel("Welcome back!")
        self._greeting_lbl.setStyleSheet(
            f"color: {_C['text_mid']}; font-size: {_FS['sm']}; background: transparent;"
        )
        bottom.addWidget(self._greeting_lbl)

        sep1 = QLabel("·")
        sep1.setStyleSheet(f"color: {_C['text_dim']}; background: transparent;")
        bottom.addWidget(sep1)

        date_lbl = QLabel(datetime.now().strftime("%A, %d %B %Y"))
        date_lbl.setStyleSheet(
            f"color: {_C['text_lo']}; font-size: {_FS['sm']}; background: transparent;"
        )
        bottom.addWidget(date_lbl)

        self._streak_sep = QLabel("·")
        self._streak_sep.setStyleSheet(f"color: {_C['text_dim']}; background: transparent;")
        self._streak_sep.setVisible(False)
        bottom.addWidget(self._streak_sep)

        self._streak_lbl = QLabel()
        self._streak_lbl.setStyleSheet(
            f"color: {_C['success']}; font-size: {_FS['sm']}; "
            f"font-weight: 600; background: transparent;"
        )
        self._streak_lbl.setVisible(False)
        bottom.addWidget(self._streak_lbl)

        bottom.addStretch()
        lay.addLayout(bottom)

        return hdr

    # ── Tab construction ───────────────────────────────────────────────────────

    def _build_tabs(self):
        # Tab order:
        #   1. Overview  — action pills + Today's Agenda + Notifications
        #   2. Projects  — active projects list
        #   3. Activity  — activity feed
        #   4. Paint Intel (only if paint_service loaded)
        #   5. Recommendations (always last)

        # Build all tab (widget, label) pairs first so set_tab_visible can re-insert them
        self._all_tabs: list[tuple[str, QWidget]] = []

        overview_tab = self._build_overview_tab()
        self._all_tabs.append(("⚡ Overview", overview_tab))
        self._tabs.addTab(overview_tab, "⚡ Overview")

        projects_tab = self._build_projects_tab()
        self._all_tabs.append(("📁 Projects", projects_tab))
        self._tabs.addTab(projects_tab, "📁 Projects")

        activity_tab = self._build_activity_tab()
        self._all_tabs.append(("📜 Activity", activity_tab))
        self._tabs.addTab(activity_tab, "📜 Activity")

        intel_tab = self._build_intel_tab()
        if intel_tab is not None:
            self._all_tabs.append(("🎨 Paint Intel", intel_tab))
            self._tabs.addTab(intel_tab, "🎨 Paint Intel")

        recs_tab = self._build_recs_tab()
        self._all_tabs.append(("💡 Recommendations", recs_tab))
        self._tabs.addTab(recs_tab, "💡 Recommendations")

    def _build_overview_tab(self) -> QWidget:
        """
        Quick action pills (compact row) above a 2-column
        Today's Agenda (left) + Notifications (right) pair.
        """
        page = QWidget()
        page.setStyleSheet(f"background: {_C['bg_base']};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # Quick-action pill strip
        self._action_pills = _QuickActionPills()
        self._action_pills.action_requested.connect(self.action_requested)
        lay.addWidget(self._action_pills)

        # Today's Agenda + Notifications side by side
        pair = QHBoxLayout()
        pair.setSpacing(12)

        self._calendar_widget = _CalendarWidget()
        self._notif_widget    = _NotificationsWidget()
        self._calendar_widget.action_requested.connect(self.action_requested)
        self._notif_widget.action_requested.connect(self.action_requested)

        pair.addWidget(self._calendar_widget, stretch=1)
        pair.addWidget(self._notif_widget,    stretch=1)
        lay.addLayout(pair, stretch=1)

        return page

    def _build_projects_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {_C['bg_base']};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(0)

        self._projects_widget = _ActiveProjectsWidget()
        self._projects_widget.action_requested.connect(self.action_requested)
        lay.addWidget(self._projects_widget)

        return page

    def _build_activity_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {_C['bg_base']};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(0)

        self._activity_widget = _ActivityWidget()
        self._activity_widget.action_requested.connect(self.action_requested)
        lay.addWidget(self._activity_widget, stretch=1)

        return page

    def _build_intel_tab(self) -> QWidget | None:
        """Only builds the Paint Intel tab if paint_service is available. Returns the page or None."""
        paint_available = (
            self._ctx.services.try_get("paint_service") is not None
            if self._ctx else False
        )
        if not paint_available:
            self._paint_intel_widget = _PaintIntelWidget()  # keep ref for refresh
            return None

        page = QWidget()
        page.setStyleSheet(f"background: {_C['bg_base']};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(0)

        self._paint_intel_widget = _PaintIntelWidget()
        self._paint_intel_widget.action_requested.connect(self.action_requested)
        lay.addWidget(self._paint_intel_widget)

        return page

    def _build_recs_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {_C['bg_base']};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(0)

        self._rec_widget = _RecommendationsWidget()
        self._rec_widget.action_requested.connect(self.action_requested)
        lay.addWidget(self._rec_widget, stretch=1)

        return page

    # ── Public setters ─────────────────────────────────────────────────────────

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

    # ── Refresh methods ────────────────────────────────────────────────────────

    def refresh_stats(self, stats: list):
        self._stats_widget.refresh(stats)

    def refresh_projects(self, cards: list):
        self._projects_widget.refresh(cards)

    def refresh_quick_actions(self, actions: list):
        self._action_pills.refresh(actions)

    def refresh_recommendations(self, recs: list):
        self._rec_widget.refresh(recs)

    def refresh_notifications(self, notifs: list):
        self._notif_widget.refresh(notifs)

    def refresh_paint_intel(self, low: list, recent: list, brands: dict):
        self._paint_intel_widget.refresh(low, recent, brands)

    def refresh_activity(self, items: list):
        self._activity_widget.refresh(items)

    def refresh_calendar(self, today_events, week_events, milestones, overdue):
        self._calendar_widget.refresh(today_events, week_events, milestones, overdue)

    def set_tab_visible(self, label: str, visible: bool):
        """Show or hide a tab by its label text, preserving master order when re-showing."""
        if visible:
            # Check if it's already visible
            for i in range(self._tabs.count()):
                if self._tabs.tabText(i) == label:
                    return  # already present
            # Find the widget in the master list
            target_widget = None
            target_idx_in_all = -1
            for idx, (lbl, wgt) in enumerate(self._all_tabs):
                if lbl == label:
                    target_widget = wgt
                    target_idx_in_all = idx
                    break
            if target_widget is None:
                return
            # Find the insertion position: insert before the first currently-visible
            # tab that comes AFTER this one in the master list
            insert_pos = self._tabs.count()  # default: append
            for idx_all, (lbl_all, _) in enumerate(self._all_tabs):
                if idx_all <= target_idx_in_all:
                    continue
                for tab_i in range(self._tabs.count()):
                    if self._tabs.tabText(tab_i) == lbl_all:
                        insert_pos = tab_i
                        break
                else:
                    continue
                break
            self._tabs.insertTab(insert_pos, target_widget, label)
        else:
            for i in range(self._tabs.count()):
                if self._tabs.tabText(i) == label:
                    self._tabs.removeTab(i)
                    return

    def open_customize_dialog(
        self,
        hidden_tabs: list[str],
        all_actions: list = None,
        hidden_actions: list[str] = None,
        all_stats: list = None,
        hidden_cards: list[str] = None,
        display_name: str = "",
    ) -> dict | None:
        """
        Show the full multi-tab Customize Dashboard dialog.
        Returns a dict with keys hidden_tabs, hidden_actions, hidden_cards, display_name
        on accept, or None on cancel.
        """
        if hidden_tabs is None:
            hidden_tabs = []
        if all_actions is None:
            all_actions = []
        if hidden_actions is None:
            hidden_actions = []
        if all_stats is None:
            all_stats = []
        if hidden_cards is None:
            hidden_cards = []

        hidden_tabs_set    = set(hidden_tabs)
        hidden_actions_set = set(hidden_actions)
        hidden_cards_set   = set(hidden_cards)

        # ── Shared checkbox stylesheet ─────────────────────────────────────────
        _CB_SS = f"""
            QCheckBox {{
                color: {_C['text_hi']};
                font-size: {_FS['base']};
                background: transparent;
                spacing: 8px;
                padding: 4px 0;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {_C['border_hi']};
                border-radius: {_R['xs']};
                background: {_C['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background: {_C['accent']};
                border-color: {_C['accent']};
            }}
            QCheckBox::indicator:disabled {{
                background: {_C['bg_hover']};
                border-color: {_C['border']};
            }}
        """

        dlg = QDialog(self)
        dlg.setWindowTitle("Customize Dashboard")
        dlg.setModal(True)
        dlg.setMinimumWidth(500)
        dlg.setMinimumHeight(520)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: {_C['bg_base']};
                color: {_C['text_hi']};
            }}
            QLabel {{
                color: {_C['text_hi']};
                font-size: {_FS['base']};
                background: transparent;
            }}
            QLineEdit {{
                background: {_C['bg_input']};
                color: {_C['text_hi']};
                border: 1px solid {_C['border_hi']};
                border-radius: {_R['base']};
                padding: 6px 10px;
                font-size: {_FS['base']};
            }}
            QLineEdit:focus {{
                border-color: {_C['accent']};
            }}
        """)

        root_lay = QVBoxLayout(dlg)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── Inner tab widget ──────────────────────────────────────────────────
        inner_tabs = QTabWidget()
        inner_tabs.setTabBar(_WideTabBar())
        inner_tabs.setStyleSheet(_TAB_STYLE)
        inner_tabs.tabBar().setExpanding(False)
        root_lay.addWidget(inner_tabs, stretch=1)

        # helper: build a tab page with the right bg + padding
        def _tab_page() -> tuple[QWidget, QVBoxLayout]:
            page = QWidget()
            page.setStyleSheet(f"background: {_C['bg_base']};")
            lay = QVBoxLayout(page)
            lay.setContentsMargins(16, 14, 16, 14)
            lay.setSpacing(10)
            return page, lay

        # helper: build a scrollable checkbox list
        def _checkbox_scroll_tab(
            items: list,
            id_fn,
            label_fn,
            source_fn,
            hidden_set: set,
        ) -> tuple[QWidget, list[tuple[object, QCheckBox]]]:
            """
            Returns (tab_page_widget, list_of_(item, checkbox)_pairs).
            """
            page, lay = _tab_page()

            if not items:
                lay.addWidget(
                    _empty_state("No items available yet.\nInstall plugins to populate this list.")
                )
                lay.addStretch()
                return page, []

            # Select All / Clear All row
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            sel_all_btn = _ghost_btn("Select All")
            clr_all_btn = _ghost_btn("Clear All")
            btn_row.addWidget(sel_all_btn)
            btn_row.addWidget(clr_all_btn)
            lay.addLayout(btn_row)

            # Scroll area
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setStyleSheet(_SCROLL_SS)

            body = QWidget()
            body.setStyleSheet("background: transparent;")
            body_lay = QVBoxLayout(body)
            body_lay.setContentsMargins(0, 0, 4, 0)
            body_lay.setSpacing(2)

            cb_pairs: list[tuple[object, QCheckBox]] = []
            for item in items:
                row_w = QWidget()
                row_w.setStyleSheet("background: transparent;")
                row_lay = QHBoxLayout(row_w)
                row_lay.setContentsMargins(4, 0, 4, 0)
                row_lay.setSpacing(0)

                cb_text = label_fn(item)
                cb = QCheckBox(cb_text)
                cb.setStyleSheet(_CB_SS)
                cb.setChecked(id_fn(item) not in hidden_set)
                row_lay.addWidget(cb, stretch=1)

                src = source_fn(item)
                if src:
                    src_lbl = QLabel(src)
                    src_lbl.setStyleSheet(
                        f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
                        f"background: transparent; padding-right: 4px;"
                    )
                    row_lay.addWidget(src_lbl)

                body_lay.addWidget(row_w)
                cb_pairs.append((item, cb))

            body_lay.addStretch()
            scroll.setWidget(body)
            lay.addWidget(scroll, stretch=1)

            # Wire select/clear all
            def _set_all(checked: bool):
                for _, cb in cb_pairs:
                    cb.setChecked(checked)

            sel_all_btn.clicked.connect(lambda: _set_all(True))
            clr_all_btn.clicked.connect(lambda: _set_all(False))

            return page, cb_pairs

        # ── Tab 1: Profile ─────────────────────────────────────────────────────
        profile_page, profile_lay = _tab_page()

        name_lbl = QLabel("Display Name")
        name_lbl.setStyleSheet(
            f"color: {_C['text_mid']}; font-size: {_FS['sm']}; font-weight: 600; "
            f"background: transparent;"
        )
        profile_lay.addWidget(name_lbl)

        from PySide6.QtWidgets import QLineEdit
        name_edit = QLineEdit()
        name_edit.setText(display_name)
        name_edit.setPlaceholderText("e.g. Jon")
        profile_lay.addWidget(name_edit)

        name_note = QLabel("Used in the dashboard greeting")
        name_note.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['xs']}; "
            f"font-style: italic; background: transparent;"
        )
        profile_lay.addWidget(name_note)
        profile_lay.addStretch()

        inner_tabs.addTab(profile_page, "👤 Profile")

        # ── Tab 2: Quick Actions ───────────────────────────────────────────────
        def _action_id(a):
            return getattr(a, "event", "") or ""

        def _action_label(a):
            icon  = getattr(a, "icon",  "")
            label = getattr(a, "label", str(a))
            return f"{icon}  {label}" if icon else label

        def _action_source(a):
            return getattr(a, "plugin_id", "") or getattr(a, "source", "") or ""

        actions_page, actions_cb_pairs = _checkbox_scroll_tab(
            items=all_actions,
            id_fn=_action_id,
            label_fn=_action_label,
            source_fn=_action_source,
            hidden_set=hidden_actions_set,
        )
        inner_tabs.addTab(actions_page, "⚡ Quick Actions")

        # ── Tab 3: Stats Cards ─────────────────────────────────────────────────
        def _stat_id(s):
            return getattr(s, "card_id", "") or ""

        def _stat_label(s):
            icon  = getattr(s, "icon",  "")
            label = getattr(s, "label", str(s))
            value = getattr(s, "value", "")
            parts = [p for p in [icon, label, value] if p]
            if icon and label:
                return f"{icon}  {label}  {value}".strip() if value else f"{icon}  {label}"
            return "  ".join(parts) if parts else str(s)

        def _stat_source(s):
            return getattr(s, "plugin_id", "") or getattr(s, "source", "") or ""

        stats_page, stats_cb_pairs = _checkbox_scroll_tab(
            items=all_stats,
            id_fn=_stat_id,
            label_fn=_stat_label,
            source_fn=_stat_source,
            hidden_set=hidden_cards_set,
        )
        inner_tabs.addTab(stats_page, "📊 Stats Cards")

        # ── Tab 4: Tabs ────────────────────────────────────────────────────────
        tabs_page, tabs_lay = _tab_page()

        heading = QLabel("Choose which tabs to show:")
        heading.setStyleSheet(
            f"color: {_C['text_mid']}; font-size: {_FS['sm']}; "
            f"background: transparent; padding-bottom: 4px;"
        )
        tabs_lay.addWidget(heading)

        tab_checkboxes: list[tuple[str, QCheckBox]] = []
        for (lbl, _) in self._all_tabs:
            cb = QCheckBox(lbl)
            cb.setStyleSheet(_CB_SS)
            if lbl == "⚡ Overview":
                cb.setChecked(True)
                cb.setEnabled(False)
            else:
                cb.setChecked(lbl not in hidden_tabs_set)
            tabs_lay.addWidget(cb)
            tab_checkboxes.append((lbl, cb))

        tabs_lay.addStretch()
        inner_tabs.addTab(tabs_page, "🗂 Tabs")

        # ── Bottom button row ─────────────────────────────────────────────────
        btn_frame = QFrame()
        btn_frame.setStyleSheet(
            f"background: {_C['bg_card']}; border-top: 1px solid {_C['border']};"
        )
        btn_frame_lay = QHBoxLayout(btn_frame)
        btn_frame_lay.setContentsMargins(16, 10, 16, 10)
        btn_frame_lay.setSpacing(8)
        btn_frame_lay.addStretch()

        cancel_btn = _ghost_btn("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        btn_frame_lay.addWidget(cancel_btn)

        save_btn = QPushButton("Save Changes")
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_C['accent']};
                color: {_C['text_hi']};
                border: none;
                border-radius: {_R['sm']};
                padding: 7px 20px;
                font-size: {_FS['base']};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {_C['accent_hi']};
            }}
            QPushButton:pressed {{
                background: {_C['accent_lo']};
            }}
        """)
        save_btn.clicked.connect(dlg.accept)
        btn_frame_lay.addWidget(save_btn)

        root_lay.addWidget(btn_frame)

        # ── Execute dialog ────────────────────────────────────────────────────
        if dlg.exec() != QDialog.Accepted:
            return None

        new_hidden_tabs    = [lbl for lbl, cb in tab_checkboxes if not cb.isChecked()]
        new_hidden_actions = [_action_id(item) for item, cb in actions_cb_pairs if not cb.isChecked()]
        new_hidden_cards   = [_stat_id(item) for item, cb in stats_cb_pairs if not cb.isChecked()]

        return {
            "hidden_tabs":    new_hidden_tabs,
            "hidden_actions": new_hidden_actions,
            "hidden_cards":   new_hidden_cards,
            "display_name":   name_edit.text(),
        }
