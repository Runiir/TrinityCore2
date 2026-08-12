from __future__ import annotations

from dataclasses import dataclass, replace
from math import cos, pi, sin
from typing import Any, Iterable


RAID_DIFFICULTIES = {
    "10n": (10, 0),
    "25n": (25, 1),
    "10h": (10, 2),
    "25h": (25, 3),
}


@dataclass(frozen=True)
class RaidMember:
    guid: int
    role: str
    slot: int = -1
    subgroup: int = -1
    active: bool = True
    lease_owned: bool = True


@dataclass(frozen=True)
class RaidIdentity:
    group_guid: int
    leader_guid: int
    raid_size: int
    difficulty_name: str
    difficulty_id: int
    map_id: int
    instance_id: int
    lockout_save_id: int
    server_epoch: int
    attempt_id: int


@dataclass(frozen=True)
class RaidFoundation:
    identity: RaidIdentity
    members: tuple[RaidMember, ...]
    main_tank_guid: int
    off_tank_guid: int
    third_tank_guid: int | None
    healer_guids: tuple[int, ...]
    interrupt_rotation: tuple[int, ...]
    dispel_rotation: tuple[int, ...]
    cooldown_rotation: tuple[int, ...]
    soak_groups: tuple[tuple[int, ...], ...]
    combat_resurrection_rotation: tuple[int, ...]


def form_raid(
    members: Iterable[RaidMember | dict[str, Any]],
    *,
    difficulty: str,
    group_guid: int,
    leader_guid: int,
    map_id: int,
    instance_id: int,
    lockout_save_id: int,
    server_epoch: int,
    attempt_id: int,
) -> RaidFoundation:
    if difficulty not in RAID_DIFFICULTIES:
        raise ValueError(f"raid_unknown_difficulty:{difficulty}")
    raid_size, difficulty_id = RAID_DIFFICULTIES[difficulty]
    normalized = tuple(_member(member) for member in members)
    if len(normalized) != raid_size:
        raise ValueError(f"raid_size_mismatch:expected={raid_size}:actual={len(normalized)}")

    guids = [member.guid for member in normalized]
    if any(guid <= 0 for guid in guids) or len(set(guids)) != len(guids):
        raise ValueError("raid_duplicate_or_invalid_guid")
    if any(not member.lease_owned for member in normalized):
        raise ValueError("raid_slot_lease_not_owned")
    if leader_guid not in set(guids):
        raise ValueError("raid_leader_not_in_roster")

    roster = tuple(replace(member, slot=index, subgroup=index // 5) for index, member in enumerate(normalized))
    tanks = tuple(member.guid for member in roster if member.role == "tank")
    healers = tuple(member.guid for member in roster if member.role == "healer")
    dps = tuple(member.guid for member in roster if member.role in {"dps", "melee_dps", "ranged_dps"})
    if len(tanks) < 2:
        raise ValueError("raid_missing_two_tanks")
    if not healers:
        raise ValueError("raid_missing_healer")
    if not dps:
        raise ValueError("raid_missing_dps")

    interrupt_rotation = dps + tanks
    dispel_rotation = healers + tuple(guid for guid in dps if _member_by_guid(roster, guid).role == "ranged_dps")
    cooldown_rotation = healers + tanks
    soak_groups = tuple(tuple(member.guid for member in roster if member.subgroup == subgroup) for subgroup in range(raid_size // 5))
    combat_resurrection_rotation = tuple(member.guid for member in roster if member.role in {"healer", "ranged_dps"})

    return RaidFoundation(
        identity=RaidIdentity(
            group_guid=group_guid,
            leader_guid=leader_guid,
            raid_size=raid_size,
            difficulty_name=difficulty,
            difficulty_id=difficulty_id,
            map_id=map_id,
            instance_id=instance_id,
            lockout_save_id=lockout_save_id,
            server_epoch=server_epoch,
            attempt_id=attempt_id,
        ),
        members=roster,
        main_tank_guid=tanks[0],
        off_tank_guid=tanks[1],
        third_tank_guid=tanks[2] if len(tanks) > 2 else None,
        healer_guids=healers,
        interrupt_rotation=interrupt_rotation,
        dispel_rotation=dispel_rotation,
        cooldown_rotation=cooldown_rotation,
        soak_groups=soak_groups,
        combat_resurrection_rotation=combat_resurrection_rotation,
    )


def formation_points(
    family: str,
    count: int,
    *,
    anchor_x: float = 0.0,
    anchor_y: float = 0.0,
    minimum_distance: float = 6.0,
) -> tuple[tuple[float, float], ...]:
    if count <= 0:
        raise ValueError("formation_empty")
    if minimum_distance <= 0:
        raise ValueError("formation_bad_minimum_distance")
    if family == "stack":
        return tuple((anchor_x, anchor_y) for _ in range(count))
    if family == "pair":
        return tuple((anchor_x + (index // 2) * minimum_distance, anchor_y + (index % 2) * minimum_distance) for index in range(count))
    if family == "lane":
        return tuple((anchor_x + index * minimum_distance, anchor_y) for index in range(count))
    if family == "quadrant":
        offsets = ((1, 1), (-1, 1), (-1, -1), (1, -1))
        return tuple((anchor_x + offsets[index % 4][0] * minimum_distance, anchor_y + offsets[index % 4][1] * minimum_distance) for index in range(count))
    if family in {"ring", "spread"}:
        radius = max(minimum_distance, count * minimum_distance / (2.0 * pi))
        return tuple((anchor_x + cos(2.0 * pi * index / count) * radius, anchor_y + sin(2.0 * pi * index / count) * radius) for index in range(count))
    if family == "cone":
        start = -pi / 3.0
        step = (2.0 * pi / 3.0) / max(1, count - 1)
        return tuple((anchor_x + cos(start + step * index) * minimum_distance, anchor_y + sin(start + step * index) * minimum_distance) for index in range(count))
    if family == "behind":
        return tuple((anchor_x - minimum_distance - index, anchor_y + (index - count / 2.0) * minimum_distance) for index in range(count))
    if family == "front_exclusion":
        return tuple((anchor_x, anchor_y + (index + 1) * minimum_distance) for index in range(count))
    raise ValueError(f"formation_unknown_family:{family}")


def validate_evidence_demultiplex(events: Iterable[dict[str, Any]], identity: RaidIdentity) -> int:
    observed = 0
    for event in events:
        expected = {
            "group_guid": identity.group_guid,
            "server_epoch": identity.server_epoch,
            "attempt_id": identity.attempt_id,
            "instance_id": identity.instance_id,
            "difficulty_id": identity.difficulty_id,
            "raid_size": identity.raid_size,
        }
        if any(event.get(key) != value for key, value in expected.items()):
            raise ValueError("raid_evidence_cross_attribution")
        observed += 1
    if not observed:
        raise ValueError("raid_evidence_empty")
    return observed


def _member(value: RaidMember | dict[str, Any]) -> RaidMember:
    if isinstance(value, RaidMember):
        return value
    return RaidMember(
        guid=int(value["guid"]),
        role=str(value["role"]),
        active=bool(value.get("active", True)),
        lease_owned=bool(value.get("lease_owned", True)),
    )


def _member_by_guid(members: tuple[RaidMember, ...], guid: int) -> RaidMember:
    return next(member for member in members if member.guid == guid)
