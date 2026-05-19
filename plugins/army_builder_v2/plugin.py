"""
Army Builder 2.0 — Plugin entry point.

Shares army_service with v1 (creates it if v1 isn't loaded) and registers
under the canonical "army_builder" dashboard key so only one provider is
ever visible to the dashboard at a time.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from PySide6.QtCore import QTimer


class Plugin(PluginBase):
    display_name = "Army Builder 2.0"
    plugin_id    = "army_builder_v2"
    name         = "Army Builder 2.0"
    version      = "1.0.0"
    description  = (
        "Redesigned army list manager with card grid, inline builder, "
        "and smart points tracking."
    )

    def __init__(self, context):
        super().__init__(context)
        self._service               = None
        self._ui_widget             = None
        self._subs: list            = []
        self._dashboard_provider_id = "army_builder"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def activate(self):
        db = self.context.services.get("db")

        # Reuse existing army_service if registered, otherwise create one
        if self.context.services.has("army_service"):
            self._service = self.context.services.get("army_service")
        else:
            from plugins.army_builder.repository import ArmyRepository
            from plugins.army_builder.service   import ArmyService
            repo          = ArmyRepository(db)
            self._service = ArmyService(repo)
            self.context.services.register("army_service", self._service)

        # Build UI
        from .ui import ArmyBuilderV2UI
        self._ui_widget = ArmyBuilderV2UI(self._service, self.context)
        self._ui_widget.setProperty("plugin_id", "army_builder_v2")

        # Dashboard — register under canonical key immediately and again at
        # 370 ms to beat the dashboard's 200 ms deferred_setup.
        self._register_dashboard_provider()
        QTimer.singleShot(370, self._register_dashboard_provider)

        # Subscribe to cross-plugin events
        bus = self.context.event_bus

        def _on_model_removed(payload=None):
            if payload and self._service:
                try:
                    self._service.on_model_removed(payload.get("id"))
                    if self._ui_widget:
                        self._ui_widget.on_model_removed(payload.get("id"))
                except Exception:
                    pass

        def _on_paint_removed(payload=None):
            if payload and self._service:
                try:
                    self._service.on_paint_removed(payload.get("id"))
                    if self._ui_widget:
                        self._ui_widget.refresh()
                except Exception:
                    pass

        bus.subscribe("model_removed", _on_model_removed)
        self._subs.append(("model_removed", _on_model_removed))
        bus.subscribe("paint_removed", _on_paint_removed)
        self._subs.append(("paint_removed", _on_paint_removed))

        # Dashboard navigation
        def _on_nav(payload=None):
            if payload and payload.get("plugin_id") in (
                "army_builder_v2", "army_builder"
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
        try:
            reg = self.context.services.try_get("dashboard_registry")
            if reg:
                current = reg.get_provider(self._dashboard_provider_id)
                if getattr(current, "_owner", None) == "army_builder_v2":
                    svc     = self.context.services.try_get("army_service")
                    restored = False
                    if svc:
                        try:
                            import importlib
                            mod    = importlib.import_module(
                                "plugins.dashboard.providers.army_provider"
                            )
                            legacy = getattr(mod, "ArmyDashboardProvider")(svc)
                            legacy._owner = "army_builder"
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
            from .providers.dashboard_provider import ArmyDashboardProviderV2
            reg = self.context.services.try_get("dashboard_registry")
            if reg and self._service:
                provider        = ArmyDashboardProviderV2(self._service)
                provider._owner = "army_builder_v2"
                reg.register_provider(self._dashboard_provider_id, provider)
                try:
                    self.context.event_bus.emit("dashboard_provider_updated", {})
                except Exception:
                    pass
        except Exception as e:
            log.error(f"[ARMY V2] Dashboard provider failed: {e}")
