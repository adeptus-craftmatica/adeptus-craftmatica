"""Dashboard provider for Tool Tracker 2.0."""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.contracts.dashboard_dto import (
    CommandStat,
    ProjectCard,
    Notification,
    QuickAction,
    Recommendation,
    Severity,
)

from plugins.tool_tracker.models import TOOL_CONDITIONS

# Map tool types to emojis for recommendations
_TYPE_ICONS: dict[str, str] = {
    "Nippers":              "✂️",
    "Hobby Knife / Blade":  "🔪",
    "File":                 "📐",
    "Sandpaper":            "〰️",
    "Brush":                "🖌️",
    "Airbrush":             "💨",
    "Drill / Pin Vice":     "🔩",
    "Sculpting Tool":       "🗿",
    "Tweezers":             "🩺",
    "Plastic Glue":         "🧴",
    "Super Glue":           "🧪",
    "Green Stuff / Putty":  "🟢",
    "Cutting Mat":          "🟦",
    "Painting Handle":      "🖊️",
    "Spray Can":            "🫧",
    "Other":                "🔧",
}


def _type_icon(t: str) -> str:
    return _TYPE_ICONS.get(t, "🔧")


class ToolTrackerDashboardProviderV2:
    def __init__(self, service):
        self._svc = service

    # ── CommandStats ──────────────────────────────────────────────────────────

    def get_command_stats(self) -> list[CommandStat]:
        try:
            stats      = self._svc.get_statistics()
            total      = stats.total_count
            needs_attn = stats.needs_replacement  # worn + replace

            stats_list = [
                CommandStat(
                    label    = "Tools",
                    value    = str(total),
                    subtitle = f"{needs_attn} need attention",
                    icon     = "🔧",
                    color    = "accent",
                    card_id  = "tool_tracker.tools",
                ),
            ]

            worn_count    = stats.conditions_distribution.get("Worn", 0)
            replace_count = stats.conditions_distribution.get("Replace", 0)
            attn_count    = worn_count + replace_count
            if attn_count > 0:
                stats_list.append(
                    CommandStat(
                        label    = "Need Attention",
                        value    = str(attn_count),
                        subtitle = "worn or replace",
                        icon     = "⚠️",
                        color    = "danger" if replace_count > 0 else "warning",
                        card_id  = "tool_tracker.need_attention",
                    )
                )

            return stats_list

        except Exception as e:
            log.error(f"[TOOL TRACKER V2 PROVIDER] get_command_stats: {e}")
            return []

    # ── Notifications ─────────────────────────────────────────────────────────

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            tools   = self._svc.get_all_tools()
            replace = [t for t in tools if t.condition == "Replace"]

            for tool in replace:
                notes.append(Notification(
                    title          = f"Replace: {tool.name}",
                    body           = f"{tool.tool_type} — {tool.brand or 'No brand'}",
                    severity       = Severity.WARNING,
                    plugin_id      = "tool_tracker_v2",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "tool_tracker_v2"},
                    action_label   = "View",
                ))
        except Exception as e:
            log.error(f"[TOOL TRACKER V2 PROVIDER] get_notifications: {e}")
        return notes

    # ── QuickActions ──────────────────────────────────────────────────────────

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction(
                "Open Toolkit", "🔧",
                "dashboard_navigate",
                {"plugin_id": "tool_tracker_v2"},
                "accent",
            ),
        ]

    # ── Recommendations ───────────────────────────────────────────────────────

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        try:
            tools = self._svc.get_all_tools()
            worn    = [t for t in tools if t.condition == "Worn"]
            replace = [t for t in tools if t.condition == "Replace"]

            candidates = ([(t, 1) for t in replace] + [(t, 2) for t in worn])[:4]

            for tool, priority in candidates:
                recs.append(Recommendation(
                    action         = "Replace tool",
                    target         = tool.name,
                    context        = f"{tool.condition} — {tool.tool_type}",
                    priority       = priority,
                    plugin_id      = "tool_tracker_v2",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "tool_tracker_v2"},
                    action_label   = "View",
                    icon           = _type_icon(tool.tool_type),
                ))
        except Exception as e:
            log.error(f"[TOOL TRACKER V2 PROVIDER] get_recommendations: {e}")
        return recs

    # ── Stubs ─────────────────────────────────────────────────────────────────

    def get_project_cards(self) -> list[ProjectCard]:
        return []
