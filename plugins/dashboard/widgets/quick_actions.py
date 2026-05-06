"""Quick actions panel — grid or sidebar mode."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QPushButton, QSizePolicy,
)

# Fallback colors used only when the theme manager is unavailable
_COLOR_FALLBACK: dict[str, str] = {
    "accent":  "#0078d4",
    "success": "#3dba6e",
    "warning": "#e07800",
    "danger":  "#e05555",
}


class QuickActionsWidget(QWidget):
    """
    Quick-action buttons widget.

    modes
    -----
    columns=2  (default) — 2-column grid, 40 px tall buttons (Alerts tab)
    columns=1             — single-column sidebar, 32 px compact buttons (Overview sidebar)
    """

    action_requested = Signal(str, dict)   # (event_name, payload)

    def __init__(self, context, parent=None, columns: int = 2):
        super().__init__(parent)
        self._ctx     = context
        self._columns = columns

        if columns == 1:
            # Sidebar: vertical stack
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(4)
            self._grid = None
        else:
            # Grid mode
            self._grid = QGridLayout(self)
            self._grid.setContentsMargins(0, 0, 0, 0)
            self._grid.setSpacing(8)
            self._layout = None

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self, actions: list) -> None:
        """Rebuild from list of QuickAction DTOs."""
        if self._columns == 1:
            self._rebuild_sidebar(actions)
        else:
            self._rebuild_grid(actions)

    # ── private ───────────────────────────────────────────────────────────────

    def _rebuild_grid(self, actions: list) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, action in enumerate(actions):
            btn = self._make_button(action, compact=False)
            row, col = divmod(i, 2)
            self._grid.addWidget(btn, row, col)

        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)

    def _rebuild_sidebar(self, actions: list) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for action in actions:
            self._layout.addWidget(self._make_button(action, compact=True))

        self._layout.addStretch()

    def _make_button(self, action, compact: bool = False) -> QPushButton:
        tm        = self._ctx.services.get("theme_manager") if self._ctx else None
        color     = _resolve_color(action.color, tm)
        bg_raised = tm.token("bg_raised") if tm else "#212121"
        border    = tm.token("border")    if tm else "#363636"
        radius_sm = f"{tm.token('radius_sm') if tm else 4}px"

        label = f"{action.icon}  {action.label}" if action.icon else action.label
        btn   = QPushButton(label)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if compact:
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-radius: {radius_sm};
                    color: {color};
                    font-weight: 600;
                    text-align: left;
                    padding: 0 10px;
                }}
                QPushButton:hover {{
                    background: {color}18;
                }}
                QPushButton:pressed {{
                    background: {color}30;
                }}
            """)
        else:
            btn.setFixedHeight(40)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg_raised};
                    border: 1px solid {border};
                    border-radius: {radius_sm};
                    color: {color};
                    font-weight: 600;
                    text-align: left;
                    padding: 0 12px;
                }}
                QPushButton:hover {{
                    background: {color}1a;
                    border-color: {color};
                }}
                QPushButton:pressed {{
                    background: {color}33;
                }}
            """)

        event   = action.event
        payload = dict(action.payload)
        btn.clicked.connect(lambda _=False, e=event, p=payload: self.action_requested.emit(e, p))
        return btn


# ── helpers ────────────────────────────────────────────────────────────────────

def _resolve_color(color_key: str, tm) -> str:
    """Prefer a live theme token, fall back to the static fallback map."""
    if tm:
        try:
            val = tm.token(color_key)
            if val:
                return val
        except Exception:
            pass
    return _COLOR_FALLBACK.get(color_key, _COLOR_FALLBACK["accent"])
