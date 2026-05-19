"""Model Tracker dashboard provider."""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.contracts.dashboard_dto import (
    CommandStat, ProjectCard, Notification, QuickAction, Severity, Recommendation,
)

_COMPLETE  = {"complete", "painted", "fully painted", "finished", "display piece",
              "based"}
_BACKLOG   = {"unassembled", "assembled", "primed"}
_WIP       = {"wip"}


class ModelDashboardProvider:
    def __init__(self, service):
        self._svc = service

    def get_command_stats(self) -> list[CommandStat]:
        try:
            models   = self._svc.get_all_models()
            total    = len(models)
            complete = sum(1 for m in models if m.status.lower() in _COMPLETE)
            backlog  = sum(1 for m in models if m.status.lower() in _BACKLOG)
            wip      = sum(1 for m in models if m.status.lower() in _WIP)
            pct      = int(complete / total * 100) if total else 0

            cards = [
                # Hero: total collection + progress
                CommandStat(
                    label    = "Models",
                    value    = str(total),
                    subtitle = f"{pct}% painted  ·  {complete} complete",
                    color    = "success" if pct >= 80 else "accent",
                    icon     = "🗿",
                ),
            ]

            # Hero: ready to paint (actionable backlog)
            if backlog > 0:
                sub = f"{wip} in progress" if wip else "waiting for brush"
                cards.append(CommandStat(
                    label    = "Ready to Paint",
                    value    = str(backlog),
                    subtitle = sub,
                    color    = "warning" if backlog > 5 else "accent",
                    icon     = "🖌",
                ))

            return cards
        except Exception as e:
            log.error(f"[MODEL PROVIDER] get_command_stats: {e}")
            return []

    def get_project_cards(self) -> list[ProjectCard]:
        # Model tracker groups are not named projects — returning them here
        # pollutes the Active Projects strip with "None", "Uncategorised" etc.
        # Model progress is surfaced via command stats and recommendations instead.
        return []

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            models  = self._svc.get_all_models()
            backlog = [m for m in models if m.status.lower() in _BACKLOG]
            if len(backlog) > 15:
                notes.append(Notification(
                    title          = f"{len(backlog)} models waiting to be painted",
                    body           = "You have a significant unpainted backlog.",
                    severity       = Severity.INFO,
                    plugin_id      = "model_tracker",
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "model_tracker"},
                    action_label   = "View Models",
                ))
        except Exception as e:
            log.error(f"[MODEL PROVIDER] get_notifications: {e}")
        return notes

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        nav = {"plugin_id": "model_tracker"}
        try:
            models = self._svc.get_all_models()
            wip        = [m for m in models if m.status.lower() == "wip"]
            primed     = [m for m in models if m.status.lower() == "primed"]
            assembled  = [m for m in models if m.status.lower() == "assembled"]
            unassembled= [m for m in models if m.status.lower() == "unassembled"]

            for m in wip[:2]:
                recs.append(Recommendation(
                    action="Finish painting", target=m.name,
                    context="work in progress",
                    priority=2, plugin_id="model_tracker", icon="🖌",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Models",
                ))
            for m in primed[:2]:
                recs.append(Recommendation(
                    action="Start painting", target=m.name,
                    context="primed and ready for colour",
                    priority=3, plugin_id="model_tracker", icon="🖌",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Models",
                ))
            for m in assembled[:1]:
                recs.append(Recommendation(
                    action="Prime", target=m.name,
                    context="assembled, awaiting primer",
                    priority=3, plugin_id="model_tracker", icon="🗿",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Models",
                ))
            for m in unassembled[:1]:
                recs.append(Recommendation(
                    action="Assemble", target=m.name,
                    context="still on sprue",
                    priority=3, plugin_id="model_tracker", icon="🗿",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="View Models",
                ))
        except Exception as e:
            log.error(f"[MODEL PROVIDER] get_recommendations: {e}")
        return recs

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction("Add Model", "🗿", "dashboard_navigate",
                        {"plugin_id": "model_tracker"}, "accent"),
        ]
