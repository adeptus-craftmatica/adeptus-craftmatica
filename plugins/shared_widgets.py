"""
Shared UI widgets used across multiple plugins.

PhotoCropDialog — avatar-style image cropper.
  The user drags the image to reposition it and uses a slider (or scroll wheel)
  to zoom in/out. The bordered preview shows exactly what will be saved.

Usage:
    from plugins.shared_widgets import PhotoCropDialog, focal_pixmap

    dlg = PhotoCropDialog(image_path, thumb_w=210, thumb_h=175,
                          zoom=1.0, fx=0.5, fy=0.5, parent=self)
    if dlg.exec():
        zoom, fx, fy = dlg.result()
        # persist to DB, re-render thumbnail with focal_pixmap(...)

    pix = focal_pixmap(QPixmap(path), w, h, zoom, fx, fy)
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSlider, QDialogButtonBox, QWidget, QSizePolicy,
)


# ── Cross-plugin relationship widgets ────────────────────────────────────────

# Map plugin_id → (icon, display_name) for navigation labels
_PLUGIN_META: dict[str, tuple[str, str]] = {
    "paint_tracker":    ("🎨", "Paint Tracker"),
    "model_tracker":    ("🤖", "Model Tracker"),
    "army_builder":     ("⚔",  "Army Builder"),
    "campaign_tracker": ("📖", "Campaign Tracker"),
    "calendar":         ("📅", "Calendar"),
    "project_tracker":  ("📋", "Projects"),
    "paint_scheme":     ("🎭", "Paint Schemes"),
}


class LinkedEntityChip(QFrame):
    """
    Compact clickable chip that represents a cross-plugin linked entity.

    Layout  [dot?] [icon?] [name / subtitle] [badge?] [→ nav] [✕ unlink?]

    Signals
    -------
    navigate_requested(plugin_id, entity_id)
        Emitted when the chip body or the → button is clicked.
    unlink_requested(entity_id)
        Emitted when the ✕ unlink button is clicked (show_unlink=True only).
    """

    navigate_requested = Signal(str, int)   # (plugin_id, entity_id)
    unlink_requested   = Signal(int)        # entity_id

    def __init__(
        self, *,
        plugin_id:     str  = "",
        entity_id:     int  = 0,
        icon:          str  = "",
        name:          str  = "",
        subtitle:      str  = "",
        dot_color:     str  = "",     # hex — renders a left color dot
        badge_text:    str  = "",     # short status text, e.g. "Low Stock"
        badge_color:   str  = "",     # hex background for the badge pill
        show_navigate: bool = True,   # show the → arrow button
        show_unlink:   bool = False,  # show the ✕ unlink button
        parent=None,
    ):
        super().__init__(parent)
        self._plugin_id = plugin_id
        self._entity_id = entity_id

        self.setObjectName("linkedEntityChip")
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        navigable = show_navigate and bool(plugin_id)
        if navigable:
            self.setCursor(Qt.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 6, 0)
        row.setSpacing(5)

        # ── Left color dot ────────────────────────────────────────────────────
        if dot_color:
            dot = QLabel()
            dot.setFixedSize(10, 10)
            bright  = QColor(dot_color).lightness()
            bdr_col = "rgba(255,255,255,0.15)" if bright < 128 else "rgba(0,0,0,0.20)"
            dot.setStyleSheet(
                f"background:{dot_color};border:1px solid {bdr_col};"
                "border-radius:2px;"
            )
            row.addWidget(dot)

        # ── Icon ──────────────────────────────────────────────────────────────
        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setFixedWidth(16)
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setStyleSheet("font-size:12px;background:transparent;")
            row.addWidget(icon_lbl)

        # ── Name + subtitle ───────────────────────────────────────────────────
        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.setContentsMargins(0, 0, 0, 0)

        name_lbl = QLabel(name)
        name_lbl.setObjectName("chipName")
        name_lbl.setTextFormat(Qt.PlainText)
        name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text_col.addWidget(name_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setObjectName("chipSubtitle")
            sub_lbl.setTextFormat(Qt.PlainText)
            text_col.addWidget(sub_lbl)

        row.addLayout(text_col, stretch=1)

        # ── Status badge pill ─────────────────────────────────────────────────
        if badge_text:
            badge = QLabel(f" {badge_text} ")
            bc = badge_color or "#0078d4"
            badge.setStyleSheet(
                f"background:{bc};color:#ffffff;"
                "border-radius:3px;font-size:9px;font-weight:600;"
                "padding:1px 3px;"
            )
            badge.setFixedHeight(15)
            row.addWidget(badge)

        # ── Navigate arrow ────────────────────────────────────────────────────
        if navigable:
            _, pname = _PLUGIN_META.get(plugin_id, ("", plugin_id))
            nav_btn = QPushButton("→")
            nav_btn.setObjectName("chipNavBtn")
            nav_btn.setFixedSize(22, 22)
            nav_btn.setToolTip(f"Open in {pname}")
            p, e = plugin_id, entity_id
            nav_btn.clicked.connect(
                lambda _=False, _p=p, _e=e: self.navigate_requested.emit(_p, _e)
            )
            row.addWidget(nav_btn)

        # ── Unlink button ─────────────────────────────────────────────────────
        if show_unlink:
            unlink_btn = QPushButton("✕")
            unlink_btn.setObjectName("chipUnlinkBtn")
            unlink_btn.setFixedSize(20, 20)
            unlink_btn.setToolTip("Remove link")
            e = entity_id
            unlink_btn.clicked.connect(
                lambda _=False, _e=e: self.unlink_requested.emit(_e)
            )
            row.addWidget(unlink_btn)

    def mousePressEvent(self, event):
        # Clicking anywhere on the chip (outside child buttons) navigates
        if event.button() == Qt.LeftButton and self._plugin_id:
            self.navigate_requested.emit(self._plugin_id, self._entity_id)
        super().mousePressEvent(event)


class RelatedItemsSection(QWidget):
    """
    A titled 'Related X' section for use inside detail panels.

    Shows a header label (icon + title), then a vertical stack of
    LinkedEntityChip rows — or a subtle 'nothing linked' placeholder.

    The navigate_requested signal bubbles up from all child chips.
    """

    navigate_requested = Signal(str, int)   # (plugin_id, entity_id)

    def __init__(self, *, title: str, icon: str = "", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 4)
        outer.setSpacing(4)

        # Section heading
        hdr = QLabel(f"{icon}  {title}" if icon else title)
        hdr.setObjectName("relatedSectionTitle")
        outer.addWidget(hdr)

        # Chips container
        self._chips_container = QWidget()
        self._chips_container.setStyleSheet("background: transparent;")
        self._chips_layout = QVBoxLayout(self._chips_container)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(3)
        outer.addWidget(self._chips_container)

        # Start empty
        self._set_placeholder("Nothing linked.")

    # ── Public API ────────────────────────────────────────────────────────────

    def set_chips(self, chips: list) -> None:
        """Replace contents with a list of LinkedEntityChip instances."""
        self._clear()
        if not chips:
            self._set_placeholder("Nothing linked.")
            return
        for chip in chips:
            chip.navigate_requested.connect(self.navigate_requested)
            self._chips_layout.addWidget(chip)

    def set_empty(self, text: str = "Nothing linked.") -> None:
        self._clear()
        self._set_placeholder(text)

    # ── Private ───────────────────────────────────────────────────────────────

    def _clear(self):
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _set_placeholder(self, text: str):
        lbl = QLabel(text)
        lbl.setObjectName("dimLabel")
        self._chips_layout.addWidget(lbl)


# ── Core render helper ─────────────────────────────────────────────────────────

def focal_pixmap(pix: QPixmap, w: int, h: int,
                 zoom: float = 1.0, fx: float = 0.5, fy: float = 0.5) -> QPixmap:
    """
    Return a w×h crop of pix.

    zoom=1.0 → minimum fill (KeepAspectRatioByExpanding).
    zoom=2.0 → 2× zoomed in (half the image visible).
    fx/fy    → focal point in 0–1 range (0=top/left, 1=bottom/right, 0.5=centre).
    """
    if pix.isNull():
        return pix
    zoom = max(1.0, zoom)

    # Step 1: fill the frame at zoom=1 (KeepAspectRatioByExpanding)
    base = pix.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

    # Step 2: apply extra zoom
    if zoom > 1.0:
        zw = max(w, int(base.width()  * zoom))
        zh = max(h, int(base.height() * zoom))
        base = base.scaled(zw, zh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    # Step 3: crop using focal point
    max_x = max(base.width()  - w, 0)
    max_y = max(base.height() - h, 0)
    x = int(max_x * max(0.0, min(1.0, fx)))
    y = int(max_y * max(0.0, min(1.0, fy)))
    return base.copy(x, y, w, h)


# ── Interactive preview widget ─────────────────────────────────────────────────

class _CropPreview(QWidget):
    """
    Interactive viewport. What you see IS the crop.

    Internally the widget operates in "thumb space" (thumb_w × thumb_h pixels)
    and renders at DISPLAY_SCALE× for comfortable interaction.
    Mouse drag pans the image; zoom is set externally via set_zoom().
    """

    DISPLAY_SCALE = 2   # render at 2× for easier dragging

    def __init__(self, pix: QPixmap, thumb_w: int, thumb_h: int, parent=None):
        super().__init__(parent)
        self._pix     = pix
        self._tw      = thumb_w
        self._th      = thumb_h
        self._zoom    = 1.0
        self._img_x   = 0.0   # image top-left in thumb-space; ≤ 0 when panned
        self._img_y   = 0.0
        self._drag_p  = None  # mouse press position (display coords)
        self._drag_ox = 0.0   # img_x at drag start
        self._drag_oy = 0.0

        ds = self.DISPLAY_SCALE
        self.setFixedSize(thumb_w * ds, thumb_h * ds)
        self.setCursor(Qt.OpenHandCursor)

        self._apply_zoom(1.0)   # centre at zoom 1

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_zoom(self, zoom: float):
        """Change zoom keeping the current centre point fixed."""
        # Centre of the current view in thumb-space
        cx = self._tw / 2.0 - self._img_x
        cy = self._th / 2.0 - self._img_y
        old_sw, old_sh = self._scaled_size()

        self._zoom = max(1.0, zoom)
        new_sw, new_sh = self._scaled_size()

        rx = new_sw / old_sw if old_sw else 1.0
        ry = new_sh / old_sh if old_sh else 1.0
        self._img_x = self._tw / 2.0 - cx * rx
        self._img_y = self._th / 2.0 - cy * ry
        self._clamp()
        self.update()

    def reset_center(self):
        self._apply_zoom(self._zoom)
        self.update()

    def focal_point(self) -> tuple[float, float, float]:
        """Return (zoom, fx, fy) ready to persist."""
        sw, sh    = self._scaled_size()
        travel_x  = max(sw - self._tw, 1e-6)
        travel_y  = max(sh - self._th, 1e-6)
        fx = max(0.0, min(1.0, -self._img_x / travel_x))
        fy = max(0.0, min(1.0, -self._img_y / travel_y))
        return self._zoom, fx, fy

    def restore_focal(self, zoom: float, fx: float, fy: float):
        """Restore a previously saved focal point."""
        self._zoom = max(1.0, zoom)
        sw, sh    = self._scaled_size()
        travel_x  = max(sw - self._tw, 0.0)
        travel_y  = max(sh - self._th, 0.0)
        self._img_x = -travel_x * max(0.0, min(1.0, fx))
        self._img_y = -travel_y * max(0.0, min(1.0, fy))
        self._clamp()
        self.update()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _apply_zoom(self, zoom: float):
        self._zoom = max(1.0, zoom)
        sw, sh = self._scaled_size()
        self._img_x = (self._tw - sw) / 2.0
        self._img_y = (self._th - sh) / 2.0
        self._clamp()

    def _scaled_size(self) -> tuple[float, float]:
        """Size of the image in thumb-space pixels at current zoom."""
        pw, ph = self._pix.width(), self._pix.height()
        if pw == 0 or ph == 0:
            return float(self._tw), float(self._th)
        base_scale = max(self._tw / pw, self._th / ph)   # fill at zoom=1
        s = base_scale * self._zoom
        return pw * s, ph * s

    def _clamp(self):
        sw, sh = self._scaled_size()
        # If image is wider/taller than thumb: keep it fully covering
        if sw >= self._tw:
            self._img_x = max(self._tw - sw, min(0.0, self._img_x))
        else:
            self._img_x = (self._tw - sw) / 2.0
        if sh >= self._th:
            self._img_y = max(self._th - sh, min(0.0, self._img_y))
        else:
            self._img_y = (self._th - sh) / 2.0

    # ── Qt events ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        ds = self.DISPLAY_SCALE
        sw, sh = self._scaled_size()

        scaled_pix = self._pix.scaled(
            max(1, int(sw * ds)), max(1, int(sh * ds)),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
        )

        p = QPainter(self)
        p.fillRect(0, 0, self.width(), self.height(), QColor("#111111"))
        p.drawPixmap(int(self._img_x * ds), int(self._img_y * ds), scaled_pix)

        # Border showing the exact crop boundary
        pen = QPen(QColor("#0078d4"), 2)
        p.setPen(pen)
        p.drawRect(1, 1, self.width() - 2, self.height() - 2)

        # Corner marks for extra clarity
        m = 18
        p.setPen(QPen(QColor("#0078d4"), 3))
        for cx, cy in [(1, 1), (self.width()-1, 1),
                       (1, self.height()-1), (self.width()-1, self.height()-1)]:
            dx = 1 if cx == 1 else -1
            dy = 1 if cy == 1 else -1
            p.drawLine(cx, cy, cx + dx * m, cy)
            p.drawLine(cx, cy, cx, cy + dy * m)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_p  = event.pos()
            self._drag_ox = self._img_x
            self._drag_oy = self._img_y
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_p is None:
            return
        ds  = self.DISPLAY_SCALE
        dx  = (event.pos().x() - self._drag_p.x()) / ds
        dy  = (event.pos().y() - self._drag_p.y()) / ds
        self._img_x = self._drag_ox + dx
        self._img_y = self._drag_oy + dy
        self._clamp()
        self.update()

    def mouseReleaseEvent(self, _event):
        self._drag_p = None
        self.setCursor(Qt.OpenHandCursor)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.08 if delta > 0 else 0.92
        new_zoom = max(1.0, min(8.0, self._zoom * factor))
        self.set_zoom(new_zoom)
        # Sync slider if parent dialog has one
        parent = self.parent()
        if parent and hasattr(parent, "_sync_slider"):
            parent._sync_slider(new_zoom)


# ── Dialog ─────────────────────────────────────────────────────────────────────

class PhotoCropDialog(QDialog):
    """
    Avatar-style photo crop/zoom dialog.

    Args:
        image_path: path to the source image
        thumb_w / thumb_h: target thumbnail dimensions (the "frame")
        zoom: initial zoom (1.0 = fill, higher = more zoomed in)
        fx / fy: initial focal point (0–1 each; 0.5 = centred)
    """

    def __init__(self, image_path: str, thumb_w: int, thumb_h: int,
                 zoom: float = 1.0, fx: float = 0.5, fy: float = 0.5,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adjust Photo")
        self.setModal(True)

        self._pix = QPixmap(image_path)
        self._tw  = thumb_w
        self._th  = thumb_h
        self._result: tuple[float, float, float] = (zoom, fx, fy)

        self._build_ui(zoom, fx, fy)

    def _build_ui(self, zoom: float, fx: float, fy: float):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        # ── Info ──────────────────────────────────────────────────────────────
        info = QLabel(
            "Drag the image to reposition  ·  "
            "Use the slider or scroll wheel to zoom in/out"
        )
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color: #808080; font-size: 12px;")
        lay.addWidget(info)

        # ── Preview ───────────────────────────────────────────────────────────
        self._preview = _CropPreview(self._pix, self._tw, self._th, parent=self)
        self._preview.restore_focal(zoom, fx, fy)
        lay.addWidget(self._preview, alignment=Qt.AlignCenter)

        # ── Zoom slider ───────────────────────────────────────────────────────
        zoom_row = QHBoxLayout(); zoom_row.setSpacing(10)
        zoom_icon = QLabel("🔍")
        zoom_row.addWidget(zoom_icon)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(100, 800)   # 1.0× to 8.0× (×100)
        self._slider.setValue(int(zoom * 100))
        self._slider.setTickInterval(100)
        self._slider.setTickPosition(QSlider.TicksBelow)
        self._slider.valueChanged.connect(self._on_slider_changed)
        zoom_row.addWidget(self._slider, stretch=1)

        self._zoom_lbl = QLabel(f"{zoom:.2f}×")
        self._zoom_lbl.setFixedWidth(52)
        self._zoom_lbl.setStyleSheet("font-weight: 600; color: #0078d4;")
        zoom_row.addWidget(self._zoom_lbl)
        lay.addLayout(zoom_row)

        tick_row = QHBoxLayout()
        tick_row.addWidget(QLabel("1×"), alignment=Qt.AlignLeft)
        tick_row.addWidget(QLabel("2×"), alignment=Qt.AlignCenter)
        tick_row.addWidget(QLabel("4×"), alignment=Qt.AlignCenter)
        tick_row.addWidget(QLabel("8×"), alignment=Qt.AlignRight)
        tick_row.setContentsMargins(28, 0, 60, 0)
        lay.addLayout(tick_row)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        reset_btn = QPushButton("Reset to Centre")
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        btn_row.addWidget(btns)
        lay.addLayout(btn_row)

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_slider_changed(self, value: int):
        zoom = value / 100.0
        self._zoom_lbl.setText(f"{zoom:.2f}×")
        self._preview.set_zoom(zoom)

    def _sync_slider(self, zoom: float):
        """Called by _CropPreview when scroll-wheel changes zoom."""
        self._slider.blockSignals(True)
        self._slider.setValue(int(zoom * 100))
        self._slider.blockSignals(False)
        self._zoom_lbl.setText(f"{zoom:.2f}×")

    def _reset(self):
        self._slider.setValue(100)
        self._preview.set_zoom(1.0)
        self._preview.reset_center()

    def _on_ok(self):
        self._result = self._preview.focal_point()
        self.accept()

    # ── Result ─────────────────────────────────────────────────────────────────

    def result(self) -> tuple[float, float, float]:
        """Returns (zoom, focal_x, focal_y) after accept()."""
        return self._result
