# ui/animations.py
"""
Premium animation primitives for Adeptus Craftmatica.

Design principles:
  - Subtle: 150–600 ms durations — noticeable but never distracting
  - Non-blocking: all animations run asynchronously; the UI never freezes
  - Graceful: every function is try/except-wrapped so failures are silent
  - Drop-in: AnimatedProgressBar and CountUpLabel are direct subclasses

Public API:
  AnimatedProgressBar   — QProgressBar with smooth set_value_animated()
  CountUpLabel          — QLabel that counts up/down to a numeric target
  fade_in(widget)       — fade from transparent to opaque
  fade_out(widget)      — fade to transparent, with optional done callback
  pulse_widget(widget)  — brief opacity pulse for achievement / attention
  glow_flash(widget)    — drop-shadow glow burst for completion moments
  flash_error(widget)   — red border flash for error / validation feedback
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QPropertyAnimation, QTimer, Property,
)
from PySide6.QtWidgets import (
    QProgressBar, QLabel, QWidget,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QColor


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _start(anim: QPropertyAnimation) -> None:
    """Start with DeleteWhenStopped — version-safe for all PySide6 releases."""
    try:
        anim.start(QPropertyAnimation.DeleteWhenStopped)  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        try:
            anim.start()
        except Exception:
            pass


def _clear_effect(widget: QWidget) -> None:
    """Remove any QGraphicsEffect so later effects apply cleanly."""
    try:
        if widget and not widget.isHidden():
            widget.setGraphicsEffect(None)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Animated Progress Bar
# ─────────────────────────────────────────────────────────────────────────────

class AnimatedProgressBar(QProgressBar):
    """
    Drop-in QProgressBar replacement that smoothly animates value changes.

    Use exactly like QProgressBar; additionally call
    ``set_value_animated(target)`` for a premium feel.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim: QPropertyAnimation | None = None

    def set_value_animated(self, target: int, duration: int = 550) -> None:
        """Animate from current value to *target* over *duration* ms."""
        try:
            target = max(self.minimum(), min(target, self.maximum()))
            if target == self.value():
                return
            if self._anim is not None:
                try:
                    self._anim.stop()
                except Exception:
                    pass
            anim = QPropertyAnimation(self, b"value", self)
            anim.setStartValue(self.value())
            anim.setEndValue(target)
            anim.setDuration(duration)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim = anim
            _start(anim)
        except Exception:
            self.setValue(target)


# ─────────────────────────────────────────────────────────────────────────────
# Count-Up Label
# ─────────────────────────────────────────────────────────────────────────────

class CountUpLabel(QLabel):
    """
    A QLabel that animates a numeric value from its current display to a
    target, giving stat cards a satisfying "counting up" entrance effect.

    Usage::

        lbl = CountUpLabel("0")
        lbl.count_to(42)                       # int, 700 ms
        lbl.count_to(3.7, fmt="{:.1f}")        # float
        lbl.count_to(0, start=42)              # count down
    """

    def __init__(self, text: str = "0", parent=None):
        super().__init__(text, parent)
        self._val:  float = 0.0
        self._fmt:  str   = "{:.0f}"
        self._anim: QPropertyAnimation | None = None

    # ── Qt property (required for QPropertyAnimation) ────────────────────────
    def _get_val(self) -> float:
        return self._val

    def _set_val(self, v: float) -> None:
        self._val = v
        self.setText(self._fmt.format(v))

    displayValue = Property(float, _get_val, _set_val)

    # ── Public API ────────────────────────────────────────────────────────────
    def count_to(
        self,
        target: float,
        duration: int = 700,
        fmt: str = "{:.0f}",
        start: float | None = None,
    ) -> None:
        """Animate from *start* (or the current display value) to *target*."""
        try:
            self._fmt = fmt
            if self._anim is not None:
                try:
                    self._anim.stop()
                except Exception:
                    pass
            from_val = start if start is not None else self._val
            anim = QPropertyAnimation(self, b"displayValue", self)
            anim.setStartValue(float(from_val))
            anim.setEndValue(float(target))
            anim.setDuration(duration)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim = anim
            _start(anim)
        except Exception:
            self._fmt = fmt
            self.setText(fmt.format(target))


# ─────────────────────────────────────────────────────────────────────────────
# Fade
# ─────────────────────────────────────────────────────────────────────────────

def fade_in(widget: QWidget, duration: int = 220, from_opacity: float = 0.0) -> None:
    """
    Fade *widget* from *from_opacity* to 1.0.
    The opacity effect is removed when the animation finishes so it does
    not interfere with subsequent effects on the same widget.
    """
    try:
        eff = QGraphicsOpacityEffect(widget)
        eff.setOpacity(from_opacity)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setStartValue(from_opacity)
        anim.setEndValue(1.0)
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: _clear_effect(widget))
        _start(anim)
    except Exception:
        pass


def fade_out(
    widget: QWidget,
    duration: int = 200,
    on_done=None,
) -> None:
    """
    Fade *widget* to invisible, then invoke *on_done* (optional callable).
    """
    try:
        eff = QGraphicsOpacityEffect(widget)
        eff.setOpacity(1.0)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.InCubic)
        if on_done:
            anim.finished.connect(on_done)
        _start(anim)
    except Exception:
        if on_done:
            try:
                on_done()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Pulse  (achievement / attention)
# ─────────────────────────────────────────────────────────────────────────────

def pulse_widget(
    widget: QWidget,
    duration: int = 500,
    min_opacity: float = 0.25,
    cycles: int = 1,
) -> None:
    """
    Briefly dim and restore a widget's opacity.
    Perfect for drawing attention to a new stat, streak update, or
    achievement — a subtle "heartbeat" that says *something changed*.
    """
    try:
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(duration)
        anim.setKeyValueAt(0.0,  1.0)
        anim.setKeyValueAt(0.45, min_opacity)
        anim.setKeyValueAt(1.0,  1.0)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.setLoopCount(cycles)
        anim.finished.connect(lambda: _clear_effect(widget))
        _start(anim)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Glow flash  (completion moment)
# ─────────────────────────────────────────────────────────────────────────────

def glow_flash(
    widget: QWidget,
    color: str = "#3dba6e",
    radius: int = 22,
    duration: int = 900,
) -> None:
    """
    Briefly burst a colored drop-shadow glow around *widget*, then fade it.
    Intended for completion moments: milestone done, project 100%, etc.

    Example::

        glow_flash(overall_bar, color="#3dba6e")   # green completion glow
        glow_flash(streak_label, color="#f0c030")  # gold streak flash
    """
    try:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(0)
        shadow.setColor(QColor(color))
        shadow.setOffset(0, 0)
        widget.setGraphicsEffect(shadow)

        anim = QPropertyAnimation(shadow, b"blurRadius", widget)
        anim.setDuration(duration)
        anim.setKeyValueAt(0.0,  0)
        anim.setKeyValueAt(0.35, radius)
        anim.setKeyValueAt(1.0,  0)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.finished.connect(lambda: _clear_effect(widget))
        _start(anim)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Error flash  (validation feedback)
# ─────────────────────────────────────────────────────────────────────────────

def flash_error(widget: QWidget, duration: int = 500) -> None:
    """
    Briefly apply a red border to signal a validation error.
    Reliable inside layouts — no geometry changes, just a style flash.
    """
    try:
        orig = widget.styleSheet()
        widget.setStyleSheet(orig + "; border: 1px solid #e05555 !important;")
        QTimer.singleShot(
            duration,
            lambda: widget.setStyleSheet(orig) if widget else None,
        )
    except Exception:
        pass
