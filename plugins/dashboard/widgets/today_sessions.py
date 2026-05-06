"""
Today's Sessions widget — shown on the Dashboard Overview tab.

Displays today's calendar events as compact clickable rows.
Clicking any row or the header link emits dashboard_navigate → Calendar.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QSizePolicy,
)


# ── Theme helper ───────────────────────────────────────────────────────────────

def _tok(ctx) -> dict:
    tm = ctx.services.get("theme_manager") if ctx else None
    def t(name, fb):
        return (tm.token(name) or fb) if tm else fb
    return {
        "bg_raised":   t("bg_raised",   "#212121"),
        "card_bg":     t("card_bg",     "#1e1e1e"),
        "border":      t("border",      "#363636"),
        "text_hi":     t("text_hi",     "#f0f0f0"),
        "text_lo":     t("text_lo",     "#909090"),
        "accent":      t("accent",      "#0078d4"),
        "radius_base": t("radius_base", "6"),
        "radius_xs":   t("radius_xs",   "3"),
    }


# ── Widget ─────────────────────────────────────────────────────────────────────

class TodaySessionsWidget(QWidget):
    """
    Compact card listing today's hobby sessions.

    Emits action_requested("dashboard_navigate", {"plugin_id": "calendar"})
    when the header link or any event row is clicked.
    """

    action_requested = Signal(str, dict)   # (event_name, payload)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet("background: transparent;")

        tok = _tok(context)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Outer card frame ──────────────────────────────────────────────────
        self._card = QFrame()
        self._card.setObjectName("todaySessionsCard")
        self._card.setStyleSheet(f"""
            QFrame#todaySessionsCard {{
                background: {tok['card_bg']};
                border: 1px solid {tok['border']};
                border-radius: {tok['radius_base']}px;
            }}
        """)
        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(0, 0, 0, 6)
        card_lay.setSpacing(0)

        # ── Header row ────────────────────────────────────────────────────────
        hdr_widget = QWidget()
        hdr_widget.setStyleSheet("background: transparent;")
        hrow = QHBoxLayout(hdr_widget)
        hrow.setContentsMargins(12, 8, 12, 6)
        hrow.setSpacing(6)

        icon_lbl = QLabel("📅")
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
        hrow.addWidget(icon_lbl)

        section_lbl = QLabel("TODAY'S SESSIONS")
        section_lbl.setObjectName("dashSectionLabel")
        hrow.addWidget(section_lbl, stretch=1)

        self._view_link = QLabel("View Calendar →")
        self._view_link.setStyleSheet(
            f"font-size: 10px; color: {tok['accent']}; "
            f"background: transparent; text-decoration: underline;"
        )
        self._view_link.setCursor(Qt.PointingHandCursor)
        self._view_link.mousePressEvent = lambda _: self._navigate()
        hrow.addWidget(self._view_link)

        card_lay.addWidget(hdr_widget)

        # Thin divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {tok['border']}; border: none;")
        card_lay.addWidget(div)

        # ── Rows area ─────────────────────────────────────────────────────────
        self._rows_widget = QWidget()
        self._rows_widget.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 4, 0, 0)
        self._rows_layout.setSpacing(0)
        card_lay.addWidget(self._rows_widget)

        outer.addWidget(self._card)

        # Initial empty state
        self._show_empty(tok)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, events: list) -> None:
        """Replace the event rows.  Pass an empty list for the 'no sessions' state."""
        # Clear old rows
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tok = _tok(self._ctx)

        # Re-apply card border in case theme changed
        self._card.setStyleSheet(f"""
            QFrame#todaySessionsCard {{
                background: {tok['card_bg']};
                border: 1px solid {tok['border']};
                border-radius: {tok['radius_base']}px;
            }}
        """)
        self._view_link.setStyleSheet(
            f"font-size: 10px; color: {tok['accent']}; "
            f"background: transparent; text-decoration: underline;"
        )

        if not events:
            self._show_empty(tok)
            return

        # Sort: incomplete first, then by time
        sorted_events = sorted(events, key=lambda e: (e.completed, e.time_start or "99:99"))

        for ev in sorted_events[:5]:
            self._rows_layout.addWidget(self._make_row(ev, tok))

        if len(events) > 5:
            more_lbl = QLabel(f"  +{len(events) - 5} more…")
            more_lbl.setStyleSheet(
                f"font-size: 10px; color: {tok['text_lo']}; "
                f"padding: 2px 12px 4px 12px; background: transparent;"
            )
            self._rows_layout.addWidget(more_lbl)

    # ── Private builders ──────────────────────────────────────────────────────

    def _navigate(self):
        self.action_requested.emit("dashboard_navigate", {"plugin_id": "calendar"})

    def _show_empty(self, tok: dict) -> None:
        empty_lbl = QLabel("No sessions scheduled today")
        empty_lbl.setAlignment(Qt.AlignCenter)
        empty_lbl.setStyleSheet(
            f"font-size: 11px; color: {tok['text_lo']}; "
            f"padding: 10px 0 4px 0; background: transparent;"
        )
        self._rows_layout.addWidget(empty_lbl)

        sched_lbl = QLabel("Schedule a session →")
        sched_lbl.setAlignment(Qt.AlignCenter)
        sched_lbl.setStyleSheet(
            f"font-size: 10px; color: {tok['accent']}; "
            f"background: transparent; text-decoration: underline; padding-bottom: 6px;"
        )
        sched_lbl.setCursor(Qt.PointingHandCursor)
        sched_lbl.mousePressEvent = lambda _: self._navigate()
        self._rows_layout.addWidget(sched_lbl)

    def _make_row(self, ev, tok: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("todaySessionRow")
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.setMinimumHeight(38)
        row.setCursor(Qt.PointingHandCursor)
        row.setStyleSheet(f"""
            QFrame#todaySessionRow {{
                background: transparent;
                border: none;
            }}
            QFrame#todaySessionRow:hover {{
                background: {tok['bg_raised']};
            }}
        """)
        # Entire row navigates to Calendar
        row.mousePressEvent = lambda _e, _ev=ev: self._navigate()

        hlay = QHBoxLayout(row)
        hlay.setContentsMargins(0, 0, 12, 0)
        hlay.setSpacing(0)

        # Left colour stripe
        stripe = QFrame()
        stripe.setFixedWidth(3)
        stripe.setStyleSheet(f"background: {ev.color()}; border: none;")
        hlay.addWidget(stripe)

        hlay.addSpacing(10)

        # Icon
        icon_lbl = QLabel(ev.icon())
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
        hlay.addWidget(icon_lbl)

        hlay.addSpacing(6)

        # Title (strikethrough if completed)
        extra = "text-decoration: line-through;" if ev.completed else ""
        title_lbl = QLabel(ev.title)
        title_lbl.setStyleSheet(
            f"font-size: 12px; color: {tok['text_hi']}; "
            f"background: transparent; {extra}"
        )
        title_lbl.setTextFormat(Qt.PlainText)
        hlay.addWidget(title_lbl, stretch=1)

        # Time badge (right-aligned)
        time_lbl = QLabel(ev.display_time())
        time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        time_lbl.setStyleSheet(
            f"font-size: 10px; color: {tok['text_lo']}; background: transparent;"
        )
        hlay.addWidget(time_lbl)

        return row
