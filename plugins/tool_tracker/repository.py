"""
Tool Tracker — Repository (SQLite persistence)
"""
from __future__ import annotations

from typing import Optional

from .models import Tool, ToolFilter

_TABLE = "tool_tracker_tools"


class ToolRepository:
    def __init__(self, db):
        self._db = db
        self._ensure_schema()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _ensure_schema(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT    NOT NULL,
                tool_type TEXT    NOT NULL,
                brand     TEXT    DEFAULT '',
                condition TEXT    DEFAULT 'Good',
                quantity  INTEGER DEFAULT 1,
                notes     TEXT
            )
        """)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, tool: Tool) -> int:
        cursor = self._db.execute(
            f"INSERT INTO {_TABLE} (name, tool_type, brand, condition, quantity, notes) "
            f"VALUES (?, ?, ?, ?, ?, ?)",
            (tool.name, tool.tool_type, tool.brand or "",
             tool.condition, tool.quantity, tool.notes),
        )
        return cursor.lastrowid

    def get_by_id(self, tool_id: int) -> Optional[Tool]:
        rows = self._db.query(
            f"SELECT * FROM {_TABLE} WHERE id = ?", (tool_id,)
        )
        return self._row_to_tool(rows[0]) if rows else None

    def get_all(self) -> list[Tool]:
        rows = self._db.query(
            f"SELECT * FROM {_TABLE} ORDER BY tool_type, name"
        )
        return [self._row_to_tool(r) for r in rows]

    def update(self, tool: Tool) -> bool:
        cursor = self._db.execute(
            f"UPDATE {_TABLE} SET name=?, tool_type=?, brand=?, "
            f"condition=?, quantity=?, notes=? WHERE id=?",
            (tool.name, tool.tool_type, tool.brand or "",
             tool.condition, tool.quantity, tool.notes, tool.id),
        )
        return cursor.rowcount > 0

    def delete(self, tool_id: int) -> bool:
        cursor = self._db.execute(
            f"DELETE FROM {_TABLE} WHERE id = ?", (tool_id,)
        )
        return cursor.rowcount > 0

    def delete_all(self) -> int:
        cursor = self._db.execute(f"DELETE FROM {_TABLE}")
        return cursor.rowcount

    # ── Queries ───────────────────────────────────────────────────────────────

    def find(self, f: ToolFilter) -> list[Tool]:
        clauses, params = [], []

        if f.search_text:
            q = f"%{f.search_text.lower()}%"
            clauses.append("(LOWER(name) LIKE ? OR LOWER(brand) LIKE ? OR LOWER(notes) LIKE ?)")
            params += [q, q, q]
        if f.tool_type:
            clauses.append("tool_type = ?")
            params.append(f.tool_type)
        if f.brand:
            clauses.append("LOWER(brand) = ?")
            params.append(f.brand.lower())
        if f.condition:
            clauses.append("condition = ?")
            params.append(f.condition)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._db.query(
            f"SELECT * FROM {_TABLE} {where} ORDER BY tool_type, name",
            tuple(params),
        )
        return [self._row_to_tool(r) for r in rows]

    def count(self) -> int:
        rows = self._db.query(f"SELECT COUNT(*) FROM {_TABLE}")
        return rows[0][0] if rows else 0

    def get_unique_types(self) -> list[str]:
        rows = self._db.query(
            f"SELECT DISTINCT tool_type FROM {_TABLE} ORDER BY tool_type"
        )
        return [r[0] for r in rows if r[0]]

    def get_unique_brands(self) -> list[str]:
        rows = self._db.query(
            f"SELECT DISTINCT brand FROM {_TABLE} ORDER BY brand"
        )
        return [r[0] for r in rows if r[0]]

    def count_by_type(self) -> dict[str, int]:
        rows = self._db.query(
            f"SELECT tool_type, COUNT(*) FROM {_TABLE} GROUP BY tool_type"
        )
        return {r[0]: r[1] for r in rows}

    def count_by_condition(self) -> dict[str, int]:
        rows = self._db.query(
            f"SELECT condition, COUNT(*) FROM {_TABLE} GROUP BY condition"
        )
        return {r[0]: r[1] for r in rows}

    def count_by_brand(self) -> dict[str, int]:
        rows = self._db.query(
            f"SELECT brand, COUNT(*) FROM {_TABLE} WHERE brand != '' GROUP BY brand"
        )
        return {r[0]: r[1] for r in rows}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_tool(row) -> Tool:
        return Tool(
            id        = row[0],
            name      = row[1],
            tool_type = row[2],
            brand     = row[3] or "",
            condition = row[4] or "Good",
            quantity  = row[5] or 1,
            notes     = row[6],
        )


# ── Auto-registration ──────────────────────────────────────────────────────────

def register(context):
    print("[TOOL_TRACKER] Registering repository...")
    db   = context.services.get("db")
    repo = ToolRepository(db)
    context.services.register("tool_repository", repo, override=True)
    print("[TOOL_TRACKER] Repository registered")
    return repo
