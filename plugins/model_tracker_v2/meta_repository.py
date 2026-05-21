"""
Model Tracker V2 — Meta Repository

Stores v2-only metadata in the model_tracker_v2_meta table.
Fields: is_focus (bool), completed_count (int), squad_name (text).
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from core.migrations import SchemaManager


class MetaRepository:
    TABLE = "model_tracker_v2_meta"

    _MIGRATIONS: list[str] = []

    def __init__(self, db) -> None:
        self._db = db
        self._ensure_schema()
        SchemaManager(db).migrate("model_tracker_v2_meta", self._MIGRATIONS)

    # ── Schema ────────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
                model_id        INTEGER PRIMARY KEY,
                is_focus        INTEGER DEFAULT 0,
                completed_count INTEGER DEFAULT 0,
                squad_name      TEXT
            )
        """)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_meta(self, model_id: int) -> dict:
        """Return {is_focus, completed_count, squad_name} for a model."""
        rows = self._db.query(
            f"SELECT is_focus, completed_count, squad_name FROM {self.TABLE} WHERE model_id = ?",
            (model_id,),
        )
        if not rows:
            return {"is_focus": False, "completed_count": 0, "squad_name": ""}
        row = rows[0]
        return {
            "is_focus":        bool(row["is_focus"]),
            "completed_count": row["completed_count"] or 0,
            "squad_name":      row["squad_name"] or "",
        }

    def get_all_meta(self) -> dict[int, dict]:
        """Return {model_id: {is_focus, completed_count, squad_name}} for bulk use."""
        rows = self._db.query(
            f"SELECT model_id, is_focus, completed_count, squad_name FROM {self.TABLE}"
        )
        result: dict[int, dict] = {}
        for row in rows:
            result[row["model_id"]] = {
                "is_focus":        bool(row["is_focus"]),
                "completed_count": row["completed_count"] or 0,
                "squad_name":      row["squad_name"] or "",
            }
        return result

    # ── Write ─────────────────────────────────────────────────────────────────

    def set_meta(
        self,
        model_id: int,
        is_focus: bool | None = None,
        completed_count: int | None = None,
        squad_name: str | None = None,
    ) -> None:
        """Upsert metadata for a model. Only updates provided (non-None) fields."""
        current = self.get_meta(model_id)
        new_is_focus        = is_focus if is_focus is not None else current["is_focus"]
        new_completed_count = completed_count if completed_count is not None else current["completed_count"]
        new_squad_name      = squad_name if squad_name is not None else current["squad_name"]
        try:
            self._db.execute(
                f"""
                INSERT INTO {self.TABLE} (model_id, is_focus, completed_count, squad_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    is_focus        = excluded.is_focus,
                    completed_count = excluded.completed_count,
                    squad_name      = excluded.squad_name
                """,
                (model_id, int(new_is_focus), new_completed_count, new_squad_name or None),
            )
        except Exception as e:
            log.error(f"[META REPO] set_meta failed for model_id={model_id}: {e}")

    def delete_meta(self, model_id: int) -> None:
        """Remove metadata row — called when a model is deleted."""
        try:
            self._db.execute(
                f"DELETE FROM {self.TABLE} WHERE model_id = ?", (model_id,)
            )
        except Exception as e:
            log.warning(f"[META REPO] delete_meta failed for model_id={model_id}: {e}")
