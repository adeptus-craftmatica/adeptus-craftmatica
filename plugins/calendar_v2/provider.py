"""
Calendar Dashboard Provider

Implements the duck-typed dashboard provider interface so the DashboardRegistry
can aggregate calendar data alongside other plugins.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.contracts.dashboard_dto import (
    CommandStat,
    Notification,
    ProjectCard,
    QuickAction,
    Recommendation,
)

from .service import CalendarService


class CalendarDashboardProvider:
    """Provides dashboard data sourced from CalendarService."""

    def __init__(self, service: CalendarService):
        self._service = service

    # ── CommandStat strip ─────────────────────────────────────────────────────

    def get_command_stats(self) -> list[CommandStat]:
        try:
            stats = self._service.get_stats()
        except Exception as e:
            log.error(f"[CALENDAR PROVIDER] get_stats failed: {e}")
            return []

        today_count   = stats.get("today", 0)
        week_count    = stats.get("week", 0)
        overdue_count = stats.get("overdue", 0)

        result: list[CommandStat] = []

        # 1. Today
        result.append(CommandStat(
            label    = "Today",
            value    = str(today_count),
            subtitle = f"{today_count} session{'s' if today_count != 1 else ''}" if today_count > 0 else "Rest day",
            color    = "success" if today_count > 0 else "accent",
            icon     = "📅",
        ))

        # 2. This Week
        result.append(CommandStat(
            label    = "This Week",
            value    = str(week_count),
            subtitle = "sessions scheduled",
            color    = "accent",
            icon     = "📆",
        ))

        # 3. Overdue (only include if there are overdue items)
        if overdue_count > 0:
            result.append(CommandStat(
                label    = "Overdue",
                value    = str(overdue_count),
                subtitle = "need attention",
                color    = "danger",
                icon     = "⚠️",
            ))

        return result

    # ── ProjectCard feed ──────────────────────────────────────────────────────

    def get_project_cards(self) -> list[ProjectCard]:
        try:
            events = self._service.get_upcoming(days=30)
        except Exception as e:
            log.error(f"[CALENDAR PROVIDER] get_upcoming failed: {e}")
            return []

        cards: list[ProjectCard] = []
        for event in events[:5]:
            detail_lines = [
                line for line in [event.event_date, event.linked_name]
                if line
            ]
            cards.append(ProjectCard(
                id             = event.id,
                plugin_id      = "calendar",
                plugin_label   = "Calendar",
                title          = event.title,
                subtitle       = f"{event.display_time()} · {event.session_type}",
                status         = event.session_type,
                status_color   = "accent",
                action_label   = "Open",
                action_event   = "dashboard_navigate",
                action_payload = {"plugin_id": "calendar"},
                detail_lines   = detail_lines,
            ))
        return cards

    # ── Notifications ─────────────────────────────────────────────────────────

    def get_notifications(self) -> list[Notification]:
        notifications: list[Notification] = []

        # Overdue events → critical (up to 3)
        try:
            overdue = self._service.get_overdue()
        except Exception as e:
            log.error(f"[CALENDAR PROVIDER] get_overdue failed: {e}")
            overdue = []

        for event in overdue[:3]:
            notifications.append(Notification(
                title          = f"Overdue: {event.title}",
                body           = f"Was scheduled for {event.event_date}",
                severity       = "critical",
                plugin_id      = "calendar",
                action_event   = "dashboard_navigate",
                action_payload = {"plugin_id": "calendar"},
                action_label   = "View",
            ))

        # Today's events → info summary if any
        try:
            today_events = self._service.get_today()
        except Exception as e:
            log.error(f"[CALENDAR PROVIDER] get_today failed: {e}")
            today_events = []

        count = len(today_events)
        if count > 0:
            notifications.append(Notification(
                title          = f"{count} session{'s' if count > 1 else ''} today",
                body           = "",
                severity       = "info",
                plugin_id      = "calendar",
                action_event   = "dashboard_navigate",
                action_payload = {"plugin_id": "calendar"},
                action_label   = "View",
            ))

        return notifications

    # ── Quick actions ─────────────────────────────────────────────────────────

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction(
                label   = "View Calendar",
                icon    = "📅",
                event   = "dashboard_navigate",
                payload = {"plugin_id": "calendar"},
                color   = "accent",
            ),
            QuickAction(
                label   = "Schedule Session",
                icon    = "＋",
                event   = "dashboard_navigate",
                payload = {"plugin_id": "calendar"},
                color   = "accent",
            ),
        ]

    # ── Recommendations ───────────────────────────────────────────────────────

    def get_recommendations(self) -> list[Recommendation]:
        recommendations: list[Recommendation] = []

        # Overdue → priority 1
        try:
            overdue = self._service.get_overdue()
        except Exception as e:
            log.error(f"[CALENDAR PROVIDER] get_overdue (recommendations) failed: {e}")
            overdue = []

        for event in overdue:
            recommendations.append(Recommendation(
                action         = "Reschedule",
                target         = event.title,
                context        = "overdue",
                priority       = 1,
                plugin_id      = "calendar",
                action_event   = "dashboard_navigate",
                action_payload = {"plugin_id": "calendar"},
                action_label   = "View",
                icon           = "⚠️",
            ))

        # Today's events not completed → priority 2
        try:
            today_events = self._service.get_today()
        except Exception as e:
            log.error(f"[CALENDAR PROVIDER] get_today (recommendations) failed: {e}")
            today_events = []

        for event in today_events:
            if not event.completed:
                recommendations.append(Recommendation(
                    action         = "Complete",
                    target         = event.title,
                    context        = "today",
                    priority       = 2,
                    plugin_id      = "calendar",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "calendar"},
                    action_label   = "View",
                    icon           = "📅",
                ))

        # Upcoming urgent (priority=1) events → priority 2
        try:
            upcoming = self._service.get_upcoming(days=30)
        except Exception as e:
            log.error(f"[CALENDAR PROVIDER] get_upcoming (recommendations) failed: {e}")
            upcoming = []

        for event in upcoming:
            if event.priority == 1:
                recommendations.append(Recommendation(
                    action         = "Prepare for",
                    target         = event.title,
                    context        = f"on {event.event_date}",
                    priority       = 2,
                    plugin_id      = "calendar",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "calendar"},
                    action_label   = "View",
                    icon           = "📆",
                ))

        # Sort by priority and cap at 5
        recommendations.sort(key=lambda r: r.priority)
        return recommendations[:5]
