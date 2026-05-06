"""Week view widget for the Calendar plugin.

Shows a 7-column time-grid (06:00–23:00) with an all-day row at the top,
timed event blocks positioned by time/duration, and a live current-time
indicator in today's column.
"""
from __future__ import annotations

from datetime import date, timedelta, datetime, time
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QRect
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QSizePolicy, QScrollArea,
)

from plugins.calendar.models import CalendarEvent


# ── Constants ─────────────────────────────────────────────────────────────────

_HOUR_START   = 6    # 06:00
_HOUR_END     = 23   # up to 23:00 (last row is 23:xx)
_HOURS        = _HOUR_END - _HOUR_START   # 17 displayed hours
_ROW_H        = 50   # px per hour row
_TIME_COL_W   = 50   # px for the time-label gutter
_HEADER_H     = 40   # px for the day-name header
_ALLDAY_H     = 40   # px for the all-day strip


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


# ── Current-time indicator overlay ───────────────────────────────────────────

class _TimeIndicator(QWidget):
    """Transparent overlay drawn on top of a day column to show current time."""

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._y: Optional[int] = None

    def set_y(self, y: Optional[int]) -> None:
        self._y = y
        self.update()

    def paintEvent(self, _event) -> None:
        if self._y is None:
            return
        painter = QPainter(self)
        pen = QPen(QColor(self._color), 2)
        painter.setPen(pen)
        painter.drawLine(0, self._y, self.width(), self._y)
        # Small dot on the left edge
        painter.setBrush(QColor(self._color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, self._y - 4, 8, 8)
        painter.end()


# ── Timed event block ─────────────────────────────────────────────────────────

class _EventBlock(QFrame):
    """A positioned event block inside a day column."""

    clicked = Signal(object)   # CalendarEvent

    def __init__(self, ev: CalendarEvent, tok: dict, parent=None):
        super().__init__(parent)
        self._ev = ev
        color    = ev.color()
        bg       = f"{color}33"

        extra_css = ""
        if ev.completed:
            extra_css = "text-decoration: line-through; opacity: 0.6;"

        self.setStyleSheet(
            f"QFrame {{ "
            f"background-color: {bg}; "
            f"border-left: 3px solid {color}; "
            f"border-top: none; border-right: none; border-bottom: none; "
            f"border-radius: 3px; "
            f"}}"
        )
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{ev.display_time()} — {ev.title}\n{ev.display_duration()}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 2, 2)
        layout.setSpacing(0)

        text = f"{ev.display_time()} {ev.icon()} {ev.title}"
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {tok['text_hi']}; font-size: 10px; "
            f"background: transparent; border: none; {extra_css}"
        )
        layout.addWidget(lbl)
        layout.addStretch()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self._ev)
        super().mousePressEvent(event)


# ── All-day chip ──────────────────────────────────────────────────────────────

class _AllDayChip(QLabel):
    """A small all-day event chip."""

    clicked = Signal(object)   # CalendarEvent

    def __init__(self, ev: CalendarEvent, tok: dict, parent=None):
        super().__init__(parent)
        self._ev = ev
        color    = ev.color()
        bg       = f"{color}33"

        extra_css = ""
        if ev.completed:
            extra_css = "text-decoration: line-through; opacity: 0.6;"

        self.setText(f"{ev.icon()} {ev.title}")
        self.setToolTip(ev.title)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"background-color: {bg}; "
            f"border-left: 2px solid {color}; "
            f"border-top: none; border-right: none; border-bottom: none; "
            f"border-radius: 3px; "
            f"padding: 1px 4px; "
            f"font-size: 10px; "
            f"color: {tok['text_hi']}; "
            f"{extra_css}"
        )

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self._ev)
        super().mousePressEvent(event)


# ── Day column (timed area) ───────────────────────────────────────────────────

class _DayColumn(QWidget):
    """The timed region for a single day — fixed-height with absolute-positioned event blocks."""

    event_clicked = Signal(object)   # CalendarEvent
    slot_clicked  = Signal(object, int)  # (date, hour)

    def __init__(self, col_date: date, tok: dict, parent=None):
        super().__init__(parent)
        self._date = col_date
        self._tok  = tok
        self._event_blocks: list[_EventBlock] = []
        self._indicator: Optional[_TimeIndicator] = None

        total_h = _HOURS * _ROW_H
        self.setFixedHeight(total_h)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Draw the hour row backgrounds via stylesheet on child frames,
        # but we manage children manually (no layout manager for event blocks).

    def set_events(self, events: list[CalendarEvent]) -> None:
        """Remove existing blocks and place new ones."""
        for blk in self._event_blocks:
            blk.deleteLater()
        self._event_blocks.clear()

        for ev in events:
            if not ev.time_start:
                continue   # all-day handled separately
            try:
                h, m    = map(int, ev.time_start.split(":"))
            except Exception:
                continue

            # Only show events within visible hours
            total_start_min = h * 60 + m
            view_start_min  = _HOUR_START * 60
            if total_start_min < view_start_min:
                continue

            y = int((total_start_min - view_start_min) / 60 * _ROW_H)
            height = max(18, int(ev.duration_minutes / 60 * _ROW_H))
            height = min(height, self.height() - y)

            blk = _EventBlock(ev, self._tok, self)
            blk.setGeometry(2, y, self.width() - 4 or 100, height)
            blk.clicked.connect(self.event_clicked)
            blk.show()
            self._event_blocks.append(blk)

        # Raise the time indicator above event blocks
        if self._indicator:
            self._indicator.raise_()

    def set_indicator(self, indicator: _TimeIndicator) -> None:
        self._indicator = indicator
        indicator.setParent(self)
        indicator.setGeometry(0, 0, self.width(), self.height())
        indicator.raise_()
        indicator.show()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Resize blocks to fill new width
        for blk in self._event_blocks:
            blk.setGeometry(2, blk.y(), self.width() - 4, blk.height())
        if self._indicator:
            self._indicator.setGeometry(0, 0, self.width(), self.height())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            y = event.position().y() if hasattr(event, "position") else event.y()
            hour = _HOUR_START + int(y / _ROW_H)
            hour = max(_HOUR_START, min(_HOUR_END - 1, hour))
            self.slot_clicked.emit(self._date, hour)
        super().mousePressEvent(event)


# ── Time-grid widget (time labels + 7 day columns) ───────────────────────────

class _TimeGrid(QWidget):
    """The scrollable area containing time labels and day columns side by side."""

    event_clicked = Signal(object)          # CalendarEvent
    slot_clicked  = Signal(object, int)     # (date, hour)

    def __init__(self, week_dates: list[date], today: date, tok: dict, parent=None):
        super().__init__(parent)
        self._tok        = tok
        self._today      = today
        self._day_cols: dict[date, _DayColumn] = {}
        self._indicator: Optional[_TimeIndicator] = None

        total_h = _HOURS * _ROW_H
        self.setMinimumHeight(total_h)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Left gutter: time labels ──────────────────────────────────────────
        gutter = QWidget()
        gutter.setFixedWidth(_TIME_COL_W)
        gutter.setFixedHeight(total_h)
        gutter.setStyleSheet(f"background-color: {tok['bg_base']};")
        gutter_layout = QVBoxLayout(gutter)
        gutter_layout.setContentsMargins(0, 0, 0, 0)
        gutter_layout.setSpacing(0)

        for h in range(_HOUR_START, _HOUR_END):
            row_container = QWidget()
            row_container.setFixedHeight(_ROW_H)
            row_lyt = QVBoxLayout(row_container)
            row_lyt.setContentsMargins(4, 2, 4, 0)
            row_lyt.setSpacing(0)

            lbl = QLabel(f"{h:02d}:00")
            lbl.setStyleSheet(
                f"color: {tok['text_lo']}; font-size: 9px; "
                "background: transparent;"
            )
            lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
            row_lyt.addWidget(lbl)
            row_lyt.addStretch()
            gutter_layout.addWidget(row_container)

        outer.addWidget(gutter)

        # ── Day columns area ──────────────────────────────────────────────────
        cols_widget = QWidget()
        cols_widget.setStyleSheet(f"background-color: {tok['bg_base']};")
        cols_widget.setFixedHeight(total_h)
        cols_layout = QHBoxLayout(cols_widget)
        cols_layout.setContentsMargins(0, 0, 0, 0)
        cols_layout.setSpacing(0)

        for d in week_dates:
            # Separator line between columns (except first)
            if self._day_cols:
                sep = QFrame()
                sep.setFixedWidth(1)
                sep.setStyleSheet(f"background-color: {tok['border']};")
                cols_layout.addWidget(sep)

            col = _DayColumn(d, tok)
            col.event_clicked.connect(self.event_clicked)
            col.slot_clicked.connect(self.slot_clicked)
            cols_layout.addWidget(col, stretch=1)
            self._day_cols[d] = col

        outer.addWidget(cols_widget, stretch=1)

        # ── Current-time indicator ────────────────────────────────────────────
        if today in self._day_cols:
            self._indicator = _TimeIndicator(tok["danger"])
            self._day_cols[today].set_indicator(self._indicator)
            self._update_indicator()

    def set_events(self, events: list[CalendarEvent]) -> None:
        by_date: dict[str, list[CalendarEvent]] = {}
        for ev in events:
            by_date.setdefault(ev.event_date, []).append(ev)

        for d, col in self._day_cols.items():
            col.set_events(by_date.get(d.isoformat(), []))

    def _update_indicator(self) -> None:
        if self._indicator is None:
            return
        now = datetime.now()
        h   = now.hour
        m   = now.minute
        if h < _HOUR_START or h >= _HOUR_END:
            self._indicator.set_y(None)
            return
        y = int(((h - _HOUR_START) * 60 + m) / 60 * _ROW_H)
        self._indicator.set_y(y)

    def tick(self) -> None:
        """Called by a QTimer every minute to refresh the indicator."""
        self._update_indicator()


# ── Week view ─────────────────────────────────────────────────────────────────

class WeekView(QWidget):
    """7-column week calendar with all-day row and scrollable time grid.

    Signals
    -------
    event_clicked(CalendarEvent)
        Emitted when any event block or chip is clicked.
    date_clicked((date, int))
        Emitted when an empty time slot is clicked; payload is (date, hour).
    """

    event_clicked = Signal(object)   # CalendarEvent
    date_clicked  = Signal(object)   # (date, int) tuple

    _DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx        = context
        self._year       = date.today().isocalendar()[0]
        self._week       = date.today().isocalendar()[1]
        self._events: list[CalendarEvent] = []
        self._week_dates: list[date] = []
        self._time_grid: Optional[_TimeGrid] = None

        # ── Root layout ───────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tok = self._tok()
        self.setStyleSheet(f"background-color: {tok['bg_base']};")

        # ── Day-name header ───────────────────────────────────────────────────
        self._header_frame = QFrame()
        self._header_frame.setFixedHeight(_HEADER_H)
        self._header_frame.setStyleSheet(
            f"background-color: {tok['bg_raised']}; "
            f"border-bottom: 1px solid {tok['border']};"
        )
        header_layout = QHBoxLayout(self._header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        # Left gutter spacer to align with time labels
        spacer = QWidget()
        spacer.setFixedWidth(_TIME_COL_W)
        spacer.setStyleSheet("background: transparent;")
        header_layout.addWidget(spacer)

        self._header_labels: list[QLabel] = []
        for i, name in enumerate(self._DAY_NAMES):
            if i > 0:
                sep = QFrame()
                sep.setFixedWidth(1)
                sep.setStyleSheet(f"background-color: {tok['border']};")
                header_layout.addWidget(sep)
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {tok['text_mid']}; font-size: 10px; "
                "background: transparent;"
            )
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            header_layout.addWidget(lbl, stretch=1)
            self._header_labels.append(lbl)

        # Right spacer — matches the always-visible scrollbar width so day
        # column boundaries stay perfectly aligned between the header and the
        # scrollable time grid.
        self._header_sb_spacer = QWidget()
        self._header_sb_spacer.setStyleSheet("background: transparent;")
        header_layout.addWidget(self._header_sb_spacer)

        root.addWidget(self._header_frame)

        # ── Scrollable time grid ──────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Always show the vertical scrollbar so the header/all-day columns never
        # misalign with the time-grid columns when content becomes scrollable.
        # A hidden-then-appearing scrollbar steals ~12–15 px from the grid
        # content without adjusting the header — making columns visually drift.
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: {tok['bg_base']}; }}"
        )
        root.addWidget(self._scroll, stretch=1)

        # Container for the _TimeGrid — built in set_week()
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet(f"background-color: {tok['bg_base']};")
        self._scroll.setWidget(self._grid_container)
        self._container_layout = QVBoxLayout(self._grid_container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(0)

        # ── Timer for live indicator ──────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(60_000)  # every minute

        # Build initial week
        self.set_week(self._year, self._week)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_week(self, year: int, week: int) -> None:
        """Rebuild the grid for the given ISO year/week."""
        self._year = year
        self._week = week
        self._events = []

        tok = self._tok()
        today = date.today()

        # Compute the 7 dates for this week
        monday = date.fromisocalendar(year, week, 1)
        self._week_dates = [monday + timedelta(days=i) for i in range(7)]
        is_current_week = any(d == today for d in self._week_dates)

        # ── Update header labels ──────────────────────────────────────────────
        for i, (lbl, d) in enumerate(zip(self._header_labels, self._week_dates)):
            day_name = self._DAY_NAMES[i]
            is_today = (d == today)
            date_color = tok["accent"] if is_today else tok["text_mid"]
            bg = tok["bg_raised"]
            lbl.setText(f"{day_name}\n{d.day}")
            lbl.setStyleSheet(
                f"color: {date_color}; font-size: 10px; "
                f"background-color: {bg}; font-weight: {'bold' if is_today else 'normal'};"
            )

        # ── Rebuild the time grid ─────────────────────────────────────────────
        # Remove old grid from container
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._time_grid = None

        today_for_indicator = today if is_current_week else None
        grid = _TimeGrid(self._week_dates, today_for_indicator or date(1, 1, 1), tok)
        grid.event_clicked.connect(self.event_clicked)
        grid.slot_clicked.connect(lambda d, h: self.date_clicked.emit((d, h)))
        self._container_layout.addWidget(grid)
        self._container_layout.addStretch()
        self._time_grid = grid

        # Scroll to 08:00 — deferred one event-loop tick so Qt has finished
        # computing the new grid's geometry before we set the scroll position.
        scroll_y = (8 - _HOUR_START) * _ROW_H
        QTimer.singleShot(0, lambda sy=scroll_y: self._scroll.verticalScrollBar().setValue(sy))

    def refresh(self, events: list[CalendarEvent]) -> None:
        """Update events without rebuilding the grid."""
        self._events = list(events)

        # Timed events → time grid (all-day events shown in daily agenda panel only)
        if self._time_grid is not None:
            self._time_grid.set_events(events)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        if self._time_grid is not None:
            self._time_grid.tick()

    def _tok(self) -> dict:
        return _tok(self._ctx)

    # ── Column alignment helpers ──────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Defer spacer sync so Qt finishes computing scrollbar geometry first.
        QTimer.singleShot(0,  self._sync_sb_spacers)
        QTimer.singleShot(50, self._sync_sb_spacers)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_sb_spacers)

    def _sync_sb_spacers(self) -> None:
        """Set the header right spacer to match the scrollbar width.

        This ensures day column boundaries line up perfectly between the sticky
        header row and the scrollable time grid even when the scrollbar is
        always visible.
        """
        try:
            sb_w = self._scroll.verticalScrollBar().width()
        except Exception:
            sb_w = 0
        # Clamp to a sensible range — scrollbar is typically 8–20 px.
        sb_w = max(0, min(sb_w, 30))
        if hasattr(self, "_header_sb_spacer"):
            self._header_sb_spacer.setFixedWidth(sb_w)
