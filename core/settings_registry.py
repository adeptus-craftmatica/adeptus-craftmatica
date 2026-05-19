import logging
log = logging.getLogger(__name__)


class SettingsRegistry:
    """
    Registry for settings pages.

    Allows plugins and core to register settings UI dynamically.
    """

    def __init__(self):
        self._pages = []

    def register_page(self, name: str, widget_factory):
        """
        Register a settings page.

        Args:
            name: Display name
            widget_factory: Callable(context) -> QWidget
        """
        # Guard against duplicate page names — silent duplicates cause two tabs
        # with the same label in the settings dialog.
        existing_names = [n for n, _ in self._pages]
        if name in existing_names:
            log.warning(f"[SETTINGS] Warning: page '{name}' is already registered — skipping duplicate")
            return
        self._pages.append((name, widget_factory))
        log.debug(f"[SETTINGS] Page registered: {name}")

    def get_pages(self):
        return self._pages