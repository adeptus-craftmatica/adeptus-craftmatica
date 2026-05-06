"""Recent Activity feed — grouped by date with colour-coded action types."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy, QScrollArea,
)


# ── Action-type → accent colour ───────────────────────────────────────────────

_ADD_KEYWORDS    = {"added", "started", "created", "logged", "photo", "session"}
_REMOVE_KEYWORDS = {"removed", "deleted"}
_UPDATE_KEYWORDS = {"updated", "edited", "changed"}
_DONE_KEYWORDS   = {"completed", "milestone", "finished"}


def _action_color(description: str, tok: dict) -> str:
    low = description.lower()
    if any(k in low for k in _REMOVE_KEYWORDS):
        return tok.get("danger", "#c62828")
    if any(k in low for k in _DONE_KEYWORDS):
        return "#f59e0b"            # gold — completions / milestones
    if any(k in low for k in _UPDATE_KEYWORDS):
        return tok.get("accent", "#0078d4")
    if any(k in low for k in _ADD_KEYWORDS):
        return tok.get("success", "#2e7d32")
    return tok.get("text_lo", "#606060")


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def _parse_dt(ts: str):
    """Try to parse an ISO datetime string; return a datetime or None."""
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts[:19], fmt)
        except ValueError:
            pass
    return None


def _date_header(entry_date: date) -> str:
    today = date.today()
    if entry_date == today:
        return "TODAY"
    if entry_date == today - timedelta(days=1):
        return "YESTERDAY"
    return entry_date.strftime("%A, %d %B %Y").upper()


def _display_time(ts: str) -> str:
    dt = _parse_dt(ts)
    if dt:
        return dt.strftime("%H:%M")
    # Legacy format: already "HH:MM"
    return ts if ts else ""


# ── Widget ────────────────────────────────────────────────────────────────────

class RecentActivityWidget(QWidget):
    """Full-width, date-grouped activity log."""

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    # ── Public ────────────────────────────────────────────────────────────────

    def refresh(self, activities: list) -> None:
        # Clear existing rows
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tok = self._tok()

        if not activities:
            empty = QLabel("No recent activity yet.\nActions like adding paints, models,\nand completing milestones will appear here.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"color: {tok['text_lo']}; font-size: 12px; "
                "background: transparent; padding: 40px 0;"
            )
            self._layout.addWidget(empty)
            self._layout.addStretch()
            return

        # Group by date
        groups: dict[date | None, list] = {}
        for entry in activities:
            ts  = entry.get("timestamp", "")
            dt  = _parse_dt(ts)
            key = dt.date() if dt else None
            groups.setdefault(key, []).append(entry)

        # Sort groups newest-first (None / legacy entries go last)
        def _group_key(k):
            return k if k is not None else date.min
        sorted_dates = sorted(groups.keys(), key=_group_key, reverse=True)

        for group_date in sorted_dates:
            # ── Date header ───────────────────────────────────────────────────
            hdr_text = _date_header(group_date) if group_date else "EARLIER"
            hdr = self._make_date_header(hdr_text, tok)
            self._layout.addWidget(hdr)

            # ── Entries ───────────────────────────────────────────────────────
            for entry in groups[group_date]:
                row = self._make_row(entry, tok)
                self._layout.addWidget(row)

            # Small gap between groups
            spacer = QWidget()
            spacer.setFixedHeight(8)
            spacer.setStyleSheet("background: transparent;")
            self._layout.addWidget(spacer)

        self._layout.addStretch()

    # ── Row builders ──────────────────────────────────────────────────────────

    def _make_date_header(self, text: str, tok: dict) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 4)
        lay.setSpacing(8)

        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {tok['text_lo']}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; background: transparent;"
        )
        lay.addWidget(lbl)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background: {tok['border']}; border: none;")
        line.setFixedHeight(1)
        line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(line, stretch=1)

        return w

    def _make_row(self, entry: dict, tok: dict) -> QFrame:
        icon        = entry.get("icon", "•")
        description = entry.get("description", "")
        timestamp   = entry.get("timestamp", "")
        color       = _action_color(description, tok)

        frame = QFrame()
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        frame.setStyleSheet(
            f"QFrame {{"
            f"  background: {tok['card_bg']};"
            f"  border: 1px solid {tok['border']};"
            f"  border-left: 3px solid {color};"
            f"  border-radius: 4px;"
            f"  margin-bottom: 3px;"
            f"}}"
            f"QFrame:hover {{ background: {tok['bg_raised']}; }}"
        )

        row = QHBoxLayout(frame)
        row.setContentsMargins(10, 8, 12, 8)
        row.setSpacing(10)

        # Icon
        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent; font-size: 14px;")
        row.addWidget(icon_lbl)

        # Description
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet(
            f"color: {tok['text_hi']}; font-size: 12px; background: transparent;"
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setTextFormat(Qt.PlainText)
        row.addWidget(desc_lbl, stretch=1)

        # Timestamp
        display_ts = _display_time(timestamp)
        if display_ts:
            ts_lbl = QLabel(display_ts)
            ts_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            ts_lbl.setStyleSheet(
                f"color: {tok['text_lo']}; font-size: 10px; background: transparent;"
            )
            row.addWidget(ts_lbl)

        return frame

    # ── Internal ──────────────────────────────────────────────────────────────

    def _tok(self) -> dict:
        tm = self._ctx.services.get("theme_manager") if self._ctx else None
        return {
            "bg_base":   tm.token("bg_base")   if tm else "#121212",
            "bg_raised": tm.token("bg_raised") if tm else "#1e1e1e",
            "card_bg":   tm.token("card_bg")   if tm else "#1a1a1a",
            "border":    tm.token("border")    if tm else "#2a2a2a",
            "text_hi":   tm.token("text_hi")   if tm else "#e8e8e8",
            "text_lo":   tm.token("text_lo")   if tm else "#606060",
            "accent":    tm.token("accent")    if tm else "#0078d4",
            "danger":    tm.token("danger")    if tm else "#c62828",
            "success":   tm.token("success")   if tm else "#2e7d32",
        }
