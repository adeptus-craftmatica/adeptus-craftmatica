"""
Materials Tracker — Service Layer (business logic)
"""
from __future__ import annotations

from typing import Optional

from .models import Material, MaterialFilter, MaterialStatistics, ValidationError
from .repository import MaterialRepository


class MaterialService:
    def __init__(self, repository: MaterialRepository):
        self.repo = repository

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add_material(
        self,
        name:          str,
        material_type: str,
        brand:         str = "",
        color:         str = "",
        stock:         str = "Good",
        quantity:      int = 1,
        notes:         Optional[str] = None,
    ) -> Material:
        material = Material(
            name=name, material_type=material_type, brand=brand,
            color=color, stock=stock, quantity=quantity, notes=notes,
        )
        if self._is_duplicate(material):
            raise ValidationError(f"'{name}' already exists in {material_type}")
        material_id = self.repo.add(material)
        return Material(
            id=material_id, name=material.name,
            material_type=material.material_type, brand=material.brand,
            color=material.color, stock=material.stock,
            quantity=material.quantity, notes=material.notes,
        )

    def update_material(
        self,
        material_id:   int,
        name:          str,
        material_type: str,
        brand:         str = "",
        color:         str = "",
        stock:         str = "Good",
        quantity:      int = 1,
        notes:         Optional[str] = None,
    ) -> Material:
        if not self.repo.get_by_id(material_id):
            raise ValueError(f"Material {material_id} not found")
        updated = Material(
            id=material_id, name=name, material_type=material_type,
            brand=brand, color=color, stock=stock,
            quantity=quantity, notes=notes,
        )
        if self._is_duplicate(updated, exclude_id=material_id):
            raise ValidationError(f"'{name}' already exists in {material_type}")
        if not self.repo.update(updated):
            raise ValueError(f"Failed to update material {material_id}")
        return updated

    def remove_material(self, material_id: int) -> bool:
        return self.repo.delete(material_id)

    def get_material(self, material_id: int) -> Optional[Material]:
        return self.repo.get_by_id(material_id)

    def get_all_materials(self) -> list[Material]:
        return self.repo.get_all()

    # ── Search / filter ───────────────────────────────────────────────────────

    def search_materials(self, f: MaterialFilter) -> list[Material]:
        materials = self.repo.find(f)
        if f.sort_by:
            try:
                materials.sort(
                    key=lambda m: (getattr(m, f.sort_by, "") or "").lower()
                    if isinstance(getattr(m, f.sort_by, ""), str)
                    else getattr(m, f.sort_by, 0),
                    reverse=f.sort_desc,
                )
            except Exception as e:
                print(f"[MATERIAL SERVICE] Sort failed: {e}")
        return materials

    # ── Statistics ────────────────────────────────────────────────────────────

    def get_statistics(self) -> MaterialStatistics:
        return MaterialStatistics(
            total_count=self.repo.count(),
            unique_types=len(self.repo.get_unique_types()),
            unique_brands=len(self.repo.get_unique_brands()),
            needs_restock=sum(
                1 for m in self.repo.get_all()
                if m.stock in ("Low", "Empty")
            ),
            types_distribution=self.repo.count_by_type(),
            stock_distribution=self.repo.count_by_stock(),
            brands_distribution=self.repo.count_by_brand(),
        )

    def get_statistics_from_subset(self, materials: list[Material]) -> MaterialStatistics:
        types  = {}
        stocks = {}
        brands = {}
        for m in materials:
            types[m.material_type] = types.get(m.material_type, 0) + 1
            stocks[m.stock] = stocks.get(m.stock, 0) + 1
            if m.brand:
                brands[m.brand] = brands.get(m.brand, 0) + 1
        needs_restock = sum(1 for m in materials if m.stock in ("Low", "Empty"))
        return MaterialStatistics(
            total_count=len(materials),
            unique_types=len(types),
            unique_brands=len(brands),
            needs_restock=needs_restock,
            types_distribution=types,
            stock_distribution=stocks,
            brands_distribution=brands,
        )

    def get_types(self) -> list[str]:
        return sorted({t.strip() for t in self.repo.get_unique_types() if t and t.strip()})

    def get_brands(self) -> list[str]:
        return sorted({b.strip() for b in self.repo.get_unique_brands() if b and b.strip()})

    # ── Business rules ────────────────────────────────────────────────────────

    def _is_duplicate(self, material: Material, exclude_id: Optional[int] = None) -> bool:
        for existing in self.repo.get_all():
            if exclude_id and existing.id == exclude_id:
                continue
            if (
                existing.name.lower()          == material.name.lower()
                and existing.material_type.lower() == material.material_type.lower()
            ):
                return True
        return False


# ── Auto-registration ──────────────────────────────────────────────────────────

def register(context):
    print("[MATERIALS_TRACKER] Registering service...")
    repo    = context.services.get("material_repository")
    service = MaterialService(repo)
    context.services.register("material_service", service, override=True)
    print("[MATERIALS_TRACKER] Service registered")
    return service
