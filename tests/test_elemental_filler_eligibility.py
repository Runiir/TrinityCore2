from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_08_02_elemental_filler_eligibility.sql"

ELEMENTAL_PROFILE = 273403
DISABLED_ELEMENTAL_PROFILE = 273404
LIGHTNING_BOLT = 403
CHAIN_LIGHTNING = 421

PROFILE_COLUMNS = (
    "id",
    "class_id",
    "spec_tag",
    "role",
    "min_range",
    "max_range",
    "enabled",
    "version",
    "movement_directive",
)
ACTION_COLUMNS = (
    "id",
    "profile_id",
    "sort_order",
    "spell_id",
    "category",
    "mechanic_tags",
    "damage_weight",
    "priority_bucket",
    "min_enemies",
    "max_enemies",
    "target_selector",
    "min_range",
    "max_range",
    "required_self_aura",
    "forbidden_target_aura",
    "enabled",
)


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
            mechanic_tags TEXT NOT NULL,
            damage_weight REAL NOT NULL,
            priority_bucket INTEGER NOT NULL,
            min_enemies INTEGER NOT NULL,
            max_enemies INTEGER NOT NULL,
            target_selector TEXT NOT NULL,
            min_range REAL NOT NULL,
            max_range REAL NOT NULL,
            required_self_aura INTEGER NOT NULL,
            forbidden_target_aura INTEGER NOT NULL,
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
            # Corrected-gear trace profile 273403.
            (ELEMENTAL_PROFILE, 7, "elemental_shaman", "dps", 12, 35, 1, 4, "ranged"),
            # Disabled profile must not be made active by a scoped repair.
            (DISABLED_ELEMENTAL_PROFILE, 7, "elemental_shaman", "dps", 12, 35, 0, 4, "ranged"),
            # Each selector dimension is represented by an unrelated profile.
            (273405, 3, "elemental_shaman", "dps", 5, 35, 1, 8, "ranged"),
            (273406, 7, "enhancement", "dps", 0, 5, 1, 8, "melee"),
            (273407, 7, "elemental_shaman", "healer", 12, 35, 1, 8, "ranged"),
        ],
    )

    db.executemany(
        """
        INSERT INTO bot_rotation_action
            (id, profile_id, sort_order, spell_id, category, mechanic_tags,
             damage_weight, priority_bucket, min_enemies, max_enemies,
             target_selector, min_range, max_range, required_self_aura,
             forbidden_target_aura, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            # The historical migration leaves this enabled filler capped at 1.
            (1, ELEMENTAL_PROFILE, 40, LIGHTNING_BOLT, "builder", "lightning_bolt,filler", 0.82, 3, 1, 1, "enemy", 12, 35, 0, 0, 1),
            # Chain Lightning remains a >=3 enemy area action at priority 2.
            (2, ELEMENTAL_PROFILE, 30, CHAIN_LIGHTNING, "cleave", "chain_lightning,aoe", 0.88, 2, 3, 0, "enemy", 12, 35, 0, 0, 1),
            (3, ELEMENTAL_PROFILE, 20, 8050, "dot", "flame_shock,maintain_debuff", 0.90, 1, 1, 0, "enemy", 12, 35, 0, 8050, 1),
            (4, ELEMENTAL_PROFILE, 50, 8042, "spender", "earth_shock", 0.86, 4, 1, 0, "enemy", 12, 35, 0, 0, 1),
            # Disabled action rows are part of the representative profile data.
            (5, ELEMENTAL_PROFILE, 41, LIGHTNING_BOLT, "builder", "lightning_bolt,filler", 0.70, 3, 1, 1, "enemy", 12, 35, 0, 0, 0),
            (6, ELEMENTAL_PROFILE, 31, CHAIN_LIGHTNING, "cleave", "chain_lightning,aoe", 0.70, 2, 3, 0, "enemy", 12, 35, 0, 0, 0),
            # An enabled action under a disabled profile must remain capped.
            (7, DISABLED_ELEMENTAL_PROFILE, 40, LIGHTNING_BOLT, "builder", "lightning_bolt,filler", 0.82, 3, 1, 1, "enemy", 12, 35, 0, 0, 1),
            # Other class, spec, and role rows must remain untouched.
            (8, 273405, 40, LIGHTNING_BOLT, "builder", "lightning_bolt,filler", 0.82, 3, 1, 1, "enemy", 5, 35, 0, 0, 1),
            (9, 273406, 40, LIGHTNING_BOLT, "builder", "lightning_bolt,filler", 0.82, 3, 1, 1, "enemy", 0, 5, 0, 0, 1),
            (10, 273407, 40, LIGHTNING_BOLT, "builder", "lightning_bolt,filler", 0.82, 3, 1, 1, "enemy", 12, 35, 0, 0, 1),
        ],
    )
    return db


def _profiles(db: sqlite3.Connection) -> list[tuple]:
    return db.execute(
        f"SELECT {', '.join(PROFILE_COLUMNS)} FROM bot_rotation_profile ORDER BY id"
    ).fetchall()


def _actions(db: sqlite3.Connection) -> list[tuple]:
    return db.execute(
        f"SELECT {', '.join(ACTION_COLUMNS)} FROM bot_rotation_action ORDER BY id"
    ).fetchall()


def _action(db: sqlite3.Connection, action_id: int) -> tuple:
    return db.execute(
        f"SELECT {', '.join(ACTION_COLUMNS)} FROM bot_rotation_action WHERE id = ?",
        (action_id,),
    ).fetchone()


def _configured_enemy_rows(
    db: sqlite3.Connection, enemy_count: int
) -> list[tuple[int, int]]:
    """Return stored enemy-count metadata matches, without native selection."""

    return db.execute(
        """
        SELECT spell_id, priority_bucket
        FROM bot_rotation_action
        WHERE profile_id = ?
          AND enabled = 1
          AND min_enemies <= ?
          AND (max_enemies = 0 OR max_enemies >= ?)
          AND spell_id IN (?, ?)
        ORDER BY priority_bucket, sort_order, id
        """,
        (ELEMENTAL_PROFILE, enemy_count, enemy_count, LIGHTNING_BOLT, CHAIN_LIGHTNING),
    ).fetchall()


def test_migration_repairs_only_enabled_elemental_lightning_bolt_metadata() -> None:
    db = _connection()
    try:
        before_profiles = _profiles(db)
        before_actions = _actions(db)
        before_by_id = {row[0]: row for row in before_actions}

        # This is the adjacent two-enemy data-contract gap: the old upper bound
        # excludes both the capped filler and the >=3-target Chain action.
        assert _configured_enemy_rows(db, 2) == []

        db.executescript(MIGRATION.read_text(encoding="utf-8"))

        after_profiles = _profiles(db)
        after_actions = _actions(db)
        after_by_id = {row[0]: row for row in after_actions}

        assert after_profiles == before_profiles
        changed_ids = {
            action_id
            for action_id, before in before_by_id.items()
            if before != after_by_id[action_id]
        }
        assert changed_ids == {1}

        before_lb = before_by_id[1]
        after_lb = after_by_id[1]
        max_enemies_index = ACTION_COLUMNS.index("max_enemies")
        assert before_lb[max_enemies_index] == 1
        assert after_lb[max_enemies_index] == 0
        for index, (before, after) in enumerate(zip(before_lb, after_lb)):
            if index != max_enemies_index:
                assert after == before

        # The repaired row now has an unbounded stored upper limit, so the
        # two-enemy fallback is represented in profile data. This query does
        # not emulate native C++ eligibility or spell landing.
        assert _configured_enemy_rows(db, 2) == [(LIGHTNING_BOLT, 3)]
    finally:
        db.close()


def test_migration_preserves_chain_order_area_tags_ranges_and_scope() -> None:
    db = _connection()
    try:
        db.executescript(MIGRATION.read_text(encoding="utf-8"))

        # At three enemies both stored gates remain open; Chain Lightning keeps
        # its lower priority bucket and therefore remains the preferred row.
        assert _configured_enemy_rows(db, 3) == [
            (CHAIN_LIGHTNING, 2),
            (LIGHTNING_BOLT, 3),
        ]

        chain = _action(db, 2)
        lb = _action(db, 1)
        columns = {name: index for index, name in enumerate(ACTION_COLUMNS)}
        assert chain[columns["category"]] == "cleave"
        assert chain[columns["min_enemies"]] == 3
        assert chain[columns["priority_bucket"]] == 2
        assert "aoe" in chain[columns["mechanic_tags"]].split(",")
        assert lb[columns["category"]] == "builder"
        assert lb[columns["min_enemies"]] == 1
        assert lb[columns["priority_bucket"]] == 3
        assert "aoe" not in lb[columns["mechanic_tags"]].split(",")

        # Range and target metadata survive; native range and area-forbidden
        # decisions still require the production consumer/live acceptance.
        for row in (chain, lb):
            assert row[columns["target_selector"]] == "enemy"
            assert row[columns["min_range"]] == 12.0
            assert row[columns["max_range"]] == 35.0

        assert _action(db, 5)[columns["max_enemies"]] == 1
        assert _action(db, 6)[columns["max_enemies"]] == 0
        assert _action(db, 7)[columns["max_enemies"]] == 1
        assert _action(db, 8)[columns["max_enemies"]] == 1
        assert _action(db, 9)[columns["max_enemies"]] == 1
        assert _action(db, 10)[columns["max_enemies"]] == 1
    finally:
        db.close()


def test_migration_is_idempotent() -> None:
    db = _connection()
    try:
        migration = MIGRATION.read_text(encoding="utf-8")
        db.executescript(migration)
        once = (_profiles(db), _actions(db))
        db.executescript(migration)
        twice = (_profiles(db), _actions(db))
        assert twice == once
    finally:
        db.close()
