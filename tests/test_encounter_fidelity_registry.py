"""Schema of the creature damage calibration registry and its ties to the staged SQL and the ledger."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools.bot_ml.live_validation_fidelity import REGISTRY_PATH, REGISTRY_SCHEMA, REGISTRY_STATUSES, load_registry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_registry(ROOT)
CREATURES = REGISTRY["creatures"]
MODES = ("10N", "25N", "10H", "25H")


def test_schema_and_method():
    assert REGISTRY["schema"] == REGISTRY_SCHEMA
    assert set(REGISTRY["statuses"]) == set(REGISTRY_STATUSES)
    assert REGISTRY["method"]["matched_stage"] == "melee_resolution.after_attacker_bonus_amount"
    assert REGISTRY["upstream_reset"]["migration"] == "sql/updates/world/4.3.4/2025_06_18_06_world.sql"
    assert (ROOT / REGISTRY["upstream_reset"]["migration"]).is_file()
    assert (ROOT / REGISTRY_PATH).is_file()


@pytest.mark.parametrize("entry", sorted(CREATURES))
def test_every_creature_row(entry):
    row = CREATURES[entry]
    assert entry.isdigit() and int(entry) > 0
    assert row["status"] in REGISTRY_STATUSES
    assert row["role"] in ("boss", "add", "trash")
    assert row["mode"] in MODES and row["raid"] and row["boss"] and row["name"]
    assert isinstance(row["base_entry"], int)
    if row["status"] == "calibrated":
        value = row["damage_modifier"]
        assert isinstance(value, (int, float)) and value > 0
        evidence = row["evidence"]
        for key in ("wcl_report", "wcl_fight", "wcl_mode", "matched_stage", "bounds", "derivation_file"):
            assert evidence.get(key), key
        assert evidence["wcl_mode"] == row["mode"]  # never borrowed from another difficulty
        assert evidence["bounds"]["lower"] <= value <= evidence["bounds"]["upper"]
        sql = (ROOT / evidence["derivation_file"]).read_text(encoding="utf-8")
        executable = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
        pattern = rf"UPDATE\s+`creature_template`\s+SET\s+`DamageModifier`\s*=\s*([0-9.]+)\s+WHERE\s+`entry`\s*=\s*{entry}\s*;"
        match = re.search(pattern, executable)
        assert match and float(match[1]) == value
        reference = row["wcl_melee_reference"]
        assert reference["stage"] == "after_attacker_bonus_amount" and reference["u_min"] < reference["u_max"]
    elif row["status"] == "open":
        assert row["damage_modifier"] is None and row["open_reason"]
    else:
        assert row["damage_modifier"] is None and row["reason"]


def test_magmaw_seed():
    magmaw = CREATURES["41570"]
    assert magmaw["status"] == "calibrated" and magmaw["damage_modifier"] == 16.0 and magmaw["role"] == "boss"
    assert magmaw["evidence"]["wcl_report"] == "MxFq7TRbvnjGY1hJ" and magmaw["evidence"]["wcl_fight"] == 22
    assert magmaw["evidence"]["derivation_file"] == "sql/custom/staged/world/2026_09_23_30_magmaw_damage_modifier.sql"
    for entry, mode in (("51101", "25N"), ("51102", "10H"), ("51103", "25H")):
        assert CREATURES[entry]["status"] == "open" and CREATURES[entry]["mode"] == mode
        assert CREATURES[entry]["base_entry"] == 41570 and CREATURES[entry]["role"] == "boss"
    for entry in ("41806", "42321", "42347", "48270", "49416"):
        assert CREATURES[entry]["status"] == "open" and CREATURES[entry]["boss"] == "magmaw"


def test_magmaw_reference_matches_the_encounter_ledger():
    magmaw = CREATURES["41570"]
    ledger = json.loads((ROOT / magmaw["ledger"]["path"]).read_text())
    value = next(row for row in ledger["values"] if row.get("key") == magmaw["ledger"]["value_key"])
    samples = value[magmaw["ledger"]["samples_field"]]
    reference = magmaw["wcl_melee_reference"]
    assert (reference["u_min"], reference["u_max"]) == (samples["unmitigated_estimate_min"], samples["unmitigated_estimate_max"])
    assert reference["landed_samples"] == samples["landed"]
