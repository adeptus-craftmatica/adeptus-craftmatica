"""
Materials Tracker — Repository (SQLite persistence)
"""
from __future__ import annotations

from typing import Optional

from .models import Material, MaterialFilter

_TABLE = "materials_tracker_materials"


class MaterialRepository:
    def __init__(self, db):
        self._db = db
        self._ensure_schema()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _ensure_schema(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                material_type TEXT    NOT NULL,
                brand         TEXT    DEFAULT '',
                color         TEXT    DEFAULT '',
                stock         TEXT    DEFAULT 'Good',
                quantity      INTEGER DEFAULT 1,
                notes         TEXT
            )
        """)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, material: Material) -> int:
        cursor = self._db.execute(
            f"INSERT INTO {_TABLE} (name, material_type, brand, color, stock, quantity, notes) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (material.name, material.material_type, material.brand or "",
             material.color or "", material.stock, material.quantity, material.notes),
        )
        return cursor.lastrowid

    def get_by_id(self, material_id: int) -> Optional[Material]:
        rows = self._db.query(
            f"SELECT * FROM {_TABLE} WHERE id = ?", (material_id,)
        )
        return self._row_to_material(rows[0]) if rows else None

    def get_all(self) -> list[Material]:
        rows = self._db.query(
            f"SELECT * FROM {_TABLE} ORDER BY material_type, name"
        )
        return [self._row_to_material(r) for r in rows]

    def update(self, material: Material) -> bool:
        cursor = self._db.execute(
            f"UPDATE {_TABLE} SET name=?, material_type=?, brand=?, color=?, "
            f"stock=?, quantity=?, notes=? WHERE id=?",
            (material.name, material.material_type, material.brand or "",
             material.color or "", material.stock, material.quantity,
             material.notes, material.id),
        )
        return cursor.rowcount > 0

    def delete(self, material_id: int) -> bool:
        cursor = self._db.execute(
            f"DELETE FROM {_TABLE} WHERE id = ?", (material_id,)
        )
        return cursor.rowcount > 0

    def delete_all(self) -> int:
        cursor = self._db.execute(f"DELETE FROM {_TABLE}")
        return cursor.rowcount

    # ── Queries ───────────────────────────────────────────────────────────────

    def find(self, f: MaterialFilter) -> list[Material]:
        clauses, params = [], []

        if f.search_text:
            q = f"%{f.search_text.lower()}%"
            clauses.append(
                "(LOWER(name) LIKE ? OR LOWER(brand) LIKE ? "
                "OR LOWER(color) LIKE ? OR LOWER(notes) LIKE ?)"
            )
            params += [q, q, q, q]
        if f.material_type:
            clauses.append("material_type = ?")
            params.append(f.material_type)
        if f.brand:
            clauses.append("LOWER(brand) = ?")
            params.append(f.brand.lower())
        if f.stock:
            clauses.append("stock = ?")
            params.append(f.stock)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._db.query(
            f"SELECT * FROM {_TABLE} {where} ORDER BY material_type, name",
            tuple(params),
        )
        return [self._row_to_material(r) for r in rows]

    def count(self) -> int:
        rows = self._db.query(f"SELECT COUNT(*) FROM {_TABLE}")
        return rows[0][0] if rows else 0

    def get_unique_types(self) -> list[str]:
        rows = self._db.query(
            f"SELECT DISTINCT material_type FROM {_TABLE} ORDER BY material_type"
        )
        return [r[0] for r in rows if r[0]]

    def get_unique_brands(self) -> list[str]:
        rows = self._db.query(
            f"SELECT DISTINCT brand FROM {_TABLE} ORDER BY brand"
        )
        return [r[0] for r in rows if r[0]]

    def count_by_type(self) -> dict[str, int]:
        rows = self._db.query(
            f"SELECT material_type, COUNT(*) FROM {_TABLE} GROUP BY material_type"
        )
        return {r[0]: r[1] for r in rows}

    def count_by_stock(self) -> dict[str, int]:
        rows = self._db.query(
            f"SELECT stock, COUNT(*) FROM {_TABLE} GROUP BY stock"
        )
        return {r[0]: r[1] for r in rows}

    def count_by_brand(self) -> dict[str, int]:
        rows = self._db.query(
            f"SELECT brand, COUNT(*) FROM {_TABLE} WHERE brand != '' GROUP BY brand"
        )
        return {r[0]: r[1] for r in rows}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_material(row) -> Material:
        return Material(
            id            = row[0],
            name          = row[1],
            material_type = row[2],
            brand         = row[3] or "",
            color         = row[4] or "",
            stock         = row[5] or "Good",
            quantity      = row[6] or 1,
            notes         = row[7],
        )


# ── Auto-registration ──────────────────────────────────────────────────────────

def register(context):
    print("[MATERIALS_TRACKER] Registering repository...")
    db   = context.services.get("db")
    repo = MaterialRepository(db)
    context.services.register("material_repository", repo, override=True)
    print("[MATERIALS_TRACKER] Repository registered")
    return repo
