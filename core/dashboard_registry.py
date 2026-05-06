"""
Dashboard Registry — central broker between plugin data providers and the
Dashboard UI.

Design:
  • Each plugin (or the Dashboard itself) calls register_provider(plugin_id, obj)
    where obj implements the duck-typed provider interface.
  • The Dashboard queries all providers through this registry, never importing
    directly from individual plugin packages.
  • Missing or broken providers are silently skipped; the dashboard degrades
    gracefully when a plugin is not installed.

Provider interface (duck-typed, no ABC required):
    get_command_stats()  → list[CommandStat]
    get_project_cards()  → list[ProjectCard]
    get_notifications()  → list[Notification]
    get_quick_actions()  → list[QuickAction]
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.contracts.dashboard_dto import (
        CommandStat, ProjectCard, Notification, QuickAction,
    )

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "success": 2, "info": 3}


class DashboardRegistry:
    """Central registry — registered as the "dashboard_registry" service."""

    def __init__(self):
        self._providers: dict[str, object] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register_provider(self, plugin_id: str, provider: object) -> None:
        self._providers[plugin_id] = provider
        print(f"[DASHBOARD REGISTRY] Registered provider: {plugin_id}")

    def unregister_provider(self, plugin_id: str) -> None:
        self._providers.pop(plugin_id, None)
        print(f"[DASHBOARD REGISTRY] Unregistered provider: {plugin_id}")

    def get_provider(self, plugin_id: str) -> object | None:
        return self._providers.get(plugin_id)

    def provider_ids(self) -> list[str]:
        return list(self._providers.keys())

    # ── Aggregated queries ────────────────────────────────────────────────────

    def get_all_command_stats(self) -> list["CommandStat"]:
        results: list = []
        for pid, provider in self._providers.items():
            try:
                items = provider.get_command_stats()
                if items:
                    results.extend(items)
            except Exception as e:
                print(f"[DASHBOARD REGISTRY] get_command_stats failed [{pid}]: {e}")
        return results

    def get_all_projects(self) -> list["ProjectCard"]:
        results: list = []
        for pid, provider in self._providers.items():
            try:
                items = provider.get_project_cards()
                if items:
                    results.extend(items)
            except Exception as e:
                print(f"[DASHBOARD REGISTRY] get_project_cards failed [{pid}]: {e}")
        return results

    def get_all_notifications(self) -> list["Notification"]:
        results: list = []
        for pid, provider in self._providers.items():
            try:
                items = provider.get_notifications()
                if items:
                    results.extend(items)
            except Exception as e:
                print(f"[DASHBOARD REGISTRY] get_notifications failed [{pid}]: {e}")
        # Critical first, then warning, success, info
        results.sort(key=lambda n: _SEVERITY_ORDER.get(n.severity, 99))
        return results

    def get_all_recommendations(self) -> list["Recommendation"]:
        """Aggregate recommendations from all providers, sorted by priority."""
        results: list = []
        for pid, provider in self._providers.items():
            fn = getattr(provider, "get_recommendations", None)
            if not callable(fn):
                continue
            try:
                items = fn()
                if items:
                    results.extend(items)
            except Exception as e:
                print(f"[DASHBOARD REGISTRY] get_recommendations failed [{pid}]: {e}")
        results.sort(key=lambda r: r.priority)
        return results

    def get_all_quick_actions(self) -> list["QuickAction"]:
        results: list = []
        for pid, provider in self._providers.items():
            try:
                items = provider.get_quick_actions()
                if items:
                    results.extend(items)
            except Exception as e:
                print(f"[DASHBOARD REGISTRY] get_quick_actions failed [{pid}]: {e}")
        return results
