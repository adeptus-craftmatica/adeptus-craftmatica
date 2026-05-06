"""Calendar domain models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


# ── Session type catalogue ─────────────────────────────────────────────────────

SESSION_TYPES: list[str] = [
    "Painting Session",
    "Building Session",
    "Priming Session",
    "Basing Session",
    "Kitbash Session",
    "Resin Printing",
    "Terrain Building",
    "Army Prep",
    "D&D Prep",
    "Campaign Writing",
    "Game Night",
    "Tournament Prep",
    "Inventory Check",
    "Paint Restock Review",
    "Custom",
]

SESSION_COLORS: dict[str, str] = {
    "Painting Session":     "#0078d4",
    "Building Session":     "#2e7d32",
    "Priming Session":      "#e07820",
    "Basing Session":       "#8b5e3c",
    "Kitbash Session":      "#7b1fa2",
    "Resin Printing":       "#00838f",
    "Terrain Building":     "#558b2f",
    "Army Prep":            "#c62828",
    "D&D Prep":             "#6a1b9a",
    "Campaign Writing":     "#283593",
    "Game Night":           "#f57f17",
    "Tournament Prep":      "#d84315",
    "Inventory Check":      "#37474f",
    "Paint Restock Review": "#1565c0",
    "Custom":               "#546e7a",
}

SESSION_ICONS: dict[str, str] = {
    "Painting Session":     "🎨",
    "Building Session":     "🔧",
    "Priming Session":      "💨",
    "Basing Session":       "🌿",
    "Kitbash Session":      "⚙",
    "Resin Printing":       "🖨",
    "Terrain Building":     "🏔",
    "Army Prep":            "⚔",
    "D&D Prep":             "🎲",
    "Campaign Writing":     "📖",
    "Game Night":           "🎮",
    "Tournament Prep":      "🏆",
    "Inventory Check":      "📋",
    "Paint Restock Review": "🛒",
    "Custom":               "📅",
}

# ── Event category system ──────────────────────────────────────────────────────
# Categories classify the *purpose* of an event.
# Colors/icons are resolved through the theme system (CATEGORY_THEME_TOKENS)
# rather than being hardcoded, so every theme remains visually consistent.

EVENT_CATEGORIES: list[str] = [
    "Hobby Session",
    "Purchase",
    "Campaign Event",
    "Deadline",
    "Milestone",
    "Completed Project",
    "Inventory Alert",
    "Timeline",      # auto-generated history record
    "Other",
]

# Maps category → theme token name.  Widgets call tm.token(ev.category_token())
# so colours follow the active theme rather than fixed hex values.
CATEGORY_THEME_TOKENS: dict[str, str] = {
    "Hobby Session":      "accent",
    "Purchase":           "warning",
    "Campaign Event":     "accent",
    "Deadline":           "danger",
    "Milestone":          "success",
    "Completed Project":  "success",
    "Inventory Alert":    "warning",
    "Timeline":           "text_mid",
    "Other":              "text_lo",
}

# Fallback hex values used only when a theme manager is unavailable.
# These are richer than the 4-token theme palette to maximise distinction.
CATEGORY_FALLBACK_COLORS: dict[str, str] = {
    "Hobby Session":      "#0078d4",   # blue
    "Purchase":           "#e07820",   # orange
    "Campaign Event":     "#7b1fa2",   # purple  (distinct from accent blue)
    "Deadline":           "#c62828",   # red
    "Milestone":          "#f9a825",   # gold    (distinct from success green)
    "Completed Project":  "#2e7d32",   # green
    "Inventory Alert":    "#f57f17",   # amber
    "Timeline":           "#607d8b",   # blue-grey
    "Other":              "#546e7a",   # grey
}

CATEGORY_ICONS: dict[str, str] = {
    "Hobby Session":      "🎨",
    "Purchase":           "🛒",
    "Campaign Event":     "⚔",
    "Deadline":           "⏰",
    "Milestone":          "🏆",
    "Completed Project":  "✅",
    "Inventory Alert":    "⚠️",
    "Timeline":           "📝",
    "Other":              "📅",
}

# Derive category from session_type for user-created events.
SESSION_TYPE_TO_CATEGORY: dict[str, str] = {
    "Painting Session":     "Hobby Session",
    "Building Session":     "Hobby Session",
    "Priming Session":      "Hobby Session",
    "Basing Session":       "Hobby Session",
    "Kitbash Session":      "Hobby Session",
    "Resin Printing":       "Hobby Session",
    "Terrain Building":     "Hobby Session",
    "Army Prep":            "Hobby Session",
    "D&D Prep":             "Campaign Event",
    "Campaign Writing":     "Campaign Event",
    "Game Night":           "Campaign Event",
    "Tournament Prep":      "Deadline",
    "Inventory Check":      "Inventory Alert",
    "Paint Restock Review": "Purchase",
    "Custom":               "Hobby Session",
}

# ── Other catalogues ───────────────────────────────────────────────────────────

RECURRENCE_LABELS: dict[str, str] = {
    "none":      "Does not repeat",
    "daily":     "Daily",
    "weekly":    "Weekly",
    "biweekly":  "Every 2 weeks",
    "monthly":   "Monthly",
}

REMINDER_OPTIONS: dict[int, str] = {
    0:    "No reminder",
    15:   "15 minutes before",
    30:   "30 minutes before",
    60:   "1 hour before",
    1440: "1 day before",
}

PRIORITY_LABELS: dict[int, str] = {
    1: "Urgent",
    2: "Important",
    3: "Normal",
}

PRIORITY_COLORS: dict[int, str] = {
    1: "#c62828",
    2: "#e07820",
    3: "#0078d4",
}


# ── Core domain model ─────────────────────────────────────────────────────────

@dataclass
class CalendarEvent:
    """A single scheduled hobby event, timeline record, or milestone."""

    title:            str
    session_type:     str  = "Custom"
    event_category:   str  = "Hobby Session"  # see EVENT_CATEGORIES
    event_date:       str  = ""               # ISO "YYYY-MM-DD"
    time_start:       str  = ""               # "HH:MM" or "" (all-day)
    duration_minutes: int  = 60
    notes:            str  = ""
    priority:         int  = 3                # 1=urgent  2=important  3=normal
    is_recurring:     bool = False
    recurrence_rule:  str  = "none"           # "daily|weekly|biweekly|monthly"
    recurrence_end:   str  = ""               # ISO date or ""
    linked_plugin:    str  = ""               # "paint_tracker" | "model_tracker" | …
    linked_id:        str  = ""
    linked_name:      str  = ""
    tags:             str  = ""               # comma-separated
    reminder_minutes: int  = 0
    completed:        bool = False
    auto_generated:   bool = False
    source_event:     str  = ""               # event-bus name that created this
    id: Optional[int]      = None

    # ── Colour / icon resolution ──────────────────────────────────────────────

    def category_token(self) -> str:
        """Return the theme token name for this event's category.

        Widgets use ``tm.token(ev.category_token())`` so colours follow the
        active theme rather than fixed hex values.
        """
        return CATEGORY_THEME_TOKENS.get(self.event_category, "text_lo")

    def category_color(self) -> str:
        """Fallback hex colour for this event's category (no theme manager)."""
        return CATEGORY_FALLBACK_COLORS.get(self.event_category, "#546e7a")

    def color(self) -> str:
        """Primary display colour — session-type palette for user events,
        category fallback for auto-generated timeline records."""
        if self.auto_generated:
            return self.category_color()
        return SESSION_COLORS.get(self.session_type, self.category_color())

    def icon(self) -> str:
        """Display icon — session-type icon for user events, category icon
        for auto-generated records."""
        if self.auto_generated:
            return CATEGORY_ICONS.get(self.event_category, "📅")
        return SESSION_ICONS.get(self.session_type, "📅")

    def category_icon(self) -> str:
        """Always return the category-level icon."""
        return CATEGORY_ICONS.get(self.event_category, "📅")

    # ── Date helpers ──────────────────────────────────────────────────────────

    def is_activity_record(self) -> bool:
        """True when this is an auto-generated history record, not a user-planned event.

        Activity records are passive logs (paint added, model bought, session logged).
        They should NEVER have completion checkboxes and NEVER appear in overdue/upcoming
        planning queues.  They are read-only history accessible through calendar views.
        """
        return self.auto_generated

    def is_all_day(self) -> bool:
        return not self.time_start

    def is_today(self) -> bool:
        return self.event_date == date.today().isoformat()

    def is_overdue(self) -> bool:
        if self.completed or not self.event_date:
            return False
        return self.event_date < date.today().isoformat()

    def is_upcoming(self, days: int = 7) -> bool:
        if not self.event_date:
            return False
        today = date.today()
        end   = today + timedelta(days=days)
        return today.isoformat() <= self.event_date <= end.isoformat()

    def days_until(self) -> Optional[int]:
        """Days from today until this event (negative = past)."""
        if not self.event_date:
            return None
        try:
            return (date.fromisoformat(self.event_date) - date.today()).days
        except (ValueError, TypeError):
            return None

    def days_since(self) -> Optional[int]:
        """Days elapsed since this event (positive = past)."""
        d = self.days_until()
        return -d if d is not None else None

    # ── Display helpers ───────────────────────────────────────────────────────

    def display_time(self) -> str:
        return self.time_start if self.time_start else "All day"

    def display_duration(self) -> str:
        m = self.duration_minutes
        if m <= 0:
            return ""
        if m < 60:
            return f"{m}m"
        h, rem = divmod(m, 60)
        return f"{h}h {rem}m" if rem else f"{h}h"

    def display_days_until(self) -> str:
        d = self.days_until()
        if d is None:
            return ""
        if d == 0:
            return "Today"
        if d == 1:
            return "Tomorrow"
        if d == -1:
            return "Yesterday"
        if d > 0:
            return f"{d} days"
        return f"{abs(d)}d ago"

    def priority_label(self) -> str:
        return PRIORITY_LABELS.get(self.priority, "Normal")

    def priority_color(self) -> str:
        return PRIORITY_COLORS.get(self.priority, "#0078d4")
