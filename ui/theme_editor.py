"""
ui/theme_editor.py
═══════════════════════════════════════════════════════════════════════════════
ThemeEditorDialog — full theme management UI (polished v2).

New in this version
───────────────────
• _GenerateDialog   — multi-source theme generation:
    – Manual        (color wheel / hex input)
    – Paint Collection  (pick from owned paints)
    – Paint Scheme      (pick a paint from any saved scheme)
    – Army / Model      (pick from army-linked paints)
  Each source updates a live mini-palette preview strip.
  Auto-suggests a theme name based on the selected source.

• Export / Import   — save / load .json theme files.

• Accent-colour icons  — every entry in the theme list shows a small
  coloured square matching the theme's accent colour.

• Read-only banner  — builtin themes show a clearly-styled "locked" notice
  with a one-click Duplicate shortcut.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Optional, Any

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QSplitter, QTabWidget, QVBoxLayout, QWidget, QMessageBox,
)

from core.theme import (
    Theme, ThemeMeta, ThemeColors, ThemeTypography, ThemeShape,
    theme_from_paint_scheme,
)


# ── Tiny color-icon factory ────────────────────────────────────────────────────

def _make_color_icon(hex_color: str, size: int = 14) -> QIcon:
    """Return a QIcon containing a solid-coloured square."""
    try:
        pix = QPixmap(size, size)
        pix.fill(QColor(hex_color))
        return QIcon(pix)
    except Exception:
        return QIcon()


# ── Swatch button (unchanged) ─────────────────────────────────────────────────

class _SwatchButton(QPushButton):
    """A square color-preview button that opens QColorDialog on click."""

    SIZE = 32

    def __init__(self, token: str, hex_color: str, parent=None):
        super().__init__(parent)
        self._token = token
        self._hex   = hex_color
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{token}: {hex_color}")
        self._refresh()

    @property
    def token(self) -> str:
        return self._token

    @property
    def hex_color(self) -> str:
        return self._hex

    def set_color(self, hex_color: str):
        self._hex = hex_color
        self.setToolTip(f"{self._token}: {hex_color}")
        self._refresh()

    def _refresh(self):
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._hex}; "
            f"border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; }}"
            f"QPushButton:hover {{ border: 2px solid rgba(255,255,255,0.5); }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            color = QColorDialog.getColor(
                QColor(self._hex), self, f"Choose color — {self._token}"
            )
            if color.isValid():
                self.set_color(color.name().upper())
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
# _GenerateDialog — multi-source accent picker
# ══════════════════════════════════════════════════════════════════════════════

class _GenerateDialog(QDialog):
    """
    Multi-source theme generation dialog.

    Tabs
    ────
    Manual           — free color-wheel / hex input
    Paint Collection — pick from owned paints  (paint_tracker)
    Paint Scheme     — pick a paint from any saved scheme  (paint_scheme)
    Army / Model     — pick from army-linked paints  (army_builder)

    Each source updates a live mini-palette preview strip.
    A theme name is auto-suggested from the selected source but remains editable.
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx          = context
        self._accent_hex   = "#0078d4"
        self._source_label = ""
        self._name_is_auto = True          # False once user manually edits name

        # --- cached data (loaded once after dialog opens) ---
        self._all_paints:  list[Any] = []
        self._all_schemes: list[Any] = []
        self._all_armies:  list[Any] = []
        self._paint_by_id: dict[int, Any] = {}

        # --- results ---
        self.result_hex    = ""
        self.result_name   = ""
        self.result_source = ""

        self.setWindowTitle("Generate Theme from Color")
        self.setMinimumSize(740, 580)
        self.setModal(True)

        self._build_ui()
        self._update_preview()
        QTimer.singleShot(0, self._load_all_data)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(48)
        title_bar.setStyleSheet(
            "QWidget { background: #0d0d0d; border-bottom: 1px solid #2a2a2a; }"
        )
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(20, 0, 20, 0)
        tb_lbl = QLabel("🎨  Generate Theme from Color")
        tb_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #f0f0f0; background: transparent;"
        )
        tb_lay.addWidget(tb_lbl)
        root.addWidget(title_bar)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: #1a1a1a; }
            QTabBar { background: #141414; border-bottom: 1px solid #2a2a2a; }
            QTabBar::tab {
                background: transparent; color: #606060;
                border: none; padding: 10px 20px;
                font-size: 12px; font-weight: 600;
            }
            QTabBar::tab:selected {
                color: #f0f0f0; border-bottom: 2px solid #0078d4;
            }
            QTabBar::tab:hover:!selected { color: #909090; background: #1e1e1e; }
        """)
        self._tabs.addTab(self._build_manual_tab(),  "🎨  Manual")
        self._tabs.addTab(self._build_paint_tab(),   "🌿  Paint Collection")
        self._tabs.addTab(self._build_scheme_tab(),  "🖌  Paint Scheme")
        self._tabs.addTab(self._build_army_tab(),    "⚔  Army / Model")
        root.addWidget(self._tabs, stretch=1)

        # Live preview strip
        root.addWidget(self._build_preview_strip())

        # Footer with name + buttons
        root.addWidget(self._build_gen_footer())

    # ── Tab builders ─────────────────────────────────────────────────────────

    def _build_manual_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #1a1a1a;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(18)

        info = QLabel(
            "Pick any color — the system derives a complete dark palette from it, "
            "including backgrounds, borders, text hierarchy, and semantic tones."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #686868; font-size: 12px; background: transparent;")
        lay.addWidget(info)

        row = QHBoxLayout()
        row.setSpacing(14)

        self._manual_swatch = QPushButton()
        self._manual_swatch.setFixedSize(56, 56)
        self._manual_swatch.setCursor(Qt.PointingHandCursor)
        self._manual_swatch.setToolTip("Click to open the color wheel")
        self._manual_swatch.clicked.connect(self._manual_pick_color)
        row.addWidget(self._manual_swatch)

        vbox = QVBoxLayout()
        vbox.setSpacing(4)
        hex_lbl = QLabel("Hex Color")
        hex_lbl.setStyleSheet(
            "color: #606060; font-size: 10px; font-weight: 600; background: transparent;"
        )
        self._manual_hex = QLineEdit(self._accent_hex)
        self._manual_hex.setPlaceholderText("#RRGGBB")
        self._manual_hex.setFixedWidth(130)
        self._manual_hex.setStyleSheet(
            "QLineEdit { background: #242424; border: 1px solid #363636; "
            "border-radius: 5px; color: #f0f0f0; padding: 6px 10px; font-size: 14px; "
            "font-family: Consolas, monospace; }"
            "QLineEdit:focus { border-color: #0078d4; }"
        )
        self._manual_hex.textChanged.connect(self._manual_on_hex_typed)
        vbox.addWidget(hex_lbl)
        vbox.addWidget(self._manual_hex)
        row.addLayout(vbox)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()

        self._manual_update_swatch()
        return w

    def _build_paint_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #1a1a1a;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Search bar
        search_bar = QWidget()
        search_bar.setFixedHeight(44)
        search_bar.setStyleSheet(
            "QWidget { background: #161616; border-bottom: 1px solid #252525; }"
        )
        sb = QHBoxLayout(search_bar)
        sb.setContentsMargins(12, 7, 12, 7)
        self._paint_search = QLineEdit()
        self._paint_search.setPlaceholderText("Search by name or brand…")
        self._paint_search.setStyleSheet(
            "QLineEdit { background: #1e1e1e; border: 1px solid #363636; "
            "border-radius: 5px; color: #d8d8d8; padding: 5px 10px; }"
            "QLineEdit:focus { border-color: #0078d4; }"
        )
        self._paint_search.textChanged.connect(self._filter_paint_list)
        sb.addWidget(self._paint_search)
        lay.addWidget(search_bar)

        self._paint_list = QListWidget()
        self._paint_list.setFrameShape(QFrame.NoFrame)
        self._paint_list.setIconSize(QSize(16, 16))
        self._paint_list.setStyleSheet(_list_style())
        self._paint_list.currentItemChanged.connect(self._on_paint_selected)
        lay.addWidget(self._paint_list, stretch=1)
        return w

    def _build_scheme_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #1a1a1a;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Left — scheme list
        left = QWidget()
        left.setFixedWidth(240)
        left.setStyleSheet(
            "QWidget { background: #161616; border-right: 1px solid #252525; }"
        )
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        lhdr = QLabel("PAINT SCHEMES")
        lhdr.setStyleSheet(_cap_style())
        ll.addWidget(lhdr)

        self._scheme_list = QListWidget()
        self._scheme_list.setFrameShape(QFrame.NoFrame)
        self._scheme_list.setStyleSheet(_list_style(sidebar=True))
        self._scheme_list.currentItemChanged.connect(self._on_scheme_selected)
        ll.addWidget(self._scheme_list, stretch=1)
        lay.addWidget(left)

        # Right — steps
        right = QWidget()
        right.setStyleSheet("background: #1a1a1a;")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        rhdr = QLabel("STEPS — click a step to use its paint colour")
        rhdr.setStyleSheet(
            _cap_style() + " background: #161616; border-bottom: 1px solid #252525;"
        )
        rl.addWidget(rhdr)

        self._step_list = QListWidget()
        self._step_list.setFrameShape(QFrame.NoFrame)
        self._step_list.setIconSize(QSize(16, 16))
        self._step_list.setStyleSheet(_list_style())
        self._step_list.currentItemChanged.connect(self._on_step_selected)
        rl.addWidget(self._step_list, stretch=1)
        lay.addWidget(right, stretch=1)
        return w

    def _build_army_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #1a1a1a;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Left — army list
        left = QWidget()
        left.setFixedWidth(240)
        left.setStyleSheet(
            "QWidget { background: #161616; border-right: 1px solid #252525; }"
        )
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        lhdr = QLabel("ARMIES")
        lhdr.setStyleSheet(_cap_style())
        ll.addWidget(lhdr)

        self._army_list = QListWidget()
        self._army_list.setFrameShape(QFrame.NoFrame)
        self._army_list.setStyleSheet(_list_style(sidebar=True))
        self._army_list.currentItemChanged.connect(self._on_army_selected)
        ll.addWidget(self._army_list, stretch=1)
        lay.addWidget(left)

        # Right — linked paints
        right = QWidget()
        right.setStyleSheet("background: #1a1a1a;")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        rhdr = QLabel("LINKED PAINTS — click a paint to use its colour")
        rhdr.setStyleSheet(
            _cap_style() + " background: #161616; border-bottom: 1px solid #252525;"
        )
        rl.addWidget(rhdr)

        self._army_paint_list = QListWidget()
        self._army_paint_list.setFrameShape(QFrame.NoFrame)
        self._army_paint_list.setIconSize(QSize(16, 16))
        self._army_paint_list.setStyleSheet(_list_style())
        self._army_paint_list.currentItemChanged.connect(self._on_army_paint_selected)
        rl.addWidget(self._army_paint_list, stretch=1)
        lay.addWidget(right, stretch=1)
        return w

    # ── Preview strip ─────────────────────────────────────────────────────────

    def _build_preview_strip(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(52)
        frame.setStyleSheet(
            "QFrame { background: #111111; border-top: 1px solid #252525; }"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(5)

        preview_lbl = QLabel("PREVIEW")
        preview_lbl.setStyleSheet(
            "color: #3a3a3a; font-size: 9px; font-weight: 700; "
            "letter-spacing: 1px; background: transparent; min-width: 54px;"
        )
        lay.addWidget(preview_lbl)
        lay.addSpacing(6)

        self._prev_squares: list[QFrame] = []
        for _ in range(5):   # bg_deep, bg_raised, bg_input, border, accent
            sq = QFrame()
            sq.setFixedSize(26, 26)
            self._prev_squares.append(sq)
            lay.addWidget(sq)

        lay.addSpacing(14)

        self._prev_heading = QLabel("Heading")
        self._prev_body    = QLabel("Body text")
        self._prev_muted   = QLabel("Muted")
        for lbl in (self._prev_heading, self._prev_body, self._prev_muted):
            lbl.setStyleSheet("padding: 3px 8px; border-radius: 4px; font-size: 12px;")
            lay.addWidget(lbl)

        lay.addSpacing(8)

        self._prev_btn = QLabel("  Button  ")
        self._prev_btn.setStyleSheet(
            "border-radius: 4px; padding: 3px 10px; font-size: 11px; font-weight: 700;"
        )
        lay.addWidget(self._prev_btn)
        lay.addStretch()
        return frame

    def _update_preview(self):
        try:
            t = theme_from_paint_scheme(self._accent_hex, "_preview")
            c = t.colors
            colors = [c.bg_deep, c.bg_raised, c.bg_input, c.border, c.accent]
            for sq, col in zip(self._prev_squares, colors):
                sq.setStyleSheet(f"background: {col}; border-radius: 4px;")

            bg = c.bg_base
            self._prev_heading.setStyleSheet(
                f"color: {c.text_hi}; background: {bg}; padding: 3px 8px; "
                f"border-radius: 4px; font-size: 12px; font-weight: 700;"
            )
            self._prev_body.setStyleSheet(
                f"color: {c.text_mid}; background: {bg}; padding: 3px 8px; "
                f"border-radius: 4px; font-size: 12px;"
            )
            self._prev_muted.setStyleSheet(
                f"color: {c.text_lo}; background: {bg}; padding: 3px 8px; "
                f"border-radius: 4px; font-size: 11px;"
            )
            self._prev_btn.setStyleSheet(
                f"background: {c.accent}; color: #ffffff; border-radius: 4px; "
                f"padding: 3px 10px; font-size: 11px; font-weight: 700;"
            )
        except Exception:
            pass

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_gen_footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(60)
        bar.setStyleSheet(
            "QWidget { background: #111111; border-top: 1px solid #2a2a2a; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        name_lbl = QLabel("Theme name:")
        name_lbl.setStyleSheet(
            "color: #808080; font-size: 12px; background: transparent;"
        )
        lay.addWidget(name_lbl)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Ultramarines Blue")
        self._name_edit.setFixedWidth(240)
        self._name_edit.setStyleSheet(
            "QLineEdit { background: #1e1e1e; border: 1px solid #363636; "
            "border-radius: 5px; color: #f0f0f0; padding: 5px 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #0078d4; }"
        )
        self._name_edit.textEdited.connect(lambda _: setattr(self, "_name_is_auto", False))
        lay.addWidget(self._name_edit)
        lay.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedSize(90, 36)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #303030; "
            "border-radius: 5px; color: #909090; font-size: 13px; }"
            "QPushButton:hover { border-color: #484848; color: #d8d8d8; }"
        )
        btn_cancel.clicked.connect(self.reject)
        lay.addWidget(btn_cancel)

        btn_gen = QPushButton("🎨  Generate Theme")
        btn_gen.setFixedHeight(36)
        btn_gen.setMinimumWidth(160)
        btn_gen.setCursor(Qt.PointingHandCursor)
        btn_gen.setStyleSheet(
            "QPushButton { background: #0078d4; border: none; border-radius: 5px; "
            "color: #ffffff; font-size: 13px; font-weight: 700; padding: 0 20px; }"
            "QPushButton:hover { background: #1a8ee8; }"
            "QPushButton:pressed { background: #006abe; }"
        )
        btn_gen.clicked.connect(self._accept_generate)
        lay.addWidget(btn_gen)
        return bar

    # ── Data loading ─────────────────────────────────────────────────────────

    def _load_all_data(self):
        # Paints
        svc_p = self._ctx.services.get("paint_service")
        if svc_p:
            try:
                self._all_paints = sorted(
                    svc_p.get_all_paints(), key=lambda p: (p.brand, p.name)
                )
            except Exception:
                pass
        for p in self._all_paints:
            if p.id:
                self._paint_by_id[p.id] = p
        self._render_paint_list()

        # Schemes
        svc_s = self._ctx.services.get("scheme_service")
        if svc_s:
            try:
                self._all_schemes = sorted(
                    svc_s.get_all_schemes(), key=lambda s: s.name
                )
            except Exception:
                pass
        self._render_scheme_list()

        # Armies
        svc_a = self._ctx.services.get("army_service")
        if svc_a:
            try:
                self._all_armies = sorted(
                    svc_a.get_all_armies(), key=lambda a: a.name
                )
            except Exception:
                pass
        self._render_army_list()

    # ── Render helpers ────────────────────────────────────────────────────────

    def _render_paint_list(self, filter_text: str = ""):
        self._paint_list.clear()
        if not self._all_paints:
            _empty_item(self._paint_list, "Paint Tracker not loaded or no paints found")
            return
        ft = filter_text.strip().lower()
        shown = 0
        for p in self._all_paints:
            if ft and ft not in p.name.lower() and ft not in p.brand.lower():
                continue
            hex_col = _safe_hex(getattr(p, "color", None))
            item = QListWidgetItem(f"{p.brand}  —  {p.name}")
            item.setIcon(_make_color_icon(hex_col, 14))
            item.setData(Qt.UserRole,     hex_col)
            item.setData(Qt.UserRole + 1, f"{p.brand} {p.name}")
            item.setForeground(QColor("#d8d8d8"))
            self._paint_list.addItem(item)
            shown += 1
        if shown == 0:
            _empty_item(self._paint_list, "No paints match the search")

    def _render_scheme_list(self):
        self._scheme_list.clear()
        if not self._all_schemes:
            _empty_item(self._scheme_list, "No schemes found")
            return
        for s in self._all_schemes:
            item = QListWidgetItem(s.name)
            item.setData(Qt.UserRole, s.id)
            item.setData(Qt.UserRole + 1, s.name)
            item.setForeground(QColor("#d8d8d8"))
            self._scheme_list.addItem(item)

    def _render_army_list(self):
        self._army_list.clear()
        if not self._all_armies:
            _empty_item(self._army_list, "No armies found")
            return
        for a in self._all_armies:
            label = a.name
            sys = getattr(a, "game_system", "") or ""
            faction = getattr(a, "faction", "") or ""
            if sys:
                label += f"  ·  {sys}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, a.id)
            item.setData(Qt.UserRole + 1, a.name)
            item.setForeground(QColor("#d8d8d8"))
            self._army_list.addItem(item)

    # ── Selection handlers ────────────────────────────────────────────────────

    def _on_paint_selected(self, current, _prev):
        if not current:
            return
        hex_col = current.data(Qt.UserRole)
        label   = current.data(Qt.UserRole + 1) or ""
        if hex_col:
            self._set_accent(hex_col, label)
            self._auto_name(label)

    def _on_scheme_selected(self, current, _prev):
        if not current:
            return
        self._step_list.clear()
        scheme_id   = current.data(Qt.UserRole)
        scheme_name = current.data(Qt.UserRole + 1) or ""
        svc_s = self._ctx.services.get("scheme_service")
        if not svc_s:
            return
        try:
            steps = svc_s.get_steps(scheme_id)
        except Exception:
            return
        for step in sorted(steps, key=lambda s: s.step_order):
            paint_name = step.paint_name or "(no paint)"
            hex_col    = "#888888"
            if step.paint_id and step.paint_id in self._paint_by_id:
                p = self._paint_by_id[step.paint_id]
                hc = _safe_hex(getattr(p, "color", None))
                if hc != "#888888":
                    hex_col    = hc
                    paint_name = p.name
            technique = step.technique or ""
            label_str = f"{technique}  ·  {paint_name}" if technique else paint_name
            item = QListWidgetItem(label_str)
            item.setIcon(_make_color_icon(hex_col, 14))
            item.setData(Qt.UserRole,     hex_col)
            item.setData(Qt.UserRole + 1, scheme_name)
            if hex_col == "#888888":
                item.setForeground(QColor("#555555"))
                item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            else:
                item.setForeground(QColor("#d8d8d8"))
            self._step_list.addItem(item)
        if not steps:
            _empty_item(self._step_list, "No steps found for this scheme")

    def _on_step_selected(self, current, _prev):
        if not current:
            return
        hex_col     = current.data(Qt.UserRole)
        scheme_name = current.data(Qt.UserRole + 1) or ""
        if hex_col and hex_col != "#888888":
            self._set_accent(hex_col, scheme_name)
            self._auto_name(scheme_name)

    def _on_army_selected(self, current, _prev):
        if not current:
            return
        self._army_paint_list.clear()
        army_id   = current.data(Qt.UserRole)
        army_name = current.data(Qt.UserRole + 1) or ""
        svc_a = self._ctx.services.get("army_service")
        if not svc_a:
            return
        try:
            paint_dicts = svc_a.get_army_paint_list(army_id)
        except Exception:
            return
        seen: set[int] = set()
        for entry in paint_dicts:
            pid = entry.get("paint_id")
            if pid in seen or pid not in self._paint_by_id:
                continue
            seen.add(pid)
            p       = self._paint_by_id[pid]
            hex_col = _safe_hex(getattr(p, "color", None))
            item    = QListWidgetItem(f"{p.brand}  —  {p.name}")
            item.setIcon(_make_color_icon(hex_col, 14))
            item.setData(Qt.UserRole,     hex_col)
            item.setData(Qt.UserRole + 1, army_name)
            item.setForeground(QColor("#d8d8d8"))
            self._army_paint_list.addItem(item)
        if not seen:
            _empty_item(self._army_paint_list, "No paints linked to this army")

    def _on_army_paint_selected(self, current, _prev):
        if not current:
            return
        hex_col   = current.data(Qt.UserRole)
        army_name = current.data(Qt.UserRole + 1) or ""
        if hex_col:
            self._set_accent(hex_col, army_name)
            self._auto_name(army_name)

    # ── Manual tab handlers ───────────────────────────────────────────────────

    def _manual_pick_color(self):
        color = QColorDialog.getColor(
            QColor(self._accent_hex), self, "Pick a Color"
        )
        if color.isValid():
            self._accent_hex = color.name().upper()
            self._manual_hex.blockSignals(True)
            self._manual_hex.setText(self._accent_hex)
            self._manual_hex.blockSignals(False)
            self._manual_update_swatch()
            self._set_accent(self._accent_hex, "manual")

    def _manual_on_hex_typed(self, text: str):
        text = text.strip()
        if not text.startswith("#"):
            text = "#" + text
        if len(text) == 7:
            try:
                QColor(text)
                self._accent_hex = text.upper()
                self._manual_update_swatch()
                self._set_accent(self._accent_hex, "manual")
            except Exception:
                pass

    def _manual_update_swatch(self):
        self._manual_swatch.setStyleSheet(
            f"QPushButton {{ background: {self._accent_hex}; "
            f"border: 2px solid rgba(255,255,255,0.25); border-radius: 6px; }}"
            f"QPushButton:hover {{ border: 2px solid rgba(255,255,255,0.5); }}"
        )

    # ── State helpers ─────────────────────────────────────────────────────────

    def _set_accent(self, hex_color: str, source: str = ""):
        self._accent_hex   = hex_color
        self._source_label = source
        self._update_preview()

    def _auto_name(self, suggested: str):
        """Set the theme name field only if the user hasn't typed a custom name."""
        if self._name_is_auto and suggested:
            self._name_edit.setText(suggested)
            # keep flag True — still auto

    def _filter_paint_list(self, text: str):
        self._render_paint_list(filter_text=text)

    # ── Accept ────────────────────────────────────────────────────────────────

    def _accept_generate(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Please enter a theme name.")
            return
        self.result_hex    = self._accent_hex
        self.result_name   = name
        self.result_source = self._source_label
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
# ThemeEditorDialog
# ══════════════════════════════════════════════════════════════════════════════

class ThemeEditorDialog(QDialog):
    """
    Full theme manager dialog.

    Retrieves the ThemeManager from the ServiceRegistry via
    ``context.services.get("theme_manager")``.  All edits are kept in a local
    working copy; they are only persisted when the user clicks Save (or applied
    live with Apply).
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context         = context
        self._tm             = context.services.get("theme_manager")
        self._working_theme: Optional[Theme] = None
        self._swatches:       dict[str, _SwatchButton] = {}

        self.setWindowTitle("Theme Manager")
        self.setMinimumSize(940, 640)
        self.setModal(True)

        self._build_ui()
        self._populate_list()
        self._select_theme_by_id(self._tm.current_theme_id)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setObjectName("dialogTitleBar")
        title_bar.setFixedHeight(52)
        title_bar.setStyleSheet(
            "QWidget#dialogTitleBar { background: #0d0d0d; "
            "border-bottom: 1px solid #2a2a2a; }"
        )
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel("🎨  Theme Manager")
        lbl.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #f0f0f0; background: transparent;"
        )
        tb_lay.addWidget(lbl)
        root.addWidget(title_bar)

        # Body splitter
        body = QSplitter(Qt.Horizontal)
        body.setHandleWidth(1)
        body.setStyleSheet("QSplitter::handle { background: #2a2a2a; }")
        root.addWidget(body, stretch=1)

        body.addWidget(self._build_left_panel())
        body.addWidget(self._build_right_panel())
        body.setSizes([220, 720])
        body.setCollapsible(0, False)
        body.setCollapsible(1, False)

        root.addWidget(self._build_footer())

    # ── Left panel ────────────────────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(200)
        panel.setMaximumWidth(280)
        panel.setStyleSheet("QWidget { background: #161616; }")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr = QLabel("THEMES")
        hdr.setStyleSheet(
            "color: #606060; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1.5px; padding: 12px 14px 6px 14px; background: transparent;"
        )
        lay.addWidget(hdr)

        self._list = QListWidget()
        self._list.setFrameShape(QFrame.NoFrame)
        self._list.setIconSize(QSize(12, 12))
        self._list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                height: 36px;
                padding: 0 14px;
                color: #d8d8d8;
                border-radius: 0;
            }
            QListWidget::item:hover {
                background: #1e1e1e;
                color: #f0f0f0;
            }
            QListWidget::item:selected {
                background: #1a2e3a;
                color: #f0f0f0;
                border-left: 3px solid #0078d4;
                padding-left: 11px;
            }
        """)
        self._list.currentItemChanged.connect(self._on_theme_selected)
        lay.addWidget(self._list, stretch=1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border: none; border-top: 1px solid #262626;")
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        btn_bar = QWidget()
        btn_bar.setStyleSheet("background: #161616;")
        bb = QHBoxLayout(btn_bar)
        bb.setContentsMargins(8, 8, 8, 8)
        bb.setSpacing(6)

        self._btn_new = self._icon_btn("＋", "New blank theme")
        self._btn_dup = self._icon_btn("⧉", "Duplicate selected theme")
        self._btn_del = self._icon_btn("✕", "Delete selected theme", danger=True)
        self._btn_new.clicked.connect(self._new_theme)
        self._btn_dup.clicked.connect(self._duplicate_theme)
        self._btn_del.clicked.connect(self._delete_theme)

        bb.addWidget(self._btn_new)
        bb.addWidget(self._btn_dup)
        bb.addStretch()
        bb.addWidget(self._btn_del)
        lay.addWidget(btn_bar)
        return panel

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("QWidget { background: #1a1a1a; }")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("QWidget { background: transparent; }")
        self._right_lay = QVBoxLayout(content)
        self._right_lay.setContentsMargins(28, 22, 28, 22)
        self._right_lay.setSpacing(20)

        # Theme name row
        name_row = QHBoxLayout()
        name_lbl = QLabel("Theme Name")
        name_lbl.setStyleSheet(
            "color: #909090; font-size: 11px; font-weight: 600; min-width: 90px;"
        )
        name_row.addWidget(name_lbl)
        self._name_field = QLineEdit()
        self._name_field.setPlaceholderText("My Custom Theme")
        self._name_field.setStyleSheet(
            "QLineEdit { background: #242424; border: 1px solid #363636; "
            "border-radius: 5px; color: #f0f0f0; padding: 5px 10px; "
            "font-size: 14px; font-weight: 600; }"
            "QLineEdit:focus { border-color: #0078d4; }"
            "QLineEdit:disabled { color: #606060; background: #1c1c1c; }"
        )
        self._name_field.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self._name_field, stretch=1)
        self._right_lay.addLayout(name_row)

        # Read-only notice (shown for builtins)
        self._readonly_notice = QFrame()
        self._readonly_notice.setStyleSheet(
            "QFrame { background: #1c2633; border: 1px solid #2a3a4a; "
            "border-radius: 6px; }"
        )
        rn_lay = QHBoxLayout(self._readonly_notice)
        rn_lay.setContentsMargins(14, 10, 14, 10)
        rn_lay.setSpacing(10)
        lock_lbl = QLabel("🔒")
        lock_lbl.setStyleSheet("font-size: 14px; background: transparent;")
        rn_lay.addWidget(lock_lbl)
        notice_text = QLabel(
            "Built-in themes are read-only.  Duplicate this theme to create an editable copy."
        )
        notice_text.setStyleSheet(
            "color: #809ab8; font-size: 12px; background: transparent;"
        )
        notice_text.setWordWrap(True)
        rn_lay.addWidget(notice_text, stretch=1)
        dup_btn = QPushButton("Duplicate")
        dup_btn.setFixedSize(88, 30)
        dup_btn.setCursor(Qt.PointingHandCursor)
        dup_btn.setStyleSheet(
            "QPushButton { background: #1e3a5a; border: 1px solid #2a5a8a; "
            "border-radius: 4px; color: #4a9eff; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #254a72; border-color: #4a9eff; }"
        )
        dup_btn.clicked.connect(self._duplicate_theme)
        rn_lay.addWidget(dup_btn)
        self._readonly_notice.setVisible(False)
        self._right_lay.addWidget(self._readonly_notice)

        # Colors section
        self._right_lay.addWidget(self._section_header("Colors"))
        self._color_grid_widget = QWidget()
        self._color_grid_widget.setStyleSheet("background: transparent;")
        self._right_lay.addWidget(self._color_grid_widget)

        # Typography section
        self._right_lay.addWidget(self._section_header("Typography"))
        self._typo_widget = QWidget()
        self._typo_widget.setStyleSheet("background: transparent;")
        self._right_lay.addWidget(self._typo_widget)

        # Shape section
        self._right_lay.addWidget(self._section_header("Shape / Radii"))
        self._shape_widget = QWidget()
        self._shape_widget.setStyleSheet("background: transparent;")
        self._right_lay.addWidget(self._shape_widget)

        self._right_lay.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)
        return container

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet(
            "QWidget { background: #111111; border-top: 1px solid #2a2a2a; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(8)

        # Generate from paint
        self._btn_paint = QPushButton("🎨  Generate from Color")
        self._btn_paint.setFixedHeight(36)
        self._btn_paint.setCursor(Qt.PointingHandCursor)
        self._btn_paint.setStyleSheet(self._accent_btn_style())
        self._btn_paint.clicked.connect(self._generate_from_paint)
        lay.addWidget(self._btn_paint)

        # Export
        btn_export = QPushButton("⬆  Export")
        btn_export.setFixedSize(90, 36)
        btn_export.setCursor(Qt.PointingHandCursor)
        btn_export.setStyleSheet(self._secondary_btn_style())
        btn_export.setToolTip("Save the selected theme as a .json file")
        btn_export.clicked.connect(self._export_theme)
        lay.addWidget(btn_export)

        # Import
        btn_import = QPushButton("⬇  Import")
        btn_import.setFixedSize(90, 36)
        btn_import.setCursor(Qt.PointingHandCursor)
        btn_import.setStyleSheet(self._secondary_btn_style())
        btn_import.setToolTip("Load a theme .json file")
        btn_import.clicked.connect(self._import_theme)
        lay.addWidget(btn_import)

        lay.addStretch()

        self._btn_apply = QPushButton("Apply")
        self._btn_apply.setFixedSize(90, 36)
        self._btn_apply.setCursor(Qt.PointingHandCursor)
        self._btn_apply.setStyleSheet(self._secondary_btn_style())
        self._btn_apply.clicked.connect(self._apply_theme)
        lay.addWidget(self._btn_apply)

        self._btn_save = QPushButton("Save")
        self._btn_save.setFixedSize(90, 36)
        self._btn_save.setCursor(Qt.PointingHandCursor)
        self._btn_save.setStyleSheet(self._primary_btn_style())
        self._btn_save.clicked.connect(self._save_theme)
        lay.addWidget(self._btn_save)

        btn_close = QPushButton("Close")
        btn_close.setFixedSize(90, 36)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(self._ghost_btn_style())
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close)

        return bar

    # ── Color grid ────────────────────────────────────────────────────────────

    _COLOR_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
        ("Backgrounds", [
            ("bg_deep",    "Deepest surface"),
            ("bg_base",    "Base surface"),
            ("bg_raised",  "Raised surface"),
            ("bg_input",   "Input / form"),
            ("header_bg",  "Header bar"),
            ("card_bg",    "Card surface"),
            ("sidebar_bg", "Sidebar"),
        ]),
        ("Borders", [
            ("border",    "Default border"),
            ("border_hi", "Highlighted border"),
        ]),
        ("Text", [
            ("text_hi",  "High emphasis"),
            ("text_mid", "Medium emphasis"),
            ("text_lo",  "Low emphasis"),
            ("text_dim", "Dim / placeholder"),
        ]),
        ("Accent", [
            ("accent",    "Primary accent"),
            ("accent_hi", "Accent hover"),
            ("accent_lo", "Accent subtle bg"),
        ]),
        ("Semantic", [
            ("danger",    "Danger"),
            ("danger_hi", "Danger hover"),
            ("danger_lo", "Danger subtle bg"),
            ("success",   "Success"),
            ("warning",   "Warning"),
        ]),
    ]

    def _build_color_grid(self, colors: ThemeColors, readonly: bool):
        if self._color_grid_widget.layout():
            old = self._color_grid_widget.layout()
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QWidget().setLayout(old)

        self._swatches.clear()
        grid = QGridLayout(self._color_grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(14)

        row = 0
        for group_name, tokens in self._COLOR_GROUPS:
            grp_lbl = QLabel(group_name.upper())
            grp_lbl.setStyleSheet(
                "color: #484848; font-size: 10px; font-weight: 700; "
                "letter-spacing: 1px; background: transparent;"
            )
            grid.addWidget(grp_lbl, row, 0, 1, 4)
            row += 1

            col = 0
            for token, tooltip in tokens:
                cell = QWidget()
                cell.setStyleSheet("background: transparent;")
                cl = QVBoxLayout(cell)
                cl.setContentsMargins(0, 0, 0, 0)
                cl.setSpacing(4)

                hex_val = getattr(colors, token, "#000000")
                swatch  = _SwatchButton(token, hex_val)
                swatch.setEnabled(not readonly)
                swatch.setToolTip(f"{token}: {hex_val}\n{tooltip}")
                self._swatches[token] = swatch

                lbl = QLabel(token.replace("_", "\u200b_"))
                lbl.setAlignment(Qt.AlignHCenter)
                lbl.setStyleSheet(
                    "color: #606060; font-size: 9px; background: transparent; max-width: 70px;"
                )
                lbl.setWordWrap(True)

                cl.addWidget(swatch, alignment=Qt.AlignHCenter)
                cl.addWidget(lbl)
                grid.addWidget(cell, row, col)

                col += 1
                if col >= 7:
                    col = 0
                    row += 1

            if col != 0:
                row += 1

    # ── Typography builder ────────────────────────────────────────────────────

    def _build_typo_panel(self, typo: ThemeTypography, readonly: bool):
        if self._typo_widget.layout():
            old = self._typo_widget.layout()
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QWidget().setLayout(old)

        self._typo_fields: dict[str, QLineEdit | QSpinBox] = {}

        def _field_style(disabled=False):
            if disabled:
                return (
                    "QLineEdit { background: #1c1c1c; border: 1px solid #2a2a2a; "
                    "color: #606060; border-radius: 4px; padding: 4px 8px; }"
                )
            return (
                "QLineEdit { background: #242424; border: 1px solid #363636; "
                "border-radius: 4px; color: #f0f0f0; padding: 4px 8px; }"
                "QLineEdit:focus { border-color: #0078d4; }"
            )

        form = QFormLayout(self._typo_widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        for key, label in [("font_family", "UI Font"), ("font_mono", "Mono Font")]:
            w = QLineEdit(str(getattr(typo, key)))
            w.setEnabled(not readonly)
            w.setStyleSheet(_field_style(readonly))
            w.textChanged.connect(lambda v, k=key: self._on_typo_changed(k, v))
            self._typo_fields[key] = w
            form.addRow(label + ":", w)

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        for key, label in [
            ("font_xs", "xs"), ("font_sm", "sm"), ("font_base", "base"),
            ("font_lg", "lg"), ("font_xl", "xl"), ("font_2xl", "2xl"), ("font_3xl", "3xl"),
        ]:
            col_w = QVBoxLayout()
            col_w.setSpacing(3)
            sp = QSpinBox()
            sp.setRange(6, 48)
            sp.setValue(int(getattr(typo, key)))
            sp.setEnabled(not readonly)
            sp.setFixedWidth(52)
            sp.setAlignment(Qt.AlignCenter)
            sp.setStyleSheet(
                "QSpinBox { background: #242424; border: 1px solid #363636; "
                "border-radius: 4px; color: #f0f0f0; padding: 2px 4px; }"
                "QSpinBox:disabled { background: #1c1c1c; color: #606060; }"
                "QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }"
            )
            sp.valueChanged.connect(lambda v, k=key: self._on_typo_changed(k, v))
            self._typo_fields[key] = sp

            sz_lbl = QLabel(label)
            sz_lbl.setAlignment(Qt.AlignHCenter)
            sz_lbl.setStyleSheet("color: #505050; font-size: 9px; background: transparent;")
            col_w.addWidget(sp)
            col_w.addWidget(sz_lbl)
            size_row.addLayout(col_w)
        size_row.addStretch()
        form.addRow("Sizes (px):", _wrap(size_row))

    # ── Shape builder ─────────────────────────────────────────────────────────

    def _build_shape_panel(self, shape: ThemeShape, readonly: bool):
        if self._shape_widget.layout():
            old = self._shape_widget.layout()
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QWidget().setLayout(old)

        self._shape_fields: dict[str, QSpinBox] = {}
        lay = QHBoxLayout(self._shape_widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        for key, label in [
            ("radius_xs", "xs"), ("radius_sm", "sm"), ("radius_base", "base"),
            ("radius_lg", "lg"), ("radius_xl", "xl"),
        ]:
            col_w = QVBoxLayout()
            col_w.setSpacing(3)
            sp = QSpinBox()
            sp.setRange(0, 32)
            sp.setValue(int(getattr(shape, key)))
            sp.setEnabled(not readonly)
            sp.setFixedWidth(60)
            sp.setAlignment(Qt.AlignCenter)
            sp.setSuffix(" px")
            sp.setStyleSheet(
                "QSpinBox { background: #242424; border: 1px solid #363636; "
                "border-radius: 4px; color: #f0f0f0; padding: 2px 4px; }"
                "QSpinBox:disabled { background: #1c1c1c; color: #606060; }"
                "QSpinBox::up-button, QSpinBox::down-button { width: 14px; }"
            )
            sp.valueChanged.connect(lambda v, k=key: self._on_shape_changed(k, v))
            self._shape_fields[key] = sp

            sh_lbl = QLabel(label)
            sh_lbl.setAlignment(Qt.AlignHCenter)
            sh_lbl.setStyleSheet("color: #505050; font-size: 9px; background: transparent;")
            col_w.addWidget(sp)
            col_w.addWidget(sh_lbl)
            lay.addLayout(col_w)
        lay.addStretch()

    # ── Population helpers ────────────────────────────────────────────────────

    def _populate_list(self):
        self._list.blockSignals(True)
        self._list.clear()
        for tid, theme in self._tm.themes.items():
            item = QListWidgetItem(theme.meta.name)
            item.setData(Qt.UserRole, tid)
            item.setIcon(_make_color_icon(theme.colors.accent, 12))
            if theme.meta.builtin:
                item.setForeground(QColor("#7a88a8"))
            else:
                item.setForeground(QColor("#d8d8d8"))
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _select_theme_by_id(self, theme_id: str):
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.UserRole) == theme_id:
                self._list.setCurrentRow(i)
                return
        if self._list.count():
            self._list.setCurrentRow(0)

    def _load_theme_into_editor(self, theme: Theme):
        readonly = theme.meta.builtin
        self._name_field.blockSignals(True)
        self._name_field.setText(theme.meta.name)
        self._name_field.setEnabled(not readonly)
        self._name_field.blockSignals(False)

        self._readonly_notice.setVisible(readonly)

        self._build_color_grid(theme.colors, readonly)
        self._build_typo_panel(theme.typography, readonly)
        self._build_shape_panel(theme.shape, readonly)

        self._btn_save.setEnabled(not readonly)
        self._btn_del.setEnabled(not readonly)

        accent = theme.colors.accent
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                height: 36px;
                padding: 0 14px;
                color: #d8d8d8;
                border-radius: 0;
            }}
            QListWidget::item:hover {{
                background: #1e1e1e;
                color: #f0f0f0;
            }}
            QListWidget::item:selected {{
                background: {theme.colors.accent_lo};
                color: #f0f0f0;
                border-left: 3px solid {accent};
                padding-left: 11px;
            }}
        """)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_theme_selected(self, current: QListWidgetItem, _previous):
        if not current:
            return
        tid      = current.data(Qt.UserRole)
        original = self._tm.themes.get(tid)
        if not original:
            return
        self._working_theme = copy.deepcopy(original)
        self._load_theme_into_editor(self._working_theme)

    def _on_name_changed(self, text: str):
        if self._working_theme:
            self._working_theme.meta.name = text
            item = self._list.currentItem()
            if item:
                item.setText(text)

    def _on_typo_changed(self, key: str, value):
        if self._working_theme:
            setattr(self._working_theme.typography, key, value)

    def _on_shape_changed(self, key: str, value: int):
        if self._working_theme:
            setattr(self._working_theme.shape, key, value)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _sync_swatches_to_working(self):
        if not self._working_theme:
            return
        for token, swatch in self._swatches.items():
            setattr(self._working_theme.colors, token, swatch.hex_color)

    def _apply_theme(self):
        if not self._working_theme:
            return
        self._sync_swatches_to_working()
        tid = self._working_theme.meta.id
        if not self._working_theme.meta.builtin:
            self._tm.save_theme(self._working_theme)
        self._tm.apply_theme(tid)

    def _save_theme(self):
        if not self._working_theme:
            return
        if self._working_theme.meta.builtin:
            QMessageBox.information(
                self, "Built-in theme",
                "Built-in themes cannot be modified.\n"
                "Use Duplicate to create an editable copy."
            )
            return
        self._sync_swatches_to_working()
        self._tm.save_theme(self._working_theme)
        current_id = self._working_theme.meta.id
        self._populate_list()
        self._select_theme_by_id(current_id)

    def _new_theme(self):
        name, ok = _input_dialog(self, "New Theme", "Theme name:")
        if not ok or not name.strip():
            return
        theme = self._tm.create_blank(name.strip())
        self._tm.save_theme(theme)
        self._populate_list()
        self._select_theme_by_id(theme.meta.id)

    def _duplicate_theme(self):
        if not self._working_theme:
            return
        name, ok = _input_dialog(
            self, "Duplicate Theme",
            "Name for the new copy:",
            default=f"{self._working_theme.meta.name} Copy"
        )
        if not ok or not name.strip():
            return
        self._sync_swatches_to_working()
        new_theme = self._tm.create_copy(name.strip(), self._working_theme.meta.id)
        self._tm.save_theme(new_theme)
        self._populate_list()
        self._select_theme_by_id(new_theme.meta.id)

    def _delete_theme(self):
        if not self._working_theme or self._working_theme.meta.builtin:
            return
        tid  = self._working_theme.meta.id
        name = self._working_theme.meta.name
        reply = QMessageBox.question(
            self, "Delete theme",
            f"Delete \"{name}\"? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel
        )
        if reply != QMessageBox.Yes:
            return
        self._tm.delete_theme(tid)
        self._working_theme = None
        self._populate_list()
        if self._list.count():
            self._list.setCurrentRow(0)

    def _generate_from_paint(self):
        dlg = _GenerateDialog(self.context, self)
        if dlg.exec() != QDialog.Accepted:
            return
        theme = self._tm.generate_from_paint(
            dlg.result_hex,
            dlg.result_name,
            dlg.result_source,
        )
        self._tm.save_theme(theme)
        self._populate_list()
        self._select_theme_by_id(theme.meta.id)
        self._tm.apply_theme(theme.meta.id)

    # ── Export / Import ───────────────────────────────────────────────────────

    def _export_theme(self):
        if not self._working_theme:
            return
        safe  = self._working_theme.meta.id.replace("/", "_")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Theme",
            f"{safe}.json",
            "Theme Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            self._sync_swatches_to_working()
            text = json.dumps(
                self._working_theme.to_dict(), indent=2, ensure_ascii=False
            )
            Path(path).write_text(text, encoding="utf-8")
            QMessageBox.information(
                self, "Exported",
                f"Theme \"{self._working_theme.meta.name}\" saved to:\n{path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _import_theme(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Theme",
            "",
            "Theme Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            # Validate basic structure
            if "meta" not in data or "colors" not in data:
                raise ValueError("File does not look like a valid theme (missing 'meta' or 'colors').")

            # Force it to be a user (non-builtin) theme so it can be edited/deleted
            data["meta"]["builtin"] = False
            if not data["meta"].get("author"):
                data["meta"]["author"] = "Imported"

            theme = Theme.from_dict(data)

            # If a theme with this ID already exists, ask to rename
            if theme.meta.id in self._tm.themes:
                name, ok = _input_dialog(
                    self, "Theme already exists",
                    "A theme with this ID already exists.\nEnter a new name:",
                    default=f"{theme.meta.name} (Imported)"
                )
                if not ok:
                    return
                import re
                safe = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
                theme.meta.id   = f"user_{safe}"
                theme.meta.name = name.strip() or theme.meta.name

            self._tm.save_theme(theme)
            self._populate_list()
            self._select_theme_by_id(theme.meta.id)
            QMessageBox.information(
                self, "Imported",
                f"Theme \"{theme.meta.name}\" has been imported."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))

    # ── Style helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _section_header(title: str) -> QLabel:
        lbl = QLabel(title.upper())
        lbl.setStyleSheet(
            "color: #505050; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1.5px; padding-top: 4px; background: transparent; "
            "border-bottom: 1px solid #2a2a2a; padding-bottom: 6px;"
        )
        return lbl

    @staticmethod
    def _icon_btn(icon: str, tooltip: str, danger: bool = False) -> QPushButton:
        btn = QPushButton(icon)
        btn.setFixedSize(30, 30)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        color = "#e05555" if danger else "#909090"
        hover = "#eb6868" if danger else "#d8d8d8"
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid #2a2a2a; "
            f"border-radius: 4px; color: {color}; font-size: 14px; }}"
            f"QPushButton:hover {{ background: #222222; color: {hover}; }}"
        )
        return btn

    @staticmethod
    def _primary_btn_style() -> str:
        return (
            "QPushButton { background: #0078d4; border: none; border-radius: 5px; "
            "color: #ffffff; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #1a8ee8; }"
            "QPushButton:pressed { background: #006abe; }"
            "QPushButton:disabled { background: #1e1e1e; color: #505050; }"
        )

    @staticmethod
    def _secondary_btn_style() -> str:
        return (
            "QPushButton { background: #252525; border: 1px solid #363636; border-radius: 5px; "
            "color: #d8d8d8; font-size: 13px; }"
            "QPushButton:hover { background: #2e2e2e; border-color: #484848; }"
            "QPushButton:pressed { background: #1e1e1e; }"
        )

    @staticmethod
    def _ghost_btn_style() -> str:
        return (
            "QPushButton { background: transparent; border: 1px solid #303030; border-radius: 5px; "
            "color: #909090; font-size: 13px; }"
            "QPushButton:hover { border-color: #484848; color: #d8d8d8; }"
        )

    @staticmethod
    def _accent_btn_style() -> str:
        return (
            "QPushButton { background: #1a2e1a; border: 1px solid #2e5a2e; border-radius: 5px; "
            "color: #3dba6e; font-size: 13px; font-weight: 600; padding: 0 16px; }"
            "QPushButton:hover { background: #1e3a1e; border-color: #3dba6e; }"
        )


# ── Module-level helpers ───────────────────────────────────────────────────────

def _safe_hex(color: Optional[str], fallback: str = "#888888") -> str:
    """Return hex_color if it looks valid, else fallback."""
    if color and isinstance(color, str) and color.startswith("#") and len(color) in (4, 7):
        try:
            QColor(color)
            return color.upper()
        except Exception:
            pass
    return fallback


def _empty_item(lst: QListWidget, text: str):
    item = QListWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
    item.setForeground(QColor("#505050"))
    lst.addItem(item)


def _list_style(sidebar: bool = False) -> str:
    bg = "transparent" if sidebar else "#1a1a1a"
    return f"""
        QListWidget {{
            background: {bg};
            border: none;
            outline: none;
        }}
        QListWidget::item {{
            height: 36px;
            padding: 0 14px;
            color: #d8d8d8;
        }}
        QListWidget::item:hover {{
            background: #212121;
            color: #f0f0f0;
        }}
        QListWidget::item:selected {{
            background: #1a2e3a;
            color: #f0f0f0;
            border-left: 3px solid #0078d4;
            padding-left: 11px;
        }}
        QListWidget::item:disabled {{
            color: #484848;
        }}
    """


def _cap_style() -> str:
    return (
        "color: #484848; font-size: 9px; font-weight: 700; "
        "letter-spacing: 1.5px; padding: 10px 14px 6px 14px; background: transparent;"
    )


def _wrap(layout) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    w.setLayout(layout)
    return w


def _input_dialog(parent, title: str, prompt: str, default: str = "") -> tuple[str, bool]:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setFixedWidth(360)
    lay = QVBoxLayout(dlg)
    lay.setSpacing(12)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.addWidget(QLabel(prompt))
    edit = QLineEdit(default)
    edit.selectAll()
    lay.addWidget(edit)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)
    ok = dlg.exec() == QDialog.Accepted
    return edit.text(), ok
