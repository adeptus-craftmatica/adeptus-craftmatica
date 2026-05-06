"""
Army Builder Repository

Three tables:
  army_builder_armies      — the lists
  army_builder_units       — unit entries within each list
  army_builder_unit_paints — direct unit → paint links (cross-plugin)
"""
from __future__ import annotations

from typing import Optional

from .models import Army, ArmyUnit, ArmyFilter


class ArmyRepository:
    ARMY_TABLE = "army_builder_armies"
    UNIT_TABLE = "army_builder_units"
    PAINT_LINK_TABLE = "army_builder_unit_paints"

    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    # ============================================================
    # SCHEMA
    # ============================================================

    def _ensure_schema(self):
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ARMY_TABLE} (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                game_system  TEXT NOT NULL,
                faction      TEXT NOT NULL,
                format       TEXT NOT NULL DEFAULT '',
                points_limit INTEGER NOT NULL DEFAULT 0,
                notes        TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.UNIT_TABLE} (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                army_id       INTEGER NOT NULL,
                unit_name     TEXT NOT NULL,
                unit_role     TEXT NOT NULL,
                points_cost   INTEGER NOT NULL DEFAULT 0,
                quantity      INTEGER NOT NULL DEFAULT 1,
                wargear_notes TEXT,
                model_id      INTEGER,
                sort_order    INTEGER NOT NULL DEFAULT 0,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (army_id) REFERENCES {self.ARMY_TABLE}(id) ON DELETE CASCADE
            )
        """)

        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_ab_army_system
            ON {self.ARMY_TABLE}(game_system)
        """)
        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_ab_unit_army
            ON {self.UNIT_TABLE}(army_id)
        """)
        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_ab_unit_model
            ON {self.UNIT_TABLE}(model_id)
        """)

        # Paint links: many-to-many between units and paints
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.PAINT_LINK_TABLE} (
                unit_id   INTEGER NOT NULL,
                paint_id  INTEGER NOT NULL,
                PRIMARY KEY (unit_id, paint_id)
            )
        """)

    # ============================================================
    # ARMY CRUD
    # ============================================================

    def add_army(self, army: Army) -> int:
        cursor = self.db.execute(f"""
            INSERT INTO {self.ARMY_TABLE}
                (name, game_system, faction, format, points_limit, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            army.name.strip(),
            army.game_system.strip(),
            army.faction.strip(),
            army.format.strip(),
            army.points_limit,
            army.notes,
        ))
        return cursor.lastrowid

    def get_army(self, army_id: int) -> Optional[Army]:
        rows = self.db.query(f"""
            SELECT id, name, game_system, faction, format, points_limit, notes
            FROM {self.ARMY_TABLE} WHERE id = ?
        """, (army_id,))
        return self._row_to_army(rows[0]) if rows else None

    def get_all_armies(self) -> list[Army]:
        rows = self.db.query(f"""
            SELECT id, name, game_system, faction, format, points_limit, notes
            FROM {self.ARMY_TABLE}
            ORDER BY game_system, faction, name
        """)
        return [self._row_to_army(r) for r in rows]

    def find_armies(self, f: ArmyFilter) -> list[Army]:
        armies = self.get_all_armies()
        if f.is_empty():
            return armies
        return [a for a in armies if f.matches(a)]

    def update_army(self, army: Army) -> bool:
        if army.id is None:
            return False
        cursor = self.db.execute(f"""
            UPDATE {self.ARMY_TABLE}
            SET name = ?, game_system = ?, faction = ?, format = ?,
                points_limit = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            army.name.strip(),
            army.game_system.strip(),
            army.faction.strip(),
            army.format.strip(),
            army.points_limit,
            army.notes,
            army.id,
        ))
        return cursor.rowcount > 0

    def delete_army(self, army_id: int) -> bool:
        # Clean up paint links before deleting units
        units = self.get_units_for_army(army_id)
        for unit in units:
            if unit.id:
                self.db.execute(
                    f"DELETE FROM {self.PAINT_LINK_TABLE} WHERE unit_id = ?", (unit.id,)
                )
        self.db.execute(f"DELETE FROM {self.UNIT_TABLE} WHERE army_id = ?", (army_id,))
        cursor = self.db.execute(f"DELETE FROM {self.ARMY_TABLE} WHERE id = ?", (army_id,))
        return cursor.rowcount > 0

    def count_armies(self) -> int:
        rows = self.db.query(f"SELECT COUNT(*) as c FROM {self.ARMY_TABLE}")
        return rows[0]["c"] if rows else 0

    # ============================================================
    # UNIT CRUD
    # ============================================================

    def add_unit(self, unit: ArmyUnit) -> int:
        cursor = self.db.execute(f"""
            INSERT INTO {self.UNIT_TABLE}
                (army_id, unit_name, unit_role, points_cost,
                 quantity, wargear_notes, model_id, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            unit.army_id,
            unit.unit_name.strip(),
            unit.unit_role.strip(),
            unit.points_cost,
            unit.quantity,
            unit.wargear_notes,
            unit.model_id,
            unit.sort_order,
        ))
        unit_id = cursor.lastrowid
        self._save_paint_links(unit_id, unit.linked_paint_ids)
        return unit_id

    def get_unit(self, unit_id: int) -> Optional[ArmyUnit]:
        rows = self.db.query(f"""
            SELECT id, army_id, unit_name, unit_role, points_cost,
                   quantity, wargear_notes, model_id, sort_order
            FROM {self.UNIT_TABLE} WHERE id = ?
        """, (unit_id,))
        if not rows:
            return None
        unit = self._row_to_unit(rows[0])
        unit.linked_paint_ids = self._get_paint_links(unit_id)
        return unit

    def get_units_for_army(self, army_id: int) -> list[ArmyUnit]:
        rows = self.db.query(f"""
            SELECT id, army_id, unit_name, unit_role, points_cost,
                   quantity, wargear_notes, model_id, sort_order
            FROM {self.UNIT_TABLE}
            WHERE army_id = ?
            ORDER BY unit_role, sort_order, unit_name
        """, (army_id,))
        units = [self._row_to_unit(r) for r in rows]
        for u in units:
            u.linked_paint_ids = self._get_paint_links(u.id)
        return units

    def update_unit(self, unit: ArmyUnit) -> bool:
        if unit.id is None:
            return False
        cursor = self.db.execute(f"""
            UPDATE {self.UNIT_TABLE}
            SET unit_name = ?, unit_role = ?, points_cost = ?,
                quantity = ?, wargear_notes = ?, model_id = ?,
                sort_order = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            unit.unit_name.strip(),
            unit.unit_role.strip(),
            unit.points_cost,
            unit.quantity,
            unit.wargear_notes,
            unit.model_id,
            unit.sort_order,
            unit.id,
        ))
        self._save_paint_links(unit.id, unit.linked_paint_ids)
        return cursor.rowcount > 0

    def delete_unit(self, unit_id: int) -> bool:
        self.db.execute(
            f"DELETE FROM {self.PAINT_LINK_TABLE} WHERE unit_id = ?", (unit_id,)
        )
        cursor = self.db.execute(
            f"DELETE FROM {self.UNIT_TABLE} WHERE id = ?", (unit_id,)
        )
        return cursor.rowcount > 0

    def delete_units_for_army(self, army_id: int) -> int:
        cursor = self.db.execute(
            f"DELETE FROM {self.UNIT_TABLE} WHERE army_id = ?", (army_id,)
        )
        return cursor.rowcount

    def count_units_for_army(self, army_id: int) -> int:
        rows = self.db.query(
            f"SELECT COUNT(*) as c FROM {self.UNIT_TABLE} WHERE army_id = ?", (army_id,)
        )
        return rows[0]["c"] if rows else 0

    def count_all_units(self) -> int:
        rows = self.db.query(f"SELECT COUNT(*) as c FROM {self.UNIT_TABLE}")
        return rows[0]["c"] if rows else 0

    # ============================================================
    # QUERIES
    # ============================================================

    def get_unique_game_systems(self) -> list[str]:
        rows = self.db.query(
            f"SELECT DISTINCT game_system FROM {self.ARMY_TABLE} ORDER BY game_system"
        )
        return [r["game_system"] for r in rows]

    def get_unique_factions(self, game_system: Optional[str] = None) -> list[str]:
        if game_system:
            rows = self.db.query(
                f"SELECT DISTINCT faction FROM {self.ARMY_TABLE} WHERE game_system = ? ORDER BY faction",
                (game_system,),
            )
        else:
            rows = self.db.query(
                f"SELECT DISTINCT faction FROM {self.ARMY_TABLE} ORDER BY faction"
            )
        return [r["faction"] for r in rows]

    def get_points_total_for_army(self, army_id: int) -> float:
        rows = self.db.query(
            f"SELECT COALESCE(SUM(points_cost * quantity), 0) as total FROM {self.UNIT_TABLE} WHERE army_id = ?",
            (army_id,),
        )
        return rows[0]["total"] if rows else 0

    def remove_model_links(self, model_id: int):
        """Called when model_tracker deletes a model — nullify the link."""
        self.db.execute(
            f"UPDATE {self.UNIT_TABLE} SET model_id = NULL WHERE model_id = ?",
            (model_id,),
        )

    # ============================================================
    # PAINT LINKS (cross-plugin)
    # ============================================================

    def _get_paint_links(self, unit_id: int) -> list[int]:
        rows = self.db.query(
            f"SELECT paint_id FROM {self.PAINT_LINK_TABLE} WHERE unit_id = ?",
            (unit_id,),
        )
        return [r["paint_id"] for r in rows]

    def _save_paint_links(self, unit_id: int, paint_ids: list[int]):
        self.db.execute(
            f"DELETE FROM {self.PAINT_LINK_TABLE} WHERE unit_id = ?", (unit_id,)
        )
        for pid in paint_ids:
            try:
                self.db.execute(
                    f"INSERT OR IGNORE INTO {self.PAINT_LINK_TABLE} (unit_id, paint_id) VALUES (?, ?)",
                    (unit_id, pid),
                )
            except Exception:
                pass

    def remove_paint_links_everywhere(self, paint_id: int):
        """Called when paint_tracker deletes a paint."""
        self.db.execute(
            f"DELETE FROM {self.PAINT_LINK_TABLE} WHERE paint_id = ?", (paint_id,)
        )

    def get_all_paint_links_for_army(self, army_id: int) -> list[tuple[int, int]]:
        """Returns [(unit_id, paint_id), ...] for all units in the army."""
        rows = self.db.query(f"""
            SELECT pl.unit_id, pl.paint_id
            FROM {self.PAINT_LINK_TABLE} pl
            JOIN {self.UNIT_TABLE} u ON u.id = pl.unit_id
            WHERE u.army_id = ?
        """, (army_id,))
        return [(r["unit_id"], r["paint_id"]) for r in rows]

    def count_by_game_system(self) -> dict[str, int]:
        rows = self.db.query(f"""
            SELECT game_system, COUNT(*) as c FROM {self.ARMY_TABLE}
            GROUP BY game_system ORDER BY c DESC
        """)
        return {r["game_system"]: r["c"] for r in rows}

    def count_by_faction(self) -> dict[str, int]:
        rows = self.db.query(f"""
            SELECT faction, COUNT(*) as c FROM {self.ARMY_TABLE}
            GROUP BY faction ORDER BY c DESC
        """)
        return {r["faction"]: r["c"] for r in rows}

    # ============================================================
    # MAPPING
    # ============================================================

    def _row_to_army(self, row) -> Army:
        keys = row.keys()
        return Army(
            id=row["id"],
            name=row["name"],
            game_system=row["game_system"],
            faction=row["faction"],
            format=row["format"] if "format" in keys else "",
            points_limit=row["points_limit"] if "points_limit" in keys else 0,
            notes=row["notes"] if "notes" in keys else None,
        )

    def _row_to_unit(self, row) -> ArmyUnit:
        keys = row.keys()
        return ArmyUnit(
            id=row["id"],
            army_id=row["army_id"],
            unit_name=row["unit_name"],
            unit_role=row["unit_role"],
            points_cost=float(row["points_cost"]) if "points_cost" in keys else 0.0,
            quantity=row["quantity"] if "quantity" in keys else 1,
            wargear_notes=row["wargear_notes"] if "wargear_notes" in keys else None,
            model_id=row["model_id"] if "model_id" in keys else None,
            sort_order=row["sort_order"] if "sort_order" in keys else 0,
        )
