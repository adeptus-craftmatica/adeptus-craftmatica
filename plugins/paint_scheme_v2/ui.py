"""
Paint Schemes 2.0 — Premium UI

Layout:
  Left pane  — search / filter bar + scrollable scheme cards + New Scheme button
  Right pane — selected scheme detail: header fields, ordered step cards,
               linked models, linked projects
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from PySide6.QtCore import Qt, QTimer, Signal, QMimeData, QByteArray
from PySide6.QtGui  import QColor, QDrag
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QSizePolicy, QSplitter, QTextEdit, QListWidget, QListWidgetItem,
    QMessageBox, QApplication,
)

from plugins.paint_scheme.models import TECHNIQUES, SchemeFilter

# ── Design system (matches model_tracker_v2) ──────────────────────────────────

_C = {
    "bg_deep":    "#141414",
    "bg_base":    "#1c1c1c",
    "bg_card":    "#1e1e1e",
    "bg_raised":  "#212121",
    "bg_input":   "#2a2a2a",
    "bg_hover":   "#2e2e2e",
    "bg_active":  "#333333",
    "border_lo":  "#282828",
    "border":     "#363636",
    "border_hi":  "#484848",
    "text_hi":    "#f0f0f0",
    "text_mid":   "#d8d8d8",
    "text_lo":    "#909090",
    "text_dim":   "#606060",
    "accent":     "#0078d4",
    "accent_hi":  "#1a8ee8",
    "accent_lo":  "#0f4a7a",
    "accent_text":"#60b0ff",
    "danger":     "#e05555",
    "danger_hi":  "#eb6868",
    "danger_lo":  "#2a1515",
    "success":    "#3dba6e",
    "success_lo": "#0f2a1a",
    "warning":    "#e07800",
    "warning_lo": "#2a1800",
    "gold":       "#c8960c",
    "gold_lo":    "#2a1e00",
}
_FS = {"xs": "10px", "sm": "11px", "base": "12px", "lg": "13px",
       "xl": "15px", "2xl": "20px", "3xl": "28px"}
_R  = {"xs": "3px", "sm": "5px", "base": "7px", "lg": "10px", "pill": "999px"}

# Technique → accent colour (bg, fg)
_TECHNIQUE_COLORS: dict[str, tuple[str, str]] = {
    "Primer":                 ("#3a3a4a", "#aaaacc"),
    "Basecoat":               ("#0d2a50", "#6699dd"),
    "Layer":                  ("#0d3060", "#77aaee"),
    "Wash / Shade":           ("#2a1040", "#bb77ee"),
    "Drybrush":               ("#3d2008", "#dd8844"),
    "Edge Highlight":         ("#0d3a50", "#55bbee"),
    "Highlight":              ("#0d3a50", "#55bbee"),
    "Glaze":                  ("#052e28", "#44ccaa"),
    "Contrast / Speed Paint": ("#052e28", "#44ccaa"),
    "Technical":              ("#0d3020", "#44bb66"),
    "Varnish":                ("#2e2000", "#ccaa44"),
    "Basing":                 ("#2e1208", "#cc7744"),
    "Other":                  ("#222222", "#888888"),
}

COMMON_GAME_SYSTEMS = [
    "", "Warhammer 40,000", "Warhammer: Age of Sigmar",
    "Warhammer: The Old World", "Horus Heresy", "Kill Team", "Necromunda",
    "Middle Earth Strategy Battle Game", "Dungeons & Dragons", "Pathfinder",
    "Gundam", "Star Wars: Legion", "Marvel Crisis Protocol", "Bolt Action", "Other",
]


# ── Style helpers ─────────────────────────────────────────────────────────────

def _input_ss() -> str:
    return (
        f"QLineEdit, QTextEdit, QComboBox {{"
        f" background: {_C['bg_input']}; color: {_C['text_hi']};"
        f" border: 1px solid {_C['border']}; border-radius: {_R['sm']};"
        f" padding: 5px 10px; font-size: {_FS['base']}; }}"
        f"QLineEdit:focus, QTextEdit:focus, QComboBox:focus"
        f" {{ border-color: {_C['accent']}; background: {_C['bg_hover']}; }}"
        f"QComboBox::drop-down {{ border: none; width: 22px; }}"
        f"QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}"
        f"QComboBox QAbstractItemView {{"
        f" background: {_C['bg_card']}; color: {_C['text_hi']};"
        f" border: 1px solid {_C['border']};"
        f" selection-background-color: {_C['accent_lo']};"
        f" selection-color: {_C['accent_text']}; }}"
    )

def _primary_btn_ss(small: bool = False) -> str:
    pad = "4px 12px" if small else "6px 18px"
    fs  = _FS["sm"] if small else _FS["base"]
    return (
        f"QPushButton {{ background: {_C['accent']}; color: {_C['text_hi']}; border: none;"
        f" border-radius: {_R['sm']}; padding: {pad}; font-size: {fs}; font-weight: 600; }}"
        f"QPushButton:hover {{ background: {_C['accent_hi']}; }}"
        f"QPushButton:disabled {{ background: {_C['bg_hover']}; color: {_C['text_dim']}; }}"
    )

def _secondary_btn_ss(small: bool = False) -> str:
    pad = "4px 10px" if small else "6px 14px"
    fs  = _FS["sm"] if small else _FS["base"]
    return (
        f"QPushButton {{ background: {_C['bg_card']}; color: {_C['text_mid']};"
        f" border: 1px solid {_C['border']}; border-radius: {_R['sm']};"
        f" padding: {pad}; font-size: {fs}; }}"
        f"QPushButton:hover {{ background: {_C['bg_hover']}; border-color: {_C['border_hi']};"
        f" color: {_C['text_hi']}; }}"
    )

def _danger_btn_ss(small: bool = False) -> str:
    pad = "4px 10px" if small else "6px 14px"
    fs  = _FS["sm"] if small else _FS["base"]
    return (
        f"QPushButton {{ background: {_C['danger_lo']}; color: {_C['danger']};"
        f" border: 1px solid {_C['danger_lo']}; border-radius: {_R['sm']};"
        f" padding: {pad}; font-size: {fs}; }}"
        f"QPushButton:hover {{ background: {_C['danger']}; color: {_C['text_hi']};"
        f" border-color: {_C['danger']}; }}"
    )

def _ghost_btn_ss(size: str = "12px") -> str:
    return (
        f"QPushButton {{ background: transparent; border: none; color: {_C['text_dim']};"
        f" border-radius: {_R['xs']}; font-size: {size}; padding: 2px 5px; }}"
        f"QPushButton:hover {{ background: rgba(255,255,255,0.07); color: {_C['text_lo']}; }}"
        f"QPushButton:pressed {{ background: rgba(255,255,255,0.12); }}"
    )

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: {_FS['xs']}; font-weight: 700; color: {_C['text_lo']};"
        f" letter-spacing: 1px; background: transparent; border: none;"
    )
    return lbl

def _hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {_C['border_lo']}; border: none;")
    return f

def _colour_dot(hex_col: str | None, size: int = 12) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    c = hex_col if (hex_col and hex_col.startswith("#") and len(hex_col) >= 7) else "#3a3a3a"
    lbl.setStyleSheet(
        f"background: {c}; border-radius: {size // 2}px;"
        f" border: 1px solid rgba(255,255,255,0.15); border: none;"
    )
    lbl.setToolTip(c)
    return lbl


# ══════════════════════════════════════════════════════════════════════════════
#  _TechniqueBadge
# ══════════════════════════════════════════════════════════════════════════════

class _TechniqueBadge(QLabel):
    def __init__(self, technique: str, parent=None):
        super().__init__(parent)
        bg, fg = _TECHNIQUE_COLORS.get(technique, ("#222222", "#888888"))
        self.setText(technique)
        self.setStyleSheet(
            f"background: {bg}; color: {fg}; font-size: {_FS['xs']}; font-weight: 700;"
            f" padding: 2px 9px; border-radius: {_R['pill']}; border: none;"
        )
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


# ══════════════════════════════════════════════════════════════════════════════
#  _SchemeCard  (left-panel list item)
# ══════════════════════════════════════════════════════════════════════════════

class _SchemeCard(QFrame):
    clicked = Signal(int)   # scheme_id

    def __init__(self, scheme, step_count: int, selected: bool = False, parent=None):
        super().__init__(parent)
        self._scheme_id = scheme.id
        self._build(scheme, step_count, selected)

    def _build(self, scheme, step_count: int, selected: bool):
        self.setObjectName("schemeCard")
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style(selected)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 9, 12, 9)
        root.setSpacing(3)

        # Name row
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(6)

        name_lbl = QLabel(scheme.name)
        name_lbl.setStyleSheet(
            f"font-size: {_FS['base']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        name_lbl.setWordWrap(False)
        name_row.addWidget(name_lbl, 1)

        # Step count badge
        badge = QLabel(f"{step_count}")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(24, 16)
        badge.setStyleSheet(
            f"color: {_C['accent_text']}; background: {_C['accent_lo']};"
            f" font-size: {_FS['xs']}; font-weight: 700;"
            f" border-radius: 8px; border: none;"
        )
        badge.setToolTip(f"{step_count} step{'s' if step_count != 1 else ''}")
        name_row.addWidget(badge)
        root.addLayout(name_row)

        # Subtitle
        parts = [x for x in [scheme.faction, scheme.game_system] if x]
        if parts:
            sub = QLabel(" · ".join(parts))
            sub.setStyleSheet(
                f"font-size: {_FS['xs']}; color: {_C['text_lo']};"
                " background: transparent; border: none;"
            )
            root.addWidget(sub)

    def _apply_style(self, selected: bool):
        if selected:
            self.setStyleSheet(f"""
                QFrame#schemeCard {{
                    background: {_C['accent_lo']};
                    border: 1px solid {_C['accent']};
                    border-left: 3px solid {_C['accent']};
                    border-radius: {_R['sm']};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#schemeCard {{
                    background: {_C['bg_card']};
                    border: 1px solid {_C['border']};
                    border-left: 3px solid {_C['bg_card']};
                    border-radius: {_R['sm']};
                }}
                QFrame#schemeCard:hover {{
                    background: {_C['bg_raised']};
                    border-color: {_C['border_hi']};
                }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._scheme_id)
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  _StepCard
# ══════════════════════════════════════════════════════════════════════════════

class _StepCard(QFrame):
    edit_requested   = Signal(object)   # step
    delete_requested = Signal(object)   # step
    move_requested   = Signal(object, int)  # step, direction (-1 / +1)

    def __init__(self, step, paint_colour: str | None,
                 is_first: bool, is_last: bool, parent=None):
        super().__init__(parent)
        self._step = step
        self._build(step, paint_colour, is_first, is_last)

    def _build(self, step, paint_colour, is_first, is_last):
        self.setObjectName("stepCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(f"""
            QFrame#stepCard {{
                background: {_C['bg_raised']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(8)

        # Step number bubble
        num = QLabel(str(step.step_order))
        num.setFixedSize(26, 26)
        num.setAlignment(Qt.AlignCenter)
        num.setStyleSheet(
            f"background: {_C['accent_lo']}; color: {_C['accent_text']};"
            f" border-radius: 13px; font-weight: 700; font-size: {_FS['sm']};"
            " border: none;"
        )
        row.addWidget(num)

        # Technique badge
        row.addWidget(_TechniqueBadge(step.technique))

        # Paint dot + name
        dot = _colour_dot(paint_colour, 10)
        row.addWidget(dot)

        paint_lbl = QLabel(step.paint_name or "—")
        paint_lbl.setStyleSheet(
            f"font-size: {_FS['sm']}; color: {_C['text_mid']};"
            " background: transparent; border: none;"
        )
        paint_lbl.setMinimumWidth(90)
        row.addWidget(paint_lbl)

        # Notes (fills remaining space, elided)
        if step.notes:
            notes_lbl = QLabel(step.notes)
            notes_lbl.setStyleSheet(
                f"font-size: {_FS['xs']}; color: {_C['text_lo']}; font-style: italic;"
                " background: transparent; border: none;"
            )
            notes_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row.addWidget(notes_lbl, 1)
        else:
            row.addStretch(1)

        # Action buttons
        _ghost = _ghost_btn_ss("11px")

        up_btn = QPushButton("↑")
        up_btn.setFixedSize(22, 22)
        up_btn.setStyleSheet(_ghost)
        up_btn.setToolTip("Move up")
        up_btn.setEnabled(not is_first)
        up_btn.clicked.connect(lambda: self.move_requested.emit(step, -1))
        row.addWidget(up_btn)

        dn_btn = QPushButton("↓")
        dn_btn.setFixedSize(22, 22)
        dn_btn.setStyleSheet(_ghost)
        dn_btn.setToolTip("Move down")
        dn_btn.setEnabled(not is_last)
        dn_btn.clicked.connect(lambda: self.move_requested.emit(step, +1))
        row.addWidget(dn_btn)

        edit_btn = QPushButton("✏")
        edit_btn.setFixedSize(22, 22)
        edit_btn.setStyleSheet(_ghost)
        edit_btn.setToolTip("Edit step")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(step))
        row.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {_C['text_dim']};"
            f" border-radius: {_R['xs']}; font-size: 11px; padding: 2px; }}"
            f"QPushButton:hover {{ background: {_C['danger_lo']}; color: {_C['danger']}; }}"
        )
        del_btn.setToolTip("Remove step")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(step))
        row.addWidget(del_btn)


# ══════════════════════════════════════════════════════════════════════════════
#  _StepDialog
# ══════════════════════════════════════════════════════════════════════════════

class _StepDialog(QDialog):
    def __init__(self, context, scheme_id: int, step=None, parent=None):
        super().__init__(parent)
        self._context   = context
        self._scheme_id = scheme_id
        self._step      = step
        self._paints: list = []
        self.setWindowTitle("Edit Step" if step else "Add Step")
        self.setMinimumWidth(520)
        self.setModal(True)
        self.setStyleSheet(f"background: {_C['bg_base']}; color: {_C['text_hi']};")
        self._build()
        self._load_paints()
        if step:
            self._populate(step)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 18, 20, 18)

        # Technique
        lay.addWidget(_section_label("TECHNIQUE"))
        self._technique_combo = QComboBox()
        self._technique_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._technique_combo.addItems(TECHNIQUES)
        self._technique_combo.setStyleSheet(_input_ss())
        lay.addWidget(self._technique_combo)

        # Paint search
        lay.addWidget(_section_label("PAINT  (optional)"))
        self._paint_search = QLineEdit()
        self._paint_search.setPlaceholderText("Search by name or brand…")
        self._paint_search.setStyleSheet(_input_ss())
        self._paint_search.textChanged.connect(self._filter_paints)
        lay.addWidget(self._paint_search)

        self._paint_list = QListWidget()
        self._paint_list.setFixedHeight(160)
        self._paint_list.setStyleSheet(f"""
            QListWidget {{
                background: {_C['bg_card']};
                color: {_C['text_hi']};
                border: 1px solid {_C['border']};
                border-radius: {_R['sm']};
                font-size: {_FS['base']};
                outline: none;
            }}
            QListWidget::item {{
                padding: 5px 10px;
                border-bottom: 1px solid {_C['border_lo']};
            }}
            QListWidget::item:selected {{
                background: {_C['accent_lo']};
                color: {_C['accent_text']};
            }}
            QListWidget::item:hover:!selected {{
                background: {_C['bg_hover']};
            }}
        """)
        lay.addWidget(self._paint_list)

        self._manual_name = QLineEdit()
        self._manual_name.setPlaceholderText("Or type paint name manually…")
        self._manual_name.setStyleSheet(_input_ss())
        self._manual_name.setVisible(False)
        lay.addWidget(self._manual_name)

        # Notes
        lay.addWidget(_section_label("NOTES"))
        self._notes_input = QLineEdit()
        self._notes_input.setPlaceholderText("e.g. Two thin coats, focus on recesses…")
        self._notes_input.setStyleSheet(_input_ss())
        lay.addWidget(self._notes_input)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("Save Step")
        btn_box.button(QDialogButtonBox.Ok).setStyleSheet(_primary_btn_ss())
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet(_secondary_btn_ss())
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _load_paints(self):
        paint_svc = self._context.services.try_get("paint_service")
        if paint_svc is None:
            self._paint_list.setVisible(False)
            self._paint_search.setVisible(False)
            self._manual_name.setVisible(True)
            return
        try:
            self._paints = paint_svc.get_all_paints()
        except Exception as e:
            log.error(f"[SCHEME V2] load_paints: {e}")
            self._paints = []
        self._populate_paint_list(self._paints)

    def _populate_paint_list(self, paints: list):
        self._paint_list.clear()
        blank = QListWidgetItem("  — No paint —")
        blank.setData(Qt.UserRole, None)
        self._paint_list.addItem(blank)
        for p in paints:
            label = f"  {p.brand}  ·  {p.name}  [{p.paint_type}]"
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole,     p.id)
            item.setData(Qt.UserRole + 1, getattr(p, "color", None))
            col = getattr(p, "color", None)
            if col and col.startswith("#"):
                qc = QColor(col)
                bright = (qc.red() * 299 + qc.green() * 587 + qc.blue() * 114) / 1000
                item.setBackground(qc)
                item.setForeground(QColor("#000" if bright > 128 else "#fff"))
            self._paint_list.addItem(item)

    def _filter_paints(self, text: str):
        needle = text.strip().lower()
        self._populate_paint_list([
            p for p in self._paints
            if not needle
            or needle in p.name.lower()
            or needle in getattr(p, "brand", "").lower()
        ])

    def _populate(self, step):
        idx = self._technique_combo.findText(step.technique)
        if idx >= 0:
            self._technique_combo.setCurrentIndex(idx)
        self._notes_input.setText(step.notes or "")
        if step.paint_id is not None:
            for i in range(self._paint_list.count()):
                if self._paint_list.item(i).data(Qt.UserRole) == step.paint_id:
                    self._paint_list.setCurrentRow(i)
                    break
        else:
            self._paint_list.setCurrentRow(0)
            if self._manual_name.isVisible():
                self._manual_name.setText(step.paint_name or "")

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_technique(self) -> str:
        return self._technique_combo.currentText()

    def get_paint_id(self):
        item = self._paint_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def get_paint_name(self) -> str:
        if self._manual_name.isVisible():
            return self._manual_name.text().strip()
        item = self._paint_list.currentItem()
        if item and item.data(Qt.UserRole) is not None:
            txt = item.text().strip()
            # strip the [type] suffix
            return txt[:txt.rfind("[")].strip() if "[" in txt else txt
        return ""

    def get_notes(self) -> str:
        return self._notes_input.text().strip()


# ══════════════════════════════════════════════════════════════════════════════
#  _SchemeDialog  (create / edit scheme metadata)
# ══════════════════════════════════════════════════════════════════════════════

class _SchemeDialog(QDialog):
    def __init__(self, context, scheme=None, parent=None):
        super().__init__(parent)
        self._context = context
        self._scheme  = scheme
        self.setWindowTitle("Edit Scheme" if scheme else "New Scheme")
        self.setMinimumWidth(480)
        self.setModal(True)
        self.setStyleSheet(f"background: {_C['bg_base']}; color: {_C['text_hi']};")
        self._build()
        if scheme:
            self._populate(scheme)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 18, 20, 18)

        lay.addWidget(_section_label("SCHEME NAME"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Ultramarines Strike Force")
        self._name.setStyleSheet(_input_ss())
        lay.addWidget(self._name)

        gs_row = QHBoxLayout()
        gs_row.setSpacing(10)

        gs_col = QVBoxLayout()
        gs_col.addWidget(_section_label("GAME SYSTEM"))
        self._gs = QComboBox()
        self._gs.setEditable(True)
        self._gs.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._gs.addItems([gs for gs in COMMON_GAME_SYSTEMS if gs])
        self._gs.setCurrentIndex(-1)
        self._gs.setStyleSheet(_input_ss())
        gs_col.addWidget(self._gs)
        gs_row.addLayout(gs_col, 1)

        fa_col = QVBoxLayout()
        fa_col.addWidget(_section_label("FACTION / ARMY"))
        self._faction = QLineEdit()
        self._faction.setPlaceholderText("e.g. Ultramarines")
        self._faction.setStyleSheet(_input_ss())
        fa_col.addWidget(self._faction)
        gs_row.addLayout(fa_col, 1)
        lay.addLayout(gs_row)

        lay.addWidget(_section_label("DESCRIPTION"))
        self._desc = QTextEdit()
        self._desc.setPlaceholderText("Overall notes — colours, style, inspiration…")
        self._desc.setFixedHeight(80)
        self._desc.setStyleSheet(_input_ss())
        lay.addWidget(self._desc)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("Save" if self._scheme else "Create")
        btn_box.button(QDialogButtonBox.Ok).setStyleSheet(_primary_btn_ss())
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet(_secondary_btn_ss())
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _populate(self, scheme):
        self._name.setText(scheme.name)
        idx = self._gs.findText(scheme.game_system)
        self._gs.setCurrentIndex(idx) if idx >= 0 else self._gs.setCurrentText(scheme.game_system)
        self._faction.setText(scheme.faction)
        self._desc.setPlainText(scheme.description)

    def get_name(self)        -> str: return self._name.text().strip()
    def get_game_system(self) -> str: return self._gs.currentText().strip()
    def get_faction(self)     -> str: return self._faction.text().strip()
    def get_description(self) -> str: return self._desc.toPlainText().strip()


# ══════════════════════════════════════════════════════════════════════════════
#  _ModelPickerDialog
# ══════════════════════════════════════════════════════════════════════════════

class _ModelPickerDialog(QDialog):
    def __init__(self, context, already_linked: list[int], parent=None):
        super().__init__(parent)
        self._context       = context
        self._already       = set(already_linked)
        self._models: list  = []
        self.selected_id: int | None = None
        self.setWindowTitle("Link a Model")
        self.setMinimumWidth(460)
        self.setModal(True)
        self.setStyleSheet(f"background: {_C['bg_base']}; color: {_C['text_hi']};")
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.addWidget(_section_label("SELECT MODEL TO LINK"))

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter models…")
        self._search.setStyleSheet(_input_ss())
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        self._list = QListWidget()
        self._list.setMinimumHeight(220)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: {_C['bg_card']}; color: {_C['text_hi']};
                border: 1px solid {_C['border']}; border-radius: {_R['sm']};
                font-size: {_FS['base']}; outline: none;
            }}
            QListWidget::item {{
                padding: 7px 12px;
                border-bottom: 1px solid {_C['border_lo']};
            }}
            QListWidget::item:selected {{
                background: {_C['accent_lo']}; color: {_C['accent_text']};
            }}
            QListWidget::item:hover:!selected {{ background: {_C['bg_hover']}; }}
        """)
        lay.addWidget(self._list)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("Link Model")
        btn_box.button(QDialogButtonBox.Ok).setStyleSheet(_primary_btn_ss())
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet(_secondary_btn_ss())
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _load(self):
        svc = self._context.services.try_get("model_service")
        if svc is None:
            self._list.addItem("Model Tracker not loaded")
            return
        try:
            from plugins.model_tracker.models import ModelFilter
            self._models = svc.search_models(ModelFilter())
        except Exception:
            try:
                self._models = svc.get_all_models()
            except Exception as e:
                log.error(f"[SCHEME V2] model load: {e}")
        self._populate(self._models)

    def _populate(self, models: list):
        self._list.clear()
        for m in models:
            if m.id in self._already:
                continue
            parts = [x for x in [getattr(m, "faction", ""), getattr(m, "game_system", "")] if x]
            label = f"{m.name}  ·  {' / '.join(parts)}" if parts else m.name
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole, m.id)
            self._list.addItem(item)

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
        item = self._list.currentItem()
        if item:
            self.selected_id = item.data(Qt.UserRole)
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  SchemeV2UI  — main widget
# ══════════════════════════════════════════════════════════════════════════════

class SchemeV2UI(QWidget):
    def __init__(self, service, context, parent=None):
        super().__init__(parent)
        self._service            = service
        self._context            = context
        self._current_id: int | None = None
        self._scheme_cards: dict[int, _SchemeCard] = {}
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status)
        self._build()
        QTimer.singleShot(0, self.refresh)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Global scrollbar style
        self.setStyleSheet(f"""
            QScrollBar:vertical {{
                background: {_C['bg_base']}; width: 6px; margin: 0; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {_C['bg_active']}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {_C['border_hi']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: {_C['bg_base']}; height: 6px; margin: 0; border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {_C['bg_active']}; border-radius: 3px; min-width: 20px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

        root.addWidget(self._build_header())

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {_C['border_lo']}; }}"
        )
        splitter.addWidget(self._build_left_pane())
        splitter.addWidget(self._build_right_pane())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self._splitter = splitter
        root.addWidget(splitter, 1)

        # Status bar
        self._status_bar = QLabel("")
        self._status_bar.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['sm']};"
            f" padding: 4px 16px; border-top: 1px solid {_C['border_lo']};"
            f" background: {_C['bg_base']};"
        )
        root.addWidget(self._status_bar)

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("psHeader")
        bar.setStyleSheet(f"""
            QFrame#psHeader {{
                background: {_C['bg_base']};
                border-bottom: 1px solid {_C['border']};
            }}
        """)
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 14, 20, 14)
        row.setSpacing(12)

        dot = QFrame()
        dot.setFixedSize(4, 28)
        dot.setStyleSheet(f"background: {_C['accent']}; border-radius: 2px;")
        row.addWidget(dot)

        title = QLabel("Paint Schemes")
        title.setStyleSheet(
            f"font-size: {_FS['xl']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        row.addWidget(title)

        self._header_count = QLabel("")
        self._header_count.setStyleSheet(
            f"font-size: {_FS['sm']}; color: {_C['text_lo']};"
            " background: transparent; border: none;"
        )
        row.addWidget(self._header_count)
        row.addStretch(1)

        self._new_btn = QPushButton("+ New Scheme")
        self._new_btn.setFixedHeight(32)
        self._new_btn.setStyleSheet(_primary_btn_ss(small=True))
        self._new_btn.clicked.connect(self._on_new_scheme)
        row.addWidget(self._new_btn)

        return bar

    def _build_left_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("leftPane")
        pane.setMinimumWidth(260)
        pane.setMaximumWidth(440)
        pane.setStyleSheet(
            f"QWidget#leftPane {{ background: {_C['bg_base']}; border: none; }}"
        )
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(12, 12, 8, 12)
        lay.setSpacing(8)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search schemes…")
        self._search.setStyleSheet(_input_ss())
        self._search.textChanged.connect(self._on_filter_changed)
        lay.addWidget(self._search)

        # Game system filter
        self._gs_filter = QComboBox()
        self._gs_filter.setMinimumWidth(200)   # fits "Middle Earth Strategy Battle Game" elided
        self._gs_filter.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._gs_filter.addItem("All game systems", "")
        for gs in COMMON_GAME_SYSTEMS:
            if gs:
                self._gs_filter.addItem(gs, gs)
        self._gs_filter.setStyleSheet(_input_ss())
        self._gs_filter.currentIndexChanged.connect(self._on_filter_changed)
        lay.addWidget(self._gs_filter)

        # Scheme list
        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {_C['bg_base']}; }}"
        )

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet(f"background: {_C['bg_base']};")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._list_empty = QLabel("No schemes found.")
        self._list_empty.setAlignment(Qt.AlignCenter)
        self._list_empty.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['sm']}; font-style: italic;"
            " background: transparent; padding: 24px;"
        )

        self._list_scroll.setWidget(self._list_widget)
        lay.addWidget(self._list_scroll, 1)

        return pane

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("rightPane")
        pane.setStyleSheet(
            f"QWidget#rightPane {{ background: {_C['bg_base']}; border: none; }}"
        )
        outer = QVBoxLayout(pane)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Placeholder
        self._placeholder = QLabel(
            "Select a scheme from the list,\nor click  + New Scheme  to get started."
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['lg']}; padding: 60px 40px;"
            " background: transparent;"
        )
        self._placeholder.setWordWrap(True)
        outer.addWidget(self._placeholder, 1)

        # Detail scroll
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._detail_scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {_C['bg_base']}; }}"
        )
        self._detail_scroll.setVisible(False)

        detail = QWidget()
        detail.setStyleSheet(f"background: {_C['bg_base']};")
        dlay = QVBoxLayout(detail)
        dlay.setContentsMargins(20, 16, 20, 24)
        dlay.setSpacing(14)

        # ── Scheme name header ────────────────────────────────────────────────
        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        self._name_display = QLabel("")
        self._name_display.setStyleSheet(
            f"font-size: {_FS['3xl']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        self._name_display.setWordWrap(True)
        name_row.addWidget(self._name_display, 1)

        self._edit_meta_btn = QPushButton("✏  Edit")
        self._edit_meta_btn.setFixedHeight(30)
        self._edit_meta_btn.setStyleSheet(_secondary_btn_ss(small=True))
        self._edit_meta_btn.clicked.connect(self._on_edit_metadata)
        name_row.addWidget(self._edit_meta_btn, 0, Qt.AlignTop)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setFixedHeight(30)
        self._delete_btn.setStyleSheet(_danger_btn_ss(small=True))
        self._delete_btn.clicked.connect(self._on_delete_scheme)
        name_row.addWidget(self._delete_btn, 0, Qt.AlignTop)

        dlay.addLayout(name_row)

        # Faction + game system row
        self._meta_row = QHBoxLayout()
        self._meta_row.setSpacing(8)
        self._faction_lbl    = QLabel("")
        self._game_sys_lbl   = QLabel("")
        for lbl in (self._faction_lbl, self._game_sys_lbl):
            lbl.setStyleSheet(
                f"color: {_C['text_lo']}; font-size: {_FS['sm']};"
                " background: transparent; border: none;"
            )
        self._meta_row.addWidget(self._faction_lbl)
        self._meta_sep = QLabel("·")
        self._meta_sep.setStyleSheet(
            f"color: {_C['text_dim']}; background: transparent; border: none;"
        )
        self._meta_row.addWidget(self._meta_sep)
        self._meta_row.addWidget(self._game_sys_lbl)
        self._meta_row.addStretch(1)
        dlay.addLayout(self._meta_row)

        # Description
        self._desc_display = QLabel("")
        self._desc_display.setStyleSheet(
            f"color: {_C['text_lo']}; font-size: {_FS['sm']};"
            " background: transparent; border: none;"
        )
        self._desc_display.setWordWrap(True)
        dlay.addWidget(self._desc_display)

        # Duplicate button (subtle, below meta)
        dup_btn = QPushButton("Duplicate Scheme")
        dup_btn.setFixedHeight(26)
        dup_btn.setStyleSheet(_secondary_btn_ss(small=True))
        dup_btn.clicked.connect(self._on_duplicate_scheme)
        dlay.addWidget(dup_btn, 0, Qt.AlignLeft)

        dlay.addWidget(_hline())

        # ── Steps ─────────────────────────────────────────────────────────────
        steps_hdr = QHBoxLayout()
        steps_hdr.setSpacing(8)
        self._steps_lbl = QLabel("Steps")
        self._steps_lbl.setStyleSheet(
            f"font-size: {_FS['lg']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        steps_hdr.addWidget(self._steps_lbl)
        steps_hdr.addStretch(1)

        add_step_btn = QPushButton("+ Add Step")
        add_step_btn.setFixedHeight(28)
        add_step_btn.setStyleSheet(_primary_btn_ss(small=True))
        add_step_btn.clicked.connect(self._on_add_step)
        steps_hdr.addWidget(add_step_btn)
        dlay.addLayout(steps_hdr)

        self._steps_empty = QLabel("No steps yet — click  + Add Step  to begin.")
        self._steps_empty.setAlignment(Qt.AlignCenter)
        self._steps_empty.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['sm']}; font-style: italic;"
            " padding: 16px; background: transparent;"
        )
        dlay.addWidget(self._steps_empty)

        self._steps_container = QWidget()
        self._steps_container.setStyleSheet("background: transparent;")
        self._steps_vlay = QVBoxLayout(self._steps_container)
        self._steps_vlay.setContentsMargins(0, 0, 0, 0)
        self._steps_vlay.setSpacing(5)
        dlay.addWidget(self._steps_container)

        dlay.addWidget(_hline())

        # ── Linked Models ─────────────────────────────────────────────────────
        models_hdr = QHBoxLayout()
        models_hdr.setSpacing(8)
        models_title = QLabel("Linked Models")
        models_title.setStyleSheet(
            f"font-size: {_FS['lg']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        models_hdr.addWidget(models_title)
        models_hdr.addStretch(1)

        link_btn = QPushButton("Link Model…")
        link_btn.setFixedHeight(28)
        link_btn.setStyleSheet(_secondary_btn_ss(small=True))
        link_btn.clicked.connect(self._on_link_model)
        models_hdr.addWidget(link_btn)
        dlay.addLayout(models_hdr)

        self._models_container = QWidget()
        self._models_container.setStyleSheet("background: transparent;")
        self._models_vlay = QVBoxLayout(self._models_container)
        self._models_vlay.setContentsMargins(0, 0, 0, 0)
        self._models_vlay.setSpacing(4)
        dlay.addWidget(self._models_container)

        # ── Linked Projects ───────────────────────────────────────────────────
        dlay.addWidget(_hline())
        projects_hdr = QLabel("Linked Projects")
        projects_hdr.setStyleSheet(
            f"font-size: {_FS['lg']}; font-weight: 700; color: {_C['text_hi']};"
            " background: transparent; border: none;"
        )
        dlay.addWidget(projects_hdr)

        self._projects_container = QWidget()
        self._projects_container.setStyleSheet("background: transparent;")
        self._projects_vlay = QVBoxLayout(self._projects_container)
        self._projects_vlay.setContentsMargins(0, 0, 0, 0)
        self._projects_vlay.setSpacing(4)
        dlay.addWidget(self._projects_container)

        dlay.addStretch()

        self._detail_scroll.setWidget(detail)
        outer.addWidget(self._detail_scroll, 1)

        return pane

    # ── showEvent: set splitter sizes once we have real width ────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_splitter_set", False):
            QTimer.singleShot(0, self._set_splitter)

    def _set_splitter(self):
        if getattr(self, "_splitter_set", False):
            return
        w = self._splitter.width()
        if w > 400:
            self._splitter.setSizes([300, w - 300])
            self._splitter_set = True

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self):
        self._rebuild_list()

    def refresh_current_scheme(self):
        if self._current_id is not None:
            self._load_detail(self._current_id)

    # ── Left-pane list ────────────────────────────────────────────────────────

    def _rebuild_list(self):
        svc = self._service
        if svc is None:
            return

        try:
            schemes = svc.search_schemes(self._current_filter())
        except Exception as e:
            log.error(f"[SCHEME V2] rebuild_list: {e}")
            return

        # Count steps per scheme
        step_counts: dict[int, int] = {}
        for s in schemes:
            try:
                step_counts[s.id] = len(svc.get_steps(s.id))
            except Exception:
                step_counts[s.id] = 0

        # Update header count
        total = len(svc.get_all_schemes()) if hasattr(svc, "get_all_schemes") else len(schemes)
        self._header_count.setText(
            f"{total} scheme{'s' if total != 1 else ''}"
        )

        # Clear existing cards
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._scheme_cards.clear()

        if not schemes:
            self._list_layout.insertWidget(0, self._list_empty)
            self._list_empty.setVisible(True)
            return

        self._list_empty.setVisible(False)

        for scheme in schemes:
            selected = (scheme.id == self._current_id)
            card = _SchemeCard(scheme, step_counts.get(scheme.id, 0), selected)
            card.clicked.connect(self._on_scheme_clicked)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
            self._scheme_cards[scheme.id] = card

        self._status_bar.setText(
            f"{len(schemes)} scheme{'s' if len(schemes) != 1 else ''}"
            + (f" (filtered)" if len(schemes) < total else "")
        )

    def _current_filter(self) -> SchemeFilter:
        return SchemeFilter(
            search_text=self._search.text().strip() or None,
            game_system=self._gs_filter.currentData() or None,
        )

    def _on_filter_changed(self, *_):
        self._rebuild_list()

    def _on_scheme_clicked(self, scheme_id: int):
        self._current_id = scheme_id
        # Update card selection states
        for sid, card in self._scheme_cards.items():
            card._apply_style(sid == scheme_id)
        self._load_detail(scheme_id)

    # ── Scheme CRUD ───────────────────────────────────────────────────────────

    def _on_new_scheme(self):
        dlg = _SchemeDialog(self._context, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        if not dlg.get_name():
            return
        try:
            scheme = self._service.add_scheme(
                name        = dlg.get_name(),
                game_system = dlg.get_game_system(),
                faction     = dlg.get_faction(),
                description = dlg.get_description(),
            )
            self._emit("scheme_added", {"scheme": scheme})
            self._current_id = scheme.id
            self._rebuild_list()
            self._load_detail(scheme.id)
            self._show_success(f"Created '{scheme.name}'")
        except Exception as e:
            self._show_error(str(e))

    def _on_edit_metadata(self):
        if self._current_id is None:
            return
        scheme = self._service.get_scheme(self._current_id)
        if not scheme:
            return
        dlg = _SchemeDialog(self._context, scheme=scheme, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            updated = self._service.update_scheme(
                self._current_id,
                name        = dlg.get_name(),
                game_system = dlg.get_game_system(),
                faction     = dlg.get_faction(),
                description = dlg.get_description(),
            )
            self._emit("scheme_updated", {"scheme": updated})
            self._load_detail(self._current_id)
            self._rebuild_list()
            self._show_success("Saved.")
        except Exception as e:
            self._show_error(str(e))

    def _on_delete_scheme(self):
        if self._current_id is None:
            return
        scheme = self._service.get_scheme(self._current_id)
        if not scheme:
            return
        reply = QMessageBox.question(
            self, "Delete Scheme",
            f"Delete '{scheme.name}' and all its steps?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._service.delete_scheme(self._current_id)
            self._emit("scheme_deleted", {"scheme_id": self._current_id})
            self._current_id = None
            self._show_placeholder()
            self._rebuild_list()
            self._show_success("Scheme deleted.")
        except Exception as e:
            self._show_error(str(e))

    def _on_duplicate_scheme(self):
        if self._current_id is None:
            return
        original = self._service.get_scheme(self._current_id)
        if not original:
            return
        try:
            copy = self._service.add_scheme(
                name        = f"{original.name} (copy)",
                game_system = original.game_system,
                faction     = original.faction,
                description = original.description,
            )
            for step in self._service.get_steps(original.id):
                self._service.add_step(
                    copy.id, step.technique, step.paint_id,
                    step.paint_name, step.notes,
                )
            self._emit("scheme_added", {"scheme": copy})
            self._current_id = copy.id
            self._rebuild_list()
            self._load_detail(copy.id)
            self._show_success(f"Duplicated as '{copy.name}'")
        except Exception as e:
            self._show_error(str(e))

    # ── Detail pane ───────────────────────────────────────────────────────────

    def _load_detail(self, scheme_id: int):
        scheme = self._service.get_scheme(scheme_id)
        if not scheme:
            self._show_placeholder()
            return

        self._placeholder.setVisible(False)
        self._detail_scroll.setVisible(True)

        self._name_display.setText(scheme.name)

        has_faction = bool(scheme.faction)
        has_gs      = bool(scheme.game_system)
        self._faction_lbl.setText(scheme.faction or "")
        self._game_sys_lbl.setText(scheme.game_system or "")
        self._faction_lbl.setVisible(has_faction)
        self._meta_sep.setVisible(has_faction and has_gs)
        self._game_sys_lbl.setVisible(has_gs)

        self._desc_display.setText(scheme.description or "")
        self._desc_display.setVisible(bool(scheme.description))

        steps = self._service.get_steps(scheme_id)
        self._steps_lbl.setText(f"Steps  ({len(steps)})")
        self._steps_empty.setVisible(len(steps) == 0)
        self._steps_container.setVisible(len(steps) > 0)
        self._rebuild_steps(steps, scheme_id)
        self._rebuild_linked_models(scheme_id)
        self._rebuild_linked_projects(scheme_id)

    def _show_placeholder(self):
        self._detail_scroll.setVisible(False)
        self._placeholder.setVisible(True)

    # ── Steps ─────────────────────────────────────────────────────────────────

    def _rebuild_steps(self, steps: list, scheme_id: int):
        # Clear
        while self._steps_vlay.count():
            item = self._steps_vlay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Gather paint colours
        paint_colours: dict[int, str] = {}
        paint_svc = self._context.services.try_get("paint_service")
        if paint_svc:
            try:
                for p in paint_svc.get_all_paints():
                    paint_colours[p.id] = getattr(p, "color", None)
            except Exception:
                pass

        n = len(steps)
        for i, step in enumerate(steps):
            colour = paint_colours.get(step.paint_id) if step.paint_id else None
            card = _StepCard(step, colour, is_first=(i == 0), is_last=(i == n - 1))
            card.edit_requested.connect(self._on_edit_step)
            card.delete_requested.connect(self._on_delete_step)
            card.move_requested.connect(self._on_move_step)
            self._steps_vlay.addWidget(card)

    def _on_add_step(self):
        if self._current_id is None:
            return
        dlg = _StepDialog(self._context, self._current_id, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self._service.add_step(
                self._current_id,
                dlg.get_technique(), dlg.get_paint_id(),
                dlg.get_paint_name(), dlg.get_notes(),
            )
            self._load_detail(self._current_id)
            self._rebuild_list()
        except Exception as e:
            self._show_error(str(e))

    def _on_edit_step(self, step):
        dlg = _StepDialog(self._context, step.scheme_id, step=step, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self._service.update_step(
                step.id,
                technique  = dlg.get_technique(),
                paint_id   = dlg.get_paint_id(),
                paint_name = dlg.get_paint_name(),
                notes      = dlg.get_notes(),
            )
            self._load_detail(step.scheme_id)
        except Exception as e:
            self._show_error(str(e))

    def _on_delete_step(self, step):
        reply = QMessageBox.question(
            self, "Remove Step",
            f"Remove Step {step.step_order} ({step.technique})?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._service.delete_step(step.id)
            self._load_detail(step.scheme_id)
            self._rebuild_list()
        except Exception as e:
            self._show_error(str(e))

    def _on_move_step(self, step, direction: int):
        try:
            steps = self._service.get_steps(step.scheme_id)
            ids   = [s.id for s in steps]
            idx   = ids.index(step.id)
            new_i = idx + direction
            if new_i < 0 or new_i >= len(ids):
                return
            ids[idx], ids[new_i] = ids[new_i], ids[idx]
            self._service.reorder_steps(step.scheme_id, ids)
            self._load_detail(step.scheme_id)
        except Exception as e:
            self._show_error(str(e))

    # ── Linked models ─────────────────────────────────────────────────────────

    def _rebuild_linked_models(self, scheme_id: int):
        while self._models_vlay.count():
            item = self._models_vlay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        linked_ids = self._service.get_linked_models(scheme_id)
        if not linked_ids:
            lbl = QLabel("No models linked yet.")
            lbl.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: {_FS['sm']}; font-style: italic;"
                " background: transparent; padding: 4px 0;"
            )
            self._models_vlay.addWidget(lbl)
            return

        model_map: dict[int, object] = {}
        model_svc = self._context.services.try_get("model_service")
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
            row_frame = QFrame()
            row_frame.setObjectName("modelRow")
            row_frame.setStyleSheet(f"""
                QFrame#modelRow {{
                    background: {_C['bg_card']};
                    border: 1px solid {_C['border']};
                    border-radius: {_R['sm']};
                }}
            """)
            row = QHBoxLayout(row_frame)
            row.setContentsMargins(12, 7, 10, 7)
            row.setSpacing(8)

            m = model_map.get(mid)
            if m:
                parts = [x for x in [getattr(m, "faction", ""), getattr(m, "game_system", "")] if x]
                name_lbl = QLabel(m.name)
                name_lbl.setStyleSheet(
                    f"font-size: {_FS['sm']}; font-weight: 600; color: {_C['text_hi']};"
                    " background: transparent; border: none;"
                )
                row.addWidget(name_lbl)
                if parts:
                    sub_lbl = QLabel(" · ".join(parts))
                    sub_lbl.setStyleSheet(
                        f"font-size: {_FS['xs']}; color: {_C['text_lo']};"
                        " background: transparent; border: none;"
                    )
                    row.addWidget(sub_lbl)
            else:
                lbl = QLabel(f"Model #{mid}")
                lbl.setStyleSheet(
                    f"font-size: {_FS['sm']}; color: {_C['text_lo']};"
                    " background: transparent; border: none;"
                )
                row.addWidget(lbl)

            row.addStretch(1)

            def _make_unlink(model_id, sid=scheme_id):
                def _f():
                    try:
                        self._service.unlink_model(sid, model_id)
                        self._rebuild_linked_models(sid)
                    except Exception as e:
                        self._show_error(str(e))
                return _f

            unlink = QPushButton("Unlink")
            unlink.setFixedHeight(22)
            unlink.setStyleSheet(_secondary_btn_ss(small=True))
            unlink.clicked.connect(_make_unlink(mid))
            row.addWidget(unlink)

            self._models_vlay.addWidget(row_frame)

    def _on_link_model(self):
        if self._current_id is None:
            return
        already = self._service.get_linked_models(self._current_id)
        dlg = _ModelPickerDialog(self._context, already, parent=self)
        if dlg.exec() != QDialog.Accepted or dlg.selected_id is None:
            return
        try:
            self._service.link_model(self._current_id, dlg.selected_id)
            self._rebuild_linked_models(self._current_id)
        except Exception as e:
            self._show_error(str(e))

    # ── Linked projects ───────────────────────────────────────────────────────

    def _rebuild_linked_projects(self, scheme_id: int):
        while self._projects_vlay.count():
            item = self._projects_vlay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        proj_svc = self._context.services.try_get("project_service")
        if proj_svc is None:
            lbl = QLabel("Project Tracker not loaded.")
            lbl.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: {_FS['sm']}; font-style: italic;"
                " background: transparent;"
            )
            self._projects_vlay.addWidget(lbl)
            return

        try:
            projects = proj_svc.get_projects_for_entity("scheme", scheme_id)
        except Exception:
            projects = []

        if not projects:
            lbl = QLabel("Not linked to any project.")
            lbl.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: {_FS['sm']}; font-style: italic;"
                " background: transparent;"
            )
            self._projects_vlay.addWidget(lbl)
            return

        for p in projects:
            chip = QFrame()
            chip.setObjectName("projChip")
            chip.setStyleSheet(f"""
                QFrame#projChip {{
                    background: {_C['bg_card']};
                    border: 1px solid {_C['border']};
                    border-radius: {_R['sm']};
                }}
            """)
            crow = QHBoxLayout(chip)
            crow.setContentsMargins(10, 6, 10, 6)
            crow.setSpacing(8)

            icon = getattr(p, "icon", "📁")
            name = getattr(p, "name", "Project")
            lbl = QLabel(f"{icon}  {name}")
            lbl.setStyleSheet(
                f"font-size: {_FS['sm']}; color: {_C['text_mid']};"
                " background: transparent; border: none;"
            )
            crow.addWidget(lbl)
            crow.addStretch(1)

            nav_btn = QPushButton("→ Open")
            nav_btn.setFixedHeight(22)
            nav_btn.setStyleSheet(_ghost_btn_ss())

            def _make_nav(pid="project_tracker"):
                def _f():
                    self._emit("dashboard_navigate", {"plugin_id": pid})
                return _f

            nav_btn.clicked.connect(_make_nav())
            crow.addWidget(nav_btn)
            self._projects_vlay.addWidget(chip)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _emit(self, event: str, payload: dict):
        bus = getattr(self._context, "event_bus", None)
        if bus:
            try:
                bus.emit(event, payload)
            except Exception:
                pass

    def _show_success(self, msg: str):
        self._status_bar.setStyleSheet(
            f"color: {_C['success']}; font-size: {_FS['sm']};"
            f" padding: 4px 16px; border-top: 1px solid {_C['border_lo']};"
            f" background: {_C['bg_base']};"
        )
        self._status_bar.setText(f"✓  {msg}")
        self._status_timer.start(3000)

    def _show_error(self, msg: str):
        self._status_bar.setStyleSheet(
            f"color: {_C['danger']}; font-size: {_FS['sm']};"
            f" padding: 4px 16px; border-top: 1px solid {_C['border_lo']};"
            f" background: {_C['bg_base']};"
        )
        self._status_bar.setText(f"✗  {msg}")
        self._status_timer.start(5000)

    def _clear_status(self):
        self._status_bar.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: {_FS['sm']};"
            f" padding: 4px 16px; border-top: 1px solid {_C['border_lo']};"
            f" background: {_C['bg_base']};"
        )
        self._status_bar.setText("")
