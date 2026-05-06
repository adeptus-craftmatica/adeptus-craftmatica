"""Paint intelligence widget — low stock, recent paints, brand breakdown."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tok(ctx):
    tm = ctx.services.get("theme_manager") if ctx else None
    return {
        "bg":     tm.token("card_bg")   if tm else "#1a1a1a",
        "border": tm.token("border")    if tm else "#2a2a2a",
        "hi":     tm.token("text_hi")   if tm else "#e8e8e8",
        "mid":    tm.token("text_mid")  if tm else "#b0b0b0",
        "lo":     tm.token("text_lo")   if tm else "#808080",
        "accent": tm.token("accent")    if tm else "#0078d4",
        "raised": tm.token("bg_raised") if tm else "#1e1e1e",
    }


# ── Reusable section panel ────────────────────────────────────────────────────

class _Panel(QWidget):
    """Flat section with a small caps header and a subtle separator."""

    def __init__(self, title: str, ctx, parent=None):
        super().__init__(parent)
        self._ctx = ctx

        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(6)

        # Header row
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_row.setSpacing(8)
        self._hdr_lbl = QLabel(title)
        self._hdr_lbl.setObjectName("panelHeader")
        hdr_row.addWidget(self._hdr_lbl)
        hdr_row.addStretch()
        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("panelCount")
        hdr_row.addWidget(self._count_lbl)
        vlay.addLayout(hdr_row)

        # Separator
        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.HLine)
        self._sep.setFixedHeight(1)
        vlay.addWidget(self._sep)

        # Body area
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(2)
        vlay.addLayout(self._body)

        self.apply_theme()

    def apply_theme(self):
        t = _tok(self._ctx)
        self._hdr_lbl.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {t['lo']}; "
            "letter-spacing: 1px; background: transparent;"
        )
        self._count_lbl.setStyleSheet(
            f"font-size: 9px; color: {t['lo']}; background: transparent;"
        )
        self._sep.setStyleSheet(f"background: {t['border']}; border: none;")

    def set_count(self, text: str):
        self._count_lbl.setText(text)

    def clear(self):
        while self._body.count():
            item = self._body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add(self, widget: QWidget):
        self._body.addWidget(widget)

    def add_empty(self, text: str):
        t = _tok(self._ctx)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 11px; color: {t['lo']}; background: transparent; padding: 4px 0;"
        )
        self._body.addWidget(lbl)


# ── Row builders ──────────────────────────────────────────────────────────────

def _stock_row(name: str, brand: str, swatch: str, status: str, ctx) -> QFrame:
    """Two-line row with coloured left stripe for stock status."""
    t   = _tok(ctx)
    clr = "#c62828" if status == "Empty" else "#e07820"  # red : amber

    frame = QFrame()
    frame.setStyleSheet(f"background: {t['bg']};")
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

    outer = QHBoxLayout(frame)
    outer.setContentsMargins(0, 2, 0, 2)
    outer.setSpacing(8)

    # Coloured left stripe
    stripe = QFrame()
    stripe.setFixedWidth(3)
    stripe.setFixedHeight(32)
    stripe.setStyleSheet(f"background: {clr}; border-radius: 1px;")
    outer.addWidget(stripe)

    # Colour swatch
    sw = QFrame()
    sw.setFixedSize(12, 12)
    sw.setStyleSheet(
        f"background: {swatch or '#555'}; border-radius: 2px; "
        "border: 1px solid rgba(255,255,255,0.12);"
    )
    outer.addWidget(sw)

    # Text block (two lines)
    txt = QVBoxLayout()
    txt.setSpacing(0)
    txt.setContentsMargins(0, 0, 0, 0)

    name_lbl = QLabel(name)
    name_lbl.setStyleSheet(
        f"font-size: 11px; font-weight: 600; color: {t['hi']}; background: transparent;"
    )
    name_lbl.setTextFormat(Qt.PlainText)
    name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    name_lbl.setMaximumWidth(160)
    txt.addWidget(name_lbl)

    if brand:
        brand_lbl = QLabel(brand)
        brand_lbl.setStyleSheet(
            f"font-size: 9px; color: {t['lo']}; background: transparent;"
        )
        brand_lbl.setTextFormat(Qt.PlainText)
        txt.addWidget(brand_lbl)

    outer.addLayout(txt, stretch=1)

    # Status badge (right-aligned, compact)
    badge = QLabel("EMPTY" if status == "Empty" else "LOW")
    badge.setFixedHeight(14)
    badge.setStyleSheet(f"""
        font-size: 8px; font-weight: 700;
        color: {clr};
        background: {clr}1a;
        border: 1px solid {clr}44;
        border-radius: 2px;
        padding: 0 4px;
        letter-spacing: 0.5px;
    """)
    outer.addWidget(badge)

    return frame


def _recent_row(name: str, brand: str, paint_type: str, swatch: str, ctx) -> QWidget:
    """Two-line row for recent paints: swatch + name + type/brand."""
    t = _tok(ctx)

    w = QWidget()
    w.setStyleSheet(f"background: {t['bg']};")
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

    row = QHBoxLayout(w)
    row.setContentsMargins(0, 2, 0, 2)
    row.setSpacing(8)

    sw = QFrame()
    sw.setFixedSize(14, 14)
    sw.setStyleSheet(
        f"background: {swatch or '#555'}; border-radius: 3px; "
        "border: 1px solid rgba(255,255,255,0.12);"
    )
    row.addWidget(sw)

    txt = QVBoxLayout()
    txt.setSpacing(0)
    txt.setContentsMargins(0, 0, 0, 0)

    name_lbl = QLabel(name)
    name_lbl.setStyleSheet(
        f"font-size: 11px; font-weight: 600; color: {t['hi']}; background: transparent;"
    )
    name_lbl.setTextFormat(Qt.PlainText)
    txt.addWidget(name_lbl)

    sub_parts = [p for p in (brand, paint_type) if p]
    if sub_parts:
        sub_lbl = QLabel("  ·  ".join(sub_parts))
        sub_lbl.setStyleSheet(
            f"font-size: 9px; color: {t['lo']}; background: transparent;"
        )
        sub_lbl.setTextFormat(Qt.PlainText)
        txt.addWidget(sub_lbl)

    row.addLayout(txt, stretch=1)
    return w


def _bar_row(brand: str, count: int, pct: float, bar_color: str, ctx) -> QWidget:
    """Single brand bar row."""
    t = _tok(ctx)

    w = QWidget()
    w.setStyleSheet(f"background: {t['bg']};")

    row = QHBoxLayout(w)
    row.setContentsMargins(0, 3, 0, 3)
    row.setSpacing(8)

    name_lbl = QLabel(brand)
    name_lbl.setStyleSheet(
        f"font-size: 10px; color: {t['hi']}; background: transparent;"
    )
    name_lbl.setTextFormat(Qt.PlainText)
    name_lbl.setFixedWidth(80)
    name_lbl.setMaximumWidth(80)
    row.addWidget(name_lbl)

    # Bar track
    track = QFrame()
    track.setFixedHeight(4)
    track.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    track.setStyleSheet(f"background: {t['border']}; border-radius: 2px;")

    fill = QFrame(track)
    fill.setFixedHeight(4)
    fill.setStyleSheet(f"background: {bar_color}; border-radius: 2px;")
    fill._pct = pct
    # Resize fill proportionally when track resizes
    def _resize(e, f=fill, tr=track):
        f.setFixedWidth(max(2, int(tr.width() * f._pct)))
        QFrame.resizeEvent(tr, e)
    track.resizeEvent = _resize
    row.addWidget(track, stretch=1)

    cnt_lbl = QLabel(str(count))
    cnt_lbl.setStyleSheet(
        f"font-size: 10px; color: {t['lo']}; background: transparent;"
    )
    cnt_lbl.setFixedWidth(24)
    cnt_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    row.addWidget(cnt_lbl)

    return w


# ── Main widget ───────────────────────────────────────────────────────────────

class PaintIntelWidget(QWidget):
    """Three-section paint health snapshot."""

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self._low_panel    = _Panel("LOW / EMPTY STOCK", context)
        self._recent_panel = _Panel("RECENTLY ADDED", context)
        self._brand_panel  = _Panel("BRAND MIX", context)

        lay.addWidget(self._low_panel)
        lay.addWidget(self._recent_panel)
        lay.addWidget(self._brand_panel)
        lay.addStretch()

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self, low_stock: list, recent: list, brands: dict) -> None:
        self._rebuild_low(low_stock)
        self._rebuild_recent(recent)
        self._rebuild_brands(brands)

    def apply_theme(self):
        for panel in (self._low_panel, self._recent_panel, self._brand_panel):
            panel.apply_theme()

    # ── private ───────────────────────────────────────────────────────────────

    def _rebuild_low(self, paints: list) -> None:
        self._low_panel.clear()
        if not paints:
            self._low_panel.set_count("")
            t = _tok(self._ctx)
            self._low_panel.add_empty("✓  All paints well stocked")
            return

        self._low_panel.set_count(str(len(paints)))
        for p in paints:
            qty    = getattr(p, "quantity", 1)
            status = "Empty" if qty == 0 else "Low"
            swatch = getattr(p, "color", "") or "#555"
            brand  = getattr(p, "brand", "") or ""
            name   = getattr(p, "name", "Unknown")
            self._low_panel.add(_stock_row(name, brand, swatch, status, self._ctx))

    def _rebuild_recent(self, paints: list) -> None:
        self._recent_panel.clear()
        if not paints:
            self._recent_panel.set_count("")
            self._recent_panel.add_empty("No paints added yet")
            return

        self._recent_panel.set_count(str(len(paints)))
        for p in paints:
            swatch     = getattr(p, "color", "") or "#555"
            brand      = getattr(p, "brand", "") or ""
            name       = getattr(p, "name", "Unknown")
            paint_type = getattr(p, "paint_type", "") or ""
            self._recent_panel.add(_recent_row(name, brand, paint_type, swatch, self._ctx))

    def _rebuild_brands(self, brands: dict) -> None:
        self._brand_panel.clear()
        if not brands:
            self._brand_panel.set_count("")
            self._brand_panel.add_empty("No brand data")
            return

        t = _tok(self._ctx)
        total   = sum(brands.values()) or 1
        sorted_ = sorted(brands.items(), key=lambda x: x[1], reverse=True)[:6]
        self._brand_panel.set_count(f"{len(brands)} brand{'s' if len(brands) != 1 else ''}")

        for brand, count in sorted_:
            pct = count / total
            self._brand_panel.add(_bar_row(brand, count, pct, t["accent"], self._ctx))
