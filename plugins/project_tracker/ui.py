# plugins/project_tracker/ui.py
"""
Project Tracker UI
──────────────────
Two-pane layout:
  Left  — scrollable project list with status filter + "New Project" button
  Right — tabbed project detail (Overview · Links · Milestones · Notes · Sessions)
"""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QDate
from PySide6.QtGui import QColor, QPixmap, QFontMetrics, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QTabWidget, QSplitter, QLineEdit,
    QTextEdit, QComboBox, QCheckBox, QDialog, QDialogButtonBox,
    QMessageBox, QSizePolicy, QSpinBox, QGridLayout, QProgressBar,
    QDateEdit, QFileDialog, QApplication,
    QListWidget, QListWidgetItem, QAbstractItemView, QAbstractSpinBox,
)

from ui.animations import AnimatedProgressBar, CountUpLabel, glow_flash, pulse_widget, fade_in
from ui.toast import ToastManager

from .models import (
    Project, ProjectStatus, ProjectCategory, ProjectPriority,
    EntityType, Milestone, ProjectNote, HobbySession,
    GalleryEntry, GalleryStage, EnabledSystem,
    ProjectRequirement, ReqItemType, ReqStatus,
)
from plugins.shared_widgets import LinkedEntityChip


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setObjectName("divider")
    return line


def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("sectionLabel")
    return lbl


STATUS_COLOR = {
    ProjectStatus.ACTIVE:    "#27ae60",
    ProjectStatus.COMPLETED: "#0078d4",
    ProjectStatus.ON_HOLD:   "#f39c12",
    ProjectStatus.ARCHIVED:  "#666666",
}

GAME_SYSTEMS = [
    "", "Warhammer 40,000", "Age of Sigmar", "The Old World",
    "Horus Heresy", "Warcry", "Kill Team",
    "Dungeons & Dragons", "Pathfinder", "Frostgrave",
    "Gundam", "Star Wars Legion", "Other",
]
ICONS = ["📁", "⚔", "🛡", "🤖", "🧙", "🐉", "🏰", "🚀", "💀", "🎲", "🎨", "📖"]


# ─────────────────────────────────────────────────────────────────────────────
# Collapsible section widget
# ─────────────────────────────────────────────────────────────────────────────

class _CollapsibleSection(QWidget):
    """A titled section with a toggle button that shows/hides its content."""

    def __init__(self, title: str, collapsed: bool = True, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header row
        hdr = QWidget()
        hdr.setCursor(Qt.PointingHandCursor)
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(0, 6, 0, 4)
        hdr_lay.setSpacing(6)

        self._arrow = QLabel("▶" if collapsed else "▼")
        self._arrow.setObjectName("collapsibleArrow")
        hdr_lay.addWidget(self._arrow)

        lbl = QLabel(title)
        lbl.setObjectName("collapsibleTitle")
        hdr_lay.addWidget(lbl, stretch=1)

        outer.addWidget(hdr)
        hdr.mousePressEvent = lambda _: self.toggle()

        # Content area
        self._body = QWidget()
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(12, 4, 0, 8)
        self._body_lay.setSpacing(8)
        outer.addWidget(self._body)

        self._collapsed = collapsed
        self._body.setVisible(not collapsed)

    def layout_body(self) -> QVBoxLayout:
        return self._body_lay

    def add_widget(self, w: QWidget):
        self._body_lay.addWidget(w)

    def toggle(self):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._arrow.setText("▶" if self._collapsed else "▼")
        # Propagate geometry change up to the nearest QDialog so it
        # shrinks/grows instead of leaving dead space or a bloated header.
        self.updateGeometry()
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, QDialog):
                QTimer.singleShot(0, parent.adjustSize)
                break
            parent = parent.parent()


# ─────────────────────────────────────────────────────────────────────────────
# Project Card (left sidebar item)
# ─────────────────────────────────────────────────────────────────────────────

class ProjectCard(QFrame):
    clicked = Signal(int)   # emits project.id

    def __init__(self, project: Project, stats=None, parent=None):
        super().__init__(parent)
        self.project_id = project.id
        self.setObjectName("projectCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Main content row ──────────────────────────────────────────────────
        content = QWidget()
        lay = QHBoxLayout(content)
        lay.setContentsMargins(12, 8, 12, 6)
        lay.setSpacing(10)

        # Colour dot
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            f"background:{project.color}; border-radius:5px;"
        )
        lay.addWidget(dot)

        # Text column
        col = QVBoxLayout()
        col.setSpacing(2)
        name_lbl = QLabel(f"{project.icon}  {project.name}")
        name_lbl.setObjectName("projectCardName")
        col.addWidget(name_lbl)

        sub_parts = [s for s in [
            project.game_system,
            ProjectCategory.LABELS.get(getattr(project, "category", ""), "")
                if getattr(project, "category", "") not in ("", "other") else "",
        ] if s]
        sub = "  ·  ".join(sub_parts) if sub_parts else ""

        # Append milestone hint if stats available
        if stats is not None:
            ms_done  = getattr(stats, "milestones_done", 0)
            ms_total = getattr(stats, "milestones_total", 0)
            if ms_total > 0:
                weighted_pct = int(getattr(stats, "milestone_progress", 0) * 100)
                if weighted_pct > 0 and ms_done == 0:
                    hint = f"{ms_done}/{ms_total} milestones  ({weighted_pct}%)"
                else:
                    hint = f"{ms_done}/{ms_total} milestones"
                sub = f"{sub}  ·  {hint}" if sub else hint

        sub_lbl = QLabel(sub or ProjectStatus.LABELS.get(project.status, ""))
        sub_lbl.setObjectName("projectCardSub")
        col.addWidget(sub_lbl)
        lay.addLayout(col, stretch=1)

        # Priority indicator
        priority = getattr(project, "priority", ProjectPriority.MEDIUM)
        if priority == ProjectPriority.HIGH:
            pri_lbl = QLabel("▲")
            pri_lbl.setObjectName("priorityHigh")
            pri_lbl.setToolTip("High priority")
            lay.addWidget(pri_lbl)

        # Status badge
        badge = QLabel(ProjectStatus.LABELS.get(project.status, project.status))
        badge.setObjectName("statusBadge")
        badge.setProperty("status", project.status)
        lay.addWidget(badge)

        outer.addWidget(content)

        # ── Thin milestone progress bar at bottom of card ─────────────────────
        if stats is not None:
            ms_done  = getattr(stats, "milestones_done", 0)
            ms_total = getattr(stats, "milestones_total", 0)
            if ms_total > 0:
                pct = int(getattr(stats, "milestone_progress", 0) * 100)
                bar = QProgressBar()
                bar.setFixedHeight(3)
                bar.setTextVisible(False)
                bar.setRange(0, 100)
                bar.setValue(pct)
                bar.setStyleSheet("""
                    QProgressBar { background: rgba(255,255,255,0.08);
                                   border: none; border-radius: 0px; }
                    QProgressBar::chunk { background: #0078d4; border-radius: 0px; }
                """)
                outer.addWidget(bar)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.project_id)

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)


# ─────────────────────────────────────────────────────────────────────────────
# Left panel — project list
# ─────────────────────────────────────────────────────────────────────────────

class ProjectListPanel(QWidget):
    project_selected = Signal(int)
    new_project_requested = Signal()

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx   = context
        self._cards: dict[int, ProjectCard] = {}
        self._selected_id: Optional[int] = None
        self._build()

    def _build(self):
        self.setObjectName("projectListPanel")
        self.setMinimumWidth(220)
        self.setMaximumWidth(460)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("panelHeader")
        header.setFixedHeight(48)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel("Projects")
        lbl.setObjectName("panelTitle")
        h_lay.addWidget(lbl)
        h_lay.addStretch()
        self._new_btn = QPushButton("＋")
        self._new_btn.setObjectName("iconBtn")
        self._new_btn.setFixedSize(28, 28)
        self._new_btn.setToolTip("New project")
        self._new_btn.clicked.connect(self.new_project_requested)
        h_lay.addWidget(self._new_btn)
        root.addWidget(header)

        # Status filter
        self._filter_combo = QComboBox()
        self._filter_combo.setObjectName("filterCombo")
        self._filter_combo.addItems(["All", "Active", "On Hold", "Completed", "Archived"])
        self._filter_combo.setContentsMargins(8, 4, 8, 0)

        # Connect signal FIRST so the restore below triggers the filter event
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)

        # Restore last-used status filter — fires _on_filter_changed immediately
        try:
            svc = self._ctx.services.try_get("settings")
            saved_filter = svc.get("project_tracker.status_filter", "") if svc else ""
            if saved_filter:
                idx = self._filter_combo.findText(saved_filter)
                if idx >= 0:
                    self._filter_combo.setCurrentIndex(idx)
        except Exception:
            pass

        filter_wrap = QWidget()
        fw = QHBoxLayout(filter_wrap)
        fw.setContentsMargins(8, 6, 8, 4)
        fw.addWidget(self._filter_combo)
        root.addWidget(filter_wrap)

        root.addWidget(_hline())

        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, stretch=1)

        # Empty state
        self._empty_lbl = QLabel("No projects yet.\nClick ＋ to create one.")
        self._empty_lbl.setObjectName("emptyState")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        root.addWidget(self._empty_lbl)

    def load_projects(self, projects: list[Project], stats_map: dict = None):
        stats_map = stats_map or {}
        # Clear existing cards
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()

        # Remove all from layout (except stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._empty_lbl.setVisible(len(projects) == 0)
        self._list_widget.setVisible(len(projects) > 0)

        for p in projects:
            card = ProjectCard(p, stats=stats_map.get(p.id))
            card.clicked.connect(self._on_card_clicked)
            self._cards[p.id] = card
            self._list_layout.insertWidget(
                self._list_layout.count() - 1, card
            )

        # Re-apply selection highlight
        if self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(True)

        # Defer measurement — Qt must finish applying QSS and laying out
        # the new cards before minimumSizeHint() returns meaningful values.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._measure_and_resize)

    def _measure_and_resize(self) -> None:
        """
        Ask Qt's own layout engine for the minimum width needed to show all
        card content (name + badge) without clipping, then apply it.

        Called via QTimer.singleShot(0) so QSS padding, font substitution,
        and emoji advance widths are already resolved before we measure.

        The list_widget's minimumSizeHint() propagates upward from every
        child label's natural text width, so it naturally accounts for:
          • badge QSS padding (2px 8px = +16 px per card)
          • font_base name labels vs font_xs badge labels
          • emoji / special-character glyph widths
        We add the panel's own outer margins (8 px each side = 16 px) and a
        small scrollbar reserve (12 px) on top.
        """
        try:
            hint_w = self._list_widget.minimumSizeHint().width()
            # outer margins (16) + scrollbar reserve (12) + breathing room (8)
            needed = hint_w + 36
            self.setFixedWidth(min(max(needed, 220), 460))
        except Exception:
            pass

    def select_project(self, project_id: int):
        for pid, card in self._cards.items():
            card.set_selected(pid == project_id)
        self._selected_id = project_id

    def _on_card_clicked(self, project_id: int):
        self.select_project(project_id)
        self.project_selected.emit(project_id)

    def _on_filter_changed(self, text: str):
        # Persist the chosen filter
        try:
            svc = self._ctx.services.try_get("settings")
            if svc:
                svc.set("project_tracker.status_filter", text if text != "All" else "")
        except Exception:
            pass

        status_map = {
            "Active":    ProjectStatus.ACTIVE,
            "On Hold":   ProjectStatus.ON_HOLD,
            "Completed": ProjectStatus.COMPLETED,
            "Archived":  ProjectStatus.ARCHIVED,
        }
        status = status_map.get(text)
        self._ctx.event_bus.emit("project_filter_changed", {"status": status})


# ─────────────────────────────────────────────────────────────────────────────
# Overview tab
# ─────────────────────────────────────────────────────────────────────────────

class ProjectOverviewTab(QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx               = context
        self._project:            Optional[Project] = None
        self._suggestion_ms_id:   Optional[int]     = None   # milestone id for pending Set Focus
        self._resume_project_id:  Optional[int]     = None   # project id for pending Resume
        self._build()

    def _build(self):
        # Outer layout holds only the scroll area so the tab never forces
        # the window taller than the screen.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        _content = QWidget()
        root = QVBoxLayout(_content)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)
        scroll.setWidget(_content)

        # ── Project header card ───────────────────────────────────────────────
        self._header_card = QFrame()
        self._header_card.setObjectName("projectHeaderCard")
        hc_lay = QVBoxLayout(self._header_card)
        hc_lay.setContentsMargins(16, 14, 16, 14)
        hc_lay.setSpacing(6)

        self._name_lbl = QLabel()
        self._name_lbl.setObjectName("projectDetailName")
        hc_lay.addWidget(self._name_lbl)

        self._system_lbl = QLabel()
        self._system_lbl.setObjectName("projectDetailSystem")
        hc_lay.addWidget(self._system_lbl)

        self._desc_lbl = QLabel()
        self._desc_lbl.setObjectName("projectDetailDesc")
        self._desc_lbl.setWordWrap(True)
        hc_lay.addWidget(self._desc_lbl)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self._status_badge = QLabel()
        self._status_badge.setObjectName("statusBadgeLarge")
        meta_row.addWidget(self._status_badge)
        self._category_badge = QLabel()
        self._category_badge.setObjectName("categoryBadge")
        meta_row.addWidget(self._category_badge)
        self._priority_badge = QLabel()
        self._priority_badge.setObjectName("priorityBadge")
        meta_row.addWidget(self._priority_badge)
        self._date_lbl = QLabel()
        self._date_lbl.setObjectName("metaLabel")
        meta_row.addWidget(self._date_lbl)
        meta_row.addStretch()
        hc_lay.addLayout(meta_row)

        # Tags row
        self._tags_row = QHBoxLayout()
        self._tags_row.setSpacing(4)
        self._tags_container = QWidget()
        self._tags_container_lay = QHBoxLayout(self._tags_container)
        self._tags_container_lay.setContentsMargins(0, 0, 0, 0)
        self._tags_container_lay.setSpacing(4)
        self._tags_row.addWidget(self._tags_container)
        self._tags_row.addStretch()
        hc_lay.addLayout(self._tags_row)
        self._tags_container.hide()

        # Overall progress bar
        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        self._overall_pct_lbl = QLabel("0%")
        self._overall_pct_lbl.setObjectName("progressPctLabel")
        self._overall_pct_lbl.setFixedWidth(38)
        self._overall_bar = AnimatedProgressBar()
        self._overall_bar.setObjectName("overallProgressBar")
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setTextVisible(False)
        self._overall_bar.setFixedHeight(8)
        progress_row.addWidget(self._overall_bar, stretch=1)
        progress_row.addWidget(self._overall_pct_lbl)
        hc_lay.addLayout(progress_row)

        root.addWidget(self._header_card)

        # ── Stats row ─────────────────────────────────────────────────────────
        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(10)
        self._stat_models   = self._make_stat_card("Models",       "0",     animated=True)
        self._stat_paints   = self._make_stat_card("Paints",       "0",     animated=True)
        self._stat_done     = self._make_stat_card("Milestones",   "0 / 0", animated=False)
        self._stat_hours    = self._make_stat_card("Hours Logged", "0",     animated=True)
        for card in [self._stat_models, self._stat_paints,
                     self._stat_done, self._stat_hours]:
            self._stats_row.addWidget(card)
        root.addLayout(self._stats_row)

        # ── Session momentum signals (subtle, below stat cards) ───────────────
        self._momentum_lbl = QLabel()
        self._momentum_lbl.setObjectName("dimLabel")
        self._momentum_lbl.setAlignment(Qt.AlignCenter)
        self._momentum_lbl.setWordWrap(True)
        root.addWidget(self._momentum_lbl)
        self._momentum_lbl.hide()

        # ── Progress section ──────────────────────────────────────────────────
        self._progress_section_lbl = _section_lbl("PROGRESS")
        root.addWidget(self._progress_section_lbl)
        self._progress_frame = QFrame()
        self._progress_frame.setObjectName("progressFrame")
        pf_lay = QVBoxLayout(self._progress_frame)
        pf_lay.setContentsMargins(12, 10, 12, 10)
        pf_lay.setSpacing(10)

        # Milestone progress — wrapped in QWidget so we can show/hide it
        self._milestone_bar_row = self._make_progress_row(
            "Milestones", "milestoneProgressBar"
        )
        self._milestone_bar_widget = QWidget()
        self._milestone_bar_widget.setLayout(self._milestone_bar_row["layout"])
        pf_lay.addWidget(self._milestone_bar_widget)

        # Model painting progress — wrapped in QWidget so we can show/hide it
        self._painting_bar_row = self._make_progress_row(
            "Painting Progress", "paintingProgressBar"
        )
        self._painting_bar_widget = QWidget()
        self._painting_bar_widget.setLayout(self._painting_bar_row["layout"])
        pf_lay.addWidget(self._painting_bar_widget)

        root.addWidget(self._progress_frame)

        # ── Active session indicator ──────────────────────────────────────────
        self._session_banner = QFrame()
        self._session_banner.setObjectName("liveSessionBanner")
        _sb_lay = QHBoxLayout(self._session_banner)
        _sb_lay.setContentsMargins(12, 8, 12, 8)
        _sb_lay.setSpacing(8)
        _sb_lay.addWidget(QLabel("🔴"))
        self._session_banner_lbl = QLabel("Hobby session currently in progress")
        self._session_banner_lbl.setObjectName("liveSessionLabel")
        _sb_lay.addWidget(self._session_banner_lbl, stretch=1)
        root.addWidget(self._session_banner)
        self._session_banner.hide()

        # ── Current Focus ─────────────────────────────────────────────────────
        self._focus_frame = QFrame()
        self._focus_frame.setObjectName("focusCard")
        _focus_lay = QHBoxLayout(self._focus_frame)
        _focus_lay.setContentsMargins(12, 8, 12, 8)
        _focus_lay.setSpacing(8)
        _focus_lay.addWidget(QLabel("🎯"))
        self._focus_lbl = QLabel()
        self._focus_lbl.setObjectName("focusLabel")
        self._focus_lbl.setWordWrap(True)
        _focus_lay.addWidget(self._focus_lbl, stretch=1)
        root.addWidget(self._focus_frame)
        self._focus_frame.hide()

        # ── Focus suggestion (soft — never auto-assigned) ──────────────────────
        self._suggestion_frame = QFrame()
        self._suggestion_frame.setObjectName("suggestionCard")
        _sug_lay = QHBoxLayout(self._suggestion_frame)
        _sug_lay.setContentsMargins(12, 8, 12, 8)
        _sug_lay.setSpacing(8)
        _sug_lay.addWidget(QLabel("💡"))
        self._suggestion_lbl = QLabel()
        self._suggestion_lbl.setObjectName("suggestionLabel")
        self._suggestion_lbl.setWordWrap(True)
        _sug_lay.addWidget(self._suggestion_lbl, stretch=1)
        self._suggestion_btn = QPushButton("Set Focus")
        self._suggestion_btn.setObjectName("secondaryBtn")
        self._suggestion_btn.setFixedHeight(28)
        self._suggestion_btn.clicked.connect(self._on_set_suggestion_focus)
        _sug_lay.addWidget(self._suggestion_btn)
        root.addWidget(self._suggestion_frame)
        self._suggestion_frame.hide()

        # ── Session resume hint (shown when last session < 48 h ago) ──────────
        self._resume_banner = QFrame()
        self._resume_banner.setObjectName("resumeBanner")
        _res_lay = QHBoxLayout(self._resume_banner)
        _res_lay.setContentsMargins(12, 8, 12, 8)
        _res_lay.setSpacing(8)
        _res_lay.addWidget(QLabel("⏱"))
        self._resume_lbl = QLabel("You worked on this recently — start a new session?")
        self._resume_lbl.setObjectName("resumeLabel")
        self._resume_lbl.setWordWrap(True)
        _res_lay.addWidget(self._resume_lbl, stretch=1)
        self._resume_btn = QPushButton("Start Session")
        self._resume_btn.setObjectName("secondaryBtn")
        self._resume_btn.setFixedHeight(28)
        self._resume_btn.clicked.connect(self._on_resume_session)
        _res_lay.addWidget(self._resume_btn)
        root.addWidget(self._resume_banner)
        self._resume_banner.hide()

        # ── Milestones preview ────────────────────────────────────────────────
        self._milestones_section_lbl = _section_lbl("MILESTONES")
        root.addWidget(self._milestones_section_lbl)
        self._milestones_preview = QWidget()
        self._milestones_preview_lay = QVBoxLayout(self._milestones_preview)
        self._milestones_preview_lay.setContentsMargins(0, 0, 0, 0)
        self._milestones_preview_lay.setSpacing(4)
        root.addWidget(self._milestones_preview)

        root.addStretch()

    def _make_progress_row(self, label: str, bar_name: str) -> dict:
        """Returns a dict with 'layout', 'bar', 'pct_lbl', 'detail_lbl'."""
        lay = QVBoxLayout()
        lay.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(8)
        name_lbl = QLabel(label)
        name_lbl.setObjectName("progressRowLabel")
        pct_lbl = QLabel("0%")
        pct_lbl.setObjectName("progressPctLabel")
        detail_lbl = QLabel("")
        detail_lbl.setObjectName("dimLabel")
        header.addWidget(name_lbl)
        header.addStretch()
        header.addWidget(detail_lbl)
        header.addWidget(pct_lbl)
        lay.addLayout(header)

        bar = AnimatedProgressBar()
        bar.setObjectName(bar_name)
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(10)
        lay.addWidget(bar)

        return {"layout": lay, "bar": bar, "pct_lbl": pct_lbl,
                "detail_lbl": detail_lbl}

    def _set_progress_row(self, row: dict, done: int, total: int,
                          detail: str = "") -> int:
        """Update a progress row, animating if the bar supports it. Returns pct."""
        pct = int(done / total * 100) if total > 0 else 0
        bar = row["bar"]
        if hasattr(bar, "set_value_animated"):
            bar.set_value_animated(pct)
        else:
            bar.setValue(pct)
        row["pct_lbl"].setText(f"{pct}%")
        row["detail_lbl"].setText(detail)
        return pct

    def _make_stat_card(self, label: str, value: str,
                        animated: bool = False) -> QFrame:
        card = QFrame()
        card.setObjectName("miniStatCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        # Use CountUpLabel for pure-numeric stats (models, paints, hours)
        val_lbl = CountUpLabel(value) if animated else QLabel(value)
        val_lbl.setObjectName("miniStatValue")
        val_lbl.setAlignment(Qt.AlignCenter)
        lbl_lbl = QLabel(label)
        lbl_lbl.setObjectName("miniStatLabel")
        lbl_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl = QLabel("")
        sub_lbl.setObjectName("dimLabel")
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setVisible(False)
        lay.addWidget(val_lbl)
        lay.addWidget(lbl_lbl)
        lay.addWidget(sub_lbl)
        card._value_lbl   = val_lbl
        card._label_lbl   = lbl_lbl
        card._sub_lbl     = sub_lbl
        card._is_animated = animated
        return card

    def load(self, project: Project, stats, milestones: list[Milestone]):
        self._project = project

        self._name_lbl.setText(f"{project.icon}  {project.name}")
        self._system_lbl.setText(project.game_system or "")
        self._desc_lbl.setText(project.description or "")
        self._desc_lbl.setVisible(bool(project.description))

        # Status badge
        status_label = ProjectStatus.LABELS.get(project.status, project.status)
        self._status_badge.setText(status_label)
        self._status_badge.setProperty("status", project.status)
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

        # Category badge
        cat = getattr(project, "category", "") or ""
        cat_label = ProjectCategory.LABELS.get(cat, "")
        if cat_label and cat != ProjectCategory.OTHER:
            self._category_badge.setText(ProjectCategory.ICONS.get(cat, "") + "  " + cat_label)
            self._category_badge.show()
        else:
            self._category_badge.hide()

        # Priority badge
        pri = getattr(project, "priority", ProjectPriority.MEDIUM) or ProjectPriority.MEDIUM
        pri_color = ProjectPriority.COLORS.get(pri, "#606060")
        pri_label = ProjectPriority.LABELS.get(pri, "")
        if pri != ProjectPriority.MEDIUM:
            self._priority_badge.setText(pri_label)
            self._priority_badge.setStyleSheet(
                f"color: {pri_color}; font-weight: 700; background: transparent;"
            )
            self._priority_badge.show()
        else:
            self._priority_badge.hide()

        # Tags
        tags = getattr(project, "tags", []) or []
        while self._tags_container_lay.count():
            item = self._tags_container_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if tags:
            for tag in tags[:8]:   # cap at 8 displayed tags
                chip = QLabel(tag)
                chip.setObjectName("tagChip")
                self._tags_container_lay.addWidget(chip)
            self._tags_container.show()
        else:
            self._tags_container.hide()

        if project.target_date:
            self._date_lbl.setText(f"📅  Target: {project.target_date}")
        else:
            self._date_lbl.setText("")

        # Active session indicator
        has_active = getattr(stats, "has_active_session", False)
        if has_active:
            self._session_banner.show()
        else:
            self._session_banner.hide()

        # Focus milestone
        focus_ms = next((m for m in milestones if getattr(m, "is_focus", False)), None)
        if focus_ms:
            focus_text = f"<b>Current Focus:</b>  {focus_ms.title}"
            if focus_ms.has_quantity:
                focus_text += f"  <span style='color:#888;font-size:11px;'>({focus_ms.quantity_done}/{focus_ms.quantity_total})</span>"
            self._focus_lbl.setText(focus_text)
            self._focus_frame.show()
        else:
            self._focus_frame.hide()

        # ── Focus suggestion — only when: no current focus, milestones exist,
        #    no active session (live sessions take visual priority)
        incomplete = [m for m in milestones if not m.is_complete]
        if not focus_ms and incomplete and not has_active:
            # Priority: overdue first → earliest due date → first incomplete
            overdue_ms = [m for m in incomplete if m.is_overdue]
            due_sorted = sorted(
                [m for m in incomplete if m.due_date and not m.is_overdue],
                key=lambda m: m.due_date,
            )
            candidate = (overdue_ms[0] if overdue_ms
                         else due_sorted[0] if due_sorted
                         else incomplete[0])

            self._suggestion_ms_id = candidate.id
            self._suggestion_lbl.setText(
                f"Set <b>{candidate.title}</b> as your current focus?"
            )
            self._suggestion_frame.show()
        else:
            self._suggestion_ms_id = None
            self._suggestion_frame.hide()

        # ── Session resume hint — shown when last session was within 48 h
        #    and no active session is running
        self._resume_project_id = None
        self._resume_banner.hide()
        if not has_active:
            last_at = getattr(stats, "last_session_at", None)
            if last_at:
                try:
                    from datetime import timezone as _tz
                    last_dt = datetime.fromisoformat(
                        last_at.replace("Z", "+00:00")
                    )
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=_tz.utc)
                    now_dt = datetime.now(_tz.utc)
                    hours_ago = (now_dt - last_dt).total_seconds() / 3600
                    if hours_ago <= 48:
                        h = int(hours_ago)
                        time_str = f"{h}h ago" if h > 0 else "just now"
                        self._resume_lbl.setText(
                            f"You worked on this <b>{time_str}</b> — start a new session?"
                        )
                        self._resume_project_id = project.id
                        self._resume_banner.show()
                except Exception:
                    pass

        # ── Enabled-systems visibility ─────────────────────────────────────────
        enabled = getattr(project, "enabled_systems", None) or []

        def _sys_on(key: str) -> bool:
            """True when enabled_systems is empty (all-on legacy) or key is present."""
            return not enabled or key in enabled

        # Stat cards
        self._stat_models.setVisible(_sys_on(EnabledSystem.MODELS))
        self._stat_paints.setVisible(_sys_on(EnabledSystem.PAINTS))
        self._stat_done.setVisible(_sys_on(EnabledSystem.MILESTONES))

        # Progress bars
        show_ms_bar   = _sys_on(EnabledSystem.MILESTONES)
        show_paint_bar = _sys_on(EnabledSystem.MODELS)
        self._milestone_bar_widget.setVisible(show_ms_bar)
        self._painting_bar_widget.setVisible(show_paint_bar)

        # Hide the entire Progress section if nothing in it is visible
        any_progress = show_ms_bar or show_paint_bar
        self._progress_frame.setVisible(any_progress)
        self._progress_section_lbl.setVisible(any_progress)

        # Milestones preview section + its label
        ms_enabled = _sys_on(EnabledSystem.MILESTONES)
        self._milestones_section_lbl.setVisible(ms_enabled)
        self._milestones_preview.setVisible(ms_enabled)

        # ── Stat cards ───────────────────────────────────────────────────────────
        # Models — show individual miniature count; subtitle shows type breakdown
        model_total = stats.total_model_count if stats.total_model_count > 0 else stats.total_models
        model_types = stats.total_models
        try:
            self._stat_models._value_lbl.count_to(float(model_total))
        except Exception:
            self._stat_models._value_lbl.setText(str(model_total))
        # Update card label and subtitle
        if model_total != model_types and model_types > 0:
            self._stat_models._label_lbl.setText("Miniatures")
            self._stat_models._sub_lbl.setText(
                f"{model_types} type{'s' if model_types != 1 else ''}"
            )
            self._stat_models._sub_lbl.setVisible(True)
        elif model_types > 1:
            self._stat_models._label_lbl.setText("Models")
            self._stat_models._sub_lbl.setText(f"{model_types} types")
            self._stat_models._sub_lbl.setVisible(True)
        else:
            self._stat_models._label_lbl.setText("Models")
            self._stat_models._sub_lbl.setVisible(False)

        # Paints
        try:
            self._stat_paints._value_lbl.count_to(float(stats.total_paints))
        except Exception:
            self._stat_paints._value_lbl.setText(str(stats.total_paints))

        # Milestones — "done / total" with pending count as subtitle
        self._stat_done._value_lbl.setText(
            f"{stats.milestones_done} / {stats.milestones_total}"
        )
        pending = stats.milestones_total - stats.milestones_done
        if stats.milestones_total > 0:
            self._stat_done._sub_lbl.setText(
                f"{pending} remaining" if pending > 0 else "All complete ✓"
            )
            self._stat_done._sub_lbl.setVisible(True)
        else:
            self._stat_done._sub_lbl.setVisible(False)

        # Hours — show session count as subtitle
        try:
            self._stat_hours._value_lbl.count_to(float(stats.total_hours))
        except Exception:
            self._stat_hours._value_lbl.setText(str(stats.total_hours))
        if stats.total_sessions > 0:
            self._stat_hours._sub_lbl.setText(
                f"{stats.total_sessions} session{'s' if stats.total_sessions != 1 else ''}"
            )
            self._stat_hours._sub_lbl.setVisible(True)
        else:
            self._stat_hours._sub_lbl.setVisible(False)

        # ── Session momentum signals ─────────────────────────────────────────────
        recent_cnt = getattr(stats, "recent_session_count", 0)
        avg_dur    = getattr(stats, "avg_session_duration", 0.0)
        if recent_cnt > 0:
            parts = []
            if recent_cnt == 1:
                parts.append("Worked on this once this week")
            else:
                parts.append(f"Worked on this {recent_cnt}× this week")
            if avg_dur > 0:
                avg_h = int(avg_dur) // 60
                avg_m = int(avg_dur) % 60
                avg_str = f"{avg_h}h {avg_m}m" if avg_h else f"{avg_m}m"
                parts.append(f"avg {avg_str} per session")
            self._momentum_lbl.setText("  ·  ".join(parts))
            self._momentum_lbl.show()
        else:
            self._momentum_lbl.hide()

        # ── Progress bars ────────────────────────────────────────────────────────
        ms_done     = stats.milestones_done
        ms_total    = stats.milestones_total
        ms_pct      = int(stats.milestone_progress * 100)   # weighted, accounts for qty milestones
        # Detail text: integer done/total + weighted pct when partial milestones exist
        in_progress_qty = ms_total - ms_done > 0 and stats.milestones_weighted_done > ms_done
        if ms_total:
            if in_progress_qty:
                ms_detail = f"{ms_done} of {ms_total} complete  ·  {ms_pct}% overall"
            else:
                ms_detail = f"{ms_done} of {ms_total} complete"
        else:
            ms_detail = "No milestones yet"
        # Drive the bar with the weighted percentage directly
        bar = self._milestone_bar_row["bar"]
        if hasattr(bar, "set_value_animated"):
            bar.set_value_animated(ms_pct)
        else:
            bar.setValue(ms_pct)
        self._milestone_bar_row["pct_lbl"].setText(f"{ms_pct}%")
        self._milestone_bar_row["detail_lbl"].setText(ms_detail)

        pm_done  = stats.painted_models
        pm_total = stats.total_model_count or stats.total_models
        unit     = "miniature" if (pm_total != model_types and pm_total > 0) else "model"
        self._set_progress_row(
            self._painting_bar_row, pm_done, pm_total,
            f"{pm_done} of {pm_total} {unit}{'s' if pm_total != 1 else ''} painted"
            if pm_total else "No models linked yet"
        )

        # Overall progress — use weighted milestone pct so partial qty milestones contribute
        pcts = []
        if ms_total > 0:
            pcts.append(ms_pct)
        if pm_total > 0:
            pcts.append(int(pm_done / pm_total * 100))
        overall = int(sum(pcts) / len(pcts)) if pcts else 0

        # Per-project progress cache — keyed by project ID so switching between
        # projects never accidentally triggers the completion toast.
        # old_overall == -1 means "not seen this project in this session yet",
        # which intentionally prevents firing on the very first load.
        if not hasattr(self, "_project_overall_cache"):
            self._project_overall_cache: dict[int, int] = {}
        old_overall = self._project_overall_cache.get(project.id, -1)
        self._project_overall_cache[project.id] = overall

        self._overall_bar.set_value_animated(overall)
        self._overall_pct_lbl.setText(f"{overall}%")

        # 🎉 Completion toast — fires only when THIS project transitions from
        # <100 % to 100 % within the same session.  old_overall >= 0 guards
        # against triggering on the first ever load of an already-complete project.
        if overall == 100 and old_overall < 100 and old_overall >= 0:
            try:
                glow_flash(self._overall_bar, color="#3dba6e", radius=26, duration=1200)
                ToastManager.instance().show(
                    f"🎉  {project.icon}  '{project.name}' is complete!",
                    level="celebration",
                    duration=6000,
                )
            except Exception:
                pass

        # Milestone preview (first 5)
        while self._milestones_preview_lay.count():
            item = self._milestones_preview_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not milestones:
            empty = QLabel("No milestones added yet.")
            empty.setObjectName("emptyState")
            self._milestones_preview_lay.addWidget(empty)
        else:
            for m in milestones[:5]:
                row = self._make_milestone_preview_row(m)
                self._milestones_preview_lay.addWidget(row)
            if len(milestones) > 5:
                more = QLabel(f"  + {len(milestones)-5} more…")
                more.setObjectName("dimLabel")
                self._milestones_preview_lay.addWidget(more)

    # ── Focus suggestion / session resume action handlers ─────────────────────

    def _on_set_suggestion_focus(self):
        """User accepted the focus suggestion — emit event to set focus."""
        mid = self._suggestion_ms_id
        pid = self._project.id if self._project else None
        if not mid or not pid:
            return
        self._ctx.event_bus.emit("project_milestone_focus_toggle", {"id": mid})
        self._suggestion_frame.hide()

    def _on_resume_session(self):
        """User clicked Start Session from the resume banner."""
        pid = self._resume_project_id
        if not pid:
            return
        self._ctx.event_bus.emit("project_session_start", {"project_id": pid})
        self._resume_banner.hide()

    def _make_milestone_preview_row(self, m: Milestone) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)

        # Status icon
        if m.is_complete:
            icon = "✅"
        elif m.is_overdue:
            icon = "⚠️"
        elif getattr(m, "is_focus", False):
            icon = "🎯"
        else:
            icon = "◻"

        title_lbl = QLabel(f"{icon}  {m.title}")
        title_lbl.setObjectName(
            "milestoneTitleDone" if m.is_complete else
            ("milestoneTitleOverdue" if m.is_overdue else "milestonePreviewLabel")
        )
        lay.addWidget(title_lbl, stretch=1)

        # Quantity progress badge
        if m.has_quantity and not m.is_complete:
            qty_lbl = QLabel(f"{m.quantity_done}/{m.quantity_total}")
            qty_lbl.setObjectName("dimLabel")
            qty_lbl.setToolTip(f"{int(m.quantity_progress * 100)}% complete")
            lay.addWidget(qty_lbl)

        # Overdue / due date
        if m.is_overdue:
            overdue_lbl = QLabel("Overdue")
            overdue_lbl.setStyleSheet("color: #c62828; font-size: 10px; font-weight: 600;")
            lay.addWidget(overdue_lbl)
        elif m.due_date and not m.is_complete:
            date_lbl = QLabel(m.due_date)
            date_lbl.setObjectName("dimLabel")
            lay.addWidget(date_lbl)

        return row


# ─────────────────────────────────────────────────────────────────────────────
# Milestones tab
# ─────────────────────────────────────────────────────────────────────────────

class MilestonesTab(QWidget):
    changed                = Signal()
    note_navigate_requested = Signal(object)   # emits Milestone

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx           = context
        self._project_id:   Optional[int] = None
        self._milestones:   list[Milestone] = []
        self._notes:        list = []
        self._milestone_rows: dict[int, QFrame] = {}   # id → row widget for scroll-to
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Toolbar
        tb = QHBoxLayout()
        tb.addWidget(_section_lbl("MILESTONES"))
        tb.addStretch()
        add_btn = QPushButton("＋ Add Milestone")
        add_btn.setObjectName("secondaryBtn")
        add_btn.clicked.connect(self._add_milestone)
        tb.addWidget(add_btn)
        root.addLayout(tb)

        # List area
        self._ms_scroll = QScrollArea()
        self._ms_scroll.setWidgetResizable(True)
        self._ms_scroll.setFrameShape(QFrame.NoFrame)

        self._list_widget = QWidget()
        self._list_lay    = QVBoxLayout(self._list_widget)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(4)
        self._list_lay.addStretch()
        self._ms_scroll.setWidget(self._list_widget)
        root.addWidget(self._ms_scroll, stretch=1)

    def load(self, project_id: int, milestones: list[Milestone], notes: list = None):
        self._project_id = project_id
        self._milestones = milestones
        self._notes      = notes or []
        self._render()

    def _render(self):
        self._milestone_rows.clear()
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._milestones:
            empty = QLabel(
                "No milestones yet.\n\n"
                "Add a milestone to break your project into trackable steps."
            )
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self._list_lay.insertWidget(0, empty)
            return

        for m in self._milestones:
            row = self._make_row(m)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)

    def scroll_to_item(self, item_id: int) -> None:
        """Scroll to the milestone row matching *item_id* and briefly highlight it."""
        row = self._milestone_rows.get(item_id)
        if not row:
            return
        # Ensure the row is visible in the scroll area
        self._ms_scroll.ensureWidgetVisible(row, 0, 20)
        # Brief highlight: swap objectName to trigger a CSS accent, then revert
        row.setObjectName("milestoneRowHighlight")
        row.style().unpolish(row)
        row.style().polish(row)
        QTimer.singleShot(1400, lambda: (
            row.setObjectName("milestoneRow"),
            row.style().unpolish(row),
            row.style().polish(row),
        ))

    def _make_row(self, m: Milestone) -> QFrame:
        row = QFrame()
        row.setObjectName("milestoneRow")
        if m.id:
            self._milestone_rows[m.id] = row
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        # Focus star
        is_focus = getattr(m, "is_focus", False)
        if is_focus:
            star = QLabel("⭐")
            star.setToolTip("Current focus milestone")
            lay.addWidget(star)

        chk = QCheckBox()
        chk.setChecked(m.is_complete)
        chk.setToolTip("Mark complete / incomplete")
        chk.toggled.connect(
            lambda checked, mid=m.id, t=m.title: self._toggle(mid, checked, t)
        )
        lay.addWidget(chk)

        col = QVBoxLayout()
        col.setSpacing(3)
        title_lbl = QLabel(m.title)
        title_lbl.setObjectName(
            "milestoneTitleDone" if m.is_complete else
            ("milestoneTitleOverdue" if m.is_overdue else "milestoneTitlePending")
        )
        col.addWidget(title_lbl)

        # Quantity mini-bar — shown inline under title when tracking is enabled
        if getattr(m, "has_quantity", False):
            qt   = m.quantity_total
            done = m.quantity_done
            pct  = int(done / qt * 100) if qt else 0
            qty_row = QHBoxLayout()
            qty_row.setSpacing(6)
            qty_row.setContentsMargins(0, 0, 0, 0)
            mini_bar = QProgressBar()
            mini_bar.setFixedHeight(4)
            mini_bar.setTextVisible(False)
            mini_bar.setRange(0, 100)
            mini_bar.setValue(pct)
            mini_bar.setStyleSheet("""
                QProgressBar { background: rgba(255,255,255,0.1);
                               border: none; border-radius: 2px; }
                QProgressBar::chunk { background: #0078d4; border-radius: 2px; }
            """)
            qty_row.addWidget(mini_bar, stretch=1)
            qty_count = QLabel(f"{done} / {qt}")
            qty_count.setObjectName("dimLabel")
            qty_count.setToolTip(f"{pct}% complete")
            qty_row.addWidget(qty_count)
            col.addLayout(qty_row)

        # Sub-info row: due date + effort
        sub_parts = []
        if m.is_overdue:
            sub_parts.append("⚠  Overdue")
        elif m.due_date:
            sub_parts.append(f"Due: {m.due_date}")
        effort = getattr(m, "estimated_effort_minutes", 0) or 0
        if effort > 0:
            effort_h = effort // 60
            effort_m = effort % 60
            effort_str = f"{effort_h}h {effort_m}m" if effort_h else f"{effort_m}m"
            sub_parts.append(f"Est. {effort_str}")
        if sub_parts:
            d_lbl = QLabel("  ·  ".join(sub_parts))
            d_lbl.setObjectName(
                "milestoneOverdueHint" if m.is_overdue else "dimLabel"
            )
            col.addWidget(d_lbl)

        lay.addLayout(col, stretch=1)

        # Quantity +/− stepper buttons — right side, only for quantity milestones
        if getattr(m, "has_quantity", False) and not m.is_complete:
            minus_btn = QPushButton("−")
            minus_btn.setObjectName("iconBtn")
            minus_btn.setFixedSize(22, 22)
            minus_btn.setToolTip("Subtract one")
            minus_btn.clicked.connect(
                lambda _, mid=m.id: self._ctx.event_bus.emit(
                    "project_milestone_quantity_step", {"id": mid, "delta": -1}
                )
            )
            lay.addWidget(minus_btn)

            plus_btn_qty = QPushButton("＋")
            plus_btn_qty.setObjectName("iconBtn")
            plus_btn_qty.setFixedSize(22, 22)
            plus_btn_qty.setToolTip("Add one")
            plus_btn_qty.clicked.connect(
                lambda _, mid=m.id: self._ctx.event_bus.emit(
                    "project_milestone_quantity_step", {"id": mid, "delta": 1}
                )
            )
            lay.addWidget(plus_btn_qty)

        # Priority badge
        priority = getattr(m, "priority", ProjectPriority.MEDIUM) or ProjectPriority.MEDIUM
        if priority != ProjectPriority.MEDIUM:
            pri_color = ProjectPriority.COLORS.get(priority, "#606060")
            pri_lbl = QLabel(ProjectPriority.LABELS.get(priority, priority))
            pri_lbl.setStyleSheet(
                f"color: {pri_color}; font-weight: 700; font-size: 11px; background: transparent;"
            )
            lay.addWidget(pri_lbl)

        # Edit button
        edit_btn = QPushButton("✎")
        edit_btn.setObjectName("iconBtn")
        edit_btn.setFixedSize(24, 24)
        edit_btn.setToolTip("Edit milestone")
        edit_btn.clicked.connect(lambda _, ms=m: self._edit_milestone(ms))
        lay.addWidget(edit_btn)

        # Note button — opens linked note or creates+links one
        linked_note_id = getattr(m, "linked_note_id", None)
        note_btn = QPushButton("📝" if linked_note_id else "📄")
        note_btn.setObjectName("iconBtn")
        note_btn.setFixedSize(24, 24)
        note_btn.setToolTip(
            "Open linked note" if linked_note_id else "Create & link a note for this milestone"
        )
        note_btn.clicked.connect(lambda _, ms=m: self.note_navigate_requested.emit(ms))
        lay.addWidget(note_btn)

        # Focus toggle button
        focus_btn = QPushButton("⭐" if is_focus else "☆")
        focus_btn.setObjectName("iconBtn")
        focus_btn.setFixedSize(24, 24)
        focus_btn.setToolTip("Unmark as focus" if is_focus else "Set as current focus")
        focus_btn.clicked.connect(lambda _, mid=m.id: self._toggle_focus(mid))
        lay.addWidget(focus_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("iconBtn")
        del_btn.setFixedSize(24, 24)
        del_btn.clicked.connect(lambda _, mid=m.id: self._delete(mid))
        lay.addWidget(del_btn)

        return row

    def _toggle_focus(self, milestone_id: int):
        self._ctx.event_bus.emit("project_milestone_focus_toggle", {"id": milestone_id})

    def _toggle(self, milestone_id: int,
                is_complete: bool = True, title: str = "") -> None:
        # Show toast BEFORE emitting the event so that the toast is created
        # while the widget tree is still stable (the event causes a reload
        # which can destroy the current row widgets synchronously).
        if is_complete:
            label = f"✓  '{title}'" if title else "✓  Milestone complete"
            ToastManager.instance().show(label, level="success", duration=2500)
        self._ctx.event_bus.emit("project_milestone_toggle", {"id": milestone_id})

    def _delete(self, milestone_id: int):
        self._ctx.event_bus.emit("project_milestone_delete", {"id": milestone_id})

    def _add_milestone(self):
        if not self._project_id:
            return
        dlg = _MilestoneDialog(notes=self._notes, parent=self)
        if dlg.exec():
            data = dlg.get_values()
            data["project_id"] = self._project_id
            self._ctx.event_bus.emit("project_milestone_add", data)

    def _edit_milestone(self, milestone):
        dlg = _MilestoneDialog(milestone=milestone, notes=self._notes, parent=self)
        if dlg.exec():
            data = dlg.get_values()
            data["id"] = milestone.id
            self._ctx.event_bus.emit("project_milestone_update", data)


class _MilestoneDialog(QDialog):
    def __init__(self, milestone=None, notes: list = None, parent=None):
        super().__init__(parent)
        self._milestone = milestone
        self._notes = notes or []
        is_edit = milestone is not None
        self.setWindowTitle("Edit Milestone" if is_edit else "Add Milestone")
        self.setMinimumWidth(640)
        self.setSizeGripEnabled(True)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # ── Core fields ───────────────────────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnMinimumWidth(0, 110)
        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("Title *"), 0, 0)
        self._title = QLineEdit()
        self._title.setPlaceholderText("e.g. Base-coating complete")
        grid.addWidget(self._title, 0, 1)

        grid.addWidget(QLabel("Description"), 1, 0, Qt.AlignTop)
        self._desc = QTextEdit()
        self._desc.setFixedHeight(56)
        self._desc.setPlaceholderText("Optional description…")
        grid.addWidget(self._desc, 1, 1)

        grid.addWidget(QLabel("Due date"), 2, 0)
        self._date = QLineEdit()
        self._date.setPlaceholderText("YYYY-MM-DD (optional)")
        grid.addWidget(self._date, 2, 1)

        # Quantity tracking
        grid.addWidget(QLabel("Track quantity"), 3, 0)
        qty_row = QHBoxLayout()
        qty_row.setSpacing(6)
        self._qty_chk = QCheckBox("Enable (e.g. 20 Clanrats)")
        qty_row.addWidget(self._qty_chk)
        qty_row.addSpacing(12)
        qty_row.addWidget(QLabel("Total:"))
        self._qty_total = QSpinBox()
        self._qty_total.setRange(1, 9999)
        self._qty_total.setValue(10)
        self._qty_total.setEnabled(False)
        self._qty_total.setFixedWidth(72)
        qty_row.addWidget(self._qty_total)
        if is_edit:
            qty_row.addSpacing(12)
            qty_row.addWidget(QLabel("Done so far:"))
            self._qty_done = QSpinBox()
            self._qty_done.setRange(0, 9999)
            self._qty_done.setValue(0)
            self._qty_done.setEnabled(False)
            self._qty_done.setFixedWidth(72)
            qty_row.addWidget(self._qty_done)
        else:
            self._qty_done = None
        qty_row.addStretch()
        qty_w = QWidget()
        qty_w.setLayout(qty_row)
        grid.addWidget(qty_w, 3, 1)
        self._qty_chk.toggled.connect(self._on_qty_toggled)

        lay.addLayout(grid)

        # ── Advanced Options (collapsible) ────────────────────────────────────
        advanced = _CollapsibleSection("Advanced Options", collapsed=True)
        adv_lay = advanced.layout_body()

        # Use a grid so labels are fixed-width and controls stretch properly
        adv_grid = QGridLayout()
        adv_grid.setSpacing(10)
        adv_grid.setColumnMinimumWidth(0, 160)
        adv_grid.setColumnStretch(1, 1)

        # Priority
        adv_grid.addWidget(QLabel("Priority"), 0, 0)
        self._priority = QComboBox()
        for p in ProjectPriority.ALL:
            self._priority.addItem(ProjectPriority.LABELS[p], p)
        idx = self._priority.findData(ProjectPriority.MEDIUM)
        if idx >= 0:
            self._priority.setCurrentIndex(idx)
        adv_grid.addWidget(self._priority, 0, 1)

        # Estimated effort
        adv_grid.addWidget(QLabel("Estimated effort (minutes)"), 1, 0)
        self._effort = QSpinBox()
        self._effort.setRange(0, 9999)
        self._effort.setValue(0)
        self._effort.setSpecialValueText("—")
        self._effort.setMaximumWidth(100)
        adv_grid.addWidget(self._effort, 1, 1)

        # Linked note
        adv_grid.addWidget(QLabel("Linked note"), 2, 0)
        self._note_combo = QComboBox()
        self._note_combo.addItem("— None —", None)
        for n in self._notes:
            self._note_combo.addItem(n.title or f"Note {n.id}", n.id)
        adv_grid.addWidget(self._note_combo, 2, 1)

        adv_grid_w = QWidget()
        adv_grid_w.setLayout(adv_grid)
        adv_lay.addWidget(adv_grid_w)

        # Focus checkbox
        self._focus_chk = QCheckBox("Set as Current Focus")
        self._focus_chk.setToolTip("Mark this milestone as the active focus — shown on Overview")
        adv_lay.addWidget(self._focus_chk)

        # Completion notes (only in edit mode when completed)
        if is_edit and milestone.is_complete:
            adv_lay.addWidget(QLabel("Completion notes"))
            self._completion_notes = QTextEdit()
            self._completion_notes.setFixedHeight(56)
            self._completion_notes.setPlaceholderText("What did you do to complete this?")
            adv_lay.addWidget(self._completion_notes)
        else:
            self._completion_notes = None

        lay.addWidget(advanced)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # Populate if editing
        if is_edit:
            self._title.setText(milestone.title or "")
            self._desc.setPlainText(milestone.description or "")
            self._date.setText(milestone.due_date or "")
            pri_idx = self._priority.findData(getattr(milestone, "priority", ProjectPriority.MEDIUM))
            if pri_idx >= 0:
                self._priority.setCurrentIndex(pri_idx)
            self._effort.setValue(getattr(milestone, "estimated_effort_minutes", 0) or 0)
            note_idx = self._note_combo.findData(getattr(milestone, "linked_note_id", None))
            if note_idx >= 0:
                self._note_combo.setCurrentIndex(note_idx)
            self._focus_chk.setChecked(getattr(milestone, "is_focus", False))
            if self._completion_notes:
                self._completion_notes.setPlainText(getattr(milestone, "completion_notes", "") or "")
            # Quantity
            qt = getattr(milestone, "quantity_total", 0) or 0
            if qt > 0:
                self._qty_chk.setChecked(True)
                self._qty_total.setValue(qt)
                if self._qty_done is not None:
                    self._qty_done.setValue(getattr(milestone, "quantity_done", 0) or 0)

    def _on_qty_toggled(self, checked: bool):
        self._qty_total.setEnabled(checked)
        if self._qty_done is not None:
            self._qty_done.setEnabled(checked)

    def _on_accept(self):
        if not self._title.text().strip():
            QMessageBox.warning(self, "Required", "Milestone title is required.")
            return
        self.accept()

    def get_values(self) -> dict:
        use_qty = self._qty_chk.isChecked()
        d = {
            "title":                    self._title.text().strip(),
            "description":              self._desc.toPlainText().strip(),
            "due_date":                 self._date.text().strip() or None,
            "priority":                 self._priority.currentData(),
            "estimated_effort_minutes": self._effort.value(),
            "linked_note_id":           self._note_combo.currentData(),
            "is_focus":                 self._focus_chk.isChecked(),
            "quantity_total":           self._qty_total.value() if use_qty else 0,
            "quantity_done":            (self._qty_done.value() if self._qty_done is not None else 0) if use_qty else 0,
        }
        if self._completion_notes is not None:
            d["completion_notes"] = self._completion_notes.toPlainText().strip()
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Notes tab
# ─────────────────────────────────────────────────────────────────────────────

class NotesTab(QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx        = context
        self._project_id: Optional[int] = None
        self._notes:      list[ProjectNote] = []
        self._active_note: Optional[ProjectNote] = None
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left: note list
        left = QWidget()
        left.setObjectName("notesListPanel")
        left.setFixedWidth(260)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(8, 8, 8, 8)
        left_lay.setSpacing(6)

        tb = QHBoxLayout()
        tb.addWidget(QLabel("Notes"))
        tb.addStretch()
        add_btn = QPushButton("＋")
        add_btn.setObjectName("iconBtn")
        add_btn.setFixedSize(26, 26)
        add_btn.clicked.connect(self._new_note)
        tb.addWidget(add_btn)
        left_lay.addLayout(tb)

        self._note_list_lay = QVBoxLayout()
        self._note_list_lay.setSpacing(4)
        left_lay.addLayout(self._note_list_lay)
        left_lay.addStretch()
        root.addWidget(left)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setObjectName("divider")
        root.addWidget(div)

        # Right: editor
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(16, 12, 16, 12)
        right_lay.setSpacing(8)

        self._note_title_edit = QLineEdit()
        self._note_title_edit.setObjectName("noteTitleEdit")
        self._note_title_edit.setPlaceholderText("Note title…")
        self._note_title_edit.setFixedHeight(34)
        right_lay.addWidget(self._note_title_edit)

        self._note_body_edit = QTextEdit()
        self._note_body_edit.setObjectName("noteBodyEdit")
        self._note_body_edit.setPlaceholderText("Start writing…")
        right_lay.addWidget(self._note_body_edit, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._save_note_btn = QPushButton("Save Note")
        self._save_note_btn.setObjectName("primaryBtn")
        self._save_note_btn.clicked.connect(self._save_note)
        btn_row.addWidget(self._save_note_btn)
        self._del_note_btn = QPushButton("Delete")
        self._del_note_btn.setObjectName("dangerBtn")
        self._del_note_btn.clicked.connect(self._delete_note)
        self._del_note_btn.setVisible(False)
        btn_row.addWidget(self._del_note_btn)
        right_lay.addLayout(btn_row)
        root.addWidget(right, stretch=1)

        self._note_title_edit.setEnabled(False)
        self._note_body_edit.setEnabled(False)
        self._save_note_btn.setEnabled(False)

    def load(self, project_id: int, notes: list[ProjectNote]):
        self._project_id = project_id
        self._notes      = notes
        self._render_list()

    def _render_list(self):
        while self._note_list_lay.count():
            item = self._note_list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Panel is now 260 px; subtract 20 px for left+right button padding (10px each).
        # Use app-level font metrics — the widget may not be shown yet.
        _fm = QFontMetrics(QApplication.font())
        for note in self._notes:
            title = note.title or "Untitled"
            btn = QPushButton()
            btn.setObjectName("noteListItem")
            btn.setFlat(True)
            btn.setToolTip(title)
            btn.setText(_fm.elidedText(title, Qt.ElideRight, 240))
            btn.clicked.connect(lambda _, n=note: self._open_note(n))
            self._note_list_lay.addWidget(btn)

    def open_note(self, note: ProjectNote):
        """Public: select a specific note and open it in the editor."""
        self._open_note(note)

    def _open_note(self, note: ProjectNote):
        self._active_note = note
        self._note_title_edit.setText(note.title or "")
        self._note_body_edit.setPlainText(note.content or "")
        self._note_title_edit.setEnabled(True)
        self._note_body_edit.setEnabled(True)
        self._save_note_btn.setEnabled(True)
        self._del_note_btn.setVisible(True)

    def _new_note(self):
        if not self._project_id:
            return
        self._active_note = None
        self._note_title_edit.clear()
        self._note_body_edit.clear()
        self._note_title_edit.setEnabled(True)
        self._note_body_edit.setEnabled(True)
        self._save_note_btn.setEnabled(True)
        self._del_note_btn.setVisible(False)
        self._note_title_edit.setFocus()

    def _save_note(self):
        if not self._project_id:
            return
        title   = self._note_title_edit.text().strip()
        content = self._note_body_edit.toPlainText().strip()
        if self._active_note:
            self._ctx.event_bus.emit("project_note_update", {
                "id": self._active_note.id, "title": title, "content": content
            })
        else:
            self._ctx.event_bus.emit("project_note_add", {
                "project_id": self._project_id, "title": title, "content": content
            })

    def _delete_note(self):
        if self._active_note:
            self._ctx.event_bus.emit("project_note_delete",
                                     {"id": self._active_note.id})


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Entity picker dialog  (used by LinksTab)
# ─────────────────────────────────────────────────────────────────────────────

def _entity_badge(et: str, obj) -> tuple[str, str]:
    """
    Return (badge_text, badge_hex_color) for a linked entity's status pill.
    Empty strings mean no badge is shown.
    """
    if et == "paint":
        qty   = getattr(obj, "quantity", 1) or 0
        level = (getattr(obj, "level", "") or "").lower()
        if qty == 0:
            return "Out of Stock", "#c62828"
        if level in ("empty", "low", "almost empty"):
            return "Low",         "#e07820"
        return "", ""

    if et == "model":
        status = (getattr(obj, "status", "") or "").lower()
        _MAP = {
            "painted":     ("Painted",    "#2e7d32"),
            "based":       ("Based",      "#2e7d32"),
            "primed":      ("Primed",     "#e07820"),
            "assembled":   ("Assembled",  "#0078d4"),
            "wip":         ("WIP",        "#e07820"),
            "unassembled": ("Unassembled","#606060"),
        }
        return _MAP.get(status, ("", ""))

    if et == "campaign":
        status = (getattr(obj, "status", "") or "").lower()
        _MAP = {
            "active":    ("Active",    "#2e7d32"),
            "completed": ("Completed", "#0078d4"),
            "paused":    ("Paused",    "#e07820"),
            "archived":  ("Archived",  "#606060"),
        }
        return _MAP.get(status, ("", ""))

    if et == "event":
        if getattr(obj, "completed", False):
            return "Done", "#2e7d32"
        return "", ""

    if et == "army":
        pts_limit = getattr(obj, "points_limit", 0) or 0
        if pts_limit > 0:
            return f"{pts_limit:,} pts", "#606060"
        return "", ""

    return "", ""


# Maps entity type → (service_name, fetch_method, display_fn)
# display_fn(obj) → (primary_text, secondary_text)
_ENTITY_SERVICE_MAP: dict[str, tuple[str, str]] = {
    "model":    ("model_service",    "get_all_models"),
    "paint":    ("paint_service",    "get_all_paints"),
    "army":     ("army_service",     "get_all_armies"),
    "campaign": ("campaign_service", "get_all_campaigns"),
    "event":    ("calendar_service", "get_upcoming"),
    "scheme":   ("scheme_service",   "get_all_schemes"),
}

# Entity type → plugin_id for dashboard_navigate
_ENTITY_PLUGIN_MAP: dict[str, str] = {
    "model":    "model_tracker",
    "paint":    "paint_tracker",
    "army":     "army_builder",
    "campaign": "campaign_tracker",
    "event":    "calendar",
    "scheme":   "paint_scheme",
}


def _entity_display(et: str, obj) -> tuple[str, str]:
    """Return (primary, secondary) display strings for any entity object."""
    primary = (
        getattr(obj, "name",  None) or
        getattr(obj, "title", None) or
        str(obj)
    )
    if et == "paint":
        secondary = getattr(obj, "brand", "") or ""
    elif et in ("model", "army"):
        parts = []
        gs = getattr(obj, "game_system", None)
        fa = getattr(obj, "faction",     None)
        if gs: parts.append(gs)
        if fa: parts.append(fa)
        secondary = "  ·  ".join(parts)
    elif et == "campaign":
        secondary = getattr(obj, "game_system", "") or ""
    elif et == "event":
        secondary = getattr(obj, "event_date", "") or getattr(obj, "date", "") or ""
    elif et == "scheme":
        parts = [x for x in [getattr(obj, "faction", ""), getattr(obj, "game_system", "")] if x]
        secondary = "  ·  ".join(parts)
    else:
        secondary = ""
    return primary, secondary


class EntityPickerDialog(QDialog):
    """
    Modal dialog that lists all available items of one entity type and lets
    the user pick one or more to link to the current project.
    Already-linked items are pre-checked / shown with a note.
    """

    def __init__(self, context, entity_type: str,
                 already_linked_ids: set[int], parent=None):
        super().__init__(parent)
        self._ctx        = context
        self._et         = entity_type
        self._linked_ids = already_linked_ids
        self._checks: list[tuple[QCheckBox, int]] = []  # (checkbox, obj_id)

        label = EntityType.LABELS.get(entity_type, entity_type)
        icon  = EntityType.ICONS.get(entity_type, "")
        self.setWindowTitle(f"Link {icon} {label}")
        self.setMinimumSize(440, 400)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(16, 16, 16, 16)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.textChanged.connect(self._filter)
        root.addWidget(self._search)

        # Scrollable item list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._list_widget = QWidget()
        self._list_lay    = QVBoxLayout(self._list_widget)
        self._list_lay.setContentsMargins(4, 4, 4, 4)
        self._list_lay.setSpacing(2)
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, stretch=1)

        # Status label
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("dimLabel")
        root.addWidget(self._status_lbl)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._populate()

    def _fetch_items(self) -> list:
        info = _ENTITY_SERVICE_MAP.get(self._et)
        if not info:
            return []
        svc_name, method_name = info
        svc = self._ctx.services.try_get(svc_name)
        if not svc:
            return []
        try:
            fn = getattr(svc, method_name)
            # calendar get_upcoming accepts an optional days arg
            if self._et == "event":
                return fn(days=365)
            return fn()
        except Exception as e:
            print(f"[LINKS PICKER] fetch {self._et}: {e}")
            return []

    def _populate(self):
        items = self._fetch_items()
        if not items:
            lbl = QLabel("No items found — add some in the relevant plugin first.")
            lbl.setObjectName("dimLabel")
            lbl.setWordWrap(True)
            self._list_lay.addWidget(lbl)
            self._status_lbl.setText("0 items available")
            return

        for obj in items:
            obj_id   = getattr(obj, "id", None)
            if obj_id is None:
                continue
            primary, secondary = _entity_display(self._et, obj)
            already = obj_id in self._linked_ids

            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(4, 2, 4, 2)
            row_lay.setSpacing(8)

            cb = QCheckBox()
            cb.setChecked(already)
            row_lay.addWidget(cb)

            text_w = QWidget()
            text_l = QVBoxLayout(text_w)
            text_l.setContentsMargins(0, 0, 0, 0)
            text_l.setSpacing(0)

            name_lbl = QLabel(primary)
            name_lbl.setObjectName("linkItemLabel")
            text_l.addWidget(name_lbl)
            if secondary:
                sub_lbl = QLabel(secondary)
                sub_lbl.setObjectName("dimLabel")
                text_l.addWidget(sub_lbl)

            row_lay.addWidget(text_w, stretch=1)

            if already:
                tag = QLabel("linked")
                tag.setObjectName("statusBadge")
                tag.setProperty("status", "active")
                row_lay.addWidget(tag)

            self._list_lay.addWidget(row)
            self._checks.append((cb, obj_id))

        self._list_lay.addStretch()
        self._status_lbl.setText(f"{len(items)} item{'s' if len(items) != 1 else ''} available")

    def _filter(self, text: str):
        text = text.lower()
        for i in range(self._list_lay.count() - 1):  # skip stretch
            item = self._list_lay.itemAt(i)
            if not item:
                continue
            w = item.widget()
            if not w:
                continue
            # Search within all child label text
            all_text = " ".join(
                lbl.text().lower()
                for lbl in w.findChildren(QLabel)
            )
            w.setVisible(text in all_text)

    def get_selected_ids(self) -> list[int]:
        """Return IDs of all checked items (including pre-checked ones)."""
        return [oid for cb, oid in self._checks if cb.isChecked()]

    def get_newly_selected_ids(self) -> list[int]:
        """IDs that are checked AND were not already linked."""
        return [oid for cb, oid in self._checks
                if cb.isChecked() and oid not in self._linked_ids]

    def get_deselected_ids(self) -> list[int]:
        """IDs that were linked but are now unchecked (to unlink)."""
        return [oid for cb, oid in self._checks
                if not cb.isChecked() and oid in self._linked_ids]


# ─────────────────────────────────────────────────────────────────────────────
# Links tab
# ─────────────────────────────────────────────────────────────────────────────

class LinksTab(QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx        = context
        self._project_id: Optional[int] = None
        self._linked_ids: dict[str, set[int]] = {}   # et → set of linked obj ids
        self._build()

    # entity type → enabled_system key (None = always show)
    _ET_SYSTEM_MAP: dict[str, str | None] = {
        EntityType.MODEL:    EnabledSystem.MODELS,
        EntityType.PAINT:    EnabledSystem.PAINTS,
        EntityType.ARMY:     EnabledSystem.ARMIES,
        EntityType.CAMPAIGN: None,
        EntityType.EVENT:    None,
        EntityType.SCHEME:   None,
        EntityType.PURCHASE: None,
    }

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 12, 16, 12)
        body_lay.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll)

        # One block per entity type — each block is a single QWidget so we can
        # show/hide the whole header + items + divider in one call.
        self._sections:       dict[str, QVBoxLayout] = {}   # et → items layout
        self._section_blocks: dict[str, QWidget]     = {}   # et → outer block widget

        for et in EntityType.ALL:
            icon  = EntityType.ICONS[et]
            label = EntityType.LABELS[et]

            # Outer block wraps header + items + divider
            block = QWidget()
            block_lay = QVBoxLayout(block)
            block_lay.setContentsMargins(0, 0, 0, 0)
            block_lay.setSpacing(6)

            # Header row: icon + label + Add button
            hdr = QWidget()
            hdr_lay = QHBoxLayout(hdr)
            hdr_lay.setContentsMargins(0, 0, 0, 0)
            hdr_lay.setSpacing(8)

            hdr_lbl = QLabel(f"{icon}  {label}")
            hdr_lbl.setObjectName("sectionLabel")
            hdr_lay.addWidget(hdr_lbl, stretch=1)

            has_service = et in _ENTITY_SERVICE_MAP
            add_btn = QPushButton(f"＋ Add {label}")
            add_btn.setObjectName("iconBtn")
            add_btn.setEnabled(has_service)
            add_btn.setToolTip(
                f"Pick {label.lower()} to link to this project"
                if has_service else
                f"No {label.lower()} service available"
            )
            add_btn.clicked.connect(lambda _, e=et: self._open_picker(e))
            hdr_lay.addWidget(add_btn)
            block_lay.addWidget(hdr)

            # Items container
            container = QWidget()
            container_lay = QVBoxLayout(container)
            container_lay.setContentsMargins(8, 2, 8, 2)
            container_lay.setSpacing(3)
            self._sections[et] = container_lay
            block_lay.addWidget(container)
            block_lay.addWidget(_hline())

            body_lay.addWidget(block)
            self._section_blocks[et] = block

        body_lay.addStretch()

    # ── Public ────────────────────────────────────────────────────────────────

    def load(self, project_id: int, linked_entities: dict[str, list],
             enabled_systems: list | None = None):
        self._project_id = project_id

        # Determine which entity type sections are visible
        # enabled_systems=None or [] → all visible (backward compat)
        enabled = enabled_systems or []

        def _section_visible(et: str) -> bool:
            sys_key = self._ET_SYSTEM_MAP.get(et)
            if sys_key is None:
                return True       # no governing system → always show
            return not enabled or sys_key in enabled

        # Show/hide blocks and populate items
        for et, block in self._section_blocks.items():
            visible = _section_visible(et)
            block.setVisible(visible)

        # Cache linked IDs for the picker
        self._linked_ids = {
            et: {getattr(obj, "id", -1) for obj in objs}
            for et, objs in linked_entities.items()
        }

        for et, lay in self._sections.items():
            _clear_layout(lay)

            items = linked_entities.get(et, [])
            if not items:
                empty = QLabel("Nothing linked yet.")
                empty.setObjectName("dimLabel")
                lay.addWidget(empty)
                continue

            for obj in items:
                row = self._make_item_row(et, obj)
                lay.addWidget(row)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _open_picker(self, entity_type: str):
        if not self._project_id:
            return
        already = self._linked_ids.get(entity_type, set())
        dlg = EntityPickerDialog(self._ctx, entity_type, already, self)
        if not dlg.exec():
            return

        bus = self._ctx.event_bus
        pid = self._project_id

        for oid in dlg.get_newly_selected_ids():
            bus.emit("project_link_entity", {
                "project_id":  pid,
                "entity_type": entity_type,
                "entity_id":   oid,
                "notes":       "",
            })

        for oid in dlg.get_deselected_ids():
            bus.emit("project_unlink_entity", {
                "project_id":  pid,
                "entity_type": entity_type,
                "entity_id":   oid,
            })

    # Entity types that map directly to a requirement item type
    _ET_TO_REQ_TYPE: dict[str, str] = {
        EntityType.PAINT: ReqItemType.PAINT,
        EntityType.MODEL: ReqItemType.MODEL,
    }

    def _make_item_row(self, entity_type: str, obj) -> QWidget:
        """Build a LinkedEntityChip for a linked entity — with status badge + navigation."""
        primary, secondary = _entity_display(entity_type, obj)
        obj_id = getattr(obj, "id", 0)

        # ── Status badge ──────────────────────────────────────────────────────
        badge_text, badge_color = _entity_badge(entity_type, obj)

        # ── Dot color (paints get their swatch color) ─────────────────────────
        dot_color = ""
        if entity_type == "paint":
            dot_color = getattr(obj, "color", "") or ""

        chip = LinkedEntityChip(
            plugin_id    = _ENTITY_PLUGIN_MAP.get(entity_type, ""),
            entity_id    = obj_id,
            icon         = EntityType.ICONS.get(entity_type, ""),
            name         = primary,
            subtitle     = secondary,
            dot_color    = dot_color,
            badge_text   = badge_text,
            badge_color  = badge_color,
            show_navigate= bool(_ENTITY_PLUGIN_MAP.get(entity_type)),
            show_unlink  = True,
        )
        # Navigate → switch main window to target plugin
        chip.navigate_requested.connect(
            lambda pid, _eid: self._ctx.event_bus.emit(
                "dashboard_navigate", {"plugin_id": pid}
            )
        )
        # Unlink ✕ → remove the project link
        pid = self._project_id
        chip.unlink_requested.connect(
            lambda eid, _et=entity_type, _pid=pid:
                self._ctx.event_bus.emit("project_unlink_entity", {
                    "project_id":  _pid,
                    "entity_type": _et,
                    "entity_id":   eid,
                })
        )

        # ── "Add as Requirement" button for paint / model ─────────────────────
        req_type = self._ET_TO_REQ_TYPE.get(entity_type)
        if req_type:
            wrapper = QFrame()
            wrapper.setObjectName("chipWrapper")
            wrapper.setStyleSheet("QFrame#chipWrapper { background: transparent; }")
            w_lay = QHBoxLayout(wrapper)
            w_lay.setContentsMargins(0, 0, 0, 0)
            w_lay.setSpacing(4)
            w_lay.addWidget(chip, stretch=1)

            req_btn = QPushButton("📋")
            req_btn.setObjectName("iconBtn")
            req_btn.setFixedSize(26, 26)
            req_btn.setToolTip("Add as project requirement")
            req_btn.clicked.connect(
                lambda _, _rt=req_type, _name=primary, _oid=obj_id, _pid=pid:
                    self._ctx.event_bus.emit("project_requirement_add", {
                        "project_id":      _pid,
                        "item_type":       _rt,
                        "item_name":       _name,
                        "item_id":         _oid,
                        "quantity_needed": 1,
                        "notes":           "",
                    })
            )
            w_lay.addWidget(req_btn)
            return wrapper

        return chip


def _clear_layout(lay: QVBoxLayout):
    while lay.count():
        item = lay.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# Sessions tab
# ─────────────────────────────────────────────────────────────────────────────

_SESSION_PRESETS = [15, 30, 45, 60, 90, 120]


class SessionsTab(QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx           = context
        self._project_id:   Optional[int] = None
        self._sessions:     list[HobbySession] = []
        self._milestones:   list = []
        self._active_session: Optional[HobbySession] = None
        self._live_timer:   Optional[QTimer] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # ── Top action bar — Start button always visible here ─────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self._start_btn = QPushButton("▶  Start Live Session")
        self._start_btn.setObjectName("secondaryBtn")
        self._start_btn.setFixedHeight(32)
        self._start_btn.clicked.connect(self._start_live_session)
        top_bar.addWidget(self._start_btn)
        top_bar.addStretch()
        root.addLayout(top_bar)

        # ── Live Session Banner (replaces start btn when a session is running) ─
        self._live_banner = QFrame()
        self._live_banner.setObjectName("liveSessionBanner")
        live_lay = QHBoxLayout(self._live_banner)
        live_lay.setContentsMargins(14, 10, 14, 10)
        live_lay.setSpacing(12)

        self._live_icon = QLabel("🔴")
        live_lay.addWidget(self._live_icon)
        self._live_elapsed_lbl = QLabel("Session in progress…")
        self._live_elapsed_lbl.setObjectName("liveSessionLabel")
        live_lay.addWidget(self._live_elapsed_lbl, stretch=1)

        self._end_session_btn = QPushButton("⏹  End Session")
        self._end_session_btn.setObjectName("dangerBtn")
        self._end_session_btn.setFixedHeight(30)
        self._end_session_btn.clicked.connect(self._end_live_session)
        live_lay.addWidget(self._end_session_btn)

        root.addWidget(self._live_banner)
        self._live_banner.hide()

        # ── Log Manual Session ────────────────────────────────────────────────
        form_card = QFrame()
        form_card.setObjectName("formCard")
        form_vlay = QVBoxLayout(form_card)
        form_vlay.setContentsMargins(14, 12, 14, 12)
        form_vlay.setSpacing(8)

        # Quick preset chips row
        presets_lbl = QLabel("Quick duration:")
        presets_lbl.setObjectName("dimLabel")
        form_vlay.addWidget(presets_lbl)

        self._preset_btns: dict[int, QPushButton] = {}
        presets_row = QHBoxLayout()
        presets_row.setSpacing(6)
        for mins in _SESSION_PRESETS:
            btn = QPushButton(f"{mins}m")
            btn.setObjectName("presetChip")
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _, m=mins: self._set_preset(m))
            presets_row.addWidget(btn)
            self._preset_btns[mins] = btn
        presets_row.addStretch()
        form_vlay.addLayout(presets_row)

        # Duration + milestone row
        dur_row = QHBoxLayout()
        dur_row.setSpacing(10)
        dur_row.addWidget(QLabel("Duration (min)"))
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 9999)
        self._duration_spin.setValue(60)
        self._duration_spin.setFixedWidth(80)
        self._duration_spin.valueChanged.connect(self._on_duration_changed)
        dur_row.addWidget(self._duration_spin)
        dur_row.addSpacing(12)
        dur_row.addWidget(QLabel("Milestone"))
        self._ms_combo = QComboBox()
        self._ms_combo.addItem("— None —", None)
        dur_row.addWidget(self._ms_combo, stretch=1)
        form_vlay.addLayout(dur_row)

        # Notes
        form_vlay.addWidget(QLabel("Notes"))
        self._session_notes = QLineEdit()
        self._session_notes.setPlaceholderText("What did you work on?")
        form_vlay.addWidget(self._session_notes)

        # Outcome + Next Action (collapsible)
        adv = _CollapsibleSection("Outcome & Next Steps", collapsed=True)
        adv_lay = adv.layout_body()

        adv_lay.addWidget(QLabel("Outcome"))
        self._outcome_edit = QLineEdit()
        self._outcome_edit.setPlaceholderText("What did you achieve?")
        adv_lay.addWidget(self._outcome_edit)

        adv_lay.addWidget(QLabel("Next Action"))
        self._next_action_edit = QLineEdit()
        self._next_action_edit.setPlaceholderText("What's the next step?")
        adv_lay.addWidget(self._next_action_edit)

        form_vlay.addWidget(adv)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        log_btn = QPushButton("Log Session")
        log_btn.setObjectName("primaryBtn")
        log_btn.setFixedHeight(32)
        log_btn.clicked.connect(self._log_session)
        btn_row.addWidget(log_btn)
        form_vlay.addLayout(btn_row)

        root.addWidget(form_card)
        root.addWidget(_hline())
        root.addWidget(_section_lbl("SESSION HISTORY"))

        # Session list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._session_list = QWidget()
        self._session_list_lay = QVBoxLayout(self._session_list)
        self._session_list_lay.setContentsMargins(0, 0, 0, 0)
        self._session_list_lay.setSpacing(4)
        self._session_list_lay.addStretch()
        scroll.setWidget(self._session_list)
        root.addWidget(scroll, stretch=1)

    def _on_duration_changed(self, val: int):
        """Highlight the matching preset chip; clear all others."""
        for mins, btn in self._preset_btns.items():
            btn.setChecked(mins == val)

    def _set_preset(self, minutes: int):
        """Set the duration spinner; _on_duration_changed fires via valueChanged."""
        self._duration_spin.setValue(minutes)

    def load(self, project_id: int, sessions: list[HobbySession],
             milestones: list = None):
        self._project_id = project_id
        self._sessions   = sessions
        self._milestones = milestones or []
        self._active_session = next((s for s in sessions if getattr(s, "is_active", False)), None)

        # Rebuild milestone combo
        self._ms_combo.clear()
        self._ms_combo.addItem("— None —", None)
        for m in self._milestones:
            prefix = "✅ " if m.is_complete else "○ "
            self._ms_combo.addItem(prefix + m.title, m.id)

        # Show/hide live banner
        self._update_live_banner()
        self._render()

    def _update_live_banner(self):
        has_active = self._active_session is not None
        self._live_banner.setVisible(has_active)
        # Hide start button while a session is running — the banner's End button
        # takes its place at the top of the tab.
        self._start_btn.setVisible(not has_active)
        if has_active and self._active_session:
            self._update_elapsed()
            if not self._live_timer:
                self._live_timer = QTimer(self)
                self._live_timer.timeout.connect(self._update_elapsed)
            self._live_timer.start(30_000)  # update every 30 s
        else:
            if self._live_timer:
                self._live_timer.stop()

    def _update_elapsed(self):
        sess = self._active_session
        if not sess:
            return
        try:
            from datetime import datetime as _dt, timezone as _tz
            start_str = sess.actual_start_time or sess.started_at
            if start_str:
                start_dt = _dt.fromisoformat(start_str.replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=_tz.utc)
                elapsed_s = int((_dt.now(_tz.utc) - start_dt).total_seconds())
                elapsed_m = elapsed_s // 60
                elapsed_h = elapsed_m // 60
                elapsed_m_rem = elapsed_m % 60
                dur_str = f"{elapsed_h}h {elapsed_m_rem}m" if elapsed_h else f"{elapsed_m_rem}m"
                self._live_elapsed_lbl.setText(f"Live session running — {dur_str}")
                return
        except Exception:
            pass
        self._live_elapsed_lbl.setText("Live session in progress…")

    def _start_live_session(self):
        if not self._project_id:
            return
        ms_id = self._ms_combo.currentData()
        self._ctx.event_bus.emit("project_session_start", {
            "project_id":          self._project_id,
            "linked_milestone_id": ms_id,
        })

    def _end_live_session(self):
        if not self._project_id:
            return

        from PySide6.QtGui import QGuiApplication
        dlg = _EndSessionDialog(self)
        screen = self.screen() if self.isVisible() else QGuiApplication.primaryScreen()
        if screen:
            ag = screen.availableGeometry()
            dlg.adjustSize()
            dlg.move(ag.center().x() - dlg.width() // 2,
                     ag.center().y() - dlg.height() // 2)

        if dlg.exec() != QDialog.Accepted:
            return  # user cancelled — session keeps running

        notes, outcome, next_action = dlg.values()

        self._ctx.event_bus.emit("project_session_end", {
            "project_id": self._project_id,
            "notes":       notes,
            "outcome":     outcome,
            "next_action": next_action,
        })

        # If they wrote a next action, offer to drop it in the calendar
        if next_action:
            QTimer.singleShot(0, lambda na=next_action: self._offer_calendar_event(na))

    def _offer_calendar_event(self, next_action: str):
        from PySide6.QtGui import QGuiApplication
        dlg = _CalendarEventOfferDialog(next_action, self)
        screen = self.screen() if self.isVisible() else QGuiApplication.primaryScreen()
        if screen:
            ag = screen.availableGeometry()
            dlg.adjustSize()
            dlg.move(ag.center().x() - dlg.width() // 2,
                     ag.center().y() - dlg.height() // 2)
        if dlg.exec() != QDialog.Accepted:
            return
        date_str, undetermined = dlg.result_data()
        cal = self._ctx.services.try_get("calendar_service")
        if cal is None:
            return
        try:
            # Resolve project name for calendar linking
            project_name = ""
            try:
                svc = self._ctx.services.try_get("project_service")
                if svc and self._project_id:
                    p = svc.get_project(self._project_id)
                    project_name = p.name if p else ""
            except Exception:
                pass

            cal.add_event(
                title          = f"Next: {next_action}",
                event_date     = "" if undetermined else date_str,
                notes          = f"Next action from project session{': ' + project_name if project_name else ''}.",
                linked_plugin  = "project_tracker",
                linked_id      = str(self._project_id or ""),
                linked_name    = project_name,
                source_event   = "project_session_next_action",
            )
        except Exception:
            pass

    def _render(self):
        while self._session_list_lay.count() > 1:
            item = self._session_list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        visible = [s for s in self._sessions if not getattr(s, "is_active", False)]

        if not visible:
            empty = QLabel(
                "No sessions logged yet.\n\n"
                "Use the form above to log a manual session,\n"
                "or click  ▶ Start Live Session  to begin timing now."
            )
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self._session_list_lay.insertWidget(0, empty)
            return

        total = sum(s.duration_minutes for s in visible)
        summary = QLabel(
            f"Total: {len(visible)} session{'s' if len(visible)!=1 else ''}  ·  "
            f"{round(total/60,1)} hours"
        )
        summary.setObjectName("sessionSummary")
        self._session_list_lay.insertWidget(0, summary)

        for s in visible:
            row = self._make_session_row(s)
            self._session_list_lay.insertWidget(
                self._session_list_lay.count() - 1, row
            )

    def _make_session_row(self, s: HobbySession) -> QFrame:
        row = QFrame()
        row.setObjectName("sessionRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(12)

        hours = s.duration_minutes // 60
        mins  = s.duration_minutes % 60
        dur   = f"{hours}h {mins}m" if hours else f"{mins}m"
        date  = (s.started_at or "")[:10]

        col = QVBoxLayout()
        col.setSpacing(1)
        lbl = QLabel(f"{date}  —  {dur}")
        lbl.setObjectName("sessionLabel")
        col.addWidget(lbl)

        notes_text = s.notes or ""
        outcome = getattr(s, "outcome", "") or ""
        next_act = getattr(s, "next_action", "") or ""
        if notes_text:
            notes_lbl = QLabel(notes_text)
            notes_lbl.setObjectName("dimLabel")
            col.addWidget(notes_lbl)
        if outcome:
            out_lbl = QLabel(f"✓  {outcome}")
            out_lbl.setObjectName("dimLabel")
            col.addWidget(out_lbl)
        if next_act:
            next_lbl = QLabel(f"→  {next_act}")
            next_lbl.setObjectName("dimLabel")
            col.addWidget(next_lbl)

        lay.addLayout(col, stretch=1)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("iconBtn")
        del_btn.setFixedSize(22, 22)
        del_btn.clicked.connect(
            lambda _, sid=s.id:
                self._ctx.event_bus.emit("project_session_delete", {"id": sid})
        )
        lay.addWidget(del_btn)
        return row

    def _log_session(self):
        if not self._project_id:
            return
        self._ctx.event_bus.emit("project_session_log", {
            "project_id":          self._project_id,
            "duration_minutes":    self._duration_spin.value(),
            "notes":               self._session_notes.text().strip(),
            "outcome":             self._outcome_edit.text().strip(),
            "next_action":         self._next_action_edit.text().strip(),
            "linked_milestone_id": self._ms_combo.currentData(),
        })
        self._session_notes.clear()
        self._outcome_edit.clear()
        self._next_action_edit.clear()
        self._duration_spin.setValue(60)


# ─────────────────────────────────────────────────────────────────────────────
# Gallery helpers
# ─────────────────────────────────────────────────────────────────────────────
# Requirements Tab
# ─────────────────────────────────────────────────────────────────────────────

_REQ_STATUS_STYLE = {
    ReqStatus.OK:          ("✅", "#2e7d32", "In Stock"),
    ReqStatus.LOW:         ("⚠️", "#e07820", "Low Stock"),
    ReqStatus.MISSING:     ("❌", "#c62828", "Missing"),
    ReqStatus.OK_OVERRIDE: ("👍", "#0078d4", "Marked OK"),
    ReqStatus.UNKNOWN:     ("❓", "#606060", "Unknown"),
}


class RequirementsTab(QWidget):
    """Tab showing what items are needed to start the project and their stock status."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self._ctx        = ctx
        self._project_id: int | None = None
        self._reqs:       list       = []
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Status banner
        self._banner = QFrame()
        self._banner.setObjectName("reqBanner")
        banner_lay = QHBoxLayout(self._banner)
        banner_lay.setContentsMargins(14, 10, 14, 10)
        self._banner_icon  = QLabel("✅")
        self._banner_icon.setStyleSheet("font-size: 20px;")
        self._banner_text  = QLabel("Ready to Start")
        self._banner_text.setStyleSheet("font-size: 14px; font-weight: 700;")
        self._banner_sub   = QLabel("")
        self._banner_sub.setStyleSheet("font-size: 11px; color: palette(mid-text);")
        banner_lay.addWidget(self._banner_icon)
        banner_lay.addSpacing(8)
        b_text_col = QVBoxLayout()
        b_text_col.setSpacing(1)
        b_text_col.addWidget(self._banner_text)
        b_text_col.addWidget(self._banner_sub)
        banner_lay.addLayout(b_text_col, stretch=1)
        root.addWidget(self._banner)

        # Requirements scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._list_widget = QWidget()
        self._list_lay    = QVBoxLayout(self._list_widget)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(6)
        self._list_lay.addStretch()
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, stretch=1)

        # Add button
        add_btn = QPushButton("＋  Add Requirement")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._on_add)
        root.addWidget(add_btn)

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self, project_id: int, reqs: list):
        self._project_id = project_id
        self._reqs       = reqs
        self._render()

    def _render(self):
        # Clear rows (keep the trailing stretch)
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._reqs:
            empty = QLabel("No requirements added yet.\nAdd paints, tools, models or materials needed to start.")
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self._list_lay.insertWidget(0, empty)
            self._update_banner([])
            return

        statuses = []
        svc = self._ctx.services.try_get("project_service")
        for req in self._reqs:
            status = ReqStatus.UNKNOWN
            if svc and hasattr(svc, "resolve_requirement_stock"):
                try:
                    status = svc.resolve_requirement_stock(req)
                except Exception:
                    pass
            statuses.append(status)
            row = self._make_row(req, status)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)

        self._update_banner(statuses)

    def _update_banner(self, statuses: list):
        missing = sum(1 for s in statuses if s == ReqStatus.MISSING)
        low     = sum(1 for s in statuses if s == ReqStatus.LOW)
        total   = len(statuses)

        if total == 0:
            self._banner_icon.setText("📋")
            self._banner_text.setText("No requirements set")
            self._banner_sub.setText("Add items below to track readiness.")
            self._banner.setStyleSheet(
                "QFrame#reqBanner { background: palette(mid); border-radius: 6px; }"
            )
        elif missing > 0:
            self._banner_icon.setText("❌")
            self._banner_text.setText("Not Ready — Items Missing")
            issues = []
            if missing: issues.append(f"{missing} missing")
            if low:     issues.append(f"{low} low stock")
            self._banner_sub.setText("  ·  ".join(issues))
            self._banner.setStyleSheet(
                "QFrame#reqBanner { background: rgba(198,40,40,0.15); "
                "border: 1px solid rgba(198,40,40,0.5); border-radius: 6px; }"
            )
        elif low > 0:
            self._banner_icon.setText("⚠️")
            self._banner_text.setText("Almost Ready — Low Stock")
            self._banner_sub.setText(f"{low} item{'s' if low>1 else ''} running low")
            self._banner.setStyleSheet(
                "QFrame#reqBanner { background: rgba(224,120,32,0.15); "
                "border: 1px solid rgba(224,120,32,0.5); border-radius: 6px; }"
            )
        else:
            self._banner_icon.setText("✅")
            self._banner_text.setText("Ready to Start!")
            self._banner_sub.setText(f"All {total} requirement{'s' if total>1 else ''} satisfied")
            self._banner.setStyleSheet(
                "QFrame#reqBanner { background: rgba(46,125,50,0.15); "
                "border: 1px solid rgba(46,125,50,0.5); border-radius: 6px; }"
            )

    def _make_row(self, req: ProjectRequirement, status: str) -> QFrame:
        icon_txt, color, label = _REQ_STATUS_STYLE.get(
            status, _REQ_STATUS_STYLE[ReqStatus.UNKNOWN]
        )
        row = QFrame()
        row.setObjectName("reqRow")
        row.setStyleSheet(
            f"QFrame#reqRow {{ border-left: 3px solid {color}; "
            f"background: palette(base); border-radius: 4px; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 8, 8, 8)
        lay.setSpacing(8)

        # Type icon
        type_icon = QLabel(ReqItemType.ICONS.get(req.item_type, "📦"))
        type_icon.setStyleSheet("font-size: 16px;")
        type_icon.setFixedWidth(22)
        lay.addWidget(type_icon)

        # Name + type label
        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        name_lbl = QLabel(req.item_name or "—")
        name_lbl.setStyleSheet("font-weight: 600;")
        type_lbl = QLabel(ReqItemType.LABELS.get(req.item_type, req.item_type))
        type_lbl.setStyleSheet("font-size: 10px; color: palette(mid-text);")
        name_col.addWidget(name_lbl)
        name_col.addWidget(type_lbl)
        lay.addLayout(name_col, stretch=1)

        # Quantity needed
        if req.quantity_needed > 1:
            qty_lbl = QLabel(f"×{req.quantity_needed}")
            qty_lbl.setStyleSheet("color: palette(mid-text); font-size: 11px;")
            lay.addWidget(qty_lbl)

        # Status badge
        badge = QLabel(f"{icon_txt} {label}")
        badge.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600; "
            f"background: transparent; padding: 2px 6px;"
        )
        lay.addWidget(badge)

        # Mark OK / Unmark button
        if status in (ReqStatus.LOW, ReqStatus.MISSING, ReqStatus.UNKNOWN):
            ok_btn = QPushButton("Mark OK")
            ok_btn.setObjectName("iconBtn")
            ok_btn.setFixedHeight(24)
            ok_btn.clicked.connect(lambda _, r=req: self._on_mark_ok(r))
            lay.addWidget(ok_btn)
        elif status == ReqStatus.OK_OVERRIDE:
            unmark_btn = QPushButton("Unmark")
            unmark_btn.setObjectName("iconBtn")
            unmark_btn.setFixedHeight(24)
            unmark_btn.clicked.connect(lambda _, r=req: self._on_unmark_ok(r))
            lay.addWidget(unmark_btn)

        # Remove button
        del_btn = QPushButton("✕")
        del_btn.setObjectName("iconBtn")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("Remove requirement")
        del_btn.clicked.connect(lambda _, r=req: self._on_remove(r))
        lay.addWidget(del_btn)

        return row

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_add(self):
        if not self._project_id:
            return
        svc = self._ctx.services.try_get("project_service")
        dlg = _AddRequirementDialog(svc, self)
        from PySide6.QtGui import QGuiApplication
        screen = self.screen() if self.isVisible() else QGuiApplication.primaryScreen()
        if screen:
            ag = screen.availableGeometry()
            dlg.adjustSize()
            dlg.move(ag.center().x() - dlg.width() // 2,
                     ag.center().y() - dlg.height() // 2)
        if dlg.exec() != QDialog.Accepted:
            return
        for values in dlg.all_values():
            self._ctx.event_bus.emit("project_requirement_add", {
                "project_id":      self._project_id,
                "item_type":       values["item_type"],
                "item_name":       values["item_name"],
                "item_id":         values["item_id"],
                "quantity_needed": values["quantity_needed"],
                "notes":           values["notes"],
            })

    def _on_remove(self, req: ProjectRequirement):
        self._ctx.event_bus.emit("project_requirement_delete", {"id": req.id})

    def _on_mark_ok(self, req: ProjectRequirement):
        self._ctx.event_bus.emit("project_requirement_update", {
            "id": req.id, "is_ok_override": True,
        })

    def _on_unmark_ok(self, req: ProjectRequirement):
        self._ctx.event_bus.emit("project_requirement_update", {
            "id": req.id, "is_ok_override": False,
        })


class _ReqItemRow(QWidget):
    """One row in the requirements picker: checkbox + optional swatch + item name + qty."""

    checked_changed = Signal(bool)

    def __init__(self, name: str, item_id, color: str = None, parent=None):
        super().__init__(parent)
        self._name    = name
        self._item_id = item_id

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)

        self._cb = QCheckBox()
        self._cb.toggled.connect(self._on_toggle)
        lay.addWidget(self._cb)

        # Paint color swatch — only shown when a hex color is supplied
        if color and color.startswith("#"):
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(
                f"background-color: {color}; border-radius: 3px;"
                f" border: 1px solid rgba(255,255,255,0.15);"
            )
            lay.addWidget(swatch)

        lbl = QLabel(name)
        lbl.setWordWrap(False)
        lay.addWidget(lbl, stretch=1)

        # Qty — QLineEdit with int validator avoids all platform spinbox quirks
        self._qty_lbl = QLabel("Qty:")
        self._qty_lbl.setStyleSheet("color: #888; font-size: 11px;")
        self._qty_lbl.setVisible(False)
        lay.addWidget(self._qty_lbl)

        self._qty = QLineEdit("1")
        self._qty.setValidator(QIntValidator(1, 9999))
        self._qty.setFixedWidth(48)
        self._qty.setFixedHeight(24)
        self._qty.setAlignment(Qt.AlignCenter)
        self._qty.setStyleSheet(
            "QLineEdit { padding: 1px 4px; min-height: 0; "
            "font-size: 11px; border-radius: 3px; }"
        )
        self._qty.setVisible(False)
        lay.addWidget(self._qty)

    def _on_toggle(self, checked: bool):
        self._qty_lbl.setVisible(checked)
        self._qty.setVisible(checked)
        self.checked_changed.emit(checked)

    def is_checked(self) -> bool:   return self._cb.isChecked()
    def set_checked(self, v: bool): self._cb.setChecked(v)
    def item_id(self):              return self._item_id
    def item_name(self) -> str:     return self._name

    def quantity(self) -> int:
        try:
            return max(1, int(self._qty.text()))
        except (ValueError, TypeError):
            return 1


class _AddRequirementDialog(QDialog):
    """Dialog for adding project requirements — multi-select from tracker or freeform."""

    def __init__(self, project_svc, parent=None):
        super().__init__(parent)
        self._svc        = project_svc
        self._all_items: list = []

        self.setWindowTitle("Add Requirements")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(500)
        self.setSizeGripEnabled(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 20, 24, 20)

        hdr = QLabel("📋  Add Requirements")
        hdr.setStyleSheet("font-size: 15px; font-weight: 700; margin-bottom: 2px;")
        lay.addWidget(hdr)

        sub = QLabel("Select one or more items from your trackers, or type a freeform name.")
        sub.setWordWrap(True)
        sub.setObjectName("dimLabel")
        lay.addWidget(sub)

        # ── Type selector ─────────────────────────────────────────────────────
        type_row = QHBoxLayout()
        type_row.setSpacing(6)
        type_row.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        for t in ReqItemType.ALL:
            self._type_combo.addItem(
                f"{ReqItemType.ICONS[t]}  {ReqItemType.LABELS[t]}", t
            )
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_row.addWidget(self._type_combo, stretch=1)

        # Select-all / clear buttons
        sel_all_btn = QPushButton("All")
        sel_all_btn.setObjectName("iconBtn")
        sel_all_btn.setFixedHeight(26)
        sel_all_btn.clicked.connect(self._select_all)
        clr_btn = QPushButton("None")
        clr_btn.setObjectName("iconBtn")
        clr_btn.setFixedHeight(26)
        clr_btn.clicked.connect(self._select_none)
        type_row.addWidget(sel_all_btn)
        type_row.addWidget(clr_btn)
        lay.addLayout(type_row)

        # ── Search ────────────────────────────────────────────────────────────
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter items…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search)
        lay.addWidget(self._search_edit)

        # ── Checklist ─────────────────────────────────────────────────────────
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSelectionMode(QAbstractItemView.NoSelection)
        self._list.setSpacing(1)
        lay.addWidget(self._list, stretch=1)

        # Selection count label
        self._count_lbl = QLabel("0 selected")
        self._count_lbl.setStyleSheet("color: palette(mid-text); font-size: 11px;")
        lay.addWidget(self._count_lbl)

        sep = _hline()
        lay.addWidget(sep)

        # ── Freeform fallback ────────────────────────────────────────────────
        free_hdr = QLabel("Or add a freeform item (not in any tracker):")
        free_hdr.setStyleSheet("font-weight: 600; margin-top: 4px;")
        lay.addWidget(free_hdr)

        free_row = QHBoxLayout()
        free_row.setSpacing(8)
        self._free_name  = QLineEdit()
        self._free_name.setPlaceholderText("Item name…")
        free_row.addWidget(self._free_name, stretch=1)
        free_qty_lbl = QLabel("Qty:")
        free_qty_lbl.setStyleSheet("color: palette(mid-text); font-size: 12px;")
        free_row.addWidget(free_qty_lbl)
        self._free_qty = QLineEdit("1")
        self._free_qty.setValidator(QIntValidator(1, 999))
        self._free_qty.setFixedWidth(56)
        self._free_qty.setAlignment(Qt.AlignCenter)
        free_row.addWidget(self._free_qty)
        lay.addLayout(free_row)

        lay.addSpacing(4)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Add Selected")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # Populate for first type
        self._on_type_changed(0)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _item_name(self, item) -> str:
        for attr in ("name", "paint_name", "title", "tool_name", "material_name"):
            v = getattr(item, attr, None)
            if v:
                return str(v)
        return str(item)

    def _on_type_changed(self, _idx):
        item_type = self._type_combo.currentData()
        self._all_items = []
        if self._svc and hasattr(self._svc, "get_all_items_for_type"):
            try:
                self._all_items = self._svc.get_all_items_for_type(item_type) or []
            except Exception:
                pass
        self._search_edit.clear()
        self._populate_list("")

    def _on_search(self, text: str):
        self._populate_list(text)

    def _populate_list(self, query: str):
        from PySide6.QtCore import QSize
        self._list.clear()
        q = query.strip().lower()
        for item in self._all_items:
            name = self._item_name(item)
            if q and q not in name.lower():
                continue
            li = QListWidgetItem()
            li.setSizeHint(QSize(0, 36))
            self._list.addItem(li)
            # Pass color swatch for items that have a hex color (e.g. paints)
            item_color = getattr(item, "color", None) or getattr(item, "hex_color", None)
            row_widget = _ReqItemRow(name, getattr(item, "id", None), color=item_color)
            row_widget.checked_changed.connect(self._update_count)
            self._list.setItemWidget(li, row_widget)
        self._update_count()

    def _update_count(self):
        n = self._checked_count()
        self._count_lbl.setText(f"{n} selected" if n else "0 selected")

    def _checked_count(self) -> int:
        count = 0
        for i in range(self._list.count()):
            w = self._list.itemWidget(self._list.item(i))
            if isinstance(w, _ReqItemRow) and w.is_checked():
                count += 1
        return count

    def _select_all(self):
        for i in range(self._list.count()):
            w = self._list.itemWidget(self._list.item(i))
            if isinstance(w, _ReqItemRow):
                w.set_checked(True)
        self._update_count()

    def _select_none(self):
        for i in range(self._list.count()):
            w = self._list.itemWidget(self._list.item(i))
            if isinstance(w, _ReqItemRow):
                w.set_checked(False)
        self._update_count()

    def all_values(self) -> list[dict]:
        """Return a list of requirement dicts — one per checked item + optional freeform."""
        item_type = self._type_combo.currentData()
        results = []

        for i in range(self._list.count()):
            w = self._list.itemWidget(self._list.item(i))
            if isinstance(w, _ReqItemRow) and w.is_checked():
                results.append({
                    "item_type":       item_type,
                    "item_name":       w.item_name(),
                    "item_id":         w.item_id(),
                    "quantity_needed": w.quantity(),
                    "notes":           "",
                })

        # Freeform entry
        free_name = self._free_name.text().strip()
        if free_name:
            results.append({
                "item_type":       item_type,
                "item_name":       free_name,
                "item_id":         None,
                "quantity_needed": max(1, int(self._free_qty.text() or "1")),
                "notes":           "",
            })

        return results


class _EndSessionDialog(QDialog):
    """Shown when the user clicks End Session — lets them log notes/outcome/next action."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("End Live Session")
        self.setModal(True)
        self.setMinimumWidth(400)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 20, 20, 20)

        hdr = QLabel("⏹  Wrap up your session")
        hdr.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(hdr)

        sub = QLabel("Optionally record what you worked on before logging the session.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: palette(mid-text); margin-bottom: 4px;")
        lay.addWidget(sub)

        lay.addWidget(QLabel("Notes"))
        self._notes = QLineEdit()
        self._notes.setPlaceholderText("What did you work on?")
        lay.addWidget(self._notes)

        lay.addWidget(QLabel("Outcome"))
        self._outcome = QLineEdit()
        self._outcome.setPlaceholderText("What did you achieve?")
        lay.addWidget(self._outcome)

        lay.addWidget(QLabel("Next Action"))
        self._next_action = QLineEdit()
        self._next_action.setPlaceholderText("What's the next step?  (fills in a calendar event if set)")
        lay.addWidget(self._next_action)

        lay.addSpacing(4)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("End Session")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def values(self) -> tuple[str, str, str]:
        return (
            self._notes.text().strip(),
            self._outcome.text().strip(),
            self._next_action.text().strip(),
        )


class _CalendarEventOfferDialog(QDialog):
    """Offers to create a calendar event from a session's Next Action text."""

    def __init__(self, next_action: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add to Calendar?")
        self.setModal(True)
        self.setMinimumWidth(380)

        self._date_str = ""
        self._undetermined = False

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        # Header
        hdr = QLabel("📅  Create Calendar Event")
        hdr.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(hdr)

        # Next-action text display
        action_lbl = QLabel(f"<b>Next Action:</b> {next_action}")
        action_lbl.setWordWrap(True)
        action_lbl.setStyleSheet("color: palette(text); padding: 8px; "
                                 "background: palette(mid); border-radius: 4px;")
        lay.addWidget(action_lbl)

        info = QLabel("Choose a date for this event or mark it as undetermined.")
        info.setWordWrap(True)
        info.setStyleSheet("color: palette(mid-text);")
        lay.addWidget(info)

        # Date row
        date_row = QHBoxLayout()
        date_row.setSpacing(8)
        date_lbl = QLabel("Date:")
        date_lbl.setFixedWidth(44)
        date_row.addWidget(date_lbl)

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setEnabled(True)
        date_row.addWidget(self._date_edit, stretch=1)
        lay.addLayout(date_row)

        # Undetermined checkbox
        self._undet_cb = QCheckBox("Date undetermined — just note it")
        self._undet_cb.toggled.connect(self._on_undet_toggled)
        lay.addWidget(self._undet_cb)

        lay.addSpacing(4)

        # Buttons
        btns = QDialogButtonBox()
        self._add_btn = btns.addButton("Add to Calendar", QDialogButtonBox.AcceptRole)
        btns.addButton("Skip", QDialogButtonBox.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_undet_toggled(self, checked: bool):
        self._date_edit.setEnabled(not checked)

    def result_data(self) -> tuple[str, bool]:
        """Returns (date_str, undetermined). date_str is 'YYYY-MM-DD' or ''."""
        undetermined = self._undet_cb.isChecked()
        if undetermined:
            return "", True
        return self._date_edit.date().toString("yyyy-MM-dd"), False


# ─────────────────────────────────────────────────────────────────────────────

_CARD_W  = 210
_CARD_H  = 250
_THUMB_H = 160
_GALLERY_COLS = 3


class _ImageCopyWorker(QThread):
    """Copy a file to a destination path without blocking the UI thread."""
    finished = Signal(str)   # destination path on success
    failed   = Signal(str)   # error message on failure

    def __init__(self, src: str, dst: str, parent=None):
        super().__init__(parent)
        self._src = src
        self._dst = dst

    def run(self):
        try:
            shutil.copy2(self._src, self._dst)
            self.finished.emit(self._dst)
        except Exception as e:
            self.failed.emit(str(e))


class _GalleryCard(QFrame):
    """Single photo card in the gallery grid."""
    open_requested        = Signal(int)      # emits list index
    edit_requested        = Signal(object)
    delete_requested      = Signal(object)
    stage_change_requested = Signal(object, str)  # (entry, new_stage)

    def __init__(self, entry, index: int, ms_map: dict, sess_map: dict, parent=None):
        super().__init__(parent)
        self._entry   = entry
        self._index   = index
        self._ms_map  = ms_map
        self._sess_map = sess_map
        self.setObjectName("galleryCard")
        self.setFixedSize(_CARD_W, _CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 6)
        lay.setSpacing(4)

        # ── Thumbnail ─────────────────────────────────────────────────────
        self._thumb = QLabel()
        self._thumb.setObjectName("galleryThumb")
        self._thumb.setFixedSize(_CARD_W - 8, _THUMB_H)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._load_thumb()
        lay.addWidget(self._thumb)

        # ── Title (elided) ────────────────────────────────────────────────
        title = (self._entry.title or "").strip()
        if title:
            t_lbl = QLabel()
            t_lbl.setObjectName("galleryCardTitle")
            fm = t_lbl.fontMetrics()
            t_lbl.setText(fm.elidedText(title, Qt.ElideRight, _CARD_W - 16))
            lay.addWidget(t_lbl)

        # ── Date + milestone badge row ────────────────────────────────────
        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(4)

        date_str = self._entry.captured_at or ""
        try:
            from datetime import date as _date
            date_str = _date.fromisoformat(date_str).strftime("%b %d, %Y")
        except Exception:
            pass
        d_lbl = QLabel(f"📅  {date_str}")
        d_lbl.setObjectName("galleryCardDate")
        meta.addWidget(d_lbl)
        meta.addStretch()

        # Progress stage badge — always present, clickable to cycle / pick stage
        stage = getattr(self._entry, "progress_stage", "") or ""
        stage_color = GalleryStage.COLORS.get(stage, "#606060") if stage else "#404040"
        stage_label = GalleryStage.LABELS.get(stage, stage) if stage else "＋ Stage"
        self._stage_btn = QPushButton(stage_label)
        self._stage_btn.setObjectName("galleryStageBtn")
        self._stage_btn.setCursor(Qt.PointingHandCursor)
        self._stage_btn.setToolTip(
            "Left-click to cycle stage  ·  Right-click to choose"
        )
        self._stage_btn.setStyleSheet(
            f"QPushButton#galleryStageBtn {{"
            f"  background: {stage_color}33; color: {stage_color}; "
            f"  border: 1px solid {stage_color}55; border-radius: 3px; "
            f"  padding: 0px 5px; font-size: 10px; font-weight: 700;"
            f"}}"
            f"QPushButton#galleryStageBtn:hover {{"
            f"  background: {stage_color}55;"
            f"}}"
        )
        self._stage_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self._stage_btn.clicked.connect(self._cycle_stage)
        self._stage_btn.customContextMenuRequested.connect(self._stage_menu)
        meta.addWidget(self._stage_btn)

        if self._entry.milestone_id:
            ms = self._ms_map.get(self._entry.milestone_id)
            if ms:
                ms_lbl = QLabel("🎯")
                ms_lbl.setObjectName("galleryMilestoneBadge")
                ms_lbl.setToolTip(f"Milestone: {ms.title}")
                meta.addWidget(ms_lbl)

        if self._entry.session_id and self._entry.session_id in self._sess_map:
            s_lbl = QLabel("⏱")
            s_lbl.setObjectName("galleryMilestoneBadge")
            s_lbl.setToolTip("Linked to a hobby session")
            meta.addWidget(s_lbl)

        lay.addLayout(meta)

        # ── Hover overlay — covers thumbnail only, not title/meta area ───────
        self._overlay = QWidget(self)
        self._overlay.setObjectName("galleryCardOverlay")
        # thumb sits at x=4, y=4 (card contentsMargins are 4,4,4,6)
        self._overlay.setGeometry(4, 4, _CARD_W - 8, _THUMB_H)
        self._overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._overlay.hide()

        ov_lay = QVBoxLayout(self._overlay)
        ov_lay.setAlignment(Qt.AlignCenter)
        ov_lay.setSpacing(8)

        view_btn = QPushButton("🔍  View")
        view_btn.setObjectName("primaryBtn")
        view_btn.setFixedWidth(100)
        view_btn.clicked.connect(lambda: self.open_requested.emit(self._index))

        edit_btn = QPushButton("✏  Edit")
        edit_btn.setObjectName("secondaryBtn")
        edit_btn.setFixedWidth(100)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._entry))

        del_btn = QPushButton("Remove")
        del_btn.setObjectName("dangerBtn")
        del_btn.setFixedWidth(100)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._entry))

        ov_lay.addWidget(view_btn)
        ov_lay.addWidget(edit_btn)
        ov_lay.addWidget(del_btn)

    def _load_thumb(self):
        try:
            path = self._entry.image_path
            if path and os.path.isfile(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    scaled = pix.scaled(
                        _CARD_W - 8, _THUMB_H,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    self._thumb.setPixmap(scaled)
                    return
        except Exception:
            pass
        self._thumb.setText("📷")
        self._thumb.setStyleSheet("font-size:28px; color:#555; background:transparent;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(4, 4, self.width() - 8, _THUMB_H)

    def enterEvent(self, event):
        self._overlay.show()
        self._overlay.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._overlay.hide()
        super().leaveEvent(event)

    # ── Quick stage assignment ─────────────────────────────────────────────────

    # Full cycle order: unstaged → Before → During → After → Reference → Completed → (back to unstaged)
    _STAGE_CYCLE = [""] + list(GalleryStage.ALL)

    def _cycle_stage(self):
        """Left-click: advance to the next stage in the cycle."""
        current = getattr(self._entry, "progress_stage", "") or ""
        try:
            idx = self._STAGE_CYCLE.index(current)
        except ValueError:
            idx = 0
        new_stage = self._STAGE_CYCLE[(idx + 1) % len(self._STAGE_CYCLE)]
        self.stage_change_requested.emit(self._entry, new_stage)

    def _stage_menu(self, pos):
        """Right-click: pop a menu with all stage options for explicit selection."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        current = getattr(self._entry, "progress_stage", "") or ""

        # "No stage" option
        act_none = menu.addAction("— None")
        act_none.setCheckable(True)
        act_none.setChecked(current == "")
        act_none.triggered.connect(lambda: self.stage_change_requested.emit(self._entry, ""))
        menu.addSeparator()

        for s in GalleryStage.ALL:
            label = GalleryStage.LABELS.get(s, s)
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(current == s)
            act.triggered.connect(
                lambda _checked, _s=s:
                    self.stage_change_requested.emit(self._entry, _s)
            )
        menu.exec(self._stage_btn.mapToGlobal(pos))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_requested.emit(self._index)
        super().mousePressEvent(event)


class _PhotoLightbox(QDialog):
    """Full-size photo viewer with prev/next navigation."""
    edit_requested   = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, entries: list, start_index: int,
                 ms_map: dict, sess_map: dict, parent=None):
        super().__init__(parent)
        self._entries    = entries
        self._index      = start_index
        self._ms_map     = ms_map
        self._sess_map   = sess_map
        self.setObjectName("lightboxDialog")
        self.setModal(True)
        self.setWindowTitle("Progress Gallery")
        screen = QApplication.primaryScreen().availableGeometry()
        w = min(1100, int(screen.width()  * 0.88))
        h = min(780,  int(screen.height() * 0.88))
        self.resize(w, h)
        self._build()
        self._show_entry(self._index)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("lightboxHeader")
        header.setFixedHeight(44)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 12, 0)
        self._counter_lbl = QLabel()
        self._counter_lbl.setObjectName("lightboxCounter")
        h_lay.addWidget(self._counter_lbl)
        h_lay.addStretch()
        close_btn = QPushButton("✕  Close")
        close_btn.setObjectName("ghostBtn")
        close_btn.setFixedHeight(28)
        close_btn.clicked.connect(self.accept)
        h_lay.addWidget(close_btn)
        root.addWidget(header)

        # ── Image area with nav arrows ────────────────────────────────────
        img_row = QHBoxLayout()
        img_row.setContentsMargins(0, 0, 0, 0)
        img_row.setSpacing(0)

        self._prev_btn = QPushButton("‹")
        self._prev_btn.setObjectName("lightboxNavBtn")
        self._prev_btn.setFixedWidth(48)
        self._prev_btn.clicked.connect(self._go_prev)
        img_row.addWidget(self._prev_btn)

        self._image_lbl = QLabel()
        self._image_lbl.setObjectName("lightboxImage")
        self._image_lbl.setAlignment(Qt.AlignCenter)
        self._image_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        img_row.addWidget(self._image_lbl, stretch=1)

        self._next_btn = QPushButton("›")
        self._next_btn.setObjectName("lightboxNavBtn")
        self._next_btn.setFixedWidth(48)
        self._next_btn.clicked.connect(self._go_next)
        img_row.addWidget(self._next_btn)

        root.addLayout(img_row, stretch=1)

        # ── Info panel ────────────────────────────────────────────────────
        info = QWidget()
        info.setObjectName("lightboxInfo")
        info.setFixedHeight(110)
        i_lay = QVBoxLayout(info)
        i_lay.setContentsMargins(24, 10, 24, 10)
        i_lay.setSpacing(4)

        # Title row + action buttons
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("lightboxTitle")
        title_row.addWidget(self._title_lbl, stretch=1)

        self._edit_btn = QPushButton("✏  Edit")
        self._edit_btn.setObjectName("secondaryBtn")
        self._edit_btn.setFixedHeight(28)
        self._edit_btn.clicked.connect(self._on_edit)
        title_row.addWidget(self._edit_btn)

        self._del_btn = QPushButton("Remove")
        self._del_btn.setObjectName("dangerBtn")
        self._del_btn.setFixedHeight(28)
        self._del_btn.clicked.connect(self._on_delete)
        title_row.addWidget(self._del_btn)
        i_lay.addLayout(title_row)

        # Meta row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(16)
        self._date_lbl = QLabel()
        self._date_lbl.setObjectName("lightboxMeta")
        meta_row.addWidget(self._date_lbl)
        self._ms_lbl = QLabel()
        self._ms_lbl.setObjectName("lightboxMeta")
        meta_row.addWidget(self._ms_lbl)
        self._sess_lbl = QLabel()
        self._sess_lbl.setObjectName("lightboxMeta")
        meta_row.addWidget(self._sess_lbl)
        meta_row.addStretch()
        i_lay.addLayout(meta_row)

        # Note
        self._note_lbl = QLabel()
        self._note_lbl.setObjectName("lightboxNote")
        self._note_lbl.setWordWrap(True)
        i_lay.addWidget(self._note_lbl)

        root.addWidget(info)

    def _show_entry(self, idx: int):
        if not self._entries:
            return
        self._index = max(0, min(idx, len(self._entries) - 1))
        entry = self._entries[self._index]
        n = len(self._entries)

        self._counter_lbl.setText(f"Photo {self._index + 1} of {n}")
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < n - 1)

        # Image
        img_w = self.width()  - 96
        img_h = self.height() - 44 - 110
        try:
            if entry.image_path and os.path.isfile(entry.image_path):
                pix = QPixmap(entry.image_path)
                if not pix.isNull():
                    self._image_lbl.setPixmap(
                        pix.scaled(img_w, img_h,
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                else:
                    self._image_lbl.setText("⚠  Could not load image")
            else:
                self._image_lbl.setText("⚠  Image file not found")
        except Exception:
            self._image_lbl.setText("⚠  Error loading image")

        # Title
        self._title_lbl.setText(entry.title or "Untitled")

        # Date
        date_str = entry.captured_at or ""
        try:
            from datetime import date as _date
            date_str = _date.fromisoformat(date_str).strftime("%B %d, %Y")
        except Exception:
            pass
        self._date_lbl.setText(f"📅  {date_str}")

        # Milestone
        if entry.milestone_id:
            ms = self._ms_map.get(entry.milestone_id)
            self._ms_lbl.setText(f"🎯  {ms.title}" if ms else "")
            self._ms_lbl.setVisible(bool(ms))
        else:
            self._ms_lbl.hide()

        # Session
        if entry.session_id:
            sess = self._sess_map.get(entry.session_id)
            if sess:
                self._sess_lbl.setText(f"⏱  {sess.duration_minutes} min session")
                self._sess_lbl.show()
            else:
                self._sess_lbl.hide()
        else:
            self._sess_lbl.hide()

        # Note
        self._note_lbl.setText(entry.note or "")
        self._note_lbl.setVisible(bool(entry.note))

    def _go_prev(self):
        self._show_entry(self._index - 1)

    def _go_next(self):
        self._show_entry(self._index + 1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self._go_prev()
        elif event.key() == Qt.Key_Right:
            self._go_next()
        elif event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Space):
            self.accept()
        else:
            super().keyPressEvent(event)

    def _on_edit(self):
        self.edit_requested.emit(self._entries[self._index])
        self.accept()

    def _on_delete(self):
        self.delete_requested.emit(self._entries[self._index])
        self.accept()


class _AddPhotoDialog(QDialog):
    """Add a new gallery entry or edit an existing one.
    File copy happens in a background QThread so the UI never freezes."""

    def __init__(self, project_id: int, milestones: list, sessions: list,
                 gallery_dir: Optional[str] = None,
                 entry=None, parent=None):
        super().__init__(parent)
        self._project_id  = project_id
        self._milestones  = milestones
        self._sessions    = sessions
        self._gallery_dir = gallery_dir
        self._entry       = entry          # None → add mode
        self._source_path: Optional[str] = None
        self._dest_path:   Optional[str] = None
        self._worker:      Optional[_ImageCopyWorker] = None
        self._result:      Optional[dict] = None

        self.setWindowTitle("Edit Photo" if entry else "Add Progress Photo")
        self.setModal(True)
        self.setMinimumSize(540, 560)
        self._build()
        if entry:
            self._populate(entry)

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # ── Image preview area ────────────────────────────────────────────
        preview_frame = QFrame()
        preview_frame.setObjectName("galleryImgPreviewFrame")
        preview_frame.setFixedHeight(200)
        pf_lay = QVBoxLayout(preview_frame)
        pf_lay.setContentsMargins(0, 0, 0, 0)
        pf_lay.setAlignment(Qt.AlignCenter)

        self._preview_lbl = QLabel("No photo selected")
        self._preview_lbl.setObjectName("galleryImgPreview")
        self._preview_lbl.setAlignment(Qt.AlignCenter)
        self._preview_lbl.setFixedSize(496, 192)
        pf_lay.addWidget(self._preview_lbl)
        root.addWidget(preview_frame)

        # Browse row
        browse_row = QHBoxLayout()
        self._browse_btn = QPushButton("🖼  Browse…")
        self._browse_btn.setObjectName("secondaryBtn")
        self._browse_btn.setFixedHeight(30)
        self._browse_btn.clicked.connect(self._browse)
        browse_row.addWidget(self._browse_btn)
        self._file_lbl = QLabel("No file selected")
        self._file_lbl.setObjectName("metaLabel")
        browse_row.addWidget(self._file_lbl, stretch=1)
        root.addLayout(browse_row)

        # ── Form ──────────────────────────────────────────────────────────
        form = QGridLayout()
        form.setSpacing(8)
        form.setColumnMinimumWidth(0, 90)
        form.setColumnStretch(1, 1)

        form.addWidget(QLabel("Title"), 0, 0)
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("Optional — e.g. 'After priming'")
        self._title_input.setFixedHeight(30)
        form.addWidget(self._title_input, 0, 1)

        form.addWidget(QLabel("Date"), 1, 0)
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setFixedHeight(30)
        form.addWidget(self._date_edit, 1, 1)

        form.addWidget(QLabel("Milestone"), 2, 0)
        self._ms_combo = QComboBox()
        self._ms_combo.setFixedHeight(30)
        self._ms_combo.addItem("— None —", None)
        for m in self._milestones:
            prefix = "✅ " if m.is_complete else "○ "
            self._ms_combo.addItem(prefix + m.title, m.id)
        form.addWidget(self._ms_combo, 2, 1)

        form.addWidget(QLabel("Session"), 3, 0)
        self._sess_combo = QComboBox()
        self._sess_combo.setFixedHeight(30)
        self._sess_combo.addItem("— None —", None)
        for s in self._sessions:
            try:
                dt = datetime.fromisoformat(s.started_at)
                lbl = dt.strftime("%b %d, %Y") + f"  ({s.duration_minutes} min)"
            except Exception:
                lbl = f"Session {s.id}"
            self._sess_combo.addItem(lbl, s.id)
        form.addWidget(self._sess_combo, 3, 1)

        form.addWidget(QLabel("Progress Stage"), 4, 0)
        self._stage_combo = QComboBox()
        self._stage_combo.setFixedHeight(30)
        self._stage_combo.addItem("— None —", GalleryStage.NONE)
        for stage in GalleryStage.ALL:
            self._stage_combo.addItem(GalleryStage.LABELS.get(stage, stage), stage)
        form.addWidget(self._stage_combo, 4, 1)

        root.addLayout(form)

        # Note
        root.addWidget(QLabel("Note (optional)"))
        self._note_input = QTextEdit()
        self._note_input.setPlaceholderText("Describe what you accomplished…")
        self._note_input.setFixedHeight(72)
        root.addWidget(self._note_input)

        # Status label shown during copy
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("metaLabel")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.hide()
        root.addWidget(self._status_lbl)

        root.addStretch()

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("ghostBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._save_btn = QPushButton("Add Photo" if not self._entry else "Save Changes")
        self._save_btn.setObjectName("primaryBtn")
        self._save_btn.setFixedHeight(34)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        root.addLayout(btn_row)

    def _populate(self, entry):
        self._dest_path = entry.image_path
        self._title_input.setText(entry.title or "")
        self._note_input.setPlainText(entry.note or "")
        try:
            from datetime import date as _date
            d = _date.fromisoformat(entry.captured_at)
            self._date_edit.setDate(QDate(d.year, d.month, d.day))
        except Exception:
            pass
        for i in range(self._ms_combo.count()):
            if self._ms_combo.itemData(i) == entry.milestone_id:
                self._ms_combo.setCurrentIndex(i)
                break
        for i in range(self._sess_combo.count()):
            if self._sess_combo.itemData(i) == entry.session_id:
                self._sess_combo.setCurrentIndex(i)
                break
        stage_val = getattr(entry, "progress_stage", "") or ""
        for i in range(self._stage_combo.count()):
            if self._stage_combo.itemData(i) == stage_val:
                self._stage_combo.setCurrentIndex(i)
                break
        if entry.image_path and os.path.isfile(entry.image_path):
            self._load_preview(entry.image_path)
            self._file_lbl.setText(os.path.basename(entry.image_path))

    # ── Actions ────────────────────────────────────────────────────────────

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Progress Photo", "",
            "Images (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tiff *.tif)"
        )
        if path:
            self._source_path = path
            self._file_lbl.setText(os.path.basename(path))
            self._load_preview(path)

    def _load_preview(self, path: str):
        try:
            pix = QPixmap(path)
            if not pix.isNull():
                self._preview_lbl.setPixmap(
                    pix.scaled(492, 188, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                return
        except Exception:
            pass
        self._preview_lbl.setText("Preview unavailable")

    def _on_save(self):
        # Require an image in add mode
        if not self._entry and not self._source_path:
            QMessageBox.warning(self, "No Photo", "Please select a photo first.")
            return

        if self._source_path and self._gallery_dir:
            # Copy file in background
            suffix   = Path(self._source_path).suffix.lower() or ".jpg"
            dst_path = os.path.join(self._gallery_dir, uuid.uuid4().hex + suffix)
            self._save_btn.setEnabled(False)
            self._save_btn.setText("Saving…")
            self._status_lbl.setText("Copying photo…")
            self._status_lbl.show()
            self._worker = _ImageCopyWorker(self._source_path, dst_path, self)
            self._worker.finished.connect(self._on_copy_done)
            self._worker.failed.connect(self._on_copy_failed)
            self._worker.start()
        elif self._source_path:
            # No gallery dir provided — use source as-is
            self._dest_path = self._source_path
            self._finish_save()
        else:
            # Edit mode, no new file selected
            self._finish_save()

    def _on_copy_done(self, dst: str):
        self._dest_path = dst
        self._status_lbl.hide()
        self._save_btn.setEnabled(True)
        self._save_btn.setText("Save Changes" if self._entry else "Add Photo")
        self._finish_save()

    def _on_copy_failed(self, err: str):
        self._status_lbl.hide()
        self._save_btn.setEnabled(True)
        self._save_btn.setText("Save Changes" if self._entry else "Add Photo")
        QMessageBox.critical(self, "Copy Failed", f"Could not copy photo:\n{err}")

    def _finish_save(self):
        d = self._date_edit.date()
        date_str = f"{d.year():04d}-{d.month():02d}-{d.day():02d}"
        stage = self._stage_combo.currentData() or GalleryStage.NONE
        self._result = {
            "project_id":     self._project_id,
            "image_path":     self._dest_path or "",
            "title":          self._title_input.text().strip(),
            "note":           self._note_input.toPlainText().strip(),
            "captured_at":    date_str,
            "milestone_id":   self._ms_combo.currentData(),
            "session_id":     self._sess_combo.currentData(),
            "progress_stage": stage,
        }
        self.accept()

    def get_values(self) -> dict:
        return self._result or {}


# ─────────────────────────────────────────────────────────────────────────────
# Gallery tab
# ─────────────────────────────────────────────────────────────────────────────

class GalleryTab(QWidget):
    """Visual progress gallery for a project.

    Two view modes:
      Timeline (default) — photos grouped by progress stage with colour-coded
                           section headers; all photos visible at once.
      Filter             — flat grid with a stage-filter combo box.
    """

    _TIMELINE_STAGE_ORDER = [
        GalleryStage.BEFORE, GalleryStage.DURING, GalleryStage.AFTER,
        GalleryStage.REFERENCE, GalleryStage.COMPLETED,
    ]

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx        = context
        self._project_id: Optional[int] = None
        self._entries:    list = []
        self._milestones: list = []
        self._sessions:   list = []
        self._cards:      list[_GalleryCard] = []
        self._view_mode:  str  = "timeline"   # "timeline" | "filter"
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # ── Toolbar ───────────────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)

        self._count_lbl = QLabel()
        self._count_lbl.setObjectName("galleryCountLabel")
        bar.addWidget(self._count_lbl)

        # Stage filter — only visible in Filter mode
        self._stage_filter = QComboBox()
        self._stage_filter.setObjectName("filterCombo")
        self._stage_filter.setFixedHeight(30)
        self._stage_filter.addItem("All Stages", "")
        for _s in GalleryStage.ALL:
            self._stage_filter.addItem(GalleryStage.LABELS.get(_s, _s), _s)
        self._stage_filter.currentIndexChanged.connect(self._rebuild_grid)
        self._stage_filter.hide()   # hidden by default (timeline mode)
        bar.addWidget(self._stage_filter)

        bar.addStretch()

        # View-mode toggle button
        self._view_toggle_btn = QPushButton("⚙  Filter View")
        self._view_toggle_btn.setObjectName("secondaryBtn")
        self._view_toggle_btn.setFixedHeight(32)
        self._view_toggle_btn.setToolTip("Switch between Timeline and Filter views")
        self._view_toggle_btn.clicked.connect(self._toggle_view_mode)
        bar.addWidget(self._view_toggle_btn)

        self._add_btn = QPushButton("📸  Add Photo")
        self._add_btn.setObjectName("primaryBtn")
        self._add_btn.setFixedHeight(32)
        self._add_btn.clicked.connect(self._on_add)
        bar.addWidget(self._add_btn)
        root.addLayout(bar)

        # ── Scroll area (inner widget recreated each rebuild) ─────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self._scroll, stretch=1)

        # ── Empty state ───────────────────────────────────────────────────
        self._empty_widget = QWidget()
        ev_lay = QVBoxLayout(self._empty_widget)
        ev_lay.setAlignment(Qt.AlignCenter)
        ev_lay.setSpacing(16)

        em_lbl = QLabel("📸")
        em_lbl.setAlignment(Qt.AlignCenter)
        em_lbl.setStyleSheet("font-size:48px; background:transparent;")
        ev_lay.addWidget(em_lbl)

        em_txt = QLabel("No progress photos yet\n\nDocument your hobby journey — add your first photo.")
        em_txt.setObjectName("galleryEmptyLabel")
        em_txt.setAlignment(Qt.AlignCenter)
        ev_lay.addWidget(em_txt)

        em_btn = QPushButton("Add First Photo")
        em_btn.setObjectName("primaryBtn")
        em_btn.setFixedWidth(160)
        em_btn.setFixedHeight(36)
        em_btn.clicked.connect(self._on_add)
        ev_lay.addWidget(em_btn, alignment=Qt.AlignCenter)
        root.addWidget(self._empty_widget)

        self._empty_widget.hide()

    # ── View-mode toggle ───────────────────────────────────────────────────

    def _toggle_view_mode(self):
        if self._view_mode == "timeline":
            self._view_mode = "filter"
            self._view_toggle_btn.setText("📅  Timeline View")
            self._stage_filter.show()
        else:
            self._view_mode = "timeline"
            self._view_toggle_btn.setText("⚙  Filter View")
            self._stage_filter.hide()
            self._stage_filter.setCurrentIndex(0)   # reset filter when leaving
        self._rebuild_grid()

    # ── Data loading ───────────────────────────────────────────────────────

    def load(self, project_id: int, entries: list,
             milestones: list, sessions: list):
        self._project_id = project_id
        self._entries    = entries
        self._milestones = milestones
        self._sessions   = sessions
        # Rebuild immediately — correct if the tab is already visible.
        # showEvent handles the case where this tab isn't visible yet.
        self._rebuild_grid()

    def showEvent(self, event):
        """Re-check column count once the viewport has its real width."""
        super().showEvent(event)
        if self._entries and self._cols() != getattr(self, "_last_cols", 0):
            # Use a 0-ms timer so Qt finishes the show-layout pass first.
            QTimer.singleShot(0, self._rebuild_grid)

    def _cols(self) -> int:
        """Dynamic column count — fills available viewport width with cards."""
        vp_w = self._scroll.viewport().width()
        if vp_w < _CARD_W:
            # Fallback: viewport not yet sized — use the tab widget's width
            # minus the GalleryTab's own left+right content margins (32px).
            vp_w = max(_CARD_W, self.width() - 32)
        spacing = 12
        return max(1, (vp_w - spacing) // (_CARD_W + spacing))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Rebuild only when the column count would change to avoid flicker
        if self._entries and self._cols() != getattr(self, "_last_cols", 0):
            self._rebuild_grid()

    def _rebuild_grid(self):
        """Tear down existing inner widget and rebuild from scratch."""
        # Discard all current card references
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        # Remove old inner widget from scroll (deleteLater is safe here)
        old_inner = self._scroll.widget()
        if old_inner:
            self._scroll.takeWidget()
            old_inner.deleteLater()

        if not self._entries:
            self._scroll.hide()
            self._empty_widget.show()
            self._count_lbl.setText("")
            return

        self._empty_widget.hide()
        self._scroll.show()

        if self._view_mode == "timeline":
            self._rebuild_timeline()
        else:
            self._rebuild_filter()

    def _rebuild_timeline(self):
        """Group photos by progress stage with coloured section headers."""
        ms_map   = {m.id: m for m in self._milestones if m.id}
        sess_map = {s.id: s for s in self._sessions   if s.id}
        cols = self._cols()
        self._last_cols = cols

        # Build stage → entries mapping (preserving TIMELINE_STAGE_ORDER)
        stage_groups: dict[str, list] = {}
        for stage in self._TIMELINE_STAGE_ORDER:
            group = [e for e in self._entries
                     if (getattr(e, "progress_stage", "") or "") == stage]
            if group:
                stage_groups[stage] = group
        # Catch unstaged photos (progress_stage is "" or not in known stages)
        known_stages = set(self._TIMELINE_STAGE_ORDER)
        unstaged = [e for e in self._entries
                    if (getattr(e, "progress_stage", "") or "") not in known_stages]
        if unstaged:
            stage_groups[GalleryStage.NONE] = unstaged

        total = len(self._entries)
        self._count_lbl.setText(f"{total} photo{'s' if total != 1 else ''}")

        inner = QWidget()
        inner.setObjectName("galleryTimeline")
        v_lay = QVBoxLayout(inner)
        v_lay.setContentsMargins(0, 0, 0, 0)
        v_lay.setSpacing(16)

        if not stage_groups:
            # Shouldn't happen (entries is non-empty), but guard anyway
            lbl = QLabel("No photos to display.")
            lbl.setObjectName("emptyState")
            lbl.setAlignment(Qt.AlignCenter)
            v_lay.addWidget(lbl)
        else:
            for stage, group in stage_groups.items():
                # Section header
                color = GalleryStage.COLORS.get(stage, "#606060")
                header_lbl = QLabel(GalleryStage.LABELS.get(stage, stage.capitalize()))
                header_lbl.setStyleSheet(
                    f"color: {color}; font-size: 11px; font-weight: 700;"
                    f" letter-spacing: 1px; background: transparent; padding: 2px 0;"
                )
                v_lay.addWidget(header_lbl)

                # Photo grid for this stage
                grid_w = QWidget()
                grid_lay = QGridLayout(grid_w)
                grid_lay.setSpacing(12)
                grid_lay.setContentsMargins(0, 0, 0, 8)
                for c in range(cols):
                    grid_lay.setColumnStretch(c, 1)

                for col_i, entry in enumerate(group):
                    global_i = self._entries.index(entry)
                    card = _GalleryCard(entry, global_i, ms_map, sess_map, self)
                    card.open_requested.connect(self._open_lightbox)
                    card.edit_requested.connect(self._on_edit_entry)
                    card.delete_requested.connect(self._on_delete_entry)
                    card.stage_change_requested.connect(self._on_stage_change)
                    self._cards.append(card)
                    grid_lay.addWidget(
                        card,
                        col_i // cols,
                        col_i % cols,
                        Qt.AlignHCenter | Qt.AlignTop,
                    )
                v_lay.addWidget(grid_w)

        v_lay.addStretch()
        self._scroll.setWidget(inner)

    def _rebuild_filter(self):
        """Flat grid with optional stage filter — original behaviour."""
        ms_map   = {m.id: m for m in self._milestones if m.id}
        sess_map = {s.id: s for s in self._sessions   if s.id}
        cols = self._cols()
        self._last_cols = cols

        active_stage = self._stage_filter.currentData() or ""
        filtered = [
            e for e in self._entries
            if not active_stage
            or (getattr(e, "progress_stage", "") or "") == active_stage
        ]

        total = len(self._entries)
        shown = len(filtered)
        if active_stage and shown < total:
            stage_label = GalleryStage.LABELS.get(active_stage, active_stage)
            self._count_lbl.setText(
                f"{shown} of {total} photo{'s' if total != 1 else ''}  —  {stage_label}"
            )
        else:
            self._count_lbl.setText(f"{total} photo{'s' if total != 1 else ''}")

        inner = QWidget()
        inner.setObjectName("galleryGrid")

        if not filtered:
            # Entries exist but none match the filter
            v_lay = QVBoxLayout(inner)
            v_lay.setAlignment(Qt.AlignCenter)
            empty_lbl = QLabel(
                f"No photos tagged as "
                f"\"{GalleryStage.LABELS.get(active_stage, active_stage)}\" yet.\n"
                f"Edit a photo to assign a progress stage."
            )
            empty_lbl.setObjectName("emptyState")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setWordWrap(True)
            v_lay.addWidget(empty_lbl)
        else:
            grid_lay = QGridLayout(inner)
            grid_lay.setSpacing(12)
            grid_lay.setContentsMargins(0, 0, 0, 0)
            for c in range(cols):
                grid_lay.setColumnStretch(c, 1)
            for local_i, entry in enumerate(filtered):
                global_i = self._entries.index(entry)
                card = _GalleryCard(entry, global_i, ms_map, sess_map, self)
                card.open_requested.connect(self._open_lightbox)
                card.edit_requested.connect(self._on_edit_entry)
                card.delete_requested.connect(self._on_delete_entry)
                card.stage_change_requested.connect(self._on_stage_change)
                self._cards.append(card)
                grid_lay.addWidget(
                    card,
                    local_i // cols,
                    local_i % cols,
                    Qt.AlignHCenter | Qt.AlignTop,
                )

        self._scroll.setWidget(inner)

    def _on_stage_change(self, entry, new_stage: str):
        """Handle a quick stage change from a gallery card badge."""
        self._ctx.event_bus.emit("project_gallery_update", {
            "id":             entry.id,
            "progress_stage": new_stage,
        })

    # ── Actions ────────────────────────────────────────────────────────────

    def _open_lightbox(self, start_idx: int):
        ms_map   = {m.id: m for m in self._milestones if m.id}
        sess_map = {s.id: s for s in self._sessions   if s.id}
        dlg = _PhotoLightbox(self._entries, start_idx, ms_map, sess_map, self)
        dlg.edit_requested.connect(self._on_edit_entry)
        dlg.delete_requested.connect(self._on_delete_entry)
        dlg.exec()

    def _on_add(self):
        if not self._project_id:
            return
        gallery_dir = self._get_gallery_dir()
        dlg = _AddPhotoDialog(
            project_id   = self._project_id,
            milestones   = self._milestones,
            sessions     = self._sessions,
            gallery_dir  = gallery_dir,
            parent       = self,
        )
        if dlg.exec():
            data = dlg.get_values()
            self._ctx.event_bus.emit("project_gallery_add", data)

    def _on_edit_entry(self, entry):
        gallery_dir = self._get_gallery_dir()
        dlg = _AddPhotoDialog(
            project_id   = self._project_id,
            milestones   = self._milestones,
            sessions     = self._sessions,
            gallery_dir  = gallery_dir,
            entry        = entry,
            parent       = self,
        )
        if dlg.exec():
            data = dlg.get_values()
            data["id"] = entry.id
            self._ctx.event_bus.emit("project_gallery_update", data)

    def _on_delete_entry(self, entry):
        reply = QMessageBox.question(
            self, "Remove Photo",
            "Remove this progress photo? The image file will be deleted.\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._ctx.event_bus.emit("project_gallery_delete", {"id": entry.id})

    def _get_gallery_dir(self) -> Optional[str]:
        """Ask the service for the gallery directory for the current project."""
        try:
            svc = self._ctx.services.try_get("project_service")
            if svc and self._project_id:
                return str(svc.gallery_dir(self._project_id))
        except Exception as e:
            print(f"[GALLERY TAB] Could not get gallery dir: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Right panel — project detail
# ─────────────────────────────────────────────────────────────────────────────

class ProjectDetailPanel(QWidget):
    edit_requested   = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx        = context
        self._project_id: Optional[int] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Action toolbar
        toolbar = QWidget()
        toolbar.setObjectName("detailToolbar")
        toolbar.setFixedHeight(44)
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(16, 0, 16, 0)
        tb_lay.setSpacing(8)
        tb_lay.addStretch()

        # Status-change quick buttons (shown/hidden based on current status)
        self._btn_complete = QPushButton("✅  Mark Complete")
        self._btn_complete.setObjectName("successBtn")
        self._btn_complete.setToolTip("Mark this project as completed")
        self._btn_complete.clicked.connect(
            lambda: self._set_status(ProjectStatus.COMPLETED)
        )
        tb_lay.addWidget(self._btn_complete)

        self._btn_hold = QPushButton("⏸  On Hold")
        self._btn_hold.setObjectName("secondaryBtn")
        self._btn_hold.setToolTip("Pause this project")
        self._btn_hold.clicked.connect(
            lambda: self._set_status(ProjectStatus.ON_HOLD)
        )
        tb_lay.addWidget(self._btn_hold)

        self._btn_reactivate = QPushButton("▶  Reactivate")
        self._btn_reactivate.setObjectName("secondaryBtn")
        self._btn_reactivate.setToolTip("Move back to active")
        self._btn_reactivate.clicked.connect(
            lambda: self._set_status(ProjectStatus.ACTIVE)
        )
        tb_lay.addWidget(self._btn_reactivate)

        edit_btn = QPushButton("✏  Edit")
        edit_btn.setObjectName("secondaryBtn")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._project_id))
        tb_lay.addWidget(edit_btn)

        del_btn = QPushButton("🗑  Delete")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._project_id))
        tb_lay.addWidget(del_btn)
        root.addWidget(toolbar)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setObjectName("projectTabWidget")
        self._tabs.setElideMode(Qt.ElideNone)
        _tb = self._tabs.tabBar()
        _tb.setExpanding(False)
        _tb.setUsesScrollButtons(True)
        _tb.setElideMode(Qt.ElideNone)
        # Direct widget stylesheet — highest specificity, unaffected by theme.qss cascade
        _tb.setStyleSheet("""
            QTabBar::tab {
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 500;
                min-width: 0;
                max-width: 9999px;
                border: none;
                border-radius: 5px;
                margin: 6px 2px;
                background: transparent;
                color: #909090;
            }
            QTabBar::tab:selected {
                background: #0078d4;
                color: #ffffff;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background: #1e1e1e;
                color: #c0c0c0;
            }
        """)

        self._overview_tab      = ProjectOverviewTab(self._ctx)
        self._gallery_tab       = GalleryTab(self._ctx)
        self._milestones_tab    = MilestonesTab(self._ctx)
        self._links_tab         = LinksTab(self._ctx)
        self._notes_tab         = NotesTab(self._ctx)
        self._sessions_tab      = SessionsTab(self._ctx)
        self._requirements_tab  = RequirementsTab(self._ctx)

        # Tab order: Overview → Gallery (always) → optional workflow tabs → Requirements
        # Plain text labels — no emojis — so all 7 tabs fit without truncation.
        self._tabs.addTab(self._overview_tab,      "Overview")
        self._tabs.addTab(self._gallery_tab,       "Gallery")
        self._tabs.addTab(self._milestones_tab,    "Milestones")
        self._tabs.addTab(self._notes_tab,         "Notes")
        self._tabs.addTab(self._sessions_tab,      "Sessions")
        self._tabs.addTab(self._links_tab,         "Links")
        self._tabs.addTab(self._requirements_tab,  "Requirements")
        root.addWidget(self._tabs, stretch=1)

        # Wire milestone → note navigation
        self._milestones_tab.note_navigate_requested.connect(self._on_note_navigate)

        # Empty state (no project selected)
        self._empty = QWidget()
        e_lay = QVBoxLayout(self._empty)
        e_lbl = QLabel("Select a project from the left\nor create a new one.")
        e_lbl.setObjectName("emptyState")
        e_lbl.setAlignment(Qt.AlignCenter)
        e_lay.addWidget(e_lbl)
        root.addWidget(self._empty)

        self._tabs.hide()

    # ── Milestone → Note navigation ───────────────────────────────────────────

    def _on_note_navigate(self, milestone) -> None:
        """Called when the user clicks a milestone's note button.

        If the milestone already has a linked note → switch to Notes tab and
        open it.  If it doesn't → create a new note named after the milestone,
        persist the link, refresh both tabs, then open the new note.
        """
        svc = self._ctx.services.try_get("project_service")
        if not svc:
            return

        linked_note_id = getattr(milestone, "linked_note_id", None)

        if linked_note_id:
            # ── Existing note ─────────────────────────────────────────────────
            note = svc.get_note(linked_note_id)
            if note:
                self._go_to_note(note)
            return

        # ── No linked note — create one and link it ───────────────────────────
        try:
            note = svc.add_note(
                project_id=milestone.project_id,
                title=milestone.title,
                content="",
            )
            svc.update_milestone(milestone.id, linked_note_id=note.id)

            # Reload notes + milestones in-place so everything stays fresh
            notes      = svc.get_notes(milestone.project_id)
            milestones = svc.get_milestones(milestone.project_id)
            self._notes_tab.load(milestone.project_id, notes)
            self._milestones_tab.load(milestone.project_id, milestones, notes)

            self._go_to_note(note)
        except Exception as exc:
            print(f"[PROJECT] _on_note_navigate error: {exc}")

    def _go_to_note(self, note) -> None:
        """Switch to the Notes tab and open *note* in the editor."""
        notes_idx = self._tabs.indexOf(self._notes_tab)
        if notes_idx >= 0:
            self._tabs.setTabVisible(notes_idx, True)
            self._tabs.setCurrentIndex(notes_idx)
        self._notes_tab.open_note(note)

    def load_project(self, project, stats, milestones,
                     notes, sessions, linked_entities, gallery=None,
                     requirements=None):
        # Always return to Overview when switching to a different project
        if project.id != self._project_id:
            self._tabs.setCurrentIndex(0)
        self._project_id = project.id
        self._tabs.show()
        self._empty.hide()
        fade_in(self._tabs, duration=160)

        # Show the right status buttons for this project's current state
        status = project.status
        self._btn_complete.setVisible(status == ProjectStatus.ACTIVE)
        self._btn_hold.setVisible(status == ProjectStatus.ACTIVE)
        self._btn_reactivate.setVisible(
            status in (ProjectStatus.COMPLETED, ProjectStatus.ON_HOLD,
                       ProjectStatus.ARCHIVED)
        )

        # Conditional tab visibility based on enabled_systems
        enabled = getattr(project, "enabled_systems", None) or []
        def _tab_visible(tab_widget: QWidget, system_key: str):
            idx = self._tabs.indexOf(tab_widget)
            if idx >= 0:
                show = not enabled or system_key in enabled
                self._tabs.setTabVisible(idx, show)

        _tab_visible(self._milestones_tab,    EnabledSystem.MILESTONES)
        _tab_visible(self._notes_tab,         EnabledSystem.NOTES)
        _tab_visible(self._sessions_tab,      EnabledSystem.SESSIONS)
        _tab_visible(self._links_tab,         EnabledSystem.LINKS)
        # Gallery, Overview, and Requirements are always visible

        self._overview_tab.load(project, stats, milestones)
        self._gallery_tab.load(project.id, gallery or [], milestones, sessions)
        self._milestones_tab.load(project.id, milestones, notes)
        self._notes_tab.load(project.id, notes)
        self._sessions_tab.load(project.id, sessions, milestones)
        self._links_tab.load(project.id, linked_entities, enabled_systems=enabled)
        self._requirements_tab.load(project.id, requirements or [])

    def _set_status(self, new_status: str):
        if self._project_id:
            self._ctx.event_bus.emit("project_edit_requested", {
                "id":     self._project_id,
                "_quick": True,
                "status": new_status,
            })

    def navigate_to_tab(self, tab_name: str,
                        item_id: Optional[int] = None) -> None:
        """Switch to the named tab if it exists and is currently visible.

        Recognised names (case-insensitive):
          overview, gallery, milestones, notes, sessions, links, requirements

        If *item_id* is provided the tab will attempt to scroll to and briefly
        highlight that item after the tab switch.  Fails gracefully when the
        tab does not support item-level navigation or the item no longer exists.
        """
        _TAB_MAP = {
            "overview":     self._overview_tab,
            "gallery":      self._gallery_tab,
            "milestones":   self._milestones_tab,
            "notes":        self._notes_tab,
            "sessions":     self._sessions_tab,
            "links":        self._links_tab,
            "requirements": self._requirements_tab,
        }
        target = _TAB_MAP.get(tab_name.lower())
        if target is None:
            return
        idx = self._tabs.indexOf(target)
        if idx < 0 or not self._tabs.isTabVisible(idx):
            return
        self._tabs.setCurrentIndex(idx)

        # Item-level scroll + highlight — defer so the tab has finished painting
        if item_id is not None:
            def _scroll_after():
                try:
                    if hasattr(target, "scroll_to_item"):
                        target.scroll_to_item(item_id)
                except Exception:
                    pass
            QTimer.singleShot(120, _scroll_after)

    def show_empty(self):
        self._project_id = None
        self._tabs.hide()
        self._empty.show()


# ─────────────────────────────────────────────────────────────────────────────
# Project Edit Dialog
# ─────────────────────────────────────────────────────────────────────────────

class ProjectEditDialog(QDialog):
    def __init__(self, project: Optional[Project] = None, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Edit Project" if project else "New Project")
        self.setMinimumWidth(600)
        self.setSizeGripEnabled(True)
        self._sys_checks: dict[str, QCheckBox] = {}
        self._build()
        if project:
            self._populate(project)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnMinimumWidth(0, 110)
        grid.setColumnStretch(1, 1)

        # ── Name ──────────────────────────────────────────────────────────────
        grid.addWidget(QLabel("Name *"), 0, 0)
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Black Templars 2000pt Army")
        grid.addWidget(self._name, 0, 1)

        # ── Category ──────────────────────────────────────────────────────────
        grid.addWidget(QLabel("Category"), 1, 0)
        self._category = QComboBox()
        for cat in ProjectCategory.ALL:
            self._category.addItem(
                ProjectCategory.ICONS.get(cat, "") + "  " + ProjectCategory.LABELS[cat],
                cat
            )
        grid.addWidget(self._category, 1, 1)

        # ── Priority ──────────────────────────────────────────────────────────
        grid.addWidget(QLabel("Priority"), 2, 0)
        self._priority = QComboBox()
        for p in ProjectPriority.ALL:
            self._priority.addItem(ProjectPriority.LABELS[p], p)
        idx = self._priority.findData(ProjectPriority.MEDIUM)
        if idx >= 0:
            self._priority.setCurrentIndex(idx)
        grid.addWidget(self._priority, 2, 1)

        # ── Tags ──────────────────────────────────────────────────────────────
        grid.addWidget(QLabel("Tags"), 3, 0)
        self._tags = QLineEdit()
        self._tags.setPlaceholderText("comma-separated tags, e.g. painting, wip, contest")
        grid.addWidget(self._tags, 3, 1)

        # ── Status ────────────────────────────────────────────────────────────
        grid.addWidget(QLabel("Status"), 4, 0)
        self._status = QComboBox()
        for s in ProjectStatus.ALL:
            self._status.addItem(ProjectStatus.LABELS[s], s)
        grid.addWidget(self._status, 4, 1)

        # ── Description ───────────────────────────────────────────────────────
        grid.addWidget(QLabel("Description"), 5, 0, Qt.AlignTop)
        self._desc = QTextEdit()
        self._desc.setFixedHeight(68)
        self._desc.setPlaceholderText("Optional project description…")
        grid.addWidget(self._desc, 5, 1)

        lay.addLayout(grid)

        # ── Advanced Options (collapsible) ────────────────────────────────────
        advanced = _CollapsibleSection("Advanced Options", collapsed=True)
        adv_lay = advanced.layout_body()

        adv_grid = QGridLayout()
        adv_grid.setSpacing(10)
        adv_grid.setColumnMinimumWidth(0, 110)
        adv_grid.setColumnStretch(1, 1)

        adv_grid.addWidget(QLabel("Game System"), 0, 0)
        self._system = QComboBox()
        self._system.addItems(GAME_SYSTEMS)
        self._system.setEditable(True)
        adv_grid.addWidget(self._system, 0, 1)

        adv_grid.addWidget(QLabel("Icon"), 1, 0)
        self._icon = QComboBox()
        self._icon.addItems(ICONS)
        adv_grid.addWidget(self._icon, 1, 1)

        adv_grid.addWidget(QLabel("Accent Colour"), 2, 0)
        self._color = QLineEdit("#0078d4")
        self._color.setPlaceholderText("#rrggbb")
        adv_grid.addWidget(self._color, 2, 1)

        adv_grid.addWidget(QLabel("Target Date"), 3, 0)
        self._date = QLineEdit()
        self._date.setPlaceholderText("YYYY-MM-DD (optional)")
        adv_grid.addWidget(self._date, 3, 1)

        adv_w = QWidget()
        adv_w.setLayout(adv_grid)
        adv_lay.addWidget(adv_w)

        # ── Feature Modules (enabled_systems) ─────────────────────────────────
        adv_lay.addWidget(_section_lbl("ENABLED FEATURES"))

        _helper = QLabel(
            "Choose which workflow sections this project uses.  "
            "Gallery is always available."
        )
        _helper.setObjectName("dimLabel")
        _helper.setWordWrap(True)
        adv_lay.addWidget(_helper)

        # Quick presets — only toggle enabled systems, never touch other fields
        _SYSTEMS_PRESETS = [
            ("General",    [EnabledSystem.MILESTONES, EnabledSystem.NOTES,
                            EnabledSystem.SESSIONS, EnabledSystem.LINKS]),
            ("Painting",   [EnabledSystem.MODELS, EnabledSystem.PAINTS,
                            EnabledSystem.MILESTONES, EnabledSystem.NOTES]),
            ("Army Build", [EnabledSystem.MODELS, EnabledSystem.PAINTS,
                            EnabledSystem.ARMIES, EnabledSystem.MILESTONES,
                            EnabledSystem.SESSIONS, EnabledSystem.NOTES,
                            EnabledSystem.LINKS]),
            ("Terrain",    [EnabledSystem.MILESTONES, EnabledSystem.NOTES,
                            EnabledSystem.SESSIONS]),
            ("Dev / Task", [EnabledSystem.MILESTONES, EnabledSystem.NOTES,
                            EnabledSystem.SESSIONS, EnabledSystem.LINKS]),
            ("Minimal",    [EnabledSystem.MILESTONES]),
        ]
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for _preset_label, _preset_sys in _SYSTEMS_PRESETS:
            _pb = QPushButton(_preset_label)
            _pb.setObjectName("presetChip")
            _pb.setFixedHeight(26)
            _pb.clicked.connect(
                lambda _, _sys=_preset_sys: self._apply_systems_preset(_sys)
            )
            preset_row.addWidget(_pb)
        preset_row.addStretch()
        preset_w = QWidget()
        preset_w.setLayout(preset_row)
        adv_lay.addWidget(preset_w)

        sys_grid = QGridLayout()
        sys_grid.setSpacing(6)
        sys_grid.setHorizontalSpacing(16)
        for i, sys_id in enumerate(EnabledSystem.ALL):
            chk = QCheckBox(EnabledSystem.LABELS.get(sys_id, sys_id))
            chk.setChecked(True)
            sys_grid.addWidget(chk, i // 3, i % 3)
            self._sys_checks[sys_id] = chk
        sys_w = QWidget()
        sys_w.setLayout(sys_grid)
        adv_lay.addWidget(sys_w)

        lay.addWidget(advanced)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _populate(self, p: Project):
        self._name.setText(p.name)

        idx = self._category.findData(getattr(p, "category", ProjectCategory.OTHER))
        self._category.setCurrentIndex(idx if idx >= 0 else 0)

        idx = self._priority.findData(getattr(p, "priority", ProjectPriority.MEDIUM))
        if idx >= 0:
            self._priority.setCurrentIndex(idx)

        tags = getattr(p, "tags", []) or []
        self._tags.setText(", ".join(tags))

        idx = self._status.findData(p.status)
        if idx >= 0:
            self._status.setCurrentIndex(idx)

        self._desc.setPlainText(p.description or "")

        # Advanced
        idx = self._system.findText(p.game_system or "")
        self._system.setCurrentIndex(idx if idx >= 0 else 0)

        idx = self._icon.findText(p.icon or "📁")
        if idx >= 0:
            self._icon.setCurrentIndex(idx)

        self._color.setText(p.color or "#0078d4")
        self._date.setText(p.target_date or "")

        enabled = getattr(p, "enabled_systems", None)
        if enabled is not None:
            for sys_id, chk in self._sys_checks.items():
                chk.setChecked(sys_id in enabled)

    def _apply_systems_preset(self, systems: list) -> None:
        """Toggle enabled-system checkboxes to match a preset.
        Other project fields (name, category, etc.) are never touched."""
        for sys_id, chk in self._sys_checks.items():
            chk.setChecked(sys_id in systems)

    def _on_save(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validation", "Project name is required.")
            return
        self.accept()

    def get_values(self) -> dict:
        # Parse tags from comma-separated string
        tags_raw = self._tags.text().strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        # Enabled systems
        enabled_systems = [sid for sid, chk in self._sys_checks.items() if chk.isChecked()]

        return {
            "name":            self._name.text().strip(),
            "category":        self._category.currentData(),
            "priority":        self._priority.currentData(),
            "tags":            tags,
            "status":          self._status.currentData(),
            "description":     self._desc.toPlainText().strip(),
            "game_system":     self._system.currentText().strip(),
            "icon":            self._icon.currentText(),
            "color":           self._color.text().strip() or "#0078d4",
            "target_date":     self._date.text().strip() or None,
            "enabled_systems": enabled_systems,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Root UI widget
# ─────────────────────────────────────────────────────────────────────────────

class ProjectUI(QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left panel
        self._list_panel = ProjectListPanel(self._ctx)
        self._list_panel.project_selected.connect(self._on_project_selected)
        self._list_panel.new_project_requested.connect(self._on_new_project)
        root.addWidget(self._list_panel)

        # Vertical divider
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setObjectName("divider")
        root.addWidget(div)

        # Right detail panel
        self._detail_panel = ProjectDetailPanel(self._ctx)
        self._detail_panel.edit_requested.connect(self._on_edit_project)
        self._detail_panel.delete_requested.connect(self._on_delete_project)
        root.addWidget(self._detail_panel, stretch=1)

    # ── Delegation methods called by plugin ───────────────────────────────────

    def display_projects(self, projects: list[Project], stats_map: dict = None):
        self._list_panel.load_projects(projects, stats_map=stats_map or {})

    def display_project_detail(self, project, stats, milestones,
                               notes, sessions, linked_entities, gallery=None,
                               requirements=None):
        self._list_panel.select_project(project.id)
        self._detail_panel.load_project(
            project, stats, milestones, notes, sessions, linked_entities,
            gallery or [], requirements or [],
        )

    def show_empty_detail(self):
        self._detail_panel.show_empty()

    def handle_quick_create(self) -> None:
        """Ctrl+N support — open the New Project dialog directly."""
        self._on_new_project()

    def _show_success(self, msg: str) -> None:
        ToastManager.instance().show(msg, level="success")

    def _show_error(self, msg: str) -> None:
        ToastManager.instance().show(msg, level="error", duration=5000)

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def _on_project_selected(self, project_id: int):
        self._ctx.event_bus.emit("project_selected", {"id": project_id})

    def _on_new_project(self):
        dlg = ProjectEditDialog(parent=self)
        if dlg.exec():
            self._ctx.event_bus.emit("project_create", dlg.get_values())

    def _on_edit_project(self, project_id: int):
        self._ctx.event_bus.emit("project_edit_requested", {"id": project_id})

    def _on_delete_project(self, project_id: int):
        reply = QMessageBox.question(
            self, "Delete Project",
            "Delete this project? This cannot be undone.\n"
            "(Linked models, paints, etc. are NOT deleted.)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._ctx.event_bus.emit("project_delete", {"id": project_id})
