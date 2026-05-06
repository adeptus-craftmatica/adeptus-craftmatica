from core.plugin_base import PluginBase
from PySide6.QtCore import QTimer


class Plugin(PluginBase):
    display_name = "Paint Tracker 2.0"
    plugin_id = "paint_tracker_v2"
    name = "Paint Tracker 2.0"
    version = "1.0.0"
    description = "Redesigned paint collection manager with card grid, usage logging, and smart restocking."

    def __init__(self, context):
        super().__init__(context)
        self._service = None
        self._ui_widget = None
        self._subs = []
        self._dashboard_provider_id = "paint_tracker"

    def activate(self):
        # Reuse existing paint_service if registered, otherwise create one
        from plugins.paint_tracker.service import PaintService
        from plugins.paint_tracker.repository import PaintRepository

        db = self.context.services.get("db")
        if self.context.services.has("paint_service"):
            self._service = self.context.services.get("paint_service")
        else:
            repo = PaintRepository(db)
            self._service = PaintService(repo)
            self.context.services.register("paint_service", self._service)

        # Build UI
        from .ui import PaintTrackerV2UI
        self._ui_widget = PaintTrackerV2UI(self._service, self.context)
        self._ui_widget.setProperty("plugin_id", "paint_tracker_v2")

        # Dashboard — register under the canonical "paint_tracker" key so the
        # dashboard gets one paint provider whether v1 or v2 is currently active.
        self._register_dashboard_provider()
        QTimer.singleShot(350, self._register_dashboard_provider)

        # Subscribe to paint events to refresh UI
        bus = self.context.event_bus
        for event in ("paint_added", "paint_updated", "paint_removed"):
            handler = self._make_refresh_handler()
            bus.subscribe(event, handler)
            self._subs.append((event, handler))

        # Dashboard navigate
        def _on_nav(payload=None):
            if payload and payload.get("plugin_id") == "paint_tracker_v2":
                if self._ui_widget:
                    preset = payload.get("preset")
                    if preset:
                        self._ui_widget.apply_preset(preset)

        bus.subscribe("dashboard_navigate", _on_nav)
        self._subs.append(("dashboard_navigate", _on_nav))

    def deactivate(self):
        bus = self.context.event_bus
        for event, handler in self._subs:
            try:
                bus.unsubscribe(event, handler)
            except Exception:
                pass
        self._subs.clear()

        reg = self.context.services.try_get("dashboard_registry")
        if reg:
            try:
                reg.unregister_provider(self._dashboard_provider_id)
            except Exception:
                pass
        self._ui_widget = None
        self._service = None

    def get_ui(self):
        return self._ui_widget

    def _register_dashboard_provider(self):
        try:
            from .providers.dashboard_provider import PaintDashboardProvider
            reg = self.context.services.try_get("dashboard_registry")
            if reg and self._service:
                reg.register_provider(
                    self._dashboard_provider_id,
                    PaintDashboardProvider(self._service),
                )
        except Exception as e:
            print(f"[PAINT V2] Dashboard provider failed: {e}")

    def _make_refresh_handler(self):
        def _handler(payload=None):
            if self._ui_widget:
                self._ui_widget.refresh()
        return _handler
