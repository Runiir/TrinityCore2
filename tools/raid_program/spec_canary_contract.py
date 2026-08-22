#!/usr/bin/env python3
"""Build the deterministic capture/review/decision contract for one DPS canary."""

from __future__ import annotations

from typing import Any, Mapping


def build_canary_pipeline(
    spec: str, reference_artifacts: Mapping[str, Any] | None
) -> dict[str, Any]:
    if reference_artifacts is None:
        return {"state": "requires_exact_reference_hydration_or_generation"}
    return {
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
            "runtime_inputs": {
                "trinity_profile": "<canary>/identity/rotation-profile.json",
                "runtime_report": "<canary>/run/report.json",
            },
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
