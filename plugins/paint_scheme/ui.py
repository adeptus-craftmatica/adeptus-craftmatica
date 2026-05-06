"""
Paint Scheme UI — polished two-pane layout.

Left pane  : title + search + filter + scheme list + action buttons
Right pane : scrollable detail — header fields, step cards, linked models
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QListWidget, QListWidgetItem, QDialog, QDialogButtonBox,
    QFrame, QScrollArea, QTextEdit, QSizePolicy, QSplitter, QGroupBox,
    QMessageBox, QSpacerItem, QTabWidget,
)

from .models import TECHNIQUES, SchemeFilter
from plugins.shared_widgets import RelatedItemsSection, LinkedEntityChip

try:
    from .chroma_ui import ChromaCodexWidget as _ChromaCodexWidget
    _CHROMA_AVAILABLE = True
except Exception as _chroma_import_err:
    import traceback as _tb
    print(f"[PAINT SCHEME] Chroma Codex failed to import: {_chroma_import_err}")
    _tb.print_exc()
    _CHROMA_AVAILABLE = False
    _ChromaCodexWidget = None

COMMON_GAME_SYSTEMS = [
    "",
    "Warhammer 40,000",
    "Warhammer: Age of Sigmar",
    "Warhammer: The Old World",
    "Horus Heresy",
    "Kill Team",
    "Necromunda",
    "Middle Earth Strategy Battle Game",
    "Dungeons & Dragons",
    "Pathfinder",
    "Gundam",
    "Star Wars: Legion",
    "Marvel Crisis Protocol",
    "Bolt Action",
    "Other",
]

TECHNIQUE_COLOURS: dict[str, str] = {
    "Primer":                 "#555566",
    "Basecoat":               "#2d3250",
    "Layer":                  "#1a4f7a",
    "Wash / Shade":           "#4a235a",
    "Drybrush":               "#7d4010",
    "Edge Highlight":         "#1a5f8a",
    "Highlight":              "#1a5f8a",
    "Glaze":                  "#0d5e4e",
    "Contrast / Speed Paint": "#0d5e4e",
    "Technical":              "#1a6635",
    "Varnish":                "#856400",
    "Basing":                 "#6b3010",
    "Other":                  "#444444",
}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _hline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    return f

def _vline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine); f.setFixedWidth(1)
    return f

def _field_label(text: str) -> QLabel:
    lbl = QLabel(text); lbl.setObjectName("fieldLabel")
    return lbl

def _colour_swatch(hex_colour: str | None, size: int = 18) -> QLabel:
    lbl = QLabel(); lbl.setFixedSize(size, size)
    c = hex_colour if (hex_colour and hex_colour.startswith("#") and len(hex_colour) == 7) else "#3a3a3a"
    bright = QColor(c).lightness()
    border = "rgba(255,255,255,0.14)" if bright < 100 else "rgba(0,0,0,0.20)"
    lbl.setStyleSheet(
        f"background:{c}; border:1px solid {border}; border-radius:3px;"
    )
    lbl.setToolTip(c)
    return lbl

def _technique_badge(technique: str) -> QLabel:
    colour = TECHNIQUE_COLOURS.get(technique, "#444444")
    lbl = QLabel(technique)
    lbl.setStyleSheet(
        f"background:{colour}; color:#e8e8e8; border-radius:4px;"
        f" padding:2px 8px; font-size:11px; font-weight:600;"
    )
    lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return lbl


# ── Step Dialog ───────────────────────────────────────────────────────────────

class StepDialog(QDialog):
    def __init__(self, parent, context, scheme_id: int, step=None):
        super().__init__(parent)
        self.context    = context
        self.scheme_id  = scheme_id
        self.step       = step
        self._paints: list = []
        self.setWindowTitle("Edit Step" if step else "Add Step")
        self.setMinimumWidth(500)
        self.setModal(True)
        self._build_ui()
        self._load_paints()
        if step:
            self._populate(step)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(18, 16, 18, 16)

        lay.addWidget(_field_label("Technique"))
        self.technique_combo = QComboBox()
        self.technique_combo.addItems(TECHNIQUES)
        lay.addWidget(self.technique_combo)

        lay.addWidget(_field_label("Paint  (optional — search to filter)"))
        self.paint_search = QLineEdit()
        self.paint_search.setPlaceholderText("Type to filter paints…")
        self.paint_search.textChanged.connect(self._filter_paint_list)
        lay.addWidget(self.paint_search)

        self.paint_list = QListWidget()
        self.paint_list.setFixedHeight(170)
        self.paint_list.setAlternatingRowColors(True)
        lay.addWidget(self.paint_list)

        self.manual_name_input = QLineEdit()
        self.manual_name_input.setPlaceholderText("Paint name (manual entry)")
        self.manual_name_input.setVisible(False)
        lay.addWidget(self.manual_name_input)

        lay.addWidget(_field_label("Step Notes"))
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("e.g. Two thin coats, focus on recesses…")
        lay.addWidget(self.notes_input)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _load_paints(self):
        paint_svc = self.context.services.try_get("paint_service")
        if paint_svc is None:
            self.paint_list.setVisible(False)
            self.paint_search.setVisible(False)
            self.manual_name_input.setVisible(True)
            return
        try:
            self._paints = paint_svc.get_all_paints()
        except Exception as e:
            print(f"[SCHEME UI] Failed to load paints: {e}")
            self._paints = []
        self._populate_paint_list(self._paints)

    def _populate_paint_list(self, paints: list):
        self.paint_list.clear()
        blank = QListWidgetItem("  — No paint selected —")
        blank.setData(Qt.UserRole, None)
        self.paint_list.addItem(blank)
        for p in paints:
            item = QListWidgetItem(f"  {p.brand}  —  {p.name}   [{p.paint_type}]")
            item.setData(Qt.UserRole, p.id)
            item.setData(Qt.UserRole + 1, getattr(p, "color", None))
            if getattr(p, "color", None) and p.color.startswith("#"):
                qc = QColor(p.color)
                brightness = (qc.red() * 299 + qc.green() * 587 + qc.blue() * 114) / 1000
                item.setBackground(qc)
                item.setForeground(QColor("#000" if brightness > 128 else "#fff"))
            self.paint_list.addItem(item)

    def _filter_paint_list(self, text: str):
        needle = text.strip().lower()
        filtered = [
            p for p in self._paints
            if needle in p.name.lower() or needle in p.brand.lower()
        ] if needle else self._paints
        self._populate_paint_list(filtered)

    def _populate(self, step):
        idx = self.technique_combo.findText(step.technique)
        if idx >= 0: self.technique_combo.setCurrentIndex(idx)
        self.notes_input.setText(step.notes or "")
        if step.paint_id is not None:
            for i in range(self.paint_list.count()):
                if self.paint_list.item(i).data(Qt.UserRole) == step.paint_id:
                    self.paint_list.setCurrentRow(i); break
        else:
            self.paint_list.setCurrentRow(0)
            if self.manual_name_input.isVisible():
                self.manual_name_input.setText(step.paint_name or "")

    def get_technique(self) -> str:
        return self.technique_combo.currentText()

    def get_paint_id(self):
        item = self.paint_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def get_paint_name(self) -> str:
        if self.manual_name_input.isVisible():
            return self.manual_name_input.text().strip()
        item = self.paint_list.currentItem()
        if item and item.data(Qt.UserRole) is not None:
            txt = item.text().strip()
            return txt[:txt.rfind("[")].strip() if "[" in txt else txt
        return ""

    def get_notes(self) -> str:
        return self.notes_input.text().strip()


# ── Model Picker Dialog ───────────────────────────────────────────────────────

class ModelPickerDialog(QDialog):
    def __init__(self, parent, context, already_linked: list[int]):
        super().__init__(parent)
        self.context        = context
        self.already_linked = set(already_linked)
        self._models: list  = []
        self.selected_model_id: int | None = None
        self.setWindowTitle("Link a Model")
        self.setMinimumWidth(440)
        self.setModal(True)
        self._build_ui()
        self._load_models()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.addWidget(_field_label("Select a model to link to this scheme:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter models…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.model_list = QListWidget()
        self.model_list.setMinimumHeight(200)
        self.model_list.setAlternatingRowColors(True)
        lay.addWidget(self.model_list)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _load_models(self):
        model_svc = self.context.services.try_get("model_service")
        if model_svc is None:
            self.model_list.addItem("Model Tracker not loaded")
            return
        try:
            from plugins.model_tracker.models import ModelFilter
            self._models = model_svc.search_models(ModelFilter())
        except Exception:
            try: self._models = model_svc.get_all_models()
            except Exception as e:
                print(f"[SCHEME UI] Model load error: {e}")
        self._populate(self._models)

    def _populate(self, models: list):
        self.model_list.clear()
        for m in models:
            if m.id in self.already_linked: continue
            parts = [x for x in [getattr(m, "faction", ""), getattr(m, "game_system", "")] if x]
            label = f"{m.name}  ·  {' / '.join(parts)}" if parts else m.name
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole, m.id)
            self.model_list.addItem(item)

    def _filter(self, text: str):
        needle = text.strip().lower()
        self._populate([
            m for m in self._models
            if not needle
            or needle in m.name.lower()
            or needle in getattr(m, "faction", "").lower()
            or needle in getattr(m, "game_system", "").lower()
        ])

    def _on_accept(self):
        item = self.model_list.currentItem()
        if item: self.selected_model_id = item.data(Qt.UserRole)
        self.accept()


# ── Step Card ─────────────────────────────────────────────────────────────────

class StepCard(QFrame):
    def __init__(self, step, paint_colour: str | None,
                 on_edit, on_delete, on_move_up, on_move_down, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build(step, paint_colour, on_edit, on_delete, on_move_up, on_move_down)

    def _build(self, step, paint_colour, on_edit, on_delete, on_move_up, on_move_down):
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        # Step number circle
        num = QLabel(str(step.step_order))
        num.setFixedSize(28, 28)
        num.setAlignment(Qt.AlignCenter)
        num.setStyleSheet(
            "background:#0078d4; color:#fff; border-radius:14px;"
            " font-weight:700; font-size:12px;"
        )
        row.addWidget(num)

        # Technique badge
        row.addWidget(_technique_badge(step.technique))

        # Paint swatch + name
        row.addWidget(_colour_swatch(paint_colour, 18))
        paint_lbl = QLabel(step.paint_name or "—")
        paint_lbl.setMinimumWidth(120)
        paint_lbl.setStyleSheet("font-weight: 500;")
        row.addWidget(paint_lbl)

        # Notes (muted, expands)
        if step.notes:
            notes_text = step.notes if len(step.notes) <= 55 else step.notes[:52] + "…"
            notes_lbl = QLabel(notes_text)
            notes_lbl.setObjectName("fieldLabel")
        else:
            notes_lbl = QLabel("")
        notes_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row.addWidget(notes_lbl)

        # Action buttons — compact
        for label, width, callback, is_danger in [
            ("Edit",  44, on_edit,      False),
            ("↑",     28, on_move_up,   False),
            ("↓",     28, on_move_down, False),
            ("✕",     28, on_delete,    True),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(width, 26)
            btn.setStyleSheet("font-size: 11px; padding: 0;")
            if is_danger:
                btn.setProperty("class", "danger")
            btn.clicked.connect(callback)
            row.addWidget(btn)


# ── Main UI ───────────────────────────────────────────────────────────────────

class SchemeUI(QWidget):

    def __init__(self, context):
        super().__init__()
        self.context             = context
        self._current_scheme_id: int | None = None
        self._status_timer       = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status)
        self._build_ui()
        QTimer.singleShot(0, self._initial_load)

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Tab container ─────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setObjectName("schemeTabWidget")
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs, stretch=1)

        # ── Tab 1: Paint Schemes (existing splitter) ──────────────────────────
        schemes_tab = QWidget()
        schemes_lay = QVBoxLayout(schemes_tab)
        schemes_lay.setContentsMargins(0, 0, 0, 0)
        schemes_lay.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_left_pane())
        splitter.addWidget(self._build_right_pane())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # Store reference so showEvent can apply the real pixel size once the
        # splitter has an actual width.  setSizes() called during construction
        # gets scaled proportionally by Qt because the widget has no width yet,
        # so we defer to after the first paint instead.
        self._scheme_splitter = splitter

        schemes_lay.addWidget(splitter, stretch=1)
        self._tabs.addTab(schemes_tab, "📋  Paint Schemes")

        # ── Tab 2: Chroma Codex ───────────────────────────────────────────────
        if _CHROMA_AVAILABLE and _ChromaCodexWidget is not None:
            try:
                self._chroma_tab = _ChromaCodexWidget(self.context)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._chroma_tab = QLabel(f"⚠  Chroma Codex failed to load: {e}")
        else:
            self._chroma_tab = QLabel(
                "⚠  Chroma Codex could not be loaded — check the console for details."
            )
        self._tabs.addTab(self._chroma_tab, "🎨  Chroma Codex")

    # ── Left pane ─────────────────────────────────────────────────────────────

    def _build_left_pane(self) -> QWidget:
        pane = QWidget()
        pane.setMinimumWidth(300)
        pane.setMaximumWidth(520)
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(16, 14, 10, 14)
        lay.setSpacing(8)

        # Title + status
        title_row = QHBoxLayout()
        title = QLabel("Paint Schemes")
        title.setObjectName("pageTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 600; background: transparent;")
        title_row.addWidget(self._status_lbl)
        lay.addLayout(title_row)

        # Search
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search schemes…")
        self._search_input.textChanged.connect(self._on_filter_changed)
        lay.addWidget(self._search_input)

        # Game system filter
        self._gs_filter = QComboBox()
        self._gs_filter.addItem("All game systems", "")
        for gs in COMMON_GAME_SYSTEMS:
            if gs: self._gs_filter.addItem(gs, gs)
        self._gs_filter.currentIndexChanged.connect(self._on_filter_changed)
        lay.addWidget(self._gs_filter)

        # Scheme list
        self._scheme_list = QListWidget()
        self._scheme_list.setAlternatingRowColors(True)
        self._scheme_list.setSpacing(1)
        self._scheme_list.currentItemChanged.connect(self._on_scheme_selected)
        lay.addWidget(self._scheme_list, stretch=1)

        # Bottom action buttons
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self._add_scheme_btn = QPushButton("+ New Scheme")
        self._add_scheme_btn.setProperty("class", "primary")
        self._add_scheme_btn.setFixedHeight(32)
        self._add_scheme_btn.clicked.connect(self._on_new_scheme)
        btn_row.addWidget(self._add_scheme_btn, stretch=1)

        self._delete_scheme_btn = QPushButton("Delete")
        self._delete_scheme_btn.setProperty("class", "danger")
        self._delete_scheme_btn.setFixedHeight(32)
        self._delete_scheme_btn.clicked.connect(self._on_delete_scheme)
        btn_row.addWidget(self._delete_scheme_btn)
        lay.addLayout(btn_row)

        return pane

    # ── Right pane ────────────────────────────────────────────────────────────

    def _build_right_pane(self) -> QWidget:
        # Outer frame with a left border acting as separator
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        # Placeholder
        self._placeholder_lbl = QLabel(
            "Select a scheme from the list, or click  + New Scheme  to get started.")
        self._placeholder_lbl.setObjectName("fieldLabel")
        self._placeholder_lbl.setAlignment(Qt.AlignCenter)
        self._placeholder_lbl.setStyleSheet(
            "color: #505050; font-size: 13px; padding: 60px 40px;")
        outer_lay.addWidget(self._placeholder_lbl, stretch=1)

        # Detail scroll area
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setFrameShape(QFrame.NoFrame)
        self._detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._detail_scroll.setVisible(False)

        detail_host = QWidget()
        detail_host_lay = QVBoxLayout(detail_host)
        detail_host_lay.setContentsMargins(20, 16, 20, 20)
        detail_host_lay.setSpacing(14)

        # ── Scheme header fields ──────────────────────────────────────────────
        self._scheme_name_lbl = QLabel("")
        self._scheme_name_lbl.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #f0f0f0; background: transparent;")
        detail_host_lay.addWidget(self._scheme_name_lbl)

        detail_host_lay.addWidget(_field_label("Scheme Name"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Ultramarines Strike Force")
        detail_host_lay.addWidget(self._name_input)

        gs_faction_row = QHBoxLayout(); gs_faction_row.setSpacing(12)

        gs_col = QVBoxLayout(); gs_col.setSpacing(4)
        gs_col.addWidget(_field_label("Game System"))
        self._gs_input = QComboBox(); self._gs_input.setEditable(True)
        for gs in COMMON_GAME_SYSTEMS: self._gs_input.addItem(gs)
        gs_col.addWidget(self._gs_input)
        gs_faction_row.addLayout(gs_col, stretch=1)

        faction_col = QVBoxLayout(); faction_col.setSpacing(4)
        faction_col.addWidget(_field_label("Faction / Army"))
        self._faction_input = QLineEdit()
        self._faction_input.setPlaceholderText("e.g. Ultramarines")
        faction_col.addWidget(self._faction_input)
        gs_faction_row.addLayout(faction_col, stretch=1)

        detail_host_lay.addLayout(gs_faction_row)

        detail_host_lay.addWidget(_field_label("Description / Overview Notes"))
        self._desc_input = QTextEdit()
        self._desc_input.setPlaceholderText(
            "Overall notes — colours used, style, inspiration…")
        self._desc_input.setFixedHeight(70)
        detail_host_lay.addWidget(self._desc_input)

        # Header action buttons
        hdr_btns = QHBoxLayout(); hdr_btns.setSpacing(8)
        self._save_btn = QPushButton("Save Changes")
        self._save_btn.setProperty("class", "primary")
        self._save_btn.setFixedHeight(34)
        self._save_btn.clicked.connect(self._on_save_scheme)
        hdr_btns.addWidget(self._save_btn)

        self._duplicate_btn = QPushButton("Duplicate")
        self._duplicate_btn.setFixedHeight(34)
        self._duplicate_btn.clicked.connect(self._on_duplicate_scheme)
        hdr_btns.addWidget(self._duplicate_btn)
        hdr_btns.addStretch()
        detail_host_lay.addLayout(hdr_btns)

        detail_host_lay.addWidget(_hline())

        # ── Steps section ─────────────────────────────────────────────────────
        steps_hdr = QHBoxLayout()
        self._steps_title_lbl = QLabel("Steps")
        self._steps_title_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #d8d8d8; background: transparent;")
        steps_hdr.addWidget(self._steps_title_lbl)
        steps_hdr.addStretch()
        detail_host_lay.addLayout(steps_hdr)

        # Steps list (no inner scroll — parent scroll area handles it)
        self._steps_container = QWidget()
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(4)
        self._steps_layout.addStretch()
        detail_host_lay.addWidget(self._steps_container)

        # Empty-steps hint
        self._steps_empty_lbl = QLabel("No steps yet — click  + Add Step  below to begin.")
        self._steps_empty_lbl.setObjectName("fieldLabel")
        self._steps_empty_lbl.setAlignment(Qt.AlignCenter)
        self._steps_empty_lbl.setStyleSheet(
            "color: #505050; padding: 18px; background: transparent;")
        detail_host_lay.addWidget(self._steps_empty_lbl)

        add_step_btn = QPushButton("+ Add Step")
        add_step_btn.setFixedHeight(34)
        add_step_btn.clicked.connect(self._on_add_step)
        detail_host_lay.addWidget(add_step_btn)

        detail_host_lay.addWidget(_hline())

        # ── Linked Models section ─────────────────────────────────────────────
        models_hdr = QHBoxLayout()
        models_title = QLabel("Linked Models")
        models_title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #d8d8d8; background: transparent;")
        models_hdr.addWidget(models_title)
        models_hdr.addStretch()
        detail_host_lay.addLayout(models_hdr)

        self._models_list_layout = QVBoxLayout()
        self._models_list_layout.setSpacing(3)
        detail_host_lay.addLayout(self._models_list_layout)

        link_btn = QPushButton("Link Model…")
        link_btn.setFixedHeight(30)
        link_btn.clicked.connect(self._on_link_model)
        detail_host_lay.addWidget(link_btn, alignment=Qt.AlignLeft)

        # ── Linked Projects back-link ─────────────────────────────────────────
        detail_host_lay.addWidget(_hline())
        self._linked_projects_section = RelatedItemsSection(title="LINKED PROJECTS", icon="📁")
        self._linked_projects_section.navigate_requested.connect(
            lambda pid, _eid: self._emit_navigate(pid)
        )
        self._linked_projects_section.set_empty("Not linked to any project.")
        detail_host_lay.addWidget(self._linked_projects_section)

        detail_host_lay.addStretch()

        self._detail_scroll.setWidget(detail_host)
        outer_lay.addWidget(self._detail_scroll, stretch=1)

        return outer

    # ── Initial load ──────────────────────────────────────────────────────────

    def _initial_load(self):
        self.refresh_scheme_list()

    def showEvent(self, event):
        """Set the splitter's left-pane width once we have a real pixel size."""
        super().showEvent(event)
        if not getattr(self, "_splitter_sized", False):
            sp = getattr(self, "_scheme_splitter", None)
            if sp is not None:
                # Defer one frame so the splitter has been laid out and
                # sp.width() returns the actual rendered width.
                from PySide6.QtCore import QTimer as _QT
                _QT.singleShot(0, self._apply_splitter_size)

    def _apply_splitter_size(self):
        sp = getattr(self, "_scheme_splitter", None)
        if sp is None or getattr(self, "_splitter_sized", False):
            return
        w = sp.width()
        if w > 400:          # sanity-check: widget is actually visible
            left = 340
            sp.setSizes([left, w - left])
            self._splitter_sized = True

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh_scheme_list(self):
        svc = self._get_service()
        if svc is None: return
        try:
            schemes = svc.search_schemes(self._current_filter())
        except Exception as e:
            print(f"[SCHEME UI] refresh_scheme_list: {e}"); return

        step_counts = {}
        for s in schemes:
            try: step_counts[s.id] = len(svc.get_steps(s.id))
            except Exception: step_counts[s.id] = 0

        current_id = self._current_scheme_id
        self._scheme_list.blockSignals(True)
        self._scheme_list.clear()
        restore_row = -1

        for i, scheme in enumerate(schemes):
            count = step_counts.get(scheme.id, 0)
            parts = [x for x in [scheme.faction, scheme.game_system] if x]
            sub   = " · ".join(parts) if parts else ""
            display = f"{scheme.name}\n{sub}  ·  {count} step{'s' if count != 1 else ''}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, scheme.id)
            self._scheme_list.addItem(item)
            if scheme.id == current_id:
                restore_row = i

        self._scheme_list.blockSignals(False)

        if restore_row >= 0:
            self._scheme_list.setCurrentRow(restore_row)
        elif self._scheme_list.count() == 0:
            self._clear_detail()

    def refresh_scheme_detail(self, scheme_id: int):
        if self._current_scheme_id == scheme_id:
            self._load_scheme_detail(scheme_id)
        self.refresh_scheme_list()

    def refresh_current_scheme(self):
        if self._current_scheme_id is not None:
            self._load_scheme_detail(self._current_scheme_id)

    # ── Filter ────────────────────────────────────────────────────────────────

    def _current_filter(self) -> SchemeFilter:
        return SchemeFilter(
            search_text=self._search_input.text().strip() or None,
            game_system=self._gs_filter.currentData() or None,
        )

    def _on_filter_changed(self, *_):
        self.refresh_scheme_list()

    # ── Scheme list interactions ──────────────────────────────────────────────

    def _on_scheme_selected(self, current, _):
        if current is None:
            self._clear_detail(); return
        self._current_scheme_id = current.data(Qt.UserRole)
        self._load_scheme_detail(self._current_scheme_id)

    def _on_new_scheme(self):
        svc = self._get_service()
        if svc is None: return
        try:
            scheme = svc.add_scheme(name="New Scheme")
            self.context.event_bus.emit("scheme_added", {"scheme": scheme})
            self._current_scheme_id = scheme.id
            self.refresh_scheme_list()
        except Exception as e:
            self._show_error(str(e))

    def _on_delete_scheme(self):
        if self._current_scheme_id is None: return
        svc = self._get_service()
        if svc is None: return
        scheme = svc.get_scheme(self._current_scheme_id)
        if scheme is None: return
        reply = QMessageBox.question(
            self, "Delete Scheme",
            f"Delete '{scheme.name}' and all its steps?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes: return
        try:
            svc.delete_scheme(self._current_scheme_id)
            self.context.event_bus.emit("scheme_deleted", {"scheme_id": self._current_scheme_id})
            self._current_scheme_id = None
            self._clear_detail()
            self.refresh_scheme_list()
        except Exception as e:
            self._show_error(str(e))

    # ── Detail ────────────────────────────────────────────────────────────────

    def _load_scheme_detail(self, scheme_id: int):
        svc = self._get_service()
        if svc is None: return
        scheme = svc.get_scheme(scheme_id)
        if scheme is None:
            self._clear_detail(); return

        self._placeholder_lbl.setVisible(False)
        self._detail_scroll.setVisible(True)

        # Big name label at top
        self._scheme_name_lbl.setText(scheme.name)

        for widget, val in [
            (self._name_input,    scheme.name),
            (self._faction_input, scheme.faction),
        ]:
            widget.blockSignals(True)
            widget.setText(val)
            widget.blockSignals(False)

        self._gs_input.blockSignals(True)
        idx = self._gs_input.findText(scheme.game_system)
        self._gs_input.setCurrentIndex(idx) if idx >= 0 else self._gs_input.setCurrentText(scheme.game_system)
        self._gs_input.blockSignals(False)

        self._desc_input.blockSignals(True)
        self._desc_input.setPlainText(scheme.description)
        self._desc_input.blockSignals(False)

        steps = svc.get_steps(scheme_id)
        n = len(steps)
        self._steps_title_lbl.setText(f"Steps  ({n})")
        self._steps_empty_lbl.setVisible(n == 0)
        self._steps_container.setVisible(n > 0)
        self._rebuild_steps(steps, scheme_id)
        self._rebuild_linked_models(scheme_id)
        self._refresh_linked_projects(scheme_id)

    def _clear_detail(self):
        self._detail_scroll.setVisible(False)
        self._placeholder_lbl.setVisible(True)

    def _on_save_scheme(self):
        if self._current_scheme_id is None: return
        svc = self._get_service()
        if svc is None: return
        try:
            scheme = svc.update_scheme(
                self._current_scheme_id,
                name        = self._name_input.text().strip(),
                game_system = self._gs_input.currentText().strip(),
                faction     = self._faction_input.text().strip(),
                description = self._desc_input.toPlainText().strip(),
            )
            self._scheme_name_lbl.setText(scheme.name)
            self.context.event_bus.emit("scheme_updated", {"scheme": scheme})
            self._show_success("Saved.")
            self.refresh_scheme_list()
        except Exception as e:
            self._show_error(str(e))

    def _on_duplicate_scheme(self):
        if self._current_scheme_id is None: return
        svc = self._get_service()
        if svc is None: return
        try:
            original = svc.get_scheme(self._current_scheme_id)
            if not original: return
            copy = svc.add_scheme(
                name        = f"{original.name} (copy)",
                game_system = original.game_system,
                faction     = original.faction,
                description = original.description,
            )
            for step in svc.get_steps(original.id):
                svc.add_step(copy.id, step.technique, step.paint_id, step.paint_name, step.notes)
            self.context.event_bus.emit("scheme_added", {"scheme": copy})
            self._current_scheme_id = copy.id
            self.refresh_scheme_list()
            self._show_success(f"Duplicated as '{copy.name}'.")
        except Exception as e:
            self._show_error(str(e))

    # ── Steps ─────────────────────────────────────────────────────────────────

    def _rebuild_steps(self, steps: list, scheme_id: int):
        while self._steps_layout.count() > 1:
            item = self._steps_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        paint_colours: dict[int, str] = {}
        paint_svc = self.context.services.try_get("paint_service")
        if paint_svc:
            try:
                for p in paint_svc.get_all_paints():
                    paint_colours[p.id] = getattr(p, "color", None)
            except Exception:
                pass

        for step in steps:
            colour = paint_colours.get(step.paint_id) if step.paint_id else None

            def make_cbs(s):
                return (
                    lambda: self._on_edit_step(s),
                    lambda: self._on_delete_step(s),
                    lambda: self._on_move_step(s, -1),
                    lambda: self._on_move_step(s, +1),
                )

            card = StepCard(step, colour, *make_cbs(step))
            self._steps_layout.insertWidget(self._steps_layout.count() - 1, card)

    def _on_add_step(self):
        if self._current_scheme_id is None: return
        dlg = StepDialog(self, self.context, self._current_scheme_id)
        if dlg.exec() != QDialog.Accepted: return
        svc = self._get_service()
        if svc is None: return
        try:
            svc.add_step(
                self._current_scheme_id,
                dlg.get_technique(), dlg.get_paint_id(),
                dlg.get_paint_name(), dlg.get_notes(),
            )
            self._load_scheme_detail(self._current_scheme_id)
            self.refresh_scheme_list()
        except Exception as e:
            self._show_error(str(e))

    def _on_edit_step(self, step):
        svc = self._get_service()
        if svc is None: return
        dlg = StepDialog(self, self.context, step.scheme_id, step=step)
        if dlg.exec() != QDialog.Accepted: return
        try:
            svc.update_step(step.id,
                technique  = dlg.get_technique(),
                paint_id   = dlg.get_paint_id(),
                paint_name = dlg.get_paint_name(),
                notes      = dlg.get_notes(),
            )
            self._load_scheme_detail(step.scheme_id)
        except Exception as e:
            self._show_error(str(e))

    def _on_delete_step(self, step):
        reply = QMessageBox.question(
            self, "Remove Step",
            f"Remove step {step.step_order} ({step.technique})?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes: return
        svc = self._get_service()
        if svc is None: return
        try:
            svc.delete_step(step.id)
            self._load_scheme_detail(step.scheme_id)
            self.refresh_scheme_list()
        except Exception as e:
            self._show_error(str(e))

    def _on_move_step(self, step, direction: int):
        svc = self._get_service()
        if svc is None: return
        try:
            steps = svc.get_steps(step.scheme_id)
            ids   = [s.id for s in steps]
            idx   = ids.index(step.id)
            new_i = idx + direction
            if new_i < 0 or new_i >= len(ids): return
            ids[idx], ids[new_i] = ids[new_i], ids[idx]
            svc.reorder_steps(step.scheme_id, ids)
            self._load_scheme_detail(step.scheme_id)
        except Exception as e:
            self._show_error(str(e))

    # ── Linked models ─────────────────────────────────────────────────────────

    def _rebuild_linked_models(self, scheme_id: int):
        while self._models_list_layout.count():
            item = self._models_list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        svc = self._get_service()
        if svc is None: return
        linked_ids = svc.get_linked_models(scheme_id)

        if not linked_ids:
            lbl = QLabel("No models linked yet.")
            lbl.setObjectName("fieldLabel")
            self._models_list_layout.addWidget(lbl)
            return

        model_map: dict[int, object] = {}
        model_svc = self.context.services.try_get("model_service")
        if model_svc:
            try:
                from plugins.model_tracker.models import ModelFilter
                model_map = {m.id: m for m in model_svc.search_models(ModelFilter())}
            except Exception:
                try:
                    model_map = {m.id: m for m in model_svc.get_all_models()}
                except Exception:
                    pass

        for mid in linked_ids:
            card = QFrame(); card.setFrameShape(QFrame.StyledPanel)
            crow = QHBoxLayout(card)
            crow.setContentsMargins(10, 6, 10, 6); crow.setSpacing(8)

            m = model_map.get(mid)
            if m:
                parts = [x for x in [
                    getattr(m, "faction", ""), getattr(m, "game_system", "")] if x]
                name_lbl = QLabel(m.name)
                name_lbl.setStyleSheet("font-weight: 600; background: transparent;")
                sub_lbl  = QLabel(" · ".join(parts))
                sub_lbl.setObjectName("fieldLabel")
            else:
                name_lbl = QLabel(f"Model #{mid}")
                name_lbl.setStyleSheet("background: transparent;")
                sub_lbl  = QLabel("")

            crow.addWidget(name_lbl)
            crow.addWidget(sub_lbl)
            crow.addStretch()

            def make_unlink(model_id):
                def _u(): self._on_unlink_model(scheme_id, model_id)
                return _u

            unlink_btn = QPushButton("Unlink")
            unlink_btn.setFixedSize(56, 24)
            unlink_btn.setStyleSheet("font-size: 11px; padding: 0;")
            unlink_btn.clicked.connect(make_unlink(mid))
            crow.addWidget(unlink_btn)

            self._models_list_layout.addWidget(card)

    def _on_link_model(self):
        if self._current_scheme_id is None: return
        svc = self._get_service()
        if svc is None: return
        already = svc.get_linked_models(self._current_scheme_id)
        dlg = ModelPickerDialog(self, self.context, already)
        if dlg.exec() != QDialog.Accepted or dlg.selected_model_id is None: return
        try:
            svc.link_model(self._current_scheme_id, dlg.selected_model_id)
            self._rebuild_linked_models(self._current_scheme_id)
        except Exception as e:
            self._show_error(str(e))

    def _on_unlink_model(self, scheme_id: int, model_id: int):
        svc = self._get_service()
        if svc is None: return
        try:
            svc.unlink_model(scheme_id, model_id)
            self._rebuild_linked_models(scheme_id)
        except Exception as e:
            self._show_error(str(e))

    # ── Linked projects ───────────────────────────────────────────────────────

    def _refresh_linked_projects(self, scheme_id: int) -> None:
        """Populate the 'Linked Projects' RelatedItemsSection."""
        proj_svc = self.context.services.try_get("project_service")
        if proj_svc is None:
            self._linked_projects_section.set_empty("Project Tracker not available.")
            return
        try:
            projects = proj_svc.get_projects_for_entity("scheme", scheme_id)
        except Exception as e:
            print(f"[SCHEME UI] _refresh_linked_projects: {e}")
            self._linked_projects_section.set_empty("Could not load projects.")
            return

        if not projects:
            self._linked_projects_section.set_empty("Not linked to any project.")
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
        self._linked_projects_section.set_chips(chips)

    def _emit_navigate(self, plugin_id: str) -> None:
        bus = getattr(self.context, "event_bus", None)
        if bus:
            try:
                bus.emit("dashboard_navigate", {"plugin_id": plugin_id})
            except Exception:
                pass

    # ── Status messages ───────────────────────────────────────────────────────

    def _show_success(self, msg: str):
        self._status_lbl.setText(f"✓ {msg}")
        self._status_lbl.setStyleSheet(
            "color: #3dba6e; font-size: 11px; font-weight: 600; background: transparent;")
        self._status_timer.start(3000)

    def _show_error(self, msg: str):
        self._status_lbl.setText(f"✗ {msg}")
        self._status_lbl.setStyleSheet(
            "color: #e05555; font-size: 11px; font-weight: 600; background: transparent;")
        self._status_timer.start(5000)

    def _clear_status(self):
        self._status_lbl.setText("")

    def _get_service(self):
        return self.context.services.try_get("scheme_service")
