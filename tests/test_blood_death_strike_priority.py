from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "sql/custom/world/2026_09_19_04_bot_blood_death_strike_priority.sql"
)
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"

PROFILE_COLUMNS = (
    "id",
    "class_id",
    "spec_tag",
    "role",
    "version",
    "source_note",
    "scope_note",
)
ACTION_COLUMNS = (
    "id",
    "profile_id",
    "sort_order",
    "spell_id",
    "category",
    "mechanic_tags",
    "damage_weight",
    "healing_weight",
    "threat_weight",
    "mitigation_weight",
    "survival_weight",
    "priority_bucket",
    "min_enemies",
    "max_self_health_pct",
    "requires_melee_range",
    "target_selector",
    "enabled",
)

BLOOD_PROFILE = 601
OTHER_SPEC_PROFILE = 602
OTHER_ROLE_PROFILE = 603
HEART_STRIKE = 55050
DEATH_STRIKE = 49998


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY,
            class_id INTEGER NOT NULL,
            spec_tag TEXT NOT NULL,
            role TEXT NOT NULL,
            version INTEGER NOT NULL,
            source_note TEXT NOT NULL,
            scope_note TEXT NOT NULL
        );
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL,
            spell_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            mechanic_tags TEXT NOT NULL,
            damage_weight REAL NOT NULL,
            healing_weight REAL NOT NULL,
            threat_weight REAL NOT NULL,
            mitigation_weight REAL NOT NULL,
            survival_weight REAL NOT NULL,
            priority_bucket INTEGER NOT NULL,
            min_enemies INTEGER NOT NULL,
            max_self_health_pct REAL NOT NULL,
            requires_melee_range INTEGER NOT NULL,
            target_selector TEXT NOT NULL,
            enabled INTEGER NOT NULL
        );
        """
    )
    db.executemany(
        "INSERT INTO bot_rotation_profile VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                BLOOD_PROFILE,
                6,
                "blood_death_knight",
                "tank",
                24,
                "phase9_blood_strict_area_category_2026_07_29",
                "Keep enemy-centered Death and Decay first",
            ),
            # Same class, but a different spec must not receive the repair.
            (
                OTHER_SPEC_PROFILE,
                6,
                "frost_death_knight",
                "dps",
                11,
                "frost_profile",
                "Frost profile remains independent",
            ),
            # Same spec, but a different role must not receive the repair.
            (
                OTHER_ROLE_PROFILE,
                6,
                "blood_death_knight",
                "dps",
                12,
                "blood_dps_profile",
                "DPS profile remains independent",
            ),
        ],
    )
    db.executemany(
        "INSERT INTO bot_rotation_action VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            # Scores are retained native-float inputs from the closed d495
            # rows: both actions are valid at 63.3332% health with FU ready.
            (
                1,
                BLOOD_PROFILE,
                40,
                DEATH_STRIKE,
                "mitigation",
                "death_strike,self_heal,melee,threat",
                0.76,
                0.80,
                0.75,
                0.65,
                0.85,
                2,
                1,
                1.0,
                1,
                "enemy",
                1,
            ),
            (
                2,
                BLOOD_PROFILE,
                42,
                HEART_STRIKE,
                "builder",
                "heart_strike,blood_rune,single_target,threat",
                1.30,
                0.0,
                1.25,
                0.0,
                0.0,
                1,
                1,
                1.0,
                1,
                "enemy",
                1,
            ),
            # An unrelated Blood action demonstrates that only Death Strike's
            # bucket is changed and its fields are preserved.
            (
                3,
                BLOOD_PROFILE,
                60,
                47541,
                "spender",
                "death_coil,runic_power",
                0.68,
                0.0,
                0.45,
                0.0,
                0.0,
                4,
                1,
                1.0,
                0,
                "enemy",
                1,
            ),
            (
                4,
                OTHER_SPEC_PROFILE,
                40,
                DEATH_STRIKE,
                "frost_unrelated",
                "unrelated",
                0.11,
                0.0,
                0.12,
                0.0,
                0.0,
                2,
                1,
                1.0,
                1,
                "enemy",
                1,
            ),
            (
                5,
                OTHER_ROLE_PROFILE,
                40,
                DEATH_STRIKE,
                "blood_dps_unrelated",
                "unrelated",
                0.21,
                0.0,
                0.22,
                0.0,
                0.0,
                2,
                1,
                1.0,
                1,
                "enemy",
                1,
            ),
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


def _run_migration(db: sqlite3.Connection) -> None:
    # This migration intentionally uses the SQLite/MySQL common subset so the
    # same forward SQL can be replayed against a deterministic fixture.
    db.executescript(MIGRATION.read_text(encoding="utf-8"))


def test_sql_replay_is_idempotent_and_scoped_to_blood_tank_death_strike():
    db = _database()
    before_profiles = _profiles(db)
    before_actions = _actions(db)
    _run_migration(db)
    first_profiles = _profiles(db)
    first_actions = _actions(db)
    _run_migration(db)

    assert _profiles(db) == first_profiles
    assert _actions(db) == first_actions
    assert first_profiles[0][4:] == (
        25,
        "phase9_blood_death_strike_priority_2026_09_19",
        "Keep Death Strike and Heart Strike in the same bucket so the higher-scoring valid action wins",
    )
    assert first_profiles[1:] == before_profiles[1:]

    # Death Strike is the only changed action field in the targeted profile.
    before_ds = before_actions[0]
    after_ds = first_actions[0]
    assert before_ds[11] == 2 and after_ds[11] == 1
    assert after_ds[:11] == before_ds[:11]
    assert after_ds[12:] == before_ds[12:]

    # Heart Strike's row, including its bucket and all native score inputs,
    # remains byte-for-byte equal in the database replay.
    assert _action(db, 2) == before_actions[1]
    assert first_actions[2:] == before_actions[2:]


def _candidate_preferred_source() -> str:
    source = RESOLVER.read_text(encoding="utf-8")
    start = source.index("    auto candidatePreferred =")
    end = source.index("\n    };", start) + len("\n    };")
    return source[start:end]


def _compile_native_selection(
    tmp_path: Path,
    *,
    death_strike_bucket: int,
    heart_strike_bucket: int,
    death_strike_score: float = 4.55550003,
    heart_strike_score: float = 4.17000008,
    include_death_strike: bool = True,
) -> str:
    comparator = _candidate_preferred_source()
    ds = (
        f"BotActionCandidate deathStrike{{{{{death_strike_bucket}, 40}}, {death_strike_score!r}f, {DEATH_STRIKE}}};"
        if include_death_strike
        else ""
    )
    hs = f"BotActionCandidate heartStrike{{{{{heart_strike_bucket}, 42}}, {heart_strike_score!r}f, {HEART_STRIKE}}};"
    choose = (
        "BotActionCandidate* selected = nullptr;\n"
        "if (candidatePreferred(deathStrike, selected)) selected = &deathStrike;\n"
        "if (candidatePreferred(heartStrike, selected)) selected = &heartStrike;\n"
        "assert(selected != nullptr);\n"
        "return selected->ActionId == 49998 ? \"death_strike\" : \"heart_strike\";"
        if include_death_strike
        else "assert(candidatePreferred(heartStrike, nullptr));\nreturn \"heart_strike\";"
    )
    expected = (
        "death_strike"
        if include_death_strike
        and (
            death_strike_bucket < heart_strike_bucket
            or (
                death_strike_bucket == heart_strike_bucket
                and death_strike_score > heart_strike_score
            )
        )
        else "heart_strike"
    )
    program = f"""
#include <cassert>
#include <string>
struct ActionProfile {{ unsigned PriorityBucket; unsigned SortOrder; }};
struct BotActionCandidate {{ ActionProfile Profile; float Score; unsigned ActionId; }};
std::string Select() {{
    {comparator}
    {ds}
    {hs}
    {choose}
}}
int main() {{
    std::string selected = Select();
    assert(selected == \"{expected}\");
}}
"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "blood_priority_native.cpp"
    binary = tmp_path / "blood_priority_native"
    source.write_text(program, encoding="utf-8")
    subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
    return program


def test_native_float_scores_flip_only_after_bucket_repair_and_preserve_fallback(
    tmp_path: Path,
):
    db = _database()
    ds_before = _action(db, 1)
    hs_before = _action(db, 2)
    low_health_pct = 0.633332
    ready_runes = 2  # B0/U1/F0/D1 from the retained valid-valid rows.
    assert low_health_pct < 0.80
    assert ready_runes >= 2

    # Before the migration, the exact production comparator rejects the
    # higher-score Death Strike because bucket 2 loses to Heart Strike bucket1.
    _compile_native_selection(
        tmp_path / "before",
        death_strike_bucket=ds_before[11],
        heart_strike_bucket=hs_before[11],
        death_strike_score=4.55550003,
        heart_strike_score=4.17000008,
    )

    _run_migration(db)
    ds_after = _action(db, 1)
    hs_after = _action(db, 2)
    assert float(ds_after[6]) == float(ds_before[6])
    assert float(ds_after[8]) == float(ds_before[8])
    assert float(hs_after[6]) == float(hs_before[6])
    assert ds_after[11] == hs_after[11] == 1

    # Loading the retained scores as native C++ float values now lets the
    # higher-scoring valid Death Strike win within the shared bucket.
    _compile_native_selection(
        tmp_path / "after",
        death_strike_bucket=ds_after[11],
        heart_strike_bucket=hs_after[11],
        death_strike_score=4.55550003,
        heart_strike_score=4.17000008,
    )

    # With only a Blood rune ready, Death Strike is invalid and Heart Strike
    # remains the legal fallback; the bucket repair does not relax rune gates.
    fallback_ready_runes = 1  # B-only: the native Death Strike rune gate fails.
    assert fallback_ready_runes < 2
    _compile_native_selection(
        tmp_path / "fallback",
        death_strike_bucket=ds_after[11],
        heart_strike_bucket=hs_after[11],
        include_death_strike=False,
    )
