# plugins/paint_scheme/chroma_codex.py
"""
Chroma Codex — Intelligent Paint Planning Engine
═════════════════════════════════════════════════
Pure Python color theory engine.  No Qt, no DB — just math.

Pipeline:
  hex color + style  →  per-role target HSL  →  closest owned paint match
  →  PaletteRecommendation list

Color space: HSL  (H: 0-360, S: 0-100, L: 0-100)
Distance metric: weighted angular-HSL with circular hue
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ── Palette roles ──────────────────────────────────────────────────────────────

ROLES = [
    "primary",
    "armor_trim",
    "cloth",
    "weapons",
    "leather",
    "glow",
    "shade",
    "highlight",
    "base",
]

ROLE_META = {
    "primary":    ("🎨", "Primary"),
    "armor_trim": ("⚙",  "Armor & Trim"),
    "cloth":      ("🧶", "Cloth & Tabards"),
    "weapons":    ("⚔",  "Weapons"),
    "leather":    ("🥾", "Leather & Straps"),
    "glow":       ("✨", "Glow & Energy"),
    "shade":      ("🌑", "Shade & Wash"),
    "highlight":  ("☀",  "Edge Highlight"),
    "base":       ("🪨", "Basing & Terrain"),
}

# ── Scheme styles ──────────────────────────────────────────────────────────────

SCHEME_STYLES = [
    "Complementary",
    "High Contrast",
    "Grimdark",
    "Parade Ready",
    "Lore Accurate",
    "Accessible Contrast",
    "Custom Manual",
]

STYLE_DESCRIPTIONS = {
    "Complementary":     "Balanced split using opposite hues for natural contrast.",
    "High Contrast":     "Bold, punchy pairings — high readability at any scale.",
    "Grimdark":          "Muted, desaturated palette with deep shadows. Battle-worn aesthetic.",
    "Parade Ready":      "Bright, saturated display quality. Competition-level vibrancy.",
    "Lore Accurate":     "Faction-informed color choices based on your game system context.",
    "Accessible Contrast":"High lightness contrast — aids color-blindness and achromatopsia.",
    "Custom Manual":     "No auto-generation — build your palette step by step.",
}


# ── Color math ────────────────────────────────────────────────────────────────

def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (128, 128, 128)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return (128, 128, 128)


def rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    r_, g_, b_ = r / 255, g / 255, b / 255
    cmax, cmin = max(r_, g_, b_), min(r_, g_, b_)
    delta = cmax - cmin
    l = (cmax + cmin) / 2

    if delta == 0:
        return 0.0, 0.0, round(l * 100, 2)

    s = delta / (1 - abs(2 * l - 1))

    if cmax == r_:
        h = 60 * (((g_ - b_) / delta) % 6)
    elif cmax == g_:
        h = 60 * ((b_ - r_) / delta + 2)
    else:
        h = 60 * ((r_ - g_) / delta + 4)

    return round(h % 360, 2), round(s * 100, 2), round(l * 100, 2)


def hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    s_, l_ = s / 100, l / 100
    c = (1 - abs(2 * l_ - 1)) * s_
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l_ - c / 2

    if   0   <= h < 60:  r_, g_, b_ = c, x, 0
    elif 60  <= h < 120: r_, g_, b_ = x, c, 0
    elif 120 <= h < 180: r_, g_, b_ = 0, c, x
    elif 180 <= h < 240: r_, g_, b_ = 0, x, c
    elif 240 <= h < 300: r_, g_, b_ = x, 0, c
    else:                r_, g_, b_ = c, 0, x

    return (
        min(255, max(0, round((r_ + m) * 255))),
        min(255, max(0, round((g_ + m) * 255))),
        min(255, max(0, round((b_ + m) * 255))),
    )


def hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = hsl_to_rgb(h, s, l)
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_hsl(hex_str: str) -> tuple[float, float, float]:
    return rgb_to_hsl(*hex_to_rgb(hex_str))


def hue_distance(h1: float, h2: float) -> float:
    """Shortest angular distance between two hues, normalised 0-1."""
    d = abs(h1 - h2) % 360
    return min(d, 360 - d) / 180.0


def color_distance(hex1: str, hex2: str) -> float:
    """
    Perceptual distance 0 (identical) to 1 (opposite).
    Weights: hue 50%, lightness 35%, saturation 15%.
    """
    h1, s1, l1 = hex_to_hsl(hex1)
    h2, s2, l2 = hex_to_hsl(hex2)
    dh = hue_distance(h1, h2)
    dl = abs(l1 - l2) / 100.0
    ds = abs(s1 - s2) / 100.0
    return dh * 0.50 + dl * 0.35 + ds * 0.15


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── Role target generation ─────────────────────────────────────────────────────

def _target_hsl(role: str, ph: float, ps: float, pl: float,
                style: str) -> tuple[float, float, float]:
    """
    Compute the ideal HSL for a palette role given the primary color HSL
    and the scheme style.
    """
    h, s, l = ph, ps, pl   # start from primary

    # ── Role base rules ──────────────────────────────────────────────────────
    if role == "primary":
        pass  # identity

    elif role == "armor_trim":
        # Metallic complementary: desaturated, complementary hue, mid-light
        h = (h + 180) % 360
        s = clamp(s * 0.3, 5, 20)
        l = clamp(l * 0.9 + 15, 35, 65)

    elif role == "cloth":
        # Analogous, slightly lighter and less saturated
        h = (h + 30) % 360
        s = clamp(s * 0.75, 20, 70)
        l = clamp(l + 10, 30, 75)

    elif role == "weapons":
        # Desaturated dark metal
        s = clamp(s * 0.1, 2, 12)
        l = clamp(35, 25, 50)

    elif role == "leather":
        # Warm brown — lock to warm brown regardless of primary
        h = 22
        s = clamp(55, 35, 65)
        l = clamp(28, 20, 40)

    elif role == "glow":
        # Triadic accent — vibrant, opposite energy to armor
        h = (h + 120) % 360
        s = clamp(max(s, 60), 55, 95)
        l = clamp(l * 0.9 + 5, 40, 65)

    elif role == "shade":
        # Much darker, slightly more saturated version of primary
        s = clamp(s * 1.15, 0, 100)
        l = clamp(l * 0.38, 5, 30)

    elif role == "highlight":
        # Much lighter, slightly desaturated
        s = clamp(s * 0.75, 0, 80)
        l = clamp(l * 0.55 + 50, 65, 92)

    elif role == "base":
        # Earth tone — low sat, dark
        h = clamp(h * 0.3 + 20, 5, 45)
        s = clamp(20, 10, 35)
        l = clamp(22, 15, 35)

    # ── Style modifiers ──────────────────────────────────────────────────────
    if style == "Grimdark":
        s = clamp(s * 0.55, 0, 60)
        if role not in ("shade",):
            l = clamp(l * 0.85 + 2, 5, 70)
        if role == "highlight":
            l = clamp(l * 0.85, 40, 72)

    elif style == "Parade Ready":
        s = clamp(s * 1.35, 10, 100)
        if role == "highlight":
            l = clamp(l + 8, 60, 96)
        if role == "primary":
            l = clamp(l + 5, 30, 75)

    elif style == "High Contrast":
        if role in ("shade",):
            l = clamp(l * 0.7, 5, 25)
        if role in ("highlight",):
            l = clamp(l + 12, 68, 95)
        if role in ("glow",):
            s = clamp(s * 1.4, 60, 100)

    elif style == "Accessible Contrast":
        # Push lightness to extremes for accessibility
        if role in ("shade", "weapons", "base", "leather"):
            l = clamp(l * 0.7, 8, 30)
        if role in ("highlight", "cloth"):
            l = clamp(l + 15, 70, 95)
            s = clamp(s * 0.6, 0, 50)

    elif style == "Lore Accurate":
        # No change — UI will show faction hint text
        pass

    return h % 360, clamp(s, 0, 100), clamp(l, 0, 100)


# ── Recommendation data ────────────────────────────────────────────────────────

@dataclass
class PaintMatch:
    paint_id:   int
    paint_name: str
    brand:      str
    color_hex:  str
    distance:   float          # 0 = perfect, 1 = opposite
    quantity:   int = 1
    level:      Optional[str] = None
    is_low:     bool = False   # quantity <= 1


@dataclass
class RoleRecommendation:
    role:        str
    icon:        str
    label:       str
    target_hex:  str           # ideal generated color
    best_match:  Optional[PaintMatch] = None
    alternatives: list[PaintMatch] = field(default_factory=list)

    @property
    def is_owned(self) -> bool:
        return self.best_match is not None and self.best_match.distance < 0.30

    @property
    def match_quality(self) -> str:
        """'excellent' / 'good' / 'fair' / 'none'"""
        if not self.best_match:
            return "none"
        d = self.best_match.distance
        if d < 0.10: return "excellent"
        if d < 0.20: return "good"
        if d < 0.30: return "fair"
        return "none"


@dataclass
class ChromaResult:
    primary_hex:     str
    style:           str
    recommendations: dict[str, RoleRecommendation]   # role → rec

    @property
    def owned_count(self) -> int:
        return sum(1 for r in self.recommendations.values() if r.is_owned)

    @property
    def missing_roles(self) -> list[RoleRecommendation]:
        return [r for r in self.recommendations.values() if not r.is_owned]


# ── Engine ────────────────────────────────────────────────────────────────────

# Good-match distance threshold
_GOOD_MATCH = 0.30
# Number of alternatives to surface
_ALT_COUNT  = 3


class ChromaEngine:
    """
    Stateless engine.  Call generate() with a primary hex, style,
    and a list of Paint-like objects (must have .id, .name, .brand,
    .color, .quantity, .level).
    """

    def generate(self, primary_hex: str, style: str,
                 owned_paints: list) -> ChromaResult:
        if not primary_hex.startswith("#") or len(primary_hex) != 7:
            primary_hex = "#888888"

        ph, ps, pl = hex_to_hsl(primary_hex)

        recs: dict[str, RoleRecommendation] = {}
        for role in ROLES:
            icon, label = ROLE_META[role]
            th, ts, tl  = _target_hsl(role, ph, ps, pl, style)
            target_hex  = hsl_to_hex(th, ts, tl)

            best, alts = self._match(target_hex, owned_paints)
            recs[role] = RoleRecommendation(
                role=role, icon=icon, label=label,
                target_hex=target_hex,
                best_match=best,
                alternatives=alts,
            )

        return ChromaResult(
            primary_hex=primary_hex,
            style=style,
            recommendations=recs,
        )

    def _match(self, target_hex: str,
               paints: list) -> tuple[Optional[PaintMatch], list[PaintMatch]]:
        """Find the closest paint(s) from the owned collection."""
        scored: list[tuple[float, PaintMatch]] = []
        for p in paints:
            color = getattr(p, "color", None)
            if not color or not color.startswith("#"):
                continue
            dist = color_distance(target_hex, color)
            qty  = getattr(p, "quantity", 1) or 1
            lvl  = getattr(p, "level", None)
            is_low = qty <= 1
            pm = PaintMatch(
                paint_id=p.id,
                paint_name=getattr(p, "name", "?"),
                brand=getattr(p, "brand", ""),
                color_hex=color,
                distance=round(dist, 4),
                quantity=qty,
                level=lvl,
                is_low=is_low,
            )
            scored.append((dist, pm))

        if not scored:
            return None, []

        scored.sort(key=lambda x: x[0])
        best_dist, best = scored[0]
        best_match = best if best_dist < _GOOD_MATCH else None
        alts = [pm for _, pm in scored[1:_ALT_COUNT + 1]]
        return best_match, alts


# Singleton — UI imports this
engine = ChromaEngine()
