"""Dashboard provider for Model Tracker 2.0."""
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

_STATUS_PROGRESS = {
    "Unassembled": 0,
    "Assembled":   15,
    "Primed":      30,
    "WIP":         50,
    "Painted":     70,
    "Based":       85,
    "Complete":    100,
}


class ModelTrackerDashboardProviderV2:
    def __init__(self, service) -> None:
        self._svc = service

    # ── CommandStats ──────────────────────────────────────────────────────────

    def get_command_stats(self) -> list[CommandStat]:
        try:
            stats = self._svc.get_statistics()

            total_entries     = stats.total_count
            total_minis       = stats.total_models
            unassembled_count = stats.status_distribution.get("Unassembled", 0)
            complete_count    = stats.status_distribution.get("Complete", 0)

            completion_pct = (
                round((complete_count / total_entries) * 100)
                if total_entries > 0 else 0
            )

            # Pile of shame = sum of quantities for Unassembled entries
            # get_statistics already counts entries, not quantities for status_distribution
            # so we recalculate quantity-based pile of shame separately
            pile_qty = self._get_pile_of_shame_qty()

            return [
                CommandStat(
                    label    = "Model Entries",
                    value    = str(total_entries),
                    subtitle = "unique model entries",
                    icon     = "🎮",
                    color    = "accent",
                    card_id  = "model_tracker.entries",
                ),
                CommandStat(
                    label    = "Miniatures",
                    value    = str(total_minis),
                    subtitle = "total miniature count",
                    icon     = "🧱",
                    color    = "accent",
                    card_id  = "model_tracker.miniatures",
                ),
                CommandStat(
                    label    = "Pile of Shame",
                    value    = str(pile_qty),
                    subtitle = "unassembled miniatures",
                    icon     = "📦",
                    color    = "warning" if pile_qty > 10 else "accent",
                    card_id  = "model_tracker.pile_of_shame",
                ),
                CommandStat(
                    label    = "Completion",
                    value    = f"{completion_pct}%",
                    subtitle = f"{complete_count} entries complete",
                    icon     = "✅",
                    color    = "success" if completion_pct >= 50 else "accent",
                    card_id  = "model_tracker.completion",
                ),
            ]
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 PROVIDER] get_command_stats: {e}")
            return []

    def _get_pile_of_shame_qty(self) -> int:
        try:
            models = self._svc.get_all_models()
            return sum(m.quantity for m in models if m.status == "Unassembled")
        except Exception:
            return 0

    # ── ProjectCards ─────────────────────────────────────────────────────────

    def get_project_cards(self) -> list[ProjectCard]:
        try:
            models = self._svc.get_all_models()
            # Sort by id descending (most recently added approximation)
            models_sorted = sorted(models, key=lambda m: m.id or 0, reverse=True)
            cards: list[ProjectCard] = []
            for m in models_sorted[:5]:
                progress = _STATUS_PROGRESS.get(m.status, 0) / 100.0
                cards.append(ProjectCard(
                    id            = m.id,
                    plugin_id     = "model_tracker_v2",
                    plugin_label  = "Model Command",
                    title         = m.name,
                    subtitle      = f"{m.faction} — {m.game_system}",
                    progress      = progress,
                    status        = m.status,
                    action_event  = "dashboard_navigate",
                    action_payload= {"plugin_id": "model_tracker_v2"},
                    action_label  = "Open",
                ))
            return cards
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 PROVIDER] get_project_cards: {e}")
            return []

    # ── Notifications ─────────────────────────────────────────────────────────

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            pile_qty = self._get_pile_of_shame_qty()
            if pile_qty > 20:
                notes.append(Notification(
                    title          = "Pile of Shame Warning",
                    body           = f"{pile_qty} unassembled miniatures — time to start assembling!",
                    severity       = Severity.WARNING,
                    plugin_id      = "model_tracker_v2",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "model_tracker_v2", "preset": "pile_of_shame"},
                    action_label   = "View",
                ))
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 PROVIDER] get_notifications: {e}")
        return notes

    # ── Recommendations ───────────────────────────────────────────────────────

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        try:
            stats      = self._svc.get_statistics()
            wip_count  = stats.status_distribution.get("WIP", 0)
            primed_cnt = stats.status_distribution.get("Primed", 0)

            if wip_count == 0 and primed_cnt > 0:
                recs.append(Recommendation(
                    action         = "Start painting!",
                    target         = f"{primed_cnt} primed models",
                    context        = "No models currently WIP — start painting now",
                    priority       = 2,
                    plugin_id      = "model_tracker_v2",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "model_tracker_v2"},
                    action_label   = "Open",
                    icon           = "🖌️",
                ))
        except Exception as e:
            log.error(f"[MODEL TRACKER V2 PROVIDER] get_recommendations: {e}")
        return recs

    # ── QuickActions ──────────────────────────────────────────────────────────

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction(
                "Open Collection", "🎮",
                "dashboard_navigate",
                {"plugin_id": "model_tracker_v2"},
                "accent",
            ),
        ]
