"""
Tool Tracker 2.0 — Plugin entry point.

Shares tool_service with v1 (creates it if v1 isn't loaded) and registers
under the canonical "tool_tracker" dashboard key so only one provider
is ever visible to the dashboard at a time.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from PySide6.QtCore import QTimer


class Plugin(PluginBase):
    display_name = "Tool Tracker 2.0"
    plugin_id    = "tool_tracker_v2"
    name         = "Tool Tracker 2.0"
    version      = "1.0.0"
    description  = (
        "Professional toolkit manager — card grid, condition tracking, "
        "project linking and smart restocking recommendations."
    )

    def __init__(self, context):
        super().__init__(context)
        self._service               = None
        self._ui_widget             = None
        self._subs: list            = []
        self._dashboard_provider_id = "tool_tracker"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def activate(self):
        # Reuse existing tool_service if registered, otherwise create one
        db = self.context.services.get("db")
        if self.context.services.has("tool_service"):
            self._service = self.context.services.get("tool_service")
        else:
            from plugins.tool_tracker.repository import ToolRepository
            from plugins.tool_tracker.service   import ToolService
            repo          = ToolRepository(db)
            self._service = ToolService(repo)
            self.context.services.register("tool_service", self._service)

        # Build UI
        from .ui import ToolTrackerV2UI
        self._ui_widget = ToolTrackerV2UI(self._service, self.context)
        self._ui_widget.setProperty("plugin_id", "tool_tracker_v2")

        # Dashboard — register under canonical key immediately and again at
        # 380 ms to win any race with the dashboard's 200 ms deferred_setup.
        # FIXME: remove second registration once dashboard startup is ordered.
        self._register_dashboard_provider()
        QTimer.singleShot(380, self._register_dashboard_provider)

        # Subscribe to tool events to keep the UI fresh.
        bus = self.context.event_bus
        for event in ("tool_added", "tool_updated", "tool_removed"):
            handler = self._make_refresh_handler()
            bus.subscribe(event, handler)
            self._subs.append((event, handler))

        # Dashboard navigation handler
        def _on_nav(payload=None):
            if payload and payload.get("plugin_id") in (
                "tool_tracker_v2", "tool_tracker"
            ):
                if self._ui_widget:
                    self._ui_widget.refresh()
                    preset = payload.get("preset", "")
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

        self._cleanup_dashboard_provider()

        self._ui_widget = None
        self._service   = None

    def get_ui(self):
        return self._ui_widget

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _register_dashboard_provider(self):
        try:
            from .providers.dashboard_provider import ToolTrackerDashboardProviderV2
            reg = self.context.services.try_get("dashboard_registry")
            if reg and self._service:
                provider        = ToolTrackerDashboardProviderV2(self._service)
                provider._owner = "tool_tracker_v2"
                reg.register_provider(self._dashboard_provider_id, provider)
                try:
                    self.context.event_bus.emit("dashboard_provider_updated", {})
                except Exception:
                    pass
        except Exception as e:
            log.error(f"[TOOL TRACKER V2] Dashboard provider failed: {e}")

    def _cleanup_dashboard_provider(self):
        """Remove our provider. If v1 is still loaded, restore its provider."""
        try:
            reg = self.context.services.try_get("dashboard_registry")
            if reg:
                current = reg.get_provider(self._dashboard_provider_id)
                if getattr(current, "_owner", None) == "tool_tracker_v2":
                    svc      = self.context.services.try_get("tool_service")
                    restored = False
                    if svc:
                        try:
                            import importlib
                            mod    = importlib.import_module(
                                "plugins.dashboard.providers.tools_provider"
                            )
                            legacy = getattr(mod, "ToolsDashboardProvider")(svc)
                            legacy._owner = "tool_tracker"
                            reg.register_provider(self._dashboard_provider_id, legacy)
                            restored = True
                        except Exception:
                            pass
                    if not restored:
                        reg.unregister_provider(self._dashboard_provider_id)
        except Exception as e:
            log.warning(f"[TOOL TRACKER V2] Dashboard cleanup: {e}")

    def _make_refresh_handler(self):
        def _handler(payload=None):
            if self._ui_widget:
                self._ui_widget.refresh()
        return _handler
