from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_08_01_fire_native_range.sql"

FIREBALL = 133
LIVING_BOMB = 44457
FIRE_BLAST = 2136
FIRE_DAMAGE_SPELLS = (LIVING_BOMB, FIREBALL)
NATIVE_MAX_RANGE = {
    FIREBALL: 40.0,
    LIVING_BOMB: 40.0,
    FIRE_BLAST: 30.0,
    2139: 40.0,  # Counterspell
    92315: 40.0,  # Pyroblast!
    2120: 40.0,  # Flamestrike
}


def _connection() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY,
            class_id INTEGER NOT NULL,
            spec_tag TEXT NOT NULL,
            role TEXT NOT NULL,
            min_range REAL NOT NULL,
            max_range REAL NOT NULL,
            enabled INTEGER NOT NULL,
            version INTEGER NOT NULL,
            movement_directive TEXT NOT NULL
        );
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL,
            spell_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            damage_weight REAL NOT NULL,
            priority_bucket INTEGER NOT NULL,
            target_selector TEXT NOT NULL,
            min_range REAL NOT NULL,
            max_range REAL NOT NULL,
            enabled INTEGER NOT NULL
        );
        """
    )
    db.executemany(
        """
        INSERT INTO bot_rotation_profile
            (id, class_id, spec_tag, role, min_range, max_range, enabled,
             version, movement_directive)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 8, "fire", "dps", 0, 35, 1, 9, "ranged"),
            (2, 8, "fire", "dps", 0, 35, 0, 9, "ranged"),
            (3, 3, "marksmanship", "dps", 5, 35, 1, 17, "ranged"),
            (4, 8, "fire", "tank", 0, 35, 1, 4, "ranged"),
        ],
    )

    actions = [
        # The enabled rows mirror the production Fire profile.  The separate
        # Fire Blast row models the single-target fallback from the prior APL
        # alignment migration, and the disabled duplicates model split gates.
        (1, 1, 10, 2139, "interrupt", 0.15, 1, "enemy", 0, 35, 1),
        (2, 1, 20, LIVING_BOMB, "dot", 0.98, 1, "enemy", 0, 35, 1),
        (3, 1, 30, 92315, "spender", 1.00, 1, "enemy", 0, 35, 1),
        (4, 1, 40, 2120, "aoe", 0.90, 3, "enemy", 0, 35, 1),
        (5, 1, 50, FIREBALL, "builder", 0.78, 4, "enemy", 0, 35, 1),
        (6, 1, 60, FIRE_BLAST, "spender", 0.70, 5, "enemy", 0, 35, 1),
        (7, 1, 61, FIRE_BLAST, "spender", 0.70, 6, "enemy", 0, 35, 1),
        (8, 1, 62, LIVING_BOMB, "dot", 0.50, 7, "enemy", 0, 35, 0),
        (9, 1, 63, FIREBALL, "builder", 0.50, 8, "enemy", 0, 35, 0),
        # Same spell IDs in disabled/other profiles must remain untouched.
        (10, 2, 50, FIREBALL, "builder", 0.78, 4, "enemy", 0, 35, 1),
        (11, 3, 50, FIREBALL, "builder", 0.78, 4, "enemy", 5, 35, 1),
        (12, 4, 50, FIREBALL, "builder", 0.78, 4, "enemy", 0, 35, 1),
    ]
    db.executemany(
        """
        INSERT INTO bot_rotation_action
            (id, profile_id, sort_order, spell_id, category, damage_weight,
             priority_bucket, target_selector, min_range, max_range, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        actions,
    )
    return db


def _profile(db: sqlite3.Connection, profile_id: int) -> tuple:
    return db.execute(
        """
        SELECT min_range, max_range, enabled, version, movement_directive
        FROM bot_rotation_profile
        WHERE id = ?
        """,
        (profile_id,),
    ).fetchone()


def _action_rows(db: sqlite3.Connection) -> list[tuple]:
    return db.execute(
        """
        SELECT id, profile_id, sort_order, spell_id, category, damage_weight,
               priority_bucket, target_selector, min_range, max_range, enabled
        FROM bot_rotation_action
        ORDER BY id
        """
    ).fetchall()


def _admitted(
    db: sqlite3.Connection,
    profile_id: int,
    spell_id: int,
    distance: float,
) -> bool:
    row = db.execute(
        """
        SELECT profile.max_range, action.max_range
        FROM bot_rotation_profile AS profile
        JOIN bot_rotation_action AS action ON action.profile_id = profile.id
        WHERE profile.id = ? AND action.spell_id = ? AND action.enabled = 1
        ORDER BY action.id
        LIMIT 1
        """,
        (profile_id, spell_id),
    ).fetchone()
    if row is None:
        return False
    profile_max, action_max = row
    configured_max = action_max if action_max > 0 else profile_max
    return distance <= min(configured_max, NATIVE_MAX_RANGE[spell_id])


def test_migration_updates_only_enabled_fire_native_damage_ranges() -> None:
    db = _connection()
    try:
        migration = MIGRATION.read_text(encoding="utf-8")
        before_actions = _action_rows(db)

        # The fixed bait is 37 yd from the exposed head.  Before the
        # migration, every Fire damage row is capped at the stale 35 yd.
        assert not _admitted(db, 1, FIREBALL, 37.0)
        assert not _admitted(db, 1, LIVING_BOMB, 37.0)
        assert not _admitted(db, 1, FIRE_BLAST, 31.0)

        db.executescript(migration)

        assert _profile(db, 1) == (0.0, 40.0, 1, 9, "ranged")
        assert _profile(db, 2) == (0.0, 35.0, 0, 9, "ranged")
        assert _profile(db, 3) == (5.0, 35.0, 1, 17, "ranged")
        assert _profile(db, 4) == (0.0, 35.0, 1, 4, "ranged")

        assert {
            spell_id
            for spell_id in (FIREBALL, LIVING_BOMB, FIRE_BLAST, 2139, 92315, 2120)
            if _admitted(db, 1, spell_id, 37.0)
        } == {FIREBALL, LIVING_BOMB}
        assert _admitted(db, 1, FIREBALL, 40.0)
        assert _admitted(db, 1, LIVING_BOMB, 40.0)
        assert not _admitted(db, 1, FIREBALL, 40.01)
        assert not _admitted(db, 1, LIVING_BOMB, 40.01)
        assert _admitted(db, 1, FIRE_BLAST, 30.0)
        assert not _admitted(db, 1, FIRE_BLAST, 30.01)
        assert not _admitted(db, 1, FIRE_BLAST, 37.0)

        # Only Fireball/Living Bomb action rows in the enabled Fire profile
        # changed; duplicate and disabled matching rows are included. Fire
        # Blast remains at its existing 35 yd policy cap, while native range
        # still rejects it beyond 30 yd.
        after_actions = _action_rows(db)
        changed_ids = {
            row[0]
            for row in before_actions
            if row[9]
            != next(current[9] for current in after_actions if current[0] == row[0])
        }
        expected_ids = {
            row[0]
            for row in before_actions
            if row[1] == 1 and row[3] in FIRE_DAMAGE_SPELLS
        }
        assert changed_ids == expected_ids
        for before, after in zip(before_actions, after_actions):
            if before[0] in expected_ids:
                assert before[9] == 35.0 and after[9] == 40.0
                assert before[:9] + before[10:] == after[:9] + after[10:]
            else:
                assert before == after
    finally:
        db.close()


def test_migration_is_idempotent_with_duplicate_and_disabled_actions() -> None:
    db = _connection()
    try:
        migration = MIGRATION.read_text(encoding="utf-8")
        db.executescript(migration)
        once = (_profile(db, 1), tuple(_action_rows(db)))
        db.executescript(migration)
        twice = (_profile(db, 1), tuple(_action_rows(db)))
        assert twice == once

        assert db.execute(
            """
            SELECT spell_id, enabled, max_range
            FROM bot_rotation_action
            WHERE profile_id = 1 AND spell_id IN (133, 2136, 44457)
            ORDER BY id
            """
        ).fetchall() == [
            (44457, 1, 40.0),
            (133, 1, 40.0),
            (2136, 1, 35.0),
            (2136, 1, 35.0),
            (44457, 0, 40.0),
            (133, 0, 40.0),
        ]
    finally:
        db.close()
