"""
Paint Scheme Plugin

Lifecycle management, event routing, and service coordination for
the Paint Scheme plugin.
"""

from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from .ui import SchemeUI


class Plugin(PluginBase):
    plugin_id = "paint_scheme"
    name = "Paint Schemes"
    version = "0.1.0"
    description = "Build and manage paint recipes and colour schemes for your models"

    def __init__(self, context):
        super().__init__(context)
        self._service = None
        self._ui: SchemeUI | None = None
        self._subscriptions: list[tuple[str, object]] = []

    # ============================================================
    # LIFECYCLE
    # ============================================================

    def activate(self):
        log.debug(f"[PLUGIN] {self.display_name} activating...")

        self._resolve_services()
        self._init_ui()
        self._register_events()

        log.debug(f"[PLUGIN] {self.display_name} activated")

    def deactivate(self):
        log.debug(f"[PLUGIN] {self.display_name} deactivating...")

        self._unsubscribe_all()
        self._ui = None
        self._service = None

        log.debug(f"[PLUGIN] {self.display_name} deactivated")

    def get_ui(self):
        return self._ui

    # ============================================================
    # SETUP
    # ============================================================

    def _resolve_services(self):
        self._service = self.context.services.get("scheme_service")
        if not self._service:
            log.warning("[PLUGIN WARNING] scheme_service not available yet — UI will operate in degraded mode")

    def _init_ui(self):
        self._ui = SchemeUI(self.context)

    # ============================================================
    # EVENT SUBSCRIPTION
    # ============================================================

    def _register_events(self):
        # Scheme CRUD
        self._subscribe("scheme_add_requested",    self._on_scheme_add_requested)
        self._subscribe("scheme_update_requested", self._on_scheme_update_requested)
        self._subscribe("scheme_delete_requested", self._on_scheme_delete_requested)

        # Step CRUD
        self._subscribe("scheme_step_add_requested",    self._on_step_add_requested)
        self._subscribe("scheme_step_update_requested", self._on_step_update_requested)
        self._subscribe("scheme_step_delete_requested", self._on_step_delete_requested)
        self._subscribe("scheme_steps_reordered",       self._on_steps_reordered)

        # Model links
        self._subscribe("scheme_model_link_changed", self._on_model_link_changed)

        # Cross-plugin: react to paint / model removals
        self._subscribe("paint_removed",  self._on_paint_removed)
        self._subscribe("model_removed",  self._on_model_removed)

    def _subscribe(self, event_name: str, handler):
        self.context.event_bus.subscribe(event_name, handler)
        self._subscriptions.append((event_name, handler))

    def _unsubscribe_all(self):
        for event_name, handler in self._subscriptions:
            try:
                self.context.event_bus.unsubscribe(event_name, handler)
            except Exception:
                pass
        self._subscriptions.clear()

    # ============================================================
    # SCHEME EVENT HANDLERS
    # ============================================================

    def _on_scheme_add_requested(self, payload: dict):
        try:
            svc = self._get_service()
            scheme = svc.add_scheme(
                name=payload.get("name", ""),
                game_system=payload.get("game_system", ""),
                faction=payload.get("faction", ""),
                description=payload.get("description", ""),
            )
            self.context.event_bus.emit("scheme_added", {"scheme": scheme})
            self._refresh_ui()
        except Exception as e:
            log.error(f"[PLUGIN ERROR] scheme_add_requested failed: {e}")
            self._ui_error(str(e))

    def _on_scheme_update_requested(self, payload: dict):
        try:
            svc = self._get_service()
            scheme_id = payload.get("id") or payload.get("scheme_id")
            kwargs = {k: v for k, v in payload.items() if k not in ("id", "scheme_id")}
            scheme = svc.update_scheme(scheme_id, **kwargs)
            self.context.event_bus.emit("scheme_updated", {"scheme": scheme})
            self._refresh_ui()
        except Exception as e:
            log.error(f"[PLUGIN ERROR] scheme_update_requested failed: {e}")
            self._ui_error(str(e))

    def _on_scheme_delete_requested(self, payload: dict):
        try:
            svc = self._get_service()
            scheme_id = payload.get("id") or payload.get("scheme_id")
            success = svc.delete_scheme(scheme_id)
            if success:
                self.context.event_bus.emit("scheme_deleted", {"scheme_id": scheme_id})
                self._refresh_ui()
        except Exception as e:
            log.error(f"[PLUGIN ERROR] scheme_delete_requested failed: {e}")
            self._ui_error(str(e))

    # ============================================================
    # STEP EVENT HANDLERS
    # ============================================================

    def _on_step_add_requested(self, payload: dict):
        try:
            svc = self._get_service()
            step = svc.add_step(
                scheme_id=payload["scheme_id"],
                technique=payload.get("technique", "Basecoat"),
                paint_id=payload.get("paint_id"),
                paint_name=payload.get("paint_name", ""),
                notes=payload.get("notes", ""),
            )
            self._refresh_scheme_detail(step.scheme_id)
        except Exception as e:
            log.error(f"[PLUGIN ERROR] scheme_step_add_requested failed: {e}")
            self._ui_error(str(e))

    def _on_step_update_requested(self, payload: dict):
        try:
            svc = self._get_service()
            step_id = payload.get("id") or payload.get("step_id")
            kwargs = {k: v for k, v in payload.items() if k not in ("id", "step_id")}
            step = svc.update_step(step_id, **kwargs)
            self._refresh_scheme_detail(step.scheme_id)
        except Exception as e:
            log.error(f"[PLUGIN ERROR] scheme_step_update_requested failed: {e}")
            self._ui_error(str(e))

    def _on_step_delete_requested(self, payload: dict):
        try:
            svc = self._get_service()
            step_id = payload.get("id") or payload.get("step_id")
            # We need the scheme_id before deleting
            step = svc.repo.get_step_by_id(step_id) if hasattr(svc, "repo") else None
            scheme_id = step.scheme_id if step else payload.get("scheme_id")
            svc.delete_step(step_id)
            if scheme_id:
                self._refresh_scheme_detail(scheme_id)
        except Exception as e:
            log.error(f"[PLUGIN ERROR] scheme_step_delete_requested failed: {e}")
            self._ui_error(str(e))

    def _on_steps_reordered(self, payload: dict):
        try:
            svc = self._get_service()
            scheme_id = payload["scheme_id"]
            ordered_ids = payload["ordered_step_ids"]
            svc.reorder_steps(scheme_id, ordered_ids)
            self._refresh_scheme_detail(scheme_id)
        except Exception as e:
            log.error(f"[PLUGIN ERROR] scheme_steps_reordered failed: {e}")
            self._ui_error(str(e))

    # ============================================================
    # MODEL LINK EVENT HANDLERS
    # ============================================================

    def _on_model_link_changed(self, payload: dict):
        try:
            svc = self._get_service()
            scheme_id = payload["scheme_id"]
            model_id = payload["model_id"]
            action = payload.get("action", "link")

            if action == "link":
                svc.link_model(scheme_id, model_id)
            else:
                svc.unlink_model(scheme_id, model_id)

            self._refresh_scheme_detail(scheme_id)
        except Exception as e:
            log.error(f"[PLUGIN ERROR] scheme_model_link_changed failed: {e}")
            self._ui_error(str(e))

    # ============================================================
    # CROSS-PLUGIN EVENT HANDLERS
    # ============================================================

    def _on_paint_removed(self, payload: dict):
        """When a paint is deleted from paint_tracker, null out any step references."""
        try:
            paint_id = payload.get("id")
            if paint_id is None:
                return
            svc = self._get_service()
            if hasattr(svc, "repo"):
                svc.repo.null_out_paint_id(paint_id)
                log.debug(f"[PLUGIN] Nulled paint_id={paint_id} from scheme steps")
                # Refresh detail pane if currently open
                if self._ui:
                    self._ui.refresh_current_scheme()
        except Exception as e:
            log.error(f"[PLUGIN ERROR] paint_removed handler failed: {e}")

    def _on_model_removed(self, payload: dict):
        """When a model is deleted from model_tracker, remove all its scheme links."""
        try:
            model_id = payload.get("id")
            if model_id is None:
                return
            svc = self._get_service()
            if hasattr(svc, "repo"):
                svc.repo.remove_all_links_for_model(model_id)
                log.debug(f"[PLUGIN] Removed all scheme links for model_id={model_id}")
                if self._ui:
                    self._ui.refresh_current_scheme()
        except Exception as e:
            log.error(f"[PLUGIN ERROR] model_removed handler failed: {e}")

    # ============================================================
    # UI HELPERS
    # ============================================================

    def _get_service(self):
        if self._service is None:
            self._service = self.context.services.get("scheme_service")
        if self._service is None:
            raise RuntimeError("scheme_service is not available")
        return self._service

    def _refresh_ui(self):
        if self._ui:
            self._ui.refresh_scheme_list()

    def _refresh_scheme_detail(self, scheme_id: int):
        if self._ui:
            self._ui.refresh_scheme_detail(scheme_id)

    def _ui_error(self, message: str):
        if self._ui and hasattr(self._ui, "_show_error"):
            self._ui._show_error(message)
