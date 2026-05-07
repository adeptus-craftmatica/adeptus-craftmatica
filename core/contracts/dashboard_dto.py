"""
Dashboard DTOs — the shared data contract between plugin providers and the
Dashboard UI.

Rules:
  • No plugin-specific imports anywhere in this file.
  • Every field has a default so callers only provide what they know.
  • color fields accept a severity key ("accent", "success", "warning", "danger")
    that the widget layer maps to an actual hex value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ── Severity keys ─────────────────────────────────────────────────────────────

class Severity:
    INFO     = "info"
    SUCCESS  = "success"
    WARNING  = "warning"
    CRITICAL = "critical"


# ── Command overview strip ────────────────────────────────────────────────────

@dataclass
class CommandStat:
    """One number shown on the top command-overview strip."""
    label:    str
    value:    str           # Pre-formatted: "42", "3 / 10", "87 %"
    subtitle: str  = ""    # Helper text rendered below the value
    color:    str  = "accent"   # severity key
    icon:     str  = ""    # emoji shown beside the value
    card_id:  str  = ""    # Stable identifier for hide/show — auto-assigned
                           # by DashboardRegistry if left empty.
                           # Format: "<plugin_id>.<label_slug>"


# ── Active-projects feed ──────────────────────────────────────────────────────

@dataclass
class ProjectCard:
    """One entry in the centre-panel active-projects feed."""
    id:             Any
    plugin_id:      str
    plugin_label:   str         # e.g. "Army Builder"
    title:          str
    subtitle:       str  = ""
    progress:       float = -1.0  # 0.0–1.0; negative → do not show bar
    status:         str  = ""
    status_color:   str  = "accent"   # severity key
    last_active:    str  = ""         # human-readable "2 days ago"
    action_label:   str  = "Open"
    action_event:   str  = "dashboard_navigate"
    action_payload: dict = field(default_factory=dict)
    detail_lines:   list[str] = field(default_factory=list)


# ── Notifications / recommendations ──────────────────────────────────────────

@dataclass
class Notification:
    """An alert, recommendation, or tip from any plugin."""
    title:          str
    body:           str  = ""
    severity:       str  = Severity.INFO   # Severity key
    plugin_id:      str  = ""
    action_event:   str  = ""
    action_payload: dict = field(default_factory=dict)
    action_label:   str  = "View"


# ── Quick actions ─────────────────────────────────────────────────────────────

@dataclass
class QuickAction:
    """A single button in the quick-actions panel."""
    label:   str
    icon:    str        # emoji
    event:   str        # event name emitted on click
    payload: dict = field(default_factory=dict)
    color:   str  = "accent"   # severity key


# ── Smart recommendations ────────────────────────────────────────────────────

@dataclass
class Recommendation:
    """
    One specific, named next action the user should take.

    priority:  1 = urgent (danger),  2 = important (warning),  3 = suggested (accent)
    action:    Short verb — "Restock", "Prime", "Finish", "Fix", "Log Session"
    target:    The named thing — "Abaddon Black", "Intercessor Squad"
    context:   Why — "0 pots remaining", "80% complete", "active campaign"
    """
    action:         str
    target:         str
    context:        str  = ""
    priority:       int  = 3          # 1 | 2 | 3
    plugin_id:      str  = ""
    action_event:   str  = "dashboard_navigate"
    action_payload: dict = field(default_factory=dict)
    action_label:   str  = "View"
    icon:           str  = "→"


# ── Recent activity feed ──────────────────────────────────────────────────────

@dataclass
class ActivityItem:
    """One entry in the recent-activity log."""
    icon:        str
    description: str
    timestamp:   str   # ISO-8601 string stored in settings
    plugin_id:   str  = ""


# ── Shared navigation contract ────────────────────────────────────────────────

@dataclass
class NavigationTarget:
    """Canonical payload structure for deep-linking into any plugin view.

    Pass ``to_dict()`` as the ``action_payload`` of any dashboard DTO.
    The receiving plugin reads plugin_id, then project_id / tab / item_id
    as available.
    """
    plugin_id:  str           = ""
    project_id: Optional[int] = None   # which project to open
    tab:        Optional[str] = None   # which tab to switch to
    item_id:    Optional[int] = None   # which item within the tab to highlight

    def to_dict(self) -> dict:
        d: dict = {"plugin_id": self.plugin_id}
        if self.project_id is not None:
            d["project_id"] = self.project_id
        if self.tab is not None:
            d["tab"] = self.tab
        if self.item_id is not None:
            d["item_id"] = self.item_id
        return d


# ── Dashboard section definitions ─────────────────────────────────────────────

@dataclass
class DashboardSectionDef:
    """Metadata for one toggleable section of the dashboard.

    Used by DashboardCustomizeDialog to build the checklist and by the
    dashboard plugin to apply visibility from saved settings.

    Plugin providers can optionally return a list of these from
    ``get_section_defs()`` to advertise their own dashboard sections.
    """
    id:              str
    label:           str
    description:     str  = ""
    tab:             str  = "overview"    # "overview" | "activity" | "alerts"
    default_visible: bool = True
