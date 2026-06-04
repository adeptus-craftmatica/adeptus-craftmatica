"""
Map Canvas — Campaign Tracker v2.

QGraphicsScene + QGraphicsView interactive map editor.
Features: layer system, grid overlay with drag handles, fog of war,
          draggable tokens, zoom/pan, measure tool, grid-align tool,
          per-column/per-row drag resize.
"""
from __future__ import annotations

import json
import math
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QLineF, QSizeF, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPixmap, QFont, QFontMetrics,
    QPainterPath, QTransform, QCursor, QKeyEvent,
)
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsItem, QGraphicsPixmapItem,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGraphicsSceneMouseEvent, QMenu, QInputDialog, QMessageBox,
    QSizePolicy, QToolButton, QButtonGroup, QSlider, QSpinBox,
    QGraphicsLineItem, QGraphicsTextItem,
)

log = logging.getLogger(__name__)

# ── Palette ──────────────────────────────────────────────────────────────────
_ACCENT  = "#4f9eff"
_BG3     = "#282828"
_BORDER2 = "#3a3a3a"


# ── Tool modes ───────────────────────────────────────────────────────────────

class MapTool:
    SELECT       = "select"
    FOG_PAINT    = "fog_paint"
    FOG_ERASE    = "fog_erase"
    MEASURE      = "measure"
    GRID_ALIGN   = "grid_align"
    GRID_MEASURE = "grid_measure"  # click two grid intersections → auto-fit grid


# ── Layer constants ───────────────────────────────────────────────────────────

class MapLayer:
    BACKGROUND = "background"
    TERRAIN    = "terrain"
    OBJECTS    = "objects"
    TOKENS     = "tokens"
    FOG        = "fog"
    NOTES      = "notes"


LAYER_Z = {
    MapLayer.BACKGROUND: -10,
    MapLayer.TERRAIN:     5,
    MapLayer.OBJECTS:    15,
    MapLayer.TOKENS:     25,
    MapLayer.FOG:        50,
    MapLayer.NOTES:      70,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def snap_to_grid(pos: QPointF, cell_px: int, offset_x: int = 0, offset_y: int = 0) -> QPointF:
    """Snap a position to the nearest grid intersection."""
    if cell_px < 1:
        return pos
    col = round((pos.x() - offset_x) / cell_px)
    row = round((pos.y() - offset_y) / cell_px)
    return QPointF(offset_x + col * cell_px, offset_y + row * cell_px)


def snap_to_grid_nonuniform(pos: QPointF, col_widths: list, row_heights: list,
                             offset_x: int, offset_y: int) -> QPointF:
    """Snap to nearest grid intersection for a non-uniform grid."""
    rx = pos.x() - offset_x
    ry = pos.y() - offset_y

    # Find nearest col boundary
    cum = 0.0
    best_x = 0.0
    best_dx = abs(rx)
    for w in col_widths:
        if abs(rx - cum) < best_dx:
            best_dx = abs(rx - cum)
            best_x = cum
        cum += w
    # also check the last boundary
    if abs(rx - cum) < best_dx:
        best_x = cum

    # Find nearest row boundary
    cum = 0.0
    best_y = 0.0
    best_dy = abs(ry)
    for h in row_heights:
        if abs(ry - cum) < best_dy:
            best_dy = abs(ry - cum)
            best_y = cum
        cum += h
    if abs(ry - cum) < best_dy:
        best_y = cum

    return QPointF(offset_x + best_x, offset_y + best_y)


# ══════════════════════════════════════════════════════════════════════════════
#  GridOverlayItem
# ══════════════════════════════════════════════════════════════════════════════

class GridOverlayItem(QGraphicsItem):
    """Draws grid lines over the map image. Supports both uniform and non-uniform grids."""

    def __init__(self):
        super().__init__()
        # Critical: must not consume mouse events — scene mousePressEvent must fire
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._enabled    = True
        self._cell_px    = 50
        self._cols       = 20
        self._rows       = 20
        self._offset_x   = 0
        self._offset_y   = 0
        self._color      = "#ffffff"
        self._opacity    = 0.3
        self._line_width = 1.0   # screen pixels (cosmetic), user-configurable
        self._scene_w    = 1000.0
        self._scene_h    = 1000.0
        # Non-uniform support — empty means uniform
        self._col_widths: list = []
        self._row_heights: list = []

    def configure(
        self,
        cell_px: int,
        cols: int,
        rows: int,
        offset_x: int = 0,
        offset_y: int = 0,
        color: str = "#ffffff",
        opacity: float = 0.3,
        scene_w: float = 1000.0,
        scene_h: float = 1000.0,
        line_width: float = 1.0,
    ):
        self._line_width = max(0.5, float(line_width))
        self._cell_px  = max(1, cell_px)
        self._cols     = cols
        self._rows     = rows
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._color    = color
        self._opacity  = opacity
        self._scene_w  = scene_w
        self._scene_h  = scene_h
        self.prepareGeometryChange()
        self.update()

    def configure_nonuniform(self, col_widths, row_heights, offset_x, offset_y,
                              color, opacity, scene_w, scene_h):
        self._col_widths  = list(col_widths)
        self._row_heights = list(row_heights)
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._color    = color
        self._opacity  = opacity
        self._scene_w  = scene_w
        self._scene_h  = scene_h
        self.prepareGeometryChange()
        self.update()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._scene_w, self._scene_h)

    def num_cols(self) -> int:
        return len(self._col_widths) if self._col_widths else self._cols

    def num_rows(self) -> int:
        return len(self._row_heights) if self._row_heights else self._rows

    def get_col_x(self, col_idx: int) -> float:
        """X position of the left border of column col_idx."""
        x = float(self._offset_x)
        if self._col_widths:
            for i, w in enumerate(self._col_widths):
                if i == col_idx:
                    return x
                x += w
        else:
            return x + col_idx * self._cell_px
        return x

    def get_col_right_x(self, col_idx: int) -> float:
        """X of the right border of column col_idx."""
        x = float(self._offset_x)
        if self._col_widths:
            for i, w in enumerate(self._col_widths):
                x += w
                if i == col_idx:
                    return x
        else:
            return x + (col_idx + 1) * self._cell_px
        return x

    def get_row_y(self, row_idx: int) -> float:
        """Y position of the top border of row row_idx."""
        y = float(self._offset_y)
        if self._row_heights:
            for i, h in enumerate(self._row_heights):
                if i == row_idx:
                    return y
                y += h
        else:
            return y + row_idx * self._cell_px
        return y

    def get_row_bottom_y(self, row_idx: int) -> float:
        """Y of the bottom border of row row_idx."""
        y = float(self._offset_y)
        if self._row_heights:
            for i, h in enumerate(self._row_heights):
                y += h
                if i == row_idx:
                    return y
        else:
            return y + (row_idx + 1) * self._cell_px
        return y

    def paint(self, painter, option, widget=None):
        if not self._enabled:
            return
        painter.save()
        pen = QPen(QColor(self._color))
        pen.setCosmetic(True)
        pen.setWidthF(self._line_width)
        painter.setPen(pen)
        painter.setOpacity(self._opacity)

        if self._col_widths:
            # Non-uniform columns
            x = float(self._offset_x)
            painter.drawLine(QLineF(x, 0, x, self._scene_h))
            for w in self._col_widths:
                x += w
                painter.drawLine(QLineF(x, 0, x, self._scene_h))
        else:
            for col in range(self._cols + 1):
                x = self._offset_x + col * self._cell_px
                painter.drawLine(QLineF(x, 0, x, self._scene_h))

        if self._row_heights:
            # Non-uniform rows
            y = float(self._offset_y)
            painter.drawLine(QLineF(0, y, self._scene_w, y))
            for h in self._row_heights:
                y += h
                painter.drawLine(QLineF(0, y, self._scene_w, y))
        else:
            for row in range(self._rows + 1):
                y = self._offset_y + row * self._cell_px
                painter.drawLine(QLineF(0, y, self._scene_w, y))

        painter.restore()


# ══════════════════════════════════════════════════════════════════════════════
#  FogOfWarItem
# ══════════════════════════════════════════════════════════════════════════════

class FogOfWarItem(QGraphicsItem):
    """Renders fog of war as opaque cells. Uses cached QPainterPath for performance."""

    def __init__(self):
        super().__init__()
        # Critical: must not consume mouse events — scene mousePressEvent must fire
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(LAYER_Z[MapLayer.FOG])
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._enabled: bool = False
        self._revealed: set = set()
        self._cell_px   = 50
        self._cols      = 20
        self._rows      = 20
        self._offset_x  = 0
        self._offset_y  = 0
        self._scene_w   = 1000.0
        self._scene_h   = 1000.0
        self._path_cache: Optional[QPainterPath] = None
        self._fog_opacity: float = 0.85  # 0.0 = transparent, 1.0 = fully opaque
        self._dirty     = True
        # Non-uniform support — empty means uniform
        self._col_widths: list = []
        self._row_heights: list = []

    def configure(
        self,
        cell_px: int,
        cols: int,
        rows: int,
        offset_x: int = 0,
        offset_y: int = 0,
        scene_w: float = 1000.0,
        scene_h: float = 1000.0,
    ):
        self._cell_px  = max(1, cell_px)
        self._cols     = cols
        self._rows     = rows
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._scene_w  = scene_w
        self._scene_h  = scene_h
        self._dirty    = True
        self.prepareGeometryChange()
        self.update()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self._dirty = True
        self.update()

    def set_revealed(self, revealed):
        """Set revealed cells from an iterable of [col, row] or (col, row) pairs."""
        self._revealed = set(tuple(pair) for pair in revealed)
        self._dirty = True
        self.update()

    def toggle_cell(self, col: int, row: int, reveal: bool):
        if reveal:
            self._revealed.add((col, row))
        else:
            self._revealed.discard((col, row))
        self._dirty = True
        self.update()

    def reveal_all(self):
        if self._col_widths and self._row_heights:
            self._revealed = {
                (c, r)
                for c in range(len(self._col_widths))
                for r in range(len(self._row_heights))
            }
        else:
            self._revealed = {(c, r) for c in range(self._cols) for r in range(self._rows)}
        self._dirty = True
        self.update()

    def hide_all(self):
        self._revealed.clear()
        self._dirty = True
        self.update()

    def get_revealed_list(self) -> list:
        """Return sorted list of [col, row] pairs for storage."""
        return sorted([list(pair) for pair in self._revealed])

    def _rebuild_path(self):
        path = QPainterPath()
        if self._col_widths and self._row_heights:
            y = float(self._offset_y)
            for row, rh in enumerate(self._row_heights):
                x = float(self._offset_x)
                for col, cw in enumerate(self._col_widths):
                    if (col, row) not in self._revealed:
                        path.addRect(QRectF(x, y, cw, rh))
                    x += cw
                y += rh
        else:
            for row in range(self._rows):
                for col in range(self._cols):
                    if (col, row) not in self._revealed:
                        x = self._offset_x + col * self._cell_px
                        y = self._offset_y + row * self._cell_px
                        path.addRect(QRectF(x, y, self._cell_px, self._cell_px))
        self._path_cache = path
        self._dirty = False

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._scene_w, self._scene_h)

    def paint(self, painter, option, widget=None):
        if not self._enabled:
            return
        if self._dirty:
            self._rebuild_path()
        if self._path_cache and not self._path_cache.isEmpty():
            painter.save()
            painter.setOpacity(max(0.0, min(1.0, self._fog_opacity)))
            painter.fillPath(self._path_cache, QBrush(QColor(0, 0, 0)))
            painter.restore()


# ══════════════════════════════════════════════════════════════════════════════
#  GridResizeHandle
# ══════════════════════════════════════════════════════════════════════════════

class GridResizeHandle(QGraphicsItem):
    """Small drag handle for resizing the grid cell size."""

    SIZE = 14

    def __init__(self, orientation: str, scene_ref):
        # orientation: "right" or "bottom"
        super().__init__()
        self._orientation = orientation
        self._scene_ref = scene_ref
        self._drag_start: Optional[QPointF] = None
        self._cell_px_start: int = 50
        self.setZValue(200)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setCursor(
            QCursor(Qt.CursorShape.SizeHorCursor if orientation == "right"
                    else Qt.CursorShape.SizeVerCursor)
        )

    def boundingRect(self):
        s = self.SIZE
        return QRectF(-s / 2, -s / 2, s, s)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(_ACCENT)))
        painter.setPen(QPen(QColor("#ffffff"), 1.5))
        painter.drawRoundedRect(QRectF(-6, -6, 12, 12), 3, 3)
        painter.setPen(QPen(QColor("#ffffff"), 1.5))
        if self._orientation == "right":
            painter.drawLine(QLineF(-3, 0, 3, 0))
            painter.drawLine(QLineF(1, -3, 4, 0))
            painter.drawLine(QLineF(1, 3, 4, 0))
        else:
            painter.drawLine(QLineF(0, -3, 0, 3))
            painter.drawLine(QLineF(-3, 1, 0, 4))
            painter.drawLine(QLineF(3, 1, 0, 4))
        painter.restore()

    def mousePressEvent(self, event):
        self._drag_start = event.scenePos()
        self._cell_px_start = self._scene_ref._cell_px
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        scene = self._scene_ref
        grid = scene._grid_item
        if self._orientation == "right":
            delta = event.scenePos().x() - self._drag_start.x()
            new_total_w = grid._cols * self._cell_px_start + delta
            new_cell = max(5, int(round(new_total_w / max(1, grid._cols))))
        else:
            delta = event.scenePos().y() - self._drag_start.y()
            new_total_h = grid._rows * self._cell_px_start + delta
            new_cell = max(5, int(round(new_total_h / max(1, grid._rows))))
        if new_cell != scene._cell_px:
            scene.set_grid(
                enabled=True,
                cell_px=new_cell,
                offset_x=scene._offset_x,
                offset_y=scene._offset_y,
                color=grid._color,
                opacity=grid._opacity,
            )
            scene.grid_changed.emit(new_cell, scene._offset_x, scene._offset_y)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        scene = self._scene_ref
        scene.grid_changed.emit(scene._cell_px, scene._offset_x, scene._offset_y)
        event.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  TokenItem
# ══════════════════════════════════════════════════════════════════════════════

class TokenItem(QGraphicsItem):
    """A draggable, selectable token on the map."""

    def __init__(self, token_data: dict, cell_px: int):
        super().__init__()
        self._data    = dict(token_data)
        self._cell_px = cell_px
        self._pixmap: Optional[QPixmap] = None
        self._offset_x = 0
        self._offset_y = 0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(LAYER_Z[MapLayer.TOKENS] + self._data.get("layer", 1))
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        self.setPos(QPointF(token_data.get("x", 0.0), token_data.get("y", 0.0)))
        self._load_pixmap()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def token_id(self) -> int:
        return self._data.get("id", -1)

    @property
    def token_data(self) -> dict:
        return self._data

    # ── Pixmap loading ────────────────────────────────────────────────────────

    def _load_pixmap(self):
        path = self._data.get("image_path", "")
        if path and Path(path).exists():
            pm = QPixmap(path)
            if not pm.isNull():
                w = int(self._data.get("cell_width", 1.0) * self._cell_px)
                h = int(self._data.get("cell_height", 1.0) * self._cell_px)
                scaled = pm.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                padded = QPixmap(w, h)
                padded.fill(Qt.GlobalColor.transparent)
                from PySide6.QtGui import QPainter as _P
                p = _P(padded)
                p.drawPixmap(
                    (w - scaled.width()) // 2,
                    (h - scaled.height()) // 2,
                    scaled,
                )
                p.end()
                self._pixmap = padded
                return
        self._pixmap = None

    # ── Geometry ──────────────────────────────────────────────────────────────

    def _token_w(self) -> float:
        return self._data.get("cell_width", 1.0) * self._cell_px

    def _token_h(self) -> float:
        return self._data.get("cell_height", 1.0) * self._cell_px

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._token_w(), self._token_h() + 18)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        w = self._token_w()
        h = self._token_h()
        color_str = self._data.get("color", "#4f9eff")

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._pixmap and not self._pixmap.isNull():
            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(0, 0, w, h), 6, 6)
            painter.setClipPath(clip_path)
            painter.drawPixmap(0, 0, self._pixmap)
            painter.setClipping(False)
        else:
            radius = min(w, h) * 0.45
            cx, cy = w / 2, h / 2
            painter.setBrush(QBrush(QColor(color_str)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

            name = self._data.get("name", "?")
            words = name.split()
            if len(words) >= 2:
                initials = words[0][0].upper() + words[-1][0].upper()
            elif words:
                initials = words[0][:2].upper()
            else:
                initials = "?"
            font = QFont()
            font.setPixelSize(max(8, int(w * 0.38)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, initials)

        # Selection outline
        if self.isSelected():
            pen = QPen(QColor("#4f9eff"))
            pen.setCosmetic(True)
            pen.setWidthF(2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 5, 5)

        # HP bar
        hp_max = self._data.get("hp_max", 0)
        hp_cur = self._data.get("hp_current", 0)
        if hp_max > 0:
            ratio = max(0.0, min(1.0, hp_cur / hp_max))
            if ratio > 0.66:
                bar_color = QColor("#3dba6e")
            elif ratio > 0.33:
                bar_color = QColor("#e07800")
            else:
                bar_color = QColor("#e05555")
            bar_h = 4
            bar_y = h - bar_h - 1
            painter.setBrush(QBrush(QColor(0, 0, 0, 120)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(0, bar_y, w, bar_h))
            painter.setBrush(QBrush(bar_color))
            painter.drawRect(QRectF(0, bar_y, w * ratio, bar_h))

        # Name label
        if self._data.get("label_visible", True):
            name = self._data.get("name", "")
            if name:
                font = QFont()
                font.setPixelSize(10)
                painter.setFont(font)
                fm = QFontMetrics(font)
                lbl_w = min(fm.horizontalAdvance(name) + 6, w + 20)
                lbl_h = 14
                lbl_x = (w - lbl_w) / 2
                lbl_y = h + 2
                painter.setBrush(QBrush(QColor(0, 0, 0, 160)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(lbl_x, lbl_y, lbl_w, lbl_h), 3, 3)
                painter.setPen(QColor("#f0f0f0"))
                painter.drawText(
                    QRectF(lbl_x, lbl_y, lbl_w, lbl_h),
                    Qt.AlignmentFlag.AlignCenter,
                    name,
                )

        painter.restore()

    # ── Item change (snap to grid) ────────────────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            scene = self.scene()
            if scene and hasattr(scene, '_grid_item'):
                grid = scene._grid_item
                if grid._col_widths and grid._row_heights:
                    return snap_to_grid_nonuniform(
                        value, grid._col_widths, grid._row_heights,
                        self._offset_x, self._offset_y
                    )
            return snap_to_grid(value, self._cell_px, self._offset_x, self._offset_y)
        return super().itemChange(change, value)

    def set_grid(self, cell_px: int, offset_x: int = 0, offset_y: int = 0):
        self._cell_px  = cell_px
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._load_pixmap()
        self.prepareGeometryChange()
        self.update()

    def update_cell_px(self, cell_px: int):
        self._cell_px = cell_px
        self._load_pixmap()
        self.prepareGeometryChange()
        self.update()

    # ── Context menu ──────────────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        scene = self.scene()
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #282828; color: #f0f0f0; border: 1px solid #3a3a3a; }"
            "QMenu::item:selected { background: #4f9eff; color: #fff; }"
        )

        edit_act   = menu.addAction("Edit Token…")
        set_hp_act = menu.addAction("Set HP…")

        cond_menu = menu.addMenu("Add Condition")
        conditions = [
            "Blinded", "Charmed", "Deafened", "Exhausted", "Frightened",
            "Grappled", "Incapacitated", "Invisible", "Paralyzed", "Petrified",
            "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious",
        ]
        cond_actions = {}
        for c in conditions:
            a = cond_menu.addAction(c)
            a.setCheckable(True)
            current = self._data.get("conditions_json", [])
            a.setChecked(c in current)
            cond_actions[a] = c

        menu.addSeparator()
        label_act = menu.addAction("Toggle Label")
        vis_act   = menu.addAction("Toggle Visibility")
        menu.addSeparator()
        del_act = menu.addAction("Delete Token")

        chosen = menu.exec(event.screenPos())
        if chosen is None:
            return

        if chosen == edit_act:
            if scene and hasattr(scene, "token_edit_requested"):
                scene.token_edit_requested.emit(dict(self._data))
        elif chosen == set_hp_act:
            cur_hp = self._data.get("hp_current", 0)
            max_hp = self._data.get("hp_max", 0)
            val, ok = QInputDialog.getInt(
                None, "Set HP",
                f"Current HP (max {max_hp}):",
                value=cur_hp, min=0, max=max(max_hp, 9999),
            )
            if ok:
                self._data["hp_current"] = val
                if scene and hasattr(scene, "_repo_update_token"):
                    scene._repo_update_token(self.token_id, hp_current=val)
                self.update()
        elif chosen in cond_actions:
            c = cond_actions[chosen]
            current = list(self._data.get("conditions_json", []))
            if c in current:
                current.remove(c)
            else:
                current.append(c)
            self._data["conditions_json"] = current
            if scene and hasattr(scene, "_repo_update_token"):
                scene._repo_update_token(self.token_id, conditions_json=current)
        elif chosen == label_act:
            self._data["label_visible"] = not self._data.get("label_visible", True)
            if scene and hasattr(scene, "_repo_update_token"):
                scene._repo_update_token(
                    self.token_id, label_visible=int(self._data["label_visible"])
                )
            self.update()
        elif chosen == vis_act:
            self._data["visible"] = not self._data.get("visible", True)
            self.setVisible(self._data["visible"])
            if scene and hasattr(scene, "_repo_update_token"):
                scene._repo_update_token(
                    self.token_id, visible=int(self._data["visible"])
                )
        elif chosen == del_act:
            if scene and hasattr(scene, "token_deleted"):
                scene.token_deleted.emit(self.token_id)

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene and hasattr(scene, "token_moved"):
            p = self.pos()
            self._data["x"] = p.x()
            self._data["y"] = p.y()
            scene.token_moved.emit(self.token_id, p.x(), p.y())


# ══════════════════════════════════════════════════════════════════════════════
#  MapScene
# ══════════════════════════════════════════════════════════════════════════════

class MapScene(QGraphicsScene):
    token_edit_requested  = Signal(dict)
    token_deleted         = Signal(int)
    token_moved           = Signal(int, float, float)
    fog_changed           = Signal()
    grid_aligned          = Signal()
    grid_changed          = Signal(int, int, int)   # cell_px, offset_x, offset_y
    grid_measure_ready    = Signal(float, float, float, float)  # x1,y1,x2,y2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._map_data: dict = {}
        self._tool: str = MapTool.SELECT
        self._cell_px: int = 50
        self._offset_x: int = 0
        self._offset_y: int = 0
        self._bg_item: Optional[QGraphicsPixmapItem] = None
        self._tokens: dict = {}
        self._measure_start: Optional[QPointF] = None
        self._measure_line: Optional[QGraphicsLineItem] = None
        self._measure_label: Optional[QGraphicsTextItem] = None
        self._fog_painting: bool = False
        self._align_pt1: Optional[QPointF] = None
        self._align_markers: list = []
        self._active_layer: str = MapLayer.TOKENS
        self._layer_visibility: dict = {layer: True for layer in LAYER_Z}
        # Non-uniform grid state
        self._col_widths: list = []
        self._row_heights: list = []

        # Persistent overlay items
        self._grid_item = GridOverlayItem()
        self._fog_item  = FogOfWarItem()
        self.addItem(self._grid_item)
        self.addItem(self._fog_item)

        # Grid resize handles
        self._right_handle  = GridResizeHandle("right",  self)
        self._bottom_handle = GridResizeHandle("bottom", self)
        self.addItem(self._right_handle)
        self.addItem(self._bottom_handle)
        self._right_handle.setVisible(False)
        self._bottom_handle.setVisible(False)

    # ── Repo callback (set by MapUI) ──────────────────────────────────────────

    def _repo_update_token(self, token_id: int, **kwargs):
        """Called by TokenItem to persist changes; wired from MapUI."""
        pass

    # ── Map loading ───────────────────────────────────────────────────────────

    def load_map(self, map_data: dict, tokens: list):
        """Clear scene and load map + tokens."""
        self.clear()
        self._tokens.clear()
        self._map_data = dict(map_data)
        self._bg_item = None
        self._measure_line = None
        self._measure_label = None
        self._align_pt1 = None
        self._align_markers = []
        self._col_widths = []
        self._row_heights = []

        # Re-add persistent items after clear()
        self._grid_item = GridOverlayItem()
        self._fog_item  = FogOfWarItem()
        self.addItem(self._grid_item)
        self.addItem(self._fog_item)

        self._right_handle  = GridResizeHandle("right",  self)
        self._bottom_handle = GridResizeHandle("bottom", self)
        self.addItem(self._right_handle)
        self.addItem(self._bottom_handle)
        self._right_handle.setVisible(False)
        self._bottom_handle.setVisible(False)

        # Background image
        image_path = map_data.get("image_path", "")
        scene_w, scene_h = 1500.0, 1000.0
        if image_path and Path(image_path).exists():
            pm = QPixmap(image_path)
            if not pm.isNull():
                self._bg_item = QGraphicsPixmapItem(pm)
                self._bg_item.setZValue(LAYER_Z[MapLayer.BACKGROUND])
                self._bg_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                self._bg_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                self.addItem(self._bg_item)
                scene_w = float(pm.width())
                scene_h = float(pm.height())

        self.setSceneRect(QRectF(0, 0, scene_w, scene_h))

        # Grid
        cell_px      = int(map_data.get("grid_size", 50)) or 50
        offset_x     = int(map_data.get("grid_offset_x", 0))
        offset_y     = int(map_data.get("grid_offset_y", 0))
        grid_color   = map_data.get("grid_color", "#ffffff")
        grid_opacity = float(map_data.get("grid_opacity", 0.3))
        grid_cols    = int(map_data.get("grid_cols", 0))
        grid_rows    = int(map_data.get("grid_rows", 0))
        if grid_cols <= 0:
            grid_cols = math.ceil(scene_w / cell_px)
        if grid_rows <= 0:
            grid_rows = math.ceil(scene_h / cell_px)

        self._cell_px  = cell_px
        self._offset_x = offset_x
        self._offset_y = offset_y

        self._grid_item.configure(
            cell_px, grid_cols, grid_rows,
            offset_x, offset_y,
            grid_color, grid_opacity,
            scene_w, scene_h,
        )
        grid_enabled = bool(map_data.get("grid_enabled", True))
        self._grid_item.set_enabled(grid_enabled)

        self._fog_item.configure(
            cell_px, grid_cols, grid_rows,
            offset_x, offset_y,
            scene_w, scene_h,
        )
        fog_data = map_data.get("fog_data", [])
        self._fog_item.set_revealed(fog_data)
        self._fog_item.set_enabled(bool(map_data.get("fog_enabled", False)))

        # Load non-uniform data if present
        col_widths  = map_data.get("col_widths_json", []) or []
        row_heights = map_data.get("row_heights_json", []) or []
        self._col_widths  = [int(x) for x in col_widths]
        self._row_heights = [int(x) for x in row_heights]
        if self._col_widths and self._row_heights:
            self._grid_item._col_widths  = list(self._col_widths)
            self._grid_item._row_heights = list(self._row_heights)
            self._fog_item._col_widths   = list(self._col_widths)
            self._fog_item._row_heights  = list(self._row_heights)
            self._fog_item._dirty = True
            self._grid_item.update()
            self._fog_item.update()

        # Tokens
        for td in tokens:
            self.add_token_from_data(td)

        # Position handles and show if grid enabled
        self._update_handle_positions()
        self.set_grid_handles_visible(grid_enabled)

    # ── Tool / grid / fog ─────────────────────────────────────────────────────

    def set_tool(self, tool: str):
        self._tool = tool

    def set_active_layer(self, layer: str):
        self._active_layer = layer

    def set_grid(
        self,
        enabled: bool,
        cell_px: int,
        offset_x: int = 0,
        offset_y: int = 0,
        color: str = "#ffffff",
        opacity: float = 0.3,
        line_width: float = None,  # None = keep existing width
    ):
        self._cell_px  = cell_px
        self._offset_x = offset_x
        self._offset_y = offset_y
        rect = self.sceneRect()
        cols = math.ceil(rect.width()  / max(1, cell_px))
        rows = math.ceil(rect.height() / max(1, cell_px))
        lw = line_width if line_width is not None else self._grid_item._line_width
        self._grid_item.configure(
            cell_px, cols, rows, offset_x, offset_y,
            color, opacity, rect.width(), rect.height(),
            line_width=lw,
        )
        self._grid_item.set_enabled(enabled)
        self._fog_item.configure(
            cell_px, cols, rows, offset_x, offset_y,
            rect.width(), rect.height(),
        )
        for token in self._tokens.values():
            token.set_grid(cell_px, offset_x, offset_y)
        self._update_handle_positions()

    def set_grid_handles_visible(self, visible: bool):
        self._right_handle.setVisible(visible)
        self._bottom_handle.setVisible(visible)

    def _update_handle_positions(self):
        grid = self._grid_item
        # Right handle: right edge of grid, mid-height
        if grid._col_widths:
            rx = float(grid._offset_x) + sum(grid._col_widths)
        else:
            rx = grid._offset_x + grid._cols * grid._cell_px
        if grid._row_heights:
            ry = float(grid._offset_y) + sum(grid._row_heights) / 2
        else:
            ry = grid._offset_y + (grid._rows * grid._cell_px) / 2
        self._right_handle.setPos(rx, ry)
        # Bottom handle: mid-width, bottom edge
        if grid._col_widths:
            bx = float(grid._offset_x) + sum(grid._col_widths) / 2
        else:
            bx = grid._offset_x + (grid._cols * grid._cell_px) / 2
        if grid._row_heights:
            by = float(grid._offset_y) + sum(grid._row_heights)
        else:
            by = grid._offset_y + grid._rows * grid._cell_px
        self._bottom_handle.setPos(bx, by)

    def set_fog_enabled(self, enabled: bool):
        self._fog_item.set_enabled(enabled)

    def set_fog_opacity(self, opacity: float):
        """Set the fog overlay opacity (0.0 = invisible, 1.0 = fully black)."""
        self._fog_item._fog_opacity = max(0.0, min(1.0, opacity))
        self._fog_item.update()

    def fog_reveal_all(self):
        self._fog_item.reveal_all()
        self.fog_changed.emit()

    def fog_hide_all(self):
        self._fog_item.hide_all()
        self.fog_changed.emit()

    def set_layer_visibility(self, layer: str, visible: bool):
        self._layer_visibility[layer] = visible
        if layer == MapLayer.FOG:
            self._fog_item.setVisible(visible)
        elif layer == MapLayer.TOKENS:
            for token in self._tokens.values():
                token.setVisible(visible and token.token_data.get("visible", True))
        elif layer == MapLayer.BACKGROUND:
            if self._bg_item:
                self._bg_item.setVisible(visible)
        else:
            z_val = LAYER_Z.get(layer)
            if z_val is not None:
                for item in self.items():
                    if (item is not self._grid_item
                            and item is not self._fog_item
                            and item is not self._bg_item
                            and item is not self._right_handle
                            and item is not self._bottom_handle
                            and not isinstance(item, TokenItem)):
                        if abs(item.zValue() - z_val) < 1:
                            item.setVisible(visible)

    # ── Non-uniform grid ──────────────────────────────────────────────────────

    def _ensure_nonuniform(self):
        """Convert uniform grid to non-uniform arrays if not already done."""
        grid = self._grid_item
        if not self._col_widths:
            self._col_widths = [self._cell_px] * grid.num_cols()
        if not self._row_heights:
            self._row_heights = [self._cell_px] * grid.num_rows()
        grid._col_widths  = list(self._col_widths)
        grid._row_heights = list(self._row_heights)
        self._fog_item._col_widths  = list(self._col_widths)
        self._fog_item._row_heights = list(self._row_heights)
        self._fog_item._dirty = True

    def resize_col(self, col_idx: int, new_width: int):
        self._ensure_nonuniform()
        if 0 <= col_idx < len(self._col_widths):
            self._col_widths[col_idx] = max(5, new_width)
            self._grid_item._col_widths = list(self._col_widths)
            self._fog_item._col_widths  = list(self._col_widths)
            self._fog_item._dirty = True
            self._grid_item.update()
            self._fog_item.update()
            self.grid_changed.emit(self._cell_px, self._offset_x, self._offset_y)

    def resize_row(self, row_idx: int, new_height: int):
        self._ensure_nonuniform()
        if 0 <= row_idx < len(self._row_heights):
            self._row_heights[row_idx] = max(5, new_height)
            self._grid_item._row_heights = list(self._row_heights)
            self._fog_item._row_heights  = list(self._row_heights)
            self._fog_item._dirty = True
            self._grid_item.update()
            self._fog_item.update()
            self.grid_changed.emit(self._cell_px, self._offset_x, self._offset_y)

    def add_col(self, width: int = None):
        self._ensure_nonuniform()
        w = width or (self._col_widths[-1] if self._col_widths else self._cell_px)
        self._col_widths.append(w)
        self._grid_item._col_widths = list(self._col_widths)
        self._fog_item._col_widths  = list(self._col_widths)
        self._fog_item._dirty = True
        rect = self.sceneRect()
        self.setSceneRect(QRectF(0, 0, rect.width() + w, rect.height()))
        self._grid_item._scene_w = self.sceneRect().width()
        self._fog_item._scene_w  = self.sceneRect().width()
        self._grid_item.prepareGeometryChange()
        self._fog_item.prepareGeometryChange()
        self._grid_item.update()
        self._fog_item.update()
        self._update_handle_positions()
        self.grid_changed.emit(self._cell_px, self._offset_x, self._offset_y)

    def remove_col(self, col_idx: int = -1):
        self._ensure_nonuniform()
        if len(self._col_widths) <= 1:
            return
        if col_idx < 0:
            col_idx = len(self._col_widths) - 1
        removed_w = self._col_widths.pop(col_idx)
        self._grid_item._col_widths = list(self._col_widths)
        self._fog_item._col_widths  = list(self._col_widths)
        self._fog_item._dirty = True
        rect = self.sceneRect()
        self.setSceneRect(QRectF(0, 0, max(100, rect.width() - removed_w), rect.height()))
        self._grid_item._scene_w = self.sceneRect().width()
        self._fog_item._scene_w  = self.sceneRect().width()
        self._grid_item.prepareGeometryChange()
        self._fog_item.prepareGeometryChange()
        self._grid_item.update()
        self._fog_item.update()
        self._update_handle_positions()
        self.grid_changed.emit(self._cell_px, self._offset_x, self._offset_y)

    def add_row(self, height: int = None):
        self._ensure_nonuniform()
        h = height or (self._row_heights[-1] if self._row_heights else self._cell_px)
        self._row_heights.append(h)
        self._grid_item._row_heights = list(self._row_heights)
        self._fog_item._row_heights  = list(self._row_heights)
        self._fog_item._dirty = True
        rect = self.sceneRect()
        self.setSceneRect(QRectF(0, 0, rect.width(), rect.height() + h))
        self._grid_item._scene_h = self.sceneRect().height()
        self._fog_item._scene_h  = self.sceneRect().height()
        self._grid_item.prepareGeometryChange()
        self._fog_item.prepareGeometryChange()
        self._grid_item.update()
        self._fog_item.update()
        self._update_handle_positions()
        self.grid_changed.emit(self._cell_px, self._offset_x, self._offset_y)

    def remove_row(self, row_idx: int = -1):
        self._ensure_nonuniform()
        if len(self._row_heights) <= 1:
            return
        if row_idx < 0:
            row_idx = len(self._row_heights) - 1
        removed_h = self._row_heights.pop(row_idx)
        self._grid_item._row_heights = list(self._row_heights)
        self._fog_item._row_heights  = list(self._row_heights)
        self._fog_item._dirty = True
        rect = self.sceneRect()
        self.setSceneRect(QRectF(0, 0, rect.width(), max(100, rect.height() - removed_h)))
        self._grid_item._scene_h = self.sceneRect().height()
        self._fog_item._scene_h  = self.sceneRect().height()
        self._grid_item.prepareGeometryChange()
        self._fog_item.prepareGeometryChange()
        self._grid_item.update()
        self._fog_item.update()
        self._update_handle_positions()
        self.grid_changed.emit(self._cell_px, self._offset_x, self._offset_y)

    def get_grid_hit(self, scene_pos: QPointF, tolerance: float):
        """
        Return ("col", col_idx) or ("row", row_idx) if scene_pos is
        within tolerance pixels of that divider. Returns None otherwise.
        col_idx is the index of the column whose right border was hit.
        """
        if not self._grid_item._enabled:
            return None
        grid = self._grid_item
        x, y = scene_pos.x(), scene_pos.y()

        # Check column dividers (vertical lines)
        if self._col_widths:
            cx = float(self._offset_x)
            for i, w in enumerate(self._col_widths):
                cx += w
                if abs(x - cx) <= tolerance:
                    return ("col", i)
        else:
            for col in range(1, grid._cols + 1):
                cx = self._offset_x + col * self._cell_px
                if abs(x - cx) <= tolerance:
                    return ("col", col - 1)

        # Check row dividers (horizontal lines)
        if self._row_heights:
            cy = float(self._offset_y)
            for i, h in enumerate(self._row_heights):
                cy += h
                if abs(y - cy) <= tolerance:
                    return ("row", i)
        else:
            for row in range(1, grid._rows + 1):
                cy = self._offset_y + row * self._cell_px
                if abs(y - cy) <= tolerance:
                    return ("row", row - 1)

        return None

    def get_grid_state(self) -> dict:
        return {
            "col_widths":  list(self._col_widths),
            "row_heights": list(self._row_heights),
        }

    # ── Token management ──────────────────────────────────────────────────────

    def add_token_from_data(self, token_data: dict) -> TokenItem:
        item = TokenItem(token_data, self._cell_px)
        item._offset_x = self._offset_x
        item._offset_y = self._offset_y
        self.addItem(item)
        tid = item.token_id
        if tid >= 0:
            self._tokens[tid] = item
        return item

    def remove_token(self, token_id: int):
        item = self._tokens.pop(token_id, None)
        if item is not None:
            self.removeItem(item)

    def update_token_data(self, token_id: int, data: dict):
        item = self._tokens.get(token_id)
        if item:
            item._data.update(data)
            item._load_pixmap()
            item.prepareGeometryChange()
            item.update()

    # ── State ─────────────────────────────────────────────────────────────────

    def get_map_state(self) -> dict:
        return {
            "fog_data": self._fog_item.get_revealed_list(),
            "token_positions": {
                tid: (item.pos().x(), item.pos().y())
                for tid, item in self._tokens.items()
            },
        }

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if self._tool in (MapTool.FOG_PAINT, MapTool.FOG_ERASE):
            self._fog_painting = True
            self._apply_fog_at(
                event.scenePos(), reveal=(self._tool == MapTool.FOG_PAINT)
            )
            return
        if self._tool == MapTool.MEASURE:
            if self._measure_start is None:
                self._measure_start = event.scenePos()
                self._start_measure_line(self._measure_start)
            else:
                self._clear_measure()
            return
        if self._tool == MapTool.GRID_ALIGN:
            if self._align_pt1 is None:
                self._align_pt1 = event.scenePos()
                self._draw_align_marker(event.scenePos(), first=True)
            else:
                pt2 = event.scenePos()
                self._calculate_and_apply_grid_from_points(self._align_pt1, pt2)
                self._align_pt1 = None
                self._clear_align_markers()
                self.grid_aligned.emit()
            return
        if self._tool == MapTool.GRID_MEASURE:
            if self._align_pt1 is None:
                # First click: mark the start point
                self._align_pt1 = event.scenePos()
                self._draw_align_marker(event.scenePos(), first=True)
            else:
                # Second click: emit both points so UI can show the dialog
                pt2 = event.scenePos()
                pt1 = self._align_pt1
                self._align_pt1 = None
                self._clear_align_markers()
                self.grid_measure_ready.emit(
                    pt1.x(), pt1.y(), pt2.x(), pt2.y()
                )
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._fog_painting and self._tool in (MapTool.FOG_PAINT, MapTool.FOG_ERASE):
            self._apply_fog_at(
                event.scenePos(), reveal=(self._tool == MapTool.FOG_PAINT)
            )
            return
        if self._tool == MapTool.MEASURE and self._measure_start is not None:
            self._update_measure(event.scenePos())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        self._fog_painting = False
        super().mouseReleaseEvent(event)

    # ── Fog helpers ───────────────────────────────────────────────────────────

    def _apply_fog_at(self, scene_pos: QPointF, reveal: bool):
        x, y = scene_pos.x(), scene_pos.y()
        grid = self._grid_item
        if grid._col_widths and grid._row_heights:
            # Find col
            col = -1
            cx = float(grid._offset_x)
            for i, cw in enumerate(grid._col_widths):
                if cx <= x < cx + cw:
                    col = i
                    break
                cx += cw
            # Find row
            row = -1
            cy = float(grid._offset_y)
            for i, rh in enumerate(grid._row_heights):
                if cy <= y < cy + rh:
                    row = i
                    break
                cy += rh
            if col >= 0 and row >= 0:
                self._fog_item.toggle_cell(col, row, reveal)
                self.fog_changed.emit()
        else:
            col = int((x - self._offset_x) // self._cell_px)
            row = int((y - self._offset_y) // self._cell_px)
            fog = self._fog_item
            if 0 <= col < fog._cols and 0 <= row < fog._rows:
                fog.toggle_cell(col, row, reveal)
                self.fog_changed.emit()

    # ── Measure helpers ───────────────────────────────────────────────────────

    def _start_measure_line(self, start: QPointF):
        pen = QPen(QColor("#e07800"))
        pen.setCosmetic(True)
        pen.setWidthF(2.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        self._measure_line = self.addLine(QLineF(start, start), pen)
        self._measure_line.setZValue(100)
        self._measure_label = self.addText("0 ft", QFont("", 10))
        self._measure_label.setDefaultTextColor(QColor("#e07800"))
        self._measure_label.setZValue(101)

    def _update_measure(self, end: QPointF):
        if self._measure_line and self._measure_start:
            self._measure_line.setLine(QLineF(self._measure_start, end))
            dx = (end.x() - self._measure_start.x()) / self._cell_px
            dy = (end.y() - self._measure_start.y()) / self._cell_px
            cells = math.sqrt(dx * dx + dy * dy)
            feet  = cells * 5
            label = f"{cells:.1f} sq / {feet:.0f} ft"
            if self._measure_label:
                self._measure_label.setPlainText(label)
                self._measure_label.setPos(end.x() + 6, end.y() - 18)

    def _clear_measure(self):
        if self._measure_line:
            self.removeItem(self._measure_line)
            self._measure_line = None
        if self._measure_label:
            self.removeItem(self._measure_label)
            self._measure_label = None
        self._measure_start = None

    # ── Grid alignment helpers ────────────────────────────────────────────────

    def _draw_align_marker(self, pos: QPointF, first: bool = True):
        r = 6.0
        pen = QPen(QColor("#e05555"))
        pen.setCosmetic(True)
        pen.setWidthF(2.0)
        ellipse = self.addEllipse(
            QRectF(pos.x() - r, pos.y() - r, r * 2, r * 2),
            pen,
            QBrush(QColor(224, 85, 85, 120)),
        )
        ellipse.setZValue(200)
        self._align_markers.append(ellipse)
        hline = self.addLine(
            QLineF(pos.x() - r * 2.5, pos.y(), pos.x() + r * 2.5, pos.y()), pen
        )
        hline.setZValue(200)
        self._align_markers.append(hline)
        vline = self.addLine(
            QLineF(pos.x(), pos.y() - r * 2.5, pos.x(), pos.y() + r * 2.5), pen
        )
        vline.setZValue(200)
        self._align_markers.append(vline)
        if first:
            lbl = self.addText(
                "Now click the bottom-right corner of the same cell",
                QFont("", 10),
            )
            lbl.setDefaultTextColor(QColor("#e07800"))
            lbl.setZValue(201)
            lbl.setPos(pos.x() + 14, pos.y() + 4)
            self._align_markers.append(lbl)

    def _clear_align_markers(self):
        for item in self._align_markers:
            if item.scene() is self:
                self.removeItem(item)
        self._align_markers.clear()

    def _calculate_and_apply_grid_from_points(self, pt1: QPointF, pt2: QPointF):
        """Derive grid cell_px and offset from two diagonal corners of a cell."""
        dx = abs(pt2.x() - pt1.x())
        dy = abs(pt2.y() - pt1.y())
        cell_px = max(5, int(round((dx + dy) / 2)))
        tl_x = min(pt1.x(), pt2.x())
        tl_y = min(pt1.y(), pt2.y())
        offset_x = int(tl_x) % cell_px
        offset_y = int(tl_y) % cell_px
        self.set_grid(
            enabled=True,
            cell_px=cell_px,
            offset_x=offset_x,
            offset_y=offset_y,
            color=self._grid_item._color,
            opacity=self._grid_item._opacity,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  MapView
# ══════════════════════════════════════════════════════════════════════════════

class MapView(QGraphicsView):
    """Zoom/pan view for MapScene. Accepts token drops from the library panel."""

    def __init__(self, scene: MapScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("background: #141414; border: none;")
        self.setAcceptDrops(True)
        self.setMinimumSize(400, 300)
        self._zoom = 1.0
        self._pan_active = False
        self._pan_start = None
        self._space_held = False
        # Per-column/row drag resize state
        self._grid_resize_active = False
        self._grid_resize_type: str = ""
        self._grid_resize_idx: int = -1
        self._grid_resize_start_scene: float = 0.0
        self._grid_resize_orig_size: int = 0
        self._GRID_HIT_PX = 6  # screen pixels hit zone
        self._grid_locked = False  # when True, suppress all grid drag / hit detection

    # ── Zoom / pan ────────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else (1 / 1.15)
        new_zoom = max(0.1, min(8.0, self._zoom * factor))
        self.scale(new_zoom / self._zoom, new_zoom / self._zoom)
        self._zoom = new_zoom

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space:
            self._space_held = True
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        elif event.key() == Qt.Key.Key_Escape:
            self.scene().clearSelection()
            if hasattr(self.scene(), "_clear_measure"):
                self.scene()._clear_measure()
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            scene = self.scene()
            for item in list(scene.selectedItems()):
                if isinstance(item, TokenItem):
                    scene.token_deleted.emit(item.token_id)
        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            new_zoom = min(8.0, self._zoom * 1.2)
            self.scale(new_zoom / self._zoom, new_zoom / self._zoom)
            self._zoom = new_zoom
        elif event.key() == Qt.Key.Key_Minus:
            new_zoom = max(0.1, self._zoom / 1.2)
            self.scale(new_zoom / self._zoom, new_zoom / self._zoom)
            self._zoom = new_zoom
        elif event.key() == Qt.Key.Key_R:
            self.set_zoom(1.0)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space:
            self._space_held = False
            if not self._pan_active:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mousePressEvent(self, event):
        # Middle mouse / space+left = pan
        if (event.button() == Qt.MouseButton.MiddleButton or
                (self._space_held and event.button() == Qt.MouseButton.LeftButton)):
            self._pan_active = True
            self._pan_start  = event.pos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            return
        # Left click: check for grid resize in SELECT mode
        if event.button() == Qt.MouseButton.LeftButton:
            scene = self.scene()
            tool = getattr(scene, '_tool', 'select') if scene else 'select'
            if tool == MapTool.SELECT:
                # Check for tokens FIRST — tokens snap to grid lines so without
                # this guard every click on a token triggers a grid resize instead
                # of selecting / dragging the token.
                tokens_here = [i for i in self.items(event.pos())
                               if isinstance(i, TokenItem)]
                hit = None if tokens_here else self._grid_hit_at(event.pos())
                if hit:
                    self._grid_resize_active = True
                    self._grid_resize_type   = hit[0]
                    self._grid_resize_idx    = hit[1]
                    scene._ensure_nonuniform()
                    if hit[0] == "col":
                        self._grid_resize_orig_size = scene._col_widths[hit[1]]
                        self._grid_resize_start_scene = self.mapToScene(event.pos()).x()
                    else:
                        self._grid_resize_orig_size = scene._row_heights[hit[1]]
                        self._grid_resize_start_scene = self.mapToScene(event.pos()).y()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Active grid resize takes priority
        if self._grid_resize_active:
            self._do_grid_resize(event.pos())
            return
        if self._pan_active and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            self._pan_start = event.pos()
            return
        # Check for grid proximity (change cursor) — only in SELECT mode
        scene = self.scene()
        tool = getattr(scene, '_tool', 'select') if scene else 'select'
        if tool == MapTool.SELECT and not self._pan_active:
            hit = self._grid_hit_at(event.pos())
            if hit:
                cursor = (Qt.CursorShape.SizeHorCursor if hit[0] == "col"
                          else Qt.CursorShape.SizeVerCursor)
                self.setCursor(QCursor(cursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._grid_resize_active:
            self._grid_resize_active = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            # Trigger save
            scene = self.scene()
            if scene:
                scene.grid_changed.emit(scene._cell_px, scene._offset_x, scene._offset_y)
            event.accept()
            return
        if self._pan_active:
            self._pan_active = False
            self._pan_start  = None
            if self._space_held:
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        else:
            super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        """Reset cursor when the mouse leaves the canvas so it never gets stuck."""
        if not self._pan_active and not self._grid_resize_active:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().leaveEvent(event)

    def _grid_hit_at(self, viewport_pos):
        """Return (type, idx) if viewport_pos is near a grid divider, else None.
        Returns None immediately when the grid is locked."""
        if self._grid_locked:
            return None
        scene = self.scene()
        if not scene or not hasattr(scene, 'get_grid_hit'):
            return None
        scene_pos = self.mapToScene(viewport_pos)
        tol = self._GRID_HIT_PX / max(0.01, self._zoom)
        return scene.get_grid_hit(scene_pos, tol)

    def _do_grid_resize(self, viewport_pos):
        scene = self.scene()
        if not scene:
            return
        scene_pos = self.mapToScene(viewport_pos)
        if self._grid_resize_type == "col":
            delta = scene_pos.x() - self._grid_resize_start_scene
            new_w = max(5, int(round(self._grid_resize_orig_size + delta)))
            scene.resize_col(self._grid_resize_idx, new_w)
        else:
            delta = scene_pos.y() - self._grid_resize_start_scene
            new_h = max(5, int(round(self._grid_resize_orig_size + delta)))
            scene.resize_row(self._grid_resize_idx, new_h)

    def set_zoom(self, zoom: float):
        zoom = max(0.1, min(8.0, zoom))
        self.scale(zoom / self._zoom, zoom / self._zoom)
        self._zoom = zoom

    def get_current_state(self) -> dict:
        return {
            "zoom":  self._zoom,
            "pan_x": float(self.horizontalScrollBar().value()),
            "pan_y": float(self.verticalScrollBar().value()),
        }

    def restore_state(self, state: dict):
        self.set_zoom(float(state.get("zoom", 1.0)))
        QTimer.singleShot(0, lambda: (
            self.horizontalScrollBar().setValue(int(state.get("pan_x", 0))),
            self.verticalScrollBar().setValue(int(state.get("pan_y", 0))),
        ))

    # ── Drag and drop (from token library) ───────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-craftmatica-token"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-craftmatica-token"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-craftmatica-token"):
            raw = bytes(event.mimeData().data("application/x-craftmatica-token"))
            try:
                lib_data = json.loads(raw.decode("utf-8"))
            except Exception:
                event.ignore()
                return
            scene_pos = self.mapToScene(event.pos())
            if hasattr(self, "_on_token_drop"):
                self._on_token_drop(lib_data, scene_pos)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
