# ui/main_window.py

from PySide6.QtCore import Qt, QTimer, QObject, QEvent
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QApplication, QMessageBox,
)

from ui.animations import fade_in
from ui.toast import ToastManager

from core.settings_dialog import SettingsDialog
from ui.global_search import GlobalSearchPanel
from ui.theme_editor import ThemeEditorDialog
from ui.forge_dialog import TheForgeDialog
from ui.plugin_manager_dialog import PluginManagerDialog
from ui.command_palette import CommandPalette, CommandRegistry, PaletteCommand
from ui.exporter import ExportDialog


class _TabCycleFilter(QObject):
    """
    Application-level event filter that intercepts Ctrl+Tab / Ctrl+Shift+Tab
    before QTabWidget can consume them for its own MRU cycling.

    Installed on QApplication so it sees every key event regardless of which
    widget has focus, then lets the window handle the actual tab switch.
    """
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self._window = window

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.KeyPress:
            mods = event.modifiers()
            key  = event.key()
            ctrl = Qt.ControlModifier
            if mods == ctrl and key == Qt.Key_Tab:
                self._window._next_tab()
                return True          # swallow — don't pass to QTabWidget
            if (mods == (ctrl | Qt.ShiftModifier)) and key == Qt.Key_Tab:
                self._window._prev_tab()
                return True
        return False


class MainWindow(QMainWindow):
    def __init__(self, plugins, context):
        super().__init__()

        self.context = context
        self.plugins = plugins

        self.setWindowTitle("Adeptus Craftmatica")

        # ── Central widget: header bar + tabs ────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        root.addWidget(self._build_header())

        # Tab widget — setDocumentMode(True) triggers native macOS rendering which
        # ignores all Qt QTabBar stylesheets, so we leave it off and style directly.
        self.tabs = QTabWidget()
        self.tabs.setElideMode(Qt.ElideNone)
        _nav_tb = self.tabs.tabBar()
        _nav_tb.setExpanding(False)
        _nav_tb.setUsesScrollButtons(True)
        _nav_tb.setElideMode(Qt.ElideNone)
        _nav_tb.setStyleSheet("""
            QTabBar::tab {
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 500;
                min-width: 0;
                max-width: 9999px;
                border: none;
                border-radius: 5px;
                margin: 4px 2px;
                background: transparent;
                color: #606060;
            }
            QTabBar::tab:selected {
                background: #0078d4;
                color: #ffffff;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background: #222222;
                color: #909090;
            }
        """)
        root.addWidget(self.tabs, stretch=1)

        # ── Floating search panel (legacy — kept for compatibility) ──────────────
        self._search_panel = GlobalSearchPanel(context, parent=central)
        self._search_panel.result_activated.connect(self._on_search_result)

        # ── Command Palette ────────────────────────────────────────────────────
        self._palette = CommandPalette(context, parent=central)

        # ── Load plugin UIs ───────────────────────────────────────────────────
        self._load_plugins()

        # ── Subscribe to cross-plugin navigation events ───────────────────────
        self._subscribe_navigation()

        # ── Menu bar ──────────────────────────────────────────────────────────
        self._setup_menu()

        # ── Register base commands in the palette ─────────────────────────────
        QTimer.singleShot(0, self._register_commands)

        # ── Keyboard shortcuts ────────────────────────────────────────────────
        # Ctrl+K → command palette.  Keep as a QShortcut (not in menu) so it
        # doesn't conflict with any menu-registered shortcut.
        self._sc_palette = QShortcut(QKeySequence("Ctrl+K"), self)
        self._sc_palette.activated.connect(self._toggle_palette)
        # Escape → close all overlays (not in menu)
        self._sc_esc = QShortcut(QKeySequence("Escape"), self)
        self._sc_esc.activated.connect(self._close_all_overlays)

        # Ctrl+Tab / Ctrl+Shift+Tab — QTabWidget eats these internally so we
        # intercept them at the application level via an event filter instead
        # of using QShortcut (which fires AFTER the widget handler).
        self._tab_cycle_filter = _TabCycleFilter(self)
        QApplication.instance().installEventFilter(self._tab_cycle_filter)

        # NOTE: Ctrl+1-9, Ctrl+0, Ctrl+N, Ctrl+E, Ctrl+P are registered as
        # QAction shortcuts on the menu bar (in _setup_menu / _rebuild_go_menu).
        # Do NOT add duplicate QShortcut objects for the same keys — Qt will
        # see both registrations and mark the shortcut as "ambiguous", silently
        # disabling both.

        # ── Premium UX: attach toast manager + tab fade ───────────────────────
        QTimer.singleShot(0, self._setup_premium_ux)

        # Fade in the first visible tab when it's shown
        self.tabs.currentChanged.connect(self._on_tab_changed)

    # ── Premium UX setup ──────────────────────────────────────────────────────

    def _setup_premium_ux(self) -> None:
        """Attach the toast manager and apply first-load polish."""
        try:
            ToastManager.instance().attach(self.centralWidget())
        except Exception:
            pass

    def _on_tab_changed(self, index: int) -> None:
        """Gently fade-in the incoming tab's widget; persist last active plugin."""
        try:
            widget = self.tabs.widget(index)
            if widget:
                fade_in(widget, duration=180)
                # Persist last active plugin tab for session resume
                plugin_id = widget.property("plugin_id")
                if plugin_id:
                    settings = (
                        self.context.services.get("settings")
                        if self.context else None
                    )
                    if settings:
                        try:
                            settings.set("app.last_plugin_tab", plugin_id)
                        except Exception:
                            pass
        except Exception:
            pass

    # ── Command palette ────────────────────────────────────────────────────────

    def _register_commands(self) -> None:
        """Register all base navigation / create / tool commands in the palette."""
        reg = CommandRegistry.instance()

        # ── Navigate ──────────────────────────────────────────────────────────
        nav_plugins = [
            ("go_dashboard",       "Go to Dashboard",       "🏠", "dashboard"),
            ("go_projects",        "Go to Projects",        "📋", "project_tracker"),
            ("go_paints",          "Go to Paint Tracker",   "🎨", "paint_tracker"),
            ("go_models",          "Go to Model Tracker",   "🗿", "model_tracker"),
            ("go_campaigns",       "Go to Campaign Tracker","⚔", "campaign_tracker"),
            ("go_army",            "Go to Army Builder",    "🛡", "army_builder"),
            ("go_paint_scheme",    "Go to Paint Schemes",   "🖌", "paint_scheme"),
            ("go_calendar",        "Go to Calendar",        "📅", "calendar"),
        ]
        for i, (cmd_id, title, icon, plugin_id) in enumerate(nav_plugins):
            sc = f"Ctrl+{i + 1}" if i < 9 else ""
            reg.register(PaletteCommand(
                id=cmd_id, title=title, icon=icon,
                category="Navigate",
                shortcut=sc,
                action=lambda pid=plugin_id: self._navigate_to_plugin(pid),
            ))

        # ── Create ────────────────────────────────────────────────────────────
        create_cmds = [
            ("new_project",  "New Project",   "📁", "project_tracker",  "Ctrl+N"),
            ("add_paint",    "Add Paint",     "🎨", "paint_tracker",    ""),
            ("new_campaign", "New Campaign",  "⚔", "campaign_tracker", ""),
            ("new_army",     "New Army",      "🛡", "army_builder",     ""),
            ("new_model",    "New Model",     "🗿", "model_tracker",    ""),
        ]
        for cmd_id, title, icon, plugin_id, sc in create_cmds:
            reg.register(PaletteCommand(
                id=cmd_id, title=title, icon=icon,
                subtitle="Open creation dialog",
                category="Create",
                shortcut=sc,
                action=lambda pid=plugin_id: self._quick_create_in(pid),
            ))

        # ── Tools ─────────────────────────────────────────────────────────────
        tool_cmds = [
            ("open_settings",  "Settings",          "⚙",  self._open_settings,      ""),
            ("open_theme",     "Theme Manager",     "🎨", self._open_theme_editor,  "Ctrl+Shift+T"),
            ("open_plugins",   "Manage Plugins",    "🔌", self._open_plugin_manager,"Ctrl+Shift+P"),
            ("open_export",    "Export / Reports",  "📤", self._open_export,         "Ctrl+E"),
            ("open_github",    "The Forge",         "⚒",  self._open_forge,         "Ctrl+Shift+G"),
        ]
        for cmd_id, title, icon, action, sc in tool_cmds:
            reg.register(PaletteCommand(
                id=cmd_id, title=title, icon=icon,
                category="Tools",
                shortcut=sc,
                action=action,
            ))

        # Build the Go menu now that tabs are loaded
        self._rebuild_go_menu()

    def _rebuild_go_menu(self) -> None:
        """
        Repopulate the Go menu to match the *current* tab order.

        Ctrl+1 always means "the tab currently at position 1", not a
        hard-coded plugin.  Called after initial load and after every
        apply_layout() so the menu stays accurate when the user rearranges
        or hides tabs in Plugin Manager.
        """
        menu = getattr(self, "_go_menu", None)
        if menu is None:
            return

        menu.clear()

        # ── Command Palette (always first) ────────────────────────────────────
        cp_act = menu.addAction("Command Palette…")
        cp_act.setShortcut(QKeySequence("Ctrl+P"))
        cp_act.triggered.connect(self._toggle_palette)

        menu.addSeparator()

        # ── One entry per visible tab, up to 10 ──────────────────────────────
        # Ctrl+1 → tab 1 (index 0) … Ctrl+9 → tab 9 (index 8)
        # Ctrl+0 → tab 10 (index 9)  — mirrors the keyboard row naturally
        for i in range(min(self.tabs.count(), 10)):
            label = self.tabs.tabText(i)
            # 0-key maps to position 10
            key = str(i + 1) if i < 9 else "0"
            act = menu.addAction(label)
            act.setShortcut(QKeySequence(f"Ctrl+{key}"))
            act.triggered.connect(lambda _, idx=i: self._go_to_tab(idx))

        menu.addSeparator()

        # ── Tab cycling (always last) ─────────────────────────────────────────
        prev_act = menu.addAction("Previous Tab")
        prev_act.setShortcut(QKeySequence("Ctrl+Shift+Tab"))
        prev_act.triggered.connect(self._prev_tab)

        next_act = menu.addAction("Next Tab")
        next_act.setShortcut(QKeySequence("Ctrl+Tab"))
        next_act.triggered.connect(self._next_tab)

        self._go_menu_built = True

    def _toggle_palette(self) -> None:
        """Close search panel if open, then toggle the command palette."""
        self._search_panel.close_panel()
        self._palette._reposition()
        self._palette.toggle()

    def _close_all_overlays(self) -> None:
        self._palette.close_palette()
        self._search_panel.close_panel()

    # ── Navigation helpers ─────────────────────────────────────────────────────

    # Fallback aliases: if a plugin isn't loaded, try its sibling version.
    _PLUGIN_ALIASES: dict[str, list[str]] = {
        "paint_tracker":          ["paint_tracker_v2"],
        "paint_tracker_v2":       ["paint_tracker"],
        "materials_tracker":      ["materials_tracker_v2"],
        "materials_tracker_v2":   ["materials_tracker"],
        "army_builder":           ["army_builder_v2"],
        "army_builder_v2":        ["army_builder"],
        "campaign_tracker":       ["campaign_tracker_v2"],
        "campaign_tracker_v2":    ["campaign_tracker"],
    }

    def _navigate_to_plugin(self, plugin_id: str) -> None:
        """Switch to the tab for the given plugin_id.

        If the primary plugin is not loaded, tries registered aliases so that
        commands like "Go to Paint Tracker" work whether v1 or v2 is active.
        """
        candidates = [plugin_id] + self._PLUGIN_ALIASES.get(plugin_id, [])
        for pid in candidates:
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if w and w.property("plugin_id") == pid:
                    self.tabs.setCurrentIndex(i)
                    return

    def _go_to_tab(self, idx: int) -> None:
        if 0 <= idx < self.tabs.count():
            self.tabs.setCurrentIndex(idx)

    def _next_tab(self) -> None:
        n = self.tabs.count()
        if n:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % n)

    def _prev_tab(self) -> None:
        n = self.tabs.count()
        if n:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % n)

    # ── Quick create ───────────────────────────────────────────────────────────

    def _quick_create(self) -> None:
        """Context-aware Ctrl+N: delegate to whichever plugin is active."""
        w = self.tabs.currentWidget()
        plugin_id = w.property("plugin_id") if w else ""
        self._quick_create_in(plugin_id or "project_tracker")

    def _quick_create_in(self, plugin_id: str) -> None:
        """Navigate to plugin and fire its handle_quick_create method if available.

        Tries the primary plugin_id first, then any registered aliases, so
        'Add Paint' works whether paint_tracker v1 or v2 is active.
        """
        self._navigate_to_plugin(plugin_id)

        # Resolve the actual tab that is now current — it may be an alias
        w = self.tabs.currentWidget()
        active_pid = w.property("plugin_id") if w else plugin_id

        if w and hasattr(w, "handle_quick_create"):
            try:
                w.handle_quick_create()
            except Exception as e:
                print(f"[MainWindow] quick_create error in {active_pid}: {e}")
        else:
            # Fallback: emit event so the plugin can intercept it
            bus = getattr(self.context, "event_bus", None)
            if bus:
                try:
                    bus.emit("quick_create", {"plugin_id": active_pid})
                except Exception:
                    pass

    # ── Export ─────────────────────────────────────────────────────────────────

    def _open_export(self) -> None:
        dlg = ExportDialog(self.context, self)
        dlg.exec()

    # ── Header bar ────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        # Pull theme tokens if available, otherwise fall back to defaults
        tm = self.context.services.get("theme_manager") if self.context else None
        accent   = tm.token("accent")   if tm else "#0078d4"
        hdr_bg   = tm.token("header_bg") if tm else "#141414"
        border   = tm.token("border")   if tm else "#2a2a2a"
        bg_raised = tm.token("bg_raised") if tm else "#1e1e1e"
        text_dim  = tm.token("text_dim")  if tm else "#484848"

        self._header_bar = QWidget()
        self._header_bar.setObjectName("appHeader")
        self._header_bar.setFixedHeight(48)
        self._header_bar.setStyleSheet(
            f"QWidget#appHeader {{ background-color: {hdr_bg}; "
            f"border-bottom: 1px solid {border}; }}"
        )

        lay = QHBoxLayout(self._header_bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)

        # App name / logo text
        self._logo_label = QLabel("⚙ Adeptus Craftmatica")
        self._logo_label.setStyleSheet(
            f"color: {accent}; font-size: 15px; font-weight: 700; "
            "letter-spacing: 0.5px; background: transparent;"
        )
        lay.addWidget(self._logo_label)

        lay.addStretch()

        # Search trigger button
        self._search_wrap = QPushButton("  ⌕   Commands & Search…")
        self._search_wrap.setObjectName("searchTrigger")
        self._search_wrap.setFixedHeight(34)
        self._search_wrap.setMinimumWidth(200)
        self._search_wrap.setMaximumWidth(340)
        self._search_wrap.setCursor(Qt.PointingHandCursor)
        self._search_wrap.setToolTip(
            "Open Command Palette — navigate, create, and search everything  (Ctrl+K / Ctrl+P)"
        )
        self._search_wrap.setStyleSheet(f"""
            QPushButton#searchTrigger {{
                background: {bg_raised};
                border: 1px solid {border};
                border-radius: 7px;
                color: {text_dim};
                font-size: 13px;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton#searchTrigger:hover {{
                border-color: {accent};
                color: {tm.token("text_lo") if tm else "#686868"};
            }}
        """)
        self._search_wrap.clicked.connect(self._toggle_palette)
        self._search_btn = self._search_wrap   # keep alias for positioning
        lay.addWidget(self._search_wrap)

        self._hint_lbl = QLabel("Ctrl+K")
        self._hint_lbl.setStyleSheet(
            f"color: {border}; font-size: 10px; background: {hdr_bg};"
            f" border: 1px solid {border}; border-radius: 3px; padding: 2px 6px;"
        )
        lay.addWidget(self._hint_lbl)

        # If ThemeManager is available, update header when theme changes
        if tm:
            tm.theme_changed.connect(self._on_theme_changed)

        return self._header_bar

    def _on_theme_changed(self, theme_id: str):
        """
        Refresh all header-bar inline styles after a theme switch.

        The global QSS (applied to QApplication) already handles every widget
        that uses standard object names / classes.  The header bar widgets have
        additional inline styles baked in at build time (colors that depend on
        specific theme tokens) — those are not covered by the global sheet and
        must be refreshed here explicitly.
        """
        tm = self.context.services.get("theme_manager")
        if not tm:
            return

        accent    = tm.token("accent")
        hdr_bg    = tm.token("header_bg")
        border    = tm.token("border")
        bg_raised = tm.token("bg_raised")
        bg_input  = tm.token("bg_input")
        text_dim  = tm.token("text_dim")
        text_lo   = tm.token("text_lo")

        # Header bar background
        self._header_bar.setStyleSheet(
            f"QWidget#appHeader {{ background-color: {hdr_bg}; "
            f"border-bottom: 1px solid {border}; }}"
        )

        # Logo / app-name label
        self._logo_label.setStyleSheet(
            f"color: {accent}; font-size: 15px; font-weight: 700; "
            "letter-spacing: 0.5px; background: transparent;"
        )

        # Search trigger button
        self._search_wrap.setStyleSheet(f"""
            QPushButton#searchTrigger {{
                background: {bg_raised};
                border: 1px solid {border};
                border-radius: 7px;
                color: {text_dim};
                font-size: 13px;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton#searchTrigger:hover {{
                border-color: {accent};
                color: {text_lo};
            }}
        """)

        # Ctrl+K hint badge
        self._hint_lbl.setStyleSheet(
            f"color: {border}; font-size: 10px; background: {hdr_bg};"
            f" border: 1px solid {border}; border-radius: 3px; padding: 2px 6px;"
        )

    # ── Plugin loading ─────────────────────────────────────────────────────────

    def _load_plugins(self):
        settings = self.context.services.get("settings") if self.context else None
        labels: dict = {}
        if settings:
            try:
                labels = settings.get("plugin_layout.labels", {}) or {}
            except Exception:
                labels = {}

        for plugin in self.plugins:
            try:
                widget = plugin.get_ui()
                if not widget:
                    continue
                plugin_id = getattr(plugin, "plugin_id", "")
                default_name = getattr(plugin, "display_name", plugin.__class__.__name__)
                tab_name = labels.get(plugin_id) or default_name

                # Tag widget with plugin_id for reliable navigation after rename
                widget.setProperty("plugin_id", plugin_id)

                self.tabs.addTab(widget, tab_name)
                print(f"[UI] Loaded tab: {tab_name} (id={plugin_id})")
            except Exception as e:
                print(f"[UI ERROR] Failed to load plugin UI: {e}")

        self._apply_saved_tab_order()
        # Always start on the Dashboard tab (index 0 after ordering)
        self.tabs.setCurrentIndex(0)

    def _apply_saved_tab_order(self):
        """
        Reorder tabs to match the saved order from settings.
        Dashboard is always pinned to position 0.
        Tabs not mentioned in the saved order keep their natural position.
        """
        settings = self.context.services.get("settings") if self.context else None
        saved_order: list = []
        if settings:
            try:
                saved_order = settings.get("plugin_layout.order", []) or []
            except Exception:
                saved_order = []

        # Build widget → plugin_id map for current tabs
        widget_by_id: dict = {}
        label_by_id:  dict = {}
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            pid = w.property("plugin_id") if w else ""
            if pid:
                widget_by_id[pid] = w
                label_by_id[pid]  = self.tabs.tabText(i)

        # Determine desired order: saved_order first, then anything not mentioned
        all_ids = list(widget_by_id.keys())
        ordered = [pid for pid in saved_order if pid in widget_by_id]
        ordered += [pid for pid in all_ids if pid not in ordered]

        # Ensure dashboard is always first
        if "dashboard" in ordered and ordered[0] != "dashboard":
            ordered.remove("dashboard")
            ordered.insert(0, "dashboard")

        # Remove all tabs and re-insert in desired order
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for pid in ordered:
            w = widget_by_id[pid]
            self.tabs.addTab(w, label_by_id[pid])
        self.tabs.blockSignals(False)
        self.tabs.setCurrentIndex(0)

    def apply_layout(self, order: list[str], labels: dict[str, str]) -> None:
        """
        Live-apply a new tab order and label set.
        Called by PluginManagerDialog after the user clicks Apply.
        Also persists the changes to settings.
        """
        settings = self.context.services.get("settings") if self.context else None

        # Build current widget map
        widget_by_id: dict = {}
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            pid = w.property("plugin_id") if w else ""
            if pid:
                widget_by_id[pid] = w

        # Ensure dashboard is always first
        ordered = [pid for pid in order if pid in widget_by_id]
        ordered += [pid for pid in widget_by_id if pid not in ordered]
        if "dashboard" in ordered and ordered[0] != "dashboard":
            ordered.remove("dashboard")
            ordered.insert(0, "dashboard")

        # Rebuild tabs
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for pid in ordered:
            w = widget_by_id[pid]
            plugin = next((p for p in self.plugins
                           if getattr(p, "plugin_id", "") == pid), None)
            default_name = getattr(plugin, "display_name", pid) if plugin else pid
            tab_name = labels.get(pid) or default_name
            self.tabs.addTab(w, tab_name)
        self.tabs.blockSignals(False)
        self.tabs.setCurrentIndex(0)

        # Sync the Go menu so Ctrl+1-9 reflects the new tab positions immediately
        self._rebuild_go_menu()

        # Persist — save the FULL requested order (including unloaded plugins like
        # project_tracker that have no tab yet) so their position is remembered.
        # `order` comes straight from the dialog; `ordered` is the filtered/live set.
        full_order = list(order)  # preserve every plugin_id the dialog returned
        # Make sure any currently-loaded tabs that weren't in the dialog's list
        # are appended at the end (shouldn't normally happen, but be safe).
        for pid in widget_by_id:
            if pid not in full_order:
                full_order.append(pid)
        if settings:
            try:
                settings.set("plugin_layout.order", full_order)
                settings.set("plugin_layout.labels", labels)
            except Exception as e:
                print(f"[UI] Failed to persist plugin layout: {e}")

    def _subscribe_navigation(self):
        """Subscribe to event-bus navigation events emitted by dashboard widgets."""
        bus = getattr(self.context, "event_bus", None)
        if not bus:
            return
        try:
            bus.subscribe("dashboard_navigate", self._on_dashboard_navigate)
        except Exception as e:
            print(f"[UI] Could not subscribe to dashboard_navigate: {e}")

    # ── Cross-plugin navigation ────────────────────────────────────────────────

    def _on_dashboard_navigate(self, payload: dict | None = None):
        """Switch to the tab whose plugin_id property matches payload['plugin_id'].
        Uses _navigate_to_plugin so alias mappings (v1↔v2) are respected and
        navigation still works after a tab is renamed.
        If payload also contains 'project_id', emits project_selected after switching."""
        if not payload:
            return
        target_id = payload.get("plugin_id", "")
        if not target_id:
            return

        # Use the alias-aware helper — handles campaign_tracker↔v2, army_builder↔v2, etc.
        self._navigate_to_plugin(target_id)

        # Select a specific project if the payload carries one
        project_id = payload.get("project_id")
        # Resolve the canonical id of whichever tab actually got focused
        resolved_id = target_id
        candidates = [target_id] + self._PLUGIN_ALIASES.get(target_id, [])
        for pid in candidates:
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if w and w.property("plugin_id") == pid:
                    resolved_id = pid
                    break

        if project_id is not None and resolved_id == "project_tracker":
            from PySide6.QtCore import QTimer
            bus = getattr(self.context, "event_bus", None)
            if bus:
                QTimer.singleShot(
                    50,
                    lambda _pid=project_id: bus.emit("project_selected", {"id": _pid}),
                )

    # ── Menu setup ─────────────────────────────────────────────────────────────

    def _setup_menu(self):
        menubar = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────────
        file_menu = menubar.addMenu("File")
        new_action = file_menu.addAction("New Item")
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self._quick_create)
        file_menu.addSeparator()
        export_action = file_menu.addAction("Export / Reports…")
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._open_export)
        file_menu.addSeparator()
        settings_action = file_menu.addAction("Settings")
        settings_action.triggered.connect(self._open_settings)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

        # ── Go ────────────────────────────────────────────────────────────────
        # Store reference so _rebuild_go_menu() can repopulate it live.
        self._go_menu = menubar.addMenu("Go")
        # Populate once now — _register_commands() deferred timer will also
        # trigger _rebuild_go_menu() after tabs are loaded.
        self._go_menu_built = False   # flag: populated at least once

        # ── View ──────────────────────────────────────────────────────────────
        view_menu = menubar.addMenu("View")
        theme_action = view_menu.addAction("Theme Manager…")
        theme_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        theme_action.triggered.connect(self._open_theme_editor)
        view_menu.addSeparator()
        plugins_action = view_menu.addAction("Manage Plugins…")
        plugins_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        plugins_action.triggered.connect(self._open_plugin_manager)

        # ── Tools ─────────────────────────────────────────────────────────────
        tools_menu = menubar.addMenu("Tools")
        github_action = tools_menu.addAction("The Forge…")
        github_action.setShortcut(QKeySequence("Ctrl+Shift+G"))
        github_action.setToolTip(
            "Browse the community library, contribute your collection, or import from GitHub"
        )
        github_action.triggered.connect(self._open_forge)

    # ── Search panel positioning ────────────────────────────────────────────────

    def _position_search_panel(self):
        """Position the floating panel centred below the search button."""
        panel = self._search_panel
        btn = self._search_wrap
        bottom_left = btn.mapTo(self.centralWidget(), btn.rect().bottomLeft())
        panel_x = bottom_left.x() - (panel.width() - btn.width()) // 2
        panel_y = bottom_left.y() + 6
        max_x = self.centralWidget().width() - panel.width() - 10
        panel.move(max(10, min(panel_x, max_x)), panel_y)

    def _toggle_search(self):
        self._position_search_panel()
        self._search_panel.toggle()

    def _close_search(self):
        self._search_panel.close_panel()

    def showEvent(self, event):
        super().showEvent(event)
        # Hook screen-change signal once the native window handle exists
        handle = self.windowHandle()
        if handle and not getattr(self, "_screen_hook_connected", False):
            try:
                handle.screenChanged.connect(self._on_screen_changed)
                self._screen_hook_connected = True
            except Exception:
                pass

    def _on_screen_changed(self, _screen):
        """Re-apply all styles when the window is dragged to a different monitor."""
        # Defer slightly — Qt needs one event-loop cycle to finish remapping
        # the native window handle before stylesheets can be re-evaluated.
        QTimer.singleShot(50, self._do_screen_refresh)

    def _do_screen_refresh(self):
        app = QApplication.instance()
        if not app:
            return

        # 1. Toggle the global QSS to flush Qt's style cache for every widget.
        qss = app.styleSheet()
        app.setStyleSheet("")
        app.setStyleSheet(qss)

        # 2. Emit theme_changed so inline-styled dashboard widgets fully rebuild.
        tm = self.context.services.get("theme_manager") if self.context else None
        if tm:
            try:
                tm.theme_changed.emit(tm.current_theme_id)
            except Exception:
                pass

        # 3. Update every widget — self.update() only repaints the window chrome.
        for widget in app.allWidgets():
            try:
                if widget.isVisible():
                    widget.update()
            except Exception:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._search_panel.isVisible():
            self._position_search_panel()
        if self._palette.isVisible():
            self._palette._reposition()

    # ── Search result navigation ────────────────────────────────────────────────

    def _on_search_result(self, category: str, payload: dict):
        """Navigate to the right tab when a search result is clicked.
        Uses plugin_id properties so this works even after tabs are renamed."""
        category_to_plugin_id = {
            "Projects":    "project_tracker",
            "Paints":      "paint_tracker",
            "Models":      "model_tracker",
            "Schemes":     "paint_scheme",
            "Armies":      "army_builder",
            "Campaigns":   "campaign_tracker",
            "Characters":  "campaign_tracker",
            "Battles":     "campaign_tracker",
            "Events":      "calendar",
        }
        target_id = category_to_plugin_id.get(category)
        if not target_id:
            return
        # Use _navigate_to_plugin so alias fallbacks (e.g. paint_tracker_v2) work
        self._navigate_to_plugin(target_id)

        # For Projects: deep-link directly to the specific project
        if category == "Projects" and payload.get("id") and self.context:
            self.context.event_bus.emit("dashboard_navigate", {
                "plugin_id":  "project_tracker",
                "project_id": payload["id"],
            })

    # ── Actions ────────────────────────────────────────────────────────────────

    def _open_plugin_manager(self):
        dialog = PluginManagerDialog(self.context, self.plugins, self)
        if not dialog.exec():
            return

        order, labels, disabled = dialog.get_result()
        settings = self.context.services.get("settings") if self.context else None
        pm       = self.context.services.get("plugin_manager") if self.context else None

        # ── Diff against previously persisted state ───────────────────────────
        prev_disabled: list = []
        if settings:
            try:
                prev_disabled = settings.get("plugin_layout.disabled", []) or []
            except Exception:
                pass

        prev_disabled_set = set(prev_disabled)
        new_disabled_set  = set(disabled)
        newly_disabled    = new_disabled_set - prev_disabled_set
        newly_enabled     = prev_disabled_set - new_disabled_set

        # ── 1. Live-deactivate newly disabled plugins ─────────────────────────
        for plugin_id in list(newly_disabled):
            # Remove tab first so the UI reacts immediately
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if w and w.property("plugin_id") == plugin_id:
                    self.tabs.removeTab(i)
                    break

            # Delegate the rest to PluginManager (deactivate + registry cleanup)
            if pm:
                pm.unload_plugin(plugin_id)

            # Mirror the change in MainWindow's own list
            self.plugins = [p for p in self.plugins
                            if getattr(p, "plugin_id", "") != plugin_id]

        # ── 2. Live-enable newly re-enabled plugins ───────────────────────────
        failed_enable: list[str] = []
        for plugin_id in list(newly_enabled):
            # Already live (edge case: disabled then re-enabled in same session
            # before Apply was clicked — nothing to do)
            if any(getattr(p, "plugin_id", "") == plugin_id for p in self.plugins):
                continue

            if pm is None:
                failed_enable.append(plugin_id)
                continue

            # PluginManager handles module import + activate() — returns the
            # ready plugin object, or None if something went wrong.
            plugin = pm.load_plugin(plugin_id)
            if plugin is None:
                failed_enable.append(plugin_id)
                continue

            # Mirror in MainWindow's list
            self.plugins.append(plugin)

            # Add its tab so apply_layout can slot it into the right position
            try:
                widget = plugin.get_ui()
                if widget:
                    pid      = getattr(plugin, "plugin_id", plugin_id)
                    tab_name = labels.get(pid) or getattr(plugin, "display_name", pid)
                    widget.setProperty("plugin_id", pid)
                    self.tabs.addTab(widget, tab_name)
                    print(f"[UI] Re-enabled tab: {tab_name}  (id={pid})")
            except Exception as e:
                print(f"[UI] Failed to add tab for re-enabled plugin '{plugin_id}': {e}")

        # ── 3. Reorder / relabel all surviving tabs ───────────────────────────
        self.apply_layout(order, labels)

        # ── 4. Persist final enabled/disabled state ───────────────────────────
        if settings:
            try:
                settings.set("plugin_layout.disabled", disabled)
            except Exception as e:
                print(f"[UI] Failed to persist disabled plugins: {e}")

        # ── 5. Report any plugins that failed to load ─────────────────────────
        if failed_enable:
            names = []
            for pid in failed_enable:
                name = pid
                if pm and hasattr(pm, "all_manifests") and pid in pm.all_manifests:
                    _, mdata = pm.all_manifests[pid]
                    name = mdata.get("name", pid)
                names.append(name)
            QMessageBox.warning(
                self,
                "Plugin Load Failed",
                "The following plugin(s) could not be loaded:\n\n"
                + "\n".join(f"  •  {n}" for n in names)
                + "\n\nCheck the console for details.",
            )

    def _open_settings(self):
        dialog = SettingsDialog(self.context, self)
        dialog.exec()

    def _open_theme_editor(self):
        tm = self.context.services.get("theme_manager") if self.context else None
        if not tm:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Theme Manager", "Theme manager is not available.")
            return
        dialog = ThemeEditorDialog(self.context, self)
        dialog.exec()

    def _open_forge(self):
        dialog = TheForgeDialog(self.context, self)
        dialog.exec()
