"""
Map UI — Campaign Tracker v2.

Full interactive map management panel with:
- Map list sidebar with layer controls and token library
- Grid-based canvas with fog of war
- Token editor and map settings dialogs
- Auto-save with 1s debounce
- Per-column/per-row drag resize
- Custom layer management
"""
from __future__ import annotations

import json
import logging
import math
import shutil
import sys
import uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QMimeData, QByteArray, QPointF
from PySide6.QtGui import (
    QPixmap, QColor, QDrag, QFont, QPainter, QPen, QBrush,
    QPainterPath, QCursor,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QListWidget, QListWidgetItem, QSplitter, QDialog,
    QDialogButtonBox, QLineEdit, QComboBox, QSpinBox, QTextEdit,
    QStackedWidget, QCheckBox, QFormLayout, QMessageBox, QFileDialog,
    QSizePolicy, QSlider, QDoubleSpinBox, QColorDialog, QGroupBox,
    QToolButton, QButtonGroup, QGridLayout, QAbstractItemView,
    QGraphicsView, QInputDialog, QTabWidget,
)
from PySide6.QtGui import QIcon

from .map_canvas import (
    MapView, MapScene, MapTool, MapLayer, LAYER_Z, TokenItem, snap_to_grid,
)

log = logging.getLogger(__name__)

# ── Palette ────────────────────────────────────────────────────────────────────
_BG      = "#1c1c1c"
_BG2     = "#212121"
_BG3     = "#282828"
_SIDEBAR = "#161616"
_BORDER  = "#2e2e2e"
_BORDER2 = "#3a3a3a"
_FG      = "#f0f0f0"
_FG_MID  = "#a0a0a0"
_FG_DIM  = "#606060"
_ACCENT  = "#4f9eff"
_SUCCESS = "#3dba6e"
_DANGER  = "#e05555"
_WARN    = "#e07800"
_GOLD    = "#f0c040"

# ── Constants ──────────────────────────────────────────────────────────────────
TOKEN_TYPES = ["Character", "NPC", "Monster", "Object", "Effect", "Area"]
TOKEN_COLORS = [
    "#4f9eff", "#3dba6e", "#e05555", "#e07800",
    "#9b59b6", "#f0c040", "#e91e8c", "#00bcd4",
]
CONDITIONS = [
    "Blinded", "Charmed", "Deafened", "Exhausted", "Frightened",
    "Grappled", "Incapacitated", "Invisible", "Paralyzed", "Petrified",
    "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious",
]

LAYER_DEFS = [
    (MapLayer.BACKGROUND, "🖼", "Background"),
    (MapLayer.TERRAIN,    "🌿", "Terrain"),
    (MapLayer.OBJECTS,    "📦", "Objects"),
    (MapLayer.TOKENS,     "🧙", "Tokens"),
    (MapLayer.FOG,        "🌫", "Fog"),
    (MapLayer.NOTES,      "📝", "Notes/Markers"),
]

BUILTIN_LAYERS = [
    ("background", "🖼", "Background"),
    ("terrain",    "🌿", "Terrain"),
    ("objects",    "📦", "Objects"),
    ("tokens",     "🧙", "Tokens"),
    ("fog",        "🌫", "Fog"),
    ("notes",      "📝", "Notes"),
]

# ── Shared style snippets ──────────────────────────────────────────────────────
_SPIN_STYLE = (
    f"QSpinBox {{ background:{_BG}; color:{_FG}; border:1px solid {_BORDER2}; "
    f"border-radius:4px; padding:2px 6px; font-size:11px; min-height:26px; }}"
    f"QSpinBox:focus {{ border-color:{_ACCENT}; }}"
    f"QSpinBox::up-button, QSpinBox::down-button {{ width:16px; background:{_BG3}; border:none; }}"
)

_DIALOG_STYLE = f"""
    QDialog {{ background:{_BG2}; color:{_FG}; }}
    QLabel {{ color:{_FG_MID}; background:transparent; border:none; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QComboBox {{
        background:{_BG3}; color:{_FG}; border:1px solid {_BORDER2};
        border-radius:4px; padding:4px 8px; font-size:12px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QTextEdit:focus, QComboBox:focus {{ border-color:{_ACCENT}; }}
    QComboBox::drop-down {{ border:none; width:20px; }}
    QComboBox::down-arrow {{ image:none; }}
    QComboBox QAbstractItemView {{
        background:{_BG3}; color:{_FG}; border:1px solid {_BORDER2};
        selection-background-color:{_ACCENT};
    }}
    QPushButton {{
        background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2};
        border-radius:4px; padding:6px 14px; font-size:12px;
    }}
    QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}
    QCheckBox {{ color:{_FG_MID}; spacing:6px; }}
    QCheckBox::indicator {{
        width:16px; height:16px; border:1px solid {_BORDER2};
        border-radius:3px; background:{_BG3};
    }}
    QCheckBox::indicator:checked {{ background:{_ACCENT}; border-color:{_ACCENT}; }}
    QGroupBox {{
        color:{_FG_MID}; border:1px solid {_BORDER}; border-radius:4px;
        margin-top:8px; font-size:11px;
    }}
    QGroupBox::title {{ subcontrol-origin:margin; left:8px; }}
    QListWidget {{
        background:{_BG3}; color:{_FG}; border:1px solid {_BORDER2};
        border-radius:4px; outline:none;
    }}
    QListWidget::item {{ padding:4px 8px; }}
    QListWidget::item:selected {{ background:{_ACCENT}; color:#fff; }}
    QListWidget::item:hover {{ background:{_BG2}; }}
    QScrollBar:vertical {{ background:{_BG}; width:6px; border:none; }}
    QScrollBar::handle:vertical {{ background:{_BORDER2}; border-radius:3px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
    QSlider::groove:horizontal {{
        background:{_BG3}; height:4px; border-radius:2px;
    }}
    QSlider::handle:horizontal {{
        background:{_ACCENT}; width:12px; height:12px;
        border-radius:6px; margin:-4px 0;
    }}
    QSlider::sub-page:horizontal {{ background:{_ACCENT}; border-radius:2px; }}
"""


def _primary_btn_style() -> str:
    return (
        f"QPushButton {{ background:{_ACCENT}; color:#fff; border:none; "
        f"border-radius:4px; padding:6px 18px; font-weight:600; font-size:12px; }}"
        f"QPushButton:hover {{ background:#6ab4ff; }}"
    )


def _tb_btn_style(active: bool = False) -> str:
    if active:
        return (
            f"QPushButton {{ background:{_ACCENT}; color:#fff; border:none; "
            f"border-radius:4px; padding:0 10px; font-size:11px; min-height:30px; }}"
        )
    return (
        f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2}; "
        f"border-radius:4px; padding:0 10px; font-size:11px; min-height:30px; }}"
        f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; border-color:{_BORDER2}; }}"
        f"QPushButton:checked {{ background:{_ACCENT}; color:#fff; border:none; }}"
    )


def _vsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFixedWidth(1)
    f.setFixedHeight(24)
    f.setStyleSheet(f"background:{_BORDER2}; border:none; margin:0 4px;")
    return f


# ── File helpers ───────────────────────────────────────────────────────────────

def _user_data_dir() -> Path:
    import os
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home()))
        else:
            base = Path.home() / "Library" / "Application Support"
        return base / "AdeptusCraftmatica"
    return Path(__file__).parent.parent.parent


def _maps_dir() -> Path:
    d = _user_data_dir() / "maps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tokens_dir() -> Path:
    d = _user_data_dir() / "tokens"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _copy_image(src_path: str, dest_dir: Path) -> str:
    """Copy an image to dest_dir with a unique name; return new absolute path."""
    src = Path(src_path)
    if not src.exists():
        return src_path
    dest = dest_dir / f"{uuid.uuid4().hex}{src.suffix.lower()}"
    shutil.copy2(src, dest)
    return str(dest)


# ══════════════════════════════════════════════════════════════════════════════
#  _ColorSwatch — clickable color circle button
# ══════════════════════════════════════════════════════════════════════════════

class _ColorSwatch(QPushButton):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(26, 26)
        self.setCheckable(True)
        self._refresh()

    def _refresh(self):
        self.setStyleSheet(
            f"QPushButton {{ background:{self._color}; border-radius:13px; border:2px solid {_BORDER2}; }}"
            f"QPushButton:checked {{ border:2px solid {_FG}; }}"
        )

    @property
    def color(self) -> str:
        return self._color


# ══════════════════════════════════════════════════════════════════════════════
#  _TokenPreviewWidget — draws token avatar (used in library items + dialogs)
# ══════════════════════════════════════════════════════════════════════════════

class _TokenPreviewWidget(QWidget):
    def __init__(self, name: str = "", color: str = "#4f9eff",
                 image_path: str = "", size: int = 48, parent=None):
        super().__init__(parent)
        self._name  = name
        self._color = color
        self._image_path = image_path
        self._size  = size
        self._pixmap: Optional[QPixmap] = None
        self.setFixedSize(size, size)
        self._reload()

    def set_data(self, name: str, color: str, image_path: str = ""):
        self._name  = name
        self._color = color
        self._image_path = image_path
        self._reload()
        self.update()

    def _reload(self):
        if self._image_path and Path(self._image_path).exists():
            pm = QPixmap(self._image_path)
            if not pm.isNull():
                self._pixmap = pm.scaled(
                    self._size, self._size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                return
        self._pixmap = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size

        if self._pixmap and not self._pixmap.isNull():
            path = QPainterPath()
            path.addRoundedRect(0, 0, s, s, 6, 6)
            p.setClipPath(path)
            p.drawPixmap(
                (s - self._pixmap.width()) // 2,
                (s - self._pixmap.height()) // 2,
                self._pixmap,
            )
        else:
            radius = s * 0.45
            p.setBrush(QBrush(QColor(self._color)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(s / 2, s / 2), radius, radius)

            words = self._name.split() if self._name else []
            if len(words) >= 2:
                initials = words[0][0].upper() + words[-1][0].upper()
            elif words:
                initials = words[0][:2].upper()
            else:
                initials = "?"
            font = QFont()
            font.setPixelSize(max(8, int(s * 0.38)))
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor("#ffffff"))
            from PySide6.QtCore import QRectF as _RF
            p.drawText(_RF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, initials)

        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  _TokenLibraryItem — draggable widget in the token library panel
# ══════════════════════════════════════════════════════════════════════════════

class _TokenLibraryItem(QFrame):
    remove_requested = Signal(int)  # lib_id

    def __init__(self, lib_data: dict, parent=None):
        super().__init__(parent)
        self._lib_data = dict(lib_data)
        self.setFixedSize(72, 90)
        self.setStyleSheet(
            f"_TokenLibraryItem {{ background:{_BG3}; border:1px solid {_BORDER}; border-radius:6px; }}"
            f"_TokenLibraryItem:hover {{ border:1px solid {_BORDER2}; background:{_BG2}; }}"
        )
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 4)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._preview = _TokenPreviewWidget(
            name=self._lib_data.get("name", ""),
            color=self._lib_data.get("color", "#4f9eff"),
            image_path=self._lib_data.get("image_path", ""),
            size=48,
        )
        lay.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignHCenter)

        name_lbl = QLabel(self._lib_data.get("name", ""))
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        name_lbl.setMaximumWidth(68)
        name_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:9px;")
        name_lbl.setWordWrap(False)
        fm = name_lbl.fontMetrics()
        name_lbl.setText(
            fm.elidedText(
                self._lib_data.get("name", ""), Qt.TextElideMode.ElideRight, 68
            )
        )
        lay.addWidget(name_lbl, 0, Qt.AlignmentFlag.AlignHCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and hasattr(self, "_drag_start")
        ):
            if (event.pos() - self._drag_start).manhattanLength() > 8:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData(
                    "application/x-craftmatica-token",
                    QByteArray(json.dumps(self._lib_data).encode("utf-8")),
                )
                drag.setMimeData(mime)
                pm = QPixmap(self._preview.size())
                self._preview.render(pm)
                drag.setPixmap(pm)
                drag.setHotSpot(pm.rect().center())
                drag.exec(Qt.DropAction.CopyAction)
        super().mouseMoveEvent(event)

    def _ctx_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{_BG3}; color:{_FG}; border:1px solid {_BORDER2}; }}"
            f"QMenu::item:selected {{ background:{_ACCENT}; color:#fff; }}"
        )
        rem = menu.addAction("Remove from library")
        if menu.exec(self.mapToGlobal(pos)) == rem:
            self.remove_requested.emit(self._lib_data.get("id", -1))


# ══════════════════════════════════════════════════════════════════════════════
#  _TokenDialog — create / edit a map token
# ══════════════════════════════════════════════════════════════════════════════

class _TokenDialog(QDialog):
    def __init__(self, token_data: Optional[dict] = None,
                 lib_mode: bool = False,
                 campaign_id: Optional[int] = None,
                 parent=None):
        super().__init__(parent)
        self._data = dict(token_data) if token_data else {}
        self._lib_mode = lib_mode
        self._campaign_id = campaign_id
        self._image_path = self._data.get("image_path", "")
        self._selected_color = self._data.get("color", TOKEN_COLORS[0])
        self.setWindowTitle("Edit Token" if token_data else "New Token")
        self.setMinimumWidth(460)
        self.setStyleSheet(_DIALOG_STYLE)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 16)

        # Name + type
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Name:"))
        self._name = QLineEdit(self._data.get("name", ""))
        self._name.setPlaceholderText("Token name…")
        row1.addWidget(self._name, 1)
        row1.addSpacing(12)
        row1.addWidget(QLabel("Type:"))
        self._type = QComboBox()
        for t in TOKEN_TYPES:
            self._type.addItem(t)
        cur_type = self._data.get("token_type", "Character")
        idx = TOKEN_TYPES.index(cur_type) if cur_type in TOKEN_TYPES else 0
        self._type.setCurrentIndex(idx)
        row1.addWidget(self._type)
        root.addLayout(row1)

        # Color swatches
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color:"))
        self._color_group = QButtonGroup(self)
        self._color_group.setExclusive(True)
        for c in TOKEN_COLORS:
            sw = _ColorSwatch(c)
            sw.setChecked(c == self._selected_color)
            sw.clicked.connect(lambda _, col=c: self._set_color(col))
            self._color_group.addButton(sw)
            color_row.addWidget(sw)
        color_row.addStretch()
        root.addLayout(color_row)

        # Image
        img_row = QHBoxLayout()
        img_row.addWidget(QLabel("Image:"))
        self._img_label = QLabel(
            Path(self._image_path).name if self._image_path else "No image"
        )
        self._img_label.setStyleSheet(f"color:{_FG_MID}; font-size:10px;")
        self._img_label.setMaximumWidth(200)
        img_row.addWidget(self._img_label, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse_image)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(28)
        clear_btn.clicked.connect(self._clear_image)
        img_row.addWidget(browse_btn)
        img_row.addWidget(clear_btn)
        root.addLayout(img_row)

        # Preview
        self._preview = _TokenPreviewWidget(
            name=self._data.get("name", ""),
            color=self._selected_color,
            image_path=self._image_path,
            size=56,
        )
        p_row = QHBoxLayout()
        p_row.addWidget(QLabel("Preview:"))
        p_row.addWidget(self._preview)
        p_row.addStretch()
        root.addLayout(p_row)
        self._name.textChanged.connect(self._refresh_preview)

        # Size
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Size:"))
        size_row.addWidget(QLabel("W:"))
        self._w_spin = QDoubleSpinBox()
        self._w_spin.setRange(0.5, 10.0)
        self._w_spin.setSingleStep(0.5)
        self._w_spin.setValue(float(self._data.get("cell_width", 1.0)))
        size_row.addWidget(self._w_spin)
        size_row.addWidget(QLabel("x H:"))
        self._h_spin = QDoubleSpinBox()
        self._h_spin.setRange(0.5, 10.0)
        self._h_spin.setSingleStep(0.5)
        self._h_spin.setValue(float(self._data.get("cell_height", 1.0)))
        size_row.addWidget(self._h_spin)
        size_row.addWidget(QLabel("cells"))
        size_row.addStretch()
        root.addLayout(size_row)

        # HP
        hp_row = QHBoxLayout()
        hp_row.addWidget(QLabel("HP:"))
        hp_row.addWidget(QLabel("Current:"))
        self._hp_cur = QSpinBox()
        self._hp_cur.setRange(0, 99999)
        self._hp_cur.setValue(int(self._data.get("hp_current", 0)))
        hp_row.addWidget(self._hp_cur)
        hp_row.addWidget(QLabel("/ Max:"))
        self._hp_max = QSpinBox()
        self._hp_max.setRange(0, 99999)
        self._hp_max.setValue(int(self._data.get("hp_max", 0)))
        hp_row.addWidget(self._hp_max)
        hp_row.addStretch()
        root.addLayout(hp_row)

        # Conditions
        root.addWidget(QLabel("Conditions:"))
        self._cond_list = QListWidget()
        self._cond_list.setMaximumHeight(100)
        self._cond_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        current_conds = self._data.get("conditions_json", [])
        for c in CONDITIONS:
            item = QListWidgetItem(c)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if c in current_conds else Qt.CheckState.Unchecked
            )
            self._cond_list.addItem(item)
        root.addWidget(self._cond_list)

        if not self._lib_mode:
            self._save_lib = QCheckBox("Save to token library")
            root.addWidget(self._save_lib)

        # Notes
        root.addWidget(QLabel("Notes:"))
        self._notes = QTextEdit(self._data.get("notes", ""))
        self._notes.setMaximumHeight(60)
        root.addWidget(self._notes)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(_primary_btn_style())
        save_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    def _set_color(self, color: str):
        self._selected_color = color
        self._refresh_preview()

    def _refresh_preview(self):
        self._preview.set_data(
            self._name.text(), self._selected_color, self._image_path
        )

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Token Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
        )
        if path:
            new_path = _copy_image(path, _tokens_dir())
            self._image_path = new_path
            self._img_label.setText(Path(new_path).name)
            self._refresh_preview()

    def _clear_image(self):
        self._image_path = ""
        self._img_label.setText("No image")
        self._refresh_preview()

    def _on_accept(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Token name is required.")
            return
        self.accept()

    def result_data(self) -> dict:
        conditions = []
        for i in range(self._cond_list.count()):
            item = self._cond_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                conditions.append(item.text())
        d = dict(self._data)
        d.update({
            "name":            self._name.text().strip(),
            "token_type":      self._type.currentText(),
            "color":           self._selected_color,
            "image_path":      self._image_path,
            "cell_width":      self._w_spin.value(),
            "cell_height":     self._h_spin.value(),
            "hp_current":      self._hp_cur.value(),
            "hp_max":          self._hp_max.value(),
            "conditions_json": conditions,
            "notes":           self._notes.toPlainText().strip(),
        })
        return d

    def save_to_library(self) -> bool:
        if self._lib_mode:
            return True
        return hasattr(self, "_save_lib") and self._save_lib.isChecked()


# ══════════════════════════════════════════════════════════════════════════════
#  _MapSettingsDialog
# ══════════════════════════════════════════════════════════════════════════════

class _MapSettingsDialog(QDialog):
    def __init__(self, map_data: dict, image_w: int = 0, image_h: int = 0, parent=None):
        super().__init__(parent)
        self._map_data = dict(map_data)
        self._image_w  = image_w
        self._image_h  = image_h
        self._grid_color = map_data.get("grid_color", "#ffffff")
        self.setWindowTitle("Map Settings")
        self.setMinimumWidth(460)
        self.setStyleSheet(_DIALOG_STYLE)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 16)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._map_name = QLineEdit(self._map_data.get("name", "Untitled Map"))
        form.addRow("Map Name:", self._map_name)

        # Grid group
        grid_box = QGroupBox("Grid")
        glay = QFormLayout(grid_box)
        glay.setSpacing(8)
        glay.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._grid_enabled = QCheckBox("Enabled")
        self._grid_enabled.setChecked(bool(self._map_data.get("grid_enabled", True)))
        glay.addRow("", self._grid_enabled)

        self._cell_size = QSpinBox()
        self._cell_size.setRange(5, 500)
        self._cell_size.setValue(int(self._map_data.get("grid_size", 50)))
        glay.addRow("Cell size (px):", self._cell_size)

        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(0, 999)
        self._cols_spin.setValue(int(self._map_data.get("grid_cols", 0)))
        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(0, 999)
        self._rows_spin.setValue(int(self._map_data.get("grid_rows", 0)))
        cr_row = QHBoxLayout()
        cr_row.addWidget(QLabel("Cols:"))
        cr_row.addWidget(self._cols_spin)
        cr_row.addWidget(QLabel("Rows:"))
        cr_row.addWidget(self._rows_spin)
        auto_btn = QPushButton("Auto-calc")
        auto_btn.setFixedHeight(26)
        auto_btn.clicked.connect(self._auto_calc)
        cr_row.addWidget(auto_btn)
        if self._image_w > 0 and self._image_h > 0:
            fit_btn = QPushButton("Fit to Image")
            fit_btn.setFixedHeight(26)
            fit_btn.clicked.connect(self._fit_to_image)
            cr_row.addWidget(fit_btn)
        cr_row.addStretch()
        glay.addRow("Dimensions:", cr_row)

        self._offset_x = QSpinBox()
        self._offset_x.setRange(-500, 500)
        self._offset_x.setValue(int(self._map_data.get("grid_offset_x", 0)))
        self._offset_y = QSpinBox()
        self._offset_y.setRange(-500, 500)
        self._offset_y.setValue(int(self._map_data.get("grid_offset_y", 0)))
        off_row = QHBoxLayout()
        off_row.addWidget(QLabel("X:"))
        off_row.addWidget(self._offset_x)
        off_row.addWidget(QLabel("Y:"))
        off_row.addWidget(self._offset_y)
        off_row.addStretch()
        glay.addRow("Offset:", off_row)

        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(80, 26)
        self._color_btn.clicked.connect(self._pick_color)
        self._refresh_color_btn()
        glay.addRow("Grid color:", self._color_btn)

        op_row = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(int(float(self._map_data.get("grid_opacity", 0.3)) * 100))
        self._opacity_lbl = QLabel(f"{self._opacity_slider.value()}%")
        self._opacity_lbl.setFixedWidth(34)
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_lbl.setText(f"{v}%")
        )
        op_row.addWidget(self._opacity_slider, 1)
        op_row.addWidget(self._opacity_lbl)
        glay.addRow("Opacity:", op_row)
        form.addRow(grid_box)

        # Fog group
        fog_box = QGroupBox("Fog of War")
        flay = QFormLayout(fog_box)
        self._fog_enabled = QCheckBox("Enabled")
        self._fog_enabled.setChecked(bool(self._map_data.get("fog_enabled", False)))
        flay.addRow("", self._fog_enabled)
        form.addRow(fog_box)

        # Auto-align
        if self._image_w > 0 and self._image_h > 0:
            align_box = QGroupBox("Auto-Align Grid")
            alay = QVBoxLayout(align_box)
            alay.setSpacing(6)
            auto_row2 = QHBoxLayout()
            auto_row2.addWidget(QLabel("Columns:"))
            self._align_cols = QSpinBox()
            self._align_cols.setRange(1, 999)
            self._align_cols.setValue(
                max(1, int(self._map_data.get("grid_cols", 0)) or
                    max(1, self._image_w // max(1, int(self._map_data.get("grid_size", 50)))))
            )
            auto_row2.addWidget(self._align_cols)
            auto_row2.addWidget(QLabel("x"))
            self._align_rows = QSpinBox()
            self._align_rows.setRange(1, 999)
            self._align_rows.setValue(
                max(1, int(self._map_data.get("grid_rows", 0)) or
                    max(1, self._image_h // max(1, int(self._map_data.get("grid_size", 50)))))
            )
            auto_row2.addWidget(self._align_rows)
            auto_row2.addWidget(QLabel("rows"))
            calc_btn = QPushButton("Calculate Cell Size")
            calc_btn.setFixedHeight(26)
            calc_btn.clicked.connect(self._auto_calc_from_cols)
            auto_row2.addWidget(calc_btn)
            auto_row2.addStretch()
            alay.addLayout(auto_row2)
            tip = QLabel("Tip: Use the Align Grid tool (📐) on the canvas for pixel-perfect alignment.")
            tip.setStyleSheet(f"color:{_FG_DIM}; font-size:10px;")
            tip.setWordWrap(True)
            alay.addWidget(tip)
            form.addRow(align_box)
        else:
            self._align_cols = None
            self._align_rows = None

        self._notes = QTextEdit(self._map_data.get("notes", ""))
        self._notes.setMaximumHeight(70)
        form.addRow("Notes:", self._notes)
        root.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(_primary_btn_style())
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    def _auto_calc(self):
        cols = self._cols_spin.value()
        if cols > 0 and self._image_w > 0:
            self._cell_size.setValue(max(5, self._image_w // cols))

    def _fit_to_image(self):
        cols = self._cols_spin.value()
        if cols > 0 and self._image_w > 0:
            self._cell_size.setValue(max(5, self._image_w // cols))

    def _auto_calc_from_cols(self):
        if self._align_cols is None:
            return
        cols = self._align_cols.value()
        rows = self._align_rows.value()
        if cols > 0 and self._image_w > 0:
            cell_w = max(5, self._image_w // cols)
            self._cell_size.setValue(cell_w)
        self._cols_spin.setValue(cols)
        self._rows_spin.setValue(rows)

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._grid_color), self, "Grid Color")
        if c.isValid():
            self._grid_color = c.name()
            self._refresh_color_btn()

    def _refresh_color_btn(self):
        self._color_btn.setStyleSheet(
            f"QPushButton {{ background:{self._grid_color}; border:1px solid {_BORDER2}; "
            f"border-radius:3px; color:{_FG}; font-size:10px; }}"
        )
        self._color_btn.setText(self._grid_color)

    def result_data(self) -> dict:
        d = dict(self._map_data)
        d.update({
            "name":          self._map_name.text().strip() or "Untitled Map",
            "grid_enabled":  int(self._grid_enabled.isChecked()),
            "grid_size":     self._cell_size.value(),
            "grid_cols":     self._cols_spin.value(),
            "grid_rows":     self._rows_spin.value(),
            "grid_offset_x": self._offset_x.value(),
            "grid_offset_y": self._offset_y.value(),
            "grid_color":    self._grid_color,
            "grid_opacity":  self._opacity_slider.value() / 100.0,
            "fog_enabled":   int(self._fog_enabled.isChecked()),
            "notes":         self._notes.toPlainText().strip(),
        })
        return d


# ══════════════════════════════════════════════════════════════════════════════
#  _AddMapDialog
# ══════════════════════════════════════════════════════════════════════════════

class _AddMapDialog(QDialog):
    def __init__(self, prefill_image: str = "", parent=None):
        super().__init__(parent)
        self._image_path = ""
        self._image_w    = 0
        self._image_h    = 0
        self.setWindowTitle("New Map")
        self.setMinimumWidth(420)
        self.setStyleSheet(_DIALOG_STYLE)
        self._build()
        if prefill_image:
            self._set_image(prefill_image)

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 20, 20, 16)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name = QLineEdit("Untitled Map")
        form.addRow("Map Name:", self._name)

        img_row = QHBoxLayout()
        self._img_label = QLabel("No image selected")
        self._img_label.setStyleSheet(f"color:{_FG_MID}; font-size:10px;")
        img_row.addWidget(self._img_label, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse)
        img_row.addWidget(browse_btn)
        form.addRow("Background:", img_row)

        self._grid_size = QSpinBox()
        self._grid_size.setRange(5, 500)
        self._grid_size.setValue(50)
        form.addRow("Grid cell size (px):", self._grid_size)

        cols_row = QHBoxLayout()
        self._cols = QSpinBox()
        self._cols.setRange(0, 999)
        cols_row.addWidget(QLabel("Cols:"))
        cols_row.addWidget(self._cols)
        self._rows = QSpinBox()
        self._rows.setRange(0, 999)
        cols_row.addWidget(QLabel("Rows:"))
        cols_row.addWidget(self._rows)
        auto_btn = QPushButton("Auto-calc")
        auto_btn.setFixedHeight(26)
        auto_btn.clicked.connect(self._auto_calc)
        cols_row.addWidget(auto_btn)
        cols_row.addStretch()
        form.addRow("Dimensions:", cols_row)

        root.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        create_btn = QPushButton("Create")
        create_btn.setStyleSheet(_primary_btn_style())
        create_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(create_btn)
        root.addLayout(btn_row)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Map Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff)"
        )
        if path:
            new_path = _copy_image(path, _maps_dir())
            self._set_image(new_path)

    def _set_image(self, path: str):
        self._image_path = path
        pm = QPixmap(path)
        if not pm.isNull():
            self._image_w = pm.width()
            self._image_h = pm.height()
        self._img_label.setText(Path(path).name)

    def _auto_calc(self):
        cols = self._cols.value()
        if cols > 0 and self._image_w > 0:
            self._grid_size.setValue(max(5, self._image_w // cols))

    def _on_accept(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validation", "Map name is required.")
            return
        self.accept()

    def result_data(self) -> dict:
        return {
            "name":       self._name.text().strip() or "Untitled Map",
            "image_path": self._image_path,
            "grid_size":  self._grid_size.value(),
            "grid_cols":  self._cols.value(),
            "grid_rows":  self._rows.value(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  _MapListItem — custom list item showing name + thumbnail
# ══════════════════════════════════════════════════════════════════════════════

class _MapListItem(QFrame):
    clicked = Signal(int)  # map_id

    def __init__(self, map_data: dict, parent=None):
        super().__init__(parent)
        self._map_id = map_data.get("id", -1)
        self._selected = False
        self.setFixedHeight(54)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._build(map_data)
        self._refresh_style()

    def _build(self, map_data: dict):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        thumb = QLabel()
        thumb.setFixedSize(38, 38)
        image_path = map_data.get("image_path", "")
        if image_path and Path(image_path).exists():
            pm = QPixmap(image_path).scaled(
                38, 38,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb.setPixmap(pm)
            thumb.setStyleSheet(f"border:1px solid {_BORDER2}; border-radius:4px;")
        else:
            thumb.setText("🗺")
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setStyleSheet(
                f"background:{_BG3}; border:1px solid {_BORDER}; border-radius:4px; font-size:18px;"
            )
        lay.addWidget(thumb)

        name_lbl = QLabel(map_data.get("name", "Untitled Map"))
        name_lbl.setStyleSheet(f"color:{_FG}; font-size:12px; background:transparent; border:none;")
        lay.addWidget(name_lbl, 1)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet(
                f"_MapListItem {{ background:{_BG2}; border-left:3px solid {_ACCENT}; border-radius:0px; }}"
            )
        else:
            self.setStyleSheet(
                f"_MapListItem {{ background:transparent; border-left:3px solid transparent; }}"
                f"_MapListItem:hover {{ background:{_BG3}; }}"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._map_id)
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  MapUI — main widget
# ══════════════════════════════════════════════════════════════════════════════

class MapUI(QWidget):
    def __init__(self, repo, context, parent=None):
        super().__init__(parent)
        self._repo    = repo
        self._context = context
        self._camp_id: Optional[int] = None
        self._current_map_id: Optional[int] = None
        self._current_map_data: Optional[dict] = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(1000)
        self._autosave_timer.timeout.connect(self._do_auto_save)
        self._map_items: dict = {}
        self._layer_rows: dict = {}
        self._layer_btns: dict = {}
        self._layer_name_lbls: dict = {}   # layer_id → QLabel (for dim/restore)
        self._active_layer_key: str = MapLayer.TOKENS
        # Widget references for custom layers panel
        self._custom_layers_widget: Optional[QWidget] = None
        self._layers_lay: Optional[QVBoxLayout] = None
        self._build()
        self._apply_style()

        if repo is None:
            self._show_unavailable()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header: title + zoom + new/import ────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(52)
        hdr.setObjectName("mapHeader")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 0, 12, 0)
        hdr_lay.setSpacing(6)

        title_lbl = QLabel("🗺  Maps")
        title_lbl.setStyleSheet(
            f"font-size:15px; font-weight:700; color:{_FG}; background:transparent; border:none;"
        )
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()

        # Zoom controls live in the header so they're always visible
        _zbtn = (
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2}; "
            f"border-radius:4px; font-size:13px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
        )
        zoom_out = QPushButton("−")
        zoom_out.setFixedSize(28, 28)
        zoom_out.setStyleSheet(_zbtn)
        zoom_out.clicked.connect(
            lambda: self._view.set_zoom(self._view._zoom / 1.2) if hasattr(self, "_view") else None
        )
        self._zoom_label = QPushButton("100%")
        self._zoom_label.setFixedSize(54, 28)
        self._zoom_label.setStyleSheet(_zbtn)
        self._zoom_label.clicked.connect(
            lambda: self._view.set_zoom(1.0) if hasattr(self, "_view") else None
        )
        zoom_in = QPushButton("+")
        zoom_in.setFixedSize(28, 28)
        zoom_in.setStyleSheet(_zbtn)
        zoom_in.clicked.connect(
            lambda: self._view.set_zoom(self._view._zoom * 1.2) if hasattr(self, "_view") else None
        )
        hdr_lay.addWidget(zoom_out)
        hdr_lay.addWidget(self._zoom_label)
        hdr_lay.addWidget(zoom_in)

        hdr_sep = QFrame()
        hdr_sep.setFrameShape(QFrame.Shape.VLine)
        hdr_sep.setFixedWidth(1)
        hdr_sep.setStyleSheet(f"background:{_BORDER2}; border:none; min-height:20px; max-height:20px; margin:0 4px;")
        hdr_lay.addWidget(hdr_sep)

        self._hdr_new_btn = QPushButton("+ New Map")
        self._hdr_new_btn.setFixedHeight(30)
        self._hdr_new_btn.setStyleSheet(
            f"QPushButton {{ background:{_ACCENT}; color:#fff; border:none; border-radius:4px; "
            f"padding:0 12px; font-size:11px; font-weight:600; }}"
            f"QPushButton:hover {{ background:#6ab4ff; }}"
        )
        self._hdr_new_btn.clicked.connect(self._on_new_map)
        self._hdr_import_btn = QPushButton("Import Image")
        self._hdr_import_btn.setFixedHeight(30)
        self._hdr_import_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2}; "
            f"border-radius:4px; padding:0 10px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
        )
        self._hdr_import_btn.clicked.connect(self._on_import_image)
        hdr_lay.addWidget(self._hdr_new_btn)
        hdr_lay.addWidget(self._hdr_import_btn)
        root.addWidget(hdr)

        # Splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet(f"QSplitter::handle {{ background:{_BORDER}; }}")
        root.addWidget(self._splitter, 1)

        # ── Tabbed sidebar ───────────────────────────────────────────────────
        sidebar = QTabWidget()
        sidebar.setFixedWidth(260)
        sidebar.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        sidebar.tabBar().setExpanding(True)
        sidebar.setStyleSheet(f"""
            QTabWidget::pane {{
                background:{_SIDEBAR}; border:none; border-top:1px solid {_BORDER};
            }}
            QTabBar::tab {{
                background:{_BG3}; color:{_FG_DIM}; border:none;
                padding:9px 4px; font-size:16px; min-width:40px;
            }}
            QTabBar::tab:selected {{
                background:{_SIDEBAR}; color:{_FG};
                border-top:2px solid {_ACCENT};
            }}
            QTabBar::tab:hover:!selected {{ color:{_FG_MID}; background:{_BG2}; }}
        """)
        sidebar.addTab(self._build_maps_tab(),   "🗺")
        sidebar.addTab(self._build_tools_tab(),  "🛠")
        sidebar.addTab(self._build_grid_tab(),   "⊞")
        sidebar.addTab(self._build_layers_tab(), "🔲")
        sidebar.addTab(self._build_tokens_tab(), "🎭")
        sidebar.tabBar().setTabToolTip(0, "Maps")
        sidebar.tabBar().setTabToolTip(1, "Tools")
        sidebar.tabBar().setTabToolTip(2, "Grid")
        sidebar.tabBar().setTabToolTip(3, "Layers")
        sidebar.tabBar().setTabToolTip(4, "Tokens")
        self._sidebar = sidebar
        self._splitter.addWidget(sidebar)

        # ── Right stacked widget ─────────────────────────────────────────────
        self._right_stack = QStackedWidget()
        self._splitter.addWidget(self._right_stack)
        self._splitter.setStretchFactor(1, 1)

        self._right_stack.addWidget(self._build_empty_state())
        self._right_stack.addWidget(self._build_canvas_page())
        self._right_stack.setCurrentIndex(0)

        self._refresh_layer_highlight()

    # ── Sidebar tab builders ──────────────────────────────────────────────────

    def _build_maps_tab(self) -> QWidget:
        """Tab 1: Map list + new/delete."""
        w = QWidget()
        w.setStyleSheet(f"background:{_SIDEBAR};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Map list — use a scroll area with custom item widgets
        self._map_scroll = QScrollArea()
        self._map_scroll.setWidgetResizable(True)
        self._map_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._map_scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:transparent; }}"
            f"QScrollBar:vertical {{ background:{_SIDEBAR}; width:6px; border:none; }}"
            f"QScrollBar::handle:vertical {{ background:{_BORDER2}; border-radius:3px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
        )
        self._map_list_container = QWidget()
        self._map_list_container.setStyleSheet("background:transparent;")
        self._map_list_layout = QVBoxLayout(self._map_list_container)
        self._map_list_layout.setContentsMargins(6, 6, 6, 6)
        self._map_list_layout.setSpacing(2)
        self._map_list_layout.addStretch()
        self._map_scroll.setWidget(self._map_list_container)
        self._map_scroll.setMinimumHeight(140)   # always shows several maps
        lay.addWidget(self._map_scroll, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 6, 8, 8)
        btn_row.setSpacing(6)
        add_btn = QPushButton("+ New Map")
        add_btn.setFixedHeight(30)
        add_btn.setStyleSheet(
            f"QPushButton {{ background:{_ACCENT}; color:#fff; border:none; "
            f"border-radius:4px; font-size:11px; font-weight:600; }}"
            f"QPushButton:hover {{ background:#6ab4ff; }}"
        )
        add_btn.clicked.connect(self._on_new_map)
        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(30, 30)
        del_btn.setToolTip("Delete selected map")
        del_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_DANGER}; border:1px solid {_BORDER2}; "
            f"border-radius:4px; font-size:13px; }}"
            f"QPushButton:hover {{ background:{_DANGER}; color:#fff; }}"
        )
        del_btn.clicked.connect(self._on_delete_map)
        btn_row.addWidget(add_btn, 1)
        btn_row.addWidget(del_btn)
        lay.addLayout(btn_row)
        return w

    def _build_tools_tab(self) -> QWidget:
        """Tab 2: Interaction tools + fog controls."""
        w = QWidget()
        w.setStyleSheet(f"background:{_SIDEBAR};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 12, 10, 12)
        lay.setSpacing(0)

        _s = _section_lbl = lambda t: _mk_section_lbl(t)

        def _mk_section_lbl(text):
            l = QLabel(text)
            l.setStyleSheet(
                f"font-size:9px; font-weight:700; color:{_FG_DIM}; "
                f"letter-spacing:2px; background:transparent; "
                f"padding:0 0 6px 0;"
            )
            return l

        # Tool buttons — 2-column grid
        lay.addWidget(_s("INTERACTION TOOLS"))
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)

        tool_defs = [
            ("↖  Select",       MapTool.SELECT,       "Select and move tokens"),
            ("👁  Reveal Fog",   MapTool.FOG_PAINT,    "Paint to reveal fog areas"),
            ("🌑  Hide Fog",     MapTool.FOG_ERASE,    "Paint to add fog"),
            ("📏  Measure",      MapTool.MEASURE,      "Click two points to measure distance"),
            ("📐  Align Grid",   MapTool.GRID_ALIGN,   "Click two diagonal corners of one cell"),
            ("🔬  Measure Grid", MapTool.GRID_MEASURE, "Click two grid intersections, enter count"),
        ]
        _tool_btn_ss = (
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2}; "
            f"border-radius:5px; font-size:11px; padding:8px 6px; text-align:left; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
            f"QPushButton:checked {{ background:{_ACCENT}; color:#fff; border-color:{_ACCENT}; }}"
        )
        grid_lay = QGridLayout()
        grid_lay.setSpacing(5)
        tool_btns = []
        for i, (label, tool, tip) in enumerate(tool_defs):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setStyleSheet(_tool_btn_ss)
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda _, t=tool: self._on_tool_changed(t))
            self._tool_group.addButton(btn)
            grid_lay.addWidget(btn, i // 2, i % 2)
            tool_btns.append((tool, btn))
            if tool == MapTool.SELECT:
                btn.setChecked(True)
        # store refs
        self._btn_select       = tool_btns[0][1]
        self._btn_fog_paint    = tool_btns[1][1]
        self._btn_fog_erase    = tool_btns[2][1]
        self._btn_measure      = tool_btns[3][1]
        self._btn_grid_align   = tool_btns[4][1]
        self._btn_grid_measure = tool_btns[5][1]
        lay.addLayout(grid_lay)
        lay.addSpacing(14)

        # Add token button
        add_tok_btn = QPushButton("＋  Add Token to Map")
        add_tok_btn.setFixedHeight(32)
        add_tok_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2}; "
            f"border-radius:5px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
        )
        add_tok_btn.clicked.connect(self._on_add_token)
        lay.addWidget(add_tok_btn)
        lay.addSpacing(16)

        # Fog controls
        lay.addWidget(_s("FOG OF WAR"))
        self._fog_toggle = QPushButton("Fog  ○  OFF")
        self._fog_toggle.setCheckable(True)
        self._fog_toggle.setChecked(False)
        self._fog_toggle.setFixedHeight(34)
        self._fog_toggle.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2}; "
            f"border-radius:5px; font-size:11px; }}"
            f"QPushButton:checked {{ background:#0f3d6a; color:{_ACCENT}; border-color:{_ACCENT}; }}"
            f"QPushButton:hover {{ border-color:{_ACCENT}; }}"
        )
        self._fog_toggle.clicked.connect(self._on_fog_toggle)
        lay.addWidget(self._fog_toggle)
        lay.addSpacing(5)

        fog_btn_row = QHBoxLayout()
        fog_btn_row.setSpacing(5)
        self._reveal_all_btn = QPushButton("Reveal All")
        self._reveal_all_btn.setFixedHeight(28)
        self._reveal_all_btn.setVisible(False)
        self._reveal_all_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_SUCCESS}; border:1px solid {_BORDER2}; "
            f"border-radius:4px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{_SUCCESS}; color:#fff; }}"
        )
        self._reveal_all_btn.clicked.connect(self._on_fog_reveal_all)
        self._hide_all_btn = QPushButton("Hide All")
        self._hide_all_btn.setFixedHeight(28)
        self._hide_all_btn.setVisible(False)
        self._hide_all_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_WARN}; border:1px solid {_BORDER2}; "
            f"border-radius:4px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{_WARN}; color:#fff; }}"
        )
        self._hide_all_btn.clicked.connect(self._on_fog_hide_all)
        fog_btn_row.addWidget(self._reveal_all_btn, 1)
        fog_btn_row.addWidget(self._hide_all_btn, 1)
        lay.addLayout(fog_btn_row)
        lay.addSpacing(8)

        # Fog opacity slider
        fog_op_row = QHBoxLayout()
        fog_op_row.setSpacing(8)
        fog_op_lbl = QLabel("Opacity:")
        fog_op_lbl.setStyleSheet(f"color:{_FG_MID}; background:transparent; font-size:11px;")
        fog_op_row.addWidget(fog_op_lbl)
        self._fog_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._fog_opacity_slider.setRange(10, 100)
        self._fog_opacity_slider.setValue(85)
        self._fog_opacity_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background:{_BG3}; height:4px; border-radius:2px; }}"
            f"QSlider::handle:horizontal {{ background:{_ACCENT}; width:14px; height:14px; "
            f"margin:-5px 0; border-radius:7px; }}"
            f"QSlider::sub-page:horizontal {{ background:{_ACCENT}; border-radius:2px; }}"
        )
        self._fog_opacity_slider.valueChanged.connect(self._on_fog_opacity_changed)
        self._fog_opacity_val_lbl = QLabel("85%")
        self._fog_opacity_val_lbl.setFixedWidth(34)
        self._fog_opacity_val_lbl.setStyleSheet(
            f"color:{_FG_MID}; font-size:11px; background:transparent;"
        )
        fog_op_row.addWidget(self._fog_opacity_slider, 1)
        fog_op_row.addWidget(self._fog_opacity_val_lbl)
        lay.addLayout(fog_op_row)

        lay.addStretch()

        # Keyboard hint
        hint = QLabel("Scroll: zoom  ·  Space+drag: pan\nDel: delete token  ·  Esc: deselect")
        hint.setStyleSheet(
            f"color:{_FG_DIM}; font-size:10px; background:transparent; line-height:1.6;"
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return w

    def _build_grid_tab(self) -> QWidget:
        """Tab 3: Grid display + alignment settings."""
        w = QWidget()
        w.setStyleSheet(f"background:{_SIDEBAR};")
        outer = QScrollArea()
        outer.setWidget(w)
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.setStyleSheet(
            f"QScrollArea {{ background:{_SIDEBAR}; border:none; }}"
            f"QScrollBar:vertical {{ background:{_SIDEBAR}; width:6px; border:none; }}"
            f"QScrollBar::handle:vertical {{ background:{_BORDER2}; border-radius:3px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
        )
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 12, 10, 12)
        lay.setSpacing(10)

        def _sec(text):
            l = QLabel(text)
            l.setStyleSheet(
                f"font-size:9px; font-weight:700; color:{_FG_DIM}; "
                f"letter-spacing:2px; background:transparent;"
            )
            return l

        _spin_ss = (
            f"QSpinBox {{ background:{_BG3}; color:{_FG}; border:1px solid {_BORDER2}; "
            f"border-radius:4px; padding:3px 6px; font-size:11px; }}"
            f"QSpinBox:focus {{ border-color:{_ACCENT}; }}"
        )

        # ── DISPLAY ──
        lay.addWidget(_sec("DISPLAY"))

        self._grid_toggle = QPushButton("Grid  ●  ON")
        self._grid_toggle.setCheckable(True)
        self._grid_toggle.setChecked(True)
        self._grid_toggle.setFixedHeight(32)
        self._grid_toggle.setStyleSheet(
            f"QPushButton {{ background:#0f3d1e; color:{_SUCCESS}; border:1px solid {_SUCCESS}; "
            f"border-radius:5px; font-size:11px; }}"
            f"QPushButton:!checked {{ background:{_BG3}; color:{_FG_DIM}; border-color:{_BORDER2}; }}"
            f"QPushButton:hover {{ border-color:{_ACCENT}; }}"
        )
        self._grid_toggle.clicked.connect(self._on_grid_toggle)
        lay.addWidget(self._grid_toggle)

        # Lock grid — prevents accidental drag-resize and cursor changes
        self._grid_lock_btn = QPushButton("🔓  Grid Unlocked")
        self._grid_lock_btn.setCheckable(True)
        self._grid_lock_btn.setChecked(False)
        self._grid_lock_btn.setFixedHeight(32)
        self._grid_lock_btn.setToolTip(
            "Lock the grid to prevent accidental resizing.\n"
            "Unlock to drag column/row borders."
        )
        self._grid_lock_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_FG_DIM}; border:1px solid {_BORDER2}; "
            f"border-radius:5px; font-size:11px; text-align:left; padding:0 10px; }}"
            f"QPushButton:checked {{ background:#2a1f00; color:{_WARN}; border-color:{_WARN}; }}"
            f"QPushButton:hover {{ border-color:{_ACCENT}; }}"
        )
        self._grid_lock_btn.clicked.connect(self._on_grid_lock_toggled)
        lay.addWidget(self._grid_lock_btn)

        # Cell size row
        sz_row = QHBoxLayout()
        sz_row.addWidget(QLabel("Cell size:"))
        self._grid_size_spin = QSpinBox()
        self._grid_size_spin.setRange(5, 500)
        self._grid_size_spin.setValue(50)
        self._grid_size_spin.setSuffix(" px")
        self._grid_size_spin.setStyleSheet(_spin_ss)
        self._grid_size_spin.setFixedWidth(80)
        self._grid_size_spin.valueChanged.connect(self._on_grid_size_changed)
        sz_row.addWidget(self._grid_size_spin)
        self._grid_dim_label = QLabel("")
        self._grid_dim_label.setStyleSheet(f"color:{_FG_DIM}; font-size:10px; background:transparent;")
        sz_row.addWidget(self._grid_dim_label, 1)
        lay.addLayout(sz_row)

        # Line width row
        lw_row = QHBoxLayout()
        lw_row.setSpacing(8)
        lw_row.addWidget(QLabel("Line width:"))
        self._line_width_slider = QSlider(Qt.Orientation.Horizontal)
        self._line_width_slider.setRange(1, 8)
        self._line_width_slider.setValue(1)
        self._line_width_slider.setTickInterval(1)
        self._line_width_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background:{_BG3}; height:4px; border-radius:2px; }}"
            f"QSlider::handle:horizontal {{ background:{_ACCENT}; width:14px; height:14px; "
            f"margin:-5px 0; border-radius:7px; }}"
            f"QSlider::sub-page:horizontal {{ background:{_ACCENT}; border-radius:2px; }}"
        )
        self._line_width_slider.valueChanged.connect(self._on_line_width_changed)
        self._line_width_val_lbl = QLabel("1 px")
        self._line_width_val_lbl.setFixedWidth(32)
        self._line_width_val_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:11px; background:transparent;")
        lw_row.addWidget(self._line_width_slider, 1)
        lw_row.addWidget(self._line_width_val_lbl)
        lay.addLayout(lw_row)

        # Color row
        col_row = QHBoxLayout()
        col_row.setSpacing(8)
        col_row.addWidget(QLabel("Line color:"))
        self._grid_color_btn = QPushButton()
        self._grid_color_btn.setFixedSize(32, 28)
        self._grid_color_btn.setToolTip("Click to change grid line color")
        self._grid_color_btn.clicked.connect(self._on_pick_grid_color)
        self._set_grid_color_btn_style("#ffffff")
        col_row.addWidget(self._grid_color_btn)
        col_row.addStretch()
        lay.addLayout(col_row)

        # Opacity row
        op_row = QHBoxLayout()
        op_row.setSpacing(8)
        op_row.addWidget(QLabel("Opacity:"))
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(5, 100)
        self._opacity_slider.setValue(30)
        self._opacity_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background:{_BG3}; height:4px; border-radius:2px; }}"
            f"QSlider::handle:horizontal {{ background:{_ACCENT}; width:14px; height:14px; "
            f"margin:-5px 0; border-radius:7px; }}"
            f"QSlider::sub-page:horizontal {{ background:{_ACCENT}; border-radius:2px; }}"
        )
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self._opacity_val_lbl = QLabel("30%")
        self._opacity_val_lbl.setFixedWidth(32)
        self._opacity_val_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:11px; background:transparent;")
        op_row.addWidget(self._opacity_slider, 1)
        op_row.addWidget(self._opacity_val_lbl)
        lay.addLayout(op_row)

        # ── POSITION ──
        lay.addWidget(self._make_hdiv())
        lay.addWidget(_sec("POSITION"))

        ox_row = QHBoxLayout()
        ox_row.addWidget(QLabel("Offset X:"))
        self._offset_x_spin = QSpinBox()
        self._offset_x_spin.setRange(-500, 500)
        self._offset_x_spin.setStyleSheet(_spin_ss)
        self._offset_x_spin.setFixedWidth(70)
        self._offset_x_spin.setToolTip("Shift grid horizontally by N pixels")
        self._offset_x_spin.valueChanged.connect(self._on_offset_changed)
        ox_row.addWidget(self._offset_x_spin)
        ox_row.addStretch()
        lay.addLayout(ox_row)

        oy_row = QHBoxLayout()
        oy_row.addWidget(QLabel("Offset Y:"))
        self._offset_y_spin = QSpinBox()
        self._offset_y_spin.setRange(-500, 500)
        self._offset_y_spin.setStyleSheet(_spin_ss)
        self._offset_y_spin.setFixedWidth(70)
        self._offset_y_spin.setToolTip("Shift grid vertically by N pixels")
        self._offset_y_spin.valueChanged.connect(self._on_offset_changed)
        oy_row.addWidget(self._offset_y_spin)
        oy_row.addStretch()
        lay.addLayout(oy_row)

        # ── MANUAL EDITING ──
        lay.addWidget(self._make_hdiv())
        lay.addWidget(_sec("MANUAL EDITING"))

        _btn_ss = (
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2}; "
            f"border-radius:4px; font-size:11px; padding:6px; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
        )
        col_edit = QGridLayout()
        col_edit.setSpacing(5)
        for (r, c, label, tip, fn) in [
            (0, 0, "+ Column", "Add a column to the right", lambda: self._scene.add_col() if hasattr(self, "_scene") else None),
            (0, 1, "− Column", "Remove last column",        lambda: self._scene.remove_col() if hasattr(self, "_scene") else None),
            (1, 0, "+ Row",    "Add a row at the bottom",   lambda: self._scene.add_row() if hasattr(self, "_scene") else None),
            (1, 1, "− Row",    "Remove last row",           lambda: self._scene.remove_row() if hasattr(self, "_scene") else None),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(30)
            b.setToolTip(tip)
            b.setStyleSheet(_btn_ss)
            b.clicked.connect(fn)
            col_edit.addWidget(b, r, c)
        lay.addLayout(col_edit)

        # ── ALIGNMENT TOOLS ──
        lay.addWidget(self._make_hdiv())
        lay.addWidget(_sec("ALIGNMENT TOOLS"))

        align_hint = QLabel(
            "📐 Align: click two diagonal corners of one grid cell\n"
            "🔬 Measure: click two intersections, enter cell count"
        )
        align_hint.setStyleSheet(
            f"color:{_FG_DIM}; font-size:10px; background:transparent; line-height:1.5;"
        )
        align_hint.setWordWrap(True)
        lay.addWidget(align_hint)
        lay.addSpacing(6)

        align_btn_row = QHBoxLayout()
        align_btn_row.setSpacing(5)
        align_btn = QPushButton("📐  Align Grid")
        align_btn.setFixedHeight(32)
        align_btn.setStyleSheet(_btn_ss)
        align_btn.clicked.connect(lambda: self._on_tool_changed(MapTool.GRID_ALIGN))
        measure_btn = QPushButton("🔬  Measure Grid")
        measure_btn.setFixedHeight(32)
        measure_btn.setStyleSheet(_btn_ss)
        measure_btn.clicked.connect(lambda: self._on_tool_changed(MapTool.GRID_MEASURE))
        align_btn_row.addWidget(align_btn, 1)
        align_btn_row.addWidget(measure_btn, 1)
        lay.addLayout(align_btn_row)

        lay.addStretch()
        return outer

    def _build_layers_tab(self) -> QWidget:
        """Tab 4: Layer visibility + custom layers."""
        w = QWidget()
        w.setStyleSheet(f"background:{_SIDEBAR};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(0)

        # Built-in layers
        self._layers_lay = QVBoxLayout()
        self._layers_lay.setContentsMargins(0, 0, 0, 4)
        self._layers_lay.setSpacing(1)

        _eye_ss = (
            f"QPushButton {{ background:{_ACCENT}; border:none; color:#fff; "
            f"font-size:11px; border-radius:4px; }}"
            f"QPushButton:!checked {{ background:{_BG3}; color:{_FG_DIM}; border:1px solid {_BORDER}; }}"
            f"QPushButton:hover {{ opacity:0.85; }}"
        )
        for layer_id, icon, name in LAYER_DEFS:
            row = QFrame()
            row.setStyleSheet("QFrame { background:transparent; border:none; }")
            row.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(6)

            eye_btn = QPushButton("👁")
            eye_btn.setFixedSize(28, 28)
            eye_btn.setCheckable(True)
            eye_btn.setChecked(True)
            eye_btn.setToolTip("Show / hide layer")
            eye_btn.setStyleSheet(_eye_ss)
            eye_btn.clicked.connect(lambda checked, lid=layer_id: self._on_layer_visibility(lid, checked))
            self._layer_btns[layer_id] = eye_btn
            rl.addWidget(eye_btn)

            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("color:#a0a0a0; background:transparent; border:none; font-size:13px;")
            icon_lbl.setFixedWidth(20)
            rl.addWidget(icon_lbl)

            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("color:#d0d0d0; background:transparent; border:none; font-size:11px;")
            rl.addWidget(name_lbl, 1)
            self._layer_name_lbls[layer_id] = name_lbl

            row.mousePressEvent = lambda e, lid=layer_id: self._set_active_layer(lid)
            self._layers_lay.addWidget(row)
            self._layer_rows[layer_id] = row

        lay.addLayout(self._layers_lay)

        # Custom layers area
        self._custom_layers_widget = QWidget()
        self._custom_layers_widget.setStyleSheet("background:transparent;")
        self._custom_layers_inner_lay = QVBoxLayout(self._custom_layers_widget)
        self._custom_layers_inner_lay.setContentsMargins(0, 0, 0, 0)
        self._custom_layers_inner_lay.setSpacing(1)
        lay.addWidget(self._custom_layers_widget)

        lay.addWidget(self._make_hdiv())

        # Add Layer button
        add_lay_btn = QPushButton("＋  Add Layer")
        add_lay_btn.setFixedHeight(30)
        add_lay_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; border:1px solid {_BORDER2}; "
            f"color:{_FG_DIM}; border-radius:4px; font-size:11px; margin:6px 10px; }}"
            f"QPushButton:hover {{ border-color:{_ACCENT}; color:{_ACCENT}; }}"
        )
        add_lay_btn.clicked.connect(self._on_add_layer)
        lay.addWidget(add_lay_btn)
        lay.addStretch()
        return w

    def _build_tokens_tab(self) -> QWidget:
        """Tab 5: Token library."""
        w = QWidget()
        w.setStyleSheet(f"background:{_SIDEBAR};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._lib_scroll = QScrollArea()
        self._lib_scroll.setWidgetResizable(True)
        self._lib_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._lib_scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:transparent; }}"
            f"QScrollBar:vertical {{ background:{_SIDEBAR}; width:6px; border:none; }}"
            f"QScrollBar::handle:vertical {{ background:{_BORDER2}; border-radius:3px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
        )
        self._lib_container = QWidget()
        self._lib_container.setStyleSheet("background:transparent;")
        self._lib_grid = QGridLayout(self._lib_container)
        self._lib_grid.setContentsMargins(6, 6, 6, 6)
        self._lib_grid.setSpacing(6)
        self._lib_scroll.setWidget(self._lib_container)
        lay.addWidget(self._lib_scroll, 1)

        add_lib_btn = QPushButton("＋  Add to Library")
        add_lib_btn.setFixedHeight(30)
        add_lib_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2}; "
            f"border-radius:4px; font-size:11px; margin:0 8px 8px 8px; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
        )
        add_lib_btn.clicked.connect(self._on_add_to_library)
        lay.addWidget(add_lib_btn)
        return w

        # ── Right stacked widget ─────────────────────────────────────────────
        self._right_stack = QStackedWidget()
        self._splitter.addWidget(self._right_stack)
        self._splitter.setStretchFactor(1, 1)

        self._right_stack.addWidget(self._build_empty_state())
        self._right_stack.addWidget(self._build_canvas_page())
        self._right_stack.setCurrentIndex(0)

        self._refresh_layer_highlight()

    def _make_hdiv(self) -> QFrame:
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background:{_BORDER}; border:none;")
        return div

    def _build_empty_state(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{_BG};")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(12)
        ico = QLabel("🗺")
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico.setStyleSheet("font-size:64px;")
        title = QLabel("No map selected")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{_FG}; font-size:18px; font-weight:bold;")
        sub = QLabel("Create or select a map from the list")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{_FG_MID}; font-size:13px;")
        new_btn = QPushButton("+ New Map")
        new_btn.setFixedWidth(140)
        new_btn.setFixedHeight(34)
        new_btn.setStyleSheet(
            f"QPushButton {{ background:{_ACCENT}; color:#fff; border:none; "
            f"border-radius:4px; font-weight:600; font-size:13px; }}"
            f"QPushButton:hover {{ background:#6ab4ff; }}"
        )
        new_btn.clicked.connect(self._on_new_map)
        lay.addWidget(ico)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(8)
        lay.addWidget(new_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        return w

    def _build_canvas_page(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{_BG};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Canvas
        canvas_container = QWidget()
        canvas_container.setStyleSheet("background:transparent;")
        canvas_lay = QVBoxLayout(canvas_container)
        canvas_lay.setContentsMargins(0, 0, 0, 0)
        canvas_lay.setSpacing(0)

        self._scene = MapScene()
        self._view  = MapView(self._scene)
        self._view._on_token_drop = self._on_token_drop
        self._connect_scene_signals()
        canvas_lay.addWidget(self._view, 1)
        lay.addWidget(canvas_container, 1)

        # Fog hint overlay
        self._fog_hint_label = QLabel(
            "Fog is ON — use the Reveal tool to uncover areas",
            canvas_container,
        )
        self._fog_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fog_hint_label.setStyleSheet(
            f"background:rgba(0,0,0,160); color:{_FG_MID}; font-size:12px; "
            f"border:1px solid {_BORDER2}; border-radius:6px; padding:6px 16px;"
        )
        self._fog_hint_label.adjustSize()
        self._fog_hint_label.hide()
        self._fog_hint_label.move(20, 20)

        # Status bar
        self._status_bar = QFrame()
        self._status_bar.setFixedHeight(24)
        self._status_bar.setStyleSheet(
            f"QFrame {{ background:{_SIDEBAR}; border-top:1px solid {_BORDER}; }}"
        )
        sb_lay = QHBoxLayout(self._status_bar)
        sb_lay.setContentsMargins(12, 0, 12, 0)
        sb_lay.setSpacing(16)
        self._status_label = QLabel("No map loaded")
        self._status_label.setStyleSheet(
            f"color:{_FG_DIM}; font-size:10px; background:transparent;"
        )
        sb_lay.addWidget(self._status_label)
        sb_lay.addStretch()
        lay.addWidget(self._status_bar)

        # Connect tool buttons
        self._btn_select.clicked.connect(lambda: self._on_tool_changed(MapTool.SELECT))
        self._btn_fog_paint.clicked.connect(lambda: self._on_tool_changed(MapTool.FOG_PAINT))
        self._btn_fog_erase.clicked.connect(lambda: self._on_tool_changed(MapTool.FOG_ERASE))
        self._btn_grid_align.clicked.connect(lambda: self._on_tool_changed(MapTool.GRID_ALIGN))
        self._btn_grid_measure.clicked.connect(lambda: self._on_tool_changed(MapTool.GRID_MEASURE))
        self._btn_measure.clicked.connect(lambda: self._on_tool_changed(MapTool.MEASURE))

        self._scene.grid_aligned.connect(self._on_grid_aligned)
        self._scene.grid_changed.connect(self._on_grid_changed_from_handle)
        self._scene.fog_changed.connect(self._on_fog_cells_changed)
        self._scene.grid_measure_ready.connect(self._on_grid_measure_ready)

        # Initialise grid toggle text
        self._grid_toggle.setText("Grid ●")

        # Zoom update timer
        self._zoom_update_timer = QTimer(self)
        self._zoom_update_timer.setInterval(200)
        self._zoom_update_timer.timeout.connect(self._update_zoom_label)
        self._zoom_update_timer.start()

        return w

    def _make_tool_btn(self, label: str, tool: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setFixedHeight(30)
        btn.setProperty("tool", tool)
        btn.setStyleSheet(_tb_btn_style())
        return btn

    def _apply_style(self):
        self.setStyleSheet(
            f"QWidget {{ background:{_BG}; color:{_FG}; }}"
            f"QFrame#mapHeader {{ background:{_BG2}; border-bottom:1px solid {_BORDER}; }}"
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER}; "
            f"border-radius:4px; padding:0 10px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
            f"QPushButton:pressed {{ background:{_ACCENT}; color:#fff; }}"
            f"QScrollBar:vertical {{ background:{_BG}; width:6px; border:none; }}"
            f"QScrollBar::handle:vertical {{ background:{_BORDER2}; border-radius:3px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}"
        )

    # ── Layer helpers ─────────────────────────────────────────────────────────

    def _on_layer_visibility(self, layer_id: str, visible: bool):
        # Update the scene
        if hasattr(self, "_scene") and self._scene:
            self._scene.set_layer_visibility(layer_id, visible)
        # Update the name label: dim + strikethrough when hidden
        lbl = self._layer_name_lbls.get(layer_id)
        if lbl:
            if visible:
                lbl.setStyleSheet(
                    f"color:{_FG_MID}; background:transparent; border:none; font-size:11px;"
                )
            else:
                lbl.setStyleSheet(
                    f"color:{_FG_DIM}; background:transparent; border:none; font-size:11px;"
                    f"text-decoration:line-through;"
                )
        # Sync the eye button checked state (in case called programmatically)
        btn = self._layer_btns.get(layer_id)
        if btn and btn.isChecked() != visible:
            btn.blockSignals(True)
            btn.setChecked(visible)
            btn.blockSignals(False)
        self._schedule_autosave()

    def _set_active_layer(self, layer_id: str):
        self._active_layer_key = layer_id
        if hasattr(self, "_scene") and self._scene:
            self._scene.set_active_layer(layer_id)
        self._refresh_layer_highlight()

    def _refresh_layer_highlight(self):
        for lid, row in self._layer_rows.items():
            if lid == self._active_layer_key:
                row.setStyleSheet(
                    f"QFrame {{ background:{_BG3}; border-left:3px solid {_ACCENT}; border-radius:0px; }}"
                )
            else:
                row.setStyleSheet("QFrame { background:transparent; border:none; }")

    # ── Custom layer management ────────────────────────────────────────────────

    def _on_add_layer(self):
        name, ok = QInputDialog.getText(self, "Add Layer", "Layer name:")
        if not ok or not name.strip():
            return
        layer_id = f"custom_{uuid.uuid4().hex[:8]}"
        custom_layers = [
            l for l in (self._current_map_data or {}).get("layers_json", [])
            if isinstance(l, dict)
        ]
        # Assign Z between Objects (15) and Tokens (25)
        z = 16 + len(custom_layers)
        new_layer = {"id": layer_id, "name": name.strip(), "visible": True, "z": z}
        custom_layers.append(new_layer)
        if self._current_map_id and self._repo:
            self._repo.update_map(self._current_map_id, layers_json=json.dumps(custom_layers))
            if self._current_map_data is not None:
                self._current_map_data["layers_json"] = custom_layers
        self._rebuild_custom_layers_panel()

    def _on_delete_layer(self, layer_id: str):
        if not self._current_map_id or not self._repo:
            return
        custom_layers = [
            l for l in (self._current_map_data or {}).get("layers_json", [])
            if isinstance(l, dict) and l.get("id") != layer_id
        ]
        self._repo.update_map(self._current_map_id, layers_json=json.dumps(custom_layers))
        if self._current_map_data is not None:
            self._current_map_data["layers_json"] = custom_layers
        self._rebuild_custom_layers_panel()

    def _rebuild_custom_layers_panel(self):
        if self._custom_layers_widget is None:
            return
        # Clear existing custom layer rows
        lay = self._custom_layers_inner_lay
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        custom_layers = [
            l for l in (self._current_map_data or {}).get("layers_json", [])
            if isinstance(l, dict)
        ]
        for layer in custom_layers:
            lid = layer.get("id", "")
            lname = layer.get("name", "Custom")
            row = QFrame()
            row.setStyleSheet("QFrame { background:transparent; border:none; }")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 3, 8, 3)
            rl.setSpacing(5)

            eye_btn = QPushButton("👁")
            eye_btn.setFixedSize(24, 24)
            eye_btn.setCheckable(True)
            eye_btn.setChecked(layer.get("visible", True))
            eye_btn.setStyleSheet(
                f"QPushButton {{ background:transparent; border:none; color:{_FG_DIM}; "
                f"font-size:12px; border-radius:4px; }}"
                f"QPushButton:checked {{ color:{_FG}; }}"
                f"QPushButton:hover {{ background:{_BG3}; }}"
            )
            eye_btn.clicked.connect(lambda checked, layer_id=lid: self._on_layer_visibility(layer_id, checked))
            rl.addWidget(eye_btn)

            icon_lbl = QLabel("✦")
            icon_lbl.setStyleSheet(f"color:{_FG_DIM}; background:transparent; border:none; font-size:10px;")
            icon_lbl.setFixedWidth(18)
            rl.addWidget(icon_lbl)

            name_lbl = QLabel(lname)
            name_lbl.setStyleSheet(f"color:{_FG_MID}; background:transparent; border:none; font-size:11px;")
            rl.addWidget(name_lbl, 1)

            del_btn = QPushButton("×")
            del_btn.setFixedSize(18, 18)
            del_btn.setStyleSheet(
                f"QPushButton {{ background:transparent; border:none; color:{_FG_DIM}; "
                f"font-size:12px; border-radius:3px; }}"
                f"QPushButton:hover {{ background:{_DANGER}; color:#fff; }}"
            )
            del_btn.clicked.connect(lambda _, layer_id=lid: self._on_delete_layer(layer_id))
            rl.addWidget(del_btn)

            lay.addWidget(row)

    # ── Scene signals ──────────────────────────────────────────────────────────

    def _connect_scene_signals(self):
        self._scene.token_edit_requested.connect(self._on_token_edit)
        self._scene.token_deleted.connect(self._on_token_delete)
        self._scene.token_moved.connect(self._on_token_moved)
        self._scene.fog_changed.connect(self._schedule_autosave)
        self._scene.grid_changed.connect(self._on_grid_changed_from_scene)

        def _repo_cb(token_id: int, **kwargs):
            if self._repo:
                self._repo.update_token(token_id, **kwargs)
        self._scene._repo_update_token = _repo_cb

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(self, campaign_id=None):
        self._camp_id = campaign_id
        if campaign_id is None:
            self._current_map_id = None
            self._current_map_data = None
            self._right_stack.setCurrentIndex(0)
            self._clear_map_list()
            return
        old_id = self._current_map_id
        self._load_map_list()
        self._load_token_library()
        if old_id and old_id in self._map_items:
            self._select_map(old_id)

    # ── Map list ───────────────────────────────────────────────────────────────

    def _clear_map_list(self):
        layout = self._map_list_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._map_items.clear()

    def _load_map_list(self):
        self._clear_map_list()
        if not self._repo or not self._camp_id:
            return
        maps = self._repo.get_maps(self._camp_id)
        for md in maps:
            self._add_map_list_item(md)

    def _add_map_list_item(self, map_data: dict):
        item = _MapListItem(map_data)
        mid = map_data.get("id", -1)
        item.clicked.connect(self._select_map)
        count = self._map_list_layout.count()
        self._map_list_layout.insertWidget(count - 1, item)
        self._map_items[mid] = item

    def _select_map(self, map_id: int):
        for mid, item in self._map_items.items():
            item.set_selected(mid == map_id)
        self._current_map_id = map_id
        if self._repo:
            md = self._repo.get_map(map_id)
            if md:
                self._load_map(md)

    # ── Canvas loading ─────────────────────────────────────────────────────────

    def _load_map(self, map_data: dict):
        self._current_map_data = dict(map_data)
        tokens = []
        if self._repo:
            tokens = self._repo.get_tokens(map_data["id"])

        self._scene.load_map(map_data, tokens)
        self._right_stack.setCurrentIndex(1)

        grid_enabled = bool(map_data.get("grid_enabled", True))
        cell_px      = int(map_data.get("grid_size", 50))
        offset_x     = int(map_data.get("grid_offset_x", 0))
        offset_y     = int(map_data.get("grid_offset_y", 0))
        fog_enabled  = bool(map_data.get("fog_enabled", False))

        self._grid_toggle.setChecked(grid_enabled)
        self._grid_toggle.setText("Grid ●" if grid_enabled else "Grid ○")
        self._scene.set_grid_handles_visible(grid_enabled)
        # Sync grid color swatch in toolbar
        self._set_grid_color_btn_style(str(map_data.get("grid_color", "#ffffff")))

        self._grid_size_spin.blockSignals(True)
        self._grid_size_spin.setValue(cell_px)
        self._grid_size_spin.blockSignals(False)

        self._offset_x_spin.blockSignals(True)
        self._offset_x_spin.setValue(offset_x)
        self._offset_x_spin.blockSignals(False)

        self._offset_y_spin.blockSignals(True)
        self._offset_y_spin.setValue(offset_y)
        self._offset_y_spin.blockSignals(False)

        self._fog_toggle.setChecked(fog_enabled)
        self._fog_toggle.setText("Fog  ●  ON" if fog_enabled else "Fog  ○  OFF")
        self._reveal_all_btn.setVisible(fog_enabled)
        self._hide_all_btn.setVisible(fog_enabled)

        # Sync Grid tab controls
        opacity_pct = int(float(map_data.get("grid_opacity", 0.3)) * 100)
        if hasattr(self, "_opacity_slider"):
            self._opacity_slider.blockSignals(True)
            self._opacity_slider.setValue(max(5, min(100, opacity_pct)))
            self._opacity_slider.blockSignals(False)
            if hasattr(self, "_opacity_val_lbl"):
                self._opacity_val_lbl.setText(f"{opacity_pct}%")
        # Reset line width slider to 1 on each map load (not persisted)
        if hasattr(self, "_line_width_slider"):
            self._line_width_slider.blockSignals(True)
            self._line_width_slider.setValue(1)
            self._line_width_slider.blockSignals(False)
            if hasattr(self, "_line_width_val_lbl"):
                self._line_width_val_lbl.setText("1 px")

        self._update_grid_dim_label()
        self._update_status_bar()

        # Rebuild custom layers panel for loaded map
        self._rebuild_custom_layers_panel()

        if hasattr(self, "_fog_hint_label"):
            fog_item = self._scene._fog_item
            if fog_enabled and not fog_item._revealed:
                self._fog_hint_label.show()
                self._fog_hint_label.adjustSize()
            else:
                self._fog_hint_label.hide()

        zoom  = float(map_data.get("zoom_level", 1.0))
        pan_x = float(map_data.get("pan_x", 0.0))
        pan_y = float(map_data.get("pan_y", 0.0))
        self._view.restore_state({"zoom": zoom, "pan_x": pan_x, "pan_y": pan_y})
        self._view.setFocus()

    # ── Toolbar handlers ───────────────────────────────────────────────────────

    def _on_tool_changed(self, tool: str):
        if tool in (MapTool.FOG_PAINT, MapTool.FOG_ERASE):
            if not self._fog_toggle.isChecked():
                self._fog_toggle.setChecked(True)
                self._on_fog_toggle(True)
        self._scene.set_tool(tool)
        if tool in (MapTool.GRID_ALIGN, MapTool.FOG_PAINT, MapTool.FOG_ERASE):
            self._view.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        else:
            self._view.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)

    def _on_grid_lock_toggled(self, locked: bool):
        if hasattr(self, "_grid_lock_btn"):
            self._grid_lock_btn.setText(
                "🔒  Grid Locked" if locked else "🔓  Grid Unlocked"
            )
        if hasattr(self, "_view") and self._view:
            self._view._grid_locked = locked
            # Reset cursor immediately so it doesn't stay as a resize arrow
            from PySide6.QtGui import QCursor
            from PySide6.QtCore import Qt
            self._view.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def _on_line_width_changed(self, value: int):
        if hasattr(self, "_line_width_val_lbl"):
            self._line_width_val_lbl.setText(f"{value} px")
        if hasattr(self, "_scene") and self._scene and self._current_map_data:
            md = self._current_map_data
            self._scene.set_grid(
                enabled=bool(md.get("grid_enabled", True)),
                cell_px=self._grid_size_spin.value(),
                offset_x=self._offset_x_spin.value(),
                offset_y=self._offset_y_spin.value(),
                color=str(md.get("grid_color", "#ffffff")),
                opacity=float(md.get("grid_opacity", 0.3)),
                line_width=float(value),
            )
        self._schedule_autosave()

    def _on_opacity_changed(self, value: int):
        if hasattr(self, "_opacity_val_lbl"):
            self._opacity_val_lbl.setText(f"{value}%")
        if hasattr(self, "_scene") and self._scene and self._current_map_data:
            md = self._current_map_data
            opacity = value / 100.0
            md["grid_opacity"] = opacity
            self._scene.set_grid(
                enabled=bool(md.get("grid_enabled", True)),
                cell_px=self._grid_size_spin.value(),
                offset_x=self._offset_x_spin.value(),
                offset_y=self._offset_y_spin.value(),
                color=str(md.get("grid_color", "#ffffff")),
                opacity=opacity,
            )
            if self._repo and self._current_map_id:
                self._repo.update_map(self._current_map_id, grid_opacity=opacity)
        self._schedule_autosave()

    def _on_grid_toggle(self, checked: bool):
        self._grid_toggle.setText("Grid  ●  ON" if checked else "Grid  ○  OFF")
        if hasattr(self, "_scene") and self._scene:
            md = self._current_map_data or {}
            self._scene.set_grid(
                enabled=checked,
                cell_px=self._grid_size_spin.value(),
                offset_x=self._offset_x_spin.value(),
                offset_y=self._offset_y_spin.value(),
                color=str(md.get("grid_color", "#ffffff")),
                opacity=float(md.get("grid_opacity", 0.3)),
            )
            self._scene.set_grid_handles_visible(checked)
        if self._current_map_data:
            self._current_map_data["grid_enabled"] = int(checked)
        if self._repo and self._current_map_id:
            self._repo.update_map(self._current_map_id, grid_enabled=int(checked))
        self._schedule_autosave()

    def _on_grid_size_changed(self, value: int):
        if self._current_map_data:
            self._current_map_data["grid_size"] = value
            self._scene.set_grid(
                enabled=bool(self._current_map_data.get("grid_enabled", True)),
                cell_px=value,
                offset_x=self._offset_x_spin.value(),
                offset_y=self._offset_y_spin.value(),
                color=str(self._current_map_data.get("grid_color", "#ffffff")),
                opacity=float(self._current_map_data.get("grid_opacity", 0.3)),
            )
            if self._repo and self._current_map_id:
                self._repo.update_map(self._current_map_id, grid_size=value)
        self._update_grid_dim_label()
        self._update_status_bar()
        self._schedule_autosave()

    def _on_offset_changed(self):
        if not self._scene or not self._current_map_data:
            return
        md = self._current_map_data
        ox = self._offset_x_spin.value()
        oy = self._offset_y_spin.value()
        md["grid_offset_x"] = ox
        md["grid_offset_y"] = oy
        self._scene.set_grid(
            enabled=bool(md.get("grid_enabled", True)),
            cell_px=self._grid_size_spin.value(),
            offset_x=ox,
            offset_y=oy,
            color=str(md.get("grid_color", "#ffffff")),
            opacity=float(md.get("grid_opacity", 0.3)),
        )
        if self._repo and self._current_map_id:
            self._repo.update_map(self._current_map_id, grid_offset_x=ox, grid_offset_y=oy)
        self._schedule_autosave()

    def _on_grid_aligned(self):
        if not self._scene:
            return
        cell_px  = self._scene._cell_px
        offset_x = self._scene._offset_x
        offset_y = self._scene._offset_y
        self._grid_size_spin.blockSignals(True)
        self._grid_size_spin.setValue(cell_px)
        self._grid_size_spin.blockSignals(False)
        self._offset_x_spin.blockSignals(True)
        self._offset_x_spin.setValue(offset_x)
        self._offset_x_spin.blockSignals(False)
        self._offset_y_spin.blockSignals(True)
        self._offset_y_spin.setValue(offset_y)
        self._offset_y_spin.blockSignals(False)
        if self._current_map_data:
            self._current_map_data["grid_size"]     = cell_px
            self._current_map_data["grid_offset_x"] = offset_x
            self._current_map_data["grid_offset_y"] = offset_y
        if self._repo and self._current_map_id:
            self._repo.update_map(
                self._current_map_id,
                grid_size=cell_px,
                grid_offset_x=offset_x,
                grid_offset_y=offset_y,
                grid_enabled=1,
            )
        self._update_grid_dim_label()
        self._update_status_bar()
        self._btn_select.setChecked(True)
        self._on_tool_changed(MapTool.SELECT)
        self._schedule_autosave()

    # ── Grid color ────────────────────────────────────────────────────────────

    def _set_grid_color_btn_style(self, color: str):
        """Update the toolbar grid-color swatch to show the current color."""
        if hasattr(self, "_grid_color_btn"):
            self._grid_color_btn.setStyleSheet(
                f"QPushButton {{"
                f"  background:{color}; border:1px solid {_BORDER2};"
                f"  border-radius:4px;"
                f"}}"
                f"QPushButton:hover {{ border-color:{_ACCENT}; }}"
            )

    def _on_pick_grid_color(self):
        """Show a color menu with presets + custom picker."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{_BG3}; color:{_FG}; border:1px solid {_BORDER2};"
            f"border-radius:6px; padding:4px; }}"
            f"QMenu::item {{ padding:6px 20px 6px 12px; border-radius:3px; }}"
            f"QMenu::item:selected {{ background:{_ACCENT}; color:#fff; }}"
        )
        presets = [
            ("⬜  White  (dark maps)",   "#ffffff"),
            ("⬛  Black  (light maps)",  "#000000"),
            ("🔴  Red  (high contrast)", "#e05555"),
            ("🟡  Yellow  (warm maps)",  "#f0c040"),
            ("🔵  Cyan  (cool maps)",    "#00bcd4"),
            ("🟢  Green",                "#3dba6e"),
            ("🔵  Blue",                 "#4f9eff"),
        ]
        acts = {}
        for label, color in presets:
            a = menu.addAction(label)
            acts[a] = color
        menu.addSeparator()
        custom_act = menu.addAction("🎨  Custom color…")

        chosen = menu.exec(self._grid_color_btn.mapToGlobal(
            self._grid_color_btn.rect().bottomLeft()
        ))
        if chosen == custom_act:
            from PySide6.QtWidgets import QColorDialog
            cur = (self._current_map_data or {}).get("grid_color", "#ffffff")
            c = QColorDialog.getColor(QColor(cur), self, "Grid Line Color")
            if c.isValid():
                self._apply_grid_color(c.name())
        elif chosen and chosen in acts:
            self._apply_grid_color(acts[chosen])

    def _apply_grid_color(self, color: str):
        """Apply a new grid color to the scene, toolbar swatch, and DB."""
        self._set_grid_color_btn_style(color)
        if self._current_map_data:
            self._current_map_data["grid_color"] = color
        if hasattr(self, "_scene") and self._scene:
            md = self._current_map_data or {}
            self._scene.set_grid(
                enabled=self._grid_toggle.isChecked(),
                cell_px=self._grid_size_spin.value(),
                offset_x=self._offset_x_spin.value(),
                offset_y=self._offset_y_spin.value(),
                color=color,
                opacity=float(md.get("grid_opacity", 0.3)),
            )
        if self._repo and self._current_map_id:
            self._repo.update_map(self._current_map_id, grid_color=color)
        self._schedule_autosave()

    # ── Grid measure ──────────────────────────────────────────────────────────

    def _on_grid_measure_ready(self, x1: float, y1: float, x2: float, y2: float):
        """
        Called after the user clicks two points in GRID_MEASURE mode.
        Shows a dialog asking how many squares are between those points,
        then auto-fits the grid.
        """
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QSpinBox, QPushButton, QDialogButtonBox, QFrame,
        )
        import math

        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        dist = math.sqrt(dx * dx + dy * dy)

        dlg = QDialog(self)
        dlg.setWindowTitle("Measure Grid — Auto-fit")
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet(
            f"QDialog {{ background:{_BG2}; color:{_FG}; }}"
            f"QLabel {{ color:{_FG_MID}; background:transparent; border:none; }}"
            f"QSpinBox {{ background:{_BG3}; color:{_FG}; border:1px solid {_BORDER2};"
            f"  border-radius:4px; padding:4px 8px; font-size:12px; }}"
            f"QSpinBox:focus {{ border-color:{_ACCENT}; }}"
        )

        root = QVBoxLayout(dlg)
        root.setSpacing(14)
        root.setContentsMargins(20, 18, 20, 16)

        # Measurement info
        info_lbl = QLabel(f"Distance between clicked points: <b>{dist:.1f} px</b>")
        info_lbl.setStyleSheet(f"color:{_FG}; background:transparent; border:none; font-size:12px;")
        info_lbl.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(info_lbl)

        # Instruction
        instr = QLabel(
            "Enter how many grid squares are between the two points you clicked.\n"
            "The grid cell size and offset will be calculated automatically."
        )
        instr.setWordWrap(True)
        instr.setStyleSheet(f"color:{_FG_MID}; background:transparent; border:none; font-size:11px;")
        root.addWidget(instr)

        # Square count input
        sq_row = QHBoxLayout()
        sq_row.setSpacing(10)
        sq_row.addWidget(QLabel("Grid squares between points:"))
        n_spin = QSpinBox()
        n_spin.setRange(1, 500)
        n_spin.setValue(max(1, round(dist / 50)))
        n_spin.setFixedWidth(80)
        sq_row.addWidget(n_spin)
        sq_row.addStretch()
        root.addLayout(sq_row)

        # Live preview
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background:{_BORDER}; border:none; max-height:1px;")
        root.addWidget(sep)

        preview_lbl = QLabel()
        preview_lbl.setStyleSheet(f"color:{_ACCENT}; background:transparent; border:none; font-size:11px;")
        root.addWidget(preview_lbl)

        def _update_preview():
            n = n_spin.value()
            if n > 0 and dist > 0:
                cell = dist / n
                ox = int(min(x1, x2)) % max(1, int(cell))
                oy = int(min(y1, y2)) % max(1, int(cell))
                preview_lbl.setText(
                    f"→ Cell size: {cell:.1f} px  |  Offset X: {ox} px  |  Offset Y: {oy} px"
                )

        n_spin.valueChanged.connect(_update_preview)
        _update_preview()

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Apply Grid")
        ok_btn.setStyleSheet(
            f"QPushButton {{ background:{_ACCENT}; color:#fff; border:none;"
            f"border-radius:4px; padding:6px 18px; font-weight:600; }}"
            f"QPushButton:hover {{ background:#6ab4ff; }}"
        )
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER2};"
            f"border-radius:4px; padding:6px 14px; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            # User cancelled — return to select
            self._btn_select.setChecked(True)
            self._on_tool_changed(MapTool.SELECT)
            return

        n = n_spin.value()
        if n > 0 and dist > 0:
            cell_px  = max(5, int(round(dist / n)))
            tl_x     = min(x1, x2)
            tl_y     = min(y1, y2)
            offset_x = int(tl_x) % cell_px
            offset_y = int(tl_y) % cell_px
            md       = self._current_map_data or {}
            color    = str(md.get("grid_color", "#ffffff"))
            opacity  = float(md.get("grid_opacity", 0.3))

            self._scene.set_grid(
                enabled=True,
                cell_px=cell_px,
                offset_x=offset_x,
                offset_y=offset_y,
                color=color,
                opacity=opacity,
            )
            # Sync toolbar controls
            self._grid_size_spin.blockSignals(True)
            self._grid_size_spin.setValue(cell_px)
            self._grid_size_spin.blockSignals(False)
            self._offset_x_spin.blockSignals(True)
            self._offset_x_spin.setValue(offset_x)
            self._offset_x_spin.blockSignals(False)
            self._offset_y_spin.blockSignals(True)
            self._offset_y_spin.setValue(offset_y)
            self._offset_y_spin.blockSignals(False)
            if not self._grid_toggle.isChecked():
                self._grid_toggle.setChecked(True)
                self._grid_toggle.setText("Grid ●")
            # Persist
            if self._current_map_data:
                self._current_map_data.update({
                    "grid_size": cell_px,
                    "grid_offset_x": offset_x,
                    "grid_offset_y": offset_y,
                    "grid_enabled": 1,
                })
            if self._repo and self._current_map_id:
                self._repo.update_map(
                    self._current_map_id,
                    grid_size=cell_px,
                    grid_offset_x=offset_x,
                    grid_offset_y=offset_y,
                    grid_enabled=1,
                )
            self._update_grid_dim_label()
            self._update_status_bar()
            self._schedule_autosave()

        # Return to select tool
        self._btn_select.setChecked(True)
        self._on_tool_changed(MapTool.SELECT)

    def _on_grid_changed_from_handle(self, cell_px: int, offset_x: int, offset_y: int):
        self._grid_size_spin.blockSignals(True)
        self._grid_size_spin.setValue(cell_px)
        self._grid_size_spin.blockSignals(False)
        self._offset_x_spin.blockSignals(True)
        self._offset_x_spin.setValue(offset_x)
        self._offset_x_spin.blockSignals(False)
        self._offset_y_spin.blockSignals(True)
        self._offset_y_spin.setValue(offset_y)
        self._offset_y_spin.blockSignals(False)
        if self._current_map_data:
            self._current_map_data["grid_size"]     = cell_px
            self._current_map_data["grid_offset_x"] = offset_x
            self._current_map_data["grid_offset_y"] = offset_y
        if self._repo and self._current_map_id:
            self._repo.update_map(
                self._current_map_id,
                grid_size=cell_px,
                grid_offset_x=offset_x,
                grid_offset_y=offset_y,
            )
        self._update_grid_dim_label()
        self._update_status_bar()
        self._schedule_autosave()

    def _on_grid_changed_from_scene(self, cell_px: int, offset_x: int, offset_y: int):
        """Called when grid changes via drag resize or add/remove col/row."""
        self._grid_size_spin.blockSignals(True)
        self._offset_x_spin.blockSignals(True)
        self._offset_y_spin.blockSignals(True)
        self._grid_size_spin.setValue(cell_px)
        self._offset_x_spin.setValue(offset_x)
        self._offset_y_spin.setValue(offset_y)
        self._grid_size_spin.blockSignals(False)
        self._offset_x_spin.blockSignals(False)
        self._offset_y_spin.blockSignals(False)
        # Update grid dims label using non-uniform aware num_cols/num_rows
        if hasattr(self, '_scene') and self._scene:
            n_cols = self._scene._grid_item.num_cols()
            n_rows = self._scene._grid_item.num_rows()
            if hasattr(self, '_grid_dim_label'):
                self._grid_dim_label.setText(f"{n_cols} × {n_rows}")
        self._schedule_autosave()

    def _on_fog_cells_changed(self):
        if hasattr(self, "_fog_hint_label"):
            fog = self._scene._fog_item
            if fog._revealed:
                self._fog_hint_label.hide()

    def _on_fog_opacity_changed(self, value: int):
        if hasattr(self, "_fog_opacity_val_lbl"):
            self._fog_opacity_val_lbl.setText(f"{value}%")
        if hasattr(self, "_scene") and self._scene:
            self._scene.set_fog_opacity(value / 100.0)
        self._schedule_autosave()

    def _on_fog_toggle(self, checked: bool):
        self._fog_toggle.setText("Fog  ●  ON" if checked else "Fog  ○  OFF")
        self._reveal_all_btn.setVisible(checked)
        self._hide_all_btn.setVisible(checked)
        if hasattr(self, "_scene") and self._scene:
            self._scene.set_fog_enabled(checked)
        if self._current_map_data:
            self._current_map_data["fog_enabled"] = int(checked)
        if self._repo and self._current_map_id:
            self._repo.update_map(self._current_map_id, fog_enabled=int(checked))
        if hasattr(self, "_fog_hint_label"):
            fog_item = self._scene._fog_item
            if checked and not fog_item._revealed:
                self._fog_hint_label.show()
                self._fog_hint_label.adjustSize()
            else:
                self._fog_hint_label.hide()
        self._schedule_autosave()

    def _on_fog_reveal_all(self):
        self._scene.fog_reveal_all()

    def _on_fog_hide_all(self):
        self._scene.fog_hide_all()

    def _update_grid_dim_label(self):
        if not hasattr(self, "_grid_dim_label"):
            return
        if hasattr(self, '_scene') and self._scene:
            n_cols = self._scene._grid_item.num_cols()
            n_rows = self._scene._grid_item.num_rows()
            self._grid_dim_label.setText(f"{n_cols}x{n_rows}")
            return
        rect    = self._scene.sceneRect()
        cell_px = max(1, self._grid_size_spin.value())
        cols    = math.ceil(rect.width()  / cell_px)
        rows    = math.ceil(rect.height() / cell_px)
        self._grid_dim_label.setText(f"{cols}x{rows}")

    def _update_status_bar(self):
        if not hasattr(self, "_status_label"):
            return
        if not self._current_map_data:
            self._status_label.setText("No map loaded")
            return
        name    = self._current_map_data.get("name", "Untitled Map")
        cell_px = self._grid_size_spin.value()
        # Use non-uniform aware col/row count
        if hasattr(self, '_scene') and self._scene:
            cols = self._scene._grid_item.num_cols()
            rows = self._scene._grid_item.num_rows()
        else:
            rect = self._scene.sceneRect()
            cols = math.ceil(rect.width()  / max(1, cell_px))
            rows = math.ceil(rect.height() / max(1, cell_px))
        tok  = len(self._scene._tokens)
        zoom = int(self._view._zoom * 100)
        parts = [
            f"{name}",
            f"Grid: {cell_px}px ({cols}x{rows})",
            f"Tokens: {tok}",
            f"Zoom: {zoom}%",
        ]
        # Show resize hint if active
        if hasattr(self, '_view') and hasattr(self._view, '_grid_resize_active'):
            if self._view._grid_resize_active:
                resize_type = "column" if self._view._grid_resize_type == "col" else "row"
                scene = self._scene
                try:
                    if self._view._grid_resize_type == "col":
                        resize_size = scene._col_widths[self._view._grid_resize_idx]
                    else:
                        resize_size = scene._row_heights[self._view._grid_resize_idx]
                    parts.append(f"Resizing {resize_type}: {resize_size}px")
                except (IndexError, KeyError):
                    pass
        self._status_label.setText("  |  ".join(parts))

    def _update_zoom_label(self):
        if hasattr(self, "_view"):
            self._zoom_label.setText(f"{int(self._view._zoom * 100)}%")
            self._update_status_bar()

    # ── Map settings ───────────────────────────────────────────────────────────

    def _on_map_settings(self):
        if not self._current_map_data:
            return
        image_w, image_h = 0, 0
        img_path = self._current_map_data.get("image_path", "")
        if img_path and Path(img_path).exists():
            pm = QPixmap(img_path)
            if not pm.isNull():
                image_w, image_h = pm.width(), pm.height()
        dlg = _MapSettingsDialog(self._current_map_data, image_w, image_h, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.result_data()
            if self._repo and self._current_map_id:
                self._repo.update_map(self._current_map_id, **{
                    k: v for k, v in new_data.items()
                    if k not in ("id", "campaign_id", "created_at", "updated_at",
                                 "fog_data", "zoom_level", "pan_x", "pan_y")
                })
                md = self._repo.get_map(self._current_map_id)
                if md:
                    self._load_map(md)
                    if self._current_map_id in self._map_items:
                        old = self._map_items.pop(self._current_map_id)
                        idx = self._map_list_layout.indexOf(old)
                        old.deleteLater()
                        new_item = _MapListItem(md)
                        new_item.clicked.connect(self._select_map)
                        new_item.set_selected(True)
                        self._map_list_layout.insertWidget(idx, new_item)
                        self._map_items[self._current_map_id] = new_item

    # ── Token operations ───────────────────────────────────────────────────────

    def _on_add_token(self):
        if not self._current_map_id or not self._repo:
            return
        dlg = _TokenDialog(campaign_id=self._camp_id, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.result_data()
        view_center  = self._view.viewport().rect().center()
        scene_center = self._view.mapToScene(view_center)
        cell_px  = self._current_map_data.get("grid_size", 50) if self._current_map_data else 50
        offset_x = self._current_map_data.get("grid_offset_x", 0) if self._current_map_data else 0
        offset_y = self._current_map_data.get("grid_offset_y", 0) if self._current_map_data else 0
        snapped  = snap_to_grid(scene_center, cell_px, offset_x, offset_y)
        data["x"] = snapped.x()
        data["y"] = snapped.y()
        self._create_token(data)
        if dlg.save_to_library() and self._repo:
            self._repo.add_to_library(
                self._camp_id,
                data["name"],
                data.get("image_path", ""),
                data.get("token_type", "Character"),
                data.get("color", "#4f9eff"),
                float(data.get("cell_width", 1.0)),
                float(data.get("cell_height", 1.0)),
            )
            self._load_token_library()

    def _on_token_drop(self, lib_data: dict, scene_pos: QPointF):
        if not self._current_map_id or not self._repo:
            return
        cell_px  = self._current_map_data.get("grid_size", 50) if self._current_map_data else 50
        offset_x = self._current_map_data.get("grid_offset_x", 0) if self._current_map_data else 0
        offset_y = self._current_map_data.get("grid_offset_y", 0) if self._current_map_data else 0
        snapped = snap_to_grid(scene_pos, cell_px, offset_x, offset_y)
        data = {
            "name":        lib_data.get("name", "Token"),
            "image_path":  lib_data.get("image_path", ""),
            "token_type":  lib_data.get("token_type", "Character"),
            "color":       lib_data.get("color", "#4f9eff"),
            "cell_width":  float(lib_data.get("default_w", 1.0)),
            "cell_height": float(lib_data.get("default_h", 1.0)),
            "x":           snapped.x(),
            "y":           snapped.y(),
        }
        self._create_token(data)

    def _create_token(self, data: dict):
        if not self._repo or not self._current_map_id:
            return
        token_id = self._repo.add_token(
            self._current_map_id,
            data.get("name", "Token"),
            data.get("image_path", ""),
            data.get("token_type", "Character"),
            data.get("color", "#4f9eff"),
            data.get("x", 0.0),
            data.get("y", 0.0),
            float(data.get("cell_width", 1.0)),
            float(data.get("cell_height", 1.0)),
        )
        if token_id < 0:
            return
        optional = {
            k: v for k, v in data.items()
            if k in ("hp_current", "hp_max", "conditions_json", "notes",
                     "label_visible", "visible", "layer")
        }
        if optional:
            self._repo.update_token(token_id, **optional)
        token_data = self._repo.get_tokens(self._current_map_id)
        td = next((t for t in token_data if t["id"] == token_id), None)
        if td:
            self._scene.add_token_from_data(td)

    def _on_token_edit(self, token_data: dict):
        dlg = _TokenDialog(token_data, campaign_id=self._camp_id, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_data = dlg.result_data()
        token_id = new_data.get("id", -1)
        if token_id < 0 or not self._repo:
            return
        update_fields = {
            "name":            new_data["name"],
            "token_type":      new_data["token_type"],
            "color":           new_data["color"],
            "image_path":      new_data["image_path"],
            "cell_width":      float(new_data["cell_width"]),
            "cell_height":     float(new_data["cell_height"]),
            "hp_current":      int(new_data["hp_current"]),
            "hp_max":          int(new_data["hp_max"]),
            "conditions_json": new_data["conditions_json"],
            "notes":           new_data["notes"],
        }
        self._repo.update_token(token_id, **update_fields)
        self._scene.update_token_data(token_id, new_data)
        if dlg.save_to_library():
            self._repo.add_to_library(
                self._camp_id,
                new_data["name"],
                new_data.get("image_path", ""),
                new_data.get("token_type", "Character"),
                new_data.get("color", "#4f9eff"),
                float(new_data.get("cell_width", 1.0)),
                float(new_data.get("cell_height", 1.0)),
            )
            self._load_token_library()

    def _on_token_delete(self, token_id: int):
        reply = QMessageBox.question(
            self, "Delete Token",
            "Remove this token from the map?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._repo:
                self._repo.delete_token(token_id)
            self._scene.remove_token(token_id)

    def _on_token_moved(self, token_id: int, x: float, y: float):
        if self._repo:
            self._repo.update_token(token_id, x=x, y=y)
        self._schedule_autosave()

    # ── Token library ──────────────────────────────────────────────────────────

    def _load_token_library(self):
        while self._lib_grid.count():
            item = self._lib_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self._repo:
            return
        lib_items = self._repo.get_library(self._camp_id)
        cols = 3
        for i, lib_data in enumerate(lib_items):
            widget = _TokenLibraryItem(lib_data)
            widget.remove_requested.connect(self._on_remove_from_library)
            row = i // cols
            col = i % cols
            self._lib_grid.addWidget(widget, row, col)
        self._lib_grid.setRowStretch(max(1, math.ceil(len(lib_items) / cols)), 1)

    def _on_add_to_library(self):
        dlg = _TokenDialog(lib_mode=True, campaign_id=self._camp_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.result_data()
            if self._repo:
                self._repo.add_to_library(
                    self._camp_id,
                    data["name"],
                    data.get("image_path", ""),
                    data.get("token_type", "Character"),
                    data.get("color", "#4f9eff"),
                    float(data.get("cell_width", 1.0)),
                    float(data.get("cell_height", 1.0)),
                )
                self._load_token_library()

    def _on_remove_from_library(self, lib_id: int):
        if lib_id < 0:
            return
        reply = QMessageBox.question(
            self, "Remove from Library",
            "Remove this token from the library?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes and self._repo:
            self._repo.delete_from_library(lib_id)
            self._load_token_library()

    # ── Map CRUD ───────────────────────────────────────────────────────────────

    def _on_new_map(self):
        if not self._camp_id:
            QMessageBox.information(self, "No Campaign", "Open a campaign first.")
            return
        dlg = _AddMapDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.result_data()
        if not self._repo:
            return
        map_id = self._repo.create_map(
            self._camp_id, data["name"], data.get("image_path", "")
        )
        if map_id < 0:
            return
        self._repo.update_map(
            map_id,
            grid_size=data.get("grid_size", 50),
            grid_cols=data.get("grid_cols", 0),
            grid_rows=data.get("grid_rows", 0),
        )
        md = self._repo.get_map(map_id)
        if md:
            self._add_map_list_item(md)
            self._select_map(map_id)

    def _on_delete_map(self):
        if not self._current_map_id:
            return
        reply = QMessageBox.question(
            self, "Delete Map",
            "Delete this map and all its tokens? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._repo:
            self._repo.delete_tokens_for_map(self._current_map_id)
            self._repo.delete_map(self._current_map_id)
        item = self._map_items.pop(self._current_map_id, None)
        if item:
            self._map_list_layout.removeWidget(item)
            item.deleteLater()
        self._current_map_id = None
        self._current_map_data = None
        self._right_stack.setCurrentIndex(0)

    def _on_import_image(self):
        if not self._camp_id:
            QMessageBox.information(self, "No Campaign", "Open a campaign first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Map Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff)"
        )
        if not path:
            return
        new_path = _copy_image(path, _maps_dir())
        dlg = _AddMapDialog(prefill_image=new_path, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.result_data()
        if not self._repo:
            return
        map_id = self._repo.create_map(
            self._camp_id, data["name"], data.get("image_path", new_path)
        )
        if map_id < 0:
            return
        self._repo.update_map(
            map_id,
            grid_size=data.get("grid_size", 50),
            grid_cols=data.get("grid_cols", 0),
            grid_rows=data.get("grid_rows", 0),
        )
        md = self._repo.get_map(map_id)
        if md:
            self._add_map_list_item(md)
            self._select_map(map_id)

    # ── Auto-save ──────────────────────────────────────────────────────────────

    def _schedule_autosave(self):
        self._autosave_timer.start()

    # Alias for compatibility
    def _schedule_auto_save(self):
        self._autosave_timer.start()

    def _do_auto_save(self):
        if not self._repo or not self._current_map_id:
            return
        try:
            state = self._scene.get_map_state()
            view_state = self._view.get_current_state()
            col_widths  = self._scene._col_widths if self._scene._col_widths else []
            row_heights = self._scene._row_heights if self._scene._row_heights else []
            layers = (self._current_map_data or {}).get("layers_json", [])
            self._repo.save_map_state(
                self._current_map_id,
                zoom=view_state["zoom"],
                pan_x=view_state["pan_x"],
                pan_y=view_state["pan_y"],
                fog_data=state["fog_data"],
                col_widths=col_widths,
                row_heights=row_heights,
                layers=layers,
            )
            # Also persist token positions
            for tid, (tx, ty) in state["token_positions"].items():
                self._repo.update_token(int(tid), x=tx, y=ty)
        except Exception as e:
            log.error(f"[MapUI] auto_save: {e}")

    # ── Unavailable state ──────────────────────────────────────────────────────

    def _show_unavailable(self):
        self._right_stack.setCurrentIndex(0)
        try:
            page = self._right_stack.widget(0)
            for child in page.findChildren(QLabel):
                if "No map selected" in child.text():
                    child.setText("Maps unavailable")
                elif "Create or select" in child.text():
                    child.setText("Map repository not initialized.")
        except Exception:
            pass
