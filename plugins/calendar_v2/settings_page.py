"""
Calendar 2.0 Settings Page

Registered into the application Settings dialog via SettingsRegistry.
Covers: timezone, DST, time format, date format, plus all display/automation prefs.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout,
    QComboBox, QCheckBox, QSpinBox,
    QLabel, QPushButton,
)

# ── Timezone list ─────────────────────────────────────────────────────────────
try:
    import zoneinfo
    _TIMEZONES = sorted(zoneinfo.available_timezones())
except Exception:
    _TIMEZONES = [
        "UTC",
        "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Madrid",
        "Europe/Rome", "Europe/Amsterdam", "Europe/Brussels", "Europe/Zurich",
        "Europe/Stockholm", "Europe/Oslo", "Europe/Copenhagen", "Europe/Helsinki",
        "Europe/Warsaw", "Europe/Prague", "Europe/Vienna", "Europe/Budapest",
        "Europe/Bucharest", "Europe/Athens", "Europe/Moscow",
        "America/New_York", "America/Chicago", "America/Denver",
        "America/Los_Angeles", "America/Anchorage", "America/Honolulu",
        "America/Toronto", "America/Vancouver", "America/Mexico_City",
        "America/Bogota", "America/Lima", "America/Sao_Paulo",
        "America/Argentina/Buenos_Aires", "America/Santiago",
        "Asia/Dubai", "Asia/Kolkata", "Asia/Dhaka", "Asia/Bangkok",
        "Asia/Jakarta", "Asia/Singapore", "Asia/Shanghai", "Asia/Hong_Kong",
        "Asia/Taipei", "Asia/Tokyo", "Asia/Seoul",
        "Australia/Perth", "Australia/Darwin", "Australia/Brisbane",
        "Australia/Adelaide", "Australia/Sydney", "Australia/Melbourne",
        "Pacific/Auckland", "Pacific/Fiji",
        "Africa/Cairo", "Africa/Johannesburg", "Africa/Lagos", "Africa/Nairobi",
    ]

_DATE_FORMATS = [
    ("dd MMM yyyy", "28 May 2026"),
    ("dd/MM/yyyy",  "28/05/2026"),
    ("MM/dd/yyyy",  "05/28/2026"),
    ("yyyy-MM-dd",  "2026-05-28"),
    ("d MMMM yyyy", "28 May 2026 (long)"),
]

_TIME_FORMATS = [
    ("HH:mm",    "24h — 18:30"),
    ("hh:mm AP", "12h — 06:30 PM"),
]


class CalendarV2SettingsPage(QWidget):
    """Calendar 2.0 preferences page shown in the main Settings dialog."""

    saved = Signal()

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context  = context
        self.settings = context.services.get("settings") if context else None

        tm = context.services.try_get("theme_manager") if context else None

        def _t(name, fb): return tm.token(name) if tm else fb

        bg_raised = _t("bg_raised", "#212121")
        bg_input  = _t("bg_input",  "#2a2a2a")
        border    = _t("border",    "#363636")
        text_hi   = _t("text_hi",   "#f0f0f0")
        text_mid  = _t("text_mid",  "#d8d8d8")
        text_lo   = _t("text_lo",   "#909090")
        accent    = _t("accent",    "#0078d4")
        accent_hi = _t("accent_hi", "#2196f3")
        accent_lo = _t("accent_lo", "#005a9e")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(20)

        combo_style = (
            f"QComboBox {{"
            f"  background-color:{bg_input}; color:{text_hi};"
            f"  border:1px solid {border}; border-radius:4px;"
            f"  padding:4px 8px; min-height:26px;"
            f"}}"
            f"QComboBox:focus {{ border-color:{accent}; }}"
            f"QComboBox QAbstractItemView {{"
            f"  background-color:{bg_raised}; color:{text_hi};"
            f"  border:1px solid {border}; selection-background-color:{accent};"
            f"}}"
        )
        spinbox_style = (
            f"QSpinBox {{"
            f"  background-color:{bg_input}; color:{text_hi};"
            f"  border:1px solid {border}; border-radius:4px;"
            f"  padding:4px 8px; min-height:26px;"
            f"}}"
            f"QSpinBox:focus {{ border-color:{accent}; }}"
        )
        check_style = (
            f"QCheckBox {{ color:{text_mid}; spacing:6px; }}"
            f"QCheckBox::indicator {{"
            f"  width:16px; height:16px;"
            f"  border:1px solid {border}; border-radius:3px;"
            f"  background-color:{bg_input};"
            f"}}"
            f"QCheckBox::indicator:checked {{"
            f"  background-color:{accent}; border-color:{accent};"
            f"}}"
        )
        lbl_style    = f"color:{text_mid}; font-size:12px;"
        header_style = f"font-size:9px; font-weight:700; color:{text_lo}; letter-spacing:1px;"

        def _section(title: str) -> QLabel:
            lbl = QLabel(title)
            lbl.setStyleSheet(header_style)
            return lbl

        def _lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setStyleSheet(lbl_style)
            return l

        # ── Regional ─────────────────────────────────────────────────────────
        root.addWidget(_section("REGIONAL"))

        form_regional = QFormLayout()
        form_regional.setSpacing(10)
        form_regional.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._tz_combo = QComboBox()
        self._tz_combo.setStyleSheet(combo_style)
        self._tz_combo.setMaxVisibleItems(20)
        for tz in _TIMEZONES:
            self._tz_combo.addItem(tz)
        saved_tz = self._get("calendar.timezone", "UTC")
        idx = self._tz_combo.findText(saved_tz)
        self._tz_combo.setCurrentIndex(idx if idx >= 0 else 0)
        form_regional.addRow(_lbl("Timezone:"), self._tz_combo)

        self._dst_check = QCheckBox("Automatically adjust for daylight saving time")
        self._dst_check.setStyleSheet(check_style)
        self._dst_check.setChecked(self._get("calendar.observe_dst", True))
        form_regional.addRow(_lbl("Daylight saving:"), self._dst_check)

        self._time_fmt_combo = QComboBox()
        self._time_fmt_combo.setStyleSheet(combo_style)
        for fmt, label in _TIME_FORMATS:
            self._time_fmt_combo.addItem(label, fmt)
        saved_time_fmt = self._get("calendar.time_format", "HH:mm")
        for i, (fmt, _) in enumerate(_TIME_FORMATS):
            if fmt == saved_time_fmt:
                self._time_fmt_combo.setCurrentIndex(i)
                break
        form_regional.addRow(_lbl("Time format:"), self._time_fmt_combo)

        self._date_fmt_combo = QComboBox()
        self._date_fmt_combo.setStyleSheet(combo_style)
        for fmt, label in _DATE_FORMATS:
            self._date_fmt_combo.addItem(label, fmt)
        saved_date_fmt = self._get("calendar.date_format", "dd MMM yyyy")
        for i, (fmt, _) in enumerate(_DATE_FORMATS):
            if fmt == saved_date_fmt:
                self._date_fmt_combo.setCurrentIndex(i)
                break
        form_regional.addRow(_lbl("Date format:"), self._date_fmt_combo)

        root.addLayout(form_regional)

        # ── Display ──────────────────────────────────────────────────────────
        root.addWidget(_section("DISPLAY"))

        form_display = QFormLayout()
        form_display.setSpacing(10)
        form_display.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._view_combo = QComboBox()
        self._view_combo.setStyleSheet(combo_style)
        self._view_combo.addItems(["Today", "Week", "Month", "Agenda"])
        self._view_combo.setCurrentText(self._get("calendar.default_view", "Today"))
        form_display.addRow(_lbl("Default view:"), self._view_combo)

        self._week_start_combo = QComboBox()
        self._week_start_combo.setStyleSheet(combo_style)
        self._week_start_combo.addItems(["Monday", "Sunday"])
        self._week_start_combo.setCurrentText(self._get("calendar.week_start", "Monday"))
        form_display.addRow(_lbl("Week starts on:"), self._week_start_combo)

        self._show_completed = QCheckBox()
        self._show_completed.setStyleSheet(check_style)
        self._show_completed.setChecked(self._get("calendar.show_completed", False))
        form_display.addRow(_lbl("Show completed events:"), self._show_completed)

        root.addLayout(form_display)

        # ── Automation ───────────────────────────────────────────────────────
        root.addWidget(_section("AUTOMATION"))

        form_auto = QFormLayout()
        form_auto.setSpacing(10)
        form_auto.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._auto_suggest = QCheckBox("Automatically suggest sessions from other plugins")
        self._auto_suggest.setStyleSheet(check_style)
        self._auto_suggest.setChecked(self._get("calendar.auto_suggest", True))
        form_auto.addRow(_lbl("Auto-generate events:"), self._auto_suggest)

        self._duration_spin = QSpinBox()
        self._duration_spin.setStyleSheet(spinbox_style)
        self._duration_spin.setRange(15, 480)
        self._duration_spin.setSingleStep(15)
        self._duration_spin.setSuffix(" minutes")
        self._duration_spin.setValue(self._get("calendar.default_duration", 60))
        form_auto.addRow(_lbl("Default session duration:"), self._duration_spin)

        root.addLayout(form_auto)
        root.addStretch()

        # ── Save ─────────────────────────────────────────────────────────────
        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedHeight(34)
        self._save_btn.setFixedWidth(100)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet(
            f"QPushButton {{ background-color:{accent}; color:#ffffff;"
            f"  border:none; border-radius:4px; font-weight:600; font-size:12px; }}"
            f"QPushButton:hover {{ background-color:{accent_hi}; }}"
            f"QPushButton:pressed {{ background-color:{accent_lo}; }}"
        )
        self._save_btn.clicked.connect(self._save)
        root.addWidget(self._save_btn, alignment=Qt.AlignLeft)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get(self, key: str, default):
        if not self.settings:
            return default
        return self.settings.get(key, default)

    def _save(self):
        if not self.settings:
            return
        self.settings.set("calendar.timezone",        self._tz_combo.currentText())
        self.settings.set("calendar.observe_dst",     self._dst_check.isChecked())
        self.settings.set("calendar.time_format",     self._time_fmt_combo.currentData())
        self.settings.set("calendar.date_format",     self._date_fmt_combo.currentData())
        self.settings.set("calendar.default_view",    self._view_combo.currentText())
        self.settings.set("calendar.week_start",      self._week_start_combo.currentText())
        self.settings.set("calendar.show_completed",  self._show_completed.isChecked())
        self.settings.set("calendar.auto_suggest",    self._auto_suggest.isChecked())
        self.settings.set("calendar.default_duration", self._duration_spin.value())

        bus = getattr(self.context, "event_bus", None)
        if bus:
            try:
                bus.emit("calendar_settings_changed", {
                    "timezone":        self._tz_combo.currentText(),
                    "observe_dst":     self._dst_check.isChecked(),
                    "time_format":     self._time_fmt_combo.currentData(),
                    "date_format":     self._date_fmt_combo.currentData(),
                    "default_view":    self._view_combo.currentText(),
                    "week_start":      self._week_start_combo.currentText(),
                    "show_completed":  self._show_completed.isChecked(),
                    "auto_suggest":    self._auto_suggest.isChecked(),
                    "default_duration": self._duration_spin.value(),
                })
            except Exception as e:
                log.error(f"[CALENDAR V2 SETTINGS] Failed to emit calendar_settings_changed: {e}")

        self.saved.emit()
