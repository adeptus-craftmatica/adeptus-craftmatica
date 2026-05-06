"""Dashboard main UI — tabbed layout."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QScrollArea, QFrame, QSizePolicy, QInputDialog,
)

from plugins.dashboard.widgets.command_cards          import CommandCardsWidget
from plugins.dashboard.widgets.quick_actions          import QuickActionsWidget
from plugins.dashboard.widgets.notifications_panel    import NotificationsPanelWidget
from plugins.dashboard.widgets.recent_activity        import RecentActivityWidget
from plugins.dashboard.widgets.smart_recommendations  import SmartRecommendationsWidget
from plugins.dashboard.widgets.calendar_intelligence  import CalendarIntelligenceWidget
from plugins.dashboard.widgets.alerts_mini            import AlertsMiniWidget
from plugins.dashboard.widgets.active_projects_strip  import ActiveProjectsStripWidget


class DashboardUI(QWidget):
    """
    Tabbed dashboard layout:

        Banner (greeting, streak — always visible)
        ┌────────────────────────────────────────────────────┐
        │  Overview │  Activity │  Alerts                    │
        ├────────────────────────────────────────────────────┤
        │  (tab content — single or two-column, full-width)  │
        └────────────────────────────────────────────────────┘
    """

    action_requested = Signal(str, dict)
    name_changed     = Signal(str)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self.setMinimumSize(0, 0)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(10)

        # ── Banner — always visible above tabs ────────────────────────────────
        self._banner = self._build_banner()
        root.addWidget(self._banner)

        # ── Tab widget ────────────────────────────────────────────────────────
        self._tab_widget = QTabWidget()
        self._tab_widget.setObjectName("dashTabWidget")
        self._tab_widget.setDocumentMode(False)   # False so pane styling works
        self._tab_widget.setMinimumSize(0, 0)
        root.addWidget(self._tab_widget, stretch=1)

        self._tab_widget.addTab(self._build_overview_tab(),  "⚡  Overview")
        self._tab_widget.addTab(self._build_activity_tab(), "📜  Activity")
        self._tab_widget.addTab(self._build_alerts_tab(),   "🔔  Alerts")

        # Theme reactivity
        tm = context.services.get("theme_manager") if context else None
        if tm:
            try:
                tm.theme_changed.connect(self._on_theme_changed)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════════════
    # Banner
    # ══════════════════════════════════════════════════════════════════════════

    def _build_banner(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dashBanner")
        frame.setFixedHeight(52)

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        self._greeting_lbl = QLabel("Welcome back!")
        self._greeting_lbl.setObjectName("dashGreeting")
        lay.addWidget(self._greeting_lbl)

        self._edit_name_btn = QLabel("✎ edit name")
        self._edit_name_btn.setObjectName("dashEditName")
        self._edit_name_btn.setCursor(Qt.PointingHandCursor)
        self._edit_name_btn.mousePressEvent = lambda _: self._prompt_rename()
        lay.addWidget(self._edit_name_btn)

        lay.addStretch()

        self._streak_lbl = QLabel("")
        self._streak_lbl.setObjectName("dashStreak")
        lay.addWidget(self._streak_lbl)

        return frame

    # ══════════════════════════════════════════════════════════════════════════
    # Tab builders
    # ══════════════════════════════════════════════════════════════════════════

    def _build_overview_tab(self) -> QWidget:
        """
        Two-column layout:
          Left (flex)  — Calendar Intelligence + Command stats + Recommendations
          Right (fixed 220 px) — Quick Actions sidebar card

        SmartRecommendationsWidget owns its own internal scroll, so there is no
        outer QScrollArea — that would create a nested-scroll conflict.
        """
        page = QWidget()
        page.setMinimumSize(0, 0)

        h_lay = QHBoxLayout(page)
        h_lay.setContentsMargins(12, 12, 12, 12)
        h_lay.setSpacing(12)

        # ── Left: main content ────────────────────────────────────────────────
        main = QWidget()
        main.setMinimumSize(0, 0)
        main_lay = QVBoxLayout(main)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(14)

        # 1. Command Overview stats — always at the top
        self._section_lbl("COMMAND OVERVIEW", main_lay)
        self._cmd_cards = CommandCardsWidget(self._ctx)
        main_lay.addWidget(self._cmd_cards)

        main_lay.addWidget(self._hline())

        # 2. Active Projects strip — top 3 projects with progress bars
        self._section_lbl("ACTIVE PROJECTS", main_lay)
        self._projects_strip = ActiveProjectsStripWidget(self._ctx)
        self._projects_strip.action_requested.connect(self.action_requested)
        main_lay.addWidget(self._projects_strip)

        main_lay.addWidget(self._hline())

        # 3. Today's Agenda — calendar events + milestones + overdue
        self._section_lbl("TODAY'S AGENDA", main_lay)
        self._cal_intelligence = CalendarIntelligenceWidget(self._ctx)
        self._cal_intelligence.action_requested.connect(self.action_requested)
        main_lay.addWidget(self._cal_intelligence)

        main_lay.addWidget(self._hline())

        # 4. Recommended Next Actions — stretch=1, its own internal scroll
        self._section_lbl("RECOMMENDED NEXT ACTIONS", main_lay)
        self._recommendations = SmartRecommendationsWidget(self._ctx)
        self._recommendations.action_requested.connect(self.action_requested)
        main_lay.addWidget(self._recommendations, stretch=1)

        h_lay.addWidget(main, stretch=1)

        # ── Right: Quick Actions sidebar card ─────────────────────────────────
        h_lay.addWidget(self._build_actions_sidebar())

        return page

    def _build_actions_sidebar(self) -> QFrame:
        """220 px fixed-width card holding compact Quick Action buttons."""
        sidebar = QFrame()
        sidebar.setObjectName("dashActionSidebar")
        sidebar.setFixedWidth(220)

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)

        # Header row: accent dot + section label
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_row.setSpacing(6)

        dot = QFrame()
        dot.setObjectName("accentDot")
        dot.setFixedSize(6, 6)
        hdr_row.addWidget(dot)

        hdr = QLabel("QUICK ACTIONS")
        hdr.setObjectName("dashSectionLabel")
        hdr_row.addWidget(hdr, stretch=1)
        lay.addLayout(hdr_row)

        # Thin divider
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        # Quick Actions (single-column compact mode)
        self._overview_quick_actions = QuickActionsWidget(self._ctx, columns=1)
        self._overview_quick_actions.action_requested.connect(self.action_requested)
        lay.addWidget(self._overview_quick_actions)

        lay.addSpacing(6)

        # Thin divider between Quick Actions and Alerts
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFixedHeight(1)
        lay.addWidget(sep2)

        # Alerts section header
        hdr2_row = QHBoxLayout()
        hdr2_row.setContentsMargins(0, 4, 0, 0)
        hdr2_row.setSpacing(6)

        dot2 = QFrame()
        dot2.setObjectName("accentDot")
        dot2.setFixedSize(6, 6)
        hdr2_row.addWidget(dot2)

        hdr2 = QLabel("ALERTS")
        hdr2.setObjectName("dashSectionLabel")
        hdr2_row.addWidget(hdr2, stretch=1)
        lay.addLayout(hdr2_row)

        # Alerts mini — top-3 critical/warning rows + "View all" link
        self._alerts_mini = AlertsMiniWidget(self._ctx)
        self._alerts_mini.navigate_alerts.connect(
            lambda: self._tab_widget.setCurrentIndex(2)
        )
        lay.addWidget(self._alerts_mini)

        lay.addStretch()
        return sidebar

    def _build_activity_tab(self) -> QWidget:
        """Full-width, date-grouped recent activity log."""
        page = QWidget()
        page.setMinimumSize(0, 0)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self._section_lbl("RECENT ACTIVITY", lay)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._activity = RecentActivityWidget(self._ctx)
        scroll.setWidget(self._activity)
        lay.addWidget(scroll, stretch=1)

        return page

    def _build_alerts_tab(self) -> QWidget:
        """Alerts only — notifications panel fills the full pane."""
        page = QWidget()
        page.setMinimumSize(0, 0)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self._section_lbl("ALERTS", lay)
        self._notifications = NotificationsPanelWidget(self._ctx)
        self._notifications.action_requested.connect(self.action_requested)
        lay.addWidget(self._notifications, stretch=1)

        return page

    # ══════════════════════════════════════════════════════════════════════════
    # Name editing
    # ══════════════════════════════════════════════════════════════════════════

    def _prompt_rename(self):
        tm       = self._ctx.services.get("theme_manager") if self._ctx else None
        settings = self._ctx.services.get("settings")      if self._ctx else None
        current  = settings.get("user.display_name", "").strip() if settings else ""

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Your Name")
        dialog.setLabelText("What should we call you?")
        dialog.setInputMode(QInputDialog.TextInput)
        dialog.setTextValue(current)
        dialog.setOkButtonText("Save")
        dialog.setCancelButtonText("Cancel")

        if tm:
            bg  = tm.token("bg_base")
            fg  = tm.token("text_hi")
            brd = tm.token("border")
            acc = tm.token("accent")
            inp = tm.token("bg_input")
            dialog.setStyleSheet(f"""
                QDialog   {{ background: {bg}; color: {fg}; }}
                QLabel    {{ color: {fg}; }}
                QLineEdit {{
                    background: {inp}; color: {fg};
                    border: 1px solid {brd}; border-radius: 4px; padding: 4px 8px;
                }}
                QLineEdit:focus {{ border-color: {acc}; }}
                QPushButton {{
                    background: {inp}; color: {fg};
                    border: 1px solid {brd}; border-radius: 4px; padding: 4px 16px;
                }}
                QPushButton:hover {{ border-color: {acc}; color: {acc}; }}
            """)

        if dialog.exec():
            name = dialog.textValue().strip()
            if settings:
                settings.set("user.display_name", name)
            self.name_changed.emit(name)

    # ══════════════════════════════════════════════════════════════════════════
    # Theme reactivity
    # ══════════════════════════════════════════════════════════════════════════

    def _on_theme_changed(self, _theme_id: str = ""):
        # Structural styling is handled by the QSS template via object names.
        pass

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _section_lbl(self, text: str, layout) -> QLabel:
        """Small-caps section header — styled via QSS (#dashSectionLabel)."""
        lbl = QLabel(text)
        lbl.setObjectName("dashSectionLabel")
        layout.addWidget(lbl)
        return lbl

    def _hline(self) -> QFrame:
        """Thin horizontal divider — styled via global QSS (QFrame[frameShape=4])."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        return line

    # ══════════════════════════════════════════════════════════════════════════
    # Public refresh API  (called by plugin.py — signatures unchanged)
    # ══════════════════════════════════════════════════════════════════════════

    def set_greeting(self, text: str) -> None:
        self._greeting_lbl.setText(text)

    def set_streak(self, streak: int) -> None:
        if streak <= 0:
            self._streak_lbl.setText("")
            return
        flames = "🔥" * min(streak, 5)
        self._streak_lbl.setText(f"{flames}  {streak}-day streak")

    def refresh_command_stats(self, stats: list) -> None:
        self._cmd_cards.refresh(stats)

    def refresh_projects(self, cards: list) -> None:
        # Projects tab was removed; _project_feed no longer exists.
        # The active-projects strip is refreshed separately via
        # refresh_active_projects_strip() — nothing to do here.
        pass

    def refresh_quick_actions(self, actions: list) -> None:
        try:
            self._overview_quick_actions.refresh(actions)
        except Exception:
            pass

    def refresh_notifications(self, notes: list) -> None:
        self._notifications.refresh(notes)

    def refresh_paint_intel(self, low: list, recent: list, brands: dict) -> None:
        pass  # Paint Studio tab removed; kept for plugin.py call-site compatibility

    def refresh_activity(self, activities: list) -> None:
        self._activity.refresh(activities)

    def refresh_recommendations(self, recs: list) -> None:
        self._recommendations.refresh(recs)

    def refresh_active_projects_strip(self, cards: list) -> None:
        """Push fresh project cards to the Overview active-projects strip."""
        try:
            self._projects_strip.refresh(cards)
        except Exception:
            pass

    def refresh_alerts_mini(self, notes: list) -> None:
        """Push fresh notifications to the Overview sidebar alerts panel."""
        try:
            self._alerts_mini.refresh(notes)
        except Exception:
            pass

    def refresh_calendar_intelligence(
        self,
        today: list,
        week: list,
        milestones: list,
        overdue: list | None = None,
    ) -> None:
        """Push fresh calendar data to the Overview intelligence card."""
        try:
            self._cal_intelligence.refresh(today, week, milestones, overdue)
        except Exception as e:
            print(f"[DASHBOARD UI] refresh_calendar_intelligence error: {e}")
