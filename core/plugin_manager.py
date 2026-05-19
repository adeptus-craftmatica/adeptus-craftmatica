# core/plugin_manager.py

import importlib
import sys
from pathlib import Path
import json
import logging
log = logging.getLogger(__name__)


class PluginManager:
    def __init__(self, context, plugin_dir="plugins"):
        self.context = context
        self.plugin_dir = Path(plugin_dir)
        self.plugins = []

    # ============================================================
    # 🔥 MAIN ENTRY
    # ============================================================

    def load_plugins(self):
        sys.path.append(str(Path.cwd()))

        # ----------------------------
        # 1. Discover all plugins
        # ----------------------------
        manifests = self._discover_manifests()
        # Keep a copy so external callers (e.g. plugin manager dialog) can
        # inspect available plugins including disabled ones.
        self.all_manifests: dict = manifests

        # ----------------------------
        # 2. Resolve load order
        # ----------------------------
        load_order = self._resolve_dependencies(manifests)

        log.debug("\n[PLUGIN] Load order:")
        for p in load_order:
            log.debug(f"   → {p}")

        # ----------------------------
        # 3. Determine disabled plugins
        # ----------------------------
        settings = self.context.services.get("settings") if self.context else None
        disabled: list = []
        if settings:
            try:
                disabled = settings.get("plugin_layout.disabled", []) or []
            except Exception:
                disabled = []

        # ----------------------------
        # 4. Load in correct order
        # ----------------------------
        for plugin_name in load_order:
            plugin_path, data = manifests[plugin_name]

            # Core plugins (category == "core" or explicitly "dashboard") are
            # never disabled, even if they appear in the disabled list.
            is_core = (
                data.get("category") == "core"
                or data.get("id") == "dashboard"
                or plugin_name == "dashboard"
            )
            if not is_core and plugin_name in disabled:
                log.debug(f"[PLUGIN] Skipping disabled plugin: {plugin_name}")
                continue

            log.debug(f"\n[PLUGIN] Loading: {plugin_name}")

            # Auto-register
            self._auto_register_modules(plugin_name, plugin_path)

            try:
                module_path = f"plugins.{plugin_name}.{data['entry'].replace('.py', '')}"
                module = importlib.import_module(module_path)

                plugin_class = getattr(module, "Plugin")
                plugin = plugin_class(self.context)

                self._apply_manifest(plugin, data, plugin_name)

                plugin.activate()
                self.plugins.append(plugin)

                log.debug(f"[PLUGIN] Loaded: {plugin.display_name}")

            except Exception as e:
                log.error(f"[PLUGIN ERROR] Failed to load {plugin_name}: {e}")

    # ============================================================
    # 🔍 DISCOVERY
    # ============================================================

    def _discover_manifests(self):
        manifests = {}

        for plugin_path in self.plugin_dir.iterdir():
            if not plugin_path.is_dir():
                continue

            manifest_file = plugin_path / "plugin.json"
            if not manifest_file.exists():
                continue

            try:
                data = json.loads(manifest_file.read_text())
                plugin_name = plugin_path.name
                manifests[plugin_name] = (plugin_path, data)

            except Exception as e:
                log.error(f"[PLUGIN ERROR] Invalid manifest in {plugin_path}: {e}")

        return manifests

    # ============================================================
    # 🔥 DEPENDENCY RESOLUTION (Topological Sort)
    # ============================================================

    def _resolve_dependencies(self, manifests: dict):
        graph = {}
        visited = {}
        result = []

        # Build graph
        for name, (_, data) in manifests.items():
            deps = data.get("dependencies", [])
            graph[name] = deps

        def visit(node):
            if node in visited:
                if visited[node] == "visiting":
                    raise RuntimeError(f"Circular dependency detected at '{node}'")
                return

            visited[node] = "visiting"

            for dep in graph.get(node, []):
                if dep not in graph:
                    raise RuntimeError(f"Missing dependency: '{dep}' required by '{node}'")
                visit(dep)

            visited[node] = "visited"
            result.append(node)

        for plugin in graph:
            visit(plugin)

        return result

    # ============================================================
    # 🔧 MANIFEST APPLICATION
    # ============================================================

    def _apply_manifest(self, plugin, data: dict, fallback_name: str):
        if getattr(plugin, "plugin_id", "unknown_plugin") == "unknown_plugin":
            plugin.plugin_id = data.get("id", fallback_name)

        if getattr(plugin, "name", "Unnamed Plugin") == "Unnamed Plugin":
            plugin.name = data.get("name", fallback_name)

        if getattr(plugin, "version", "0.0.1") == "0.0.1":
            plugin.version = data.get("version", "0.0.1")

        if getattr(plugin, "description", "") == "":
            plugin.description = data.get("description", "")

    # ============================================================
    # 🔄 DYNAMIC LOAD / UNLOAD  (used by plugin manager UI)
    # ============================================================

    def load_plugin(self, plugin_id: str):
        """
        Dynamically load and activate a single plugin by its ID.

        Safe to call at runtime — Python's import system caches modules in
        sys.modules, so re-importing a previously-seen module is instant and
        returns the same module object.  We just create a fresh Plugin()
        instance and call activate(), exactly as the initial boot does.

        Returns the activated plugin object, or None on failure.
        """
        if plugin_id not in self.all_manifests:
            log.error(f"[PLUGIN] Cannot load '{plugin_id}': not found in manifests")
            return None

        # Already active — hand back the existing instance
        existing = next(
            (p for p in self.plugins if getattr(p, "plugin_id", "") == plugin_id),
            None,
        )
        if existing:
            log.debug(f"[PLUGIN] '{plugin_id}' is already loaded — returning existing instance")
            return existing

        plugin_path, data = self.all_manifests[plugin_id]
        log.debug(f"\n[PLUGIN] Dynamically loading: {plugin_id}")

        # Register any sub-modules that expose a register() function
        self._auto_register_modules(plugin_id, plugin_path)

        try:
            module_path = f"plugins.{plugin_id}.{data['entry'].replace('.py', '')}"
            # importlib.import_module is idempotent — returns cached module if
            # already imported, so disabling then re-enabling in the same
            # session works perfectly without re-executing module-level code.
            module = importlib.import_module(module_path)

            plugin_class = getattr(module, "Plugin")
            plugin = plugin_class(self.context)
            self._apply_manifest(plugin, data, plugin_id)
            plugin.activate()
            self.plugins.append(plugin)

            log.debug(f"[PLUGIN] Dynamically loaded: {plugin.display_name}")
            return plugin

        except Exception as e:
            import traceback
            log.error(f"[PLUGIN ERROR] Failed to dynamically load '{plugin_id}': {e}")
            traceback.print_exc()
            return None

    def unload_plugin(self, plugin_id: str) -> bool:
        """
        Deactivate and remove a plugin from the live registry.

        Called by the plugin manager UI when the user disables a plugin.
        Returns True on success, False if the plugin wasn't found.
        """
        plugin = next(
            (p for p in self.plugins if getattr(p, "plugin_id", "") == plugin_id),
            None,
        )
        if plugin is None:
            return False

        try:
            plugin.deactivate()
        except Exception as e:
            log.error(f"[PLUGIN] Deactivation error for '{plugin_id}': {e}")

        self.plugins = [p for p in self.plugins
                        if getattr(p, "plugin_id", "") != plugin_id]
        log.debug(f"[PLUGIN] Unloaded: {plugin_id}")
        return True

    # ============================================================
    # ⚙️ AUTO REGISTRATION
    # ============================================================

    def _auto_register_modules(self, plugin_name: str, plugin_path: Path):
        for file in sorted(plugin_path.glob("*.py")):
            if file.name.startswith("__"):
                continue

            module_name = file.stem
            full_module_path = f"plugins.{plugin_name}.{module_name}"

            try:
                module = importlib.import_module(full_module_path)

                register_fn = getattr(module, "register", None)

                if callable(register_fn):
                    log.debug(f"[AUTO] Registering: {full_module_path}")
                    register_fn(self.context)

            except Exception as e:
                log.error(f"[AUTO ERROR] {full_module_path}: {e}")