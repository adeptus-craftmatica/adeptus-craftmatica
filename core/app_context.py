# core/app_context.py

from pathlib import Path

from core.event_bus import EventBus
from core.database_service import DatabaseService
from core.service_registry import ServiceRegistry
from core.settings_service import SettingsService
from core.settings_registry import SettingsRegistry
from core.settings_pages.app_settings_page import AppSettingsPage


class AppContext:
    """
    Central application context.

    Provides:
    - EventBus (for decoupled communication)
    - ServiceRegistry (for shared services)
    - Core services (database, settings, theme_manager, etc.)
    """

    def __init__(self, app=None):
        self._app = app  # QApplication reference (may be None if not passed)

        # ----------------------------
        # Core infrastructure
        # ----------------------------

        self.event_bus = EventBus()
        self.services = ServiceRegistry()

        # ----------------------------
        # Register core services
        # ----------------------------

        # Database
        db_service = DatabaseService()
        self.services.register("db", db_service)

        # Settings service
        settings_service = SettingsService(
            db=db_service,
            event_bus=self.event_bus
        )
        self.services.register("settings", settings_service)

        # 🔥 NEW: Settings Registry
        settings_registry = SettingsRegistry()
        self.services.register("settings_registry", settings_registry)

        # ----------------------------
        # Register global defaults
        # ----------------------------

        settings_service.register_defaults({
            "app.theme": "dark",
            "app.window_width": 1200,
            "app.window_height": 800,
            "paint_tracker.default_brand": "",
            "paint_tracker.default_type": "Base",
            # Session resume
            "app.last_plugin_tab": "",
            "project_tracker.last_project_id": "",
            "project_tracker.status_filter": "",
            # Dashboard personalisation
            "dashboard.pinned_projects": "[]",
        })

        # 🔥 NEW: Register core settings pages dynamically
        settings_registry.register_page(
            "Application",
            lambda ctx: AppSettingsPage(ctx)
        )

        # ----------------------------
        # Theme Manager
        # ----------------------------
        if self._app is not None:
            from core.theme_manager import ThemeManager
            themes_dir = Path(__file__).parent.parent / "themes"
            theme_manager = ThemeManager(
                app=self._app,
                themes_dir=themes_dir,
                settings=settings_service,
            )
            self.services.register("theme_manager", theme_manager)
        else:
            print("[APP] No QApplication reference — ThemeManager skipped.")

        print("[APP] Context initialized")

        self.services.debug_dump()