# ui/plugin_manager_dialog.py
"""
Plugin Manager Dialog — redesigned
────────────────────────────────────
Features:
  • Drag-and-drop reordering via a grip handle (⠿)
  • Inline label editing for ALL plugins (including core)
  • Enable / disable toggle for non-core plugins
  • Clean dark design system matching the rest of the app
"""
from __future__ import annotations

from PySide6.QtCore  import Qt, Signal, QPoint, QRect, QTimer
from PySide6.QtGui   import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QLineEdit, QCheckBox,
    QMessageBox, QSizePolicy,
)


# ── Design tokens (inline so the dialog is self-contained) ────────────────────

_C = {
    "bg_deep":    "#0c0c0c",
    "bg_base":    "#121212",
    "bg_card":    "#1a1a1a",
    "bg_raised":  "#1f1f1f",
    "bg_input":   "#252525",
    "bg_hover":   "#2a2a2a",
    "border":     "#2a2a2a",
    "border_hi":  "#3a3a3a",
    "text_hi":    "#f2f2f2",
    "text_mid":   "#c2c2c2",
    "text_lo":    "#848484",
    "text_dim":   "#484848",
    "accent":     "#0078d4",
    "accent_hi":  "#1a8ee8",
    "accent_lo":  "#0a2a4a",
    "accent_txt": "#60b0ff",
    "success":    "#3dba6e",
    "danger":     "#e05555",
    "warning":    "#e07800",
}


# ── Drag handle ───────────────────────────────────────────────────────────────

class _DragHandle(QLabel):
    """Six-dot grip — grabMouse during press so drag stays tracked."""

    drag_moved = Signal(QPoint)   # globalPos while dragging
    drag_ended = Signal(QPoint)   # globalPos on release

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("⠿")
        self.setFixedWidth(28)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(
            f"color:{_C['text_dim']}; font-size:16px; background:transparent; border:none;"
        )
        self._active = False

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._active = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.grabMouse()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._active:
            self.drag_moved.emit(e.globalPosition().toPoint())
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._active and e.button() == Qt.MouseButton.LeftButton:
            self._active = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.releaseMouse()
            self.drag_ended.emit(e.globalPosition().toPoint())
            e.accept()


# ── Toggle pill button ────────────────────────────────────────────────────────

class _TogglePill(QWidget):
    """A small ON / OFF pill toggle."""

    toggled = Signal(bool)

    def __init__(self, on: bool, parent=None):
        super().__init__(parent)
        self._on = on
        self.setFixedSize(56, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Toggle to enable or disable this plugin.")

    def is_on(self) -> bool:
        return self._on

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on = not self._on
            self.toggled.emit(self._on)
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Track
        track_color = QColor(_C["accent"] if self._on else _C["text_dim"])
        p.setBrush(track_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 4, 56, 16, 8, 8)

        # Thumb
        thumb_x = 34 if self._on else 4
        p.setBrush(QColor("#ffffff" if self._on else _C["text_lo"]))
        p.drawEllipse(thumb_x, 2, 20, 20)

        # Label
        p.setPen(QColor("#ffffff" if self._on else _C["text_lo"]))
        font = p.font()
        font.setPointSize(7)
        font.setBold(True)
        p.setFont(font)
        if self._on:
            p.drawText(QRect(4, 4, 26, 16), Qt.AlignmentFlag.AlignCenter, "ON")
        else:
            p.drawText(QRect(26, 4, 26, 16), Qt.AlignmentFlag.AlignCenter, "OFF")


# ── Plugin row ────────────────────────────────────────────────────────────────

class _PluginRow(QFrame):
    """
    One plugin row:
      [⠿ handle]  [● dot]  [label edit / sub-text]  [CORE badge | toggle]
    """

    def __init__(
        self,
        plugin_id:    str,
        display_name: str,
        current_label: str,
        description:  str,
        is_core:      bool,
        is_enabled:   bool,
        parent=None,
    ):
        super().__init__(parent)
        self.plugin_id = plugin_id
        self.is_core   = is_core
        self._enabled  = is_core or is_enabled

        self.setObjectName("PluginRow")
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._update_frame_style(False)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 12, 0)
        outer.setSpacing(0)

        # ── Drag handle ───────────────────────────────────────────────────────
        self._handle = _DragHandle(self)
        outer.addWidget(self._handle)

        # ── Status dot ────────────────────────────────────────────────────────
        self._dot = QFrame()
        self._dot.setFixedSize(10, 10)
        self._dot.setStyleSheet(self._dot_style())
        outer.addWidget(self._dot)
        outer.addSpacing(10)

        # ── Text column ───────────────────────────────────────────────────────
        txt_col = QVBoxLayout()
        txt_col.setContentsMargins(0, 10, 0, 10)
        txt_col.setSpacing(3)

        self._label_edit = QLineEdit(current_label or display_name)
        self._label_edit.setPlaceholderText(display_name)
        self._label_edit.setFixedHeight(28)
        self._label_edit.setStyleSheet(
            f"QLineEdit{{background:{_C['bg_input']}; color:{_C['text_hi']};"
            f"border:1px solid {_C['border']}; border-radius:5px;"
            f"font-size:13px; font-weight:600; padding:0 8px;}}"
            f"QLineEdit:focus{{border-color:{_C['accent']}; background:{_C['bg_raised']};}}"
        )
        txt_col.addWidget(self._label_edit)

        sub_text = f"{display_name}  ·  {plugin_id}"
        sub_lbl = QLabel(sub_text)
        sub_lbl.setToolTip(description or "No description available.")
        sub_lbl.setStyleSheet(
            f"color:{_C['text_dim']}; font-size:10px; background:transparent; border:none;"
        )
        txt_col.addWidget(sub_lbl)
        outer.addLayout(txt_col, stretch=1)

        outer.addSpacing(10)

        # ── Right side: badge or toggle ───────────────────────────────────────
        if is_core:
            badge = QLabel("CORE")
            badge.setFixedHeight(22)
            badge.setStyleSheet(
                f"background:{_C['accent_lo']}; color:{_C['accent_txt']};"
                f"border:1px solid {_C['accent']}44; border-radius:4px;"
                f"font-size:9px; font-weight:700; padding:0 8px;"
            )
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            outer.addWidget(badge)
        else:
            self._toggle = _TogglePill(self._enabled)
            self._toggle.toggled.connect(self._on_toggle)
            outer.addWidget(self._toggle)

    # ── Styling helpers ───────────────────────────────────────────────────────

    def _dot_style(self) -> str:
        color = _C["success"] if self._enabled else _C["text_dim"]
        return f"background:{color}; border-radius:5px; border:none;"

    def _update_frame_style(self, dragging: bool):
        if dragging:
            self.setStyleSheet(
                f"QFrame#PluginRow{{background:{_C['bg_hover']};"
                f"border:1px solid {_C['accent']}; border-radius:8px;}}"
            )
        else:
            self.setStyleSheet(
                f"QFrame#PluginRow{{background:{_C['bg_card']};"
                f"border:1px solid {_C['border']}; border-radius:8px;}}"
                f"QFrame#PluginRow:hover{{border-color:{_C['border_hi']};}}"
            )

    def set_dragging(self, dragging: bool):
        self._update_frame_style(dragging)

    # ── Public accessors ──────────────────────────────────────────────────────

    @property
    def label(self) -> str:
        return self._label_edit.text().strip()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _on_toggle(self, on: bool):
        self._enabled = on
        self._dot.setStyleSheet(self._dot_style())


# ── Drop indicator line ───────────────────────────────────────────────────────

class _DropLine(QFrame):
    """2-px accent line that shows where a dragged row will land."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(2)
        self.setStyleSheet(
            f"background:{_C['accent']}; border-radius:1px;"
        )
        self.hide()


# ── Draggable list container ──────────────────────────────────────────────────

class _DragList(QWidget):
    """
    Vertical list of _PluginRow widgets with live drag-and-drop reordering.

    Each row's _DragHandle emits positions via Signal; this container
    tracks drag state and updates the layout when the drag ends.
    """

    _SCROLL_ZONE = 60    # px from edge where auto-scroll kicks in
    _SCROLL_MAX  = 18   # max px per timer tick

    def __init__(self, scroll_area=None, parent=None):
        super().__init__(parent)
        self.setObjectName("DragList")
        self.setStyleSheet("background:transparent;")

        self._rows: list[_PluginRow] = []
        self._scroll_area = scroll_area

        self._vlay = QVBoxLayout(self)
        self._vlay.setContentsMargins(12, 8, 12, 8)
        self._vlay.setSpacing(4)
        self._vlay.addStretch()

        # Drag state
        self._dragging:         _PluginRow | None = None
        self._orig_idx:         int    = -1
        self._drop_idx:         int    = -1
        self._last_global_pos:  QPoint = QPoint()

        # Auto-scroll timer — fires at ~60 fps while dragging near an edge
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(16)
        self._scroll_timer.timeout.connect(self._do_auto_scroll)
        self._scroll_speed: int = 0   # px/tick; negative = up

        # Drop indicator (overlay — child of this widget, drawn on top)
        self._indicator = _DropLine(self)
        self._indicator.raise_()

    # ── Row management ────────────────────────────────────────────────────────

    def add_row(self, row: _PluginRow):
        self._rows.append(row)
        # Insert before the trailing stretch
        self._vlay.insertWidget(self._vlay.count() - 1, row)
        row._handle.drag_moved.connect(lambda pos, r=row: self._on_drag_move(r, pos))
        row._handle.drag_ended.connect(lambda pos, r=row: self._on_drag_end(r, pos))

    def rows(self) -> list[_PluginRow]:
        return list(self._rows)

    # ── Drag logic ────────────────────────────────────────────────────────────

    def _on_drag_move(self, row: _PluginRow, global_pos: QPoint):
        if self._dragging is None:
            # Start of drag
            self._dragging = row
            self._orig_idx = self._rows.index(row)
            row.set_dragging(True)

        self._last_global_pos = global_pos

        local_y = self.mapFromGlobal(global_pos).y()
        self._drop_idx = self._calc_drop_idx(local_y)
        self._show_indicator(self._drop_idx)

        # ── Auto-scroll when near the viewport edges ──────────────────────────
        self._update_scroll_speed(global_pos)

    def _on_drag_end(self, row: _PluginRow, _pos: QPoint):
        if self._dragging is None:
            return

        # Stop auto-scroll
        self._scroll_timer.stop()
        self._scroll_speed = 0

        row.set_dragging(False)
        self._indicator.hide()

        orig = self._orig_idx
        dest = self._drop_idx

        # Adjust dest: inserting after the row shifts index by 1
        if dest > orig:
            dest -= 1

        if dest != orig and 0 <= dest < len(self._rows):
            # Remove from layout and list
            self._vlay.removeWidget(row)
            self._rows.pop(orig)
            # Re-insert at new position
            self._rows.insert(dest, row)
            self._vlay.insertWidget(dest, row)   # stretch is always last

        self._dragging  = None
        self._orig_idx  = -1
        self._drop_idx  = -1

    def _update_scroll_speed(self, global_pos: QPoint):
        """Start / adjust / stop the auto-scroll timer based on cursor proximity to edges."""
        if not self._scroll_area:
            return
        vp     = self._scroll_area.viewport()
        local  = vp.mapFromGlobal(global_pos)
        y      = local.y()
        height = vp.height()
        zone   = self._SCROLL_ZONE

        if y < zone:
            # Near top — scroll up; faster the closer to the edge
            ratio = max(0.0, (zone - y) / zone)
            self._scroll_speed = -max(2, int(ratio * self._SCROLL_MAX))
            self._scroll_timer.start()
        elif y > height - zone:
            # Near bottom — scroll down
            ratio = max(0.0, (y - (height - zone)) / zone)
            self._scroll_speed = max(2, int(ratio * self._SCROLL_MAX))
            self._scroll_timer.start()
        else:
            self._scroll_speed = 0
            self._scroll_timer.stop()

    def _do_auto_scroll(self):
        """Called by the timer — scroll and refresh the drop indicator."""
        if not self._scroll_area or self._scroll_speed == 0:
            return
        sb = self._scroll_area.verticalScrollBar()
        sb.setValue(sb.value() + self._scroll_speed)

        # Recalculate drop position after the viewport moved
        if not self._last_global_pos.isNull() and self._dragging:
            local_y = self.mapFromGlobal(self._last_global_pos).y()
            self._drop_idx = self._calc_drop_idx(local_y)
            self._show_indicator(self._drop_idx)

    def _calc_drop_idx(self, local_y: int) -> int:
        """Return the index (0..len) at which to insert the dragged row."""
        for i, r in enumerate(self._rows):
            mid = r.pos().y() + r.height() // 2
            if local_y < mid:
                return i
        return len(self._rows)

    def _show_indicator(self, drop_idx: int):
        margin = self._vlay.contentsMargins().left()
        w = self.width() - margin * 2

        if drop_idx < len(self._rows):
            ref = self._rows[drop_idx]
            y   = ref.pos().y() - 3
        else:
            ref = self._rows[-1] if self._rows else None
            y   = (ref.pos().y() + ref.height() + 1) if ref else 8

        self._indicator.setGeometry(margin, y, w, 2)
        self._indicator.show()
        self._indicator.raise_()

    # ── Arrow-key fallback (for keyboard users) ───────────────────────────────

    def move_row_up(self, row: _PluginRow):
        idx = self._rows.index(row)
        if idx <= 0:
            return
        self._rows.pop(idx)
        self._vlay.removeWidget(row)
        self._rows.insert(idx - 1, row)
        self._vlay.insertWidget(idx - 1, row)

    def move_row_down(self, row: _PluginRow):
        idx = self._rows.index(row)
        if idx >= len(self._rows) - 1:
            return
        self._rows.pop(idx)
        self._vlay.removeWidget(row)
        self._rows.insert(idx + 1, row)
        self._vlay.insertWidget(idx + 1, row)


# ── Main dialog ───────────────────────────────────────────────────────────────

class PluginManagerDialog(QDialog):
    """
    Plugin Manager Dialog.

    Usage:
        dialog = PluginManagerDialog(context, plugins, parent)
        if dialog.exec():
            order, labels, disabled = dialog.get_result()
    """

    def __init__(self, context, plugins: list, parent=None):
        super().__init__(parent)
        self._context  = context
        self._plugins  = plugins
        self._result_order:    list[str]      = []
        self._result_labels:   dict[str, str] = {}
        self._result_disabled: list[str]      = []

        self.setWindowTitle("Manage Plugins")
        self.setMinimumWidth(580)
        self.setMinimumHeight(520)
        self.setModal(True)
        self.setStyleSheet(f"QDialog{{background:{_C['bg_base']}; color:{_C['text_hi']};}}")

        self._build_ui()
        self._populate()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(60)
        hdr.setStyleSheet(
            f"background:{_C['bg_card']}; border-bottom:1px solid {_C['border']};"
        )
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(20, 0, 20, 0)
        hdr_row.setSpacing(10)

        icon_lbl = QLabel("⚙")
        icon_lbl.setStyleSheet(
            f"color:{_C['accent']}; font-size:18px; background:transparent; border:none;"
        )
        hdr_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title_lbl = QLabel("Manage Plugins")
        title_lbl.setStyleSheet(
            f"color:{_C['text_hi']}; font-size:14px; font-weight:700;"
            f"background:transparent; border:none;"
        )
        sub_lbl = QLabel(
            "Drag  ⠿  to reorder  ·  Edit label to rename  ·  Toggle to enable / disable"
        )
        sub_lbl.setStyleSheet(
            f"color:{_C['text_dim']}; font-size:10px; background:transparent; border:none;"
        )
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        hdr_row.addLayout(title_col, stretch=1)

        root.addWidget(hdr)

        # ── Scroll area ───────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{_C['bg_base']}; border:none;}}"
            f"QScrollBar:vertical{{background:{_C['bg_base']}; width:5px; margin:0;}}"
            f"QScrollBar::handle:vertical{{background:{_C['border_hi']}; border-radius:2px; min-height:20px;}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{{height:0;}}"
        )

        self._list = _DragList(scroll_area=scroll)
        scroll.setWidget(self._list)
        root.addWidget(scroll, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(60)
        footer.setStyleSheet(
            f"background:{_C['bg_card']}; border-top:1px solid {_C['border']};"
        )
        foot_row = QHBoxLayout(footer)
        foot_row.setContentsMargins(20, 0, 20, 0)
        foot_row.setSpacing(8)

        reset_btn = QPushButton("↺  Reset to Defaults")
        reset_btn.setFixedHeight(34)
        reset_btn.setStyleSheet(self._secondary_btn_ss())
        reset_btn.clicked.connect(self._on_reset)
        foot_row.addWidget(reset_btn)

        foot_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setStyleSheet(self._secondary_btn_ss())
        cancel_btn.clicked.connect(self.reject)
        foot_row.addWidget(cancel_btn)

        apply_btn = QPushButton("✓  Apply")
        apply_btn.setFixedHeight(34)
        apply_btn.setDefault(True)
        apply_btn.setStyleSheet(self._primary_btn_ss())
        apply_btn.clicked.connect(self._on_apply)
        foot_row.addWidget(apply_btn)

        root.addWidget(footer)

    # ── Populate ──────────────────────────────────────────────────────────────

    def _populate(self):
        settings = self._context.services.get("settings") if self._context else None
        pm       = self._context.services.get("plugin_manager") if self._context else None

        saved_labels:   dict = {}
        saved_disabled: list = []
        saved_order:    list = []

        if settings:
            try:
                saved_labels   = settings.get("plugin_layout.labels",   {}) or {}
                saved_disabled = settings.get("plugin_layout.disabled", []) or []
                saved_order    = settings.get("plugin_layout.order",    []) or []
            except Exception:
                pass

        loaded_map: dict[str, object] = {
            getattr(p, "plugin_id", ""): p for p in self._plugins
        }
        all_manifests: dict = {}
        if pm and hasattr(pm, "all_manifests"):
            all_manifests = pm.all_manifests

        all_ids = set(loaded_map.keys()) | set(all_manifests.keys())
        all_ids.discard("")

        ordered = [pid for pid in saved_order if pid in all_ids]
        ordered += sorted(pid for pid in all_ids if pid not in ordered)

        for pid in ordered:
            plugin        = loaded_map.get(pid)
            manifest_data = all_manifests.get(pid, (None, {}))[1] if pid in all_manifests else {}

            display_name  = (
                getattr(plugin, "display_name", None)
                or manifest_data.get("name", pid)
            )
            description = (
                getattr(plugin, "description", None)
                or manifest_data.get("description", "")
            )
            current_label = saved_labels.get(pid, "")
            is_core       = manifest_data.get("category") == "core"
            is_enabled    = pid not in saved_disabled

            row = _PluginRow(
                plugin_id     = pid,
                display_name  = display_name,
                current_label = current_label,
                description   = description,
                is_core       = is_core,
                is_enabled    = is_enabled,
            )
            self._list.add_row(row)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_apply(self):
        rows = self._list.rows()
        self._result_order = [r.plugin_id for r in rows]
        self._result_labels = {
            r.plugin_id: r.label
            for r in rows
            if r.label and r.label != self._default_name(r.plugin_id)
        }
        self._result_disabled = [
            r.plugin_id for r in rows
            if not r.enabled and not r.is_core
        ]
        self.accept()

    def _on_reset(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Reset to Defaults")
        msg.setText(
            "This will reset all tab labels to their defaults and "
            "restore the original plugin order.\n\nContinue?"
        )
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setStyleSheet(
            f"QMessageBox{{background:{_C['bg_base']}; color:{_C['text_hi']};}}"
        )
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return
        for row in self._list.rows():
            row._label_edit.setText("")
        settings = self._context.services.get("settings") if self._context else None
        if settings:
            try:
                settings.set("plugin_layout.labels", {})
                settings.set("plugin_layout.order",  [])
            except Exception:
                pass

    # ── Public result ─────────────────────────────────────────────────────────

    def get_result(self) -> tuple[list[str], dict[str, str], list[str]]:
        return self._result_order, self._result_labels, self._result_disabled

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _default_name(self, plugin_id: str) -> str:
        for p in self._plugins:
            if getattr(p, "plugin_id", "") == plugin_id:
                return getattr(p, "display_name", plugin_id)
        pm = self._context.services.get("plugin_manager") if self._context else None
        if pm and hasattr(pm, "all_manifests") and plugin_id in pm.all_manifests:
            _, data = pm.all_manifests[plugin_id]
            return data.get("name", plugin_id)
        return plugin_id

    def _primary_btn_ss(self) -> str:
        return (
            f"QPushButton{{background:{_C['accent']}; color:#fff; border:none;"
            f"border-radius:6px; font-size:12px; font-weight:600; padding:0 20px;}}"
            f"QPushButton:hover{{background:{_C['accent_hi']};}}"
            f"QPushButton:pressed{{background:{_C['accent']};}}"
        )

    def _secondary_btn_ss(self) -> str:
        return (
            f"QPushButton{{background:{_C['bg_raised']}; color:{_C['text_mid']};"
            f"border:1px solid {_C['border']}; border-radius:6px;"
            f"font-size:12px; padding:0 16px;}}"
            f"QPushButton:hover{{border-color:{_C['border_hi']}; color:{_C['text_hi']};}}"
        )
