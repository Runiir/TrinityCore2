from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import cos, hypot, pi, sin
from typing import Any, Iterable


RAID_DIFFICULTIES = {
    "10n": (10, 0),
    "25n": (25, 1),
    "10h": (10, 2),
    "25h": (25, 3),
}

FORMATION_FAMILIES = frozenset({"stack", "pair", "lane", "quadrant", "ring", "spread", "cone", "behind", "front_exclusion"})
ANCHOR_SCOPES = frozenset({"raid", "role", "subgroup"})
TANK_SWAP_TRIGGERS = frozenset({"debuff_stacks", "timer", "boss_cast", "add_spawn", "phase_transition"})
TARGET_CONTROLS = frozenset({"focus_fire", "multidot", "do_not_damage", "controlled_aoe", "kill_synchronization"})
INTERACTION_KINDS = frozenset({"none", "object", "extra_action", "vehicle", "transport", "jump_pad"})
MOVEMENT_LINKS = frozenset({"none", "encounter_link", "cross_platform"})
PLATFORM_POLICIES = frozenset({"ground", "platform", "altitude", "flying"})
RECOVERY_POLICIES = frozenset({"release_resurrect_runback_ready_check", "raid_entrance_teleporter_ready_check"})


@dataclass(frozen=True)
class DeclarativeMechanicContract:
    strategy_id: str
    formation: str
    anchor_scope: str
    minimum_distance: float
    tank_swap_trigger: str
    target_control: str
    interrupt_backup: bool | None
    dispel_backup: bool | None
    healer_ownership: str
    cooldown_schedule: str
    soak_policy: str
    immunity_policy: str
    personal_cooldown_policy: str
    battle_resurrection_policy: str
    interaction_kind: str
    movement_link: str
    platform_policy: str
    recovery_policy: str


MECHANIC_CONTRACT_FIELDS = frozenset(DeclarativeMechanicContract.__dataclass_fields__)


@dataclass(frozen=True)
class RaidMember:
    guid: int
    role: str
    slot: int = -1
    subgroup: int = -1
    active: bool = True
    lease_owned: bool = True
    roster_slot_id: str | None = None


@dataclass(frozen=True)
class SavedRaidPlacement:
    guid: int
    map_id: int
    x: float
    y: float
    z: float


@dataclass
class ValidationRaidAdmissionState:
    bots: list[int] = field(default_factory=list)
    leases: set[int] = field(default_factory=set)
    group_guid: int | None = None
    pinned_guids: tuple[int, ...] = ()
    complete: bool = False
    terminal_failure: bool = False


def preflight_validation_raid_spawn(
    planned_guids: Iterable[int],
    saved_placements: Iterable[SavedRaidPlacement],
    *,
    route_start_map_id: int,
    route_start_x: float,
    route_start_y: float,
    route_start_z: float,
    horizontal_tolerance_yards: float = 5.0,
    vertical_tolerance_yards: float = 3.0,
) -> tuple[SavedRaidPlacement, ...]:
    """Validate the complete immutable raid spawn plan without side effects."""
    guids = tuple(planned_guids)
    placements = tuple(saved_placements)
    if not guids or any(guid <= 0 for guid in guids) or len(set(guids)) != len(guids):
        raise ValueError("validation_raid_preflight_roster_not_unique")
    if route_start_map_id <= 0 or horizontal_tolerance_yards <= 0 or vertical_tolerance_yards <= 0:
        raise ValueError("validation_raid_preflight_route_start_invalid")

    by_guid = {placement.guid: placement for placement in placements}
    if len(by_guid) != len(placements) or set(by_guid) != set(guids):
        raise ValueError("validation_raid_preflight_saved_placement_missing")
    for guid in guids:
        placement = by_guid[guid]
        if (
            placement.map_id != route_start_map_id
            or hypot(placement.x - route_start_x, placement.y - route_start_y)
            > horizontal_tolerance_yards
            or abs(placement.z - route_start_z) > vertical_tolerance_yards
        ):
            raise ValueError("validation_raid_preflight_route_start_mismatch")
    return tuple(by_guid[guid] for guid in guids)


def transact_validation_raid_admission(
    planned_guids: Iterable[int],
    saved_placements: Iterable[SavedRaidPlacement],
    *,
    route_start_map_id: int,
    route_start_x: float,
    route_start_y: float,
    route_start_z: float,
    state: ValidationRaidAdmissionState,
    fail_claim_at: int | None = None,
    fail_spawn_at: int | None = None,
) -> ValidationRaidAdmissionState:
    """Model the one-shot all-or-nothing runtime admission transaction."""
    if state.terminal_failure:
        raise ValueError("validation_raid_admission_terminal_failure")
    if state.complete:
        return state
    if state.bots or state.leases or state.group_guid is not None:
        state.bots.clear()
        state.leases.clear()
        state.group_guid = None
        state.pinned_guids = ()
        state.terminal_failure = True
        raise ValueError("validation_raid_admission_nonempty_start")

    placements = preflight_validation_raid_spawn(
        planned_guids,
        saved_placements,
        route_start_map_id=route_start_map_id,
        route_start_x=route_start_x,
        route_start_y=route_start_y,
        route_start_z=route_start_z,
    )
    state.pinned_guids = tuple(placement.guid for placement in placements)
    try:
        for index, placement in enumerate(placements):
            if fail_claim_at == index:
                raise ValueError("validation_raid_admission_claim_failed")
            state.leases.add(placement.guid)
            if fail_spawn_at == index:
                raise ValueError("validation_raid_admission_spawn_failed")
            state.bots.append(placement.guid)
            state.group_guid = 1
    except ValueError:
        state.bots.clear()
        state.leases.clear()
        state.group_guid = None
        state.terminal_failure = True
        raise

    state.complete = True
    return state


def validate_completed_validation_raid_admission(
    expected_guids: Iterable[int], state: ValidationRaidAdmissionState
) -> ValidationRaidAdmissionState:
    expected = tuple(expected_guids)
    exact = (
        state.complete
        and not state.terminal_failure
        and tuple(state.bots) == expected
        and state.leases == set(expected)
        and state.group_guid is not None
        and state.pinned_guids == expected
    )
    if exact:
        return state
    state.bots.clear()
    state.leases.clear()
    state.group_guid = None
    state.complete = False
    state.terminal_failure = True
    raise ValueError("validation_raid_admission_identity_drift")


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
    strategy_id: str = "foundation"


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
    strategy_id: str = "foundation",
) -> RaidFoundation:
    if difficulty not in RAID_DIFFICULTIES:
        raise ValueError(f"raid_unknown_difficulty:{difficulty}")
    normalized_strategy_id = str(strategy_id).strip()
    if not normalized_strategy_id:
        raise ValueError("raid_empty_strategy_id")
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

    roster_slot_ids = [member.roster_slot_id for member in normalized]
    if any(slot_id is not None and not str(slot_id).strip() for slot_id in roster_slot_ids):
        raise ValueError("raid_empty_roster_slot_id")
    if len({slot_id for slot_id in roster_slot_ids if slot_id is not None}) != sum(slot_id is not None for slot_id in roster_slot_ids):
        raise ValueError("raid_duplicate_roster_slot_id")
    roster = tuple(
        replace(
            member,
            slot=index,
            subgroup=index // 5,
            roster_slot_id=member.roster_slot_id or f"raid-slot-{index:02d}",
        )
        for index, member in enumerate(normalized)
    )
    tanks = tuple(member.guid for member in roster if member.role == "tank")
    healers = tuple(member.guid for member in roster if member.role == "healer")
    dps = tuple(member.guid for member in roster if member.role in {"dps", "melee_dps", "ranged_dps"})
    if len(tanks) < 2:
        raise ValueError("raid_missing_two_tanks")
    if not healers:
        raise ValueError("raid_missing_healer")
    if not dps:
        raise ValueError("raid_missing_dps")
    if raid_size == 10 and (len(tanks), len(healers), len(dps)) != (2, 3, 5):
        raise ValueError("raid_10n_composition_mismatch")

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
            strategy_id=normalized_strategy_id,
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
        # Keep the assignments in distinct quadrants while expanding the ring
        # radius enough that a fifth (or later) member never overlaps the
        # first four.  The old modulo-four layout silently produced a zero
        # distance for five-player subgroups.
        radius = minimum_distance / (2.0 * sin(pi / count)) if count > 1 else minimum_distance
        return tuple(
            (
                anchor_x + cos(pi / 4.0 + 2.0 * pi * index / count) * radius,
                anchor_y + sin(pi / 4.0 + 2.0 * pi * index / count) * radius,
            )
            for index in range(count)
        )
    if family in {"ring", "spread"}:
        radius = minimum_distance / (2.0 * sin(pi / count)) if count > 1 else minimum_distance
        return tuple((anchor_x + cos(2.0 * pi * index / count) * radius, anchor_y + sin(2.0 * pi * index / count) * radius) for index in range(count))
    if family == "cone":
        start = -pi / 3.0
        step = (2.0 * pi / 3.0) / max(1, count - 1)
        radius = minimum_distance / (2.0 * sin(step / 2.0)) if count > 1 else minimum_distance
        return tuple((anchor_x + cos(start + step * index) * radius, anchor_y + sin(start + step * index) * radius) for index in range(count))
    if family == "behind":
        return tuple((anchor_x - minimum_distance - index, anchor_y + (index - count / 2.0) * minimum_distance) for index in range(count))
    if family == "front_exclusion":
        return tuple((anchor_x, anchor_y + (index + 1) * minimum_distance) for index in range(count))
    raise ValueError(f"formation_unknown_family:{family}")


def compile_mechanic_contract(
    payload: dict[str, Any], *, allow_undeclared: bool = False
) -> DeclarativeMechanicContract:
    supplied = frozenset(payload)
    missing = sorted(MECHANIC_CONTRACT_FIELDS - supplied)
    unknown = sorted(supplied - MECHANIC_CONTRACT_FIELDS)
    if missing and not allow_undeclared:
        raise ValueError(f"mechanic_contract_missing_fields:{','.join(missing)}")
    if unknown:
        raise ValueError(f"mechanic_contract_unknown_fields:{','.join(unknown)}")

    strategy_id = str(payload["strategy_id"]).strip()
    if not strategy_id:
        raise ValueError("mechanic_contract_empty_strategy_id")
    formation = _choice("formation", payload["formation"], FORMATION_FAMILIES)
    anchor_scope = "not_declared" if allow_undeclared and "anchor_scope" not in payload else _choice("anchor_scope", payload["anchor_scope"], ANCHOR_SCOPES)
    tank_swap_trigger = "not_declared" if allow_undeclared and "tank_swap_trigger" not in payload else _choice("tank_swap_trigger", payload["tank_swap_trigger"], TANK_SWAP_TRIGGERS)
    target_control = _choice("target_control", payload["target_control"], TARGET_CONTROLS)
    interaction_kind = "not_declared" if allow_undeclared and "interaction_kind" not in payload else _choice("interaction_kind", payload["interaction_kind"], INTERACTION_KINDS)
    movement_link = "not_declared" if allow_undeclared and "movement_link" not in payload else _choice("movement_link", payload["movement_link"], MOVEMENT_LINKS)
    platform_policy = "not_declared" if allow_undeclared and "platform_policy" not in payload else _choice("platform_policy", payload["platform_policy"], PLATFORM_POLICIES)
    recovery_policy = "not_declared" if allow_undeclared and "recovery_policy" not in payload else _choice("recovery_policy", payload["recovery_policy"], RECOVERY_POLICIES)
    minimum_distance = float(payload["minimum_distance"])
    if minimum_distance <= 0:
        raise ValueError("mechanic_contract_bad_minimum_distance")
    for field in ("interrupt_backup", "dispel_backup"):
        if field not in payload and allow_undeclared:
            continue
        if not isinstance(payload[field], bool):
            raise ValueError(f"mechanic_contract_non_boolean:{field}")

    policy_fields = (
        "healer_ownership",
        "cooldown_schedule",
        "soak_policy",
        "immunity_policy",
        "personal_cooldown_policy",
        "battle_resurrection_policy",
    )
    normalized_policies: dict[str, str] = {}
    for field in policy_fields:
        value = str(payload.get(field, "not_declared")).strip()
        if not value:
            raise ValueError(f"mechanic_contract_empty_policy:{field}")
        normalized_policies[field] = value

    return DeclarativeMechanicContract(
        strategy_id=strategy_id,
        formation=formation,
        anchor_scope=anchor_scope,
        minimum_distance=minimum_distance,
        tank_swap_trigger=tank_swap_trigger,
        target_control=target_control,
        interrupt_backup=payload.get("interrupt_backup"),
        dispel_backup=payload.get("dispel_backup"),
        healer_ownership=normalized_policies["healer_ownership"],
        cooldown_schedule=normalized_policies["cooldown_schedule"],
        soak_policy=normalized_policies["soak_policy"],
        immunity_policy=normalized_policies["immunity_policy"],
        personal_cooldown_policy=normalized_policies["personal_cooldown_policy"],
        battle_resurrection_policy=normalized_policies["battle_resurrection_policy"],
        interaction_kind=interaction_kind,
        movement_link=movement_link,
        platform_policy=platform_policy,
        recovery_policy=recovery_policy,
    )


def generic_assignment_smoke(
    foundation: RaidFoundation,
    contract: DeclarativeMechanicContract,
    *,
    assignment_generation: int,
) -> tuple[dict[str, Any], ...]:
    if assignment_generation <= 0:
        raise ValueError("raid_assignment_generation_invalid")
    if any(not member.active or not member.lease_owned for member in foundation.members):
        raise ValueError("raid_assignment_inactive_or_unleased_member")

    points = formation_points(contract.formation, len(foundation.members), minimum_distance=contract.minimum_distance)
    events: list[dict[str, Any]] = []
    for member, point in zip(foundation.members, points, strict=True):
        if contract.anchor_scope == "role":
            anchor = f"role:{member.role}"
        elif contract.anchor_scope == "subgroup":
            anchor = f"subgroup:{member.subgroup}"
        else:
            anchor = "raid"
        events.append(
            {
                "group_guid": foundation.identity.group_guid,
                "leader_guid": foundation.identity.leader_guid,
                "expected_size": foundation.identity.raid_size,
                "server_epoch": foundation.identity.server_epoch,
                "attempt_id": foundation.identity.attempt_id,
                "instance_id": foundation.identity.instance_id,
                "map_id": foundation.identity.map_id,
                "lockout_save_id": foundation.identity.lockout_save_id,
                "difficulty_id": foundation.identity.difficulty_id,
                "difficulty_name": foundation.identity.difficulty_name,
                "raid_size": foundation.identity.raid_size,
                "strategy_id": contract.strategy_id,
                "assignment_generation": assignment_generation,
                "evidence_sequence": assignment_generation * foundation.identity.raid_size + member.slot + 1,
                "member_guid": member.guid,
                "roster_slot_id": member.roster_slot_id,
                "slot": member.slot,
                "subgroup": member.subgroup,
                "role": member.role,
                "anchor": anchor,
                "formation": contract.formation,
                "formation_point": point,
                "tank_swap_trigger": contract.tank_swap_trigger,
                "target_control": contract.target_control,
                "interrupt_primary": foundation.interrupt_rotation[0],
                "interrupt_backup": foundation.interrupt_rotation[1] if contract.interrupt_backup else None,
                "dispel_primary": foundation.dispel_rotation[0],
                "dispel_backup": foundation.dispel_rotation[1] if contract.dispel_backup else None,
                "healer_ownership": contract.healer_ownership,
                "cooldown_schedule": contract.cooldown_schedule,
                "soak_policy": contract.soak_policy,
                "immunity_policy": contract.immunity_policy,
                "personal_cooldown_policy": contract.personal_cooldown_policy,
                "battle_resurrection_policy": contract.battle_resurrection_policy,
                "interaction_kind": contract.interaction_kind,
                "movement_link": contract.movement_link,
                "platform_policy": contract.platform_policy,
                "recovery_policy": contract.recovery_policy,
            }
        )
    validate_evidence_demultiplex(
        events,
        replace(foundation.identity, strategy_id=contract.strategy_id),
        foundation.members,
    )
    if len({event["member_guid"] for event in events}) != foundation.identity.raid_size:
        raise ValueError("raid_assignment_cross_member_attribution")
    return tuple(events)


def validate_evidence_demultiplex(
    events: Iterable[dict[str, Any]],
    identity: RaidIdentity,
    members: Iterable[RaidMember] | None = None,
) -> int:
    observed = 0
    sequences: set[int] = set()
    previous_sequence = 0
    expected_members = {member.guid: member for member in members} if members is not None else None
    for event in events:
        expected = {
            "group_guid": identity.group_guid,
            "leader_guid": identity.leader_guid,
            "expected_size": identity.raid_size,
            "server_epoch": identity.server_epoch,
            "attempt_id": identity.attempt_id,
            "instance_id": identity.instance_id,
            "map_id": identity.map_id,
            "lockout_save_id": identity.lockout_save_id,
            "difficulty_id": identity.difficulty_id,
            "difficulty_name": identity.difficulty_name,
            "raid_size": identity.raid_size,
            "strategy_id": identity.strategy_id,
        }
        if any(key not in event or event.get(key) != value for key, value in expected.items()):
            raise ValueError("raid_evidence_cross_attribution")
        if expected_members is not None:
            member_guid = event.get("member_guid")
            member = expected_members.get(member_guid)
            if member is None or any(
                event.get(key) != value
                for key, value in {
                    "roster_slot_id": member.roster_slot_id,
                    "slot": member.slot,
                    "subgroup": member.subgroup,
                    "role": member.role,
                }.items()
            ):
                raise ValueError("raid_evidence_roster_cross_attribution")
        sequence = event.get("evidence_sequence", event.get("sequence"))
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0:
            raise ValueError("raid_evidence_sequence_missing")
        if sequence in sequences:
            raise ValueError("raid_evidence_duplicate_sequence")
        if sequence <= previous_sequence:
            raise ValueError("raid_evidence_sequence_not_monotonic")
        sequences.add(sequence)
        previous_sequence = sequence
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
        roster_slot_id=(str(value["roster_slot_id"]) if value.get("roster_slot_id") is not None else None),
    )


def _member_by_guid(members: tuple[RaidMember, ...], guid: int) -> RaidMember:
    return next(member for member in members if member.guid == guid)


def _choice(field: str, value: Any, allowed: frozenset[str]) -> str:
    normalized = str(value)
    if normalized not in allowed:
        raise ValueError(f"mechanic_contract_unknown_{field}:{normalized}")
    return normalized
