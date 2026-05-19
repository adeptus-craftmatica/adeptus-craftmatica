"""Dashboard plugin — aggregates data from all other plugins."""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

import json
from datetime import date, timedelta

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from core.plugin_base import PluginBase
from core.contracts.dashboard_dto import DashboardSectionDef
from plugins.dashboard.ui import DashboardUI


# ── Dashboard section catalogue ───────────────────────────────────────────────
# Each entry describes one toggleable section.  The order here matches the
# dialog display order.  Section IDs must match the keys used in
# DashboardUI._section_widgets (set by _wrap_section / sidebar builder).

_DASHBOARD_SECTIONS: list[DashboardSectionDef] = [
    DashboardSectionDef(
        id="command_overview",
        label="Command Overview",
        description="Stats at a glance — total paints, active projects, "
                    "sessions this week, hobby streak and monthly hours",
        tab="overview",
    ),
    DashboardSectionDef(
        id="active_projects",
        label="Active Projects",
        description="Your top in-progress projects with live completion "
                    "progress bars",
        tab="overview",
    ),
    DashboardSectionDef(
        id="calendar_agenda",
        label="Today's Agenda",
        description="Today's calendar events, upcoming milestones and "
                    "overdue items",
        tab="overview",
    ),
    DashboardSectionDef(
        id="recommendations",
        label="Recommended Actions",
        description="Smart next-step suggestions powered by your active "
                    "plugins — restocks, priming reminders and more",
        tab="overview",
    ),
    DashboardSectionDef(
        id="quick_actions",
        label="Quick Actions (sidebar)",
        description="One-click shortcuts to add paints, start projects, "
                    "log models and more",
        tab="overview",
    ),
    DashboardSectionDef(
        id="alerts_mini",
        label="Alerts (sidebar)",
        description="Critical alerts preview shown in the overview sidebar",
        tab="overview",
    ),
    DashboardSectionDef(
        id="recent_activity",
        label="Recent Activity",
        description="Chronological log of everything you've done across "
                    "all your hobby plugins",
        tab="activity",
    ),
    DashboardSectionDef(
        id="notifications",
        label="Notifications Panel",
        description="Full alerts and notifications from all installed "
                    "plugins",
        tab="alerts",
    ),
]

# ── Events that should trigger a dashboard refresh
_REFRESH_EVENTS = [
    # Paint tracker
    "paint_added", "paint_removed", "paint_updated",
    # Model tracker
    "model_added", "model_removed", "model_updated",
    # Army builder
    "army_created", "army_deleted", "army_updated",
    "unit_added", "unit_removed", "unit_updated",
    # Campaign tracker
    "campaign_created", "campaign_deleted", "campaign_updated",
    "battle_logged",
    # Tool tracker
    "tool_added", "tool_removed", "tool_updated",
    # Materials tracker
    "material_added", "material_removed", "material_updated",
    # Calendar — refresh dashboard when events change
    "calendar_event_added", "calendar_event_updated", "calendar_event_deleted",
    "calendar_settings_changed",
    # Plugin lifecycle — refresh when a provider re-registers
    "dashboard_provider_updated",
    # Project tracker
    "project_create", "project_updated", "project_delete", "project_milestone_add",
    "project_milestone_toggle", "project_milestone_quantity_step",
    "project_milestone_uncompleted",
    "project_session_log", "project_session_end", "project_milestone_completed",
    "project_gallery_add",
]

# Events that also log an activity entry: (icon, description_prefix)
# The handler will append ": <name>" from the event payload when available.
_ACTIVITY_EVENTS: dict[str, tuple[str, str]] = {
    # Paints
    "paint_added":                  ("🎨", "Added paint"),
    "paint_removed":                ("🗑", "Removed paint"),
    "paint_updated":                ("✏️", "Updated paint"),
    # Models
    "model_added":                  ("🗿", "Added model"),
    "model_removed":                ("🗑", "Removed model"),
    "model_updated":                ("✏️", "Updated model"),
    # Armies
    "army_created":                 ("⚔️",  "Created army"),
    "army_deleted":                 ("🗑",  "Deleted army"),
    "army_updated":                 ("✏️",  "Updated army"),
    # Campaigns
    "campaign_created":             ("🏕",  "Started campaign"),
    "campaign_deleted":             ("🗑",  "Deleted campaign"),
    "battle_logged":                ("🎲",  "Logged battle"),
    # Tools
    "tool_added":                   ("🔧", "Added tool"),
    "tool_removed":                 ("🗑", "Removed tool"),
    "tool_updated":                 ("✏️", "Updated tool"),
    # Materials
    "material_added":               ("🌿", "Added material"),
    "material_removed":             ("🗑", "Removed material"),
    "material_updated":             ("✏️", "Updated material"),
    # Projects
    "project_create":               ("📁", "Started project"),
    "project_session_log":          ("⏱",  "Logged hobby session"),
    "project_milestone_completed":  ("✅", "Completed milestone"),
    "project_gallery_add":          ("📸", "Added progress photo"),
}

_MAX_ACTIVITY = 30   # extended from 20 — history matters


class Plugin(PluginBase):
    display_name = "Dashboard"

    def __init__(self, context):
        super().__init__(context)
        self._ui: DashboardUI | None = None
        self._refresh_timer: QTimer | None = None
        self._streak = 0
        self._last_stats: list = []   # full unfiltered stat list, refreshed each cycle
        # Track which provider IDs we successfully registered so deactivate()
        # can clean up exactly those — no hardcoded list (M-15).
        self._registered_provider_ids: list[str] = []

    # ── PluginBase interface ───────────────────────────────────────────────────

    def activate(self):
        self._streak = self._update_hobby_streak()
        self._log_session_today()

        self._ui = DashboardUI(self.context)
        self._ui.set_streak(self._streak)
        self._ui.set_greeting(self._greeting())
        self._ui.action_requested.connect(self._on_action)
        self._ui.name_changed.connect(self._on_name_changed)

        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)

        self._ui.customize_clicked.connect(self._open_customize_dialog)

        self._register_events()
        self._connect_theme()
        self._register_settings_page()

        # Defer until all other plugins have activated and registered their services
        QTimer.singleShot(200, self._deferred_setup)

    def get_ui(self) -> QWidget | None:
        return self._ui

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

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _deferred_setup(self):
        self._setup_providers()
        self._do_refresh()

    def _setup_providers(self):
        registry = self.context.services.try_get("dashboard_registry")
        if not registry:
            log.warning("[DASHBOARD] dashboard_registry not found — skipping providers")
            return

        # These are fallback providers used when only the v1 plugin is loaded.
        # If a v2 plugin is also active (e.g. campaign_tracker_v2), its dedicated
        # provider registers under the same canonical key AFTER this runs and
        # naturally overwrites the fallback.  On deactivation the v2 plugin
        # restores or unregisters cleanly via the _owner marker pattern.
        _PROVIDER_MAP = [
            ("project_tracker",  "plugins.project_tracker.providers.dashboard_provider", "ProjectDashboardProvider",  "project_service"),
            ("paint_tracker",    "plugins.dashboard.providers.paint_provider",    "PaintDashboardProvider",    "paint_service"),
            ("model_tracker",    "plugins.dashboard.providers.model_provider",    "ModelDashboardProvider",    "model_service"),
            ("army_builder",     "plugins.dashboard.providers.army_provider",     "ArmyDashboardProvider",     "army_service"),
            ("campaign_tracker", "plugins.dashboard.providers.campaign_provider", "CampaignDashboardProvider", "campaign_service"),
            ("tool_tracker",     "plugins.dashboard.providers.tool_provider",     "ToolDashboardProvider",     "tool_service"),
            ("materials_tracker","plugins.dashboard.providers.materials_provider","MaterialsDashboardProvider","material_service"),
        ]

        import importlib
        self._registered_provider_ids = []
        for plugin_id, module_path, class_name, service_name in _PROVIDER_MAP:
            # try_get returns None instead of raising when service isn't registered
            svc = self.context.services.try_get(service_name)
            if not svc:
                continue
            try:
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                provider = cls(svc)
                registry.register_provider(plugin_id, provider)
                self._registered_provider_ids.append(plugin_id)
            except Exception as e:
                log.error(f"[DASHBOARD] Failed to register provider {plugin_id}: {e}")

    def _register_settings_page(self):
        registry = self.context.services.try_get("settings_registry")
        if registry:
            from plugins.dashboard.settings_page import ProfileSettingsPage
            registry.register_page("Profile", lambda ctx: ProfileSettingsPage(ctx))

    # ── Dashboard customization ────────────────────────────────────────────────

    def _open_customize_dialog(self):
        """Open the section + card visibility dialog."""
        from plugins.dashboard.customize_dialog import DashboardCustomizeDialog
        settings = self.context.services.get("settings")
        hidden_sections = self._load_json_list("dashboard.hidden_sections")
        hidden_cards    = self._load_json_list("dashboard.hidden_cards")

        dlg = DashboardCustomizeDialog(
            sections        = _DASHBOARD_SECTIONS,
            hidden_sections = hidden_sections,
            cards           = self._last_stats,
            hidden_cards    = hidden_cards,
            context         = self.context,
            parent          = self._ui,
        )
        if dlg.exec():
            new_hidden_sections = dlg.get_hidden_sections()
            new_hidden_cards    = dlg.get_hidden_cards()
            if settings:
                settings.set("dashboard.hidden_sections",
                             json.dumps(new_hidden_sections))
                settings.set("dashboard.hidden_cards",
                             json.dumps(new_hidden_cards))
            self._apply_section_visibility()
            # Re-render cards with the new filter applied
            self._schedule_refresh(50)

    def _apply_section_visibility(self):
        """Read saved hidden-section prefs and show/hide each section widget."""
        if not self._ui:
            return
        hidden = set(self._load_json_list("dashboard.hidden_sections"))
        for sec in _DASHBOARD_SECTIONS:
            self._ui.set_section_visible(sec.id, sec.id not in hidden)

    def _connect_theme(self):
        tm = self.context.services.try_get("theme_manager")
        if tm:
            try:
                tm.theme_changed.connect(self._on_theme_changed)
            except Exception:
                pass

    def _on_theme_changed(self, _theme_id: str = ""):
        """Re-apply theme to persistent frames then do a full data refresh."""
        if self._ui:
            # Re-style the paint intel section boxes (they persist between refreshes)
            try:
                self._ui._paint_intel.apply_theme()
            except Exception:
                pass
        self._schedule_refresh(50)

    def _register_events(self):
        bus = self.context.event_bus

        for event in _REFRESH_EVENTS:
            if event in _ACTIVITY_EVENTS:
                icon, desc = _ACTIVITY_EVENTS[event]
                def _make_activity_handler(ev_icon: str, ev_desc: str):
                    def _handler(payload: dict | None = None,
                                 _i=ev_icon, _d=ev_desc):
                        # Try to enrich the description with the item's name
                        description = _d
                        if payload and isinstance(payload, dict):
                            for key in ("name", "title", "paint_name",
                                        "model_name", "army_name",
                                        "campaign_name", "tool_name",
                                        "material_name"):
                                val = payload.get(key, "")
                                if val:
                                    description = f"{_d}: {val}"
                                    break
                        self.log_activity(_i, description)
                        self._schedule_refresh(300)
                    return _handler
                try:
                    bus.subscribe(event, _make_activity_handler(icon, desc))
                except Exception:
                    pass
            else:
                try:
                    bus.subscribe(event, self._on_data_event)
                except Exception:
                    pass

        try:
            bus.subscribe("user_profile_updated", self._on_profile_updated)
        except Exception:
            pass

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_data_event(self, payload: dict | None = None):
        self._schedule_refresh(300)

    def _on_name_changed(self, name: str):
        """Immediately refresh the greeting after the user saves a new name (banner click)."""
        if self._ui:
            self._ui.set_greeting(self._greeting())

    def _on_profile_updated(self, payload: dict | None = None):
        """Immediately refresh the greeting after the user saves via Settings dialog."""
        if self._ui:
            self._ui.set_greeting(self._greeting())

    def _on_action(self, event: str, payload: dict):
        """Forward quick-action / card button events onto the event bus."""
        try:
            self.context.event_bus.emit(event, payload)
        except Exception as e:
            log.error(f"[DASHBOARD] Failed to emit action {event}: {e}")

    # ── Refresh ────────────────────────────────────────────────────────────────

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

        try:
            all_stats = self._get_self_stats() + registry.get_all_command_stats()
            # Cache for the customize dialog (always the full unfiltered list)
            self._last_stats = all_stats
            hidden_cards = set(self._load_json_list("dashboard.hidden_cards"))
            visible_stats = [s for s in all_stats if s.card_id not in hidden_cards]
            self._ui.refresh_command_stats(visible_stats)
        except Exception as e:
            log.error(f"[DASHBOARD] refresh command stats: {e}")

        # Fetch project cards once; pass to both consumers independently
        project_cards = []
        try:
            project_cards = registry.get_all_projects()
        except Exception as e:
            log.error(f"[DASHBOARD] get_all_projects: {e}")

        try:
            self._ui.refresh_projects(project_cards)
        except Exception as e:
            log.error(f"[DASHBOARD] refresh projects: {e}")

        try:
            self._ui.refresh_active_projects_strip(project_cards)
        except Exception as e:
            log.error(f"[DASHBOARD] refresh active projects strip: {e}")

        try:
            self._ui.refresh_quick_actions(registry.get_all_quick_actions())
        except Exception as e:
            log.error(f"[DASHBOARD] refresh quick actions: {e}")

        try:
            notifications = registry.get_all_notifications()
            self._ui.refresh_notifications(notifications)
        except Exception as e:
            log.error(f"[DASHBOARD] refresh notifications: {e}")
            notifications = []

        try:
            self._ui.refresh_alerts_mini(notifications)
        except Exception as e:
            log.error(f"[DASHBOARD] refresh alerts mini: {e}")

        try:
            self._ui.refresh_recommendations(registry.get_all_recommendations())
        except Exception as e:
            log.error(f"[DASHBOARD] refresh recommendations: {e}")

        try:
            self._refresh_paint_intel(registry)
        except Exception as e:
            log.error(f"[DASHBOARD] refresh paint intel: {e}")

        try:
            self._refresh_activity()
        except Exception as e:
            log.error(f"[DASHBOARD] refresh activity: {e}")

        try:
            self._refresh_calendar_intelligence()
        except Exception as e:
            log.error(f"[DASHBOARD] refresh calendar intelligence: {e}")

        # Apply user's section visibility preferences last, after all data is loaded
        self._apply_section_visibility()

    def _refresh_paint_intel(self, registry):
        provider = registry.get_provider("paint_tracker")
        if not provider:
            self._ui.refresh_paint_intel([], [], {})
            return
        low    = provider.get_low_stock_paints(limit=8)
        recent = provider.get_recent_paints(limit=5)
        brands = provider.get_brand_breakdown()
        self._ui.refresh_paint_intel(low, recent, brands)

    def _refresh_activity(self):
        activities = self._load_activity_log()
        self._ui.refresh_activity(activities)

    def _refresh_calendar_intelligence(self):
        """Pull today/week/milestone/overdue data from calendar_service and push to UI."""
        cal_svc = self.context.services.try_get("calendar_service")
        if not cal_svc:
            return   # Calendar plugin not loaded — widget stays in empty state

        today_events = cal_svc.get_today()
        week_events  = cal_svc.get_upcoming_week()
        milestones   = cal_svc.get_milestones()

        # Overdue: not all calendar services expose this — gracefully skip if absent
        overdue: list = []
        try:
            overdue = cal_svc.get_overdue() or []
        except AttributeError:
            pass  # calendar_service version that predates get_overdue()
        except Exception as e:
            log.error(f"[DASHBOARD] get_overdue(): {e}")

        self._ui.refresh_calendar_intelligence(today_events, week_events, milestones, overdue)

    # ── Self stats (hobby engagement) ─────────────────────────────────────────

    def _get_self_stats(self) -> list:
        from core.contracts.dashboard_dto import CommandStat
        stats = []

        # Hobby streak
        if self._streak > 0:
            if self._streak == 1:
                sub = "day in a row — keep it up!"
            elif self._streak < 7:
                sub = f"days in a row 🔥"
            else:
                sub = f"days — legendary streak! 🔥"
            stats.append(CommandStat(
                label    = "Hobby Streak",
                value    = str(self._streak),
                subtitle = sub,
                color    = "success" if self._streak >= 3 else "accent",
                icon     = "🔥",
                card_id  = "dashboard.hobby_streak",
            ))

        # Sessions this week
        sessions = self._count_sessions_this_week()
        stats.append(CommandStat(
            label    = "This Week",
            value    = str(sessions),
            subtitle = f"session{'s' if sessions != 1 else ''} so far",
            color    = "success" if sessions >= 4 else ("warning" if sessions == 0 else "accent"),
            icon     = "📅",
            card_id  = "dashboard.this_week",
        ))

        # Monthly hobby hours (from project tracker sessions)
        hours = self._get_monthly_hours()
        if hours > 0:
            stats.append(CommandStat(
                label    = "This Month",
                value    = f"{hours}h",
                subtitle = "hobby time logged",
                color    = "success" if hours >= 10 else "accent",
                icon     = "⏱",
                card_id  = "dashboard.this_month",
            ))

        return stats

    def _get_monthly_hours(self) -> float:
        """Sum logged session hours from project_service for the current calendar month."""
        proj_svc = self.context.services.try_get("project_service")
        if not proj_svc:
            return 0.0
        try:
            today = date.today()
            sessions = proj_svc.get_sessions()
            total = 0.0
            for s in sessions:
                s_date = (
                    getattr(s, "date", None)
                    or getattr(s, "logged_at", None)
                    or getattr(s, "session_date", None)
                )
                if s_date:
                    try:
                        d = date.fromisoformat(str(s_date)[:10])
                        if d.year == today.year and d.month == today.month:
                            duration = (
                                getattr(s, "duration_hours", None)
                                or getattr(s, "hours", None)
                                or getattr(s, "duration", None)
                                or 0
                            )
                            total += float(duration)
                    except Exception:
                        pass
            return round(total, 1)
        except Exception:
            return 0.0

    # ── JSON list helper ───────────────────────────────────────────────────────

    def _load_json_list(self, settings_key: str, default: str = "[]") -> list:
        """Load a JSON-encoded list from settings, returning [] on any error (M-14)."""
        settings = self.context.services.get("settings")
        if not settings:
            return []
        raw = settings.get(settings_key, default)
        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def _log_session_today(self):
        """Record today as a hobby session day."""
        settings = self.context.services.get("settings")
        if not settings:
            return
        today = date.today().isoformat()
        dates = self._load_json_list("dashboard.session_dates")
        if today not in dates:
            dates.append(today)
            dates = dates[-90:]  # keep rolling 90-day window
            settings.set("dashboard.session_dates", json.dumps(dates))

    def _count_sessions_this_week(self) -> int:
        dates  = self._load_json_list("dashboard.session_dates")
        today  = date.today()
        monday = today - timedelta(days=today.weekday())
        week   = {(monday + timedelta(days=i)).isoformat() for i in range(7)}
        return sum(1 for d in dates if d in week)

    # ── Activity log ───────────────────────────────────────────────────────────

    def _load_activity_log(self) -> list[dict]:
        return self._load_json_list("dashboard.recent_activity")

    def log_activity(self, icon: str, description: str, plugin_id: str = "") -> None:
        """Public API — other plugins can call this to log an activity entry."""
        settings = self.context.services.get("settings")
        if not settings:
            return
        from datetime import datetime
        # Store full ISO datetime so the widget can group entries by date.
        timestamp = datetime.now().isoformat(timespec="seconds")
        entry = {"icon": icon, "description": description,
                 "timestamp": timestamp, "plugin_id": plugin_id}
        log = self._load_activity_log()
        log.insert(0, entry)
        log = log[:_MAX_ACTIVITY]
        settings.set("dashboard.recent_activity", json.dumps(log))

    # ── Hobby streak ───────────────────────────────────────────────────────────

    def _update_hobby_streak(self) -> int:
        settings = self.context.services.get("settings")
        if not settings:
            return 0
        today_str  = date.today().isoformat()
        last_str   = settings.get("dashboard.last_session_date", "")
        streak     = int(settings.get("dashboard.hobby_streak", 0) or 0)

        if last_str == today_str:
            return streak                            # already counted today

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if last_str == yesterday:
            streak += 1                              # consecutive day
        else:
            streak = 1                               # broke the streak

        settings.set("dashboard.last_session_date", today_str)
        settings.set("dashboard.hobby_streak", str(streak))
        return streak

    # ── Greeting ───────────────────────────────────────────────────────────────

    def _get_display_name(self) -> str:
        settings = self.context.services.get("settings")
        if settings:
            name = settings.get("user.display_name", "").strip()
            if name:
                return name
        return "Hobbyist"

    def _greeting(self) -> str:
        from datetime import datetime
        hour = datetime.now().hour
        if hour < 12:
            prefix = "Good morning"
        elif hour < 18:
            prefix = "Good afternoon"
        else:
            prefix = "Good evening"
        return f"{prefix}, {self._get_display_name()}!"
