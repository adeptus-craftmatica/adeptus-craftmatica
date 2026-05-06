# ui/exporter.py
"""
Export / Report engine for Adeptus Craftmatica.

Provides lightweight, zero-dependency text and CSV exports for the
most common power-user reporting needs:

  • Paint inventory   → CSV or plain-text summary
  • Project report    → Markdown-style progress document
  • Army summary      → Unit roster with points

Usage:
    from ui.exporter import ExportDialog
    dlg = ExportDialog(context, parent=self)
    dlg.exec()
"""
from __future__ import annotations

import csv
import io
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QFileDialog, QFrame, QMessageBox,
    QWidget, QTabWidget,
)


# ─────────────────────────────────────────────────────────────────────────────
# Generators
# ─────────────────────────────────────────────────────────────────────────────

def generate_paint_inventory_csv(context) -> str:
    """Return paint inventory as a CSV string."""
    svc = context.services.try_get("paint_service")
    if not svc:
        return "# Paint service unavailable\n"

    paints = svc.get_all_paints()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Brand", "Name", "Type", "Quantity", "Level",
                     "Color", "Favorite", "Low Stock Notify", "Notes"])
    for p in sorted(paints, key=lambda x: (x.brand, x.name)):
        writer.writerow([
            p.brand,
            p.name,
            p.paint_type or "",
            p.quantity,
            p.level or "",
            p.color or "",
            "Yes" if p.is_favorite else "",
            "Yes" if getattr(p, "notify_low_stock", False) else "",
            (p.notes or "").replace("\n", " "),
        ])
    return out.getvalue()


def generate_paint_inventory_text(context) -> str:
    """Return a human-readable paint inventory report."""
    svc = context.services.try_get("paint_service")
    if not svc:
        return "Paint service unavailable.\n"

    paints = svc.get_all_paints()
    if not paints:
        return "No paints in inventory.\n"

    lines = [
        f"PAINT INVENTORY — {date.today().strftime('%d %B %Y')}",
        f"Total: {len(paints)} paints",
        "=" * 56,
        "",
    ]

    # Group by brand
    brands: dict[str, list] = {}
    for p in paints:
        brands.setdefault(p.brand, []).append(p)

    stats_by_level: dict[str, int] = {}
    low_stock = []

    for brand in sorted(brands):
        lines.append(f"▸ {brand}")
        for p in sorted(brands[brand], key=lambda x: x.name):
            level_tag = f"  [{p.level}]" if p.level else ""
            low_tag   = "  ⚠ LOW" if (p.level in ("Low", "Empty") or p.quantity == 0) else ""
            lines.append(f"    {p.name:<30} {p.paint_type or '':<12}{level_tag}{low_tag}")
            if p.level:
                stats_by_level[p.level] = stats_by_level.get(p.level, 0) + 1
            if p.level in ("Low", "Empty") or p.quantity == 0:
                low_stock.append(f"{p.brand} — {p.name}")
        lines.append("")

    lines += [
        "=" * 56,
        "SUMMARY BY STOCK LEVEL",
    ]
    for level, count in sorted(stats_by_level.items()):
        lines.append(f"  {level:<12} {count}")

    if low_stock:
        lines += ["", "LOW / EMPTY PAINTS"]
        for item in low_stock:
            lines.append(f"  • {item}")

    return "\n".join(lines)


def generate_project_report(context, project_id: int | None = None) -> str:
    """Return a Markdown-style project progress report."""
    svc = context.services.try_get("project_service")
    if not svc:
        return "Project service unavailable.\n"

    projects = svc.get_all_projects()
    if not projects:
        return "No projects found.\n"

    if project_id is not None:
        projects = [p for p in projects if p.id == project_id]
        if not projects:
            return f"Project {project_id} not found.\n"

    lines = [
        f"PROJECT PROGRESS REPORT — {date.today().strftime('%d %B %Y')}",
        f"Projects: {len(projects)}",
        "=" * 60,
        "",
    ]

    for proj in projects:
        try:
            stats     = svc.get_project_stats(proj.id)
            milestones = svc.get_milestones(proj.id)
        except Exception:
            stats, milestones = None, []

        status_icon = {
            "active": "🔄", "completed": "✅",
            "on_hold": "⏸", "archived": "📦",
        }.get(proj.status, "•")

        lines.append(f"{status_icon}  {proj.icon}  {proj.name}")
        lines.append(f"   System : {proj.game_system or 'Not specified'}")
        lines.append(f"   Status : {proj.status.replace('_', ' ').title()}")

        if proj.description:
            lines.append(f"   Desc   : {proj.description[:120]}")

        if stats:
            total_ms  = len(milestones)
            done_ms   = sum(1 for m in milestones if m.is_complete)
            pct       = int(done_ms / total_ms * 100) if total_ms else 0
            bar_filled = int(pct / 5)
            bar       = "█" * bar_filled + "░" * (20 - bar_filled)
            lines.append(f"   Progress : [{bar}] {pct}%")
            lines.append(f"   Milestones : {done_ms} / {total_ms} complete")
            if hasattr(stats, "total_models") and stats.total_models:
                lines.append(f"   Models : {stats.total_models} total")

        if milestones:
            lines.append("   Milestones:")
            for m in milestones:
                tick = "✓" if m.is_complete else "○"
                due  = f"  (due {m.due_date})" if m.due_date else ""
                lines.append(f"     {tick} {m.title}{due}")

        lines += ["", "-" * 60, ""]

    return "\n".join(lines)


def generate_army_summary(context) -> str:
    """Return a text summary of all armies."""
    svc = context.services.try_get("army_service")
    if not svc:
        return "Army service unavailable.\n"

    try:
        from plugins.army_builder.models import ArmyFilter
        armies = svc.search_armies(ArmyFilter())
    except Exception:
        armies = []

    if not armies:
        return "No armies found.\n"

    lines = [
        f"ARMY SUMMARY — {date.today().strftime('%d %B %Y')}",
        f"Armies: {len(armies)}",
        "=" * 56,
        "",
    ]

    for army in armies:
        lines.append(f"⚔  {army.name}")
        lines.append(f"   System : {army.game_system or 'Unknown'}")
        lines.append(f"   Faction: {army.faction or 'Unknown'}")

        try:
            rosters = svc.get_rosters(army.id)
            for r in rosters:
                units     = svc.get_roster_units(r.id) if hasattr(svc, "get_roster_units") else []
                pts_total = sum(getattr(u, "points_total", 0) for u in units)
                lines.append(f"   Roster : {r.name}  ({pts_total} pts, {len(units)} units)")
        except Exception:
            pass

        lines += [""]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Dialog
# ─────────────────────────────────────────────────────────────────────────────

class ExportDialog(QDialog):
    """
    One-stop export dialog. Lets the user pick a report type, preview the
    output, and save to file or copy to clipboard.
    """

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._ctx = context
        self.setWindowTitle("Export / Reports")
        self.setMinimumSize(680, 520)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Report selector ───────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(QLabel("Report:"))

        self._type_combo = QComboBox()
        self._type_combo.addItems([
            "Paint Inventory (text)",
            "Paint Inventory (CSV)",
            "Project Progress Report",
            "Army Summary",
        ])
        self._type_combo.currentIndexChanged.connect(self._generate)
        top.addWidget(self._type_combo, stretch=1)

        gen_btn = QPushButton("↻  Refresh")
        gen_btn.setObjectName("secondaryBtn")
        gen_btn.clicked.connect(self._generate)
        top.addWidget(gen_btn)
        root.addLayout(top)

        # ── Preview ───────────────────────────────────────────────────────────
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setObjectName("noteBodyEdit")
        self._preview.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;"
        )
        root.addWidget(self._preview, stretch=1)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        copy_btn = QPushButton("📋  Copy to Clipboard")
        copy_btn.setObjectName("secondaryBtn")
        copy_btn.clicked.connect(self._copy)
        btn_row.addWidget(copy_btn)

        save_btn = QPushButton("💾  Save to File…")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryBtn")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self._generate()

    # ── Generator dispatch ────────────────────────────────────────────────────

    def _generate(self) -> None:
        idx = self._type_combo.currentIndex()
        try:
            if idx == 0:
                text = generate_paint_inventory_text(self._ctx)
            elif idx == 1:
                text = generate_paint_inventory_csv(self._ctx)
            elif idx == 2:
                text = generate_project_report(self._ctx)
            elif idx == 3:
                text = generate_army_summary(self._ctx)
            else:
                text = ""
        except Exception as e:
            text = f"Error generating report:\n{e}"
        self._preview.setPlainText(text)

    def _copy(self) -> None:
        clip = QApplication.clipboard()
        if clip:
            clip.setText(self._preview.toPlainText())
        from ui.toast import ToastManager
        ToastManager.instance().show("Copied to clipboard", level="success", duration=2000)

    def _save(self) -> None:
        idx      = self._type_combo.currentIndex()
        is_csv   = idx == 1
        ext_filt = "CSV Files (*.csv)" if is_csv else "Text Files (*.txt);;Markdown (*.md)"
        default  = "paint_inventory.csv" if is_csv else "adeptus_report.txt"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", default, ext_filt
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="" if is_csv else "\n") as f:
                f.write(self._preview.toPlainText())
            from ui.toast import ToastManager
            ToastManager.instance().show(f"Saved to {path}", level="success", duration=3000)
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
