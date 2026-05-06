# plugins/project_tracker/models.py
"""
Project Tracker — domain models.

A Project is the top-level hobby entity.  Every other tracked item
(model, paint, army list, campaign, calendar event, session) can be
linked to a project via the ProjectLink junction record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Enums / constants
# ─────────────────────────────────────────────────────────────────────────────

class ProjectStatus:
    ACTIVE    = "active"
    COMPLETED = "completed"
    ON_HOLD   = "on_hold"
    ARCHIVED  = "archived"

    ALL = [ACTIVE, COMPLETED, ON_HOLD, ARCHIVED]
    LABELS = {
        ACTIVE:    "Active",
        COMPLETED: "Completed",
        ON_HOLD:   "On Hold",
        ARCHIVED:  "Archived",
    }


class ProjectCategory:
    ARMY      = "army"
    DIORAMA   = "diorama"
    VEHICLE   = "vehicle"
    CHARACTER = "character"
    TERRAIN   = "terrain"
    CAMPAIGN  = "campaign"
    COLLECTION = "collection"
    OTHER     = "other"

    ALL = [ARMY, DIORAMA, VEHICLE, CHARACTER, TERRAIN, CAMPAIGN, COLLECTION, OTHER]
    LABELS = {
        ARMY:       "Army",
        DIORAMA:    "Diorama",
        VEHICLE:    "Vehicle",
        CHARACTER:  "Character",
        TERRAIN:    "Terrain",
        CAMPAIGN:   "Campaign",
        COLLECTION: "Collection",
        OTHER:      "Other",
    }
    ICONS = {
        ARMY:       "⚔",
        DIORAMA:    "🏛",
        VEHICLE:    "🚗",
        CHARACTER:  "👤",
        TERRAIN:    "🏔",
        CAMPAIGN:   "📖",
        COLLECTION: "🗂",
        OTHER:      "📁",
    }


class ProjectPriority:
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"

    ALL = [HIGH, MEDIUM, LOW]
    LABELS = {
        HIGH:   "High",
        MEDIUM: "Medium",
        LOW:    "Low",
    }
    COLORS = {
        HIGH:   "#c62828",
        MEDIUM: "#e07820",
        LOW:    "#2e7d32",
    }


class GalleryStage:
    BEFORE    = "before"
    DURING    = "during"
    AFTER     = "after"
    REFERENCE = "reference"
    COMPLETED = "completed"
    NONE      = ""

    ALL = [BEFORE, DURING, AFTER, REFERENCE, COMPLETED]
    LABELS = {
        BEFORE:    "Before",
        DURING:    "During",
        AFTER:     "After",
        REFERENCE: "Reference",
        COMPLETED: "Completed",
        NONE:      "—",
    }
    COLORS = {
        BEFORE:    "#5c6bc0",
        DURING:    "#e07820",
        AFTER:     "#2e7d32",
        REFERENCE: "#0078d4",
        COMPLETED: "#8338ec",
        NONE:      "#606060",
    }


class EnabledSystem:
    """Feature module identifiers for per-project enabled_systems list."""
    MODELS     = "models"
    PAINTS     = "paints"
    ARMIES     = "armies"
    MATERIALS  = "materials"
    TOOLS      = "tools"
    SESSIONS   = "sessions"
    MILESTONES = "milestones"
    NOTES      = "notes"
    LINKS      = "links"

    ALL = [MODELS, PAINTS, ARMIES, MATERIALS, TOOLS, SESSIONS, MILESTONES, NOTES, LINKS]
    LABELS = {
        MODELS:     "Models",
        PAINTS:     "Paints",
        ARMIES:     "Armies",
        MATERIALS:  "Materials",
        TOOLS:      "Tools",
        SESSIONS:   "Sessions",
        MILESTONES: "Milestones",
        NOTES:      "Notes",
        LINKS:      "Links",
    }
    # Default set when no preference stored.
    # LINKS is intentionally excluded — it is auto-enabled transparently
    # the first time the user links an entity to a project.
    DEFAULT = [MODELS, PAINTS, SESSIONS, MILESTONES, NOTES]


class EntityType:
    """Types of entities that can be linked to a project."""
    MODEL    = "model"
    PAINT    = "paint"
    ARMY     = "army"
    CAMPAIGN = "campaign"
    EVENT    = "event"
    SCHEME   = "scheme"
    PURCHASE = "purchase"

    ALL = [MODEL, PAINT, ARMY, CAMPAIGN, EVENT, SCHEME, PURCHASE]
    LABELS = {
        MODEL:    "Models",
        PAINT:    "Paints",
        ARMY:     "Army Lists",
        CAMPAIGN: "Campaigns",
        EVENT:    "Calendar Events",
        SCHEME:   "Paint Schemes",
        PURCHASE: "Purchases",
    }
    ICONS = {
        MODEL:    "🤖",
        PAINT:    "🎨",
        ARMY:     "⚔",
        CAMPAIGN: "📖",
        EVENT:    "📅",
        SCHEME:   "🎭",
        PURCHASE: "🛒",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_json_list(raw) -> list:
    """Safely parse a JSON list stored as TEXT in SQLite. Returns [] on any error."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def _dump_json_list(lst) -> str:
    """Serialize a list to JSON string for SQLite storage."""
    return json.dumps(lst or [])


# ─────────────────────────────────────────────────────────────────────────────
# Core domain objects
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Project:
    id:              Optional[int]  = None
    name:            str            = ""
    description:     str            = ""
    game_system:     str            = ""       # "Warhammer 40K", "AoS", "D&D", …
    status:          str            = ProjectStatus.ACTIVE
    color:           str            = "#0078d4"
    icon:            str            = "📁"
    target_date:     Optional[str]  = None    # ISO date "YYYY-MM-DD"
    created_at:      Optional[str]  = None
    updated_at:      Optional[str]  = None
    # ── new fields (v2) ───────────────────────────────────────────────────────
    category:        str            = ProjectCategory.OTHER
    priority:        str            = ProjectPriority.MEDIUM
    tags:            list           = field(default_factory=list)
    enabled_systems: list           = field(default_factory=lambda: list(EnabledSystem.DEFAULT))

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "name":            self.name,
            "description":     self.description,
            "game_system":     self.game_system,
            "status":          self.status,
            "color":           self.color,
            "icon":            self.icon,
            "target_date":     self.target_date,
            "created_at":      self.created_at,
            "updated_at":      self.updated_at,
            "category":        self.category,
            "priority":        self.priority,
            "tags":            _dump_json_list(self.tags),
            "enabled_systems": _dump_json_list(self.enabled_systems),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        return cls(
            id              = d.get("id"),
            name            = d.get("name", ""),
            description     = d.get("description", ""),
            game_system     = d.get("game_system", ""),
            status          = d.get("status", ProjectStatus.ACTIVE),
            color           = d.get("color", "#0078d4"),
            icon            = d.get("icon", "📁"),
            target_date     = d.get("target_date"),
            created_at      = d.get("created_at"),
            updated_at      = d.get("updated_at"),
            category        = d.get("category", ProjectCategory.OTHER) or ProjectCategory.OTHER,
            priority        = d.get("priority", ProjectPriority.MEDIUM) or ProjectPriority.MEDIUM,
            tags            = _load_json_list(d.get("tags", "[]")),
            enabled_systems = _load_json_list(d.get("enabled_systems")) or list(EnabledSystem.DEFAULT),
        )

    def system_enabled(self, system: str) -> bool:
        """Return True if the given EnabledSystem is active for this project."""
        if not self.enabled_systems:
            return True   # empty list → treat as all enabled (backward compat)
        return system in self.enabled_systems


@dataclass
class ProjectLink:
    """Junction record linking any entity to a project."""
    id:          Optional[int] = None
    project_id:  int           = 0
    entity_type: str           = ""   # EntityType constant
    entity_id:   int           = 0
    notes:       str           = ""
    created_at:  Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "project_id":  self.project_id,
            "entity_type": self.entity_type,
            "entity_id":   self.entity_id,
            "notes":       self.notes,
            "created_at":  self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectLink":
        return cls(
            id          = d.get("id"),
            project_id  = d.get("project_id", 0),
            entity_type = d.get("entity_type", ""),
            entity_id   = d.get("entity_id", 0),
            notes       = d.get("notes", ""),
            created_at  = d.get("created_at"),
        )


@dataclass
class Milestone:
    id:                       Optional[int] = None
    project_id:               int           = 0
    title:                    str           = ""
    description:              str           = ""
    due_date:                 Optional[str] = None   # ISO date
    completed_at:             Optional[str] = None  # ISO datetime, None = incomplete
    order_index:              int           = 0
    # ── new fields (v2) ──────────────────────────────────────────────────────
    priority:                 str           = ProjectPriority.MEDIUM
    linked_note_id:           Optional[int] = None
    estimated_effort_minutes: int           = 0
    completion_notes:         str           = ""
    is_focus:                 bool          = False
    # ── quantity tracking (v3) ───────────────────────────────────────────────
    # quantity_total = 0  →  no quantity tracking (plain checkbox milestone)
    # quantity_total > 0  →  track n-of-total progress (e.g. 12/20 Clanrats)
    quantity_total:           int           = 0
    quantity_done:            int           = 0

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    @property
    def has_quantity(self) -> bool:
        return self.quantity_total > 0

    @property
    def quantity_progress(self) -> float:
        """0.0–1.0; 0.0 when no quantity tracking."""
        if not self.quantity_total:
            return 0.0
        return min(self.quantity_done / self.quantity_total, 1.0)

    @property
    def is_overdue(self) -> bool:
        if self.is_complete or not self.due_date:
            return False
        from datetime import date
        try:
            return date.fromisoformat(self.due_date) < date.today()
        except Exception:
            return False

    def to_dict(self) -> dict:
        return {
            "id":                       self.id,
            "project_id":               self.project_id,
            "title":                    self.title,
            "description":              self.description,
            "due_date":                 self.due_date,
            "completed_at":             self.completed_at,
            "order_index":              self.order_index,
            "priority":                 self.priority,
            "linked_note_id":           self.linked_note_id,
            "estimated_effort_minutes": self.estimated_effort_minutes,
            "completion_notes":         self.completion_notes,
            "is_focus":                 int(self.is_focus),
            "quantity_total":           self.quantity_total,
            "quantity_done":            self.quantity_done,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Milestone":
        return cls(
            id                       = d.get("id"),
            project_id               = d.get("project_id", 0),
            title                    = d.get("title", ""),
            description              = d.get("description", ""),
            due_date                 = d.get("due_date"),
            completed_at             = d.get("completed_at"),
            order_index              = d.get("order_index", 0),
            priority                 = d.get("priority", ProjectPriority.MEDIUM) or ProjectPriority.MEDIUM,
            linked_note_id           = d.get("linked_note_id"),
            estimated_effort_minutes = int(d.get("estimated_effort_minutes") or 0),
            completion_notes         = d.get("completion_notes", "") or "",
            is_focus                 = bool(d.get("is_focus", 0)),
            quantity_total           = int(d.get("quantity_total") or 0),
            quantity_done            = int(d.get("quantity_done") or 0),
        )


@dataclass
class ProjectNote:
    id:         Optional[int] = None
    project_id: int           = 0
    title:      str           = ""
    content:    str           = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "project_id": self.project_id,
            "title":      self.title,
            "content":    self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectNote":
        return cls(
            id         = d.get("id"),
            project_id = d.get("project_id", 0),
            title      = d.get("title", ""),
            content    = d.get("content", ""),
            created_at = d.get("created_at"),
            updated_at = d.get("updated_at"),
        )


@dataclass
class HobbySession:
    """A timed work session attached to a project."""
    id:                Optional[int] = None
    project_id:        int           = 0
    started_at:        Optional[str] = None   # ISO datetime
    ended_at:          Optional[str] = None   # ISO datetime
    duration_minutes:  int           = 0
    notes:             str           = ""
    # ── new fields (v2) ──────────────────────────────────────────────────────
    linked_milestone_id: Optional[int] = None
    outcome:             str           = ""
    next_action:         str           = ""
    is_active:           bool          = False  # live session in progress
    actual_start_time:   Optional[str] = None   # wall-clock start for live sessions

    def to_dict(self) -> dict:
        return {
            "id":                  self.id,
            "project_id":          self.project_id,
            "started_at":          self.started_at,
            "ended_at":            self.ended_at,
            "duration_minutes":    self.duration_minutes,
            "notes":               self.notes,
            "linked_milestone_id": self.linked_milestone_id,
            "outcome":             self.outcome,
            "next_action":         self.next_action,
            "is_active":           int(self.is_active),
            "actual_start_time":   self.actual_start_time,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HobbySession":
        return cls(
            id                  = d.get("id"),
            project_id          = d.get("project_id", 0),
            started_at          = d.get("started_at"),
            ended_at            = d.get("ended_at"),
            duration_minutes    = int(d.get("duration_minutes") or 0),
            notes               = d.get("notes", "") or "",
            linked_milestone_id = d.get("linked_milestone_id"),
            outcome             = d.get("outcome", "") or "",
            next_action         = d.get("next_action", "") or "",
            is_active           = bool(d.get("is_active", 0)),
            actual_start_time   = d.get("actual_start_time"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight stats bundle (assembled by service, consumed by UI)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProjectStats:
    total_models:            int   = 0    # distinct model entries/types linked
    total_model_count:       int   = 0    # sum of quantities (individual miniatures)
    painted_models:          int   = 0
    total_paints:            int   = 0
    milestones_done:         int   = 0    # fully-complete count (for "X / Y" display)
    milestones_total:        int   = 0
    milestones_weighted_done: float = 0.0 # partial credit for in-progress qty milestones
    total_sessions:          int   = 0
    total_hours:             float = 0.0
    has_active_session:      bool  = False
    last_session_at:         Optional[str] = None   # ISO datetime of most recent completed session
    recent_session_count:    int   = 0              # sessions started within the last 7 days
    avg_session_duration:    float = 0.0            # average duration (minutes) of recent sessions

    @property
    def paint_progress(self) -> float:
        """0.0–1.0 painting completion ratio based on individual miniature counts."""
        total = self.total_model_count or self.total_models
        if not total:
            return 0.0
        return min(self.painted_models / total, 1.0)

    @property
    def milestone_progress(self) -> float:
        """Weighted 0.0–1.0: quantity milestones contribute partial progress."""
        if not self.milestones_total:
            return 0.0
        effective = self.milestones_weighted_done if self.milestones_weighted_done > 0 \
                    else float(self.milestones_done)
        return min(effective / self.milestones_total, 1.0)


@dataclass
class GalleryEntry:
    """A single progress photo attached to a project."""
    id:             Optional[int] = None
    project_id:     int           = 0
    image_path:     str           = ""     # absolute path to stored image file
    title:          str           = ""
    note:           str           = ""
    captured_at:    str           = ""     # ISO date YYYY-MM-DD
    milestone_id:   Optional[int] = None
    session_id:     Optional[int] = None
    sort_order:     int           = 0
    created_at:     Optional[str] = None
    # ── new field (v2) ────────────────────────────────────────────────────────
    progress_stage: str           = GalleryStage.NONE   # GalleryStage constant

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "project_id":     self.project_id,
            "image_path":     self.image_path,
            "title":          self.title,
            "note":           self.note,
            "captured_at":    self.captured_at,
            "milestone_id":   self.milestone_id,
            "session_id":     self.session_id,
            "sort_order":     self.sort_order,
            "created_at":     self.created_at,
            "progress_stage": self.progress_stage,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GalleryEntry":
        return cls(
            id             = d.get("id"),
            project_id     = d.get("project_id", 0),
            image_path     = d.get("image_path", ""),
            title          = d.get("title", ""),
            note           = d.get("note", ""),
            captured_at    = d.get("captured_at", ""),
            milestone_id   = d.get("milestone_id"),
            session_id     = d.get("session_id"),
            sort_order     = d.get("sort_order", 0),
            created_at     = d.get("created_at"),
            progress_stage = d.get("progress_stage", "") or "",
        )


class ReqItemType:
    """Item types that can appear as project requirements."""
    PAINT    = "paint"
    MODEL    = "model"
    MATERIAL = "material"
    TOOL     = "tool"

    ALL = [PAINT, MODEL, MATERIAL, TOOL]
    LABELS = {
        PAINT:    "Paint",
        MODEL:    "Model",
        MATERIAL: "Material",
        TOOL:     "Tool",
    }
    ICONS = {
        PAINT:    "🎨",
        MODEL:    "🤖",
        MATERIAL: "🧱",
        TOOL:     "🔧",
    }


class ReqStatus:
    """Computed stock status for a requirement."""
    OK          = "ok"          # in stock
    LOW         = "low"         # low stock
    MISSING     = "missing"     # out of stock / not found
    OK_OVERRIDE = "ok_override" # user marked as fine
    UNKNOWN     = "unknown"     # freeform or service unavailable


@dataclass
class ProjectRequirement:
    """A single item required to start/complete a project."""
    id:              Optional[int] = None
    project_id:      int           = 0
    item_type:       str           = ""      # ReqItemType constant
    item_id:         Optional[int] = None    # FK into the relevant tracker; None = freeform
    item_name:       str           = ""      # display name (denormalized)
    quantity_needed: int           = 1
    notes:           str           = ""
    is_ok_override:  bool          = False   # user said "it's fine regardless"
    created_at:      Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "project_id":      self.project_id,
            "item_type":       self.item_type,
            "item_id":         self.item_id,
            "item_name":       self.item_name,
            "quantity_needed": self.quantity_needed,
            "notes":           self.notes,
            "is_ok_override":  int(self.is_ok_override),
            "created_at":      self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectRequirement":
        return cls(
            id              = d.get("id"),
            project_id      = d.get("project_id", 0),
            item_type       = d.get("item_type", ""),
            item_id         = d.get("item_id"),
            item_name       = d.get("item_name", "") or "",
            quantity_needed = int(d.get("quantity_needed") or 1),
            notes           = d.get("notes", "") or "",
            is_ok_override  = bool(d.get("is_ok_override", 0)),
            created_at      = d.get("created_at"),
        )


class ValidationError(Exception):
    pass
