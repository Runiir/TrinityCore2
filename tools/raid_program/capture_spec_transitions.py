"""Authorised talent-group transitions in captured raid evidence (round 10).

A canonical full raid switches members between their two talent groups at
spec-switch route nodes (BotRaidSpecSwitch.h; the route's `spec_contract`
rows in the validation route manifest). Capture used to freeze the whole
roster for a run, so the first lawful switch made every later row look like
another identity.

Authority. Everything here is judged against a `SpecRouteAuthority`: the
route rows of the manifest the capture preflight selected and bound (path and
sha256 come from the caller, never from a default path), strictly parsed like
the native loader, joined with the generated raid-shard plan's members (GUID,
account, name, slot, class and each talent group's provisioned talents, glyphs
and gear). No authority means no spec scope.

The split this module enforces:

- a runtime or roster row may carry `spec_contract_scope` only when an
  authority with contracts is in force, and the runtime and every roster row
  must agree (`scope_marker_rejections`); only then may capture_runtime_identity
  mask the mutable loadout fields (`masking_authorised`), so an unauthorised or
  row-only marker is rejected before it can hide anything;
- membership (roster slot, slot index, class, GUID, account id and name,
  character name) is validated on every observation against the plan;
- route progress is bound to the authority: the observed node index exists,
  its generation is index + 1, the status's node id/index/count match the
  manifest, the attempt never changes, and the index never regresses (the
  native route index is written only by forward advance, manifest load and a
  configuration reset, so an attempt has no lawful rewind: a regressed row is
  rejected and judged at the furthest validated node, so a replay cannot
  re-open a switch window);
- a member's (class spec, role) is always one of its declared talent groups;
  it may change only to the wanted identity of the contract in force, once per
  contract; after the switch node every member holds that identity;
- outside a switch node each talent group's talents, glyphs and gear equal the
  plan's provisioned group from its first observation on, and its runtime gear
  manifest is then frozen;
- the assignment generation never regresses, advances with every role/spec
  change and moves only with a loadout change.

Completed-roster acceptance (every member switched and provisioned) and
transition/failure acceptance (a switch node may be mid-switch) are separate:
see capture_runtime_acceptance._spec_contract_roster_rejections.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
PROVISIONING_PLANS = ROOT / "dataset/raid_shard_provisioning"
SPEC_CONTRACT_SCOPE_FIELD = "spec_contract_scope"
SPEC_CONTRACT_SCOPE_MARKER = "<spec_contract_scope>"
ROSTER_LOADOUT_FIELDS = ("role", "class_spec", "gear_identity", "talents", "glyphs", "gear_identity_manifest")
FROZEN_PER_GROUP_FIELDS = ("gear_identity", "talents", "glyphs", "gear_identity_manifest")
CONTRACT_ROW_FIELDS = frozenset({"roster_slot", "character_key", "talent_group", "class_spec", "role", "talent_groups"})
CONTRACT_GROUP_FIELDS = frozenset({"talent_group", "class_spec", "role"})
ROLES = frozenset({"tank", "healer", "dps"})


class SpecAuthorityError(ValueError):
    """The route manifest or plan cannot authorise spec transitions."""


def in_scope(value: Any) -> bool:
    """A runtime object or roster row that declares the spec-contract scope."""
    return isinstance(value, dict) and value.get(SPEC_CONTRACT_SCOPE_FIELD) is True


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class GroupLoadout:
    role: str
    talents: tuple[int, ...]
    glyphs: tuple[int, ...]
    gear: tuple[dict[str, Any], ...]


@dataclass(frozen=True, eq=False)
class MemberIdentity:
    slot: int
    roster_slot_id: str
    character_key: str
    account: str
    account_id: int | None
    character_guid: int | None
    name: str
    class_id: int
    initial: tuple[str, str]
    groups: dict[str, GroupLoadout]
    group_identities: dict[int, tuple[str, str]]  # numeric talent group -> (class_spec, role)

    def membership(self) -> dict[str, Any]:
        return {"slot": self.slot, "roster_slot_id": self.roster_slot_id, "class_id": self.class_id,
                "account": self.account, "account_id": self.account_id, "character_guid": self.character_guid,
                "name": self.name}

    def group_for(self, identity: tuple[str, str]) -> GroupLoadout | None:
        group = self.groups.get(identity[0])
        return group if group is not None and group.role == identity[1] else None


@dataclass(frozen=True)
class SpecContract:
    node_index: int
    node_id: str
    wanted: dict[int, tuple[str, str]]  # 0-based roster slot -> (class_spec, role)
    wanted_group: dict[int, int]  # 0-based roster slot -> numeric talent group
    declared: dict[int, dict[int, tuple[str, str]]]  # 0-based roster slot -> talent group -> (class_spec, role)


@dataclass(frozen=True, eq=False)
class SpecRouteAuthority:
    scenario_id: str
    node_ids: tuple[str, ...]
    contracts: tuple[SpecContract, ...]
    members: dict[int, MemberIdentity]
    manifest_sha256: str | None = None

    def in_force(self, node_index: int) -> SpecContract | None:
        current = None
        for contract in self.contracts:
            if contract.node_index <= node_index:
                current = contract
        return current


def _contract(row: dict[str, Any], node_index: int, node_id: str) -> tuple[SpecContract, dict[int, str]]:
    """One route row's contract, parsed as strictly as BotRaidSpecSwitch::ParseContract."""
    entries = row.get("spec_contract")
    if not isinstance(entries, list) or not entries:
        raise SpecAuthorityError(f"spec_contract_shape:{node_id}")
    wanted: dict[int, tuple[str, str]] = {}
    wanted_group: dict[int, int] = {}
    declared: dict[int, dict[int, tuple[str, str]]] = {}
    keys: dict[int, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != CONTRACT_ROW_FIELDS:
            raise SpecAuthorityError(f"spec_contract_row_shape:{node_id}")
        slot, group_index = entry["roster_slot"], entry["talent_group"]
        if not _int(slot) or slot < 1 or not _int(group_index) or entry["role"] not in ROLES \
                or not isinstance(entry["class_spec"], str) or not entry["class_spec"] \
                or not isinstance(entry["character_key"], str) or not entry["character_key"]:
            raise SpecAuthorityError(f"spec_contract_row_invalid:{node_id}")
        groups = entry["talent_groups"]
        if not isinstance(groups, list) or not groups:
            raise SpecAuthorityError(f"spec_contract_talent_groups_shape:{node_id}")
        by_index: dict[int, tuple[str, str]] = {}
        for group in groups:
            if not isinstance(group, dict) or set(group) != CONTRACT_GROUP_FIELDS \
                    or group["talent_group"] not in (0, 1) or not _int(group["talent_group"]) \
                    or group["role"] not in ROLES or not isinstance(group["class_spec"], str) \
                    or not group["class_spec"] or group["talent_group"] in by_index:
                raise SpecAuthorityError(f"spec_contract_talent_group_invalid:{node_id}")
            by_index[group["talent_group"]] = (group["class_spec"], group["role"])
        if by_index.get(group_index) != (entry["class_spec"], entry["role"]):
            raise SpecAuthorityError(f"spec_contract_wanted_identity_mismatch:{node_id}")
        if slot - 1 in wanted:
            raise SpecAuthorityError(f"spec_contract_slot_duplicate:{node_id}")
        wanted[slot - 1] = (entry["class_spec"], entry["role"])
        wanted_group[slot - 1] = group_index
        declared[slot - 1] = by_index
        keys[slot - 1] = entry["character_key"]
    return SpecContract(node_index, node_id, wanted, wanted_group, declared), keys


def members_from_plan_shard(shard: dict[str, Any], gear_profiles: dict[str, Any]) -> dict[int, MemberIdentity]:
    """Each plan member's membership identity and its talent groups' provisioned loadouts (0-based slot)."""
    from tools.bot_ml.build_validation_provisioning import normalized_glyph_slots

    members: dict[int, MemberIdentity] = {}
    for slot, bot in enumerate(shard.get("bots") or []):
        groups: dict[str, GroupLoadout] = {}
        identities: dict[int, tuple[str, str]] = {}
        for group in (bot.get("loadout") or {}).get("groups") or []:
            index = group.get("talent_group")
            if not _int(index) or index not in (0, 1) or index in identities:
                raise SpecAuthorityError(f"spec_contract_plan_group_index_invalid:{bot.get('roster_slot_id')}")
            identities[index] = (str(group["class_spec"]), str(group["role"]))
            profile = gear_profiles.get(str(group["gear_profile_id"]))
            if not profile or not profile.get("equipment"):
                raise SpecAuthorityError(f"spec_contract_gear_profile_missing:{group['gear_profile_id']}")
            gear = tuple(sorted(({"slot": int(item["slot"]), "entry": int(item["item_id"]),
                                  "enchant_id": int(item.get("enchant_id") or 0),
                                  "gem_item_ids": tuple(int(value) for value in item.get("gem_item_ids", [])),
                                  "reforge_id": int(item.get("reforge_id") or 0)} for item in profile["equipment"]),
                                key=lambda item: item["slot"]))
            glyphs = tuple(value for value in normalized_glyph_slots({"glyphs": group.get("glyphs") or []})
                           if value > 0)
            loadout = GroupLoadout(
                str(group["role"]), tuple(sorted(int(row["spell_id"]) for row in group["talents"])), glyphs, gear)
            # Runtime rows name a talent group by its class spec, so two numeric groups may share one only when
            # they are the same role and loadout (a member that keeps its spec at every switch node); the numeric
            # group -> identity mapping is kept separately and compared with every contract.
            if groups.setdefault(str(group["class_spec"]), loadout) != loadout:
                raise SpecAuthorityError(f"spec_contract_plan_group_ambiguous:{bot.get('roster_slot_id')}")
        if not groups:
            raise SpecAuthorityError(f"spec_contract_plan_groups_missing:{bot.get('roster_slot_id')}")
        # Native telemetry names members by the canonical roster slot id (`druid`), not the scenario-qualified
        # provisioning id (`blackwing_descent_10n_full_c0:druid`).
        roster_slot_id = str(bot.get("canonical_roster_slot_id") or "")
        if not roster_slot_id:
            raise SpecAuthorityError(f"spec_contract_plan_canonical_slot_missing:{bot.get('roster_slot_id')}")
        members[slot] = MemberIdentity(
            slot=slot, roster_slot_id=roster_slot_id, character_key=str(bot.get("character_key") or ""),
            account=str(bot.get("account") or "").upper(),
            account_id=bot.get("expected_account_id", bot.get("account_id")),
            character_guid=bot.get("expected_character_guid", bot.get("character_guid")),
            name=str(bot.get("name") or ""), class_id=int(bot["class"]),
            initial=(str(bot["class_spec"]), str(bot["role"])), groups=groups, group_identities=identities)
    return members


def route_authority_from_rows(
    route_rows: Iterable[dict[str, Any]],
    scenario_id: str,
    members: dict[int, MemberIdentity] | None,
    *,
    manifest_sha256: str | None = None,
) -> SpecRouteAuthority:
    """The scenario's verified route authority: contiguous steps, unique node ids, strict regroup-only contracts
    that cover exactly the plan's members with their plan-declared talent groups."""
    rows = sorted((row for row in route_rows if row.get("scenario_id") == scenario_id),
                  key=lambda row: row.get("step") if _int(row.get("step")) else -1)
    if [row.get("step") for row in rows] != list(range(1, len(rows) + 1)) or not rows:
        raise SpecAuthorityError(f"spec_contract_route_steps_invalid:{scenario_id}")
    node_ids = tuple(str(row.get("route_node_id") or "") for row in rows)
    if any(not node for node in node_ids) or len(set(node_ids)) != len(node_ids):
        raise SpecAuthorityError(f"spec_contract_route_node_ids_invalid:{scenario_id}")
    contracts = []
    for index, row in enumerate(rows):
        if "spec_contract" not in row:
            continue
        if row.get("kind") != "regroup":
            raise SpecAuthorityError(f"spec_contract_node_kind:{node_ids[index]}")
        contract, keys = _contract(row, index, node_ids[index])
        if members is None or set(contract.wanted) != set(members):
            raise SpecAuthorityError(f"spec_contract_roster_coverage:{node_ids[index]}")
        for slot, member in members.items():
            # The numeric talent group -> (class spec, role) mapping must equal the plan's, so a contract cannot
            # authorise group 1 as the identity the plan provisioned in group 0.
            if keys[slot] != member.character_key or contract.declared[slot] != member.group_identities:
                raise SpecAuthorityError(f"spec_contract_plan_mismatch:{node_ids[index]}:{slot + 1}")
        contracts.append(contract)
    return SpecRouteAuthority(scenario_id, node_ids, tuple(contracts), dict(members or {}), manifest_sha256)


def plan_shard(profile_name: str, plans: Path = PROVISIONING_PLANS) -> dict[str, Any] | None:
    """The generated raid-shard plan's shard for a canonical cohort scenario (None for any other profile)."""
    for path in sorted(Path(plans).glob("*/plan.json")):
        for shard in json.loads(path.read_text(encoding="utf-8")).get("shards") or []:
            if shard.get("scenario_id") == profile_name:
                return shard
    return None


def load_route_authority(
    scenario_id: str,
    manifest_path: Path | str,
    *,
    manifest_sha256: str | None = None,
    plans: Path = PROVISIONING_PLANS,
    gear_profiles: dict[str, Any] | None = None,
) -> SpecRouteAuthority:
    """The authority of the manifest the capture preflight selected (its bound sha256 is re-checked)."""
    data = Path(manifest_path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if manifest_sha256 is not None and digest != manifest_sha256:
        raise SpecAuthorityError("spec_contract_route_manifest_sha256_mismatch")
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    members = None
    if any(row.get("scenario_id") == scenario_id and "spec_contract" in row for row in rows):
        shard = plan_shard(scenario_id, plans)
        if shard is None:
            raise SpecAuthorityError(f"spec_contract_plan_missing:{scenario_id}")
        if gear_profiles is None:
            from tools.bot_ml.generate_bot_admission_identities import load_gear_profiles

            from tools.bot_ml.phase_gear_profiles import merge_phase_gear_profiles

            # A composition bound to a content phase wears ``<phase>/<spec>`` profiles.
            gear_profiles = merge_phase_gear_profiles(load_gear_profiles(
                ROOT / "dataset/validation_gear_profiles/profiles.json",
                ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"))
        members = members_from_plan_shard(shard, gear_profiles)
    return route_authority_from_rows(rows, scenario_id, members, manifest_sha256=digest)


def _scenario_has_contracts(path: Path, scenario_id: str) -> bool:
    """Whether the scenario's route declares any spec contract. An unreadable manifest declares none here: the
    capture then keeps HEAD's own asset checks and error order, and any scoped runtime is still rejected
    downstream for lack of an authority."""
    try:
        rows = [json.loads(line) for line in path.read_bytes().decode("utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    return any(isinstance(row, dict) and row.get("scenario_id") == scenario_id and "spec_contract" in row
               for row in rows)


def capture_spec_authority(
    runtime_assets: dict[str, Any],
    scenario_id: str,
    *,
    plans: Path = PROVISIONING_PLANS,
    gear_profiles: dict[str, Any] | None = None,
) -> SpecRouteAuthority | None:
    """The spec authority of one capture, loaded once from the preflight-verified closure: the route manifest
    `runtime_assets["route_manifest"]` re-checked against its bound `runtime_assets["route_sha256"]`.

    None when the selected scenario's route has no spec contract (every legacy and boss-shard capture), so those
    captures run exactly as before; a route with contracts but no bound sha256 fails closed."""
    path = runtime_assets.get("route_manifest") if isinstance(runtime_assets, dict) else None
    if not isinstance(path, str) or not path:
        return None
    if not _scenario_has_contracts(Path(path), scenario_id):
        return None
    bound_sha256 = runtime_assets.get("route_sha256")
    if not isinstance(bound_sha256, str) or not bound_sha256:
        raise SpecAuthorityError("spec_contract_route_manifest_sha256_unbound")
    return load_route_authority(scenario_id, path, manifest_sha256=bound_sha256, plans=plans,
                                gear_profiles=gear_profiles)


def spec_authority_kwargs(authority: SpecRouteAuthority | None) -> dict[str, Any]:
    """Keyword arguments for an authority-aware callee: empty without an authority, so an unscoped capture calls
    every validator (and any injected replacement) exactly as before."""
    return {"spec_authority": authority} if authority is not None else {}


def _has_contracts(authority: SpecRouteAuthority | None) -> bool:
    return authority is not None and bool(authority.contracts)


def scope_marker_rejections(runtime: Any, authority: SpecRouteAuthority | None) -> list[str]:
    """Scope markers must be well formed, agree between the runtime and every roster row, and be authorised by a
    verified route contract; a route with contracts must be claimed by all of them."""
    if not isinstance(runtime, dict):
        return []
    roster = runtime.get("roster")
    rows = [row for row in roster if isinstance(row, dict)] if isinstance(roster, list) else []
    carriers = [runtime, *rows]
    reasons = []
    if any(SPEC_CONTRACT_SCOPE_FIELD in value and value[SPEC_CONTRACT_SCOPE_FIELD] is not True for value in carriers):
        reasons.append("spec_contract_scope_marker_invalid")
    flags = {in_scope(value) for value in carriers}
    if len(flags) > 1:
        reasons.append("spec_contract_scope_disagreement")
    claimed = True in flags or any(SPEC_CONTRACT_SCOPE_FIELD in value for value in carriers)
    if claimed and not _has_contracts(authority):
        reasons.append("spec_contract_scope_without_authorised_contracts")
    if _has_contracts(authority) and False in flags:
        reasons.append("spec_contract_route_without_runtime_scope")
    return reasons


def masking_authorised(runtime: Any, authority: SpecRouteAuthority | None) -> bool:
    """capture_runtime_identity may mask the mutable loadout only for an authorised, consistently scoped runtime."""
    return _has_contracts(authority) and in_scope(runtime) and not scope_marker_rejections(runtime, authority)


def node_index(runtime: dict[str, Any]) -> int | None:
    progress = runtime.get("route_progress")
    value = progress.get("node_index") if isinstance(progress, dict) else None
    return value if _int(value) and value >= 0 else None


def member_loadout_rejections(row: dict[str, Any], group: GroupLoadout) -> list[str]:
    """A roster row's talents, glyphs and gear against its active talent group's provisioned loadout."""
    try:
        from tools.raid_program.capture_runtime_acceptance import (
            _canonical_int_list, _gear_identity_rejections, _runtime_gear_manifest)
    except ModuleNotFoundError:
        from capture_runtime_acceptance import _canonical_int_list, _gear_identity_rejections, _runtime_gear_manifest
    reasons = []
    talents = _canonical_int_list(row.get("talents"))
    if talents is None or tuple(sorted(talents)) != group.talents:
        reasons.append("frozen_identity_talents_mismatch")
    if _canonical_int_list(row.get("glyphs")) != group.glyphs:
        reasons.append("frozen_identity_glyphs_mismatch")
    reasons.extend(_gear_identity_rejections(_runtime_gear_manifest(row), group.gear))
    return reasons


def _membership_rejections(row: dict[str, Any], member: MemberIdentity) -> list[str]:
    try:
        from tools.raid_program.capture_runtime_identity import _membership_identity_rejections
    except ModuleNotFoundError:
        from capture_runtime_identity import _membership_identity_rejections
    return _membership_identity_rejections(row, member.membership(), check_position=True)


@dataclass
class SpecTransitionTracker:
    """Validates the successive runtime observations of one attempt against a verified route authority."""

    authority: SpecRouteAuthority
    attempt: tuple[Any, ...] | None = None
    furthest_index: int | None = None
    identity: dict[int, tuple[str, str]] = field(default_factory=dict)
    settled: dict[int, int] = field(default_factory=dict)
    frozen: dict[tuple[int, str], tuple[Any, ...]] = field(default_factory=dict)
    previous_loadout: dict[int, tuple[Any, ...]] = field(default_factory=dict)
    previous_generation: int | None = None

    def _route_rejections(self, runtime: dict[str, Any], index: int, route_status: Any) -> list[str]:
        reasons = []
        authority = self.authority
        if route_status is not None and not (
                isinstance(route_status, dict)
                and route_status.get("scenario_id") == authority.scenario_id
                and route_status.get("node_id") == authority.node_ids[index]
                and route_status.get("manifest_index") == index
                and route_status.get("manifest_count") == len(authority.node_ids)):
            reasons.append("spec_route_node_identity_mismatch")
        attempt = tuple(runtime.get(name) for name in ("server_epoch", "attempt_id", "instance_id"))
        if self.attempt is not None and attempt != self.attempt:
            reasons.append("spec_route_attempt_changed")
        self.attempt = self.attempt or attempt
        if self.furthest_index is not None and index < self.furthest_index:
            reasons.append("spec_route_progress_regressed")
        return reasons

    def observe(self, runtime: dict[str, Any], route_status: Any = None) -> list[str]:
        """Rejection reasons for one runtime observation (empty when lawful). `route_status` is the status
        payload's `validation_route` object when the row carries one."""
        reasons = scope_marker_rejections(runtime, self.authority)
        if reasons or not _has_contracts(self.authority):
            return reasons
        authority = self.authority
        roster = runtime.get("roster")
        index = node_index(runtime)
        progress = runtime.get("route_progress")
        if index is None or index >= len(authority.node_ids) or not isinstance(roster, list) \
                or progress.get("generation") != index + 1:
            return ["spec_contract_observation_invalid"]
        reasons.extend(self._route_rejections(runtime, index, route_status))
        # Judge a regressed row at the furthest validated node: a replayed index never re-opens a switch window.
        effective = max(index, self.furthest_index if self.furthest_index is not None else index)
        contract = authority.in_force(effective)
        switching = contract is not None and contract.node_index == effective
        identity_changed = loadout_changed = False
        seen_slots: set[int] = set()
        observed_identity: dict[int, tuple[str, str]] = {}
        observed_loadout: dict[int, tuple[Any, ...]] = {}
        for row in roster:
            slot = row.get("slot") if isinstance(row, dict) else None
            member = authority.members.get(slot) if _int(slot) else None
            if member is None or slot in seen_slots:
                reasons.append("spec_membership_mismatch")
                continue
            seen_slots.add(slot)
            reasons.extend(_membership_rejections(row, member))
            identity = (str(row.get("class_spec")), str(row.get("role")))
            group = member.group_for(identity)
            if group is None:
                reasons.append("spec_identity_unauthorised")
            wanted = contract.wanted.get(slot) if contract is not None else member.initial
            previous = self.identity.get(slot)
            if previous is not None and identity != previous:
                identity_changed = True
                if contract is None or identity != wanted or self.settled.get(slot) == contract.node_index:
                    reasons.append("spec_transition_unauthorised")
            elif previous is None and contract is None and identity != member.initial:
                reasons.append("spec_transition_unauthorised")
            if contract is not None and not switching and identity != wanted:
                reasons.append("spec_switch_incomplete_after_node")
            if contract is not None and not switching and identity == wanted:
                self.settled[slot] = contract.node_index
            loadout = tuple(json.dumps(row.get(name), sort_keys=True) for name in ROSTER_LOADOUT_FIELDS)
            observed_loadout[slot] = loadout
            loadout_changed = loadout_changed or self.previous_loadout.get(slot, loadout) != loadout
            if group is not None and not switching:
                if member_loadout_rejections(row, group):
                    reasons.append("spec_loadout_baseline_mismatch")
                frozen = tuple(json.dumps(row.get(name), sort_keys=True) for name in FROZEN_PER_GROUP_FIELDS)
                if self.frozen.setdefault((slot, identity[0]), frozen) != frozen:
                    reasons.append("spec_loadout_drift")
            observed_identity[slot] = identity
        if seen_slots != set(authority.members):
            reasons.append("spec_membership_mismatch")
        generation = runtime.get("assignment_generation")
        if not _int(generation) or generation <= 0:
            reasons.append("spec_assignment_generation_invalid")
        elif self.previous_generation is not None:
            if generation < self.previous_generation:
                reasons.append("spec_assignment_generation_regressed")
            elif identity_changed and generation == self.previous_generation:
                reasons.append("spec_assignment_generation_not_advanced")
            elif generation > self.previous_generation and not loadout_changed:
                reasons.append("spec_assignment_generation_without_loadout_transition")
        if _int(generation):
            self.previous_generation = max(self.previous_generation or 0, generation)
        self.identity.update(observed_identity)
        self.previous_loadout.update(observed_loadout)
        self.furthest_index = effective
        return list(dict.fromkeys(reasons))
