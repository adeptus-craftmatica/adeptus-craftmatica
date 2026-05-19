"""
Model Tracker Repository

SQLite persistence layer for models and their paint links.
"""
from __future__ import annotations

from typing import Optional

from core.migrations import SchemaManager
from .models import Model, ModelFilter


class ModelRepository:
    TABLE        = "model_tracker_models"
    LINK_TABLE   = "model_tracker_paint_links"
    IMAGES_TABLE = "model_tracker_images"

    _MIGRATIONS: list[str] = [
        "ALTER TABLE model_tracker_models ADD COLUMN image_path TEXT",
    ]

    def __init__(self, db):
        self.db = db
        self._ensure_schema()
        SchemaManager(db).migrate("model_tracker", self._MIGRATIONS)

    # ============================================================
    # SCHEMA
    # ============================================================

    def _ensure_schema(self):
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                game_system TEXT NOT NULL,
                faction     TEXT NOT NULL,
                model_type  TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'Unassembled',
                scale       TEXT DEFAULT '',
                quantity    INTEGER NOT NULL DEFAULT 1,
                notes       TEXT,
                image_path  TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Cross-plugin paint links (survives paint_tracker not being loaded)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.LINK_TABLE} (
                model_id  INTEGER NOT NULL,
                paint_id  INTEGER NOT NULL,
                PRIMARY KEY (model_id, paint_id)
            )
        """)

        # Per-model image gallery (multiple photos per model)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.IMAGES_TABLE} (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id   INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            )
        """)

        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_model_game_system
            ON {self.TABLE}(game_system)
        """)

        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_model_status
            ON {self.TABLE}(status)
        """)

        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_model_faction
            ON {self.TABLE}(faction)
        """)

    # ============================================================
    # CRUD
    # ============================================================

    def add(self, model: Model) -> int:
        cursor = self.db.execute(f"""
            INSERT INTO {self.TABLE} (name, game_system, faction, model_type, status, scale, quantity, notes, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            model.name.strip(),
            model.game_system.strip(),
            model.faction.strip(),
            model.model_type.strip(),
            model.status,
            model.scale.strip() if model.scale else "",
            model.quantity,
            model.notes,
            model.image_path,
        ))
        model_id = cursor.lastrowid
        self._save_links(model_id, model.linked_paint_ids)
        return model_id

    def get_by_id(self, model_id: int) -> Optional[Model]:
        rows = self.db.query(f"""
            SELECT id, name, game_system, faction, model_type, status, scale, quantity, notes, image_path
            FROM {self.TABLE} WHERE id = ?
        """, (model_id,))
        if not rows:
            return None
        m = self._row_to_model(rows[0])
        m.linked_paint_ids = self._get_links(model_id)
        return m

    def get_all(self) -> list[Model]:
        rows = self.db.query(f"""
            SELECT id, name, game_system, faction, model_type, status, scale, quantity, notes, image_path
            FROM {self.TABLE}
            ORDER BY game_system, faction, name
        """)
        models = [self._row_to_model(row) for row in rows]
        for m in models:
            m.linked_paint_ids = self._get_links(m.id)
        return models

    def find(self, f: ModelFilter) -> list[Model]:
        models = self.get_all()
        if f.is_empty():
            return models
        return [m for m in models if f.matches(m)]

    def update(self, model: Model) -> bool:
        if model.id is None:
            return False
        cursor = self.db.execute(f"""
            UPDATE {self.TABLE}
            SET name = ?, game_system = ?, faction = ?, model_type = ?,
                status = ?, scale = ?, quantity = ?, notes = ?, image_path = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            model.name.strip(),
            model.game_system.strip(),
            model.faction.strip(),
            model.model_type.strip(),
            model.status,
            model.scale.strip() if model.scale else "",
            model.quantity,
            model.notes,
            model.image_path,
            model.id,
        ))
        self._save_links(model.id, model.linked_paint_ids)
        return cursor.rowcount > 0

    def delete(self, model_id: int) -> bool:
        self.db.execute(f"DELETE FROM {self.LINK_TABLE}   WHERE model_id = ?", (model_id,))
        self.db.execute(f"DELETE FROM {self.IMAGES_TABLE} WHERE model_id = ?", (model_id,))
        cursor = self.db.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (model_id,))
        return cursor.rowcount > 0

    def delete_all(self) -> int:
        self.db.execute(f"DELETE FROM {self.LINK_TABLE}")
        cursor = self.db.execute(f"DELETE FROM {self.TABLE}")
        return cursor.rowcount

    # ============================================================
    # QUERIES
    # ============================================================

    def count(self) -> int:
        rows = self.db.query(f"SELECT COUNT(*) as c FROM {self.TABLE}")
        return rows[0]["c"] if rows else 0

    def get_unique_game_systems(self) -> list[str]:
        rows = self.db.query(f"SELECT DISTINCT game_system FROM {self.TABLE} ORDER BY game_system")
        return [r["game_system"] for r in rows]

    def get_unique_factions(self, game_system: Optional[str] = None) -> list[str]:
        if game_system:
            rows = self.db.query(
                f"SELECT DISTINCT faction FROM {self.TABLE} WHERE game_system = ? ORDER BY faction",
                (game_system,),
            )
        else:
            rows = self.db.query(f"SELECT DISTINCT faction FROM {self.TABLE} ORDER BY faction")
        return [r["faction"] for r in rows]

    def get_unique_types(self) -> list[str]:
        rows = self.db.query(f"SELECT DISTINCT model_type FROM {self.TABLE} ORDER BY model_type")
        return [r["model_type"] for r in rows]

    def count_by_status(self) -> dict[str, int]:
        rows = self.db.query(f"""
            SELECT status, COUNT(*) as c FROM {self.TABLE} GROUP BY status ORDER BY c DESC
        """)
        return {r["status"]: r["c"] for r in rows}

    def count_by_game_system(self) -> dict[str, int]:
        rows = self.db.query(f"""
            SELECT game_system, COUNT(*) as c FROM {self.TABLE} GROUP BY game_system ORDER BY c DESC
        """)
        return {r["game_system"]: r["c"] for r in rows}

    def count_by_faction(self) -> dict[str, int]:
        rows = self.db.query(f"""
            SELECT faction, COUNT(*) as c FROM {self.TABLE} GROUP BY faction ORDER BY c DESC
        """)
        return {r["faction"]: r["c"] for r in rows}

    # ============================================================
    # PAINT LINKS (cross-plugin)
    # ============================================================

    def _get_links(self, model_id: int) -> list[int]:
        rows = self.db.query(
            f"SELECT paint_id FROM {self.LINK_TABLE} WHERE model_id = ?",
            (model_id,),
        )
        return [r["paint_id"] for r in rows]

    def _save_links(self, model_id: int, paint_ids: list[int]):
        self.db.execute(f"DELETE FROM {self.LINK_TABLE} WHERE model_id = ?", (model_id,))
        for pid in paint_ids:
            try:
                self.db.execute(
                    f"INSERT OR IGNORE INTO {self.LINK_TABLE} (model_id, paint_id) VALUES (?, ?)",
                    (model_id, pid),
                )
            except Exception:
                pass

    def remove_paint_link_everywhere(self, paint_id: int):
        """Called when a paint is deleted — removes all links to that paint."""
        self.db.execute(f"DELETE FROM {self.LINK_TABLE} WHERE paint_id = ?", (paint_id,))

    def get_models_using_paint(self, paint_id: int) -> list[int]:
        """Returns model IDs that reference a given paint."""
        rows = self.db.query(
            f"SELECT model_id FROM {self.LINK_TABLE} WHERE paint_id = ?",
            (paint_id,),
        )
        return [r["model_id"] for r in rows]

    # ============================================================
    # IMAGE GALLERY
    # ============================================================

    def get_images(self, model_id: int) -> list[dict]:
        """Return all images for a model, ordered by sort_order."""
        rows = self.db.query(
            f"SELECT id, image_path, sort_order FROM {self.IMAGES_TABLE} "
            f"WHERE model_id = ? ORDER BY sort_order, id",
            (model_id,),
        )
        return [{"id": r["id"], "image_path": r["image_path"], "sort_order": r["sort_order"]} for r in rows]

    def add_image(self, model_id: int, path: str) -> int:
        """Add an image path for a model (deduplicates). Returns the row id."""
        existing = self.db.query(
            f"SELECT id FROM {self.IMAGES_TABLE} WHERE model_id = ? AND image_path = ?",
            (model_id, path),
        )
        if existing:
            return existing[0]["id"]
        order_rows = self.db.query(
            f"SELECT COALESCE(MAX(sort_order), -1) + 1 AS nxt FROM {self.IMAGES_TABLE} WHERE model_id = ?",
            (model_id,),
        )
        next_order = order_rows[0]["nxt"] if order_rows else 0
        cursor = self.db.execute(
            f"INSERT INTO {self.IMAGES_TABLE} (model_id, image_path, sort_order) VALUES (?, ?, ?)",
            (model_id, path, next_order),
        )
        return cursor.lastrowid

    def delete_image(self, image_id: int) -> bool:
        cursor = self.db.execute(f"DELETE FROM {self.IMAGES_TABLE} WHERE id = ?", (image_id,))
        return cursor.rowcount > 0

    # ============================================================
    # MAPPING
    # ============================================================

    def _row_to_model(self, row) -> Model:
        keys = row.keys()
        return Model(
            id=row["id"],
            name=row["name"],
            game_system=row["game_system"],
            faction=row["faction"],
            model_type=row["model_type"],
            status=row["status"],
            scale=row["scale"] if "scale" in keys else "",
            quantity=row["quantity"] if "quantity" in keys else 1,
            notes=row["notes"] if "notes" in keys else None,
            image_path=row["image_path"] if "image_path" in keys else None,
            linked_paint_ids=[],
        )
