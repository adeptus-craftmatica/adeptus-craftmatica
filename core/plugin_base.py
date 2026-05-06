# core/plugin_base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class PluginBase(ABC):
    """
    Base class for all plugins.

    Provides:
    - Required lifecycle hooks (activate, deactivate, get_ui)
    - Optional metadata (name, id, version, description)
    - Safe defaults (no breaking changes)
    """

    # ----------------------------
    # Optional Metadata (Override if desired)
    # ----------------------------

    plugin_id: str = "unknown_plugin"
    name: str = "Unnamed Plugin"
    version: str = "0.0.1"
    description: str = ""

    def __init__(self, context):
        self.context = context

    # ----------------------------
    # Lifecycle (REQUIRED)
    # ----------------------------

    @abstractmethod
    def activate(self):
        """
        Called when the plugin is loaded.

        Use this to:
        - Resolve services
        - Register event listeners
        - Initialize UI
        """
        raise NotImplementedError

    @abstractmethod
    def deactivate(self):
        """
        Called when the plugin is unloaded.

        Use this to:
        - Unsubscribe from events
        - Clean up resources
        """
        raise NotImplementedError

    @abstractmethod
    def get_ui(self):
        """
        Return the main QWidget for this plugin.

        Return None if the plugin has no UI.
        """
        raise NotImplementedError

    # ----------------------------
    # Optional Hooks (SAFE DEFAULTS)
    # ----------------------------

    def on_event(self, event_name: str, payload: dict):
        """
        Optional generic event hook (not required).

        Can be used for:
        - Logging
        - Debugging
        - Catch-all event handling
        """
        pass

    def get_settings_page(self):
        """
        Optional settings page hook.

        Not required because you're using SettingsRegistry,
        but useful if you ever want plugin-driven settings discovery.
        """
        return None

    # ----------------------------
    # Helpers
    # ----------------------------

    @property
    def display_name(self) -> str:
        """
        Safe display name for UI.

        Falls back to class name if not overridden.
        """
        return self.name or self.__class__.__name__

    def __repr__(self):
        return f"<Plugin {self.display_name} v{self.version}>"