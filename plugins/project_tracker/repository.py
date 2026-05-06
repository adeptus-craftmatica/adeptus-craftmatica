# plugins/project_tracker/repository.py
"""
Project Tracker — SQLite repository.

Tables:
  projects            — top-level project records
  project_links       — junction: project ↔ any entity
  project_notes       — freeform notes attached to a project
  project_milestones  — checklist items with optional due dates
  hobby_sessions      — timed work sessions
  project_gallery     — progress photos

Uses the shared DatabaseService API:
  db.execute(sql, params) → cursor  (auto-commits)
  db.query(sql, params)   → list[sqlite3.Row]
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .models import (
    Project, ProjectLink, Milestone, ProjectNote, HobbySession,
    GalleryEntry, ProjectCategory, ProjectPriority, EnabledSystem,
    ProjectRequirement,
    _dump_json_list,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectRepository:
    def __init__(self, db):
        self._db = db
        self._ensure_tables()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _ensure_tables(self):
        # ── Original tables (unchanged) ──────────────────────────────────────
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                game_system TEXT DEFAULT '',
                status      TEXT DEFAULT 'active',
                color       TEXT DEFAULT '#0078d4',
                icon        TEXT DEFAULT '📁',
                target_date TEXT,
                created_at  TEXT,
                updated_at  TEXT
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS project_links (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id   INTEGER NOT NULL,
                notes       TEXT DEFAULT '',
                created_at  TEXT,
                UNIQUE(project_id, entity_type, entity_id)
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS project_notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                title       TEXT DEFAULT '',
                content     TEXT DEFAULT '',
                created_at  TEXT,
                updated_at  TEXT
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS project_milestones (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                title        TEXT NOT NULL,
                description  TEXT DEFAULT '',
                due_date     TEXT,
                completed_at TEXT,
                order_index  INTEGER DEFAULT 0
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS hobby_sessions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id       INTEGER NOT NULL,
                started_at       TEXT,
                ended_at         TEXT,
                duration_minutes INTEGER DEFAULT 0,
                notes            TEXT DEFAULT ''
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS project_gallery (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                image_path   TEXT NOT NULL DEFAULT '',
                title        TEXT DEFAULT '',
                note         TEXT DEFAULT '',
                captured_at  TEXT NOT NULL DEFAULT '',
                milestone_id INTEGER,
                session_id   INTEGER,
                sort_order   INTEGER DEFAULT 0,
                created_at   TEXT NOT NULL DEFAULT ''
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS project_requirements (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id      INTEGER NOT NULL,
                item_type       TEXT NOT NULL DEFAULT '',
                item_id         INTEGER,
                item_name       TEXT NOT NULL DEFAULT '',
                quantity_needed INTEGER NOT NULL DEFAULT 1,
                notes           TEXT DEFAULT '',
                is_ok_override  INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT
            )
        """)

        # ── v2 migrations: ADD COLUMN (safe to run repeatedly — errors silently ignored) ──
        _migrations = [
            # projects
            ("projects",           "category",                 "TEXT DEFAULT 'other'"),
            ("projects",           "priority",                 "TEXT DEFAULT 'medium'"),
            ("projects",           "tags",                     "TEXT DEFAULT '[]'"),
            ("projects",           "enabled_systems",          "TEXT DEFAULT '[]'"),
            # project_milestones
            ("project_milestones", "priority",                 "TEXT DEFAULT 'medium'"),
            ("project_milestones", "linked_note_id",           "INTEGER"),
            ("project_milestones", "estimated_effort_minutes", "INTEGER DEFAULT 0"),
            ("project_milestones", "completion_notes",         "TEXT DEFAULT ''"),
            ("project_milestones", "is_focus",                 "INTEGER DEFAULT 0"),
            ("project_milestones", "quantity_total",           "INTEGER DEFAULT 0"),
            ("project_milestones", "quantity_done",            "INTEGER DEFAULT 0"),
            # hobby_sessions
            ("hobby_sessions",     "linked_milestone_id",      "INTEGER"),
            ("hobby_sessions",     "outcome",                  "TEXT DEFAULT ''"),
            ("hobby_sessions",     "next_action",              "TEXT DEFAULT ''"),
            ("hobby_sessions",     "is_active",                "INTEGER DEFAULT 0"),
            ("hobby_sessions",     "actual_start_time",        "TEXT"),
            # project_gallery
            ("project_gallery",    "progress_stage",           "TEXT DEFAULT ''"),
        ]
        for table, column, col_def in _migrations:
            try:
                self._db.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"
                )
            except Exception:
                pass   # column already exists — safe to ignore

    # ─────────────────────────────────────────────────────────────────────────
    # Projects CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def add_project(self, project: Project) -> Project:
        now = _now()
        cur = self._db.execute(
            """INSERT INTO projects
               (name, description, game_system, status, color, icon,
                target_date, created_at, updated_at,
                category, priority, tags, enabled_systems)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (project.name, project.description, project.game_system,
             project.status, project.color, project.icon,
             project.target_date, now, now,
             project.category, project.priority,
             _dump_json_list(project.tags),
             _dump_json_list(project.enabled_systems)),
        )
        project.id = cur.lastrowid
        project.created_at = now
        project.updated_at = now
        return project

    def update_project(self, project: Project) -> Project:
        now = _now()
        self._db.execute(
            """UPDATE projects SET
               name=?, description=?, game_system=?, status=?, color=?,
               icon=?, target_date=?, updated_at=?,
               category=?, priority=?, tags=?, enabled_systems=?
               WHERE id=?""",
            (project.name, project.description, project.game_system,
             project.status, project.color, project.icon,
             project.target_date, now,
             project.category, project.priority,
             _dump_json_list(project.tags),
             _dump_json_list(project.enabled_systems),
             project.id),
        )
        project.updated_at = now
        return project

    def delete_project(self, project_id: int) -> bool:
        self._db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        self._db.execute("DELETE FROM project_links WHERE project_id=?", (project_id,))
        self._db.execute("DELETE FROM project_notes WHERE project_id=?", (project_id,))
        self._db.execute("DELETE FROM project_milestones WHERE project_id=?", (project_id,))
        self._db.execute("DELETE FROM hobby_sessions WHERE project_id=?", (project_id,))
        self._db.execute("DELETE FROM project_gallery WHERE project_id=?", (project_id,))
        self._db.execute("DELETE FROM project_requirements WHERE project_id=?", (project_id,))
        return True

    def get_project(self, project_id: int) -> Optional[Project]:
        rows = self._db.query("SELECT * FROM projects WHERE id=?", (project_id,))
        return self._row_to_project(rows[0]) if rows else None

    def get_all_projects(self, status: Optional[str] = None) -> list[Project]:
        if status:
            rows = self._db.query(
                "SELECT * FROM projects WHERE status=? ORDER BY updated_at DESC",
                (status,)
            )
        else:
            rows = self._db.query(
                "SELECT * FROM projects ORDER BY updated_at DESC"
            )
        return [self._row_to_project(r) for r in rows]

    def _row_to_project(self, row) -> Project:
        # Original columns + v2 columns appended by ALTER TABLE
        keys = [
            "id", "name", "description", "game_system", "status",
            "color", "icon", "target_date", "created_at", "updated_at",
            # v2
            "category", "priority", "tags", "enabled_systems",
        ]
        d = dict(zip(keys, row))
        return Project.from_dict(d)

    # ─────────────────────────────────────────────────────────────────────────
    # Links CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def add_link(self, link: ProjectLink) -> ProjectLink:
        now = _now()
        try:
            cur = self._db.execute(
                """INSERT OR IGNORE INTO project_links
                   (project_id, entity_type, entity_id, notes, created_at)
                   VALUES (?,?,?,?,?)""",
                (link.project_id, link.entity_type, link.entity_id,
                 link.notes, now),
            )
            link.id = cur.lastrowid
            link.created_at = now
        except Exception as e:
            print(f"[PROJECT REPO] add_link: {e}")
        return link

    def remove_link(self, project_id: int, entity_type: str, entity_id: int) -> bool:
        self._db.execute(
            "DELETE FROM project_links WHERE project_id=? AND entity_type=? AND entity_id=?",
            (project_id, entity_type, entity_id),
        )
        return True

    def get_links(self, project_id: int,
                  entity_type: Optional[str] = None) -> list[ProjectLink]:
        if entity_type:
            rows = self._db.query(
                "SELECT * FROM project_links WHERE project_id=? AND entity_type=? ORDER BY created_at",
                (project_id, entity_type),
            )
        else:
            rows = self._db.query(
                "SELECT * FROM project_links WHERE project_id=? ORDER BY entity_type, created_at",
                (project_id,),
            )
        return [self._row_to_link(r) for r in rows]

    def get_projects_for_entity(self, entity_type: str, entity_id: int) -> list[int]:
        rows = self._db.query(
            "SELECT project_id FROM project_links WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id),
        )
        return [r[0] for r in rows]

    def _row_to_link(self, row) -> ProjectLink:
        keys = ["id", "project_id", "entity_type", "entity_id", "notes", "created_at"]
        return ProjectLink.from_dict(dict(zip(keys, row)))

    # ─────────────────────────────────────────────────────────────────────────
    # Milestones CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def add_milestone(self, m: Milestone) -> Milestone:
        order_rows = self._db.query(
            "SELECT COALESCE(MAX(order_index)+1, 0) FROM project_milestones WHERE project_id=?",
            (m.project_id,)
        )
        m.order_index = order_rows[0][0] if order_rows else 0
        cur = self._db.execute(
            """INSERT INTO project_milestones
               (project_id, title, description, due_date, completed_at, order_index,
                priority, linked_note_id, estimated_effort_minutes, completion_notes,
                is_focus, quantity_total, quantity_done)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (m.project_id, m.title, m.description,
             m.due_date, m.completed_at, m.order_index,
             m.priority, m.linked_note_id,
             m.estimated_effort_minutes, m.completion_notes, int(m.is_focus),
             m.quantity_total, m.quantity_done),
        )
        m.id = cur.lastrowid
        return m

    def update_milestone(self, m: Milestone) -> Milestone:
        self._db.execute(
            """UPDATE project_milestones SET
               title=?, description=?, due_date=?, completed_at=?, order_index=?,
               priority=?, linked_note_id=?, estimated_effort_minutes=?,
               completion_notes=?, is_focus=?, quantity_total=?, quantity_done=?
               WHERE id=?""",
            (m.title, m.description, m.due_date,
             m.completed_at, m.order_index,
             m.priority, m.linked_note_id,
             m.estimated_effort_minutes, m.completion_notes, int(m.is_focus),
             m.quantity_total, m.quantity_done,
             m.id),
        )
        return m

    def delete_milestone(self, milestone_id: int) -> bool:
        self._db.execute(
            "DELETE FROM project_milestones WHERE id=?", (milestone_id,)
        )
        return True

    def get_milestones(self, project_id: int) -> list[Milestone]:
        rows = self._db.query(
            "SELECT * FROM project_milestones WHERE project_id=? ORDER BY order_index",
            (project_id,)
        )
        return [self._row_to_milestone(r) for r in rows]

    def get_milestone(self, milestone_id: int) -> Optional[Milestone]:
        rows = self._db.query(
            "SELECT * FROM project_milestones WHERE id=?", (milestone_id,)
        )
        return self._row_to_milestone(rows[0]) if rows else None

    def get_focus_milestone(self, project_id: int) -> Optional[Milestone]:
        """Return the milestone currently marked as focus for a project."""
        rows = self._db.query(
            "SELECT * FROM project_milestones WHERE project_id=? AND is_focus=1 LIMIT 1",
            (project_id,)
        )
        return self._row_to_milestone(rows[0]) if rows else None

    def _row_to_milestone(self, row) -> Milestone:
        keys = [
            "id", "project_id", "title", "description",
            "due_date", "completed_at", "order_index",
            # v2
            "priority", "linked_note_id", "estimated_effort_minutes",
            "completion_notes", "is_focus",
            # v3 — quantity tracking
            "quantity_total", "quantity_done",
        ]
        d = dict(zip(keys, row))
        return Milestone.from_dict(d)

    # ─────────────────────────────────────────────────────────────────────────
    # Notes CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def add_note(self, note: ProjectNote) -> ProjectNote:
        now = _now()
        cur = self._db.execute(
            """INSERT INTO project_notes
               (project_id, title, content, created_at, updated_at)
               VALUES (?,?,?,?,?)""",
            (note.project_id, note.title, note.content, now, now),
        )
        note.id = cur.lastrowid
        note.created_at = now
        note.updated_at = now
        return note

    def update_note(self, note: ProjectNote) -> ProjectNote:
        now = _now()
        self._db.execute(
            "UPDATE project_notes SET title=?, content=?, updated_at=? WHERE id=?",
            (note.title, note.content, now, note.id),
        )
        note.updated_at = now
        return note

    def delete_note(self, note_id: int) -> bool:
        self._db.execute("DELETE FROM project_notes WHERE id=?", (note_id,))
        return True

    def get_notes(self, project_id: int) -> list[ProjectNote]:
        rows = self._db.query(
            "SELECT * FROM project_notes WHERE project_id=? ORDER BY updated_at DESC",
            (project_id,)
        )
        return [self._row_to_note(r) for r in rows]

    def get_note(self, note_id: int) -> Optional[ProjectNote]:
        rows = self._db.query(
            "SELECT * FROM project_notes WHERE id=?", (note_id,)
        )
        return self._row_to_note(rows[0]) if rows else None

    def _row_to_note(self, row) -> ProjectNote:
        keys = ["id", "project_id", "title", "content", "created_at", "updated_at"]
        return ProjectNote.from_dict(dict(zip(keys, row)))

    # ─────────────────────────────────────────────────────────────────────────
    # Hobby Sessions CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def add_session(self, session: HobbySession) -> HobbySession:
        cur = self._db.execute(
            """INSERT INTO hobby_sessions
               (project_id, started_at, ended_at, duration_minutes, notes,
                linked_milestone_id, outcome, next_action, is_active, actual_start_time)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (session.project_id, session.started_at, session.ended_at,
             session.duration_minutes, session.notes,
             session.linked_milestone_id, session.outcome, session.next_action,
             int(session.is_active), session.actual_start_time),
        )
        session.id = cur.lastrowid
        return session

    def update_session(self, session: HobbySession) -> HobbySession:
        self._db.execute(
            """UPDATE hobby_sessions SET
               started_at=?, ended_at=?, duration_minutes=?, notes=?,
               linked_milestone_id=?, outcome=?, next_action=?,
               is_active=?, actual_start_time=?
               WHERE id=?""",
            (session.started_at, session.ended_at,
             session.duration_minutes, session.notes,
             session.linked_milestone_id, session.outcome, session.next_action,
             int(session.is_active), session.actual_start_time,
             session.id),
        )
        return session

    def delete_session(self, session_id: int) -> bool:
        self._db.execute("DELETE FROM hobby_sessions WHERE id=?", (session_id,))
        return True

    def get_sessions(self, project_id: int) -> list[HobbySession]:
        rows = self._db.query(
            "SELECT * FROM hobby_sessions WHERE project_id=? ORDER BY started_at DESC",
            (project_id,)
        )
        return [self._row_to_session(r) for r in rows]

    def get_active_session(self, project_id: int) -> Optional[HobbySession]:
        """Return the single active (live) session for a project, if any."""
        rows = self._db.query(
            "SELECT * FROM hobby_sessions WHERE project_id=? AND is_active=1 LIMIT 1",
            (project_id,)
        )
        return self._row_to_session(rows[0]) if rows else None

    def get_total_minutes(self, project_id: int) -> int:
        rows = self._db.query(
            "SELECT COALESCE(SUM(duration_minutes),0) FROM hobby_sessions WHERE project_id=?",
            (project_id,)
        )
        return rows[0][0] if rows else 0

    def _row_to_session(self, row) -> HobbySession:
        keys = [
            "id", "project_id", "started_at", "ended_at",
            "duration_minutes", "notes",
            # v2
            "linked_milestone_id", "outcome", "next_action",
            "is_active", "actual_start_time",
        ]
        d = dict(zip(keys, row))
        return HobbySession.from_dict(d)

    # ─────────────────────────────────────────────────────────────────────────
    # Gallery CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def add_gallery_entry(self, entry: GalleryEntry) -> GalleryEntry:
        now = _now()
        # Auto sort_order = max + 1
        rows = self._db.query(
            "SELECT COALESCE(MAX(sort_order)+1, 0) FROM project_gallery WHERE project_id=?",
            (entry.project_id,)
        )
        entry.sort_order = rows[0][0] if rows else 0
        entry.created_at = now
        cur = self._db.execute(
            """INSERT INTO project_gallery
               (project_id, image_path, title, note, captured_at,
                milestone_id, session_id, sort_order, created_at, progress_stage)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (entry.project_id, entry.image_path, entry.title, entry.note,
             entry.captured_at, entry.milestone_id, entry.session_id,
             entry.sort_order, entry.created_at, entry.progress_stage),
        )
        entry.id = cur.lastrowid
        return entry

    def update_gallery_entry(self, entry: GalleryEntry) -> GalleryEntry:
        self._db.execute(
            """UPDATE project_gallery SET
               title=?, note=?, captured_at=?, milestone_id=?, session_id=?,
               progress_stage=?
               WHERE id=?""",
            (entry.title, entry.note, entry.captured_at,
             entry.milestone_id, entry.session_id,
             entry.progress_stage, entry.id),
        )
        return entry

    def delete_gallery_entry(self, entry_id: int) -> Optional[str]:
        """Delete DB record; returns image_path so caller can clean up the file."""
        rows = self._db.query(
            "SELECT image_path FROM project_gallery WHERE id=?", (entry_id,)
        )
        image_path = rows[0][0] if rows else None
        self._db.execute("DELETE FROM project_gallery WHERE id=?", (entry_id,))
        return image_path

    def get_gallery_entries(self, project_id: int) -> list[GalleryEntry]:
        rows = self._db.query(
            """SELECT * FROM project_gallery
               WHERE project_id=?
               ORDER BY sort_order ASC, captured_at DESC, created_at DESC""",
            (project_id,)
        )
        return [self._row_to_gallery(r) for r in rows]

    def get_gallery_entry(self, entry_id: int) -> Optional[GalleryEntry]:
        rows = self._db.query(
            "SELECT * FROM project_gallery WHERE id=?", (entry_id,)
        )
        return self._row_to_gallery(rows[0]) if rows else None

    def _row_to_gallery(self, row) -> GalleryEntry:
        keys = [
            "id", "project_id", "image_path", "title", "note",
            "captured_at", "milestone_id", "session_id", "sort_order", "created_at",
            # v2
            "progress_stage",
        ]
        d = dict(zip(keys, row))
        return GalleryEntry.from_dict(d)

    # ─────────────────────────────────────────────────────────────────────────
    # Requirements CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def add_requirement(self, req: ProjectRequirement) -> ProjectRequirement:
        now = _now()
        cur = self._db.execute(
            """INSERT INTO project_requirements
               (project_id, item_type, item_id, item_name,
                quantity_needed, notes, is_ok_override, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (req.project_id, req.item_type, req.item_id, req.item_name,
             req.quantity_needed, req.notes, int(req.is_ok_override), now),
        )
        req.id = cur.lastrowid
        req.created_at = now
        return req

    def update_requirement(self, req: ProjectRequirement) -> ProjectRequirement:
        self._db.execute(
            """UPDATE project_requirements SET
               item_type=?, item_id=?, item_name=?,
               quantity_needed=?, notes=?, is_ok_override=?
               WHERE id=?""",
            (req.item_type, req.item_id, req.item_name,
             req.quantity_needed, req.notes, int(req.is_ok_override),
             req.id),
        )
        return req

    def delete_requirement(self, req_id: int) -> bool:
        self._db.execute(
            "DELETE FROM project_requirements WHERE id=?", (req_id,)
        )
        return True

    def get_requirements(self, project_id: int) -> list[ProjectRequirement]:
        rows = self._db.query(
            """SELECT * FROM project_requirements
               WHERE project_id=? ORDER BY created_at""",
            (project_id,)
        )
        return [self._row_to_requirement(r) for r in rows]

    def get_requirement(self, req_id: int) -> Optional[ProjectRequirement]:
        rows = self._db.query(
            "SELECT * FROM project_requirements WHERE id=?", (req_id,)
        )
        return self._row_to_requirement(rows[0]) if rows else None

    def _row_to_requirement(self, row) -> ProjectRequirement:
        keys = [
            "id", "project_id", "item_type", "item_id", "item_name",
            "quantity_needed", "notes", "is_ok_override", "created_at",
        ]
        return ProjectRequirement.from_dict(dict(zip(keys, row)))
