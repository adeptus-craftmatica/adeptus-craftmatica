"""
Campaign Tracker v2 — Plugin entry point.

Shares campaign_service with v1 if already loaded; otherwise creates its own.
Registers under the canonical "campaign_tracker" dashboard key using the same
ownership pattern as army_builder_v2.
"""
from __future__ import annotations

from core.plugin_base import PluginBase
from PySide6.QtCore import QTimer


class Plugin(PluginBase):
    display_name = "Campaign Command 2.0"
    plugin_id    = "campaign_tracker_v2"
    name         = "Campaign Command 2.0"
    version      = "2.0.0"
    description  = (
        "Professional command centre for tabletop RPG and wargame campaigns."
    )

    def __init__(self, context):
        super().__init__(context)
        self._service    = None
        self._ui_widget  = None
        self._subs: list = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def activate(self):
        db = self.context.services.get("db")

        # ── V1 campaign service ────────────────────────────────────────────
        if self.context.services.has("campaign_service"):
            v1_svc = self.context.services.get("campaign_service")
        else:
            from plugins.campaign_tracker.repository import CampaignRepository
            from plugins.campaign_tracker.service   import CampaignService
            repo   = CampaignRepository(db)
            v1_svc = CampaignService(repo)
            self.context.services.register("campaign_service", v1_svc)

        # ── V2-only repo ───────────────────────────────────────────────────
        from .repository         import CampaignV2Repository
        from .gallery_repository import CampaignGalleryRepository
        from .asset_repository   import CampaignAssetRepository
        from .service            import CampaignV2Service
        v2_repo      = CampaignV2Repository(db)
        gallery_repo = CampaignGalleryRepository(db)
        asset_repo   = CampaignAssetRepository(db)
        self._service = CampaignV2Service(v1_svc, v2_repo, gallery_repo, asset_repo)

        # ── Build UI ───────────────────────────────────────────────────────
        from .ui import CampaignV2UI
        self._ui_widget = CampaignV2UI(self._service, self.context)
        self._ui_widget.setProperty("plugin_id", "campaign_tracker_v2")

        # ── Dashboard provider ─────────────────────────────────────────────
        self._register_dashboard_provider()
        QTimer.singleShot(380, self._register_dashboard_provider)

        # ── Event subscriptions ────────────────────────────────────────────
        bus = self.context.event_bus

        def _nav(payload=None):
            target = (payload or {}).get("plugin_id", "")
            if target in ("campaign_tracker_v2", "campaign_tracker") and self._ui_widget:
                self._ui_widget.refresh()

        bus.subscribe("dashboard_navigate", _nav)
        self._subs.append(("dashboard_navigate", _nav))

    def deactivate(self):
        bus = self.context.event_bus
        for event, cb in self._subs:
            try:
                bus.unsubscribe(event, cb)
            except Exception:
                pass
        self._subs.clear()
        self._cleanup_dashboard_provider()

    def get_ui(self):
        return self._ui_widget

    # ── Dashboard helpers ──────────────────────────────────────────────────

    def _register_dashboard_provider(self):
        try:
            from core.contracts.dashboard_registry import get_registry
            from .providers.dashboard_provider import CampaignDashboardProviderV2
            reg      = get_registry()
            provider = CampaignDashboardProviderV2(self._service)
            provider._owner = "campaign_tracker_v2"
            reg.register_provider("campaign_tracker", provider)
            try:
                self.context.event_bus.publish("dashboard_provider_updated", {})
            except Exception:
                pass
        except Exception as e:
            print(f"[CAMPAIGN V2] dashboard register: {e}")

    def _cleanup_dashboard_provider(self):
        try:
            from core.contracts.dashboard_registry import get_registry
            reg     = get_registry()
            current = reg.get_provider("campaign_tracker")
            if getattr(current, "_owner", None) == "campaign_tracker_v2":
                reg.unregister_provider("campaign_tracker")
        except Exception:
            pass
