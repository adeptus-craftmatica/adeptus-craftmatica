"""
Campaign Tracker v2 — Quest Repository

Quests: title / status / priority / category / description / notes / reward /
        quest_giver / location / date_started / date_completed / pinned /
        linked_session_id / tags
Objectives: per-quest checklist items.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.migrations import SchemaManager


@dataclass
class CampaignQuest:
    id:                int
    campaign_id:       int
    title:             str
    status:            str          = "Active"
    priority:          str          = "Medium"
    category:          str          = "Main Quest"
    description:       str          = ""
    notes:             str          = ""
    reward:            str          = ""
    quest_giver:       str          = ""
    location:          str          = ""
    date_started:      str          = ""
    date_completed:    str          = ""
    pinned:            bool         = False
    linked_session_id: Optional[int] = None
    tags:              str          = ""
    created_at:        str          = ""
    updated_at:        str          = ""


@dataclass
class QuestObjective:
    id:        int
    quest_id:  int
    text:      str
    completed: bool = False


class CampaignQuestRepository:
    _Q   = "campaign_quests_v2"
    _OBJ = "campaign_quest_objectives_v2"

    _MIGRATIONS: list[str] = [
        "ALTER TABLE campaign_quests_v2 ADD COLUMN quest_giver       TEXT    NOT NULL DEFAULT ''",
        "ALTER TABLE campaign_quests_v2 ADD COLUMN location          TEXT    NOT NULL DEFAULT ''",
        "ALTER TABLE campaign_quests_v2 ADD COLUMN date_started      TEXT    NOT NULL DEFAULT ''",
        "ALTER TABLE campaign_quests_v2 ADD COLUMN date_completed    TEXT    NOT NULL DEFAULT ''",
        "ALTER TABLE campaign_quests_v2 ADD COLUMN pinned            INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE campaign_quests_v2 ADD COLUMN linked_session_id INTEGER",
        "ALTER TABLE campaign_quests_v2 ADD COLUMN tags              TEXT    NOT NULL DEFAULT ''",
        "ALTER TABLE campaign_quest_objectives_v2 ADD COLUMN failed  INTEGER NOT NULL DEFAULT 0",
    ]

    _COLS = (
        "id,campaign_id,title,status,priority,category,"
        "description,notes,reward,quest_giver,location,"
        "date_started,date_completed,pinned,linked_session_id,"
        "tags,created_at,updated_at"
    )

    def __init__(self, db):
        self._db = db
        self._init_tables()
        SchemaManager(db).migrate("campaign_tracker_v2.quests", self._MIGRATIONS)

    def _init_tables(self):
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._Q} (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id        INTEGER NOT NULL,
                title              TEXT    NOT NULL,
                status             TEXT    NOT NULL DEFAULT 'Active',
                priority           TEXT    NOT NULL DEFAULT 'Medium',
                category           TEXT    NOT NULL DEFAULT 'Main Quest',
                description        TEXT    NOT NULL DEFAULT '',
                notes              TEXT    NOT NULL DEFAULT '',
                reward             TEXT    NOT NULL DEFAULT '',
                quest_giver        TEXT    NOT NULL DEFAULT '',
                location           TEXT    NOT NULL DEFAULT '',
                date_started       TEXT    NOT NULL DEFAULT '',
                date_completed     TEXT    NOT NULL DEFAULT '',
                pinned             INTEGER NOT NULL DEFAULT 0,
                linked_session_id  INTEGER,
                tags               TEXT    NOT NULL DEFAULT '',
                created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self._Q}_campaign "
            f"ON {self._Q} (campaign_id)"
        )
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._OBJ} (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                quest_id  INTEGER NOT NULL,
                text      TEXT    NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self._OBJ}_quest "
            f"ON {self._OBJ} (quest_id)"
        )

    # ── Sorting helpers ───────────────────────────────────────────────────────

    _PRI_ORDER    = "CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END"
    _STATUS_ORDER = (
        "CASE status "
        "WHEN 'Active' THEN 1 WHEN 'On Hold' THEN 2 "
        "WHEN 'Completed' THEN 3 ELSE 4 END"
    )

    # ── Quest queries ─────────────────────────────────────────────────────────

    def get_quests(self, campaign_id: int,
                   status: str | None = None) -> list[CampaignQuest]:
        order = (
            f"pinned DESC, {self._STATUS_ORDER}, "
            f"{self._PRI_ORDER}, title COLLATE NOCASE"
        )
        if status and status != "all":
            rows = self._db.query(
                f"SELECT {self._COLS} FROM {self._Q} "
                f"WHERE campaign_id=? AND status=? ORDER BY {order}",
                (campaign_id, status),
            )
        else:
            rows = self._db.query(
                f"SELECT {self._COLS} FROM {self._Q} "
                f"WHERE campaign_id=? ORDER BY {order}",
                (campaign_id,),
            )
        return [self._row_to_quest(r) for r in rows]

    def get_quest(self, quest_id: int) -> CampaignQuest | None:
        rows = self._db.query(
            f"SELECT {self._COLS} FROM {self._Q} WHERE id=?",
            (quest_id,),
        )
        return self._row_to_quest(rows[0]) if rows else None

    def get_status_counts(self, campaign_id: int) -> dict[str, int]:
        rows = self._db.query(
            f"SELECT status, COUNT(*) FROM {self._Q} "
            f"WHERE campaign_id=? GROUP BY status",
            (campaign_id,),
        )
        return {r[0]: r[1] for r in rows}

    def search_quests(self, campaign_id: int, query: str) -> list[CampaignQuest]:
        q = f"%{query}%"
        order = f"pinned DESC, {self._PRI_ORDER}, title COLLATE NOCASE"
        rows = self._db.query(
            f"SELECT {self._COLS} FROM {self._Q} "
            f"WHERE campaign_id=? AND ("
            f"  title LIKE ? OR description LIKE ? OR "
            f"  quest_giver LIKE ? OR location LIKE ? OR tags LIKE ?"
            f") ORDER BY {order}",
            (campaign_id, q, q, q, q, q),
        )
        return [self._row_to_quest(r) for r in rows]

    @staticmethod
    def _row_to_quest(r) -> CampaignQuest:
        return CampaignQuest(
            id=r[0], campaign_id=r[1], title=r[2], status=r[3],
            priority=r[4], category=r[5],
            description=r[6] or "", notes=r[7] or "", reward=r[8] or "",
            quest_giver=r[9] or "", location=r[10] or "",
            date_started=r[11] or "", date_completed=r[12] or "",
            pinned=bool(r[13]), linked_session_id=r[14],
            tags=r[15] or "",
            created_at=r[16] or "", updated_at=r[17] or "",
        )

    # ── Quest mutations ───────────────────────────────────────────────────────

    def add_quest(self, campaign_id: int, title: str,
                  status: str = "Active", priority: str = "Medium",
                  category: str = "Main Quest",
                  description: str = "", notes: str = "", reward: str = "",
                  quest_giver: str = "", location: str = "",
                  date_started: str = "", date_completed: str = "",
                  linked_session_id: Optional[int] = None,
                  tags: str = "") -> int:
        cur = self._db.execute(
            f"INSERT INTO {self._Q} "
            f"(campaign_id,title,status,priority,category,description,notes,reward,"
            f"quest_giver,location,date_started,date_completed,linked_session_id,tags) "
            f"VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (campaign_id, title, status, priority, category,
             description, notes, reward,
             quest_giver, location, date_started, date_completed,
             linked_session_id, tags),
        )
        return cur.lastrowid

    def update_quest(self, quest_id: int, title: str, status: str,
                     priority: str, category: str,
                     description: str, notes: str, reward: str,
                     quest_giver: str = "", location: str = "",
                     date_started: str = "", date_completed: str = "",
                     linked_session_id: Optional[int] = None,
                     tags: str = "") -> bool:
        self._db.execute(
            f"UPDATE {self._Q} SET "
            f"title=?,status=?,priority=?,category=?,"
            f"description=?,notes=?,reward=?,"
            f"quest_giver=?,location=?,date_started=?,date_completed=?,"
            f"linked_session_id=?,tags=?,"
            f"updated_at=datetime('now') WHERE id=?",
            (title, status, priority, category,
             description, notes, reward,
             quest_giver, location, date_started, date_completed,
             linked_session_id, tags, quest_id),
        )
        return True

    def update_quest_status(self, quest_id: int, status: str) -> bool:
        if status == "Completed":
            # Auto-fill date_completed only if not already set
            self._db.execute(
                f"UPDATE {self._Q} SET status=?, "
                f"date_completed = CASE WHEN date_completed='' "
                f"  THEN date('now') ELSE date_completed END, "
                f"updated_at=datetime('now') WHERE id=?",
                (status, quest_id),
            )
        else:
            self._db.execute(
                f"UPDATE {self._Q} SET status=?,updated_at=datetime('now') WHERE id=?",
                (status, quest_id),
            )
        return True

    def toggle_pin(self, quest_id: int) -> bool:
        rows = self._db.query(
            f"SELECT pinned FROM {self._Q} WHERE id=?", (quest_id,)
        )
        if not rows:
            return False
        new_val = 0 if rows[0][0] else 1
        self._db.execute(
            f"UPDATE {self._Q} SET pinned=?,updated_at=datetime('now') WHERE id=?",
            (new_val, quest_id),
        )
        return bool(new_val)

    def delete_quest(self, quest_id: int) -> bool:
        self._db.execute(f"DELETE FROM {self._OBJ} WHERE quest_id=?", (quest_id,))
        self._db.execute(f"DELETE FROM {self._Q}   WHERE id=?",       (quest_id,))
        return True

    def delete_for_campaign(self, campaign_id: int):
        rows = self._db.query(
            f"SELECT id FROM {self._Q} WHERE campaign_id=?", (campaign_id,)
        )
        for r in rows:
            self._db.execute(f"DELETE FROM {self._OBJ} WHERE quest_id=?", (r[0],))
        self._db.execute(f"DELETE FROM {self._Q} WHERE campaign_id=?", (campaign_id,))

    # ── Objective queries ─────────────────────────────────────────────────────

    def get_objectives(self, quest_id: int) -> list[QuestObjective]:
        rows = self._db.query(
            f"SELECT id,quest_id,text,completed FROM {self._OBJ} "
            f"WHERE quest_id=? ORDER BY id",
            (quest_id,),
        )
        return [QuestObjective(
            id=r[0], quest_id=r[1], text=r[2], completed=bool(r[3])
        ) for r in rows]

    # ── Objective mutations ───────────────────────────────────────────────────

    def add_objective(self, quest_id: int, text: str) -> int:
        cur = self._db.execute(
            f"INSERT INTO {self._OBJ} (quest_id,text,completed) VALUES (?,?,0)",
            (quest_id, text),
        )
        return cur.lastrowid

    def set_objective_completed(self, obj_id: int, completed: bool) -> bool:
        self._db.execute(
            f"UPDATE {self._OBJ} SET completed=? WHERE id=?",
            (1 if completed else 0, obj_id),
        )
        return True

    def delete_objective(self, obj_id: int) -> bool:
        self._db.execute(f"DELETE FROM {self._OBJ} WHERE id=?", (obj_id,))
        return True
