"""
Paint Tracker Domain Models

Pure domain objects with no dependencies on framework or infrastructure.
Handles validation and business rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


class ValidationError(Exception):
    """Raised when domain validation fails."""
    pass


# ============================================================
# CONSTANTS
# ============================================================

VALID_LEVELS = ["Full", "Half-Bottle", "Low", "Out"]


# ============================================================
# PAINT MODEL
# ============================================================

@dataclass
class Paint:
    """
    Core domain model for a paint.

    Contains validation and normalization rules.
    """
    brand: str
    name: str
    paint_type: str
    color: str
    quantity: int = 1
    level: Optional[str] = None
    notes: Optional[str] = None
    is_favorite: bool = False
    notify_low_stock: bool = True
    id: Optional[int] = None

    def __post_init__(self):
        self._validate()

    def _validate(self):
        # Brand validation
        if not self.brand or not self.brand.strip():
            raise ValidationError("Brand cannot be empty")
        if len(self.brand.strip()) > 100:
            raise ValidationError("Brand cannot exceed 100 characters")

        # Name validation
        if not self.name or not self.name.strip():
            raise ValidationError("Name cannot be empty")
        if len(self.name.strip()) > 200:
            raise ValidationError("Name cannot exceed 200 characters")

        # Type validation
        if not self.paint_type or not self.paint_type.strip():
            raise ValidationError("Type cannot be empty")
        if len(self.paint_type.strip()) > 50:
            raise ValidationError("Type cannot exceed 50 characters")

        # Color validation
        if not self._is_valid_hex_color(self.color):
            raise ValidationError(
                f"Invalid color format: {self.color} (must be #RRGGBB)"
            )

        # Quantity validation
        if not isinstance(self.quantity, int) or self.quantity < 0:
            raise ValidationError("Quantity must be a non-negative integer")

        # Level validation (optional)
        if self.level is not None:
            if self.level not in VALID_LEVELS:
                raise ValidationError(
                    f"Invalid level: {self.level} (must be one of {VALID_LEVELS})"
                )

        # Notes validation (optional)
        if self.notes is not None:
            if len(self.notes) > 1000:
                raise ValidationError("Notes cannot exceed 1000 characters")

    @staticmethod
    def _is_valid_hex_color(color: str) -> bool:
        return bool(re.match(r"^#[0-9A-Fa-f]{6}$", color or ""))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "brand": self.brand.strip(),
            "name": self.name.strip(),
            "type": self.paint_type.strip(),
            "color": self.color.upper(),
            "quantity": self.quantity,
            "level": self.level,
            "notes": self.notes,
            "is_favorite": self.is_favorite,
            "notify_low_stock": self.notify_low_stock,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Paint":
        return cls(
            id=data.get("id"),
            brand=data.get("brand", ""),
            name=data.get("name", ""),
            paint_type=data.get("type", ""),
            color=data.get("color", "#000000"),
            quantity=data.get("quantity", 1),
            level=data.get("level"),
            notes=data.get("notes"),
            is_favorite=bool(data.get("is_favorite", False)),
            notify_low_stock=bool(data.get("notify_low_stock", True)),
        )


# ============================================================
# FILTER MODEL
# ============================================================

@dataclass
class PaintFilter:
    """
    Filter criteria for searching paints.

    All fields are optional. Empty filter returns all paints.
    """
    brand: Optional[str] = None
    name: Optional[str] = None
    paint_type: Optional[str] = None
    level: Optional[str] = None
    search_text: Optional[str] = None
    favorites_only: bool = False
    notify_only: bool = False   # show only paints with notify_low_stock=True

    # Sorting state
    sort_by: Optional[str] = None
    sort_desc: bool = False

    def matches(self, paint: Paint) -> bool:
        # Brand filter
        if self.brand and self.brand.lower() not in paint.brand.lower():
            return False

        # Name filter
        if self.name and self.name.lower() not in paint.name.lower():
            return False

        # Type filter
        if self.paint_type and self.paint_type.lower() != paint.paint_type.lower():
            return False

        # Level filter
        if self.level and self.level != paint.level:
            return False

        # Global search text
        if self.search_text:
            search_lower = self.search_text.lower()
            searchable = f"{paint.brand} {paint.name} {paint.paint_type}".lower()
            if search_lower not in searchable:
                return False

        # Favorites filter
        if self.favorites_only and not paint.is_favorite:
            return False

        # Notify-only filter
        if self.notify_only and not getattr(paint, "notify_low_stock", True):
            return False

        return True

    def is_empty(self) -> bool:
        return not any([
            self.brand,
            self.name,
            self.paint_type,
            self.level,
            self.search_text,
            self.favorites_only,
            self.notify_only,
        ])


# ============================================================
# STATISTICS
# ============================================================

@dataclass
class PaintStatistics:
    """Statistics about the paint collection."""
    total_count: int
    unique_brands: int
    unique_types: int
    low_stock_count: int = 0   # quantity ≤ 1
    brands_distribution: dict[str, int] = field(default_factory=dict)
    types_distribution: dict[str, int] = field(default_factory=dict)
    levels_distribution: dict[str, int] = field(default_factory=dict)