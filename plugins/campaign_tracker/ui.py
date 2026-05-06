"""
Campaign Tracker UI

Main widget for the Campaign Tracker plugin.

Structure:
  CampaignTrackerUI         — outer QWidget, two top-level tabs
    [Campaigns tab]
      QStackedWidget
        CampaignListView    — card grid of all campaigns
        CampaignDetailView  — tabs: Overview | Players | Roster | Battle Log | Chronicle | Assets
    [Dice Roller tab]
      DiceRollerWidget      — dice buttons, expression input, result display, history
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, QAbstractTableModel, QModelIndex, QSignalBlocker
from PySide6.QtGui import QColor, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTableView,
    QGroupBox, QMessageBox, QTabWidget, QSpinBox,
    QTextEdit, QListWidget, QListWidgetItem,
    QDialog, QDialogButtonBox, QSizePolicy, QFrame,
    QScrollArea, QFileDialog, QSplitter, QStackedWidget,
    QProgressBar,
)

from .models import (
    Campaign, CampaignPlayer, Character, Battle,
    JournalEntry, CampaignAsset, CharacterSpell, InventoryItem,
    Encounter, EncounterMonster,
    GAME_SYSTEMS, CAMPAIGN_STATUSES, CHARACTER_ROLES, CHARACTER_ROLE_COLORS,
    CHARACTER_STATUSES, BATTLE_OUTCOMES, OUTCOME_COLORS, ASSET_TYPES,
    PLAYER_ROLES, STAT_STYLES, DND_STATS, WARGAME_40K, WARGAME_AOS,
    ValidationError,
)
from plugins.shared_widgets import PhotoCropDialog, focal_pixmap
from .game_data import GameDataLoader


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _cover_pixmap(pix, w: int, h: int):
    """Scale-to-fill then center-crop — like CSS object-fit: cover."""
    if pix.isNull():
        return pix
    scaled = pix.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    if scaled.width() > w or scaled.height() > h:
        x = (scaled.width() - w) // 2
        y = (scaled.height() - h) // 2
        return scaled.copy(x, y, w, h)
    return scaled


def _hline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    return f

def _vline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine); f.setFixedWidth(1)
    return f

def _field(label: str, widget: QWidget) -> QVBoxLayout:
    col = QVBoxLayout(); col.setSpacing(4)
    lbl = QLabel(label); lbl.setObjectName("fieldLabel")
    col.addWidget(lbl); col.addWidget(widget)
    return col

def _stat_chip(label: str, value: str, color: str = "#0078d4") -> QFrame:
    chip = QFrame()
    chip.setFrameShape(QFrame.StyledPanel)
    chip.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    lay = QVBoxLayout(chip)
    lay.setContentsMargins(14, 8, 14, 8)
    lay.setSpacing(2)
    v = QLabel(str(value))
    v.setAlignment(Qt.AlignCenter)
    v.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {color};")
    l = QLabel(label)
    l.setAlignment(Qt.AlignCenter)
    l.setObjectName("fieldLabel")
    lay.addWidget(v)
    lay.addWidget(l)
    return chip

def _outcome_badge(outcome: str) -> QLabel:
    color = OUTCOME_COLORS.get(outcome, "#808080")
    lbl = QLabel(outcome)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(
        f"background-color: {color}22; color: {color}; border: 1px solid {color}55;"
        f" border-radius: 4px; padding: 2px 8px; font-weight: 600; font-size: 11px;"
    )
    lbl.setFixedHeight(22)
    return lbl

def _role_badge(role: str) -> QLabel:
    color = CHARACTER_ROLE_COLORS.get(role, "#686868")
    lbl = QLabel(role)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(
        f"background-color: {color}22; color: {color}; border: 1px solid {color}55;"
        f" border-radius: 4px; padding: 2px 8px; font-size: 11px;"
    )
    lbl.setFixedHeight(20)
    return lbl


# ── Dice parser ────────────────────────────────────────────────────────────────

def _parse_and_roll(expression: str) -> tuple[int, str]:
    """
    Parse a dice expression and return (total, detail_string).
    Supported:
      d20, 2d6, 3d8+4, 2d6-1
      adv / dis  (d20 with advantage/disadvantage)
      4d6dl      (4d6 drop lowest — D&D stat gen)
    """
    expr = expression.lower().strip()

    # Advantage
    if re.match(r"(adv|advantage|d20\s*adv)", expr):
        r1, r2 = random.randint(1, 20), random.randint(1, 20)
        total = max(r1, r2)
        return total, f"Advantage [{r1}, {r2}] → {total}"

    # Disadvantage
    if re.match(r"(dis|disadvantage|d20\s*dis)", expr):
        r1, r2 = random.randint(1, 20), random.randint(1, 20)
        total = min(r1, r2)
        return total, f"Disadvantage [{r1}, {r2}] → {total}"

    # 4d6 drop lowest
    if re.match(r"4d6\s*(dl|drop|drop\s*lowest)", expr):
        rolls = [random.randint(1, 6) for _ in range(4)]
        dropped = min(rolls)
        kept = sorted(rolls, reverse=True)[:3]
        total = sum(kept)
        return total, f"4d6dl {sorted(rolls, reverse=True)} → drop {dropped} → {kept} = {total}"

    # Standard NdX±M
    m = re.fullmatch(r"(\d*)d(\d+)([+\-]\d+)?", expr.replace(" ", ""))
    if m:
        n     = int(m.group(1)) if m.group(1) else 1
        sides = int(m.group(2))
        mod   = int(m.group(3)) if m.group(3) else 0
        n = min(max(n, 1), 100)
        sides = min(max(sides, 2), 10000)
        rolls  = [random.randint(1, sides) for _ in range(n)]
        total  = sum(rolls) + mod
        detail = f"{n}d{sides}: {rolls}" if n > 1 else f"d{sides}: {rolls[0]}"
        if mod > 0:  detail += f" +{mod}"
        elif mod < 0: detail += f" {mod}"
        detail += f" = {total}"
        return total, detail

    raise ValueError(f"Cannot parse: '{expression}'")


# ── Shared non-blocking feedback helpers ──────────────────────────────────────

def _show_toast(widget: QWidget, msg: str, obj_name: str = "toastSuccess") -> None:
    """Floating toast anchored to *widget* — auto-dismisses after 2.5 s."""
    bar = QLabel(msg, widget)
    bar.setObjectName(obj_name)
    bar.adjustSize()
    bar.move(widget.width() // 2 - bar.width() // 2, widget.height() - 60)
    bar.show()
    bar.raise_()
    QTimer.singleShot(2500, bar.deleteLater)


def _show_inline_status(lbl: QLabel, text: str, obj_name: str, duration_ms: int = 4000) -> None:
    """Set a QLabel's objectName + text, then clear after *duration_ms*."""
    lbl.setObjectName(obj_name)
    lbl.style().unpolish(lbl)
    lbl.style().polish(lbl)
    lbl.setText(text)
    QTimer.singleShot(duration_ms, lambda: lbl.setText(""))


# ── Image viewer ───────────────────────────────────────────────────────────────

class _ImageViewerDialog(QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Photo Viewer")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignCenter)
        screen  = QApplication.primaryScreen().availableGeometry()
        max_w, max_h = int(screen.width() * 0.85), int(screen.height() * 0.80)
        pix = QPixmap(path)
        if not pix.isNull():
            scaled = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_lbl.setPixmap(scaled)
            self.resize(scaled.width() + 24, scaled.height() + 60)
        else:
            img_lbl.setText("Could not load image.")
            self.resize(400, 300)
        lay.addWidget(img_lbl)
        close = QPushButton("Close"); close.setFixedWidth(100)
        close.clicked.connect(self.accept)
        lay.addWidget(close, alignment=Qt.AlignCenter)


# ── Character Gallery Dialog ───────────────────────────────────────────────────

class CharacterGalleryDialog(QDialog):
    THUMB_W = 200; THUMB_H = 160; COLS = 4

    def __init__(self, context, character, parent=None):
        super().__init__(parent)
        self._ctx  = context
        self._char = character
        self._svc  = context.services.try_get("campaign_service")
        self.setWindowTitle(f"{character.name} — Photos")
        self.setMinimumSize(640, 460)
        self.resize(860, 580)
        self._build_ui()
        self._load()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        t = QLabel(self._char.name)
        t.setStyleSheet("font-size: 20px; font-weight: 700; color: #f0f0f0;")
        hdr.addWidget(t); hdr.addStretch()
        hdr.addWidget(_role_badge(self._char.character_role))
        lay.addLayout(hdr)
        lay.addWidget(_hline())

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._grid_w = QWidget()
        self._grid   = QGridLayout(self._grid_w)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._grid_w)
        lay.addWidget(scroll, stretch=1)

        btm = QHBoxLayout()
        self._cnt = QLabel(""); self._cnt.setStyleSheet("color: #606060; font-size: 12px;")
        btm.addWidget(self._cnt); btm.addStretch()
        add = QPushButton("+ Add Photos"); add.setProperty("class", "primary")
        add.clicked.connect(self._add_photos)
        btm.addWidget(add)
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        btm.addWidget(close)
        lay.addLayout(btm)

    def _load(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        images = self._svc.get_character_images(self._char.id) if self._svc else []
        if not images:
            lbl = QLabel('No photos yet — click  "+ Add Photos"  to get started.')
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #606060; padding: 50px;")
            self._grid.addWidget(lbl, 0, 0, 1, self.COLS)
            self._cnt.setText(""); return

        self._cnt.setText(f"{len(images)} photo{'s' if len(images)!=1 else ''}")
        for i, img in enumerate(images):
            self._grid.addWidget(self._make_card(img), i//self.COLS, i%self.COLS)

    def _make_card(self, img: dict) -> QFrame:
        path       = img.get("image_path", "")
        img_id     = img["id"]
        is_primary = (path == self._char.primary_image_path)
        zoom   = float(img.get("zoom",    1.0))
        fx     = float(img.get("focal_x", 0.5))
        fy     = float(img.get("focal_y", 0.5))

        card = QFrame(); card.setFrameShape(QFrame.StyledPanel)
        card.setFixedWidth(self.THUMB_W + 4)
        lay = QVBoxLayout(card); lay.setContentsMargins(2, 2, 2, 6); lay.setSpacing(4)

        thumb = QLabel()
        thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setCursor(Qt.PointingHandCursor)
        if path and os.path.isfile(path):
            pix = focal_pixmap(QPixmap(path), self.THUMB_W, self.THUMB_H, zoom, fx, fy)
            thumb.setPixmap(pix)
            thumb.setStyleSheet(
                "background:#111; border-radius:4px;"
                + ("border: 2px solid #f0a020;" if is_primary else "border: 2px solid transparent;")
            )
            thumb.mousePressEvent = lambda _e, p=path: _ImageViewerDialog(p, self).exec()
        else:
            thumb.setText("No image"); thumb.setStyleSheet("color: #505050;")
        lay.addWidget(thumb)

        if is_primary:
            pl = QLabel("★ Primary"); pl.setAlignment(Qt.AlignCenter)
            pl.setStyleSheet("color: #f0a020; font-size: 11px; font-weight: 600;")
            lay.addWidget(pl)

        btns = QHBoxLayout(); btns.setSpacing(4)
        if not is_primary:
            set_btn = QPushButton("Set Primary"); set_btn.setFixedHeight(24)
            set_btn.setStyleSheet("font-size: 11px; padding: 0 6px;")
            set_btn.clicked.connect(
                lambda _=False, p=path, z=zoom, fx_=fx, fy_=fy:
                    self._set_primary_with_crop(p, z, fx_, fy_)
            )
            btns.addWidget(set_btn)

        crop_btn = QPushButton("Crop…"); crop_btn.setFixedHeight(24)
        crop_btn.setStyleSheet("font-size: 11px; padding: 0 6px;")
        crop_btn.clicked.connect(
            lambda _=False, p=path, i=img_id, z=zoom, fx_=fx, fy_=fy:
                self._open_crop(p, i, z, fx_, fy_)
        )
        btns.addWidget(crop_btn)

        rm_btn = QPushButton("Remove"); rm_btn.setFixedHeight(24)
        rm_btn.setStyleSheet("font-size: 11px; padding: 0 6px;")
        rm_btn.setProperty("class", "danger")
        rm_btn.clicked.connect(lambda _=False, i=img_id: self._remove(i))
        btns.addWidget(rm_btn)

        lay.addLayout(btns)
        return card

    def _add_photos(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Photos", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not files or not self._svc: return
        existing = {img["image_path"] for img in self._svc.get_character_images(self._char.id)}
        for f in files:
            if f not in existing:
                self._svc.add_character_image(self._char.id, f)
        # If first photo added, open crop dialog for it
        new_files = [f for f in files if f not in existing]
        if new_files and not self._char.primary_image_path:
            self._load()
            imgs = self._svc.get_character_images(self._char.id)
            first = next((i for i in imgs if i["image_path"] == new_files[0]), None)
            if first:
                self._open_crop(new_files[0], first["id"], 1.0, 0.5, 0.5,
                                set_primary_on_accept=True)
        else:
            self._load()

    def _open_crop(self, path: str, img_id: int,
                   zoom: float, fx: float, fy: float,
                   set_primary_on_accept: bool = False):
        """Open the PhotoCropDialog for this image; persist crop on OK."""
        if not path or not os.path.isfile(path):
            return
        dlg = PhotoCropDialog(path, self.THUMB_W, self.THUMB_H,
                              zoom=zoom, fx=fx, fy=fy, parent=self)
        if dlg.exec() and self._svc:
            new_zoom, new_fx, new_fy = dlg.result()
            self._svc.update_character_image_crop(img_id, new_zoom, new_fx, new_fy)
            if set_primary_on_accept:
                self._svc.set_primary_character_image(
                    self._char.id, path, new_zoom, new_fx, new_fy)
                self._char.primary_image_path = path
        self._load()

    def _set_primary_with_crop(self, path: str, zoom: float, fx: float, fy: float):
        """Promote to primary and open crop dialog so user can set the focal point."""
        if not path or not os.path.isfile(path):
            return
        dlg = PhotoCropDialog(path, self.THUMB_W, self.THUMB_H,
                              zoom=zoom, fx=fx, fy=fy, parent=self)
        if dlg.exec() and self._svc:
            new_zoom, new_fx, new_fy = dlg.result()
            self._svc.set_primary_character_image(
                self._char.id, path, new_zoom, new_fx, new_fy)
            self._char.primary_image_path = path
        self._load()

    def _set_primary(self, path: str):
        """Quick set-primary without crop (kept for compat)."""
        if self._svc:
            self._svc.set_primary_character_image(self._char.id, path)
            self._char.primary_image_path = path
        self._load()

    def _remove(self, img_id: int):
        if self._svc: self._svc.delete_character_image(img_id)
        self._load()


# ── Battle Gallery Dialog ──────────────────────────────────────────────────────

class BattleGalleryDialog(QDialog):
    THUMB_W = 200; THUMB_H = 160; COLS = 4

    def __init__(self, context, battle, parent=None):
        super().__init__(parent)
        self._ctx    = context
        self._battle = battle
        self._svc    = context.services.try_get("campaign_service")
        self.setWindowTitle(f"#{battle.session_number} {battle.title} — Photos")
        self.setMinimumSize(640, 460)
        self.resize(860, 560)
        self._build_ui()
        self._load()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18,14,18,14); lay.setSpacing(10)
        hdr = QHBoxLayout()
        t = QLabel(f"#{self._battle.session_number}  {self._battle.title}")
        t.setStyleSheet("font-size: 18px; font-weight: 700; color: #f0f0f0;")
        hdr.addWidget(t); hdr.addStretch()
        hdr.addWidget(_outcome_badge(self._battle.outcome))
        lay.addLayout(hdr); lay.addWidget(_hline())

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._grid_w = QWidget()
        self._grid   = QGridLayout(self._grid_w)
        self._grid.setSpacing(12); self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._grid_w)
        lay.addWidget(scroll, stretch=1)

        btm = QHBoxLayout()
        self._cnt = QLabel(""); self._cnt.setStyleSheet("color: #606060; font-size: 12px;")
        btm.addWidget(self._cnt); btm.addStretch()
        add = QPushButton("+ Add Photos"); add.setProperty("class", "primary")
        add.clicked.connect(self._add_photos)
        btm.addWidget(add)
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        btm.addWidget(close)
        lay.addLayout(btm)

    def _load(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        images = self._svc.get_battle_images(self._battle.id) if self._svc else []
        if not images:
            lbl = QLabel('No photos yet.'); lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #606060; padding: 50px;")
            self._grid.addWidget(lbl, 0, 0, 1, self.COLS)
            self._cnt.setText(""); return
        self._cnt.setText(f"{len(images)} photo{'s' if len(images)!=1 else ''}")
        for i, img in enumerate(images):
            self._grid.addWidget(self._make_card(img), i//self.COLS, i%self.COLS)

    def _make_card(self, img: dict) -> QFrame:
        path     = img.get("image_path", "")
        img_id   = img["id"]
        is_primary = (path == getattr(self._battle, "primary_image_path", None))
        zoom = float(img.get("zoom",    1.0))
        fx   = float(img.get("focal_x", 0.5))
        fy   = float(img.get("focal_y", 0.5))

        card = QFrame(); card.setFrameShape(QFrame.StyledPanel)
        card.setFixedWidth(self.THUMB_W + 4)
        lay = QVBoxLayout(card); lay.setContentsMargins(2, 2, 2, 6); lay.setSpacing(4)
        thumb = QLabel(); thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        thumb.setAlignment(Qt.AlignCenter); thumb.setCursor(Qt.PointingHandCursor)
        if path and os.path.isfile(path):
            pix = focal_pixmap(QPixmap(path), self.THUMB_W, self.THUMB_H, zoom, fx, fy)
            thumb.setPixmap(pix)
            thumb.setStyleSheet(
                "background:#111; border-radius:4px;"
                + ("border: 2px solid #f0a020;" if is_primary else "border: 2px solid transparent;")
            )
            thumb.mousePressEvent = lambda _e, p=path: _ImageViewerDialog(p, self).exec()
        else:
            thumb.setText("No image"); thumb.setStyleSheet("color: #505050;")
        lay.addWidget(thumb)

        if is_primary:
            pl = QLabel("★ Primary"); pl.setAlignment(Qt.AlignCenter)
            pl.setStyleSheet("color: #f0a020; font-size: 11px; font-weight: 600;")
            lay.addWidget(pl)

        btns = QHBoxLayout(); btns.setSpacing(4)
        if not is_primary:
            set_btn = QPushButton("Set Primary"); set_btn.setFixedHeight(24)
            set_btn.setStyleSheet("font-size: 11px; padding: 0 6px;")
            set_btn.clicked.connect(
                lambda _=False, p=path, z=zoom, fx_=fx, fy_=fy:
                    self._set_primary_with_crop(p, z, fx_, fy_)
            )
            btns.addWidget(set_btn)

        crop_btn = QPushButton("Crop…"); crop_btn.setFixedHeight(24)
        crop_btn.setStyleSheet("font-size: 11px; padding: 0 6px;")
        crop_btn.clicked.connect(
            lambda _=False, p=path, i=img_id, z=zoom, fx_=fx, fy_=fy:
                self._open_crop(p, i, z, fx_, fy_)
        )
        btns.addWidget(crop_btn)

        rm = QPushButton("Remove"); rm.setFixedHeight(24)
        rm.setStyleSheet("font-size: 11px; padding: 0 6px;")
        rm.setProperty("class", "danger")
        rm.clicked.connect(lambda _=False, i=img_id: self._remove(i))
        btns.addWidget(rm)

        lay.addLayout(btns)
        return card

    def _add_photos(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Photos", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not files or not self._svc: return
        existing = {img["image_path"] for img in self._svc.get_battle_images(self._battle.id)}
        new_files = [f for f in files if f not in existing]
        for f in new_files:
            self._svc.add_battle_image(self._battle.id, f)
        if new_files and not getattr(self._battle, "primary_image_path", None):
            self._load()
            imgs = self._svc.get_battle_images(self._battle.id)
            first = next((i for i in imgs if i["image_path"] == new_files[0]), None)
            if first:
                self._open_crop(new_files[0], first["id"], 1.0, 0.5, 0.5,
                                set_primary_on_accept=True)
        else:
            self._load()

    def _open_crop(self, path: str, img_id: int,
                   zoom: float, fx: float, fy: float,
                   set_primary_on_accept: bool = False):
        if not path or not os.path.isfile(path):
            return
        dlg = PhotoCropDialog(path, self.THUMB_W, self.THUMB_H,
                              zoom=zoom, fx=fx, fy=fy, parent=self)
        if dlg.exec() and self._svc:
            new_zoom, new_fx, new_fy = dlg.result()
            self._svc.update_battle_image_crop(img_id, new_zoom, new_fx, new_fy)
            if set_primary_on_accept:
                self._svc.set_primary_battle_image(
                    self._battle.id, path, new_zoom, new_fx, new_fy)
                self._battle.primary_image_path = path
        self._load()

    def _set_primary_with_crop(self, path: str, zoom: float, fx: float, fy: float):
        if not path or not os.path.isfile(path):
            return
        dlg = PhotoCropDialog(path, self.THUMB_W, self.THUMB_H,
                              zoom=zoom, fx=fx, fy=fy, parent=self)
        if dlg.exec() and self._svc:
            new_zoom, new_fx, new_fy = dlg.result()
            self._svc.set_primary_battle_image(
                self._battle.id, path, new_zoom, new_fx, new_fy)
            self._battle.primary_image_path = path
        self._load()

    def _remove(self, img_id: int):
        if self._svc: self._svc.delete_battle_image(img_id)
        self._load()


# ── Character edit dialog ──────────────────────────────────────────────────────

class CharacterDialog(QDialog):
    def __init__(self, context, campaign, character=None, parent=None):
        super().__init__(parent)
        self._ctx       = context
        self._campaign  = campaign
        self._character = character
        self._svc       = context.services.try_get("campaign_service")
        self._stat_widgets: dict[str, QLineEdit] = {}
        self.setWindowTitle("Edit Character" if character else "Add Character")
        self.setMinimumSize(580, 520)
        self.resize(680, 640)
        self._build_ui()
        if character:
            self._populate(character)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 14); lay.setSpacing(10)

        # ── Scroll area for the form ──────────────────────────────────────────
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        form_w = QWidget()
        fl = QVBoxLayout(form_w); fl.setSpacing(12)
        scroll.setWidget(form_w)
        lay.addWidget(scroll, stretch=1)

        # ── Identity ──────────────────────────────────────────────────────────
        id_box = QGroupBox("Identity")
        ib = QGridLayout(id_box); ib.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Character name…")
        ib.addLayout(_field("Name *", self._name_edit), 0, 0, 1, 2)

        self._role_combo = QComboBox(); self._role_combo.addItems(CHARACTER_ROLES)
        ib.addLayout(_field("Role", self._role_combo), 1, 0)

        self._status_combo = QComboBox(); self._status_combo.addItems(CHARACTER_STATUSES)
        ib.addLayout(_field("Status", self._status_combo), 1, 1)

        self._class_edit = QLineEdit(); self._class_edit.setPlaceholderText("e.g. Fighter, Ranger, Skaven Warlord…")
        ib.addLayout(_field("Class / Type", self._class_edit), 2, 0)

        self._race_edit = QLineEdit(); self._race_edit.setPlaceholderText("e.g. Human, Elf, Space Marine…")
        ib.addLayout(_field("Race / Faction", self._race_edit), 2, 1)

        self._level_spin = QSpinBox(); self._level_spin.setRange(0, 30)
        self._level_spin.setSpecialValueText("—")
        ib.addLayout(_field("Level", self._level_spin), 3, 0)

        # Player link
        self._player_combo = QComboBox()
        self._player_combo.addItem("— No Player —", None)
        players = self._svc.get_players(self._campaign.id) if self._svc else []
        for p in players:
            self._player_combo.addItem(f"{p.player_name} ({p.role})", p.id)
        ib.addLayout(_field("Controlled by", self._player_combo), 3, 1)

        fl.addWidget(id_box)

        # ── Combat stats ──────────────────────────────────────────────────────
        cs_box = QGroupBox("Combat")
        cs = QHBoxLayout(cs_box); cs.setSpacing(10)

        self._hp_spin = QSpinBox(); self._hp_spin.setRange(0, 9999)
        cs.addLayout(_field("Current HP", self._hp_spin))

        self._max_hp_spin = QSpinBox(); self._max_hp_spin.setRange(0, 9999)
        cs.addLayout(_field("Max HP", self._max_hp_spin))

        self._ac_spin = QSpinBox(); self._ac_spin.setRange(0, 99)
        cs.addLayout(_field("AC / Save", self._ac_spin))

        fl.addWidget(cs_box)

        # ── Stat block ────────────────────────────────────────────────────────
        sb_box = QGroupBox("Stat Block")
        sb = QVBoxLayout(sb_box); sb.setSpacing(8)

        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Style:"))
        self._style_combo = QComboBox(); self._style_combo.addItems(STAT_STYLES)
        self._style_combo.currentTextChanged.connect(self._rebuild_stats_grid)
        style_row.addWidget(self._style_combo); style_row.addStretch()
        sb.addLayout(style_row)

        self._stats_grid_w = QWidget()
        self._stats_grid   = QGridLayout(self._stats_grid_w)
        self._stats_grid.setSpacing(8)
        sb.addWidget(self._stats_grid_w)

        self._stats_freeform = QTextEdit()
        self._stats_freeform.setPlaceholderText(
            "Enter stats freeform, e.g.:\nSTR: 16\nDEX: 14\nWIS: 12")
        self._stats_freeform.setFixedHeight(100)
        self._stats_freeform.setVisible(False)
        sb.addWidget(self._stats_freeform)

        fl.addWidget(sb_box)
        self._rebuild_stats_grid("D&D 5e")

        # ── Lore / Notes ──────────────────────────────────────────────────────
        lore_box = QGroupBox("Lore & Notes")
        lb = QVBoxLayout(lore_box); lb.setSpacing(8)

        self._bg_edit = QTextEdit(); self._bg_edit.setPlaceholderText("Background…")
        self._bg_edit.setFixedHeight(70)
        lb.addLayout(_field("Background", self._bg_edit))

        self._traits_edit = QTextEdit()
        self._traits_edit.setPlaceholderText("Personality traits, ideals, bonds, flaws…")
        self._traits_edit.setFixedHeight(70)
        lb.addLayout(_field("Traits", self._traits_edit))

        self._equip_edit = QTextEdit()
        self._equip_edit.setPlaceholderText("Equipment & wargear…")
        self._equip_edit.setFixedHeight(70)
        lb.addLayout(_field("Equipment / Wargear", self._equip_edit))

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Other notes…")
        self._notes_edit.setFixedHeight(70)
        lb.addLayout(_field("Notes", self._notes_edit))

        fl.addWidget(lore_box)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("statusError")
        lay.addWidget(self._status_lbl)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _rebuild_stats_grid(self, style: str):
        # Clear old widgets
        self._stat_widgets.clear()
        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if style == "Freeform":
            self._stats_freeform.setVisible(True)
            self._stats_grid_w.setVisible(False)
            return

        self._stats_freeform.setVisible(False)
        self._stats_grid_w.setVisible(True)

        if style == "D&D 5e":
            keys = DND_STATS
        elif style == "Wargame: 40K":
            keys = WARGAME_40K
        else:  # AOS
            keys = WARGAME_AOS

        for col, key in enumerate(keys):
            lbl = QLabel(key); lbl.setObjectName("fieldLabel")
            lbl.setAlignment(Qt.AlignCenter)
            inp = QLineEdit(); inp.setFixedWidth(60); inp.setAlignment(Qt.AlignCenter)
            self._stats_grid.addWidget(lbl, 0, col)
            self._stats_grid.addWidget(inp, 1, col)
            self._stat_widgets[key] = inp

    def _populate(self, ch):
        self._name_edit.setText(ch.name)
        self._role_combo.setCurrentText(ch.character_role)
        self._status_combo.setCurrentText(ch.status)
        if ch.character_class: self._class_edit.setText(ch.character_class)
        if ch.race:            self._race_edit.setText(ch.race)
        self._level_spin.setValue(ch.level)
        self._hp_spin.setValue(ch.hit_points)
        self._max_hp_spin.setValue(ch.max_hit_points)
        self._ac_spin.setValue(ch.armor_class)
        if ch.background:       self._bg_edit.setPlainText(ch.background)
        if ch.traits:           self._traits_edit.setPlainText(ch.traits)
        if ch.equipment_notes:  self._equip_edit.setPlainText(ch.equipment_notes)
        if ch.notes:            self._notes_edit.setPlainText(ch.notes)

        # Player link
        if ch.player_id:
            idx = self._player_combo.findData(ch.player_id)
            if idx >= 0: self._player_combo.setCurrentIndex(idx)

        # Stat style & values
        style = ch.stat_style or "D&D 5e"
        self._style_combo.setCurrentText(style)
        self._rebuild_stats_grid(style)
        stats = ch.stats
        if style == "Freeform":
            lines = [f"{k}: {v}" for k, v in stats.items()]
            self._stats_freeform.setPlainText("\n".join(lines))
        else:
            for key, widget in self._stat_widgets.items():
                widget.setText(str(stats.get(key, "")))

    def _collect_stats(self) -> dict:
        style = self._style_combo.currentText()
        if style == "Freeform":
            stats = {}
            for line in self._stats_freeform.toPlainText().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    stats[k.strip()] = v.strip()
            return stats
        return {k: w.text().strip() for k, w in self._stat_widgets.items() if w.text().strip()}

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._status_lbl.setText("Name cannot be empty.")
            return

        kwargs = dict(
            character_role  = self._role_combo.currentText(),
            status          = self._status_combo.currentText(),
            character_class = self._class_edit.text().strip() or None,
            race            = self._race_edit.text().strip() or None,
            level           = self._level_spin.value(),
            hit_points      = self._hp_spin.value(),
            max_hit_points  = self._max_hp_spin.value(),
            armor_class     = self._ac_spin.value(),
            stat_style      = self._style_combo.currentText(),
            background      = self._bg_edit.toPlainText().strip() or None,
            traits          = self._traits_edit.toPlainText().strip() or None,
            equipment_notes = self._equip_edit.toPlainText().strip() or None,
            notes           = self._notes_edit.toPlainText().strip() or None,
            player_id       = self._player_combo.currentData(),
        )

        import json
        stats = self._collect_stats()
        kwargs["stats_json"] = json.dumps(stats) if stats else None

        try:
            if self._character:
                self._character = self._svc.update_character(self._character.id, name=name, **kwargs)
            else:
                self._character = self._svc.add_character(self._campaign.id, name, **kwargs)
            self.accept()
        except (ValidationError, ValueError, Exception) as e:
            self._status_lbl.setText(str(e))

    def result_character(self):
        return self._character


# ── Battle dialog ──────────────────────────────────────────────────────────────

class BattleDialog(QDialog):
    def __init__(self, context, campaign, battle=None, parent=None):
        super().__init__(parent)
        self._ctx      = context
        self._campaign = campaign
        self._battle   = battle
        self._svc      = context.services.try_get("campaign_service")
        self.setWindowTitle("Edit Session/Battle" if battle else "Log Session / Battle")
        self.setMinimumSize(560, 480)
        self.resize(660, 580)
        self._build_ui()
        if battle:
            self._populate(battle)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18,14,18,14); lay.setSpacing(10)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        fw = QWidget(); fl = QVBoxLayout(fw); fl.setSpacing(12)
        scroll.setWidget(fw); lay.addWidget(scroll, stretch=1)

        # ── Core info ─────────────────────────────────────────────────────────
        info_box = QGroupBox("Session Info")
        ib = QGridLayout(info_box); ib.setSpacing(8)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Session or battle title…")
        ib.addLayout(_field("Title *", self._title_edit), 0, 0, 1, 2)

        self._num_spin = QSpinBox(); self._num_spin.setRange(1, 9999)
        ib.addLayout(_field("Session #", self._num_spin), 1, 0)

        self._date_edit = QLineEdit()
        self._date_edit.setPlaceholderText("YYYY-MM-DD")
        ib.addLayout(_field("Date Played", self._date_edit), 1, 1)

        self._loc_edit = QLineEdit()
        self._loc_edit.setPlaceholderText("Location or setting name…")
        ib.addLayout(_field("Location", self._loc_edit), 2, 0, 1, 2)

        self._scenario_edit = QLineEdit()
        self._scenario_edit.setPlaceholderText("Scenario or adventure name…")
        ib.addLayout(_field("Scenario / Adventure", self._scenario_edit), 3, 0, 1, 2)

        self._outcome_combo = QComboBox(); self._outcome_combo.addItems(BATTLE_OUTCOMES)
        ib.addLayout(_field("Outcome", self._outcome_combo), 4, 0)

        fl.addWidget(info_box)

        # ── Participants ──────────────────────────────────────────────────────
        p_box = QGroupBox("Participants")
        pb = QVBoxLayout(p_box)

        self._participant_table = QTableWidget(0, 4)
        self._participant_table.setHorizontalHeaderLabels(["Player", "Side", "Score", "Result"])
        self._participant_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._participant_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._participant_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._participant_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._participant_table.verticalHeader().setVisible(False)
        self._participant_table.setMaximumHeight(160)
        pb.addWidget(self._participant_table)

        p_btn_row = QHBoxLayout()
        add_p  = QPushButton("+ Add Participant"); add_p.clicked.connect(self._add_participant_row)
        rem_p  = QPushButton("Remove Selected");   rem_p.clicked.connect(self._remove_participant_row)
        rem_p.setProperty("class", "danger")
        p_btn_row.addWidget(add_p); p_btn_row.addWidget(rem_p); p_btn_row.addStretch()
        pb.addLayout(p_btn_row)
        fl.addWidget(p_box)

        # ── Scoring + Chronicle ───────────────────────────────────────────────
        sc_box = QGroupBox("Scoring & Notes")
        sc = QVBoxLayout(sc_box)
        self._scoring_edit = QTextEdit()
        self._scoring_edit.setPlaceholderText("VP totals, objectives completed, XP awarded…")
        self._scoring_edit.setFixedHeight(80)
        sc.addLayout(_field("Scoring Notes", self._scoring_edit))

        self._chronicle_edit = QTextEdit()
        self._chronicle_edit.setPlaceholderText("Session recap / battle narrative…")
        self._chronicle_edit.setFixedHeight(100)
        sc.addLayout(_field("Chronicle / Recap", self._chronicle_edit))
        fl.addWidget(sc_box)

        self._status_lbl = QLabel(""); self._status_lbl.setObjectName("statusError")
        lay.addWidget(self._status_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # Populate players if we have them
        self._players = self._svc.get_players(self._campaign.id) if self._svc else []

    def _add_participant_row(self, player_id=None, side="", score=0, result=""):
        row = self._participant_table.rowCount()
        self._participant_table.insertRow(row)

        p_combo = QComboBox()
        for p in self._players:
            p_combo.addItem(f"{p.player_name} ({p.role})", p.id)
        if player_id:
            idx = p_combo.findData(player_id)
            if idx >= 0: p_combo.setCurrentIndex(idx)
        self._participant_table.setCellWidget(row, 0, p_combo)

        self._participant_table.setItem(row, 1, QTableWidgetItem(side))
        score_item = QTableWidgetItem(str(score))
        score_item.setTextAlignment(Qt.AlignCenter)
        self._participant_table.setItem(row, 2, score_item)
        self._participant_table.setItem(row, 3, QTableWidgetItem(result))

    def _remove_participant_row(self):
        row = self._participant_table.currentRow()
        if row >= 0: self._participant_table.removeRow(row)

    def _populate(self, b):
        self._title_edit.setText(b.title)
        self._num_spin.setValue(b.session_number)
        if b.date_played:    self._date_edit.setText(b.date_played)
        if b.location_name:  self._loc_edit.setText(b.location_name)
        if b.scenario_name:  self._scenario_edit.setText(b.scenario_name)
        self._outcome_combo.setCurrentText(b.outcome)
        if b.scoring_notes:  self._scoring_edit.setPlainText(b.scoring_notes)
        if b.chronicle_text: self._chronicle_edit.setPlainText(b.chronicle_text)

        if self._svc:
            for p in self._svc.get_participants(b.id):
                self._add_participant_row(p.player_id, p.side, p.score, p.result)

    def _on_save(self):
        title = self._title_edit.text().strip()
        if not title:
            self._status_lbl.setText("Title cannot be empty."); return

        # Collect participants
        participants = []
        for row in range(self._participant_table.rowCount()):
            combo = self._participant_table.cellWidget(row, 0)
            if not combo: continue
            pid = combo.currentData()
            if pid is None: continue
            side_item   = self._participant_table.item(row, 1)
            score_item  = self._participant_table.item(row, 2)
            result_item = self._participant_table.item(row, 3)
            try:    score = int(score_item.text()) if score_item else 0
            except: score = 0
            participants.append({
                "player_id": pid,
                "side":   side_item.text()   if side_item   else "",
                "score":  score,
                "result": result_item.text() if result_item else "",
            })

        kwargs = dict(
            session_number      = self._num_spin.value(),
            date_played         = self._date_edit.text().strip() or None,
            location_name       = self._loc_edit.text().strip() or None,
            scenario_name       = self._scenario_edit.text().strip() or None,
            outcome             = self._outcome_combo.currentText(),
            scoring_notes       = self._scoring_edit.toPlainText().strip() or None,
            chronicle_text      = self._chronicle_edit.toPlainText().strip() or None,
        )
        try:
            if self._battle:
                self._battle = self._svc.update_battle(self._battle.id, title=title, **kwargs)
            else:
                self._battle = self._svc.add_battle(self._campaign.id, title, **kwargs)
            if participants:
                self._svc.set_participants(self._battle.id, participants)
            self.accept()
        except Exception as e:
            self._status_lbl.setText(str(e))

    def result_battle(self): return self._battle


# ── Journal entry dialog ───────────────────────────────────────────────────────

class JournalDialog(QDialog):
    def __init__(self, context, campaign, entry=None, parent=None):
        super().__init__(parent)
        self._ctx      = context
        self._campaign = campaign
        self._entry    = entry
        self._svc      = context.services.try_get("campaign_service")
        self.setWindowTitle("Edit Entry" if entry else "New Journal Entry")
        self.setMinimumSize(540, 480)
        self._build_ui()
        if entry: self._populate(entry)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18,14,18,14); lay.setSpacing(10)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Entry title…")
        lay.addLayout(_field("Title *", self._title_edit))

        # Optional battle link
        self._battle_combo = QComboBox()
        self._battle_combo.addItem("— Not linked to a battle —", None)
        if self._svc:
            for b in self._svc.get_battles(self._campaign.id):
                self._battle_combo.addItem(f"#{b.session_number}  {b.title}", b.id)
        lay.addLayout(_field("Link to Session / Battle (optional)", self._battle_combo))

        self._content_edit = QTextEdit()
        self._content_edit.setPlaceholderText("Write your journal entry here…")
        lay.addWidget(self._content_edit, stretch=1)

        self._status_lbl = QLabel(""); self._status_lbl.setObjectName("statusError")
        lay.addWidget(self._status_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _populate(self, e):
        self._title_edit.setText(e.title)
        self._content_edit.setPlainText(e.content)
        if e.battle_id:
            idx = self._battle_combo.findData(e.battle_id)
            if idx >= 0: self._battle_combo.setCurrentIndex(idx)

    def _on_save(self):
        title   = self._title_edit.text().strip()
        content = self._content_edit.toPlainText()
        if not title:
            self._status_lbl.setText("Title cannot be empty."); return
        battle_id = self._battle_combo.currentData()
        try:
            if self._entry:
                self._entry = self._svc.update_journal_entry(self._entry.id, title, content, battle_id)
            else:
                self._entry = self._svc.add_journal_entry(self._campaign.id, title, content, battle_id)
            self.accept()
        except Exception as e:
            self._status_lbl.setText(str(e))

    def result_entry(self): return self._entry


# ── Campaign create/edit dialog ────────────────────────────────────────────────

class CampaignDialog(QDialog):
    def __init__(self, context, campaign=None, parent=None):
        super().__init__(parent)
        self._ctx      = context
        self._campaign = campaign
        self._svc      = context.services.try_get("campaign_service")
        self.setWindowTitle("Edit Campaign" if campaign else "New Campaign")
        self.setMinimumSize(520, 420)
        self._build_ui()
        if campaign: self._populate(campaign)

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18,14,18,14); lay.setSpacing(10)

        self._name_edit = QLineEdit(); self._name_edit.setPlaceholderText("Campaign name…")
        lay.addLayout(_field("Name *", self._name_edit))

        self._gs_combo = QComboBox(); self._gs_combo.setEditable(True)
        self._gs_combo.addItems(GAME_SYSTEMS)
        lay.addLayout(_field("Game System", self._gs_combo))

        self._status_combo = QComboBox(); self._status_combo.addItems(CAMPAIGN_STATUSES)
        lay.addLayout(_field("Status", self._status_combo))

        self._start_edit = QLineEdit(); self._start_edit.setPlaceholderText("YYYY-MM-DD")
        lay.addLayout(_field("Start Date", self._start_edit))

        self._desc_edit = QTextEdit(); self._desc_edit.setFixedHeight(80)
        self._desc_edit.setPlaceholderText("Campaign description…")
        lay.addLayout(_field("Description", self._desc_edit))

        self._notes_edit = QTextEdit(); self._notes_edit.setFixedHeight(80)
        self._notes_edit.setPlaceholderText("Additional notes…")
        lay.addLayout(_field("Notes", self._notes_edit))

        self._status_lbl = QLabel(""); self._status_lbl.setObjectName("statusError")
        lay.addWidget(self._status_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _populate(self, c):
        self._name_edit.setText(c.name)
        self._gs_combo.setCurrentText(c.game_system)
        self._status_combo.setCurrentText(c.status)
        if c.start_date:   self._start_edit.setText(c.start_date)
        if c.description:  self._desc_edit.setPlainText(c.description)
        if c.notes:        self._notes_edit.setPlainText(c.notes)

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._status_lbl.setText("Name cannot be empty."); return
        kwargs = dict(
            game_system  = self._gs_combo.currentText(),
            status       = self._status_combo.currentText(),
            start_date   = self._start_edit.text().strip() or None,
            description  = self._desc_edit.toPlainText().strip() or None,
            notes        = self._notes_edit.toPlainText().strip() or None,
        )
        try:
            if self._campaign:
                self._campaign = self._svc.update_campaign(self._campaign.id, name=name, **kwargs)
            else:
                self._campaign = self._svc.create_campaign(name, **kwargs)
            self.accept()
        except Exception as e:
            self._status_lbl.setText(str(e))

    def result_campaign(self): return self._campaign


# ── Encounter Builder Tab ─────────────────────────────────────────────────────

class _EncounterBuilderTab(QWidget):
    """Plan and save encounters with monsters from the game data library."""

    DIFFICULTIES = ["", "Easy", "Medium", "Hard", "Deadly"]
    DIFF_COLORS  = {"Easy": "#3dba6e", "Medium": "#f0a020",
                    "Hard": "#e05555", "Deadly": "#a020a0"}

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self._svc = context.services.try_get("campaign_service")
        self._campaign = None
        self._selected_enc = None
        self._build_ui()

    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Left: encounter list ──────────────────────────────────────────────
        left = QWidget()
        left.setObjectName("sidePanel")
        left.setFixedWidth(300)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 12, 8, 12)
        ll.setSpacing(8)

        lbl = QLabel("Encounters")
        lbl.setObjectName("sidePanelTitle")
        ll.addWidget(lbl)

        new_enc_btn = QPushButton("+ New Encounter")
        new_enc_btn.setProperty("class", "primary")
        new_enc_btn.clicked.connect(self._new_encounter)
        ll.addWidget(new_enc_btn)

        self._enc_list = QListWidget()
        self._enc_list.setAlternatingRowColors(False)
        self._enc_list.setStyleSheet("background: transparent; border: none;")
        self._enc_list.currentItemChanged.connect(self._on_enc_selected)
        ll.addWidget(self._enc_list, stretch=1)

        del_enc_btn = QPushButton("Delete Encounter")
        del_enc_btn.setProperty("class", "danger")
        del_enc_btn.clicked.connect(self._delete_encounter)
        ll.addWidget(del_enc_btn)

        lay.addWidget(left)

        # ── Right: encounter detail ───────────────────────────────────────────
        self._right = QWidget()
        rl = QVBoxLayout(self._right)
        rl.setContentsMargins(20, 16, 20, 16)
        rl.setSpacing(12)

        # Encounter header
        hdr = QHBoxLayout()
        self._enc_name_edit = QLineEdit()
        self._enc_name_edit.setPlaceholderText("Encounter name…")
        self._enc_name_edit.setStyleSheet("font-size: 15px; font-weight: 600;")
        hdr.addWidget(self._enc_name_edit, stretch=1)

        hdr.addWidget(QLabel("Difficulty:"))
        self._diff_combo = QComboBox()
        self._diff_combo.addItems(self.DIFFICULTIES)
        self._diff_combo.currentTextChanged.connect(self._update_diff_color)
        hdr.addWidget(self._diff_combo)

        save_enc_btn = QPushButton("Save")
        save_enc_btn.setProperty("class", "primary")
        save_enc_btn.clicked.connect(self._save_encounter)
        hdr.addWidget(save_enc_btn)
        rl.addLayout(hdr)

        self._enc_desc = QTextEdit()
        self._enc_desc.setPlaceholderText("Notes, setting, objectives…")
        self._enc_desc.setFixedHeight(60)
        rl.addWidget(self._enc_desc)

        # Monster list
        monster_hdr = QHBoxLayout()
        monster_hdr.addWidget(QLabel("Monsters"))
        monster_hdr.addStretch()
        browse_mon_btn = QPushButton("Browse Monsters…")
        browse_mon_btn.clicked.connect(self._browse_monsters)
        add_custom_mon = QPushButton("+ Custom")
        add_custom_mon.clicked.connect(lambda: self._add_monster_manually())
        monster_hdr.addWidget(browse_mon_btn)
        monster_hdr.addWidget(add_custom_mon)
        rl.addLayout(monster_hdr)

        self._mon_table = QTableWidget(0, 4)
        self._mon_table.setHorizontalHeaderLabels(["Monster", "CR", "Count", "HP Override"])
        h = self._mon_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._mon_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._mon_table.setAlternatingRowColors(True)
        self._mon_table.verticalHeader().setVisible(False)
        self._mon_table.setShowGrid(False)
        self._mon_table.setSelectionBehavior(QTableWidget.SelectRows)
        rl.addWidget(self._mon_table, stretch=1)

        btn_row = QHBoxLayout()
        remove_mon_btn = QPushButton("Remove Selected")
        remove_mon_btn.setProperty("class", "danger")
        remove_mon_btn.clicked.connect(self._remove_monster)
        push_btn = QPushButton("▶ Push to Initiative Tracker")
        push_btn.setToolTip("Add all monsters in this encounter to the Initiative tab")
        push_btn.clicked.connect(self._push_to_initiative)
        btn_row.addWidget(remove_mon_btn)
        btn_row.addStretch()
        btn_row.addWidget(push_btn)
        rl.addLayout(btn_row)

        self._empty_lbl = QLabel("Select or create an encounter to get started.")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #484848; font-size: 13px;")
        rl.addWidget(self._empty_lbl)

        lay.addWidget(self._right, stretch=1)
        self._set_detail_visible(False)

    def load(self, campaign):
        self._campaign = campaign
        self._refresh_list()

    def _refresh_list(self):
        self._enc_list.clear()
        if not self._svc or not self._campaign:
            return
        for enc in self._svc.get_encounters(self._campaign.id):
            item = QListWidgetItem(enc.name)
            item.setData(Qt.UserRole, enc.id)
            diff_color = self.DIFF_COLORS.get(enc.difficulty or "", "#666")
            item.setForeground(QColor(diff_color))
            self._enc_list.addItem(item)

    def _on_enc_selected(self, item):
        if not item:
            self._set_detail_visible(False)
            return
        enc_id = item.data(Qt.UserRole)
        encs = self._svc.get_encounters(self._campaign.id) if self._svc else []
        enc = next((e for e in encs if e.id == enc_id), None)
        if not enc:
            return
        self._selected_enc = enc
        self._enc_name_edit.setText(enc.name)
        idx = self._diff_combo.findText(enc.difficulty or "")
        self._diff_combo.setCurrentIndex(max(0, idx))
        self._enc_desc.setPlainText(enc.description or "")
        self._refresh_monsters()
        self._set_detail_visible(True)

    def _set_detail_visible(self, visible: bool):
        for w in [self._enc_name_edit, self._diff_combo, self._enc_desc, self._mon_table]:
            w.setVisible(visible)
        self._empty_lbl.setVisible(not visible)

    def _update_diff_color(self, text: str):
        color = self.DIFF_COLORS.get(text, "#d8d8d8")
        self._diff_combo.setStyleSheet(f"color: {color}; font-weight: 600;")

    def _new_encounter(self):
        if not self._campaign or not self._svc:
            return
        enc = self._svc.add_encounter(self._campaign.id, "New Encounter")
        self._refresh_list()
        # Select it
        for i in range(self._enc_list.count()):
            if self._enc_list.item(i).data(Qt.UserRole) == enc.id:
                self._enc_list.setCurrentRow(i)
                break

    def _save_encounter(self):
        if not self._selected_enc or not self._svc:
            return
        self._selected_enc.name = self._enc_name_edit.text().strip() or "Encounter"
        self._selected_enc.difficulty = self._diff_combo.currentText() or None
        self._selected_enc.description = self._enc_desc.toPlainText().strip() or None
        self._svc.update_encounter(self._selected_enc)
        self._refresh_list()

    def _delete_encounter(self):
        item = self._enc_list.currentItem()
        if not item:
            return
        if QMessageBox.question(self, "Delete Encounter",
            f"Delete \"{item.text()}\"?",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._svc.delete_encounter(item.data(Qt.UserRole))
        self._selected_enc = None
        self._set_detail_visible(False)
        self._refresh_list()

    # ── Monsters ──────────────────────────────────────────────────────────────

    def _refresh_monsters(self):
        if not self._selected_enc or not self._svc:
            return
        self._mon_table.setRowCount(0)
        for m in self._svc.get_encounter_monsters(self._selected_enc.id):
            row = self._mon_table.rowCount()
            self._mon_table.insertRow(row)
            name_item = QTableWidgetItem(m.monster_name)
            name_item.setData(Qt.UserRole, m.id)
            self._mon_table.setItem(row, 0, name_item)
            cr_item = QTableWidgetItem(m.cr or "—")
            cr_item.setTextAlignment(Qt.AlignCenter)
            self._mon_table.setItem(row, 1, cr_item)
            cnt = QTableWidgetItem(str(m.count))
            cnt.setTextAlignment(Qt.AlignCenter)
            self._mon_table.setItem(row, 2, cnt)
            hp = QTableWidgetItem(str(m.hp_override) if m.hp_override else "—")
            hp.setTextAlignment(Qt.AlignCenter)
            self._mon_table.setItem(row, 3, hp)

    def _browse_monsters(self):
        if not self._selected_enc:
            return
        dlg = _GameDataBrowserDialog("Monsters", parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_name:
            self._add_monster_manually(prefill_name=dlg.selected_name,
                                       prefill_cr=self._get_cr_for(dlg.selected_name))

    def _get_cr_for(self, monster_name: str) -> str:
        try:
            m = GameDataLoader.get_monster(monster_name)
            if m:
                cr = m.get("properties", {}).get("Challenge Rating", "")
                return str(cr) if cr is not None else ""
        except Exception:
            pass
        return ""

    def _add_monster_manually(self, prefill_name: str = "", prefill_cr: str = ""):
        if not self._selected_enc:
            return
        dlg = _AddEncounterMonsterDialog(prefill_name=prefill_name,
                                         prefill_cr=prefill_cr, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, count, hp_override, cr = dlg.values()
        if self._svc:
            self._svc.add_encounter_monster(
                self._selected_enc.id, name,
                count=count, hp_override=hp_override or None, cr=cr or None)
        self._refresh_monsters()

    def _remove_monster(self):
        row = self._mon_table.currentRow()
        if row < 0:
            return
        m_id = self._mon_table.item(row, 0).data(Qt.UserRole)
        if self._svc:
            self._svc.delete_encounter_monster(m_id)
        self._refresh_monsters()

    def _push_to_initiative(self):
        """Emit signal or find the initiative tab and add monsters there."""
        if not self._selected_enc or not self._svc:
            return
        monsters = self._svc.get_encounter_monsters(self._selected_enc.id)
        if not monsters:
            _show_toast(self, "ℹ  Add monsters to this encounter first", "toastInfo")
            return
        # Navigate to the Initiative tab and add
        detail_view = self.parent()
        while detail_view and not isinstance(detail_view, CampaignDetailView):
            detail_view = detail_view.parent()
        if not detail_view:
            _show_toast(self, "ℹ  Switch to the ⚔ Initiative tab and click 'Load Roster'", "toastInfo")
            return
        init_tab = detail_view._initiative_tab
        for m in monsters:
            for _ in range(m.count):
                hp = m.hp_override or 10
                init_tab._add_row(m.monster_name, hp, hp, 0, "Monster")
        # Switch to initiative tab
        tabs = detail_view._tabs
        for i in range(tabs.count()):
            if "Initiative" in tabs.tabText(i):
                tabs.setCurrentIndex(i)
                break
        _show_toast(self, f"✓  Added {sum(m.count for m in monsters)} combatant(s) to Initiative")


# ── Add Encounter Monster dialog ──────────────────────────────────────────────

class _AddEncounterMonsterDialog(QDialog):
    def __init__(self, prefill_name: str = "", prefill_cr: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Monster")
        self.setFixedWidth(360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel("Monster Name"))
        self._name = QLineEdit(prefill_name)
        lay.addWidget(self._name)

        grid = QGridLayout()
        grid.addWidget(QLabel("Count"), 0, 0)
        self._count = QSpinBox(); self._count.setRange(1, 99); self._count.setValue(1)
        grid.addWidget(self._count, 0, 1)

        grid.addWidget(QLabel("CR"), 0, 2)
        self._cr = QLineEdit(str(prefill_cr) if prefill_cr is not None else ""); self._cr.setFixedWidth(60)
        grid.addWidget(self._cr, 0, 3)

        grid.addWidget(QLabel("HP Override"), 1, 0)
        self._hp = QSpinBox(); self._hp.setRange(0, 9999)
        self._hp.setSpecialValueText("Use default")
        grid.addWidget(self._hp, 1, 1)
        lay.addLayout(grid)

        btns = QHBoxLayout()
        ok = QPushButton("Add"); ok.setProperty("class", "primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(ok)
        lay.addLayout(btns)

    def values(self):
        return (self._name.text().strip(), self._count.value(),
                self._hp.value() if self._hp.value() > 0 else None,
                self._cr.text().strip())


# ── Game Data Model (used by _GameDataTab and _GameDataBrowserDialog) ──────────────

def _game_row(entry: dict, category: str) -> list:
    """Build the display columns for one table row."""
    props     = entry.get("properties", {}) or {}
    name      = entry.get("name", "")
    book      = entry.get("book", "") or ""
    publisher = entry.get("publisher", "") or ""
    if category == "Spells":
        level  = str(props.get("Level", "?"))
        school = (props.get("School", "") or "").capitalize()
        col1   = f"Level {level}  ·  {school}".strip("  ·  ")
        col2   = "  ·  ".join(filter(None, [
            props.get("Components", ""),
            props.get("Casting Time", ""),
        ]))
        return [name, col1, col2, book]
    elif category == "Monsters":
        cr    = str(props.get("Challenge Rating", "?"))
        mtype = (props.get("Type", "") or "").capitalize()
        size  = props.get("Size", "") or ""
        col1  = "  ·  ".join(filter(None, [f"CR {cr}", mtype, size]))
        col2  = props.get("Alignment", "") or ""
        return [name, col1, col2, book]
    elif category == "Items":
        col1 = props.get("Item Type", "") or ""
        col2 = (props.get("Item Rarity", "") or "").capitalize()
        return [name, col1, col2, book]
    elif category == "📁 Data Files":
        # Generic row for any JSON file — extract the most useful fields available
        # Try common field names used in various game data formats
        faction = (entry.get("faction") or entry.get("factionname")
                   or entry.get("type") or entry.get("category") or "")
        if isinstance(faction, list):
            faction = ", ".join(str(f) for f in faction[:3])

        # Points / cost
        pts = ""
        points_raw = entry.get("points") or entry.get("cost") or entry.get("pts") or ""
        if isinstance(points_raw, list) and points_raw:
            first = points_raw[0]
            if isinstance(first, dict):
                pts = str(first.get("cost", first.get("pts", "")))
            else:
                pts = str(first)
        elif isinstance(points_raw, (int, float, str)):
            pts = str(points_raw)

        # Keywords / tags
        kw = entry.get("keywords") or entry.get("tags") or entry.get("source") or ""
        if isinstance(kw, dict):
            kw = ", ".join(str(v) for v in kw.values() if isinstance(v, (str, int)))
        elif isinstance(kw, list):
            kw = ", ".join(str(k) for k in kw[:4])

        return [name, faction, pts, str(kw)[:60]]
    else:
        return [name, publisher, book, ""]


class _GameDataModel(QAbstractTableModel):
    """High-performance table model.  Handles 15 000+ rows with no lag."""

    def __init__(self, headers: list, parent=None):
        super().__init__(parent)
        self._headers = headers
        self._rows: list = []   # list of (display_cols: list[str], raw_entry: dict)

    def reset_data(self, entries: list, category: str):
        self.beginResetModel()
        self._rows = [(_game_row(e, category), e) for e in entries]
        self.endResetModel()

    def entry(self, row: int) -> dict:
        if 0 <= row < len(self._rows):
            return self._rows[row][1]
        return {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        if role == Qt.DisplayRole:
            cols = self._rows[index.row()][0]
            col = index.column()
            return cols[col] if col < len(cols) else ""
        return None

    def sort(self, column: int, order=Qt.AscendingOrder):
        self.layoutAboutToBeChanged.emit()
        reverse = (order == Qt.DescendingOrder)
        self._rows.sort(
            key=lambda r: (r[0][column] if column < len(r[0]) else "").lower(),
            reverse=reverse,
        )
        self.layoutChanged.emit()


# ── Game Data Tab ─────────────────────────────────────────────────────────────────────────────

class _GameDataTab(QWidget):
    """Browse all game data — Spells, Monsters, Items, Classes, Species, Backgrounds, and any custom data files."""

    _HEADERS = {
        "Spells":      ["Name", "Level · School", "Components", "Book"],
        "Monsters":    ["Name", "CR · Type · Size", "Alignment", "Book"],
        "Items":       ["Name", "Type", "Rarity", "Book"],
        "Classes":     ["Name", "Publisher", "Book", ""],
        "Species":     ["Name", "Publisher", "Book", ""],
        "Backgrounds": ["Name", "Publisher", "Book", ""],
        "📁 Data Files": ["Name", "Detail", "Extra", "Source"],
    }
    _CATEGORIES = ["Spells", "Monsters", "Items", "Classes", "Species", "Backgrounds", "📁 Data Files"]

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self._models: dict = {}
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        title = QLabel("Game Data Library")
        title.setObjectName("pageTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(QLabel("System:"))
        self._sys_combo = QComboBox()
        self._sys_combo.addItems(GameDataLoader.available_systems() or ["D&D 5e"])
        self._sys_combo.currentTextChanged.connect(self._on_system_changed)
        hdr.addWidget(self._sys_combo)

        # Refresh button — re-scans installed systems (useful after a GitHub import)
        self._refresh_sys_btn = QPushButton("⟳")
        self._refresh_sys_btn.setFixedSize(28, 28)
        self._refresh_sys_btn.setToolTip("Refresh installed systems")
        self._refresh_sys_btn.clicked.connect(self._refresh_systems)
        hdr.addWidget(self._refresh_sys_btn)

        lay.addLayout(hdr)

        self._cat_tabs = QTabWidget()
        self._cat_tabs.setDocumentMode(True)
        for cat in self._CATEGORIES:
            self._cat_tabs.addTab(self._make_data_page(cat), cat)
        self._cat_tabs.currentChanged.connect(self._on_cat_changed)
        lay.addWidget(self._cat_tabs, stretch=1)

        QTimer.singleShot(0, lambda: self._do_search("Spells", ""))

    def _make_data_page(self, category: str) -> QWidget:
        # ── Special "Data Files" page ──────────────────────────────────────────
        if category == "📁 Data Files":
            return self._make_files_page()

        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(6)

        # ─ Filter row ────────────────────────────────────────────────────────────
        filters = QHBoxLayout()
        filters.setSpacing(6)

        search = QLineEdit()
        search.setPlaceholderText(f"Search {category.lower()}…")
        search.setObjectName(f"search_{category}")
        search.textChanged.connect(lambda q, c=category: self._do_search(c, q))
        filters.addWidget(search, stretch=2)

        if category == "Spells":
            school_cb = QComboBox()
            school_cb.setObjectName("school_combo")
            school_cb.addItem("All Schools")
            try:
                school_cb.addItems(GameDataLoader.spell_schools())
            except Exception:
                pass
            school_cb.currentTextChanged.connect(
                lambda _, c=category, s=search: self._do_search(c, s.text()))
            filters.addWidget(school_cb)
        elif category == "Monsters":
            cr_cb = QComboBox()
            cr_cb.setObjectName("cr_combo")
            cr_cb.addItem("All CR")
            try:
                cr_cb.addItems(GameDataLoader.challenge_ratings())
            except Exception:
                pass
            cr_cb.currentTextChanged.connect(
                lambda _, c=category, s=search: self._do_search(c, s.text()))
            filters.addWidget(cr_cb)
        elif category == "Items":
            rarity_cb = QComboBox()
            rarity_cb.setObjectName("rarity_combo")
            rarity_cb.addItem("All Rarities")
            try:
                rarity_cb.addItems(GameDataLoader.item_rarities())
            except Exception:
                pass
            rarity_cb.currentTextChanged.connect(
                lambda _, c=category, s=search: self._do_search(c, s.text()))
            filters.addWidget(rarity_cb)

        # Book filter — populated lazily on first data load for this category
        book_cb = QComboBox()
        book_cb.setObjectName("book_combo")
        book_cb.setMinimumWidth(220)
        book_cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        book_cb.addItem("All Books")
        book_cb.currentTextChanged.connect(
            lambda _, c=category, s=search: self._do_search(c, s.text()))
        filters.addWidget(book_cb, stretch=3)

        outer.addLayout(filters)

        # ─ Splitter: table | description ────────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        model = _GameDataModel(self._HEADERS.get(category, ["Name", "Detail", "", ""]))
        self._models[category] = model

        view = QTableView()
        view.setModel(model)
        view.setObjectName(f"view_{category}")
        view.setSortingEnabled(True)
        view.setAlternatingRowColors(True)
        view.verticalHeader().setVisible(False)
        view.setShowGrid(False)
        view.setSelectionBehavior(QTableView.SelectRows)
        view.setSelectionMode(QTableView.SingleSelection)
        view.setEditTriggers(QTableView.NoEditTriggers)
        hh = view.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        view.verticalHeader().setDefaultSectionSize(24)

        # Full description — no character truncation, drag-to-resize via splitter
        desc = QTextEdit()
        desc.setReadOnly(True)
        desc.setMinimumHeight(100)
        desc.setPlaceholderText("Select an entry to read its full description…")

        view.selectionModel().currentRowChanged.connect(
            lambda cur, _p, m=model, d=desc: self._on_selection(m, cur.row(), d))

        count_lbl = QLabel("")
        count_lbl.setStyleSheet("color: #505050; font-size: 11px;")
        count_lbl.setObjectName(f"count_{category}")

        splitter.addWidget(view)
        splitter.addWidget(desc)
        splitter.setSizes([420, 180])

        outer.addWidget(splitter, stretch=1)
        outer.addWidget(count_lbl)
        return w

    # ─ Data Files page ───────────────────────────────────────────────────────────────────

    def _make_files_page(self) -> QWidget:
        """Generic data-file browser — works for any game system."""
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(6)

        # File picker + search row
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        file_cb = QComboBox()
        file_cb.setObjectName("files_file_combo")
        file_cb.setMinimumWidth(260)
        file_cb.setPlaceholderText("Select a data file…")
        top_row.addWidget(file_cb, stretch=1)

        search = QLineEdit()
        search.setPlaceholderText("Search entries…")
        search.setObjectName("search_📁 Data Files")
        search.setClearButtonEnabled(True)
        top_row.addWidget(search, stretch=2)
        outer.addLayout(top_row)

        # Splitter: table | description
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        model = _GameDataModel(["Name", "Detail", "Extra", "Source"])
        self._models["📁 Data Files"] = model

        view = QTableView()
        view.setModel(model)
        view.setObjectName("view_📁 Data Files")
        view.setSortingEnabled(True)
        view.setAlternatingRowColors(True)
        view.verticalHeader().setVisible(False)
        view.setShowGrid(False)
        view.setSelectionBehavior(QTableView.SelectRows)
        view.setSelectionMode(QTableView.SingleSelection)
        view.setEditTriggers(QTableView.NoEditTriggers)
        hh = view.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        view.verticalHeader().setDefaultSectionSize(24)

        desc = QTextEdit()
        desc.setReadOnly(True)
        desc.setMinimumHeight(120)
        desc.setPlaceholderText("Select an entry to see its full details…")

        view.selectionModel().currentRowChanged.connect(
            lambda cur, _p, m=model, d=desc: self._on_files_selection(m, cur.row(), d))

        count_lbl = QLabel("")
        count_lbl.setStyleSheet("color: #505050; font-size: 11px;")
        count_lbl.setObjectName("count_📁 Data Files")

        splitter.addWidget(view)
        splitter.addWidget(desc)
        splitter.setSizes([400, 160])

        outer.addWidget(splitter, stretch=1)
        outer.addWidget(count_lbl)

        # Wire signals
        file_cb.currentTextChanged.connect(
            lambda _fn, s=search: self._do_search_files(s.text()))
        search.textChanged.connect(self._do_search_files)

        return w

    def _on_files_selection(self, model: _GameDataModel, row: int, desc_view: QTextEdit):
        """Show all fields of the selected entry as formatted text."""
        entry = model.entry(row)
        if not entry:
            return
        lines = []
        for k, v in entry.items():
            if k.startswith("_"):
                continue
            if isinstance(v, (dict, list)):
                v = json.dumps(v, indent=2)
            lines.append(f"{'─' * 40}\n{k.upper()}\n{v}")
        desc_view.setPlainText("\n".join(lines) if lines else "No details available.")

    def _populate_file_combo(self):
        """Refresh the file-picker combo for the currently selected system."""
        page = self._files_page()
        if not page:
            return
        file_cb = page.findChild(QComboBox, "files_file_combo")
        if not file_cb:
            return
        system = self._sys_combo.currentText()
        files  = GameDataLoader.list_data_files(system)
        with QSignalBlocker(file_cb):
            file_cb.clear()
            file_cb.addItems(files)
        self._do_search_files("")

    def _files_page(self):
        for i in range(self._cat_tabs.count()):
            if self._cat_tabs.tabText(i) == "📁 Data Files":
                return self._cat_tabs.widget(i)
        return None

    def _do_search_files(self, query: str = ""):
        page = self._files_page()
        if not page:
            return
        file_cb   = page.findChild(QComboBox, "files_file_combo")
        count_lbl = page.findChild(QLabel, "count_📁 Data Files")
        model     = self._models.get("📁 Data Files")
        if not model:
            return

        filename = file_cb.currentText() if file_cb else ""
        system   = self._sys_combo.currentText()

        if not filename:
            model.reset_data([], "📁 Data Files")
            if count_lbl:
                count_lbl.setText("Select a file above to browse its contents.")
            return

        try:
            results = GameDataLoader.search_file_entries(system, filename, query)
        except Exception as e:
            if count_lbl:
                count_lbl.setText(f"Error: {e}")
            return

        model.reset_data(results, "📁 Data Files")
        if count_lbl:
            count_lbl.setText(f"{len(results):,} entries  ·  {filename}")

    # ─ System refresh ─────────────────────────────────────────────────────────────────────

    def _refresh_systems(self):
        """Re-scan installed systems and update the combo (useful after a GitHub import)."""
        current = self._sys_combo.currentText()
        systems = GameDataLoader.available_systems() or ["D&D 5e"]
        with QSignalBlocker(self._sys_combo):
            self._sys_combo.clear()
            self._sys_combo.addItems(systems)
        # Restore previous selection if it still exists, else stay at index 0
        if current in systems:
            self._sys_combo.setCurrentText(current)
        self._on_system_changed()

    # ─ Event handlers ────────────────────────────────────────────────────────────────────

    def _on_system_changed(self):
        for i in range(self._cat_tabs.count()):
            page = self._cat_tabs.widget(i)
            bc = page.findChild(QComboBox, "book_combo")
            if bc:
                bc.blockSignals(True)
                bc.clear()
                bc.addItem("All Books")
                bc.blockSignals(False)
        # Refresh data-files picker for the new system
        self._populate_file_combo()
        cat = self._cat_tabs.tabText(self._cat_tabs.currentIndex())
        self._do_search(cat, "")

    def _on_cat_changed(self, index: int):
        category = self._cat_tabs.tabText(index)
        if category == "📁 Data Files":
            self._populate_file_combo()
            return
        page = self._cat_tabs.widget(index)
        search = page.findChild(QLineEdit, f"search_{category}")
        self._do_search(category, search.text() if search else "")

    def _on_selection(self, model: _GameDataModel, row: int, desc_view: QTextEdit):
        entry = model.entry(row)
        text = entry.get("description", "") or ""
        desc_view.setPlainText(text if text else "No description available.")

    def _do_search(self, category: str, query: str):
        if category == "📁 Data Files":
            self._do_search_files(query)
            return

        page = None
        for i in range(self._cat_tabs.count()):
            if self._cat_tabs.tabText(i) == category:
                page = self._cat_tabs.widget(i)
                break
        if not page:
            return

        model     = self._models.get(category)
        count_lbl = page.findChild(QLabel, f"count_{category}")
        system    = self._sys_combo.currentText()

        book_cb = page.findChild(QComboBox, "book_combo")
        book = None
        if book_cb and book_cb.currentText() != "All Books":
            book = book_cb.currentText()

        try:
            if category == "Spells":
                school_cb = page.findChild(QComboBox, "school_combo")
                school = None
                if school_cb and school_cb.currentText() != "All Schools":
                    school = school_cb.currentText()
                results = GameDataLoader.search_spells(
                    query, system=system, school=school, book=book)
            elif category == "Monsters":
                cr_cb = page.findChild(QComboBox, "cr_combo")
                cr = None
                if cr_cb and cr_cb.currentText() != "All CR":
                    cr = cr_cb.currentText()
                results = GameDataLoader.search_monsters(
                    query, system=system, cr=cr, book=book)
            elif category == "Items":
                rarity_cb = page.findChild(QComboBox, "rarity_combo")
                rarity = None
                if rarity_cb and rarity_cb.currentText() != "All Rarities":
                    rarity = rarity_cb.currentText()
                results = GameDataLoader.search_items(
                    query, system=system, rarity=rarity, book=book)
            elif category == "Classes":
                results = GameDataLoader.search_classes(query, system=system, book=book)
            elif category == "Species":
                results = GameDataLoader.search_species(query, system=system, book=book)
            elif category == "Backgrounds":
                results = GameDataLoader.search_backgrounds(query, system=system, book=book)
            else:
                results = []
        except Exception as e:
            if count_lbl:
                count_lbl.setText(f"Error: {e}")
            return

        # Lazily populate book combo on first load
        if book_cb and book_cb.count() == 1:
            try:
                books = GameDataLoader.book_names(category, system)
                book_cb.blockSignals(True)
                book_cb.addItems(books)
                book_cb.blockSignals(False)
            except Exception:
                pass

        if model:
            model.reset_data(results, category)

        if count_lbl:
            count_lbl.setText(f"{len(results):,} entries")


# ── Campaign Gallery Tab ───────────────────────────────────────────────────────

class _CampaignGalleryTab(QWidget):
    """Inline gallery tab for a campaign — upload session photos with captions."""

    THUMB_W = 220
    THUMB_H = 165
    COLS    = 4

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx      = context
        self._svc      = context.services.try_get("campaign_service")
        self._campaign = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # ── toolbar ──────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("fieldLabel")
        toolbar.addWidget(self._count_lbl)
        toolbar.addStretch()
        add_btn = QPushButton("+ Add Photos")
        add_btn.setProperty("class", "primary")
        add_btn.clicked.connect(self._add_photos)
        toolbar.addWidget(add_btn)
        lay.addLayout(toolbar)
        lay.addWidget(_hline())

        # ── scrollable grid ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._grid_w = QWidget()
        self._grid   = QGridLayout(self._grid_w)
        self._grid.setSpacing(14)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._grid_w)
        lay.addWidget(scroll, stretch=1)

    # ── public ────────────────────────────────────────────────────────────────

    def load(self, campaign):
        self._campaign = campaign
        self._reload()

    # ── private ───────────────────────────────────────────────────────────────

    def _reload(self):
        # Clear grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._campaign or not self._svc:
            return

        images = self._svc.get_campaign_images(self._campaign.id)
        n = len(images)
        self._count_lbl.setText(
            f"{n} photo{'s' if n != 1 else ''}" if n else ""
        )

        if not images:
            placeholder = QLabel(
                'No photos yet — click  "+ Add Photos"  to upload session pictures.'
            )
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #606060; padding: 60px;")
            self._grid.addWidget(placeholder, 0, 0, 1, self.COLS)
            return

        for idx, img in enumerate(images):
            card = self._make_card(img)
            self._grid.addWidget(card, idx // self.COLS, idx % self.COLS)

    def _make_card(self, img: dict) -> QFrame:
        img_id     = img["id"]
        path       = img.get("image_path", "")
        caption    = img.get("caption", "") or ""
        zoom       = float(img.get("zoom",    1.0))
        fx         = float(img.get("focal_x", 0.5))
        fy         = float(img.get("focal_y", 0.5))
        is_primary = bool(img.get("is_primary", 0))

        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setFixedWidth(self.THUMB_W + 8)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(4, 4, 4, 8)
        lay.setSpacing(5)

        # ── thumbnail ─────────────────────────────────────────────────────────
        thumb = QLabel()
        thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setCursor(Qt.PointingHandCursor)

        if path and os.path.isfile(path):
            pix = focal_pixmap(QPixmap(path), self.THUMB_W, self.THUMB_H, zoom, fx, fy)
            thumb.setPixmap(pix)
            border_color = "#f0a020" if is_primary else "transparent"
            thumb.setStyleSheet(
                f"background: #111; border-radius: 4px; border: 2px solid {border_color};"
            )
            thumb.mousePressEvent = lambda _e, p=path: _ImageViewerDialog(p, self).exec()
        else:
            thumb.setText("File not found")
            thumb.setStyleSheet("color: #505050; background: #1a1a1a; border-radius: 4px;")
        lay.addWidget(thumb)

        # ── primary badge ─────────────────────────────────────────────────────
        if is_primary:
            badge = QLabel("★ Campaign Cover")
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "color: #f0a020; font-size: 11px; font-weight: 600;"
            )
            lay.addWidget(badge)

        # ── caption ───────────────────────────────────────────────────────────
        caption_edit = QLineEdit(caption)
        caption_edit.setPlaceholderText("Add a caption…")
        caption_edit.setStyleSheet("font-size: 12px;")
        caption_edit.setFixedWidth(self.THUMB_W)
        caption_edit.editingFinished.connect(
            lambda i=img_id, w=caption_edit: self._save_caption(i, w.text())
        )
        lay.addWidget(caption_edit)

        # ── action buttons ────────────────────────────────────────────────────
        btns = QHBoxLayout()
        btns.setSpacing(4)

        if not is_primary:
            cover_btn = QPushButton("Set Cover")
            cover_btn.setFixedHeight(24)
            cover_btn.setStyleSheet("font-size: 11px; padding: 0 6px;")
            cover_btn.clicked.connect(
                lambda _=False, p=path, z=zoom, fx_=fx, fy_=fy:
                    self._set_cover_with_crop(p, z, fx_, fy_)
            )
            btns.addWidget(cover_btn)

        crop_btn = QPushButton("Crop…")
        crop_btn.setFixedHeight(24)
        crop_btn.setStyleSheet("font-size: 11px; padding: 0 6px;")
        crop_btn.clicked.connect(
            lambda _=False, p=path, i=img_id, z=zoom, fx_=fx, fy_=fy:
                self._open_crop(p, i, z, fx_, fy_)
        )
        btns.addWidget(crop_btn)

        rm_btn = QPushButton("Remove")
        rm_btn.setFixedHeight(24)
        rm_btn.setStyleSheet("font-size: 11px; padding: 0 6px;")
        rm_btn.setProperty("class", "danger")
        rm_btn.clicked.connect(lambda _=False, i=img_id: self._remove(i))
        btns.addWidget(rm_btn)

        lay.addLayout(btns)
        return card

    # ── actions ───────────────────────────────────────────────────────────────

    def _add_photos(self):
        if not self._campaign or not self._svc:
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Session Photos", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if not files:
            return
        existing = {
            img["image_path"]
            for img in self._svc.get_campaign_images(self._campaign.id)
        }
        new_files = [f for f in files if f not in existing]
        for f in new_files:
            self._svc.add_campaign_image(self._campaign.id, f)

        # Auto-set cover if none exists yet
        if new_files and not self._campaign.cover_image_path:
            self._reload()
            imgs = self._svc.get_campaign_images(self._campaign.id)
            first = next((i for i in imgs if i["image_path"] == new_files[0]), None)
            if first:
                self._open_crop(
                    new_files[0], first["id"], 1.0, 0.5, 0.5,
                    set_cover_on_accept=True,
                )
        else:
            self._reload()

    def _open_crop(self, path: str, img_id: int,
                   zoom: float, fx: float, fy: float,
                   set_cover_on_accept: bool = False):
        if not path or not os.path.isfile(path):
            return
        dlg = PhotoCropDialog(
            path, self.THUMB_W, self.THUMB_H,
            zoom=zoom, fx=fx, fy=fy, parent=self
        )
        if dlg.exec() and self._svc:
            new_zoom, new_fx, new_fy = dlg.result()
            self._svc.update_campaign_image_crop(img_id, new_zoom, new_fx, new_fy)
            if set_cover_on_accept:
                self._svc.set_primary_campaign_image(
                    self._campaign.id, path, new_zoom, new_fx, new_fy
                )
                self._campaign.cover_image_path = path
        self._reload()

    def _set_cover_with_crop(self, path: str, zoom: float, fx: float, fy: float):
        if not path or not os.path.isfile(path) or not self._svc:
            return
        dlg = PhotoCropDialog(
            path, self.THUMB_W, self.THUMB_H,
            zoom=zoom, fx=fx, fy=fy, parent=self
        )
        if dlg.exec():
            new_zoom, new_fx, new_fy = dlg.result()
            self._svc.set_primary_campaign_image(
                self._campaign.id, path, new_zoom, new_fx, new_fy
            )
            self._campaign.cover_image_path = path
        self._reload()

    def _save_caption(self, img_id: int, text: str):
        if self._svc:
            self._svc.update_campaign_image_caption(img_id, text.strip())

    def _remove(self, img_id: int):
        if self._svc:
            self._svc.delete_campaign_image(img_id)
        self._reload()


# ── Campaign Detail View ───────────────────────────────────────────────────────

class CampaignDetailView(QWidget):
    def __init__(self, context, on_back, parent=None):
        super().__init__(parent)
        self._ctx      = context
        self._on_back  = on_back
        self._svc      = context.services.try_get("campaign_service")
        self._campaign = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        # ── Header bar ───────────────────────────────────────────────────────
        # Uses objectName "panelHeader" — styled entirely by global QSS.
        hdr = QWidget()
        hdr.setObjectName("panelHeader")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(16, 10, 16, 10); hl.setSpacing(12)

        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(80)
        back_btn.clicked.connect(self._on_back)
        hl.addWidget(back_btn)

        self._hdr_name   = QLabel(""); self._hdr_name.setObjectName("pageTitle")
        self._hdr_system = QLabel(""); self._hdr_system.setObjectName("headerSub")
        self._hdr_status = QLabel(""); self._hdr_status.setObjectName("headerStatus")

        hl.addWidget(self._hdr_name)
        hl.addWidget(self._hdr_system)
        hl.addStretch()
        hl.addWidget(self._hdr_status)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_campaign)
        hl.addWidget(edit_btn)

        export_btn = QPushButton("Export…")
        export_btn.setToolTip("Export this campaign to a Markdown file")
        export_btn.clicked.connect(self._export_campaign)
        hl.addWidget(export_btn)

        lay.addWidget(hdr)

        # ── Sub-tabs ──────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._overview_tab     = _OverviewTab(self._ctx)
        self._players_tab      = _PlayersTab(self._ctx)
        self._roster_tab       = _RosterTab(self._ctx)
        self._initiative_tab   = _InitiativeTab(self._ctx)
        self._encounter_tab    = _EncounterBuilderTab(self._ctx)
        self._battle_tab       = _BattleLogTab(self._ctx)
        self._chronicle_tab    = _ChronicleTab(self._ctx)
        self._gallery_tab      = _CampaignGalleryTab(self._ctx)
        self._assets_tab       = _AssetsTab(self._ctx)
        self._game_data_tab    = _GameDataTab(self._ctx)

        self._tabs.addTab(self._overview_tab,    "Overview")
        self._tabs.addTab(self._players_tab,     "Players")
        self._tabs.addTab(self._roster_tab,      "Roster")
        self._tabs.addTab(self._initiative_tab,  "⚔ Initiative")
        self._tabs.addTab(self._encounter_tab,   "Encounters")
        self._tabs.addTab(self._battle_tab,      "Battle Log")
        self._tabs.addTab(self._chronicle_tab,   "Chronicle")
        self._tabs.addTab(self._gallery_tab,     "📷 Gallery")
        self._tabs.addTab(self._assets_tab,      "Assets")
        self._tabs.addTab(self._game_data_tab,   "Game Data")

        lay.addWidget(self._tabs, stretch=1)

    def load(self, campaign: Campaign):
        self._campaign = campaign
        self._hdr_name.setText(campaign.name)
        self._hdr_system.setText(campaign.game_system)
        self._hdr_status.setText(campaign.status)
        self._overview_tab.load(campaign)
        self._players_tab.load(campaign)
        self._roster_tab.load(campaign)
        self._initiative_tab.load(campaign)
        self._encounter_tab.load(campaign)
        self._battle_tab.load(campaign)
        self._chronicle_tab.load(campaign)
        self._gallery_tab.load(campaign)
        self._assets_tab.load(campaign)

    def _edit_campaign(self):
        if not self._campaign: return
        dlg = CampaignDialog(self._ctx, self._campaign, parent=self)
        if dlg.exec():
            self._campaign = dlg.result_campaign()
            self.load(self._campaign)

    def _export_campaign(self):
        if not self._campaign: return
        svc = self._ctx.services.try_get("campaign_service")
        if not svc: return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Campaign", f"{self._campaign.name}.md",
            "Markdown (*.md);;Text Files (*.txt);;All Files (*)")
        if not path: return

        lines = []
        c = self._campaign

        lines += [f"# {c.name}", ""]
        lines += [f"**Game System:** {c.game_system}  |  **Status:** {c.status}"]
        if c.start_date: lines.append(f"**Started:** {c.start_date}")
        lines.append("")

        if c.description:
            lines += ["## Description", "", c.description, ""]
        if c.notes:
            lines += ["## Campaign Notes", "", c.notes, ""]

        # Players
        players = svc.get_players(c.id)
        if players:
            lines += ["## Players", ""]
            for p in players:
                lines.append(f"- **{p.player_name}** — {p.role}"
                             + (f"  _{p.notes}_" if p.notes else ""))
            lines.append("")

        # Roster
        characters = svc.get_characters(c.id)
        if characters:
            lines += ["## Roster", ""]
            by_role: dict[str, list] = {}
            for ch in characters:
                by_role.setdefault(ch.character_role, []).append(ch)
            for role, chars in by_role.items():
                lines += [f"### {role}s", ""]
                for ch in chars:
                    hp_str = f"HP {ch.hit_points}/{ch.max_hit_points}" if ch.max_hit_points else ""
                    ac_str = f"AC {ch.armor_class}" if ch.armor_class else ""
                    lvl_str = f"Level {ch.level}" if ch.level > 0 else ""
                    meta = "  ·  ".join(filter(None, [ch.character_class, ch.race, lvl_str, hp_str, ac_str]))
                    status_str = f" _({ch.status})_" if ch.status != "Active" else ""
                    lines.append(f"- **{ch.name}**{status_str}" + (f" — {meta}" if meta else ""))
                    if ch.background:
                        lines.append(f"  > {ch.background[:200]}")
                    if ch.notes:
                        lines.append(f"  > _{ch.notes[:200]}_")
                lines.append("")

        # Battle log
        battles = svc.get_battles(c.id)
        if battles:
            lines += ["## Battle Log", ""]
            player_map = {p.id: p.player_name for p in players}
            for b in battles:
                outcome_str = f"**{b.outcome}**"
                date_str = f"_{b.date_played}_  " if b.date_played else ""
                loc_str = f"📍 {b.location_name}  " if b.location_name else ""
                lines += [f"### #{b.session_number} — {b.title}  ({outcome_str})", ""]
                lines.append(f"{date_str}{loc_str}")
                if b.scenario_name:
                    lines.append(f"*Scenario:* {b.scenario_name}")
                parts = svc.get_participants(b.id)
                if parts:
                    p_names = [player_map.get(p.player_id, "?") for p in parts]
                    lines.append(f"*Participants:* {', '.join(p_names)}")
                if b.scoring_notes:
                    lines += ["", f"**Scoring:** {b.scoring_notes}"]
                if b.chronicle_text:
                    lines += ["", b.chronicle_text]
                lines.append("")

        # Chronicle
        entries = svc.get_journal_entries(c.id)
        if entries:
            lines += ["## Chronicle", ""]
            for e in reversed(entries):
                date = (e.created_at or "")[:10]
                lines += [f"### {e.title}  _{date}_", "", e.content, ""]

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            _show_toast(self, f"✓  Campaign exported to {Path(path).name}")
        except Exception as ex:
            _show_toast(self, f"✕  Export failed: {ex}", "toastError")


# ── Overview tab ──────────────────────────────────────────────────────────────

class _OverviewTab(QWidget):
    def __init__(self, context):
        super().__init__()
        self._ctx = context
        self._svc = context.services.try_get("campaign_service")
        self._campaign = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(20,16,20,16); lay.setSpacing(14)

        # Stat chips row
        chips_row = QHBoxLayout(); chips_row.setSpacing(10)
        self._chip_battles   = _stat_chip("Battles", "0")
        self._chip_victories = _stat_chip("Victories", "0", "#3dba6e")
        self._chip_defeats   = _stat_chip("Defeats",   "0", "#e05555")
        self._chip_chars     = _stat_chip("Characters", "0", "#f0a020")
        self._chip_players   = _stat_chip("Players",   "0", "#909090")
        for c in [self._chip_battles, self._chip_victories, self._chip_defeats,
                  self._chip_chars, self._chip_players]:
            chips_row.addWidget(c)
        chips_row.addStretch()
        lay.addLayout(chips_row)

        lay.addWidget(_hline())

        # Two-column layout below
        cols = QHBoxLayout(); cols.setSpacing(16)

        # ── Recent battles ────────────────────────────────────────────────────
        left = QVBoxLayout()
        lbl = QLabel("Recent Sessions / Battles")
        lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #d8d8d8;")
        left.addWidget(lbl)
        self._recent_list = QListWidget(); self._recent_list.setAlternatingRowColors(True)
        self._recent_list.setMaximumHeight(260)
        left.addWidget(self._recent_list)
        left.addStretch()
        cols.addLayout(left, stretch=1)

        # ── Campaign notes ────────────────────────────────────────────────────
        right = QVBoxLayout()
        note_lbl = QLabel("Campaign Notes")
        note_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #d8d8d8;")
        right.addWidget(note_lbl)
        self._notes_view = QTextEdit()
        self._notes_view.setReadOnly(False)
        self._notes_view.setPlaceholderText("No campaign notes yet…")
        right.addWidget(self._notes_view, stretch=1)

        save_notes = QPushButton("Save Notes")
        save_notes.setProperty("class", "primary")
        save_notes.clicked.connect(self._save_notes)
        right.addWidget(save_notes, alignment=Qt.AlignRight)
        cols.addLayout(right, stretch=1)

        lay.addLayout(cols, stretch=1)

    def load(self, campaign: Campaign):
        self._campaign = campaign
        if not self._svc: return

        battles    = self._svc.get_battles(campaign.id)
        characters = self._svc.get_characters(campaign.id)
        players    = self._svc.get_players(campaign.id)

        victories = sum(1 for b in battles if b.outcome == "Victory")
        defeats   = sum(1 for b in battles if b.outcome == "Defeat")

        self._chip_battles.findChild(QLabel).setText(str(len(battles)))
        # Find value labels (first child QLabel per chip)
        def _set_chip(chip, val):
            for lbl in chip.findChildren(QLabel):
                if lbl.objectName() != "fieldLabel":
                    lbl.setText(str(val)); break

        _set_chip(self._chip_battles,   len(battles))
        _set_chip(self._chip_victories, victories)
        _set_chip(self._chip_defeats,   defeats)
        _set_chip(self._chip_chars,     len(characters))
        _set_chip(self._chip_players,   len(players))

        self._recent_list.clear()
        for b in reversed(battles[-5:]):
            item = QListWidgetItem(f"#{b.session_number}  {b.title}  —  {b.outcome}")
            color = OUTCOME_COLORS.get(b.outcome, "#808080")
            item.setForeground(QColor(color))
            self._recent_list.addItem(item)

        self._notes_view.setPlainText(campaign.notes or "")

    def _save_notes(self):
        if not self._campaign or not self._svc: return
        self._svc.update_campaign(self._campaign.id, notes=self._notes_view.toPlainText().strip() or None)
        self._campaign.notes = self._notes_view.toPlainText().strip() or None


# ── Players tab ───────────────────────────────────────────────────────────────

class _PlayersTab(QWidget):
    def __init__(self, context):
        super().__init__()
        self._ctx = context
        self._svc = context.services.try_get("campaign_service")
        self._campaign = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(20,16,20,16); lay.setSpacing(10)

        action_row = QHBoxLayout()
        add_btn = QPushButton("+ Add Player"); add_btn.setProperty("class", "primary")
        add_btn.clicked.connect(self._add_player)
        action_row.addWidget(add_btn); action_row.addStretch()
        lay.addLayout(action_row)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Player Name", "Role", "Notes"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self._table, stretch=1)

        btn_row = QHBoxLayout()
        edit_btn = QPushButton("Edit Selected"); edit_btn.clicked.connect(self._edit_player)
        rem_btn  = QPushButton("Remove Selected"); rem_btn.setProperty("class", "danger")
        rem_btn.clicked.connect(self._remove_player)
        btn_row.addWidget(edit_btn); btn_row.addWidget(rem_btn); btn_row.addStretch()
        lay.addLayout(btn_row)

    def load(self, campaign: Campaign):
        self._campaign = campaign
        self._refresh()

    def _refresh(self):
        self._table.setRowCount(0)
        if not self._svc or not self._campaign: return
        for p in self._svc.get_players(self._campaign.id):
            row = self._table.rowCount(); self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(p.player_name))
            self._table.setItem(row, 1, QTableWidgetItem(p.role))
            self._table.setItem(row, 2, QTableWidgetItem(p.notes or ""))
            self._table.item(row, 0).setData(Qt.UserRole, p.id)

    def _add_player(self):
        name, ok = _simple_input(self, "Add Player", "Player name:")
        if not ok or not name.strip(): return
        role_opts = PLAYER_ROLES
        role, ok2 = _simple_choice(self, "Player Role", "Select role:", role_opts)
        if not ok2: return
        self._svc.add_player(self._campaign.id, name.strip(), role)
        self._refresh()

    def _edit_player(self):
        row = self._table.currentRow()
        if row < 0: return
        pid = self._table.item(row, 0).data(Qt.UserRole)
        p = self._svc.repo.get_player(pid)
        if not p: return
        name, ok = _simple_input(self, "Edit Player", "Player name:", p.player_name)
        if not ok: return
        role, ok2 = _simple_choice(self, "Player Role", "Select role:", PLAYER_ROLES, p.role)
        if not ok2: return
        self._svc.update_player(pid, name.strip(), role)
        self._refresh()

    def _remove_player(self):
        row = self._table.currentRow()
        if row < 0: return
        pid = self._table.item(row, 0).data(Qt.UserRole)
        name = self._table.item(row, 0).text()
        if QMessageBox.question(self, "Remove Player", f"Remove '{name}'?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self._svc.delete_player(pid)
        self._refresh()


def _simple_input(parent, title, prompt, default="") -> tuple[str, bool]:
    dlg = QDialog(parent); dlg.setWindowTitle(title); dlg.setMinimumWidth(320)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(prompt))
    edit = QLineEdit(default)
    lay.addWidget(edit)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)
    ok = dlg.exec() == QDialog.Accepted
    return edit.text(), ok

def _simple_choice(parent, title, prompt, options, default="") -> tuple[str, bool]:
    dlg = QDialog(parent); dlg.setWindowTitle(title); dlg.setMinimumWidth(320)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(prompt))
    combo = QComboBox(); combo.addItems(options)
    if default in options: combo.setCurrentText(default)
    lay.addWidget(combo)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)
    ok = dlg.exec() == QDialog.Accepted
    return combo.currentText(), ok


# ── Character Sheet Dialog ────────────────────────────────────────────────────

class CharacterSheetDialog(QDialog):
    """Full editable character sheet — Overview, Spells, Inventory."""

    def __init__(self, context, character: Character, parent=None):
        super().__init__(parent)
        self._ctx  = context
        self._svc  = context.services.try_get("campaign_service")
        self._char = character
        self.setWindowTitle(f"{character.name} — Character Sheet")
        self.setMinimumSize(720, 560)
        self.resize(900, 660)
        self._build_ui()
        self._load()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header strip — styled by global QSS via objectName "panelHeader".
        hdr = QWidget()
        hdr.setObjectName("panelHeader")
        hdr.setFixedHeight(56)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)

        self._hdr_name = QLabel(self._char.name)
        self._hdr_name.setObjectName("pageTitle")
        hl.addWidget(self._hdr_name)

        color = CHARACTER_ROLE_COLORS.get(self._char.character_role, "#686868")
        role_lbl = QLabel(self._char.character_role)
        role_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 600;"
            f" background: {color}18; border: 1px solid {color}40;"
            f" border-radius: 4px; padding: 3px 10px;"
        )
        hl.addWidget(role_lbl)
        hl.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        hl.addWidget(close_btn)
        lay.addWidget(hdr)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        lay.addWidget(self._tabs, stretch=1)

        self._tabs.addTab(self._build_overview_tab(),  "Overview")
        self._tabs.addTab(self._build_spells_tab(),    "Spells")
        self._tabs.addTab(self._build_inventory_tab(), "Inventory")

    # ── Overview tab ──────────────────────────────────────────────────────────

    def _build_overview_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)

        # ── Core stats row ────────────────────────────────────────────────────
        core_box = QGroupBox("Core")
        cl = QGridLayout(core_box)
        cl.setSpacing(10)

        def _field_pair(label, widget, row, col):
            cl.addWidget(QLabel(label), row, col * 2)
            cl.addWidget(widget, row, col * 2 + 1)

        self._xp_spin = QSpinBox(); self._xp_spin.setRange(0, 9_999_999)
        self._hp_spin = QSpinBox(); self._hp_spin.setRange(0, 9999)
        self._maxhp_spin = QSpinBox(); self._maxhp_spin.setRange(0, 9999)
        self._ac_spin = QSpinBox(); self._ac_spin.setRange(0, 99)
        self._speed_spin = QSpinBox(); self._speed_spin.setRange(0, 999); self._speed_spin.setSuffix(" ft")
        self._init_spin = QSpinBox(); self._init_spin.setRange(-20, 20)
        self._prof_spin = QSpinBox(); self._prof_spin.setRange(2, 9)
        self._insp_check = QPushButton("Inspiration")
        self._insp_check.setCheckable(True)
        self._insp_check.setFixedHeight(28)

        _field_pair("Experience",  self._xp_spin,    0, 0)
        _field_pair("Hit Points",  self._hp_spin,     0, 1)
        _field_pair("Max HP",      self._maxhp_spin,  0, 2)
        _field_pair("Armor Class", self._ac_spin,     1, 0)
        _field_pair("Speed",       self._speed_spin,  1, 1)
        _field_pair("Initiative",  self._init_spin,   1, 2)
        _field_pair("Proficiency", self._prof_spin,   2, 0)
        cl.addWidget(self._insp_check, 2, 2, 1, 2)

        lay.addWidget(core_box)

        # ── Death Saves ───────────────────────────────────────────────────────
        ds_box = QGroupBox("Death Saves")
        dl = QHBoxLayout(ds_box)
        dl.setSpacing(20)

        def _save_row(label: str, count: int) -> tuple[QHBoxLayout, list[QPushButton]]:
            row = QHBoxLayout(); row.setSpacing(6)
            row.addWidget(QLabel(label))
            btns = []
            for _ in range(3):
                b = QPushButton()
                b.setCheckable(True)
                b.setFixedSize(22, 22)
                b.setStyleSheet("""
                    QPushButton { background: #2a2a2a; border: 1px solid #444; border-radius: 11px; }
                    QPushButton:checked { background: #3dba6e; border-color: #3dba6e; }
                """)
                btns.append(b)
                row.addWidget(b)
            return row, btns

        suc_row, self._ds_success = _save_row("Successes", 3)
        fail_row, self._ds_failure = _save_row("Failures",  3)
        # style failures red
        for b in self._ds_failure:
            b.setStyleSheet("""
                QPushButton { background: #2a2a2a; border: 1px solid #444; border-radius: 11px; }
                QPushButton:checked { background: #e05555; border-color: #e05555; }
            """)

        dl.addLayout(suc_row)
        dl.addLayout(fail_row)
        dl.addStretch()
        lay.addWidget(ds_box)

        # ── Currency ──────────────────────────────────────────────────────────
        cur_box = QGroupBox("Currency")
        cur_l = QHBoxLayout(cur_box)
        cur_l.setSpacing(12)
        self._currency_spins = {}
        for label, key in [("CP", "cp"), ("SP", "sp"), ("EP", "ep"), ("GP", "gp"), ("PP", "pp")]:
            col = QVBoxLayout(); col.setSpacing(3)
            spin = QSpinBox(); spin.setRange(0, 9_999_999)
            spin.setAlignment(Qt.AlignCenter)
            lbl = QLabel(label); lbl.setAlignment(Qt.AlignCenter)
            lbl.setObjectName("fieldLabel")
            col.addWidget(spin); col.addWidget(lbl)
            cur_l.addLayout(col)
            self._currency_spins[key] = spin
        lay.addWidget(cur_box)

        # ── Traits / Notes ────────────────────────────────────────────────────
        traits_box = QGroupBox("Traits & Features")
        tl = QVBoxLayout(traits_box)
        self._traits_edit = QTextEdit()
        self._traits_edit.setPlaceholderText("Personality traits, ideals, bonds, flaws, special features…")
        self._traits_edit.setMinimumHeight(80)
        tl.addWidget(self._traits_edit)
        lay.addWidget(traits_box)

        notes_box = QGroupBox("Notes")
        nl = QVBoxLayout(notes_box)
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Session notes, backstory, DM notes…")
        self._notes_edit.setMinimumHeight(80)
        nl.addWidget(self._notes_edit)
        lay.addWidget(notes_box)

        # Save button
        save_btn = QPushButton("Save Changes")
        save_btn.setProperty("class", "primary")
        save_btn.clicked.connect(self._save_overview)
        lay.addWidget(save_btn, alignment=Qt.AlignRight)

        scroll.setWidget(w)
        return scroll

    # ── Spells tab ────────────────────────────────────────────────────────────

    def _build_spells_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # Spell slots
        slots_box = QGroupBox("Spell Slots")
        slots_l = QHBoxLayout(slots_box)
        slots_l.setSpacing(10)
        self._slot_widgets: dict[int, tuple[QSpinBox, QSpinBox]] = {}
        for lvl in range(1, 10):
            col = QVBoxLayout(); col.setSpacing(3)
            lbl = QLabel(f"Lvl {lvl}"); lbl.setAlignment(Qt.AlignCenter)
            lbl.setObjectName("fieldLabel")
            used = QSpinBox(); used.setRange(0, 20); used.setFixedWidth(52)
            max_ = QSpinBox(); max_.setRange(0, 20); max_.setFixedWidth(52)
            div  = QLabel("/ "); div.setAlignment(Qt.AlignCenter)
            div.setStyleSheet("color: #555; font-size: 11px;")
            inner = QHBoxLayout(); inner.setSpacing(2)
            inner.addWidget(used); inner.addWidget(div); inner.addWidget(max_)
            col.addWidget(lbl); col.addLayout(inner)
            slots_l.addLayout(col)
            self._slot_widgets[lvl] = (used, max_)
        save_slots_btn = QPushButton("Save Slots")
        save_slots_btn.clicked.connect(self._save_slots)
        save_slots_btn.setFixedWidth(90)
        slots_l.addWidget(save_slots_btn)
        lay.addWidget(slots_box)

        # Known spells list + browse
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Known Spells"))
        top_row.addStretch()
        browse_btn = QPushButton("Browse Spells…")
        browse_btn.clicked.connect(self._browse_spells)
        add_custom_btn = QPushButton("+ Add Manually")
        add_custom_btn.clicked.connect(lambda: self._add_spell_manually())
        top_row.addWidget(browse_btn)
        top_row.addWidget(add_custom_btn)
        lay.addLayout(top_row)

        self._spell_table = QTableWidget(0, 5)
        self._spell_table.setHorizontalHeaderLabels(
            ["Spell Name", "Level", "School/Notes", "Prepared", "Ritual"])
        h = self._spell_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._spell_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._spell_table.setAlternatingRowColors(True)
        self._spell_table.verticalHeader().setVisible(False)
        self._spell_table.setShowGrid(False)
        self._spell_table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self._spell_table, stretch=1)

        del_btn = QPushButton("Remove Selected")
        del_btn.setProperty("class", "danger")
        del_btn.clicked.connect(self._remove_spell)
        lay.addWidget(del_btn, alignment=Qt.AlignLeft)

        return w

    # ── Inventory tab ─────────────────────────────────────────────────────────

    def _build_inventory_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Inventory"))
        top_row.addStretch()
        browse_items_btn = QPushButton("Browse Items…")
        browse_items_btn.clicked.connect(self._browse_items)
        add_item_btn = QPushButton("+ Add Item")
        add_item_btn.setProperty("class", "primary")
        add_item_btn.clicked.connect(lambda: self._add_edit_item())
        top_row.addWidget(browse_items_btn)
        top_row.addWidget(add_item_btn)
        lay.addLayout(top_row)

        self._inv_table = QTableWidget(0, 6)
        self._inv_table.setHorizontalHeaderLabels(
            ["Item", "Type", "Qty", "Weight", "Value (gp)", "Equipped"])
        h = self._inv_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._inv_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._inv_table.setAlternatingRowColors(True)
        self._inv_table.verticalHeader().setVisible(False)
        self._inv_table.setShowGrid(False)
        self._inv_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._inv_table.doubleClicked.connect(
            lambda: self._add_edit_item(self._selected_item_id()))
        lay.addWidget(self._inv_table, stretch=1)

        # Summary row
        self._inv_summary = QLabel("")
        self._inv_summary.setStyleSheet("color: #606060; font-size: 11px;")
        lay.addWidget(self._inv_summary)

        btn_row = QHBoxLayout()
        edit_btn = QPushButton("Edit Selected")
        edit_btn.clicked.connect(lambda: self._add_edit_item(self._selected_item_id()))
        del_btn = QPushButton("Remove Selected")
        del_btn.setProperty("class", "danger")
        del_btn.clicked.connect(self._remove_item)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        return w

    # ── Load data ─────────────────────────────────────────────────────────────

    def _load(self):
        ch = self._char
        # Overview
        self._xp_spin.setValue(ch.experience_points or 0)
        self._hp_spin.setValue(ch.hit_points)
        self._maxhp_spin.setValue(ch.max_hit_points)
        self._ac_spin.setValue(ch.armor_class)
        # speed / init / proficiency not stored yet — default
        self._speed_spin.setValue(30)
        self._init_spin.setValue(0)
        self._prof_spin.setValue(max(2, 2 + (ch.level - 1) // 4))
        # Death saves
        for i, btn in enumerate(self._ds_success):
            btn.setChecked(bool(ch.death_saves_success & (1 << i)))
        for i, btn in enumerate(self._ds_failure):
            btn.setChecked(bool(ch.death_saves_failure & (1 << i)))
        # Currency
        cur = ch.currency
        for key, spin in self._currency_spins.items():
            spin.setValue(cur.get(key, 0))
        # Traits / notes
        self._traits_edit.setPlainText(ch.traits or "")
        self._notes_edit.setPlainText(ch.notes or "")
        # Spell slots
        slots = ch.spell_slots
        for lvl, (used, max_) in self._slot_widgets.items():
            s = slots.get(str(lvl), {})
            used.setValue(s.get("used", 0))
            max_.setValue(s.get("max", 0))
        # Spells
        self._refresh_spells()
        # Inventory
        self._refresh_inventory()

    # ── Save overview ─────────────────────────────────────────────────────────

    def _save_overview(self):
        if not self._svc:
            return
        ds_suc = sum(1 << i for i, b in enumerate(self._ds_success) if b.isChecked())
        ds_fail = sum(1 << i for i, b in enumerate(self._ds_failure) if b.isChecked())
        import json
        cur_data = {k: s.value() for k, s in self._currency_spins.items()}
        self._svc.update_character(
            self._char.id,
            hit_points=self._hp_spin.value(),
            max_hit_points=self._maxhp_spin.value(),
            armor_class=self._ac_spin.value(),
            experience_points=self._xp_spin.value(),
            death_saves_success=ds_suc,
            death_saves_failure=ds_fail,
            currency_json=json.dumps(cur_data),
            traits=self._traits_edit.toPlainText().strip() or None,
            notes=self._notes_edit.toPlainText().strip() or None,
        )
        self._char = self._svc.get_character(self._char.id)
        _show_toast(self, "✓  Character sheet saved")

    def _save_slots(self):
        if not self._svc:
            return
        import json
        slots = {}
        for lvl, (used, max_) in self._slot_widgets.items():
            if max_.value() > 0:
                slots[str(lvl)] = {"used": used.value(), "max": max_.value()}
        self._svc.update_character(self._char.id, spell_slots_json=json.dumps(slots))
        self._char = self._svc.get_character(self._char.id)

    # ── Spells ────────────────────────────────────────────────────────────────

    def _refresh_spells(self):
        if not self._svc:
            return
        self._spell_table.setRowCount(0)
        for spell in self._svc.get_character_spells(self._char.id):
            row = self._spell_table.rowCount()
            self._spell_table.insertRow(row)
            name_item = QTableWidgetItem(spell.spell_name)
            name_item.setData(Qt.UserRole, spell.id)
            self._spell_table.setItem(row, 0, name_item)
            lvl_text = "Cantrip" if spell.spell_level == 0 else str(spell.spell_level)
            lvl_item = QTableWidgetItem(lvl_text)
            lvl_item.setTextAlignment(Qt.AlignCenter)
            self._spell_table.setItem(row, 1, lvl_item)
            self._spell_table.setItem(row, 2, QTableWidgetItem(spell.notes or ""))
            prep_item = QTableWidgetItem("✓" if spell.is_prepared else "")
            prep_item.setTextAlignment(Qt.AlignCenter)
            self._spell_table.setItem(row, 3, prep_item)
            rit_item = QTableWidgetItem("✓" if spell.is_ritual else "")
            rit_item.setTextAlignment(Qt.AlignCenter)
            self._spell_table.setItem(row, 4, rit_item)

    def _add_spell_manually(self, prefill_name: str = "", prefill_level: int = 0):
        dlg = _AddSpellDialog(prefill_name=prefill_name,
                              prefill_level=prefill_level, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, level, prepared, ritual, notes = dlg.values()
        if self._svc:
            self._svc.add_character_spell(
                self._char.id, name, spell_level=level,
                is_prepared=prepared, is_ritual=ritual, notes=notes)
        self._refresh_spells()

    def _browse_spells(self):
        dlg = _GameDataBrowserDialog("Spells", parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_name:
            self._add_spell_manually(prefill_name=dlg.selected_name)

    def _remove_spell(self):
        row = self._spell_table.currentRow()
        if row < 0:
            return
        spell_id = self._spell_table.item(row, 0).data(Qt.UserRole)
        if self._svc:
            self._svc.delete_character_spell(spell_id)
        self._refresh_spells()

    # ── Inventory ─────────────────────────────────────────────────────────────

    def _refresh_inventory(self):
        if not self._svc:
            return
        items = self._svc.get_inventory(self._char.id)
        self._inv_table.setRowCount(0)
        total_weight = 0.0
        total_value = 0.0
        for item in items:
            row = self._inv_table.rowCount()
            self._inv_table.insertRow(row)
            name_item = QTableWidgetItem(item.name)
            name_item.setData(Qt.UserRole, item.id)
            if item.equipped:
                name_item.setForeground(QColor("#3b9eff"))
            self._inv_table.setItem(row, 0, name_item)
            self._inv_table.setItem(row, 1, QTableWidgetItem(item.item_type or ""))
            qty = QTableWidgetItem(str(item.quantity))
            qty.setTextAlignment(Qt.AlignCenter)
            self._inv_table.setItem(row, 2, qty)
            wt = QTableWidgetItem(f"{item.weight:.1f}" if item.weight else "—")
            wt.setTextAlignment(Qt.AlignCenter)
            self._inv_table.setItem(row, 3, wt)
            val = QTableWidgetItem(f"{item.value_gp:.2f}" if item.value_gp else "—")
            val.setTextAlignment(Qt.AlignCenter)
            self._inv_table.setItem(row, 4, val)
            eq = QTableWidgetItem("✓" if item.equipped else "")
            eq.setTextAlignment(Qt.AlignCenter)
            self._inv_table.setItem(row, 5, eq)
            total_weight += item.weight * item.quantity
            total_value += item.value_gp * item.quantity
        self._inv_summary.setText(
            f"Total weight: {total_weight:.1f} lb  ·  Total value: {total_value:.2f} gp"
            f"  ·  {len(items)} items"
        )

    def _selected_item_id(self):
        row = self._inv_table.currentRow()
        if row < 0:
            return None
        return self._inv_table.item(row, 0).data(Qt.UserRole)

    def _add_edit_item(self, item_id=None):
        item = None
        if item_id and self._svc:
            items = self._svc.get_inventory(self._char.id)
            item = next((i for i in items if i.id == item_id), None)
        dlg = _InventoryItemDialog(item=item, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.values()
        if self._svc:
            if item:
                for k, v in data.items():
                    setattr(item, k, v)
                self._svc.update_inventory_item(item)
            else:
                self._svc.add_inventory_item(self._char.id, **data)
        self._refresh_inventory()

    def _browse_items(self):
        dlg = _GameDataBrowserDialog("Items", parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_name:
            # Pre-fill item dialog with name from browser
            item_data = GameDataLoader.search_items(dlg.selected_name, limit=1)
            prefill = None
            if item_data:
                props = item_data[0].get("properties", {})
                prefill = InventoryItem(
                    character_id=self._char.id,
                    name=item_data[0].get("name", dlg.selected_name),
                    item_type=props.get("Item Type", ""),
                )
            dlg2 = _InventoryItemDialog(item=prefill, parent=self)
            if dlg2.exec() == QDialog.Accepted and self._svc:
                self._svc.add_inventory_item(self._char.id, **dlg2.values())
            self._refresh_inventory()

    def _remove_item(self):
        item_id = self._selected_item_id()
        if not item_id:
            return
        if self._svc:
            self._svc.delete_inventory_item(item_id)
        self._refresh_inventory()


# ── Add Spell dialog ──────────────────────────────────────────────────────────

class _AddSpellDialog(QDialog):
    def __init__(self, prefill_name: str = "", prefill_level: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Spell")
        self.setFixedWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel("Spell Name"))
        self._name = QLineEdit(prefill_name)
        lay.addWidget(self._name)

        row = QHBoxLayout()
        lv_col = QVBoxLayout()
        lv_col.addWidget(QLabel("Level (0 = Cantrip)"))
        self._level = QSpinBox(); self._level.setRange(0, 9)
        self._level.setValue(prefill_level)
        lv_col.addWidget(self._level)
        row.addLayout(lv_col)

        flag_col = QVBoxLayout()
        self._prepared = QPushButton("Prepared"); self._prepared.setCheckable(True)
        self._ritual   = QPushButton("Ritual");   self._ritual.setCheckable(True)
        flag_col.addWidget(self._prepared)
        flag_col.addWidget(self._ritual)
        row.addLayout(flag_col)
        lay.addLayout(row)

        lay.addWidget(QLabel("Notes / School"))
        self._notes = QLineEdit()
        self._notes.setPlaceholderText("e.g. Evocation, from Ring of Spell Storing…")
        lay.addWidget(self._notes)

        btns = QHBoxLayout()
        ok = QPushButton("Add"); ok.setProperty("class", "primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(ok)
        lay.addLayout(btns)

    def values(self):
        return (self._name.text().strip(), self._level.value(),
                self._prepared.isChecked(), self._ritual.isChecked(),
                self._notes.text().strip() or None)


# ── Inventory item dialog ─────────────────────────────────────────────────────

class _InventoryItemDialog(QDialog):
    TYPES = ["", "Weapon", "Armor", "Shield", "Gear", "Tool",
             "Magic Item", "Consumable", "Valuables", "Other"]

    def __init__(self, item: InventoryItem = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Item" if item is None else "Edit Item")
        self.setFixedWidth(400)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel("Name"))
        self._name = QLineEdit(item.name if item else "")
        lay.addWidget(self._name)

        lay.addWidget(QLabel("Type"))
        self._type = QComboBox()
        self._type.addItems(self.TYPES)
        if item and item.item_type:
            idx = self._type.findText(item.item_type)
            if idx >= 0: self._type.setCurrentIndex(idx)
        lay.addWidget(self._type)

        grid = QGridLayout()
        grid.addWidget(QLabel("Quantity"), 0, 0)
        self._qty = QSpinBox(); self._qty.setRange(1, 9999)
        self._qty.setValue(item.quantity if item else 1)
        grid.addWidget(self._qty, 0, 1)

        grid.addWidget(QLabel("Weight (lb)"), 0, 2)
        self._weight = QSpinBox(); self._weight.setRange(0, 9999)
        self._weight.setValue(int(item.weight) if item else 0)
        grid.addWidget(self._weight, 0, 3)

        grid.addWidget(QLabel("Value (gp)"), 1, 0)
        self._value = QSpinBox(); self._value.setRange(0, 9_999_999)
        self._value.setValue(int(item.value_gp) if item else 0)
        grid.addWidget(self._value, 1, 1)

        self._equipped = QPushButton("Equipped")
        self._equipped.setCheckable(True)
        self._equipped.setChecked(item.equipped if item else False)
        grid.addWidget(self._equipped, 1, 2, 1, 2)
        lay.addLayout(grid)

        lay.addWidget(QLabel("Description"))
        self._desc = QTextEdit()
        self._desc.setPlaceholderText("Item description, effects, attunement requirements…")
        self._desc.setFixedHeight(70)
        self._desc.setPlainText(item.description or "" if item else "")
        lay.addWidget(self._desc)

        btns = QHBoxLayout()
        ok = QPushButton("Save"); ok.setProperty("class", "primary")
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(ok)
        lay.addLayout(btns)

    def _accept(self):
        if not self._name.text().strip():
            self._name.setPlaceholderText("Name is required!")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "name":        self._name.text().strip(),
            "item_type":   self._type.currentText() or None,
            "quantity":    self._qty.value(),
            "weight":      float(self._weight.value()),
            "value_gp":    float(self._value.value()),
            "equipped":    self._equipped.isChecked(),
            "description": self._desc.toPlainText().strip() or None,
        }


# ── Game Data Browser Dialog ──────────────────────────────────────────────

class _GameDataBrowserDialog(QDialog):
    """Search and select a spell, monster or item from JSON data files."""

    _HEADERS = {
        "Spells":   ["Name", "Level · School", "Components", "Book"],
        "Monsters": ["Name", "CR · Type · Size", "Alignment", "Book"],
        "Items":    ["Name", "Type", "Rarity", "Book"],
    }

    def __init__(self, data_type: str = "Spells", parent=None):
        super().__init__(parent)
        self._data_type = data_type
        self.selected_name: str = ""
        self._model = _GameDataModel(
            self._HEADERS.get(data_type, ["Name", "Detail", "", "Book"]))
        self.setWindowTitle(f"Browse {data_type}")
        self.setMinimumSize(640, 500)
        self.resize(820, 600)
        self._build_ui()
        self._search("")

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        # ─ Filter row ────────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(f"Search {self._data_type.lower()}…")
        self._search_edit.textChanged.connect(self._search)
        top.addWidget(self._search_edit, stretch=2)

        if self._data_type == "Spells":
            self._school_combo = QComboBox()
            self._school_combo.addItem("All Schools")
            try:
                self._school_combo.addItems(GameDataLoader.spell_schools())
            except Exception:
                pass
            self._school_combo.currentTextChanged.connect(
                lambda _: self._search(self._search_edit.text()))
            top.addWidget(self._school_combo)
        elif self._data_type == "Monsters":
            self._cr_combo = QComboBox()
            self._cr_combo.addItem("All CR")
            try:
                self._cr_combo.addItems(GameDataLoader.challenge_ratings())
            except Exception:
                pass
            self._cr_combo.currentTextChanged.connect(
                lambda _: self._search(self._search_edit.text()))
            top.addWidget(self._cr_combo)
        elif self._data_type == "Items":
            self._rarity_combo = QComboBox()
            self._rarity_combo.addItem("All Rarities")
            try:
                self._rarity_combo.addItems(GameDataLoader.item_rarities())
            except Exception:
                pass
            self._rarity_combo.currentTextChanged.connect(
                lambda _: self._search(self._search_edit.text()))
            top.addWidget(self._rarity_combo)

        # Book filter — populated lazily on first search
        self._book_combo = QComboBox()
        self._book_combo.setMinimumWidth(200)
        self._book_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._book_combo.addItem("All Books")
        self._book_combo.currentTextChanged.connect(
            lambda _: self._search(self._search_edit.text()))
        top.addWidget(self._book_combo, stretch=2)

        lay.addLayout(top)

        # ─ Splitter: table | description ────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        self._view = QTableView()
        self._view.setModel(self._model)
        self._view.setSortingEnabled(True)
        self._view.setAlternatingRowColors(True)
        self._view.verticalHeader().setVisible(False)
        self._view.setShowGrid(False)
        self._view.setSelectionBehavior(QTableView.SelectRows)
        self._view.setSelectionMode(QTableView.SingleSelection)
        self._view.setEditTriggers(QTableView.NoEditTriggers)
        hh = self._view.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._view.verticalHeader().setDefaultSectionSize(24)
        self._view.doubleClicked.connect(self._accept_selection)

        self._desc_view = QTextEdit()
        self._desc_view.setReadOnly(True)
        self._desc_view.setMinimumHeight(100)
        self._desc_view.setPlaceholderText("Select an entry to read its full description…")

        self._view.selectionModel().currentRowChanged.connect(self._on_row_changed)

        splitter.addWidget(self._view)
        splitter.addWidget(self._desc_view)
        splitter.setSizes([380, 160])
        lay.addWidget(splitter, stretch=1)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color: #505050; font-size: 11px;")
        lay.addWidget(self._count_lbl)

        btns = QHBoxLayout()
        select_btn = QPushButton("Select")
        select_btn.setProperty("class", "primary")
        select_btn.clicked.connect(self._accept_selection)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(select_btn)
        lay.addLayout(btns)

        self._search_edit.setFocus()

    def _search(self, query: str):
        book = self._book_combo.currentText()
        if book == "All Books":
            book = None

        try:
            if self._data_type == "Spells":
                school = None
                if hasattr(self, "_school_combo"):
                    t = self._school_combo.currentText()
                    if t != "All Schools":
                        school = t
                results = GameDataLoader.search_spells(query, school=school, book=book)
            elif self._data_type == "Monsters":
                cr = None
                if hasattr(self, "_cr_combo"):
                    t = self._cr_combo.currentText()
                    if t != "All CR":
                        cr = t
                results = GameDataLoader.search_monsters(query, cr=cr, book=book)
            else:
                rarity = None
                if hasattr(self, "_rarity_combo"):
                    t = self._rarity_combo.currentText()
                    if t != "All Rarities":
                        rarity = t
                results = GameDataLoader.search_items(query, rarity=rarity, book=book)
        except Exception as e:
            self._count_lbl.setText(f"Error: {e}")
            return

        # Lazily populate book combo
        if self._book_combo.count() == 1:
            try:
                books = GameDataLoader.book_names(self._data_type)
                self._book_combo.blockSignals(True)
                self._book_combo.addItems(books)
                self._book_combo.blockSignals(False)
            except Exception:
                pass

        self._model.reset_data(results, self._data_type)
        self._count_lbl.setText(f"{len(results):,} entries")

    def _on_row_changed(self, current, _previous):
        entry = self._model.entry(current.row())
        text = entry.get("description", "") or ""
        self._desc_view.setPlainText(text if text else "No description available.")

    def _accept_selection(self):
        idx = self._view.currentIndex()
        if not idx.isValid():
            return
        entry = self._model.entry(idx.row())
        self.selected_name = entry.get("name", "")
        self.accept()


# ── Roster tab ────────────────────────────────────────────────────────────────

class _RosterTab(QWidget):
    def __init__(self, context):
        super().__init__()
        self._ctx = context
        self._svc = context.services.try_get("campaign_service")
        self._campaign = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(20,16,20,16); lay.setSpacing(10)

        # Filter + action row
        top = QHBoxLayout(); top.setSpacing(8)
        self._role_filter = QComboBox()
        self._role_filter.addItem("All Roles")
        self._role_filter.addItems(CHARACTER_ROLES)
        self._role_filter.currentTextChanged.connect(self._refresh)
        top.addWidget(QLabel("Role:"))
        top.addWidget(self._role_filter)
        self._search = QLineEdit(); self._search.setPlaceholderText("Search name…")
        self._search.textChanged.connect(self._refresh)
        top.addWidget(self._search, stretch=1)
        add_btn = QPushButton("+ Add Character"); add_btn.setProperty("class", "primary")
        add_btn.clicked.connect(self._add_character)
        top.addWidget(add_btn)
        lay.addLayout(top)

        # Splitter: table left, detail right
        splitter = QSplitter(Qt.Horizontal)

        # Left: character table
        left_w = QWidget()
        left_l = QVBoxLayout(left_w); left_l.setContentsMargins(0,0,0,0); left_l.setSpacing(6)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Name", "Role", "Status", "Class", "Lvl"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_change)
        left_l.addWidget(self._table)

        btn_row = QHBoxLayout()
        self._edit_btn = QPushButton("Edit"); self._edit_btn.clicked.connect(self._edit_character)
        self._gal_btn  = QPushButton("Gallery"); self._gal_btn.clicked.connect(self._open_gallery)
        self._del_btn  = QPushButton("Delete"); self._del_btn.setProperty("class", "danger")
        self._del_btn.clicked.connect(self._delete_character)
        for b in [self._edit_btn, self._gal_btn, self._del_btn]:
            b.setEnabled(False); btn_row.addWidget(b)
        btn_row.addStretch()
        left_l.addLayout(btn_row)

        splitter.addWidget(left_w)

        # Right: character detail panel
        self._detail_panel = _CharacterDetailPanel()
        self._detail_panel.set_service(self._svc)
        self._detail_panel.set_context(self._ctx)
        splitter.addWidget(self._detail_panel)
        splitter.setSizes([480, 320])
        lay.addWidget(splitter, stretch=1)

    def load(self, campaign: Campaign):
        self._campaign = campaign
        self._refresh()

    def _refresh(self):
        self._table.setRowCount(0)
        self._detail_panel.clear()
        if not self._svc or not self._campaign: return

        needle    = self._search.text().strip().lower()
        role_sel  = self._role_filter.currentText()

        for ch in self._svc.get_characters(self._campaign.id):
            if role_sel != "All Roles" and ch.character_role != role_sel: continue
            if needle and needle not in ch.name.lower(): continue

            row = self._table.rowCount(); self._table.insertRow(row)
            name_item = QTableWidgetItem(ch.name)
            name_item.setData(Qt.UserRole, ch.id)
            color = CHARACTER_ROLE_COLORS.get(ch.character_role, "#686868")
            name_item.setForeground(QColor(color))
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, QTableWidgetItem(ch.character_role))
            self._table.setItem(row, 2, QTableWidgetItem(ch.status))
            self._table.setItem(row, 3, QTableWidgetItem(ch.character_class or ""))
            lvl = QTableWidgetItem(str(ch.level) if ch.level > 0 else "—")
            lvl.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 4, lvl)

    def _on_selection_change(self):
        row = self._table.currentRow()
        has_sel = row >= 0
        for b in [self._edit_btn, self._gal_btn, self._del_btn]:
            b.setEnabled(has_sel)
        if has_sel:
            ch_id = self._table.item(row, 0).data(Qt.UserRole)
            ch = self._svc.get_character(ch_id)
            if ch: self._detail_panel.show_character(ch)

    def _selected_id(self):
        row = self._table.currentRow()
        if row < 0: return None
        return self._table.item(row, 0).data(Qt.UserRole)

    def _add_character(self):
        if not self._campaign: return
        dlg = CharacterDialog(self._ctx, self._campaign, parent=self)
        if dlg.exec(): self._refresh()

    def _edit_character(self):
        ch_id = self._selected_id()
        if not ch_id: return
        ch = self._svc.get_character(ch_id)
        dlg = CharacterDialog(self._ctx, self._campaign, character=ch, parent=self)
        if dlg.exec(): self._refresh()

    def _open_gallery(self):
        ch_id = self._selected_id()
        if not ch_id: return
        ch = self._svc.get_character(ch_id)
        CharacterGalleryDialog(self._ctx, ch, parent=self).exec()

    def _delete_character(self):
        ch_id = self._selected_id()
        if not ch_id: return
        name = self._table.item(self._table.currentRow(), 0).text()
        if QMessageBox.question(self, "Delete Character",
            f"Delete '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self._svc.delete_character(ch_id)
        self._refresh()


class _CharacterDetailPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(280)
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 8, 8, 8); lay.setSpacing(8)

        self._thumb = QLabel()
        self._thumb.setFixedSize(180, 140)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._thumb.setObjectName("cardThumb")
        self._thumb.setText("No Photo")
        lay.addWidget(self._thumb, alignment=Qt.AlignHCenter)

        self._name_lbl = QLabel("—")
        self._name_lbl.setObjectName("cardTitle")
        self._name_lbl.setWordWrap(True)
        lay.addWidget(self._name_lbl)

        self._role_lbl = QLabel("")
        lay.addWidget(self._role_lbl)

        self._sub_lbl = QLabel("")
        self._sub_lbl.setObjectName("fieldLabel")
        self._sub_lbl.setWordWrap(True)
        lay.addWidget(self._sub_lbl)

        # HP bar — uses global QProgressBar style; chunk color stays green (semantic)
        hp_row = QHBoxLayout()
        hp_row.addWidget(QLabel("HP"))
        self._hp_bar = QProgressBar()
        self._hp_bar.setFixedHeight(10)
        self._hp_bar.setTextVisible(False)
        hp_row.addWidget(self._hp_bar, stretch=1)
        self._hp_lbl = QLabel("0 / 0")
        self._hp_lbl.setObjectName("fieldLabel")
        hp_row.addWidget(self._hp_lbl)
        lay.addLayout(hp_row)

        self._stats_lbl = QLabel("")
        self._stats_lbl.setObjectName("fieldLabel")
        self._stats_lbl.setWordWrap(True)
        lay.addWidget(self._stats_lbl)

        # Quick HP editor
        hp_edit_row = QHBoxLayout(); hp_edit_row.setSpacing(4)
        self._dmg_spin = QSpinBox(); self._dmg_spin.setRange(1, 999)
        self._dmg_spin.setValue(1); self._dmg_spin.setFixedWidth(60)
        self._dmg_spin.setToolTip("Amount to damage or heal")
        dmg_btn  = QPushButton("− Dmg"); dmg_btn.setFixedHeight(26)
        dmg_btn.setProperty("class", "danger")
        dmg_btn.setStyleSheet("font-size: 11px; padding: 0 6px;")
        heal_btn = QPushButton("+ Heal"); heal_btn.setFixedHeight(26)
        heal_btn.setStyleSheet("font-size: 11px; padding: 0 6px; color: #3dba6e;")
        dmg_btn.clicked.connect(self._apply_damage)
        heal_btn.clicked.connect(self._apply_heal)
        hp_edit_row.addWidget(self._dmg_spin)
        hp_edit_row.addWidget(dmg_btn)
        hp_edit_row.addWidget(heal_btn)
        hp_edit_row.addStretch()
        lay.addLayout(hp_edit_row)

        self._notes_view = QLabel("")
        self._notes_view.setWordWrap(True)
        self._notes_view.setStyleSheet("color: #808080; font-size: 12px;")
        lay.addWidget(self._notes_view)

        lay.addStretch()

        # Open full sheet button
        self._sheet_btn = QPushButton("Open Full Character Sheet")
        self._sheet_btn.setProperty("class", "primary")
        self._sheet_btn.setEnabled(False)
        self._sheet_btn.clicked.connect(self._open_sheet)
        lay.addWidget(self._sheet_btn)

        # Internal state
        self._current_ch  = None
        self._svc_ref     = None
        self._ctx_ref     = None

    def set_service(self, svc):
        self._svc_ref = svc

    def set_context(self, ctx):
        self._ctx_ref = ctx

    def _open_sheet(self):
        if not self._current_ch or not self._ctx_ref:
            return
        dlg = CharacterSheetDialog(self._ctx_ref, self._current_ch, parent=self)
        dlg.exec()
        # Reload character in case HP / data changed
        if self._svc_ref:
            refreshed = self._svc_ref.get_character(self._current_ch.id)
            if refreshed:
                self.show_character(refreshed)

    def clear(self):
        self._current_ch = None
        self._sheet_btn.setEnabled(False)
        self._name_lbl.setText("—")
        self._role_lbl.setText("")
        self._sub_lbl.setText("")
        self._thumb.setText("No Photo")
        self._thumb.setPixmap(QPixmap())
        self._hp_bar.setValue(0); self._hp_lbl.setText("0 / 0")
        self._stats_lbl.setText(""); self._notes_view.setText("")

    def _apply_damage(self):
        if not self._current_ch or not self._svc_ref: return
        amt = self._dmg_spin.value()
        new_hp = max(0, self._current_ch.hit_points - amt)
        self._svc_ref.update_character(self._current_ch.id, hit_points=new_hp)
        self._current_ch.hit_points = new_hp
        self.show_character(self._current_ch)

    def _apply_heal(self):
        if not self._current_ch or not self._svc_ref: return
        amt = self._dmg_spin.value()
        new_hp = min(self._current_ch.max_hit_points, self._current_ch.hit_points + amt)
        self._svc_ref.update_character(self._current_ch.id, hit_points=new_hp)
        self._current_ch.hit_points = new_hp
        self.show_character(self._current_ch)

    def show_character(self, ch: Character):
        self._current_ch = ch
        self._sheet_btn.setEnabled(True)
        self._name_lbl.setText(ch.name)

        # Role badge (inline text styling)
        color = CHARACTER_ROLE_COLORS.get(ch.character_role, "#686868")
        self._role_lbl.setText(ch.character_role)
        self._role_lbl.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 12px;")

        parts = []
        if ch.character_class: parts.append(ch.character_class)
        if ch.race:             parts.append(ch.race)
        if ch.level > 0:        parts.append(f"Level {ch.level}")
        self._sub_lbl.setText("  ·  ".join(parts))

        # Photo — use stored crop/focal data if available
        if ch.primary_image_path and os.path.isfile(ch.primary_image_path):
            zoom, fx, fy = 1.0, 0.5, 0.5
            svc = getattr(self, "_svc_ref", None)
            if svc:
                try:
                    imgs = svc.get_character_images(ch.id)
                    primary_img = next(
                        (i for i in imgs if i["image_path"] == ch.primary_image_path), None)
                    if primary_img:
                        zoom = float(primary_img.get("zoom",    1.0))
                        fx   = float(primary_img.get("focal_x", 0.5))
                        fy   = float(primary_img.get("focal_y", 0.5))
                except Exception:
                    pass
            pix = focal_pixmap(QPixmap(ch.primary_image_path), 180, 140, zoom, fx, fy)
            self._thumb.setPixmap(pix)
            self._thumb.setText("")
        else:
            self._thumb.setPixmap(QPixmap())
            self._thumb.setText("No Photo")

        # HP
        hp_max = max(ch.max_hit_points, 1)
        self._hp_bar.setRange(0, hp_max)
        self._hp_bar.setValue(min(ch.hit_points, hp_max))
        self._hp_lbl.setText(f"{ch.hit_points} / {ch.max_hit_points}")
        hp_pct = ch.hit_points / hp_max
        bar_color = "#3dba6e" if hp_pct > 0.5 else "#f0a020" if hp_pct > 0.25 else "#e05555"
        self._hp_bar.setStyleSheet(
            f"QProgressBar {{ border-radius: 5px; background: #2a2a2a; }}"
            f"QProgressBar::chunk {{ background: {bar_color}; border-radius: 5px; }}"
        )

        # Stats
        stats = ch.stats
        if stats:
            parts = [f"{k}: {v}" for k, v in list(stats.items())[:6]]
            self._stats_lbl.setText("  ".join(parts))
        else:
            self._stats_lbl.setText("")

        self._notes_view.setText(
            (ch.notes or "")[:200] + ("…" if ch.notes and len(ch.notes) > 200 else ""))


# ── Initiative Tracker tab ────────────────────────────────────────────────────

class _InitiativeTab(QWidget):
    """
    Combat / encounter tracker.
    Load characters from the roster, add custom combatants, roll initiatives,
    sort, and track HP + conditions turn-by-turn.  Resets between encounters.
    """

    COL_INIT  = 0
    COL_NAME  = 1
    COL_HP    = 2
    COL_MAXHP = 3
    COL_AC    = 4
    COL_COND  = 5

    def __init__(self, context):
        super().__init__()
        self._ctx      = context
        self._svc      = context.services.try_get("campaign_service")
        self._campaign = None
        self._round    = 0
        self._cur_row  = -1
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        # ── Action bar ────────────────────────────────────────────────────────
        top = QHBoxLayout(); top.setSpacing(6)

        load_btn = QPushButton("⚔  Load Roster")
        load_btn.setToolTip("Load all characters from this campaign's roster into the tracker")
        load_btn.clicked.connect(self._load_roster)
        top.addWidget(load_btn)

        add_btn = QPushButton("+ Custom Combatant")
        add_btn.setToolTip("Add a monster or other combatant not in the roster")
        add_btn.clicked.connect(self._add_custom)
        top.addWidget(add_btn)

        top.addWidget(_vline())

        roll_btn = QPushButton("🎲  Roll All Initiatives")
        roll_btn.setProperty("class", "primary")
        roll_btn.clicked.connect(self._roll_all)
        top.addWidget(roll_btn)

        sort_btn = QPushButton("Sort ↓")
        sort_btn.setToolTip("Sort by initiative (highest first)")
        sort_btn.clicked.connect(self._sort_by_initiative)
        top.addWidget(sort_btn)

        top.addWidget(_vline())

        self._next_btn = QPushButton("Next Turn →")
        self._next_btn.setProperty("class", "primary")
        self._next_btn.setFixedWidth(110)
        self._next_btn.clicked.connect(self._next_turn)
        top.addWidget(self._next_btn)

        self._round_lbl = QLabel("Round —")
        self._round_lbl.setStyleSheet("font-weight: 600; color: #f0a020; min-width: 80px;")
        top.addWidget(self._round_lbl)

        top.addStretch()

        clear_btn = QPushButton("Clear Combat")
        clear_btn.setProperty("class", "danger")
        clear_btn.clicked.connect(self._clear_combat)
        top.addWidget(clear_btn)

        lay.addLayout(top)

        # ── Active combatant banner ───────────────────────────────────────────
        self._active_banner = QLabel("")
        self._active_banner.setAlignment(Qt.AlignCenter)
        self._active_banner.setStyleSheet(
            "background: #0078d420; border: 1px solid #0078d455; border-radius: 5px;"
            " color: #4ab0ff; font-size: 16px; font-weight: 700; padding: 6px;"
        )
        self._active_banner.setVisible(False)
        lay.addWidget(self._active_banner)

        # ── Combatant table ───────────────────────────────────────────────────
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Initiative", "Name", "HP", "Max HP", "AC", "Conditions"])
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(self.COL_INIT,  QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_NAME,  QHeaderView.Stretch)
        h.setSectionResizeMode(self.COL_HP,    QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_MAXHP, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_AC,    QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_COND,  QHeaderView.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self._table, stretch=1)

        # ── Bottom bar: remove selected ───────────────────────────────────────
        btm = QHBoxLayout()
        rem_btn = QPushButton("Remove Selected")
        rem_btn.setProperty("class", "danger")
        rem_btn.clicked.connect(self._remove_selected)
        btm.addWidget(rem_btn); btm.addStretch()
        hint = QLabel("Double-click HP or Conditions cells to edit inline")
        hint.setStyleSheet("color: #505050; font-size: 11px;")
        btm.addWidget(hint)
        lay.addLayout(btm)

    def load(self, campaign):
        self._campaign = campaign
        # Don't auto-clear — combat may still be in progress across tab switches

    def _load_roster(self):
        if not self._campaign or not self._svc: return
        characters = self._svc.get_characters(self._campaign.id)
        if not characters:
            _show_toast(self, "ℹ  No characters in the roster yet — add some in the Roster tab", "toastInfo")
            return
        for ch in characters:
            self._add_row(
                name   = ch.name,
                hp     = ch.hit_points,
                max_hp = ch.max_hit_points or ch.hit_points or 10,
                ac     = ch.armor_class,
                role   = ch.character_role,
            )

    def _add_custom(self):
        dlg = _AddCombatantDialog(self)
        if dlg.exec():
            d = dlg.data()
            self._add_row(d["name"], d["hp"], d["hp"], d["ac"], "Monster")

    def _add_row(self, name: str, hp: int, max_hp: int, ac: int, role: str = ""):
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Initiative — editable spin
        init_item = QTableWidgetItem("0")
        init_item.setTextAlignment(Qt.AlignCenter)
        init_item.setData(Qt.UserRole, role)
        self._table.setItem(row, self.COL_INIT, init_item)

        # Name
        color = CHARACTER_ROLE_COLORS.get(role, "#d0d0d0")
        name_item = QTableWidgetItem(name)
        name_item.setForeground(QColor(color))
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, self.COL_NAME, name_item)

        # HP
        hp_item = QTableWidgetItem(str(hp))
        hp_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, self.COL_HP, hp_item)

        # Max HP
        max_item = QTableWidgetItem(str(max_hp))
        max_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, self.COL_MAXHP, max_item)

        # AC
        ac_item = QTableWidgetItem(str(ac) if ac else "—")
        ac_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, self.COL_AC, ac_item)

        # Conditions
        self._table.setItem(row, self.COL_COND, QTableWidgetItem(""))

    def _roll_all(self):
        for row in range(self._table.rowCount()):
            roll = random.randint(1, 20)
            self._table.item(row, self.COL_INIT).setText(str(roll))
        self._sort_by_initiative()

    def _sort_by_initiative(self):
        rows_data = []
        for row in range(self._table.rowCount()):
            try:
                init = int(self._table.item(row, self.COL_INIT).text())
            except (ValueError, AttributeError):
                init = 0
            rows_data.append((
                init,
                self._table.item(row, self.COL_NAME).text(),
                self._table.item(row, self.COL_HP).text(),
                self._table.item(row, self.COL_MAXHP).text(),
                self._table.item(row, self.COL_AC).text(),
                self._table.item(row, self.COL_COND).text(),
                self._table.item(row, self.COL_NAME).data(Qt.UserRole) or "",
                self._table.item(row, self.COL_INIT).data(Qt.UserRole) or "",
            ))
        rows_data.sort(key=lambda r: r[0], reverse=True)

        self._table.setRowCount(0)
        for d in rows_data:
            self._add_row(d[1], int(d[2]) if d[2].isdigit() else 0,
                          int(d[3]) if d[3].isdigit() else 0,
                          int(d[4]) if d[4].isdigit() else 0, d[6])
            row = self._table.rowCount() - 1
            self._table.item(row, self.COL_INIT).setText(str(d[0]))
            self._table.item(row, self.COL_COND).setText(d[5])

        self._cur_row = -1
        self._active_banner.setVisible(False)
        self._highlight_row(-1)

    def _next_turn(self):
        count = self._table.rowCount()
        if count == 0: return
        if self._round == 0:
            self._round = 1
            self._cur_row = 0
        else:
            self._cur_row += 1
            if self._cur_row >= count:
                self._cur_row = 0
                self._round += 1

        self._round_lbl.setText(f"Round {self._round}")
        self._highlight_row(self._cur_row)
        name = self._table.item(self._cur_row, self.COL_NAME).text()
        self._active_banner.setText(f"▶  {name}'s Turn")
        self._active_banner.setVisible(True)

    def _highlight_row(self, active_row: int):
        for row in range(self._table.rowCount()):
            is_active = (row == active_row)
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item:
                    if is_active:
                        item.setBackground(QColor("#0078d430"))
                    else:
                        item.setBackground(QColor(0, 0, 0, 0))

    def _remove_selected(self):
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)
            if self._cur_row >= self._table.rowCount():
                self._cur_row = 0

    def _clear_combat(self):
        if QMessageBox.question(self, "Clear Combat",
            "Clear all combatants and reset the round counter?",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self._table.setRowCount(0)
        self._round = 0
        self._cur_row = -1
        self._round_lbl.setText("Round —")
        self._active_banner.setVisible(False)


class _AddCombatantDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Combatant")
        self.setMinimumWidth(320)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        self._name = QLineEdit(); self._name.setPlaceholderText("e.g. Goblin #1, Pit Fiend…")
        lay.addLayout(_field("Name *", self._name))

        self._hp = QSpinBox(); self._hp.setRange(1, 9999); self._hp.setValue(10)
        lay.addLayout(_field("Hit Points", self._hp))

        self._ac = QSpinBox(); self._ac.setRange(0, 99); self._ac.setValue(10)
        lay.addLayout(_field("Armour Class", self._ac))

        self._err = QLabel(""); self._err.setObjectName("statusError")
        lay.addWidget(self._err)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _ok(self):
        if not self._name.text().strip():
            self._err.setText("Name is required."); return
        self.accept()

    def data(self) -> dict:
        return {"name": self._name.text().strip(),
                "hp": self._hp.value(), "ac": self._ac.value()}


# ── Battle Log tab ────────────────────────────────────────────────────────────

class _BattleLogTab(QWidget):
    def __init__(self, context):
        super().__init__()
        self._ctx = context
        self._svc = context.services.try_get("campaign_service")
        self._campaign = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(20,16,20,16); lay.setSpacing(10)

        top = QHBoxLayout()
        add_btn = QPushButton("+ Log Session / Battle"); add_btn.setProperty("class", "primary")
        add_btn.clicked.connect(self._add_battle)
        top.addWidget(add_btn); top.addStretch()
        lay.addLayout(top)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        self._cards_w = QWidget()
        self._cards_l = QVBoxLayout(self._cards_w)
        self._cards_l.setSpacing(8)
        self._cards_l.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._cards_w)
        lay.addWidget(scroll, stretch=1)

    def load(self, campaign: Campaign):
        self._campaign = campaign
        self._refresh()

    def _refresh(self):
        while self._cards_l.count():
            item = self._cards_l.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not self._svc or not self._campaign:
            empty = QLabel("No sessions logged yet.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #606060; padding: 40px;")
            self._cards_l.addWidget(empty)
            return

        battles = self._svc.get_battles(self._campaign.id)
        if not battles:
            empty = QLabel("No sessions logged yet — click  \"+ Log Session / Battle\"  to start.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #606060; padding: 40px;")
            self._cards_l.addWidget(empty)
            return

        for b in reversed(battles):
            self._cards_l.addWidget(self._make_battle_card(b))

    def _make_battle_card(self, b: Battle) -> QFrame:
        card = QFrame(); card.setFrameShape(QFrame.StyledPanel)
        lay = QHBoxLayout(card); lay.setContentsMargins(14,10,14,10); lay.setSpacing(12)

        num_lbl = QLabel(f"#{b.session_number}")
        num_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #505050; min-width: 36px;")
        num_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(num_lbl)

        lay.addWidget(_vline())

        info = QVBoxLayout(); info.setSpacing(2)
        title_lbl = QLabel(b.title)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0;")
        info.addWidget(title_lbl)

        meta_parts = []
        if b.date_played:    meta_parts.append(b.date_played)
        if b.location_name:  meta_parts.append(b.location_name)
        if b.scenario_name:  meta_parts.append(b.scenario_name)
        if meta_parts:
            meta = QLabel("  ·  ".join(meta_parts))
            meta.setStyleSheet("color: #606060; font-size: 12px;")
            info.addWidget(meta)

        # Participants
        if self._svc:
            players_for_campaign = {p.id: p.player_name for p in self._svc.get_players(self._campaign.id)}
            parts = self._svc.get_participants(b.id)
            if parts:
                p_names = [players_for_campaign.get(p.player_id, f"Player {p.player_id}") for p in parts]
                p_lbl = QLabel("Participants: " + ", ".join(p_names))
                p_lbl.setStyleSheet("color: #707070; font-size: 11px;")
                info.addWidget(p_lbl)

        lay.addLayout(info, stretch=1)

        badge = _outcome_badge(b.outcome)
        badge.setFixedWidth(110)
        lay.addWidget(badge, alignment=Qt.AlignVCenter)

        btn_col = QVBoxLayout(); btn_col.setSpacing(4)
        edit_btn = QPushButton("Edit"); edit_btn.setFixedWidth(70)
        edit_btn.clicked.connect(lambda _=False, battle=b: self._edit_battle(battle))
        gal_btn  = QPushButton("Photos"); gal_btn.setFixedWidth(70)
        gal_btn.clicked.connect(lambda _=False, battle=b: self._open_gallery(battle))
        del_btn  = QPushButton("Delete"); del_btn.setFixedWidth(70)
        del_btn.setProperty("class", "danger")
        del_btn.clicked.connect(lambda _=False, battle=b: self._delete_battle(battle))
        for btn in [edit_btn, gal_btn, del_btn]: btn_col.addWidget(btn)
        lay.addLayout(btn_col)

        # Expand/collapse chronicle
        if b.chronicle_text:
            card2 = QFrame(); c2l = QVBoxLayout(card2)
            c2l.setContentsMargins(14,0,14,10); c2l.setSpacing(4)
            chr_lbl = QLabel(b.chronicle_text[:400] + ("…" if len(b.chronicle_text)>400 else ""))
            chr_lbl.setStyleSheet("color: #808080; font-size: 12px;")
            chr_lbl.setWordWrap(True)
            c2l.addWidget(chr_lbl)

            wrapper = QFrame(); wrapper.setFrameShape(QFrame.StyledPanel)
            wl = QVBoxLayout(wrapper); wl.setContentsMargins(0,0,0,0); wl.setSpacing(0)
            wl.addWidget(card)
            wl.addWidget(card2)
            return wrapper

        return card

    def _add_battle(self):
        if not self._campaign: return
        dlg = BattleDialog(self._ctx, self._campaign, parent=self)
        if dlg.exec(): self._refresh()

    def _edit_battle(self, battle: Battle):
        dlg = BattleDialog(self._ctx, self._campaign, battle=battle, parent=self)
        if dlg.exec(): self._refresh()

    def _open_gallery(self, battle: Battle):
        BattleGalleryDialog(self._ctx, battle, parent=self).exec()

    def _delete_battle(self, battle: Battle):
        if QMessageBox.question(self, "Delete",
            f"Delete session '#{battle.session_number} {battle.title}'?",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self._svc.delete_battle(battle.id)
        self._refresh()


# ── Chronicle tab ─────────────────────────────────────────────────────────────

class _ChronicleTab(QWidget):
    def __init__(self, context):
        super().__init__()
        self._ctx = context
        self._svc = context.services.try_get("campaign_service")
        self._campaign = None
        self._current_entry = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(20,16,20,16); lay.setSpacing(10)

        top = QHBoxLayout()
        add_btn = QPushButton("+ New Entry"); add_btn.setProperty("class", "primary")
        add_btn.clicked.connect(self._add_entry)
        top.addWidget(add_btn); top.addStretch()
        lay.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        # Left: entry list
        left_w = QWidget(); ll = QVBoxLayout(left_w); ll.setContentsMargins(0,0,0,0)
        self._entry_list = QListWidget(); self._entry_list.setAlternatingRowColors(True)
        self._entry_list.currentRowChanged.connect(self._on_entry_selected)
        ll.addWidget(self._entry_list)

        btn_row = QHBoxLayout()
        self._edit_entry_btn = QPushButton("Edit"); self._edit_entry_btn.setEnabled(False)
        self._edit_entry_btn.clicked.connect(self._edit_entry)
        self._del_entry_btn  = QPushButton("Delete"); self._del_entry_btn.setEnabled(False)
        self._del_entry_btn.setProperty("class", "danger")
        self._del_entry_btn.clicked.connect(self._delete_entry)
        btn_row.addWidget(self._edit_entry_btn); btn_row.addWidget(self._del_entry_btn)
        btn_row.addStretch()
        ll.addLayout(btn_row)
        splitter.addWidget(left_w)

        # Right: content
        right_w = QWidget(); rl = QVBoxLayout(right_w); rl.setContentsMargins(0,0,0,0); rl.setSpacing(6)
        self._entry_title = QLabel("")
        self._entry_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #e0e0e0;")
        self._entry_date  = QLabel("")
        self._entry_date.setStyleSheet("color: #606060; font-size: 11px;")
        self._entry_content = QTextEdit(); self._entry_content.setReadOnly(True)
        rl.addWidget(self._entry_title)
        rl.addWidget(self._entry_date)
        rl.addWidget(_hline())
        rl.addWidget(self._entry_content, stretch=1)
        splitter.addWidget(right_w)

        splitter.setSizes([280, 480])
        lay.addWidget(splitter, stretch=1)

    def load(self, campaign: Campaign):
        self._campaign = campaign
        self._refresh()

    def _refresh(self):
        self._entry_list.clear()
        self._current_entry = None
        self._entry_title.setText(""); self._entry_date.setText("")
        self._entry_content.clear()
        self._edit_entry_btn.setEnabled(False)
        self._del_entry_btn.setEnabled(False)

        if not self._svc or not self._campaign: return
        self._entries = self._svc.get_journal_entries(self._campaign.id)
        for e in self._entries:
            item = QListWidgetItem(e.title)
            item.setData(Qt.UserRole, e.id)
            if e.created_at:
                item.setToolTip(e.created_at[:10])
            self._entry_list.addItem(item)

    def _on_entry_selected(self, row: int):
        if row < 0:
            self._current_entry = None
            self._edit_entry_btn.setEnabled(False)
            self._del_entry_btn.setEnabled(False)
            return
        eid = self._entry_list.item(row).data(Qt.UserRole)
        for e in self._entries:
            if e.id == eid:
                self._current_entry = e
                self._entry_title.setText(e.title)
                self._entry_date.setText(
                    f"Created: {(e.created_at or '')[:10]}  ·  "
                    f"Updated: {(e.updated_at or '')[:10]}"
                )
                self._entry_content.setPlainText(e.content)
                self._edit_entry_btn.setEnabled(True)
                self._del_entry_btn.setEnabled(True)
                break

    def _add_entry(self):
        if not self._campaign: return
        dlg = JournalDialog(self._ctx, self._campaign, parent=self)
        if dlg.exec(): self._refresh()

    def _edit_entry(self):
        if not self._current_entry: return
        dlg = JournalDialog(self._ctx, self._campaign, entry=self._current_entry, parent=self)
        if dlg.exec(): self._refresh()

    def _delete_entry(self):
        if not self._current_entry: return
        if QMessageBox.question(self, "Delete", f"Delete entry '{self._current_entry.title}'?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self._svc.delete_journal_entry(self._current_entry.id)
        self._refresh()


# ── Assets tab ────────────────────────────────────────────────────────────────

class _AssetsTab(QWidget):
    ASSET_ICONS = {
        "Map":      "🗺",
        "Token":    "🪙",
        "Music":    "🎵",
        "Document": "📄",
        "Image":    "🖼",
        "Other":    "📁",
    }

    def __init__(self, context):
        super().__init__()
        self._ctx = context
        self._svc = context.services.try_get("campaign_service")
        self._campaign = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(20,16,20,16); lay.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(8)
        add_btn = QPushButton("+ Add Files…"); add_btn.setProperty("class", "primary")
        add_btn.clicked.connect(self._add_files)
        folder_btn = QPushButton("Open Folder")
        folder_btn.clicked.connect(self._open_folder)
        top.addWidget(add_btn); top.addWidget(folder_btn); top.addStretch()
        lay.addLayout(top)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Type", "Name", "Path"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self._table, stretch=1)

        btn_row = QHBoxLayout()
        open_btn = QPushButton("Open File"); open_btn.clicked.connect(self._open_file)
        rem_btn  = QPushButton("Remove"); rem_btn.setProperty("class", "danger")
        rem_btn.clicked.connect(self._remove_asset)
        btn_row.addWidget(open_btn); btn_row.addWidget(rem_btn); btn_row.addStretch()
        lay.addLayout(btn_row)

    def load(self, campaign: Campaign):
        self._campaign = campaign
        self._refresh()

    def _refresh(self):
        self._table.setRowCount(0)
        if not self._svc or not self._campaign: return
        for a in self._svc.get_assets(self._campaign.id):
            row = self._table.rowCount(); self._table.insertRow(row)
            icon = self.ASSET_ICONS.get(a.asset_type, "📁")
            type_item = QTableWidgetItem(f"{icon}  {a.asset_type}")
            type_item.setData(Qt.UserRole, a.id)
            self._table.setItem(row, 0, type_item)
            self._table.setItem(row, 1, QTableWidgetItem(a.name))
            path_item = QTableWidgetItem(a.file_path)
            if not os.path.exists(a.file_path):
                path_item.setForeground(QColor("#e05555"))
                path_item.setToolTip("File not found at this path")
            self._table.setItem(row, 2, path_item)

    def _add_files(self):
        if not self._campaign: return
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Assets", "",
            "All Files (*);;Images (*.png *.jpg *.jpeg *.bmp *.webp);;PDFs (*.pdf)"
            ";;Audio (*.mp3 *.wav *.ogg *.flac);;Documents (*.pdf *.txt *.docx)")
        if not files: return

        # Copy to campaign folder if set
        dest_folder = self._campaign.assets_folder
        if dest_folder and os.path.isdir(dest_folder):
            new_paths = []
            for f in files:
                dest = os.path.join(dest_folder, Path(f).name)
                try:
                    if f != dest: shutil.copy2(f, dest)
                    new_paths.append(dest)
                except Exception as e:
                    new_paths.append(f)
                    print(f"[CAMPAIGN ASSETS] Could not copy {f}: {e}")
            files = new_paths

        for f in files:
            name = Path(f).name
            asset_type = self._infer_type(f)
            self._svc.add_asset(self._campaign.id, name, f, asset_type)
        self._refresh()

    def _infer_type(self, path: str) -> str:
        ext = Path(path).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"): return "Image"
        if ext in (".mp3", ".wav", ".ogg", ".flac", ".m4a"):          return "Music"
        if ext in (".pdf", ".txt", ".docx", ".odt"):                   return "Document"
        if "token" in Path(path).stem.lower():                         return "Token"
        if "map"   in Path(path).stem.lower():                         return "Map"
        return "Other"

    def _open_folder(self):
        if not self._campaign: return
        folder = self._campaign.assets_folder
        if not folder:
            # Ask to set one
            folder = QFileDialog.getExistingDirectory(self, "Select Assets Folder")
            if not folder: return
            self._svc.update_campaign(self._campaign.id, assets_folder=folder)
            self._campaign.assets_folder = folder
        if os.path.isdir(folder):
            import subprocess, sys
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])

    def _open_file(self):
        row = self._table.currentRow()
        if row < 0: return
        path = self._table.item(row, 2).text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Not Found", f"Cannot find:\n{path}"); return
        import subprocess, sys
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _remove_asset(self):
        row = self._table.currentRow()
        if row < 0: return
        aid = self._table.item(row, 0).data(Qt.UserRole)
        name = self._table.item(row, 1).text()
        if QMessageBox.question(self, "Remove Asset",
            f"Remove '{name}' from this campaign?\n(The file itself will not be deleted.)",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self._svc.delete_asset(aid)
        self._refresh()


# ── Dice Roller ───────────────────────────────────────────────────────────────

class _SaveExprDialog(QDialog):
    """Small dialog to name and save a custom expression."""
    def __init__(self, expression: str = "", name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Expression")
        self.setFixedWidth(360)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        lay.addWidget(QLabel("Expression Name"))
        self._name = QLineEdit(name)
        self._name.setPlaceholderText("e.g. Attack Roll, Fireball Damage…")
        lay.addWidget(self._name)

        lay.addWidget(QLabel("Expression"))
        self._expr = QLineEdit(expression)
        self._expr.setPlaceholderText("e.g. 2d6+3")
        lay.addWidget(self._expr)

        btns = QHBoxLayout()
        save = QPushButton("Save")
        save.setProperty("class", "primary")
        save.clicked.connect(self._accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

        self._name.setFocus()

    def _accept(self):
        if not self._name.text().strip():
            self._name.setPlaceholderText("Name is required!")
            return
        if not self._expr.text().strip():
            self._expr.setPlaceholderText("Expression is required!")
            return
        self.accept()

    def values(self) -> tuple[str, str]:
        return self._name.text().strip(), self._expr.text().strip()


class DiceRollerWidget(QWidget):
    DICE = [4, 6, 8, 10, 12, 20, 100]

    def __init__(self, context):
        super().__init__()
        self._ctx = context
        self._svc = context.services.try_get("campaign_service")
        self._build_ui()
        self._load_history()
        self._load_saved()

    def _build_ui(self):
        # Two-column layout: left = roller, right = saved expressions
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left column: roller ───────────────────────────────────────────────
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(24, 20, 20, 20)
        lay.setSpacing(14)

        title = QLabel("Dice Roller")
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        # Quick dice buttons
        dice_box = QGroupBox("Quick Roll")
        dl = QHBoxLayout(dice_box); dl.setSpacing(8)
        for sides in self.DICE:
            btn = QPushButton(f"d{sides}")
            btn.setFixedSize(60, 46)
            btn.setStyleSheet("font-size: 15px; font-weight: 600;")
            btn.clicked.connect(lambda _=False, s=sides: self._quick_roll(s))
            dl.addWidget(btn)
        dl.addStretch()
        lay.addWidget(dice_box)

        # Special rolls
        spec_box = QGroupBox("Special")
        sl = QHBoxLayout(spec_box); sl.setSpacing(8)
        for label, expr in [("Advantage", "adv"), ("Disadvantage", "dis"), ("4d6 Drop Low", "4d6dl")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, e=expr: self._roll_expr(e))
            sl.addWidget(btn)
        sl.addStretch()
        lay.addWidget(spec_box)

        # Expression input
        expr_box = QGroupBox("Custom Expression")
        el = QHBoxLayout(expr_box); el.setSpacing(8)
        self._expr_edit = QLineEdit()
        self._expr_edit.setPlaceholderText("e.g.  2d6+3   or   4d8-1")
        self._expr_edit.returnPressed.connect(self._roll_custom)
        el.addWidget(self._expr_edit, stretch=1)
        roll_btn = QPushButton("Roll")
        roll_btn.setProperty("class", "primary")
        roll_btn.setFixedWidth(64)
        roll_btn.clicked.connect(self._roll_custom)
        save_btn = QPushButton("Save…")
        save_btn.setToolTip("Save this expression for quick access")
        save_btn.setFixedWidth(64)
        save_btn.clicked.connect(self._save_current_expr)
        el.addWidget(roll_btn)
        el.addWidget(save_btn)
        lay.addWidget(expr_box)

        # Result display
        result_frame = QFrame()
        result_frame.setFrameShape(QFrame.StyledPanel)
        rl = QVBoxLayout(result_frame)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(4)

        self._result_lbl = QLabel("—")
        self._result_lbl.setAlignment(Qt.AlignCenter)
        self._result_lbl.setObjectName("diceResult")
        rl.addWidget(self._result_lbl)

        self._detail_lbl = QLabel("")
        self._detail_lbl.setAlignment(Qt.AlignCenter)
        self._detail_lbl.setObjectName("fieldLabel")
        rl.addWidget(self._detail_lbl)
        lay.addWidget(result_frame)

        # History
        hist_hdr = QHBoxLayout()
        hist_hdr.addWidget(QLabel("Roll History"))
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_history)
        hist_hdr.addStretch()
        hist_hdr.addWidget(clear_btn)
        lay.addLayout(hist_hdr)

        self._hist_table = QTableWidget(0, 3)
        self._hist_table.setHorizontalHeaderLabels(["Expression", "Result", "Timestamp"])
        self._hist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._hist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._hist_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._hist_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._hist_table.setAlternatingRowColors(True)
        self._hist_table.verticalHeader().setVisible(False)
        self._hist_table.setShowGrid(False)
        lay.addWidget(self._hist_table, stretch=1)

        root.addWidget(left, stretch=3)

        # ── Divider ───────────────────────────────────────────────────────────
        root.addWidget(_vline())

        # ── Right column: saved expressions ───────────────────────────────────
        right = QWidget()
        rl2 = QVBoxLayout(right)
        rl2.setContentsMargins(20, 20, 20, 20)
        rl2.setSpacing(10)

        saved_hdr = QHBoxLayout()
        saved_title = QLabel("Saved Expressions")
        saved_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f0f0f0;")
        saved_hdr.addWidget(saved_title)
        saved_hdr.addStretch()
        new_expr_btn = QPushButton("+ New")
        new_expr_btn.setProperty("class", "primary")
        new_expr_btn.clicked.connect(lambda: self._new_saved_expr())
        saved_hdr.addWidget(new_expr_btn)
        rl2.addLayout(saved_hdr)

        hint = QLabel("Click a saved expression to roll it instantly.")
        hint.setStyleSheet("color: #505050; font-size: 11px;")
        rl2.addWidget(hint)

        # Saved expressions list
        self._saved_scroll = QScrollArea()
        self._saved_scroll.setWidgetResizable(True)
        self._saved_scroll.setFrameShape(QFrame.NoFrame)
        self._saved_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._saved_container = QWidget()
        self._saved_layout = QVBoxLayout(self._saved_container)
        self._saved_layout.setContentsMargins(0, 0, 0, 0)
        self._saved_layout.setSpacing(6)
        self._saved_layout.setAlignment(Qt.AlignTop)
        self._saved_scroll.setWidget(self._saved_container)
        rl2.addWidget(self._saved_scroll, stretch=1)

        root.addWidget(right, stretch=2)

    # ── Saved expressions ─────────────────────────────────────────────────────

    def _load_saved(self):
        # Clear existing cards
        while self._saved_layout.count():
            item = self._saved_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._svc:
            return

        exprs = self._svc.get_saved_expressions()

        if not exprs:
            empty = QLabel("No saved expressions yet.\nClick  + New  to create one.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #484848; font-size: 12px; padding: 30px 10px;")
            self._saved_layout.addWidget(empty)
            return

        for expr in exprs:
            self._saved_layout.addWidget(self._make_saved_card(expr))

    def _make_saved_card(self, expr) -> QFrame:
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setCursor(Qt.PointingHandCursor)
        card.setToolTip(f"Click to roll  {expr.expression}")
        card.setProperty("saved_id", expr.id)

        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 8, 8, 8)
        cl.setSpacing(8)

        text = QVBoxLayout()
        text.setSpacing(2)
        name_lbl = QLabel(expr.name)
        name_lbl.setStyleSheet("font-weight: 600; font-size: 13px; color: #e0e0e0;")
        expr_lbl = QLabel(expr.expression)
        expr_lbl.setStyleSheet("font-size: 11px; color: #0078d4; font-family: monospace;")
        text.addWidget(name_lbl)
        text.addWidget(expr_lbl)
        cl.addLayout(text, stretch=1)

        edit_btn = QPushButton("✎")
        edit_btn.setFixedSize(28, 28)
        edit_btn.setToolTip("Edit")
        edit_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #505050; font-size: 14px; }"
            "QPushButton:hover { color: #d8d8d8; }"
        )
        edit_btn.clicked.connect(lambda _=False, e=expr: self._edit_saved_expr(e))

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.setToolTip("Delete")
        del_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #505050; font-size: 12px; }"
            "QPushButton:hover { color: #e05555; }"
        )
        del_btn.clicked.connect(lambda _=False, eid=expr.id: self._delete_saved_expr(eid))

        cl.addWidget(edit_btn)
        cl.addWidget(del_btn)

        # Click the card body (not the buttons) to roll
        card.mousePressEvent = lambda ev, e=expr: self._roll_saved(ev, e)

        return card

    def _roll_saved(self, event, expr):
        if event.button() == Qt.LeftButton:
            self._expr_edit.setText(expr.expression)
            self._roll_expr(expr.expression)

    def _save_current_expr(self):
        self._new_saved_expr(prefill=self._expr_edit.text().strip())

    def _new_saved_expr(self, prefill: str = ""):
        dlg = _SaveExprDialog(expression=prefill, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, expression = dlg.values()
        if self._svc:
            self._svc.add_saved_expression(name, expression)
        self._load_saved()

    def _edit_saved_expr(self, expr):
        dlg = _SaveExprDialog(expression=expr.expression, name=expr.name, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, expression = dlg.values()
        if self._svc:
            self._svc.update_saved_expression(expr.id, name, expression)
        self._load_saved()

    def _delete_saved_expr(self, expr_id: int):
        if QMessageBox.question(self, "Delete Expression",
            "Delete this saved expression?",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        if self._svc:
            self._svc.delete_saved_expression(expr_id)
        self._load_saved()

    # ── Rolling ───────────────────────────────────────────────────────────────

    def _quick_roll(self, sides: int):
        self._roll_expr(f"d{sides}")

    def _roll_custom(self):
        self._roll_expr(self._expr_edit.text().strip())

    def _roll_expr(self, expr: str):
        if not expr:
            return
        try:
            total, detail = _parse_and_roll(expr)
        except ValueError as e:
            self._detail_lbl.setText(f"Error: {e}")
            self._result_lbl.setText("!")
            self._result_lbl.setStyleSheet(
                "font-size: 56px; font-weight: 700; color: #e05555; letter-spacing: 4px;")
            return

        self._result_lbl.setText(str(total))
        self._result_lbl.setStyleSheet(
            "font-size: 56px; font-weight: 700; color: #0078d4; letter-spacing: 4px;")
        self._detail_lbl.setText(detail)

        if self._svc:
            self._svc.log_dice_roll(expr, total, detail)
        self._load_history()

    # ── History ───────────────────────────────────────────────────────────────

    def _load_history(self):
        self._hist_table.setRowCount(0)
        if not self._svc:
            return
        for roll in self._svc.get_dice_log(limit=50):
            row = self._hist_table.rowCount()
            self._hist_table.insertRow(row)
            self._hist_table.setItem(row, 0, QTableWidgetItem(roll.expression))
            result_item = QTableWidgetItem(str(roll.result))
            result_item.setTextAlignment(Qt.AlignCenter)
            result_item.setForeground(QColor("#0078d4"))
            self._hist_table.setItem(row, 1, result_item)
            self._hist_table.setItem(row, 2, QTableWidgetItem(
                (roll.timestamp or "")[:16]))

    def _clear_history(self):
        if QMessageBox.question(self, "Clear History",
            "Clear all dice roll history?",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        if self._svc:
            self._svc.clear_dice_log()
        self._load_history()


# ── Campaign List View ────────────────────────────────────────────────────────

class CampaignListView(QWidget):
    def __init__(self, context, on_open_campaign, parent=None):
        super().__init__(parent)
        self._ctx             = context
        self._on_open_campaign = on_open_campaign
        self._svc             = context.services.try_get("campaign_service")
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(20, 10, 20, 16); lay.setSpacing(12)

        # Action row (title now lives in CampaignTrackerUI above the nav bar)
        hdr = QHBoxLayout()
        hdr.addStretch()
        new_btn = QPushButton("+ New Campaign"); new_btn.setProperty("class", "primary")
        new_btn.clicked.connect(self._new_campaign)
        hdr.addWidget(new_btn)
        lay.addLayout(hdr)

        # Stat chips
        chips_row = QHBoxLayout(); chips_row.setSpacing(10)
        self._chip_total  = _stat_chip("Total Campaigns", "0")
        self._chip_active = _stat_chip("Active",          "0", "#3dba6e")
        self._chip_battles = _stat_chip("Total Battles",  "0", "#f0a020")
        self._chip_chars  = _stat_chip("Characters",      "0", "#909090")
        for c in [self._chip_total, self._chip_active, self._chip_battles, self._chip_chars]:
            chips_row.addWidget(c)
        chips_row.addStretch()
        lay.addLayout(chips_row)

        lay.addWidget(_hline())

        # Filter bar
        flt = QHBoxLayout(); flt.setSpacing(8)
        self._search = QLineEdit(); self._search.setPlaceholderText("Search campaigns…")
        self._search.textChanged.connect(self._apply_filter)
        flt.addWidget(self._search, stretch=1)
        flt.addWidget(QLabel("Status:"))
        self._status_filter = QComboBox()
        self._status_filter.addItem("All"); self._status_filter.addItems(CAMPAIGN_STATUSES)
        self._status_filter.currentTextChanged.connect(self._apply_filter)
        flt.addWidget(self._status_filter)
        lay.addLayout(flt)

        # Card grid in a scroll area
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        self._cards_w = QWidget()
        self._cards_l = QVBoxLayout(self._cards_w)
        self._cards_l.setSpacing(8)
        self._cards_l.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._cards_w)
        lay.addWidget(scroll, stretch=1)

        self._all_campaigns = []

    def refresh(self):
        self._all_campaigns = self._svc.get_all_campaigns() if self._svc else []
        self._apply_filter()
        self._update_chips()

    def _update_chips(self):
        if not self._svc: return
        stats = self._svc.get_statistics()

        def _set_chip(chip, val):
            for lbl in chip.findChildren(QLabel):
                if lbl.objectName() != "fieldLabel":
                    lbl.setText(str(val)); break

        _set_chip(self._chip_total,   stats.total_campaigns)
        _set_chip(self._chip_active,  stats.active_campaigns)
        _set_chip(self._chip_battles, stats.total_battles)
        _set_chip(self._chip_chars,   stats.total_characters)

    def _apply_filter(self):
        while self._cards_l.count():
            item = self._cards_l.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        needle     = self._search.text().strip().lower()
        status_sel = self._status_filter.currentText()

        visible = [
            c for c in self._all_campaigns
            if (not needle or needle in c.name.lower() or needle in c.game_system.lower())
            and (status_sel == "All" or c.status == status_sel)
        ]

        if not visible:
            empty = QLabel("No campaigns found. Click  \"+ New Campaign\"  to start.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #606060; padding: 60px;")
            self._cards_l.addWidget(empty)
            return

        for c in visible:
            self._cards_l.addWidget(self._make_campaign_card(c))

    def _make_campaign_card(self, c: Campaign) -> QFrame:
        card = QFrame(); card.setFrameShape(QFrame.StyledPanel)
        card.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(14)

        # Cover image or placeholder
        thumb = QLabel()
        thumb.setFixedSize(80, 64)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setObjectName("cardThumb")
        if c.cover_image_path and os.path.isfile(c.cover_image_path):
            pix = _cover_pixmap(QPixmap(c.cover_image_path), 80, 64)
            thumb.setPixmap(pix)
        else:
            thumb.setText("⚔")
        lay.addWidget(thumb)

        # Info
        info = QVBoxLayout(); info.setSpacing(3)
        name_lbl = QLabel(c.name)
        name_lbl.setObjectName("cardTitle")
        info.addWidget(name_lbl)
        sys_lbl = QLabel(c.game_system)
        sys_lbl.setObjectName("fieldLabel")
        info.addWidget(sys_lbl)
        if c.description:
            desc = QLabel(c.description[:80] + ("…" if len(c.description)>80 else ""))
            desc.setObjectName("cardDesc")
            info.addWidget(desc)
        lay.addLayout(info, stretch=1)

        # Status badge
        status_colors = {
            "Active":   "#3dba6e", "Paused":   "#f0a020",
            "Complete": "#4a9eda", "Archived": "#606060",
        }
        sc = status_colors.get(c.status, "#808080")
        s_lbl = QLabel(c.status)
        s_lbl.setStyleSheet(
            f"background: {sc}22; color: {sc}; border: 1px solid {sc}55;"
            f" border-radius: 4px; padding: 3px 10px; font-weight: 600; font-size: 11px;")
        s_lbl.setFixedHeight(24)
        lay.addWidget(s_lbl, alignment=Qt.AlignVCenter)

        # Action buttons
        btn_col = QVBoxLayout(); btn_col.setSpacing(4)
        open_btn = QPushButton("Open →"); open_btn.setProperty("class", "primary")
        open_btn.setFixedWidth(84)
        open_btn.clicked.connect(lambda _=False, camp=c: self._on_open_campaign(camp))
        del_btn  = QPushButton("Delete"); del_btn.setProperty("class", "danger")
        del_btn.setFixedWidth(84)
        del_btn.clicked.connect(lambda _=False, camp=c: self._delete_campaign(camp))
        btn_col.addWidget(open_btn); btn_col.addWidget(del_btn)
        lay.addLayout(btn_col)

        # Also open on card double-click
        card.mouseDoubleClickEvent = lambda _e, camp=c: self._on_open_campaign(camp)
        return card

    def _new_campaign(self):
        dlg = CampaignDialog(self._ctx, parent=self)
        if dlg.exec():
            self._ctx.event_bus.emit("campaign_created", dlg.result_campaign().to_dict())
            self.refresh()

    def _delete_campaign(self, c: Campaign):
        if QMessageBox.question(self, "Delete Campaign",
            f"Delete '{c.name}' and all its data? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self._svc.delete_campaign(c.id)
        self._ctx.event_bus.emit("campaign_deleted", {"id": c.id})
        self.refresh()


# ── Main Widget ───────────────────────────────────────────────────────────────

class CampaignTrackerUI(QWidget):
    def __init__(self, context):
        super().__init__()
        self._ctx = context
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Page title (matches Paint/Model/Army layout) ──────────────────────
        title_bar = QWidget()
        title_row = QHBoxLayout(title_bar)
        title_row.setContentsMargins(20, 16, 20, 6)
        title_lbl = QLabel("Campaign Tracker")
        title_lbl.setObjectName("pageTitle")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        lay.addWidget(title_bar)

        # ── Pill nav bar ─────────────────────────────────────────────────────
        # Styling is entirely handled by the global QSS rule for #ctNavBar /
        # QWidget#ctNavBar QPushButton — no inline overrides here.
        nav = QWidget()
        nav.setObjectName("ctNavBar")
        nav.setFixedHeight(42)
        nav_lay = QHBoxLayout(nav)
        nav_lay.setContentsMargins(14, 0, 14, 0)
        nav_lay.setSpacing(4)

        self._nav_btns = []
        for i, label in enumerate(["Campaigns", "Dice Roller"]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            nav_lay.addWidget(btn)
            self._nav_btns.append(btn)

        nav_lay.addStretch()
        lay.addWidget(nav)

        # ── Page stack ────────────────────────────────────────────────────────
        self._page_stack = QStackedWidget()

        # Page 0: Campaigns (list ↔ detail)
        campaigns_w = QWidget()
        cl = QVBoxLayout(campaigns_w)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self._stack = QStackedWidget()
        self._list_view   = CampaignListView(self._ctx, self._open_campaign)
        self._detail_view = CampaignDetailView(self._ctx, self._back_to_list)
        self._stack.addWidget(self._list_view)
        self._stack.addWidget(self._detail_view)
        self._stack.setCurrentIndex(0)
        cl.addWidget(self._stack)

        self._page_stack.addWidget(campaigns_w)           # index 0

        # Page 1: Dice Roller
        self._dice_roller = DiceRollerWidget(self._ctx)
        self._page_stack.addWidget(self._dice_roller)     # index 1

        lay.addWidget(self._page_stack, stretch=1)

        self._switch_page(0)

    def _switch_page(self, index: int):
        self._page_stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == index)

    def _open_campaign(self, campaign: Campaign):
        self._detail_view.load(campaign)
        self._stack.setCurrentIndex(1)

    def _back_to_list(self):
        self._list_view.refresh()
        self._stack.setCurrentIndex(0)
