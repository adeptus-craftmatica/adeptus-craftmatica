"""
Adeptus Craftmatica — Paint Tracker Premium Mockup (Master Reference)
Standalone PySide6 proof-of-concept UI.

Run:
    pip install PySide6
    python paint_tracker_premium_mockup_master.py

Purpose:
    This file is a visual/reference mockup for redesigning the real Paint Tracker plugin.
    It has no database, no plugin integration, and no app dependencies beyond PySide6.

Design goals:
    - Premium dark UI
    - Clean visual hierarchy
    - No patchy native-widget artifacts
    - Cross-platform consistency on Windows, macOS, and Linux
    - Easy to tweak through centralized design tokens
    - Fully commented so you can understand what each section controls

Important:
    This mockup intentionally avoids QTableWidget because native table styling can create
    inconsistent visual artifacts across platforms. Instead, it uses custom row widgets.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


# =============================================================================
# MOCK DATA
# =============================================================================
# This represents fake paint inventory data.
# In the real application, this would come from your Paint Tracker service/repo.
#
# Changing this section affects:
#   - rows shown in the table
#   - metric card counts only if you manually update those values too
#   - visual examples of stock levels, color swatches, notes, etc.
# =============================================================================

@dataclass(frozen=True)
class Paint:
    favorite: bool
    brand: str
    name: str
    paint_type: str
    color_hex: str
    stock: str       # Expected: "Good", "Low", or "Out"
    qty: int
    level: str       # Expected: "Full", "Low", or "Out"
    notes: str


PAINTS: list[Paint] = [
    Paint(False, "Citadel", "Abaddon Black", "Base", "#0A0A0A", "Good", 2, "Full", "Perfect for dark armor."),
    Paint(True, "Citadel", "Agrax Earthshade", "Shade", "#5C4A39", "Good", 4, "Full", "Great all-over wash."),
    Paint(False, "Citadel", "Armageddon Dust", "Technical", "#E3D374", "Good", 1, "Full", "Dry pigment effect."),
    Paint(False, "Citadel", "Astrogranite", "Technical", "#8D8D8D", "Low", 2, "Low", "Always keep on hand."),
    Paint(False, "Citadel", "Balthasar Gold", "Base", "#B8985A", "Good", 2, "Full", "Rich gold tone."),
    Paint(False, "Citadel", "Bugman's Glow", "Base", "#7D3F36", "Good", 1, "Full", "Warm, earthy tone."),
    Paint(True, "Citadel", "Corax White", "Base", "#FFFFFF", "Low", 3, "Low", "Chalky — thin coats."),
    Paint(False, "Citadel", "Guilliman Flesh", "Contrast", "#E0B2A6", "Good", 1, "Full", ""),
    Paint(False, "Citadel", "Kantor Blue", "Base", "#001E5A", "Out", 1, "Out", "Restock soon!"),
    Paint(False, "Vallejo", "Game Air Black", "Air", "#1B1B1B", "Good", 2, "Full", "Smooth airbrush flow."),
    Paint(False, "Vallejo", "Titanium White", "Pigment", "#F4F1E8", "Good", 1, "Full", "Bright white pigment powder."),
    Paint(False, "AK Interactive", "Moss Texture", "Texture", "#3E5138", "Good", 1, "Full", "Great for bases and terrain."),
    Paint(False, "Golden", "High Flow Sepia", "Ink", "#6F4B2A", "Good", 1, "Full", "Great for glazing."),
    Paint(False, "Scale75", "Graphite", "Metallic", "#6D747A", "Low", 1, "Low", "Needs replacement soon."),
]


# =============================================================================
# DESIGN TOKENS
# =============================================================================
# This is the most important section for visual tuning.
#
# These values control the entire look of the mockup:
#   - background colors
#   - card colors
#   - text colors
#   - accent colors
#   - semantic colors for good/low/out states
#
# Changing these affects the whole UI.
#
# Design rule:
#   Keep the number of surfaces small.
#   Too many slightly different dark colors create the "patchy" feeling you noticed.
# =============================================================================

class T:
    # Base app background.
    # Changing this affects the entire page behind all cards/panels.
    bg = "#0B1118"

    # Main card/panel/row surface.
    # Used for metric cards, filter cards, rows, and table body.
    surface = "#121821"

    # Hover/intermediate surface.
    # Used when controls or rows need a subtle lifted state.
    surface_hover = "#182230"

    # Slightly raised surface.
    # Used for inputs, buttons, footer/header zones.
    surface_raised = "#162131"

    # Selected row/card surface.
    # Used for the currently selected paint row.
    surface_active = "#1E3555"

    # Borders/dividers.
    # Changing this affects card borders, row dividers, and structural lines.
    line = "#243244"
    line_soft = "#1A2635"

    # Text hierarchy.
    text = "#E6EDF3"      # primary text
    text_2 = "#9AAEC7"    # secondary text
    text_3 = "#6F8198"    # muted metadata

    # Primary app accent.
    # Used for active tabs, primary buttons, focus states.
    accent = "#3B82F6"
    accent_2 = "#60A5FA"

    # Semantic colors.
    green = "#22C55E"
    green_bg = "#123D2B"

    yellow = "#F59E0B"
    yellow_bg = "#3F2A0F"

    red = "#EF4444"
    red_bg = "#3A1D1D"

    purple = "#A855F7"
    purple_bg = "#2B1F3F"

    cyan = "#22D3EE"
    cyan_bg = "#10313A"

    orange = "#FB923C"
    orange_bg = "#3B2413"


# =============================================================================
# GLOBAL APPLICATION STYLESHEET
# =============================================================================
# This stylesheet controls native Qt widgets used in the mockup:
#   - QPushButton
#   - QToolButton
#   - QLineEdit
#   - QComboBox
#   - QScrollBar
#
# Most custom components are styled locally inside their classes.
#
# Why:
#   Keeping global styles small prevents unexpected conflicts.
#   Component-specific styles keep each widget predictable.
# =============================================================================

def app_stylesheet() -> str:
    return f"""
    QWidget {{
        background: {T.bg};
        color: {T.text};
        font-family: "Segoe UI", "Inter", "SF Pro Display", Arial, sans-serif;
        font-size: 14px;
    }}

    QMainWindow {{
        background: {T.bg};
    }}

    QScrollArea {{
        border: none;
        background: transparent;
    }}

    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    QLineEdit, QComboBox {{
        background: {T.surface_raised};
        color: {T.text};
        border: 1px solid {T.line};
        border-radius: 10px;
        padding: 10px 12px;
        min-height: 22px;
        selection-background-color: {T.accent};
    }}

    QLineEdit:focus, QComboBox:focus {{
        border: 1px solid {T.accent};
        background: {T.surface_hover};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 30px;
    }}

    QComboBox QAbstractItemView {{
        background: {T.surface};
        color: {T.text};
        border: 1px solid {T.line};
        selection-background-color: {T.surface_active};
    }}

    QPushButton, QToolButton {{
        background: {T.surface_raised};
        color: {T.text};
        border: 1px solid {T.line};
        border-radius: 10px;
        padding: 9px 14px;
        min-height: 22px;
        font-weight: 650;
    }}

    QPushButton:hover, QToolButton:hover {{
        background: {T.surface_hover};
        border-color: {T.accent};
    }}

    QPushButton:pressed, QToolButton:pressed {{
        background: {T.surface_active};
    }}

    QPushButton#primary {{
        background: {T.accent};
        border-color: {T.accent_2};
        color: white;
        font-weight: 800;
    }}

    QPushButton#primary:hover {{
        background: {T.accent_2};
    }}

    QPushButton#tabActive {{
        background: rgba(59, 130, 246, 0.20);
        border: 1px solid {T.accent};
        color: {T.text};
        font-weight: 800;
    }}

    QPushButton#tab {{
        background: transparent;
        border: 1px solid transparent;
        color: {T.text_2};
        font-weight: 650;
    }}

    QPushButton#tab:hover {{
        background: {T.surface_raised};
        border-color: {T.line};
    }}

    QPushButton#chip {{
        background: {T.surface_raised};
        border: 1px solid {T.line};
        border-radius: 16px;
        padding: 6px 12px;
        color: {T.text_2};
        font-weight: 700;
        min-height: 18px;
    }}

    QPushButton#chip:hover {{
        background: {T.surface_hover};
        color: {T.text};
    }}

    QPushButton#chipActive {{
        background: {T.accent};
        border: 1px solid {T.accent_2};
        border-radius: 16px;
        padding: 6px 14px;
        color: white;
        font-weight: 800;
        min-height: 18px;
    }}

    QPushButton#iconButton {{
        background: transparent;
        border: 1px solid {T.line};
        border-radius: 9px;
        padding: 6px;
        min-height: 20px;
        min-width: 20px;
        color: {T.text_2};
    }}

    QPushButton#iconButton:hover {{
        background: {T.surface_hover};
        border-color: {T.accent};
        color: {T.text};
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical {{
        background: #43536A;
        border-radius: 6px;
        min-height: 40px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: #566A86;
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 12px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal {{
        background: #43536A;
        border-radius: 6px;
        min-width: 40px;
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    """


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
# Helpers for repeated text/icon styling.
# =============================================================================

def transparent_label(text: str = "") -> QLabel:
    """Create a QLabel that will not add its own background."""
    label = QLabel(text)
    label.setStyleSheet("background: transparent;")
    return label


def set_label_font(label: QLabel, size: int, weight: int = QFont.Normal, color: str | None = None) -> QLabel:
    """
    Convenience helper for font size/weight.

    Changing this affects only labels passed through this helper.
    """
    font = label.font()
    font.setPointSize(size)
    font.setWeight(weight)
    label.setFont(font)
    if color:
        label.setStyleSheet(f"color: {color}; background: transparent;")
    return label


# =============================================================================
# BASE CARD COMPONENT
# =============================================================================
# Used for visual grouping.
#
# Changing Card affects:
#   - metric cards
#   - filter card
#   - paint table container
#   - any future card subclass
# =============================================================================

class Card(QFrame):
    def __init__(self, object_name: str = "card"):
        super().__init__()
        self.setObjectName(object_name)
        self.setStyleSheet(f"""
            QFrame#{object_name} {{
                background: {T.surface};
                border: 1px solid {T.line};
                border-radius: 14px;
            }}
        """)


# =============================================================================
# METRIC CARD
# =============================================================================
# Top stat cards: Total Paints, In Stock, Low Stock, etc.
#
# Changing MetricCard affects:
#   - top summary card layout
#   - icon circle size
#   - stat number hierarchy
#   - spacing inside metric cards
# =============================================================================

class MetricCard(Card):
    def __init__(self, icon: str, label: str, value: str, subtext: str, accent: str):
        super().__init__("metricCard")
        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(15)

        # Icon circle gives each metric a visual identity.
        icon_box = QLabel(icon)
        icon_box.setFixedSize(54, 54)
        icon_box.setAlignment(Qt.AlignCenter)
        icon_box.setStyleSheet(f"""
            QLabel {{
                background: rgba(255,255,255,0.035);
                border: 2px solid {accent};
                border-radius: 27px;
                color: {accent};
                font-size: 23px;
                font-weight: 900;
            }}
        """)

        labels = QVBoxLayout()
        labels.setSpacing(2)

        top = QLabel(label.upper())
        top.setStyleSheet(f"""
            color: {accent};
            background: transparent;
            font-size: 12px;
            font-weight: 900;
            letter-spacing: 0.8px;
        """)

        num = QLabel(value)
        num.setStyleSheet(f"""
            color: {T.text};
            background: transparent;
            font-size: 28px;
            font-weight: 900;
        """)

        sub = QLabel(subtext)
        sub.setStyleSheet(f"""
            color: {T.text_2};
            background: transparent;
            font-size: 13px;
        """)

        labels.addWidget(top)
        labels.addWidget(num)
        labels.addWidget(sub)

        root.addWidget(icon_box)
        root.addLayout(labels, 1)


# =============================================================================
# BADGE COMPONENT
# =============================================================================
# Used for paint type badges and stock status badges.
#
# Changing Badge affects:
#   - Type pills: Base, Shade, Technical, etc.
#   - Stock pills: Good, Low, Out
#
# Keep badge styling simple. Heavy shadows/borders can make the table feel busy.
# =============================================================================

class Badge(QLabel):
    def __init__(self, text: str, bg: str, fg: str = T.text):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(28)
        self.setStyleSheet(f"""
            QLabel {{
                background: {bg};
                color: {fg};
                border: 1px solid rgba(255,255,255,0.055);
                border-radius: 7px;
                padding: 4px 9px;
                font-weight: 800;
            }}
        """)


# =============================================================================
# COLOR SWATCH COMPONENT
# =============================================================================
# Shows a paint color as a small square + hex code.
#
# Changing Swatch affects:
#   - color column appearance
#   - swatch size
#   - hex-code readability
# =============================================================================

class Swatch(QWidget):
    def __init__(self, color_hex: str):
        super().__init__()
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        chip = QLabel()
        chip.setFixedSize(28, 28)
        chip.setStyleSheet(f"""
            QLabel {{
                background: {color_hex};
                border: 1px solid rgba(255,255,255,0.25);
                border-radius: 7px;
            }}
        """)

        code = QLabel(color_hex.upper())
        code.setStyleSheet(f"""
            color: {T.text_2};
            background: transparent;
            font-family: Consolas, "Courier New", monospace;
        """)

        layout.addWidget(chip)
        layout.addWidget(code)
        layout.addStretch()


# =============================================================================
# MINI LEVEL PROGRESS COMPONENT
# =============================================================================
# Shows Full/Low/Out plus a compact horizontal level bar.
#
# This deliberately uses layout instead of setGeometry so it scales better.
#
# Changing TinyProgress affects:
#   - Level column readability
#   - progress bar height/width
#   - colors for Full/Low/Out
# =============================================================================

class TinyProgress(QWidget):
    def __init__(self, level: str):
        super().__init__()
        self.setStyleSheet("background: transparent;")

        value = {"Full": 100, "Low": 35, "Out": 8}.get(level, 60)
        color = {"Full": T.green, "Low": T.yellow, "Out": T.red}.get(level, T.accent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        text = QLabel(level)
        text.setStyleSheet(f"""
            color: {color};
            background: transparent;
            font-weight: 900;
        """)

        # Track container.
        track = QFrame()
        track.setFixedHeight(7)
        track.setStyleSheet(f"""
            QFrame {{
                background: {T.line_soft};
                border-radius: 4px;
            }}
        """)

        track_layout = QHBoxLayout(track)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(0)

        fill = QFrame()
        fill.setFixedHeight(7)
        fill.setFixedWidth(max(8, int(116 * value / 100)))
        fill.setStyleSheet(f"""
            QFrame {{
                background: {color};
                border-radius: 4px;
            }}
        """)

        track_layout.addWidget(fill)
        track_layout.addStretch()

        root.addWidget(text)
        root.addWidget(track)


# =============================================================================
# TABLE HEADER
# =============================================================================
# Custom header row for the fake table.
#
# This is NOT a native QHeaderView, which avoids platform-specific table artifacts.
#
# Changing TableHeader affects:
#   - column titles
#   - table header height
#   - column width layout
# =============================================================================

class TableHeader(QFrame):
    COLUMN_LABELS = ["★", "BRAND", "NAME", "TYPE", "COLOR", "STOCK", "QTY", "LEVEL", "NOTES", "ACTIONS"]

    # These widths are shared by header and row.
    # If you change a number here, also update PaintRow.COLUMN_WIDTHS.
    COLUMN_WIDTHS = [42, 125, 215, 130, 190, 105, 70, 140, 1, 104]

    def __init__(self):
        super().__init__()
        self.setFixedHeight(48)
        self.setStyleSheet(f"""
            QFrame {{
                background: {T.surface_raised};
                border: 1px solid {T.line};
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }}
            QLabel {{
                background: transparent;
                color: {T.text_2};
                font-size: 12px;
                font-weight: 900;
                letter-spacing: 0.6px;
            }}
        """)

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 0, 12, 0)
        grid.setHorizontalSpacing(14)

        for i, name in enumerate(self.COLUMN_LABELS):
            label = QLabel(name)
            label.setAlignment(Qt.AlignCenter if i in (0, 6, 9) else Qt.AlignVCenter | Qt.AlignLeft)
            grid.addWidget(label, 0, i)

            width = self.COLUMN_WIDTHS[i]
            if width == 1:
                grid.setColumnStretch(i, 1)
            else:
                grid.setColumnMinimumWidth(i, width)


# =============================================================================
# PAINT ROW
# =============================================================================
# One custom row in the table.
#
# This is the most important visual component in the mockup.
#
# Changing PaintRow affects:
#   - table row height
#   - row hover behavior
#   - selection behavior
#   - column layout
#   - table density
#
# Design rule:
#   The row should be ONE visual surface.
#   Inner widgets should remain transparent unless they are badges/swatch/progress.
# =============================================================================

class PaintRow(QFrame):
    COLUMN_WIDTHS = TableHeader.COLUMN_WIDTHS

    def __init__(self, paint: Paint, selected: bool = False):
        super().__init__()
        self.paint = paint
        self.selected = selected

        # Row height controls table density.
        # Increase to 60+ for a more comfortable dashboard look.
        # Decrease to 48 for a denser inventory view.
        self.setFixedHeight(54)
        self.setCursor(Qt.PointingHandCursor)

        self._apply_row_style()

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 0, 12, 0)
        grid.setHorizontalSpacing(14)

        star = QLabel("★" if paint.favorite else "☆")
        star.setAlignment(Qt.AlignCenter)
        star.setStyleSheet(f"""
            color: {T.yellow if paint.favorite else T.text_2};
            font-size: 17px;
            background: transparent;
        """)

        brand = QLabel(f"◈  {paint.brand}")
        brand.setStyleSheet(f"color: {T.text}; background: transparent; font-weight: 650;")

        name = QLabel(paint.name)
        name.setStyleSheet(f"color: {T.text}; background: transparent; font-weight: 850;")

        type_badge = Badge(
            paint.paint_type,
            self._type_color(paint.paint_type),
            T.text,
        )

        stock_badge = Badge(
            paint.stock,
            {"Good": T.green_bg, "Low": T.yellow_bg, "Out": T.red_bg}.get(paint.stock, T.surface_hover),
            {"Good": T.green, "Low": T.yellow, "Out": T.red}.get(paint.stock, T.text),
        )

        qty = QLabel(str(paint.qty))
        qty.setAlignment(Qt.AlignCenter)
        qty.setStyleSheet(f"color: {T.text}; background: transparent; font-weight: 650;")

        notes = QLabel(paint.notes or "—")
        notes.setStyleSheet(f"color: {T.text_2}; background: transparent;")
        notes.setToolTip(paint.notes or "No notes")

        actions = self._actions_widget()

        cells: list[QWidget] = [
            star,
            brand,
            name,
            type_badge,
            Swatch(paint.color_hex),
            stock_badge,
            qty,
            TinyProgress(paint.level),
            notes,
            actions,
        ]

        for i, cell in enumerate(cells):
            grid.addWidget(cell, 0, i)

            width = self.COLUMN_WIDTHS[i]
            if width == 1:
                grid.setColumnStretch(i, 1)
            else:
                grid.setColumnMinimumWidth(i, width)

    def _apply_row_style(self) -> None:
        """Apply selected or normal row styling."""
        if self.selected:
            # Selected rows get a strong but clean accent.
            # The left border is intentional and helps selection feel premium.
            self.setStyleSheet(f"""
                QFrame {{
                    background: {T.surface_active};
                    border-left: 3px solid {T.accent};
                    border-bottom: 1px solid {T.line};
                }}
                QFrame:hover {{
                    background: #25466F;
                }}
                QLabel {{
                    background: transparent;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {T.surface};
                    border-bottom: 1px solid {T.line_soft};
                }}
                QFrame:hover {{
                    background: {T.surface_hover};
                }}
                QLabel {{
                    background: transparent;
                }}
            """)

    def _actions_widget(self) -> QWidget:
        """Create edit/delete icon buttons for each row."""
        actions = QWidget()
        actions.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(actions)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        edit = QPushButton("✎")
        delete = QPushButton("🗑")

        for button in (edit, delete):
            button.setObjectName("iconButton")
            button.setFixedSize(36, 34)
            button.setToolTip("Edit paint" if button is edit else "Delete paint")

        layout.addWidget(edit)
        layout.addWidget(delete)
        return actions

    @staticmethod
    def _type_color(paint_type: str) -> str:
        """Map paint type to badge color."""
        return {
            "Base": "#20334B",
            "Shade": "#17385F",
            "Technical": "#33264F",
            "Contrast": "#153B43",
            "Air": "#153B37",
            "Pigment": "#3A2E16",
            "Texture": "#22351E",
            "Ink": "#27315D",
            "Metallic": "#34313A",
        }.get(paint_type, T.surface_hover)


# =============================================================================
# PAINT TABLE
# =============================================================================
# Container holding:
#   - custom header
#   - scrollable row list
#   - footer/pagination area
#
# Changing PaintTable affects:
#   - full table shape
#   - footer appearance
#   - scroll behavior
# =============================================================================

class PaintTable(Card):
    def __init__(self, paints: Iterable[Paint]):
        super().__init__("paintTable")
        self.setStyleSheet(f"""
            QFrame#paintTable {{
                background: {T.surface};
                border: 1px solid {T.line};
                border-radius: 14px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(TableHeader())

        body_container = QWidget()
        body_container.setStyleSheet("background: transparent;")

        body = QVBoxLayout(body_container)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        for idx, paint in enumerate(paints):
            # idx == 5 is selected only for visual demonstration.
            body.addWidget(PaintRow(paint, selected=(idx == 5)))

        body.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(body_container)
        root.addWidget(scroll, 1)

        root.addWidget(self._footer())

    def _footer(self) -> QFrame:
        """Create table footer with rows-per-page and fake pagination."""
        footer = QFrame()
        footer.setFixedHeight(50)
        footer.setStyleSheet(f"""
            QFrame {{
                background: {T.surface_raised};
                border-top: 1px solid {T.line};
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }}
            QLabel {{
                background: transparent;
                color: {T.text_2};
            }}
        """)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(14, 0, 14, 0)

        layout.addWidget(QLabel("Rows per page:"))

        per_page = QComboBox()
        per_page.addItems(["25", "50", "100"])
        per_page.setFixedWidth(78)
        layout.addWidget(per_page)

        layout.addStretch()

        page = QLabel("‹    1    2    3    4    5    …    6    ›")
        page.setStyleSheet(f"color: {T.text}; background: transparent;")
        layout.addWidget(page)

        layout.addStretch()

        layout.addWidget(QLabel("1–25 of 133"))

        return footer


# =============================================================================
# FILTER CARD
# =============================================================================
# Contains:
#   - search field
#   - dropdown filters
#   - quick filter chips
#   - reset button
#
# Changing FilterCard affects:
#   - filter layout
#   - quick filter presentation
#   - search prominence
# =============================================================================

class FilterCard(Card):
    def __init__(self):
        super().__init__("filterCard")
        self.setStyleSheet(f"""
            QFrame#filterCard {{
                background: {T.surface};
                border: 1px solid {T.line};
                border-radius: 14px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addLayout(self._filter_row())
        root.addLayout(self._chip_row())

    def _filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        search = QLineEdit()
        search.setPlaceholderText("Search by brand, name, type, color or notes…")
        search.setMinimumHeight(42)
        row.addWidget(search, 4)

        for label in ["All Brands", "All Types", "All Stock Levels", "💧  Color"]:
            combo = QComboBox()
            combo.addItem(label)
            combo.setMinimumHeight(42)
            row.addWidget(combo, 1)

        more_filters = QPushButton("⚱  More Filters")
        more_filters.setMinimumHeight(42)
        row.addWidget(more_filters)

        return row

    def _chip_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        label = QLabel("Quick Filters:")
        label.setStyleSheet(f"background: transparent; color: {T.text_2}; font-weight: 700;")
        row.addWidget(label)

        for text, active in [
            ("All", True),
            ("⚠  Low Stock", False),
            ("×  Out of Stock", False),
            ("★  Favorites", False),
            ("⟳  Recently Added", False),
        ]:
            chip = QPushButton(text)
            chip.setObjectName("chipActive" if active else "chip")
            chip.setMinimumHeight(32)
            row.addWidget(chip)

        row.addStretch()

        count = QLabel("133 paints")
        count.setStyleSheet(f"background: transparent; color: {T.text};")
        row.addWidget(count)

        reset = QPushButton("↻  Reset Filters")
        reset.setMinimumHeight(32)
        row.addWidget(reset)

        return row


# =============================================================================
# MAIN WINDOW
# =============================================================================
# Builds the full page:
#   - header
#   - metrics
#   - tabs
#   - filters
#   - table
#
# Changing PaintTrackerMockup affects:
#   - page-level spacing
#   - overall content order
#   - top-level window size
# =============================================================================

class PaintTrackerMockup(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Adeptus Craftmatica — Paint Tracker Premium Mockup")
        self.resize(1500, 900)
        self.setMinimumSize(1180, 760)

        self._build()

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        page = QVBoxLayout(root)

        # Page margins control how much breathing room the entire UI has.
        # Increase for a spacious dashboard feel.
        # Decrease for a denser desktop-app feel.
        page.setContentsMargins(18, 18, 18, 18)
        page.setSpacing(16)

        page.addLayout(self._header())
        page.addLayout(self._metrics())
        page.addLayout(self._tabs())
        page.addWidget(FilterCard())
        page.addWidget(PaintTable(PAINTS), 1)

    def _header(self) -> QHBoxLayout:
        """Top title/subtitle and primary actions."""
        header = QHBoxLayout()
        header.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(5)

        title = QLabel("🎨  Paint Tracker")
        title.setStyleSheet(f"""
            font-size: 30px;
            font-weight: 900;
            color: {T.text};
            background: transparent;
        """)

        subtitle = QLabel("Track your paint collection, stock levels, favorites, and usage.")
        subtitle.setStyleSheet(f"""
            font-size: 14px;
            color: {T.text_2};
            background: transparent;
        """)

        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        header.addLayout(title_col)
        header.addStretch()

        import_btn = QPushButton("⇧  Import CSV")
        add_btn = QPushButton("＋  Add Paint")
        add_btn.setObjectName("primary")

        more = QToolButton()
        more.setText("⋮")
        more.setFixedWidth(46)
        more.setToolTip("More actions")

        for button in (import_btn, add_btn, more):
            button.setMinimumHeight(42)

        header.addWidget(import_btn)
        header.addWidget(add_btn)
        header.addWidget(more)

        return header

    def _metrics(self) -> QHBoxLayout:
        """Top metric card row."""
        metrics = QHBoxLayout()
        metrics.setSpacing(12)

        cards = [
            ("🧰", "Total Paints", "133", "paints in collection", T.accent),
            ("✓", "In Stock", "118", "88.7% of collection", T.green),
            ("⚠", "Low Stock", "9", "need restocking", T.yellow),
            ("×", "Out of Stock", "6", "out of stock", T.red),
            ("★", "Favorites", "24", "marked as favorite", T.purple),
        ]

        for args in cards:
            metrics.addWidget(MetricCard(*args))

        return metrics

    def _tabs(self) -> QHBoxLayout:
        """Collection/Statistics tabs."""
        tabs = QHBoxLayout()
        tabs.setSpacing(8)

        collection = QPushButton("▣  Collection")
        stats = QPushButton("⌁  Statistics")

        collection.setObjectName("tabActive")
        stats.setObjectName("tab")

        collection.setMinimumSize(150, 44)
        stats.setMinimumSize(150, 44)

        tabs.addWidget(collection)
        tabs.addWidget(stats)
        tabs.addStretch()

        return tabs


# =============================================================================
# APPLICATION BOOTSTRAP
# =============================================================================
# Cross-platform setup.
#
# Fusion style + dark palette help make Windows/macOS/Linux more consistent.
#
# Changing this section affects:
#   - platform consistency
#   - base native widget rendering
#   - HiDPI behavior
# =============================================================================

def main() -> int:
    # These attributes help on high-DPI displays.
    # They are harmless on most desktop systems.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Adeptus Craftmatica Paint Tracker Mockup")

    # Fusion is more consistent across Windows/macOS/Linux than native styles.
    app.setStyle("Fusion")

    # Dark palette reduces native-widget surprises.
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(T.bg))
    palette.setColor(QPalette.WindowText, QColor(T.text))
    palette.setColor(QPalette.Base, QColor(T.surface))
    palette.setColor(QPalette.AlternateBase, QColor(T.surface_raised))
    palette.setColor(QPalette.Text, QColor(T.text))
    palette.setColor(QPalette.Button, QColor(T.surface_raised))
    palette.setColor(QPalette.ButtonText, QColor(T.text))
    palette.setColor(QPalette.Highlight, QColor(T.accent))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)

    app.setStyleSheet(app_stylesheet())

    win = PaintTrackerMockup()
    win.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
