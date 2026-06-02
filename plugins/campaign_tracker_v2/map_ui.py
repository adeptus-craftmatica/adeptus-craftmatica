"""
Map UI — Campaign Tracker v2.

Full interactive map management panel with:
- Map list sidebar
- Token library with drag-to-place
- Grid-based canvas with fog of war
- Token editor
- Map settings
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
)
from PySide6.QtGui import QIcon

from .map_canvas import MapView, MapScene, MapTool, TokenItem, snap_to_grid

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
#  _ColorSwatch  — clickable color circle button
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
                # Drag pixmap
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
        self.setMinimumWidth(440)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 16)

        # Name + type row
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
        size_row.addWidget(QLabel("× H:"))
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
        hp_row.addWidget(QLabel("/  Max:"))
        self._hp_max = QSpinBox()
        self._hp_max.setRange(0, 99999)
        self._hp_max.setValue(int(self._data.get("hp_max", 0)))
        hp_row.addWidget(self._hp_max)
        hp_row.addStretch()
        root.addLayout(hp_row)

        # Conditions
        cond_lbl = QLabel("Conditions:")
        root.addWidget(cond_lbl)
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

        # Save to library (if not already in lib mode)
        if not self._lib_mode:
            self._save_lib = QCheckBox("Save to token library")
            root.addWidget(self._save_lib)

        # Notes
        root.addWidget(QLabel("Notes:"))
        self._notes = QTextEdit(self._data.get("notes", ""))
        self._notes.setMaximumHeight(60)
        root.addWidget(self._notes)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

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
        self.setMinimumWidth(420)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 16)

        form = QFormLayout()
        form.setSpacing(8)

        # Map name
        self._map_name = QLineEdit(self._map_data.get("name", "Untitled Map"))
        form.addRow("Map Name:", self._map_name)

        # Grid group
        grid_box = QGroupBox("Grid")
        grid_box.setStyleSheet(
            f"QGroupBox {{ color:{_FG_MID}; border:1px solid {_BORDER}; border-radius:4px; "
            f"margin-top:8px; }} QGroupBox::title {{ subcontrol-origin:margin; left:8px; }}"
        )
        glay = QFormLayout(grid_box)
        glay.setSpacing(8)

        self._grid_enabled = QCheckBox("Enabled")
        self._grid_enabled.setChecked(bool(self._map_data.get("grid_enabled", True)))
        glay.addRow("", self._grid_enabled)

        self._cell_size = QSpinBox()
        self._cell_size.setRange(5, 500)
        self._cell_size.setValue(int(self._map_data.get("grid_size", 50)))
        glay.addRow("Cell size (px):", self._cell_size)

        # Cols/rows + auto-calc
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
        auto_btn = QPushButton("Auto-calc cell size")
        auto_btn.setFixedHeight(26)
        auto_btn.clicked.connect(self._auto_calc)
        cr_row.addWidget(auto_btn)
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
        glay.addRow("Offset:", off_row)

        # Grid color
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(60, 24)
        self._color_btn.clicked.connect(self._pick_color)
        self._refresh_color_btn()
        glay.addRow("Grid color:", self._color_btn)

        # Grid opacity
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(int(float(self._map_data.get("grid_opacity", 0.3)) * 100))
        glay.addRow("Opacity:", self._opacity_slider)

        form.addRow(grid_box)

        # Fog group
        fog_box = QGroupBox("Fog of War")
        fog_box.setStyleSheet(grid_box.styleSheet())
        flay = QFormLayout(fog_box)
        self._fog_enabled = QCheckBox("Enabled")
        self._fog_enabled.setChecked(bool(self._map_data.get("fog_enabled", False)))
        flay.addRow("", self._fog_enabled)
        form.addRow(fog_box)

        # Notes
        self._notes = QTextEdit(self._map_data.get("notes", ""))
        self._notes.setMaximumHeight(70)
        form.addRow("Notes:", self._notes)

        root.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _auto_calc(self):
        cols = self._cols_spin.value()
        if cols > 0 and self._image_w > 0:
            self._cell_size.setValue(max(5, self._image_w // cols))

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._grid_color), self, "Grid Color")
        if c.isValid():
            self._grid_color = c.name()
            self._refresh_color_btn()

    def _refresh_color_btn(self):
        self._color_btn.setStyleSheet(
            f"QPushButton {{ background:{self._grid_color}; border:1px solid {_BORDER2}; border-radius:3px; }}"
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
        self.setMinimumWidth(400)
        self._build()
        if prefill_image:
            self._set_image(prefill_image)

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 20, 20, 16)

        form = QFormLayout()
        form.setSpacing(8)

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
        form.addRow("Dimensions:", cols_row)

        root.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

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

        # Thumbnail
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
            thumb.setStyleSheet(
                f"border:1px solid {_BORDER2}; border-radius:4px;"
            )
        else:
            thumb.setText("🗺")
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setStyleSheet(
                f"background:{_BG3}; border:1px solid {_BORDER}; border-radius:4px; font-size:18px;"
            )
        lay.addWidget(thumb)

        # Name
        name_lbl = QLabel(map_data.get("name", "Untitled Map"))
        name_lbl.setStyleSheet(f"color:{_FG}; font-size:12px;")
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
        self._map_items: dict[int, _MapListItem] = {}
        self._build()
        self._apply_style()

        if repo is None:
            self._show_unavailable()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        hdr = QFrame()
        hdr.setFixedHeight(52)
        hdr.setObjectName("mapHeader")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 0, 12, 0)
        hdr_lay.setSpacing(8)
        title_lbl = QLabel("🗺  Maps")
        title_lbl.setStyleSheet(f"color:{_FG}; font-size:16px; font-weight:bold;")
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()
        self._hdr_new_btn = QPushButton("+ New Map")
        self._hdr_new_btn.setFixedHeight(30)
        self._hdr_new_btn.clicked.connect(self._on_new_map)
        self._hdr_import_btn = QPushButton("Import Image")
        self._hdr_import_btn.setFixedHeight(30)
        self._hdr_import_btn.clicked.connect(self._on_import_image)
        hdr_lay.addWidget(self._hdr_new_btn)
        hdr_lay.addWidget(self._hdr_import_btn)
        root.addWidget(hdr)

        # Splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background:{_BORDER}; }}"
        )
        root.addWidget(self._splitter, 1)

        # ── Left panel ────────────────────────────────────────────────────────
        self._left = QFrame()
        self._left.setFixedWidth(260)
        self._left.setStyleSheet(f"background:{_SIDEBAR};")
        left_lay = QVBoxLayout(self._left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        # MAPS section header
        maps_hdr = QLabel("MAPS")
        maps_hdr.setContentsMargins(12, 10, 8, 4)
        maps_hdr.setStyleSheet(
            f"color:{_FG_DIM}; font-size:10px; font-weight:bold; letter-spacing:1.2px;"
        )
        left_lay.addWidget(maps_hdr)

        # Map scroll area
        self._map_scroll = QScrollArea()
        self._map_scroll.setWidgetResizable(True)
        self._map_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._map_scroll.setStyleSheet("border:none; background:transparent;")
        self._map_list_container = QWidget()
        self._map_list_container.setStyleSheet("background:transparent;")
        self._map_list_layout = QVBoxLayout(self._map_list_container)
        self._map_list_layout.setContentsMargins(4, 2, 4, 2)
        self._map_list_layout.setSpacing(1)
        self._map_list_layout.addStretch()
        self._map_scroll.setWidget(self._map_list_container)
        self._map_scroll.setMaximumHeight(200)
        left_lay.addWidget(self._map_scroll)

        # Map buttons row
        map_btn_row = QHBoxLayout()
        map_btn_row.setContentsMargins(8, 4, 8, 6)
        map_btn_row.setSpacing(6)
        add_map_btn = QPushButton("+ New Map")
        add_map_btn.setFixedHeight(26)
        add_map_btn.clicked.connect(self._on_new_map)
        del_map_btn = QPushButton("🗑 Delete")
        del_map_btn.setFixedHeight(26)
        del_map_btn.setStyleSheet(f"color:{_DANGER};")
        del_map_btn.clicked.connect(self._on_delete_map)
        map_btn_row.addWidget(add_map_btn, 1)
        map_btn_row.addWidget(del_map_btn)
        left_lay.addLayout(map_btn_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"background:{_BORDER}; max-height:1px;")
        left_lay.addWidget(div)

        # TOKEN LIBRARY section header
        lib_hdr = QLabel("TOKEN LIBRARY")
        lib_hdr.setContentsMargins(12, 10, 8, 4)
        lib_hdr.setStyleSheet(
            f"color:{_FG_DIM}; font-size:10px; font-weight:bold; letter-spacing:1.2px;"
        )
        left_lay.addWidget(lib_hdr)

        # Token library scroll area
        self._lib_scroll = QScrollArea()
        self._lib_scroll.setWidgetResizable(True)
        self._lib_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._lib_scroll.setStyleSheet("border:none; background:transparent;")
        self._lib_container = QWidget()
        self._lib_container.setStyleSheet("background:transparent;")
        self._lib_grid = QGridLayout(self._lib_container)
        self._lib_grid.setContentsMargins(6, 4, 6, 4)
        self._lib_grid.setSpacing(4)
        self._lib_scroll.setWidget(self._lib_container)
        left_lay.addWidget(self._lib_scroll, 1)

        # Add token to library button
        add_lib_btn = QPushButton("+ Add to Library")
        add_lib_btn.setFixedHeight(28)
        add_lib_btn.setContentsMargins(8, 0, 8, 0)
        add_lib_btn.clicked.connect(self._on_add_to_library)
        lib_btn_wrap = QHBoxLayout()
        lib_btn_wrap.setContentsMargins(8, 4, 8, 8)
        lib_btn_wrap.addWidget(add_lib_btn)
        left_lay.addLayout(lib_btn_wrap)

        self._splitter.addWidget(self._left)

        # ── Right stacked widget ───────────────────────────────────────────────
        self._right_stack = QStackedWidget()
        self._splitter.addWidget(self._right_stack)
        self._splitter.setStretchFactor(1, 1)

        # Page 0: empty state
        self._right_stack.addWidget(self._build_empty_state())

        # Page 1: canvas
        self._right_stack.addWidget(self._build_canvas_page())

        # Start on empty state
        self._right_stack.setCurrentIndex(0)

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

        # ── Toolbar ──────────────────────────────────────────────────────────
        self._toolbar = QFrame()
        self._toolbar.setFixedHeight(44)
        self._toolbar.setStyleSheet(
            f"QFrame {{ background:{_BG3}; border-bottom:1px solid {_BORDER}; }}"
        )
        tb_lay = QHBoxLayout(self._toolbar)
        tb_lay.setContentsMargins(8, 0, 8, 0)
        tb_lay.setSpacing(4)

        # Tool group
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)

        self._btn_select = self._make_tool_btn("↖ Select", MapTool.SELECT)
        self._btn_fog_paint = self._make_tool_btn("👁 Reveal", MapTool.FOG_PAINT)
        self._btn_fog_erase = self._make_tool_btn("🌑 Fog", MapTool.FOG_ERASE)
        self._btn_measure = self._make_tool_btn("📏 Measure", MapTool.MEASURE)

        self._tool_group.addButton(self._btn_select)
        self._tool_group.addButton(self._btn_fog_paint)
        self._tool_group.addButton(self._btn_fog_erase)
        self._tool_group.addButton(self._btn_measure)
        self._btn_select.setChecked(True)

        for btn in [self._btn_select, self._btn_fog_paint,
                    self._btn_fog_erase, self._btn_measure]:
            tb_lay.addWidget(btn)

        # Separator
        tb_lay.addWidget(self._make_sep())

        # Grid toggle
        self._grid_toggle = QPushButton("Grid: ON")
        self._grid_toggle.setCheckable(True)
        self._grid_toggle.setChecked(True)
        self._grid_toggle.setFixedHeight(30)
        self._grid_toggle.clicked.connect(self._on_grid_toggle)
        tb_lay.addWidget(self._grid_toggle)

        # Grid size
        tb_lay.addWidget(QLabel("Size:"))
        self._grid_size_spin = QSpinBox()
        self._grid_size_spin.setRange(10, 200)
        self._grid_size_spin.setValue(50)
        self._grid_size_spin.setFixedWidth(56)
        self._grid_size_spin.setFixedHeight(28)
        self._grid_size_spin.valueChanged.connect(self._on_grid_size_changed)
        tb_lay.addWidget(self._grid_size_spin)

        # Grid settings
        grid_cfg_btn = QPushButton("⚙ Grid")
        grid_cfg_btn.setFixedHeight(30)
        grid_cfg_btn.clicked.connect(self._on_map_settings)
        tb_lay.addWidget(grid_cfg_btn)

        tb_lay.addWidget(self._make_sep())

        # Fog toggle
        self._fog_toggle = QPushButton("Fog: OFF")
        self._fog_toggle.setCheckable(True)
        self._fog_toggle.setChecked(False)
        self._fog_toggle.setFixedHeight(30)
        self._fog_toggle.clicked.connect(self._on_fog_toggle)
        tb_lay.addWidget(self._fog_toggle)

        self._reveal_all_btn = QPushButton("Reveal All")
        self._reveal_all_btn.setFixedHeight(30)
        self._reveal_all_btn.setVisible(False)
        self._reveal_all_btn.clicked.connect(self._on_fog_reveal_all)
        tb_lay.addWidget(self._reveal_all_btn)

        self._hide_all_btn = QPushButton("Hide All")
        self._hide_all_btn.setFixedHeight(30)
        self._hide_all_btn.setVisible(False)
        self._hide_all_btn.clicked.connect(self._on_fog_hide_all)
        tb_lay.addWidget(self._hide_all_btn)

        tb_lay.addStretch()

        # Zoom controls
        zoom_out = QPushButton("−")
        zoom_out.setFixedSize(28, 28)
        zoom_out.clicked.connect(lambda: self._view.set_zoom(self._view._zoom / 1.2))
        tb_lay.addWidget(zoom_out)
        self._zoom_label = QPushButton("100%")
        self._zoom_label.setFixedSize(52, 28)
        self._zoom_label.clicked.connect(lambda: self._view.set_zoom(1.0))
        tb_lay.addWidget(self._zoom_label)
        zoom_in = QPushButton("+")
        zoom_in.setFixedSize(28, 28)
        zoom_in.clicked.connect(lambda: self._view.set_zoom(self._view._zoom * 1.2))
        tb_lay.addWidget(zoom_in)

        tb_lay.addWidget(self._make_sep())

        # Map settings
        map_cfg_btn = QPushButton("⚙ Map Settings")
        map_cfg_btn.setFixedHeight(30)
        map_cfg_btn.clicked.connect(self._on_map_settings)
        tb_lay.addWidget(map_cfg_btn)

        # Add token button
        add_tok_btn = QPushButton("+ Token")
        add_tok_btn.setFixedHeight(30)
        add_tok_btn.clicked.connect(self._on_add_token)
        tb_lay.addWidget(add_tok_btn)

        lay.addWidget(self._toolbar)

        # ── Canvas ────────────────────────────────────────────────────────────
        self._scene = MapScene()
        self._view  = MapView(self._scene)
        self._view._on_token_drop = self._on_token_drop
        self._connect_scene_signals()
        lay.addWidget(self._view, 1)

        # Connect tool buttons after scene is created
        self._btn_select.clicked.connect(lambda: self._on_tool_changed(MapTool.SELECT))
        self._btn_fog_paint.clicked.connect(lambda: self._on_tool_changed(MapTool.FOG_PAINT))
        self._btn_fog_erase.clicked.connect(lambda: self._on_tool_changed(MapTool.FOG_ERASE))
        self._btn_measure.clicked.connect(lambda: self._on_tool_changed(MapTool.MEASURE))

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
        btn.setStyleSheet(self._tool_btn_style(False))
        return btn

    def _make_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background:{_BORDER}; min-height:20px; max-height:20px; margin:10px 4px;")
        return sep

    def _tool_btn_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background:{_ACCENT}; color:#fff; border:none; "
                f"border-radius:4px; padding:0 8px; font-size:11px; }}"
            )
        return (
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER}; "
            f"border-radius:4px; padding:0 8px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
            f"QPushButton:checked {{ background:{_ACCENT}; color:#fff; border:none; }}"
        )

    def _apply_style(self):
        btn_style = (
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID}; border:1px solid {_BORDER}; "
            f"border-radius:4px; padding:0 10px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{_BG2}; color:{_FG}; }}"
            f"QPushButton:pressed {{ background:{_ACCENT}; color:#fff; }}"
        )
        self.setStyleSheet(
            f"QWidget {{ background:{_BG}; color:{_FG}; }}"
            f"QFrame#mapHeader {{ background:{_BG2}; border-bottom:1px solid {_BORDER}; }}"
            f"QScrollBar:vertical {{ background:{_BG2}; width:6px; border:none; }}"
            f"QScrollBar::handle:vertical {{ background:{_BORDER2}; border-radius:3px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}"
            + btn_style
        )
        # Toolbar button styles
        for btn in [self._btn_select, self._btn_fog_paint,
                    self._btn_fog_erase, self._btn_measure]:
            btn.setStyleSheet(self._tool_btn_style(False))

    # ── Scene signals ──────────────────────────────────────────────────────────

    def _connect_scene_signals(self):
        self._scene.token_edit_requested.connect(self._on_token_edit)
        self._scene.token_deleted.connect(self._on_token_delete)
        self._scene.token_moved.connect(self._on_token_moved)
        self._scene.fog_changed.connect(self._schedule_auto_save)

        # Wire repo callback into scene
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
        # Re-select previously open map if it still exists
        if old_id and old_id in self._map_items:
            self._select_map(old_id)

    # ── Map list ───────────────────────────────────────────────────────────────

    def _clear_map_list(self):
        layout = self._map_list_layout
        while layout.count() > 1:  # keep the stretch
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
        # Insert before stretch
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

        # Restore toolbar state from map
        grid_enabled = bool(map_data.get("grid_enabled", True))
        cell_px      = int(map_data.get("grid_size", 50))
        fog_enabled  = bool(map_data.get("fog_enabled", False))

        self._grid_toggle.setChecked(grid_enabled)
        self._grid_toggle.setText("Grid: ON" if grid_enabled else "Grid: OFF")
        self._grid_size_spin.blockSignals(True)
        self._grid_size_spin.setValue(cell_px)
        self._grid_size_spin.blockSignals(False)
        self._fog_toggle.setChecked(fog_enabled)
        self._fog_toggle.setText("Fog: ON" if fog_enabled else "Fog: OFF")
        self._reveal_all_btn.setVisible(fog_enabled)
        self._hide_all_btn.setVisible(fog_enabled)

        # Restore view state
        zoom  = float(map_data.get("zoom_level", 1.0))
        pan_x = float(map_data.get("pan_x", 0.0))
        pan_y = float(map_data.get("pan_y", 0.0))
        self._view.restore_state({"zoom": zoom, "pan_x": pan_x, "pan_y": pan_y})

        self._view.setFocus()

    # ── Toolbar handlers ───────────────────────────────────────────────────────

    def _on_tool_changed(self, tool: str):
        self._scene.set_tool(tool)

    def _on_grid_toggle(self, checked: bool):
        self._grid_toggle.setText("Grid: ON" if checked else "Grid: OFF")
        if self._current_map_data:
            self._current_map_data["grid_enabled"] = int(checked)
            self._scene.set_grid(
                enabled=checked,
                cell_px=self._grid_size_spin.value(),
                offset_x=int(self._current_map_data.get("grid_offset_x", 0)),
                offset_y=int(self._current_map_data.get("grid_offset_y", 0)),
                color=str(self._current_map_data.get("grid_color", "#ffffff")),
                opacity=float(self._current_map_data.get("grid_opacity", 0.3)),
            )
            if self._repo and self._current_map_id:
                self._repo.update_map(self._current_map_id, grid_enabled=int(checked))

    def _on_grid_size_changed(self, value: int):
        if self._current_map_data:
            self._current_map_data["grid_size"] = value
            self._scene.set_grid(
                enabled=bool(self._current_map_data.get("grid_enabled", True)),
                cell_px=value,
                offset_x=int(self._current_map_data.get("grid_offset_x", 0)),
                offset_y=int(self._current_map_data.get("grid_offset_y", 0)),
                color=str(self._current_map_data.get("grid_color", "#ffffff")),
                opacity=float(self._current_map_data.get("grid_opacity", 0.3)),
            )
        self._schedule_auto_save()

    def _on_fog_toggle(self, checked: bool):
        self._fog_toggle.setText("Fog: ON" if checked else "Fog: OFF")
        self._reveal_all_btn.setVisible(checked)
        self._hide_all_btn.setVisible(checked)
        self._scene.set_fog_enabled(checked)
        if self._current_map_data:
            self._current_map_data["fog_enabled"] = int(checked)
        if self._repo and self._current_map_id:
            self._repo.update_map(self._current_map_id, fog_enabled=int(checked))

    def _on_fog_reveal_all(self):
        self._scene.fog_reveal_all()

    def _on_fog_hide_all(self):
        self._scene.fog_hide_all()

    def _update_zoom_label(self):
        if hasattr(self, "_view"):
            self._zoom_label.setText(f"{int(self._view._zoom * 100)}%")

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

        dlg = _MapSettingsDialog(
            self._current_map_data, image_w, image_h, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.result_data()
            if self._repo and self._current_map_id:
                # Update all columns
                self._repo.update_map(self._current_map_id, **{
                    k: v for k, v in new_data.items()
                    if k not in ("id", "campaign_id", "created_at", "updated_at",
                                 "fog_data", "zoom_level", "pan_x", "pan_y")
                })
                # Reload map
                md = self._repo.get_map(self._current_map_id)
                if md:
                    self._load_map(md)
                    # Refresh list item name if changed
                    if self._current_map_id in self._map_items:
                        # Rebuild the item
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
        """Add a new token via dialog, place at view center."""
        if not self._current_map_id or not self._repo:
            return
        dlg = _TokenDialog(
            campaign_id=self._camp_id, parent=self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.result_data()
        # Place at view center in scene coords
        view_center = self._view.viewport().rect().center()
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
        """Called when a library token is dropped onto the canvas."""
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
        # Update optional fields if present
        optional = {
            k: v for k, v in data.items()
            if k in ("hp_current", "hp_max", "conditions_json", "notes",
                     "label_visible", "visible", "layer")
        }
        if optional:
            self._repo.update_token(token_id, **optional)

        # Fetch fresh from DB and add to scene
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
        self._schedule_auto_save()

    # ── Token library ──────────────────────────────────────────────────────────

    def _load_token_library(self):
        # Clear grid
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

        # Filler spacer
        self._lib_grid.setRowStretch(
            max(1, math.ceil(len(lib_items) / cols)), 1
        )

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
        # Save additional grid settings
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
        # Remove from UI
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

    def _schedule_auto_save(self):
        self._autosave_timer.start()

    def _do_auto_save(self):
        if not self._repo or not self._current_map_id:
            return
        try:
            state = self._scene.get_map_state()
            view_state = self._view.get_current_state()
            self._repo.save_map_state(
                self._current_map_id,
                zoom=view_state["zoom"],
                pan_x=view_state["pan_x"],
                pan_y=view_state["pan_y"],
                fog_data=state["fog_data"],
            )
        except Exception as e:
            log.error(f"[MapUI] auto_save: {e}")

    # ── Unavailable state ──────────────────────────────────────────────────────

    def _show_unavailable(self):
        self._right_stack.setCurrentIndex(0)
        # Replace empty state text
        try:
            page = self._right_stack.widget(0)
            for child in page.findChildren(QLabel):
                if "No map selected" in child.text():
                    child.setText("Maps unavailable")
                elif "Create or select" in child.text():
                    child.setText("Map repository not initialized.")
        except Exception:
            pass
