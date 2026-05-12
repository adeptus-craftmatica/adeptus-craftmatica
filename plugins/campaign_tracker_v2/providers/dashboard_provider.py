"""Campaign Tracker v2 dashboard provider."""
from __future__ import annotations

from core.contracts.dashboard_dto import (
    CommandStat, ProjectCard, Notification, QuickAction, Severity, Recommendation,
)


class CampaignDashboardProviderV2:
    def __init__(self, service):
        self._svc = service

    def get_command_stats(self) -> list[CommandStat]:
        try:
            campaigns = self._svc.get_all_campaigns()
            total     = len(campaigns)
            active    = sum(1 for c in campaigns
                            if (getattr(c, "status", "") or "").lower() == "active")
            cards = [
                CommandStat(
                    label="Campaigns", value=str(total),
                    subtitle=f"{active} active",
                    color="accent", icon="🗺",
                ),
            ]

            # Count total characters across all campaigns
            total_chars = 0
            for c in campaigns:
                try:
                    total_chars += len(self._svc.get_characters(c.id))
                except Exception:
                    pass
            if total_chars:
                cards.append(CommandStat(
                    label="Characters", value=str(total_chars),
                    subtitle="across all campaigns",
                    color="accent", icon="🧙",
                ))

            # Total sessions
            total_sessions = 0
            for c in campaigns:
                try:
                    total_sessions += len(self._svc.get_sessions(c.id))
                except Exception:
                    pass
            if total_sessions:
                cards.append(CommandStat(
                    label="Sessions", value=str(total_sessions),
                    subtitle="logged",
                    color="accent", icon="📅",
                ))
            return cards
        except Exception as e:
            print(f"[CAMPAIGN V2 PROVIDER] get_command_stats: {e}")
            return []

    def get_project_cards(self) -> list[ProjectCard]:
        return []

    def get_notifications(self) -> list[Notification]:
        return []

    def get_recommendations(self) -> list[Recommendation]:
        recs = []
        nav  = {"plugin_id": "campaign_tracker_v2"}
        try:
            campaigns = self._svc.get_all_campaigns()
            active = [c for c in campaigns
                      if (getattr(c, "status", "") or "").lower() == "active"]
            for c in active[:3]:
                recs.append(Recommendation(
                    action="Log session", target=c.name,
                    context="Active campaign — record your latest session",
                    priority=2, plugin_id="campaign_tracker_v2", icon="🗺",
                    action_event="dashboard_navigate", action_payload=nav,
                    action_label="Open Campaign",
                ))
        except Exception:
            pass
        return recs

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction("Open Campaign", "🗺", "dashboard_navigate",
                        {"plugin_id": "campaign_tracker_v2"}, "accent"),
        ]
