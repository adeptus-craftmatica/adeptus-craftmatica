# main.py

import sys
from PySide6.QtWidgets import QApplication

from core.app_context import AppContext
from core.plugin_manager import PluginManager
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # ----------------------------
    # Core App Context
    # (pass app so ThemeManager can be registered)
    # ----------------------------
    print("[APP] Initializing context...")
    context = AppContext(app=app)
    print("[APP] Context initialized\n")

    # ----------------------------
    # Apply initial theme BEFORE window is created
    # (prevents white flash on startup)
    # ----------------------------
    tm = context.services.get("theme_manager")
    if tm:
        tm.apply_current()

    # ----------------------------
    # Plugin System
    # ----------------------------
    manager = PluginManager(context)
    manager.load_plugins()

    # Register manager so dialogs can inspect all_manifests (incl. disabled plugins)
    context.services.register("plugin_manager", manager)

    # ----------------------------
    # Main Window
    # ----------------------------
    window = MainWindow(manager.plugins, context)
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
