"""
Campaign Tracker Plugin

Lifecycle controller: resolves services, registers events, owns the UI.
"""
from __future__ import annotations

from core.plugin_base import PluginBase
from .models import ValidationError


class Plugin(PluginBase):
    plugin_id   = "campaign_tracker"
    name        = "Campaign Tracker"
    version     = "0.1.0"
    description = "Track campaigns, sessions, characters, and battles for any tabletop game or RPG"

    def __init__(self, context):
        super().__init__(context)
        self._service   = None
        self._ui        = None
        self._subscriptions: list[tuple[str, object]] = []

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def activate(self):
        self._resolve_services()
        self._init_ui()
        self._register_events()
        print(f"[CAMPAIGN_TRACKER] Plugin activated")

    def deactivate(self):
        self._unsubscribe_all()
        self._ui      = None
        self._service = None

    def get_ui(self):
        return self._ui

    # ── Internals ─────────────────────────────────────────────────────────────

    def _resolve_services(self):
        self._service = self.context.services.get("campaign_service")
        if not self._service:
            raise RuntimeError("[CAMPAIGN_TRACKER] campaign_service not found")

    def _init_ui(self):
        from .ui import CampaignTrackerUI
        self._ui = CampaignTrackerUI(self.context)

    def _register_events(self):
        self._subscribe("model_removed", self._on_model_removed)

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

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_model_removed(self, payload: dict):
        model_id = payload.get("id")
        if model_id and self._service:
            self._service.on_model_removed(model_id)
