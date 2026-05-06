"""
Paint Scheme Repository

Handles all database operations for schemes, steps and model links.
"""

from __future__ import annotations

from typing import Optional
from .models import PaintScheme, SchemeStep, SchemeFilter


class SchemeRepository:
    SCHEMES_TABLE = "paint_scheme_schemes"
    STEPS_TABLE = "paint_scheme_steps"
    LINKS_TABLE = "paint_scheme_model_links"

    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    # ============================================================
    # SCHEMA
    # ============================================================

    def _ensure_schema(self):
        # Schemes table
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.SCHEMES_TABLE} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                game_system TEXT NOT NULL DEFAULT '',
                faction     TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Steps table
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.STEPS_TABLE} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scheme_id   INTEGER NOT NULL,
                step_order  INTEGER NOT NULL DEFAULT 1,
                technique   TEXT NOT NULL DEFAULT 'Basecoat',
                paint_id    INTEGER,
                paint_name  TEXT NOT NULL DEFAULT '',
                notes       TEXT NOT NULL DEFAULT ''
            )
        """)

        # Model links table (many-to-many)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.LINKS_TABLE} (
                scheme_id   INTEGER NOT NULL,
                model_id    INTEGER NOT NULL,
                PRIMARY KEY (scheme_id, model_id)
            )
        """)

        # Migration-safe column additions
        self._ensure_column(self.SCHEMES_TABLE, "game_system", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(self.SCHEMES_TABLE, "faction",     "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(self.SCHEMES_TABLE, "description", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(self.STEPS_TABLE, "paint_name",    "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(self.STEPS_TABLE, "notes",         "TEXT NOT NULL DEFAULT ''")

        # Indexes
        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_scheme_steps_scheme_id
            ON {self.STEPS_TABLE}(scheme_id)
        """)
        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_scheme_links_scheme_id
            ON {self.LINKS_TABLE}(scheme_id)
        """)
        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_scheme_links_model_id
            ON {self.LINKS_TABLE}(model_id)
        """)

    def _ensure_column(self, table: str, column: str, column_def: str):
        """Add a column if it does not already exist (migration safety)."""
        try:
            cols = self.db.query(f"PRAGMA table_info({table})")
            existing = [c["name"] for c in cols]
            if column not in existing:
                print(f"[DB] Adding column {column} to {table}...")
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
        except Exception as e:
            print(f"[DB WARNING] Failed to ensure column {column} on {table}: {e}")

    # ============================================================
    # SCHEME CRUD
    # ============================================================

    def add_scheme(self, scheme: PaintScheme) -> int:
        cursor = self.db.execute(f"""
            INSERT INTO {self.SCHEMES_TABLE} (name, game_system, faction, description)
            VALUES (?, ?, ?, ?)
        """, (scheme.name, scheme.game_system, scheme.faction, scheme.description))
        return cursor.lastrowid

    def get_scheme_by_id(self, scheme_id: int) -> Optional[PaintScheme]:
        rows = self.db.query(f"""
            SELECT id, name, game_system, faction, description, created_at, updated_at
            FROM {self.SCHEMES_TABLE}
            WHERE id = ?
        """, (scheme_id,))
        if not rows:
            return None
        return self._row_to_scheme(rows[0])

    def get_all_schemes(self) -> list[PaintScheme]:
        rows = self.db.query(f"""
            SELECT id, name, game_system, faction, description, created_at, updated_at
            FROM {self.SCHEMES_TABLE}
            ORDER BY name COLLATE NOCASE
        """)
        return [self._row_to_scheme(r) for r in rows]

    def find_schemes(self, f: SchemeFilter) -> list[PaintScheme]:
        schemes = self.get_all_schemes()
        if f.is_empty():
            return schemes
        return [s for s in schemes if f.matches(s)]

    def update_scheme(self, scheme: PaintScheme) -> bool:
        if scheme.id is None:
            return False
        cursor = self.db.execute(f"""
            UPDATE {self.SCHEMES_TABLE}
            SET name = ?, game_system = ?, faction = ?, description = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (scheme.name, scheme.game_system, scheme.faction, scheme.description, scheme.id))
        return cursor.rowcount > 0

    def delete_scheme(self, scheme_id: int) -> bool:
        # Cascade: delete steps and links
        self.db.execute(f"DELETE FROM {self.STEPS_TABLE} WHERE scheme_id = ?", (scheme_id,))
        self.db.execute(f"DELETE FROM {self.LINKS_TABLE} WHERE scheme_id = ?", (scheme_id,))
        cursor = self.db.execute(f"DELETE FROM {self.SCHEMES_TABLE} WHERE id = ?", (scheme_id,))
        return cursor.rowcount > 0

    # ============================================================
    # STEP CRUD
    # ============================================================

    def add_step(self, step: SchemeStep) -> int:
        cursor = self.db.execute(f"""
            INSERT INTO {self.STEPS_TABLE} (scheme_id, step_order, technique, paint_id, paint_name, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            step.scheme_id,
            step.step_order,
            step.technique,
            step.paint_id,
            step.paint_name,
            step.notes,
        ))
        return cursor.lastrowid

    def get_step_by_id(self, step_id: int) -> Optional[SchemeStep]:
        rows = self.db.query(f"""
            SELECT id, scheme_id, step_order, technique, paint_id, paint_name, notes
            FROM {self.STEPS_TABLE}
            WHERE id = ?
        """, (step_id,))
        if not rows:
            return None
        return self._row_to_step(rows[0])

    def get_steps_for_scheme(self, scheme_id: int) -> list[SchemeStep]:
        rows = self.db.query(f"""
            SELECT id, scheme_id, step_order, technique, paint_id, paint_name, notes
            FROM {self.STEPS_TABLE}
            WHERE scheme_id = ?
            ORDER BY step_order ASC
        """, (scheme_id,))
        return [self._row_to_step(r) for r in rows]

    def update_step(self, step: SchemeStep) -> bool:
        if step.id is None:
            return False
        cursor = self.db.execute(f"""
            UPDATE {self.STEPS_TABLE}
            SET scheme_id = ?, step_order = ?, technique = ?,
                paint_id = ?, paint_name = ?, notes = ?
            WHERE id = ?
        """, (
            step.scheme_id,
            step.step_order,
            step.technique,
            step.paint_id,
            step.paint_name,
            step.notes,
            step.id,
        ))
        return cursor.rowcount > 0

    def delete_step(self, step_id: int) -> bool:
        cursor = self.db.execute(f"DELETE FROM {self.STEPS_TABLE} WHERE id = ?", (step_id,))
        return cursor.rowcount > 0

    def count_steps_for_scheme(self, scheme_id: int) -> int:
        rows = self.db.query(
            f"SELECT COUNT(*) as cnt FROM {self.STEPS_TABLE} WHERE scheme_id = ?",
            (scheme_id,)
        )
        return rows[0]["cnt"] if rows else 0

    def null_out_paint_id(self, paint_id: int):
        """Set paint_id to NULL on all steps that reference the given paint."""
        self.db.execute(f"""
            UPDATE {self.STEPS_TABLE}
            SET paint_id = NULL
            WHERE paint_id = ?
        """, (paint_id,))

    # ============================================================
    # MODEL LINKS
    # ============================================================

    def add_model_link(self, scheme_id: int, model_id: int):
        try:
            self.db.execute(f"""
                INSERT OR IGNORE INTO {self.LINKS_TABLE} (scheme_id, model_id)
                VALUES (?, ?)
            """, (scheme_id, model_id))
        except Exception as e:
            print(f"[DB WARNING] Failed to add model link: {e}")

    def remove_model_link(self, scheme_id: int, model_id: int):
        self.db.execute(f"""
            DELETE FROM {self.LINKS_TABLE}
            WHERE scheme_id = ? AND model_id = ?
        """, (scheme_id, model_id))

    def get_linked_model_ids(self, scheme_id: int) -> list[int]:
        rows = self.db.query(f"""
            SELECT model_id FROM {self.LINKS_TABLE}
            WHERE scheme_id = ?
            ORDER BY model_id
        """, (scheme_id,))
        return [r["model_id"] for r in rows]

    def get_scheme_ids_for_model(self, model_id: int) -> list[int]:
        rows = self.db.query(f"""
            SELECT scheme_id FROM {self.LINKS_TABLE}
            WHERE model_id = ?
            ORDER BY scheme_id
        """, (model_id,))
        return [r["scheme_id"] for r in rows]

    def remove_all_links_for_model(self, model_id: int):
        self.db.execute(f"DELETE FROM {self.LINKS_TABLE} WHERE model_id = ?", (model_id,))

    # ============================================================
    # MAPPING
    # ============================================================

    def _row_to_scheme(self, row) -> PaintScheme:
        return PaintScheme(
            id=row["id"],
            name=row["name"],
            game_system=row["game_system"] if "game_system" in row.keys() else "",
            faction=row["faction"] if "faction" in row.keys() else "",
            description=row["description"] if "description" in row.keys() else "",
            created_at=row["created_at"] if "created_at" in row.keys() else None,
            updated_at=row["updated_at"] if "updated_at" in row.keys() else None,
        )

    def _row_to_step(self, row) -> SchemeStep:
        return SchemeStep(
            id=row["id"],
            scheme_id=row["scheme_id"],
            step_order=row["step_order"],
            technique=row["technique"],
            paint_id=row["paint_id"] if "paint_id" in row.keys() else None,
            paint_name=row["paint_name"] if "paint_name" in row.keys() else "",
            notes=row["notes"] if "notes" in row.keys() else "",
        )
