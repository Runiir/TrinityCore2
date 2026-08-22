#!/usr/bin/env python3
"""Build the deterministic capture/review/decision contract for one DPS canary."""

from __future__ import annotations

from shlex import join
from typing import Any, Mapping


REQUIRED_SIMULATOR_ARTIFACTS = (
    "generation_receipt",
    "raid_sim_request",
    "raid_sim_result",
    "compute_stats",
)


def _artifact_path(value: Any) -> str | None:
    """Return the executable path carried by a reference-artifact value.

    Promoted references use a repo-relative string, while a hydrated receipt
    may still expose the normal content-addressed descriptor.  Accept both
    forms so the contract does not incorrectly discard an available
    ComputeStats descriptor merely because it is nested in a receipt-shaped
    mapping.
    """

    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, Mapping):
        path = value.get("path")
        if isinstance(path, str) and path.strip():
            return path
    return None


def _missing_simulator_artifacts(
    reference_artifacts: Mapping[str, Any],
) -> list[str]:
    return [
        name
        for name in REQUIRED_SIMULATOR_ARTIFACTS
        if _artifact_path(reference_artifacts.get(name)) is None
    ]


def _rotation_review_command(
    reference_artifacts: Mapping[str, Any],
) -> list[str]:
    """Build the exact review argv from the promoted reference mapping."""

    command = [
        "pixi",
        "run",
        "python",
        "-m",
        "tools.bot_ml.review_rotation_mechanics",
        "--reference-class",
        "self_provided_baseline",
        "--wowsims-apl",
        _artifact_path(reference_artifacts["raid_sim_request"]) or "",
        "--wowsims-result",
        _artifact_path(reference_artifacts["raid_sim_result"]) or "",
        "--wowsims-compute-stats",
        _artifact_path(reference_artifacts["compute_stats"]) or "",
    ]
    debug_result = _artifact_path(reference_artifacts.get("debug_raid_sim_result"))
    if debug_result is not None:
        command.extend(("--wowsims-debug-result", debug_result))
    command.extend(
        (
            "--trinity-profile",
            "<canary>/identity/rotation-profile.json",
            "--runtime-report",
            "<canary>/run/report.json",
            "--output",
            "<canary>/rotation-review.json",
        )
    )
    return command


def build_canary_pipeline(
    spec: str, reference_artifacts: Mapping[str, Any] | None
) -> dict[str, Any]:
    if reference_artifacts is None:
        return {"state": "requires_exact_reference_hydration_or_generation"}

    missing = _missing_simulator_artifacts(reference_artifacts)
    pipeline: dict[str, Any] = {
        "state": "ready_for_capture",
        "fixed_order": ["capture", "rotation_review", "acceptance_decision"],
        "capture": {
            "owner_skill": "raid-shard-architecture",
            "mode": "capture_only_preserve_worldserver",
            "identity_manifest_command": (
                "pixi run python -m "
                "tools.bot_ml.build_phase8_evidence_identity_manifest "
                "--calibration-self-provided-baseline "
                f"--profile-target-spec {spec} "
                "--session-runtime-dir <owned-session-runtime-dir> "
                "--profile-output <canary>/identity/rotation-profile.json "
                "--output <canary>/identity/identity-manifest.json"
            ),
            "runner_module": "tools.bot_ml.run_live_bot_validation",
            "validation_clock": {
                "policy": "isolated_training_dummy_scoring_window",
                "duration_seconds": 300,
                "duration_variation_seconds": 0,
            },
            "required_runner_flags": [
                "--calibration-only",
                "--calibration-self-provided-baseline",
                "--calibration-mode single_target_300",
                f"--calibration-target-spec {spec}",
                "--transport session",
                "--session-profile affliction_canary",
                "--preserve-worldserver",
                "--session-runtime-dir <owned-session-runtime-dir>",
                "--bot-pool-tag all_spec_candidate_pool",
                "--evidence-identity-manifest <canary>/identity/identity-manifest.json",
                "--output-dir <canary>/run",
            ],
            "directory_contract": {
                "identity_dir": "<canary>/identity",
                "runner_output_dir": "<canary>/run",
                "runner_output_dir_must_be_new_or_empty": True,
                "identity_files_must_not_be_written_to_runner_output_dir": True,
            },
            "required_outputs": [
                "closed runtime report",
                "runtime botauto rotation dump",
                "scoring_start_stats and scoring_start_pet_stats",
                "native consumable use and inventory receipts",
            ],
            "forbidden_lifecycle_actions": [
                "stop_worldserver",
                "restart_worldserver",
            ],
        },
        "rotation_review": {
            "owner_skill": "raid-rotation-review",
            "reference_class": "self_provided_baseline",
            "simulator_artifacts": dict(reference_artifacts),
            "required_simulator_artifacts": list(REQUIRED_SIMULATOR_ARTIFACTS),
            "runtime_inputs": {
                "trinity_profile": "<canary>/identity/rotation-profile.json",
                "runtime_report": "<canary>/run/report.json",
            },
            "command": None,
            "argv": None,
            "output": "<canary>/rotation-review.json",
        },
        "acceptance_decision": {
            "owner_skill": "raid-performance-loop",
            "command": (
                "pixi run python -m tools.bot_ml.spec_canary_gate "
                "--review <canary>/rotation-review.json "
                f"--spec {spec} "
                "--reference-class self_provided_baseline "
                "--output <canary>/canary-decision.json"
            ),
            "max_capture_attempts": 1,
            "max_fix_attempts": 1,
            "pass_rule": "runtime_dps_greater_than_or_equal_to_reference",
            "upper_rejection_bound": None,
        },
    }

    if missing:
        # Keep the contract inspectable, but do not emit an executable capture
        # or tuning path until the exact promoted reference is complete.
        pipeline.update(
            {
                "state": "blocked_missing_rotation_review_artifacts",
                "missing_required_simulator_artifacts": missing,
                "blocked_before_gameplay_tuning": True,
                "routing": {
                    "owner_skill": "raid-wowsims-reference",
                    "first_broken_edge": (
                        "wowsims_compute_stats_reference"
                        if "compute_stats" in missing
                        else "wowsims_reference_artifact"
                    ),
                },
            }
        )
        pipeline["capture"]["admitted"] = False
        pipeline["acceptance_decision"]["admitted"] = False
        return pipeline

    review_command = _rotation_review_command(reference_artifacts)
    pipeline["rotation_review"]["argv"] = review_command
    pipeline["rotation_review"]["command"] = join(review_command)
    pipeline["rotation_review"]["compute_stats_input"] = _artifact_path(
        reference_artifacts["compute_stats"]
    )
    return pipeline
