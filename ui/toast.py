# ui/toast.py
"""
Premium toast notification system for Adeptus Craftmatica.

Provides a global ToastManager singleton that displays brief, non-blocking
notifications at the bottom-center of the main window.  Each toast slides
up from below, holds for a moment, then fades out cleanly.

Setup (once, in MainWindow.__init__ after the window is visible):
    from ui.toast import ToastManager
    ToastManager.instance().attach(self.centralWidget())

Usage from anywhere:
    from ui.toast import ToastManager
    ToastManager.instance().show("Project saved.")
    ToastManager.instance().show("3 paints low on stock.", level="warning")
    ToastManager.instance().show("Something went wrong.", level="error")
    ToastManager.instance().show("🎉  Project complete!", level="celebration", duration=5000)

Levels: "success" | "error" | "warning" | "info" | "celebration"
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QObject, QPoint,
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QLabel, QPushButton, QApplication,
)
from PySide6.QtGui import QColor

from ui.animations import fade_out


# ── Visual style per level ─────────────────────────────────────────────────

_STYLES: dict[str, dict] = {
    "success": {
        "bg": "#0d2818", "border": "#1e5035",
        "text": "#4dca7e", "icon": "✓",
    },
    "error": {
        "bg": "#2a1515", "border": "#6a2525",
        "text": "#e86060", "icon": "✕",
    },
    "warning": {
        "bg": "#281e00", "border": "#5a3a00",
        "text": "#e08030", "icon": "⚠",
    },
    "info": {
        "bg": "#0a2035", "border": "#184868",
        "text": "#48b0f0", "icon": "ℹ",
    },
    "celebration": {
        "bg": "#28200a", "border": "#7a6020",
        "text": "#f0c030", "icon": "★",
    },
}

_TOAST_HEIGHT    = 46    # approx height for stacking maths
_TOAST_GAP       = 8     # gap between stacked toasts
_MARGIN_BOTTOM   = 22    # distance from parent bottom edge
_SLIDE_DISTANCE  = 16    # px slide-up entry distance


# ─────────────────────────────────────────────────────────────────────────────
# Single Toast
# ─────────────────────────────────────────────────────────────────────────────

class _Toast(QFrame):
    """
    One toast notification.  Created by ToastManager; manages its own
    slide-in → hold → fade-out lifecycle.
    """

    def __init__(
        self,
        message:      str,
        level:        str = "success",
        parent:       QWidget | None = None,
        duration:     int = 3000,
        stack_offset: int = 0,
        action_label: Optional[str] = None,
        action_fn:    Optional[Callable] = None,
    ):
        super().__init__(parent)
        self._duration     = duration
        self._stack_offset = stack_offset
        style = _STYLES.get(level, _STYLES["info"])

        # ── Widget setup ──────────────────────────────────────────────────────
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("toastFrame")
        self.setStyleSheet(f"""
            QFrame#toastFrame {{
                background-color: {style['bg']};
                border: 1px solid {style['border']};
                border-radius: 9px;
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        icon_lbl = QLabel(style["icon"])
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 700; "
            f"color: {style['text']}; background: transparent;"
        )
        lay.addWidget(icon_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 500; "
            f"color: {style['text']}; background: transparent;"
        )
        msg_lbl.setTextFormat(Qt.PlainText)
        lay.addWidget(msg_lbl)

        # ── Optional action button (e.g. "Undo") ─────────────────────────────
        if action_label and action_fn:
            sep = QLabel("·")
            sep.setStyleSheet(
                f"font-size: 13px; color: {style['text']}; "
                f"background: transparent; opacity: 0.5;"
            )
            lay.addWidget(sep)

            _fn = action_fn   # local ref for closure
            def _clicked(_fn=_fn):
                try:
                    _fn()
                except Exception as e:
                    print(f"[TOAST ACTION] {e}")
                self._dismiss()

            act_btn = QPushButton(action_label)
            act_btn.setCursor(Qt.PointingHandCursor)
            act_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {style['text']};
                    background: transparent;
                    border: 1px solid {style['border']};
                    border-radius: 5px;
                    padding: 2px 10px;
                    font-size: 12px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.12);
                }}
                QPushButton:pressed {{
                    background-color: rgba(255, 255, 255, 0.20);
                }}
            """)
            act_btn.setFixedHeight(26)
            act_btn.clicked.connect(_clicked)
            lay.addWidget(act_btn)

        self.setFixedHeight(_TOAST_HEIGHT)
        self.adjustSize()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def show_animated(self) -> None:
        """Position in parent, slide up, hold, then auto-dismiss."""
        parent = self.parent()
        if not isinstance(parent, QWidget) or not parent.isVisible():
            self.deleteLater()
            return

        pw = parent.width()
        ph = parent.height()
        w  = max(self.sizeHint().width() + 4, 260)
        w  = min(w, pw - 40)
        self.setFixedWidth(w)

        x_center = (pw - w) // 2
        y_final  = ph - _TOAST_HEIGHT - _MARGIN_BOTTOM - self._stack_offset
        y_start  = y_final + _SLIDE_DISTANCE

        self.move(x_center, y_start)
        self.show()
        self.raise_()

        # Slide up
        pos_anim = QPropertyAnimation(self, b"pos", self)
        pos_anim.setStartValue(QPoint(x_center, y_start))
        pos_anim.setEndValue(QPoint(x_center, y_final))
        pos_anim.setDuration(200)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        try:
            pos_anim.start(QPropertyAnimation.DeleteWhenStopped)  # type: ignore
        except (AttributeError, TypeError):
            pos_anim.start()

        # Fade in simultaneously
        from ui.animations import fade_in
        fade_in(self, duration=170)

        # Auto-dismiss
        QTimer.singleShot(self._duration, self._dismiss)

    def _dismiss(self) -> None:
        fade_out(self, duration=260, on_done=self.deleteLater)


# ─────────────────────────────────────────────────────────────────────────────
# Toast Manager
# ─────────────────────────────────────────────────────────────────────────────

class ToastManager(QObject):
    """
    Singleton manager for all toast notifications.

    Attach once to the main window's central widget, then call .show()
    from anywhere in the codebase without worrying about parenting.
    """

    _instance: "ToastManager | None" = None

    def __init__(self):
        super().__init__()
        self._parent: QWidget | None = None
        self._active: list[_Toast]   = []

    @classmethod
    def instance(cls) -> "ToastManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def attach(self, parent: QWidget) -> None:
        """
        Attach to the main window's central widget.
        Call this once after the window is visible.
        """
        self._parent = parent

    def show(
        self,
        message:      str,
        level:        str = "success",
        duration:     int = 3000,
        action_label: Optional[str] = None,
        action_fn:    Optional[Callable] = None,
    ) -> None:
        """
        Display a toast notification.

        Toasts stack upward if multiple are visible simultaneously.
        Each auto-dismisses after *duration* ms.

        :param message:      Plain-text message (no HTML).
        :param level:        "success" | "error" | "warning" | "info" | "celebration".
        :param duration:     Milliseconds to hold before fading out.
        :param action_label: Optional button label shown on the toast (e.g. "Undo").
        :param action_fn:    Zero-argument callable invoked when the button is clicked.
                             The toast dismisses immediately after the callback runs.
        """
        parent = self._resolve_parent()
        if parent is None:
            return

        # Prune stale refs first — must be outside the try block so that a
        # RuntimeError from a half-deleted C++ object cannot silently swallow
        # the entire toast creation that follows.
        self._prune()

        try:
            # Stack offset: each still-alive toast adds vertical space
            offset = len(self._active) * (_TOAST_HEIGHT + _TOAST_GAP)

            toast = _Toast(
                message=message,
                level=level,
                parent=parent,
                duration=duration,
                stack_offset=offset,
                action_label=action_label,
                action_fn=action_fn,
            )
            # Use a plain Python flag so the destroyed callback never has to
            # call isVisible() on an already-deleted C++ object.
            toast._manager_alive = True
            toast.destroyed.connect(lambda _=None: self._prune())
            self._active.append(toast)
            toast.show_animated()
        except Exception:
            pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resolve_parent(self) -> QWidget | None:
        if self._parent and self._parent.isVisible():
            return self._parent
        # Fallback: use the active main window
        app = QApplication.instance()
        if app:
            w = app.activeWindow()
            if w:
                cw = w.centralWidget() if hasattr(w, "centralWidget") else w
                return cw or w
        return None

    @staticmethod
    def _alive(t: "_Toast") -> bool:
        """
        Safe liveness check for a _Toast.

        When Qt calls deleteLater() the C++ side is torn down before the
        Python wrapper is garbage-collected, so calling any Qt method on it
        raises RuntimeError (libshiboken: Internal C++ object already deleted).
        We catch that here so callers never have to worry about it.
        """
        try:
            return t is not None and t.isVisible()
        except RuntimeError:
            return False

    def _prune(self) -> None:
        self._active = [t for t in self._active if self._alive(t)]
