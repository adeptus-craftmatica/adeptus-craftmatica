"""Dashboard customization dialog — toggle sections and individual cards."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QFrame, QScrollArea, QWidget, QTabWidget,
)

from core.contracts.dashboard_dto import DashboardSectionDef

# ── Tab display order for the sections pane ───────────────────────────────────
_TAB_META = [
    ("overview", "⚡  Overview"),
    ("activity", "📜  Activity"),
    ("alerts",   "🔔  Alerts"),
]

# ── Human-readable group names for the cards pane ────────────────────────────
_PLUGIN_GROUP_LABELS: dict[str, str] = {
    "dashboard":        "🔥  Hobby Engagement",
    "paint_tracker":    "🎨  Paint Collection",
    "project_tracker":  "📋  Projects",
    "model_tracker":    "🗿  Models",
    "army_builder":     "🛡  Army Builder",
    "campaign_tracker": "⚔  Campaigns",
    "tool_tracker":     "🔧  Tool Tracker",
    "materials_tracker":"🌿  Materials",
    "calendar":         "📅  Calendar",
}


class DashboardCustomizeDialog(QDialog):
    """
    Two-tab dialog for customizing the dashboard:

      Sections tab — toggle whole sections (Command Overview, Active Projects…)
      Cards tab    — toggle individual stat cards within Command Overview

    Usage::

        dlg = DashboardCustomizeDialog(
            sections=_DASHBOARD_SECTIONS,  hidden_sections=[...],
            cards=all_stats,               hidden_cards=[...],
            context=ctx, parent=parent_widget,
        )
        if dlg.exec():
            hide_these_sections = dlg.get_hidden_sections()
            hide_these_cards    = dlg.get_hidden_cards()
    """

    def __init__(
        self,
        sections:         list[DashboardSectionDef],
        hidden_sections:  list[str],
        cards:            list | None = None,
        hidden_cards:     list[str] | None = None,
        context=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Customize Dashboard")
        self.setMinimumWidth(520)
        self.setMinimumHeight(480)
        self.setModal(True)

        self._sections         = sections
        self._hidden_sections  = set(hidden_sections)
        self._cards            = cards or []
        self._hidden_cards     = set(hidden_cards or [])

        self._section_checks: dict[str, QCheckBox] = {}
        self._card_checks:    dict[str, QCheckBox] = {}

        self._apply_theme(context)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        title = QLabel("Customize Dashboard")
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        root.addWidget(title)

        sub = QLabel("Choose which sections and stat cards appear on your dashboard.")
        sub.setStyleSheet("font-size: 12px;")
        root.addWidget(sub)

        root.addWidget(self._hline())

        # ── Tab widget ────────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setObjectName("customizeTabs")
        # Prevent tab labels from being elided (cut off with "…")
        tabs.tabBar().setElideMode(Qt.ElideNone)
        # Let each tab be exactly as wide as its label needs
        tabs.tabBar().setExpanding(False)
        tabs.addTab(self._build_sections_tab(), "⬛  Sections")
        tabs.addTab(self._build_cards_tab(),    "📊  Stat Cards")
        root.addWidget(tabs, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        root.addWidget(self._hline())

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondaryBtn")
        cancel.setFixedWidth(90)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        save = QPushButton("Save")
        save.setObjectName("primaryBtn")
        save.setFixedWidth(90)
        save.setDefault(True)
        save.clicked.connect(self.accept)
        btn_row.addWidget(save)

        root.addLayout(btn_row)

    # ── Sections tab ──────────────────────────────────────────────────────────

    def _build_sections_tab(self) -> QWidget:
        """Checklist of full dashboard sections, grouped by tab."""
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(0)

        scroll = self._make_scroll()
        inner  = QWidget()
        il     = QVBoxLayout(inner)
        il.setContentsMargins(4, 0, 4, 4)
        il.setSpacing(2)

        by_tab: dict[str, list[DashboardSectionDef]] = {}
        for s in self._sections:
            by_tab.setdefault(s.tab, []).append(s)

        first = True
        for tab_id, tab_label in _TAB_META:
            secs = by_tab.get(tab_id, [])
            if not secs:
                continue
            if not first:
                il.addSpacing(8)
            first = False
            il.addWidget(self._group_label(tab_label))
            for sec in secs:
                row = self._build_section_row(sec)
                il.addWidget(row)

        il.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, stretch=1)
        return page

    def _build_section_row(self, sec: DashboardSectionDef) -> QWidget:
        row = self._make_row()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(12)

        cb = QCheckBox()
        cb.setChecked(sec.id not in self._hidden_sections)
        cb.setFixedWidth(20)
        self._section_checks[sec.id] = cb
        lay.addWidget(cb, alignment=Qt.AlignTop | Qt.AlignHCenter)

        txt = QVBoxLayout()
        txt.setSpacing(2)
        txt.setContentsMargins(0, 0, 0, 0)
        name = QLabel(sec.label)
        name.setStyleSheet("font-size: 13px; font-weight: 600;")
        txt.addWidget(name)
        if sec.description:
            desc = QLabel(sec.description)
            desc.setObjectName("customizeDesc")
            desc.setStyleSheet("font-size: 11px;")
            desc.setWordWrap(True)
            txt.addWidget(desc)
        lay.addLayout(txt, stretch=1)

        row.mousePressEvent = lambda _, c=cb: c.setChecked(not c.isChecked())
        return row

    # ── Cards tab ─────────────────────────────────────────────────────────────

    def _build_cards_tab(self) -> QWidget:
        """
        Checklist of individual CommandStat cards, grouped by source plugin.
        Each row shows icon + label + current value so the user can identify
        exactly which card they're looking at.
        """
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(0)

        if not self._cards:
            placeholder = QLabel("No stat cards available yet.\nOpen the dashboard first to load plugin data.")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("font-size: 12px; padding: 40px;")
            lay.addWidget(placeholder)
            return page

        scroll = self._make_scroll()
        inner  = QWidget()
        il     = QVBoxLayout(inner)
        il.setContentsMargins(4, 0, 4, 4)
        il.setSpacing(2)

        # Group cards by their plugin source (prefix before the first ".")
        grouped: dict[str, list] = {}
        for card in self._cards:
            source = card.card_id.split(".")[0] if "." in card.card_id else "other"
            grouped.setdefault(source, []).append(card)

        # Preferred display order: dashboard built-ins first, then alphabetical
        _ORDER = ["dashboard", "paint_tracker", "project_tracker", "model_tracker",
                  "army_builder", "campaign_tracker", "tool_tracker",
                  "materials_tracker", "calendar"]
        ordered_sources = [s for s in _ORDER if s in grouped]
        ordered_sources += sorted(k for k in grouped if k not in _ORDER)

        first = True
        for source in ordered_sources:
            cards = grouped[source]
            if not first:
                il.addSpacing(8)
            first = False
            group_label = _PLUGIN_GROUP_LABELS.get(source, f"🔌  {source.replace('_', ' ').title()}")
            il.addWidget(self._group_label(group_label))
            for card in cards:
                il.addWidget(self._build_card_row(card))

        il.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, stretch=1)
        return page

    def _build_card_row(self, card) -> QWidget:
        row = self._make_row()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(12)

        cb = QCheckBox()
        cb.setChecked(card.card_id not in self._hidden_cards)
        cb.setFixedWidth(20)
        self._card_checks[card.card_id] = cb
        lay.addWidget(cb, alignment=Qt.AlignVCenter | Qt.AlignHCenter)

        # Icon
        if card.icon:
            icon_lbl = QLabel(card.icon)
            icon_lbl.setStyleSheet("font-size: 15px; background: transparent;")
            icon_lbl.setFixedWidth(22)
            lay.addWidget(icon_lbl, alignment=Qt.AlignVCenter)

        # Label
        name = QLabel(card.label)
        name.setStyleSheet("font-size: 13px; font-weight: 600;")
        lay.addWidget(name, stretch=1)

        # Current value — right-aligned, subtle
        val_lbl = QLabel(card.value)
        val_lbl.setObjectName("customizeDesc")
        val_lbl.setStyleSheet("font-size: 12px; font-weight: bold;")
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(val_lbl)

        row.mousePressEvent = lambda _, c=cb: c.setChecked(not c.isChecked())
        return row

    # ── Public API ────────────────────────────────────────────────────────────

    def get_hidden_sections(self) -> list[str]:
        """Section IDs that are currently unchecked."""
        return [sid for sid, cb in self._section_checks.items()
                if not cb.isChecked()]

    def get_hidden_cards(self) -> list[str]:
        """Card IDs that are currently unchecked."""
        return [cid for cid, cb in self._card_checks.items()
                if not cb.isChecked()]

    # keep old name for any callers that haven't been updated
    def get_hidden(self) -> list[str]:
        return self.get_hidden_sections()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _group_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("customizeGroupLabel")
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; letter-spacing: 0.5px;"
            " padding: 6px 4px 4px 4px;"
        )
        return lbl

    def _make_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName("customizeRow")
        row.setCursor(Qt.PointingHandCursor)
        return row

    def _make_scroll(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll

    def _hline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        return line

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self, context):
        if not context:
            return
        try:
            tm = context.services.try_get("theme_manager")
            if not tm:
                return
            bg  = tm.token("bg_base")
            bg2 = tm.token("bg_card")
            fg  = tm.token("text_hi")
            fg2 = tm.token("text_lo")
            brd = tm.token("border")
            acc = tm.token("accent")
            inp = tm.token("bg_input")

            self.setStyleSheet(f"""
                QDialog {{
                    background: {bg};
                    color: {fg};
                }}
                QTabWidget#customizeTabs::pane {{
                    border: 1px solid {brd};
                    border-radius: 6px;
                    background: {bg2};
                }}
                QTabWidget#customizeTabs QTabBar::tab {{
                    background: {inp};
                    color: {fg2};
                    border: 1px solid {brd};
                    border-bottom: none;
                    border-radius: 4px 4px 0 0;
                    padding: 6px 20px;
                    margin-right: 2px;
                    font-size: 12px;
                    min-width: 100px;
                }}
                QTabWidget#customizeTabs QTabBar::tab:selected {{
                    background: {bg2};
                    color: {fg};
                    border-bottom: 1px solid {bg2};
                }}
                QTabWidget#customizeTabs QTabBar::tab:hover:!selected {{
                    color: {acc};
                }}
                QLabel {{
                    color: {fg};
                    background: transparent;
                }}
                QLabel#customizeDesc {{
                    color: {fg2};
                }}
                QLabel#customizeGroupLabel {{
                    color: {fg2};
                }}
                QScrollArea, QWidget {{
                    background: transparent;
                }}
                QWidget#customizeRow {{
                    background: transparent;
                    border-radius: 6px;
                }}
                QWidget#customizeRow:hover {{
                    background: {inp};
                }}
                QCheckBox {{
                    color: {fg};
                    background: transparent;
                    spacing: 0px;
                }}
                QCheckBox::indicator {{
                    width: 16px;
                    height: 16px;
                    border: 1.5px solid {brd};
                    border-radius: 4px;
                    background: {inp};
                }}
                QCheckBox::indicator:checked {{
                    background: {acc};
                    border-color: {acc};
                }}
                QPushButton#primaryBtn {{
                    background: {acc};
                    color: #fff;
                    border: none;
                    border-radius: 5px;
                    padding: 6px 16px;
                    font-weight: bold;
                    font-size: 13px;
                }}
                QPushButton#primaryBtn:hover {{
                    border: 1px solid rgba(255,255,255,0.2);
                }}
                QPushButton#secondaryBtn {{
                    background: {inp};
                    color: {fg};
                    border: 1px solid {brd};
                    border-radius: 5px;
                    padding: 6px 16px;
                    font-size: 13px;
                }}
                QPushButton#secondaryBtn:hover {{
                    border-color: {acc};
                    color: {acc};
                }}
                QFrame[frameShape="4"] {{
                    background: {brd};
                    border: none;
                    max-height: 1px;
                }}
                QScrollBar:vertical {{
                    background: {bg2};
                    width: 6px;
                    margin: 0;
                    border-radius: 3px;
                }}
                QScrollBar::handle:vertical {{
                    background: {brd};
                    border-radius: 3px;
                    min-height: 20px;
                }}
                QScrollBar::add-line:vertical,
                QScrollBar::sub-line:vertical {{
                    height: 0;
                }}
            """)
        except Exception:
            pass
