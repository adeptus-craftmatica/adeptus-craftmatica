"""
Paint Tracker Repository
"""

from __future__ import annotations
from typing import Optional
from .models import Paint, PaintFilter


class PaintRepository:
    TABLE_NAME = "paint_tracker_paints"

    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    # ============================================================
    # SCHEMA
    # ============================================================

    def _ensure_schema(self):
        # Create table (new installs)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                color TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                level TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 🔥 Backward compatibility (add columns if missing)
        self._ensure_quantity_column()
        self._ensure_level_column()
        self._ensure_notes_column()
        self._ensure_favorite_column()
        self._ensure_notify_low_stock_column()

        # Indexes
        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_paint_brand 
            ON {self.TABLE_NAME}(brand)
        """)

        self.db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_paint_type 
            ON {self.TABLE_NAME}(type)
        """)

    def _ensure_quantity_column(self):
        """Add quantity column if it doesn't exist"""
        try:
            columns = self.db.query(f"PRAGMA table_info({self.TABLE_NAME})")
            column_names = [col["name"] for col in columns]

            if "quantity" not in column_names:
                print("[DB] Adding quantity column...")
                self.db.execute(f"""
                    ALTER TABLE {self.TABLE_NAME}
                    ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1
                """)
        except Exception as e:
            print(f"[DB WARNING] Failed to ensure quantity column: {e}")

    def _ensure_level_column(self):
        """Add level column if it doesn't exist"""
        try:
            columns = self.db.query(f"PRAGMA table_info({self.TABLE_NAME})")
            column_names = [col["name"] for col in columns]

            if "level" not in column_names:
                print("[DB] Adding level column...")
                self.db.execute(f"""
                    ALTER TABLE {self.TABLE_NAME}
                    ADD COLUMN level TEXT
                """)
        except Exception as e:
            print(f"[DB WARNING] Failed to ensure level column: {e}")

    def _ensure_notes_column(self):
        """Add notes column if it doesn't exist"""
        try:
            columns = self.db.query(f"PRAGMA table_info({self.TABLE_NAME})")
            column_names = [col["name"] for col in columns]

            if "notes" not in column_names:
                print("[DB] Adding notes column...")
                self.db.execute(f"""
                    ALTER TABLE {self.TABLE_NAME}
                    ADD COLUMN notes TEXT
                """)
        except Exception as e:
            print(f"[DB WARNING] Failed to ensure notes column: {e}")

    def _ensure_favorite_column(self):
        """Add is_favorite column if it doesn't exist (default FALSE)."""
        try:
            columns = self.db.query(f"PRAGMA table_info({self.TABLE_NAME})")
            if "is_favorite" not in [col["name"] for col in columns]:
                print("[DB] Adding is_favorite column...")
                self.db.execute(f"""
                    ALTER TABLE {self.TABLE_NAME}
                    ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0
                """)
        except Exception as e:
            print(f"[DB WARNING] Failed to ensure is_favorite column: {e}")

    def _ensure_notify_low_stock_column(self):
        """Add notify_low_stock column if it doesn't exist (default TRUE)."""
        try:
            columns = self.db.query(f"PRAGMA table_info({self.TABLE_NAME})")
            if "notify_low_stock" not in [col["name"] for col in columns]:
                print("[DB] Adding notify_low_stock column...")
                self.db.execute(f"""
                    ALTER TABLE {self.TABLE_NAME}
                    ADD COLUMN notify_low_stock INTEGER NOT NULL DEFAULT 1
                """)
        except Exception as e:
            print(f"[DB WARNING] Failed to ensure notify_low_stock column: {e}")

    # ============================================================
    # CRUD
    # ============================================================

    def add(self, paint: Paint) -> int:
        cursor = self.db.execute(f"""
            INSERT INTO {self.TABLE_NAME}
                (brand, name, type, color, quantity, level, notes, is_favorite, notify_low_stock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paint.brand.strip(),
            paint.name.strip(),
            paint.paint_type.strip(),
            paint.color.upper(),
            paint.quantity,
            paint.level,
            paint.notes,
            int(paint.is_favorite),
            int(paint.notify_low_stock),
        ))

        return cursor.lastrowid

    def get_by_id(self, paint_id: int) -> Optional[Paint]:
        rows = self.db.query(f"""
            SELECT id, brand, name, type, color, quantity, level, notes,
                   is_favorite, notify_low_stock
            FROM {self.TABLE_NAME}
            WHERE id = ?
        """, (paint_id,))

        if not rows:
            return None

        return self._row_to_paint(rows[0])

    def get_all(self) -> list[Paint]:
        rows = self.db.query(f"""
            SELECT id, brand, name, type, color, quantity, level, notes,
                   is_favorite, notify_low_stock
            FROM {self.TABLE_NAME}
            ORDER BY brand, name
        """)

        return [self._row_to_paint(row) for row in rows]

    def find(self, filter: PaintFilter) -> list[Paint]:
        paints = self.get_all()

        if filter.is_empty():
            return paints

        return [paint for paint in paints if filter.matches(paint)]

    def update(self, paint: Paint) -> bool:
        if paint.id is None:
            return False

        cursor = self.db.execute(f"""
            UPDATE {self.TABLE_NAME}
            SET brand = ?, name = ?, type = ?, color = ?, quantity = ?, level = ?, notes = ?,
                is_favorite = ?, notify_low_stock = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            paint.brand.strip(),
            paint.name.strip(),
            paint.paint_type.strip(),
            paint.color.upper(),
            paint.quantity,
            paint.level,
            paint.notes,
            int(paint.is_favorite),
            int(paint.notify_low_stock),
            paint.id,
        ))

        return cursor.rowcount > 0

    def delete(self, paint_id: int) -> bool:
        cursor = self.db.execute(f"""
            DELETE FROM {self.TABLE_NAME}
            WHERE id = ?
        """, (paint_id,))

        return cursor.rowcount > 0

    def delete_all(self) -> int:
        cursor = self.db.execute(f"DELETE FROM {self.TABLE_NAME}")
        return cursor.rowcount

    # ============================================================
    # QUERIES
    # ============================================================

    def count(self) -> int:
        rows = self.db.query(f"SELECT COUNT(*) as count FROM {self.TABLE_NAME}")
        return rows[0]["count"] if rows else 0

    def get_unique_brands(self) -> list[str]:
        rows = self.db.query(f"""
            SELECT DISTINCT brand 
            FROM {self.TABLE_NAME}
            ORDER BY brand
        """)
        return [row["brand"] for row in rows]

    def get_unique_types(self) -> list[str]:
        rows = self.db.query(f"""
            SELECT DISTINCT type 
            FROM {self.TABLE_NAME}
            ORDER BY type
        """)
        return [row["type"] for row in rows]

    def get_unique_levels(self) -> list[str]:
        rows = self.db.query(f"""
            SELECT DISTINCT level 
            FROM {self.TABLE_NAME}
            WHERE level IS NOT NULL
            ORDER BY level
        """)
        return [row["level"] for row in rows]

    def count_by_brand(self) -> dict[str, int]:
        rows = self.db.query(f"""
            SELECT brand, COUNT(*) as count
            FROM {self.TABLE_NAME}
            GROUP BY brand
            ORDER BY count DESC, brand
        """)
        return {row["brand"]: row["count"] for row in rows}

    def count_by_type(self) -> dict[str, int]:
        rows = self.db.query(f"""
            SELECT type, COUNT(*) as count
            FROM {self.TABLE_NAME}
            GROUP BY type
            ORDER BY count DESC, type
        """)
        return {row["type"]: row["count"] for row in rows}

    def count_by_level(self) -> dict[str, int]:
        rows = self.db.query(f"""
            SELECT level, COUNT(*) as count
            FROM {self.TABLE_NAME}
            WHERE level IS NOT NULL
            GROUP BY level
            ORDER BY count DESC, level
        """)
        return {row["level"]: row["count"] for row in rows}

    # ============================================================
    # MAPPING
    # ============================================================

    def _row_to_paint(self, row) -> Paint:
        keys = row.keys()
        return Paint(
            id=row["id"],
            brand=row["brand"],
            name=row["name"],
            paint_type=row["type"],
            color=row["color"],
            quantity=row["quantity"]         if "quantity"         in keys else 1,
            level=row["level"]               if "level"            in keys else None,
            notes=row["notes"]               if "notes"            in keys else None,
            is_favorite=bool(row["is_favorite"])         if "is_favorite"       in keys else False,
            notify_low_stock=bool(row["notify_low_stock"]) if "notify_low_stock" in keys else True,
        )