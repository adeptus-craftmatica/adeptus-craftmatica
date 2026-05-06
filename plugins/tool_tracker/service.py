"""
Tool Tracker — Service Layer (business logic)
"""
from __future__ import annotations

from typing import Optional

from .models import Tool, ToolFilter, ToolStatistics, ValidationError
from .repository import ToolRepository


class ToolService:
    def __init__(self, repository: ToolRepository):
        self.repo = repository

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add_tool(
        self,
        name:      str,
        tool_type: str,
        brand:     str = "",
        condition: str = "Good",
        quantity:  int = 1,
        notes:     Optional[str] = None,
    ) -> Tool:
        tool = Tool(
            name=name, tool_type=tool_type, brand=brand,
            condition=condition, quantity=quantity, notes=notes,
        )
        if self._is_duplicate(tool):
            raise ValidationError(f"'{name}' already exists in {tool_type}")
        tool_id = self.repo.add(tool)
        return Tool(
            id=tool_id, name=tool.name, tool_type=tool.tool_type,
            brand=tool.brand, condition=tool.condition,
            quantity=tool.quantity, notes=tool.notes,
        )

    def update_tool(
        self,
        tool_id:   int,
        name:      str,
        tool_type: str,
        brand:     str = "",
        condition: str = "Good",
        quantity:  int = 1,
        notes:     Optional[str] = None,
    ) -> Tool:
        if not self.repo.get_by_id(tool_id):
            raise ValueError(f"Tool {tool_id} not found")
        updated = Tool(
            id=tool_id, name=name, tool_type=tool_type, brand=brand,
            condition=condition, quantity=quantity, notes=notes,
        )
        if self._is_duplicate(updated, exclude_id=tool_id):
            raise ValidationError(f"'{name}' already exists in {tool_type}")
        if not self.repo.update(updated):
            raise ValueError(f"Failed to update tool {tool_id}")
        return updated

    def remove_tool(self, tool_id: int) -> bool:
        return self.repo.delete(tool_id)

    def get_tool(self, tool_id: int) -> Optional[Tool]:
        return self.repo.get_by_id(tool_id)

    def get_all_tools(self) -> list[Tool]:
        return self.repo.get_all()

    # ── Search / filter ───────────────────────────────────────────────────────

    def search_tools(self, f: ToolFilter) -> list[Tool]:
        tools = self.repo.find(f)
        if f.sort_by:
            try:
                tools.sort(
                    key=lambda t: (getattr(t, f.sort_by, "") or "").lower()
                    if isinstance(getattr(t, f.sort_by, ""), str)
                    else getattr(t, f.sort_by, 0),
                    reverse=f.sort_desc,
                )
            except Exception as e:
                print(f"[TOOL SERVICE] Sort failed: {e}")
        return tools

    # ── Statistics ────────────────────────────────────────────────────────────

    def get_statistics(self) -> ToolStatistics:
        return ToolStatistics(
            total_count=self.repo.count(),
            unique_types=len(self.repo.get_unique_types()),
            unique_brands=len(self.repo.get_unique_brands()),
            needs_replacement=sum(
                1 for t in self.repo.get_all()
                if t.condition in ("Worn", "Replace")
            ),
            types_distribution=self.repo.count_by_type(),
            conditions_distribution=self.repo.count_by_condition(),
            brands_distribution=self.repo.count_by_brand(),
        )

    def get_statistics_from_subset(self, tools: list[Tool]) -> ToolStatistics:
        types  = {}
        conds  = {}
        brands = {}
        for t in tools:
            types[t.tool_type] = types.get(t.tool_type, 0) + 1
            conds[t.condition] = conds.get(t.condition, 0) + 1
            if t.brand:
                brands[t.brand] = brands.get(t.brand, 0) + 1
        needs_replace = sum(1 for t in tools if t.condition in ("Worn", "Replace"))
        return ToolStatistics(
            total_count=len(tools),
            unique_types=len(types),
            unique_brands=len(brands),
            needs_replacement=needs_replace,
            types_distribution=types,
            conditions_distribution=conds,
            brands_distribution=brands,
        )

    def get_types(self) -> list[str]:
        return sorted({t.strip() for t in self.repo.get_unique_types() if t and t.strip()})

    def get_brands(self) -> list[str]:
        return sorted({b.strip() for b in self.repo.get_unique_brands() if b and b.strip()})

    # ── Business rules ────────────────────────────────────────────────────────

    def _is_duplicate(self, tool: Tool, exclude_id: Optional[int] = None) -> bool:
        for existing in self.repo.get_all():
            if exclude_id and existing.id == exclude_id:
                continue
            if (
                existing.name.lower()      == tool.name.lower()
                and existing.tool_type.lower() == tool.tool_type.lower()
            ):
                return True
        return False


# ── Auto-registration ──────────────────────────────────────────────────────────

def register(context):
    print("[TOOL_TRACKER] Registering service...")
    repo    = context.services.get("tool_repository")
    service = ToolService(repo)
    context.services.register("tool_service", service, override=True)
    print("[TOOL_TRACKER] Service registered")
    return service
