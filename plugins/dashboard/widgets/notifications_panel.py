"""Notifications panel — scrollable list with severity-coloured left border."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)

# Severity → theme token name (resolved via ThemeManager at render time)
_SEV_TOKEN: dict[str, str] = {
    "critical": "danger",
    "warning":  "warning",
    "success":  "success",
    "info":     "accent",
}

# Static fallbacks used only when ThemeManager is unavailable
_SEV_FALLBACK: dict[str, str] = {
    "danger":  "#e05555",
    "warning": "#e07800",
    "success": "#3dba6e",
    "accent":  "#0078d4",
}

_SEV_ICONS: dict[str, str] = {
    "critical": "🔴",
    "warning":  "🟡",
    "success":  "🟢",
    "info":     "🔵",
}


class NotificationsPanelWidget(QWidget):
    """Scrollable notification list with coloured severity border."""

    action_requested = Signal(str, dict)   # (event_name, payload)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self, notes: list) -> None:
        """Rebuild list from list of Notification DTOs (already sorted by severity)."""
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not notes:
            tm = self._ctx.services.get("theme_manager") if self._ctx else None
            lo = tm.token("text_lo") if tm else "#808080"
            empty = QLabel("All clear — no alerts")
            empty.setStyleSheet(f"color: {lo}; font-size: 12px; padding: 12px;")
            empty.setAlignment(Qt.AlignCenter)
            self._list_layout.insertWidget(0, empty)
            return

        for note in notes:
            widget = self._make_note_widget(note)
            self._list_layout.insertWidget(self._list_layout.count() - 1, widget)

    # ── private ───────────────────────────────────────────────────────────────

    def _make_note_widget(self, note) -> QFrame:
        tm = self._ctx.services.get("theme_manager") if self._ctx else None
        bg      = tm.token("card_bg")    if tm else "#1e1e1e"
        border  = tm.token("border")     if tm else "#363636"
        hi      = tm.token("text_hi")    if tm else "#f0f0f0"
        mid     = tm.token("text_mid")   if tm else "#d8d8d8"
        radius  = f"{tm.token('radius_base') if tm else 6}px"

        # Resolve severity color from live theme tokens
        tok_name  = _SEV_TOKEN.get(note.severity, "accent")
        sev_color = (tm.token(tok_name) if tm else None) or _SEV_FALLBACK.get(tok_name, "#0078d4")
        sev_icon  = _SEV_ICONS.get(note.severity, "🔵")

        frame = QFrame()
        frame.setObjectName("noteFrame")
        frame.setStyleSheet(f"""
            QFrame#noteFrame {{
                background: {bg};
                border: 1px solid {border};
                border-left: 3px solid {sev_color};
                border-radius: {radius};
            }}
        """)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(12, 8, 12, 8)
        vlay.setSpacing(4)

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        icon_lbl = QLabel(sev_icon)
        icon_lbl.setStyleSheet("font-size: 12px; background: transparent;")
        icon_lbl.setFixedWidth(16)
        title_row.addWidget(icon_lbl)

        title_lbl = QLabel(note.title)
        title_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {hi}; background: transparent;")
        title_lbl.setTextFormat(Qt.PlainText)
        title_lbl.setWordWrap(True)
        title_row.addWidget(title_lbl, stretch=1)
        vlay.addLayout(title_row)

        # Body
        if note.body:
            body_lbl = QLabel(note.body)
            body_lbl.setStyleSheet(f"font-size: 11px; color: {mid}; background: transparent;")
            body_lbl.setTextFormat(Qt.PlainText)
            body_lbl.setWordWrap(True)
            vlay.addWidget(body_lbl)

        # Action button
        if note.action_event and note.action_label:
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            btn = QPushButton(note.action_label)
            btn.setFixedHeight(22)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid {sev_color};
                    border-radius: 3px;
                    color: {sev_color};
                    font-size: 10px;
                    font-weight: 600;
                    padding: 0 8px;
                }}
                QPushButton:hover {{ background: {sev_color}22; }}
                QPushButton:pressed {{ background: {sev_color}44; }}
            """)
            event   = note.action_event
            payload = dict(note.action_payload)
            btn.clicked.connect(lambda _=False, e=event, p=payload: self.action_requested.emit(e, p))
            btn_row.addWidget(btn)
            vlay.addLayout(btn_row)

        return frame
