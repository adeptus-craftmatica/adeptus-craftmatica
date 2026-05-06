"""
core/theme_manager.py
═══════════════════════════════════════════════════════════════════════════════
ThemeManager — central theme loading, compilation, and application.

Pipeline
────────
  JSON file → Theme dataclass → token dict → QSS string → QApplication

Token substitution uses a simple regex: {token_name} in the template is
replaced by the corresponding string value from Theme.tokens().  Regular CSS
curly-braces are safe because CSS property names and values never form valid
token patterns (they contain colons, spaces, or digits at the start).

Usage
─────
    tm: ThemeManager = context.services.get("theme_manager")
    tm.apply_theme("dark_midnight")          # switch theme
    color = tm.token("accent")              # "#4f9eff"
    tm.theme_changed.connect(my_slot)       # react to changes
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer, QThread, Qt
from PySide6.QtWidgets import QApplication

from core.theme import (
    Theme, ThemeMeta, ThemeColors, ThemeTypography, ThemeShape,
    theme_from_paint_scheme,
)

# ── QSS template ──────────────────────────────────────────────────────────────
# Tokens are written as {token_name}.  All color names map 1-to-1 with
# ThemeColors field names; numeric tokens (radii, font sizes) have no unit —
# the template appends px where needed.

_QSS_TEMPLATE = """
/* ════════════════════════════════════════════════════════════════════════════
   ADEPTUS CRAFTMATICA  |  Generated Theme Stylesheet
   All values injected from the active Theme object by ThemeManager.
   ════════════════════════════════════════════════════════════════════════════ */

/* ── Reset ──────────────────────────────────────────────────────────────── */
* {{ outline: none; }}

/* ── Base ───────────────────────────────────────────────────────────────── */
QWidget {{
    background-color: {bg_base};
    color: {text_mid};
    font-family: "{font_family}", system-ui, sans-serif;
    font-size: {font_lg}px;
}}
QWidget:disabled {{ color: {text_dim}; }}

QMainWindow, QDialog {{
    background-color: {bg_deep};
}}

/* ── Typography ─────────────────────────────────────────────────────────── */
QLabel#pageTitle {{
    font-size: {font_3xl}px;
    font-weight: 700;
    color: {text_hi};
    background: transparent;
    padding-bottom: 4px;
    letter-spacing: -0.3px;
}}

QLabel {{
    color: {text_mid};
    background: transparent;
}}

QLabel#fieldLabel {{
    color: {text_lo};
    font-size: {font_sm}px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background: transparent;
}}

QLabel#sectionTitle {{
    color: {text_hi};
    font-size: {font_xl}px;
    font-weight: 600;
    background: transparent;
}}

QLabel#metaLabel {{
    color: {text_dim};
    font-size: {font_xs}px;
    background: transparent;
}}

QLabel#statusOk    {{ color: {success}; font-weight: 600; background: transparent; }}
QLabel#statusError {{ color: {danger};  font-weight: 600; background: transparent; }}
QLabel#statusWarn  {{ color: {warning}; font-weight: 600; background: transparent; }}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {bg_input};
    color: {text_hi};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
    padding: 6px 10px;
    min-height: 18px;
    selection-background-color: {accent};
    selection-color: #ffffff;
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {border_hi};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {accent};
    background-color: {bg_raised};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {bg_base};
    color: {text_dim};
    border-color: {border};
}}
QLineEdit::placeholder {{ color: {text_dim}; }}

QTextEdit, QPlainTextEdit {{
    background-color: {bg_input};
    color: {text_hi};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
    padding: 6px 10px;
    selection-background-color: {accent};
    selection-color: #ffffff;
}}
QTextEdit:hover, QPlainTextEdit:hover  {{ border-color: {border_hi}; }}
QTextEdit:focus, QPlainTextEdit:focus  {{ border-color: {accent}; background-color: {bg_raised}; }}
QTextEdit:disabled, QPlainTextEdit:disabled {{
    background-color: {bg_base};
    color: {text_dim};
    border-color: {border};
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 18px;
    background: {bg_raised};
    border: none;
    border-radius: 2px;
    margin: 1px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {border_hi};
}}

/* ── ComboBox ───────────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {bg_input};
    color: {text_hi};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
    padding: 6px 10px;
    min-height: 18px;
}}
QComboBox:hover  {{ border-color: {border_hi}; }}
QComboBox:focus  {{ border-color: {accent}; background-color: {bg_raised}; }}
QComboBox:disabled {{ background-color: {bg_base}; color: {text_dim}; }}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 24px;
    border: none;
    border-left: 1px solid {border};
    border-top-right-radius: {radius_sm}px;
    border-bottom-right-radius: {radius_sm}px;
    background: transparent;
}}
QComboBox::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {text_lo};
    width: 0; height: 0;
}}
QComboBox QAbstractItemView {{
    background-color: {bg_input};
    color: {text_hi};
    border: 1px solid {border_hi};
    border-radius: {radius_sm}px;
    selection-background-color: {accent};
    selection-color: #ffffff;
    padding: 3px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    min-height: 24px;
    border-radius: {radius_xs}px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {bg_raised};
}}

/* ── Buttons ────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {bg_raised};
    color: {text_mid};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
    padding: 7px 16px;
    font-weight: 500;
    min-width: 64px;
}}
QPushButton:hover   {{
    background-color: {bg_input};
    border-color: {border_hi};
    color: {text_hi};
}}
QPushButton:pressed {{
    background-color: {bg_base};
    border-color: {border_hi};
    color: {text_mid};
}}
QPushButton:disabled {{
    background-color: {bg_base};
    color: {text_dim};
    border-color: {border};
}}
QPushButton:checked {{
    background-color: {accent};
    border-color: {accent};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton:checked:hover {{
    background-color: {accent_hi};
    border-color: {accent_hi};
}}

QPushButton[class="primary"] {{
    background-color: {accent};
    color: #ffffff;
    border-color: {accent};
    font-weight: 600;
}}
QPushButton[class="primary"]:hover   {{ background-color: {accent_hi}; border-color: {accent_hi}; }}
QPushButton[class="primary"]:pressed {{ background-color: {accent}; opacity: 0.85; }}
QPushButton[class="primary"]:disabled {{
    background-color: {accent_lo};
    color: {text_dim};
    border-color: {accent_lo};
}}

QPushButton[class="danger"] {{
    background-color: {danger_lo};
    color: {danger};
    border-color: {danger_lo};
}}
QPushButton[class="danger"]:hover   {{
    background-color: {danger_lo};
    border-color: {danger};
    color: {danger_hi};
}}
QPushButton[class="danger"]:pressed {{ background-color: {danger}; color: #ffffff; border-color: {danger}; }}

QPushButton[class="ghost"] {{
    background-color: transparent;
    color: {text_lo};
    border-color: transparent;
}}
QPushButton[class="ghost"]:hover   {{ background-color: {bg_raised}; color: {text_mid}; }}
QPushButton[class="ghost"]:pressed {{ background-color: {bg_input}; }}

/* ── Checkboxes & Radio buttons ─────────────────────────────────────────── */
QCheckBox, QRadioButton {{
    color: {text_mid};
    spacing: 8px;
    background: transparent;
}}
QCheckBox:hover, QRadioButton:hover {{ color: {text_hi}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {text_dim}; }}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {border_hi};
    border-radius: {radius_xs}px;
    background: {bg_input};
}}
QCheckBox::indicator:hover   {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
    image: none;
}}
QCheckBox::indicator:checked:hover {{ background-color: {accent_hi}; border-color: {accent_hi}; }}

QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {border_hi};
    border-radius: 8px;
    background: {bg_input};
}}
QRadioButton::indicator:hover   {{ border-color: {accent}; }}
QRadioButton::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
}}

/* ── Group Boxes ────────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_lg}px;
    margin-top: 20px;
    padding: 16px 14px 14px 14px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: -1px;
    padding: 2px 8px;
    background-color: {bg_raised};
    color: {text_lo};
    font-size: {font_sm}px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    border-radius: {radius_xs}px;
}}
QDialog QGroupBox::title {{ background-color: {bg_raised}; }}

/* ── Tab Widget ─────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    background: transparent;
    border: none;
}}
QTabWidget::tab-bar {{ alignment: left; }}

QTabBar {{
    background: {sidebar_bg};
    border-bottom: 1px solid {border};
}}
QTabBar::tab {{
    background: transparent;
    color: {text_dim};
    border: none;
    border-radius: {radius_sm}px;
    padding: 6px 18px;
    margin: 6px 2px;
    font-size: {font_base}px;
    font-weight: 500;
    min-width: 64px;
}}
QTabBar::tab:selected {{
    background: {accent};
    color: #ffffff;
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: {bg_raised};
    color: {text_lo};
}}

/* ── Tables (QTableWidget + QTableView) ─────────────────────────────────── */
QTableWidget, QTableView {{
    background-color: {bg_base};
    alternate-background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_base}px;
    gridline-color: transparent;
    selection-background-color: {accent_lo};
    selection-color: {text_hi};
}}
QTableWidget::item, QTableView::item {{
    padding: 6px 10px;
    border: none;
    color: {text_mid};
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {accent_lo};
    color: {text_hi};
}}
QTableWidget::item:hover:!selected, QTableView::item:hover:!selected {{
    background-color: {bg_raised};
}}

QHeaderView {{ background-color: transparent; border: none; }}
QHeaderView::section {{
    background-color: {bg_deep};
    color: {text_lo};
    padding: 8px 10px;
    border: none;
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    font-size: {font_sm}px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
QHeaderView::section:first {{ border-top-left-radius: {radius_sm}px; }}
QHeaderView::section:last  {{ border-right: none; border-top-right-radius: {radius_sm}px; }}
QHeaderView::section:hover {{ background-color: {bg_raised}; color: {text_mid}; }}
QHeaderView::section:checked  {{ color: {text_hi}; }}
QHeaderView::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {text_lo};
    width: 0; height: 0;
    subcontrol-origin: padding;
    subcontrol-position: right center;
    margin-right: 6px;
}}
QHeaderView::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {text_lo};
    width: 0; height: 0;
    subcontrol-origin: padding;
    subcontrol-position: right center;
    margin-right: 6px;
}}

/* ── List Widget ────────────────────────────────────────────────────────── */
QListWidget {{
    background-color: {bg_base};
    alternate-background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_base}px;
    outline: none;
}}
QListWidget::item {{
    padding: 7px 12px;
    color: {text_mid};
    border-radius: {radius_xs}px;
}}
QListWidget::item:selected {{
    background-color: {accent_lo};
    color: {text_hi};
}}
QListWidget::item:hover:!selected {{ background-color: {bg_raised}; }}
QListWidget::item:selected:!active {{
    background-color: {bg_raised};
    color: {text_mid};
}}

/* ── Tree Widget ────────────────────────────────────────────────────────── */
QTreeWidget {{
    background-color: {bg_base};
    alternate-background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_base}px;
    outline: none;
    show-decoration-selected: 1;
}}
QTreeWidget::item {{
    padding: 5px 6px;
    color: {text_mid};
    border: none;
}}
QTreeWidget::item:selected  {{ background-color: {accent_lo}; color: {text_hi}; }}
QTreeWidget::item:hover:!selected {{ background-color: {bg_raised}; }}
QTreeWidget::item:selected:!active {{ background-color: {bg_raised}; color: {text_mid}; }}
QTreeWidget::branch {{ background: transparent; }}

/* ── Scrollbars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {border_hi}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0 2px;
}}
QScrollBar::handle:horizontal {{
    background: {border};
    border-radius: 4px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background: {border_hi}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Progress Bar ───────────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {bg_input};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
    text-align: center;
    color: {text_mid};
    font-weight: 600;
    font-size: {font_sm}px;
    min-height: 10px;
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: {radius_sm}px;
}}

/* ── Splitter ───────────────────────────────────────────────────────────── */
QSplitter::handle            {{ background: {bg_raised}; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QSplitter::handle:vertical   {{ height: 3px; }}
QSplitter::handle:hover      {{ background: {accent}; }}
QSplitter::handle:pressed    {{ background: {accent_hi}; }}

/* ── Frames ─────────────────────────────────────────────────────────────── */
QFrame[frameShape="4"] {{ color: {border};  max-height: 1px; }}   /* HLine */
QFrame[frameShape="5"] {{ color: {border};  max-width:  1px; }}   /* VLine */
QFrame[frameShape="6"] {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_base}px;
}}

/* ── Menus ──────────────────────────────────────────────────────────────── */
QMenuBar {{
    background-color: {header_bg};
    border-bottom: 1px solid {border};
    padding: 2px 4px;
}}
QMenuBar::item {{ background: transparent; padding: 5px 12px; border-radius: {radius_sm}px; }}
QMenuBar::item:selected {{ background-color: {bg_raised}; color: {text_hi}; }}

QMenu {{
    background-color: {bg_input};
    border: 1px solid {border_hi};
    border-radius: {radius_base}px;
    padding: 4px;
}}
QMenu::item {{ padding: 7px 24px 7px 14px; border-radius: {radius_xs}px; color: {text_mid}; }}
QMenu::item:selected {{ background-color: {accent}; color: #ffffff; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 10px; }}

/* ── Tooltips ───────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {bg_input};
    color: {text_hi};
    border: 1px solid {border_hi};
    border-radius: {radius_sm}px;
    padding: 5px 10px;
    font-size: {font_base}px;
}}

/* ── Scroll Area ────────────────────────────────────────────────────────── */
QScrollArea         {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ── Message Box ────────────────────────────────────────────────────────── */
QMessageBox         {{ background-color: {bg_base}; }}
QDialogButtonBox QPushButton {{ min-width: 84px; }}

/* ── Detail / Edit Panel (Model Tracker) ────────────────────────────────── */
QWidget#detailPanel {{
    background-color: {card_bg};
}}
QWidget#detailPanel QLabel#fieldLabel {{ color: {text_dim}; }}
QWidget#detailPanel QLineEdit,
QWidget#detailPanel QComboBox,
QWidget#detailPanel QTextEdit,
QWidget#detailPanel QSpinBox {{
    background-color: {bg_raised};
    border-color: {border};
}}
QWidget#detailPanel QLineEdit:focus,
QWidget#detailPanel QComboBox:focus,
QWidget#detailPanel QTextEdit:focus,
QWidget#detailPanel QSpinBox:focus {{
    border-color: {accent};
    background-color: {bg_input};
}}

/* ── Panel headers (detail view strip bars) ─────────────────────────────── */
QWidget#panelHeader {{
    background-color: {bg_raised};
    border-bottom: 1px solid {border};
}}
QWidget#panelHeader QLabel {{
    background: transparent;
    color: {text_mid};
}}
QWidget#panelHeader QLabel#pageTitle {{
    color: {text_hi};
}}
QWidget#panelHeader QLabel#headerSub {{
    color: {text_lo};
    font-size: {font_base}px;
}}
QWidget#panelHeader QLabel#headerStatus {{
    color: {text_dim};
    font-size: {font_sm}px;
    font-weight: 600;
}}

/* ── Dice Roller ─────────────────────────────────────────────────────────── */
QLabel#diceResult {{
    font-size: 56px;
    font-weight: 700;
    color: {accent};
    letter-spacing: 4px;
    background: transparent;
}}

/* ── Card labels (campaign cards, model cards, etc.) ───────────────────── */
QLabel#cardTitle {{
    font-size: {font_xl}px;
    font-weight: 700;
    color: {text_hi};
    background: transparent;
}}
QLabel#cardDesc {{
    font-size: {font_sm}px;
    color: {text_dim};
    background: transparent;
}}
QLabel#cardThumb {{
    background-color: {bg_raised};
    border-radius: {radius_sm}px;
    color: {text_dim};
    font-size: 20px;
}}

/* ── Side panels (encounter builder left column, etc.) ──────────────────── */
QWidget#sidePanel {{
    background-color: {sidebar_bg};
    border-right: 1px solid {border};
}}
QWidget#sidePanel QLabel {{
    background: transparent;
    color: {text_mid};
}}
QLabel#sidePanelTitle {{
    font-size: {font_lg}px;
    font-weight: 700;
    color: {text_hi};
    background: transparent;
}}

/* ── Nav bar (Campaign Tracker pill buttons) ────────────────────────────── */
QWidget#ctNavBar {{
    background-color: {sidebar_bg};
    border-bottom: 1px solid {border};
}}
QWidget#ctNavBar QPushButton {{
    background: transparent;
    color: {text_dim};
    border: none;
    border-radius: {radius_sm}px;
    padding: 6px 18px;
    font-size: {font_base}px;
    font-weight: 500;
    min-width: 64px;
}}
QWidget#ctNavBar QPushButton:hover   {{ background: {bg_raised}; color: {text_lo}; }}
QWidget#ctNavBar QPushButton:checked {{ background: {accent}; color: #ffffff; font-weight: 600; }}

/* ── Project Tracker ────────────────────────────────────────────────────── */
QWidget#projectListPanel {{
    background-color: {sidebar_bg};
    border-right: 1px solid {border};
}}
QWidget#panelHeader {{
    background-color: {sidebar_bg};
    border-bottom: 1px solid {border};
}}
QLabel#panelTitle {{
    font-size: {font_lg}px;
    font-weight: 700;
    color: {text_hi};
    background: transparent;
}}

/* Project cards (left sidebar) */
QFrame#projectCard {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
}}
QFrame#projectCard:hover {{
    border-color: {border_hi};
    background-color: {bg_input};
}}
QFrame#projectCard[selected="true"] {{
    border-color: {accent};
    background-color: {bg_input};
}}
QLabel#projectCardName {{
    font-size: {font_base}px;
    font-weight: 600;
    color: {text_hi};
    background: transparent;
}}
QLabel#projectCardSub {{
    font-size: {font_xs}px;
    color: {text_dim};
    background: transparent;
}}

/* Status badges */
QLabel#statusBadge, QLabel#statusBadgeLarge {{
    border-radius: {radius_xs}px;
    font-size: {font_xs}px;
    font-weight: 700;
    padding: 2px 8px;
}}
QLabel#statusBadge[status="active"],    QLabel#statusBadgeLarge[status="active"]    {{ background: {success}22; color: {success}; border: 1px solid {success}44; }}
QLabel#statusBadge[status="completed"], QLabel#statusBadgeLarge[status="completed"] {{ background: {accent}22;  color: {accent};  border: 1px solid {accent}44;  }}
QLabel#statusBadge[status="on_hold"],   QLabel#statusBadgeLarge[status="on_hold"]   {{ background: {warning}22; color: {warning}; border: 1px solid {warning}44; }}
QLabel#statusBadge[status="archived"],  QLabel#statusBadgeLarge[status="archived"]  {{ background: {bg_raised}; color: {text_dim}; border: 1px solid {border}; }}

/* Detail panel */
QWidget#detailToolbar {{
    background-color: {bg_raised};
    border-bottom: 1px solid {border};
}}
QFrame#projectHeaderCard {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_base}px;
}}
QLabel#projectDetailName {{
    font-size: {font_2xl}px;
    font-weight: 700;
    color: {text_hi};
    background: transparent;
}}
QLabel#projectDetailSystem {{
    font-size: {font_base}px;
    color: {accent};
    font-weight: 600;
    background: transparent;
}}
QLabel#projectDetailDesc {{
    font-size: {font_sm}px;
    color: {text_lo};
    background: transparent;
}}

/* Mini stat cards */
QFrame#miniStatCard {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
}}
QLabel#miniStatValue {{
    font-size: {font_xl}px;
    font-weight: 700;
    color: {text_hi};
    background: transparent;
}}
QLabel#miniStatLabel {{
    font-size: {font_xs}px;
    color: {text_dim};
    background: transparent;
}}

/* Milestones */
QFrame#milestoneRow {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
}}
QLabel#milestoneTitlePending {{ color: {text_hi}; font-weight: 500; background: transparent; }}
QLabel#milestoneTitleDone    {{ color: {text_dim}; text-decoration: line-through; background: transparent; }}
QLabel#milestoneTitleOverdue {{ color: {danger}; font-weight: 600; background: transparent; }}
QLabel#milestonePreviewLabel {{ color: {text_mid}; font-size: {font_sm}px; background: transparent; }}

/* Notes */
QWidget#notesListPanel {{
    background-color: {sidebar_bg};
    border-right: 1px solid {border};
}}
QLineEdit#noteTitleEdit {{
    font-size: {font_lg}px;
    font-weight: 600;
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {border};
    border-radius: 0;
    color: {text_hi};
    padding: 4px 0;
}}
QLineEdit#noteTitleEdit:focus {{ border-bottom-color: {accent}; }}
QTextEdit#noteBodyEdit {{
    background-color: transparent;
    border: none;
    color: {text_mid};
    font-size: {font_base}px;
    line-height: 1.6;
}}
QPushButton#noteListItem {{
    text-align: left;
    padding: 6px 8px;
    border-radius: {radius_sm}px;
    color: {text_lo};
    font-size: {font_sm}px;
}}
QPushButton#noteListItem:hover {{ background-color: {bg_raised}; color: {text_hi}; }}

/* Sessions */
QFrame#sessionRow {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
}}
QLabel#sessionLabel   {{ color: {text_hi}; font-weight: 500; background: transparent; }}
QLabel#sessionSummary {{ color: {accent}; font-size: {font_sm}px; font-weight: 600; background: transparent; }}

/* Form card */
QFrame#formCard {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
}}

/* Links */
QLabel#linkItemLabel {{ color: {text_hi}; background: transparent; }}

/* Misc shared */
QLabel#sectionLabel {{
    font-size: {font_xs}px;
    font-weight: 700;
    color: {text_dim};
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#dimLabel  {{ color: {text_dim}; font-size: {font_xs}px; background: transparent; }}
QLabel#emptyState {{
    color: {text_dim};
    font-size: {font_base}px;
    background: transparent;
    padding: 24px;
}}

/* ── Linked Entity Chips (shared relationship widgets) ─────────────────── */
QFrame#linkedEntityChip {{
    background: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
}}
QFrame#linkedEntityChip:hover {{
    background: {card_bg};
    border-color: {accent};
}}
QLabel#chipName {{
    font-size: 11px;
    font-weight: 600;
    color: {text_hi};
    background: transparent;
}}
QLabel#chipSubtitle {{
    font-size: 9px;
    color: {text_lo};
    background: transparent;
}}
QPushButton#chipNavBtn {{
    background: transparent;
    border: none;
    color: {text_lo};
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#chipNavBtn:hover {{ color: {accent}; }}
QPushButton#chipUnlinkBtn {{
    background: transparent;
    border: none;
    color: {text_dim};
    font-size: 10px;
    font-weight: 600;
}}
QPushButton#chipUnlinkBtn:hover {{ color: {danger}; }}
QLabel#relatedSectionTitle {{
    font-size: {font_xs}px;
    font-weight: 700;
    color: {text_lo};
    letter-spacing: 0.8px;
    background: transparent;
}}

/* ── Toast notifications ───────────────────────────────────────────────── */
QLabel#toastSuccess {{
    background: {success};
    color: #ffffff;
    border-radius: {radius_base}px;
    font-size: {font_sm}px;
    font-weight: 600;
    padding: 8px 20px;
}}
QLabel#toastError {{
    background: {danger};
    color: #ffffff;
    border-radius: {radius_base}px;
    font-size: {font_sm}px;
    font-weight: 600;
    padding: 8px 20px;
}}
QLabel#toastWarning {{
    background: {warning};
    color: #ffffff;
    border-radius: {radius_base}px;
    font-size: {font_sm}px;
    font-weight: 600;
    padding: 8px 20px;
}}
QLabel#toastInfo {{
    background: {accent};
    color: #ffffff;
    border-radius: {radius_base}px;
    font-size: {font_sm}px;
    font-weight: 600;
    padding: 8px 20px;
}}

/* ── Form status labels (inline, non-blocking) ─────────────────────────── */
QLabel#formStatusErr  {{ color: {danger};  font-size: {font_sm}px; background: transparent; }}
QLabel#formStatusWarn {{ color: {warning}; font-size: {font_sm}px; background: transparent; }}
QLabel#formStatusOk   {{ color: {success}; font-size: {font_sm}px; background: transparent; }}

/* Close/dismiss buttons used in slide-in panels */
QPushButton#panelCloseBtn {{
    font-size: 14px;
    color: {text_dim};
    border: none;
    background: transparent;
}}
QPushButton#panelCloseBtn:hover {{ color: {danger}; }}

/* Danger button */
QPushButton#dangerBtn {{
    background: {danger}22;
    border: 1px solid {danger}44;
    border-radius: {radius_sm}px;
    color: {danger};
    font-size: {font_sm}px;
    padding: 5px 14px;
}}
QPushButton#dangerBtn:hover {{
    background: {danger}44;
    border-color: {danger};
}}

/* Success button (mark complete) */
QPushButton#successBtn {{
    background: {success}22;
    border: 1px solid {success}44;
    border-radius: {radius_sm}px;
    color: {success};
    font-size: {font_sm}px;
    padding: 5px 14px;
}}
QPushButton#successBtn:hover {{
    background: {success}44;
    border-color: {success};
}}

/* Progress bars — shared base */
QProgressBar#overallProgressBar,
QProgressBar#milestoneProgressBar,
QProgressBar#paintingProgressBar {{
    background-color: {bg_input};
    border: none;
    border-radius: {radius_sm}px;
}}
QProgressBar#overallProgressBar::chunk {{
    background-color: {accent};
    border-radius: {radius_sm}px;
}}
QProgressBar#milestoneProgressBar::chunk {{
    background-color: {success};
    border-radius: {radius_sm}px;
}}
QProgressBar#paintingProgressBar::chunk {{
    background-color: {warning};
    border-radius: {radius_sm}px;
}}

/* Progress row typography */
QLabel#progressRowLabel {{
    font-size: {font_sm}px;
    font-weight: 600;
    color: {text_hi};
    background: transparent;
}}
QLabel#progressPctLabel {{
    font-size: {font_sm}px;
    font-weight: 700;
    color: {accent};
    background: transparent;
    min-width: 36px;
}}
QFrame#progressFrame {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
}}

/* ── Paint Tracker statistics ────────────────────────────────────────────── */

QFrame#statCard {{
    background-color: {card_bg};
    border: 1px solid {border};
    border-radius: {radius_base}px;
}}
QLabel#statCardLabel {{
    font-size: {font_xs}px;
    font-weight: 700;
    color: {text_lo};
    letter-spacing: 0.8px;
    background: transparent;
}}
QLabel#statCardValue {{
    font-size: 32px;
    font-weight: 700;
    color: {accent};
    background: transparent;
}}
QLabel#statCardValueWarn {{
    font-size: 32px;
    font-weight: 700;
    color: {warning};
    background: transparent;
}}
QFrame#distCard {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_base}px;
}}
QLabel#distCardTitle {{
    font-size: {font_base}px;
    font-weight: 700;
    color: {text_mid};
    background: transparent;
}}

/* ── Paint Tracker quick-filter preset chips ─────────────────────────────── */

QFrame#presetChipBar {{
    background: transparent;
    border: none;
}}
QLabel#presetChipLabel {{
    font-size: {font_xs}px;
    color: {text_lo};
    background: transparent;
}}
QPushButton#presetChip {{
    background-color: {bg_raised};
    color: {text_mid};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 1px 10px;
    font-size: {font_xs}px;
    font-weight: 500;
}}
QPushButton#presetChip:hover {{
    background-color: {bg_input};
    border-color: {accent};
    color: {text_hi};
}}
QPushButton#presetChip:checked {{
    background-color: {accent};
    border-color: {accent};
    color: #ffffff;
    font-weight: 700;
}}
QPushButton#presetChip:checked:hover {{
    background-color: {accent_hi};
    border-color: {accent_hi};
}}

/* ── Project Tracker v2 components ───────────────────────────────────────── */

QLabel#categoryBadge {{
    background: {bg_raised};
    color: {text_mid};
    border: 1px solid {border};
    border-radius: {radius_xs}px;
    padding: 1px 7px;
    font-size: {font_xs}px;
    font-weight: 600;
}}
QLabel#priorityBadge {{
    font-size: {font_xs}px;
    font-weight: 700;
    background: transparent;
    padding: 0px 4px;
}}
QLabel#priorityHigh {{
    color: #c62828;
    font-size: {font_xs}px;
    font-weight: 900;
    background: transparent;
}}
QLabel#tagChip {{
    background: {accent}22;
    color: {accent};
    border: 1px solid {accent}44;
    border-radius: 8px;
    padding: 0px 8px;
    font-size: {font_xs}px;
}}
QFrame#focusCard {{
    background: {accent}14;
    border: 1px solid {accent}44;
    border-radius: {radius_sm}px;
}}
QLabel#focusLabel {{
    font-size: {font_sm}px;
    color: {text_hi};
    background: transparent;
}}
/* Collapsible section */
QLabel#collapsibleArrow {{
    color: {text_lo};
    font-size: {font_sm}px;
    background: transparent;
}}
QLabel#collapsibleTitle {{
    color: {text_lo};
    font-size: {font_xs}px;
    font-weight: 600;
    letter-spacing: 0.8px;
    background: transparent;
}}
/* Live session banner */
QFrame#liveSessionBanner {{
    background: #c6282814;
    border: 1px solid #c6282844;
    border-radius: {radius_sm}px;
}}
QLabel#liveSessionLabel {{
    color: #c62828;
    font-weight: 700;
    background: transparent;
}}

/* ── Project Gallery ─────────────────────────────────────────────────────── */

QFrame#galleryCard {{
    background-color: {card_bg};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
}}
QFrame#galleryCard:hover {{
    border-color: {accent};
}}
QLabel#galleryThumb {{
    background-color: {bg_deep};
    border-radius: {radius_xs}px;
}}
QLabel#galleryCardTitle {{
    font-size: {font_sm}px;
    font-weight: 600;
    color: {text_hi};
    background: transparent;
}}
QLabel#galleryCardDate {{
    font-size: {font_xs}px;
    color: {text_lo};
    background: transparent;
}}
QLabel#galleryMilestoneBadge {{
    font-size: {font_xs}px;
    background: transparent;
    color: {accent};
}}
QLabel#galleryCountLabel {{
    font-size: {font_sm}px;
    font-weight: 600;
    color: {text_mid};
    background: transparent;
}}
QLabel#galleryEmptyLabel {{
    font-size: {font_base}px;
    color: {text_dim};
    background: transparent;
}}
QWidget#galleryCardOverlay {{
    background-color: rgba(0, 0, 0, 175);
    border-radius: {radius_sm}px;
}}

/* ── Gallery lightbox ────────────────────────────────────────────────────── */

QDialog#lightboxDialog {{
    background-color: {bg_deep};
    border: 1px solid {border};
    border-radius: {radius_base}px;
}}
QWidget#lightboxHeader {{
    background-color: {bg_base};
    border-bottom: 1px solid {border};
}}
QLabel#lightboxCounter {{
    font-size: {font_sm}px;
    color: {text_lo};
    background: transparent;
}}
QLabel#lightboxImage {{
    background-color: {bg_deep};
}}
QPushButton#lightboxNavBtn {{
    background-color: transparent;
    border: none;
    color: {text_mid};
    font-size: 30px;
    font-weight: 300;
    padding: 0px;
}}
QPushButton#lightboxNavBtn:hover {{
    background-color: {bg_raised};
    color: {text_hi};
    border-radius: 0px;
}}
QPushButton#lightboxNavBtn:disabled {{
    color: {text_dim};
}}
QWidget#lightboxInfo {{
    background-color: {bg_base};
    border-top: 1px solid {border};
}}
QLabel#lightboxTitle {{
    font-size: {font_lg}px;
    font-weight: 700;
    color: {text_hi};
    background: transparent;
}}
QLabel#lightboxMeta {{
    font-size: {font_sm}px;
    color: {text_lo};
    background: transparent;
}}
QLabel#lightboxNote {{
    font-size: {font_sm}px;
    color: {text_mid};
    background: transparent;
    font-style: italic;
}}

/* ── Add Photo dialog ────────────────────────────────────────────────────── */

QFrame#galleryImgPreviewFrame {{
    background-color: {bg_deep};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
}}
QLabel#galleryImgPreview {{
    background: transparent;
    color: {text_dim};
    font-size: {font_base}px;
}}

/* ── Dashboard ────────────────────────────────────────────────────────────── */

/* Top banner — accent left-stripe card */
QFrame#dashBanner {{
    background-color: {card_bg};
    border: 1px solid {border};
    border-left: 3px solid {accent};
    border-radius: {radius_base}px;
}}

/* Greeting, streak, edit-name link inside the banner */
QLabel#dashGreeting {{
    font-size: {font_xl}px;
    font-weight: 700;
    color: {text_hi};
    background: transparent;
}}
QLabel#dashStreak {{
    font-size: {font_base}px;
    color: {text_lo};
    background: transparent;
}}
QLabel#dashEditName {{
    font-size: {font_xs}px;
    color: {text_lo};
    text-decoration: underline;
    background: transparent;
}}
QLabel#dashEditName:hover {{
    color: {text_mid};
}}

/* Section caps labels (COMMAND OVERVIEW, ACTIVE PROJECTS, etc.) */
QLabel#dashSectionLabel {{
    font-size: {font_xs}px;
    font-weight: 700;
    color: {text_lo};
    letter-spacing: 1px;
    background: transparent;
}}

/* Right-rail quick actions sidebar card */
QFrame#dashActionSidebar {{
    background-color: {card_bg};
    border: 1px solid {border};
    border-radius: {radius_base}px;
}}

/* Accent dot in the sidebar header */
QFrame#accentDot {{
    background-color: {accent};
    border-radius: 3px;
}}

/* Dashboard tab widget — underline style (overrides global pill style) */
QTabWidget#dashTabWidget::pane {{
    background: {bg_base};
    border: 1px solid {border};
    border-top: none;
    border-bottom-left-radius: {radius_base}px;
    border-bottom-right-radius: {radius_base}px;
}}
QTabWidget#dashTabWidget QTabBar {{
    background: transparent;
    border-bottom: none;
}}
QTabWidget#dashTabWidget QTabBar::tab {{
    background: {bg_raised};
    color: {text_lo};
    border: 1px solid {border};
    border-bottom: none;
    padding: 7px 18px;
    margin-right: 3px;
    border-top-left-radius: {radius_sm}px;
    border-top-right-radius: {radius_sm}px;
    font-size: {font_base}px;
    font-weight: 500;
    min-width: 80px;
}}
QTabWidget#dashTabWidget QTabBar::tab:selected {{
    background: {bg_base};
    color: {text_hi};
    border-bottom: 2px solid {accent};
    font-weight: 700;
}}
QTabWidget#dashTabWidget QTabBar::tab:hover:!selected {{
    background: {card_bg};
    color: {text_hi};
}}

/* Hero metric command cards */
QFrame#heroCard {{
    background-color: {card_bg};
    border: 1px solid {border};
    border-radius: {radius_base}px;
}}
QLabel#heroCardLabel {{
    font-size: {font_xs}px;
    font-weight: 700;
    letter-spacing: 0.8px;
    color: {text_lo};
    background: transparent;
}}
QLabel#heroCardSub {{
    font-size: {font_xs}px;
    color: {text_mid};
    background: transparent;
}}

/* ── Chroma Codex ─────────────────────────────────────────────────────────── */

/* Top bar */
QWidget#chromaTopBar {{
    background-color: {bg_raised};
    border-bottom: 1px solid {border};
}}

/* Role cards */
QFrame#roleCard {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_base}px;
}}
QFrame#roleCard:hover {{
    border-color: {accent}88;
}}

/* Missing banner */
QFrame#missingBanner {{
    background-color: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_base}px;
    padding: 4px 0;
}}

/* Scheme preview cards — base managed inline, but provide fallback */
QFrame#schemePreviewCard {{
    border-radius: {radius_base}px;
}}

/* Primary color picker dialog ─────────────────────────────────────────────── */

/* Hard-lock the dialog background — defeats any cascade from the parent
   button's inline setStyleSheet("background:#RRGGBB").  This rule is more
   specific than the parent cascade so it always wins. */
QDialog#primaryPickerDialog {{
    background: {bg_base};
}}

/* Every direct-child QWidget of the dialog should be transparent so the
   dialog background shows through — individual named frames override below. */
QDialog#primaryPickerDialog > QWidget {{
    background: transparent;
}}

/* Tab pane: transparent so dialog background shows */
QDialog#primaryPickerDialog QTabWidget::pane {{
    background: transparent;
    border: none;
}}
QDialog#primaryPickerDialog QTabBar::tab {{
    background: {bg_raised};
    color: {text_lo};
    padding: 6px 16px;
    font-size: {font_base}px;
    font-weight: 600;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
}}
QDialog#primaryPickerDialog QTabBar::tab:selected {{
    background: {bg_base};
    color: {text_hi};
    border-bottom: 2px solid {accent};
}}
QDialog#primaryPickerDialog QTabBar::tab:hover:!selected {{
    background: {bg_raised};
    color: {text_mid};
}}

/* Section panels inside the picker (hex row, slider block, selected paint row) */
QFrame#pickerSection {{
    background: {bg_raised};
    border: 1px solid {border};
    border-radius: {radius_base}px;
}}

/* "Open Full Color Wheel…" button — secondary style */
QPushButton#wheelBtn {{
    background: {bg_raised};
    color: {text_mid};
    border: 1px solid {border};
    border-radius: {radius_sm}px;
    padding: 7px 14px;
    font-size: {font_base}px;
}}
QPushButton#wheelBtn:hover {{
    background: {bg_raised};
    color: {text_hi};
    border-color: {accent};
}}

/* Tab widget — schemeTabWidget */
QTabWidget#schemeTabWidget::pane {{
    border: none;
    background: transparent;
}}
QTabWidget#schemeTabWidget QTabBar {{
    background: {bg_base};
}}
QTabWidget#schemeTabWidget QTabBar::tab {{
    background: {bg_base};
    color: {text_lo};
    padding: 7px 20px;
    font-size: {font_base}px;
    font-weight: 600;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
}}
QTabWidget#schemeTabWidget QTabBar::tab:selected {{
    background: {bg_base};
    color: {text_hi};
    border-bottom: 2px solid {accent};
}}
QTabWidget#schemeTabWidget QTabBar::tab:hover:!selected {{
    background: {bg_raised};
    color: {text_mid};
    border-bottom: 2px solid {border};
}}
"""

# ── QSS compilation ───────────────────────────────────────────────────────────
# The template uses Python str.format_map() conventions:
#   {token_name}  → replaced with the token's value
#   {{            → literal {  (CSS rule-open brace)
#   }}            → literal }  (CSS rule-close brace)
#
# _SafeFormatDict returns the placeholder text for any unknown key so that
# unrecognised tokens are left in place rather than raising KeyError.

class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _compile_qss(template: str, tokens: dict[str, str]) -> str:
    """
    Compile the QSS template by substituting token values and converting
    {{ / }} escape sequences to literal CSS braces.
    """
    return template.format_map(_SafeFormatDict(tokens))


# ── Background QSS compile thread ─────────────────────────────────────────────

class _CompileThread(QThread):
    """
    Compiles the QSS template on a worker thread so the main thread stays
    free to handle events while the string substitution runs.

    The compiled signal carries (theme_id, qss_string) and is automatically
    queued to the main thread by Qt's cross-thread signal mechanism.
    """
    compiled = Signal(str, str)   # theme_id, qss_string

    def __init__(self, theme_id: str, tokens: dict, parent=None):
        super().__init__(parent)
        self._theme_id = theme_id
        self._tokens   = dict(tokens)   # defensive copy — thread-safe read

    def run(self):
        qss = _compile_qss(_QSS_TEMPLATE, self._tokens)
        self.compiled.emit(self._theme_id, qss)


# ── ThemeManager ──────────────────────────────────────────────────────────────

class ThemeManager(QObject):
    """
    Central theme authority.  Registered in ServiceRegistry as "theme_manager".

    Responsibilities
    ────────────────
    • Load all JSON themes from the themes/ directory on startup
    • Compile QSS from the template and apply it to QApplication
    • Persist the active theme ID via SettingsService
    • Emit theme_changed(id) so any widget can react
    • Provide token(name) for Python-side color access
    • Generate new themes from paint-scheme colors
    • Save / delete user themes
    """

    #: Emitted after a new theme is applied.  Carries the theme id.
    theme_changed = Signal(str)

    def __init__(
        self,
        app: QApplication,
        themes_dir: Path,
        settings=None,
    ):
        super().__init__()
        self._app      = app
        self._dir      = themes_dir
        self._settings = settings     # SettingsService or None
        self._themes:  dict[str, Theme] = {}
        self._current: str = "dark_default"
        self._applied_qss: str = ""      # last QSS actually sent to QApplication
        self._pending_apply: Optional[str] = None  # theme_id queued for deferred apply
        self._compile_thread: Optional[_CompileThread] = None  # current worker

        self._dir.mkdir(parents=True, exist_ok=True)
        self._load_all()

        # Restore last-used theme
        if settings:
            saved = settings.get("app.theme_id", "dark_default")
            if saved in self._themes:
                self._current = saved

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def themes(self) -> dict[str, Theme]:
        """All loaded themes keyed by id."""
        return self._themes

    @property
    def current_theme_id(self) -> str:
        """ID of the currently applied theme."""
        return self._current

    def available(self) -> list[Theme]:
        """Return all themes sorted: builtins first, then user themes A-Z."""
        builtins = sorted(
            [t for t in self._themes.values() if t.meta.builtin],
            key=lambda t: t.meta.name,
        )
        user = sorted(
            [t for t in self._themes.values() if not t.meta.builtin],
            key=lambda t: t.meta.name,
        )
        return builtins + user

    def current(self) -> Theme:
        return self._themes.get(self._current, next(iter(self._themes.values())))

    def current_id(self) -> str:
        return self._current

    def token(self, name: str) -> str:
        """
        Return the current value of a theme token by name.

        Example
        -------
            color = tm.token("accent")    # e.g. "#0078d4"
            label.setStyleSheet(f"color: {tm.token('text_lo')};")
        """
        return self.current().tokens().get(name, "")

    def apply_theme(self, theme_id: str) -> None:
        """
        Apply the theme with the given id.

        Startup path (no visible windows)
        ──────────────────────────────────
        QSS is compiled and applied synchronously so the correct stylesheet is
        in place before the main window renders for the first time.

        Runtime path (visible windows present)
        ───────────────────────────────────────
        1.  The apply is deferred to the next event-loop tick via
            QTimer.singleShot(0) so the triggering event finishes first.
        2.  Rapid repeated calls are coalesced — only the last id runs.
        3.  QSS template compilation happens on a background QThread
            (_CompileThread) so the main thread stays responsive.
        4.  The compiled QSS is handed back to the main thread via a queued
            signal, then applied with a WaitCursor so the user sees feedback
            during the Qt widget-tree style traversal.
        """
        if theme_id not in self._themes:
            print(f"[THEME] Unknown theme id: {theme_id!r}")
            return
        self._current = theme_id
        if self._settings:
            self._settings.set("app.theme_id", theme_id)

        # Startup path: no visible windows yet — compile+apply synchronously
        # so the main window receives the correct stylesheet before first paint.
        has_visible = any(w.isVisible() for w in self._app.topLevelWidgets())
        if not has_visible:
            qss = _compile_qss(_QSS_TEMPLATE, self._themes[theme_id].tokens())
            self._apply_qss(theme_id, qss)
            return

        # Runtime path: defer and coalesce rapid calls.
        if self._pending_apply is None:
            QTimer.singleShot(0, self._flush_pending_apply)
        self._pending_apply = theme_id

    def _flush_pending_apply(self) -> None:
        """
        Called from the event loop after coalescing.  Starts a background
        _CompileThread to build the QSS string off the main thread.
        The thread emits compiled(theme_id, qss) which is queued back to the
        main thread, where _apply_qss does the actual setStyleSheet() call.
        """
        theme_id = self._pending_apply
        self._pending_apply = None

        if theme_id not in self._themes:
            return

        # Disconnect any previous thread so stale results are discarded.
        if self._compile_thread is not None:
            try:
                self._compile_thread.compiled.disconnect()
            except RuntimeError:
                pass

        self._compile_thread = _CompileThread(
            theme_id, self._themes[theme_id].tokens()
        )
        self._compile_thread.compiled.connect(self._apply_qss)
        self._compile_thread.start()

    def _apply_qss(self, theme_id: str, qss: str) -> None:
        """
        Apply pre-compiled QSS to QApplication.  Always runs on the main
        thread (called directly at startup, or via a queued signal at runtime).

        • Ignores stale results if a newer theme was applied while the thread
          was compiling.
        • Skips the traversal entirely when the compiled QSS is identical to
          what is already loaded (e.g. user presses Save without changing
          anything).
        • Sets a WaitCursor around setStyleSheet() so the user gets visual
          feedback during the widget-tree traversal, which can take 50–300 ms
          on large UIs.
        • NOTE: setUpdatesEnabled(False/True) is intentionally NOT used here —
          see the extensive comment in the previous version for why it causes
          widgets to never repaint after a theme switch.
        """
        if theme_id != self._current:
            return   # stale: a newer theme superseded this compile result

        if qss == self._applied_qss:
            self.theme_changed.emit(theme_id)
            return

        # Drain pending OS messages before the blocking traversal so Windows
        # does not declare the app "Not Responding".
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._app.setStyleSheet(qss)
            self._applied_qss = qss
        finally:
            QApplication.restoreOverrideCursor()

        self.theme_changed.emit(theme_id)
        print(f"[THEME] Applied: {self._themes[theme_id].meta.name}")

    def apply_current(self) -> None:
        """Re-apply the current theme (e.g. after editing tokens in-place)."""
        # Clear the QSS cache so the next apply is never skipped
        self._applied_qss = ""
        self.apply_theme(self._current)

    # ── Theme CRUD ─────────────────────────────────────────────────────────

    def create_blank(self, name: str) -> Theme:
        """
        Create a brand-new user theme with default (dark) colors.
        The theme is NOT saved — call save_theme() when ready.
        """
        safe = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        meta = ThemeMeta(id=f"user_{safe}", name=name, author="User", builtin=False)
        return Theme(meta=meta, colors=ThemeColors(), typography=ThemeTypography(), shape=ThemeShape())

    def create_copy(self, name: str, base_id: Optional[str] = None) -> Theme:
        """
        Create a new editable theme by copying base_id (or current).
        The new theme is NOT saved to disk — call save_theme() when ready.
        """
        from copy import deepcopy

        base = self._themes.get(base_id or self._current, self.current())
        new  = deepcopy(base)
        safe = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        new.meta = ThemeMeta(id=f"user_{safe}", name=name, author="User", builtin=False)
        return new

    def save_theme(self, theme: Theme) -> None:
        """Persist a theme to disk and register it in memory."""
        if theme.meta.builtin:
            raise ValueError("Cannot overwrite a builtin theme.")
        path = self._dir / f"{theme.meta.id}.json"
        path.write_text(
            json.dumps(theme.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._themes[theme.meta.id] = theme
        print(f"[THEME] Saved: {theme.meta.name} → {path.name}")

    def delete_theme(self, theme_id: str) -> None:
        """Delete a user theme from disk and memory."""
        theme = self._themes.get(theme_id)
        if not theme:
            return
        if theme.meta.builtin:
            raise ValueError("Cannot delete a builtin theme.")
        path = self._dir / f"{theme_id}.json"
        if path.exists():
            path.unlink()
        del self._themes[theme_id]
        if self._current == theme_id:
            self.apply_theme("dark_default")
        print(f"[THEME] Deleted: {theme_id}")

    # ── Paint-scheme generation ─────────────────────────────────────────────

    def generate_from_paint(
        self,
        accent_hex: str,
        theme_name: str,
        scheme_name: str = "",
    ) -> Theme:
        """
        Generate a new Theme from a paint color and register it in memory.
        Call save_theme() to persist it to disk.

        Parameters
        ----------
        accent_hex  : Source paint color, e.g. "#3A86FF"
        theme_name  : Display name for the generated theme
        scheme_name : Paint scheme this color belongs to (stored in meta)
        """
        theme = theme_from_paint_scheme(
            accent_hex  = accent_hex,
            theme_name  = theme_name,
            scheme_name = scheme_name,
            base_theme  = self.current(),
        )
        self._themes[theme.meta.id] = theme
        return theme

    # ── Internal ───────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        """Load every JSON file in the themes directory."""
        for path in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                theme = Theme.from_dict(data)
                self._themes[theme.meta.id] = theme
            except Exception as exc:
                print(f"[THEME] Failed to load {path.name}: {exc}")

        if not self._themes:
            # Absolute fallback — create an in-memory default so the app
            # never crashes even if the themes/ directory is empty.
            fallback = Theme(meta=ThemeMeta(id="dark_default", name="Dark (Default)", builtin=True))
            self._themes["dark_default"] = fallback

        print(f"[THEME] Loaded {len(self._themes)} theme(s): "
              f"{', '.join(self._themes)}")
