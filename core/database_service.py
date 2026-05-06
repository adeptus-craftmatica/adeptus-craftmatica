from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


class DatabaseService:
    """
    Central database service.
    One DB file, shared across all plugins.

    Normal usage — auto-commits after every statement:
        cursor = db.execute("INSERT INTO ...", (values,))
        cursor = db.query("SELECT ...", (params,))

    Multi-step atomic usage — opt-in transaction context:
        with db.transaction():
            db.execute("INSERT INTO table_a ...")
            db.execute("INSERT INTO table_b ...")
        # Both committed together, or both rolled back on exception.
    """

    def __init__(self, db_path: str = "app.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        # Track whether we are inside an explicit transaction so execute()
        # knows not to call commit() (the context manager handles it).
        self._in_transaction: bool = False

    # ── Single-statement helpers ──────────────────────────────────────────────

    def execute(self, query: str, params: tuple = ()):
        """Execute a write statement. Auto-commits unless inside transaction()."""
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        if not self._in_transaction:
            self.conn.commit()
        return cursor

    def query(self, query: str, params: tuple = ()):
        """Execute a read-only statement and return all rows."""
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

    # ── Explicit transaction context manager ──────────────────────────────────

    @contextmanager
    def transaction(self):
        """
        Explicit transaction block.  Multiple execute() calls inside share one
        commit/rollback — either all succeed or all are rolled back.

        Usage::

            with db.transaction():
                db.execute("INSERT INTO table_a ...", (...,))
                db.execute("INSERT INTO table_b ...", (...,))
        """
        if self._in_transaction:
            # Already inside an outer transaction — let that one own commit/rollback.
            yield
            return

        self._in_transaction = True
        try:
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self._in_transaction = False
