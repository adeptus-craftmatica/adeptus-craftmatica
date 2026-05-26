"""
Dashboard 2.0 — Plugin entry point.

Reuses the existing DashboardRegistry service and all provider classes.
Provides a more polished, adaptive, customisable UI than the v1 dashboard.
"""
from __future__ import annotations

import json
import logging
log = logging.getLogger(__name__)

from datetime import date, timedelta

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from core.plugin_base import PluginBase


# ── Events that trigger a refresh ─────────────────────────────────────────────

_REFRESH_EVENTS = [
    "paint_added", "paint_removed", "paint_updated",
    "model_added", "model_removed", "model_updated",
    "army_created", "army_deleted", "army_updated",
    "unit_added", "unit_removed", "unit_updated",
    "campaign_created", "campaign_deleted", "campaign_updated",
    "battle_logged",
    "tool_added", "tool_removed", "tool_updated",
    "material_added", "material_removed", "material_updated",
    "calendar_event_added", "calendar_event_updated", "calendar_event_deleted",
    "calendar_settings_changed",
    "dashboard_provider_updated",
    "project_create", "project_updated", "project_delete",
    "project_milestone_add", "project_milestone_toggle",
    "project_milestone_quantity_step", "project_milestone_uncompleted",
    "project_session_log", "project_session_end",
    "project_milestone_completed", "project_gallery_add",
]

# Events that also write an activity log entry
_ACTIVITY_EVENTS: dict[str, tuple[str, str]] = {
    "paint_added":                  ("🎨", "Added paint"),
    "paint_removed":                ("🗑", "Removed paint"),
    "paint_updated":                ("✏️", "Updated paint"),
    "model_added":                  ("🗿", "Added model"),
    "model_removed":                ("🗑", "Removed model"),
    "model_updated":                ("✏️", "Updated model"),
    "army_created":                 ("⚔️", "Created army"),
    "army_deleted":                 ("🗑", "Deleted army"),
    "army_updated":                 ("✏️", "Updated army"),
    "campaign_created":             ("🏕", "Started campaign"),
    "campaign_deleted":             ("🗑", "Deleted campaign"),
    "battle_logged":                ("🎲", "Logged battle"),
    "tool_added":                   ("🔧", "Added tool"),
    "tool_removed":                 ("🗑", "Removed tool"),
    "tool_updated":                 ("✏️", "Updated tool"),
    "material_added":               ("🌿", "Added material"),
    "material_removed":             ("🗑", "Removed material"),
    "material_updated":             ("✏️", "Updated material"),
    "project_create":               ("📁", "Started project"),
    "project_session_log":          ("⏱", "Logged hobby session"),
    "project_milestone_completed":  ("✅", "Completed milestone"),
    "project_gallery_add":          ("📸", "Added progress photo"),
}

_MAX_ACTIVITY = 30


class Plugin(PluginBase):
    display_name = "Dashboard 2.0"
    plugin_id    = "dashboard_v2"
    name         = "Dashboard 2.0"
    version      = "2.0.0"
    description  = (
        "Professional adaptive dashboard — beautiful, feature-rich, and "
        "customisable. Powered by your installed plugins."
    )

    def __init__(self, context):
        super().__init__(context)
        self._ui = None
        self._refresh_timer: QTimer | None = None
        self._streak = 0
        self._last_stats: list = []
        self._registered_provider_ids: list[str] = []

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def activate(self):
        from .ui import DashboardV2UI

        self._streak = self._update_hobby_streak()
        self._log_session_today()

        self._ui = DashboardV2UI(self.context)
        self._ui.setProperty("plugin_id", "dashboard_v2")
        self._ui.action_requested.connect(self._on_action)
        self._ui.customize_clicked.connect(self._open_customize)
        self._ui.refresh_clicked.connect(self._do_refresh)

        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)

        self._register_events()

        # Defer until all other plugins have registered their services
        QTimer.singleShot(200, self._deferred_setup)

        log.info("[DASHBOARD V2] Activated")

    def deactivate(self):
        if self._refresh_timer:
            self._refresh_timer.stop()
        registry = self.context.services.try_get("dashboard_registry")
        if registry:
            for pid in self._registered_provider_ids:
                try:
                    registry.unregister_provider(pid)
                except Exception:
                    pass
        self._registered_provider_ids = []
        log.info("[DASHBOARD V2] Deactivated")

    def get_ui(self) -> QWidget | None:
        return self._ui

    # ── Deferred setup ─────────────────────────────────────────────────────────

    def _deferred_setup(self):
        self._setup_providers()
        self._update_greeting()
        self._do_refresh()

    def _update_greeting(self):
        if not self._ui:
            return
        from datetime import datetime
        hour = datetime.now().hour
        if hour < 12:
            prefix = "Good morning"
        elif hour < 18:
            prefix = "Good afternoon"
        else:
            prefix = "Good evening"
        self._ui.set_greeting(f"{prefix}, {self._get_display_name()}!")
        self._ui.set_streak(self._streak)

    def _setup_providers(self):
        registry = self.context.services.try_get("dashboard_registry")
        if not registry:
            log.debug("[DASHBOARD V2] dashboard_registry not available yet — providers skipped")
            return

        _PROVIDER_MAP = [
            ("project_tracker",   "plugins.project_tracker.providers.dashboard_provider",
             "ProjectDashboardProvider",  "project_service"),
            ("paint_tracker",     "plugins.dashboard.providers.paint_provider",
             "PaintDashboardProvider",    "paint_service"),
            ("model_tracker",     "plugins.dashboard.providers.model_provider",
             "ModelDashboardProvider",    "model_service"),
            ("army_builder",      "plugins.dashboard.providers.army_provider",
             "ArmyDashboardProvider",     "army_service"),
            ("campaign_tracker",  "plugins.dashboard.providers.campaign_provider",
             "CampaignDashboardProvider", "campaign_service"),
            ("tool_tracker",      "plugins.dashboard.providers.tool_provider",
             "ToolDashboardProvider",     "tool_service"),
            ("materials_tracker", "plugins.dashboard.providers.materials_provider",
             "MaterialsDashboardProvider","material_service"),
        ]

        import importlib
        self._registered_provider_ids = []
        for plugin_id, module_path, class_name, service_name in _PROVIDER_MAP:
            svc = self.context.services.try_get(service_name)
            if not svc:
                continue
            try:
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                provider = cls(svc)
                registry.register_provider(plugin_id, provider)
                self._registered_provider_ids.append(plugin_id)
                log.debug(f"[DASHBOARD V2] Registered provider: {plugin_id}")
            except Exception as e:
                log.error(f"[DASHBOARD V2] Failed to register provider {plugin_id}: {e}")

    # ── Events ─────────────────────────────────────────────────────────────────

    def _register_events(self):
        bus = self.context.event_bus

        for event in _REFRESH_EVENTS:
            if event in _ACTIVITY_EVENTS:
                icon, desc = _ACTIVITY_EVENTS[event]

                def _make_handler(ev_icon: str, ev_desc: str):
                    def _handler(payload=None, _i=ev_icon, _d=ev_desc):
                        description = _d
                        if payload and isinstance(payload, dict):
                            for key in ("name", "title", "paint_name", "model_name",
                                        "army_name", "campaign_name", "tool_name",
                                        "material_name"):
                                val = payload.get(key, "")
                                if val:
                                    description = f"{_d}: {val}"
                                    break
                        self._log_activity(_i, description)
                        self._schedule_refresh(300)
                    return _handler

                try:
                    bus.subscribe(event, _make_handler(icon, desc))
                except Exception:
                    pass
            else:
                try:
                    bus.subscribe(event, lambda p=None: self._schedule_refresh(300))
                except Exception:
                    pass

        try:
            bus.subscribe("user_profile_updated",
                          lambda p=None: self._update_greeting())
        except Exception:
            pass

    def _on_action(self, event: str, payload: dict):
        try:
            self.context.event_bus.emit(event, payload)
        except Exception as e:
            log.error(f"[DASHBOARD V2] Action error: {e}")

    # ── Refresh ─────────────────────────────────────────────────────────────────

    def _schedule_refresh(self, delay_ms: int = 300):
        if self._refresh_timer:
            if self._refresh_timer.isActive():
                self._refresh_timer.stop()
            self._refresh_timer.start(delay_ms)

    def _do_refresh(self):
        if not self._ui:
            return
        registry = self.context.services.try_get("dashboard_registry")
        if not registry:
            return

        # Stats
        try:
            all_stats = self._get_self_stats() + registry.get_all_command_stats()
            self._last_stats = all_stats
            self._ui.refresh_stats(all_stats)
        except Exception as e:
            log.error(f"[DASHBOARD V2] stats: {e}")

        # Projects
        project_cards = []
        try:
            project_cards = registry.get_all_projects()
            self._ui.refresh_projects(project_cards)
        except Exception as e:
            log.error(f"[DASHBOARD V2] projects: {e}")

        # Quick actions
        try:
            self._ui.refresh_quick_actions(registry.get_all_quick_actions())
        except Exception as e:
            log.error(f"[DASHBOARD V2] quick_actions: {e}")

        # Notifications
        notifications = []
        try:
            notifications = registry.get_all_notifications()
            self._ui.refresh_notifications(notifications)
        except Exception as e:
            log.error(f"[DASHBOARD V2] notifications: {e}")

        # Recommendations
        try:
            self._ui.refresh_recommendations(registry.get_all_recommendations())
        except Exception as e:
            log.error(f"[DASHBOARD V2] recommendations: {e}")

        # Paint intel
        try:
            self._refresh_paint_intel(registry)
        except Exception as e:
            log.error(f"[DASHBOARD V2] paint_intel: {e}")

        # Activity feed
        try:
            activities = self._load_json_list("dashboard.recent_activity")
            self._ui.refresh_activity(activities)
        except Exception as e:
            log.error(f"[DASHBOARD V2] activity: {e}")

        # Calendar intelligence
        try:
            self._refresh_calendar()
        except Exception as e:
            log.error(f"[DASHBOARD V2] calendar: {e}")

    def _refresh_paint_intel(self, registry):
        provider = registry.get_provider("paint_tracker")
        if provider:
            low    = provider.get_low_stock_paints(limit=8)
            recent = provider.get_recent_paints(limit=6)
            brands = provider.get_brand_breakdown()
        else:
            low, recent, brands = [], [], {}
        self._ui.refresh_paint_intel(low, recent, brands)

    def _refresh_calendar(self):
        cal_svc = self.context.services.try_get("calendar_service")
        if not cal_svc:
            return
        today_events = cal_svc.get_today()
        week_events  = cal_svc.get_upcoming_week()
        milestones   = cal_svc.get_milestones()
        overdue: list = []
        try:
            overdue = cal_svc.get_overdue() or []
        except Exception:
            pass
        self._ui.refresh_calendar(today_events, week_events, milestones, overdue)

    # ── Customize ──────────────────────────────────────────────────────────────

    def _open_customize(self):
        if self._ui:
            self._ui.open_customize_dialog()

    # ── Self stats (hobby engagement) ─────────────────────────────────────────

    def _get_self_stats(self) -> list:
        from core.contracts.dashboard_dto import CommandStat
        stats = []

        if self._streak > 0:
            if self._streak == 1:
                sub = "day in a row — keep it up!"
            elif self._streak < 7:
                sub = "days in a row 🔥"
            else:
                sub = "days — legendary streak! 🔥"
            stats.append(CommandStat(
                label="Hobby Streak", value=str(self._streak), subtitle=sub,
                color="success" if self._streak >= 3 else "accent",
                icon="🔥", card_id="dashboard.hobby_streak",
            ))

        sessions = self._count_sessions_this_week()
        stats.append(CommandStat(
            label="This Week", value=str(sessions),
            subtitle=f"session{'s' if sessions != 1 else ''} so far",
            color=("success" if sessions >= 4 else
                   "warning" if sessions == 0 else "accent"),
            icon="📅", card_id="dashboard.this_week",
        ))

        hours = self._get_monthly_hours()
        if hours > 0:
            stats.append(CommandStat(
                label="This Month", value=f"{hours}h",
                subtitle="hobby time logged",
                color="success" if hours >= 10 else "accent",
                icon="⏱", card_id="dashboard.this_month",
            ))

        return stats

    def _get_monthly_hours(self) -> float:
        proj_svc = self.context.services.try_get("project_service")
        if not proj_svc:
            return 0.0
        try:
            today = date.today()
            sessions = proj_svc.get_sessions()
            total = 0.0
            for s in sessions:
                s_date = (getattr(s, "date", None) or
                          getattr(s, "logged_at", None) or
                          getattr(s, "session_date", None))
                if s_date:
                    try:
                        d = date.fromisoformat(str(s_date)[:10])
                        if d.year == today.year and d.month == today.month:
                            duration = (getattr(s, "duration_hours", None) or
                                        getattr(s, "hours", None) or
                                        getattr(s, "duration", None) or 0)
                            total += float(duration)
                    except Exception:
                        pass
            return round(total, 1)
        except Exception:
            return 0.0

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_json_list(self, key: str, default: str = "[]") -> list:
        settings = self.context.services.get("settings")
        if not settings:
            return []
        raw = settings.get(key, default)
        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def _log_session_today(self):
        settings = self.context.services.get("settings")
        if not settings:
            return
        today = date.today().isoformat()
        dates = self._load_json_list("dashboard.session_dates")
        if today not in dates:
            dates.append(today)
            dates = dates[-90:]
            settings.set("dashboard.session_dates", json.dumps(dates))

    def _count_sessions_this_week(self) -> int:
        dates  = self._load_json_list("dashboard.session_dates")
        today  = date.today()
        monday = today - timedelta(days=today.weekday())
        week   = {(monday + timedelta(days=i)).isoformat() for i in range(7)}
        return sum(1 for d in dates if d in week)

    def _log_activity(self, icon: str, description: str, plugin_id: str = "") -> None:
        settings = self.context.services.get("settings")
        if not settings:
            return
        from datetime import datetime
        timestamp = datetime.now().isoformat(timespec="seconds")
        entry = {"icon": icon, "description": description,
                 "timestamp": timestamp, "plugin_id": plugin_id}
        items = self._load_json_list("dashboard.recent_activity")
        items.insert(0, entry)
        items = items[:_MAX_ACTIVITY]
        settings.set("dashboard.recent_activity", json.dumps(items))

    def _update_hobby_streak(self) -> int:
        settings = self.context.services.get("settings")
        if not settings:
            return 0
        today_str  = date.today().isoformat()
        last_str   = settings.get("dashboard.last_session_date", "")
        streak     = int(settings.get("dashboard.hobby_streak", 0) or 0)
        if last_str == today_str:
            return streak
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if last_str == yesterday:
            streak += 1
        else:
            streak = 1
        settings.set("dashboard.last_session_date", today_str)
        settings.set("dashboard.hobby_streak", str(streak))
        return streak

    def _get_display_name(self) -> str:
        settings = self.context.services.get("settings")
        if settings:
            name = settings.get("user.display_name", "").strip()
            if name:
                return name
        return "Hobbyist"
