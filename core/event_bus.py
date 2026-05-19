# core/event_bus.py

from __future__ import annotations

import logging
log = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list] = {}

    def subscribe(self, event_name, callback):
        self._subscribers.setdefault(event_name, [])
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name, callback):
        callbacks = self._subscribers.get(event_name, [])
        if callback in callbacks:
            callbacks.remove(callback)

        if not callbacks and event_name in self._subscribers:
            del self._subscribers[event_name]

    def emit(self, event_name, payload=None):
        if payload is None:
            payload = {}
        _SENSITIVE = ("pat", "token", "secret", "password")
        safe = {k: "***" if any(s in k.lower() for s in _SENSITIVE) else v
                for k, v in payload.items()} if isinstance(payload, dict) else payload
        log.debug(f"[EVENT] {event_name} -> {safe}")

        for callback in list(self._subscribers.get(event_name, [])):
            callback(payload)