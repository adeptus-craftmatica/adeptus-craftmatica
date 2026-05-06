"""Calendar plugin main UI — toolbar + 4 views in a QStackedWidget."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QSizePolicy, QScrollArea,
)

from plugins.calendar.widgets.month_view   import MonthView
from plugins.calendar.widgets.week_view    import WeekView
from plugins.calendar.widgets.agenda_view  import AgendaView
from plugins.calendar.widgets.today_view   import TodayView
from plugins.calendar.widgets.event_dialog import EventDialog


def _tok(ctx) -> dict:
    tm = ctx.services.get("theme_manager") if ctx else None
    return {
        "bg":      tm.token("bg_base")    if tm else "#121212",
        "raised":  tm.token("bg_raised")  if tm else "#1e1e1e",
        "input":   tm.token("bg_input")   if tm else "#2a2a2a",
        "card":    tm.token("card_bg")    if tm else "#1a1a1a",
        "border":  tm.token("border")     if tm else "#2a2a2a",
        "hi":      tm.token("text_hi")    if tm else "#e8e8e8",
        "mid":     tm.token("text_mid")   if tm else "#b0b0b0",
        "lo":      tm.token("text_lo")    if tm else "#808080",
        "accent":  tm.token("accent")     if tm else "#0078d4",
        "danger":  tm.token("danger")     if tm else "#c62828",
        "success": tm.token("success")    if tm else "#2e7d32",
    }


# ── Daily agenda panel ────────────────────────────────────────────────────────

class DailyAgendaPanel(QFrame):
    """Right-side panel that shows events for a single selected day."""

    add_requested   = Signal(str)    # ISO date string
    event_clicked   = Signal(object) # CalendarEvent
    close_requested = Signal()

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx   = context
        self._date  = None

        self.setFixedWidth(264)
        t = _tok(self._ctx)
        self.setStyleSheet(
            f"QFrame#DailyAgendaPanel {{"
            f"  background: {t['card']};"
            f"  border-left: 1px solid {t['border']};"
            f"}}"
        )
        self.setObjectName("DailyAgendaPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("AgendaHdr")
        hdr.setFixedHeight(44)
        hdr.setStyleSheet(
            f"QFrame#AgendaHdr {{"
            f"  background: {t['raised']};"
            f"  border-bottom: 1px solid {t['border']};"
            f"}}"
        )
        hlay = QHBoxLayout(hdr)
        hlay.setContentsMargins(12, 0, 8, 0)
        hlay.setSpacing(6)

        self._hdr_lbl = QLabel("")
        self._hdr_lbl.setStyleSheet(
            f"color: {t['hi']}; font-size: 13px; font-weight: 700; background: transparent;"
        )
        hlay.addWidget(self._hdr_lbl, stretch=1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {t['lo']}; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {t['hi']}; }}"
        )
        close_btn.clicked.connect(self.close_requested)
        hlay.addWidget(close_btn)

        root.addWidget(hdr)

        # ── Scroll area ───────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; }}"
        )

        self._list_w = QWidget()
        self._list_w.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list_w)
        self._list_lay.setContentsMargins(8, 8, 8, 8)
        self._list_lay.setSpacing(5)
        self._list_lay.addStretch()

        self._scroll.setWidget(self._list_w)
        root.addWidget(self._scroll, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        ftr = QFrame()
        ftr.setObjectName("AgendaFtr")
        ftr.setFixedHeight(52)
        ftr.setStyleSheet(
            f"QFrame#AgendaFtr {{"
            f"  background: {t['raised']};"
            f"  border-top: 1px solid {t['border']};"
            f"}}"
        )
        flay = QHBoxLayout(ftr)
        flay.setContentsMargins(8, 0, 8, 0)

        self._add_btn = QPushButton("＋  Add Event")
        self._add_btn.setFixedHeight(34)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.setStyleSheet(
            f"QPushButton {{ background: {t['accent']}; color: #ffffff; border: none; "
            f"border-radius: 6px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {t['accent']}cc; }}"
        )
        self._add_btn.clicked.connect(
            lambda: self.add_requested.emit(self._date.isoformat() if self._date else "")
        )
        flay.addWidget(self._add_btn)

        root.addWidget(ftr)

    # ── Public ────────────────────────────────────────────────────────────────

    def show_date(self, d, events: list) -> None:
        """Populate and show the panel for the given date."""
        self._date = d
        t = _tok(self._ctx)

        # Header label
        day_name  = d.strftime("%A")
        month_day = f"{d.strftime('%B')} {d.day}"
        self._hdr_lbl.setText(f"{day_name}, {month_day}")

        # Rebuild event list (keep trailing stretch at end)
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not events:
            lbl = QLabel("No events for this day")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setContentsMargins(0, 20, 0, 0)
            lbl.setStyleSheet(
                f"color: {t['lo']}; font-size: 11px; background: transparent;"
            )
            self._list_lay.insertWidget(0, lbl)
        else:
            for i, ev in enumerate(events):
                self._list_lay.insertWidget(i, self._make_row(ev, t))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_row(self, ev, t: dict) -> QFrame:
        color = ev.color()
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: {color}18; border-left: 3px solid {color}; "
            f"border-radius: 4px; }}"
            f"QFrame:hover {{ background: {color}30; }}"
        )
        row.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)

        title = QLabel(f"{ev.icon()}  {ev.title}")
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {t['hi']}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        lay.addWidget(title)

        meta_parts = []
        if ev.time_start:
            meta_parts.append(ev.time_start)
        meta_parts.append(ev.event_category)
        meta = QLabel("  ·  ".join(meta_parts))
        meta.setStyleSheet(
            f"color: {t['mid']}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(meta)

        row.mousePressEvent = lambda _e, e=ev: self.event_clicked.emit(e)  # type: ignore[method-assign]
        return row


# ── View index constants ──────────────────────────────────────────────────────

_V_MONTH  = 0
_V_WEEK   = 1
_V_AGENDA = 2
_V_TODAY  = 3


class CalendarUI(QWidget):
    """
    Hobby Command Center — main calendar view.

    Toolbar: [Today] [◀] [date label] [▶]  |  [Month][Week][Agenda][Today]  |  [+ Add]
    Body:    QStackedWidget → MonthView / WeekView / AgendaView / TodayView
    """

    # Emitted when plugin should navigate elsewhere (pass-through to main bus)
    action_requested = Signal(str, dict)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx  = context
        self._svc  = None           # set by plugin.py after service registration

        # Current navigation state
        self._view_idx   = _V_TODAY
        self._cur_year   = date.today().year
        self._cur_month  = date.today().month
        self._cur_week   = date.today().isocalendar()[1]

        self.setMinimumSize(0, 0)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(8)

        root.addWidget(self._build_toolbar())
        root.addWidget(self._hline())
        root.addWidget(self._build_body(), stretch=1)

        # Initialise date label now that toolbar + stack exist
        self._update_date_label()

        # Theme reactivity
        tm = context.services.get("theme_manager") if context else None
        if tm:
            try:
                tm.theme_changed.connect(self._on_theme_changed)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════════════
    # Toolbar
    # ══════════════════════════════════════════════════════════════════════════

    def _build_toolbar(self) -> QWidget:
        t = _tok(self._ctx)
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"background: {t['bg']};")

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # ── Today button ──────────────────────────────────────────────────────
        self._today_btn = self._make_btn("Today", primary=False)
        self._today_btn.clicked.connect(self._go_today)
        lay.addWidget(self._today_btn)

        # ── Prev / Next navigation ────────────────────────────────────────────
        self._prev_btn = self._make_btn("◀", icon=True)
        self._prev_btn.clicked.connect(self._go_prev)
        lay.addWidget(self._prev_btn)

        self._date_lbl = QLabel("")
        self._date_lbl.setAlignment(Qt.AlignCenter)
        self._date_lbl.setMinimumWidth(180)
        self._date_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {t['hi']}; background: transparent;"
        )
        lay.addWidget(self._date_lbl)

        self._next_btn = self._make_btn("▶", icon=True)
        self._next_btn.clicked.connect(self._go_next)
        lay.addWidget(self._next_btn)

        lay.addStretch()

        # ── View toggle buttons ───────────────────────────────────────────────
        self._view_btns: list[QPushButton] = []
        for idx, (label, icon) in enumerate([
            ("Month",  "🗓"),
            ("Week",   "📅"),
            ("Agenda", "📋"),
            ("Today",  "⚡"),
        ]):
            btn = self._make_view_btn(f"{icon}  {label}", idx)
            self._view_btns.append(btn)
            lay.addWidget(btn)

        lay.addSpacing(12)

        # ── Add Event button ──────────────────────────────────────────────────
        self._add_btn = self._make_btn("＋  Add Event", primary=True)
        self._add_btn.clicked.connect(self._on_add_event)
        lay.addWidget(self._add_btn)

        self._update_toolbar_style()
        return bar

    def _make_btn(self, text: str, primary: bool = False, icon: bool = False) -> QPushButton:
        t = _tok(self._ctx)
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        if icon:
            btn.setFixedSize(28, 28)
        elif primary:
            btn.setFixedHeight(32)
        else:
            btn.setFixedHeight(32)
        self._style_btn(btn, primary=primary, active=False)
        return btn

    def _make_view_btn(self, text: str, view_idx: int) -> QPushButton:
        t = _tok(self._ctx)
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda _, i=view_idx: self._switch_view(i))
        self._style_btn(btn, active=(view_idx == self._view_idx))
        return btn

    def _style_btn(self, btn: QPushButton, primary: bool = False, active: bool = False):
        t = _tok(self._ctx)
        if primary:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t['accent']}; color: white;
                    border: none; border-radius: 6px;
                    padding: 0 14px; font-size: 12px; font-weight: 600;
                }}
                QPushButton:hover {{ background: {t['accent']}cc; }}
            """)
        elif active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t['accent']}22; color: {t['accent']};
                    border: 1px solid {t['accent']}55; border-radius: 5px;
                    padding: 0 12px; font-size: 12px; font-weight: 600;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t['raised']}; color: {t['lo']};
                    border: 1px solid {t['border']}; border-radius: 5px;
                    padding: 0 12px; font-size: 12px;
                }}
                QPushButton:hover {{ color: {t['hi']}; border-color: {t['accent']}88; }}
            """)

    def _update_toolbar_style(self):
        """Refresh all toolbar button styles (e.g. after view change or theme change)."""
        t = _tok(self._ctx)

        self._style_btn(self._today_btn, primary=False, active=False)
        self._style_btn(self._prev_btn)
        self._style_btn(self._next_btn)
        self._style_btn(self._add_btn,   primary=True)
        self._date_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {t['hi']}; background: transparent;"
        )

        for idx, btn in enumerate(self._view_btns):
            self._style_btn(btn, active=(idx == self._view_idx))

        self._update_date_label()

    # ══════════════════════════════════════════════════════════════════════════
    # Stacked view
    # ══════════════════════════════════════════════════════════════════════════

    def _build_body(self) -> QWidget:
        """Horizontal container: stacked views on the left, agenda panel on the right."""
        body = QWidget()
        lay  = QHBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_stack(), stretch=1)

        self._daily_panel = DailyAgendaPanel(self._ctx)
        # Add to layout FIRST so Qt sets the parent (child widget, not top-level
        # window). Only then hide — otherwise show() later opens a detached window.
        lay.addWidget(self._daily_panel)
        self._daily_panel.setVisible(False)

        self._daily_panel.add_requested.connect(self._on_add_event_for_date)
        self._daily_panel.event_clicked.connect(self._on_event_clicked)
        self._daily_panel.close_requested.connect(lambda: self._daily_panel.setVisible(False))

        return body

    def _build_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._stack.setMinimumSize(0, 0)

        self._month_view  = MonthView(self._ctx)
        self._week_view   = WeekView(self._ctx)
        self._agenda_view = AgendaView(self._ctx)
        self._today_view  = TodayView(self._ctx)

        self._stack.addWidget(self._month_view)   # idx 0
        self._stack.addWidget(self._week_view)    # idx 1
        self._stack.addWidget(self._agenda_view)  # idx 2
        self._stack.addWidget(self._today_view)   # idx 3

        # Wire child signals
        for view in (self._month_view, self._week_view, self._agenda_view, self._today_view):
            if hasattr(view, "event_clicked"):
                view.event_clicked.connect(self._on_event_clicked)
            if hasattr(view, "date_clicked"):
                view.date_clicked.connect(self._on_date_clicked)
            if hasattr(view, "complete_toggled"):
                view.complete_toggled.connect(self._on_complete_toggled)
            if hasattr(view, "add_requested"):
                view.add_requested.connect(self._on_add_event_for_date)
            if hasattr(view, "source_navigate"):
                view.source_navigate.connect(self._on_source_navigate)

        self._stack.setCurrentIndex(_V_TODAY)
        return self._stack

    # ══════════════════════════════════════════════════════════════════════════
    # Navigation
    # ══════════════════════════════════════════════════════════════════════════

    def _switch_view(self, idx: int):
        self._view_idx = idx
        if hasattr(self, "_daily_panel"):
            self._daily_panel.setVisible(False)
        self._stack.setCurrentIndex(idx)
        self._update_toolbar_style()
        self.refresh()

    def _go_today(self):
        today = date.today()
        self._cur_year  = today.year
        self._cur_month = today.month
        self._cur_week  = today.isocalendar()[1]
        self._update_date_label()
        self._switch_view(_V_TODAY)

    def _go_prev(self):
        if self._view_idx == _V_MONTH:
            self._cur_month -= 1
            if self._cur_month < 1:
                self._cur_month = 12
                self._cur_year -= 1
            if hasattr(self, "_daily_panel"):
                self._daily_panel.setVisible(False)
        elif self._view_idx == _V_WEEK:
            d = date.fromisocalendar(self._cur_year, self._cur_week, 1) - timedelta(weeks=1)
            self._cur_year, self._cur_week, _ = d.isocalendar()
        elif self._view_idx in (_V_AGENDA, _V_TODAY):
            return  # Agenda/Today don't paginate
        self._update_date_label()
        self.refresh()

    def _go_next(self):
        if self._view_idx == _V_MONTH:
            self._cur_month += 1
            if self._cur_month > 12:
                self._cur_month = 1
                self._cur_year += 1
            if hasattr(self, "_daily_panel"):
                self._daily_panel.setVisible(False)
        elif self._view_idx == _V_WEEK:
            d = date.fromisocalendar(self._cur_year, self._cur_week, 1) + timedelta(weeks=1)
            self._cur_year, self._cur_week, _ = d.isocalendar()
        elif self._view_idx in (_V_AGENDA, _V_TODAY):
            return
        self._update_date_label()
        self.refresh()

    def _update_date_label(self):
        import calendar as _cal
        if self._view_idx == _V_MONTH:
            month_name = _cal.month_name[self._cur_month]
            self._date_lbl.setText(f"{month_name} {self._cur_year}")
        elif self._view_idx == _V_WEEK:
            monday = date.fromisocalendar(self._cur_year, self._cur_week, 1)
            sunday = monday + timedelta(days=6)
            if monday.month == sunday.month:
                self._date_lbl.setText(
                    f"{monday.strftime('%b %d')} – {sunday.day}, {sunday.year}"
                )
            else:
                self._date_lbl.setText(
                    f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d')}, {sunday.year}"
                )
        elif self._view_idx == _V_AGENDA:
            self._date_lbl.setText("Next 30 days")
        elif self._view_idx == _V_TODAY:
            self._date_lbl.setText(date.today().strftime("%A, %B %d"))

        # Show/hide prev-next for Agenda/Today
        navigable = self._view_idx in (_V_MONTH, _V_WEEK)
        self._prev_btn.setVisible(navigable)
        self._next_btn.setVisible(navigable)

    # ══════════════════════════════════════════════════════════════════════════
    # Data refresh
    # ══════════════════════════════════════════════════════════════════════════

    def set_service(self, svc):
        """Called by plugin.py after the service is registered."""
        self._svc = svc

    def refresh(self):
        if not self._svc:
            return

        # Re-populate the daily panel if it's open (but don't force-show it)
        if (hasattr(self, "_daily_panel")
                and self._daily_panel.isVisible()
                and self._daily_panel._date is not None
                and self._view_idx == _V_MONTH):
            self._show_daily_panel(self._daily_panel._date)

        try:
            if self._view_idx == _V_MONTH:
                events = self._svc.get_events_for_month(self._cur_year, self._cur_month)
                if (self._month_view._year != self._cur_year
                        or self._month_view._month != self._cur_month):
                    self._month_view.set_month(self._cur_year, self._cur_month)
                self._month_view.refresh(events)

            elif self._view_idx == _V_WEEK:
                events = self._svc.get_events_for_week(self._cur_year, self._cur_week)
                # Only rebuild the time grid when the week actually changed.
                # Rebuilding on every refresh (e.g. after saving an event) causes
                # the scroll area to flash blank while Qt re-lays out the grid.
                if (self._week_view._year != self._cur_year
                        or self._week_view._week != self._cur_week):
                    self._week_view.set_week(self._cur_year, self._cur_week)
                self._week_view.refresh(events)

            elif self._view_idx == _V_AGENDA:
                upcoming = self._svc.get_upcoming(30)
                overdue  = self._svc.get_overdue()
                self._agenda_view.refresh(upcoming, overdue)

            elif self._view_idx == _V_TODAY:
                planned      = self._svc.get_today_planned()
                activity     = self._svc.get_today_activity()
                overdue      = self._svc.get_overdue()
                upcoming_wk  = self._svc.get_upcoming_week()
                self._today_view.refresh(planned, activity, overdue, upcoming_wk)

        except Exception as e:
            print(f"[CALENDAR UI] refresh error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Event handlers
    # ══════════════════════════════════════════════════════════════════════════

    def _on_add_event(self):
        self._open_event_dialog(event=None, default_date=date.today().isoformat())

    def _on_add_event_for_date(self, d):
        """Called by agenda panel footer or TodayView add_requested."""
        if isinstance(d, tuple):
            d = d[0]
        iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
        self._open_event_dialog(event=None, default_date=iso)

    def _on_date_clicked(self, d):
        """Any date/slot click → open daily agenda panel on the right."""
        if isinstance(d, tuple):
            d = d[0]
        self._show_daily_panel(d)

    def _show_daily_panel(self, d) -> None:
        """Fetch events for `d`, populate the right-hand agenda panel, and show it."""
        events: list = []
        if self._svc:
            try:
                d_iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
                # Use a direct day query if available, otherwise filter from the month.
                try:
                    all_events = self._svc.get_events_for_month(
                        int(d_iso[:4]), int(d_iso[5:7])
                    )
                except Exception:
                    all_events = []
                events = [e for e in all_events if e.event_date == d_iso]
                events.sort(key=lambda e: (e.time_start == "", e.time_start))
            except Exception as exc:
                print(f"[CALENDAR UI] daily panel error: {exc}")
        self._daily_panel.show_date(d, events)
        self._daily_panel.setVisible(True)

    def _on_event_clicked(self, event):
        """Event chip / row click → open edit dialog."""
        self._open_event_dialog(event=event)

    def _on_source_navigate(self, plugin_id: str):
        """Navigate the main window to the plugin that generated a calendar event."""
        self._emit_bus("dashboard_navigate", {"plugin_id": plugin_id})

    def _on_complete_toggled(self, event_id: int):
        if not self._svc:
            return
        try:
            ev = self._svc.get_event(event_id)
            if ev:
                if ev.completed:
                    self._svc.uncomplete_event(event_id)
                else:
                    self._svc.complete_event(event_id)
            self.refresh()
            # Notify the dashboard so it re-polls overdue/notifications immediately
            self._emit_bus("calendar_event_updated", {"id": event_id})
        except Exception as e:
            print(f"[CALENDAR UI] complete toggle error: {e}")

    def _open_event_dialog(self, event=None, default_date=None):
        from plugins.calendar.widgets.event_dialog import EventDialog as _ED
        from PySide6.QtGui import QGuiApplication
        parent = self.window() if self.window() is not self else self
        dlg = EventDialog(self._ctx, event=event, default_date=default_date, parent=parent)
        # Center on the parent's screen to prevent off-screen placement that
        # creates an invisible blocking modal (symptom: UI appears "frozen").
        try:
            screen = (parent.screen()
                      if parent and parent.isVisible()
                      else QGuiApplication.primaryScreen())
            if screen:
                ag = screen.availableGeometry()
                dlg.adjustSize()
                dlg.move(
                    ag.center().x() - dlg.width()  // 2,
                    ag.center().y() - dlg.height() // 2,
                )
        except Exception:
            pass
        result = dlg.exec()

        if result == _ED.DELETED and event and event.id is not None:
            # ── User confirmed deletion ───────────────────────────────────────
            try:
                self._svc.delete_event(event.id)
                self._emit_bus("calendar_event_deleted", {
                    "id": event.id,
                    "title": event.title,
                })
                self.refresh()
            except Exception as e:
                print(f"[CALENDAR UI] delete event error: {e}")

        elif result:
            # ── User saved (add or update) ────────────────────────────────────
            data = dlg.get_event_data()
            try:
                if event and event.id is not None:
                    self._svc.update_event(event.id, **data)
                    self._emit_bus("calendar_event_updated", {
                        "id": event.id,
                        "event_category": data.get("event_category", ""),
                    })
                else:
                    new_ev = self._svc.add_event(**data)
                    self._emit_bus("calendar_event_added", {
                        "id": new_ev.id,
                        "event_category": data.get("event_category", ""),
                    })
                self.refresh()
            except Exception as e:
                print(f"[CALENDAR UI] save event error: {e}")

    def _emit_bus(self, event_name: str, payload: dict):
        bus = getattr(self._ctx, "event_bus", None) if self._ctx else None
        if bus:
            try:
                bus.emit(event_name, payload)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════════════
    # Theme
    # ══════════════════════════════════════════════════════════════════════════

    def _on_theme_changed(self, _theme_id: str = ""):
        self._update_toolbar_style()

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _hline(self) -> QFrame:
        t = _tok(self._ctx)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {t['border']}; border: none;")
        return line
