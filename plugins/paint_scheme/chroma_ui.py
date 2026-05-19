# plugins/paint_scheme/chroma_ui.py
"""
Chroma Codex UI — Intelligent Paint Planning Interface
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

import json
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QRect
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QBrush, QPalette, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
    QFrame, QScrollArea, QSizePolicy, QSplitter, QColorDialog, QMessageBox,
    QGridLayout, QTabWidget, QSlider, QApplication,
)

from .chroma_codex import (
    engine as chroma_engine,
    SCHEME_STYLES, STYLE_DESCRIPTIONS, ROLES, ROLE_META,
    RoleRecommendation, PaintMatch, ChromaResult,
    hex_to_hsl, hsl_to_hex, _target_hsl, color_distance,
    _GOOD_MATCH, _ALT_COUNT,
)


# ── Personality system ────────────────────────────────────────────────────────

PERSONALITIES: list[str] = [
    "",
    "Regal", "Grimdark", "Noble", "Savage", "Ancient",
    "Corrupted", "Holy", "Industrial", "Arcane", "Feral",
    "Spectral", "Veteran", "Pristine", "Forsaken",
]

_PERSONALITY_META: dict[str, tuple[str, str, str]] = {
    "Regal":      ("#3a1854", "#d4a0f0", "👑"),
    "Grimdark":   ("#1c1c1c", "#909090", "💀"),
    "Noble":      ("#122040", "#7ab0f0", "⚜"),
    "Savage":     ("#3d1005", "#f08050", "🔥"),
    "Ancient":    ("#2e1e05", "#c8a040", "🏛"),
    "Corrupted":  ("#0a1e0a", "#5ec85e", "☣"),
    "Holy":       ("#2c2808", "#f0e060", "✝"),
    "Industrial": ("#14181c", "#8090a0", "⚙"),
    "Arcane":     ("#14083a", "#9868f0", "🔮"),
    "Feral":      ("#121e08", "#80a040", "🐾"),
    "Spectral":   ("#08121e", "#60c0f8", "👻"),
    "Veteran":    ("#1e1008", "#a07840", "🎖"),
    "Pristine":   ("#08202e", "#60d8f8", "⭐"),
    "Forsaken":   ("#120828", "#9060a8", "🌑"),
}


# ── Palette math helpers ──────────────────────────────────────────────────────

def _derive_palette_swatches(
    primary_hex: str, style: str,
    overrides: dict[str, str] | None = None,
    roles: tuple = ("primary", "armor_trim", "cloth", "shade", "highlight", "glow"),
) -> list[str]:
    """Compute target hex colors for key roles — pure math, no DB needed."""
    try:
        ph, ps, pl = hex_to_hsl(primary_hex)
        result = []
        for r in roles:
            if overrides and r in overrides:
                result.append(overrides[r])
            else:
                result.append(hsl_to_hex(*_target_hsl(r, ph, ps, pl, style)))
        return result
    except Exception:
        return [primary_hex] * len(roles)


def _apply_overrides_to_result(
    result: ChromaResult,
    overrides: dict[str, str],
    owned_paints: list,
) -> ChromaResult:
    """Apply manual target-color overrides to a ChromaResult, re-matching each role."""
    for role, hex_override in overrides.items():
        rec = result.recommendations.get(role)
        if rec is None:
            continue
        scored: list[tuple[float, PaintMatch]] = []
        for p in owned_paints:
            color = getattr(p, "color", None)
            if not color or not color.startswith("#"):
                continue
            dist = color_distance(hex_override, color)
            qty = getattr(p, "quantity", 1) or 1
            scored.append((dist, PaintMatch(
                paint_id=p.id,
                paint_name=getattr(p, "name", "?"),
                brand=getattr(p, "brand", ""),
                color_hex=color,
                distance=round(dist, 4),
                quantity=qty,
                level=getattr(p, "level", None),
                is_low=qty <= 1,
            )))
        scored.sort(key=lambda x: x[0])
        best = scored[0][1] if scored and scored[0][0] < _GOOD_MATCH else None
        alts = [pm for _, pm in scored[1: _ALT_COUNT + 1]] if scored else []
        result.recommendations[role] = RoleRecommendation(
            role=role, icon=rec.icon, label=rec.label,
            target_hex=hex_override,
            best_match=best,
            alternatives=alts,
        )
    return result


# ── Micro helpers ─────────────────────────────────────────────────────────────

def _hline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine); f.setObjectName("hSep")
    return f


def _swatch(hex_color: str, size: int = 20, border_radius: int = 4) -> QLabel:
    lbl = QLabel(); lbl.setFixedSize(size, size)
    c = hex_color if (hex_color and hex_color.startswith("#") and len(hex_color) == 7) else "#3a3a3a"
    bright = QColor(c).lightness()
    border = "rgba(255,255,255,0.18)" if bright < 100 else "rgba(0,0,0,0.25)"
    lbl.setStyleSheet(f"background:{c}; border:1px solid {border}; border-radius:{border_radius}px;")
    lbl.setToolTip(c)
    return lbl


def _badge(text: str, bg: str, fg: str = "#ffffff") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background:{bg}; color:{fg}; border-radius:3px;"
        f" padding:1px 6px; font-size:10px; font-weight:700;"
    )
    lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return lbl


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size:13px; font-weight:700; color:#d0d0d0; background:transparent;")
    return lbl


def _field_lbl(text: str) -> QLabel:
    lbl = QLabel(text); lbl.setObjectName("fieldLabel")
    return lbl


# ── Bleed-safe color swatch ───────────────────────────────────────────────────

class _ColorSwatchWidget(QWidget):
    """
    Paints a solid color preview with QPainter — never via setStyleSheet.

    Using setStyleSheet("background: <color>") on a child widget in Qt on
    Windows causes the palette engine to propagate that color upward through
    ancestor widgets (the 'bleed' bug).  QPainter-based rendering is fully
    isolated to this widget's own paint surface and cannot affect parents.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor("#888888")
        self._hex_text = "#888888"
        self.setFixedHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Opaque paint event — we own every pixel, nothing leaks through
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_color(self, hex_str: str):
        self._color = QColor(hex_str)
        self._hex_text = hex_str.upper()
        self.update()   # schedules a repaint — no palette write

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # ── Background from parent palette so we don't create dead space ───
        bg = self.palette().color(QPalette.Window)
        p.fillRect(self.rect(), bg)

        # ── Colour fill ─────────────────────────────────────────────────────
        inner = self.rect().adjusted(2, 2, -2, -2)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(inner, 8, 8)

        # ── Subtle border ────────────────────────────────────────────────────
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        p.drawRoundedRect(inner, 8, 8)

        # ── Hex text — auto-contrast ─────────────────────────────────────────
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        text_qc = QColor("#111111") if brightness > 145 else QColor("#f0f0f0")
        p.setPen(text_qc)
        f = QFont(self.font())
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(inner, Qt.AlignCenter, self._hex_text)
        p.end()


# ── Owned-paint swatch chip (small, painted) ──────────────────────────────────

class _PaintChip(QWidget):
    """22×22 colour chip painted with QPainter — no stylesheet background."""

    def __init__(self, hex_str: str = "#888888", parent=None):
        super().__init__(parent)
        self._color = QColor(hex_str)
        self.setFixedSize(24, 24)

    def set_color(self, hex_str: str):
        self._color = QColor(hex_str)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = self.palette().color(QPalette.Window)
        p.fillRect(self.rect(), bg)
        inner = self.rect().adjusted(1, 1, -1, -1)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(inner, 4, 4)
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(inner, 4, 4)
        p.end()


# ── Primary color + paint picker dialog ───────────────────────────────────────

class _PrimaryPickerDialog(QDialog):
    """
    Two-tab dialog for choosing the scheme's primary color.

    Theme safety strategy
    ─────────────────────
    The QPalette bleed bug: on Windows, calling setStyleSheet("background: X")
    on any child widget can cause Qt's paint system to propagate X up through
    ancestor widget backgrounds if the ancestor has no explicit palette locked.

    Three-layer defence used here:
      1. Dialog palette is locked at __init__ time by copying QApplication's
         palette and calling setAutoFillBackground(True). No child can override
         this once it is set.
      2. The colour preview swatch is a custom QPainter widget (_ColorSwatchWidget)
         that never writes to any palette or stylesheet.
      3. The owned-paint chip (_PaintChip) is also QPainter-based for the
         same reason.
    """

    def __init__(self, current_hex: str, context, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Primary Color")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(480)
        self._context = context
        self._selected_hex = current_hex
        self._all_paints: list = []
        self._guard = False   # re-entrancy guard for slider ↔ hex sync

        # ── Isolate this dialog from parent's stylesheet cascade ─────────────
        # The parent widget (_ColorPickerBtn) has setStyleSheet("background:#RRGGBB")
        # on itself, which Qt cascades into child windows.  Setting our own
        # objectName and an explicit stylesheet here makes OUR rule more
        # specific than the parent's rule, so it always wins.
        self.setObjectName("primaryPickerDialog")
        # Explicit empty-string stylesheet on THIS widget breaks the parent cascade.
        # The theme_manager QSS rule for #primaryPickerDialog then applies cleanly.
        self.setStyleSheet("")

        self._build(current_hex)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self, current_hex: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        root.addWidget(tabs, stretch=1)

        tabs.addTab(self._build_picker_tab(current_hex), "🎨  Color Picker")
        tabs.addTab(self._build_paint_tab(current_hex),  "🪣  From Owned Paints")

        # Divider line above buttons
        line = QFrame(); line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: rgba(255,255,255,0.08);")
        root.addWidget(line)

        btn_bar = QWidget()
        btn_lay = QHBoxLayout(btn_bar)
        btn_lay.setContentsMargins(12, 10, 12, 10)
        btn_lay.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btn_lay.addWidget(btns)
        root.addWidget(btn_bar)

        QTimer.singleShot(0, self._load_paints)

    # ── Tab 1: HSL color picker ───────────────────────────────────────────────

    def _build_picker_tab(self, current_hex: str) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)

        # ── Swatch (custom painted — zero palette bleed) ──────────────────────
        self._swatch = _ColorSwatchWidget()
        lay.addWidget(self._swatch)

        # ── Hex input ─────────────────────────────────────────────────────────
        hex_frame = QFrame()
        hex_frame.setObjectName("pickerSection")
        hex_lay = QHBoxLayout(hex_frame)
        hex_lay.setContentsMargins(10, 8, 10, 8)
        hex_lay.setSpacing(10)

        hex_lbl = QLabel("Hex")
        hex_lbl.setFixedWidth(24)
        hex_lay.addWidget(hex_lbl)

        self._hex_edit = QLineEdit(current_hex.upper())
        self._hex_edit.setFixedWidth(100)
        self._hex_edit.setMaxLength(7)
        self._hex_edit.setPlaceholderText("#RRGGBB")
        self._hex_edit.editingFinished.connect(self._on_hex_committed)
        hex_lay.addWidget(self._hex_edit)
        hex_lay.addStretch()
        lay.addWidget(hex_frame)

        # ── HSL sliders ───────────────────────────────────────────────────────
        slider_frame = QFrame()
        slider_frame.setObjectName("pickerSection")
        sf_lay = QVBoxLayout(slider_frame)
        sf_lay.setContentsMargins(10, 10, 10, 10)
        sf_lay.setSpacing(10)

        h0, s0, l0 = hex_to_hsl(current_hex)
        self._sl_h, self._lbl_h = self._make_slider(0, 360, int(round(h0)))
        self._sl_s, self._lbl_s = self._make_slider(0, 100, int(round(s0)))
        self._sl_l, self._lbl_l = self._make_slider(0, 100, int(round(l0)))

        for name, sl, vl in [
            ("Hue",        self._sl_h, self._lbl_h),
            ("Saturation", self._sl_s, self._lbl_s),
            ("Lightness",  self._sl_l, self._lbl_l),
        ]:
            row = QHBoxLayout(); row.setSpacing(8)
            name_lbl = QLabel(name)
            name_lbl.setFixedWidth(82)
            row.addWidget(name_lbl)
            row.addWidget(sl, stretch=1)
            vl.setFixedWidth(34)
            vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(vl)
            sf_lay.addLayout(row)

        self._sl_h.valueChanged.connect(self._on_slider_changed)
        self._sl_s.valueChanged.connect(self._on_slider_changed)
        self._sl_l.valueChanged.connect(self._on_slider_changed)
        lay.addWidget(slider_frame)

        # ── Color wheel escape hatch ───────────────────────────────────────────
        wheel_btn = QPushButton("  Open Full Color Wheel…")
        wheel_btn.setObjectName("wheelBtn")
        wheel_btn.setToolTip(
            "Opens Qt's color wheel as a separate window.\n"
            "The chosen color is applied back here automatically."
        )
        wheel_btn.clicked.connect(self._open_color_wheel)
        lay.addWidget(wheel_btn)

        lay.addStretch()

        # Seed the swatch with the initial color
        self._swatch.set_color(current_hex)
        return tab

    def _make_slider(self, lo: int, hi: int, val: int):
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(val)
        sl.setMinimumWidth(160)
        lbl = QLabel(str(val))
        return sl, lbl

    # ── Tab 2: From owned paints ──────────────────────────────────────────────

    def _build_paint_tab(self, current_hex: str) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        search_row = QHBoxLayout(); search_row.setSpacing(8)
        search_lbl = QLabel("Search:")
        search_lbl.setFixedWidth(52)
        search_row.addWidget(search_lbl)
        self._paint_search = QLineEdit()
        self._paint_search.setPlaceholderText("Filter by name or brand…")
        self._paint_search.textChanged.connect(self._filter_paints)
        search_row.addWidget(self._paint_search)
        lay.addLayout(search_row)

        self._paint_list = QListWidget()
        self._paint_list.setAlternatingRowColors(True)
        self._paint_list.setSpacing(1)
        self._paint_list.itemClicked.connect(self._on_paint_clicked)
        lay.addWidget(self._paint_list, stretch=1)

        # Selected paint preview row — QPainter chip (no background bleed)
        sel_frame = QFrame()
        sel_frame.setObjectName("pickerSection")
        sel_lay = QHBoxLayout(sel_frame)
        sel_lay.setContentsMargins(10, 8, 10, 8)
        sel_lay.setSpacing(10)
        sel_lay.addWidget(QLabel("Selected:"))
        self._paint_chip = _PaintChip(current_hex)
        sel_lay.addWidget(self._paint_chip)
        self._paint_hex_lbl = QLabel(current_hex.upper())
        self._paint_hex_lbl.setStyleSheet("font-weight: 600;")
        sel_lay.addWidget(self._paint_hex_lbl)
        sel_lay.addStretch()
        lay.addWidget(sel_frame)

        return tab

    # ── Slots — HSL tab ───────────────────────────────────────────────────────

    def _on_slider_changed(self):
        if self._guard:
            return
        h = self._sl_h.value()
        s = self._sl_s.value()
        l = self._sl_l.value()
        self._lbl_h.setText(str(h))
        self._lbl_s.setText(str(s))
        self._lbl_l.setText(str(l))
        new_hex = hsl_to_hex(float(h), float(s), float(l))
        self._selected_hex = new_hex
        self._swatch.set_color(new_hex)          # painter-based, no palette write
        self._guard = True
        self._hex_edit.setText(new_hex.upper())
        self._guard = False

    def _on_hex_committed(self):
        if self._guard:
            return
        raw = self._hex_edit.text().strip()
        if not raw.startswith("#"):
            raw = "#" + raw
        raw = raw.lower()
        if len(raw) == 7:
            try:
                int(raw[1:], 16)
                self._apply_hex(raw)
                return
            except ValueError:
                pass
        # Invalid — restore last good value
        self._hex_edit.setText(self._selected_hex.upper())

    def _apply_hex(self, hex_str: str):
        """Apply a validated hex string to all controls."""
        self._selected_hex = hex_str
        h, s, l = hex_to_hsl(hex_str)
        self._guard = True
        self._sl_h.setValue(int(round(h)))
        self._sl_s.setValue(int(round(s)))
        self._sl_l.setValue(int(round(l)))
        self._lbl_h.setText(str(int(round(h))))
        self._lbl_s.setText(str(int(round(s))))
        self._lbl_l.setText(str(int(round(l))))
        self._hex_edit.setText(hex_str.upper())
        self._guard = False
        self._swatch.set_color(hex_str)          # painter-based, no palette write

    def _open_color_wheel(self):
        """
        Call QColorDialog.getColor() with NO parent (None).

        Passing 'self' as parent causes Qt to create a parent-child palette
        link between the color dialog and this window, which lets the selected
        color bleed into our background.  None severs that link completely —
        the color wheel appears as a fully independent top-level window, and
        only the returned QColor value crosses back to us.
        """
        initial = QColor(self._selected_hex)
        chosen = QColorDialog.getColor(
            initial,
            None,                              # ← no parent → no palette link
            "Choose Color",
            QColorDialog.DontUseNativeDialog,
        )
        if chosen.isValid():
            self._apply_hex(chosen.name().lower())

    # ── Slots — Paint tab ─────────────────────────────────────────────────────

    def _load_paints(self):
        paint_svc = self._context.services.try_get("paint_service")
        if not paint_svc:
            self._paint_list.addItem("⚠  Paint Tracker not loaded")
            return
        try:
            self._all_paints = paint_svc.get_all_paints()
        except Exception as e:
            log.error(f"[CHROMA] Paint load: {e}")
        self._populate_paint_list(self._all_paints)

    def _populate_paint_list(self, paints: list):
        self._paint_list.clear()
        for p in paints:
            color = getattr(p, "color", None)
            if not color or not color.startswith("#"):
                continue
            label = f"  {p.name}  —  {p.brand}"
            pt = getattr(p, "paint_type", "")
            if pt:
                label += f"  [{pt}]"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, color)
            qc = QColor(color)
            bright = (qc.red() * 299 + qc.green() * 587 + qc.blue() * 114) / 1000
            item.setBackground(qc)
            item.setForeground(QColor("#000" if bright > 128 else "#fff"))
            self._paint_list.addItem(item)

    def _filter_paints(self, text: str):
        needle = text.strip().lower()
        self._populate_paint_list([
            p for p in self._all_paints
            if not needle
            or needle in p.name.lower()
            or needle in p.brand.lower()
        ])

    def _on_paint_clicked(self, item: QListWidgetItem):
        color = item.data(Qt.UserRole)
        if not color:
            return
        self._selected_hex = color
        self._paint_chip.set_color(color)        # painter-based, no palette write
        self._paint_hex_lbl.setText(color.upper())
        # Sync the HSL tab so it's consistent if the user switches tabs
        self._apply_hex(color)

    # ── Result ────────────────────────────────────────────────────────────────

    @property
    def selected_hex(self) -> str:
        return self._selected_hex


# ── Card palette extractor ────────────────────────────────────────────────────

def _rgba(hex_str: str, alpha: float) -> str:
    """Convert #rrggbb + alpha [0-1] to CSS rgba() string."""
    qc = QColor(hex_str)
    return f"rgba({qc.red()},{qc.green()},{qc.blue()},{alpha:.2f})"


def _card_colors(swatches: list[str], primary_hex: str) -> dict:
    """
    Derive card-safe accent colors from a scheme palette.

    Design rules:
      · card backgrounds are ALWAYS very dark (lightness ≤ 22 %) regardless of input
      · accent bar uses the primary hue at medium brightness — never oversaturated
      · badge bg/fg pair always has ≥ 35 % lightness gap for readability
      · completion colour uses the palette's highlight/glow rather than hardcoded values
    """
    safe = list(swatches) + [primary_hex] * 9   # ensure at least 9 entries
    pri  = safe[0]   # primary
    glow = safe[5]   # glow / energy
    hi   = safe[7]   # highlight / light end

    h, s, l = hex_to_hsl(pri)

    # ── Card backgrounds (always dark, just hue-tinted) ─────────────────────
    bg_l      = max(min(l * 0.12 + 8,  18), 9)
    bg_hov_l  = max(min(l * 0.15 + 9,  21), 11)
    bg_sel_l  = max(min(l * 0.18 + 10, 24), 13)
    bg_s      = max(s * 0.20, 5)
    card_bg      = hsl_to_hex(h, bg_s, bg_l)
    card_bg_hov  = hsl_to_hex(h, bg_s, bg_hov_l)
    card_bg_sel  = hsl_to_hex(h, bg_s, bg_sel_l)

    # ── Accent bar (left stripe) ─────────────────────────────────────────────
    accent = hsl_to_hex(h, min(s * 0.85, 75), max(min(l * 0.65 + 14, 54), 30))

    # ── Border ──────────────────────────────────────────────────────────────
    border = hsl_to_hex(h, min(s * 0.45, 40), min(l * 0.40 + 10, 34))

    # ── Style badge — themed to primary hue, readable ────────────────────────
    badge_bg = hsl_to_hex(h, max(s * 0.40, 15), max(l * 0.22 + 11, 14))
    badge_fg = hsl_to_hex(h, min(s * 0.65, 62), min(l * 0.55 + 32, 70))

    # ── Completion colour ────────────────────────────────────────────────────
    # Use the palette's highlight if it's meaningfully different from primary
    hi_h, hi_s, hi_l = hex_to_hsl(hi)
    done_color = hi if hi_l > 52 else hsl_to_hex(h, min(s * 0.55, 55), 70)
    gl_h, gl_s, gl_l = hex_to_hsl(glow)
    part_color = glow if gl_l > 38 else hsl_to_hex(h, min(s * 0.70, 65), 55)

    return {
        "primary":     pri,
        "card_bg":     card_bg,
        "card_bg_hov": card_bg_hov,
        "card_bg_sel": card_bg_sel,
        "accent":      accent,
        "border":      border,
        "badge_bg":    badge_bg,
        "badge_fg":    badge_fg,
        "done_color":  done_color,
        "part_color":  part_color,
    }


def _card_qss(c: dict, state: str) -> str:
    """Build the QFrame stylesheet for a card given its current interaction state."""
    if state == "selected":
        bg, b_alpha, a_alpha, bw = c["card_bg_sel"], 0.65, 1.00, "1.5px"
    elif state == "hover":
        bg, b_alpha, a_alpha, bw = c["card_bg_hov"], 0.42, 0.82, "1px"
    else:
        bg, b_alpha, a_alpha, bw = c["card_bg"],     0.22, 0.55, "1px"

    return (
        f"QFrame#schemePreviewCard {{"
        f" background: {bg};"
        f" border: {bw} solid {_rgba(c['border'], b_alpha)};"
        f" border-left: 3px solid {_rgba(c['accent'], a_alpha)};"
        f" border-radius: 6px;"
        f"}}"
    )


# ── Palette banner strip (QPainter — no QSS backgrounds) ──────────────────────

class _PaletteBannerStrip(QWidget):
    """
    Seamless multi-colour strip rendered with QPainter.
    Never uses setStyleSheet(background:…) so it is completely cascade-safe.
    """

    def __init__(self, swatches: list[str], height: int = 22, parent=None):
        super().__init__(parent)
        self._swatches = [s for s in swatches if s] or ["#3a3a3a"]
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def paintEvent(self, _event):
        p = QPainter(self)
        n   = len(self._swatches)
        w   = self.width()
        h   = self.height()
        seg = w / n
        for i, hex_c in enumerate(self._swatches):
            x  = int(i * seg)
            x2 = int((i + 1) * seg) if i < n - 1 else w
            p.fillRect(x, 0, x2 - x, h, QColor(hex_c))
        p.end()


# ── Scheme Preview Card ───────────────────────────────────────────────────────

class SchemePreviewCard(QFrame):
    """
    Premium palette preview card.

    Visual design:
      • 22 px colour strip across the top — all 9 palette colours
      • 3 px left accent bar in the primary hue
      • Card background: barely-visible primary-hued dark tint
      • Border: primary hue, opacity driven by interaction state
      • Style badge: colour-derived from the primary hue (not hardcoded blue)
      • Personality badge: retains its own meta colours
      • Completion indicator: uses the palette's highlight / glow colour
    """

    clicked = Signal(int)

    def __init__(self, scheme: dict, swatches: list[str],
                 project_name: str = "", parent=None):
        super().__init__(parent)
        self._scheme_id = scheme["id"]
        self._selected  = False
        self._c         = _card_colors(swatches, scheme.get("primary_hex", "#888888"))
        self._swatches  = swatches

        self.setObjectName("schemePreviewCard")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.installEventFilter(self)
        self._build(scheme, swatches, project_name)
        self._refresh_style("normal")

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self, s: dict, swatches: list[str], project_name: str):
        c   = self._c
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Palette strip ─────────────────────────────────────────────────────
        banner = _PaletteBannerStrip(swatches, height=22)
        root.addWidget(banner)

        # ── Text content ──────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(12, 8, 10, 9)
        body_lay.setSpacing(4)

        # Name row: accent dot + bold name
        name_row = QHBoxLayout(); name_row.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            f"background:{c['primary']}; border-radius:5px;"
            f" border:1px solid rgba(255,255,255,0.25);"
        )
        name_row.addWidget(dot)
        name_lbl = QLabel(s["name"])
        name_lbl.setStyleSheet(
            "font-size:12px; font-weight:700; color:#e8e8e8; background:transparent;"
        )
        name_lbl.setWordWrap(True)
        name_row.addWidget(name_lbl, stretch=1)
        body_lay.addLayout(name_row)

        # Badge row: style (palette-tinted) + personality (own meta)
        badge_row = QHBoxLayout(); badge_row.setSpacing(5)
        badge_row.addWidget(_badge(s["style"], c["badge_bg"], c["badge_fg"]))
        pers = s.get("personality", "")
        if pers and pers in _PERSONALITY_META:
            pbg, pfg, picon = _PERSONALITY_META[pers]
            badge_row.addWidget(_badge(f"{picon} {pers}", pbg, pfg))
        badge_row.addStretch()
        body_lay.addLayout(badge_row)

        # Meta rows
        meta: list[tuple[str, str, str]] = []   # (icon, text, color)
        gs  = s.get("game_system", "").strip()
        if gs:           meta.append(("🎮", gs,           "#888888"))
        fac = s.get("faction", "").strip()
        if fac:          meta.append(("⚔", fac,           "#888888"))
        if project_name: meta.append(("📁", project_name, "#888888"))

        owned = s.get("owned_count", 0)
        total = s.get("total_roles", len(ROLES))
        if total > 0:
            all_done = owned == total
            meta.append((
                "✓" if all_done else "◑",
                f"{owned}/{total} roles covered",
                c["done_color"] if all_done else c["part_color"],
            ))

        if meta:
            sep = QFrame(); sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("color: rgba(255,255,255,0.07); background:transparent;")
            body_lay.addWidget(sep)

        for icon, text, color in meta:
            row = QHBoxLayout(); row.setSpacing(5)
            il = QLabel(icon); il.setFixedWidth(16)
            il.setStyleSheet(f"font-size:10px; background:transparent; color:{color};")
            tl = QLabel(text)
            tl.setStyleSheet(f"font-size:10px; color:{color}; background:transparent;")
            tl.setWordWrap(True)
            row.addWidget(il); row.addWidget(tl, stretch=1)
            body_lay.addLayout(row)

        root.addWidget(body)

    # ── State management ──────────────────────────────────────────────────────

    def _refresh_style(self, state: str):
        self.setStyleSheet(_card_qss(self._c, state))

    def set_selected(self, selected: bool):
        self._selected = selected
        self._refresh_style("selected" if selected else "normal")

    def scheme_id(self) -> int:
        return self._scheme_id

    # ── Events ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._scheme_id)
        super().mousePressEvent(event)

    def eventFilter(self, watched, event):
        if watched is self and not self._selected:
            if event.type() == QEvent.Enter:
                self._refresh_style("hover")
            elif event.type() == QEvent.Leave:
                self._refresh_style("normal")
        return super().eventFilter(watched, event)


# ── Scheme card list ──────────────────────────────────────────────────────────

class _SchemeCardList(QScrollArea):
    selection_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._container = QWidget()
        self._lay = QVBoxLayout(self._container)
        self._lay.setContentsMargins(0, 4, 0, 8)
        self._lay.setSpacing(6)
        self._lay.addStretch()
        self.setWidget(self._container)
        self._cards: list[SchemePreviewCard] = []
        self._selected_id: int | None = None

    def populate(self, schemes: list[dict], swatches_map: dict[int, list[str]],
                 project_lookup: dict[int, str] | None = None):
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        for s in schemes:
            proj = (project_lookup or {}).get(s.get("linked_project_id"), "")
            swatches = swatches_map.get(s["id"], [s["primary_hex"]])
            card = SchemePreviewCard(s, swatches, proj)
            card.clicked.connect(self._on_card_clicked)
            self._lay.insertWidget(self._lay.count() - 1, card)
            self._cards.append(card)

        if self._selected_id is not None:
            if self._selected_id not in {c.scheme_id() for c in self._cards}:
                self._selected_id = None
        self._apply_selection()

    def select(self, scheme_id: int):
        self._selected_id = scheme_id
        self._apply_selection()

    def get_selected_id(self) -> int | None:
        return self._selected_id

    def count(self) -> int:
        return len(self._cards)

    def _on_card_clicked(self, scheme_id: int):
        if self._selected_id == scheme_id:
            return
        self._selected_id = scheme_id
        self._apply_selection()
        self.selection_changed.emit(scheme_id)

    def _apply_selection(self):
        for card in self._cards:
            card.set_selected(card.scheme_id() == self._selected_id)


# ── Chroma scheme DB helper ───────────────────────────────────────────────────

class _ChromaRepo:
    _CREATE_SQL = """
        CREATE TABLE IF NOT EXISTS chroma_schemes (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT    NOT NULL DEFAULT 'Untitled',
            primary_hex       TEXT    NOT NULL DEFAULT '#888888',
            style             TEXT    NOT NULL DEFAULT 'Complementary',
            personality       TEXT    NOT NULL DEFAULT '',
            notes             TEXT    NOT NULL DEFAULT '',
            game_system       TEXT    NOT NULL DEFAULT '',
            faction           TEXT    NOT NULL DEFAULT '',
            linked_project_id INTEGER,
            owned_count       INTEGER NOT NULL DEFAULT 0,
            total_roles       INTEGER NOT NULL DEFAULT 9,
            role_overrides    TEXT    NOT NULL DEFAULT '{}',
            palette_json      TEXT    NOT NULL DEFAULT '[]',
            created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """
    _MIGRATIONS = [
        ("personality",       "TEXT    NOT NULL DEFAULT ''"),
        ("game_system",       "TEXT    NOT NULL DEFAULT ''"),
        ("faction",           "TEXT    NOT NULL DEFAULT ''"),
        ("linked_project_id", "INTEGER"),
        ("owned_count",       "INTEGER NOT NULL DEFAULT 0"),
        ("total_roles",       "INTEGER NOT NULL DEFAULT 9"),
        ("role_overrides",    "TEXT    NOT NULL DEFAULT '{}'"),
        ("palette_json",      "TEXT    NOT NULL DEFAULT '[]'"),
    ]

    def __init__(self, db):
        self._db = db
        self._ensure_tables()

    def _ensure_tables(self):
        self._db.execute(self._CREATE_SQL)
        for col, defn in self._MIGRATIONS:
            try:
                self._db.execute(f"ALTER TABLE chroma_schemes ADD COLUMN {col} {defn}")
            except Exception:
                pass

    def get_all(self) -> list[dict]:
        rows = self._db.query(
            "SELECT id, name, primary_hex, style, personality, notes, "
            "game_system, faction, linked_project_id, owned_count, total_roles, "
            "role_overrides, palette_json, created_at "
            "FROM chroma_schemes ORDER BY id DESC"
        )
        return [dict(r) for r in rows]

    def get(self, scheme_id: int) -> Optional[dict]:
        rows = self._db.query(
            "SELECT id, name, primary_hex, style, personality, notes, "
            "game_system, faction, linked_project_id, owned_count, total_roles, "
            "role_overrides, palette_json, created_at "
            "FROM chroma_schemes WHERE id=?", (scheme_id,)
        )
        return dict(rows[0]) if rows else None

    def add(self, name: str, primary_hex: str, style: str,
            personality: str = "", notes: str = "",
            game_system: str = "", faction: str = "",
            linked_project_id: int | None = None,
            owned_count: int = 0, total_roles: int = 9,
            role_overrides: dict | None = None,
            palette_json: list | None = None) -> dict:
        cur = self._db.execute(
            "INSERT INTO chroma_schemes "
            "(name, primary_hex, style, personality, notes, "
            " game_system, faction, linked_project_id, owned_count, total_roles, "
            " role_overrides, palette_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, primary_hex, style, personality, notes,
             game_system, faction, linked_project_id, owned_count, total_roles,
             json.dumps(role_overrides or {}),
             json.dumps(palette_json or [])),
        )
        return self.get(cur.lastrowid)

    def update(self, scheme_id: int, **kwargs) -> Optional[dict]:
        allowed = {
            "name", "primary_hex", "style", "personality", "notes",
            "game_system", "faction", "linked_project_id",
            "owned_count", "total_roles", "role_overrides", "palette_json",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return self.get(scheme_id)
        # Serialize JSON fields if passed as Python objects
        if "role_overrides" in fields and isinstance(fields["role_overrides"], dict):
            fields["role_overrides"] = json.dumps(fields["role_overrides"])
        if "palette_json" in fields and isinstance(fields["palette_json"], list):
            fields["palette_json"] = json.dumps(fields["palette_json"])
        cols = ", ".join(f"{k}=?" for k in fields)
        self._db.execute(
            f"UPDATE chroma_schemes SET {cols} WHERE id=?",
            list(fields.values()) + [scheme_id]
        )
        return self.get(scheme_id)

    def delete(self, scheme_id: int):
        self._db.execute("DELETE FROM chroma_schemes WHERE id=?", (scheme_id,))


# ── Save / Edit dialog ────────────────────────────────────────────────────────

class _SaveDialog(QDialog):
    def __init__(self, parent, primary_hex: str, style: str, existing: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Update Scheme" if existing else "Save Chroma Scheme")
        self.setMinimumWidth(400)
        self.setModal(True)
        self._build(primary_hex, style, existing or {})

    def _build(self, primary_hex: str, style: str, ex: dict):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 18, 20, 18)

        lay.addWidget(_field_lbl("Scheme Name"))
        self.name_input = QLineEdit(ex.get("name", f"Scheme — {style}"))
        lay.addWidget(self.name_input)

        lay.addWidget(_field_lbl("Personality  (sets the emotional tone)"))
        self.pers_combo = QComboBox()
        for p in PERSONALITIES:
            if p == "":
                self.pers_combo.addItem("— None —", "")
            else:
                bg, fg, icon = _PERSONALITY_META[p]
                self.pers_combo.addItem(f"{icon}  {p}", p)
        cur_p = ex.get("personality", "")
        idx = next((i for i in range(self.pers_combo.count())
                    if self.pers_combo.itemData(i) == cur_p), 0)
        self.pers_combo.setCurrentIndex(idx)
        lay.addWidget(self.pers_combo)

        row = QHBoxLayout(); row.setSpacing(10)
        gs_col = QVBoxLayout(); gs_col.setSpacing(4)
        gs_col.addWidget(_field_lbl("Game System"))
        self.gs_input = QLineEdit(ex.get("game_system", ""))
        self.gs_input.setPlaceholderText("e.g. Warhammer 40,000")
        gs_col.addWidget(self.gs_input)
        row.addLayout(gs_col, stretch=1)

        fac_col = QVBoxLayout(); fac_col.setSpacing(4)
        fac_col.addWidget(_field_lbl("Faction / Army"))
        self.fac_input = QLineEdit(ex.get("faction", ""))
        self.fac_input.setPlaceholderText("e.g. Dark Angels")
        fac_col.addWidget(self.fac_input)
        row.addLayout(fac_col, stretch=1)
        lay.addLayout(row)

        lay.addWidget(_field_lbl("Notes  (optional)"))
        self.notes_input = QLineEdit(ex.get("notes", ""))
        self.notes_input.setPlaceholderText("Any extra context…")
        lay.addWidget(self.notes_input)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_values(self) -> dict:
        return {
            "name":        self.name_input.text().strip() or "Untitled",
            "personality": self.pers_combo.currentData() or "",
            "game_system": self.gs_input.text().strip(),
            "faction":     self.fac_input.text().strip(),
            "notes":       self.notes_input.text().strip(),
        }


# ── Role Card ─────────────────────────────────────────────────────────────────

class RoleCard(QFrame):
    """
    Displays one palette role.  Clicking the target swatch opens the override
    picker — emits override_requested(role, current_target_hex).
    """
    override_requested = Signal(str, str)   # role, current_hex

    def __init__(self, rec: RoleRecommendation, parent=None):
        super().__init__(parent)
        self.setObjectName("roleCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(190)
        self.setMaximumWidth(270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._role = rec.role
        self._build(rec)

    @staticmethod
    def _dist_color(d: float) -> str:
        if d < 0.10: return "#3dba6e"
        if d < 0.20: return "#f5a623"
        if d < 0.30: return "#e07c35"
        return "#e05555"

    def _build(self, rec: RoleRecommendation):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 9, 9, 9)
        lay.setSpacing(5)

        # ── Header: icon + label + clickable target swatch ────────────────────
        row1 = QHBoxLayout(); row1.setSpacing(6)
        icon_lbl = QLabel(rec.icon)
        icon_lbl.setStyleSheet("font-size:15px; background:transparent;")
        icon_lbl.setFixedWidth(20)
        row1.addWidget(icon_lbl)
        lbl = QLabel(rec.label)
        lbl.setStyleSheet("font-size:11px; font-weight:700; color:#c0c0c0; background:transparent;")
        row1.addWidget(lbl, stretch=1)

        # Clickable swatch — opens override picker
        target_sw = _swatch(rec.target_hex, size=24, border_radius=4)
        target_sw.setToolTip(f"Target: {rec.target_hex}\nClick to override")
        target_sw.setCursor(QCursor(Qt.PointingHandCursor))
        target_sw.mousePressEvent = lambda _e, r=rec.role, h=rec.target_hex: \
            self.override_requested.emit(r, h)
        row1.addWidget(target_sw)

        # "✏" hint label beside swatch
        edit_hint = QLabel("✏")
        edit_hint.setStyleSheet("font-size:9px; color:#505050; background:transparent;")
        edit_hint.setToolTip("Click swatch to override color")
        row1.addWidget(edit_hint)
        lay.addLayout(row1)

        lay.addWidget(_hline())

        # ── Best match ────────────────────────────────────────────────────────
        if rec.best_match:
            pm = rec.best_match
            mr = QHBoxLayout(); mr.setSpacing(6)
            mr.addWidget(_swatch(pm.color_hex, size=20))
            nc = QVBoxLayout(); nc.setSpacing(1)
            n = QLabel(pm.paint_name)
            n.setStyleSheet("font-size:11px; font-weight:600; background:transparent;")
            n.setWordWrap(True)
            b = QLabel(pm.brand)
            b.setStyleSheet("font-size:10px; color:#888; background:transparent;")
            nc.addWidget(n); nc.addWidget(b)
            mr.addLayout(nc, stretch=1)
            qc = self._dist_color(pm.distance)
            mr.addWidget(_badge(f"✓ {int((1-pm.distance)*100)}%", qc))
            lay.addLayout(mr)
            if pm.is_low:
                lr = QHBoxLayout()
                lr.addWidget(_badge("⚠ Low Stock", "#c47a15", "#fff8e0"))
                lr.addStretch()
                lay.addLayout(lr)
        else:
            mr = QHBoxLayout()
            mr.addWidget(_badge("✕  No Match", "#5a2020"))
            mr.addStretch()
            lay.addLayout(mr)
            h = QLabel("Add a paint close to this color.")
            h.setStyleSheet("font-size:10px; color:#666; background:transparent;")
            h.setWordWrap(True)
            lay.addWidget(h)

        # ── Alternatives ──────────────────────────────────────────────────────
        if rec.alternatives:
            al = QLabel("Alternatives:")
            al.setStyleSheet("font-size:10px; color:#888; background:transparent; margin-top:1px;")
            lay.addWidget(al)
            for alt in rec.alternatives[:3]:
                ar = QHBoxLayout(); ar.setSpacing(5)
                ar.addWidget(_swatch(alt.color_hex, size=13))
                an = QLabel(f"{alt.paint_name}  ·  {alt.brand}")
                an.setStyleSheet("font-size:10px; color:#999; background:transparent;")
                an.setWordWrap(True)
                ar.addWidget(an, stretch=1)
                qc = self._dist_color(alt.distance)
                pl = QLabel(f"{int((1-alt.distance)*100)}%")
                pl.setStyleSheet(f"font-size:10px; color:{qc}; background:transparent;")
                ar.addWidget(pl)
                lay.addLayout(ar)


# ── Missing paints banner ─────────────────────────────────────────────────────

class _MissingBanner(QFrame):
    def __init__(self, missing: list[RoleRecommendation], parent=None):
        super().__init__(parent)
        self.setObjectName("missingBanner")
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)
        if not missing:
            r = QHBoxLayout()
            r.addWidget(_badge("✓  All roles covered by your collection!", "#1a5a2a", "#a0f0b0"))
            r.addStretch()
            lay.addLayout(r)
            return
        r = QHBoxLayout(); r.setSpacing(8)
        r.addWidget(QLabel(f"⚠  {len(missing)} role{'s' if len(missing)>1 else ''} need paint:"))
        for rec in missing:
            sw = _swatch(rec.target_hex, size=16)
            sw.setToolTip(f"{rec.label}: {rec.target_hex}")
            r.addWidget(sw)
            lbl = QLabel(rec.label)
            lbl.setStyleSheet("font-size:10px; color:#aaa; background:transparent;")
            r.addWidget(lbl)
        r.addStretch()
        lay.addLayout(r)


# ── Results pane ──────────────────────────────────────────────────────────────

class _ResultsPane(QWidget):
    override_requested = Signal(str, str)   # role, current_hex

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._context = context
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self._scroll, stretch=1)

        self._host = QWidget()
        self._host_lay = QVBoxLayout(self._host)
        self._host_lay.setContentsMargins(12, 12, 12, 12)
        self._host_lay.setSpacing(10)

        self._placeholder = QLabel(
            "Pick a primary color and click  ⚡ Generate  to build your palette."
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            "font-size:13px; color:#505050; padding:60px 40px; background:transparent;"
        )
        self._host_lay.addWidget(self._placeholder)

        self._grid_container = QWidget()
        self._grid_container.setVisible(False)
        self._grid_lay = QGridLayout(self._grid_container)
        self._grid_lay.setSpacing(8)
        self._host_lay.addWidget(self._grid_container)

        self._banner_container = QWidget()
        self._banner_container.setVisible(False)
        self._banner_lay = QVBoxLayout(self._banner_container)
        self._banner_lay.setContentsMargins(0, 0, 0, 0)
        self._host_lay.addWidget(self._banner_container)

        # Stretch at the END so cards sit flush at the top
        self._host_lay.addStretch()

        self._scroll.setWidget(self._host)

    def load_result(self, result: ChromaResult):
        while self._grid_lay.count():
            item = self._grid_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        while self._banner_lay.count():
            item = self._banner_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        self._placeholder.setVisible(False)
        self._grid_container.setVisible(True)
        self._banner_container.setVisible(True)

        COLS = 3
        for idx, role in enumerate(ROLES):
            rec = result.recommendations.get(role)
            if rec is None: continue
            card = RoleCard(rec)
            card.override_requested.connect(self.override_requested)
            row_, col_ = divmod(idx, COLS)
            self._grid_lay.addWidget(card, row_, col_)

        self._banner_lay.addWidget(_MissingBanner(result.missing_roles))

    def show_placeholder(self):
        self._placeholder.setVisible(True)
        self._grid_container.setVisible(False)
        self._banner_container.setVisible(False)


# ── Color picker button ───────────────────────────────────────────────────────

class _ColorPickerBtn(QPushButton):
    """Shows current hex as background; opens the two-tab picker on click."""

    def __init__(self, initial_hex: str = "#8b0000", context=None, parent=None):
        super().__init__(parent)
        self._hex = initial_hex
        self._context = context
        self.setFixedSize(80, 34)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._open_dialog)
        self._refresh()

    def _refresh(self):
        c = self._hex
        bright = QColor(c).lightness()
        fg = "#000000" if bright > 128 else "#ffffff"
        self.setText(c.upper())
        self.setStyleSheet(
            f"background:{c}; color:{fg}; border:1px solid rgba(255,255,255,0.18);"
            f" border-radius:4px; font-size:10px; font-weight:700; padding:0;"
        )

    def _open_dialog(self):
        # Use self.window() — the top-level app window — as parent instead of
        # self (the button).  The button has setStyleSheet("background:#RRGGBB")
        # which Qt cascades into any child window created with parent=self.
        # self.window() has no such inline stylesheet, so the cascade is clean.
        top = self.window()
        if self._context:
            dlg = _PrimaryPickerDialog(self._hex, self._context, top)
            if dlg.exec() == QDialog.Accepted:
                self._hex = dlg.selected_hex
                self._refresh()
        else:
            # Fallback: Qt's own color dialog — also parentless to avoid bleed
            color = QColorDialog.getColor(
                QColor(self._hex), None, "Pick Primary Colour",
                QColorDialog.DontUseNativeDialog,
            )
            if color.isValid():
                self._hex = color.name().lower()
                self._refresh()

    def get_hex(self) -> str:
        return self._hex

    def set_hex(self, hex_str: str):
        self._hex = hex_str
        self._refresh()


# ── Project picker dialog ─────────────────────────────────────────────────────

class _ProjectPickerDialog(QDialog):
    def __init__(self, projects: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link Palette to Project")
        self.setMinimumWidth(360)
        self.setModal(True)
        self.selected_id: int | None = None
        lay = QVBoxLayout(self)
        lay.setSpacing(8); lay.setContentsMargins(16, 14, 16, 14)
        lay.addWidget(QLabel("Choose a project to link this palette to:"))
        self._list = QListWidget()
        self._list.setMinimumHeight(180)
        self._list.setAlternatingRowColors(True)
        for p in projects:
            item = QListWidgetItem(p.name)
            item.setData(Qt.UserRole, p.id)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)
        lay.addWidget(self._list)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_accept(self):
        item = self._list.currentItem()
        if item: self.selected_id = item.data(Qt.UserRole)
        self.accept()


# ── Main Chroma Codex Widget ──────────────────────────────────────────────────

class ChromaCodexWidget(QWidget):

    def __init__(self, context):
        super().__init__()
        self.context = context
        self._repo: Optional[_ChromaRepo] = None
        self._current_result: Optional[ChromaResult] = None
        self._current_scheme_id: Optional[int] = None
        self._role_overrides: dict[str, str] = {}   # role → hex override
        self._project_lookup: dict[int, str] = {}
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status)
        self._init_repo()
        self._build_ui()
        QTimer.singleShot(0, self._initial_load)

    def _init_repo(self):
        db = self.context.services.try_get("db")
        if db:
            try:
                self._repo = _ChromaRepo(db)
            except Exception as e:
                log.error(f"[CHROMA UI] Repo init failed: {e}")

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top_bar())
        root.addWidget(_hline())
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left_pane())
        splitter.addWidget(self._build_right_pane())
        splitter.setSizes([280, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

    # ── Top bar ───────────────────────────────────────────────────────────────

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("chromaTopBar")
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(10)

        title = QLabel("🎨  Chroma Codex")
        title.setObjectName("pageTitle")
        title.setStyleSheet("font-size:16px; font-weight:700; background:transparent;")
        lay.addWidget(title)

        def _vsep():
            s = QFrame(); s.setFrameShape(QFrame.VLine)
            s.setObjectName("vSep"); s.setFixedWidth(1)
            return s

        lay.addWidget(_vsep())

        lay.addWidget(QLabel("Primary:"))
        # Pass context so the picker can offer "from owned paint"
        self._color_btn = _ColorPickerBtn("#8b1a1a", context=self.context)
        lay.addWidget(self._color_btn)

        self._hex_input = QLineEdit("#8b1a1a")
        self._hex_input.setFixedWidth(90)   # wide enough for #rrggbb without clipping
        self._hex_input.setPlaceholderText("#rrggbb")
        self._hex_input.setMaxLength(7)
        self._hex_input.editingFinished.connect(self._on_hex_input_changed)
        lay.addWidget(self._hex_input)

        lay.addWidget(_vsep())

        lay.addWidget(QLabel("Style:"))
        self._style_combo = QComboBox()
        self._style_combo.setMinimumWidth(148)
        for s in SCHEME_STYLES:
            if s != "Custom Manual":
                self._style_combo.addItem(s, s)
        self._style_combo.setCurrentIndex(0)
        self._style_combo.currentIndexChanged.connect(self._on_style_changed)
        lay.addWidget(self._style_combo)

        lay.addWidget(_vsep())

        lay.addWidget(QLabel("Personality:"))
        self._pers_combo = QComboBox()
        self._pers_combo.setMinimumWidth(130)
        for p in PERSONALITIES:
            if p == "":
                self._pers_combo.addItem("— None —", "")
            else:
                _, _, icon = _PERSONALITY_META[p]
                self._pers_combo.addItem(f"{icon}  {p}", p)
        lay.addWidget(self._pers_combo)

        self._style_hint = QLabel("")
        self._style_hint.setStyleSheet(
            "font-size:10px; color:#606060; background:transparent; max-width:180px;")
        self._style_hint.setWordWrap(True)
        lay.addWidget(self._style_hint)
        self._update_style_hint()

        lay.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            "font-size:11px; font-weight:600; background:transparent;")
        lay.addWidget(self._status_lbl)

        self._gen_btn = QPushButton("⚡  Generate")
        self._gen_btn.setProperty("class", "primary")
        self._gen_btn.setFixedHeight(34)
        self._gen_btn.setMinimumWidth(110)
        self._gen_btn.clicked.connect(self._on_generate)
        lay.addWidget(self._gen_btn)

        self._save_btn = QPushButton("💾  Save")
        self._save_btn.setFixedHeight(34)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        lay.addWidget(self._save_btn)

        self._link_btn = QPushButton("🔗  Link to Project")
        self._link_btn.setFixedHeight(34)
        self._link_btn.setEnabled(False)
        self._link_btn.clicked.connect(self._on_link_to_project)
        lay.addWidget(self._link_btn)

        return bar

    # ── Left pane ─────────────────────────────────────────────────────────────

    def _build_left_pane(self) -> QWidget:
        pane = QWidget()
        pane.setMinimumWidth(240)
        pane.setMaximumWidth(340)
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(12, 14, 8, 14)
        lay.setSpacing(8)

        hdr = QHBoxLayout(); hdr.setSpacing(8)
        hdr.addWidget(_section_title("Saved Schemes"))
        self._count_badge = QLabel("")
        self._count_badge.setStyleSheet(
            "background:#1e3a5a; color:#7ab0e0; border-radius:8px;"
            " padding:1px 7px; font-size:10px; font-weight:700;")
        self._count_badge.setVisible(False)
        hdr.addWidget(self._count_badge)
        hdr.addStretch()
        lay.addLayout(hdr)

        self._saved_search = QLineEdit()
        self._saved_search.setPlaceholderText("Search saved schemes…")
        self._saved_search.textChanged.connect(self._filter_saved_list)
        lay.addWidget(self._saved_search)

        self._card_list = _SchemeCardList()
        self._card_list.selection_changed.connect(self._on_saved_selected)
        lay.addWidget(self._card_list, stretch=1)

        self._saved_empty_lbl = QLabel(
            "No saved schemes yet.\n\nGenerate a palette and\nclick  💾 Save  to begin.")
        self._saved_empty_lbl.setAlignment(Qt.AlignCenter)
        self._saved_empty_lbl.setStyleSheet(
            "color:#505050; font-size:11px; padding:24px 12px; background:transparent;")
        lay.addWidget(self._saved_empty_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self._del_saved_btn = QPushButton("Delete")
        self._del_saved_btn.setProperty("class", "danger")
        self._del_saved_btn.setFixedHeight(28)
        self._del_saved_btn.setEnabled(False)
        self._del_saved_btn.clicked.connect(self._on_delete_saved)
        btn_row.addStretch()
        btn_row.addWidget(self._del_saved_btn)
        lay.addLayout(btn_row)

        return pane

    # ── Right pane ────────────────────────────────────────────────────────────

    def _build_right_pane(self) -> QWidget:
        self._results_pane = _ResultsPane(self.context)
        self._results_pane.override_requested.connect(self._on_override_requested)
        return self._results_pane

    # ── Initial load ──────────────────────────────────────────────────────────

    def _initial_load(self):
        self._refresh_project_lookup()
        self._load_saved_list()

    def _refresh_project_lookup(self):
        svc = self.context.services.try_get("project_service")
        if not svc: return
        try:
            self._project_lookup = {p.id: p.name for p in svc.get_all_projects()}
        except Exception:
            pass

    # ── Saved list ────────────────────────────────────────────────────────────

    def _load_saved_list(self, restore_id: int | None = None):
        if not self._repo:
            self._card_list.setVisible(False)
            self._saved_empty_lbl.setVisible(True)
            self._count_badge.setVisible(False)
            return

        schemes = self._repo.get_all()
        needle = self._saved_search.text().strip().lower()
        if needle:
            schemes = [s for s in schemes if any(
                needle in s.get(k, "").lower()
                for k in ("name", "game_system", "faction", "personality")
            )]

        has = bool(schemes)
        self._card_list.setVisible(has)
        self._saved_empty_lbl.setVisible(not has)
        self._count_badge.setText(str(len(schemes))); self._count_badge.setVisible(has)

        # Build swatch colors for each card.
        # Priority: stored palette_json (actual paint/target colors captured at save time)
        #           → fallback to mathematical derivation (for old records without palette_json)
        swatches_map: dict[int, list[str]] = {}
        for s in schemes:
            stored: list[str] = []
            try:
                stored = json.loads(s.get("palette_json") or "[]")
            except Exception:
                pass
            if stored and all(c.startswith("#") for c in stored):
                swatches_map[s["id"]] = stored
            else:
                # Fallback for schemes saved before palette_json existed
                try:
                    overrides = json.loads(s.get("role_overrides") or "{}")
                except Exception:
                    overrides = {}
                swatches_map[s["id"]] = _derive_palette_swatches(
                    s["primary_hex"], s["style"], overrides=overrides
                )

        self._card_list.populate(schemes, swatches_map, self._project_lookup)

        target_id = restore_id or self._current_scheme_id
        if target_id:
            self._card_list.select(target_id)

        has_sel = self._card_list.get_selected_id() is not None
        self._del_saved_btn.setEnabled(has_sel and self._repo is not None)

    def _filter_saved_list(self, _=None):
        self._load_saved_list()

    def _on_saved_selected(self, scheme_id: int):
        if not self._repo: return
        data = self._repo.get(scheme_id)
        if not data: return

        self._del_saved_btn.setEnabled(True)
        self._current_scheme_id = scheme_id

        primary_hex = data.get("primary_hex", "#888888")
        style       = data.get("style", SCHEME_STYLES[0])
        personality = data.get("personality", "")

        # Restore stored overrides
        try:
            self._role_overrides = json.loads(data.get("role_overrides") or "{}")
        except Exception:
            self._role_overrides = {}

        self._color_btn.set_hex(primary_hex)
        self._hex_input.setText(primary_hex.upper())

        idx = self._style_combo.findData(style)
        if idx >= 0:
            self._style_combo.blockSignals(True)
            self._style_combo.setCurrentIndex(idx)
            self._style_combo.blockSignals(False)

        p_idx = next(
            (i for i in range(self._pers_combo.count())
             if self._pers_combo.itemData(i) == personality), 0
        )
        self._pers_combo.blockSignals(True)
        self._pers_combo.setCurrentIndex(p_idx)
        self._pers_combo.blockSignals(False)

        self._update_style_hint()
        self._run_generate(primary_hex, style)

    def _on_delete_saved(self):
        scheme_id = self._card_list.get_selected_id()
        if not scheme_id or not self._repo: return
        data = self._repo.get(scheme_id)
        name = data.get("name", "this scheme") if data else "this scheme"
        if QMessageBox.question(
            self, "Delete Saved Scheme",
            f"Delete '{name}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            self._repo.delete(scheme_id)
            if self._current_scheme_id == scheme_id:
                self._current_scheme_id = None
                self._role_overrides.clear()
                self._results_pane.show_placeholder()
                self._save_btn.setEnabled(False)
                self._link_btn.setEnabled(False)
            self._del_saved_btn.setEnabled(False)
            self._load_saved_list()
            self._show_status("Scheme deleted.", success=True)
        except Exception as e:
            self._show_status(f"Delete failed: {e}", success=False)

    # ── Generation ────────────────────────────────────────────────────────────

    def _on_hex_input_changed(self):
        txt = self._hex_input.text().strip()
        if not txt.startswith("#"): txt = "#" + txt
        if len(txt) == 7:
            self._color_btn.set_hex(txt.lower())

    def _on_style_changed(self, _=None):
        self._update_style_hint()

    def _update_style_hint(self):
        style = self._style_combo.currentData() or self._style_combo.currentText()
        self._style_hint.setText(STYLE_DESCRIPTIONS.get(style, ""))

    def _on_generate(self):
        # Fresh generate clears any manual overrides
        self._role_overrides.clear()
        primary_hex = self._color_btn.get_hex()
        style       = self._style_combo.currentData() or SCHEME_STYLES[0]
        self._hex_input.setText(primary_hex.upper())
        self._run_generate(primary_hex, style)

    def _run_generate(self, primary_hex: str, style: str):
        owned = self._get_owned_paints()
        try:
            result = chroma_engine.generate(primary_hex, style, owned)
        except Exception as e:
            self._show_status(f"Generation failed: {e}", success=False)
            return

        # Apply any stored/active overrides on top
        if self._role_overrides:
            result = _apply_overrides_to_result(result, self._role_overrides, owned)

        self._current_result = result
        self._results_pane.load_result(result)

        n_owned = result.owned_count
        total   = len(ROLES)
        missing = total - n_owned
        if missing == 0:
            self._show_status(f"✓ All {total} roles covered!", success=True)
        else:
            self._show_status(f"{n_owned}/{total} roles covered — {missing} need paint.", success=None)

        self._save_btn.setEnabled(self._repo is not None)
        self._link_btn.setEnabled(True)

    def _get_owned_paints(self) -> list:
        svc = self.context.services.try_get("paint_service")
        if svc is None: return []
        try: return svc.get_all_paints()
        except Exception: return []

    # ── Manual color override ─────────────────────────────────────────────────

    def _on_override_requested(self, role: str, current_hex: str):
        """User clicked a target swatch — let them pick a replacement color."""
        dlg = _PrimaryPickerDialog(current_hex, self.context, self)
        dlg.setWindowTitle(f"Override Color — {ROLE_META.get(role, ('', role))[1]}")
        if dlg.exec() != QDialog.Accepted:
            return
        new_hex = dlg.selected_hex
        if new_hex == current_hex:
            return
        self._role_overrides[role] = new_hex
        if self._current_result:
            primary_hex = self._current_result.primary_hex
            style       = self._current_result.style
            self._run_generate(primary_hex, style)

    # ── Palette color capture ─────────────────────────────────────────────────

    def _collect_palette_colors(self) -> list[str]:
        """
        Capture the real palette colors from the current result — all 9 roles in order.
        Uses the best-match paint color where owned, otherwise the mathematical target.
        This is what gets stored in palette_json and drives the card banner strip,
        so the preview card always looks exactly like the generated scheme.
        """
        if not self._current_result:
            return []
        colors = []
        for role in ROLES:
            rec = self._current_result.recommendations.get(role)
            if rec is None:
                colors.append("#3a3a3a")
            elif rec.best_match:
                colors.append(rec.best_match.color_hex)   # actual owned paint color
            else:
                colors.append(rec.target_hex)              # theoretical target
        return colors

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save(self):
        if not self._current_result or not self._repo: return
        primary_hex   = self._current_result.primary_hex
        style         = self._current_result.style
        owned         = self._current_result.owned_count
        total         = len(ROLES)
        personality   = self._pers_combo.currentData() or ""
        palette_colors = self._collect_palette_colors()

        if self._current_scheme_id:
            existing = self._repo.get(self._current_scheme_id)
            if existing:
                reply = QMessageBox.question(
                    self, "Update or Save New?",
                    f"Update '{existing['name']}' or save as a new scheme?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save,
                )
                if reply == QMessageBox.Cancel: return
                if reply == QMessageBox.Save:
                    dlg = _SaveDialog(self, primary_hex, style, existing)
                    if dlg.exec() != QDialog.Accepted: return
                    vals = dlg.get_values()
                    self._repo.update(
                        self._current_scheme_id,
                        primary_hex=primary_hex, style=style,
                        owned_count=owned, total_roles=total,
                        role_overrides=self._role_overrides,
                        palette_json=palette_colors,
                        **vals,
                    )
                    self._load_saved_list(self._current_scheme_id)
                    self._show_status(f"Updated '{vals['name']}'.", success=True)
                    return

        dlg = _SaveDialog(self, primary_hex, style,
                          existing={"personality": personality})
        if dlg.exec() != QDialog.Accepted: return
        vals = dlg.get_values()
        try:
            scheme = self._repo.add(
                primary_hex=primary_hex, style=style,
                owned_count=owned, total_roles=total,
                role_overrides=self._role_overrides,
                palette_json=palette_colors,
                **vals,
            )
            self._current_scheme_id = scheme["id"]
            self._refresh_project_lookup()
            self._load_saved_list(scheme["id"])
            self._show_status(f"Saved '{vals['name']}'.", success=True)
        except Exception as e:
            self._show_status(f"Save failed: {e}", success=False)

    # ── Link to project ───────────────────────────────────────────────────────

    def _on_link_to_project(self):
        if not self._current_result: return
        svc = self.context.services.try_get("project_service")
        if not svc:
            QMessageBox.warning(self, "No Projects",
                                "Project Tracker is not loaded.")
            return
        try: projects = svc.get_all_projects()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load projects: {e}"); return
        if not projects:
            self._show_status("No projects found — create one in Project Tracker first.", success=False)
            return

        dlg = _ProjectPickerDialog(projects, self)
        if dlg.exec() != QDialog.Accepted or dlg.selected_id is None: return
        project_id = dlg.selected_id

        paint_ids = [
            rec.best_match.paint_id
            for rec in self._current_result.recommendations.values()
            if rec.best_match
        ]
        linked = 0
        for pid in set(paint_ids):
            try:
                self.context.event_bus.emit("project_link_entity", {
                    "project_id":  project_id,
                    "entity_type": "paint",
                    "entity_id":   pid,
                    "notes":       f"Chroma Codex — {self._current_result.style}",
                })
                linked += 1
            except Exception as e:
                log.error(f"[CHROMA UI] Link paint {pid} failed: {e}")

        if self._current_scheme_id and self._repo:
            try:
                self._repo.update(self._current_scheme_id, linked_project_id=project_id)
                self._refresh_project_lookup()
                self._load_saved_list(self._current_scheme_id)
            except Exception:
                pass

        self._show_status(
            f"Linked {linked} paint{'s' if linked != 1 else ''} to project.", success=True)

    # ── Status ────────────────────────────────────────────────────────────────

    def _show_status(self, msg: str, success: bool | None = True):
        color = "#3dba6e" if success is True else "#e05555" if success is False else "#f5a623"
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(
            f"font-size:11px; font-weight:600; color:{color}; background:transparent;")
        self._status_timer.start(4000)

    def _clear_status(self):
        self._status_lbl.setText("")
