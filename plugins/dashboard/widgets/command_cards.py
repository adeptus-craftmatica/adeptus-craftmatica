"""Hero metric command cards — executive-style KPI overview."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy,
)

# Fallback colors used only when the theme manager is unavailable
_COLOR_FALLBACK = {
    "accent":  "#0078d4",
    "success": "#3dba6e",
    "warning": "#e07800",
    "danger":  "#e05555",
    "info":    "#0078d4",
}

# Most urgent cards shown first
_SORT_PRIORITY = {"danger": 0, "warning": 1, "success": 2, "accent": 3, "info": 4}

# Never show more than this many cards regardless of how many plugins register
_MAX_CARDS = 7


class CommandCardsWidget(QWidget):
    """
    A row of expanding hero-metric cards.

    Cards use QSizePolicy.Expanding so they fill whatever width the parent
    gives them (up to _CARD_MAX_W each).  minimumSizeHint() returns width=0
    so the window minimum is NEVER driven by card count.
    """

    _CARD_MAX_W = 185   # each card caps at this width
    _CARD_H     = 105   # fixed height

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

        # Fixed widget height so parent doesn't need to guess
        self.setFixedHeight(self._CARD_H + 8)   # card + top/bottom breathing room

    # ── Qt overrides ──────────────────────────────────────────────────────────

    def minimumSizeHint(self) -> QSize:
        # Return zero width — never force the window wider than the screen.
        return QSize(0, self._CARD_H + 8)

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self, stats: list) -> None:
        """Rebuild cards — most urgent first, capped at _MAX_CARDS."""
        # Remove all existing cards
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Sort by urgency and cap
        sorted_stats = sorted(stats, key=lambda s: _SORT_PRIORITY.get(s.color, 4))
        for stat in sorted_stats[:_MAX_CARDS]:
            self._layout.addWidget(self._make_card(stat))

    # ── private ───────────────────────────────────────────────────────────────

    def _make_card(self, stat) -> QFrame:
        tm    = self._ctx.services.get("theme_manager") if self._ctx else None
        # Resolve status color from live theme tokens with static fallback
        color = (tm.token(stat.color) if tm and tm.token(stat.color)
                 else _COLOR_FALLBACK.get(stat.color, _COLOR_FALLBACK["accent"]))
        border = tm.token("border") if tm else "#363636"

        bg = tm.token("card_bg") if tm else "#1e1e1e"

        frame = QFrame()
        frame.setObjectName("heroCard")
        # Expanding but capped — fills the row, never overflows it
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        frame.setMinimumWidth(0)
        frame.setMaximumWidth(self._CARD_MAX_W)
        frame.setFixedHeight(self._CARD_H)
        frame.setStyleSheet(f"""
            QFrame#heroCard {{
                background: {bg};
                border: 1px solid {border};
                border-top: 3px solid {color};
                border-radius: 8px;
            }}
        """)

        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(14, 10, 14, 12)
        vlay.setSpacing(0)

        tm_lo  = tm.token("text_lo")  if tm else "#909090"
        tm_mid = tm.token("text_mid") if tm else "#d8d8d8"

        # Icon + label row
        top = QHBoxLayout()
        top.setSpacing(5)
        top.setContentsMargins(0, 0, 0, 0)

        if stat.icon:
            icon_lbl = QLabel(stat.icon)
            icon_lbl.setStyleSheet(f"font-size: 13px; color: {color}; background: transparent;")
            top.addWidget(icon_lbl)

        lbl = QLabel(stat.label.upper())
        lbl.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {tm_lo}; "
            "letter-spacing: 0.8px; background: transparent;"
        )
        lbl.setTextFormat(Qt.PlainText)
        top.addWidget(lbl)
        top.addStretch()
        vlay.addLayout(top)

        vlay.addSpacing(2)

        # Big number — display size, uses semantic color
        val = QLabel(stat.value)
        val.setStyleSheet(
            f"font-size: 34px; font-weight: 700; color: {color}; "
            "background: transparent; line-height: 1;"
        )
        val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        vlay.addWidget(val)

        vlay.addStretch()

        # Subtitle
        if stat.subtitle:
            sub = QLabel(stat.subtitle)
            sub.setStyleSheet(f"font-size: 10px; color: {tm_mid}; background: transparent;")
            sub.setTextFormat(Qt.PlainText)
            sub.setWordWrap(True)
            vlay.addWidget(sub)

        return frame
