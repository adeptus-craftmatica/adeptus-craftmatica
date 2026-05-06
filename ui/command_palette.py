# ui/command_palette.py
"""
Command Palette — the power-user hub for Adeptus Craftmatica.

Triggered via Ctrl+P (or Ctrl+K when search panel is already open).
Provides:
  • Keyboard-navigable command list (navigate, create, tools)
  • Inline content search (projects, paints, models, armies, campaigns)
  • Recent-command memory (last 8 actions, persisted in-session)
  • Fuzzy title matching as the user types

Usage (once, in MainWindow.__init__):
    from ui.command_palette import CommandPalette, CommandRegistry
    self._palette = CommandPalette(context, parent=central)
    CommandRegistry.instance().register_command(...)

Trigger:
    self._palette.toggle()

Register commands from anywhere:
    from ui.command_palette import CommandRegistry
    CommandRegistry.instance().register_command(PaletteCommand(
        id="go_projects", title="Go to Projects",
        icon="📋", category="Navigate",
        action=lambda: ...
    ))
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QScrollArea, QGraphicsDropShadowEffect, QApplication,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PaletteCommand:
    """One entry in the command palette."""
    id:       str
    title:    str
    icon:     str       = "›"
    subtitle: str       = ""
    category: str       = "Actions"
    shortcut: str       = ""
    keywords: list      = field(default_factory=list)
    action:   Optional[Callable] = None

    def matches(self, needle: str) -> bool:
        """True if needle fuzzy-matches title, subtitle, or keywords."""
        if not needle:
            return True
        n = needle.lower()
        corpus = " ".join([self.title, self.subtitle] + self.keywords).lower()
        # Allow subsequence matching: every char in needle must appear in order
        it = iter(corpus)
        return all(c in it for c in n)

    def score(self, needle: str) -> int:
        """Higher = better match. Used for sorting filtered results."""
        if not needle:
            return 0
        n = needle.lower()
        t = self.title.lower()
        if t.startswith(n):
            return 100
        if n in t:
            return 80
        if n in self.subtitle.lower():
            return 50
        return 10


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

class CommandRegistry:
    """
    Singleton registry of all palette commands.

    Commands registered here appear in the palette automatically.
    Plugins can register their own commands during activation.
    """

    _instance: "CommandRegistry | None" = None

    def __init__(self):
        self._commands: dict[str, PaletteCommand] = {}

    @classmethod
    def instance(cls) -> "CommandRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, cmd: PaletteCommand) -> None:
        self._commands[cmd.id] = cmd

    def unregister(self, cmd_id: str) -> None:
        self._commands.pop(cmd_id, None)

    def all_commands(self) -> list[PaletteCommand]:
        return list(self._commands.values())

    def by_category(self) -> dict[str, list[PaletteCommand]]:
        result: dict[str, list] = {}
        for cmd in self._commands.values():
            result.setdefault(cmd.category, []).append(cmd)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Category ordering + colours
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORY_ORDER = ["Recent", "Navigate", "Create", "Tools", "Results"]

_CATEGORY_COLOR: dict[str, str] = {
    "Recent":   "#888888",
    "Navigate": "#3b9eff",
    "Create":   "#22c55e",
    "Tools":    "#f59e0b",
    "Results":  "#a855f7",
}


# ─────────────────────────────────────────────────────────────────────────────
# Row widgets
# ─────────────────────────────────────────────────────────────────────────────

class _PaletteRow(QFrame):
    activated = Signal()

    def __init__(self, cmd: PaletteCommand, parent=None):
        super().__init__(parent)
        self._cmd = cmd
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(46)
        self._selected = False
        self._apply_style(False)
        self._build(cmd)

    def _build(self, cmd: PaletteCommand) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 14, 0)
        lay.setSpacing(12)

        # Icon
        icon_lbl = QLabel(cmd.icon)
        icon_lbl.setFixedWidth(22)
        icon_lbl.setAlignment(Qt.AlignCenter)
        color = _CATEGORY_COLOR.get(cmd.category, "#666")
        icon_lbl.setStyleSheet(
            f"font-size: 15px; color: {color}; background: transparent;"
        )
        lay.addWidget(icon_lbl)

        # Text block
        text = QVBoxLayout()
        text.setSpacing(1)
        text.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(cmd.title)
        title_lbl.setStyleSheet(
            "color: #e0e0e0; font-size: 13px; font-weight: 600; background: transparent;"
        )
        text.addWidget(title_lbl)

        if cmd.subtitle:
            sub_lbl = QLabel(cmd.subtitle)
            sub_lbl.setStyleSheet(
                "color: #555; font-size: 11px; background: transparent;"
            )
            text.addWidget(sub_lbl)

        lay.addLayout(text, stretch=1)

        # Shortcut badge
        if cmd.shortcut:
            sc = QLabel(cmd.shortcut)
            sc.setStyleSheet(
                "color: #3a3a3a; font-size: 10px; background: #1e1e1e;"
                " border: 1px solid #2a2a2a; border-radius: 4px; padding: 2px 7px;"
            )
            lay.addWidget(sc)

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self._apply_style(selected)

    def _apply_style(self, selected: bool) -> None:
        if selected:
            color = _CATEGORY_COLOR.get(self._cmd.category, "#0078d4")
            self.setStyleSheet(
                f"QFrame {{ background: {color}18; border-left: 2px solid {color};"
                f" border-radius: 5px; }}"
            )
        else:
            self.setStyleSheet(
                "QFrame { background: transparent; border-radius: 5px; }"
            )

    def mousePressEvent(self, ev: QKeyEvent) -> None:
        if ev.button() == Qt.LeftButton:
            self.activated.emit()

    def enterEvent(self, ev) -> None:
        if not self._selected:
            self.setStyleSheet(
                "QFrame { background: #222; border-radius: 5px; }"
            )

    def leaveEvent(self, ev) -> None:
        self._apply_style(self._selected)

    @property
    def command(self) -> PaletteCommand:
        return self._cmd


class _SectionDivider(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(24)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        color = _CATEGORY_COLOR.get(label, "#666")
        lbl = QLabel(label.upper())
        lbl.setStyleSheet(
            f"color: {color}; font-size: 9px; font-weight: 700;"
            " letter-spacing: 1.5px; background: transparent;"
        )
        lay.addWidget(lbl)
        lay.addStretch()


# ─────────────────────────────────────────────────────────────────────────────
# Main palette widget
# ─────────────────────────────────────────────────────────────────────────────

class CommandPalette(QFrame):
    """
    Floating command palette widget.

    Attach to the central widget of MainWindow (as a child, for absolute
    positioning). Call toggle() to open/close.
    """

    command_activated = Signal(PaletteCommand)

    _RECENT_MAX = 8

    def __init__(self, context, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx     = context
        self._rows:   list[_PaletteRow] = []
        self._cursor  = -1          # index in self._rows currently selected
        self._recent: deque[str] = deque(maxlen=self._RECENT_MAX)

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._refresh)

        self._build_frame()
        self.hide()

    # ── Frame / chrome ────────────────────────────────────────────────────────

    def _build_frame(self) -> None:
        self.setObjectName("commandPalette")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(580)
        self.setStyleSheet("""
            QFrame#commandPalette {
                background: #161616;
                border: 1px solid #2a2a2a;
                border-radius: 10px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 220))
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(0)

        # ── Input row ─────────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setFrameShape(QFrame.NoFrame)
        input_frame.setFixedHeight(52)
        input_frame.setStyleSheet("QFrame { background: transparent; }")
        ir = QHBoxLayout(input_frame)
        ir.setContentsMargins(16, 0, 16, 0)
        ir.setSpacing(10)

        icon = QLabel("⌕")
        icon.setStyleSheet("font-size: 18px; color: #484848; background: transparent;")
        icon.setFixedWidth(22)
        ir.addWidget(icon)

        self._input = _PaletteInput()
        self._input.setPlaceholderText("Search commands, projects, paints, models…")
        self._input.setFrame(False)
        self._input.setStyleSheet(
            "QLineEdit { background: transparent; border: none;"
            " color: #ebebeb; font-size: 14px; }"
            "QLineEdit::placeholder { color: #353535; }"
        )
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._activate_selected)
        self._input.arrow_up.connect(self._move_up)
        self._input.arrow_down.connect(self._move_down)
        self._input.escape_pressed.connect(self.close_palette)
        ir.addWidget(self._input, stretch=1)

        hint = QLabel("esc")
        hint.setStyleSheet(
            "color: #333; font-size: 10px; background: #1a1a1a;"
            " border: 1px solid #2a2a2a; border-radius: 4px; padding: 2px 7px;"
        )
        ir.addWidget(hint)

        root.addWidget(input_frame)

        # ── Divider ───────────────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet("background: #222; border: none;")
        root.addWidget(div)

        # ── Results scroll area ───────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 4px; }
            QScrollBar::handle:vertical { background: #2a2a2a; border-radius: 2px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._lay = QVBoxLayout(self._content)
        self._lay.setContentsMargins(6, 4, 6, 4)
        self._lay.setSpacing(0)

        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, stretch=1)

    # ── Public API ────────────────────────────────────────────────────────────

    def toggle(self) -> None:
        if self.isVisible():
            self.close_palette()
        else:
            self._open()

    def close_palette(self) -> None:
        self.hide()
        self._input.clear()
        self._cursor = -1

    def record_recent(self, cmd_id: str) -> None:
        """Call after activating a command to bump it to the recent list."""
        if cmd_id in self._recent:
            self._recent.remove(cmd_id)
        self._recent.appendleft(cmd_id)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _open(self) -> None:
        self._reposition()
        self.show()
        self.raise_()
        self._input.setFocus()
        self._input.selectAll()
        self._refresh()

    def _reposition(self) -> None:
        parent = self.parent()
        if not isinstance(parent, QWidget):
            return
        pw, ph = parent.width(), parent.height()
        x = (pw - self.width()) // 2
        y = max(60, int(ph * 0.12))
        self.move(x, y)

    def _on_text_changed(self) -> None:
        self._debounce.start()

    def _refresh(self) -> None:
        needle = self._input.text().strip()
        self._clear_list()
        self._rows = []
        self._cursor = -1

        if not needle:
            self._populate_default()
        else:
            self._populate_filtered(needle)

        self._sync_height()

    # ── Default (empty query) layout ──────────────────────────────────────────

    def _populate_default(self) -> None:
        registry = CommandRegistry.instance()

        # Recent section
        recent_cmds = [
            registry._commands[rid]
            for rid in self._recent
            if rid in registry._commands
        ]
        if recent_cmds:
            self._add_section("Recent")
            for cmd in recent_cmds[:5]:
                self._add_row(cmd)

        # Grouped sections (Navigate, Create, Tools)
        by_cat = registry.by_category()
        for cat in ["Navigate", "Create", "Tools"]:
            cmds = by_cat.get(cat, [])
            if cmds:
                self._add_section(cat)
                for cmd in cmds:
                    self._add_row(cmd)

        if not self._rows:
            self._add_placeholder("No commands registered yet")

        self._lay.addStretch()

    # ── Filtered layout ───────────────────────────────────────────────────────

    def _populate_filtered(self, needle: str) -> None:
        registry = CommandRegistry.instance()

        # Filter and score commands
        matched = [
            (cmd, cmd.score(needle))
            for cmd in registry.all_commands()
            if cmd.matches(needle)
        ]
        matched.sort(key=lambda x: -x[1])

        if matched:
            self._add_section("Commands")
            for cmd, _ in matched[:12]:
                self._add_row(cmd)

        # Content search (async-friendly via try/except)
        content_results = self._search_content(needle)
        if content_results:
            self._add_section("Results")
            for cmd in content_results:
                self._add_row(cmd)

        if not self._rows:
            self._add_placeholder(f'No results for "{needle}"')

        self._lay.addStretch()

        # Auto-select first
        if self._rows:
            self._set_cursor(0)

    # ── Content search ────────────────────────────────────────────────────────

    def _search_content(self, needle: str) -> list[PaletteCommand]:
        """Search all plugin services and return PaletteCommands for results."""
        results: list[PaletteCommand] = []
        n = needle.lower()

        # Projects
        try:
            svc = self._ctx.services.try_get("project_service")
            if svc:
                projects = svc.get_all_projects()
                hits = [p for p in projects
                        if n in p.name.lower()
                        or n in (p.description or "").lower()
                        or n in (p.game_system or "").lower()][:5]
                for p in hits:
                    results.append(PaletteCommand(
                        id=f"_result_project_{p.id}",
                        title=f"{p.icon}  {p.name}",
                        icon="📋",
                        subtitle=f"Project  ·  {p.game_system or 'No system'}  ·  {p.status}",
                        category="Results",
                        action=self._make_project_navigate_action(p.id),
                    ))
        except Exception:
            pass

        # Paints
        try:
            svc = self._ctx.services.try_get("paint_service")
            if svc:
                hits = [p for p in svc.get_all_paints()
                        if n in p.name.lower() or n in p.brand.lower()][:4]
                for p in hits:
                    results.append(PaletteCommand(
                        id=f"_result_paint_{p.id}",
                        title=p.name,
                        icon="🎨",
                        subtitle=f"Paint  ·  {p.brand}  ·  {p.paint_type or ''}",
                        category="Results",
                        action=self._make_navigate_action("paint_tracker"),
                    ))
        except Exception:
            pass

        # Models
        try:
            svc = self._ctx.services.try_get("model_service")
            if svc:
                from plugins.model_tracker.models import ModelFilter
                hits = svc.search_models(ModelFilter(search_text=needle))[:4]
                for m in hits:
                    results.append(PaletteCommand(
                        id=f"_result_model_{m.id}",
                        title=m.name,
                        icon="🗿",
                        subtitle=f"Model  ·  {m.faction or ''}  ·  {m.status}",
                        category="Results",
                        action=self._make_navigate_action("model_tracker"),
                    ))
        except Exception:
            pass

        # Armies
        try:
            svc = self._ctx.services.try_get("army_service")
            if svc:
                from plugins.army_builder.models import ArmyFilter
                hits = svc.search_armies(ArmyFilter(search_text=needle))[:3]
                for a in hits:
                    results.append(PaletteCommand(
                        id=f"_result_army_{a.id}",
                        title=a.name,
                        icon="⚔",
                        subtitle=f"Army  ·  {a.faction or ''}",
                        category="Results",
                        action=self._make_navigate_action("army_builder"),
                    ))
        except Exception:
            pass

        return results[:14]

    def _make_navigate_action(self, plugin_id: str) -> Callable:
        def _action():
            bus = getattr(self._ctx, "event_bus", None)
            if bus:
                bus.emit("dashboard_navigate", {"plugin_id": plugin_id})
        return _action

    def _make_project_navigate_action(self, project_id) -> Callable:
        """Navigate to a specific project, not just the plugin root."""
        def _action():
            bus = getattr(self._ctx, "event_bus", None)
            if bus:
                bus.emit("dashboard_navigate", {
                    "plugin_id":  "project_tracker",
                    "project_id": project_id,
                })
        return _action

    # ── Keyboard navigation ───────────────────────────────────────────────────

    def _move_up(self) -> None:
        if not self._rows:
            return
        self._set_cursor(max(0, self._cursor - 1))

    def _move_down(self) -> None:
        if not self._rows:
            return
        self._set_cursor(min(len(self._rows) - 1, self._cursor + 1))

    def _set_cursor(self, idx: int) -> None:
        # Deselect old
        if 0 <= self._cursor < len(self._rows):
            self._rows[self._cursor].set_selected(False)
        self._cursor = idx
        if 0 <= self._cursor < len(self._rows):
            row = self._rows[self._cursor]
            row.set_selected(True)
            # Scroll into view
            self._scroll.ensureWidgetVisible(row)

    def _activate_selected(self) -> None:
        if 0 <= self._cursor < len(self._rows):
            row = self._rows[self._cursor]
            self._run_command(row.command)
        elif self._rows:
            self._run_command(self._rows[0].command)

    def _run_command(self, cmd: PaletteCommand) -> None:
        self.record_recent(cmd.id)
        self.close_palette()
        self.command_activated.emit(cmd)
        if callable(cmd.action):
            try:
                cmd.action()
            except Exception as e:
                print(f"[CommandPalette] Error running '{cmd.id}': {e}")

    # ── List helpers ──────────────────────────────────────────────────────────

    def _add_section(self, label: str) -> None:
        self._lay.addWidget(_SectionDivider(label))

    def _add_row(self, cmd: PaletteCommand) -> None:
        row = _PaletteRow(cmd)
        row.activated.connect(lambda c=cmd: self._run_command(c))
        self._lay.addWidget(row)
        self._rows.append(row)

    def _add_placeholder(self, msg: str) -> None:
        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            "color: #353535; font-size: 13px; padding: 28px 0; background: transparent;"
        )
        self._lay.addWidget(lbl)

    def _clear_list(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _sync_height(self) -> None:
        """Resize panel to fit content, capped at 560px."""
        n_rows = len(self._rows)
        # Count section dividers
        n_secs = self._lay.count() - n_rows
        h = 52 + 1 + (n_secs * 24) + (n_rows * 46) + 20
        self.setFixedHeight(min(560, max(110, h)))


# ─────────────────────────────────────────────────────────────────────────────
# Custom QLineEdit that intercepts arrow keys + escape without eating them
# ─────────────────────────────────────────────────────────────────────────────

class _PaletteInput(QLineEdit):
    arrow_up      = Signal()
    arrow_down    = Signal()
    escape_pressed = Signal()

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.key() == Qt.Key_Up:
            self.arrow_up.emit()
        elif ev.key() == Qt.Key_Down:
            self.arrow_down.emit()
        elif ev.key() == Qt.Key_Escape:
            self.escape_pressed.emit()
        else:
            super().keyPressEvent(ev)
