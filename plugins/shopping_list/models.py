"""Shopping List — domain models."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

CATEGORIES = [
    "Paint", "Tool", "Material", "Miniature",
    "Terrain", "Accessory", "Consumable", "Other",
]

CATEGORY_ICONS = {
    "Paint": "🎨", "Tool": "🔧", "Material": "🧱",
    "Miniature": "⚔️", "Terrain": "🌄", "Accessory": "🎒",
    "Consumable": "🧪", "Other": "📦",
}


@dataclass
class ShoppingItem:
    name: str
    list_id: int = 0
    section_id: int = 0
    category: str = "Other"
    quantity: float = 1.0
    unit: str = ""
    notes: str = ""
    purchased: bool = False
    source_plugin: str = ""
    source_item_id: str = ""
    project_id: str = ""
    id: Optional[int] = None
    created_at: str = ""
    updated_at: str = ""

    def icon(self) -> str:
        return CATEGORY_ICONS.get(self.category, "📦")

    def qty_display(self) -> str:
        if self.unit:
            q = int(self.quantity) if self.quantity == int(self.quantity) else self.quantity
            return f"{q} {self.unit}"
        q = int(self.quantity) if self.quantity == int(self.quantity) else self.quantity
        return f"×{q}"


@dataclass
class ShoppingSection:
    title: str
    list_id: int
    source_type: str = "custom"   # "custom" | "project" | "inventory"
    source_project_id: str = ""
    sort_order: int = 0
    collapsed: bool = False
    id: Optional[int] = None
    items: list = field(default_factory=list)


@dataclass
class ShoppingList:
    name: str
    id: Optional[int] = None
    created_at: str = ""
    updated_at: str = ""
    sections: list = field(default_factory=list)
