# ui/command_palette.py
"""
Command Palette — universal control surface for Adeptus Craftmatica.

Triggered via Ctrl+P / Ctrl+K.

Features:
  • Fuzzy search across commands, descriptions, keywords, and aliases
  • Grouped results: Recent, Navigate, Create, Tools, Settings, Plugin Commands, Results
  • Persistent recent + frequency tracking (SQLite via SettingsService)
  • Plugin-provided commands via optional get_commands() hook
  • Inline content search (projects, paints, models, armies)
  • Full keyboard navigation: arrows, Enter, Escape

Public API:
    from ui.command_palette import CommandPalette, CommandRegistry, PaletteCommand

    # Register a command from anywhere:
    CommandRegistry.instance().register(PaletteCommand(
        id="my_cmd", title="Do Something", icon="✦",
        category="Tools", source="My Plugin",
        description="A helpful description",
        keywords=["something", "action"],
        action=lambda: do_something(),
    ))

    # Open the palette:
    palette.toggle()
"""
from __future__ import annotations

import json
import logging
log = logging.getLogger(__name__)

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QScrollArea, QGraphicsDropShadowEffect,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PaletteCommand:
    """One entry in the command palette."""
    id:          str
    title:       str
    icon:        str                = "›"
    subtitle:    str                = ""
    description: str                = ""      # longer text shown below the title
    category:    str                = "Actions"
    source:      str                = ""      # plugin name, "Core", etc.
    shortcut:    str                = ""
    keywords:    list               = field(default_factory=list)
    aliases:     list               = field(default_factory=list)
    action:      Optional[Callable] = None

    def matches(self, needle: str) -> bool:
        """True if needle fuzzy-matches title, subtitle, description, keywords, or aliases."""
        if not needle:
            return True
        n = needle.lower()
        corpus = " ".join([
            self.title, self.subtitle, self.description
        ] + self.keywords + self.aliases).lower()
        it = iter(corpus)
        return all(c in it for c in n)

    def score(self, needle: str) -> int:
        """Higher = better match. Used to rank filtered results."""
        if not needle:
            return 0
        n = needle.lower()
        t = self.title.lower()
        if t == n:
            return 200
        if t.startswith(n):
            return 150
        if any(w.startswith(n) for w in t.split()):
            return 120
        if n in t:
            return 90
        if n in self.subtitle.lower():
            return 60
        for kw in self.keywords + self.aliases:
            if n in kw.lower():
                return 50
        if n in self.description.lower():
            return 40
        return 10


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

class CommandRegistry:
    """
    Singleton registry of all palette commands.

    Register commands from any module at any time — they appear in the
    palette automatically. Plugins should call this during activate().
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
# Category config
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORY_ORDER = [
    "Recent",
    "Navigate",
    "Create",
    "Tools",
    "Settings",
    "Plugin Commands",
    "Results",
]

_CATEGORY_COLOR: dict[str, str] = {
    "Recent":          "#787878",
    "Navigate":        "#3b9eff",
    "Create":          "#22c55e",
    "Tools":           "#f59e0b",
    "Settings":        "#ec4899",
    "Plugin Commands": "#1abc9c",
    "Results":         "#a855f7",
    "Commands":        "#787878",
    "Actions":         "#787878",
}


# ─────────────────────────────────────────────────────────────────────────────
# Row widget
# ─────────────────────────────────────────────────────────────────────────────

class _PaletteRow(QFrame):
    activated = Signal()
    _ROW_H = 54

    def __init__(self, cmd: PaletteCommand, parent=None):
        super().__init__(parent)
        self._cmd = cmd
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self._ROW_H)
        self._selected = False
        self._apply_style(False)
        self._build(cmd)

    def _build(self, cmd: PaletteCommand) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)

        # Icon
        color = _CATEGORY_COLOR.get(cmd.category, "#666")
        icon_lbl = QLabel(cmd.icon)
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            f"font-size:16px; color:{color}; background:transparent;"
        )
        lay.addWidget(icon_lbl)

        # Text block: title + description/subtitle
        text = QVBoxLayout()
        text.setSpacing(2)
        text.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(cmd.title)
        title_lbl.setStyleSheet(
            "color:#e0e0e0; font-size:13px; font-weight:600; background:transparent;"
        )
        text.addWidget(title_lbl)

        desc = cmd.description or cmd.subtitle
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                "color:#484848; font-size:11px; background:transparent;"
            )
            text.addWidget(desc_lbl)

        lay.addLayout(text, stretch=1)

        # Right side: source badge + shortcut
        has_right = bool(cmd.source or cmd.shortcut)
        if has_right:
            right = QVBoxLayout()
            right.setSpacing(3)
            right.setContentsMargins(0, 0, 0, 0)
            right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            if cmd.source:
                src_lbl = QLabel(cmd.source)
                src_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                src_lbl.setStyleSheet(
                    "color:#404040; font-size:9px; background:#181818;"
                    " border:1px solid #242424; border-radius:3px; padding:1px 5px;"
                )
                right.addWidget(src_lbl, alignment=Qt.AlignRight)

            if cmd.shortcut:
                sc_lbl = QLabel(cmd.shortcut)
                sc_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                sc_lbl.setStyleSheet(
                    "color:#484848; font-size:10px; background:#161616;"
                    " border:1px solid #2a2a2a; border-radius:4px;"
                    " padding:1px 6px; font-family:monospace;"
                )
                right.addWidget(sc_lbl, alignment=Qt.AlignRight)

            lay.addLayout(right)

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self._apply_style(selected)

    def _apply_style(self, selected: bool) -> None:
        if selected:
            color = _CATEGORY_COLOR.get(self._cmd.category, "#0078d4")
            self.setStyleSheet(
                f"QFrame {{ background:{color}18; border-left:2px solid {color};"
                f" border-radius:5px; }}"
            )
        else:
            self.setStyleSheet(
                "QFrame { background:transparent; border-radius:5px; }"
            )

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self.activated.emit()

    def enterEvent(self, ev) -> None:
        if not self._selected:
            self.setStyleSheet("QFrame { background:#1c1c1c; border-radius:5px; }")

    def leaveEvent(self, ev) -> None:
        self._apply_style(self._selected)

    @property
    def command(self) -> PaletteCommand:
        return self._cmd


# ─────────────────────────────────────────────────────────────────────────────
# Section divider
# ─────────────────────────────────────────────────────────────────────────────

class _SectionDivider(QFrame):
    def __init__(self, label: str, count: int = 0, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(26)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(6)
        color = _CATEGORY_COLOR.get(label, "#444")

        name_lbl = QLabel(label.upper())
        name_lbl.setStyleSheet(
            f"color:{color}; font-size:9px; font-weight:700;"
            " letter-spacing:1.5px; background:transparent;"
        )
        lay.addWidget(name_lbl)

        if count > 0:
            count_lbl = QLabel(str(count))
            count_lbl.setStyleSheet(
                f"color:{color}88; font-size:9px; background:#181818;"
                f" border:1px solid #202020; border-radius:8px; padding:0 5px;"
            )
            lay.addWidget(count_lbl)

        lay.addStretch()


# ─────────────────────────────────────────────────────────────────────────────
# Main palette widget
# ─────────────────────────────────────────────────────────────────────────────

class CommandPalette(QFrame):
    """
    Floating command palette widget.

    Attach to the central widget of MainWindow as a child for absolute
    positioning.  Call toggle() to open/close.
    """

    command_activated = Signal(PaletteCommand)
    _RECENT_MAX = 10

    def __init__(self, context, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx     = context
        self._rows:   list[_PaletteRow] = []
        self._cursor  = -1
        self._recent: deque[str]     = deque(maxlen=self._RECENT_MAX)
        self._freq:   dict[str, int] = {}

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._refresh)

        self._build_frame()
        self._load_history()
        self.hide()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_history(self) -> None:
        try:
            s = self._ctx.services.try_get("settings")
            if s:
                recent_ids = json.loads(s.get("command_palette.recent", "[]"))
                self._recent = deque(recent_ids[:self._RECENT_MAX], maxlen=self._RECENT_MAX)
                self._freq   = json.loads(s.get("command_palette.freq",   "{}"))
        except Exception:
            pass

    def _save_history(self) -> None:
        try:
            s = self._ctx.services.try_get("settings")
            if s:
                s.set("command_palette.recent", json.dumps(list(self._recent)))
                s.set("command_palette.freq",   json.dumps(self._freq))
        except Exception:
            pass

    # ── Frame / chrome ────────────────────────────────────────────────────────

    def _build_frame(self) -> None:
        self.setObjectName("commandPalette")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(640)
        self.setStyleSheet("""
            QFrame#commandPalette {
                background: #141414;
                border: 1px solid #2a2a2a;
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(0)

        # ── Input row ─────────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setFrameShape(QFrame.NoFrame)
        input_frame.setFixedHeight(54)
        input_frame.setStyleSheet("QFrame { background: transparent; }")
        ir = QHBoxLayout(input_frame)
        ir.setContentsMargins(16, 0, 16, 0)
        ir.setSpacing(10)

        search_icon = QLabel("⌕")
        search_icon.setStyleSheet(
            "font-size:18px; color:#404040; background:transparent;"
        )
        search_icon.setFixedWidth(22)
        ir.addWidget(search_icon)

        self._input = _PaletteInput()
        self._input.setPlaceholderText("Search commands, actions, projects, paints…")
        self._input.setFrame(False)
        self._input.setStyleSheet(
            "QLineEdit { background:transparent; border:none;"
            " color:#ebebeb; font-size:14px; }"
            "QLineEdit::placeholder { color:#303030; }"
        )
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._activate_selected)
        self._input.arrow_up.connect(self._move_up)
        self._input.arrow_down.connect(self._move_down)
        self._input.escape_pressed.connect(self.close_palette)
        ir.addWidget(self._input, stretch=1)

        esc_hint = QLabel("esc")
        esc_hint.setStyleSheet(
            "color:#2e2e2e; font-size:10px; background:#181818;"
            " border:1px solid #242424; border-radius:4px; padding:2px 7px;"
        )
        ir.addWidget(esc_hint)

        root.addWidget(input_frame)

        # ── Divider ───────────────────────────────────────────────────────────
        div = QFrame()
        div.setFixedHeight(1)
        div.setFrameShape(QFrame.NoFrame)
        div.setStyleSheet("background:#202020; border:none;")
        root.addWidget(div)

        # ── Results scroll area ───────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background:transparent; border:none; }
            QScrollBar:vertical { background:transparent; width:4px; }
            QScrollBar::handle:vertical {
                background:#282828; border-radius:2px; min-height:20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height:0; }
        """)

        self._content = QWidget()
        self._content.setStyleSheet("background:transparent;")
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
        """Bump command to top of recent list and increment its frequency count."""
        if cmd_id in self._recent:
            self._recent.remove(cmd_id)
        self._recent.appendleft(cmd_id)
        self._freq[cmd_id] = self._freq.get(cmd_id, 0) + 1
        self._save_history()

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
        y = max(60, int(ph * 0.10))
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
        by_cat   = registry.by_category()

        # Recent section — most-frequent within the recent set shown first
        recent_cmds = [
            registry._commands[rid]
            for rid in self._recent
            if rid in registry._commands
        ]
        if recent_cmds:
            recent_cmds.sort(key=lambda c: -self._freq.get(c.id, 0))
            self._add_section("Recent", min(5, len(recent_cmds)))
            for cmd in recent_cmds[:5]:
                self._add_row(cmd)

        # All other categories in display order
        for cat in _CATEGORY_ORDER:
            if cat in ("Recent", "Results"):
                continue
            cmds = by_cat.get(cat, [])
            if cmds:
                self._add_section(cat, len(cmds))
                for cmd in cmds:
                    self._add_row(cmd)

        if not self._rows:
            self._add_placeholder("No commands registered yet")

        self._lay.addStretch()

    # ── Filtered layout ───────────────────────────────────────────────────────

    def _populate_filtered(self, needle: str) -> None:
        registry = CommandRegistry.instance()

        matched = [
            (cmd, cmd.score(needle))
            for cmd in registry.all_commands()
            if cmd.matches(needle)
        ]
        matched.sort(key=lambda x: (-x[1], x[0].title.lower()))

        if matched:
            # Group into categories preserving score order within each group
            by_cat: dict[str, list[PaletteCommand]] = {}
            for cmd, _ in matched[:24]:
                by_cat.setdefault(cmd.category, []).append(cmd)

            shown = 0
            for cat in _CATEGORY_ORDER:
                cmds = by_cat.pop(cat, [])
                if not cmds:
                    continue
                self._add_section(cat, len(cmds))
                for cmd in cmds[:8]:
                    self._add_row(cmd)
                    shown += 1
                if shown >= 18:
                    break

            # Any category not in the standard order list
            for cat, cmds in by_cat.items():
                if cmds:
                    self._add_section(cat, len(cmds))
                    for cmd in cmds[:5]:
                        self._add_row(cmd)

        # Content search (projects, paints, models, armies)
        content_results = self._search_content(needle)
        if content_results:
            self._add_section("Results", len(content_results))
            for cmd in content_results:
                self._add_row(cmd)

        if not self._rows:
            self._add_no_results(needle)
        else:
            self._lay.addStretch()
            if self._rows:
                self._set_cursor(0)

    # ── Content search ────────────────────────────────────────────────────────

    def _search_content(self, needle: str) -> list[PaletteCommand]:
        """Query plugin services and return result commands."""
        results: list[PaletteCommand] = []
        n = needle.lower()

        # Projects
        try:
            svc = self._ctx.services.try_get("project_service")
            if svc:
                hits = [p for p in svc.get_all_projects()
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
                        source="Projects",
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
                        source="Paints",
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
                        source="Models",
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
                        source="Armies",
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
        if 0 <= self._cursor < len(self._rows):
            self._rows[self._cursor].set_selected(False)
        self._cursor = idx
        if 0 <= self._cursor < len(self._rows):
            row = self._rows[self._cursor]
            row.set_selected(True)
            self._scroll.ensureWidgetVisible(row)

    def _activate_selected(self) -> None:
        if 0 <= self._cursor < len(self._rows):
            self._run_command(self._rows[self._cursor].command)
        elif self._rows:
            self._run_command(self._rows[0].command)

    def _run_command(self, cmd: PaletteCommand) -> None:
        self.record_recent(cmd.id)
        self.close_palette()
        self.command_activated.emit(cmd)
        if callable(cmd.action):
            try:
                cmd.action()
            except Exception as exc:
                log.error(f"[CommandPalette] Error running '{cmd.id}': {exc}")

    # ── List helpers ──────────────────────────────────────────────────────────

    def _add_section(self, label: str, count: int = 0) -> None:
        self._lay.addWidget(_SectionDivider(label, count))

    def _add_row(self, cmd: PaletteCommand) -> None:
        row = _PaletteRow(cmd)
        row.activated.connect(lambda c=cmd: self._run_command(c))
        self._lay.addWidget(row)
        self._rows.append(row)

    def _add_placeholder(self, msg: str) -> None:
        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            "color:#303030; font-size:13px; padding:28px 0; background:transparent;"
        )
        self._lay.addWidget(lbl)

    def _add_no_results(self, needle: str) -> None:
        wrap = QWidget()
        wrap.setStyleSheet("background:transparent;")
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(24, 22, 24, 16)
        wl.setSpacing(6)

        msg = QLabel(f'No results for "{needle}"')
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet(
            "color:#404040; font-size:13px; font-weight:600; background:transparent;"
        )
        wl.addWidget(msg)

        hint = QLabel("Try a plugin name, action, or an item in your collection")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(
            "color:#2e2e2e; font-size:11px; background:transparent;"
        )
        wl.addWidget(hint)

        self._lay.addWidget(wrap)
        self._lay.addStretch()

    def _clear_list(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _sync_height(self) -> None:
        """Resize panel to fit content, capped at 600px."""
        n_rows = len(self._rows)
        n_secs = 0
        for i in range(self._lay.count()):
            item = self._lay.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _SectionDivider):
                n_secs += 1
        h = 54 + 1 + (n_secs * 26) + (n_rows * _PaletteRow._ROW_H) + 20
        self.setFixedHeight(min(600, max(110, h)))


# ─────────────────────────────────────────────────────────────────────────────
# Custom QLineEdit — intercepts arrow keys and Escape before Qt eats them
# ─────────────────────────────────────────────────────────────────────────────

class _PaletteInput(QLineEdit):
    arrow_up       = Signal()
    arrow_down     = Signal()
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
