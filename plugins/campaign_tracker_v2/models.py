"""
Campaign Tracker v2 — Models and system presets.
Core entity models delegate to v1; this file adds v2-specific types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
#  Game System Presets
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class GameSystem:
    id:                 str
    name:               str
    icon:               str
    accent:             str           # hex colour for badges/accents
    compendium_cats:    list[str]
    character_template: str           # drives character sheet layout
    encounter_system:   str           # "cr_xp" | "xp_budget" | "points" | "none"
    dice_pool:          list[str]
    session_label:      str           # "Session" | "Battle" | "Mission"
    character_label:    str           # "Character" | "Unit" | "Operative"
    npc_label:          str           # "NPC" | "Named Character" | "Commander"
    enemy_label:        str           # "Monster" | "Enemy Unit" | "Operative"


SYSTEMS: dict[str, GameSystem] = {
    "dnd5e": GameSystem(
        id="dnd5e", name="Dungeons & Dragons 5e", icon="⚔",
        accent="#c0392b",
        compendium_cats=["Spells", "Items", "Monsters", "Locations", "NPCs",
                         "Lore", "Factions", "Rules"],
        character_template="dnd5e",
        encounter_system="cr_xp",
        dice_pool=["d4", "d6", "d8", "d10", "d12", "d20", "d100"],
        session_label="Session", character_label="Character",
        npc_label="NPC", enemy_label="Monster",
    ),
    "pathfinder2e": GameSystem(
        id="pathfinder2e", name="Pathfinder 2e", icon="🔮",
        accent="#8B4513",
        compendium_cats=["Spells", "Feats", "Items", "Monsters", "Rules",
                         "Locations", "Ancestry", "Classes"],
        character_template="pathfinder2e",
        encounter_system="xp_budget",
        dice_pool=["d4", "d6", "d8", "d10", "d12", "d20"],
        session_label="Session", character_label="Character",
        npc_label="NPC", enemy_label="Creature",
    ),
    "wh40k": GameSystem(
        id="wh40k", name="Warhammer 40,000", icon="💀",
        accent="#8B0000",
        compendium_cats=["Units", "Stratagems", "Weapons", "Detachments",
                         "Missions", "Terrain", "Rules"],
        character_template="wh40k",
        encounter_system="points",
        dice_pool=["d3", "d6"],
        session_label="Battle", character_label="Unit",
        npc_label="Named Character", enemy_label="Enemy Unit",
    ),
    "aos": GameSystem(
        id="aos", name="Age of Sigmar", icon="⚡",
        accent="#1a237e",
        compendium_cats=["Warscrolls", "Spells", "Prayers", "Terrain",
                         "Missions", "Rules", "Factions"],
        character_template="aos",
        encounter_system="points",
        dice_pool=["d3", "d6"],
        session_label="Battle", character_label="Unit",
        npc_label="Hero", enemy_label="Enemy Unit",
    ),
    "necromunda": GameSystem(
        id="necromunda", name="Necromunda", icon="🏭",
        accent="#4e342e",
        compendium_cats=["Gangers", "Weapons", "Equipment", "Skills",
                         "Territories", "Trading Post", "Rules"],
        character_template="necromunda",
        encounter_system="credits",
        dice_pool=["d3", "d6", "d8", "d10", "d12"],
        session_label="Mission", character_label="Ganger",
        npc_label="Bounty Hunter", enemy_label="Enemy Ganger",
    ),
    "killteam": GameSystem(
        id="killteam", name="Kill Team", icon="🎯",
        accent="#006064",
        compendium_cats=["Operatives", "Equipment", "Tac-Ops", "Ploys",
                         "Terrain", "Missions", "Rules"],
        character_template="killteam",
        encounter_system="points",
        dice_pool=["d3", "d6"],
        session_label="Mission", character_label="Operative",
        npc_label="Operative", enemy_label="Enemy Operative",
    ),
    "custom": GameSystem(
        id="custom", name="Custom / Other", icon="🎲",
        accent="#424242",
        compendium_cats=["Characters", "Items", "Locations", "Rules",
                         "Lore", "Factions", "Notes"],
        character_template="custom",
        encounter_system="none",
        dice_pool=["d4", "d6", "d8", "d10", "d12", "d20", "d100"],
        session_label="Session", character_label="Character",
        npc_label="NPC", enemy_label="Enemy",
    ),
}

SYSTEM_LIST = list(SYSTEMS.values())


# ── Character sheet templates (which fields are shown) ────────────────────

CHAR_TEMPLATES: dict[str, dict] = {
    "dnd5e": {
        "core_stats": [
            ("STR", "str"), ("DEX", "dex"), ("CON", "con"),
            ("INT", "int"), ("WIS", "wis"), ("CHA", "cha"),
        ],
        "combat_fields": [
            ("HP", "hp"), ("Max HP", "max_hp"), ("AC", "ac"),
            ("Initiative", "initiative"), ("Speed", "speed"), ("Prof Bonus", "prof_bonus"),
        ],
        "has_class_race": True,
        "has_level": True,
        "has_spells": True,
        "has_inventory": True,
        "has_cr": False,
        "extra_fields": [
            ("Background", "background"), ("Alignment", "alignment"),
            ("Passive Perception", "passive_perception"),
        ],
    },
    "pathfinder2e": {
        "core_stats": [
            ("STR", "str"), ("DEX", "dex"), ("CON", "con"),
            ("INT", "int"), ("WIS", "wis"), ("CHA", "cha"),
        ],
        "combat_fields": [
            ("HP", "hp"), ("Max HP", "max_hp"), ("AC", "ac"),
            ("Fortitude", "fort"), ("Reflex", "ref"), ("Will", "will"),
            ("Speed", "speed"), ("Perception", "perception"),
        ],
        "has_class_race": True,
        "has_level": True,
        "has_spells": True,
        "has_inventory": True,
        "has_cr": False,
        "extra_fields": [
            ("Ancestry", "ancestry"), ("Heritage", "heritage"),
            ("Size", "size"),
        ],
    },
    "wh40k": {
        "core_stats": [
            ("M", "move"), ("T", "toughness"), ("Sv", "save"),
            ("W", "wounds"), ("Ld", "leadership"), ("OC", "oc"),
        ],
        "combat_fields": [
            ("Points", "points"), ("Inv Save", "inv_save"),
            ("Feel No Pain", "fnp"),
        ],
        "has_class_race": False,
        "has_level": False,
        "has_spells": False,
        "has_inventory": False,
        "has_cr": False,
        "extra_fields": [
            ("Faction Keywords", "faction"), ("Keywords", "keywords"),
            ("Datasheet", "datasheet_name"),
        ],
    },
    "aos": {
        "core_stats": [
            ("Move", "move"), ("Health", "wounds"), ("Save", "save"),
            ("Ward", "ward"), ("Control", "control"),
        ],
        "combat_fields": [
            ("Points", "points"), ("Banishment", "banishment"),
        ],
        "has_class_race": False,
        "has_level": False,
        "has_spells": True,
        "has_inventory": False,
        "has_cr": False,
        "extra_fields": [
            ("Grand Alliance", "grand_alliance"),
            ("Faction", "faction"), ("Keywords", "keywords"),
        ],
    },
    "necromunda": {
        "core_stats": [
            ("M", "move"), ("WS", "ws"), ("BS", "bs"),
            ("S", "strength"), ("T", "toughness"), ("W", "wounds"),
            ("I", "initiative"), ("A", "attacks"), ("Ld", "leadership"),
            ("Cl", "cool"), ("Wil", "will"), ("Int", "intelligence"),
        ],
        "combat_fields": [
            ("Credits", "credits"), ("XP", "xp"), ("Kills", "kills"),
        ],
        "has_class_race": False,
        "has_level": True,
        "has_spells": False,
        "has_inventory": True,
        "has_cr": False,
        "extra_fields": [
            ("Gang Role", "gang_role"), ("Status", "ganger_status"),
            ("Advance Count", "advance_count"),
        ],
    },
    "killteam": {
        "core_stats": [
            ("M", "move"), ("APL", "apl"), ("GA", "ga"),
            ("DF", "df"), ("SV", "sv"), ("W", "wounds"),
        ],
        "combat_fields": [
            ("Equipment Points", "eq_pts"),
        ],
        "has_class_race": False,
        "has_level": False,
        "has_spells": False,
        "has_inventory": True,
        "has_cr": False,
        "extra_fields": [
            ("Faction", "faction"), ("Keywords", "keywords"),
            ("Unique Actions", "unique_actions"),
        ],
    },
    "custom": {
        "core_stats": [],
        "combat_fields": [],
        "has_class_race": True,
        "has_level": True,
        "has_spells": False,
        "has_inventory": True,
        "has_cr": False,
        "extra_fields": [],
    },
}


# ══════════════════════════════════════════════════════════════════════════════
#  V2-specific data models
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CompendiumEntry:
    id:          int
    campaign_id: int
    category:    str
    title:       str
    content:     str
    tags:        str = ""
    source:      str = ""
    created_at:  str = ""
    updated_at:  str = ""


# ── Gallery stages ────────────────────────────────────────────────────────────

class CampaignGalleryStage:
    MAP       = "map"
    TOKEN     = "token"
    ART       = "art"
    REFERENCE = "reference"
    SESSION   = "session"
    CHARACTER = "character"
    NONE      = ""

    ALL = [MAP, TOKEN, ART, REFERENCE, SESSION, CHARACTER]
    LABELS = {
        MAP: "Map", TOKEN: "Token", ART: "Art",
        REFERENCE: "Reference", SESSION: "Session", CHARACTER: "Character Art",
        NONE: "—",
    }
    COLORS = {
        MAP: "#2e7d32",   TOKEN: "#1565c0",    ART: "#6a1b9a",
        REFERENCE: "#e65100", SESSION: "#00695c", CHARACTER: "#ad1457",
        NONE: "#606060",
    }


# ── D&D 5e XP tables for encounter difficulty ─────────────────────────────────

# XP thresholds per character level [Easy, Medium, Hard, Deadly]
DND5E_XP_THRESHOLDS = {
    1: (25, 50, 75, 100),       2: (50, 100, 150, 200),
    3: (75, 150, 225, 400),     4: (125, 250, 375, 500),
    5: (250, 500, 750, 1100),   6: (300, 600, 900, 1400),
    7: (350, 750, 1100, 1700),  8: (450, 900, 1400, 2100),
    9: (550, 1100, 1600, 2400), 10: (600, 1200, 1900, 2800),
    11: (800, 1600, 2400, 3600), 12: (1000, 2000, 3000, 4500),
    13: (1100, 2200, 3400, 5100), 14: (1250, 2500, 3800, 5700),
    15: (1400, 2800, 4300, 6400), 16: (1600, 3200, 4800, 7200),
    17: (2000, 3900, 5900, 8800), 18: (2100, 4200, 6300, 9500),
    19: (2400, 4900, 7300, 10900), 20: (2800, 5700, 8500, 12700),
}

# CR → XP
DND5E_CR_XP = {
    "0": 10, "1/8": 25, "1/4": 50, "1/2": 100,
    "1": 200, "2": 450, "3": 700, "4": 1100, "5": 1800,
    "6": 2300, "7": 2900, "8": 3900, "9": 5000, "10": 5900,
    "11": 7200, "12": 8400, "13": 10000, "14": 11500, "15": 13000,
    "16": 15000, "17": 18000, "18": 20000, "19": 22000, "20": 25000,
    "21": 33000, "22": 41000, "23": 50000, "24": 62000, "25": 75000,
    "26": 90000, "27": 105000, "28": 120000, "29": 135000, "30": 155000,
}

# Monster count multipliers
DND5E_MULT = [(1, 1.0), (2, 1.5), (6, 2.0), (10, 2.5), (14, 3.0)]

# Pathfinder 2e XP budget per difficulty
PF2E_XP_BUDGET = {
    "Trivial": 40, "Low": 60, "Moderate": 80, "Severe": 120, "Extreme": 160
}
# Simple creature XP by level delta (creature_level - party_level)
PF2E_CREATURE_XP = {
    -4: 10, -3: 15, -2: 20, -1: 30, 0: 40,
    1: 60, 2: 80, 3: 120, 4: 160,
}
