from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QLabel,
)


class PaintSettingsPage(QWidget):
    """
    Paint Tracker settings page.
    """

    def __init__(self, context):
        super().__init__()

        self.context = context
        self.settings = context.services.get("settings")

        layout = QVBoxLayout(self)

        title = QLabel("Paint Tracker Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        form = QFormLayout()

        # Default Brand
        self.brand_input = QLineEdit()
        self.brand_input.setText(
            self.settings.get("paint_tracker.default_brand", "")
        )
        self.brand_input.textChanged.connect(self._save)

        form.addRow("Default Brand:", self.brand_input)

        # Default Type
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Base", "Layer", "Shade", "Dry", "Contrast"])

        current_type = self.settings.get("paint_tracker.default_type", "Base")
        self.type_combo.setCurrentText(current_type)
        self.type_combo.currentTextChanged.connect(self._save)

        form.addRow("Default Type:", self.type_combo)

        layout.addLayout(form)
        layout.addStretch()

    def _save(self):
        self.settings.set("paint_tracker.default_brand", self.brand_input.text())
        self.settings.set("paint_tracker.default_type", self.type_combo.currentText())