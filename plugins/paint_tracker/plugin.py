"""
Paint Tracker Plugin (Refactored)

Key Improvements:
- Color filter properly integrated into main filtering pipeline
- Combines text/type/brand filters WITH color filtering
- Stats update correctly based on filtered results
- Cleaner event flow and safer UI handling
- Better separation: color filter applied to already-filtered subset
"""

from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from .ui import PaintUI
from .models import ValidationError, PaintFilter
from .settings_page import PaintSettingsPage


class Plugin(PluginBase):
    def __init__(self, context):
        super().__init__(context)

        self._service = None
        self._settings = None
        self._ui: PaintUI | None = None
        self._subscriptions = []

        # Track active color filter
        self._active_color_filter: str | None = None

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

        # Self-register dashboard provider so this plugin is independent of
        # the dashboard plugin's built-in _setup_providers.
        # 250 ms gives all other plugins time to activate first; v2 fires at
        # 350 ms so it will still win when both are loaded.
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

    # ── Dashboard wiring ──────────────────────────────────────────────────────

    def _register_dashboard_provider(self):
        """Register paint dashboard provider under the canonical key."""
        try:
            import importlib
            mod = importlib.import_module(
                "plugins.dashboard.providers.paint_provider"
            )
            cls = getattr(mod, "PaintDashboardProvider")
            reg = self.context.services.try_get("dashboard_registry")
            if reg and self._service:
                provider = cls(self._service)
                provider._owner = "paint_tracker"   # ownership marker
                reg.register_provider("paint_tracker", provider)
                # Signal the dashboard to re-render with our provider
                try:
                    self.context.event_bus.emit("dashboard_provider_updated", {})
                except Exception:
                    pass
        except Exception as e:
            log.error(f"[PAINT TRACKER] Dashboard provider failed: {e}")

    def _cleanup_dashboard_provider(self):
        """Only remove our registration if we still own the key."""
        try:
            reg = self.context.services.try_get("dashboard_registry")
            if reg:
                current = reg.get_provider("paint_tracker")
                if getattr(current, "_owner", None) == "paint_tracker":
                    reg.unregister_provider("paint_tracker")
        except Exception:
            pass

    # ── Services ──────────────────────────────────────────────────────────────

    def _resolve_services(self):
        self._service = self.context.services.get("paint_service")
        self._settings = self.context.services.get("settings")

        if not self._service:
            raise RuntimeError("PaintService not found")

        if not self._settings:
            raise RuntimeError("SettingsService not found")

    def _register_settings(self):
        registry = self.context.services.get("settings_registry")
        if registry:
            registry.register_page(
                self.display_name,
                lambda ctx: PaintSettingsPage(ctx)
            )

    def _init_ui(self):
        self._ui = PaintUI(self.context)

    def _apply_settings(self):
        if not self._ui:
            return

        try:
            default_brand = self._settings.get("paint_tracker.default_brand", "")
            default_type = self._settings.get("paint_tracker.default_type", "Base")

            if default_brand:
                self._ui.brand_input.setCurrentText(default_brand)

            if default_type:
                index = self._ui.type_combo.findText(default_type)
                if index >= 0:
                    self._ui.type_combo.setCurrentIndex(index)
                else:
                    self._ui.type_combo.setCurrentText(default_type)

        except Exception as e:
            log.warning(f"[PLUGIN WARNING] Failed to apply settings: {e}")

    def _initial_load(self):
        try:
            data = self._settings.get("paint_tracker.filters", {})

            paint_filter = PaintFilter(
                brand=data.get("brand"),
                paint_type=data.get("type"),
                level=data.get("level"),
                search_text=data.get("search"),
                sort_by=data.get("sort_by"),
                sort_desc=data.get("sort_desc", False),
                notify_only=data.get("notify_only", False),
            )

            self.context.event_bus.emit("paints_filter_changed", {
                "filter": paint_filter
            })

        except Exception as e:
            log.warning(f"[PLUGIN WARNING] Failed initial load: {e}")
            self._refresh_ui()

    # ============================================================
    # EVENTS
    # ============================================================

    def _register_events(self):
        self._subscribe("paint_added", self._on_paint_added)
        self._subscribe("paint_removed", self._on_paint_removed)
        self._subscribe("paint_updated", self._on_paint_updated)
        self._subscribe("paints_filter_changed", self._on_filter_changed)
        self._subscribe("paints_import_requested", self._on_import_requested)
        self._subscribe("stats_color_filter_changed", self._on_color_filter_changed)

    def _subscribe(self, event_name, handler):
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
    # COLOR FILTER INTEGRATION
    # ============================================================

    def _on_color_filter_changed(self, payload: dict):
        """
        Update the active color filter state.

        This handler intentionally does NOT trigger a UI refresh.  The UI layer
        emits stats_color_filter_changed first (to set state here), then
        immediately emits paints_filter_changed to trigger the actual refresh.
        This guarantees exactly one refresh per user action and ensures
        _active_color_filter is already correct when _on_filter_changed runs.
        """
        try:
            color = payload.get("color")
            if color and len(color) == 7 and color.startswith("#"):
                self._active_color_filter = color.upper()
            else:
                self._active_color_filter = None
            log.debug(f"[PLUGIN] Color filter state updated: {self._active_color_filter}")
        except Exception as e:
            log.error(f"[PLUGIN ERROR] Color filter state update failed: {e}")

    def _apply_color_filter_to_subset(self, paints: list) -> list:
        """
        Apply color filtering on top of already-filtered results.

        This is the key architectural piece: color filtering happens
        AFTER text/brand/type filtering, not instead of it.

        Uses strict hue-based matching (30° tolerance) to ensure:
        - Red picks only return reds (not oranges/pinks)
        - Blue picks only return blues (not purples/teals)
        - Grays only match other grays

        Args:
            paints: Already filtered paint list

        Returns:
            Color-filtered subset (or original if no color filter active)
        """

        if not self._active_color_filter:
            return paints

        if not paints:
            return []

        try:
            # Service uses strict hue matching internally
            return self._service.find_paints_by_color(
                self._active_color_filter,
                paints=paints
            )
        except Exception as e:
            log.warning(f"[PLUGIN WARNING] Color filter application failed: {e}")
            return paints

    # ============================================================
    # SETTINGS PERSISTENCE
    # ============================================================

    def _persist_user_settings(self, brand: str, paint_type: str):
        try:
            self._settings.set("paint_tracker.default_brand", brand)
            self._settings.set("paint_tracker.default_type", paint_type)
        except Exception as e:
            log.warning(f"[PLUGIN WARNING] Failed to persist settings: {e}")

    def _persist_filter(self, paint_filter: PaintFilter):
        try:
            self._settings.set("paint_tracker.filters", {
                "brand":       paint_filter.brand,
                "type":        paint_filter.paint_type,
                "level":       paint_filter.level,
                "search":      paint_filter.search_text,
                "sort_by":     paint_filter.sort_by,
                "sort_desc":   paint_filter.sort_desc,
                "notify_only": getattr(paint_filter, "notify_only", False),
            })
        except Exception as e:
            log.warning(f"[PLUGIN WARNING] Failed to save filter: {e}")

    # ============================================================
    # EVENT HANDLERS
    # ============================================================

    def _on_paint_added(self, payload: dict):
        try:
            paint = self._service.add_paint(
                brand=payload.get("brand", ""),
                name=payload.get("name", ""),
                paint_type=payload.get("type", ""),
                color=payload.get("color", "#000000"),
                quantity=payload.get("quantity", 1),
                level=payload.get("level"),
                notes=payload.get("notes"),
                is_favorite=bool(payload.get("is_favorite", False)),
                notify_low_stock=bool(payload.get("notify_low_stock", True)),
            )

            self._persist_user_settings(paint.brand, paint.paint_type)

            if self._ui:
                self._ui._show_success(f"Added: {paint.brand} - {paint.name}")

            self._refresh_with_current_filter()

        except ValidationError as e:
            if self._ui:
                self._ui._show_error(str(e))
        except Exception as e:
            log.error(f"[PLUGIN ERROR] Add paint failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_paint_updated(self, payload: dict):
        try:
            paint = self._service.update_paint(
                paint_id=payload.get("id"),
                brand=payload.get("brand", ""),
                name=payload.get("name", ""),
                paint_type=payload.get("type", ""),
                color=payload.get("color", "#000000"),
                quantity=payload.get("quantity", 1),
                level=payload.get("level"),
                notes=payload.get("notes"),
                is_favorite=bool(payload.get("is_favorite", False)),
                notify_low_stock=bool(payload.get("notify_low_stock", True)),
            )

            # Suppress toast for silent in-place toggles (favourite / notify)
            if self._ui and not payload.get("_silent"):
                self._ui._show_success(f"Updated: {paint.brand} - {paint.name}")

            self._refresh_with_current_filter()

        except (ValidationError, ValueError) as e:
            if self._ui:
                self._ui._show_error(str(e))
        except Exception as e:
            log.error(f"[PLUGIN ERROR] Update paint failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_paint_removed(self, payload: dict):
        try:
            paint_id = payload.get("id")

            # ── Capture state before deletion so we can offer Undo ────────────
            paint      = None
            paint_data = None
            try:
                paint = self._service.get_paint(paint_id)
                if paint:
                    paint_data = {
                        "brand":            paint.brand,
                        "name":             paint.name,
                        "paint_type":       paint.paint_type,
                        "color":            paint.color,
                        "quantity":         paint.quantity,
                        "level":            paint.level,
                        "notes":            paint.notes or "",
                        "is_favorite":      bool(paint.is_favorite),
                        "notify_low_stock": bool(getattr(paint, "notify_low_stock", True)),
                    }
            except Exception:
                pass

            success = self._service.remove_paint(paint_id)

            if not success:
                if self._ui:
                    self._ui._show_error("Paint not found")
                return

            # ── Register undo and show toast with Undo button ─────────────────
            if paint_data:
                label  = f"{paint.brand} — {paint.name}"
                _svc   = self._service
                _plug  = self

                def _undo(_d=paint_data):
                    try:
                        _svc.add_paint(**_d)
                        _plug._refresh_with_current_filter()
                        _plug.context.event_bus.emit("paint_added", {})
                    except Exception as ex:
                        log.error(f"[UNDO] Restore paint failed: {ex}")

                from ui.toast import ToastManager
                from ui.undo_manager import UndoManager
                UndoManager.instance().push(f"Deleted {label}", _undo)
                ToastManager.instance().show(
                    f"Removed {label}",
                    level="info",
                    duration=6000,
                    action_label="Undo",
                    action_fn=_undo,
                )
            else:
                if self._ui:
                    self._ui._show_success("Paint removed")

            self._refresh_with_current_filter()

        except Exception as e:
            log.error(f"[PLUGIN ERROR] Remove paint failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_filter_changed(self, payload: dict):
        """
        Main filter handler - applies text/brand/type/level filters,
        then applies color filter on top of those results.

        Data flow:
        1. Get base filter from payload
        2. Apply base filter via service.search_paints()
        3. Apply color filter to that subset
        4. Calculate stats from final filtered subset
        5. Push everything to UI
        """

        if not self._ui:
            return

        try:
            paint_filter = payload.get("filter")
            if not paint_filter:
                log.warning("[PLUGIN WARNING] Filter changed but no filter provided")
                return

            # Persist filter settings
            self._persist_filter(paint_filter)

            # Step 1: Apply base filters (text, brand, type, level, sort)
            base_filtered_paints = self._service.search_paints(paint_filter)

            # Step 2: Apply color filter on top of base results
            final_paints = self._apply_color_filter_to_subset(base_filtered_paints)

            # Step 3: Calculate statistics from FINAL filtered subset
            stats = self._service.get_statistics_from_subset(final_paints)

            # Step 4: Get dropdown options (always from full collection)
            brands = self._service.get_brands()
            types = self._service.get_types()
            levels = self._service.get_levels()

            # Step 5: Push to UI
            self._ui.display_paints(
                final_paints,
                brands=brands,
                types=types,
                levels=levels
            )

            self._ui.update_statistics(stats)

            log.debug(f"[PLUGIN] Filter applied: {len(base_filtered_paints)} base → {len(final_paints)} final")

        except Exception as e:
            log.error(f"[PLUGIN ERROR] Filter failed: {e}")
            if self._ui:
                self._ui._show_error(f"Filter error: {e}")

    def _on_import_requested(self, payload: dict):
        try:
            success_count, errors = self._service.import_paints(
                payload.get("paints", [])
            )

            self.context.event_bus.emit("paints_import_complete", {
                "success_count": success_count,
                "errors": errors
            })

            self._refresh_with_current_filter()

        except Exception as e:
            log.error(f"[PLUGIN ERROR] Import failed: {e}")
            self.context.event_bus.emit("paints_import_complete", {
                "success_count": 0,
                "errors": [str(e)]
            })

    # ============================================================
    # UI SYNC
    # ============================================================

    def _refresh_ui(self):
        """Public refresh - uses current filter state"""
        self._refresh_with_current_filter()

    def _refresh_with_current_filter(self):
        """
        Re-apply the current filter state (including color filter).

        This is the single source of truth for refreshing the UI.
        It reconstructs the filter from settings and re-emits the
        filter_changed event.
        """

        try:
            data = self._settings.get("paint_tracker.filters", {})

            paint_filter = PaintFilter(
                brand=data.get("brand"),
                paint_type=data.get("type"),
                level=data.get("level"),
                search_text=data.get("search"),
                sort_by=data.get("sort_by"),
                sort_desc=data.get("sort_desc", False),
                notify_only=data.get("notify_only", False),
            )

            self.context.event_bus.emit("paints_filter_changed", {
                "filter": paint_filter
            })

        except Exception as e:
            log.error(f"[PLUGIN ERROR] Refresh failed: {e}")