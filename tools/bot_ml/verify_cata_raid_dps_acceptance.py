"""Verify the current 25H DPS target set and its 75/85 reference gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .common import write_json
from .live_validation_session import canonical_sha256, sha256_file
from .phase8_calibration_adapter import expected_gear_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "experiments/configs/cata_raid_dps_acceptance_v1.json"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _resolve(config_path: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    repository_candidate = REPO_ROOT / candidate
    if repository_candidate.exists():
        return repository_candidate
    return config_path.parent / candidate


def gear_profile_binding(
    target: Mapping[str, Any], reference: Mapping[str, Any]
) -> dict[str, Any]:
    """Project the canonical gear id through target, provisioning, and reference."""
    target_profile_id = str(target.get("gear_profile_id") or "")
    provisioning = target.get("provisioning_bot") or {}
    reference_gear = reference.get("gear") or {}
    provisioning_profile_id = str(provisioning.get("gear_profile_id") or "")
    provisioning_profile_name = str(provisioning.get("gear_profile") or "")
    reference_profile_id = str(reference_gear.get("gear_profile_id") or "")
    reference_runtime_profile_id = str(
        reference_gear.get("runtime_profile_id") or ""
    )
    return {
        "gear_profile_id": target_profile_id,
        "provisioning_gear_profile_id": provisioning_profile_id,
        "provisioning_gear_profile": provisioning_profile_name,
        "reference_gear_profile_id": reference_profile_id,
        "reference_runtime_profile_id": reference_runtime_profile_id,
        "gear_profile_binding_verified": bool(
            target_profile_id
            and provisioning_profile_id == target_profile_id
            and provisioning_profile_name == target_profile_id
            and reference_profile_id == target_profile_id
            and reference_runtime_profile_id == target_profile_id
        ),
    }


def verify(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = _load(config_path)
    if config.get("schema") != "cata_raid_dps_acceptance_v1":
        raise ValueError("unexpected DPS acceptance schema")

    roster_path = _resolve(config_path, str(config["roster"]))
    pair_policy_path = _resolve(config_path, str(config["stonecore_pair_policy"]))
    calibration_policy_path = _resolve(config_path, str(config["role_calibration_policy"]))
    targets_path = _resolve(config_path, str(config["target_catalog"]))
    references_path = _resolve(config_path, str(config["reference_catalog"]))
    roster = _load(roster_path)
    pair_policy = _load(pair_policy_path)
    calibration_policy = _load(calibration_policy_path)
    targets = _load(targets_path)
    references = _load(references_path)

    configured = [str(value) for value in config.get("dps_targets") or []]
    supported = [
        str(value)
        for value in (
            (pair_policy.get("live_qualification_policy") or {}).get(
                "supported_dps_targets"
            )
            or []
        )
    ]
    target_by_id = {
        str(row.get("spec_target_id") or ""): row
        for row in targets.get("targets") or []
        if isinstance(row, Mapping)
    }
    reference_by_id = {
        str(row.get("spec_target_id") or ""): row
        for row in references.get("references") or []
        if isinstance(row, Mapping)
    }
    acceptance = config.get("acceptance") or {}
    hard_ratio = float(calibration_policy.get("hard_reference_ratio") or 0.0)
    optimization_ratio = float(
        calibration_policy.get("optimization_reference_ratio") or 0.0
    )
    default_shape = roster.get("default_shape") or {}
    encounter_shapes = (
        (pair_policy.get("progression_roster_25h") or {}).get(
            "encounter_shapes"
        )
        or []
    )

    rows: list[dict[str, Any]] = []
    reference_complete = True
    target_identity_complete = True
    gear_profile_identity_complete = True
    for target_id in configured:
        target = target_by_id.get(target_id) or {}
        reference = reference_by_id.get(target_id) or {}
        gear_binding = gear_profile_binding(target, reference)
        try:
            gear_manifest = expected_gear_manifest(
                str(gear_binding["gear_profile_id"])
            )
        except (OSError, ValueError):
            gear_manifest = []
        gear_binding["gear_manifest_sha256"] = (
            canonical_sha256(gear_manifest) if gear_manifest else ""
        )
        gear_binding["gear_profile_binding_verified"] = bool(
            gear_binding["gear_profile_binding_verified"] and gear_manifest
        )
        metrics = ((reference.get("expected_output") or {}).get("metrics") or {})
        reference_dps = float(metrics.get("dps") or 0.0)
        target_valid = bool(target and target.get("role") == "dps")
        reference_valid = bool(
            reference_dps > 0
            and reference.get("provider_revision")
            and reference.get("reference_conditions")
        )
        target_identity_complete = target_identity_complete and target_valid
        reference_complete = reference_complete and reference_valid
        gear_profile_identity_complete = (
            gear_profile_identity_complete
            and gear_binding["gear_profile_binding_verified"]
        )
        rows.append(
            {
                "spec_target_id": target_id,
                "runtime_join_key": target.get("runtime_join_key"),
                "class_name": target.get("class_name"),
                "reference_id": reference.get("reference_id"),
                "provider": reference.get("provider"),
                "provider_revision": reference.get("provider_revision"),
                "reference_dps": reference_dps,
                "hard_floor_dps": round(reference_dps * hard_ratio, 3),
                "optimization_target_dps": round(
                    reference_dps * optimization_ratio, 3
                ),
                "target_valid": target_valid,
                "reference_valid": reference_valid,
                **gear_binding,
            }
        )

    qualification_mode = str(config.get("qualification_mode") or "")
    qualification_seed = int(config.get("qualification_seed") or 0)
    max_tries = int(config.get("max_tries_per_dps_spec") or 0)
    expected_attempt_count = len(configured)
    checks = {
        "current_stonecore_dps_target_set_exact": configured == supported,
        "configured_dps_target_count_exact": len(configured)
        == int(config.get("supported_dps_spec_count") or 0)
        == 16,
        "all_targets_are_canonical_dps_specs": target_identity_complete,
        "all_targets_have_positive_pinned_references": reference_complete,
        "all_targets_have_one_canonical_gear_profile_id": (
            gear_profile_identity_complete
        ),
        "hard_floor_is_75_percent": hard_ratio
        == float(acceptance.get("hard_reference_ratio") or 0.0)
        == 0.75,
        "optimization_target_is_85_percent": optimization_ratio
        == float(acceptance.get("optimization_reference_ratio") or 0.0)
        == 0.85,
        "default_dps_slots_match_roster": int(default_shape.get("dps") or 0)
        == int(config.get("default_dps_slot_count") or 0),
        "encounter_dps_slots_match_roster": sorted(
            int(row.get("dps") or 0)
            for row in encounter_shapes
            if isinstance(row, Mapping)
        )
        == sorted(int(value) for value in config.get("encounter_dps_slot_counts") or []),
        "one_qualification_per_unique_dps_spec": qualification_mode
        == "single_target_300"
        and qualification_seed == 1
        and expected_attempt_count == 16,
        "one_retry_maximum": max_tries == 2,
        "benchmark_provenance_explicit": config.get("evidence_role")
        == "non_certifying_controller_benchmark"
        and config.get("expected_runtime_mode") == "calibration_fixture"
        and config.get("non_certifying_assistance_expected") is True
        and config.get("excluded_from_training_corpus") is True
        and config.get("requires_player_like_clear_gate") is True,
        "remote_publication_required": acceptance.get(
            "all_attempts_require_remote_verified_publication"
        )
        is True,
        "targeted_eviction_required": acceptance.get(
            "evict_after_remote_verification"
        )
        is True
        and acceptance.get("retain_published_batch") is False,
    }
    report = {
        "schema": "cata_raid_dps_acceptance_verification_v1",
        "passed": all(checks.values()),
        "checks": checks,
        "supported_dps_spec_count": len(configured),
        "supported_specialization_target_count": int(
            config.get("supported_specialization_target_count") or 0
        ),
        "attempt_count": expected_attempt_count,
        "qualification_mode": qualification_mode,
        "qualification_seed": qualification_seed,
        "max_tries_per_dps_spec": max_tries,
        "evidence_role": config.get("evidence_role"),
        "expected_runtime_mode": config.get("expected_runtime_mode"),
        "non_certifying_assistance_expected": config.get(
            "non_certifying_assistance_expected"
        ),
        "excluded_from_training_corpus": config.get(
            "excluded_from_training_corpus"
        ),
        "requires_player_like_clear_gate": config.get(
            "requires_player_like_clear_gate"
        ),
        "hard_reference_ratio": hard_ratio,
        "optimization_reference_ratio": optimization_ratio,
        "targets": rows,
        "input_hashes": {
            "config": sha256_file(config_path),
            "roster": sha256_file(roster_path),
            "stonecore_pair_policy": sha256_file(pair_policy_path),
            "role_calibration_policy": sha256_file(calibration_policy_path),
            "target_catalog": sha256_file(targets_path),
            "reference_catalog": sha256_file(references_path),
        },
    }
    report["verification_sha256"] = canonical_sha256(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.config)
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
