"""Alerts mini panel — compact inline alerts for the Overview sidebar (220 px wide)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy,
)

_SEV_COLORS: dict[str, str] = {
    "critical": "danger",
    "warning":  "warning",
}

_SEV_ICONS: dict[str, str] = {
    "critical": "🔴",
    "warning":  "🟡",
}

# Static fallbacks used only when ThemeManager is unavailable
_TOKEN_FALLBACK: dict[str, str] = {
    "card_bg":  "#1a1a1a",
    "border":   "#2a2a2a",
    "text_hi":  "#e8e8e8",
    "text_lo":  "#808080",
    "accent":   "#0078d4",
    "danger":   "#c62828",
    "warning":  "#e07820",
}


def _tok(tm, name: str) -> str:
    """Resolve a theme token with a static fallback."""
    if tm:
        try:
            val = tm.token(name)
            if val:
                return val
        except Exception:
            pass
    return _TOKEN_FALLBACK.get(name, "#808080")


class AlertsMiniWidget(QWidget):
    """Compact inline alerts panel — top-3 critical/warning rows + 'View all' link."""

    navigate_alerts = Signal()

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Alert rows body
        self._list_layout = QVBoxLayout()
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        outer.addLayout(self._list_layout)

        # Footer link
        self._view_all_link = QLabel("View all →")
        self._view_all_link.setCursor(Qt.PointingHandCursor)
        self._view_all_link.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._view_all_link.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Attach click handler by overriding mousePressEvent at instance level
        widget_ref = self

        def _on_click(event, _w=widget_ref):
            _w.navigate_alerts.emit()

        self._view_all_link.mousePressEvent = _on_click

        outer.addWidget(self._view_all_link)

        # Initial empty state render
        self.refresh([])

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self, notes: list) -> None:
        """Rebuild from a list of Notification DTOs.

        Shows up to 3 rows filtered to severity critical/warning.
        The 'View all' count reflects the total len(notes) across all severities.
        """
        # Clear existing rows
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tm = self._ctx.services.get("theme_manager") if self._ctx else None
        lo     = _tok(tm, "text_lo")
        accent = _tok(tm, "accent")

        total = len(notes)
        filtered = [n for n in notes if getattr(n, "severity", None) in ("critical", "warning")]
        visible  = filtered[:3]

        if not visible:
            # Empty state: no rows, muted link
            self._view_all_link.setStyleSheet(f"color: {lo}; font-size: 10px; background: transparent;")
            self._view_all_link.setText("View all →")
        else:
            for note in visible:
                self._list_layout.addWidget(self._make_row(note))
            self._view_all_link.setStyleSheet(
                f"color: {accent}; font-size: 10px; text-decoration: underline; background: transparent;"
            )
            self._view_all_link.setText(f"View all {total} →")

    # ── private ───────────────────────────────────────────────────────────────

    def _make_row(self, note) -> QFrame:
        tm = self._ctx.services.get("theme_manager") if self._ctx else None
        bg     = _tok(tm, "card_bg")
        border = _tok(tm, "border")
        hi     = _tok(tm, "text_hi")

        tok_name  = _SEV_COLORS.get(note.severity, "accent")
        sev_color = _tok(tm, tok_name)
        sev_icon  = _SEV_ICONS.get(note.severity, "🔵")

        frame = QFrame()
        frame.setObjectName("alertMiniRow")
        frame.setFixedHeight(32)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        frame.setStyleSheet(f"""
            QFrame#alertMiniRow {{
                background: {bg};
                border: 1px solid {border};
                border-left: 4px solid {sev_color};
                border-radius: 4px;
            }}
        """)

        row = QHBoxLayout(frame)
        row.setContentsMargins(6, 0, 8, 0)
        row.setSpacing(5)

        icon_lbl = QLabel(sev_icon)
        icon_lbl.setStyleSheet("font-size: 10px; background: transparent;")
        icon_lbl.setFixedWidth(14)
        row.addWidget(icon_lbl)

        title_lbl = QLabel(note.title)
        title_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {hi}; background: transparent;"
        )
        title_lbl.setTextFormat(Qt.PlainText)
        title_lbl.setWordWrap(False)
        # Elide long titles to fit the 220 px sidebar
        title_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(title_lbl, stretch=1)

        return frame
