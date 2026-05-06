"""
Army Builder UI

Three tabs:
  "My Lists"  — browse, create, duplicate, delete army lists
  "Builder"   — open list editor: roster tree + unit form + points bar
  "Statistics"— collection-wide breakdown

Pure presentation layer. All user actions emit events.
All data arrives via display_* / load_* method calls from the plugin.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSignalBlocker, QEvent
from PySide6.QtGui import QColor, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QMessageBox, QTabWidget, QTextEdit,
    QDialog, QDialogButtonBox, QFrame, QScrollArea,
    QTreeWidget, QTreeWidgetItem, QProgressBar,
    QSizePolicy, QApplication,
    QListWidget, QListWidgetItem, QStackedWidget,
)

from .models import (
    ArmyFilter, ArmyStatistics,
    UNIT_ROLES, ARMY_FORMATS,
    get_roles_for_system, get_formats_for_system, parse_points_limit,
)

from plugins.shared_widgets import RelatedItemsSection, LinkedEntityChip


# ── Layout helpers (mirrors model_tracker / paint_tracker pattern) ────────

def _vline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine); f.setFixedWidth(1)
    return f

def _hline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    return f

def _field(label_text: str, widget: QWidget) -> QVBoxLayout:
    """Stacked muted label + widget block for horizontal form rows."""
    col = QVBoxLayout(); col.setSpacing(4)
    lbl = QLabel(label_text); lbl.setObjectName("fieldLabel")
    col.addWidget(lbl); col.addWidget(widget)
    return col

def _fmt_pts(v: float) -> str:
    """Format a points value: whole numbers show without decimal, others show as needed."""
    if v == int(v):
        return str(int(v))
    return f"{v:g}"


# ============================================================
# PAINT LINK DIALOG
# ============================================================

class PaintLinkDialog(QDialog):
    """
    Select which paints are directly linked to a unit.
    Shows the full paint_tracker collection with checkboxes.
    Gracefully handles paint_tracker not being loaded.
    """

    def __init__(self, context, current_paint_ids: list[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link Paints to Unit")
        self.setMinimumSize(500, 500)
        self._context = context
        self._selected_ids: list[int] = list(current_paint_ids)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Select paints used for this unit.\n"
            "These will appear in the Army Paints view."
        ))

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter paints…")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self._list)
        self._populate()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _populate(self):
        paint_service = self._context.services.try_get("paint_service")
        if not paint_service:
            item = QListWidgetItem("⚠  Paint Tracker service unavailable — restart the app.")
            item.setFlags(Qt.ItemIsEnabled)
            self._list.addItem(item)
            return
        try:
            paints = paint_service.get_all_paints()
        except Exception as e:
            item = QListWidgetItem(f"⚠  Could not load paints: {e}")
            item.setFlags(Qt.ItemIsEnabled)
            self._list.addItem(item)
            return

        if not paints:
            item = QListWidgetItem("No paints in your collection yet — add them in the Paint Tracker tab.")
            item.setFlags(Qt.ItemIsEnabled)
            self._list.addItem(item)
            return

        for paint in paints:
            color_hint = f"  {paint.color}" if (paint.color and paint.color.startswith("#")) else ""
            label = f"{paint.brand} — {paint.name}  [{paint.paint_type}]{color_hint}"
            item = QListWidgetItem(label)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if paint.id in self._selected_ids else Qt.Unchecked)
            item.setData(Qt.UserRole, paint.id)
            self._list.addItem(item)

    def _filter(self, text: str):
        needle = text.lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(needle not in item.text().lower())

    def _on_ok(self):
        self._selected_ids = [
            self._list.item(i).data(Qt.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.Checked
            and self._list.item(i).data(Qt.UserRole) is not None
        ]
        self.accept()

    def get_selected_ids(self) -> list[int]:
        return self._selected_ids


# ============================================================
# EXPORT DIALOG
# ============================================================

class ExportDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Army List")
        self.setMinimumSize(520, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Copy the text below to share your list:"))

        self._text_area = QTextEdit()
        self._text_area.setPlainText(text)
        self._text_area.setReadOnly(True)
        self._text_area.setFont(QFont("Courier New", 9))
        layout.addWidget(self._text_area)

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _copy(self):
        QApplication.clipboard().setText(self._text_area.toPlainText())


# ============================================================
# MAIN UI
# ============================================================

class ArmyBuilderUI(QWidget):
    """
    Top-level Army Builder widget.
    Hosts three tabs: My Lists, Builder, Statistics.
    """

    # List tab table columns
    LIST_COLUMNS = ["Name", "Game System", "Faction", "Format", "Points Limit", "Units", "Total Pts"]
    LIST_SORT_MAP = {0: "name", 1: "game_system", 2: "faction", 3: "format", 4: "points_limit"}

    def __init__(self, context):
        super().__init__()
        self.context = context

        self._current_army_id: int | None = None
        self._current_filter = ArmyFilter()
        self._editing_unit_id: int | None = None
        self._unit_sort_order: int = 0
        self._unit_linked_paint_ids: list[int] = []  # paints linked to unit in form

        self._build_ui()
        self._connect_signals()

    # ============================================================
    # TOP-LEVEL CONSTRUCTION
    # ============================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(12)

        title = QLabel("Army Builder")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs)

        self._tabs.addTab(self._build_lists_tab(), "My Lists")
        self._tabs.addTab(self._build_builder_tab(), "Builder")
        self._tabs.addTab(self._build_paints_tab(), "Army Paints")
        self._tabs.addTab(self._build_stats_tab(), "Statistics")

    # ============================================================
    # MY LISTS TAB
    # ============================================================

    def _build_lists_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        layout.addWidget(self._build_new_army_form())
        layout.addWidget(self._build_list_filter_bar())

        # Stacked widget: index 0 = populated table, index 1 = empty state
        self._lists_stack = QStackedWidget()
        self._lists_stack.addWidget(self._build_army_table())   # 0
        _empty_w = QWidget()
        _empty_lay = QVBoxLayout(_empty_w)
        self._lists_empty_lbl = QLabel(
            "No army lists yet\n\nFill in the form above and click Create List to get started."
        )
        self._lists_empty_lbl.setAlignment(Qt.AlignCenter)
        self._lists_empty_lbl.setObjectName("emptyState")
        _empty_lay.addWidget(self._lists_empty_lbl)
        self._lists_stack.addWidget(_empty_w)                   # 1
        layout.addWidget(self._lists_stack, stretch=1)

        layout.addLayout(self._build_list_action_bar())

        return tab

    def _build_new_army_form(self) -> QGroupBox:
        box = QGroupBox("Create New List")
        outer = QVBoxLayout(box)
        outer.setSpacing(10)

        r1 = QHBoxLayout(); r1.setSpacing(10)

        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText("e.g. My Iron Warriors — 2000pts")
        r1.addLayout(_field("List Name", self.new_name_input), stretch=3)

        self.new_system_combo = QComboBox()
        self.new_system_combo.setEditable(True)
        self.new_system_combo.addItems([""] + list(ARMY_FORMATS.keys()))
        r1.addLayout(_field("Game System", self.new_system_combo), stretch=2)

        self.new_faction_input = QLineEdit()
        self.new_faction_input.setPlaceholderText("e.g. Iron Warriors, Space Marines")
        r1.addLayout(_field("Faction", self.new_faction_input), stretch=2)

        self.new_format_combo = QComboBox()
        self.new_format_combo.setEditable(True)
        r1.addLayout(_field("Format", self.new_format_combo), stretch=2)

        self.new_points_spin = QSpinBox()
        self.new_points_spin.setRange(0, 99999)
        self.new_points_spin.setValue(0)
        self.new_points_spin.setSpecialValueText("No Limit")
        self.new_points_spin.setFixedWidth(110)
        r1.addLayout(_field("Points Limit", self.new_points_spin))

        outer.addLayout(r1)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self._create_army_btn = QPushButton("Create List")
        self._create_army_btn.setProperty("class", "primary")
        self._create_army_btn.setFixedHeight(34)
        self._new_form_status = QLabel("")
        btn_row.addWidget(self._create_army_btn)
        btn_row.addWidget(self._new_form_status)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        return box

    def _build_list_filter_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Search:"))
        self.list_search = QLineEdit()
        self.list_search.setPlaceholderText("Name, system, faction…")
        layout.addWidget(self.list_search, stretch=1)

        layout.addWidget(_vline())

        layout.addWidget(QLabel("System:"))
        self.list_filter_system = QComboBox()
        self.list_filter_system.setMinimumWidth(160)
        layout.addWidget(self.list_filter_system)

        layout.addWidget(QLabel("Faction:"))
        self.list_filter_faction = QComboBox()
        self.list_filter_faction.setMinimumWidth(130)
        layout.addWidget(self.list_filter_faction)

        layout.addWidget(_vline())

        self._clear_list_filter_btn = QPushButton("Reset")
        layout.addWidget(self._clear_list_filter_btn)

        return bar

    def _build_army_table(self) -> QTableWidget:
        self.army_table = QTableWidget()
        self.army_table.setColumnCount(len(self.LIST_COLUMNS))
        self.army_table.setHorizontalHeaderLabels(self.LIST_COLUMNS)
        self.army_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.army_table.setSelectionMode(QTableWidget.SingleSelection)
        self.army_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.army_table.setAlternatingRowColors(True)
        self.army_table.verticalHeader().setVisible(False)

        hdr = self.army_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(self.LIST_COLUMNS)):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        hdr.setSectionsClickable(True)

        return self.army_table

    def _build_list_action_bar(self) -> QHBoxLayout:
        lay = QHBoxLayout(); lay.setContentsMargins(0, 4, 0, 0); lay.setSpacing(8)

        self._open_builder_btn = QPushButton("Open in Builder →")
        self._open_builder_btn.setProperty("class", "primary")
        self._duplicate_btn = QPushButton("Duplicate")
        self._delete_army_btn = QPushButton("Delete")
        self._delete_army_btn.setProperty("class", "danger")
        self._list_count_label = QLabel("No lists")
        self._list_count_label.setObjectName("fieldLabel")

        lay.addWidget(self._open_builder_btn)
        lay.addWidget(self._duplicate_btn)
        lay.addWidget(self._delete_army_btn)
        lay.addStretch()
        lay.addWidget(self._list_count_label)

        return lay

    # ============================================================
    # BUILDER TAB
    # ============================================================

    def _build_builder_tab(self) -> QWidget:
        self._builder_container = QWidget()
        layout = QVBoxLayout(self._builder_container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Placeholder shown when no army is open
        self._builder_placeholder = QLabel(
            "Select a list from My Lists and click \"Open in Builder →\"\n"
            "or create a new list above."
        )
        self._builder_placeholder.setAlignment(Qt.AlignCenter)
        self._builder_placeholder.setObjectName("fieldLabel")
        self._builder_placeholder.setStyleSheet("font-size: 14px; color: #606060;")
        layout.addWidget(self._builder_placeholder)

        # Army header bar (hidden until army is loaded)
        self._builder_header = self._build_army_header()
        self._builder_header.setVisible(False)
        layout.addWidget(self._builder_header)

        # Used in Projects back-link (hidden until army is loaded)
        self._army_projects_section = RelatedItemsSection(title="USED IN PROJECTS", icon="📁")
        self._army_projects_section.navigate_requested.connect(
            lambda pid, _eid: self._emit_navigate(pid)
        )
        self._army_projects_section.set_empty("Not linked to any project.")
        self._army_projects_section.setVisible(False)
        layout.addWidget(self._army_projects_section)

        # Splitter: roster (left) + unit form (right)
        self._builder_splitter = QSplitter(Qt.Horizontal)
        self._builder_splitter.setVisible(False)
        self._builder_splitter.addWidget(self._build_roster_panel())
        self._builder_splitter.addWidget(self._build_unit_form_panel())
        self._builder_splitter.setStretchFactor(0, 1)
        self._builder_splitter.setStretchFactor(1, 1)
        layout.addWidget(self._builder_splitter, stretch=1)

        return self._builder_container

    def _build_army_header(self) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Row 1: identity fields using _field() helpers
        r1 = QHBoxLayout(); r1.setSpacing(10)

        self.builder_name_input = QLineEdit()
        self.builder_name_input.setPlaceholderText("List name")
        r1.addLayout(_field("List Name", self.builder_name_input), stretch=3)

        self.builder_system_combo = QComboBox()
        self.builder_system_combo.setEditable(True)
        self.builder_system_combo.addItems(list(ARMY_FORMATS.keys()))
        r1.addLayout(_field("Game System", self.builder_system_combo), stretch=2)

        self.builder_faction_input = QLineEdit()
        r1.addLayout(_field("Faction", self.builder_faction_input), stretch=2)

        self.builder_format_combo = QComboBox()
        self.builder_format_combo.setEditable(True)
        r1.addLayout(_field("Format", self.builder_format_combo), stretch=2)

        self.builder_points_limit = QSpinBox()
        self.builder_points_limit.setRange(0, 99999)
        self.builder_points_limit.setSpecialValueText("∞")
        self.builder_points_limit.setFixedWidth(90)
        r1.addLayout(_field("Pt Limit", self.builder_points_limit))

        layout.addLayout(r1)

        # Row 2: notes + points bar + action buttons
        r2 = QHBoxLayout(); r2.setSpacing(10)

        self.builder_notes_input = QLineEdit()
        self.builder_notes_input.setPlaceholderText("Optional list notes")
        r2.addLayout(_field("Notes", self.builder_notes_input), stretch=2)

        r2.addWidget(_vline())

        pts_col = QVBoxLayout(); pts_col.setSpacing(4)
        self._points_label = QLabel("Points: 0 / ∞")
        self._points_label.setObjectName("fieldLabel")
        pts_col.addWidget(self._points_label)
        self._points_bar = QProgressBar()
        self._points_bar.setRange(0, 100)
        self._points_bar.setValue(0)
        self._points_bar.setTextVisible(False)
        self._points_bar.setMaximumHeight(10)
        self._points_bar.setVisible(False)
        pts_col.addWidget(self._points_bar)
        r2.addLayout(pts_col, stretch=1)

        r2.addWidget(_vline())

        self._save_header_btn   = QPushButton("Save Changes")
        self._export_btn        = QPushButton("Export")
        self._close_builder_btn = QPushButton("Close List")
        r2.addWidget(self._save_header_btn)
        r2.addWidget(self._export_btn)
        r2.addWidget(self._close_builder_btn)

        layout.addLayout(r2)
        return frame

    def _build_roster_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        roster_label = QLabel("Roster")
        roster_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #d8d8d8;")
        layout.addWidget(roster_label)

        # Tree widget showing units grouped by role
        self.roster_tree = QTreeWidget()
        self.roster_tree.setColumnCount(3)
        self.roster_tree.setHeaderLabels(["Unit / Role", "Qty", "Points"])
        self.roster_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.roster_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.roster_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.roster_tree.setSelectionMode(QTreeWidget.SingleSelection)
        self.roster_tree.setAlternatingRowColors(True)
        self.roster_tree.setExpandsOnDoubleClick(True)
        layout.addWidget(self.roster_tree, stretch=1)

        # Roster action buttons
        btn_row = QHBoxLayout()
        self._edit_unit_btn = QPushButton("Edit Selected")
        self._duplicate_unit_btn = QPushButton("Duplicate")
        self._duplicate_unit_btn.setToolTip("Copy the selected unit  (Del = remove)")
        self._duplicate_unit_btn.setEnabled(False)
        self._remove_unit_btn = QPushButton("Remove")
        self._remove_unit_btn.setProperty("class", "danger")
        self._move_up_btn = QPushButton("▲")
        self._move_up_btn.setFixedWidth(32)
        self._move_down_btn = QPushButton("▼")
        self._move_down_btn.setFixedWidth(32)

        btn_row.addWidget(self._edit_unit_btn)
        btn_row.addWidget(self._duplicate_unit_btn)
        btn_row.addWidget(self._remove_unit_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._move_up_btn)
        btn_row.addWidget(self._move_down_btn)
        layout.addLayout(btn_row)

        # Enable Delete key on the roster tree
        self.roster_tree.installEventFilter(self)

        self._roster_status = QLabel("")
        layout.addWidget(self._roster_status)

        return panel

    def _build_unit_form_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("Add / Edit Unit")
        form_layout = QVBoxLayout(box)
        form_layout.setSpacing(10)

        # ── Row 1: key fields ──────────────────────────────────────────────
        r1 = QHBoxLayout(); r1.setSpacing(10)

        self.unit_name_input = QLineEdit()
        self.unit_name_input.setPlaceholderText("e.g. Tactical Squad, Gandalf")
        r1.addLayout(_field("Unit Name", self.unit_name_input), stretch=3)

        self.unit_role_combo = QComboBox()
        self.unit_role_combo.setEditable(True)
        r1.addLayout(_field("Role", self.unit_role_combo), stretch=2)

        self.unit_qty_spin = QSpinBox()
        self.unit_qty_spin.setRange(1, 9999)
        self.unit_qty_spin.setValue(1)
        self.unit_qty_spin.setFixedWidth(80)
        r1.addLayout(_field("Qty", self.unit_qty_spin))

        self.unit_pts_spin = QDoubleSpinBox()
        self.unit_pts_spin.setRange(0, 99999)
        self.unit_pts_spin.setValue(0)
        self.unit_pts_spin.setSingleStep(0.5)
        self.unit_pts_spin.setDecimals(1)
        self.unit_pts_spin.setSpecialValueText("Free")
        self.unit_pts_spin.setFixedWidth(90)

        pts_col = QVBoxLayout(); pts_col.setSpacing(4)
        pts_lbl = QLabel("Pts / model"); pts_lbl.setObjectName("fieldLabel")
        self._unit_pts_total_lbl = QLabel("= 0 pts")
        self._unit_pts_total_lbl.setStyleSheet("font-size: 11px; color: #0078d4; font-weight: 600;")
        pts_col.addWidget(pts_lbl)
        pts_col.addWidget(self.unit_pts_spin)
        pts_col.addWidget(self._unit_pts_total_lbl)
        r1.addLayout(pts_col)

        form_layout.addLayout(r1)

        # ── Row 2: wargear + model/paint links ────────────────────────────
        r2 = QHBoxLayout(); r2.setSpacing(10)

        wg_col = QVBoxLayout(); wg_col.setSpacing(4)
        wg_lbl = QLabel("Wargear / Loadout / Abilities")
        wg_lbl.setObjectName("fieldLabel"); wg_col.addWidget(wg_lbl)
        self.unit_wargear_input = QTextEdit()
        self.unit_wargear_input.setPlaceholderText(
            "e.g. Plasma Gun ×2, Power Sword\nSpell list, abilities, equipment…"
        )
        self.unit_wargear_input.setFixedHeight(80)
        wg_col.addWidget(self.unit_wargear_input)
        r2.addLayout(wg_col, stretch=2)

        r2.addWidget(_vline())

        links_col = QVBoxLayout(); links_col.setSpacing(6)

        mdl_lbl = QLabel("Link to Model"); mdl_lbl.setObjectName("fieldLabel")
        links_col.addWidget(mdl_lbl)
        self.unit_model_combo = QComboBox()
        self.unit_model_combo.setMinimumWidth(140)
        links_col.addWidget(self.unit_model_combo)

        pnt_lbl = QLabel("Linked Paints"); pnt_lbl.setObjectName("fieldLabel")
        links_col.addWidget(pnt_lbl)
        paint_row = QHBoxLayout(); paint_row.setSpacing(6)
        self._unit_paints_label = QLabel("None")
        paint_row.addWidget(self._unit_paints_label, stretch=1)
        self._manage_unit_paints_btn = QPushButton("Manage")
        self._manage_unit_paints_btn.setFixedWidth(80)
        self._manage_unit_paints_btn.clicked.connect(self._open_paint_link_dialog)
        paint_row.addWidget(self._manage_unit_paints_btn)
        links_col.addLayout(paint_row)
        links_col.addStretch()

        r2.addLayout(links_col, stretch=1)
        form_layout.addLayout(r2)

        form_layout.addWidget(_hline())

        # ── Action buttons ────────────────────────────────────────────────
        unit_btn_row = QHBoxLayout(); unit_btn_row.setSpacing(6)
        self._add_unit_btn = QPushButton("Add Unit")
        self._add_unit_btn.setProperty("class", "primary")
        self._add_unit_btn.setFixedHeight(34)
        self._update_unit_btn = QPushButton("Save Changes")
        self._update_unit_btn.setProperty("class", "primary")
        self._update_unit_btn.setFixedHeight(34)
        self._update_unit_btn.setVisible(False)
        self._cancel_edit_btn = QPushButton("Cancel")
        self._cancel_edit_btn.setFixedHeight(34)
        self._cancel_edit_btn.setVisible(False)
        unit_btn_row.addWidget(self._add_unit_btn)
        unit_btn_row.addWidget(self._update_unit_btn)
        unit_btn_row.addWidget(self._cancel_edit_btn)
        unit_btn_row.addStretch()
        self._unit_form_status = QLabel("")
        unit_btn_row.addWidget(self._unit_form_status)
        form_layout.addLayout(unit_btn_row)

        layout.addWidget(box)
        layout.addStretch()

        return panel

    # ============================================================
    # STATISTICS TAB
    # ============================================================

    # ============================================================
    # ARMY PAINTS TAB
    # ============================================================

    def _build_paints_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header bar
        hdr_frame = QFrame(); hdr_frame.setFrameShape(QFrame.StyledPanel)
        hdr_lay = QHBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(12, 8, 12, 8); hdr_lay.setSpacing(8)
        self._paints_army_label = QLabel("Open a list in the Builder tab to see its paint requirements.")
        self._paints_army_label.setStyleSheet("font-weight: 600; color: #d8d8d8;")
        hdr_lay.addWidget(self._paints_army_label, stretch=1)
        self._paints_refresh_btn = QPushButton("Refresh")
        self._paints_refresh_btn.clicked.connect(self._emit_refresh_paints)
        hdr_lay.addWidget(self._paints_refresh_btn)
        layout.addWidget(hdr_frame)

        # Filter bar
        opts_frame = QFrame(); opts_frame.setFrameShape(QFrame.StyledPanel)
        opts = QHBoxLayout(opts_frame)
        opts.setContentsMargins(12, 8, 12, 8); opts.setSpacing(8)

        opts.addWidget(QLabel("Search:"))
        self._paints_search = QLineEdit()
        self._paints_search.setPlaceholderText("Paint name or unit…")
        self._paints_search.textChanged.connect(self._filter_paint_table)
        opts.addWidget(self._paints_search, stretch=1)

        opts.addWidget(_vline())

        opts.addWidget(QLabel("Unit:"))
        self._paints_unit_filter = QComboBox()
        self._paints_unit_filter.addItem("All Units")
        self._paints_unit_filter.currentTextChanged.connect(self._filter_paint_table)
        opts.addWidget(self._paints_unit_filter)

        opts.addWidget(QLabel("Source:"))
        self._paints_source_filter = QComboBox()
        self._paints_source_filter.addItems(["All Sources", "Direct links", "Via Model Tracker"])
        self._paints_source_filter.currentTextChanged.connect(self._filter_paint_table)
        opts.addWidget(self._paints_source_filter)
        layout.addWidget(opts_frame)

        # Paint table
        self.paint_list_table = QTableWidget()
        self.paint_list_table.setColumnCount(7)
        self.paint_list_table.setHorizontalHeaderLabels(
            ["", "Brand", "Paint Name", "Type", "Used By Units", "Source", "Stock"]
        )
        self.paint_list_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.paint_list_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.paint_list_table.setAlternatingRowColors(True)
        self.paint_list_table.verticalHeader().setVisible(False)
        self.paint_list_table.verticalHeader().setDefaultSectionSize(36)
        hdr = self.paint_list_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.paint_list_table.setColumnWidth(0, 80)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        layout.addWidget(self.paint_list_table, stretch=1)

        # Summary bar
        summary = QFrame(); summary.setFrameShape(QFrame.StyledPanel)
        sl = QHBoxLayout(summary); sl.setContentsMargins(12, 6, 12, 6); sl.setSpacing(4)
        self._paints_total_lbl   = QLabel("Unique paints: 0")
        self._paints_missing_lbl = QLabel("Out of stock: 0")
        self._paints_missing_lbl.setStyleSheet("color: #e05555;")
        self._paints_low_lbl     = QLabel("Low stock: 0")
        self._paints_low_lbl.setStyleSheet("color: #e07800;")
        self._paints_direct_lbl  = QLabel("Direct links: 0")
        self._paints_model_lbl   = QLabel("Via model: 0")
        for lbl in [self._paints_total_lbl, self._paints_missing_lbl,
                    self._paints_low_lbl, self._paints_direct_lbl, self._paints_model_lbl]:
            sl.addWidget(lbl)
            sl.addWidget(_vline())
        sl.addStretch()
        layout.addWidget(summary)

        # Store raw data for filtering
        self._paint_list_raw: list[dict] = []

        return tab

    # ----------------------------------------------------------
    # Paint list data display
    # ----------------------------------------------------------

    def refresh_paint_list(self, paint_entries: list[dict], army_name: str = ""):
        """
        Paint entries: list of {
            paint_id, paint (Paint object or None),
            unit_names: [str], sources: {str}
        }
        """
        self._paint_list_raw = paint_entries

        if army_name:
            self._paints_army_label.setText(f"Paints required for: {army_name}")

        # Rebuild unit filter dropdown
        all_units: set[str] = set()
        for entry in paint_entries:
            all_units.update(entry.get("unit_names", []))
        current_unit = self._paints_unit_filter.currentText()
        with QSignalBlocker(self._paints_unit_filter):
            self._paints_unit_filter.clear()
            self._paints_unit_filter.addItem("All Units")
            for u in sorted(all_units):
                self._paints_unit_filter.addItem(u)
            idx = self._paints_unit_filter.findText(current_unit)
            self._paints_unit_filter.setCurrentIndex(idx if idx >= 0 else 0)

        self._filter_paint_table()

    def _filter_paint_table(self):
        """Apply search + unit + source filters to the raw paint list."""
        needle = self._paints_search.text().lower()
        unit_filter = self._paints_unit_filter.currentText()
        source_filter = self._paints_source_filter.currentText()

        filtered = []
        for entry in self._paint_list_raw:
            paint = entry.get("paint")
            sources = entry.get("sources", set())
            unit_names = entry.get("unit_names", [])

            # Source filter
            if source_filter == "Direct links" and "direct" not in sources:
                continue
            if source_filter == "Via Model Tracker" and "model" not in sources:
                continue

            # Unit filter
            if unit_filter != "All Units" and unit_filter not in unit_names:
                continue

            # Text filter
            if needle:
                brand = getattr(paint, "brand", "") or ""
                name = getattr(paint, "name", "") or ""
                units_str = ", ".join(unit_names)
                if needle not in f"{brand} {name} {units_str}".lower():
                    continue

            filtered.append(entry)

        self._populate_paint_table(filtered)

    def _make_paint_swatch(self, color_hex: str) -> QWidget:
        """Colored swatch that fills the table cell."""
        from PySide6.QtGui import QColor as _QColor
        bright = _QColor(color_hex).lightness()
        border = "rgba(255,255,255,0.15)" if bright < 128 else "rgba(0,0,0,0.20)"
        w = QFrame()
        w.setToolTip(color_hex)
        w.setStyleSheet(
            f"QFrame {{"
            f"  background-color: {color_hex};"
            f"  border: 1px solid {border};"
            f"  border-radius: 4px;"
            f"  margin: 5px 10px;"
            f"}}"
        )
        return w

    def _populate_paint_table(self, entries: list[dict]):
        from PySide6.QtGui import QColor
        self.paint_list_table.setRowCount(0)

        out_count = 0
        low_count = 0
        direct_count = 0
        model_count = 0

        for entry in entries:
            paint = entry.get("paint")
            unit_names = entry.get("unit_names", [])
            sources = entry.get("sources", set())

            row = self.paint_list_table.rowCount()
            self.paint_list_table.insertRow(row)

            # Col 0: color swatch
            self.paint_list_table.setItem(row, 0, QTableWidgetItem())
            if paint and hasattr(paint, "color") and paint.color:
                try:
                    self.paint_list_table.setCellWidget(row, 0, self._make_paint_swatch(paint.color))
                except Exception:
                    pass

            # Col 1: brand
            brand = getattr(paint, "brand", "—") if paint else "—"
            self.paint_list_table.setItem(row, 1, QTableWidgetItem(brand))

            # Col 2: paint name
            name = getattr(paint, "name", f"Paint #{entry.get('paint_id')}") if paint else f"Paint #{entry.get('paint_id')}"
            name_item = QTableWidgetItem(name)
            if not paint:
                name_item.setForeground(QColor("#888888"))
            self.paint_list_table.setItem(row, 2, name_item)

            # Col 3: type
            ptype = getattr(paint, "paint_type", "—") if paint else "—"
            self.paint_list_table.setItem(row, 3, QTableWidgetItem(ptype))

            # Col 4: used by
            units_str = ", ".join(unit_names) if unit_names else "—"
            self.paint_list_table.setItem(row, 4, QTableWidgetItem(units_str))

            # Col 5: source badge
            source_parts = []
            if "direct" in sources:
                source_parts.append("Direct")
                direct_count += 1
            if "model" in sources:
                source_parts.append("Model")
                model_count += 1
            src_item = QTableWidgetItem(" + ".join(source_parts))
            src_item.setForeground(QColor("#aaaaff"))
            self.paint_list_table.setItem(row, 5, src_item)

            # Col 6: stock level
            level = getattr(paint, "level", None) if paint else None
            if level is None:
                level_text = "—"
                level_color = "#888888"
            elif level == "Out":
                level_text = "Out of Stock"
                level_color = "#cc3333"
                out_count += 1
            elif level == "Low":
                level_text = "Low"
                level_color = "#e07800"
                low_count += 1
            elif level == "Half-Bottle":
                level_text = "Half"
                level_color = "#ccaa00"
            else:
                level_text = level
                level_color = "#00cc66"
            level_item = QTableWidgetItem(level_text)
            level_item.setForeground(QColor(level_color))
            self.paint_list_table.setItem(row, 6, level_item)
            self.paint_list_table.setRowHeight(row, 34)

        total = len(entries)
        self._paints_total_lbl.setText(f"Unique paints: {total}")
        self._paints_missing_lbl.setText(f"Out of stock: {out_count}")
        self._paints_low_lbl.setText(f"Low stock: {low_count}")
        self._paints_direct_lbl.setText(f"Direct links: {direct_count}")
        self._paints_model_lbl.setText(f"Via model: {model_count}")

    def _emit_refresh_paints(self):
        if self._current_army_id:
            self.context.event_bus.emit("army_paints_refresh_requested", {
                "id": self._current_army_id
            })

    def _on_tab_changed(self, index: int):
        """Auto-refresh the Army Paints tab whenever it becomes active."""
        _PAINTS_TAB = 2   # My Lists=0, Builder=1, Army Paints=2, Statistics=3
        if index == _PAINTS_TAB:
            self._emit_refresh_paints()

    def _build_stats_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._stats_layout = QVBoxLayout(content)
        self._stats_layout.setSpacing(12)
        self._stats_layout.setContentsMargins(2, 2, 2, 2)

        self._stats_placeholder = QLabel("No data yet — create some army lists to see statistics.")
        self._stats_placeholder.setAlignment(Qt.AlignCenter)
        self._stats_placeholder.setObjectName("fieldLabel")
        self._stats_layout.addWidget(self._stats_placeholder)
        self._stats_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)
        return tab

    # ============================================================
    # SIGNAL CONNECTIONS
    # ============================================================

    def _connect_signals(self):
        # My Lists tab
        self._create_army_btn.clicked.connect(self._emit_create_army)
        self._open_builder_btn.clicked.connect(self._emit_open_army)
        self._duplicate_btn.clicked.connect(self._emit_duplicate_army)
        self._delete_army_btn.clicked.connect(self._emit_delete_army)
        self.list_search.textChanged.connect(self._emit_army_filter)
        self.list_filter_system.currentTextChanged.connect(self._emit_army_filter)
        self.list_filter_faction.currentTextChanged.connect(self._emit_army_filter)
        self._clear_list_filter_btn.clicked.connect(self._clear_list_filters)
        self.army_table.horizontalHeader().sectionClicked.connect(self._on_list_header_clicked)
        self.army_table.itemDoubleClicked.connect(lambda _: self._emit_open_army())

        # New army form — auto-populate format + points when system changes
        self.new_system_combo.currentTextChanged.connect(self._on_new_system_changed)
        self.new_format_combo.currentTextChanged.connect(self._on_new_format_changed)

        # Unit pts live total
        self.unit_qty_spin.valueChanged.connect(self._update_unit_pts_total)
        self.unit_pts_spin.valueChanged.connect(self._update_unit_pts_total)

        # Builder tab
        self._save_header_btn.clicked.connect(self._emit_update_army_header)
        self._export_btn.clicked.connect(self._emit_export)
        self._close_builder_btn.clicked.connect(self._close_builder)
        self._add_unit_btn.clicked.connect(self._emit_add_unit)
        self._update_unit_btn.clicked.connect(self._emit_update_unit)
        self._cancel_edit_btn.clicked.connect(self._cancel_unit_edit)
        self._edit_unit_btn.clicked.connect(self._load_unit_into_form)
        self._duplicate_unit_btn.clicked.connect(self._emit_duplicate_unit)
        self._remove_unit_btn.clicked.connect(self._emit_remove_unit)
        self.roster_tree.currentItemChanged.connect(self._on_roster_selection_changed)
        self.roster_tree.itemDoubleClicked.connect(lambda _item, _col: self._load_unit_into_form())
        self.builder_system_combo.currentTextChanged.connect(self._on_builder_system_changed)
        self.builder_format_combo.currentTextChanged.connect(self._on_builder_format_changed)
        self._move_up_btn.clicked.connect(lambda: self._emit_move_unit(-1))
        self._move_down_btn.clicked.connect(lambda: self._emit_move_unit(1))

        # Auto-refresh Army Paints tab when it becomes visible
        self._tabs.currentChanged.connect(self._on_tab_changed)

    # ============================================================
    # MY LISTS — EMIT EVENTS
    # ============================================================

    def _emit_create_army(self):
        name = self.new_name_input.text().strip()
        game_system = self.new_system_combo.currentText().strip()
        faction = self.new_faction_input.text().strip()
        fmt = self.new_format_combo.currentText().strip()

        errors = []
        if not name:
            errors.append("List name required")
        if not game_system:
            errors.append("Game system required")
        if not faction:
            errors.append("Faction required")
        if not fmt:
            errors.append("Format required")

        if errors:
            self.show_create_error(" · ".join(errors))
            return

        self.context.event_bus.emit("army_create_requested", {
            "name": name,
            "game_system": game_system,
            "faction": faction,
            "format": fmt,
            "points_limit": self.new_points_spin.value(),
        })

    def _emit_open_army(self):
        army_id = self._get_selected_army_id()
        if army_id is None:
            return
        self.context.event_bus.emit("army_open_requested", {"id": army_id})

    def _emit_duplicate_army(self):
        army_id = self._get_selected_army_id()
        if army_id is None:
            return
        self.context.event_bus.emit("army_duplicate_requested", {"id": army_id})

    def _emit_delete_army(self):
        army_id = self._get_selected_army_id()
        if army_id is None:
            return
        reply = QMessageBox.question(
            self, "Delete List",
            "Delete this army list and all its units? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.context.event_bus.emit("army_delete_requested", {"id": army_id})

    def _emit_army_filter(self):
        f = ArmyFilter(
            search_text=self.list_search.text().strip() or None,
            game_system=self._combo_val(self.list_filter_system),
            faction=self._combo_val(self.list_filter_faction),
            sort_by=self._current_filter.sort_by,
            sort_desc=self._current_filter.sort_desc,
        )
        self._current_filter = f
        self.context.event_bus.emit("armies_filter_changed", {"filter": f})

    def _clear_list_filters(self):
        for w in [self.list_search, self.list_filter_system, self.list_filter_faction]:
            with QSignalBlocker(w):
                if isinstance(w, QLineEdit):
                    w.clear()
                elif isinstance(w, QComboBox):
                    w.setCurrentIndex(0)
        self._current_filter = ArmyFilter()
        self.context.event_bus.emit("armies_filter_changed", {"filter": self._current_filter})

    # ============================================================
    # BUILDER — EMIT EVENTS
    # ============================================================

    def _emit_update_army_header(self):
        if self._current_army_id is None:
            return
        self.context.event_bus.emit("army_update_requested", {
            "id": self._current_army_id,
            "name": self.builder_name_input.text().strip(),
            "game_system": self.builder_system_combo.currentText().strip(),
            "faction": self.builder_faction_input.text().strip(),
            "format": self.builder_format_combo.currentText().strip(),
            "points_limit": self.builder_points_limit.value(),
            "notes": self.builder_notes_input.text().strip() or None,
        })

    def _emit_export(self):
        if self._current_army_id is None:
            return
        self.context.event_bus.emit("army_export_requested", {"id": self._current_army_id})

    def _close_builder(self):
        self._current_army_id = None
        self._builder_header.setVisible(False)
        self._army_projects_section.setVisible(False)
        self._builder_splitter.setVisible(False)
        self._builder_placeholder.setVisible(True)

    def _emit_add_unit(self):
        if self._current_army_id is None:
            self.show_unit_error("No list open")
            return

        data = self._read_unit_form()
        if data is None:
            return
        data["army_id"] = self._current_army_id
        data["sort_order"] = self._unit_sort_order
        self.context.event_bus.emit("unit_add_requested", data)

    def _emit_update_unit(self):
        if self._editing_unit_id is None:
            return
        data = self._read_unit_form()
        if data is None:
            return
        data["id"] = self._editing_unit_id
        self.context.event_bus.emit("unit_update_requested", data)

    def _emit_remove_unit(self):
        unit_id = self._get_selected_unit_id()
        if unit_id is None:
            self._roster_status.setText("No unit selected")
            return
        reply = QMessageBox.question(
            self, "Remove Unit",
            "Remove this unit from the list?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.context.event_bus.emit("unit_remove_requested", {"id": unit_id})

    def _emit_duplicate_unit(self):
        """Duplicate the selected unit in the roster."""
        unit_id = self._get_selected_unit_id()
        if unit_id is None:
            return
        self.context.event_bus.emit("unit_duplicate_requested", {"id": unit_id})

    def eventFilter(self, obj, event):
        """Handle Delete key on the roster tree."""
        if obj is self.roster_tree and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Delete:
                self._emit_remove_unit()
                return True
        return super().eventFilter(obj, event)

    def _emit_move_unit(self, direction: int):
        """Reorder a unit within its role group (direction: -1 = up, +1 = down)."""
        unit_id = self._get_selected_unit_id()
        if unit_id is None:
            return
        self.context.event_bus.emit("unit_reorder_requested", {
            "id": unit_id,
            "direction": direction,
        })

    # ============================================================
    # DATA DISPLAY — called by plugin
    # ============================================================

    def display_armies(
        self,
        armies: list,
        points_totals: dict[int, int] | None = None,
        unit_counts: dict[int, int] | None = None,
        game_systems: list[str] | None = None,
        factions: list[str] | None = None,
    ):
        """Populate the My Lists table."""
        self._refresh_list_dropdowns(game_systems, factions)
        points_totals = points_totals or {}
        unit_counts = unit_counts or {}

        self.army_table.setRowCount(0)
        for army in armies:
            row = self.army_table.rowCount()
            self.army_table.insertRow(row)

            name_item = QTableWidgetItem(army.name)
            name_item.setData(Qt.UserRole, army.id)
            self.army_table.setItem(row, 0, name_item)
            self.army_table.setItem(row, 1, QTableWidgetItem(army.game_system))
            self.army_table.setItem(row, 2, QTableWidgetItem(army.faction))
            self.army_table.setItem(row, 3, QTableWidgetItem(army.format))

            limit_str = str(army.points_limit) if army.points_limit > 0 else "∞"
            self.army_table.setItem(row, 4, QTableWidgetItem(limit_str))

            count_item = QTableWidgetItem(str(unit_counts.get(army.id, 0)))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.army_table.setItem(row, 5, count_item)

            pts = points_totals.get(army.id, 0)
            pts_item = QTableWidgetItem(_fmt_pts(pts) if pts > 0 else "—")
            pts_item.setTextAlignment(Qt.AlignCenter)
            # Color code: over limit = red
            if army.points_limit > 0 and pts > army.points_limit:
                pts_item.setForeground(QColor("#cc3333"))
            self.army_table.setItem(row, 6, pts_item)

        count = len(armies)
        self._list_count_label.setText(f"{count} list{'s' if count != 1 else ''}")
        # Show empty state when no armies, table when populated
        self._lists_stack.setCurrentIndex(1 if not armies else 0)

    def load_army_into_builder(self, army, units: list):
        """
        Open an army in the Builder tab.
        Called by the plugin after army_open_requested is handled.
        """
        self._current_army_id = army.id
        self._editing_unit_id = None
        self._unit_sort_order = max((u.sort_order for u in units), default=0) + 1

        # Show builder widgets
        self._builder_placeholder.setVisible(False)
        self._builder_header.setVisible(True)
        self._army_projects_section.setVisible(True)
        self._builder_splitter.setVisible(True)

        # Populate header fields
        with QSignalBlocker(self.builder_system_combo):
            idx = self.builder_system_combo.findText(army.game_system)
            if idx >= 0:
                self.builder_system_combo.setCurrentIndex(idx)
            else:
                self.builder_system_combo.setCurrentText(army.game_system)

        with QSignalBlocker(self.builder_format_combo):
            self._populate_format_combo(self.builder_format_combo, army.game_system, army.format)

        self.builder_name_input.setText(army.name)
        self.builder_faction_input.setText(army.faction)
        self.builder_points_limit.setValue(army.points_limit)
        self.builder_notes_input.setText(army.notes or "")

        # Populate role combo for unit form
        self._populate_role_combo(army.game_system)

        # Populate model link combo
        self._populate_model_combo()

        # Rebuild roster
        self.refresh_builder_units(units, army.points_limit)

        # Populate "Used in Projects" back-link
        self._refresh_army_projects(army.id)

        # Switch to builder tab
        self._tabs.setCurrentIndex(1)

    def refresh_builder_units(self, units: list, points_limit: int = 0):
        """Rebuild the roster tree from a fresh unit list."""
        if self._current_army_id is None:
            return

        self._unit_sort_order = max((u.sort_order for u in units), default=0) + 1

        total_pts = sum(u.total_points for u in units)
        self._update_points_bar(total_pts, points_limit)
        self._rebuild_roster_tree(units)

    def update_statistics(self, stats: ArmyStatistics):
        self._rebuild_stats_tab(stats)

    def _refresh_army_projects(self, army_id: int) -> None:
        """Populate the 'Used in Projects' RelatedItemsSection for the given army."""
        proj_svc = self.context.services.try_get("project_service")
        if proj_svc is None:
            self._army_projects_section.set_empty("Project Tracker not available.")
            return
        try:
            projects = proj_svc.get_projects_for_entity("army", army_id)
        except Exception as e:
            print(f"[ARMY UI] _refresh_army_projects: {e}")
            self._army_projects_section.set_empty("Could not load projects.")
            return

        if not projects:
            self._army_projects_section.set_empty("Not linked to any project.")
            return

        chips = []
        for p in projects:
            chip = LinkedEntityChip(
                plugin_id="project_tracker",
                entity_id=getattr(p, "id", 0),
                icon=getattr(p, "icon", "📁"),
                name=getattr(p, "name", "Project"),
                subtitle=getattr(p, "game_system", ""),
                dot_color=getattr(p, "color", ""),
                show_navigate=True,
                show_unlink=False,
            )
            chip.navigate_requested.connect(
                lambda pid, _eid: self._emit_navigate(pid)
            )
            chips.append(chip)
        self._army_projects_section.set_chips(chips)

    def _emit_navigate(self, plugin_id: str) -> None:
        bus = getattr(self.context, "event_bus", None)
        if bus:
            try:
                bus.emit("dashboard_navigate", {"plugin_id": plugin_id})
            except Exception:
                pass

    def clear_new_army_form(self):
        self.new_name_input.clear()
        self.new_system_combo.setCurrentIndex(0)
        self.new_faction_input.clear()
        self.new_format_combo.clear()
        self.new_points_spin.setValue(0)
        self._new_form_status.setText("")

    # ============================================================
    # ROSTER TREE
    # ============================================================

    def _rebuild_roster_tree(self, units: list):
        self.roster_tree.clear()

        if not units:
            placeholder = QTreeWidgetItem(["No units yet — add one using the form →"])
            placeholder.setForeground(0, QColor("#888"))
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
            self.roster_tree.addTopLevelItem(placeholder)
            self._roster_status.setText("0 units")
            return

        # Group by role, preserving sort_order within each role
        grouped: dict[str, list] = {}
        for u in sorted(units, key=lambda x: (x.unit_role, x.sort_order, x.unit_name)):
            grouped.setdefault(u.unit_role, []).append(u)

        # Determine role display order
        game_system = self.builder_system_combo.currentText()
        ordered_roles = get_roles_for_system(game_system)
        known_order = [r for r in ordered_roles if r in grouped]
        extra = [r for r in grouped if r not in ordered_roles]

        bold = QFont()
        bold.setBold(True)

        for role in known_order + extra:
            role_units = grouped[role]
            role_pts = sum(u.total_points for u in role_units)
            pts_label = f"  [{_fmt_pts(role_pts)}pts]" if role_pts > 0 else ""

            role_item = QTreeWidgetItem([
                f"{role}{pts_label}",
                str(len(role_units)),
                _fmt_pts(role_pts) if role_pts > 0 else "—",
            ])
            role_item.setFont(0, bold)
            role_item.setForeground(0, QColor("#aaddff"))
            role_item.setFlags(role_item.flags() & ~Qt.ItemIsSelectable)
            role_item.setData(0, Qt.UserRole, None)  # role header, no unit id

            for u in role_units:
                qty_str = f"×{u.quantity}" if u.quantity > 1 else "×1"
                unit_total = u.total_points
                if unit_total == 0:
                    pts_display = "Free"
                elif u.quantity > 1:
                    pts_display = f"{_fmt_pts(u.points_cost)} ea = {_fmt_pts(unit_total)}"
                else:
                    pts_display = _fmt_pts(unit_total)
                unit_item = QTreeWidgetItem([
                    u.unit_name,
                    qty_str,
                    pts_display,
                ])
                unit_item.setData(0, Qt.UserRole, u.id)

                if u.wargear_notes:
                    tip = u.wargear_notes[:120] + ("…" if len(u.wargear_notes) > 120 else "")
                    unit_item.setToolTip(0, tip)

                if u.model_id:
                    unit_item.setForeground(0, QColor("#aaffaa"))
                    unit_item.setToolTip(2, "Linked to Model Tracker")

                role_item.addChild(unit_item)

            role_item.setExpanded(True)
            self.roster_tree.addTopLevelItem(role_item)

        total_units = len(units)
        self._roster_status.setText(f"{total_units} unit entr{'ies' if total_units != 1 else 'y'}")

    # ============================================================
    # POINTS BAR
    # ============================================================

    def _update_points_bar(self, total: float, limit: float):
        total_str = _fmt_pts(total)
        if limit == 0:
            self._points_bar.setVisible(False)
            self._points_label.setText(f"Points: {total_str}  ·  no limit")
            self._points_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #909090;")
            return

        limit_str = _fmt_pts(limit)
        # QProgressBar only handles integers — scale to 1 decimal place resolution
        scale = 10
        self._points_bar.setMaximum(int(max(limit, total) * scale))
        self._points_bar.setValue(int(total * scale))
        self._points_bar.setVisible(True)
        pct = total / limit

        if total > limit:
            chunk_color = "#e05555"
            label_color = "#e05555"
            status = f"OVER by {_fmt_pts(total - limit)}"
        elif pct >= 0.95:
            chunk_color = "#e07800"
            label_color = "#e07800"
            status = f"{_fmt_pts(limit - total)} remaining"
        else:
            chunk_color = "#00bb55"
            label_color = "#d8d8d8"
            status = f"{_fmt_pts(limit - total)} remaining"

        self._points_bar.setStyleSheet(
            f"QProgressBar {{ background:#2a2a2a; border:1px solid #363636; border-radius:3px; }}"
            f"QProgressBar::chunk {{ background:{chunk_color}; border-radius:3px; }}"
        )
        self._points_label.setText(f"Points: {total_str} / {limit_str}  ·  {status}")
        self._points_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {label_color};")

    # ============================================================
    # UNIT FORM HELPERS
    # ============================================================

    def _read_unit_form(self) -> dict | None:
        name = self.unit_name_input.text().strip()
        role = self.unit_role_combo.currentText().strip()
        if not name:
            self.show_unit_error("Unit name required")
            return None
        if not role:
            self.show_unit_error("Unit role required")
            return None

        model_id = self.unit_model_combo.currentData()

        return {
            "unit_name": name,
            "unit_role": role,
            "points_cost": self.unit_pts_spin.value(),
            "quantity": self.unit_qty_spin.value(),
            "wargear_notes": self.unit_wargear_input.toPlainText().strip() or None,
            "model_id": model_id,
            "linked_paint_ids": list(self._unit_linked_paint_ids),
        }

    def populate_unit_form(self, unit):
        """Load a unit into the form for editing."""
        self._editing_unit_id = unit.id
        self.unit_name_input.setText(unit.unit_name)

        idx = self.unit_role_combo.findText(unit.unit_role)
        if idx >= 0:
            self.unit_role_combo.setCurrentIndex(idx)
        else:
            self.unit_role_combo.setCurrentText(unit.unit_role)

        self.unit_qty_spin.setValue(unit.quantity)
        self.unit_pts_spin.setValue(unit.points_cost)
        self._update_unit_pts_total()
        self.unit_wargear_input.setPlainText(unit.wargear_notes or "")

        # Set model combo
        if unit.model_id is not None:
            for i in range(self.unit_model_combo.count()):
                if self.unit_model_combo.itemData(i) == unit.model_id:
                    self.unit_model_combo.setCurrentIndex(i)
                    break
        else:
            self.unit_model_combo.setCurrentIndex(0)

        # Set linked paints
        self._unit_linked_paint_ids = list(getattr(unit, "linked_paint_ids", []))
        self._update_unit_paints_label()

        self._add_unit_btn.setVisible(False)
        self._update_unit_btn.setVisible(True)
        self._cancel_edit_btn.setVisible(True)
        self._unit_form_status.setText("")

    def _cancel_unit_edit(self):
        self._editing_unit_id = None
        self._unit_linked_paint_ids = []
        self.unit_name_input.clear()
        self.unit_role_combo.setCurrentIndex(0)
        self.unit_qty_spin.setValue(1)
        self.unit_pts_spin.setValue(0)
        self.unit_wargear_input.clear()
        self.unit_model_combo.setCurrentIndex(0)
        self._update_unit_paints_label()
        self._add_unit_btn.setVisible(True)
        self._update_unit_btn.setVisible(False)
        self._cancel_edit_btn.setVisible(False)
        self._unit_form_status.setText("")

    def _load_unit_into_form(self):
        unit_id = self._get_selected_unit_id()
        if unit_id is None:
            self._roster_status.setText("Select a unit first")
            return
        self.context.event_bus.emit("unit_edit_requested", {"id": unit_id})

    def _populate_role_combo(self, game_system: str):
        roles = get_roles_for_system(game_system)
        current = self.unit_role_combo.currentText()
        with QSignalBlocker(self.unit_role_combo):
            self.unit_role_combo.clear()
            self.unit_role_combo.addItems(roles)
            idx = self.unit_role_combo.findText(current)
            if idx >= 0:
                self.unit_role_combo.setCurrentIndex(idx)

    def _populate_format_combo(self, combo: QComboBox, game_system: str, current_fmt: str = ""):
        formats = get_formats_for_system(game_system)
        with QSignalBlocker(combo):
            combo.clear()
            combo.addItems(formats)
            idx = combo.findText(current_fmt)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif current_fmt:
                combo.setCurrentText(current_fmt)

    def _populate_model_combo(self):
        """Populate the model link combo from model_tracker if loaded."""
        with QSignalBlocker(self.unit_model_combo):
            self.unit_model_combo.clear()
            self.unit_model_combo.addItem("— None —", None)

        model_service = self.context.services.try_get("model_service")
        if not model_service:
            return

        try:
            models = model_service.get_all_models()
            for m in models:
                label = f"{m.name}  ({m.game_system})"
                self.unit_model_combo.addItem(label, m.id)
        except Exception as e:
            print(f"[ARMY BUILDER UI] Could not load models: {e}")

    def _open_paint_link_dialog(self):
        dialog = PaintLinkDialog(self.context, self._unit_linked_paint_ids, parent=self)
        if dialog.exec():
            self._unit_linked_paint_ids = dialog.get_selected_ids()
            self._update_unit_paints_label()

    def _update_unit_paints_label(self):
        count = len(self._unit_linked_paint_ids)
        if count == 0:
            self._unit_paints_label.setText("None")
        else:
            self._unit_paints_label.setText(f"{count} paint{'s' if count != 1 else ''} linked")

    def _update_unit_pts_total(self):
        cost = self.unit_pts_spin.value()
        qty = self.unit_qty_spin.value()
        total = cost * qty
        if total == 0:
            self._unit_pts_total_lbl.setText("= Free")
        else:
            self._unit_pts_total_lbl.setText(f"= {_fmt_pts(total)} pts")

    # ============================================================
    # FILTER DROPDOWN REFRESH
    # ============================================================

    def _refresh_list_dropdowns(self, game_systems: list[str] | None, factions: list[str] | None):
        def _refresh(combo: QComboBox, options: list[str], current: str):
            with QSignalBlocker(combo):
                combo.clear()
                combo.addItem("All")
                combo.addItems(options or [])
                idx = combo.findText(current)
                combo.setCurrentIndex(idx if idx >= 0 else 0)

        _refresh(self.list_filter_system, game_systems or [], self._combo_val(self.list_filter_system) or "")
        _refresh(self.list_filter_faction, factions or [], self._combo_val(self.list_filter_faction) or "")

    # ============================================================
    # GAME SYSTEM CHANGE HANDLERS
    # ============================================================

    def _on_new_system_changed(self, system: str):
        self._populate_format_combo(self.new_format_combo, system, "")

    def _on_new_format_changed(self, fmt: str):
        pts = parse_points_limit(fmt)
        if pts > 0:
            with QSignalBlocker(self.new_points_spin):
                self.new_points_spin.setValue(pts)

    def _on_builder_system_changed(self, system: str):
        self._populate_role_combo(system)
        self._populate_format_combo(
            self.builder_format_combo,
            system,
            self.builder_format_combo.currentText(),
        )

    def _on_builder_format_changed(self, fmt: str):
        pts = parse_points_limit(fmt)
        if pts > 0:
            with QSignalBlocker(self.builder_points_limit):
                self.builder_points_limit.setValue(pts)

    # ============================================================
    # TABLE / TREE SELECTION
    # ============================================================

    def _get_selected_army_id(self) -> int | None:
        rows = self.army_table.selectedItems()
        if not rows:
            return None
        item = self.army_table.item(self.army_table.currentRow(), 0)
        return item.data(Qt.UserRole) if item else None

    def _get_selected_unit_id(self) -> int | None:
        item = self.roster_tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.UserRole)  # None for role headers

    def _on_roster_selection_changed(self, current, _previous):
        unit_id = self._get_selected_unit_id()
        has_unit = unit_id is not None
        self._edit_unit_btn.setEnabled(has_unit)
        self._duplicate_unit_btn.setEnabled(has_unit)
        self._remove_unit_btn.setEnabled(has_unit)
        self._move_up_btn.setEnabled(has_unit)
        self._move_down_btn.setEnabled(has_unit)

    def _on_list_header_clicked(self, col: int):
        field = self.LIST_SORT_MAP.get(col)
        if not field:
            return
        if self._current_filter.sort_by == field:
            self._current_filter.sort_desc = not self._current_filter.sort_desc
        else:
            self._current_filter.sort_by = field
            self._current_filter.sort_desc = False
        hdr = self.army_table.horizontalHeader()
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(
            col,
            Qt.DescendingOrder if self._current_filter.sort_desc else Qt.AscendingOrder,
        )
        self.context.event_bus.emit("armies_filter_changed", {"filter": self._current_filter})

    # ============================================================
    # STATISTICS TAB
    # ============================================================

    def _rebuild_stats_tab(self, stats: ArmyStatistics):
        while self._stats_layout.count():
            child = self._stats_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if stats.total_armies == 0:
            lbl = QLabel("No data yet — create some army lists to see statistics.")
            lbl.setAlignment(Qt.AlignCenter)
            self._stats_layout.addWidget(lbl)
            self._stats_layout.addStretch()
            return

        self._stats_layout.addWidget(self._make_stat_box("Overview", {
            "Total Lists": str(stats.total_armies),
            "Total Unit Entries": str(stats.total_units),
            "Avg Points per List": f"{stats.average_points:.0f}pts",
            "Largest List": f"{stats.largest_army_name} ({stats.largest_army_points}pts)",
        }))

        self._stats_layout.addWidget(self._make_dist_box(
            "Lists by Game System",
            stats.game_system_distribution,
        ))

        self._stats_layout.addWidget(self._make_dist_box(
            "Lists by Faction / Warband",
            stats.faction_distribution,
        ))

        self._stats_layout.addStretch()

    def _make_stat_box(self, title: str, data: dict) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setSpacing(6)
        for k, v in data.items():
            row = QHBoxLayout()
            k_lbl = QLabel(k); k_lbl.setObjectName("fieldLabel")
            v_lbl = QLabel(v); v_lbl.setStyleSheet("font-weight: 700; color: #f0f0f0;")
            row.addWidget(k_lbl)
            row.addStretch()
            row.addWidget(v_lbl)
            layout.addLayout(row)
        return box

    def _make_dist_box(self, title: str, distribution: dict[str, int]) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setSpacing(5)
        if not distribution:
            lbl = QLabel("No data"); lbl.setObjectName("fieldLabel"); layout.addWidget(lbl)
            return box
        total = sum(distribution.values())
        for label, count in sorted(distribution.items(), key=lambda x: x[1], reverse=True):
            row = QHBoxLayout(); row.setSpacing(8)
            lbl = QLabel(label); lbl.setMinimumWidth(180)
            cnt = QLabel(f"{count}"); cnt.setObjectName("fieldLabel"); cnt.setMinimumWidth(28)
            bar = QProgressBar()
            bar.setRange(0, total); bar.setValue(count)
            bar.setTextVisible(False); bar.setMaximumHeight(8)
            row.addWidget(lbl)
            row.addWidget(cnt)
            row.addWidget(bar, stretch=1)
            layout.addLayout(row)
        return box

    # ============================================================
    # STATUS MESSAGES
    # ============================================================

    def show_create_success(self, msg: str):
        self._set_label_status(self._new_form_status, f"✓  {msg}", "formStatusOk", 4000)

    def show_create_error(self, msg: str):
        self._set_label_status(self._new_form_status, f"✗  {msg}", "formStatusErr", 5000)

    def show_unit_success(self, msg: str):
        self._set_label_status(self._unit_form_status, f"✓  {msg}", "formStatusOk", 4000)

    def show_unit_error(self, msg: str):
        self._set_label_status(self._unit_form_status, f"✗  {msg}", "formStatusErr", 5000)

    @staticmethod
    def _set_label_status(lbl: QLabel, text: str, obj_name: str, duration_ms: int) -> None:
        """Set status label text with themed objectName, then auto-clear after duration_ms."""
        from PySide6.QtCore import QTimer
        lbl.setObjectName(obj_name)
        lbl.style().unpolish(lbl)
        lbl.style().polish(lbl)
        lbl.setText(text)
        QTimer.singleShot(duration_ms, lambda: lbl.setText(""))

    def show_export_dialog(self, text: str):
        ExportDialog(text, parent=self).exec()

    # ============================================================
    # UTILITY
    # ============================================================

    @staticmethod
    def _combo_val(combo: QComboBox) -> str | None:
        val = combo.currentText().strip()
        return val if val and val != "All" else None
