"""Today view — hero banner + PLANNED TODAY + ACTIVITY TODAY + overdue + upcoming week.

Architecture note
-----------------
The Calendar distinguishes two fundamentally different record types:

  Planned Events  (auto_generated=False)
      Created by the user with intent to do something.
      Support completion checkboxes.  Can be overdue.

  Activity Records  (auto_generated=True)
      Automatically logged by sibling plugins when something happened.
      Examples: "Added Vallejo Red", "Logged 90-min session on Terminators".
      These are historical facts.  They already happened.
      They must NEVER have completion checkboxes.
      They must NEVER appear in overdue queues.

This view renders both categories in semantically separate sections so the
distinction is always visually clear to the user.
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QCheckBox, QSizePolicy,
)


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
        "bg_base":   t("bg_base",   "#121212"),
        "bg_raised": t("bg_raised", "#1e1e1e"),
        "bg_input":  t("bg_input",  "#1a1a1a"),
        "card_bg":   t("card_bg",   "#1a1a1a"),
        "border":    t("border",    "#2a2a2a"),
        "text_hi":   t("text_hi",   "#e8e8e8"),
        "text_mid":  t("text_mid",  "#b0b0b0"),
        "text_lo":   t("text_lo",   "#808080"),
        "accent":    t("accent",    "#0078d4"),
        "danger":    t("danger",    "#c62828"),
        "success":   t("success",   "#2e7d32"),
        "warning":   t("warning",   "#e07820"),
    }


# ── Date formatting helpers ────────────────────────────────────────────────────

_DAYS  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

def _day_name(d: date) -> str:
    return _DAYS[d.weekday()]

def _full_date(d: date) -> str:
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"

def _short_date(d: date) -> str:
    return f"{_MONTHS[d.month - 1][:3].upper()} {d.day}"

def _days_ago(iso_str: str) -> str:
    try:
        d = date.fromisoformat(iso_str)
        delta = (date.today() - d).days
        if delta == 1:
            return "yesterday"
        return f"{delta}d ago"
    except (ValueError, TypeError):
        return ""


# ── Badge / section label helpers ──────────────────────────────────────────────

def _make_badge(text: str, bg: str, fg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        QLabel {{
            background: {bg};
            color: {fg};
            border-radius: 3px;
            font-size: 10px;
            padding: 1px 6px;
        }}
    """)
    lbl.setTextFormat(Qt.PlainText)
    return lbl


def _make_section_label(text: str, color: str, bg_tint: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        QLabel {{
            background: {bg_tint};
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


# ── Planned-event session card (with checkbox) ─────────────────────────────────

class _SessionCard(QFrame):
    """Full session card for *planned* events — has a completion checkbox."""

    card_clicked             = Signal(object)   # CalendarEvent
    checkbox_toggled         = Signal(int)      # event.id
    source_navigate_requested = Signal(str)     # plugin_id

    def __init__(self, event, tok: dict, parent=None):
        super().__init__(parent)
        self._event = event
        self._tok   = tok

        self.setObjectName("sessionCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 10, 0)
        outer.setSpacing(0)

        # Left color stripe
        stripe = QFrame()
        stripe.setFixedWidth(3)
        stripe.setStyleSheet(f"background: {event.color()}; border: none;")
        outer.addWidget(stripe)

        # Card content
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(content_widget)
        vlay.setContentsMargins(10, 10, 0, 10)
        vlay.setSpacing(5)

        # Top row: icon + title + checkbox
        top = QHBoxLayout()
        top.setSpacing(6)

        icon_lbl = QLabel(event.icon())
        icon_lbl.setFixedWidth(20)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 16px; background: transparent;")
        top.addWidget(icon_lbl)

        title_style = (
            f"font-size: 13px; font-weight: 600; color: {tok['text_lo']}; "
            f"background: transparent; text-decoration: line-through;"
            if event.completed
            else
            f"font-size: 13px; font-weight: 600; color: {tok['text_hi']}; "
            f"background: transparent;"
        )
        title_lbl = QLabel(event.title)
        title_lbl.setStyleSheet(title_style)
        title_lbl.setTextFormat(Qt.PlainText)
        top.addWidget(title_lbl, stretch=1)

        # Checkbox — only planned events have these
        self._chk = QCheckBox()
        self._chk.setChecked(event.completed)
        self._chk.setStyleSheet("background: transparent;")
        self._chk.setToolTip("Mark as complete")
        self._chk.toggled.connect(self._on_checkbox)
        top.addWidget(self._chk)
        vlay.addLayout(top)

        # Bottom row: time badge + duration badge + linked name
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        time_str = event.display_time()
        time_badge = _make_badge(time_str, tok["bg_raised"], tok["text_lo"])
        bottom.addWidget(time_badge)

        dur = event.display_duration()
        if dur:
            dur_badge = _make_badge(dur, tok["bg_raised"], tok["text_lo"])
            bottom.addWidget(dur_badge)

        if event.linked_name:
            link_lbl = QLabel(event.linked_name)
            link_lbl.setStyleSheet(
                f"font-size: 10px; color: {tok['text_lo']}; background: transparent;"
            )
            link_lbl.setTextFormat(Qt.PlainText)
            bottom.addWidget(link_lbl)

        bottom.addStretch()
        vlay.addLayout(bottom)

        # Source navigation link
        if event.linked_plugin:
            plugin_name = _PLUGIN_DISPLAY_NAMES.get(event.linked_plugin, event.linked_plugin)
            src_lbl = QLabel(f"→ {plugin_name}")
            src_lbl.setStyleSheet(
                f"font-size: 9px; color: {tok['accent']}; "
                "background: transparent; text-decoration: underline;"
            )
            src_lbl.setCursor(Qt.PointingHandCursor)
            _pid = event.linked_plugin
            src_lbl.mousePressEvent = (
                lambda _e, pid=_pid: self.source_navigate_requested.emit(pid)
            )
            vlay.addWidget(src_lbl)

        outer.addWidget(content_widget, stretch=1)

    def _apply_style(self):
        tok = self._tok
        self.setStyleSheet(f"""
            QFrame#sessionCard {{
                background: {tok['bg_raised']};
                border: 1px solid {tok['border']};
                border-radius: 6px;
            }}
            QFrame#sessionCard:hover {{
                border-color: {tok['accent']};
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            chk_rect = self._chk.geometry()
            if not chk_rect.contains(event.pos()):
                self.card_clicked.emit(self._event)
        super().mousePressEvent(event)

    def _on_checkbox(self, checked: bool):
        if self._event.id is not None:
            self.checkbox_toggled.emit(self._event.id)


# ── Activity record row (NO checkbox) ─────────────────────────────────────────

class _ActivityRow(QFrame):
    """Compact row for auto-generated history records.

    Deliberately has NO checkbox — these records already happened.
    Clicking opens the event dialog for viewing / note editing only.
    """

    row_clicked               = Signal(object)   # CalendarEvent
    source_navigate_requested = Signal(str)       # plugin_id

    def __init__(self, event, tok: dict, parent=None):
        super().__init__(parent)
        self._event = event

        self.setObjectName("activityRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(38)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame#activityRow {{
                background: transparent;
                border: none;
            }}
            QFrame#activityRow:hover {{
                background: {tok['bg_raised']};
                border-radius: 4px;
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 10, 0)
        row.setSpacing(0)

        # Thin left stripe (dimmer than session cards — these are secondary records)
        stripe = QFrame()
        stripe.setFixedWidth(2)
        stripe.setStyleSheet(f"background: {event.color()}88; border: none;")
        row.addWidget(stripe)

        row.addSpacing(10)

        # Icon
        icon_lbl = QLabel(event.icon())
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
        row.addWidget(icon_lbl)

        row.addSpacing(8)

        # Content column: title + source plugin
        content = QVBoxLayout()
        content.setContentsMargins(0, 5, 0, 5)
        content.setSpacing(2)

        title_lbl = QLabel(event.title)
        title_lbl.setStyleSheet(
            f"font-size: 11px; color: {tok['text_mid']}; background: transparent;"
        )
        title_lbl.setTextFormat(Qt.PlainText)
        content.addWidget(title_lbl)

        if event.linked_plugin:
            plugin_name = _PLUGIN_DISPLAY_NAMES.get(event.linked_plugin, event.linked_plugin)
            src_lbl = QLabel(f"→ {plugin_name}")
            src_lbl.setStyleSheet(
                f"font-size: 9px; color: {tok['accent']}; "
                "background: transparent; text-decoration: underline;"
            )
            src_lbl.setCursor(Qt.PointingHandCursor)
            _pid = event.linked_plugin
            src_lbl.mousePressEvent = (
                lambda _e, pid=_pid: self.source_navigate_requested.emit(pid)
            )
            content.addWidget(src_lbl)

        row.addLayout(content, stretch=1)

        # Duration badge (if present — e.g. hobby sessions have duration)
        dur = event.display_duration()
        if dur:
            dur_badge = _make_badge(dur, tok["bg_raised"], tok["text_lo"])
            row.addWidget(dur_badge)
            row.addSpacing(6)

        # "📝 Record" indicator — replaces the checkbox for activity records
        rec_lbl = QLabel("📝")
        rec_lbl.setFixedWidth(20)
        rec_lbl.setAlignment(Qt.AlignCenter)
        rec_lbl.setStyleSheet(
            f"font-size: 11px; color: {tok['text_lo']}; background: transparent;"
        )
        rec_lbl.setToolTip("Automatically logged activity record")
        row.addWidget(rec_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.row_clicked.emit(self._event)
        super().mousePressEvent(event)


# ── Compact overdue row ────────────────────────────────────────────────────────

class _OverdueRow(QFrame):
    """Compact row used in the OVERDUE section (planned events only)."""

    row_clicked               = Signal(object)
    checkbox_toggled          = Signal(int)
    source_navigate_requested = Signal(str)

    def __init__(self, event, tok: dict, parent=None):
        super().__init__(parent)
        self._event = event

        self.setObjectName("overdueRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(38)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame#overdueRow {{
                background: transparent;
                border: none;
            }}
            QFrame#overdueRow:hover {{
                background: {tok['bg_raised']};
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 4, 8, 4)
        row.setSpacing(8)

        icon_lbl = QLabel(event.icon())
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent;")
        row.addWidget(icon_lbl)

        title_lbl = QLabel(event.title)
        title_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {tok['text_mid']}; background: transparent;"
        )
        title_lbl.setTextFormat(Qt.PlainText)
        row.addWidget(title_lbl, stretch=1)

        ago = _days_ago(event.event_date)
        if ago:
            ago_lbl = QLabel(ago)
            ago_lbl.setStyleSheet(
                f"font-size: 10px; color: {tok['danger']}; background: transparent;"
            )
            row.addWidget(ago_lbl)

        if event.linked_plugin:
            plugin_name = _PLUGIN_DISPLAY_NAMES.get(event.linked_plugin, event.linked_plugin)
            _pid = event.linked_plugin
            src_lbl = QLabel(f"→ {plugin_name}")
            src_lbl.setStyleSheet(
                f"font-size: 9px; color: {tok['accent']}; "
                "background: transparent; text-decoration: underline;"
            )
            src_lbl.setCursor(Qt.PointingHandCursor)
            src_lbl.mousePressEvent = (
                lambda _e, pid=_pid: self.source_navigate_requested.emit(pid)
            )
            row.addWidget(src_lbl)

        self._chk = QCheckBox()
        self._chk.setChecked(event.completed)
        self._chk.setStyleSheet("background: transparent;")
        self._chk.toggled.connect(self._on_checkbox)
        row.addWidget(self._chk)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            chk_rect = self._chk.geometry()
            if not chk_rect.contains(event.pos()):
                self.row_clicked.emit(self._event)
        super().mousePressEvent(event)

    def _on_checkbox(self, checked: bool):
        if self._event.id is not None:
            self.checkbox_toggled.emit(self._event.id)


# ── Compact upcoming row ───────────────────────────────────────────────────────

class _UpcomingRow(QFrame):
    """Compact row: time + icon + title used in UPCOMING THIS WEEK."""

    row_clicked = Signal(object)

    def __init__(self, event, tok: dict, parent=None):
        super().__init__(parent)
        self._event = event

        self.setObjectName("upcomingRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(34)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame#upcomingRow {{
                background: transparent;
                border: none;
            }}
            QFrame#upcomingRow:hover {{
                background: {tok['bg_raised']};
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 3, 8, 3)
        row.setSpacing(6)

        time_lbl = QLabel(event.display_time())
        time_lbl.setFixedWidth(52)
        time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        time_lbl.setStyleSheet(
            f"font-size: 10px; color: {tok['text_lo']}; background: transparent;"
        )
        row.addWidget(time_lbl)

        # Color dot
        dot = QLabel("●")
        dot.setFixedWidth(10)
        dot.setAlignment(Qt.AlignCenter)
        dot.setStyleSheet(f"font-size: 8px; color: {event.color()}; background: transparent;")
        row.addWidget(dot)

        icon_lbl = QLabel(event.icon())
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 12px; background: transparent;")
        row.addWidget(icon_lbl)

        title_lbl = QLabel(event.title)
        title_lbl.setStyleSheet(
            f"font-size: 11px; color: {tok['text_mid']}; background: transparent;"
        )
        title_lbl.setTextFormat(Qt.PlainText)
        row.addWidget(title_lbl, stretch=1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.row_clicked.emit(self._event)
        super().mousePressEvent(event)


# ── Main widget ────────────────────────────────────────────────────────────────

class TodayView(QWidget):
    """Hero + PLANNED TODAY (checkboxes) + ACTIVITY TODAY (no checkboxes) + overdue + upcoming."""

    event_clicked    = Signal(object)   # CalendarEvent
    complete_toggled = Signal(int)      # event.id
    add_requested    = Signal(object)   # date (today)
    source_navigate  = Signal(str)      # plugin_id

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        tok = _tok(context)
        self.setStyleSheet(f"background: {tok['bg_base']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Hero banner ───────────────────────────────────────────────────────
        self._hero = self._build_hero(tok)
        outer.addWidget(self._hero)

        # ── Scroll area ───────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"background: {tok['bg_base']}; border: none;")

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {tok['bg_base']};")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 12, 12, 12)
        self._content_layout.setSpacing(12)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, stretch=1)

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(
        self,
        planned: list,
        activity: list,
        overdue: list,
        upcoming_week: list,
    ) -> None:
        """Full refresh of all sections.

        Parameters
        ----------
        planned:
            User-created planned events for today — support checkboxes.
        activity:
            Auto-generated history records for today — no checkboxes, read-only.
        overdue:
            Planned events past their due date — support checkboxes.
        upcoming_week:
            Planned events from tomorrow through the next 6 days.
        """
        # Clear all but the trailing stretch
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tok = _tok(self._ctx)

        # Update hero with planned count
        self._update_hero(len(planned), len(activity), tok)

        insert_pos = 0

        # ── PLANNED TODAY ─────────────────────────────────────────────────────
        planned_section = self._build_planned_section(planned, tok)
        self._content_layout.insertWidget(insert_pos, planned_section)
        insert_pos += 1

        # ── ACTIVITY TODAY (only if non-empty) ────────────────────────────────
        if activity:
            activity_section = self._build_activity_section(activity, tok)
            self._content_layout.insertWidget(insert_pos, activity_section)
            insert_pos += 1

        # ── OVERDUE (only if non-empty) ───────────────────────────────────────
        if overdue:
            overdue_section = self._build_overdue_section(overdue, tok)
            self._content_layout.insertWidget(insert_pos, overdue_section)
            insert_pos += 1

        # ── UPCOMING THIS WEEK ────────────────────────────────────────────────
        if upcoming_week:
            week_section = self._build_week_section(upcoming_week, tok)
            self._content_layout.insertWidget(insert_pos, week_section)
            insert_pos += 1

        # ── Add Session button ────────────────────────────────────────────────
        add_btn = self._build_add_button(tok)
        self._content_layout.insertWidget(insert_pos, add_btn)

    # ── Hero ───────────────────────────────────────────────────────────────────

    def _build_hero(self, tok: dict) -> QFrame:
        today = date.today()
        hero  = QFrame()
        hero.setObjectName("heroFrame")
        hero.setFixedHeight(76)
        hero.setStyleSheet(f"""
            QFrame#heroFrame {{
                background: {tok['card_bg']};
                border-left: 3px solid {tok['accent']};
                border-radius: 8px;
                border-top: none;
                border-right: none;
                border-bottom: none;
            }}
        """)

        row = QHBoxLayout(hero)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(10)

        # Left: day name + full date
        left = QVBoxLayout()
        left.setSpacing(2)

        self._day_name_lbl = QLabel(_day_name(today).upper())
        self._day_name_lbl.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {tok['accent']}; "
            f"letter-spacing: 2px; background: transparent;"
        )
        left.addWidget(self._day_name_lbl)

        self._full_date_lbl = QLabel(_full_date(today))
        self._full_date_lbl.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {tok['text_hi']}; background: transparent;"
        )
        left.addWidget(self._full_date_lbl)
        row.addLayout(left, stretch=1)

        # Right: two stacked stat badges
        right = QVBoxLayout()
        right.setSpacing(4)
        right.setAlignment(Qt.AlignVCenter)

        self._count_badge = QLabel("Rest day")
        self._count_badge.setStyleSheet(
            f"background: {tok['bg_raised']}; color: {tok['text_hi']}; "
            f"border-radius: 10px; font-size: 11px; font-weight: 600; padding: 3px 12px;"
        )
        self._count_badge.setAlignment(Qt.AlignCenter)
        right.addWidget(self._count_badge)

        self._activity_badge = QLabel("")
        self._activity_badge.setStyleSheet(
            f"background: transparent; color: {tok['text_lo']}; "
            f"font-size: 9px; padding: 0 4px;"
        )
        self._activity_badge.setAlignment(Qt.AlignCenter)
        self._activity_badge.setVisible(False)
        right.addWidget(self._activity_badge)

        row.addLayout(right)
        return hero

    def _update_hero(self, planned_count: int, activity_count: int, tok: dict) -> None:
        today = date.today()
        self._day_name_lbl.setText(_day_name(today).upper())
        self._full_date_lbl.setText(_full_date(today))

        if planned_count > 0:
            label = f"{planned_count} session{'s' if planned_count != 1 else ''} planned"
            self._count_badge.setText(label)
            self._count_badge.setStyleSheet(
                f"background: {tok['accent']}; color: white; "
                f"border-radius: 10px; font-size: 11px; font-weight: 600; padding: 3px 12px;"
            )
        else:
            self._count_badge.setText("Rest day")
            self._count_badge.setStyleSheet(
                f"background: {tok['bg_raised']}; color: {tok['text_hi']}; "
                f"border-radius: 10px; font-size: 11px; font-weight: 600; padding: 3px 12px;"
            )

        if activity_count > 0:
            act_label = f"{activity_count} activit{'ies' if activity_count != 1 else 'y'} logged"
            self._activity_badge.setText(act_label)
            self._activity_badge.setVisible(True)
        else:
            self._activity_badge.setVisible(False)

    # ── Section: PLANNED TODAY ─────────────────────────────────────────────────

    def _build_planned_section(self, events: list, tok: dict) -> QWidget:
        """Planned events — full session cards with completion checkboxes."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(6)

        hdr = _make_section_label("PLANNED TODAY", tok["accent"], f"{tok['accent']}11")
        vlay.addWidget(hdr)

        if not events:
            empty_card = QFrame()
            empty_card.setObjectName("emptyCard")
            empty_card.setStyleSheet(f"""
                QFrame#emptyCard {{
                    background: {tok['card_bg']};
                    border: 1px solid {tok['border']};
                    border-radius: 6px;
                }}
            """)
            empty_lay = QVBoxLayout(empty_card)
            empty_lay.setContentsMargins(16, 14, 16, 14)
            empty_lay.setSpacing(8)
            empty_lay.setAlignment(Qt.AlignCenter)

            msg = QLabel("Nothing scheduled yet")
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(
                f"font-size: 12px; color: {tok['text_lo']}; background: transparent;"
            )
            empty_lay.addWidget(msg)

            sched_btn = QPushButton("＋  Schedule a session")
            sched_btn.setFlat(True)
            sched_btn.setCursor(Qt.PointingHandCursor)
            sched_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {tok['accent']}; font-size: 11px; font-weight: 600; padding: 0;
                }}
                QPushButton:hover {{ text-decoration: underline; }}
            """)
            sched_btn.clicked.connect(lambda: self.add_requested.emit(date.today()))
            empty_lay.addWidget(sched_btn, alignment=Qt.AlignCenter)

            vlay.addWidget(empty_card)
        else:
            for ev in events:
                card = _SessionCard(ev, tok)
                card.card_clicked.connect(self.event_clicked)
                card.checkbox_toggled.connect(self.complete_toggled)
                card.source_navigate_requested.connect(self.source_navigate)
                vlay.addWidget(card)

        return container

    # ── Section: ACTIVITY TODAY ────────────────────────────────────────────────

    def _build_activity_section(self, activity: list, tok: dict) -> QWidget:
        """Auto-generated activity records — compact log rows, NO checkboxes.

        This is intentional.  These records already happened.  They are history.
        Showing checkboxes would imply something still needs to be done, which
        is semantically wrong for auto-logged data.
        """
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        count = len(activity)
        hdr = _make_section_label(
            f"ACTIVITY TODAY  ·  {count}",
            tok["text_lo"],
            "transparent",
        )
        vlay.addWidget(hdr)
        vlay.addSpacing(4)

        # Wrapper card for the activity log
        card = QFrame()
        card.setObjectName("activityCard")
        card.setStyleSheet(f"""
            QFrame#activityCard {{
                background: {tok['card_bg']};
                border: 1px solid {tok['border']};
                border-radius: 6px;
            }}
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 4, 0, 4)
        card_lay.setSpacing(0)

        for i, ev in enumerate(activity):
            row = _ActivityRow(ev, tok)
            row.row_clicked.connect(self.event_clicked)
            row.source_navigate_requested.connect(self.source_navigate)
            card_lay.addWidget(row)

            if i < len(activity) - 1:
                div = QFrame()
                div.setFrameShape(QFrame.HLine)
                div.setStyleSheet(
                    f"color: {tok['border']}; background: {tok['border']};"
                )
                div.setFixedHeight(1)
                card_lay.addWidget(div)

        vlay.addWidget(card)
        return container

    # ── Section: OVERDUE ───────────────────────────────────────────────────────

    def _build_overdue_section(self, overdue: list, tok: dict) -> QWidget:
        """Overdue planned events — with checkboxes to mark complete."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        hdr = _make_section_label(
            f"⚠  OVERDUE  ·  {len(overdue)}",
            tok["danger"],
            f"{tok['danger']}11",
        )
        vlay.addWidget(hdr)

        for ev in overdue:
            row = _OverdueRow(ev, tok)
            row.row_clicked.connect(self.event_clicked)
            row.checkbox_toggled.connect(self.complete_toggled)
            row.source_navigate_requested.connect(self.source_navigate)
            vlay.addWidget(row)

            div = QFrame()
            div.setFrameShape(QFrame.HLine)
            div.setStyleSheet(
                f"color: {tok['border']}; background: {tok['border']};"
            )
            div.setFixedHeight(1)
            vlay.addWidget(div)

        return container

    # ── Section: UPCOMING THIS WEEK ───────────────────────────────────────────

    def _build_week_section(self, upcoming_week: list, tok: dict) -> QWidget:
        """Planned events grouped by day for the coming week."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(6)

        hdr = _make_section_label("UPCOMING THIS WEEK", tok["text_lo"], "transparent")
        vlay.addWidget(hdr)

        today    = date.today()
        tomorrow = today + timedelta(days=1)

        groups: dict[str, list] = {}
        for ev in upcoming_week:
            groups.setdefault(ev.event_date, []).append(ev)

        for iso_date in sorted(groups.keys()):
            try:
                d = date.fromisoformat(iso_date)
            except (ValueError, TypeError):
                continue

            if d == today:
                day_label = "TODAY"
            elif d == tomorrow:
                day_label = "TOMORROW"
            else:
                day_label = f"{_day_name(d).upper()}  {_short_date(d)}"

            day_hdr = QLabel(day_label)
            day_hdr.setStyleSheet(
                f"font-size: 9px; font-weight: 700; color: {tok['text_lo']}; "
                f"letter-spacing: 1px; padding: 4px 0 2px 4px; background: transparent;"
            )
            vlay.addWidget(day_hdr)

            for ev in groups[iso_date]:
                row = _UpcomingRow(ev, tok)
                row.row_clicked.connect(self.event_clicked)
                vlay.addWidget(row)

        return container

    # ── Add button ────────────────────────────────────────────────────────────

    def _build_add_button(self, tok: dict) -> QPushButton:
        btn = QPushButton("＋  Schedule New Session")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(38)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {tok['bg_raised']};
                border: 1px solid {tok['border']};
                border-radius: 6px;
                color: {tok['accent']};
                font-size: 12px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                border-color: {tok['accent']};
                background: {tok['bg_raised']};
            }}
            QPushButton:pressed {{
                background: {tok['bg_input']};
            }}
        """)
        btn.clicked.connect(lambda: self.add_requested.emit(date.today()))
        return btn
