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
        background: {_C['bg_deep']}; width: 5px; margin: 0;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: {_C['border_hi']}; border-radius: 3px; min-height: 20px;
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
                border-bottom: 1px solid {_C['border_lo']};
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
                background: {_C['bg_deep']};
                border-bottom: 1px solid {_C['border_lo']};
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
        background: {_C['bg_deep']};
        border-bottom: 1px solid {_C['border_lo']};
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
        hdr.setStyleSheet(f"background: {_C['bg_deep']}; border: none;")

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
        self._tabs.addTab(self._build_overview_tab(),      "⚡ Overview")
        self._tabs.addTab(self._build_projects_tab(),      "📁 Projects")
        self._tabs.addTab(self._build_activity_tab(),      "📜 Activity")
        self._build_intel_tab()                            # conditional
        self._tabs.addTab(self._build_recs_tab(),          "💡 Recommendations")

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

    def _build_intel_tab(self):
        """Only adds the Paint Intel tab if paint_service is available."""
        paint_available = (
            self._ctx.services.try_get("paint_service") is not None
            if self._ctx else False
        )
        if not paint_available:
            self._paint_intel_widget = _PaintIntelWidget()  # keep ref for refresh
            return

        page = QWidget()
        page.setStyleSheet(f"background: {_C['bg_base']};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(0)

        self._paint_intel_widget = _PaintIntelWidget()
        self._paint_intel_widget.action_requested.connect(self.action_requested)
        lay.addWidget(self._paint_intel_widget)

        self._tabs.addTab(page, "🎨 Paint Intel")

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

    def open_customize_dialog(self):
        """Reserved for future tab-visibility customisation."""
        pass
