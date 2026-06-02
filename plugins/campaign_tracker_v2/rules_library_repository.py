"""
Campaign Tracker v2 — Rules Library Repository.

Owns the game_rules_library table: a universal store for game reference
data across Warhammer 40K, Age of Sigmar, D&D 5e, and custom entries.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

_TABLE = "game_rules_library"


class RulesLibraryRepository:

    def __init__(self, db):
        self._db = db
        self._init_tables()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_tables(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                system_id   TEXT    NOT NULL DEFAULT '',
                entity_type TEXT    NOT NULL DEFAULT '',
                faction     TEXT    NOT NULL DEFAULT '',
                name        TEXT    NOT NULL,
                data_json   TEXT    NOT NULL DEFAULT '{{}}',
                source      TEXT    NOT NULL DEFAULT '',
                is_custom   INTEGER NOT NULL DEFAULT 0,
                campaign_id INTEGER,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        for col, idx in [
            ("system_id",   f"idx_{_TABLE}_system"),
            ("faction",     f"idx_{_TABLE}_faction"),
            ("entity_type", f"idx_{_TABLE}_etype"),
            ("campaign_id", f"idx_{_TABLE}_camp"),
            ("name",        f"idx_{_TABLE}_name"),
        ]:
            self._db.execute(
                f"CREATE INDEX IF NOT EXISTS {idx} ON {_TABLE} ({col})"
            )

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_entity(
        self,
        system_id: str,
        entity_type: str,
        faction: str,
        name: str,
        data_json: str,
        source: str,
        is_custom: int = 0,
        campaign_id=None,
    ) -> int:
        cur = self._db.execute(
            f"INSERT INTO {_TABLE} "
            f"(system_id, entity_type, faction, name, data_json, source, is_custom, campaign_id) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (system_id, entity_type, faction, name, data_json, source,
             is_custom, campaign_id),
        )
        return cur.lastrowid

    def add_entities_bulk(self, rows: list[dict]) -> int:
        """Batch insert a list of entity dicts. Returns count inserted."""
        if not rows:
            return 0
        inserted = 0
        try:
            with self._db.transaction():
                for row in rows:
                    self._db.execute(
                        f"INSERT INTO {_TABLE} "
                        f"(system_id, entity_type, faction, name, data_json, "
                        f"source, is_custom, campaign_id) "
                        f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            row.get("system_id", ""),
                            row.get("entity_type", ""),
                            row.get("faction", ""),
                            row.get("name", ""),
                            row.get("data_json", "{}"),
                            row.get("source", ""),
                            int(row.get("is_custom", 0)),
                            row.get("campaign_id"),
                        ),
                    )
                    inserted += 1
        except Exception as e:
            log.error(f"[RulesLibRepo] bulk insert error: {e}")
            raise
        return inserted

    def update_entity(self, entity_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        allowed = {
            "system_id", "entity_type", "faction", "name",
            "data_json", "source", "is_custom", "campaign_id",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [entity_id]
        self._db.execute(
            f"UPDATE {_TABLE} SET {set_clause}, updated_at=datetime('now') "
            f"WHERE id=?",
            values,
        )
        return True

    def delete_entity(self, entity_id: int) -> bool:
        self._db.execute(f"DELETE FROM {_TABLE} WHERE id=?", (entity_id,))
        return True

    def delete_by_source(self, source: str) -> int:
        rows = self._db.query(
            f"SELECT COUNT(*) FROM {_TABLE} WHERE source=?", (source,)
        )
        count = rows[0][0] if rows else 0
        self._db.execute(f"DELETE FROM {_TABLE} WHERE source=?", (source,))
        return count

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_entity(self, entity_id: int) -> dict | None:
        rows = self._db.query(
            f"SELECT id, system_id, entity_type, faction, name, data_json, "
            f"source, is_custom, campaign_id, created_at, updated_at "
            f"FROM {_TABLE} WHERE id=?",
            (entity_id,),
        )
        if not rows:
            return None
        return self._row_to_dict(rows[0])

    def get_entities(
        self,
        system_id=None,
        faction=None,
        entity_type=None,
        search=None,
        campaign_id=None,
        limit: int = 500,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list = []

        if system_id and system_id != "all":
            clauses.append("system_id=?")
            params.append(system_id)
        if faction:
            clauses.append("faction=?")
            params.append(faction)
        if entity_type:
            clauses.append("entity_type=?")
            params.append(entity_type)
        if search:
            clauses.append("name LIKE ?")
            params.append(f"%{search}%")
        if campaign_id is not None:
            clauses.append("(campaign_id=? OR campaign_id IS NULL)")
            params.append(campaign_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        rows = self._db.query(
            f"SELECT id, system_id, entity_type, faction, name, data_json, "
            f"source, is_custom, campaign_id, created_at, updated_at "
            f"FROM {_TABLE} {where} ORDER BY name LIMIT ?",
            params,
        )
        return [self._row_to_dict(r) for r in rows]

    def get_factions(self, system_id: str) -> list[str]:
        rows = self._db.query(
            f"SELECT DISTINCT faction FROM {_TABLE} "
            f"WHERE system_id=? AND faction != '' ORDER BY faction",
            (system_id,),
        )
        return [r[0] for r in rows]

    def get_entity_types(self, system_id: str) -> list[str]:
        rows = self._db.query(
            f"SELECT DISTINCT entity_type FROM {_TABLE} "
            f"WHERE system_id=? AND entity_type != '' ORDER BY entity_type",
            (system_id,),
        )
        return [r[0] for r in rows]

    def count(self, system_id=None, faction=None) -> int:
        clauses: list[str] = []
        params: list = []
        if system_id:
            clauses.append("system_id=?")
            params.append(system_id)
        if faction:
            clauses.append("faction=?")
            params.append(faction)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            f"SELECT COUNT(*) FROM {_TABLE} {where}", params
        )
        return rows[0][0] if rows else 0

    def has_data(self, system_id: str) -> bool:
        rows = self._db.query(
            f"SELECT 1 FROM {_TABLE} WHERE system_id=? LIMIT 1",
            (system_id,),
        )
        return bool(rows)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row) -> dict:
        (id_, system_id, entity_type, faction, name, data_json,
         source, is_custom, campaign_id, created_at, updated_at) = row
        data = {}
        try:
            data = json.loads(data_json) if data_json else {}
        except Exception:
            pass
        return {
            "id":          id_,
            "system_id":   system_id,
            "entity_type": entity_type,
            "faction":     faction,
            "name":        name,
            "data_json":   data_json,
            "data":        data,
            "source":      source,
            "is_custom":   bool(is_custom),
            "campaign_id": campaign_id,
            "created_at":  created_at,
            "updated_at":  updated_at,
        }
