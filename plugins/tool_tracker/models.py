"""
Tool Tracker — Domain Models

Pure data classes with no framework or infrastructure dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class ValidationError(Exception):
    """Raised when tool data fails validation."""
    pass


# ── Presets ───────────────────────────────────────────────────────────────────

TOOL_TYPES = [
    "Nippers",
    "Hobby Knife / Blade",
    "File",
    "Sandpaper",
    "Brush",
    "Airbrush",
    "Drill / Pin Vice",
    "Sculpting Tool",
    "Tweezers",
    "Plastic Glue",
    "Super Glue",
    "Green Stuff / Putty",
    "Cutting Mat",
    "Painting Handle",
    "Spray Can",
    "Other",
]

TOOL_CONDITIONS = ["New", "Good", "Fair", "Worn", "Replace"]

CONDITION_COLORS = {
    "New":     "#2e7d32",   # green
    "Good":    "#388e3c",   # mid-green
    "Fair":    "#f57c00",   # amber
    "Worn":    "#d84315",   # orange-red
    "Replace": "#b71c1c",   # red
}


# ── Tool dataclass ────────────────────────────────────────────────────────────

@dataclass
class Tool:
    name:       str
    tool_type:  str
    brand:      str       = ""
    condition:  str       = "Good"
    quantity:   int       = 1
    notes:      Optional[str] = None
    id:         Optional[int] = None

    def __post_init__(self):
        self._validate()

    def _validate(self):
        if not self.name or not self.name.strip():
            raise ValidationError("Tool name cannot be empty")
        if len(self.name.strip()) > 200:
            raise ValidationError("Tool name cannot exceed 200 characters")
        if not self.tool_type or not self.tool_type.strip():
            raise ValidationError("Tool type cannot be empty")
        if self.quantity < 0:
            raise ValidationError("Quantity cannot be negative")
        if self.condition not in TOOL_CONDITIONS:
            raise ValidationError(
                f"Condition must be one of: {', '.join(TOOL_CONDITIONS)}"
            )


# ── Filter ────────────────────────────────────────────────────────────────────

@dataclass
class ToolFilter:
    search_text: Optional[str] = None
    tool_type:   Optional[str] = None
    brand:       Optional[str] = None
    condition:   Optional[str] = None
    sort_by:     Optional[str] = None
    sort_desc:   bool          = False


# ── Statistics ────────────────────────────────────────────────────────────────

@dataclass
class ToolStatistics:
    total_count:          int        = 0
    unique_types:         int        = 0
    unique_brands:        int        = 0
    needs_replacement:    int        = 0
    types_distribution:   dict       = field(default_factory=dict)
    conditions_distribution: dict    = field(default_factory=dict)
    brands_distribution:  dict       = field(default_factory=dict)
