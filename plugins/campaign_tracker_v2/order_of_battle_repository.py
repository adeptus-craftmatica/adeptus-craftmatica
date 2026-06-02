"""
Campaign Tracker v2 — Order of Battle Repository.

Owns two tables:
  campaign_order_of_battle  — the persistent unit roster per campaign
  campaign_army_links       — many-to-many links to army_builder armies
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_TABLE_OOB   = "campaign_order_of_battle"
_TABLE_LINKS = "campaign_army_links"


class OrderOfBattleRepository:

    def __init__(self, db):
        self._db = db
        self._init_tables()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_tables(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE_OOB} (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id       INTEGER NOT NULL,
                library_entity_id INTEGER,
                custom_name       TEXT    DEFAULT '',
                unit_role         TEXT    DEFAULT '',
                faction           TEXT    DEFAULT '',
                system_id         TEXT    DEFAULT '',
                loadout_json      TEXT    DEFAULT '[]',
                points_cost       INTEGER DEFAULT 0,
                power_rating      INTEGER DEFAULT 0,
                supply_used       INTEGER DEFAULT 1,
                quantity          INTEGER DEFAULT 1,
                notes             TEXT    DEFAULT '',
                created_at        TEXT    DEFAULT (datetime('now')),
                updated_at        TEXT    DEFAULT (datetime('now'))
            )
        """)
        self._db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{_TABLE_OOB}_campaign
                ON {_TABLE_OOB} (campaign_id)
        """)
        self._db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{_TABLE_OOB}_entity
                ON {_TABLE_OOB} (library_entity_id)
        """)

        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE_LINKS} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                army_id     INTEGER NOT NULL,
                label       TEXT    DEFAULT '',
                is_primary  INTEGER DEFAULT 0,
                created_at  TEXT    DEFAULT (datetime('now')),
                UNIQUE(campaign_id, army_id)
            )
        """)
        self._db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{_TABLE_LINKS}_campaign
                ON {_TABLE_LINKS} (campaign_id)
        """)

    # ── Order of Battle — Write ───────────────────────────────────────────────

    def add_entry(
        self,
        campaign_id: int,
        library_entity_id=None,
        custom_name: str = "",
        unit_role: str = "",
        faction: str = "",
        system_id: str = "",
        loadout_json: str = "[]",
        points_cost: int = 0,
        power_rating: int = 0,
        supply_used: int = 1,
        quantity: int = 1,
        notes: str = "",
    ) -> int:
        cur = self._db.execute(
            f"INSERT INTO {_TABLE_OOB} "
            f"(campaign_id, library_entity_id, custom_name, unit_role, faction, "
            f"system_id, loadout_json, points_cost, power_rating, supply_used, "
            f"quantity, notes) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                campaign_id,
                library_entity_id,
                custom_name,
                unit_role,
                faction,
                system_id,
                loadout_json,
                int(points_cost),
                int(power_rating),
                int(supply_used),
                int(quantity),
                notes,
            ),
        )
        return cur.lastrowid

    def update_entry(self, entry_id: int, **kwargs) -> bool:
        allowed = {
            "library_entity_id", "custom_name", "unit_role", "faction",
            "system_id", "loadout_json", "points_cost", "power_rating",
            "supply_used", "quantity", "notes",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [entry_id]
        self._db.execute(
            f"UPDATE {_TABLE_OOB} SET {set_clause}, updated_at=datetime('now') "
            f"WHERE id=?",
            values,
        )
        return True

    def delete_entry(self, entry_id: int) -> bool:
        self._db.execute(f"DELETE FROM {_TABLE_OOB} WHERE id=?", (entry_id,))
        return True

    # ── Order of Battle — Read ────────────────────────────────────────────────

    def get_entry(self, entry_id: int) -> dict | None:
        rows = self._db.query(
            f"SELECT id, campaign_id, library_entity_id, custom_name, unit_role, "
            f"faction, system_id, loadout_json, points_cost, power_rating, "
            f"supply_used, quantity, notes, created_at, updated_at "
            f"FROM {_TABLE_OOB} WHERE id=?",
            (entry_id,),
        )
        if not rows:
            return None
        return self._oob_row_to_dict(rows[0])

    def get_entries(self, campaign_id: int) -> list[dict]:
        rows = self._db.query(
            f"SELECT id, campaign_id, library_entity_id, custom_name, unit_role, "
            f"faction, system_id, loadout_json, points_cost, power_rating, "
            f"supply_used, quantity, notes, created_at, updated_at "
            f"FROM {_TABLE_OOB} WHERE campaign_id=? "
            f"ORDER BY unit_role, custom_name",
            (campaign_id,),
        )
        return [self._oob_row_to_dict(r) for r in rows]

    def get_entries_by_role(self, campaign_id: int, role: str) -> list[dict]:
        rows = self._db.query(
            f"SELECT id, campaign_id, library_entity_id, custom_name, unit_role, "
            f"faction, system_id, loadout_json, points_cost, power_rating, "
            f"supply_used, quantity, notes, created_at, updated_at "
            f"FROM {_TABLE_OOB} WHERE campaign_id=? AND unit_role=? "
            f"ORDER BY custom_name",
            (campaign_id, role),
        )
        return [self._oob_row_to_dict(r) for r in rows]

    def get_stats(self, campaign_id: int) -> dict:
        rows = self._db.query(
            f"SELECT unit_role, quantity, points_cost, supply_used "
            f"FROM {_TABLE_OOB} WHERE campaign_id=?",
            (campaign_id,),
        )
        total_units  = 0
        total_points = 0
        total_supply = 0
        by_role: dict[str, int] = {}
        for role, qty, pts, supply in rows:
            qty    = int(qty    or 1)
            pts    = int(pts    or 0)
            supply = int(supply or 1)
            total_units  += qty
            total_points += pts * qty
            total_supply += supply * qty
            role_key = role or "Other"
            by_role[role_key] = by_role.get(role_key, 0) + qty
        return {
            "total_units":  total_units,
            "total_points": total_points,
            "total_supply": total_supply,
            "by_role":      by_role,
        }

    # ── Army Links — Write ────────────────────────────────────────────────────

    def link_army(
        self,
        campaign_id: int,
        army_id: int,
        label: str = "",
        is_primary: bool = False,
    ) -> int:
        cur = self._db.execute(
            f"INSERT OR REPLACE INTO {_TABLE_LINKS} "
            f"(campaign_id, army_id, label, is_primary) VALUES (?, ?, ?, ?)",
            (campaign_id, army_id, label, int(is_primary)),
        )
        return cur.lastrowid

    def unlink_army(self, campaign_id: int, army_id: int) -> bool:
        self._db.execute(
            f"DELETE FROM {_TABLE_LINKS} WHERE campaign_id=? AND army_id=?",
            (campaign_id, army_id),
        )
        return True

    # ── Army Links — Read ─────────────────────────────────────────────────────

    def get_linked_armies(self, campaign_id: int) -> list[dict]:
        rows = self._db.query(
            f"SELECT id, campaign_id, army_id, label, is_primary, created_at "
            f"FROM {_TABLE_LINKS} WHERE campaign_id=? "
            f"ORDER BY is_primary DESC, id ASC",
            (campaign_id,),
        )
        return [self._link_row_to_dict(r) for r in rows]

    def is_linked(self, campaign_id: int, army_id: int) -> bool:
        rows = self._db.query(
            f"SELECT 1 FROM {_TABLE_LINKS} WHERE campaign_id=? AND army_id=? LIMIT 1",
            (campaign_id, army_id),
        )
        return bool(rows)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _oob_row_to_dict(row) -> dict:
        (id_, campaign_id, library_entity_id, custom_name, unit_role,
         faction, system_id, loadout_json, points_cost, power_rating,
         supply_used, quantity, notes, created_at, updated_at) = row
        return {
            "id":                id_,
            "campaign_id":       int(campaign_id),
            "library_entity_id": library_entity_id,
            "custom_name":       custom_name or "",
            "unit_role":         unit_role or "",
            "faction":           faction or "",
            "system_id":         system_id or "",
            "loadout_json":      loadout_json or "[]",
            "points_cost":       int(points_cost or 0),
            "power_rating":      int(power_rating or 0),
            "supply_used":       int(supply_used or 1),
            "quantity":          int(quantity or 1),
            "notes":             notes or "",
            "created_at":        created_at or "",
            "updated_at":        updated_at or "",
        }

    @staticmethod
    def _link_row_to_dict(row) -> dict:
        (id_, campaign_id, army_id, label, is_primary, created_at) = row
        return {
            "id":          id_,
            "campaign_id": int(campaign_id),
            "army_id":     int(army_id),
            "label":       label or "",
            "is_primary":  bool(is_primary),
            "created_at":  created_at or "",
        }
