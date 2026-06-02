"""
Campaign Tracker v2 — Crusade / Campaign Progression Repository.

Four tables:
  campaign_crusade_force    — campaign-level Crusade/progression metadata
  unit_crusade_record       — per-unit progression (linked to OoB entry)
  campaign_battle_log       — battle history per campaign
  campaign_requisition_log  — RP gain/spend audit log
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

# XP rank thresholds: (xp_threshold, rank_name, honour_slots)
_XP_RANKS = [
    (0,  "Fresh Recruit", 0),
    (5,  "Blooded",       1),
    (10, "Veteran",       2),
    (15, "Elite",         3),
    (20, "Legendary",     4),
]


def _get_rank(xp: int) -> tuple[str, int, int]:
    """Return (rank_name, honour_slots, next_threshold) for the given XP."""
    rank_name    = "Fresh Recruit"
    honour_slots = 0
    next_thresh  = 5
    for i, (thresh, name, slots) in enumerate(_XP_RANKS):
        if xp >= thresh:
            rank_name    = name
            honour_slots = slots
            if i + 1 < len(_XP_RANKS):
                next_thresh = _XP_RANKS[i + 1][0]
            else:
                next_thresh = thresh  # already at max rank
    return rank_name, honour_slots, next_thresh


class CrusadeRepository:

    def __init__(self, db):
        self.db = db
        self._init_tables()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_tables(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS campaign_crusade_force (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id             INTEGER NOT NULL UNIQUE,
                faction                 TEXT    DEFAULT '',
                system_id               TEXT    DEFAULT 'wh40k',
                crusade_points_earned   INTEGER DEFAULT 0,
                crusade_points_spent    INTEGER DEFAULT 0,
                requisition_points      INTEGER DEFAULT 5,
                supply_limit            INTEGER DEFAULT 50,
                battles_fought          INTEGER DEFAULT 0,
                battles_won             INTEGER DEFAULT 0,
                battles_lost            INTEGER DEFAULT 0,
                battles_drawn           INTEGER DEFAULT 0,
                notes                   TEXT    DEFAULT '',
                created_at              TEXT    DEFAULT (datetime('now')),
                updated_at              TEXT    DEFAULT (datetime('now'))
            )
        """)
        self.db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_crusade_force_campaign
                ON campaign_crusade_force (campaign_id)
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS unit_crusade_record (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                oob_entry_id        INTEGER NOT NULL UNIQUE,
                experience_points   INTEGER DEFAULT 0,
                crusade_points      INTEGER DEFAULT 0,
                battles_fought      INTEGER DEFAULT 0,
                battles_survived    INTEGER DEFAULT 0,
                times_destroyed     INTEGER DEFAULT 0,
                is_out_of_action    INTEGER DEFAULT 0,
                honours_json        TEXT    DEFAULT '[]',
                scars_json          TEXT    DEFAULT '[]',
                legendary_name      TEXT    DEFAULT '',
                is_warlord          INTEGER DEFAULT 0,
                warlord_trait       TEXT    DEFAULT '',
                notes               TEXT    DEFAULT '',
                created_at          TEXT    DEFAULT (datetime('now')),
                updated_at          TEXT    DEFAULT (datetime('now'))
            )
        """)
        self.db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unit_crusade_oob
                ON unit_crusade_record (oob_entry_id)
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS campaign_battle_log (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id         INTEGER NOT NULL,
                battle_date         TEXT    DEFAULT '',
                mission             TEXT    DEFAULT '',
                opponent            TEXT    DEFAULT '',
                points_played       INTEGER DEFAULT 0,
                result              TEXT    DEFAULT 'Draw',
                vp_scored           INTEGER DEFAULT 0,
                vp_opponent         INTEGER DEFAULT 0,
                narrative_notes     TEXT    DEFAULT '',
                units_json          TEXT    DEFAULT '[]',
                honours_awarded     TEXT    DEFAULT '[]',
                created_at          TEXT    DEFAULT (datetime('now'))
            )
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_battle_log_campaign
                ON campaign_battle_log (campaign_id)
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS campaign_requisition_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                action      TEXT    NOT NULL,
                rp_change   INTEGER DEFAULT 0,
                description TEXT    DEFAULT '',
                log_date    TEXT    DEFAULT (date('now')),
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_requisition_log_campaign
                ON campaign_requisition_log (campaign_id)
        """)

    # ── Force methods ─────────────────────────────────────────────────────────

    def get_force(self, campaign_id: int) -> dict | None:
        rows = self.db.query(
            "SELECT id, campaign_id, faction, system_id, crusade_points_earned, "
            "crusade_points_spent, requisition_points, supply_limit, battles_fought, "
            "battles_won, battles_lost, battles_drawn, notes, created_at, updated_at "
            "FROM campaign_crusade_force WHERE campaign_id=?",
            (campaign_id,),
        )
        if not rows:
            return None
        return self._force_row_to_dict(rows[0])

    def create_force(self, campaign_id: int, faction: str = '',
                     system_id: str = 'wh40k') -> int:
        cur = self.db.execute(
            "INSERT INTO campaign_crusade_force "
            "(campaign_id, faction, system_id) VALUES (?, ?, ?)",
            (campaign_id, faction, system_id),
        )
        return cur.lastrowid

    def get_or_create_force(self, campaign_id: int, faction: str = '',
                             system_id: str = 'wh40k') -> dict:
        force = self.get_force(campaign_id)
        if force is None:
            self.create_force(campaign_id, faction, system_id)
            force = self.get_force(campaign_id)
        return force or {}

    def update_force(self, campaign_id: int, **kwargs) -> bool:
        allowed = {
            "faction", "system_id", "crusade_points_earned", "crusade_points_spent",
            "requisition_points", "supply_limit", "battles_fought", "battles_won",
            "battles_lost", "battles_drawn", "notes",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [campaign_id]
        self.db.execute(
            f"UPDATE campaign_crusade_force "
            f"SET {set_clause}, updated_at=datetime('now') "
            f"WHERE campaign_id=?",
            values,
        )
        return True

    def increment_force_battles(self, campaign_id: int, result: str):
        """Atomically increment the appropriate battle counter."""
        col = {"Victory": "battles_won", "Defeat": "battles_lost"}.get(result, "battles_drawn")
        self.db.execute(
            f"UPDATE campaign_crusade_force "
            f"SET battles_fought = battles_fought + 1, "
            f"    {col} = {col} + 1, "
            f"    updated_at = datetime('now') "
            f"WHERE campaign_id = ?",
            (campaign_id,),
        )

    def add_requisition(self, campaign_id: int, amount: int,
                        action: str, description: str = '') -> bool:
        self.db.execute(
            "UPDATE campaign_crusade_force "
            "SET requisition_points = requisition_points + ?, "
            "    updated_at = datetime('now') "
            "WHERE campaign_id = ?",
            (amount, campaign_id),
        )
        self.db.execute(
            "INSERT INTO campaign_requisition_log "
            "(campaign_id, action, rp_change, description) VALUES (?, ?, ?, ?)",
            (campaign_id, action, amount, description),
        )
        return True

    def spend_requisition(self, campaign_id: int, amount: int,
                          action: str, description: str = '') -> bool:
        force = self.get_force(campaign_id)
        if force is None:
            return False
        current_rp = force.get("requisition_points", 0)
        if current_rp < amount:
            return False
        self.db.execute(
            "UPDATE campaign_crusade_force "
            "SET requisition_points = requisition_points - ?, "
            "    updated_at = datetime('now') "
            "WHERE campaign_id = ?",
            (amount, campaign_id),
        )
        self.db.execute(
            "INSERT INTO campaign_requisition_log "
            "(campaign_id, action, rp_change, description) VALUES (?, ?, ?, ?)",
            (campaign_id, action, -amount, description),
        )
        return True

    def get_requisition_log(self, campaign_id: int) -> list[dict]:
        rows = self.db.query(
            "SELECT id, campaign_id, action, rp_change, description, log_date, created_at "
            "FROM campaign_requisition_log "
            "WHERE campaign_id=? ORDER BY created_at DESC LIMIT 20",
            (campaign_id,),
        )
        return [
            {
                "id":          r[0],
                "campaign_id": r[1],
                "action":      r[2] or "",
                "rp_change":   int(r[3] or 0),
                "description": r[4] or "",
                "log_date":    r[5] or "",
                "created_at":  r[6] or "",
            }
            for r in rows
        ]

    # ── Unit record methods ───────────────────────────────────────────────────

    def get_unit_record(self, oob_entry_id: int) -> dict | None:
        rows = self.db.query(
            "SELECT id, oob_entry_id, experience_points, crusade_points, "
            "battles_fought, battles_survived, times_destroyed, is_out_of_action, "
            "honours_json, scars_json, legendary_name, is_warlord, warlord_trait, "
            "notes, created_at, updated_at "
            "FROM unit_crusade_record WHERE oob_entry_id=?",
            (oob_entry_id,),
        )
        if not rows:
            return None
        return self._unit_row_to_dict(rows[0])

    def get_or_create_unit_record(self, oob_entry_id: int) -> dict:
        record = self.get_unit_record(oob_entry_id)
        if record is None:
            self.db.execute(
                "INSERT INTO unit_crusade_record (oob_entry_id) VALUES (?)",
                (oob_entry_id,),
            )
            record = self.get_unit_record(oob_entry_id)
        return record or {}

    def update_unit_record(self, oob_entry_id: int, **kwargs) -> bool:
        allowed = {
            "experience_points", "crusade_points", "battles_fought",
            "battles_survived", "times_destroyed", "is_out_of_action",
            "honours_json", "scars_json", "legendary_name",
            "is_warlord", "warlord_trait", "notes",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [oob_entry_id]
        self.db.execute(
            f"UPDATE unit_crusade_record "
            f"SET {set_clause}, updated_at=datetime('now') "
            f"WHERE oob_entry_id=?",
            values,
        )
        return True

    def add_honour(self, oob_entry_id: int, honour_type: str,
                   name: str, effect: str) -> bool:
        record = self.get_or_create_unit_record(oob_entry_id)
        honours = record.get("honours_json", [])
        if not isinstance(honours, list):
            honours = []
        honours.append({"type": honour_type, "name": name, "effect": effect})
        self.db.execute(
            "UPDATE unit_crusade_record SET honours_json=?, updated_at=datetime('now') "
            "WHERE oob_entry_id=?",
            (json.dumps(honours), oob_entry_id),
        )
        return True

    def remove_honour(self, oob_entry_id: int, honour_index: int) -> bool:
        record = self.get_unit_record(oob_entry_id)
        if not record:
            return False
        honours = record.get("honours_json", [])
        if not isinstance(honours, list):
            honours = []
        if 0 <= honour_index < len(honours):
            honours.pop(honour_index)
            self.db.execute(
                "UPDATE unit_crusade_record SET honours_json=?, updated_at=datetime('now') "
                "WHERE oob_entry_id=?",
                (json.dumps(honours), oob_entry_id),
            )
            return True
        return False

    def add_scar(self, oob_entry_id: int, scar_type: str,
                 name: str, effect: str) -> bool:
        record = self.get_or_create_unit_record(oob_entry_id)
        scars = record.get("scars_json", [])
        if not isinstance(scars, list):
            scars = []
        scars.append({"type": scar_type, "name": name, "effect": effect})
        self.db.execute(
            "UPDATE unit_crusade_record SET scars_json=?, updated_at=datetime('now') "
            "WHERE oob_entry_id=?",
            (json.dumps(scars), oob_entry_id),
        )
        return True

    def remove_scar(self, oob_entry_id: int, scar_index: int) -> bool:
        record = self.get_unit_record(oob_entry_id)
        if not record:
            return False
        scars = record.get("scars_json", [])
        if not isinstance(scars, list):
            scars = []
        if 0 <= scar_index < len(scars):
            scars.pop(scar_index)
            self.db.execute(
                "UPDATE unit_crusade_record SET scars_json=?, updated_at=datetime('now') "
                "WHERE oob_entry_id=?",
                (json.dumps(scars), oob_entry_id),
            )
            return True
        return False

    def add_experience(self, oob_entry_id: int, xp: int) -> dict:
        """Increment XP + crusade_points if rank threshold crossed, return updated record."""
        record = self.get_or_create_unit_record(oob_entry_id)
        old_xp = record.get("experience_points", 0)
        new_xp = old_xp + xp

        _, old_slots, _ = _get_rank(old_xp)
        _, new_slots, _ = _get_rank(new_xp)

        # Crusade points increase by the difference in honour_slots
        cp_delta = new_slots - old_slots
        current_cp = record.get("crusade_points", 0)
        new_cp = current_cp + cp_delta

        self.db.execute(
            "UPDATE unit_crusade_record "
            "SET experience_points=?, crusade_points=?, updated_at=datetime('now') "
            "WHERE oob_entry_id=?",
            (new_xp, new_cp, oob_entry_id),
        )
        updated = self.get_unit_record(oob_entry_id)
        return updated or {}

    def get_all_unit_records_for_campaign(self, campaign_id: int) -> list[dict]:
        rows = self.db.query(
            "SELECT ucr.id, ucr.oob_entry_id, ucr.experience_points, ucr.crusade_points, "
            "ucr.battles_fought, ucr.battles_survived, ucr.times_destroyed, "
            "ucr.is_out_of_action, ucr.honours_json, ucr.scars_json, "
            "ucr.legendary_name, ucr.is_warlord, ucr.warlord_trait, ucr.notes, "
            "ucr.created_at, ucr.updated_at, "
            "oob.custom_name, oob.unit_role, oob.faction, oob.points_cost "
            "FROM unit_crusade_record ucr "
            "JOIN campaign_order_of_battle oob ON oob.id = ucr.oob_entry_id "
            "WHERE oob.campaign_id = ? "
            "ORDER BY ucr.crusade_points DESC, ucr.experience_points DESC",
            (campaign_id,),
        )
        result = []
        for r in rows:
            d = self._unit_row_to_dict(r[:16])
            d["custom_name"] = r[16] or ""
            d["unit_role"]   = r[17] or ""
            d["faction"]     = r[18] or ""
            d["points_cost"] = int(r[19] or 0)
            result.append(d)
        return result

    # ── Battle log methods ────────────────────────────────────────────────────

    def add_battle(self, campaign_id: int, battle_date: str = '',
                   mission: str = '', opponent: str = '',
                   points_played: int = 0, result: str = 'Draw',
                   vp_scored: int = 0, vp_opponent: int = 0,
                   narrative_notes: str = '', units_json: str = '[]',
                   honours_awarded: str = '[]') -> int:
        cur = self.db.execute(
            "INSERT INTO campaign_battle_log "
            "(campaign_id, battle_date, mission, opponent, points_played, result, "
            "vp_scored, vp_opponent, narrative_notes, units_json, honours_awarded) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (campaign_id, battle_date, mission, opponent, int(points_played),
             result, int(vp_scored), int(vp_opponent),
             narrative_notes, units_json, honours_awarded),
        )
        return cur.lastrowid

    def get_battles(self, campaign_id: int) -> list[dict]:
        rows = self.db.query(
            "SELECT id, campaign_id, battle_date, mission, opponent, points_played, "
            "result, vp_scored, vp_opponent, narrative_notes, units_json, "
            "honours_awarded, created_at "
            "FROM campaign_battle_log WHERE campaign_id=? "
            "ORDER BY created_at DESC",
            (campaign_id,),
        )
        return [self._battle_row_to_dict(r) for r in rows]

    def get_battle(self, battle_id: int) -> dict | None:
        rows = self.db.query(
            "SELECT id, campaign_id, battle_date, mission, opponent, points_played, "
            "result, vp_scored, vp_opponent, narrative_notes, units_json, "
            "honours_awarded, created_at "
            "FROM campaign_battle_log WHERE id=?",
            (battle_id,),
        )
        if not rows:
            return None
        return self._battle_row_to_dict(rows[0])

    def update_battle(self, battle_id: int, **kwargs) -> bool:
        allowed = {
            "battle_date", "mission", "opponent", "points_played",
            "result", "vp_scored", "vp_opponent", "narrative_notes",
            "units_json", "honours_awarded",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [battle_id]
        self.db.execute(
            f"UPDATE campaign_battle_log SET {set_clause} WHERE id=?",
            values,
        )
        return True

    def delete_battle(self, battle_id: int) -> bool:
        self.db.execute("DELETE FROM campaign_battle_log WHERE id=?", (battle_id,))
        return True

    # ── Row-to-dict helpers ───────────────────────────────────────────────────

    @staticmethod
    def _force_row_to_dict(row) -> dict:
        (id_, campaign_id, faction, system_id, cp_earned, cp_spent,
         rp, supply_limit, battles_fought, battles_won, battles_lost,
         battles_drawn, notes, created_at, updated_at) = row
        return {
            "id":                    id_,
            "campaign_id":           int(campaign_id),
            "faction":               faction or "",
            "system_id":             system_id or "wh40k",
            "crusade_points_earned": int(cp_earned or 0),
            "crusade_points_spent":  int(cp_spent or 0),
            "requisition_points":    int(rp or 0),
            "supply_limit":          int(supply_limit or 50),
            "battles_fought":        int(battles_fought or 0),
            "battles_won":           int(battles_won or 0),
            "battles_lost":          int(battles_lost or 0),
            "battles_drawn":         int(battles_drawn or 0),
            "notes":                 notes or "",
            "created_at":            created_at or "",
            "updated_at":            updated_at or "",
        }

    @staticmethod
    def _unit_row_to_dict(row) -> dict:
        (id_, oob_entry_id, xp, cp, battles_fought, battles_survived,
         times_destroyed, is_out_of_action, honours_json, scars_json,
         legendary_name, is_warlord, warlord_trait, notes,
         created_at, updated_at) = row

        def _parse(v):
            if isinstance(v, list):
                return v
            if not v:
                return []
            try:
                return json.loads(v)
            except Exception:
                return []

        return {
            "id":                id_,
            "oob_entry_id":      int(oob_entry_id),
            "experience_points": int(xp or 0),
            "crusade_points":    int(cp or 0),
            "battles_fought":    int(battles_fought or 0),
            "battles_survived":  int(battles_survived or 0),
            "times_destroyed":   int(times_destroyed or 0),
            "is_out_of_action":  bool(is_out_of_action),
            "honours_json":      _parse(honours_json),
            "scars_json":        _parse(scars_json),
            "legendary_name":    legendary_name or "",
            "is_warlord":        bool(is_warlord),
            "warlord_trait":     warlord_trait or "",
            "notes":             notes or "",
            "created_at":        created_at or "",
            "updated_at":        updated_at or "",
        }

    @staticmethod
    def _battle_row_to_dict(row) -> dict:
        (id_, campaign_id, battle_date, mission, opponent, points_played,
         result, vp_scored, vp_opponent, narrative_notes,
         units_json, honours_awarded, created_at) = row

        def _parse(v):
            if isinstance(v, list):
                return v
            if not v:
                return []
            try:
                return json.loads(v)
            except Exception:
                return []

        return {
            "id":              id_,
            "campaign_id":     int(campaign_id),
            "battle_date":     battle_date or "",
            "mission":         mission or "",
            "opponent":        opponent or "",
            "points_played":   int(points_played or 0),
            "result":          result or "Draw",
            "vp_scored":       int(vp_scored or 0),
            "vp_opponent":     int(vp_opponent or 0),
            "narrative_notes": narrative_notes or "",
            "units_json":      _parse(units_json),
            "honours_awarded": _parse(honours_awarded),
            "created_at":      created_at or "",
        }
