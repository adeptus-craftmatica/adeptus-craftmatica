"""
Model Tracker Plugin

Lifecycle controller — wires the service, UI, settings, and events together.

Cross-plugin integration:
  - Subscribes to "paint_removed" (from paint_tracker) to clean up links.
  - Registers "model_service" in ServiceRegistry so future plugins
    (army builder, encounter builder, etc.) can call it directly.
  - Emits "model_added", "model_removed", "model_updated",
    "model_status_changed" for other plugins to react to.
"""
from __future__ import annotations

from core.plugin_base import PluginBase
from .ui import ModelUI
from .models import ValidationError, ModelFilter
from .settings_page import ModelSettingsPage


class Plugin(PluginBase):

    plugin_id = "model_tracker"
    name = "Model Tracker"
    version = "0.1.0"
    description = "Track Warhammer, Gundam, D&D, and all your hobby models in one place"

    def __init__(self, context):
        super().__init__(context)
        self._service = None
        self._settings = None
        self._ui: ModelUI | None = None
        self._subscriptions: list[tuple[str, callable]] = []

    # ============================================================
    # LIFECYCLE
    # ============================================================

    def activate(self):
        print(f"[PLUGIN] {self.display_name} activating...")

        self._resolve_services()
        self._register_settings()
        self._init_ui()
        self._apply_settings()
        self._register_events()
        self._initial_load()

        print(f"[PLUGIN] {self.display_name} activated")

    def deactivate(self):
        print(f"[PLUGIN] {self.display_name} deactivating...")
        self._unsubscribe_all()
        self._ui = None
        self._service = None
        self._settings = None
        print(f"[PLUGIN] {self.display_name} deactivated")

    def get_ui(self):
        return self._ui

    # ============================================================
    # SETUP
    # ============================================================

    def _resolve_services(self):
        self._service = self.context.services.get("model_service")
        self._settings = self.context.services.get("settings")

        if not self._service:
            raise RuntimeError("ModelService not found — ensure model_tracker registered correctly")
        if not self._settings:
            raise RuntimeError("SettingsService not found")

    def _register_settings(self):
        registry = self.context.services.try_get("settings_registry")
        if registry:
            registry.register_page(
                self.display_name,
                lambda ctx: ModelSettingsPage(ctx),
            )

    def _init_ui(self):
        self._ui = ModelUI(self.context)

    def _apply_settings(self):
        if not self._ui:
            return
        try:
            default_system = self._settings.get("model_tracker.default_game_system", "")
            default_status = self._settings.get("model_tracker.default_status", "Unassembled")
            if default_system:
                self._ui.game_system_input.setCurrentText(default_system)
            if default_status:
                self._ui.status_combo.setCurrentText(default_status)
        except Exception as e:
            print(f"[PLUGIN WARNING] {self.display_name}: Failed to apply settings: {e}")

    def _initial_load(self):
        try:
            self.context.event_bus.emit("models_filter_changed", {
                "filter": ModelFilter()
            })
        except Exception as e:
            print(f"[PLUGIN WARNING] {self.display_name}: Initial load failed: {e}")

    # ============================================================
    # EVENT SUBSCRIPTIONS
    # ============================================================

    def _register_events(self):
        # Own CRUD events (emitted by UI)
        self._subscribe("model_add_requested", self._on_add)
        self._subscribe("model_update_requested", self._on_update)
        self._subscribe("model_remove_requested", self._on_remove)
        self._subscribe("model_edit_requested", self._on_edit_requested)
        self._subscribe("models_filter_changed", self._on_filter_changed)

        # model_added fires both from manual adds (via _on_add) and from the
        # library import dialog (which calls svc.add_model() directly).
        # Subscribing here ensures the list refreshes in both cases.
        self._subscribe("model_added", self._on_model_added)

        # Cross-plugin: paint_tracker tells us when a paint is deleted
        self._subscribe("paint_removed", self._on_paint_removed)

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
    # EVENT HANDLERS
    # ============================================================

    def _on_add(self, payload: dict):
        try:
            model = self._service.add_model(
                name=payload.get("name", ""),
                game_system=payload.get("game_system", ""),
                faction=payload.get("faction", ""),
                model_type=payload.get("model_type", ""),
                status=payload.get("status", "Unassembled"),
                scale=payload.get("scale", ""),
                quantity=payload.get("quantity", 1),
                notes=payload.get("notes"),
                linked_paint_ids=payload.get("linked_paint_ids", []),
                image_path=payload.get("image_path"),
            )

            self._persist_defaults(model.game_system, model.status)

            if self._ui:
                self._ui._show_success(f"Added: {model.name}")
                self._ui.clear_form()

            # Broadcast so other plugins know.
            # _refresh() is triggered by the model_added subscription below —
            # no need to call it here directly.
            self.context.event_bus.emit("model_added", model.to_dict())

        except ValidationError as e:
            if self._ui:
                self._ui._show_error(str(e))
        except Exception as e:
            print(f"[PLUGIN ERROR] {self.display_name} add failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_model_added(self, _payload: dict):
        """Refresh the model list whenever any model is added (manual or bulk import)."""
        self._refresh()

    def _on_update(self, payload: dict):
        try:
            model = self._service.update_model(
                model_id=payload.get("id"),
                name=payload.get("name", ""),
                game_system=payload.get("game_system", ""),
                faction=payload.get("faction", ""),
                model_type=payload.get("model_type", ""),
                status=payload.get("status", "Unassembled"),
                scale=payload.get("scale", ""),
                quantity=payload.get("quantity", 1),
                notes=payload.get("notes"),
                linked_paint_ids=payload.get("linked_paint_ids", []),
                image_path=payload.get("image_path"),
            )

            if self._ui:
                self._ui._show_success(f"Updated: {model.name}")
                self._ui.clear_form()

            self.context.event_bus.emit("model_updated", model.to_dict())
            self._refresh()

        except (ValidationError, ValueError) as e:
            if self._ui:
                self._ui._show_error(str(e))
        except Exception as e:
            print(f"[PLUGIN ERROR] {self.display_name} update failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_remove(self, payload: dict):
        try:
            success = self._service.remove_model(payload.get("id"))
            if self._ui:
                if success:
                    self._ui._show_success("Model removed")
                    self._ui.clear_form()
                else:
                    self._ui._show_error("Model not found")

            if success:
                self.context.event_bus.emit("model_removed", {"id": payload.get("id")})
            self._refresh()

        except Exception as e:
            print(f"[PLUGIN ERROR] {self.display_name} remove failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_edit_requested(self, payload: dict):
        """UI asked for the full model data to populate the form."""
        try:
            model = self._service.get_model(payload.get("id"))
            if model and self._ui:
                self._ui.populate_form(model)
        except Exception as e:
            print(f"[PLUGIN ERROR] {self.display_name} edit request failed: {e}")

    def _on_filter_changed(self, payload: dict):
        if not self._ui:
            return
        try:
            f = payload.get("filter")
            if not f:
                return

            models = self._service.search_models(f)
            stats = self._service.get_statistics_from_subset(models)

            game_systems = self._service.get_game_systems()
            factions = self._service.get_factions()

            self._ui.display_models(models, game_systems=game_systems, factions=factions)
            self._ui.update_statistics(stats)

        except Exception as e:
            print(f"[PLUGIN ERROR] {self.display_name} filter failed: {e}")
            if self._ui:
                self._ui._show_error(f"Filter error: {e}")

    def _on_paint_removed(self, payload: dict):
        """
        Cross-plugin: paint_tracker has deleted a paint.
        Remove that paint from all model links so nothing points to a ghost.
        """
        paint_id = payload.get("id")
        if paint_id is None:
            return
        try:
            self._service.on_paint_removed(paint_id)
            # If UI is showing linked paints for the current edit, refresh label
            if self._ui and paint_id in self._ui._linked_paint_ids:
                self._ui._linked_paint_ids.remove(paint_id)
                self._ui._update_linked_paints_label()
        except Exception as e:
            print(f"[PLUGIN WARNING] {self.display_name} paint_removed cleanup failed: {e}")

    # ============================================================
    # HELPERS
    # ============================================================

    def _persist_defaults(self, game_system: str, status: str):
        try:
            self._settings.set("model_tracker.default_game_system", game_system)
            self._settings.set("model_tracker.default_status", status)
        except Exception as e:
            print(f"[PLUGIN WARNING] {self.display_name}: Failed to persist defaults: {e}")

    def _refresh(self):
        """Re-apply the current filter to refresh the table."""
        if self._ui:
            self.context.event_bus.emit("models_filter_changed", {
                "filter": self._ui._current_filter
            })
