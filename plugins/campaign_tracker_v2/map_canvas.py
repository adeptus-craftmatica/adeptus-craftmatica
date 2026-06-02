"""
Map Canvas — Campaign Tracker v2.

QGraphicsScene + QGraphicsView interactive map editor.
Features: grid overlay, fog of war, draggable tokens, zoom/pan, measure tool.
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


# ── Tool modes ──────────────────────────────────────────────────────────────

class MapTool:
    SELECT    = "select"
    FOG_PAINT = "fog_paint"
    FOG_ERASE = "fog_erase"
    MEASURE   = "measure"


# ── Helpers ─────────────────────────────────────────────────────────────────

def snap_to_grid(pos: QPointF, cell_px: int, offset_x: int = 0, offset_y: int = 0) -> QPointF:
    """Snap a position to the nearest grid intersection."""
    if cell_px < 1:
        return pos
    col = round((pos.x() - offset_x) / cell_px)
    row = round((pos.y() - offset_y) / cell_px)
    return QPointF(offset_x + col * cell_px, offset_y + row * cell_px)


# ══════════════════════════════════════════════════════════════════════════════
#  GridOverlayItem
# ══════════════════════════════════════════════════════════════════════════════

class GridOverlayItem(QGraphicsItem):
    """Draws grid lines over the map image."""

    def __init__(self):
        super().__init__()
        self.setZValue(10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._enabled   = True
        self._cell_px   = 50
        self._cols      = 20
        self._rows      = 20
        self._offset_x  = 0
        self._offset_y  = 0
        self._color     = "#ffffff"
        self._opacity   = 0.3
        self._scene_w   = 1000.0
        self._scene_h   = 1000.0

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
    ):
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

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._scene_w, self._scene_h)

    def paint(self, painter, option, widget=None):
        if not self._enabled:
            return
        painter.save()
        pen = QPen(QColor(self._color))
        pen.setCosmetic(True)
        pen.setWidthF(0.7)
        painter.setPen(pen)
        painter.setOpacity(self._opacity)
        for col in range(self._cols + 1):
            x = self._offset_x + col * self._cell_px
            painter.drawLine(QLineF(x, 0, x, self._scene_h))
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
        self.setZValue(50)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._enabled: bool = False
        self._revealed: set[tuple[int, int]] = set()
        self._cell_px   = 50
        self._cols      = 20
        self._rows      = 20
        self._offset_x  = 0
        self._offset_y  = 0
        self._scene_w   = 1000.0
        self._scene_h   = 1000.0
        self._path_cache: Optional[QPainterPath] = None
        self._dirty     = True

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
            painter.setOpacity(0.85)
            painter.fillPath(self._path_cache, QBrush(QColor(0, 0, 0)))
            painter.restore()


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
        self.setZValue(20 + self._data.get("layer", 1) * 5)
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
                size = max(w, h)
                scaled = pm.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # Pad to square (w x h)
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
            # Draw rounded-rect clipped pixmap
            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(0, 0, w, h), 6, 6)
            painter.setClipPath(clip_path)
            painter.drawPixmap(0, 0, self._pixmap)
            painter.setClipping(False)
        else:
            # Avatar: filled circle with initials
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
            # Background
            painter.setBrush(QBrush(QColor(0, 0, 0, 120)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(0, bar_y, w, bar_h))
            # Fill
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
                # Background
                painter.setBrush(QBrush(QColor(0, 0, 0, 160)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(lbl_x, lbl_y, lbl_w, lbl_h), 3, 3)
                # Text
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

        edit_act = menu.addAction("Edit Token…")
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
        # Notify scene of final position
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
    token_edit_requested = Signal(dict)
    token_deleted        = Signal(int)
    token_moved          = Signal(int, float, float)
    fog_changed          = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._map_data: dict = {}
        self._tool: str = MapTool.SELECT
        self._cell_px: int = 50
        self._offset_x: int = 0
        self._offset_y: int = 0
        self._bg_item: Optional[QGraphicsPixmapItem] = None
        self._tokens: dict[int, TokenItem] = {}
        self._measure_start: Optional[QPointF] = None
        self._measure_line: Optional[QGraphicsLineItem] = None
        self._measure_label: Optional[QGraphicsTextItem] = None
        self._fog_painting: bool = False
        self._space_held: bool = False

        # Create persistent overlay items
        self._grid_item = GridOverlayItem()
        self._fog_item  = FogOfWarItem()
        self.addItem(self._grid_item)
        self.addItem(self._fog_item)

    # ── Repo callback (set by MapUI) ──────────────────────────────────────────

    def _repo_update_token(self, token_id: int, **kwargs):
        """Called by TokenItem to persist changes; wired from MapUI."""
        pass  # Overridden at runtime by MapUI._connect_scene_signals

    # ── Map loading ───────────────────────────────────────────────────────────

    def load_map(self, map_data: dict, tokens: list[dict]):
        """Clear scene and load map + tokens."""
        self.clear()
        self._tokens.clear()
        self._map_data = dict(map_data)
        self._bg_item = None
        self._measure_line = None
        self._measure_label = None

        # Re-add persistent items after clear()
        self._grid_item = GridOverlayItem()
        self._fog_item  = FogOfWarItem()
        self.addItem(self._grid_item)
        self.addItem(self._fog_item)

        # Background image
        image_path = map_data.get("image_path", "")
        scene_w, scene_h = 1500.0, 1000.0
        if image_path and Path(image_path).exists():
            pm = QPixmap(image_path)
            if not pm.isNull():
                self._bg_item = QGraphicsPixmapItem(pm)
                self._bg_item.setZValue(-10)
                self._bg_item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False
                )
                self._bg_item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False
                )
                self.addItem(self._bg_item)
                scene_w = float(pm.width())
                scene_h = float(pm.height())

        self.setSceneRect(QRectF(0, 0, scene_w, scene_h))

        # Grid
        cell_px  = int(map_data.get("grid_size", 50)) or 50
        offset_x = int(map_data.get("grid_offset_x", 0))
        offset_y = int(map_data.get("grid_offset_y", 0))
        grid_color   = map_data.get("grid_color", "#ffffff")
        grid_opacity = float(map_data.get("grid_opacity", 0.3))

        # Compute cols/rows
        grid_cols = int(map_data.get("grid_cols", 0))
        grid_rows = int(map_data.get("grid_rows", 0))
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
        self._grid_item.set_enabled(bool(map_data.get("grid_enabled", True)))

        self._fog_item.configure(
            cell_px, grid_cols, grid_rows,
            offset_x, offset_y,
            scene_w, scene_h,
        )
        fog_data = map_data.get("fog_data", [])
        self._fog_item.set_revealed(fog_data)
        self._fog_item.set_enabled(bool(map_data.get("fog_enabled", False)))

        # Tokens
        for td in tokens:
            self.add_token_from_data(td)

    # ── Tool / grid / fog ─────────────────────────────────────────────────────

    def set_tool(self, tool: str):
        self._tool = tool

    def set_grid(
        self,
        enabled: bool,
        cell_px: int,
        offset_x: int = 0,
        offset_y: int = 0,
        color: str = "#ffffff",
        opacity: float = 0.3,
    ):
        self._cell_px  = cell_px
        self._offset_x = offset_x
        self._offset_y = offset_y
        rect = self.sceneRect()
        cols = math.ceil(rect.width()  / max(1, cell_px))
        rows = math.ceil(rect.height() / max(1, cell_px))
        self._grid_item.configure(
            cell_px, cols, rows, offset_x, offset_y,
            color, opacity, rect.width(), rect.height(),
        )
        self._grid_item.set_enabled(enabled)
        self._fog_item.configure(
            cell_px, cols, rows, offset_x, offset_y,
            rect.width(), rect.height(),
        )
        for token in self._tokens.values():
            token.set_grid(cell_px, offset_x, offset_y)

    def set_fog_enabled(self, enabled: bool):
        self._fog_item.set_enabled(enabled)

    def fog_reveal_all(self):
        self._fog_item.reveal_all()
        self.fog_changed.emit()

    def fog_hide_all(self):
        self._fog_item.hide_all()
        self.fog_changed.emit()

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
        self._measure_line = self.addLine(
            QLineF(start, start), pen
        )
        self._measure_line.setZValue(100)
        self._measure_label = self.addText("0 ft", QFont("", 10))
        self._measure_label.setDefaultTextColor(QColor("#e07800"))
        self._measure_label.setZValue(101)

    def _update_measure(self, end: QPointF):
        if self._measure_line and self._measure_start:
            self._measure_line.setLine(
                QLineF(self._measure_start, end)
            )
            dx = (end.x() - self._measure_start.x()) / self._cell_px
            dy = (end.y() - self._measure_start.y()) / self._cell_px
            cells = math.sqrt(dx * dx + dy * dy)
            feet  = cells * 5
            label = f"{cells:.1f} sq / {feet:.0f} ft"
            if self._measure_label:
                self._measure_label.setPlainText(label)
                self._measure_label.setPos(
                    end.x() + 6, end.y() - 18
                )

    def _clear_measure(self):
        if self._measure_line:
            self.removeItem(self._measure_line)
            self._measure_line = None
        if self._measure_label:
            self.removeItem(self._measure_label)
            self._measure_label = None
        self._measure_start = None


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
        self._zoom = 1.0
        self._pan_active = False
        self._pan_start = None
        self._space_held = False

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
            # Delete selected tokens
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
        if (
            event.button() == Qt.MouseButton.MiddleButton
            or (self._space_held and event.button() == Qt.MouseButton.LeftButton)
        ):
            self._pan_active = True
            self._pan_start  = event.pos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_active and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            self._pan_start = event.pos()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_active:
            self._pan_active = False
            self._pan_start  = None
            if self._space_held:
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        else:
            super().mouseReleaseEvent(event)

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
