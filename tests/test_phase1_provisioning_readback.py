from pathlib import Path

from tools.raid_program.capture_phase1_provisioning_readback import (
    load_materialized_readback_contract,
    validate_readback,
)
from tools.bot_ml.build_validation_provisioning import VALIDATION_FULL_STAT_SEED


ROOT = Path(__file__).resolve().parents[1]
PROVISIONING = ROOT / "experiments/configs/validation_provisioning_cata_001.json"
SCENARIOS = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
FIXTURE = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"


def _rows():
    roles = ["tank", "tank", "healer", "healer", "healer", "dps", "dps", "dps", "dps", "dps"]
    expected = []
    observed = []
    for index, role in enumerate(roles, 1):
        name = f"Bwd{index}"
        spec = f"spec_{index}"
        expected.append({"guid": 1200 + index, "name": name, "role": role, "class_spec": spec, "class": index})
        observed.append({
            "guid": 1200 + index, "account_id": 7000 + index,
            "account_registry_id": 7000 + index,
            "name": name, "role": role, "class_spec": spec,
            "class_id": index, "map_id": 669, "x": -345.872, "y": -224.344,
            "z": 193.127, "o": 0.0, "online": 0, "enabled": 1, "in_use": 0,
            "health": VALIDATION_FULL_STAT_SEED, "power1": VALIDATION_FULL_STAT_SEED,
            "character_flags": 0, "at_login": 0,
            "experiment_tags": "blackwing_descent_10n",
        })
    return expected, observed


def test_phase1_provisioning_readback_reconstructs_exact_clean_roster():
    expected, observed = _rows()
    assert validate_readback(
        expected, observed,
        start={"map_id": 669, "x": -345.872, "y": -224.344, "z": 193.127, "o": 0.0},
        character_instance_rows=0, group_member_rows=0, ghost_aura_rows=0, corpse_rows=0, corpse_phase_rows=0,
    ) == []


def test_phase1_provisioning_readback_rejects_identity_position_and_residue_drift():
    expected, observed = _rows()
    observed[-1] = {**observed[-1], "guid": 9999, "x": -300.0, "in_use": 1}
    reasons = validate_readback(
        expected, observed,
        start={"map_id": 669, "x": -345.872, "y": -224.344, "z": 193.127, "o": 0.0},
        character_instance_rows=1, group_member_rows=1, ghost_aura_rows=0, corpse_rows=0, corpse_phase_rows=0,
    )
    assert reasons == [
        "Bwd10:guid", "Bwd10:pool_state", "Bwd10:position",
        "character_instance_rows", "group_member_rows",
    ]


def test_phase1_provisioning_readback_rejects_unclamped_stat_seed():
    expected, observed = _rows()
    observed[0] = {**observed[0], "health": 100, "power1": 100}
    reasons = validate_readback(
        expected, observed,
        start={"map_id": 669, "x": -345.872, "y": -224.344, "z": 193.127, "o": 0.0},
        character_instance_rows=0, group_member_rows=0, ghost_aura_rows=0, corpse_rows=0, corpse_phase_rows=0,
    )
    assert reasons == ["Bwd1:health_seed", "Bwd1:power1_seed"]


def test_phase1_provisioning_readback_rejects_persisted_ghost_state():
    expected, observed = _rows()
    observed[0] = {**observed[0], "character_flags": 0x2000, "at_login": 0x100}
    reasons = validate_readback(
        expected, observed,
        start={"map_id": 669, "x": -345.872, "y": -224.344, "z": 193.127, "o": 0.0},
        character_instance_rows=0, group_member_rows=0, ghost_aura_rows=1, corpse_rows=1, corpse_phase_rows=1,
    )
    assert reasons == [
        "Bwd1:at_login_flags", "Bwd1:ghost_character_flag", "Bwd1:resurrect_at_login_flag",
        "corpse_phase_rows", "corpse_rows", "ghost_aura_rows",
    ]


def test_phase1_provisioning_readback_rejects_native_rename_flag():
    expected, observed = _rows()
    observed[0] = {**observed[0], "at_login": 0x1}
    reasons = validate_readback(
        expected, observed,
        start={"map_id": 669, "x": -345.872, "y": -224.344, "z": 193.127, "o": 0.0},
        character_instance_rows=0, group_member_rows=0, ghost_aura_rows=0,
        corpse_rows=0, corpse_phase_rows=0,
    )
    assert reasons == ["Bwd1:at_login_flags"]


def _materialized_observed(contract):
    rows = []
    start = contract["start"]
    for index, expected in enumerate(contract["expected"], 1):
        account_id = expected.get("expected_account_id") or 7000 + index
        rows.append({
            "guid": expected.get("guid") or expected["expected_character_guid"],
            "account_id": account_id,
            "account_registry_id": account_id,
            "account": expected["account"],
            "name": expected["name"],
            "role": expected["role"],
            "class_spec": expected["class_spec"],
            "class_id": expected["class"],
            "canonical_roster_slot_id": expected["canonical_roster_slot_id"],
            "roster_slot_id": expected["roster_slot_id"],
            "runtime_profile_id": expected["runtime_profile_id"],
            "pool_tag": expected["pool_tag"],
            "map_id": start["map_id"],
            "x": start["x"], "y": start["y"], "z": start["z"], "o": start["o"],
            "online": 0,
            "health": VALIDATION_FULL_STAT_SEED,
            "power1": VALIDATION_FULL_STAT_SEED,
            "character_flags": 0,
            "at_login": 0,
            "enabled": 1,
            "in_use": 0,
            "experiment_tags": expected["experiment_tags"],
        })
    return rows


def test_materialized_magmaw_readback_contract_is_exact_and_boss_scoped():
    contract = load_materialized_readback_contract(PROVISIONING, SCENARIOS, FIXTURE, "blackwing_descent_10n_magmaw_diagnostic")
    assert len(contract["expected"]) == 10
    assert contract["scenario_id"] == "blackwing_descent_10n_magmaw_diagnostic"
    assert all(row["pool_tag"] == contract["scenario_id"] for row in contract["expected"])
    assert all(row["runtime_profile_id"] == contract["scenario_id"] for row in contract["expected"])
    assert {row["canonical_roster_slot_id"] for row in contract["expected"]} == {
        "raid_tank_1", "raid_tank_2", "raid_healer_1", "raid_healer_2", "raid_healer_3",
        "raid_dps_1", "raid_dps_2", "raid_dps_3", "raid_dps_4", "raid_dps_5",
    }
    assert contract["shard"]["predecessor_state"]["precompleted_boss_entries"] == []


def test_materialized_canonical_readback_contract_is_positive_and_exact():
    contract = load_materialized_readback_contract(PROVISIONING, SCENARIOS, FIXTURE)
    assert len(contract["expected"]) == 10
    assert validate_readback(
        contract["expected"], _materialized_observed(contract),
        start=contract["start"],
        character_instance_rows=0, group_member_rows=0, ghost_aura_rows=0,
        corpse_rows=0, corpse_phase_rows=0,
    ) == []


def test_materialized_canonical_readback_rejects_character_to_auth_account_mismatch():
    contract = load_materialized_readback_contract(PROVISIONING, SCENARIOS, FIXTURE)
    observed = _materialized_observed(contract)
    observed[0]["account_id"] = 71001
    observed[0]["account_registry_id"] = 71002
    reasons = validate_readback(
        contract["expected"], observed,
        start=contract["start"],
        character_instance_rows=0, group_member_rows=0, ghost_aura_rows=0,
        corpse_rows=0, corpse_phase_rows=0,
    )
    assert "Bwdtanka:account_binding" in reasons


def test_materialized_readback_rejects_cross_shard_identity_contamination():
    magmaw = load_materialized_readback_contract(PROVISIONING, SCENARIOS, FIXTURE, "blackwing_descent_10n_magmaw_diagnostic")
    omnotron = load_materialized_readback_contract(PROVISIONING, SCENARIOS, FIXTURE, "blackwing_descent_10n_omnotron_diagnostic")
    observed = _materialized_observed(magmaw)
    observed[0]["experiment_tags"] = omnotron["scenario_id"]
    observed[0]["pool_tag"] = omnotron["scenario_id"]
    reasons = validate_readback(
        magmaw["expected"], observed,
        start=magmaw["start"],
        character_instance_rows=0, group_member_rows=0, ghost_aura_rows=0,
        corpse_rows=0, corpse_phase_rows=0,
    )
    assert "Mgwtanka:pool_tag" in reasons
    assert "Mgwtanka:tag" in reasons
    assert magmaw["expected"][0]["name"] != omnotron["expected"][0]["name"]
    assert magmaw["expected"][0]["guid"] != omnotron["expected"][0]["guid"]


def test_materialized_readback_rejects_cross_shard_account_name_guid_and_residue_drift():
    magmaw = load_materialized_readback_contract(PROVISIONING, SCENARIOS, FIXTURE, "blackwing_descent_10n_magmaw_diagnostic")
    omnotron = load_materialized_readback_contract(PROVISIONING, SCENARIOS, FIXTURE, "blackwing_descent_10n_omnotron_diagnostic")
    observed = _materialized_observed(magmaw)
    observed[0]["account_id"] = omnotron["expected"][0]["expected_account_id"]
    observed[0]["account_registry_id"] = omnotron["expected"][0]["expected_account_id"]
    observed[0]["account"] = omnotron["expected"][0]["account"]
    observed[0]["guid"] = omnotron["expected"][0]["guid"]
    reasons = validate_readback(
        magmaw["expected"], observed,
        start=magmaw["start"],
        character_instance_rows=0, group_member_rows=1, ghost_aura_rows=1,
        corpse_rows=0, corpse_phase_rows=1,
    )
    assert "Mgwtanka:account_id" in reasons
    assert "Mgwtanka:account_registry_id" in reasons
    assert "Mgwtanka:account" in reasons
    assert "Mgwtanka:guid" in reasons
    assert {"group_member_rows", "ghost_aura_rows", "corpse_phase_rows"}.issubset(reasons)
