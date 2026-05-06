"""
Model Tracker Domain Models

Pure domain objects — no framework or infrastructure dependencies.
Handles validation and business rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class ValidationError(Exception):
    """Raised when domain validation fails."""
    pass


# ============================================================
# CONSTANTS
# ============================================================

VALID_STATUSES = [
    "Unassembled",
    "Assembled",
    "Primed",
    "WIP",
    "Painted",
    "Based",
    "Complete",
]

STATUS_COLORS = {
    "Unassembled": "#666666",
    "Assembled":   "#888888",
    "Primed":      "#aaaaaa",
    "WIP":         "#e07800",
    "Painted":     "#3377cc",
    "Based":       "#339944",
    "Complete":    "#00bb55",
}

COMMON_GAME_SYSTEMS = [
    "Warhammer 40,000",
    "Warhammer: Age of Sigmar",
    "Warhammer: The Old World",
    "Horus Heresy",
    "Kill Team",
    "Necromunda",
    "Middle Earth Strategy Battle Game",
    "Dungeons & Dragons",
    "Pathfinder",
    "Gundam",
    "Star Wars: Legion",
    "Marvel Crisis Protocol",
    "Bolt Action",
    "Other",
]

COMMON_MODEL_TYPES = [
    "Infantry",
    "Character / Hero",
    "Monster / Beast",
    "Vehicle / Tank",
    "Cavalry",
    "Artillery",
    "Mech / Mobile Suit",
    "Terrain",
    "Scenery",
    "Other",
]


# ============================================================
# MODEL
# ============================================================

@dataclass
class Model:
    """Core domain model representing a physical miniature or model kit."""
    name: str
    game_system: str
    faction: str
    model_type: str
    status: str
    scale: str = ""
    quantity: int = 1
    notes: Optional[str] = None
    linked_paint_ids: list[int] = field(default_factory=list)
    image_path: Optional[str] = None
    id: Optional[int] = None

    def __post_init__(self):
        self._validate()

    def _validate(self):
        if not self.name or not self.name.strip():
            raise ValidationError("Name cannot be empty")
        if len(self.name.strip()) > 200:
            raise ValidationError("Name cannot exceed 200 characters")

        if not self.game_system or not self.game_system.strip():
            raise ValidationError("Game system cannot be empty")
        if len(self.game_system.strip()) > 100:
            raise ValidationError("Game system cannot exceed 100 characters")

        if not self.faction or not self.faction.strip():
            raise ValidationError("Faction / Collection cannot be empty")
        if len(self.faction.strip()) > 100:
            raise ValidationError("Faction cannot exceed 100 characters")

        if not self.model_type or not self.model_type.strip():
            raise ValidationError("Model type cannot be empty")
        if len(self.model_type.strip()) > 100:
            raise ValidationError("Model type cannot exceed 100 characters")

        if not self.status or self.status not in VALID_STATUSES:
            raise ValidationError(f"Status must be one of: {', '.join(VALID_STATUSES)}")

        if not isinstance(self.quantity, int) or self.quantity < 1:
            raise ValidationError("Quantity must be a positive integer")

        if self.notes and len(self.notes) > 2000:
            raise ValidationError("Notes cannot exceed 2000 characters")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name.strip(),
            "game_system": self.game_system.strip(),
            "faction": self.faction.strip(),
            "model_type": self.model_type.strip(),
            "status": self.status,
            "scale": self.scale.strip() if self.scale else "",
            "quantity": self.quantity,
            "notes": self.notes,
            "linked_paint_ids": self.linked_paint_ids,
            "image_path": self.image_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Model":
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            game_system=data.get("game_system", ""),
            faction=data.get("faction", ""),
            model_type=data.get("model_type", ""),
            status=data.get("status", "Unassembled"),
            scale=data.get("scale", ""),
            quantity=data.get("quantity", 1),
            notes=data.get("notes"),
            linked_paint_ids=data.get("linked_paint_ids", []),
            image_path=data.get("image_path"),
        )


# ============================================================
# FILTER
# ============================================================

@dataclass
class ModelFilter:
    """Filter criteria for querying models. All fields optional."""
    search_text: Optional[str] = None
    game_system: Optional[str] = None
    faction: Optional[str] = None
    model_type: Optional[str] = None
    status: Optional[str] = None
    sort_by: Optional[str] = None
    sort_desc: bool = False

    def matches(self, model: Model) -> bool:
        if self.game_system and self.game_system.lower() not in model.game_system.lower():
            return False
        if self.faction and self.faction.lower() not in model.faction.lower():
            return False
        if self.model_type and self.model_type.lower() not in model.model_type.lower():
            return False
        if self.status and self.status != model.status:
            return False
        if self.search_text:
            needle = self.search_text.lower()
            haystack = f"{model.name} {model.game_system} {model.faction} {model.model_type}".lower()
            if needle not in haystack:
                return False
        return True

    def is_empty(self) -> bool:
        return not any([
            self.game_system, self.faction, self.model_type,
            self.status, self.search_text,
        ])


# ============================================================
# STATISTICS
# ============================================================

@dataclass
class ModelStatistics:
    """Aggregated statistics about the model collection."""
    total_count: int          # unique entries
    total_models: int         # sum of quantities
    unique_game_systems: int
    unique_factions: int
    status_distribution: dict[str, int] = field(default_factory=dict)
    game_system_distribution: dict[str, int] = field(default_factory=dict)
    faction_distribution: dict[str, int] = field(default_factory=dict)
