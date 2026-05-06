"""Tool Tracker dashboard provider."""
from __future__ import annotations

from core.contracts.dashboard_dto import (
    CommandStat, ProjectCard, Notification, QuickAction, Severity, Recommendation,
)


class ToolDashboardProvider:
    def __init__(self, service):
        self._svc = service

    def get_command_stats(self) -> list[CommandStat]:
        try:
            stats = self._svc.get_statistics()
            attn  = stats.needs_replacement
            return [
                CommandStat(
                    label    = "Tools",
                    value    = str(stats.total_count),
                    subtitle = f"{attn} need attention" if attn else "all good",
                    color    = "warning" if attn else "success",
                    icon     = "🔧",
                ),
            ]
        except Exception as e:
            print(f"[TOOL PROVIDER] get_command_stats: {e}")
            return []

    def get_project_cards(self) -> list[ProjectCard]:
        return []

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            tools   = self._svc.get_all_tools()
            replace = [t for t in tools if t.condition in ("Worn", "Replace")]
            if replace:
                names = ", ".join(t.name for t in replace[:4])
                if len(replace) > 4:
                    names += f" +{len(replace) - 4} more"
                notes.append(Notification(
                    title          = f"{len(replace)} tool{'s' if len(replace) != 1 else ''} "
                                     f"need{'s' if len(replace) == 1 else ''} attention",
                    body           = names,
                    severity       = Severity.WARNING,
                    plugin_id      = "tool_tracker",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "tool_tracker"},
                    action_label   = "View Tools",
                ))
        except Exception as e:
            print(f"[TOOL PROVIDER] get_notifications: {e}")
        return notes

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        nav = {"plugin_id": "tool_tracker"}
        try:
            tools   = self._svc.get_all_tools()
            replace = [t for t in tools if t.condition == "Replace"]
            worn    = [t for t in tools if t.condition == "Worn"]
            for t in replace[:2]:
                recs.append(Recommendation(
                    action="Replace", target=t.name,
                    context="condition: needs replacing",
                    priority=1, plugin_id="tool_tracker", icon="🔧",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Tools",
                ))
            for t in worn[:1]:
                recs.append(Recommendation(
                    action="Check condition", target=t.name,
                    context="showing wear — inspect soon",
                    priority=2, plugin_id="tool_tracker", icon="🔧",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Tools",
                ))
        except Exception as e:
            print(f"[TOOL PROVIDER] get_recommendations: {e}")
        return recs

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction("Add Tool", "🔧", "dashboard_navigate",
                        {"plugin_id": "tool_tracker"}, "success"),
        ]
