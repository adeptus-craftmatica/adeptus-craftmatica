from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QLabel,
)
from .models import ARMY_FORMATS


class ArmyBuilderSettingsPage(QWidget):
    """Army Builder settings page."""

    def __init__(self, context):
        super().__init__()
        self.context = context
        self.settings = context.services.get("settings")

        layout = QVBoxLayout(self)

        title = QLabel("Army Builder Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        form = QFormLayout()

        self.default_system = QComboBox()
        self.default_system.setEditable(True)
        self.default_system.addItems([""] + list(ARMY_FORMATS.keys()))
        self.default_system.setCurrentText(
            self.settings.get("army_builder.default_game_system", "")
        )
        self.default_system.currentTextChanged.connect(self._save)
        form.addRow("Default Game System:", self.default_system)

        layout.addLayout(form)
        layout.addStretch()

    def _save(self):
        self.settings.set("army_builder.default_game_system", self.default_system.currentText())
