"""
Model Tracker UI  —  polished, theme-consistent layout.

Tabs:
  0 — Collection   form + filter bar + table
  1 — Gallery      visual card grid with photos
  2 — Statistics   stat cards + distribution bars

New features vs previous version:
  • Form restructured into horizontal rows (matches Paint Tracker style)
  • Status shown as a coloured dot-badge in the table
  • Stat chips bar at the bottom of Collection tab
  • Duplicate Model button
  • Gallery cards larger with status dot overlay
  • Paint swatches shown inline in form (mini colour dots)
  • No inline colour overrides that fight theme.qss
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker, QSize, QEvent
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QMessageBox, QTabWidget, QSpinBox,
    QTextEdit, QListWidget, QListWidgetItem,
    QDialog, QDialogButtonBox, QSizePolicy, QFrame,
    QScrollArea, QFileDialog, QProgressBar,
)

from .models import (
    ModelFilter, ModelStatistics,
    VALID_STATUSES, STATUS_COLORS,
    COMMON_GAME_SYSTEMS, COMMON_MODEL_TYPES,
)

from plugins.shared_widgets import RelatedItemsSection


# ── tiny shared helpers ───────────────────────────────────────────────────────

def _vline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine); f.setFixedWidth(1)
    return f

def _hline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    return f

def _cover_pixmap(pix: "QPixmap", w: int, h: int) -> "QPixmap":
    """Scale-to-fill then center-crop — like CSS object-fit: cover."""
    if pix.isNull():
        return pix
    scaled = pix.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    if scaled.width() > w or scaled.height() > h:
        x = (scaled.width() - w) // 2
        y = (scaled.height() - h) // 2
        return scaled.copy(x, y, w, h)
    return scaled


def _field(label: str, widget: QWidget) -> QVBoxLayout:
    col = QVBoxLayout(); col.setSpacing(4)
    lbl = QLabel(label); lbl.setObjectName("fieldLabel")
    col.addWidget(lbl); col.addWidget(widget)
    return col


# ── Status badge helper ───────────────────────────────────────────────────────

def _status_dot(status: str, size: int = 10) -> QLabel:
    """A small coloured circle label for status."""
    dot = QLabel()
    dot.setFixedSize(size, size)
    color = STATUS_COLORS.get(status, "#888888")
    dot.setStyleSheet(
        f"background-color: {color}; border-radius: {size // 2}px;"
    )
    dot.setToolTip(status)
    return dot


# ─────────────────────────────────────────────────────────────────────────────
# PAINT LINK DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class PaintLinkDialog(QDialog):
    def __init__(self, context, current_paint_ids: list[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link Paints to Model")
        self.setMinimumSize(500, 520)
        self._context = context
        self._selected_ids = list(current_paint_ids)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        info = QLabel("Select every paint used on this model. Linked paints appear in army lists.")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search paints…")
        self._search.textChanged.connect(self._filter_list)
        lay.addWidget(self._search)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.MultiSelection)
        self._list.setAlternatingRowColors(True)
        self._list.setSpacing(1)
        lay.addWidget(self._list)

        self._populate_list()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _populate_list(self):
        paint_service = self._context.services.try_get("paint_service")
        if not paint_service:
            item = QListWidgetItem("⚠  Paint Tracker not loaded — no paints available")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self._list.addItem(item)
            return
        try:
            paints = paint_service.get_all_paints()
        except Exception as e:
            item = QListWidgetItem(f"⚠  Could not load paints: {e}")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self._list.addItem(item)
            return

        for paint in paints:
            display = f"{paint.brand}  —  {paint.name}   ({paint.paint_type})"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, paint.id)
            # colour dot via foreground hint
            if paint.id in self._selected_ids:
                item.setSelected(True)
            self._list.addItem(item)

    def _filter_list(self, text: str):
        needle = text.lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(needle not in item.text().lower())

    def _on_accept(self):
        self._selected_ids = [
            self._list.item(i).data(Qt.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).isSelected()
            and self._list.item(i).data(Qt.UserRole) is not None
        ]
        self.accept()

    def get_selected_ids(self) -> list[int]:
        return self._selected_ids


# ─────────────────────────────────────────────────────────────────────────────
# FULL-SIZE IMAGE VIEWER
# ─────────────────────────────────────────────────────────────────────────────

class _ImageViewerDialog(QDialog):
    """Shows a single image as large as the screen comfortably allows."""

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Photo Viewer")
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignCenter)
        img_lbl.setStyleSheet("background: #111; border-radius: 6px;")

        screen  = QApplication.primaryScreen().availableGeometry()
        max_w   = int(screen.width()  * 0.85)
        max_h   = int(screen.height() * 0.80)

        pix = QPixmap(path)
        if not pix.isNull():
            scaled = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_lbl.setPixmap(scaled)
            self.resize(scaled.width() + 24, scaled.height() + 70)
        else:
            img_lbl.setText("Could not load image.")
            self.resize(400, 300)

        lay.addWidget(img_lbl)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignCenter)


# ─────────────────────────────────────────────────────────────────────────────
# MODEL IMAGE GALLERY DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class ModelImageGalleryDialog(QDialog):
    """
    Full photo gallery for a single model.

    • Shows all saved images in a scrollable grid.
    • Click any thumbnail → full-size viewer.
    • Add Photos → multi-file picker (deduplicates automatically).
    • Remove / Set Primary buttons per image.
    • Backward-compatible: if the model already has image_path set but no
      gallery rows, that image is migrated into the gallery on first open.
    """

    THUMB_W   = 210
    THUMB_H   = 175
    GRID_COLS = 4

    def __init__(self, context, model, parent=None):
        super().__init__(parent)
        self.context  = context
        self.model    = model          # may have .image_path / .id
        self._service = context.services.try_get("model_service")

        self.setWindowTitle(f"{model.name} — Photo Gallery")
        self.setMinimumSize(640, 480)
        self.resize(860, 580)

        self._build_ui()
        self._migrate_legacy_image()
        self._load_images()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(10)

        title = QLabel(self.model.name)
        title.setObjectName("pageTitle")
        hdr.addWidget(title)
        hdr.addStretch()

        color = STATUS_COLORS.get(self.model.status, "#888888")
        hdr.addWidget(_status_dot(self.model.status, 10))
        s_lbl = QLabel(self.model.status)
        s_lbl.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 13px;")
        hdr.addWidget(s_lbl)
        lay.addLayout(hdr)

        sub = QLabel(f"{self.model.faction}  ·  {self.model.game_system}")
        sub.setObjectName("fieldLabel")
        lay.addWidget(sub)

        lay.addWidget(_hline())

        # ── Scroll area ──────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._grid_widget)
        lay.addWidget(scroll, stretch=1)

        # ── Bottom bar ───────────────────────────────────────────────────────
        btm = QHBoxLayout(); btm.setSpacing(8)

        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("fieldLabel")
        btm.addWidget(self._count_lbl)
        btm.addStretch()

        add_btn = QPushButton("+ Add Photos")
        add_btn.setProperty("class", "primary")
        add_btn.clicked.connect(self._add_photos)
        btm.addWidget(add_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btm.addWidget(close_btn)

        lay.addLayout(btm)

    # ── Data helpers ─────────────────────────────────────────────────────────

    def _migrate_legacy_image(self):
        """If model has image_path but no gallery rows yet, add it to the gallery."""
        if not self._service or not self.model.image_path:
            return
        if not os.path.isfile(self.model.image_path):
            return
        existing = self._service.get_images_for_model(self.model.id)
        paths    = [img["image_path"] for img in existing]
        if self.model.image_path not in paths:
            self._service.add_image(self.model.id, self.model.image_path)

    def _load_images(self):
        # Clear grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        images = self._service.get_images_for_model(self.model.id) if self._service else []

        if not images:
            lbl = QLabel('No photos yet — click  "+ Add Photos"  to get started.')
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #606060; padding: 50px;")
            self._grid.addWidget(lbl, 0, 0, 1, self.GRID_COLS)
            self._count_lbl.setText("")
            return

        n = len(images)
        self._count_lbl.setText(f"{n} photo{'s' if n != 1 else ''}")

        for i, img in enumerate(images):
            card = self._make_image_card(img)
            self._grid.addWidget(card, i // self.GRID_COLS, i % self.GRID_COLS)

    # ── Image card ───────────────────────────────────────────────────────────

    def _make_image_card(self, img: dict) -> QFrame:
        path       = img.get("image_path", "")
        img_id     = img["id"]
        is_primary = (path == self.model.image_path)

        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setFixedWidth(self.THUMB_W + 4)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(2, 2, 2, 8)
        lay.setSpacing(5)

        # ── Thumbnail ────────────────────────────────────────────────────────
        thumb = QLabel()
        thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setCursor(Qt.PointingHandCursor)
        thumb.setToolTip("Click to view full size")

        if path and os.path.isfile(path):
            pix = _cover_pixmap(QPixmap(path), self.THUMB_W, self.THUMB_H)
            thumb.setPixmap(pix)
            thumb.setStyleSheet(
                "background: #111; border-radius: 4px;"
                "border: 2px solid " + ("#f0a000;" if is_primary else "transparent;")
            )
        else:
            thumb.setText("File not found")
            thumb.setStyleSheet("background: #1c1c1c; color: #404040; border-radius: 4px;")

        thumb.mousePressEvent = lambda _e, p=path: self._view_full_size(p)
        lay.addWidget(thumb)

        # ── Primary star badge ───────────────────────────────────────────────
        if is_primary:
            badge = QLabel("★  Primary photo")
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet("color: #f0a000; font-size: 10px; font-weight: 700;")
            lay.addWidget(badge)

        # ── Action buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(5)

        if not is_primary:
            pri_btn = QPushButton("Set Primary")
            pri_btn.setFixedHeight(26)
            pri_btn.setStyleSheet("font-size: 10px; padding: 2px 8px;")
            pri_btn.clicked.connect(lambda _, p=path: self._set_primary(p))
            btn_row.addWidget(pri_btn)

        del_btn = QPushButton("Remove")
        del_btn.setFixedHeight(26)
        del_btn.setProperty("class", "danger")
        del_btn.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        del_btn.clicked.connect(lambda _, iid=img_id, p=path: self._remove_image(iid, p))
        btn_row.addWidget(del_btn)

        lay.addLayout(btn_row)
        return card

    # ── Actions ──────────────────────────────────────────────────────────────

    def _view_full_size(self, path: str):
        if path and os.path.isfile(path):
            _ImageViewerDialog(path, self).exec()

    def _add_photos(self):
        start_dir = str(
            Path(self.model.image_path).parent
            if self.model.image_path and os.path.isfile(self.model.image_path)
            else Path.home()
        )
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Photos", start_dir,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tiff *.tif)",
        )
        if not paths or not self._service:
            return
        for p in paths:
            self._service.add_image(self.model.id, p)
        # Auto-set primary if none assigned yet
        if not self.model.image_path:
            self._service.set_primary_image(self.model.id, paths[0])
            self.model.image_path = paths[0]
        self._load_images()

    def _set_primary(self, path: str):
        if self._service:
            self._service.set_primary_image(self.model.id, path)
            self.model.image_path = path
        self._load_images()

    def _remove_image(self, image_id: int, path: str):
        if not self._service:
            return
        self._service.remove_image(image_id)
        # If it was primary, promote the next available image (or None)
        if path == self.model.image_path:
            remaining = self._service.get_images_for_model(self.model.id)
            new_primary = remaining[0]["image_path"] if remaining else None
            self._service.set_primary_image(self.model.id, new_primary)
            self.model.image_path = new_primary
        self._load_images()


# ─────────────────────────────────────────────────────────────────────────────
# LINKED PAINTS VIEW DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class LinkedPaintsViewDialog(QDialog):
    def __init__(self, context, paint_ids: list[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Linked Paints")
        self.setMinimumSize(540, 400)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        if not paint_ids:
            lbl = QLabel("No paints linked to this model.")
            lbl.setAlignment(Qt.AlignCenter)
            lay.addWidget(lbl)
        else:
            paint_service = context.services.try_get("paint_service")
            table = QTableWidget()
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(["", "Brand", "Name", "Type"])
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionMode(QTableWidget.NoSelection)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            table.setShowGrid(False)
            table.setRowCount(len(paint_ids))

            for row, pid in enumerate(paint_ids):
                paint = None
                if paint_service:
                    try:
                        paint = paint_service.get_paint(pid)
                    except Exception:
                        pass

                color_hex = getattr(paint, "color", "#888888") if paint else "#888888"
                if not color_hex or not color_hex.startswith("#"):
                    color_hex = "#888888"

                # Swatch cell
                sw_w = QWidget()
                sw_l = QHBoxLayout(sw_w)
                sw_l.setContentsMargins(8, 4, 8, 4)
                swatch = QLabel()
                swatch.setFixedSize(24, 24)
                bright = QColor(color_hex).lightness()
                border = "rgba(255,255,255,0.12)" if bright < 128 else "rgba(0,0,0,0.18)"
                swatch.setStyleSheet(
                    f"background-color:{color_hex}; border:1px solid {border}; border-radius:4px;"
                )
                swatch.setToolTip(color_hex)
                sw_l.addWidget(swatch, alignment=Qt.AlignCenter)
                table.setCellWidget(row, 0, sw_w)
                table.setRowHeight(row, 40)

                table.setItem(row, 1, QTableWidgetItem(getattr(paint, "brand", "—") if paint else "—"))
                table.setItem(row, 2, QTableWidgetItem(getattr(paint, "name", f"ID {pid}") if paint else f"ID {pid}"))
                table.setItem(row, 3, QTableWidgetItem(getattr(paint, "paint_type", "—") if paint else "—"))

            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.Fixed);  table.setColumnWidth(0, 48)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(2, QHeaderView.Stretch)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            lay.addWidget(table)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)


# ─────────────────────────────────────────────────────────────────────────────
# LIBRARY IMPORT DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class LibraryImportDialog(QDialog):
    """
    Parse one or more JSON unit library files and let the user select which
    entries to bulk-import as models.

    Supported schemas (auto-detected):
      • Warhammer 40K  — top-level array; fields: unitname, factionname,
                         keywords[].words, stats[], unitcompo, abilities{}
      • Age of Sigmar 4e warscrolls — single object per file; fields: name,
                         faction, keywords (flat list), sizes, stats{}, abilities[]
    """

    _TYPE_MAP = [
        ("titan",      "Titan / Super-heavy"),
        ("warmaster",  "Character / Hero"),
        ("primarch",   "Character / Hero"),
        ("walker",     "Vehicle"),
        ("vehicle",    "Vehicle"),
        ("monster",    "Monster / Beast"),
        ("cavalry",    "Cavalry"),
        ("battlesuit", "Infantry"),
        ("character",  "Character / Hero"),
        ("hero",       "Character / Hero"),
        ("infantry",   "Infantry"),
    ]

    def __init__(self, context, paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Models from Library")
        self.setMinimumSize(700, 500)
        self.resize(900, 620)
        self.context = context
        self._all_units: list[dict] = []   # normalised internal format
        self._visible_rows: list[dict] = []
        self._file_count = 0

        self._load_files(paths)

        if not self._all_units:
            QMessageBox.warning(
                parent, "No units found",
                "No recognisable unit data was found in the selected file(s).",
            )
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.reject)
            return

        self._build_ui()
        self._repopulate()
        self._autodetect_game_system()

    # ── File loading & normalisation ──────────────────────────────────────────

    def _load_files(self, paths: list[str]):
        import json
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                before = len(self._all_units)
                self._parse_data(data)
                if len(self._all_units) > before:
                    self._file_count += 1
                else:
                    # Still count the file even if we got 0 units — the user
                    # can see the file loaded but produced nothing
                    self._file_count += 1
            except Exception as e:
                print(f"[LIBRARY IMPORT] Parse error — {Path(path).name}: {e}")

    # ── Format detection ──────────────────────────────────────────────────────

    def _parse_data(self, data):
        """Top-level dispatcher — handles any supported JSON structure."""
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    self._parse_unit(item)

        elif isinstance(data, dict):
            # ── Container formats: dict with a list of units under a known key ─
            for key in ("units", "warscrolls", "datasheets", "models",
                        "dataCards", "entries", "catalogue"):
                if key in data and isinstance(data[key], list):
                    # Inherit faction from container if items don't carry one
                    container_faction = (
                        data.get("faction") or data.get("name") or ""
                    )
                    for item in data[key]:
                        if isinstance(item, dict):
                            if not item.get("faction") and not item.get("factionname"):
                                item = dict(item)   # shallow copy — don't mutate
                                item.setdefault("_container_faction", container_faction)
                            self._parse_unit(item)
                    return  # handled as container

            # ── Single-unit dict ──────────────────────────────────────────────
            self._parse_unit(data)

    def _parse_unit(self, unit: dict):
        """Detect the schema of a single unit dict and normalise it."""
        # 40k: has 'unitname' field (Hoplite-Research / community 40k exports)
        if unit.get("unitname"):
            self._all_units.append(self._normalize_40k(unit))
            return

        # Explicit AoS schema hint
        schema = unit.get("$schema", "")
        if "aos" in schema.lower() or unit.get("type") in ("warscroll", "warscrolls"):
            name = unit.get("name", "").strip()
            if name:
                self._all_units.append(self._normalize_aos(unit))
            return

        # Generic: any dict with a name string is worth attempting
        name = (
            unit.get("name") or unit.get("unitname") or
            unit.get("unit_name") or unit.get("title") or ""
        ).strip()
        if not name:
            return

        # Detect 40k vs AoS by field presence
        has_40k_fields = bool(
            unit.get("factionname") or unit.get("unitcompo") or
            unit.get("stats") and isinstance(unit.get("stats"), list)
        )
        if has_40k_fields:
            self._all_units.append(self._normalize_40k(unit))
            return

        # Anything else: use the flexible AoS normaliser
        self._all_units.append(self._normalize_aos_flexible(unit))

        # Deduplicate by name+faction
        seen: set[tuple] = set()
        deduped: list[dict] = []
        for u in self._all_units:
            key = (u["_name"].lower(), u["_faction"].lower())
            if key not in seen:
                seen.add(key)
                deduped.append(u)
        self._all_units = deduped

    def _normalize_40k(self, unit: dict) -> dict:
        name    = unit.get("unitname", "Unknown").strip().title()
        faction = unit.get("factionname", "").strip() or "Unknown"

        keywords: list[str] = []
        for grp in unit.get("keywords", []):
            if isinstance(grp, dict):
                keywords.extend(grp.get("words", []))
            elif isinstance(grp, str):
                keywords.append(grp)

        qty = 1
        for compo in unit.get("unitcompo", {}).get("units", []):
            try:
                qty = int(compo.get("amount", 1)); break
            except (ValueError, TypeError):
                pass

        notes_lines = []
        stats_list = unit.get("stats", [])
        if stats_list and isinstance(stats_list, list):
            s = stats_list[0]
            notes_lines.append(
                f"M:{s.get('m','—')}  T:{s.get('t','—')}  Sv:{s.get('sv','—')}  "
                f"W:{s.get('w','—')}  Ld:{s.get('ld','—')}  OC:{s.get('oc','—')}"
            )
        abilities = unit.get("abilities", {})
        if isinstance(abilities, dict):
            core_ab = abilities.get("core", [])
            if core_ab:
                notes_lines.append(f"Core abilities: {', '.join(core_ab)}")
            faction_ab = abilities.get("faction", [])
            if faction_ab:
                notes_lines.append(f"Faction abilities: {', '.join(faction_ab)}")
            inv = abilities.get("invulnerablesave", [])
            if inv and isinstance(inv, list) and isinstance(inv[0], dict) and inv[0].get("save"):
                notes_lines.append(f"Invulnerable save: {inv[0]['save']}")
        if keywords:
            notes_lines.append(f"Keywords: {', '.join(keywords)}")
        flavor = unit.get("flavortext", "").strip()
        if flavor:
            notes_lines.append(f"\n{flavor}")

        notes = "\n".join(notes_lines)
        if len(notes) > 1990:
            notes = notes[:1990] + "…"

        kw_lower = {w.lower() for w in keywords}
        return {
            "_name":           name,
            "_faction":        faction,
            "_grand_alliance": "",
            "_model_type":     self._infer_type(kw_lower, ""),
            "_quantity":       qty,
            "_keywords":       keywords,
            "_notes":          notes,
            "_schema":         "40k",
        }

    def _normalize_aos(self, unit: dict) -> dict:
        name           = unit.get("name", "Unknown").strip().title()
        grand_alliance = unit.get("grandAlliance", "").strip()
        role           = unit.get("role", "")
        # Faction must not be empty — fall back to grand alliance then "Unknown"
        faction = (
            unit.get("faction", "").strip().title()
            or grand_alliance.title()
            or "Unknown"
        )

        # keywords is a flat list of strings
        keywords = [k for k in unit.get("keywords", []) if isinstance(k, str)]

        sizes = unit.get("sizes", {})
        qty = sizes.get("default") or sizes.get("min") or 1
        try:
            qty = int(qty)
        except (ValueError, TypeError):
            qty = 1

        notes_lines = []
        stats = unit.get("stats", {})
        if stats and isinstance(stats, dict):
            parts = []
            if stats.get("move"):    parts.append(f"Move: {stats['move']}")
            if stats.get("health"):  parts.append(f"Health: {stats['health']}")
            if stats.get("save"):    parts.append(f"Save: {stats['save']}")
            if stats.get("control"): parts.append(f"Control: {stats['control']}")
            if parts:
                notes_lines.append("  ".join(parts))

        meta = []
        if grand_alliance: meta.append(f"Alliance: {grand_alliance.title()}")
        if role:           meta.append(f"Role: {role.title()}")
        if meta:
            notes_lines.append("  ".join(meta))

        weapons = unit.get("weapons", [])
        if weapons:
            notes_lines.append("Weapons:")
            for w in weapons:
                atk = (f"  {w.get('name','')} ({w.get('type','').title()}): "
                       f"{w.get('attacks','')}A / {w.get('hit','')} / "
                       f"{w.get('wound','')} / Rend {w.get('rend',0)} / "
                       f"D{w.get('damage','')}")
                notes_lines.append(atk)
                wab = w.get("abilities", [])
                if wab:
                    notes_lines.append(f"    [{', '.join(wab)}]")

        abilities = unit.get("abilities", [])
        if abilities and isinstance(abilities, list):
            notes_lines.append("Abilities:")
            for ab in abilities:
                if not isinstance(ab, dict):
                    continue
                ab_name   = ab.get("name", "")
                ab_effect = ab.get("effect", "")
                line = f"  {ab_name}: {ab_effect}" if ab_effect else f"  {ab_name}"
                if ab_name:
                    notes_lines.append(line)

        if keywords:
            notes_lines.append(f"Keywords: {', '.join(keywords)}")

        notes = "\n".join(notes_lines)
        if len(notes) > 1990:
            notes = notes[:1990] + "…"

        kw_lower = {k.lower() for k in keywords}
        return {
            "_name":           name,
            "_faction":        faction,
            "_grand_alliance": grand_alliance,
            "_model_type":     self._infer_type(kw_lower, role),
            "_quantity":       qty,
            "_keywords":       keywords,
            "_notes":          notes,
            "_schema":         "aos",
        }

    def _normalize_aos_flexible(self, unit: dict) -> dict:
        """
        Permissive normaliser for AoS / generic JSON that uses varied field names.
        Attempts to extract meaningful data regardless of exact key naming.
        """
        def _first(*keys):
            for k in keys:
                v = unit.get(k)
                if v:
                    return str(v).strip()
            return ""

        name = _first("name", "unit_name", "unitname", "title") or "Unknown"
        name = name.strip().title()

        # grand_alliance must be defined before faction (used as fallback)
        grand_alliance = _first("grandAlliance", "grand_alliance", "alliance", "order")
        faction = (
            _first(
                "faction", "factionname", "allegiance", "subfaction",
                "_container_faction",
            )
            or grand_alliance.title()
            or "Unknown"
        )

        # Role / type
        role = _first("role", "type", "category", "classification")

        # Keywords — accept list of strings OR list of dicts
        raw_kw = unit.get("keywords") or unit.get("keyword") or []
        keywords: list[str] = []
        if isinstance(raw_kw, list):
            for k in raw_kw:
                if isinstance(k, str):
                    keywords.append(k)
                elif isinstance(k, dict):
                    keywords.extend(
                        str(v) for v in k.values() if isinstance(v, str)
                    )

        # Quantity — check a variety of size fields
        qty = 1
        for field in ("sizes", "models_per_unit", "model_count", "quantity",
                      "unit_size", "min_models"):
            val = unit.get(field)
            if isinstance(val, dict):
                val = val.get("default") or val.get("min") or val.get("max") or 1
            if val is not None:
                try:
                    qty = max(1, int(val)); break
                except (ValueError, TypeError):
                    pass

        # Build a human-readable notes string from whatever stats exist
        notes_lines = []

        # Stats block — many possible shapes
        stats = unit.get("stats") or unit.get("profile") or {}
        if isinstance(stats, dict) and stats:
            parts = []
            for label, keys in [
                ("Move",    ["move", "m", "movement"]),
                ("Health",  ["health", "wounds", "w", "hp"]),
                ("Save",    ["save", "sv", "armour"]),
                ("Control", ["control", "ld", "leadership", "bravery"]),
                ("OC",      ["oc", "objective_control"]),
            ]:
                val = next((stats[k] for k in keys if k in stats), None)
                if val is not None:
                    parts.append(f"{label}: {val}")
            if parts:
                notes_lines.append("  ".join(parts))
        elif isinstance(stats, list) and stats and isinstance(stats[0], dict):
            # 40k-style stats list
            s = stats[0]
            row = "  ".join(
                f"{k.upper()}: {v}" for k, v in s.items()
                if isinstance(v, (str, int, float))
            )
            if row:
                notes_lines.append(row)

        if grand_alliance:
            notes_lines.append(f"Alliance: {grand_alliance.title()}")
        if role:
            notes_lines.append(f"Role: {role.title()}")

        points = unit.get("points") or unit.get("pts") or unit.get("points_cost")
        if points:
            notes_lines.append(f"Points: {points}")

        if keywords:
            notes_lines.append(f"Keywords: {', '.join(keywords)}")

        # Description / flavour
        for fld in ("description", "flavortext", "flavour_text", "lore", "notes"):
            text = unit.get(fld, "").strip() if isinstance(unit.get(fld), str) else ""
            if text:
                notes_lines.append(f"\n{text[:400]}")
                break

        notes = "\n".join(notes_lines)
        if len(notes) > 1990:
            notes = notes[:1990] + "…"

        kw_lower = {k.lower() for k in keywords}
        return {
            "_name":           name,
            "_faction":        faction,
            "_grand_alliance": grand_alliance,
            "_model_type":     self._infer_type(kw_lower, role.lower()),
            "_quantity":       qty,
            "_keywords":       keywords,
            "_notes":          notes,
            "_schema":         "flexible",
        }

    def _infer_type(self, kw_lower: set, role: str) -> str:
        if role == "hero":
            return "Character / Hero"
        for kw, model_type in self._TYPE_MAP:
            if kw in kw_lower:
                return model_type
        return "Infantry"

    # ── Game system detection ─────────────────────────────────────────────────

    def _autodetect_game_system(self):
        """
        Inspect the loaded unit schemas and grand alliances to pre-select the
        most likely game system so the user doesn't have to change it manually.
        """
        if not self._all_units:
            return

        schemas = [u.get("_schema", "") for u in self._all_units]
        alliances = [u.get("_grand_alliance", "").lower() for u in self._all_units]

        # Count how many units come from each schema
        aos_count = schemas.count("aos") + schemas.count("flexible")
        k40_count = schemas.count("40k")

        # AoS grand alliance keywords that only appear in AoS data
        aos_alliance_words = {"order", "chaos", "destruction", "death", "undead"}
        has_aos_alliance = any(a in aos_alliance_words for a in alliances)

        if aos_count > k40_count or has_aos_alliance:
            target = "Warhammer: Age of Sigmar"
        elif k40_count > 0:
            target = "Warhammer 40,000"
        else:
            return   # leave as-is (first item in list)

        idx = self._gs_combo.findText(target)
        if idx >= 0:
            self._gs_combo.setCurrentIndex(idx)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        # ── info bar ─────────────────────────────────────────────────────────
        n  = len(self._all_units)
        fc = self._file_count
        info_lbl = QLabel(
            f"Loaded {n} unit{'s' if n != 1 else ''} "
            f"from {fc} file{'s' if fc != 1 else ''}"
        )
        info_lbl.setObjectName("fieldLabel")
        layout.addWidget(info_lbl)

        # ── controls bar ─────────────────────────────────────────────────────
        ctrl = QFrame(); ctrl.setFrameShape(QFrame.StyledPanel)
        cl = QHBoxLayout(ctrl); cl.setContentsMargins(10, 8, 10, 8); cl.setSpacing(8)

        cl.addWidget(QLabel("Game System:"))
        self._gs_combo = QComboBox()
        self._gs_combo.addItems(COMMON_GAME_SYSTEMS)
        self._gs_combo.setMinimumWidth(180)
        cl.addWidget(self._gs_combo)

        cl.addWidget(_vline())

        cl.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by name or faction…")
        self._search.textChanged.connect(self._repopulate)
        cl.addWidget(self._search, stretch=2)

        cl.addWidget(QLabel("Faction:"))
        self._faction_filter = QComboBox()
        self._faction_filter.setMinimumWidth(160)
        self._faction_filter.addItem("All Factions")
        factions = sorted({u["_faction"] for u in self._all_units if u["_faction"]})
        self._faction_filter.addItems(factions)
        self._faction_filter.currentTextChanged.connect(self._repopulate)
        cl.addWidget(self._faction_filter)

        cl.addWidget(_vline())

        sel_all_btn = QPushButton("All")
        sel_all_btn.setFixedWidth(44)
        sel_all_btn.clicked.connect(self._select_all)
        sel_none_btn = QPushButton("None")
        sel_none_btn.setFixedWidth(48)
        sel_none_btn.clicked.connect(self._select_none)
        cl.addWidget(sel_all_btn)
        cl.addWidget(sel_none_btn)
        layout.addWidget(ctrl)

        # ── unit table ────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Unit Name", "Faction", "Type", "Keywords"])
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        th = self._table.horizontalHeader()
        th.setSectionResizeMode(0, QHeaderView.Stretch)
        th.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        th.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        th.setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self._table, stretch=1)

        # Wire up checkbox tracking.
        # itemChanged fires when Qt auto-toggles the indicator; cellClicked fires
        # for any cell click.  Both are needed to handle all interaction cases.
        self._last_changed_item = None   # set by _on_item_changed, read by _on_cell_clicked
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellClicked.connect(self._on_cell_clicked)

        # ── footer ────────────────────────────────────────────────────────────
        # Inline result label — replaces blocking QMessageBox for import results
        self._result_lbl = QLabel("")
        self._result_lbl.setObjectName("formStatusErr")
        self._result_lbl.setWordWrap(True)
        self._result_lbl.setVisible(False)
        layout.addWidget(self._result_lbl)

        foot = QHBoxLayout()
        self._count_lbl = QLabel("0 selected")
        self._count_lbl.setObjectName("fieldLabel")
        foot.addWidget(self._count_lbl)
        foot.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self._import_btn = QPushButton("Import Selected")
        self._import_btn.setProperty("class", "primary")
        self._import_btn.setEnabled(False)
        self._import_btn.clicked.connect(self._do_import)
        foot.addWidget(cancel_btn)
        foot.addWidget(self._import_btn)
        layout.addLayout(foot)

    # ── population ────────────────────────────────────────────────────────────

    def _repopulate(self):
        self._table.blockSignals(True)
        try:
            needle      = self._search.text().strip().lower()
            faction_sel = self._faction_filter.currentText()

            self._table.setRowCount(0)
            self._visible_rows = []

            for unit in self._all_units:
                name    = unit["_name"]
                faction = unit["_faction"]

                if faction_sel not in ("All Factions", "") and faction != faction_sel:
                    continue
                if needle and needle not in name.lower() and needle not in faction.lower():
                    continue

                row = self._table.rowCount()
                self._table.insertRow(row)

                name_item = QTableWidgetItem(name)
                name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                name_item.setCheckState(Qt.Unchecked)
                self._table.setItem(row, 0, name_item)
                self._table.setItem(row, 1, QTableWidgetItem(faction))
                self._table.setItem(row, 2, QTableWidgetItem(unit["_model_type"]))

                kw_item = QTableWidgetItem(", ".join(unit["_keywords"][:7]))
                kw_item.setForeground(QColor("#686868"))
                self._table.setItem(row, 3, kw_item)

                self._visible_rows.append({"item": name_item, "unit": unit})
        finally:
            self._table.blockSignals(False)

        self._refresh_count()

    def _on_item_changed(self, item):
        """Qt auto-toggled the checkbox indicator — record it so _on_cell_clicked
        knows not to double-toggle, then refresh the counter."""
        self._last_changed_item = item
        self._refresh_count()

    def _on_cell_clicked(self, row: int, _col: int):
        """Any cell in the row was clicked.  Toggle the checkbox — unless Qt
        just did it via the indicator (detected via _last_changed_item)."""
        name_item = self._table.item(row, 0)
        if name_item is None:
            return
        if name_item is self._last_changed_item:
            # Indicator click: Qt already toggled the state, itemChanged already
            # refreshed the counter — nothing more to do.
            self._last_changed_item = None
            return
        # Row text / other column clicked: toggle manually.
        self._last_changed_item = None
        with QSignalBlocker(self._table):
            new_state = Qt.Unchecked if name_item.checkState() == Qt.Checked else Qt.Checked
            name_item.setCheckState(new_state)
        self._refresh_count()

    def _refresh_count(self):
        n = sum(1 for r in self._visible_rows if r["item"].checkState() == Qt.Checked)
        self._count_lbl.setText(f"{n} selected")
        self._import_btn.setEnabled(n > 0)

    def _select_all(self):
        self._table.blockSignals(True)
        try:
            for r in self._visible_rows:
                r["item"].setCheckState(Qt.Checked)
        finally:
            self._table.blockSignals(False)
        self._refresh_count()

    def _select_none(self):
        self._table.blockSignals(True)
        try:
            for r in self._visible_rows:
                r["item"].setCheckState(Qt.Unchecked)
        finally:
            self._table.blockSignals(False)
        self._refresh_count()

    # ── import ────────────────────────────────────────────────────────────────

    def _do_import(self):
        # Call the service directly so we can detect and report failures per row.
        # Using the event bus here masked ValidationErrors — the handler caught them
        # internally and _do_import always counted the emit as a success (bug fix).
        svc = self.context.services.try_get("model_service")
        if not svc:
            QMessageBox.critical(
                self, "Error",
                "Model Tracker service is not available.\n"
                "Make sure the Model Tracker plugin is enabled.",
            )
            return

        game_system = self._gs_combo.currentText()
        imported: list[str] = []
        errors:   list[tuple[str, str]] = []

        for r in self._visible_rows:
            if r["item"].checkState() != Qt.Checked:
                continue
            unit = r["unit"]
            try:
                model = svc.add_model(
                    name=unit["_name"],
                    game_system=game_system,
                    faction=unit["_faction"] or "Unknown",
                    model_type=unit["_model_type"],
                    status="Unassembled",
                    scale="28mm",
                    quantity=unit["_quantity"],
                    notes=unit["_notes"] or None,
                    linked_paint_ids=[],
                )
                imported.append(model.name)
                # Notify dashboard / other plugins
                self.context.event_bus.emit("model_added", model.to_dict())
            except Exception as e:
                errors.append((unit["_name"], str(e)))
                print(f"[LIBRARY IMPORT] {unit['_name']}: {e}")

        # ── Result summary ────────────────────────────────────────────────────
        parts = []
        if imported:
            parts.append(f"✓  {len(imported)} model{'s' if len(imported) != 1 else ''} imported")
        if errors:
            parts.append(f"✗  {len(errors)} failed")

        detail_lines = []
        if imported:
            detail_lines.append(f"Added ({len(imported)}):")
            for name in imported:
                detail_lines.append(f"  {name}")
        if errors:
            if detail_lines:
                detail_lines.append("")
            detail_lines.append(f"Failed ({len(errors)}):")
            for name, reason in errors:
                detail_lines.append(f"  {name}: {reason}")

        summary = " · ".join(parts) if parts else "Nothing imported"

        if errors and not imported:
            # All failed — show inline error, keep dialog open
            self._result_lbl.setObjectName("formStatusErr")
            self._result_lbl.style().unpolish(self._result_lbl)
            self._result_lbl.style().polish(self._result_lbl)
            self._result_lbl.setText(
                summary + "\n" + "\n".join(f"  ✗ {n}: {r}" for n, r in errors)
            )
            self._result_lbl.setVisible(True)
        elif errors:
            # Partial success — show summary, keep dialog open so user sees what failed
            self._result_lbl.setObjectName("formStatusWarn")
            self._result_lbl.style().unpolish(self._result_lbl)
            self._result_lbl.style().polish(self._result_lbl)
            self._result_lbl.setText(
                summary + "\n" + "\n".join(f"  ✗ {n}: {r}" for n, r in errors)
            )
            self._result_lbl.setVisible(True)
            # Disable import button — remaining unchecked items won't re-import cleanly
            self._import_btn.setEnabled(False)
        else:
            # Full success — close silently; model_added events update the main roster
            self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────────────────────────────────────

class ModelUI(QWidget):

    TABLE_COLUMNS = ["Name", "Game System", "Faction", "Type", "Status", "Scale", "Qty", "Paints"]
    SORT_COL_MAP = {
        0: "name", 1: "game_system", 2: "faction",
        3: "model_type", 4: "status", 5: "scale", 6: "quantity",
    }

    GALLERY_COLS    = 5
    GALLERY_CARD_W  = 170
    GALLERY_THUMB_H = 140

    def __init__(self, context):
        super().__init__()
        self.context = context
        self._editing_id: int | None = None
        self._linked_paint_ids: list[int] = []
        self._image_path: str | None = None
        self._current_filter = ModelFilter()
        self._gallery_models: list = []
        self._build_ui()
        self._connect_signals()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(12)

        title = QLabel("Model Tracker")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs)
        self._tabs.addTab(self._build_collection_tab(), "Collection")
        self._tabs.addTab(self._build_gallery_tab(),    "Gallery")
        self._tabs.addTab(self._build_stats_tab(),      "Statistics")

    # ── Collection tab ───────────────────────────────────────────────────────

    def _build_collection_tab(self) -> QWidget:
        tab = QWidget()
        outer = QHBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Left pane: toolbar + filter + table + chips ──────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 12, 14, 12)
        ll.setSpacing(8)
        ll.addLayout(self._build_toolbar())
        ll.addWidget(self._build_filter_bar())
        ll.addWidget(self._build_table(), stretch=1)
        ll.addWidget(self._build_stat_chips())

        # ── Right pane: detail / edit panel ─────────────────────────────────
        self._detail_panel = self._build_detail_panel()
        self._detail_panel.setMinimumWidth(260)
        self._detail_panel.setMaximumWidth(370)
        self._detail_panel.setVisible(False)

        self._detail_sep = QFrame()
        self._detail_sep.setFrameShape(QFrame.VLine)
        self._detail_sep.setVisible(False)

        outer.addWidget(left, stretch=1)
        outer.addWidget(self._detail_sep)
        outer.addWidget(self._detail_panel)

        return tab

    def _build_toolbar(self) -> QHBoxLayout:
        """Top action bar above the table."""
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)

        self._new_model_btn = QPushButton("+ Add Model")
        self._new_model_btn.setProperty("class", "primary")
        self._new_model_btn.setFixedHeight(32)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedHeight(32)
        self._edit_btn.setEnabled(False)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setProperty("class", "danger")
        self._delete_btn.setFixedHeight(32)
        self._delete_btn.setEnabled(False)

        self._import_library_btn = QPushButton("Import Library…")
        self._import_library_btn.setFixedHeight(32)
        self._import_library_btn.setToolTip(
            "Import models from a JSON unit library file\n"
            "(e.g. Warhammer 40K or Age of Sigmar unit data)"
        )

        lay.addWidget(self._new_model_btn)
        lay.addWidget(self._edit_btn)
        lay.addWidget(self._delete_btn)
        lay.addWidget(_vline())
        lay.addWidget(self._import_library_btn)
        lay.addStretch()

        self._result_label = QLabel("No models")
        self._result_label.setObjectName("fieldLabel")
        lay.addWidget(self._result_label)

        return lay

    def _build_detail_panel(self) -> QWidget:
        """Slide-in detail / edit panel on the right side of the collection tab.

        Structure
        ---------
        panel (QWidget)
          outer_lay (QVBoxLayout, no padding)
            scroll_area (QScrollArea, stretch=1)   ← all fields scroll here
              scroll_content (QWidget)
                content_lay (QVBoxLayout, padded)
                  header, identity fields, notes, photo, paints, projects…
            bottom_strip (QWidget)                 ← buttons pinned to bottom
              bottom_lay (QVBoxLayout, padded)
                divider + action buttons + status label

        This prevents the panel (and the window) from growing beyond the
        available height no matter how much content is present.
        """
        panel = QWidget()
        panel.setObjectName("detailPanel")

        outer_lay = QVBoxLayout(panel)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        # ── Scrollable content area ──────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        scroll_content = QWidget()
        scroll_content.setObjectName("detailPanel")   # keeps QSS consistent
        lay = QVBoxLayout(scroll_content)
        lay.setContentsMargins(16, 14, 16, 8)
        lay.setSpacing(9)

        scroll.setWidget(scroll_content)
        outer_lay.addWidget(scroll, stretch=1)

        # ── Panel header ────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(8)
        self._panel_title = QLabel("Add Model")
        self._panel_title.setObjectName("cardTitle")
        self._panel_close_btn = QPushButton("✕")
        self._panel_close_btn.setFixedSize(26, 26)
        self._panel_close_btn.setFlat(True)
        self._panel_close_btn.setToolTip("Close panel")
        self._panel_close_btn.setObjectName("panelCloseBtn")
        self._panel_close_btn.setStyleSheet("")
        hdr.addWidget(self._panel_title)
        hdr.addStretch()
        hdr.addWidget(self._panel_close_btn)
        lay.addLayout(hdr)
        lay.addWidget(_hline())

        # ── Identity fields ─────────────────────────────────────────────────
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Primaris Intercessor")
        lay.addLayout(_field("Name *", self.name_input))

        self.game_system_input = QComboBox()
        self.game_system_input.setEditable(True)
        self.game_system_input.setInsertPolicy(QComboBox.NoInsert)
        self.game_system_input.addItems([""] + COMMON_GAME_SYSTEMS)
        lay.addLayout(_field("Game System *", self.game_system_input))

        self.faction_input = QComboBox()
        self.faction_input.setEditable(True)
        self.faction_input.setInsertPolicy(QComboBox.NoInsert)
        self.faction_input.setPlaceholderText("e.g. Space Marines")
        lay.addLayout(_field("Faction / Collection *", self.faction_input))

        self.type_input = QComboBox()
        self.type_input.setEditable(True)
        self.type_input.setInsertPolicy(QComboBox.NoInsert)
        self.type_input.addItems([""] + COMMON_MODEL_TYPES)
        lay.addLayout(_field("Model Type *", self.type_input))

        # ── Status / Scale / Qty row ────────────────────────────────────────
        row_ssq = QHBoxLayout(); row_ssq.setSpacing(8)
        self.status_combo = QComboBox()
        self.status_combo.addItems(VALID_STATUSES)
        row_ssq.addLayout(_field("Status", self.status_combo), stretch=3)
        self.scale_input = QLineEdit()
        self.scale_input.setPlaceholderText("28mm")
        row_ssq.addLayout(_field("Scale", self.scale_input), stretch=2)
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 9999)
        self.qty_spin.setValue(1)
        self.qty_spin.setFixedWidth(72)
        row_ssq.addLayout(_field("Qty", self.qty_spin))
        lay.addLayout(row_ssq)

        # ── Notes ────────────────────────────────────────────────────────────
        notes_lbl = QLabel("Notes"); notes_lbl.setObjectName("fieldLabel")
        lay.addWidget(notes_lbl)
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Assembly notes, paint recipe, purchase info…")
        self.notes_input.setFixedHeight(68)
        lay.addWidget(self.notes_input)

        lay.addWidget(_hline())

        # ── Photo ────────────────────────────────────────────────────────────
        photo_lbl = QLabel("Photo"); photo_lbl.setObjectName("fieldLabel")
        lay.addWidget(photo_lbl)
        photo_row = QHBoxLayout(); photo_row.setSpacing(10)
        self._image_label = QLabel("No photo")
        self._image_label.setFixedSize(72, 54)
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setStyleSheet(
            "background:#1a1a1a; border:1px solid #363636; border-radius:4px;"
            " color:#585858; font-size:10px;"
        )
        photo_row.addWidget(self._image_label)
        img_btns = QHBoxLayout(); img_btns.setSpacing(4)
        self._choose_image_btn = QPushButton("Choose…")
        self._choose_image_btn.setFixedHeight(26)
        self._clear_image_btn = QPushButton("Clear")
        self._clear_image_btn.setFixedHeight(26)
        img_btns.addWidget(self._choose_image_btn)
        img_btns.addWidget(self._clear_image_btn)
        img_btns.addStretch()
        photo_row.addLayout(img_btns, stretch=1)
        lay.addLayout(photo_row)

        # ── Linked paints ────────────────────────────────────────────────────
        paints_lbl = QLabel("Linked Paints"); paints_lbl.setObjectName("fieldLabel")
        lay.addWidget(paints_lbl)
        self._linked_paints_label = QLabel("None")
        self._linked_paints_label.setWordWrap(True)
        lay.addWidget(self._linked_paints_label)
        self._swatches_row = QHBoxLayout()
        self._swatches_row.setSpacing(3)
        self._swatches_row.setAlignment(Qt.AlignLeft)
        lay.addLayout(self._swatches_row)
        paint_btns = QHBoxLayout(); paint_btns.setSpacing(4)
        self._view_paints_btn = QPushButton("View")
        self._view_paints_btn.setEnabled(False)
        self._manage_paints_btn = QPushButton("Manage")
        paint_btns.addWidget(self._view_paints_btn)
        paint_btns.addWidget(self._manage_paints_btn)
        paint_btns.addStretch()
        lay.addLayout(paint_btns)

        # ── Used in Projects back-link ───────────────────────────────────────
        lay.addWidget(_hline())
        self._projects_section = RelatedItemsSection(title="USED IN PROJECTS", icon="📁")
        self._projects_section.navigate_requested.connect(
            lambda pid, _eid: self._emit_navigate(pid)
        )
        self._projects_section.set_empty("Not linked to any project.")
        lay.addWidget(self._projects_section)

        # Spacer fills leftover space so content stays top-aligned
        lay.addStretch()

        # ── Bottom strip — action buttons pinned outside the scroll ──────────
        bottom_strip = QWidget()
        bottom_strip.setObjectName("detailPanelBottom")
        bottom_lay = QVBoxLayout(bottom_strip)
        bottom_lay.setContentsMargins(16, 6, 16, 12)
        bottom_lay.setSpacing(6)
        bottom_lay.addWidget(_hline())

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self._add_btn = QPushButton("Add Model")
        self._add_btn.setProperty("class", "primary")
        self._add_btn.setFixedHeight(34)
        self._update_btn = QPushButton("Save Changes")
        self._update_btn.setProperty("class", "primary")
        self._update_btn.setFixedHeight(34)
        self._update_btn.setVisible(False)
        self._duplicate_btn = QPushButton("Duplicate")
        self._duplicate_btn.setFixedHeight(34)
        self._duplicate_btn.setVisible(False)
        self._duplicate_btn.setToolTip("Create a copy of this model")
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedHeight(34)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._update_btn)
        btn_row.addWidget(self._duplicate_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._clear_btn)
        bottom_lay.addLayout(btn_row)

        self._form_status = QLabel("")
        bottom_lay.addWidget(self._form_status)

        outer_lay.addWidget(bottom_strip)

        return panel

    def _build_filter_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFrameShape(QFrame.StyledPanel)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Name, system, faction, type…")
        lay.addWidget(self.search_input, stretch=1)

        lay.addWidget(_vline())

        lay.addWidget(QLabel("System:"))
        self.filter_system = QComboBox()
        self.filter_system.setMinimumWidth(150)
        lay.addWidget(self.filter_system)

        lay.addWidget(QLabel("Status:"))
        self.filter_status = QComboBox()
        self.filter_status.setMinimumWidth(110)
        lay.addWidget(self.filter_status)

        lay.addWidget(QLabel("Faction:"))
        self.filter_faction = QComboBox()
        self.filter_faction.setMinimumWidth(130)
        lay.addWidget(self.filter_faction)

        lay.addWidget(_vline())

        self._clear_filters_btn = QPushButton("Reset")
        lay.addWidget(self._clear_filters_btn)

        return bar

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(self.TABLE_COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)            # Name
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # System
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)   # Faction
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)   # Type
        hdr.setSectionResizeMode(4, QHeaderView.Fixed);  self.table.setColumnWidth(4, 120)  # Status
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)   # Scale
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)   # Qty
        hdr.setSectionResizeMode(7, QHeaderView.ResizeToContents)   # Paints
        hdr.setSectionsClickable(True)

        return self.table

    def _build_stat_chips(self) -> QFrame:
        """Compact stat strip at the bottom of the collection tab."""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        self._chip_total      = self._make_chip("Entries", "0")
        self._chip_models     = self._make_chip("Models",  "0")
        self._chip_complete   = self._make_chip("Complete","0", STATUS_COLORS["Complete"])
        self._chip_wip        = self._make_chip("WIP",     "0", STATUS_COLORS["WIP"])
        self._chip_unassembled= self._make_chip("Unbuilt", "0", STATUS_COLORS["Unassembled"])
        self._chip_systems    = self._make_chip("Systems", "0")

        for chip in [self._chip_total, self._chip_models, self._chip_complete,
                     self._chip_wip, self._chip_unassembled, self._chip_systems]:
            lay.addWidget(chip)
            lay.addWidget(_vline())

        lay.addStretch()
        return frame

    def _make_chip(self, label: str, value: str, accent: str = "#0078d4") -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"QWidget {{ background: transparent; }}")
        lay = QHBoxLayout(w); lay.setContentsMargins(6, 2, 6, 2); lay.setSpacing(5)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(f"font-weight: 700; font-size: 15px; color: {accent};")
        key_lbl = QLabel(label)
        key_lbl.setStyleSheet("font-size: 11px; color: #707070;")
        lay.addWidget(val_lbl)
        lay.addWidget(key_lbl)
        # Store references so we can update them
        w._val_lbl = val_lbl
        return w

    # ── Gallery tab ──────────────────────────────────────────────────────────

    def _build_gallery_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # Filter bar
        bar = QFrame(); bar.setFrameShape(QFrame.StyledPanel)
        flay = QHBoxLayout(bar); flay.setContentsMargins(12, 8, 12, 8); flay.setSpacing(8)
        flay.addWidget(QLabel("Search:"))
        self._gallery_search = QLineEdit()
        self._gallery_search.setPlaceholderText("Name, system, faction…")
        self._gallery_search.textChanged.connect(self._filter_gallery)
        flay.addWidget(self._gallery_search, stretch=1)
        flay.addWidget(_vline())
        flay.addWidget(QLabel("Status:"))
        self._gallery_status = QComboBox()
        self._gallery_status.setMinimumWidth(130)
        self._gallery_status.addItem("All Statuses")
        self._gallery_status.addItems(VALID_STATUSES)
        self._gallery_status.currentTextChanged.connect(self._filter_gallery)
        flay.addWidget(self._gallery_status)
        flay.addStretch()
        self._gallery_count_lbl = QLabel("")
        self._gallery_count_lbl.setStyleSheet("color: #606060; font-size: 12px;")
        flay.addWidget(self._gallery_count_lbl)
        lay.addWidget(bar)

        # Scroll grid
        self._gallery_scroll = QScrollArea()
        self._gallery_scroll.setWidgetResizable(True)
        self._gallery_content = QWidget()
        self._gallery_grid = QGridLayout(self._gallery_content)
        self._gallery_grid.setSpacing(12)
        self._gallery_grid.setContentsMargins(4, 4, 4, 4)
        self._gallery_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._gallery_scroll.setWidget(self._gallery_content)
        lay.addWidget(self._gallery_scroll, stretch=1)

        return tab

    # ── Statistics tab ───────────────────────────────────────────────────────

    def _build_stats_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget()
        self._stats_layout = QVBoxLayout(content)
        self._stats_layout.setSpacing(14)
        self._stats_layout.setContentsMargins(2, 2, 2, 2)

        placeholder = QLabel("No data yet — add some models to see statistics.")
        placeholder.setAlignment(Qt.AlignCenter)
        self._stats_layout.addWidget(placeholder)
        self._stats_layout.addStretch()

        scroll.setWidget(content)
        lay.addWidget(scroll)
        return tab

    # ── Signal connections ────────────────────────────────────────────────────

    def _connect_signals(self):
        # Toolbar
        self._new_model_btn.clicked.connect(self._start_add)
        self._edit_btn.clicked.connect(self._load_selected_into_form)
        self._delete_btn.clicked.connect(self._emit_delete)
        self._import_library_btn.clicked.connect(self._open_library_import)

        # Panel submit buttons
        self._add_btn.clicked.connect(self._emit_add)
        self._update_btn.clicked.connect(self._emit_update)
        self._duplicate_btn.clicked.connect(self._emit_duplicate)
        self._clear_btn.clicked.connect(self.clear_form)
        self._panel_close_btn.clicked.connect(self._close_detail_panel)

        # Filter bar
        self._clear_filters_btn.clicked.connect(self._clear_filters)

        # Image + paints
        self._choose_image_btn.clicked.connect(self._choose_image)
        self._clear_image_btn.clicked.connect(self._clear_image)
        self._view_paints_btn.clicked.connect(self._open_paint_view_dialog)
        self._manage_paints_btn.clicked.connect(self._open_paint_link_dialog)

        # Table
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table.selectionModel().selectionChanged.connect(self._on_row_selected)
        self.table.doubleClicked.connect(lambda _: self._load_selected_into_form())
        self.table.installEventFilter(self)

        # Filters
        self.search_input.textChanged.connect(self._emit_filter)
        self.filter_system.currentTextChanged.connect(self._emit_filter)
        self.filter_status.currentTextChanged.connect(self._emit_filter)
        self.filter_faction.currentTextChanged.connect(self._emit_filter)

    def eventFilter(self, obj, event):
        """Delete key on the model table triggers delete; Escape closes the detail panel."""
        if obj is self.table and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Delete:
                self._emit_delete()
                return True
            if event.key() == Qt.Key_Escape:
                self._close_detail_panel()
                return True
        return super().eventFilter(obj, event)

    # ── Panel show / hide ─────────────────────────────────────────────────────

    def _show_detail_panel(self):
        self._detail_sep.setVisible(True)
        self._detail_panel.setVisible(True)

    def _close_detail_panel(self):
        self._detail_sep.setVisible(False)
        self._detail_panel.setVisible(False)
        self.table.clearSelection()
        self._editing_id = None

    def _start_add(self):
        """Switch panel to Add mode and reveal it."""
        self.table.clearSelection()
        self.clear_form()
        self._show_detail_panel()

    # ── Events emitted to plugin ──────────────────────────────────────────────

    def _emit_add(self):
        data = self._read_form()
        if data: self.context.event_bus.emit("model_add_requested", data)

    def _emit_update(self):
        if self._editing_id is None: return
        data = self._read_form()
        if data:
            data["id"] = self._editing_id
            self.context.event_bus.emit("model_update_requested", data)

    def _emit_duplicate(self):
        if self._editing_id is None: return
        data = self._read_form()
        if data:
            data["name"] = data["name"] + " (Copy)"
            data.pop("id", None)
            self.context.event_bus.emit("model_add_requested", data)

    def _emit_delete(self):
        model_id = self._get_selected_id()
        if model_id is None:
            self._show_error("No model selected"); return
        if QMessageBox.question(
            self, "Delete Model",
            "Delete this model? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.context.event_bus.emit("model_remove_requested", {"id": model_id})

    def _emit_filter(self):
        f = ModelFilter(
            search_text=self.search_input.text().strip() or None,
            game_system=self._combo_value(self.filter_system),
            status=self._combo_value(self.filter_status),
            faction=self._combo_value(self.filter_faction),
            sort_by=self._current_filter.sort_by,
            sort_desc=self._current_filter.sort_desc,
        )
        self._current_filter = f
        self.context.event_bus.emit("models_filter_changed", {"filter": f})

    # ── Data display ──────────────────────────────────────────────────────────

    def display_models(self, models: list,
                       game_systems=None, factions=None, statuses=None):
        self._refresh_filter_dropdowns(game_systems, factions, statuses)
        self._populate_table(models)
        self._populate_gallery(models)

    def update_statistics(self, stats: ModelStatistics):
        self._update_stat_chips(stats)
        self._rebuild_stats_tab(stats)

    def _populate_table(self, models: list):
        self.table.setRowCount(0)
        for model in models:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 38)

            name_item = QTableWidgetItem(model.name)
            name_item.setData(Qt.UserRole, model.id)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(model.game_system))
            self.table.setItem(row, 2, QTableWidgetItem(model.faction))
            self.table.setItem(row, 3, QTableWidgetItem(model.model_type))

            # Status badge cell
            self.table.setCellWidget(row, 4, self._make_status_badge(model.status))

            self.table.setItem(row, 5, QTableWidgetItem(model.scale or ""))
            self.table.setItem(row, 6, QTableWidgetItem(str(model.quantity)))

            paint_count = len(model.linked_paint_ids)
            pi = QTableWidgetItem(str(paint_count) if paint_count else "—")
            pi.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 7, pi)

        self._result_label.setText(f"{len(models)} model{'s' if len(models) != 1 else ''}")

    def _make_status_badge(self, status: str) -> QWidget:
        """Coloured dot + status text in a container widget."""
        w = QWidget()
        lay = QHBoxLayout(w); lay.setContentsMargins(8, 0, 8, 0); lay.setSpacing(7)
        lay.addWidget(_status_dot(status, 10))
        lbl = QLabel(status)
        color = STATUS_COLORS.get(status, "#888888")
        lbl.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 12px;")
        lay.addWidget(lbl)
        lay.addStretch()
        return w

    def _refresh_filter_dropdowns(self, game_systems, factions, statuses):
        def _ref(combo, options, cur):
            with QSignalBlocker(combo):
                combo.clear(); combo.addItem("All")
                combo.addItems(options or [])
                idx = combo.findText(cur)
                combo.setCurrentIndex(idx if idx >= 0 else 0)

        _ref(self.filter_system,  game_systems or [], self._combo_value(self.filter_system) or "")
        _ref(self.filter_faction, factions or [],     self._combo_value(self.filter_faction) or "")
        _ref(self.filter_status,  statuses or VALID_STATUSES, self._combo_value(self.filter_status) or "")

    def _update_stat_chips(self, stats: ModelStatistics):
        self._chip_total._val_lbl.setText(str(stats.total_count))
        self._chip_models._val_lbl.setText(str(stats.total_models))
        self._chip_complete._val_lbl.setText(str(stats.status_distribution.get("Complete", 0)))
        self._chip_wip._val_lbl.setText(str(stats.status_distribution.get("WIP", 0)))
        self._chip_unassembled._val_lbl.setText(str(stats.status_distribution.get("Unassembled", 0)))
        self._chip_systems._val_lbl.setText(str(stats.unique_game_systems))

    def _rebuild_stats_tab(self, stats: ModelStatistics):
        while self._stats_layout.count():
            child = self._stats_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        if stats.total_count == 0:
            lbl = QLabel("No data yet — add some models to see statistics.")
            lbl.setAlignment(Qt.AlignCenter)
            self._stats_layout.addWidget(lbl)
            self._stats_layout.addStretch()
            return

        # Overview cards
        cards_row = QHBoxLayout(); cards_row.setSpacing(12)
        for title, value, color in [
            ("Total Entries",    str(stats.total_count),     "#0078d4"),
            ("Total Models",     str(stats.total_models),    "#0078d4"),
            ("Game Systems",     str(stats.unique_game_systems), "#0078d4"),
            ("Factions",         str(stats.unique_factions), "#0078d4"),
        ]:
            box = QGroupBox(title)
            bl = QVBoxLayout(box); bl.setAlignment(Qt.AlignCenter)
            vl = QLabel(value)
            vl.setStyleSheet(f"font-size: 36px; font-weight: 700; color: {color};")
            vl.setAlignment(Qt.AlignCenter)
            bl.addWidget(vl)
            cards_row.addWidget(box)

        cards_widget = QWidget()
        cards_widget.setLayout(cards_row)
        self._stats_layout.addWidget(cards_widget)

        # Progress bars for status breakdown
        if stats.status_distribution:
            status_box = QGroupBox("Status Breakdown")
            sb_lay = QVBoxLayout(status_box); sb_lay.setSpacing(8)
            total = sum(stats.status_distribution.values())
            for status in VALID_STATUSES:
                count = stats.status_distribution.get(status, 0)
                if count == 0: continue
                pct = int(count / total * 100) if total else 0
                color = STATUS_COLORS.get(status, "#888888")

                row_lay = QHBoxLayout(); row_lay.setSpacing(10)
                dot = _status_dot(status, 10)
                row_lay.addWidget(dot)
                name_lbl = QLabel(status)
                name_lbl.setFixedWidth(100)
                name_lbl.setStyleSheet(f"color: {color}; font-weight: 600;")
                row_lay.addWidget(name_lbl)

                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(pct)
                bar.setFixedHeight(12)
                bar.setTextVisible(False)
                bar.setStyleSheet(
                    f"QProgressBar {{ background: #2a2a2a; border-radius: 4px; border: none; }}"
                    f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
                )
                row_lay.addWidget(bar, stretch=1)

                cnt_lbl = QLabel(f"{count}  ({pct}%)")
                cnt_lbl.setFixedWidth(70)
                cnt_lbl.setStyleSheet("color: #909090; font-size: 11px;")
                row_lay.addWidget(cnt_lbl)
                sb_lay.addLayout(row_lay)

            self._stats_layout.addWidget(status_box)

        # Distribution side by side
        dist_row = QHBoxLayout(); dist_row.setSpacing(12)
        dist_row.addWidget(self._dist_table_group("By Game System",        stats.game_system_distribution))
        dist_row.addWidget(self._dist_table_group("By Faction / Collection", stats.faction_distribution))
        dist_widget = QWidget(); dist_widget.setLayout(dist_row)
        self._stats_layout.addWidget(dist_widget)
        self._stats_layout.addStretch()

    def _dist_table_group(self, title: str, data: dict) -> QGroupBox:
        box = QGroupBox(title)
        lay = QVBoxLayout(box)
        t = QTableWidget(len(data), 2)
        t.setHorizontalHeaderLabels(["Name", "Count"])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        t.setShowGrid(False)
        for i, (k, v) in enumerate(sorted(data.items(), key=lambda x: x[1], reverse=True)):
            t.setItem(i, 0, QTableWidgetItem(k))
            t.setItem(i, 1, QTableWidgetItem(str(v)))
        lay.addWidget(t)
        return box

    # ── Gallery ───────────────────────────────────────────────────────────────

    def _populate_gallery(self, models: list):
        self._gallery_models = list(models)
        self._filter_gallery()

    def _refresh_gallery(self):
        """Re-fetch fresh model data then repopulate (called after gallery dialog edits)."""
        svc = self.context.services.try_get("model_service")
        if svc:
            models = svc.search_models(self._current_filter)
            self._populate_gallery(models)
        else:
            self._filter_gallery()

    def _filter_gallery(self):
        search = self._gallery_search.text().lower()
        status_filter = self._gallery_status.currentText()

        while self._gallery_grid.count():
            item = self._gallery_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        visible = [
            m for m in self._gallery_models
            if (not search or search in f"{m.name} {m.game_system} {m.faction}".lower())
            and (status_filter in ("All", "All Statuses") or m.status == status_filter)
        ]

        if not visible:
            lbl = QLabel("No models match — adjust the filters above.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #606060; padding: 40px;")
            self._gallery_grid.addWidget(lbl, 0, 0, 1, self.GALLERY_COLS)
            self._gallery_count_lbl.setText("")
            return

        self._gallery_count_lbl.setText(f"{len(visible)} model{'s' if len(visible) != 1 else ''}")
        for i, model in enumerate(visible):
            self._gallery_grid.addWidget(
                self._make_gallery_card(model),
                i // self.GALLERY_COLS,
                i % self.GALLERY_COLS,
            )

    def _make_gallery_card(self, model) -> QFrame:
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setFixedWidth(self.GALLERY_CARD_W)
        card.setCursor(Qt.PointingHandCursor)
        card.setToolTip("Double-click to open photo gallery")

        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(5)

        # Thumbnail (full width, rounded top)
        thumb = QLabel()
        thumb.setFixedSize(self.GALLERY_CARD_W - 2, self.GALLERY_THUMB_H)
        thumb.setAlignment(Qt.AlignCenter)

        if model.image_path and os.path.isfile(model.image_path):
            pix = QPixmap(model.image_path).scaled(
                self.GALLERY_CARD_W - 2, self.GALLERY_THUMB_H,
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
            )
            thumb.setPixmap(pix)
            thumb.setStyleSheet(
                "background:#111; border-top-left-radius:6px; border-top-right-radius:6px;"
            )
        else:
            thumb.setText("📷  Double-click to add photos")
            thumb.setStyleSheet(
                "background:#1c1c1c; color:#404040; font-size:11px;"
                "border-top-left-radius:6px; border-top-right-radius:6px;"
            )
        lay.addWidget(thumb)

        # Status dot + text
        status_row = QHBoxLayout(); status_row.setContentsMargins(8, 0, 8, 0); status_row.setSpacing(5)
        status_row.addWidget(_status_dot(model.status, 8))
        color = STATUS_COLORS.get(model.status, "#888")
        s_lbl = QLabel(model.status)
        s_lbl.setStyleSheet(f"color:{color}; font-size:10px; font-weight:600;")
        status_row.addWidget(s_lbl)
        status_row.addStretch()
        lay.addLayout(status_row)

        # Name
        name_lbl = QLabel(model.name)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet("font-weight: 600; font-size: 12px; padding: 0 6px;")
        lay.addWidget(name_lbl)

        # Faction (muted)
        faction_lbl = QLabel(model.faction)
        faction_lbl.setAlignment(Qt.AlignCenter)
        faction_lbl.setWordWrap(True)
        faction_lbl.setStyleSheet("color:#606060; font-size:10px; padding: 0 6px;")
        lay.addWidget(faction_lbl)

        # Photo count badge (if gallery images exist)
        svc = self.context.services.try_get("model_service")
        if svc and model.id:
            imgs = svc.get_images_for_model(model.id)
            n = len(imgs)
            if n > 0:
                cnt_lbl = QLabel(f"🖼  {n} photo{'s' if n != 1 else ''}")
                cnt_lbl.setAlignment(Qt.AlignCenter)
                cnt_lbl.setStyleSheet("color:#0078d4; font-size:10px; padding: 0 6px;")
                lay.addWidget(cnt_lbl)

        # Double-click → open gallery dialog
        card.mouseDoubleClickEvent = lambda _e, m=model: self._open_model_gallery(m)

        return card

    def _open_model_gallery(self, model):
        """Open the per-model photo gallery dialog."""
        dlg = ModelImageGalleryDialog(self.context, model, self)
        dlg.exec()
        # Refresh gallery tiles so photo counts and primary thumbs update
        self._refresh_gallery()

    # ── Form helpers ──────────────────────────────────────────────────────────

    def _read_form(self) -> dict | None:
        name        = self.name_input.text().strip()
        game_system = self.game_system_input.currentText().strip()
        faction     = self.faction_input.currentText().strip()
        model_type  = self.type_input.currentText().strip()

        errors = []
        if not name:        errors.append("Name is required")
        if not game_system: errors.append("Game system is required")
        if not faction:     errors.append("Faction / Collection is required")
        if not model_type:  errors.append("Model type is required")

        if errors:
            self._show_error("  ·  ".join(errors)); return None

        return {
            "name":             name,
            "game_system":      game_system,
            "faction":          faction,
            "model_type":       model_type,
            "status":           self.status_combo.currentText(),
            "scale":            self.scale_input.text().strip(),
            "quantity":         self.qty_spin.value(),
            "notes":            self.notes_input.toPlainText().strip() or None,
            "linked_paint_ids": list(self._linked_paint_ids),
            "image_path":       self._image_path,
        }

    def populate_form(self, model):
        self._editing_id       = model.id
        self._linked_paint_ids = list(model.linked_paint_ids)
        self._image_path       = getattr(model, "image_path", None)

        self.name_input.setText(model.name)

        for combo, val in [
            (self.game_system_input, model.game_system),
            (self.faction_input,     model.faction),
            (self.type_input,        model.model_type),
        ]:
            idx = combo.findText(val)
            combo.setCurrentIndex(idx) if idx >= 0 else combo.setCurrentText(val)

        self.status_combo.setCurrentText(model.status)
        self.scale_input.setText(model.scale or "")
        self.qty_spin.setValue(model.quantity)
        self.notes_input.setPlainText(model.notes or "")

        self._update_linked_paints_label()
        self._update_image_preview()
        self._refresh_projects_section(model.id)

        self._add_btn.setVisible(False)
        self._update_btn.setVisible(True)
        self._duplicate_btn.setVisible(True)
        self._panel_title.setText(f"Editing — {model.name}")
        self._form_status.setText("")
        self._tabs.setCurrentIndex(0)
        self._show_detail_panel()

    def clear_form(self):
        self._editing_id       = None
        self._linked_paint_ids = []
        self._image_path       = None

        self.name_input.clear()
        self.game_system_input.setCurrentIndex(0)
        self.faction_input.setCurrentText("")
        self.type_input.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.scale_input.clear()
        self.qty_spin.setValue(1)
        self.notes_input.clear()

        self._update_linked_paints_label()
        self._update_image_preview()

        self._add_btn.setVisible(True)
        self._update_btn.setVisible(False)
        self._duplicate_btn.setVisible(False)
        self._panel_title.setText("Add Model")
        self._form_status.setText("")

    def _update_linked_paints_label(self):
        count = len(self._linked_paint_ids)
        if count == 0:
            self._linked_paints_label.setText("None")
            self._view_paints_btn.setEnabled(False)
        else:
            self._linked_paints_label.setText(f"{count} paint{'s' if count != 1 else ''} linked")
            self._view_paints_btn.setEnabled(True)

        # Rebuild mini swatch strip
        while self._swatches_row.count():
            item = self._swatches_row.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        paint_service = self.context.services.try_get("paint_service")
        shown = 0
        for pid in self._linked_paint_ids[:8]:
            color = "#888888"
            if paint_service:
                try:
                    p = paint_service.get_paint(pid)
                    color = getattr(p, "color", "#888888") or "#888888"
                except Exception:
                    pass
            dot = QLabel()
            dot.setFixedSize(14, 14)
            bright = QColor(color).lightness()
            border = "rgba(255,255,255,0.12)" if bright < 128 else "rgba(0,0,0,0.18)"
            dot.setStyleSheet(f"background:{color}; border:1px solid {border}; border-radius:3px;")
            dot.setToolTip(color)
            self._swatches_row.addWidget(dot)
            shown += 1

        if count > 8:
            more = QLabel(f"+{count - 8}")
            more.setStyleSheet("color:#707070; font-size:10px;")
            self._swatches_row.addWidget(more)

    def _update_image_preview(self):
        if self._image_path and os.path.isfile(self._image_path):
            pix = _cover_pixmap(QPixmap(self._image_path), 72, 54)
            self._image_label.setPixmap(pix)
            self._image_label.setText("")
        else:
            self._image_label.clear()
            self._image_label.setText("No photo")

    def _refresh_projects_section(self, model_id: int) -> None:
        """Populate the 'Used in Projects' RelatedItemsSection for the given model."""
        from plugins.shared_widgets import LinkedEntityChip
        proj_svc = self.context.services.try_get("project_service")
        if proj_svc is None:
            self._projects_section.set_empty("Project Tracker not available.")
            return
        try:
            projects = proj_svc.get_projects_for_entity("model", model_id)
        except Exception as e:
            print(f"[MODEL UI] _refresh_projects_section: {e}")
            self._projects_section.set_empty("Could not load projects.")
            return

        if not projects:
            self._projects_section.set_empty("Not linked to any project.")
            return

        chips = []
        for p in projects:
            chip = LinkedEntityChip(
                plugin_id="project_tracker",
                entity_id=getattr(p, "id", 0),
                icon=getattr(p, "icon", "📁"),
                name=getattr(p, "name", "Project"),
                subtitle=getattr(p, "game_system", ""),
                dot_color=getattr(p, "color", ""),
                show_navigate=True,
                show_unlink=False,
            )
            chip.navigate_requested.connect(
                lambda pid, _eid: self._emit_navigate(pid)
            )
            chips.append(chip)
        self._projects_section.set_chips(chips)

    def _emit_navigate(self, plugin_id: str) -> None:
        """Emit a dashboard_navigate event via the event bus."""
        bus = getattr(self.context, "event_bus", None)
        if bus:
            try:
                bus.emit("dashboard_navigate", {"plugin_id": plugin_id})
            except Exception:
                pass

    # ── Image actions ─────────────────────────────────────────────────────────

    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Model Photo", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if path:
            self._image_path = path
            self._update_image_preview()

    def _clear_image(self):
        self._image_path = None
        self._update_image_preview()

    # ── Table interaction ─────────────────────────────────────────────────────

    def _get_selected_id(self) -> int | None:
        if not self.table.selectedItems(): return None
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(Qt.UserRole) if item else None

    def _on_selection_changed(self):
        has = bool(self.table.selectedItems())
        self._edit_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)

    def _on_row_selected(self):
        model_id = self._get_selected_id()
        if model_id is None or self._editing_id == model_id: return
        self.context.event_bus.emit("model_edit_requested", {"id": model_id})

    def _load_selected_into_form(self):
        model_id = self._get_selected_id()
        if model_id: self.context.event_bus.emit("model_edit_requested", {"id": model_id})

    def _on_header_clicked(self, col: int):
        field = self.SORT_COL_MAP.get(col)
        if not field: return
        if self._current_filter.sort_by == field:
            self._current_filter.sort_desc = not self._current_filter.sort_desc
        else:
            self._current_filter.sort_by = field
            self._current_filter.sort_desc = False
        hdr = self.table.horizontalHeader()
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(col, Qt.DescendingOrder if self._current_filter.sort_desc else Qt.AscendingOrder)
        self.context.event_bus.emit("models_filter_changed", {"filter": self._current_filter})

    # ── Filter helpers ────────────────────────────────────────────────────────

    def _clear_filters(self):
        for w in (self.search_input,):
            with QSignalBlocker(w): w.clear()
        for w in (self.filter_system, self.filter_status, self.filter_faction):
            with QSignalBlocker(w): w.setCurrentIndex(0)
        self._current_filter = ModelFilter()
        self.context.event_bus.emit("models_filter_changed", {"filter": self._current_filter})

    @staticmethod
    def _combo_value(combo: QComboBox) -> str | None:
        val = combo.currentText()
        return val.strip() if val and val not in ("All", "All Statuses") else None

    # ── Paint dialogs ─────────────────────────────────────────────────────────

    def _open_paint_link_dialog(self):
        dlg = PaintLinkDialog(self.context, self._linked_paint_ids, parent=self)
        if dlg.exec():
            self._linked_paint_ids = dlg.get_selected_ids()
            self._update_linked_paints_label()

    def _open_paint_view_dialog(self):
        LinkedPaintsViewDialog(self.context, self._linked_paint_ids, parent=self).exec()

    # ── Library import ────────────────────────────────────────────────────────

    def _open_library_import(self):
        choice = QMessageBox(self)
        choice.setWindowTitle("Import Library")
        choice.setText("How would you like to load unit data?")
        file_btn   = choice.addButton("Select File(s)…", QMessageBox.ActionRole)
        folder_btn = choice.addButton("Select Folder…",  QMessageBox.ActionRole)
        choice.addButton(QMessageBox.Cancel)
        choice.exec()

        clicked = choice.clickedButton()
        paths: list[str] = []

        if clicked == file_btn:
            files, _ = QFileDialog.getOpenFileNames(
                self, "Open Unit Library File(s)", "",
                "JSON Files (*.json);;All Files (*)",
            )
            paths = files
        elif clicked == folder_btn:
            folder = QFileDialog.getExistingDirectory(
                self, "Select Folder with Unit JSON Files", "",
            )
            if folder:
                paths = [str(p) for p in Path(folder).glob("*.json")]
                if not paths:
                    self._show_error("No .json files found in the selected folder")
                    return

        if not paths:
            return
        dlg = LibraryImportDialog(self.context, paths, parent=self)
        dlg.exec()

    # ── Status messages ───────────────────────────────────────────────────────

    def _show_success(self, msg: str):
        from PySide6.QtCore import QTimer
        self._form_status.setObjectName("formStatusOk")
        self._form_status.style().unpolish(self._form_status)
        self._form_status.style().polish(self._form_status)
        self._form_status.setText(f"✓  {msg}")
        QTimer.singleShot(4000, lambda: self._form_status.setText(""))

    def _show_error(self, msg: str):
        from PySide6.QtCore import QTimer
        self._form_status.setObjectName("formStatusErr")
        self._form_status.style().unpolish(self._form_status)
        self._form_status.style().polish(self._form_status)
        self._form_status.setText(f"✗  {msg}")
        QTimer.singleShot(5000, lambda: self._form_status.setText(""))
