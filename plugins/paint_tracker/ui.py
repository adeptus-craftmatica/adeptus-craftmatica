"""
Paint Tracker UI — premium inventory management for miniature hobbyists.
No inline colour overrides for structural chrome — everything flows from theme.qss.
Dynamic colour values (swatch backgrounds, low-stock tints) are necessarily inline.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

import csv

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QColor

from ui.animations import CountUpLabel, pulse_widget
from ui.toast import ToastManager
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QColorDialog, QMessageBox,
    QTabWidget, QDialog, QSpinBox, QTextEdit,
    QFrame, QSizePolicy,
    QFileDialog, QMenu, QApplication,
)

from .models import Paint, PaintFilter, PaintStatistics, VALID_LEVELS

# ── Column index constants ────────────────────────────────────────────────────
_C_ID     = 0   # hidden
_C_FAV    = 1   # ★  28 px fixed, click-to-toggle
_C_BRAND  = 2
_C_NAME   = 3
_C_TYPE   = 4
_C_QTY    = 5
_C_LEVEL  = 6
_C_COLOR  = 7   # 150 px fixed
_C_NOTES  = 8
_C_NOTIFY = 9   # 🔔  28 px fixed, click-to-toggle
_C_COUNT  = 10


# ── Layout micro-helpers ──────────────────────────────────────────────────────

def _vline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setFixedWidth(1)
    return f


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFixedHeight(1)
    return f


def _field(label_text: str, widget: QWidget) -> QVBoxLayout:
    """Stacked label + widget block used in horizontal form rows."""
    col = QVBoxLayout()
    col.setSpacing(3)
    lbl = QLabel(label_text)
    lbl.setObjectName("fieldLabel")
    col.addWidget(lbl)
    col.addWidget(widget)
    return col


# ─────────────────────────────────────────────────────────────────────────────

class PaintUI(QWidget):

    DEFAULT_TYPES = [
        "Base", "Layer", "Contrast", "Shade",
        "Dry", "Air", "Metallic", "Technical",
    ]

    SORT_COLUMN_TO_FIELD = {
        _C_ID:    "id",
        _C_FAV:   "is_favorite",
        _C_BRAND: "brand",
        _C_NAME:  "name",
        _C_TYPE:  "paint_type",
        _C_QTY:   "quantity",
        _C_LEVEL: "level",
        _C_COLOR: "color",
    }
    SORT_FIELD_TO_COLUMN = {v: k for k, v in SORT_COLUMN_TO_FIELD.items()}

    def __init__(self, context):
        super().__init__()
        self.context = context
        self._selected_color       = "#3A86FF"
        self._filter_color         = None
        self._show_favorites_only  = False
        self._active_notify_filter = False
        self._current_filter       = PaintFilter()
        self._build_ui()
        self._connect_signals()
        self._apply_saved_sort_indicator()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._restore_last_entry_defaults)

    # ── Top-level construction ────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        title = QLabel("Paint Tracker")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)
        self.tabs.addTab(self._build_collection_tab(), "Collection")
        self.tabs.addTab(self._build_statistics_tab(), "Statistics")

    # ── Collection tab ────────────────────────────────────────────────────

    def _build_collection_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        lay.addWidget(self._build_form())
        lay.addWidget(self._build_filter_bar())
        lay.addWidget(self._build_preset_chips())
        lay.addWidget(self._build_table(), stretch=1)
        lay.addWidget(self._build_footer())
        return w

    # ── Add / Edit form ───────────────────────────────────────────────────

    def _build_form(self) -> QFrame:
        """
        Add / Edit panel — styled card with:
          • section header showing current mode (ADD vs EDITING)
          • Row 1 — Brand / Name / Type / Qty / Level
          • thin divider
          • Row 2 — Colour picker / Notes / Action buttons
          • inline status strip
        """
        box = QFrame()
        box.setObjectName("formCard")

        outer = QVBoxLayout(box)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(0)

        # ── Section header ────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 10)
        hdr.setSpacing(8)

        self._form_title_lbl = QLabel("ADD PAINT")
        self._form_title_lbl.setObjectName("dashSectionLabel")
        hdr.addWidget(self._form_title_lbl)

        self._form_mode_lbl = QLabel("")
        self._form_mode_lbl.setObjectName("formModeLbl")
        self._form_mode_lbl.setVisible(False)
        hdr.addWidget(self._form_mode_lbl)
        hdr.addStretch()
        outer.addLayout(hdr)

        # ── Row 1: identity fields ────────────────────────────────────────
        r1 = QHBoxLayout()
        r1.setSpacing(12)
        r1.setContentsMargins(0, 0, 0, 10)

        self.brand_input = QComboBox()
        self.brand_input.setEditable(True)
        self.brand_input.setPlaceholderText("e.g. Citadel")
        self.brand_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        r1.addLayout(_field("Brand", self.brand_input), stretch=3)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Mephiston Red")
        r1.addLayout(_field("Name", self.name_input), stretch=4)

        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.addItems(self.DEFAULT_TYPES)
        r1.addLayout(_field("Type", self.type_combo), stretch=3)

        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(0)
        self.quantity_input.setMaximum(999)
        self.quantity_input.setValue(1)
        self.quantity_input.setFixedWidth(72)
        r1.addLayout(_field("Qty", self.quantity_input))

        self.level_combo = QComboBox()
        self.level_combo.addItem("")
        self.level_combo.addItems(VALID_LEVELS)
        self.level_combo.setCurrentText("Full")
        r1.addLayout(_field("Level", self.level_combo), stretch=2)

        outer.addLayout(r1)

        # ── Divider ───────────────────────────────────────────────────────
        outer.addWidget(_hline())

        # ── Row 2: colour + notes + buttons ──────────────────────────────
        r2 = QHBoxLayout()
        r2.setSpacing(14)
        r2.setContentsMargins(0, 10, 0, 0)

        # Colour picker block
        colour_col = QVBoxLayout()
        colour_col.setSpacing(4)
        _clbl = QLabel("Colour")
        _clbl.setObjectName("fieldLabel")
        colour_col.addWidget(_clbl)

        colour_controls = QHBoxLayout()
        colour_controls.setSpacing(6)
        colour_controls.setContentsMargins(0, 0, 0, 0)

        self.color_preview = QLabel()
        self.color_preview.setFixedSize(40, 34)
        self.color_preview.setObjectName("colorPreviewSwatch")
        self.color_preview.setToolTip("Current colour")
        self._update_color_preview()
        colour_controls.addWidget(self.color_preview)

        self.color_button = QPushButton("Pick…")
        self.color_button.setFixedHeight(34)
        self.color_button.setMinimumWidth(60)
        colour_controls.addWidget(self.color_button)

        self.color_hex_input = QLineEdit(self._selected_color)
        self.color_hex_input.setMaxLength(7)
        self.color_hex_input.setPlaceholderText("#RRGGBB")
        self.color_hex_input.setFixedWidth(86)
        self.color_hex_input.setFixedHeight(34)
        colour_controls.addWidget(self.color_hex_input)

        colour_col.addLayout(colour_controls)
        r2.addLayout(colour_col)

        r2.addWidget(_vline())

        # Notes
        notes_col = QVBoxLayout()
        notes_col.setSpacing(4)
        _nlbl = QLabel("Notes")
        _nlbl.setObjectName("fieldLabel")
        notes_col.addWidget(_nlbl)
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Optional notes about this paint…")
        self.notes_input.setFixedHeight(58)
        notes_col.addWidget(self.notes_input)
        r2.addLayout(notes_col, stretch=1)

        r2.addWidget(_vline())

        # Action buttons — bottom-aligned in the row
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        btn_col.setContentsMargins(4, 0, 0, 0)
        btn_col.addStretch()
        self.add_button = QPushButton("Add Paint")
        self.add_button.setProperty("class", "primary")
        self.add_button.setFixedHeight(36)
        self.add_button.setMinimumWidth(114)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setFixedHeight(30)
        self.clear_button.setMinimumWidth(114)
        btn_col.addWidget(self.add_button)
        btn_col.addWidget(self.clear_button)
        r2.addLayout(btn_col)

        outer.addLayout(r2)

        # Inline status label — auto-clears; never blocks with a modal dialog
        self._form_status_lbl = QLabel("")
        self._form_status_lbl.setObjectName("formStatusErr")
        self._form_status_lbl.setVisible(False)
        self._form_status_lbl.setContentsMargins(0, 6, 0, 0)
        outer.addWidget(self._form_status_lbl)

        return box

    # ── Filter bar ────────────────────────────────────────────────────────

    def _build_filter_bar(self) -> QFrame:
        """
        Professional control bar — logically grouped:
          [search] | [Brand] [Type] [Level] | [color swatch][Pick…][hex][✕] | [★] | [Reset]
        Redundant text labels removed; placeholder / combo first-items carry the meaning.
        """
        bar = QFrame()
        bar.setObjectName("filterBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(6)

        # Search — stretch to fill
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("⌕  Search brand, name or type…")
        self.search_input.setObjectName("filterSearch")
        lay.addWidget(self.search_input, stretch=2)

        lay.addWidget(_vline())

        # Dropdown filters — no prefixed labels; use first item as implicit label
        self.filter_brand_combo = QComboBox()
        self.filter_brand_combo.addItem("All Brands")
        self.filter_brand_combo.setMinimumWidth(110)
        self.filter_brand_combo.setToolTip("Filter by brand")
        lay.addWidget(self.filter_brand_combo)

        self.filter_type_combo = QComboBox()
        self.filter_type_combo.addItem("All Types")
        self.filter_type_combo.setMinimumWidth(100)
        self.filter_type_combo.setToolTip("Filter by type")
        lay.addWidget(self.filter_type_combo)

        self.filter_level_combo = QComboBox()
        self.filter_level_combo.addItem("All Levels")
        self.filter_level_combo.setMinimumWidth(100)
        self.filter_level_combo.setToolTip("Filter by stock level")
        lay.addWidget(self.filter_level_combo)

        lay.addWidget(_vline())

        # Colour filter — compact group
        self.filter_color_preview = QLabel()
        self.filter_color_preview.setFixedSize(24, 24)
        self.filter_color_preview.setToolTip("Active colour filter")
        self._update_filter_color_preview()
        lay.addWidget(self.filter_color_preview)

        self.filter_color_button = QPushButton("Colour…")
        self.filter_color_button.setFixedHeight(28)
        self.filter_color_button.setMinimumWidth(68)
        self.filter_color_button.setToolTip("Pick a colour to filter by hue")
        lay.addWidget(self.filter_color_button)

        self.filter_color_hex = QLineEdit()
        self.filter_color_hex.setMaxLength(7)
        self.filter_color_hex.setPlaceholderText("#hex")
        self.filter_color_hex.setFixedWidth(72)
        lay.addWidget(self.filter_color_hex)

        self.clear_color_filter_button = QPushButton("✕")
        self.clear_color_filter_button.setFixedSize(26, 26)
        self.clear_color_filter_button.setObjectName("clearColorBtn")
        self.clear_color_filter_button.setToolTip("Clear colour filter")
        lay.addWidget(self.clear_color_filter_button)

        lay.addWidget(_vline())

        # Favorites toggle — checkable, prominent
        self.favorites_filter_btn = QPushButton("★  Favorites")
        self.favorites_filter_btn.setCheckable(True)
        self.favorites_filter_btn.setObjectName("favoritesToggleBtn")
        self.favorites_filter_btn.setToolTip("Show only favourites")
        lay.addWidget(self.favorites_filter_btn)

        lay.addWidget(_vline())

        # Reset — clearly secondary
        self.clear_filter_button = QPushButton("↺  Reset")
        self.clear_filter_button.setToolTip("Clear all filters")
        lay.addWidget(self.clear_filter_button)

        return bar

    # ── Quick-preset chip strip ───────────────────────────────────────────

    def _build_preset_chips(self) -> QFrame:
        """
        Compact row of one-click smart filter chips.
        Each chip activates a pre-wired filter combination; active chip stays
        highlighted.  Chips update the existing filter bar controls so the
        full filter state is always visible and consistent.
        """
        bar = QFrame()
        bar.setObjectName("presetChipBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        lbl = QLabel("Quick filters:")
        lbl.setObjectName("presetChipLabel")
        lay.addWidget(lbl)

        def _chip(text: str, tooltip: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setObjectName("presetChip")
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setToolTip(tooltip)
            lay.addWidget(btn)
            return btn

        self._chip_all       = _chip("All",          "Show all paints (clear preset)")
        self._chip_low       = _chip("⚠  Low Stock", "Show paints marked as Low or Out")
        self._chip_out       = _chip("❌  Out",       "Show paints marked as Out of stock")
        self._chip_favs      = _chip("⭐  Favorites", "Show only favourited paints")
        self._chip_notify    = _chip("🔔  Notify",    "Show paints with low-stock notifications enabled")

        self._chip_all.setChecked(True)   # default

        # Group them so only one can be active at a time
        self._preset_chips: list[QPushButton] = [
            self._chip_all, self._chip_low, self._chip_out,
            self._chip_favs, self._chip_notify,
        ]

        self._chip_all.clicked.connect(lambda: self._apply_preset("all"))
        self._chip_low.clicked.connect(lambda: self._apply_preset("low"))
        self._chip_out.clicked.connect(lambda: self._apply_preset("out"))
        self._chip_favs.clicked.connect(lambda: self._apply_preset("favs"))
        self._chip_notify.clicked.connect(lambda: self._apply_preset("notify"))

        lay.addStretch()
        return bar

    def _apply_preset(self, preset: str) -> None:
        """Activate a preset: update UI controls, then emit filter_changed."""
        # Highlight the chosen chip exclusively
        for chip in self._preset_chips:
            chip.setChecked(False)

        if preset == "all":
            self._chip_all.setChecked(True)
            # Clear level, favorites
            with QSignalBlocker(self.filter_level_combo):
                self.filter_level_combo.setCurrentIndex(0)
            self._show_favorites_only = False
            with QSignalBlocker(self.favorites_filter_btn):
                self.favorites_filter_btn.setChecked(False)
            self._active_notify_filter = False

        elif preset == "low":
            self._chip_low.setChecked(True)
            # Set level dropdown to "Low" — "All Levels" is index 0, levels follow
            idx = self.filter_level_combo.findText("Low")
            with QSignalBlocker(self.filter_level_combo):
                if idx >= 0:
                    self.filter_level_combo.setCurrentIndex(idx)
            self._show_favorites_only = False
            with QSignalBlocker(self.favorites_filter_btn):
                self.favorites_filter_btn.setChecked(False)
            self._active_notify_filter = False

        elif preset == "out":
            self._chip_out.setChecked(True)
            idx = self.filter_level_combo.findText("Out")
            with QSignalBlocker(self.filter_level_combo):
                if idx >= 0:
                    self.filter_level_combo.setCurrentIndex(idx)
            self._show_favorites_only = False
            with QSignalBlocker(self.favorites_filter_btn):
                self.favorites_filter_btn.setChecked(False)
            self._active_notify_filter = False

        elif preset == "favs":
            self._chip_favs.setChecked(True)
            with QSignalBlocker(self.filter_level_combo):
                self.filter_level_combo.setCurrentIndex(0)
            self._show_favorites_only = True
            with QSignalBlocker(self.favorites_filter_btn):
                self.favorites_filter_btn.setChecked(True)
            self._active_notify_filter = False

        elif preset == "notify":
            self._chip_notify.setChecked(True)
            with QSignalBlocker(self.filter_level_combo):
                self.filter_level_combo.setCurrentIndex(0)
            self._show_favorites_only = False
            with QSignalBlocker(self.favorites_filter_btn):
                self.favorites_filter_btn.setChecked(False)
            self._active_notify_filter = True

        self._emit_filter_changed()

    def _reset_preset_chips(self) -> None:
        """Called from _clear_filter — reset chips back to 'All'."""
        for chip in self._preset_chips:
            chip.setChecked(False)
        self._chip_all.setChecked(True)
        self._active_notify_filter = False

    # ── Table ─────────────────────────────────────────────────────────────

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget(0, _C_COUNT)
        self.table.setHorizontalHeaderLabels(
            ["ID", "★", "Brand", "Name", "Type", "Qty", "Level", "Colour", "Notes", "🔔"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnHidden(_C_ID, True)
        self.table.setShowGrid(False)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(_C_FAV,    QHeaderView.Fixed)
        hdr.setSectionResizeMode(_C_BRAND,  QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_C_NAME,   QHeaderView.Stretch)
        hdr.setSectionResizeMode(_C_TYPE,   QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_C_QTY,    QHeaderView.Fixed)
        hdr.setSectionResizeMode(_C_LEVEL,  QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_C_COLOR,  QHeaderView.Fixed)
        hdr.setSectionResizeMode(_C_NOTES,  QHeaderView.Stretch)
        hdr.setSectionResizeMode(_C_NOTIFY, QHeaderView.Fixed)

        self.table.setColumnWidth(_C_FAV,    28)
        self.table.setColumnWidth(_C_QTY,    54)
        self.table.setColumnWidth(_C_COLOR, 150)
        self.table.setColumnWidth(_C_NOTIFY, 28)

        return self.table

    # ── Footer action bar ─────────────────────────────────────────────────

    def _build_footer(self) -> QFrame:
        """
        Status count · Qty ± controls · Export · Edit · Delete
        All actions disabled until a row is selected.
        """
        bar = QFrame()
        bar.setObjectName("footerBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 6, 4, 2)
        lay.setSpacing(6)

        # Count / low-stock status
        self.status_label = QLabel("0 paints")
        self.status_label.setObjectName("footerStatus")
        lay.addWidget(self.status_label)

        lay.addStretch()

        # Quantity adjustment — clearly paired
        qty_frame = QFrame()
        qty_frame.setObjectName("qtyAdjustGroup")
        qty_lay = QHBoxLayout(qty_frame)
        qty_lay.setContentsMargins(8, 2, 8, 2)
        qty_lay.setSpacing(4)

        qty_lbl = QLabel("Qty")
        qty_lbl.setObjectName("fieldLabel")
        qty_lay.addWidget(qty_lbl)

        self.qty_minus_btn = QPushButton("−")
        self.qty_minus_btn.setObjectName("qtyAdjustBtn")
        self.qty_minus_btn.setFixedSize(28, 28)
        self.qty_minus_btn.setToolTip("Decrease quantity  (or right-click row)")
        self.qty_minus_btn.setEnabled(False)
        qty_lay.addWidget(self.qty_minus_btn)

        self.qty_plus_btn = QPushButton("+")
        self.qty_plus_btn.setObjectName("qtyAdjustBtn")
        self.qty_plus_btn.setFixedSize(28, 28)
        self.qty_plus_btn.setToolTip("Increase quantity  (or right-click row)")
        self.qty_plus_btn.setEnabled(False)
        qty_lay.addWidget(self.qty_plus_btn)

        lay.addWidget(qty_frame)

        lay.addWidget(_vline())

        self.export_btn = QPushButton("⬇  Export CSV")
        self.export_btn.setToolTip("Export current view to CSV")
        lay.addWidget(self.export_btn)

        lay.addWidget(_vline())

        self.edit_button = QPushButton("✎  Edit")
        self.edit_button.setEnabled(False)
        self.edit_button.setToolTip("Edit selected paint")
        lay.addWidget(self.edit_button)

        self.remove_button = QPushButton("Delete")
        self.remove_button.setProperty("class", "danger")
        self.remove_button.setEnabled(False)
        self.remove_button.setToolTip("Permanently delete selected paint")
        lay.addWidget(self.remove_button)

        lay.addWidget(_vline())

        # ── Batch mode toggle ─────────────────────────────────────────────────
        self.batch_btn = QPushButton("⊠  Select")
        self.batch_btn.setObjectName("secondaryBtn")
        self.batch_btn.setToolTip("Enter batch selection mode to update multiple paints at once")
        self.batch_btn.setCheckable(True)
        self.batch_btn.clicked.connect(self._toggle_batch_mode)
        lay.addWidget(self.batch_btn)

        # Batch action buttons — hidden by default
        self._batch_widgets: list[QWidget] = []

        self._batch_sep = _vline()
        self._batch_sep.hide()
        lay.addWidget(self._batch_sep)

        self.batch_select_all_btn = QPushButton("Select All")
        self.batch_select_all_btn.setObjectName("secondaryBtn")
        self.batch_select_all_btn.clicked.connect(self._batch_select_all)
        self.batch_select_all_btn.hide()
        lay.addWidget(self.batch_select_all_btn)

        self.batch_level_btn = QPushButton("Set Level…")
        self.batch_level_btn.setObjectName("secondaryBtn")
        self.batch_level_btn.setToolTip("Set stock level for all selected paints")
        self.batch_level_btn.clicked.connect(self._batch_set_level)
        self.batch_level_btn.hide()
        lay.addWidget(self.batch_level_btn)

        self.batch_delete_btn = QPushButton("Delete Selected")
        self.batch_delete_btn.setObjectName("dangerBtn")
        self.batch_delete_btn.clicked.connect(self._batch_delete)
        self.batch_delete_btn.hide()
        lay.addWidget(self.batch_delete_btn)

        self._batch_widgets = [
            self._batch_sep,
            self.batch_select_all_btn,
            self.batch_level_btn,
            self.batch_delete_btn,
        ]

        return bar

    # ── Statistics tab ────────────────────────────────────────────────────

    def _build_statistics_tab(self) -> QWidget:
        outer = QWidget()
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(16)

        # KPI cards — CountUpLabel gives a satisfying count-up on each refresh
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.stat_total_label     = CountUpLabel("0")
        self.stat_brands_label    = CountUpLabel("0")
        self.stat_types_label     = CountUpLabel("0")
        self.stat_low_stock_label = CountUpLabel("0")
        cards.addWidget(self._stat_card("Total Paints",        self.stat_total_label,     warn=False))
        cards.addWidget(self._stat_card("Unique Brands",       self.stat_brands_label,    warn=False))
        cards.addWidget(self._stat_card("Paint Types",         self.stat_types_label,     warn=False))
        cards.addWidget(self._stat_card("Low / Out of Stock",  self.stat_low_stock_label, warn=True))
        lay.addLayout(cards)

        # Distribution tables
        dist = QHBoxLayout()
        dist.setSpacing(12)
        self.brand_dist_table = self._dist_table(["Brand", "Count"])
        self.type_dist_table  = self._dist_table(["Type",  "Count"])
        self.level_dist_table = self._dist_table(["Level", "Count"])
        dist.addWidget(self._dist_group("By Brand", self.brand_dist_table))
        dist.addWidget(self._dist_group("By Type",  self.type_dist_table))
        dist.addWidget(self._dist_group("By Level", self.level_dist_table))
        lay.addLayout(dist, stretch=1)

        return outer

    # ── Widget factories ──────────────────────────────────────────────────

    def _stat_card(self, title: str, value_lbl: QLabel, warn: bool = False) -> QFrame:
        """KPI card — uses theme tokens via objectName for colour; no hardcoded hex."""
        card = QFrame()
        card.setObjectName("statCard")
        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(16, 14, 16, 14)
        lyt.setAlignment(Qt.AlignCenter)

        hdr_lbl = QLabel(title)
        hdr_lbl.setObjectName("statCardLabel")
        hdr_lbl.setAlignment(Qt.AlignCenter)
        lyt.addWidget(hdr_lbl)

        value_lbl.setObjectName("statCardValueWarn" if warn else "statCardValue")
        value_lbl.setAlignment(Qt.AlignCenter)
        lyt.addWidget(value_lbl)

        return card

    def _dist_table(self, headers: list[str]) -> QTableWidget:
        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        t.setShowGrid(False)
        return t

    def _dist_group(self, title: str, table: QTableWidget) -> QFrame:
        box = QFrame()
        box.setObjectName("distCard")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        hdr = QLabel(title)
        hdr.setObjectName("distCardTitle")
        lay.addWidget(hdr)
        lay.addWidget(table)
        return box

    def _make_swatch(self, color_hex: str) -> QWidget:
        """Colour swatch + monospace hex label. Hex stored as Qt property."""
        container = QWidget()
        container.setProperty("paint_color", color_hex)
        container.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(container)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(8)

        swatch = QLabel()
        swatch.setFixedSize(26, 26)
        bright = QColor(color_hex).lightness()
        border = "rgba(255,255,255,0.15)" if bright < 128 else "rgba(0,0,0,0.20)"
        swatch.setStyleSheet(
            f"background-color:{color_hex}; border:1px solid {border}; border-radius:4px;"
        )
        swatch.setToolTip(color_hex)

        hex_lbl = QLabel(color_hex.upper())
        hex_lbl.setObjectName("swatchHex")
        hex_lbl.setStyleSheet(
            "font-size:11px; font-family:'Consolas','Courier New',monospace; background:transparent;"
        )

        lay.addWidget(swatch)
        lay.addWidget(hex_lbl)
        lay.addStretch()
        return container

    # ── Signals ───────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.add_button.clicked.connect(self._handle_add)
        self.clear_button.clicked.connect(self._clear_form)
        self.color_button.clicked.connect(self._pick_color)
        self.color_hex_input.textChanged.connect(self._on_hex_input_changed)

        self.search_input.textChanged.connect(self._emit_filter_changed)
        self.filter_brand_combo.currentTextChanged.connect(self._emit_filter_changed)
        self.filter_type_combo.currentTextChanged.connect(self._emit_filter_changed)
        self.filter_level_combo.currentTextChanged.connect(self._emit_filter_changed)
        self.clear_filter_button.clicked.connect(self._clear_filter)

        self.filter_color_button.clicked.connect(self._pick_filter_color)
        self.filter_color_hex.textChanged.connect(self._on_filter_hex_changed)
        self.clear_color_filter_button.clicked.connect(lambda: self._clear_color_filter())

        self.table.itemSelectionChanged.connect(self._update_action_buttons)
        self.remove_button.clicked.connect(self._handle_remove)
        self.edit_button.clicked.connect(self._handle_edit)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._on_sort_changed)
        self.qty_minus_btn.clicked.connect(lambda: self._handle_qty_adjust(-1))
        self.qty_plus_btn.clicked.connect(lambda: self._handle_qty_adjust(1))
        self.export_btn.clicked.connect(self._handle_export)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.favorites_filter_btn.toggled.connect(self._on_favorites_filter_toggled)

    # ── Batch mode ────────────────────────────────────────────────────────

    def _toggle_batch_mode(self, checked: bool) -> None:
        """Switch table between single-select (normal) and multi-select (batch) mode."""
        if checked:
            self.table.setSelectionMode(QTableWidget.ExtendedSelection)
            self.batch_btn.setText("✕  Exit Select")
            self.edit_button.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.qty_minus_btn.setEnabled(False)
            self.qty_plus_btn.setEnabled(False)
        else:
            self.table.setSelectionMode(QTableWidget.SingleSelection)
            self.table.clearSelection()
            self.batch_btn.setText("⊠  Select")
            self._update_action_buttons()

        for w in self._batch_widgets:
            w.setVisible(checked)

    def _batch_select_all(self) -> None:
        self.table.selectAll()

    def _get_selected_paint_ids(self) -> list[int]:
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        ids = []
        for row in rows:
            item = self.table.item(row, _C_ID)
            if item:
                try:
                    ids.append(int(item.text()))
                except ValueError:
                    pass
        return ids

    def _batch_set_level(self) -> None:
        ids = self._get_selected_paint_ids()
        if not ids:
            ToastManager.instance().show("No paints selected", level="warning", duration=2000)
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Set Level — {len(ids)} paints")
        dlg.setFixedSize(280, 120)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.addWidget(QLabel(f"New stock level for {len(ids)} selected paints:"))

        combo = QComboBox()
        combo.addItems(VALID_LEVELS)
        lay.addWidget(combo)

        btns = QHBoxLayout()
        ok_btn = QPushButton("Apply")
        ok_btn.setObjectName("primaryBtn")
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        lay.addLayout(btns)

        if not dlg.exec():
            return

        new_level = combo.currentText()
        svc = self.context.services.try_get("paint_service")
        if not svc:
            return

        ok = 0
        for pid in ids:
            try:
                svc.update_paint(pid, level=new_level)
                ok += 1
            except Exception:
                pass

        # Exit batch mode, refresh
        self.batch_btn.setChecked(False)
        self._toggle_batch_mode(False)
        self.context.event_bus.emit("paint_filter_changed", {})
        ToastManager.instance().show(
            f"Updated {ok} paint{'s' if ok != 1 else ''} → {new_level}",
            level="success", duration=2500,
        )

    def _batch_delete(self) -> None:
        ids = self._get_selected_paint_ids()
        if not ids:
            ToastManager.instance().show("No paints selected", level="warning", duration=2000)
            return

        reply = QMessageBox.question(
            self, "Delete Paints",
            f"Permanently delete {len(ids)} selected paint{'s' if len(ids) != 1 else ''}?\n"
            "You can undo this action using the Undo button in the toast.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        svc = self.context.services.try_get("paint_service")
        if not svc:
            return

        # ── Capture state before deletion for undo ────────────────────────
        snapshots: list[dict] = []
        for pid in ids:
            try:
                p = svc.get_paint(pid)
                if p:
                    snapshots.append({
                        "brand":            p.brand,
                        "name":             p.name,
                        "paint_type":       p.paint_type,
                        "color":            p.color,
                        "quantity":         p.quantity,
                        "level":            p.level,
                        "notes":            p.notes or "",
                        "is_favorite":      bool(p.is_favorite),
                        "notify_low_stock": bool(getattr(p, "notify_low_stock", True)),
                    })
            except Exception:
                pass

        ok = 0
        for pid in ids:
            try:
                svc.delete_paint(pid)
                ok += 1
            except Exception:
                pass

        self.batch_btn.setChecked(False)
        self._toggle_batch_mode(False)
        self.context.event_bus.emit("paint_filter_changed", {})

        # ── Register batch undo ───────────────────────────────────────────
        if snapshots:
            _ctx   = self.context
            _snaps = snapshots

            def _undo(_ss=_snaps):
                _svc = _ctx.services.try_get("paint_service")
                if not _svc:
                    return
                for snap in _ss:
                    try:
                        _svc.add_paint(**snap)
                    except Exception as ex:
                        log.error(f"[UNDO] Restore paint failed: {ex}")
                _ctx.event_bus.emit("paint_filter_changed", {})

            from ui.undo_manager import UndoManager
            label = f"Deleted {ok} paint{'s' if ok != 1 else ''}"
            UndoManager.instance().push(label, _undo)
            ToastManager.instance().show(
                label,
                level="info",
                duration=7000,
                action_label="Undo",
                action_fn=_undo,
            )
        else:
            ToastManager.instance().show(
                f"Deleted {ok} paint{'s' if ok != 1 else ''}",
                level="info", duration=2500,
            )

    # ── User actions ──────────────────────────────────────────────────────

    def _handle_add(self):
        brand = self.brand_input.currentText().strip()
        name  = self.name_input.text().strip()
        if not brand:
            self._set_form_status("Brand is required", "error"); return
        if not name:
            self._set_form_status("Name is required", "error"); return

        # Duplicate detection — warn inline but do not block
        brand_lo = brand.lower()
        name_lo  = name.lower()
        for r in range(self.table.rowCount()):
            b_item = self.table.item(r, _C_BRAND)
            n_item = self.table.item(r, _C_NAME)
            if (b_item and b_item.text().lower() == brand_lo and
                    n_item and n_item.text().lower() == name_lo):
                self._set_form_status(
                    f"⚠  '{brand} — {name}' already in collection — adding another copy",
                    "warning",
                )
                break

        paint_type = self.type_combo.currentText().strip()
        self.context.event_bus.emit("paint_added", {
            "brand":            brand,
            "name":             name,
            "type":             paint_type,
            "color":            self._selected_color,
            "quantity":         self.quantity_input.value(),
            "level":            self.level_combo.currentText() or None,
            "notes":            self.notes_input.toPlainText().strip() or None,
            "notify_low_stock": False,
        })
        ToastManager.instance().show(
            f"Added  {brand}  {name}", level="success", duration=2000
        )
        self._save_setting("paint_tracker.last_brand", brand)
        if paint_type:
            self._save_setting("paint_tracker.last_type", paint_type)
        self._clear_form()

    def _handle_remove(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pid   = int(self.table.item(row, _C_ID).text())
        pname = self.table.item(row, _C_NAME).text()
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Remove '{pname}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes:
            self.context.event_bus.emit("paint_removed", {"id": pid})
            ToastManager.instance().show(
                f"Removed  '{pname}'", level="info", duration=2000
            )

    def _handle_edit(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pid   = int(self.table.item(row, _C_ID).text())
        cw    = self.table.cellWidget(row, _C_COLOR)
        color = (cw.property("paint_color") if cw else None) or "#000000"
        ni    = self.table.item(row, _C_NOTES)
        fi    = self.table.item(row, _C_FAV)
        noti  = self.table.item(row, _C_NOTIFY)

        dlg = PaintEditDialog(
            self,
            paint_id         = pid,
            brand            = self.table.item(row, _C_BRAND).text(),
            name             = self.table.item(row, _C_NAME).text(),
            paint_type       = self.table.item(row, _C_TYPE).text(),
            color            = color,
            quantity         = int(self.table.item(row, _C_QTY).text()),
            level            = self.table.item(row, _C_LEVEL).text() or None,
            notes            = ni.data(Qt.UserRole) if ni else None,
            is_favorite      = fi.data(Qt.UserRole) if fi else False,
            notify_low_stock = noti.data(Qt.UserRole) if noti else True,
            default_types    = self.DEFAULT_TYPES,
        )
        if dlg.exec() == QDialog.Accepted:
            self.context.event_bus.emit("paint_updated", {"id": pid, **dlg.get_values()})

    # ── Filtering ─────────────────────────────────────────────────────────

    def _emit_filter_changed(self):
        brand = self.filter_brand_combo.currentText()
        pt    = self.filter_type_combo.currentText()
        lvl   = self.filter_level_combo.currentText()
        srch  = self.search_input.text().strip()
        svc   = self.context.services.get("settings")
        saved = svc.get("paint_tracker.filters", {}) if svc else {}

        self._current_filter = PaintFilter(
            brand          = None if brand == "All Brands" else brand,
            paint_type     = None if pt    == "All Types"  else pt,
            level          = None if lvl   == "All Levels" else lvl,
            search_text    = srch or None,
            favorites_only = self._show_favorites_only,
            notify_only    = getattr(self, "_active_notify_filter", False),
            sort_by        = saved.get("sort_by") or "brand",
            sort_desc      = saved.get("sort_desc", False),
        )
        self.context.event_bus.emit("paints_filter_changed", {"filter": self._current_filter})

    def _on_sort_changed(self, column: int, order: Qt.SortOrder):
        self._current_filter = PaintFilter(
            brand       = self._current_filter.brand,
            paint_type  = self._current_filter.paint_type,
            level       = self._current_filter.level,
            search_text = self._current_filter.search_text,
            sort_by     = self.SORT_COLUMN_TO_FIELD.get(column, "brand"),
            sort_desc   = (order == Qt.DescendingOrder),
        )
        self.context.event_bus.emit("paints_filter_changed", {"filter": self._current_filter})

    def _on_favorites_filter_toggled(self, checked: bool):
        self._show_favorites_only = checked
        self._emit_filter_changed()

    def _clear_filter(self):
        with QSignalBlocker(self.search_input):
            self.search_input.clear()
        for w in (self.filter_brand_combo, self.filter_type_combo, self.filter_level_combo):
            with QSignalBlocker(w):
                w.setCurrentIndex(0)
        self._show_favorites_only = False
        with QSignalBlocker(self.favorites_filter_btn):
            self.favorites_filter_btn.setChecked(False)
        self._filter_color = None
        self._update_filter_color_preview()
        with QSignalBlocker(self.filter_color_hex):
            self.filter_color_hex.clear()
        self._reset_preset_chips()
        self.context.event_bus.emit("stats_color_filter_changed", {"color": None})
        self._emit_filter_changed()

    # ── Colour picker (form) ───────────────────────────────────────────────

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._selected_color), self)
        if c.isValid():
            self._selected_color = c.name().upper()
            self._update_color_preview()
            with QSignalBlocker(self.color_hex_input):
                self.color_hex_input.setText(self._selected_color)

    def _on_hex_input_changed(self, text: str):
        n = self._normalize_hex(text)
        if n:
            self._selected_color = n
            self._update_color_preview()

    def _update_color_preview(self):
        bright = QColor(self._selected_color).lightness()
        border = "rgba(255,255,255,0.2)" if bright < 128 else "rgba(0,0,0,0.25)"
        self.color_preview.setStyleSheet(
            f"background-color:{self._selected_color}; border:1px solid {border}; border-radius:5px;"
        )
        self.color_preview.setToolTip(self._selected_color)

    # ── Colour filter ──────────────────────────────────────────────────────

    def _pick_filter_color(self):
        c = QColorDialog.getColor(
            QColor(self._filter_color) if self._filter_color else QColor("#FFFFFF"), self
        )
        if c.isValid():
            self._set_filter_color(c.name().upper())

    def _on_filter_hex_changed(self, text: str):
        n = self._normalize_hex(text)
        changed = n != self._filter_color
        self._filter_color = n
        self._update_filter_color_preview()
        if changed:
            self._emit_color_filter()

    def _set_filter_color(self, color: str | None):
        self._filter_color = color.upper() if color else None
        self._update_filter_color_preview()
        with QSignalBlocker(self.filter_color_hex):
            self.filter_color_hex.setText(self._filter_color or "")
        self._emit_color_filter()

    def _clear_color_filter(self, emit: bool = True):
        self._filter_color = None
        self._update_filter_color_preview()
        with QSignalBlocker(self.filter_color_hex):
            self.filter_color_hex.clear()
        if emit:
            self._emit_color_filter()

    def _update_filter_color_preview(self):
        if not self._filter_color:
            self.filter_color_preview.setStyleSheet(
                "background:transparent; border:1px dashed #505050; border-radius:4px;"
            )
        else:
            bright = QColor(self._filter_color).lightness()
            border = "rgba(255,255,255,0.12)" if bright < 128 else "rgba(0,0,0,0.18)"
            self.filter_color_preview.setStyleSheet(
                f"background-color:{self._filter_color}; border:1px solid {border}; border-radius:4px;"
            )
        self.filter_color_preview.setToolTip(self._filter_color or "No colour filter active")

    def _emit_color_filter(self):
        self.context.event_bus.emit("stats_color_filter_changed", {"color": self._filter_color})
        self._emit_filter_changed()

    # ── Data display ───────────────────────────────────────────────────────

    def handle_quick_create(self) -> None:
        """Ctrl+N support — focus the Add Paint form and scroll to top."""
        # Switch to Collection tab if needed
        self.tabs.setCurrentIndex(0)
        # Clear form to add mode and focus brand input
        self._clear_form()
        self.brand_input.setFocus()
        self.brand_input.lineEdit().selectAll()

    def display_paints(
        self,
        paints: list[Paint],
        brands: list[str] | None = None,
        types:  list[str] | None = None,
        levels: list[str] | None = None,
    ):
        svc   = self.context.services.get("settings")
        saved = svc.get("paint_tracker.filters", {}) if svc else {}
        scol  = self.SORT_FIELD_TO_COLUMN.get(saved.get("sort_by") or "brand", _C_BRAND)
        sord  = Qt.DescendingOrder if saved.get("sort_desc") else Qt.AscendingOrder

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(paints))

        for row, paint in enumerate(paints):
            self.table.setItem(row, _C_ID, QTableWidgetItem(str(paint.id)))

            # ★ Favourite
            fav_item = QTableWidgetItem("⭐" if paint.is_favorite else "☆")
            fav_item.setTextAlignment(Qt.AlignCenter)
            fav_item.setData(Qt.UserRole, paint.is_favorite)
            fav_item.setToolTip("Click to toggle favourite")
            self.table.setItem(row, _C_FAV, fav_item)

            self.table.setItem(row, _C_BRAND, QTableWidgetItem(paint.brand))
            self.table.setItem(row, _C_NAME,  QTableWidgetItem(paint.name))
            self.table.setItem(row, _C_TYPE,  QTableWidgetItem(paint.paint_type))

            # Qty — show plain number; low-stock colours applied below
            qty_item = QTableWidgetItem(str(paint.quantity))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, _C_QTY, qty_item)

            self.table.setItem(row, _C_LEVEL, QTableWidgetItem(paint.level or ""))
            self.table.setCellWidget(row, _C_COLOR, self._make_swatch(paint.color))
            self.table.setRowHeight(row, 38)

            notes = paint.notes or ""
            disp  = notes[:60] + "…" if len(notes) > 60 else notes
            ni = QTableWidgetItem(disp)
            ni.setData(Qt.UserRole, notes)
            ni.setToolTip(notes if notes else "")
            self.table.setItem(row, _C_NOTES, ni)

            # 🔔 Low-stock notification toggle
            notify_item = QTableWidgetItem("🔔" if paint.notify_low_stock else "🔕")
            notify_item.setTextAlignment(Qt.AlignCenter)
            notify_item.setData(Qt.UserRole, paint.notify_low_stock)
            notify_item.setToolTip(
                "Low-stock alerts ON — click to disable"
                if paint.notify_low_stock else
                "Low-stock alerts OFF — click to enable"
            )
            self.table.setItem(row, _C_NOTIFY, notify_item)

            # ── Low-stock row tinting ──────────────────────────────────────
            # Apply a subtle full-row tint + make qty text stand out.
            # Tint is applied to ALL columns so the row reads consistently.
            if paint.notify_low_stock:
                if paint.quantity == 0:
                    row_bg = QColor(180, 30, 30, 40)   # danger tint — out of stock
                    qty_item.setForeground(QColor("#e05555"))
                elif paint.quantity == 1:
                    row_bg = QColor(180, 100, 0, 35)   # warning tint — last one
                    qty_item.setForeground(QColor("#e07820"))
                else:
                    row_bg = None
            else:
                row_bg = None

            if row_bg is not None:
                for col in range(_C_COUNT):
                    if col == _C_ID:
                        continue
                    item = self.table.item(row, col)
                    if item:
                        item.setBackground(row_bg)

        self.table.setSortingEnabled(True)
        with QSignalBlocker(self.table.horizontalHeader()):
            self.table.sortItems(scol, sord)

        # Status bar
        low_stock = sum(1 for p in paints if p.quantity <= 1 and p.notify_low_stock)
        base_txt  = f"{len(paints)} paint{'s' if len(paints) != 1 else ''}"
        warn_txt  = f"  ·  ⚠ {low_stock} low stock" if low_stock else ""
        self.status_label.setText(base_txt + warn_txt)

        self._update_action_buttons()
        self._update_filter_options(brands, types, levels)

        # Sync brand / type inputs with live collection data
        if brands is not None:
            cur = self.brand_input.currentText()
            merged = [b for b in brands if b.strip()]
            if cur and cur not in merged:
                merged.insert(0, cur)
            with QSignalBlocker(self.brand_input):
                self.brand_input.clear()
                self.brand_input.addItems(merged)
                self.brand_input.setCurrentText(cur)

        if types is not None:
            cur_t = self.type_combo.currentText()
            with QSignalBlocker(self.type_combo):
                self.type_combo.clear()
                self.type_combo.addItems(self._merge_types(types))
                self.type_combo.setCurrentText(cur_t)

        # Empty state overlay
        self._refresh_empty_state(paints)

    def _refresh_empty_state(self, paints: list):
        """Show a helpful overlay when the table is empty."""
        if not hasattr(self, "_empty_lbl"):
            lbl = QLabel(self.table.viewport())
            lbl.setObjectName("emptyState")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            lbl.setWordWrap(True)
            self._empty_lbl = lbl

        if paints:
            self._empty_lbl.hide()
            return

        has_filter = bool(
            self.search_input.text().strip()
            or self.filter_brand_combo.currentIndex() > 0
            or self.filter_type_combo.currentIndex() > 0
            or self.filter_level_combo.currentIndex() > 0
            or self._filter_color
            or self._show_favorites_only
        )

        if has_filter:
            self._empty_lbl.setText(
                "🔍\n\nNo paints match your filters\n\nTry adjusting or resetting the filter bar"
            )
        else:
            self._empty_lbl.setText(
                "🎨\n\nYour paint collection is empty\n\nAdd your first paint using the form above"
            )

        vp = self.table.viewport()
        self._empty_lbl.resize(vp.size())
        self._empty_lbl.move(0, 0)
        self._empty_lbl.show()
        self._empty_lbl.raise_()

    def update_statistics(self, stats: PaintStatistics):
        # Count-up animation for each KPI card
        prev_total = getattr(self, "_prev_total", -1)
        for lbl, val in [
            (self.stat_total_label,     stats.total_count),
            (self.stat_brands_label,    stats.unique_brands),
            (self.stat_types_label,     stats.unique_types),
            (self.stat_low_stock_label, stats.low_stock_count),
        ]:
            try:
                lbl.count_to(float(val))
            except Exception:
                lbl.setText(str(val))

        # Pulse the low-stock card if the count just increased
        if prev_total >= 0 and stats.low_stock_count > getattr(self, "_prev_low", 0):
            try:
                pulse_widget(self.stat_low_stock_label, duration=600, min_opacity=0.2)
            except Exception:
                pass

        self._prev_total = stats.total_count
        self._prev_low   = stats.low_stock_count

        def _fill(t, data):
            t.setRowCount(len(data))
            for i, (k, v) in enumerate(sorted(data.items())):
                t.setItem(i, 0, QTableWidgetItem(k or "(None)"))
                t.setItem(i, 1, QTableWidgetItem(str(v)))

        _fill(self.brand_dist_table, stats.brands_distribution)
        _fill(self.type_dist_table,  stats.types_distribution)
        _fill(self.level_dist_table, stats.levels_distribution)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _update_filter_options(self, brands, types, levels):
        def _ref(combo, items, placeholder):
            if items is None:
                return
            cur = combo.currentText()
            with QSignalBlocker(combo):
                combo.clear()
                combo.addItem(placeholder)
                combo.addItems(items)
                idx = combo.findText(cur)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
        _ref(self.filter_brand_combo, brands, "All Brands")
        _ref(self.filter_type_combo,  types,  "All Types")
        _ref(self.filter_level_combo, levels, "All Levels")

    def _update_action_buttons(self):
        has = self.table.currentRow() >= 0
        self.remove_button.setEnabled(has)
        self.edit_button.setEnabled(has)
        self.qty_minus_btn.setEnabled(has)
        self.qty_plus_btn.setEnabled(has)

    def _clear_form(self):
        last_brand = self._get_setting("paint_tracker.last_brand", "")
        last_type  = self._get_setting("paint_tracker.last_type",  "")
        self.brand_input.setCurrentText(last_brand)
        self.name_input.clear()
        self.type_combo.setCurrentText(last_type) if last_type else self.type_combo.setCurrentIndex(0)
        self.quantity_input.setValue(1)
        self.level_combo.setCurrentText("Full")
        self.notes_input.clear()
        self._selected_color = "#3A86FF"
        with QSignalBlocker(self.color_hex_input):
            self.color_hex_input.setText(self._selected_color)
        self._update_color_preview()
        self._form_status_lbl.setVisible(False)

    def _restore_last_entry_defaults(self):
        last_brand = self._get_setting("paint_tracker.last_brand", "")
        last_type  = self._get_setting("paint_tracker.last_type",  "")
        if last_brand:
            self.brand_input.setCurrentText(last_brand)
        if last_type:
            self.type_combo.setCurrentText(last_type)
        self.level_combo.setCurrentText("Full")

    def _get_setting(self, key: str, default="") -> str:
        svc = self.context.services.try_get("settings")
        return svc.get(key, default) if svc else default

    def _save_setting(self, key: str, value: str):
        svc = self.context.services.try_get("settings")
        if svc:
            svc.set(key, value)

    def _apply_saved_sort_indicator(self):
        svc   = self.context.services.get("settings")
        saved = svc.get("paint_tracker.filters", {}) if svc else {}
        scol  = self.SORT_FIELD_TO_COLUMN.get(saved.get("sort_by") or "brand", _C_BRAND)
        sord  = Qt.DescendingOrder if saved.get("sort_desc") else Qt.AscendingOrder
        self.table.horizontalHeader().setSortIndicator(scol, sord)

    def _merge_types(self, types):
        seen, out = set(), []
        for v in self.DEFAULT_TYPES + list(types):
            k = v.strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(v.strip())
        return out

    @staticmethod
    def _normalize_hex(text: str) -> str | None:
        v = (text or "").strip().upper()
        if len(v) != 7 or not v.startswith("#"):
            return None
        return v if QColor(v).isValid() else None

    # ── Quick quantity adjustment ──────────────────────────────────────────

    def _handle_qty_adjust(self, delta: int):
        """Increment or decrement selected paint's quantity without opening the editor."""
        row = self.table.currentRow()
        if row < 0:
            return
        pid         = int(self.table.item(row, _C_ID).text())
        current_qty = int(self.table.item(row, _C_QTY).text())
        new_qty     = max(0, current_qty + delta)
        if new_qty == current_qty:
            return
        cw   = self.table.cellWidget(row, _C_COLOR)
        ni   = self.table.item(row, _C_NOTES)
        fi   = self.table.item(row, _C_FAV)
        noti = self.table.item(row, _C_NOTIFY)
        self.context.event_bus.emit("paint_updated", {
            "id":               pid,
            "brand":            self.table.item(row, _C_BRAND).text(),
            "name":             self.table.item(row, _C_NAME).text(),
            "type":             self.table.item(row, _C_TYPE).text(),
            "color":            (cw.property("paint_color") if cw else None) or "#000000",
            "quantity":         new_qty,
            "level":            self.table.item(row, _C_LEVEL).text() or None,
            "notes":            ni.data(Qt.UserRole) if ni else None,
            "is_favorite":      fi.data(Qt.UserRole) if fi else False,
            "notify_low_stock": noti.data(Qt.UserRole) if noti else True,
            "_silent":          True,
        })

    # ── CSV export ─────────────────────────────────────────────────────────

    def _handle_export(self):
        """Export the currently displayed paint list to a CSV file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Paint Collection", "paints.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Brand", "Name", "Type", "Quantity", "Level", "Color", "Notes"])
                for r in range(self.table.rowCount()):
                    cw    = self.table.cellWidget(r, _C_COLOR)
                    color = cw.property("paint_color") if cw else ""
                    ni    = self.table.item(r, _C_NOTES)

                    def _txt(col):
                        item = self.table.item(r, col)
                        return item.text() if item else ""

                    writer.writerow([
                        _txt(_C_BRAND), _txt(_C_NAME), _txt(_C_TYPE),
                        _txt(_C_QTY), _txt(_C_LEVEL),
                        color or "",
                        (ni.data(Qt.UserRole) or "") if ni else "",
                    ])
            n = self.table.rowCount()
            self._show_success(
                f"Exported {n} paint{'s' if n != 1 else ''} to:\n{path}"
            )
        except Exception as e:
            self._show_error(f"Export failed: {e}")

    # ── Context menu ───────────────────────────────────────────────────────

    def _on_cell_clicked(self, row: int, col: int):
        if col == _C_FAV:
            self._toggle_favorite(row)
        elif col == _C_NOTIFY:
            self._toggle_notify(row)

    def _on_cell_double_clicked(self, row: int, col: int):
        # Skip the toggle columns — those are handled by single-click
        if col not in (_C_FAV, _C_NOTIFY):
            self.table.selectRow(row)
            self._handle_edit()

    def _toggle_favorite(self, row: int):
        fi = self.table.item(row, _C_FAV)
        if not fi:
            return
        self._emit_toggle(row, is_favorite=not fi.data(Qt.UserRole))

    def _toggle_notify(self, row: int):
        noti = self.table.item(row, _C_NOTIFY)
        if not noti:
            return
        self._emit_toggle(row, notify_low_stock=not noti.data(Qt.UserRole))

    def _emit_toggle(self, row: int, **override):
        pid  = int(self.table.item(row, _C_ID).text())
        cw   = self.table.cellWidget(row, _C_COLOR)
        fi   = self.table.item(row, _C_FAV)
        noti = self.table.item(row, _C_NOTIFY)
        ni   = self.table.item(row, _C_NOTES)
        payload = {
            "id":               pid,
            "brand":            self.table.item(row, _C_BRAND).text(),
            "name":             self.table.item(row, _C_NAME).text(),
            "type":             self.table.item(row, _C_TYPE).text(),
            "color":            (cw.property("paint_color") if cw else None) or "#000000",
            "quantity":         int(self.table.item(row, _C_QTY).text()),
            "level":            self.table.item(row, _C_LEVEL).text() or None,
            "notes":            ni.data(Qt.UserRole) if ni else None,
            "is_favorite":      fi.data(Qt.UserRole) if fi else False,
            "notify_low_stock": noti.data(Qt.UserRole) if noti else True,
            "_silent":          True,
        }
        payload.update(override)
        self.context.event_bus.emit("paint_updated", payload)

    def _show_context_menu(self, pos):
        """Right-click: copy hex, qty adjust, toggle fav/notify, edit, delete."""
        row = self.table.currentRow()
        if row < 0:
            return
        menu  = QMenu(self)
        cw    = self.table.cellWidget(row, _C_COLOR)
        color = cw.property("paint_color") if cw else None
        if color:
            act = menu.addAction(f"Copy Colour  {color}")
            act.triggered.connect(lambda: QApplication.clipboard().setText(color))
            menu.addSeparator()

        fi   = self.table.item(row, _C_FAV)
        noti = self.table.item(row, _C_NOTIFY)
        is_fav    = fi.data(Qt.UserRole)   if fi   else False
        is_notify = noti.data(Qt.UserRole) if noti else True

        fav_act = menu.addAction(
            "★  Remove from Favourites" if is_fav else "☆  Add to Favourites"
        )
        fav_act.triggered.connect(lambda: self._toggle_favorite(row))
        notify_act = menu.addAction(
            "🔕  Disable Low-Stock Alert" if is_notify else "🔔  Enable Low-Stock Alert"
        )
        notify_act.triggered.connect(lambda: self._toggle_notify(row))

        menu.addSeparator()
        menu.addAction("Quantity  +1").triggered.connect(lambda: self._handle_qty_adjust(1))
        menu.addAction("Quantity  −1").triggered.connect(lambda: self._handle_qty_adjust(-1))
        menu.addSeparator()
        menu.addAction("✎  Edit…").triggered.connect(self._handle_edit)
        menu.addAction("Delete").triggered.connect(self._handle_remove)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ── Non-blocking feedback ──────────────────────────────────────────────

    def _set_form_status(self, msg: str, level: str = "error") -> None:
        from PySide6.QtCore import QTimer
        obj = {
            "error":   "formStatusErr",
            "warning": "formStatusWarn",
            "ok":      "formStatusOk",
        }.get(level, "formStatusErr")
        self._form_status_lbl.setObjectName(obj)
        self._form_status_lbl.style().unpolish(self._form_status_lbl)
        self._form_status_lbl.style().polish(self._form_status_lbl)
        self._form_status_lbl.setText(msg)
        self._form_status_lbl.setVisible(True)
        QTimer.singleShot(4000, lambda: self._form_status_lbl.setVisible(False))

    def _show_toast(self, msg: str, obj_name: str = "toastSuccess") -> None:
        from PySide6.QtCore import QTimer
        bar = QLabel(msg, self)
        bar.setObjectName(obj_name)
        bar.adjustSize()
        bar.move(self.width() // 2 - bar.width() // 2, self.height() - 60)
        bar.show()
        bar.raise_()
        QTimer.singleShot(2500, bar.deleteLater)

    def _show_error(self, msg: str) -> None:
        self._show_toast(f"✕  {msg}", "toastError")

    def _show_success(self, msg: str) -> None:
        self._show_toast(f"✓  {msg}", "toastSuccess")

    def _show_info(self, msg: str) -> None:
        self._show_toast(f"ℹ  {msg}", "toastInfo")


# ─────────────────────────────────────────────────────────────────────────────
# EDIT DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class PaintEditDialog(QDialog):
    """
    Full-field editor opened via Edit Selected or right-click → Edit.
    Matches the visual language of the Add form: same field order,
    same divider between rows, same colour-picker layout.
    """

    def __init__(self, parent, paint_id, brand, name, paint_type,
                 color, quantity, level, notes, default_types,
                 is_favorite: bool = False, notify_low_stock: bool = True):
        super().__init__(parent)
        self.paint_id          = paint_id
        self._selected_color   = color
        self._default_types    = default_types
        self._is_favorite      = is_favorite
        self._notify_low_stock = notify_low_stock
        self.setWindowTitle(f"Edit — {brand}  {name}")
        self.setModal(True)
        self.setMinimumWidth(540)
        self._build_ui(brand, name, paint_type, color, quantity, level, notes,
                       is_favorite, notify_low_stock)
        self._connect_signals()

    def _build_ui(self, brand, name, paint_type, color, quantity, level, notes,
                  is_favorite, notify_low_stock):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 18)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        hdr_lbl = QLabel("EDIT PAINT")
        hdr_lbl.setObjectName("dashSectionLabel")
        hdr_lbl.setContentsMargins(0, 0, 0, 10)
        root.addWidget(hdr_lbl)

        # ── Row 1: identity ───────────────────────────────────────────────
        r1 = QHBoxLayout()
        r1.setSpacing(12)
        r1.setContentsMargins(0, 0, 0, 10)

        self.brand_input = QLineEdit(brand)
        self.brand_input.setPlaceholderText("Brand")
        r1.addLayout(_field("Brand", self.brand_input), stretch=3)

        self.name_input = QLineEdit(name)
        self.name_input.setPlaceholderText("Paint name")
        r1.addLayout(_field("Name", self.name_input), stretch=4)

        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.addItems(self._default_types)
        self.type_combo.setCurrentText(paint_type)
        r1.addLayout(_field("Type", self.type_combo), stretch=3)

        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(0)
        self.quantity_input.setMaximum(999)
        self.quantity_input.setValue(quantity)
        self.quantity_input.setFixedWidth(72)
        r1.addLayout(_field("Qty", self.quantity_input))

        self.level_combo = QComboBox()
        self.level_combo.addItem("")
        self.level_combo.addItems(VALID_LEVELS)
        if level:
            self.level_combo.setCurrentText(level)
        r1.addLayout(_field("Level", self.level_combo), stretch=2)

        root.addLayout(r1)

        # ── Divider ───────────────────────────────────────────────────────
        root.addWidget(_hline())

        # ── Row 2: colour + notes ─────────────────────────────────────────
        r2 = QHBoxLayout()
        r2.setSpacing(14)
        r2.setContentsMargins(0, 10, 0, 10)

        # Colour picker
        colour_col = QVBoxLayout()
        colour_col.setSpacing(4)
        _clbl = QLabel("Colour")
        _clbl.setObjectName("fieldLabel")
        colour_col.addWidget(_clbl)

        colour_inner = QHBoxLayout()
        colour_inner.setSpacing(6)
        colour_inner.setContentsMargins(0, 0, 0, 0)

        self.color_preview = QLabel()
        self.color_preview.setFixedSize(40, 34)
        self.color_preview.setObjectName("colorPreviewSwatch")
        self._update_color_preview()
        colour_inner.addWidget(self.color_preview)

        self.color_button = QPushButton("Pick…")
        self.color_button.setFixedHeight(34)
        self.color_button.setMinimumWidth(60)
        colour_inner.addWidget(self.color_button)

        self.color_hex_input = QLineEdit(color)
        self.color_hex_input.setMaxLength(7)
        self.color_hex_input.setPlaceholderText("#RRGGBB")
        self.color_hex_input.setFixedWidth(86)
        self.color_hex_input.setFixedHeight(34)
        colour_inner.addWidget(self.color_hex_input)

        colour_col.addLayout(colour_inner)
        r2.addLayout(colour_col)

        r2.addWidget(_vline())

        # Notes
        notes_col = QVBoxLayout()
        notes_col.setSpacing(4)
        _nlbl = QLabel("Notes")
        _nlbl.setObjectName("fieldLabel")
        notes_col.addWidget(_nlbl)
        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(60)
        self.notes_input.setPlaceholderText("Optional notes…")
        if notes:
            self.notes_input.setPlainText(notes)
        notes_col.addWidget(self.notes_input)
        r2.addLayout(notes_col, stretch=1)

        root.addLayout(r2)

        # ── Row 3: options ────────────────────────────────────────────────
        root.addWidget(_hline())

        r3 = QHBoxLayout()
        r3.setSpacing(24)
        r3.setContentsMargins(0, 10, 0, 10)
        self.favorite_check = QCheckBox("⭐  Mark as Favourite")
        self.favorite_check.setChecked(is_favorite)
        self.notify_check = QCheckBox("🔔  Notify when low stock")
        self.notify_check.setChecked(notify_low_stock)
        r3.addWidget(self.favorite_check)
        r3.addWidget(self.notify_check)
        r3.addStretch()
        root.addLayout(r3)

        root.addWidget(_hline())

        # Inline validation strip
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("formStatusErr")
        self._status_lbl.setVisible(False)
        self._status_lbl.setContentsMargins(0, 4, 0, 4)
        root.addWidget(self._status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 6, 0, 0)
        btn_row.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.save_button   = QPushButton("Save Changes")
        self.save_button.setProperty("class", "primary")
        self.save_button.setDefault(True)
        self.save_button.setMinimumWidth(120)
        btn_row.addWidget(self.cancel_button)
        btn_row.addWidget(self.save_button)
        root.addLayout(btn_row)

    def _connect_signals(self):
        self.save_button.clicked.connect(self._handle_save)
        self.cancel_button.clicked.connect(self.reject)
        self.color_button.clicked.connect(self._pick_color)
        self.color_hex_input.textChanged.connect(self._on_hex_changed)

    def _handle_save(self):
        if not self.brand_input.text().strip():
            self._status_lbl.setText("Brand is required")
            self._status_lbl.setVisible(True)
            self.brand_input.setFocus()
            return
        if not self.name_input.text().strip():
            self._status_lbl.setText("Name is required")
            self._status_lbl.setVisible(True)
            self.name_input.setFocus()
            return
        self.accept()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._selected_color), self)
        if c.isValid():
            self._selected_color = c.name().upper()
            self._update_color_preview()
            with QSignalBlocker(self.color_hex_input):
                self.color_hex_input.setText(self._selected_color)

    def _on_hex_changed(self, text: str):
        n = PaintUI._normalize_hex(text)
        if n:
            self._selected_color = n
            self._update_color_preview()

    def _update_color_preview(self):
        bright = QColor(self._selected_color).lightness()
        border = "rgba(255,255,255,0.2)" if bright < 128 else "rgba(0,0,0,0.25)"
        self.color_preview.setStyleSheet(
            f"background-color:{self._selected_color}; border:1px solid {border}; border-radius:5px;"
        )
        self.color_preview.setToolTip(self._selected_color)

    def get_values(self) -> dict:
        level = self.level_combo.currentText().strip()
        notes = self.notes_input.toPlainText().strip()
        return {
            "brand":            self.brand_input.text().strip(),
            "name":             self.name_input.text().strip(),
            "type":             self.type_combo.currentText().strip(),
            "color":            self._selected_color,
            "quantity":         self.quantity_input.value(),
            "level":            level or None,
            "notes":            notes or None,
            "is_favorite":      self.favorite_check.isChecked(),
            "notify_low_stock": self.notify_check.isChecked(),
        }
