"""
Army Builder Plugin

Lifecycle controller.

Cross-plugin integration:
  - Listens for "model_removed" from model_tracker → nullifies unit.model_id links.
  - Registers "army_service" in ServiceRegistry so future plugins
    (encounter builder, campaign tracker) can query lists directly.
  - Emits "army_created", "army_updated", "army_deleted", "army_duplicated".
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from .ui import ArmyBuilderUI
from .models import ValidationError, ArmyFilter
from .settings_page import ArmyBuilderSettingsPage


class Plugin(PluginBase):

    plugin_id = "army_builder"
    name = "Army Builder"
    version = "0.1.0"
    description = "Build army lists for 40K, AoS, Kill Team, D&D, and more"

    def __init__(self, context):
        super().__init__(context)
        self._service = None
        self._settings = None
        self._ui: ArmyBuilderUI | None = None
        self._subscriptions: list[tuple[str, callable]] = []

    # ============================================================
    # LIFECYCLE
    # ============================================================

    def activate(self):
        log.debug(f"[PLUGIN] {self.display_name} activating...")

        self._resolve_services()
        self._register_settings()
        self._init_ui()
        self._apply_settings()
        self._register_events()
        self._initial_load()

        # Register dashboard provider with ownership marker so v2 can take
        # over cleanly and restore v1's provider on deactivate.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(250, self._register_dashboard_provider)

        log.debug(f"[PLUGIN] {self.display_name} activated")

    def deactivate(self):
        log.debug(f"[PLUGIN] {self.display_name} deactivating...")
        self._unsubscribe_all()
        self._cleanup_dashboard_provider()
        self._ui = None
        self._service = None
        self._settings = None
        log.debug(f"[PLUGIN] {self.display_name} deactivated")

    def get_ui(self):
        return self._ui

    # ============================================================
    # SETUP
    # ============================================================

    def _resolve_services(self):
        self._service = self.context.services.get("army_service")
        self._settings = self.context.services.get("settings")

        if not self._service:
            raise RuntimeError("ArmyService not found")
        if not self._settings:
            raise RuntimeError("SettingsService not found")

    def _register_settings(self):
        registry = self.context.services.try_get("settings_registry")
        if registry:
            registry.register_page(
                self.display_name,
                lambda ctx: ArmyBuilderSettingsPage(ctx),
            )

    def _init_ui(self):
        self._ui = ArmyBuilderUI(self.context)

    def _apply_settings(self):
        if not self._ui:
            return
        try:
            default_system = self._settings.get("army_builder.default_game_system", "")
            if default_system:
                self._ui.new_system_combo.setCurrentText(default_system)
        except Exception as e:
            log.warning(f"[PLUGIN WARNING] {self.display_name}: Failed to apply settings: {e}")

    def _initial_load(self):
        try:
            self.context.event_bus.emit("armies_filter_changed", {
                "filter": ArmyFilter()
            })
        except Exception as e:
            log.warning(f"[PLUGIN WARNING] {self.display_name}: Initial load failed: {e}")

    # ============================================================
    # EVENT SUBSCRIPTIONS
    # ============================================================

    def _register_events(self):
        # Army list management
        self._subscribe("army_create_requested", self._on_army_create)
        self._subscribe("army_update_requested", self._on_army_update)
        self._subscribe("army_delete_requested", self._on_army_delete)
        self._subscribe("army_duplicate_requested", self._on_army_duplicate)
        self._subscribe("army_open_requested", self._on_army_open)
        self._subscribe("armies_filter_changed", self._on_filter_changed)
        self._subscribe("army_export_requested", self._on_export)

        # Unit management (within builder tab)
        self._subscribe("unit_add_requested", self._on_unit_add)
        self._subscribe("unit_update_requested", self._on_unit_update)
        self._subscribe("unit_remove_requested", self._on_unit_remove)
        self._subscribe("unit_edit_requested", self._on_unit_edit_requested)
        self._subscribe("unit_reorder_requested", self._on_unit_reorder)
        self._subscribe("unit_duplicate_requested", self._on_unit_duplicate)

        # Cross-plugin: model deleted → nullify model_id links
        self._subscribe("model_removed", self._on_model_removed)
        # Cross-plugin: paint deleted → remove direct paint links
        self._subscribe("paint_removed", self._on_paint_removed)

        # Army paints tab refresh
        self._subscribe("army_paints_refresh_requested", self._on_army_paints_refresh)

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
    # ARMY EVENT HANDLERS
    # ============================================================

    def _on_army_create(self, payload: dict):
        try:
            army = self._service.create_army(
                name=payload.get("name", ""),
                game_system=payload.get("game_system", ""),
                faction=payload.get("faction", ""),
                format=payload.get("format", ""),
                points_limit=payload.get("points_limit", 0),
                notes=payload.get("notes"),
            )

            self._settings.set("army_builder.default_game_system", army.game_system)

            if self._ui:
                self._ui.show_create_success(f"Created: {army.name}")
                self._ui.clear_new_army_form()

            self.context.event_bus.emit("army_created", army.to_dict())
            self._refresh_list()

        except ValidationError as e:
            if self._ui:
                self._ui.show_create_error(str(e))
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} create army: {e}")
            if self._ui:
                self._ui.show_create_error(str(e))

    def _on_army_update(self, payload: dict):
        try:
            army = self._service.update_army(
                army_id=payload.get("id"),
                name=payload.get("name", ""),
                game_system=payload.get("game_system", ""),
                faction=payload.get("faction", ""),
                format=payload.get("format", ""),
                points_limit=payload.get("points_limit", 0),
                notes=payload.get("notes"),
            )
            self.context.event_bus.emit("army_updated", army.to_dict())
            # Refresh the builder with updated points limit
            units = self._service.get_units_for_army(army.id)
            if self._ui:
                self._ui.refresh_builder_units(units, army.points_limit)
            self._refresh_list()

        except (ValidationError, ValueError) as e:
            if self._ui:
                self._ui.show_create_error(str(e))
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} update army: {e}")

    def _on_army_delete(self, payload: dict):
        try:
            army_id = payload.get("id")
            success = self._service.delete_army(army_id)

            if success:
                if self._ui and self._ui._current_army_id == army_id:
                    self._ui._close_builder()
                self.context.event_bus.emit("army_deleted", {"id": army_id})
                self._refresh_list()

        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} delete army: {e}")

    def _on_army_duplicate(self, payload: dict):
        try:
            new_army = self._service.duplicate_army(payload.get("id"))
            self.context.event_bus.emit("army_duplicated", new_army.to_dict())
            if self._ui:
                self._ui.show_create_success(f"Duplicated as: {new_army.name}")
            self._refresh_list()
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} duplicate army: {e}")
            if self._ui:
                self._ui.show_create_error(str(e))

    def _on_army_open(self, payload: dict):
        try:
            army_id = payload.get("id")
            army = self._service.get_army(army_id)
            if not army:
                return
            units = self._service.get_units_for_army(army_id)
            if self._ui:
                self._ui.load_army_into_builder(army, units)
            self._refresh_paint_tab(army_id)
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} open army: {e}")

    def _on_filter_changed(self, payload: dict):
        if not self._ui:
            return
        try:
            f = payload.get("filter")
            if not f:
                return

            armies = self._service.search_armies(f)

            # Build per-army points totals + unit counts for display
            points_totals = {a.id: self._service.get_points_total(a.id) for a in armies}
            unit_counts = {
                a.id: len(self._service.get_units_for_army(a.id)) for a in armies
            }

            game_systems = self._service.get_game_systems()
            factions = self._service.get_factions()

            self._ui.display_armies(
                armies,
                points_totals=points_totals,
                unit_counts=unit_counts,
                game_systems=game_systems,
                factions=factions,
            )

            stats = self._service.get_statistics_from_subset(armies)
            self._ui.update_statistics(stats)

        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} filter: {e}")

    def _on_export(self, payload: dict):
        try:
            army_id = payload.get("id")
            army = self._service.get_army(army_id)
            if not army:
                return
            units = self._service.get_units_for_army(army_id)
            text = self._service.export_as_text(army, units)
            if self._ui:
                self._ui.show_export_dialog(text)
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} export: {e}")

    # ============================================================
    # UNIT EVENT HANDLERS
    # ============================================================

    def _on_unit_add(self, payload: dict):
        try:
            unit = self._service.add_unit(
                army_id=payload.get("army_id"),
                unit_name=payload.get("unit_name", ""),
                unit_role=payload.get("unit_role", ""),
                points_cost=payload.get("points_cost", 0),
                quantity=payload.get("quantity", 1),
                wargear_notes=payload.get("wargear_notes"),
                model_id=payload.get("model_id"),
                linked_paint_ids=payload.get("linked_paint_ids", []),
                sort_order=payload.get("sort_order", 0),
            )

            if self._ui:
                self._ui.show_unit_success(f"Added: {unit.unit_name}")
                self._ui._cancel_unit_edit()

            self._refresh_builder(unit.army_id)

        except ValidationError as e:
            if self._ui:
                self._ui.show_unit_error(str(e))
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} add unit: {e}")
            if self._ui:
                self._ui.show_unit_error(str(e))

    def _on_unit_update(self, payload: dict):
        try:
            unit = self._service.update_unit(
                unit_id=payload.get("id"),
                unit_name=payload.get("unit_name", ""),
                unit_role=payload.get("unit_role", ""),
                points_cost=payload.get("points_cost", 0),
                quantity=payload.get("quantity", 1),
                wargear_notes=payload.get("wargear_notes"),
                model_id=payload.get("model_id"),
                linked_paint_ids=payload.get("linked_paint_ids"),
            )

            if self._ui:
                self._ui.show_unit_success(f"Updated: {unit.unit_name}")
                self._ui._cancel_unit_edit()

            self._refresh_builder(unit.army_id)

        except (ValidationError, ValueError) as e:
            if self._ui:
                self._ui.show_unit_error(str(e))
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} update unit: {e}")

    def _on_unit_remove(self, payload: dict):
        try:
            unit_id = payload.get("id")
            unit = self._service.get_unit(unit_id)
            army_id = unit.army_id if unit else (self._ui._current_army_id if self._ui else None)

            success = self._service.remove_unit(unit_id)
            if success and army_id:
                if self._ui:
                    self._ui.show_unit_success("Unit removed")
                    self._ui._cancel_unit_edit()
                self._refresh_builder(army_id)

        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} remove unit: {e}")

    def _on_unit_edit_requested(self, payload: dict):
        """UI wants the full unit data to populate the form."""
        try:
            unit = self._service.get_unit(payload.get("id"))
            if unit and self._ui:
                self._ui.populate_unit_form(unit)
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} unit edit: {e}")

    def _on_unit_duplicate(self, payload: dict):
        try:
            unit = self._service.duplicate_unit(payload.get("id"))
            if self._ui:
                self._ui.show_unit_success(f"Duplicated: {unit.unit_name}")
            self._refresh_builder(unit.army_id)
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} duplicate unit: {e}")
            if self._ui:
                self._ui.show_unit_error(str(e))

    def _on_unit_reorder(self, payload: dict):
        """Move a unit up/down within its role group by swapping sort_order values."""
        try:
            unit_id = payload.get("id")
            direction = payload.get("direction", 1)  # -1 = up, 1 = down
            unit = self._service.get_unit(unit_id)
            if not unit:
                return

            army_id = unit.army_id
            units = self._service.get_units_for_army(army_id)
            same_role = [u for u in units if u.unit_role == unit.unit_role]
            same_role.sort(key=lambda u: u.sort_order)

            idx = next((i for i, u in enumerate(same_role) if u.id == unit_id), None)
            if idx is None:
                return

            swap_idx = idx + direction
            if swap_idx < 0 or swap_idx >= len(same_role):
                return

            target = same_role[swap_idx]
            # Swap sort orders
            self._service.update_unit(
                unit_id=unit.id,
                unit_name=unit.unit_name,
                unit_role=unit.unit_role,
                points_cost=unit.points_cost,
                quantity=unit.quantity,
                wargear_notes=unit.wargear_notes,
                model_id=unit.model_id,
                sort_order=target.sort_order,
            )
            self._service.update_unit(
                unit_id=target.id,
                unit_name=target.unit_name,
                unit_role=target.unit_role,
                points_cost=target.points_cost,
                quantity=target.quantity,
                wargear_notes=target.wargear_notes,
                model_id=target.model_id,
                sort_order=unit.sort_order,
            )
            self._refresh_builder(army_id)

        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} reorder unit: {e}")

    # ============================================================
    # CROSS-PLUGIN
    # ============================================================

    def _on_model_removed(self, payload: dict):
        model_id = payload.get("id")
        if model_id is None:
            return
        try:
            self._service.on_model_removed(model_id)
            if self._ui and self._ui._current_army_id:
                self._refresh_builder(self._ui._current_army_id)
        except Exception as e:
            log.warning(f"[PLUGIN WARNING] {self.display_name} model_removed cleanup: {e}")

    def _on_paint_removed(self, payload: dict):
        paint_id = payload.get("id")
        if paint_id is None:
            return
        try:
            self._service.on_paint_removed(paint_id)
            # Refresh paint tab if open army is affected
            if self._ui and self._ui._current_army_id:
                self._refresh_paint_tab(self._ui._current_army_id)
        except Exception as e:
            log.warning(f"[PLUGIN WARNING] {self.display_name} paint_removed cleanup: {e}")

    def _on_army_paints_refresh(self, payload: dict):
        army_id = payload.get("id")
        if army_id:
            self._refresh_paint_tab(army_id)

    # ============================================================
    # HELPERS
    # ============================================================

    def _refresh_list(self):
        self.context.event_bus.emit("armies_filter_changed", {
            "filter": self._ui._current_filter if self._ui else ArmyFilter()
        })

    def _refresh_builder(self, army_id: int):
        """Re-push current army units to the builder UI and refresh paint tab."""
        if not self._ui or self._ui._current_army_id != army_id:
            return
        try:
            army = self._service.get_army(army_id)
            units = self._service.get_units_for_army(army_id)
            if army:
                self._ui.refresh_builder_units(units, army.points_limit)
            self._refresh_paint_tab(army_id)
            self._refresh_stats()
        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} refresh builder: {e}")

    def _refresh_stats(self):
        """Push fresh army-level statistics to the UI without rebuilding the list."""
        if not self._ui:
            return
        try:
            stats = self._service.get_statistics()
            self._ui.update_statistics(stats)
        except Exception as e:
            log.warning(f"[PLUGIN WARNING] {self.display_name} stats refresh: {e}")

    def _refresh_paint_tab(self, army_id: int):
        """Build the aggregated paint list and push it to the Army Paints tab."""
        if not self._ui:
            return
        try:
            army = self._service.get_army(army_id)
            if not army:
                return

            model_service = self.context.services.try_get("model_service")
            paint_service = self.context.services.try_get("paint_service")

            raw_entries = self._service.get_army_paint_list(army_id, model_service)

            # Enrich with full paint objects
            enriched = []
            for entry in raw_entries:
                paint = None
                if paint_service:
                    try:
                        paint = paint_service.get_paint(entry["paint_id"])
                    except Exception:
                        pass
                enriched.append({
                    "paint_id": entry["paint_id"],
                    "paint": paint,
                    "unit_names": entry["unit_names"],
                    "sources": entry["sources"],
                })

            self._ui.refresh_paint_list(enriched, army_name=army.name)

        except Exception as e:
            log.error(f"[PLUGIN ERROR] {self.display_name} refresh paint tab: {e}")

    # ============================================================
    # DASHBOARD PROVIDER (ownership-aware)
    # ============================================================

    def _register_dashboard_provider(self):
        """Register under canonical key with an _owner marker."""
        try:
            from plugins.dashboard.providers.army_provider import ArmyDashboardProvider
            reg = self.context.services.try_get("dashboard_registry")
            if reg and self._service:
                provider        = ArmyDashboardProvider(self._service)
                provider._owner = "army_builder"
                reg.register_provider("army_builder", provider)
                try:
                    self.context.event_bus.emit("dashboard_provider_updated", {})
                except Exception:
                    pass
        except Exception as e:
            log.error(f"[ARMY V1] Dashboard provider failed: {e}")

    def _cleanup_dashboard_provider(self):
        """Only unregister if we still own the provider slot."""
        try:
            reg = self.context.services.try_get("dashboard_registry")
            if reg:
                current = reg.get_provider("army_builder")
                if getattr(current, "_owner", None) == "army_builder":
                    reg.unregister_provider("army_builder")
        except Exception:
            pass
