from __future__ import annotations

import base64
import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

from .phase8_reference_conditions import (
    EXPECTED_REFERENCE_CONDITIONS,
    derive_reference_condition_compatibility,
    load_fixture_contract_binding,
    load_reference_request_binding,
    observed_gear_manifest_sha256,
    verified_reference_request_runtime_facts,
)
from .role_calibration_harness import (
    expected_calibration_profile_lane,
    single_target_fixture_geometry_valid,
)


class RawEvidenceBindingError(ValueError):
    pass


SUPPORTED_EVIDENCE_KINDS = {
    "live_validation",
    "dps_calibration",
    "stonecore_5h",
}
DPS_HARD_REFERENCE_RATIO = 0.75
DPS_OPTIMIZATION_REFERENCE_RATIO = 0.8
DPS_SERIALIZED_DECIMAL_PLACES = 2
DPS_SERIALIZED_ABSOLUTE_TOLERANCE = 0.005000001
DERIVED_ACTIVE_DPS_ABSOLUTE_TOLERANCE = 0.000001
DERIVED_RATIO_SERIALIZED_DECIMAL_PLACES = 6
DERIVED_RATIO_ABSOLUTE_TOLERANCE = 0.000000500001

_DECISIVE_EVENT_ACTIONS = {
    "boss_killed",
    "raid_boss_killed",
    "validation_route_manifest_complete",
    "validation_route_teacher_assist",
    "validation_route_terminal",
    "teacher_kill_assist",
}

DEFAULT_ROLE_CALIBRATION_POLICY = (
    Path(__file__).resolve().parents[2]
    / "experiments/configs/all_spec_role_calibration_policy_v1.json"
)


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_value(value: Any) -> Any:
    """Return the exact JSON-domain value used by the signed projection."""
    return json.loads(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    )


def parse_json_objects(output: str) -> list[dict[str, Any]]:
    """Recover the server JSON envelopes from the retained console bytes."""
    rows: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(output):
        start = output.find("{", index)
        if start < 0:
            break
        try:
            payload, end = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        index = start + max(end, 1)
    return rows


def validate_transport_receipt(
    receipt: Mapping[str, Any], output: str
) -> dict[str, Any]:
    returncode = receipt.get("returncode")
    timed_out = receipt.get("timed_out")
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise RawEvidenceBindingError("transport returncode must be an exact integer")
    if not isinstance(timed_out, bool):
        raise RawEvidenceBindingError("transport timed_out must be an exact boolean")
    output_bytes = output.encode("utf-8")
    expected = {
        "schema": "bot_raw_transport_receipt_v1",
        "returncode": returncode,
        "timed_out": timed_out,
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "output_bytes": len(output_bytes),
        "json_payload_count": len(parse_json_objects(output)),
    }
    if dict(receipt) != expected:
        raise RawEvidenceBindingError("raw transport receipt does not match console bytes")
    return expected


def build_transport_receipt(
    output: str, *, returncode: int, timed_out: bool
) -> dict[str, Any]:
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise RawEvidenceBindingError("transport returncode must be an exact integer")
    if not isinstance(timed_out, bool):
        raise RawEvidenceBindingError("transport timed_out must be an exact boolean")
    output_bytes = output.encode("utf-8")
    return {
        "schema": "bot_raw_transport_receipt_v1",
        "returncode": returncode,
        "timed_out": timed_out,
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "output_bytes": len(output_bytes),
        "json_payload_count": len(parse_json_objects(output)),
    }


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _positive_numbers_equal(left: Any, right: Any) -> bool:
    try:
        left_fraction = _exact_fraction(left, field="left numeric value")
        right_fraction = _exact_fraction(right, field="right numeric value")
    except RawEvidenceBindingError:
        return False
    return left_fraction > 0 and left_fraction == right_fraction


def _exact_fraction(value: Any, *, field: str) -> Fraction:
    """Map a finite JSON number to its exact base-10 rational value."""
    if isinstance(value, bool):
        raise RawEvidenceBindingError(f"{field} must be a finite number")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise RawEvidenceBindingError(f"{field} must be a finite number") from None
    if not decimal_value.is_finite():
        raise RawEvidenceBindingError(f"{field} must be a finite number")
    return Fraction(decimal_value)


def calibration_reference_thresholds(
    policy_sha256: Any = None,
) -> tuple[float, float, Fraction, Fraction]:
    """Load and validate the DPS thresholds from the authoritative policy."""
    try:
        policy = json.loads(
            DEFAULT_ROLE_CALIBRATION_POLICY.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RawEvidenceBindingError(
            "calibration scoring policy is unavailable or invalid"
        ) from exc
    if not isinstance(policy, Mapping):
        raise RawEvidenceBindingError("calibration scoring policy is not an object")
    supplied_policy_sha256 = str(policy_sha256 or "")
    if supplied_policy_sha256 and supplied_policy_sha256 != canonical_sha256(policy):
        raise RawEvidenceBindingError(
            "calibration scoring policy hash does not match the authoritative policy"
        )
    hard_fraction = _exact_fraction(
        policy.get("hard_reference_ratio"), field="hard_reference_ratio"
    )
    optimization_fraction = _exact_fraction(
        policy.get("optimization_reference_ratio"),
        field="optimization_reference_ratio",
    )
    if not (
        Fraction(0) < hard_fraction < optimization_fraction <= Fraction(1)
    ):
        raise RawEvidenceBindingError(
            "calibration scoring policy thresholds are not strictly ordered"
        )
    return (
        float(hard_fraction),
        float(optimization_fraction),
        hard_fraction,
        optimization_fraction,
    )


def _fraction_projection(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _validated_elapsed_dps(
    target: Mapping[str, Any],
) -> tuple[float, Fraction, Fraction]:
    """Validate serialized DPS while retaining exact damage/time for scoring."""
    if not target:
        return 0.0, Fraction(0), Fraction(0)
    damage = _integer(target.get("damage"))
    elapsed_seconds = _number(target.get("elapsed_seconds"))
    observed_dps = _number(target.get("dps"))
    if not math.isfinite(elapsed_seconds) or not math.isfinite(observed_dps):
        raise RawEvidenceBindingError("target DPS arithmetic contains a non-finite value")
    if elapsed_seconds <= 0.0:
        if damage != 0 or observed_dps != 0.0:
            raise RawEvidenceBindingError(
                "target DPS has damage without a positive elapsed_seconds denominator"
            )
        return observed_dps, Fraction(0), Fraction(0)
    elapsed_fraction = _exact_fraction(
        target.get("elapsed_seconds"), field="target elapsed_seconds"
    )
    observed_fraction = _exact_fraction(target.get("dps"), field="target dps")
    expected_dps = Fraction(damage, 1) / elapsed_fraction
    absolute_error = abs(observed_fraction - expected_dps)
    if absolute_error > _exact_fraction(
        DPS_SERIALIZED_ABSOLUTE_TOLERANCE,
        field="DPS serialization tolerance",
    ):
        raise RawEvidenceBindingError(
            "target DPS does not equal damage / elapsed_seconds within the "
            "two-decimal serialization tolerance"
        )
    return observed_dps, expected_dps, absolute_error


def _validated_reported_active_dps(
    *,
    observed_active_dps: float,
    exact_elapsed_dps: Fraction,
    active_uptime: float,
) -> Fraction:
    active_uptime_fraction = _exact_fraction(
        active_uptime, field="active_uptime_ratio"
    )
    expected = (
        exact_elapsed_dps / active_uptime_fraction
        if active_uptime_fraction > 0
        else Fraction(0)
    )
    if not all(
        math.isfinite(value)
        for value in (observed_active_dps, active_uptime, float(expected))
    ):
        raise RawEvidenceBindingError(
            "role calibration active DPS arithmetic contains a non-finite value"
        )
    observed_fraction = _exact_fraction(
        observed_active_dps, field="role calibration active_dps"
    )
    if abs(observed_fraction - expected) > _exact_fraction(
        DERIVED_ACTIVE_DPS_ABSOLUTE_TOLERANCE,
        field="active DPS tolerance",
    ):
        raise RawEvidenceBindingError(
            "role calibration active_dps does not equal exact damage / "
            "elapsed_seconds / active_uptime_ratio"
        )
    return expected


def _route_scope(entry: Mapping[str, Any]) -> tuple[str, int]:
    node_id = str(entry.get("route_node_id") or "")
    generation = _integer(entry.get("route_generation"))
    if node_id and generation > 0:
        return node_id, generation
    route = entry.get("validation_route")
    if not isinstance(route, Mapping):
        return "", 0
    return str(route.get("route_node_id") or ""), _integer(
        route.get("route_generation")
    )


def _scope_rows(entries: Sequence[Mapping[str, Any]], actions: set[str]) -> list[dict[str, Any]]:
    scopes = {
        _route_scope(entry)
        for entry in entries
        if str(entry.get("action") or "") in actions
    }
    return [
        {"route_node_id": node_id, "route_generation": generation}
        for node_id, generation in sorted(scopes)
        if node_id and generation > 0
    ]


def _trace_entries(payloads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for payload in payloads:
        direct = payload.get("entries")
        if isinstance(direct, list):
            entries.extend(dict(row) for row in direct if isinstance(row, Mapping))
        bots = payload.get("bots")
        if isinstance(bots, list):
            for bot in bots:
                if not isinstance(bot, Mapping) or not isinstance(bot.get("entries"), list):
                    continue
                entries.extend(
                    dict(row)
                    for row in bot["entries"]
                    if isinstance(row, Mapping)
                )
        if str(payload.get("action") or "") in _DECISIVE_EVENT_ACTIONS:
            entries.append(dict(payload))
    return entries


def _admission_status_candidates(
    payloads: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for payload in payloads:
        runtime = payload.get("raid_runtime")
        if isinstance(runtime, Mapping) and isinstance(
            runtime.get("admission_receipt"), Mapping
        ):
            candidates.append(dict(payload))
    return candidates


def _status_with_admission(
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidates = _admission_status_candidates(payloads)
    # Admission identity is established by the first complete active receipt.
    # Later terminal rows intentionally clear live member fields during cleanup;
    # they are authoritative for route/cleanup state, not for the immutable
    # five-player roster admitted at the start.
    for candidate in candidates:
        runtime = candidate.get("raid_runtime")
        runtime = runtime if isinstance(runtime, Mapping) else {}
        receipt = runtime.get("admission_receipt")
        receipt = receipt if isinstance(receipt, Mapping) else {}
        if (
            str(runtime.get("admission_phase") or "") == "active"
            and runtime.get("bot_actions_enabled") is True
            and receipt.get("bot_actions_enabled_at_commit") is True
        ):
            return candidate
    return (candidates or [{}])[0]


def _post_admission_gear_drift(
    payloads: Sequence[Mapping[str, Any]],
) -> bool:
    candidates = _admission_status_candidates(payloads)
    if len(candidates) < 2:
        return False
    admitted = _status_with_admission(payloads)
    admitted_runtime = admitted.get("raid_runtime")
    admitted_runtime = admitted_runtime if isinstance(admitted_runtime, Mapping) else {}
    admitted_receipt = admitted_runtime.get("admission_receipt")
    admitted_receipt = admitted_receipt if isinstance(admitted_receipt, Mapping) else {}
    admitted_members = admitted_receipt.get("members")
    admitted_members = admitted_members if isinstance(admitted_members, list) else []
    expected_by_slot = {
        str(member.get("roster_slot_id") or ""): str(
            member.get("gear_manifest_sha256") or ""
        ).lower()
        for member in admitted_members
        if isinstance(member, Mapping)
    }
    for candidate in candidates:
        if candidate == admitted:
            continue
        runtime = candidate.get("raid_runtime")
        runtime = runtime if isinstance(runtime, Mapping) else {}
        receipt = runtime.get("admission_receipt")
        receipt = receipt if isinstance(receipt, Mapping) else {}
        members = receipt.get("members")
        members = members if isinstance(members, list) else []
        complete_observations = 0
        for member in members:
            if not isinstance(member, Mapping):
                continue
            slot = str(member.get("roster_slot_id") or "")
            current = str(member.get("current_gear_manifest_sha256") or "").lower()
            expected = expected_by_slot.get(slot, "")
            if len(current) != 64 or len(expected) != 64:
                continue
            complete_observations += 1
            if current != expected or member.get("gear_identity_current_matches_admission") is False:
                return True
        # An explicit aggregate mismatch is actionable only when the row also
        # carries complete current gear observations.  Cleanup rows otherwise
        # report false/empty values after the bots have been released.
        if (
            complete_observations == len(expected_by_slot)
            and complete_observations > 0
            and receipt.get("all_current_gear_matches_admission") is False
        ):
            return True
    return False


def _status_payloads(payloads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(payload)
        for payload in payloads
        if payload.get("action") == "botauto_status"
        or {"active_bots", "target_bots"} <= set(payload)
    ]


def _raw_cleanup_projection(
    payloads: Sequence[Mapping[str, Any]], admission_status: Mapping[str, Any]
) -> dict[str, Any]:
    statuses = _status_payloads(payloads)
    inactive = [
        status
        for status in statuses
        if status.get("active") is False
        and _integer(status.get("active_bots")) == 0
        and _integer(status.get("lease_count")) == 0
    ]
    status = (inactive or statuses or [{}])[-1]
    cohort_id = str(
        status.get("cohort_id") or admission_status.get("cohort_id") or ""
    )
    registries = [
        payload
        for payload in payloads
        if payload.get("action") == "botauto_cohorts"
        and isinstance(payload.get("cohorts"), list)
    ]
    registry = registries[-1] if registries else {}
    calibration_attempt = any(
        payload.get("action") in {
            "botauto_calibrate_start",
            "botauto_calibrate_status",
        }
        and str(payload.get("cohort_id") or "") == cohort_id
        for payload in payloads
    )
    calibration_stops = [
        payload
        for payload in payloads
        if payload.get("action") == "botauto_calibrate_stop"
        and str(payload.get("cohort_id") or "") == cohort_id
    ]
    calibration_stop = calibration_stops[-1] if calibration_stops else {}
    fixture_cleanup_submitted_or_absent = bool(
        not calibration_attempt
        or calibration_stop.get("fixture_cleanup_submitted_or_absent") is True
    )
    cohort_row = next(
        (
            row
            for row in registry.get("cohorts") or []
            if isinstance(row, Mapping)
            and str(row.get("cohort_id") or "") == cohort_id
        ),
        {},
    )
    facts = {
        "active": status.get("active") is True,
        "active_bots": _integer(status.get("active_bots")),
        "lease_count": _integer(status.get("lease_count")),
        "party_bot_count": _integer(cohort_row.get("party_bot_count")),
        "server_epoch": _integer(registry.get("server_epoch")),
        "status_server_epoch": _integer(status.get("server_epoch")),
        "status_attempt_id": _integer(status.get("attempt_id")),
        "fixture_cleanup_required": calibration_attempt,
        "fixture_cleanup_submitted_or_absent": (
            fixture_cleanup_submitted_or_absent
        ),
    }
    registry_verified = (
        bool(cohort_id)
        and bool(cohort_row)
        and cohort_row.get("active") is False
        and _integer(cohort_row.get("lease_count")) == 0
        and _integer(cohort_row.get("party_bot_count")) == 0
    )
    return {
        "cohort_id": cohort_id,
        "facts": facts,
        "inactive_after_attempt": (
            facts["active"] is False
            and facts["active_bots"] == 0
            and facts["lease_count"] == 0
            and facts["party_bot_count"] == 0
            and facts["server_epoch"] > 0
            and facts["status_server_epoch"] == facts["server_epoch"]
            and facts["status_attempt_id"] > 0
            and fixture_cleanup_submitted_or_absent
            and registry_verified
        ),
        "registry_verified": registry_verified,
    }


def _report_cleanup_projection(session: Mapping[str, Any]) -> dict[str, Any]:
    cleanup = session.get("cleanup")
    cleanup = cleanup if isinstance(cleanup, Mapping) else {}
    verified = session.get("inactive_after_attempt") is True
    fixture_cleanup_required = cleanup.get("fixture_cleanup_required") is True
    fixture_cleanup_submitted_or_absent = bool(
        not fixture_cleanup_required
        or cleanup.get("fixture_cleanup_submitted_or_absent") is True
    )
    return {
        "cohort_id": str(session.get("cohort_id") or ""),
        "facts": {
            "active": cleanup.get("active") is True,
            "active_bots": _integer(cleanup.get("active_bots")),
            "lease_count": _integer(cleanup.get("lease_count")),
            "party_bot_count": _integer(cleanup.get("party_bot_count")),
            "server_epoch": _integer(cleanup.get("server_epoch")),
            "status_server_epoch": _integer(session.get("server_epoch")),
            "status_attempt_id": _integer(session.get("runtime_attempt_id")),
            "fixture_cleanup_required": fixture_cleanup_required,
            "fixture_cleanup_submitted_or_absent": (
                fixture_cleanup_submitted_or_absent
            ),
        },
        "inactive_after_attempt": verified
        and fixture_cleanup_submitted_or_absent,
        # The controller sets inactive_after_attempt only after it has checked
        # the cohort-registry row, so this claim must match the raw registry.
        "registry_verified": verified,
    }


def _gear_manifest_projection(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return []
        gems = item.get("gem_item_ids")
        if not isinstance(gems, list):
            return []
        rows.append(
            {
                "slot": _integer(item.get("slot")) if "slot" in item else -1,
                "item_id": _integer(item.get("item_id")),
                "enchant_id": _integer(item.get("enchant_id")),
                "reforge_id": _integer(item.get("reforge_id")),
                "gem_item_ids": [_integer(gem) for gem in gems],
            }
        )
    rows.sort(key=lambda row: row["slot"])
    return rows


def _member_projection(member: Mapping[str, Any]) -> dict[str, Any]:
    talent_ids = member.get("active_talent_spell_ids")
    if not isinstance(talent_ids, list):
        talent_ids = []
    gear_manifest = _gear_manifest_projection(member.get("gear_manifest"))
    return {
        "guid": _integer(member.get("guid")),
        "roster_slot_id": str(member.get("roster_slot_id") or ""),
        "role": str(member.get("role") or ""),
        "class_spec": str(member.get("class_spec") or ""),
        "class_id": _integer(member.get("class_id")),
        "active_spec_index": _integer(member.get("active_spec_index")),
        "primary_talent_tree_id": _integer(member.get("primary_talent_tree_id")),
        "active_talent_count": _integer(member.get("active_talent_count")),
        "active_talent_spell_ids": sorted(_integer(value) for value in talent_ids),
        "gear_profile_id": str(member.get("gear_profile_id") or ""),
        "gear_item_count": _integer(member.get("gear_item_count")),
        "gear_manifest": gear_manifest,
        "gear_manifest_sha256": str(
            member.get("gear_manifest_sha256") or ""
        ).lower(),
        "current_gear_manifest_sha256": str(
            member.get("current_gear_manifest_sha256") or ""
        ).lower(),
        "gear_identity_current_matches_admission": member.get(
            "gear_identity_current_matches_admission"
        ) is True,
        "group_guid": _integer(member.get("group_guid")),
        "leader_guid": _integer(member.get("leader_guid")),
        "map_id": _integer(member.get("map_id")),
        "instance_id": _integer(member.get("instance_id")),
        "expected_difficulty": _integer(member.get("expected_difficulty")),
        "player_difficulty": _integer(member.get("player_difficulty")),
        "map_difficulty": _integer(member.get("map_difficulty")),
        "spawn_x": _number(member.get("spawn_x")),
        "spawn_y": _number(member.get("spawn_y")),
        "spawn_z": _number(member.get("spawn_z")),
        "server_provisioned": member.get("server_provisioned") is True,
        "initial_baseline_normalized": member.get("initial_baseline_normalized")
        is True,
        "initial_alive_state_verified": member.get("initial_alive_state_verified")
        is True,
    }


def _admission_projection(status: Mapping[str, Any]) -> dict[str, Any]:
    runtime = status.get("raid_runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    receipt = runtime.get("admission_receipt")
    receipt = receipt if isinstance(receipt, Mapping) else {}
    members_value = receipt.get("members")
    members = [
        _member_projection(row)
        for row in members_value
        if isinstance(row, Mapping)
    ] if isinstance(members_value, list) else []
    members.sort(key=lambda row: (row["roster_slot_id"], row["guid"]))
    exact_party = status.get("exact_party_class_specs")
    exact_party = [str(value) for value in exact_party] if isinstance(exact_party, list) else []
    member_specs_by_slot = [
        row["class_spec"]
        for row in sorted(
            members,
            key=lambda row: (
                {
                    "party_tank_1": 0,
                    "party_healer_1": 1,
                    "party_dps_1": 2,
                    "party_dps_2": 3,
                    "party_dps_3": 4,
                }.get(row["roster_slot_id"], 99),
                row["roster_slot_id"],
            ),
        )
    ]
    members_ready = len(members) == 5 and all(
        row["guid"] > 0
        and row["roster_slot_id"]
        and row["class_spec"]
        and row["class_id"] > 0
        and row["primary_talent_tree_id"] > 0
        and row["active_talent_count"] > 0
        and row["active_talent_count"] == len(row["active_talent_spell_ids"])
        and bool(row["gear_profile_id"])
        and row["gear_item_count"] >= 16
        and row["gear_item_count"] == len(row["gear_manifest"])
        and len({item["slot"] for item in row["gear_manifest"]})
        == len(row["gear_manifest"])
        and all(
            0 <= item["slot"] <= 18
            and item["item_id"] > 0
            and all(gem >= 0 for gem in item["gem_item_ids"])
            for item in row["gear_manifest"]
        )
        and len(row["gear_manifest_sha256"]) == 64
        and row["gear_manifest_sha256"] == canonical_sha256(row["gear_manifest"])
        and row["current_gear_manifest_sha256"] == row["gear_manifest_sha256"]
        and row["gear_identity_current_matches_admission"]
        and row["server_provisioned"]
        and row["initial_baseline_normalized"]
        and row["initial_alive_state_verified"]
        and row["expected_difficulty"] == 1
        and row["player_difficulty"] == 1
        and row["map_difficulty"] == 1
        for row in members
    )
    member_guids = [row["guid"] for row in members]
    member_slots = [row["roster_slot_id"] for row in members]
    group_guid = _integer(runtime.get("group_guid"))
    leader_guid = _integer(runtime.get("leader_guid"))
    instance_id = _integer(runtime.get("instance_id"))
    entrance_map_id = _integer(receipt.get("entrance_map_id"))
    server_epoch = _integer(status.get("server_epoch"))
    receipt_server_epoch = _integer(receipt.get("server_epoch"))
    receipt_identity_ready = (
        _integer(receipt.get("attempt_id")) == _integer(status.get("attempt_id"))
        and server_epoch > 0
        and receipt_server_epoch == server_epoch
        and _integer(receipt.get("profile_generation"))
        == _integer(status.get("profile_generation"))
        and str(receipt.get("profile_content_hash") or "")
        == str(status.get("profile_content_hash") or "")
        and len(str(receipt.get("identity_catalog_source_sha256") or "")) == 64
        and len(str(receipt.get("route_manifest_sha256") or "")) == 64
        and group_guid > 0
        and leader_guid > 0
        and instance_id > 0
        and entrance_map_id == 725
        and _integer(receipt.get("recovery_entrance_area_trigger_id")) > 0
        and _integer(receipt.get("recovery_entrance_source_map_id")) > 0
        and _integer(receipt.get("recovery_entrance_target_map_id")) > 0
        and len(member_guids) == len(set(member_guids))
        and len(member_slots) == len(set(member_slots))
        and all(
            row["group_guid"] == group_guid
            and row["leader_guid"] == leader_guid
            and row["instance_id"] == instance_id
            and row["map_id"] == entrance_map_id
            for row in members
        )
    )
    exact_party_matches = bool(exact_party) and exact_party == member_specs_by_slot
    gear_identity = [
        {
            "roster_slot_id": row["roster_slot_id"],
            "class_spec": row["class_spec"],
            "gear_profile_id": row["gear_profile_id"],
            "gear_manifest_sha256": row["gear_manifest_sha256"],
        }
        for row in members
    ]
    player_like_ready = (
        str(runtime.get("admission_phase") or "") == "active"
        and runtime.get("server_provisioning_complete") is True
        and runtime.get("bot_actions_enabled") is True
        and runtime.get("difficulty_matches") is True
        and _integer(runtime.get("expected_difficulty")) == 1
        and _integer(runtime.get("group_difficulty")) == 1
        and _integer(runtime.get("map_difficulty")) == 1
        and _integer(runtime.get("expected_size")) == 5
        and _integer(status.get("lease_count")) == 5
        and _integer(status.get("bots")) == 5
        and str(receipt.get("scenario_id") or "") == "stonecore_5h"
        and str(receipt.get("runtime_profile") or "") == "stonecore_5h"
        and receipt.get("bot_actions_enabled_at_commit") is True
        and receipt.get("all_current_gear_matches_admission") is True
        and members_ready
        and receipt_identity_ready
        and exact_party_matches
    )
    return {
        "cohort_id": str(status.get("cohort_id") or ""),
        "server_epoch": server_epoch,
        "attempt_id": _integer(status.get("attempt_id")),
        "profile_generation": _integer(status.get("profile_generation")),
        "profile_content_hash": str(status.get("profile_content_hash") or ""),
        "pool_tag_filter": str(status.get("pool_tag_filter") or ""),
        "exact_party_class_specs": exact_party,
        "exact_party_sha256": str(status.get("exact_party_sha256") or ""),
        "member_specs_by_slot": member_specs_by_slot,
        "exact_party_matches_receipt": exact_party_matches,
        "admission_phase": str(runtime.get("admission_phase") or ""),
        "server_provisioning_complete": runtime.get("server_provisioning_complete")
        is True,
        "bot_actions_enabled": runtime.get("bot_actions_enabled") is True,
        "difficulty_matches": runtime.get("difficulty_matches") is True,
        "expected_difficulty": _integer(runtime.get("expected_difficulty")),
        "group_difficulty": _integer(runtime.get("group_difficulty")),
        "map_difficulty": _integer(runtime.get("map_difficulty")),
        "expected_size": _integer(runtime.get("expected_size")),
        "group_guid": group_guid,
        "leader_guid": leader_guid,
        "instance_id": instance_id,
        "scenario_id": str(receipt.get("scenario_id") or ""),
        "runtime_profile": str(receipt.get("runtime_profile") or ""),
        "identity_catalog_source_sha256": str(
            receipt.get("identity_catalog_source_sha256") or ""
        ),
        "receipt_attempt_id": _integer(receipt.get("attempt_id")),
        "receipt_server_epoch": receipt_server_epoch,
        "receipt_profile_generation": _integer(receipt.get("profile_generation")),
        "receipt_profile_content_hash": str(
            receipt.get("profile_content_hash") or ""
        ),
        "route_manifest_sha256": str(receipt.get("route_manifest_sha256") or ""),
        "entrance_map_id": entrance_map_id,
        "entrance_x": _number(receipt.get("entrance_x")),
        "entrance_y": _number(receipt.get("entrance_y")),
        "entrance_z": _number(receipt.get("entrance_z")),
        "recovery_entrance_area_trigger_id": _integer(
            receipt.get("recovery_entrance_area_trigger_id")
        ),
        "recovery_entrance_source_map_id": _integer(
            receipt.get("recovery_entrance_source_map_id")
        ),
        "recovery_entrance_target_map_id": _integer(
            receipt.get("recovery_entrance_target_map_id")
        ),
        "bot_actions_enabled_at_commit": receipt.get("bot_actions_enabled_at_commit")
        is True,
        "all_current_gear_matches_admission": receipt.get(
            "all_current_gear_matches_admission"
        ) is True,
        "gear_identity": gear_identity,
        "gear_identity_sha256": canonical_sha256(gear_identity)
        if gear_identity else "",
        "receipt_identity_ready": receipt_identity_ready,
        "members": members,
        "receipt_sha256": canonical_sha256(receipt) if receipt else "",
        "player_like_ready": player_like_ready,
        # This is populated from the later raw status stream only.  A report's
        # immutable admission snapshot has no post-admission drift claim.
        "post_admission_gear_drift": False,
    }


def _expected_route_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    routes_value = manifest.get("routes")
    routes = routes_value if isinstance(routes_value, list) else []
    expected: list[dict[str, Any]] = []
    bosses: list[dict[str, Any]] = []
    for ordinal, route in enumerate(routes, 1):
        if not isinstance(route, Mapping):
            continue
        row = {
            "route_node_id": str(route.get("route_node_id") or ""),
            "route_generation": _integer(route.get("route_generation")) or ordinal,
        }
        if not row["route_node_id"]:
            continue
        expected.append(row)
        if str(route.get("kind") or "") == "boss":
            bosses.append(row)
    return {
        "scenario_id": str(manifest.get("scenario_id") or ""),
        "manifest_sha256": canonical_sha256(manifest),
        "route_count": len(expected),
        "boss_route_count": len(bosses),
        "expected_route_scopes": expected,
        "expected_boss_scopes": bosses,
    }


def _forbidden_assists(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    rows: set[tuple[str, str]] = set()
    for entry in entries:
        action = str(entry.get("action") or "")
        result = str(entry.get("result") or "")
        if action in {"teacher_kill_assist", "validation_route_teacher_assist"} or any(
            token in result
            for token in ("teacher_assist", "forced_kill", "force_terminal", "force_damage")
        ):
            rows.add((action, result))
    return [
        {"action": action, "result": result}
        for action, result in sorted(rows)
    ]


def _stonecore_raw_decisive(
    payloads: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    entries = _trace_entries(payloads)
    status = _status_with_admission(payloads)
    status_candidates = _admission_status_candidates(payloads)
    terminal_status = status_candidates[-1] if status_candidates else status
    status_route = terminal_status.get("validation_route")
    status_route = status_route if isinstance(status_route, Mapping) else {}
    terminals = _scope_rows(entries, {"validation_route_terminal"})
    terminal_scopes = {
        (row["route_node_id"], row["route_generation"]) for row in terminals
    }
    for row in status_route.get("terminal_evidence") or []:
        if not isinstance(row, Mapping):
            continue
        scope = (str(row.get("route_node_id") or ""), _integer(row.get("route_generation")))
        if scope[0] and scope[1] > 0:
            terminal_scopes.add(scope)
    terminals = [
        {"route_node_id": node_id, "route_generation": generation}
        for node_id, generation in sorted(terminal_scopes)
    ]

    boss_entries = [
        entry
        for entry in entries
        if str(entry.get("action") or "") in {"boss_killed", "raid_boss_killed"}
        and str(entry.get("result") or "") in {"ok", "confirmed_unit_death"}
        and _integer(entry.get("target_id")) > 0
    ]
    bosses = _scope_rows(boss_entries, {"boss_killed", "raid_boss_killed"})
    boss_scopes = {(row["route_node_id"], row["route_generation"]) for row in bosses}
    for row in status_route.get("boss_death_evidence") or []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("result") or "") not in {"ok", "confirmed_unit_death"} or _integer(
            row.get("target_id")
        ) <= 0:
            continue
        scope = (str(row.get("route_node_id") or ""), _integer(row.get("route_generation")))
        if scope[0] and scope[1] > 0:
            boss_scopes.add(scope)
    bosses = [
        {"route_node_id": node_id, "route_generation": generation}
        for node_id, generation in sorted(boss_scopes)
    ]

    manifest_scopes = _scope_rows(entries, {"validation_route_manifest_complete"})
    if status_route.get("manifest_complete") is True:
        node_id = str(status_route.get("node_id") or "")
        generation = _integer(
            status_route.get("generation") or status_route.get("manifest_count")
        )
        if node_id and generation > 0:
            manifest_scopes = [
                {"route_node_id": node_id, "route_generation": generation}
            ]

    expected = _expected_route_projection(manifest)
    terminal_keys = {
        (row["route_node_id"], row["route_generation"]) for row in terminals
    }
    boss_keys = {(row["route_node_id"], row["route_generation"]) for row in bosses}
    missing_terminals = [
        row["route_node_id"]
        for row in expected["expected_route_scopes"]
        if (row["route_node_id"], row["route_generation"]) not in terminal_keys
    ]
    missing_bosses = [
        row["route_node_id"]
        for row in expected["expected_boss_scopes"]
        if (row["route_node_id"], row["route_generation"]) not in boss_keys
    ]
    admission = _admission_projection(status)
    admission["post_admission_gear_drift"] = _post_admission_gear_drift(payloads)
    return {
        "route_manifest": expected,
        "route_terminal_evidence": terminals,
        "real_boss_kill_evidence": bosses,
        "manifest_completion_evidence": manifest_scopes,
        "missing_terminal_route_nodes": missing_terminals,
        "missing_boss_route_nodes": missing_bosses,
        "forbidden_completion_assists": _forbidden_assists(entries),
        "admission": admission,
        "heroic_admission_verified": admission["player_like_ready"],
        "exact_party_verified": admission["player_like_ready"]
        and admission["exact_party_matches_receipt"],
    }


def _report_scope_rows(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    scopes = {
        (str(row.get("route_node_id") or ""), _integer(row.get("route_generation")))
        for row in rows
        if isinstance(row, Mapping)
    }
    return [
        {"route_node_id": node_id, "route_generation": generation}
        for node_id, generation in sorted(scopes)
        if node_id and generation > 0
    ]


_CALIBRATION_FIELDS = (
    "cohort_id",
    "phase",
    "mode",
    "target_spec",
    "failure_reason",
    "runtime_authority",
    "runtime_mode",
    "profile_content_hash",
    "reset_id",
)


def _selected_target_measurement(
    calibration: Mapping[str, Any],
) -> dict[str, Any]:
    target_guid = _integer(calibration.get("target_guid"))
    previous = calibration.get("previous_window")
    previous = previous if isinstance(previous, Mapping) else {}
    bots = previous.get("bots")
    bots = bots if isinstance(bots, list) else []
    target = next(
        (
            row
            for row in bots
            if isinstance(row, Mapping) and _integer(row.get("guid")) == target_guid
        ),
        {},
    )
    return _canonical_value(dict(target)) if isinstance(target, Mapping) else {}


def _calibration_scoring_contract(
    exact_manifests: Mapping[str, Any],
) -> Mapping[str, Any]:
    contract = exact_manifests.get("calibration_scoring_contract")
    return contract if isinstance(contract, Mapping) else {}


def _generated_reference_scoring_authority(target_spec: str) -> dict[str, Any]:
    """Resolve the sole numeric DPS authority from verified generated artifacts."""
    binding = load_reference_request_binding(target_spec)
    facts = verified_reference_request_runtime_facts(binding)
    valid = bool(binding.get("valid") is True)
    reference_value = _number(facts.get("reference_value")) if valid else 0.0
    result_key = str(facts.get("reference_result_key") or "") if valid else ""
    catalog_sha256 = (
        str(facts.get("reference_request_catalog_sha256") or "")
        if valid
        else ""
    )
    valid = bool(
        valid
        and reference_value > 0.0
        and result_key
        and len(catalog_sha256) == 64
    )
    return {
        "valid": valid,
        "reference_value": reference_value if valid else 0.0,
        "reference_result_key": result_key if valid else "",
        "reference_basis": (
            "generated_verified_live_compatible_wowsims_dps"
            if valid
            else "generated_reference_unavailable"
        ),
        "reference_request_catalog_sha256": (
            catalog_sha256 if valid else ""
        ),
    }


def _derive_raw_reference_compatibility(
    calibration: Mapping[str, Any],
    target: Mapping[str, Any],
    _contract: Mapping[str, Any],
) -> dict[str, Any]:
    normalization = calibration.get("normalization")
    normalization = normalization if isinstance(normalization, Mapping) else {}
    setup = target.get("reference_setup")
    setup = setup if isinstance(setup, Mapping) else {}
    target_spec = str(calibration.get("target_spec") or "")
    request_binding = load_reference_request_binding(target_spec)
    fixture_binding = load_fixture_contract_binding(target_spec)
    request_facts = verified_reference_request_runtime_facts(request_binding)
    expected_manifest = request_binding.get("comparison_manifest")
    expected_manifest = (
        expected_manifest if isinstance(expected_manifest, Mapping) else {}
    )
    request_facts["fixture_contract_sha256"] = fixture_binding.get(
        "content_sha256"
    )
    request_facts["fixture_contract_binding_valid"] = fixture_binding.get(
        "valid"
    )
    return derive_reference_condition_compatibility(
        target_spec=target_spec,
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=normalization,
        target_observation=target,
        runtime_facts={
            **request_facts,
            "observed_gear_manifest_sha256": observed_gear_manifest_sha256(
                target
            ),
        },
        expected_manifest=expected_manifest,
    )


def _single_target_fixture_evaluation(
    calibration: Mapping[str, Any], target: Mapping[str, Any]
) -> dict[str, Any]:
    if str(calibration.get("mode") or "") != "single_target_300":
        return {}
    fixture = calibration.get("fixture_target")
    fixture = fixture if isinstance(fixture, Mapping) else {}
    runtime_guid = _integer(fixture.get("runtime_guid"))
    primary_guid = _integer(target.get("primary_target_guid"))
    damage = _integer(target.get("damage"))
    primary_damage = _integer(target.get("primary_target_damage"))
    off_target_damage = _integer(target.get("off_target_damage"))
    observed_targets = _integer(target.get("observed_distinct_damage_targets"))
    target_spec = str(calibration.get("target_spec") or "")
    expected_lane = expected_calibration_profile_lane(target_spec)
    try:
        computed_distance = math.dist(
            tuple(float(fixture[name]) for name in ("x", "y", "z")),
            tuple(
                float(fixture[name])
                for name in ("bot_spawn_x", "bot_spawn_y", "bot_spawn_z")
            ),
        )
    except (KeyError, TypeError, ValueError):
        computed_distance = -1.0
    checks = {
        "isolated_single_target": fixture.get("isolated_single_target") is True,
        "training_dummy_entry": _integer(fixture.get("entry")) == 44548,
        "runtime_guid_present": runtime_guid > 0,
        "map_zero": _integer(fixture.get("map_id")) == 0,
        "fixture_x_pinned": abs(_number(fixture.get("x")) - (-9140.0)) <= 0.01,
        "fixture_y_pinned": abs(_number(fixture.get("y")) - 520.0) <= 0.01,
        "fixture_z_bounded": 145.0 <= _number(fixture.get("z")) <= 147.0,
        "hostile_clearance": _number(
            fixture.get("nearest_other_hostile_clearance")
        ) >= 45.0,
        "provisioned_before_scoring": (
            fixture.get("provisioned_before_scoring") is True
            and _integer(fixture.get("provisioned_at_ms")) > 0
        ),
        "fixture_profile_lane_matches_target_spec": (
            bool(expected_lane)
            and str(fixture.get("profile_lane") or "") == expected_lane
        ),
        "fixture_distance_recomputed": (
            math.isfinite(computed_distance)
            and computed_distance > 0.0
            and abs(
                computed_distance - _number(fixture.get("bot_target_distance"))
            ) <= 0.01
        ),
        "fixture_geometry_validated": single_target_fixture_geometry_valid(
            fixture, target_spec
        ),
        "native_path_reachable": fixture.get("native_path_reachable") is True,
        "native_dry_land": fixture.get("native_dry_land") is True,
        "melee_native_reach": (
            expected_lane != "melee"
            or fixture.get("native_melee_reachable") is True
        ),
        "primary_guid_bound": runtime_guid == primary_guid,
        "primary_damage_is_scored_damage": primary_damage == damage,
        "zero_off_target_damage": off_target_damage == 0,
        "one_observed_damage_target": observed_targets == 1,
        "one_scored_target": _integer(target.get("target_count")) == 1,
    }
    return {
        "fixture_target": _canonical_value(dict(fixture)),
        "checks": checks,
        "reasons": [name for name, passed in checks.items() if not passed],
        "passed": all(checks.values()),
    }


def _raw_target_scoring(
    calibration: Mapping[str, Any],
    target: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    elapsed_seconds = _number(target.get("elapsed_seconds"))
    scored_seconds = _number(calibration.get("scored_seconds"))
    damage = _integer(target.get("damage"))
    pet_damage = _integer(target.get("pet_damage"))
    serialized_elapsed_dps, exact_elapsed_dps, dps_absolute_error = (
        _validated_elapsed_dps(target)
    )
    quality = target.get("quality_metrics")
    quality = quality if isinstance(quality, Mapping) else {}
    active_uptime = _number(quality.get("active_uptime_ratio"))
    active_seconds = elapsed_seconds * active_uptime
    active_uptime_fraction = _exact_fraction(
        active_uptime, field="active_uptime_ratio"
    )
    exact_active_dps = (
        exact_elapsed_dps / active_uptime_fraction
        if active_uptime_fraction > 0
        else Fraction(0)
    )
    reference_authority = _generated_reference_scoring_authority(
        str(calibration.get("target_spec") or "")
    )
    if reference_authority.get("valid") is not True:
        raise RawEvidenceBindingError(
            "calibration has no verified generated DPS reference"
        )
    reference_value = _number(reference_authority.get("reference_value"))
    hard_ratio = _number(contract.get("hard_reference_ratio"))
    optimization_ratio = _number(contract.get("optimization_reference_ratio"))
    (
        policy_hard_ratio,
        policy_optimization_ratio,
        hard_ratio_fraction,
        optimization_ratio_fraction,
    ) = calibration_reference_thresholds(contract.get("policy_sha256"))
    if hard_ratio != policy_hard_ratio or optimization_ratio != policy_optimization_ratio:
        raise RawEvidenceBindingError(
            "calibration scoring contract does not match the authoritative policy"
        )
    reference_fraction = _exact_fraction(
        reference_value, field="calibration reference_value"
    )
    exact_reference_ratio = (
        exact_elapsed_dps / reference_fraction
        if reference_fraction > 0
        else Fraction(0)
    )
    fixture = _single_target_fixture_evaluation(calibration, target)
    reference_compatibility = _derive_raw_reference_compatibility(
        calibration, target, contract
    )
    return {
        "target_guid": _integer(target.get("guid")),
        "elapsed_seconds": elapsed_seconds,
        "scored_seconds": scored_seconds,
        "active_seconds": active_seconds,
        "active_uptime_ratio": active_uptime,
        "damage": damage,
        "pet_damage": pet_damage,
        "primary_target_guid": _integer(target.get("primary_target_guid")),
        "primary_target_damage": _integer(target.get("primary_target_damage")),
        "off_target_damage": _integer(target.get("off_target_damage")),
        "observed_distinct_damage_targets": _integer(
            target.get("observed_distinct_damage_targets")
        ),
        "isolated_fixture_evaluation": fixture,
        "reference_condition_compatibility": reference_compatibility,
        "elapsed_dps": float(exact_elapsed_dps),
        "serialized_elapsed_dps": serialized_elapsed_dps,
        "exact_elapsed_dps": _fraction_projection(exact_elapsed_dps),
        "unrounded_damage_over_elapsed_dps": float(exact_elapsed_dps),
        "dps_absolute_error": float(dps_absolute_error),
        "dps_arithmetic_contract": {
            "formula": "damage / elapsed_seconds",
            "serialized_decimal_places": DPS_SERIALIZED_DECIMAL_PLACES,
            "absolute_tolerance": DPS_SERIALIZED_ABSOLUTE_TOLERANCE,
            "validated": True,
        },
        "active_dps": float(exact_active_dps),
        "exact_active_dps": _fraction_projection(exact_active_dps),
        "active_dps_arithmetic_contract": {
            "formula": "exact_damage_over_elapsed_dps / active_uptime_ratio",
            "absolute_tolerance": DERIVED_ACTIVE_DPS_ABSOLUTE_TOLERANCE,
            "validated": True,
        },
        "reference_value": reference_value,
        "reference_basis": str(reference_authority["reference_basis"]),
        "reference_id": str(reference_authority["reference_result_key"]),
        "reference_authority_valid": reference_authority["valid"],
        "reference_request_catalog_sha256": str(
            reference_authority["reference_request_catalog_sha256"]
        ),
        "hard_reference_ratio": hard_ratio,
        "optimization_reference_ratio": optimization_ratio,
        "reference_ratio": round(float(exact_reference_ratio), 6),
        "exact_reference_ratio": _fraction_projection(exact_reference_ratio),
        "reference_ratio_arithmetic_contract": {
            "formula": "exact_damage_over_elapsed_dps / reference_value",
            "serialized_decimal_places": DERIVED_RATIO_SERIALIZED_DECIMAL_PLACES,
            "absolute_tolerance": DERIVED_RATIO_ABSOLUTE_TOLERANCE,
            "threshold_comparison": "exact_rational_before_serialization",
            "validated": True,
        },
        "hard_floor_passed": exact_reference_ratio >= hard_ratio_fraction,
        "optimization_target_met": (
            exact_reference_ratio >= optimization_ratio_fraction
        ),
        "attempts": _integer(target.get("attempts")),
        "successes": _integer(target.get("successes")),
        "result_counts": _canonical_value(target.get("result_counts") or {}),
        "action_attempts": _canonical_value(target.get("action_attempts") or []),
        "spell_damage": _canonical_value(target.get("spell_damage") or []),
        "illegal_action_count": _integer(quality.get("illegal_action_count")),
        "cast_failure_ratio": _number(quality.get("cast_failure_ratio")),
        "record_sha256": str(contract.get("record_sha256") or ""),
        "policy_sha256": str(contract.get("policy_sha256") or ""),
    }


def _reported_target_scoring(
    report: Mapping[str, Any],
    calibration: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    record = report.get("role_calibration_record")
    record = record if isinstance(record, Mapping) else {}
    metrics = record.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    window = record.get("window")
    window = window if isinstance(window, Mapping) else {}
    evaluation = report.get("role_calibration_evaluation")
    evaluation = evaluation if isinstance(evaluation, Mapping) else {}
    quality = target.get("quality_metrics")
    quality = quality if isinstance(quality, Mapping) else {}
    elapsed_seconds = _number(target.get("elapsed_seconds"))
    active_uptime = _number(quality.get("active_uptime_ratio"))
    serialized_elapsed_dps, exact_elapsed_dps, dps_absolute_error = (
        _validated_elapsed_dps(target)
    )
    exact_active_dps = (
        exact_elapsed_dps
        / _exact_fraction(active_uptime, field="active_uptime_ratio")
        if active_uptime > 0
        else Fraction(0)
    )
    if not record:
        elapsed_dps = serialized_elapsed_dps
        active_dps = float(exact_active_dps)
        scored_seconds = _number(calibration.get("scored_seconds"))
    else:
        elapsed_dps = _number(metrics.get("elapsed_dps"))
        active_dps = _number(metrics.get("active_dps"))
        scored_seconds = _number(window.get("scored_duration_seconds"))
        measured_value = _number(metrics.get("measured_value"))
        if abs(elapsed_dps - float(exact_elapsed_dps)) > DPS_SERIALIZED_ABSOLUTE_TOLERANCE:
            raise RawEvidenceBindingError(
                "role calibration elapsed_dps does not match validated target DPS"
            )
        if abs(measured_value - float(exact_elapsed_dps)) > DPS_SERIALIZED_ABSOLUTE_TOLERANCE:
            raise RawEvidenceBindingError(
                "role calibration measured_value does not match validated target DPS"
            )
        _validated_reported_active_dps(
            observed_active_dps=active_dps,
            exact_elapsed_dps=exact_elapsed_dps,
            active_uptime=active_uptime,
        )
    reference_authority = _generated_reference_scoring_authority(
        str(calibration.get("target_spec") or "")
    )
    reference_value = _number(reference_authority.get("reference_value"))
    if record:
        if reference_authority.get("valid") is not True:
            raise RawEvidenceBindingError(
                "role calibration record has no verified generated DPS reference"
            )
        if not _positive_numbers_equal(
            metrics.get("reference_value"), reference_value
        ):
            raise RawEvidenceBindingError(
                "role calibration reference_value does not match verified generated result"
            )
        if metrics.get("reference_basis") != reference_authority.get(
            "reference_basis"
        ):
            raise RawEvidenceBindingError(
                "role calibration reference_basis does not identify the verified generated result"
            )
    reference_fraction = _exact_fraction(
        reference_value, field="role calibration reference_value"
    )
    exact_reference_ratio = (
        exact_elapsed_dps / reference_fraction
        if reference_fraction > 0
        else Fraction(0)
    )
    serialized_reference_ratio = round(
        float(exact_reference_ratio), DERIVED_RATIO_SERIALIZED_DECIMAL_PLACES
    )
    reported_reference_ratio = _number(evaluation.get("reference_ratio"))
    (
        hard_ratio,
        optimization_ratio,
        hard_ratio_fraction,
        optimization_ratio_fraction,
    ) = calibration_reference_thresholds(
        evaluation.get("policy_sha256") if record else None
    )
    expected_hard_passed = exact_reference_ratio >= hard_ratio_fraction
    expected_optimization_met = exact_reference_ratio >= optimization_ratio_fraction
    if record:
        if (
            abs(reported_reference_ratio - serialized_reference_ratio)
            > DERIVED_RATIO_ABSOLUTE_TOLERANCE
        ):
            raise RawEvidenceBindingError(
                "role calibration reference_ratio does not match exact DPS ratio"
            )
        if evaluation.get("hard_floor_passed") is not expected_hard_passed:
            raise RawEvidenceBindingError(
                "role calibration hard_floor_passed does not match exact DPS ratio"
            )
        if evaluation.get("optimization_target_met") is not expected_optimization_met:
            raise RawEvidenceBindingError(
                "role calibration optimization_target_met does not match exact DPS ratio"
            )
    fixture = _single_target_fixture_evaluation(calibration, target)
    stored_compatibility = record.get("reference_condition_compatibility")
    stored_compatibility = (
        stored_compatibility if isinstance(stored_compatibility, Mapping) else {}
    )
    reference_compatibility = _derive_raw_reference_compatibility(
        calibration,
        target,
        _calibration_scoring_contract(report),
    )
    if record and dict(stored_compatibility) != reference_compatibility:
        raise RawEvidenceBindingError(
            "role calibration reference conditions do not match raw server facts"
        )
    return {
        "target_guid": _integer(target.get("guid")),
        "elapsed_seconds": elapsed_seconds,
        "scored_seconds": scored_seconds,
        "active_seconds": elapsed_seconds * active_uptime,
        "active_uptime_ratio": active_uptime,
        "damage": _integer(target.get("damage")),
        "pet_damage": _integer(target.get("pet_damage")),
        "primary_target_guid": _integer(target.get("primary_target_guid")),
        "primary_target_damage": _integer(target.get("primary_target_damage")),
        "off_target_damage": _integer(target.get("off_target_damage")),
        "observed_distinct_damage_targets": _integer(
            target.get("observed_distinct_damage_targets")
        ),
        "isolated_fixture_evaluation": fixture,
        "reference_condition_compatibility": reference_compatibility,
        "elapsed_dps": float(exact_elapsed_dps),
        "serialized_elapsed_dps": serialized_elapsed_dps,
        "exact_elapsed_dps": _fraction_projection(exact_elapsed_dps),
        "unrounded_damage_over_elapsed_dps": float(exact_elapsed_dps),
        "dps_absolute_error": float(dps_absolute_error),
        "dps_arithmetic_contract": {
            "formula": "damage / elapsed_seconds",
            "serialized_decimal_places": DPS_SERIALIZED_DECIMAL_PLACES,
            "absolute_tolerance": DPS_SERIALIZED_ABSOLUTE_TOLERANCE,
            "validated": True,
        },
        "active_dps": float(exact_active_dps),
        "exact_active_dps": _fraction_projection(exact_active_dps),
        "active_dps_arithmetic_contract": {
            "formula": "exact_damage_over_elapsed_dps / active_uptime_ratio",
            "absolute_tolerance": DERIVED_ACTIVE_DPS_ABSOLUTE_TOLERANCE,
            "validated": True,
        },
        "reference_value": reference_value,
        "reference_basis": str(reference_authority["reference_basis"]),
        "reference_id": str(reference_authority["reference_result_key"]),
        "reference_authority_valid": reference_authority["valid"],
        "reference_request_catalog_sha256": str(
            reference_authority["reference_request_catalog_sha256"]
        ),
        "hard_reference_ratio": hard_ratio,
        "optimization_reference_ratio": optimization_ratio,
        "reference_ratio": serialized_reference_ratio,
        "exact_reference_ratio": _fraction_projection(exact_reference_ratio),
        "reference_ratio_arithmetic_contract": {
            "formula": "exact_damage_over_elapsed_dps / reference_value",
            "serialized_decimal_places": DERIVED_RATIO_SERIALIZED_DECIMAL_PLACES,
            "absolute_tolerance": DERIVED_RATIO_ABSOLUTE_TOLERANCE,
            "threshold_comparison": "exact_rational_before_serialization",
            "validated": True,
        },
        "hard_floor_passed": expected_hard_passed,
        "optimization_target_met": expected_optimization_met,
        "attempts": _integer(target.get("attempts")),
        "successes": _integer(target.get("successes")),
        "result_counts": _canonical_value(target.get("result_counts") or {}),
        "action_attempts": _canonical_value(target.get("action_attempts") or []),
        "spell_damage": _canonical_value(target.get("spell_damage") or []),
        "illegal_action_count": _integer(quality.get("illegal_action_count")),
        "cast_failure_ratio": _number(quality.get("cast_failure_ratio")),
        "record_sha256": str(evaluation.get("record_sha256") or ""),
        "policy_sha256": str(evaluation.get("policy_sha256") or ""),
    }


def _calibration_projection(calibration: Mapping[str, Any]) -> dict[str, Any]:
    target = _selected_target_measurement(calibration)
    target_guid = _integer(calibration.get("target_guid"))
    projection = {field: str(calibration.get(field) or "") for field in _CALIBRATION_FIELDS}
    projection.update(
        {
            "server_epoch": _integer(calibration.get("server_epoch")),
            "attempt_id": _integer(calibration.get("attempt_id")),
            "seed": _integer(calibration.get("seed")),
            "target_guid": target_guid,
            "window_complete": calibration.get("window_complete") is True,
            "non_certifying_assistance": calibration.get("non_certifying_assistance")
            is True,
            "generic_ml_runtime_authority": calibration.get(
                "generic_ml_runtime_authority"
            )
            is True,
            "reset_applied": calibration.get("reset_applied") is True,
            "cross_window_event_count": _integer(
                calibration.get("cross_window_event_count")
            ),
            "scored_seconds": _number(calibration.get("scored_seconds")),
            "scored_started_at_ms": _integer(
                calibration.get("scored_started_at_ms")
            ),
            "scored_ended_at_ms": _integer(calibration.get("scored_ended_at_ms")),
            "profile_generation": _integer(calibration.get("profile_generation")),
            "target_attempts": _integer(target.get("attempts")),
            "fixture_target": _canonical_value(
                calibration.get("fixture_target") or {}
            ),
        }
    )
    return projection


def _latest_calibration_status(
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Recover the latest direct or completely reassembled calibration status."""
    latest: dict[str, Any] = {}
    chunks: dict[int, Mapping[str, Any]] = {}
    expected = 0
    cohort_id = ""

    for payload in payloads:
        action = str(payload.get("action") or "")
        if action == "botauto_calibrate_status":
            latest = dict(payload)
            chunks = {}
            expected = 0
            cohort_id = str(payload.get("cohort_id") or "")
            continue
        if action == "botauto_calibrate_status_chunk":
            try:
                sequence = int(payload.get("sequence"))
                chunk_count = int(payload.get("chunk_count"))
            except (TypeError, ValueError):
                latest = {}
                continue
            row_cohort = str(payload.get("cohort_id") or "")
            if sequence == 0:
                latest = {}
                chunks = {}
                expected = chunk_count
                cohort_id = row_cohort
            if (
                chunk_count <= 0
                or chunk_count != expected
                or sequence < 0
                or sequence >= expected
                or row_cohort != cohort_id
                or payload.get("encoding") != "base64"
                or int(payload.get("calibration_status_chunk_schema_version") or 0)
                != 1
            ):
                latest = {}
                continue
            chunks[sequence] = payload
            continue
        if action != "botauto_calibrate_status_complete":
            continue

        try:
            completion_expected = int(payload.get("chunk_count"))
            total_bytes = int(payload.get("total_bytes"))
        except (TypeError, ValueError):
            completion_expected = 0
            total_bytes = 0
        complete = (
            int(payload.get("calibration_status_chunk_schema_version") or 0) == 1
            and str(payload.get("cohort_id") or "") == cohort_id
            and completion_expected == expected
            and expected > 0
            and set(chunks) == set(range(expected))
        )
        decoded: Any = None
        if complete:
            try:
                raw = b"".join(
                    base64.b64decode(chunks[index]["data"], validate=True)
                    for index in range(expected)
                )
                decoded = json.loads(raw)
                complete = (
                    len(raw) == total_bytes
                    and isinstance(decoded, dict)
                    and decoded.get("action") == "botauto_calibrate_status"
                    and str(decoded.get("cohort_id") or "") == cohort_id
                    and bool(decoded.get("ok")) == bool(payload.get("payload_ok"))
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                complete = False
        latest = dict(decoded) if complete else {}

    return latest


def _raw_calibration_decisive(
    payloads: Sequence[Mapping[str, Any]],
    exact_manifests: Mapping[str, Any],
) -> dict[str, Any]:
    calibration = _latest_calibration_status(payloads)
    if calibration.get("active") is not True:
        calibration = {}
    observed = _calibration_projection(calibration)
    target = _selected_target_measurement(calibration)
    dps_mode = observed["mode"] in {"single_target_300", "aoe_300"}
    scoring = (
        _raw_target_scoring(
            calibration,
            target,
            _calibration_scoring_contract(exact_manifests),
        )
        if dps_mode
        else {"mode": observed["mode"], "dps_scoring_applicable": False}
    )
    return {
        "requested_calibration": {
            "mode": observed["mode"],
            "target_spec": observed["target_spec"],
            "seed": observed["seed"],
        },
        "combat_calibration": observed,
        "selected_target_measurement": target,
        "selected_target_measurement_sha256": canonical_sha256(target),
        "selected_target_scoring": scoring,
    }


def _manifest_from_exact(exact_manifests: Mapping[str, Any]) -> Mapping[str, Any]:
    manifest = exact_manifests.get("validation_route_manifest")
    return manifest if isinstance(manifest, Mapping) else {}


def projection_from_raw(
    *,
    evidence_kind: str,
    payloads: Sequence[Mapping[str, Any]],
    transport_receipt: Mapping[str, Any],
    exact_manifests: Mapping[str, Any],
) -> dict[str, Any]:
    if evidence_kind not in SUPPORTED_EVIDENCE_KINDS:
        raise RawEvidenceBindingError(f"unsupported evidence kind: {evidence_kind}")
    admission_status = _status_with_admission(payloads)
    if evidence_kind == "dps_calibration":
        decisive = _raw_calibration_decisive(payloads, exact_manifests)
    elif evidence_kind == "stonecore_5h":
        decisive = _stonecore_raw_decisive(
            payloads, _manifest_from_exact(exact_manifests)
        )
    else:
        decisive = {}
    cleanup = _raw_cleanup_projection(payloads, admission_status)
    decisive["cleanup"] = cleanup
    capture_identity = exact_manifests.get("raw_event_envelope_identity")
    capture_identity = (
        capture_identity if isinstance(capture_identity, Mapping) else {}
    )
    if evidence_kind == "dps_calibration":
        observed_identity = decisive.get("combat_calibration") or {}
    elif evidence_kind == "stonecore_5h":
        observed_identity = decisive.get("admission") or {}
    else:
        observed_identity = {}
    observed_identity = (
        observed_identity if isinstance(observed_identity, Mapping) else {}
    )
    observed_cohort_id = str(
        observed_identity.get("cohort_id") or cleanup.get("cohort_id") or ""
    )
    observed_server_epoch = _integer(observed_identity.get("server_epoch"))
    observed_attempt_id = _integer(observed_identity.get("attempt_id"))
    cohort_id = str(capture_identity.get("cohort_id") or "")
    attempt_index = capture_identity.get("attempt_index")
    cleanup_facts = cleanup.get("facts") or {}
    cleanup_facts = cleanup_facts if isinstance(cleanup_facts, Mapping) else {}
    cleanup_server_epoch = _integer(cleanup_facts.get("server_epoch"))
    cleanup_status_epoch = _integer(cleanup_facts.get("status_server_epoch"))
    cleanup_attempt_id = _integer(cleanup_facts.get("status_attempt_id"))
    if (
        capture_identity.get("schema") != "bot_raw_event_envelope_identity_v1"
        or not cohort_id
        or observed_cohort_id != cohort_id
        or cleanup.get("cohort_id") != cohort_id
        or isinstance(attempt_index, bool)
        or not isinstance(attempt_index, int)
        or attempt_index <= 0
        or observed_server_epoch <= 0
        or observed_server_epoch != cleanup_server_epoch
        or cleanup_status_epoch != observed_server_epoch
        or observed_attempt_id <= 0
        or cleanup_attempt_id != observed_attempt_id
    ):
        raise RawEvidenceBindingError(
            "raw calibration/admission, cleanup, and event envelope identities differ"
        )
    decisive["attempt_identity"] = {
        "cohort_id": cohort_id,
        "controller_attempt_index": attempt_index,
        "server_attempt_id": observed_attempt_id,
        "server_epoch": observed_server_epoch,
    }
    return {
        "schema": "bot_raw_decisive_projection_v1",
        "evidence_kind": evidence_kind,
        "transport": {
            "returncode": transport_receipt["returncode"],
            "timed_out": transport_receipt["timed_out"],
        },
        "decisive": decisive,
        "raw_transport": {
            "output_sha256": str(transport_receipt.get("output_sha256") or ""),
            "output_bytes": _integer(transport_receipt.get("output_bytes")),
            "json_payload_count": _integer(
                transport_receipt.get("json_payload_count")
            ),
        },
    }


def projection_from_report(
    report: Mapping[str, Any], *, evidence_kind: str
) -> dict[str, Any]:
    returncode = report.get("returncode")
    timed_out = report.get("timed_out")
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise RawEvidenceBindingError("report returncode must be an exact integer")
    if not isinstance(timed_out, bool):
        raise RawEvidenceBindingError("report timed_out must be an exact boolean")
    session = report.get("session")
    session = session if isinstance(session, Mapping) else {}
    if evidence_kind == "dps_calibration":
        requested = report.get("requested_calibration")
        requested = requested if isinstance(requested, Mapping) else {}
        calibration = report.get("combat_calibration")
        calibration = calibration if isinstance(calibration, Mapping) else {}
        target = _selected_target_measurement(calibration)
        mode = str(calibration.get("mode") or "")
        scoring = (
            _reported_target_scoring(report, calibration, target)
            if mode in {"single_target_300", "aoe_300"}
            else {"mode": mode, "dps_scoring_applicable": False}
        )
        decisive = {
            "requested_calibration": {
                "mode": str(requested.get("mode") or ""),
                "target_spec": str(requested.get("target_spec") or ""),
                "seed": _integer(requested.get("seed")),
            },
            "combat_calibration": _calibration_projection(calibration),
            "selected_target_measurement": target,
            "selected_target_measurement_sha256": canonical_sha256(target),
            "selected_target_scoring": scoring,
        }
    elif evidence_kind == "stonecore_5h":
        evidence = report.get("evidence")
        evidence = evidence if isinstance(evidence, Mapping) else {}
        manifest = report.get("validation_route_manifest")
        manifest = manifest if isinstance(manifest, Mapping) else {}
        admission_status = session.get("admission_status")
        admission_status = (
            admission_status if isinstance(admission_status, Mapping) else {}
        )
        admission = _admission_projection(admission_status)
        expected = _expected_route_projection(manifest)
        terminals = _report_scope_rows(evidence.get("route_terminal_evidence"))
        bosses = _report_scope_rows(evidence.get("real_boss_kill_evidence"))
        terminal_keys = {
            (row["route_node_id"], row["route_generation"]) for row in terminals
        }
        boss_keys = {
            (row["route_node_id"], row["route_generation"]) for row in bosses
        }
        forbidden = evidence.get("forbidden_completion_assists")
        forbidden = forbidden if isinstance(forbidden, list) else []
        forbidden_rows = {
            (str(row.get("action") or ""), str(row.get("result") or ""))
            for row in forbidden
            if isinstance(row, Mapping)
        }
        decisive = {
            "route_manifest": expected,
            "route_terminal_evidence": terminals,
            "real_boss_kill_evidence": bosses,
            "manifest_completion_evidence": _report_scope_rows(
                evidence.get("manifest_completion_evidence")
            ),
            "missing_terminal_route_nodes": [
                row["route_node_id"]
                for row in expected["expected_route_scopes"]
                if (row["route_node_id"], row["route_generation"])
                not in terminal_keys
            ],
            "missing_boss_route_nodes": [
                row["route_node_id"]
                for row in expected["expected_boss_scopes"]
                if (row["route_node_id"], row["route_generation"]) not in boss_keys
            ],
            "forbidden_completion_assists": [
                {"action": action, "result": result}
                for action, result in sorted(forbidden_rows)
            ],
            "admission": admission,
            "heroic_admission_verified": session.get("heroic_admission_verified")
            is True,
            "exact_party_verified": session.get("exact_party_verified") is True,
        }
    else:
        decisive = {}
    cleanup = _report_cleanup_projection(session)
    decisive["cleanup"] = cleanup
    if evidence_kind == "dps_calibration":
        observed_identity = decisive.get("combat_calibration") or {}
    elif evidence_kind == "stonecore_5h":
        observed_identity = decisive.get("admission") or {}
    else:
        observed_identity = {}
    observed_identity = (
        observed_identity if isinstance(observed_identity, Mapping) else {}
    )
    observed_cohort_id = str(
        observed_identity.get("cohort_id") or cleanup.get("cohort_id") or ""
    )
    observed_server_epoch = _integer(observed_identity.get("server_epoch"))
    observed_attempt_id = _integer(observed_identity.get("attempt_id"))
    cohort_id = str(session.get("cohort_id") or "")
    attempt_index = session.get("attempt_index")
    cleanup_facts = cleanup.get("facts") or {}
    cleanup_facts = cleanup_facts if isinstance(cleanup_facts, Mapping) else {}
    cleanup_server_epoch = _integer(cleanup_facts.get("server_epoch"))
    session_server_epoch = _integer(session.get("server_epoch"))
    session_attempt_id = _integer(session.get("runtime_attempt_id"))
    if (
        not cohort_id
        or observed_cohort_id != cohort_id
        or cleanup.get("cohort_id") != cohort_id
        or isinstance(attempt_index, bool)
        or not isinstance(attempt_index, int)
        or attempt_index <= 0
        or observed_server_epoch <= 0
        or observed_server_epoch != cleanup_server_epoch
        or session_server_epoch != observed_server_epoch
        or observed_attempt_id <= 0
        or session_attempt_id != observed_attempt_id
    ):
        raise RawEvidenceBindingError(
            "report calibration/admission, cleanup, and session identities differ"
        )
    decisive["attempt_identity"] = {
        "cohort_id": cohort_id,
        "controller_attempt_index": attempt_index,
        "server_attempt_id": observed_attempt_id,
        "server_epoch": observed_server_epoch,
    }
    return {
        "schema": "bot_acceptance_source_decisive_projection_v1",
        "evidence_kind": evidence_kind,
        "transport": {"returncode": returncode, "timed_out": timed_out},
        "decisive": decisive,
    }


def binding_projection(raw_projection: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "bot_acceptance_source_decisive_projection_v1",
        "evidence_kind": raw_projection.get("evidence_kind"),
        "transport": raw_projection.get("transport"),
        "decisive": raw_projection.get("decisive"),
    }


def semantic_binding(
    raw_projection: Mapping[str, Any], report_projection: Mapping[str, Any]
) -> dict[str, Any]:
    raw_binding = binding_projection(raw_projection)
    if raw_binding != dict(report_projection):
        raise RawEvidenceBindingError(
            "acceptance source report decisive facts do not match raw telemetry"
        )
    raw_hash = canonical_sha256(raw_projection)
    projection_hash = canonical_sha256(raw_binding)
    return {
        "schema": "bot_raw_semantic_binding_v1",
        "evidence_kind": str(raw_projection.get("evidence_kind") or ""),
        "raw_projection_sha256": raw_hash,
        "decisive_projection_sha256": projection_hash,
        "acceptance_source_projection_sha256": canonical_sha256(report_projection),
        "raw_transport_sha256": str(
            (raw_projection.get("raw_transport") or {}).get("output_sha256") or ""
        ),
    }
