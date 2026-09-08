from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_08_00_marksmanship_native_range.sql"

MAIN_SHOT_SPELLS = (75, 1978, 53209, 19434, 2643, 3044, 56641)
KILL_SHOT = 53351


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
            (1, 3, "marksmanship", "dps", 5, 35, 1, 17, "ranged"),
            (2, 3, "survival", "dps", 5, 35, 1, 11, "ranged"),
            (3, 8, "fire", "dps", 0, 35, 1, 9, "ranged"),
            (4, 3, "marksmanship", "tank", 5, 35, 1, 4, "ranged"),
        ],
    )

    actions = []
    action_id = 1
    sort_order = 10
    for spell_id in MAIN_SHOT_SPELLS + (KILL_SHOT,):
        actions.append(
            (action_id, 1, sort_order, spell_id, "damage", 0.80, 2,
             "enemy", 5, 35, 1)
        )
        action_id += 1
        sort_order += 10

    # Duplicate Aimed Shot and Steady Shot rows model the current profile's
    # split gates.  The second row is disabled, but remains a matching action
    # and therefore must receive the same range correction.
    for spell_id in (19434, 56641):
        actions.append(
            (action_id, 1, sort_order, spell_id, "damage", 0.70, 5,
             "enemy", 5, 35, 0)
        )
        action_id += 1
        sort_order += 1

    # Self-target and utility rows are outside the native damaging spell set.
    actions.extend(
        [
            (action_id, 1, 1, 883, "buff", 0.20, 0, "self", 5, 35, 1),
            (action_id + 1, 1, 5, 1130, "debuff", 0.35, 0, "enemy", 5, 35, 1),
            (action_id + 2, 2, 10, 1978, "damage", 0.88, 1, "enemy", 5, 35, 1),
            (action_id + 3, 3, 10, 1978, "damage", 0.78, 1, "enemy", 5, 35, 1),
            (action_id + 4, 4, 10, 1978, "damage", 0.78, 1, "enemy", 5, 35, 1),
        ]
    )
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
    native_max_range: float,
) -> bool:
    profile_max, action_max = db.execute(
        """
        SELECT profile.max_range, action.max_range
        FROM bot_rotation_profile AS profile
        JOIN bot_rotation_action AS action ON action.profile_id = profile.id
        WHERE profile.id = ? AND action.spell_id = ?
        ORDER BY action.id
        LIMIT 1
        """,
        (profile_id, spell_id),
    ).fetchone()
    configured_max = action_max if action_max > 0 else profile_max
    return distance <= min(configured_max, native_max_range)


def test_migration_updates_only_enabled_marksmanship_native_damage_ranges() -> None:
    db = _connection()
    try:
        migration = MIGRATION.read_text(encoding="utf-8")
        before_actions = _action_rows(db)

        # The nominal bait radius is 38.42 yd. This tests configuration
        # eligibility, not the unrecorded live actor-to-head distance.
        assert not _admitted(db, 1, 75, 38.42, 40)

        db.executescript(migration)

        assert _profile(db, 1) == (5.0, 40.0, 1, 17, "ranged")
        for spell_id in MAIN_SHOT_SPELLS:
            rows = db.execute(
                """
                SELECT max_range FROM bot_rotation_action
                WHERE profile_id = 1 AND spell_id = ?
                ORDER BY id
                """,
                (spell_id,),
            ).fetchall()
            assert rows and all((row[0] == 40.0) for row in rows)
        assert db.execute(
            """
            SELECT DISTINCT max_range FROM bot_rotation_action
            WHERE profile_id = 1 AND spell_id = ?
            """,
            (KILL_SHOT,),
        ).fetchall() == [(45.0,)]

        # The same fixture distance is now inside the configured/native
        # intersection. Spell execution remains authoritative in the live run.
        assert _admitted(db, 1, 75, 38.42, 40)
        assert db.execute(
            "SELECT max_range FROM bot_rotation_profile WHERE id = 1"
        ).fetchone()[0] <= 40
        assert _admitted(db, 1, KILL_SHOT, 44.0, 45)

        # Scope guards preserve other specs/roles and self/utility actions.
        assert _profile(db, 2) == (5.0, 35.0, 1, 11, "ranged")
        assert _profile(db, 3) == (0.0, 35.0, 1, 9, "ranged")
        assert _profile(db, 4) == (5.0, 35.0, 1, 4, "ranged")
        assert db.execute(
            "SELECT max_range FROM bot_rotation_action WHERE profile_id = 1 AND spell_id IN (883, 1130) ORDER BY spell_id"
        ).fetchall() == [(35.0,), (35.0,)]
        assert db.execute(
            "SELECT max_range FROM bot_rotation_action WHERE profile_id IN (2, 3, 4)"
        ).fetchall() == [(35.0,), (35.0,), (35.0,)]

        # The migration only changes max_range on the scoped rows.
        after_actions = _action_rows(db)
        changed_ids = {
            row[0] for row in before_actions if row[9] != next(
                current[9] for current in after_actions if current[0] == row[0]
            )
        }
        expected_ids = {
            row[0] for row in before_actions
            if row[1] == 1 and row[3] in MAIN_SHOT_SPELLS + (KILL_SHOT,)
        }
        assert changed_ids == expected_ids
        for before, after in zip(before_actions, after_actions):
            if before[0] in expected_ids:
                assert before[9] == 35.0 and after[9] in (40.0, 45.0)
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

        # Both duplicate rows, including the disabled one, were updated.
        assert db.execute(
            """
            SELECT spell_id, enabled, max_range
            FROM bot_rotation_action
            WHERE profile_id = 1 AND spell_id IN (19434, 56641)
            ORDER BY id
            """
        ).fetchall() == [
            (19434, 1, 40.0),
            (56641, 1, 40.0),
            (19434, 0, 40.0),
            (56641, 0, 40.0),
        ]
    finally:
        db.close()
