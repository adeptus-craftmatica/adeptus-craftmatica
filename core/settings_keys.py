# core/settings_keys.py
"""
Centralised settings key constants (M-06).

Import this module wherever settings keys are read or written to prevent
silent typos that create orphaned keys.

Usage::

    from core.settings_keys import Keys
    settings.set(Keys.APP_THEME, "dark")
    theme = settings.get(Keys.APP_THEME, "dark")
"""


class Keys:
    # ── Application ───────────────────────────────────────────────────────────
    APP_THEME          = "app.theme"
    APP_WINDOW_WIDTH   = "app.window_width"
    APP_WINDOW_HEIGHT  = "app.window_height"

    # ── Plugin layout ─────────────────────────────────────────────────────────
    PLUGIN_ORDER    = "plugin_layout.order"
    PLUGIN_LABELS   = "plugin_layout.labels"
    PLUGIN_DISABLED = "plugin_layout.disabled"

    # ── User profile ──────────────────────────────────────────────────────────
    USER_DISPLAY_NAME = "user.display_name"

    # ── Dashboard ─────────────────────────────────────────────────────────────
    DASHBOARD_HOBBY_STREAK       = "dashboard.hobby_streak"
    DASHBOARD_LAST_SESSION_DATE  = "dashboard.last_session_date"
    DASHBOARD_SESSION_DATES      = "dashboard.session_dates"
    DASHBOARD_RECENT_ACTIVITY    = "dashboard.recent_activity"

    # ── Paint tracker ─────────────────────────────────────────────────────────
    PAINT_DEFAULT_BRAND = "paint_tracker.default_brand"
    PAINT_DEFAULT_TYPE  = "paint_tracker.default_type"

    # ── Session resume ────────────────────────────────────────────────────────
    LAST_PLUGIN_TAB      = "app.last_plugin_tab"       # plugin_id of last active tab
    LAST_PROJECT_ID      = "project_tracker.last_project_id"

    # ── Saved views ───────────────────────────────────────────────────────────
    PROJECT_STATUS_FILTER = "project_tracker.status_filter"  # saved list-panel filter

    # ── Dashboard personalisation ─────────────────────────────────────────────
    DASHBOARD_PINNED_PROJECTS = "dashboard.pinned_projects"   # JSON list of project IDs
