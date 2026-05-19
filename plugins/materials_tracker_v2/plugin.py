"""
Materials Tracker 2.0 — Plugin entry point.

Shares material_service with v1 (creates it if v1 isn't loaded) and registers
under the canonical "materials_tracker" dashboard key so only one provider
is ever visible to the dashboard at a time.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from PySide6.QtCore import QTimer


class Plugin(PluginBase):
    display_name = "Materials Tracker 2.0"
    plugin_id    = "materials_tracker_v2"
    name         = "Materials Tracker 2.0"
    version      = "1.0.0"
    description  = (
        "Redesigned materials and basing supplies manager with card grid, "
        "stock tracking, and smart restocking recommendations."
    )

    def __init__(self, context):
        super().__init__(context)
        self._service              = None
        self._ui_widget            = None
        self._subs: list           = []
        self._dashboard_provider_id = "materials_tracker"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def activate(self):
        # Reuse existing material_service if registered, otherwise create one
        db = self.context.services.get("db")
        if self.context.services.has("material_service"):
            self._service = self.context.services.get("material_service")
        else:
            from plugins.materials_tracker.repository import MaterialRepository
            from plugins.materials_tracker.service   import MaterialService
            repo           = MaterialRepository(db)
            self._service  = MaterialService(repo)
            self.context.services.register("material_service", self._service)

        # Build UI
        from .ui import MaterialsTrackerV2UI
        self._ui_widget = MaterialsTrackerV2UI(self._service, self.context)
        self._ui_widget.setProperty("plugin_id", "materials_tracker_v2")

        # Dashboard — register under canonical key immediately and again at
        # 360 ms to win any race with the dashboard's 200 ms deferred_setup.
        self._register_dashboard_provider()
        QTimer.singleShot(360, self._register_dashboard_provider)

        # Subscribe to material events to keep the UI fresh.
        # "materials_filter_changed" is emitted by the Forge (community import) and v1
        bus = self.context.event_bus
        for event in (
            "material_added", "material_updated", "material_removed",
            "materials_filter_changed",
        ):
            handler = self._make_refresh_handler()
            bus.subscribe(event, handler)
            self._subs.append((event, handler))

        # Dashboard navigation handler
        def _on_nav(payload=None):
            if payload and payload.get("plugin_id") in (
                "materials_tracker_v2", "materials_tracker"
            ):
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

        # Dashboard cleanup — only act if we currently own the provider slot.
        # If v1 is still loaded, restore its provider so the dashboard keeps working.
        try:
            reg = self.context.services.try_get("dashboard_registry")
            if reg:
                current = reg.get_provider(self._dashboard_provider_id)
                if getattr(current, "_owner", None) == "materials_tracker_v2":
                    svc      = self.context.services.try_get("material_service")
                    restored = False
                    if svc:
                        try:
                            import importlib
                            mod    = importlib.import_module(
                                "plugins.dashboard.providers.materials_provider"
                            )
                            legacy = getattr(mod, "MaterialsDashboardProvider")(svc)
                            legacy._owner = "materials_tracker"
                            reg.register_provider(self._dashboard_provider_id, legacy)
                            restored = True
                        except Exception:
                            pass
                    if not restored:
                        reg.unregister_provider(self._dashboard_provider_id)
        except Exception:
            pass

        self._ui_widget = None
        self._service   = None

    def get_ui(self):
        return self._ui_widget

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _register_dashboard_provider(self):
        try:
            from .providers.dashboard_provider import MaterialsDashboardProviderV2
            reg = self.context.services.try_get("dashboard_registry")
            if reg and self._service:
                provider        = MaterialsDashboardProviderV2(self._service)
                provider._owner = "materials_tracker_v2"
                reg.register_provider(self._dashboard_provider_id, provider)
                try:
                    self.context.event_bus.emit("dashboard_provider_updated", {})
                except Exception:
                    pass
        except Exception as e:
            log.error(f"[MATERIALS V2] Dashboard provider failed: {e}")

    def _make_refresh_handler(self):
        def _handler(payload=None):
            if self._ui_widget:
                self._ui_widget.refresh()
        return _handler
