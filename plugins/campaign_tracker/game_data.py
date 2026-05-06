"""
Game Data Loader

Lazy-loads and caches JSON data files from game_system_data/.
Provides fast in-memory search across spells, monsters, items, etc.
Large files (monsters ~28MB, items ~19MB) are loaded on first access
and then held in memory for the session.

All search methods return EVERY matching entry — no artificial limits.
Results are sorted alphabetically by name.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# Resolve relative to this file → project root → game_system_data/
_DATA_ROOT = Path(__file__).parent.parent.parent / "game_system_data"

# Known label → folder mappings (well-known systems get friendly display names)
_KNOWN_SYSTEMS: dict[str, str] = {
    "D&D 5e":              "dungeons_and_dragons",
    "Pathfinder 2e":       "pathfinder_2e",
    "Warhammer 40k":       "warhammer_40k",
    "Age of Sigmar":       "age_of_sigmar",
    "Community":           "community",
}

# Reverse: folder slug → display label
_FOLDER_TO_LABEL: dict[str, str] = {v: k for k, v in _KNOWN_SYSTEMS.items()}

# Keep as a public alias so existing imports of SYSTEMS still work
SYSTEMS = _KNOWN_SYSTEMS

# Map category name → filename (D&D-specific categories)
_CAT_FILE = {
    "Spells":      "spells.json",
    "Monsters":    "monsters.json",
    "Items":       "items.json",
    "Classes":     "classes.json",
    "Species":     "species.json",
    "Backgrounds": "backgrounds.json",
}


def _folder_name_to_label(folder: str) -> str:
    """Convert a raw folder slug to a readable display name."""
    return folder.replace("_", " ").title()


class GameDataLoader:
    """Class-level cache — shared across all instances."""

    _cache: dict[str, list[dict]] = {}

    # ── Internal ──────────────────────────────────────────────────────────────

    @classmethod
    def _load(cls, system_folder: str, filename: str) -> list[dict]:
        key = f"{system_folder}/{filename}"
        if key not in cls._cache:
            path = _DATA_ROOT / system_folder / filename
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    cls._cache[key] = json.load(f)
            else:
                cls._cache[key] = []
        return cls._cache[key]

    @classmethod
    def available_systems(cls) -> list[str]:
        """
        Return a display label for every folder that exists under game_system_data/.

        Known folders (e.g. dungeons_and_dragons) are mapped to their friendly
        labels (e.g. "D&D 5e").  Unknown folders are title-cased from the slug.
        """
        if not _DATA_ROOT.is_dir():
            return []
        labels = []
        for entry in sorted(_DATA_ROOT.iterdir()):
            if entry.is_dir():
                label = _FOLDER_TO_LABEL.get(entry.name) or _folder_name_to_label(entry.name)
                labels.append(label)
        return labels

    @classmethod
    def _folder(cls, system_label: str) -> str:
        """Resolve a display label to its on-disk folder name."""
        # 1. Check known mapping
        if system_label in _KNOWN_SYSTEMS:
            return _KNOWN_SYSTEMS[system_label]
        # 2. Check if the label itself is a valid folder name
        if (_DATA_ROOT / system_label).is_dir():
            return system_label
        # 3. Check reverse map (in case a folder slug was passed directly)
        if system_label in _FOLDER_TO_LABEL:
            return system_label
        # 4. Slugify and try
        slug = re.sub(r"[^a-z0-9]+", "_", system_label.strip().lower()).strip("_")
        if (_DATA_ROOT / slug).is_dir():
            return slug
        # 5. Fall back to community (generic), not D&D
        return "community"

    @classmethod
    def list_data_files(cls, system_label: str) -> list[str]:
        """
        Return filenames of all JSON files available for a given system.
        These are the files that can be browsed generically via search_file_entries().
        """
        folder = cls._folder(system_label)
        dir_path = _DATA_ROOT / folder
        if not dir_path.is_dir():
            return []
        return sorted(p.name for p in dir_path.glob("*.json"))

    # Alternative key names used by various game data formats
    _NAME_KEYS  = ("name", "unitname", "title", "item_name", "spell_name", "entry_name", "label")
    _FACTION_KEYS = ("faction", "factionname", "type", "category", "class", "role")
    _DESC_KEYS  = ("description", "flavortext", "flavor", "text", "effect", "summary", "details")
    _KW_KEYS    = ("keywords", "tags", "traits", "subtypes")

    @classmethod
    def _normalise_entry(cls, entry: dict) -> dict:
        """
        Return a copy of entry with canonical keys populated where possible.
        Adds 'name', 'faction', 'description', 'keywords' from whatever
        alternative field names the source data uses.
        """
        result = dict(entry)
        if "name" not in result or not result["name"]:
            for k in cls._NAME_KEYS:
                if k != "name" and entry.get(k):
                    result["name"] = entry[k]
                    break
        if "faction" not in result:
            for k in cls._FACTION_KEYS:
                if k != "faction" and entry.get(k):
                    result["faction"] = entry[k]
                    break
        if "description" not in result:
            for k in cls._DESC_KEYS:
                if entry.get(k):
                    result["description"] = entry[k]
                    break
        if "keywords" not in result:
            for k in cls._KW_KEYS:
                if entry.get(k):
                    result["keywords"] = entry[k]
                    break
        return result

    @classmethod
    def search_file_entries(
        cls,
        system_label: str,
        filename: str,
        query: str = "",
    ) -> list[dict]:
        """
        Generic entry search across any JSON file.

        The JSON may be:
          - A list of dicts (each item is an entry)
          - A dict whose values are lists (each nested list is flattened)
          - A dict whose values are plain values (treat the whole dict as one entry)

        Each entry is normalised so it always has at least a 'name' key.
        """
        folder = cls._folder(system_label)
        raw = cls._load(folder, filename)

        # Flatten dict-of-lists into a single list
        if isinstance(raw, dict):
            entries: list[dict] = []
            for key, val in raw.items():
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            if "name" not in item:
                                item = {"name": key, **item}
                            entries.append(item)
                        else:
                            entries.append({"name": str(item), "source": key})
                else:
                    entries.append({"name": key, "value": str(val)})
        elif isinstance(raw, list):
            entries = [e if isinstance(e, dict) else {"name": str(e)} for e in raw]
        else:
            entries = []

        # Normalise alternative key names
        entries = [cls._normalise_entry(e) for e in entries]

        # Apply query filter
        q = query.strip().lower()
        if q:
            entries = [
                e for e in entries
                if q in str(e.get("name", "")).lower()
                or q in str(e.get("description", "")).lower()
                or q in str(e.get("faction", "")).lower()
                or q in str(e.get("keywords", "")).lower()
            ]

        return sorted(entries, key=lambda e: str(e.get("name", "")).lower())

    @classmethod
    def book_names(cls, category: str, system: str = "D&D 5e") -> list[str]:
        """Return sorted list of all source book titles for a given category."""
        filename = _CAT_FILE.get(category)
        if not filename:
            return []
        data = cls._load(cls._folder(system), filename)
        seen: set[str] = set()
        for entry in data:
            b = entry.get("book", "")
            if b:
                seen.add(b)
        return sorted(seen, key=str.lower)

    # ── Spells ────────────────────────────────────────────────────────────────

    # Canonical D&D spell schools — sub-school variants are normalised to these.
    _STANDARD_SCHOOLS = [
        "Abjuration", "Conjuration", "Divination", "Enchantment",
        "Evocation", "Illusion", "Necromancy", "Transmutation",
    ]

    @classmethod
    def search_spells(cls, query: str, system: str = "D&D 5e",
                      level: Optional[int] = None,
                      school: Optional[str] = None,
                      book: Optional[str] = None) -> list[dict]:
        """Return all matching spells, sorted alphabetically."""
        data = cls._load(cls._folder(system), "spells.json")
        q = query.lower().strip() if query else ""

        results = []
        for s in data:
            if q and q not in s.get("name", "").lower():
                continue
            props = s.get("properties", {})
            if level is not None and str(props.get("Level", "")) != str(level):
                continue
            if school:
                raw_school = (props.get("School", "") or "").strip().lower()
                school_lc = school.lower()
                # Match exact or sub-school variant (e.g. "evocation (angelic)")
                if not (raw_school == school_lc or raw_school.startswith(school_lc)):
                    continue
            if book and s.get("book", "") != book:
                continue
            results.append(s)

        return sorted(results, key=lambda x: x.get("name", "").lower())

    @classmethod
    def get_spell(cls, name: str, system: str = "D&D 5e") -> Optional[dict]:
        data = cls._load(cls._folder(system), "spells.json")
        return next((s for s in data if s.get("name") == name), None)

    @classmethod
    def spell_schools(cls, system: str = "D&D 5e") -> list[str]:
        """Return the 8 canonical spell schools that appear in the data."""
        data = cls._load(cls._folder(system), "spells.json")
        present: set[str] = set()
        for s in data:
            sc = (s.get("properties", {}).get("School", "") or "").strip().lower()
            for std in cls._STANDARD_SCHOOLS:
                if sc == std.lower() or sc.startswith(std.lower()):
                    present.add(std)
                    break
        return [sc for sc in cls._STANDARD_SCHOOLS if sc in present]

    # ── Monsters ──────────────────────────────────────────────────────────────

    @classmethod
    def search_monsters(cls, query: str, system: str = "D&D 5e",
                        cr: Optional[str] = None,
                        book: Optional[str] = None) -> list[dict]:
        """Return all matching monsters, sorted alphabetically."""
        data = cls._load(cls._folder(system), "monsters.json")
        q = query.lower().strip() if query else ""

        results = []
        for m in data:
            if q and q not in m.get("name", "").lower():
                continue
            if cr is not None:
                props = m.get("properties", {})
                if str(props.get("Challenge Rating", "")) != str(cr):
                    continue
            if book and m.get("book", "") != book:
                continue
            results.append(m)

        return sorted(results, key=lambda x: x.get("name", "").lower())

    @classmethod
    def get_monster(cls, name: str, system: str = "D&D 5e") -> Optional[dict]:
        data = cls._load(cls._folder(system), "monsters.json")
        return next((m for m in data if m.get("name") == name), None)

    @classmethod
    def challenge_ratings(cls, system: str = "D&D 5e") -> list[str]:
        data = cls._load(cls._folder(system), "monsters.json")
        seen: set[str] = set()
        for m in data:
            cr = m.get("properties", {}).get("Challenge Rating", "")
            if cr is not None and cr != "":
                seen.add(str(cr))

        def _cr_sort(cr: str) -> float:
            try:
                if "/" in cr:
                    parts = cr.split("/")
                    return int(parts[0]) / int(parts[1])
                return float(cr)
            except Exception:
                return 999.0

        return sorted(seen, key=_cr_sort)

    # ── Items ─────────────────────────────────────────────────────────────────

    @classmethod
    def search_items(cls, query: str, system: str = "D&D 5e",
                     item_type: Optional[str] = None,
                     rarity: Optional[str] = None,
                     book: Optional[str] = None) -> list[dict]:
        """Return all matching items, sorted alphabetically."""
        data = cls._load(cls._folder(system), "items.json")
        q = query.lower().strip() if query else ""

        results = []
        for item in data:
            if q and q not in item.get("name", "").lower():
                continue
            props = item.get("properties", {})
            if item_type and item_type.lower() not in props.get("Item Type", "").lower():
                continue
            if rarity:
                raw_rarity = (props.get("Item Rarity", "") or "").strip().lower()
                rarity_lc = rarity.lower()
                # "rare" matches "rare (requires attunement)" but NOT "very rare"
                if not (raw_rarity == rarity_lc or raw_rarity.startswith(rarity_lc + " ")):
                    continue
            if book and item.get("book", "") != book:
                continue
            results.append(item)

        return sorted(results, key=lambda x: x.get("name", "").lower())

    @classmethod
    def item_types(cls, system: str = "D&D 5e") -> list[str]:
        data = cls._load(cls._folder(system), "items.json")
        seen: set[str] = set()
        for item in data:
            t = item.get("properties", {}).get("Item Type", "")
            if t:
                seen.add(t)
        return sorted(seen)

    # Standard rarities in tier order — used as the filter list in the UI.
    _STANDARD_RARITIES = ["Common", "Uncommon", "Rare", "Very Rare", "Legendary", "Artifact"]

    @classmethod
    def item_rarities(cls, system: str = "D&D 5e") -> list[str]:
        """Return the standard D&D rarity tiers that exist in the data."""
        data = cls._load(cls._folder(system), "items.json")
        present: set[str] = set()
        for item in data:
            raw = (item.get("properties", {}).get("Item Rarity", "") or "").strip().lower()
            for tier in cls._STANDARD_RARITIES:
                if raw == tier.lower() or raw.startswith(tier.lower()):
                    present.add(tier)
        return [r for r in cls._STANDARD_RARITIES if r in present]

    # ── Classes / Species / Backgrounds ───────────────────────────────────────

    @classmethod
    def get_classes(cls, system: str = "D&D 5e") -> list[dict]:
        return cls._load(cls._folder(system), "classes.json")

    @classmethod
    def get_species(cls, system: str = "D&D 5e") -> list[dict]:
        return cls._load(cls._folder(system), "species.json")

    @classmethod
    def get_backgrounds(cls, system: str = "D&D 5e") -> list[dict]:
        return cls._load(cls._folder(system), "backgrounds.json")

    @classmethod
    def _search_generic(cls, data: list[dict], query: str,
                         book: Optional[str] = None) -> list[dict]:
        q = query.lower().strip() if query else ""
        results = [
            item for item in data
            if (not q or q in item.get("name", "").lower())
            and (not book or item.get("book", "") == book)
        ]
        return sorted(results, key=lambda x: x.get("name", "").lower())

    @classmethod
    def search_classes(cls, query: str, system: str = "D&D 5e",
                       book: Optional[str] = None) -> list[dict]:
        return cls._search_generic(cls.get_classes(system), query, book)

    @classmethod
    def search_species(cls, query: str, system: str = "D&D 5e",
                       book: Optional[str] = None) -> list[dict]:
        return cls._search_generic(cls.get_species(system), query, book)

    @classmethod
    def search_backgrounds(cls, query: str, system: str = "D&D 5e",
                           book: Optional[str] = None) -> list[dict]:
        return cls._search_generic(cls.get_backgrounds(system), query, book)
