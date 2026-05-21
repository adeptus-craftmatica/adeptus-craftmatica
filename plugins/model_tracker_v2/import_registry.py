"""
Model Tracker V2 — Import Registry

Extensible import template system for bulk-adding models from various
army builder export formats (40K, AoS, CSV, generic JSON).
"""
from __future__ import annotations

import csv
import io
import json
import logging
log = logging.getLogger(__name__)

from typing import Optional


# ── Type inference helper ─────────────────────────────────────────────────────

_TYPE_MAP = {
    "infantry":  "Infantry",
    "troop":     "Infantry",
    "warrior":   "Infantry",
    "character": "Character / Hero",
    "hero":      "Character / Hero",
    "leader":    "Character / Hero",
    "warlord":   "Character / Hero",
    "monster":   "Monster / Beast",
    "beast":     "Monster / Beast",
    "daemon":    "Monster / Beast",
    "vehicle":   "Vehicle / Tank",
    "tank":      "Vehicle / Tank",
    "walker":    "Vehicle / Tank",
    "cavalry":   "Cavalry",
    "mounted":   "Cavalry",
    "artillery": "Artillery",
    "gun":       "Artillery",
    "mech":      "Mech / Mobile Suit",
    "suit":      "Mech / Mobile Suit",
    "terrain":   "Terrain",
    "scenery":   "Scenery",
}


def _infer_type(keywords: list[str]) -> str:
    for kw in [k.lower() for k in keywords]:
        for key, val in _TYPE_MAP.items():
            if key in kw:
                return val
    return "Other"


# ══════════════════════════════════════════════════════════════════════════════
#  Base template
# ══════════════════════════════════════════════════════════════════════════════

class ImportTemplate:
    id:          str = ""
    name:        str = ""
    description: str = ""

    def parse(self, raw_text: str) -> list[dict]:
        """
        Parse raw text/JSON and return list of model dicts ready for
        service.add_model().  Raises NotImplementedError if not overridden.
        """
        raise NotImplementedError


# ══════════════════════════════════════════════════════════════════════════════
#  Warhammer 40K Army Builder JSON
# ══════════════════════════════════════════════════════════════════════════════

class Wh40kJsonTemplate(ImportTemplate):
    id          = "wh40k"
    name        = "Warhammer 40,000 Army Builder JSON"
    description = (
        "Parses the standard 40K army builder export format. "
        "Extracts unit names, faction, keywords, and composition quantity."
    )

    _GAME_SYSTEM = "Warhammer 40,000"

    def parse(self, raw_text: str) -> list[dict]:
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            log.warning(f"[WH40K IMPORT] JSON parse failed: {e}")
            return []

        # Support both root-as-list and root-as-dict with "units" / "detachments"
        units = self._extract_units(data)
        results: list[dict] = []
        for unit in units:
            try:
                model = self._normalize(unit)
                if model:
                    results.append(model)
            except Exception as e:
                log.warning(f"[WH40K IMPORT] Unit normalization failed: {e}")
        return results

    def _extract_units(self, data) -> list:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("units", "detachments", "selections", "roster"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return [data] if isinstance(data, dict) else []

    def _normalize(self, unit: dict) -> Optional[dict]:
        name = (
            unit.get("unitName") or unit.get("name") or
            unit.get("customName") or unit.get("unit_name", "")
        ).strip()
        if not name:
            return None

        faction = (
            unit.get("factionName") or unit.get("faction") or
            unit.get("allegiance", "Unknown Faction")
        ).strip()

        keywords = unit.get("keywords") or unit.get("Keywords") or []
        if isinstance(keywords, str):
            keywords = [kw.strip() for kw in keywords.split(",")]

        # Quantity from unit composition
        qty = 1
        compo = unit.get("unitCompo") or unit.get("unitComposition") or unit.get("models") or []
        if isinstance(compo, list) and compo:
            try:
                qty = max(1, sum(int(c.get("count", c.get("quantity", 1))) for c in compo if isinstance(c, dict)))
            except (TypeError, ValueError):
                qty = 1
        elif isinstance(compo, int):
            qty = max(1, compo)

        model_type = _infer_type(keywords)

        return {
            "name":        name,
            "game_system": self._GAME_SYSTEM,
            "faction":     faction or "Unknown Faction",
            "model_type":  model_type,
            "status":      "Unassembled",
            "scale":       "28mm",
            "quantity":    qty,
            "notes":       None,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Warhammer: Age of Sigmar JSON
# ══════════════════════════════════════════════════════════════════════════════

class AoSJsonTemplate(ImportTemplate):
    id          = "aos"
    name        = "Warhammer: Age of Sigmar Army Builder JSON"
    description = (
        "Parses the AoS army builder export format. "
        "Supports both strict and flexible field naming."
    )

    _GAME_SYSTEM = "Warhammer: Age of Sigmar"

    def parse(self, raw_text: str) -> list[dict]:
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            log.warning(f"[AOS IMPORT] JSON parse failed: {e}")
            return []

        units = self._extract_units(data)
        results: list[dict] = []
        for unit in units:
            try:
                model = self._normalize_flexible(unit)
                if model:
                    results.append(model)
            except Exception as e:
                log.warning(f"[AOS IMPORT] Unit normalization failed: {e}")
        return results

    def _extract_units(self, data) -> list:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("units", "warscrolls", "batallions", "army", "selections"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return [data] if isinstance(data, dict) else []

    def _normalize_flexible(self, unit: dict) -> Optional[dict]:
        name = (
            unit.get("warscrollName") or unit.get("name") or
            unit.get("unitName") or unit.get("unit_name", "")
        ).strip()
        if not name:
            return None

        grand_alliance = unit.get("grandAlliance") or unit.get("grand_alliance") or ""
        faction = (
            unit.get("allegiance") or unit.get("faction") or
            unit.get("subfaction") or unit.get("army") or
            grand_alliance or "Unknown Faction"
        ).strip()

        keywords = unit.get("keywords") or unit.get("Keywords") or []
        if isinstance(keywords, str):
            keywords = [kw.strip() for kw in keywords.split(",")]

        qty = 1
        size_field = unit.get("unitSize") or unit.get("unit_size") or unit.get("models")
        if isinstance(size_field, int):
            qty = max(1, size_field)

        model_type = _infer_type(keywords)

        return {
            "name":        name,
            "game_system": self._GAME_SYSTEM,
            "faction":     faction,
            "model_type":  model_type,
            "status":      "Unassembled",
            "scale":       "28mm",
            "quantity":    qty,
            "notes":       None,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  CSV Template
# ══════════════════════════════════════════════════════════════════════════════

class CsvTemplate(ImportTemplate):
    id          = "csv"
    name        = "CSV (name, game_system, faction, …)"
    description = (
        "Parses a CSV file with a header row. "
        "Required columns: name, game_system, faction. "
        "Optional: model_type, status, scale, quantity, notes."
    )

    _REQUIRED = {"name", "game_system", "faction"}
    _VALID_STATUSES = {"Unassembled", "Assembled", "Primed", "WIP", "Painted", "Based", "Complete"}

    def parse(self, raw_text: str) -> list[dict]:
        results: list[dict] = []
        try:
            reader = csv.DictReader(io.StringIO(raw_text.strip()))
            if not reader.fieldnames:
                log.warning("[CSV IMPORT] No header row found")
                return []

            headers = {h.strip().lower() for h in reader.fieldnames}
            missing = self._REQUIRED - headers
            if missing:
                log.warning(f"[CSV IMPORT] Missing required columns: {missing}")
                return []

            for idx, raw_row in enumerate(reader):
                row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
                try:
                    model = self._parse_row(row, idx + 2)  # +2: header + 1-based
                    if model:
                        results.append(model)
                except Exception as e:
                    log.warning(f"[CSV IMPORT] Row {idx + 2}: {e}")
        except Exception as e:
            log.error(f"[CSV IMPORT] Parse failed: {e}")
        return results

    def _parse_row(self, row: dict, line: int) -> Optional[dict]:
        name        = row.get("name", "")
        game_system = row.get("game_system", "")
        faction     = row.get("faction", "")

        if not name or not game_system or not faction:
            log.warning(f"[CSV IMPORT] Line {line}: skipping — missing required field(s)")
            return None

        status = row.get("status", "Unassembled")
        if status not in self._VALID_STATUSES:
            log.warning(f"[CSV IMPORT] Line {line}: unknown status '{status}' — defaulting to Unassembled")
            status = "Unassembled"

        qty_str = row.get("quantity", "1")
        try:
            qty = max(1, int(qty_str))
        except (ValueError, TypeError):
            qty = 1

        return {
            "name":        name,
            "game_system": game_system,
            "faction":     faction,
            "model_type":  row.get("model_type", "Other") or "Other",
            "status":      status,
            "scale":       row.get("scale", ""),
            "quantity":    qty,
            "notes":       row.get("notes") or None,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Generic JSON Template
# ══════════════════════════════════════════════════════════════════════════════

class GenericJsonTemplate(ImportTemplate):
    id          = "generic_json"
    name        = "Generic JSON list"
    description = (
        "Parses a JSON array of objects. "
        "Required fields: name, game_system, faction. "
        "Optional: model_type, status, scale, quantity, notes."
    )

    _VALID_STATUSES = {"Unassembled", "Assembled", "Primed", "WIP", "Painted", "Based", "Complete"}

    def parse(self, raw_text: str) -> list[dict]:
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            log.warning(f"[JSON IMPORT] Parse failed: {e}")
            return []

        if isinstance(data, dict):
            # Try to find a list inside
            for key in ("models", "units", "items", "data", "results"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
            else:
                data = [data]

        if not isinstance(data, list):
            log.warning("[JSON IMPORT] Root is not a list and no known key found")
            return []

        results: list[dict] = []
        for idx, obj in enumerate(data):
            if not isinstance(obj, dict):
                continue
            try:
                model = self._normalize(obj, idx + 1)
                if model:
                    results.append(model)
            except Exception as e:
                log.warning(f"[JSON IMPORT] Object {idx + 1}: {e}")
        return results

    def _normalize(self, obj: dict, idx: int) -> Optional[dict]:
        name        = (obj.get("name") or "").strip()
        game_system = (obj.get("game_system") or obj.get("gameSystem") or "").strip()
        faction     = (obj.get("faction") or "").strip()

        if not name or not game_system or not faction:
            log.warning(f"[JSON IMPORT] Object {idx}: skipping — missing required field(s)")
            return None

        status = obj.get("status", "Unassembled")
        if status not in self._VALID_STATUSES:
            status = "Unassembled"

        qty = obj.get("quantity") or obj.get("qty") or 1
        try:
            qty = max(1, int(qty))
        except (ValueError, TypeError):
            qty = 1

        return {
            "name":        name,
            "game_system": game_system,
            "faction":     faction,
            "model_type":  (obj.get("model_type") or obj.get("modelType") or "Other").strip() or "Other",
            "status":      status,
            "scale":       (obj.get("scale") or "").strip(),
            "quantity":    qty,
            "notes":       obj.get("notes") or None,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Registry
# ══════════════════════════════════════════════════════════════════════════════

class ImportRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, ImportTemplate] = {}
        # Register built-ins
        for tmpl in (Wh40kJsonTemplate(), AoSJsonTemplate(), CsvTemplate(), GenericJsonTemplate()):
            self.register(tmpl)

    def register(self, template: ImportTemplate) -> None:
        self._templates[template.id] = template
        log.debug(f"[IMPORT REGISTRY] Registered template: {template.id}")

    def get(self, template_id: str) -> Optional[ImportTemplate]:
        return self._templates.get(template_id)

    def list_all(self) -> list[ImportTemplate]:
        return list(self._templates.values())
