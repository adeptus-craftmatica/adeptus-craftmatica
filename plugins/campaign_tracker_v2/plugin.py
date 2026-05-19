"""
Campaign Tracker v2 — Plugin entry point.

Shares campaign_service with v1 if already loaded; otherwise creates its own.
Registers under the canonical "campaign_tracker" dashboard key using the same
ownership pattern as army_builder_v2.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

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
        from .repository                import CampaignV2Repository
        from .gallery_repository        import CampaignGalleryRepository
        from .asset_repository          import CampaignAssetRepository
        from .quest_repository          import CampaignQuestRepository
        from .custom_monster_repository import CustomMonsterRepository
        from .service                   import CampaignV2Service
        v2_repo             = CampaignV2Repository(db)
        gallery_repo        = CampaignGalleryRepository(db)
        asset_repo          = CampaignAssetRepository(db)
        quest_repo          = CampaignQuestRepository(db)
        custom_monster_repo = CustomMonsterRepository(db)
        self._service = CampaignV2Service(
            v1_svc, v2_repo, gallery_repo, asset_repo, quest_repo,
            custom_monster_repo,
        )

        # ── Build UI ───────────────────────────────────────────────────────
        from .ui import CampaignV2UI
        self._ui_widget = CampaignV2UI(self._service, self.context)
        self._ui_widget.setProperty("plugin_id", "campaign_tracker_v2")

        # ── Dashboard provider ─────────────────────────────────────────────
        self._register_dashboard_provider()
        # FIXME: dashboard_registry may not exist yet when this plugin activates
        # because plugin load order is not guaranteed beyond core plugins.
        # Re-register once the event loop has processed all activate() calls.
        # Long-term fix: emit a "dashboard_registry_ready" event from the
        # dashboard plugin and subscribe to it here instead.
        QTimer.singleShot(380, self._register_dashboard_provider)

        # ── Event subscriptions ────────────────────────────────────────────
        bus = self.context.event_bus

        def _nav(payload=None):
            p      = payload or {}
            target = p.get("plugin_id", "")
            if target not in ("campaign_tracker_v2", "campaign_tracker"):
                return
            if not self._ui_widget:
                return
            campaign_id = p.get("project_id")
            log.debug(f"[CAMPAIGN V2] _nav: target={target!r} project_id={campaign_id!r}")
            if campaign_id is not None:
                try:
                    self._ui_widget._open_campaign(int(campaign_id))
                except Exception as e:
                    log.error(f"[CAMPAIGN V2] _open_campaign failed: {e}")
            else:
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
            registry = self.context.services.try_get("dashboard_registry")
            if not registry:
                return
            from .providers.dashboard_provider import CampaignDashboardProviderV2
            provider = CampaignDashboardProviderV2(self._service)
            provider._owner = "campaign_tracker_v2"
            registry.register_provider("campaign_tracker", provider)
            self.context.event_bus.emit("dashboard_provider_updated", {})
        except Exception as e:
            log.error(f"[CAMPAIGN V2] dashboard register: {e}")

    def _cleanup_dashboard_provider(self):
        try:
            registry = self.context.services.try_get("dashboard_registry")
            if not registry:
                return
            current = registry.get_provider("campaign_tracker")
            if getattr(current, "_owner", None) == "campaign_tracker_v2":
                registry.unregister_provider("campaign_tracker")
        except Exception:
            pass
