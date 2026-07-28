"""Normalize live Phase 8 calibration status for independent role acceptance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

try:
    from .live_validation_session import canonical_sha256
    from .role_calibration_harness import evaluate_calibration, load_policy
except ImportError:
    from live_validation_session import canonical_sha256
    from role_calibration_harness import evaluate_calibration, load_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
DEFAULT_REFERENCES = REPO_ROOT / "experiments/configs/all_spec_references_cata_p4_v1.json"
DEFAULT_SCENARIOS = REPO_ROOT / "experiments/configs/all_spec_calibration_scenarios_v1.json"
DEFAULT_POLICY = REPO_ROOT / "experiments/configs/all_spec_role_calibration_policy_v1.json"


class Phase8CalibrationNormalizationError(ValueError):
    """Raised when live calibration evidence cannot be normalized safely."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Phase8CalibrationNormalizationError(f"missing_mapping:{label}")
    return value


def _required(row: Mapping[str, Any], key: str, label: str) -> Any:
    if key not in row:
        raise Phase8CalibrationNormalizationError(f"missing_field:{label}.{key}")
    return row[key]


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def _load_rows(path: Path, key: str, expected_schema: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != expected_schema:
        raise Phase8CalibrationNormalizationError(f"unexpected_catalog_schema:{path}")
    rows = payload.get(key)
    if not isinstance(rows, list):
        raise Phase8CalibrationNormalizationError(f"missing_catalog_rows:{path}:{key}")
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def load_phase8_catalog_entry(
    target_spec: str,
    *,
    targets_path: Path = DEFAULT_TARGETS,
    references_path: Path = DEFAULT_REFERENCES,
    scenarios_path: Path = DEFAULT_SCENARIOS,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load one canonical target, reference, and calibration scenario."""
    targets = _load_rows(targets_path, "targets", "all_spec_targets_cata_p4_v1")
    references = _load_rows(references_path, "references", "all_spec_references_cata_p4_v1")
    scenarios = _load_rows(scenarios_path, "scenarios", "all_spec_calibration_scenarios_v1")
    target = next(
        (
            row
            for row in targets
            if str(row.get("runtime_join_key") or "") == target_spec
            or str(row.get("spec_target_id") or "") == target_spec
            or target_spec in set(row.get("accepted_aliases") or [])
        ),
        None,
    )
    if target is None:
        raise Phase8CalibrationNormalizationError(f"unknown_target_spec:{target_spec}")
    target_id = str(target.get("spec_target_id") or "")
    reference = next(
        (row for row in references if str(row.get("spec_target_id") or "") == target_id),
        None,
    )
    scenario = next(
        (row for row in scenarios if str(row.get("spec_target_id") or "") == target_id),
        None,
    )
    if reference is None:
        raise Phase8CalibrationNormalizationError(f"missing_reference:{target_id}")
    if scenario is None:
        raise Phase8CalibrationNormalizationError(f"missing_scenario:{target_id}")
    return target, reference, scenario


def _ability_mix(target_bot: Mapping[str, Any]) -> dict[str, float]:
    rows = target_bot.get("spell_damage") or []
    if not isinstance(rows, list):
        raise Phase8CalibrationNormalizationError("invalid_field:target_bot.spell_damage")
    amounts: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        amount = float(row.get("damage") or 0.0)
        if amount <= 0:
            continue
        spell_id = int(row.get("spell_id") or 0)
        spell_name = str(row.get("spell_name") or "Melee")
        amounts[f"{spell_id}:{spell_name}"] = amounts.get(f"{spell_id}:{spell_name}", 0.0) + amount
    total = sum(amounts.values())
    return {key: round(value / total, 8) for key, value in amounts.items()} if total > 0 else {}


def _simulator_dps(reference: Mapping[str, Any]) -> float:
    expected = _mapping(reference.get("expected_output"), "reference.expected_output")
    metrics = _mapping(expected.get("metrics"), "reference.expected_output.metrics")
    value = float(metrics.get("dps") or 0.0)
    if value <= 0:
        raise Phase8CalibrationNormalizationError("missing_positive_reference_dps")
    return value


def normalize_runtime_calibration(
    calibration: Mapping[str, Any],
    *,
    target_row: Mapping[str, Any],
    reference_row: Mapping[str, Any],
    scenario_row: Mapping[str, Any],
    mode: str,
) -> dict[str, Any]:
    """Convert one completed live status payload into the Phase 7 record schema."""
    if not bool(calibration.get("window_complete")) or str(calibration.get("phase") or "") != "complete":
        raise Phase8CalibrationNormalizationError("calibration_window_incomplete")
    if str(calibration.get("mode") or "") != mode:
        raise Phase8CalibrationNormalizationError("calibration_mode_mismatch")
    runtime_key = str(target_row.get("runtime_join_key") or "")
    if str(calibration.get("target_spec") or "") != runtime_key:
        raise Phase8CalibrationNormalizationError("calibration_target_mismatch")

    previous = _mapping(calibration.get("previous_window"), "calibration.previous_window")
    if str(previous.get("mode") or "") != mode:
        raise Phase8CalibrationNormalizationError("previous_window_mode_mismatch")
    bots = previous.get("bots")
    if not isinstance(bots, list) or not bots:
        raise Phase8CalibrationNormalizationError("missing_previous_window_bots")
    target_guid = int(calibration.get("target_guid") or 0)
    target_bot = next(
        (row for row in bots if isinstance(row, Mapping) and int(row.get("guid") or 0) == target_guid),
        None,
    )
    if target_bot is None:
        raise Phase8CalibrationNormalizationError("missing_target_window_metrics")
    role = str(target_row.get("role") or "")
    if str(target_bot.get("role") or "") != role:
        raise Phase8CalibrationNormalizationError("target_role_mismatch")
    if int(target_bot.get("class_id") or 0) != int(target_row.get("class_id") or 0):
        raise Phase8CalibrationNormalizationError("target_class_mismatch")

    quality = _mapping(target_bot.get("quality_metrics"), "target_bot.quality_metrics")
    scored_seconds = float(_required(calibration, "scored_seconds", "calibration") or 0.0)
    warmup_seconds = float(_required(calibration, "warmup_seconds", "calibration") or 0.0)
    scored_started_at_ms = int(_required(calibration, "scored_started_at_ms", "calibration") or 0)
    scored_ended_at_ms = int(_required(calibration, "scored_ended_at_ms", "calibration") or 0)
    normalization = _mapping(calibration.get("normalization"), "calibration.normalization")
    reference_setup = _mapping(target_bot.get("reference_setup"), "target_bot.reference_setup")

    identity = {
        "spec_target_id": str(target_row.get("spec_target_id") or ""),
        "runtime_join_key": runtime_key,
        "reference_id": str(reference_row.get("reference_id") or ""),
        "scenario_id": str((_mapping(scenario_row.get("primary"), "scenario.primary")).get("scenario_id") or ""),
        "seed": int(calibration.get("seed") or 0),
        "target_guid": target_guid,
        "target_sha256": canonical_sha256(target_row),
        "conditions_sha256": canonical_sha256(
            {
                "reference_conditions": reference_row.get("reference_conditions") or {},
                "runtime_normalization": dict(normalization),
                "runtime_reference_setup": dict(reference_setup),
                "consumable_item_ids": target_row.get("consumable_item_ids") or [],
                "scenario": scenario_row,
                "mode": mode,
            }
        ),
        "profile_generation": int(calibration.get("profile_generation") or 0),
        "profile_content_hash": str(calibration.get("profile_content_hash") or ""),
        "runtime_authority": str(calibration.get("runtime_authority") or ""),
        "generic_ml_runtime_authority": calibration.get("generic_ml_runtime_authority"),
    }
    window = {
        "warmup_seconds": warmup_seconds,
        "warmup_ended_at_ms": scored_started_at_ms,
        "scored_started_at_ms": scored_started_at_ms,
        "scored_ended_at_ms": scored_ended_at_ms,
        "scored_duration_seconds": scored_seconds,
        "reset_applied": bool(calibration.get("reset_applied")),
        "reset_id": str(calibration.get("reset_id") or ""),
        "cross_window_event_count": int(calibration.get("cross_window_event_count") or 0),
    }
    common = {
        "illegal_action_count": int(quality.get("illegal_action_count") or 0),
    }
    elapsed_dps = float(_required(target_bot, "dps", "target_bot") or 0.0)

    if mode in {"single_target_300", "aoe_300"}:
        active_uptime = float(_required(quality, "active_uptime_ratio", "target_bot.quality_metrics") or 0.0)
        metrics = {
            **common,
            "reference_value": _simulator_dps(reference_row),
            "reference_basis": "pinned_cata_phase4_simulator_dps",
            "measured_value": elapsed_dps,
            "active_dps": elapsed_dps / active_uptime if active_uptime > 0 else 0.0,
            "elapsed_dps": elapsed_dps,
            "target_count": int(_required(target_bot, "target_count", "target_bot") or 0),
            "ability_mix": _ability_mix(target_bot),
            "rotation_group_coverage": float(_required(quality, "rotation_group_coverage", "target_bot.quality_metrics") or 0.0),
            "observed_action_groups": list(target_bot.get("action_groups") or []),
            "expected_action_groups": list(target_bot.get("expected_action_groups") or []),
            "cast_failure_ratio": float(_required(quality, "cast_failure_ratio", "target_bot.quality_metrics") or 0.0),
            "resource_capped_ratio": float(_required(quality, "resource_capped_ratio", "target_bot.quality_metrics") or 0.0),
            "resource_starved_ratio": float(_required(quality, "resource_starved_ratio", "target_bot.quality_metrics") or 0.0),
            "active_uptime_ratio": active_uptime,
            "movement_range_loss_ratio": float(_required(quality, "movement_range_loss_ratio", "target_bot.quality_metrics") or 0.0),
            "pet_damage_ratio": float(_required(quality, "pet_damage_ratio", "target_bot.quality_metrics") or 0.0),
        }
    elif mode == "tank_threat_300":
        tank = _mapping(target_bot.get("tank_metrics"), "target_bot.tank_metrics")
        defensive_actions = int(_required(tank, "defensive_action_count", "target_bot.tank_metrics") or 0)
        mitigation_uptime = float(_required(tank, "mitigation_uptime_ratio", "target_bot.tank_metrics") or 0.0)
        metrics = {
            **common,
            "reference_value": _simulator_dps(reference_row),
            "reference_basis": "pinned_cata_phase4_simulator_dps",
            "measured_value": elapsed_dps,
            "active_dps": elapsed_dps,
            "threat_per_second": float(_required(target_bot, "threat_per_second", "target_bot") or 0.0),
            "target_count": int(_required(target_bot, "target_count", "target_bot") or 0),
            "tank_stance_form_presence_active": float(_required(tank, "stance_form_uptime_ratio", "target_bot.tank_metrics") or 0.0) >= 0.99,
            "snap_threat_success_ratio": float(_required(tank, "snap_threat_success_ratio", "target_bot.tank_metrics") or 0.0),
            "add_threat_success_ratio": float(_required(tank, "add_threat_success_ratio", "target_bot.tank_metrics") or 0.0),
            "all_hostile_retention_ratio": float(_required(tank, "all_hostile_retention_ratio", "target_bot.tank_metrics") or 0.0),
            "threat_aura_uptime_ratio": float(_required(tank, "threat_aura_uptime_ratio", "target_bot.tank_metrics") or 0.0),
            "healer_exposure_ratio": float(_required(tank, "healer_exposure_ratio", "target_bot.tank_metrics") or 0.0),
            "mitigation_uptime_ratio": mitigation_uptime,
            "defensive_coverage": {
                "defensive_action_count": defensive_actions,
                "mitigation_uptime_ratio": mitigation_uptime,
            } if defensive_actions > 0 or mitigation_uptime > 0 else {},
            "maximum_damage_spike_ratio": float(_required(tank, "maximum_controlled_damage_ratio", "target_bot.tank_metrics") or 0.0),
            "death_count": int(_required(tank, "death_count", "target_bot.tank_metrics") or 0),
            "health_floor_ratio": float(_required(tank, "health_floor_ratio", "target_bot.tank_metrics") or 0.0),
            "interrupt_success_ratio": float(_required(tank, "interrupt_success_ratio", "target_bot.tank_metrics") or 0.0),
        }
    elif mode == "healer_controlled_damage_300":
        healer = _mapping(target_bot.get("healer_metrics"), "target_bot.healer_metrics")
        controlled_damage = float(_required(healer, "controlled_damage", "target_bot.healer_metrics") or 0.0)
        reference_value = controlled_damage / scored_seconds if scored_seconds > 0 else 0.0
        dispel_attempts = int(_required(healer, "dispel_attempts", "target_bot.healer_metrics") or 0)
        cooldown_attempts = int(_required(healer, "cooldown_attempts", "target_bot.healer_metrics") or 0)
        metrics = {
            **common,
            "reference_value": reference_value,
            "reference_basis": "deterministic_delivered_controlled_damage_hps",
            "measured_value": float(_required(healer, "effective_hps", "target_bot.healer_metrics") or 0.0),
            "effective_hps": float(_required(healer, "effective_hps", "target_bot.healer_metrics") or 0.0),
            "scheduled_phases": list(target_bot.get("scheduled_damage_phases") or []),
            "delivered_phases": list(target_bot.get("delivered_damage_phases") or []),
            "scheduled_event_count": int(_required(healer, "scheduled_event_count", "target_bot.healer_metrics") or 0),
            "delivered_event_count": int(_required(healer, "delivered_event_count", "target_bot.healer_metrics") or 0),
            "death_count": sum(
                int((_mapping(row.get("healer_metrics") if str(row.get("role") or "") == "healer" else row.get("tank_metrics"), "bot.role_metrics")).get("death_count") or 0)
                for row in bots
                if isinstance(row, Mapping)
            ),
            "health_floor_ratio": float(_required(healer, "health_floor_ratio", "target_bot.healer_metrics") or 0.0),
            "overheal_ratio": float(_required(healer, "overheal_ratio", "target_bot.healer_metrics") or 0.0),
            "absorb_amount": int(_required(healer, "absorbed_healing", "target_bot.healer_metrics") or 0),
            "remaining_mana_ratio": float(_required(healer, "remaining_mana_ratio", "target_bot.healer_metrics") or 0.0),
            "time_to_oom_seconds": float(_required(healer, "time_to_oom_seconds", "target_bot.healer_metrics") or 0.0),
            "response_latency_p95_ms": float(_required(healer, "response_latency_p95_ms", "target_bot.healer_metrics") or 0.0),
            "target_selection_accuracy": float(_required(healer, "target_selection_accuracy", "target_bot.healer_metrics") or 0.0),
            "dispel_success_ratio": _ratio(float(healer.get("dispel_successes") or 0), float(dispel_attempts)),
            "cooldown_success_ratio": _ratio(float(healer.get("cooldown_successes") or 0), float(cooldown_attempts)),
            "idle_ratio_under_demand": float(_required(healer, "idle_ratio_under_demand", "target_bot.healer_metrics") or 0.0),
            "cast_failure_ratio": float(_required(quality, "cast_failure_ratio", "target_bot.quality_metrics") or 0.0),
            "triage_target_counts": dict(_mapping(target_bot.get("heal_target_counts"), "target_bot.heal_target_counts")),
        }
    else:
        raise Phase8CalibrationNormalizationError(f"unsupported_mode:{mode}")

    return {
        "schema": "all_spec_role_calibration_record_v1",
        "mode": mode,
        "role": role,
        "identity": identity,
        "window": window,
        "metrics": metrics,
        "raw_runtime_status": dict(calibration),
    }


def evaluate_runtime_calibration(
    calibration: Mapping[str, Any],
    *,
    target_spec: str,
    mode: str,
    policy_path: Path = DEFAULT_POLICY,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize and independently evaluate one completed live calibration."""
    target, reference, scenario = load_phase8_catalog_entry(target_spec)
    record = normalize_runtime_calibration(
        calibration,
        target_row=target,
        reference_row=reference,
        scenario_row=scenario,
        mode=mode,
    )
    return record, evaluate_calibration(record, load_policy(policy_path))
