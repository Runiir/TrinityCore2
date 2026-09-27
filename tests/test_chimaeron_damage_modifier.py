"""Static checks for the staged Chimaeron 10N DamageModifier migration.

The migration is replayed against an in-memory SQLite copy of the Chimaeron
creature_template rows (TDB 4.3.4 snapshot plus the upstream DamageModifier
reset), covering the forward UPDATE, its idempotence and the reverse block.

The calibration arithmetic is pinned against the matched-stage WCL sample
(report MxFq7TRbvnjGY1hJ fight 27, 10N), retained in chimaeron_ledger_v1.json.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/staged/world/2026_09_27_00_chimaeron_damage_modifier.sql"
LEDGER = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/chimaeron_ledger_v1.json"
REGISTRY_PATCH = (ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/"
                  "chimaeron_damage_calibration_registry_patch_v1.json")

CHIMAERON_10N = 43296
CHIMAERON_OTHER_MODES = (47774, 47775, 47776)  # 25N, 10H, 25H: open, untouched
EXPECTED_MODIFIER = 20.0

# (entry, DamageModifier, BaseAttackTime, difficulty_entry_1..3).
ROWS = (
    (CHIMAERON_10N, 1.0, 4000, 47774, 47775, 47776),
    (47774, 1.0, 2000, 0, 0, 0),
    (47775, 1.0, 2000, 0, 0, 0),
    (47776, 1.0, 2000, 0, 0, 0),
    (41570, 16.0, 2500, 51101, 51102, 51103),  # Magmaw 10N: accepted value stays
)

BASE_DAMAGE_88_WARRIOR_EXP3 = 2947.9421
ATTACK_POWER_88_WARRIOR = 1226
ATTACK_TIME_S = 4.0
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
    melee = next(value for value in ledger["values"] if value["key"] == "boss_melee")
    return melee["wcl_10N_samples"]


def test_executable_sql_is_one_update_of_the_10n_template():
    executable = _executable()
    assert "DELETE" not in executable.upper() and "INSERT" not in executable.upper()
    assert len([s for s in executable.split(";") if s.strip()]) == 1
    match = FORWARD.search(executable)
    assert int(match["entry"]) == CHIMAERON_10N
    assert _migration_value() == EXPECTED_MODIFIER


def test_forward_is_scoped_and_idempotent():
    db = _database()
    before = _state(db)
    db.executescript(_sql())
    first = _state(db)
    db.executescript(_sql())
    assert _state(db) == first
    assert _modifier(db, CHIMAERON_10N) == EXPECTED_MODIFIER
    assert [r for r in first if r[0] != CHIMAERON_10N] == [r for r in before if r[0] != CHIMAERON_10N]
    for entry in CHIMAERON_OTHER_MODES:
        assert _modifier(db, entry) == 1.0
    assert _modifier(db, 41570) == 16.0


def test_reverse_restores_and_does_not_clobber_a_retune():
    db = _database()
    before = _state(db)
    db.executescript(_sql())
    db.executescript(_reverse_sql())
    assert _state(db) == before
    db.executescript(_sql())
    db.execute("UPDATE creature_template SET DamageModifier = 19.5 WHERE entry = ?", (CHIMAERON_10N,))
    db.executescript(_reverse_sql())
    assert _modifier(db, CHIMAERON_10N) == 19.5


def test_modifier_fits_the_matched_wcl_envelope():
    samples = _wcl_samples()
    assert samples["report"] == "MxFq7TRbvnjGY1hJ" and samples["fight"] == 27 and samples["mode"] == "10N"
    rows = samples["landed"]
    unreduced = [row["u"] for row in rows if not row["done_reduction_aura"]]
    reduced = [row["u"] for row in rows if row["done_reduction_aura"]]
    assert (len(unreduced), len(reduced)) == (10, 7)

    low1, high1 = _native_swing_range(1.0)
    assert (round(low1, 1), round(high1, 1)) == (12142.1, 18037.9)
    # A reduced row bounds the multiplier against the reduced (-10%) envelope, not the native one.
    lower = max(max(unreduced) / high1, max(reduced) / (DONE_REDUCTION * high1))
    upper = min(min(unreduced) / low1, min(reduced) / (DONE_REDUCTION * low1))
    assert lower == pytest.approx(19.3757, abs=1e-4)  # set by the largest reduced row, 314,547
    assert upper == pytest.approx(20.88, abs=0.01)
    assert lower / AUTO_ATTACK_BONUS == pytest.approx(19.1838, abs=1e-4)

    modifier = _migration_value()
    assert lower <= modifier * AUTO_ATTACK_BONUS <= upper

    low, high = _native_swing_range(modifier * AUTO_ATTACK_BONUS)
    assert all(low <= u <= high for u in unreduced)
    assert all(DONE_REDUCTION * low <= u <= DONE_REDUCTION * high for u in reduced)
    mean_ratio = statistics.mean(unreduced) / ((low1 + high1) / 2 * AUTO_ATTACK_BONUS)
    assert abs(mean_ratio - modifier) / modifier < 0.05


def test_registry_patch_records_the_same_value():
    patch = json.loads(REGISTRY_PATCH.read_text(encoding="utf-8"))
    row = patch["creatures"][str(CHIMAERON_10N)]
    assert row["status"] == "calibrated" and row["damage_modifier"] == EXPECTED_MODIFIER
    assert row["evidence"]["derivation_file"] == MIGRATION.relative_to(ROOT).as_posix()
    assert row["evidence"]["migration_state"] == "staged"
    for entry in CHIMAERON_OTHER_MODES:
        assert str(entry) not in patch["creatures"]
