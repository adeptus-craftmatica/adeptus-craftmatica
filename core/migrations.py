"""
SchemaManager — per-repository migration runner.

Each repository registers a list of ALTER TABLE SQL strings as `_MIGRATIONS`.
SchemaManager tracks which migrations have run in a `_schema_versions` table
and executes only the pending ones on each startup.

Migration numbering: index 0 in _MIGRATIONS = migration version 1, etc.
For ADD COLUMN migrations: a pre-flight PRAGMA table_info check skips the
ALTER if the column already exists, allowing safe rollout on databases that
pre-date this migration system.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class SchemaManager:
    """Tracks and applies schema migrations for a single repository owner."""

    _META_TABLE = "_schema_versions"

    def __init__(self, db) -> None:
        self._db = db
        self._ensure_meta_table()

    # ── Public API ─────────────────────────────────────────────────────────

    def migrate(self, owner: str, migrations: list[str]) -> None:
        """
        Apply any pending migrations for *owner*.

        :param owner:      Unique string identifying the repository
                           (e.g. ``"campaign_tracker"``).
        :param migrations: Ordered list of SQL strings.  Index 0 is migration
                           version 1 (v0 → v1), index 1 is version 2, etc.
        """
        current = self._get_version(owner)
        for idx, sql in enumerate(migrations):
            target_version = idx + 1
            if target_version <= current:
                continue
            self._apply(owner, target_version, sql)

    # ── Internal ───────────────────────────────────────────────────────────

    def _ensure_meta_table(self) -> None:
        self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._META_TABLE} (
                owner   TEXT PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 0
            )
        """)

    def _get_version(self, owner: str) -> int:
        rows = self._db.query(
            f"SELECT version FROM {self._META_TABLE} WHERE owner = ?", (owner,)
        )
        return rows[0][0] if rows else 0

    def _set_version(self, owner: str, version: int) -> None:
        self._db.execute(
            f"""INSERT INTO {self._META_TABLE} (owner, version) VALUES (?, ?)
                ON CONFLICT(owner) DO UPDATE SET version = excluded.version""",
            (owner, version),
        )

    def _apply(self, owner: str, version: int, sql: str) -> None:
        """
        Execute *sql* and record *version* atomically.

        For ``ADD COLUMN`` statements: uses ``PRAGMA table_info`` to skip the
        ALTER when the column already exists (safe on pre-migration databases).
        """
        if "ADD COLUMN" in sql.upper():
            if self._column_exists(sql):
                log.debug(
                    "[migrations] %s v%d: column already present — skipping",
                    owner, version,
                )
                self._set_version(owner, version)
                return

        log.debug("[migrations] %s: applying v%d", owner, version)
        try:
            with self._db.transaction():
                self._db.execute(sql)
                self._set_version(owner, version)
        except Exception as exc:
            raise RuntimeError(
                f"Migration v{version} for '{owner}' failed.\n"
                f"SQL: {sql!r}"
            ) from exc

    def _column_exists(self, alter_sql: str) -> bool:
        """
        Parse ``ALTER TABLE <t> ADD COLUMN <col> ...`` and return True if
        the column already exists in the table.  Returns False if parsing
        fails so the migration runs and lets SQLite report any real error.
        """
        parts = alter_sql.split()
        try:
            table_idx = next(i for i, p in enumerate(parts) if p.upper() == "TABLE") + 1
            col_idx   = next(i for i, p in enumerate(parts) if p.upper() == "COLUMN") + 1
            table = parts[table_idx]
            col   = parts[col_idx]
            existing = {r[1].lower() for r in self._db.query(f"PRAGMA table_info({table})")}
            return col.lower() in existing
        except (StopIteration, IndexError):
            return False
