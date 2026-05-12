"""
Army Builder 2.0 — Gallery Repository

Stores per-army image paths and captions in a local SQLite table.
Images are NOT copied into the database — only their absolute paths are
stored.  This keeps the DB small and lets users keep photos wherever
they like on disk.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GalleryEntry:
    id:             int
    army_id:        int
    image_path:     str
    caption:        str
    created_at:     str
    progress_stage: str = ""


class GalleryRepository:
    """Thin persistence layer for army photo galleries."""

    _TABLE = "army_gallery_v2"

    def __init__(self, db):
        self._db = db
        self._init_table()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_table(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._TABLE} (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                army_id        INTEGER NOT NULL,
                image_path     TEXT    NOT NULL,
                caption        TEXT    NOT NULL DEFAULT '',
                created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
                progress_stage TEXT    NOT NULL DEFAULT ''
            )
        """)
        self._db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self._TABLE}_army "
            f"ON {self._TABLE} (army_id)"
        )
        # Migrate: add progress_stage column to existing tables
        try:
            self._db.execute(
                f"ALTER TABLE {self._TABLE} "
                f"ADD COLUMN progress_stage TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass  # Column already exists

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_for_army(self, army_id: int) -> list[GalleryEntry]:
        rows = self._db.query(
            f"SELECT id, army_id, image_path, caption, created_at, progress_stage "
            f"FROM {self._TABLE} WHERE army_id = ? ORDER BY created_at",
            (army_id,),
        )
        return [
            GalleryEntry(
                id=r[0], army_id=r[1], image_path=r[2],
                caption=r[3], created_at=r[4],
                progress_stage=r[5] if len(r) > 5 else "",
            )
            for r in rows
        ]

    def count_for_army(self, army_id: int) -> int:
        rows = self._db.query(
            f"SELECT COUNT(*) FROM {self._TABLE} WHERE army_id = ?",
            (army_id,),
        )
        return rows[0][0] if rows else 0

    # ── Mutations ─────────────────────────────────────────────────────────────

    def add_image(self, army_id: int, image_path: str, caption: str = "",
                  progress_stage: str = "") -> int:
        cur = self._db.execute(
            f"INSERT INTO {self._TABLE} (army_id, image_path, caption, progress_stage)"
            f" VALUES (?,?,?,?)",
            (army_id, image_path, caption, progress_stage),
        )
        return cur.lastrowid

    def update_caption(self, entry_id: int, caption: str) -> bool:
        self._db.execute(
            f"UPDATE {self._TABLE} SET caption = ? WHERE id = ?",
            (caption, entry_id),
        )
        return True

    def update_stage(self, entry_id: int, stage: str) -> bool:
        self._db.execute(
            f"UPDATE {self._TABLE} SET progress_stage = ? WHERE id = ?",
            (stage, entry_id),
        )
        return True

    def update_entry(self, entry_id: int, caption: str, progress_stage: str) -> bool:
        self._db.execute(
            f"UPDATE {self._TABLE} SET caption = ?, progress_stage = ? WHERE id = ?",
            (caption, progress_stage, entry_id),
        )
        return True

    def delete_image(self, entry_id: int) -> bool:
        self._db.execute(
            f"DELETE FROM {self._TABLE} WHERE id = ?",
            (entry_id,),
        )
        return True

    def delete_for_army(self, army_id: int):
        """Remove all gallery entries for a deleted army."""
        self._db.execute(
            f"DELETE FROM {self._TABLE} WHERE army_id = ?",
            (army_id,),
        )
