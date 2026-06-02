"""
Map Repository — Campaign Tracker v2.

Three tables:
  campaign_maps        — map metadata, grid config, fog state
  map_tokens           — tokens placed on a specific map
  map_token_library    — reusable token templates per campaign
"""
from __future__ import annotations

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_map(row: dict) -> dict:
    raw = row.get("fog_data", "[]")
    try:
        row["fog_data"] = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    except Exception:
        row["fog_data"] = []
    row["grid_enabled"] = bool(row.get("grid_enabled", 1))
    row["fog_enabled"]  = bool(row.get("fog_enabled",  0))
    return row


def _parse_token(row: dict) -> dict:
    raw = row.get("conditions_json", "[]")
    try:
        row["conditions_json"] = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    except Exception:
        row["conditions_json"] = []
    row["visible"]       = bool(row.get("visible", 1))
    row["label_visible"] = bool(row.get("label_visible", 1))
    return row


class MapRepository:

    def __init__(self, db):
        self._db = db
        self._init_tables()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_tables(self):
        try:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS campaign_maps (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id   INTEGER NOT NULL,
                    name          TEXT    NOT NULL DEFAULT 'Untitled Map',
                    image_path    TEXT    DEFAULT '',
                    grid_enabled  INTEGER DEFAULT 1,
                    grid_size     INTEGER DEFAULT 50,
                    grid_cols     INTEGER DEFAULT 0,
                    grid_rows     INTEGER DEFAULT 0,
                    grid_color    TEXT    DEFAULT '#ffffff',
                    grid_opacity  REAL    DEFAULT 0.3,
                    grid_offset_x INTEGER DEFAULT 0,
                    grid_offset_y INTEGER DEFAULT 0,
                    zoom_level    REAL    DEFAULT 1.0,
                    pan_x         REAL    DEFAULT 0.0,
                    pan_y         REAL    DEFAULT 0.0,
                    fog_enabled   INTEGER DEFAULT 0,
                    fog_data      TEXT    DEFAULT '[]',
                    notes         TEXT    DEFAULT '',
                    created_at    TEXT    DEFAULT (datetime('now')),
                    updated_at    TEXT    DEFAULT (datetime('now'))
                )
            """)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS map_tokens (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    map_id          INTEGER NOT NULL,
                    name            TEXT    DEFAULT '',
                    image_path      TEXT    DEFAULT '',
                    token_type      TEXT    DEFAULT 'Character',
                    color           TEXT    DEFAULT '#4f9eff',
                    x               REAL    DEFAULT 0.0,
                    y               REAL    DEFAULT 0.0,
                    cell_width      REAL    DEFAULT 1.0,
                    cell_height     REAL    DEFAULT 1.0,
                    rotation        REAL    DEFAULT 0.0,
                    layer           INTEGER DEFAULT 1,
                    visible         INTEGER DEFAULT 1,
                    label_visible   INTEGER DEFAULT 1,
                    hp_current      INTEGER DEFAULT 0,
                    hp_max          INTEGER DEFAULT 0,
                    conditions_json TEXT    DEFAULT '[]',
                    notes           TEXT    DEFAULT '',
                    sort_order      INTEGER DEFAULT 0,
                    created_at      TEXT    DEFAULT (datetime('now'))
                )
            """)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS map_token_library (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER,
                    name        TEXT    NOT NULL,
                    image_path  TEXT    DEFAULT '',
                    token_type  TEXT    DEFAULT 'Character',
                    color       TEXT    DEFAULT '#4f9eff',
                    default_w   REAL    DEFAULT 1.0,
                    default_h   REAL    DEFAULT 1.0,
                    created_at  TEXT    DEFAULT (datetime('now'))
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_campaign_maps_cid "
                "ON campaign_maps(campaign_id)"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_map_tokens_mid "
                "ON map_tokens(map_id)"
            )
        except Exception as e:
            log.error(f"[MapRepository] init_tables: {e}")

    # ── Maps ──────────────────────────────────────────────────────────────────

    def create_map(self, campaign_id: int, name: str, image_path: str = "") -> int:
        try:
            cur = self._db.execute(
                "INSERT INTO campaign_maps (campaign_id, name, image_path) "
                "VALUES (?, ?, ?)",
                (campaign_id, name, image_path),
            )
            return cur.lastrowid
        except Exception as e:
            log.error(f"[MapRepository] create_map: {e}")
            return -1

    def get_map(self, map_id: int) -> Optional[dict]:
        try:
            rows = self._db.query(
                "SELECT * FROM campaign_maps WHERE id=?", (map_id,)
            )
            return _parse_map(dict(rows[0])) if rows else None
        except Exception as e:
            log.error(f"[MapRepository] get_map: {e}")
            return None

    def get_maps(self, campaign_id: int) -> list[dict]:
        try:
            rows = self._db.query(
                "SELECT * FROM campaign_maps WHERE campaign_id=? ORDER BY name",
                (campaign_id,),
            )
            return [_parse_map(dict(r)) for r in rows]
        except Exception as e:
            log.error(f"[MapRepository] get_maps: {e}")
            return []

    def update_map(self, map_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        if "fog_data" in kwargs and isinstance(kwargs["fog_data"], (list, tuple, set)):
            kwargs["fog_data"] = json.dumps(list(kwargs["fog_data"]))
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [map_id]
        try:
            self._db.execute(
                f"UPDATE campaign_maps SET {cols}, updated_at=datetime('now') WHERE id=?",
                vals,
            )
            return True
        except Exception as e:
            log.error(f"[MapRepository] update_map: {e}")
            return False

    def delete_map(self, map_id: int) -> bool:
        try:
            self._db.execute("DELETE FROM campaign_maps WHERE id=?", (map_id,))
            self._db.execute("DELETE FROM map_tokens WHERE map_id=?", (map_id,))
            return True
        except Exception as e:
            log.error(f"[MapRepository] delete_map: {e}")
            return False

    def save_map_state(self, map_id: int, zoom: float, pan_x: float,
                       pan_y: float, fog_data: list) -> bool:
        return self.update_map(
            map_id,
            zoom_level=float(zoom),
            pan_x=float(pan_x),
            pan_y=float(pan_y),
            fog_data=fog_data,
        )

    # ── Tokens ────────────────────────────────────────────────────────────────

    def add_token(self, map_id: int, name: str, image_path: str = "",
                  token_type: str = "Character", color: str = "#4f9eff",
                  x: float = 0.0, y: float = 0.0,
                  cell_width: float = 1.0, cell_height: float = 1.0) -> int:
        try:
            cur = self._db.execute(
                "INSERT INTO map_tokens "
                "(map_id, name, image_path, token_type, color, x, y, cell_width, cell_height) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (map_id, name, image_path, token_type, color,
                 x, y, cell_width, cell_height),
            )
            return cur.lastrowid
        except Exception as e:
            log.error(f"[MapRepository] add_token: {e}")
            return -1

    def get_tokens(self, map_id: int) -> list[dict]:
        try:
            rows = self._db.query(
                "SELECT * FROM map_tokens WHERE map_id=? ORDER BY sort_order, id",
                (map_id,),
            )
            return [_parse_token(dict(r)) for r in rows]
        except Exception as e:
            log.error(f"[MapRepository] get_tokens: {e}")
            return []

    def update_token(self, token_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        if "conditions_json" in kwargs and isinstance(
            kwargs["conditions_json"], (list, tuple)
        ):
            kwargs["conditions_json"] = json.dumps(kwargs["conditions_json"])
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [token_id]
        try:
            self._db.execute(
                f"UPDATE map_tokens SET {cols} WHERE id=?", vals
            )
            return True
        except Exception as e:
            log.error(f"[MapRepository] update_token: {e}")
            return False

    def delete_token(self, token_id: int) -> bool:
        try:
            self._db.execute("DELETE FROM map_tokens WHERE id=?", (token_id,))
            return True
        except Exception as e:
            log.error(f"[MapRepository] delete_token: {e}")
            return False

    def delete_tokens_for_map(self, map_id: int) -> int:
        try:
            self._db.execute("DELETE FROM map_tokens WHERE map_id=?", (map_id,))
            return 0
        except Exception as e:
            log.error(f"[MapRepository] delete_tokens_for_map: {e}")
            return 0

    # ── Token library ─────────────────────────────────────────────────────────

    def add_to_library(self, campaign_id: Optional[int], name: str,
                       image_path: str = "", token_type: str = "Character",
                       color: str = "#4f9eff",
                       default_w: float = 1.0, default_h: float = 1.0) -> int:
        try:
            cur = self._db.execute(
                "INSERT INTO map_token_library "
                "(campaign_id, name, image_path, token_type, color, default_w, default_h) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (campaign_id, name, image_path, token_type,
                 color, default_w, default_h),
            )
            return cur.lastrowid
        except Exception as e:
            log.error(f"[MapRepository] add_to_library: {e}")
            return -1

    def get_library(self, campaign_id: Optional[int]) -> list[dict]:
        try:
            if campaign_id is not None:
                rows = self._db.query(
                    "SELECT * FROM map_token_library "
                    "WHERE campaign_id=? OR campaign_id IS NULL ORDER BY name",
                    (campaign_id,),
                )
            else:
                rows = self._db.query(
                    "SELECT * FROM map_token_library "
                    "WHERE campaign_id IS NULL ORDER BY name"
                )
            return [dict(r) for r in rows]
        except Exception as e:
            log.error(f"[MapRepository] get_library: {e}")
            return []

    def delete_from_library(self, lib_id: int) -> bool:
        try:
            self._db.execute(
                "DELETE FROM map_token_library WHERE id=?", (lib_id,)
            )
            return True
        except Exception as e:
            log.error(f"[MapRepository] delete_from_library: {e}")
            return False
