from tools.raid_program.capture_phase1_provisioning_readback import validate_readback


def _rows():
    roles = ["tank", "tank", "healer", "healer", "healer", "dps", "dps", "dps", "dps", "dps"]
    expected = []
    observed = []
    for index, role in enumerate(roles, 1):
        name = f"Bwd{index}"
        spec = f"spec_{index}"
        expected.append({"guid": 1200 + index, "name": name, "role": role, "class_spec": spec, "class": index})
        observed.append({
            "guid": 1200 + index, "name": name, "role": role, "class_spec": spec,
            "class_id": index, "map_id": 669, "x": -345.872, "y": -224.344,
            "z": 193.127, "o": 0.0, "online": 0, "enabled": 1, "in_use": 0,
            "experiment_tags": "blackwing_descent_10n",
        })
    return expected, observed


def test_phase1_provisioning_readback_reconstructs_exact_clean_roster():
    expected, observed = _rows()
    assert validate_readback(
        expected, observed,
        start={"map_id": 669, "x": -345.872, "y": -224.344, "z": 193.127, "o": 0.0},
        character_instance_rows=0, group_member_rows=0,
    ) == []


def test_phase1_provisioning_readback_rejects_identity_position_and_residue_drift():
    expected, observed = _rows()
    observed[-1] = {**observed[-1], "guid": 9999, "x": -300.0, "in_use": 1}
    reasons = validate_readback(
        expected, observed,
        start={"map_id": 669, "x": -345.872, "y": -224.344, "z": 193.127, "o": 0.0},
        character_instance_rows=1, group_member_rows=1,
    )
    assert reasons == [
        "Bwd10:guid", "Bwd10:pool_state", "Bwd10:position",
        "character_instance_rows", "group_member_rows",
    ]
