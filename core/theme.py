"""
core/theme.py
═══════════════════════════════════════════════════════════════════════════════
Theme data structures and color-science utilities.

Architecture
────────────
  Theme (dataclass)
   ├─ ThemeMeta       — id, name, author, builtin, generated_from
   ├─ ThemeColors     — full background/border/text/accent/semantic scale
   ├─ ThemeTypography — font families + size scale
   └─ ThemeShape      — border radii

  Theme.tokens() → flat {name: str} dict used for QSS template substitution
                   and Python-side color lookups via ThemeManager.token().

Paint-Scheme → Theme
────────────────────
  theme_from_paint_scheme(accent_hex, ...) derives a full dark palette from a
  single paint color using HSL manipulation:
    1. Parse accent → HSL
    2. Clamp accent lightness to a visible range (0.45–0.75)
    3. Generate extremely dark, lightly hue-tinted backgrounds
    4. Derive border and text tokens relative to the same hue
    5. Run a WCAG AA contrast guard; adjust if luminance is too low
    6. Keep danger/success/warning stable across all themes for muscle memory
"""
from __future__ import annotations

import colorsys
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

def _default_font_family() -> str:
    if sys.platform == "darwin":
        return "SF Pro Text"
    if sys.platform == "win32":
        return "Segoe UI"
    return "Ubuntu"

def _default_font_mono() -> str:
    if sys.platform == "darwin":
        return "Menlo"
    if sys.platform == "win32":
        return "Consolas"
    return "Ubuntu Mono"


# ── Color science ──────────────────────────────────────────────────────────────

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    """Returns (hue 0–1, saturation 0–1, lightness 0–1)."""
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return h, s, l


def hsl_to_hex(h: float, s: float, l: float) -> str:
    h, s, l = _clamp(h), _clamp(s), _clamp(l)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return rgb_to_hex(round(r * 255), round(g * 255), round(b * 255))


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance (0 = black, 1 = white)."""
    vals = []
    for c in hex_to_rgb(hex_color):
        v = c / 255
        vals.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def contrast_ratio(c1: str, c2: str) -> float:
    """WCAG contrast ratio.  ≥ 4.5 satisfies AA for normal text."""
    l1, l2 = relative_luminance(c1), relative_luminance(c2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def is_dark(hex_color: str) -> bool:
    return relative_luminance(hex_color) < 0.18


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class ThemeColors:
    # Background scale — deep (darkest) → input (lightest surface)
    bg_deep:    str = "#141414"
    bg_base:    str = "#1c1c1c"
    bg_raised:  str = "#212121"
    bg_input:   str = "#2a2a2a"

    # Specialised surfaces
    header_bg:  str = "#141414"
    card_bg:    str = "#1e1e1e"
    sidebar_bg: str = "#161616"

    # Border scale
    border:     str = "#363636"
    border_hi:  str = "#484848"

    # Text scale — hi (most prominent) → dim (most muted)
    text_hi:    str = "#f0f0f0"
    text_mid:   str = "#d8d8d8"
    text_lo:    str = "#909090"
    text_dim:   str = "#606060"

    # Accent / interactive
    accent:     str = "#0078d4"
    accent_hi:  str = "#1a8ee8"
    accent_lo:  str = "#0f4a7a"   # selection bg, subtle tints

    # Semantic
    danger:     str = "#e05555"
    danger_hi:  str = "#eb6868"
    danger_lo:  str = "#2a1515"
    success:    str = "#3dba6e"
    warning:    str = "#e07800"


@dataclass
class ThemeTypography:
    font_family: str = field(default_factory=_default_font_family)
    font_mono:   str = field(default_factory=_default_font_mono)
    # Pixel sizes used as integers in QSS
    font_xs:   int = 10
    font_sm:   int = 11
    font_base: int = 12
    font_lg:   int = 13
    font_xl:   int = 15
    font_2xl:  int = 18
    font_3xl:  int = 22


@dataclass
class ThemeShape:
    radius_xs:   int = 3
    radius_sm:   int = 4
    radius_base: int = 6
    radius_lg:   int = 8
    radius_xl:   int = 12


@dataclass
class ThemeMeta:
    id:             str
    name:           str
    author:         str  = "System"
    builtin:        bool = False    # system themes: read-only, cannot be deleted
    generated_from: Optional[str] = None  # paint scheme name if auto-generated


@dataclass
class Theme:
    meta:       ThemeMeta
    colors:     ThemeColors     = field(default_factory=ThemeColors)
    typography: ThemeTypography = field(default_factory=ThemeTypography)
    shape:      ThemeShape      = field(default_factory=ThemeShape)

    # ── Serialisation ────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        meta   = ThemeMeta(**data["meta"])
        colors = ThemeColors(**data.get("colors", {}))
        typo   = ThemeTypography(**data.get("typography", {}))
        shape  = ThemeShape(**data.get("shape", {}))
        return cls(meta=meta, colors=colors, typography=typo, shape=shape)

    def to_dict(self) -> dict:
        return {
            "meta":       vars(self.meta).copy(),
            "colors":     vars(self.colors).copy(),
            "typography": vars(self.typography).copy(),
            "shape":      vars(self.shape).copy(),
        }

    # ── Token API ────────────────────────────────────────────────────────

    def tokens(self) -> dict[str, str]:
        """
        Flat string dict for QSS template substitution and Python-side access.

        All values are strings (numeric tokens have no unit — ThemeManager
        appends 'px' inside the QSS template where needed).

        Key groups
        ──────────
          bg_deep / bg_base / bg_raised / bg_input / header_bg / card_bg / sidebar_bg
          border / border_hi
          text_hi / text_mid / text_lo / text_dim
          accent / accent_hi / accent_lo
          danger / danger_hi / danger_lo / success / warning
          font_family / font_mono / font_xs .. font_3xl
          radius_xs .. radius_xl
        """
        t: dict[str, str] = {}
        t.update({k: v for k, v in vars(self.colors).items()})
        t.update({k: str(v) for k, v in vars(self.typography).items()})
        t.update({k: str(v) for k, v in vars(self.shape).items()})
        return t


# ── Paint-scheme → Theme generation ───────────────────────────────────────────

def theme_from_paint_scheme(
    accent_hex: str,
    theme_name: str,
    scheme_name: str = "",
    base_theme: Optional[Theme] = None,
) -> Theme:
    """
    Derive a complete dark Theme from a single accent color.

    Typical usage — user selects a miniature paint (e.g. Citadel Macragge Blue
    #1B5299) and the system generates a coherent app theme with that color as
    the interactive accent.

    Parameters
    ----------
    accent_hex  : Hex color string, e.g. "#3A86FF"
    theme_name  : Display name for the new theme
    scheme_name : Source paint scheme name (stored in meta.generated_from)
    base_theme  : If provided, typography and shape are inherited from it

    Algorithm
    ---------
    1. Convert accent → HSL
    2. Clamp accent lightness so it reads on dark backgrounds (0.45–0.75)
    3. Build a very dark background palette with a faint hue tint
    4. Derive borders and text from the same hue, near-neutral saturation
    5. WCAG AA guard: if text_hi/bg_deep contrast < 4.5, override to near-white
    6. Keep danger/success/warning stable for cross-theme muscle memory
    """
    h, s, l = hex_to_hsl(accent_hex)

    # ── Accent ──────────────────────────────────────────────────────────
    accent_l  = _clamp(l, 0.42, 0.72)
    accent_s  = _clamp(s, 0.55, 1.0)
    accent    = hsl_to_hex(h, accent_s, accent_l)
    accent_hi = hsl_to_hex(h, accent_s, _clamp(accent_l + 0.10, 0.0, 0.88))
    accent_lo = hsl_to_hex(h, _clamp(s * 0.45, 0.08, 0.35), 0.18)

    # ── Backgrounds (barely tinted by hue) ──────────────────────────────
    bg_s = _clamp(s * 0.18, 0.0, 0.08)
    bg_deep    = hsl_to_hex(h, bg_s, 0.070)
    bg_base    = hsl_to_hex(h, bg_s, 0.105)
    bg_raised  = hsl_to_hex(h, bg_s, 0.135)
    bg_input   = hsl_to_hex(h, bg_s, 0.170)
    header_bg  = hsl_to_hex(h, bg_s, 0.060)
    card_bg    = hsl_to_hex(h, bg_s, 0.115)
    sidebar_bg = hsl_to_hex(h, bg_s, 0.078)

    # ── Borders ─────────────────────────────────────────────────────────
    bd_s    = _clamp(s * 0.10, 0.0, 0.05)
    border    = hsl_to_hex(h, bd_s, 0.22)
    border_hi = hsl_to_hex(h, bd_s, 0.30)

    # ── Text ────────────────────────────────────────────────────────────
    text_hi  = hsl_to_hex(h, 0.05, 0.93)
    text_mid = hsl_to_hex(h, 0.04, 0.85)
    text_lo  = hsl_to_hex(h, 0.03, 0.55)
    text_dim = hsl_to_hex(h, 0.02, 0.37)

    # ── WCAG AA guard ───────────────────────────────────────────────────
    if contrast_ratio(text_hi, bg_deep) < 4.5:
        text_hi = "#f0f0f0"

    colors = ThemeColors(
        bg_deep=bg_deep, bg_base=bg_base, bg_raised=bg_raised, bg_input=bg_input,
        header_bg=header_bg, card_bg=card_bg, sidebar_bg=sidebar_bg,
        border=border, border_hi=border_hi,
        text_hi=text_hi, text_mid=text_mid, text_lo=text_lo, text_dim=text_dim,
        accent=accent, accent_hi=accent_hi, accent_lo=accent_lo,
        # Semantic colors stay constant across all themes
        danger="#e05555", danger_hi="#eb6868", danger_lo="#2a1515",
        success="#3dba6e", warning="#e07800",
    )

    safe_id = re.sub(r"[^a-z0-9]+", "_", theme_name.lower()).strip("_")
    meta = ThemeMeta(
        id=f"gen_{safe_id}",
        name=theme_name,
        author="Paint Scheme Generator",
        builtin=False,
        generated_from=scheme_name or None,
    )

    typo  = base_theme.typography if base_theme else ThemeTypography()
    shape = base_theme.shape      if base_theme else ThemeShape()

    return Theme(meta=meta, colors=colors, typography=typo, shape=shape)
