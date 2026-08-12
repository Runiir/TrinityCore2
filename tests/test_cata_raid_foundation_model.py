from math import dist

import pytest

from ml.raid.foundation import RaidMember, form_raid, formation_points, validate_evidence_demultiplex


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
