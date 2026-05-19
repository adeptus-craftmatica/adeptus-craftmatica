# plugins/project_tracker/providers/dashboard_provider.py
"""Dashboard provider — surfaces active project info on the overview page."""

from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.contracts.dashboard_dto import (
    CommandStat, ProjectCard as DashProjectCard, Notification,
    QuickAction, Severity, Recommendation, NavigationTarget,
)
from plugins.project_tracker.models import ProjectStatus


class ProjectDashboardProvider:
    def __init__(self, service):
        self._svc = service

    # ── CommandStat ───────────────────────────────────────────────────────────

    def get_command_stats(self) -> list[CommandStat]:
        try:
            all_projects = self._svc.get_all_projects()
            active = [p for p in all_projects
                      if p.status == ProjectStatus.ACTIVE]
            done   = [p for p in all_projects
                      if p.status == ProjectStatus.COMPLETED]

            # Aggregate recent-session momentum across all active projects
            week_sessions = 0
            week_hours    = 0.0
            has_live      = False
            for p in active:
                try:
                    stats = self._svc.get_stats(p.id)
                    week_sessions += stats.recent_session_count or 0
                    if stats.recent_session_count:
                        week_hours += round(
                            (stats.avg_session_duration or 0)
                            * stats.recent_session_count / 60, 1
                        )
                    if stats.has_active_session:
                        has_live = True
                except Exception:
                    pass

            cards = [
                CommandStat(
                    label    = "Active Projects",
                    value    = str(len(active)),
                    subtitle = f"{len(done)} completed",
                    color    = "accent",
                    icon     = "📁",
                ),
                CommandStat(
                    label    = "This Week",
                    value    = str(week_sessions),
                    subtitle = (
                        f"🔴 live session running" if has_live
                        else (f"{round(week_hours, 1)}h logged" if week_hours else "no sessions yet")
                    ),
                    color    = "danger" if has_live else ("success" if week_sessions else "accent"),
                    icon     = "🔴" if has_live else "⏱",
                ),
            ]
            return cards
        except Exception as e:
            log.error(f"[PROJECT PROVIDER] get_command_stats: {e}")
            return []

    # ── ProjectCard (recent active projects) ──────────────────────────────────

    # Map project status → dashboard severity colour key
    _STATUS_COLOR = {
        ProjectStatus.ACTIVE:    "success",
        ProjectStatus.ON_HOLD:   "warning",
        ProjectStatus.COMPLETED: "accent",
        ProjectStatus.ARCHIVED:  "danger",
    }

    def get_project_cards(self) -> list[DashProjectCard]:
        cards = []
        try:
            active = self._svc.get_active_projects()[:3]
            for p in active:
                stats = self._svc.get_stats(p.id)

                # ── Progress ──────────────────────────────────────────────────
                # Only show bar when milestones actually exist; 0/0 → no bar
                if stats.milestones_total > 0:
                    progress = stats.milestone_progress   # 0.0–1.0
                else:
                    progress = -1.0   # hides the bar

                # ── Subtitle ──────────────────────────────────────────────────
                # Prefer game_system; fall back to category label or "Project"
                from plugins.project_tracker.models import ProjectCategory
                subtitle = (
                    p.game_system
                    or ProjectCategory.LABELS.get(p.category, "")
                    or "Project"
                )

                # ── Detail lines ──────────────────────────────────────────────
                detail = []

                # Milestones: "3/7 milestones · 4 remaining"
                if stats.milestones_total > 0:
                    remaining = stats.milestones_total - stats.milestones_done
                    ms_str = f"{stats.milestones_done}/{stats.milestones_total} milestones"
                    if remaining > 0:
                        ms_str += f"  ({remaining} left)"
                    detail.append(ms_str)

                # Models: prefer miniature count; show types in parens when they differ
                if stats.total_models:
                    mc = stats.total_model_count or stats.total_models
                    mt = stats.total_models
                    if mc != mt:
                        detail.append(
                            f"{mc} miniature{'s' if mc != 1 else ''}  ({mt} type{'s' if mt != 1 else ''})"
                        )
                    else:
                        detail.append(f"{mc} model{'s' if mc != 1 else ''}")

                # Time: hours with session count, or just sessions
                if stats.total_hours:
                    hrs = round(stats.total_hours, 1)
                    s_suffix = f"  ·  {stats.total_sessions} session{'s' if stats.total_sessions != 1 else ''}" \
                               if stats.total_sessions else ""
                    detail.append(f"{hrs}h logged{s_suffix}")
                elif stats.total_sessions:
                    detail.append(
                        f"{stats.total_sessions} session{'s' if stats.total_sessions != 1 else ''} logged"
                    )

                if not detail:
                    detail.append("No activity logged yet")

                cards.append(DashProjectCard(
                    id           = p.id,
                    plugin_id    = "project_tracker",
                    plugin_label = "Projects",
                    title        = f"{p.icon}  {p.name}",
                    subtitle     = subtitle,
                    status       = ProjectStatus.LABELS.get(p.status, p.status),
                    status_color = self._STATUS_COLOR.get(p.status, "accent"),
                    progress     = progress,
                    detail_lines = detail,
                    action_event   = "dashboard_navigate",
                    action_payload = {"plugin_id": "project_tracker", "project_id": p.id},
                    action_label   = "Open Project",
                ))
        except Exception as e:
            log.error(f"[PROJECT PROVIDER] get_project_cards: {e}")
        return cards

    # ── Notifications ─────────────────────────────────────────────────────────

    def get_notifications(self) -> list[Notification]:
        notes: list[Notification] = []
        try:
            active = self._svc.get_active_projects()
            for p in active:
                milestones = self._svc.get_milestones(p.id)
                overdue = [m for m in milestones if m.is_overdue]
                for m in overdue[:2]:
                    notes.append(Notification(
                        title          = f"Overdue milestone: {m.title}",
                        body           = f"Project: {p.name}  ·  Due: {m.due_date}",
                        severity       = Severity.WARNING,
                        plugin_id      = "project_tracker",
                        action_event   = "dashboard_navigate",
                        action_payload = {"plugin_id": "project_tracker"},
                        action_label   = "View Projects",
                    ))
        except Exception as e:
            log.error(f"[PROJECT PROVIDER] get_notifications: {e}")
        return notes

    # ── QuickActions ──────────────────────────────────────────────────────────

    def get_quick_actions(self) -> list[QuickAction]:
        return [
            QuickAction("New Project", "📁", "dashboard_navigate",
                        {"plugin_id": "project_tracker"}, "accent"),
        ]

    # ── Recommendations ───────────────────────────────────────────────────────

    def get_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        try:
            active = self._svc.get_active_projects()
            for p in active:
                stats = self._svc.get_stats(p.id)

                def _nav(tab=None, item_id=None) -> dict:
                    """Build a NavigationTarget payload for this project."""
                    return NavigationTarget(
                        plugin_id  = "project_tracker",
                        project_id = p.id,
                        tab        = tab,
                        item_id    = item_id,
                    ).to_dict()

                # ── Priority 0: active live session ───────────────────────────
                if stats.has_active_session:
                    recs.append(Recommendation(
                        action="Active session",
                        target=p.name,
                        context="hobby session currently running",
                        priority=0, plugin_id="project_tracker", icon="🔴",
                        action_event="dashboard_navigate",
                        action_payload=_nav("overview"),
                        action_label="Open",
                    ))
                    continue   # no other recs while a session is live

                # ── Priority 1: focus milestone exists ────────────────────────
                focus = None
                try:
                    focus = self._svc.get_focus_milestone(p.id)
                except Exception:
                    pass

                if focus and not focus.is_complete:
                    qty_ctx = ""
                    if focus.has_quantity:
                        qty_ctx = f"{focus.quantity_done}/{focus.quantity_total} done"
                    recs.append(Recommendation(
                        action="Continue",
                        target=f"{p.name} — {focus.title}",
                        context=qty_ctx or "current focus milestone",
                        priority=1, plugin_id="project_tracker", icon="🎯",
                        action_event="dashboard_navigate",
                        action_payload=_nav("milestones", focus.id),
                        action_label="Open",
                    ))
                    # Suggest starting a session to work on that focus
                    recs.append(Recommendation(
                        action="Start session",
                        target=p.name,
                        context=f"continue: {focus.title}",
                        priority=1, plugin_id="project_tracker", icon="▶",
                        action_event="dashboard_navigate",
                        action_payload=_nav("sessions"),
                        action_label="Open Sessions",
                    ))

                # ── Priority 2: overdue + nearly-complete milestones ──────────
                milestones = self._svc.get_milestones(p.id)

                overdue = [m for m in milestones if m.is_overdue]
                if overdue:
                    m = overdue[0]
                    recs.append(Recommendation(
                        action="Review milestone",
                        target=f"{p.name} — {m.title}",
                        context=f"overdue since {m.due_date}",
                        priority=2, plugin_id="project_tracker", icon="⚠️",
                        action_event="dashboard_navigate",
                        action_payload=_nav("milestones", m.id),
                        action_label="Open",
                    ))

                # Nearly-complete quantity milestones (≥ 80 % done, not yet complete)
                nearly_done = [
                    m for m in milestones
                    if not m.is_complete and m.has_quantity
                    and m.quantity_progress >= 0.8
                ]
                if nearly_done:
                    m = nearly_done[0]
                    recs.append(Recommendation(
                        action="Finish milestone",
                        target=f"{p.name} — {m.title}",
                        context=f"{int(m.quantity_progress * 100)}% complete",
                        priority=2, plugin_id="project_tracker", icon="🏁",
                        action_event="dashboard_navigate",
                        action_payload=_nav("milestones", m.id),
                        action_label="Open",
                    ))

                # ── Priority 3: no sessions yet ───────────────────────────────
                if stats.total_sessions == 0:
                    recs.append(Recommendation(
                        action="Start tracking",
                        target=p.name,
                        context="no hobby sessions logged yet",
                        priority=3, plugin_id="project_tracker", icon="📁",
                        action_event="dashboard_navigate",
                        action_payload=_nav("sessions"),
                        action_label="Open Sessions",
                    ))
        except Exception as e:
            log.error(f"[PROJECT PROVIDER] get_recommendations: {e}")
        return recs
