# plugins/project_tracker/service.py
"""
Project Tracker — service layer.

Orchestrates the repository and resolves cross-plugin entity info
via the service registry (model_service, paint_service, etc.).
No other plugin depends on this service — dependency arrows point inward.
"""

from __future__ import annotations

import logging
log = logging.getLogger(__name__)

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import (
    Project, ProjectLink, Milestone, ProjectNote, HobbySession,
    ProjectStats, EntityType, GalleryEntry, ValidationError,
    ProjectCategory, ProjectPriority, EnabledSystem, GalleryStage,
    ProjectRequirement, ReqItemType, ReqStatus,
)
from .repository import ProjectRepository


class ProjectService:
    def __init__(self, db, context=None):
        self._db      = db
        self._repo    = ProjectRepository(db)
        self._context = context   # may be None in tests

    # ── helpers ───────────────────────────────────────────────────────────────

    def _svc(self, name: str):
        if self._context:
            return self._context.services.try_get(name)
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Projects
    # ─────────────────────────────────────────────────────────────────────────

    def create_project(self, name: str, description: str = "",
                       game_system: str = "", status: str = "active",
                       color: str = "#0078d4", icon: str = "📁",
                       target_date: Optional[str] = None,
                       category: str = ProjectCategory.OTHER,
                       priority: str = ProjectPriority.MEDIUM,
                       tags: Optional[list] = None,
                       enabled_systems: Optional[list] = None) -> Project:
        if not name.strip():
            raise ValidationError("Project name cannot be empty")
        project = Project(
            name            = name.strip(),
            description     = description,
            game_system     = game_system,
            status          = status,
            color           = color,
            icon            = icon,
            target_date     = target_date,
            category        = category or ProjectCategory.OTHER,
            priority        = priority or ProjectPriority.MEDIUM,
            tags            = tags or [],
            enabled_systems = enabled_systems if enabled_systems is not None else list(EnabledSystem.DEFAULT),
        )
        return self._repo.add_project(project)

    def update_project(self, project_id: int, **kwargs) -> Project:
        project = self._repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        for k, v in kwargs.items():
            if hasattr(project, k):
                setattr(project, k, v)
        if not project.name.strip():
            raise ValidationError("Project name cannot be empty")
        return self._repo.update_project(project)

    def delete_project(self, project_id: int) -> bool:
        return self._repo.delete_project(project_id)

    def get_project(self, project_id: int) -> Optional[Project]:
        return self._repo.get_project(project_id)

    def get_all_projects(self, status: Optional[str] = None) -> list[Project]:
        return self._repo.get_all_projects(status)

    def get_active_projects(self) -> list[Project]:
        return self._repo.get_all_projects(status="active")

    # ─────────────────────────────────────────────────────────────────────────
    # Links
    # ─────────────────────────────────────────────────────────────────────────

    def link_entity(self, project_id: int, entity_type: str,
                    entity_id: int, notes: str = "") -> ProjectLink:
        link = ProjectLink(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            notes=notes,
        )
        result = self._repo.add_link(link)

        # Auto-enable LINKS system the first time any entity is linked.
        # Only touches projects that have an explicit enabled_systems list;
        # legacy projects (empty list = all-on) are left unchanged.
        try:
            project = self._repo.get_project(project_id)
            if (project and project.enabled_systems
                    and EnabledSystem.LINKS not in project.enabled_systems):
                project.enabled_systems.append(EnabledSystem.LINKS)
                self._repo.update_project(project)
        except Exception as e:
            log.error(f"[PROJECT SVC] Auto-enable LINKS: {e}")

        # Auto-link paints when a model is linked
        if entity_type == EntityType.MODEL:
            self._auto_link_model_paints(project_id, entity_id)

        return result

    def _auto_link_model_paints(self, project_id: int, model_id: int):
        """
        When a model is linked to a project, automatically link any paints
        that are already associated with that model in the model tracker.
        Uses INSERT OR IGNORE so duplicates are silently skipped.
        """
        try:
            model_svc = self._svc("model_service")
            if not model_svc:
                return
            model = model_svc.get_model(model_id)
            if not model:
                return
            paint_ids = getattr(model, "linked_paint_ids", []) or []
            for paint_id in paint_ids:
                self._repo.add_link(ProjectLink(
                    project_id=project_id,
                    entity_type=EntityType.PAINT,
                    entity_id=paint_id,
                    notes="auto-linked from model",
                ))
            if paint_ids:
                log.debug(f"[PROJECT SVC] Auto-linked {len(paint_ids)} paint(s) "
                          f"from model {model_id} to project {project_id}")
        except Exception as e:
            log.error(f"[PROJECT SVC] Auto-link paints for model {model_id}: {e}")

    def unlink_entity(self, project_id: int, entity_type: str,
                      entity_id: int) -> bool:
        return self._repo.remove_link(project_id, entity_type, entity_id)

    def get_links(self, project_id: int,
                  entity_type: Optional[str] = None) -> list[ProjectLink]:
        return self._repo.get_links(project_id, entity_type)

    def is_linked(self, project_id: int, entity_type: str,
                  entity_id: int) -> bool:
        links = self._repo.get_links(project_id, entity_type)
        return any(l.entity_id == entity_id for l in links)

    def get_projects_for_entity(self, entity_type: str,
                                entity_id: int) -> list[Project]:
        ids = self._repo.get_projects_for_entity(entity_type, entity_id)
        return [p for p in (self._repo.get_project(i) for i in ids) if p]

    # ─────────────────────────────────────────────────────────────────────────
    # Entity resolution (reads from sibling services)
    # ─────────────────────────────────────────────────────────────────────────

    def resolve_linked_entities(self, project_id: int) -> dict[str, list]:
        """
        Return a dict keyed by EntityType constant whose values are
        the actual domain objects pulled from each plugin's service.
        Unknown / deleted entities are silently skipped.
        """
        links = self._repo.get_links(project_id)
        result: dict[str, list] = {et: [] for et in EntityType.ALL}

        for link in links:
            obj = self._resolve_one(link.entity_type, link.entity_id)
            if obj is not None:
                result[link.entity_type].append(obj)

        return result

    def _resolve_one(self, entity_type: str, entity_id: int):
        try:
            if entity_type == EntityType.MODEL:
                svc = self._svc("model_service")
                return svc.get_model(entity_id) if svc else None

            if entity_type == EntityType.PAINT:
                svc = self._svc("paint_service")
                return svc.get_paint(entity_id) if svc else None

            if entity_type == EntityType.ARMY:
                svc = self._svc("army_service")
                return svc.get_army(entity_id) if svc else None

            if entity_type == EntityType.CAMPAIGN:
                svc = self._svc("campaign_service")
                return svc.get_campaign(entity_id) if svc else None

            if entity_type == EntityType.EVENT:
                svc = self._svc("calendar_service")
                return svc.get_event(entity_id) if svc else None

            if entity_type == EntityType.SCHEME:
                svc = self._svc("scheme_service")
                return svc.get_scheme(entity_id) if svc else None

        except Exception as e:
            log.error(f"[PROJECT SVC] resolve_one({entity_type}, {entity_id}): {e}")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Milestones
    # ─────────────────────────────────────────────────────────────────────────

    def add_milestone(self, project_id: int, title: str,
                      description: str = "",
                      due_date: Optional[str] = None,
                      priority: str = ProjectPriority.MEDIUM,
                      linked_note_id: Optional[int] = None,
                      estimated_effort_minutes: int = 0,
                      quantity_total: int = 0,
                      quantity_done: int = 0) -> Milestone:
        if not title.strip():
            raise ValidationError("Milestone title cannot be empty")
        m = Milestone(
            project_id               = project_id,
            title                    = title.strip(),
            description              = description,
            due_date                 = due_date,
            priority                 = priority or ProjectPriority.MEDIUM,
            linked_note_id           = linked_note_id,
            estimated_effort_minutes = estimated_effort_minutes,
            quantity_total           = max(0, quantity_total),
            quantity_done            = max(0, quantity_done),
        )
        return self._repo.add_milestone(m)

    def toggle_milestone(self, milestone_id: int) -> Milestone:
        m = self._repo.get_milestone(milestone_id)
        if not m:
            raise ValueError(f"Milestone {milestone_id} not found")
        now = datetime.now(timezone.utc).isoformat()
        m.completed_at = None if m.completed_at else now
        return self._repo.update_milestone(m)

    def update_milestone(self, milestone_id: int, **kwargs) -> Milestone:
        m = self._repo.get_milestone(milestone_id)
        if not m:
            raise ValueError(f"Milestone {milestone_id} not found")
        for k, v in kwargs.items():
            if hasattr(m, k):
                setattr(m, k, v)
        # If setting is_focus=True, clear focus on other milestones first
        if kwargs.get("is_focus"):
            self._clear_other_focus(m.project_id, milestone_id)
        return self._repo.update_milestone(m)

    def set_focus_milestone(self, project_id: int,
                            milestone_id: Optional[int]) -> None:
        """Mark a milestone as the current focus (clears any previous focus)."""
        self._clear_other_focus(project_id, exclude_id=None)
        if milestone_id is not None:
            m = self._repo.get_milestone(milestone_id)
            if m:
                m.is_focus = True
                self._repo.update_milestone(m)

    def _clear_other_focus(self, project_id: int,
                           exclude_id: Optional[int]) -> None:
        milestones = self._repo.get_milestones(project_id)
        for m in milestones:
            if m.is_focus and m.id != exclude_id:
                m.is_focus = False
                self._repo.update_milestone(m)

    def step_milestone_quantity(self, milestone_id: int, delta: int) -> Milestone:
        """Increment or decrement quantity_done by delta; clamps to [0, quantity_total].
        Auto-completes the milestone when quantity_done reaches quantity_total,
        and un-completes it if quantity_done drops back below."""
        m = self._repo.get_milestone(milestone_id)
        if not m:
            raise ValueError(f"Milestone {milestone_id} not found")
        new_done = max(0, min(m.quantity_done + delta, m.quantity_total))
        m.quantity_done = new_done
        # Auto-complete / un-complete based on quantity
        if m.quantity_total > 0:
            if new_done >= m.quantity_total and not m.completed_at:
                from datetime import datetime, timezone
                m.completed_at = datetime.now(timezone.utc).isoformat()
            elif new_done < m.quantity_total and m.completed_at:
                m.completed_at = None
        return self._repo.update_milestone(m)

    def delete_milestone(self, milestone_id: int) -> bool:
        return self._repo.delete_milestone(milestone_id)

    def get_milestone(self, milestone_id: int) -> Optional[Milestone]:
        return self._repo.get_milestone(milestone_id)

    def get_milestones(self, project_id: int) -> list[Milestone]:
        return self._repo.get_milestones(project_id)

    def get_focus_milestone(self, project_id: int) -> Optional[Milestone]:
        return self._repo.get_focus_milestone(project_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Notes
    # ─────────────────────────────────────────────────────────────────────────

    def add_note(self, project_id: int, title: str = "",
                 content: str = "") -> ProjectNote:
        note = ProjectNote(project_id=project_id,
                           title=title, content=content)
        return self._repo.add_note(note)

    def update_note(self, note_id: int, title: str,
                    content: str) -> ProjectNote:
        note = self._repo.get_note(note_id)
        if not note:
            raise ValueError(f"Note {note_id} not found")
        note.title   = title
        note.content = content
        return self._repo.update_note(note)

    def delete_note(self, note_id: int) -> bool:
        return self._repo.delete_note(note_id)

    def get_notes(self, project_id: int) -> list[ProjectNote]:
        return self._repo.get_notes(project_id)

    def get_note(self, note_id: int) -> Optional[ProjectNote]:
        return self._repo.get_note(note_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Hobby Sessions
    # ─────────────────────────────────────────────────────────────────────────

    def log_session(self, project_id: int, duration_minutes: int,
                    notes: str = "",
                    started_at: Optional[str] = None,
                    outcome: str = "",
                    next_action: str = "",
                    linked_milestone_id: Optional[int] = None) -> HobbySession:
        if duration_minutes < 1:
            raise ValidationError("Session must be at least 1 minute")
        now = datetime.now(timezone.utc).isoformat()
        session = HobbySession(
            project_id          = project_id,
            started_at          = started_at or now,
            ended_at            = now,
            duration_minutes    = duration_minutes,
            notes               = notes,
            outcome             = outcome,
            next_action         = next_action,
            linked_milestone_id = linked_milestone_id,
            is_active           = False,
        )
        return self._repo.add_session(session)

    def start_session(self, project_id: int,
                      linked_milestone_id: Optional[int] = None) -> HobbySession:
        """
        Begin a live session for a project.
        If one is already active, return it without creating a duplicate.
        """
        existing = self._repo.get_active_session(project_id)
        if existing:
            return existing
        now = datetime.now(timezone.utc).isoformat()
        session = HobbySession(
            project_id          = project_id,
            started_at          = now,
            actual_start_time   = now,
            linked_milestone_id = linked_milestone_id,
            is_active           = True,
            duration_minutes    = 0,
        )
        return self._repo.add_session(session)

    def end_session(self, project_id: int, notes: str = "",
                    outcome: str = "", next_action: str = "",
                    linked_milestone_id: Optional[int] = None) -> Optional[HobbySession]:
        """
        End the active live session for a project.
        Computes duration from actual_start_time → now.
        Returns the completed session, or None if no active session found.
        """
        session = self._repo.get_active_session(project_id)
        if not session:
            return None

        now = datetime.now(timezone.utc)
        session.ended_at = now.isoformat()
        session.is_active = False

        # Compute duration
        try:
            start_str = session.actual_start_time or session.started_at
            if start_str:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                # Make both offset-aware
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                duration_secs = (now.replace(tzinfo=timezone.utc) - start_dt).total_seconds()
                session.duration_minutes = max(1, int(duration_secs / 60))
            else:
                session.duration_minutes = 1
        except Exception as e:
            log.error(f"[PROJECT SVC] end_session duration calc: {e}")
            session.duration_minutes = 1

        session.notes               = notes
        session.outcome             = outcome
        session.next_action         = next_action
        if linked_milestone_id is not None:
            session.linked_milestone_id = linked_milestone_id

        return self._repo.update_session(session)

    def get_active_session(self, project_id: int) -> Optional[HobbySession]:
        return self._repo.get_active_session(project_id)

    def update_session(self, session_id: int, **kwargs) -> HobbySession:
        from .repository import ProjectRepository
        rows = self._repo._db.query(
            "SELECT * FROM hobby_sessions WHERE id=?", (session_id,)
        )
        if not rows:
            raise ValueError(f"Session {session_id} not found")
        session = self._repo._row_to_session(rows[0])
        for k, v in kwargs.items():
            if hasattr(session, k):
                setattr(session, k, v)
        return self._repo.update_session(session)

    def delete_session(self, session_id: int) -> bool:
        return self._repo.delete_session(session_id)

    def get_sessions(self, project_id: int) -> list[HobbySession]:
        return self._repo.get_sessions(project_id)

    def get_total_hours(self, project_id: int) -> float:
        mins = self._repo.get_total_minutes(project_id)
        return round(mins / 60, 1)

    # ─────────────────────────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────────────────────────

    def get_stats(self, project_id: int) -> ProjectStats:
        stats = ProjectStats()

        # Milestones — integer done count + weighted float for quantity milestones
        milestones = self._repo.get_milestones(project_id)
        stats.milestones_total = len(milestones)
        stats.milestones_done  = sum(1 for m in milestones if m.is_complete)
        weighted = 0.0
        for m in milestones:
            if m.is_complete:
                weighted += 1.0
            elif m.has_quantity:
                weighted += m.quantity_progress   # 0.0–1.0 partial credit
            # plain incomplete milestone contributes 0
        stats.milestones_weighted_done = weighted

        # Sessions
        sessions = self._repo.get_sessions(project_id)
        stats.total_sessions    = len(sessions)
        stats.total_hours       = round(self._repo.get_total_minutes(project_id) / 60, 1)
        stats.has_active_session = any(s.is_active for s in sessions)
        # Most recent completed session (sessions come back DESC by started_at)
        completed_sessions = [s for s in sessions if not s.is_active]
        if completed_sessions:
            stats.last_session_at = completed_sessions[0].started_at

        # Recent session momentum (last 7 days)
        try:
            from datetime import timedelta
            now_dt   = datetime.now(timezone.utc)
            week_ago = now_dt - timedelta(days=7)
            recent = []
            for s in completed_sessions:
                if not s.started_at:
                    continue
                try:
                    dt = datetime.fromisoformat(s.started_at.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt >= week_ago:
                        recent.append(s)
                except Exception:
                    pass
            stats.recent_session_count = len(recent)
            if recent:
                stats.avg_session_duration = round(
                    sum(s.duration_minutes for s in recent) / len(recent), 1
                )
        except Exception:
            pass

        # Model links → painting progress
        try:
            model_links = self._repo.get_links(project_id, EntityType.MODEL)
            model_svc   = self._svc("model_service")
            if model_svc and model_links:
                stats.total_models = len(model_links)   # distinct types
                painted   = 0
                qty_total = 0
                for lnk in model_links:
                    m = model_svc.get_model(lnk.entity_id)
                    if m:
                        qty = getattr(m, "quantity", 1) or 1
                        qty_total += qty
                        if getattr(m, "status", "").lower() in (
                            "painted", "complete", "completed", "done",
                            "fully painted", "display piece",
                        ):
                            painted += qty   # accumulate miniatures, not types
                stats.total_model_count = qty_total
                stats.painted_models    = painted
        except Exception:
            pass

        # Paint links
        try:
            paint_links = self._repo.get_links(project_id, EntityType.PAINT)
            stats.total_paints = len(paint_links)
        except Exception:
            pass

        return stats

    # ─────────────────────────────────────────────────────────────────────────
    # Gallery
    # ─────────────────────────────────────────────────────────────────────────

    def gallery_dir(self, project_id: int) -> Path:
        """Return (and create) the filesystem directory for a project's gallery images."""
        base = Path(self._db.db_path).parent / "gallery" / str(project_id)
        base.mkdir(parents=True, exist_ok=True)
        return base

    def add_gallery_entry(self, project_id: int, image_path: str,
                          title: str = "", note: str = "",
                          captured_at: Optional[str] = None,
                          milestone_id: Optional[int] = None,
                          session_id: Optional[int] = None,
                          progress_stage: str = GalleryStage.NONE) -> GalleryEntry:
        from datetime import date
        entry = GalleryEntry(
            project_id     = project_id,
            image_path     = image_path,
            title          = title.strip(),
            note           = note.strip(),
            captured_at    = captured_at or date.today().isoformat(),
            milestone_id   = milestone_id,
            session_id     = session_id,
            progress_stage = progress_stage or GalleryStage.NONE,
        )
        return self._repo.add_gallery_entry(entry)

    def get_gallery_entries(self, project_id: int) -> list[GalleryEntry]:
        return self._repo.get_gallery_entries(project_id)

    def update_gallery_entry(self, entry_id: int, **kwargs) -> GalleryEntry:
        entry = self._repo.get_gallery_entry(entry_id)
        if not entry:
            raise ValueError(f"Gallery entry {entry_id} not found")
        allowed = {"title", "note", "captured_at", "milestone_id",
                   "session_id", "progress_stage"}
        for k, v in kwargs.items():
            if k in allowed:
                setattr(entry, k, v)
        return self._repo.update_gallery_entry(entry)

    def delete_gallery_entry(self, entry_id: int) -> bool:
        """Delete the DB record and the image file from disk."""
        image_path = self._repo.delete_gallery_entry(entry_id)
        if image_path:
            try:
                if os.path.isfile(image_path):
                    os.remove(image_path)
            except Exception as e:
                log.error(f"[PROJECT SVC] Could not delete gallery image file: {e}")
        return True

    def delete_project(self, project_id: int) -> bool:
        """Delete project and clean up all gallery image files."""
        entries = self._repo.get_gallery_entries(project_id)
        self._repo.delete_project(project_id)
        for entry in entries:
            try:
                if entry.image_path and os.path.isfile(entry.image_path):
                    os.remove(entry.image_path)
            except Exception:
                pass
        try:
            gallery = Path(self._db.db_path).parent / "gallery" / str(project_id)
            if gallery.is_dir():
                gallery.rmdir()
        except Exception:
            pass
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Requirements
    # ─────────────────────────────────────────────────────────────────────────

    def add_requirement(self, project_id: int, item_type: str, item_name: str,
                        item_id: Optional[int] = None,
                        quantity_needed: int = 1,
                        notes: str = "") -> ProjectRequirement:
        req = ProjectRequirement(
            project_id      = project_id,
            item_type       = item_type,
            item_id         = item_id,
            item_name       = item_name.strip(),
            quantity_needed = max(1, quantity_needed),
            notes           = notes,
        )
        return self._repo.add_requirement(req)

    def update_requirement(self, req_id: int, **kwargs) -> ProjectRequirement:
        req = self._repo.get_requirement(req_id)
        if not req:
            raise ValueError(f"Requirement {req_id} not found")
        for k, v in kwargs.items():
            if hasattr(req, k):
                setattr(req, k, v)
        return self._repo.update_requirement(req)

    def delete_requirement(self, req_id: int) -> bool:
        return self._repo.delete_requirement(req_id)

    def get_requirements(self, project_id: int) -> list[ProjectRequirement]:
        return self._repo.get_requirements(project_id)

    def resolve_requirement_stock(self, req: ProjectRequirement) -> str:
        """Return a ReqStatus constant for the given requirement."""
        if req.is_ok_override:
            return ReqStatus.OK_OVERRIDE

        if req.item_id is None:
            return ReqStatus.UNKNOWN   # freeform — no live check possible

        try:
            if req.item_type == ReqItemType.PAINT:
                svc = self._svc("paint_service")
                if not svc:
                    return ReqStatus.UNKNOWN
                paint = svc.get_paint(req.item_id)
                if not paint:
                    return ReqStatus.MISSING
                level = (paint.level or "").lower()
                if level == "out":
                    return ReqStatus.MISSING
                if level == "low":
                    return ReqStatus.LOW
                if getattr(paint, "quantity", 1) <= 0:
                    return ReqStatus.MISSING
                return ReqStatus.OK

            if req.item_type == ReqItemType.MODEL:
                svc = self._svc("model_service")
                if not svc:
                    return ReqStatus.UNKNOWN
                model = svc.get_model(req.item_id)
                if not model:
                    return ReqStatus.MISSING
                qty = getattr(model, "quantity", 0) or 0
                if qty <= 0:
                    return ReqStatus.MISSING
                if qty < req.quantity_needed:
                    return ReqStatus.LOW
                return ReqStatus.OK

            if req.item_type == ReqItemType.MATERIAL:
                svc = self._svc("material_service")
                if not svc:
                    return ReqStatus.UNKNOWN
                mat = svc.get_material(req.item_id)
                if not mat:
                    return ReqStatus.MISSING
                stock = (getattr(mat, "stock", "") or "").lower()
                if stock in ("empty",):
                    return ReqStatus.MISSING
                if stock in ("low",):
                    return ReqStatus.LOW
                if getattr(mat, "quantity", 1) <= 0:
                    return ReqStatus.MISSING
                return ReqStatus.OK

            if req.item_type == ReqItemType.TOOL:
                svc = self._svc("tool_service")
                if not svc:
                    return ReqStatus.UNKNOWN
                tool = svc.get_tool(req.item_id)
                if not tool:
                    return ReqStatus.MISSING
                cond = (getattr(tool, "condition", "") or "").lower()
                if cond in ("worn", "replace"):
                    return ReqStatus.LOW
                if getattr(tool, "quantity", 1) <= 0:
                    return ReqStatus.MISSING
                return ReqStatus.OK

        except Exception as e:
            log.error(f"[PROJECT SVC] resolve_requirement_stock: {e}")

        return ReqStatus.UNKNOWN

    def get_all_items_for_type(self, item_type: str) -> list:
        """Return all items from the relevant tracker service for picker dialogs."""
        try:
            if item_type == ReqItemType.PAINT:
                svc = self._svc("paint_service")
                return svc.get_all_paints() if svc else []
            if item_type == ReqItemType.MODEL:
                svc = self._svc("model_service")
                return svc.get_all_models() if svc else []
            if item_type == ReqItemType.MATERIAL:
                svc = self._svc("material_service")
                return svc.get_all_materials() if svc else []
            if item_type == ReqItemType.TOOL:
                svc = self._svc("tool_service")
                return svc.get_all_tools() if svc else []
        except Exception as e:
            log.error(f"[PROJECT SVC] get_all_items_for_type({item_type}): {e}")
        return []
