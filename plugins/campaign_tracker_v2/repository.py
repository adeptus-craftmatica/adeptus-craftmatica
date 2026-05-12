"""
Campaign Tracker v2 — Repository (v2-only tables).

Core campaign data (campaigns, characters, battles, etc.) lives in the v1
CampaignRepository.  This repo owns only the new v2 additions:
  • campaign_compendium_v2  — structured reference entries
"""
from __future__ import annotations

from .models import CompendiumEntry


class CampaignV2Repository:
    _COMP = "campaign_compendium_v2"

    def __init__(self, db):
        self._db = db
        self._init_tables()

    def _init_tables(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._COMP} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                category    TEXT    NOT NULL DEFAULT '',
                title       TEXT    NOT NULL,
                content     TEXT    NOT NULL DEFAULT '',
                tags        TEXT    NOT NULL DEFAULT '',
                source      TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self._COMP}_campaign "
            f"ON {self._COMP} (campaign_id)"
        )

    # ── Compendium ────────────────────────────────────────────────────────────

    def get_compendium(self, campaign_id: int,
                       category: str | None = None) -> list[CompendiumEntry]:
        if category:
            rows = self._db.query(
                f"SELECT id,campaign_id,category,title,content,tags,source,created_at,updated_at "
                f"FROM {self._COMP} WHERE campaign_id=? AND category=? ORDER BY title",
                (campaign_id, category),
            )
        else:
            rows = self._db.query(
                f"SELECT id,campaign_id,category,title,content,tags,source,created_at,updated_at "
                f"FROM {self._COMP} WHERE campaign_id=? ORDER BY category,title",
                (campaign_id,),
            )
        return [CompendiumEntry(*r) for r in rows]

    def get_compendium_categories(self, campaign_id: int) -> list[str]:
        rows = self._db.query(
            f"SELECT DISTINCT category FROM {self._COMP} "
            f"WHERE campaign_id=? ORDER BY category",
            (campaign_id,),
        )
        return [r[0] for r in rows]

    def get_compendium_entry(self, entry_id: int) -> CompendiumEntry | None:
        rows = self._db.query(
            f"SELECT id,campaign_id,category,title,content,tags,source,created_at,updated_at "
            f"FROM {self._COMP} WHERE id=?",
            (entry_id,),
        )
        return CompendiumEntry(*rows[0]) if rows else None

    def add_compendium_entry(self, campaign_id: int, category: str,
                             title: str, content: str = "",
                             tags: str = "", source: str = "") -> int:
        cur = self._db.execute(
            f"INSERT INTO {self._COMP} (campaign_id,category,title,content,tags,source) "
            f"VALUES (?,?,?,?,?,?)",
            (campaign_id, category, title, content, tags, source),
        )
        return cur.lastrowid

    def update_compendium_entry(self, entry_id: int, category: str,
                                title: str, content: str,
                                tags: str, source: str) -> bool:
        self._db.execute(
            f"UPDATE {self._COMP} SET category=?,title=?,content=?,tags=?,source=?,"
            f"updated_at=datetime('now') WHERE id=?",
            (category, title, content, tags, source, entry_id),
        )
        return True

    def delete_compendium_entry(self, entry_id: int) -> bool:
        self._db.execute(f"DELETE FROM {self._COMP} WHERE id=?", (entry_id,))
        return True

    def delete_compendium_for_campaign(self, campaign_id: int):
        self._db.execute(f"DELETE FROM {self._COMP} WHERE campaign_id=?", (campaign_id,))

    def search_compendium(self, campaign_id: int, query: str) -> list[CompendiumEntry]:
        like = f"%{query}%"
        rows = self._db.query(
            f"SELECT id,campaign_id,category,title,content,tags,source,created_at,updated_at "
            f"FROM {self._COMP} "
            f"WHERE campaign_id=? AND (title LIKE ? OR content LIKE ? OR tags LIKE ?) "
            f"ORDER BY category,title",
            (campaign_id, like, like, like),
        )
        return [CompendiumEntry(*r) for r in rows]
