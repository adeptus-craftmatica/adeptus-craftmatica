"""Add / Edit Event dialog for the Calendar plugin."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from plugins.calendar.models import (
    EVENT_CATEGORIES,
    RECURRENCE_LABELS,
    REMINDER_OPTIONS,
    SESSION_TYPES,
    SESSION_TYPE_TO_CATEGORY,
)

# ── Constants ──────────────────────────────────────────────────────────────────

# Maps combo index → priority int  (combo order: Normal, Important, Urgent)
_PRIORITY_INDEX_TO_INT: list[int] = [3, 2, 1]
_PRIORITY_INT_TO_INDEX: dict[int, int] = {3: 0, 2: 1, 1: 2}

# Recurrence: combo index → rule key
_RECURRENCE_KEYS: list[str] = ["none", "daily", "weekly", "biweekly", "monthly"]
_RECURRENCE_KEY_TO_INDEX: dict[str, int] = {k: i for i, k in enumerate(_RECURRENCE_KEYS)}

# Linked plugin: combo index → plugin key
_LINK_KEYS: list[str] = ["", "paint_tracker", "model_tracker", "army_builder", "campaign_tracker"]
_LINK_KEY_TO_INDEX: dict[str, int] = {k: i for i, k in enumerate(_LINK_KEYS)}

# Reminder: combo index → minutes
_REMINDER_MINUTES: list[int] = [0, 15, 30, 60, 1440]
_REMINDER_MINUTES_TO_INDEX: dict[int, int] = {v: i for i, v in enumerate(_REMINDER_MINUTES)}

# Default fallback theme tokens
_DEFAULTS: dict[str, str] = {
    "bg_base":    "#121212",
    "bg_raised":  "#1e1e1e",
    "bg_input":   "#1a1a1a",
    "card_bg":    "#1c1c1c",
    "border":     "#2a2a2a",
    "border_hi":  "#3a3a3a",
    "text_hi":    "#e8e8e8",
    "text_mid":   "#a0a0a0",
    "text_lo":    "#606060",
    "accent":     "#0078d4",
    "danger":     "#c62828",
    "success":    "#2e7d32",
    "warning":    "#e07820",
    "radius_base": "6px",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tok(tm, name: str) -> str:
    """Return a theme token, falling back to built-in defaults."""
    if tm is not None:
        try:
            return tm.token(name)
        except Exception:
            pass
    return _DEFAULTS.get(name, "#888888")


def _section_label(text: str, color_lo: str) -> QLabel:
    """Create a small-caps section divider label."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color_lo}; font-size: 9px; font-weight: 700; "
        f"letter-spacing: 1px; text-transform: uppercase;"
    )
    lbl.setContentsMargins(0, 8, 0, 2)
    return lbl


def _separator(border_color: str) -> QFrame:
    """Thin horizontal rule."""
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Plain)
    line.setStyleSheet(f"color: {border_color}; border: none; border-top: 1px solid {border_color};")
    line.setFixedHeight(1)
    return line


# ── Dialog ─────────────────────────────────────────────────────────────────────

class EventDialog(QDialog):
    """
    Modal dialog for creating or editing a CalendarEvent.

    Parameters
    ----------
    context:
        Application context object (may be None in standalone usage).
    event:
        Existing CalendarEvent to edit, or None for a new event.
    default_date:
        ISO date string ("YYYY-MM-DD") used when creating a new event.
        Falls back to today when not supplied.
    parent:
        Optional Qt parent widget.

    Custom result codes
    -------------------
    QDialog.Accepted (1) — user clicked Save
    QDialog.Rejected (0) — user clicked Cancel or closed
    EventDialog.DELETED (2) — user clicked Delete and confirmed
    """

    DELETED: int = 2  # Custom result code for confirmed deletion

    def __init__(self, context, event=None, default_date: str | None = None, parent=None):
        super().__init__(parent)
        self._context = context
        self._event   = event

        # Resolve theme tokens
        tm = context.services.get("theme_manager") if context else None
        self._tm = tm

        t = lambda name: _tok(tm, name)  # noqa: E731  (short alias)

        # ── Dialog chrome ──────────────────────────────────────────────────────
        is_edit         = event is not None
        is_activity_rec = is_edit and getattr(event, "auto_generated", False)
        self.setWindowTitle(
            "Activity Record" if is_activity_rec
            else ("Edit Event" if is_edit else "New Event")
        )
        self.setMinimumWidth(480)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background: {t('bg_base')};
            }}
            QLabel {{
                color: {t('text_hi')};
            }}
            QLineEdit, QTextEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {{
                background: {t('bg_input')};
                border: 1px solid {t('border')};
                border-radius: 4px;
                color: {t('text_hi')};
                padding: 4px 8px;
                selection-background-color: {t('accent')};
            }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
            QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus {{
                border-color: {t('accent')};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 4px;
            }}
            QComboBox QAbstractItemView {{
                background: {t('bg_raised')};
                border: 1px solid {t('border')};
                color: {t('text_hi')};
                selection-background-color: {t('accent')};
            }}
            QCheckBox {{
                color: {t('text_hi')};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {t('border')};
                border-radius: 3px;
                background: {t('bg_input')};
            }}
            QCheckBox::indicator:checked {{
                background: {t('accent')};
                border-color: {t('accent')};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 16px;
                border: none;
                background: transparent;
            }}
            QDateEdit::up-button, QDateEdit::down-button,
            QTimeEdit::up-button, QTimeEdit::down-button {{
                width: 16px;
                border: none;
                background: transparent;
            }}
        """)

        # ── Root layout ────────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────────
        if is_activity_rec:
            header_icon = "📝 "
            header_text = "📝 Activity Record"
        elif is_edit:
            header_icon = "✏ "
            header_text = "✏ Edit Event"
        else:
            header_icon = "📅 "
            header_text = "📅 New Event"

        header_lbl = QLabel(header_text)
        header_font = QFont()
        header_font.setPointSize(16)
        header_font.setBold(True)
        header_lbl.setFont(header_font)
        header_lbl.setStyleSheet(f"color: {t('accent')}; margin-bottom: 8px;")
        root.addWidget(header_lbl)
        root.addWidget(_separator(t("border")))
        root.addSpacing(12)

        # ── Activity record info banner ─────────────────────────────────────────
        # Shown only for auto-generated records so the user understands this is
        # a historical log entry, not a task they created.
        if is_activity_rec:
            banner = QFrame()
            banner.setStyleSheet(f"""
                QFrame {{
                    background: {t('warning')}18;
                    border: 1px solid {t('warning')}44;
                    border-radius: 6px;
                    padding: 2px;
                }}
            """)
            banner_lay = QHBoxLayout(banner)
            banner_lay.setContentsMargins(10, 8, 10, 8)
            banner_lay.setSpacing(8)

            icon_lbl = QLabel("📋")
            icon_lbl.setStyleSheet("font-size: 14px; background: transparent;")
            icon_lbl.setFixedWidth(20)
            banner_lay.addWidget(icon_lbl)

            msg_lbl = QLabel(
                "This is an automatically logged activity record.\n"
                "It was created by the system when an action occurred in another plugin.\n"
                "You can add notes or delete it, but it is not a task to be completed."
            )
            msg_lbl.setWordWrap(True)
            msg_lbl.setStyleSheet(
                f"font-size: 11px; color: {t('text_mid')}; background: transparent;"
            )
            banner_lay.addWidget(msg_lbl, stretch=1)
            root.addWidget(banner)
            root.addSpacing(10)

        # ── Form ───────────────────────────────────────────────────────────────
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        label_style = f"color: {t('text_hi')}; font-size: 12px;"

        def _lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setStyleSheet(label_style)
            l.setMinimumSize(0, 0)
            return l

        # -- DETAILS section ---------------------------------------------------
        form.addRow(_section_label("DETAILS", t("text_lo")))

        # Title
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("What are you planning?")
        self._title_edit.setMinimumSize(0, 0)
        form.addRow(_lbl("Title"), self._title_edit)

        # Session Type
        self._type_combo = QComboBox()
        self._type_combo.addItems(SESSION_TYPES)
        self._type_combo.setMinimumSize(0, 0)
        self._type_combo.currentTextChanged.connect(self._on_session_type_changed)
        form.addRow(_lbl("Session Type"), self._type_combo)

        # Category (auto-derived from session type, but user-editable)
        self._category_combo = QComboBox()
        self._category_combo.addItems(EVENT_CATEGORIES)
        self._category_combo.setMinimumSize(0, 0)
        self._category_combo.setCurrentText(
            SESSION_TYPE_TO_CATEGORY.get(SESSION_TYPES[0], "Hobby Session")
        )
        form.addRow(_lbl("Category"), self._category_combo)

        # Priority
        self._priority_combo = QComboBox()
        self._priority_combo.addItems(["Normal", "Important", "Urgent"])
        self._priority_combo.setMinimumSize(0, 0)
        form.addRow(_lbl("Priority"), self._priority_combo)

        # Notes
        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(66)   # ~3 lines
        self._notes_edit.setMinimumSize(0, 0)
        self._notes_edit.setPlaceholderText("Optional notes…")
        form.addRow(_lbl("Notes"), self._notes_edit)

        # -- WHEN section ------------------------------------------------------
        form.addRow(_section_label("WHEN", t("text_lo")))

        # Date
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setMinimumSize(0, 0)
        # Set default date
        if default_date:
            try:
                qd = QDate.fromString(default_date, "yyyy-MM-dd")
                if qd.isValid():
                    self._date_edit.setDate(qd)
                else:
                    self._date_edit.setDate(QDate.currentDate())
            except Exception:
                self._date_edit.setDate(QDate.currentDate())
        else:
            self._date_edit.setDate(QDate.currentDate())
        form.addRow(_lbl("Date"), self._date_edit)

        # All Day
        self._allday_check = QCheckBox("All day")
        self._allday_check.setChecked(True)
        self._allday_check.setMinimumSize(0, 0)
        form.addRow(_lbl(""), self._allday_check)

        # Time (hidden when all-day)
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setMinimumSize(0, 0)
        self._time_label = _lbl("Start Time")
        form.addRow(self._time_label, self._time_edit)

        # Duration (hidden when all-day)
        duration_container = QWidget()
        duration_container.setMinimumSize(0, 0)
        dur_layout = QHBoxLayout(duration_container)
        dur_layout.setContentsMargins(0, 0, 0, 0)
        dur_layout.setSpacing(6)
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(0, 480)
        self._duration_spin.setSingleStep(15)
        self._duration_spin.setValue(60)
        self._duration_spin.setMinimumSize(0, 0)
        dur_layout.addWidget(self._duration_spin)
        dur_layout.addWidget(QLabel("minutes"))
        dur_layout.addStretch()
        self._duration_label = _lbl("Duration")
        form.addRow(self._duration_label, duration_container)

        # Reminder
        self._reminder_combo = QComboBox()
        self._reminder_combo.addItems(list(REMINDER_OPTIONS.values()))
        self._reminder_combo.setMinimumSize(0, 0)
        form.addRow(_lbl("Reminder"), self._reminder_combo)

        # -- RECURRENCE section ------------------------------------------------
        form.addRow(_section_label("RECURRENCE", t("text_lo")))

        # Repeats
        self._recurrence_combo = QComboBox()
        self._recurrence_combo.addItems(list(RECURRENCE_LABELS.values()))
        self._recurrence_combo.setMinimumSize(0, 0)
        form.addRow(_lbl("Repeats"), self._recurrence_combo)

        # Until (hidden when no recurrence)
        self._until_edit = QDateEdit()
        self._until_edit.setCalendarPopup(True)
        self._until_edit.setDisplayFormat("yyyy-MM-dd")
        self._until_edit.setDate(QDate.currentDate())
        self._until_edit.setMinimumSize(0, 0)
        self._until_label = _lbl("Until")
        form.addRow(self._until_label, self._until_edit)

        # -- LINK section ------------------------------------------------------
        form.addRow(_section_label("LINK", t("text_lo")))

        self._link_combo = QComboBox()
        self._link_combo.addItems([
            "— None —",
            "Paint Tracker",
            "Model Tracker",
            "Army Builder",
            "Campaign Tracker",
        ])
        self._link_combo.setMinimumSize(0, 0)
        form.addRow(_lbl("Link to"), self._link_combo)

        # "→ Open in [Plugin]" shortcut — only shown when event has a linked_plugin
        if is_edit and event and event.linked_plugin:
            _plugin_names: dict[str, str] = {
                "paint_tracker":    "Paint Tracker",
                "model_tracker":    "Model Tracker",
                "army_builder":     "Army Builder",
                "campaign_tracker": "Campaign Tracker",
                "tool_tracker":     "Tool Tracker",
                "materials_tracker":"Materials Tracker",
                "project_tracker":  "Projects",
                "paint_scheme":     "Paint Schemes",
            }
            _pid = event.linked_plugin
            plugin_label = _plugin_names.get(_pid, _pid)
            src_btn = QPushButton(f"→  Open in {plugin_label}")
            src_btn.setCursor(Qt.PointingHandCursor)
            src_btn.setMinimumSize(0, 0)
            src_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {t('accent')};
                    font-size: 11px;
                    font-weight: 600;
                    padding: 0;
                    text-align: left;
                }}
                QPushButton:hover {{
                    text-decoration: underline;
                }}
            """)
            src_btn.clicked.connect(
                lambda _checked=False, pid=_pid: self._navigate_to_source(pid)
            )
            form.addRow(_lbl(""), src_btn)

        root.addLayout(form)
        root.addSpacing(16)
        root.addWidget(_separator(t("border")))
        root.addSpacing(12)

        # ── Footer buttons ─────────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(8)

        # Delete button — only shown when editing an existing event
        if is_edit:
            self._delete_btn = QPushButton("🗑  Delete")
            self._delete_btn.setFixedHeight(34)
            self._delete_btn.setCursor(Qt.PointingHandCursor)
            self._delete_btn.setMinimumSize(0, 0)
            self._delete_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid {t('danger')};
                    border-radius: 6px;
                    color: {t('danger')};
                    font-size: 12px;
                    padding: 0 14px;
                }}
                QPushButton:hover {{
                    background: {t('danger')}22;
                }}
                QPushButton:pressed {{
                    background: {t('danger')}44;
                }}
            """)
            footer.addWidget(self._delete_btn)
        else:
            self._delete_btn = None

        footer.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedHeight(34)
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setMinimumSize(0, 0)
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t('bg_raised')};
                border: 1px solid {t('border')};
                border-radius: 6px;
                color: {t('text_lo')};
                font-size: 12px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {t('border')};
                color: {t('text_hi')};
            }}
        """)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedHeight(34)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setMinimumSize(0, 0)
        self._save_btn.setDefault(True)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t('accent')};
                border: none;
                border-radius: 6px;
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background: {t('accent')}cc;
            }}
            QPushButton:pressed {{
                background: {t('accent')}99;
            }}
        """)

        footer.addWidget(self._cancel_btn)
        footer.addWidget(self._save_btn)
        root.addLayout(footer)

        # ── Error label (hidden until needed) ─────────────────────────────────
        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(f"color: {t('danger')}; font-size: 11px;")
        self._error_lbl.setVisible(False)
        root.addWidget(self._error_lbl)

        # ── Wire signals ───────────────────────────────────────────────────────
        self._allday_check.toggled.connect(self._on_allday_toggled)
        self._recurrence_combo.currentIndexChanged.connect(self._on_recurrence_changed)
        self._save_btn.clicked.connect(self._on_save)
        self._cancel_btn.clicked.connect(self.reject)
        if self._delete_btn is not None:
            self._delete_btn.clicked.connect(self._on_delete)

        # ── Populate fields if editing ─────────────────────────────────────────
        if event is not None:
            self._populate(event)

        # Apply initial visibility
        self._on_allday_toggled(self._allday_check.isChecked())
        self._on_recurrence_changed(self._recurrence_combo.currentIndex())

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_session_type_changed(self, session_type: str) -> None:
        """Auto-set category when session type changes, unless user has overridden it."""
        derived = SESSION_TYPE_TO_CATEGORY.get(session_type, "Hobby Session")
        self._category_combo.setCurrentText(derived)

    def _on_allday_toggled(self, checked: bool) -> None:
        """Show/hide Time and Duration rows based on All Day checkbox."""
        self._time_edit.setVisible(not checked)
        self._time_label.setVisible(not checked)
        self._duration_spin.parentWidget().setVisible(not checked)
        self._duration_label.setVisible(not checked)

    def _on_recurrence_changed(self, index: int) -> None:
        """Show/hide the Until date when a recurrence is selected."""
        has_recurrence = (index != 0)
        self._until_edit.setVisible(has_recurrence)
        self._until_label.setVisible(has_recurrence)

    def _on_save(self) -> None:
        """Validate required fields, then accept the dialog."""
        title = self._title_edit.text().strip()
        if not title:
            self._error_lbl.setText("Title is required.")
            self._error_lbl.setVisible(True)
            self._title_edit.setFocus()
            return
        self._error_lbl.setVisible(False)
        self.accept()

    def _on_delete(self) -> None:
        """Ask for confirmation then close with DELETED result code."""
        from PySide6.QtWidgets import QMessageBox
        tm = self._tm
        bg  = tm.token("bg_base")   if tm else "#121212"
        fg  = tm.token("text_hi")   if tm else "#e8e8e8"
        brd = tm.token("border")    if tm else "#2a2a2a"
        acc = tm.token("accent")    if tm else "#0078d4"
        inp = tm.token("bg_input")  if tm else "#1a1a1a"
        dan = tm.token("danger")    if tm else "#c62828"

        title = self._event.title if self._event else "this event"
        msg = QMessageBox(self)
        msg.setWindowTitle("Delete Event")
        msg.setText(f"Delete <b>{title}</b>?")
        msg.setInformativeText("This action cannot be undone.")
        msg.setIcon(QMessageBox.Warning)
        msg.setStyleSheet(f"""
            QMessageBox {{
                background: {bg}; color: {fg};
            }}
            QLabel {{ color: {fg}; }}
            QPushButton {{
                background: {inp}; color: {fg};
                border: 1px solid {brd}; border-radius: 4px;
                padding: 4px 16px; min-width: 80px;
            }}
            QPushButton:hover {{ border-color: {acc}; color: {acc}; }}
        """)
        delete_btn = msg.addButton("Delete", QMessageBox.DestructiveRole)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: {dan}22; color: {dan};
                border: 1px solid {dan}; border-radius: 4px;
                padding: 4px 16px;
            }}
            QPushButton:hover {{ background: {dan}44; }}
        """)
        msg.addButton("Cancel", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() is delete_btn:
            self.done(EventDialog.DELETED)

    def _navigate_to_source(self, plugin_id: str) -> None:
        """Emit a dashboard_navigate event and close the dialog."""
        bus = getattr(self._context, "event_bus", None) if self._context else None
        if bus:
            try:
                bus.emit("dashboard_navigate", {"plugin_id": plugin_id})
            except Exception:
                pass
        self.reject()

    # ── Population ─────────────────────────────────────────────────────────────

    def _populate(self, event) -> None:
        """Fill all form fields from an existing CalendarEvent."""
        # Title
        self._title_edit.setText(event.title or "")

        # Session type
        idx = SESSION_TYPES.index(event.session_type) if event.session_type in SESSION_TYPES else 0
        self._type_combo.setCurrentIndex(idx)

        # Category (explicit — don't let session_type signal override it during populate)
        if event.event_category and event.event_category in EVENT_CATEGORIES:
            self._category_combo.blockSignals(True)
            self._category_combo.setCurrentText(event.event_category)
            self._category_combo.blockSignals(False)

        # Date
        if event.event_date:
            qd = QDate.fromString(event.event_date, "yyyy-MM-dd")
            if qd.isValid():
                self._date_edit.setDate(qd)

        # All day / time
        is_all_day = not event.time_start
        self._allday_check.setChecked(is_all_day)
        if not is_all_day and event.time_start:
            qt = QTime.fromString(event.time_start, "HH:mm")
            if qt.isValid():
                self._time_edit.setTime(qt)

        # Duration
        self._duration_spin.setValue(event.duration_minutes if event.duration_minutes >= 0 else 60)

        # Priority
        self._priority_combo.setCurrentIndex(
            _PRIORITY_INT_TO_INDEX.get(event.priority, 0)
        )

        # Notes
        self._notes_edit.setPlainText(event.notes or "")

        # Recurrence
        rec_idx = _RECURRENCE_KEY_TO_INDEX.get(event.recurrence_rule or "none", 0)
        self._recurrence_combo.setCurrentIndex(rec_idx)

        # Until
        if event.recurrence_end:
            qu = QDate.fromString(event.recurrence_end, "yyyy-MM-dd")
            if qu.isValid():
                self._until_edit.setDate(qu)

        # Link
        link_idx = _LINK_KEY_TO_INDEX.get(event.linked_plugin or "", 0)
        self._link_combo.setCurrentIndex(link_idx)

        # Reminder
        rem_idx = _REMINDER_MINUTES_TO_INDEX.get(event.reminder_minutes, 0)
        self._reminder_combo.setCurrentIndex(rem_idx)

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_event_data(self) -> dict:
        """
        Return all dialog field values as a dict matching CalendarEvent fields.
        Call this after the dialog is accepted.
        """
        # Date
        event_date = self._date_edit.date().toString("yyyy-MM-dd")

        # Time / all-day
        if self._allday_check.isChecked():
            time_start = ""
        else:
            time_start = self._time_edit.time().toString("HH:mm")

        duration = (
            0 if self._allday_check.isChecked()
            else self._duration_spin.value()
        )

        # Priority
        priority = _PRIORITY_INDEX_TO_INT[self._priority_combo.currentIndex()]

        # Recurrence
        rec_idx = self._recurrence_combo.currentIndex()
        recurrence_rule = _RECURRENCE_KEYS[rec_idx]
        is_recurring = recurrence_rule != "none"

        if is_recurring:
            recurrence_end = self._until_edit.date().toString("yyyy-MM-dd")
        else:
            recurrence_end = ""

        # Link
        link_idx = self._link_combo.currentIndex()
        linked_plugin = _LINK_KEYS[link_idx]

        # Preserve existing linked_id / linked_name if not changed
        if self._event is not None and linked_plugin == (self._event.linked_plugin or ""):
            linked_id   = self._event.linked_id   or ""
            linked_name = self._event.linked_name or ""
        else:
            linked_id   = ""
            linked_name = self._link_combo.currentText() if link_idx != 0 else ""

        # Reminder
        reminder_minutes = _REMINDER_MINUTES[self._reminder_combo.currentIndex()]

        # Completed — preserve existing value; new events start incomplete
        completed = self._event.completed if self._event is not None else False

        return {
            "title":             self._title_edit.text().strip(),
            "session_type":      self._type_combo.currentText(),
            "event_category":    self._category_combo.currentText(),
            "event_date":        event_date,
            "time_start":        time_start,
            "duration_minutes":  duration,
            "priority":          priority,
            "is_recurring":      is_recurring,
            "recurrence_rule":   recurrence_rule,
            "recurrence_end":    recurrence_end,
            "linked_plugin":     linked_plugin,
            "linked_name":       linked_name,
            "linked_id":         linked_id,
            "notes":             self._notes_edit.toPlainText(),
            "reminder_minutes":  reminder_minutes,
            "completed":         completed,
        }
