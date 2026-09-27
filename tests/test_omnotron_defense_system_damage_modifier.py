"""Static checks for the Omnotron Defense System 10N DamageModifier migration (under
sql/custom/world, applied by the worldserver DB updater at startup).

The SQL is replayed against an in-memory SQLite copy of the construct
templates (every one at DamageModifier 1 after the upstream reset). The
calibration arithmetic is pinned to the matched 10N WCL envelope. That
envelope was read on 2026-09-27 from three kills: MxFq7TRbvnjGY1hJ fight 24,
Y8ajQ7dbmKMG1RZy fight 24 and xAhkN2y9YP3KRmnJ fight 12.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_27_23_omnotron_defense_system_damage_modifier.sql"
PATCH = ROOT / ("experiments/configs/cata_raid_encounters/blackwing_descent/"
                "omnotron_defense_system_damage_calibration_registry_patch_v1.json")
LEDGER = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/omnotron_defense_system_ledger_v1.json"

CONSTRUCTS_10N = (42166, 42178, 42179, 42180)
OTHER_MODES = tuple(range(49047, 49059))  # 25N/10H/25H construct templates: open, untouched
EXPECTED = 11.2
AUTO_ATTACK_BONUS = 1.01  # Unit::MeleeDamageBonusDone adds 1% to auto-attacks
DONE_REDUCTION = 0.9  # Scarlet Fever / Vindication (Demoralizing Roar/Shout, Curse of Weakness absent)

# Native inputs: gt_npc_damage_by_class_exp3[88] (unit_class 4), creature_classlevelstats(88, 4)
# attackpower 920, BaseVariance 1, BaseAttackTime 1500.
BASE_DAMAGE = 2947.9421
ATTACK_POWER = 920
ATTACK_TIME_S = 1.5

# Matched-stage WCL U (Power Generator windows excluded).
WCL_UNREDUCED_MAX = 75687  # Magmatron, MxFq 1:27.56
WCL_UNREDUCED_MIN = 51220  # Toxitron, xAhk 0:03.97 (Scarlet Fever from 0:06.4)
WCL_REDUCED_MIN = 46798  # Magmatron, MxFq 0:05.33 under Scarlet Fever
WCL_UNREDUCED_EQUIVALENT_MEAN = 63254

FORWARD = re.compile(
    r"UPDATE\s+`creature_template`\s+SET\s+`DamageModifier`\s*=\s*(?P<value>[0-9.]+)\s+"
    r"WHERE\s+`entry`\s*=\s*(?P<entry>\d+)\s*;")


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _executable() -> str:
    return "\n".join(line for line in _sql().splitlines() if not line.lstrip().startswith("--"))


def _reverse_sql() -> str:
    lines = _sql().splitlines()
    block = lines[lines.index("-- BEGIN REVERSE MIGRATION") + 1: lines.index("-- END REVERSE MIGRATION")]
    assert block and all(line.startswith("-- ") for line in block)
    return "\n".join(line[3:] for line in block)


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE creature_template (entry INTEGER PRIMARY KEY, DamageModifier REAL NOT NULL,"
               " BaseAttackTime INTEGER NOT NULL)")
    db.executemany("INSERT INTO creature_template VALUES (?, 1.0, 1500)", [(e,) for e in CONSTRUCTS_10N])
    db.executemany("INSERT INTO creature_template VALUES (?, 1.0, 2000)", [(e,) for e in OTHER_MODES])
    db.execute("INSERT INTO creature_template VALUES (42186, 1.0, 2000)")  # controller
    return db


def _state(db: sqlite3.Connection) -> list[tuple]:
    return db.execute("SELECT * FROM creature_template ORDER BY entry").fetchall()


def _native_range(modifier: float) -> tuple[float, float]:
    ap_term = ATTACK_POWER / 14.0
    return ((BASE_DAMAGE + ap_term) * ATTACK_TIME_S * modifier,
            (BASE_DAMAGE * 1.5 + ap_term) * ATTACK_TIME_S * modifier)


def test_file_is_applied_under_sql_custom_world() -> None:
    assert MIGRATION.parent == ROOT / "sql/custom/world"
    assert [path.name for path in (ROOT / "sql/custom/world").glob("*omnotron*")] == [MIGRATION.name]
    assert not list((ROOT / "sql/custom/staged/world").glob("*omnotron*"))


def test_forward_updates_exactly_the_four_10n_constructs() -> None:
    executable = _executable()
    assert "DELETE" not in executable.upper() and "INSERT" not in executable.upper()
    matches = FORWARD.findall(executable)
    assert sorted(int(entry) for _, entry in matches) == list(CONSTRUCTS_10N)
    assert {float(value) for value, _ in matches} == {EXPECTED}
    assert len([s for s in executable.split(";") if s.strip()]) == 4


def test_forward_is_idempotent_and_reverse_restores() -> None:
    db = _database()
    before = _state(db)
    db.executescript(_sql())
    after = _state(db)
    db.executescript(_sql())
    assert _state(db) == after
    changed = {row[0] for row in after if row not in before}
    assert changed == set(CONSTRUCTS_10N)
    db.executescript(_reverse_sql())
    assert _state(db) == before
    # A later re-tune is not clobbered by this reverse.
    db.executescript(_sql())
    db.execute("UPDATE creature_template SET DamageModifier = 10.5 WHERE entry = 42166")
    db.executescript(_reverse_sql())
    assert db.execute("SELECT DamageModifier FROM creature_template WHERE entry = 42166").fetchone()[0] == 10.5


def test_modifier_reproduces_the_matched_wcl_envelope() -> None:
    low1, high1 = _native_range(1.0)
    assert (round(low1, 1), round(high1, 1)) == (4520.5, 6731.4)
    lower = WCL_UNREDUCED_MAX / high1
    upper = min(WCL_UNREDUCED_MIN / low1, WCL_REDUCED_MIN / (DONE_REDUCTION * low1))
    assert lower == pytest.approx(11.244, abs=0.001)
    assert upper == pytest.approx(11.331, abs=0.001)
    effective = EXPECTED * AUTO_ATTACK_BONUS
    assert lower <= effective <= upper
    low, high = _native_range(effective)
    mean = (low + high) / 2
    assert abs(mean / WCL_UNREDUCED_EQUIVALENT_MEAN - 1) < 0.02
    header = _sql().split("UPDATE", 1)[0]
    for citation in ("MxFq7TRbvnjGY1hJ", "Y8ajQ7dbmKMG1RZy", "xAhkN2y9YP3KRmnJ", "75,687", "51,220", "46,798"):
        assert citation in header


def test_ledger_samples_bind_the_derivation() -> None:
    values = {row["key"]: row for row in json.loads(LEDGER.read_text(encoding="utf-8"))["values"]}
    samples = values["construct_melee_native_roll_10n"]["wcl_10N_samples"]
    assert samples["unreduced"]["max"] == WCL_UNREDUCED_MAX
    assert samples["unreduced"]["min"] == WCL_UNREDUCED_MIN
    assert samples["under_attacker_minus_10pct"]["min"] == WCL_REDUCED_MIN
    assert samples["unmitigated_estimate_min"] < samples["unmitigated_estimate_max"]
    assert set(samples["per_construct"]) == {str(e) for e in CONSTRUCTS_10N}


def test_registry_patch_rows_satisfy_the_registry_contract() -> None:
    """The four patch rows pass the checks test_encounter_fidelity_registry applies to calibrated rows."""
    creatures = json.loads(PATCH.read_text(encoding="utf-8"))["creatures"]
    executable = _executable()
    for entry in CONSTRUCTS_10N:
        row = creatures[str(entry)]
        assert row["status"] == "calibrated" and row["damage_modifier"] == EXPECTED and row["mode"] == "10N"
        evidence = row["evidence"]
        for key in ("wcl_report", "wcl_fight", "wcl_mode", "matched_stage", "bounds", "derivation_file"):
            assert evidence.get(key), key
        assert evidence["wcl_mode"] == "10N"
        assert evidence["bounds"]["lower"] <= EXPECTED <= evidence["bounds"]["upper"]
        assert (ROOT / evidence["derivation_file"]) == MIGRATION
        pattern = rf"UPDATE\s+`creature_template`\s+SET\s+`DamageModifier`\s*=\s*([0-9.]+)\s+WHERE\s+`entry`\s*=\s*{entry}\s*;"
        match = re.search(pattern, executable)
        assert match and float(match[1]) == EXPECTED
        reference = row["wcl_melee_reference"]
        assert reference["stage"] == "after_attacker_bonus_amount" and reference["u_min"] < reference["u_max"]
        # Each construct's own envelope fits the native roll at the effective multiplier,
        # allowing for the -10% done auras in its sample.
        low, high = _native_range(EXPECTED * AUTO_ATTACK_BONUS)
        assert reference["u_max"] <= high and reference["u_min"] >= DONE_REDUCTION * low
    for entry in OTHER_MODES:
        assert creatures[str(entry)]["status"] == "open" and creatures[str(entry)]["damage_modifier"] is None
