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
    customize_clicked = Signal()   # emitted when the ⚙ Customize button is pressed

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self.setMinimumSize(0, 0)

        # section_id → container QWidget (used by set_section_visible)
        self._section_widgets: dict[str, QWidget] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(10)

        # ── Banner — always visible above tabs ────────────────────────────────
        self._banner = self._build_banner()
        root.addWidget(self._banner)

        # ── Tab widget ────────────────────────────────────────────────────────
        self._tab_widget = QTabWidget()
        self._tab_widget.setObjectName("dashTabWidget")
        self._tab_widget.setDocumentMode(False)
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

        # ── Customize button ──────────────────────────────────────────────────
        lay.addSpacing(8)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(20)
        lay.addWidget(sep, alignment=Qt.AlignVCenter)

        lay.addSpacing(4)

        self._customize_btn = QLabel("⚙  Customize")
        self._customize_btn.setObjectName("dashCustomizeBtn")
        self._customize_btn.setCursor(Qt.PointingHandCursor)
        self._customize_btn.setToolTip("Show / hide dashboard sections")
        self._customize_btn.mousePressEvent = lambda _: self.customize_clicked.emit()
        lay.addWidget(self._customize_btn)

        return frame

    # ══════════════════════════════════════════════════════════════════════════
    # Section wrapper helper
    # ══════════════════════════════════════════════════════════════════════════

    def _wrap_section(
        self,
        section_id: str,
        title: str,
        content: QWidget,
        *,
        leading_divider: bool = True,
        stretch_content: bool = False,
    ) -> QWidget:
        """
        Wraps a section label + content widget in a container QWidget.

        The container is stored in self._section_widgets[section_id] so
        set_section_visible() can show/hide it as a unit (label + divider +
        content all disappear together).
        """
        container = QWidget()
        container.setObjectName("dashSectionContainer")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        if leading_divider:
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFixedHeight(1)
            lay.addWidget(line)

        lbl = QLabel(title)
        lbl.setObjectName("dashSectionLabel")
        lay.addWidget(lbl)

        if stretch_content:
            lay.addWidget(content, stretch=1)
        else:
            lay.addWidget(content)

        self._section_widgets[section_id] = container
        return container

    # ══════════════════════════════════════════════════════════════════════════
    # Tab builders
    # ══════════════════════════════════════════════════════════════════════════

    def _build_overview_tab(self) -> QWidget:
        """
        Two-column layout:
          Left (flex)  — Command stats + Active Projects + Calendar + Recommendations
          Right (fixed 220 px) — Quick Actions + Alerts sidebar card
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
        main_lay.setSpacing(6)

        # 1. Command Overview
        self._cmd_cards = CommandCardsWidget(self._ctx)
        main_lay.addWidget(self._wrap_section(
            "command_overview", "COMMAND OVERVIEW", self._cmd_cards,
            leading_divider=False,
        ))

        # 2. Active Projects
        self._projects_strip = ActiveProjectsStripWidget(self._ctx)
        self._projects_strip.action_requested.connect(self.action_requested)
        main_lay.addWidget(self._wrap_section(
            "active_projects", "ACTIVE PROJECTS", self._projects_strip,
        ))

        # 3. Today's Agenda
        self._cal_intelligence = CalendarIntelligenceWidget(self._ctx)
        self._cal_intelligence.action_requested.connect(self.action_requested)
        main_lay.addWidget(self._wrap_section(
            "calendar_agenda", "TODAY'S AGENDA", self._cal_intelligence,
        ))

        # 4. Recommended Next Actions — stretch=1, owns its own internal scroll
        self._recommendations = SmartRecommendationsWidget(self._ctx)
        self._recommendations.action_requested.connect(self.action_requested)
        main_lay.addWidget(
            self._wrap_section(
                "recommendations", "RECOMMENDED NEXT ACTIONS",
                self._recommendations, stretch_content=True,
            ),
            stretch=1,
        )

        h_lay.addWidget(main, stretch=1)

        # ── Right: Quick Actions + Alerts sidebar ─────────────────────────────
        self._sidebar = self._build_actions_sidebar()
        h_lay.addWidget(self._sidebar)

        return page

    def _build_actions_sidebar(self) -> QFrame:
        """220 px fixed-width card holding Quick Actions and Alerts mini."""
        sidebar = QFrame()
        sidebar.setObjectName("dashActionSidebar")
        sidebar.setFixedWidth(220)
        self._sidebar = sidebar  # keep ref for collapse logic

        outer = QVBoxLayout(sidebar)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        # ── Quick Actions section ─────────────────────────────────────────────
        qa_container = QWidget()
        qa_lay = QVBoxLayout(qa_container)
        qa_lay.setContentsMargins(0, 0, 0, 0)
        qa_lay.setSpacing(6)

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
        qa_lay.addLayout(hdr_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        qa_lay.addWidget(sep)

        self._overview_quick_actions = QuickActionsWidget(self._ctx, columns=1)
        self._overview_quick_actions.action_requested.connect(self.action_requested)
        qa_lay.addWidget(self._overview_quick_actions)
        qa_lay.addSpacing(6)

        self._section_widgets["quick_actions"] = qa_container
        outer.addWidget(qa_container)

        # ── Alerts mini section ───────────────────────────────────────────────
        alerts_container = QWidget()
        alerts_lay = QVBoxLayout(alerts_container)
        alerts_lay.setContentsMargins(0, 0, 0, 0)
        alerts_lay.setSpacing(6)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFixedHeight(1)
        alerts_lay.addWidget(sep2)

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
        alerts_lay.addLayout(hdr2_row)

        self._alerts_mini = AlertsMiniWidget(self._ctx)
        self._alerts_mini.navigate_alerts.connect(
            lambda: self._tab_widget.setCurrentIndex(2)
        )
        alerts_lay.addWidget(self._alerts_mini)

        self._section_widgets["alerts_mini"] = alerts_container
        outer.addWidget(alerts_container)
        outer.addStretch()

        return sidebar

    def _build_activity_tab(self) -> QWidget:
        """Full-width, date-grouped recent activity log."""
        page = QWidget()
        page.setMinimumSize(0, 0)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(0)

        self._activity = RecentActivityWidget(self._ctx)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self._activity)

        # Wrap in a section container so it can be hidden
        activity_sec = QWidget()
        sec_lay = QVBoxLayout(activity_sec)
        sec_lay.setContentsMargins(0, 0, 0, 0)
        sec_lay.setSpacing(8)
        lbl = QLabel("RECENT ACTIVITY")
        lbl.setObjectName("dashSectionLabel")
        sec_lay.addWidget(lbl)
        sec_lay.addWidget(scroll, stretch=1)
        self._section_widgets["recent_activity"] = activity_sec

        lay.addWidget(activity_sec, stretch=1)
        return page

    def _build_alerts_tab(self) -> QWidget:
        """Alerts only — notifications panel fills the full pane."""
        page = QWidget()
        page.setMinimumSize(0, 0)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(0)

        self._notifications = NotificationsPanelWidget(self._ctx)
        self._notifications.action_requested.connect(self.action_requested)

        notif_sec = QWidget()
        sec_lay = QVBoxLayout(notif_sec)
        sec_lay.setContentsMargins(0, 0, 0, 0)
        sec_lay.setSpacing(8)
        lbl = QLabel("ALERTS")
        lbl.setObjectName("dashSectionLabel")
        sec_lay.addWidget(lbl)
        sec_lay.addWidget(self._notifications, stretch=1)
        self._section_widgets["notifications"] = notif_sec

        lay.addWidget(notif_sec, stretch=1)
        return page

    # ══════════════════════════════════════════════════════════════════════════
    # Section visibility  (called by plugin.py after settings change)
    # ══════════════════════════════════════════════════════════════════════════

    def set_section_visible(self, section_id: str, visible: bool) -> None:
        """Show or hide a named dashboard section (label + content together)."""
        container = self._section_widgets.get(section_id)
        if container is not None:
            container.setVisible(visible)

        # Collapse the sidebar entirely when both its sections are hidden
        if section_id in ("quick_actions", "alerts_mini"):
            self._update_sidebar_visibility()

    def _update_sidebar_visibility(self) -> None:
        qa  = self._section_widgets.get("quick_actions")
        alm = self._section_widgets.get("alerts_mini")
        qa_vis  = qa.isVisible()  if qa  else True
        alm_vis = alm.isVisible() if alm else True
        if hasattr(self, "_sidebar") and self._sidebar:
            self._sidebar.setVisible(qa_vis or alm_vis)

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
        pass

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _section_lbl(self, text: str, layout) -> QLabel:
        """Small-caps section header — kept for any external callers."""
        lbl = QLabel(text)
        lbl.setObjectName("dashSectionLabel")
        layout.addWidget(lbl)
        return lbl

    def _hline(self) -> QFrame:
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
        # Active-projects strip is refreshed via refresh_active_projects_strip()
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
        try:
            self._projects_strip.refresh(cards)
        except Exception:
            pass

    def refresh_alerts_mini(self, notes: list) -> None:
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
        try:
            self._cal_intelligence.refresh(today, week, milestones, overdue)
        except Exception as e:
            print(f"[DASHBOARD UI] refresh_calendar_intelligence error: {e}")
