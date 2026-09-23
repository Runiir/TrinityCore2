"""Static checks for the Blood tank rune-recovery bundle (2026_09_23_50-52).

2026_09_23_50 adds the native ``max_ready_runes`` upper bound. 2026_09_23_51
and 2026_09_23_52 add Blood Tap and Empower Rune Weapon rows gated by it. The
row migrations are replayed, after the promoted Outbreak migration, against an
in-memory SQLite copy of the live Blood tank rows (world DB profile 267 v28,
read on 2026-09-23). Score arithmetic mirrors the candidate builder and
resolver formulas, whose source text is pinned. The new gate is compiled out
of BotClassSpecActionProfileCandidates.cpp and run for every ready-rune count.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import struct
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src/server/game/Bots"
SQL = ROOT / "sql/custom/world"
ALTER = SQL / "2026_09_23_50_blood_max_ready_runes_gate.sql"
OUTBREAK_SQL = SQL / "2026_09_23_10_blood_outbreak_disease_upkeep.sql"
BLOOD_TAP_SQL = SQL / "2026_09_23_51_blood_tap_rune_recovery.sql"
ERW_SQL = SQL / "2026_09_23_52_blood_empower_rune_weapon_rune_recovery.sql"
MANGLE_DISEASE_SQL = SQL / "2026_09_23_41_blood_mangle_disease_runes.sql"
HEADER = BOT / "BotClassSpecActionProfile.h"
LOADER = BOT / "BotClassSpecActionProfileDb.cpp"
CANDIDATES = BOT / "BotClassSpecActionProfileCandidates.cpp"
RESOLVER = BOT / "BotWorldPopulationMgrCombatResolver.cpp"
RESERVATION = BOT / "BotWorldPopulationMgrRaidCooldownReservation.h"
ACTION_PROFILES = ROOT / "experiments/configs/cata_434_action_profiles.json"
TARGETS = ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
DBC = ROOT / "data/dbc/enUS"

BLOOD_TAP, ERW, OUTBREAK, IMPROVED_BLOOD_TAP = 45529, 47568, 77575, 94555
DEATH_STRIKE, HEART_STRIKE, RUNE_STRIKE = 49998, 55050, 56815
BLOOD, FROST, UNHOLY, BLOOD_DPS = 267, 283, 284, 900
MANGLE_SEAT = 78412

V28 = (
    28,
    "phase9_blood_mangle_disease_runes_2026_09_23",
    "Hold Heart Strike, Icy Touch and Plague Strike while the Magmaw Mangle seat aura 78412 is up "
    "so Death Strike gets the runes",
)
V29_NOTE = "phase9_blood_outbreak_disease_upkeep_2026_09_23"
V30_NOTE = "phase9_blood_tap_rune_recovery_2026_09_23"
V31_NOTE = "phase9_blood_empower_rune_weapon_rune_recovery_2026_09_23"
BLOOD_TAP_TAGS = "blood_tap,rune_activation,death_rune,runes_short,off_gcd"
ERW_TAGS = "empower_rune_weapon,rune_activation,runic_power,runes_short,off_gcd"

COLUMNS = (
    "id", "profile_id", "sort_order", "spell_id", "category", "mechanic_tags",
    "damage_weight", "healing_weight", "threat_weight", "mitigation_weight",
    "survival_weight", "priority_bucket", "min_enemies", "max_enemies",
    "max_self_health_pct", "requires_melee_range", "target_selector",
    "movement_directive", "auto_attack_mode", "min_range", "max_range",
    "maintain_aura_id", "refresh_aura_below_ms", "min_ready_runes",
    "max_ready_runes", "forbidden_self_aura", "enabled",
)
# Live profile 267 v28 rows: (id, sort, spell, category, D, H, T, M, S, bucket,
# min_enemies, max_self_hp, melee, selector, max_range, maintain, refresh,
# min_ready_runes, forbidden_self_aura).
BLOOD_ROWS = (
    (2042, 10, 57330, "buff", 0.15, 0, 0.2, 0, 0.4, 0, 1, 1.0, 0, "self", 0, 57330, 0, 0, 0),
    (2043, 12, 48263, "buff", 0, 0, 0.3, 0.9, 0.9, 0, 1, 1.0, 0, "self", 0, 48263, 0, 0, 0),
    (3560, 31, 43265, "aoe", 1, 0, 5, 0, 0, 0, 2, 1.0, 0, "ground_enemy", 30, 0, 0, 1, 0),
    (2875, 32, 48721, "aoe", 1.2, 0, 4, 0, 0, 0, 2, 1.0, 0, "self", 0, 0, 0, 1, 0),
    (2876, 15, 49028, "offensive_cooldown", 2, 0, 2, 0.15, 0.1, 1, 1, 1.0, 0, "enemy", 0, 0, 0, 0, 0),
    (2044, 20, 49222, "defensive", 0, 0, 0.2, 0.85, 0.85, 1, 1, 0.9, 0, "self", 0, 49222, 0, 0, 0),
    (2045, 25, 48792, "defensive", 0, 0, 0.1, 1, 1, 1, 1, 0.65, 0, "self", 0, 48792, 0, 0, 0),
    (2046, 28, 55233, "defensive", 0, 0.3, 0.1, 0.85, 1, 1, 1, 0.7, 0, "self", 0, 55233, 0, 0, 0),
    (2047, 30, 47528, "interrupt", 0.15, 0, 0, 0, 0.2, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 0, 0),
    (2048, 35, 56222, "taunt", 0, 0, 4, 0, 0.3, 1, 1, 1.0, 0, "enemy", 0, 0, 0, 0, 0),
    (2049, 40, DEATH_STRIKE, "mitigation", 0.76, 0.8, 0.75, 0.65, 0.85, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 2, 0),
    (2874, 42, HEART_STRIKE, "builder", 1.5, 0, 1.5, 0, 0, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 1, MANGLE_SEAT),
    (2884, 44, RUNE_STRIKE, "spender", 1.45, 0, 1.55, 0, 0, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 0, 0),
    (2050, 45, 45477, "threat_build", 1.05, 0, 1.2, 0, 0, 1, 1, 1.0, 0, "enemy", 0, 55095, 3000, 1, MANGLE_SEAT),
    (2051, 50, 45462, "builder", 1.05, 0, 1.15, 0, 0, 1, 1, 1.0, 1, "enemy", 0, 55078, 3000, 1, MANGLE_SEAT),
    (2052, 60, 47541, "spender", 0.68, 0, 0.45, 0, 0, 4, 1, 1.0, 0, "enemy", 0, 0, 0, 0, 0),
)
# Frost and Unholy already own Blood Tap / Empower Rune Weapon rows; they must
# neither block nor receive the Blood rows.
OTHER_ROWS = (
    (2993, FROST, 88, BLOOD_TAP, "resource_generator", 0.89, 4),
    (2992, FROST, 90, ERW, "resource_generator", 0.88, 4),
    (2999, UNHOLY, 31, ERW, "offensive_cooldown", 0.96, 1),
    (3000, UNHOLY, 75, BLOOD_TAP, "resource_generator", 0.72, 3),
)


def _create(db: sqlite3.Connection, *, with_max_ready_runes: bool) -> None:
    max_ready = "max_ready_runes INTEGER NOT NULL DEFAULT 0," if with_max_ready_runes else ""
    db.executescript(
        f"""
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, spec_tag TEXT NOT NULL,
            role TEXT NOT NULL, version INTEGER NOT NULL, source_note TEXT NOT NULL,
            scope_note TEXT NOT NULL);
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0, spell_id INTEGER NOT NULL DEFAULT 0,
            category TEXT NOT NULL, mechanic_tags TEXT NOT NULL DEFAULT '',
            damage_weight REAL NOT NULL DEFAULT 0, healing_weight REAL NOT NULL DEFAULT 0,
            threat_weight REAL NOT NULL DEFAULT 0, mitigation_weight REAL NOT NULL DEFAULT 0,
            survival_weight REAL NOT NULL DEFAULT 0, priority_bucket INTEGER NOT NULL DEFAULT 5,
            min_enemies INTEGER NOT NULL DEFAULT 1, max_enemies INTEGER NOT NULL DEFAULT 0,
            max_self_health_pct REAL NOT NULL DEFAULT 1, requires_melee_range INTEGER NOT NULL DEFAULT 0,
            target_selector TEXT NOT NULL DEFAULT 'enemy', movement_directive TEXT NOT NULL DEFAULT '',
            auto_attack_mode TEXT NOT NULL DEFAULT '', min_range REAL NOT NULL DEFAULT 0,
            max_range REAL NOT NULL DEFAULT 0, maintain_aura_id INTEGER NOT NULL DEFAULT 0,
            refresh_aura_below_ms INTEGER NOT NULL DEFAULT 0, min_ready_runes INTEGER NOT NULL DEFAULT 0,
            {max_ready}
            forbidden_self_aura INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1);
        """
    )


def _database(*, with_max_ready_runes: bool = True) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    _create(db, with_max_ready_runes=with_max_ready_runes)
    db.executemany(
        "INSERT INTO bot_rotation_profile VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (BLOOD, 6, "blood_death_knight", "tank", *V28),
            (FROST, 6, "frost_death_knight", "dps", 11, "frost", "frost scope"),
            (UNHOLY, 6, "unholy_death_knight", "dps", 2, "unholy", "unholy scope"),
            (BLOOD_DPS, 6, "blood_death_knight", "dps", 3, "blood dps", "dps scope"),
        ],
    )
    names = [c for c in COLUMNS if with_max_ready_runes or c != "max_ready_runes"]
    for (rid, sort, spell, cat, d, h, t, m, s, bucket, min_en, max_hp, melee, selector,
         max_range, maintain, refresh, runes, forbidden) in BLOOD_ROWS:
        values = dict(zip(COLUMNS, (
            rid, BLOOD, sort, spell, cat, "", d, h, t, m, s, bucket, min_en, 0, max_hp, melee,
            selector, "melee", "melee", 0, max_range, maintain, refresh, runes, 0, forbidden, 1)))
        db.execute(
            f"INSERT INTO bot_rotation_action ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
            [values[c] for c in names],
        )
    for rid, profile, sort, spell, cat, d, bucket in OTHER_ROWS:
        db.execute(
            "INSERT INTO bot_rotation_action (id, profile_id, sort_order, spell_id, category, "
            "damage_weight, priority_bucket, target_selector) VALUES (?, ?, ?, ?, ?, ?, ?, 'self')",
            (rid, profile, sort, spell, cat, d, bucket),
        )
    return db


def _state(db: sqlite3.Connection) -> tuple[list[tuple], list[tuple]]:
    columns = [row[1] for row in db.execute("PRAGMA table_info(bot_rotation_action)")]
    return (
        db.execute("SELECT * FROM bot_rotation_profile ORDER BY id").fetchall(),
        db.execute(f"SELECT {', '.join(columns)} FROM bot_rotation_action ORDER BY id").fetchall(),
    )


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _executable(path: Path) -> str:
    return "\n".join(l for l in _text(path).splitlines() if not l.lstrip().startswith("--"))


def _reverse(path: Path) -> str:
    lines = _text(path).splitlines()
    block = lines[lines.index("-- BEGIN REVERSE MIGRATION") + 1 : lines.index("-- END REVERSE MIGRATION")]
    assert block and all(line.startswith("-- ") for line in block)
    return "\n".join(line[3:] for line in block)


def _rows(db: sqlite3.Connection, profile: int, spell: int) -> list[dict]:
    db.row_factory = sqlite3.Row
    rows = db.execute(
        f"SELECT {', '.join(COLUMNS)} FROM bot_rotation_action WHERE profile_id = ? AND spell_id = ?",
        (profile, spell),
    ).fetchall()
    db.row_factory = None
    return [dict(row) for row in rows]


def _profile(db: sqlite3.Connection) -> tuple:
    return db.execute(
        "SELECT version, source_note FROM bot_rotation_profile WHERE id = ?", (BLOOD,)
    ).fetchone()


# --- 2026_09_23_50: the max_ready_runes column --------------------------------


def _sqlite_alter(sql: str) -> str:
    # MariaDB-only clauses; SQLite appends the column and has no IF [NOT] EXISTS.
    return (sql.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN")
            .replace("DROP COLUMN IF EXISTS", "DROP COLUMN")
            .replace(" AFTER `min_ready_runes`", ""))


def test_max_ready_runes_column_is_additive_default_off_and_reversible():
    executable = _executable(ALTER)
    statements = [s.strip() for s in executable.split(";") if s.strip()]
    assert statements == [
        "ALTER TABLE `bot_rotation_action`\n  ADD COLUMN IF NOT EXISTS `max_ready_runes` "
        "TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `min_ready_runes`"
    ]
    reverse = _reverse(ALTER)
    assert [s.strip() for s in reverse.split(";") if s.strip()] == [
        "ALTER TABLE `bot_rotation_action`\n  DROP COLUMN IF EXISTS `max_ready_runes`"
    ]

    db = _database(with_max_ready_runes=False)
    before_profiles, before_actions = _state(db)
    db.executescript(_sqlite_alter(executable))
    after_profiles, after_actions = _state(db)
    columns = [row[1] for row in db.execute("PRAGMA table_info(bot_rotation_action)")]
    assert columns[-1] == "max_ready_runes"
    # Every existing row keeps every value and gets the disabled bound 0.
    assert after_profiles == before_profiles
    assert [row[:-1] for row in after_actions] == before_actions
    assert {row[-1] for row in after_actions} == {0}

    db.executescript(_sqlite_alter(reverse))
    assert _state(db) == (before_profiles, before_actions)


def test_gate_column_is_applied_before_the_rows_that_use_it():
    names = sorted(p.name for p in SQL.glob("2026_09_23_*.sql"))
    order = [names.index(p.name) for p in (OUTBREAK_SQL, MANGLE_DISEASE_SQL, ALTER, BLOOD_TAP_SQL, ERW_SQL)]
    assert order == sorted(order)
    for path in (BLOOD_TAP_SQL, ERW_SQL):
        assert "`max_ready_runes`" in _executable(path)
        assert "2026_09_23_50" in _text(path).split("INSERT INTO", 1)[0]


# --- 2026_09_23_51/52: Blood Tap and Empower Rune Weapon rows ----------------

CHAIN = (OUTBREAK_SQL, BLOOD_TAP_SQL, ERW_SQL)


def test_rows_replay_after_outbreak_idempotently_and_touch_only_blood_tank():
    for path in (BLOOD_TAP_SQL, ERW_SQL):
        executable = _executable(path)
        assert "DELETE" not in executable.upper()
        assert [s.split(None, 2)[:2] for s in executable.split(";") if s.strip()] == [
            ["INSERT", "INTO"], ["UPDATE", "`bot_rotation_profile`"]]

    db = _database()
    before_profiles, before_actions = _state(db)
    for path in CHAIN:
        db.executescript(_text(path))
    first = _state(db)
    for path in CHAIN:
        db.executescript(_text(path))
    assert _state(db) == first

    blood_tap, erw = _rows(db, BLOOD, BLOOD_TAP), _rows(db, BLOOD, ERW)
    assert len(blood_tap) == 1 and len(erw) == 1 and len(_rows(db, BLOOD, OUTBREAK)) == 1
    shared = {
        "priority_bucket": 1, "min_enemies": 1, "max_enemies": 0, "max_self_health_pct": 1.0,
        "requires_melee_range": 0, "target_selector": "self", "min_range": 0, "max_range": 0,
        "maintain_aura_id": 0, "refresh_aura_below_ms": 0, "min_ready_runes": 0,
        "max_ready_runes": 1, "forbidden_self_aura": 0, "enabled": 1,
        "healing_weight": 0, "mitigation_weight": 0, "survival_weight": 0,
    }
    for row, sort, category, tags, weights in (
        (blood_tap[0], 37, "resource_generator", BLOOD_TAP_TAGS, (1.2, 1.9)),
        (erw[0], 36, "offensive_cooldown", ERW_TAGS, (1.1, 2.2)),
    ):
        assert {k: row[k] for k in shared} == shared
        assert (row["sort_order"], row["category"], row["mechanic_tags"]) == (sort, category, tags)
        assert (row["damage_weight"], row["threat_weight"]) == pytest.approx(weights)
    sorts = [r[1] for r in BLOOD_ROWS] + [38]
    assert 36 not in sorts and 37 not in sorts

    # Pre-existing rows (including other specs' Blood Tap/ERW) are untouched.
    after_profiles, after_actions = first
    added = {blood_tap[0]["id"], erw[0]["id"], _rows(db, BLOOD, OUTBREAK)[0]["id"]}
    assert [a for a in after_actions if a[0] not in added] == before_actions
    for profile in (FROST, UNHOLY, BLOOD_DPS):
        assert len(_rows(db, profile, BLOOD_TAP)) == (profile != BLOOD_DPS)
        assert len(_rows(db, profile, ERW)) == (profile != BLOOD_DPS)
    assert after_profiles[0][4:] == (
        31, V31_NOTE,
        "Cast native Empower Rune Weapon only while at most one rune is ready, "
        "above Blood Tap and below Death Strike",
    )
    assert after_profiles[1:] == before_profiles[1:]

    # The version bumps never lower a later profile version.
    db.execute("UPDATE bot_rotation_profile SET version = 40 WHERE id = ?", (BLOOD,))
    for path in CHAIN:
        db.executescript(_text(path))
    assert _profile(db)[0] == 40


def test_reverse_blocks_restore_each_prior_state_in_lifo_order():
    db = _database()
    states = [_state(db)]
    for path in CHAIN:
        db.executescript(_text(path))
        states.append(_state(db))
    assert [_profile_version(s) for s in states] == [28, 29, 30, 31]

    for path, expected in zip(reversed(CHAIN), reversed(states[:-1])):
        db.executescript(_reverse(path))
        assert _state(db) == expected
        db.executescript(_reverse(path))  # replaying a reverse is harmless
        assert _state(db) == expected

    # Reversing Blood Tap out of order removes only its row; the later
    # Empower Rune Weapon identity is not clobbered.
    for path in CHAIN:
        db.executescript(_text(path))
    db.executescript(_reverse(BLOOD_TAP_SQL))
    assert _rows(db, BLOOD, BLOOD_TAP) == [] and len(_rows(db, BLOOD, ERW)) == 1
    assert _profile(db) == (31, V31_NOTE)


def _profile_version(state: tuple[list[tuple], list[tuple]]) -> int:
    return next(p[4] for p in state[0] if p[0] == BLOOD)


# --- Scores ------------------------------------------------------------------


def _scores(d: float, h: float, t: float, m: float, s: float, bucket: int) -> dict[str, float]:
    base = d + h + t + m + s - bucket * 0.03
    return {
        "balanced_role_dps": base + d * 0.55 + h * 0.25 + t * 0.25,
        "role_first_tank": base + t + m + s * 0.45,
        "dps_push": base + d,
        "pure_survival": base + s * 1.5 + m + h - d * 0.25,
    }


def _row_scores(row: dict) -> dict[str, float]:
    return _scores(row["damage_weight"], row["healing_weight"], row["threat_weight"],
                   row["mitigation_weight"], row["survival_weight"], row["priority_bucket"])


def test_recovery_rows_rank_below_death_strike_in_every_mode():
    candidates = _text(CANDIDATES)
    assert "candidate.Score = spell.DamageWeight + spell.HealingWeight + spell.ThreatWeight" in candidates
    assert "- float(spell.PriorityBucket) * 0.03f;" in candidates
    resolver = _text(RESOLVER)
    for formula in (
        "roleScore += candidate.Profile.DamageWeight * 0.55f + candidate.Profile.HealingWeight * 0.25f + candidate.Profile.ThreatWeight * 0.25f;",
        "roleScore += candidate.Profile.ThreatWeight + candidate.Profile.MitigationWeight + candidate.Profile.SurvivalWeight * 0.45f;",
        "roleScore += candidate.Profile.DamageWeight + candidate.Profile.ProgressionWeight * 0.35f;",
        "roleScore += candidate.Profile.SurvivalWeight * 1.5f + candidate.Profile.MitigationWeight + candidate.Profile.HealingWeight;",
        "roleScore -= candidate.Profile.DamageWeight * 0.25f;",
        # Bucket is compared before score, so equal buckets make score decisive.
        "return !current || candidate.Profile.PriorityBucket < current->Profile.PriorityBucket",
    ):
        assert formula in resolver

    db = _database()
    for path in CHAIN:
        db.executescript(_text(path))
    rows = {spell: _rows(db, BLOOD, spell)[0]
            for spell in (BLOOD_TAP, ERW, DEATH_STRIKE, HEART_STRIKE, RUNE_STRIKE)}
    assert {row["priority_bucket"] for row in rows.values()} == {1}
    bt, erw, ds, hs, rs = (_row_scores(rows[s]) for s in (BLOOD_TAP, ERW, DEATH_STRIKE, HEART_STRIKE, RUNE_STRIKE))

    assert bt == pytest.approx({"balanced_role_dps": 4.205, "role_first_tank": 4.97,
                                "dps_push": 4.27, "pure_survival": 2.77})
    assert erw == pytest.approx({"balanced_role_dps": 4.425, "role_first_tank": 5.47,
                                 "dps_push": 4.37, "pure_survival": 2.995})
    assert ds == pytest.approx({"balanced_role_dps": 4.5855, "role_first_tank": 5.5625,
                                "dps_push": 4.54, "pure_survival": 6.315})
    for mode in ds:
        # Never above Death Strike, including the survival modes; Empower Rune
        # Weapon refreshes everything before Blood Tap spends its cooldown.
        assert bt[mode] < erw[mode] < ds[mode], mode
        # Margins stay far above float32 rounding in the C++ scorer.
        assert ds[mode] - erw[mode] > 0.05 and erw[mode] - bt[mode] > 0.05
    # In the tank's observed mode both fire before the rune spenders they feed.
    bal = "balanced_role_dps"
    assert max(hs[bal], rs[bal]) < bt[bal] < erw[bal]
    # No exact ties with the strikes in any mode.
    for mode in ds:
        assert {round(bt[mode], 6), round(erw[mode], 6)}.isdisjoint({round(hs[mode], 6), round(rs[mode], 6)})


# --- The native gate -----------------------------------------------------------


def _source_columns() -> list[str]:
    loader = _text(LOADER)
    query = loader[loader.index('"SELECT p.id'):loader.index('"FROM bot_rotation_profile p')]
    return re.findall(r"\b[pa]\.([a-z_]+)", query)


def test_loader_selects_loads_hashes_dumps_and_validates_max_ready_runes():
    header = _text(HEADER)
    struct_body = header[header.index("struct BotActionProfileSpell"):header.index("struct BotCombatPotionHealthOwner")]
    assert "    uint8 MinReadyRunes = 0;\n" in struct_body
    assert "    uint8 MaxReadyRunes = 0;\n" in struct_body

    loader = _text(LOADER)
    columns = _source_columns()
    # Appended: every prior SELECT index is preserved.
    assert len(columns) == 82 and columns[81] == "max_ready_runes"
    assert columns[67] == "min_ready_runes" and columns[80] == "max_hostile_target_health_pct"
    assert "spell.MinReadyRunes = fields[67].GetUInt8();" in loader
    assert "spell.MaxReadyRunes = fields[81].GetUInt8();" in loader
    payload = loader[loader.index("std::string SnapshotPayload"):loader.index("std::shared_ptr<DbRotationSnapshot> Load")]
    assert "uint32(spell.MaxReadyRunes)" in payload
    assert '\\"max_ready_runes\\":" << uint32(spell.MaxReadyRunes)' in loader
    assert ("if (spell.MinReadyRunes > spell.MaxReadyRunes && spell.MaxReadyRunes)\n"
            '            invalidReasons.insert("invalid_ready_rune_range_"') in loader


def _gate_block() -> str:
    source = _text(CANDIDATES)
    evaluate = source[source.index("std::string EvaluateCompiledConditions"):source.index(
        "std::vector<BotActionCandidate> BotClassSpecActionProfileStore::BuildCandidates")]
    start = evaluate.index("    if (spell.MinReadyRunes && ReadyRuneCount(bot) < spell.MinReadyRunes)")
    end = evaluate.index('return "ready_rune_cap";', start) + len('return "ready_rune_cap";')
    block = evaluate[start:end]
    assert 'return "ready_rune_gate";' in block
    assert "if (spell.MaxReadyRunes && ReadyRuneCount(bot) > spell.MaxReadyRunes)" in block
    # Both bounds read the same native observation.
    assert "return BotBloodDecisionObservation::ObserveReadyRunes(bot).Total;" in source
    return block


@pytest.mark.skipif(shutil.which("c++") is None, reason="no C++ compiler")
def test_native_gate_makes_rune_recovery_and_death_strike_mutually_exclusive(tmp_path):
    header = _text(HEADER)
    definition = header[header.index("struct BotActionProfileSpell"):header.index("inline bool ValidHostileTargetHealthRange")]
    source = tmp_path / "gate.cpp"
    source.write_text(
        "#include <cstdio>\n#include <string>\n"
        "using uint32=unsigned; using uint16=unsigned short; using uint8=unsigned char;\n"
        "enum class BotCombatActionCategory { Builder };\n"
        + definition
        + "\nstruct Player {};\nstatic uint8 g_ready = 0;\n"
        "uint8 ReadyRuneCount(Player const*) { return g_ready; }\n"
        "std::string Gate(Player const* bot, BotActionProfileSpell const& spell) {\n"
        + _gate_block()
        + "\n    return \"\";\n}\n"
        "int main() {\n Player bot;\n"
        " struct Row { char const* name; uint8 min; uint8 max; } rows[] = {\n"
        "  {\"death_strike\", 2, 0}, {\"rune_recovery\", 0, 1}, {\"ungated\", 0, 0}, {\"window\", 1, 3}};\n"
        " for (auto const& row : rows) {\n"
        "  BotActionProfileSpell spell; spell.MinReadyRunes = row.min; spell.MaxReadyRunes = row.max;\n"
        "  for (int ready = 0; ready <= 6; ++ready) {\n"
        "   g_ready = uint8(ready);\n"
        "   std::printf(\"%s %d %s\\n\", row.name, ready, Gate(&bot, spell).c_str());\n"
        "  }\n }\n}\n",
        encoding="utf-8",
    )
    binary = tmp_path / "gate"
    subprocess.run(["c++", "-std=c++17", str(source), "-o", str(binary)], check=True)
    output = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    gate: dict[tuple[str, int], str] = {}
    for line in output.splitlines():
        name, ready, *reason = line.split()
        gate[(name, int(ready))] = reason[0] if reason else ""

    for ready in range(7):
        ds, recovery = gate[("death_strike", ready)], gate[("rune_recovery", ready)]
        assert ds == ("" if ready >= 2 else "ready_rune_gate")
        assert recovery == ("" if ready <= 1 else "ready_rune_cap")
        # Never both valid in one decision: recovery cannot displace Death Strike.
        assert not (ds == "" and recovery == "")
        assert gate[("ungated", ready)] == ""
        assert gate[("window", ready)] == (
            "ready_rune_gate" if ready < 1 else "ready_rune_cap" if ready > 3 else "")


def test_death_strike_keeps_the_two_rune_floor_the_exclusion_relies_on():
    db = _database()
    for path in CHAIN:
        db.executescript(_text(path))
    ds = _rows(db, BLOOD, DEATH_STRIKE)[0]
    assert (ds["min_ready_runes"], ds["max_ready_runes"]) == (2, 0)
    for spell in (BLOOD_TAP, ERW):
        row = _rows(db, BLOOD, spell)[0]
        assert row["max_ready_runes"] < ds["min_ready_runes"]


def test_erw_is_reserved_on_raid_trash_and_blood_tap_is_not():
    reservation = _text(RESERVATION)
    assert 'if (route.RouteKind == "trash" || route.RouteKind == "regroup"' in reservation
    assert ("if (candidate.Category == BotCombatActionCategory::OffensiveCooldown)\n"
            '        return "raid_offensive_cooldown_reserved";') in reservation
    exempt = re.search(r'return HasAnyTag\(candidate\.MechanicTags, \{\s*"emergency".*?\}\);',
                       reservation, re.S).group(0)
    exempt_tags = set(re.findall(r'"([a-z_]+)"', exempt))
    for tags in (BLOOD_TAP_TAGS, ERW_TAGS):
        assert exempt_tags.isdisjoint(tags.split(","))
    assert "'offensive_cooldown'" in _executable(ERW_SQL)
    assert "'resource_generator'" in _executable(BLOOD_TAP_SQL)


# --- Provisioning and native facts --------------------------------------------


def test_bundle_spells_are_provisioned_in_every_admission_source():
    profiles = json.loads(_text(ACTION_PROFILES))["action_profile_spells_by_spec"]
    blood = profiles["blood_death_knight"]
    assert blood == sorted(blood)
    for spell in (BLOOD_TAP, ERW, OUTBREAK, IMPROVED_BLOOD_TAP):
        assert spell in blood
    targets = json.loads(_text(TARGETS))["targets"]
    (target,) = [t for t in targets if t["spec_target_id"] == "blood_death_knight"]
    assert target["action_profile_spell_ids"] == blood
    from tools.bot_ml.build_all_spec_phase1_catalogs import QUALIFICATION_TUNED_ACTION_SPELL_IDS
    assert {BLOOD_TAP, ERW, OUTBREAK} <= set(QUALIFICATION_TUNED_ACTION_SPELL_IDS["blood_death_knight"])
    for path in (BLOOD_TAP_SQL, ERW_SQL):
        header = _text(path).split("INSERT INTO", 1)[0]
        assert "cata_434_action_profiles.json" in header and "unknown_requested_spell" in header


def _wdbc(name: str) -> list[tuple[int, ...]]:
    data = (DBC / name).read_bytes()
    magic, count, fields, size, _strings = struct.unpack_from("<4s4i", data)
    assert magic == b"WDBC" and size == fields * 4
    return list(struct.iter_unpack(f"<{fields}i", data[20 : 20 + count * size]))


@pytest.mark.skipif(not (DBC / "Spell.dbc").exists(), reason="pinned DBC not extracted")
def test_native_blood_tap_and_empower_rune_weapon_facts():
    runes = _text(ROOT / "src/server/game/Entities/Player/Player.h")
    for name, value in (("Blood", 0), ("Unholy", 1), ("Frost", 2), ("Death", 3)):
        assert re.search(rf"\b{name}\s*=\s*{value},", runes)
    blood, unholy, frost, death = 0, 1, 2, 3
    wanted = (BLOOD_TAP, ERW, 89831, IMPROVED_BLOOD_TAP)
    spell = {r[0]: r for r in _wdbc("Spell.dbc") if r[0] in wanted}
    effects: dict[int, list[tuple]] = {}
    for r in _wdbc("SpellEffect.dbc"):
        if r[24] in spell:
            effects.setdefault(r[24], []).append(r)
    cooldowns = {r[0]: r for r in _wdbc("SpellCooldowns.dbc")}
    categories = {r[0]: r for r in _wdbc("SpellCategories.dbc")}
    power = {r[0]: r for r in _wdbc("SpellPower.dbc")}
    rune_cost = {r[0]: r for r in _wdbc("SpellRuneCost.dbc")}
    options = {r[0]: r for r in _wdbc("SpellClassOptions.dbc")}
    durations = {r[0]: r for r in _wdbc("SpellDuration.dbc")}

    def recovery(spell_id: int) -> tuple[int, int, int]:
        # (cooldown ms, GCD ms, GCD category): both spells are off the GCD.
        row = spell[spell_id]
        return cooldowns[row[37]][2], cooldowns[row[37]][3], categories[row[35]][6]

    def effect_set(spell_id: int) -> list[tuple[int, int, int, int, int]]:
        # (effect, aura, amount, misc A, misc B / trigger spell)
        return sorted((e[1], e[3], e[5], e[12], e[21] or e[13]) for e in effects[spell_id])

    # Blood Tap: 6% of base health, 60 s cooldown (30 s with Improved Blood
    # Tap 2/2), activates one Death/Blood-base rune, converts one Blood rune.
    bt = spell[BLOOD_TAP]
    assert bt[14] == -2 and power[bt[42]][3] == 6  # POWER_HEALTH, ManaCostPercentage
    assert recovery(BLOOD_TAP) == (60000, 0, 0)
    assert durations[bt[13]][1] == 20000
    assert effect_set(BLOOD_TAP) == [(6, 249, 1, blood, death), (146, 0, 1, death, 0)]
    improved = [e for e in effects[IMPROVED_BLOOD_TAP] if e[3] == 107 and e[12] == 11]
    blood_tap_mask = tuple(x & 0xFFFFFFFF for x in options[bt[36]][2:5])
    assert improved and improved[0][5] == -30000
    assert any(a & (b & 0xFFFFFFFF) for a, b in zip(blood_tap_mask, improved[0][18:21]))

    # Empower Rune Weapon: no rune cost, +25 runic power, 300 s cooldown,
    # activates 2 Blood, 2 Frost, then (89831) 6 Death/Blood-base and 2 Unholy.
    erw = spell[ERW]
    assert erw[14] == 5 and rune_cost[erw[26]][1:] == (0, 0, 0, 250)
    assert recovery(ERW) == (300000, 0, 0)
    assert effect_set(ERW) == [(64, 0, 2, 0, 89831), (146, 0, 2, blood, 0), (146, 0, 2, frost, 0)]
    assert effect_set(89831) == [(146, 0, 2, unholy, 0), (146, 0, 6, death, 0)]
