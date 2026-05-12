"""
Campaign Tracker v2 — Service layer.

Wraps the v1 CampaignService for all core entity CRUD and adds v2-specific
methods (compendium, gallery).
"""
from __future__ import annotations

from typing import Optional


class CampaignV2Service:
    """Facade over v1 service + v2 repository additions."""

    def __init__(self, v1_service, v2_repo, gallery_repo, asset_repo=None):
        self._svc     = v1_service
        self._repo    = v2_repo
        self._gallery = gallery_repo
        self._assets  = asset_repo

    # ── Campaigns ─────────────────────────────────────────────────────────────

    def get_all_campaigns(self):
        return self._svc.get_all_campaigns()

    def get_campaign(self, campaign_id: int):
        return self._svc.get_campaign(campaign_id)

    def create_campaign(self, name: str, game_system: str,
                        status: str = "Active", description: str = "",
                        notes: str = "", start_date: str = "",
                        cover_image_path: str = ""):
        return self._svc.create_campaign(
            name=name, game_system=game_system, status=status,
            description=description or None, notes=notes or None,
            start_date=start_date or None,
            cover_image_path=cover_image_path or None,
        )

    def update_campaign(self, campaign_id: int, **kwargs):
        return self._svc.update_campaign(campaign_id, **kwargs)

    def delete_campaign(self, campaign_id: int):
        try:
            self._gallery.delete_for_campaign(campaign_id)
        except Exception:
            pass
        try:
            self._repo.delete_compendium_for_campaign(campaign_id)
        except Exception:
            pass
        try:
            if self._assets:
                self._assets.delete_for_campaign(campaign_id)
        except Exception:
            pass
        return self._svc.delete_campaign(campaign_id)

    # ── Characters ────────────────────────────────────────────────────────────

    def get_characters(self, campaign_id: int):
        try:
            return self._svc.get_characters(campaign_id)
        except Exception:
            return []

    def get_character(self, char_id: int):
        try:
            return self._svc.get_character(char_id)
        except Exception:
            return None

    def create_character(self, campaign_id: int, name: str,
                         character_role: str = "Player Character", **kwargs):
        return self._svc.add_character(
            campaign_id=campaign_id, name=name,
            character_role=character_role, **kwargs,
        )

    def update_character(self, char_id: int, **kwargs):
        return self._svc.update_character(char_id, **kwargs)

    def delete_character(self, char_id: int):
        return self._svc.delete_character(char_id)

    def get_character_spells(self, char_id: int):
        try:
            return self._svc.get_character_spells(char_id)
        except Exception:
            return []

    def add_character_spell(self, char_id: int, spell_name: str,
                            spell_level: int = 0, notes: str = ""):
        return self._svc.add_character_spell(
            char_id, spell_name=spell_name,
            spell_level=spell_level, notes=notes,
        )

    def delete_character_spell(self, spell_id: int):
        return self._svc.delete_character_spell(spell_id)

    def get_character_inventory(self, char_id: int):
        try:
            return self._svc.get_inventory(char_id)
        except Exception:
            return []

    def add_inventory_item(self, char_id: int, name: str, quantity: int = 1,
                           item_type: str = "Gear", notes: str = ""):
        return self._svc.add_inventory_item(
            char_id, name=name, quantity=quantity,
            item_type=item_type,
        )

    def delete_inventory_item(self, item_id: int):
        return self._svc.delete_inventory_item(item_id)

    # ── Sessions / Battles ────────────────────────────────────────────────────

    def get_sessions(self, campaign_id: int):
        try:
            return sorted(
                self._svc.get_battles(campaign_id),
                key=lambda b: (getattr(b, "session_number", 0) or 0),
            )
        except Exception:
            return []

    def get_session(self, session_id: int):
        try:
            return self._svc.get_battle(session_id)
        except Exception:
            return None

    def create_session(self, campaign_id: int, title: str,
                       session_number: int = 0, date_played: str = "",
                       location_name: str = "", scenario_name: str = "",
                       outcome: str = "In Progress",
                       chronicle_text: str = ""):
        return self._svc.add_battle(
            campaign_id=campaign_id, title=title,
            session_number=session_number,
            date_played=date_played or None,
            location_name=location_name or None,
            scenario_name=scenario_name or None,
            outcome=outcome, chronicle_text=chronicle_text,
        )

    def update_session(self, session_id: int, **kwargs):
        return self._svc.update_battle(session_id, **kwargs)

    def delete_session(self, session_id: int):
        return self._svc.delete_battle(session_id)

    # ── Encounters ────────────────────────────────────────────────────────────

    def get_encounters(self, campaign_id: int):
        try:
            return self._svc.get_encounters(campaign_id)
        except Exception:
            return []

    def get_encounter(self, enc_id: int):
        try:
            return self._svc.get_encounter(enc_id)  if hasattr(self._svc, "get_encounter") else None
        except Exception:
            return None

    def create_encounter(self, campaign_id: int, name: str,
                         description: str = "", difficulty: str = "Medium"):
        return self._svc.add_encounter(
            campaign_id=campaign_id, name=name,
            description=description, difficulty=difficulty,
        )

    def update_encounter(self, encounter, **kwargs):
        """Pass an Encounter object (v1 takes the object, not id+kwargs)."""
        try:
            for k, v in kwargs.items():
                setattr(encounter, k, v)
            return self._svc.update_encounter(encounter)
        except Exception as e:
            print(f"[CAMPAIGN V2] update_encounter: {e}")

    def delete_encounter(self, enc_id: int):
        return self._svc.delete_encounter(enc_id)

    def get_monsters(self, encounter_id: int):
        try:
            return self._svc.get_encounter_monsters(encounter_id)
        except Exception:
            return []

    def add_monster(self, encounter_id: int, name: str, count: int = 1,
                    cr: str = "1", hp_override: int = 0, notes: str = ""):
        return self._svc.add_encounter_monster(
            encounter_id=encounter_id, monster_name=name,
            count=count, cr=cr,
            hp_override=hp_override or None, notes=notes,
        )

    def remove_monster(self, monster_id: int):
        return self._svc.delete_encounter_monster(monster_id)

    # ── Players ───────────────────────────────────────────────────────────────

    def get_players(self, campaign_id: int):
        try:
            return self._svc.get_players(campaign_id)
        except Exception:
            return []

    # ── Journal ───────────────────────────────────────────────────────────────

    def get_journal_entries(self, campaign_id: int):
        try:
            return self._svc.get_journal_entries(campaign_id)
        except Exception:
            return []

    def create_journal_entry(self, campaign_id: int, title: str,
                             content: str = "", battle_id=None):
        return self._svc.add_journal_entry(
            campaign_id=campaign_id, title=title,
            content=content, battle_id=battle_id,
        )

    def update_journal_entry(self, entry_id: int, title: str, content: str):
        return self._svc.update_journal_entry(
            entry_id=entry_id, title=title, content=content,
        )

    def delete_journal_entry(self, entry_id: int):
        return self._svc.delete_journal_entry(entry_id)

    # ── Dice ──────────────────────────────────────────────────────────────────

    def log_roll(self, expression: str, result: int, detail: str = ""):
        try:
            return self._svc.log_dice_roll(
                expression=expression, result=result, detail=detail,
            )
        except Exception:
            pass

    def get_roll_history(self, limit: int = 50):
        try:
            return self._svc.get_dice_log(limit=limit)
        except Exception:
            return []

    def get_saved_expressions(self):
        try:
            return self._svc.get_saved_expressions()
        except Exception:
            return []

    def save_expression(self, name: str, expression: str):
        try:
            return self._svc.add_saved_expression(name=name, expression=expression)
        except Exception:
            pass

    def delete_saved_expression(self, expr_id: int):
        try:
            return self._svc.delete_saved_expression(expr_id)
        except Exception:
            pass

    # ── Compendium ────────────────────────────────────────────────────────────

    def get_compendium(self, campaign_id: int, category: str | None = None):
        return self._repo.get_compendium(campaign_id, category)

    def get_compendium_categories(self, campaign_id: int) -> list[str]:
        return self._repo.get_compendium_categories(campaign_id)

    def add_compendium_entry(self, campaign_id: int, category: str,
                             title: str, content: str = "",
                             tags: str = "", source: str = "") -> int:
        return self._repo.add_compendium_entry(
            campaign_id, category, title, content, tags, source,
        )

    def update_compendium_entry(self, entry_id: int, category: str,
                                title: str, content: str,
                                tags: str = "", source: str = ""):
        return self._repo.update_compendium_entry(
            entry_id, category, title, content, tags, source,
        )

    def delete_compendium_entry(self, entry_id: int):
        return self._repo.delete_compendium_entry(entry_id)

    def search_compendium(self, campaign_id: int, query: str):
        return self._repo.search_compendium(campaign_id, query)

    # ── Gallery ───────────────────────────────────────────────────────────────

    def get_gallery(self, campaign_id: int):
        return self._gallery.get_for_campaign(campaign_id)

    def add_gallery_image(self, campaign_id: int, image_path: str,
                          caption: str = "", stage: str = "") -> int:
        return self._gallery.add_image(campaign_id, image_path, caption, stage)

    def update_gallery_entry(self, entry_id: int, caption: str, stage: str):
        return self._gallery.update_entry(entry_id, caption, stage)

    def update_gallery_stage(self, entry_id: int, stage: str):
        return self._gallery.update_stage(entry_id, stage)

    def delete_gallery_image(self, entry_id: int):
        return self._gallery.delete_image(entry_id)

    # ── Statistics ────────────────────────────────────────────────────────────

    def get_campaign_stats(self, campaign_id: int) -> dict:
        try:
            characters  = self.get_characters(campaign_id)
            sessions    = self.get_sessions(campaign_id)
            encounters  = self.get_encounters(campaign_id)
            compendium  = self.get_compendium(campaign_id)
            gallery_cnt = self._gallery.count_for_campaign(campaign_id)
            return {
                "characters": len(characters),
                "pcs": sum(1 for c in characters
                           if "player" in (getattr(c, "character_role", "") or "").lower()),
                "sessions":   len(sessions),
                "encounters": len(encounters),
                "compendium": len(compendium),
                "gallery":    gallery_cnt,
            }
        except Exception:
            return {k: 0 for k in
                    ["characters", "pcs", "sessions", "encounters", "compendium", "gallery"]}

    # ── Assets ────────────────────────────────────────────────────────────────

    def get_assets(self, campaign_id: int, category: str | None = None):
        if not self._assets:
            return []
        try:
            return self._assets.get_assets(campaign_id, category)
        except Exception:
            return []

    def get_asset_category_counts(self, campaign_id: int) -> dict[str, int]:
        if not self._assets:
            return {}
        try:
            return self._assets.get_category_counts(campaign_id)
        except Exception:
            return {}

    def add_asset(self, campaign_id: int, name: str, file_path: str,
                  category: str = "other", tags: str = "",
                  notes: str = "") -> int:
        if not self._assets:
            return -1
        return self._assets.add_asset(campaign_id, name, file_path,
                                       category, tags, notes)

    def update_asset(self, asset_id: int, name: str, category: str,
                     tags: str = "", notes: str = "") -> bool:
        if not self._assets:
            return False
        return self._assets.update_asset(asset_id, name, category, tags, notes)

    def delete_asset(self, asset_id: int) -> bool:
        if not self._assets:
            return False
        return self._assets.delete_asset(asset_id)
