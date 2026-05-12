"""
Campaign Tracker v2 — Gallery Repository

Per-campaign image gallery.  Stores absolute paths + caption + stage.
Uses DatabaseService.execute() / .query() directly.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CampaignGalleryEntry:
    id:          int
    campaign_id: int
    image_path:  str
    caption:     str
    stage:       str = ""   # CampaignGalleryStage constant
    created_at:  str = ""


class CampaignGalleryRepository:
    _TABLE = "campaign_gallery_v2"

    def __init__(self, db):
        self._db = db
        self._init_table()

    def _init_table(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._TABLE} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                image_path  TEXT    NOT NULL,
                caption     TEXT    NOT NULL DEFAULT '',
                stage       TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self._TABLE}_campaign "
            f"ON {self._TABLE} (campaign_id)"
        )
        # migrate: add stage column to older tables
        try:
            self._db.execute(
                f"ALTER TABLE {self._TABLE} ADD COLUMN stage TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_for_campaign(self, campaign_id: int) -> list[CampaignGalleryEntry]:
        rows = self._db.query(
            f"SELECT id, campaign_id, image_path, caption, stage, created_at "
            f"FROM {self._TABLE} WHERE campaign_id = ? ORDER BY created_at",
            (campaign_id,),
        )
        return [
            CampaignGalleryEntry(
                id=r[0], campaign_id=r[1], image_path=r[2],
                caption=r[3], stage=r[4] if len(r) > 4 else "",
                created_at=r[5] if len(r) > 5 else "",
            )
            for r in rows
        ]

    def count_for_campaign(self, campaign_id: int) -> int:
        rows = self._db.query(
            f"SELECT COUNT(*) FROM {self._TABLE} WHERE campaign_id = ?",
            (campaign_id,),
        )
        return rows[0][0] if rows else 0

    # ── Mutations ─────────────────────────────────────────────────────────────

    def add_image(self, campaign_id: int, image_path: str,
                  caption: str = "", stage: str = "") -> int:
        cur = self._db.execute(
            f"INSERT INTO {self._TABLE} (campaign_id, image_path, caption, stage)"
            f" VALUES (?,?,?,?)",
            (campaign_id, image_path, caption, stage),
        )
        return cur.lastrowid

    def update_entry(self, entry_id: int, caption: str, stage: str) -> bool:
        self._db.execute(
            f"UPDATE {self._TABLE} SET caption = ?, stage = ? WHERE id = ?",
            (caption, stage, entry_id),
        )
        return True

    def update_stage(self, entry_id: int, stage: str) -> bool:
        self._db.execute(
            f"UPDATE {self._TABLE} SET stage = ? WHERE id = ?",
            (stage, entry_id),
        )
        return True

    def delete_image(self, entry_id: int) -> bool:
        self._db.execute(
            f"DELETE FROM {self._TABLE} WHERE id = ?",
            (entry_id,),
        )
        return True

    def delete_for_campaign(self, campaign_id: int):
        self._db.execute(
            f"DELETE FROM {self._TABLE} WHERE campaign_id = ?",
            (campaign_id,),
        )
