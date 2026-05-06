import os
from pathlib import Path

BASE_PATH = Path(r"C:\Users\JonathanStrachan\PycharmProjects\Adeptus Craftmatica")

# Folder structure
folders = [
    "core",
    "ui",
    "plugins",
    "plugins/paint_tracker",
    "assets",
]

# Files with optional starter content
files = {
    "main.py": """# Entry point for Adeptus Craftmatica

def main():
    print("Adeptus Craftmatica starting...")


if __name__ == "__main__":
    main()
""",

    "core/__init__.py": "",
    "core/app_context.py": "",
    "core/event_bus.py": "",
    "core/plugin_base.py": "",
    "core/plugin_manager.py": "",
    "core/service_registry.py": "",
    "core/database_service.py": "",
    "core/settings_service.py": "",

    "ui/__init__.py": "",
    "ui/main_window.py": "",

    "plugins/__init__.py": "",

    "plugins/paint_tracker/plugin.json": """{
    "name": "Paint Tracker",
    "id": "paint_tracker",
    "version": "0.1.0",
    "entry": "plugin.py"
}
""",

    "plugins/paint_tracker/plugin.py": """# Paint Tracker Plugin Entry Point

from core.plugin_base import PluginBase


class Plugin(PluginBase):
    def activate(self):
        print("Paint Tracker activated")

    def deactivate(self):
        print("Paint Tracker deactivated")

    def get_ui(self):
        return None
""",

    "plugins/paint_tracker/models.py": "",
    "plugins/paint_tracker/ui.py": "",
}


def create_structure():
    print(f"Creating project at: {BASE_PATH}\\n")

    # Create base directory
    BASE_PATH.mkdir(parents=True, exist_ok=True)

    # Create folders
    for folder in folders:
        path = BASE_PATH / folder
        path.mkdir(parents=True, exist_ok=True)
        print(f"Created folder: {path}")

    # Create files
    for file_path, content in files.items():
        full_path = BASE_PATH / file_path

        if not full_path.exists():
            full_path.write_text(content, encoding="utf-8")
            print(f"Created file: {full_path}")
        else:
            print(f"Skipped (already exists): {full_path}")

    print("\\n✅ Project structure created successfully!")


if __name__ == "__main__":
    create_structure()