# core/service_registry.py

from __future__ import annotations
from typing import Any, Callable
import logging
log = logging.getLogger(__name__)


class ServiceRegistry:
    """
    Central registry for all application and plugin services.

    Responsibilities:
    - Register services
    - Provide access to services
    - Prevent accidental overrides
    - Support lazy-loaded services
    - Provide debugging visibility
    """

    def __init__(self):
        self._services: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}

    # ----------------------------
    # Registration
    # ----------------------------

    def register(self, name: str, service: Any, override: bool = False):
        """
        Register a service instance.

        Args:
            name: Unique service name
            service: Service instance
            override: Allow overwriting existing service
        """
        if not override and name in self._services:
            raise ValueError(f"Service '{name}' is already registered")

        self._services[name] = service
        log.debug(f"[SERVICE] Registered: {name}")

    def register_factory(self, name: str, factory: Callable[[], Any], override: bool = False):
        """
        Register a lazy-loaded service.

        The factory will only be called when the service is first requested.
        """
        if not override and (name in self._services or name in self._factories):
            raise ValueError(f"Service '{name}' is already registered")

        self._factories[name] = factory
        log.debug(f"[SERVICE] Registered factory: {name}")

    # ----------------------------
    # Retrieval
    # ----------------------------

    def get(self, name: str) -> Any:
        """
        Retrieve a service by name.

        Supports lazy initialization if registered via factory.
        """
        # Already instantiated
        if name in self._services:
            return self._services[name]

        # Lazy factory
        if name in self._factories:
            log.debug(f"[SERVICE] Lazy-loading: {name}")
            service = self._factories[name]()
            self._services[name] = service
            del self._factories[name]
            return service

        raise KeyError(f"Service '{name}' not found")

    def try_get(self, name: str) -> Any | None:
        """
        Safe version of get() that returns None if not found.
        """
        try:
            return self.get(name)
        except KeyError:
            return None

    # ----------------------------
    # Introspection
    # ----------------------------

    def has(self, name: str) -> bool:
        """Check if a service exists"""
        return name in self._services or name in self._factories

    def list_services(self) -> list[str]:
        """List all registered services"""
        return list(self._services.keys()) + list(self._factories.keys())

    def debug_dump(self):
        """Print all registered services (debugging)"""
        log.debug("\n=== SERVICE REGISTRY ===")
        for name in self._services:
            log.debug(f"✔ {name} (loaded)")
        for name in self._factories:
            log.debug(f"⏳ {name} (lazy)")
        log.debug("========================\n")

    # ----------------------------
    # Removal (optional)
    # ----------------------------

    def unregister(self, name: str):
        """Remove a service"""
        if name in self._services:
            del self._services[name]
        elif name in self._factories:
            del self._factories[name]
        else:
            raise KeyError(f"Service '{name}' not found")

        log.debug(f"[SERVICE] Unregistered: {name}")