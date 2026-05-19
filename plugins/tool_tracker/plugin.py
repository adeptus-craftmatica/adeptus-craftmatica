"""
Tool Tracker Plugin

Track hobby tools — nippers, files, blades, brushes, adhesives and more.
"""

from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase
from .ui import ToolUI
from .models import ValidationError, ToolFilter


class Plugin(PluginBase):
    def __init__(self, context):
        super().__init__(context)

        self._service = None
        self._settings = None
        self._ui: ToolUI | None = None
        self._subscriptions = []

    # ============================================================
    # LIFECYCLE
    # ============================================================

    def activate(self):
        log.debug(f"[PLUGIN] {self.display_name} activating...")

        self._resolve_services()
        self._init_ui()
        self._register_events()
        self._initial_load()

        log.debug(f"[PLUGIN] {self.display_name} activated")

    def deactivate(self):
        log.debug(f"[PLUGIN] {self.display_name} deactivating...")

        self._unsubscribe_all()

        self._ui = None
        self._service = None
        self._settings = None

        log.debug(f"[PLUGIN] {self.display_name} deactivated")

    def get_ui(self):
        return self._ui

    @property
    def display_name(self) -> str:
        return "Tool Tracker"

    # ============================================================
    # SETUP
    # ============================================================

    def _resolve_services(self):
        self._service = self.context.services.get("tool_service")
        self._settings = self.context.services.get("settings")

        if not self._service:
            raise RuntimeError("ToolService not found")

    def _init_ui(self):
        self._ui = ToolUI(self.context)

    def _initial_load(self):
        """Push the full unfiltered tool list to the UI on startup."""
        try:
            self.context.event_bus.emit("tools_filter_changed", {
                "filter": ToolFilter()
            })
        except Exception as e:
            log.warning(f"[PLUGIN WARNING] Initial load failed: {e}")
            self._refresh_ui()

    # ============================================================
    # EVENTS
    # ============================================================

    def _register_events(self):
        self._subscribe("tool_added",          self._on_tool_added)
        self._subscribe("tool_removed",        self._on_tool_removed)
        self._subscribe("tool_updated",        self._on_tool_updated)
        self._subscribe("tools_filter_changed", self._on_filter_changed)

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

    def _on_tool_added(self, payload: dict):
        try:
            tool = self._service.add_tool(
                name      = payload.get("name", ""),
                tool_type = payload.get("tool_type", ""),
                brand     = payload.get("brand", ""),
                condition = payload.get("condition", "Good"),
                quantity  = payload.get("quantity", 1),
                notes     = payload.get("notes"),
            )

            if self._ui:
                self._ui._show_success(f"Added: {tool.name}")

            self._refresh_ui()

        except ValidationError as e:
            if self._ui:
                self._ui._show_error(str(e))
        except Exception as e:
            log.error(f"[PLUGIN ERROR] Add tool failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_tool_updated(self, payload: dict):
        try:
            tool = self._service.update_tool(
                tool_id   = payload.get("id"),
                name      = payload.get("name", ""),
                tool_type = payload.get("tool_type", ""),
                brand     = payload.get("brand", ""),
                condition = payload.get("condition", "Good"),
                quantity  = payload.get("quantity", 1),
                notes     = payload.get("notes"),
            )

            if self._ui:
                self._ui._show_success(f"Updated: {tool.name}")

            self._refresh_ui()

        except (ValidationError, ValueError) as e:
            if self._ui:
                self._ui._show_error(str(e))
        except Exception as e:
            log.error(f"[PLUGIN ERROR] Update tool failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_tool_removed(self, payload: dict):
        try:
            success = self._service.remove_tool(payload.get("id"))

            if self._ui:
                if success:
                    self._ui._show_success("Tool removed")
                else:
                    self._ui._show_error("Tool not found")

            self._refresh_ui()

        except Exception as e:
            log.error(f"[PLUGIN ERROR] Remove tool failed: {e}")
            if self._ui:
                self._ui._show_error(str(e))

    def _on_filter_changed(self, payload: dict):
        if not self._ui:
            return

        try:
            tool_filter = payload.get("filter")
            if not tool_filter:
                tool_filter = ToolFilter()

            tools = self._service.search_tools(tool_filter)
            stats = self._service.get_statistics_from_subset(tools)

            brands = self._service.get_brands()

            self._ui.display_tools(tools, brands=brands)
            self._ui.update_statistics(stats)

            log.debug(f"[PLUGIN] Filter applied: {len(tools)} tools shown")

        except Exception as e:
            log.error(f"[PLUGIN ERROR] Filter failed: {e}")
            if self._ui:
                self._ui._show_error(f"Filter error: {e}")

    # ============================================================
    # UI SYNC
    # ============================================================

    def _refresh_ui(self):
        """Re-emit a blank filter to reload the full list."""
        try:
            self.context.event_bus.emit("tools_filter_changed", {
                "filter": ToolFilter()
            })
        except Exception as e:
            log.error(f"[PLUGIN ERROR] Refresh failed: {e}")
