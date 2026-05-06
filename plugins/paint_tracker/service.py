"""
Paint Tracker Service (Refactored)

Key Improvements:
- Perceptually accurate color matching using HSV color space
- Weighted matching: hue (most important), saturation, brightness
- Adaptive tolerance based on color characteristics
- Better sorting and safer attribute access
"""

from __future__ import annotations
from typing import Optional, Iterable
import colorsys

from .models import Paint, PaintFilter, PaintStatistics, ValidationError
from .repository import PaintRepository


class PaintService:
    def __init__(self, repository: PaintRepository):
        self.repo = repository

    # ============================================================
    # CORE OPERATIONS
    # ============================================================

    def add_paint(
        self,
        brand: str,
        name: str,
        paint_type: str,
        color: str,
        quantity: int = 1,
        level: Optional[str] = None,
        notes: Optional[str] = None,
        is_favorite: bool = False,
        notify_low_stock: bool = True,
    ) -> Paint:
        paint = Paint(
            brand=brand,
            name=name,
            paint_type=paint_type,
            color=color,
            quantity=quantity,
            level=level,
            notes=notes,
            is_favorite=is_favorite,
            notify_low_stock=notify_low_stock,
        )

        if self._is_duplicate(paint):
            raise ValidationError(f"Paint '{brand} - {name}' already exists")

        paint_id = self.repo.add(paint)

        return Paint(
            id=paint_id,
            brand=paint.brand,
            name=paint.name,
            paint_type=paint.paint_type,
            color=paint.color,
            quantity=paint.quantity,
            level=paint.level,
            notes=paint.notes,
            is_favorite=paint.is_favorite,
            notify_low_stock=paint.notify_low_stock,
        )

    def update_paint(
        self,
        paint_id: int,
        brand: str,
        name: str,
        paint_type: str,
        color: str,
        quantity: int = 1,
        level: Optional[str] = None,
        notes: Optional[str] = None,
        is_favorite: bool = False,
        notify_low_stock: bool = True,
    ) -> Paint:
        updated = Paint(
            id=paint_id,
            brand=brand,
            name=name,
            paint_type=paint_type,
            color=color,
            quantity=quantity,
            level=level,
            notes=notes,
            is_favorite=is_favorite,
            notify_low_stock=notify_low_stock,
        )

        if not self.repo.get_by_id(paint_id):
            raise ValueError(f"Paint with ID {paint_id} not found")

        if self._is_duplicate(updated, exclude_id=paint_id):
            raise ValidationError(f"Paint '{brand} - {name}' already exists")

        success = self.repo.update(updated)

        if not success:
            raise ValueError(f"Failed to update paint {paint_id}")

        return updated

    def get_favorites(self) -> list[Paint]:
        """Return all paints marked as favourite."""
        return [p for p in self.repo.get_all() if p.is_favorite]

    def get_low_stock_notifiable(self) -> list[Paint]:
        """Return low/out-of-stock paints that have notifications enabled."""
        return [p for p in self.repo.get_all()
                if p.quantity <= 1 and p.notify_low_stock]

    def remove_paint(self, paint_id: int) -> bool:
        return self.repo.delete(paint_id)

    def get_paint(self, paint_id: int) -> Optional[Paint]:
        return self.repo.get_by_id(paint_id)

    def get_all_paints(self) -> list[Paint]:
        return self.repo.get_all()

    # ============================================================
    # SEARCH + SORT
    # ============================================================

    def search_paints(self, filter: PaintFilter) -> list[Paint]:
        paints = self.repo.find(filter)

        if filter.sort_by:
            try:
                paints.sort(
                    key=lambda p: getattr(p, filter.sort_by, ""),
                    reverse=filter.sort_desc
                )
            except Exception as e:
                print(f"[SERVICE WARNING] Sorting failed: {e}")

        return paints

    # ============================================================
    # STATISTICS
    # ============================================================

    def get_statistics(self) -> PaintStatistics:
        return PaintStatistics(
            total_count=self.repo.count(),
            unique_brands=len(self.repo.get_unique_brands()),
            unique_types=len(self.repo.get_unique_types()),
            brands_distribution=self.repo.count_by_brand(),
            types_distribution=self.repo.count_by_type(),
            levels_distribution=self.repo.count_by_level(),
        )

    def get_statistics_from_subset(self, paints: list[Paint]) -> PaintStatistics:
        brands = {}
        types = {}
        levels = {}

        for p in paints:
            brands[p.brand] = brands.get(p.brand, 0) + 1
            types[p.paint_type] = types.get(p.paint_type, 0) + 1

            level_key = p.level if p.level else ""
            levels[level_key] = levels.get(level_key, 0) + 1

        low_stock = sum(1 for p in paints if p.quantity <= 1)

        return PaintStatistics(
            total_count=len(paints),
            unique_brands=len(brands),
            unique_types=len(types),
            low_stock_count=low_stock,
            brands_distribution=brands,
            types_distribution=types,
            levels_distribution=levels,
        )

    def get_brands(self) -> list[str]:
        return sorted({b.strip() for b in self.repo.get_unique_brands() if b and b.strip()})

    def get_types(self) -> list[str]:
        return sorted({t.strip() for t in self.repo.get_unique_types() if t and t.strip()})

    def get_levels(self) -> list[str]:
        return sorted({l.strip() for l in self.repo.get_unique_levels() if l and l.strip()})

    # ============================================================
    # 🔥 COLOR FILTER (PERCEPTUALLY ACCURATE)
    # ============================================================

    def find_paints_by_color(
        self,
        target_hex: str,
        paints: Optional[Iterable[Paint]] = None,
        tolerance: int = 150
    ) -> list[Paint]:
        """
        Find paints close to a target color using strict HSV matching.

        Strategy:
        - Hue must match within a tight range (primary filter)
        - Saturation and value can vary more (allows light/dark variants)
        - Special handling for near-grays (low saturation colors)

        This ensures when you pick RED, you only get reds (not oranges/pinks).
        When you pick BLUE, you only get blues (not purples/teals).

        Args:
            target_hex: Target color in #RRGGBB format (or None/empty to return all)
            paints: Optional subset to filter from
            tolerance: Ignored - using strict hue-based matching instead

        Returns:
            List of paints sorted by perceptual similarity
        """

        # If no target color specified, return all paints
        if not target_hex or len(target_hex) != 7 or not target_hex.startswith("#"):
            return list(paints) if paints else self.repo.get_all()

        paints = list(paints) if paints else self.repo.get_all()

        try:
            target_hsv = self._hex_to_hsv(target_hex)
        except Exception as e:
            print(f"[SERVICE WARNING] Invalid target color {target_hex}: {e}")
            # Return all paints on error instead of empty list
            return paints

        target_hue, target_sat, target_val = target_hsv

        # Determine if target is a gray/neutral (low saturation)
        is_target_gray = target_sat < 15

        matches = []

        for paint in paints:
            try:
                paint_hsv = self._hex_to_hsv(paint.color)
                paint_hue, paint_sat, paint_val = paint_hsv

                is_paint_gray = paint_sat < 15

                # Both gray/neutral - match only grays
                if is_target_gray and is_paint_gray:
                    # For grays, only compare value (brightness)
                    val_diff = abs(target_val - paint_val)
                    if val_diff <= 40:  # Allow brightness variance
                        matches.append((val_diff, paint))
                    continue

                # Target is gray but paint isn't (or vice versa) - skip
                if is_target_gray != is_paint_gray:
                    continue

                # Both are saturated colors - strict hue matching
                hue_diff = self._hue_distance(target_hue, paint_hue)

                # STRICT hue tolerance - only colors in the same family
                # 30 degrees = very tight (red stays red, blue stays blue)
                if hue_diff > 30:
                    continue

                # Calculate weighted distance for ranking
                sat_diff = abs(target_sat - paint_sat)
                val_diff = abs(target_val - paint_val)

                # Weighted score: hue most important, then saturation, then value
                score = (hue_diff * 3.0) + (sat_diff * 1.0) + (val_diff * 0.5)

                matches.append((score, paint))

            except Exception as e:
                print(f"[SERVICE WARNING] Invalid paint color {paint.color}: {e}")
                continue

        # Sort by score (lowest = best match)
        matches.sort(key=lambda x: x[0])

        return [p for _, p in matches]

    # ============================================================
    # 🔧 COLOR HELPERS (PERCEPTUALLY ACCURATE)
    # ============================================================

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple (0-255 range)"""
        hex_color = hex_color.strip().lstrip("#").upper()

        if len(hex_color) != 6:
            raise ValueError(f"Invalid hex color: {hex_color}")

        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def _hex_to_hsv(self, hex_color: str) -> tuple[float, float, float]:
        """
        Convert hex color to HSV tuple.

        Returns:
            (hue [0-360], saturation [0-100], value [0-100])
        """
        r, g, b = self._hex_to_rgb(hex_color)
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

        return (h * 360, s * 100, v * 100)

    def _hue_distance(self, hue1: float, hue2: float) -> float:
        """
        Calculate the shortest distance between two hues on the color wheel.

        Hue is circular (0-360 degrees), so we need to account for wraparound.
        For example, 350° and 10° are only 20° apart, not 340°.

        Returns:
            Distance in degrees (0-180)
        """
        diff = abs(hue1 - hue2)
        if diff > 180:
            diff = 360 - diff
        return diff

    # ============================================================
    # BULK
    # ============================================================

    def import_paints(self, paints: list[dict]) -> tuple[int, list[str]]:
        success_count = 0
        errors = []

        for i, paint_data in enumerate(paints):
            try:
                self.add_paint(
                    brand=paint_data.get("brand", ""),
                    name=paint_data.get("name", ""),
                    paint_type=paint_data.get("type", ""),
                    color=paint_data.get("color", "#000000"),
                    quantity=paint_data.get("quantity", 1),
                    level=paint_data.get("level"),
                    notes=paint_data.get("notes"),
                )
                success_count += 1
            except (ValidationError, Exception) as e:
                errors.append(f"Row {i+1}: {str(e)}")

        return success_count, errors

    def clear_collection(self) -> int:
        return self.repo.delete_all()

    # ============================================================
    # BUSINESS RULES
    # ============================================================

    def _is_duplicate(self, paint: Paint, exclude_id: Optional[int] = None) -> bool:
        for existing in self.repo.get_all():
            if exclude_id and existing.id == exclude_id:
                continue

            if (
                existing.brand.lower() == paint.brand.lower()
                and existing.name.lower() == paint.name.lower()
            ):
                return True

        return False

    # ============================================================
    # VALIDATION
    # ============================================================

    def validate_paint_data(
        self,
        brand: str,
        name: str,
        paint_type: str,
        color: str,
        quantity: int = 1,
        level: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> tuple[bool, str]:
        try:
            Paint(
                brand=brand,
                name=name,
                paint_type=paint_type,
                color=color,
                quantity=quantity,
                level=level,
                notes=notes,
            )
            return True, ""
        except ValidationError as e:
            return False, str(e)


# ============================================================
# AUTO-REGISTRATION
# ============================================================

def register(context):
    print("[PAINT_TRACKER] Registering service...")

    db = context.services.get("db")

    repo = PaintRepository(db)
    service = PaintService(repo)

    context.services.register("paint_service", service, override=True)

    print("[PAINT_TRACKER] Service registered")

    return service