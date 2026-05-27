"""
Project Tracker 2.0 — UI
Premium two-pane project management interface.
"""
from __future__ import annotations

import logging, os, shutil, uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

from PySide6.QtCore    import Qt, Signal, QTimer, QDate
from PySide6.QtGui     import QColor, QPainter, QPen, QPixmap, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QSizePolicy, QLineEdit, QTextEdit, QComboBox,
    QDialog, QDialogButtonBox, QFileDialog, QApplication,
    QSplitter, QTabWidget, QCheckBox, QSpinBox, QDateEdit,
    QGridLayout, QStackedWidget, QProgressBar, QAbstractSpinBox,
    QMessageBox, QMenu, QToolButton,
)

from ui.toast import ToastManager

from plugins.project_tracker.models import (
    Project, ProjectStatus, ProjectCategory, ProjectPriority,
    EntityType, Milestone, ProjectNote, HobbySession,
    GalleryEntry, GalleryStage, EnabledSystem,
    ProjectRequirement, ReqItemType, ReqStatus,
)

# ── Design system ──────────────────────────────────────────────────────────────
_C = {
    "bg_deep":    "#141414", "bg_base":   "#1c1c1c", "bg_card":    "#1e1e1e",
    "bg_raised":  "#212121", "bg_input":  "#2a2a2a", "bg_hover":   "#2e2e2e",
    "bg_selected":"#0f4a7a",
    "border_lo":  "#282828", "border":    "#363636", "border_hi":  "#484848",
    "text_hi":    "#f0f0f0", "text_mid":  "#d8d8d8", "text_lo":    "#909090",
    "text_dim":   "#606060",
    "accent":     "#0078d4", "accent_hi": "#1a8ee8", "accent_lo":  "#0f4a7a",
    "accent_text":"#60b0ff",
    "danger":     "#e05555", "danger_lo": "#2a1515",
    "success":    "#3dba6e", "success_lo":"#0f2a1a",
    "warning":    "#e07800", "warning_lo":"#2a1800",
    "gold":       "#c8960c", "gold_lo":   "#2a1e00",
    "purple":     "#8b5cf6",
}
_FS = {"xs":"10px","sm":"11px","base":"12px","lg":"13px","xl":"15px","2xl":"20px","3xl":"26px"}
_R  = {"xs":"3px","sm":"4px","base":"6px","lg":"10px","xl":"14px","pill":"999px"}

def _rgba(h: str, a: float) -> str:
    h = h.lstrip("#")
    if len(h) == 6:
        r,g,b = int(h[:2],16),int(h[2:4],16),int(h[4:],16)
        return f"rgba({r},{g},{b},{a:.2f})"
    return h

_PRIORITY_C = {ProjectPriority.HIGH:_C["danger"], ProjectPriority.MEDIUM:_C["warning"], ProjectPriority.LOW:_C["success"]}
_STATUS_C   = {ProjectStatus.ACTIVE:_C["success"], ProjectStatus.COMPLETED:_C["accent"],
               ProjectStatus.ON_HOLD:_C["warning"], ProjectStatus.ARCHIVED:_C["text_lo"]}

GAME_SYSTEMS = ["","Warhammer 40,000","Age of Sigmar","The Old World","Horus Heresy",
                "Warcry","Kill Team","Dungeons & Dragons","Pathfinder","Frostgrave",
                "Gundam","Star Wars Legion","Other"]
PROJECT_ICONS = ["📁","⚔","🛡","🤖","🧙","🐉","🏰","🚀","💀","🎲","🎨","📖","🏔","🚗","👤","🗂"]

# ── Reusable helpers ───────────────────────────────────────────────────────────

def _sep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine); f.setFixedHeight(1)
    f.setStyleSheet(f"background:{_C['border_lo']};border:none;"); return f

def _vspace(h:int) -> QWidget:
    w = QWidget(); w.setFixedHeight(h); w.setStyleSheet("background:transparent;"); return w

def _lbl(text:str, size:str="base", color:str="", bold:bool=False) -> QLabel:
    l = QLabel(text); c = color or _C["text_mid"]
    l.setStyleSheet(f"font-size:{_FS[size]};color:{c};font-weight:{'600' if bold else '400'};background:transparent;")
    return l

def _section_hdr(text:str) -> QLabel:
    l = QLabel(text.upper())
    l.setStyleSheet(f"font-size:{_FS['xs']};color:{_C['text_dim']};font-weight:600;"
                    f"letter-spacing:0.08em;background:transparent;")
    return l

def _badge(text:str, bg:str, fg:str=_C["text_hi"]) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(f"background:{bg};color:{fg};border-radius:{_R['pill']};"
                    f"padding:2px 7px;font-size:{_FS['xs']};font-weight:600;")
    l.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return l

def _pbar(pct:int, color:str="", height:int=5) -> QProgressBar:
    c = color or _C["accent"]
    b = QProgressBar(); b.setRange(0,100); b.setValue(max(0,min(100,pct)))
    b.setFixedHeight(height); b.setTextVisible(False)
    b.setStyleSheet(f"QProgressBar{{background:{_rgba(c,0.15)};border:none;border-radius:{height//2}px;}}"
                    f"QProgressBar::chunk{{background:{c};border-radius:{height//2}px;}}")
    return b

def _icon_btn(text:str, tip:str="", danger:bool=False, sz:int=28) -> QPushButton:
    b = QPushButton(text); b.setFixedSize(sz,sz); b.setToolTip(tip)
    c  = _C["danger"]    if danger else _C["text_lo"]
    ch = _C["danger"]    if danger else _C["text_mid"]
    b.setStyleSheet(f"QPushButton{{background:transparent;color:{c};border:none;"
                    f"border-radius:{_R['sm']};font-size:13px;}}"
                    f"QPushButton:hover{{background:{_rgba(_C['border_hi'],0.6)};color:{ch};}}"
                    f"QPushButton:pressed{{background:{_rgba(_C['border_hi'],0.9)};}}")
    return b

def _btn(text:str, accent:bool=False, danger:bool=False, small:bool=False,
         primary:bool=False) -> QPushButton:
    b = QPushButton(text); h = 28 if small else 32; b.setFixedHeight(h)
    if accent or primary:
        bg,bgh,col,bd = _C["accent"],_C["accent_hi"],_C["text_hi"],_C["accent"]
    elif danger:
        bg = _rgba(_C["danger"],0.12); bgh = _rgba(_C["danger"],0.22)
        col = _C["danger"]; bd = _rgba(_C["danger"],0.4)
    else:
        bg,bgh,col,bd = _C["bg_raised"],_C["bg_hover"],_C["text_mid"],_C["border_hi"]
    b.setStyleSheet(f"QPushButton{{background:{bg};color:{col};"
                    f"border:1px solid {bd};border-radius:{_R['base']};"
                    f"font-size:{_FS['sm']};font-weight:500;padding:0 12px;}}"
                    f"QPushButton:hover{{background:{bgh};}}"
                    f"QPushButton:pressed{{background:{_C['bg_input']};}}"
                    f"QPushButton:disabled{{opacity:0.35;}}")
    return b

def _scroll_area(widget:QWidget) -> QScrollArea:
    sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(widget)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    sa.setStyleSheet(f"QScrollArea{{background:transparent;border:none;}}"
                     f"QScrollBar:vertical{{background:transparent;width:5px;margin:0;}}"
                     f"QScrollBar::handle:vertical{{background:{_C['border']};border-radius:2px;min-height:30px;}}"
                     f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}"
                     f"QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:transparent;}}")
    return sa

_INPUT_SS = (
    # All text inputs share one base style
    f"QLineEdit,QTextEdit,QSpinBox,QDateEdit,QComboBox{{"
    f"background:{_C['bg_input']};color:{_C['text_hi']};"
    f"border:1px solid {_C['border']};border-radius:{_R['base']};"
    f"font-size:{_FS['base']};padding:5px 8px;}}"
    f"QLineEdit:focus,QTextEdit:focus,QSpinBox:focus,QDateEdit:focus,QComboBox:focus{{"
    f"border-color:{_C['accent']};background:{_C['bg_hover']};}}"
    f"QLineEdit:hover,QTextEdit:hover,QSpinBox:hover,QDateEdit:hover,QComboBox:hover{{"
    f"border-color:{_C['border_hi']};}}"
    f"QComboBox{{min-height:28px;}}"
    # Completely hide the drop-down zone and arrow on ALL picker controls
    f"QComboBox::drop-down,QDateEdit::drop-down{{"
    f"width:0px;border:none;background:transparent;}}"
    f"QComboBox::down-arrow,QDateEdit::down-arrow{{image:none;width:0px;height:0px;}}"
    # Dropdown list popup
    f"QComboBox QAbstractItemView{{"
    f"background:{_C['bg_card']};color:{_C['text_hi']};"
    f"border:1px solid {_C['border']};"
    f"selection-background-color:{_C['accent_lo']};selection-color:{_C['accent_text']};"
    f"outline:none;padding:4px;}}"
    # Spinner buttons
    f"QSpinBox::up-button,QSpinBox::down-button{{"
    f"width:18px;background:{_C['bg_raised']};border:none;}}"
)

_DLG_SS = (
    f"QDialog{{background:{_C['bg_card']};color:{_C['text_hi']};}}"
    # All plain QWidgets inside dialogs get the card background (prevents black bars)
    f"QWidget{{background:{_C['bg_card']};}}"
    f"QLabel{{background:transparent;color:{_C['text_mid']};}}"
    f"QCheckBox{{background:transparent;color:{_C['text_mid']};font-size:{_FS['sm']};}}"
    f"QCheckBox::indicator{{width:15px;height:15px;"
    f"border:1px solid {_C['border_hi']};border-radius:3px;background:{_C['bg_input']};}}"
    f"QCheckBox::indicator:checked{{background:{_C['accent']};border-color:{_C['accent']};}}"
    + _INPUT_SS +
    f"QDialogButtonBox QPushButton{{background:{_C['bg_card']};color:{_C['text_mid']};"
    f"border:1px solid {_C['border']};border-radius:{_R['base']};padding:6px 20px;"
    f"font-size:{_FS['sm']};font-weight:500;}}"
    f"QDialogButtonBox QPushButton:hover{{background:{_C['bg_hover']};"
    f"border-color:{_C['border_hi']};color:{_C['text_hi']};}}"
)


# ── Circular progress ring ─────────────────────────────────────────────────────
class _Ring(QWidget):
    def __init__(self, pct:int=0, color:str="", size:int=64, label:str="", parent=None):
        super().__init__(parent); self._pct = pct
        self._color = color or _C["accent"]; self._label = label
        self.setFixedSize(size,size)
    def set(self, pct:int): self._pct=pct; self.update()
    def paintEvent(self,_):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m=6; r=self.rect().adjusted(m,m,-m,-m); s=min(self.width(),self.height())
        pen=QPen(QColor(_rgba(self._color,0.12))); pen.setWidth(5)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap); p.setPen(pen); p.drawArc(r,0,360*16)
        if self._pct>0:
            pen2=QPen(QColor(self._color)); pen2.setWidth(5)
            pen2.setCapStyle(Qt.PenCapStyle.RoundCap); p.setPen(pen2)
            p.drawArc(r,90*16,-int(min(self._pct,100)/100*360*16))
        p.setPen(QColor(_C["text_hi"]))
        f=QFont(); f.setPixelSize(max(8,s//5)); f.setBold(True); p.setFont(f)
        p.drawText(r,Qt.AlignmentFlag.AlignCenter,f"{self._pct}%"); p.end()


# ── Eliding label ─────────────────────────────────────────────────────────────
class _ElidedLabel(QLabel):
    """QLabel that truncates text with '…' rather than silently clipping."""
    def __init__(self, text:str="", parent=None):
        super().__init__(parent)
        self._full = text
        super().setText(text)

    def setFullText(self, text:str):
        self._full = text
        self._update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update()

    def _update(self):
        w = self.width()
        if w < 4:
            return
        elided = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideRight, w - 4)
        super().setText(elided)


# ── Project card (sidebar) ─────────────────────────────────────────────────────
class _ProjectCard(QFrame):
    clicked = Signal(int)
    def __init__(self, project:Project, stats=None, parent=None):
        super().__init__(parent)
        self.project_id = project.id
        self._color     = project.color or _C["accent"]
        self._selected  = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setObjectName(f"pcard{project.id}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        row = QWidget(); row.setObjectName(f"pcardrow{project.id}")
        rl  = QHBoxLayout(row); rl.setContentsMargins(0,0,10,0); rl.setSpacing(0)

        # Color stripe
        stripe = QFrame(); stripe.setFixedWidth(3)
        stripe.setObjectName(f"pcardstripe{project.id}")
        stripe.setStyleSheet(f"QFrame#{f'pcardstripe{project.id}'}{{background:{self._color};"
                             f"border-radius:2px;margin:10px 0 10px 8px;}}")
        rl.addWidget(stripe); rl.addSpacing(10)

        # Text
        tc = QVBoxLayout(); tc.setSpacing(3); tc.setContentsMargins(0,10,0,10)
        self._name_lbl = _ElidedLabel(f"{project.icon}  {project.name}")
        self._name_lbl.setStyleSheet(f"font-size:{_FS['lg']};color:{_C['text_hi']};"
                                      "font-weight:600;background:transparent;")
        self._name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self._name_lbl.setMinimumWidth(0)
        tc.addWidget(self._name_lbl)
        ms_done  = getattr(stats,"milestones_done",0)  if stats else 0
        ms_total = getattr(stats,"milestones_total",0) if stats else 0
        hours    = getattr(stats,"total_hours",0)       if stats else 0
        parts = []
        if project.game_system: parts.append(project.game_system)
        if ms_total: parts.append(f"{ms_done}/{ms_total} milestones")
        if hours:    parts.append(f"{hours}h")
        sub = QLabel("  ·  ".join(parts) if parts else ProjectStatus.LABELS.get(project.status,""))
        sub.setStyleSheet(f"font-size:{_FS['xs']};color:{_C['text_lo']};background:transparent;")
        tc.addWidget(sub)
        rl.addLayout(tc,1)

        # Status pill
        sc  = _STATUS_C.get(project.status,_C["text_lo"])
        bgl = _badge(ProjectStatus.LABELS.get(project.status,project.status), _rgba(sc,0.15), sc)
        rl.addWidget(bgl)
        outer.addWidget(row,1)

        # Progress bar at bottom
        if ms_total:
            pct = int(getattr(stats,"milestone_progress",0)*100)
            pb  = _pbar(pct, self._color, 3)
            outer.addWidget(pb)

        self._apply_style()

    def _apply_style(self):
        oid = f"pcard{self.project_id}"
        if self._selected:
            bg,bd = _C["bg_selected"], _C["accent"]
        else:
            bg,bd = _C["bg_card"], _C["border_lo"]
        self.setStyleSheet(f"QFrame#{oid}{{background:{bg};border-radius:{_R['lg']};"
                           f"border:1px solid {bd};}}"
                           f"QFrame#{oid}:hover{{background:{_C['bg_hover']};"
                           f"border-color:{_C['border']};}}")

    def set_selected(self, s:bool):
        self._selected = s; self._apply_style()

    def mousePressEvent(self,e):
        super().mousePressEvent(e)
        if e.button()==Qt.MouseButton.LeftButton: self.clicked.emit(self.project_id)


# ── Sidebar ────────────────────────────────────────────────────────────────────
class _SidebarPanel(QWidget):
    project_selected      = Signal(int)
    new_project_requested = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self._ctx = ctx; self._cards:dict[int,_ProjectCard]={}
        self._selected_id:Optional[int]=None; self._search=""
        self.setMinimumWidth(300)
        self.setObjectName("sidebarPanel")
        # Scope style to this widget only — prevents border cascading into cards
        self.setStyleSheet(f"QWidget#sidebarPanel{{background:{_C['bg_deep']};}}")
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget(); hdr.setObjectName("sidebarHdr"); hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"QWidget#sidebarHdr{{background:{_C['bg_deep']};"
                          f"border-bottom:1px solid {_C['border']};}}")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(16,0,12,0); hl.setSpacing(0)
        t = QLabel("Projects")
        t.setStyleSheet(f"color:{_C['text_hi']};font-size:{_FS['xl']};font-weight:700;"
                        f"background:transparent;border:none;")
        hl.addWidget(t, 1)
        # QToolButton respects setFixedSize on all platforms unlike QPushButton
        nb = QToolButton()
        nb.setText("+")
        nb.setFixedSize(26, 26)
        nb.setToolTip("New project")
        nb.setStyleSheet(
            f"QToolButton{{background:{_C['accent']};color:{_C['text_hi']};border:none;"
            f"border-radius:13px;font-size:17px;font-weight:300;padding:0;}}"
            f"QToolButton:hover{{background:{_C['accent_hi']};}}"
            f"QToolButton:pressed{{background:{_C['accent']};}}")
        nb.clicked.connect(self.new_project_requested)
        hl.addWidget(nb)
        root.addWidget(hdr)

        # ── Search ────────────────────────────────────────────────────────────
        sw = QWidget(); sw.setObjectName("sidebarSearch")
        sw.setStyleSheet(f"QWidget#sidebarSearch{{background:{_C['bg_deep']};}}")
        sl = QHBoxLayout(sw); sl.setContentsMargins(12,10,12,6)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search projects...")
        self._search_edit.setFixedHeight(30)
        self._search_edit.setStyleSheet(
            f"QLineEdit{{background:{_C['bg_input']};color:{_C['text_hi']};"
            f"border:1px solid {_C['border']};border-radius:{_R['base']};"
            f"font-size:{_FS['sm']};padding:0 10px;}}"
            f"QLineEdit:focus{{border-color:{_C['accent']};}}")
        self._search_edit.textChanged.connect(self._on_search)
        sl.addWidget(self._search_edit)
        root.addWidget(sw)

        # ── Filter — QPushButton + QMenu (no native QComboBox) ────────────────
        self._filter_labels = ["All Projects","Active","On Hold","Completed","Archived"]
        self._filter_vals   = ["","active","on_hold","completed","archived"]
        fw = QWidget(); fw.setObjectName("sidebarFilter")
        fw.setStyleSheet(f"QWidget#sidebarFilter{{background:{_C['bg_deep']};}}")
        fl = QHBoxLayout(fw); fl.setContentsMargins(12,4,12,10)
        self._filter_btn = QPushButton(f"{self._filter_labels[0]}  ▾")
        self._filter_btn.setFixedHeight(30)
        self._filter_btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']};color:{_C['text_hi']};"
            f"border:1px solid {_C['border_hi']};border-radius:{_R['base']};"
            f"font-size:{_FS['sm']};font-weight:400;text-align:left;padding:0 10px;}}"
            f"QPushButton:hover{{border-color:{_C['accent']};}}"
            f"QPushButton:pressed{{background:{_C['bg_input']};}}")
        self._filter_btn.clicked.connect(self._show_filter_menu)
        fl.addWidget(self._filter_btn)
        root.addWidget(fw)

        root.addWidget(_sep())

        # ── List ──────────────────────────────────────────────────────────────
        self._list_body = QWidget(); self._list_body.setObjectName("sidebarList")
        self._list_body.setStyleSheet(f"QWidget#sidebarList{{background:{_C['bg_deep']};}}")
        self._list_lay  = QVBoxLayout(self._list_body)
        self._list_lay.setContentsMargins(12,8,12,10); self._list_lay.setSpacing(6)
        self._list_lay.addStretch()
        root.addWidget(_scroll_area(self._list_body),1)

    def _on_search(self, t:str):
        self._search=t.lower(); self._refilter()

    def _show_filter_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{_C['bg_raised']};color:{_C['text_hi']};"
            f"border:1px solid {_C['border_hi']};border-radius:{_R['base']};padding:4px;}}"
            f"QMenu::item{{padding:8px 16px;font-size:{_FS['sm']};}}"
            f"QMenu::item:selected{{background:{_C['accent']};color:{_C['text_hi']};"
            f"border-radius:{_R['sm']};}}")
        for i, label in enumerate(self._filter_labels):
            act = menu.addAction(label)
            act.setData(i)
        chosen = menu.exec(self._filter_btn.mapToGlobal(
            self._filter_btn.rect().bottomLeft()))
        if chosen:
            idx = chosen.data()
            self._filter_btn.setText(f"{self._filter_labels[idx]}  ▾")
            val = self._filter_vals[idx]
            self._ctx.event_bus.emit("project_filter_changed",{"status":val or None})

    def _refilter(self):
        for pid,card in self._cards.items():
            name=card._name_lbl.text().lower()
            card.setVisible(not self._search or self._search in name)

    def populate(self, projects:list, stats_map:dict):
        for c in list(self._cards.values()):
            self._list_lay.removeWidget(c); c.deleteLater()
        self._cards.clear()
        for p in projects:
            card=_ProjectCard(p,stats_map.get(p.id))
            card.clicked.connect(self._on_card_clicked)
            self._list_lay.insertWidget(self._list_lay.count()-1,card)
            self._cards[p.id]=card
        if self._selected_id and self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(True)
        self._refilter()

    def _on_card_clicked(self, pid:int):
        self.select_project(pid); self.project_selected.emit(pid)

    def select_project(self, pid:int):
        if self._selected_id and self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(False)
        self._selected_id=pid
        if pid in self._cards: self._cards[pid].set_selected(True)


# ── Live session banner ────────────────────────────────────────────────────────
class _SessionBanner(QWidget):
    end_clicked = Signal()
    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedHeight(44)
        self.setStyleSheet(f"background:{_rgba(_C['success'],0.08)};"
                           f"border-bottom:1px solid {_rgba(_C['success'],0.2)};")
        lay = QHBoxLayout(self); lay.setContentsMargins(18,0,14,0); lay.setSpacing(10)
        dot = QFrame(); dot.setFixedSize(8,8)
        dot.setStyleSheet(f"background:{_C['success']};border-radius:4px;")
        lay.addWidget(dot)
        lbl = QLabel("Live session in progress")
        lbl.setStyleSheet(f"font-size:{_FS['base']};color:{_C['success']};font-weight:600;background:transparent;")
        lay.addWidget(lbl,1)
        self._tlbl = QLabel("00:00")
        self._tlbl.setStyleSheet(f"font-size:{_FS['lg']};color:{_C['success']};font-weight:700;background:transparent;")
        lay.addWidget(self._tlbl)
        eb = _btn("End Session", danger=True, small=True); eb.clicked.connect(self.end_clicked)
        lay.addWidget(eb)
        self._timer=QTimer(self); self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._start_dt:Optional[datetime]=None
    def start(self, started_at:Optional[str]=None):
        if started_at:
            try:
                dt=datetime.fromisoformat(started_at.replace("Z","+00:00"))
                self._start_dt=dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            except: self._start_dt=None
        else: self._start_dt=None
        self._timer.start(); self.show()
    def stop(self): self._timer.stop(); self.hide()
    def _tick(self):
        if self._start_dt:
            secs=max(0,int((datetime.now(timezone.utc)-self._start_dt).total_seconds()))
        else: secs=0
        h,r=divmod(secs,3600); m,s=divmod(r,60)
        self._tlbl.setText(f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}")


# ── Overview tab ───────────────────────────────────────────────────────────────
class _StatCard(QFrame):
    def __init__(self, icon:str, value:str, label:str, color:str="", parent=None):
        super().__init__(parent)
        c = color or _C["accent_text"]
        self.setObjectName("statcard")
        self.setStyleSheet(f"QFrame#statcard{{background:{_C['bg_raised']};"
                           f"border:1px solid {_C['border']};border-radius:{_R['xl']};}}")
        lay = QVBoxLayout(self); lay.setContentsMargins(18,16,18,16); lay.setSpacing(6)
        top = QHBoxLayout()
        ic  = QLabel(icon); ic.setStyleSheet(f"font-size:20px;background:transparent;")
        top.addWidget(ic); top.addStretch()
        lay.addLayout(top)
        vl = QLabel(value)
        vl.setStyleSheet(f"font-size:{_FS['2xl']};color:{c};font-weight:700;background:transparent;")
        lay.addWidget(vl)
        ll = QLabel(label)
        ll.setStyleSheet(f"font-size:{_FS['sm']};color:{_C['text_lo']};background:transparent;")
        lay.addWidget(ll)


class _OverviewTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent); self._ctx=ctx
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        body=QWidget(); body.setStyleSheet(f"background:{_C['bg_base']};")
        self._lay=QVBoxLayout(body); self._lay.setContentsMargins(20,20,20,20); self._lay.setSpacing(20)
        lay.addWidget(_scroll_area(body))

    def populate(self, project:Project, stats, milestones:list, sessions:list):
        while self._lay.count():
            it=self._lay.takeAt(0);
            if it.widget(): it.widget().deleteLater()

        hours   = getattr(stats,"total_hours",0)    if stats else 0
        sess_n  = getattr(stats,"total_sessions",0) if stats else 0
        ms_done = getattr(stats,"milestones_done",0) if stats else 0
        ms_tot  = getattr(stats,"milestones_total",0) if stats else 0
        mdl_p   = getattr(stats,"painted_models",0)  if stats else 0
        mdl_t   = (getattr(stats,"total_model_count",0) or getattr(stats,"total_models",0)) if stats else 0

        # ── Description ───────────────────────────────────────────────────────
        if project.description or getattr(project,"tags",[]):
            desc_card = QFrame(); desc_card.setObjectName("desccard")
            desc_card.setStyleSheet(f"QFrame#desccard{{background:{_C['bg_card']};"
                                    f"border:1px solid {_C['border']};border-radius:{_R['xl']};}}")
            dcl = QVBoxLayout(desc_card); dcl.setContentsMargins(16,14,16,14); dcl.setSpacing(8)
            if project.description:
                dl = QLabel(project.description); dl.setWordWrap(True)
                dl.setStyleSheet(f"font-size:{_FS['base']};color:{_C['text_mid']};background:transparent;")
                dcl.addWidget(dl)
            tags = getattr(project,"tags",[]) or []
            if tags:
                tr=QHBoxLayout(); tr.setSpacing(6)
                for t in tags[:12]:
                    tr.addWidget(_badge(f"#{t}",_rgba(_C["accent"],0.15),_C["accent_text"]))
                tr.addStretch(); dcl.addLayout(tr)
            self._lay.addWidget(desc_card)

        # ── Stat cards (2×2 grid) ─────────────────────────────────────────────
        grid=QWidget(); grid.setStyleSheet("background:transparent;")
        gl=QGridLayout(grid); gl.setContentsMargins(0,0,0,0); gl.setSpacing(10)
        tiles=[
            ("⏱",f"{hours:.1f}h","Time Logged",_C["accent_text"]),
            ("📅",str(sess_n),"Sessions",_C["success"]),
            (f"✅",f"{ms_done}/{ms_tot}" if ms_tot else "—","Milestones",_C["warning"]),
            ("🎨",f"{mdl_p}/{mdl_t}" if mdl_t else "—","Models Painted",_C["gold"]),
        ]
        for i,(ic,val,label,col) in enumerate(tiles):
            gl.addWidget(_StatCard(ic,val,label,col), 0, i)
        self._lay.addWidget(grid)

        # ── Milestone progress ────────────────────────────────────────────────
        if ms_tot:
            pct=int(getattr(stats,"milestone_progress",0)*100)
            pf=QFrame(); pf.setObjectName("progcard")
            pf.setStyleSheet(f"QFrame#progcard{{background:{_C['bg_card']};"
                             f"border:1px solid {_C['border']};border-radius:{_R['xl']};}}")
            pfl=QVBoxLayout(pf); pfl.setContentsMargins(16,14,16,16); pfl.setSpacing(10)
            rw=QHBoxLayout()
            rw.addWidget(_section_hdr("Milestone Progress"))
            rw.addStretch()
            pc=QLabel(f"{pct}%")
            pc.setStyleSheet(f"font-size:{_FS['base']};color:{_C['accent_text']};font-weight:700;background:transparent;")
            rw.addWidget(pc); pfl.addLayout(rw)
            pfl.addWidget(_pbar(pct,_C["accent"],8))
            mi=QLabel(f"{ms_done} of {ms_tot} milestones complete")
            mi.setStyleSheet(f"font-size:{_FS['xs']};color:{_C['text_lo']};background:transparent;")
            pfl.addWidget(mi); self._lay.addWidget(pf)

        # ── Focus milestone ───────────────────────────────────────────────────
        focus=next((m for m in milestones if m.is_focus and not m.is_complete),None)
        if focus:
            ff=QFrame(); ff.setObjectName("focuscard")
            ff.setStyleSheet(f"QFrame#focuscard{{background:{_rgba(_C['gold'],0.07)};"
                             f"border:1px solid {_rgba(_C['gold'],0.25)};border-radius:{_R['xl']};}}")
            ffl=QVBoxLayout(ff); ffl.setContentsMargins(16,14,16,14); ffl.setSpacing(6)
            hr=QHBoxLayout()
            hr.addWidget(_lbl("⭐  Focus Milestone","sm",_C["gold"]))
            hr.addStretch()
            if focus.due_date:
                try:
                    d=date.fromisoformat(focus.due_date); diff=(d-date.today()).days
                    c=_C["danger"] if diff<0 else _C["warning"] if diff<7 else _C["text_lo"]
                    hr.addWidget(_lbl(f"Due {focus.due_date}","xs",c))
                except: hr.addWidget(_lbl(focus.due_date,"xs",_C["text_lo"]))
            ffl.addLayout(hr)
            tl=QLabel(focus.title); tl.setWordWrap(True)
            tl.setStyleSheet(f"font-size:{_FS['lg']};color:{_C['text_hi']};font-weight:600;background:transparent;")
            ffl.addWidget(tl)
            if focus.has_quantity:
                ffl.addWidget(_pbar(int(focus.quantity_progress*100),_C["gold"],5))
                ffl.addWidget(_lbl(f"{focus.quantity_done} / {focus.quantity_total} done","xs",_C["text_lo"]))
            self._lay.addWidget(ff)

        # ── Target date ───────────────────────────────────────────────────────
        if project.target_date:
            try:
                d=date.fromisoformat(project.target_date); diff=(d-date.today()).days
                if diff>=0: txt,col=f"🎯  Target: {project.target_date}  ·  {diff} days remaining",\
                                    (_C["warning"] if diff<14 else _C["text_lo"])
                else:       txt,col=f"⚠  Target {project.target_date} overdue by {-diff} days",_C["danger"]
                tl=QLabel(txt)
                tl.setStyleSheet(f"font-size:{_FS['sm']};color:{col};background:transparent;padding:4px 0;")
                self._lay.addWidget(tl)
            except: pass

        # ── Recent sessions ───────────────────────────────────────────────────
        done=[s for s in sessions if not s.is_active][:5]
        if done:
            sf=QFrame(); sf.setObjectName("sesscard")
            sf.setStyleSheet(f"QFrame#sesscard{{background:{_C['bg_card']};"
                             f"border:1px solid {_C['border']};border-radius:{_R['xl']};}}")
            sfl=QVBoxLayout(sf); sfl.setContentsMargins(16,14,16,14); sfl.setSpacing(10)
            sfl.addWidget(_section_hdr("Recent Sessions"))
            for s in done:
                sr=QHBoxLayout(); sr.setSpacing(14)
                dt=""
                if s.started_at:
                    try: dt=datetime.fromisoformat(s.started_at.replace("Z","+00:00")).strftime("%b %d")
                    except: dt=s.started_at[:10]
                h,rem=divmod(s.duration_minutes,60); m=rem
                dur=f"{h}h {m}m" if h else f"{m}m"
                sr.addWidget(_lbl(dt,"sm",_C["text_lo"]))
                dl=QLabel(dur)
                dl.setStyleSheet(f"font-size:{_FS['sm']};color:{_C['accent_text']};font-weight:700;background:transparent;")
                sr.addWidget(dl)
                note=(s.notes or s.outcome or "")[:70]
                if note:
                    nl=QLabel(note); nl.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
                    nl.setStyleSheet(f"font-size:{_FS['xs']};color:{_C['text_dim']};background:transparent;")
                    sr.addWidget(nl,1)
                else: sr.addStretch(1)
                sfl.addLayout(sr)
            self._lay.addWidget(sf)

        self._lay.addStretch()


# ── Milestones tab ─────────────────────────────────────────────────────────────
class _MilestoneRow(QFrame):
    toggled          = Signal(int)
    edit_requested   = Signal(int)
    delete_requested = Signal(int)
    focus_toggled    = Signal(int)
    qty_step         = Signal(int,int)

    def __init__(self, m:Milestone, parent=None):
        super().__init__(parent); self._m=m
        self.setFixedHeight(52 if not m.has_quantity else 66)
        oid=f"msrow{m.id}"; self.setObjectName(oid)
        if m.is_complete:    bg,bd=_rgba(_C["success"],0.04),_C["border_lo"]
        elif m.is_focus:     bg,bd=_rgba(_C["gold"],0.06),_rgba(_C["gold"],0.2)
        elif m.is_overdue:   bg,bd=_rgba(_C["danger"],0.05),_rgba(_C["danger"],0.2)
        else:                bg,bd=_C["bg_card"],_C["border_lo"]
        self.setStyleSheet(f"QFrame#{oid}{{background:{bg};border:1px solid {bd};"
                           f"border-radius:{_R['base']};}}")
        lay=QHBoxLayout(self); lay.setContentsMargins(14,0,8,0); lay.setSpacing(10)

        # Circle check indicator
        chk=QPushButton()
        chk.setFixedSize(18,18); chk.setToolTip("Toggle complete")
        if m.is_complete:
            chk.setText("✓")
            chk.setStyleSheet(f"QPushButton{{background:{_C['accent']};color:{_C['text_hi']};border:none;"
                              f"border-radius:9px;font-size:9px;font-weight:700;}}"
                              f"QPushButton:hover{{background:{_C['accent_hi']};}}")
        else:
            chk.setText("")
            chk.setStyleSheet(f"QPushButton{{background:transparent;border:2px solid {_C['border_hi']};"
                              f"border-radius:9px;}}"
                              f"QPushButton:hover{{border-color:{_C['accent']};background:{_rgba(_C['accent'],0.1)};}}")
        chk.clicked.connect(lambda: self.toggled.emit(m.id))
        lay.addWidget(chk)

        # Content
        col=QVBoxLayout(); col.setSpacing(2); col.setContentsMargins(0,8,0,8)
        title_row=QHBoxLayout(); title_row.setSpacing(6)
        tl=QLabel(m.title)
        tc=_C["text_dim"] if m.is_complete else _C["text_hi"]
        tl.setStyleSheet(f"font-size:{_FS['base']};color:{tc};"
                         f"{'text-decoration:line-through;' if m.is_complete else ''}"
                         f"font-weight:500;background:transparent;")
        title_row.addWidget(tl,1)
        if m.is_focus: title_row.addWidget(_lbl("⭐","xs",_C["gold"]))
        pri=m.priority; pc=_PRIORITY_C.get(pri,"")
        if pc and pri!=ProjectPriority.MEDIUM:
            pd=QFrame(); pd.setFixedSize(6,6)
            pd.setStyleSheet(f"background:{pc};border-radius:3px;border:none;")
            title_row.addWidget(pd)
        col.addLayout(title_row)

        # Sub-labels
        sub_parts=[]
        if m.due_date and not m.is_complete:
            try:
                d=date.fromisoformat(m.due_date); diff=(d-date.today()).days
                if diff<0:    sub_parts.append(_lbl(f"Overdue {-diff}d","xs",_C["danger"]))
                elif diff==0: sub_parts.append(_lbl("Due today","xs",_C["warning"]))
                elif diff<=7: sub_parts.append(_lbl(f"Due in {diff}d","xs",_C["warning"]))
                else:         sub_parts.append(_lbl(m.due_date,"xs",_C["text_dim"]))
            except: sub_parts.append(_lbl(m.due_date,"xs",_C["text_dim"]))
        if sub_parts:
            sr=QHBoxLayout(); sr.setSpacing(8); sr.setContentsMargins(0,0,0,0)
            for sl in sub_parts: sr.addWidget(sl)
            sr.addStretch(); col.addLayout(sr)
        lay.addLayout(col,1)

        # Quantity stepper
        if m.has_quantity:
            qw=QWidget(); qw.setStyleSheet("background:transparent;")
            ql=QHBoxLayout(qw); ql.setContentsMargins(0,0,0,0); ql.setSpacing(2)
            dm=_icon_btn("−","",sz=22); dm.clicked.connect(lambda: self.qty_step.emit(m.id,-1))
            ql.addWidget(dm)
            qt=QLabel(f"{m.quantity_done}/{m.quantity_total}")
            qt.setFixedWidth(44)
            qt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qt.setStyleSheet(f"font-size:{_FS['xs']};color:{_C['text_mid']};background:transparent;")
            ql.addWidget(qt)
            pm=_icon_btn("＋","",sz=22); pm.clicked.connect(lambda: self.qty_step.emit(m.id,+1))
            ql.addWidget(pm); lay.addWidget(qw)

        # Actions
        focus_ic="⭐" if m.is_focus else "☆"
        fb=_icon_btn(focus_ic,"Toggle focus",sz=24); fb.clicked.connect(lambda: self.focus_toggled.emit(m.id))
        eb=_icon_btn("✎","Edit",sz=24); eb.clicked.connect(lambda: self.edit_requested.emit(m.id))
        db=_icon_btn("✕","Delete",danger=True,sz=24); db.clicked.connect(lambda: self.delete_requested.emit(m.id))
        lay.addWidget(fb); lay.addWidget(eb); lay.addWidget(db)


class _MilestonesTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent); self._ctx=ctx; self._project_id:Optional[int]=None
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        # Quick-add bar
        qa=QWidget(); qa.setFixedHeight(52)
        qa.setStyleSheet(f"background:{_C['bg_base']};border-bottom:1px solid {_C['border']};")
        ql=QHBoxLayout(qa); ql.setContentsMargins(14,10,14,10); ql.setSpacing(8)
        self._qi=QLineEdit(); self._qi.setPlaceholderText("  ＋  Type a milestone title and press Enter to add…")
        self._qi.setStyleSheet(
            f"QLineEdit{{background:{_C['bg_input']};color:{_C['text_hi']};"
            f"border:1px solid {_C['border']};border-radius:{_R['pill']};"
            f"font-size:{_FS['base']};padding:6px 14px;}}"
            f"QLineEdit:focus{{border-color:{_C['accent']};}}")
        self._qi.returnPressed.connect(self._quick_add)
        ql.addWidget(self._qi,1)
        fb=_btn("Full Form",small=True); fb.clicked.connect(self._add_full)
        ql.addWidget(fb); lay.addWidget(qa)

        self._body=QWidget(); self._body.setStyleSheet(f"background:{_C['bg_base']};")
        self._blay=QVBoxLayout(self._body)
        self._blay.setContentsMargins(16,16,16,16); self._blay.setSpacing(5)
        self._blay.addStretch()
        lay.addWidget(_scroll_area(self._body),1)

    def populate(self, project_id:int, milestones:list):
        self._project_id=project_id
        while self._blay.count():
            it=self._blay.takeAt(0);
            if it.widget(): it.widget().deleteLater()

        incomplete=[m for m in milestones if not m.is_complete]
        complete  =[m for m in milestones if m.is_complete]
        pri_ord   ={ProjectPriority.HIGH:0,ProjectPriority.MEDIUM:1,ProjectPriority.LOW:2}
        incomplete.sort(key=lambda m:(not m.is_focus,pri_ord.get(m.priority,1),m.order_index))

        for m in incomplete: self._add_row(m)

        if complete:
            self._blay.addSpacing(12)
            self._blay.addWidget(_section_hdr(f"Completed  ({len(complete)})"))
            self._blay.addSpacing(4)
            for m in complete: self._add_row(m)

        if not milestones:
            el=_lbl("No milestones yet — add one above","base",_C["text_dim"])
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.setContentsMargins(0,50,0,0); self._blay.addWidget(el)
        self._blay.addStretch()

    def _add_row(self, m:Milestone):
        row=_MilestoneRow(m)
        row.toggled.connect(lambda mid: self._ctx.event_bus.emit("project_milestone_toggle",{"id":mid}))
        row.edit_requested.connect(self._edit)
        row.delete_requested.connect(lambda mid: self._ctx.event_bus.emit("project_milestone_delete",{"id":mid}))
        row.focus_toggled.connect(lambda mid: self._ctx.event_bus.emit("project_milestone_focus_toggle",{"id":mid}))
        row.qty_step.connect(lambda mid,d: self._ctx.event_bus.emit("project_milestone_quantity_step",{"id":mid,"delta":d}))
        self._blay.insertWidget(self._blay.count()-1,row)

    def _quick_add(self):
        t=self._qi.text().strip()
        if t and self._project_id:
            self._ctx.event_bus.emit("project_milestone_add",{"project_id":self._project_id,"title":t})
            self._qi.clear()

    def _add_full(self):
        if not self._project_id: return
        dlg=_MilestoneDialog(self._project_id,None,self)
        if dlg.exec():
            self._ctx.event_bus.emit("project_milestone_add",{"project_id":self._project_id,**dlg.get_values()})

    def _edit(self, mid:int):
        svc=self._ctx.services.try_get("project_service")
        if not svc: return
        m=svc.get_milestone(mid)
        if not m: return
        dlg=_MilestoneDialog(self._project_id,m,self)
        if dlg.exec():
            self._ctx.event_bus.emit("project_milestone_update",{"id":mid,**dlg.get_values()})


# ── Sessions tab ───────────────────────────────────────────────────────────────
class _SessionRow(QFrame):
    delete_requested=Signal(int)
    def __init__(self, s:HobbySession, parent=None):
        super().__init__(parent)
        oid=f"srow{s.id}"; self.setObjectName(oid)
        self.setStyleSheet(f"QFrame#{oid}{{background:{_C['bg_card']};"
                           f"border:1px solid {_C['border_lo']};border-radius:{_R['base']};}}")
        lay=QHBoxLayout(self); lay.setContentsMargins(16,10,10,10); lay.setSpacing(14)
        dt=""
        if s.started_at:
            try: dt=datetime.fromisoformat(s.started_at.replace("Z","+00:00")).strftime("%b %d, %Y")
            except: dt=s.started_at[:10]
        dl=QLabel(dt); dl.setFixedWidth(96)
        dl.setStyleSheet(f"font-size:{_FS['sm']};color:{_C['text_lo']};background:transparent;")
        lay.addWidget(dl)
        h,rem=divmod(s.duration_minutes,60); m=rem
        dur=f"{h}h {m}m" if h else f"{m}m"
        durl=QLabel(dur); durl.setFixedWidth(60)
        durl.setStyleSheet(f"font-size:{_FS['base']};color:{_C['accent_text']};font-weight:700;background:transparent;")
        lay.addWidget(durl)
        note=" · ".join(p for p in [s.notes,s.outcome] if p)
        if note:
            nl=QLabel(note[:90]); nl.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
            nl.setStyleSheet(f"font-size:{_FS['sm']};color:{_C['text_mid']};background:transparent;")
            lay.addWidget(nl,1)
        else: lay.addStretch(1)
        db=_icon_btn("✕","Delete",danger=True,sz=24)
        db.clicked.connect(lambda: self.delete_requested.emit(s.id))
        lay.addWidget(db)


class _SessionsTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent); self._ctx=ctx
        self._project_id:Optional[int]=None; self._milestones:list=[]
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        ab=QWidget(); ab.setFixedHeight(52)
        ab.setStyleSheet(f"background:{_C['bg_base']};border-bottom:1px solid {_C['border']};")
        al=QHBoxLayout(ab); al.setContentsMargins(14,10,14,10); al.setSpacing(8)
        self._start_btn=_btn("▶  Start Session",accent=True,small=True)
        self._start_btn.clicked.connect(self._start)
        al.addWidget(self._start_btn)
        lb=_btn("＋  Log Session",small=True); lb.clicked.connect(self._log)
        al.addWidget(lb); al.addStretch()
        lay.addWidget(ab)

        self._body=QWidget(); self._body.setStyleSheet(f"background:{_C['bg_base']};")
        self._blay=QVBoxLayout(self._body)
        self._blay.setContentsMargins(16,16,16,16); self._blay.setSpacing(6)
        self._blay.addStretch()
        lay.addWidget(_scroll_area(self._body),1)

    def populate(self, project_id:int, sessions:list, milestones:list):
        self._project_id=project_id; self._milestones=milestones
        has_active=any(s.is_active for s in sessions)
        self._start_btn.setEnabled(not has_active)
        self._start_btn.setText("● Session Active" if has_active else "▶  Start Session")
        while self._blay.count():
            it=self._blay.takeAt(0);
            if it.widget(): it.widget().deleteLater()
        done=[s for s in sessions if not s.is_active]
        if done:
            for s in done:
                r=_SessionRow(s)
                r.delete_requested.connect(lambda sid: self._ctx.event_bus.emit("project_session_delete",{"id":sid}))
                self._blay.insertWidget(self._blay.count()-1,r)
        else:
            el=_lbl("No sessions logged yet","base",_C["text_dim"])
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.setContentsMargins(0,50,0,0); self._blay.addWidget(el)
        self._blay.addStretch()

    def _start(self):
        if self._project_id:
            self._ctx.event_bus.emit("project_session_start",{"project_id":self._project_id})
    def _log(self):
        if not self._project_id: return
        dlg=_LogSessionDialog(self._project_id,self._milestones,self)
        if dlg.exec():
            self._ctx.event_bus.emit("project_session_log",{"project_id":self._project_id,**dlg.get_values()})


# ── Notes tab ──────────────────────────────────────────────────────────────────
class _NoteCard(QFrame):
    edit_requested   = Signal(int)
    delete_requested = Signal(int)
    def __init__(self, note:ProjectNote, parent=None):
        super().__init__(parent); self._note=note
        oid=f"ncard{note.id}"; self.setObjectName(oid)
        self.setStyleSheet(f"QFrame#{oid}{{background:{_C['bg_card']};"
                           f"border:1px solid {_C['border_lo']};border-radius:{_R['lg']};}}"
                           f"QFrame#{oid}:hover{{border-color:{_C['border']};background:{_C['bg_raised']};}}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay=QVBoxLayout(self); lay.setContentsMargins(16,14,12,14); lay.setSpacing(6)
        top=QHBoxLayout(); top.setSpacing(6)
        tl=QLabel(note.title or "Untitled")
        tl.setStyleSheet(f"font-size:{_FS['base']};color:{_C['text_hi']};font-weight:600;background:transparent;")
        top.addWidget(tl,1)
        eb=_icon_btn("✎","Edit",sz=24); eb.clicked.connect(lambda: self.edit_requested.emit(note.id))
        db=_icon_btn("✕","Delete",danger=True,sz=24); db.clicked.connect(lambda: self.delete_requested.emit(note.id))
        top.addWidget(eb); top.addWidget(db); lay.addLayout(top)
        if note.content:
            cl=QLabel(note.content[:120].replace("\n"," ")+("…" if len(note.content)>120 else ""))
            cl.setWordWrap(True)
            cl.setStyleSheet(f"font-size:{_FS['sm']};color:{_C['text_lo']};background:transparent;")
            lay.addWidget(cl)
        if note.updated_at:
            lay.addWidget(_lbl(note.updated_at[:10],"xs",_C["text_dim"]))
    def mousePressEvent(self,e):
        super().mousePressEvent(e)
        if e.button()==Qt.MouseButton.LeftButton: self.edit_requested.emit(self._note.id)


class _NotesTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent); self._ctx=ctx; self._project_id:Optional[int]=None
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        ab=QWidget(); ab.setFixedHeight(52)
        ab.setStyleSheet(f"background:{_C['bg_base']};border-bottom:1px solid {_C['border']};")
        al=QHBoxLayout(ab); al.setContentsMargins(14,10,14,10)
        nb=_btn("＋  New Note",small=True); nb.clicked.connect(self._new)
        al.addWidget(nb); al.addStretch(); lay.addWidget(ab)
        self._body=QWidget(); self._body.setStyleSheet(f"background:{_C['bg_base']};")
        self._blay=QVBoxLayout(self._body)
        self._blay.setContentsMargins(16,16,16,16); self._blay.setSpacing(8)
        self._blay.addStretch()
        lay.addWidget(_scroll_area(self._body),1)

    def populate(self, project_id:int, notes:list):
        self._project_id=project_id
        while self._blay.count():
            it=self._blay.takeAt(0);
            if it.widget(): it.widget().deleteLater()
        if notes:
            for n in notes:
                c=_NoteCard(n)
                c.edit_requested.connect(self._edit)
                c.delete_requested.connect(lambda nid: self._ctx.event_bus.emit("project_note_delete",{"id":nid}))
                self._blay.insertWidget(self._blay.count()-1,c)
        else:
            el=_lbl("No notes yet","base",_C["text_dim"])
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.setContentsMargins(0,50,0,0); self._blay.addWidget(el)
        self._blay.addStretch()

    def _new(self):
        if not self._project_id: return
        dlg=_NoteDialog(None,self)
        if dlg.exec():
            self._ctx.event_bus.emit("project_note_add",{"project_id":self._project_id,**dlg.get_values()})

    def _edit(self, nid:int):
        svc=self._ctx.services.try_get("project_service")
        if not svc: return
        note=svc.get_note(nid)
        if not note: return
        dlg=_NoteDialog(note,self)
        if dlg.exec():
            self._ctx.event_bus.emit("project_note_update",{"id":nid,**dlg.get_values()})


# ── Gallery tab ────────────────────────────────────────────────────────────────
class _GalleryThumb(QFrame):
    delete_requested=Signal(int)
    def __init__(self, entry:GalleryEntry, parent=None):
        super().__init__(parent); self._entry=entry
        self.setFixedSize(156,168)
        oid=f"gthumb{entry.id}"; self.setObjectName(oid)
        self.setStyleSheet(f"QFrame#{oid}{{background:{_C['bg_card']};"
                           f"border:1px solid {_C['border_lo']};border-radius:{_R['lg']};}}"
                           f"QFrame#{oid}:hover{{border-color:{_C['border']};background:{_C['bg_raised']};}}")
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        img=QLabel(); img.setFixedHeight(120); img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img.setStyleSheet(f"background:{_C['bg_raised']};border-radius:{_R['lg']} {_R['lg']} 0 0;")
        if entry.image_path and os.path.isfile(entry.image_path):
            px=QPixmap(entry.image_path).scaled(156,120,Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                Qt.TransformationMode.SmoothTransformation)
            img.setPixmap(px)
        else:
            img.setText("📷"); img.setStyleSheet(img.styleSheet()+f"font-size:28px;")
        lay.addWidget(img)
        foot=QWidget(); foot.setFixedHeight(48)
        foot.setStyleSheet("background:transparent;")
        fl=QHBoxLayout(foot); fl.setContentsMargins(8,0,6,0); fl.setSpacing(4)
        sc=GalleryStage.COLORS.get(entry.progress_stage or "","")
        if sc:
            fl.addWidget(_badge(GalleryStage.LABELS.get(entry.progress_stage,""),_rgba(sc,0.2),sc))
        elif entry.title:
            tl=QLabel(entry.title[:16])
            tl.setStyleSheet(f"font-size:{_FS['xs']};color:{_C['text_lo']};background:transparent;")
            fl.addWidget(tl)
        fl.addStretch()
        db=_icon_btn("✕","Delete",danger=True,sz=22)
        db.clicked.connect(lambda: self.delete_requested.emit(entry.id))
        fl.addWidget(db); lay.addWidget(foot)


class _GalleryTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent); self._ctx=ctx; self._project_id:Optional[int]=None
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        ab=QWidget(); ab.setFixedHeight(52)
        ab.setStyleSheet(f"background:{_C['bg_base']};border-bottom:1px solid {_C['border']};")
        al=QHBoxLayout(ab); al.setContentsMargins(14,10,14,10)
        apb=_btn("＋  Add Photo",small=True); apb.clicked.connect(self._add)
        al.addWidget(apb); al.addStretch(); lay.addWidget(ab)
        self._body=QWidget(); self._body.setStyleSheet(f"background:{_C['bg_base']};")
        self._grid=QGridLayout(self._body)
        self._grid.setContentsMargins(16,16,16,16); self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(_scroll_area(self._body),1)

    def populate(self, project_id:int, gallery:list):
        self._project_id=project_id
        while self._grid.count():
            it=self._grid.takeAt(0);
            if it.widget(): it.widget().deleteLater()
        if not gallery:
            el=_lbl("No photos yet — add your first progress shot","base",_C["text_dim"])
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(el,0,0,1,4); return
        for i,entry in enumerate(gallery):
            t=_GalleryThumb(entry)
            t.delete_requested.connect(lambda eid: self._ctx.event_bus.emit("project_gallery_delete",{"id":eid}))
            self._grid.addWidget(t,i//4,i%4)

    def _add(self):
        if not self._project_id: return
        path,_=QFileDialog.getOpenFileName(self,"Select Photo","",
                                           "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)")
        if not path: return
        dlg=_GalleryDialog(path,self)
        if dlg.exec():
            v=dlg.get_values()
            try:
                svc=self._ctx.services.try_get("project_service")
                gdir=svc.gallery_dir(self._project_id) if svc else Path(path).parent
                dst=str(gdir/f"{uuid.uuid4().hex}{Path(path).suffix}")
                shutil.copy2(path,dst); path=dst
            except Exception as e: log.error(f"Gallery copy: {e}")
            self._ctx.event_bus.emit("project_gallery_add",
                                     {"project_id":self._project_id,"image_path":path,**v})


# ── Requirements tab ───────────────────────────────────────────────────────────
class _ReqRow(QFrame):
    delete_requested = Signal(int)
    override_toggled = Signal(int,bool)
    _SICON={ReqStatus.OK:("✓",_C["success"]),ReqStatus.LOW:("▲",_C["warning"]),
            ReqStatus.MISSING:("✕",_C["danger"]),ReqStatus.OK_OVERRIDE:("✓",_C["success"]),
            ReqStatus.UNKNOWN:("?",_C["text_lo"])}
    def __init__(self, req:ProjectRequirement, stock:str, parent=None):
        super().__init__(parent); self.setFixedHeight(46)
        oid=f"rrow{req.id}"; self.setObjectName(oid)
        self.setStyleSheet(f"QFrame#{oid}{{background:{_C['bg_card']};"
                           f"border:1px solid {_C['border_lo']};border-radius:{_R['base']};}}")
        lay=QHBoxLayout(self); lay.setContentsMargins(14,0,10,0); lay.setSpacing(10)
        ic_txt,ic_col=self._SICON.get(stock,("?",_C["text_lo"]))
        si=QLabel(ic_txt); si.setFixedWidth(14)
        si.setStyleSheet(f"font-size:{_FS['sm']};color:{ic_col};font-weight:700;background:transparent;")
        lay.addWidget(si)
        ti=QLabel(ReqItemType.ICONS.get(req.item_type,""))
        ti.setStyleSheet("font-size:14px;background:transparent;"); lay.addWidget(ti)
        nl=QLabel(f"{req.item_name}" + (f"  ×{req.quantity_needed}" if req.quantity_needed>1 else ""))
        nl.setStyleSheet(f"font-size:{_FS['base']};color:{_C['text_hi']};background:transparent;")
        lay.addWidget(nl,1)
        sl=QLabel(stock.replace("_"," ").title())
        sl.setStyleSheet(f"font-size:{_FS['xs']};color:{ic_col};background:transparent;")
        lay.addWidget(sl)
        ov=QCheckBox("Mark OK"); ov.setChecked(req.is_ok_override)
        ov.setStyleSheet(f"color:{_C['text_lo']};font-size:{_FS['xs']};background:transparent;")
        ov.stateChanged.connect(lambda s: self.override_toggled.emit(req.id,bool(s))); lay.addWidget(ov)
        db=_icon_btn("✕","Remove",danger=True,sz=24); db.clicked.connect(lambda: self.delete_requested.emit(req.id))
        lay.addWidget(db)


class _RequirementsTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent); self._ctx=ctx; self._project_id:Optional[int]=None
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        ab=QWidget(); ab.setFixedHeight(52)
        ab.setStyleSheet(f"background:{_C['bg_base']};border-bottom:1px solid {_C['border']};")
        al=QHBoxLayout(ab); al.setContentsMargins(14,10,14,10)
        rb=_btn("＋  Add Requirement",small=True); rb.clicked.connect(self._add)
        al.addWidget(rb); al.addStretch(); lay.addWidget(ab)
        self._body=QWidget(); self._body.setStyleSheet(f"background:{_C['bg_base']};")
        self._blay=QVBoxLayout(self._body)
        self._blay.setContentsMargins(16,16,16,16); self._blay.setSpacing(5)
        self._blay.addStretch()
        lay.addWidget(_scroll_area(self._body),1)

    def populate(self, project_id:int, requirements:list):
        self._project_id=project_id
        while self._blay.count():
            it=self._blay.takeAt(0);
            if it.widget(): it.widget().deleteLater()
        svc=self._ctx.services.try_get("project_service")
        if requirements:
            for req in requirements:
                stock=svc.resolve_requirement_stock(req) if svc else ReqStatus.UNKNOWN
                row=_ReqRow(req,stock)
                row.delete_requested.connect(lambda rid: self._ctx.event_bus.emit("project_requirement_delete",{"id":rid}))
                row.override_toggled.connect(lambda rid,v: self._ctx.event_bus.emit("project_requirement_update",{"id":rid,"is_ok_override":v}))
                self._blay.insertWidget(self._blay.count()-1,row)
        else:
            el=_lbl("No requirements added","base",_C["text_dim"])
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.setContentsMargins(0,50,0,0); self._blay.addWidget(el)
        self._blay.addStretch()

    def _add(self):
        if not self._project_id: return
        svc=self._ctx.services.try_get("project_service")
        dlg=_ReqDialog(self._project_id,svc,self)
        if dlg.exec():
            self._ctx.event_bus.emit("project_requirement_add",
                                     {"project_id":self._project_id,**dlg.get_values()})


# ── Links tab ──────────────────────────────────────────────────────────────────
class _LinksTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent); self._ctx=ctx; self._project_id:Optional[int]=None
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self._body=QWidget(); self._body.setStyleSheet(f"background:{_C['bg_base']};")
        self._blay=QVBoxLayout(self._body)
        self._blay.setContentsMargins(16,16,16,16); self._blay.setSpacing(14)
        self._blay.addStretch()
        lay.addWidget(_scroll_area(self._body))

    def populate(self, project_id:int, linked:dict):
        self._project_id=project_id
        while self._blay.count():
            it=self._blay.takeAt(0);
            if it.widget(): it.widget().deleteLater()
        has_any=False
        for etype in EntityType.ALL:
            items=linked.get(etype,[])
            if not items: continue
            has_any=True
            sec=QFrame(); sec.setObjectName(f"lsec{etype}")
            sec.setStyleSheet(f"QFrame#lsec{etype}{{background:{_C['bg_card']};"
                              f"border:1px solid {_C['border']};border-radius:{_R['xl']};}}")
            sl=QVBoxLayout(sec); sl.setContentsMargins(16,14,16,14); sl.setSpacing(8)
            hr=QHBoxLayout()
            hr.addWidget(_section_hdr(f"{EntityType.ICONS.get(etype,'')}  {EntityType.LABELS.get(etype,etype)}"))
            hr.addWidget(_badge(str(len(items)),_rgba(_C["accent"],0.2),_C["accent_text"]))
            hr.addStretch(); sl.addLayout(hr)
            chips=QWidget(); chips.setStyleSheet("background:transparent;")
            cl=QHBoxLayout(chips); cl.setContentsMargins(0,0,0,0); cl.setSpacing(6)
            for obj in items:
                name=(getattr(obj,"name","") or getattr(obj,"title","") or str(obj))[:50]
                chip=QFrame(); chip.setObjectName(f"chip{id(obj)}")
                chip.setStyleSheet(f"QFrame#chip{id(obj)}{{background:{_rgba(_C['accent'],0.08)};"
                                   f"border:1px solid {_rgba(_C['accent'],0.2)};border-radius:{_R['pill']};}}")
                chipl=QHBoxLayout(chip); chipl.setContentsMargins(10,3,6,3); chipl.setSpacing(6)
                nl=QLabel(name); nl.setStyleSheet(f"font-size:{_FS['sm']};color:{_C['text_mid']};background:transparent;")
                chipl.addWidget(nl)
                eid=getattr(obj,"id",None)
                if eid:
                    ub=_icon_btn("✕","Unlink",danger=True,sz=18)
                    ub.clicked.connect(lambda _,et=etype,ei=eid:
                        self._ctx.event_bus.emit("project_unlink_entity",
                                                 {"project_id":self._project_id,"entity_type":et,"entity_id":ei}))
                    chipl.addWidget(ub)
                cl.addWidget(chip)
            cl.addStretch(); sl.addWidget(chips)
            self._blay.insertWidget(self._blay.count()-1,sec)
        if not has_any:
            el=_lbl("No linked entities yet","base",_C["text_dim"])
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.setContentsMargins(0,50,0,0); self._blay.addWidget(el)
        self._blay.addStretch()


# ── Detail panel ───────────────────────────────────────────────────────────────
_TAB_NAMES=["overview","milestones","sessions","notes","gallery","requirements","links"]

class _DetailPanel(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent); self._ctx=ctx
        self._project:Optional[Project]=None
        self.setStyleSheet(f"background:{_C['bg_base']};")
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────────
        self._hdr=QWidget(); self._hdr.setFixedHeight(72)
        self._hdr.setStyleSheet(f"background:{_C['bg_card']};"
                                f"border-bottom:1px solid {_C['border']};")
        hl=QHBoxLayout(self._hdr); hl.setContentsMargins(20,0,16,0); hl.setSpacing(12)

        self._hdr_icon=QLabel("📁")
        self._hdr_icon.setStyleSheet("font-size:24px;background:transparent;")
        hl.addWidget(self._hdr_icon)

        tc=QVBoxLayout(); tc.setSpacing(2)
        self._hdr_name=QLabel("Select a project")
        self._hdr_name.setStyleSheet(f"font-size:{_FS['xl']};color:{_C['text_hi']};"
                                      "font-weight:700;background:transparent;")
        tc.addWidget(self._hdr_name)
        self._hdr_sub=QLabel("")
        self._hdr_sub.setStyleSheet(f"font-size:{_FS['xs']};color:{_C['text_lo']};background:transparent;")
        tc.addWidget(self._hdr_sub)
        hl.addLayout(tc,1)

        # Status pill button (click to cycle)
        self._status_btn=QPushButton()
        self._status_btn.setFixedHeight(22); self._status_btn.hide()
        self._status_btn.setStyleSheet("QPushButton{background:transparent;border:none;padding:0;}")
        self._status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._status_btn.clicked.connect(self._cycle_status)
        hl.addWidget(self._status_btn)

        self._proj_menu = QMenu(self)
        self._proj_menu.setStyleSheet(
            f"QMenu{{background:{_C['bg_raised']};color:{_C['text_hi']};"
            f"border:1px solid {_C['border_hi']};border-radius:{_R['base']};padding:4px;}}"
            f"QMenu::item{{padding:7px 20px 7px 12px;font-size:{_FS['base']};}}"
            f"QMenu::item:selected{{background:{_C['bg_hover']};border-radius:{_R['sm']};}}"
            f"QMenu::separator{{height:1px;background:{_C['border']};margin:4px 8px;}}")
        self._act_edit   = self._proj_menu.addAction("Edit Project")
        self._proj_menu.addSeparator()
        self._act_delete = self._proj_menu.addAction("Delete Project")
        self._act_edit.triggered.connect(self._on_edit)
        self._act_delete.triggered.connect(self._on_delete)

        self._menu_btn = QPushButton("Actions  ▾"); self._menu_btn.hide()
        self._menu_btn.setFixedHeight(28)
        self._menu_btn.setToolTip("Project actions")
        self._menu_btn.setStyleSheet(
            f"QPushButton{{background:{_C['bg_raised']};color:{_C['text_mid']};"
            f"border:1px solid {_C['border_hi']};border-radius:{_R['base']};"
            f"font-size:{_FS['sm']};font-weight:500;padding:0 10px;}}"
            f"QPushButton:hover{{background:{_C['bg_hover']};color:{_C['text_hi']};"
            f"border-color:{_C['accent']};}}"
            f"QPushButton:pressed{{background:{_C['bg_input']};}}")
        self._menu_btn.clicked.connect(self._show_proj_menu)
        hl.addWidget(self._menu_btn)
        root.addWidget(self._hdr)

        # ── Live session banner ────────────────────────────────────────────
        self._banner=_SessionBanner(); self._banner.hide()
        self._banner.end_clicked.connect(self._on_end_session)
        root.addWidget(self._banner)

        # ── Tabs ────────────────────────────────────────────────────────────
        self._tabs=QTabWidget()
        self._tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.tabBar().setUsesScrollButtons(True)
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane{{background:{_C['bg_base']};border:none;
                border-top:1px solid {_C['border']};}}
            QTabBar{{background:{_C['bg_card']};}}
            QTabBar::tab{{background:transparent;color:{_C['text_lo']};
                padding:9px 16px;font-size:{_FS['sm']};font-weight:500;
                border:none;border-bottom:2px solid transparent;}}
            QTabBar::tab:selected{{color:{_C['text_hi']};
                border-bottom:2px solid {_C['accent']};}}
            QTabBar::tab:hover:!selected{{color:{_C['text_mid']};}}
            QTabBar QToolButton{{background:{_C['bg_raised']};border:none;
                color:{_C['text_mid']};border-radius:{_R['sm']};}}
        """)
        self._t_overview = _OverviewTab(ctx)
        self._t_ms       = _MilestonesTab(ctx)
        self._t_sess     = _SessionsTab(ctx)
        self._t_notes    = _NotesTab(ctx)
        self._t_gallery  = _GalleryTab(ctx)
        self._t_req      = _RequirementsTab(ctx)
        self._t_links    = _LinksTab(ctx)
        for tab,name in [(self._t_overview,"Overview"),(self._t_ms,"Milestones"),
                         (self._t_sess,"Sessions"),(self._t_notes,"Notes"),
                         (self._t_gallery,"Gallery"),(self._t_req,"Requirements"),
                         (self._t_links,"Links")]:
            self._tabs.addTab(tab,name)

        # ── Empty state ────────────────────────────────────────────────────
        self._empty=QWidget(); self._empty.setStyleSheet(f"background:{_C['bg_base']};")
        el=QVBoxLayout(self._empty); el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ei=QLabel("📁"); ei.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ei.setStyleSheet("font-size:52px;background:transparent;")
        et=_lbl("Select or create a project to get started","xl",_C["text_dim"])
        et.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(ei); el.addSpacing(16); el.addWidget(et)

        self._stack=QStackedWidget()
        self._stack.addWidget(self._tabs)   # 0 = detail
        self._stack.addWidget(self._empty)  # 1 = empty
        self._stack.setCurrentIndex(1)
        root.addWidget(self._stack,1)

    # ── Public API ────────────────────────────────────────────────────────────
    def load_project(self, project:Project, stats, milestones:list, notes:list,
                     sessions:list, linked:dict, gallery:list, requirements:list):
        self._project=project

        self._hdr_icon.setText(project.icon or "📁")
        self._hdr_name.setText(project.name)

        sub=[]
        if project.game_system: sub.append(project.game_system)
        cat=ProjectCategory.LABELS.get(getattr(project,"category",""),"")
        if cat and cat!="Other": sub.append(cat)
        if stats and stats.total_hours: sub.append(f"{stats.total_hours}h logged")
        self._hdr_sub.setText("  ·  ".join(sub))

        sc=_STATUS_C.get(project.status,_C["text_lo"])
        st_label=ProjectStatus.LABELS.get(project.status,project.status)
        self._status_btn.setText(st_label)
        self._status_btn.setStyleSheet(
            f"QPushButton{{background:{_rgba(sc,0.15)};color:{sc};"
            f"border:none;border-radius:{_R['pill']};font-size:{_FS['xs']};"
            f"font-weight:600;padding:2px 10px;}}"
            f"QPushButton:hover{{background:{_rgba(sc,0.25)};}}")
        self._status_btn.show()
        self._menu_btn.show()

        # Live session banner
        active=next((s for s in sessions if s.is_active),None)
        if active:
            self._banner.start(active.actual_start_time or active.started_at)
        else:
            self._banner.stop()

        self._t_overview.populate(project,stats,milestones,sessions)
        self._t_ms.populate(project.id,milestones)
        self._t_sess.populate(project.id,sessions,milestones)
        self._t_notes.populate(project.id,notes)
        self._t_gallery.populate(project.id,gallery)
        self._t_req.populate(project.id,requirements)
        self._t_links.populate(project.id,linked)
        self._stack.setCurrentIndex(0)

    def show_empty(self):
        self._project=None
        self._hdr_icon.setText("📁"); self._hdr_name.setText("Select a project")
        self._hdr_sub.setText("")
        self._status_btn.hide(); self._menu_btn.hide()
        self._banner.stop(); self._stack.setCurrentIndex(1)

    def navigate_to_tab(self, tab:str, item_id=None):
        idx=_TAB_NAMES.index(tab) if tab in _TAB_NAMES else 0
        self._tabs.setCurrentIndex(idx)

    # ── Internal handlers ─────────────────────────────────────────────────────
    def _on_edit(self):
        if self._project:
            self._ctx.event_bus.emit("project_edit_requested",{"id":self._project.id})

    def _on_delete(self):
        if not self._project: return
        mb=QMessageBox(self); mb.setWindowTitle("Delete Project")
        mb.setText(f"Delete <b>{self._project.name}</b>?")
        mb.setInformativeText("All milestones, sessions, notes, gallery photos and links will be removed.")
        mb.setStandardButtons(QMessageBox.StandardButton.Cancel|QMessageBox.StandardButton.Yes)
        mb.setDefaultButton(QMessageBox.StandardButton.Cancel)
        mb.setStyleSheet(f"QMessageBox{{background:{_C['bg_card']};color:{_C['text_hi']};}}"
                         f"QLabel{{color:{_C['text_hi']};background:transparent;}}"
                         f"QPushButton{{background:{_C['bg_raised']};color:{_C['text_mid']};"
                         f"border:1px solid {_C['border_hi']};border-radius:{_R['base']};padding:5px 16px;}}")
        if mb.exec()==QMessageBox.StandardButton.Yes:
            self._ctx.event_bus.emit("project_delete",{"id":self._project.id})

    def _cycle_status(self):
        if not self._project: return
        order=[ProjectStatus.ACTIVE,ProjectStatus.ON_HOLD,ProjectStatus.COMPLETED,ProjectStatus.ARCHIVED]
        idx=order.index(self._project.status) if self._project.status in order else 0
        new_st=order[(idx+1)%len(order)]
        self._ctx.event_bus.emit("project_v2_status_changed",
                                 {"id":self._project.id,"status":new_st})

    def _show_proj_menu(self):
        self._proj_menu.exec(self._menu_btn.mapToGlobal(
            self._menu_btn.rect().bottomLeft()))

    def _on_end_session(self):
        if not self._project: return
        dlg=_EndSessionDialog(self)
        if dlg.exec():
            self._ctx.event_bus.emit("project_session_end",
                                     {"project_id":self._project.id,**dlg.get_values()})
        else:
            self._ctx.event_bus.emit("project_session_end",{"project_id":self._project.id})


# ── Dialogs ────────────────────────────────────────────────────────────────────
class _ProjectDialog(QDialog):
    def __init__(self, project:Optional[Project]=None, parent=None):
        super().__init__(parent); self._project=project
        self.setWindowTitle("Edit Project" if project else "New Project")
        self.setMinimumWidth(520); self.setStyleSheet(_DLG_SS); self._build()
        if project: self._load(project)

    def _build(self):
        lay=QVBoxLayout(self); lay.setSpacing(0); lay.setContentsMargins(24,20,24,20)

        # ── Name row ────────────────────────────────────────────────────────
        row=QHBoxLayout(); row.setSpacing(10)
        self._icon_btn=QToolButton(); self._icon_btn.setText("📁")
        self._icon_btn.setFixedSize(40,40)
        self._icon_btn.setStyleSheet(
            f"QToolButton{{background:{_C['bg_input']};border:1px solid {_C['border_hi']};"
            f"border-radius:{_R['base']};font-size:20px;padding:0;}}"
            f"QToolButton:hover{{border-color:{_C['accent']};}}")
        self._icon_btn.clicked.connect(self._pick_icon)
        row.addWidget(self._icon_btn)
        self._name=QLineEdit(); self._name.setPlaceholderText("Project name *")
        self._name.setFixedHeight(40)
        row.addWidget(self._name,1); lay.addLayout(row)
        lay.addSpacing(14)

        # ── Description ─────────────────────────────────────────────────────
        lay.addWidget(_lbl("Description")); lay.addSpacing(5)
        self._desc=QTextEdit(); self._desc.setFixedHeight(72)
        self._desc.setPlaceholderText("What are you building?")
        lay.addWidget(self._desc); lay.addSpacing(14)

        # ── Game System ─────────────────────────────────────────────────────
        lay.addWidget(_lbl("Game System")); lay.addSpacing(5)
        self._game=QComboBox(); self._game.setEditable(True)
        self._game.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._game.lineEdit().setPlaceholderText("Select or type a game system…")
        for g in GAME_SYSTEMS[1:]:
            self._game.addItem(g, g)
        self._game.setCurrentIndex(-1)
        lay.addWidget(self._game); lay.addSpacing(14)

        # ── Category / Priority / Status ─────────────────────────────────────
        row2=QHBoxLayout(); row2.setSpacing(12)
        for attr,label,items_fn in [
            ("_cat","Category",  lambda:[(ProjectCategory.LABELS[k],k) for k in ProjectCategory.ALL]),
            ("_pri","Priority",  lambda:[(ProjectPriority.LABELS[k],k)  for k in ProjectPriority.ALL]),
            ("_status","Status", lambda:[(ProjectStatus.LABELS[k],k)    for k in ProjectStatus.ALL]),
        ]:
            col=QVBoxLayout(); col.setSpacing(5)
            col.addWidget(_lbl(label))
            cb=QComboBox()
            for disp,val in items_fn():
                cb.addItem(disp,val)
            col.addWidget(cb); setattr(self,attr,cb); row2.addLayout(col)
        lay.addLayout(row2); lay.addSpacing(14)

        # ── Target Date + Accent Color ───────────────────────────────────────
        row3=QHBoxLayout(); row3.setSpacing(16)

        dcol=QVBoxLayout(); dcol.setSpacing(5)
        dcol.addWidget(_lbl("Target Date"))
        self._has_target=QCheckBox("Set a target date")
        self._target=QDateEdit(); self._target.setCalendarPopup(True)
        self._target.setDate(QDate.currentDate().addDays(30))
        self._target.setEnabled(False)
        self._has_target.stateChanged.connect(lambda s: self._target.setEnabled(bool(s)))
        dcol.addWidget(self._has_target); dcol.addSpacing(4); dcol.addWidget(self._target)
        row3.addLayout(dcol,1)

        ccol=QVBoxLayout(); ccol.setSpacing(5)
        ccol.addWidget(_lbl("Accent Color"))
        self._color="#0078d4"
        self._color_btn=QToolButton()
        self._color_btn.setFixedSize(36,36)
        self._color_btn.setToolTip("Pick accent colour")
        self._color_btn.clicked.connect(self._pick_color)
        self._update_color_btn()
        ccol.addWidget(self._color_btn)
        ccol.addStretch()
        row3.addLayout(ccol)
        lay.addLayout(row3); lay.addSpacing(14)

        # ── Tags ────────────────────────────────────────────────────────────
        lay.addWidget(_lbl("Tags  (comma-separated)")); lay.addSpacing(5)
        self._tags=QLineEdit()
        self._tags.setPlaceholderText("e.g. commission, display, wip")
        lay.addWidget(self._tags); lay.addSpacing(20)

        # ── Buttons ─────────────────────────────────────────────────────────
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Save" if self._project else "Create")
        lay.addWidget(bb)

    def _load(self, p:Project):
        self._icon_btn.setText(p.icon or "📁"); self._name.setText(p.name)
        self._desc.setPlainText(p.description or "")
        # Game system: editable combo — set text directly
        if p.game_system:
            idx = self._game.findText(p.game_system)
            if idx >= 0: self._game.setCurrentIndex(idx)
            else: self._game.setCurrentText(p.game_system)
        for cb,val in [(self._cat,p.category),(self._pri,p.priority),(self._status,p.status)]:
            idx=cb.findData(val)
            if idx>=0: cb.setCurrentIndex(idx)
        if p.target_date:
            try:
                self._has_target.setChecked(True)
                self._target.setDate(QDate.fromString(p.target_date,"yyyy-MM-dd"))
            except: pass
        self._color=p.color or "#0078d4"; self._update_color_btn()
        self._tags.setText(", ".join(p.tags) if p.tags else "")

    def _pick_icon(self):
        dlg=QDialog(self); dlg.setWindowTitle("Pick Icon"); dlg.setStyleSheet(_DLG_SS)
        gl=QGridLayout(dlg); gl.setSpacing(6); gl.setContentsMargins(16,16,16,16)
        for i,ic in enumerate(PROJECT_ICONS):
            b=QToolButton(); b.setText(ic); b.setFixedSize(42,42)
            b.setStyleSheet(
                f"QToolButton{{font-size:20px;background:{_C['bg_raised']};border:none;"
                f"border-radius:{_R['base']};padding:0;}}"
                f"QToolButton:hover{{background:{_C['bg_hover']};border:1px solid {_C['accent']};}}")
            b.clicked.connect(lambda _,c=ic:(self._icon_btn.setText(c),dlg.accept()))
            gl.addWidget(b,i//8,i%8)
        dlg.exec()

    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        c=QColorDialog.getColor(QColor(self._color),self)
        if c.isValid(): self._color=c.name(); self._update_color_btn()

    def _update_color_btn(self):
        self._color_btn.setStyleSheet(
            f"QToolButton{{background:{self._color};"
            f"border:2px solid {_rgba(self._color,0.6)};border-radius:{_R['base']};padding:0;}}"
            f"QToolButton:hover{{border-color:{_C['text_hi']};}}")

    def _accept(self):
        if not self._name.text().strip():
            ToastManager.instance().show("Project name is required","warning"); return
        self.accept()

    def get_values(self)->dict:
        tags=[t.strip() for t in self._tags.text().split(",") if t.strip()]
        td=self._target.date().toString("yyyy-MM-dd") if self._has_target.isChecked() else None
        cat_data = self._cat.currentData()
        pri_data = self._pri.currentData()
        stat_data= self._status.currentData()
        game_text= self._game.currentText()
        return {"name":self._name.text().strip(),"description":self._desc.toPlainText().strip(),
                "game_system":game_text,"status":stat_data or "active",
                "category":cat_data or "other","priority":pri_data or "medium",
                "color":self._color,"icon":self._icon_btn.text(),
                "target_date":td,"tags":tags}

ProjectEditDialog = _ProjectDialog


class _MilestoneDialog(QDialog):
    def __init__(self, project_id:int, milestone:Optional[Milestone]=None, parent=None):
        super().__init__(parent); self._m=milestone
        self.setWindowTitle("Edit Milestone" if milestone else "Add Milestone")
        self.setMinimumWidth(400); self.setStyleSheet(_DLG_SS); self._build()
        if milestone: self._load(milestone)

    def _build(self):
        lay=QVBoxLayout(self); lay.setSpacing(10); lay.setContentsMargins(20,18,20,18)
        lay.addWidget(_lbl("Title *"))
        self._title=QLineEdit(); self._title.setPlaceholderText("Milestone title")
        lay.addWidget(self._title)
        lay.addWidget(_lbl("Description"))
        self._desc=QTextEdit(); self._desc.setFixedHeight(58); lay.addWidget(self._desc)
        row=QHBoxLayout(); row.setSpacing(12)
        pl=QVBoxLayout(); pl.setSpacing(4); pl.addWidget(_lbl("Priority"))
        self._pri=QComboBox()
        for k in ProjectPriority.ALL: self._pri.addItem(ProjectPriority.LABELS[k],k)
        pl.addWidget(self._pri); row.addLayout(pl)
        dl=QVBoxLayout(); dl.setSpacing(4); dl.addWidget(_lbl("Due Date"))
        self._has_due=QCheckBox("Set due date")
        self._due=QDateEdit(); self._due.setCalendarPopup(True)
        self._due.setDate(QDate.currentDate().addDays(7)); self._due.setEnabled(False)
        self._has_due.stateChanged.connect(lambda s: self._due.setEnabled(bool(s)))
        dl.addWidget(self._has_due); dl.addWidget(self._due); row.addLayout(dl)
        lay.addLayout(row)
        qrow=QHBoxLayout(); qrow.setSpacing(8)
        self._has_qty=QCheckBox("Quantity milestone")
        self._qty=QSpinBox(); self._qty.setRange(2,9999); self._qty.setValue(10); self._qty.setEnabled(False)
        self._has_qty.stateChanged.connect(lambda s: self._qty.setEnabled(bool(s)))
        qrow.addWidget(self._has_qty); qrow.addWidget(_lbl("Total:","sm")); qrow.addWidget(self._qty); qrow.addStretch()
        lay.addLayout(qrow)
        self._focus=QCheckBox("Mark as focus milestone"); lay.addWidget(self._focus)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Save" if self._m else "Add")
        lay.addWidget(bb)

    def _load(self, m:Milestone):
        self._title.setText(m.title); self._desc.setPlainText(m.description or "")
        idx=self._pri.findData(m.priority)
        if idx>=0: self._pri.setCurrentIndex(idx)
        if m.due_date:
            self._has_due.setChecked(True); self._due.setDate(QDate.fromString(m.due_date,"yyyy-MM-dd"))
        if m.quantity_total:
            self._has_qty.setChecked(True); self._qty.setValue(m.quantity_total)
        self._focus.setChecked(m.is_focus)

    def _accept(self):
        if not self._title.text().strip():
            ToastManager.instance().show("Title required","warning"); return
        self.accept()

    def get_values(self)->dict:
        return {"title":self._title.text().strip(),"description":self._desc.toPlainText().strip(),
                "priority":self._pri.currentData(),
                "due_date":self._due.date().toString("yyyy-MM-dd") if self._has_due.isChecked() else None,
                "quantity_total":self._qty.value() if self._has_qty.isChecked() else 0,
                "is_focus":self._focus.isChecked()}


class _LogSessionDialog(QDialog):
    def __init__(self, project_id:int, milestones:list, parent=None):
        super().__init__(parent); self._milestones=milestones
        self.setWindowTitle("Log Session"); self.setMinimumWidth(360)
        self.setStyleSheet(_DLG_SS); self._build()

    def _build(self):
        lay=QVBoxLayout(self); lay.setSpacing(10); lay.setContentsMargins(20,18,20,18)
        lay.addWidget(_lbl("Duration *"))
        self._dur=QSpinBox(); self._dur.setRange(1,1440); self._dur.setValue(60); self._dur.setSuffix(" min")
        lay.addWidget(self._dur)
        if self._milestones:
            lay.addWidget(_lbl("Linked Milestone"))
            self._ms=QComboBox(); self._ms.addItem("No milestone",None)
            for m in self._milestones:
                if not m.is_complete: self._ms.addItem(m.title,m.id)
            lay.addWidget(self._ms)
        lay.addWidget(_lbl("Notes"))
        self._notes=QTextEdit(); self._notes.setFixedHeight(56); lay.addWidget(self._notes)
        lay.addWidget(_lbl("Outcome"))
        self._outcome=QLineEdit(); self._outcome.setPlaceholderText("What did you achieve?")
        lay.addWidget(self._outcome)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Log Session")
        lay.addWidget(bb)

    def get_values(self)->dict:
        ms_id=self._ms.currentData() if hasattr(self,"_ms") else None
        return {"duration_minutes":self._dur.value(),"notes":self._notes.toPlainText().strip(),
                "outcome":self._outcome.text().strip(),"linked_milestone_id":ms_id}


class _EndSessionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("End Session")
        self.setMinimumWidth(360); self.setStyleSheet(_DLG_SS); self._build()

    def _build(self):
        lay=QVBoxLayout(self); lay.setSpacing(10); lay.setContentsMargins(20,18,20,18)
        lay.addWidget(_lbl("How did the session go?","lg",bold=True))
        lay.addWidget(_lbl("Notes"))
        self._notes=QTextEdit(); self._notes.setFixedHeight(68); lay.addWidget(self._notes)
        lay.addWidget(_lbl("Outcome"))
        self._outcome=QLineEdit(); self._outcome.setPlaceholderText("What did you achieve?")
        lay.addWidget(self._outcome)
        lay.addWidget(_lbl("Next action"))
        self._next=QLineEdit(); self._next.setPlaceholderText("What's next?")
        lay.addWidget(self._next)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("End Session")
        lay.addWidget(bb)

    def get_values(self)->dict:
        return {"notes":self._notes.toPlainText().strip(),"outcome":self._outcome.text().strip(),
                "next_action":self._next.text().strip()}


class _NoteDialog(QDialog):
    def __init__(self, note:Optional[ProjectNote]=None, parent=None):
        super().__init__(parent); self._note=note
        self.setWindowTitle("Edit Note" if note else "New Note")
        self.setMinimumWidth(440); self.setMinimumHeight(300)
        self.setStyleSheet(_DLG_SS); self._build()
        if note: self._title.setText(note.title or ""); self._content.setPlainText(note.content or "")

    def _build(self):
        lay=QVBoxLayout(self); lay.setSpacing(10); lay.setContentsMargins(20,18,20,18)
        lay.addWidget(_lbl("Title"))
        self._title=QLineEdit(); self._title.setPlaceholderText("Optional title")
        lay.addWidget(self._title)
        lay.addWidget(_lbl("Content"))
        self._content=QTextEdit(); self._content.setPlaceholderText("Write your notes…")
        lay.addWidget(self._content,1)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Save"); lay.addWidget(bb)

    def get_values(self)->dict:
        return {"title":self._title.text().strip(),"content":self._content.toPlainText().strip()}


class _GalleryDialog(QDialog):
    def __init__(self, image_path:str, parent=None):
        super().__init__(parent); self._path=image_path
        self.setWindowTitle("Add Progress Photo"); self.setMinimumWidth(360)
        self.setStyleSheet(_DLG_SS); self._build()

    def _build(self):
        lay=QVBoxLayout(self); lay.setSpacing(10); lay.setContentsMargins(20,18,20,18)
        pv=QLabel(); pv.setFixedHeight(120); pv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pv.setStyleSheet(f"background:{_C['bg_raised']};border-radius:{_R['base']};")
        if os.path.isfile(self._path):
            px=QPixmap(self._path).scaled(340,120,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            pv.setPixmap(px)
        lay.addWidget(pv)
        lay.addWidget(_lbl("Stage"))
        self._stage=QComboBox(); self._stage.addItem("No stage","")
        for k in GalleryStage.ALL: self._stage.addItem(GalleryStage.LABELS[k],k)
        lay.addWidget(self._stage)
        lay.addWidget(_lbl("Title")); self._title=QLineEdit(); lay.addWidget(self._title)
        lay.addWidget(_lbl("Note")); self._note=QLineEdit(); lay.addWidget(self._note)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Add Photo"); lay.addWidget(bb)

    def get_values(self)->dict:
        return {"title":self._title.text().strip(),"note":self._note.text().strip(),
                "progress_stage":self._stage.currentData() or ""}


class _ReqDialog(QDialog):
    def __init__(self, project_id:int, svc, parent=None):
        super().__init__(parent); self.setWindowTitle("Add Requirement")
        self.setMinimumWidth(380); self.setStyleSheet(_DLG_SS); self._build()

    def _build(self):
        lay=QVBoxLayout(self); lay.setSpacing(10); lay.setContentsMargins(20,18,20,18)
        lay.addWidget(_lbl("Item Type"))
        self._type=QComboBox()
        for k in ReqItemType.ALL: self._type.addItem(f"{ReqItemType.ICONS[k]}  {ReqItemType.LABELS[k]}",k)
        lay.addWidget(self._type)
        lay.addWidget(_lbl("Item Name *"))
        self._name=QLineEdit(); self._name.setPlaceholderText("e.g. Contrast Black Templar")
        lay.addWidget(self._name)
        row=QHBoxLayout(); row.setSpacing(10)
        ql=QVBoxLayout(); ql.setSpacing(4); ql.addWidget(_lbl("Quantity Needed"))
        self._qty=QSpinBox(); self._qty.setRange(1,999); self._qty.setValue(1)
        ql.addWidget(self._qty); row.addLayout(ql); row.addStretch(); lay.addLayout(row)
        lay.addWidget(_lbl("Notes"))
        self._notes=QLineEdit(); self._notes.setPlaceholderText("Optional"); lay.addWidget(self._notes)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Add"); lay.addWidget(bb)

    def _accept(self):
        if not self._name.text().strip():
            ToastManager.instance().show("Item name required","warning"); return
        self.accept()

    def get_values(self)->dict:
        return {"item_type":self._type.currentData(),"item_name":self._name.text().strip(),
                "quantity_needed":self._qty.value(),"notes":self._notes.text().strip()}


# ── Main widget ────────────────────────────────────────────────────────────────
class ProjectTrackerV2UI(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent); self._ctx=ctx
        self.setStyleSheet(f"background:{_C['bg_base']};")
        self._build()

    def _build(self):
        root=QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        self._splitter=QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet(f"QSplitter::handle{{background:{_C['border_lo']};}}")
        self._list_panel  =_SidebarPanel(self._ctx)
        self._detail_panel=_DetailPanel(self._ctx)
        self._list_panel.new_project_requested.connect(self._new_project)
        self._list_panel.project_selected.connect(
            lambda pid: self._ctx.event_bus.emit("project_selected",{"id":pid}))
        self._splitter.addWidget(self._list_panel)
        self._splitter.addWidget(self._detail_panel)
        self._splitter.setStretchFactor(0,0); self._splitter.setStretchFactor(1,1)
        self._splitter.setCollapsible(0,False); self._splitter.setCollapsible(1,False)
        # Restore saved sidebar width, fall back to 320
        saved = self._load_sidebar_width()
        self._splitter.setSizes([saved, 900])
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        root.addWidget(self._splitter)

    _SIDEBAR_WIDTH_KEY = "project_tracker_v2.sidebar_width"

    def _load_sidebar_width(self) -> int:
        try:
            svc = self._ctx.services.try_get("settings")
            if svc:
                raw = svc.get(self._SIDEBAR_WIDTH_KEY, "")
                if str(raw).isdigit():
                    return max(200, min(600, int(raw)))
        except Exception:
            pass
        return 320

    def _on_splitter_moved(self, pos:int, index:int):
        try:
            svc = self._ctx.services.try_get("settings")
            if svc:
                width = self._splitter.sizes()[0]
                svc.set(self._SIDEBAR_WIDTH_KEY, width)
        except Exception:
            pass

    def display_projects(self, projects:list, stats_map:dict=None):
        self._list_panel.populate(projects, stats_map or {})

    def display_project_detail(self, project:Project, stats, milestones:list,
                                notes:list, sessions:list, linked:dict,
                                gallery:list, requirements:list=None):
        self._detail_panel.load_project(project,stats,milestones,notes,
                                        sessions,linked,gallery,requirements or [])
        self._list_panel.select_project(project.id)

    def show_empty_detail(self):
        self._detail_panel.show_empty()

    def _show_success(self, msg:str):
        ToastManager.instance().show(msg, level="success")

    def _show_error(self, msg:str):
        ToastManager.instance().show(msg, level="error")

    def _new_project(self):
        dlg=_ProjectDialog(None,self)
        if dlg.exec():
            self._ctx.event_bus.emit("project_create", dlg.get_values())
