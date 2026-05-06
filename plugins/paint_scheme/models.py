"""
Paint Scheme Domain Models

Pure domain objects with no dependencies on framework or infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ============================================================
# CONSTANTS
# ============================================================

TECHNIQUES = [
    "Primer",
    "Basecoat",
    "Layer",
    "Wash / Shade",
    "Drybrush",
    "Edge Highlight",
    "Highlight",
    "Glaze",
    "Contrast / Speed Paint",
    "Technical",
    "Varnish",
    "Basing",
    "Other",
]


# ============================================================
# PAINT SCHEME
# ============================================================

@dataclass
class PaintScheme:
    """A named paint scheme containing an ordered list of steps."""
    name: str
    game_system: str = ""
    faction: str = ""
    description: str = ""
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================================
# SCHEME STEP
# ============================================================

@dataclass
class SchemeStep:
    """A single step in a paint scheme."""
    scheme_id: int
    step_order: int          # 1-based position within the scheme
    technique: str = "Basecoat"
    paint_id: Optional[int] = None   # FK to paint_tracker paints table, nullable
    paint_name: str = ""             # display name (copied from paint or typed manually)
    notes: str = ""
    id: Optional[int] = None


# ============================================================
# FILTER
# ============================================================

@dataclass
class SchemeFilter:
    """Filter criteria for searching schemes. All fields optional."""
    search_text: Optional[str] = None
    game_system: Optional[str] = None
    faction: Optional[str] = None

    def is_empty(self) -> bool:
        return not any([self.search_text, self.game_system, self.faction])

    def matches(self, scheme: PaintScheme) -> bool:
        if self.game_system and self.game_system.lower() not in scheme.game_system.lower():
            return False
        if self.faction and self.faction.lower() not in scheme.faction.lower():
            return False
        if self.search_text:
            needle = self.search_text.lower()
            haystack = f"{scheme.name} {scheme.game_system} {scheme.faction} {scheme.description}".lower()
            if needle not in haystack:
                return False
        return True
