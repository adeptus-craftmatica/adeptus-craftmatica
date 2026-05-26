"""
Paint Schemes 2.0 — Plugin entry point.

Shares scheme_service with v1 (creates it if v1 isn't loaded) and registers
under the canonical "paint_scheme" dashboard key so only one provider is ever
visible to the dashboard at a time.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from PySide6.QtCore import QTimer


class Plugin(PluginBase):
    display_name = "Paint Schemes 2.0"
    plugin_id    = "paint_scheme_v2"
    name         = "Paint Schemes 2.0"
    version      = "2.0.0"
    description  = (
        "Professional paint scheme manager — recipe builder, "
        "step-by-step guides, and model linking."
    )

    def __init__(self, context):
        super().__init__(context)
        self._service    = None
        self._ui_widget  = None
        self._subs: list = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def activate(self):
        db = self.context.services.get("db")

        # Reuse existing scheme_service if v1 already registered it
        if self.context.services.has("scheme_service"):
            self._service = self.context.services.get("scheme_service")
        else:
            from plugins.paint_scheme.repository import SchemeRepository
            from plugins.paint_scheme.service   import SchemeService
            repo          = SchemeRepository(db)
            self._service = SchemeService(repo)
            self.context.services.register("scheme_service", self._service)

        from .ui import SchemeV2UI
        self._ui_widget = SchemeV2UI(self._service, self.context)
        self._ui_widget.setProperty("plugin_id", "paint_scheme_v2")

        bus = self.context.event_bus
        for event in ("scheme_added", "scheme_updated", "scheme_deleted",
                      "paint_removed", "model_removed"):
            handler = self._make_refresh_handler(event)
            bus.subscribe(event, handler)
            self._subs.append((event, handler))

        log.info("[PAINT SCHEMES V2] Activated")

    def deactivate(self):
        bus = self.context.event_bus
        for event, handler in self._subs:
            try:
                bus.unsubscribe(event, handler)
            except Exception:
                pass
        self._subs.clear()
        self._ui_widget = None
        self._service   = None

    def get_ui(self):
        return self._ui_widget

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_refresh_handler(self, event_name: str):
        def _handler(payload=None):
            if self._ui_widget:
                if event_name in ("paint_removed", "model_removed"):
                    self._ui_widget.refresh_current_scheme()
                else:
                    self._ui_widget.refresh()
        return _handler
