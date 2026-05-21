"""
Model Command 2.0 — Plugin entry point.

Shares model_service with v1 (creates it if v1 isn't loaded) and registers
under the canonical "model_tracker" dashboard key so only one provider
is ever visible to the dashboard at a time.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from PySide6.QtCore import QTimer


class Plugin(PluginBase):
    display_name = "Model Command 2.0"
    plugin_id    = "model_tracker_v2"
    name         = "Model Command 2.0"
    version      = "2.0.0"
    description  = (
        "Professional miniature collection manager — Pipeline view, drag-drop, "
        "Wall of Shame, and squad tracking."
    )

    def __init__(self, context):
        super().__init__(context)
        self._service               = None
        self._meta_repo             = None
        self._ui_widget             = None
        self._subs: list            = []
        self._dashboard_provider_id = "model_tracker"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def activate(self):
        db = self.context.services.get("db")

        # Reuse existing model_service if registered, otherwise create one
        if self.context.services.has("model_service"):
            self._service = self.context.services.get("model_service")
        else:
            from plugins.model_tracker.repository import ModelRepository
            from plugins.model_tracker.service    import ModelService
            repo          = ModelRepository(db)
            self._service = ModelService(repo)
            self.context.services.register("model_service", self._service)

        # V2-only metadata repository
        from .meta_repository import MetaRepository
        self._meta_repo = MetaRepository(db)

        # Build UI
        from .ui import ModelTrackerV2UI
        self._ui_widget = ModelTrackerV2UI(self._service, self._meta_repo, self.context)
        self._ui_widget.setProperty("plugin_id", "model_tracker_v2")

        # Dashboard — register under canonical key immediately and again at
        # 380 ms to win any race with the dashboard's 200 ms deferred_setup.
        self._register_dashboard_provider()
        QTimer.singleShot(380, self._register_dashboard_provider)

        # Subscribe to model events to keep the UI fresh
        bus = self.context.event_bus
        for event in ("model_added", "model_updated", "model_removed"):
            handler = self._make_refresh_handler()
            bus.subscribe(event, handler)
            self._subs.append((event, handler))

        # Dashboard navigation handler
        def _on_nav(payload=None):
            if payload and payload.get("plugin_id") in ("model_tracker_v2", "model_tracker"):
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

        self._ui_widget  = None
        self._service    = None
        self._meta_repo  = None

    def get_ui(self):
        return self._ui_widget

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _register_dashboard_provider(self):
        try:
            from .providers.dashboard_provider import ModelTrackerDashboardProviderV2
            reg = self.context.services.try_get("dashboard_registry")
            if reg and self._service:
                provider        = ModelTrackerDashboardProviderV2(self._service)
                provider._owner = "model_tracker_v2"
                reg.register_provider(self._dashboard_provider_id, provider)
                try:
                    self.context.event_bus.emit("dashboard_provider_updated", {})
                except Exception:
                    pass
        except Exception as e:
            log.error(f"[MODEL TRACKER V2] Dashboard provider failed: {e}")

    def _cleanup_dashboard_provider(self):
        """Remove our provider. If v1 is still loaded, restore its provider."""
        try:
            reg = self.context.services.try_get("dashboard_registry")
            if reg:
                current = reg.get_provider(self._dashboard_provider_id)
                if getattr(current, "_owner", None) == "model_tracker_v2":
                    svc      = self.context.services.try_get("model_service")
                    restored = False
                    if svc:
                        try:
                            import importlib
                            mod    = importlib.import_module(
                                "plugins.dashboard.providers.models_provider"
                            )
                            legacy = getattr(mod, "ModelsDashboardProvider")(svc)
                            legacy._owner = "model_tracker"
                            reg.register_provider(self._dashboard_provider_id, legacy)
                            restored = True
                        except Exception:
                            pass
                    if not restored:
                        reg.unregister_provider(self._dashboard_provider_id)
        except Exception as e:
            log.warning(f"[MODEL TRACKER V2] Dashboard cleanup: {e}")

    def _make_refresh_handler(self):
        def _handler(payload=None):
            if self._ui_widget:
                self._ui_widget.refresh()
        return _handler
