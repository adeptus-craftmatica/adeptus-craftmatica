"""Calendar service — business logic layer."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

from .models import CalendarEvent, SESSION_TYPES, SESSION_TYPE_TO_CATEGORY, EVENT_CATEGORIES
from .repository import CalendarRepository


class CalendarService:
    def __init__(self, repo: CalendarRepository):
        self.repo = repo

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def add_event(
        self,
        title: str,
        session_type: str = "Custom",
        event_category: str = "",        # inferred from session_type when blank
        event_date: str = "",
        time_start: str = "",
        duration_minutes: int = 60,
        notes: str = "",
        priority: int = 3,
        is_recurring: bool = False,
        recurrence_rule: str = "none",
        recurrence_end: str = "",
        linked_plugin: str = "",
        linked_id: str = "",
        linked_name: str = "",
        tags: str = "",
        reminder_minutes: int = 0,
        completed: bool = False,
        auto_generated: bool = False,
        source_event: str = "",
    ) -> CalendarEvent:
        if not title.strip():
            raise ValueError("Event title cannot be empty")
        if not event_date:
            event_date = date.today().isoformat()

        safe_type = session_type if session_type in SESSION_TYPES else "Custom"

        # Derive category from session_type when caller doesn't specify one
        if not event_category or event_category not in EVENT_CATEGORIES:
            event_category = SESSION_TYPE_TO_CATEGORY.get(safe_type, "Hobby Session")

        ev = CalendarEvent(
            title            = title.strip(),
            session_type     = safe_type,
            event_category   = event_category,
            event_date       = event_date,
            time_start       = time_start,
            duration_minutes = max(0, duration_minutes),
            notes            = notes,
            priority         = max(1, min(3, priority)),
            is_recurring     = is_recurring,
            recurrence_rule  = recurrence_rule,
            recurrence_end   = recurrence_end,
            linked_plugin    = linked_plugin,
            linked_id        = linked_id,
            linked_name      = linked_name,
            tags             = tags,
            reminder_minutes = reminder_minutes,
            completed        = completed,
            auto_generated   = auto_generated,
            source_event     = source_event,
        )
        ev.id = self.repo.add(ev)
        return ev

    def update_event(self, event_id: int, **kwargs) -> CalendarEvent:
        ev = self.repo.get_by_id(event_id)
        if not ev:
            raise ValueError(f"Event {event_id} not found")
        for k, v in kwargs.items():
            if hasattr(ev, k):
                setattr(ev, k, v)
        if not ev.title.strip():
            raise ValueError("Event title cannot be empty")
        self.repo.update(ev)
        return ev

    def delete_event(self, event_id: int) -> bool:
        return self.repo.delete(event_id)

    def complete_event(self, event_id: int) -> bool:
        ev = self.repo.get_by_id(event_id)
        if not ev:
            return False
        ev.completed = True
        return self.repo.update(ev)

    def uncomplete_event(self, event_id: int) -> bool:
        ev = self.repo.get_by_id(event_id)
        if not ev:
            return False
        ev.completed = False
        return self.repo.update(ev)

    def get_event(self, event_id: int) -> Optional[CalendarEvent]:
        return self.repo.get_by_id(event_id)

    # ── Calendar view queries ─────────────────────────────────────────────────

    def get_events_for_month(self, year: int, month: int) -> list[CalendarEvent]:
        """All events in a calendar month (including any partial-week days shown)."""
        first = date(year, month, 1)
        # Include leading days from previous month shown in the grid
        start = first - timedelta(days=first.weekday())   # Monday of first week
        end   = start + timedelta(days=41)                # 6 weeks = 42 days
        return self.repo.get_range(start.isoformat(), end.isoformat())

    def get_events_for_week(self, year: int, week: int) -> list[CalendarEvent]:
        """All events in an ISO week."""
        monday = date.fromisocalendar(year, week, 1)
        sunday = monday + timedelta(days=6)
        return self.repo.get_range(monday.isoformat(), sunday.isoformat())

    def get_events_for_date(self, d: date) -> list[CalendarEvent]:
        return self.repo.get_by_date(d.isoformat())

    def get_today(self) -> list[CalendarEvent]:
        """All events for today — both planned and activity records.

        Used by month/week/agenda views where all events should appear on the grid.
        """
        return self.repo.get_today()

    def get_today_planned(self) -> list[CalendarEvent]:
        """User-created planned events for today.

        Used by TodayView 'Planned Today' section — supports checkboxes.
        """
        return self.repo.get_today_planned()

    def get_today_activity(self) -> list[CalendarEvent]:
        """Auto-generated history records logged today.

        Used by TodayView 'Activity Today' section — no checkboxes, read-only display.
        """
        return self.repo.get_today_activity()

    def get_upcoming(self, days: int = 30) -> list[CalendarEvent]:
        """Upcoming planned events (excludes auto-generated activity records)."""
        return self.repo.get_upcoming(days)

    def get_overdue(self) -> list[CalendarEvent]:
        """Overdue planned events (activity records can never be overdue)."""
        return self.repo.get_overdue()

    def get_upcoming_week(self) -> list[CalendarEvent]:
        """Planned events from tomorrow through 6 days from now (excludes today).

        Used by the TodayView 'Upcoming This Week' and dashboard 'This Week' sections.
        Excludes auto-generated activity records — only user-planned events belong here.
        """
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        end      = (date.today() + timedelta(days=7)).isoformat()
        return self.repo.get_upcoming_planned(tomorrow, end)

    def get_milestones(self) -> list[CalendarEvent]:
        """Upcoming milestone events sorted by date (up to 1 year ahead)."""
        return self.repo.get_upcoming_by_category("Milestone", days=365)

    def get_deadlines(self) -> list[CalendarEvent]:
        """Upcoming deadline events sorted by date (up to 90 days ahead)."""
        return self.repo.get_upcoming_by_category("Deadline", days=90)

    def get_history_for_date(self, d: date) -> list[CalendarEvent]:
        """All events (manual + auto-generated) on a specific date — the timeline view."""
        return self.repo.get_by_date(d.isoformat())

    def get_timeline_range(self, start: date, end: date) -> list[CalendarEvent]:
        """Full event history in a date range, for 'On This Day' style insights."""
        return self.repo.get_timeline(start.isoformat(), end.isoformat())

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "today":    self.repo.count_today(),
            "week":     self.repo.count_upcoming(7),
            "overdue":  self.repo.count_overdue(),
            "upcoming": self.repo.count_upcoming(30),
        }

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str) -> list[CalendarEvent]:
        if not query.strip():
            return []
        return self.repo.search(query.strip())

    # ── Recurrence expansion ─────────────────────────────────────────────────

    def expand_recurring_event(self, ev: CalendarEvent, months_ahead: int = 3) -> list[CalendarEvent]:
        """
        Return a list of virtual (unsaved) occurrences of a recurring event
        within the next `months_ahead` months.  Does not write to the DB.
        """
        if not ev.is_recurring or ev.recurrence_rule == "none":
            return []

        results: list[CalendarEvent] = []
        try:
            base  = date.fromisoformat(ev.event_date)
            today = date.today()
            end_d = today + timedelta(days=months_ahead * 30)
            if ev.recurrence_end:
                end_d = min(end_d, date.fromisoformat(ev.recurrence_end))

            rule = ev.recurrence_rule
            cur  = base

            for _ in range(200):  # safety cap
                cur = self._next_occurrence(cur, rule)
                if cur > end_d:
                    break
                clone = CalendarEvent(
                    title            = ev.title,
                    session_type     = ev.session_type,
                    event_date       = cur.isoformat(),
                    time_start       = ev.time_start,
                    duration_minutes = ev.duration_minutes,
                    notes            = ev.notes,
                    priority         = ev.priority,
                    is_recurring     = True,
                    recurrence_rule  = ev.recurrence_rule,
                    linked_plugin    = ev.linked_plugin,
                    linked_id        = ev.linked_id,
                    linked_name      = ev.linked_name,
                    tags             = ev.tags,
                    reminder_minutes = ev.reminder_minutes,
                    auto_generated   = True,
                    source_event     = f"recurrence:{ev.id}",
                    id               = None,  # virtual
                )
                results.append(clone)
        except Exception as e:
            print(f"[CALENDAR] Recurrence expansion error: {e}")

        return results

    def _next_occurrence(self, d: date, rule: str) -> date:
        if rule == "daily":
            return d + timedelta(days=1)
        if rule == "weekly":
            return d + timedelta(weeks=1)
        if rule == "biweekly":
            return d + timedelta(weeks=2)
        if rule == "monthly":
            month = d.month + 1
            year  = d.year
            if month > 12:
                month = 1
                year += 1
            day = min(d.day, calendar.monthrange(year, month)[1])
            return date(year, month, day)
        return d + timedelta(days=1)

    # ── Auto-generation from events ───────────────────────────────────────────

    def suggest_session_for_model(self, model_name: str, model_id: str, status: str) -> Optional[CalendarEvent]:
        """Return a suggested (unsaved) event for a model based on its status."""
        session_map = {
            "Unassembled": ("Building Session",  "🔧 Assemble"),
            "Assembled":   ("Priming Session",   "💨 Prime"),
            "Primed":      ("Painting Session",  "🎨 Start painting"),
            "WIP":         ("Painting Session",  "🎨 Continue painting"),
        }
        if status not in session_map:
            return None
        stype, verb = session_map[status]
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        return CalendarEvent(
            title         = f"{verb}: {model_name}",
            session_type  = stype,
            event_date    = tomorrow,
            duration_minutes = 120,
            priority      = 2,
            linked_plugin = "model_tracker",
            linked_id     = str(model_id),
            linked_name   = model_name,
            auto_generated = True,
            source_event  = "model_status_suggest",
        )
