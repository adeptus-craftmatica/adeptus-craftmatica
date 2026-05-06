from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QWidget,
    QPushButton,
)
from PySide6.QtCore import Qt


class SettingsDialog(QDialog):
    """
    Main Settings Dialog

    Supports dynamic page registration.
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)

        self.context = context

        self.setWindowTitle("Settings")
        self.resize(800, 500)

        # Layout
        root_layout = QVBoxLayout(self)

        content_layout = QHBoxLayout()

        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)

        # Page stack
        self.pages = QStackedWidget()

        content_layout.addWidget(self.sidebar)
        content_layout.addWidget(self.pages)

        root_layout.addLayout(content_layout)

        # Bottom buttons
        button_layout = QHBoxLayout()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)

        root_layout.addLayout(button_layout)

        # Internal storage
        self._pages = []

        # Signals
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)

        # 🔥 NEW: Load pages dynamically
        self._load_pages()

    # ----------------------------
    # Dynamic Page Loading
    # ----------------------------

    def _load_pages(self):
        registry = self.context.services.get("settings_registry")

        if not registry:
            print("[SETTINGS WARNING] No registry found")
            return

        for name, factory in registry.get_pages():
            try:
                widget = factory(self.context)
                self.register_page(name, widget)
            except Exception as e:
                print(f"[SETTINGS ERROR] Failed to load page '{name}': {e}")

    # ----------------------------
    # Public API
    # ----------------------------

    def register_page(self, name: str, widget: QWidget):
        item = QListWidgetItem(name)
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.sidebar.addItem(item)
        self.pages.addWidget(widget)

        self._pages.append((name, widget))

        if self.sidebar.count() == 1:
            self.sidebar.setCurrentRow(0)