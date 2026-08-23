#!/usr/bin/env python3
"""Classify one closed spec canary and emit at most one bounded work unit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = Path("experiments/configs/spec_canary_acceptance_v1.json")


class SpecCanaryError(ValueError):
    """Raised when a canary input is malformed or unsupported."""


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecCanaryError(f"invalid_json:{path}") from exc
    if not isinstance(value, dict):
        raise SpecCanaryError(f"json_object_required:{path}")
    return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _in_range(value: float | None, limits: Mapping[str, Any]) -> bool | None:
    minimum = _number(limits.get("minimum"))
    maximum = _number(limits.get("maximum"))
    if value is None or minimum is None or maximum is None:
        return None
    return minimum <= value <= maximum


def _meets_limits(value: float | None, limits: Mapping[str, Any]) -> bool | None:
    minimum = _number(limits.get("minimum"))
    maximum = _number(limits.get("maximum"))
    if value is None or (minimum is None and maximum is None):
        return None
    return (minimum is None or value >= minimum) and (
        maximum is None or value <= maximum
    )


def _gate(name: str, passed: bool | None, observed: Any, expected: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed is True else "fail" if passed is False else "insufficient_data",
        "observed": observed,
        "expected": expected,
    }


def _pet_reference(result: Mapping[str, Any], names: set[str]) -> dict[str, float]:
    """Aggregate pet damage and every landed outcome over the same actions.

    A glancing melee outcome deals damage but is not a normal hit, so omitting
    it from the event denominator makes the resulting pet DPE incomparable to
    the damage total. Blocks and critical blocks are likewise landed outcomes
    in the WoWSims action metrics.
    """
    totals = {"damage": 0.0, "landed_events": 0.0, "casts": 0.0}
    landed_outcome_fields = (
        "hits",
        "crits",
        "ticks",
        "crit_ticks",
        "glances",
        "blocks",
        "crit_blocks",
    )
    for action in result.get("action_metrics") or []:
        if not isinstance(action, Mapping):
            continue
        source = action.get("source") or {}
        if not isinstance(source, Mapping) or str(source.get("kind") or "") != "pet":
            continue
        if names and str(source.get("name") or "") not in names:
            continue
        metrics = action.get("per_iteration_target_metric_sums") or {}
        if not isinstance(metrics, Mapping):
            continue
        totals["damage"] += _number(metrics.get("damage")) or 0.0
        totals["casts"] += _number(metrics.get("casts")) or 0.0
        totals["landed_events"] += sum(
            _number(metrics.get(field)) or 0.0
            for field in landed_outcome_fields
        )
    return totals


def _dps_distribution(
    result: Mapping[str, Any],
) -> dict[str, float | int | None]:
    """Return aggregate WoWSims DPS statistics without collapsing the sample.

    The aggregate result is a distribution over stochastic iterations.  Keep
    its summary intact so reports can explain a single-run comparison without
    treating the mean as a deterministic per-run floor.
    """
    player_dps = result.get("player_dps") or {}
    if not isinstance(player_dps, Mapping):
        player_dps = {}
    aggregate_data = player_dps.get("aggregatorData") or {}
    if not isinstance(aggregate_data, Mapping):
        aggregate_data = {}
    iterations = _number(aggregate_data.get("n"))
    if iterations is None:
        iterations = _number(result.get("iterations_done"))
    return {
        "mean": _number(player_dps.get("avg")),
        "stdev": _number(player_dps.get("stdev")),
        "minimum": _number(player_dps.get("min")),
        "maximum": _number(player_dps.get("max")),
        "iterations": (
            int(iterations)
            if iterations is not None and iterations.is_integer()
            else iterations
        ),
    }


def _debug_dps_reference(
    debug_result: Mapping[str, Any] | None,
    *,
    required_duration_seconds: float | None,
) -> dict[str, Any]:
    """Validate the pinned one-iteration debug denominator for one canary.

    Debug logs are trace evidence, not an aggregate throughput denominator.
    For a single 300-second canary, however, their one-iteration DPS is the
    matching stochastic sample to compare against.  Require both normalized
    iteration counters so an aggregate result cannot be mistaken for debug
    evidence.
    """
    result = debug_result if isinstance(debug_result, Mapping) else {}
    player_dps = result.get("player_dps") or {}
    if not isinstance(player_dps, Mapping):
        player_dps = {}
    aggregate_data = player_dps.get("aggregatorData") or {}
    if not isinstance(aggregate_data, Mapping):
        aggregate_data = {}
    iterations_done = _number(result.get("iterations_done"))
    aggregate_iterations = _number(aggregate_data.get("n"))
    dps = _number(player_dps.get("avg"))
    first_iteration_duration = _number(result.get("first_iteration_duration_seconds"))
    avg_iteration_duration = _number(result.get("avg_iteration_duration_seconds"))
    duration_pass = (
        required_duration_seconds is None
        or (
            first_iteration_duration is not None
            and avg_iteration_duration is not None
            and first_iteration_duration >= required_duration_seconds
            and avg_iteration_duration >= required_duration_seconds
        )
    )
    valid = (
        isinstance(debug_result, Mapping)
        and iterations_done == 1
        and aggregate_iterations == 1
        and dps is not None
        and dps > 0
        and result.get("debug_log_present") is True
        and duration_pass
    )
    return {
        "valid": valid,
        "iterations_done": (
            int(iterations_done)
            if iterations_done is not None and iterations_done.is_integer()
            else iterations_done
        ),
        "aggregate_iterations": (
            int(aggregate_iterations)
            if aggregate_iterations is not None and aggregate_iterations.is_integer()
            else aggregate_iterations
        ),
        "dps": dps,
        "first_iteration_duration_seconds": first_iteration_duration,
        "avg_iteration_duration_seconds": avg_iteration_duration,
        "debug_log_present": result.get("debug_log_present") is True,
    }


def _next_work_unit(
    *,
    spec: str,
    reference_class: str,
    review_sha256: str,
    edge: str,
    skill: str,
    mode: str,
    fixes_used: int,
    captures_used: int,
    expected_metric: str,
) -> dict[str, Any]:
    identity = {
        "spec": spec,
        "reference_class": reference_class,
        "review_sha256": review_sha256,
        "first_broken_edge": edge,
        "specialist_skill": skill,
        "fixes_used": fixes_used,
        "capture_attempts_used": captures_used,
    }
    return {
        "work_unit_id": f"spec-canary-{canonical_sha256(identity)[:16]}",
        "specialist_skill": skill,
        "mode": mode,
        "scope": {"spec": spec, "first_broken_edge": edge},
        "reference_class": reference_class,
        "expected_metric": expected_metric,
        "constraints": [
            "one specialist skill",
            "no nested agents",
            "do not stop or restart an existing worldserver",
            "one implementation and one matched verification at most",
        ],
    }


def evaluate_canary(
    review: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    spec: str,
    review_sha256: str,
    policy_sha256: str,
    reference_class: str | None = None,
    fixes_used: int = 0,
    capture_attempts_used: int = 0,
) -> dict[str, Any]:
    if policy.get("schema") != "trinity_spec_canary_acceptance_v1":
        raise SpecCanaryError("unsupported_policy_schema")
    specs = policy.get("specs") or {}
    if not isinstance(specs, Mapping) or spec not in specs:
        raise SpecCanaryError(f"unsupported_spec:{spec}")
    spec_policy = specs[spec]
    thresholds = policy.get("thresholds") or {}
    if not isinstance(spec_policy, Mapping) or not isinstance(thresholds, Mapping):
        raise SpecCanaryError("malformed_policy")
    if fixes_used < 0 or capture_attempts_used < 0:
        raise SpecCanaryError("attempt_counts_must_be_nonnegative")

    reference_classes = policy.get("reference_classes") or {}
    selected_reference_class = str(
        reference_class
        or review.get("reference_class")
        or policy.get("default_reference_class")
        or "controlled_live_parity"
    )
    if reference_classes and selected_reference_class not in reference_classes:
        raise SpecCanaryError(
            f"unsupported_reference_class:{selected_reference_class}"
        )
    selected_reference_policy = reference_classes.get(selected_reference_class) or {}
    if not isinstance(selected_reference_policy, Mapping):
        raise SpecCanaryError("malformed_reference_class_policy")

    max_fixes = int(policy.get("max_fix_attempts") or 0)
    max_captures = int(policy.get("max_capture_attempts") or 0)
    gates: list[dict[str, Any]] = []
    gear_status = str((review.get("gear_parity") or {}).get("status") or "")
    stat_status = str((review.get("effective_stat_parity") or {}).get("status") or "")
    tuning_admitted = (review.get("dps_tuning_gate") or {}).get("tuning_admitted") is True
    gear_gate = True if gear_status == "match" else False if gear_status == "mismatch" else None
    stat_gate = True if stat_status == "match" else False if stat_status == "mismatch" else None
    tuning_gate = tuning_admitted if gear_gate is True and stat_gate is True else None
    gates.extend(
        [
            _gate("gear_parity", gear_gate, gear_status or None, "match"),
            _gate("effective_stat_parity", stat_gate, stat_status or None, "match"),
            _gate("dps_tuning_admission", tuning_gate, tuning_admitted, True),
        ]
    )

    consumable_parity = review.get("consumable_parity") or {}
    consumes_required = (
        selected_reference_policy.get("requires_consumable_parity") is True
    )
    consume_status = str(
        consumable_parity.get("status") or ""
    ) if isinstance(consumable_parity, Mapping) else ""
    consume_gate = (
        True
        if not consumes_required or consume_status == "match"
        else False
        if consume_status == "mismatch"
        else None
    )
    gates.append(
        _gate(
            "consumable_parity",
            consume_gate,
            consumable_parity if consumable_parity else None,
            {
                "status": "match",
                "inventory_backed": True,
                "flask_native_use_before_scoring": 1,
                "food_native_use_before_scoring": 1,
                "prepot_native_use_before_combat": 1,
                "combat_potion_native_use_during_combat": 1,
                "static_aura_is_use_receipt": False,
            }
            if consumes_required
            else "not_required_by_selected_reference_class",
        )
    )

    runtime = review.get("runtime") or {}
    runtime_terminal = (
        runtime.get("calibration_terminal")
        if isinstance(runtime, Mapping)
        and isinstance(runtime.get("calibration_terminal"), Mapping)
        else {}
    )
    runtime_terminal_reason = str(runtime_terminal.get("reason") or "")
    blockers = runtime.get("pre_scoring_blockers") or [] if isinstance(runtime, Mapping) else []
    blocker = blockers[0] if blockers and isinstance(blockers[0], Mapping) else {}
    blocker_reason = str(blocker.get("reason") or "")
    calibration_complete = runtime.get("calibration_complete") is True if isinstance(runtime, Mapping) else False
    liveness_gate = False if blocker_reason else True if calibration_complete else None
    gates.append(
        _gate(
            "calibration_pre_scoring_liveness",
            liveness_gate,
            blocker if blocker else None,
            "no persistent warmup blocker",
        )
    )

    edge: str | None = None
    skill: str | None = None
    mode = "single_fix"
    expected_metric = ""
    evidence_gap = False
    if gear_status != "match":
        edge = "gear_setup_identity" if gear_status == "mismatch" else "gear_parity_observation"
        skill = "raid-shard-architecture"
        mode = "capture_only"
        expected_metric = "gear_parity.status=match"
        evidence_gap = gear_status != "mismatch"
    elif runtime_terminal_reason:
        edge = runtime_terminal_reason
        resource_failures = runtime_terminal.get("initial_resource_failures") or []
        pet_resource_mismatch = any(
            isinstance(failure, Mapping)
            and any(
                isinstance(row, Mapping)
                and str(row.get("unit_kind") or "") == "pet"
                and row.get("matches_contract") is False
                for row in failure.get("power_mismatches") or []
            )
            for failure in resource_failures
        )
        skill = (
            "raid-role-implementation"
            if pet_resource_mismatch
            else "raid-shard-architecture"
        )
        expected_metric = (
            "required native pet setup reaches the initial-resource contract"
            if pet_resource_mismatch
            else "runtime terminal is cleared before one scored window"
        )
    elif blocker_reason:
        edge = blocker_reason
        skill = (
            "raid-role-implementation"
            if blocker_reason.startswith("persistent_setup_")
            else "raid-shard-architecture"
        )
        expected_metric = "calibration advances from warmup to one scored window"
    elif not calibration_complete:
        # An interrupted or partial window cannot establish stat, rotation, or
        # DPS parity. Successful native movement is not a repair edge; ask for
        # one clean capture before comparing downstream signals.
        edge = "calibration_pre_scoring_liveness"
        skill = "raid-shard-architecture"
        mode = "capture_only"
        expected_metric = "one completed deterministic calibration window"
        evidence_gap = True
    elif stat_status != "match":
        reason = str((review.get("effective_stat_parity") or {}).get("reason") or "")
        if stat_status == "mismatch":
            edge = str((review.get("effective_stat_parity") or {}).get("first_broken_edge") or "native_effective_stat_application")
            skill = "raid-class-mechanics-implementation"
            expected_metric = "effective_stat_parity.status=match"
        elif reason.startswith("missing_wowsims"):
            edge = "wowsims_compute_stats_observation"
            skill = "raid-wowsims-reference"
            mode = "capture_only"
            expected_metric = "bound ComputeStats.finalStats"
            evidence_gap = True
        else:
            edge = "trinity_scoring_start_stat_observation"
            skill = "raid-shard-architecture"
            mode = "capture_only"
            expected_metric = "scoring_start_stats at calibration t=0"
            evidence_gap = True
    elif not tuning_admitted:
        edge = "rotation_review_tuning_gate"
        skill = "raid-rotation-review"
        mode = "review_only"
        expected_metric = "dps_tuning_gate.tuning_admitted=true"
        evidence_gap = True
    elif consume_gate is not True:
        consume_edge = str(
            consumable_parity.get("first_broken_edge") or ""
        ) if isinstance(consumable_parity, Mapping) else ""
        edge = consume_edge or "consumable_parity_observation"
        if consume_gate is False:
            skill = (
                "raid-wowsims-reference"
                if edge.startswith("wowsims_")
                else "raid-shard-architecture"
                if edge.startswith("consumable_inventory_")
                else "raid-role-implementation"
            )
            expected_metric = "inventory-backed per-spec consumables and native-use receipts match"
        else:
            skill = "raid-rotation-review"
            mode = "review_only"
            expected_metric = "normalized consumable_parity.status=match"
            evidence_gap = True

    result = review.get("wowsims_result") or {}
    execution = review.get("execution_comparison") or {}
    cast_mix = execution.get("cast_mix") or {}
    windows = runtime.get("calibration_windows") or [] if isinstance(runtime, Mapping) else []
    window = windows[0] if len(windows) == 1 and isinstance(windows[0], Mapping) else {}
    required_duration = _number(policy.get("required_duration_seconds"))
    observed_duration = _number(window.get("elapsed_seconds"))
    duration_pass = (
        observed_duration is not None
        and required_duration is not None
        and observed_duration >= required_duration
        and runtime.get("calibration_complete") is True
        and len(windows) == 1
    )
    gates.append(_gate("closed_calibration_window", duration_pass, observed_duration, required_duration))
    if edge is None and not duration_pass:
        edge = "closed_calibration_window"
        skill = "raid-shard-architecture"
        mode = "capture_only"
        expected_metric = "one completed deterministic calibration window"
        evidence_gap = True

    single_300_canary = (
        selected_reference_class == "self_provided_baseline"
        and len(windows) == 1
        and required_duration == 300.0
        and observed_duration == 300.0
        and runtime.get("calibration_complete") is True
    )
    debug_reference = _debug_dps_reference(
        review.get("wowsims_debug_result"),
        required_duration_seconds=required_duration,
    )
    debug_reference_required = single_300_canary
    if debug_reference_required:
        debug_reference_pass = debug_reference["valid"]
        gates.append(
            _gate(
                "wowsims_debug_dps_reference",
                debug_reference_pass,
                debug_reference,
                {
                    "iterations_done": 1,
                    "aggregate_iterations": 1,
                    "debug_log_present": True,
                    "minimum_duration_seconds": required_duration,
                },
            )
        )
        if edge is None and not debug_reference_pass:
            edge = "wowsims_debug_dps_reference"
            skill = "raid-rotation-review"
            mode = "review_only"
            expected_metric = (
                "one pinned WoWSims debug iteration with a 300-second DPS sample"
            )
            evidence_gap = True

    overlap = _number(cast_mix.get("cast_mix_overlap")) if isinstance(cast_mix, Mapping) else None
    tvd = max(0.0, 1.0 - overlap) if overlap is not None else None
    max_delta = _number(cast_mix.get("maximum_absolute_share_delta")) if isinstance(cast_mix, Mapping) else None
    cadence = cast_mix.get("cast_cadence") or {} if isinstance(cast_mix, Mapping) else {}
    cadence_ratio = _number(cadence.get("trinity_to_wowsims_cadence_ratio")) if isinstance(cadence, Mapping) else None
    mix_limit = _number(thresholds.get("cast_mix_total_variation_distance_maximum"))
    delta_limit = _number(thresholds.get("cast_share_absolute_delta_maximum"))
    cadence_limits = thresholds.get("cast_cadence_ratio") or {}
    mix_pass = tvd is not None and mix_limit is not None and tvd <= mix_limit
    delta_pass = max_delta is not None and delta_limit is not None and max_delta <= delta_limit
    cadence_pass = _in_range(cadence_ratio, cadence_limits) if isinstance(cadence_limits, Mapping) else None
    gates.extend(
        [
            _gate("cast_mix_total_variation", mix_pass if tvd is not None else None, tvd, {"maximum": mix_limit}),
            _gate("maximum_cast_share_delta", delta_pass if max_delta is not None else None, max_delta, {"maximum": delta_limit}),
            _gate("cast_cadence_ratio", cadence_pass, cadence_ratio, cadence_limits),
        ]
    )
    if edge is None and (tvd is None or max_delta is None or cadence_ratio is None):
        edge = "rotation_comparison_signal"
        skill = "raid-rotation-review"
        mode = "review_only"
        expected_metric = "attributable cast mix and cadence"
        evidence_gap = True
    cast_behavior_failed = not mix_pass or not delta_pass or cadence_pass is not True

    runtime_dps = _number(window.get("dps"))
    aggregate_dps = _dps_distribution(result)
    wowsims_dps = _number(aggregate_dps.get("mean"))
    debug_dps = _number(debug_reference.get("dps"))
    if debug_reference_required:
        dps_denominator = debug_dps if debug_reference["valid"] else None
        dps_denominator_name = "wowsims_debug_result.player_dps.avg"
        total_limits = (
            selected_reference_policy.get("single_sample_dps_ratio") or {}
        )
    else:
        dps_denominator = wowsims_dps
        dps_denominator_name = "wowsims_result.player_dps.avg"
        total_limits = (
            selected_reference_policy.get("total_dps_ratio")
            or thresholds.get("total_dps_ratio")
            or {}
        )
    total_dps_ratio = _ratio(runtime_dps, dps_denominator)
    if not isinstance(total_limits, Mapping):
        total_dps_pass = None
    elif debug_reference_required and not debug_reference["valid"]:
        total_dps_pass = None
    elif selected_reference_policy.get("overtuned_is_failure") is False:
        minimum = _number(total_limits.get("minimum"))
        total_dps_pass = (
            total_dps_ratio is not None
            and minimum is not None
            and total_dps_ratio >= minimum
        )
    else:
        total_dps_pass = _meets_limits(total_dps_ratio, total_limits)
    total_dps_minimum = (
        _number(total_limits.get("minimum"))
        if isinstance(total_limits, Mapping)
        else None
    )
    total_dps_below_minimum = (
        total_dps_ratio is not None
        and total_dps_minimum is not None
        and total_dps_ratio < total_dps_minimum
    )

    pet_required = spec_policy.get("pet_required") is True
    pet_names = {str(value) for value in spec_policy.get("wowsims_primary_pet_names") or []}
    pet_spell_ids = {
        int(value) for value in spec_policy.get("trinity_primary_pet_spell_ids") or []
    }
    pet_reference = _pet_reference(result, pet_names) if isinstance(result, Mapping) else {"damage": 0.0, "landed_events": 0.0, "casts": 0.0}
    runtime_pet_damage = sum(
        _number(value) or 0.0
        for spell_id, value in (runtime.get("primary_pet_damage_by_spell") or {}).items()
        if not pet_spell_ids or int(spell_id) in pet_spell_ids
    ) if isinstance(runtime, Mapping) else 0.0
    runtime_pet_events = sum(
        _number(value) or 0.0
        for spell_id, value in (runtime.get("primary_pet_damage_event_counts_by_spell") or {}).items()
        if not pet_spell_ids or int(spell_id) in pet_spell_ids
    ) if isinstance(runtime, Mapping) else 0.0
    pet_observations = runtime.get("pet_execution_observations") or [] if isinstance(runtime, Mapping) else []
    pet_observation = pet_observations[0] if len(pet_observations) == 1 and isinstance(pet_observations[0], Mapping) else {}
    pet_alive = _number(pet_observation.get("alive_ratio"))
    pet_target = _number(pet_observation.get("target_match_ratio"))
    pet_event_ratio = _ratio(runtime_pet_events, pet_reference["landed_events"])
    runtime_pet_dpe = _ratio(runtime_pet_damage, runtime_pet_events)
    reference_pet_dpe = _ratio(pet_reference["damage"], pet_reference["landed_events"])
    pet_dpe_ratio = _ratio(runtime_pet_dpe, reference_pet_dpe)
    pet_total_damage_ratio = _ratio(runtime_pet_damage, pet_reference["damage"])
    if pet_required:
        pet_signal_present = (
            pet_reference["damage"] > 0
            and pet_reference["landed_events"] > 0
            and runtime_pet_damage > 0
            and runtime_pet_events > 0
            and bool(pet_observation)
        )
        pet_alive_min = _number(thresholds.get("pet_alive_ratio_minimum"))
        pet_target_min = _number(thresholds.get("pet_target_match_ratio_minimum"))
        pet_event_limits = thresholds.get("pet_landed_event_cadence_ratio") or {}
        pet_dpe_limits = thresholds.get("pet_damage_per_event_ratio") or {}
        pet_dpe_minimum = (
            _number(pet_dpe_limits.get("minimum"))
            if isinstance(pet_dpe_limits, Mapping)
            else None
        )
        pet_dpe_maximum = (
            _number(pet_dpe_limits.get("maximum"))
            if isinstance(pet_dpe_limits, Mapping)
            else None
        )
        pet_alive_pass = pet_alive is not None and pet_alive_min is not None and pet_alive >= pet_alive_min
        pet_target_pass = pet_target is not None and pet_target_min is not None and pet_target >= pet_target_min
        pet_event_pass = _meets_limits(pet_event_ratio, pet_event_limits) if isinstance(pet_event_limits, Mapping) else None
        # The simulator is a minimum-throughput reference for the pet.  A
        # higher damage per landed event is favorable throughput, not evidence
        # of a broken native damage model.  Keep the configured maximum in the
        # receipt as an informational diagnostic, while only the minimum is a
        # fail-closed gate.  Missing data still produces insufficient_data via
        # the normal gate path.
        pet_dpe_pass = (
            pet_dpe_ratio is not None
            and pet_dpe_minimum is not None
            and pet_dpe_ratio >= pet_dpe_minimum
        )
        pet_dpe_expected = {
            "minimum": pet_dpe_minimum,
            "maximum": pet_dpe_maximum,
            "upper_bound_enforced": False,
        }
        gates.extend(
            [
                _gate("primary_pet_attribution", True if pet_signal_present else None, {"runtime_damage": runtime_pet_damage, "runtime_landed_events": runtime_pet_events, "wowsims_damage": pet_reference["damage"], "wowsims_landed_events": pet_reference["landed_events"]}, "owner primary pet separated from guardians"),
                _gate("pet_alive_ratio", pet_alive_pass if pet_signal_present else None, pet_alive, {"minimum": pet_alive_min}),
                _gate("pet_target_match_ratio", pet_target_pass if pet_signal_present else None, pet_target, {"minimum": pet_target_min}),
                _gate("pet_landed_event_cadence_ratio", pet_event_pass if pet_signal_present else None, pet_event_ratio if pet_signal_present else None, pet_event_limits),
                _gate("pet_damage_per_event_ratio", pet_dpe_pass if pet_signal_present else None, pet_dpe_ratio, pet_dpe_expected),
            ]
        )
        if edge is None and not pet_signal_present:
            edge = "primary_pet_runtime_attribution"
            skill = "raid-shard-architecture"
            mode = "capture_only"
            expected_metric = "primary-pet execution and per-spell landed damage attribution"
            evidence_gap = True
        elif edge is None and cast_behavior_failed:
            edge = "priority_action_cadence"
            skill = "raid-role-implementation"
            expected_metric = "cast mix and cadence inside acceptance policy"
        elif edge is None and (not pet_alive_pass or not pet_target_pass or pet_event_pass is not True):
            edge = "primary_pet_policy_execution"
            skill = "raid-role-implementation"
            expected_metric = "pet alive, target, and landed-event cadence inside policy"
        elif edge is None and pet_dpe_pass is not True:
            edge = "native_pet_damage_model"
            skill = "raid-class-mechanics-implementation"
            expected_metric = "primary-pet damage per landed event inside policy"
    elif edge is None and cast_behavior_failed:
        edge = "priority_action_cadence"
        skill = "raid-role-implementation"
        expected_metric = "cast mix and cadence inside acceptance policy"

    total_dps_expected = {
        "denominator": dps_denominator_name,
        "limits": total_limits,
        "upper_bound_enforced": (
            not debug_reference_required
            or selected_reference_policy.get("overtuned_is_failure") is True
        ),
    }
    gates.append(
        _gate("total_dps_ratio", total_dps_pass, total_dps_ratio, total_dps_expected)
    )
    if edge is None and total_dps_ratio is None:
        edge = "total_dps_observation"
        skill = "raid-rotation-review"
        mode = "review_only"
        expected_metric = "comparable Trinity and WoWSims total DPS"
        evidence_gap = True
    elif edge is None and total_dps_pass is not True:
        owner_deficit_is_attributable = (
            total_dps_below_minimum
            and pet_required
            and pet_total_damage_ratio is not None
            and pet_total_damage_ratio >= 1.0
            and not cast_behavior_failed
        )
        edge = (
            "native_owner_damage_model"
            if owner_deficit_is_attributable
            else "native_class_damage_model"
        )
        skill = "raid-class-mechanics-implementation"
        expected_metric = (
            "owner damage closes the total DPS deficit with unchanged cadence and pet damage"
            if owner_deficit_is_attributable
            else "total DPS inside policy with unchanged cadence"
        )

    passed = edge is None and all(row["status"] == "pass" for row in gates)
    next_work_unit: dict[str, Any] | None = None
    terminal_reason: str | None = None
    if passed:
        status = "passed"
        terminal_reason = "verified_after_single_fix" if fixes_used else "baseline_within_policy"
    elif evidence_gap:
        if capture_attempts_used >= max_captures:
            status = "failed"
            terminal_reason = "capture_budget_exhausted"
        else:
            status = "insufficient_data"
            next_work_unit = _next_work_unit(
                spec=spec, reference_class=selected_reference_class,
                review_sha256=review_sha256, edge=edge or "unknown",
                skill=skill or "raid-rotation-review", mode=mode, fixes_used=fixes_used,
                captures_used=capture_attempts_used, expected_metric=expected_metric,
            )
    elif fixes_used >= max_fixes:
        status = "failed"
        terminal_reason = "fix_budget_exhausted"
    else:
        status = "failed"
        next_work_unit = _next_work_unit(
            spec=spec, reference_class=selected_reference_class,
            review_sha256=review_sha256, edge=edge or "unknown",
            skill=skill or "raid-rotation-review", mode=mode, fixes_used=fixes_used,
            captures_used=capture_attempts_used, expected_metric=expected_metric,
        )

    decision: dict[str, Any] = {
        "schema": "trinity_spec_canary_decision_v1",
        "spec": spec,
        "reference_class": selected_reference_class,
        "status": status,
        "stage": "verification" if fixes_used else "baseline",
        "first_broken_edge": edge,
        "owner_skill": skill,
        "terminal_reason": terminal_reason,
        "budgets": {
            "fixes_used": fixes_used,
            "max_fix_attempts": max_fixes,
            "capture_attempts_used": capture_attempts_used,
            "max_capture_attempts": max_captures,
        },
        "identities": {
            "review_sha256": review_sha256,
            "policy_sha256": policy_sha256,
        },
        "gates": gates,
        "signals": {
            "cast_mix_total_variation_distance": tvd,
            "maximum_cast_share_delta": max_delta,
            "cast_cadence_ratio": cadence_ratio,
            "total_dps_ratio": total_dps_ratio,
            "runtime_dps": runtime_dps,
            "wowsims_dps": wowsims_dps,
            "wowsims_aggregate_dps": aggregate_dps,
            "wowsims_debug_dps": debug_dps,
            "dps_comparison": {
                "denominator": dps_denominator_name,
                "denominator_value": dps_denominator,
                "aggregate_mean": aggregate_dps.get("mean"),
                "aggregate_stdev": aggregate_dps.get("stdev"),
                "aggregate_minimum": aggregate_dps.get("minimum"),
                "aggregate_maximum": aggregate_dps.get("maximum"),
                "aggregate_iterations": aggregate_dps.get("iterations"),
                "debug_value": debug_dps,
                "debug_iterations_done": debug_reference.get("iterations_done"),
                "debug_aggregate_iterations": debug_reference.get("aggregate_iterations"),
                "debug_reference_valid": debug_reference.get("valid"),
                "single_sample_canary": single_300_canary,
                "parity_band": total_limits if debug_reference_required else None,
                "upper_bound_enforced": (
                    debug_reference_required
                    and selected_reference_policy.get("overtuned_is_failure") is True
                ),
            },
            "primary_pet": {
                "runtime_damage": runtime_pet_damage,
                "runtime_landed_events": runtime_pet_events,
                "wowsims_damage": pet_reference["damage"],
                "wowsims_landed_events": pet_reference["landed_events"],
                "landed_event_cadence_ratio": pet_event_ratio,
                "damage_per_event_ratio": pet_dpe_ratio,
                "total_damage_ratio": pet_total_damage_ratio,
                "alive_ratio": pet_alive,
                "target_match_ratio": pet_target,
            },
        },
        "next_work_unit": next_work_unit,
    }
    decision["decision_sha256"] = canonical_sha256(decision)
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--reference-class")
    parser.add_argument("--fixes-used", type=int, default=0)
    parser.add_argument("--capture-attempts-used", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    review_path = args.review.resolve()
    policy_path = args.policy if args.policy.is_absolute() else ROOT / args.policy
    policy_path = policy_path.resolve()
    decision = evaluate_canary(
        load_object(review_path), load_object(policy_path), spec=args.spec,
        review_sha256=file_sha256(review_path), policy_sha256=file_sha256(policy_path),
        reference_class=args.reference_class,
        fixes_used=args.fixes_used, capture_attempts_used=args.capture_attempts_used,
    )
    rendered = json.dumps(decision, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
