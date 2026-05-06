from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout,
    QComboBox, QLabel,
)

from .models import VALID_STATUSES, COMMON_GAME_SYSTEMS


class ModelSettingsPage(QWidget):
    """Model Tracker settings page (registered in the app Settings dialog)."""

    def __init__(self, context):
        super().__init__()
        self.context = context
        self.settings = context.services.get("settings")

        layout = QVBoxLayout(self)

        title = QLabel("Model Tracker Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        form = QFormLayout()

        # Default game system
        self.default_system = QComboBox()
        self.default_system.setEditable(True)
        self.default_system.addItems([""] + COMMON_GAME_SYSTEMS)
        self.default_system.setCurrentText(
            self.settings.get("model_tracker.default_game_system", "")
        )
        self.default_system.currentTextChanged.connect(self._save)
        form.addRow("Default Game System:", self.default_system)

        # Default status
        self.default_status = QComboBox()
        self.default_status.addItems(VALID_STATUSES)
        self.default_status.setCurrentText(
            self.settings.get("model_tracker.default_status", "Unassembled")
        )
        self.default_status.currentTextChanged.connect(self._save)
        form.addRow("Default Status:", self.default_status)

        layout.addLayout(form)
        layout.addStretch()

    def _save(self):
        self.settings.set("model_tracker.default_game_system", self.default_system.currentText())
        self.settings.set("model_tracker.default_status", self.default_status.currentText())
