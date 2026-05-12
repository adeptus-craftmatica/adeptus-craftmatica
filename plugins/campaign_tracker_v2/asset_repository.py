"""
Campaign Tracker v2 — Asset Repository

Stores per-campaign file assets: tokens, maps, music, documents, and anything else.
Uses the same DatabaseService.execute() / .query() pattern as gallery_repository.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CampaignAsset:
    id:          int
    campaign_id: int
    name:        str
    file_path:   str
    category:    str = "other"
    tags:        str = ""
    notes:       str = ""
    created_at:  str = ""


class CampaignAssetRepository:
    _TABLE = "campaign_assets_v2"

    def __init__(self, db):
        self._db = db
        self._init_table()

    def _init_table(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._TABLE} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                name        TEXT    NOT NULL,
                file_path   TEXT    NOT NULL,
                category    TEXT    NOT NULL DEFAULT 'other',
                tags        TEXT    NOT NULL DEFAULT '',
                notes       TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self._TABLE}_campaign "
            f"ON {self._TABLE} (campaign_id)"
        )

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_assets(self, campaign_id: int,
                   category: str | None = None) -> list[CampaignAsset]:
        if category and category != "all":
            rows = self._db.query(
                f"SELECT id, campaign_id, name, file_path, category, tags, notes, created_at "
                f"FROM {self._TABLE} WHERE campaign_id=? AND category=? "
                f"ORDER BY name COLLATE NOCASE",
                (campaign_id, category),
            )
        else:
            rows = self._db.query(
                f"SELECT id, campaign_id, name, file_path, category, tags, notes, created_at "
                f"FROM {self._TABLE} WHERE campaign_id=? "
                f"ORDER BY category, name COLLATE NOCASE",
                (campaign_id,),
            )
        return [CampaignAsset(
            id=r[0], campaign_id=r[1], name=r[2], file_path=r[3],
            category=r[4], tags=r[5] or "", notes=r[6] or "",
            created_at=r[7] or "",
        ) for r in rows]

    def get_category_counts(self, campaign_id: int) -> dict[str, int]:
        rows = self._db.query(
            f"SELECT category, COUNT(*) FROM {self._TABLE} "
            f"WHERE campaign_id=? GROUP BY category",
            (campaign_id,),
        )
        return {r[0]: r[1] for r in rows}

    def count_for_campaign(self, campaign_id: int) -> int:
        rows = self._db.query(
            f"SELECT COUNT(*) FROM {self._TABLE} WHERE campaign_id=?",
            (campaign_id,),
        )
        return rows[0][0] if rows else 0

    # ── Mutations ─────────────────────────────────────────────────────────────

    def add_asset(self, campaign_id: int, name: str, file_path: str,
                  category: str = "other", tags: str = "",
                  notes: str = "") -> int:
        cur = self._db.execute(
            f"INSERT INTO {self._TABLE} "
            f"(campaign_id, name, file_path, category, tags, notes) "
            f"VALUES (?,?,?,?,?,?)",
            (campaign_id, name, file_path, category, tags, notes),
        )
        return cur.lastrowid

    def update_asset(self, asset_id: int, name: str, category: str,
                     tags: str = "", notes: str = "") -> bool:
        self._db.execute(
            f"UPDATE {self._TABLE} SET name=?, category=?, tags=?, notes=? WHERE id=?",
            (name, category, tags, notes, asset_id),
        )
        return True

    def delete_asset(self, asset_id: int) -> bool:
        self._db.execute(f"DELETE FROM {self._TABLE} WHERE id=?", (asset_id,))
        return True

    def delete_for_campaign(self, campaign_id: int):
        self._db.execute(
            f"DELETE FROM {self._TABLE} WHERE campaign_id=?", (campaign_id,)
        )
