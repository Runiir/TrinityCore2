"""Run the serial all-spec Phase 8 live calibration campaign."""

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
from .live_validation_session import canonical_sha256
from .phase8_calibration_adapter import DEFAULT_TARGETS
from .phase8_evidence_identity import validate_manifest as validate_evidence_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts/all_spec_program/phase8_live_calibration_20260719"
DEFAULT_DPS_REPRESENTATIVES = (
    REPO_ROOT / "experiments/configs/phase8_dps_representatives_cata_p4_v1.json"
)
DPS_CLASSES = {
    "warrior",
    "paladin",
    "hunter",
    "rogue",
    "death_knight",
    "shaman",
    "mage",
    "warlock",
    "priest",
    "druid",
}
MODES_BY_ROLE = {
    "dps": ("single_target_300", "aoe_300"),
    "tank": ("single_target_300", "tank_threat_300"),
    "healer": ("healer_controlled_damage_300",),
}


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def load_targets(path: Path = DEFAULT_TARGETS) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "all_spec_targets_cata_p4_v1":
        raise ValueError("unexpected all-spec target catalog schema")
    targets = [dict(row) for row in payload.get("targets") or [] if isinstance(row, Mapping)]
    role_counts = {role: sum(str(row.get("role") or "") == role for row in targets) for role in MODES_BY_ROLE}
    if len(targets) != 31 or role_counts != {"dps": 22, "tank": 4, "healer": 5}:
        raise ValueError(f"invalid canonical target coverage: count={len(targets)} roles={role_counts}")
    return targets


def load_dps_representatives(
    path: Path = DEFAULT_DPS_REPRESENTATIVES,
) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "phase8_dps_representatives_cata_p4_v1":
        raise ValueError("unexpected Phase 8 DPS representative schema")
    representatives = {
        str(class_name): str(spec_target_id)
        for class_name, spec_target_id in (payload.get("representatives") or {}).items()
    }
    if set(representatives) != DPS_CLASSES:
        raise ValueError(
            "Phase 8 requires exactly one DPS representative for every DPS-capable class"
        )
    targets = {str(row["spec_target_id"]): row for row in load_targets()}
    selected_ids = set(representatives.values())
    if len(selected_ids) != len(DPS_CLASSES):
        raise ValueError("Phase 8 DPS representatives must be unique")
    for class_name, target_id in representatives.items():
        target = targets.get(target_id)
        if not target or target.get("role") != "dps" or target.get("class_name") != class_name:
            raise ValueError(
                f"invalid Phase 8 DPS representative: {class_name}={target_id}"
            )
    return representatives


def campaign_targets(
    targets: Sequence[Mapping[str, Any]],
    dps_representatives: Mapping[str, str],
) -> list[dict[str, Any]]:
    selected_ids = set(dps_representatives.values())
    selected = [
        dict(target)
        for target in targets
        if target.get("role") != "dps" or target.get("spec_target_id") in selected_ids
    ]
    role_counts = {
        role: sum(str(row.get("role") or "") == role for row in selected)
        for role in MODES_BY_ROLE
    }
    if len(selected) != 19 or role_counts != {"dps": 10, "tank": 4, "healer": 5}:
        raise ValueError(
            f"invalid Phase 8 representative target coverage: count={len(selected)} roles={role_counts}"
        )
    return selected


def campaign_attempts(
    targets: Sequence[Mapping[str, Any]],
    seeds: Sequence[int],
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    index = 0
    for seed in seeds:
        for target in targets:
            target_id = str(target.get("spec_target_id") or "")
            runtime_key = str(target.get("runtime_join_key") or "")
            role = str(target.get("role") or "")
            for mode in MODES_BY_ROLE[role]:
                index += 1
                attempt_id = f"seed-{seed:02d}/{target_id}/{mode}"
                attempts.append(
                    {
                        "attempt_index": index,
                        "attempt_id": attempt_id,
                        "cohort_id": _slug(f"p8-s{seed}-{target_id}-{mode}"),
                        "seed": seed,
                        "spec_target_id": target_id,
                        "runtime_join_key": runtime_key,
                        "class_name": str(target.get("class_name") or ""),
                        "role": role,
                        "mode": mode,
                    }
                )
    return attempts


def attempt_base_dir(output_root: Path, attempt: Mapping[str, Any]) -> Path:
    return output_root / "attempts" / str(attempt["attempt_id"])


def attempt_directory_candidates(output_root: Path, attempt: Mapping[str, Any]) -> list[Path]:
    base = attempt_base_dir(output_root, attempt)
    retries = sorted(base.parent.glob(f"{base.name}-retry-*")) if base.parent.exists() else []
    return [base, *retries]


def published_attempt_dirs(
    output_root: Path,
    attempt: Mapping[str, Any],
) -> list[Path]:
    return [
        path
        for path in attempt_directory_candidates(output_root, attempt)
        if valid_publication(path, attempt)
    ]


def publication_passed(attempt_dir: Path) -> bool:
    try:
        report = json.loads((attempt_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (report.get("role_calibration_evaluation") or {}).get("passed") is True


def completed_attempt_dir(output_root: Path, attempt: Mapping[str, Any]) -> Path | None:
    return next(
        (
            path
            for path in reversed(published_attempt_dirs(output_root, attempt))
            if publication_passed(path)
        ),
        None,
    )


def next_attempt_dir(output_root: Path, attempt: Mapping[str, Any]) -> Path:
    base = attempt_base_dir(output_root, attempt)
    if not base.exists():
        return base
    retry = 1
    while (base.parent / f"{base.name}-retry-{retry:02d}").exists():
        retry += 1
    return base.parent / f"{base.name}-retry-{retry:02d}"


def valid_publication(
    attempt_dir: Path,
    attempt: Mapping[str, Any] | None = None,
) -> bool:
    report_path = attempt_dir / "report.json"
    receipt_path = attempt_dir / "batch/retained/publication_receipt.json"
    manifest_path = attempt_dir / "batch/retained/final_manifest.json"
    if not report_path.is_file() or not receipt_path.is_file() or not manifest_path.is_file():
        return False
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not all(isinstance(row, Mapping) for row in (report, receipt, manifest)):
        return False
    receipt_identity = dict(receipt)
    stored_hash = str(receipt_identity.pop("receipt_sha256", ""))
    valid = bool(
        stored_hash
        and canonical_sha256(receipt_identity) == stored_hash
        and receipt.get("remote_verified") is True
        and receipt.get("batch_identity_sha256") == manifest.get("identity_sha256")
        and isinstance(report.get("role_calibration_evaluation"), Mapping)
        and isinstance(report.get("role_calibration_identity"), Mapping)
        and (report.get("evidence_envelope") or {}).get("identity_complete") is True
        and len(str((report.get("evidence_envelope") or {}).get("identity_manifest_sha256") or "")) == 64
    )
    if not valid or attempt is None:
        return valid
    requested = report.get("requested_calibration") or {}
    identity = report.get("role_calibration_identity") or {}
    session = report.get("session") or {}
    return bool(
        requested.get("mode") == attempt.get("mode")
        and requested.get("target_spec") == attempt.get("runtime_join_key")
        and int(requested.get("seed") or 0) == int(attempt.get("seed") or 0)
        and identity.get("spec_target_id") == attempt.get("spec_target_id")
        and identity.get("runtime_join_key") == attempt.get("runtime_join_key")
        and int(identity.get("seed") or 0) == int(attempt.get("seed") or 0)
        and session.get("cohort_id") == attempt.get("cohort_id")
    )


def compact_result(attempt: Mapping[str, Any], attempt_dir: Path, returncode: int) -> dict[str, Any]:
    report_path = attempt_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    evaluation = report.get("role_calibration_evaluation") or {}
    receipt_path = attempt_dir / "batch/retained/publication_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
    return {
        **dict(attempt),
        "returncode": returncode,
        "published": valid_publication(attempt_dir, attempt),
        "passed": bool(evaluation.get("passed")),
        "hard_floor_passed": bool(evaluation.get("hard_floor_passed")),
        "optimization_target_met": bool(evaluation.get("optimization_target_met")),
        "reference_ratio": float(evaluation.get("reference_ratio") or 0.0),
        "failure_reasons": list(evaluation.get("failure_reasons") or report.get("failure_labels") or []),
        "record_sha256": evaluation.get("record_sha256"),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "report_path": str(report_path.relative_to(REPO_ROOT)) if report_path.is_file() else "",
    }


def write_campaign_state(
    output_root: Path,
    attempts: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    *,
    active_attempt: Mapping[str, Any] | None,
    dps_representatives: Mapping[str, str],
) -> dict[str, Any]:
    completed_ids = {
        str(row.get("attempt_id") or "")
        for row in results
        if row.get("published") and row.get("passed")
    }
    qualification_failures = [dict(row) for row in results if row.get("published") and not row.get("passed")]
    infrastructure_failures = [dict(row) for row in results if not row.get("published")]
    backlog = [
        dict(row)
        for row in results
        if row.get("hard_floor_passed") and not row.get("optimization_target_met")
    ]
    state = {
        "schema": "all_spec_phase8_live_campaign_state_v2",
        "generated_at_unix": int(time.time()),
        "dps_qualification_policy": "one_representative_per_class_at_75_percent_floor",
        "dps_representatives": dict(sorted(dps_representatives.items())),
        "dps_representatives_sha256": canonical_sha256(dict(sorted(dps_representatives.items()))),
        "attempt_count": len(attempts),
        "completed_attempt_count": len(completed_ids),
        "remaining_attempt_count": len(attempts) - len(completed_ids),
        "active_attempt": dict(active_attempt) if active_attempt else None,
        "published_attempt_count": sum(bool(row.get("published")) for row in results),
        "passing_attempt_count": sum(bool(row.get("passed")) for row in results),
        "hard_floor_failure_count": sum(not bool(row.get("hard_floor_passed")) for row in results),
        "optimization_backlog_count": len(backlog),
        "qualification_failures": qualification_failures,
        "infrastructure_failures": infrastructure_failures,
        "optimization_backlog": backlog,
        "results": [dict(row) for row in results],
    }
    state["state_sha256"] = canonical_sha256(state)
    write_json(output_root / "campaign_state.json", state)
    return state


def child_command(args: argparse.Namespace, attempt: Mapping[str, Any], attempt_dir: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "tools.bot_ml.run_live_bot_validation",
        "--transport",
        "session",
        "--worldserver",
        str(args.worldserver),
        "--config",
        str(args.config),
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
        "--bot-pool-tag",
        "all_spec_candidate_pool",
        "--publish-batch",
    ]
    if args.evidence_identity_manifest:
        command.extend(
            [
                "--evidence-identity-manifest",
                str(args.evidence_identity_manifest),
            ]
        )
    if args.retain_published_batch:
        command.append("--retain-published-batch")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver"))
    parser.add_argument("--config", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--dps-representatives",
        type=Path,
        default=DEFAULT_DPS_REPRESENTATIVES,
    )
    parser.add_argument("--session-environment", default="phase8-calibration")
    parser.add_argument("--evidence-identity-manifest", type=Path)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--heartbeat-sec", type=int, default=30)
    parser.add_argument("--session-transition-timeout-sec", type=int, default=360)
    parser.add_argument("--retain-published-batch", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Run at most this many pending attempts; zero runs all.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.seeds != [1, 2, 3]:
        raise SystemExit("Phase 8 requires the canonical ordered seeds: 1 2 3")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    try:
        dps_representatives = load_dps_representatives(args.dps_representatives.resolve())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid --dps-representatives: {exc}") from exc
    targets = campaign_targets(load_targets(), dps_representatives)
    attempts = campaign_attempts(targets, args.seeds)
    payload = {
        "schema": "all_spec_phase8_live_campaign_plan_v2",
        "dps_qualification_policy": "one_representative_per_class_at_75_percent_floor",
        "dps_representatives": dict(sorted(dps_representatives.items())),
        "dps_representatives_sha256": canonical_sha256(
            dict(sorted(dps_representatives.items()))
        ),
        "target_count": len(targets),
        "attempt_count": len(attempts),
        "seeds": args.seeds,
        "attempts": attempts,
    }
    representatives_payload = {
        "schema": "phase8_dps_representatives_cata_p4_v1",
        "qualification_policy": "one_representative_per_class_at_75_percent_floor",
        "representatives": dict(sorted(dps_representatives.items())),
        "representatives_sha256": canonical_sha256(
            dict(sorted(dps_representatives.items()))
        ),
    }
    campaign_representatives = output_root / "dps_representatives.json"
    if campaign_representatives.is_file():
        existing_representatives = json.loads(
            campaign_representatives.read_text(encoding="utf-8")
        )
        if existing_representatives != representatives_payload:
            raise SystemExit("campaign DPS representatives cannot change while resuming")
    else:
        write_json(campaign_representatives, representatives_payload)
    write_json(output_root / "campaign_plan.json", payload)
    if args.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if not args.evidence_identity_manifest:
        raise SystemExit("--evidence-identity-manifest is required for live Phase 8 execution")
    try:
        manifest_payload = validate_evidence_manifest(
            json.loads(args.evidence_identity_manifest.read_text(encoding="utf-8"))
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid --evidence-identity-manifest: {exc}") from exc
    campaign_manifest = output_root / "evidence_identity_manifest.json"
    if campaign_manifest.is_file():
        try:
            existing_manifest = validate_evidence_manifest(
                json.loads(campaign_manifest.read_text(encoding="utf-8"))
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SystemExit(f"invalid campaign evidence identity manifest: {exc}") from exc
        if existing_manifest["manifest_sha256"] != manifest_payload["manifest_sha256"]:
            raise SystemExit("campaign evidence identity manifest cannot change while resuming")
    else:
        write_json(campaign_manifest, manifest_payload)
    args.evidence_identity_manifest = campaign_manifest

    if not os.environ.get("TRINITY_SOAP_USER") or not os.environ.get("TRINITY_SOAP_PASSWORD"):
        raise SystemExit("TRINITY_SOAP_USER and TRINITY_SOAP_PASSWORD are required")

    results: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for attempt in attempts:
        published_dirs = published_attempt_dirs(output_root, attempt)
        passing_dir = next(
            (path for path in reversed(published_dirs) if publication_passed(path)),
            None,
        )
        current_dir = passing_dir or (published_dirs[-1] if published_dirs else None)
        if current_dir is not None:
            results.append(compact_result(attempt, current_dir, 0))
        if passing_dir is None:
            pending.append(attempt)
    if args.limit > 0:
        pending = pending[: args.limit]
    write_campaign_state(
        output_root,
        attempts,
        results,
        active_attempt=None,
        dps_representatives=dps_representatives,
    )

    for attempt in pending:
        attempt_dir = next_attempt_dir(output_root, attempt)
        attempt_dir.mkdir(parents=True, exist_ok=False)
        write_campaign_state(
            output_root,
            attempts,
            results,
            active_attempt=attempt,
            dps_representatives=dps_representatives,
        )
        command = child_command(args, attempt, attempt_dir)
        with (attempt_dir / "runner.log").open("w", encoding="utf-8") as stream:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=os.environ.copy(),
                stdout=stream,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        result = compact_result(attempt, attempt_dir, completed.returncode)
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
            dps_representatives=dps_representatives,
        )
        print(
            json.dumps(
                {
                    "attempt_id": attempt["attempt_id"],
                    "published": result["published"],
                    "passed": result["passed"],
                    "reference_ratio": result["reference_ratio"],
                    "failure_reasons": result["failure_reasons"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if not result["published"]:
            return 2
        if not result["passed"]:
            return 1

    state = write_campaign_state(
        output_root,
        attempts,
        results,
        active_attempt=None,
        dps_representatives=dps_representatives,
    )
    complete = state["completed_attempt_count"] == state["attempt_count"]
    qualified = complete and not state["qualification_failures"] and not state["infrastructure_failures"]
    return 0 if qualified else 1


if __name__ == "__main__":
    raise SystemExit(main())
