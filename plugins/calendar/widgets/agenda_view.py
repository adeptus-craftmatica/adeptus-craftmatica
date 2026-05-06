"""Agenda view — scrollable chronological list of upcoming and overdue events."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QCheckBox, QSizePolicy,
)


# ── Theme helper ───────────────────────────────────────────────────────────────

def _tok(ctx) -> dict:
    """Return a theme-token dict with safe fallbacks."""
    tm = ctx.services.get("theme_manager") if ctx else None
    def t(name, fallback):
        if tm is None:
            return fallback
        val = tm.token(name)
        return val if val else fallback

    return {
        "bg_base":  t("bg_base",  "#121212"),
        "bg_raised": t("bg_raised", "#1e1e1e"),
        "bg_input": t("bg_input",  "#1a1a1a"),
        "card_bg":  t("card_bg",   "#1a1a1a"),
        "border":   t("border",    "#2a2a2a"),
        "text_hi":  t("text_hi",   "#e8e8e8"),
        "text_mid": t("text_mid",  "#b0b0b0"),
        "text_lo":  t("text_lo",   "#808080"),
        "accent":   t("accent",    "#0078d4"),
        "danger":   t("danger",    "#c62828"),
        "success":  t("success",   "#2e7d32"),
        "warning":  t("warning",   "#e07820"),
    }


# ── Section grouping helpers ───────────────────────────────────────────────────

def _section_for_event(ev, today: date, tomorrow: date, week_end: date) -> str:
    """Return the section key for an upcoming event."""
    try:
        d = date.fromisoformat(ev.event_date)
    except (ValueError, TypeError):
        return "UPCOMING"
    if d == today:
        return "TODAY"
    if d == tomorrow:
        return "TOMORROW"
    if today < d <= week_end:
        return "THIS WEEK"
    return "UPCOMING"


# ── Clickable event row ────────────────────────────────────────────────────────

_PLUGIN_DISPLAY_NAMES: dict[str, str] = {
    "paint_tracker":    "Paint Tracker",
    "model_tracker":    "Model Tracker",
    "army_builder":     "Army Builder",
    "campaign_tracker": "Campaign Tracker",
    "tool_tracker":     "Tool Tracker",
    "materials_tracker":"Materials Tracker",
    "project_tracker":  "Projects",
    "paint_scheme":     "Paint Schemes",
}


class _EventRow(QFrame):
    """A single agenda row. Emits row_clicked, checkbox_toggled, or source_navigate_requested."""

    row_clicked             = Signal(object)   # CalendarEvent
    checkbox_toggled        = Signal(int)      # event.id
    source_navigate_requested = Signal(str)    # plugin_id

    def __init__(self, event, tok: dict, parent=None):
        super().__init__(parent)
        self._event = event
        self._tok   = tok

        self._bg_normal = tok["bg_base"]
        self._bg_hover  = tok["bg_raised"]

        self.setObjectName("agendaEventRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(52)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style(hovered=False)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 8, 0)
        row.setSpacing(0)

        # ── Left color stripe ─────────────────────────────────────────────────
        # Activity records use a dimmer (semi-transparent) stripe to visually
        # distinguish them from user-created planned events.
        stripe_color = f"{event.color()}88" if event.is_activity_record() else event.color()
        stripe = QFrame()
        stripe.setFixedWidth(3)
        stripe.setStyleSheet(f"background: {stripe_color}; border: none;")
        row.addWidget(stripe)

        row.addSpacing(8)

        # ── Time column ───────────────────────────────────────────────────────
        time_lbl = QLabel(event.display_time())
        time_lbl.setFixedWidth(60)
        time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        time_lbl.setStyleSheet(
            f"font-size: 10px; color: {tok['text_lo']}; background: transparent;"
        )
        row.addWidget(time_lbl)

        row.addSpacing(6)

        # ── Icon ──────────────────────────────────────────────────────────────
        icon_lbl = QLabel(event.icon())
        icon_lbl.setFixedWidth(20)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 14px; background: transparent;")
        row.addWidget(icon_lbl)

        row.addSpacing(6)

        # ── Content column ────────────────────────────────────────────────────
        content = QVBoxLayout()
        content.setContentsMargins(0, 6, 0, 6)
        content.setSpacing(2)

        # Activity records use a muted text colour — they are secondary history
        # entries, not primary tasks demanding the user's attention.
        if event.completed:
            title_color = tok["text_lo"]
            title_extra = "text-decoration: line-through;"
        elif event.is_activity_record():
            title_color = tok["text_mid"]
            title_extra = ""
        else:
            title_color = tok["text_hi"]
            title_extra = ""

        title_style = (
            f"font-size: 12px; font-weight: 600; color: {title_color}; "
            f"background: transparent; {title_extra}"
        )
        title_lbl = QLabel(event.title)
        title_lbl.setStyleSheet(title_style)
        title_lbl.setTextFormat(Qt.PlainText)
        content.addWidget(title_lbl)

        subtitle_parts = []
        dur = event.display_duration()
        if dur:
            subtitle_parts.append(dur)
        if event.linked_name:
            subtitle_parts.append(event.linked_name)
        if subtitle_parts:
            sub_lbl = QLabel("  ·  ".join(subtitle_parts))
            sub_lbl.setStyleSheet(
                f"font-size: 10px; color: {tok['text_lo']}; background: transparent;"
            )
            sub_lbl.setTextFormat(Qt.PlainText)
            content.addWidget(sub_lbl)

        # Source navigation link — shown when the event was auto-generated from another plugin
        if event.linked_plugin:
            plugin_name = _PLUGIN_DISPLAY_NAMES.get(event.linked_plugin, event.linked_plugin)
            src_lbl = QLabel(f"→ {plugin_name}")
            src_lbl.setStyleSheet(
                f"font-size: 9px; color: {tok['accent']}; "
                "background: transparent; text-decoration: underline;"
            )
            src_lbl.setCursor(Qt.PointingHandCursor)
            # Store plugin_id for click handler (lambda capture)
            _pid = event.linked_plugin
            src_lbl.mousePressEvent = (
                lambda _e, pid=_pid: self.source_navigate_requested.emit(pid)
            )
            content.addWidget(src_lbl)

        row.addLayout(content, stretch=1)

        # ── Right-side indicator ──────────────────────────────────────────────
        # Activity records (auto_generated) are historical facts that already
        # happened.  A completion checkbox makes no semantic sense for them.
        # Show a 📝 badge instead.  Planned events get a normal checkbox.
        if event.is_activity_record():
            self._chk = None
            rec_lbl = QLabel("📝")
            rec_lbl.setFixedWidth(20)
            rec_lbl.setAlignment(Qt.AlignCenter)
            rec_lbl.setStyleSheet(
                f"font-size: 11px; color: {tok['text_lo']}; background: transparent;"
            )
            rec_lbl.setToolTip("Auto-logged activity record")
            row.addWidget(rec_lbl)
        else:
            self._chk = QCheckBox()
            self._chk.setFixedWidth(20)
            self._chk.setChecked(event.completed)
            self._chk.setStyleSheet("background: transparent;")
            self._chk.toggled.connect(self._on_checkbox_toggled)
            row.addWidget(self._chk)

        # ── Priority dot (planned events only) ───────────────────────────────
        if not event.is_activity_record() and event.priority < 3:
            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setAlignment(Qt.AlignCenter)
            dot.setStyleSheet(
                f"font-size: 8px; color: {event.priority_color()}; background: transparent;"
            )
            row.addWidget(dot)
        else:
            spacer = QLabel()
            spacer.setFixedWidth(12)
            row.addWidget(spacer)

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self, hovered: bool):
        bg = self._bg_hover if hovered else self._bg_normal
        self.setStyleSheet(f"""
            QFrame#agendaEventRow {{
                background: {bg};
                border: none;
                border-radius: 0px;
            }}
        """)

    # ── Events ────────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._apply_style(hovered=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(hovered=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Only emit row click when not clicking the checkbox.
            # For activity records, _chk is None, so always emit row click.
            if self._chk is not None:
                chk_rect = self._chk.geometry()
                if not chk_rect.contains(event.pos()):
                    self.row_clicked.emit(self._event)
            else:
                self.row_clicked.emit(self._event)
        super().mousePressEvent(event)

    def _on_checkbox_toggled(self, checked: bool):
        if self._event.id is not None:
            self.checkbox_toggled.emit(self._event.id)


# ── Main widget ────────────────────────────────────────────────────────────────

class AgendaView(QWidget):
    """Scrollable agenda grouped by OVERDUE / TODAY / TOMORROW / THIS WEEK / UPCOMING."""

    event_clicked    = Signal(object)   # CalendarEvent
    complete_toggled = Signal(int)      # event.id
    source_navigate  = Signal(str)      # plugin_id

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        tok = _tok(context)
        self.setStyleSheet(f"background: {tok['bg_base']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Range header label ────────────────────────────────────────────────
        self._range_lbl = QLabel("")
        self._range_lbl.setStyleSheet(
            f"font-size: 10px; color: {tok['text_lo']}; "
            f"padding: 6px 12px 4px 12px; background: transparent;"
        )
        outer.addWidget(self._range_lbl)

        # ── Scroll area ───────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"background: {tok['bg_base']}; border: none;")

        self._inner = QWidget()
        self._inner.setStyleSheet(f"background: {tok['bg_base']};")
        self._sections_layout = QVBoxLayout(self._inner)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(0)
        self._sections_layout.addStretch()

        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_range_label(self, text: str) -> None:
        """Update the small header range label."""
        self._range_lbl.setText(text)

    def refresh(self, upcoming: list, overdue: list) -> None:
        """Rebuild the agenda from upcoming and overdue event lists."""
        # Clear existing rows
        while self._sections_layout.count() > 1:
            item = self._sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear_layout(item.layout())

        tok = _tok(self._ctx)

        if not upcoming and not overdue:
            self._show_empty(tok)
            return

        today    = date.today()
        tomorrow = today + timedelta(days=1)
        week_end = today + timedelta(days=6)

        # ── Bucket upcoming events ─────────────────────────────────────────────
        buckets: dict[str, list] = {
            "TODAY":     [],
            "TOMORROW":  [],
            "THIS WEEK": [],
            "UPCOMING":  [],
        }
        for ev in upcoming:
            key = _section_for_event(ev, today, tomorrow, week_end)
            buckets[key].append(ev)

        section_order = [
            ("OVERDUE",   overdue,              tok["danger"],  "#c62828"),
            ("TODAY",     buckets["TODAY"],      tok["accent"],  tok["accent"]),
            ("TOMORROW",  buckets["TOMORROW"],   tok["text_lo"], tok["text_lo"]),
            ("THIS WEEK", buckets["THIS WEEK"],  tok["text_lo"], tok["text_lo"]),
            ("UPCOMING",  buckets["UPCOMING"],   tok["text_lo"], tok["text_lo"]),
        ]

        insert_pos = 0
        for label, events, header_color, _stripe_color in section_order:
            if not events:
                continue
            block = self._build_section(label, events, header_color, tok)
            self._sections_layout.insertWidget(insert_pos, block)
            insert_pos += 1

    # ── Private builders ───────────────────────────────────────────────────────

    def _show_empty(self, tok: dict) -> None:
        empty = QLabel("✓  No upcoming events — you're all caught up!")
        empty.setAlignment(Qt.AlignCenter)
        empty.setStyleSheet(
            f"font-size: 13px; color: {tok['text_lo']}; padding: 40px 20px; background: transparent;"
        )
        self._sections_layout.insertWidget(0, empty)

    def _build_section(self, title: str, events: list, color: str, tok: dict) -> QWidget:
        """Build a section block: header + event rows."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 4, 0, 4)
        vlay.setSpacing(0)

        # Section header
        header = self._make_section_header(title, len(events), color, tok)
        vlay.addWidget(header)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {tok['border']}; background: {tok['border']};")
        sep.setFixedHeight(1)
        vlay.addWidget(sep)

        # Event rows
        for ev in events:
            row = _EventRow(ev, tok)
            row.row_clicked.connect(self.event_clicked)
            row.checkbox_toggled.connect(self.complete_toggled)
            row.source_navigate_requested.connect(self.source_navigate)
            vlay.addWidget(row)

            divider = QFrame()
            divider.setFrameShape(QFrame.HLine)
            divider.setStyleSheet(
                f"color: {tok['border']}; background: {tok['border']};"
            )
            divider.setFixedHeight(1)
            vlay.addWidget(divider)

        return container

    def _make_section_header(self, title: str, count: int, color: str, tok: dict) -> QLabel:
        lbl = QLabel(f"{title}  ·  {count}")
        lbl.setStyleSheet(f"""
            QLabel {{
                background: {color}11;
                color: {color};
                border-left: 3px solid {color};
                border-radius: 4px;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 6px 12px;
            }}
        """)
        lbl.setTextFormat(Qt.PlainText)
        return lbl


# ── Layout utility ─────────────────────────────────────────────────────────────

def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_layout(item.layout())
