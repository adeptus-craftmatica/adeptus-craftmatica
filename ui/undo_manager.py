# ui/undo_manager.py
"""
Lightweight undo stack for Adeptus Craftmatica.

Stores up to MAX_STACK reversible operations. Each operation carries
a human-readable label and a callable that reverses it.

Pattern — call push() AFTER a destructive action, passing the undo
function so that if the user clicks "Undo" in the resulting toast the
operation can be reversed cleanly:

    # Capture state before destruction
    paint_data = {k: getattr(paint, k) for k in PAINT_FIELDS}
    # Execute destruction
    service.delete_paint(paint_id)
    # Register undo
    UndoManager.instance().push(
        f"Deleted {paint.brand} — {paint.name}",
        lambda d=paint_data: restore_paint(d),
    )

The toast system calls undo() when the user taps the "Undo" button.
Nothing else in the codebase needs to know about this module.
"""
from __future__ import annotations

import logging
log = logging.getLogger(__name__)

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class _UndoAction:
    label:     str
    undo_fn:   Callable
    timestamp: float = field(default_factory=time.monotonic)


class UndoManager:
    """
    Global undo stack.  Singleton — always use UndoManager.instance().

    Thread note: all mutations happen on the Qt main thread (event
    handlers), so no locking is required.
    """

    _instance: "UndoManager | None" = None
    MAX_STACK: int = 15

    def __init__(self) -> None:
        self._stack: deque[_UndoAction] = deque(maxlen=self.MAX_STACK)

    # ── Singleton ──────────────────────────────────────────────────────────────

    @classmethod
    def instance(cls) -> "UndoManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Public API ─────────────────────────────────────────────────────────────

    def push(self, label: str, undo_fn: Callable) -> None:
        """
        Register a reversible action.

        :param label:    Short human-readable description shown to the user.
        :param undo_fn:  Zero-argument callable that undoes the action.
        """
        self._stack.append(_UndoAction(label=label, undo_fn=undo_fn))

    def can_undo(self) -> bool:
        """True when at least one reversible action is queued."""
        return bool(self._stack)

    def peek_label(self) -> Optional[str]:
        """Return the label of the most recent action without undoing it."""
        return self._stack[-1].label if self._stack else None

    def undo(self) -> Optional[str]:
        """
        Execute the most recent undo function and remove it from the stack.

        :returns: The action label on success, None if nothing to undo or
                  if the undo_fn raises an exception.
        """
        if not self._stack:
            return None
        action = self._stack.pop()
        try:
            action.undo_fn()
            return action.label
        except Exception as e:
            log.error(f"[UNDO] Failed to reverse '{action.label}': {e}")
            return None

    def clear(self) -> None:
        """Discard all queued undo actions (e.g., when the user deletes a project)."""
        self._stack.clear()
