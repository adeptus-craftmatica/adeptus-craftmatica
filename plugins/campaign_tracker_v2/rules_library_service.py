"""
Campaign Tracker v2 — Rules Library Service.

Business logic and game-data import for the Rules Library feature.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)


def _game_data_path(filename: str) -> Path:
    """Resolve path to a game_system_data file, works in frozen bundles."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent.parent.parent  # project root
    return base / "game_system_data" / filename


# Exclude non-unit JSON files in the age_of_sigmar directory
_AOS_EXCLUDE = {"armies.test.json", "armies_schema.json", "unit_schema.json",
                "package.json", "package-lock.json"}


class RulesLibraryService:

    def __init__(self, repo):
        self._repo = repo

    # ── Import ────────────────────────────────────────────────────────────────

    def import_wh40k(
        self,
        faction_filter: str | None = None,
        progress_cb: Callable | None = None,
    ) -> dict:
        """Import all (or a single faction's) units from wh40k_10th.json."""
        path = _game_data_path("community/wh40k_10th.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                units = json.load(f)
        except Exception as e:
            log.error(f"[RulesLibSvc] wh40k load error: {e}")
            return {"imported": 0, "skipped": 0, "factions": [], "error": str(e)}

        source = "Warhammer 40K 10th Edition"

        # Delete existing rows for this source (or faction) so reimport is clean
        if faction_filter:
            # Delete only rows matching this faction+source
            rows = self._repo.get_entities(
                system_id="wh40k", faction=faction_filter, limit=10000
            )
            for r in rows:
                if r["source"] == source:
                    self._repo.delete_entity(r["id"])
        else:
            self._repo.delete_by_source(source)

        total = len(units)
        to_insert: list[dict] = []
        skipped = 0
        factions_seen: set[str] = set()

        for i, unit in enumerate(units):
            faction = unit.get("factionname", "Unknown")
            name = unit.get("unitname", unit.get("name", ""))
            if not name:
                skipped += 1
                continue
            if faction_filter and faction != faction_filter:
                skipped += 1
                continue

            factions_seen.add(faction)
            to_insert.append({
                "system_id":   "wh40k",
                "entity_type": "Unit",
                "faction":     faction,
                "name":        name,
                "data_json":   json.dumps(unit),
                "source":      source,
                "is_custom":   0,
                "campaign_id": None,
            })

            if progress_cb and i % 10 == 0:
                try:
                    progress_cb(i, total, name)
                except Exception:
                    pass

        imported = self._repo.add_entities_bulk(to_insert)
        if progress_cb:
            try:
                progress_cb(total, total, "Done")
            except Exception:
                pass

        return {
            "imported": imported,
            "skipped":  skipped,
            "factions": sorted(factions_seen),
        }

    def import_aos(
        self,
        army_file: str | None = None,
        progress_cb: Callable | None = None,
    ) -> dict:
        """Import Age of Sigmar warscrolls from JSON army files."""
        aos_dir = _game_data_path("age_of_sigmar")

        if army_file:
            files = [aos_dir / army_file]
        else:
            files = sorted(
                p for p in aos_dir.glob("*.json")
                if p.name not in _AOS_EXCLUDE
            )

        source = "Age of Sigmar"
        if not army_file:
            self._repo.delete_by_source(source)

        total_files = len(files)
        to_insert: list[dict] = []
        factions_seen: set[str] = set()
        processed = 0

        for fi, fpath in enumerate(files):
            # Derive faction name from filename
            faction = fpath.stem.replace("_", " ").title()

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                log.warning(f"[RulesLibSvc] AoS file {fpath.name} load error: {e}")
                continue

            # Support both list format and {"army": "...", "units": [...]}
            if isinstance(data, dict):
                units = data.get("units", [])
                army_name = data.get("army", "")
                if army_name:
                    faction = army_name
            elif isinstance(data, list):
                units = data
            else:
                units = []

            factions_seen.add(faction)

            for unit in units:
                name = unit.get("name", "")
                if not name:
                    continue
                to_insert.append({
                    "system_id":   "aos",
                    "entity_type": "Warscroll",
                    "faction":     faction,
                    "name":        name,
                    "data_json":   json.dumps(unit),
                    "source":      source,
                    "is_custom":   0,
                    "campaign_id": None,
                })
                processed += 1
                if progress_cb and processed % 10 == 0:
                    try:
                        progress_cb(fi, total_files, name)
                    except Exception:
                        pass

        imported = self._repo.add_entities_bulk(to_insert)
        if progress_cb:
            try:
                progress_cb(total_files, total_files, "Done")
            except Exception:
                pass

        return {"imported": imported, "factions": sorted(factions_seen)}

    def _import_dnd_file(
        self,
        filename: str,
        entity_type: str,
        source: str,
        faction_fn,
        progress_cb: Callable | None = None,
        progress_interval: int = 50,
    ) -> dict:
        """Generic D&D import helper — reads a JSON array and bulk-inserts."""
        path = _game_data_path(f"dungeons_and_dragons/{filename}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception as e:
            log.error(f"[RulesLibSvc] dnd load error ({filename}): {e}")
            return {"imported": 0, "error": str(e)}

        self._repo.delete_by_source(source)
        total = len(records)
        to_insert: list[dict] = []

        for i, rec in enumerate(records):
            name = rec.get("name", "")
            if not name:
                continue
            to_insert.append({
                "system_id":   "dnd5e",
                "entity_type": entity_type,
                "faction":     faction_fn(rec),
                "name":        name,
                "data_json":   json.dumps(rec),
                "source":      source,
                "is_custom":   0,
                "campaign_id": None,
            })
            if progress_cb and i % progress_interval == 0:
                try:
                    progress_cb(i, total, name)
                except Exception:
                    pass

        imported = self._repo.add_entities_bulk(to_insert)
        if progress_cb:
            try:
                progress_cb(total, total, "Done")
            except Exception:
                pass
        return {"imported": imported}

    def import_dnd_monsters(self, progress_cb: Callable | None = None) -> dict:
        """Import all D&D 5e monsters."""
        def _faction(r):
            props = r.get("properties", {}) or {}
            return (props.get("Type") or "Unknown").capitalize()
        return self._import_dnd_file(
            "monsters.json", "Monster", "D&D 5e — Monsters", _faction,
            progress_cb, progress_interval=50,
        )

    def import_dnd_spells(self, progress_cb: Callable | None = None) -> dict:
        """Import all D&D 5e spells."""
        def _faction(r):
            props = r.get("properties", {}) or {}
            school = props.get("School") or props.get("school") or "Unknown"
            return school.capitalize()
        return self._import_dnd_file(
            "spells.json", "Spell", "D&D 5e — Spells", _faction,
            progress_cb, progress_interval=100,
        )

    def import_dnd_classes(self, progress_cb: Callable | None = None) -> dict:
        """Import all D&D 5e classes."""
        return self._import_dnd_file(
            "classes.json", "Class", "D&D 5e — Classes",
            lambda r: r.get("properties", {}).get("Category") or "Class",
            progress_cb,
        )

    def import_dnd_backgrounds(self, progress_cb: Callable | None = None) -> dict:
        """Import all D&D 5e backgrounds."""
        return self._import_dnd_file(
            "backgrounds.json", "Background", "D&D 5e — Backgrounds",
            lambda r: r.get("publisher") or "Unknown",
            progress_cb,
        )

    def import_dnd_species(self, progress_cb: Callable | None = None) -> dict:
        """Import all D&D 5e species / races."""
        return self._import_dnd_file(
            "species.json", "Species", "D&D 5e — Species",
            lambda r: r.get("publisher") or "Unknown",
            progress_cb,
        )

    def import_dnd_items(self, progress_cb: Callable | None = None) -> dict:
        """Import all D&D 5e items."""
        def _faction(r):
            props = r.get("properties", {}) or {}
            return props.get("Item Type") or "Other"
        return self._import_dnd_file(
            "items.json", "Item", "D&D 5e — Items", _faction,
            progress_cb, progress_interval=200,
        )

    def import_dnd_all(self, progress_cb: Callable | None = None) -> dict:
        """Import all D&D 5e content (spells, classes, backgrounds, species, items, monsters)."""
        totals: dict[str, int] = {}
        steps = [
            ("Spells",      self.import_dnd_spells),
            ("Classes",     self.import_dnd_classes),
            ("Backgrounds", self.import_dnd_backgrounds),
            ("Species",     self.import_dnd_species),
            ("Items",       self.import_dnd_items),
            ("Monsters",    self.import_dnd_monsters),
        ]
        for label, fn in steps:
            if progress_cb:
                try:
                    progress_cb(0, 1, f"Importing {label}…")
                except Exception:
                    pass
            result = fn(progress_cb=progress_cb)
            totals[label] = result.get("imported", 0)
        return {"imported": sum(totals.values()), "breakdown": totals}

    # ── Data discovery ────────────────────────────────────────────────────────

    def get_wh40k_factions(self) -> list[str]:
        """Return sorted list of unique factionname values from the JSON."""
        path = _game_data_path("community/wh40k_10th.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                units = json.load(f)
            factions = sorted({u.get("factionname", "") for u in units if u.get("factionname")})
            return factions
        except Exception as e:
            log.error(f"[RulesLibSvc] get_wh40k_factions error: {e}")
            return []

    def get_aos_armies(self) -> list[str]:
        """Return sorted display names for all AoS army JSON files."""
        aos_dir = _game_data_path("age_of_sigmar")
        names = []
        try:
            for p in sorted(aos_dir.glob("*.json")):
                if p.name in _AOS_EXCLUDE:
                    continue
                names.append(p.stem.replace("_", " ").title())
        except Exception as e:
            log.error(f"[RulesLibSvc] get_aos_armies error: {e}")
        return names

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def get_entities(
        self,
        system_id=None,
        faction=None,
        entity_type=None,
        search=None,
        campaign_id=None,
        limit: int = 500,
    ) -> list[dict]:
        return self._repo.get_entities(
            system_id=system_id,
            faction=faction,
            entity_type=entity_type,
            search=search,
            campaign_id=campaign_id,
            limit=limit,
        )

    def get_entity(self, entity_id: int) -> dict | None:
        return self._repo.get_entity(entity_id)

    def add_custom_entity(
        self,
        system_id: str,
        entity_type: str,
        faction: str,
        name: str,
        stats: dict,
        abilities: list,
        notes: str,
        campaign_id=None,
    ) -> int:
        data = {
            "name":      name,
            "stats":     stats,
            "abilities": abilities,
            "notes":     notes,
        }
        return self._repo.add_entity(
            system_id=system_id,
            entity_type=entity_type,
            faction=faction,
            name=name,
            data_json=json.dumps(data),
            source="Custom",
            is_custom=1,
            campaign_id=campaign_id,
        )

    def update_entity(self, entity_id: int, **kwargs) -> bool:
        return self._repo.update_entity(entity_id, **kwargs)

    def delete_entity(self, entity_id: int) -> bool:
        return self._repo.delete_entity(entity_id)

    def get_factions(self, system_id: str) -> list[str]:
        return self._repo.get_factions(system_id)

    def get_entity_types(self, system_id: str) -> list[str]:
        return self._repo.get_entity_types(system_id)

    def has_data(self, system_id: str) -> bool:
        return self._repo.has_data(system_id)

    def get_stats(self) -> dict:
        wh40k  = self._repo.count(system_id="wh40k")
        aos    = self._repo.count(system_id="aos")
        dnd5e  = self._repo.count(system_id="dnd5e")
        custom = self._repo.count(system_id="custom")
        # Also count custom entries from any system
        custom_total = 0
        try:
            rows = self._repo._db.query(
                "SELECT COUNT(*) FROM game_rules_library WHERE is_custom=1"
            )
            custom_total = rows[0][0] if rows else 0
        except Exception:
            custom_total = custom
        return {
            "wh40k":  wh40k,
            "aos":    aos,
            "dnd5e":  dnd5e,
            "custom": custom_total,
            "total":  wh40k + aos + dnd5e + custom,
        }
