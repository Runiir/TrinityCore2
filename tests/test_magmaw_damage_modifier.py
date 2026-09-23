"""Static checks for the Magmaw 10N DamageModifier migration.

The migration is replayed against an in-memory SQLite copy of the relevant
creature_template rows, as read from the world DB on 2026-09-23 (every Magmaw
encounter template at DamageModifier 1). This exercises the forward UPDATE, its
idempotence and the documented reverse block without a MySQL server.

The calibration arithmetic is also pinned. The native swing envelope comes from
the core formula and the level-88 game-table inputs. The migration value must
reproduce the matched-stage WCL envelope (report MxFq7TRbvnjGY1hJ fight 22).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_23_30_magmaw_damage_modifier.sql"
CREATURE = ROOT / "src/server/game/Entities/Creature/Creature.cpp"
CREATURE_DATA = ROOT / "src/server/game/Entities/Creature/CreatureData.h"
CREATURE_STATS = ROOT / "src/server/game/Entities/Unit/CreatureStatSystem.cpp"

MAGMAW_10N = 41570
MAGMAW_OTHER_MODES = (51101, 51102, 51103)  # 25N, 10H, 25H: open, untouched
EXPECTED_MODIFIER = 16.0

# (entry, DamageModifier, BaseAttackTime, difficulty_entry_1..3) on 2026-09-23.
ROWS = (
    (MAGMAW_10N, 1.0, 2500, 51101, 51102, 51103),
    (51101, 1.0, 2000, 0, 0, 0),
    (51102, 1.0, 2000, 0, 0, 0),
    (51103, 1.0, 2000, 0, 0, 0),
    (41806, 1.0, 2000, 51456, 51457, 51458),  # Lava Parasite
    (42321, 1.0, 2000, 51459, 51460, 51461),  # Lava Parasite
    (42347, 1.0, 2700, 51248, 51249, 51250),  # Exposed Head of Magmaw
    (49416, 1.0, 2000, 49482, 49483, 49484),  # Blazing Bone Construct (heroic)
    (42362, 1.0, 2000, 49489, 0, 0),          # Drakonid Drudge (trash)
)

# Native inputs: gt_npc_damage_by_class_exp3 level 88 Warrior, and
# creature_classlevelstats (88, 1). Magmaw: unit_class 1, HealthScalingExpansion 3,
# rank 1, BaseVariance 1, BaseAttackTime 2500.
BASE_DAMAGE_88_WARRIOR_EXP3 = 2947.94
ATTACK_POWER_88_WARRIOR = 1226
ATTACK_TIME_S = 2.5
BASE_VARIANCE = 1.0

# WCL MxFq7TRbvnjGY1hJ fight 22, 10N: landed Magmaw melee "U" envelope, and the
# 150%-weapon Mangle initial hit (89773 has SPELL_ATTR3_IGNORE_CASTER_MODIFIERS).
WCL_MELEE_U_MIN = 111531
WCL_MELEE_U_MAX = 178540
WCL_MANGLE_INITIAL_U = 240338
MANGLE_WEAPON_PCT = 1.5
DONE_REDUCTION = 0.9  # Scarlet Fever / Demoralizing Roar / Shout / Vindication

FORWARD = re.compile(
    r"UPDATE\s+`creature_template`\s+SET\s+`DamageModifier`\s*=\s*(?P<value>[0-9.]+)\s+"
    r"WHERE\s+`entry`\s*=\s*(?P<entry>\d+)\s*;"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _executable() -> str:
    return "\n".join(line for line in _sql().splitlines() if not line.lstrip().startswith("--"))


def _migration_value() -> float:
    match = FORWARD.search(_executable())
    assert match, "forward statement must be a single-entry DamageModifier UPDATE"
    return float(match["value"])


def _reverse_block() -> list[str]:
    lines = _sql().splitlines()
    start = lines.index("-- BEGIN REVERSE MIGRATION")
    end = lines.index("-- END REVERSE MIGRATION")
    return lines[start + 1 : end]


def _reverse_sql() -> str:
    return "\n".join(line[3:] for line in _reverse_block())


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE creature_template (entry INTEGER PRIMARY KEY, DamageModifier REAL NOT NULL DEFAULT 1,"
        " BaseAttackTime INTEGER NOT NULL, difficulty_entry_1 INTEGER NOT NULL,"
        " difficulty_entry_2 INTEGER NOT NULL, difficulty_entry_3 INTEGER NOT NULL)"
    )
    db.executemany("INSERT INTO creature_template VALUES (?, ?, ?, ?, ?, ?)", ROWS)
    return db


def _state(db: sqlite3.Connection) -> list[tuple]:
    return db.execute("SELECT * FROM creature_template ORDER BY entry").fetchall()


def _modifier(db: sqlite3.Connection, entry: int) -> float:
    return db.execute("SELECT DamageModifier FROM creature_template WHERE entry = ?", (entry,)).fetchone()[0]


def _native_swing_range(modifier: float) -> tuple[float, float]:
    ap_term = ATTACK_POWER_88_WARRIOR / 14.0 * BASE_VARIANCE
    low = (BASE_DAMAGE_88_WARRIOR_EXP3 + ap_term) * ATTACK_TIME_S * modifier
    high = (BASE_DAMAGE_88_WARRIOR_EXP3 * 1.5 + ap_term) * ATTACK_TIME_S * modifier
    return low, high


def test_executable_sql_is_one_update_of_the_10n_magmaw_template():
    executable = _executable()
    assert "DELETE" not in executable.upper() and "INSERT" not in executable.upper()
    statements = [s.strip() for s in executable.split(";") if s.strip()]
    assert len(statements) == 1
    match = FORWARD.search(executable)
    assert match, "forward statement must be a single-entry DamageModifier UPDATE"
    assert int(match["entry"]) == MAGMAW_10N
    assert _migration_value() == EXPECTED_MODIFIER


def test_forward_sets_only_magmaw_10n_and_replays_idempotently():
    db = _database()
    before = _state(db)
    db.executescript(_sql())
    first = _state(db)
    db.executescript(_sql())
    assert _state(db) == first

    assert _modifier(db, MAGMAW_10N) == EXPECTED_MODIFIER
    # 25N/10H/25H, parasites, head, construct and trash are unchanged (open items).
    assert [row for row in first if row[0] != MAGMAW_10N] == [row for row in before if row[0] != MAGMAW_10N]
    for entry in MAGMAW_OTHER_MODES:
        assert _modifier(db, entry) == 1.0
    # Only DamageModifier moved on 41570; attack time and difficulty links are untouched.
    magmaw_before = next(row for row in before if row[0] == MAGMAW_10N)
    magmaw_after = next(row for row in first if row[0] == MAGMAW_10N)
    assert magmaw_after[2:] == magmaw_before[2:]


def test_reverse_block_is_inert_on_autoapply_and_restores_exact_state():
    reverse = _reverse_block()
    assert reverse and all(line.startswith("-- ") for line in reverse)
    assert "`DamageModifier` = 1 WHERE `entry` = 41570" in _reverse_sql()

    db = _database()
    before = _state(db)
    db.executescript(_sql())
    db.executescript(_reverse_sql())
    assert _state(db) == before
    db.executescript(_reverse_sql())  # replaying the reverse is harmless
    assert _state(db) == before

    # A later re-tune of 41570 is not clobbered by this migration's reverse.
    db.executescript(_sql())
    db.execute("UPDATE creature_template SET DamageModifier = 15.5 WHERE entry = ?", (MAGMAW_10N,))
    db.executescript(_reverse_sql())
    assert _modifier(db, MAGMAW_10N) == 15.5


def test_modifier_reproduces_the_matched_wcl_stage_envelope():
    modifier = _migration_value()
    low1, high1 = _native_swing_range(1.0)
    assert (round(low1, 1), round(high1, 1)) == (7588.8, 11273.7)

    # Bounds: the largest WCL hit is unreduced, and the smallest was taken under a
    # -10% physical done aura (Scarlet Fever covered roughly 58 s of the sample).
    lower_bound = WCL_MELEE_U_MAX / high1
    upper_bound = WCL_MELEE_U_MIN / (DONE_REDUCTION * low1)
    assert lower_bound == pytest.approx(15.84, abs=0.01)
    assert upper_bound == pytest.approx(16.33, abs=0.01)
    assert lower_bound <= modifier <= upper_bound
    # The native +1% auto-attack bonus (Unit::MeleeDamageBonusDone) stays in band.
    assert lower_bound <= modifier * 1.01 <= upper_bound
    # No unreduced reading can fit both ends: the WCL spread is wider than the
    # native roll spread, which is why the done-reduction stage matters.
    assert WCL_MELEE_U_MIN / low1 < lower_bound

    # Independent check: the Mangle 150% weapon hit ignores caster modifiers.
    unmodified_swing = WCL_MANGLE_INITIAL_U / MANGLE_WEAPON_PCT
    low, high = _native_swing_range(modifier)
    assert low <= unmodified_swing <= high

    header = _sql().split("UPDATE", 1)[0]
    for citation in ("68a3622133", "MxFq7TRbvnjGY1hJ", "111,531", "178,540", "240,338"):
        assert citation in header


def test_native_damage_formula_matches_the_pinned_derivation():
    creature = CREATURE.read_text(encoding="utf-8")
    assert "float basedamage = stats->GenerateBaseDamage(cInfo);" in creature
    assert "float weaponBaseMaxDamage = basedamage * 1.5f;" in creature
    assert "return BaseDamage[info->GetHealthScalingExpansion()];" in CREATURE_DATA.read_text(encoding="utf-8")
    stats = CREATURE_STATS.read_text(encoding="utf-8")
    assert "float baseValue        = GetFlatModifierValue(unitMod, BASE_VALUE) + (attackPower / 14.0f) * variance;" in stats
    assert "float dmgMultiplier    = GetCreatureTemplate()->ModDamage;" in stats
    assert "minDamage = ((weaponMinDamage + baseValue) * dmgMultiplier * basePct + totalValue) * totalPct;" in stats
