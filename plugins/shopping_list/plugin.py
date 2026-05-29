"""Shopping List — plugin entry point."""
from __future__ import annotations
import logging
log = logging.getLogger(__name__)

from core.plugin_base import PluginBase


class Plugin(PluginBase):
    plugin_id    = "shopping_list"
    display_name = "Shopping List"
    name         = "Shopping List"
    version      = "1.0.0"
    description  = "Build, organise, and share hobby shopping lists with inventory integration."

    def __init__(self, context):
        super().__init__(context)
        self._service = None
        self._ui      = None
        self._subs: list = []

    def activate(self):
        db = self.context.services.get("db")
        from .repository import ShoppingRepository
        from .service    import ShoppingService
        repo = ShoppingRepository(db)
        self._service = ShoppingService(repo)
        self.context.services.register("shopping_service", self._service)

        from .ui import ShoppingListUI
        self._ui = ShoppingListUI(self._service, self.context)
        self._ui.setProperty("plugin_id", "shopping_list")

        # Subscribe to events from other plugins so they can trigger adds
        bus = self.context.event_bus
        pairs = [
            ("add_to_shopping_list", self._on_add_request),
        ]
        for event, handler in pairs:
            try:
                bus.subscribe(event, handler)
                self._subs.append((event, handler))
            except Exception as e:
                log.error(f"[SHOPPING] Subscribe error '{event}': {e}")

        log.info("[SHOPPING] Activated")

    def deactivate(self):
        bus = self.context.event_bus
        for event, handler in self._subs:
            try:
                bus.unsubscribe(event, handler)
            except Exception:
                pass
        self._subs.clear()
        self._ui      = None
        self._service = None
        log.info("[SHOPPING] Deactivated")

    def get_ui(self):
        return self._ui

    def _on_add_request(self, payload=None):
        """Handle add_to_shopping_list event from other plugins."""
        if not payload or not self._service or not self._ui:
            return
        try:
            lists = self._service.get_all_lists()
            if not lists:
                sl = self._service.create_list("My Shopping List")
                list_id = sl.id
            else:
                list_id = lists[0].id

            name          = payload.get("name", "")
            category      = payload.get("category", "Other")
            quantity      = float(payload.get("quantity", 1))
            unit          = payload.get("unit", "")
            notes         = payload.get("notes", "")
            source_plugin = payload.get("source_plugin", "")
            source_item_id = payload.get("source_item_id", "")
            project_id    = payload.get("project_id", "")
            section_title = payload.get("section", "General")

            if name:
                self._service.add_item_from_plugin(
                    list_id=list_id, name=name, category=category,
                    quantity=quantity, unit=unit, notes=notes,
                    source_plugin=source_plugin, source_item_id=source_item_id,
                    project_id=project_id, section_title=section_title,
                )
                if self._ui:
                    self._ui.refresh()
        except Exception as e:
            log.error(f"[SHOPPING] add_to_shopping_list error: {e}")

    def get_commands(self, context) -> list:
        from ui.command_palette import PaletteCommand
        return [
            PaletteCommand(
                id="shopping_list.open",
                title="Open Shopping List",
                icon="🛒",
                description="Navigate to your shopping list",
                category="Navigate",
                aliases=["shopping", "buy", "cart"],
                action=lambda: context.event_bus.emit(
                    "navigate_to_plugin", {"plugin_id": "shopping_list"}
                ),
            ),
            PaletteCommand(
                id="shopping_list.add",
                title="Add Item to Shopping List",
                icon="➕",
                description="Add a new item to your shopping list",
                category="Create",
                aliases=["add shopping", "new item"],
                action=lambda: self._ui.open_add_dialog() if self._ui else None,
            ),
        ]
