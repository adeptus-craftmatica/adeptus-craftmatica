"""
Calendar Plugin

Lifecycle controller — wires the service, UI, settings, dashboard provider,
and cross-plugin events together.

Cross-plugin integration:
  - Subscribes to events from ALL sibling plugins to build an automatic timeline.
  - Registers "calendar_service" in ServiceRegistry.
  - Registers a CalendarDashboardProvider with DashboardRegistry.
  - Registers a settings page with SettingsRegistry.

Auto-timeline philosophy:
  Every significant action in the app (buying a paint, creating an army, logging
  a battle) becomes a Timeline event on the date it happened.  Users can always
  edit or delete these records.  auto_generated=True marks them so the UI can
  display them differently from manually scheduled sessions.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer

from core.plugin_base import PluginBase


class Plugin(PluginBase):

    plugin_id    = "calendar"
    display_name = "Calendar"
    name         = "Calendar"
    version      = "0.2.0"
    description  = "Hobby Timeline, Planner & Strategic Dashboard Intelligence"

    def __init__(self, context):
        super().__init__(context)
        self._service          = None
        self._ui               = None
        self._refresh_timer: QTimer | None = None
        self._subscriptions: list[tuple[str, object]] = []

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def activate(self):
        print(f"[PLUGIN] {self.display_name} activating...")

        self._init_service()
        self._init_ui()
        self._register_dashboard_provider()
        self._register_settings_page()
        self._register_events()

        QTimer.singleShot(200, self._initial_refresh)

        print(f"[PLUGIN] {self.display_name} activated")

    def deactivate(self):
        print(f"[PLUGIN] {self.display_name} deactivating...")

        if self._refresh_timer is not None:
            try:
                self._refresh_timer.stop()
            except Exception:
                pass
            self._refresh_timer = None

        self._unsubscribe_all()

        dashboard_registry = self.context.services.try_get("dashboard_registry")
        if dashboard_registry:
            try:
                dashboard_registry.unregister_provider("calendar")
            except Exception:
                pass

        self._ui      = None
        self._service = None

        print(f"[PLUGIN] {self.display_name} deactivated")

    def get_ui(self):
        return self._ui

    # ── Initialisation ─────────────────────────────────────────────────────────

    def _init_service(self):
        from .repository import CalendarRepository
        from .service import CalendarService

        db = self.context.services.get("db")
        if not db:
            raise RuntimeError("[CALENDAR] DatabaseService ('db') not found")

        repo = CalendarRepository(db)
        self._service = CalendarService(repo)
        self.context.services.register("calendar_service", self._service, override=True)

    def _init_ui(self):
        from .ui import CalendarUI
        self._ui = CalendarUI(self.context)
        self._ui.set_service(self._service)

    def _register_dashboard_provider(self):
        dashboard_registry = self.context.services.try_get("dashboard_registry")
        if dashboard_registry and self._service:
            from .provider import CalendarDashboardProvider
            provider = CalendarDashboardProvider(self._service)
            dashboard_registry.register_provider("calendar", provider)

    def _register_settings_page(self):
        settings_registry = self.context.services.try_get("settings_registry")
        if settings_registry:
            from .settings_page import CalendarSettingsPage
            settings_registry.register_page(
                "Calendar",
                lambda ctx: CalendarSettingsPage(ctx),
            )

    # ── Event subscriptions ────────────────────────────────────────────────────

    def _register_events(self):
        subscriptions = [
            # ── Calendar-internal ──────────────────────────────────────────────
            ("calendar_settings_changed", self._on_settings_changed),

            # ── Paint Tracker ──────────────────────────────────────────────────
            ("paint_added",              self._on_paint_added),
            ("paint_updated",            self._on_paint_updated),

            # ── Model Tracker ──────────────────────────────────────────────────
            ("model_added",              self._on_model_added),
            ("model_updated",            self._on_model_updated),

            # ── Army Builder ───────────────────────────────────────────────────
            ("army_created",             self._on_army_created),
            ("army_updated",             self._on_army_updated),

            # ── Campaign Tracker ───────────────────────────────────────────────
            ("campaign_created",         self._on_campaign_created),
            ("campaign_updated",         self._on_campaign_updated),
            ("battle_logged",            self._on_battle_logged),

            # ── Tool Tracker ───────────────────────────────────────────────────
            ("tool_added",               self._on_tool_added),

            # ── Materials Tracker ──────────────────────────────────────────────
            ("material_added",           self._on_material_added),

            # ── Project Tracker ────────────────────────────────────────────────
            ("project_session_log",      self._on_project_session_log),
            ("project_session_end",      self._on_project_session_end),
        ]

        for event, handler in subscriptions:
            try:
                self._subscribe(event, handler)
            except Exception as e:
                print(f"[CALENDAR] Failed to subscribe to '{event}': {e}")

    def _subscribe(self, event: str, handler):
        self.context.event_bus.subscribe(event, handler)
        self._subscriptions.append((event, handler))

    def _unsubscribe_all(self):
        for event, handler in self._subscriptions:
            try:
                self.context.event_bus.unsubscribe(event, handler)
            except Exception:
                pass
        self._subscriptions.clear()

    # ── Auto-timeline helpers ──────────────────────────────────────────────────

    def _auto_suggest_enabled(self) -> bool:
        settings = self.context.services.try_get("settings")
        return settings.get("calendar.auto_suggest", True) if settings else True

    def _create_timeline_event(
        self,
        title: str,
        event_category: str,
        session_type: str = "Custom",
        linked_plugin: str = "",
        linked_id: str = "",
        linked_name: str = "",
        source_event: str = "",
        notes: str = "",
    ) -> None:
        """Create a single auto-generated Timeline record for today."""
        if not self._service:
            return
        try:
            self._service.add_event(
                title          = title,
                session_type   = session_type,
                event_category = event_category,
                auto_generated = True,
                source_event   = source_event,
                linked_plugin  = linked_plugin,
                linked_id      = str(linked_id) if linked_id else "",
                linked_name    = linked_name,
                notes          = notes,
                duration_minutes = 0,
            )
        except Exception as e:
            print(f"[CALENDAR] Failed to create timeline event '{title}': {e}")

    # ── Event handlers — Paint Tracker ─────────────────────────────────────────

    def _on_paint_added(self, payload: dict):
        try:
            if not self._auto_suggest_enabled():
                return
            name  = payload.get("name") or payload.get("paint_name", "")
            brand = payload.get("brand", "")
            label = f"Purchased: {name}" if not brand else f"Purchased: {name} ({brand})"
            self._create_timeline_event(
                title          = label,
                event_category = "Purchase",
                linked_plugin  = "paint_tracker",
                linked_id      = payload.get("id", ""),
                linked_name    = name,
                source_event   = "paint_added",
            )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_paint_added error: {e}")

    def _on_paint_updated(self, payload: dict):
        try:
            # Only create a timeline event for notable updates (e.g. restocked)
            if payload.get("restocked") or payload.get("quantity_added"):
                name = payload.get("name") or payload.get("paint_name", "Paint")
                self._create_timeline_event(
                    title          = f"Restocked: {name}",
                    event_category = "Purchase",
                    linked_plugin  = "paint_tracker",
                    linked_id      = payload.get("id", ""),
                    linked_name    = name,
                    source_event   = "paint_updated",
                )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_paint_updated error: {e}")

    # ── Event handlers — Model Tracker ─────────────────────────────────────────

    def _on_model_added(self, payload: dict):
        try:
            if not self._auto_suggest_enabled():
                self._schedule_refresh()
                return
            name = payload.get("name") or payload.get("model_name", "")
            if name:
                self._create_timeline_event(
                    title          = f"Added to collection: {name}",
                    event_category = "Purchase",
                    linked_plugin  = "model_tracker",
                    linked_id      = payload.get("id", ""),
                    linked_name    = name,
                    source_event   = "model_added",
                )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_model_added error: {e}")

    def _on_model_updated(self, payload: dict):
        try:
            # Detect completion status changes
            status = payload.get("status", "")
            name   = payload.get("name") or payload.get("model_name", "")
            if status and status.lower() in ("completed", "done", "finished") and name:
                if self._auto_suggest_enabled():
                    self._create_timeline_event(
                        title          = f"Completed: {name}",
                        event_category = "Completed Project",
                        session_type   = "Painting Session",
                        linked_plugin  = "model_tracker",
                        linked_id      = payload.get("id", ""),
                        linked_name    = name,
                        source_event   = "model_updated",
                    )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_model_updated error: {e}")

    # ── Event handlers — Army Builder ──────────────────────────────────────────

    def _on_army_created(self, payload: dict):
        try:
            if not self._auto_suggest_enabled():
                self._schedule_refresh()
                return
            name = payload.get("name") or payload.get("army_name", "")
            if name:
                self._create_timeline_event(
                    title          = f"Created army: {name}",
                    event_category = "Campaign Event",
                    session_type   = "Army Prep",
                    linked_plugin  = "army_builder",
                    linked_id      = payload.get("id", ""),
                    linked_name    = name,
                    source_event   = "army_created",
                )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_army_created error: {e}")

    def _on_army_updated(self, payload: dict):
        try:
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_army_updated error: {e}")

    # ── Event handlers — Campaign Tracker ──────────────────────────────────────

    def _on_campaign_created(self, payload: dict):
        try:
            settings     = self.context.services.try_get("settings")
            auto_suggest = settings.get("calendar.auto_suggest", True) if settings else True
            if auto_suggest and self._service:
                campaign_name = payload.get("name") or payload.get("title", "Campaign")
                # Scheduled planning session
                self._service.add_event(
                    title          = f"Campaign Planning: {campaign_name}",
                    session_type   = "Campaign Writing",
                    event_category = "Campaign Event",
                    auto_generated = True,
                    source_event   = "campaign_created",
                    linked_plugin  = "campaign_tracker",
                    linked_id      = str(payload.get("id", "")),
                    linked_name    = campaign_name,
                )
                # Timeline record of the creation itself
                self._create_timeline_event(
                    title          = f"Started campaign: {campaign_name}",
                    event_category = "Campaign Event",
                    linked_plugin  = "campaign_tracker",
                    linked_id      = payload.get("id", ""),
                    linked_name    = campaign_name,
                    source_event   = "campaign_created",
                )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_campaign_created error: {e}")

    def _on_campaign_updated(self, payload: dict):
        try:
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_campaign_updated error: {e}")

    def _on_battle_logged(self, payload: dict):
        try:
            if not self._auto_suggest_enabled():
                self._schedule_refresh()
                return
            campaign_name = (
                payload.get("campaign_name")
                or payload.get("campaign_id", "")
            )
            battle_name = payload.get("name") or payload.get("title", "")
            title = f"Battle: {battle_name}" if battle_name else "Battle logged"
            if campaign_name:
                title += f" ({campaign_name})"
            self._create_timeline_event(
                title          = title,
                event_category = "Campaign Event",
                session_type   = "Game Night",
                linked_plugin  = "campaign_tracker",
                linked_id      = payload.get("id", ""),
                linked_name    = str(campaign_name),
                source_event   = "battle_logged",
            )
            self.context.event_bus.emit("calendar_activity", {
                "description": title,
                "plugin_id":   "calendar",
            })
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_battle_logged error: {e}")

    # ── Event handlers — Tool Tracker ──────────────────────────────────────────

    def _on_tool_added(self, payload: dict):
        try:
            if not self._auto_suggest_enabled():
                return
            name = payload.get("name") or payload.get("tool_name", "")
            if name:
                self._create_timeline_event(
                    title          = f"Added tool: {name}",
                    event_category = "Purchase",
                    linked_plugin  = "tool_tracker",
                    linked_id      = payload.get("id", ""),
                    linked_name    = name,
                    source_event   = "tool_added",
                )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_tool_added error: {e}")

    # ── Event handlers — Materials Tracker ────────────────────────────────────

    def _on_material_added(self, payload: dict):
        try:
            if not self._auto_suggest_enabled():
                return
            name = payload.get("name") or payload.get("material_name", "")
            if name:
                self._create_timeline_event(
                    title          = f"Added material: {name}",
                    event_category = "Purchase",
                    linked_plugin  = "materials_tracker",
                    linked_id      = payload.get("id", ""),
                    linked_name    = name,
                    source_event   = "material_added",
                )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_material_added error: {e}")

    # ── Event handlers — Project Tracker ──────────────────────────────────────

    def _on_project_session_log(self, payload: dict):
        try:
            if not self._auto_suggest_enabled():
                self._schedule_refresh()
                return

            project_id       = payload.get("project_id")
            duration_minutes = int(payload.get("duration_minutes") or 0)
            notes            = payload.get("notes", "")
            started_at       = payload.get("started_at", "") or ""

            # Derive the event date from started_at (ISO string) or fall back to today
            event_date = started_at[:10] if len(started_at) >= 10 else ""

            project_name = ""
            project_svc  = self.context.services.try_get("project_service")
            if project_svc and project_id:
                try:
                    project = project_svc.get_project(project_id)
                    if project:
                        project_name = project.name
                except Exception:
                    pass

            title = f"Hobby Session: {project_name}" if project_name else "Hobby Session"

            if not self._service:
                return

            self._service.add_event(
                title            = title,
                session_type     = "Hobby Session",
                event_category   = "Hobby Session",
                event_date       = event_date,
                duration_minutes = duration_minutes,
                notes            = notes,
                linked_plugin    = "project_tracker",
                linked_id        = str(project_id) if project_id else "",
                linked_name      = project_name,
                auto_generated   = True,
                source_event     = "project_session_log",
            )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_project_session_log error: {e}")

    def _on_project_session_end(self, payload: dict):
        try:
            if not self._auto_suggest_enabled():
                self._schedule_refresh()
                return

            project_id = payload.get("project_id")
            notes      = payload.get("notes", "")

            project_name     = ""
            duration_minutes = 0

            project_svc = self.context.services.try_get("project_service")
            if project_svc and project_id:
                try:
                    project = project_svc.get_project(project_id)
                    if project:
                        project_name = project.name
                except Exception:
                    pass

                # Grab the most-recently completed session to get the real duration
                try:
                    sessions  = project_svc.get_sessions(project_id)
                    completed = [
                        s for s in sessions
                        if not getattr(s, "is_active", False)
                        and getattr(s, "duration_minutes", 0) > 0
                    ]
                    if completed:
                        # Sessions are returned newest-first; take the first one
                        duration_minutes = completed[0].duration_minutes
                except Exception:
                    pass

            title = f"Hobby Session: {project_name}" if project_name else "Hobby Session"

            if not self._service:
                return

            self._service.add_event(
                title            = title,
                session_type     = "Hobby Session",
                event_category   = "Hobby Session",
                duration_minutes = duration_minutes,
                notes            = notes,
                linked_plugin    = "project_tracker",
                linked_id        = str(project_id) if project_id else "",
                linked_name      = project_name,
                auto_generated   = True,
                source_event     = "project_session_end",
            )
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_project_session_end error: {e}")

    # ── Event handlers — settings ──────────────────────────────────────────────

    def _on_settings_changed(self, payload: dict):
        try:
            self._schedule_refresh()
        except Exception as e:
            print(f"[CALENDAR] _on_settings_changed error: {e}")

    # ── Refresh helpers ────────────────────────────────────────────────────────

    def _initial_refresh(self):
        if self._ui:
            try:
                self._ui.refresh()
            except Exception as e:
                print(f"[CALENDAR] _initial_refresh error: {e}")

    def _schedule_refresh(self, delay_ms: int = 300):
        """Debounced refresh — cancels any pending timer and restarts it."""
        if self._refresh_timer is None:
            self._refresh_timer = QTimer()
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._initial_refresh)

        self._refresh_timer.stop()
        self._refresh_timer.start(delay_ms)
