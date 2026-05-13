"""
Campaign Tracker v2 — Custom Monster Repository

Per-campaign monster templates.  These live in the database and can be
added to encounters like any game-data monster.  Fields mirror the
EncounterMonster model plus extra stat-block fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CustomMonster:
    id:               int
    campaign_id:      int
    name:             str
    cr:               str          = "1"
    hp:               int          = 10
    ac:               int          = 12
    monster_type:     str          = ""
    size:             str          = ""
    speed:            str          = ""
    initiative_bonus: int          = 0
    str_:             int          = 10
    dex:              int          = 10
    con:              int          = 10
    int_:             int          = 10
    wis:              int          = 10
    cha:              int          = 10
    attacks:          str          = ""
    traits:           str          = ""
    notes:            str          = ""
    created_at:       str          = ""
    updated_at:       str          = ""


class CustomMonsterRepository:
    _T = "campaign_custom_monsters_v2"

    _COLS = (
        "id, campaign_id, name, cr, hp, ac, monster_type, size, speed, "
        "initiative_bonus, str_, dex, con, int_, wis, cha, "
        "attacks, traits, notes, created_at, updated_at"
    )

    def __init__(self, db):
        self._db = db
        self._init_table()

    def _init_table(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._T} (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id      INTEGER NOT NULL,
                name             TEXT    NOT NULL,
                cr               TEXT    NOT NULL DEFAULT '1',
                hp               INTEGER NOT NULL DEFAULT 10,
                ac               INTEGER NOT NULL DEFAULT 12,
                monster_type     TEXT    NOT NULL DEFAULT '',
                size             TEXT    NOT NULL DEFAULT '',
                speed            TEXT    NOT NULL DEFAULT '',
                initiative_bonus INTEGER NOT NULL DEFAULT 0,
                str_             INTEGER NOT NULL DEFAULT 10,
                dex              INTEGER NOT NULL DEFAULT 10,
                con              INTEGER NOT NULL DEFAULT 10,
                int_             INTEGER NOT NULL DEFAULT 10,
                wis              INTEGER NOT NULL DEFAULT 10,
                cha              INTEGER NOT NULL DEFAULT 10,
                attacks          TEXT    NOT NULL DEFAULT '',
                traits           TEXT    NOT NULL DEFAULT '',
                notes            TEXT    NOT NULL DEFAULT '',
                created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self._T}_campaign "
            f"ON {self._T} (campaign_id)"
        )

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_all(self, campaign_id: int,
                query: str = "") -> list[CustomMonster]:
        if query:
            q = f"%{query}%"
            rows = self._db.query(
                f"SELECT {self._COLS} FROM {self._T} "
                f"WHERE campaign_id=? AND (name LIKE ? OR monster_type LIKE ? OR notes LIKE ?) "
                f"ORDER BY name COLLATE NOCASE",
                (campaign_id, q, q, q),
            )
        else:
            rows = self._db.query(
                f"SELECT {self._COLS} FROM {self._T} "
                f"WHERE campaign_id=? ORDER BY name COLLATE NOCASE",
                (campaign_id,),
            )
        return [self._row(r) for r in rows]

    def get(self, monster_id: int) -> CustomMonster | None:
        rows = self._db.query(
            f"SELECT {self._COLS} FROM {self._T} WHERE id=?",
            (monster_id,),
        )
        return self._row(rows[0]) if rows else None

    @staticmethod
    def _row(r) -> CustomMonster:
        return CustomMonster(
            id=r[0], campaign_id=r[1], name=r[2], cr=r[3] or "1",
            hp=r[4] or 10, ac=r[5] or 12,
            monster_type=r[6] or "", size=r[7] or "", speed=r[8] or "",
            initiative_bonus=r[9] or 0,
            str_=r[10] or 10, dex=r[11] or 10, con=r[12] or 10,
            int_=r[13] or 10, wis=r[14] or 10, cha=r[15] or 10,
            attacks=r[16] or "", traits=r[17] or "", notes=r[18] or "",
            created_at=r[19] or "", updated_at=r[20] or "",
        )

    # ── Mutations ─────────────────────────────────────────────────────────────

    def add(self, campaign_id: int, name: str,
            cr: str = "1", hp: int = 10, ac: int = 12,
            monster_type: str = "", size: str = "", speed: str = "",
            initiative_bonus: int = 0,
            str_: int = 10, dex: int = 10, con: int = 10,
            int_: int = 10, wis: int = 10, cha: int = 10,
            attacks: str = "", traits: str = "",
            notes: str = "") -> int:
        cur = self._db.execute(
            f"INSERT INTO {self._T} "
            f"(campaign_id, name, cr, hp, ac, monster_type, size, speed, "
            f"initiative_bonus, str_, dex, con, int_, wis, cha, "
            f"attacks, traits, notes) "
            f"VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (campaign_id, name, cr, hp, ac, monster_type, size, speed,
             initiative_bonus, str_, dex, con, int_, wis, cha,
             attacks, traits, notes),
        )
        return cur.lastrowid

    def update(self, monster_id: int, name: str,
               cr: str = "1", hp: int = 10, ac: int = 12,
               monster_type: str = "", size: str = "", speed: str = "",
               initiative_bonus: int = 0,
               str_: int = 10, dex: int = 10, con: int = 10,
               int_: int = 10, wis: int = 10, cha: int = 10,
               attacks: str = "", traits: str = "",
               notes: str = "") -> bool:
        self._db.execute(
            f"UPDATE {self._T} SET "
            f"name=?, cr=?, hp=?, ac=?, monster_type=?, size=?, speed=?, "
            f"initiative_bonus=?, str_=?, dex=?, con=?, int_=?, wis=?, cha=?, "
            f"attacks=?, traits=?, notes=?, updated_at=datetime('now') WHERE id=?",
            (name, cr, hp, ac, monster_type, size, speed,
             initiative_bonus, str_, dex, con, int_, wis, cha,
             attacks, traits, notes, monster_id),
        )
        return True

    def delete(self, monster_id: int) -> bool:
        self._db.execute(f"DELETE FROM {self._T} WHERE id=?", (monster_id,))
        return True

    def delete_for_campaign(self, campaign_id: int):
        self._db.execute(f"DELETE FROM {self._T} WHERE campaign_id=?", (campaign_id,))
