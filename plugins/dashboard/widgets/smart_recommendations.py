"""Smart Recommendations widget — cross-plugin actionable next steps."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy,
)

# Priority → (theme token name, label)
_PRIORITY_TOKENS = {
    1: ("danger",  "URGENT"),
    2: ("warning", "IMPORTANT"),
    3: ("accent",  "SUGGESTED"),
}

# Fallbacks when ThemeManager is unavailable
_PRIORITY_FALLBACK = {
    "danger":  "#e05555",
    "warning": "#e07800",
    "accent":  "#0078d4",
}

_MAX_SHOWN = 6   # rows before "+N more" footer


class SmartRecommendationsWidget(QWidget):
    """Full-width list of prioritised, named recommended next actions."""

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
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._container = QWidget()
        self._list = QVBoxLayout(self._container)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(6)
        self._list.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self, recs: list) -> None:
        """Rebuild from a list of Recommendation DTOs (already sorted by priority)."""
        while self._list.count() > 1:
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not recs:
            self._list.insertWidget(0, self._empty_state())
            return

        shown = recs[:_MAX_SHOWN]
        overflow = len(recs) - len(shown)

        for rec in shown:
            row = self._make_row(rec)
            self._list.insertWidget(self._list.count() - 1, row)

        if overflow > 0:
            tm = self._ctx.services.get("theme_manager") if self._ctx else None
            lo = tm.token("text_lo") if tm else "#808080"
            more = QLabel(f"+ {overflow} more recommendation{'s' if overflow != 1 else ''}")
            more.setStyleSheet(
                f"font-size: 10px; color: {lo}; background: transparent; padding: 2px 0;"
            )
            self._list.insertWidget(self._list.count() - 1, more)

    # ── private ───────────────────────────────────────────────────────────────

    def _tm_tokens(self):
        tm = self._ctx.services.get("theme_manager") if self._ctx else None
        return {
            "bg":     tm.token("card_bg")  if tm else "#1a1a1a",
            "border": tm.token("border")   if tm else "#2a2a2a",
            "hi":     tm.token("text_hi")  if tm else "#e8e8e8",
            "mid":    tm.token("text_mid") if tm else "#b0b0b0",
            "lo":     tm.token("text_lo")  if tm else "#808080",
            "bg_raised": tm.token("bg_raised") if tm else "#1e1e1e",
        }

    def _make_row(self, rec) -> QFrame:
        t = self._tm_tokens()
        tm = self._ctx.services.get("theme_manager") if self._ctx else None
        tok_name, pri_label = _PRIORITY_TOKENS.get(rec.priority, _PRIORITY_TOKENS[3])
        pri_color = (tm.token(tok_name) if tm else None) or _PRIORITY_FALLBACK.get(tok_name, "#0078d4")
        radius    = f"{tm.token('radius_base') if tm else 6}px"

        frame = QFrame()
        frame.setObjectName("recRow")
        frame.setStyleSheet(f"""
            QFrame#recRow {{
                background: {t['bg']};
                border: 1px solid {t['border']};
                border-left: 3px solid {pri_color};
                border-radius: {radius};
            }}
            QFrame#recRow:hover {{
                border-color: {pri_color};
                border-left: 3px solid {pri_color};
                background: {t['bg_raised']};
            }}
        """)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(10)

        # Icon
        icon_lbl = QLabel(rec.icon)
        icon_lbl.setStyleSheet(f"font-size: 15px; background: transparent; color: {pri_color};")
        icon_lbl.setFixedWidth(20)
        row.addWidget(icon_lbl)

        # Action + target + context (stacked vertically)
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.setContentsMargins(0, 0, 0, 0)

        # Top line: "Action · Target"
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        top_row.setContentsMargins(0, 0, 0, 0)

        action_lbl = QLabel(rec.action)
        action_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {pri_color}; background: transparent;"
        )
        action_lbl.setTextFormat(Qt.PlainText)
        top_row.addWidget(action_lbl)

        sep = QLabel("·")
        sep.setStyleSheet(f"font-size: 11px; color: {t['lo']}; background: transparent;")
        top_row.addWidget(sep)

        target_lbl = QLabel(rec.target)
        target_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {t['hi']}; background: transparent;"
        )
        target_lbl.setTextFormat(Qt.PlainText)
        top_row.addWidget(target_lbl, stretch=1)
        text_col.addLayout(top_row)

        # Bottom line: context
        if rec.context:
            ctx_lbl = QLabel(rec.context)
            ctx_lbl.setStyleSheet(
                f"font-size: 10px; color: {t['lo']}; background: transparent;"
            )
            ctx_lbl.setTextFormat(Qt.PlainText)
            text_col.addWidget(ctx_lbl)

        row.addLayout(text_col, stretch=1)

        # Priority chip
        chip = QLabel(pri_label)
        chip.setFixedHeight(16)
        chip.setStyleSheet(f"""
            font-size: 8px; font-weight: 700;
            color: {pri_color};
            background: {pri_color}1a;
            border: 1px solid {pri_color}44;
            border-radius: 3px;
            padding: 0 5px;
            letter-spacing: 0.5px;
        """)
        row.addWidget(chip)

        # Action button
        if rec.action_event:
            btn = QPushButton(rec.action_label)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid {pri_color};
                    border-radius: 4px;
                    color: {pri_color};
                    font-size: 10px;
                    font-weight: 600;
                    padding: 0 10px;
                    min-width: 60px;
                }}
                QPushButton:hover {{ background: {pri_color}22; }}
                QPushButton:pressed {{ background: {pri_color}44; }}
            """)
            event   = rec.action_event
            payload = dict(rec.action_payload)
            btn.clicked.connect(
                lambda _=False, e=event, p=payload: self.action_requested.emit(e, p)
            )
            row.addWidget(btn)

        return frame

    def _empty_state(self) -> QLabel:
        tm = self._ctx.services.get("theme_manager") if self._ctx else None
        lo = tm.token("text_lo") if tm else "#808080"
        lbl = QLabel("✓  Nothing urgent — you're on top of everything!")
        lbl.setStyleSheet(
            f"font-size: 12px; color: {lo}; padding: 12px 0; background: transparent;"
        )
        lbl.setAlignment(Qt.AlignCenter)
        return lbl
