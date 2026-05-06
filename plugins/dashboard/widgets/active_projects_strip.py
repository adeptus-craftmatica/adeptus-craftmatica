"""Active projects strip — compact horizontal row of up to 3 project cards."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QProgressBar, QSizePolicy,
)

_STATUS_COLORS: dict[str, str] = {
    "success": "#2e7d32",
    "warning": "#e07820",
    "danger":  "#c62828",
}

# Static fallbacks used only when ThemeManager is unavailable
_TOKEN_FALLBACK: dict[str, str] = {
    "card_bg":  "#1a1a1a",
    "border":   "#2a2a2a",
    "text_hi":  "#e8e8e8",
    "text_lo":  "#808080",
    "accent":   "#0078d4",
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


class ActiveProjectsStripWidget(QWidget):
    """Horizontal strip of up to 3 active project cards."""

    action_requested = Signal(str, dict)   # ("dashboard_navigate", {"plugin_id": "project_tracker"})

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        self._outer = QHBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(8)

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self, cards: list) -> None:
        """Rebuild the strip from a list of ProjectCard DTOs. Shows up to 3."""
        # Clear previous contents
        while self._outer.count():
            item = self._outer.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        visible = cards[:3]

        if not visible:
            return

        for card in visible:
            self._outer.addWidget(self._make_card(card), stretch=1)

        # Fill remaining slots with invisible spacer widgets for equal widths
        for _ in range(3 - len(visible)):
            spacer = QWidget()
            spacer.setVisible(False)
            spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._outer.addWidget(spacer, stretch=1)

    # ── private ───────────────────────────────────────────────────────────────

    def _make_card(self, card) -> QFrame:
        tm = self._ctx.services.get("theme_manager") if self._ctx else None
        bg     = _tok(tm, "card_bg")
        border = _tok(tm, "border")
        hi     = _tok(tm, "text_hi")
        lo     = _tok(tm, "text_lo")
        acc    = _tok(tm, "accent")

        status_color = _STATUS_COLORS.get(getattr(card, "status_color", ""), acc)

        frame = QFrame()
        frame.setObjectName("activeProjectCard")
        frame.setFixedHeight(88)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        frame.setCursor(Qt.PointingHandCursor)
        frame.setStyleSheet(f"""
            QFrame#activeProjectCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 4px;
            }}
            QFrame#activeProjectCard:hover {{
                border-color: {acc};
            }}
        """)

        # Capture signal ref + card data for the closure
        signal_ref = self.action_requested
        _pid   = getattr(card, "id", None)
        _plid  = getattr(card, "plugin_id", "project_tracker")

        def _on_click(event, _sig=signal_ref, _project_id=_pid, _plugin_id=_plid):
            # Navigate to the plugin tab first
            _sig.emit("dashboard_navigate", {
                "plugin_id":  _plugin_id,
                "project_id": _project_id,
            })

        frame.mousePressEvent = _on_click

        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(10, 8, 10, 8)
        vlay.setSpacing(4)

        # ── Row 1: title + status chip ─────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)
        top.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(getattr(card, "title", ""))
        title_lbl.setTextFormat(Qt.PlainText)
        title_lbl.setWordWrap(False)
        title_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {hi}; background: transparent;"
        )
        title_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top.addWidget(title_lbl, stretch=1)

        status_text = getattr(card, "status", None)
        if status_text:
            chip = QLabel(status_text)
            chip.setAlignment(Qt.AlignCenter)
            chip.setFixedHeight(14)
            chip.setStyleSheet(f"""
                font-size: 8px;
                font-weight: bold;
                color: {status_color};
                background: {status_color}1a;
                border: 1px solid {status_color}44;
                border-radius: 3px;
                padding: 0 4px;
            """)
            top.addWidget(chip)

        vlay.addLayout(top)

        # ── Row 2: progress bar ────────────────────────────────────────────────
        progress = getattr(card, "progress", -1)
        if progress >= 0:
            bar = QProgressBar()
            bar.setFixedHeight(4)
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            bar.setValue(int(progress * 100) if progress <= 1.0 else int(progress))
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background: {border};
                    border: none;
                    border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background: {status_color};
                    border-radius: 2px;
                }}
            """)
            vlay.addWidget(bar)

        # ── Row 3: subtitle ────────────────────────────────────────────────────
        subtitle = getattr(card, "subtitle", None)
        sub_lbl = QLabel(subtitle or "")
        sub_lbl.setTextFormat(Qt.PlainText)
        sub_lbl.setWordWrap(False)
        sub_lbl.setStyleSheet(f"font-size: 9px; color: {lo}; background: transparent;")
        vlay.addWidget(sub_lbl)

        # ── Row 4: detail lines (models / hours / milestones) ─────────────────
        detail_lines = getattr(card, "detail_lines", None) or []
        if detail_lines:
            detail_text = "  ·  ".join(detail_lines)
            detail_lbl = QLabel(detail_text)
            detail_lbl.setTextFormat(Qt.PlainText)
            detail_lbl.setWordWrap(False)
            detail_lbl.setStyleSheet(
                f"font-size: 8px; color: {lo}; background: transparent; opacity: 0.8;"
            )
            vlay.addWidget(detail_lbl)

        return frame
