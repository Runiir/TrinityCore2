"""Static checks for the staged Nefarian and Onyxia 10N DamageModifier migrations.

Each migration is replayed against an in-memory SQLite copy of the relevant
creature_template rows (all at the upstream DamageModifier 1), exercising the
forward UPDATE, idempotence and the documented reverse block without MySQL.
The calibration is pinned to the retained WCL U samples
(nefarian_wcl_melee_samples_v1.json, three 10N kills): the chosen value, after
the native +1% auto-attack bonus, must sit inside the registry-method bounds.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
STAGED = ROOT / "sql/custom/staged/world"
SAMPLES = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_wcl_melee_samples_v1.json"

MIGRATIONS = {
    41376: (STAGED / "2026_09_27_00_nefarian_damage_modifier.sql", 12.75, "Nefarian", (51104, 51105, 51106)),
    41270: (STAGED / "2026_09_27_01_nefarian_onyxia_damage_modifier.sql", 10.34375, "Onyxia", (51116, 51117, 51118)),
}

# Native per-swing roll at DamageModifier 1: gt_npc_damage_by_class_exp3[88].Warrior,
# creature_classlevelstats(88, 1) attack power 1226, BaseVariance 1, BaseAttackTime 1.5 s.
BASE = 2947.94
AP_TERM = 1226 / 14 * 1.0
ATTACK_TIME_S = 1.5
NATIVE_MIN = (BASE + AP_TERM) * ATTACK_TIME_S
NATIVE_MAX = (BASE * 1.5 + AP_TERM) * ATTACK_TIME_S
AUTO_ATTACK_BONUS = 1.01
DONE_REDUCTION = 0.9

FORWARD = re.compile(
    r"UPDATE\s+`creature_template`\s+SET\s+`DamageModifier`\s*=\s*(?P<value>[0-9.]+)\s+"
    r"WHERE\s+`entry`\s*=\s*(?P<entry>\d+)\s*;"
)


def _executable(path: Path) -> str:
    return "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("--"))


def _reverse(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    block = text.split("-- BEGIN REVERSE MIGRATION", 1)[1].split("-- END REVERSE MIGRATION", 1)[0]
    return "\n".join(line.lstrip("- ").rstrip() for line in block.splitlines() if line.strip())


def _db(entries) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE creature_template (entry INTEGER PRIMARY KEY, DamageModifier REAL)")
    db.executemany("INSERT INTO creature_template VALUES (?, 1.0)", [(entry,) for entry in entries])
    return db


def _value(db, entry) -> float:
    return db.execute("SELECT DamageModifier FROM creature_template WHERE entry = ?", (entry,)).fetchone()[0]


def test_native_roll_matches_registry() -> None:
    assert round(NATIVE_MIN, 1) == 4553.3
    assert round(NATIVE_MAX, 1) == 6764.2


@pytest.mark.parametrize("entry", sorted(MIGRATIONS))
def test_forward_idempotent_and_reverse(entry: int) -> None:
    path, expected, _, other_modes = MIGRATIONS[entry]
    statements = FORWARD.findall(_executable(path))
    assert [(float(value), int(target)) for value, target in statements] == [(expected, entry)]
    db = _db((entry, *other_modes))
    sql = _executable(path).replace("`", "")
    db.executescript(sql)
    db.executescript(sql)
    assert _value(db, entry) == expected
    assert all(_value(db, other) == 1.0 for other in other_modes)
    db.executescript(_reverse(path).replace("`", ""))
    assert _value(db, entry) == 1.0


@pytest.mark.parametrize("entry", sorted(MIGRATIONS))
def test_value_inside_wcl_bounds(entry: int) -> None:
    _, modifier, source, _ = MIGRATIONS[entry]
    data = json.loads(SAMPLES.read_text(encoding="utf-8"))
    index = {name: i for i, name in enumerate(data["columns"])}
    rows = [row for row in data["samples"] if row[index["source"]] == source and row[index["U"]]]
    reduced = [row[index["U"]] for row in rows if row[index["attacker_minus_10pct_aura"]]]
    unreduced = [row[index["U"]] for row in rows if not row[index["attacker_minus_10pct_aura"]]]
    lower = max(max(reduced) / (DONE_REDUCTION * NATIVE_MAX), max(unreduced) / NATIVE_MAX if unreduced else 0.0)
    upper = min(min(reduced) / (DONE_REDUCTION * NATIVE_MIN), min(unreduced) / NATIVE_MIN if unreduced else 1e9)
    effective = modifier * AUTO_ATTACK_BONUS
    assert lower <= effective <= upper, (source, lower, effective, upper)
    summary = data["summary"][source]
    assert summary["landed_with_u"] == len(rows)
    assert summary["bounds_on_effective_multiplier"] == {"lower": round(lower, 3), "upper": round(upper, 3)}


REGISTRY = ROOT / "experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json"


@pytest.mark.parametrize("entry", sorted(MIGRATIONS))
def test_registry_row_matches_migration_once_calibrated(entry: int) -> None:
    """The registry row is applied by the coordinator; once calibrated it must name this migration."""
    path, expected, _, _ = MIGRATIONS[entry]
    row = json.loads(REGISTRY.read_text(encoding="utf-8"))["creatures"][str(entry)]
    if row["status"] != "calibrated":
        pytest.skip("registry patch not applied yet")
    assert row["damage_modifier"] == expected
    assert row["evidence"]["derivation_file"] == path.relative_to(ROOT).as_posix()
    assert row["evidence"]["migration_state"] == "staged"
    assert row["evidence"]["wcl_mode"] == "10N"
