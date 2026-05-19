"""Calendar repository — SQLite persistence."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from core.migrations import SchemaManager
from .models import CalendarEvent

_TABLE = "calendar_events"


class CalendarRepository:
    _MIGRATIONS: list[str] = [
        "ALTER TABLE calendar_events ADD COLUMN event_category TEXT NOT NULL DEFAULT 'Hobby Session'",
    ]

    def __init__(self, db):
        self.db = db
        self._ensure_schema()
        SchemaManager(db).migrate("calendar", self._MIGRATIONS)

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _ensure_schema(self):
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                title             TEXT    NOT NULL,
                session_type      TEXT    NOT NULL DEFAULT 'Custom',
                event_category    TEXT    NOT NULL DEFAULT 'Hobby Session',
                event_date        TEXT    NOT NULL DEFAULT '',
                time_start        TEXT    NOT NULL DEFAULT '',
                duration_minutes  INTEGER NOT NULL DEFAULT 60,
                notes             TEXT    NOT NULL DEFAULT '',
                priority          INTEGER NOT NULL DEFAULT 3,
                is_recurring      INTEGER NOT NULL DEFAULT 0,
                recurrence_rule   TEXT    NOT NULL DEFAULT 'none',
                recurrence_end    TEXT    NOT NULL DEFAULT '',
                linked_plugin     TEXT    NOT NULL DEFAULT '',
                linked_id         TEXT    NOT NULL DEFAULT '',
                linked_name       TEXT    NOT NULL DEFAULT '',
                tags              TEXT    NOT NULL DEFAULT '',
                reminder_minutes  INTEGER NOT NULL DEFAULT 0,
                completed         INTEGER NOT NULL DEFAULT 0,
                auto_generated    INTEGER NOT NULL DEFAULT 0,
                source_event      TEXT    NOT NULL DEFAULT '',
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_cal_date   ON {_TABLE}(event_date)"
        )
        self.db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_cal_plugin ON {_TABLE}(linked_plugin)"
        )
        self.db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_cal_done   ON {_TABLE}(completed)"
        )

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def add(self, ev: CalendarEvent) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {_TABLE}
                (title, session_type, event_category, event_date, time_start,
                 duration_minutes, notes, priority, is_recurring, recurrence_rule,
                 recurrence_end, linked_plugin, linked_id, linked_name, tags,
                 reminder_minutes, completed, auto_generated, source_event)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ev.title, ev.session_type, ev.event_category, ev.event_date,
            ev.time_start, ev.duration_minutes, ev.notes, ev.priority,
            int(ev.is_recurring), ev.recurrence_rule, ev.recurrence_end,
            ev.linked_plugin, ev.linked_id, ev.linked_name, ev.tags,
            ev.reminder_minutes, int(ev.completed),
            int(ev.auto_generated), ev.source_event,
        ))
        return cur.lastrowid

    def get_by_id(self, event_id: int) -> Optional[CalendarEvent]:
        rows = self.db.query(f"SELECT * FROM {_TABLE} WHERE id=?", (event_id,))
        return self._row(rows[0]) if rows else None

    def get_all(self) -> list[CalendarEvent]:
        rows = self.db.query(
            f"SELECT * FROM {_TABLE} ORDER BY event_date, time_start"
        )
        return [self._row(r) for r in rows]

    def get_by_date(self, date_iso: str) -> list[CalendarEvent]:
        rows = self.db.query(
            f"SELECT * FROM {_TABLE} WHERE event_date=? ORDER BY time_start, title",
            (date_iso,),
        )
        return [self._row(r) for r in rows]

    def get_range(self, start: str, end: str) -> list[CalendarEvent]:
        rows = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE event_date>=? AND event_date<=? "
            f"ORDER BY event_date, time_start",
            (start, end),
        )
        return [self._row(r) for r in rows]

    def get_upcoming(self, days: int = 30) -> list[CalendarEvent]:
        """Upcoming *planned* events (excludes auto-generated activity records)."""
        today = date.today().isoformat()
        end   = (date.today() + timedelta(days=days)).isoformat()
        rows  = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE event_date>=? AND event_date<=? AND completed=0 AND auto_generated=0 "
            f"ORDER BY event_date, time_start",
            (today, end),
        )
        return [self._row(r) for r in rows]

    def get_overdue(self) -> list[CalendarEvent]:
        """Overdue *planned* events only — activity records can never be overdue."""
        today = date.today().isoformat()
        rows  = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE event_date<? AND completed=0 AND auto_generated=0 "
            f"ORDER BY event_date DESC, time_start",
            (today,),
        )
        return [self._row(r) for r in rows]

    def get_today(self) -> list[CalendarEvent]:
        """All events for today — both planned and activity (for month/week/agenda views)."""
        return self.get_by_date(date.today().isoformat())

    def get_today_planned(self) -> list[CalendarEvent]:
        """User-created planned events for today only (no auto-generated records)."""
        rows = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE event_date=? AND auto_generated=0 "
            f"ORDER BY time_start, title",
            (date.today().isoformat(),),
        )
        return [self._row(r) for r in rows]

    def get_today_activity(self) -> list[CalendarEvent]:
        """Auto-generated history records for today (no user-created planned events)."""
        rows = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE event_date=? AND auto_generated=1 "
            f"ORDER BY time_start, title",
            (date.today().isoformat(),),
        )
        return [self._row(r) for r in rows]

    def get_upcoming_planned(self, start: str, end: str) -> list[CalendarEvent]:
        """Planned (non-auto-generated) events in a date range for use in planning views."""
        rows = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE event_date>=? AND event_date<=? AND auto_generated=0 "
            f"ORDER BY event_date, time_start",
            (start, end),
        )
        return [self._row(r) for r in rows]

    def update(self, ev: CalendarEvent) -> bool:
        if ev.id is None:
            return False
        cur = self.db.execute(f"""
            UPDATE {_TABLE} SET
                title=?, session_type=?, event_category=?, event_date=?,
                time_start=?, duration_minutes=?, notes=?, priority=?,
                is_recurring=?, recurrence_rule=?, recurrence_end=?,
                linked_plugin=?, linked_id=?, linked_name=?, tags=?,
                reminder_minutes=?, completed=?, auto_generated=?, source_event=?
            WHERE id=?
        """, (
            ev.title, ev.session_type, ev.event_category, ev.event_date,
            ev.time_start, ev.duration_minutes, ev.notes, ev.priority,
            int(ev.is_recurring), ev.recurrence_rule, ev.recurrence_end,
            ev.linked_plugin, ev.linked_id, ev.linked_name, ev.tags,
            ev.reminder_minutes, int(ev.completed),
            int(ev.auto_generated), ev.source_event,
            ev.id,
        ))
        return cur.rowcount > 0

    def delete(self, event_id: int) -> bool:
        cur = self.db.execute(f"DELETE FROM {_TABLE} WHERE id=?", (event_id,))
        return cur.rowcount > 0

    # ── Aggregate queries ──────────────────────────────────────────────────────

    def count_today(self) -> int:
        rows = self.db.query(
            f"SELECT COUNT(*) AS c FROM {_TABLE} WHERE event_date=?",
            (date.today().isoformat(),),
        )
        return rows[0]["c"] if rows else 0

    def count_upcoming(self, days: int = 7) -> int:
        """Count upcoming *planned* events only (excludes auto-generated records)."""
        today = date.today().isoformat()
        end   = (date.today() + timedelta(days=days)).isoformat()
        rows  = self.db.query(
            f"SELECT COUNT(*) AS c FROM {_TABLE} "
            f"WHERE event_date>=? AND event_date<=? AND completed=0 AND auto_generated=0",
            (today, end),
        )
        return rows[0]["c"] if rows else 0

    def count_overdue(self) -> int:
        """Count overdue *planned* events only (activity records can never be overdue)."""
        rows = self.db.query(
            f"SELECT COUNT(*) AS c FROM {_TABLE} "
            f"WHERE event_date<? AND completed=0 AND auto_generated=0",
            (date.today().isoformat(),),
        )
        return rows[0]["c"] if rows else 0

    def get_upcoming_by_category(self, category: str, days: int = 365) -> list[CalendarEvent]:
        today = date.today().isoformat()
        end   = (date.today() + timedelta(days=days)).isoformat()
        rows  = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE event_category=? AND event_date>=? AND event_date<=? AND completed=0 "
            f"ORDER BY event_date, time_start",
            (category, today, end),
        )
        return [self._row(r) for r in rows]

    def get_by_category_and_date_range(self, category: str, start: str, end: str) -> list[CalendarEvent]:
        rows = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE event_category=? AND event_date>=? AND event_date<=? "
            f"ORDER BY event_date, time_start",
            (category, start, end),
        )
        return [self._row(r) for r in rows]

    def get_timeline(self, start: str, end: str) -> list[CalendarEvent]:
        """All events (auto-generated + manual) in a date range — the full hobby history."""
        rows = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE event_date>=? AND event_date<=? "
            f"ORDER BY event_date, time_start",
            (start, end),
        )
        return [self._row(r) for r in rows]

    def search(self, query: str) -> list[CalendarEvent]:
        q = f"%{query.lower()}%"
        rows = self.db.query(
            f"SELECT * FROM {_TABLE} "
            f"WHERE LOWER(title) LIKE ? OR LOWER(notes) LIKE ? OR LOWER(linked_name) LIKE ? "
            f"ORDER BY event_date",
            (q, q, q),
        )
        return [self._row(r) for r in rows]

    # ── Row mapper ─────────────────────────────────────────────────────────────

    def _row(self, r) -> CalendarEvent:
        keys = r.keys() if hasattr(r, "keys") else []
        def _get(k, default=""):
            return r[k] if k in keys else default

        return CalendarEvent(
            id               = r["id"],
            title            = r["title"],
            session_type     = _get("session_type", "Custom"),
            event_category   = _get("event_category", "Hobby Session"),
            event_date       = _get("event_date"),
            time_start       = _get("time_start"),
            duration_minutes = _get("duration_minutes") or 60,
            notes            = _get("notes"),
            priority         = _get("priority") or 3,
            is_recurring     = bool(_get("is_recurring", 0)),
            recurrence_rule  = _get("recurrence_rule", "none"),
            recurrence_end   = _get("recurrence_end"),
            linked_plugin    = _get("linked_plugin"),
            linked_id        = _get("linked_id"),
            linked_name      = _get("linked_name"),
            tags             = _get("tags"),
            reminder_minutes = _get("reminder_minutes") or 0,
            completed        = bool(_get("completed", 0)),
            auto_generated   = bool(_get("auto_generated", 0)),
            source_event     = _get("source_event"),
        )
