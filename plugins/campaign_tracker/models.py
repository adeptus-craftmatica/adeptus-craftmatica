"""
Campaign Tracker Models

Data classes for the campaign tracker plugin.
All game systems supported: D&D, Pathfinder, Warhammer 40K, AOS, and more.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


class ValidationError(Exception):
    pass


# ── Presets ────────────────────────────────────────────────────────────────────

GAME_SYSTEMS = [
    "Dungeons & Dragons 5e",
    "Dungeons & Dragons 2024",
    "Pathfinder 2e",
    "Call of Cthulhu",
    "Warhammer 40,000",
    "Age of Sigmar",
    "Warhammer: The Old World",
    "Horus Heresy",
    "Kill Team",
    "Necromunda",
    "Star Wars: Legion",
    "Bolt Action",
    "Infinity",
    "Marvel Crisis Protocol",
    "Other",
]

CAMPAIGN_STATUSES = ["Active", "Paused", "Complete", "Archived"]

CHARACTER_ROLES = [
    "Player Character",
    "NPC",
    "Monster",
    "Villain",
    "Companion",
    "Boss",
    "Other",
]

CHARACTER_ROLE_COLORS = {
    "Player Character": "#4a9eda",
    "NPC":             "#909090",
    "Monster":         "#e05555",
    "Villain":         "#a855a5",
    "Companion":       "#3dba6e",
    "Boss":            "#e07820",
    "Other":           "#686868",
}

CHARACTER_STATUSES = ["Active", "Dead", "Retired", "Captured", "Unknown"]

BATTLE_OUTCOMES = ["Victory", "Defeat", "Draw", "Partial Victory", "In Progress"]

OUTCOME_COLORS = {
    "Victory":         "#3dba6e",
    "Defeat":          "#e05555",
    "Draw":            "#f0a020",
    "Partial Victory": "#4a9eda",
    "In Progress":     "#808080",
}

ASSET_TYPES = ["Map", "Token", "Music", "Document", "Image", "Other"]

PLAYER_ROLES = ["Player", "Dungeon Master", "Game Master", "Narrator", "Spectator"]

# Stat block presets
STAT_STYLES = ["D&D 5e", "Wargame: 40K", "Wargame: AOS", "Freeform"]

DND_STATS      = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
WARGAME_40K    = ["M", "T", "W", "SV", "LD", "OC"]
WARGAME_AOS    = ["Move", "Health", "Save", "Control"]


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Campaign:
    name: str
    game_system: str
    status: str = "Active"
    description: Optional[str] = None
    notes: Optional[str] = None
    start_date: Optional[str] = None
    cover_image_path: Optional[str] = None
    assets_folder: Optional[str] = None
    id: Optional[int] = None

    def __post_init__(self):
        self._validate()

    def _validate(self):
        if not self.name or not self.name.strip():
            raise ValidationError("Campaign name cannot be empty")
        if self.status not in CAMPAIGN_STATUSES:
            raise ValidationError(f"Invalid status: {self.status}")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "game_system": self.game_system,
            "status": self.status, "description": self.description, "notes": self.notes,
            "start_date": self.start_date, "cover_image_path": self.cover_image_path,
            "assets_folder": self.assets_folder,
        }


@dataclass
class CampaignPlayer:
    campaign_id: int
    player_name: str
    role: str = "Player"
    notes: Optional[str] = None
    id: Optional[int] = None

    def __post_init__(self):
        if not self.player_name or not self.player_name.strip():
            raise ValidationError("Player name cannot be empty")
        if self.role not in PLAYER_ROLES:
            self.role = "Player"


@dataclass
class Character:
    campaign_id: int
    name: str
    character_role: str = "Player Character"
    status: str = "Active"
    player_id: Optional[int] = None
    model_id: Optional[int] = None
    character_class: Optional[str] = None
    race: Optional[str] = None
    level: int = 1
    hit_points: int = 0
    max_hit_points: int = 0
    armor_class: int = 0
    stat_style: str = "D&D 5e"
    stats_json: Optional[str] = None
    background: Optional[str] = None
    traits: Optional[str] = None
    equipment_notes: Optional[str] = None
    notes: Optional[str] = None
    primary_image_path: Optional[str] = None
    # Extended sheet fields
    experience_points: int = 0
    death_saves_success: int = 0   # bitmask: bit 0-2
    death_saves_failure: int = 0   # bitmask: bit 0-2
    currency_json: Optional[str] = None   # {cp, sp, ep, gp, pp}
    spell_slots_json: Optional[str] = None  # {1:{max,used}, 2:{max,used}, ...}
    id: Optional[int] = None

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValidationError("Character name cannot be empty")
        if self.character_role not in CHARACTER_ROLES:
            self.character_role = "Player Character"
        if self.status not in CHARACTER_STATUSES:
            self.status = "Active"

    @property
    def stats(self) -> dict:
        if self.stats_json:
            try:
                return json.loads(self.stats_json)
            except Exception:
                pass
        return {}

    @stats.setter
    def stats(self, value: dict):
        self.stats_json = json.dumps(value) if value else None

    @property
    def currency(self) -> dict:
        if self.currency_json:
            try:
                return json.loads(self.currency_json)
            except Exception:
                pass
        return {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}

    @currency.setter
    def currency(self, value: dict):
        self.currency_json = json.dumps(value) if value else None

    @property
    def spell_slots(self) -> dict:
        if self.spell_slots_json:
            try:
                return json.loads(self.spell_slots_json)
            except Exception:
                pass
        return {}

    @spell_slots.setter
    def spell_slots(self, value: dict):
        self.spell_slots_json = json.dumps(value) if value else None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "campaign_id": self.campaign_id, "name": self.name,
            "character_role": self.character_role, "status": self.status,
            "player_id": self.player_id, "model_id": self.model_id,
            "character_class": self.character_class, "race": self.race, "level": self.level,
            "hit_points": self.hit_points, "max_hit_points": self.max_hit_points,
            "armor_class": self.armor_class, "stat_style": self.stat_style,
            "stats_json": self.stats_json, "background": self.background,
            "traits": self.traits, "equipment_notes": self.equipment_notes,
            "notes": self.notes, "primary_image_path": self.primary_image_path,
            "experience_points": self.experience_points,
            "death_saves_success": self.death_saves_success,
            "death_saves_failure": self.death_saves_failure,
            "currency_json": self.currency_json,
            "spell_slots_json": self.spell_slots_json,
        }


@dataclass
class CharacterImage:
    character_id: int
    image_path: str
    is_primary: bool = False
    zoom: float = 1.0
    focal_x: float = 0.5
    focal_y: float = 0.5
    id: Optional[int] = None


@dataclass
class CharacterSpell:
    character_id: int
    spell_name: str
    spell_level: int = 0           # 0 = cantrip
    is_prepared: bool = False
    is_ritual: bool = False
    notes: Optional[str] = None
    source: Optional[str] = None   # e.g. "Wizard", "Magic Item"
    id: Optional[int] = None


@dataclass
class InventoryItem:
    character_id: int
    name: str
    quantity: int = 1
    weight: float = 0.0
    value_gp: float = 0.0
    equipped: bool = False
    description: Optional[str] = None
    item_type: Optional[str] = None   # Weapon, Armor, Gear, Magic Item…
    id: Optional[int] = None


@dataclass
class Encounter:
    campaign_id: int
    name: str
    description: Optional[str] = None
    difficulty: Optional[str] = None   # Easy / Medium / Hard / Deadly
    id: Optional[int] = None


@dataclass
class EncounterMonster:
    encounter_id: int
    monster_name: str
    count: int = 1
    hp_override: Optional[int] = None   # custom HP; None = use stat block default
    notes: Optional[str] = None
    cr: Optional[str] = None
    id: Optional[int] = None


@dataclass
class Battle:
    campaign_id: int
    title: str
    session_number: int = 1
    date_played: Optional[str] = None
    location_name: Optional[str] = None
    scenario_name: Optional[str] = None
    scenario_description: Optional[str] = None
    outcome: str = "In Progress"
    scoring_notes: Optional[str] = None
    chronicle_text: Optional[str] = None
    primary_image_path: Optional[str] = None
    id: Optional[int] = None

    def __post_init__(self):
        if not self.title or not self.title.strip():
            raise ValidationError("Battle/Session title cannot be empty")
        if self.outcome not in BATTLE_OUTCOMES:
            self.outcome = "In Progress"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "campaign_id": self.campaign_id, "title": self.title,
            "session_number": self.session_number, "date_played": self.date_played,
            "location_name": self.location_name, "scenario_name": self.scenario_name,
            "scenario_description": self.scenario_description, "outcome": self.outcome,
            "scoring_notes": self.scoring_notes, "chronicle_text": self.chronicle_text,
            "primary_image_path": self.primary_image_path,
        }


@dataclass
class BattleParticipant:
    battle_id: int
    player_id: int
    side: str = ""
    army_id: Optional[int] = None
    score: int = 0
    result: str = ""
    notes: Optional[str] = None
    id: Optional[int] = None


@dataclass
class BattleImage:
    battle_id: int
    image_path: str
    is_primary: bool = False
    zoom: float = 1.0
    focal_x: float = 0.5
    focal_y: float = 0.5
    id: Optional[int] = None


@dataclass
class CampaignImage:
    campaign_id: int
    image_path: str
    caption: str = ""
    is_primary: bool = False
    zoom: float = 1.0
    focal_x: float = 0.5
    focal_y: float = 0.5
    id: Optional[int] = None


@dataclass
class JournalEntry:
    campaign_id: int
    title: str
    content: str = ""
    battle_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    id: Optional[int] = None

    def __post_init__(self):
        if not self.title or not self.title.strip():
            raise ValidationError("Journal entry title cannot be empty")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "campaign_id": self.campaign_id, "title": self.title,
            "content": self.content, "battle_id": self.battle_id,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


@dataclass
class CampaignAsset:
    campaign_id: int
    name: str
    file_path: str
    asset_type: str = "Other"
    notes: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "campaign_id": self.campaign_id, "name": self.name,
            "file_path": self.file_path, "asset_type": self.asset_type, "notes": self.notes,
        }


@dataclass
class DiceRoll:
    expression: str
    result: int
    detail: str
    timestamp: Optional[str] = None
    id: Optional[int] = None


@dataclass
class SavedExpression:
    name: str
    expression: str
    id: Optional[int] = None


@dataclass
class CampaignStatistics:
    total_campaigns: int = 0
    active_campaigns: int = 0
    total_battles: int = 0
    total_characters: int = 0
    total_players: int = 0
    victories: int = 0
    defeats: int = 0
    draws: int = 0
    game_system_distribution: dict = field(default_factory=dict)
