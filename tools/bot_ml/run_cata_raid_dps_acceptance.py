"""Run the current 25H DPS matrix with 75% hard and 85% optimization gates."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import write_json
from .live_validation_session import canonical_sha256, sha256_file
from .phase8_evidence_identity import validate_manifest as validate_evidence_manifest
from .run_phase8_all_spec_calibration import (
    compact_result,
    load_targets,
    next_attempt_dir,
    published_attempt_dirs,
)
from .verify_cata_raid_dps_acceptance import verify as verify_acceptance


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "experiments/configs/cata_raid_dps_acceptance_v1.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts/all_spec_program/cata_raid_dps_acceptance"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _resolve(config_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def acceptance_targets(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_id = {
        str(row.get("spec_target_id") or ""): dict(row)
        for row in load_targets()
    }
    target_ids = [str(value) for value in config.get("dps_targets") or []]
    selected = [by_id[target_id] for target_id in target_ids if target_id in by_id]
    if len(selected) != len(target_ids) or any(row.get("role") != "dps" for row in selected):
        raise ValueError("DPS acceptance targets must resolve to canonical DPS rows")
    return selected


def campaign_attempts(
    targets: Sequence[Mapping[str, Any]],
    modes: Sequence[str],
    seeds: Sequence[int],
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    index = 0
    for seed in seeds:
        for target in targets:
            for mode in modes:
                index += 1
                target_id = str(target["spec_target_id"])
                attempts.append(
                    {
                        "attempt_index": index,
                        "attempt_id": f"seed-{seed:02d}/{target_id}/{mode}",
                        "cohort_id": f"dps85-s{seed}-{target_id}-{mode}".replace("_", "-"),
                        "seed": int(seed),
                        "spec_target_id": target_id,
                        "runtime_join_key": str(target["runtime_join_key"]),
                        "class_name": str(target["class_name"]),
                        "role": "dps",
                        "mode": str(mode),
                    }
                )
    return attempts


def attempt_accepted(result: Mapping[str, Any]) -> bool:
    return bool(
        result.get("published")
        and result.get("passed")
        and result.get("hard_floor_passed")
        and result.get("optimization_target_met")
        and result.get("targeted_eviction_complete")
    )


def targeted_eviction_complete(attempt_dir: Path) -> bool:
    batch = attempt_dir / "batch"
    return bool(
        (batch / "retained/publication_receipt.json").is_file()
        and not (batch / "raw").exists()
        and not (batch / "compact").exists()
        and not (batch / ".batch-dvc-cache").exists()
    )


def compact_acceptance_result(
    attempt: Mapping[str, Any], attempt_dir: Path, returncode: int
) -> dict[str, Any]:
    result = compact_result(attempt, attempt_dir, returncode)
    result["targeted_eviction_complete"] = targeted_eviction_complete(attempt_dir)
    result["accepted"] = attempt_accepted(result)
    return result


def write_campaign_state(
    output_root: Path,
    attempts: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    *,
    active_attempt: Mapping[str, Any] | None,
    config_path: Path,
    policy_path: Path,
) -> dict[str, Any]:
    result_by_id = {
        str(row.get("attempt_id") or ""): dict(row) for row in results
    }
    ordered_results = [
        result_by_id[str(attempt["attempt_id"])]
        for attempt in attempts
        if str(attempt["attempt_id"]) in result_by_id
    ]
    accepted_ids = {
        str(row.get("attempt_id") or "")
        for row in ordered_results
        if attempt_accepted(row)
    }
    target_rows = []
    for target_id in sorted(
        {str(attempt["spec_target_id"]) for attempt in attempts}
    ):
        rows = [
            row
            for row in ordered_results
            if row.get("spec_target_id") == target_id
        ]
        target_rows.append(
            {
                "spec_target_id": target_id,
                "attempt_count": len(rows),
                "accepted_attempt_count": sum(attempt_accepted(row) for row in rows),
                "minimum_reference_ratio": min(
                    (float(row.get("reference_ratio") or 0.0) for row in rows),
                    default=0.0,
                ),
                "hard_floor_passed": bool(rows)
                and all(bool(row.get("hard_floor_passed")) for row in rows),
                "optimization_target_met": bool(rows)
                and all(bool(row.get("optimization_target_met")) for row in rows),
                "remote_verified_and_evicted": bool(rows)
                and all(
                    bool(row.get("published"))
                    and bool(row.get("targeted_eviction_complete"))
                    for row in rows
                ),
            }
        )
    state = {
        "schema": "cata_raid_dps_acceptance_campaign_state_v1",
        "generated_at_unix": int(time.time()),
        "config_path": str(config_path.relative_to(REPO_ROOT)),
        "config_sha256": sha256_file(config_path),
        "policy_path": str(policy_path.relative_to(REPO_ROOT)),
        "policy_sha256": sha256_file(policy_path),
        "hard_reference_ratio": 0.75,
        "optimization_reference_ratio": 0.85,
        "target_count": len(target_rows),
        "attempt_count": len(attempts),
        "accepted_attempt_count": len(accepted_ids),
        "remaining_attempt_count": len(attempts) - len(accepted_ids),
        "active_attempt": dict(active_attempt) if active_attempt else None,
        "target_rows": target_rows,
        "results": ordered_results,
    }
    state["passed"] = bool(
        state["attempt_count"] == state["accepted_attempt_count"]
        and state["target_count"] == 16
        and all(row["hard_floor_passed"] for row in target_rows)
        and all(row["optimization_target_met"] for row in target_rows)
        and all(row["remote_verified_and_evicted"] for row in target_rows)
    )
    state["state_sha256"] = canonical_sha256(state)
    write_json(output_root / "campaign_state.json", state)
    return state


def child_command(
    args: argparse.Namespace,
    attempt: Mapping[str, Any],
    attempt_dir: Path,
    policy_path: Path,
    manifest_path: Path,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "tools.bot_ml.run_live_bot_validation",
        "--transport",
        "session",
        "--worldserver",
        str(args.worldserver),
        "--config",
        str(args.worldserver_config),
        "--output-dir",
        str(attempt_dir),
        "--duration-policy",
        "completion-watchdog",
        "--timeout-sec",
        str(args.timeout_sec),
        "--heartbeat-sec",
        str(args.heartbeat_sec),
        "--session-transition-timeout-sec",
        str(args.session_transition_timeout_sec),
        "--session-environment",
        args.session_environment,
        "--session-profile",
        "phase8_calibration",
        "--cohort-id",
        str(attempt["cohort_id"]),
        "--session-attempt-index",
        str(attempt["attempt_index"]),
        "--calibration-only",
        "--calibration-reference-conditions",
        "--calibration-mode",
        str(attempt["mode"]),
        "--calibration-target-spec",
        str(attempt["runtime_join_key"]),
        "--calibration-seed",
        str(attempt["seed"]),
        "--role-calibration-policy",
        str(policy_path),
        "--bot-pool-tag",
        "all_spec_candidate_pool",
        "--publish-batch",
        "--evidence-identity-manifest",
        str(manifest_path),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver")
    )
    parser.add_argument(
        "--worldserver-config", type=Path, default=Path("trinity-worldserver-test.conf")
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--session-environment", default="cata-raid-dps85")
    parser.add_argument("--evidence-identity-manifest", type=Path)
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--heartbeat-sec", type=int, default=30)
    parser.add_argument("--session-transition-timeout-sec", type=int, default=360)
    parser.add_argument(
        "--limit", type=int, default=0, help="Run at most this many pending attempts; zero runs all."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = args.acceptance_config.resolve()
    verification = verify_acceptance(config_path)
    if not verification["passed"]:
        raise SystemExit("DPS acceptance contract verification failed")
    config = _load(config_path)
    acceptance = config.get("acceptance") or {}
    if acceptance.get("evict_after_remote_verification") is not True or acceptance.get(
        "retain_published_batch"
    ) is not False:
        raise SystemExit("DPS acceptance must use verified targeted eviction")

    policy_path = _resolve(config_path, str(config["role_calibration_policy"])).resolve()
    targets = acceptance_targets(config)
    modes = [str(value) for value in config.get("modes") or []]
    seeds = [int(value) for value in config.get("seeds") or []]
    attempts = campaign_attempts(targets, modes, seeds)
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema": "cata_raid_dps_acceptance_campaign_plan_v1",
        "verification_sha256": verification["verification_sha256"],
        "target_count": len(targets),
        "attempt_count": len(attempts),
        "hard_reference_ratio": 0.75,
        "optimization_reference_ratio": 0.85,
        "publish_batch": True,
        "retain_published_batch": False,
        "attempts": attempts,
    }
    plan["plan_sha256"] = canonical_sha256(plan)
    write_json(output_root / "campaign_plan.json", plan)
    write_json(output_root / "acceptance_verification.json", verification)
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    if not args.evidence_identity_manifest:
        raise SystemExit("--evidence-identity-manifest is required for live DPS acceptance")
    try:
        manifest = validate_evidence_manifest(
            _load(args.evidence_identity_manifest.resolve())
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid --evidence-identity-manifest: {exc}") from exc
    campaign_manifest_path = output_root / "evidence_identity_manifest.json"
    if campaign_manifest_path.is_file():
        existing = validate_evidence_manifest(_load(campaign_manifest_path))
        if existing["manifest_sha256"] != manifest["manifest_sha256"]:
            raise SystemExit("campaign evidence manifest cannot change while resuming")
    else:
        write_json(campaign_manifest_path, manifest)

    if not os.environ.get("TRINITY_SOAP_USER") or not os.environ.get("TRINITY_SOAP_PASSWORD"):
        raise SystemExit("TRINITY_SOAP_USER and TRINITY_SOAP_PASSWORD are required")

    results: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for attempt in attempts:
        published_dirs = published_attempt_dirs(output_root, attempt)
        accepted_dir = None
        for attempt_dir in reversed(published_dirs):
            result = compact_acceptance_result(attempt, attempt_dir, 0)
            if attempt_accepted(result):
                accepted_dir = attempt_dir
                break
        current_dir = accepted_dir or (published_dirs[-1] if published_dirs else None)
        if current_dir is not None:
            results.append(compact_acceptance_result(attempt, current_dir, 0))
        if accepted_dir is None:
            pending.append(attempt)
    if args.limit > 0:
        pending = pending[: args.limit]
    write_campaign_state(
        output_root,
        attempts,
        results,
        active_attempt=None,
        config_path=config_path,
        policy_path=policy_path,
    )

    for attempt in pending:
        attempt_dir = next_attempt_dir(output_root, attempt)
        attempt_dir.mkdir(parents=True, exist_ok=False)
        write_campaign_state(
            output_root,
            attempts,
            results,
            active_attempt=attempt,
            config_path=config_path,
            policy_path=policy_path,
        )
        command = child_command(
            args, attempt, attempt_dir, policy_path, campaign_manifest_path
        )
        runner_log = attempt_dir / "runner.log"
        with runner_log.open("w", encoding="utf-8") as stream:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=os.environ.copy(),
                stdout=stream,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        result = compact_acceptance_result(attempt, attempt_dir, completed.returncode)
        if result["published"] and result["targeted_eviction_complete"]:
            runner_log.unlink(missing_ok=True)
            result["runner_log_evicted_after_publication"] = True
        else:
            result["runner_log_evicted_after_publication"] = False
        result["accepted"] = attempt_accepted(result)
        results = [
            row
            for row in results
            if row.get("attempt_id") != attempt.get("attempt_id")
        ]
        results.append(result)
        write_campaign_state(
            output_root,
            attempts,
            results,
            active_attempt=None,
            config_path=config_path,
            policy_path=policy_path,
        )
        print(
            json.dumps(
                {
                    "attempt_id": attempt["attempt_id"],
                    "accepted": result["accepted"],
                    "published": result["published"],
                    "targeted_eviction_complete": result[
                        "targeted_eviction_complete"
                    ],
                    "reference_ratio": result["reference_ratio"],
                    "failure_reasons": result["failure_reasons"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if not result["published"] or not result["targeted_eviction_complete"]:
            return 2
        if not result["accepted"]:
            return 1

    state = write_campaign_state(
        output_root,
        attempts,
        results,
        active_attempt=None,
        config_path=config_path,
        policy_path=policy_path,
    )
    return 0 if state["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
