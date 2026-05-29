# hooks/runtime_hook_craftmatica.py
#
# Executed at app startup when running as a PyInstaller bundle.
#
# Sets the working directory to sys._MEIPASS so all relative paths used by the
# app (plugins/, themes/, game_system_data/, paints.csv) resolve correctly
# inside the bundle.
#
# The database (app.db) is intentionally NOT stored here — AppContext detects
# the frozen flag and writes it to:
#   ~/Library/Application Support/AdeptusCraftmatica/app.db
# This means user data survives app updates and is never inside the bundle.

import sys
import os

if getattr(sys, 'frozen', False):
    # All bundled read-only data lives at sys._MEIPASS.
    # Changing cwd here lets Path("plugins"), Path("themes"), etc. resolve correctly.
    os.chdir(sys._MEIPASS)

    # Ensure the bundle root is on sys.path so importlib.import_module works
    # for the dynamic plugin loader (PluginManager appends cwd to sys.path,
    # but doing it here guarantees it's available before any imports run).
    if sys._MEIPASS not in sys.path:
        sys.path.insert(0, sys._MEIPASS)
