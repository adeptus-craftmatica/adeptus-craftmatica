"""Month view widget for the Calendar plugin.

Displays a 6-row × 7-column grid (Mon–Sun, always 42 cells) with
colour-coded event chips and today-highlight.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QSizePolicy, QScrollArea,
)

from plugins.calendar.models import CalendarEvent


# ── Theme helper ──────────────────────────────────────────────────────────────

def _tok(ctx) -> dict:
    tm = ctx.services.get("theme_manager") if ctx else None
    return {
        "bg_base":  tm.token("bg_base")   if tm else "#121212",
        "bg_raised": tm.token("bg_raised") if tm else "#1e1e1e",
        "card_bg":  tm.token("card_bg")   if tm else "#1a1a1a",
        "border":   tm.token("border")    if tm else "#2a2a2a",
        "text_hi":  tm.token("text_hi")   if tm else "#e8e8e8",
        "text_mid": tm.token("text_mid")  if tm else "#b0b0b0",
        "text_lo":  tm.token("text_lo")   if tm else "#606060",
        "accent":   tm.token("accent")    if tm else "#0078d4",
        "danger":   tm.token("danger")    if tm else "#c62828",
        "success":  tm.token("success")   if tm else "#2e7d32",
    }


# ── Day cell ──────────────────────────────────────────────────────────────────

class _DayCell(QFrame):
    """A single day cell in the month grid."""

    date_clicked  = Signal(object)   # date
    event_clicked = Signal(object)   # CalendarEvent

    def __init__(self, cell_date: date, in_month: bool, tok: dict, parent=None):
        super().__init__(parent)
        self._date = cell_date
        self._in_month = in_month
        self._tok = tok
        self._event_chips: list[QLabel] = []

        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Out-of-month cells are transparent placeholders — no border, no content,
        # no cursor. The layout still occupies space to keep column widths uniform.
        if not in_month:
            self.setStyleSheet("QFrame { background: transparent; border: none; }")
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            return

        self.setCursor(Qt.PointingHandCursor)

        # Styling
        is_today = (cell_date == date.today())
        if is_today:
            bg = tok["bg_raised"]
            border_css = f"border: 2px solid {tok['accent']};"
        else:
            bg = tok["card_bg"]
            border_css = f"border: 1px solid {tok['border']};"

        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; {border_css} border-radius: 4px; }}"
        )

        # Layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 3, 4, 3)
        self._layout.setSpacing(2)

        # Date number (top-right aligned)
        date_row = QHBoxLayout()
        date_row.addStretch()
        is_today = (cell_date == date.today())
        num_color = tok["accent"] if is_today else tok["text_mid"]
        self._date_lbl = QLabel(str(cell_date.day))
        self._date_lbl.setStyleSheet(
            f"color: {num_color}; font-size: 11px; font-weight: {'bold' if is_today else 'normal'};"
            "background: transparent; border: none;"
        )
        date_row.addWidget(self._date_lbl)
        self._layout.addLayout(date_row)

        # Placeholder stretch — chips go above this
        self._layout.addStretch()

    # ── Event chips ───────────────────────────────────────────────────────────

    def set_events(self, events: list[CalendarEvent]) -> None:
        """Populate chip labels; call after cell creation or on refresh."""
        if not self._in_month:
            return
        for chip in self._event_chips:
            self._layout.removeWidget(chip)
            chip.deleteLater()
        self._event_chips.clear()

        while self._layout.count() > 1:
            item = self._layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        if events:
            chip = self._make_chip(events[0])
            self._event_chips.append(chip)
            self._layout.addWidget(chip)

            overflow = len(events) - 1
            if overflow > 0:
                more_lbl = QLabel(f"And {overflow} more")
                more_lbl.setStyleSheet(
                    f"color: {self._tok['text_lo']}; font-size: 9px; "
                    "background: transparent; border: none; padding: 0 2px;"
                )
                self._layout.addWidget(more_lbl)

        self._layout.addStretch()

    def _make_chip(self, ev: CalendarEvent) -> QLabel:
        color = ev.color()
        bg    = f"{color}22"
        text  = f"{ev.icon()} {ev.title}"

        extra_css = ""
        if ev.completed:
            extra_css = "text-decoration: line-through; opacity: 0.6;"

        chip = QLabel(text)
        chip.setToolTip(f"{ev.display_time()} — {ev.title}")
        chip.setMaximumWidth(self.width() - 10 if self.width() > 10 else 200)
        chip.setWordWrap(False)
        chip.setStyleSheet(
            f"background-color: {bg}; "
            f"border-left: 2px solid {color}; "
            f"border-top: none; border-right: none; border-bottom: none; "
            f"border-radius: 3px; "
            f"padding: 1px 4px; "
            f"font-size: 10px; "
            f"color: {self._tok['text_hi']}; "
            f"{extra_css}"
        )
        chip.setCursor(Qt.PointingHandCursor)
        # Store reference to event on the label
        chip.setProperty("calendar_event", ev)
        chip.mousePressEvent = lambda _e, e=ev: self.event_clicked.emit(e)  # type: ignore[method-assign]
        return chip

    # ── Mouse interaction ─────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if self._in_month:
            self.date_clicked.emit(self._date)
        super().mousePressEvent(event)


# ── Month view ────────────────────────────────────────────────────────────────

class MonthView(QWidget):
    """6-week month calendar grid with event chips.

    Signals
    -------
    event_clicked(CalendarEvent)
        Emitted when an event chip is clicked.
    date_clicked(date)
        Emitted when a day cell background is clicked.
    """

    event_clicked = Signal(object)   # CalendarEvent
    date_clicked  = Signal(object)   # date

    _DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx   = context
        self._year  = date.today().year
        self._month = date.today().month
        self._cells: dict[date, _DayCell] = {}   # date → cell widget
        self._events: list[CalendarEvent] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tok = self._tok()
        self.setStyleSheet(f"background-color: {tok['bg_base']};")

        # ── Day-of-week header ────────────────────────────────────────────────
        header_frame = QFrame()
        header_frame.setStyleSheet(
            f"background-color: {tok['bg_base']}; "
            f"border-bottom: 1px solid {tok['border']};"
        )
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(2, 4, 2, 4)
        header_layout.setSpacing(0)

        for name in self._DAY_NAMES:
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {tok['text_lo']}; font-size: 9px; font-weight: bold; "
                "background: transparent;"
            )
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            header_layout.addWidget(lbl)

        root.addWidget(header_frame)

        # ── Grid container ────────────────────────────────────────────────────
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet(f"background-color: {tok['bg_base']};")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(2, 2, 2, 2)
        self._grid.setSpacing(3)

        # Make all rows/columns expand equally
        for col in range(7):
            self._grid.setColumnStretch(col, 1)
        for row in range(6):
            self._grid.setRowStretch(row, 1)

        root.addWidget(self._grid_widget, stretch=1)

        # Build initial grid
        self.set_month(self._year, self._month)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_month(self, year: int, month: int) -> None:
        """Rebuild the grid for the given year/month."""
        self._year  = year
        self._month = month
        self._cells.clear()
        self._events = []

        tok = self._tok()
        self.setStyleSheet(f"background-color: {tok['bg_base']};")
        self._grid_widget.setStyleSheet(f"background-color: {tok['bg_base']};")

        # Remove all existing cell widgets from the grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Calculate the Monday of the first week
        first_day = date(year, month, 1)
        start_date = first_day - timedelta(days=first_day.weekday())

        for idx in range(42):  # 6 rows × 7 cols
            cell_date = start_date + timedelta(days=idx)
            in_month  = (cell_date.month == month)

            cell = _DayCell(cell_date, in_month, tok)
            cell.date_clicked.connect(self.date_clicked)
            cell.event_clicked.connect(self.event_clicked)

            row = idx // 7
            col = idx % 7
            self._grid.addWidget(cell, row, col)
            self._cells[cell_date] = cell

    def refresh(self, events: list[CalendarEvent]) -> None:
        """Update event chips without rebuilding the grid."""
        self._events = list(events)

        # Group events by date
        by_date: dict[str, list[CalendarEvent]] = {}
        for ev in events:
            by_date.setdefault(ev.event_date, []).append(ev)

        for cell_date, cell in self._cells.items():
            day_events = by_date.get(cell_date.isoformat(), [])
            # Sort: timed events first, then all-day; within each group by time
            day_events.sort(key=lambda e: (e.time_start == "", e.time_start))
            cell.set_events(day_events)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _tok(self) -> dict:
        return _tok(self._ctx)
