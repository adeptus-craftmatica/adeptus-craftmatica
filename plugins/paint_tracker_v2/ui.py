"""
Paint Tracker 2.0 — card-grid UI
Redesigned with paint-pot style circular swatches and a premium feel.
"""
from __future__ import annotations

import re
import csv
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIntValidator, QPainter, QPen, QBrush, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QComboBox, QCheckBox, QDialog, QDialogButtonBox,
    QGridLayout, QSizePolicy, QApplication, QSpinBox, QTextEdit, QColorDialog,
    QMessageBox, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QFileDialog, QTabWidget,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_CARD_W   = 160
_CARD_H   = 240
_SWATCH_D = 84    # diameter of the circular paint-pot swatch

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ── Type / level colour mappings ──────────────────────────────────────────────

_TYPE_COLORS: dict[str, str] = {
    "Base":      "#1565c0",
    "Layer":     "#0288d1",
    "Shade":     "#6a1b9a",
    "Dry":       "#8d6e63",
    "Contrast":  "#e65100",
    "Metallic":  "#f9a825",
    "Technical": "#546e7a",
    "Air":       "#00838f",
    "Texture":   "#4e342e",
    "Primer":    "#37474f",
    "Varnish":   "#1b5e20",
}

_LEVEL_COLORS: dict[str, str] = {
    "Full":        "#4caf50",
    "Half-Bottle": "#f57f17",
    "Low":         "#e65100",
    "Out":         "#c62828",
}

_ALL_TYPES = [
    "Base", "Layer", "Shade", "Dry", "Contrast",
    "Metallic", "Technical", "Air", "Texture", "Primer", "Varnish",
]

_ALL_LEVELS = ["Full", "Half-Bottle", "Low", "Out"]


# ── Colour helpers ────────────────────────────────────────────────────────────

def _type_color(t: str) -> str:
    return _TYPE_COLORS.get(t, "#546e7a")


def _level_color(l: str) -> str:
    return _LEVEL_COLORS.get(l, "#808080")


def _contrasting_text(hex_bg: str) -> str:
    try:
        h = hex_bg.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return "#1a1a1a" if (0.299 * r + 0.587 * g + 0.114 * b) > 128 else "#ffffff"
    except Exception:
        return "#ffffff"


def _valid_hex(s: str) -> bool:
    return bool(_HEX_RE.match(s or ""))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = (hex_color or "#000000").strip().lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _color_distance(a: str, b: str) -> float:
    try:
        ar, ag, ab = _hex_to_rgb(a)
        br, bg, bb = _hex_to_rgb(b)
        return ((ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2) ** 0.5
    except Exception:
        return 999.0


def _match_confidence(distance: float) -> int:
    return max(0, min(100, round(100 - (distance / 441.7 * 100))))


def _polish_combo(combo: QComboBox, width: int, popup_width: Optional[int] = None):
    combo.setMinimumWidth(width)
    combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    try:
        combo.view().setMinimumWidth(popup_width or width)
    except Exception:
        pass


def _fit_combo_to_items(combo: QComboBox, min_width: int, max_width: int):
    fm = combo.fontMetrics()
    longest = ""
    for i in range(combo.count()):
        text = combo.itemText(i)
        if fm.horizontalAdvance(text) > fm.horizontalAdvance(longest):
            longest = text
    width = max(min_width, min(max_width, fm.horizontalAdvance(longest) + 44))
    combo.setMinimumWidth(width)
    try:
        combo.view().setMinimumWidth(max(width, min(max_width, fm.horizontalAdvance(longest) + 54)))
    except Exception:
        pass


def _label_style(label: QLabel, color: str, size: int, bold: bool = False,
                 bg: Optional[str] = None):
    font = label.font()
    font.setPointSize(size)
    font.setBold(bold)
    label.setFont(font)
    rules = [
        f"color: {color};",
        f"font-size: {size}px;",
        "font-weight: bold;" if bold else "font-weight: normal;",
        f"background-color: {bg};" if bg is not None else "background-color: transparent;",
    ]
    label.setStyleSheet(" ".join(rules))


def _two_line_label(text: str, fm: QFontMetrics, width: int) -> str:
    if fm.horizontalAdvance(text) <= width:
        return text

    words = text.split()
    if len(words) <= 1:
        return fm.elidedText(text, Qt.ElideRight, width)

    best = None
    best_score = 10**9
    for idx in range(1, len(words)):
        first = " ".join(words[:idx])
        second = " ".join(words[idx:])
        w1 = fm.horizontalAdvance(first)
        w2 = fm.horizontalAdvance(second)
        if w1 <= width and w2 <= width:
            score = abs(w1 - w2)
            if score < best_score:
                best = (first, second)
                best_score = score

    if best:
        return f"{best[0]}\n{best[1]}"

    first = words[0]
    second = fm.elidedText(" ".join(words[1:]), Qt.ElideRight, width)
    return f"{first}\n{second}"


def _type_chip_style(label: QLabel, text: str, bg: str, fg: str, max_width: int):
    label.setAlignment(Qt.AlignCenter)
    label.setWordWrap(False)
    label.setFixedWidth(max_width)
    label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    size = 9
    while size > 7:
        font = label.font()
        font.setPointSize(size)
        font.setBold(True)
        fm = QFontMetrics(font)
        display = _two_line_label(text, fm, max_width - 14)
        if "\n" not in display or all(fm.horizontalAdvance(line) <= max_width - 14 for line in display.splitlines()):
            break
        size -= 1

    label.setFont(font)
    label.setText(display)
    label.setToolTip(text)
    label.setFixedHeight(34)
    label.setStyleSheet(
        f"color: {fg}; background-color: {bg}; font-size: {size}px;"
        " font-weight: bold; border-radius: 7px; padding: 3px 6px;"
    )


def _stock_badge_text(quantity: int) -> str:
    if quantity <= 0:
        return "Out"
    if quantity == 1:
        return "Low"
    return f"×{quantity}"


def _stock_badge_colors(quantity: int) -> tuple[str, str]:
    if quantity <= 0:
        return "#9f2720", "#ffffff"
    if quantity == 1:
        return "#9a5a12", "#ffffff"
    return "#101010", "#e0e0e0"


def _apply_stock_badge(label: QLabel, quantity: int):
    bg, fg = _stock_badge_colors(quantity)
    label.setText(_stock_badge_text(quantity))
    label.setMargin(4)
    _label_style(label, fg, 10, bold=True, bg=bg)


# ── Vertical separator ────────────────────────────────────────────────────────

def _vline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setFixedWidth(1)
    f.setStyleSheet("background-color: #333333;")
    return f


class _ColorDot(QWidget):
    def __init__(self, hex_color: str, size: int = 24, parent=None):
        super().__init__(parent)
        self._color = QColor(hex_color if _valid_hex(hex_color) else "#808080")
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(QColor("#4a4a4a"), 1))
        painter.drawEllipse(self.rect().adjusted(2, 2, -2, -2))


# ── Paint card ────────────────────────────────────────────────────────────────

class _PaintCard(QFrame):
    edit_requested    = Signal(object)
    delete_requested  = Signal(object)
    stock_adjusted    = Signal(object, int)
    similar_requested = Signal(str)
    favourite_toggled = Signal(object)

    def __init__(self, paint, parent=None):
        super().__init__(parent)
        self._paint = paint
        self.setObjectName("paintCard")
        self.setFixedSize(_CARD_W, _CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("""
            QFrame#paintCard {
                background-color: #1c1c1c;
                border: 1px solid #2e2e2e;
                border-radius: 12px;
            }
        """)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 12)
        root.setSpacing(0)

        # ── Top row: fav button aligned right (in layout — avoids corner clip) ─
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        top_row.addStretch()

        self._fav_btn = QPushButton("⭐" if self._paint.is_favorite else "☆")
        self._fav_btn.setFixedSize(26, 26)
        self._fav_btn.setStyleSheet(
            "QPushButton { background-color: transparent; border: none;"
            " font-size: 14px; padding: 0; border-radius: 13px; }"
            "QPushButton:hover { background-color: #333333; }"
        )
        self._fav_btn.setCursor(Qt.PointingHandCursor)
        self._fav_btn.clicked.connect(self._toggle_favourite)
        top_row.addWidget(self._fav_btn)
        root.addLayout(top_row)

        root.addSpacing(4)

        # ── Circular swatch ──────────────────────────────────────────────────
        swatch_container = QWidget()
        swatch_container.setFixedHeight(_SWATCH_D + 4)
        sc_layout = QHBoxLayout(swatch_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setAlignment(Qt.AlignCenter)

        self._swatch = QFrame()
        self._swatch.setObjectName("paintCardSwatch")
        self._swatch.setFixedSize(_SWATCH_D, _SWATCH_D)
        self._apply_swatch_style(self._paint.color)
        sc_layout.addWidget(self._swatch)
        root.addWidget(swatch_container)

        # Quantity badge — absolute, anchored bottom-right of the swatch circle
        self._qty_badge = QLabel(self)
        _apply_stock_badge(self._qty_badge, self._paint.quantity)
        self._qty_badge.adjustSize()
        self._reposition_qty_badge()

        root.addSpacing(10)

        # ── Brand ────────────────────────────────────────────────────────────
        self._brand_lbl = QLabel()
        self._brand_lbl.setAlignment(Qt.AlignCenter)
        _label_style(self._brand_lbl, "#686868", 10)
        self._brand_lbl.setFixedWidth(_CARD_W - 20)
        self._brand_lbl.setText(
            self._brand_lbl.fontMetrics().elidedText(
                self._paint.brand, Qt.ElideRight, _CARD_W - 20
            )
        )
        root.addWidget(self._brand_lbl)

        root.addSpacing(2)

        # ── Name ─────────────────────────────────────────────────────────────
        self._name_lbl = QLabel()
        self._name_lbl.setAlignment(Qt.AlignCenter)
        _label_style(self._name_lbl, "#f0f0f0", 12, bold=True)
        self._name_lbl.setFixedWidth(_CARD_W - 20)
        self._name_lbl.setText(
            self._name_lbl.fontMetrics().elidedText(
                self._paint.name, Qt.ElideRight, _CARD_W - 20
            )
        )
        root.addWidget(self._name_lbl)

        # ── Type chip ────────────────────────────────────────────────────────
        chip_slot = QWidget()
        chip_slot.setFixedHeight(38)
        chip_row = QHBoxLayout(chip_slot)
        chip_row.setContentsMargins(0, 2, 0, 2)
        chip_row.setSpacing(0)
        chip_row.setAlignment(Qt.AlignCenter)
        chip_row.addStretch()

        chip_bg = _type_color(self._paint.paint_type)
        chip_fg = _contrasting_text(chip_bg)
        type_chip = QLabel(self._paint.paint_type)
        _type_chip_style(type_chip, self._paint.paint_type, chip_bg, chip_fg, _CARD_W - 28)
        chip_row.addWidget(type_chip)
        chip_row.addStretch()
        root.addWidget(chip_slot)

        # ── Level indicator ──────────────────────────────────────────────────
        level_slot = QWidget()
        level_slot.setFixedHeight(18)
        level_row = QHBoxLayout(level_slot)
        level_row.setContentsMargins(0, 0, 0, 0)
        level_row.setSpacing(4)
        level_row.addStretch()
        if self._paint.level:
            dot = QLabel("●")
            _label_style(dot, _level_color(self._paint.level), 9)
            lev = QLabel(self._paint.level)
            _label_style(lev, "#909090", 10)
            level_row.addWidget(dot)
            level_row.addWidget(lev)
        level_row.addStretch()
        root.addWidget(level_slot)

        root.addStretch()

        # ── Hover overlay (full card) ─────────────────────────────────────────
        self._overlay = QWidget(self)
        self._overlay.setGeometry(0, 0, _CARD_W, _CARD_H)
        self._overlay.setStyleSheet(
            "QWidget { background-color: #080808; border-radius: 12px; }"
        )
        ov = QVBoxLayout(self._overlay)
        ov.setAlignment(Qt.AlignCenter)
        ov.setSpacing(6)
        ov.setContentsMargins(14, 14, 14, 14)

        # Paint name at top of overlay
        ov_name = QLabel(self._paint.name)
        ov_name.setAlignment(Qt.AlignCenter)
        ov_name.setWordWrap(True)
        _label_style(ov_name, "#ffffff", 12, bold=True)
        ov.addWidget(ov_name)
        ov.addSpacing(2)

        btn_style = (
            "QPushButton { background-color: #242424; color: #e8e8e8;"
            " border: 1px solid #3a3a3a; border-radius: 6px;"
            " font-size: 11px; padding: 0 8px; }"
            "QPushButton:hover { background-color: #0078d4; border-color: #0078d4;"
            " color: #ffffff; }"
        )

        btn_edit = QPushButton("✏  Edit")
        btn_edit.setFixedSize(120, 30)
        btn_edit.setStyleSheet(btn_style)
        btn_edit.setCursor(Qt.PointingHandCursor)
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self._paint))

        btn_stock = QPushButton("＋  Stock +1")
        btn_stock.setFixedSize(120, 30)
        btn_stock.setStyleSheet(btn_style)
        btn_stock.setCursor(Qt.PointingHandCursor)
        btn_stock.clicked.connect(lambda: self.stock_adjusted.emit(self._paint, 1))

        btn_similar = QPushButton("🔍  Similar")
        btn_similar.setFixedSize(120, 30)
        btn_similar.setStyleSheet(btn_style)
        btn_similar.setCursor(Qt.PointingHandCursor)
        btn_similar.clicked.connect(lambda: self.similar_requested.emit(self._paint.color))

        btn_delete = QPushButton("Delete")
        btn_delete.setFixedSize(120, 30)
        btn_delete.setStyleSheet(
            btn_style +
            "QPushButton:hover { background-color: #b3261e; border-color: #b3261e; color: #ffffff; }"
        )
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.clicked.connect(lambda: self.delete_requested.emit(self._paint))

        ov.addWidget(btn_edit)
        ov.addWidget(btn_stock)
        ov.addWidget(btn_similar)
        ov.addWidget(btn_delete)

        self._overlay.hide()
        self._overlay.raise_()
        # Fav button must always sit above the overlay in the z-order
        self._fav_btn.raise_()

    # ── Style helpers ─────────────────────────────────────────────────────────

    def _apply_swatch_style(self, color: str):
        r = _SWATCH_D // 2
        self._swatch.setStyleSheet(
            f"QFrame#paintCardSwatch {{"
            f" background-color: {color};"
            f" border-radius: {r}px;"
            f" border: 3px solid #4a4a4a;"
            f"}}"
        )

    def _reposition_qty_badge(self):
        self._qty_badge.adjustSize()
        # Place bottom-right of the circle, slightly inset
        cx = _CARD_W // 2
        r  = _SWATCH_D // 2
        bw = self._qty_badge.width()
        bh = self._qty_badge.height()
        x  = cx + r - bw + 6
        y  = 16 + _SWATCH_D - bh + 2   # top margin + swatch height - badge height + overlap
        self._qty_badge.move(x, y)
        self._qty_badge.raise_()

    # ── Events ────────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._overlay.show()
        self._overlay.raise_()
        self._fav_btn.raise_()   # always on top of the overlay
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._overlay.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        self._overlay.setGeometry(0, 0, _CARD_W, _CARD_H)
        super().resizeEvent(event)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_favourite(self):
        self.favourite_toggled.emit(self._paint)

    def refresh(self, paint):
        self._paint = paint
        self._apply_swatch_style(paint.color)
        self._fav_btn.setText("⭐" if paint.is_favorite else "☆")
        _apply_stock_badge(self._qty_badge, paint.quantity)
        self._reposition_qty_badge()


# ── Quick Add Bar ─────────────────────────────────────────────────────────────

class _QuickAddBar(QWidget):
    submitted = Signal(dict)

    _NEUTRAL = "#808080"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._color = self._NEUTRAL
        self._build()

    def _build(self):
        self._root_layout = QHBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(6)

        # Collapsed button
        self._add_btn = QPushButton("＋  Add Paint")
        self._add_btn.setObjectName("primaryBtn")
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.clicked.connect(self._expand)
        self._root_layout.addWidget(self._add_btn)

        # Expanded form (hidden by default)
        self._form_widget = QWidget()
        self._form_widget.hide()
        form_layout = QHBoxLayout(self._form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        self._brand_input = QComboBox()
        self._brand_input.setEditable(True)
        self._brand_input.setInsertPolicy(QComboBox.NoInsert)
        self._brand_input.lineEdit().setPlaceholderText("Brand…")
        _polish_combo(self._brand_input, 140, 220)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Name…")

        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)
        self._type_combo.setInsertPolicy(QComboBox.NoInsert)
        for t in _ALL_TYPES:
            self._type_combo.addItem(t)
        _polish_combo(self._type_combo, 140, 190)

        self._color_swatch = QFrame()
        self._color_swatch.setFixedSize(30, 30)
        self._color_swatch.setCursor(Qt.PointingHandCursor)
        self._color_swatch.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #555; border-radius: 15px;"
        )
        self._color_swatch.mousePressEvent = lambda _: self._pick_color()

        self._hex_input = QLineEdit(self._color)
        self._hex_input.setFixedWidth(80)
        self._hex_input.setPlaceholderText("#RRGGBB")
        self._hex_input.textChanged.connect(self._on_hex_changed)

        self._qty_input = QSpinBox()
        self._qty_input.setRange(0, 999)
        self._qty_input.setValue(1)
        self._qty_input.setFixedWidth(58)
        self._qty_input.setToolTip("Quantity on hand")

        self._submit_btn = QPushButton("Add")
        self._submit_btn.setObjectName("primaryBtn")
        self._submit_btn.setCursor(Qt.PointingHandCursor)
        self._submit_btn.clicked.connect(self._on_submit)
        self._name_input.returnPressed.connect(self._on_submit)
        self._brand_input.lineEdit().returnPressed.connect(self._on_submit)
        self._type_combo.lineEdit().returnPressed.connect(self._on_submit)
        self._hex_input.returnPressed.connect(self._on_submit)

        self._collapse_btn = QPushButton("✕")
        self._collapse_btn.setObjectName("secondaryBtn")
        self._collapse_btn.setFixedWidth(28)
        self._collapse_btn.setCursor(Qt.PointingHandCursor)
        self._collapse_btn.clicked.connect(self._collapse)

        form_layout.addWidget(self._brand_input)
        form_layout.addWidget(self._name_input, 1)
        form_layout.addWidget(self._type_combo)
        form_layout.addWidget(self._color_swatch)
        form_layout.addWidget(self._hex_input)
        form_layout.addWidget(self._qty_input)
        form_layout.addWidget(self._submit_btn)
        form_layout.addWidget(self._collapse_btn)

        self._root_layout.addWidget(self._form_widget)
        self._root_layout.addStretch()

    def _expand(self):
        self._add_btn.hide()
        self._form_widget.show()
        self._expanded = True
        self._brand_input.setFocus()

    def expand(self):
        if not self._expanded:
            self._expand()
        else:
            self._brand_input.setFocus()

    def update_options(self, brands: list[str], types: list[str]):
        def refill(combo: QComboBox, values: list[str], fallback: list[str] | None = None):
            current = combo.currentText().strip()
            combo.blockSignals(True)
            combo.clear()
            seen = set()
            for value in list(fallback or []) + list(values):
                text = (value or "").strip()
                key = text.lower()
                if text and key not in seen:
                    combo.addItem(text)
                    seen.add(key)
            combo.setCurrentText(current)
            combo.blockSignals(False)

        refill(self._brand_input, brands)
        refill(self._type_combo, types, _ALL_TYPES)
        _fit_combo_to_items(self._brand_input, 140, 240)
        _fit_combo_to_items(self._type_combo, 140, 260)

    def _collapse(self):
        self._form_widget.hide()
        self._add_btn.show()
        self._expanded = False
        self._clear_validation()

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._color), self)
        if color.isValid():
            self._color = color.name().upper()
            self._hex_input.blockSignals(True)
            self._hex_input.setText(self._color)
            self._hex_input.blockSignals(False)
            self._update_swatch()

    def _on_hex_changed(self, text: str):
        if _valid_hex(text):
            self._color = text.upper()
            self._update_swatch()
            self._hex_input.setStyleSheet("")
        else:
            self._hex_input.setStyleSheet("border: 1px solid #e05555;")

    def _update_swatch(self):
        self._color_swatch.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #555; border-radius: 15px;"
        )

    def _clear_validation(self):
        for w in (self._brand_input.lineEdit(), self._name_input, self._hex_input):
            w.setStyleSheet("")

    def _on_submit(self):
        brand = self._brand_input.currentText().strip()
        name  = self._name_input.text().strip()
        paint_type = self._type_combo.currentText().strip()
        color = self._hex_input.text().strip()

        valid = True
        for field, val in ((self._brand_input.lineEdit(), brand), (self._name_input, name)):
            if not val:
                field.setStyleSheet("border: 1px solid #e05555;")
                valid = False
            else:
                field.setStyleSheet("")

        if not _valid_hex(color):
            self._hex_input.setStyleSheet("border: 1px solid #e05555;")
            valid = False
        else:
            self._hex_input.setStyleSheet("")

        if not valid:
            return

        self.submitted.emit({
            "brand": brand, "name": name, "paint_type": paint_type,
            "color": color.upper(), "quantity": self._qty_input.value(), "level": None,
            "notes": "", "is_favorite": False, "notify_low_stock": True,
        })
        self._reset_inputs()
        self._collapse()

    def _reset_inputs(self):
        self._brand_input.setCurrentText("")
        self._name_input.clear()
        self._type_combo.setCurrentIndex(0)
        self._qty_input.setValue(1)
        self._color = self._NEUTRAL
        self._hex_input.setText(self._color)
        self._update_swatch()
        self._clear_validation()


# ── Filter Bar ────────────────────────────────────────────────────────────────

class _FilterBar(QFrame):
    filter_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color_hex: Optional[str] = None
        self._block_signals = False
        self.setObjectName("filterBar")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame#filterBar { background-color: #161616; border: 1px solid #2a2a2a;"
            " border-radius: 8px; }"
        )
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setObjectName("filterSearch")
        self._search.setPlaceholderText("🔍  Search paints…")
        self._search.setMinimumWidth(160)
        self._search.textChanged.connect(self._emit)

        self._brand_combo = QComboBox()
        self._brand_combo.addItem("All Brands")
        _polish_combo(self._brand_combo, 150, 220)
        self._brand_combo.currentIndexChanged.connect(self._emit)

        self._type_combo = QComboBox()
        self._type_combo.addItem("All Types")
        for t in _ALL_TYPES:
            self._type_combo.addItem(t)
        _polish_combo(self._type_combo, 130, 170)
        self._type_combo.currentIndexChanged.connect(self._emit)

        self._level_combo = QComboBox()
        self._level_combo.addItem("All Levels")
        for l in _ALL_LEVELS:
            self._level_combo.addItem(l)
        _polish_combo(self._level_combo, 145, 170)
        self._level_combo.currentIndexChanged.connect(self._emit)

        # Colour filter swatch + button
        self._color_swatch = QFrame()
        self._color_swatch.setFixedSize(20, 20)
        self._color_swatch.setStyleSheet(
            "background-color: transparent; border: 1px solid #555; border-radius: 10px;"
        )

        self._color_btn = QPushButton("Colour…")
        self._color_btn.setObjectName("secondaryBtn")
        self._color_btn.setCursor(Qt.PointingHandCursor)
        self._color_btn.clicked.connect(self._pick_color)

        self._color_clear = QPushButton("✕")
        self._color_clear.setObjectName("secondaryBtn")
        self._color_clear.setFixedWidth(24)
        self._color_clear.setCursor(Qt.PointingHandCursor)
        self._color_clear.clicked.connect(self._clear_color)
        self._color_clear.hide()

        self._reset_btn = QPushButton("↺  Reset")
        self._reset_btn.setObjectName("secondaryBtn")
        self._reset_btn.setCursor(Qt.PointingHandCursor)
        self._reset_btn.clicked.connect(self.reset)

        layout.addWidget(self._search, 2)
        layout.addWidget(_vline())
        layout.addWidget(self._brand_combo)
        layout.addWidget(self._type_combo)
        layout.addWidget(self._level_combo)
        layout.addWidget(_vline())
        layout.addWidget(self._color_swatch)
        layout.addWidget(self._color_btn)
        layout.addWidget(self._color_clear)
        layout.addWidget(_vline())
        layout.addWidget(self._reset_btn)

    def update_brands(self, brands: list[str]):
        self._block_signals = True
        current = self._brand_combo.currentText()
        self._brand_combo.clear()
        self._brand_combo.addItem("All Brands")
        for b in brands:
            self._brand_combo.addItem(b)
        idx = self._brand_combo.findText(current)
        if idx >= 0:
            self._brand_combo.setCurrentIndex(idx)
        self._block_signals = False

    def update_types(self, types: list[str]):
        self._block_signals = True
        current = self._type_combo.currentText()
        self._type_combo.clear()
        self._type_combo.addItem("All Types")
        seen = set()
        for value in list(_ALL_TYPES) + list(types):
            text = (value or "").strip()
            key = text.lower()
            if text and key not in seen:
                self._type_combo.addItem(text)
                seen.add(key)
        idx = self._type_combo.findText(current)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        _fit_combo_to_items(self._type_combo, 130, 230)
        self._block_signals = False

    def _pick_color(self):
        start = QColor(self._color_hex) if self._color_hex else QColor("#808080")
        color = QColorDialog.getColor(start, self)
        if color.isValid():
            self._color_hex = color.name().upper()
            self._color_swatch.setStyleSheet(
                f"background-color: {self._color_hex}; border: 1px solid #555; border-radius: 10px;"
            )
            self._color_clear.show()
            self._emit()

    def _clear_color(self):
        self._color_hex = None
        self._color_swatch.setStyleSheet(
            "background-color: transparent; border: 1px solid #555; border-radius: 10px;"
        )
        self._color_clear.hide()
        self._emit()

    def set_level(self, level: Optional[str]):
        self._block_signals = True
        idx = self._level_combo.findText(level or "All Levels")
        if idx >= 0:
            self._level_combo.setCurrentIndex(idx)
        self._block_signals = False

    def set_color(self, hex_color: Optional[str]):
        self._block_signals = True
        self._color_hex = hex_color.upper() if hex_color and _valid_hex(hex_color) else None
        if self._color_hex:
            self._color_swatch.setStyleSheet(
                f"background-color: {self._color_hex}; border: 1px solid #555; border-radius: 10px;"
            )
            self._color_clear.show()
        else:
            self._color_swatch.setStyleSheet(
                "background-color: transparent; border: 1px solid #555; border-radius: 10px;"
            )
            self._color_clear.hide()
        self._block_signals = False

    def focus_search(self):
        self._search.setFocus()
        self._search.selectAll()

    def get_state(self) -> dict:
        brand = self._brand_combo.currentText()
        ptype = self._type_combo.currentText()
        level = self._level_combo.currentText()
        return {
            "search":     self._search.text().strip(),
            "brand":      brand if brand != "All Brands"  else "",
            "type":       ptype if ptype != "All Types"   else "",
            "level":      level if level != "All Levels"  else "",
            "color_hex":  self._color_hex or "",
        }

    def reset(self):
        self._block_signals = True
        self._search.clear()
        self._brand_combo.setCurrentIndex(0)
        self._type_combo.setCurrentIndex(0)
        self._level_combo.setCurrentIndex(0)
        self._color_hex = None
        self._color_swatch.setStyleSheet(
            "background-color: transparent; border: 1px solid #555; border-radius: 10px;"
        )
        self._color_clear.hide()
        self._block_signals = False
        self._emit()

    def _emit(self, *_):
        if self._block_signals:
            return
        self.filter_changed.emit(self.get_state())


# ── Preset Chips ──────────────────────────────────────────────────────────────

class _PresetChips(QWidget):
    preset_changed = Signal(str)

    _PRESETS = [
        ("All",           "all"),
        ("⚠  Low Stock",  "low_stock"),
        ("❌  Out",        "out"),
        ("⭐  Favourites", "favourites"),
        ("🔔  Notify",    "notify"),
    ]

    _ACTIVE = (
        "QPushButton { background-color: #0078d4; color: #ffffff;"
        " border: none; border-radius: 5px; padding: 4px 12px; font-size: 12px; }"
    )
    _INACTIVE = (
        "QPushButton { background-color: #252525; color: #a0a0a0;"
        " border: 1px solid #353535; border-radius: 5px; padding: 4px 12px; font-size: 12px; }"
        "QPushButton:hover { background-color: #303030; color: #e0e0e0; }"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = "all"
        self._buttons: dict[str, QPushButton] = {}
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for label, key in self._PRESETS:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._ACTIVE if key == "all" else self._INACTIVE)
            btn.clicked.connect(lambda _, k=key: self._on_click(k))
            self._buttons[key] = btn
            layout.addWidget(btn)
        layout.addStretch()

    def _on_click(self, key: str):
        self._active = key
        for k, btn in self._buttons.items():
            btn.setStyleSheet(self._ACTIVE if k == key else self._INACTIVE)
        self.preset_changed.emit(key)

    def set_active(self, key: str):
        """Update visual state only — does NOT emit preset_changed."""
        if key in self._buttons:
            self._active = key
            for k, btn in self._buttons.items():
                btn.setStyleSheet(self._ACTIVE if k == key else self._INACTIVE)


# ── Card Grid ─────────────────────────────────────────────────────────────────

class _CardGrid(QWidget):
    edit_requested    = Signal(object)
    delete_requested  = Signal(object)
    stock_adjusted    = Signal(object, int)
    similar_requested = Signal(str)
    favourite_toggled = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paints: list = []
        self._group_by = "none"
        self._last_cols = 0
        self._empty_message = "No paints match your filters."

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)

        self._scroll.setWidget(QWidget())   # placeholder

    def _cols(self) -> int:
        vp_w = self._scroll.viewport().width()
        if vp_w < _CARD_W:
            vp_w = max(_CARD_W, self.width() - 32)
        spacing = 14
        return max(1, (vp_w - spacing) // (_CARD_W + spacing))

    def showEvent(self, event):
        super().showEvent(event)
        if self._paints and self._cols() != self._last_cols:
            QTimer.singleShot(0, self._rebuild)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._paints and self._cols() != self._last_cols:
            self._rebuild()

    def load(self, paints: list, empty_message: str = "", group_by: str = "none"):
        self._paints = paints
        self._group_by = group_by or "none"
        self._empty_message = empty_message or "No paints match your filters."
        QTimer.singleShot(0, self._rebuild)

    def _group_title(self, paint) -> str:
        if self._group_by == "brand":
            return paint.brand or "Unbranded"
        if self._group_by == "type":
            return paint.paint_type or "Unspecified Type"
        if self._group_by == "stock":
            if paint.quantity <= 0:
                return "Out of Stock"
            if paint.quantity == 1:
                return "Low Stock"
            return "In Stock"
        return ""

    def _add_group_header(self, grid: QGridLayout, row: int, cols: int, title: str, count: int):
        frame = QFrame()
        frame.setObjectName("paintGroupHeader")
        frame.setStyleSheet(
            "QFrame#paintGroupHeader { background-color: #151515;"
            " border: 1px solid #2a2a2a; border-radius: 8px; }"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 6, 10, 6)
        name = QLabel(title)
        _label_style(name, "#f0f0f0", 12, bold=True)
        badge = QLabel(f"{count} paint{'s' if count != 1 else ''}")
        _label_style(badge, "#8a8a8a", 11)
        lay.addWidget(name)
        lay.addStretch()
        lay.addWidget(badge)
        grid.addWidget(frame, row, 0, 1, max(cols, 1))

    def _rebuild(self):
        cols = self._cols()
        self._last_cols = cols

        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(14)
        grid.setContentsMargins(4, 4, 4, 4)
        for c in range(cols):
            grid.setColumnStretch(c, 0)

        if not self._paints:
            lbl = QLabel(self._empty_message)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setMinimumHeight(180)
            lbl.setMargin(36)
            _label_style(lbl, "#707070", 15)
            grid.addWidget(lbl, 0, 0, 1, max(cols, 1))
        else:
            row = col = 0
            groups: list[tuple[str, list]] = []
            if self._group_by == "none":
                groups = [("", self._paints)]
            else:
                grouped: dict[str, list] = {}
                order: list[str] = []
                for paint in self._paints:
                    title = self._group_title(paint)
                    if title not in grouped:
                        grouped[title] = []
                        order.append(title)
                    grouped[title].append(paint)
                groups = [(title, grouped[title]) for title in order]

            for title, paints in groups:
                if title:
                    if col != 0:
                        row += 1
                        col = 0
                    self._add_group_header(grid, row, cols, title, len(paints))
                    row += 1
                for paint in paints:
                    card = _PaintCard(paint)
                    card.edit_requested.connect(self.edit_requested)
                    card.delete_requested.connect(self.delete_requested)
                    card.stock_adjusted.connect(self.stock_adjusted)
                    card.similar_requested.connect(self.similar_requested)
                    card.favourite_toggled.connect(self.favourite_toggled)
                    grid.addWidget(card, row, col, Qt.AlignTop)
                    col += 1
                    if col >= cols:
                        col = 0
                        row += 1
                if col != 0:
                    row += 1
                    col = 0

        self._scroll.setWidget(inner)


# ── Table View ────────────────────────────────────────────────────────────────

class _TableView(QWidget):
    edit_requested    = Signal(object)
    delete_requested  = Signal(object)
    stock_adjusted    = Signal(object, int)
    favourite_toggled = Signal(object)

    _COL_FAV   = 0
    _COL_COLOR = 1
    _COL_BRAND = 2
    _COL_NAME  = 3
    _COL_TYPE  = 4
    _COL_QTY   = 5
    _COL_LEVEL = 6
    _COL_NOTES = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_paints: list = []
        self._paints: list = []
        self._sort_column = self._COL_BRAND
        self._sort_desc = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            ["♥", "Color", "Brand", "Name", "Type", "Qty", "Level", "Notes"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(
            "QTableWidget { border: none; gridline-color: transparent; }"
            "QTableWidget::item { padding: 4px 8px; }"
        )

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(self._COL_FAV,   QHeaderView.Fixed)
        hdr.setSectionResizeMode(self._COL_COLOR, QHeaderView.Fixed)
        hdr.setSectionResizeMode(self._COL_BRAND, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_NAME,  QHeaderView.Stretch)
        hdr.setSectionResizeMode(self._COL_TYPE,  QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_QTY,   QHeaderView.Fixed)
        hdr.setSectionResizeMode(self._COL_LEVEL, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self._COL_NOTES, QHeaderView.Stretch)
        hdr.setSectionsClickable(True)
        hdr.setSortIndicatorShown(False)
        hdr.sectionClicked.connect(self._on_header_clicked)

        self._table.setColumnWidth(self._COL_FAV,   34)
        self._table.setColumnWidth(self._COL_COLOR, 76)
        self._table.setColumnWidth(self._COL_QTY,   46)
        self._table.setRowHeight(0, 36)   # default row height

        self._table.doubleClicked.connect(self._on_double_click)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self._table)

    def load(self, paints: list):
        self._base_paints = list(paints)
        self._paints = self._sorted_paints(self._base_paints)
        self._render()

    def _render(self):
        self._table.setRowCount(0)
        for row_idx, paint in enumerate(self._paints):
            self._table.insertRow(row_idx)
            self._table.setRowHeight(row_idx, 36)

            # ♥ Favourite
            fav = QTableWidgetItem("⭐" if paint.is_favorite else "☆")
            fav.setTextAlignment(Qt.AlignCenter)
            fav.setToolTip("Favourite" if paint.is_favorite else "Not favourite")
            self._table.setItem(row_idx, self._COL_FAV, fav)

            # Color — clean circle swatch widget (no hex text)
            swatch_w = QWidget()
            swatch_w.setStyleSheet("background-color: transparent;")
            sw_layout = QHBoxLayout(swatch_w)
            sw_layout.setAlignment(Qt.AlignCenter)
            sw_layout.setContentsMargins(4, 4, 4, 4)
            circle = QFrame()
            circle.setFixedSize(22, 22)
            circle.setStyleSheet(
                f"background-color: {paint.color}; border-radius: 11px;"
                f" border: 1px solid #4a4a4a;"
            )
            circle.setToolTip(f"{paint.color}")
            sw_layout.addWidget(circle)
            self._table.setCellWidget(row_idx, self._COL_COLOR, swatch_w)

            # Brand
            self._table.setItem(row_idx, self._COL_BRAND,
                                QTableWidgetItem(paint.brand))

            # Name
            self._table.setItem(row_idx, self._COL_NAME,
                                QTableWidgetItem(paint.name))

            # Type — coloured text
            type_item = QTableWidgetItem(paint.paint_type)
            type_item.setForeground(QColor(_type_color(paint.paint_type)))
            self._table.setItem(row_idx, self._COL_TYPE, type_item)

            # Qty
            qty_item = QTableWidgetItem(str(paint.quantity))
            qty_item.setTextAlignment(Qt.AlignCenter)
            if paint.quantity <= 0:
                qty_item.setForeground(QColor("#e05555"))
                qty_item.setToolTip("Out of stock")
            elif paint.quantity == 1:
                qty_item.setForeground(QColor("#e08030"))
                qty_item.setToolTip("Low stock")
            self._table.setItem(row_idx, self._COL_QTY, qty_item)

            # Level — coloured text
            level_text = paint.level or "—"
            level_item = QTableWidgetItem(level_text)
            if paint.level:
                level_item.setForeground(QColor(_level_color(paint.level)))
            self._table.setItem(row_idx, self._COL_LEVEL, level_item)

            # Notes
            self._table.setItem(row_idx, self._COL_NOTES,
                                QTableWidgetItem(paint.notes or ""))

    def _on_header_clicked(self, column: int):
        if column == self._sort_column:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_column = column
            self._sort_desc = False
        self._paints = self._sorted_paints(self._base_paints)
        self._render()

    def _sorted_paints(self, paints: list) -> list:
        def text(value) -> str:
            return (value or "").lower()

        def stock_rank(paint) -> tuple:
            if paint.quantity <= 0:
                status = 0
            elif paint.quantity == 1:
                status = 1
            else:
                status = 2
            return (status, paint.quantity)

        key_map = {
            self._COL_FAV:   lambda p: (not p.is_favorite, text(p.brand), text(p.name)),
            self._COL_COLOR: lambda p: (text(p.color), text(p.brand), text(p.name)),
            self._COL_BRAND: lambda p: (text(p.brand), text(p.name)),
            self._COL_NAME:  lambda p: (text(p.name), text(p.brand)),
            self._COL_TYPE:  lambda p: (text(p.paint_type), text(p.brand), text(p.name)),
            self._COL_QTY:   lambda p: (*stock_rank(p), text(p.brand), text(p.name)),
            self._COL_LEVEL: lambda p: (text(p.level), text(p.brand), text(p.name)),
            self._COL_NOTES: lambda p: (text(p.notes), text(p.brand), text(p.name)),
        }
        key_fn = key_map.get(self._sort_column, key_map[self._COL_BRAND])
        return sorted(paints, key=key_fn, reverse=self._sort_desc)

    def _paint_at_row(self, row: int):
        return self._paints[row] if 0 <= row < len(self._paints) else None

    def _on_double_click(self, index):
        paint = self._paint_at_row(index.row())
        if paint:
            self.edit_requested.emit(paint)

    def _on_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        paint = self._paint_at_row(row)
        if not paint:
            return
        menu = QMenu(self)
        act_edit = menu.addAction("✏  Edit")
        act_plus = menu.addAction("＋  Stock +1")
        act_minus = menu.addAction("−  Stock -1")
        menu.addSeparator()
        act_del  = menu.addAction("🗑  Delete")
        act_fav  = menu.addAction("☆  Toggle Favourite")
        action   = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == act_edit:
            self.edit_requested.emit(paint)
        elif action == act_plus:
            self.stock_adjusted.emit(paint, 1)
        elif action == act_minus:
            self.stock_adjusted.emit(paint, -1)
        elif action == act_del:
            self.delete_requested.emit(paint)
        elif action == act_fav:
            self.favourite_toggled.emit(paint)


# ── Stats Bar ─────────────────────────────────────────────────────────────────

class _StatsBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 4, 2, 0)
        self._label = QLabel()
        _label_style(self._label, "#606060", 11)
        self._layout.addWidget(self._label)
        self._layout.addStretch()

    def update_stats(self, all_paints: list, filtered: list):
        total    = len(all_paints)
        showing  = len(filtered)
        brands   = len({p.brand for p in all_paints})
        types    = len({p.paint_type for p in all_paints})
        low      = sum(1 for p in all_paints if p.quantity <= 1)
        out      = sum(1 for p in all_paints if p.quantity == 0)

        sep = "  ·  "
        parts = [
            f"{total} paints",
            f"{brands} brands",
            f"{types} types",
        ]
        if showing != total:
            parts.append(f"<span style='color:#c0c0c0;'>{showing} shown</span>")
        if out > 0:
            parts.append(f"<span style='color:#e05555;'>⚠ {out} out of stock</span>")
        elif low > 0:
            parts.append(f"<span style='color:#e08030;'>⚠ {low} low stock</span>")

        self._label.setText(
            f"<span style='color:#505050;'>{sep.join(parts)}</span>"
            .replace(f"{sep}<span", f"{sep.replace('  ·  ', '')}<span")
        )
        # Rebuild with actual sep between items
        pieces = sep.join(
            f"<span style='color:#505050;'>{p}</span>"
            if "<span" not in p else p
            for p in parts
        )
        self._label.setText(pieces)


# ── Overview Strip ────────────────────────────────────────────────────────────

class _OverviewStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, tuple[QLabel, QLabel]] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        for key, label, color in [
            ("total", "Collection", "#0078d4"),
            ("low", "Low Stock", "#e08030"),
            ("out", "Out", "#c62828"),
            ("fav", "Favourites", "#b794f4"),
        ]:
            card = QFrame()
            card.setObjectName("overviewCard")
            card.setStyleSheet(
                "QFrame#overviewCard { background-color: #171717;"
                " border: 1px solid #2d2d2d; border-radius: 8px; }"
            )
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(12, 9, 12, 9)
            card_lay.setSpacing(2)

            value = QLabel("0")
            _label_style(value, color, 20, bold=True)
            caption = QLabel(label)
            _label_style(caption, "#8c8c8c", 11)
            card_lay.addWidget(value)
            card_lay.addWidget(caption)
            layout.addWidget(card, 1)
            self._cards[key] = (value, caption)

    def update_counts(self, paints: list):
        total = len(paints)
        low = sum(1 for p in paints if p.quantity <= 1)
        out = sum(1 for p in paints if p.quantity == 0)
        fav = sum(1 for p in paints if p.is_favorite)
        values = {
            "total": str(total),
            "low": str(low),
            "out": str(out),
            "fav": str(fav),
        }
        for key, value in values.items():
            self._cards[key][0].setText(value)


# ── Intelligence Panel ────────────────────────────────────────────────────────

class _ColorIntelligencePanel(QFrame):
    color_filter_requested = Signal(str)
    export_shopping_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paints: list = []
        self._manual_shopping_items: list[dict] = []
        self._target = "#808080"
        self.setObjectName("intelPanel")
        self.setStyleSheet(
            "QFrame#intelPanel { background-color: #141414;"
            " border: 1px solid #292929; border-radius: 8px; }"
        )
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Collection Intelligence")
        _label_style(title, "#f0f0f0", 13, bold=True)
        subtitle = QLabel("Color matches, restock planning, and data checks")
        _label_style(subtitle, "#777777", 11)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box)
        top.addStretch()

        self._target_swatch = QFrame()
        self._target_swatch.setFixedSize(24, 24)
        top.addWidget(self._target_swatch)
        self._target_input = QLineEdit(self._target)
        self._target_input.setFixedWidth(86)
        self._target_input.textChanged.connect(self._on_target_text)
        top.addWidget(self._target_input)
        pick = QPushButton("Pick Color")
        pick.setObjectName("secondaryBtn")
        pick.clicked.connect(self._pick_color)
        top.addWidget(pick)
        apply = QPushButton("Find Similar")
        apply.setObjectName("primaryBtn")
        apply.clicked.connect(lambda: self.color_filter_requested.emit(self._target))
        top.addWidget(apply)
        root.addLayout(top)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("intelTabs")
        self._tabs.setStyleSheet(
            "QTabWidget#intelTabs::pane { border: 1px solid #2b2b2b; border-radius: 8px;"
            " top: -1px; background-color: #181818; }"
            "QTabWidget#intelTabs QTabBar::tab { min-width: 118px; padding: 8px 18px;"
            " margin-right: 4px; font-weight: bold; }"
        )
        self._matches = self._make_table(["Match", "Paint", "Confidence"])
        self._restock_tab = QWidget()
        restock_layout = QVBoxLayout(self._restock_tab)
        restock_layout.setContentsMargins(0, 0, 0, 0)
        restock_layout.setSpacing(8)
        restock_controls = QHBoxLayout()
        restock_label = QLabel("Restock rule")
        _label_style(restock_label, "#9a9a9a", 11, bold=True)
        self._restock_rule = QComboBox()
        self._restock_rule.addItem("Out of stock only", "out")
        self._restock_rule.addItem("Marked low-stock alerts", "notify_low")
        self._restock_rule.addItem("All paints at 1 or less", "all_low")
        _polish_combo(self._restock_rule, 210, 240)
        self._restock_rule.currentIndexChanged.connect(self._render_restock)
        self._restock_export = QPushButton("Export Restock CSV")
        self._restock_export.setObjectName("secondaryBtn")
        self._restock_export.clicked.connect(lambda: self.export_shopping_requested.emit(self._shopping_entries()))
        restock_controls.addWidget(restock_label)
        restock_controls.addWidget(self._restock_rule)
        restock_controls.addStretch()
        restock_controls.addWidget(self._restock_export)
        restock_layout.addLayout(restock_controls)

        picker_row = QHBoxLayout()
        picker_label = QLabel("Add from catalog")
        _label_style(picker_label, "#9a9a9a", 11, bold=True)
        self._shopping_source = QComboBox()
        self._shopping_source.currentIndexChanged.connect(self._populate_shopping_items)
        _polish_combo(self._shopping_source, 150, 190)
        self._shopping_item = QComboBox()
        _polish_combo(self._shopping_item, 260, 360)
        self._shopping_qty = QSpinBox()
        self._shopping_qty.setRange(1, 999)
        self._shopping_qty.setValue(1)
        self._shopping_qty.setFixedWidth(70)
        self._shopping_add = QPushButton("Add Selected")
        self._shopping_add.setObjectName("secondaryBtn")
        self._shopping_add.clicked.connect(self._add_selected_item)
        picker_row.addWidget(picker_label)
        picker_row.addWidget(self._shopping_source)
        picker_row.addWidget(self._shopping_item, 1)
        picker_row.addWidget(self._shopping_qty)
        picker_row.addWidget(self._shopping_add)
        restock_layout.addLayout(picker_row)

        manual_row = QHBoxLayout()
        manual_label = QLabel("Manual item")
        _label_style(manual_label, "#9a9a9a", 11, bold=True)
        self._manual_brand = QLineEdit()
        self._manual_brand.setPlaceholderText("Brand")
        self._manual_brand.setMinimumWidth(150)
        self._manual_name = QLineEdit()
        self._manual_name.setPlaceholderText("Paint, tool, or supply")
        self._manual_name.setMinimumWidth(220)
        self._manual_qty = QSpinBox()
        self._manual_qty.setRange(1, 999)
        self._manual_qty.setValue(1)
        self._manual_qty.setFixedWidth(70)
        self._manual_add = QPushButton("Add to List")
        self._manual_add.setObjectName("secondaryBtn")
        self._manual_add.clicked.connect(self._add_manual_item)
        self._manual_clear = QPushButton("Clear Manual")
        self._manual_clear.setObjectName("secondaryBtn")
        self._manual_clear.clicked.connect(self._clear_manual_items)
        manual_row.addWidget(manual_label)
        manual_row.addWidget(self._manual_brand)
        manual_row.addWidget(self._manual_name, 1)
        manual_row.addWidget(self._manual_qty)
        manual_row.addWidget(self._manual_add)
        manual_row.addWidget(self._manual_clear)
        restock_layout.addLayout(manual_row)

        self._restock = self._make_table(["Brand", "Paint", "Qty", "Reason", "Used In"])
        restock_layout.addWidget(self._restock)
        self._quality = self._make_table(["Issue", "Paints"])
        self._tabs.addTab(self._matches, "Matches")
        self._tabs.addTab(self._restock_tab, "Restock")
        self._tabs.addTab(self._quality, "Data")
        root.addWidget(self._tabs)
        self._update_target_swatch()

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setMinimumHeight(280)
        hdr = table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionsClickable(False)
        table.setStyleSheet(
            "QTableWidget { border: none; gridline-color: transparent; background-color: #1b1b1b; }"
            "QHeaderView::section { padding: 8px 10px; }"
            "QTableWidget::item { padding: 8px 10px; }"
        )
        return table

    def _autosize_table(self, table: QTableWidget, stretch_col: Optional[int] = None,
                        fixed: Optional[dict[int, int]] = None):
        hdr = table.horizontalHeader()
        for col in range(table.columnCount()):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        for col, width in (fixed or {}).items():
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            table.setColumnWidth(col, width)
        if table.columnCount() > 1:
            col = stretch_col if stretch_col is not None else table.columnCount() - 1
            hdr.setSectionResizeMode(col, QHeaderView.Stretch)

    def _swatch_cell(self, hex_color: str, label: str = "") -> QWidget:
        widget = QWidget()
        widget.setMinimumWidth(138)
        widget.setMinimumHeight(54)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignVCenter)
        swatch = _ColorDot(hex_color, 28)
        swatch.setToolTip(hex_color)
        layout.addWidget(swatch)
        if label:
            text = QLabel(label)
            text.setMinimumWidth(72)
            _label_style(text, "#d0d0d0", 11)
            layout.addWidget(text)
        layout.addStretch()
        return widget

    def update_data(self, paints: list, usage: dict[int, list[str]], shopping_sources: Optional[dict[str, list[dict]]] = None):
        self._paints = list(paints)
        self._usage = usage
        self._shopping_sources = shopping_sources or {"Paints": []}
        self._populate_shopping_sources()
        self._render_matches()
        self._render_restock()
        self._render_quality()

    def _populate_shopping_sources(self):
        current = self._shopping_source.currentText() if hasattr(self, "_shopping_source") else ""
        self._shopping_source.blockSignals(True)
        self._shopping_source.clear()
        for label, items in self._shopping_sources.items():
            if items:
                self._shopping_source.addItem(label, label)
        idx = self._shopping_source.findText(current)
        self._shopping_source.setCurrentIndex(idx if idx >= 0 else 0)
        self._shopping_source.blockSignals(False)
        self._populate_shopping_items()

    def _populate_shopping_items(self):
        if not hasattr(self, "_shopping_item"):
            return
        source = self._shopping_source.currentData()
        current = self._shopping_item.currentText()
        self._shopping_item.blockSignals(True)
        self._shopping_item.clear()
        for item in self._shopping_sources.get(source, []):
            self._shopping_item.addItem(item["label"], item)
        idx = self._shopping_item.findText(current)
        if idx >= 0:
            self._shopping_item.setCurrentIndex(idx)
        self._shopping_item.blockSignals(False)
        _fit_combo_to_items(self._shopping_item, 260, 420)

    def set_target(self, hex_color: str):
        if _valid_hex(hex_color):
            self._target = hex_color.upper()
            self._target_input.blockSignals(True)
            self._target_input.setText(self._target)
            self._target_input.blockSignals(False)
            self._update_target_swatch()
            self._render_matches()

    def _on_target_text(self, text: str):
        if _valid_hex(text):
            self._target = text.upper()
            self._target_input.setStyleSheet("")
            self._update_target_swatch()
            self._render_matches()
        else:
            self._target_input.setStyleSheet("border: 1px solid #e05555;")

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._target), self)
        if color.isValid():
            self.set_target(color.name().upper())

    def _update_target_swatch(self):
        self._target_swatch.setStyleSheet(
            f"background-color: {self._target}; border: 1px solid #555; border-radius: 12px;"
        )

    def _render_matches(self):
        rows = sorted(
            ((p, _color_distance(self._target, p.color)) for p in self._paints),
            key=lambda item: item[1],
        )[:8]
        self._matches.setRowCount(0)
        for p, distance in rows:
            row = self._matches.rowCount()
            self._matches.insertRow(row)
            self._matches.setRowHeight(row, 58)
            self._matches.setCellWidget(row, 0, self._swatch_cell(p.color, p.color))
            self._matches.setItem(row, 1, QTableWidgetItem(f"{p.brand} — {p.name}"))
            self._matches.setItem(row, 2, QTableWidgetItem(f"{_match_confidence(distance)}%"))
        self._autosize_table(self._matches, stretch_col=1, fixed={0: 154, 2: 150})

    def _restock_paints(self) -> list:
        rule = self._restock_rule.currentData() if hasattr(self, "_restock_rule") else "out"
        if rule == "all_low":
            return [p for p in self._paints if p.quantity <= 1]
        if rule == "notify_low":
            return [
                p for p in self._paints
                if p.quantity <= 1 and getattr(p, "notify_low_stock", True)
            ]
        return [p for p in self._paints if p.quantity <= 0]

    def _shopping_entries(self) -> list[dict]:
        entries = []
        for p in self._restock_paints():
            entries.append({
                "brand": p.brand,
                "paint": p.name,
                "quantity": p.quantity,
                "reason": self._restock_reason(p),
                "used_in": ", ".join(self._usage.get(p.id, [])),
                "source": "catalog",
            })
        entries.extend(self._manual_shopping_items)
        return entries

    def _restock_reason(self, paint) -> str:
        if paint.quantity <= 0:
            return "Out of stock"
        if getattr(paint, "notify_low_stock", True):
            return "Low-stock alert enabled"
        return "Quantity is 1 or less"

    def _render_restock(self):
        rows = sorted(self._shopping_entries(), key=lambda item: (item["brand"].lower(), item["paint"].lower()))
        self._restock.setRowCount(0)
        for item in rows:
            row = self._restock.rowCount()
            self._restock.insertRow(row)
            self._restock.setItem(row, 0, QTableWidgetItem(item["brand"]))
            self._restock.setItem(row, 1, QTableWidgetItem(item["paint"]))
            raw_qty = item["quantity"]
            qty = QTableWidgetItem("Out" if item.get("source") == "catalog" and raw_qty <= 0 else str(raw_qty))
            if item.get("source") == "manual":
                qty.setForeground(QColor("#c0c0c0"))
            else:
                qty.setForeground(QColor("#e05555" if raw_qty <= 0 else "#e08030"))
            self._restock.setItem(row, 2, qty)
            self._restock.setItem(row, 3, QTableWidgetItem(item["reason"]))
            self._restock.setItem(row, 4, QTableWidgetItem(item["used_in"] or "—"))
        self._autosize_table(self._restock)

    def _add_manual_item(self):
        brand = self._manual_brand.text().strip()
        name = self._manual_name.text().strip()
        if not name:
            self._manual_name.setStyleSheet("border: 1px solid #e05555;")
            return
        self._manual_name.setStyleSheet("")
        self._manual_shopping_items.append({
            "brand": brand or "Manual",
            "paint": name,
            "quantity": self._manual_qty.value(),
            "reason": "Manually added",
            "used_in": "",
            "source": "manual",
        })
        self._manual_brand.clear()
        self._manual_name.clear()
        self._manual_qty.setValue(1)
        self._render_restock()

    def _add_selected_item(self):
        item = self._shopping_item.currentData()
        if not item:
            return
        self._manual_shopping_items.append({
            "brand": item.get("brand") or item.get("category", "Catalog"),
            "paint": item["name"],
            "quantity": self._shopping_qty.value(),
            "reason": item.get("reason", "Selected from catalog"),
            "used_in": "",
            "source": "selected",
        })
        self._shopping_qty.setValue(1)
        self._render_restock()

    def _clear_manual_items(self):
        self._manual_shopping_items = []
        self._render_restock()

    def _render_quality(self):
        issues: list[tuple[str, str]] = []
        seen = {}
        for p in self._paints:
            key = (p.brand.strip().lower(), p.name.strip().lower())
            seen.setdefault(key, []).append(p)
        for paints in seen.values():
            if len(paints) > 1:
                issues.append(("Duplicate name", ", ".join(f"{p.brand} — {p.name}" for p in paints)))

        near = []
        for i, a in enumerate(self._paints):
            for b in self._paints[i + 1:]:
                if _color_distance(a.color, b.color) <= 12:
                    near.append(f"{a.brand} {a.name} / {b.brand} {b.name}")
        if near:
            issues.append(("Near-duplicate colors", "; ".join(near[:4])))

        missing_level = [f"{p.brand} {p.name}" for p in self._paints if not p.level]
        if missing_level:
            issues.append(("Missing fill level", ", ".join(missing_level[:8])))

        self._quality.setRowCount(0)
        for issue, detail in issues or [("No issues found", "Collection data looks clean.")]:
            row = self._quality.rowCount()
            self._quality.insertRow(row)
            self._quality.setItem(row, 0, QTableWidgetItem(issue))
            self._quality.setItem(row, 1, QTableWidgetItem(detail))
        self._autosize_table(self._quality)


# ── Edit Paint Dialog ─────────────────────────────────────────────────────────

class _EditPaintDialog(QDialog):
    def __init__(self, paint, paint_types: Optional[list[str]] = None, parent=None):
        super().__init__(parent)
        self._paint = paint
        self._paint_types = paint_types or []
        self._color = paint.color if _valid_hex(paint.color) else "#808080"
        self.setWindowTitle(f"Edit — {paint.brand} {paint.name}")
        self.setMinimumWidth(500)
        self.setSizeGripEnabled(True)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        form = QGridLayout()
        form.setSpacing(8)
        form.setColumnStretch(1, 1)
        form.setColumnMinimumWidth(0, 80)

        def lbl(text):
            l = QLabel(text)
            _label_style(l, "#c0c0c0", 12)
            return l

        self._brand = QLineEdit(self._paint.brand)
        self._name  = QLineEdit(self._paint.name)

        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)
        self._type_combo.setInsertPolicy(QComboBox.NoInsert)
        _polish_combo(self._type_combo, 160, 190)
        seen_types = set()
        for t in list(_ALL_TYPES) + list(self._paint_types):
            text = (t or "").strip()
            key = text.lower()
            if text and key not in seen_types:
                self._type_combo.addItem(text)
                seen_types.add(key)
        idx = self._type_combo.findText(self._paint.paint_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        else:
            self._type_combo.setCurrentText(self._paint.paint_type)
        _fit_combo_to_items(self._type_combo, 160, 260)

        # Color row
        color_w = QWidget()
        color_row = QHBoxLayout(color_w)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(8)

        self._color_swatch = QFrame()
        self._color_swatch.setFixedSize(58, 58)
        self._color_swatch.setCursor(Qt.PointingHandCursor)
        self._color_swatch.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #555; border-radius: 29px;"
        )
        self._color_swatch.mousePressEvent = lambda _: self._pick_color()

        self._color_pick_btn = QPushButton("Pick…")
        self._color_pick_btn.setObjectName("secondaryBtn")
        self._color_pick_btn.setCursor(Qt.PointingHandCursor)
        self._color_pick_btn.clicked.connect(self._pick_color)

        self._hex_input = QLineEdit(self._color)
        self._hex_input.setFixedWidth(90)
        self._hex_input.setPlaceholderText("#RRGGBB")
        self._hex_input.textChanged.connect(self._on_hex_changed)

        color_row.addWidget(self._color_swatch)
        color_row.addWidget(self._color_pick_btn)
        color_row.addWidget(self._hex_input)
        color_row.addStretch()

        qty_w = QWidget()
        qty_row = QHBoxLayout(qty_w)
        qty_row.setContentsMargins(0, 0, 0, 0)
        qty_row.setSpacing(6)

        self._qty_minus = QPushButton("−")
        self._qty_minus.setObjectName("secondaryBtn")
        self._qty_minus.setFixedWidth(30)
        self._qty_minus.setCursor(Qt.PointingHandCursor)
        self._qty_minus.clicked.connect(lambda: self._qty.setValue(max(0, self._qty.value() - 1)))

        self._qty = QSpinBox()
        self._qty.setRange(0, 999)
        self._qty.setValue(self._paint.quantity)
        self._qty.setFixedWidth(80)

        self._qty_plus = QPushButton("＋")
        self._qty_plus.setObjectName("secondaryBtn")
        self._qty_plus.setFixedWidth(30)
        self._qty_plus.setCursor(Qt.PointingHandCursor)
        self._qty_plus.clicked.connect(lambda: self._qty.setValue(min(999, self._qty.value() + 1)))

        qty_row.addWidget(self._qty_minus)
        qty_row.addWidget(self._qty)
        qty_row.addWidget(self._qty_plus)
        qty_row.addStretch()

        self._level_combo = QComboBox()
        self._level_combo.addItem("—")
        for l in _ALL_LEVELS:
            self._level_combo.addItem(l)
        _polish_combo(self._level_combo, 150, 180)
        if self._paint.level:
            idx2 = self._level_combo.findText(self._paint.level)
            if idx2 >= 0:
                self._level_combo.setCurrentIndex(idx2)

        self._notes = QTextEdit()
        self._notes.setPlainText(self._paint.notes or "")
        self._notes.setFixedHeight(70)

        self._fav_check    = QCheckBox("Mark as favourite")
        self._notify_check = QCheckBox("Notify when low stock")
        self._fav_check.setChecked(self._paint.is_favorite)
        self._notify_check.setChecked(self._paint.notify_low_stock)

        for r, (label, widget) in enumerate([
            ("Brand",    self._brand),
            ("Name",     self._name),
            ("Type",     self._type_combo),
            ("Colour",   color_w),
            ("Quantity", qty_w),
            ("Level",    self._level_combo),
            ("Notes",    self._notes),
        ]):
            form.addWidget(lbl(label), r, 0)
            form.addWidget(widget, r, 1)

        layout.addLayout(form)

        checks = QHBoxLayout()
        checks.addWidget(self._fav_check)
        checks.addWidget(self._notify_check)
        checks.addStretch()
        layout.addLayout(checks)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._color), self)
        if color.isValid():
            self._color = color.name().upper()
            self._hex_input.blockSignals(True)
            self._hex_input.setText(self._color)
            self._hex_input.blockSignals(False)
            self._color_swatch.setStyleSheet(
                f"background-color: {self._color}; border: 1px solid #555; border-radius: 29px;"
            )

    def _on_hex_changed(self, text: str):
        if _valid_hex(text):
            self._color = text.upper()
            self._color_swatch.setStyleSheet(
                f"background-color: {self._color}; border: 1px solid #555; border-radius: 29px;"
            )
            self._hex_input.setStyleSheet("")
        else:
            self._hex_input.setStyleSheet("border: 1px solid #e05555;")

    def get_values(self) -> dict:
        level = self._level_combo.currentText()
        return {
            "brand":            self._brand.text().strip(),
            "name":             self._name.text().strip(),
            "paint_type":       self._type_combo.currentText().strip(),
            "color":            self._color,
            "quantity":         self._qty.value(),
            "level":            level if level != "—" else None,
            "notes":            self._notes.toPlainText().strip(),
            "is_favorite":      self._fav_check.isChecked(),
            "notify_low_stock": self._notify_check.isChecked(),
        }


# ── Import Preview ────────────────────────────────────────────────────────────

class _ImportPreviewDialog(QDialog):
    def __init__(self, rows: list[dict], parent=None):
        super().__init__(parent)
        self._rows = rows
        self.setWindowTitle("Preview Paint Import")
        self.setMinimumSize(760, 420)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        ready = sum(1 for r in self._rows if r["status"] == "ready")
        skipped = len(self._rows) - ready
        summary = QLabel(f"{ready} ready to import · {skipped} will be skipped")
        _label_style(summary, "#f0f0f0", 13, bold=True)
        layout.addWidget(summary)

        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Status", "Brand", "Name", "Type", "Color", "Reason"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)

        for row_data in self._rows:
            row = table.rowCount()
            table.insertRow(row)
            vals = [
                row_data["status"].title(),
                row_data["brand"],
                row_data["name"],
                row_data["paint_type"],
                row_data["color"],
                row_data["reason"],
            ]
            for col, value in enumerate(vals):
                item = QTableWidgetItem(str(value))
                if row_data["status"] != "ready":
                    item.setForeground(QColor("#e08030"))
                table.setItem(row, col, item)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Import Ready Rows")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ── Main Widget ───────────────────────────────────────────────────────────────

class PaintTrackerV2UI(QWidget):
    def __init__(self, service, context, parent=None):
        super().__init__(parent)
        self._svc = service
        self._ctx = context
        self._paints: list  = []
        self._filtered: list = []
        self._active_filter: dict = {}
        self._last_import_ids: list[int] = []
        self._usage_map: dict[int, list[str]] = {}
        self._view_mode = "cards"
        self._build()
        QTimer.singleShot(0, self.refresh)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # ── Header row ───────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)

        title_block = QWidget()
        title_lay = QVBoxLayout(title_block)
        title_lay.setContentsMargins(0, 0, 0, 0)
        title_lay.setSpacing(1)
        title = QLabel("Paint Collection")
        title.setObjectName("pageTitle")
        _label_style(title, "#f0f0f0", 20, bold=True)
        subtitle = QLabel("Organize, restock, and compare your paints at a glance")
        _label_style(subtitle, "#707070", 11)
        title_lay.addWidget(title)
        title_lay.addWidget(subtitle)
        header.addWidget(title_block)
        header.addStretch()

        # View toggle
        self._cards_btn = QPushButton("▦  Cards")
        self._cards_btn.setObjectName("secondaryBtn")
        self._cards_btn.setCheckable(True)
        self._cards_btn.setChecked(True)
        self._cards_btn.setCursor(Qt.PointingHandCursor)
        self._cards_btn.setFixedHeight(28)
        self._cards_btn.clicked.connect(lambda: self._set_view_mode("cards"))

        self._table_btn = QPushButton("≡  Table")
        self._table_btn.setObjectName("secondaryBtn")
        self._table_btn.setCheckable(True)
        self._table_btn.setChecked(False)
        self._table_btn.setCursor(Qt.PointingHandCursor)
        self._table_btn.setFixedHeight(28)
        self._table_btn.clicked.connect(lambda: self._set_view_mode("table"))

        header.addWidget(self._cards_btn)
        header.addWidget(self._table_btn)
        header.addSpacing(6)

        self._sort_combo = QComboBox()
        self._sort_combo.setObjectName("sortCombo")
        self._sort_combo.addItem("Sort: Brand + Name", "brand_name")
        self._sort_combo.addItem("Sort: Quantity Low First", "quantity_asc")
        self._sort_combo.addItem("Sort: Quantity High First", "quantity_desc")
        self._sort_combo.addItem("Sort: Favourites First", "favourites")
        self._sort_combo.addItem("Sort: Type", "type")
        _polish_combo(self._sort_combo, 230, 260)
        self._sort_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self._sort_combo)

        self._group_combo = QComboBox()
        self._group_combo.setObjectName("groupCombo")
        self._group_combo.addItem("Group: None", "none")
        self._group_combo.addItem("Group: Brand", "brand")
        self._group_combo.addItem("Group: Type", "type")
        self._group_combo.addItem("Group: Stock", "stock")
        _polish_combo(self._group_combo, 150, 190)
        self._group_combo.currentIndexChanged.connect(self._update_views)
        header.addWidget(self._group_combo)

        self._import_btn = QPushButton("Import")
        self._import_btn.setObjectName("secondaryBtn")
        self._import_btn.setCursor(Qt.PointingHandCursor)
        self._import_btn.clicked.connect(self._import_csv)
        header.addWidget(self._import_btn)

        self._export_btn = QPushButton("Export")
        self._export_btn.setObjectName("secondaryBtn")
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.clicked.connect(self._export_csv)
        header.addWidget(self._export_btn)

        self._undo_import_btn = QPushButton("Undo Import")
        self._undo_import_btn.setObjectName("secondaryBtn")
        self._undo_import_btn.setCursor(Qt.PointingHandCursor)
        self._undo_import_btn.clicked.connect(self._undo_last_import)
        self._undo_import_btn.hide()
        header.addWidget(self._undo_import_btn)
        root.addLayout(header)

        self._main_tabs = QTabWidget()
        self._main_tabs.setObjectName("paintTrackerTabs")
        self._main_tabs.setStyleSheet(
            "QTabWidget#paintTrackerTabs::pane { border: 1px solid #2b2b2b; border-radius: 8px;"
            " top: -1px; }"
            "QTabWidget#paintTrackerTabs QTabBar::tab { min-width: 132px; padding: 8px 20px;"
            " margin-right: 4px; font-weight: bold; }"
        )
        root.addWidget(self._main_tabs, 1)

        collection_tab = QWidget()
        collection_lay = QVBoxLayout(collection_tab)
        collection_lay.setContentsMargins(0, 8, 0, 0)
        collection_lay.setSpacing(8)

        self._overview = _OverviewStrip()
        collection_lay.addWidget(self._overview)

        # ── Quick add bar ─────────────────────────────────────────────────────
        self._quick_add = _QuickAddBar()
        collection_lay.addWidget(self._quick_add)

        # ── Filter bar ────────────────────────────────────────────────────────
        self._filter_bar = _FilterBar()
        collection_lay.addWidget(self._filter_bar)

        # ── Preset chips ──────────────────────────────────────────────────────
        self._presets = _PresetChips()
        collection_lay.addWidget(self._presets)

        # ── Stacked view ──────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._card_grid   = _CardGrid()
        self._table_view  = _TableView()
        self._stack.addWidget(self._card_grid)    # index 0
        self._stack.addWidget(self._table_view)   # index 1
        collection_lay.addWidget(self._stack, 1)

        # ── Stats bar ─────────────────────────────────────────────────────────
        self._stats_bar = _StatsBar()
        collection_lay.addWidget(self._stats_bar)

        intelligence_tab = QWidget()
        intelligence_lay = QVBoxLayout(intelligence_tab)
        intelligence_lay.setContentsMargins(0, 8, 0, 0)
        intelligence_lay.setSpacing(8)
        self._intel_panel = _ColorIntelligencePanel()
        intelligence_lay.addWidget(self._intel_panel, 1)

        self._main_tabs.addTab(collection_tab, "Collection")
        self._main_tabs.addTab(intelligence_tab, "Intelligence")

        # ── Toast label ──────────────────────────────────────────────────────
        self._toast_label = QLabel(self)
        self._toast_label.setMargin(10)
        _label_style(self._toast_label, "#f0f0f0", 13, bg="#181818")
        self._toast_label.setAlignment(Qt.AlignCenter)
        self._toast_label.hide()
        self._toast_timer = QTimer()
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_label.hide)

        self._connect_signals()
        self._install_shortcuts()

    def _connect_signals(self):
        self._quick_add.submitted.connect(self._on_quick_add)
        self._filter_bar.filter_changed.connect(self._on_filter_changed)
        self._presets.preset_changed.connect(self._on_preset_changed)

        self._card_grid.edit_requested.connect(self._on_edit)
        self._card_grid.delete_requested.connect(self._on_delete)
        self._card_grid.stock_adjusted.connect(self._on_stock_adjust)
        self._card_grid.similar_requested.connect(self._on_similar)
        self._card_grid.favourite_toggled.connect(self._on_toggle_fav)

        self._table_view.edit_requested.connect(self._on_edit)
        self._table_view.delete_requested.connect(self._on_delete)
        self._table_view.stock_adjusted.connect(self._on_stock_adjust)
        self._table_view.favourite_toggled.connect(self._on_toggle_fav)

        self._intel_panel.color_filter_requested.connect(self._on_similar)
        self._intel_panel.export_shopping_requested.connect(self._export_shopping_list)

    def _install_shortcuts(self):
        self._sc_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self._sc_search.activated.connect(self._filter_bar.focus_search)
        self._sc_add = QShortcut(QKeySequence("Ctrl+N"), self)
        self._sc_add.activated.connect(self._quick_add.expand)
        self._sc_escape = QShortcut(QKeySequence("Esc"), self)
        self._sc_escape.activated.connect(self._clear_active_filters)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        try:
            self._paints = self._svc.get_all_paints()
            self._usage_map = self._build_usage_map(self._paints)
            brands = sorted({p.brand for p in self._paints if p.brand}, key=str.lower)
            types = sorted({p.paint_type for p in self._paints if p.paint_type}, key=str.lower)
            self._filter_bar.update_brands(brands)
            self._filter_bar.update_types(types)
            self._quick_add.update_options(brands, types)
            self._filtered = self._apply_filter(self._paints, self._active_filter)
            self._update_views()
        except Exception as e:
            print(f"[PAINT V2 UI] refresh: {e}")

    def _update_views(self):
        empty_message = (
            "No paints in your collection yet.\nOpen Add Paint to start building your library."
            if not self._paints
            else "No paints match these filters.\nTry broadening the search or reset the active filters."
        )
        group_by = self._group_combo.currentData() if hasattr(self, "_group_combo") else "none"
        self._card_grid.load(self._filtered, empty_message=empty_message, group_by=group_by)
        self._table_view.load(self._filtered)
        self._overview.update_counts(self._paints)
        self._stats_bar.update_stats(self._paints, self._filtered)
        self._intel_panel.update_data(self._paints, self._usage_map, self._build_shopping_sources(self._paints))

    def _build_usage_map(self, paints: list) -> dict[int, list[str]]:
        usage: dict[int, list[str]] = {p.id: [] for p in paints if getattr(p, "id", None) is not None}
        try:
            services = getattr(self._ctx, "services", None)
            scheme_svc = None
            if services:
                if hasattr(services, "try_get"):
                    scheme_svc = services.try_get("scheme_service")
                elif hasattr(services, "get"):
                    scheme_svc = services.get("scheme_service")
            if scheme_svc:
                for scheme in scheme_svc.get_all_schemes():
                    for step in scheme_svc.get_steps(scheme.id):
                        paint_id = getattr(step, "paint_id", None)
                        if paint_id in usage:
                            name = getattr(scheme, "name", "Scheme")
                            if name not in usage[paint_id]:
                                usage[paint_id].append(name)
        except Exception as e:
            print(f"[PAINT V2 UI] usage map: {e}")
        return usage

    def _service(self, name: str):
        services = getattr(self._ctx, "services", None)
        if not services:
            return None
        try:
            if hasattr(services, "try_get"):
                return services.try_get(name)
            if hasattr(services, "get"):
                return services.get(name)
        except Exception:
            return None
        return None

    def _build_shopping_sources(self, paints: list) -> dict[str, list[dict]]:
        sources: dict[str, list[dict]] = {}
        sources["Paints"] = [
            {
                "label": f"{p.brand} — {p.name}",
                "brand": p.brand,
                "name": p.name,
                "category": "Paints",
                "reason": "Selected from Paints",
            }
            for p in sorted(paints, key=lambda p: (p.brand.lower(), p.name.lower()))
        ]

        tool_svc = self._service("tool_service")
        if tool_svc:
            try:
                tools = sorted(tool_svc.get_all_tools(), key=lambda t: ((getattr(t, "brand", "") or "").lower(), t.name.lower()))
                sources["Tools"] = [
                    {
                        "label": f"{getattr(t, 'brand', '') + ' — ' if getattr(t, 'brand', '') else ''}{t.name}",
                        "brand": getattr(t, "brand", "") or "Tool",
                        "name": t.name,
                        "category": "Tools",
                        "reason": f"Selected from Tools · {getattr(t, 'tool_type', 'Tool')}",
                    }
                    for t in tools
                ]
            except Exception as e:
                print(f"[PAINT V2 UI] shopping tools: {e}")

        material_svc = self._service("material_service")
        if material_svc:
            try:
                materials = sorted(material_svc.get_all_materials(), key=lambda m: ((getattr(m, "brand", "") or "").lower(), m.name.lower()))
                sources["Materials"] = [
                    {
                        "label": f"{getattr(m, 'brand', '') + ' — ' if getattr(m, 'brand', '') else ''}{m.name}",
                        "brand": getattr(m, "brand", "") or "Material",
                        "name": m.name,
                        "category": "Materials",
                        "reason": f"Selected from Materials · {getattr(m, 'material_type', 'Material')}",
                    }
                    for m in materials
                ]
            except Exception as e:
                print(f"[PAINT V2 UI] shopping materials: {e}")

        model_svc = self._service("model_service")
        if model_svc:
            try:
                models = sorted(model_svc.get_all_models(), key=lambda m: ((getattr(m, "faction", "") or "").lower(), m.name.lower()))
                sources["Models"] = [
                    {
                        "label": f"{getattr(m, 'faction', '') + ' — ' if getattr(m, 'faction', '') else ''}{m.name}",
                        "brand": getattr(m, "faction", "") or getattr(m, "game_system", "") or "Model",
                        "name": m.name,
                        "category": "Models",
                        "reason": f"Selected from Models · {getattr(m, 'model_type', 'Model')}",
                    }
                    for m in models
                ]
            except Exception as e:
                print(f"[PAINT V2 UI] shopping models: {e}")

        return sources

    # ── Filter ────────────────────────────────────────────────────────────────

    def _apply_filter(self, paints: list, f: dict) -> list:
        if not f:
            return self._sort_paints(list(paints))

        search      = (f.get("search") or "").lower()
        brand       = (f.get("brand") or "").lower()
        ptype       = (f.get("type") or "").lower()
        level       = f.get("level") or ""
        color_hex   = f.get("color_hex") or ""
        fav_only    = f.get("favorites_only", False)
        notify_only = f.get("notify_only", False)
        stock       = f.get("stock") or ""

        result = []
        for p in paints:
            if search and search not in f"{p.brand} {p.name} {p.paint_type}".lower():
                continue
            if brand and brand not in p.brand.lower():
                continue
            if ptype and ptype != p.paint_type.lower():
                continue
            if level and level != (p.level or ""):
                continue
            if fav_only and not p.is_favorite:
                continue
            if notify_only and not getattr(p, "notify_low_stock", True):
                continue
            if stock == "low" and p.quantity > 1:
                continue
            if stock == "out" and p.quantity != 0:
                continue
            result.append(p)

        if color_hex and _valid_hex(color_hex):
            try:
                result = self._svc.find_paints_by_color(color_hex, paints=result)
            except Exception as e:
                print(f"[PAINT V2 UI] color filter: {e}")

        return self._sort_paints(result)

    def _sort_paints(self, paints: list) -> list:
        mode = self._sort_combo.currentData() if hasattr(self, "_sort_combo") else "brand_name"
        if mode == "quantity_asc":
            return sorted(paints, key=lambda p: (p.quantity, p.brand.lower(), p.name.lower()))
        if mode == "quantity_desc":
            return sorted(paints, key=lambda p: (-p.quantity, p.brand.lower(), p.name.lower()))
        if mode == "favourites":
            return sorted(paints, key=lambda p: (not p.is_favorite, p.brand.lower(), p.name.lower()))
        if mode == "type":
            return sorted(paints, key=lambda p: (p.paint_type.lower(), p.brand.lower(), p.name.lower()))
        return sorted(paints, key=lambda p: (p.brand.lower(), p.name.lower()))

    # ── Import / Export ──────────────────────────────────────────────────────

    def _write_paints_csv(self, path: str, paints: list):
        fields = [
            "brand", "name", "paint_type", "color", "quantity", "level",
            "notes", "is_favorite", "notify_low_stock",
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for p in paints:
                writer.writerow({
                    "brand": p.brand,
                    "name": p.name,
                    "paint_type": p.paint_type,
                    "color": p.color,
                    "quantity": p.quantity,
                    "level": p.level or "",
                    "notes": p.notes or "",
                    "is_favorite": int(bool(p.is_favorite)),
                    "notify_low_stock": int(bool(getattr(p, "notify_low_stock", True))),
                })

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Paint Collection", "paint_collection.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        try:
            self._write_paints_csv(path, self._paints)
            self._show_toast(f"Exported {len(self._paints)} paints")
        except Exception as e:
            self._show_toast(f"Export failed: {e}", 4000)

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Paint Collection", "", "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            rows = self._parse_import_rows(path)
            dlg = _ImportPreviewDialog(rows, self)
            if dlg.exec() != QDialog.Accepted:
                return
            backup_path = self._backup_before_import(path)
            added_ids = []
            skipped = 0
            for row in rows:
                if row["status"] != "ready":
                    skipped += 1
                    continue
                try:
                    p = self._svc.add_paint(
                        brand=row["brand"], name=row["name"], paint_type=row["paint_type"],
                        color=row["color"], quantity=row["quantity"], level=row["level"],
                        notes=row["notes"], is_favorite=row["is_favorite"],
                        notify_low_stock=row["notify_low_stock"],
                    )
                    if getattr(p, "id", None) is not None:
                        added_ids.append(p.id)
                except Exception:
                    skipped += 1
            added = len(added_ids)
            self._last_import_ids = added_ids
            self._undo_import_btn.setVisible(bool(added_ids))
            self._ctx.event_bus.emit("paint_imported", {"count": added, "_silent": True})
            self.refresh()
            suffix = f", {skipped} skipped" if skipped else ""
            self._show_toast(f"Imported {added} paints{suffix}. Backup saved: {os.path.basename(backup_path)}", 5000)
        except Exception as e:
            self._show_toast(f"Import failed: {e}", 4000)

    def _parse_import_rows(self, path: str) -> list[dict]:
        existing = {(p.brand.lower(), p.name.lower()) for p in self._paints}
        seen_in_file = set()
        rows = []
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            for raw in csv.DictReader(f):
                brand = (raw.get("brand") or raw.get("Brand") or "").strip()
                name = (raw.get("name") or raw.get("Name") or "").strip()
                paint_type = (raw.get("paint_type") or raw.get("type") or raw.get("Type") or "").strip()
                color = (raw.get("color") or raw.get("Color") or "#808080").strip().upper()
                qty_raw = str(raw.get("quantity") or raw.get("qty") or "1").strip()
                try:
                    quantity = max(0, int(qty_raw or 1))
                except Exception:
                    quantity = 1
                level = (raw.get("level") or "").strip() or None
                notes = raw.get("notes") or ""
                fav = self._csv_bool(raw.get("is_favorite") or raw.get("favorite"))
                notify = self._csv_bool(raw.get("notify_low_stock"), default=True)
                reason = ""
                status = "ready"
                key = (brand.lower(), name.lower())
                if not brand or not name or not paint_type:
                    status, reason = "skip", "Missing brand, name, or type"
                elif key in existing:
                    status, reason = "skip", "Already in collection"
                elif key in seen_in_file:
                    status, reason = "skip", "Duplicate inside import file"
                elif not _valid_hex(color):
                    color, reason = "#808080", "Invalid color replaced with neutral"
                if level not in _ALL_LEVELS:
                    level = None
                seen_in_file.add(key)
                rows.append({
                    "status": status, "reason": reason, "brand": brand, "name": name,
                    "paint_type": paint_type, "color": color, "quantity": quantity,
                    "level": level, "notes": notes, "is_favorite": fav,
                    "notify_low_stock": notify,
                })
        return rows

    def _backup_before_import(self, import_path: str) -> str:
        folder = os.path.dirname(import_path) or os.getcwd()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(folder, f"paint_collection_backup_before_import_{stamp}.csv")
        self._write_paints_csv(backup_path, self._paints)
        return backup_path

    def _undo_last_import(self):
        if not self._last_import_ids:
            return
        reply = QMessageBox.question(
            self, "Undo Import",
            f"Remove the {len(self._last_import_ids)} paints added by the last import?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        removed = 0
        for paint_id in list(self._last_import_ids):
            try:
                if self._svc.remove_paint(paint_id):
                    removed += 1
            except Exception:
                pass
        self._last_import_ids = []
        self._undo_import_btn.hide()
        self.refresh()
        self._show_toast(f"Undid import: removed {removed} paints", 4000)

    def _export_shopping_list(self, entries: list):
        if not entries:
            self._show_toast("No restock or manual shopping items to export")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Shopping List", "paint_shopping_list.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["brand", "paint", "quantity", "reason", "used_in"])
                writer.writeheader()
                for item in sorted(entries, key=lambda item: (item["brand"].lower(), item["paint"].lower())):
                    writer.writerow({
                        "brand": item["brand"],
                        "paint": item["paint"],
                        "quantity": item["quantity"],
                        "reason": item["reason"],
                        "used_in": item["used_in"],
                    })
            self._show_toast(f"Exported {len(entries)} shopping items")
        except Exception as e:
            self._show_toast(f"Shopping export failed: {e}", 4000)

    @staticmethod
    def _csv_bool(value, default: bool = False) -> bool:
        if value is None or value == "":
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "favorite", "favourite"}

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_quick_add(self, data: dict):
        try:
            paint = self._svc.add_paint(
                brand=data["brand"], name=data["name"],
                paint_type=data["paint_type"], color=data["color"],
                quantity=data.get("quantity", 1), level=data.get("level"),
                notes=data.get("notes", ""), is_favorite=data.get("is_favorite", False),
                notify_low_stock=data.get("notify_low_stock", True),
            )
            self._ctx.event_bus.emit("paint_added", {"id": paint.id})
            self.refresh()
            self._show_toast(f"Added {paint.brand} — {paint.name}")
        except Exception as e:
            self._show_toast(f"Error: {e}")

    def _on_edit(self, paint):
        try:
            paint_types = sorted({p.paint_type for p in self._paints if p.paint_type}, key=str.lower)
            dlg = _EditPaintDialog(paint, paint_types, self)
            if dlg.exec() == QDialog.Accepted:
                vals = dlg.get_values()
                existing = self._svc.get_paint(paint.id)
                if not existing:
                    return
                self._svc.update_paint(
                    paint.id,
                    brand=vals.get("brand", existing.brand),
                    name=vals.get("name", existing.name),
                    paint_type=vals.get("paint_type", existing.paint_type),
                    color=vals.get("color", existing.color),
                    quantity=vals.get("quantity", existing.quantity),
                    level=vals.get("level", existing.level),
                    notes=vals.get("notes", existing.notes or ""),
                    is_favorite=vals.get("is_favorite", existing.is_favorite),
                    notify_low_stock=vals.get("notify_low_stock", existing.notify_low_stock),
                )
                self._ctx.event_bus.emit("paint_updated", {"id": paint.id})
                self.refresh()
        except Exception as e:
            self._show_toast(f"Error: {e}")

    def _on_delete(self, paint):
        reply = QMessageBox.question(
            self, "Delete Paint",
            f"Delete {paint.brand} — {paint.name}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                self._svc.remove_paint(paint.id)
                self._ctx.event_bus.emit("paint_removed", {"id": paint.id})
                self.refresh()
            except Exception as e:
                self._show_toast(f"Error: {e}")

    def _on_stock_adjust(self, paint, delta: int):
        try:
            existing = self._svc.get_paint(paint.id)
            if not existing:
                return
            new_qty = max(0, existing.quantity + delta)
            self._svc.update_paint(
                paint.id,
                brand=existing.brand, name=existing.name,
                paint_type=existing.paint_type, color=existing.color,
                quantity=new_qty, level=existing.level,
                notes=existing.notes or "", is_favorite=existing.is_favorite,
                notify_low_stock=existing.notify_low_stock,
            )
            self._ctx.event_bus.emit("paint_updated", {"id": paint.id, "_silent": True})
            self.refresh()
            self._show_toast(f"{existing.name} stock updated — {new_qty} on hand")
        except Exception as e:
            self._show_toast(f"Error: {e}")

    def _on_similar(self, hex_color: str):
        self._intel_panel.set_target(hex_color)
        self._active_filter = dict(self._active_filter)
        self._active_filter["color_hex"] = hex_color
        self._filter_bar.set_color(hex_color)
        self._presets.set_active("all")
        self._filtered = self._apply_filter(self._paints, self._active_filter)
        self._update_views()

    def _on_toggle_fav(self, paint):
        try:
            existing = self._svc.get_paint(paint.id)
            if not existing:
                return
            self._svc.update_paint(
                paint.id,
                brand=existing.brand, name=existing.name,
                paint_type=existing.paint_type, color=existing.color,
                quantity=existing.quantity, level=existing.level,
                notes=existing.notes or "", is_favorite=not existing.is_favorite,
                notify_low_stock=existing.notify_low_stock,
            )
            self._ctx.event_bus.emit("paint_updated", {"id": paint.id, "_silent": True})
            self.refresh()
        except Exception as e:
            print(f"[PAINT V2 UI] toggle fav: {e}")

    def _on_filter_changed(self, state: dict):
        self._active_filter = state
        self._presets.set_active("all")   # visual only — no signal emitted
        self.refresh()

    def _clear_active_filters(self):
        self._active_filter = {}
        self._presets.set_active("all")
        self._filter_bar.reset()
        self.refresh()

    def _on_preset_changed(self, preset: str):
        self._active_filter = {}
        if preset == "low_stock":
            self._active_filter["stock"] = "low"
        elif preset == "out":
            self._active_filter["stock"] = "out"
        elif preset == "favourites":
            self._active_filter["favorites_only"] = True
        elif preset == "notify":
            self._active_filter["notify_only"] = True

        # Sync filter bar without triggering filter_changed
        self._filter_bar.blockSignals(True)
        self._filter_bar.reset()
        self._filter_bar.blockSignals(False)

        self._filtered = self._apply_filter(self._paints, self._active_filter)
        self._update_views()

    def apply_preset(self, preset: str):
        if preset == "add":
            self.handle_quick_create()
            return
        self._presets.set_active(preset)
        self._on_preset_changed(preset)

    def handle_quick_create(self) -> None:
        """Open the add-paint form ready for input.

        Called by the main window's Ctrl+N / 'Add Paint' command palette entry,
        and by the dashboard 'Add Paint' quick action.
        """
        # Ensure Collection tab is visible
        self._main_tabs.setCurrentIndex(0)
        # Expand (or re-focus) the quick-add bar
        self._quick_add.expand()

    # ── View mode ─────────────────────────────────────────────────────────────

    def _set_view_mode(self, mode: str):
        self._view_mode = mode
        is_cards = mode == "cards"
        self._stack.setCurrentIndex(0 if is_cards else 1)
        self._cards_btn.setChecked(is_cards)
        self._table_btn.setChecked(not is_cards)
        self._update_views()

    # ── Toast ─────────────────────────────────────────────────────────────────

    def _show_toast(self, message: str, ms: int = 2500):
        self._toast_label.setText(message)
        self._toast_label.adjustSize()
        x = (self.width() - self._toast_label.width()) // 2
        self._toast_label.move(x, 60)
        self._toast_label.show()
        self._toast_label.raise_()
        self._toast_timer.stop()
        self._toast_timer.start(ms)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._toast_label.isHidden():
            x = (self.width() - self._toast_label.width()) // 2
            self._toast_label.move(x, 60)
