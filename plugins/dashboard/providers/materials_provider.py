"""Materials Tracker dashboard provider."""
from __future__ import annotations

from core.contracts.dashboard_dto import (
    CommandStat, ProjectCard, Notification, QuickAction, Severity, Recommendation,
)


class MaterialsDashboardProvider:
    def __init__(self, service):
        self._svc = service

    def get_command_stats(self) -> list[CommandStat]:
        try:
            stats = self._svc.get_statistics()
            low   = stats.needs_restock
            return [
                CommandStat(
                    label    = "Materials",
                    value    = str(stats.total_count),
                    subtitle = f"{low} low / empty" if low else "fully stocked",
                    color    = "warning" if low else "success",
                    icon     = "🌿",
                ),
            ]
        except Exception as e:
            print(f"[MATERIALS PROVIDER] get_command_stats: {e}")
            return []

    def get_project_cards(self) -> list[ProjectCard]:
        return []

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            materials = self._svc.get_all_materials()
            low       = [m for m in materials if m.stock in ("Low", "Empty")]
            if low:
                has_empty = any(m.stock == "Empty" for m in low)
                severity  = Severity.CRITICAL if has_empty else Severity.WARNING
                names     = ", ".join(m.name for m in low[:4])
                if len(low) > 4:
                    names += f" +{len(low) - 4} more"
                notes.append(Notification(
                    title          = f"{len(low)} material{'s' if len(low) != 1 else ''} "
                                     f"running low",
                    body           = names,
                    severity       = severity,
                    plugin_id      = "materials_tracker",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "materials_tracker"},
                    action_label   = "View Materials",
                ))
        except Exception as e:
            print(f"[MATERIALS PROVIDER] get_notifications: {e}")
        return notes

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        nav = {"plugin_id": "materials_tracker"}
        try:
            materials = self._svc.get_all_materials()
            empty = [m for m in materials if m.stock == "Empty"]
            low   = [m for m in materials if m.stock == "Low"]
            for m in empty[:2]:
                recs.append(Recommendation(
                    action="Restock", target=m.name,
                    context=f"completely out of {m.material_type.lower()}",
                    priority=1, plugin_id="materials_tracker", icon="🌿",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Materials",
                ))
            for m in low[:1]:
                recs.append(Recommendation(
                    action="Restock", target=m.name,
                    context="running low",
                    priority=2, plugin_id="materials_tracker", icon="🌿",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Materials",
                ))
        except Exception as e:
            print(f"[MATERIALS PROVIDER] get_recommendations: {e}")
        return recs

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction("Add Material", "🌿", "dashboard_navigate",
                        {"plugin_id": "materials_tracker"}, "success"),
        ]
