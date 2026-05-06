"""
Campaign Tracker Service

Business logic layer. Registered as 'campaign_service' in ServiceRegistry.
"""
from __future__ import annotations

from typing import Optional

from .models import (
    Campaign, CampaignPlayer, Character, CharacterImage,
    Battle, BattleParticipant, BattleImage, CampaignImage,
    JournalEntry, CampaignAsset, DiceRoll, CampaignStatistics,
    SavedExpression, CharacterSpell, InventoryItem, Encounter, EncounterMonster,
    ValidationError,
)
from .repository import CampaignRepository


class CampaignService:
    def __init__(self, repo: CampaignRepository):
        self.repo = repo

    # ── Campaigns ──────────────────────────────────────────────────────────────

    def create_campaign(self, name: str, game_system: str, status: str = "Active",
                        description=None, notes=None, start_date=None,
                        cover_image_path=None, assets_folder=None) -> Campaign:
        c = Campaign(
            name=name, game_system=game_system, status=status,
            description=description, notes=notes, start_date=start_date,
            cover_image_path=cover_image_path, assets_folder=assets_folder,
        )
        c.id = self.repo.add_campaign(c)
        return c

    def update_campaign(self, campaign_id: int, **kwargs) -> Campaign:
        existing = self.repo.get_campaign(campaign_id)
        if not existing:
            raise ValueError(f"Campaign {campaign_id} not found")
        for k, v in kwargs.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        existing._validate()
        self.repo.update_campaign(existing)
        return existing

    def delete_campaign(self, campaign_id: int) -> bool:
        return self.repo.delete_campaign(campaign_id)

    def get_campaign(self, campaign_id: int) -> Optional[Campaign]:
        return self.repo.get_campaign(campaign_id)

    def get_all_campaigns(self) -> list[Campaign]:
        return self.repo.get_all_campaigns()

    # ── Players ────────────────────────────────────────────────────────────────

    def add_player(self, campaign_id: int, player_name: str, role: str = "Player",
                   notes=None) -> CampaignPlayer:
        p = CampaignPlayer(campaign_id=campaign_id, player_name=player_name,
                           role=role, notes=notes)
        p.id = self.repo.add_player(p)
        return p

    def update_player(self, player_id: int, player_name: str, role: str,
                      notes=None) -> CampaignPlayer:
        p = self.repo.get_player(player_id)
        if not p:
            raise ValueError(f"Player {player_id} not found")
        p.player_name = player_name
        p.role = role
        p.notes = notes
        self.repo.update_player(p)
        return p

    def delete_player(self, player_id: int) -> bool:
        return self.repo.delete_player(player_id)

    def get_players(self, campaign_id: int) -> list[CampaignPlayer]:
        return self.repo.get_players_for_campaign(campaign_id)

    # ── Characters ─────────────────────────────────────────────────────────────

    def add_character(self, campaign_id: int, name: str,
                      character_role: str = "Player Character",
                      status: str = "Active", **kwargs) -> Character:
        ch = Character(campaign_id=campaign_id, name=name,
                       character_role=character_role, status=status, **kwargs)
        ch.id = self.repo.add_character(ch)
        return ch

    def update_character(self, character_id: int, **kwargs) -> Character:
        existing = self.repo.get_character(character_id)
        if not existing:
            raise ValueError(f"Character {character_id} not found")
        for k, v in kwargs.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        self.repo.update_character(existing)
        return existing

    def delete_character(self, character_id: int) -> bool:
        return self.repo.delete_character(character_id)

    def get_character(self, character_id: int) -> Optional[Character]:
        return self.repo.get_character(character_id)

    def get_characters(self, campaign_id: int) -> list[Character]:
        return self.repo.get_characters_for_campaign(campaign_id)

    # ── Character images ───────────────────────────────────────────────────────

    def add_character_image(self, character_id: int, image_path: str) -> int:
        img = CharacterImage(character_id=character_id, image_path=image_path)
        return self.repo.add_character_image(img)

    def get_character_images(self, character_id: int) -> list[dict]:
        return self.repo.get_images_for_character(character_id)

    def delete_character_image(self, img_id: int) -> bool:
        return self.repo.delete_character_image(img_id)

    def update_character_image_crop(self, img_id: int,
                                    zoom: float, fx: float, fy: float):
        self.repo.update_character_image_crop(img_id, zoom, fx, fy)

    def set_primary_character_image(self, character_id: int, image_path: str,
                                    zoom: float = 1.0, fx: float = 0.5, fy: float = 0.5):
        self.repo.db.execute(
            f"UPDATE {self.repo.CHAR_IMAGE_TABLE} SET is_primary=0 WHERE character_id=?",
            (character_id,),
        )
        self.repo.db.execute(
            f"UPDATE {self.repo.CHAR_IMAGE_TABLE} "
            f"SET is_primary=1, zoom=?, focal_x=?, focal_y=? "
            f"WHERE character_id=? AND image_path=?",
            (zoom, fx, fy, character_id, image_path),
        )
        ch = self.repo.get_character(character_id)
        if ch:
            ch.primary_image_path = image_path
            self.repo.update_character(ch)

    # ── Character spells ──────────────────────────────────────────────────────

    def add_character_spell(self, character_id: int, spell_name: str,
                            spell_level: int = 0, is_prepared: bool = False,
                            is_ritual: bool = False, notes: str = None,
                            source: str = None) -> CharacterSpell:
        spell = CharacterSpell(
            character_id=character_id, spell_name=spell_name,
            spell_level=spell_level, is_prepared=is_prepared,
            is_ritual=is_ritual, notes=notes, source=source,
        )
        spell.id = self.repo.add_character_spell(spell)
        return spell

    def update_character_spell(self, spell: CharacterSpell):
        self.repo.update_character_spell(spell)

    def delete_character_spell(self, spell_id: int):
        self.repo.delete_character_spell(spell_id)

    def get_character_spells(self, character_id: int) -> list[CharacterSpell]:
        return self.repo.get_spells_for_character(character_id)

    # ── Inventory ─────────────────────────────────────────────────────────────

    def add_inventory_item(self, character_id: int, name: str, **kwargs) -> InventoryItem:
        item = InventoryItem(character_id=character_id, name=name, **kwargs)
        item.id = self.repo.add_inventory_item(item)
        return item

    def update_inventory_item(self, item: InventoryItem):
        self.repo.update_inventory_item(item)

    def delete_inventory_item(self, item_id: int):
        self.repo.delete_inventory_item(item_id)

    def get_inventory(self, character_id: int) -> list[InventoryItem]:
        return self.repo.get_inventory_for_character(character_id)

    # ── Encounters ────────────────────────────────────────────────────────────

    def add_encounter(self, campaign_id: int, name: str, **kwargs) -> Encounter:
        enc = Encounter(campaign_id=campaign_id, name=name, **kwargs)
        enc.id = self.repo.add_encounter(enc)
        return enc

    def update_encounter(self, enc: Encounter):
        self.repo.update_encounter(enc)

    def delete_encounter(self, enc_id: int):
        self.repo.delete_encounter(enc_id)

    def get_encounters(self, campaign_id: int) -> list[Encounter]:
        return self.repo.get_encounters_for_campaign(campaign_id)

    def add_encounter_monster(self, encounter_id: int, monster_name: str,
                              count: int = 1, hp_override: int = None,
                              notes: str = None, cr: str = None) -> EncounterMonster:
        m = EncounterMonster(encounter_id=encounter_id, monster_name=monster_name,
                             count=count, hp_override=hp_override, notes=notes, cr=cr)
        m.id = self.repo.add_encounter_monster(m)
        return m

    def update_encounter_monster(self, m: EncounterMonster):
        self.repo.update_encounter_monster(m)

    def delete_encounter_monster(self, monster_id: int):
        self.repo.delete_encounter_monster(monster_id)

    def get_encounter_monsters(self, enc_id: int) -> list[EncounterMonster]:
        return self.repo.get_monsters_for_encounter(enc_id)

    # ── Battles ────────────────────────────────────────────────────────────────

    def add_battle(self, campaign_id: int, title: str, **kwargs) -> Battle:
        existing = self.repo.get_battles_for_campaign(campaign_id)
        next_num = max((b.session_number for b in existing), default=0) + 1
        kwargs.setdefault("session_number", next_num)
        b = Battle(campaign_id=campaign_id, title=title, **kwargs)
        b.id = self.repo.add_battle(b)
        return b

    def update_battle(self, battle_id: int, **kwargs) -> Battle:
        existing = self.repo.get_battle(battle_id)
        if not existing:
            raise ValueError(f"Battle {battle_id} not found")
        for k, v in kwargs.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        self.repo.update_battle(existing)
        return existing

    def delete_battle(self, battle_id: int) -> bool:
        return self.repo.delete_battle(battle_id)

    def get_battle(self, battle_id: int) -> Optional[Battle]:
        return self.repo.get_battle(battle_id)

    def get_battles(self, campaign_id: int) -> list[Battle]:
        return self.repo.get_battles_for_campaign(campaign_id)

    # ── Participants ───────────────────────────────────────────────────────────

    def set_participants(self, battle_id: int,
                         participants: list[dict]) -> list[BattleParticipant]:
        self.repo.delete_participants_for_battle(battle_id)
        result = []
        for p in participants:
            bp = BattleParticipant(
                battle_id=battle_id,
                player_id=p["player_id"],
                side=p.get("side", ""),
                army_id=p.get("army_id"),
                score=p.get("score", 0),
                result=p.get("result", ""),
                notes=p.get("notes"),
            )
            bp.id = self.repo.add_participant(bp)
            result.append(bp)
        return result

    def get_participants(self, battle_id: int) -> list[BattleParticipant]:
        return self.repo.get_participants_for_battle(battle_id)

    # ── Battle images ──────────────────────────────────────────────────────────

    def add_battle_image(self, battle_id: int, image_path: str) -> int:
        img = BattleImage(battle_id=battle_id, image_path=image_path)
        return self.repo.add_battle_image(img)

    def get_battle_images(self, battle_id: int) -> list[dict]:
        return self.repo.get_images_for_battle(battle_id)

    def delete_battle_image(self, img_id: int) -> bool:
        return self.repo.delete_battle_image(img_id)

    def update_battle_image_crop(self, img_id: int,
                                 zoom: float, fx: float, fy: float):
        self.repo.update_battle_image_crop(img_id, zoom, fx, fy)

    def set_primary_battle_image(self, battle_id: int, image_path: str,
                                 zoom: float = 1.0, fx: float = 0.5, fy: float = 0.5):
        self.repo.db.execute(
            f"UPDATE {self.repo.BATTLE_IMAGE_TABLE} SET is_primary=0 WHERE battle_id=?",
            (battle_id,),
        )
        self.repo.db.execute(
            f"UPDATE {self.repo.BATTLE_IMAGE_TABLE} "
            f"SET is_primary=1, zoom=?, focal_x=?, focal_y=? "
            f"WHERE battle_id=? AND image_path=?",
            (zoom, fx, fy, battle_id, image_path),
        )
        b = self.repo.get_battle(battle_id)
        if b:
            b.primary_image_path = image_path
            self.repo.update_battle(b)

    # ── Campaign images ────────────────────────────────────────────────────────

    def add_campaign_image(self, campaign_id: int, image_path: str,
                           caption: str = "") -> int:
        img = CampaignImage(campaign_id=campaign_id, image_path=image_path,
                            caption=caption)
        return self.repo.add_campaign_image(img)

    def get_campaign_images(self, campaign_id: int) -> list[dict]:
        return self.repo.get_images_for_campaign(campaign_id)

    def delete_campaign_image(self, img_id: int) -> bool:
        return self.repo.delete_campaign_image(img_id)

    def update_campaign_image_crop(self, img_id: int,
                                   zoom: float, fx: float, fy: float):
        self.repo.update_campaign_image_crop(img_id, zoom, fx, fy)

    def update_campaign_image_caption(self, img_id: int, caption: str):
        self.repo.update_campaign_image_caption(img_id, caption)

    def set_primary_campaign_image(self, campaign_id: int, image_path: str,
                                   zoom: float = 1.0, fx: float = 0.5,
                                   fy: float = 0.5):
        self.repo.db.execute(
            f"UPDATE {self.repo.CAMPAIGN_IMAGE_TABLE} SET is_primary=0 "
            f"WHERE campaign_id=?",
            (campaign_id,),
        )
        self.repo.db.execute(
            f"UPDATE {self.repo.CAMPAIGN_IMAGE_TABLE} "
            f"SET is_primary=1, zoom=?, focal_x=?, focal_y=? "
            f"WHERE campaign_id=? AND image_path=?",
            (zoom, fx, fy, campaign_id, image_path),
        )
        c = self.repo.get_campaign(campaign_id)
        if c:
            c.cover_image_path = image_path
            self.repo.update_campaign(c)

    # ── Journal ────────────────────────────────────────────────────────────────

    def add_journal_entry(self, campaign_id: int, title: str, content: str,
                          battle_id=None) -> JournalEntry:
        j = JournalEntry(campaign_id=campaign_id, title=title, content=content,
                         battle_id=battle_id)
        j.id = self.repo.add_journal_entry(j)
        return j

    def update_journal_entry(self, entry_id: int, title: str, content: str,
                              battle_id=None) -> JournalEntry:
        j = self.repo.get_journal_entry(entry_id)
        if not j:
            raise ValueError(f"Journal entry {entry_id} not found")
        j.title = title
        j.content = content
        j.battle_id = battle_id
        self.repo.update_journal_entry(j)
        return j

    def delete_journal_entry(self, entry_id: int) -> bool:
        return self.repo.delete_journal_entry(entry_id)

    def get_journal_entries(self, campaign_id: int) -> list[JournalEntry]:
        return self.repo.get_journal_entries_for_campaign(campaign_id)

    # ── Assets ─────────────────────────────────────────────────────────────────

    def add_asset(self, campaign_id: int, name: str, file_path: str,
                  asset_type: str = "Other", notes=None) -> CampaignAsset:
        a = CampaignAsset(campaign_id=campaign_id, name=name, file_path=file_path,
                          asset_type=asset_type, notes=notes)
        a.id = self.repo.add_asset(a)
        return a

    def delete_asset(self, asset_id: int) -> bool:
        return self.repo.delete_asset(asset_id)

    def get_assets(self, campaign_id: int) -> list[CampaignAsset]:
        return self.repo.get_assets_for_campaign(campaign_id)

    # ── Dice ───────────────────────────────────────────────────────────────────

    def log_dice_roll(self, expression: str, result: int, detail: str) -> DiceRoll:
        roll = DiceRoll(expression=expression, result=result, detail=detail)
        roll.id = self.repo.add_dice_roll(roll)
        return roll

    def get_dice_log(self, limit: int = 100) -> list[DiceRoll]:
        return self.repo.get_dice_log(limit)

    def clear_dice_log(self):
        self.repo.clear_dice_log()

    # ── Saved Expressions ─────────────────────────────────────────────────────

    def add_saved_expression(self, name: str, expression: str) -> SavedExpression:
        expr = SavedExpression(name=name.strip(), expression=expression.strip())
        expr.id = self.repo.add_saved_expression(expr)
        return expr

    def update_saved_expression(self, expr_id: int, name: str, expression: str) -> SavedExpression:
        expr = SavedExpression(name=name.strip(), expression=expression.strip(), id=expr_id)
        self.repo.update_saved_expression(expr)
        return expr

    def delete_saved_expression(self, expr_id: int):
        self.repo.delete_saved_expression(expr_id)

    def get_saved_expressions(self) -> list[SavedExpression]:
        return self.repo.get_saved_expressions()

    # ── Statistics ─────────────────────────────────────────────────────────────

    def get_statistics(self) -> CampaignStatistics:
        return self.repo.get_statistics()

    # ── Cross-plugin ───────────────────────────────────────────────────────────

    def on_model_removed(self, model_id: int):
        self.repo.remove_model_links(model_id)
        print(f"[CAMPAIGN SERVICE] Nullified model_id={model_id} links in characters")


# ── Auto-registration ──────────────────────────────────────────────────────────

def register(context):
    print("[CAMPAIGN_TRACKER] Registering service...")
    db = context.services.get("db")
    from .repository import CampaignRepository
    repo = CampaignRepository(db)
    service = CampaignService(repo)
    context.services.register("campaign_service", service, override=True)
    print("[CAMPAIGN_TRACKER] Service registered as 'campaign_service'")
    return service
