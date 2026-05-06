"""
Materials Tracker — Domain Models
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class ValidationError(Exception):
    """Raised when material data fails validation."""
    pass


# ── Presets ───────────────────────────────────────────────────────────────────

MATERIAL_TYPES = [
    "Static Grass",
    "Tufts",
    "Sand / Ballast",
    "Gravel / Grit",
    "Stones / Rocks",
    "Leaves / Foliage",
    "Moss / Lichen",
    "Bark / Cork",
    "Snow Effect",
    "Water Effect",
    "Texture Medium",
    "Technical Paint",
    "Pigment Powder",
    "Resin / Epoxy",
    "Foam",
    "Flock",
    "Scenic Bits",
    "Basing Kit",
    "Other",
]

STOCK_LEVELS = ["Full", "Good", "Low", "Empty", "On Order"]

STOCK_COLORS = {
    "Full":     "#2e7d32",   # green
    "Good":     "#388e3c",   # mid-green
    "Low":      "#f57c00",   # amber
    "Empty":    "#b71c1c",   # red
    "On Order": "#0277bd",   # blue
}

STOCK_ROW_COLORS = {
    "Empty":    "#3d1515",   # dark red bg
    "Low":      "#362410",   # dark amber bg
    "On Order": "#0d2137",   # dark blue bg
}


# ── Material dataclass ────────────────────────────────────────────────────────

@dataclass
class Material:
    name:          str
    material_type: str
    brand:         str            = ""
    color:         str            = ""
    stock:         str            = "Good"
    quantity:      int            = 1
    notes:         Optional[str]  = None
    id:            Optional[int]  = None

    def __post_init__(self):
        self._validate()

    def _validate(self):
        if not self.name or not self.name.strip():
            raise ValidationError("Material name cannot be empty")
        if len(self.name.strip()) > 200:
            raise ValidationError("Material name cannot exceed 200 characters")
        if not self.material_type or not self.material_type.strip():
            raise ValidationError("Material type cannot be empty")
        if self.quantity < 0:
            raise ValidationError("Quantity cannot be negative")
        if self.stock not in STOCK_LEVELS:
            raise ValidationError(
                f"Stock level must be one of: {', '.join(STOCK_LEVELS)}"
            )


# ── Filter ────────────────────────────────────────────────────────────────────

@dataclass
class MaterialFilter:
    search_text:   Optional[str] = None
    material_type: Optional[str] = None
    brand:         Optional[str] = None
    stock:         Optional[str] = None
    sort_by:       Optional[str] = None
    sort_desc:     bool          = False


# ── Statistics ────────────────────────────────────────────────────────────────

@dataclass
class MaterialStatistics:
    total_count:             int  = 0
    unique_types:            int  = 0
    unique_brands:           int  = 0
    needs_restock:           int  = 0
    types_distribution:      dict = field(default_factory=dict)
    stock_distribution:      dict = field(default_factory=dict)
    brands_distribution:     dict = field(default_factory=dict)
