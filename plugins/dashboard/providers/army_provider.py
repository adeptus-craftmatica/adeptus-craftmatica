"""Army Builder dashboard provider."""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.contracts.dashboard_dto import (
    CommandStat, ProjectCard, Notification, QuickAction, Severity, Recommendation,
)


class ArmyDashboardProvider:
    def __init__(self, service):
        self._svc = service

    def get_command_stats(self) -> list[CommandStat]:
        try:
            armies    = self._svc.get_all_armies()
            total     = len(armies)
            over      = 0
            pct_vals  = []

            for army in armies:
                try:
                    used  = self._svc.get_points_total(army.id)
                    limit = getattr(army, "points_limit", 0) or 0
                    if limit > 0:
                        pct_vals.append(min(used / limit * 100, 100))
                        if used > limit:
                            over += 1
                except Exception:
                    pass

            avg_pct = int(sum(pct_vals) / len(pct_vals)) if pct_vals else -1

            cards = [
                CommandStat(
                    label    = "Armies",
                    value    = str(total),
                    subtitle = f"{total} list{'s' if total != 1 else ''} built",
                    color    = "accent",
                    icon     = "⚔",
                ),
            ]

            if avg_pct >= 0:
                cards.append(CommandStat(
                    label    = "Avg Completion",
                    value    = f"{avg_pct}%",
                    subtitle = "of points limits filled",
                    color    = "success" if avg_pct >= 90 else ("warning" if avg_pct < 50 else "accent"),
                    icon     = "📊",
                ))

            if over > 0:
                cards.append(CommandStat(
                    label    = "Over Limit",
                    value    = str(over),
                    subtitle = f"arm{'ies' if over != 1 else 'y'} exceeds points",
                    color    = "danger",
                    icon     = "⚠",
                ))

            return cards
        except Exception as e:
            log.error(f"[ARMY PROVIDER] get_command_stats: {e}")
            return []

    def get_project_cards(self) -> list[ProjectCard]:
        # Armies are not projects — surfacing them in the Active Projects strip
        # alongside project-tracker entries causes confusion ("Reckless Rodents"
        # appearing as a project).  Army stats are shown via command cards and
        # recommendations instead.
        return []

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            armies = self._svc.get_all_armies()
            for army in armies:
                pts_limit = getattr(army, "points_limit", 0) or 0
                if pts_limit <= 0:
                    continue
                try:
                    pts_used = self._svc.get_points_total(army.id)
                except Exception:
                    continue
                if pts_used > pts_limit:
                    over = pts_used - pts_limit
                    notes.append(Notification(
                        title          = f"{army.name} exceeds points limit",
                        body           = f"{pts_used:,} / {pts_limit:,} pts — {over:,} pts over.",
                        severity       = Severity.WARNING,
                        plugin_id      = "army_builder",
                        action_event   = "dashboard_navigate",
                        action_payload = {"plugin_id": "army_builder"},
                        action_label   = "Edit Army",
                    ))
        except Exception as e:
            log.error(f"[ARMY PROVIDER] get_notifications: {e}")
        return notes

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        nav = {"plugin_id": "army_builder"}
        try:
            armies = self._svc.get_all_armies()
            for army in armies:
                try:
                    used  = self._svc.get_points_total(army.id)
                    limit = getattr(army, "points_limit", 0) or 0
                except Exception:
                    continue

                if limit <= 0:
                    continue

                if used > limit:
                    over = used - limit
                    recs.append(Recommendation(
                        action="Fix list", target=army.name,
                        context=f"{over:,} pts over limit — trim some units",
                        priority=1, plugin_id="army_builder", icon="⚔",
                        action_event="dashboard_navigate", action_payload=nav,
                        action_label="Edit Army",
                    ))
                elif used / limit < 0.5:
                    remaining = limit - used
                    recs.append(Recommendation(
                        action="Build out", target=army.name,
                        context=f"{remaining:,} pts of room left — add units",
                        priority=3, plugin_id="army_builder", icon="⚔",
                        action_event="dashboard_navigate", action_payload=nav,
                        action_label="Open Army",
                    ))
                elif used / limit >= 0.85 and used < limit:
                    remaining = limit - used
                    recs.append(Recommendation(
                        action="Complete list", target=army.name,
                        context=f"{remaining:,} pts remaining to fill",
                        priority=2, plugin_id="army_builder", icon="⚔",
                        action_event="dashboard_navigate", action_payload=nav,
                        action_label="Open Army",
                    ))
        except Exception as e:
            log.error(f"[ARMY PROVIDER] get_recommendations: {e}")
        return recs

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction("Build Army", "⚔", "dashboard_navigate",
                        {"plugin_id": "army_builder"}, "accent"),
        ]
