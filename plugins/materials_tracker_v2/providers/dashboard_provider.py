"""Dashboard provider for Materials Tracker 2.0."""
from __future__ import annotations

from core.contracts.dashboard_dto import (
    CommandStat,
    ProjectCard,
    Notification,
    QuickAction,
    Recommendation,
    Severity,
)


class MaterialsDashboardProviderV2:
    def __init__(self, service):
        self._svc = service

    # ── CommandStats ──────────────────────────────────────────────────────────

    def get_command_stats(self) -> list[CommandStat]:
        try:
            stats    = self._svc.get_statistics()
            total    = stats.total_count
            low      = stats.needs_restock
            on_order = stats.stock_distribution.get("On Order", 0)
            empty    = stats.stock_distribution.get("Empty", 0)

            restock_sub = (
                f"{empty} out of stock" if empty > 0
                else "need restocking"  if low > 0
                else "all stocked up"
            )

            return [
                CommandStat(
                    label    = "Materials",
                    value    = str(total),
                    subtitle = f"{stats.unique_types} type{'s' if stats.unique_types != 1 else ''}",
                    icon     = "🌿",
                    color    = "accent",
                    card_id  = "materials_tracker.materials",
                ),
                CommandStat(
                    label    = "Needs Restock",
                    value    = str(low),
                    subtitle = restock_sub,
                    icon     = "⚠️",
                    color    = "danger" if empty > 0 else ("warning" if low > 0 else "success"),
                    card_id  = "materials_tracker.needs_restock",
                ),
                CommandStat(
                    label    = "On Order",
                    value    = str(on_order),
                    subtitle = "arriving soon" if on_order > 0 else "nothing pending",
                    icon     = "📦",
                    color    = "accent" if on_order > 0 else "accent",
                    card_id  = "materials_tracker.on_order",
                ),
            ]
        except Exception as e:
            print(f"[MATERIALS V2 PROVIDER] get_command_stats: {e}")
            return []

    # ── Notifications ─────────────────────────────────────────────────────────

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            materials = self._svc.get_all_materials()
            empty     = [m for m in materials if m.stock == "Empty"]
            low       = [m for m in materials if m.stock == "Low"]

            if empty:
                names = ", ".join(m.name for m in empty[:4])
                if len(empty) > 4:
                    names += f" +{len(empty) - 4} more"
                notes.append(Notification(
                    title          = f"{len(empty)} material{'s' if len(empty) != 1 else ''} out of stock",
                    body           = names,
                    severity       = Severity.CRITICAL,
                    plugin_id      = "materials_tracker_v2",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "materials_tracker_v2", "preset": "empty"},
                    action_label   = "View",
                ))
            if low:
                names = ", ".join(m.name for m in low[:4])
                if len(low) > 4:
                    names += f" +{len(low) - 4} more"
                notes.append(Notification(
                    title          = f"{len(low)} material{'s' if len(low) != 1 else ''} running low",
                    body           = names,
                    severity       = Severity.WARNING,
                    plugin_id      = "materials_tracker_v2",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "materials_tracker_v2", "preset": "low"},
                    action_label   = "View",
                ))
        except Exception as e:
            print(f"[MATERIALS V2 PROVIDER] get_notifications: {e}")
        return notes

    # ── QuickActions ──────────────────────────────────────────────────────────

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction(
                "Add Material", "🌿",
                "dashboard_navigate",
                {"plugin_id": "materials_tracker_v2", "preset": "add"},
                "success",
            ),
            QuickAction(
                "View Low Stock", "⚠️",
                "dashboard_navigate",
                {"plugin_id": "materials_tracker_v2", "preset": "low"},
                "warning",
            ),
        ]

    # ── Recommendations ───────────────────────────────────────────────────────

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        try:
            materials = self._svc.get_all_materials()
            empty     = [m for m in materials if m.stock == "Empty"]
            low       = [m for m in materials if m.stock == "Low"]

            for m in empty[:2]:
                recs.append(Recommendation(
                    action         = "Restock",
                    target         = m.name,
                    context        = f"out of {m.material_type.lower()}",
                    priority       = 1,
                    plugin_id      = "materials_tracker_v2",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "materials_tracker_v2", "preset": "empty"},
                    action_label   = "View",
                    icon           = "🛒",
                ))
            for m in low[:2]:
                recs.append(Recommendation(
                    action         = "Running low",
                    target         = m.name,
                    context        = "stock is low",
                    priority       = 2,
                    plugin_id      = "materials_tracker_v2",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "materials_tracker_v2", "preset": "low"},
                    action_label   = "View",
                    icon           = "⚠️",
                ))
        except Exception as e:
            print(f"[MATERIALS V2 PROVIDER] get_recommendations: {e}")
        return recs

    # ── Stubs ─────────────────────────────────────────────────────────────────

    def get_project_cards(self) -> list[ProjectCard]:
        return []
