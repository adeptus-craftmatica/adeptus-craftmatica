"""
Dashboard service auto-registration.

This module is discovered by PluginManager._auto_register_modules() and
registers the DashboardRegistry as a core service before the Dashboard
plugin's activate() runs.  Other plugins (or the Dashboard itself) then
call context.services.try_get("dashboard_registry") to interact with it.
"""
import logging
log = logging.getLogger(__name__)

from core.dashboard_registry import DashboardRegistry


def register(context):
    log.debug("[DASHBOARD] Registering DashboardRegistry...")
    registry = DashboardRegistry()
    context.services.register("dashboard_registry", registry, override=True)
    log.debug("[DASHBOARD] DashboardRegistry registered")
    return registry
