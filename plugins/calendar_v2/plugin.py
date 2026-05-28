"""
Calendar 2.0 — Plugin entry point.

Reuses the same CalendarService / Repository / models as v1 (same DB table,
so existing data is preserved automatically).  Only the UI is new.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from PySide6.QtCore import QTimer
from core.plugin_base import PluginBase


class Plugin(PluginBase):
    plugin_id    = "calendar_v2"
    display_name = "Calendar 2.0"
    name         = "Calendar 2.0"
    version      = "2.0.0"
    description  = "Hobby Timeline, Planner & Strategic Dashboard Intelligence"

    def __init__(self, context):
        super().__init__(context)
        self._service                      = None
        self._ui                           = None
        self._refresh_timer: QTimer | None = None
        self._subscriptions: list[tuple]   = []

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def activate(self):
        self._init_service()
        self._init_ui()
        self._register_dashboard_provider()
        self._register_settings_page()
        self._register_events()
        QTimer.singleShot(200, self._initial_refresh)
        log.info("[CALENDAR V2] Activated")

    def deactivate(self):
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None
        self._unsubscribe_all()
        registry = self.context.services.try_get("dashboard_registry")
        if registry:
            try:
                registry.unregister_provider("calendar")
            except Exception:
                pass
        self._ui      = None
        self._service = None
        log.info("[CALENDAR V2] Deactivated")

    def get_ui(self):
        return self._ui

    # ── Init helpers ───────────────────────────────────────────────────────────

    def _init_service(self):
        from .repository import CalendarRepository
        from .service    import CalendarService
        db = self.context.services.get("db")
        if not db:
            raise RuntimeError("[CALENDAR V2] DatabaseService ('db') not found")
        repo = CalendarRepository(db)
        self._service = CalendarService(repo)
        self.context.services.register("calendar_service", self._service, override=True)

    def _init_ui(self):
        from .ui import CalendarV2UI
        self._ui = CalendarV2UI(self.context, self._service)
        self._ui.setProperty("plugin_id", "calendar_v2")

    def _register_dashboard_provider(self):
        registry = self.context.services.try_get("dashboard_registry")
        if registry and self._service:
            from .provider import CalendarDashboardProvider
            registry.register_provider("calendar", CalendarDashboardProvider(self._service))

    def _register_settings_page(self):
        reg = self.context.services.try_get("settings_registry")
        if reg:
            try:
                from .settings_page import CalendarV2SettingsPage
                reg.register_page("Calendar 2.0", lambda ctx: CalendarV2SettingsPage(ctx))
            except Exception as e:
                log.error(f"[CALENDAR V2] Failed to register settings page: {e}")

    # ── Event subscriptions ────────────────────────────────────────────────────

    def _register_events(self):
        pairs = [
            ("calendar_settings_changed", self._on_settings_changed),
            ("paint_added",               self._on_paint_added),
            ("paint_updated",             self._on_paint_updated),
            ("model_added",               self._on_model_added),
            ("model_updated",             self._on_model_updated),
            ("army_created",              self._on_army_created),
            ("army_updated",              lambda p=None: self._schedule_refresh()),
            ("campaign_created",          self._on_campaign_created),
            ("campaign_updated",          lambda p=None: self._schedule_refresh()),
            ("battle_logged",             self._on_battle_logged),
            ("tool_added",                self._on_tool_added),
            ("material_added",            self._on_material_added),
            ("project_session_log",       self._on_project_session_log),
            ("project_session_end",       self._on_project_session_end),
        ]
        for event, handler in pairs:
            try:
                self.context.event_bus.subscribe(event, handler)
                self._subscriptions.append((event, handler))
            except Exception as e:
                log.error(f"[CALENDAR V2] Failed to subscribe '{event}': {e}")

    def _unsubscribe_all(self):
        for event, handler in self._subscriptions:
            try:
                self.context.event_bus.unsubscribe(event, handler)
            except Exception:
                pass
        self._subscriptions.clear()

    # ── Auto-timeline helpers ──────────────────────────────────────────────────

    def _auto_suggest_enabled(self) -> bool:
        s = self.context.services.try_get("settings")
        return s.get("calendar.auto_suggest", True) if s else True

    def _create_timeline_event(self, title, event_category, session_type="Custom",
                                linked_plugin="", linked_id="", linked_name="",
                                source_event="", notes=""):
        if not self._service:
            return
        try:
            self._service.add_event(
                title=title, session_type=session_type,
                event_category=event_category, auto_generated=True,
                source_event=source_event, linked_plugin=linked_plugin,
                linked_id=str(linked_id) if linked_id else "",
                linked_name=linked_name, notes=notes, duration_minutes=0,
            )
        except Exception as e:
            log.error(f"[CALENDAR V2] Failed to create timeline event: {e}")

    # ── Event handlers (identical logic to v1) ─────────────────────────────────

    def _on_paint_added(self, payload=None):
        payload = payload or {}
        try:
            if not self._auto_suggest_enabled():
                return
            name  = payload.get("name") or payload.get("paint_name", "")
            brand = payload.get("brand", "")
            label = f"Purchased: {name}" if not brand else f"Purchased: {name} ({brand})"
            self._create_timeline_event(label, "Purchase", linked_plugin="paint_tracker",
                linked_id=payload.get("id", ""), linked_name=name, source_event="paint_added")
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_paint_added: {e}")

    def _on_paint_updated(self, payload=None):
        payload = payload or {}
        try:
            if payload.get("restocked") or payload.get("quantity_added"):
                name = payload.get("name") or payload.get("paint_name", "Paint")
                self._create_timeline_event(f"Restocked: {name}", "Purchase",
                    linked_plugin="paint_tracker", linked_id=payload.get("id", ""),
                    linked_name=name, source_event="paint_updated")
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_paint_updated: {e}")

    def _on_model_added(self, payload=None):
        payload = payload or {}
        try:
            if self._auto_suggest_enabled():
                name = payload.get("name") or payload.get("model_name", "")
                if name:
                    self._create_timeline_event(f"Added to collection: {name}", "Purchase",
                        linked_plugin="model_tracker", linked_id=payload.get("id", ""),
                        linked_name=name, source_event="model_added")
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_model_added: {e}")

    def _on_model_updated(self, payload=None):
        payload = payload or {}
        try:
            status = payload.get("status", "")
            name   = payload.get("name") or payload.get("model_name", "")
            if status and status.lower() in ("completed", "done", "finished") and name:
                if self._auto_suggest_enabled():
                    self._create_timeline_event(f"Completed: {name}", "Completed Project",
                        session_type="Painting Session", linked_plugin="model_tracker",
                        linked_id=payload.get("id", ""), linked_name=name,
                        source_event="model_updated")
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_model_updated: {e}")

    def _on_army_created(self, payload=None):
        payload = payload or {}
        try:
            if self._auto_suggest_enabled():
                name = payload.get("name") or payload.get("army_name", "")
                if name:
                    self._create_timeline_event(f"Created army: {name}", "Campaign Event",
                        session_type="Army Prep", linked_plugin="army_builder",
                        linked_id=payload.get("id", ""), linked_name=name,
                        source_event="army_created")
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_army_created: {e}")

    def _on_campaign_created(self, payload=None):
        payload = payload or {}
        try:
            if self._auto_suggest_enabled() and self._service:
                name = payload.get("name") or payload.get("title", "Campaign")
                self._service.add_event(
                    title=f"Campaign Planning: {name}", session_type="Campaign Writing",
                    event_category="Campaign Event", auto_generated=True,
                    source_event="campaign_created", linked_plugin="campaign_tracker",
                    linked_id=str(payload.get("id", "")), linked_name=name,
                )
                self._create_timeline_event(f"Started campaign: {name}", "Campaign Event",
                    linked_plugin="campaign_tracker", linked_id=payload.get("id", ""),
                    linked_name=name, source_event="campaign_created")
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_campaign_created: {e}")

    def _on_battle_logged(self, payload=None):
        payload = payload or {}
        try:
            if self._auto_suggest_enabled():
                campaign = payload.get("campaign_name") or payload.get("campaign_id", "")
                battle   = payload.get("name") or payload.get("title", "")
                title    = f"Battle: {battle}" if battle else "Battle logged"
                if campaign:
                    title += f" ({campaign})"
                self._create_timeline_event(title, "Campaign Event", session_type="Game Night",
                    linked_plugin="campaign_tracker", linked_id=payload.get("id", ""),
                    linked_name=str(campaign), source_event="battle_logged")
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_battle_logged: {e}")

    def _on_tool_added(self, payload=None):
        payload = payload or {}
        try:
            if self._auto_suggest_enabled():
                name = payload.get("name") or payload.get("tool_name", "")
                if name:
                    self._create_timeline_event(f"Added tool: {name}", "Purchase",
                        linked_plugin="tool_tracker", linked_id=payload.get("id", ""),
                        linked_name=name, source_event="tool_added")
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_tool_added: {e}")

    def _on_material_added(self, payload=None):
        payload = payload or {}
        try:
            if self._auto_suggest_enabled():
                name = payload.get("name") or payload.get("material_name", "")
                if name:
                    self._create_timeline_event(f"Added material: {name}", "Purchase",
                        linked_plugin="materials_tracker", linked_id=payload.get("id", ""),
                        linked_name=name, source_event="material_added")
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_material_added: {e}")

    def _on_project_session_log(self, payload=None):
        payload = payload or {}
        try:
            if not self._auto_suggest_enabled() or not self._service:
                self._schedule_refresh()
                return
            project_id       = payload.get("project_id")
            duration_minutes = int(payload.get("duration_minutes") or 0)
            notes            = payload.get("notes", "")
            started_at       = payload.get("started_at", "") or ""
            event_date       = started_at[:10] if len(started_at) >= 10 else ""
            project_name     = ""
            proj_svc = self.context.services.try_get("project_service")
            if proj_svc and project_id:
                try:
                    p = proj_svc.get_project(project_id)
                    if p:
                        project_name = p.name
                except Exception:
                    pass
            self._service.add_event(
                title=f"Hobby Session: {project_name}" if project_name else "Hobby Session",
                session_type="Hobby Session", event_category="Hobby Session",
                event_date=event_date, duration_minutes=duration_minutes,
                notes=notes, linked_plugin="project_tracker",
                linked_id=str(project_id) if project_id else "",
                linked_name=project_name, auto_generated=True,
                source_event="project_session_log",
            )
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_project_session_log: {e}")

    def _on_project_session_end(self, payload=None):
        payload = payload or {}
        try:
            if not self._auto_suggest_enabled() or not self._service:
                self._schedule_refresh()
                return
            project_id       = payload.get("project_id")
            notes            = payload.get("notes", "")
            project_name     = ""
            duration_minutes = 0
            proj_svc = self.context.services.try_get("project_service")
            if proj_svc and project_id:
                try:
                    p = proj_svc.get_project(project_id)
                    if p:
                        project_name = p.name
                except Exception:
                    pass
                try:
                    sessions  = proj_svc.get_sessions(project_id)
                    completed = [s for s in sessions
                                 if not getattr(s, "is_active", False)
                                 and getattr(s, "duration_minutes", 0) > 0]
                    if completed:
                        duration_minutes = completed[0].duration_minutes
                except Exception:
                    pass
            self._service.add_event(
                title=f"Hobby Session: {project_name}" if project_name else "Hobby Session",
                session_type="Hobby Session", event_category="Hobby Session",
                duration_minutes=duration_minutes, notes=notes,
                linked_plugin="project_tracker",
                linked_id=str(project_id) if project_id else "",
                linked_name=project_name, auto_generated=True,
                source_event="project_session_end",
            )
            self._schedule_refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2] _on_project_session_end: {e}")

    def _on_settings_changed(self, payload=None):
        self._schedule_refresh()

    # ── Refresh ────────────────────────────────────────────────────────────────

    def _initial_refresh(self):
        if self._ui:
            try:
                self._ui.refresh()
            except Exception as e:
                log.error(f"[CALENDAR V2] refresh error: {e}")

    def _schedule_refresh(self, delay_ms: int = 300):
        if self._refresh_timer is None:
            self._refresh_timer = QTimer()
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._initial_refresh)
        self._refresh_timer.stop()
        self._refresh_timer.start(delay_ms)
