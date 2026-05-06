"""
Paint Scheme Service

Business logic layer for managing paint schemes, their steps and model links.
Registered as 'scheme_service' in the service registry.
"""

from __future__ import annotations

from typing import Optional

from .models import PaintScheme, SchemeStep, SchemeFilter
from .repository import SchemeRepository


class SchemeService:
    def __init__(self, repository: SchemeRepository):
        self.repo = repository

    # ============================================================
    # SCHEME OPERATIONS
    # ============================================================

    def add_scheme(
        self,
        name: str,
        game_system: str = "",
        faction: str = "",
        description: str = "",
    ) -> PaintScheme:
        if not name or not name.strip():
            raise ValueError("Scheme name cannot be empty")

        scheme = PaintScheme(
            name=name.strip(),
            game_system=game_system.strip() if game_system else "",
            faction=faction.strip() if faction else "",
            description=description.strip() if description else "",
        )
        scheme_id = self.repo.add_scheme(scheme)
        scheme.id = scheme_id
        return scheme

    def update_scheme(self, scheme_id: int, **kwargs) -> PaintScheme:
        scheme = self.repo.get_scheme_by_id(scheme_id)
        if not scheme:
            raise ValueError(f"Scheme with id {scheme_id} not found")

        if "name" in kwargs:
            val = kwargs["name"]
            if not val or not str(val).strip():
                raise ValueError("Scheme name cannot be empty")
            scheme.name = str(val).strip()

        if "game_system" in kwargs:
            scheme.game_system = str(kwargs["game_system"]).strip() if kwargs["game_system"] else ""
        if "faction" in kwargs:
            scheme.faction = str(kwargs["faction"]).strip() if kwargs["faction"] else ""
        if "description" in kwargs:
            scheme.description = str(kwargs["description"]).strip() if kwargs["description"] else ""

        self.repo.update_scheme(scheme)
        return self.repo.get_scheme_by_id(scheme_id)

    def delete_scheme(self, scheme_id: int) -> bool:
        return self.repo.delete_scheme(scheme_id)

    def get_scheme(self, scheme_id: int) -> Optional[PaintScheme]:
        return self.repo.get_scheme_by_id(scheme_id)

    def get_all_schemes(self) -> list[PaintScheme]:
        return self.repo.get_all_schemes()

    def search_schemes(self, f: SchemeFilter) -> list[PaintScheme]:
        return self.repo.find_schemes(f)

    # ============================================================
    # STEP OPERATIONS
    # ============================================================

    def add_step(
        self,
        scheme_id: int,
        technique: str = "Basecoat",
        paint_id: Optional[int] = None,
        paint_name: str = "",
        notes: str = "",
    ) -> SchemeStep:
        # Determine the next step order
        existing = self.repo.get_steps_for_scheme(scheme_id)
        next_order = (max((s.step_order for s in existing), default=0) + 1)

        step = SchemeStep(
            scheme_id=scheme_id,
            step_order=next_order,
            technique=technique,
            paint_id=paint_id,
            paint_name=paint_name.strip() if paint_name else "",
            notes=notes.strip() if notes else "",
        )
        step_id = self.repo.add_step(step)
        step.id = step_id
        return step

    def update_step(self, step_id: int, **kwargs) -> SchemeStep:
        step = self.repo.get_step_by_id(step_id)
        if not step:
            raise ValueError(f"Step with id {step_id} not found")

        if "technique" in kwargs:
            step.technique = str(kwargs["technique"])
        if "paint_id" in kwargs:
            step.paint_id = kwargs["paint_id"]  # may be None
        if "paint_name" in kwargs:
            step.paint_name = str(kwargs["paint_name"]).strip() if kwargs["paint_name"] else ""
        if "notes" in kwargs:
            step.notes = str(kwargs["notes"]).strip() if kwargs["notes"] else ""
        if "step_order" in kwargs:
            step.step_order = int(kwargs["step_order"])

        self.repo.update_step(step)
        return self.repo.get_step_by_id(step_id)

    def delete_step(self, step_id: int) -> bool:
        step = self.repo.get_step_by_id(step_id)
        if not step:
            return False
        success = self.repo.delete_step(step_id)
        if success:
            # Re-number remaining steps so order is contiguous
            self._renumber_steps(step.scheme_id)
        return success

    def get_steps(self, scheme_id: int) -> list[SchemeStep]:
        return self.repo.get_steps_for_scheme(scheme_id)

    def reorder_steps(self, scheme_id: int, ordered_step_ids: list[int]):
        """Reassign step_order 1..N based on the provided ordered list of step ids."""
        for i, step_id in enumerate(ordered_step_ids, start=1):
            step = self.repo.get_step_by_id(step_id)
            if step and step.scheme_id == scheme_id:
                step.step_order = i
                self.repo.update_step(step)

    # ============================================================
    # MODEL LINK OPERATIONS
    # ============================================================

    def link_model(self, scheme_id: int, model_id: int):
        self.repo.add_model_link(scheme_id, model_id)

    def unlink_model(self, scheme_id: int, model_id: int):
        self.repo.remove_model_link(scheme_id, model_id)

    def get_linked_models(self, scheme_id: int) -> list[int]:
        return self.repo.get_linked_model_ids(scheme_id)

    def get_schemes_for_model(self, model_id: int) -> list[PaintScheme]:
        scheme_ids = self.repo.get_scheme_ids_for_model(model_id)
        schemes = []
        for sid in scheme_ids:
            s = self.repo.get_scheme_by_id(sid)
            if s:
                schemes.append(s)
        return schemes

    # ============================================================
    # INTERNAL HELPERS
    # ============================================================

    def _renumber_steps(self, scheme_id: int):
        """Ensure steps are numbered 1..N without gaps after a deletion."""
        steps = self.repo.get_steps_for_scheme(scheme_id)
        for i, step in enumerate(steps, start=1):
            if step.step_order != i:
                step.step_order = i
                self.repo.update_step(step)


# ============================================================
# AUTO-REGISTRATION
# ============================================================

def register(context):
    print("[PAINT_SCHEME] Registering service...")

    db = context.services.get("db")
    if not db:
        print("[PAINT_SCHEME] ERROR: db service not available")
        return None

    repo = SchemeRepository(db)
    service = SchemeService(repo)

    context.services.register("scheme_service", service, override=True)

    print("[PAINT_SCHEME] Service registered as 'scheme_service'")
    return service
