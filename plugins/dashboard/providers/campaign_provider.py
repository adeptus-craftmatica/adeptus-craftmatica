"""Campaign Tracker dashboard provider."""
from __future__ import annotations

from core.contracts.dashboard_dto import (
    CommandStat, ProjectCard, Notification, QuickAction, Severity, Recommendation,
)

_ACTIVE_STATUSES = {"active", "in progress", "ongoing", "running"}


class CampaignDashboardProvider:
    def __init__(self, service):
        self._svc = service

    def get_command_stats(self) -> list[CommandStat]:
        try:
            campaigns = self._svc.get_all_campaigns()
            active    = [c for c in campaigns if
                         getattr(c, "status", "").lower() in _ACTIVE_STATUSES]

            # Count total battles across all campaigns
            total_battles = 0
            for c in campaigns:
                try:
                    total_battles += len(self._svc.get_battles(c.id))
                except Exception:
                    pass

            cards = [
                CommandStat(
                    label    = "Active Campaigns",
                    value    = str(len(active)),
                    subtitle = (f"{len(campaigns)} total  ·  {total_battles} battle{'s' if total_battles != 1 else ''} logged"
                                if total_battles else f"{len(campaigns)} total"),
                    color    = "accent",
                    icon     = "🏕",
                ),
            ]

            return cards
        except Exception as e:
            print(f"[CAMPAIGN PROVIDER] get_command_stats: {e}")
            return []

    def get_project_cards(self) -> list[ProjectCard]:
        # Campaigns are not projects — the Active Projects strip is reserved for
        # project_tracker entries only.  Campaign stats surface via command cards
        # and recommendations instead.
        return []

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        nav = {"plugin_id": "campaign_tracker"}
        try:
            campaigns = self._svc.get_all_campaigns()
            active    = [c for c in campaigns
                         if getattr(c, "status", "").lower() in _ACTIVE_STATUSES]
            for c in active[:2]:
                try:
                    battles = self._svc.get_battles(c.id)
                    n = len(battles)
                    ctx = f"session {n + 1} prep due" if n else "no sessions logged yet"
                except Exception:
                    ctx = "active campaign"
                recs.append(Recommendation(
                    action="Log next session", target=c.name,
                    context=ctx,
                    priority=2, plugin_id="campaign_tracker", icon="🏕",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="Open Campaign",
                ))
        except Exception as e:
            print(f"[CAMPAIGN PROVIDER] get_recommendations: {e}")
        return recs

    def get_notifications(self) -> list[Notification]:
        return []

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction("New Campaign", "🏕", "dashboard_navigate",
                        {"plugin_id": "campaign_tracker"}, "accent"),
        ]
