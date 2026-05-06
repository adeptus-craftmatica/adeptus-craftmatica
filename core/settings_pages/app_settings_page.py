from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QLabel,
)
from PySide6.QtCore import Qt


class AppSettingsPage(QWidget):
    """
    Global application settings page.
    """

    def __init__(self, context):
        super().__init__()

        self.context = context
        self.settings = context.services.get("settings")

        layout = QVBoxLayout(self)

        title = QLabel("Application Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        form = QFormLayout()

        # ----------------------------
        # Theme
        # ----------------------------
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])

        current_theme = self.settings.get("app.theme", "dark")
        self.theme_combo.setCurrentText(current_theme)

        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)

        form.addRow("Theme:", self.theme_combo)

        # ----------------------------
        # Window Width
        # ----------------------------
        self.width_spin = QSpinBox()
        self.width_spin.setRange(600, 4000)

        current_width = self.settings.get("app.window_width", 1200)
        self.width_spin.setValue(current_width)

        self.width_spin.valueChanged.connect(self._on_size_changed)

        form.addRow("Window Width:", self.width_spin)

        # ----------------------------
        # Window Height
        # ----------------------------
        self.height_spin = QSpinBox()
        self.height_spin.setRange(400, 3000)

        current_height = self.settings.get("app.window_height", 800)
        self.height_spin.setValue(current_height)

        self.height_spin.valueChanged.connect(self._on_size_changed)

        form.addRow("Window Height:", self.height_spin)

        layout.addLayout(form)
        layout.addStretch()

    # ----------------------------
    # Handlers
    # ----------------------------

    def _on_theme_changed(self, value: str):
        self.settings.set("app.theme", value)

    def _on_size_changed(self):
        self.settings.set("app.window_width", self.width_spin.value())
        self.settings.set("app.window_height", self.height_spin.value())