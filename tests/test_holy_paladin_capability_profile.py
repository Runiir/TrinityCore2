from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_21_00_holy_paladin_capability_profile.sql"
CANDIDATE_SOURCE = ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp"


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY,
            class_id INTEGER NOT NULL,
            spec_tag TEXT NOT NULL,
            role TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            spell_id INTEGER NOT NULL DEFAULT 0,
            category TEXT NOT NULL,
            mechanic_tags TEXT NOT NULL DEFAULT '',
            damage_weight REAL NOT NULL DEFAULT 0,
            healing_weight REAL NOT NULL DEFAULT 0,
            survival_weight REAL NOT NULL DEFAULT 0,
            priority_bucket INTEGER NOT NULL DEFAULT 5,
            min_enemies INTEGER NOT NULL DEFAULT 1,
            max_target_health_pct REAL NOT NULL DEFAULT 1,
            target_selector TEXT NOT NULL DEFAULT 'enemy',
            movement_directive TEXT NOT NULL DEFAULT '',
            auto_attack_mode TEXT NOT NULL DEFAULT '',
            max_range REAL NOT NULL DEFAULT 0,
            maintain_aura_id INTEGER NOT NULL DEFAULT 0,
            min_injured_players INTEGER NOT NULL DEFAULT 0,
            injured_health_pct REAL NOT NULL DEFAULT 1
        );
        """
    )
    db.execute(
        "INSERT INTO bot_rotation_profile(id, class_id, spec_tag, role) VALUES (1, 2, 'holy_paladin', 'healer')"
    )
    db.execute(
        "INSERT INTO bot_rotation_profile(id, class_id, spec_tag, role) VALUES (2, 2, 'protection', 'tank')"
    )
    db.executemany(
        """
        INSERT INTO bot_rotation_action(
            profile_id, sort_order, spell_id, category, mechanic_tags,
            healing_weight, survival_weight, priority_bucket, min_enemies,
            max_target_health_pct, target_selector, movement_directive,
            auto_attack_mode, max_range, maintain_aura_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 10, 20217, "buff", "blessing_of_kings,party,prepull_required", 0.20, 0.50, 0, 1, 1.0, "party", "healer_support", "none", 40, 20217),
            (1, 20, 19750, "heal_fast", "flash_of_light,triage,heal", 0.94, 0.75, 1, 1, 0.82, "lowest_ally", "healer_support", "none", 40, 0),
            (1, 30, 635, "heal_efficient", "holy_light,heal", 0.82, 0.65, 2, 1, 0.94, "lowest_ally", "healer_support", "none", 40, 0),
        ],
    )
    return db


def _run_migration(db: sqlite3.Connection) -> None:
    db.executescript(MIGRATION.read_text(encoding="utf-8"))


def test_word_of_glory_is_added_once_with_existing_healer_gates() -> None:
    db = _database()
    try:
        _run_migration(db)
        _run_migration(db)

        rows = db.execute(
            "SELECT * FROM bot_rotation_action WHERE profile_id = 1 ORDER BY sort_order"
        ).fetchall()
        assert [row["spell_id"] for row in rows] == [20217, 85673, 19750, 635]
        word_of_glory = rows[1]
        assert word_of_glory["category"] == "heal_fast"
        assert word_of_glory["mechanic_tags"] == "word_of_glory,holy_power_3,triage,heal"
        assert word_of_glory["healing_weight"] == 1.0
        assert word_of_glory["survival_weight"] == 0.9
        assert word_of_glory["priority_bucket"] == 1
        assert word_of_glory["max_target_health_pct"] == 0.94
        assert word_of_glory["target_selector"] == "lowest_ally"
        assert word_of_glory["movement_directive"] == "healer_support"
        assert word_of_glory["min_injured_players"] == 1
        assert word_of_glory["injured_health_pct"] == 0.94
    finally:
        db.close()


def test_migration_does_not_touch_other_profiles_or_baseline_rows() -> None:
    db = _database()
    try:
        db.execute(
            "INSERT INTO bot_rotation_action(profile_id, spell_id, category) VALUES (2, 999, 'builder')"
        )
        before = db.execute(
            "SELECT profile_id, sort_order, spell_id, category, mechanic_tags FROM bot_rotation_action ORDER BY id"
        ).fetchall()
        _run_migration(db)

        after = db.execute(
            "SELECT profile_id, sort_order, spell_id, category, mechanic_tags FROM bot_rotation_action ORDER BY id"
        ).fetchall()
        assert [tuple(row) for row in after if row[0] != 1] == [tuple(row) for row in before if row[0] != 1]
        assert [tuple(row) for row in after if row[0] == 1][:3] == [tuple(row) for row in before if row[0] == 1]
    finally:
        db.close()


def test_native_candidate_builder_owns_the_holy_power_gate() -> None:
    source = CANDIDATE_SOURCE.read_text(encoding="utf-8")
    assert 'HasMechanicTag(spell.MechanicTags, "holy_power_3")' in source
    assert 'return "insufficient_holy_power";' in source
