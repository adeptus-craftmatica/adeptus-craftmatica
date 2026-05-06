"""
Calendar Intelligence Widget
Dashboard Overview panel — "What matters right now?"

Three sections rendered as a single cohesive card:
  ┌─────────────────────────────────────────────────────┐
  │  📅  TODAY — Tuesday, April 21        View Calendar →│
  ├─────────────────────────────────────────────────────┤
  │  🎨  Painting Session                  All day       │
  │  ⚔   Battle Night                      19:00         │
  ├─────────────────────────────────────────────────────┤
  │  THIS WEEK                                           │
  ├─────────────────────────────────────────────────────┤
  │  Wed  🏆  Tournament Prep              Apr 23        │
  │  Fri  🎮  Game Night                   Apr 25        │
  ├─────────────────────────────────────────────────────┤
  │  ACTIVE MILESTONES                                   │
  ├─────────────────────────────────────────────────────┤
  │  🏆  AdeptiCon                         17 days       │
  │  ⏰  Army Completion Goal              42 days       │
  └─────────────────────────────────────────────────────┘

All event rows navigate to the Calendar tab on click.
Colors are fully resolved through the active application theme.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QSizePolicy,
)

_DAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS_SHORT = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


# ── Theme resolution ───────────────────────────────────────────────────────────

def _tok(ctx) -> dict:
    tm = ctx.services.get("theme_manager") if ctx else None
    def t(name, fb):
        return (tm.token(name) or fb) if tm else fb
    return {
        "bg_raised": t("bg_raised", "#1e1e1e"),
        "card_bg":   t("card_bg",   "#1a1a1a"),
        "border":    t("border",    "#2a2a2a"),
        "text_hi":   t("text_hi",   "#e8e8e8"),
        "text_mid":  t("text_mid",  "#b0b0b0"),
        "text_lo":   t("text_lo",   "#808080"),
        "accent":    t("accent",    "#0078d4"),
        "danger":    t("danger",    "#c62828"),
        "success":   t("success",   "#2e7d32"),
        "warning":   t("warning",   "#e07820"),
    }

def _ev_color(ev, tok: dict) -> str:
    """Resolve event colour through the theme, falling back to the model's
    category_color() hex only when the token is absent from the tok dict."""
    token_name = ev.category_token()
    return tok.get(token_name) or ev.category_color()


# ── Shared UI helpers ──────────────────────────────────────────────────────────

def _divider(tok: dict) -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {tok['border']}; border: none;")
    return line


def _section_header(text: str, tok: dict) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 9px; font-weight: 700; color: {tok['text_lo']}; "
        f"letter-spacing: 1px; padding: 6px 12px 4px 12px; background: transparent;"
    )
    return lbl


def _format_date_short(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
        return f"{_MONTHS_SHORT[d.month - 1]} {d.day}"
    except (ValueError, TypeError):
        return iso


# ── CalendarIntelligenceWidget ─────────────────────────────────────────────────

class CalendarIntelligenceWidget(QWidget):
    """
    Composite dashboard card: Today's Sessions + This Week + Active Milestones.

    Call ``refresh(today, week, milestones)`` with lists of CalendarEvent objects.
    Every interactive element emits ``action_requested("dashboard_navigate",
    {"plugin_id": "calendar"})`` so the main window switches to the Calendar tab.
    """

    action_requested = Signal(str, dict)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet("background: transparent;")

        tok = _tok(context)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Outer card ────────────────────────────────────────────────────────
        self._card = QFrame()
        self._card.setObjectName("calIntelCard")
        self._update_card_style(tok)

        self._card_layout = QVBoxLayout(self._card)
        self._card_layout.setContentsMargins(0, 0, 0, 8)
        self._card_layout.setSpacing(0)

        # ── OVERDUE section (hidden until populated — floats above TODAY) ────────
        self._overdue_section = QWidget()
        self._overdue_section.setStyleSheet("background: transparent;")
        self._overdue_section_layout = QVBoxLayout(self._overdue_section)
        self._overdue_section_layout.setContentsMargins(0, 0, 0, 0)
        self._overdue_section_layout.setSpacing(0)
        self._card_layout.addWidget(self._overdue_section)
        self._overdue_section.hide()

        # ── TODAY header ──────────────────────────────────────────────────────
        self._today_header = self._build_today_header(tok)
        self._card_layout.addWidget(self._today_header)
        self._card_layout.addWidget(_divider(tok))

        # ── TODAY rows placeholder ─────────────────────────────────────────────
        self._today_rows = QWidget()
        self._today_rows.setStyleSheet("background: transparent;")
        self._today_rows_layout = QVBoxLayout(self._today_rows)
        self._today_rows_layout.setContentsMargins(0, 4, 0, 4)
        self._today_rows_layout.setSpacing(0)
        self._card_layout.addWidget(self._today_rows)

        # ── THIS WEEK section (hidden until populated) ────────────────────────
        self._week_section = QWidget()
        self._week_section.setStyleSheet("background: transparent;")
        self._week_section_layout = QVBoxLayout(self._week_section)
        self._week_section_layout.setContentsMargins(0, 0, 0, 0)
        self._week_section_layout.setSpacing(0)
        self._card_layout.addWidget(self._week_section)
        self._week_section.hide()

        # ── MILESTONES section (hidden until populated) ───────────────────────
        self._milestone_section = QWidget()
        self._milestone_section.setStyleSheet("background: transparent;")
        self._milestone_section_layout = QVBoxLayout(self._milestone_section)
        self._milestone_section_layout.setContentsMargins(0, 0, 0, 0)
        self._milestone_section_layout.setSpacing(0)
        self._card_layout.addWidget(self._milestone_section)
        self._milestone_section.hide()

        outer.addWidget(self._card)

        # Initial empty state
        self._show_today_empty(tok)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(
        self,
        today: list,
        week: list,
        milestones: list,
        overdue: list | None = None,
    ) -> None:
        """Rebuild all sections with fresh data.

        ``overdue`` is an optional list of CalendarEvent objects whose date
        has passed and which are not yet completed — shown as an ⚠ OVERDUE
        banner above today's agenda.
        """
        tok = _tok(self._ctx)
        self._update_card_style(tok)
        self._rebuild_overdue(overdue or [], tok)
        self._refresh_today_header(tok)
        self._rebuild_today(today, tok)
        self._rebuild_week(week, tok)
        self._rebuild_milestones(milestones, tok)

    # ── Internal: TODAY ───────────────────────────────────────────────────────

    def _build_today_header(self, tok: dict) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        hrow = QHBoxLayout(w)
        hrow.setContentsMargins(12, 8, 12, 6)
        hrow.setSpacing(6)

        icon_lbl = QLabel("📅")
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
        hrow.addWidget(icon_lbl)

        self._today_date_lbl = QLabel(self._today_label())
        self._today_date_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {tok['text_hi']}; "
            f"background: transparent;"
        )
        hrow.addWidget(self._today_date_lbl, stretch=1)

        link = QLabel("View Calendar →")
        link.setStyleSheet(
            f"font-size: 10px; color: {tok['accent']}; "
            f"background: transparent; text-decoration: underline;"
        )
        link.setCursor(Qt.PointingHandCursor)
        link.mousePressEvent = lambda _: self._navigate()
        hrow.addWidget(link)

        return w

    def _refresh_today_header(self, tok: dict) -> None:
        self._today_date_lbl.setText(self._today_label())
        self._today_date_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {tok['text_hi']}; "
            f"background: transparent;"
        )

    def _today_label(self) -> str:
        d = date.today()
        return f"{_DAYS_SHORT[d.weekday()]}, {_MONTHS_SHORT[d.month - 1]} {d.day}"

    def _rebuild_today(self, events: list, tok: dict) -> None:
        _clear_widget(self._today_rows_layout)

        if not events:
            self._show_today_empty(tok)
            return

        sorted_ev = sorted(events, key=lambda e: (e.completed, e.time_start or "99:99"))
        for ev in sorted_ev[:5]:
            self._today_rows_layout.addWidget(self._make_event_row(ev, tok, show_date=False))

        if len(events) > 5:
            more = QLabel(f"  +{len(events) - 5} more today…")
            more.setStyleSheet(
                f"font-size: 10px; color: {tok['text_lo']}; "
                f"padding: 2px 12px 4px 12px; background: transparent;"
            )
            self._today_rows_layout.addWidget(more)

    def _show_today_empty(self, tok: dict) -> None:
        _clear_widget(self._today_rows_layout)

        empty = QLabel("No sessions scheduled today")
        empty.setAlignment(Qt.AlignCenter)
        empty.setStyleSheet(
            f"font-size: 11px; color: {tok['text_lo']}; "
            f"padding: 10px 0 4px 0; background: transparent;"
        )
        self._today_rows_layout.addWidget(empty)

        sched = QLabel("Schedule a session →")
        sched.setAlignment(Qt.AlignCenter)
        sched.setStyleSheet(
            f"font-size: 10px; color: {tok['accent']}; "
            f"background: transparent; text-decoration: underline; padding-bottom: 8px;"
        )
        sched.setCursor(Qt.PointingHandCursor)
        sched.mousePressEvent = lambda _: self._navigate()
        self._today_rows_layout.addWidget(sched)

    # ── Internal: OVERDUE ─────────────────────────────────────────────────────

    def _rebuild_overdue(self, events: list, tok: dict) -> None:
        _clear_widget(self._overdue_section_layout)

        if not events:
            self._overdue_section.hide()
            return

        # Danger-tinted section header
        hdr = QLabel("⚠  OVERDUE")
        hdr.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {tok['danger']}; "
            f"letter-spacing: 1px; padding: 6px 12px 4px 12px; background: transparent;"
        )
        self._overdue_section_layout.addWidget(hdr)

        for ev in events[:3]:
            row = self._make_overdue_row(ev, tok)
            self._overdue_section_layout.addWidget(row)

        if len(events) > 3:
            more = QLabel(f"  +{len(events) - 3} more overdue…")
            more.setStyleSheet(
                f"font-size: 10px; color: {tok['danger']}; "
                f"padding: 2px 12px 4px 12px; background: transparent;"
            )
            self._overdue_section_layout.addWidget(more)

        self._overdue_section_layout.addWidget(_divider(tok))
        self._overdue_section.show()

    def _make_overdue_row(self, ev, tok: dict) -> QFrame:
        """Compact danger-tinted row for an overdue event."""
        row = QFrame()
        row.setObjectName("calOverdueRow")
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.setMinimumHeight(34)
        row.setCursor(Qt.PointingHandCursor)
        row.setStyleSheet(f"""
            QFrame#calOverdueRow {{
                background: {tok['danger']}11;
                border: none;
                border-left: 3px solid {tok['danger']};
            }}
            QFrame#calOverdueRow:hover {{
                background: {tok['danger']}22;
            }}
        """)
        row.mousePressEvent = lambda _e: self._navigate()

        hlay = QHBoxLayout(row)
        hlay.setContentsMargins(10, 0, 12, 0)
        hlay.setSpacing(6)

        icon_lbl = QLabel(ev.icon())
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
        hlay.addWidget(icon_lbl)

        title_lbl = QLabel(ev.title)
        title_lbl.setStyleSheet(
            f"font-size: 12px; color: {tok['text_hi']}; background: transparent;"
        )
        title_lbl.setTextFormat(Qt.PlainText)
        hlay.addWidget(title_lbl, stretch=1)

        if ev.event_date:
            date_lbl = QLabel(_format_date_short(ev.event_date))
            date_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            date_lbl.setStyleSheet(
                f"font-size: 10px; color: {tok['danger']}; background: transparent;"
            )
            hlay.addWidget(date_lbl)

        return row

    # ── Internal: THIS WEEK ───────────────────────────────────────────────────

    def _rebuild_week(self, events: list, tok: dict) -> None:
        _clear_widget(self._week_section_layout)

        if not events:
            self._week_section.hide()
            return

        self._week_section_layout.addWidget(_divider(tok))
        self._week_section_layout.addWidget(_section_header("THIS WEEK", tok))

        # Group by date, show up to 5 events
        shown = 0
        last_date = None
        for ev in events[:6]:
            if shown >= 5:
                break
            if ev.event_date != last_date:
                last_date = ev.event_date
            self._week_section_layout.addWidget(
                self._make_event_row(ev, tok, show_date=True)
            )
            shown += 1

        if len(events) > 5:
            more = QLabel(f"  +{len(events) - 5} more this week…")
            more.setStyleSheet(
                f"font-size: 10px; color: {tok['text_lo']}; "
                f"padding: 2px 12px 4px 12px; background: transparent;"
            )
            self._week_section_layout.addWidget(more)

        self._week_section.show()

    # ── Internal: MILESTONES ──────────────────────────────────────────────────

    def _rebuild_milestones(self, milestones: list, tok: dict) -> None:
        _clear_widget(self._milestone_section_layout)

        if not milestones:
            self._milestone_section.hide()
            return

        self._milestone_section_layout.addWidget(_divider(tok))
        self._milestone_section_layout.addWidget(_section_header("ACTIVE MILESTONES", tok))

        for ms in milestones[:4]:
            self._milestone_section_layout.addWidget(
                self._make_milestone_row(ms, tok)
            )

        self._milestone_section.show()

    # ── Row builders ──────────────────────────────────────────────────────────

    def _make_event_row(self, ev, tok: dict, show_date: bool = False) -> QFrame:
        row = QFrame()
        row.setObjectName("calIntelRow")
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.setMinimumHeight(36)
        row.setCursor(Qt.PointingHandCursor)
        row.setStyleSheet(f"""
            QFrame#calIntelRow {{
                background: transparent; border: none;
            }}
            QFrame#calIntelRow:hover {{
                background: {tok['bg_raised']};
            }}
        """)
        row.mousePressEvent = lambda _e: self._navigate()

        hlay = QHBoxLayout(row)
        hlay.setContentsMargins(0, 0, 12, 0)
        hlay.setSpacing(0)

        # Left stripe — theme-resolved category colour
        color = _ev_color(ev, tok)
        stripe = QFrame()
        stripe.setFixedWidth(3)
        stripe.setStyleSheet(f"background: {color}; border: none;")
        hlay.addWidget(stripe)

        hlay.addSpacing(10)

        # Icon
        icon_lbl = QLabel(ev.icon())
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
        hlay.addWidget(icon_lbl)

        hlay.addSpacing(6)

        # Title
        extra_css = "text-decoration: line-through;" if ev.completed else ""
        title_color = tok["text_lo"] if ev.completed else tok["text_hi"]
        title_lbl = QLabel(ev.title)
        title_lbl.setStyleSheet(
            f"font-size: 12px; color: {title_color}; "
            f"background: transparent; {extra_css}"
        )
        title_lbl.setTextFormat(Qt.PlainText)
        hlay.addWidget(title_lbl, stretch=1)

        # Right side: date badge OR time
        if show_date and ev.event_date:
            right_text = _format_date_short(ev.event_date)
        else:
            right_text = ev.display_time() if ev.time_start else ""

        if right_text:
            right_lbl = QLabel(right_text)
            right_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            right_lbl.setStyleSheet(
                f"font-size: 10px; color: {tok['text_lo']}; background: transparent;"
            )
            hlay.addWidget(right_lbl)

        return row

    def _make_milestone_row(self, ms, tok: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("calMilestoneRow")
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.setMinimumHeight(36)
        row.setCursor(Qt.PointingHandCursor)
        row.setStyleSheet(f"""
            QFrame#calMilestoneRow {{
                background: transparent; border: none;
            }}
            QFrame#calMilestoneRow:hover {{
                background: {tok['bg_raised']};
            }}
        """)
        row.mousePressEvent = lambda _e: self._navigate()

        hlay = QHBoxLayout(row)
        hlay.setContentsMargins(0, 0, 12, 0)
        hlay.setSpacing(0)

        # Accent stripe for milestones
        color = _ev_color(ms, tok)
        stripe = QFrame()
        stripe.setFixedWidth(3)
        stripe.setStyleSheet(f"background: {color}; border: none;")
        hlay.addWidget(stripe)

        hlay.addSpacing(10)

        icon_lbl = QLabel(ms.icon())
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
        hlay.addWidget(icon_lbl)

        hlay.addSpacing(6)

        title_lbl = QLabel(ms.title)
        title_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {tok['text_hi']}; "
            f"background: transparent;"
        )
        title_lbl.setTextFormat(Qt.PlainText)
        hlay.addWidget(title_lbl, stretch=1)

        # Countdown badge
        days = ms.days_until()
        if days is not None:
            countdown_text = ms.display_days_until()
            badge_bg   = f"{color}22"
            badge_lbl  = QLabel(countdown_text)
            badge_lbl.setAlignment(Qt.AlignCenter)
            badge_lbl.setStyleSheet(f"""
                QLabel {{
                    background: {badge_bg};
                    color: {color};
                    border: 1px solid {color}55;
                    border-radius: 8px;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 1px 8px;
                }}
            """)
            hlay.addWidget(badge_lbl)

        return row

    # ── Style helpers ─────────────────────────────────────────────────────────

    def _update_card_style(self, tok: dict) -> None:
        self._card.setStyleSheet(f"""
            QFrame#calIntelCard {{
                background: {tok['card_bg']};
                border: 1px solid {tok['border']};
                border-radius: 6px;
            }}
        """)

    def _navigate(self):
        self.action_requested.emit("dashboard_navigate", {"plugin_id": "calendar"})


# ── Utility ────────────────────────────────────────────────────────────────────

def _clear_widget(layout) -> None:
    """Remove and destroy all children of a layout."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_widget(item.layout())
