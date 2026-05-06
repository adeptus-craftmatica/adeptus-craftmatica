"""Dashboard / Profile settings page — registered into the core Settings dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QSizePolicy,
)


class ProfileSettingsPage(QWidget):
    """'Profile' page shown in the main Settings dialog."""

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(20)

        title = QLabel("Profile")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        root.addWidget(title)

        root.addWidget(self._hline())

        # ── Display name field ─────────────────────────────────────────────────
        name_group = QFrame()
        name_lay = QVBoxLayout(name_group)
        name_lay.setContentsMargins(0, 0, 0, 0)
        name_lay.setSpacing(6)

        lbl = QLabel("Display Name")
        lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        name_lay.addWidget(lbl)

        hint = QLabel("Used in the dashboard greeting — e.g. \"Good morning, Sarah!\"")
        hint.setStyleSheet("font-size: 11px; opacity: 0.6;")
        name_lay.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Sarah, Commander, The Painter…")
        self._name_input.setFixedHeight(34)
        settings = self._ctx.services.get("settings") if self._ctx else None
        if settings:
            self._name_input.setText(settings.get("user.display_name", ""))
        row.addWidget(self._name_input, stretch=1)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedHeight(34)
        self._save_btn.setFixedWidth(80)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.clicked.connect(self._save)
        row.addWidget(self._save_btn)

        name_lay.addLayout(row)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size: 11px; color: #2e7d32;")
        name_lay.addWidget(self._status_lbl)

        root.addWidget(name_group)
        root.addStretch()

    # ── private ───────────────────────────────────────────────────────────────

    def _save(self):
        settings = self._ctx.services.get("settings") if self._ctx else None
        if not settings:
            return
        name = self._name_input.text().strip()
        settings.set("user.display_name", name)

        # Notify the dashboard to update its greeting immediately
        bus = getattr(self._ctx, "event_bus", None)
        if bus:
            try:
                bus.emit("user_profile_updated", {"display_name": name})
            except Exception:
                pass

        display = name or "Hobbyist"
        self._status_lbl.setText(f"✓ Saved — dashboard will greet you as \"{display}\"")

    def _hline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        return line
