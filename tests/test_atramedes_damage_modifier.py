"""Static checks for the staged Atramedes 10N DamageModifier migration.

The migration is replayed against an in-memory SQLite copy of the Atramedes
creature_template rows (TDB 4.3.4 snapshot plus the upstream DamageModifier
reset), covering the forward UPDATE, its idempotence and the reverse block.

The calibration arithmetic is pinned against the matched-stage WCL sample
(report MxFq7TRbvnjGY1hJ fight 32, 10N), retained in atramedes_ledger_v1.json.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/staged/world/2026_09_27_01_atramedes_damage_modifier.sql"
LEDGER = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/atramedes_ledger_v1.json"
REGISTRY_PATCH = (ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/"
                  "atramedes_damage_calibration_registry_patch_v1.json")

ATRAMEDES_10N = 41442
ATRAMEDES_OTHER_MODES = (49583, 49584, 49585)  # 25N, 10H, 25H: open, untouched
EXPECTED_MODIFIER = 10.35

# (entry, DamageModifier, BaseAttackTime, difficulty_entry_1..3).
ROWS = (
    (ATRAMEDES_10N, 1.0, 1500, 49583, 49584, 49585),
    (49583, 1.0, 2000, 0, 0, 0),
    (49584, 1.0, 2000, 0, 0, 0),
    (49585, 1.0, 2000, 0, 0, 0),
    (43296, 1.0, 4000, 47774, 47775, 47776),  # Chimaeron 10N: untouched
    (41570, 16.0, 2500, 51101, 51102, 51103),  # Magmaw 10N: accepted value stays
)

BASE_DAMAGE_88_WARRIOR_EXP3 = 2947.9421
ATTACK_POWER_88_WARRIOR = 1226
ATTACK_TIME_S = 1.5
BASE_VARIANCE = 1.0
AUTO_ATTACK_BONUS = 1.01
DONE_REDUCTION = 0.9

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
    assert match
    return float(match["value"])


def _reverse_sql() -> str:
    lines = _sql().splitlines()
    block = lines[lines.index("-- BEGIN REVERSE MIGRATION") + 1: lines.index("-- END REVERSE MIGRATION")]
    assert block and all(line.startswith("-- ") for line in block)
    return "\n".join(line[3:] for line in block)


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


def _wcl_samples() -> dict:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    melee = next(value for value in ledger["values"] if value["key"] == "boss_melee_damage_modifier_10n")
    return melee["wcl_10N_samples"]


def test_executable_sql_is_one_update_of_the_10n_template():
    executable = _executable()
    assert "DELETE" not in executable.upper() and "INSERT" not in executable.upper()
    assert len([s for s in executable.split(";") if s.strip()]) == 1
    match = FORWARD.search(executable)
    assert int(match["entry"]) == ATRAMEDES_10N
    assert _migration_value() == EXPECTED_MODIFIER


def test_forward_is_scoped_and_idempotent():
    db = _database()
    before = _state(db)
    db.executescript(_sql())
    first = _state(db)
    db.executescript(_sql())
    assert _state(db) == first
    assert _modifier(db, ATRAMEDES_10N) == EXPECTED_MODIFIER
    assert [r for r in first if r[0] != ATRAMEDES_10N] == [r for r in before if r[0] != ATRAMEDES_10N]
    for entry in ATRAMEDES_OTHER_MODES:
        assert _modifier(db, entry) == 1.0
    assert _modifier(db, 41570) == 16.0


def test_reverse_restores_and_does_not_clobber_a_retune():
    db = _database()
    before = _state(db)
    db.executescript(_sql())
    db.executescript(_reverse_sql())
    assert _state(db) == before
    db.executescript(_sql())
    db.execute("UPDATE creature_template SET DamageModifier = 10.25 WHERE entry = ?", (ATRAMEDES_10N,))
    db.executescript(_reverse_sql())
    assert _modifier(db, ATRAMEDES_10N) == 10.25


def test_modifier_fits_the_matched_wcl_envelope():
    samples = _wcl_samples()
    assert samples["report"] == "MxFq7TRbvnjGY1hJ" and samples["fight"] == 32 and samples["mode"] == "10N"
    rows = samples["landed"]
    unreduced = [row["u"] for row in rows if not row["done_reduction_aura"]]
    reduced = [row["u"] for row in rows if row["done_reduction_aura"]]
    assert (len(unreduced), len(reduced)) == (3, 19)

    low1, high1 = _native_swing_range(1.0)
    assert (round(low1, 1), round(high1, 1)) == (4553.3, 6764.2)
    lower = max(max(unreduced) / high1, max(reduced) / (DONE_REDUCTION * high1))
    upper = min(min(unreduced) / low1, min(reduced) / (DONE_REDUCTION * low1))
    assert lower == pytest.approx(10.32, abs=0.01)
    assert upper == pytest.approx(10.47, abs=0.01)

    modifier = _migration_value()
    assert lower <= modifier <= upper
    assert lower <= modifier * AUTO_ATTACK_BONUS <= upper

    low, high = _native_swing_range(modifier * AUTO_ATTACK_BONUS)
    assert all(low <= u <= high for u in unreduced)
    assert all(DONE_REDUCTION * low <= u <= high for u in reduced)
    mid = (low1 + high1) / 2 * modifier * AUTO_ATTACK_BONUS
    expected = (len(unreduced) * mid + len(reduced) * DONE_REDUCTION * mid) / (len(unreduced) + len(reduced))
    assert abs(statistics.mean(unreduced + reduced) - expected) / expected < 0.05
    # Scarlet Fever must be inside U: without it no single modifier fits the envelope.
    assert max(unreduced + reduced) / high1 > min(unreduced + reduced) / low1


def test_reverse_tolerates_float_storage():
    # MySQL stores DamageModifier as FLOAT; an exact "= 10.35" would never match.
    assert "ABS(`DamageModifier` - 10.35) < 0.001" in _reverse_sql()


def test_registry_patch_records_the_same_value():
    patch = json.loads(REGISTRY_PATCH.read_text(encoding="utf-8"))
    row = patch["creatures"][str(ATRAMEDES_10N)]
    assert row["status"] == "calibrated" and row["damage_modifier"] == EXPECTED_MODIFIER
    assert row["evidence"]["derivation_file"] == MIGRATION.relative_to(ROOT).as_posix()
    assert row["evidence"]["migration_state"] == "staged"
    for entry in ATRAMEDES_OTHER_MODES:
        assert str(entry) not in patch["creatures"]
