"""Round 10: capture accepts authorised talent-group transitions and rejects the rest (capture_spec_transitions.py).

Every check runs against a verified route authority (route rows + plan members). Scope markers are rejected unless
that authority carries contracts, membership is always checked against the plan, route progress is bound to the
manifest and never rewinds, each talent group's first observation is checked against its provisioned loadout, and
completed-roster acceptance is separate from transition/failure acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tests.test_phase1_raid_foundation_capture import accepted_status
from tools.raid_program import capture_runtime_acceptance as acceptance
from tools.raid_program.capture_evidence_demux import evidence_demux_report
from tools.raid_program.capture_finalization import normalized_batch_payload
from tools.raid_program.capture_finalization import terminal_runtime_failure_reason
from tools.raid_program.capture_runtime_identity import _roster_binding_identity, _runtime_identity
from tools.raid_program.capture_spec_transitions import (
    GroupLoadout,
    MemberIdentity,
    SpecAuthorityError,
    SpecTransitionTracker,
    _membership_rejections,
    load_route_authority,
    masking_authorised,
    members_from_plan_shard,
    plan_shard,
    route_authority_from_rows,
    scope_marker_rejections,
)

ROOT = Path(__file__).resolve().parents[1]
SWITCHER = 1  # 0-based roster slot of the member that changes talent group
BALANCE = ("balance_druid", "dps")
BALANCE_TALENTS = [78674, 93401]
NODES = 10


def _scoped(status: dict) -> dict:
    status = copy.deepcopy(status)
    runtime = status["raid_runtime"]
    runtime["spec_contract_scope"] = True
    for row in runtime["roster"]:
        row["spec_contract_scope"] = True
    return status


def _group(row: dict, role: str, talents: list[int]) -> GroupLoadout:
    return GroupLoadout(role, tuple(sorted(talents)), acceptance._canonical_int_list(row["glyphs"]), tuple(
        {"slot": item[0], "entry": item[2], "enchant_id": item[3], "gem_item_ids": item[4], "reforge_id": item[5]}
        for item in acceptance._runtime_gear_manifest(row)))


def _members(status: dict) -> dict[int, MemberIdentity]:
    members = {}
    for row in status["raid_runtime"]["roster"]:
        groups = {row["class_spec"]: _group(row, row["role"], row["talents"])}
        identities = {0: (row["class_spec"], row["role"])}
        if row["slot"] == SWITCHER:
            groups[BALANCE[0]] = _group(row, BALANCE[1], BALANCE_TALENTS)
            identities[1] = BALANCE
        members[row["slot"]] = MemberIdentity(
            slot=row["slot"], roster_slot_id=row["roster_slot_id"], character_key=f"member{row['slot']}",
            account=row["account"].upper(), account_id=row["account_id"], character_guid=row["guid"],
            name=row["name"], class_id=row["class_id"], initial=(row["class_spec"], row["role"]), groups=groups,
            group_identities=identities)
    return members


def _route_rows(status: dict) -> list[dict]:
    """Node 0 moves the switcher to Balance; node 5 moves it back to its provisioned group."""
    original = {row["slot"]: (row["class_spec"], row["role"]) for row in status["raid_runtime"]["roster"]}

    def contract(switcher: tuple[str, str]) -> list[dict]:
        rows = []
        for slot in sorted(original):
            groups = [original[slot], BALANCE] if slot == SWITCHER else [original[slot]]
            wanted = switcher if slot == SWITCHER else original[slot]
            rows.append({"roster_slot": slot + 1, "character_key": f"member{slot}",
                         "talent_group": groups.index(wanted), "class_spec": wanted[0], "role": wanted[1],
                         "talent_groups": [{"talent_group": index, "class_spec": spec, "role": role}
                                           for index, (spec, role) in enumerate(groups)]})
        return rows

    rows = []
    for index in range(NODES):
        row = {"scenario_id": "raid", "step": index + 1, "route_node_id": f"n{index}",
               "kind": "regroup" if index in (0, 5) else "trash"}
        if index == 0:
            row["spec_contract"] = contract(BALANCE)
        if index == 5:
            row["spec_contract"] = contract(original[SWITCHER])
        rows.append(row)
    return rows


@pytest.fixture()
def base() -> dict:
    status = _scoped(accepted_status())
    status["cohort_id"] = "raid"
    return status


@pytest.fixture()
def authority(base):
    return route_authority_from_rows(_route_rows(base), "raid", _members(base))


def _at(status: dict, node_index: int, *, balance: bool, generation_delta: int = 0, node_id: str | None = None) -> dict:
    status = copy.deepcopy(status)
    runtime = status["raid_runtime"]
    runtime["route_progress"] = {"generation": node_index + 1, "node_index": node_index}
    runtime["assignment_generation"] += generation_delta
    status["validation_route"] = {"scenario_id": "raid", "node_id": node_id or f"n{node_index}",
                                  "manifest_index": node_index, "manifest_count": NODES}
    row = next(row for row in runtime["roster"] if row["slot"] == SWITCHER)
    if balance:
        row["class_spec"], row["role"] = BALANCE
        row["talents"] = list(BALANCE_TALENTS)
        row["gear_identity"] = row["gear_identity"] + ";balance"
    return status


def _switcher(status: dict) -> dict:
    return next(row for row in status["raid_runtime"]["roster"] if row["slot"] == SWITCHER)


def _rows(*statuses: dict) -> list:
    final = statuses[-1]
    runtime = final["raid_runtime"]
    envelopes = (
        {"ok": True, "action": "botauto_diagnose", "cohort_id": "raid", "raid_runtime": runtime,
         "bots": [{"bot_guid": 1001 + index} for index in range(10)]},
        {"ok": True, "action": "botauto_trace", "cohort_id": "raid", "raid_runtime": runtime,
         "bots": [{"bot_guid": 1001 + index, "entries": [], "delta": True, "gap": False} for index in range(10)]},
        {"ok": True, "action": "botauto_readycheck", "cohort_id": "raid", "raid_runtime": runtime},
    )
    stop = {"ok": True, "action": "botauto_stop", "cohort_id": "raid", "server_epoch": 88, "attempt_id": 1,
            "raid_runtime_before_cleanup": final["raid_runtime"],
            "post_cleanup": {"active": False, "bots": 0, "lease_count": 0}}
    inactive = _native_cleanup(final)
    return normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (*statuses, *envelopes, stop, inactive)) + b"\n")


def _native_cleanup(final: dict) -> dict:
    """The post-cleanup status as native code emits it: StopAutonomy() resets the party runtime, so the route
    manifest and with it every spec scope marker are gone; the assignment generation stays an integer."""
    inactive = json.loads(json.dumps(final))
    inactive.update(active=False, bots=0, lease_count=0, server_epoch=88, attempt_id=1)
    runtime = inactive["raid_runtime"]
    runtime["active"] = False
    runtime.pop("spec_contract_scope", None)
    for row in runtime["roster"]:
        row.pop("spec_contract_scope", None)
    return inactive


def _demux(rows: list, authority) -> dict:
    return evidence_demux_report(rows, profile_name="blackwing_descent_10n", controller_terminal=None,
                                 terminal_failure_validator=terminal_runtime_failure_reason,
                                 spec_authority=authority)


def test_an_authorised_switch_is_bound_and_membership_stays_frozen(base, authority):
    before = _at(base, 0, balance=False)
    switched = _at(base, 0, balance=True, generation_delta=1)
    later = _at(base, 2, balance=True, generation_delta=1)
    rows = _rows(before, switched, later)
    report = _demux(rows, authority)
    assert report["rejections"] == [], report["rejections"]
    # Masked projections are equal across the switch only with the authority's consent.
    runtime_before, runtime_later = before["raid_runtime"], later["raid_runtime"]
    assert masking_authorised(runtime_later, authority)
    assert _roster_binding_identity(runtime_before["roster"], spec_scope_authorised=True) == _roster_binding_identity(
        runtime_later["roster"], spec_scope_authorised=True)
    assert _runtime_identity(runtime_before, spec_scope_authorised=True) == _runtime_identity(
        runtime_later, spec_scope_authorised=True)
    assert _runtime_identity(runtime_before) != _runtime_identity(runtime_later)
    # Correlation telemetry carries the observed integer generation, never the mask.
    generations = {bot["identity_binding"]["correlation"]["assignment_generation"]
                   for row in rows if row["payload"].get("action") in {"botauto_diagnose", "botauto_trace"}
                   for bot in row["payload"]["bots"]}
    assert generations == {runtime_later["assignment_generation"]}


def _edited(status: dict) -> dict:
    _switcher(status)["gear_identity"] += ";edited"
    return status


def _talents(status: dict, talents: list[int]) -> dict:
    _switcher(status)["talents"] = talents
    return status


@pytest.mark.parametrize("make,reason", [
    # A switch where no contract authorises it (after the switch node, back to the other group).
    (lambda base: [_at(base, 0, balance=True, generation_delta=1), _at(base, 2, balance=False, generation_delta=2)],
     "evidence_demux_spec_transition_unauthorised"),
    # Leaving a switch node before switching.
    (lambda base: [_at(base, 0, balance=False), _at(base, 2, balance=False)],
     "evidence_demux_spec_switch_incomplete_after_node"),
    # Gear edited outside a switch node.
    (lambda base: [_at(base, 2, balance=True, generation_delta=1),
                   _edited(_at(base, 3, balance=True, generation_delta=1))],
     "evidence_demux_spec_loadout_drift"),
    # An assignment change with no loadout transition.
    (lambda base: [_at(base, 2, balance=True, generation_delta=1), _at(base, 3, balance=True, generation_delta=2)],
     "evidence_demux_spec_assignment_generation_without_loadout_transition"),
    # A role/spec change without an assignment-generation advance.
    (lambda base: [_at(base, 0, balance=False), _at(base, 0, balance=True)],
     "evidence_demux_spec_assignment_generation_not_advanced"),
    # A group's first observation already differs from its provisioned talents: it is never frozen as the baseline.
    (lambda base: [_at(base, 0, balance=False),
                   _talents(_at(base, 2, balance=True, generation_delta=1), [78674, 99999])],
     "evidence_demux_spec_loadout_baseline_mismatch"),
    # A status row whose node id is not the manifest's node at that index.
    (lambda base: [_at(base, 0, balance=False, node_id="n7")],
     "evidence_demux_spec_route_node_identity_mismatch"),
    # A renamed member is a membership change, whatever the scope masks.
    (lambda base: [_at(base, 0, balance=False),
                   _renamed(_at(base, 0, balance=True, generation_delta=1))],
     "evidence_demux_frozen_identity_name_mismatch"),
])
def test_an_unauthorised_change_is_rejected(base, authority, make, reason):
    report = _demux(_rows(*make(base)), authority)
    assert reason in report["rejections"], report["rejections"]


def _renamed(status: dict) -> dict:
    _switcher(status)["name"] = "Someoneelse"
    return status


def test_a_replayed_node_index_never_reopens_a_switch_window(base, authority):
    # 6 -> 0 -> 2 -> 5 -> 6: the replay to node 0 would authorise Balance again if the window re-opened.
    sequence = [_at(base, 0, balance=True, generation_delta=1), _at(base, 5, balance=False, generation_delta=2),
                _at(base, 6, balance=False, generation_delta=2), _at(base, 0, balance=True, generation_delta=3),
                _at(base, 2, balance=True, generation_delta=3), _at(base, 5, balance=False, generation_delta=4),
                _at(base, 6, balance=False, generation_delta=4)]
    tracker = SpecTransitionTracker(authority)
    results = [tracker.observe(status["raid_runtime"], status["validation_route"]) for status in sequence]
    assert results[:3] == [[], [], []], results
    assert "spec_route_progress_regressed" in results[3] and "spec_transition_unauthorised" in results[3]
    assert "spec_route_progress_regressed" in results[4] and "spec_route_progress_regressed" in results[5]
    report = _demux(_rows(*sequence), authority)
    assert "evidence_demux_spec_route_progress_regressed" in report["rejections"]
    assert "evidence_demux_spec_transition_unauthorised" in report["rejections"]


def test_the_tracker_binds_the_attempt_and_the_route_generation(base, authority):
    tracker = SpecTransitionTracker(authority)
    assert tracker.observe(_at(base, 0, balance=False)["raid_runtime"]) == []
    other = _at(base, 1, balance=False)
    other["raid_runtime"]["attempt_id"] = 2
    assert "spec_route_attempt_changed" in tracker.observe(other["raid_runtime"])
    skewed = _at(base, 1, balance=False)
    skewed["raid_runtime"]["route_progress"]["generation"] = 7
    assert tracker.observe(skewed["raid_runtime"]) == ["spec_contract_observation_invalid"]
    beyond = _at(base, 1, balance=False)
    beyond["raid_runtime"]["route_progress"] = {"generation": NODES + 1, "node_index": NODES}
    assert tracker.observe(beyond["raid_runtime"]) == ["spec_contract_observation_invalid"]


def test_scope_markers_need_an_authority_and_must_agree(base, authority):
    legacy = copy.deepcopy(accepted_status())
    runtime = legacy["raid_runtime"]
    # A row-only marker: rejected, and it masks nothing.
    runtime["roster"][SWITCHER]["spec_contract_scope"] = True
    assert set(scope_marker_rejections(runtime, None)) == {
        "spec_contract_scope_disagreement", "spec_contract_scope_without_authorised_contracts"}
    assert not masking_authorised(runtime, authority)
    assert "<spec_contract_scope>" not in _roster_binding_identity(runtime["roster"])[SWITCHER]
    assert "<spec_contract_scope>" not in _roster_binding_identity(
        runtime["roster"], spec_scope_authorised=masking_authorised(runtime, authority))[SWITCHER]
    # A fully scoped runtime with no authority, or with an authority lacking contracts.
    scoped = base["raid_runtime"]
    assert scope_marker_rejections(scoped, None) == ["spec_contract_scope_without_authorised_contracts"]
    empty = route_authority_from_rows([{"scenario_id": "raid", "step": 1, "route_node_id": "n0", "kind": "regroup"}],
                                      "raid", None)
    assert scope_marker_rejections(scoped, empty) == ["spec_contract_scope_without_authorised_contracts"]
    # An authority with contracts whose runtime does not claim the scope.
    assert scope_marker_rejections(accepted_status()["raid_runtime"], authority) == [
        "spec_contract_route_without_runtime_scope"]
    # A malformed marker.
    malformed = copy.deepcopy(scoped)
    malformed["spec_contract_scope"] = "true"
    assert "spec_contract_scope_marker_invalid" in scope_marker_rejections(malformed, authority)
    assert scope_marker_rejections(scoped, authority) == []


def test_the_demux_rejects_unauthorised_markers_before_masking(base, authority):
    # No authority: a scoped switch is not masked, so it neither binds nor hides the loadout change.
    report = _demux(_rows(_at(base, 0, balance=False), _at(base, 0, balance=True, generation_delta=1)), None)
    assert "evidence_demux_no_active_raid_rows" in report["rejections"], report["rejections"]
    # Row-only markers on legacy rows: the unmasked loadout change is a cross-identity row.
    legacy = copy.deepcopy(accepted_status())
    legacy["cohort_id"] = "raid"
    changed = copy.deepcopy(legacy)
    for status in (legacy, changed):
        for row in status["raid_runtime"]["roster"]:
            row["spec_contract_scope"] = True
    report = _demux(_rows(legacy, changed), None)
    assert "evidence_demux_no_active_raid_rows" in report["rejections"]
    # An authority with contracts and unscoped legacy rows.
    unscoped = copy.deepcopy(accepted_status())
    unscoped["cohort_id"] = "raid"
    report = _demux(_rows(unscoped), authority)
    assert "evidence_demux_spec_contract_route_without_runtime_scope" in report["rejections"]


def test_completed_roster_and_transition_acceptance_are_separate(base, authority):
    switched = _at(base, 2, balance=True, generation_delta=1)["raid_runtime"]
    assert acceptance._roster_rejections(switched, "raid", authority) == []
    unswitched = _at(base, 2, balance=False)["raid_runtime"]
    assert "spec_contract_roster_identity_mismatch" in acceptance._roster_rejections(unswitched, "raid", authority)
    # Mid-switch at the switch node: a transition, not a completed roster.
    mid = _at(base, 0, balance=False)["raid_runtime"]
    assert "spec_contract_roster_identity_mismatch" in acceptance._roster_rejections(mid, "raid", authority)
    assert acceptance._roster_rejections(mid, "raid", authority, completed=False) == []
    # Membership is checked in both modes.
    foreign = copy.deepcopy(mid)
    foreign["roster"][3]["guid"] = 9999
    foreign["roster"][4]["account_id"] = 4242
    for completed in (True, False):
        reasons = acceptance._roster_rejections(foreign, "raid", authority, completed=completed)
        assert {"frozen_identity_character_guid_mismatch", "frozen_identity_account_id_mismatch"} <= set(reasons)
    # A wrong loadout at a non-switch node fails both modes.
    wrong = _talents(_at(base, 2, balance=True, generation_delta=1), [78674, 99999])["raid_runtime"]
    for completed in (True, False):
        assert "frozen_identity_talents_mismatch" in acceptance._roster_rejections(
            wrong, "raid", authority, completed=completed)
    # No authority: the scope is rejected before any roster check.
    assert acceptance._roster_rejections(switched, "raid", None) == ["spec_contract_scope_without_authorised_contracts"]


def _terminal(status: dict) -> dict:
    status = copy.deepcopy(status)
    status.update(cohort_id="default", active_profile="blackwing_descent_10n", failure_reason="spec_switch_timeout")
    return status


def test_a_scoped_terminal_failure_is_judged_as_a_transition(base, authority):
    # Mid-switch at the switch node: a lawful failure with the authority, rejected without it.
    terminal = _terminal(_at(base, 0, balance=False))
    assert acceptance.terminal_runtime_failure_reason(terminal, spec_authority=authority) == ("spec_switch_timeout", [])
    reason, rejections = acceptance.terminal_runtime_failure_reason(terminal)
    assert reason is None and "terminal_failure_spec_contract_scope_without_authorised_contracts" in rejections
    # Membership still binds a terminal failure.
    foreign = copy.deepcopy(terminal)
    _switcher(foreign)["guid"] = 9999
    reason, rejections = acceptance.terminal_runtime_failure_reason(foreign, spec_authority=authority)
    assert reason is None and "terminal_failure_frozen_identity_character_guid_mismatch" in rejections
    # The demux hands the authority to the terminal validator, so the lawful terminal failure waives the
    # ready-check; the same scoped rows without the authority never bind.
    rows = [row for row in _rows(terminal) if row["payload"]["action"] != "botauto_readycheck"]
    for sequence, row in enumerate(rows, 1):
        row["capture_sequence"] = sequence
        row["payload"]["cohort_id"] = "default"
    assert _demux(copy.deepcopy(rows), authority)["rejections"] == []
    assert "evidence_demux_spec_contract_scope_without_authorised_contracts" in _demux(rows, None)["rejections"]


def test_native_recovery_rejects_an_unauthorised_scope(base):
    accepted, reasons = acceptance.accepted_native_recovery([_at(base, 0, balance=False)])
    assert not accepted
    assert "native_spec_contract_scope_without_authorised_contracts" in reasons


def test_unscoped_legacy_projections_are_unchanged():
    runtime = accepted_status()["raid_runtime"]
    assert _runtime_identity(runtime)[-1] == runtime["assignment_generation"]
    assert _runtime_identity(runtime, spec_scope_authorised=True) == _runtime_identity(runtime)
    assert all("<spec_contract_scope>" not in member for member in _roster_binding_identity(runtime["roster"]))
    assert scope_marker_rejections(runtime, None) == []


@pytest.mark.parametrize("edit,reason", [
    (lambda rows: rows[0].update(spec_contract=None), "spec_contract_shape"),
    (lambda rows: rows[0].update(spec_contract={}), "spec_contract_shape"),
    (lambda rows: rows[0].update(spec_contract=[]), "spec_contract_shape"),
    (lambda rows: rows[0]["spec_contract"][0].update(extra=1), "spec_contract_row_shape"),
    (lambda rows: rows[0]["spec_contract"][0].update(talent_group=1), "spec_contract_wanted_identity_mismatch"),
    (lambda rows: rows[0]["spec_contract"].pop(), "spec_contract_roster_coverage"),
    (lambda rows: rows[0]["spec_contract"][2].update(character_key="someone"), "spec_contract_plan_mismatch"),
    (lambda rows: rows[0].update(kind="trash"), "spec_contract_node_kind"),
    (lambda rows: rows[3].update(step=9), "spec_contract_route_steps_invalid"),
    (lambda rows: rows[3].update(route_node_id="n0"), "spec_contract_route_node_ids_invalid"),
])
def test_the_authority_parses_the_route_strictly(base, edit, reason):
    rows = copy.deepcopy(_route_rows(base))
    edit(rows)
    with pytest.raises(SpecAuthorityError, match=reason):
        route_authority_from_rows(rows, "raid", _members(base))


def test_the_authority_comes_from_the_bound_manifest(base, tmp_path):
    manifest = tmp_path / "validation_routes.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in _route_rows(base)))
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(SpecAuthorityError, match="sha256_mismatch"):
        load_route_authority("raid", manifest, manifest_sha256="0" * 64)
    # No contracts for the scenario: an authority without contracts (and so no spec scope), no plan needed.
    manifest_without = tmp_path / "plain.jsonl"
    manifest_without.write_text(json.dumps({"scenario_id": "plain", "step": 1, "route_node_id": "a",
                                            "kind": "regroup"}) + "\n")
    plain = load_route_authority("plain", manifest_without)
    assert plain.contracts == () and plain.manifest_sha256 == hashlib.sha256(manifest_without.read_bytes()).hexdigest()
    with pytest.raises(SpecAuthorityError, match="spec_contract_plan_missing"):
        load_route_authority("raid", manifest, manifest_sha256=digest, plans=tmp_path)


def test_the_canonical_full_raid_manifest_yields_a_complete_authority():
    manifest = ROOT / "dataset/validation_scenarios/validation_routes.jsonl"
    if not manifest.is_file() or not (ROOT / "dataset/raid_shard_provisioning").is_dir():
        pytest.skip("DVC-tracked route manifest or provisioning plan not checked out")
    authority = load_route_authority("blackwing_descent_10n_full_c0", manifest)
    assert [contract.node_id for contract in authority.contracts] == [
        f"bwd.spec_switch.{boss}" for boss in ("magmaw", "omnotron", "atramedes", "chimaeron", "nefarian")]
    assert len(authority.members) == 10 and len(authority.node_ids) >= 35
    assert all(set(contract.wanted) == set(range(10)) for contract in authority.contracts)


def _real_full_raid():
    manifest = ROOT / "dataset/validation_scenarios/validation_routes.jsonl"
    if not manifest.is_file() or not (ROOT / "dataset/raid_shard_provisioning").is_dir():
        pytest.skip("DVC-tracked route manifest or provisioning plan not checked out")
    scenario = "blackwing_descent_10n_full_c0"
    rows = [row for row in (json.loads(line) for line in manifest.read_text().splitlines() if line.strip())
            if row.get("scenario_id") == scenario]
    return scenario, manifest, rows, plan_shard(scenario)


def test_the_real_full_raid_authority_binds_the_native_roster_identity():
    """Membership built from the real plan matches what native telemetry emits (the route's roster_identity):
    canonical roster slot ids, GUIDs and names, and every emitted spec is a declared talent group."""
    scenario, manifest, rows, shard = _real_full_raid()
    authority = load_route_authority(scenario, manifest)
    native = rows[0]["roster_identity"]
    assert all(row["roster_identity"] == native for row in rows)
    assert len(native) == len(authority.members) == 10
    for slot, (emitted, bot) in enumerate(zip(native, shard["bots"])):
        member = authority.members[slot]
        assert member.roster_slot_id == emitted["roster_slot_id"] == bot["canonical_roster_slot_id"]
        runtime_row = {"slot": slot, "roster_slot_id": emitted["roster_slot_id"], "guid": emitted["guid"],
                       "name": emitted["name"], "class_id": bot["class"], "account": bot["account"],
                       "account_id": bot["expected_account_id"]}
        assert _membership_rejections(runtime_row, member) == [], emitted
        assert member.group_for((emitted["class_spec"], emitted["role"])) is not None, emitted
        assert member.group_identities == {group["talent_group"]: (group["class_spec"], group["role"])
                                           for group in bot["loadout"]["groups"]}


def test_contracts_keep_the_numeric_talent_group_mapping():
    scenario, manifest, rows, shard = _real_full_raid()
    from tools.bot_ml.generate_bot_admission_identities import load_gear_profiles
    from tools.bot_ml.phase_gear_profiles import merge_phase_gear_profiles

    # As the production default loader (load_route_authority): a composition bound to a content phase
    # (BWD: cata_t11) names ``<phase>/<spec>`` profiles, which live in the phase-gear output.
    profiles = merge_phase_gear_profiles(load_gear_profiles(ROOT / "dataset/validation_gear_profiles/profiles.json",
                                                            ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"))
    members = members_from_plan_shard(shard, profiles)
    assert route_authority_from_rows(rows, scenario, members).contracts
    # The druid's group indexes reversed in every contract (wanted spec and role unchanged): group 1 would be
    # authorised as Balance although the plan provisions Balance in group 0.
    swapped = copy.deepcopy(rows)
    for row in swapped:
        for entry in row.get("spec_contract") or []:
            if entry["character_key"] == "druid":
                entry["talent_group"] = 1 - entry["talent_group"]
                for group in entry["talent_groups"]:
                    group["talent_group"] = 1 - group["talent_group"]
    with pytest.raises(SpecAuthorityError, match="spec_contract_plan_mismatch"):
        route_authority_from_rows(swapped, scenario, members)
    # An unchanged-spec member keeps both numeric groups for one identical loadout; unequal ones are ambiguous.
    death_knight = next(member for member in members.values() if member.roster_slot_id == "death_knight")
    assert set(death_knight.group_identities) == {0, 1} and len(death_knight.groups) == 1
    unequal = copy.deepcopy(shard)
    unequal["bots"][0]["loadout"]["groups"][1]["talents"][0]["spell_id"] += 1
    with pytest.raises(SpecAuthorityError, match="spec_contract_plan_group_ambiguous"):
        members_from_plan_shard(unequal, profiles)
    renumbered = copy.deepcopy(shard)
    renumbered["bots"][1]["loadout"]["groups"][1]["talent_group"] = 0
    with pytest.raises(SpecAuthorityError, match="spec_contract_plan_group_index_invalid"):
        members_from_plan_shard(renumbered, profiles)


def _terminal_rows(terminal: dict) -> list:
    rows = [row for row in _rows(terminal) if row["payload"]["action"] != "botauto_readycheck"]
    for sequence, row in enumerate(rows, 1):
        row["capture_sequence"] = sequence
        row["payload"]["cohort_id"] = "default"
    return rows


def test_the_finalization_wrapper_threads_the_capture_authority(base, authority):
    """Production path: capture_finalization's evidence_demux_report wrapper (used by finalize_capture) forwards the
    capture's authority to the demux and its terminal-failure validator."""
    from tools.raid_program import capture_finalization as finalization

    rows = _terminal_rows(_terminal(_at(base, 0, balance=False)))
    assert finalization.evidence_demux_report(copy.deepcopy(rows), spec_authority=authority)["rejections"] == []
    assert finalization.evidence_demux_rejections(copy.deepcopy(rows), spec_authority=authority) == []
    without = finalization.evidence_demux_report(copy.deepcopy(rows))["rejections"]
    assert "evidence_demux_spec_contract_scope_without_authorised_contracts" in without
    # The immutable batch's diagnostic bindings are reconstructed with the same authority.
    log = b"\n".join(json.dumps(row["payload"]).encode() for row in rows) + b"\n"
    bound = finalization.normalized_batch_payload(log, spec_authority=authority)
    assert {row["identity_binding"]["state"] for row in bound} == {"bound"}
    assert "bound" not in {row["identity_binding"]["state"] for row in finalization.normalized_batch_payload(log)}


def test_live_evidence_helpers_mask_only_with_the_capture_authority(base, authority):
    from tools.raid_program.capture_forced_evidence import validate_forced_evidence_bundle
    from tools.raid_program.capture_telemetry_transport import drain_pending_trace_batches

    expected = _at(base, 0, balance=False)
    switched = _at(base, 0, balance=True, generation_delta=1)
    envelopes = [row["payload"] for row in _rows(switched)
                 if row["payload"]["action"] in {"botauto_diagnose", "botauto_trace"}]

    def forced(**kwargs) -> list:
        report = validate_forced_evidence_bundle([(row, 1.0) for row in envelopes], expected,
                                                 requested_at_monotonic=0.0, freshness_timeout_seconds=10.0,
                                                 **kwargs)
        return [reason for channel in report["channels"].values() for reason in channel["rejections"]]

    assert "forced_response_runtime_identity_unbound" not in forced(spec_authority=authority)
    assert "forced_response_runtime_identity_unbound" in forced()

    def drained(**kwargs) -> list:
        trace = next(row for row in envelopes if row["action"] == "botauto_trace")
        return drain_pending_trace_batches((trace, 0.0), expected, deadline_monotonic=5.0, send_delta=lambda: None,
                                           read_trace_response=lambda deadline: None, monotonic=lambda: 0.0,
                                           **kwargs)["rejections"]

    assert "trace_drain_runtime_identity_mismatch" not in drained(spec_authority=authority)
    assert "trace_drain_runtime_identity_mismatch" in drained()


def test_the_capture_authority_is_loaded_once_from_the_verified_closure():
    from tools.raid_program.capture_spec_transitions import capture_spec_authority, spec_authority_kwargs

    scenario, manifest, rows, shard = _real_full_raid()
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    authority = capture_spec_authority({"route_manifest": str(manifest), "route_sha256": digest}, scenario)
    assert authority is not None and len(authority.contracts) == 5 and authority.manifest_sha256 == digest
    with pytest.raises(SpecAuthorityError, match="sha256_mismatch"):
        capture_spec_authority({"route_manifest": str(manifest), "route_sha256": "0" * 64}, scenario)
    with pytest.raises(SpecAuthorityError, match="sha256_unbound"):
        capture_spec_authority({"route_manifest": str(manifest)}, scenario)
    # A boss shard or legacy route has no spec contract: no authority, and every callee is called as at HEAD.
    assert capture_spec_authority({"route_manifest": str(manifest), "route_sha256": "0" * 64},
                                  "blackwing_descent_10n_magmaw_c0_diagnostic") is None
    assert capture_spec_authority({}, scenario) is None
    assert spec_authority_kwargs(None) == {}


def test_an_unreadable_route_keeps_the_legacy_capture_path(tmp_path):
    from tools.raid_program.capture_spec_transitions import capture_spec_authority

    broken = tmp_path / "routes.jsonl"
    broken.write_text("{not json\n")
    assert capture_spec_authority({"route_manifest": str(broken)}, "raid") is None
    assert capture_spec_authority({"route_manifest": str(tmp_path / "missing.jsonl")}, "raid") is None


def test_native_cleanup_binds_to_the_validated_stop_through_the_production_wrapper(base, authority):
    """Native cleanup clears the scope markers: the unmarked, inactive status after a validated stop binds to the
    stop's identity (generation masked under the authority); without a validated stop it does not."""
    from tools.raid_program import capture_finalization as finalization

    rows = _rows(_at(base, 0, balance=False), _at(base, 0, balance=True, generation_delta=1),
                 _at(base, 2, balance=True, generation_delta=1))
    cleanup = rows[-1]["payload"]
    assert cleanup["raid_runtime"]["active"] is False and "spec_contract_scope" not in cleanup["raid_runtime"]
    assert isinstance(cleanup["raid_runtime"]["assignment_generation"], int)
    log = b"\n".join(json.dumps(row["payload"]).encode() for row in rows) + b"\n"
    normalized = finalization.normalized_batch_payload(log, spec_authority=authority)
    assert normalized[-1]["identity_binding"]["state"] == "bound"
    assert finalization.evidence_demux_report(normalized, spec_authority=authority)["rejections"] == []
    # A cleanup whose other identity changed is still a cross-identity row.
    moved = copy.deepcopy(rows)
    moved[-1]["payload"]["raid_runtime"]["instance_id"] += 1
    assert "evidence_demux_cross_identity_row" in finalization.evidence_demux_report(
        moved, spec_authority=authority)["rejections"]
    # No validated stop: the stop row itself is rejected, so the unmarked cleanup row does not bind.
    unvalidated = copy.deepcopy(rows)
    stop = next(row for row in unvalidated if row["payload"]["action"] == "botauto_stop")
    stop["payload"]["post_cleanup"]["bots"] = 1
    report = finalization.evidence_demux_report(unvalidated, spec_authority=authority)
    assert "evidence_demux_spec_cleanup_without_validated_stop" in report["rejections"]
    assert unvalidated[-1]["identity_binding"]["state"] == "rejected"
    # An inactive unmarked row before any stop is still rejected, and a malformed leftover marker too.
    early = copy.deepcopy(rows)
    early.insert(1, copy.deepcopy(early[-1]))
    for sequence, row in enumerate(early, 1):
        row["capture_sequence"] = sequence
    assert "evidence_demux_inactive_status_before_stop" in finalization.evidence_demux_report(
        early, spec_authority=authority)["rejections"]
    malformed = copy.deepcopy(rows)
    malformed[-1]["payload"]["raid_runtime"]["spec_contract_scope"] = "true"
    assert "evidence_demux_spec_contract_scope_marker_invalid" in finalization.evidence_demux_report(
        malformed, spec_authority=authority)["rejections"]
    # Active evidence keeps the strict scope check.
    stripped = copy.deepcopy(rows)
    stripped[1]["payload"]["raid_runtime"].pop("spec_contract_scope")
    assert "evidence_demux_spec_contract_scope_disagreement" in finalization.evidence_demux_report(
        stripped, spec_authority=authority)["rejections"]
