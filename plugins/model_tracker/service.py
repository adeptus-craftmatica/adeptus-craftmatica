"""
Model Tracker Service

Business logic layer. Owns all rules about models and their paint links.

Cross-plugin integration:
  - Registers itself as "model_service" in ServiceRegistry so other plugins
    (army builder, encounter builder, etc.) can call it directly.
  - Listens for "paint_removed" events via the plugin (not here) to keep
    paint links consistent.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from typing import Optional

from .models import Model, ModelFilter, ModelStatistics, ValidationError
from .repository import ModelRepository


class ModelService:
    def __init__(self, repository: ModelRepository):
        self.repo = repository

    # ============================================================
    # CORE CRUD
    # ============================================================

    def add_model(
        self,
        name: str,
        game_system: str,
        faction: str,
        model_type: str,
        status: str,
        scale: str = "",
        quantity: int = 1,
        notes: Optional[str] = None,
        linked_paint_ids: Optional[list[int]] = None,
        image_path: Optional[str] = None,
    ) -> Model:
        model = Model(
            name=name,
            game_system=game_system,
            faction=faction,
            model_type=model_type,
            status=status,
            scale=scale,
            quantity=quantity,
            notes=notes,
            linked_paint_ids=linked_paint_ids or [],
            image_path=image_path,
        )
        model_id = self.repo.add(model)
        return Model(
            id=model_id,
            name=model.name,
            game_system=model.game_system,
            faction=model.faction,
            model_type=model.model_type,
            status=model.status,
            scale=model.scale,
            quantity=model.quantity,
            notes=model.notes,
            linked_paint_ids=model.linked_paint_ids,
            image_path=model.image_path,
        )

    def update_model(
        self,
        model_id: int,
        name: str,
        game_system: str,
        faction: str,
        model_type: str,
        status: str,
        scale: str = "",
        quantity: int = 1,
        notes: Optional[str] = None,
        linked_paint_ids: Optional[list[int]] = None,
        image_path: Optional[str] = None,
    ) -> Model:
        if not self.repo.get_by_id(model_id):
            raise ValueError(f"Model with ID {model_id} not found")

        updated = Model(
            id=model_id,
            name=name,
            game_system=game_system,
            faction=faction,
            model_type=model_type,
            status=status,
            scale=scale,
            quantity=quantity,
            notes=notes,
            linked_paint_ids=linked_paint_ids or [],
            image_path=image_path,
        )
        if not self.repo.update(updated):
            raise ValueError(f"Failed to update model {model_id}")
        return updated

    def remove_model(self, model_id: int) -> bool:
        return self.repo.delete(model_id)

    def get_model(self, model_id: int) -> Optional[Model]:
        return self.repo.get_by_id(model_id)

    def get_all_models(self) -> list[Model]:
        return self.repo.get_all()

    # ============================================================
    # SEARCH + SORT
    # ============================================================

    def search_models(self, f: ModelFilter) -> list[Model]:
        models = self.repo.find(f)
        if f.sort_by:
            try:
                models.sort(
                    key=lambda m: (getattr(m, f.sort_by, "") or "").lower()
                    if isinstance(getattr(m, f.sort_by, ""), str)
                    else getattr(m, f.sort_by, 0),
                    reverse=f.sort_desc,
                )
            except Exception as e:
                log.error(f"[MODEL SERVICE] Sorting failed: {e}")
        return models

    # ============================================================
    # STATISTICS
    # ============================================================

    def get_statistics(self) -> ModelStatistics:
        return self._build_stats(self.repo.get_all())

    def get_statistics_from_subset(self, models: list[Model]) -> ModelStatistics:
        return self._build_stats(models)

    def _build_stats(self, models: list[Model]) -> ModelStatistics:
        status_dist: dict[str, int] = {}
        system_dist: dict[str, int] = {}
        faction_dist: dict[str, int] = {}
        total_models = 0

        for m in models:
            total_models += m.quantity
            status_dist[m.status] = status_dist.get(m.status, 0) + 1
            system_dist[m.game_system] = system_dist.get(m.game_system, 0) + 1
            faction_dist[m.faction] = faction_dist.get(m.faction, 0) + 1

        return ModelStatistics(
            total_count=len(models),
            total_models=total_models,
            unique_game_systems=len(system_dist),
            unique_factions=len(faction_dist),
            status_distribution=status_dist,
            game_system_distribution=system_dist,
            faction_distribution=faction_dist,
        )

    # ============================================================
    # DROPDOWN OPTIONS
    # ============================================================

    def get_game_systems(self) -> list[str]:
        return sorted({s.strip() for s in self.repo.get_unique_game_systems() if s and s.strip()})

    def get_factions(self, game_system: Optional[str] = None) -> list[str]:
        return sorted({f.strip() for f in self.repo.get_unique_factions(game_system) if f and f.strip()})

    def get_types(self) -> list[str]:
        return sorted({t.strip() for t in self.repo.get_unique_types() if t and t.strip()})

    # ============================================================
    # CROSS-PLUGIN: PAINT LINKS
    # ============================================================

    def on_paint_removed(self, paint_id: int):
        """
        Called when paint_tracker removes a paint.
        Cleans up all model → paint links for that paint_id.
        """
        self.repo.remove_paint_link_everywhere(paint_id)
        log.debug(f"[MODEL SERVICE] Removed paint link for paint_id={paint_id} from all models")

    def get_models_using_paint(self, paint_id: int) -> list[Model]:
        """Returns all models that reference a given paint (for cross-plugin queries)."""
        model_ids = self.repo.get_models_using_paint(paint_id)
        return [m for m in [self.repo.get_by_id(mid) for mid in model_ids] if m]

    # ============================================================
    # IMAGE GALLERY
    # ============================================================

    def get_images_for_model(self, model_id: int) -> list[dict]:
        """Return ordered list of {id, image_path, sort_order} dicts for a model."""
        return self.repo.get_images(model_id)

    def add_image(self, model_id: int, path: str) -> int:
        """Register an image path for a model. Deduplicates silently."""
        return self.repo.add_image(model_id, path)

    def remove_image(self, image_id: int) -> bool:
        return self.repo.delete_image(image_id)

    def set_primary_image(self, model_id: int, path: Optional[str]):
        """Update the model's primary thumbnail (image_path on the model row)."""
        model = self.repo.get_by_id(model_id)
        if model:
            model.image_path = path
            self.repo.update(model)


# ============================================================
# AUTO-REGISTRATION
# ============================================================

def register(context):
    """
    Auto-registered by PluginManager.
    Creates the ModelService and registers it as "model_service"
    so any other plugin can call:
        context.services.get("model_service")
    """
    log.debug("[MODEL_TRACKER] Registering service...")
    db = context.services.get("db")
    repo = ModelRepository(db)
    service = ModelService(repo)
    context.services.register("model_service", service, override=True)
    log.debug("[MODEL_TRACKER] Service registered as 'model_service'")
    return service
