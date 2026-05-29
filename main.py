# main.py

import sys
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication

from core.app_context import AppContext
from core.plugin_manager import PluginManager
from ui.main_window import MainWindow


def _setup_logging():
    """
    In a frozen (packaged) build, also write logs to a file next to the database
    so errors are visible even without a console window.
    In development, log to stderr only.
    """
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [logging.StreamHandler()]

    if getattr(sys, 'frozen', False):
        if sys.platform == 'win32':
            import os
            log_dir = Path(os.environ.get('APPDATA', Path.home())) / 'AdeptusCraftmatica'
        else:
            log_dir = Path.home() / 'Library' / 'Application Support' / 'AdeptusCraftmatica'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / 'adeptus_craftmatica.log'
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))

    logging.basicConfig(level=logging.WARNING, format=fmt, handlers=handlers)


_setup_logging()
log = logging.getLogger(__name__)


def main():
    app = QApplication(sys.argv)

    # ----------------------------
    # Core App Context
    # (pass app so ThemeManager can be registered)
    # ----------------------------
    log.debug("[APP] Initializing context...")
    context = AppContext(app=app)
    log.debug("[APP] Context initialized")

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
