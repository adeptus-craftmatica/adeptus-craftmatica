# plugins/project_tracker/plugin.py
"""
Project Tracker Plugin

Lifecycle: creates DB tables, registers service, wires event bus,
loads initial data.  All business logic stays in the service.
"""

from __future__ import annotations

from core.plugin_base import PluginBase
from .service import ProjectService
from .models import ValidationError, ProjectStatus
# NOTE: ProjectUI and ProjectEditDialog are imported lazily inside activate()
# so that any Qt import error in ui.py doesn't silently block the whole plugin.

# Sentinel used to distinguish "caller passed no status" from "caller passed None"
_SENTINEL = object()


class Plugin(PluginBase):
    plugin_id   = "project_tracker"
    name        = "Projects"
    version     = "1.0.0"
    description = "Central project hub linking all trackers together."

    def __init__(self, context):
        super().__init__(context)
        self._service:              ProjectService | None = None
        self._ui:                                  None   = None
        self._ProjectEditDialog:                   None   = None   # set lazily in activate()
        self._subs:                list           = []
        self._current_project_id:  int | None = None
        self._current_status_filter: str | None = None  # persisted filter state

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def activate(self):
        print(f"[PLUGIN] {self.display_name} activating…")

        # ── 1. Database / service (must succeed) ──────────────────────────────
        db = self.context.services.get("db")
        if not db:
            raise RuntimeError("DatabaseService not available")

        self._service = ProjectService(db, self.context)

        # Register before building UI so the dashboard can always find it
        if not self.context.services.has("project_service"):
            self.context.services.register("project_service", self._service)

        # ── 2. UI (guarded — failure here must not swallow the plugin) ─────────
        try:
            from .ui import ProjectUI, ProjectEditDialog  # lazy — errors here are caught
            self._ProjectEditDialog = ProjectEditDialog
            self._ui = ProjectUI(self.context)
        except Exception as e:
            import traceback
            print(f"[PROJECT PLUGIN] UI construction failed: {e}")
            traceback.print_exc()
            self._ProjectEditDialog = None
            # Create a minimal fallback so the tab still appears
            from PySide6.QtWidgets import QLabel
            fallback = QLabel("⚠  Projects failed to load — check console for details.")
            fallback.setProperty("plugin_id", self.plugin_id)
            self._ui = fallback

        # ── 3. Events + initial data ───────────────────────────────────────────
        self._register_events()

        try:
            self._load_initial()
        except Exception as e:
            print(f"[PROJECT PLUGIN] Initial load failed: {e}")

        print(f"[PLUGIN] {self.display_name} activated")

    def deactivate(self):
        for event, handler in self._subs:
            try:
                self.context.event_bus.unsubscribe(event, handler)
            except Exception:
                pass
        self._subs.clear()
        self._ui      = None
        self._service = None

    def get_ui(self):
        if self._ui is not None:
            # Ensure plugin_id tag is always set on whatever widget we return
            try:
                self._ui.setProperty("plugin_id", self.plugin_id)
            except Exception:
                pass
        return self._ui

    # ── Event wiring ──────────────────────────────────────────────────────────

    def _sub(self, event: str, handler):
        self.context.event_bus.subscribe(event, handler)
        self._subs.append((event, handler))

    def _register_events(self):
        self._sub("project_create",                self._on_create)
        self._sub("project_edit_requested",        self._on_edit_requested)
        self._sub("project_delete",                self._on_delete)
        self._sub("project_selected",              self._on_selected)
        self._sub("project_filter_changed",        self._on_filter_changed)

        self._sub("project_milestone_add",            self._on_milestone_add)
        self._sub("project_milestone_update",         self._on_milestone_update)
        self._sub("project_milestone_toggle",         self._on_milestone_toggle)
        self._sub("project_milestone_delete",         self._on_milestone_delete)
        self._sub("project_milestone_focus_toggle",   self._on_milestone_focus_toggle)
        self._sub("project_milestone_quantity_step",  self._on_milestone_quantity_step)

        self._sub("project_note_add",              self._on_note_add)
        self._sub("project_note_update",           self._on_note_update)
        self._sub("project_note_delete",           self._on_note_delete)

        self._sub("project_session_log",           self._on_session_log)
        self._sub("project_session_delete",        self._on_session_delete)
        self._sub("project_session_start",         self._on_session_start)
        self._sub("project_session_end",           self._on_session_end)

        self._sub("project_link_entity",           self._on_link_entity)
        self._sub("project_unlink_entity",         self._on_unlink_entity)

        self._sub("project_gallery_add",           self._on_gallery_add)
        self._sub("project_gallery_update",        self._on_gallery_update)
        self._sub("project_gallery_delete",        self._on_gallery_delete)

        self._sub("project_requirement_add",       self._on_requirement_add)
        self._sub("project_requirement_update",    self._on_requirement_update)
        self._sub("project_requirement_delete",    self._on_requirement_delete)

        self._sub("dashboard_navigate",            self._on_dashboard_navigate)

    # ── Initial load ──────────────────────────────────────────────────────────

    def _is_full_ui(self) -> bool:
        """True only when the real ProjectUI was built successfully."""
        try:
            from .ui import ProjectUI
            return isinstance(self._ui, ProjectUI)
        except Exception:
            return False

    def _load_initial(self):
        if not self._is_full_ui():
            return
        try:
            # ── Restore saved status filter ────────────────────────────────────
            self._current_status_filter = self._read_saved_status_filter()

            projects   = self._service.get_all_projects(self._current_status_filter)
            stats_map  = {}
            for p in projects:
                try:
                    stats_map[p.id] = self._service.get_stats(p.id)
                except Exception:
                    pass
            self._ui.display_projects(projects, stats_map=stats_map)

            # For session-resume we need the project to exist regardless of
            # the current filter, so look it up from the full list if needed.
            all_projects = (
                projects if not self._current_status_filter
                else self._service.get_all_projects()
            )
            if all_projects:
                # ── Session resume — reopen the last-viewed project ────────────
                settings  = self.context.services.try_get("settings")
                last_raw  = settings.get("project_tracker.last_project_id", "") if settings else ""
                last_id   = int(last_raw) if str(last_raw).isdigit() else None
                ids       = {p.id for p in all_projects}
                if last_id and last_id in ids:
                    self._load_project(last_id)
                else:
                    self._load_project(all_projects[0].id)
            else:
                self._ui.show_empty_detail()
        except Exception as e:
            import traceback
            print(f"[PROJECT PLUGIN] Initial load failed: {e}")
            traceback.print_exc()

    def _load_project(self, project_id: int):
        if not self._is_full_ui():
            return
        try:
            project      = self._service.get_project(project_id)
            if not project:
                return
            stats        = self._service.get_stats(project_id)
            milestones   = self._service.get_milestones(project_id)
            notes        = self._service.get_notes(project_id)
            sessions     = self._service.get_sessions(project_id)
            linked       = self._service.resolve_linked_entities(project_id)
            gallery      = self._service.get_gallery_entries(project_id)
            requirements = self._service.get_requirements(project_id)

            self._current_project_id = project_id
            self._ui.display_project_detail(
                project, stats, milestones, notes, sessions, linked, gallery,
                requirements=requirements,
            )
        except Exception as e:
            import traceback
            print(f"[PROJECT PLUGIN] Load project {project_id} failed: {e}")
            traceback.print_exc()

    def _refresh_after_milestone(self, project_id: int) -> None:
        """Reload the project detail AND the sidebar card list after any
        milestone mutation so every surface reflects the new state."""
        self._load_project(project_id)
        self._refresh_list()   # updates sidebar cards + their progress bars/counts

    def _refresh_list(self, status=_SENTINEL):
        """Refresh the project list, preserving the current status filter
        when no explicit status override is given."""
        if not self._is_full_ui():
            return
        try:
            effective = (
                self._current_status_filter if status is _SENTINEL else status
            )
            projects  = self._service.get_all_projects(effective)
            stats_map = {}
            for p in projects:
                try:
                    stats_map[p.id] = self._service.get_stats(p.id)
                except Exception:
                    pass
            self._ui.display_projects(projects, stats_map=stats_map)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Refresh list failed: {e}")

    # ── Project handlers ──────────────────────────────────────────────────────

    def _on_create(self, payload: dict):
        try:
            project = self._service.create_project(**payload)
            if self._is_full_ui():
                self._ui._show_success(f"Created: {project.name}")
            self._refresh_list()
            self._load_project(project.id)
        except ValidationError as e:
            if self._is_full_ui():
                self._ui._show_error(str(e))
        except Exception as e:
            print(f"[PROJECT PLUGIN] Create failed: {e}")

    def _on_edit_requested(self, payload: dict):
        project_id = payload.get("id")
        if not project_id:
            return

        # Quick status-only update (no dialog needed)
        if payload.get("_quick") and "status" in payload:
            try:
                new_status = payload["status"]
                self._service.update_project(project_id, status=new_status)
                label = ProjectStatus.LABELS.get(new_status, new_status)
                if self._is_full_ui():
                    self._ui._show_success(f"Project marked {label}")
                self._refresh_list()
                self._load_project(project_id)
                # Notify the dashboard so it refreshes immediately
                self.context.event_bus.emit("project_updated", {
                    "id": project_id, "status": new_status,
                })
            except Exception as e:
                print(f"[PROJECT PLUGIN] Quick status update failed: {e}")
            return

        if not self._is_full_ui() or not self._ProjectEditDialog:
            return
        try:
            project = self._service.get_project(project_id)
            if not project:
                return
            dlg = self._ProjectEditDialog(project, self._ui)
            if dlg.exec():
                values = dlg.get_values()
                self._service.update_project(project_id, **values)
                self._ui._show_success("Project updated")
                self._refresh_list()
                self._load_project(project_id)
                self.context.event_bus.emit("project_updated", {"id": project_id})
        except ValidationError as e:
            if self._is_full_ui():
                self._ui._show_error(str(e))
        except Exception as e:
            print(f"[PROJECT PLUGIN] Edit failed: {e}")

    def _on_delete(self, payload: dict):
        project_id = payload.get("id")
        if not project_id:
            return
        try:
            self._service.delete_project(project_id)
            if self._is_full_ui():
                self._ui._show_success("Project deleted")
            if self._current_project_id == project_id:
                self._current_project_id = None
            self._refresh_list()
            projects = self._service.get_all_projects()
            if projects:
                self._load_project(projects[0].id)
            elif self._is_full_ui():
                self._ui.show_empty_detail()
        except Exception as e:
            print(f"[PROJECT PLUGIN] Delete failed: {e}")

    def _on_selected(self, payload: dict):
        project_id = payload.get("id")
        if project_id:
            # Persist for next session
            try:
                settings = self.context.services.try_get("settings")
                if settings:
                    settings.set("project_tracker.last_project_id", project_id)
            except Exception:
                pass
            self._load_project(project_id)

    def _read_saved_status_filter(self):
        """Read the saved status filter text from settings and return the
        corresponding ProjectStatus constant (or None for 'All')."""
        _STATUS_MAP = {
            "Active":    ProjectStatus.ACTIVE,
            "On Hold":   ProjectStatus.ON_HOLD,
            "Completed": ProjectStatus.COMPLETED,
            "Archived":  ProjectStatus.ARCHIVED,
        }
        try:
            settings = self.context.services.try_get("settings")
            if not settings:
                return None
            text = settings.get("project_tracker.status_filter", "")
            return _STATUS_MAP.get(text)   # None for "All" or unrecognised
        except Exception:
            return None

    def _on_filter_changed(self, payload: dict):
        status = payload.get("status")
        self._current_status_filter = status   # keep in sync
        self._refresh_list(status)

    # ── Milestone handlers ────────────────────────────────────────────────────

    def _on_milestone_add(self, payload: dict):
        try:
            from .models import ProjectPriority
            pid   = payload.get("project_id") or self._current_project_id
            title = payload.get("title", "")
            new_m = self._service.add_milestone(
                project_id               = pid,
                title                    = title,
                description              = payload.get("description", ""),
                due_date                 = payload.get("due_date"),
                priority                 = payload.get("priority", ProjectPriority.MEDIUM),
                linked_note_id           = payload.get("linked_note_id"),
                estimated_effort_minutes = payload.get("estimated_effort_minutes", 0),
                quantity_total           = payload.get("quantity_total", 0),
                quantity_done            = payload.get("quantity_done", 0),
            )
            # Set focus using the actual new milestone id (not milestones[-1])
            if payload.get("is_focus") and new_m.id:
                self._service.set_focus_milestone(pid, new_m.id)
            self._refresh_after_milestone(pid)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Milestone add failed: {e}")

    def _on_milestone_update(self, payload: dict):
        try:
            mid = payload.get("id")
            if not mid:
                return
            self._service.update_milestone(
                mid,
                title                    = payload.get("title"),
                description              = payload.get("description", ""),
                due_date                 = payload.get("due_date"),
                priority                 = payload.get("priority"),
                linked_note_id           = payload.get("linked_note_id"),
                estimated_effort_minutes = payload.get("estimated_effort_minutes", 0),
                is_focus                 = payload.get("is_focus", False),
                completion_notes         = payload.get("completion_notes", ""),
                quantity_total           = payload.get("quantity_total", 0),
                quantity_done            = payload.get("quantity_done", 0),
            )
            if self._current_project_id:
                self._refresh_after_milestone(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Milestone update failed: {e}")

    def _on_milestone_toggle(self, payload: dict):
        try:
            mid = payload.get("id")
            m   = self._service.toggle_milestone(mid)
            pid = self._current_project_id
            if m.is_complete:
                # Auto-clear focus when the focused milestone is completed so
                # the suggestion loop can immediately surface the next candidate.
                if getattr(m, "is_focus", False) and pid:
                    try:
                        self._service.set_focus_milestone(pid, None)
                    except Exception as _fe:
                        print(f"[PROJECT PLUGIN] Auto-clear focus: {_fe}")
                # Completed — log as a named activity event
                self.context.event_bus.emit("project_milestone_completed", {
                    "id":    mid,
                    "title": m.title,
                })
            else:
                # Un-completed — emit a dedicated event so the dashboard
                # knows to refresh even without an activity entry
                self.context.event_bus.emit("project_milestone_uncompleted", {
                    "id":    mid,
                    "title": m.title,
                })
            if pid:
                self._refresh_after_milestone(pid)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Milestone toggle failed: {e}")

    def _on_milestone_delete(self, payload: dict):
        try:
            mid = payload.get("id")

            # Capture milestone data before deletion
            milestone = None
            try:
                milestone = self._service.get_milestone(mid)
            except Exception:
                pass

            self._service.delete_milestone(mid)

            # Offer undo if we captured the data
            if milestone:
                _svc  = self._service
                _plug = self
                _pid  = self._current_project_id

                def _undo(_m=milestone):
                    try:
                        _svc.add_milestone(
                            project_id  = _m.project_id,
                            title       = _m.title,
                            description = _m.description or "",
                            due_date    = _m.due_date,
                        )
                        if _pid and _plug._is_full_ui():
                            _plug._refresh_after_milestone(_pid)
                    except Exception as ex:
                        print(f"[UNDO] Restore milestone failed: {ex}")

                from ui.toast import ToastManager
                from ui.undo_manager import UndoManager
                UndoManager.instance().push(
                    f"Deleted milestone '{milestone.title}'", _undo
                )
                ToastManager.instance().show(
                    f"Deleted milestone '{milestone.title}'",
                    level="info",
                    duration=6000,
                    action_label="Undo",
                    action_fn=_undo,
                )

            if self._current_project_id:
                self._refresh_after_milestone(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Milestone delete failed: {e}")

    def _on_milestone_focus_toggle(self, payload: dict):
        try:
            mid = payload.get("id")
            pid = self._current_project_id
            if not mid or not pid:
                return
            m = self._service.get_milestone(mid)
            if not m:
                return
            if m.is_focus:
                self._service.set_focus_milestone(pid, None)
            else:
                self._service.set_focus_milestone(pid, mid)
            self._load_project(pid)   # focus doesn't affect card counts, no need to refresh list
        except Exception as e:
            print(f"[PROJECT PLUGIN] Milestone focus toggle failed: {e}")

    def _on_milestone_quantity_step(self, payload: dict):
        """Handle +1 / -1 taps on a quantity-tracked milestone."""
        try:
            mid   = payload.get("id")
            delta = int(payload.get("delta", 1))
            pid   = self._current_project_id
            if not mid or not pid:
                return
            m = self._service.step_milestone_quantity(mid, delta)
            if m.is_complete and delta > 0:
                # Auto-clear focus when a quantity milestone reaches 100%
                if getattr(m, "is_focus", False):
                    try:
                        self._service.set_focus_milestone(pid, None)
                    except Exception as _fe:
                        print(f"[PROJECT PLUGIN] Auto-clear focus (qty): {_fe}")
                from ui.toast import ToastManager
                ToastManager.instance().show(
                    f"✓  '{m.title}' — all {m.quantity_total} done!",
                    level="success", duration=2500,
                )
                self.context.event_bus.emit("project_milestone_completed", {
                    "id": mid, "title": m.title,
                })
            elif not m.is_complete and delta < 0:
                self.context.event_bus.emit("project_milestone_uncompleted", {
                    "id": mid, "title": m.title,
                })
            self._refresh_after_milestone(pid)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Milestone quantity step failed: {e}")

    # ── Note handlers ─────────────────────────────────────────────────────────

    def _on_note_add(self, payload: dict):
        try:
            self._service.add_note(
                project_id=payload.get("project_id") or self._current_project_id,
                title=payload.get("title", ""),
                content=payload.get("content", ""),
            )
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Note add failed: {e}")

    def _on_note_update(self, payload: dict):
        try:
            self._service.update_note(
                note_id=payload.get("id"),
                title=payload.get("title", ""),
                content=payload.get("content", ""),
            )
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Note update failed: {e}")

    def _on_note_delete(self, payload: dict):
        try:
            self._service.delete_note(payload.get("id"))
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Note delete failed: {e}")

    # ── Session handlers ──────────────────────────────────────────────────────

    def _on_session_log(self, payload: dict):
        try:
            self._service.log_session(
                project_id          = payload.get("project_id") or self._current_project_id,
                duration_minutes    = payload.get("duration_minutes", 60),
                notes               = payload.get("notes", ""),
                outcome             = payload.get("outcome", ""),
                next_action         = payload.get("next_action", ""),
                linked_milestone_id = payload.get("linked_milestone_id"),
            )
            if self._is_full_ui():
                self._ui._show_success("Session logged!")
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except ValidationError as e:
            if self._is_full_ui():
                self._ui._show_error(str(e))
        except Exception as e:
            print(f"[PROJECT PLUGIN] Session log failed: {e}")

    def _on_session_start(self, payload: dict):
        try:
            pid = payload.get("project_id") or self._current_project_id
            ms_id = payload.get("linked_milestone_id")
            self._service.start_session(pid, linked_milestone_id=ms_id)
            if self._is_full_ui():
                self._ui._show_success("Live session started!")
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Session start failed: {e}")

    def _on_session_end(self, payload: dict):
        try:
            pid = payload.get("project_id") or self._current_project_id
            session = self._service.end_session(
                project_id  = pid,
                notes       = payload.get("notes", ""),
                outcome     = payload.get("outcome", ""),
                next_action = payload.get("next_action", ""),
            )
            if session and self._is_full_ui():
                h = session.duration_minutes // 60
                m = session.duration_minutes % 60
                dur = f"{h}h {m}m" if h else f"{m}m"
                self._ui._show_success(f"Session ended — {dur} logged!")
            if self._current_project_id:
                self._load_project(self._current_project_id)

            # ── Auto-record completed session in the calendar ─────────────────
            self._push_session_to_calendar(pid, session)

        except Exception as e:
            print(f"[PROJECT PLUGIN] Session end failed: {e}")

    def _push_session_to_calendar(self, project_id, session) -> None:
        """Create a completed CalendarEvent record for a finished hobby session."""
        try:
            cal = self.context.services.try_get("calendar_service")
            if cal is None or session is None:
                return
            project = self._service.get_project(project_id)
            project_name = project.name if project else "Unknown Project"
            project_icon = (project.icon + "  ") if project and project.icon else ""

            from datetime import date as _date
            session_date = _date.today().isoformat()
            if session.ended_at:
                try:
                    session_date = session.ended_at[:10]
                except Exception:
                    pass

            h = session.duration_minutes // 60
            m = session.duration_minutes % 60
            dur_str = f"{h}h {m}m" if h else f"{m}m"

            notes_parts = []
            if session.notes:
                notes_parts.append(session.notes)
            if session.outcome:
                notes_parts.append(f"Outcome: {session.outcome}")

            cal.add_event(
                title            = f"{project_icon}{project_name}  ·  {dur_str}",
                session_type     = "Painting Session",
                event_date       = session_date,
                duration_minutes = session.duration_minutes or 60,
                notes            = "\n".join(notes_parts),
                completed        = True,
                auto_generated   = True,
                source_event     = "project_session_end",
                linked_plugin    = "project_tracker",
                linked_id        = str(project_id),
                linked_name      = project_name,
            )
        except Exception as e:
            print(f"[PROJECT PLUGIN] Calendar push failed: {e}")

    def _on_session_delete(self, payload: dict):
        try:
            self._service.delete_session(payload.get("id"))
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Session delete failed: {e}")

    # ── Link handlers ─────────────────────────────────────────────────────────

    def _on_link_entity(self, payload: dict):
        try:
            self._service.link_entity(
                project_id=payload.get("project_id"),
                entity_type=payload.get("entity_type"),
                entity_id=payload.get("entity_id"),
                notes=payload.get("notes", ""),
            )
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Link failed: {e}")

    def _on_unlink_entity(self, payload: dict):
        try:
            self._service.unlink_entity(
                project_id=payload.get("project_id"),
                entity_type=payload.get("entity_type"),
                entity_id=payload.get("entity_id"),
            )
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Unlink failed: {e}")

    # ── Gallery handlers ──────────────────────────────────────────────────────

    def _on_gallery_add(self, payload: dict):
        try:
            self._service.add_gallery_entry(
                project_id     = payload.get("project_id") or self._current_project_id,
                image_path     = payload.get("image_path", ""),
                title          = payload.get("title", ""),
                note           = payload.get("note", ""),
                captured_at    = payload.get("captured_at"),
                milestone_id   = payload.get("milestone_id"),
                session_id     = payload.get("session_id"),
                progress_stage = payload.get("progress_stage", ""),
            )
            if self._is_full_ui():
                self._ui._show_success("Progress photo added!")
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Gallery add failed: {e}")

    def _on_gallery_update(self, payload: dict):
        try:
            entry_id = payload.get("id")
            self._service.update_gallery_entry(entry_id, **{
                k: v for k, v in payload.items()
                if k in ("title", "note", "captured_at", "milestone_id",
                         "session_id", "progress_stage")
            })
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Gallery update failed: {e}")

    def _on_gallery_delete(self, payload: dict):
        try:
            self._service.delete_gallery_entry(payload.get("id"))
            if self._is_full_ui():
                from ui.toast import ToastManager
                ToastManager.instance().show("Progress photo removed.", level="info")
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Gallery delete failed: {e}")


    # ── Requirements handlers ─────────────────────────────────────────────────

    def _on_requirement_add(self, payload: dict):
        try:
            pid = payload.get("project_id") or self._current_project_id
            self._service.add_requirement(
                project_id      = pid,
                item_type       = payload.get("item_type", ""),
                item_name       = payload.get("item_name", ""),
                item_id         = payload.get("item_id"),
                quantity_needed = int(payload.get("quantity_needed") or 1),
                notes           = payload.get("notes", ""),
            )
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Requirement add failed: {e}")

    def _on_requirement_update(self, payload: dict):
        try:
            req_id = payload.get("id")
            if not req_id:
                return
            self._service.update_requirement(req_id, **{
                k: v for k, v in payload.items()
                if k in ("item_name", "item_id", "item_type",
                         "quantity_needed", "notes", "is_ok_override")
            })
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Requirement update failed: {e}")

    def _on_requirement_delete(self, payload: dict):
        try:
            self._service.delete_requirement(payload.get("id"))
            if self._current_project_id:
                self._load_project(self._current_project_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] Requirement delete failed: {e}")

    # ── Dashboard deep-link handler ───────────────────────────────────────────

    def _on_dashboard_navigate(self, payload: dict):
        """Handle deep-link navigation from dashboard recommendations/cards.

        Expected payload keys:
          plugin_id  — must be "project_tracker" (ignored otherwise)
          project_id — optional; if present, open that project
          tab        — optional; e.g. "milestones", "overview", "sessions"
        """
        if payload.get("plugin_id") != self.plugin_id:
            return
        if not self._is_full_ui():
            return
        try:
            pid = payload.get("project_id")
            if pid:
                self._load_project(pid)
                self._ui._list_panel.select_project(pid)
            tab     = payload.get("tab")
            item_id = payload.get("item_id")
            if tab:
                self._ui._detail_panel.navigate_to_tab(tab, item_id=item_id)
        except Exception as e:
            print(f"[PROJECT PLUGIN] dashboard_navigate failed: {e}")
