"""
Campaign Command 2.0 — UI
Iterative build — start with scaffold + campaigns page, add sections progressively.
"""
from __future__ import annotations

import json
import os
import random
import re
from datetime import date
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QPixmap, QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QComboBox, QCheckBox, QDialog, QDialogButtonBox,
    QGridLayout, QSpinBox, QTextEdit, QMessageBox, QMenu,
    QFileDialog, QStackedWidget, QSizePolicy, QFormLayout,
    QListWidget, QListWidgetItem, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QApplication,
)

from .models import (
    SYSTEMS, SYSTEM_LIST, CHAR_TEMPLATES, CampaignGalleryStage,
    DND5E_XP_THRESHOLDS, DND5E_CR_XP, DND5E_MULT,
    PF2E_XP_BUDGET, PF2E_CREATURE_XP,
)

try:
    from plugins.campaign_tracker.game_data import GameDataLoader
    _GAME_DATA_AVAILABLE = True
except Exception:
    GameDataLoader = None  # type: ignore
    _GAME_DATA_AVAILABLE = False

# ── Palette ────────────────────────────────────────────────────────────────────
_BG      = "#1c1c1c"
_BG2     = "#212121"
_BG3     = "#282828"
_SIDEBAR = "#161616"
_BORDER  = "#2e2e2e"
_FG      = "#f0f0f0"
_FG_MID  = "#a0a0a0"
_FG_DIM  = "#606060"
_ACCENT  = "#4f9eff"
_SUCCESS = "#3dba6e"
_DANGER  = "#e05555"

# ── Section indices ────────────────────────────────────────────────────────────
_SEC_CAMPAIGNS  = 0
_SEC_OVERVIEW   = 1
_SEC_SESSIONS   = 2
_SEC_CHARACTERS = 3
_SEC_ENCOUNTERS = 4
_SEC_COMPENDIUM = 5
_SEC_GALLERY    = 6
_SEC_DICE       = 7
_SEC_ASSETS     = 8
_SEC_QUESTS     = 9

_NAV_ITEMS = [
    (_SEC_OVERVIEW,   "🏠", "Overview"),
    (_SEC_SESSIONS,   "📅", "Sessions"),
    (_SEC_QUESTS,     "🗡", "Quests"),
    (_SEC_CHARACTERS, "🧙", "Characters"),
    (_SEC_ENCOUNTERS, "⚔",  "Encounters"),
    (_SEC_COMPENDIUM, "📖", "Compendium"),
    (_SEC_GALLERY,    "🖼",  "Gallery"),
    (_SEC_ASSETS,     "📁", "Assets"),
    (_SEC_DICE,       "🎲", "Dice"),
]

# ── Quest metadata ──────────────────────────────────────────────────────────────
_QUEST_STATUSES   = ["Active", "On Hold", "Completed", "Abandoned"]
_QUEST_PRIORITIES = ["High", "Medium", "Low"]
_QUEST_CATEGORIES = [
    "Main Quest", "Side Quest", "Personal Quest", "Faction Quest", "Other"
]
_QUEST_STATUS_META: dict[str, tuple[str, str]] = {
    "Active":    ("🔵", "#4f9eff"),
    "On Hold":   ("⏸",  "#e08c55"),
    "Completed": ("✅", "#3dba6e"),
    "Abandoned": ("💀", "#606060"),
}
_QUEST_PRIORITY_COLORS = {
    "High":   "#e05555",
    "Medium": "#e08c55",
    "Low":    "#4f9eff",
}
_QUEST_CAT_ICONS = {
    "Main Quest":     "⚔",
    "Side Quest":     "📜",
    "Personal Quest": "🧙",
    "Faction Quest":  "🏛",
    "Other":          "❓",
}

# ── Asset categories ────────────────────────────────────────────────────────────
_ASSET_CATS = [
    ("all",       "All",       "📁", "#4f9eff"),
    ("tokens",    "Tokens",    "🎭", "#1565c0"),
    ("maps",      "Maps",      "🗺", "#2e7d32"),
    ("music",     "Music",     "🎵", "#6a1b9a"),
    ("documents", "Documents", "📄", "#e65100"),
    ("other",     "Other",     "📦", "#5d4037"),
]
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg"}
_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"}
_DOC_EXTS   = {".pdf", ".txt", ".md", ".docx", ".doc", ".rtf", ".odt", ".csv"}


def _guess_asset_category(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in _AUDIO_EXTS:
        return "music"
    if ext in _DOC_EXTS:
        return "documents"
    if ext in _IMAGE_EXTS:
        return "tokens"   # user can change to maps/other
    return "other"


def _asset_cat_info(cat_id: str) -> tuple[str, str, str]:
    """Return (label, icon, colour) for a category id."""
    for cid, lbl, icon, col in _ASSET_CATS:
        if cid == cat_id:
            return lbl, icon, col
    return "Other", "📦", "#5d4037"


# ── Custom game-system preset helpers ─────────────────────────────────────────
_CUSTOM_PRESETS_FILE = os.path.join(os.path.dirname(__file__), "custom_systems.json")


def _load_custom_presets() -> list[dict]:
    """Return user-saved custom game system presets from disk."""
    try:
        if os.path.exists(_CUSTOM_PRESETS_FILE):
            with open(_CUSTOM_PRESETS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_custom_preset(name: str) -> str:
    """Persist a new custom game system preset and return its generated ID."""
    from .models import GameSystem
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_") or "custom_system"
    preset_id = f"custom_{slug}"
    presets = _load_custom_presets()
    if not any(p.get("id") == preset_id for p in presets):
        presets.append({"id": preset_id, "name": name.strip(), "icon": "🎲"})
        try:
            with open(_CUSTOM_PRESETS_FILE, "w", encoding="utf-8") as f:
                json.dump(presets, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CAMPAIGN V2] _save_custom_preset: {e}")
    # Ensure it's live in SYSTEMS for the rest of the session
    if preset_id not in SYSTEMS:
        SYSTEMS[preset_id] = GameSystem(
            id=preset_id, name=name.strip(), icon="🎲",
            accent="#5c6bc0",
            compendium_cats=SYSTEMS["custom"].compendium_cats,
            character_template="custom",
            encounter_system="none",
            dice_pool=SYSTEMS["custom"].dice_pool,
            session_label="Session", character_label="Character",
            npc_label="NPC", enemy_label="Enemy",
        )
    return preset_id


def _ensure_custom_presets_in_systems():
    """Load all saved custom presets into the live SYSTEMS dict (call on startup)."""
    from .models import GameSystem
    for preset in _load_custom_presets():
        pid   = preset.get("id", "")
        pname = preset.get("name", "Custom")
        picon = preset.get("icon", "🎲")
        if pid and pid not in SYSTEMS:
            SYSTEMS[pid] = GameSystem(
                id=pid, name=pname, icon=picon,
                accent="#5c6bc0",
                compendium_cats=SYSTEMS["custom"].compendium_cats,
                character_template="custom",
                encounter_system="none",
                dice_pool=SYSTEMS["custom"].dice_pool,
                session_label="Session", character_label="Character",
                npc_label="NPC", enemy_label="Enemy",
            )


# ══════════════════════════════════════════════════════════════════════════════
#  Toast
# ══════════════════════════════════════════════════════════════════════════════

class _Toast(QLabel):
    def __init__(self, message: str, parent=None):
        super().__init__(message, parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.adjustSize()
        QTimer.singleShot(3500, self._dismiss)

    def _dismiss(self):
        self.hide()
        self.deleteLater()


# ══════════════════════════════════════════════════════════════════════════════
#  _NewCampaignDialog  —  two-step wizard
# ══════════════════════════════════════════════════════════════════════════════

class _NewCampaignDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Campaign")
        self.setMinimumSize(660, 520)
        self._system_id = "dnd5e"
        self._step      = 0          # 0 = pick system, 1 = details
        self._build()

    # ── public ────────────────────────────────────────────────────────────────

    def result_data(self) -> dict:
        return {
            "name":        self._name.text().strip(),
            "game_system": self._system_id,
            "status":      self._status.currentText(),
            "description": self._desc.toPlainText().strip(),
            "start_date":  self._start.text().strip(),
        }

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_step0())
        self._stack.addWidget(self._build_step1())

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 10, 16, 14)
        self._back_btn   = QPushButton("← Back")
        self._next_btn   = QPushButton("Next →")
        self._create_btn = QPushButton("Create Campaign")
        self._back_btn.setVisible(False)
        self._create_btn.setVisible(False)
        self._create_btn.setObjectName("accentBtn")
        self._next_btn.setObjectName("accentBtn")
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn.clicked.connect(self._go_next)
        self._create_btn.clicked.connect(self._try_accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._back_btn)
        btn_row.addWidget(self._next_btn)
        btn_row.addWidget(self._create_btn)
        root.addLayout(btn_row)

    def _build_step0(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 10)

        title = QLabel("Choose a Game System")
        title.setObjectName("dialogTitle")
        lay.addWidget(title)
        sub = QLabel("Your choice shapes the compendium, character sheet, and encounter tools.")
        sub.setObjectName("subLabel")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addSpacing(14)

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setContentsMargins(4, 8, 4, 8)
        self._sys_btns: dict[str, QPushButton] = {}
        cols = 4

        # Built-in systems
        all_tiles: list = list(SYSTEM_LIST)

        # Append user-saved custom presets
        for preset in _load_custom_presets():
            pid   = preset.get("id", "")
            pname = preset.get("name", "Custom")
            picon = preset.get("icon", "🎲")
            if pid and pid not in SYSTEMS:
                from .models import GameSystem as _GS
                ps = _GS(
                    id=pid, name=pname, icon=picon,
                    accent="#5c6bc0",
                    compendium_cats=SYSTEMS["custom"].compendium_cats,
                    character_template="custom",
                    encounter_system="none",
                    dice_pool=SYSTEMS["custom"].dice_pool,
                    session_label="Session", character_label="Character",
                    npc_label="NPC", enemy_label="Enemy",
                )
                SYSTEMS[pid] = ps
                all_tiles.append(ps)
            elif pid in SYSTEMS:
                all_tiles.append(SYSTEMS[pid])

        for i, sys in enumerate(all_tiles):
            btn = QPushButton(f"{sys.icon}\n{sys.name}")
            is_preset = sys.id.startswith("custom_") and sys.id != "custom"
            btn.setObjectName("sysCardCustom" if is_preset else "sysCard")
            btn.setProperty("sys_id", sys.id)
            btn.setCheckable(True)
            btn.setFixedHeight(90)
            btn.clicked.connect(lambda checked, sid=sys.id: self._select_system(sid))
            self._sys_btns[sys.id] = btn
            grid.addWidget(btn, i // cols, i % cols)

        lay.addLayout(grid)

        # "Name your system" row — visible only when base "custom" tile is selected
        self._custom_name_row = QWidget()
        cname_lay = QHBoxLayout(self._custom_name_row)
        cname_lay.setContentsMargins(4, 8, 4, 0)
        cname_lay.setSpacing(10)
        cname_lbl = QLabel("System Name:")
        cname_lbl.setFixedWidth(110)
        self._custom_name_edit = QLineEdit()
        self._custom_name_edit.setPlaceholderText(
            "e.g. My Homebrew System  —  leave blank to skip saving as preset"
        )
        cname_lay.addWidget(cname_lbl)
        cname_lay.addWidget(self._custom_name_edit, 1)
        self._custom_name_row.setVisible(False)
        lay.addWidget(self._custom_name_row)

        lay.addStretch()

        # Pre-select first
        self._select_system("dnd5e")
        return w

    def _build_step1(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 10)

        self._sys_header = QLabel()
        self._sys_header.setObjectName("dialogTitle")
        lay.addWidget(self._sys_header)
        lay.addSpacing(8)

        form = QFormLayout()
        form.setSpacing(10)
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. The Shattered Realm")
        self._status = QComboBox()
        self._status.addItems(["Active", "Paused", "Completed", "Archived"])
        self._start = QLineEdit()
        self._start.setPlaceholderText(f"e.g. {date.today().isoformat()}")
        self._desc = QTextEdit()
        self._desc.setPlaceholderText("A brief description or premise…")
        self._desc.setFixedHeight(80)
        form.addRow("Campaign Name *", self._name)
        form.addRow("Status", self._status)
        form.addRow("Start Date", self._start)
        form.addRow("Description", self._desc)
        lay.addLayout(form)
        lay.addStretch()
        return w

    # ── slots ─────────────────────────────────────────────────────────────────

    def _select_system(self, sys_id: str):
        self._system_id = sys_id
        for sid, btn in self._sys_btns.items():
            btn.setChecked(sid == sys_id)
        # Show "Name your system" input only for the base custom tile
        if hasattr(self, "_custom_name_row"):
            self._custom_name_row.setVisible(sys_id == "custom")

    def _go_next(self):
        # If the base "custom" tile was chosen with a name → save as preset
        if self._system_id == "custom":
            cname = getattr(self, "_custom_name_edit", None)
            if cname and cname.text().strip():
                new_id = _save_custom_preset(cname.text().strip())
                self._system_id = new_id
        sys = SYSTEMS.get(self._system_id) or SYSTEMS["custom"]
        self._sys_header.setText(f"{sys.icon}  New {sys.name} Campaign")
        self._stack.setCurrentIndex(1)
        self._back_btn.setVisible(True)
        self._next_btn.setVisible(False)
        self._create_btn.setVisible(True)

    def _go_back(self):
        self._stack.setCurrentIndex(0)
        self._back_btn.setVisible(False)
        self._next_btn.setVisible(True)
        self._create_btn.setVisible(False)

    def _try_accept(self):
        if not self._name.text().strip():
            self._name.setFocus()
            QMessageBox.warning(self, "Required", "Please enter a campaign name.")
            return
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  _EditCampaignDialog
# ══════════════════════════════════════════════════════════════════════════════

class _EditCampaignDialog(QDialog):
    def __init__(self, campaign, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Campaign")
        self.setMinimumWidth(480)
        self._campaign = campaign
        self._build()

    def result_data(self) -> dict:
        return {
            "name":        self._name.text().strip(),
            "status":      self._status.currentText(),
            "description": self._desc.toPlainText().strip(),
            "notes":       self._notes.toPlainText().strip(),
            "start_date":  self._start.text().strip(),
        }

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)

        c = self._campaign
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self._name   = QLineEdit(c.name)
        self._status = QComboBox()
        self._status.addItems(["Active", "Paused", "Completed", "Archived"])
        self._status.setCurrentText(getattr(c, "status", "Active") or "Active")
        self._start  = QLineEdit(getattr(c, "start_date", "") or "")
        self._start.setPlaceholderText("YYYY-MM-DD")
        self._desc   = QTextEdit(getattr(c, "description", "") or "")
        self._desc.setFixedHeight(80)
        self._notes  = QTextEdit(getattr(c, "notes", "") or "")
        self._notes.setFixedHeight(80)
        form.addRow("Name",         self._name)
        form.addRow("Status",       self._status)
        form.addRow("Start Date",   self._start)
        form.addRow("Description",  self._desc)
        form.addRow("Notes",        self._notes)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _try_accept(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Required", "Campaign name is required.")
            return
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  Campaign Card  (used on the campaigns grid page)
# ══════════════════════════════════════════════════════════════════════════════

class _CampaignCard(QFrame):
    clicked          = Signal(int)   # campaign_id
    edit_requested   = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, campaign, stats: dict, parent=None):
        super().__init__(parent)
        self._cid  = campaign.id
        self._name = campaign.name
        self.setObjectName("campaignCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(220, 130)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._build(campaign, stats)

    def _build(self, c, stats: dict):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)

        sys = SYSTEMS.get(getattr(c, "game_system", "") or "", None)

        # System badge
        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        if sys:
            badge = QLabel(f"{sys.icon} {sys.name}")
            badge.setObjectName("sysBadge")
            badge.setStyleSheet(f"color: {sys.accent}; font-size: 10px; font-weight: 600;")
        else:
            badge = QLabel(getattr(c, "game_system", "—") or "—")
            badge.setObjectName("sysBadge")
        badge_row.addWidget(badge)
        badge_row.addStretch()

        status = getattr(c, "status", "Active") or "Active"
        sc = _SUCCESS if status == "Active" else _FG_DIM
        s_lbl = QLabel(status)
        s_lbl.setStyleSheet(f"color: {sc}; font-size: 10px;")
        badge_row.addWidget(s_lbl)
        lay.addLayout(badge_row)

        # Name
        name_lbl = QLabel(c.name)
        name_lbl.setObjectName("cardName")
        name_lbl.setWordWrap(True)
        lay.addWidget(name_lbl)

        lay.addStretch()

        # Stats row
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        for label, key in [("Sessions", "sessions"), ("Characters", "characters")]:
            v = stats.get(key, 0)
            col = QVBoxLayout()
            col.setSpacing(0)
            vl = QLabel(str(v))
            vl.setObjectName("cardStat")
            ll = QLabel(label)
            ll.setStyleSheet(f"color: {_FG_DIM}; font-size: 10px;")
            col.addWidget(vl)
            col.addWidget(ll)
            stat_row.addLayout(col)
        stat_row.addStretch()
        lay.addLayout(stat_row)

    def _show_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("📂  Open",   lambda: self.clicked.emit(self._cid))
        menu.addAction("✏  Edit",   lambda: self.edit_requested.emit(self._cid))
        menu.addSeparator()
        act = menu.addAction("🗑  Delete", lambda: self.delete_requested.emit(self._cid))
        menu.exec(self.mapToGlobal(pos))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._cid)
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  Campaign Gallery  —  card / lightbox / add-photo dialog
# ══════════════════════════════════════════════════════════════════════════════

_GC_W   = 210    # card width
_GC_H   = 248    # card height
_GT_H   = 158    # thumbnail height
_GC_GAP = 14     # grid gap

_STAGE_CYCLE = [""] + list(CampaignGalleryStage.ALL)


class _CampaignGalleryCard(QFrame):
    open_requested         = Signal(int)
    edit_requested         = Signal(object)
    delete_requested       = Signal(object)
    stage_change_requested = Signal(object, str)

    def __init__(self, entry, index: int, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._index = index
        self.setObjectName("galleryCard")
        self.setFixedSize(_GC_W, _GC_H)
        self.setCursor(Qt.PointingHandCursor)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 6)
        lay.setSpacing(4)

        # Thumbnail
        self._thumb = QLabel()
        self._thumb.setObjectName("galleryThumb")
        self._thumb.setFixedSize(_GC_W - 8, _GT_H)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._load_thumb()
        lay.addWidget(self._thumb)

        # Caption
        caption = (getattr(self._entry, "caption", "") or "").strip()
        if caption:
            fm  = self.fontMetrics()
            cap = QLabel(fm.elidedText(caption, Qt.ElideRight, _GC_W - 16))
            cap.setObjectName("galleryCardTitle")
            lay.addWidget(cap)

        # Date + stage row
        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(4)
        date_str = getattr(self._entry, "created_at", "") or ""
        try:
            from datetime import date as _d
            date_str = _d.fromisoformat(date_str[:10]).strftime("%b %d, %Y")
        except Exception:
            date_str = date_str[:10]
        d_lbl = QLabel(f"📅  {date_str}")
        d_lbl.setObjectName("galleryCardDate")
        meta.addWidget(d_lbl)
        meta.addStretch()

        stage = getattr(self._entry, "stage", "") or ""
        sc    = CampaignGalleryStage.COLORS.get(stage, "#404040")
        sl    = CampaignGalleryStage.LABELS.get(stage, stage) if stage else "＋ Stage"
        self._stage_btn = QPushButton(sl)
        self._stage_btn.setObjectName("galleryStageBtn")
        self._stage_btn.setCursor(Qt.PointingHandCursor)
        self._stage_btn.setToolTip("Left-click to cycle  ·  Right-click to choose")
        self._stage_btn.setStyleSheet(
            f"QPushButton#galleryStageBtn{{"
            f"background:{sc}33;color:{sc};"
            f"border:1px solid {sc}55;border-radius:3px;"
            f"padding:0 5px;font-size:10px;font-weight:700;}}"
            f"QPushButton#galleryStageBtn:hover{{background:{sc}55;}}"
        )
        self._stage_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self._stage_btn.clicked.connect(self._cycle_stage)
        self._stage_btn.customContextMenuRequested.connect(self._stage_menu)
        meta.addWidget(self._stage_btn)
        lay.addLayout(meta)

        # Hover overlay (covers thumbnail only)
        self._overlay = QWidget(self)
        self._overlay.setObjectName("galleryCardOverlay")
        self._overlay.setGeometry(4, 4, _GC_W - 8, _GT_H)
        self._overlay.hide()
        ov = QVBoxLayout(self._overlay)
        ov.setAlignment(Qt.AlignCenter)
        ov.setSpacing(8)
        for label, obj_name, sig in [
            ("🔍  View",  "primaryBtn",   lambda: self.open_requested.emit(self._index)),
            ("✏  Edit",  "secondaryBtn",  lambda: self.edit_requested.emit(self._entry)),
            ("Remove",   "dangerBtn",     lambda: self.delete_requested.emit(self._entry)),
        ]:
            b = QPushButton(label)
            b.setObjectName(obj_name)
            b.setFixedWidth(100)
            b.clicked.connect(sig)
            ov.addWidget(b)

    def _load_thumb(self):
        try:
            path = getattr(self._entry, "image_path", "")
            if path and os.path.isfile(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    self._thumb.setPixmap(
                        pix.scaled(_GC_W - 8, _GT_H,
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    return
        except Exception:
            pass
        self._thumb.setText("📷")
        self._thumb.setStyleSheet("font-size:28px;color:#555;background:transparent;")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._overlay.setGeometry(4, 4, self.width() - 8, _GT_H)

    def enterEvent(self, e):
        self._overlay.show(); self._overlay.raise_(); super().enterEvent(e)

    def leaveEvent(self, e):
        self._overlay.hide(); super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.open_requested.emit(self._index)
        super().mousePressEvent(e)

    def _cycle_stage(self):
        current = getattr(self._entry, "stage", "") or ""
        try:    idx = _STAGE_CYCLE.index(current)
        except ValueError: idx = 0
        self.stage_change_requested.emit(self._entry,
                                         _STAGE_CYCLE[(idx + 1) % len(_STAGE_CYCLE)])

    def _stage_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu    = QMenu(self)
        current = getattr(self._entry, "stage", "") or ""
        act = menu.addAction("— None")
        act.setCheckable(True); act.setChecked(current == "")
        act.triggered.connect(lambda: self.stage_change_requested.emit(self._entry, ""))
        menu.addSeparator()
        for s in CampaignGalleryStage.ALL:
            lbl = CampaignGalleryStage.LABELS.get(s, s)
            a   = menu.addAction(lbl)
            a.setCheckable(True); a.setChecked(current == s)
            a.triggered.connect(
                lambda _c=False, _s=s: self.stage_change_requested.emit(self._entry, _s))
        menu.exec(self._stage_btn.mapToGlobal(pos))


# ── Lightbox ───────────────────────────────────────────────────────────────────

class _CampaignPhotoLightbox(QDialog):
    edit_requested   = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, entries: list, start_index: int, parent=None):
        super().__init__(parent)
        self._entries = entries
        self._index   = start_index
        self.setModal(True)
        self.setWindowTitle("Campaign Gallery")
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1100, int(screen.width() * .88)),
                    min(780,  int(screen.height() * .88)))
        self._build()
        self._show(self._index)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setObjectName("lightboxHeader"); hdr.setFixedHeight(44)
        hl  = QHBoxLayout(hdr); hl.setContentsMargins(16, 0, 12, 0)
        self._counter = QLabel(); self._counter.setObjectName("lightboxCounter")
        hl.addWidget(self._counter); hl.addStretch()
        cl = QPushButton("✕  Close"); cl.setObjectName("ghostBtn")
        cl.setFixedHeight(28); cl.clicked.connect(self.accept)
        hl.addWidget(cl)
        root.addWidget(hdr)

        # Image area
        img_row = QHBoxLayout(); img_row.setContentsMargins(0, 0, 0, 0); img_row.setSpacing(0)
        self._prev = QPushButton("‹"); self._prev.setObjectName("lightboxNavBtn")
        self._prev.setFixedWidth(48); self._prev.clicked.connect(self._go_prev)
        self._next = QPushButton("›"); self._next.setObjectName("lightboxNavBtn")
        self._next.setFixedWidth(48); self._next.clicked.connect(self._go_next)
        self._img  = QLabel(); self._img.setObjectName("lightboxImage")
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        img_row.addWidget(self._prev)
        img_row.addWidget(self._img, 1)
        img_row.addWidget(self._next)
        root.addLayout(img_row, 1)

        # Info bar
        info = QWidget(); info.setObjectName("lightboxInfo"); info.setFixedHeight(100)
        il   = QVBoxLayout(info); il.setContentsMargins(24, 10, 24, 10); il.setSpacing(4)
        tr   = QHBoxLayout(); tr.setSpacing(8)
        self._cap_lbl = QLabel(); self._cap_lbl.setObjectName("lightboxTitle")
        tr.addWidget(self._cap_lbl, 1)
        eb = QPushButton("✏  Edit"); eb.setObjectName("secondaryBtn")
        eb.setFixedHeight(28); eb.clicked.connect(self._on_edit); tr.addWidget(eb)
        db = QPushButton("Remove"); db.setObjectName("dangerBtn")
        db.setFixedHeight(28); db.clicked.connect(self._on_delete); tr.addWidget(db)
        il.addLayout(tr)
        mr = QHBoxLayout(); mr.setSpacing(16)
        self._date_lbl  = QLabel(); self._date_lbl.setObjectName("lightboxMeta")
        self._stage_lbl = QLabel(); self._stage_lbl.setObjectName("lightboxMeta")
        mr.addWidget(self._date_lbl); mr.addWidget(self._stage_lbl); mr.addStretch()
        il.addLayout(mr)
        root.addWidget(info)

    def _show(self, idx: int):
        if not self._entries: return
        self._index = max(0, min(idx, len(self._entries) - 1))
        e = self._entries[self._index]
        n = len(self._entries)
        self._counter.setText(f"Photo {self._index + 1} of {n}")
        self._prev.setEnabled(self._index > 0)
        self._next.setEnabled(self._index < n - 1)

        iw = self.width() - 96
        ih = self.height() - 144
        try:
            path = getattr(e, "image_path", "")
            if path and os.path.isfile(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    self._img.setPixmap(pix.scaled(iw, ih, Qt.KeepAspectRatio,
                                                    Qt.SmoothTransformation))
                else:
                    self._img.setText("⚠  Could not load image")
            else:
                self._img.setText("⚠  File not found")
        except Exception:
            self._img.setText("⚠  Error")

        self._cap_lbl.setText(getattr(e, "caption", "") or "Untitled")

        date_str = getattr(e, "created_at", "") or ""
        try:
            from datetime import date as _d
            date_str = _d.fromisoformat(date_str[:10]).strftime("%B %d, %Y")
        except Exception:
            pass
        self._date_lbl.setText(f"📅  {date_str}")

        stage = getattr(e, "stage", "") or ""
        if stage:
            color = CampaignGalleryStage.COLORS.get(stage, "#888")
            label = CampaignGalleryStage.LABELS.get(stage, stage)
            self._stage_lbl.setText(f"● {label}")
            self._stage_lbl.setStyleSheet(f"color:{color};")
            self._stage_lbl.show()
        else:
            self._stage_lbl.hide()

    def _go_prev(self): self._show(self._index - 1)
    def _go_next(self): self._show(self._index + 1)

    def keyPressEvent(self, e):
        k = e.key()
        if   k == Qt.Key_Left:  self._go_prev()
        elif k == Qt.Key_Right: self._go_next()
        elif k in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Space): self.accept()
        else: super().keyPressEvent(e)

    def _on_edit(self):
        self.edit_requested.emit(self._entries[self._index]); self.accept()

    def _on_delete(self):
        self.delete_requested.emit(self._entries[self._index]); self.accept()


# ── Add / Edit Photo Dialog ────────────────────────────────────────────────────

class _CampaignAddPhotoDialog(QDialog):
    def __init__(self, entry=None, parent=None):
        super().__init__(parent)
        self._entry  = entry
        self._path:  Optional[str] = None
        self._result: Optional[dict] = None
        self.setWindowTitle("Edit Photo" if entry else "Add Photo")
        self.setModal(True)
        self.setMinimumSize(500, 520)
        self._build()
        if entry:
            self._populate(entry)

    def get_values(self) -> dict:
        return self._result or {}

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # Preview
        pf = QFrame(); pf.setObjectName("galleryImgPreviewFrame"); pf.setFixedHeight(200)
        pl = QVBoxLayout(pf); pl.setContentsMargins(0,0,0,0); pl.setAlignment(Qt.AlignCenter)
        self._preview = QLabel("No photo selected")
        self._preview.setObjectName("galleryImgPreview")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setFixedSize(456, 192)
        pl.addWidget(self._preview)
        root.addWidget(pf)

        # Browse row
        br = QHBoxLayout()
        bb = QPushButton("🖼  Browse…"); bb.setObjectName("secondaryBtn")
        bb.setFixedHeight(30); bb.clicked.connect(self._browse)
        self._file_lbl = QLabel("No file selected"); self._file_lbl.setObjectName("dimLabel")
        br.addWidget(bb); br.addWidget(self._file_lbl, 1)
        root.addLayout(br)

        # Form
        form = QGridLayout(); form.setSpacing(8); form.setColumnMinimumWidth(0, 100)
        form.setColumnStretch(1, 1)
        form.addWidget(QLabel("Caption"), 0, 0)
        self._caption = QLineEdit()
        self._caption.setPlaceholderText("e.g. Session 3 — the dragon fight")
        self._caption.setFixedHeight(30)
        form.addWidget(self._caption, 0, 1)
        form.addWidget(QLabel("Stage"), 1, 0)
        self._stage = QComboBox(); self._stage.setFixedHeight(30)
        self._stage.addItem("— None —", "")
        for s in CampaignGalleryStage.ALL:
            self._stage.addItem(CampaignGalleryStage.LABELS[s], s)
        form.addWidget(self._stage, 1, 1)
        root.addLayout(form)
        root.addStretch()

        # Buttons
        btn_row = QHBoxLayout(); btn_row.addStretch()
        cancel = QPushButton("Cancel"); cancel.setObjectName("ghostBtn")
        cancel.clicked.connect(self.reject); btn_row.addWidget(cancel)
        save = QPushButton("Save Changes" if self._entry else "Add Photo")
        save.setObjectName("primaryBtn"); save.setFixedHeight(34)
        save.clicked.connect(self._on_save); btn_row.addWidget(save)
        root.addLayout(btn_row)

    def _populate(self, e):
        self._path = getattr(e, "image_path", None)
        self._caption.setText(getattr(e, "caption", "") or "")
        stage = getattr(e, "stage", "") or ""
        for i in range(self._stage.count()):
            if self._stage.itemData(i) == stage:
                self._stage.setCurrentIndex(i); break
        if self._path and os.path.isfile(self._path):
            self._load_preview(self._path)
            self._file_lbl.setText(os.path.basename(self._path))

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Photo", "",
            "Images (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tiff *.tif)")
        if path:
            self._path = path
            self._file_lbl.setText(os.path.basename(path))
            self._load_preview(path)

    def _load_preview(self, path: str):
        try:
            pix = QPixmap(path)
            if not pix.isNull():
                self._preview.setPixmap(
                    pix.scaled(452, 188, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        except Exception:
            pass
        self._preview.setText("Preview unavailable")

    def _on_save(self):
        if not self._entry and not self._path:
            QMessageBox.warning(self, "No Photo", "Please select a photo first.")
            return
        self._result = {
            "image_path": self._path or (getattr(self._entry, "image_path", "") if self._entry else ""),
            "caption":    self._caption.text().strip(),
            "stage":      self._stage.currentData() or "",
        }
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  CampaignV2UI  —  main widget
# ══════════════════════════════════════════════════════════════════════════════

class CampaignV2UI(QWidget):
    def __init__(self, service, context, parent=None):
        super().__init__(parent)
        self._svc      = service
        self._ctx      = context
        self._camp_id: Optional[int] = None
        self._camp     = None
        self._sys_id   = "custom"

        # Gallery state
        self._gallery_entries: list = []
        self._gallery_stage_filter: str = ""

        # Encounter state
        self._enc_id: Optional[int] = None
        self._enc_obj = None

        # Compendium search / book filter state
        self._comp_search_mode: bool = False
        self._comp_search_results: list = []
        self._disabled_books: set[str] = set()

        # Assets state
        self._asset_cat_filter: str = "all"

        # Quest state
        self._quest_status_filter: str = "all"
        self._quest_id: Optional[int] = None
        self._quest_search_active: bool = False

        _ensure_custom_presets_in_systems()  # load any saved custom presets into SYSTEMS
        self._build()
        self._apply_theme()
        QTimer.singleShot(0, self._load_campaigns)

    # ── Build skeleton ─────────────────────────────────────────────────────────

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left sidebar ──────────────────────────────────────────────────────
        self._sidebar = QFrame()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(170)
        sb_lay = QVBoxLayout(self._sidebar)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        sb_lay.setSpacing(0)

        # App header
        header = QFrame()
        header.setObjectName("sidebarHeader")
        hh = QVBoxLayout(header)
        hh.setContentsMargins(14, 14, 14, 10)
        title = QLabel("Campaign\nCommand")
        title.setObjectName("appTitle")
        ver = QLabel("2.0")
        ver.setObjectName("appVer")
        hh.addWidget(title)
        hh.addWidget(ver)
        sb_lay.addWidget(header)

        # Back to campaigns button (hidden until a campaign is open)
        self._back_btn = QPushButton("‹ All Campaigns")
        self._back_btn.setObjectName("backBtn")
        self._back_btn.setVisible(False)
        self._back_btn.clicked.connect(self._close_campaign)
        sb_lay.addWidget(self._back_btn)

        # Campaign name label (shown when campaign is open)
        self._camp_label = QLabel()
        self._camp_label.setObjectName("campLabel")
        self._camp_label.setWordWrap(True)
        self._camp_label.setContentsMargins(14, 6, 14, 4)
        self._camp_label.setVisible(False)
        sb_lay.addWidget(self._camp_label)

        # Nav buttons
        self._nav_btns: dict[int, QPushButton] = {}
        self._nav_frame = QFrame()
        nav_lay = QVBoxLayout(self._nav_frame)
        nav_lay.setContentsMargins(6, 4, 6, 4)
        nav_lay.setSpacing(2)
        for sec, icon, label in _NAV_ITEMS:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setProperty("sec", sec)
            btn.clicked.connect(lambda _, s=sec: self._go_section(s))
            nav_lay.addWidget(btn)
            self._nav_btns[sec] = btn
        nav_lay.addStretch()
        self._nav_frame.setVisible(False)
        sb_lay.addWidget(self._nav_frame)
        sb_lay.addStretch()

        root.addWidget(self._sidebar)

        # ── Content area ──────────────────────────────────────────────────────
        content = QFrame()
        content.setObjectName("contentArea")
        c_lay = QVBoxLayout(content)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(0)

        self._stack = QStackedWidget()
        c_lay.addWidget(self._stack)

        # Build pages in order (indices must match _SEC_* constants)
        self._stack.addWidget(self._build_campaigns_page())   # 0
        self._stack.addWidget(self._build_overview_page())    # 1
        self._stack.addWidget(self._build_sessions_page())    # 2
        self._stack.addWidget(self._build_characters_page())  # 3
        self._stack.addWidget(self._build_encounters_page())  # 4
        self._stack.addWidget(self._build_compendium_page())  # 5
        self._stack.addWidget(self._build_gallery_page())     # 6
        self._stack.addWidget(self._build_dice_page())        # 7
        self._stack.addWidget(self._build_assets_page())      # 8
        self._stack.addWidget(self._build_quests_page())      # 9

        root.addWidget(content, 1)

    # ══════════════════════════════════════════════════════════════════════════
    #  Page builders
    # ══════════════════════════════════════════════════════════════════════════

    # ── 0 · Campaigns ─────────────────────────────────────────────────────────

    def _build_campaigns_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Campaigns")
        title.setObjectName("pageTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        self._camp_search = QLineEdit()
        self._camp_search.setPlaceholderText("Search campaigns…")
        self._camp_search.setFixedWidth(200)
        self._camp_search.textChanged.connect(self._filter_campaigns)
        hdr.addWidget(self._camp_search)
        new_btn = QPushButton("＋  New Campaign")
        new_btn.setObjectName("accentBtn")
        new_btn.clicked.connect(self._on_new_campaign)
        hdr.addSpacing(8)
        hdr.addWidget(new_btn)
        lay.addLayout(hdr)
        lay.addSpacing(18)

        # Scroll area for card grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._camp_grid_container = QWidget()
        self._camp_grid = QGridLayout(self._camp_grid_container)
        self._camp_grid.setSpacing(14)
        self._camp_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._camp_grid_container)
        lay.addWidget(scroll, 1)

        # Empty state label (hidden when cards exist)
        self._camp_empty = QLabel("No campaigns yet.\nClick ＋ New Campaign to get started.")
        self._camp_empty.setObjectName("emptyState")
        self._camp_empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._camp_empty)
        self._camp_empty.setVisible(False)

        return w

    # ── 1 · Overview ──────────────────────────────────────────────────────────

    def _build_overview_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        # Header row
        hdr = QHBoxLayout()
        self._ov_title = QLabel("Overview")
        self._ov_title.setObjectName("pageTitle")
        hdr.addWidget(self._ov_title)
        hdr.addStretch()
        edit_btn = QPushButton("✏  Edit Campaign")
        edit_btn.setObjectName("ghostBtn")
        edit_btn.clicked.connect(self._on_edit_campaign)
        hdr.addWidget(edit_btn)
        hdr.addSpacing(6)
        del_camp_btn = QPushButton("🗑  Delete Campaign")
        del_camp_btn.setObjectName("dangerBtn")
        del_camp_btn.clicked.connect(self._on_delete_campaign)
        hdr.addWidget(del_camp_btn)
        lay.addLayout(hdr)

        # System + description
        self._ov_system = QLabel()
        self._ov_system.setObjectName("subLabel")
        lay.addWidget(self._ov_system)
        self._ov_desc = QLabel()
        self._ov_desc.setObjectName("dimLabel")
        self._ov_desc.setWordWrap(True)
        lay.addWidget(self._ov_desc)

        # Stats strip
        stats_frame = QFrame()
        stats_frame.setObjectName("statsStrip")
        stats_row = QHBoxLayout(stats_frame)
        stats_row.setContentsMargins(16, 12, 16, 12)
        stats_row.setSpacing(30)
        self._ov_stats: dict[str, QLabel] = {}
        for key in ["sessions", "characters", "encounters", "compendium", "gallery"]:
            col = QVBoxLayout()
            col.setSpacing(2)
            val = QLabel("0")
            val.setObjectName("statValue")
            val.setAlignment(Qt.AlignCenter)
            lbl = QLabel(key.capitalize())
            lbl.setObjectName("statLabel")
            lbl.setAlignment(Qt.AlignCenter)
            col.addWidget(val)
            col.addWidget(lbl)
            stats_row.addLayout(col)
            self._ov_stats[key] = val
        stats_row.addStretch()
        lay.addWidget(stats_frame)

        # Recent sessions
        recent_lbl = QLabel("Recent Sessions")
        recent_lbl.setObjectName("sectionLabel")
        lay.addWidget(recent_lbl)
        self._ov_recent = QListWidget()
        self._ov_recent.setObjectName("recentList")
        self._ov_recent.setMaximumHeight(160)
        self._ov_recent.itemDoubleClicked.connect(
            lambda: self._go_section(_SEC_SESSIONS))
        lay.addWidget(self._ov_recent)

        lay.addStretch()
        return w

    # ── 2 · Sessions ──────────────────────────────────────────────────────────

    def _build_sessions_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        hdr = QHBoxLayout()
        self._ses_title = QLabel("Sessions")
        self._ses_title.setObjectName("pageTitle")
        hdr.addWidget(self._ses_title)
        hdr.addStretch()
        add_btn = QPushButton("＋  Log Session")
        add_btn.setObjectName("accentBtn")
        add_btn.clicked.connect(self._on_new_session)
        hdr.addWidget(add_btn)
        lay.addLayout(hdr)

        splitter = QSplitter(Qt.Horizontal)

        # Left list
        left = QFrame()
        left.setObjectName("panelFrame")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self._ses_list = QListWidget()
        self._ses_list.setObjectName("sideList")
        self._ses_list.currentRowChanged.connect(self._on_session_selected)
        self._ses_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._ses_list.customContextMenuRequested.connect(self._ses_list_context_menu)
        ll.addWidget(self._ses_list)
        splitter.addWidget(left)

        # Right detail
        right = QFrame()
        right.setObjectName("panelFrame")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18, 16, 18, 16)
        rl.setSpacing(10)
        self._ses_detail = _SessionDetail()
        self._ses_detail.edit_requested.connect(self._on_edit_session)
        self._ses_detail.delete_requested.connect(self._on_delete_session)
        rl.addWidget(self._ses_detail)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        lay.addWidget(splitter, 1)
        return w

    # ── 3 · Characters ────────────────────────────────────────────────────────

    def _build_characters_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        hdr = QHBoxLayout()
        self._char_title = QLabel("Characters")
        self._char_title.setObjectName("pageTitle")
        hdr.addWidget(self._char_title)
        hdr.addStretch()
        add_btn = QPushButton("＋  Add Character")
        add_btn.setObjectName("accentBtn")
        add_btn.clicked.connect(self._on_new_character)
        hdr.addWidget(add_btn)
        lay.addLayout(hdr)

        splitter = QSplitter(Qt.Horizontal)

        left = QFrame()
        left.setObjectName("panelFrame")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self._char_list = QListWidget()
        self._char_list.setObjectName("sideList")
        self._char_list.currentRowChanged.connect(self._on_character_selected)
        self._char_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._char_list.customContextMenuRequested.connect(self._char_list_context_menu)
        ll.addWidget(self._char_list)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("panelFrame")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18, 16, 18, 16)
        self._char_detail = _CharacterDetail(service=self._svc)
        self._char_detail.edit_requested.connect(self._on_edit_character)
        self._char_detail.delete_requested.connect(self._on_delete_character)
        rl.addWidget(self._char_detail)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        lay.addWidget(splitter, 1)
        return w

    # ── 4 · Encounters ────────────────────────────────────────────────────────

    def _build_encounters_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        self._enc_page_title = QLabel("Encounters")
        self._enc_page_title.setObjectName("pageTitle")
        hdr.addWidget(self._enc_page_title)
        hdr.addStretch()
        add_enc_btn = QPushButton("＋  New Encounter")
        add_enc_btn.setObjectName("accentBtn")
        add_enc_btn.clicked.connect(self._on_new_encounter)
        hdr.addWidget(add_enc_btn)
        lay.addLayout(hdr)

        # ── Splitter: list | detail ───────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("encSplitter")

        # Left — encounter list
        left = QFrame()
        left.setObjectName("encListPanel")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)

        self._enc_list = QListWidget()
        self._enc_list.setObjectName("encList")
        self._enc_list.currentRowChanged.connect(self._on_enc_select)
        left_lay.addWidget(self._enc_list)

        enc_btn_row = QHBoxLayout()
        self._enc_del_btn = QPushButton("✕  Delete")
        self._enc_del_btn.setObjectName("dangerBtn")
        self._enc_del_btn.setEnabled(False)
        self._enc_del_btn.clicked.connect(self._on_delete_encounter)
        enc_btn_row.addStretch()
        enc_btn_row.addWidget(self._enc_del_btn)
        left_lay.addLayout(enc_btn_row)

        # Right — stacked: empty state | detail
        self._enc_right = QStackedWidget()

        # Empty state (index 0)
        enc_empty = QLabel("Select an encounter\nor create a new one.")
        enc_empty.setObjectName("emptyState")
        enc_empty.setAlignment(Qt.AlignCenter)
        self._enc_right.addWidget(enc_empty)

        # Detail panel (index 1)
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.NoFrame)
        detail_w = QWidget()
        detail_lay = QVBoxLayout(detail_w)
        detail_lay.setContentsMargins(20, 16, 20, 20)
        detail_lay.setSpacing(14)

        # Name + difficulty row
        name_row = QHBoxLayout()
        self._enc_name_edit = QLineEdit()
        self._enc_name_edit.setObjectName("encNameEdit")
        self._enc_name_edit.setPlaceholderText("Encounter name…")
        self._enc_name_edit.editingFinished.connect(self._on_enc_name_commit)
        self._enc_diff_badge = QLabel()
        self._enc_diff_badge.setObjectName("diffBadge")
        self._enc_diff_badge.setFixedWidth(90)
        self._enc_diff_badge.setAlignment(Qt.AlignCenter)
        name_row.addWidget(self._enc_name_edit, 1)
        name_row.addSpacing(8)
        name_row.addWidget(self._enc_diff_badge)
        detail_lay.addLayout(name_row)

        # Description
        self._enc_desc_edit = QTextEdit()
        self._enc_desc_edit.setObjectName("encDescEdit")
        self._enc_desc_edit.setPlaceholderText("Notes, description, setup…")
        self._enc_desc_edit.setMaximumHeight(80)
        self._enc_desc_edit.focusOutEvent = self._enc_desc_focus_out
        detail_lay.addWidget(self._enc_desc_edit)

        # ── Difficulty calculator (shown for cr_xp / xp_budget systems) ──────
        self._enc_calc_frame = QFrame()
        self._enc_calc_frame.setObjectName("sectionCard")
        calc_lay = QVBoxLayout(self._enc_calc_frame)
        calc_lay.setContentsMargins(14, 12, 14, 12)
        calc_lay.setSpacing(10)

        calc_hdr = QLabel("Difficulty Calculator")
        calc_hdr.setObjectName("sectionLabel")
        calc_lay.addWidget(calc_hdr)

        # Party row
        party_row = QHBoxLayout()
        party_row.setSpacing(12)
        party_lbl = QLabel("Party:")
        party_row.addWidget(party_lbl)
        self._enc_party_size = QSpinBox()
        self._enc_party_size.setRange(1, 20)
        self._enc_party_size.setValue(4)
        self._enc_party_size.setPrefix("× ")
        self._enc_party_size.setFixedWidth(70)
        party_row.addWidget(self._enc_party_size)
        lvl_lbl = QLabel("Level:")
        party_row.addWidget(lvl_lbl)
        self._enc_party_level = QSpinBox()
        self._enc_party_level.setRange(1, 20)
        self._enc_party_level.setValue(1)
        self._enc_party_level.setFixedWidth(60)
        party_row.addWidget(self._enc_party_level)
        party_row.addStretch()
        self._enc_party_size.valueChanged.connect(self._recalc_encounter)
        self._enc_party_level.valueChanged.connect(self._recalc_encounter)
        calc_lay.addLayout(party_row)

        # Thresholds display (D&D 5e only)
        self._enc_thresh_lbl = QLabel()
        self._enc_thresh_lbl.setObjectName("dimLabel")
        self._enc_thresh_lbl.setWordWrap(True)
        calc_lay.addWidget(self._enc_thresh_lbl)

        # Result row
        result_row = QHBoxLayout()
        self._enc_xp_lbl = QLabel("Total XP: —")
        self._enc_xp_lbl.setObjectName("statValue")
        self._enc_result_lbl = QLabel()
        self._enc_result_lbl.setObjectName("diffBadgeLarge")
        result_row.addWidget(self._enc_xp_lbl)
        result_row.addStretch()
        result_row.addWidget(self._enc_result_lbl)
        calc_lay.addLayout(result_row)

        detail_lay.addWidget(self._enc_calc_frame)

        # ── Enemies list ──────────────────────────────────────────────────────
        enemies_hdr = QHBoxLayout()
        self._enc_enemy_section_lbl = QLabel("Enemies")
        self._enc_enemy_section_lbl.setObjectName("sectionLabel")
        enemies_hdr.addWidget(self._enc_enemy_section_lbl)
        enemies_hdr.addStretch()
        if _GAME_DATA_AVAILABLE:
            _browse_books_btn = QPushButton("📚  Browse Books…")
            _browse_books_btn.setObjectName("ghostBtn")
            _browse_books_btn.clicked.connect(self._on_browse_monsters_for_encounter)
            enemies_hdr.addWidget(_browse_books_btn)
            enemies_hdr.addSpacing(4)
        _custom_mon_btn = QPushButton("🧟  Custom…")
        _custom_mon_btn.setObjectName("ghostBtn")
        _custom_mon_btn.clicked.connect(self._on_open_custom_monsters)
        enemies_hdr.addWidget(_custom_mon_btn)
        detail_lay.addLayout(enemies_hdr)

        self._enc_monster_list = QListWidget()
        self._enc_monster_list.setObjectName("monsterList")
        self._enc_monster_list.setMinimumHeight(160)
        self._enc_monster_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._enc_monster_list.customContextMenuRequested.connect(
            self._enc_monster_context_menu)
        self._enc_monster_list.itemDoubleClicked.connect(
            self._on_edit_monster_dblclick)
        detail_lay.addWidget(self._enc_monster_list)

        # Quick-add enemy row
        add_enemy_row = QHBoxLayout()
        add_enemy_row.setSpacing(6)
        self._enc_enemy_name = QLineEdit()
        self._enc_enemy_name.setPlaceholderText("Quick-add name…")
        self._enc_enemy_cr = QLineEdit()
        self._enc_enemy_cr.setPlaceholderText("CR")
        self._enc_enemy_cr.setFixedWidth(56)
        self._enc_enemy_count = QSpinBox()
        self._enc_enemy_count.setRange(1, 99)
        self._enc_enemy_count.setValue(1)
        self._enc_enemy_count.setFixedWidth(56)
        add_enemy_btn = QPushButton("Add")
        add_enemy_btn.setObjectName("accentBtn")
        add_enemy_btn.setFixedWidth(52)
        add_enemy_btn.clicked.connect(self._on_add_monster)
        self._enc_remove_enemy_btn = QPushButton("✕")
        self._enc_remove_enemy_btn.setObjectName("dangerBtn")
        self._enc_remove_enemy_btn.setFixedWidth(32)
        self._enc_remove_enemy_btn.setToolTip("Remove selected")
        self._enc_remove_enemy_btn.setEnabled(False)
        self._enc_remove_enemy_btn.clicked.connect(self._on_remove_monster)
        self._enc_monster_list.currentRowChanged.connect(
            lambda row: self._enc_remove_enemy_btn.setEnabled(row >= 0))

        add_enemy_row.addWidget(self._enc_enemy_name, 2)
        add_enemy_row.addWidget(QLabel("CR:"))
        add_enemy_row.addWidget(self._enc_enemy_cr)
        add_enemy_row.addWidget(QLabel("×"))
        add_enemy_row.addWidget(self._enc_enemy_count)
        add_enemy_row.addWidget(add_enemy_btn)
        add_enemy_row.addWidget(self._enc_remove_enemy_btn)
        detail_lay.addLayout(add_enemy_row)

        run_init_btn = QPushButton("▶  Run Initiative")
        run_init_btn.setObjectName("accentBtn")
        run_init_btn.clicked.connect(self._on_run_initiative)
        detail_lay.addWidget(run_init_btn)

        detail_lay.addStretch()
        detail_scroll.setWidget(detail_w)
        self._enc_right.addWidget(detail_scroll)

        splitter.addWidget(left)
        splitter.addWidget(self._enc_right)
        splitter.setSizes([220, 600])

        # Wrap builder + initiative in tabs
        self._enc_tab_widget = QTabWidget()
        self._enc_tab_widget.setObjectName("encTabWidget")

        builder_wrapper = QWidget()
        bw_lay = QVBoxLayout(builder_wrapper)
        bw_lay.setContentsMargins(0, 0, 0, 0)
        bw_lay.addWidget(splitter)
        self._enc_tab_widget.addTab(builder_wrapper, "🗡  Encounters")

        self._initiative_tracker = _InitiativeTracker(self._svc)
        self._enc_tab_widget.addTab(self._initiative_tracker, "⚔  Initiative")

        lay.addWidget(self._enc_tab_widget, 1)
        return w

    # ── 5 · Compendium ────────────────────────────────────────────────────────

    def _build_compendium_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # ── Header row ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        lbl = QLabel("Compendium")
        lbl.setObjectName("pageTitle")
        hdr.addWidget(lbl)
        hdr.addSpacing(16)

        # Global search bar
        self._comp_search = QLineEdit()
        self._comp_search.setObjectName("compSearchBar")
        self._comp_search.setPlaceholderText("🔍  Search all entries…")
        self._comp_search.setFixedWidth(240)
        self._comp_search.textChanged.connect(self._on_comp_search)
        hdr.addWidget(self._comp_search)

        # Clear button (only visible when searching)
        self._comp_search_clear = QPushButton("✕")
        self._comp_search_clear.setObjectName("compSearchClear")
        self._comp_search_clear.setFixedSize(24, 24)
        self._comp_search_clear.setVisible(False)
        self._comp_search_clear.clicked.connect(self._comp_search.clear)
        hdr.addWidget(self._comp_search_clear)

        hdr.addStretch()

        # Books manager button
        self._books_btn = QPushButton("📚  Books")
        self._books_btn.setObjectName("ghostBtn")
        self._books_btn.setVisible(_GAME_DATA_AVAILABLE)
        self._books_btn.clicked.connect(self._on_manage_books)
        hdr.addWidget(self._books_btn)
        hdr.addSpacing(4)

        self._browse_data_btn = QPushButton("🗂  Browse Game Data")
        self._browse_data_btn.setObjectName("ghostBtn")
        self._browse_data_btn.clicked.connect(self._on_browse_game_data)
        self._browse_data_btn.setVisible(_GAME_DATA_AVAILABLE)
        hdr.addWidget(self._browse_data_btn)
        hdr.addSpacing(6)
        add_btn = QPushButton("＋  New Entry")
        add_btn.setObjectName("accentBtn")
        add_btn.clicked.connect(self._on_new_compendium_entry)
        hdr.addWidget(add_btn)
        lay.addLayout(hdr)

        splitter = QSplitter(Qt.Horizontal)

        # Category list
        cat_frame = QFrame()
        cat_frame.setObjectName("panelFrame")
        cl = QVBoxLayout(cat_frame)
        cl.setContentsMargins(0, 0, 0, 0)
        self._comp_cat_hdr = QLabel("Categories")
        self._comp_cat_hdr.setObjectName("panelHeader")
        cl.addWidget(self._comp_cat_hdr)
        self._comp_cats = QListWidget()
        self._comp_cats.setObjectName("sideList")
        self._comp_cats.currentRowChanged.connect(self._on_comp_category_selected)
        cl.addWidget(self._comp_cats)
        splitter.addWidget(cat_frame)

        # Entry list
        entry_frame = QFrame()
        entry_frame.setObjectName("panelFrame")
        el = QVBoxLayout(entry_frame)
        el.setContentsMargins(0, 0, 0, 0)
        self._comp_entry_hdr = QLabel("Entries")
        self._comp_entry_hdr.setObjectName("panelHeader")
        el.addWidget(self._comp_entry_hdr)
        self._comp_entries = QListWidget()
        self._comp_entries.setObjectName("sideList")
        self._comp_entries.currentRowChanged.connect(self._on_comp_entry_selected)
        self._comp_entries.setContextMenuPolicy(Qt.CustomContextMenu)
        self._comp_entries.customContextMenuRequested.connect(self._comp_entry_context_menu)
        el.addWidget(self._comp_entries)
        splitter.addWidget(entry_frame)

        # Entry viewer
        view_frame = QFrame()
        view_frame.setObjectName("panelFrame")
        vl = QVBoxLayout(view_frame)
        vl.setContentsMargins(14, 12, 14, 12)
        vl.setSpacing(8)
        self._comp_view_title = QLabel()
        self._comp_view_title.setObjectName("cardName")
        self._comp_view_title.setWordWrap(True)
        self._comp_view_tags = QLabel()
        self._comp_view_tags.setObjectName("dimLabel")
        self._comp_view_body = QTextEdit()
        self._comp_view_body.setReadOnly(True)
        self._comp_view_body.setObjectName("compBody")
        comp_btn_row = QHBoxLayout()
        self._comp_edit_btn = QPushButton("✏ Edit")
        self._comp_edit_btn.setObjectName("ghostBtn")
        self._comp_edit_btn.clicked.connect(self._on_edit_compendium_entry)
        self._comp_del_btn = QPushButton("Delete")
        self._comp_del_btn.setObjectName("dangerBtn")
        self._comp_del_btn.clicked.connect(self._on_delete_compendium_entry)
        comp_btn_row.addWidget(self._comp_edit_btn)
        comp_btn_row.addStretch()
        comp_btn_row.addWidget(self._comp_del_btn)
        vl.addWidget(self._comp_view_title)
        vl.addWidget(self._comp_view_tags)
        vl.addWidget(self._comp_view_body, 1)
        vl.addLayout(comp_btn_row)
        self._comp_edit_btn.setVisible(False)
        self._comp_del_btn.setVisible(False)
        splitter.addWidget(view_frame)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)
        lay.addWidget(splitter, 1)

        self._comp_current_cat  = ""
        self._comp_current_eid  = None
        return w

    # ── 6 · Gallery ───────────────────────────────────────────────────────────

    def _build_gallery_page(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Toolbar
        toolbar = QWidget(); toolbar.setObjectName("galleryToolbar")
        tl = QHBoxLayout(toolbar); tl.setContentsMargins(24, 12, 24, 10); tl.setSpacing(10)
        self._gallery_title_lbl = QLabel("Gallery")
        self._gallery_title_lbl.setObjectName("pageTitle")
        self._gallery_count_lbl = QLabel()
        self._gallery_count_lbl.setObjectName("dimLabel")
        tl.addWidget(self._gallery_title_lbl)
        tl.addWidget(self._gallery_count_lbl)
        tl.addStretch()
        add_btn = QPushButton("📸  Add Photo")
        add_btn.setObjectName("accentBtn")
        add_btn.clicked.connect(self._on_add_photo)
        tl.addWidget(add_btn)
        lay.addWidget(toolbar)

        # Stage filter chips
        chip_bar = QWidget(); chip_bar.setObjectName("galleryChipBar")
        cl = QHBoxLayout(chip_bar); cl.setContentsMargins(24, 6, 24, 6); cl.setSpacing(6)
        self._gallery_chips: dict[str, QPushButton] = {}
        for label, val in [("All", "")] + [
                (CampaignGalleryStage.LABELS[s], s) for s in CampaignGalleryStage.ALL]:
            btn = QPushButton(label)
            btn.setObjectName("chipActive" if val == "" else "chip")
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _=False, v=val: self._set_gallery_filter(v))
            self._gallery_chips[val] = btn
            cl.addWidget(btn)
        cl.addStretch()
        lay.addWidget(chip_bar)

        # Scrollable grid
        self._gallery_scroll = QScrollArea()
        self._gallery_scroll.setWidgetResizable(True)
        self._gallery_scroll.setFrameShape(QFrame.NoFrame)
        self._gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._gallery_scroll.setWidget(QWidget())
        lay.addWidget(self._gallery_scroll, 1)
        return page

    # ── 9 · Quests ────────────────────────────────────────────────────────────

    def _build_quests_page(self) -> QWidget:
        w = QWidget()
        root = QHBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel ────────────────────────────────────────────────────
        left = QFrame()
        left.setObjectName("questLeftPanel")
        left.setFixedWidth(220)
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(0)

        # ── Top: title + add button ───────────────────────────────────────
        lhdr = QFrame()
        lhdr.setObjectName("questLeftHdr")
        lhdr_lay = QHBoxLayout(lhdr)
        lhdr_lay.setContentsMargins(14, 12, 10, 12)
        lhdr_lay.setSpacing(8)
        qlbl = QLabel("Quests")
        qlbl.setObjectName("questPanelTitle")
        new_q_btn = QPushButton("+ New")
        new_q_btn.setObjectName("questAddBtn")
        new_q_btn.setFixedHeight(28)
        new_q_btn.clicked.connect(self._add_quest_dialog)
        lhdr_lay.addWidget(qlbl)
        lhdr_lay.addStretch()
        lhdr_lay.addWidget(new_q_btn)
        llay.addWidget(lhdr)

        # ── Search box ────────────────────────────────────────────────────
        search_frame = QFrame()
        search_frame.setObjectName("questSearchFrame")
        sf_lay = QHBoxLayout(search_frame)
        sf_lay.setContentsMargins(10, 6, 10, 6)
        sf_lay.setSpacing(0)
        self._quest_search_edit = QLineEdit()
        self._quest_search_edit.setObjectName("questSearch")
        self._quest_search_edit.setPlaceholderText("Search quests…")
        self._quest_search_edit.setClearButtonEnabled(True)
        self._quest_search_edit.textChanged.connect(self._on_quest_search_changed)
        sf_lay.addWidget(self._quest_search_edit)
        llay.addWidget(search_frame)

        # ── Stats label ───────────────────────────────────────────────────
        self._quest_stats_lbl = QLabel("")
        self._quest_stats_lbl.setObjectName("questStatsLbl")
        self._quest_stats_lbl.setContentsMargins(14, 4, 10, 4)
        llay.addWidget(self._quest_stats_lbl)

        # ── Status nav (vertical, sidebar style) ──────────────────────────
        status_nav = QFrame()
        status_nav.setObjectName("questStatusNav")
        sn_lay = QVBoxLayout(status_nav)
        sn_lay.setContentsMargins(8, 6, 8, 6)
        sn_lay.setSpacing(2)

        self._quest_filter_btns: dict[str, QPushButton] = {}
        _filters = [
            ("all",       "📋", "All Quests"),
            ("Active",    "🔵", "Active"),
            ("On Hold",   "⏸",  "On Hold"),
            ("Completed", "✅", "Completed"),
            ("Abandoned", "💀", "Abandoned"),
        ]
        for fid, ficon, flbl in _filters:
            fb = QPushButton(f"{ficon}  {flbl}")
            fb.setCheckable(True)
            fb.setObjectName("questNavBtn")
            fb.clicked.connect(lambda _, f=fid: self._set_quest_filter(f))
            self._quest_filter_btns[fid] = fb
            sn_lay.addWidget(fb)

        div = QFrame()
        div.setObjectName("questDivider")
        div.setFixedHeight(1)
        sn_lay.addSpacing(4)
        sn_lay.addWidget(div)
        llay.addWidget(status_nav)

        # ── Quest list ────────────────────────────────────────────────────
        self._quest_list = QListWidget()
        self._quest_list.setObjectName("questList")
        self._quest_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._quest_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._quest_list.itemClicked.connect(self._on_quest_list_click)
        self._quest_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._quest_list.customContextMenuRequested.connect(
            self._quest_list_context_menu
        )
        llay.addWidget(self._quest_list, 1)
        root.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────────
        self._quest_right_stack = QStackedWidget()

        # Index 0 — placeholder
        ph = QWidget()
        ph_lay = QVBoxLayout(ph)
        ph_lbl = QLabel("Select a quest or click  + New  to get started")
        ph_lbl.setObjectName("dimHint")
        ph_lbl.setAlignment(Qt.AlignCenter)
        ph_lay.addWidget(ph_lbl)
        self._quest_right_stack.addWidget(ph)

        # Index 1 — scrollable detail view
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setObjectName("questDetailScroll")
        detail_scroll.setFrameShape(QFrame.NoFrame)
        self._quest_detail_widget = QWidget()
        self._quest_detail_widget.setObjectName("questDetailWidget")
        self._quest_detail_layout = QVBoxLayout(self._quest_detail_widget)
        self._quest_detail_layout.setContentsMargins(28, 22, 28, 28)
        self._quest_detail_layout.setSpacing(0)
        detail_scroll.setWidget(self._quest_detail_widget)
        self._quest_right_stack.addWidget(detail_scroll)

        root.addWidget(self._quest_right_stack, 1)
        return w

    # ── 8 · Assets ────────────────────────────────────────────────────────────

    def _build_assets_page(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────
        top_bar = QFrame()
        top_bar.setObjectName("assetsTopBar")
        tb_lay = QHBoxLayout(top_bar)
        tb_lay.setContentsMargins(20, 12, 16, 12)
        tb_lay.setSpacing(10)
        hdr = QLabel("Assets")
        hdr.setObjectName("pageTitle")
        self._asset_search = QLineEdit()
        self._asset_search.setPlaceholderText("Search assets…")
        self._asset_search.setObjectName("assetSearch")
        self._asset_search.setFixedWidth(220)
        self._asset_search.textChanged.connect(self._filter_asset_cards)
        add_btn = QPushButton("+ Add Assets")
        add_btn.setObjectName("accentBtn")
        add_btn.clicked.connect(self._add_assets_dialog)
        tb_lay.addWidget(hdr)
        tb_lay.addStretch()
        tb_lay.addWidget(self._asset_search)
        tb_lay.addWidget(add_btn)
        root.addWidget(top_bar)

        # ── Body: category sidebar + card grid ────────────────────────────
        body = QSplitter(Qt.Horizontal)
        body.setObjectName("assetsSplitter")
        body.setHandleWidth(1)

        # Left: category list
        cat_panel = QFrame()
        cat_panel.setObjectName("assetCatPanel")
        cat_panel.setFixedWidth(160)
        cp_lay = QVBoxLayout(cat_panel)
        cp_lay.setContentsMargins(8, 12, 8, 12)
        cp_lay.setSpacing(4)
        cat_hdr = QLabel("CATEGORIES")
        cat_hdr.setObjectName("panelHeader")
        cp_lay.addWidget(cat_hdr)
        cp_lay.addSpacing(4)

        self._asset_cat_btns: dict[str, QPushButton] = {}
        for cat_id, label, icon, _ in _ASSET_CATS:
            btn = QPushButton(f"{icon}  {label}")
            btn.setObjectName("assetCatBtn")
            btn.setCheckable(True)
            btn.setProperty("cat_id", cat_id)
            btn.clicked.connect(lambda _, c=cat_id: self._select_asset_cat(c))
            self._asset_cat_btns[cat_id] = btn
            cp_lay.addWidget(btn)
        cp_lay.addStretch()
        body.addWidget(cat_panel)

        # Right: scrollable card area
        right = QWidget()
        right.setObjectName("assetRightPanel")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(16, 14, 16, 14)
        right_lay.setSpacing(12)

        self._asset_count_lbl = QLabel("")
        self._asset_count_lbl.setObjectName("subLabel")
        right_lay.addWidget(self._asset_count_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("assetScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        self._asset_grid_widget = QWidget()
        self._asset_grid_widget.setObjectName("assetGridWidget")
        self._asset_grid_layout = QGridLayout(self._asset_grid_widget)
        self._asset_grid_layout.setSpacing(12)
        self._asset_grid_layout.setContentsMargins(0, 0, 0, 0)
        self._asset_grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._asset_grid_widget)
        right_lay.addWidget(scroll, 1)
        body.addWidget(right)

        body.setSizes([160, 700])
        root.addWidget(body, 1)

        self._select_asset_cat("all")
        return w

    # ── 7 · Dice ──────────────────────────────────────────────────────────────

    def _build_dice_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        hdr = QLabel("Dice Roller")
        hdr.setObjectName("pageTitle")
        lay.addWidget(hdr)

        # ── Quick-roll dice buttons ────────────────────────────────────────
        dice_row = QHBoxLayout()
        dice_row.setSpacing(10)
        self._dice_btns: list[QPushButton] = []
        for die in ["d4", "d6", "d8", "d10", "d12", "d20", "d100"]:
            btn = QPushButton(die)
            btn.setObjectName("dieBtn")
            btn.setFixedSize(64, 64)
            btn.clicked.connect(lambda _, d=die: self._quick_roll(d))
            dice_row.addWidget(btn)
            self._dice_btns.append(btn)
        dice_row.addStretch()
        lay.addLayout(dice_row)

        # ── Expression input ───────────────────────────────────────────────
        expr_row = QHBoxLayout()
        expr_row.setSpacing(8)
        self._dice_expr = QLineEdit()
        self._dice_expr.setPlaceholderText("Expression: 2d6+3, 4d6kh3, d20+5…")
        self._dice_expr.setObjectName("diceExpr")
        self._dice_expr.returnPressed.connect(self._roll_expression)
        roll_btn = QPushButton("Roll")
        roll_btn.setObjectName("accentBtn")
        roll_btn.setFixedHeight(36)
        roll_btn.clicked.connect(self._roll_expression)
        save_btn = QPushButton("★  Save")
        save_btn.setObjectName("saveExprBtn")
        save_btn.setFixedHeight(36)
        save_btn.setToolTip("Save this expression as a named preset")
        save_btn.clicked.connect(self._save_expression_prompt)
        expr_row.addWidget(self._dice_expr, 1)
        expr_row.addWidget(roll_btn)
        expr_row.addWidget(save_btn)
        lay.addLayout(expr_row)

        # ── Result display ─────────────────────────────────────────────────
        self._dice_result = QLabel("—")
        self._dice_result.setObjectName("diceResult")
        self._dice_result.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._dice_result)

        self._dice_detail = QLabel()
        self._dice_detail.setObjectName("diceDetail")
        self._dice_detail.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._dice_detail)

        # ── Saved expressions ──────────────────────────────────────────────
        saved_hdr = QHBoxLayout()
        saved_lbl = QLabel("Saved Expressions")
        saved_lbl.setObjectName("sectionLabel")
        saved_hdr.addWidget(saved_lbl)
        saved_hdr.addStretch()
        lay.addLayout(saved_hdr)

        # Horizontal scroll area for chips
        self._saved_expr_scroll = QScrollArea()
        self._saved_expr_scroll.setObjectName("savedExprScroll")
        self._saved_expr_scroll.setWidgetResizable(True)
        self._saved_expr_scroll.setFixedHeight(52)
        self._saved_expr_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._saved_expr_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._saved_expr_container = QWidget()
        self._saved_expr_container.setObjectName("savedExprContainer")
        self._saved_expr_layout = QHBoxLayout(self._saved_expr_container)
        self._saved_expr_layout.setContentsMargins(4, 4, 4, 4)
        self._saved_expr_layout.setSpacing(8)
        self._saved_expr_layout.addStretch()
        self._saved_expr_scroll.setWidget(self._saved_expr_container)
        lay.addWidget(self._saved_expr_scroll)

        # ── Roll history ───────────────────────────────────────────────────
        hist_hdr = QHBoxLayout()
        hist_lbl = QLabel("Roll History")
        hist_lbl.setObjectName("sectionLabel")
        clear_btn = QPushButton("Clear Log")
        clear_btn.setObjectName("dimBtn")
        clear_btn.setFixedHeight(24)
        clear_btn.clicked.connect(self._clear_dice_log)
        hist_hdr.addWidget(hist_lbl)
        hist_hdr.addStretch()
        hist_hdr.addWidget(clear_btn)
        lay.addLayout(hist_hdr)

        self._dice_history = QListWidget()
        self._dice_history.setObjectName("diceHistory")
        lay.addWidget(self._dice_history, 1)

        return w

    # ══════════════════════════════════════════════════════════════════════════
    #  Navigation
    # ══════════════════════════════════════════════════════════════════════════

    def _go_section(self, sec: int):
        self._stack.setCurrentIndex(sec)
        for s, btn in self._nav_btns.items():
            btn.setChecked(s == sec)
        # Load section data
        loaders = {
            _SEC_OVERVIEW:    self._load_overview,
            _SEC_SESSIONS:    self._load_sessions,
            _SEC_CHARACTERS:  self._load_characters,
            _SEC_ENCOUNTERS:  self._load_encounters,
            _SEC_COMPENDIUM:  self._load_compendium,
            _SEC_GALLERY:     self._load_gallery,
            _SEC_DICE:        self._load_dice_page,
            _SEC_ASSETS:      self._load_assets,
            _SEC_QUESTS:      self._load_quests,
        }
        if sec in loaders:
            loaders[sec]()

    def _open_campaign(self, campaign_id: int):
        self._camp_id = campaign_id
        self._camp    = self._svc.get_campaign(campaign_id)
        if not self._camp:
            return
        sys_id = getattr(self._camp, "game_system", "custom") or "custom"
        self._sys_id  = sys_id if sys_id in SYSTEMS else "custom"

        # Update sidebar
        self._back_btn.setVisible(True)
        sys = SYSTEMS.get(self._sys_id)
        icon = sys.icon if sys else "🎲"
        self._camp_label.setText(f"{icon} {self._camp.name}")
        self._camp_label.setVisible(True)
        self._nav_frame.setVisible(True)

        self._go_section(_SEC_OVERVIEW)
        self._initiative_tracker.set_camp_id(campaign_id)

    def _close_campaign(self):
        self._camp_id = None
        self._camp    = None
        self._enc_id  = None
        self._initiative_tracker.set_camp_id(None)
        self._initiative_tracker.clear_combat()
        self._enc_obj = None
        self._back_btn.setVisible(False)
        self._camp_label.setVisible(False)
        self._nav_frame.setVisible(False)
        self._stack.setCurrentIndex(_SEC_CAMPAIGNS)
        self._load_campaigns()

    # ══════════════════════════════════════════════════════════════════════════
    #  Data loaders
    # ══════════════════════════════════════════════════════════════════════════

    def _load_campaigns(self, filter_text: str = ""):
        campaigns = self._svc.get_all_campaigns()
        if filter_text:
            q = filter_text.lower()
            campaigns = [c for c in campaigns if q in c.name.lower()]

        # Clear grid
        while self._camp_grid.count():
            item = self._camp_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not campaigns:
            self._camp_empty.setVisible(True)
            return

        self._camp_empty.setVisible(False)
        cols = 4
        for i, camp in enumerate(campaigns):
            try:
                stats = self._svc.get_campaign_stats(camp.id)
            except Exception:
                stats = {}
            card = _CampaignCard(camp, stats)
            card.clicked.connect(self._open_campaign)
            card.edit_requested.connect(self._on_edit_campaign_by_id)
            card.delete_requested.connect(self._on_delete_campaign_by_id)
            self._camp_grid.addWidget(card, i // cols, i % cols)

    def _load_overview(self):
        if not self._camp:
            return
        sys = SYSTEMS.get(self._sys_id)
        self._ov_title.setText(self._camp.name)
        system_name = sys.name if sys else (getattr(self._camp, "game_system", "") or "")
        icon = sys.icon if sys else "🎲"
        self._ov_system.setText(f"{icon}  {system_name}")
        self._ov_desc.setText(getattr(self._camp, "description", "") or "")

        try:
            stats = self._svc.get_campaign_stats(self._camp_id)
            for key, lbl in self._ov_stats.items():
                lbl.setText(str(stats.get(key, 0)))
        except Exception:
            pass

        # Recent sessions
        self._ov_recent.clear()
        try:
            sessions = self._svc.get_sessions(self._camp_id)
            for s in reversed(sessions[-5:]):
                num  = getattr(s, "session_number", 0) or 0
                sys_obj = SYSTEMS.get(self._sys_id)
                label = sys_obj.session_label if sys_obj else "Session"
                item = QListWidgetItem(f"{label} {num} — {s.title}")
                item.setData(Qt.UserRole, s.id)
                self._ov_recent.addItem(item)
        except Exception:
            pass

    def _load_sessions(self):
        self._ses_list.clear()
        if not self._camp_id:
            return
        sys_obj = SYSTEMS.get(self._sys_id)
        label = sys_obj.session_label if sys_obj else "Session"
        try:
            sessions = self._svc.get_sessions(self._camp_id)
            for s in sessions:
                num  = getattr(s, "session_number", 0) or 0
                item = QListWidgetItem(f"{label} {num}: {s.title}")
                item.setData(Qt.UserRole, s.id)
                self._ses_list.addItem(item)
        except Exception:
            pass
        self._ses_detail.clear()

    def _load_characters(self):
        self._char_list.clear()
        if not self._camp_id:
            return
        try:
            chars = self._svc.get_characters(self._camp_id)
            for c in chars:
                role = getattr(c, "character_role", "") or ""
                item = QListWidgetItem(f"{c.name}  [{role}]")
                item.setData(Qt.UserRole, c.id)
                self._char_list.addItem(item)
        except Exception:
            pass
        self._char_detail.clear()

    def _load_compendium(self):
        # Exit search mode on any reload
        self._comp_search_mode = False
        self._comp_search_results = []
        self._comp_cat_hdr.setText("Categories")
        self._comp_entry_hdr.setText("Entries")
        # Restore search bar without triggering another reload
        self._comp_search.blockSignals(True)
        self._comp_search.clear()
        self._comp_search.blockSignals(False)
        self._comp_search_clear.setVisible(False)

        self._comp_cats.clear()
        if not self._camp_id:
            return
        try:
            cats = self._svc.get_compendium_categories(self._camp_id)
        except Exception:
            cats = []
        # Show system categories first (even if empty), then any extra DB cats
        sys_obj = SYSTEMS.get(self._sys_id)
        sys_cats = sys_obj.compendium_cats if sys_obj else []
        all_cats = list(sys_cats)
        for c in cats:
            if c not in all_cats:
                all_cats.append(c)
        for cat in all_cats:
            self._comp_cats.addItem(cat)
        self._comp_entries.clear()
        self._comp_current_cat = ""
        self._comp_current_eid = None

    # ══════════════════════════════════════════════════════════════════════════
    #  Selection handlers
    # ══════════════════════════════════════════════════════════════════════════

    def _on_session_selected(self, row: int):
        item = self._ses_list.item(row)
        if not item:
            return
        sid = item.data(Qt.UserRole)
        session = self._svc.get_session(sid)
        self._ses_detail.load(session, self._sys_id)

    def _on_character_selected(self, row: int):
        item = self._char_list.item(row)
        if not item:
            return
        cid = item.data(Qt.UserRole)
        char = self._svc.get_character(cid)
        self._char_detail.load(char, self._sys_id)

    def _on_comp_category_selected(self, row: int):
        item = self._comp_cats.item(row)
        if not item:
            return
        cat = item.text()
        self._comp_current_cat = cat
        self._comp_entries.clear()
        self._comp_view_title.clear()
        self._comp_view_tags.clear()
        self._comp_view_body.clear()
        self._comp_edit_btn.setVisible(False)
        self._comp_del_btn.setVisible(False)
        self._comp_current_eid = None
        try:
            entries = self._svc.get_compendium(self._camp_id, cat)
            for e in entries:
                item2 = QListWidgetItem(e.title)
                item2.setData(Qt.UserRole, e.id)
                self._comp_entries.addItem(item2)
        except Exception:
            pass

    def _on_comp_entry_selected(self, row: int):
        item = self._comp_entries.item(row)
        if not item:
            return
        eid = item.data(Qt.UserRole)
        self._comp_current_eid = eid

        # In search mode, use cached results; also pick up the category
        if self._comp_search_mode:
            entry = next((e for e in self._comp_search_results if e.id == eid), None)
            if entry:
                self._comp_current_cat = getattr(entry, "category", "") or ""
        else:
            entry = None
            try:
                entries = self._svc.get_compendium(self._camp_id, self._comp_current_cat)
                entry   = next((e for e in entries if e.id == eid), None)
            except Exception:
                pass

        if entry:
            self._comp_view_title.setText(entry.title)
            tags = entry.tags or ""
            cat  = getattr(entry, "category", "") or ""
            # Show category breadcrumb in search mode
            if self._comp_search_mode and cat:
                tag_text = f"📂 {cat}" + (f"  ·  {tags}" if tags else "")
            else:
                tag_text = f"Tags: {tags}" if tags else ""
            self._comp_view_tags.setText(tag_text)
            self._comp_view_body.setPlainText(entry.content or "")
            self._comp_edit_btn.setVisible(True)
            self._comp_del_btn.setVisible(True)

    # ── Compendium search ─────────────────────────────────────────────────────

    def _on_comp_search(self, text: str):
        if not self._camp_id:
            return
        text = text.strip()
        self._comp_search_clear.setVisible(bool(text))

        if not text:
            # Exit search mode and restore normal view
            if self._comp_search_mode:
                self._comp_search_mode    = False
                self._comp_search_results = []
                self._comp_cat_hdr.setText("Categories")
                self._comp_entry_hdr.setText("Entries")
                # Reload category list (don't call _load_compendium — would
                # recurse into clearing the search bar again)
                try:
                    cats    = self._svc.get_compendium_categories(self._camp_id)
                    sys_obj = SYSTEMS.get(self._sys_id)
                    sys_cats = sys_obj.compendium_cats if sys_obj else []
                    all_cats = list(sys_cats)
                    for c in cats:
                        if c not in all_cats:
                            all_cats.append(c)
                    self._comp_cats.blockSignals(True)
                    self._comp_cats.clear()
                    for cat in all_cats:
                        self._comp_cats.addItem(cat)
                    self._comp_cats.blockSignals(False)
                except Exception:
                    pass
                self._comp_entries.clear()
                self._comp_view_title.clear()
                self._comp_view_tags.clear()
                self._comp_view_body.clear()
                self._comp_edit_btn.setVisible(False)
                self._comp_del_btn.setVisible(False)
                self._comp_current_cat = ""
                self._comp_current_eid = None
            return

        # Enter search mode
        self._comp_search_mode = True
        try:
            results = self._svc.search_compendium(self._camp_id, text)
        except Exception:
            results = []
        self._comp_search_results = results

        n = len(results)
        self._comp_cat_hdr.setText(f"🔍 Search")
        self._comp_entry_hdr.setText(
            f"{'No' if n == 0 else n} result{'s' if n != 1 else ''}")

        # Populate category panel with a single "search" indicator item
        self._comp_cats.blockSignals(True)
        self._comp_cats.clear()
        item = QListWidgetItem(f'"{text}"')
        item.setForeground(self._comp_cats.palette().highlight().color())
        self._comp_cats.addItem(item)
        self._comp_cats.setCurrentRow(0)
        self._comp_cats.blockSignals(False)

        # Populate entry panel with flat results
        self._comp_entries.blockSignals(True)
        self._comp_entries.clear()
        for e in results:
            cat   = getattr(e, "category", "") or ""
            label = f"[{cat}]  {e.title}" if cat else e.title
            row   = QListWidgetItem(label)
            row.setData(Qt.UserRole, e.id)
            self._comp_entries.addItem(row)
        self._comp_entries.blockSignals(False)

        # Clear detail panel
        self._comp_view_title.clear()
        self._comp_view_tags.clear()
        self._comp_view_body.clear()
        self._comp_edit_btn.setVisible(False)
        self._comp_del_btn.setVisible(False)
        self._comp_current_eid = None

    # ── Book manager ──────────────────────────────────────────────────────────

    def _on_manage_books(self):
        if not _GAME_DATA_AVAILABLE:
            return
        dlg = _BookManagerDialog(
            system_id=self._sys_id,
            disabled_books=self._disabled_books,
            parent=self,
        )
        dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() == QDialog.Accepted:
            self._disabled_books = dlg.get_disabled_books()
            count = len(self._disabled_books)
            if count:
                self._show_toast(f"{count} book{'s' if count != 1 else ''} hidden from game data.")
            else:
                self._show_toast("All books enabled.")

    # ══════════════════════════════════════════════════════════════════════════
    #  Context menus — list items
    # ══════════════════════════════════════════════════════════════════════════

    def _ses_list_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        item = self._ses_list.itemAt(pos)
        if not item:
            return
        sid = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("✏  Edit",   lambda: self._on_edit_session(sid))
        menu.addAction("🗑  Delete", lambda: self._on_delete_session(sid))
        menu.exec(self._ses_list.mapToGlobal(pos))

    def _char_list_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        item = self._char_list.itemAt(pos)
        if not item:
            return
        cid = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("✏  Edit",   lambda: self._on_edit_character(cid))
        menu.addAction("🗑  Delete", lambda: self._on_delete_character(cid))
        menu.exec(self._char_list.mapToGlobal(pos))

    def _comp_entry_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        item = self._comp_entries.itemAt(pos)
        if not item:
            return
        eid = item.data(Qt.UserRole)
        if not eid:
            return
        # select the item so edit/delete see the right entry
        self._comp_entries.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("✏  Edit",   self._on_edit_compendium_entry)
        menu.addAction("🗑  Delete", self._on_delete_compendium_entry)
        menu.exec(self._comp_entries.mapToGlobal(pos))

    # ══════════════════════════════════════════════════════════════════════════
    #  CRUD handlers — Campaigns
    # ══════════════════════════════════════════════════════════════════════════

    def _filter_campaigns(self, text: str):
        self._load_campaigns(text)

    # ── Dashboard event bus helper ─────────────────────────────────────────────

    def _fire(self, event: str, payload: dict | None = None):
        """Emit an event to the app event bus (silently ignores errors)."""
        try:
            self._ctx.event_bus.emit(event, payload or {})
        except Exception:
            pass

    # ── Campaign CRUD ─────────────────────────────────────────────────────────

    def _on_new_campaign(self):
        dlg = _NewCampaignDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.result_data()
        try:
            self._svc.create_campaign(**data)
            self._load_campaigns()
            self._show_toast("Campaign created.")
            self._fire("campaign_created", {"name": data.get("name", "")})
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_edit_campaign(self):
        """Edit the currently open campaign (called from overview page)."""
        if not self._camp:
            return
        dlg = _EditCampaignDialog(self._camp, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self._svc.update_campaign(self._camp_id, **dlg.result_data())
            self._camp = self._svc.get_campaign(self._camp_id)
            self._load_overview()
            self._show_toast("Campaign updated.")
            self._fire("campaign_updated", {"name": self._camp.name if self._camp else ""})
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_delete_campaign(self):
        """Delete the currently open campaign (called from overview page)."""
        if not self._camp:
            return
        name = self._camp.name
        reply = QMessageBox.question(
            self, "Delete Campaign",
            f"Permanently delete \"{name}\" and ALL its data?\n\n"
            "This includes all sessions, characters, encounters, compendium\n"
            "entries, journal entries, and gallery images.\n\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._svc.delete_campaign(self._camp_id)
            self._close_campaign()
            self._show_toast(f"Campaign \"{name}\" deleted.")
            self._fire("campaign_deleted", {"name": name})
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_edit_campaign_by_id(self, campaign_id: int):
        """Edit a campaign from the card grid (right-click → Edit)."""
        camp = self._svc.get_campaign(campaign_id)
        if not camp:
            return
        dlg = _EditCampaignDialog(camp, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self._svc.update_campaign(campaign_id, **dlg.result_data())
            self._load_campaigns()
            self._show_toast("Campaign updated.")
            self._fire("campaign_updated", {"name": camp.name})
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_delete_campaign_by_id(self, campaign_id: int):
        """Delete a campaign from the card grid (right-click → Delete)."""
        camp = self._svc.get_campaign(campaign_id)
        if not camp:
            return
        name = camp.name
        reply = QMessageBox.question(
            self, "Delete Campaign",
            f"Permanently delete \"{name}\" and ALL its data?\n\n"
            "This includes all sessions, characters, encounters, compendium\n"
            "entries, journal entries, and gallery images.\n\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._svc.delete_campaign(campaign_id)
            # If we just deleted the open campaign, close it first
            if campaign_id == self._camp_id:
                self._close_campaign()
            self._load_campaigns()
            self._show_toast(f"Campaign \"{name}\" deleted.")
            self._fire("campaign_deleted", {"name": name})
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Sessions ──────────────────────────────────────────────────────────────

    def _on_new_session(self):
        if not self._camp_id:
            return
        sys_obj = SYSTEMS.get(self._sys_id)
        label   = sys_obj.session_label if sys_obj else "Session"
        existing = self._svc.get_sessions(self._camp_id)
        next_num = len(existing) + 1
        dlg = _SessionDialog(label=label, session_number=next_num, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self._svc.create_session(self._camp_id, **dlg.result_data())
            self._load_sessions()
            self._show_toast(f"{label} logged.")
            title = dlg.result_data().get("title", "")
            self._fire("battle_logged", {
                "name": title,
                "campaign_name": self._camp.name if self._camp else "",
            })
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_edit_session(self, session_id: int):
        session = self._svc.get_session(session_id)
        if not session:
            return
        sys_obj = SYSTEMS.get(self._sys_id)
        label   = sys_obj.session_label if sys_obj else "Session"
        dlg = _SessionDialog(session=session, label=label, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self._svc.update_session(session_id, **dlg.result_data())
            self._load_sessions()
            self._show_toast(f"{label} updated.")
            self._fire("dashboard_provider_updated")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_delete_session(self, session_id: int):
        if not session_id:
            return
        if QMessageBox.question(self, "Delete", "Delete this session?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self._svc.delete_session(session_id)
            self._ses_detail.clear()
            self._load_sessions()
            self._show_toast("Session deleted.")
            self._fire("dashboard_provider_updated")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Characters ────────────────────────────────────────────────────────────

    def _on_new_character(self):
        if not self._camp_id:
            return
        sys_obj = SYSTEMS.get(self._sys_id)
        dlg = _CharacterDialog(system_id=self._sys_id, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            data = dlg.result_data()
            self._svc.create_character(self._camp_id, **data)
            self._load_characters()
            self._show_toast("Character added.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_edit_character(self, char_id: int):
        char = self._svc.get_character(char_id)
        if not char:
            return
        dlg = _CharacterDialog(system_id=self._sys_id, character=char, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            data = dlg.result_data()
            self._svc.update_character(char_id, **data)
            char = self._svc.get_character(char_id)
            self._char_detail.load(char, self._sys_id)
            self._load_characters()
            self._show_toast("Character updated.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_delete_character(self, char_id: int):
        if not char_id:
            return
        if QMessageBox.question(self, "Delete", "Delete this character?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self._svc.delete_character(char_id)
            self._char_detail.clear()
            self._load_characters()
            self._show_toast("Character deleted.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Encounters ────────────────────────────────────────────────────────────

    def _load_encounters(self):
        """Reload the encounter list from the service."""
        if not self._camp_id:
            return
        sys = SYSTEMS.get(self._sys_id, SYSTEMS["custom"])
        self._enc_enemy_section_lbl.setText(f"{sys.enemy_label}s")
        show_calc = sys.encounter_system in ("cr_xp", "xp_budget")
        self._enc_calc_frame.setVisible(show_calc)

        encounters = self._svc.get_encounters(self._camp_id)
        self._enc_list.blockSignals(True)
        self._enc_list.clear()
        for enc in encounters:
            diff = getattr(enc, "difficulty", "") or ""
            suffix = f"  [{diff}]" if diff else ""
            self._enc_list.addItem(f"{enc.name}{suffix}")
        self._enc_list.blockSignals(False)

        # Re-select the same encounter if still present
        if self._enc_id is not None:
            for i in range(self._enc_list.count()):
                item = self._enc_list.item(i)
                if item:
                    match = [e for e in encounters if e.id == self._enc_id]
                    if match and item.text().startswith(match[0].name):
                        self._enc_list.setCurrentRow(i)
                        return
        # No selection
        self._enc_id = None
        self._enc_obj = None
        self._enc_right.setCurrentIndex(0)
        self._enc_del_btn.setEnabled(False)

    def _on_enc_select(self, row: int):
        if not self._camp_id or row < 0:
            self._enc_id = None
            self._enc_obj = None
            self._enc_right.setCurrentIndex(0)
            self._enc_del_btn.setEnabled(False)
            return
        encounters = self._svc.get_encounters(self._camp_id)
        if row >= len(encounters):
            return
        enc = encounters[row]
        self._enc_id  = enc.id
        self._enc_obj = enc
        self._enc_right.setCurrentIndex(1)
        self._enc_del_btn.setEnabled(True)
        self._populate_enc_detail(enc)

    def _populate_enc_detail(self, enc):
        """Fill the detail panel from the encounter object."""
        self._enc_name_edit.blockSignals(True)
        self._enc_name_edit.setText(enc.name or "")
        self._enc_name_edit.blockSignals(False)
        self._enc_desc_edit.blockSignals(True)
        self._enc_desc_edit.setPlainText(enc.description or "")
        self._enc_desc_edit.blockSignals(False)
        self._refresh_enc_monsters()
        self._recalc_encounter()

    def _refresh_enc_monsters(self):
        """Reload the monster list widget for the current encounter."""
        if not self._enc_id:
            return
        monsters = self._svc.get_monsters(self._enc_id)
        self._enc_monster_list.clear()
        for m in monsters:
            cr    = m.cr or "—"
            cnt   = m.count or 1
            xp    = DND5E_CR_XP.get(cr, 0) * cnt if self._sys_id == "dnd5e" else 0
            xp_s  = f"  [{xp:,} xp]" if xp else ""
            hp_s  = f"  HP:{m.hp_override}" if m.hp_override else ""
            note_s = "  📝" if (m.notes and m.notes.strip()) else ""
            label = f"{m.monster_name}  ×{cnt}  CR {cr}{hp_s}{xp_s}{note_s}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, m.id)
            self._enc_monster_list.addItem(item)
        self._recalc_encounter()

    def _recalc_encounter(self):
        """Recalculate difficulty and update the badge + XP label."""
        if not self._enc_id:
            self._enc_diff_badge.setText("")
            return
        sys = SYSTEMS.get(self._sys_id, SYSTEMS["custom"])
        monsters = self._svc.get_monsters(self._enc_id)

        if sys.encounter_system == "cr_xp":
            self._recalc_dnd5e(monsters)
        elif sys.encounter_system == "xp_budget":
            self._recalc_pf2e(monsters)
        else:
            self._enc_xp_lbl.setText("")
            self._enc_result_lbl.setText("")
            self._enc_diff_badge.setText("")
            self._enc_thresh_lbl.setText("")

    def _recalc_dnd5e(self, monsters):
        """D&D 5e CR/XP difficulty calc."""
        n_chars = self._enc_party_size.value()
        level   = self._enc_party_level.value()
        thresh  = DND5E_XP_THRESHOLDS.get(level, (0, 0, 0, 0))
        labels  = ("Easy", "Medium", "Hard", "Deadly")
        self._enc_thresh_lbl.setText(
            "Thresholds:  "
            + "  ".join(f"{l}: {t:,}" for l, t in zip(labels, thresh))
        )

        raw_xp = 0
        m_count = 0
        for m in monsters:
            cr  = m.cr or "0"
            cnt = m.count or 1
            raw_xp  += DND5E_CR_XP.get(cr, 0) * cnt
            m_count += cnt

        # Multiplier
        mult = 1.0
        for threshold, factor in DND5E_MULT:
            if m_count >= threshold:
                mult = factor

        # Small/large party adjustment
        if n_chars < 3:
            mult = min(mult * 1.5, DND5E_MULT[-1][1])
        elif n_chars >= 6:
            mult = max(mult * 0.5, 1.0)

        adj_xp = int(raw_xp * mult)
        party_thresh = tuple(t * n_chars for t in thresh)

        if adj_xp == 0:
            diff, color = "—", _FG_DIM
        elif adj_xp < party_thresh[0]:
            diff, color = "Trivial", "#6ab04c"
        elif adj_xp < party_thresh[1]:
            diff, color = "Easy", _SUCCESS
        elif adj_xp < party_thresh[2]:
            diff, color = "Medium", "#f9ca24"
        elif adj_xp < party_thresh[3]:
            diff, color = "Hard", "#f0932b"
        else:
            diff, color = "Deadly", _DANGER

        self._enc_xp_lbl.setText(
            f"Raw: {raw_xp:,} xp  ×{mult:.1f} → {adj_xp:,} adj. xp")
        self._enc_result_lbl.setText(diff)
        self._enc_result_lbl.setStyleSheet(
            f"color: {color}; font-weight: 700; font-size: 13px;")
        self._enc_diff_badge.setText(diff)
        self._enc_diff_badge.setStyleSheet(
            f"color: {color}; font-weight: 700; background: transparent;")

    def _recalc_pf2e(self, monsters):
        """Pathfinder 2e XP-budget difficulty calc."""
        party_level = self._enc_party_level.value()
        n_chars     = self._enc_party_size.value()
        total_xp    = 0
        for m in monsters:
            try:
                creature_lvl = int(m.cr or str(party_level))
            except ValueError:
                creature_lvl = party_level
            delta = min(max(creature_lvl - party_level, -4), 4)
            total_xp += PF2E_CREATURE_XP.get(delta, 0) * (m.count or 1)

        # Scale for non-4-player parties
        budget_mod = (n_chars - 4) * 10

        budgets = PF2E_XP_BUDGET.copy()
        rated = "—"
        color = _FG_DIM
        for label, budget in sorted(budgets.items(), key=lambda x: x[1]):
            adjusted = budget + budget_mod
            if total_xp <= adjusted:
                rated = label
                color = {
                    "Trivial": "#6ab04c", "Low": _SUCCESS,
                    "Moderate": "#f9ca24", "Severe": "#f0932b",
                    "Extreme": _DANGER,
                }.get(label, _FG)
                break
        else:
            if total_xp > 0:
                rated, color = "Extreme", _DANGER

        self._enc_thresh_lbl.setText(
            "Budgets (4-player):  "
            + "  ".join(f"{l}: {b}" for l, b in PF2E_XP_BUDGET.items()))
        self._enc_xp_lbl.setText(f"Total XP: {total_xp}")
        self._enc_result_lbl.setText(rated)
        self._enc_result_lbl.setStyleSheet(
            f"color: {color}; font-weight: 700; font-size: 13px;")
        self._enc_diff_badge.setText(rated)
        self._enc_diff_badge.setStyleSheet(
            f"color: {color}; font-weight: 700; background: transparent;")

    def _enc_desc_focus_out(self, event):
        """Commit description on focus-out."""
        QTextEdit.focusOutEvent(self._enc_desc_edit, event)
        self._on_enc_desc_commit()

    def _on_enc_name_commit(self):
        if not self._enc_obj:
            return
        name = self._enc_name_edit.text().strip()
        if name and name != self._enc_obj.name:
            try:
                self._svc.update_encounter(self._enc_obj, name=name)
                self._load_encounters()
            except Exception as e:
                print(f"[ENCOUNTERS] name commit: {e}")

    def _on_enc_desc_commit(self):
        if not self._enc_obj:
            return
        desc = self._enc_desc_edit.toPlainText().strip()
        if desc != (self._enc_obj.description or ""):
            try:
                self._svc.update_encounter(self._enc_obj, description=desc)
            except Exception as e:
                print(f"[ENCOUNTERS] desc commit: {e}")

    def _on_new_encounter(self):
        if not self._camp_id:
            return
        dlg = _SimpleInputDialog("New Encounter", "Encounter name:", parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.value():
            return
        try:
            enc = self._svc.create_encounter(self._camp_id, name=dlg.value())
            self._load_encounters()
            # Select the new encounter
            if enc and getattr(enc, "id", None):
                encounters = self._svc.get_encounters(self._camp_id)
                for i, e in enumerate(encounters):
                    if e.id == enc.id:
                        self._enc_list.setCurrentRow(i)
                        break
            self._show_toast("Encounter created.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_delete_encounter(self):
        if not self._enc_obj:
            return
        name = self._enc_obj.name
        reply = QMessageBox.question(
            self, "Delete Encounter",
            f"Delete \"{name}\"? This will also remove all its enemies.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._svc.delete_encounter(self._enc_id)
            self._enc_id  = None
            self._enc_obj = None
            self._load_encounters()
            self._show_toast("Encounter deleted.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_run_initiative(self):
        """Switch to initiative tab and pre-load the current encounter's monsters."""
        if not self._enc_id:
            return
        self._enc_tab_widget.setCurrentIndex(1)
        self._initiative_tracker.load_from_encounter(self._enc_id)

    def _on_add_monster(self):
        if not self._enc_id:
            return
        name = self._enc_enemy_name.text().strip()
        if not name:
            return
        cr    = self._enc_enemy_cr.text().strip() or "0"
        count = self._enc_enemy_count.value()
        try:
            self._svc.add_monster(self._enc_id, name=name, count=count, cr=cr)
            self._enc_enemy_name.clear()
            self._enc_enemy_cr.clear()
            self._enc_enemy_count.setValue(1)
            self._refresh_enc_monsters()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_remove_monster(self):
        row = self._enc_monster_list.currentRow()
        if row < 0:
            return
        item = self._enc_monster_list.item(row)
        if not item:
            return
        monster_id = item.data(Qt.UserRole)
        if not monster_id:
            return
        try:
            self._svc.remove_monster(monster_id)
            self._refresh_enc_monsters()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_edit_monster_dblclick(self, item: QListWidgetItem):
        """Double-click a monster row to edit it."""
        self._edit_monster_by_id(item.data(Qt.UserRole))

    def _enc_monster_context_menu(self, pos):
        item = self._enc_monster_list.itemAt(pos)
        if not item:
            return
        monster_id = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(self.styleSheet())
        edit_act = menu.addAction("✏  Edit…")
        dup_act  = menu.addAction("⧉  Duplicate")
        menu.addSeparator()
        del_act  = menu.addAction("✕  Remove")
        act = menu.exec(self._enc_monster_list.mapToGlobal(pos))
        if act == edit_act:
            self._edit_monster_by_id(monster_id)
        elif act == dup_act:
            self._duplicate_monster(monster_id)
        elif act == del_act:
            try:
                self._svc.remove_monster(monster_id)
                self._refresh_enc_monsters()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _edit_monster_by_id(self, monster_id):
        if not monster_id or not self._enc_id:
            return
        # Fetch the monster from the list by scanning
        monsters = self._svc.get_monsters(self._enc_id)
        m = next((x for x in monsters if x.id == monster_id), None)
        if not m:
            return
        dlg = _MonsterEditDialog(m, parent=self)
        dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        self._svc.update_monster(
            monster_id,
            name=vals["name"],
            count=vals["count"],
            cr=vals["cr"],
            hp_override=vals["hp_override"],
            notes=vals["notes"],
        )
        self._refresh_enc_monsters()

    def _duplicate_monster(self, monster_id):
        if not self._enc_id:
            return
        monsters = self._svc.get_monsters(self._enc_id)
        m = next((x for x in monsters if x.id == monster_id), None)
        if not m:
            return
        try:
            self._svc.add_monster(
                self._enc_id,
                name=m.monster_name,
                count=m.count,
                cr=m.cr or "0",
                hp_override=m.hp_override or 0,
                notes=m.notes or "",
            )
            self._refresh_enc_monsters()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_browse_monsters_for_encounter(self):
        if not self._enc_id or not self._camp_id:
            return
        dlg = _MonsterFromBookDialog(
            service=self._svc,
            campaign_id=self._camp_id,
            encounter_id=self._enc_id,
            system_id=self._sys_id,
            disabled_books=self._disabled_books,
            parent=self,
        )
        dlg.setStyleSheet(self.styleSheet())
        dlg.exec()
        self._refresh_enc_monsters()

    def _on_open_custom_monsters(self):
        if not self._camp_id:
            return
        dlg = _CustomMonsterManagerDialog(
            service=self._svc,
            campaign_id=self._camp_id,
            encounter_id=self._enc_id,
            parent=self,
        )
        dlg.setStyleSheet(self.styleSheet())
        dlg.exec()
        if self._enc_id:
            self._refresh_enc_monsters()

    # ── Compendium ────────────────────────────────────────────────────────────

    def _on_browse_game_data(self):
        if not self._camp_id:
            return
        dlg = _GameDataBrowserDialog(
            self._svc, self._camp_id,
            system_id=self._sys_id,
            disabled_books=self._disabled_books,
            parent=self)
        dlg.exec()
        # Refresh compendium after potential imports
        self._load_compendium()
        # Re-select the current category if it's still there
        for i in range(self._comp_cats.count()):
            if self._comp_cats.item(i).text() == self._comp_current_cat:
                self._comp_cats.setCurrentRow(i)
                break

    def _on_new_compendium_entry(self):
        if not self._camp_id:
            return
        sys_obj = SYSTEMS.get(self._sys_id)
        cats = sys_obj.compendium_cats if sys_obj else []
        dlg = _CompendiumEntryDialog(categories=cats,
                                     default_cat=self._comp_current_cat,
                                     parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self._svc.add_compendium_entry(self._camp_id, **dlg.result_data())
            self._load_compendium()
            self._show_toast("Entry added.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_edit_compendium_entry(self):
        if not self._comp_current_eid or not self._camp_id:
            return
        entries = self._svc.get_compendium(self._camp_id, self._comp_current_cat)
        entry   = next((e for e in entries if e.id == self._comp_current_eid), None)
        if not entry:
            return
        sys_obj = SYSTEMS.get(self._sys_id)
        cats    = sys_obj.compendium_cats if sys_obj else []
        dlg = _CompendiumEntryDialog(categories=cats, entry=entry, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.result_data()
        try:
            self._svc.update_compendium_entry(
                self._comp_current_eid,
                category=data["category"], title=data["title"],
                content=data["content"], tags=data["tags"], source=data["source"],
            )
            self._on_comp_category_selected(
                self._comp_cats.currentRow())
            self._show_toast("Entry updated.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_delete_compendium_entry(self):
        if not self._comp_current_eid:
            return
        if QMessageBox.question(self, "Delete", "Delete this compendium entry?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self._svc.delete_compendium_entry(self._comp_current_eid)
            self._comp_current_eid = None
            self._comp_view_title.clear()
            self._comp_view_tags.clear()
            self._comp_view_body.clear()
            self._comp_edit_btn.setVisible(False)
            self._comp_del_btn.setVisible(False)
            # Refresh: in search mode re-run search, otherwise reload category
            if self._comp_search_mode:
                self._on_comp_search(self._comp_search.text())
            else:
                self._on_comp_category_selected(self._comp_cats.currentRow())
            self._show_toast("Entry deleted.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Gallery ───────────────────────────────────────────────────────────────

    def _load_gallery(self):
        if not self._camp_id:
            self._gallery_entries = []
            self._render_gallery()
            return
        try:
            self._gallery_entries = self._svc.get_gallery(self._camp_id)
        except Exception:
            self._gallery_entries = []
        n = len(self._gallery_entries)
        self._gallery_title_lbl.setText(
            f"Gallery — {self._camp.name}" if self._camp else "Gallery")
        self._gallery_count_lbl.setText(
            f"  {n} photo{'s' if n != 1 else ''}")
        self._render_gallery()

    def _gallery_cols(self) -> int:
        vp_w = self._gallery_scroll.viewport().width()
        if vp_w < _GC_W:
            vp_w = max(_GC_W, self.width() - 200)
        return max(1, (vp_w - _GC_GAP) // (_GC_W + _GC_GAP))

    def _render_gallery(self):
        entries = self._gallery_entries
        if self._gallery_stage_filter:
            entries = [e for e in entries
                       if (getattr(e, "stage", "") or "") == self._gallery_stage_filter]
        cols  = self._gallery_cols()
        inner = QWidget()
        grid  = QGridLayout(inner)
        grid.setContentsMargins(24, 14, 24, 24)
        grid.setSpacing(_GC_GAP)
        for c in range(cols):
            grid.setColumnStretch(c, 0)
        grid.setColumnStretch(cols, 1)

        if not self._camp_id:
            ph = QLabel("Open a campaign first.")
            ph.setAlignment(Qt.AlignCenter)
            ph.setStyleSheet("font-size:13px;color:rgba(255,255,255,0.28);padding:60px;")
            grid.addWidget(ph, 0, 0, 1, max(cols, 1))
        elif not entries:
            msg = ("No photos yet.\n\nClick  📸 Add Photo  to start your campaign gallery."
                   if not self._gallery_stage_filter else
                   "No photos tagged for this stage yet.")
            ph = QLabel(msg)
            ph.setAlignment(Qt.AlignCenter)
            ph.setWordWrap(True)
            ph.setStyleSheet("font-size:13px;color:rgba(255,255,255,0.28);padding:60px;")
            grid.addWidget(ph, 0, 0, 1, max(cols, 1))
        else:
            row = col = 0
            for idx, entry in enumerate(entries):
                card = _CampaignGalleryCard(entry, idx)
                card.open_requested.connect(self._on_view_photo)
                card.edit_requested.connect(self._on_edit_photo)
                card.delete_requested.connect(self._on_delete_photo)
                card.stage_change_requested.connect(self._on_stage_change)
                grid.addWidget(card, row, col, Qt.AlignTop)
                col += 1
                if col >= cols:
                    col = 0; row += 1
            if col != 0:
                row += 1
            grid.setRowStretch(row, 1)

        self._gallery_scroll.setWidget(inner)

    def _set_gallery_filter(self, stage: str):
        self._gallery_stage_filter = stage
        for val, btn in self._gallery_chips.items():
            btn.setObjectName("chipActive" if val == stage else "chip")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._render_gallery()

    def _on_add_photo(self):
        if not self._camp_id:
            return
        dlg = _CampaignAddPhotoDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        path = vals.get("image_path", "")
        if not path:
            return
        try:
            self._svc.add_gallery_image(
                self._camp_id, path,
                caption=vals.get("caption", ""),
                stage=vals.get("stage", ""),
            )
            self._load_gallery()
            self._show_toast("Photo added.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_view_photo(self, index: int):
        entries = self._gallery_entries
        if self._gallery_stage_filter:
            entries = [e for e in entries
                       if (getattr(e, "stage", "") or "") == self._gallery_stage_filter]
        if not entries:
            return
        dlg = _CampaignPhotoLightbox(entries, index, parent=self)
        dlg.edit_requested.connect(self._on_edit_photo)
        dlg.delete_requested.connect(self._on_delete_photo)
        dlg.exec()

    def _on_edit_photo(self, entry):
        dlg = _CampaignAddPhotoDialog(entry=entry, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        try:
            self._svc.update_gallery_entry(
                entry.id,
                caption=vals.get("caption", ""),
                stage=vals.get("stage", ""),
            )
            self._load_gallery()
            self._show_toast("Photo updated.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_delete_photo(self, entry):
        if QMessageBox.question(
            self, "Remove Photo",
            "Remove this photo from the gallery?\n(The file on disk won't be deleted.)",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        ) != QMessageBox.Yes:
            return
        try:
            self._svc.delete_gallery_image(entry.id)
            self._load_gallery()
            self._show_toast("Photo removed.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_stage_change(self, entry, new_stage: str):
        try:
            self._svc.update_gallery_stage(entry.id, new_stage)
            self._load_gallery()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ══════════════════════════════════════════════════════════════════════════
    #  Dice
    # ══════════════════════════════════════════════════════════════════════════

    def _quick_roll(self, die: str):
        sides = int(die[1:])
        result = random.randint(1, sides)
        self._dice_result.setText(str(result))
        self._dice_detail.setText(f"1{die}  →  [{result}]")
        self._dice_history.insertItem(0, f"1{die}  =  {result}")
        self._dice_expr.setText(f"1{die}")
        try:
            self._svc.log_roll(f"1{die}", result, f"[{result}]")
        except Exception:
            pass

    def _roll_expression(self):
        expr = self._dice_expr.text().strip()
        if not expr:
            return
        try:
            result, detail = _roll_dice(expr)
            self._dice_result.setText(str(result))
            self._dice_detail.setText(detail)
            self._dice_history.insertItem(0, f"{expr}  =  {result}  ({detail})")
            try:
                self._svc.log_roll(expr, result, detail)
            except Exception:
                pass
        except Exception as e:
            self._dice_result.setText("!")
            self._dice_detail.setText(str(e))

    # ── Dice page helpers ──────────────────────────────────────────────────────

    def _load_dice_page(self):
        """Reload history + saved expressions whenever the dice page is entered."""
        self._reload_dice_history()
        self._reload_saved_chips()

    def _reload_dice_history(self):
        """Populate the roll history list from the service."""
        self._dice_history.clear()
        try:
            for entry in self._svc.get_roll_history(limit=100):
                expr   = getattr(entry, "expression", "")
                result = getattr(entry, "result", "")
                detail = getattr(entry, "detail", "")
                text   = f"{expr}  =  {result}"
                if detail:
                    text += f"  ({detail})"
                self._dice_history.addItem(text)
        except Exception:
            pass

    def _clear_dice_log(self):
        """Clear the visible roll history (does not affect DB)."""
        self._dice_history.clear()
        self._dice_result.setText("—")
        self._dice_detail.setText("")

    def _save_expression_prompt(self):
        """Open a small dialog to name and save the current expression."""
        expr = self._dice_expr.text().strip()
        if not expr:
            self._show_toast("Type an expression first.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Save Expression")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel(f"Expression:  <b>{expr}</b>"))
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("e.g. Sneak Attack, Fireball, Ability Check…")
        name_edit.returnPressed.connect(dlg.accept)
        lay.addWidget(QLabel("Name:"))
        lay.addWidget(name_edit)

        btns = QHBoxLayout()
        ok_btn = QPushButton("Save")
        ok_btn.setObjectName("accentBtn")
        ok_btn.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dlg.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok_btn)
        lay.addLayout(btns)

        name_edit.setFocus()
        if dlg.exec() != QDialog.Accepted:
            return

        name = name_edit.text().strip() or expr
        try:
            self._svc.save_expression(name, expr)
            self._reload_saved_chips()
            self._show_toast(f"Saved “{name}”")
        except Exception as e:
            self._show_toast(f"Could not save: {e}")

    def _reload_saved_chips(self):
        """Rebuild the saved-expression chip strip."""
        # Remove all existing chips (everything except the trailing stretch)
        while self._saved_expr_layout.count() > 1:
            item = self._saved_expr_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            exprs = self._svc.get_saved_expressions()
        except Exception:
            exprs = []

        for entry in exprs:
            eid    = getattr(entry, "id", None)
            name   = getattr(entry, "name", "?")
            expr   = getattr(entry, "expression", "")
            label  = f"★  {name}" + (f"  ·  {expr}" if expr != name else "")

            chip = QFrame()
            chip.setObjectName("exprChip")
            chip_lay = QHBoxLayout(chip)
            chip_lay.setContentsMargins(0, 0, 0, 0)
            chip_lay.setSpacing(0)

            use_btn = QPushButton(label)
            use_btn.setObjectName("chipUseBtn")
            use_btn.setToolTip(f"Load and roll  {expr}")
            use_btn.clicked.connect(lambda _, e=expr: self._use_saved_expression(e))

            del_btn = QPushButton("×")
            del_btn.setObjectName("chipDelBtn")
            del_btn.setToolTip("Delete this saved expression")
            del_btn.setFixedWidth(22)
            if eid is not None:
                del_btn.clicked.connect(lambda _, i=eid: self._delete_saved_expression(i))

            chip_lay.addWidget(use_btn)
            chip_lay.addWidget(del_btn)

            # Insert before the trailing stretch
            self._saved_expr_layout.insertWidget(
                self._saved_expr_layout.count() - 1, chip
            )

        # Show a hint when empty
        if not exprs:
            hint = QLabel("No saved expressions yet — type one above and click ★ Save")
            hint.setObjectName("dimHint")
            self._saved_expr_layout.insertWidget(0, hint)

    def _use_saved_expression(self, expr: str):
        """Load expression into the input field and roll it immediately."""
        self._dice_expr.setText(expr)
        self._roll_expression()

    def _delete_saved_expression(self, expr_id: int):
        """Delete a saved expression and refresh chips."""
        try:
            self._svc.delete_saved_expression(expr_id)
            self._reload_saved_chips()
        except Exception as e:
            self._show_toast(f"Could not delete: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    #  Quests
    # ══════════════════════════════════════════════════════════════════════════

    def _load_quests(self):
        self._set_quest_filter(self._quest_status_filter)

    def _set_quest_filter(self, filter_id: str):
        self._quest_status_filter = filter_id
        for fid, btn in self._quest_filter_btns.items():
            btn.setChecked(fid == filter_id)
        if not self._camp_id:
            return

        # Search overrides status filter
        search_q = ""
        if hasattr(self, "_quest_search_edit"):
            search_q = self._quest_search_edit.text().strip()

        if search_q:
            quests = self._svc.search_quests(self._camp_id, search_q)
        else:
            status_param = None if filter_id == "all" else filter_id
            quests = self._svc.get_quests(self._camp_id, status_param)

        # Update nav button labels with live counts
        counts = self._svc.get_quest_status_counts(self._camp_id)
        total  = sum(counts.values())
        _filters = [
            ("all",       "📋", "All Quests",  total),
            ("Active",    "🔵", "Active",      counts.get("Active",    0)),
            ("On Hold",   "⏸",  "On Hold",     counts.get("On Hold",   0)),
            ("Completed", "✅", "Completed",   counts.get("Completed", 0)),
            ("Abandoned", "💀", "Abandoned",   counts.get("Abandoned", 0)),
        ]
        for fid, ficon, flbl, cnt in _filters:
            btn = self._quest_filter_btns.get(fid)
            if not btn:
                continue
            count_str = f"  {cnt}" if cnt else ""
            btn.setText(f"{ficon}  {flbl}{count_str}")

        # Stats summary line
        if hasattr(self, "_quest_stats_lbl"):
            parts = []
            if counts.get("Active"):    parts.append(f"{counts['Active']} Active")
            if counts.get("On Hold"):   parts.append(f"{counts['On Hold']} On Hold")
            if counts.get("Completed"): parts.append(f"{counts['Completed']} Done")
            self._quest_stats_lbl.setText(
                " · ".join(parts) if parts else ("No quests yet" if not total else "")
            )

        self._quest_list.clear()
        for quest in quests:
            objs = self._svc.get_objectives(quest.id)
            done = sum(1 for o in objs if o.completed)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, quest.id)
            widget = _QuestListItem(quest, len(objs), done)
            item.setSizeHint(widget.sizeHint())
            self._quest_list.addItem(item)
            self._quest_list.setItemWidget(item, widget)

        # Restore selection
        if self._quest_id:
            for i in range(self._quest_list.count()):
                it = self._quest_list.item(i)
                if it and it.data(Qt.UserRole) == self._quest_id:
                    self._quest_list.setCurrentItem(it)
                    break

    def _on_quest_search_changed(self, text: str):
        self._set_quest_filter(self._quest_status_filter)

    def _on_quest_list_click(self, item: QListWidgetItem):
        qid = item.data(Qt.UserRole)
        if qid:
            quest = self._svc.get_quest(qid)
            if quest:
                self._quest_id = qid
                self._show_quest_detail(quest)

    def _show_quest_detail(self, quest):
        """Rebuild the right-panel detail view for quest."""
        self._quest_right_stack.setCurrentIndex(1)

        # Clear previous content
        while self._quest_detail_layout.count():
            item = self._quest_detail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        status_icon, status_color = _QUEST_STATUS_META.get(
            quest.status, ("?", "#a0a0a0")
        )

        # ── Title row: pin + title + Edit / Delete ────────────────────────
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(8)
        hdr_row.setContentsMargins(0, 0, 0, 0)

        # Pin toggle button
        pin_btn = QPushButton("★" if quest.pinned else "☆")
        pin_btn.setObjectName("questPinBtn")
        pin_btn.setFixedSize(30, 30)
        pin_btn.setToolTip("Unpin quest" if quest.pinned else "Pin quest to top")
        pin_btn.clicked.connect(lambda: self._toggle_quest_pin(quest.id))
        if quest.pinned:
            pin_btn.setStyleSheet(
                f"QPushButton {{ color:#f0c040; background:rgba(240,192,64,0.12);"
                f"border:1px solid rgba(240,192,64,0.35); border-radius:6px;"
                f"font-size:16px; }}"
                f"QPushButton:hover {{ background:rgba(240,192,64,0.22); }}"
            )
        else:
            pin_btn.setStyleSheet(
                f"QPushButton {{ color:{_FG_DIM}; background:transparent;"
                f"border:1px solid {_BORDER}; border-radius:6px; font-size:16px; }}"
                f"QPushButton:hover {{ color:{_FG_MID}; background:{_BG3}; }}"
            )

        title_lbl = QLabel(quest.title)
        title_lbl.setObjectName("questDetailTitle")
        title_lbl.setWordWrap(True)

        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("ghostBtn")
        edit_btn.setFixedHeight(30)
        edit_btn.clicked.connect(lambda: self._edit_quest_dialog(quest))
        del_btn = QPushButton("Delete")
        del_btn.setObjectName("dangerBtn")
        del_btn.setFixedHeight(30)
        del_btn.clicked.connect(lambda: self._delete_quest(quest.id))

        hdr_row.addWidget(pin_btn)
        hdr_row.addWidget(title_lbl, 1)
        hdr_row.addWidget(edit_btn)
        hdr_row.addWidget(del_btn)
        hdr_w = QWidget()
        hdr_w.setLayout(hdr_row)
        self._quest_detail_layout.addWidget(hdr_w)
        self._quest_detail_layout.addSpacing(10)

        # ── Status / priority / category pills ───────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Status pill — click to change
        s_btn = QPushButton(f"{status_icon}  {quest.status}  ▾")
        s_btn.setFixedHeight(26)
        s_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        s_btn.setStyleSheet(
            f"QPushButton {{ background:{status_color}1a; color:{status_color};"
            f"border:1px solid {status_color}55; border-radius:13px;"
            f"padding:0 12px; font-size:12px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{status_color}30; }}"
            f"QPushButton:pressed {{ background:{status_color}40; }}"
        )
        def _open_status_menu(qid=quest.id, btn=s_btn):
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            menu.setStyleSheet(self.styleSheet())
            for s in _QUEST_STATUSES:
                ico, _ = _QUEST_STATUS_META.get(s, ("", ""))
                act = menu.addAction(f"{ico}  {s}" if ico else s)
                act.triggered.connect(
                    lambda _, st=s, qid=qid: self._quick_status_change(qid, st)
                )
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        s_btn.clicked.connect(_open_status_menu)

        # Priority pill
        pcolor = _QUEST_PRIORITY_COLORS.get(quest.priority, "#a0a0a0")
        p_btn = QPushButton(f"● {quest.priority}")
        p_btn.setFixedHeight(26)
        p_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        p_btn.setStyleSheet(
            f"QPushButton {{ background:{pcolor}15; color:{pcolor};"
            f"border:1px solid {pcolor}44; border-radius:13px;"
            f"padding:0 12px; font-size:12px; }}"
            f"QPushButton:hover {{ background:{pcolor}25; }}"
        )
        def _open_priority_menu(qid=quest.id, btn=p_btn):
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            menu.setStyleSheet(self.styleSheet())
            for pri in _QUEST_PRIORITIES:
                act = menu.addAction(f"● {pri}")
                act.triggered.connect(
                    lambda _, p=pri, qid=qid: self._quick_field_change(qid, priority=p)
                )
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        p_btn.clicked.connect(_open_priority_menu)

        # Category pill
        c_btn = QPushButton(quest.category)
        c_btn.setFixedHeight(26)
        c_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        c_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_FG_MID};"
            f"border:1px solid {_BORDER}; border-radius:13px;"
            f"padding:0 12px; font-size:12px; }}"
            f"QPushButton:hover {{ color:{_FG}; border-color:#444; }}"
        )
        def _open_category_menu(qid=quest.id, btn=c_btn):
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            menu.setStyleSheet(self.styleSheet())
            for cat in _QUEST_CATEGORIES:
                act = menu.addAction(cat)
                act.triggered.connect(
                    lambda _, c=cat, qid=qid: self._quick_field_change(qid, category=c)
                )
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        c_btn.clicked.connect(_open_category_menu)

        meta_row.addWidget(s_btn)
        meta_row.addWidget(p_btn)
        meta_row.addWidget(c_btn)
        meta_row.addStretch()
        meta_w = QWidget()
        meta_w.setFixedHeight(36)
        meta_w.setLayout(meta_row)
        self._quest_detail_layout.addWidget(meta_w)
        self._quest_detail_layout.addSpacing(14)

        # ── Info grid: giver / location / dates ───────────────────────────
        _info = [
            ("Quest Giver", quest.quest_giver, "Location", quest.location),
            ("Date Started", quest.date_started, "Completed", quest.date_completed),
        ]
        has_info = any(
            quest.quest_giver or quest.location or
            quest.date_started or quest.date_completed
        )
        if has_info:
            info_w = QWidget()
            info_g = QGridLayout(info_w)
            info_g.setContentsMargins(0, 0, 0, 0)
            info_g.setHorizontalSpacing(18)
            info_g.setVerticalSpacing(6)
            gr = 0
            for lbl1, val1, lbl2, val2 in _info:
                if not (val1 or val2):
                    continue
                if val1:
                    kl = QLabel(lbl1)
                    kl.setObjectName("questInfoKey")
                    vl = QLabel(val1)
                    vl.setObjectName("questInfoVal")
                    info_g.addWidget(kl, gr, 0)
                    info_g.addWidget(vl, gr, 1)
                if val2:
                    kl2 = QLabel(lbl2)
                    kl2.setObjectName("questInfoKey")
                    vl2 = QLabel(val2)
                    vl2.setObjectName("questInfoVal")
                    info_g.addWidget(kl2, gr, 2)
                    info_g.addWidget(vl2, gr, 3)
                gr += 1
            info_g.setColumnStretch(1, 1)
            info_g.setColumnStretch(3, 1)
            self._quest_detail_layout.addWidget(info_w)
            self._quest_detail_layout.addSpacing(10)

        # ── Tags ─────────────────────────────────────────────────────────
        if quest.tags:
            tags_w = QWidget()
            tags_lay = QHBoxLayout(tags_w)
            tags_lay.setContentsMargins(0, 0, 0, 0)
            tags_lay.setSpacing(6)
            for tag in quest.tags.split(","):
                tag = tag.strip()
                if not tag:
                    continue
                chip = QLabel(tag)
                chip.setObjectName("questTagChip")
                tags_lay.addWidget(chip)
            tags_lay.addStretch()
            self._quest_detail_layout.addWidget(tags_w)
            self._quest_detail_layout.addSpacing(10)

        # ── Linked session ────────────────────────────────────────────────
        if quest.linked_session_id:
            sess = self._svc.get_session(quest.linked_session_id)
            if sess:
                sess_row = QHBoxLayout()
                sess_row.setContentsMargins(0, 0, 0, 0)
                sess_row.setSpacing(8)
                sess_lbl_key = QLabel("Session")
                sess_lbl_key.setObjectName("questInfoKey")
                sess_title = getattr(sess, "title", "") or f"Session {quest.linked_session_id}"
                sess_lbl_val = QLabel(sess_title)
                sess_lbl_val.setObjectName("questInfoVal")
                sess_row.addWidget(sess_lbl_key)
                sess_row.addWidget(sess_lbl_val)
                sess_row.addStretch()
                sess_w = QWidget()
                sess_w.setLayout(sess_row)
                self._quest_detail_layout.addWidget(sess_w)
                self._quest_detail_layout.addSpacing(10)

        # Spacer before sections
        if has_info or quest.tags or quest.linked_session_id:
            sep = QFrame()
            sep.setObjectName("questDivider")
            sep.setFixedHeight(1)
            self._quest_detail_layout.addWidget(sep)
            self._quest_detail_layout.addSpacing(16)

        # ── Description ───────────────────────────────────────────────────
        self._add_quest_section(
            "Description",
            quest.description or "No description yet.",
            dim=(not quest.description),
        )
        self._quest_detail_layout.addSpacing(20)

        # ── Objectives ────────────────────────────────────────────────────
        self._quest_obj_section = self._build_objectives_section(quest)
        self._quest_detail_layout.addWidget(self._quest_obj_section)
        self._quest_detail_layout.addSpacing(20)

        # ── Reward ────────────────────────────────────────────────────────
        if quest.reward:
            self._add_quest_section("Reward", quest.reward)
            self._quest_detail_layout.addSpacing(20)

        # ── DM Notes ──────────────────────────────────────────────────────
        if quest.notes:
            self._add_quest_section("DM Notes", quest.notes)
            self._quest_detail_layout.addSpacing(20)

        self._quest_detail_layout.addStretch()

    def _add_quest_section(self, label: str, body: str, dim: bool = False):
        """Append a read-only labelled section to the detail layout."""
        sec = QWidget()
        sl = QVBoxLayout(sec)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        lbl = QLabel(label)
        lbl.setObjectName("questSectionLabel")
        div = QFrame()
        div.setObjectName("questDivider")
        div.setFixedHeight(1)
        body_lbl = QLabel(body)
        body_lbl.setObjectName("questBodyDim" if dim else "questBodyText")
        body_lbl.setWordWrap(True)
        sl.addWidget(lbl)
        sl.addWidget(div)
        sl.addWidget(body_lbl)
        self._quest_detail_layout.addWidget(sec)

    def _build_objectives_section(self, quest) -> QWidget:
        """Build the interactive objectives checklist widget."""
        objs = self._svc.get_objectives(quest.id)
        done = sum(1 for o in objs if o.completed)
        total = len(objs)

        sec = QWidget()
        sl = QVBoxLayout(sec)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)

        # Header row: label + progress fraction + add button
        hrow = QHBoxLayout()
        hrow.setSpacing(8)
        prog = f"  ({done}/{total})" if total else ""
        hdr_lbl = QLabel(f"Objectives{prog}")
        hdr_lbl.setObjectName("questSectionLabel")
        add_obj_btn = QPushButton("+ Add")
        add_obj_btn.setObjectName("dimBtn")
        add_obj_btn.setFixedHeight(22)
        add_obj_btn.clicked.connect(lambda: self._add_objective_prompt(quest.id))
        hrow.addWidget(hdr_lbl)
        hrow.addStretch()
        hrow.addWidget(add_obj_btn)
        sl.addLayout(hrow)

        div = QFrame()
        div.setObjectName("questDivider")
        div.setFixedHeight(1)
        sl.addWidget(div)

        # Progress bar (only shown when objectives exist)
        if total > 0:
            bar = _TinyProgressBar(done, total)
            sl.addWidget(bar)
            sl.addSpacing(4)

        if not objs:
            hint = QLabel("No objectives yet — click  + Add  to track your steps.")
            hint.setObjectName("dimHint")
            hint.setWordWrap(True)
            sl.addWidget(hint)
        else:
            for obj in objs:
                row_w = QWidget()
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(0, 2, 0, 2)
                row_l.setSpacing(8)

                cb = QCheckBox(obj.text)
                cb.setObjectName("questObjCheck")
                cb.setChecked(obj.completed)
                self._apply_obj_style(cb, obj.completed)

                # Live style + DB save on toggle
                def _make_toggle(checkbox, obj_id, qid):
                    def handler(checked):
                        self._apply_obj_style(checkbox, checked)
                        self._svc.set_objective_completed(obj_id, checked)
                        self._update_quest_list_progress(qid)
                        self._refresh_obj_header(sec, qid)
                    return handler

                cb.toggled.connect(_make_toggle(cb, obj.id, quest.id))

                del_obj = QPushButton("×")
                del_obj.setObjectName("chipDelBtn")
                del_obj.setFixedSize(20, 20)
                del_obj.clicked.connect(
                    lambda _, oid=obj.id, qid=quest.id:
                    self._delete_objective_item(oid, qid)
                )
                row_l.addWidget(cb, 1)
                row_l.addWidget(del_obj)
                sl.addWidget(row_w)

        return sec

    @staticmethod
    def _apply_obj_style(cb: "QCheckBox", completed: bool):
        if completed:
            cb.setStyleSheet(f"color:{_FG_DIM};text-decoration:line-through;")
        else:
            cb.setStyleSheet("")

    def _refresh_obj_header(self, sec_widget: QWidget, quest_id: int):
        """Update the 'Objectives (X/Y)' label after a toggle."""
        objs = self._svc.get_objectives(quest_id)
        done = sum(1 for o in objs if o.completed)
        prog = f"  ({done}/{len(objs)})" if objs else ""
        # Walk the sec_widget layout looking for the header QLabel
        lay = sec_widget.layout()
        if not lay:
            return
        for i in range(lay.count()):
            item = lay.itemAt(i)
            hrow = item.layout() if item else None
            if not isinstance(hrow, QHBoxLayout):
                continue
            for j in range(hrow.count()):
                child = hrow.itemAt(j)
                w = child.widget() if child else None
                if isinstance(w, QLabel) and w.objectName() == "questSectionLabel":
                    w.setText(f"Objectives{prog}")
                    return

    def _update_quest_list_progress(self, quest_id: int):
        """Refresh only the progress counter on the list item."""
        objs = self._svc.get_objectives(quest_id)
        done = sum(1 for o in objs if o.completed)
        for i in range(self._quest_list.count()):
            it = self._quest_list.item(i)
            if it and it.data(Qt.UserRole) == quest_id:
                widget = self._quest_list.itemWidget(it)
                if isinstance(widget, _QuestListItem):
                    widget.update_progress(len(objs), done)
                break

    def _add_objective_prompt(self, quest_id: int):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Objective")
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Objective text:"))
        edit = QLineEdit()
        edit.setPlaceholderText("e.g. Speak with the Oracle")
        edit.returnPressed.connect(dlg.accept)
        lay.addWidget(edit)
        btns = QHBoxLayout()
        ok = QPushButton("Add")
        ok.setObjectName("accentBtn")
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dlg.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        edit.setFocus()
        if dlg.exec() != QDialog.Accepted or not edit.text().strip():
            return
        self._svc.add_objective(quest_id, edit.text().strip())
        # Rebuild objectives section in-place
        quest = self._svc.get_quest(quest_id)
        if quest:
            self._refresh_objectives_widget(quest)
            self._update_quest_list_progress(quest_id)

    def _delete_objective_item(self, obj_id: int, quest_id: int):
        self._svc.delete_objective(obj_id)
        quest = self._svc.get_quest(quest_id)
        if quest:
            self._refresh_objectives_widget(quest)
            self._update_quest_list_progress(quest_id)

    def _refresh_objectives_widget(self, quest):
        """Replace only the objectives section widget without rebuilding all of detail."""
        new_sec = self._build_objectives_section(quest)
        # Swap out the old section widget
        old = self._quest_obj_section
        idx = self._quest_detail_layout.indexOf(old)
        if idx >= 0:
            self._quest_detail_layout.takeAt(idx)
            old.deleteLater()
            self._quest_detail_layout.insertWidget(idx, new_sec)
            self._quest_obj_section = new_sec

    def _quick_status_change(self, quest_id: int, status: str):
        self._svc.update_quest_status(quest_id, status)
        self._refresh_quest_after_change(quest_id)

    def _quick_field_change(self, quest_id: int, **fields):
        """Update arbitrary quest fields and refresh the view."""
        quest = self._svc.get_quest(quest_id)
        if not quest:
            return
        self._svc.update_quest(
            quest_id,
            title=quest.title,
            status=fields.get("status", quest.status),
            priority=fields.get("priority", quest.priority),
            category=fields.get("category", quest.category),
            description=quest.description,
            notes=quest.notes,
            reward=quest.reward,
            quest_giver=quest.quest_giver,
            location=quest.location,
            date_started=quest.date_started,
            date_completed=quest.date_completed,
            linked_session_id=quest.linked_session_id,
            tags=quest.tags,
        )
        self._refresh_quest_after_change(quest_id)

    def _refresh_quest_after_change(self, quest_id: int):
        """Reload list counts and rebuild the detail panel for quest_id."""
        # Refresh sidebar counts
        self._set_quest_filter(self._quest_status_filter)
        # Rebuild detail
        updated = self._svc.get_quest(quest_id)
        if updated:
            self._show_quest_detail(updated)

    def _add_quest_dialog(self):
        if not self._camp_id:
            return
        sessions = self._svc.get_sessions(self._camp_id)
        dlg = _QuestEditDialog(sessions=sessions, parent=self)
        dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.result_data()
        new_id = self._svc.add_quest(
            self._camp_id, d["title"],
            status=d["status"], priority=d["priority"],
            category=d["category"], description=d["description"],
            notes=d["notes"], reward=d["reward"],
            quest_giver=d.get("quest_giver", ""),
            location=d.get("location", ""),
            date_started=d.get("date_started", ""),
            date_completed=d.get("date_completed", ""),
            linked_session_id=d.get("linked_session_id"),
            tags=d.get("tags", ""),
        )
        self._set_quest_filter(self._quest_status_filter)
        if new_id and new_id > 0:
            self._quest_id = new_id
            quest = self._svc.get_quest(new_id)
            if quest:
                self._show_quest_detail(quest)
        self._show_toast(f"Quest created: {d['title']}")

    def _edit_quest_dialog(self, quest):
        sessions = self._svc.get_sessions(self._camp_id) if self._camp_id else []
        dlg = _QuestEditDialog(quest=quest, sessions=sessions, parent=self)
        dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.result_data()
        self._svc.update_quest(
            quest.id, d["title"], d["status"], d["priority"],
            d["category"], d["description"], d["notes"], d["reward"],
            quest_giver=d.get("quest_giver", ""),
            location=d.get("location", ""),
            date_started=d.get("date_started", ""),
            date_completed=d.get("date_completed", ""),
            linked_session_id=d.get("linked_session_id"),
            tags=d.get("tags", ""),
        )
        self._set_quest_filter(self._quest_status_filter)
        updated = self._svc.get_quest(quest.id)
        if updated:
            self._show_quest_detail(updated)
        self._show_toast("Quest updated.")

    def _delete_quest(self, quest_id: int):
        resp = QMessageBox.question(
            self, "Delete Quest",
            "Delete this quest and all its objectives?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if resp != QMessageBox.Yes:
            return
        self._svc.delete_quest(quest_id)
        self._quest_id = None
        self._quest_right_stack.setCurrentIndex(0)
        self._set_quest_filter(self._quest_status_filter)
        self._show_toast("Quest deleted.")

    def _toggle_quest_pin(self, quest_id: int):
        """Pin or unpin a quest and refresh the view."""
        is_pinned = self._svc.toggle_quest_pin(quest_id)
        self._refresh_quest_after_change(quest_id)
        self._show_toast("Quest pinned." if is_pinned else "Quest unpinned.")

    def _quest_list_context_menu(self, pos):
        """Right-click context menu on quest list items."""
        item = self._quest_list.itemAt(pos)
        if not item:
            return
        qid = item.data(Qt.UserRole)
        quest = self._svc.get_quest(qid)
        if not quest:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(self.styleSheet())

        pin_lbl = "Unpin Quest" if quest.pinned else "Pin Quest"
        pin_act = menu.addAction(pin_lbl)
        pin_act.triggered.connect(lambda: self._toggle_quest_pin(qid))

        menu.addSeparator()

        status_menu = menu.addMenu("Change Status")
        status_menu.setStyleSheet(self.styleSheet())
        for s in _QUEST_STATUSES:
            ico, _ = _QUEST_STATUS_META.get(s, ("", ""))
            act = status_menu.addAction(f"{ico}  {s}" if ico else s)
            act.triggered.connect(
                lambda _, st=s, q=qid: self._quick_status_change(q, st)
            )

        menu.addSeparator()

        edit_act = menu.addAction("Edit Quest…")
        edit_act.triggered.connect(lambda: self._edit_quest_dialog(quest))

        del_act = menu.addAction("Delete Quest")
        del_act.triggered.connect(lambda: self._delete_quest(qid))

        menu.exec(self._quest_list.mapToGlobal(pos))

    # ══════════════════════════════════════════════════════════════════════════
    #  Assets
    # ══════════════════════════════════════════════════════════════════════════

    def _load_assets(self):
        self._select_asset_cat(self._asset_cat_filter)

    def _select_asset_cat(self, cat_id: str):
        self._asset_cat_filter = cat_id
        for cid, btn in self._asset_cat_btns.items():
            btn.setChecked(cid == cat_id)
        self._rebuild_asset_grid()

    def _rebuild_asset_grid(self, search: str = ""):
        """Clear and repopulate the asset card grid."""
        if not self._camp_id:
            return

        # Clear grid
        while self._asset_grid_layout.count():
            item = self._asset_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        assets = self._svc.get_assets(
            self._camp_id,
            None if self._asset_cat_filter == "all" else self._asset_cat_filter,
        )

        # Apply search filter
        q = (search or self._asset_search.text()).strip().lower()
        if q:
            assets = [a for a in assets
                      if q in a.name.lower() or q in a.tags.lower()
                      or q in a.category.lower()]

        # Update category sidebar with live counts
        counts = self._svc.get_asset_category_counts(self._camp_id)
        total  = sum(counts.values())
        for cat_id, label, icon, _ in _ASSET_CATS:
            btn = self._asset_cat_btns.get(cat_id)
            if not btn:
                continue
            if cat_id == "all":
                cnt = total
            else:
                cnt = counts.get(cat_id, 0)
            btn.setText(f"{icon}  {label}" + (f"  ({cnt})" if cnt else ""))

        self._asset_count_lbl.setText(
            f"{len(assets)} asset{'s' if len(assets) != 1 else ''}"
        )

        if not assets:
            placeholder = QLabel("No assets yet — click  + Add Assets  to get started")
            placeholder.setObjectName("dimHint")
            placeholder.setAlignment(Qt.AlignCenter)
            self._asset_grid_layout.addWidget(placeholder, 0, 0)
            return

        cols = 5
        for i, asset in enumerate(assets):
            card = self._make_asset_card(asset)
            self._asset_grid_layout.addWidget(card, i // cols, i % cols)

    def _make_asset_card(self, asset) -> QFrame:
        """Build a single asset card widget."""
        card = QFrame()
        card.setObjectName("assetCard")
        card.setFixedSize(140, 158)
        card.setCursor(Qt.PointingHandCursor)
        card.setToolTip(
            f"{asset.file_path}\n" + (f"Tags: {asset.tags}" if asset.tags else "")
        )

        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # Thumbnail / icon area
        thumb = QLabel()
        thumb.setObjectName("assetThumb")
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setFixedHeight(88)

        ext = os.path.splitext(asset.file_path)[1].lower()
        loaded_thumb = False
        if ext in _IMAGE_EXTS and os.path.exists(asset.file_path):
            pix = QPixmap(asset.file_path)
            if not pix.isNull():
                thumb.setPixmap(pix.scaled(120, 88, Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation))
                loaded_thumb = True

        if not loaded_thumb:
            _, icon, col = _asset_cat_info(asset.category)
            thumb.setText(icon)
            thumb.setStyleSheet(
                f"font-size: 36px; background: {col}22; "
                f"border-radius: 6px; color: {col};"
            )

        lay.addWidget(thumb)

        # Name
        name_lbl = QLabel(asset.name)
        name_lbl.setObjectName("assetName")
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(False)
        name_lbl.setMaximumWidth(124)
        # Truncate with elide via fixed-width label
        fm = name_lbl.fontMetrics()
        elided = fm.elidedText(asset.name, Qt.ElideRight, 124)
        name_lbl.setText(elided)
        lay.addWidget(name_lbl)

        # Category badge
        _, cat_icon, cat_col = _asset_cat_info(asset.category)
        badge = QLabel(f"{cat_icon} {asset.category.capitalize()}")
        badge.setObjectName("assetBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background: {cat_col}33; color: {cat_col}; "
            f"border-radius: 8px; padding: 2px 6px; font-size: 10px;"
        )
        lay.addWidget(badge)

        # Click to open
        card.mousePressEvent = lambda ev, p=asset.file_path: self._open_asset_file(p)

        # Right-click context menu
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, a=asset: self._asset_card_context_menu(pos, a, card)
        )

        return card

    def _open_asset_file(self, file_path: str):
        if not os.path.exists(file_path):
            self._show_toast("File not found — it may have been moved or deleted.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    def _asset_card_context_menu(self, pos, asset, card: QFrame):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(card)
        menu.addAction("📂  Open File",
                       lambda: self._open_asset_file(asset.file_path))
        menu.addAction("📋  Copy Path",
                       lambda: QApplication.clipboard().setText(asset.file_path))
        menu.addSeparator()
        menu.addAction("✏  Edit",
                       lambda: self._edit_asset_dialog(asset))
        menu.addSeparator()
        act_del = menu.addAction("🗑  Remove")
        act_del.triggered.connect(lambda: self._delete_asset(asset.id))
        menu.exec(card.mapToGlobal(pos))

    def _filter_asset_cards(self, text: str):
        self._rebuild_asset_grid(text)

    def _add_assets_dialog(self):
        if not self._camp_id:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Asset Files", "",
            "All Files (*);;"
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.svg);;"
            "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus);;"
            "Documents (*.pdf *.txt *.md *.docx *.rtf);;"
            "Maps (*.png *.jpg *.pdf *.svg)",
        )
        if not paths:
            return

        # For a single file: show full detail dialog
        # For multiple: auto-import with defaults, then refresh
        if len(paths) == 1:
            self._add_single_asset_dialog(paths[0])
        else:
            added = 0
            for p in paths:
                name = os.path.splitext(os.path.basename(p))[0]
                cat  = _guess_asset_category(p)
                self._svc.add_asset(self._camp_id, name, p, cat)
                added += 1
            self._rebuild_asset_grid()
            self._show_toast(f"Added {added} assets.")

    def _add_single_asset_dialog(self, file_path: str = ""):
        dlg = _AssetEditDialog(file_path=file_path, parent=self)
        dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.result_data()
        self._svc.add_asset(
            self._camp_id, d["name"], d["file_path"],
            d["category"], d["tags"], d["notes"],
        )
        self._rebuild_asset_grid()
        self._show_toast("Added  “" + d['name'] + "”")

    def _edit_asset_dialog(self, asset):
        dlg = _AssetEditDialog(asset=asset, parent=self)
        dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.result_data()
        self._svc.update_asset(
            asset.id, d["name"], d["category"], d["tags"], d["notes"]
        )
        self._rebuild_asset_grid()
        self._show_toast("Asset updated.")

    def _delete_asset(self, asset_id: int):
        resp = QMessageBox.question(
            self, "Remove Asset",
            "Remove this asset from the campaign?\n(The file itself will not be deleted.)",
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if resp != QMessageBox.Yes:
            return
        try:
            self._svc.delete_asset(asset_id)
            self._rebuild_asset_grid()
            self._show_toast("Asset removed.")
        except Exception as e:
            self._show_toast(f"Error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    #  Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def refresh(self):
        if self._camp_id:
            sec = self._stack.currentIndex()
            loaders = {
                _SEC_OVERVIEW:   self._load_overview,
                _SEC_SESSIONS:   self._load_sessions,
                _SEC_CHARACTERS: self._load_characters,
                _SEC_COMPENDIUM: self._load_compendium,
            }
            if sec in loaders:
                loaders[sec]()
        else:
            self._load_campaigns()

    def _show_toast(self, msg: str):
        t = _Toast(msg, self)
        t.adjustSize()
        x = (self.width()  - t.width())  // 2
        y =  self.height() - t.height() - 24
        t.move(x, y)
        t.show()

    # ══════════════════════════════════════════════════════════════════════════
    #  Theme
    # ══════════════════════════════════════════════════════════════════════════

    def _apply_theme(self):
        self.setStyleSheet(f"""
/* ── Base ──────────────────────────────────────────────────────────── */
* {{ font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px;
     color: {_FG}; }}
QWidget  {{ background: {_BG}; }}

/* Labels and non-container widgets must be transparent so they inherit
   the background of whatever frame they sit inside. */
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QScrollBar:vertical {{ background: {_BG}; width: 6px; border: none; }}
QScrollBar::handle:vertical {{ background: {_BORDER}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {_BG}; height: 6px; border: none; }}
QScrollBar::handle:horizontal {{ background: {_BORDER}; border-radius: 3px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Sidebar ────────────────────────────────────────────────────────── */
QFrame#sidebar {{ background: {_SIDEBAR}; border-right: 1px solid {_BORDER}; }}
QFrame#sidebarHeader {{ background: transparent; border-bottom: 1px solid {_BORDER}; }}
QLabel#appTitle {{ font-size: 15px; font-weight: 700; color: {_FG}; line-height: 1.3; }}
QLabel#appVer   {{ font-size: 11px; color: {_FG_DIM}; }}

QPushButton#navBtn {{
    background: transparent;
    border: none; border-radius: 6px;
    padding: 8px 10px;
    text-align: left; font-size: 13px; color: {_FG_MID};
}}
QPushButton#navBtn:hover   {{ background: rgba(255,255,255,0.05); color: {_FG}; }}
QPushButton#navBtn:checked {{ background: rgba(79,158,255,0.15); color: {_ACCENT}; font-weight: 600; }}

QPushButton#backBtn {{
    background: transparent; border: none;
    padding: 8px 14px; text-align: left;
    font-size: 12px; color: {_FG_DIM};
}}
QPushButton#backBtn:hover {{ color: {_FG}; }}
QLabel#campLabel {{ font-size: 12px; font-weight: 600; color: {_FG}; }}

/* ── Content ────────────────────────────────────────────────────────── */
QFrame#contentArea {{ background: {_BG}; }}
QLabel#pageTitle   {{ font-size: 22px; font-weight: 700; color: {_FG}; }}
QLabel#sectionLabel {{ font-size: 13px; font-weight: 600; color: {_FG_MID}; text-transform: uppercase; letter-spacing: 1px; }}
QLabel#subLabel    {{ font-size: 12px; color: {_FG_MID}; }}
QLabel#dimLabel    {{ font-size: 12px; color: {_FG_DIM}; }}
QLabel#dialogTitle {{ font-size: 16px; font-weight: 700; }}
QLabel#emptyState  {{ font-size: 14px; color: {_FG_DIM}; }}

/* ── Campaign cards ─────────────────────────────────────────────────── */
QFrame#campaignCard {{
    background: {_BG2};
    border: 1px solid {_BORDER};
    border-radius: 10px;
}}
QFrame#campaignCard:hover {{ border-color: #3a3a3a; background: {_BG3}; }}
QLabel#cardName {{ font-size: 14px; font-weight: 600; }}
QLabel#cardStat {{ font-size: 18px; font-weight: 700; color: {_ACCENT}; }}

/* ── Stats strip ────────────────────────────────────────────────────── */
QFrame#statsStrip {{ background: {_BG2}; border: 1px solid {_BORDER}; border-radius: 8px; }}
QLabel#statValue  {{ font-size: 24px; font-weight: 700; color: {_ACCENT}; }}
QLabel#statLabel  {{ font-size: 11px; color: {_FG_DIM}; }}

/* ── Panels / Splitters ─────────────────────────────────────────────── */
QFrame#panelFrame {{ background: {_BG2}; border: 1px solid {_BORDER}; border-radius: 8px; }}
QLabel#panelHeader {{
    font-size: 11px; font-weight: 600; color: {_FG_DIM};
    text-transform: uppercase; letter-spacing: 0.8px;
    padding: 8px 12px 6px; border-bottom: 1px solid {_BORDER};
}}
QSplitter::handle {{ background: {_BORDER}; width: 1px; height: 1px; }}

/* ── Lists ──────────────────────────────────────────────────────────── */
QListWidget#sideList, QListWidget#recentList, QListWidget#diceHistory {{
    background: transparent; border: none;
    outline: none; padding: 4px;
}}
QListWidget#sideList::item, QListWidget#recentList::item {{
    padding: 7px 10px; border-radius: 5px;
    color: {_FG_MID};
}}
QListWidget#sideList::item:selected,
QListWidget#recentList::item:selected {{
    background: rgba(79,158,255,0.15); color: {_FG};
}}
QListWidget#sideList::item:hover,
QListWidget#recentList::item:hover {{
    background: rgba(255,255,255,0.04); color: {_FG};
}}
QListWidget#diceHistory::item {{ padding: 5px 10px; color: {_FG_MID}; }}

/* ── Inputs ─────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QComboBox, QSpinBox {{
    background: {_BG3}; border: 1px solid {_BORDER};
    border-radius: 6px; padding: 6px 10px; color: {_FG};
    selection-background-color: rgba(79,158,255,0.3);
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {_ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {_BG3}; border: 1px solid {_BORDER}; }}

/* ── Buttons ────────────────────────────────────────────────────────── */
QPushButton {{
    background: {_BG3}; border: 1px solid {_BORDER};
    border-radius: 6px; padding: 7px 16px; color: {_FG};
}}
QPushButton:hover {{ background: #303030; border-color: #3a3a3a; }}
QPushButton:pressed {{ background: #252525; }}

QPushButton#accentBtn {{
    background: {_ACCENT}; border: none; color: #fff; font-weight: 600;
}}
QPushButton#accentBtn:hover {{ background: #3d8de0; }}

QPushButton#ghostBtn {{
    background: transparent; border: 1px solid {_BORDER}; color: {_FG_MID};
}}
QPushButton#ghostBtn:hover {{ border-color: {_FG_MID}; color: {_FG}; }}

QPushButton#dangerBtn {{
    background: transparent; border: 1px solid rgba(224,85,85,0.4); color: {_DANGER};
}}
QPushButton#dangerBtn:hover {{ background: rgba(224,85,85,0.12); }}

/* ── System selector cards ──────────────────────────────────────────── */
QPushButton#sysCard {{
    background: {_BG3}; border: 1px solid {_BORDER};
    border-radius: 8px; font-size: 11px;
    text-align: center; color: {_FG_MID};
}}
QPushButton#sysCard:hover   {{ background: #2e2e2e; color: {_FG}; border-color: #3a3a3a; }}
QPushButton#sysCard:checked {{ border: 2px solid {_ACCENT}; color: {_FG}; background: rgba(79,158,255,0.10); }}

QPushButton#sysCardCustom {{
    background: {_BG3}; border: 1px dashed #5c6bc0;
    border-radius: 8px; font-size: 11px;
    text-align: center; color: {_FG_MID};
}}
QPushButton#sysCardCustom:hover   {{ background: rgba(92,107,192,0.12); color: {_FG}; border-color: #7986cb; }}
QPushButton#sysCardCustom:checked {{ border: 2px solid #7986cb; color: {_FG}; background: rgba(92,107,192,0.18); }}

/* ── Dice ───────────────────────────────────────────────────────────── */
QPushButton#dieBtn {{
    background: {_BG3}; border: 1px solid {_BORDER};
    border-radius: 10px; font-size: 16px; font-weight: 700; color: {_ACCENT};
}}
QPushButton#dieBtn:hover {{ background: rgba(79,158,255,0.15); border-color: {_ACCENT}; }}
QPushButton#dieBtn:pressed {{ background: rgba(79,158,255,0.25); }}

QLineEdit#diceExpr {{ font-size: 14px; }}
QLabel#diceResult  {{ font-size: 64px; font-weight: 800; color: {_FG}; }}
QLabel#diceDetail  {{ font-size: 13px; color: {_FG_MID}; }}

QPushButton#saveExprBtn {{
    background: {_BG3}; border: 1px solid {_ACCENT};
    border-radius: 6px; color: {_ACCENT}; padding: 0 14px;
}}
QPushButton#saveExprBtn:hover {{ background: rgba(79,158,255,0.12); }}
QPushButton#saveExprBtn:pressed {{ background: rgba(79,158,255,0.22); }}

QPushButton#dimBtn {{
    background: transparent; border: 1px solid {_BORDER};
    border-radius: 5px; color: {_FG_DIM}; font-size: 11px; padding: 0 10px;
}}
QPushButton#dimBtn:hover {{ border-color: #555555; color: {_FG_MID}; }}

/* Saved expression chips */
QScrollArea#savedExprScroll {{ background: transparent; border: none; }}
QWidget#savedExprContainer  {{ background: transparent; }}
QFrame#exprChip {{
    background: {_BG3}; border: 1px solid {_BORDER}; border-radius: 14px;
}}
QFrame#exprChip:hover {{ border-color: #3a3a3a; }}
QPushButton#chipUseBtn {{
    background: transparent; border: none;
    color: {_FG_MID}; font-size: 12px;
    padding: 4px 6px 4px 12px; text-align: left;
}}
QPushButton#chipUseBtn:hover {{ color: {_FG}; }}
QPushButton#chipDelBtn {{
    background: transparent; border: none;
    color: {_FG_DIM}; font-size: 13px; font-weight: 700;
    padding: 2px 8px 2px 2px;
}}
QPushButton#chipDelBtn:hover {{ color: {_DANGER}; }}
QLabel#dimHint {{ color: {_FG_DIM}; font-size: 12px; }}

/* ── Compendium ─────────────────────────────────────────────────────── */
QTextEdit#compBody {{
    background: transparent; border: none;
    font-size: 13px; color: {_FG_MID};
}}
QLineEdit#compSearchBar {{
    background: {_BG3}; border: 1px solid {_BORDER};
    border-radius: 16px; padding: 5px 14px;
    font-size: 12px; color: {_FG};
}}
QLineEdit#compSearchBar:focus {{ border-color: {_ACCENT}; }}
QPushButton#compSearchClear {{
    background: transparent; border: none;
    color: {_FG_DIM}; font-size: 14px; border-radius: 12px;
    padding: 0;
}}
QPushButton#compSearchClear:hover {{ color: {_FG}; }}

/* ── Book manager ────────────────────────────────────────────────────── */
QListWidget#bookList {{
    background: {_BG3}; border: 1px solid {_BORDER};
    border-radius: 6px; padding: 4px; outline: none;
}}
QListWidget#bookList::item {{
    padding: 5px 8px; border-radius: 4px;
}}
QListWidget#bookList::item:hover {{ background: rgba(255,255,255,0.04); }}

/* ── Quest page ──────────────────────────────────────────────────────── */
QFrame#questLeftPanel {{ background: {_BG2}; border-right: 1px solid {_BORDER}; }}
QFrame#questLeftHdr   {{ background: {_BG2}; border-bottom: 1px solid {_BORDER}; }}
QFrame#questStatusNav {{ background: {_BG2}; }}
QFrame#questSearchFrame {{ background: {_BG2}; border-bottom: 1px solid {_BORDER}; }}
QScrollArea#questDetailScroll {{ background: {_BG}; border: none; }}
QWidget#questDetailWidget     {{ background: {_BG}; }}

QLabel#questPanelTitle {{
    font-size: 15px; font-weight: 700; color: {_FG};
}}
QLabel#questStatsLbl {{
    font-size: 10px; color: {_FG_DIM}; background: transparent;
}}
QPushButton#questAddBtn {{
    background: {_ACCENT}; border: none; border-radius: 5px;
    color: #fff; font-size: 11px; font-weight: 600; padding: 0 10px;
}}
QPushButton#questAddBtn:hover   {{ background: #3d8de0; }}
QPushButton#questAddBtn:pressed {{ background: #2d7dc8; }}

/* Search bar */
QLineEdit#questSearch {{
    background: {_BG3}; border: 1px solid {_BORDER};
    border-radius: 12px; padding: 4px 10px;
    font-size: 12px; color: {_FG};
}}
QLineEdit#questSearch:focus {{ border-color: {_ACCENT}; }}

/* Vertical status nav */
QPushButton#questNavBtn {{
    background: transparent; border: none;
    text-align: left; padding: 6px 10px;
    border-radius: 6px; color: {_FG_MID}; font-size: 13px;
}}
QPushButton#questNavBtn:hover   {{ background: rgba(255,255,255,0.05); color: {_FG}; }}
QPushButton#questNavBtn:checked {{ background: rgba(79,158,255,0.13); color: {_FG}; font-weight: 600; }}

/* Quest list items */
QListWidget#questList {{
    background: transparent; border: none; outline: none; padding: 4px;
}}
QListWidget#questList::item          {{ border-radius: 6px; }}
QListWidget#questList::item:selected {{ background: rgba(79,158,255,0.15); }}
QListWidget#questList::item:hover    {{ background: rgba(255,255,255,0.04); }}

QLabel#questItemTitle {{ font-size: 13px; font-weight: 600; color: {_FG}; background: transparent; }}
QLabel#questItemMeta  {{ font-size: 11px; color: {_FG_DIM}; background: transparent; }}
QLabel#questItemProg  {{ font-size: 11px; background: transparent; }}

/* Detail panel */
QLabel#questDetailTitle {{
    font-size: 20px; font-weight: 700; color: {_FG};
}}
QLabel#questSectionLabel {{
    font-size: 10px; font-weight: 700; color: {_FG_DIM};
    text-transform: uppercase; letter-spacing: 1.2px;
    background: transparent;
}}
QFrame#questDivider  {{ background: {_BORDER}; border: none; }}
QLabel#questBodyText {{ font-size: 13px; color: {_FG_MID}; background: transparent; }}
QLabel#questBodyDim  {{ font-size: 13px; color: {_FG_DIM};  background: transparent; font-style: italic; }}

/* Info grid labels */
QLabel#questInfoKey {{
    font-size: 11px; font-weight: 600; color: {_FG_DIM};
    background: transparent;
}}
QLabel#questInfoVal {{
    font-size: 12px; color: {_FG_MID}; background: transparent;
}}

/* Tag chips */
QLabel#questTagChip {{
    background: {_BG3}; color: {_FG_MID};
    border: 1px solid {_BORDER}; border-radius: 10px;
    padding: 1px 8px; font-size: 11px;
}}

/* Objective checkboxes */
QCheckBox#questObjCheck {{ font-size: 13px; color: {_FG}; spacing: 8px; background: transparent; }}
QCheckBox#questObjCheck::indicator {{
    width: 16px; height: 16px;
    border: 2px solid {_BORDER}; border-radius: 4px; background: {_BG3};
}}
QCheckBox#questObjCheck::indicator:hover   {{ border-color: {_ACCENT}; }}
QCheckBox#questObjCheck::indicator:checked {{
    background: {_ACCENT}; border-color: {_ACCENT};
}}

/* ── Assets page ─────────────────────────────────────────────────────── */
QFrame#assetsTopBar  {{ background: {_BG2}; border-bottom: 1px solid {_BORDER}; }}
QFrame#assetCatPanel {{ background: {_BG2}; border-right: 1px solid {_BORDER}; }}
QWidget#assetRightPanel {{ background: {_BG}; }}
QScrollArea#assetScroll  {{ background: {_BG}; border: none; }}
QWidget#assetGridWidget  {{ background: {_BG}; }}
QLineEdit#assetSearch {{
    background: {_BG3}; border: 1px solid {_BORDER};
    border-radius: 14px; padding: 4px 12px; color: {_FG};
}}
QLineEdit#assetSearch:focus {{ border-color: {_ACCENT}; }}

QPushButton#assetCatBtn {{
    background: transparent; border: none;
    text-align: left; padding: 6px 10px;
    border-radius: 6px; color: {_FG_MID}; font-size: 13px;
}}
QPushButton#assetCatBtn:hover   {{ background: rgba(255,255,255,0.04); color: {_FG}; }}
QPushButton#assetCatBtn:checked {{ background: rgba(79,158,255,0.12); color: {_FG}; }}

QFrame#assetCard {{
    background: {_BG2}; border: 1px solid {_BORDER};
    border-radius: 10px;
}}
QFrame#assetCard:hover {{ border-color: {_ACCENT}; background: {_BG3}; }}
QLabel#assetName  {{ font-size: 12px; color: {_FG}; }}
QLabel#assetThumb {{ background: transparent; border-radius: 6px; }}

/* ── Toast ──────────────────────────────────────────────────────────── */
QLabel#toast {{
    background: rgba(28,28,28,0.95);
    color: {_FG}; font-size: 12px;
    padding: 9px 20px; border-radius: 8px;
    border: 1px solid {_BORDER};
}}

/* ── Dialogs ────────────────────────────────────────────────────────── */
QDialog {{ background: {_BG}; color: {_FG}; }}

/* Form labels inside dialogs */
QFormLayout QLabel {{
    color: {_FG_MID}; font-size: 12px; font-weight: 500;
    min-width: 90px;
}}

/* QDialogButtonBox — style as proper themed buttons */
QDialogButtonBox QPushButton {{
    min-width: 90px; padding: 7px 20px;
}}
QDialogButtonBox QPushButton:default {{
    background: {_ACCENT}; color: #ffffff;
    font-weight: 600; border-color: {_ACCENT};
}}
QDialogButtonBox QPushButton:default:hover  {{ background: #3d8de0; border-color: #3d8de0; }}
QDialogButtonBox QPushButton:default:pressed {{ background: #2d7dc8; }}

/* Generic QTabWidget — applies to all tab widgets not specifically named */
QTabWidget::pane {{
    border: 1px solid {_BORDER}; border-top: none;
    background: {_BG}; border-radius: 0 0 6px 6px;
}}
QTabBar {{ background: transparent; border: none; }}
QTabBar::tab {{
    background: {_BG2}; color: {_FG_MID};
    border: 1px solid {_BORDER}; border-bottom: none;
    padding: 7px 18px; font-size: 12px; font-weight: 500;
    margin-right: 2px; border-radius: 5px 5px 0 0;
}}
QTabBar::tab:selected {{
    background: {_BG}; color: {_FG}; font-weight: 600;
    border-top: 2px solid {_ACCENT};
}}
QTabBar::tab:hover:!selected {{ background: {_BG3}; color: {_FG}; }}

/* ── Gallery ────────────────────────────────────────────────────────── */
QWidget#galleryToolbar  {{ background: {_BG}; border-bottom: 1px solid {_BORDER}; }}
QWidget#galleryChipBar  {{ background: {_BG}; border-bottom: 1px solid {_BORDER}; }}

QFrame#galleryCard {{
    background: {_BG2};
    border: 1px solid {_BORDER};
    border-radius: 10px;
}}
QFrame#galleryCard:hover {{ border-color: #3a3a3a; }}

QLabel#galleryThumb {{
    background: {_BG3};
    border-radius: 7px;
}}
QLabel#galleryCardTitle {{
    font-size: 12px; font-weight: 600; color: {_FG};
    padding: 0 4px;
}}
QLabel#galleryCardDate {{
    font-size: 10px; color: {_FG_DIM}; padding: 0 2px;
}}

QWidget#galleryCardOverlay {{
    background: rgba(0,0,0,0.60);
    border-radius: 7px;
}}
QWidget#galleryCardOverlay QPushButton {{
    font-size: 12px; font-weight: 600; border-radius: 6px;
    padding: 5px 0;
}}
QPushButton#primaryBtn {{
    background: {_ACCENT}; border: none; color: #fff;
}}
QPushButton#primaryBtn:hover {{ background: #3d8de0; }}
QPushButton#secondaryBtn {{
    background: rgba(255,255,255,0.12); border: none; color: {_FG};
}}
QPushButton#secondaryBtn:hover {{ background: rgba(255,255,255,0.22); }}

/* Gallery stage filter chips */
QPushButton#chip {{
    background: transparent;
    border: 1px solid {_BORDER};
    border-radius: 13px;
    padding: 0 12px;
    font-size: 11px; color: {_FG_MID};
}}
QPushButton#chip:hover {{ border-color: {_FG_MID}; color: {_FG}; }}
QPushButton#chipActive {{
    background: rgba(79,158,255,0.18);
    border: 1px solid {_ACCENT};
    border-radius: 13px;
    padding: 0 12px;
    font-size: 11px; color: {_ACCENT}; font-weight: 600;
}}

/* Lightbox */
QWidget#lightboxHeader {{ background: {_BG2}; border-bottom: 1px solid {_BORDER}; }}
QLabel#lightboxCounter  {{ font-size: 13px; font-weight: 600; color: {_FG}; }}
QWidget#lightboxInfo    {{ background: {_BG2}; border-top: 1px solid {_BORDER}; }}
QLabel#lightboxTitle    {{ font-size: 15px; font-weight: 700; color: {_FG}; }}
QLabel#lightboxMeta     {{ font-size: 12px; color: {_FG_MID}; }}
QLabel#lightboxImage    {{ background: #111; }}
QPushButton#lightboxNavBtn {{
    background: transparent; border: none; color: {_FG_DIM};
    font-size: 32px;
}}
QPushButton#lightboxNavBtn:hover  {{ color: {_FG}; }}
QPushButton#lightboxNavBtn:disabled {{ color: #2a2a2a; }}

/* Add photo dialog */
QFrame#galleryImgPreviewFrame {{
    background: {_BG3}; border: 1px solid {_BORDER}; border-radius: 8px;
}}
QLabel#galleryImgPreview {{ background: transparent; color: {_FG_DIM}; }}

/* ── Encounters ─────────────────────────────────────────────────────── */
QFrame#encListPanel  {{ background: {_BG2}; border: 1px solid {_BORDER}; border-radius: 8px; }}
QListWidget#encList  {{
    background: transparent; border: none; outline: none; padding: 4px;
}}
QListWidget#encList::item {{
    padding: 8px 10px; border-radius: 6px; color: {_FG_MID};
}}
QListWidget#encList::item:selected {{
    background: rgba(79,158,255,0.15); color: {_FG};
}}
QListWidget#encList::item:hover {{
    background: rgba(255,255,255,0.04); color: {_FG};
}}
QLineEdit#encNameEdit {{
    font-size: 16px; font-weight: 600; background: transparent;
    border: none; border-bottom: 1px solid {_BORDER};
    border-radius: 0; padding: 4px 2px;
}}
QLineEdit#encNameEdit:focus {{ border-bottom-color: {_ACCENT}; }}
QTextEdit#encDescEdit {{
    background: transparent; border: 1px dashed {_BORDER};
    border-radius: 6px; padding: 6px; color: {_FG_MID};
}}
QFrame#sectionCard {{
    background: {_BG2}; border: 1px solid {_BORDER}; border-radius: 8px;
}}
QListWidget#monsterList {{
    background: {_BG3}; border: 1px solid {_BORDER};
    border-radius: 6px; padding: 4px; outline: none;
}}
QListWidget#monsterList::item {{
    padding: 5px 8px; border-radius: 4px; color: {_FG_MID};
}}
QListWidget#monsterList::item:selected {{
    background: rgba(79,158,255,0.15); color: {_FG};
}}
QLabel#diffBadge {{
    font-size: 13px; font-weight: 700; background: transparent;
}}
QLabel#diffBadgeLarge {{
    font-size: 15px; font-weight: 800; background: transparent;
}}

/* ── Initiative tracker ──────────────────────────────────────────── */
QTabWidget#encTabWidget::pane   {{ border: none; }}
QTabWidget#encTabWidget::tab-bar {{ alignment: left; }}
QTabWidget#encTabWidget QTabBar::tab {{
    background: transparent; border: none;
    padding: 8px 18px; color: {_FG_DIM};
    font-size: 13px;
}}
QTabWidget#encTabWidget QTabBar::tab:selected {{
    color: {_FG}; border-bottom: 2px solid {_ACCENT};
    font-weight: 600;
}}
QTabWidget#encTabWidget QTabBar::tab:hover {{ color: {_FG}; }}

QLabel#roundLabel  {{ font-weight: 700; color: #f0a020; min-width: 80px; }}
QLabel#activeBanner {{
    background: rgba(79,158,255,0.12);
    border: 1px solid rgba(79,158,255,0.35);
    border-radius: 6px; color: {_ACCENT};
    font-size: 15px; font-weight: 700; padding: 7px;
}}
QTableWidget {{
    background: {_BG2}; border: 1px solid {_BORDER};
    border-radius: 6px; gridline-color: transparent;
    alternate-background-color: {_BG3};
}}
QTableWidget::item {{ padding: 4px 8px; color: {_FG}; }}
QTableWidget::item:selected {{
    background: rgba(79,158,255,0.20); color: {_FG};
}}
QHeaderView::section {{
    background: {_BG3}; border: none;
    border-bottom: 1px solid {_BORDER};
    padding: 5px 8px; font-size: 11px;
    font-weight: 600; color: {_FG_DIM};
    text-transform: uppercase; letter-spacing: 0.5px;
}}

/* ── Character sub-tabs ──────────────────────────────────────────── */
QTabWidget#charSubTabs::pane   {{ border: none; background: transparent; }}
QTabWidget#charSubTabs QTabBar::tab {{
    background: transparent; border: none;
    padding: 5px 12px; color: {_FG_DIM};
    font-size: 12px;
}}
QTabWidget#charSubTabs QTabBar::tab:selected {{
    color: {_FG}; border-bottom: 2px solid {_ACCENT};
    font-weight: 600;
}}
QTabWidget#charSubTabs QTabBar::tab:hover {{ color: {_FG}; }}
""")


# ══════════════════════════════════════════════════════════════════════════════
#  Detail sub-widgets
# ══════════════════════════════════════════════════════════════════════════════

class _SessionDetail(QWidget):
    edit_requested   = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._session_id = None

        self._title = QLabel()
        self._title.setObjectName("cardName")
        self._title.setWordWrap(True)
        self._meta  = QLabel()
        self._meta.setObjectName("dimLabel")
        self._chronicle = QTextEdit()
        self._chronicle.setReadOnly(True)
        self._chronicle.setObjectName("compBody")
        self._chronicle.setPlaceholderText("No chronicle recorded yet.")

        btn_row = QHBoxLayout()
        self._edit_btn = QPushButton("✏ Edit")
        self._edit_btn.setObjectName("ghostBtn")
        self._edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._session_id))
        self._del_btn  = QPushButton("Delete")
        self._del_btn.setObjectName("dangerBtn")
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self._session_id))
        btn_row.addWidget(self._edit_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._del_btn)

        lay.addWidget(self._title)
        lay.addWidget(self._meta)
        lay.addWidget(self._chronicle, 1)
        lay.addLayout(btn_row)

        self.clear()

    def load(self, session, sys_id: str = "custom"):
        self._session_id = getattr(session, "id", None)
        sys_obj = SYSTEMS.get(sys_id)
        label   = sys_obj.session_label if sys_obj else "Session"
        num     = getattr(session, "session_number", 0) or 0
        self._title.setText(f"{label} {num}: {session.title}")
        parts = []
        d = getattr(session, "date_played", None)
        if d: parts.append(str(d))
        loc = getattr(session, "location_name", None) or getattr(session, "location", None)
        if loc: parts.append(f"📍 {loc}")
        outcome = getattr(session, "outcome", "")
        if outcome: parts.append(f"⚑ {outcome}")
        self._meta.setText("  ·  ".join(parts))
        self._chronicle.setPlainText(getattr(session, "chronicle_text", "") or "")
        self._edit_btn.setVisible(True)
        self._del_btn.setVisible(True)

    def clear(self):
        self._session_id = None
        self._title.setText("")
        self._meta.setText("")
        self._chronicle.clear()
        self._edit_btn.setVisible(False)
        self._del_btn.setVisible(False)


class _AddSpellDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Spell")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self._name  = QLineEdit()
        self._name.setPlaceholderText("e.g. Fireball")
        self._level = QSpinBox()
        self._level.setRange(0, 9)
        self._notes = QLineEdit()
        self._notes.setPlaceholderText("School, duration, notes…")
        form.addRow("Name",  self._name)
        form.addRow("Level", self._level)
        form.addRow("Notes", self._notes)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "name":  self._name.text().strip(),
            "level": self._level.value(),
            "notes": self._notes.text().strip(),
        }


class _AddInventoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Item")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self._name  = QLineEdit()
        self._name.setPlaceholderText("Item name…")
        self._qty   = QSpinBox()
        self._qty.setRange(1, 9999)
        self._qty.setValue(1)
        self._type  = QComboBox()
        self._type.addItems(["Gear", "Weapon", "Armor", "Consumable",
                              "Magic Item", "Treasure", "Other"])
        self._notes = QLineEdit()
        self._notes.setPlaceholderText("Notes…")
        form.addRow("Name",  self._name)
        form.addRow("Qty",   self._qty)
        form.addRow("Type",  self._type)
        form.addRow("Notes", self._notes)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "name":      self._name.text().strip(),
            "qty":       self._qty.value(),
            "item_type": self._type.currentText(),
            "notes":     self._notes.text().strip(),
        }


class _CharacterDetail(QWidget):
    edit_requested   = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, service=None, parent=None):
        super().__init__(parent)
        self._svc     = service
        self._char_id = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._name  = QLabel()
        self._name.setObjectName("cardName")
        self._role  = QLabel()
        self._role.setObjectName("dimLabel")
        self._stats_frame = QFrame()
        self._stats_frame.setObjectName("statsStrip")
        self._stats_lay = QHBoxLayout(self._stats_frame)
        self._stats_lay.setContentsMargins(14, 10, 14, 10)

        # ── Sub-tabs: Notes | Spells | Inventory ──────────────────────────────
        self._sub_tabs = QTabWidget()
        self._sub_tabs.setObjectName("charSubTabs")

        # Notes tab
        notes_w = QWidget()
        notes_lay = QVBoxLayout(notes_w)
        notes_lay.setContentsMargins(0, 6, 0, 0)
        self._notes = QTextEdit()
        self._notes.setReadOnly(True)
        self._notes.setObjectName("compBody")
        notes_lay.addWidget(self._notes)
        self._sub_tabs.addTab(notes_w, "Notes")

        # Spells tab
        spells_w = QWidget()
        sl = QVBoxLayout(spells_w)
        sl.setContentsMargins(0, 6, 0, 0)
        sl.setSpacing(6)
        spell_hdr = QHBoxLayout()
        spell_hdr.addStretch()
        add_spell_btn = QPushButton("＋ Add Spell")
        add_spell_btn.setObjectName("accentBtn")
        add_spell_btn.clicked.connect(self._on_add_spell)
        spell_hdr.addWidget(add_spell_btn)
        sl.addLayout(spell_hdr)
        self._spell_list = QListWidget()
        self._spell_list.setObjectName("sideList")
        sl.addWidget(self._spell_list, 1)
        rem_spell_btn = QPushButton("✕  Remove Selected")
        rem_spell_btn.setObjectName("dangerBtn")
        rem_spell_btn.clicked.connect(self._on_remove_spell)
        sl.addWidget(rem_spell_btn, alignment=Qt.AlignLeft)
        self._sub_tabs.addTab(spells_w, "Spells")

        # Inventory tab
        inv_w = QWidget()
        il = QVBoxLayout(inv_w)
        il.setContentsMargins(0, 6, 0, 0)
        il.setSpacing(6)
        inv_hdr = QHBoxLayout()
        inv_hdr.addStretch()
        add_item_btn = QPushButton("＋ Add Item")
        add_item_btn.setObjectName("accentBtn")
        add_item_btn.clicked.connect(self._on_add_inventory)
        inv_hdr.addWidget(add_item_btn)
        il.addLayout(inv_hdr)
        self._inv_list = QListWidget()
        self._inv_list.setObjectName("sideList")
        il.addWidget(self._inv_list, 1)
        rem_inv_btn = QPushButton("✕  Remove Selected")
        rem_inv_btn.setObjectName("dangerBtn")
        rem_inv_btn.clicked.connect(self._on_remove_inventory)
        il.addWidget(rem_inv_btn, alignment=Qt.AlignLeft)
        self._sub_tabs.addTab(inv_w, "Inventory")

        btn_row = QHBoxLayout()
        self._edit_btn = QPushButton("✏ Edit")
        self._edit_btn.setObjectName("ghostBtn")
        self._edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._char_id))
        self._del_btn  = QPushButton("Delete")
        self._del_btn.setObjectName("dangerBtn")
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self._char_id))
        btn_row.addWidget(self._edit_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._del_btn)

        lay.addWidget(self._name)
        lay.addWidget(self._role)
        lay.addWidget(self._stats_frame)
        lay.addWidget(self._sub_tabs, 1)
        lay.addLayout(btn_row)

        self.clear()

    def load(self, char, sys_id: str = "custom"):
        self._char_id = getattr(char, "id", None)
        sys_obj  = SYSTEMS.get(sys_id)
        tmpl_key = sys_obj.character_template if sys_obj else "custom"
        tmpl     = CHAR_TEMPLATES.get(tmpl_key, CHAR_TEMPLATES["custom"])

        self._name.setText(char.name)
        role  = getattr(char, "character_role", "") or ""
        level = getattr(char, "level", None)
        cls   = getattr(char, "character_class", None) or ""
        race  = getattr(char, "race", None) or ""
        meta_parts = [role]
        if cls:   meta_parts.append(cls)
        if race:  meta_parts.append(race)
        if level: meta_parts.append(f"Level {level}")
        self._role.setText("  ·  ".join(p for p in meta_parts if p))

        # Rebuild stats strip
        while self._stats_lay.count():
            item = self._stats_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        stats_json = getattr(char, "stats_json", None) or "{}"
        try:
            stats = json.loads(stats_json)
        except Exception:
            stats = {}

        # Show core stats
        core = tmpl.get("core_stats", [])
        if core:
            for label, key in core[:8]:  # cap at 8 for display
                val = stats.get(key, getattr(char, key, "—") or "—")
                col = QVBoxLayout()
                col.setSpacing(0)
                vl = QLabel(str(val))
                vl.setObjectName("statValue")
                vl.setAlignment(Qt.AlignCenter)
                vl.setFixedWidth(42)
                ll = QLabel(label)
                ll.setObjectName("statLabel")
                ll.setAlignment(Qt.AlignCenter)
                ll.setFixedWidth(42)
                col.addWidget(vl)
                col.addWidget(ll)
                self._stats_lay.addLayout(col)
        else:
            hp = getattr(char, "hit_points", 0) or 0
            maxhp = getattr(char, "max_hit_points", 0) or 0
            ac    = getattr(char, "armor_class", 0) or 0
            for label, val in [("HP", f"{hp}/{maxhp}"), ("AC", str(ac))]:
                col = QVBoxLayout()
                col.setSpacing(0)
                vl = QLabel(str(val))
                vl.setObjectName("statValue")
                vl.setAlignment(Qt.AlignCenter)
                ll = QLabel(label)
                ll.setObjectName("statLabel")
                ll.setAlignment(Qt.AlignCenter)
                col.addWidget(vl)
                col.addWidget(ll)
                self._stats_lay.addLayout(col)
        self._stats_lay.addStretch()

        notes = getattr(char, "notes", "") or ""
        traits = getattr(char, "traits", "") or ""
        self._notes.setPlainText("\n\n".join(p for p in [traits, notes] if p))

        self._edit_btn.setVisible(True)
        self._del_btn.setVisible(True)
        self._stats_frame.setVisible(bool(core) or True)

        # Load spells
        self._spell_list.clear()
        if self._svc:
            try:
                for spell in self._svc.get_character_spells(self._char_id):
                    lvl  = getattr(spell, "spell_level", 0) or 0
                    name = getattr(spell, "spell_name", "") or ""
                    item = QListWidgetItem(f"Lv {lvl}  {name}")
                    item.setData(Qt.UserRole, spell.id)
                    self._spell_list.addItem(item)
            except Exception:
                pass

        # Load inventory
        self._inv_list.clear()
        if self._svc:
            try:
                for inv in self._svc.get_character_inventory(self._char_id):
                    qty  = getattr(inv, "quantity", 1) or 1
                    name = getattr(inv, "name", "") or ""
                    typ  = getattr(inv, "item_type", "") or ""
                    label = f"{name}  ×{qty}" + (f"  [{typ}]" if typ else "")
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, inv.id)
                    self._inv_list.addItem(item)
            except Exception:
                pass

    def clear(self):
        self._char_id = None
        self._name.clear()
        self._role.clear()
        self._notes.clear()
        self._edit_btn.setVisible(False)
        self._del_btn.setVisible(False)
        if hasattr(self, "_spell_list"):
            self._spell_list.clear()
        if hasattr(self, "_inv_list"):
            self._inv_list.clear()

    def _on_add_spell(self):
        if not self._svc or not self._char_id:
            return
        dlg = _AddSpellDialog(self)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            try:
                self._svc.add_character_spell(
                    self._char_id,
                    spell_name=d["name"],
                    spell_level=d["level"],
                    notes=d["notes"],
                )
                # Reload spell list
                self._spell_list.clear()
                for spell in self._svc.get_character_spells(self._char_id):
                    lvl  = getattr(spell, "spell_level", 0) or 0
                    name = getattr(spell, "spell_name", "") or ""
                    item = QListWidgetItem(f"Lv {lvl}  {name}")
                    item.setData(Qt.UserRole, spell.id)
                    self._spell_list.addItem(item)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_remove_spell(self):
        if not self._svc:
            return
        item = self._spell_list.currentItem()
        if not item:
            return
        spell_id = item.data(Qt.UserRole)
        if not spell_id:
            return
        try:
            self._svc.delete_character_spell(spell_id)
            self._spell_list.takeItem(self._spell_list.currentRow())
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_add_inventory(self):
        if not self._svc or not self._char_id:
            return
        dlg = _AddInventoryDialog(self)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            try:
                self._svc.add_inventory_item(
                    self._char_id,
                    name=d["name"],
                    quantity=d["qty"],
                    item_type=d["item_type"],
                    notes=d["notes"],
                )
                # Reload inventory list
                self._inv_list.clear()
                for inv in self._svc.get_character_inventory(self._char_id):
                    qty   = getattr(inv, "quantity", 1) or 1
                    iname = getattr(inv, "name", "") or ""
                    typ   = getattr(inv, "item_type", "") or ""
                    label = f"{iname}  ×{qty}" + (f"  [{typ}]" if typ else "")
                    row   = QListWidgetItem(label)
                    row.setData(Qt.UserRole, inv.id)
                    self._inv_list.addItem(row)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_remove_inventory(self):
        if not self._svc:
            return
        item = self._inv_list.currentItem()
        if not item:
            return
        item_id = item.data(Qt.UserRole)
        if not item_id:
            return
        try:
            self._svc.delete_inventory_item(item_id)
            self._inv_list.takeItem(self._inv_list.currentRow())
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  _SessionDialog
# ══════════════════════════════════════════════════════════════════════════════

class _SessionDialog(QDialog):
    def __init__(self, session=None, label: str = "Session",
                 session_number: int = 1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Session" if session is None else f"Edit {label}")
        self.setMinimumSize(520, 480)
        self._session = session
        self._label   = label
        self._default_num = session_number
        self._build()

    def result_data(self) -> dict:
        return {
            "title":          self._title.text().strip(),
            "session_number": self._num.value(),
            "date_played":    self._date.text().strip() or None,
            "location_name":  self._loc.text().strip(),
            "scenario_name":  self._scen.text().strip(),
            "outcome":        self._outcome.currentText(),
            "chronicle_text": self._chronicle.toPlainText().strip(),
        }

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._title   = QLineEdit()
        self._title.setPlaceholderText(f"e.g. The Dragon's Lair")
        self._num     = QSpinBox()
        self._num.setRange(0, 9999)
        self._num.setValue(
            getattr(self._session, "session_number", self._default_num)
            if self._session else self._default_num
        )
        self._date    = QLineEdit(
            str(getattr(self._session, "date_played", "") or date.today().isoformat()))
        self._loc  = QLineEdit(
            getattr(self._session, "location_name", "") or "" if self._session else "")
        self._scen = QLineEdit(
            getattr(self._session, "scenario_name", "") or "" if self._session else "")
        self._outcome = QComboBox()
        self._outcome.addItems(["In Progress", "Victory", "Defeat", "Partial Victory",
                                "Fled", "Completed"])
        self._chronicle = QTextEdit()
        self._chronicle.setPlaceholderText("What happened this session?")

        if self._session:
            self._title.setText(self._session.title)
            self._outcome.setCurrentText(
                getattr(self._session, "outcome", "In Progress") or "In Progress")
            self._chronicle.setPlainText(
                getattr(self._session, "chronicle_text", "") or "")

        form.addRow("Title",    self._title)
        form.addRow("#",        self._num)
        form.addRow("Date",     self._date)
        form.addRow("Location", self._loc)
        form.addRow("Scenario", self._scen)
        form.addRow("Outcome",  self._outcome)
        lay.addLayout(form)

        chron_lbl = QLabel("Chronicle / Session Notes")
        chron_lbl.setObjectName("subLabel")
        lay.addWidget(chron_lbl)
        lay.addWidget(self._chronicle, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _try_accept(self):
        if not self._title.text().strip():
            QMessageBox.warning(self, "Required", "Session title is required.")
            return
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  _CharacterDialog  —  system-adaptive
# ══════════════════════════════════════════════════════════════════════════════

class _CharacterDialog(QDialog):
    def __init__(self, system_id: str = "custom",
                 character=None, parent=None):
        super().__init__(parent)
        self._sys_id = system_id
        self._char   = character
        sys_obj      = SYSTEMS.get(system_id)
        self._tmpl   = CHAR_TEMPLATES.get(
            sys_obj.character_template if sys_obj else "custom",
            CHAR_TEMPLATES["custom"])
        self._char_label = sys_obj.character_label if sys_obj else "Character"
        self.setWindowTitle("Add Character" if character is None else "Edit Character")
        self.setMinimumSize(540, 560)
        self._build()

    def result_data(self) -> dict:
        stats = {}
        for label, key in self._tmpl.get("core_stats", []):
            w = self._stat_inputs.get(key)
            if w:
                try:   stats[key] = int(w.text()) if w.text().strip() else 0
                except ValueError: stats[key] = w.text().strip()
        for label, key in self._tmpl.get("combat_fields", []):
            w = self._stat_inputs.get(key)
            if w:
                try:   stats[key] = int(w.text()) if w.text().strip() else 0
                except ValueError: stats[key] = w.text().strip()

        # Map known direct fields
        direct: dict = {
            "name":            self._name.text().strip(),
            "character_role":  self._role.currentText(),
            "notes":           self._notes.toPlainText().strip(),
            "stats_json":      json.dumps(stats),
        }
        if self._tmpl.get("has_level"):
            try: direct["level"] = int(self._stat_inputs.get("level", QLineEdit()).text() or 1)
            except Exception: pass
        hp_w = self._stat_inputs.get("hp")
        if hp_w:
            try: direct["hit_points"] = int(hp_w.text() or 0)
            except Exception: pass
        max_hp_w = self._stat_inputs.get("max_hp")
        if max_hp_w:
            try: direct["max_hit_points"] = int(max_hp_w.text() or 0)
            except Exception: pass
        ac_w = self._stat_inputs.get("ac")
        if ac_w:
            try: direct["armor_class"] = int(ac_w.text() or 0)
            except Exception: pass
        if self._tmpl.get("has_class_race"):
            direct["character_class"] = self._cls.text().strip() if hasattr(self, "_cls") else ""
            direct["race"]            = self._race.text().strip() if hasattr(self, "_race") else ""

        return direct

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)

        c   = self._char
        tmpl = self._tmpl

        # Name + role row
        name_row = QHBoxLayout()
        self._name = QLineEdit(getattr(c, "name", "") if c else "")
        self._name.setPlaceholderText(f"{self._char_label} name…")
        self._role = QComboBox()
        self._role.addItems(["Player Character", "NPC", "Villain", "Ally",
                             "Monster / Creature", "Vehicle / Mount"])
        if c:
            self._role.setCurrentText(getattr(c, "character_role", "Player Character") or "Player Character")
        name_row.addWidget(self._name, 2)
        name_row.addWidget(self._role, 1)
        lay.addLayout(name_row)

        # Class / race row (for RPG systems)
        self._stat_inputs: dict[str, QLineEdit] = {}
        if tmpl.get("has_class_race"):
            cr_row = QHBoxLayout()
            self._cls  = QLineEdit(getattr(c, "character_class", "") or "" if c else "")
            self._cls.setPlaceholderText("Class")
            self._race = QLineEdit(getattr(c, "race", "") or "" if c else "")
            self._race.setPlaceholderText("Race / Ancestry")
            cr_row.addWidget(self._cls)
            cr_row.addWidget(self._race)
            lay.addLayout(cr_row)

        # Level
        if tmpl.get("has_level"):
            lev_row = QHBoxLayout()
            lev_row.addWidget(QLabel("Level"))
            lev_inp = QLineEdit(str(getattr(c, "level", 1) if c else 1))
            lev_inp.setFixedWidth(60)
            self._stat_inputs["level"] = lev_inp
            lev_row.addWidget(lev_inp)
            lev_row.addStretch()
            lay.addLayout(lev_row)

        # Core stats grid
        core = tmpl.get("core_stats", [])
        if core:
            stats_label = QLabel("Core Stats")
            stats_label.setObjectName("sectionLabel")
            lay.addWidget(stats_label)
            grid = QGridLayout()
            grid.setSpacing(8)
            existing_stats = {}
            if c:
                try:
                    existing_stats = json.loads(getattr(c, "stats_json", "{}") or "{}")
                except Exception:
                    pass
            for i, (label, key) in enumerate(core):
                col_widget = QWidget()
                col_lay = QVBoxLayout(col_widget)
                col_lay.setContentsMargins(0, 0, 0, 0)
                col_lay.setSpacing(2)
                lbl = QLabel(label)
                lbl.setObjectName("statLabel")
                lbl.setAlignment(Qt.AlignCenter)
                inp = QLineEdit(str(existing_stats.get(key, "")))
                inp.setAlignment(Qt.AlignCenter)
                inp.setFixedWidth(56)
                col_lay.addWidget(inp)
                col_lay.addWidget(lbl)
                self._stat_inputs[key] = inp
                grid.addWidget(col_widget, 0, i)
            lay.addLayout(grid)

        # Combat fields
        combat = tmpl.get("combat_fields", [])
        if combat:
            combat_label = QLabel("Combat")
            combat_label.setObjectName("sectionLabel")
            lay.addWidget(combat_label)
            form = QFormLayout()
            form.setSpacing(6)
            existing_stats = {}
            if c:
                try:
                    existing_stats = json.loads(getattr(c, "stats_json", "{}") or "{}")
                except Exception:
                    pass
            _direct = {"hp": "hit_points", "max_hp": "max_hit_points", "ac": "armor_class"}
            for label, key in combat:
                if key in self._stat_inputs:
                    continue
                if key in _direct and c:
                    val = str(getattr(c, _direct[key], 0) or 0)
                else:
                    val = str(existing_stats.get(key, ""))
                inp = QLineEdit(val)
                self._stat_inputs[key] = inp
                form.addRow(label, inp)
            lay.addLayout(form)

        # Notes
        notes_lbl = QLabel("Notes / Traits")
        notes_lbl.setObjectName("sectionLabel")
        lay.addWidget(notes_lbl)
        self._notes = QTextEdit(getattr(c, "notes", "") or "" if c else "")
        self._notes.setFixedHeight(70)
        lay.addWidget(self._notes)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _try_accept(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Required", "Character name is required.")
            return
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  _CompendiumEntryDialog
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  _AssetEditDialog
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  _TinyProgressBar  —  thin painted progress bar used in quest views
# ══════════════════════════════════════════════════════════════════════════════

class _TinyProgressBar(QWidget):
    """A 5 px tall filled progress bar drawn with QPainter."""

    def __init__(self, value: int, total: int, parent=None):
        super().__init__(parent)
        self._value = max(0, value)
        self._total = max(1, total)
        self.setFixedHeight(5)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):          # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r    = h // 2

        # Background track
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_BG3))
        p.drawRoundedRect(0, 0, w, h, r, r)

        # Fill
        if self._total > 0:
            fill_w = max(r * 2, int(w * self._value / self._total))
            color  = QColor(_SUCCESS if self._value >= self._total else _ACCENT)
            p.setBrush(color)
            p.drawRoundedRect(0, 0, fill_w, h, r, r)

        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  _QuestListItem  —  compact widget used inside the quest QListWidget
# ══════════════════════════════════════════════════════════════════════════════

class _QuestListItem(QWidget):
    """Compact three-row widget rendered inside the quest QListWidget."""

    def __init__(self, quest, obj_total: int, obj_done: int, parent=None):
        super().__init__(parent)
        self._quest     = quest
        self._obj_total = obj_total
        self._obj_done  = obj_done

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(3)

        pcolor = _QUEST_PRIORITY_COLORS.get(quest.priority, "#a0a0a0")

        # ── Row 1: pin star + priority dot + title ────────────────────────
        t_row = QHBoxLayout()
        t_row.setSpacing(5)
        t_row.setContentsMargins(0, 0, 0, 0)

        if quest.pinned:
            pin_lbl = QLabel("★")
            pin_lbl.setFixedSize(14, 16)
            pin_lbl.setStyleSheet("color:#f0c040; font-size:10px;")
            pin_lbl.setAlignment(Qt.AlignCenter)
            t_row.addWidget(pin_lbl)

        dot = QLabel("●")
        dot.setFixedSize(12, 16)
        dot.setStyleSheet(f"color:{pcolor}; font-size:9px;")
        dot.setAlignment(Qt.AlignCenter)
        t_row.addWidget(dot)

        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("questItemTitle")
        self._set_title(quest.title)
        t_row.addWidget(self._title_lbl, 1)

        lay.addLayout(t_row)

        # ── Row 2: category + giver + progress counter ────────────────────
        indent = 17 + (14 + 5 if quest.pinned else 0)
        m_row = QHBoxLayout()
        m_row.setSpacing(5)
        m_row.setContentsMargins(indent, 0, 0, 0)

        meta_parts = [quest.category]
        if quest.quest_giver:
            meta_parts.append(quest.quest_giver)
        self._cat_lbl = QLabel("  ·  ".join(meta_parts))
        self._cat_lbl.setObjectName("questItemMeta")

        self._prog_lbl = QLabel()
        self._prog_lbl.setObjectName("questItemProg")
        self._update_prog_lbl(obj_total, obj_done)

        m_row.addWidget(self._cat_lbl, 1)
        m_row.addWidget(self._prog_lbl)
        lay.addLayout(m_row)

        # ── Row 3: mini progress bar (only if objectives exist) ───────────
        if obj_total > 0:
            bar = _TinyProgressBar(obj_done, obj_total)
            bar.setContentsMargins(indent, 0, 0, 0)
            lay.addWidget(bar)
            lay.addSpacing(1)

    def _set_title(self, text: str):
        fm = self._title_lbl.fontMetrics()
        self._title_lbl.setText(fm.elidedText(text, Qt.ElideRight, 164))

    def _update_prog_lbl(self, total: int, done: int):
        if total == 0:
            self._prog_lbl.setText("")
        elif done == total:
            self._prog_lbl.setText(f"{done}/{total} done")
            self._prog_lbl.setStyleSheet(f"color:{_SUCCESS}; font-size:11px;")
        else:
            self._prog_lbl.setText(f"{done}/{total}")
            self._prog_lbl.setStyleSheet(f"color:{_FG_DIM}; font-size:11px;")

    def update_progress(self, total: int, done: int):
        self._update_prog_lbl(total, done)

    def update_status(self, status: str):
        """No-op — status changes trigger a full list reload."""
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  _QuestEditDialog
# ══════════════════════════════════════════════════════════════════════════════

class _QuestEditDialog(QDialog):
    def __init__(self, quest=None, sessions=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Quest" if quest is None else "Edit Quest")
        self.setMinimumSize(540, 560)
        self._quest    = quest
        self._sessions = sessions or []
        self._build()

    def result_data(self) -> dict:
        # linked_session_id from combobox
        sess_idx = self._session_combo.currentIndex()
        linked_id = None
        if sess_idx > 0:  # index 0 = "None"
            linked_id = self._session_combo.currentData()
        return {
            "title":             self._title.text().strip(),
            "status":            self._status.currentText(),
            "priority":          self._priority.currentText(),
            "category":          self._category.currentText(),
            "description":       self._desc.toPlainText().strip(),
            "reward":            self._reward.text().strip(),
            "notes":             self._notes.toPlainText().strip(),
            "quest_giver":       self._giver.text().strip(),
            "location":          self._location.text().strip(),
            "date_started":      self._date_started.text().strip(),
            "date_completed":    self._date_completed.text().strip(),
            "linked_session_id": linked_id,
            "tags":              self._tags.text().strip(),
        }

    def _build(self):
        q   = self._quest
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        # ── Title (always visible, above tabs) ───────────────────────────
        title_lbl = QLabel("Quest Title")
        title_lbl.setStyleSheet(
            f"color:{_FG_MID}; font-size:11px; font-weight:600; letter-spacing:0.5px;"
        )
        lay.addWidget(title_lbl)
        self._title = QLineEdit(getattr(q, "title", "") if q else "")
        self._title.setPlaceholderText("e.g. Retrieve the Lost Crown")
        self._title.setFixedHeight(34)
        lay.addWidget(self._title)

        # ── Tabs ─────────────────────────────────────────────────────────
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        # ─ Tab 1: Overview ───────────────────────────────────────────────
        t1 = QWidget()
        f1 = QFormLayout(t1)
        f1.setContentsMargins(16, 16, 16, 16)
        f1.setSpacing(10)
        f1.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f1.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # Status + Priority side-by-side
        sp_row = QHBoxLayout()
        sp_row.setSpacing(8)
        self._status = QComboBox()
        self._status.addItems(_QUEST_STATUSES)
        self._status.setCurrentText(getattr(q, "status", "Active") if q else "Active")
        self._priority = QComboBox()
        self._priority.addItems(_QUEST_PRIORITIES)
        self._priority.setCurrentText(getattr(q, "priority", "Medium") if q else "Medium")
        pri_lbl = QLabel("Priority")
        pri_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:12px; font-weight:500;")
        sp_row.addWidget(self._status, 1)
        sp_row.addWidget(pri_lbl)
        sp_row.addWidget(self._priority, 1)
        f1.addRow("Status", sp_row)

        self._category = QComboBox()
        self._category.addItems(_QUEST_CATEGORIES)
        self._category.setCurrentText(
            getattr(q, "category", "Main Quest") if q else "Main Quest"
        )
        f1.addRow("Category", self._category)

        self._desc = QTextEdit(getattr(q, "description", "") if q else "")
        self._desc.setPlaceholderText("Quest summary, background, or hook…")
        self._desc.setFixedHeight(110)
        f1.addRow("Description", self._desc)

        tabs.addTab(t1, "Overview")

        # ─ Tab 2: Details ─────────────────────────────────────────────────
        t2 = QWidget()
        f2 = QFormLayout(t2)
        f2.setContentsMargins(16, 16, 16, 16)
        f2.setSpacing(10)
        f2.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f2.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._giver = QLineEdit(getattr(q, "quest_giver", "") if q else "")
        self._giver.setPlaceholderText("e.g. Lord Aldric, the Merchant Guild…")
        f2.addRow("Quest Giver", self._giver)

        self._location = QLineEdit(getattr(q, "location", "") if q else "")
        self._location.setPlaceholderText("e.g. The Ancient Ruins, City of Midvale…")
        f2.addRow("Location", self._location)

        # Dates side-by-side
        date_row = QHBoxLayout()
        date_row.setSpacing(8)
        self._date_started = QLineEdit(getattr(q, "date_started", "") if q else "")
        self._date_started.setPlaceholderText("YYYY-MM-DD")
        comp_lbl = QLabel("Completed")
        comp_lbl.setStyleSheet(f"color:{_FG_MID}; font-size:12px; font-weight:500;")
        self._date_completed = QLineEdit(getattr(q, "date_completed", "") if q else "")
        self._date_completed.setPlaceholderText("YYYY-MM-DD")
        date_row.addWidget(self._date_started, 1)
        date_row.addWidget(comp_lbl)
        date_row.addWidget(self._date_completed, 1)
        f2.addRow("Started", date_row)

        self._tags = QLineEdit(getattr(q, "tags", "") if q else "")
        self._tags.setPlaceholderText("Comma-separated: main, urgent, dragon…")
        f2.addRow("Tags", self._tags)

        # Linked session
        self._session_combo = QComboBox()
        self._session_combo.addItem("— None —", None)
        cur_sess_id = getattr(q, "linked_session_id", None) if q else None
        for sess in self._sessions:
            num   = getattr(sess, "session_number", "") or ""
            title = getattr(sess, "title", "") or f"Session {sess.id}"
            label = f"#{num}  {title}" if num else title
            self._session_combo.addItem(label, sess.id)
            if sess.id == cur_sess_id:
                self._session_combo.setCurrentIndex(
                    self._session_combo.count() - 1
                )
        f2.addRow("Linked Session", self._session_combo)

        tabs.addTab(t2, "Details")

        # ─ Tab 3: Notes ───────────────────────────────────────────────────
        t3 = QWidget()
        f3 = QFormLayout(t3)
        f3.setContentsMargins(16, 16, 16, 16)
        f3.setSpacing(10)
        f3.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f3.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._reward = QLineEdit(getattr(q, "reward", "") if q else "")
        self._reward.setPlaceholderText("e.g. 5,000 gp + Cloak of Elvenkind")
        f3.addRow("Reward", self._reward)

        self._notes = QTextEdit(getattr(q, "notes", "") if q else "")
        self._notes.setPlaceholderText("DM-only notes — secrets, contingencies, clues…")
        self._notes.setFixedHeight(130)
        f3.addRow("DM Notes", self._notes)

        tabs.addTab(t3, "Notes")

        # ── Footer buttons ────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _try_accept(self):
        if not self._title.text().strip():
            QMessageBox.warning(self, "Required", "Please enter a quest title.")
            return
        self.accept()


class _AssetEditDialog(QDialog):
    """Add or edit a campaign asset (file reference)."""

    def __init__(self, file_path: str = "", asset=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Asset" if asset is None else "Edit Asset")
        self.setMinimumWidth(480)
        self._asset = asset
        self._file_path = file_path or (getattr(asset, "file_path", "") if asset else "")
        self._build()

    def result_data(self) -> dict:
        return {
            "name":      self._name.text().strip(),
            "file_path": self._path_lbl.text().strip(),
            "category":  self._cat.currentData(),
            "tags":      self._tags.text().strip(),
            "notes":     self._notes.toPlainText().strip(),
        }

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # File path row
        path_row = QHBoxLayout()
        self._path_lbl = QLineEdit(self._file_path)
        self._path_lbl.setReadOnly(True)
        self._path_lbl.setPlaceholderText("No file selected")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self._path_lbl, 1)
        path_row.addWidget(browse_btn)
        form.addRow("File", path_row)

        # Name
        default_name = ""
        if self._asset:
            default_name = getattr(self._asset, "name", "")
        elif self._file_path:
            default_name = os.path.splitext(os.path.basename(self._file_path))[0]
        self._name = QLineEdit(default_name)
        self._name.setPlaceholderText("Display name for this asset")
        form.addRow("Name *", self._name)

        # Category
        self._cat = QComboBox()
        for cat_id, label, icon, _ in _ASSET_CATS:
            if cat_id == "all":
                continue
            self._cat.addItem(f"{icon}  {label}", userData=cat_id)
        # Pre-select
        current_cat = getattr(self._asset, "category", None) if self._asset else None
        if not current_cat and self._file_path:
            current_cat = _guess_asset_category(self._file_path)
        if current_cat:
            idx = self._cat.findData(current_cat)
            if idx >= 0:
                self._cat.setCurrentIndex(idx)
        form.addRow("Category", self._cat)

        # Tags
        self._tags = QLineEdit(getattr(self._asset, "tags", "") if self._asset else "")
        self._tags.setPlaceholderText("Comma-separated tags, e.g. forest, dungeon")
        form.addRow("Tags", self._tags)

        # Notes
        self._notes = QTextEdit(getattr(self._asset, "notes", "") if self._asset else "")
        self._notes.setPlaceholderText("Optional notes…")
        self._notes.setFixedHeight(70)
        form.addRow("Notes", self._notes)

        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "",
            "All Files (*);;"
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.svg);;"
            "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus);;"
            "Documents (*.pdf *.txt *.md *.docx *.rtf)",
        )
        if not path:
            return
        self._path_lbl.setText(path)
        # Auto-fill name if empty
        if not self._name.text().strip():
            self._name.setText(os.path.splitext(os.path.basename(path))[0])
        # Auto-select category
        cat = _guess_asset_category(path)
        idx = self._cat.findData(cat)
        if idx >= 0:
            self._cat.setCurrentIndex(idx)

    def _try_accept(self):
        if not self._path_lbl.text().strip():
            QMessageBox.warning(self, "Required", "Please select a file.")
            return
        if not self._name.text().strip():
            QMessageBox.warning(self, "Required", "Please enter a name.")
            return
        self.accept()


class _CompendiumEntryDialog(QDialog):
    def __init__(self, categories: list[str], default_cat: str = "",
                 entry=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Entry" if entry is None else "Edit Entry")
        self.setMinimumSize(540, 480)
        self._entry = entry
        self._cats  = categories
        self._default_cat = default_cat
        self._build()

    def result_data(self) -> dict:
        return {
            "category": self._cat.currentText().strip(),
            "title":    self._title.text().strip(),
            "content":  self._content.toPlainText().strip(),
            "tags":     self._tags.text().strip(),
            "source":   self._source.text().strip(),
        }

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)

        e = self._entry
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._cat = QComboBox()
        self._cat.setEditable(True)
        self._cat.setMinimumWidth(220)
        self._cat.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for c in self._cats:
            self._cat.addItem(c)
        if e:
            self._cat.setCurrentText(e.category)
        elif self._default_cat:
            self._cat.setCurrentText(self._default_cat)

        self._title   = QLineEdit(e.title if e else "")
        self._title.setPlaceholderText("Entry title…")
        self._tags    = QLineEdit(e.tags if e else "")
        self._tags.setPlaceholderText("comma, separated, tags")
        self._source  = QLineEdit(e.source if e else "")
        self._source.setPlaceholderText("PHB p.123, rulebook…")
        self._content = QTextEdit(e.content if e else "")
        self._content.setPlaceholderText("Description, stats, notes…")

        form.addRow("Category", self._cat)
        form.addRow("Title *",  self._title)
        form.addRow("Tags",     self._tags)
        form.addRow("Source",   self._source)
        lay.addLayout(form)

        content_lbl = QLabel("Content")
        content_lbl.setObjectName("subLabel")
        lay.addWidget(content_lbl)
        lay.addWidget(self._content, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _try_accept(self):
        if not self._title.text().strip():
            QMessageBox.warning(self, "Required", "Entry title is required.")
            return
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  _AddCombatantDialog
# ══════════════════════════════════════════════════════════════════════════════

class _AddCombatantDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Combatant")
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Goblin Archer")
        self._hp   = QSpinBox()
        self._hp.setRange(0, 9999)
        self._hp.setValue(10)
        self._max_hp = QSpinBox()
        self._max_hp.setRange(0, 9999)
        self._max_hp.setValue(10)
        self._ac   = QSpinBox()
        self._ac.setRange(0, 40)
        self._ac.setValue(10)
        self._kind = QComboBox()
        self._kind.addItems(["Enemy", "NPC", "Summon", "Custom"])
        # Sync max HP when HP changes
        self._hp.valueChanged.connect(
            lambda v: self._max_hp.setValue(v) if self._max_hp.value() < v else None
        )
        form.addRow("Name",   self._name)
        form.addRow("HP",     self._hp)
        form.addRow("Max HP", self._max_hp)
        form.addRow("AC",     self._ac)
        form.addRow("Type",   self._kind)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _accept(self):
        if not self._name.text().strip():
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name":   self._name.text().strip() or "Unknown",
            "hp":     self._hp.value(),
            "max_hp": self._max_hp.value(),
            "ac":     self._ac.value(),
            "kind":   self._kind.currentText(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  _InitiativeTracker
# ══════════════════════════════════════════════════════════════════════════════

class _InitiativeTracker(QWidget):
    """
    Full initiative / combat tracker.
    Columns: Init | Name | Type | HP | Max HP | AC | Conditions
    """
    COL_INIT  = 0
    COL_NAME  = 1
    COL_TYPE  = 2
    COL_HP    = 3
    COL_MAXHP = 4
    COL_AC    = 5
    COL_COND  = 6

    _TYPE_COLORS = {
        "Player Character": "#4f9eff",
        "PC":               "#4f9eff",
        "Enemy":            "#e05555",
        "NPC":              "#f9ca24",
        "Summon":           "#3dba6e",
    }

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self._svc     = service
        self._camp_id = None
        self._round   = 0
        self._cur_row = -1
        self._build()

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_camp_id(self, camp_id):
        self._camp_id = camp_id

    def load_from_encounter(self, enc_id: int):
        """Add each monster from the encounter as an enemy combatant."""
        if not enc_id:
            return
        try:
            monsters = self._svc.get_monsters(enc_id)
        except Exception:
            return
        for m in monsters:
            cnt  = m.count or 1
            name = m.monster_name or "Unknown"
            hp   = m.hp_override or 0
            for i in range(cnt):
                label = f"{name} #{i+1}" if cnt > 1 else name
                self._add_row(label, "Enemy", hp, hp, 0)

    def clear_combat(self):
        self._table.setRowCount(0)
        self._round   = 0
        self._cur_row = -1
        self._round_lbl.setText("Round —")
        self._active_banner.setVisible(False)

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        # ── Toolbar ───────────────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        load_btn = QPushButton("📋  Load Roster")
        load_btn.setObjectName("ghostBtn")
        load_btn.clicked.connect(self._load_roster)
        top.addWidget(load_btn)

        add_btn = QPushButton("＋  Add Combatant")
        add_btn.setObjectName("ghostBtn")
        add_btn.clicked.connect(self._add_custom)
        top.addWidget(add_btn)

        top.addStretch()

        roll_btn = QPushButton("🎲  Roll All")
        roll_btn.setObjectName("accentBtn")
        roll_btn.clicked.connect(self._roll_all)
        top.addWidget(roll_btn)

        sort_btn = QPushButton("Sort ↓")
        sort_btn.setObjectName("ghostBtn")
        sort_btn.clicked.connect(self._sort)
        top.addWidget(sort_btn)

        self._next_btn = QPushButton("Next Turn →")
        self._next_btn.setObjectName("accentBtn")
        self._next_btn.clicked.connect(self._next_turn)
        top.addWidget(self._next_btn)

        self._round_lbl = QLabel("Round —")
        self._round_lbl.setObjectName("roundLabel")
        top.addWidget(self._round_lbl)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("dangerBtn")
        clear_btn.clicked.connect(self._confirm_clear)
        top.addWidget(clear_btn)

        lay.addLayout(top)

        # ── Active turn banner ─────────────────────────────────────────────────
        self._active_banner = QLabel()
        self._active_banner.setObjectName("activeBanner")
        self._active_banner.setAlignment(Qt.AlignCenter)
        self._active_banner.setVisible(False)
        lay.addWidget(self._active_banner)

        # ── Combat table ───────────────────────────────────────────────────────
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["Init", "Name", "Type", "HP", "Max HP", "AC", "Conditions"])
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(self.COL_INIT,  QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_NAME,  QHeaderView.Stretch)
        h.setSectionResizeMode(self.COL_TYPE,  QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_HP,    QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_MAXHP, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_AC,    QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_COND,  QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self._table, 1)

        # ── Bottom bar ─────────────────────────────────────────────────────────
        btm = QHBoxLayout()
        rem_btn = QPushButton("✕  Remove Selected")
        rem_btn.setObjectName("dangerBtn")
        rem_btn.clicked.connect(self._remove_selected)
        btm.addWidget(rem_btn)
        btm.addStretch()
        hint = QLabel("Double-click Init / HP / Conditions to edit inline")
        hint.setObjectName("dimLabel")
        btm.addWidget(hint)
        lay.addLayout(btm)

    # ── Row management ─────────────────────────────────────────────────────────

    def _add_row(self, name: str, kind: str = "", hp: int = 10,
                 max_hp: int = 10, ac: int = 10):
        row = self._table.rowCount()
        self._table.insertRow(row)

        init_item = QTableWidgetItem("0")
        init_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, self.COL_INIT, init_item)

        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, self.COL_NAME, name_item)

        type_item = QTableWidgetItem(kind)
        type_item.setTextAlignment(Qt.AlignCenter)
        type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
        color = self._TYPE_COLORS.get(kind, "#a0a0a0")
        type_item.setForeground(QColor(color))
        self._table.setItem(row, self.COL_TYPE, type_item)

        for col, val in [(self.COL_HP, hp), (self.COL_MAXHP, max_hp), (self.COL_AC, ac)]:
            item = QTableWidgetItem(str(val) if val else "—")
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, col, item)

        self._table.setItem(row, self.COL_COND, QTableWidgetItem(""))

    # ── Toolbar actions ────────────────────────────────────────────────────────

    def _load_roster(self):
        if not self._camp_id:
            return
        try:
            chars = self._svc.get_characters(self._camp_id)
        except Exception:
            return
        for ch in chars:
            self._add_row(
                name=ch.name,
                kind=getattr(ch, "character_role", "PC") or "PC",
                hp=int(getattr(ch, "hit_points", 10) or 10),
                max_hp=int(getattr(ch, "max_hit_points", 10) or 10),
                ac=int(getattr(ch, "armor_class", 10) or 10),
            )

    def _add_custom(self):
        dlg = _AddCombatantDialog(self)
        if hasattr(dlg, "setStyleSheet") and self.styleSheet():
            dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            self._add_row(d["name"], d["kind"], d["hp"], d["max_hp"], d["ac"])

    def _roll_all(self):
        for row in range(self._table.rowCount()):
            roll = random.randint(1, 20)
            item = self._table.item(row, self.COL_INIT)
            if item:
                item.setText(str(roll))
        self._sort()

    def _sort(self):
        rows_data = []
        for row in range(self._table.rowCount()):
            def _t(col):
                item = self._table.item(row, col)
                return item.text() if item else ""
            try:
                init = int(_t(self.COL_INIT) or 0)
            except ValueError:
                init = 0
            rows_data.append({
                "init": init,
                "name": _t(self.COL_NAME),
                "kind": _t(self.COL_TYPE),
                "hp":   _t(self.COL_HP),
                "mhp":  _t(self.COL_MAXHP),
                "ac":   _t(self.COL_AC),
                "cond": _t(self.COL_COND),
            })
        rows_data.sort(key=lambda r: r["init"], reverse=True)
        self._table.setRowCount(0)
        for d in rows_data:
            def _i(v):
                try:
                    return int(v)
                except (ValueError, TypeError):
                    return 0
            self._add_row(d["name"], d["kind"], _i(d["hp"]), _i(d["mhp"]), _i(d["ac"]))
            r = self._table.rowCount() - 1
            self._table.item(r, self.COL_INIT).setText(str(d["init"]))
            self._table.item(r, self.COL_COND).setText(d["cond"])
        self._cur_row = -1
        self._active_banner.setVisible(False)

    def _next_turn(self):
        count = self._table.rowCount()
        if count == 0:
            return
        if self._round == 0:
            self._round   = 1
            self._cur_row = 0
        else:
            self._cur_row += 1
            if self._cur_row >= count:
                self._cur_row = 0
                self._round  += 1
        self._round_lbl.setText(f"Round {self._round}")
        self._table.setCurrentCell(self._cur_row, 0)
        self._table.scrollToItem(self._table.item(self._cur_row, 0))
        name = self._table.item(self._cur_row, self.COL_NAME)
        self._active_banner.setText(f"⚔  {name.text() if name else '?'}'s Turn  —  Round {self._round}")
        self._active_banner.setVisible(True)

    def _remove_selected(self):
        rows = sorted({i.row() for i in self._table.selectedItems()}, reverse=True)
        for row in rows:
            self._table.removeRow(row)
        if self._cur_row >= self._table.rowCount():
            self._cur_row = -1
        self._active_banner.setVisible(False)

    def _confirm_clear(self):
        reply = QMessageBox.question(
            self, "Clear Combat",
            "Remove all combatants and reset initiative order?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.clear_combat()


# ══════════════════════════════════════════════════════════════════════════════
#  _BookManagerDialog  —  toggle game data source books on / off
# ══════════════════════════════════════════════════════════════════════════════

class _BookManagerDialog(QDialog):
    """
    Shows all source books for the current game system as checkboxes.
    Unchecked books will be excluded from all game-data browser searches.
    """

    # Map plugin system_id → GameDataLoader system label (same as _GameDataBrowserDialog._SYS_MAP)
    _SYS_MAP = {
        "dnd5e":        "D&D 5e",
        "pathfinder2e": "Pathfinder 2e",
        "wh40k":        "Warhammer 40k",
        "aos":          "Age of Sigmar",
    }
    _SEARCHABLE_CATS = ["Spells", "Monsters", "Items", "Classes", "Species", "Backgrounds"]

    def __init__(self, system_id: str = "custom",
                 disabled_books: set | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Source Books")
        self.setMinimumSize(480, 520)
        self._system_id      = system_id
        self._disabled_books = set(disabled_books or set())
        self._build()
        self._load_books()

    def get_disabled_books(self) -> set[str]:
        """Return the set of book names that the user has turned OFF."""
        disabled: set[str] = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.checkState() == Qt.Unchecked:
                disabled.add(item.text())
        return disabled

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        # Header
        hdr = QLabel("Source Books")
        hdr.setObjectName("dialogTitle")
        root.addWidget(hdr)

        sys_label = self._SYS_MAP.get(self._system_id, "")
        sub = QLabel(
            f"System: {sys_label or 'Unknown'}  —  "
            "uncheck books to hide their entries in the game data browser."
        )
        sub.setObjectName("subLabel")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Search/filter bar
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter books…")
        self._filter.textChanged.connect(self._apply_filter)
        root.addWidget(self._filter)

        # Book list
        self._list = QListWidget()
        self._list.setObjectName("bookList")
        root.addWidget(self._list, 1)

        # Buttons row: Select All / Deselect All  +  OK / Cancel
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        all_btn = QPushButton("✓ Enable All")
        all_btn.setObjectName("ghostBtn")
        all_btn.clicked.connect(self._enable_all)
        none_btn = QPushButton("✗ Disable All")
        none_btn.setObjectName("ghostBtn")
        none_btn.clicked.connect(self._disable_all)
        self._count_lbl = QLabel()
        self._count_lbl.setObjectName("dimLabel")
        ok_btn = QPushButton("Apply")
        ok_btn.setObjectName("accentBtn")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._count_lbl)
        btn_row.addSpacing(8)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    def _load_books(self):
        if not _GAME_DATA_AVAILABLE:
            item = QListWidgetItem("Game data not available")
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            return

        system = self._SYS_MAP.get(self._system_id, "")
        if not system:
            item = QListWidgetItem("No book data for this game system")
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            return

        all_books: set[str] = set()
        for cat in self._SEARCHABLE_CATS:
            try:
                all_books.update(GameDataLoader.book_names(cat, system))
            except Exception:
                pass

        if not all_books:
            item = QListWidgetItem("No books found for this system")
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            return

        self._list.clear()
        for book in sorted(all_books, key=str.lower):
            item = QListWidgetItem(book)
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            state = Qt.Unchecked if book in self._disabled_books else Qt.Checked
            item.setCheckState(state)
            self._list.addItem(item)

        self._list.itemChanged.connect(self._update_count)
        self._update_count()

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item:
                item.setHidden(bool(text) and text not in item.text().lower())

    def _enable_all(self):
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and not item.isHidden():
                item.setCheckState(Qt.Checked)

    def _disable_all(self):
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and not item.isHidden():
                item.setCheckState(Qt.Unchecked)

    def _update_count(self):
        total    = self._list.count()
        disabled = sum(
            1 for i in range(total)
            if self._list.item(i)
            and self._list.item(i).checkState() == Qt.Unchecked
        )
        enabled = total - disabled
        self._count_lbl.setText(f"{enabled} / {total} enabled")


# ══════════════════════════════════════════════════════════════════════════════
#  _MonsterEditDialog  —  edit a single encounter monster entry
# ══════════════════════════════════════════════════════════════════════════════

class _MonsterEditDialog(QDialog):
    """Edit an existing EncounterMonster row (name, count, CR, HP override, notes)."""

    def __init__(self, monster, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Monster")
        self.setMinimumWidth(400)
        self._build(monster)

    def _build(self, m):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        title = QLabel("Edit Monster Entry")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setSpacing(10)
        form.setContentsMargins(0, 0, 0, 0)

        self._name_edit = QLineEdit(m.monster_name or "")
        form.addRow("Name:", self._name_edit)

        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 999)
        self._count_spin.setValue(m.count or 1)
        form.addRow("Count:", self._count_spin)

        self._cr_edit = QLineEdit(m.cr or "")
        self._cr_edit.setPlaceholderText("e.g. 1/4  2  10")
        form.addRow("CR / Level:", self._cr_edit)

        self._hp_spin = QSpinBox()
        self._hp_spin.setRange(0, 9999)
        self._hp_spin.setSpecialValueText("Default (use stat block)")
        self._hp_spin.setValue(m.hp_override or 0)
        form.addRow("HP Override:", self._hp_spin)

        self._notes_edit = QLineEdit(m.notes or "")
        self._notes_edit.setPlaceholderText("Optional notes…")
        form.addRow("Notes:", self._notes_edit)

        root.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        # Style the default (Save) button with accent colour
        save_btn = bb.button(QDialogButtonBox.Save)
        if save_btn:
            save_btn.setDefault(True)
            save_btn.setObjectName("accentBtn")
        root.addWidget(bb)

    def get_values(self) -> dict:
        hp = self._hp_spin.value()
        return {
            "name":        self._name_edit.text().strip(),
            "count":       self._count_spin.value(),
            "cr":          self._cr_edit.text().strip() or "0",
            "hp_override": hp if hp > 0 else None,
            "notes":       self._notes_edit.text().strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  _CustomMonsterEditDialog  —  create / edit a custom monster template
# ══════════════════════════════════════════════════════════════════════════════

_MONSTER_SIZES  = ["Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan", ""]
_MONSTER_TYPES  = [
    "Aberration", "Beast", "Celestial", "Construct", "Dragon",
    "Elemental", "Fey", "Fiend", "Giant", "Humanoid", "Monstrosity",
    "Ooze", "Plant", "Undead", "Other", ""
]


class _CustomMonsterEditDialog(QDialog):
    """Create or edit a custom monster template."""

    def __init__(self, monster=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Custom Monster" if monster else "New Custom Monster")
        self.setMinimumWidth(520)
        self.setMinimumHeight(600)
        self._build(monster)

    def _build(self, m):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # ── Tab 1: Core stats ─────────────────────────────────────────────────
        core_w = QWidget()
        core_lay = QVBoxLayout(core_w)
        core_lay.setContentsMargins(12, 12, 12, 12)
        core_lay.setSpacing(10)

        form1 = QFormLayout()
        form1.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form1.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form1.setSpacing(9)

        self._name_edit = QLineEdit(m.name if m else "")
        self._name_edit.setPlaceholderText("Monster name…")
        form1.addRow("Name:", self._name_edit)

        self._cr_edit = QLineEdit(m.cr if m else "1")
        self._cr_edit.setPlaceholderText("e.g. 1/4  2  10")
        form1.addRow("CR / Level:", self._cr_edit)

        self._hp_spin = QSpinBox()
        self._hp_spin.setRange(1, 9999)
        self._hp_spin.setValue(m.hp if m else 10)
        form1.addRow("Hit Points:", self._hp_spin)

        self._ac_spin = QSpinBox()
        self._ac_spin.setRange(1, 30)
        self._ac_spin.setValue(m.ac if m else 12)
        form1.addRow("Armour Class:", self._ac_spin)

        self._init_spin = QSpinBox()
        self._init_spin.setRange(-10, 20)
        self._init_spin.setValue(m.initiative_bonus if m else 0)
        form1.addRow("Initiative Bonus:", self._init_spin)

        self._type_combo = QComboBox()
        self._type_combo.addItems(_MONSTER_TYPES)
        self._type_combo.setEditable(True)
        if m and m.monster_type in _MONSTER_TYPES:
            self._type_combo.setCurrentText(m.monster_type)
        elif m:
            self._type_combo.setEditText(m.monster_type)
        form1.addRow("Type:", self._type_combo)

        self._size_combo = QComboBox()
        self._size_combo.addItems(_MONSTER_SIZES)
        self._size_combo.setEditable(True)
        if m and m.size:
            self._size_combo.setCurrentText(m.size)
        form1.addRow("Size:", self._size_combo)

        self._speed_edit = QLineEdit(m.speed if m else "")
        self._speed_edit.setPlaceholderText("e.g. 30 ft., fly 60 ft.")
        form1.addRow("Speed:", self._speed_edit)

        core_lay.addLayout(form1)

        # Ability scores grid
        ab_lbl = QLabel("Ability Scores")
        ab_lbl.setObjectName("subLabel")
        core_lay.addWidget(ab_lbl)

        ab_grid = QGridLayout()
        ab_grid.setSpacing(8)
        ab_names   = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
        ab_fields  = ["str_", "dex", "con", "int_", "wis", "cha"]
        ab_vals    = [
            m.str_ if m else 10, m.dex if m else 10, m.con if m else 10,
            m.int_ if m else 10, m.wis if m else 10, m.cha if m else 10,
        ]
        self._ab_spins = {}
        for i, (label, field, val) in enumerate(zip(ab_names, ab_fields, ab_vals)):
            col = i * 2
            ab_grid.addWidget(QLabel(label), 0, col, Qt.AlignCenter)
            spin = QSpinBox()
            spin.setRange(1, 30)
            spin.setValue(val)
            spin.setFixedWidth(58)
            ab_grid.addWidget(spin, 1, col, Qt.AlignCenter)
            self._ab_spins[field] = spin
        core_lay.addLayout(ab_grid)
        core_lay.addStretch()

        tabs.addTab(core_w, "Core Stats")

        # ── Tab 2: Attacks & Traits ───────────────────────────────────────────
        at_w = QWidget()
        at_lay = QVBoxLayout(at_w)
        at_lay.setContentsMargins(12, 12, 12, 12)
        at_lay.setSpacing(8)

        atk_lbl = QLabel("Attacks / Actions")
        atk_lbl.setObjectName("subLabel")
        at_lay.addWidget(atk_lbl)
        self._attacks_edit = QTextEdit()
        self._attacks_edit.setObjectName("journalEditor")
        self._attacks_edit.setPlaceholderText(
            "Describe attacks and actions — one per line or free text…")
        self._attacks_edit.setPlainText(m.attacks if m else "")
        at_lay.addWidget(self._attacks_edit, 1)

        tr_lbl = QLabel("Traits / Special Abilities")
        tr_lbl.setObjectName("subLabel")
        at_lay.addWidget(tr_lbl)
        self._traits_edit = QTextEdit()
        self._traits_edit.setObjectName("journalEditor")
        self._traits_edit.setPlaceholderText(
            "Passive traits, resistances, immunities, legendary actions…")
        self._traits_edit.setPlainText(m.traits if m else "")
        at_lay.addWidget(self._traits_edit, 1)

        tabs.addTab(at_w, "Attacks & Traits")

        # ── Tab 3: Notes ──────────────────────────────────────────────────────
        notes_w = QWidget()
        notes_lay = QVBoxLayout(notes_w)
        notes_lay.setContentsMargins(12, 12, 12, 12)
        self._notes_edit = QTextEdit()
        self._notes_edit.setObjectName("journalEditor")
        self._notes_edit.setPlaceholderText("DM notes, lore, tactics…")
        self._notes_edit.setPlainText(m.notes if m else "")
        notes_lay.addWidget(self._notes_edit)
        tabs.addTab(notes_w, "Notes")

        # ── Button box ────────────────────────────────────────────────────────
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        save_btn = bb.button(QDialogButtonBox.Save)
        if save_btn:
            save_btn.setDefault(True)
            save_btn.setObjectName("accentBtn")
        root.addWidget(bb)

    def get_values(self) -> dict:
        return {
            "name":             self._name_edit.text().strip(),
            "cr":               self._cr_edit.text().strip() or "1",
            "hp":               self._hp_spin.value(),
            "ac":               self._ac_spin.value(),
            "initiative_bonus": self._init_spin.value(),
            "monster_type":     self._type_combo.currentText().strip(),
            "size":             self._size_combo.currentText().strip(),
            "speed":            self._speed_edit.text().strip(),
            "str_":             self._ab_spins["str_"].value(),
            "dex":              self._ab_spins["dex"].value(),
            "con":              self._ab_spins["con"].value(),
            "int_":             self._ab_spins["int_"].value(),
            "wis":              self._ab_spins["wis"].value(),
            "cha":              self._ab_spins["cha"].value(),
            "attacks":          self._attacks_edit.toPlainText().strip(),
            "traits":           self._traits_edit.toPlainText().strip(),
            "notes":            self._notes_edit.toPlainText().strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  _CustomMonsterManagerDialog  —  library of per-campaign custom monsters
# ══════════════════════════════════════════════════════════════════════════════

class _CustomMonsterManagerDialog(QDialog):
    """List, create, edit, delete custom monster templates.
    If encounter_id is provided, also allows adding them to an encounter."""

    def __init__(self, service, campaign_id: int,
                 encounter_id=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Monster Library")
        self.setMinimumSize(820, 560)
        self._svc          = service
        self._campaign_id  = campaign_id
        self._encounter_id = encounter_id
        self._monsters: list = []
        self._build()
        self._load()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Custom Monster Library")
        title.setObjectName("pageTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        new_btn = QPushButton("＋  New Monster")
        new_btn.setObjectName("accentBtn")
        new_btn.clicked.connect(self._on_new)
        hdr.addWidget(new_btn)
        root.addLayout(hdr)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search by name, type…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._load)
        root.addWidget(self._search)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left — list
        left = QFrame()
        left.setObjectName("panelFrame")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        self._list = QListWidget()
        self._list.setObjectName("encList")
        self._list.currentRowChanged.connect(self._on_select)
        self._list.itemDoubleClicked.connect(lambda _: self._on_edit())
        ll.addWidget(self._list)
        splitter.addWidget(left)

        # Right — detail
        right = QFrame()
        right.setObjectName("panelFrame")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(6)

        self._detail_name = QLabel()
        self._detail_name.setObjectName("cardName")
        self._detail_name.setWordWrap(True)
        rl.addWidget(self._detail_name)

        self._detail_meta = QLabel()
        self._detail_meta.setObjectName("dimLabel")
        self._detail_meta.setWordWrap(True)
        rl.addWidget(self._detail_meta)

        self._detail_body = QTextEdit()
        self._detail_body.setReadOnly(True)
        self._detail_body.setObjectName("journalEditor")
        rl.addWidget(self._detail_body, 1)

        splitter.addWidget(right)
        splitter.setSizes([300, 480])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        # Bottom toolbar
        bot = QHBoxLayout()
        bot.setSpacing(8)

        self._edit_btn = QPushButton("✏  Edit")
        self._edit_btn.setObjectName("ghostBtn")
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        bot.addWidget(self._edit_btn)

        self._del_btn = QPushButton("✕  Delete")
        self._del_btn.setObjectName("dangerBtn")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._on_delete)
        bot.addWidget(self._del_btn)

        bot.addStretch()

        if self._encounter_id is not None:
            self._count_spin = QSpinBox()
            self._count_spin.setRange(1, 99)
            self._count_spin.setValue(1)
            self._count_spin.setFixedWidth(56)
            self._count_spin.setPrefix("× ")
            bot.addWidget(self._count_spin)

            self._add_enc_btn = QPushButton("⚔  Add to Encounter")
            self._add_enc_btn.setObjectName("accentBtn")
            self._add_enc_btn.setEnabled(False)
            self._add_enc_btn.clicked.connect(self._on_add_to_encounter)
            bot.addWidget(self._add_enc_btn)
            bot.addSpacing(8)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bot.addWidget(close_btn)

        root.addLayout(bot)

    # ── Data ─────────────────────────────────────────────────────────────────

    def _load(self):
        q = self._search.text().strip() if hasattr(self, "_search") else ""
        self._monsters = self._svc.get_custom_monsters(self._campaign_id, q)
        self._list.clear()
        for m in self._monsters:
            parts = [m.name]
            if m.cr:     parts.append(f"CR {m.cr}")
            if m.monster_type: parts.append(m.monster_type)
            item = QListWidgetItem("  ·  ".join(parts))
            item.setData(Qt.UserRole, m.id)
            self._list.addItem(item)
        self._update_buttons()
        if not self._monsters:
            self._detail_name.setText("No custom monsters yet.")
            self._detail_meta.clear()
            self._detail_body.clear()

    def _on_select(self, row):
        self._update_buttons(row)
        if row < 0 or row >= len(self._monsters):
            self._detail_name.clear()
            self._detail_meta.clear()
            self._detail_body.clear()
            return
        m = self._monsters[row]
        self._detail_name.setText(m.name)
        meta_parts = []
        if m.cr:             meta_parts.append(f"CR {m.cr}")
        if m.hp:             meta_parts.append(f"HP {m.hp}")
        if m.ac:             meta_parts.append(f"AC {m.ac}")
        if m.monster_type:   meta_parts.append(m.monster_type)
        if m.size:           meta_parts.append(m.size)
        if m.speed:          meta_parts.append(f"Speed: {m.speed}")
        if m.initiative_bonus:
            meta_parts.append(f"Initiative: +{m.initiative_bonus}" if m.initiative_bonus >= 0
                               else f"Initiative: {m.initiative_bonus}")
        self._detail_meta.setText("   ·   ".join(meta_parts))

        lines = []
        ab_labels = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
        ab_vals   = [m.str_, m.dex, m.con, m.int_, m.wis, m.cha]
        ab_strs   = [f"{l} {v}" for l, v in zip(ab_labels, ab_vals)]
        lines.append("  ".join(ab_strs))
        if m.attacks:
            lines.append("\n── Attacks & Actions ──\n" + m.attacks)
        if m.traits:
            lines.append("\n── Traits ──\n" + m.traits)
        if m.notes:
            lines.append("\n── Notes ──\n" + m.notes)
        self._detail_body.setPlainText("\n".join(lines))

    def _update_buttons(self, row=None):
        if row is None:
            row = self._list.currentRow()
        has_sel = 0 <= row < len(self._monsters)
        self._edit_btn.setEnabled(has_sel)
        self._del_btn.setEnabled(has_sel)
        if self._encounter_id is not None and hasattr(self, "_add_enc_btn"):
            self._add_enc_btn.setEnabled(has_sel)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_new(self):
        dlg = _CustomMonsterEditDialog(parent=self)
        dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        if not vals["name"]:
            return
        self._svc.add_custom_monster(self._campaign_id, **vals)
        self._load()

    def _on_edit(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._monsters):
            return
        m = self._monsters[row]
        dlg = _CustomMonsterEditDialog(m, parent=self)
        dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        if not vals["name"]:
            return
        self._svc.update_custom_monster(m.id, **vals)
        self._load()

    def _on_delete(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._monsters):
            return
        m = self._monsters[row]
        reply = QMessageBox.question(
            self, "Delete Monster",
            f"Delete \"{m.name}\" from the custom library?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._svc.delete_custom_monster(m.id)
        self._load()

    def _on_add_to_encounter(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._monsters) or self._encounter_id is None:
            return
        m     = self._monsters[row]
        count = self._count_spin.value() if hasattr(self, "_count_spin") else 1
        try:
            self._svc.add_monster(
                self._encounter_id,
                name=m.name,
                count=count,
                cr=m.cr or "0",
                hp_override=m.hp,
                notes=f"AC {m.ac}" + (f", {m.notes}" if m.notes else ""),
            )
            # Provide brief feedback without closing the dialog
            self._add_enc_btn.setText("✓  Added!")
            QTimer.singleShot(1200, lambda: self._add_enc_btn.setText("⚔  Add to Encounter"))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  _MonsterFromBookDialog  —  focused monster browser for encounter building
# ══════════════════════════════════════════════════════════════════════════════

class _MonsterFromBookDialog(QDialog):
    """Searches game-data books for monsters and adds them to an encounter.
    Reuses GameDataLoader; only shows the Monsters tab with an 'Add' action."""

    _SYS_MAP = {
        "dnd5e":        "D&D 5e",
        "pathfinder2e": "Pathfinder 2e",
        "wh40k":        "Warhammer 40k",
        "aos":          "Age of Sigmar",
    }

    def __init__(self, service, campaign_id: int, encounter_id: int,
                 system_id: str = "custom",
                 disabled_books: set | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browse Monsters — Add to Encounter")
        self.setMinimumSize(860, 580)
        self._svc            = service
        self._campaign_id    = campaign_id
        self._encounter_id   = encounter_id
        self._system_id      = system_id
        self._disabled_books = disabled_books or set()
        self._results: list[dict] = []
        self._build()
        QTimer.singleShot(0, self._init_systems)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Title
        hdr = QHBoxLayout()
        title = QLabel("Add Monsters from Books")
        title.setObjectName("pageTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        root.addLayout(hdr)

        # System + book filter row
        sys_row = QHBoxLayout()
        sys_row.setSpacing(8)
        sys_row.addWidget(QLabel("System:"))
        self._sys_combo = QComboBox()
        self._sys_combo.setMinimumWidth(160)
        self._sys_combo.currentTextChanged.connect(self._on_system_changed)
        sys_row.addWidget(self._sys_combo)

        sys_row.addWidget(QLabel("Book:"))
        self._book_combo = QComboBox()
        self._book_combo.setMinimumWidth(180)
        self._book_combo.addItem("All Books")
        self._book_combo.currentTextChanged.connect(self._do_search)
        sys_row.addWidget(self._book_combo)

        sys_row.addWidget(QLabel("CR:"))
        self._cr_combo = QComboBox()
        self._cr_combo.setMinimumWidth(80)
        self._cr_combo.addItem("All CR")
        self._cr_combo.currentTextChanged.connect(self._do_search)
        sys_row.addWidget(self._cr_combo)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search monsters…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._do_search)
        sys_row.addWidget(self._search, 2)

        self._count_lbl = QLabel()
        self._count_lbl.setObjectName("dimLabel")
        sys_row.addWidget(self._count_lbl)
        root.addLayout(sys_row)

        # Splitter: list | detail
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.currentRowChanged.connect(self._on_row_selected)
        splitter.addWidget(self._list)

        detail = QFrame()
        detail.setObjectName("panelFrame")
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(12, 10, 12, 10)
        dl.setSpacing(6)
        self._d_title = QLabel()
        self._d_title.setObjectName("cardName")
        self._d_title.setWordWrap(True)
        self._d_meta = QLabel()
        self._d_meta.setObjectName("dimLabel")
        self._d_meta.setWordWrap(True)
        self._d_body = QTextEdit()
        self._d_body.setReadOnly(True)
        dl.addWidget(self._d_title)
        dl.addWidget(self._d_meta)
        dl.addWidget(self._d_body, 1)
        splitter.addWidget(detail)
        splitter.setSizes([380, 440])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        # Bottom toolbar
        bot = QHBoxLayout()
        bot.setSpacing(8)
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("dimLabel")
        bot.addWidget(self._status_lbl)
        bot.addStretch()

        bot.addWidget(QLabel("Count:"))
        self._add_count = QSpinBox()
        self._add_count.setRange(1, 99)
        self._add_count.setValue(1)
        self._add_count.setFixedWidth(60)
        bot.addWidget(self._add_count)

        self._add_btn = QPushButton("⚔  Add Selected to Encounter")
        self._add_btn.setObjectName("accentBtn")
        self._add_btn.clicked.connect(self._on_add_selected)
        bot.addWidget(self._add_btn)
        bot.addSpacing(8)

        close_btn = QPushButton("Done")
        close_btn.clicked.connect(self.accept)
        bot.addWidget(close_btn)
        root.addLayout(bot)

    # ── System / search ───────────────────────────────────────────────────────

    def _init_systems(self):
        if not _GAME_DATA_AVAILABLE:
            self._status_lbl.setText("Game data not available.")
            return
        systems = GameDataLoader.available_systems() or []
        self._sys_combo.blockSignals(True)
        self._sys_combo.addItems(systems)
        self._sys_combo.blockSignals(False)
        target = self._SYS_MAP.get(self._system_id, "")
        if target in systems:
            self._sys_combo.setCurrentText(target)
        elif systems:
            self._sys_combo.setCurrentIndex(0)
        self._on_system_changed()

    def _on_system_changed(self):
        system = self._sys_combo.currentText()
        if not system or not _GAME_DATA_AVAILABLE:
            return
        # Refresh CR combo
        self._cr_combo.blockSignals(True)
        self._cr_combo.clear()
        self._cr_combo.addItem("All CR")
        try:
            self._cr_combo.addItems(GameDataLoader.challenge_ratings(system))
        except Exception:
            pass
        self._cr_combo.blockSignals(False)
        # Reset book combo
        self._book_combo.blockSignals(True)
        self._book_combo.clear()
        self._book_combo.addItem("All Books")
        self._book_combo.blockSignals(False)
        self._do_search()

    def _do_search(self):
        if not _GAME_DATA_AVAILABLE:
            return
        system = self._sys_combo.currentText()
        query  = self._search.text().strip()
        cr     = self._cr_combo.currentText()
        cr     = None if cr == "All CR" else cr
        book   = self._book_combo.currentText()
        book   = None if book == "All Books" else book
        try:
            results = GameDataLoader.search_monsters(
                query, system=system, cr=cr, book=book)
        except Exception as e:
            self._count_lbl.setText(f"Error: {e}")
            return
        # Filter disabled books
        if self._disabled_books:
            results = [r for r in results
                       if r.get("book", "") not in self._disabled_books]
        self._results = results
        # Lazily populate book combo
        if self._book_combo.count() == 1 and results:
            try:
                books = GameDataLoader.book_names("Monsters", system)
                self._book_combo.blockSignals(True)
                self._book_combo.addItems(books)
                self._book_combo.blockSignals(False)
            except Exception:
                pass
        self._list.clear()
        for entry in results:
            name  = entry.get("name") or "(unnamed)"
            props = entry.get("properties", {})
            cr_v  = props.get("Challenge Rating", "")
            detail = f"  ·  CR {cr_v}" if cr_v else ""
            item = QListWidgetItem(name + detail)
            item.setData(Qt.UserRole, name)
            self._list.addItem(item)
        self._count_lbl.setText(f"{len(results):,} results")

    def _on_row_selected(self, row: int):
        if row < 0 or row >= len(self._results):
            self._d_title.clear(); self._d_meta.clear(); self._d_body.clear()
            return
        entry = self._results[row]
        self._d_title.setText(entry.get("name", "(unnamed)"))
        props = entry.get("properties", {}) or {}
        parts = []
        for k in ("Challenge Rating", "Type", "Size", "Alignment",
                  "Hit Points", "Armor Class", "Speed"):
            v = props.get(k)
            if v: parts.append(f"{k}: {v}")
        book = entry.get("book", "")
        if book: parts.append(f"Source: {book}")
        self._d_meta.setText("   ·   ".join(parts))
        self._d_body.setPlainText(_format_entry(entry))

    # ── Add to encounter ──────────────────────────────────────────────────────

    def _on_add_selected(self):
        rows = sorted({self._list.row(i) for i in self._list.selectedItems()})
        if not rows:
            self._status_lbl.setText("Select monsters to add.")
            return
        count = self._add_count.value()
        added = 0
        for row in rows:
            if row >= len(self._results):
                continue
            entry = self._results[row]
            name  = entry.get("name") or "(unnamed)"
            props = entry.get("properties", {}) or {}
            cr    = props.get("Challenge Rating", "") or "0"
            try:
                self._svc.add_monster(
                    self._encounter_id,
                    name=name, count=count, cr=cr,
                )
                added += 1
            except Exception:
                pass
        noun = "monster" if added == 1 else "monsters"
        self._status_lbl.setText(f"✓  Added {added} {noun} to encounter")


# ══════════════════════════════════════════════════════════════════════════════
#  _GameDataBrowserDialog  —  full knowledge-base browser + compendium import
# ══════════════════════════════════════════════════════════════════════════════

class _GameDataBrowserDialog(QDialog):
    """
    Tabbed game data library (Spells / Monsters / Items / Classes / Species /
    Backgrounds / Data Files).  Each tab has type-specific filters, a search
    box, a result list and a detail panel.  Selected entries can be imported
    directly into the campaign compendium in one click.
    """

    # ── Tab definitions ────────────────────────────────────────────────────────
    # (name, default_compendium_category, filter_type)
    # filter_type: "school" | "cr" | "rarity" | "none"
    _TABS = [
        ("Spells",      "Spells",      "school"),
        ("Monsters",    "Monsters",    "cr"),
        ("Items",       "Items",       "rarity"),
        ("Classes",     "Classes",     "none"),
        ("Species",     "Species",     "none"),
        ("Backgrounds", "Backgrounds", "none"),
        ("Data Files",  "",            "file"),
    ]

    # Map our system_id → GameDataLoader system label
    _SYS_MAP = {
        "dnd5e":        "D&D 5e",
        "pathfinder2e": "Pathfinder 2e",
        "wh40k":        "Warhammer 40k",
        "aos":          "Age of Sigmar",
    }

    def __init__(self, service, campaign_id: int,
                 system_id: str = "custom",
                 disabled_books: set | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Game Data Library")
        self.setMinimumSize(920, 640)
        self._svc            = service
        self._campaign_id    = campaign_id
        self._system_id      = system_id
        self._disabled_books: set[str] = disabled_books or set()
        # per-tab result lists  {tab_name: [entry_dict, ...]}
        self._results: dict[str, list[dict]] = {t[0]: [] for t in self._TABS}
        self._build()
        QTimer.singleShot(0, self._init_systems)

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        # ── System selector row ───────────────────────────────────────────────
        sys_row = QHBoxLayout()
        sys_row.setSpacing(8)
        lbl = QLabel("System:")
        lbl.setObjectName("subLabel")
        self._sys_combo = QComboBox()
        self._sys_combo.setMinimumWidth(180)
        self._sys_combo.currentTextChanged.connect(self._on_system_changed)
        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setToolTip("Refresh installed systems")
        refresh_btn.clicked.connect(self._refresh_systems)
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("dimLabel")
        sys_row.addWidget(lbl)
        sys_row.addWidget(self._sys_combo)
        sys_row.addWidget(refresh_btn)
        sys_row.addStretch()
        sys_row.addWidget(self._status_lbl)
        root.addLayout(sys_row)

        # ── Category tabs ─────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tab_widgets: dict[str, QWidget] = {}
        for tab_name, _, filter_type in self._TABS:
            w = self._build_tab(tab_name, filter_type)
            self._tabs.addTab(w, tab_name)
            self._tab_widgets[tab_name] = w
        self._tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self._tabs, 1)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bot = QHBoxLayout()
        bot.setSpacing(8)
        cat_lbl = QLabel("Import into:")
        cat_lbl.setObjectName("subLabel")
        self._import_cat = QComboBox()
        self._import_cat.setEditable(True)
        self._import_cat.setMinimumWidth(160)
        sys_obj = SYSTEMS.get(self._system_id)
        if sys_obj:
            self._import_cat.addItems(sys_obj.compendium_cats)
        self._import_btn = QPushButton("⬇  Import Selected")
        self._import_btn.setObjectName("accentBtn")
        self._import_btn.clicked.connect(self._import_selected)
        self._import_all_btn = QPushButton("Import All")
        self._import_all_btn.setObjectName("ghostBtn")
        self._import_all_btn.clicked.connect(self._import_all)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bot.addWidget(cat_lbl)
        bot.addWidget(self._import_cat)
        bot.addSpacing(8)
        bot.addWidget(self._import_btn)
        bot.addWidget(self._import_all_btn)
        bot.addStretch()
        bot.addWidget(close_btn)
        root.addLayout(bot)

    def _build_tab(self, tab_name: str, filter_type: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(6)

        # ── Filter row ────────────────────────────────────────────────────────
        frow = QHBoxLayout()
        frow.setSpacing(6)

        search = QLineEdit()
        search.setObjectName(f"search_{tab_name}")
        search.setPlaceholderText(f"Search {tab_name.lower()}…")
        search.textChanged.connect(lambda q, n=tab_name: self._do_search(n))
        frow.addWidget(search, 2)

        if filter_type == "file":
            # Data Files tab: file picker instead of type filter
            file_cb = QComboBox()
            file_cb.setObjectName("file_combo")
            file_cb.setMinimumWidth(200)
            file_cb.currentTextChanged.connect(lambda _: self._do_search("Data Files"))
            frow.addWidget(file_cb, 2)
        elif filter_type == "school":
            school_cb = QComboBox()
            school_cb.setObjectName("school_combo")
            school_cb.addItem("All Schools")
            school_cb.currentTextChanged.connect(lambda _: self._do_search(tab_name))
            frow.addWidget(school_cb)
        elif filter_type == "cr":
            cr_cb = QComboBox()
            cr_cb.setObjectName("cr_combo")
            cr_cb.addItem("All CR")
            cr_cb.currentTextChanged.connect(lambda _: self._do_search(tab_name))
            frow.addWidget(cr_cb)
        elif filter_type == "rarity":
            rar_cb = QComboBox()
            rar_cb.setObjectName("rarity_combo")
            rar_cb.addItem("All Rarities")
            rar_cb.currentTextChanged.connect(lambda _: self._do_search(tab_name))
            frow.addWidget(rar_cb)

        if filter_type != "file":
            book_cb = QComboBox()
            book_cb.setObjectName("book_combo")
            book_cb.setMinimumWidth(180)
            book_cb.addItem("All Books")
            book_cb.currentTextChanged.connect(lambda _: self._do_search(tab_name))
            frow.addWidget(book_cb, 2)

        count_lbl = QLabel()
        count_lbl.setObjectName(f"count_{tab_name}")
        count_lbl.setObjectName("dimLabel")
        frow.addWidget(count_lbl)
        lay.addLayout(frow)

        # ── Splitter: list | detail ───────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        lst = QListWidget()
        lst.setObjectName(f"list_{tab_name}")
        lst.setSelectionMode(QListWidget.ExtendedSelection)
        lst.currentRowChanged.connect(lambda row, n=tab_name: self._on_row_selected(n, row))
        splitter.addWidget(lst)

        detail = QFrame()
        detail.setObjectName("panelFrame")
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(12, 10, 12, 10)
        dl.setSpacing(6)
        d_title = QLabel()
        d_title.setObjectName("cardName")
        d_title.setWordWrap(True)
        d_meta = QLabel()
        d_meta.setObjectName("dimLabel")
        d_meta.setWordWrap(True)
        d_body = QTextEdit()
        d_body.setReadOnly(True)
        d_body.setObjectName(f"detail_body_{tab_name}")
        dl.addWidget(d_title)
        dl.addWidget(d_meta)
        dl.addWidget(d_body, 1)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        lay.addWidget(splitter, 1)

        return w

    # ── System init / refresh ──────────────────────────────────────────────────

    def _init_systems(self):
        if not _GAME_DATA_AVAILABLE:
            self._status_lbl.setText("game_system_data/ not found")
            return
        self._refresh_systems()

    def _refresh_systems(self):
        systems = GameDataLoader.available_systems() or []
        prev = self._sys_combo.currentText()
        self._sys_combo.blockSignals(True)
        self._sys_combo.clear()
        self._sys_combo.addItems(systems)
        self._sys_combo.blockSignals(False)
        target = self._SYS_MAP.get(self._system_id, "")
        if target in systems:
            self._sys_combo.setCurrentText(target)
        elif prev in systems:
            self._sys_combo.setCurrentText(prev)
        self._on_system_changed()

    def _on_system_changed(self):
        system = self._sys_combo.currentText()
        if not system:
            return

        # Refresh school/cr/rarity combos
        for tab_name, _, ftype in self._TABS:
            w = self._tab_widgets.get(tab_name)
            if not w:
                continue
            if ftype == "school":
                cb = w.findChild(QComboBox, "school_combo")
                if cb:
                    cb.blockSignals(True)
                    cb.clear()
                    cb.addItem("All Schools")
                    try: cb.addItems(GameDataLoader.spell_schools(system))
                    except Exception: pass
                    cb.blockSignals(False)
            elif ftype == "cr":
                cb = w.findChild(QComboBox, "cr_combo")
                if cb:
                    cb.blockSignals(True)
                    cb.clear()
                    cb.addItem("All CR")
                    try: cb.addItems(GameDataLoader.challenge_ratings(system))
                    except Exception: pass
                    cb.blockSignals(False)
            elif ftype == "rarity":
                cb = w.findChild(QComboBox, "rarity_combo")
                if cb:
                    cb.blockSignals(True)
                    cb.clear()
                    cb.addItem("All Rarities")
                    try: cb.addItems(GameDataLoader.item_rarities(system))
                    except Exception: pass
                    cb.blockSignals(False)
            elif ftype == "file":
                cb = w.findChild(QComboBox, "file_combo")
                if cb:
                    cb.blockSignals(True)
                    cb.clear()
                    try: cb.addItems(GameDataLoader.list_data_files(system))
                    except Exception: pass
                    cb.blockSignals(False)
            # Reset book combos
            book_cb = w.findChild(QComboBox, "book_combo")
            if book_cb:
                book_cb.blockSignals(True)
                book_cb.clear()
                book_cb.addItem("All Books")
                book_cb.blockSignals(False)

        # Trigger search on the currently visible tab
        current = self._tabs.tabText(self._tabs.currentIndex())
        self._do_search(current)

    def _on_tab_changed(self, index: int):
        name = self._tabs.tabText(index)
        # Auto-suggest import category
        for tab_name, default_cat, _ in self._TABS:
            if tab_name == name and default_cat:
                idx = self._import_cat.findText(default_cat, Qt.MatchFixedString)
                if idx >= 0:
                    self._import_cat.setCurrentIndex(idx)
                else:
                    self._import_cat.setEditText(default_cat)
                break
        self._do_search(name)

    # ── Search ─────────────────────────────────────────────────────────────────

    def _do_search(self, tab_name: str):
        if not _GAME_DATA_AVAILABLE:
            return
        w = self._tab_widgets.get(tab_name)
        if not w:
            return

        system  = self._sys_combo.currentText()
        search  = w.findChild(QLineEdit, f"search_{tab_name}")
        query   = search.text().strip() if search else ""
        count_l = w.findChild(QLabel, f"count_{tab_name}")
        lst     = w.findChild(QListWidget, f"list_{tab_name}")

        book_cb = w.findChild(QComboBox, "book_combo")
        book    = book_cb.currentText() if book_cb and book_cb.currentText() != "All Books" else None

        try:
            if tab_name == "Spells":
                cb = w.findChild(QComboBox, "school_combo")
                school = cb.currentText() if cb and cb.currentText() != "All Schools" else None
                results = GameDataLoader.search_spells(query, system=system, school=school, book=book)
            elif tab_name == "Monsters":
                cb = w.findChild(QComboBox, "cr_combo")
                cr = cb.currentText() if cb and cb.currentText() != "All CR" else None
                results = GameDataLoader.search_monsters(query, system=system, cr=cr, book=book)
            elif tab_name == "Items":
                cb = w.findChild(QComboBox, "rarity_combo")
                rarity = cb.currentText() if cb and cb.currentText() != "All Rarities" else None
                results = GameDataLoader.search_items(query, system=system, rarity=rarity, book=book)
            elif tab_name == "Classes":
                results = GameDataLoader.search_classes(query, system=system, book=book)
            elif tab_name == "Species":
                results = GameDataLoader.search_species(query, system=system, book=book)
            elif tab_name == "Backgrounds":
                results = GameDataLoader.search_backgrounds(query, system=system, book=book)
            elif tab_name == "Data Files":
                file_cb  = w.findChild(QComboBox, "file_combo")
                filename = file_cb.currentText() if file_cb else ""
                results  = GameDataLoader.search_file_entries(system, filename, query) if filename else []
            else:
                results = []
        except Exception as e:
            if count_l: count_l.setText(f"Error: {e}")
            return

        # Post-filter disabled books
        if self._disabled_books and tab_name != "Data Files":
            results = [
                r for r in results
                if r.get("book", "") not in self._disabled_books
            ]

        self._results[tab_name] = results

        # Lazily populate book combo on first successful load
        if book_cb and book_cb.count() == 1 and results:
            try:
                books = GameDataLoader.book_names(tab_name, system)
                book_cb.blockSignals(True)
                book_cb.addItems(books)
                book_cb.blockSignals(False)
            except Exception:
                pass

        if lst:
            lst.clear()
            for entry in results:
                name = entry.get("name") or "(unnamed)"
                props = entry.get("properties", {})
                # Show brief secondary detail in the list item
                detail = ""
                if tab_name == "Spells":
                    lvl = props.get("Level", "")
                    sch = props.get("School", "")
                    detail = f"  ·  Lv {lvl} {sch}".strip(" ·") if (lvl or sch) else ""
                elif tab_name == "Monsters":
                    cr = props.get("Challenge Rating", "")
                    detail = f"  ·  CR {cr}" if cr else ""
                elif tab_name == "Items":
                    rar = props.get("Item Rarity", "") or props.get("Rarity", "")
                    detail = f"  ·  {rar}" if rar else ""
                item = QListWidgetItem(name + detail)
                item.setData(Qt.UserRole, name)  # store clean name
                lst.addItem(item)

        if count_l:
            count_l.setText(f"{len(results):,} results")

    def _on_row_selected(self, tab_name: str, row: int):
        results = self._results.get(tab_name, [])
        if row < 0 or row >= len(results):
            return
        entry = results[row]
        w = self._tab_widgets.get(tab_name)
        if not w:
            return

        # Find the detail widgets by object name
        d_title = w.findChild(QLabel, "cardName")
        d_meta  = w.findChild(QLabel, "dimLabel")
        d_body  = w.findChild(QTextEdit, f"detail_body_{tab_name}")

        if d_title:
            d_title.setText(entry.get("name", "(unnamed)"))
        if d_meta:
            props  = entry.get("properties", {}) or {}
            parts  = []
            if tab_name == "Spells":
                for k in ("Level", "School", "Casting Time", "Range",
                          "Components", "Duration", "Classes"):
                    v = props.get(k)
                    if v: parts.append(f"{k}: {v}")
            elif tab_name == "Monsters":
                for k in ("Challenge Rating", "Type", "Size", "Alignment",
                          "Hit Points", "Armor Class", "Speed"):
                    v = props.get(k)
                    if v: parts.append(f"{k}: {v}")
            elif tab_name == "Items":
                for k in ("Item Type", "Item Rarity", "Requires Attunement",
                          "Weight", "Cost"):
                    v = props.get(k)
                    if v: parts.append(f"{k}: {v}")
            book = entry.get("book", "")
            if book: parts.append(f"Source: {book}")
            d_meta.setText("   ·   ".join(parts))
        if d_body:
            d_body.setPlainText(_format_entry(entry))

    # ── Import ──────────────────────────────────────────────────────────────────

    def _current_tab_name(self) -> str:
        return self._tabs.tabText(self._tabs.currentIndex())

    def _import_selected(self):
        tab   = self._current_tab_name()
        w     = self._tab_widgets.get(tab)
        lst   = w.findChild(QListWidget, f"list_{tab}") if w else None
        if not lst:
            return
        rows = sorted({lst.row(i) for i in lst.selectedItems()})
        if not rows:
            self._status_lbl.setText("Select entries to import.")
            return
        self._do_import(tab, rows)

    def _import_all(self):
        tab     = self._current_tab_name()
        results = self._results.get(tab, [])
        if not results:
            return
        if QMessageBox.question(
            self, "Import All",
            f"Import all {len(results):,} {tab.lower()} into the compendium?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._do_import(tab, list(range(len(results))))

    def _do_import(self, tab_name: str, rows: list[int]):
        results = self._results.get(tab_name, [])
        cat     = self._import_cat.currentText().strip() or tab_name
        imported = 0
        for row in rows:
            if row >= len(results):
                continue
            entry   = results[row]
            title   = entry.get("name") or "(unnamed)"
            content = _format_entry(entry)
            tags    = _entry_tags(entry)
            source  = entry.get("book", "") or entry.get("source", "") or ""
            try:
                self._svc.add_compendium_entry(
                    self._campaign_id, cat, title, content, tags, source)
                imported += 1
            except Exception:
                pass
        noun = "entry" if imported == 1 else "entries"
        self._status_lbl.setText(f"✓ {imported} {noun} added to \"{cat}\"")


# ── Entry formatting helpers ───────────────────────────────────────────────────

def _format_entry(entry: dict) -> str:
    """Render a game data dict as readable plain text."""
    lines = []
    skip  = {"name", "book", "source"}
    # Description / flavour first
    for key in ("description", "flavortext", "flavor", "text", "effect", "summary"):
        val = entry.get(key)
        if val:
            lines.append(str(val))
            lines.append("")
            break
    # Properties block
    props = entry.get("properties", {})
    if isinstance(props, dict):
        for k, v in props.items():
            if v not in (None, "", [], {}):
                lines.append(f"{k}: {v}")
    # Remaining top-level fields
    for k, v in entry.items():
        if k in skip or k in ("description", "flavortext", "flavor", "text",
                               "effect", "summary", "properties"):
            continue
        if v not in (None, "", [], {}):
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def _entry_tags(entry: dict) -> str:
    parts = []
    for key in ("faction", "type", "category", "school", "keywords", "traits", "subtypes"):
        val = entry.get(key)
        if val:
            if isinstance(val, list):
                parts.extend(str(v) for v in val)
            else:
                parts.append(str(val))
    return ", ".join(parts[:6])


# ══════════════════════════════════════════════════════════════════════════════

class _SimpleInputDialog(QDialog):
    def __init__(self, title: str, prompt: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel(prompt))
        self._input = QLineEdit()
        lay.addWidget(self._input)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def value(self) -> str:
        return self._input.text().strip()


# ══════════════════════════════════════════════════════════════════════════════
#  Dice utility
# ══════════════════════════════════════════════════════════════════════════════

def _roll_dice(expression: str) -> tuple[int, str]:
    """
    Parse and roll a dice expression.
    Supports: NdS, NdSkHM (keep highest), NdSkLM (keep lowest), modifiers +/-N.
    Examples: 2d6, d20, 4d6kh3, 2d8+5, d100-10
    Returns (total, detail_string).
    """
    expr = expression.strip().lower().replace(" ", "")
    total   = 0
    detail_parts = []

    # Split by + and - preserving sign
    tokens = re.split(r'(?=[+-])', expr)
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        sign = 1
        if token.startswith('-'):
            sign = -1
            token = token[1:]
        elif token.startswith('+'):
            token = token[1:]

        # Dice token: NdS or NdSkHM or NdSkLM
        m = re.match(r'^(\d*)d(\d+)(?:k([hl])(\d+))?$', token)
        if m:
            n_str, s_str, keep_type, keep_n_str = m.groups()
            n      = int(n_str) if n_str else 1
            sides  = int(s_str)
            rolls  = [random.randint(1, sides) for _ in range(n)]
            kept   = list(rolls)
            if keep_type and keep_n_str:
                k = int(keep_n_str)
                if keep_type == 'h':
                    kept = sorted(rolls, reverse=True)[:k]
                else:
                    kept = sorted(rolls)[:k]
            roll_total = sum(kept)
            total += sign * roll_total
            kept_str = "+".join(str(r) for r in kept)
            if keep_type:
                detail_parts.append(
                    f"[{', '.join(str(r) for r in rolls)} → {kept_str}]")
            else:
                detail_parts.append(f"[{kept_str}]")
        else:
            # Plain number modifier
            try:
                val = int(token)
                total += sign * val
                detail_parts.append(f"{'+' if sign > 0 else '-'}{val}")
            except ValueError:
                raise ValueError(f"Cannot parse token: {token!r}")

    return total, "  ".join(detail_parts)
