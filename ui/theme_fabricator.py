"""
ui/theme_fabricator.py
══════════════════════════════════════════════════════════════════════════════
Theme Fabricator — premium theme management dialog for Adeptus Craftmatica.

Designed as a polished alternative to ThemeEditorDialog with:
  • Visual gallery of theme cards with colour-swatch previews
  • Live preview pane (real-time mock-UI updates as you edit colours)
  • Grouped, labelled colour token editor with inline swatches
  • Smooth theme-apply transition (brief opacity dip on main window)
  • Duplicate / Delete / Generate from paint scheme
  • "More options…" shortcut to Basic editor for typography/shape/export

Behaviour
─────────
  Builtin themes  → read-only banner; Apply applies directly; Duplicate
                    creates an editable user copy.
  User themes     → fully editable; Apply = save + apply to app;
                    Save = persist only; Delete removes from disk.
  Live preview    → debounced 180 ms after each colour change; UI never locks.
  Transitions     → 220 ms overlay dip on parent window during Apply.

The underlying ThemeManager service is shared with BasicThemeEditorDialog;
no theme data is duplicated.
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from core.theme import Theme, ThemeColors, ThemeMeta, ThemeShape, ThemeTypography

log = logging.getLogger(__name__)

# ── Tuning constants ──────────────────────────────────────────────────────────
_TRANSITION_MS = 220   # overlay fade duration when applying a theme (0 = off)
_DEBOUNCE_MS   = 180   # delay before live-preview repaints after a colour edit

# ── Token groups shown in the colour editor ───────────────────────────────────
_TOKEN_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Backgrounds", [
        ("Deep",      "bg_deep"),
        ("Base",      "bg_base"),
        ("Raised",    "bg_raised"),
        ("Input",     "bg_input"),
        ("Card",      "card_bg"),
        ("Sidebar",   "sidebar_bg"),
        ("Header",    "header_bg"),
    ]),
    ("Borders", [
        ("Default",   "border"),
        ("Highlight", "border_hi"),
    ]),
    ("Text", [
        ("Primary",   "text_hi"),
        ("Secondary", "text_mid"),
        ("Muted",     "text_lo"),
        ("Dim",       "text_dim"),
    ]),
    ("Accent", [
        ("Primary",   "accent"),
        ("Highlight", "accent_hi"),
        ("Subtle",    "accent_lo"),
    ]),
    ("Semantic", [
        ("Danger",    "danger"),
        ("Danger Hi", "danger_hi"),
        ("Danger Lo", "danger_lo"),
        ("Success",   "success"),
        ("Warning",   "warning"),
    ]),
]

# Tokens shown as swatches on each gallery card
_CARD_SWATCH_TOKENS = ["accent", "bg_base", "bg_raised", "border_hi", "text_hi", "danger"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _swatch_icon(hex_color: str, size: int = 16) -> QIcon:
    """Round filled-circle icon in *hex_color*."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(hex_color if hex_color.startswith("#") else "#808080"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(px)


def _valid_hex(s: str) -> bool:
    return bool(re.match(r"^#[0-9A-Fa-f]{6}$", s or ""))


def _get_colors(theme: Theme) -> dict[str, str]:
    """Return a flat token→hex dict for the colour tokens we edit."""
    return {k: v for k, v in vars(theme.colors).items() if isinstance(v, str)}


# ── Gallery card ──────────────────────────────────────────────────────────────

class _ThemeCard(QFrame):
    """
    Compact gallery card.  Shows a colour swatch strip, theme name,
    category label, and an active-theme indicator.
    """
    clicked = Signal(str)   # emits theme_id

    _CARD_H = 76

    def __init__(self, theme: Theme, active_id: str, tm_token, parent=None):
        super().__init__(parent)
        self._id   = theme.meta.id
        self._name = theme.meta.name
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self._CARD_H)
        self.setObjectName(f"themeCard_{self._id}")

        # Determine card type label
        if theme.meta.builtin:
            badge = "Built-in"
        elif theme.meta.generated_from:
            badge = f"From: {theme.meta.generated_from}"
        else:
            badge = "Custom"

        is_active = (self._id == active_id)

        # Base style — accent left border when active
        accent = tm_token("accent")
        bd     = tm_token("border")
        bg     = tm_token("card_bg")
        bg_h   = tm_token("bg_hover") if hasattr(tm_token, "__call__") else "#2e2e2e"
        t_hi   = tm_token("text_hi")
        t_lo   = tm_token("text_lo")

        border_left = f"3px solid {accent}" if is_active else f"3px solid transparent"
        self.setStyleSheet(
            f"QFrame#themeCard_{self._id} {{"
            f"  background: {bg}; border: 1px solid {bd};"
            f"  border-left: {border_left}; border-radius: 6px;"
            f"}}"
            f"QFrame#themeCard_{self._id}:hover {{"
            f"  background: {bg_h}; border-color: {accent};"
            f"  border-left: {border_left};"
            f"}}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        # ── Top row: swatches + active badge ─────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(4)

        tokens = _get_colors(theme)
        for tok in _CARD_SWATCH_TOKENS:
            hex_val = tokens.get(tok, "#808080")
            dot = QLabel()
            dot.setFixedSize(13, 13)
            dot.setStyleSheet(
                f"background:{hex_val}; border-radius:6px; border:none;"
            )
            top.addWidget(dot)

        top.addStretch()

        if is_active:
            active_lbl = QLabel("✓  Active")
            active_lbl.setStyleSheet(
                f"font-size:10px; font-weight:600; color:{accent}; background:transparent;"
            )
            top.addWidget(active_lbl)

        lay.addLayout(top)

        # ── Bottom row: name + category ───────────────────────────────────────
        name_lbl = QLabel(self._name)
        name_lbl.setStyleSheet(
            f"font-size:12px; font-weight:600; color:{t_hi}; background:transparent;"
        )
        lay.addWidget(name_lbl)

        badge_lbl = QLabel(badge)
        badge_lbl.setStyleSheet(
            f"font-size:10px; color:{t_lo}; background:transparent;"
        )
        lay.addWidget(badge_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._id)
        super().mousePressEvent(event)


# ── Live preview pane ─────────────────────────────────────────────────────────

class _PreviewPane(QWidget):
    """
    Renders a small mock UI that updates in real-time as colour tokens change.
    Shows a card, buttons, a text input, and a labelled swatch strip.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors: dict[str, str] = {}
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Mock card ─────────────────────────────────────────────────────────
        self._mock_card = QFrame()
        self._mock_card.setObjectName("previewCard")

        card_lay = QVBoxLayout(self._mock_card)
        card_lay.setContentsMargins(14, 10, 14, 10)
        card_lay.setSpacing(6)

        # Title row: label + two mock buttons
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._mock_title = QLabel("🎨  Theme Preview")
        self._mock_title.setObjectName("previewTitle")
        title_row.addWidget(self._mock_title)
        title_row.addStretch()

        self._mock_btn_primary = QPushButton("Apply")
        self._mock_btn_primary.setObjectName("previewBtnPrimary")
        self._mock_btn_primary.setFixedSize(60, 24)
        self._mock_btn_primary.setEnabled(False)
        title_row.addWidget(self._mock_btn_primary)

        self._mock_btn_ghost = QPushButton("Cancel")
        self._mock_btn_ghost.setObjectName("previewBtnGhost")
        self._mock_btn_ghost.setFixedSize(60, 24)
        self._mock_btn_ghost.setEnabled(False)
        title_row.addWidget(self._mock_btn_ghost)

        card_lay.addLayout(title_row)

        # 1 px divider — fixed height avoids the "line through buttons" artifact
        self._mock_divider = QFrame()
        self._mock_divider.setObjectName("previewDivider")
        self._mock_divider.setFixedHeight(1)
        self._mock_divider.setFrameShape(QFrame.NoFrame)
        card_lay.addWidget(self._mock_divider)

        # Body text
        self._mock_body = QLabel("Secondary text · Muted description line")
        self._mock_body.setObjectName("previewBody")
        card_lay.addWidget(self._mock_body)

        # Input mock
        self._mock_input = QLabel("▌  Input placeholder text…")
        self._mock_input.setObjectName("previewInput")
        self._mock_input.setFixedHeight(26)
        card_lay.addWidget(self._mock_input)

        lay.addWidget(self._mock_card)
        lay.addStretch()

        # Keep dict for repaint compatibility (no visible dots needed)
        self._swatch_dots: dict[str, QLabel] = {}

    def update_colors(self, colors: dict[str, str]) -> None:
        self._colors = colors
        self._repaint_preview()

    def _repaint_preview(self) -> None:
        c = self._colors
        if not c:
            return

        bg_card    = c.get("card_bg",  "#1e1e1e")
        bg_raised  = c.get("bg_raised","#212121")
        bg_input   = c.get("bg_input", "#2a2a2a")
        border     = c.get("border",   "#363636")
        border_hi  = c.get("border_hi","#484848")
        text_hi    = c.get("text_hi",  "#f0f0f0")
        text_mid   = c.get("text_mid", "#d8d8d8")
        text_lo    = c.get("text_lo",  "#909090")
        accent     = c.get("accent",   "#0078d4")
        accent_hi  = c.get("accent_hi","#1a8ee8")

        self._mock_card.setStyleSheet(
            f"QFrame#previewCard {{"
            f"  background:{bg_card}; border:1px solid {border}; border-radius:8px;"
            f"}}"
        )
        self._mock_title.setStyleSheet(
            f"font-size:13px; font-weight:700; color:{text_hi}; background:transparent;"
        )
        self._mock_btn_primary.setStyleSheet(
            f"QPushButton#previewBtnPrimary {{"
            f"  background:{accent}; color:{text_hi}; border:none;"
            f"  border-radius:5px; font-size:11px; font-weight:600;"
            f"}}"
        )
        self._mock_btn_ghost.setStyleSheet(
            f"QPushButton#previewBtnGhost {{"
            f"  background:{bg_raised}; color:{text_mid}; border:1px solid {border_hi};"
            f"  border-radius:5px; font-size:11px;"
            f"}}"
        )
        self._mock_body.setStyleSheet(
            f"font-size:11px; color:{text_lo}; background:transparent;"
        )
        self._mock_input.setStyleSheet(
            f"font-size:11px; color:{text_lo}; background:{bg_input};"
            f"border:1px solid {border}; border-radius:5px; padding: 0 8px;"
        )

        self._mock_divider.setStyleSheet(f"background:{border}; border:none;")


# ── Main dialog ───────────────────────────────────────────────────────────────

class ThemeFabricatorDialog(QDialog):
    """
    Premium theme management dialog.

    Open via ``ThemeFabricatorDialog(context, parent).exec()``.
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self._tm = context.services.get("theme_manager")
        self._working: Optional[Theme]  = None   # deep-copy of selected theme
        self._read_only: bool           = False   # True when a builtin is selected
        self._color_rows: dict[str, tuple[QPushButton, QLineEdit]] = {}
        self._preview_timer: QTimer     = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._flush_preview)
        self._gallery_cards: list[_ThemeCard] = []

        self.setWindowTitle("Theme Fabricator")
        self.setMinimumSize(960, 660)
        self.setModal(True)
        self.setSizeGripEnabled(True)

        self._maximized_once = False
        self._build_ui()
        self._refresh_gallery()
        self._select_theme(self._tm.current_theme_id)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._maximized_once:
            self._maximized_once = True
            self.showMaximized()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QSplitter(Qt.Horizontal)
        body.setHandleWidth(1)
        body.setStyleSheet("QSplitter::handle { background: #2a2a2a; }")
        body.addWidget(self._build_gallery_panel())
        body.addWidget(self._build_editor_panel())
        body.setSizes([240, 720])
        body.setCollapsible(0, False)
        body.setCollapsible(1, False)
        root.addWidget(body, stretch=1)

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("fabHeader")
        bar.setFixedHeight(54)
        bar.setStyleSheet(
            "QWidget#fabHeader { background:#0d0d0d; border-bottom:1px solid #2a2a2a; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 16, 0)

        icon_lbl = QLabel("⚒")
        icon_lbl.setStyleSheet("font-size:22px; background:transparent;")
        lay.addWidget(icon_lbl)

        title = QLabel("Theme Fabricator")
        title.setStyleSheet(
            "font-size:16px; font-weight:700; color:#f0f0f0; background:transparent; margin-left:6px;"
        )
        lay.addWidget(title)
        lay.addStretch()

        hint = QLabel("Select a theme to edit or apply it to the app.")
        hint.setStyleSheet("font-size:11px; color:#606060; background:transparent;")
        lay.addWidget(hint)

        # Switch to Basic editor
        basic_btn = QPushButton("Basic Mode…")
        basic_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#606060;border:1px solid #363636;"
            "border-radius:5px;padding:4px 10px;font-size:11px;}"
            "QPushButton:hover{color:#f0f0f0;border-color:#484848;}"
        )
        basic_btn.clicked.connect(self._open_basic_editor)
        lay.addWidget(basic_btn)

        return bar

    def _build_gallery_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("fabGallery")
        panel.setStyleSheet("QWidget#fabGallery { background:#141414; }")
        panel.setMinimumWidth(220)

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Gallery header
        hdr = QWidget()
        hdr.setStyleSheet("background:#141414; border-bottom:1px solid #252525;")
        hdr.setFixedHeight(40)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 10, 0)
        hl.addWidget(self._lbl("THEMES", size=10, bold=True, color="#606060"))
        hl.addStretch()

        new_btn = QPushButton("+ New")
        new_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#0078d4;border:none;"
            "font-size:11px;font-weight:600;padding:2px 6px;}"
            "QPushButton:hover{color:#1a8ee8;}"
        )
        new_btn.clicked.connect(self._do_new_theme)
        hl.addWidget(new_btn)
        lay.addWidget(hdr)

        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{background:#141414;border:none;}"
            "QScrollBar:vertical{background:#141414;width:5px;border:none;}"
            "QScrollBar::handle:vertical{background:#363636;border-radius:2px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )

        self._gallery_widget = QWidget()
        self._gallery_widget.setStyleSheet("background:#141414;")
        self._gallery_layout = QVBoxLayout(self._gallery_widget)
        self._gallery_layout.setContentsMargins(8, 8, 8, 8)
        self._gallery_layout.setSpacing(5)
        self._gallery_layout.addStretch()

        scroll.setWidget(self._gallery_widget)
        lay.addWidget(scroll, stretch=1)

        return panel

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("fabEditor")
        panel.setStyleSheet("QWidget#fabEditor { background:#1a1a1a; }")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Read-only banner (hidden by default) ──────────────────────────────
        self._readonly_banner = QWidget()
        self._readonly_banner.setStyleSheet(
            "background:#1e1a00; border-bottom:1px solid #3a3000;"
        )
        self._readonly_banner.setFixedHeight(36)
        bl = QHBoxLayout(self._readonly_banner)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.addWidget(self._lbl("🔒  Built-in theme — read-only.  Use Duplicate to create an editable copy.",
                               size=11, color="#b8900a"))
        bl.addStretch()
        self._readonly_banner.hide()
        lay.addWidget(self._readonly_banner)

        # ── Editor name bar ───────────────────────────────────────────────────
        name_bar = QWidget()
        name_bar.setStyleSheet("background:#1a1a1a; border-bottom:1px solid #252525;")
        name_bar.setFixedHeight(48)
        nl = QHBoxLayout(name_bar)
        nl.setContentsMargins(18, 0, 18, 0)
        nl.setSpacing(10)
        nl.addWidget(self._lbl("Name:", size=11, color="#909090"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Theme name…")
        self._name_edit.setStyleSheet(
            "QLineEdit{background:#242424;color:#f0f0f0;border:1px solid #363636;"
            "border-radius:5px;padding:4px 10px;font-size:12px;}"
            "QLineEdit:focus{border-color:#0078d4;}"
        )
        self._name_edit.textEdited.connect(self._on_name_edit)
        nl.addWidget(self._name_edit, stretch=1)
        lay.addWidget(name_bar)

        # ── Body: preview (top) + colour editor (bottom) ──────────────────────
        body_splitter = QSplitter(Qt.Vertical)
        body_splitter.setHandleWidth(1)
        body_splitter.setStyleSheet("QSplitter::handle{background:#2a2a2a;}")

        # Preview pane — kept compact; colour grid gets the remaining height
        preview_wrap = QWidget()
        preview_wrap.setStyleSheet("background:#1a1a1a;")
        preview_wrap.setMaximumHeight(195)
        pw_lay = QVBoxLayout(preview_wrap)
        pw_lay.setContentsMargins(18, 8, 18, 8)
        pw_lay.setSpacing(6)
        pw_lay.addWidget(self._lbl("PREVIEW", size=10, bold=True, color="#606060"))
        self._preview = _PreviewPane()
        pw_lay.addWidget(self._preview)
        body_splitter.addWidget(preview_wrap)

        # Colour editor (scrollable)
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor_scroll.setStyleSheet(
            "QScrollArea{background:#1a1a1a;border:none;}"
            "QScrollBar:vertical{background:#1a1a1a;width:5px;border:none;}"
            "QScrollBar::handle:vertical{background:#363636;border-radius:2px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )

        self._color_grid_widget = QWidget()
        self._color_grid_widget.setStyleSheet("background:#1a1a1a;")
        self._color_grid_layout = QVBoxLayout(self._color_grid_widget)
        self._color_grid_layout.setContentsMargins(18, 10, 18, 10)
        self._color_grid_layout.setSpacing(0)
        self._color_grid_layout.addStretch()
        editor_scroll.setWidget(self._color_grid_widget)
        body_splitter.addWidget(editor_scroll)

        body_splitter.setSizes([185, 9999])
        lay.addWidget(body_splitter, stretch=1)

        # ── Action bar ────────────────────────────────────────────────────────
        lay.addWidget(self._build_action_bar())

        return panel

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background:#141414; border-top:1px solid #252525;")
        bar.setFixedHeight(54)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(8)

        self._btn_generate  = self._action_btn("⚗  Generate…",  secondary=True)
        self._btn_duplicate = self._action_btn("⎘  Duplicate",  secondary=True)
        self._btn_delete    = self._action_btn("✕  Delete",     danger=True)
        self._btn_save      = self._action_btn("Save",          secondary=True)
        self._btn_apply     = self._action_btn("Apply Theme",   primary=True)

        self._btn_generate.clicked.connect(self._do_generate)
        self._btn_duplicate.clicked.connect(self._do_duplicate)
        self._btn_delete.clicked.connect(self._do_delete)
        self._btn_save.clicked.connect(self._do_save)
        self._btn_apply.clicked.connect(self._do_apply)

        bl.addWidget(self._btn_generate)
        bl.addWidget(self._btn_duplicate)
        bl.addWidget(self._btn_delete)
        bl.addStretch()
        bl.addWidget(self._btn_save)
        bl.addWidget(self._btn_apply)

        return bar

    # ── Gallery management ────────────────────────────────────────────────────

    def _refresh_gallery(self) -> None:
        """Rebuild the gallery card list from current themes."""
        # Clear existing cards
        for card in self._gallery_cards:
            card.deleteLater()
        self._gallery_cards.clear()

        # Remove all items except the trailing stretch
        while self._gallery_layout.count() > 1:
            item = self._gallery_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tm_token = self._tm.token
        active_id = self._tm.current_theme_id

        # Section: Built-in
        builtins = [t for t in self._tm.available() if t.meta.builtin]
        user     = [t for t in self._tm.available() if not t.meta.builtin]

        if builtins:
            self._gallery_layout.insertWidget(
                self._gallery_layout.count() - 1,
                self._section_label("Built-in")
            )
            for theme in builtins:
                card = _ThemeCard(theme, active_id, tm_token)
                card.clicked.connect(self._select_theme)
                self._gallery_cards.append(card)
                self._gallery_layout.insertWidget(
                    self._gallery_layout.count() - 1, card
                )

        if user:
            self._gallery_layout.insertWidget(
                self._gallery_layout.count() - 1,
                self._section_label("My Themes")
            )
            for theme in user:
                card = _ThemeCard(theme, active_id, tm_token)
                card.clicked.connect(self._select_theme)
                self._gallery_cards.append(card)
                self._gallery_layout.insertWidget(
                    self._gallery_layout.count() - 1, card
                )

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            "font-size:9px; font-weight:700; color:#505050; "
            "background:transparent; padding:8px 6px 4px 6px; letter-spacing:1px;"
        )
        return lbl

    # ── Theme selection ───────────────────────────────────────────────────────

    def _select_theme(self, theme_id: str) -> None:
        theme = self._tm.themes.get(theme_id)
        if not theme:
            return

        self._working    = copy.deepcopy(theme)
        self._read_only  = theme.meta.builtin
        self._readonly_banner.setVisible(self._read_only)

        # Update name field
        self._name_edit.setText(theme.meta.name)
        self._name_edit.setEnabled(not self._read_only)

        # Rebuild colour grid
        self._rebuild_color_grid()

        # Refresh preview immediately
        self._flush_preview()

        # Update action button states
        self._btn_save.setEnabled(not self._read_only)
        self._btn_delete.setEnabled(
            not self._read_only
            and theme_id != self._tm.current_theme_id
        )

        # Highlight the correct gallery card
        for card in self._gallery_cards:
            is_selected = (card._id == theme_id)
            card.setProperty("selected", is_selected)
            card.style().unpolish(card)
            card.style().polish(card)

    def _rebuild_color_grid(self) -> None:
        """Tear down and rebuild the colour token rows for the current working theme."""
        self._color_rows.clear()

        # Clear layout (leave trailing stretch)
        while self._color_grid_layout.count() > 1:
            item = self._color_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        if not self._working:
            return

        colors = _get_colors(self._working)
        insert_pos = 0

        for group_name, tokens in _TOKEN_GROUPS:
            # Group header
            grp_hdr = QLabel(group_name.upper())
            grp_hdr.setStyleSheet(
                "font-size:9px; font-weight:700; color:#505050; "
                "background:transparent; padding:12px 0 5px 0; letter-spacing:1px;"
            )
            self._color_grid_layout.insertWidget(insert_pos, grp_hdr)
            insert_pos += 1

            for label, token in tokens:
                hex_val = colors.get(token, "#808080")
                row = self._build_color_row(label, token, hex_val)
                self._color_grid_layout.insertLayout(insert_pos, row)
                insert_pos += 1

            # Thin divider between groups
            div = QFrame()
            div.setFrameShape(QFrame.HLine)
            div.setFixedHeight(1)
            div.setStyleSheet("background:#252525; border:none;")
            self._color_grid_layout.insertWidget(insert_pos, div)
            insert_pos += 1

    def _build_color_row(
        self, label: str, token: str, hex_val: str
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 2, 0, 2)

        # Label
        lbl = QLabel(label)
        lbl.setFixedWidth(82)
        lbl.setStyleSheet("font-size:11px; color:#909090; background:transparent;")
        row.addWidget(lbl)

        # Swatch button (opens colour picker)
        swatch = QPushButton()
        swatch.setFixedSize(22, 22)
        swatch.setCursor(Qt.PointingHandCursor)
        swatch.setEnabled(not self._read_only)
        self._set_swatch_color(swatch, hex_val)

        # Hex input
        hex_edit = QLineEdit(hex_val)
        hex_edit.setFixedWidth(90)
        hex_edit.setMaxLength(7)
        hex_edit.setEnabled(not self._read_only)
        hex_edit.setStyleSheet(
            "QLineEdit{background:#242424;color:#f0f0f0;border:1px solid #363636;"
            "border-radius:4px;padding:2px 6px;font-size:11px;font-family:monospace;}"
            "QLineEdit:focus{border-color:#0078d4;}"
            "QLineEdit:disabled{color:#606060;}"
        )

        # Wire up interactions
        def _pick_color(_checked=False, _tok=token, _swatch=swatch, _edit=hex_edit):
            current = _edit.text()
            initial = QColor(current) if _valid_hex(current) else QColor("#808080")
            chosen  = QColorDialog.getColor(initial, self, f"Pick colour for {_tok}")
            if chosen.isValid():
                new_hex = chosen.name().upper()
                _edit.setText(new_hex)
                self._set_swatch_color(_swatch, new_hex)
                self._on_color_change(_tok, new_hex)

        def _on_hex_edit(_text, _tok=token, _swatch=swatch):
            t = _text.strip()
            if not t.startswith("#"):
                t = "#" + t
            if _valid_hex(t):
                self._set_swatch_color(_swatch, t)
                self._on_color_change(_tok, t)

        swatch.clicked.connect(_pick_color)
        hex_edit.textEdited.connect(_on_hex_edit)

        self._color_rows[token] = (swatch, hex_edit)
        row.addWidget(swatch)
        row.addWidget(hex_edit)
        row.addStretch()

        return row

    @staticmethod
    def _set_swatch_color(btn: QPushButton, hex_val: str) -> None:
        safe = hex_val if _valid_hex(hex_val) else "#808080"
        btn.setStyleSheet(
            f"QPushButton{{background:{safe};border:1px solid #484848;"
            f"border-radius:4px;}}"
            f"QPushButton:hover{{border-color:#f0f0f0;}}"
        )

    # ── Colour change handling ────────────────────────────────────────────────

    def _on_name_edit(self, text: str) -> None:
        if self._working and not self._read_only:
            self._working.meta = ThemeMeta(
                id=self._working.meta.id,
                name=text,
                author=self._working.meta.author,
                builtin=False,
                generated_from=self._working.meta.generated_from,
            )

    def _on_color_change(self, token: str, hex_val: str) -> None:
        if not self._working or self._read_only:
            return
        if _valid_hex(hex_val):
            setattr(self._working.colors, token, hex_val.upper())
        self._preview_timer.start(_DEBOUNCE_MS)

    def _flush_preview(self) -> None:
        if self._working:
            self._preview.update_colors(_get_colors(self._working))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _do_apply(self) -> None:
        if not self._working:
            return

        theme = self._working
        tm = self._tm

        def _perform():
            if theme.meta.builtin:
                # Apply builtin as-is (no save needed)
                tm.apply_theme(theme.meta.id)
            else:
                # Persist edits then apply
                try:
                    tm.save_theme(theme)
                except Exception as exc:
                    log.warning(f"[Fabricator] Save before apply failed: {exc}")
                tm.apply_theme(theme.meta.id)
            self._refresh_gallery()

        self._transition_then(_perform)

    def _do_save(self) -> None:
        if not self._working or self._read_only:
            return
        try:
            self._tm.save_theme(self._working)
            self._refresh_gallery()
            self._show_toast("Theme saved.")
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))

    def _do_duplicate(self) -> None:
        if not self._working:
            return
        base_name = self._working.meta.name
        new_name  = f"{base_name} Copy"
        new_theme = self._tm.create_copy(new_name, self._working.meta.id)
        try:
            self._tm.save_theme(new_theme)
        except Exception as exc:
            QMessageBox.critical(self, "Duplicate Failed", str(exc))
            return
        self._refresh_gallery()
        self._select_theme(new_theme.meta.id)

    def _do_delete(self) -> None:
        if not self._working or self._working.meta.builtin:
            return
        name = self._working.meta.name
        answer = QMessageBox.question(
            self, "Delete Theme",
            f'Permanently delete “{name}”?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self._tm.delete_theme(self._working.meta.id)
        except Exception as exc:
            QMessageBox.critical(self, "Delete Failed", str(exc))
            return
        self._refresh_gallery()
        self._select_theme(self._tm.current_theme_id)

    def _do_generate(self) -> None:
        """Open the Generate dialog (reused from BasicThemeEditor) then save the result."""
        try:
            from ui.theme_editor import _GenerateDialog
        except ImportError:
            QMessageBox.information(
                self, "Generate",
                "The generate dialog requires the basic theme editor module."
            )
            return

        dlg = _GenerateDialog(self.context, self)
        if dlg.exec() != QDialog.Accepted:
            return

        hex_val = getattr(dlg, "result_hex",    None)
        name    = getattr(dlg, "result_name",   None)
        source  = getattr(dlg, "result_source", "")
        if not hex_val or not name:
            return

        new_theme = self._tm.generate_from_paint(hex_val, name, source)
        try:
            self._tm.save_theme(new_theme)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self._refresh_gallery()
        self._select_theme(new_theme.meta.id)

    def _do_new_theme(self) -> None:
        new_theme = self._tm.create_blank("New Theme")
        try:
            self._tm.save_theme(new_theme)
        except Exception as exc:
            QMessageBox.critical(self, "Create Failed", str(exc))
            return
        self._refresh_gallery()
        self._select_theme(new_theme.meta.id)

    def _open_basic_editor(self) -> None:
        from ui.theme_editor import ThemeEditorDialog
        dlg = ThemeEditorDialog(self.context, self)
        dlg.exec()
        self._refresh_gallery()
        self._select_theme(self._tm.current_theme_id)

    # ── Smooth apply transition ───────────────────────────────────────────────

    def _transition_then(self, callback) -> None:
        """
        Apply a brief overlay fade on the parent window, execute callback at
        peak opacity, then fade out.  Falls back to direct call if parent
        is unavailable or _TRANSITION_MS == 0.
        """
        if not _TRANSITION_MS:
            try:
                callback()
            except Exception:
                pass
            return

        try:
            from ui.animations import theme_fade_transition
            parent = self.parent() or self
            theme_fade_transition(parent, callback, _TRANSITION_MS)
        except Exception:
            try:
                callback()
            except Exception:
                pass

    # ── Misc helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _lbl(
        text: str,
        size: int = 12,
        bold: bool = False,
        color: str = "#d8d8d8",
    ) -> QLabel:
        lbl = QLabel(text)
        weight = "700" if bold else "400"
        lbl.setStyleSheet(
            f"font-size:{size}px; font-weight:{weight}; color:{color}; background:transparent;"
        )
        return lbl

    @staticmethod
    def _action_btn(
        text: str,
        primary: bool = False,
        secondary: bool = False,
        danger: bool = False,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setCursor(Qt.PointingHandCursor)
        if primary:
            btn.setStyleSheet(
                "QPushButton{background:#0078d4;color:#f0f0f0;border:none;"
                "border-radius:5px;padding:0 18px;font-size:12px;font-weight:600;}"
                "QPushButton:hover{background:#1a8ee8;}"
                "QPushButton:pressed{background:#0060aa;}"
                "QPushButton:disabled{background:#1e2a38;color:#506070;}"
            )
        elif danger:
            btn.setStyleSheet(
                "QPushButton{background:transparent;color:#e05555;border:1px solid #4a2020;"
                "border-radius:5px;padding:0 14px;font-size:12px;}"
                "QPushButton:hover{background:#2a1515;border-color:#e05555;}"
                "QPushButton:disabled{color:#604040;border-color:#3a2020;}"
            )
        else:
            btn.setStyleSheet(
                "QPushButton{background:#242424;color:#d8d8d8;border:1px solid #363636;"
                "border-radius:5px;padding:0 14px;font-size:12px;}"
                "QPushButton:hover{border-color:#484848;color:#f0f0f0;}"
                "QPushButton:pressed{background:#1e1e1e;}"
                "QPushButton:disabled{color:#606060;border-color:#2a2a2a;}"
            )
        return btn

    def _show_toast(self, message: str) -> None:
        try:
            from ui.toast import ToastManager
            ToastManager.instance().show(message, "success")
        except Exception:
            pass

    @staticmethod
    def _clear_layout(layout) -> None:
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                ThemeFabricatorDialog._clear_layout(item.layout())
