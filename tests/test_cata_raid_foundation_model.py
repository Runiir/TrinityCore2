from math import dist

import pytest

from ml.raid.foundation import (
    RaidMember,
    compile_mechanic_contract,
    form_raid,
    formation_points,
    generic_assignment_smoke,
    validate_evidence_demultiplex,
)


def roster(size: int) -> list[RaidMember]:
    healers = 3 if size == 10 else 5
    return [
        RaidMember(1001, "tank"),
        RaidMember(1002, "tank"),
        *[RaidMember(1100 + index, "healer") for index in range(healers)],
        *[RaidMember(1200 + index, "melee_dps" if index % 2 else "ranged_dps") for index in range(size - healers - 2)],
    ]


@pytest.mark.parametrize(("size", "difficulty", "difficulty_id"), [(10, "10n", 0), (10, "10h", 2), (25, "25n", 1), (25, "25h", 3)])
def test_exact_raid_identity_and_five_player_subgroups(size: int, difficulty: str, difficulty_id: int):
    runtime = form_raid(
        roster(size), difficulty=difficulty, group_guid=501, leader_guid=1001,
        map_id=669, instance_id=701, lockout_save_id=701, server_epoch=801, attempt_id=901,
    )
    assert runtime.identity.raid_size == size
    assert runtime.identity.difficulty_id == difficulty_id
    assert [member.subgroup for member in runtime.members] == [index // 5 for index in range(size)]
    assert all(len(group) == 5 for group in runtime.soak_groups)
    assert runtime.main_tank_guid == 1001
    assert runtime.off_tank_guid == 1002


def test_duplicate_and_unowned_leases_fail_closed():
    duplicate = roster(10)
    duplicate[-1] = RaidMember(duplicate[0].guid, duplicate[-1].role)
    with pytest.raises(ValueError, match="duplicate_or_invalid"):
        form_raid(duplicate, difficulty="10n", group_guid=1, leader_guid=1001, map_id=669, instance_id=2, lockout_save_id=2, server_epoch=3, attempt_id=4)

    unowned = roster(10)
    unowned[-1] = RaidMember(unowned[-1].guid, unowned[-1].role, lease_owned=False)
    with pytest.raises(ValueError, match="lease_not_owned"):
        form_raid(unowned, difficulty="10n", group_guid=1, leader_guid=1001, map_id=669, instance_id=2, lockout_save_id=2, server_epoch=3, attempt_id=4)


def test_wrong_size_or_difficulty_fails_closed():
    with pytest.raises(ValueError, match="size_mismatch"):
        form_raid(roster(10), difficulty="25n", group_guid=1, leader_guid=1001, map_id=669, instance_id=2, lockout_save_id=2, server_epoch=3, attempt_id=4)
    with pytest.raises(ValueError, match="unknown_difficulty"):
        form_raid(roster(10), difficulty="lfr", group_guid=1, leader_guid=1001, map_id=669, instance_id=2, lockout_save_id=2, server_epoch=3, attempt_id=4)


@pytest.mark.parametrize("family", ["stack", "pair", "lane", "quadrant", "ring", "spread", "cone", "behind", "front_exclusion"])
def test_declarative_formation_families_are_deterministic(family: str):
    first = formation_points(family, 5, anchor_x=10.0, anchor_y=20.0, minimum_distance=6.0)
    assert first == formation_points(family, 5, anchor_x=10.0, anchor_y=20.0, minimum_distance=6.0)
    assert len(first) == 5
    if family in {"ring", "spread", "lane"}:
        assert all(dist(first[left], first[right]) > 0 for left in range(5) for right in range(left + 1, 5))


def test_evidence_demultiplex_rejects_cross_attribution():
    runtime = form_raid(roster(10), difficulty="10n", group_guid=501, leader_guid=1001, map_id=669, instance_id=701, lockout_save_id=701, server_epoch=801, attempt_id=901)
    event = {
        "group_guid": 501, "server_epoch": 801, "attempt_id": 901,
        "instance_id": 701, "difficulty_id": 0, "raid_size": 10,
    }
    assert validate_evidence_demultiplex([event, event], runtime.identity) == 2
    with pytest.raises(ValueError, match="cross_attribution"):
        validate_evidence_demultiplex([{**event, "attempt_id": 902}], runtime.identity)


def mechanic_payload(**overrides) -> dict:
    payload = {
        "strategy_id": "synthetic_phase1",
        "formation": "quadrant",
        "anchor_scope": "subgroup",
        "minimum_distance": 6.0,
        "tank_swap_trigger": "debuff_stacks",
        "target_control": "do_not_damage",
        "interrupt_backup": True,
        "dispel_backup": True,
        "healer_ownership": "tank_and_subgroup",
        "cooldown_schedule": "external_then_raid",
        "soak_policy": "subgroup_rotation",
        "immunity_policy": "assigned_only",
        "personal_cooldown_policy": "assigned_or_emergency",
        "battle_resurrection_policy": "tank_then_healer_then_dps",
        "interaction_kind": "extra_action",
        "movement_link": "cross_platform",
        "platform_policy": "altitude",
        "recovery_policy": "release_resurrect_runback_ready_check",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("trigger", ["debuff_stacks", "timer", "boss_cast", "add_spawn", "phase_transition"])
@pytest.mark.parametrize("target_control", ["focus_fire", "multidot", "do_not_damage", "controlled_aoe", "kill_synchronization"])
def test_generic_assignment_contract_covers_trigger_and_target_families(trigger: str, target_control: str):
    runtime = form_raid(
        roster(10), difficulty="10n", group_guid=501, leader_guid=1001,
        map_id=669, instance_id=701, lockout_save_id=701, server_epoch=801, attempt_id=901,
    )
    contract = compile_mechanic_contract(mechanic_payload(tank_swap_trigger=trigger, target_control=target_control))
    events = generic_assignment_smoke(runtime, contract, assignment_generation=2)
    assert len(events) == 10
    assert {event["slot"] for event in events} == set(range(10))
    assert {event["subgroup"] for event in events} == {0, 1}
    assert {event["tank_swap_trigger"] for event in events} == {trigger}
    assert {event["target_control"] for event in events} == {target_control}
    assert all(event["interrupt_primary"] and event["interrupt_backup"] for event in events)
    assert all(event["dispel_primary"] and event["dispel_backup"] for event in events)


@pytest.mark.parametrize("anchor_scope", ["raid", "role", "subgroup"])
@pytest.mark.parametrize("interaction_kind", ["none", "object", "extra_action", "vehicle", "transport", "jump_pad"])
@pytest.mark.parametrize("platform_policy", ["ground", "platform", "altitude", "flying"])
def test_assignment_smoke_covers_anchor_interaction_and_platform_contracts(
    anchor_scope: str, interaction_kind: str, platform_policy: str
):
    runtime = form_raid(
        roster(10), difficulty="10h", group_guid=501, leader_guid=1001,
        map_id=669, instance_id=701, lockout_save_id=701, server_epoch=801, attempt_id=901,
    )
    contract = compile_mechanic_contract(
        mechanic_payload(anchor_scope=anchor_scope, interaction_kind=interaction_kind, platform_policy=platform_policy)
    )
    events = generic_assignment_smoke(runtime, contract, assignment_generation=4)
    assert {event["interaction_kind"] for event in events} == {interaction_kind}
    assert {event["platform_policy"] for event in events} == {platform_policy}
    assert all(event["assignment_generation"] == 4 for event in events)
    assert all(event["recovery_policy"].endswith("ready_check") for event in events)


def test_contract_rejects_unknown_missing_and_bad_fields():
    with pytest.raises(ValueError, match="unknown_fields"):
        compile_mechanic_contract({**mechanic_payload(), "boss_name_switch": "magmaw"})
    missing = mechanic_payload()
    missing.pop("target_control")
    with pytest.raises(ValueError, match="missing_fields"):
        compile_mechanic_contract(missing)
    with pytest.raises(ValueError, match="unknown_formation"):
        compile_mechanic_contract(mechanic_payload(formation="teleport_to_safety"))
    with pytest.raises(ValueError, match="bad_minimum_distance"):
        compile_mechanic_contract(mechanic_payload(minimum_distance=0))
    with pytest.raises(ValueError, match="non_boolean:interrupt_backup"):
        compile_mechanic_contract(mechanic_payload(interrupt_backup="false"))


def test_assignment_generation_and_membership_fail_closed():
    runtime = form_raid(
        roster(10), difficulty="10n", group_guid=501, leader_guid=1001,
        map_id=669, instance_id=701, lockout_save_id=701, server_epoch=801, attempt_id=901,
    )
    contract = compile_mechanic_contract(mechanic_payload())
    with pytest.raises(ValueError, match="generation_invalid"):
        generic_assignment_smoke(runtime, contract, assignment_generation=0)
