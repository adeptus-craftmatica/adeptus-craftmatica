"""Campaign Tracker v2 dashboard provider."""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.contracts.dashboard_dto import (
    CommandStat, ProjectCard, Notification, QuickAction,
    Severity, Recommendation,
)

_ACTIVE_STATUSES = {"active", "in progress", "ongoing", "running"}
_NAV = {"plugin_id": "campaign_tracker_v2"}


class CampaignDashboardProviderV2:
    def __init__(self, service):
        self._svc = service

    # ── Command stats ─────────────────────────────────────────────────────────

    def get_command_stats(self) -> list[CommandStat]:
        try:
            campaigns   = self._svc.get_all_campaigns()
            total       = len(campaigns)
            active_list = [c for c in campaigns
                           if (getattr(c, "status", "") or "").lower()
                           in _ACTIVE_STATUSES]
            active = len(active_list)

            session_counts = self._svc.count_sessions_by_campaign()
            char_counts    = self._svc.count_characters_by_campaign()
            total_sessions = sum(session_counts.values())
            total_chars    = sum(char_counts.values())

            cards = [
                CommandStat(
                    label    = "Campaigns",
                    value    = str(total),
                    subtitle = f"{active} active",
                    color    = "accent",
                    icon     = "🗺",
                ),
            ]
            if total_sessions:
                cards.append(CommandStat(
                    label    = "Sessions Logged",
                    value    = str(total_sessions),
                    subtitle = "across all campaigns",
                    color    = "accent",
                    icon     = "📅",
                ))
            if total_chars:
                cards.append(CommandStat(
                    label    = "Characters",
                    value    = str(total_chars),
                    subtitle = "across all campaigns",
                    color    = "accent",
                    icon     = "🧙",
                ))
            return cards
        except Exception as e:
            log.error(f"[CAMPAIGN V2 PROVIDER] get_command_stats: {e}")
            return []

    # ── Project cards ─────────────────────────────────────────────────────────

    def get_project_cards(self) -> list[ProjectCard]:
        """Return one ProjectCard per active campaign."""
        cards: list[ProjectCard] = []
        try:
            campaigns = self._svc.get_all_campaigns()
            active    = [c for c in campaigns
                         if (getattr(c, "status", "") or "").lower()
                         in _ACTIVE_STATUSES]

            session_counts = self._svc.count_sessions_by_campaign()
            for c in active[:6]:       # cap to 6 to avoid flooding the feed
                try:
                    n_sessions = session_counts.get(c.id, 0)
                    sessions   = self._svc.get_sessions(c.id)
                    characters = self._svc.get_characters(c.id)
                    n_chars    = len(characters)
                    n_pcs      = sum(
                        1 for ch in characters
                        if "player" in (getattr(ch, "character_role", "") or "").lower()
                    )

                    # Last session date
                    last_date = ""
                    if sessions:
                        last = sessions[-1]
                        dp   = getattr(last, "date_played", None)
                        last_date = str(dp)[:10] if dp else ""

                    detail_lines = []
                    if n_chars:
                        detail_lines.append(
                            f"🧙 {n_pcs} PC{'s' if n_pcs != 1 else ''}"
                            + (f"  +{n_chars - n_pcs} NPC" if n_chars > n_pcs else "")
                        )
                    if last_date:
                        detail_lines.append(f"📅 Last session: {last_date}")

                    system = getattr(c, "game_system", "") or ""

                    cards.append(ProjectCard(
                        id             = c.id,
                        plugin_id      = "campaign_tracker_v2",
                        plugin_label   = "Campaign Command",
                        title          = c.name,
                        subtitle       = system,
                        progress       = -1.0,          # campaigns have no fixed end
                        status         = f"{n_sessions} session{'s' if n_sessions != 1 else ''}",
                        status_color   = "accent",
                        last_active    = last_date,
                        action_label   = "Open",
                        action_event   = "dashboard_navigate",
                        action_payload = {"plugin_id": "campaign_tracker_v2", "project_id": c.id},
                        detail_lines   = detail_lines,
                    ))
                except Exception:
                    pass
        except Exception as e:
            log.error(f"[CAMPAIGN V2 PROVIDER] get_project_cards: {e}")
        return cards

    # ── Notifications ─────────────────────────────────────────────────────────

    def get_notifications(self) -> list[Notification]:
        return []

    # ── Recommendations ───────────────────────────────────────────────────────

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        try:
            campaigns = self._svc.get_all_campaigns()
            active    = [c for c in campaigns
                         if (getattr(c, "status", "") or "").lower()
                         in _ACTIVE_STATUSES]
            for c in active[:3]:
                try:
                    sessions = self._svc.get_sessions(c.id)
                    n        = len(sessions)
                    ctx      = (f"session {n + 1} prep due"
                                if n else "no sessions logged yet")
                except Exception:
                    ctx = "active campaign"

                recs.append(Recommendation(
                    action         = "Log next session",
                    target         = c.name,
                    context        = ctx,
                    priority       = 2,
                    plugin_id      = "campaign_tracker_v2",
                    icon           = "🗺",
                    action_event   = "dashboard_navigate",
                    action_payload = {
                        "plugin_id":  "campaign_tracker_v2",
                        "project_id": c.id,
                    },
                    action_label   = "Open",
                ))
        except Exception as e:
            log.error(f"[CAMPAIGN V2 PROVIDER] get_recommendations: {e}")
        return recs

    # ── Quick actions ─────────────────────────────────────────────────────────

    def get_quick_actions(self) -> list[QuickAction]:
        # Try to surface the single most recent active campaign directly.
        # Fall back to just opening the tracker if there are multiple or none.
        try:
            campaigns = self._svc.get_all_campaigns()
            active    = [c for c in campaigns
                         if (getattr(c, "status", "") or "").lower()
                         in _ACTIVE_STATUSES]
            if len(active) == 1:
                return [QuickAction(
                    label   = f"Open: {active[0].name}",
                    icon    = "🗺",
                    event   = "dashboard_navigate",
                    payload = {
                        "plugin_id":  "campaign_tracker_v2",
                        "project_id": active[0].id,
                    },
                    color   = "accent",
                )]
        except Exception:
            pass
        return [
            QuickAction(
                label   = "Open Campaign",
                icon    = "🗺",
                event   = "dashboard_navigate",
                payload = _NAV,
                color   = "accent",
            ),
        ]
