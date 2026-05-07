"""Dashboard provider for Paint Tracker 2.0."""
from __future__ import annotations

from core.contracts.dashboard_dto import (
    CommandStat,
    Notification,
    QuickAction,
    Recommendation,
    Severity,
)


class PaintDashboardProvider:
    def __init__(self, service):
        self._svc = service

    # ── CommandStats ─────────────────────────────────────────────────────────

    def get_command_stats(self) -> list[CommandStat]:
        try:
            all_paints = self._svc.get_all_paints()
            total = len(all_paints)
            brands = len({p.brand for p in all_paints})
            low_stock = sum(1 for p in all_paints if p.quantity <= 1)
            out_of_stock = sum(1 for p in all_paints if p.quantity == 0)

            low_subtitle = (
                f"{out_of_stock} out of stock" if out_of_stock > 0
                else "need restocking" if low_stock > 0
                else "all stocked up"
            )

            return [
                CommandStat(
                    label="Total Paints",
                    value=str(total),
                    subtitle=f"{brands} brand{'s' if brands != 1 else ''}",
                    icon="🎨",
                    color="accent",
                ),
                CommandStat(
                    label="Low Stock",
                    value=str(low_stock),
                    subtitle=low_subtitle,
                    icon="⚠️",
                    color="danger" if out_of_stock > 0 else ("warning" if low_stock > 0 else "accent"),
                ),
            ]
        except Exception as e:
            print(f"[PAINT V2 PROVIDER] get_command_stats: {e}")
            return []

    # ── Notifications ─────────────────────────────────────────────────────────

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            low_stock_paints = self._svc.get_low_stock_notifiable()
            for p in low_stock_paints[:3]:
                notes.append(Notification(
                    title=f"Low stock: {p.brand} {p.name}",
                    body=f"Only {p.quantity} remaining",
                    severity=Severity.WARNING,
                    plugin_id="paint_tracker_v2",
                    action_event="dashboard_navigate",
                    action_payload={"plugin_id": "paint_tracker_v2"},
                    action_label="View",
                ))
        except Exception as e:
            print(f"[PAINT V2 PROVIDER] get_notifications: {e}")
        return notes

    # ── QuickActions ──────────────────────────────────────────────────────────

    def get_quick_actions(self) -> list[QuickAction]:
        return [
                QuickAction(
                    "Add Paint", "🎨",
                    "dashboard_navigate",
                    {"plugin_id": "paint_tracker_v2", "preset": "add"},
                    "accent",
                ),
                QuickAction(
                    "View Low Stock", "⚠️",
                    "dashboard_navigate",
                    {"plugin_id": "paint_tracker_v2", "preset": "low_stock"},
                    "warning",
                ),
        ]

    # ── Recommendations ───────────────────────────────────────────────────────

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        try:
            all_paints = self._svc.get_all_paints()

            # Out-of-stock (quantity == 0) — priority 1
            out_of_stock = [p for p in all_paints if p.quantity == 0]
            for p in out_of_stock[:3]:
                recs.append(Recommendation(
                    action="Restock",
                    target=f"{p.brand} {p.name}",
                    context="out of stock",
                    priority=1,
                    plugin_id="paint_tracker_v2",
                    action_event="dashboard_navigate",
                    action_payload={"plugin_id": "paint_tracker_v2", "preset": "out"},
                    action_label="View",
                    icon="🛒",
                ))

            # Low stock (quantity == 1) — priority 2
            low_stock = [p for p in all_paints if p.quantity == 1]
            for p in low_stock[:3]:
                recs.append(Recommendation(
                    action="Running low",
                    target=f"{p.brand} {p.name}",
                    context="only 1 remaining",
                    priority=2,
                    plugin_id="paint_tracker_v2",
                    action_event="dashboard_navigate",
                    action_payload={"plugin_id": "paint_tracker_v2", "preset": "low_stock"},
                    action_label="View",
                    icon="⚠️",
                ))
        except Exception as e:
            print(f"[PAINT V2 PROVIDER] get_recommendations: {e}")
        return recs

    # ── Paint Intel (called directly by dashboard paint intel section) ────────

    def get_low_stock_paints(self, limit: int = 8) -> list:
        try:
            paints = self._svc.get_all_paints()
            low = [p for p in paints if p.quantity <= 1 and p.notify_low_stock]
            low.sort(key=lambda p: p.quantity)
            return low[:limit]
        except Exception:
            return []

    def get_recent_paints(self, limit: int = 5) -> list:
        try:
            paints = self._svc.get_all_paints()
            return sorted(paints, key=lambda p: p.id or 0, reverse=True)[:limit]
        except Exception:
            return []

    def get_brand_breakdown(self) -> dict[str, int]:
        try:
            breakdown: dict[str, int] = {}
            for p in self._svc.get_all_paints():
                breakdown[p.brand] = breakdown.get(p.brand, 0) + 1
            return breakdown
        except Exception:
            return {}

    # ── Stub for providers that don't have project cards ─────────────────────

    def get_project_cards(self) -> list:
        return []
