"""Static checks for the Balance moving Moonfire/Sunfire filler migration."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/staged/world/2026_09_23_20_balance_moving_moonfire.sql"
# `sql/custom/world` is auto-applied by the worldserver DB updater, so the
# reverse belongs outside it, in the repository's rollback directory.  Until
# that file exists, the exact reverse below is the reviewed specification.
ROLLBACK = ROOT / "sql/custom/rollback/world/2026_09_23_20_balance_moving_moonfire_rollback.sql"
REVERSE_SQL = """
DELETE FROM `bot_rotation_action`
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 11 AND `spec_tag` = 'balance_druid' AND `role` = 'dps'
)
  AND ((`spell_id` = 8921 AND `mechanic_tags` = 'moonfire,moving_filler_20260923')
    OR (`spell_id` = 93402 AND `mechanic_tags` = 'sunfire,moving_filler_20260923'));
"""
BOT_DIR = ROOT / "src/server/game/Bots"
BALANCE = 290
MOONFIRE = 8921
SUNFIRE = 93402
MOVING_TAGS = {
    MOONFIRE: "moonfire,moving_filler_20260923",
    SUNFIRE: "sunfire,moving_filler_20260923",
}


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY, class_id INTEGER, spec_tag TEXT,
            role TEXT, enabled INTEGER);
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
            spell_id INTEGER NOT NULL DEFAULT 0, category TEXT NOT NULL,
            mechanic_tags TEXT NOT NULL DEFAULT '',
            damage_weight REAL NOT NULL DEFAULT 0,
            priority_bucket INTEGER NOT NULL DEFAULT 5,
            min_enemies INTEGER NOT NULL DEFAULT 1,
            max_enemies INTEGER NOT NULL DEFAULT 0,
            target_selector TEXT NOT NULL DEFAULT 'enemy',
            movement_directive TEXT NOT NULL DEFAULT '',
            auto_attack_mode TEXT NOT NULL DEFAULT '',
            min_range REAL NOT NULL DEFAULT 0, max_range REAL NOT NULL DEFAULT 0,
            requires_instant_cast INTEGER NOT NULL DEFAULT 0,
            requires_ranged_range INTEGER NOT NULL DEFAULT 0,
            requires_stationary INTEGER NOT NULL DEFAULT 0,
            requires_moving INTEGER NOT NULL DEFAULT 0,
            required_self_aura INTEGER NOT NULL DEFAULT 0,
            forbidden_self_aura INTEGER NOT NULL DEFAULT 0,
            maintain_aura_id INTEGER NOT NULL DEFAULT 0,
            refresh_aura_below_ms INTEGER NOT NULL DEFAULT 0,
            requires_ground_target INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1);
        INSERT INTO bot_rotation_profile VALUES
          (290, 11, 'balance_druid', 'dps', 1),
          (291, 11, 'balance_druid', 'dps', 0),
          (292, 11, 'feral_druid_dps', 'dps', 1),
          (293, 11, 'balance_druid', 'healer', 1),
          (294, 8, 'balance_druid', 'dps', 1);
        """
    )
    # Live profile 290 rows relevant to ordering (read back from the world DB).
    balance_rows = [
        (5, 88747, "offensive_cooldown", "wild_mushroom,magmaw_lava_parasite_add_duty,pinned_apl", 0.0, 1, 0, 40, 0, 0, 0),
        (10, MOONFIRE, "dot", "moonfire,dot", 0.92, 1, 0, 35, 1, MOONFIRE, 3000),
        (15, SUNFIRE, "dot", "sunfire,dot,solar_eclipse,pinned_apl", 0.93, 1, 0, 40, 0, SUNFIRE, 3000),
        (20, 5570, "dot", "insect_swarm,dot", 0.92, 1, 0, 35, 1, 5570, 3000),
        (30, 78674, "spender", "starsurge,primary,balance_starsurge_neutral_gate", 1.0, 1, 0, 35, 0, 0, 0),
        (35, 48505, "offensive_cooldown", "starfall,cooldown,pinned_apl", 0.94, 1, 0, 0, 0, 48505, 0),
        (60, 2912, "builder", "starfire,eclipse", 0.82, 3, 5, 35, 1, 0, 0),
        (70, 5176, "builder", "wrath,eclipse", 0.80, 3, 5, 35, 1, 0, 0),
        (80, 16914, "aoe", "hurricane,aoe", 0.84, 2, 0, 35, 0, 0, 0),
    ]
    for sort, spell, category, tags, weight, bucket, lo, hi, ranged, aura, refresh in balance_rows:
        db.execute(
            """INSERT INTO bot_rotation_action (profile_id, sort_order, spell_id,
            category, mechanic_tags, damage_weight, priority_bucket, target_selector,
            movement_directive, auto_attack_mode, min_range, max_range,
            requires_ranged_range, maintain_aura_id, refresh_aura_below_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'enemy', 'ranged', 'none', ?, ?, ?, ?, ?)""",
            (BALANCE, sort, spell, category, tags, weight, bucket, lo, hi, ranged, aura, refresh),
        )
    # Disabled Balance, Feral, Balance-healer and other-class rows must stay untouched.
    for profile in (291, 292, 293, 294):
        db.execute(
            """INSERT INTO bot_rotation_action (profile_id, sort_order, spell_id,
            category, mechanic_tags, damage_weight, priority_bucket, max_range,
            maintain_aura_id, refresh_aura_below_ms)
            VALUES (?, 10, 8921, 'dot', 'moonfire,dot', 0.92, 1, 35, 8921, 3000)""",
            (profile,),
        )
    return db


def _rows(db: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in db.execute("SELECT * FROM bot_rotation_action ORDER BY id")]


def _apply(db: sqlite3.Connection, sql: str) -> None:
    db.executescript(sql)


def test_migration_adds_two_last_choice_moving_rows_only_to_enabled_balance_dps() -> None:
    db = _database()
    before = _rows(db)
    _apply(db, MIGRATION.read_text(encoding="utf-8"))
    after = _rows(db)

    assert after[: len(before)] == before  # every existing row is byte-for-byte unchanged
    added = after[len(before):]
    assert sorted(row["spell_id"] for row in added) == [MOONFIRE, SUNFIRE]

    balance_before = [row for row in before if row["profile_id"] == BALANCE]
    stationary_dot = {row["spell_id"]: row for row in balance_before if row["category"] == "dot"}
    for row in added:
        assert row["profile_id"] == BALANCE
        assert row["mechanic_tags"] == MOVING_TAGS[row["spell_id"]]
        # Only while moving, never replacing the stationary APL.
        assert row["requires_moving"] == 1 and row["requires_stationary"] == 0
        # Last choice: after every existing Balance bucket and sort position.
        assert row["priority_bucket"] == 14
        assert row["priority_bucket"] > max(r["priority_bucket"] for r in balance_before)
        assert row["sort_order"] > max(r["sort_order"] for r in balance_before)
        assert row["damage_weight"] < min(
            r["damage_weight"] for r in balance_before if r["damage_weight"] > 0
        )
        # Plain native cast: no aura prerequisites or maintenance windows, no
        # ground placement, no density cap, ordinary enemy target.
        assert row["maintain_aura_id"] == 0 and row["refresh_aura_below_ms"] == 0
        assert row["required_self_aura"] == 0 and row["forbidden_self_aura"] == 0
        assert row["requires_ground_target"] == 0 and row["requires_ranged_range"] == 0
        assert row["requires_instant_cast"] == 0
        assert row["target_selector"] == "enemy" and row["max_enemies"] == 0
        assert (row["movement_directive"], row["auto_attack_mode"]) == ("ranged", "none")
        # Range envelope mirrors the spell's existing stationary DoT row.
        assert row["min_range"] == 0
        assert row["max_range"] == stationary_dot[row["spell_id"]]["max_range"]
        assert row["enabled"] == 1


def test_migration_is_idempotent() -> None:
    db = _database()
    sql = MIGRATION.read_text(encoding="utf-8")
    _apply(db, sql)
    once = _rows(db)
    _apply(db, sql)
    assert _rows(db) == once


def test_exact_reverse_restores_pre_migration_rows() -> None:
    db = _database()
    before = _rows(db)
    _apply(db, MIGRATION.read_text(encoding="utf-8"))
    reverse = ROLLBACK.read_text(encoding="utf-8") if ROLLBACK.exists() else REVERSE_SQL
    _apply(db, reverse)
    assert _rows(db) == before
    # Reapplying the reverse on the restored state is a no-op.
    _apply(db, reverse)
    assert _rows(db) == before


def test_migration_is_additive_profile_data_only() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    statements = [
        s.strip() for s in re.sub(r"--[^\n]*", "", sql).split(";") if s.strip()
    ]
    assert len(statements) == 2
    for statement in statements:
        assert statement.upper().startswith("INSERT INTO `BOT_ROTATION_ACTION`")
        assert "NOT EXISTS" in statement.upper()
    body = " ".join(statements).lower()
    # No profile edits, deletes, spell scripts, procs, auras or forced state.
    for forbidden in ("update ", "delete ", "spell_script_names", "spell_proc",
                      "spell_bonus", "required_self_aura", "maintain_aura_id",
                      "bot_rotation_profile` set"):
        assert forbidden not in body


def _category_index(name: str) -> int:
    header = (BOT_DIR / "BotCombatActionCatalog.h").read_text(encoding="utf-8")
    enum = header[header.index("enum class BotCombatActionCategory"):]
    enum = enum[enum.index("{") + 1: enum.index("}")]
    members = [m.strip().split("=")[0].strip() for m in enum.split(",") if m.strip()]
    return members.index(name)


def test_moving_rows_have_distinct_stable_action_ids_from_maintained_dots() -> None:
    catalog = (BOT_DIR / "BotCombatActionCatalog.cpp").read_text(encoding="utf-8")
    assert "return (uint32(category) + 1u) * 100000u + concreteId;" in catalog

    def stable(category: str, spell: int) -> int:
        return (_category_index(category) + 1) * 100000 + spell

    for spell in (MOONFIRE, SUNFIRE):
        assert stable("Builder", spell) != stable("Dot", spell)
    # The live maintained Sunfire row was observed as action id 893402.
    assert stable("Dot", SUNFIRE) == 893402


def test_native_gates_keep_one_eclipse_variant_and_moving_only_semantics() -> None:
    resolver = (BOT_DIR / "BotWorldPopulationMgrCombatResolver.cpp").read_text(encoding="utf-8")
    candidates = (BOT_DIR / "BotClassSpecActionProfileCandidates.cpp").read_text(encoding="utf-8")
    # Eclipse direction keys on spell id, so exactly one of the two rows can pass.
    assert re.search(
        r"\(candidate\.SpellId == 93402 && !solarEclipse\)\s*\|\|\s*"
        r"\(candidate\.SpellId == 8921 && solarEclipse\)",
        resolver,
    )
    assert 'candidate.RejectReason = "eclipse_dot_direction";' in resolver
    # Stationary ticks reject requires_moving rows before any cast.
    assert "(spell.RequiresMoving && !bot->isMoving())" in candidates
    assert 'return "movement_gate";' in candidates
    # Cast-time fillers stay rejected while moving; instants remain admissible.
    assert 'candidate.RejectReason = "movement_requires_instant_action";' in resolver
