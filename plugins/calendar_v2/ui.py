"""
Calendar 2.0 — Main UI
══════════════════════════════════════════════════════════════════════════════
Layout (no outer scroll):

  ┌─ Header ──────────────────────────────────────────────────────────────┐
  │  📅 Calendar 2.0   [Today] [Week] [Month] [Agenda]   [+ Add]  [🔍]  │
  ├─ Quick Add ────────────────────────────────────────────────────────────┤
  │  "Paint Marines tomorrow 2pm 2h" → smart parse → confirm chip         │
  ├─ QStackedWidget ───────────────────────────────────────────────────────┤
  │  TODAY  │ WEEK  │ MONTH  │ AGENDA                                      │
  └───────────────────────────────────────────────────────────────────────┘

Each view manages its own internal scrolling.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

from PySide6.QtCore    import Qt, Signal, QDate, QSize, QTimer
from PySide6.QtGui     import QColor, QPainter, QFont, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QDialog, QDialogButtonBox, QSizePolicy, QStackedWidget,
    QLineEdit, QComboBox, QSpinBox, QCheckBox, QTextEdit, QDateEdit,
    QTimeEdit, QGridLayout, QButtonGroup, QAbstractButton, QApplication,
    QTabWidget,
)

# ── Design system ─────────────────────────────────────────────────────────────
# Matches dashboard_v2 so the two plugins feel native to the same app.

_C = {
    "bg_deep":     "#141414",
    "bg_base":     "#1c1c1c",
    "bg_card":     "#1e1e1e",
    "bg_raised":   "#212121",
    "bg_input":    "#2a2a2a",
    "bg_hover":    "#2e2e2e",
    "bg_active":   "#333333",
    "border_lo":   "#282828",
    "border":      "#363636",
    "border_hi":   "#484848",
    "text_hi":     "#f0f0f0",
    "text_mid":    "#d8d8d8",
    "text_lo":     "#909090",
    "text_dim":    "#606060",
    "accent":      "#0078d4",
    "accent_hi":   "#1a8ee8",
    "accent_lo":   "#0f4a7a",
    "accent_text": "#60b0ff",
    "danger":      "#e05555",
    "danger_hi":   "#eb6868",
    "danger_lo":   "#2a1515",
    "success":     "#3dba6e",
    "success_lo":  "#0f2a1a",
    "warning":     "#e07800",
    "warning_lo":  "#2a1800",
    "gold":        "#c8960c",
    "gold_lo":     "#2a1e00",
    "overdue":     "#c62828",
}
_FS = {
    "xs":  "10px", "sm": "11px", "base": "12px", "lg": "13px",
    "xl":  "15px", "2xl": "20px", "3xl": "28px",
}
_R = {"xs": "3px", "sm": "5px", "base": "7px", "lg": "10px", "pill": "999px"}

_DAY_NAMES  = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _rgba(hex_color: str, alpha: float) -> str:
    """Convert #RRGGBB hex to rgba() string for Qt stylesheet.

    Qt stylesheets don't support CSS-style #RRGGBBAA 8-digit hex; they use
    #AARRGGBB which is a different byte order.  Using rgba() is the safe,
    cross-platform way to set semi-transparent colours.
    """
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha:.2f})"
    return hex_color  # fallback — already an rgba() or named colour
_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# ── Natural-language quick-add parser ─────────────────────────────────────────

_DATE_WORDS = {
    "today":     0,
    "tonight":   0,
    "tomorrow":  1,
    "tmr":       1,
    "yesterday": -1,
    "monday":    None, "tuesday":   None, "wednesday": None,
    "thursday":  None, "friday":    None, "saturday":  None,
    "sunday":    None,
    "mon": None, "tue": None, "wed": None, "thu": None,
    "fri": None, "sat": None, "sun": None,
    "next monday":    None, "next tuesday":   None, "next wednesday": None,
    "next thursday":  None, "next friday":    None, "next saturday":  None,
    "next sunday":    None,
    "next week":  7,
}
_WEEKDAY_IDX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}
_SESSION_KEYWORDS: dict[str, str] = {
    "paint":       "Painting Session",
    "painting":    "Painting Session",
    "build":       "Building Session",
    "building":    "Building Session",
    "assembly":    "Building Session",
    "assemble":    "Building Session",
    "prime":       "Priming Session",
    "priming":     "Priming Session",
    "base":        "Basing Session",
    "basing":      "Basing Session",
    "kitbash":     "Kitbash Session",
    "resin":       "Resin Printing",
    "print":       "Resin Printing",
    "terrain":     "Terrain Building",
    "army":        "Army Prep",
    "dnd":         "D&D Prep",
    "d&d":         "D&D Prep",
    "dungeon":     "D&D Prep",
    "campaign":    "Campaign Writing",
    "writing":     "Campaign Writing",
    "game":        "Game Night",
    "gaming":      "Game Night",
    "tournament":  "Tournament Prep",
    "inventory":   "Inventory Check",
    "restock":     "Paint Restock Review",
}


def _parse_quick_add(text: str) -> dict:
    """Parse a natural-language string into a partial CalendarEvent dict.

    Examples:
        "Paint Marines tomorrow 2pm 2h"
        "Game night Friday at 7pm"
        "Finish diorama next week"
    """
    result: dict = {}
    remaining = text.strip()

    # ── duration ──────────────────────────────────────────────────────────────
    dur_match = re.search(
        r'\b(\d+)\s*h(?:ours?)?\s*(\d+)?\s*m(?:in(?:utes?)?)?\b'
        r'|\b(\d+)\s*h(?:ours?)?\b'
        r'|\b(\d+)\s*m(?:in(?:utes?)?)?\b',
        remaining, re.I
    )
    if dur_match:
        g = dur_match.groups()
        if g[0] and g[1]:
            result["duration_minutes"] = int(g[0]) * 60 + int(g[1])
        elif g[0]:
            result["duration_minutes"] = int(g[0]) * 60
        elif g[2]:
            result["duration_minutes"] = int(g[2]) * 60
        elif g[3]:
            result["duration_minutes"] = int(g[3])
        remaining = remaining[:dur_match.start()] + remaining[dur_match.end():]

    # ── time ──────────────────────────────────────────────────────────────────
    time_match = re.search(
        r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b'
        r'|(\d{1,2}):(\d{2})\s*(am|pm)?\b'
        r'|(\d{1,2})\s*(am|pm)\b',
        remaining, re.I
    )
    if time_match:
        g = time_match.groups()
        try:
            if g[0]:  # "at HH[:MM] [am/pm]"
                h, m, ampm = int(g[0]), int(g[1] or 0), (g[2] or "").lower()
            elif g[3]:  # "HH:MM [am/pm]"
                h, m, ampm = int(g[3]), int(g[4]), (g[5] or "").lower()
            else:  # "H am/pm"
                h, m, ampm = int(g[6]), 0, (g[7] or "").lower()
            if ampm == "pm" and h < 12:
                h += 12
            if ampm == "am" and h == 12:
                h = 0
            result["time_start"] = f"{h:02d}:{m:02d}"
        except (ValueError, TypeError):
            pass
        remaining = remaining[:time_match.start()] + remaining[time_match.end():]

    # ── date ──────────────────────────────────────────────────────────────────
    today = date.today()
    for pattern in sorted(_DATE_WORDS, key=len, reverse=True):
        pat_re = re.compile(r'\b' + re.escape(pattern) + r'\b', re.I)
        if pat_re.search(remaining):
            offset = _DATE_WORDS[pattern]
            if offset is not None:
                result["event_date"] = (today + timedelta(days=offset)).isoformat()
            else:
                # Resolve weekday
                wd_key = pattern.replace("next ", "")
                target = _WEEKDAY_IDX.get(wd_key)
                if target is not None:
                    days_ahead = (target - today.weekday()) % 7
                    if "next " in pattern:
                        days_ahead = days_ahead if days_ahead > 0 else 7
                    elif days_ahead == 0:
                        days_ahead = 7
                    result["event_date"] = (today + timedelta(days=days_ahead)).isoformat()
            remaining = pat_re.sub("", remaining)
            break

    if "event_date" not in result:
        result["event_date"] = today.isoformat()

    # ── session type ──────────────────────────────────────────────────────────
    for kw, stype in _SESSION_KEYWORDS.items():
        if re.search(r'\b' + re.escape(kw) + r'\b', remaining, re.I):
            result["session_type"] = stype
            break

    # ── title = remaining stripped ────────────────────────────────────────────
    title = re.sub(r'\s{2,}', ' ', remaining).strip().strip(",.-")
    result["title"] = title if title else "New Event"

    return result


# ── Shared helper widgets ──────────────────────────────────────────────────────

def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color: {_C['border']}; max-height: 1px; background: {_C['border']};")
    return f


def _label(text: str, size_key: str = "base", color_key: str = "text_mid",
           bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    weight = "600" if bold else "400"
    lbl.setStyleSheet(
        f"color:{_C[color_key]}; font-size:{_FS[size_key]}; font-weight:{weight};"
        f" background:transparent; border:none;"
    )
    return lbl


class _SectionHeader(QWidget):
    """Section title with optional count badge and collapse toggle."""

    toggled = Signal(bool)  # True = expanded

    def __init__(self, title: str, icon: str = "", collapsible: bool = False, parent=None):
        super().__init__(parent)
        self._expanded = True
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 2)
        row.setSpacing(6)
        if icon:
            row.addWidget(_label(icon, "sm"))
        self._title_lbl = _label(title, "sm", "text_lo", bold=True)
        row.addWidget(self._title_lbl)
        self._badge = QLabel()
        self._badge.setStyleSheet(
            f"color:{_C['text_dim']}; font-size:{_FS['xs']}; background:transparent; border:none;"
        )
        self._badge.hide()
        row.addWidget(self._badge)
        row.addStretch()
        if collapsible:
            self._toggle = QPushButton("▾")
            self._toggle.setFixedSize(20, 20)
            self._toggle.setStyleSheet(
                f"QPushButton{{background:transparent; border:none; color:{_C['text_dim']};"
                f"font-size:{_FS['sm']};}}"
                f"QPushButton:hover{{color:{_C['text_lo']};}}"
            )
            self._toggle.clicked.connect(self._do_toggle)
            row.addWidget(self._toggle)

    def set_count(self, n: int):
        if n > 0:
            self._badge.setText(f"({n})")
            self._badge.show()
        else:
            self._badge.hide()

    def set_title(self, text: str):
        self._title_lbl.setText(text)

    def _do_toggle(self):
        self._expanded = not self._expanded
        arrow = "▾" if self._expanded else "▸"
        if hasattr(self, "_toggle"):
            self._toggle.setText(arrow)
        self.toggled.emit(self._expanded)


class _EventRow(QFrame):
    """A single event row: [color bar] [icon] [title + meta] [check / action buttons]."""

    complete_requested = Signal(int)   # event_id
    edit_requested     = Signal(int)   # event_id
    delete_requested   = Signal(int)   # event_id

    def __init__(self, event, show_date: bool = False, parent=None):
        super().__init__(parent)
        self._ev = event
        self.setObjectName("EventRow")
        self.setFixedHeight(46)
        self.setStyleSheet(
            f"QFrame#EventRow{{background:{_C['bg_card']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; margin:1px 0;}}"
            f"QFrame#EventRow:hover{{background:{_C['bg_hover']}; border-color:{_C['border_hi']};}}"
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 8, 0)
        outer.setSpacing(0)

        # Colored left bar
        bar = QFrame()
        bar.setFixedWidth(4)
        clr = event.color() if not event.completed else _C["text_dim"]
        bar.setStyleSheet(
            f"background:{clr}; border-radius:2px 0 0 2px; border:none; min-height:0;"
        )
        outer.addWidget(bar)

        # Icon
        icon_lbl = _label(event.icon(), "base")
        icon_lbl.setFixedWidth(28)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(icon_lbl)

        # Text block
        txt = QVBoxLayout()
        txt.setContentsMargins(4, 4, 4, 4)
        txt.setSpacing(1)

        title_color  = _C["text_dim"] if event.completed else _C["text_hi"]
        title_weight = "400" if event.completed else "500"
        title_style  = "line-through " if event.completed else ""
        title_lbl = QLabel(event.title)
        title_lbl.setStyleSheet(
            f"color:{title_color}; font-size:{_FS['base']}; font-weight:{title_weight};"
            f" text-decoration:{title_style}; background:transparent; border:none;"
        )
        title_lbl.setMaximumWidth(9999)
        txt.addWidget(title_lbl)

        meta_parts = []
        if show_date and event.event_date:
            try:
                d = date.fromisoformat(event.event_date)
                meta_parts.append(d.strftime("%a %d %b"))
            except ValueError:
                pass
        if event.display_time() != "All day":
            meta_parts.append(event.display_time())
        dur = event.display_duration()
        if dur:
            meta_parts.append(dur)
        if not event.auto_generated:
            meta_parts.append(event.session_type)
        if event.is_overdue() and not event.completed:
            meta_parts.insert(0, "⚠ OVERDUE")
        elif event.is_today() and show_date:
            meta_parts.insert(0, "Today")

        meta_lbl = _label(" · ".join(meta_parts), "xs", "text_lo")
        meta_lbl.setWordWrap(False)
        txt.addWidget(meta_lbl)

        outer.addLayout(txt, stretch=1)

        # Action buttons
        if not event.auto_generated:
            btn_check = QPushButton("✓" if not event.completed else "↩")
            btn_check.setFixedSize(26, 26)
            chk_color = _C["success"] if not event.completed else _C["text_lo"]
            btn_check.setStyleSheet(
                f"QPushButton{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
                f"border-radius:{_R['sm']}; color:{chk_color}; font-size:{_FS['base']}; font-weight:600;}}"
                f"QPushButton:hover{{background:{_C['bg_hover']}; border-color:{_C['border_hi']};}}"
            )
            btn_check.setToolTip("Mark complete" if not event.completed else "Reopen")
            btn_check.clicked.connect(lambda: self.complete_requested.emit(self._ev.id))
            outer.addWidget(btn_check)

        btn_edit = QPushButton("✎")
        btn_edit.setFixedSize(26, 26)
        btn_edit.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; color:{_C['text_lo']}; font-size:{_FS['base']};}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; color:{_C['accent_text']}; border-color:{_C['accent']};}}"
        )
        btn_edit.setToolTip("Edit event")
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self._ev.id))
        outer.addWidget(btn_edit)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(26, 26)
        btn_del.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; color:{_C['text_dim']}; font-size:{_FS['sm']};}}"
            f"QPushButton:hover{{background:{_C['danger_lo']}; color:{_C['danger']}; border-color:{_C['danger']};}}"
        )
        btn_del.setToolTip("Delete event")
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self._ev.id))
        outer.addWidget(btn_del)


# ── Event Dialog ──────────────────────────────────────────────────────────────

class _EventDialog(QDialog):
    """Add / edit a CalendarEvent. Progressive disclosure: basic → advanced."""

    def __init__(self, service, prefill: dict | None = None, event_id: int | None = None,
                 parent=None):
        super().__init__(parent)
        self._service  = service
        self._event_id = event_id
        self._advanced_visible = False
        self.setWindowTitle("Edit Event" if event_id else "New Event")
        self.setMinimumWidth(440)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog{{background:{_C['bg_base']}; color:{_C['text_hi']};}}"
            f"QLabel{{color:{_C['text_mid']}; font-size:{_FS['base']}; background:transparent; border:none;}}"
            f"QLineEdit, QComboBox, QSpinBox, QTextEdit, QDateEdit, QTimeEdit{{"
            f"  background:{_C['bg_input']}; color:{_C['text_hi']}; border:1px solid {_C['border']};"
            f"  border-radius:{_R['sm']}; padding:4px 6px; font-size:{_FS['base']};}}"
            f"QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus,"
            f"QDateEdit:focus, QTimeEdit:focus{{"
            f"  border-color:{_C['accent']};}}"
            f"QComboBox::drop-down{{border:none; width:18px;}}"
            f"QComboBox::down-arrow{{image:none; width:0; height:0;}}"
            f"QComboBox QAbstractItemView{{background:{_C['bg_raised']}; color:{_C['text_hi']};"
            f"  border:1px solid {_C['border']}; selection-background-color:{_C['accent']};}}"
            f"QCheckBox{{color:{_C['text_mid']}; font-size:{_FS['base']};}}"
            f"QCheckBox::indicator{{width:14px; height:14px; border:1px solid {_C['border']};"
            f"  border-radius:3px; background:{_C['bg_input']};}}"
            f"QCheckBox::indicator:checked{{background:{_C['accent']}; border-color:{_C['accent']};}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        # ── Title ─────────────────────────────────────────────────────────────
        root.addWidget(_label("Title", "sm", "text_lo"))
        self._title = QLineEdit()
        self._title.setPlaceholderText("e.g. Paint Space Marines squad")
        self._title.setFixedHeight(34)
        root.addWidget(self._title)

        # ── Date + Time row ───────────────────────────────────────────────────
        dt_row = QHBoxLayout()
        dt_row.setSpacing(10)

        date_col = QVBoxLayout()
        date_col.setSpacing(3)
        date_col.addWidget(_label("Date", "sm", "text_lo"))
        self._date = QDateEdit()
        self._date.setCalendarPopup(True)
        self._date.setFixedHeight(34)
        self._date.setDisplayFormat("dd MMM yyyy")
        date_col.addWidget(self._date)
        dt_row.addLayout(date_col, stretch=2)

        time_col = QVBoxLayout()
        time_col.setSpacing(6)
        time_col.addWidget(_label("Time (optional)", "sm", "text_lo"))
        self._time_check = QCheckBox("Set time")
        self._time = QTimeEdit()
        self._time.setDisplayFormat("HH:mm")
        self._time.setFixedHeight(34)
        self._time.setEnabled(False)
        self._time_check.toggled.connect(self._time.setEnabled)
        time_col.addWidget(self._time_check)
        time_col.addWidget(self._time)
        dt_row.addLayout(time_col, stretch=1)

        root.addLayout(dt_row)

        # ── Session type + Duration ───────────────────────────────────────────
        sd_row = QHBoxLayout()
        sd_row.setSpacing(10)

        type_col = QVBoxLayout()
        type_col.setSpacing(3)
        type_col.addWidget(_label("Session Type", "sm", "text_lo"))
        self._session_type = QComboBox()
        self._session_type.setFixedHeight(34)
        from .models import SESSION_TYPES
        for t in SESSION_TYPES:
            self._session_type.addItem(t)
        type_col.addWidget(self._session_type)
        sd_row.addLayout(type_col, stretch=2)

        dur_col = QVBoxLayout()
        dur_col.setSpacing(3)
        dur_col.addWidget(_label("Duration (min)", "sm", "text_lo"))
        self._duration = QSpinBox()
        self._duration.setRange(0, 1440)
        self._duration.setValue(60)
        self._duration.setSingleStep(15)
        self._duration.setFixedHeight(34)
        dur_col.addWidget(self._duration)
        sd_row.addLayout(dur_col, stretch=1)

        root.addLayout(sd_row)

        # ── Advanced toggle ───────────────────────────────────────────────────
        adv_btn = QPushButton("▸ Advanced options")
        adv_btn.setStyleSheet(
            f"QPushButton{{background:transparent; border:none; color:{_C['text_lo']};"
            f"font-size:{_FS['sm']}; text-align:left; padding:0;}}"
            f"QPushButton:hover{{color:{_C['accent_text']};}}"
        )
        adv_btn.clicked.connect(lambda: self._toggle_advanced(adv_btn))
        root.addWidget(adv_btn)

        # ── Advanced panel ────────────────────────────────────────────────────
        self._adv_panel = QWidget()
        self._adv_panel.setVisible(False)
        adv_layout = QVBoxLayout(self._adv_panel)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(10)

        # Priority
        pri_row = QHBoxLayout()
        pri_row.setSpacing(10)
        pri_col = QVBoxLayout()
        pri_col.setSpacing(3)
        pri_col.addWidget(_label("Priority", "sm", "text_lo"))
        self._priority = QComboBox()
        self._priority.setFixedHeight(34)
        self._priority.addItems(["Normal", "Important", "Urgent"])
        pri_col.addWidget(self._priority)
        pri_row.addLayout(pri_col)

        rem_col = QVBoxLayout()
        rem_col.setSpacing(3)
        rem_col.addWidget(_label("Reminder", "sm", "text_lo"))
        self._reminder = QComboBox()
        self._reminder.setFixedHeight(34)
        from .models import REMINDER_OPTIONS
        for mins, lbl in REMINDER_OPTIONS.items():
            self._reminder.addItem(lbl, mins)
        rem_col.addWidget(self._reminder)
        pri_row.addLayout(rem_col)
        adv_layout.addLayout(pri_row)

        # Tags
        adv_layout.addWidget(_label("Tags (comma-separated)", "sm", "text_lo"))
        self._tags = QLineEdit()
        self._tags.setPlaceholderText("space marines, warhammer, imperium")
        self._tags.setFixedHeight(34)
        adv_layout.addWidget(self._tags)

        # Recurrence
        adv_layout.addWidget(_label("Recurrence", "sm", "text_lo"))
        self._recurrence = QComboBox()
        self._recurrence.setFixedHeight(34)
        from .models import RECURRENCE_LABELS
        for key, lbl in RECURRENCE_LABELS.items():
            self._recurrence.addItem(lbl, key)
        adv_layout.addWidget(self._recurrence)

        # Notes
        adv_layout.addWidget(_label("Notes", "sm", "text_lo"))
        self._notes = QTextEdit()
        self._notes.setFixedHeight(72)
        self._notes.setPlaceholderText("Optional notes or details…")
        adv_layout.addWidget(self._notes)

        root.addWidget(self._adv_panel)
        root.addWidget(_hline())

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setText(
            "Save Changes" if event_id else "Add Event"
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setStyleSheet(
            f"QPushButton{{background:{_C['accent']}; color:#fff; border:none;"
            f"border-radius:{_R['sm']}; padding:6px 18px; font-size:{_FS['base']}; font-weight:600;}}"
            f"QPushButton:hover{{background:{_C['accent_hi']};}}"
        )
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; color:{_C['text_mid']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']}; padding:6px 14px;"
            f"font-size:{_FS['base']};}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; border-color:{_C['border_hi']};}}"
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        # ── Pre-fill ──────────────────────────────────────────────────────────
        self._populate(prefill or {})

    def _toggle_advanced(self, btn: QPushButton):
        self._advanced_visible = not self._advanced_visible
        self._adv_panel.setVisible(self._advanced_visible)
        arrow = "▾" if self._advanced_visible else "▸"
        btn.setText(f"{arrow} Advanced options")
        self.adjustSize()

    def _populate(self, data: dict):
        if data.get("title"):
            self._title.setText(data["title"])
        today = date.today()
        ev_date = data.get("event_date", today.isoformat())
        try:
            d = date.fromisoformat(ev_date)
            self._date.setDate(QDate(d.year, d.month, d.day))
        except (ValueError, TypeError):
            self._date.setDate(QDate(today.year, today.month, today.day))

        if data.get("time_start"):
            try:
                h, m = map(int, data["time_start"].split(":"))
                from PySide6.QtCore import QTime
                self._time.setTime(QTime(h, m))
                self._time_check.setChecked(True)
            except (ValueError, AttributeError):
                pass
        else:
            from PySide6.QtCore import QTime
            self._time.setTime(QTime(18, 0))

        if data.get("session_type"):
            idx = self._session_type.findText(data["session_type"])
            if idx >= 0:
                self._session_type.setCurrentIndex(idx)

        if data.get("duration_minutes") is not None:
            self._duration.setValue(int(data["duration_minutes"]))

        if data.get("notes"):
            self._notes.setPlainText(data["notes"])
            if not self._advanced_visible:
                self._adv_panel.setVisible(True)
                self._advanced_visible = True

        pri = data.get("priority", 3)
        self._priority.setCurrentIndex(3 - max(1, min(3, int(pri))))

        if data.get("tags"):
            self._tags.setText(data["tags"])

    def _save(self):
        title = self._title.text().strip()
        if not title:
            self._title.setStyleSheet(
                self._title.styleSheet() + f" border-color:{_C['danger']};"
            )
            self._title.setFocus()
            return

        qd      = self._date.date()
        ev_date = date(qd.year(), qd.month(), qd.day()).isoformat()
        time_start = ""
        if self._time_check.isChecked():
            qt = self._time.time()
            time_start = f"{qt.hour():02d}:{qt.minute():02d}"

        stype    = self._session_type.currentText()
        dur      = self._duration.value()
        pri_text = self._priority.currentText()
        priority = int(pri_text[0])
        rec_data = self._recurrence.currentData()
        is_rec   = rec_data != "none"

        kwargs = dict(
            title            = title,
            session_type     = stype,
            event_date       = ev_date,
            time_start       = time_start,
            duration_minutes = dur,
            notes            = self._notes.toPlainText().strip(),
            priority         = priority,
            reminder_minutes = self._reminder.currentData() or 0,
            tags             = self._tags.text().strip(),
            is_recurring     = is_rec,
            recurrence_rule  = rec_data,
        )

        try:
            if self._event_id:
                self._service.update_event(self._event_id, **kwargs)
            else:
                self._service.add_event(**kwargs)
            self.accept()
        except Exception as e:
            log.error(f"[CALENDAR V2 DIALOG] Save error: {e}")


# ── Today View ────────────────────────────────────────────────────────────────

class _TodayView(QWidget):
    """Hero view: Overdue → Planned Today → This Week → Activity Today."""

    refresh_needed = Signal()

    def __init__(self, service, context, parent=None):
        super().__init__(parent)
        self._service = service
        self._context = context
        self.setStyleSheet(f"background:{_C['bg_base']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{_C['bg_base']}; border:none;}}"
            f"QScrollBar:vertical{{background:{_C['bg_base']}; width:6px; margin:0;}}"
            f"QScrollBar::handle:vertical{{background:{_C['border_hi']}; border-radius:3px;}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{{height:0;}}"
        )
        self._inner = QWidget()
        self._inner.setStyleSheet(f"background:{_C['bg_base']};")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(16, 12, 16, 20)
        self._inner_layout.setSpacing(0)

        scroll.setWidget(self._inner)
        root.addWidget(scroll)

    def refresh(self):
        # Clear old contents
        while self._inner_layout.count():
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        il = self._inner_layout

        # ── Hero date header ──────────────────────────────────────────────────
        today = date.today()
        today_str = today.strftime("%A, %d %B %Y")
        hdr = _label(f"📅  {today_str}", "xl", "text_hi", bold=True)
        hdr.setContentsMargins(0, 0, 0, 8)
        il.addWidget(hdr)
        il.addWidget(_hline())

        # ── Overdue ───────────────────────────────────────────────────────────
        try:
            overdue = self._service.get_overdue()
        except Exception:
            overdue = []
        if overdue:
            sec = _SectionHeader("OVERDUE", "⚠")
            sec.set_count(len(overdue))
            sec._title_lbl.setStyleSheet(
                sec._title_lbl.styleSheet().replace(_C["text_lo"], _C["overdue"])
            )
            il.addWidget(sec)
            for ev in overdue:
                row = _EventRow(ev, show_date=True)
                self._connect_row(row)
                il.addWidget(row)
            il.addSpacing(6)

        # ── Planned Today ─────────────────────────────────────────────────────
        try:
            planned = self._service.get_today_planned()
        except Exception:
            planned = []
        sec_p = _SectionHeader("PLANNED TODAY", "📋")
        sec_p.set_count(len(planned))
        il.addWidget(sec_p)
        if planned:
            for ev in planned:
                row = _EventRow(ev)
                self._connect_row(row)
                il.addWidget(row)
        else:
            il.addWidget(_label("  Nothing planned for today — enjoy the calm.", "sm", "text_dim"))
        il.addSpacing(6)

        # ── This Week ─────────────────────────────────────────────────────────
        try:
            week_events = self._service.get_upcoming_week()
        except Exception:
            week_events = []

        # Group by date
        from collections import defaultdict
        by_date: dict[str, list] = defaultdict(list)
        for ev in week_events:
            by_date[ev.event_date].append(ev)

        if by_date:
            sec_w = _SectionHeader("COMING UP THIS WEEK", "📆")
            sec_w.set_count(len(week_events))
            il.addWidget(sec_w)
            for d_iso in sorted(by_date):
                try:
                    d = date.fromisoformat(d_iso)
                    day_lbl = _label(d.strftime("  %A  ·  %d %b"), "xs", "text_lo")
                    day_lbl.setContentsMargins(0, 4, 0, 1)
                    il.addWidget(day_lbl)
                except ValueError:
                    pass
                for ev in by_date[d_iso]:
                    row = _EventRow(ev)
                    self._connect_row(row)
                    il.addWidget(row)
            il.addSpacing(6)

        # ── Activity Today ────────────────────────────────────────────────────
        try:
            activity = self._service.get_today_activity()
        except Exception:
            activity = []
        if activity:
            sec_a = _SectionHeader("ACTIVITY TODAY", "📝")
            sec_a.set_count(len(activity))
            il.addWidget(sec_a)
            for ev in activity:
                row = _EventRow(ev)
                self._connect_row(row)
                il.addWidget(row)
            il.addSpacing(6)

        il.addStretch()

    def _connect_row(self, row: _EventRow):
        row.complete_requested.connect(self._toggle_complete)
        row.edit_requested.connect(self._edit_event)
        row.delete_requested.connect(self._delete_event)

    def _toggle_complete(self, event_id: int):
        ev = self._service.get_event(event_id)
        if ev:
            if ev.completed:
                self._service.uncomplete_event(event_id)
            else:
                self._service.complete_event(event_id)
        self.refresh_needed.emit()

    def _edit_event(self, event_id: int):
        ev = self._service.get_event(event_id)
        if not ev:
            return
        data = {k: getattr(ev, k) for k in (
            "title", "session_type", "event_date", "time_start", "duration_minutes",
            "notes", "priority", "tags", "is_recurring", "recurrence_rule",
        )}
        dlg = _EventDialog(self._service, prefill=data, event_id=event_id, parent=self)
        if dlg.exec():
            self.refresh_needed.emit()

    def _delete_event(self, event_id: int):
        self._service.delete_event(event_id)
        self.refresh_needed.emit()


# ── Agenda View ───────────────────────────────────────────────────────────────

class _AgendaView(QWidget):
    """Scrollable chronological list of upcoming events, grouped by date."""

    refresh_needed = Signal()

    def __init__(self, service, context, parent=None):
        super().__init__(parent)
        self._service = service
        self._context = context
        self.setStyleSheet(f"background:{_C['bg_base']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{_C['bg_base']}; border:none;}}"
            f"QScrollBar:vertical{{background:{_C['bg_base']}; width:6px; margin:0;}}"
            f"QScrollBar::handle:vertical{{background:{_C['border_hi']}; border-radius:3px;}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{{height:0;}}"
        )
        self._inner = QWidget()
        self._inner.setStyleSheet(f"background:{_C['bg_base']};")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(16, 12, 16, 20)
        self._inner_layout.setSpacing(0)
        scroll.setWidget(self._inner)
        root.addWidget(scroll)

    def refresh(self):
        while self._inner_layout.count():
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        il = self._inner_layout

        try:
            events = self._service.get_upcoming(days=60)
        except Exception:
            events = []

        # Also add overdue
        try:
            overdue = self._service.get_overdue()
        except Exception:
            overdue = []

        from collections import defaultdict
        by_date: dict[str, list] = defaultdict(list)
        for ev in overdue:
            by_date[ev.event_date].append(ev)
        for ev in events:
            by_date[ev.event_date].append(ev)

        if not by_date:
            il.addSpacing(20)
            il.addWidget(_label("No upcoming events.", "base", "text_lo"))
            il.addStretch()
            return

        today_iso = date.today().isoformat()
        for d_iso in sorted(by_date):
            try:
                d = date.fromisoformat(d_iso)
            except ValueError:
                continue

            # Date header
            if d_iso < today_iso:
                label_text = d.strftime("⚠  %A, %d %B")
                color = _C["overdue"]
            elif d_iso == today_iso:
                label_text = "Today — " + d.strftime("%A %d %B")
                color = _C["accent_text"]
            else:
                days_ahead = (d - date.today()).days
                suffix = f"  (+{days_ahead}d)"
                label_text = d.strftime("%A, %d %B") + suffix
                color = _C["text_mid"]

            date_hdr = QLabel(label_text)
            date_hdr.setContentsMargins(0, 10, 0, 4)
            date_hdr.setStyleSheet(
                f"color:{color}; font-size:{_FS['sm']}; font-weight:600;"
                f" background:transparent; border:none;"
            )
            il.addWidget(date_hdr)

            for ev in by_date[d_iso]:
                row = _EventRow(ev)
                row.complete_requested.connect(self._toggle_complete)
                row.edit_requested.connect(self._edit_event)
                row.delete_requested.connect(self._delete_event)
                il.addWidget(row)

        il.addStretch()

    def _toggle_complete(self, event_id: int):
        ev = self._service.get_event(event_id)
        if ev:
            if ev.completed:
                self._service.uncomplete_event(event_id)
            else:
                self._service.complete_event(event_id)
        self.refresh_needed.emit()

    def _edit_event(self, event_id: int):
        ev = self._service.get_event(event_id)
        if not ev:
            return
        data = {k: getattr(ev, k) for k in (
            "title", "session_type", "event_date", "time_start", "duration_minutes",
            "notes", "priority", "tags", "is_recurring", "recurrence_rule",
        )}
        dlg = _EventDialog(self._service, prefill=data, event_id=event_id, parent=self)
        if dlg.exec():
            self.refresh_needed.emit()

    def _delete_event(self, event_id: int):
        self._service.delete_event(event_id)
        self.refresh_needed.emit()


# ── Week View ─────────────────────────────────────────────────────────────────

class _WeekView(QWidget):
    """7-column week view with stacked event chips per day."""

    refresh_needed = Signal()

    def __init__(self, service, context, parent=None):
        super().__init__(parent)
        self._service  = service
        self._context  = context
        self._ref_date = date.today()
        self.setStyleSheet(f"background:{_C['bg_base']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Nav row
        nav = QWidget()
        nav.setFixedHeight(40)
        nav.setStyleSheet(f"background:{_C['bg_card']}; border-bottom:1px solid {_C['border']};")
        nav_row = QHBoxLayout(nav)
        nav_row.setContentsMargins(12, 4, 12, 4)
        nav_row.setSpacing(8)

        self._prev_btn = self._nav_btn("◀")
        self._prev_btn.clicked.connect(self._prev_week)
        nav_row.addWidget(self._prev_btn)

        self._week_lbl = _label("", "base", "text_hi", bold=True)
        nav_row.addWidget(self._week_lbl, stretch=1)

        self._today_btn = QPushButton("Today")
        self._today_btn.setFixedHeight(26)
        self._today_btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; color:{_C['text_mid']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"font-size:{_FS['sm']}; padding:0 10px;}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; border-color:{_C['accent']};"
            f"color:{_C['accent_text']};}}"
        )
        self._today_btn.clicked.connect(self._goto_today)
        nav_row.addWidget(self._today_btn)

        self._next_btn = self._nav_btn("▶")
        self._next_btn.clicked.connect(self._next_week)
        nav_row.addWidget(self._next_btn)

        root.addWidget(nav)

        # Columns container (scrollable vertically)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{_C['bg_base']}; border:none;}}"
            f"QScrollBar:vertical{{background:{_C['bg_base']}; width:6px; margin:0;}}"
            f"QScrollBar::handle:vertical{{background:{_C['border_hi']}; border-radius:3px;}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{{height:0;}}"
        )
        self._cols_widget = QWidget()
        self._cols_widget.setStyleSheet(f"background:{_C['bg_base']};")
        self._cols_layout = QHBoxLayout(self._cols_widget)
        self._cols_layout.setContentsMargins(8, 8, 8, 8)
        self._cols_layout.setSpacing(6)
        scroll.setWidget(self._cols_widget)
        root.addWidget(scroll)

    def _nav_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; color:{_C['text_mid']}; font-size:{_FS['sm']};}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; border-color:{_C['border_hi']}; color:{_C['text_hi']};}}"
        )
        return btn

    def _prev_week(self):
        self._ref_date -= timedelta(weeks=1)
        self.refresh()

    def _next_week(self):
        self._ref_date += timedelta(weeks=1)
        self.refresh()

    def _goto_today(self):
        self._ref_date = date.today()
        self.refresh()

    def refresh(self):
        # Find Monday of the week
        monday = self._ref_date - timedelta(days=self._ref_date.weekday())
        sunday = monday + timedelta(days=6)
        iso_cal = monday.isocalendar()
        self._week_lbl.setText(
            f"Week {iso_cal.week}  ·  {monday.strftime('%d %b')} – {sunday.strftime('%d %b %Y')}"
        )

        # Fetch events
        try:
            events = self._service.get_events_for_week(iso_cal.year, iso_cal.week)
        except Exception:
            events = []

        from collections import defaultdict
        by_date: dict[str, list] = defaultdict(list)
        for ev in events:
            by_date[ev.event_date].append(ev)

        # Rebuild columns
        while self._cols_layout.count():
            item = self._cols_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        today_iso = date.today().isoformat()
        for i in range(7):
            d = monday + timedelta(days=i)
            d_iso = d.isoformat()
            is_today = (d_iso == today_iso)

            col = QFrame()
            col.setStyleSheet(
                f"QFrame{{background:{'#1e2d3d' if is_today else _C['bg_card']};"
                f"border:1px solid {'#1a4a7a' if is_today else _C['border']};"
                f"border-radius:{_R['base']};}}"
            )
            col_layout = QVBoxLayout(col)
            col_layout.setContentsMargins(6, 6, 6, 6)
            col_layout.setSpacing(3)

            # Day header
            day_hdr = QLabel(f"{_DAY_NAMES[i]}\n{d.day}")
            day_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_hdr.setStyleSheet(
                f"color:{_C['accent_text'] if is_today else _C['text_mid']};"
                f"font-size:{_FS['sm']}; font-weight:{'600' if is_today else '400'};"
                f"background:transparent; border:none; padding:2px 0;"
            )
            col_layout.addWidget(day_hdr)
            col_layout.addWidget(_hline())

            evs = by_date.get(d_iso, [])
            for ev in evs[:8]:  # Cap at 8 chips per column
                chip = QLabel(f"{ev.icon()} {ev.title}")
                chip.setWordWrap(True)
                chip.setMinimumHeight(22)
                chip.setStyleSheet(
                    f"background:{_rgba(ev.color(), 0.12)}; color:{ev.color()};"
                    f"border:1px solid {_rgba(ev.color(), 0.35)};"
                    f"border-radius:{_R['xs']}; font-size:{_FS['xs']}; padding:2px 5px;"
                )
                col_layout.addWidget(chip)

            if len(evs) > 8:
                more = _label(f"+{len(evs)-8} more", "xs", "text_dim")
                col_layout.addWidget(more)
            elif not evs:
                col_layout.addWidget(_label("—", "xs", "text_dim"))

            col_layout.addStretch()
            self._cols_layout.addWidget(col, stretch=1)


# ── Month View ────────────────────────────────────────────────────────────────

class _MonthView(QWidget):
    """Classic 6×7 month grid with colored event chips.  Click a day → side panel."""

    refresh_needed = Signal()

    def __init__(self, service, context, parent=None):
        super().__init__(parent)
        self._service   = service
        self._context   = context
        self._year      = date.today().year
        self._month     = date.today().month
        self._selected  = date.today().isoformat()
        self.setStyleSheet(f"background:{_C['bg_base']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Nav
        nav = QWidget()
        nav.setFixedHeight(42)
        nav.setStyleSheet(f"background:{_C['bg_card']}; border-bottom:1px solid {_C['border']};")
        nav_row = QHBoxLayout(nav)
        nav_row.setContentsMargins(12, 4, 12, 4)

        self._prev_btn = self._nav_btn("◀")
        self._prev_btn.clicked.connect(self._prev_month)
        nav_row.addWidget(self._prev_btn)

        self._month_lbl = _label("", "lg", "text_hi", bold=True)
        self._month_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self._month_lbl, stretch=1)

        today_btn = QPushButton("Today")
        today_btn.setFixedHeight(26)
        today_btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; color:{_C['text_mid']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"font-size:{_FS['sm']}; padding:0 10px;}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; border-color:{_C['accent']};"
            f"color:{_C['accent_text']};}}"
        )
        today_btn.clicked.connect(self._goto_today)
        nav_row.addWidget(today_btn)

        self._next_btn = self._nav_btn("▶")
        self._next_btn.clicked.connect(self._next_month)
        nav_row.addWidget(self._next_btn)
        root.addWidget(nav)

        # Split: grid (left) + side panel (right)
        split = QHBoxLayout()
        split.setContentsMargins(8, 8, 8, 8)
        split.setSpacing(8)

        # Grid panel
        self._grid_panel = QFrame()
        self._grid_panel.setStyleSheet(
            f"QFrame{{background:{_C['bg_card']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['base']};}}"
        )
        self._grid_layout = QVBoxLayout(self._grid_panel)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)
        self._grid_layout.setSpacing(0)
        split.addWidget(self._grid_panel, stretch=3)

        # Side panel: events for selected day
        self._side_panel = QFrame()
        self._side_panel.setMinimumWidth(220)
        self._side_panel.setMaximumWidth(300)
        self._side_panel.setStyleSheet(
            f"QFrame{{background:{_C['bg_card']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['base']};}}"
        )
        side_v = QVBoxLayout(self._side_panel)
        side_v.setContentsMargins(10, 10, 10, 10)
        side_v.setSpacing(4)

        self._side_date_lbl = _label("", "base", "text_hi", bold=True)
        side_v.addWidget(self._side_date_lbl)
        side_v.addWidget(_hline())

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setStyleSheet(
            f"QScrollArea{{background:transparent; border:none;}}"
            f"QScrollBar:vertical{{background:transparent; width:4px; margin:0;}}"
            f"QScrollBar::handle:vertical{{background:{_C['border_hi']}; border-radius:2px;}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{{height:0;}}"
        )
        self._side_inner = QWidget()
        self._side_inner.setStyleSheet("background:transparent;")
        self._side_inner_layout = QVBoxLayout(self._side_inner)
        self._side_inner_layout.setContentsMargins(0, 0, 0, 0)
        self._side_inner_layout.setSpacing(3)
        side_scroll.setWidget(self._side_inner)
        side_v.addWidget(side_scroll)
        split.addWidget(self._side_panel, stretch=1)

        container = QWidget()
        container.setLayout(split)
        root.addWidget(container)
        root.setStretchFactor(container, 1)

    def _nav_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; color:{_C['text_mid']}; font-size:{_FS['sm']};}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; border-color:{_C['border_hi']};"
            f"color:{_C['text_hi']};}}"
        )
        return btn

    def _prev_month(self):
        if self._month == 1:
            self._year -= 1
            self._month = 12
        else:
            self._month -= 1
        self.refresh()

    def _next_month(self):
        if self._month == 12:
            self._year += 1
            self._month = 1
        else:
            self._month += 1
        self.refresh()

    def _goto_today(self):
        self._year  = date.today().year
        self._month = date.today().month
        self._selected = date.today().isoformat()
        self.refresh()

    def _day_clicked(self, d_iso: str):
        self._selected = d_iso
        self._refresh_side()
        # Redraw grid to update selected highlight without full refresh
        self._rebuild_grid_cells()

    def refresh(self):
        self._month_lbl.setText(f"{_MONTH_NAMES[self._month]}  {self._year}")
        # Rebuild grid
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Fetch events for the displayed range
        try:
            self._month_events = self._service.get_events_for_month(self._year, self._month)
        except Exception:
            self._month_events = []

        # Day-of-week headers
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(2)
        for day_name in _DAY_NAMES:
            lbl = _label(day_name, "xs", "text_dim")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(20)
            hdr_row.addWidget(lbl)
        hdr_widget = QWidget()
        hdr_widget.setLayout(hdr_row)
        hdr_widget.setStyleSheet("background:transparent;")
        self._grid_layout.addWidget(hdr_widget)

        self._grid_cells_layout = QGridLayout()
        self._grid_cells_layout.setSpacing(3)
        self._grid_cells_container = QWidget()
        self._grid_cells_container.setLayout(self._grid_cells_layout)
        self._grid_cells_container.setStyleSheet("background:transparent;")
        self._grid_layout.addWidget(self._grid_cells_container)
        self._grid_layout.addStretch()

        self._rebuild_grid_cells()
        self._refresh_side()

    def _rebuild_grid_cells(self):
        layout = self._grid_cells_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from collections import defaultdict
        by_date: dict[str, list] = defaultdict(list)
        for ev in self._month_events:
            by_date[ev.event_date].append(ev)

        first   = date(self._year, self._month, 1)
        start   = first - timedelta(days=first.weekday())
        today   = date.today()
        today_iso = today.isoformat()

        for cell_idx in range(42):
            d       = start + timedelta(days=cell_idx)
            d_iso   = d.isoformat()
            in_month = (d.month == self._month)
            is_today = (d_iso == today_iso)
            is_sel   = (d_iso == self._selected)
            evs      = by_date.get(d_iso, [])

            # ── Cell frame ────────────────────────────────────────────────────
            cell = QFrame()
            if is_sel:
                bg     = _rgba(_C["accent"], 0.14)
                border = _rgba(_C["accent"], 0.55)
            elif is_today:
                bg     = _rgba(_C["accent"], 0.07)
                border = _rgba(_C["accent"], 0.30)
            elif not in_month:
                bg     = _C["bg_base"]
                border = _C["border_lo"]
            else:
                bg     = _C["bg_raised"]
                border = _C["border"]

            cell.setStyleSheet(
                f"QFrame{{background:{bg}; border:1px solid {border};"
                f"border-radius:{_R['xs']};}}"
            )
            cell.setMinimumHeight(72)

            cell_v = QVBoxLayout(cell)
            cell_v.setContentsMargins(4, 3, 4, 3)
            cell_v.setSpacing(2)

            # ── Day number ────────────────────────────────────────────────────
            dn_row = QHBoxLayout()
            dn_row.setContentsMargins(0, 0, 0, 0)
            dn_row.setSpacing(0)
            dn_row.addStretch()

            if is_today:
                # Circle badge for today
                badge = QLabel(str(d.day))
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge.setFixedSize(20, 20)
                badge.setStyleSheet(
                    f"background:{_C['accent']}; color:#fff; font-size:9px;"
                    f"font-weight:700; border-radius:10px; border:none;"
                )
                dn_row.addWidget(badge)
            else:
                dn_color = _C["text_hi"] if in_month else _C["text_dim"]
                dn = QLabel(str(d.day))
                dn.setStyleSheet(
                    f"color:{dn_color}; font-size:{_FS['xs']};"
                    f"font-weight:{'500' if in_month else '400'};"
                    f"background:transparent; border:none;"
                )
                dn_row.addWidget(dn)

            cell_v.addLayout(dn_row)

            # ── Event rows (max 3) — dot + title ──────────────────────────────
            text_color = _C["text_mid"] if in_month else _C["text_dim"]
            for ev in evs[:3]:
                ev_row = QWidget()
                ev_row.setFixedHeight(15)
                ev_row.setStyleSheet("background:transparent;")
                ev_h = QHBoxLayout(ev_row)
                ev_h.setContentsMargins(0, 0, 0, 0)
                ev_h.setSpacing(4)

                dot = QFrame()
                dot.setFixedSize(6, 6)
                dot.setStyleSheet(
                    f"background:{ev.color()}; border-radius:3px; border:none;"
                )
                ev_h.addWidget(dot)

                t = QLabel(ev.title)
                t.setStyleSheet(
                    f"color:{text_color}; font-size:9px; background:transparent; border:none;"
                )
                t.setSizePolicy(
                    QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
                )
                ev_h.addWidget(t, stretch=1)
                cell_v.addWidget(ev_row)

            # ── Overflow count ────────────────────────────────────────────────
            if len(evs) > 3:
                more_lbl = QLabel(f"+{len(evs) - 3} more")
                more_lbl.setStyleSheet(
                    f"color:{_C['text_dim']}; font-size:8px; background:transparent; border:none;"
                )
                cell_v.addWidget(more_lbl)

            cell_v.addStretch()

            row = cell_idx // 7
            col = cell_idx % 7
            layout.addWidget(cell, row, col)

            # Click to select
            d_copy = d_iso

            def _make_click(iso):
                def _click(ev=None):
                    self._day_clicked(iso)
                return _click

            cell.mousePressEvent = _make_click(d_copy)

    def _refresh_side(self):
        while self._side_inner_layout.count():
            item = self._side_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            d     = date.fromisoformat(self._selected)
            label = d.strftime("%A, %d %B %Y")
        except (ValueError, TypeError):
            label = "Select a day"

        self._side_date_lbl.setText(label)

        try:
            evs = self._service.get_events_for_date(date.fromisoformat(self._selected))
        except Exception:
            evs = []

        if not evs:
            self._side_inner_layout.addWidget(_label("No events.", "sm", "text_dim"))
        else:
            for ev in evs:
                row = _EventRow(ev)
                row.complete_requested.connect(self._toggle_complete)
                row.edit_requested.connect(self._edit_event)
                row.delete_requested.connect(self._delete_event)
                self._side_inner_layout.addWidget(row)

        self._side_inner_layout.addStretch()

    def _toggle_complete(self, event_id: int):
        ev = self._service.get_event(event_id)
        if ev:
            if ev.completed:
                self._service.uncomplete_event(event_id)
            else:
                self._service.complete_event(event_id)
        self.refresh()

    def _edit_event(self, event_id: int):
        ev = self._service.get_event(event_id)
        if not ev:
            return
        data = {k: getattr(ev, k) for k in (
            "title", "session_type", "event_date", "time_start", "duration_minutes",
            "notes", "priority", "tags", "is_recurring", "recurrence_rule",
        )}
        dlg = _EventDialog(self._service, prefill=data, event_id=event_id, parent=self)
        if dlg.exec():
            self.refresh()

    def _delete_event(self, event_id: int):
        self._service.delete_event(event_id)
        self.refresh()


# ── Stats strip ───────────────────────────────────────────────────────────────

class _StatsStrip(QFrame):
    """Compact fixed-height stat bar: Today | Overdue | This Week | Upcoming."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet(
            f"QFrame{{background:{_C['bg_card']}; border-bottom:1px solid {_C['border']};}}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(0)
        self._cells: list[tuple[QLabel, QLabel]] = []
        for _ in range(4):
            cell = QVBoxLayout()
            cell.setSpacing(1)
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"color:{_C['text_hi']}; font-size:{_FS['xl']}; font-weight:700;"
                f"background:transparent; border:none;"
            )
            lbl = QLabel("—")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color:{_C['text_dim']}; font-size:{_FS['xs']}; font-weight:400;"
                f"background:transparent; border:none;"
            )
            cell.addWidget(val)
            cell.addWidget(lbl)
            cw = QWidget()
            cw.setStyleSheet("background:transparent;")
            cw.setLayout(cell)
            row.addWidget(cw, stretch=1)
            self._cells.append((val, lbl))

            if _ < 3:
                div = QFrame()
                div.setFrameShape(QFrame.Shape.VLine)
                div.setStyleSheet(f"color:{_C['border']}; max-width:1px; background:{_C['border']};")
                row.addWidget(div)

        self._cells[0][1].setText("TODAY")
        self._cells[1][1].setText("OVERDUE")
        self._cells[2][1].setText("THIS WEEK")
        self._cells[3][1].setText("UPCOMING 30D")

    def update_stats(self, stats: dict):
        colors = [_C["accent_text"], _C["overdue"], _C["text_hi"], _C["text_mid"]]
        values = [
            stats.get("today",    0),
            stats.get("overdue",  0),
            stats.get("week",     0),
            stats.get("upcoming", 0),
        ]
        for i, (v, l) in enumerate(self._cells):
            n = values[i]
            v.setText(str(n))
            c = _C["overdue"] if (i == 1 and n > 0) else colors[i]
            v.setStyleSheet(v.styleSheet().split("color:")[0] + f"color:{c}; " + "font-size:"
                            + v.styleSheet().split("font-size:")[1])


# ── Main CalendarV2UI ─────────────────────────────────────────────────────────

class CalendarV2UI(QWidget):
    """Calendar 2.0 — main container widget."""

    def __init__(self, context, service, parent=None):
        super().__init__(parent)
        self._context = context
        self._service = service
        self._active_view = 0   # 0=Today 1=Week 2=Month 3=Agenda
        self._search_visible = False

        self.setStyleSheet(f"background:{_C['bg_base']}; color:{_C['text_hi']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_quick_add_bar())
        root.addWidget(self._build_stats_strip())
        root.addWidget(self._build_views(), stretch=1)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(
            f"background:{_C['bg_card']}; border-bottom:1px solid {_C['border']};"
        )
        row = QHBoxLayout(hdr)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(10)

        # Title
        title = _label("📅  Calendar 2.0", "lg", "text_hi", bold=True)
        row.addWidget(title)
        row.addStretch()

        # View switcher
        views = [("Today", 0), ("Week", 1), ("Month", 2), ("Agenda", 3)]
        self._view_btns: list[QPushButton] = []
        for name, idx in views:
            btn = QPushButton(name)
            btn.setFixedHeight(30)
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.setStyleSheet(self._view_btn_style(idx == 0))
            btn.clicked.connect(lambda checked, i=idx, b=btn: self._switch_view(i))
            row.addWidget(btn)
            self._view_btns.append(btn)

        row.addSpacing(12)

        # Search toggle
        self._search_btn = QPushButton("🔍")
        self._search_btn.setFixedSize(30, 30)
        self._search_btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']}; border:1px solid {_C['border']};"
            f"border-radius:{_R['sm']}; color:{_C['text_lo']}; font-size:{_FS['base']};}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; color:{_C['text_hi']};"
            f"border-color:{_C['border_hi']};}}"
        )
        self._search_btn.clicked.connect(self._toggle_search)
        row.addWidget(self._search_btn)

        # Add event button
        add_btn = QPushButton("+ Add Event")
        add_btn.setFixedHeight(30)
        add_btn.setStyleSheet(
            f"QPushButton{{background:{_C['accent']}; color:#fff; border:none;"
            f"border-radius:{_R['sm']}; font-size:{_FS['base']}; font-weight:600;"
            f"padding:0 14px;}}"
            f"QPushButton:hover{{background:{_C['accent_hi']};}}"
        )
        add_btn.clicked.connect(lambda: self._open_add_dialog())
        row.addWidget(add_btn)

        return hdr

    def _view_btn_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton{{background:{_C['accent_lo']}; color:{_C['accent_text']};"
                f"border:1px solid {_C['accent']}; border-radius:{_R['sm']};"
                f"font-size:{_FS['sm']}; font-weight:600; padding:0 12px;}}"
                f"QPushButton:hover{{background:{_C['accent_lo']};}}"
            )
        return (
            f"QPushButton{{background:{_C['bg_raised']}; color:{_C['text_mid']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"font-size:{_FS['sm']}; padding:0 12px;}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; color:{_C['text_hi']};"
            f"border-color:{_C['border_hi']};}}"
        )

    # ── Quick Add ─────────────────────────────────────────────────────────────

    def _build_quick_add_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            f"background:{_C['bg_raised']}; border-bottom:1px solid {_C['border']};"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 6, 16, 6)
        row.setSpacing(8)

        hint = _label("⚡", "base", "text_dim")
        hint.setFixedWidth(20)
        row.addWidget(hint)

        self._quick_add = QLineEdit()
        self._quick_add.setPlaceholderText(
            "Quick add: \"Paint Marines tomorrow 2pm 2h\"  →  Enter to create"
        )
        self._quick_add.setFixedHeight(30)
        self._quick_add.setStyleSheet(
            f"QLineEdit{{background:{_C['bg_input']}; color:{_C['text_hi']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"font-size:{_FS['base']}; padding:0 10px;}}"
            f"QLineEdit:focus{{border-color:{_C['accent']};}}"
        )
        self._quick_add.returnPressed.connect(self._do_quick_add)
        row.addWidget(self._quick_add, stretch=1)

        qa_btn = QPushButton("Add")
        qa_btn.setFixedHeight(30)
        qa_btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_card']}; color:{_C['text_mid']};"
            f"border:1px solid {_C['border']}; border-radius:{_R['sm']};"
            f"font-size:{_FS['sm']}; padding:0 12px;}}"
            f"QPushButton:hover{{background:{_C['bg_hover']}; color:{_C['text_hi']};"
            f"border-color:{_C['accent']};}}"
        )
        qa_btn.clicked.connect(self._do_quick_add)
        row.addWidget(qa_btn)

        # Search bar (hidden by default)
        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText("Search events…")
        self._search_bar.setFixedHeight(30)
        self._search_bar.setVisible(False)
        self._search_bar.setStyleSheet(self._quick_add.styleSheet())
        self._search_bar.textChanged.connect(self._do_search)
        row.addWidget(self._search_bar)

        return bar

    # ── Stats strip ───────────────────────────────────────────────────────────

    def _build_stats_strip(self) -> QWidget:
        self._stats_strip = _StatsStrip()
        return self._stats_strip

    # ── Views stack ───────────────────────────────────────────────────────────

    def _build_views(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background:{_C['bg_base']};")

        self._today_view  = _TodayView(self._service, self._context)
        self._week_view   = _WeekView(self._service, self._context)
        self._month_view  = _MonthView(self._service, self._context)
        self._agenda_view = _AgendaView(self._service, self._context)

        self._today_view.refresh_needed.connect(self.refresh)
        self._agenda_view.refresh_needed.connect(self.refresh)

        self._stack.addWidget(self._today_view)   # 0
        self._stack.addWidget(self._week_view)    # 1
        self._stack.addWidget(self._month_view)   # 2
        self._stack.addWidget(self._agenda_view)  # 3

        return self._stack

    # ── Interaction helpers ───────────────────────────────────────────────────

    def _switch_view(self, idx: int):
        self._active_view = idx
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._view_btns):
            btn.setChecked(i == idx)
            btn.setStyleSheet(self._view_btn_style(i == idx))
        # Lazy-refresh the newly visible view
        views = [self._today_view, self._week_view, self._month_view, self._agenda_view]
        try:
            views[idx].refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2 UI] View refresh error: {e}")

    def _toggle_search(self):
        self._search_visible = not self._search_visible
        self._search_bar.setVisible(self._search_visible)
        self._quick_add.setVisible(not self._search_visible)
        if self._search_visible:
            self._search_bar.setFocus()
        else:
            self._search_bar.clear()

    def _do_search(self, query: str):
        if not query.strip():
            self.refresh()
            return
        try:
            results = self._service.search(query)
        except Exception:
            results = []
        # Show results in Today view (repurposed as search results display)
        self._switch_view(0)
        self._show_search_results(results, query)

    def _show_search_results(self, events: list, query: str):
        """Temporarily replace Today view content with search results."""
        while self._today_view._inner_layout.count():
            item = self._today_view._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        il = self._today_view._inner_layout
        hdr = _label(f'🔍  Results for "{query}"  ({len(events)} found)', "lg", "text_hi", bold=True)
        hdr.setContentsMargins(0, 0, 0, 8)
        il.addWidget(hdr)
        il.addWidget(_hline())

        if not events:
            il.addSpacing(12)
            il.addWidget(_label("No events match your search.", "base", "text_lo"))
        else:
            for ev in events:
                row = _EventRow(ev, show_date=True)
                self._today_view._connect_row(row)
                il.addWidget(row)
        il.addStretch()

    def _open_add_dialog(self, prefill: dict | None = None):
        dlg = _EventDialog(self._service, prefill=prefill, parent=self)
        if dlg.exec():
            self.refresh()

    def _do_quick_add(self):
        text = self._quick_add.text().strip()
        if not text:
            return
        parsed = _parse_quick_add(text)
        # Open dialog pre-filled — user confirms before saving
        dlg = _EventDialog(self._service, prefill=parsed, parent=self)
        if dlg.exec():
            self._quick_add.clear()
            self.refresh()

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self):
        """Refresh stats strip + the currently visible view."""
        try:
            stats = self._service.get_stats()
            self._stats_strip.update_stats(stats)
        except Exception as e:
            log.error(f"[CALENDAR V2 UI] Stats error: {e}")

        views = [self._today_view, self._week_view, self._month_view, self._agenda_view]
        try:
            views[self._active_view].refresh()
        except Exception as e:
            log.error(f"[CALENDAR V2 UI] Refresh error: {e}")
