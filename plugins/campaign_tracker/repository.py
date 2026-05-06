"""
Campaign Tracker Repository

All SQLite access for campaign_tracker plugin.
Tables are prefixed with 'campaign_tracker_' to avoid conflicts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .models import (
    Campaign, CampaignPlayer, Character, CharacterImage,
    Battle, BattleParticipant, BattleImage, CampaignImage,
    JournalEntry, CampaignAsset, DiceRoll, CampaignStatistics,
    SavedExpression, CharacterSpell, InventoryItem, Encounter, EncounterMonster,
)


class CampaignRepository:
    CAMPAIGN_TABLE     = "campaign_tracker_campaigns"
    PLAYER_TABLE       = "campaign_tracker_players"
    CHARACTER_TABLE    = "campaign_tracker_characters"
    CHAR_IMAGE_TABLE   = "campaign_tracker_character_images"
    BATTLE_TABLE       = "campaign_tracker_battles"
    PARTICIPANT_TABLE  = "campaign_tracker_battle_participants"
    BATTLE_IMAGE_TABLE = "campaign_tracker_battle_images"
    JOURNAL_TABLE      = "campaign_tracker_journal"
    ASSET_TABLE        = "campaign_tracker_assets"
    DICE_LOG_TABLE     = "campaign_tracker_dice_log"
    SAVED_EXPR_TABLE   = "campaign_tracker_saved_expressions"
    CHAR_SPELL_TABLE   = "campaign_tracker_character_spells"
    INVENTORY_TABLE    = "campaign_tracker_inventory"
    ENCOUNTER_TABLE      = "campaign_tracker_encounters"
    ENC_MONSTER_TABLE    = "campaign_tracker_encounter_monsters"
    CAMPAIGN_IMAGE_TABLE = "campaign_tracker_campaign_images"

    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self):
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.CAMPAIGN_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                game_system TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Active',
                description TEXT,
                notes TEXT,
                start_date TEXT,
                cover_image_path TEXT,
                assets_folder TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.PLAYER_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                player_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Player',
                notes TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.CHARACTER_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                character_role TEXT NOT NULL DEFAULT 'Player Character',
                status TEXT NOT NULL DEFAULT 'Active',
                player_id INTEGER,
                model_id INTEGER,
                character_class TEXT,
                race TEXT,
                level INTEGER DEFAULT 1,
                hit_points INTEGER DEFAULT 0,
                max_hit_points INTEGER DEFAULT 0,
                armor_class INTEGER DEFAULT 0,
                stat_style TEXT DEFAULT 'D&D 5e',
                stats_json TEXT,
                background TEXT,
                traits TEXT,
                equipment_notes TEXT,
                notes TEXT,
                primary_image_path TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.CHAR_IMAGE_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                is_primary INTEGER DEFAULT 0,
                zoom REAL DEFAULT 1.0,
                focal_x REAL DEFAULT 0.5,
                focal_y REAL DEFAULT 0.5
            )
        """)
        # Migrations: add crop columns to existing DBs
        for col, dflt in [("zoom", "1.0"), ("focal_x", "0.5"), ("focal_y", "0.5")]:
            try:
                self.db.execute(f"ALTER TABLE {self.CHAR_IMAGE_TABLE} ADD COLUMN {col} REAL DEFAULT {dflt}")
            except Exception:
                pass
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.BATTLE_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                session_number INTEGER DEFAULT 1,
                date_played TEXT,
                location_name TEXT,
                scenario_name TEXT,
                scenario_description TEXT,
                outcome TEXT DEFAULT 'In Progress',
                scoring_notes TEXT,
                chronicle_text TEXT,
                primary_image_path TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.PARTICIPANT_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                battle_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                side TEXT DEFAULT '',
                army_id INTEGER,
                score INTEGER DEFAULT 0,
                result TEXT DEFAULT '',
                notes TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.BATTLE_IMAGE_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                battle_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                is_primary INTEGER DEFAULT 0,
                zoom REAL DEFAULT 1.0,
                focal_x REAL DEFAULT 0.5,
                focal_y REAL DEFAULT 0.5
            )
        """)
        # Migrations: add crop columns to existing DBs
        for col, dflt in [("zoom", "1.0"), ("focal_x", "0.5"), ("focal_y", "0.5")]:
            try:
                self.db.execute(f"ALTER TABLE {self.BATTLE_IMAGE_TABLE} ADD COLUMN {col} REAL DEFAULT {dflt}")
            except Exception:
                pass
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.JOURNAL_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                battle_id INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ASSET_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                asset_type TEXT DEFAULT 'Other',
                notes TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.DICE_LOG_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expression TEXT NOT NULL,
                result INTEGER NOT NULL,
                detail TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.SAVED_EXPR_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                expression TEXT NOT NULL
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.CHAR_SPELL_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                spell_name TEXT NOT NULL,
                spell_level INTEGER DEFAULT 0,
                is_prepared INTEGER DEFAULT 0,
                is_ritual INTEGER DEFAULT 0,
                notes TEXT,
                source TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.INVENTORY_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                weight REAL DEFAULT 0.0,
                value_gp REAL DEFAULT 0.0,
                equipped INTEGER DEFAULT 0,
                description TEXT,
                item_type TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ENCOUNTER_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                difficulty TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ENC_MONSTER_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER NOT NULL,
                monster_name TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                hp_override INTEGER,
                notes TEXT,
                cr TEXT
            )
        """)
        self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.CAMPAIGN_IMAGE_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                caption TEXT DEFAULT '',
                is_primary INTEGER DEFAULT 0,
                zoom REAL DEFAULT 1.0,
                focal_x REAL DEFAULT 0.5,
                focal_y REAL DEFAULT 0.5
            )
        """)
        # Migrations for campaign_images (in case table existed without caption)
        try:
            self.db.execute(
                f"ALTER TABLE {self.CAMPAIGN_IMAGE_TABLE} ADD COLUMN caption TEXT DEFAULT ''"
            )
        except Exception:
            pass

        # Migrate existing character table to add new columns
        for col, dflt in [
            ("experience_points",  "0"),
            ("death_saves_success","0"),
            ("death_saves_failure","0"),
            ("currency_json",      "NULL"),
            ("spell_slots_json",   "NULL"),
        ]:
            try:
                self.db.execute(
                    f"ALTER TABLE {self.CHARACTER_TABLE} ADD COLUMN {col} "
                    f"{'INTEGER' if dflt != 'NULL' else 'TEXT'} DEFAULT {dflt}"
                )
            except Exception:
                pass   # column already exists

    # ── Campaigns ──────────────────────────────────────────────────────────────

    def add_campaign(self, c: Campaign) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {self.CAMPAIGN_TABLE}
                (name, game_system, status, description, notes,
                 start_date, cover_image_path, assets_folder)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (c.name.strip(), c.game_system, c.status, c.description,
              c.notes, c.start_date, c.cover_image_path, c.assets_folder))
        return cur.lastrowid

    def get_campaign(self, cid: int) -> Optional[Campaign]:
        rows = self.db.query(f"SELECT * FROM {self.CAMPAIGN_TABLE} WHERE id=?", (cid,))
        return self._row_to_campaign(rows[0]) if rows else None

    def get_all_campaigns(self) -> list[Campaign]:
        rows = self.db.query(f"SELECT * FROM {self.CAMPAIGN_TABLE} ORDER BY name")
        return [self._row_to_campaign(r) for r in rows]

    def update_campaign(self, c: Campaign) -> bool:
        cur = self.db.execute(f"""
            UPDATE {self.CAMPAIGN_TABLE} SET
                name=?, game_system=?, status=?, description=?, notes=?,
                start_date=?, cover_image_path=?, assets_folder=?
            WHERE id=?
        """, (c.name.strip(), c.game_system, c.status, c.description,
              c.notes, c.start_date, c.cover_image_path, c.assets_folder, c.id))
        return cur.rowcount > 0

    def delete_campaign(self, cid: int) -> bool:
        cur = self.db.execute(f"DELETE FROM {self.CAMPAIGN_TABLE} WHERE id=?", (cid,))
        return cur.rowcount > 0

    def _row_to_campaign(self, row) -> Campaign:
        return Campaign(
            id=row["id"], name=row["name"], game_system=row["game_system"],
            status=row["status"], description=row["description"], notes=row["notes"],
            start_date=row["start_date"], cover_image_path=row["cover_image_path"],
            assets_folder=row["assets_folder"],
        )

    # ── Players ────────────────────────────────────────────────────────────────

    def add_player(self, p: CampaignPlayer) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {self.PLAYER_TABLE} (campaign_id, player_name, role, notes)
            VALUES (?, ?, ?, ?)
        """, (p.campaign_id, p.player_name.strip(), p.role, p.notes))
        return cur.lastrowid

    def get_player(self, pid: int) -> Optional[CampaignPlayer]:
        rows = self.db.query(f"SELECT * FROM {self.PLAYER_TABLE} WHERE id=?", (pid,))
        return self._row_to_player(rows[0]) if rows else None

    def get_players_for_campaign(self, cid: int) -> list[CampaignPlayer]:
        rows = self.db.query(
            f"SELECT * FROM {self.PLAYER_TABLE} WHERE campaign_id=? ORDER BY player_name",
            (cid,))
        return [self._row_to_player(r) for r in rows]

    def update_player(self, p: CampaignPlayer) -> bool:
        cur = self.db.execute(f"""
            UPDATE {self.PLAYER_TABLE} SET player_name=?, role=?, notes=? WHERE id=?
        """, (p.player_name.strip(), p.role, p.notes, p.id))
        return cur.rowcount > 0

    def delete_player(self, pid: int) -> bool:
        cur = self.db.execute(f"DELETE FROM {self.PLAYER_TABLE} WHERE id=?", (pid,))
        return cur.rowcount > 0

    def _row_to_player(self, row) -> CampaignPlayer:
        return CampaignPlayer(
            id=row["id"], campaign_id=row["campaign_id"],
            player_name=row["player_name"], role=row["role"], notes=row["notes"],
        )

    # ── Characters ─────────────────────────────────────────────────────────────

    def add_character(self, ch: Character) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {self.CHARACTER_TABLE}
                (campaign_id, name, character_role, status, player_id, model_id,
                 character_class, race, level, hit_points, max_hit_points, armor_class,
                 stat_style, stats_json, background, traits, equipment_notes, notes,
                 primary_image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ch.campaign_id, ch.name.strip(), ch.character_role, ch.status,
            ch.player_id, ch.model_id, ch.character_class, ch.race, ch.level,
            ch.hit_points, ch.max_hit_points, ch.armor_class,
            ch.stat_style, ch.stats_json, ch.background, ch.traits,
            ch.equipment_notes, ch.notes, ch.primary_image_path,
        ))
        return cur.lastrowid

    def get_character(self, ch_id: int) -> Optional[Character]:
        rows = self.db.query(f"SELECT * FROM {self.CHARACTER_TABLE} WHERE id=?", (ch_id,))
        return self._row_to_character(rows[0]) if rows else None

    def get_characters_for_campaign(self, cid: int) -> list[Character]:
        rows = self.db.query(
            f"SELECT * FROM {self.CHARACTER_TABLE} WHERE campaign_id=? ORDER BY character_role, name",
            (cid,))
        return [self._row_to_character(r) for r in rows]

    def update_character(self, ch: Character) -> bool:
        cur = self.db.execute(f"""
            UPDATE {self.CHARACTER_TABLE} SET
                name=?, character_role=?, status=?, player_id=?, model_id=?,
                character_class=?, race=?, level=?, hit_points=?, max_hit_points=?,
                armor_class=?, stat_style=?, stats_json=?, background=?, traits=?,
                equipment_notes=?, notes=?, primary_image_path=?
            WHERE id=?
        """, (
            ch.name.strip(), ch.character_role, ch.status, ch.player_id, ch.model_id,
            ch.character_class, ch.race, ch.level, ch.hit_points, ch.max_hit_points,
            ch.armor_class, ch.stat_style, ch.stats_json, ch.background, ch.traits,
            ch.equipment_notes, ch.notes, ch.primary_image_path, ch.id,
        ))
        return cur.rowcount > 0

    def delete_character(self, ch_id: int) -> bool:
        cur = self.db.execute(f"DELETE FROM {self.CHARACTER_TABLE} WHERE id=?", (ch_id,))
        return cur.rowcount > 0

    def remove_model_links(self, model_id: int):
        self.db.execute(
            f"UPDATE {self.CHARACTER_TABLE} SET model_id=NULL WHERE model_id=?",
            (model_id,))

    def _row_to_character(self, row) -> Character:
        # Use dict() so we can safely use .get() for columns that may not
        # exist in databases created before migrations ran (M-12).
        d = dict(row)
        return Character(
            id=d["id"], campaign_id=d["campaign_id"], name=d["name"],
            character_role=d["character_role"], status=d["status"],
            player_id=d.get("player_id"), model_id=d.get("model_id"),
            character_class=d.get("character_class"), race=d.get("race"),
            level=d.get("level") or 1, hit_points=d.get("hit_points") or 0,
            max_hit_points=d.get("max_hit_points") or 0,
            armor_class=d.get("armor_class") or 0,
            stat_style=d.get("stat_style") or "D&D 5e",
            stats_json=d.get("stats_json"), background=d.get("background"),
            traits=d.get("traits"), equipment_notes=d.get("equipment_notes"),
            notes=d.get("notes"), primary_image_path=d.get("primary_image_path"),
            experience_points=d.get("experience_points") or 0,
            death_saves_success=d.get("death_saves_success") or 0,
            death_saves_failure=d.get("death_saves_failure") or 0,
            currency_json=d.get("currency_json"),
            spell_slots_json=d.get("spell_slots_json"),
        )

    # ── Character spells ───────────────────────────────────────────────────────

    def add_character_spell(self, spell: CharacterSpell) -> int:
        cur = self.db.execute(
            f"INSERT INTO {self.CHAR_SPELL_TABLE} "
            f"(character_id, spell_name, spell_level, is_prepared, is_ritual, notes, source) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (spell.character_id, spell.spell_name, spell.spell_level,
             1 if spell.is_prepared else 0, 1 if spell.is_ritual else 0,
             spell.notes, spell.source),
        )
        return cur.lastrowid

    def update_character_spell(self, spell: CharacterSpell):
        self.db.execute(
            f"UPDATE {self.CHAR_SPELL_TABLE} SET "
            f"spell_name=?, spell_level=?, is_prepared=?, is_ritual=?, notes=?, source=? "
            f"WHERE id=?",
            (spell.spell_name, spell.spell_level, 1 if spell.is_prepared else 0,
             1 if spell.is_ritual else 0, spell.notes, spell.source, spell.id),
        )

    def delete_character_spell(self, spell_id: int):
        self.db.execute(f"DELETE FROM {self.CHAR_SPELL_TABLE} WHERE id=?", (spell_id,))

    def get_spells_for_character(self, ch_id: int) -> list[CharacterSpell]:
        rows = self.db.query(
            f"SELECT * FROM {self.CHAR_SPELL_TABLE} WHERE character_id=? ORDER BY spell_level, spell_name",
            (ch_id,),
        )
        return [CharacterSpell(
            id=r["id"], character_id=r["character_id"],
            spell_name=r["spell_name"], spell_level=r["spell_level"] or 0,
            is_prepared=bool(r["is_prepared"]), is_ritual=bool(r["is_ritual"]),
            notes=r["notes"], source=r["source"],
        ) for r in rows]

    # ── Inventory ──────────────────────────────────────────────────────────────

    def add_inventory_item(self, item: InventoryItem) -> int:
        cur = self.db.execute(
            f"INSERT INTO {self.INVENTORY_TABLE} "
            f"(character_id, name, quantity, weight, value_gp, equipped, description, item_type) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item.character_id, item.name, item.quantity, item.weight,
             item.value_gp, 1 if item.equipped else 0, item.description, item.item_type),
        )
        return cur.lastrowid

    def update_inventory_item(self, item: InventoryItem):
        self.db.execute(
            f"UPDATE {self.INVENTORY_TABLE} SET "
            f"name=?, quantity=?, weight=?, value_gp=?, equipped=?, description=?, item_type=? "
            f"WHERE id=?",
            (item.name, item.quantity, item.weight, item.value_gp,
             1 if item.equipped else 0, item.description, item.item_type, item.id),
        )

    def delete_inventory_item(self, item_id: int):
        self.db.execute(f"DELETE FROM {self.INVENTORY_TABLE} WHERE id=?", (item_id,))

    def get_inventory_for_character(self, ch_id: int) -> list[InventoryItem]:
        rows = self.db.query(
            f"SELECT * FROM {self.INVENTORY_TABLE} WHERE character_id=? ORDER BY item_type, name",
            (ch_id,),
        )
        return [InventoryItem(
            id=r["id"], character_id=r["character_id"],
            name=r["name"], quantity=r["quantity"] or 1,
            weight=r["weight"] or 0.0, value_gp=r["value_gp"] or 0.0,
            equipped=bool(r["equipped"]), description=r["description"],
            item_type=r["item_type"],
        ) for r in rows]

    # ── Encounters ────────────────────────────────────────────────────────────

    def add_encounter(self, enc: Encounter) -> int:
        cur = self.db.execute(
            f"INSERT INTO {self.ENCOUNTER_TABLE} (campaign_id, name, description, difficulty) "
            f"VALUES (?, ?, ?, ?)",
            (enc.campaign_id, enc.name, enc.description, enc.difficulty),
        )
        return cur.lastrowid

    def update_encounter(self, enc: Encounter):
        self.db.execute(
            f"UPDATE {self.ENCOUNTER_TABLE} SET name=?, description=?, difficulty=? WHERE id=?",
            (enc.name, enc.description, enc.difficulty, enc.id),
        )

    def delete_encounter(self, enc_id: int):
        self.db.execute(f"DELETE FROM {self.ENCOUNTER_TABLE} WHERE id=?", (enc_id,))
        self.db.execute(f"DELETE FROM {self.ENC_MONSTER_TABLE} WHERE encounter_id=?", (enc_id,))

    def get_encounters_for_campaign(self, campaign_id: int) -> list[Encounter]:
        rows = self.db.query(
            f"SELECT * FROM {self.ENCOUNTER_TABLE} WHERE campaign_id=? ORDER BY name",
            (campaign_id,),
        )
        return [Encounter(id=r["id"], campaign_id=r["campaign_id"],
                          name=r["name"], description=r["description"],
                          difficulty=r["difficulty"]) for r in rows]

    def add_encounter_monster(self, m: EncounterMonster) -> int:
        cur = self.db.execute(
            f"INSERT INTO {self.ENC_MONSTER_TABLE} "
            f"(encounter_id, monster_name, count, hp_override, notes, cr) VALUES (?,?,?,?,?,?)",
            (m.encounter_id, m.monster_name, m.count, m.hp_override, m.notes, m.cr),
        )
        return cur.lastrowid

    def update_encounter_monster(self, m: EncounterMonster):
        self.db.execute(
            f"UPDATE {self.ENC_MONSTER_TABLE} SET "
            f"monster_name=?, count=?, hp_override=?, notes=?, cr=? WHERE id=?",
            (m.monster_name, m.count, m.hp_override, m.notes, m.cr, m.id),
        )

    def delete_encounter_monster(self, monster_id: int):
        self.db.execute(f"DELETE FROM {self.ENC_MONSTER_TABLE} WHERE id=?", (monster_id,))

    def get_monsters_for_encounter(self, enc_id: int) -> list[EncounterMonster]:
        rows = self.db.query(
            f"SELECT * FROM {self.ENC_MONSTER_TABLE} WHERE encounter_id=? ORDER BY monster_name",
            (enc_id,),
        )
        return [EncounterMonster(
            id=r["id"], encounter_id=r["encounter_id"],
            monster_name=r["monster_name"], count=r["count"] or 1,
            hp_override=r["hp_override"], notes=r["notes"], cr=r["cr"],
        ) for r in rows]

    # ── Character images ───────────────────────────────────────────────────────

    def add_character_image(self, img: CharacterImage) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {self.CHAR_IMAGE_TABLE}
                (character_id, image_path, is_primary, zoom, focal_x, focal_y)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (img.character_id, img.image_path, 1 if img.is_primary else 0,
              img.zoom, img.focal_x, img.focal_y))
        return cur.lastrowid

    def get_images_for_character(self, ch_id: int) -> list[dict]:
        rows = self.db.query(
            f"SELECT * FROM {self.CHAR_IMAGE_TABLE} WHERE character_id=? ORDER BY id",
            (ch_id,))
        out = []
        for r in rows:
            d = dict(r)
            d.setdefault("zoom",    1.0)
            d.setdefault("focal_x", 0.5)
            d.setdefault("focal_y", 0.5)
            out.append(d)
        return out

    def update_character_image_crop(self, img_id: int, zoom: float, fx: float, fy: float):
        self.db.execute(
            f"UPDATE {self.CHAR_IMAGE_TABLE} SET zoom=?, focal_x=?, focal_y=? WHERE id=?",
            (zoom, fx, fy, img_id),
        )

    def delete_character_image(self, img_id: int) -> bool:
        cur = self.db.execute(f"DELETE FROM {self.CHAR_IMAGE_TABLE} WHERE id=?", (img_id,))
        return cur.rowcount > 0

    # ── Battles ────────────────────────────────────────────────────────────────

    def add_battle(self, b: Battle) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {self.BATTLE_TABLE}
                (campaign_id, title, session_number, date_played, location_name,
                 scenario_name, scenario_description, outcome, scoring_notes,
                 chronicle_text, primary_image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            b.campaign_id, b.title.strip(), b.session_number, b.date_played,
            b.location_name, b.scenario_name, b.scenario_description,
            b.outcome, b.scoring_notes, b.chronicle_text, b.primary_image_path,
        ))
        return cur.lastrowid

    def get_battle(self, bid: int) -> Optional[Battle]:
        rows = self.db.query(f"SELECT * FROM {self.BATTLE_TABLE} WHERE id=?", (bid,))
        return self._row_to_battle(rows[0]) if rows else None

    def get_battles_for_campaign(self, cid: int) -> list[Battle]:
        rows = self.db.query(
            f"SELECT * FROM {self.BATTLE_TABLE} WHERE campaign_id=? ORDER BY session_number",
            (cid,))
        return [self._row_to_battle(r) for r in rows]

    def update_battle(self, b: Battle) -> bool:
        cur = self.db.execute(f"""
            UPDATE {self.BATTLE_TABLE} SET
                title=?, session_number=?, date_played=?, location_name=?,
                scenario_name=?, scenario_description=?, outcome=?,
                scoring_notes=?, chronicle_text=?, primary_image_path=?
            WHERE id=?
        """, (
            b.title.strip(), b.session_number, b.date_played, b.location_name,
            b.scenario_name, b.scenario_description, b.outcome,
            b.scoring_notes, b.chronicle_text, b.primary_image_path, b.id,
        ))
        return cur.rowcount > 0

    def delete_battle(self, bid: int) -> bool:
        cur = self.db.execute(f"DELETE FROM {self.BATTLE_TABLE} WHERE id=?", (bid,))
        return cur.rowcount > 0

    def _row_to_battle(self, row) -> Battle:
        return Battle(
            id=row["id"], campaign_id=row["campaign_id"], title=row["title"],
            session_number=row["session_number"] or 1, date_played=row["date_played"],
            location_name=row["location_name"], scenario_name=row["scenario_name"],
            scenario_description=row["scenario_description"], outcome=row["outcome"],
            scoring_notes=row["scoring_notes"], chronicle_text=row["chronicle_text"],
            primary_image_path=row["primary_image_path"],
        )

    # ── Participants ───────────────────────────────────────────────────────────

    def add_participant(self, p: BattleParticipant) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {self.PARTICIPANT_TABLE}
                (battle_id, player_id, side, army_id, score, result, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (p.battle_id, p.player_id, p.side, p.army_id, p.score, p.result, p.notes))
        return cur.lastrowid

    def get_participants_for_battle(self, bid: int) -> list[BattleParticipant]:
        rows = self.db.query(
            f"SELECT * FROM {self.PARTICIPANT_TABLE} WHERE battle_id=?", (bid,))
        return [BattleParticipant(
            id=r["id"], battle_id=r["battle_id"], player_id=r["player_id"],
            side=r["side"] or "", army_id=r["army_id"],
            score=r["score"] or 0, result=r["result"] or "", notes=r["notes"],
        ) for r in rows]

    def delete_participants_for_battle(self, bid: int):
        self.db.execute(f"DELETE FROM {self.PARTICIPANT_TABLE} WHERE battle_id=?", (bid,))

    # ── Battle images ──────────────────────────────────────────────────────────

    def add_battle_image(self, img: BattleImage) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {self.BATTLE_IMAGE_TABLE}
                (battle_id, image_path, is_primary, zoom, focal_x, focal_y)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (img.battle_id, img.image_path, 1 if img.is_primary else 0,
              img.zoom, img.focal_x, img.focal_y))
        return cur.lastrowid

    def get_images_for_battle(self, bid: int) -> list[dict]:
        rows = self.db.query(
            f"SELECT * FROM {self.BATTLE_IMAGE_TABLE} WHERE battle_id=? ORDER BY id",
            (bid,))
        out = []
        for r in rows:
            d = dict(r)
            d.setdefault("zoom",    1.0)
            d.setdefault("focal_x", 0.5)
            d.setdefault("focal_y", 0.5)
            out.append(d)
        return out

    def update_battle_image_crop(self, img_id: int, zoom: float, fx: float, fy: float):
        self.db.execute(
            f"UPDATE {self.BATTLE_IMAGE_TABLE} SET zoom=?, focal_x=?, focal_y=? WHERE id=?",
            (zoom, fx, fy, img_id),
        )

    def delete_battle_image(self, img_id: int) -> bool:
        cur = self.db.execute(f"DELETE FROM {self.BATTLE_IMAGE_TABLE} WHERE id=?", (img_id,))
        return cur.rowcount > 0

    # ── Journal ────────────────────────────────────────────────────────────────

    def add_journal_entry(self, j: JournalEntry) -> int:
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        cur = self.db.execute(f"""
            INSERT INTO {self.JOURNAL_TABLE}
                (campaign_id, title, content, battle_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (j.campaign_id, j.title.strip(), j.content, j.battle_id, now, now))
        return cur.lastrowid

    def get_journal_entry(self, jid: int) -> Optional[JournalEntry]:
        rows = self.db.query(f"SELECT * FROM {self.JOURNAL_TABLE} WHERE id=?", (jid,))
        return self._row_to_journal(rows[0]) if rows else None

    def get_journal_entries_for_campaign(self, cid: int) -> list[JournalEntry]:
        rows = self.db.query(
            f"SELECT * FROM {self.JOURNAL_TABLE} WHERE campaign_id=? ORDER BY created_at DESC",
            (cid,))
        return [self._row_to_journal(r) for r in rows]

    def update_journal_entry(self, j: JournalEntry) -> bool:
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        cur = self.db.execute(f"""
            UPDATE {self.JOURNAL_TABLE}
            SET title=?, content=?, battle_id=?, updated_at=? WHERE id=?
        """, (j.title.strip(), j.content, j.battle_id, now, j.id))
        return cur.rowcount > 0

    def delete_journal_entry(self, jid: int) -> bool:
        cur = self.db.execute(f"DELETE FROM {self.JOURNAL_TABLE} WHERE id=?", (jid,))
        return cur.rowcount > 0

    def _row_to_journal(self, row) -> JournalEntry:
        return JournalEntry(
            id=row["id"], campaign_id=row["campaign_id"], title=row["title"],
            content=row["content"] or "", battle_id=row["battle_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    # ── Assets ─────────────────────────────────────────────────────────────────

    def add_asset(self, a: CampaignAsset) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {self.ASSET_TABLE}
                (campaign_id, name, file_path, asset_type, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (a.campaign_id, a.name, a.file_path, a.asset_type, a.notes))
        return cur.lastrowid

    def get_assets_for_campaign(self, cid: int) -> list[CampaignAsset]:
        rows = self.db.query(
            f"SELECT * FROM {self.ASSET_TABLE} WHERE campaign_id=? ORDER BY asset_type, name",
            (cid,))
        return [CampaignAsset(
            id=r["id"], campaign_id=r["campaign_id"], name=r["name"],
            file_path=r["file_path"], asset_type=r["asset_type"], notes=r["notes"],
        ) for r in rows]

    def delete_asset(self, aid: int) -> bool:
        cur = self.db.execute(f"DELETE FROM {self.ASSET_TABLE} WHERE id=?", (aid,))
        return cur.rowcount > 0

    # ── Dice log ───────────────────────────────────────────────────────────────

    def add_dice_roll(self, roll: DiceRoll) -> int:
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        cur = self.db.execute(f"""
            INSERT INTO {self.DICE_LOG_TABLE} (expression, result, detail, timestamp)
            VALUES (?, ?, ?, ?)
        """, (roll.expression, roll.result, roll.detail, now))
        return cur.lastrowid

    def get_dice_log(self, limit: int = 100) -> list[DiceRoll]:
        rows = self.db.query(
            f"SELECT * FROM {self.DICE_LOG_TABLE} ORDER BY id DESC LIMIT ?", (limit,))
        return [DiceRoll(
            id=r["id"], expression=r["expression"], result=r["result"],
            detail=r["detail"], timestamp=r["timestamp"],
        ) for r in rows]

    def clear_dice_log(self):
        self.db.execute(f"DELETE FROM {self.DICE_LOG_TABLE}")

    # ── Saved Expressions ─────────────────────────────────────────────────────

    def add_saved_expression(self, expr: SavedExpression) -> int:
        cur = self.db.execute(
            f"INSERT INTO {self.SAVED_EXPR_TABLE} (name, expression) VALUES (?, ?)",
            (expr.name, expr.expression),
        )
        return cur.lastrowid

    def update_saved_expression(self, expr: SavedExpression):
        self.db.execute(
            f"UPDATE {self.SAVED_EXPR_TABLE} SET name=?, expression=? WHERE id=?",
            (expr.name, expr.expression, expr.id),
        )

    def delete_saved_expression(self, expr_id: int):
        self.db.execute(
            f"DELETE FROM {self.SAVED_EXPR_TABLE} WHERE id=?", (expr_id,)
        )

    def get_saved_expressions(self) -> list[SavedExpression]:
        rows = self.db.query(f"SELECT * FROM {self.SAVED_EXPR_TABLE} ORDER BY name")
        return [SavedExpression(name=r["name"], expression=r["expression"], id=r["id"])
                for r in rows]

    # ── Campaign images ────────────────────────────────────────────────────────

    def add_campaign_image(self, img: CampaignImage) -> int:
        cur = self.db.execute(f"""
            INSERT INTO {self.CAMPAIGN_IMAGE_TABLE}
                (campaign_id, image_path, caption, is_primary, zoom, focal_x, focal_y)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (img.campaign_id, img.image_path, img.caption,
              1 if img.is_primary else 0, img.zoom, img.focal_x, img.focal_y))
        return cur.lastrowid

    def get_images_for_campaign(self, cid: int) -> list[dict]:
        rows = self.db.query(
            f"SELECT * FROM {self.CAMPAIGN_IMAGE_TABLE} WHERE campaign_id=? ORDER BY id",
            (cid,))
        out = []
        for r in rows:
            d = dict(r)
            d.setdefault("zoom",    1.0)
            d.setdefault("focal_x", 0.5)
            d.setdefault("focal_y", 0.5)
            d.setdefault("caption", "")
            out.append(d)
        return out

    def update_campaign_image_crop(self, img_id: int, zoom: float, fx: float, fy: float):
        self.db.execute(
            f"UPDATE {self.CAMPAIGN_IMAGE_TABLE} SET zoom=?, focal_x=?, focal_y=? WHERE id=?",
            (zoom, fx, fy, img_id),
        )

    def update_campaign_image_caption(self, img_id: int, caption: str):
        self.db.execute(
            f"UPDATE {self.CAMPAIGN_IMAGE_TABLE} SET caption=? WHERE id=?",
            (caption, img_id),
        )

    def delete_campaign_image(self, img_id: int) -> bool:
        cur = self.db.execute(
            f"DELETE FROM {self.CAMPAIGN_IMAGE_TABLE} WHERE id=?", (img_id,))
        return cur.rowcount > 0

    # ── Statistics ─────────────────────────────────────────────────────────────

    def get_statistics(self) -> CampaignStatistics:
        campaigns = self.get_all_campaigns()
        total  = len(campaigns)
        active = sum(1 for c in campaigns if c.status == "Active")
        gs_dist: dict[str, int] = {}
        for c in campaigns:
            gs_dist[c.game_system] = gs_dist.get(c.game_system, 0) + 1

        battles   = self.db.query(f"SELECT outcome FROM {self.BATTLE_TABLE}")
        victories = sum(1 for b in battles if b["outcome"] == "Victory")
        defeats   = sum(1 for b in battles if b["outcome"] == "Defeat")
        draws     = sum(1 for b in battles if b["outcome"] == "Draw")

        char_rows   = self.db.query(f"SELECT COUNT(*) AS cnt FROM {self.CHARACTER_TABLE}")
        player_rows = self.db.query(f"SELECT COUNT(*) AS cnt FROM {self.PLAYER_TABLE}")

        return CampaignStatistics(
            total_campaigns=total,
            active_campaigns=active,
            total_battles=len(battles),
            total_characters=char_rows[0]["cnt"] if char_rows else 0,
            total_players=player_rows[0]["cnt"] if player_rows else 0,
            victories=victories,
            defeats=defeats,
            draws=draws,
            game_system_distribution=gs_dist,
        )
