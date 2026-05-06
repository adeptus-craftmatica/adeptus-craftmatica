"""Project feed — scrollable list of ProjectCard DTOs."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QFrame, QSizePolicy,
)

PLUGIN_COLORS: dict[str, str] = {
    "paint_tracker":    "#3a86ff",
    "model_tracker":    "#8338ec",
    "army_builder":     "#ff006e",
    "campaign_tracker": "#fb5607",
    "paint_scheme":     "#06d6a0",
    "tool_tracker":     "#ffbe0b",
    "materials_tracker":"#118ab2",
    "dashboard":        "#0078d4",
}

_STATUS_COLORS: dict[str, str] = {
    "accent":  "#0078d4",
    "success": "#2e7d32",
    "warning": "#e07820",
    "danger":  "#c62828",
}


class ProjectFeedWidget(QWidget):
    """Scrollable list of project cards with plugin badge, progress bar, action button."""

    action_requested = Signal(str, dict)   # (event_name, payload)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self._last_cards: list = []   # cache for pin-toggle re-render

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._feed_layout = QVBoxLayout(self._container)
        self._feed_layout.setContentsMargins(0, 0, 0, 0)
        self._feed_layout.setSpacing(8)
        self._feed_layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self, cards: list) -> None:
        """Rebuild feed from list of ProjectCard DTOs."""
        self._last_cards = list(cards)   # cache for pin-toggle re-render
        self._render(cards)

    # ── private ── render ─────────────────────────────────────────────────────

    def _render(self, cards: list) -> None:
        """Clear and rebuild the feed. Pinned cards float to the top."""
        while self._feed_layout.count() > 1:
            item = self._feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not cards:
            empty = QLabel("No active projects")
            tm = self._ctx.services.get("theme_manager") if self._ctx else None
            lo = tm.token("text_lo") if tm else "#808080"
            empty.setStyleSheet(f"color: {lo}; font-size: 13px; padding: 20px;")
            empty.setAlignment(Qt.AlignCenter)
            self._feed_layout.insertWidget(0, empty)
            return

        pinned_keys = self._get_pinned_keys()

        # Sort: pinned first (preserving relative order), then rest
        pinned  = [c for c in cards if self._card_key(c) in pinned_keys]
        regular = [c for c in cards if self._card_key(c) not in pinned_keys]

        # Visual separator between the two groups
        if pinned and regular:
            sorted_cards = pinned + [None] + regular   # None = separator sentinel
        else:
            sorted_cards = pinned + regular

        for card in sorted_cards:
            if card is None:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setFixedHeight(1)
                sep.setStyleSheet("background: rgba(255,255,255,0.07);")
                self._feed_layout.insertWidget(self._feed_layout.count() - 1, sep)
            else:
                is_pinned = self._card_key(card) in pinned_keys
                widget = self._make_card_widget(card, pinned=is_pinned)
                self._feed_layout.insertWidget(self._feed_layout.count() - 1, widget)

    # ── pinning helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _card_key(card) -> str:
        """
        Unique pin key that is stable across restarts and safe across plugins.

        Each plugin's providers use their own auto-increment IDs so a bare
        integer is NOT unique (project 1 vs campaign 1 vs army 1 all share id=1).
        Combining plugin_id with the entity id gives a globally unique key.
        """
        return f"{card.plugin_id}:{card.id}"

    def _get_pinned_keys(self) -> set:
        try:
            svc = self._ctx.services.try_get("settings") if self._ctx else None
            if not svc:
                return set()
            raw = svc.get("dashboard.pinned_projects", "[]")
            data = json.loads(raw)
            # Migrate any old bare-integer entries (pre-compound-key) — discard them
            # cleanly so users start fresh rather than seeing corrupt state.
            return {k for k in data if isinstance(k, str) and ":" in k}
        except Exception:
            return set()

    def _toggle_pin(self, card_key: str) -> None:
        try:
            svc = self._ctx.services.try_get("settings") if self._ctx else None
            if not svc:
                return
            raw = svc.get("dashboard.pinned_projects", "[]")
            pinned: list = json.loads(raw)
            # Strip any stale bare-integer entries from the old format
            pinned = [k for k in pinned if isinstance(k, str) and ":" in k]
            if card_key in pinned:
                pinned.remove(card_key)
            else:
                pinned.append(card_key)
            svc.set("dashboard.pinned_projects", json.dumps(pinned))
            # Re-render immediately using cached cards — no full refresh needed
            self._render(self._last_cards)
        except Exception as e:
            print(f"[PROJECT FEED] toggle pin: {e}")

    # ── private ───────────────────────────────────────────────────────────────

    def _make_card_widget(self, card, pinned: bool = False) -> QFrame:
        tm = self._ctx.services.get("theme_manager") if self._ctx else None
        bg       = tm.token("card_bg")     if tm else "#1e1e1e"
        border   = tm.token("border")      if tm else "#363636"
        bg_input = tm.token("bg_input")    if tm else "#2a2a2a"
        hi       = tm.token("text_hi")     if tm else "#f0f0f0"
        mid      = tm.token("text_mid")    if tm else "#d8d8d8"
        lo       = tm.token("text_lo")     if tm else "#909090"
        radius_base = f"{tm.token('radius_base') if tm else 6}px"
        radius_xs   = f"{tm.token('radius_xs')   if tm else 3}px"
        radius_sm   = f"{tm.token('radius_sm')   if tm else 4}px"

        plugin_color  = PLUGIN_COLORS.get(card.plugin_id, "#0078d4")
        status_color  = _STATUS_COLORS.get(card.status_color, _STATUS_COLORS["accent"])

        frame = QFrame()
        frame.setObjectName("dashProjectCard")
        frame.setStyleSheet(f"""
            QFrame#dashProjectCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {radius_base};
            }}
            QFrame#dashProjectCard:hover {{
                border-color: {plugin_color};
            }}
        """)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(14, 12, 14, 12)
        vlay.setSpacing(6)

        # ── Top row: badge + title + status chip ──────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)

        badge = QLabel(card.plugin_label)
        badge.setStyleSheet(f"""
            background: {plugin_color}22;
            color: {plugin_color};
            border: 1px solid {plugin_color}55;
            border-radius: {radius_xs};
            font-weight: 600;
            padding: 1px 6px;
        """)
        badge.setFixedHeight(18)
        top.addWidget(badge)

        title = QLabel(card.title)
        title.setStyleSheet(f"font-weight: 600; color: {hi}; background: transparent;")
        title.setTextFormat(Qt.PlainText)
        top.addWidget(title, stretch=1)

        if card.status:
            chip = QLabel(card.status)
            chip.setStyleSheet(f"""
                background: {status_color}22;
                color: {status_color};
                border: 1px solid {status_color}55;
                border-radius: {radius_xs};
                font-weight: 600;
                padding: 1px 6px;
            """)
            chip.setFixedHeight(18)
            top.addWidget(chip)

        # ── Pin toggle ────────────────────────────────────────────────────────
        pin_btn = QPushButton("📌" if pinned else "📍")
        pin_btn.setFixedSize(22, 22)
        pin_btn.setToolTip("Unpin from top" if pinned else "Pin to top of feed")
        pin_btn.setCursor(Qt.PointingHandCursor)
        pin_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 13px;
                color: {"#f0c040" if pinned else lo};
                opacity: {"1" if pinned else "0.5"};
                padding: 0;
            }}
            QPushButton:hover {{
                color: #f0c040;
            }}
        """)
        _key = self._card_key(card)
        pin_btn.clicked.connect(lambda _=False, k=_key: self._toggle_pin(k))
        top.addWidget(pin_btn)

        vlay.addLayout(top)

        # ── Subtitle ──────────────────────────────────────────────────────────
        if card.subtitle:
            sub = QLabel(card.subtitle)
            sub.setStyleSheet(f"color: {lo}; background: transparent;")
            sub.setTextFormat(Qt.PlainText)
            vlay.addWidget(sub)

        # ── Progress bar (only when progress ≥ 0) ────────────────────────────
        if card.progress >= 0:
            bar = QProgressBar()
            bar.setFixedHeight(5)
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            bar.setValue(int(card.progress * 100))
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background: {bg_input};
                    border: none;
                    border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background: {status_color};
                    border-radius: 2px;
                }}
            """)
            vlay.addWidget(bar)

        # ── Detail lines ──────────────────────────────────────────────────────
        for line in (card.detail_lines or []):
            if line:
                dl = QLabel(line)
                dl.setStyleSheet(f"color: {mid}; background: transparent;")
                dl.setTextFormat(Qt.PlainText)
                vlay.addWidget(dl)

        # ── Action button ─────────────────────────────────────────────────────
        if card.action_label and card.action_event:
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            btn = QPushButton(card.action_label)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid {plugin_color};
                    border-radius: {radius_sm};
                    color: {plugin_color};
                    font-weight: 600;
                    padding: 0 12px;
                }}
                QPushButton:hover {{
                    background: {plugin_color}22;
                }}
                QPushButton:pressed {{
                    background: {plugin_color}44;
                }}
            """)
            event = card.action_event
            payload = dict(card.action_payload)
            btn.clicked.connect(lambda _=False, e=event, p=payload: self.action_requested.emit(e, p))
            btn_row.addWidget(btn)
            vlay.addLayout(btn_row)

        return frame
