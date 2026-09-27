"""User decision 2026-09-27: the Feral tank's DPS is informational; the Blood DK tank stays gated."""
from __future__ import annotations

import json
from pathlib import Path

from tests.test_raid_scoreboard import ROOT, SCENARIO, TARGET, kill, record_all, root  # noqa: F401 (fixture)
from tools.raid_program.scoreboard_core import dps_gate_exempt_specs
from tools.raid_program.scoreboard_verdict import evaluate_target

FERAL = "30099"
BWD_TARGETS = ROOT / "experiments/configs/raid_targets"


def _add_feral(root: Path, *, exempt: bool) -> None:
    target = json.loads((root / TARGET).read_text())
    target["roster"][FERAL] = {"name": "Feral", "spec": "feral_druid_tank", "role": "tank"}
    if exempt:
        target["dps_gate_exempt_specs"] = ["feral_druid_tank"]
    (root / TARGET).write_text(json.dumps(target))


def _kills(label: str, *, blood_scale: float = 1.0) -> list[dict]:
    records = []
    for index in range(3):
        record = kill(label, f"k{index}")
        for actor in record["actors"]:
            if actor["spec"] == "blood_death_knight":
                actor["encounter_window_dps"] *= blood_scale
        record["actors"].append({"actor_id": FERAL, "name": "Feral", "spec": "feral_druid_tank", "role": "tank",
                                 "encounter_window_dps": 3000.0, "damage_uptime": 0.8, "casts_per_minute": 30.0,
                                 "hps": 0.0})
        records.append(record)
    return records


def test_exempt_feral_tank_without_a_reference_passes(root: Path) -> None:
    _add_feral(root, exempt=True)
    record_all(root, *_kills("a"))
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["status"] == "pass", verdict["reason"]
    feral = verdict["actors"][FERAL]
    assert feral["status"] == "pass" and feral["dps_gate"] == "informational"
    assert feral["reference_basis"] == "none" and feral["mean_dps"] == 3000.0  # recorded, not gated


def test_the_same_feral_tank_fails_when_it_is_not_exempt(root: Path) -> None:
    _add_feral(root, exempt=False)
    record_all(root, *_kills("a"))
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["status"] == "fail" and verdict["actors"][FERAL]["status"] == "no_reference"


def test_blood_dk_below_its_floor_still_fails(root: Path) -> None:
    _add_feral(root, exempt=True)
    record_all(root, *_kills("a", blood_scale=0.5))
    verdict = evaluate_target(root, SCENARIO, "a")
    blood = next(actor for actor in verdict["actors"].values() if actor["spec"] == "blood_death_knight")
    assert verdict["status"] == "fail" and blood["status"] == "fail" and blood["reason"] == "below_target"
    assert "dps_gate" not in blood and verdict["actors"][FERAL]["status"] == "pass"


def test_bwd_targets_declare_the_decision_and_magmaw_is_unchanged() -> None:
    for boss in ("atramedes", "chimaeron", "maloriak", "nefarian", "omnotron_defense_system"):
        target = json.loads((BWD_TARGETS / f"blackwing_descent_10n_{boss}.json").read_text())
        assert dps_gate_exempt_specs(target) == {"feral_druid_tank"}, boss
        assert target["dps_gate_exempt_decision"]["source"] == "user decision 2026-09-27"
        assert "blood_death_knight" not in dps_gate_exempt_specs(target)
    magmaw = json.loads((BWD_TARGETS / "blackwing_descent_10n_magmaw.json").read_text())
    assert "dps_gate_exempt_specs" not in magmaw  # its target hash binds the accepted verdict
    assert "feral_druid_tank" not in {row["spec"] for row in magmaw["roster"].values()}
    verdict = evaluate_target(ROOT, "blackwing_descent_10n_magmaw", "b5-d1898555")
    assert verdict["status"] == "pass" and verdict["kills"] == 8
    assert not any("dps_gate" in actor for actor in verdict["actors"].values())


# --- the exemption parser refuses anything but a tank-role Feral ---------------------------------------

import pytest  # noqa: E402

from tools.raid_program.scoreboard_core import TargetConfigError  # noqa: E402


def _set_exempt(root: Path, value) -> None:
    target = json.loads((root / TARGET).read_text())
    target["dps_gate_exempt_specs"] = value
    (root / TARGET).write_text(json.dumps(target))


@pytest.mark.parametrize("value", [["fire_mage"], ["blood_death_knight"], ["feral_druid_tank", "fire_mage"],
                                   {"feral_druid_tank": True}, "feral_druid_tank", None, ["feral_druid_tank", 5]])
def test_malformed_or_non_feral_exemptions_are_config_errors(root: Path, value) -> None:
    _add_feral(root, exempt=False)
    _set_exempt(root, value)
    record_all(root, *_kills("a"))
    with pytest.raises(TargetConfigError):
        evaluate_target(root, SCENARIO, "a")


def test_a_feral_in_a_dps_role_is_not_exempt(root: Path) -> None:
    _add_feral(root, exempt=True)
    target = json.loads((root / TARGET).read_text())
    target["roster"][FERAL]["role"] = "dps"
    (root / TARGET).write_text(json.dumps(target))
    records = _kills("a")
    for record in records:
        next(actor for actor in record["actors"] if actor["actor_id"] == FERAL)["role"] = "dps"
    record_all(root, *records)
    verdict = evaluate_target(root, SCENARIO, "a")
    feral = verdict["actors"][FERAL]
    assert verdict["status"] == "fail" and feral["status"] == "no_reference" and "dps_gate" not in feral
