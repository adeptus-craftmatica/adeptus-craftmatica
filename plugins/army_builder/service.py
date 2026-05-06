"""
Army Builder Service

Business logic. Owns all rules about army lists and their units.

Cross-plugin integration:
  - Registers itself as "army_service" in ServiceRegistry.
  - Future plugins (encounter builder, campaign tracker) can call:
        context.services.get("army_service")
  - Handles model_removed / model_updated events via on_model_removed().
"""
from __future__ import annotations

from typing import Optional

from .models import (
    Army, ArmyUnit, ArmyFilter, ArmyStatistics,
    ValidationError, get_roles_for_system,
)
from .repository import ArmyRepository


class ArmyService:
    def __init__(self, repository: ArmyRepository):
        self.repo = repository

    # ============================================================
    # ARMY CRUD
    # ============================================================

    def create_army(
        self,
        name: str,
        game_system: str,
        faction: str,
        format: str,
        points_limit: int = 0,
        notes: Optional[str] = None,
    ) -> Army:
        army = Army(
            name=name,
            game_system=game_system,
            faction=faction,
            format=format,
            points_limit=points_limit,
            notes=notes,
        )
        army_id = self.repo.add_army(army)
        army.id = army_id
        return army

    def update_army(
        self,
        army_id: int,
        name: str,
        game_system: str,
        faction: str,
        format: str,
        points_limit: int = 0,
        notes: Optional[str] = None,
    ) -> Army:
        existing = self.repo.get_army(army_id)
        if not existing:
            raise ValueError(f"Army {army_id} not found")

        updated = Army(
            id=army_id,
            name=name,
            game_system=game_system,
            faction=faction,
            format=format,
            points_limit=points_limit,
            notes=notes,
        )
        if not self.repo.update_army(updated):
            raise ValueError(f"Failed to update army {army_id}")
        return updated

    def delete_army(self, army_id: int) -> bool:
        return self.repo.delete_army(army_id)

    def get_army(self, army_id: int) -> Optional[Army]:
        return self.repo.get_army(army_id)

    def get_all_armies(self) -> list[Army]:
        return self.repo.get_all_armies()

    def search_armies(self, f: ArmyFilter) -> list[Army]:
        armies = self.repo.find_armies(f)
        if f.sort_by:
            try:
                armies.sort(
                    key=lambda a: (getattr(a, f.sort_by, "") or "").lower()
                    if isinstance(getattr(a, f.sort_by, ""), str)
                    else getattr(a, f.sort_by, 0),
                    reverse=f.sort_desc,
                )
            except Exception as e:
                print(f"[ARMY SERVICE] Sorting failed: {e}")
        return armies

    def duplicate_army(self, army_id: int, new_name: Optional[str] = None) -> Army:
        """
        Deep-copies an army and all its units under a new name.
        """
        source = self.repo.get_army(army_id)
        if not source:
            raise ValueError(f"Army {army_id} not found")

        copy_name = new_name or f"{source.name} (Copy)"
        new_army = self.create_army(
            name=copy_name,
            game_system=source.game_system,
            faction=source.faction,
            format=source.format,
            points_limit=source.points_limit,
            notes=source.notes,
        )

        source_units = self.repo.get_units_for_army(army_id)
        for unit in source_units:
            self.add_unit(
                army_id=new_army.id,
                unit_name=unit.unit_name,
                unit_role=unit.unit_role,
                points_cost=unit.points_cost,
                quantity=unit.quantity,
                wargear_notes=unit.wargear_notes,
                model_id=unit.model_id,
                linked_paint_ids=list(unit.linked_paint_ids),
                sort_order=unit.sort_order,
            )

        return new_army

    # ============================================================
    # UNIT CRUD
    # ============================================================

    def add_unit(
        self,
        army_id: int,
        unit_name: str,
        unit_role: str,
        points_cost: float,
        quantity: int = 1,
        wargear_notes: Optional[str] = None,
        model_id: Optional[int] = None,
        linked_paint_ids: Optional[list[int]] = None,
        sort_order: int = 0,
    ) -> ArmyUnit:
        unit = ArmyUnit(
            army_id=army_id,
            unit_name=unit_name,
            unit_role=unit_role,
            points_cost=points_cost,
            quantity=quantity,
            wargear_notes=wargear_notes,
            model_id=model_id,
            linked_paint_ids=linked_paint_ids or [],
            sort_order=sort_order,
        )
        unit_id = self.repo.add_unit(unit)
        unit.id = unit_id
        return unit

    def update_unit(
        self,
        unit_id: int,
        unit_name: str,
        unit_role: str,
        points_cost: float,
        quantity: int = 1,
        wargear_notes: Optional[str] = None,
        model_id: Optional[int] = None,
        linked_paint_ids: Optional[list[int]] = None,
        sort_order: int = 0,
    ) -> ArmyUnit:
        existing = self.repo.get_unit(unit_id)
        if not existing:
            raise ValueError(f"Unit {unit_id} not found")

        updated = ArmyUnit(
            id=unit_id,
            army_id=existing.army_id,
            unit_name=unit_name,
            unit_role=unit_role,
            points_cost=points_cost,
            quantity=quantity,
            wargear_notes=wargear_notes,
            model_id=model_id,
            linked_paint_ids=linked_paint_ids if linked_paint_ids is not None else existing.linked_paint_ids,
            sort_order=sort_order,
        )
        if not self.repo.update_unit(updated):
            raise ValueError(f"Failed to update unit {unit_id}")
        return updated

    def remove_unit(self, unit_id: int) -> bool:
        return self.repo.delete_unit(unit_id)

    def get_units_for_army(self, army_id: int) -> list[ArmyUnit]:
        return self.repo.get_units_for_army(army_id)

    def get_unit(self, unit_id: int) -> Optional[ArmyUnit]:
        return self.repo.get_unit(unit_id)

    def duplicate_unit(self, unit_id: int) -> ArmyUnit:
        """Create an identical copy of a unit in the same army."""
        existing = self.repo.get_unit(unit_id)
        if not existing:
            raise ValueError(f"Unit {unit_id} not found")
        copy = ArmyUnit(
            army_id=existing.army_id,
            unit_name=f"{existing.unit_name} (Copy)",
            unit_role=existing.unit_role,
            points_cost=existing.points_cost,
            quantity=existing.quantity,
            wargear_notes=existing.wargear_notes,
            model_id=existing.model_id,
            linked_paint_ids=list(existing.linked_paint_ids),
            sort_order=existing.sort_order + 1,
        )
        copy.id = self.repo.add_unit(copy)
        return copy

    # ============================================================
    # POINTS
    # ============================================================

    def get_points_total(self, army_id: int) -> float:
        return self.repo.get_points_total_for_army(army_id)

    def get_points_total_from_units(self, units: list[ArmyUnit]) -> float:
        return sum(u.points_cost * u.quantity for u in units)

    # ============================================================
    # STATISTICS
    # ============================================================

    def get_statistics(self) -> ArmyStatistics:
        armies = self.repo.get_all_armies()
        return self._build_stats(armies)

    def get_statistics_from_subset(self, armies: list[Army]) -> ArmyStatistics:
        return self._build_stats(armies)

    def _build_stats(self, armies: list[Army]) -> ArmyStatistics:
        system_dist: dict[str, int] = {}
        faction_dist: dict[str, int] = {}
        total_units = 0
        total_pts = 0
        largest_name = ""
        largest_pts = 0

        for a in armies:
            system_dist[a.game_system] = system_dist.get(a.game_system, 0) + 1
            faction_dist[a.faction] = faction_dist.get(a.faction, 0) + 1

            pts = self.repo.get_points_total_for_army(a.id) if a.id else 0
            total_pts += pts
            total_units += self.repo.count_units_for_army(a.id) if a.id else 0

            if pts > largest_pts:
                largest_pts = pts
                largest_name = a.name

        avg_pts = total_pts / len(armies) if armies else 0.0

        return ArmyStatistics(
            total_armies=len(armies),
            total_units=total_units,
            game_system_distribution=system_dist,
            faction_distribution=faction_dist,
            average_points=avg_pts,
            largest_army_name=largest_name,
            largest_army_points=largest_pts,
        )

    # ============================================================
    # DROPDOWN OPTIONS
    # ============================================================

    def get_game_systems(self) -> list[str]:
        return sorted({s.strip() for s in self.repo.get_unique_game_systems() if s and s.strip()})

    def get_factions(self, game_system: Optional[str] = None) -> list[str]:
        return sorted({f.strip() for f in self.repo.get_unique_factions(game_system) if f and f.strip()})

    # ============================================================
    # EXPORT
    # ============================================================

    def export_as_text(self, army: Army, units: list[ArmyUnit]) -> str:
        """
        Generates a plain-text army list suitable for copying / sharing.
        """
        def _fmt_pts(v: float) -> str:
            return str(int(v)) if v == int(v) else f"{v:g}"

        total_pts = sum(u.total_points for u in units)
        limit_str = f" / {_fmt_pts(army.points_limit)}pts" if army.points_limit > 0 else ""

        lines = [
            f"{'=' * 60}",
            f"  {army.name}",
            f"  {army.game_system} — {army.faction}",
            f"  Format: {army.format}",
            f"  Total: {_fmt_pts(total_pts)}pts{limit_str}",
            f"{'=' * 60}",
            "",
        ]

        # Group by role
        roles_order = get_roles_for_system(army.game_system)
        grouped: dict[str, list[ArmyUnit]] = {}
        for unit in units:
            grouped.setdefault(unit.unit_role, []).append(unit)

        # Emit known roles first (in order), then any extras
        ordered_roles = [r for r in roles_order if r in grouped]
        extra_roles = [r for r in grouped if r not in roles_order]
        all_roles = ordered_roles + extra_roles

        for role in all_roles:
            role_units = grouped[role]
            role_pts = sum(u.total_points for u in role_units)
            pts_label = f"  [{_fmt_pts(role_pts)}pts]" if role_pts > 0 else ""
            lines.append(f"── {role.upper()}{pts_label}")

            for u in role_units:
                qty_str = f" × {u.quantity}" if u.quantity > 1 else ""
                unit_total = u.total_points
                if unit_total > 0:
                    cost_str = _fmt_pts(u.points_cost)
                    total_str = _fmt_pts(unit_total)
                    pts_str = f"  [{cost_str}pts ea, {total_str}pts total]" if u.quantity > 1 else f"  [{total_str}pts]"
                else:
                    pts_str = ""
                lines.append(f"    {u.unit_name}{qty_str}{pts_str}")
                if u.wargear_notes:
                    lines.append(f"      ↳ {u.wargear_notes}")

            lines.append("")

        lines += [
            f"{'─' * 60}",
            f"  TOTAL: {_fmt_pts(total_pts)}pts{limit_str}",
            f"{'─' * 60}",
        ]

        return "\n".join(lines)

    # ============================================================
    # CROSS-PLUGIN
    # ============================================================

    def on_model_removed(self, model_id: int):
        """Called when model_tracker removes a model — nullify references."""
        self.repo.remove_model_links(model_id)
        print(f"[ARMY SERVICE] Nullified model_id={model_id} links in army units")

    def on_paint_removed(self, paint_id: int):
        """Called when paint_tracker removes a paint — clean up direct links."""
        self.repo.remove_paint_links_everywhere(paint_id)
        print(f"[ARMY SERVICE] Removed paint_id={paint_id} links from all army units")

    def get_units_using_model(self, model_id: int) -> list[ArmyUnit]:
        """Returns all army units referencing a given model_tracker model."""
        all_units = []
        for army in self.repo.get_all_armies():
            units = self.repo.get_units_for_army(army.id)
            all_units.extend(u for u in units if u.model_id == model_id)
        return all_units

    def get_army_paint_list(self, army_id: int, model_service=None) -> list[dict]:
        """
        Aggregate all paints needed for an army.

        Sources (deduplicated by paint_id):
          1. Direct unit → paint links  (unit.linked_paint_ids)
          2. Model-derived links        (unit.model_id → model.linked_paint_ids)

        Returns a list of dicts:
            {
              "paint_id":  int,
              "unit_names": [str, ...],   which units reference this paint
              "sources":    {"direct", "model"},
            }
        """
        units = self.repo.get_units_for_army(army_id)

        # paint_id → {"unit_names": set, "sources": set}
        aggregated: dict[int, dict] = {}

        def _add(paint_id: int, unit_name: str, source: str):
            if paint_id not in aggregated:
                aggregated[paint_id] = {"unit_names": set(), "sources": set()}
            aggregated[paint_id]["unit_names"].add(unit_name)
            aggregated[paint_id]["sources"].add(source)

        for unit in units:
            # Source 1: direct links on this unit
            for pid in unit.linked_paint_ids:
                _add(pid, unit.unit_name, "direct")

            # Source 2: via model_tracker
            if unit.model_id and model_service:
                try:
                    model = model_service.get_model(unit.model_id)
                    if model:
                        for pid in model.linked_paint_ids:
                            _add(pid, unit.unit_name, "model")
                except Exception as e:
                    print(f"[ARMY SERVICE] model paint lookup failed: {e}")

        return [
            {
                "paint_id": pid,
                "unit_names": sorted(info["unit_names"]),
                "sources": info["sources"],
            }
            for pid, info in aggregated.items()
        ]


# ============================================================
# AUTO-REGISTRATION
# ============================================================

def register(context):
    """
    Auto-registered by PluginManager.
    Registers as "army_service" — accessible by any plugin via:
        context.services.get("army_service")
    """
    print("[ARMY_BUILDER] Registering service...")
    db = context.services.get("db")
    repo = ArmyRepository(db)
    service = ArmyService(repo)
    context.services.register("army_service", service, override=True)
    print("[ARMY_BUILDER] Service registered as 'army_service'")
    return service
