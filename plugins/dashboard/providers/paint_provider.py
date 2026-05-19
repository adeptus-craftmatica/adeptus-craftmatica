"""Paint Tracker dashboard provider."""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.contracts.dashboard_dto import (
    CommandStat, ProjectCard, Notification, QuickAction, Severity, Recommendation,
)


class PaintDashboardProvider:
    def __init__(self, service):
        self._svc = service

    # ── CommandStat ───────────────────────────────────────────────────────────

    def get_command_stats(self) -> list[CommandStat]:
        try:
            paints = self._svc.get_all_paints()
            total  = len(paints)
            # Only count paints where the user wants low-stock alerts
            alerted = [p for p in paints if p.notify_low_stock]
            empty  = sum(1 for p in alerted if p.quantity == 0)
            low    = sum(1 for p in alerted if p.quantity == 1)
            low_total = empty + low

            stats = self._svc.get_statistics()
            brands = stats.unique_brands

            # Hero card 1 — total collection
            cards = [
                CommandStat(
                    label    = "Paint Collection",
                    value    = str(total),
                    subtitle = f"{brands} brand{'s' if brands != 1 else ''}",
                    color    = "accent",
                    icon     = "🎨",
                ),
            ]

            # Hero card 2 — low stock (only show when relevant)
            if low_total > 0:
                cards.append(CommandStat(
                    label    = "Paints Low",
                    value    = str(low_total),
                    subtitle = f"{empty} empty · {low} running low" if empty else f"{low} running low",
                    color    = "danger" if empty > 0 else "warning",
                    icon     = "⚠",
                ))

            return cards
        except Exception as e:
            log.error(f"[PAINT PROVIDER] get_command_stats: {e}")
            return []

    # ── ProjectCard ───────────────────────────────────────────────────────────

    def get_project_cards(self) -> list[ProjectCard]:
        return []

    # ── Notification ──────────────────────────────────────────────────────────

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            paints = self._svc.get_all_paints()
            empty  = [p for p in paints if p.quantity == 0 and p.notify_low_stock]
            low    = [p for p in paints if p.quantity == 1 and p.notify_low_stock]

            for p in empty[:5]:
                notes.append(Notification(
                    title          = f"Out of stock: {p.brand} {p.name}",
                    body           = "Quantity is 0 — consider restocking.",
                    severity       = Severity.CRITICAL,
                    plugin_id      = "paint_tracker",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "paint_tracker"},
                    action_label   = "View Paints",
                ))
            for p in low[:3]:
                notes.append(Notification(
                    title          = f"Running low: {p.brand} {p.name}",
                    body           = "Only 1 pot remaining.",
                    severity       = Severity.WARNING,
                    plugin_id      = "paint_tracker",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "paint_tracker"},
                    action_label   = "View Paints",
                ))
        except Exception as e:
            log.error(f"[PAINT PROVIDER] get_notifications: {e}")
        return notes

    # ── QuickAction ───────────────────────────────────────────────────────────

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction("Add Paint", "🎨", "dashboard_navigate",
                        {"plugin_id": "paint_tracker"}, "accent"),
        ]

    # ── Paint Intelligence (called directly by dashboard) ─────────────────────

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

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        nav = {"plugin_id": "paint_tracker"}
        try:
            paints = self._svc.get_all_paints()
            empty  = [p for p in paints if p.quantity == 0 and p.notify_low_stock]
            low    = [p for p in paints if p.quantity == 1 and p.notify_low_stock]
            for p in empty[:3]:
                recs.append(Recommendation(
                    action="Restock", target=f"{p.brand} {p.name}",
                    context="completely out of stock",
                    priority=1, plugin_id="paint_tracker", icon="🎨",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Paints",
                ))
            for p in low[:2]:
                recs.append(Recommendation(
                    action="Restock", target=f"{p.brand} {p.name}",
                    context="only 1 pot remaining",
                    priority=2, plugin_id="paint_tracker", icon="🎨",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Paints",
                ))
        except Exception as e:
            log.error(f"[PAINT PROVIDER] get_recommendations: {e}")
        return recs

    def get_brand_breakdown(self) -> dict[str, int]:
        try:
            return self._svc.get_statistics().brands_distribution
        except Exception:
            return {}
