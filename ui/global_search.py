"""
Global Search

A floating search panel accessible from the main window toolbar.
Queries all loaded plugin services and shows categorised results.
Clicking a result navigates to the relevant plugin tab + item.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QScrollArea, QGraphicsDropShadowEffect,
)


# ── Category colours ──────────────────────────────────────────────────────────

_CAT_COLOR = {
    "Projects":   "#0078d4",
    "Models":     "#3b9eff",
    "Paints":     "#ff6b35",
    "Schemes":    "#a855f7",
    "Armies":     "#22c55e",
    "Campaigns":  "#f59e0b",
    "Characters": "#ec4899",
    "Battles":    "#60a5fa",
}


# ── Result row ────────────────────────────────────────────────────────────────

class _ResultRow(QFrame):
    clicked = Signal()

    def __init__(self, category: str, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(44)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        # Coloured category label
        color = _CAT_COLOR.get(category, "#666")
        cat_lbl = QLabel(category)
        cat_lbl.setFixedWidth(74)
        cat_lbl.setAlignment(Qt.AlignCenter)
        cat_lbl.setStyleSheet(
            f"color: {color}; background: {color}18;"
            f" border: 1px solid {color}35;"
            f" border-radius: 4px; padding: 2px 0;"
            f" font-size: 10px; font-weight: 700;"
        )
        lay.addWidget(cat_lbl)

        # Text block
        text = QVBoxLayout()
        text.setSpacing(1)
        text.setContentsMargins(0, 0, 0, 0)

        t = QLabel(title)
        t.setStyleSheet("color: #e0e0e0; font-size: 13px; font-weight: 600; background: transparent;")
        t.setWordWrap(False)
        text.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet("color: #555; font-size: 11px; background: transparent;")
            s.setWordWrap(False)
            text.addWidget(s)

        lay.addLayout(text, stretch=1)

        self._base = "QFrame { background: transparent; border-radius: 5px; }"
        self._hover = "QFrame { background: #222; border-radius: 5px; }"
        self.setStyleSheet(self._base)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()

    def enterEvent(self, ev):
        self.setStyleSheet(self._hover)

    def leaveEvent(self, ev):
        self.setStyleSheet(self._base)


# ── Section header ────────────────────────────────────────────────────────────

class _SectionHeader(QFrame):
    def __init__(self, label: str, count: int, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(26)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)

        color = _CAT_COLOR.get(label, "#666")
        lbl = QLabel(label.upper())
        lbl.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: 700;"
            " letter-spacing: 1px; background: transparent;"
        )
        cnt = QLabel(str(count))
        cnt.setStyleSheet("color: #3a3a3a; font-size: 10px; background: transparent;")

        lay.addWidget(lbl)
        lay.addStretch()
        lay.addWidget(cnt)


# ── Main panel ────────────────────────────────────────────────────────────────

class GlobalSearchPanel(QFrame):
    result_activated = Signal(str, object)

    MAX_PER_CATEGORY = 6

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._run_search)

        self.setObjectName("GSPanel")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(560)
        self.setStyleSheet("""
            QFrame#GSPanel {
                background: #191919;
                border: 1px solid #2e2e2e;
                border-radius: 8px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.setGraphicsEffect(shadow)

        self._build_ui()
        self.hide()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(0)

        # Input row
        input_row = QFrame()
        input_row.setObjectName("GSInputRow")
        input_row.setFrameShape(QFrame.NoFrame)
        input_row.setFixedHeight(50)
        input_row.setStyleSheet("QFrame#GSInputRow { background: transparent; }")

        ir = QHBoxLayout(input_row)
        ir.setContentsMargins(14, 0, 14, 0)
        ir.setSpacing(10)

        icon = QLabel()
        icon.setText("⌕")
        icon.setStyleSheet("font-size: 18px; color: #484848; background: transparent;")
        icon.setFixedWidth(20)
        ir.addWidget(icon)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Search models, paints, schemes, armies…")
        self._input.setFrame(False)
        self._input.setStyleSheet(
            "QLineEdit { background: transparent; border: none;"
            " color: #ebebeb; font-size: 14px; }"
            "QLineEdit::placeholder { color: #3e3e3e; }"
        )
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._run_search)
        ir.addWidget(self._input, stretch=1)

        esc = QLabel("esc")
        esc.setStyleSheet(
            "color: #3a3a3a; font-size: 10px;"
            " background: #1e1e1e; border: 1px solid #2e2e2e;"
            " border-radius: 4px; padding: 2px 6px;"
        )
        ir.addWidget(esc)

        root.addWidget(input_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet("background: #252525; border: none;")
        root.addWidget(div)

        # Results area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 4px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 2px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._results_widget = QWidget()
        self._results_widget.setStyleSheet("background: transparent;")
        self._results_layout = QVBoxLayout(self._results_widget)
        self._results_layout.setContentsMargins(6, 6, 6, 4)
        self._results_layout.setSpacing(0)

        self._scroll.setWidget(self._results_widget)
        root.addWidget(self._scroll, stretch=1)

        self._show_placeholder()

    # ── Public ────────────────────────────────────────────────────────────────

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self._input.setFocus()
            self._input.selectAll()

    def close_panel(self):
        self.hide()
        self._input.clear()
        self._clear_results()
        self._show_placeholder()

    # ── Search ────────────────────────────────────────────────────────────────

    def _on_text_changed(self, text: str):
        if not text.strip():
            self._clear_results()
            self._show_placeholder()
            return
        self._debounce.start()

    def _run_search(self):
        query = self._input.text().strip()
        if not query:
            return
        self._clear_results()
        needle = query.lower()
        results: list[tuple[str, list]] = []

        # Projects
        project_svc = self._ctx.services.try_get("project_service")
        if project_svc:
            try:
                hits = [
                    p for p in project_svc.get_all_projects()
                    if needle in p.name.lower()
                    or needle in (p.description or "").lower()
                    or needle in (p.game_system or "").lower()
                ][:self.MAX_PER_CATEGORY]
                if hits:
                    results.append(("Projects", [
                        (f"{p.icon}  {p.name}",
                         f"{p.game_system or 'No system'}  ·  {p.status}",
                         {"id": p.id, "name": p.name})
                        for p in hits
                    ]))
            except Exception:
                pass

        # Paints
        paint_svc = self._ctx.services.try_get("paint_service")
        if paint_svc:
            try:
                hits = [
                    p for p in paint_svc.get_all_paints()
                    if needle in p.name.lower()
                    or needle in p.brand.lower()
                    or needle in (p.paint_type or "").lower()
                ][:self.MAX_PER_CATEGORY]
                if hits:
                    results.append(("Paints", [
                        (p.name, f"{p.brand}  ·  {p.paint_type}", {"id": p.id, "name": p.name})
                        for p in hits
                    ]))
            except Exception:
                pass

        # Models
        model_svc = self._ctx.services.try_get("model_service")
        if model_svc:
            try:
                from plugins.model_tracker.models import ModelFilter
                hits = model_svc.search_models(ModelFilter(search_text=query))[:self.MAX_PER_CATEGORY]
                if hits:
                    results.append(("Models", [
                        (m.name, f"{m.faction}  ·  {m.game_system}  ·  {m.status}",
                         {"id": m.id, "name": m.name})
                        for m in hits
                    ]))
            except Exception:
                pass

        # Schemes
        scheme_svc = self._ctx.services.try_get("scheme_service")
        if scheme_svc:
            try:
                from plugins.paint_scheme.models import SchemeFilter
                hits = scheme_svc.search_schemes(SchemeFilter(search_text=query))[:self.MAX_PER_CATEGORY]
                if hits:
                    results.append(("Schemes", [
                        (s.name, "  ·  ".join(x for x in [s.faction, s.game_system] if x),
                         {"id": s.id, "name": s.name})
                        for s in hits
                    ]))
            except Exception:
                pass

        # Armies
        army_svc = self._ctx.services.try_get("army_service")
        if army_svc:
            try:
                from plugins.army_builder.models import ArmyFilter
                hits = army_svc.search_armies(ArmyFilter(search_text=query))[:self.MAX_PER_CATEGORY]
                if hits:
                    results.append(("Armies", [
                        (a.name, f"{a.faction}  ·  {a.game_system}", {"id": a.id, "name": a.name})
                        for a in hits
                    ]))
            except Exception:
                pass

        # Campaigns / Characters / Battles
        camp_svc = self._ctx.services.try_get("campaign_service")
        if camp_svc:
            try:
                all_camps = camp_svc.get_all_campaigns()
                hits = [
                    c for c in all_camps
                    if needle in c.name.lower()
                    or needle in (c.game_system or "").lower()
                    or needle in (c.description or "").lower()
                ][:self.MAX_PER_CATEGORY]
                if hits:
                    results.append(("Campaigns", [
                        (c.name, f"{c.game_system}  ·  {c.status}", {"id": c.id, "name": c.name})
                        for c in hits
                    ]))
            except Exception:
                pass

            try:
                all_chars = []
                for c in camp_svc.get_all_campaigns():
                    all_chars.extend(camp_svc.get_characters(c.id))
                hits = [
                    ch for ch in all_chars
                    if needle in ch.name.lower()
                    or needle in (ch.character_role or "").lower()
                    or needle in (ch.character_class or "").lower()
                    or needle in (ch.race or "").lower()
                ][:self.MAX_PER_CATEGORY]
                if hits:
                    results.append(("Characters", [
                        (ch.name,
                         "  ·  ".join(x for x in [ch.character_role, ch.character_class, ch.race] if x),
                         {"id": ch.id, "name": ch.name, "campaign_id": ch.campaign_id})
                        for ch in hits
                    ]))
            except Exception:
                pass

            try:
                all_battles = []
                for c in camp_svc.get_all_campaigns():
                    all_battles.extend(camp_svc.get_battles(c.id))
                hits = [
                    b for b in all_battles
                    if needle in b.title.lower()
                    or needle in (b.location_name or "").lower()
                    or needle in (b.scenario_name or "").lower()
                ][:self.MAX_PER_CATEGORY]
                if hits:
                    results.append(("Battles", [
                        (b.title,
                         "  ·  ".join(x for x in [b.location_name, b.outcome, b.date_played] if x),
                         {"id": b.id, "name": b.title, "campaign_id": b.campaign_id})
                        for b in hits
                    ]))
            except Exception:
                pass

        # Render
        if not results:
            self._show_placeholder(f'No results for "{query}"')
            return

        total = 0
        for i, (category, rows) in enumerate(results):
            if i > 0:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setFixedHeight(1)
                sep.setStyleSheet("background: #232323; border: none; margin: 2px 0;")
                self._results_layout.addWidget(sep)

            self._results_layout.addWidget(_SectionHeader(category, len(rows)))
            for title, subtitle, payload in rows:
                row = _ResultRow(category, title, subtitle)
                row.clicked.connect(
                    lambda cat=category, pay=payload: self._activate(cat, pay)
                )
                self._results_layout.addWidget(row)
                total += 1

        self._results_layout.addStretch()

        # Size panel to content
        n_sec = len(results)
        h = 50 + 1 + (n_sec * 26) + (total * 46) + 20
        self.setFixedHeight(min(540, max(100, h)))

    def _activate(self, category: str, payload: dict):
        self.result_activated.emit(category, payload)
        self.close_panel()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_results(self):
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_placeholder(self, msg: str = "Start typing to search everything…"):
        self._clear_results()
        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #3e3e3e; font-size: 13px; padding: 24px; background: transparent;")
        self._results_layout.addWidget(lbl)
        self._results_layout.addStretch()
        self.setFixedHeight(110)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.close_panel()
        else:
            super().keyPressEvent(ev)
