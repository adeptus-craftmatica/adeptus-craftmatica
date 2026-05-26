"""
Chroma Codex 2.0 — Plugin entry point.

Standalone plugin; does not depend on the v1 paint_scheme plugin being loaded.
Imports the colour-theory engine from plugins.paint_scheme.chroma_codex (pure
Python, no Qt) and builds its own UI on top.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from PySide6.QtCore import QTimer


class Plugin(PluginBase):
    display_name = "Chroma Codex 2.0"
    plugin_id    = "chroma_codex_v2"
    name         = "Chroma Codex 2.0"
    version      = "2.0.0"
    description  = (
        "Intelligent paint planning engine — generate palette recommendations "
        "from any primary colour using colour theory."
    )

    def __init__(self, context):
        super().__init__(context)
        self._ui_widget = None
        self._subs: list = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def activate(self):
        from .ui import ChromaCodexV2UI
        self._ui_widget = ChromaCodexV2UI(self.context)
        self._ui_widget.setProperty("plugin_id", "chroma_codex_v2")

        bus = self.context.event_bus
        for event in ("paint_added", "paint_updated", "paint_removed"):
            handler = self._make_refresh_handler(event)
            bus.subscribe(event, handler)
            self._subs.append((event, handler))

        log.info("[CHROMA CODEX V2] Activated")

    def deactivate(self):
        bus = self.context.event_bus
        for event, handler in self._subs:
            try:
                bus.unsubscribe(event, handler)
            except Exception:
                pass
        self._subs.clear()
        self._ui_widget = None

    def get_ui(self):
        return self._ui_widget

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_refresh_handler(self, event_name: str):
        def _handler(payload=None):
            if self._ui_widget:
                self._ui_widget.on_paints_changed()
        return _handler
