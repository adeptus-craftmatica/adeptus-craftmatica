"""
Army Builder Domain Models

Covers any game that uses lists/rosters:
  Warhammer 40K, Age of Sigmar, Kill Team, Horus Heresy,
  D&D parties, Star Wars Legion, Marvel Crisis Protocol, etc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class ValidationError(Exception):
    pass


# ============================================================
# GAME-SYSTEM PRESETS
# ============================================================

UNIT_ROLES: dict[str, list[str]] = {
    "Warhammer 40,000": [
        "HQ", "Troops", "Elites", "Fast Attack",
        "Heavy Support", "Dedicated Transport", "Flyer",
        "Lord of War", "Agent of the Imperium", "Allied Units",
    ],
    "Warhammer: Age of Sigmar": [
        "Leader", "Battleline", "Behemoth", "Artillery",
        "Endless Spells", "Endless Prayers", "Terrain",
    ],
    "Horus Heresy": [
        "HQ", "Troops", "Elites", "Fast Attack",
        "Heavy Support", "Dedicated Transport",
        "Lord of War", "Fortification",
    ],
    "Kill Team": [
        "Leader", "Medic", "Comms Specialist", "Gunner",
        "Sniper", "Demo Specialist", "Scout", "Operator", "Other",
    ],
    "Necromunda": [
        "Leader", "Champion", "Ganger", "Juve",
        "Specialist", "Exotic Beast", "Hired Gun", "Hanger-On",
    ],
    "Middle Earth Strategy Battle Game": [
        "Hero", "Warrior", "Siege Engine", "Monster", "Cavalry",
    ],
    "Dungeons & Dragons": [
        "Barbarian", "Bard", "Cleric", "Druid", "Fighter",
        "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer",
        "Warlock", "Wizard", "Artificer", "NPC", "Other",
    ],
    "Pathfinder": [
        "Alchemist", "Barbarian", "Bard", "Champion", "Cleric",
        "Druid", "Fighter", "Monk", "Oracle", "Ranger",
        "Rogue", "Sorcerer", "Wizard", "NPC", "Other",
    ],
    "Star Wars: Legion": [
        "Commander", "Operative", "Corps",
        "Special Forces", "Support", "Heavy", "Fortification",
    ],
    "Marvel Crisis Protocol": [
        "Leader", "Core", "Support",
        "Infinity Watch", "Cabal", "Avengers",
        "X-Men", "Guardians of the Galaxy", "S.H.I.E.L.D.",
    ],
    "Bolt Action": [
        "Headquarters", "Infantry Section", "Artillery",
        "Armoured Vehicle", "Soft-Skin Vehicle",
        "Air Support", "Naval Support",
    ],
    "_default": [
        "Commander", "Core", "Elites",
        "Support", "Heavy", "Fast Attack", "Other",
    ],
}

ARMY_FORMATS: dict[str, list[str]] = {
    "Warhammer 40,000": [
        "Combat Patrol (500pts)",
        "Incursion (1000pts)",
        "Strike Force (2000pts)",
        "Onslaught (3000pts)",
        "Open Play",
        "Narrative",
    ],
    "Warhammer: Age of Sigmar": [
        "Vanguard (750pts)",
        "Spearhead (1000pts)",
        "Matched Play (2000pts)",
        "Open Play",
        "Narrative",
    ],
    "Horus Heresy": [
        "Skirmish (1000pts)",
        "Battle (2500pts)",
        "Grand Battle (3000pts)",
        "Open Play",
    ],
    "Kill Team": [
        "Standard (100pts)",
        "Open Play",
    ],
    "Necromunda": [
        "Campaign Start (1000 Credits)",
        "Open Play",
    ],
    "Middle Earth Strategy Battle Game": [
        "Skirmish (250pts)",
        "Battle (500pts)",
        "Grand Battle (1000pts)",
        "Open Play",
    ],
    "Dungeons & Dragons": [
        "One-Shot Party",
        "Campaign Party",
        "Encounter",
        "Open Play",
    ],
    "Pathfinder": [
        "One-Shot Party",
        "Campaign Party",
        "Encounter",
        "Open Play",
    ],
    "Star Wars: Legion": [
        "Standard (800pts)",
        "Open Play",
    ],
    "Marvel Crisis Protocol": [
        "Standard (10 Threat)",
        "Open Play",
    ],
    "Bolt Action": [
        "Skirmish (500pts)",
        "Standard (1000pts)",
        "Open Play",
    ],
    "_default": [
        "Standard",
        "Open Play",
        "Narrative",
    ],
}

# Points extracted from format strings like "Strike Force (2000pts)" → 2000
def parse_points_limit(fmt: str) -> int:
    import re
    m = re.search(r"\((\d+)\s*pts?\)", fmt, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\((\d+)\s*Credits?\)", fmt, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\((\d+)\s*Threat\)", fmt, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0  # no limit


def get_roles_for_system(game_system: str) -> list[str]:
    return UNIT_ROLES.get(game_system, UNIT_ROLES["_default"])


def get_formats_for_system(game_system: str) -> list[str]:
    return ARMY_FORMATS.get(game_system, ARMY_FORMATS["_default"])


# ============================================================
# ARMY (the list itself)
# ============================================================

@dataclass
class Army:
    """An army list / roster."""
    name: str
    game_system: str
    faction: str
    format: str
    points_limit: int = 0       # 0 = no limit
    notes: Optional[str] = None
    id: Optional[int] = None

    def __post_init__(self):
        self._validate()

    def _validate(self):
        if not self.name or not self.name.strip():
            raise ValidationError("List name cannot be empty")
        if len(self.name.strip()) > 200:
            raise ValidationError("Name cannot exceed 200 characters")
        if not self.game_system or not self.game_system.strip():
            raise ValidationError("Game system cannot be empty")
        if not self.faction or not self.faction.strip():
            raise ValidationError("Faction / Warband cannot be empty")
        if not self.format or not self.format.strip():
            raise ValidationError("Format cannot be empty")
        if not isinstance(self.points_limit, int) or self.points_limit < 0:
            raise ValidationError("Points limit must be a non-negative integer")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name.strip(),
            "game_system": self.game_system.strip(),
            "faction": self.faction.strip(),
            "format": self.format.strip(),
            "points_limit": self.points_limit,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Army":
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            game_system=data.get("game_system", ""),
            faction=data.get("faction", ""),
            format=data.get("format", ""),
            points_limit=data.get("points_limit", 0),
            notes=data.get("notes"),
        )


# ============================================================
# ARMY UNIT (entry within a list)
# ============================================================

@dataclass
class ArmyUnit:
    """
    A single unit/model/character entry in an army list.

    Works for all game types:
      40K    — "Tactical Squad × 10, 150pts"
      Kill Team — "Gunner Operative × 1, 12pts"
      D&D   — "Mage character × 1, 0pts"
    """
    army_id: int
    unit_name: str
    unit_role: str
    points_cost: float   # cost per individual model
    quantity: int = 1
    wargear_notes: Optional[str] = None        # loadout / abilities / equipment
    model_id: Optional[int] = None              # link to model_tracker
    linked_paint_ids: list[int] = field(default_factory=list)  # direct paint links
    sort_order: int = 0
    id: Optional[int] = None

    def __post_init__(self):
        self._validate()

    def _validate(self):
        if not self.unit_name or not self.unit_name.strip():
            raise ValidationError("Unit name cannot be empty")
        if len(self.unit_name.strip()) > 200:
            raise ValidationError("Unit name cannot exceed 200 characters")
        if not self.unit_role or not self.unit_role.strip():
            raise ValidationError("Unit role cannot be empty")
        if not isinstance(self.points_cost, (int, float)) or self.points_cost < 0:
            raise ValidationError("Points cost must be a non-negative number")
        if not isinstance(self.quantity, int) or self.quantity < 1:
            raise ValidationError("Quantity must be a positive integer")
        if self.wargear_notes and len(self.wargear_notes) > 2000:
            raise ValidationError("Wargear/notes cannot exceed 2000 characters")

    @property
    def total_points(self) -> float:
        """Total cost for this unit entry: per-model cost × quantity."""
        return self.points_cost * self.quantity

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "army_id": self.army_id,
            "unit_name": self.unit_name.strip(),
            "unit_role": self.unit_role.strip(),
            "points_cost": self.points_cost,
            "quantity": self.quantity,
            "wargear_notes": self.wargear_notes,
            "model_id": self.model_id,
            "linked_paint_ids": self.linked_paint_ids,
            "sort_order": self.sort_order,
        }


# ============================================================
# FILTER
# ============================================================

@dataclass
class ArmyFilter:
    """Filter criteria for the My Lists view."""
    search_text: Optional[str] = None
    game_system: Optional[str] = None
    faction: Optional[str] = None
    sort_by: Optional[str] = None
    sort_desc: bool = False

    def matches(self, army: Army) -> bool:
        if self.game_system and self.game_system.lower() not in army.game_system.lower():
            return False
        if self.faction and self.faction.lower() not in army.faction.lower():
            return False
        if self.search_text:
            needle = self.search_text.lower()
            haystack = f"{army.name} {army.game_system} {army.faction} {army.format}".lower()
            if needle not in haystack:
                return False
        return True

    def is_empty(self) -> bool:
        return not any([self.game_system, self.faction, self.search_text])


# ============================================================
# STATISTICS
# ============================================================

@dataclass
class ArmyStatistics:
    total_armies: int
    total_units: int
    game_system_distribution: dict[str, int] = field(default_factory=dict)
    faction_distribution: dict[str, int] = field(default_factory=dict)
    average_points: float = 0.0
    largest_army_name: str = ""
    largest_army_points: int = 0
