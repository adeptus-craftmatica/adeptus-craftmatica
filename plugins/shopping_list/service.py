"""Shopping List — service layer."""
from __future__ import annotations
import csv
import io
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

from .models import ShoppingItem, ShoppingSection, ShoppingList, CATEGORIES
from .repository import ShoppingRepository


class ShoppingService:
    def __init__(self, repo: ShoppingRepository):
        self._repo = repo

    # ── Lists ─────────────────────────────────────────────────────────────────

    def create_list(self, name: str) -> ShoppingList:
        name = name.strip()
        if not name:
            raise ValueError("List name cannot be empty")
        list_id = self._repo.create_list(name)
        # Auto-create a General section
        self._repo.create_section(list_id, "General", sort_order=0)
        sl = self._repo.get_list(list_id)
        return sl

    def get_all_lists(self) -> list[ShoppingList]:
        return self._repo.get_all_lists()

    def rename_list(self, list_id: int, name: str):
        name = name.strip()
        if not name:
            raise ValueError("List name cannot be empty")
        self._repo.rename_list(list_id, name)

    def delete_list(self, list_id: int):
        self._repo.delete_list(list_id)

    def get_or_create_default_list(self) -> ShoppingList:
        lists = self._repo.get_all_lists()
        if lists:
            return lists[0]
        return self.create_list("My Shopping List")

    # ── Sections ──────────────────────────────────────────────────────────────

    def get_sections(self, list_id: int) -> list[ShoppingSection]:
        sections = self._repo.get_sections(list_id)
        for sec in sections:
            sec.items = self._repo.get_items(list_id, sec.id)
        return sections

    def create_section(self, list_id: int, title: str,
                       source_type: str = "custom",
                       source_project_id: str = "") -> ShoppingSection:
        title = title.strip()
        if not title:
            raise ValueError("Section title cannot be empty")
        existing = self._repo.get_sections(list_id)
        sort_order = max((s.sort_order for s in existing), default=-1) + 1
        sec_id = self._repo.create_section(
            list_id, title, source_type, source_project_id, sort_order
        )
        return ShoppingSection(title=title, list_id=list_id,
                               source_type=source_type,
                               source_project_id=source_project_id,
                               sort_order=sort_order, id=sec_id)

    def rename_section(self, section_id: int, title: str):
        title = title.strip()
        if not title:
            raise ValueError("Section title cannot be empty")
        self._repo.rename_section(section_id, title)

    def delete_section(self, section_id: int):
        self._repo.delete_section(section_id)

    def set_section_collapsed(self, section_id: int, collapsed: bool):
        self._repo.set_section_collapsed(section_id, collapsed)

    def ensure_section(self, list_id: int, title: str,
                       source_type: str = "custom",
                       source_project_id: str = "") -> int:
        """Return existing section id by title, or create it."""
        sections = self._repo.get_sections(list_id)
        for s in sections:
            if s.title.lower() == title.lower():
                return s.id
        sec = self.create_section(list_id, title, source_type, source_project_id)
        return sec.id

    # ── Items ─────────────────────────────────────────────────────────────────

    def add_item(self, item: ShoppingItem,
                 merge_duplicates: bool = True) -> tuple[ShoppingItem, bool]:
        """Add an item. Returns (item, was_merged)."""
        item.name = item.name.strip()
        if not item.name:
            raise ValueError("Item name is required")
        if item.quantity <= 0:
            raise ValueError("Quantity must be greater than 0")
        if not item.category:
            item.category = "Other"

        if merge_duplicates:
            dup = self._repo.find_duplicate(item.list_id, item.name, item.section_id)
            if dup:
                self._repo.merge_quantity(dup.id, item.quantity)
                dup.quantity += item.quantity
                return dup, True

        item_id = self._repo.add_item(item)
        item.id = item_id
        return item, False

    def update_item(self, item: ShoppingItem):
        item.name = item.name.strip()
        if not item.name:
            raise ValueError("Item name is required")
        self._repo.update_item(item)

    def set_purchased(self, item_id: int, purchased: bool):
        self._repo.set_purchased(item_id, purchased)

    def delete_item(self, item_id: int):
        self._repo.delete_item(item_id)

    def delete_purchased(self, list_id: int):
        self._repo.delete_purchased(list_id)

    def clear_list(self, list_id: int):
        self._repo.clear_list(list_id)

    def get_all_items(self, list_id: int) -> list[ShoppingItem]:
        return self._repo.get_items(list_id)

    def search_items(self, list_id: int, query: str,
                     category: str = "") -> list[ShoppingItem]:
        items = self._repo.get_items(list_id)
        q = query.lower().strip()
        if q:
            items = [i for i in items if q in i.name.lower() or q in i.notes.lower()]
        if category and category != "All":
            items = [i for i in items if i.category == category]
        return items

    def get_stats(self, list_id: int) -> dict:
        items = self._repo.get_items(list_id)
        total = len(items)
        purchased = sum(1 for i in items if i.purchased)
        return {"total": total, "purchased": purchased, "remaining": total - purchased}

    # ── Export ────────────────────────────────────────────────────────────────

    def export_txt(self, list_id: int) -> str:
        sl = self._repo.get_list(list_id)
        sections = self.get_sections(list_id)
        lines = [f"=== {sl.name} ===", ""]
        for sec in sections:
            if not sec.items:
                continue
            lines.append(f"## {sec.title}")
            for item in sec.items:
                status = "✓" if item.purchased else "☐"
                qty = item.qty_display()
                line = f"  {status} {item.name}  {qty}"
                if item.notes:
                    line += f"  — {item.notes}"
                lines.append(line)
            lines.append("")
        return "\n".join(lines)

    def export_csv(self, list_id: int) -> str:
        sections = self.get_sections(list_id)
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["Section", "Name", "Category", "Quantity", "Unit",
                    "Purchased", "Notes", "Source"])
        for sec in sections:
            for item in sec.items:
                w.writerow([sec.title, item.name, item.category,
                            item.quantity, item.unit,
                            "Yes" if item.purchased else "No",
                            item.notes, item.source_plugin])
        return out.getvalue()

    def export_json(self, list_id: int) -> str:
        sl = self._repo.get_list(list_id)
        sections = self.get_sections(list_id)
        data = {
            "list": {"id": sl.id, "name": sl.name},
            "sections": [
                {
                    "title": sec.title,
                    "source_type": sec.source_type,
                    "items": [
                        {
                            "name": i.name, "category": i.category,
                            "quantity": i.quantity, "unit": i.unit,
                            "purchased": i.purchased, "notes": i.notes,
                            "source_plugin": i.source_plugin,
                        }
                        for i in sec.items
                    ]
                }
                for sec in sections
            ]
        }
        return json.dumps(data, indent=2)

    # ── Public integration API ─────────────────────────────────────────────────

    def add_item_from_plugin(self, list_id: int, name: str, category: str = "Other",
                             quantity: float = 1.0, unit: str = "",
                             notes: str = "", source_plugin: str = "",
                             source_item_id: str = "", project_id: str = "",
                             section_title: str = "General") -> ShoppingItem:
        """Called by other plugins to add items to the shopping list."""
        section_id = self.ensure_section(list_id, section_title)
        item = ShoppingItem(
            name=name, list_id=list_id, section_id=section_id,
            category=category, quantity=quantity, unit=unit,
            notes=notes, source_plugin=source_plugin,
            source_item_id=source_item_id, project_id=project_id,
        )
        result, _ = self.add_item(item, merge_duplicates=True)
        return result
