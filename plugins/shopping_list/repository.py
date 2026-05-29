"""Shopping List — SQLite repository."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

from .models import ShoppingList, ShoppingSection, ShoppingItem

_DDL = """
CREATE TABLE IF NOT EXISTS shopping_lists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shopping_sections (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id            INTEGER NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
    title              TEXT NOT NULL,
    source_type        TEXT DEFAULT 'custom',
    source_project_id  TEXT DEFAULT '',
    sort_order         INTEGER DEFAULT 0,
    collapsed          INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS shopping_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id          INTEGER NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
    section_id       INTEGER NOT NULL REFERENCES shopping_sections(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    category         TEXT DEFAULT 'Other',
    quantity         REAL DEFAULT 1.0,
    unit             TEXT DEFAULT '',
    notes            TEXT DEFAULT '',
    purchased        INTEGER DEFAULT 0,
    source_plugin    TEXT DEFAULT '',
    source_item_id   TEXT DEFAULT '',
    project_id       TEXT DEFAULT '',
    created_at       TEXT DEFAULT (datetime('now')),
    updated_at       TEXT DEFAULT (datetime('now'))
);
"""


class ShoppingRepository:
    def __init__(self, db):
        self._db = db
        self._ensure_schema()

    def _ensure_schema(self):
        try:
            for stmt in _DDL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    self._db.execute(stmt)
        except Exception as e:
            log.error(f"[SHOPPING] Schema error: {e}")

    # ── Lists ─────────────────────────────────────────────────────────────────

    def create_list(self, name: str) -> int:
        cur = self._db.execute(
            "INSERT INTO shopping_lists (name) VALUES (?)", (name,)
        )
        return cur.lastrowid

    def get_all_lists(self) -> list[ShoppingList]:
        rows = self._db.query("SELECT * FROM shopping_lists ORDER BY id ASC")
        return [ShoppingList(name=r["name"], id=r["id"],
                             created_at=r["created_at"] or "",
                             updated_at=r["updated_at"] or "") for r in rows]

    def get_list(self, list_id: int) -> Optional[ShoppingList]:
        rows = self._db.query("SELECT * FROM shopping_lists WHERE id = ?", (list_id,))
        if not rows:
            return None
        r = rows[0]
        return ShoppingList(name=r["name"], id=r["id"],
                            created_at=r["created_at"] or "",
                            updated_at=r["updated_at"] or "")

    def rename_list(self, list_id: int, name: str):
        self._db.execute(
            "UPDATE shopping_lists SET name=?, updated_at=datetime('now') WHERE id=?",
            (name, list_id)
        )

    def delete_list(self, list_id: int):
        self._db.execute("DELETE FROM shopping_lists WHERE id=?", (list_id,))

    # ── Sections ──────────────────────────────────────────────────────────────

    def create_section(self, list_id: int, title: str,
                       source_type: str = "custom",
                       source_project_id: str = "",
                       sort_order: int = 0) -> int:
        cur = self._db.execute(
            """INSERT INTO shopping_sections
               (list_id, title, source_type, source_project_id, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (list_id, title, source_type, source_project_id, sort_order)
        )
        return cur.lastrowid

    def get_sections(self, list_id: int) -> list[ShoppingSection]:
        rows = self._db.query(
            "SELECT * FROM shopping_sections WHERE list_id=? ORDER BY sort_order ASC, id ASC",
            (list_id,)
        )
        return [ShoppingSection(
            title=r["title"], list_id=r["list_id"],
            source_type=r["source_type"] or "custom",
            source_project_id=r["source_project_id"] or "",
            sort_order=r["sort_order"] or 0,
            collapsed=bool(r["collapsed"]),
            id=r["id"],
        ) for r in rows]

    def rename_section(self, section_id: int, title: str):
        self._db.execute(
            "UPDATE shopping_sections SET title=? WHERE id=?", (title, section_id)
        )

    def delete_section(self, section_id: int):
        self._db.execute("DELETE FROM shopping_sections WHERE id=?", (section_id,))

    def set_section_collapsed(self, section_id: int, collapsed: bool):
        self._db.execute(
            "UPDATE shopping_sections SET collapsed=? WHERE id=?",
            (int(collapsed), section_id)
        )

    # ── Items ─────────────────────────────────────────────────────────────────

    def add_item(self, item: ShoppingItem) -> int:
        cur = self._db.execute(
            """INSERT INTO shopping_items
               (list_id, section_id, name, category, quantity, unit, notes,
                purchased, source_plugin, source_item_id, project_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.list_id, item.section_id, item.name, item.category,
             item.quantity, item.unit, item.notes, int(item.purchased),
             item.source_plugin, item.source_item_id, item.project_id)
        )
        return cur.lastrowid

    def get_items(self, list_id: int, section_id: Optional[int] = None) -> list[ShoppingItem]:
        if section_id is not None:
            rows = self._db.query(
                "SELECT * FROM shopping_items WHERE list_id=? AND section_id=? ORDER BY id ASC",
                (list_id, section_id)
            )
        else:
            rows = self._db.query(
                "SELECT * FROM shopping_items WHERE list_id=? ORDER BY id ASC", (list_id,)
            )
        return [self._row_to_item(r) for r in rows]

    def update_item(self, item: ShoppingItem):
        self._db.execute(
            """UPDATE shopping_items SET
               name=?, category=?, quantity=?, unit=?, notes=?,
               purchased=?, section_id=?, source_plugin=?, source_item_id=?,
               project_id=?, updated_at=datetime('now')
               WHERE id=?""",
            (item.name, item.category, item.quantity, item.unit, item.notes,
             int(item.purchased), item.section_id, item.source_plugin,
             item.source_item_id, item.project_id, item.id)
        )

    def set_purchased(self, item_id: int, purchased: bool):
        self._db.execute(
            "UPDATE shopping_items SET purchased=?, updated_at=datetime('now') WHERE id=?",
            (int(purchased), item_id)
        )

    def delete_item(self, item_id: int):
        self._db.execute("DELETE FROM shopping_items WHERE id=?", (item_id,))

    def delete_purchased(self, list_id: int):
        self._db.execute(
            "DELETE FROM shopping_items WHERE list_id=? AND purchased=1", (list_id,)
        )

    def clear_list(self, list_id: int):
        self._db.execute("DELETE FROM shopping_items WHERE list_id=?", (list_id,))

    def find_duplicate(self, list_id: int, name: str,
                       section_id: int) -> Optional[ShoppingItem]:
        rows = self._db.query(
            """SELECT * FROM shopping_items
               WHERE list_id=? AND section_id=? AND lower(name)=lower(?) LIMIT 1""",
            (list_id, section_id, name)
        )
        return self._row_to_item(rows[0]) if rows else None

    def merge_quantity(self, item_id: int, extra: float):
        self._db.execute(
            "UPDATE shopping_items SET quantity=quantity+?, updated_at=datetime('now') WHERE id=?",
            (extra, item_id)
        )

    def _row_to_item(self, r) -> ShoppingItem:
        return ShoppingItem(
            id=r["id"], list_id=r["list_id"], section_id=r["section_id"],
            name=r["name"], category=r["category"] or "Other",
            quantity=float(r["quantity"] or 1),
            unit=r["unit"] or "", notes=r["notes"] or "",
            purchased=bool(r["purchased"]),
            source_plugin=r["source_plugin"] or "",
            source_item_id=r["source_item_id"] or "",
            project_id=r["project_id"] or "",
            created_at=r["created_at"] or "",
            updated_at=r["updated_at"] or "",
        )
