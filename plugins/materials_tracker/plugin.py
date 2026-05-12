"""
Materials Tracker Plugin

Track basing materials, mediums, and scenic supplies.
"""
from __future__ import annotations

from core.plugin_base import PluginBase
from PySide6.QtCore import QTimer
from .ui import MaterialUI
from .models import ValidationError, MaterialFilter


class Plugin(PluginBase):
    def __init__(self, context):
        super().__init__(context)

        self._service = None
        self._ui: MaterialUI | None = None
        self._subscriptions = []

    # ============================================================
    # LIFECYCLE
    # ============================================================

    def activate(self):
        print(f"[PLUGIN] {self.display_name} activating...")

        self._resolve_services()
        self._init_ui()
        self._register_events()
        self._initial_load()

        # Register dashboard provider with ownership marker so v2 can take
        # over cleanly and restore v1's provider on deactivate.
        QTimer.singleShot(250, self._register_dashboard_provider)

        print(f"[PLUGIN] {self.display_name} activated")

    def deactivate(self):
        print(f"[PLUGIN] {self.display_name} deactivating...")

        self._unsubscribe_all()
        self._cleanup_dashboard_provider()

        self._ui      = None
        self._service = None

        print(f"[PLUGIN] {self.display_name} deactivated")

    def get_ui(self):
        return self._ui

    @property
    def display_name(self) -> str:
        return "Materials Tracker"

    # ============================================================
    # SETUP
    # ============================================================

    def _resolve_services(self):
        self._service = self.context.services.get("material_service")
        if not self._service:
            raise RuntimeError("MaterialService not found")

    def _init_ui(self):
        self._ui = MaterialUI(self.context)

    def _initial_load(self):
        """Push the full unfiltered list to the UI on startup."""
        try:
            self.context.event_bus.emit("materials_filter_changed", {
                "filter": MaterialFilter()
            })
        except Exception as e:
            print(f"[PLUGIN WARNING] Initial load failed: {e}")
            self._refresh_ui()

    # ============================================================
    # EVENTS
    # ============================================================

    def _register_events(self):
        self._subscribe("material_added",           self._on_material_added)
        self._subscribe("material_removed",         self._on_material_removed)
        self._subscribe("material_updated",         self._on_material_updated)
        self._subscribe("materials_filter_changed", self._on_filter_changed)

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

    def _on_material_added(self, payload: dict):
        try:
            mat = self._service.add_material(
                name          = payload.get("name", ""),
                material_type = payload.get("material_type", ""),
                brand         = payload.get("brand", ""),
                color         = payload.get("color", ""),
                stock         = payload.get("stock", "Good"),
                quantity      = payload.get("quantity", 1),
                notes         = payload.get("notes"),
            )

            if self._ui:
                self._ui._show_success(f"Added: {mat.name}")

            self._refresh_ui()

        except ValidationError as e:
            if self._ui:
                self._ui._show_error(str(e))
        except Exception as e:
            print(f"[PLUGIN ERROR] Add material failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_material_updated(self, payload: dict):
        try:
            mat = self._service.update_material(
                material_id   = payload.get("id"),
                name          = payload.get("name", ""),
                material_type = payload.get("material_type", ""),
                brand         = payload.get("brand", ""),
                color         = payload.get("color", ""),
                stock         = payload.get("stock", "Good"),
                quantity      = payload.get("quantity", 1),
                notes         = payload.get("notes"),
            )

            if self._ui:
                self._ui._show_success(f"Updated: {mat.name}")

            self._refresh_ui()

        except (ValidationError, ValueError) as e:
            if self._ui:
                self._ui._show_error(str(e))
        except Exception as e:
            print(f"[PLUGIN ERROR] Update material failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_material_removed(self, payload: dict):
        try:
            success = self._service.remove_material(payload.get("id"))

            if self._ui:
                if success:
                    self._ui._show_success("Material removed")
                else:
                    self._ui._show_error("Material not found")

            self._refresh_ui()

        except Exception as e:
            print(f"[PLUGIN ERROR] Remove material failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_filter_changed(self, payload: dict):
        if not self._ui:
            return

        try:
            mat_filter = payload.get("filter")
            if not mat_filter:
                mat_filter = MaterialFilter()

            materials = self._service.search_materials(mat_filter)
            stats     = self._service.get_statistics_from_subset(materials)
            brands    = self._service.get_brands()

            self._ui.display_materials(materials, brands=brands)
            self._ui.update_statistics(stats)

            print(f"[PLUGIN] Filter applied: {len(materials)} materials shown")

        except Exception as e:
            print(f"[PLUGIN ERROR] Filter failed: {e}")
            if self._ui:
                self._ui._show_error(f"Filter error: {e}")

    # ============================================================
    # UI SYNC
    # ============================================================

    def _refresh_ui(self):
        """Re-emit a blank filter to reload the full list."""
        try:
            self.context.event_bus.emit("materials_filter_changed", {
                "filter": MaterialFilter()
            })
        except Exception as e:
            print(f"[PLUGIN ERROR] Refresh failed: {e}")

    # ============================================================
    # DASHBOARD PROVIDER (ownership-aware)
    # ============================================================

    def _register_dashboard_provider(self):
        """Register under the canonical key with an _owner marker."""
        try:
            from plugins.dashboard.providers.materials_provider import MaterialsDashboardProvider
            reg = self.context.services.try_get("dashboard_registry")
            if reg and self._service:
                provider        = MaterialsDashboardProvider(self._service)
                provider._owner = "materials_tracker"
                reg.register_provider("materials_tracker", provider)
                try:
                    self.context.event_bus.emit("dashboard_provider_updated", {})
                except Exception:
                    pass
        except Exception as e:
            print(f"[MATERIALS V1] Dashboard provider failed: {e}")

    def _cleanup_dashboard_provider(self):
        """Only unregister if we still own the provider slot."""
        try:
            reg = self.context.services.try_get("dashboard_registry")
            if reg:
                current = reg.get_provider("materials_tracker")
                if getattr(current, "_owner", None) == "materials_tracker":
                    reg.unregister_provider("materials_tracker")
        except Exception:
            pass
