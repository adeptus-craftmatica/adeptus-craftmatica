# core/settings_service.py

from __future__ import annotations
import json
from typing import Any, Optional
import logging
log = logging.getLogger(__name__)


class SettingsService:
    """
    Central settings service.

    Features:
    - Persistent storage (SQLite via DatabaseService)
    - Namespaced keys (plugin-safe)
    - Default values
    - JSON-based storage for flexibility
    - Change events (via EventBus)
    """

    TABLE_NAME = "app_settings"

    def __init__(self, db, event_bus=None):
        self.db = db
        self.event_bus = event_bus

        # In-memory cache for performance
        self._cache: dict[str, Any] = {}

        # Defaults (not stored in DB unless overridden)
        self._defaults: dict[str, Any] = {}

        self._ensure_schema()

    # ----------------------------
    # Schema
    # ----------------------------

    def _ensure_schema(self):
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # ----------------------------
    # Public API
    # ----------------------------

    def set(self, key: str, value: Any):
        """
        Set a setting value.

        Args:
            key: Unique key (recommended: plugin.key format)
            value: Any JSON-serializable value
        """
        serialized = json.dumps(value)

        self.db.execute(f"""
            INSERT INTO {self.TABLE_NAME} (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, serialized))

        self._cache[key] = value

        # Emit change event
        if self.event_bus:
            self.event_bus.emit("setting_changed", {
                "key": key,
                "value": value
            })

        _SENSITIVE = ("pat", "token", "secret", "password")
        display = "***" if any(s in key.lower() for s in _SENSITIVE) else value
        log.debug(f"[SETTINGS] Set: {key} = {display}")

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """
        Retrieve a setting value.

        Priority:
        1. Cache
        2. Database
        3. Registered defaults
        4. Provided default
        """
        # Cache hit
        if key in self._cache:
            return self._cache[key]

        # Database lookup
        rows = self.db.query(f"""
            SELECT value FROM {self.TABLE_NAME}
            WHERE key = ?
        """, (key,))

        if rows:
            value = json.loads(rows[0]["value"])
            self._cache[key] = value
            return value

        # Default fallback
        if key in self._defaults:
            return self._defaults[key]

        return default

    def has(self, key: str) -> bool:
        """Check if a setting exists (DB or defaults)"""
        if key in self._cache or key in self._defaults:
            return True

        rows = self.db.query(f"""
            SELECT 1 FROM {self.TABLE_NAME}
            WHERE key = ?
            LIMIT 1
        """, (key,))

        return bool(rows)

    def delete(self, key: str):
        """Remove a setting"""
        self.db.execute(f"""
            DELETE FROM {self.TABLE_NAME}
            WHERE key = ?
        """, (key,))

        self._cache.pop(key, None)

        log.debug(f"[SETTINGS] Deleted: {key}")

    # ----------------------------
    # Defaults
    # ----------------------------

    def register_default(self, key: str, value: Any):
        """
        Register a default value.

        Does NOT overwrite existing DB value.
        """
        if key not in self._defaults:
            self._defaults[key] = value
            log.debug(f"[SETTINGS] Default registered: {key} = {value}")

    def register_defaults(self, defaults: dict[str, Any]):
        """Bulk register defaults"""
        for key, value in defaults.items():
            self.register_default(key, value)

    # ----------------------------
    # Namespacing Helpers
    # ----------------------------

    def get_namespace(self, namespace: str) -> dict[str, Any]:
        """
        Get all settings for a namespace.

        Example:
            namespace = "paint_tracker"
            returns all keys starting with "paint_tracker."
        """
        prefix = f"{namespace}."

        rows = self.db.query(f"""
            SELECT key, value FROM {self.TABLE_NAME}
            WHERE key LIKE ?
        """, (f"{prefix}%",))

        result = {}

        for row in rows:
            key = row["key"]
            short_key = key.replace(prefix, "", 1)
            result[short_key] = json.loads(row["value"])

        return result

    def set_namespace(self, namespace: str, values: dict[str, Any]):
        """
        Set multiple settings under a namespace.
        """
        for key, value in values.items():
            full_key = f"{namespace}.{key}"
            self.set(full_key, value)

    # ----------------------------
    # Debugging
    # ----------------------------

    def debug_dump(self):
        log.debug("\n=== SETTINGS DUMP ===")

        rows = self.db.query(f"""
            SELECT key, value FROM {self.TABLE_NAME}
            ORDER BY key
        """)

        for row in rows:
            log.debug(f"{row['key']} = {row['value']}")

        log.debug("======================\n")