"""
Calendar Settings Page

Registered into the application Settings dialog via SettingsRegistry.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout,
    QComboBox, QCheckBox, QSpinBox,
    QLabel, QPushButton,
)


class CalendarSettingsPage(QWidget):
    """Calendar preferences page shown in the main Settings dialog."""

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context  = context
        self.settings = context.services.get("settings") if context else None

        # ── Theme tokens ──────────────────────────────────────────────────────
        tm = context.services.get("theme_manager") if context else None

        def _t(name, fb): return tm.token(name) if tm else fb

        bg_raised  = _t("bg_raised",  "#212121")
        bg_input   = _t("bg_input",   "#2a2a2a")
        border     = _t("border",     "#363636")
        text_hi    = _t("text_hi",    "#f0f0f0")
        text_mid   = _t("text_mid",   "#d8d8d8")
        text_lo    = _t("text_lo",    "#909090")
        accent     = _t("accent",     "#0078d4")
        accent_hi  = _t("accent_hi",  "#2196f3")
        accent_lo  = _t("accent_lo",  "#005a9e")

        # ── Root layout ───────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Section header
        header = QLabel("CALENDAR PREFERENCES")
        header.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {text_lo}; letter-spacing: 1px;"
        )
        root.addWidget(header)

        # ── Form ──────────────────────────────────────────────────────────────
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        combo_style = (
            f"QComboBox {{"
            f"  background-color: {bg_input}; color: {text_hi};"
            f"  border: 1px solid {border}; border-radius: 4px;"
            f"  padding: 4px 8px; min-height: 26px;"
            f"}}"
            f"QComboBox:focus {{"
            f"  border-color: {accent};"
            f"}}"
            f"QComboBox QAbstractItemView {{"
            f"  background-color: {bg_raised}; color: {text_hi};"
            f"  border: 1px solid {border}; selection-background-color: {accent};"
            f"}}"
        )
        spinbox_style = (
            f"QSpinBox {{"
            f"  background-color: {bg_input}; color: {text_hi};"
            f"  border: 1px solid {border}; border-radius: 4px;"
            f"  padding: 4px 8px; min-height: 26px;"
            f"}}"
            f"QSpinBox:focus {{"
            f"  border-color: {accent};"
            f"}}"
        )
        check_style = (
            f"QCheckBox {{ color: {text_mid}; spacing: 6px; }}"
            f"QCheckBox::indicator {{"
            f"  width: 16px; height: 16px;"
            f"  border: 1px solid {border}; border-radius: 3px;"
            f"  background-color: {bg_input};"
            f"}}"
            f"QCheckBox::indicator:checked {{"
            f"  background-color: {accent}; border-color: {accent};"
            f"}}"
        )
        label_style = f"color: {text_mid}; font-size: 12px;"

        # 1. Default View
        self._view_combo = QComboBox()
        self._view_combo.addItems(["Month", "Week", "Agenda", "Today"])
        self._view_combo.setStyleSheet(combo_style)
        saved_view = self._get("calendar.default_view", "Month")
        self._view_combo.setCurrentText(saved_view)

        view_label = QLabel("Default View:")
        view_label.setStyleSheet(label_style)
        form.addRow(view_label, self._view_combo)

        # 2. Week starts on
        self._week_start_combo = QComboBox()
        self._week_start_combo.addItems(["Monday", "Sunday"])
        self._week_start_combo.setStyleSheet(combo_style)
        saved_week_start = self._get("calendar.week_start", "Monday")
        self._week_start_combo.setCurrentText(saved_week_start)

        week_label = QLabel("Week starts on:")
        week_label.setStyleSheet(label_style)
        form.addRow(week_label, self._week_start_combo)

        # 3. Show completed events
        self._show_completed = QCheckBox()
        self._show_completed.setStyleSheet(check_style)
        self._show_completed.setChecked(self._get("calendar.show_completed", False))

        completed_label = QLabel("Show completed events:")
        completed_label.setStyleSheet(label_style)
        form.addRow(completed_label, self._show_completed)

        # 4. Auto-generate events
        self._auto_suggest = QCheckBox("Automatically suggest sessions from other plugins")
        self._auto_suggest.setStyleSheet(check_style)
        self._auto_suggest.setChecked(self._get("calendar.auto_suggest", True))

        suggest_label = QLabel("Auto-generate events:")
        suggest_label.setStyleSheet(label_style)
        form.addRow(suggest_label, self._auto_suggest)

        # 5. Default session duration
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(15, 480)
        self._duration_spin.setSingleStep(15)
        self._duration_spin.setSuffix(" minutes")
        self._duration_spin.setStyleSheet(spinbox_style)
        self._duration_spin.setValue(self._get("calendar.default_duration", 60))

        duration_label = QLabel("Default session duration:")
        duration_label.setStyleSheet(label_style)
        form.addRow(duration_label, self._duration_spin)

        root.addLayout(form)
        root.addStretch()

        # ── Save button ───────────────────────────────────────────────────────
        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedHeight(34)
        self._save_btn.setFixedWidth(100)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {accent}; color: #ffffff;"
            f"  border: none; border-radius: 4px;"
            f"  font-weight: 600; font-size: 12px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {accent_hi};"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background-color: {accent_lo};"
            f"}}"
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
        self.settings.set("calendar.default_view",    self._view_combo.currentText())
        self.settings.set("calendar.week_start",      self._week_start_combo.currentText())
        self.settings.set("calendar.show_completed",  self._show_completed.isChecked())
        self.settings.set("calendar.auto_suggest",    self._auto_suggest.isChecked())
        self.settings.set("calendar.default_duration", self._duration_spin.value())

        bus = getattr(self.context, "event_bus", None)
        if bus:
            try:
                bus.emit("calendar_settings_changed", {
                    "default_view":     self._view_combo.currentText(),
                    "week_start":       self._week_start_combo.currentText(),
                    "show_completed":   self._show_completed.isChecked(),
                    "auto_suggest":     self._auto_suggest.isChecked(),
                    "default_duration": self._duration_spin.value(),
                })
            except Exception as e:
                log.error(f"[CALENDAR SETTINGS] Failed to emit calendar_settings_changed: {e}")
