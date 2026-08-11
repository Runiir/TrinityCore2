"""Build the deterministic Phase 9 serial Stonecore canary run plan."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from .common import write_json
from .live_validation_session import canonical_sha256, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = REPO_ROOT / "experiments/configs/stonecore_phase9_pairwise_matrix_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/all_spec_program/phase9_serial_canaries_20260728"


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def render_command(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def build_plan(
    matrix_path: Path,
    output_root: Path,
    evidence_identity_manifest: Path,
    session_environment: str,
    cohort_id: str,
) -> dict[str, Any]:
    matrix = load_object(matrix_path)
    if matrix.get("schema") != "stonecore_phase9_pairwise_matrix_v1":
        raise ValueError("unexpected Phase 9 matrix schema")
    compositions = {
        str(row["composition_id"]): row for row in matrix.get("compositions") or []
    }
    attempts: list[dict[str, Any]] = []
    for serial in matrix.get("serial_canaries") or []:
        serial_index = int(serial["serial_index"])
        composition_id = str(serial["composition_id"])
        composition = compositions.get(composition_id)
        if not composition:
            raise ValueError(f"serial canary references unknown composition: {composition_id}")
        ordered_party = [str(value) for value in composition.get("ordered_party") or []]
        if len(ordered_party) != 5:
            raise ValueError(f"serial canary has malformed ordered party: {composition_id}")
        attempt_id = f"phase9_serial_{serial_index:02d}_{composition_id}"
        attempt_dir = output_root / attempt_id
        command = [
            "pixi",
            "run",
            "python",
            "-m",
            "tools.bot_ml.run_live_bot_validation",
            "--transport",
            "session",
            "--session-environment",
            session_environment,
            "--session-runtime-dir",
            str(output_root / "session_runtime"),
            "--session-profile",
            "stonecore_5n",
            "--cohort-id",
            cohort_id,
            "--session-attempt-index",
            str(serial_index),
            "--validation-scenario-id",
            "stonecore_5n",
            "--validation-route-manifest",
            "--duration-policy",
            "completion-watchdog",
            "--observe-sec",
            "300",
            "--timeout-sec",
            "2100",
            "--publish-batch",
            "--skip-route-bot-start-mutation",
            "--evidence-identity-manifest",
            str(evidence_identity_manifest),
            "--output-dir",
            str(attempt_dir),
        ]
        for target in ordered_party:
            command.extend(("--party-spec-target", target))
        attempts.append(
            {
                "attempt_id": attempt_id,
                "serial_index": serial_index,
                "composition_id": composition_id,
                "composition_sha256": composition["composition_sha256"],
                "ordered_party": ordered_party,
                "party_sha256": canonical_sha256(ordered_party),
                "new_targets": list(serial.get("new_targets") or []),
                "output_dir": str(attempt_dir.relative_to(REPO_ROOT)),
                "command": command,
                "command_text": render_command(command),
            }
        )
    target_union = sorted(
        {target for attempt in attempts for target in attempt["ordered_party"]}
    )
    expected_target_union = sorted(str(value) for value in matrix.get("serial_target_union") or [])
    plan: dict[str, Any] = {
        "schema": "all_spec_phase9_serial_run_plan_v1",
        "matrix_path": str(matrix_path.relative_to(REPO_ROOT)),
        "matrix_file_sha256": sha256_file(matrix_path),
        "matrix_identity_sha256": matrix.get("matrix_sha256"),
        "evidence_identity_manifest_path": str(evidence_identity_manifest.relative_to(REPO_ROOT)),
        "session_environment": session_environment,
        "session_runtime_dir": str((output_root / "session_runtime").relative_to(REPO_ROOT)),
        "cohort_id": cohort_id,
        "runtime_profile": "stonecore_5n",
        "candidate_pool_tag": "all_spec_candidate_pool",
        "transport": "session",
        "max_active_cohorts": 1,
        "route_mode": "strict_uninterrupted_current_manifest_full_clear",
        "route_node_count": 14,
        "observe_sec": 300,
        "timeout_sec": 2100,
        "publish_each_closed_batch": True,
        "remote_verify_before_evict": True,
        "attempt_count": len(attempts),
        "canonical_target_count": int(matrix.get("canonical_target_count") or matrix.get("target_count") or 0),
        "qualification_excluded_targets": list(matrix.get("qualification_excluded_targets") or []),
        "target_union": target_union,
        "target_union_count": len(target_union),
        "attempts": attempts,
    }
    if (
        len(attempts) != int(matrix.get("serial_canary_count") or 0)
        or target_union != expected_target_union
        or len(target_union) != int(matrix.get("target_count") or 0)
    ):
        raise ValueError("serial run plan does not preserve the matrix canary set and live-qualification target union")
    plan["plan_sha256"] = canonical_sha256(plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-identity-manifest", type=Path, required=True)
    parser.add_argument("--session-environment", default="phase9-serial-stonecore")
    parser.add_argument("--cohort-id", default="phase9-serial-canary")
    args = parser.parse_args()
    matrix_path = args.matrix.resolve()
    output_root = args.output_root.resolve()
    evidence_identity_manifest = args.evidence_identity_manifest.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    plan = build_plan(
        matrix_path,
        output_root,
        evidence_identity_manifest,
        args.session_environment,
        args.cohort_id,
    )
    write_json(output_root / "run_plan.json", plan)
    (output_root / "commands.txt").write_text(
        "\n".join(row["command_text"] for row in plan["attempts"]) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "plan_sha256": plan["plan_sha256"],
                "attempt_count": plan["attempt_count"],
                "target_union_count": plan["target_union_count"],
                "output_root": str(output_root),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
