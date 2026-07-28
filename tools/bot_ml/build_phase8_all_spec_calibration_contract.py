"""Build the aggregate Phase 8 all-spec live calibration contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .common import write_json
from .live_validation_session import canonical_sha256, sha256_file
from .phase8_evidence_identity import validate_manifest as validate_evidence_manifest
from .run_phase8_all_spec_calibration import (
    DPS_CLASSES,
    attempt_base_dir,
    campaign_attempts,
    campaign_targets,
    load_targets,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAMPAIGN_ROOT = REPO_ROOT / "artifacts/all_spec_program/phase8_live_calibration_20260719"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts/all_spec_program/phase8_all_spec_calibration_contract_20260719"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _receipt_valid(attempt_dir: Path) -> tuple[bool, dict[str, Any]]:
    receipt_path = attempt_dir / "batch/retained/publication_receipt.json"
    manifest_path = attempt_dir / "batch/retained/final_manifest.json"
    if not receipt_path.is_file() or not manifest_path.is_file():
        return False, {}
    try:
        receipt = _load(receipt_path)
        manifest = _load(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False, {}
    identity = dict(receipt)
    stored_hash = str(identity.pop("receipt_sha256", ""))
    valid = bool(
        stored_hash
        and canonical_sha256(identity) == stored_hash
        and receipt.get("remote_verified") is True
        and receipt.get("batch_identity_sha256") == manifest.get("identity_sha256")
    )
    return valid, receipt


def build_contract(campaign_root: Path) -> dict[str, Any]:
    campaign_root = campaign_root.resolve()
    campaign_state_path = campaign_root / "campaign_state.json"
    state = _load(campaign_state_path)
    if state.get("schema") != "all_spec_phase8_live_campaign_state_v2":
        raise ValueError("unexpected Phase 8 campaign state schema")
    representatives_path = campaign_root / "dps_representatives.json"
    representatives_payload = _load(representatives_path)
    if representatives_payload.get("schema") != "phase8_dps_representatives_cata_p4_v1":
        raise ValueError("unexpected Phase 8 DPS representative schema")
    dps_representatives = {
        str(class_name): str(spec_target_id)
        for class_name, spec_target_id in (
            representatives_payload.get("representatives") or {}
        ).items()
    }
    representatives_sha256 = canonical_sha256(dict(sorted(dps_representatives.items())))
    representatives_valid = bool(
        set(dps_representatives) == DPS_CLASSES
        and len(set(dps_representatives.values())) == len(DPS_CLASSES)
        and representatives_payload.get("representatives_sha256") == representatives_sha256
        and state.get("dps_qualification_policy")
        == "one_representative_per_class_at_75_percent_floor"
        and state.get("dps_representatives") == dict(sorted(dps_representatives.items()))
        and state.get("dps_representatives_sha256") == representatives_sha256
    )
    state_identity = dict(state)
    stored_state_hash = str(state_identity.pop("state_sha256", ""))
    state_hash_valid = bool(stored_state_hash and canonical_sha256(state_identity) == stored_state_hash)
    evidence_manifest_path = campaign_root / "evidence_identity_manifest.json"
    try:
        evidence_manifest = validate_evidence_manifest(_load(evidence_manifest_path))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        evidence_manifest = {}
    evidence_manifest_hash = str(evidence_manifest.get("manifest_sha256") or "")
    evidence_components = evidence_manifest.get("component_hashes") or {}

    selected_targets = campaign_targets(load_targets(), dps_representatives)
    expected = campaign_attempts(selected_targets, [1, 2, 3])
    expected_ids = {str(row["attempt_id"]) for row in expected}
    state_results = [dict(row) for row in state.get("results") or [] if isinstance(row, Mapping)]
    state_result_ids = [str(row.get("attempt_id") or "") for row in state_results]
    result_by_id = {attempt_id: row for attempt_id, row in zip(state_result_ids, state_results)}
    actual_ids = set(state_result_ids)
    state_results_unique = bool(
        len(state_results) == len(state_result_ids) == len(actual_ids)
        and "" not in actual_ids
    )

    attempt_rows: list[dict[str, Any]] = []
    server_epochs: set[int] = set()
    server_process_ids: set[int] = set()
    profile_generations: set[int] = set()
    profile_hashes: set[str] = set()
    receipt_hashes: list[str] = []
    batch_identity_hashes: list[str] = []
    max_active_cohorts = 0
    for expected_row in expected:
        attempt_id = str(expected_row["attempt_id"])
        result = result_by_id.get(attempt_id) or {}
        report_relative = str(result.get("report_path") or "")
        report_path = (REPO_ROOT / report_relative).resolve() if report_relative else Path()
        try:
            report_path.relative_to(campaign_root)
            report_in_campaign = True
        except (ValueError, OSError):
            report_in_campaign = False
        report: dict[str, Any] = {}
        if report_relative and report_in_campaign and report_path.is_file():
            try:
                report = _load(report_path)
            except (OSError, ValueError, json.JSONDecodeError):
                report = {}
        evaluation = report.get("role_calibration_evaluation") or {}
        identity = report.get("role_calibration_identity") or {}
        if not identity and isinstance(report.get("role_calibration_record"), Mapping):
            identity = (report.get("role_calibration_record") or {}).get("identity") or {}
        requested = report.get("requested_calibration") or {}
        session = report.get("session") or {}
        attempt_dir = report_path.parent if report and report_path.name == "report.json" else Path()
        expected_base = attempt_base_dir(campaign_root, expected_row)
        retry_prefix = f"{expected_base.name}-retry-"
        retry_suffix = (
            attempt_dir.name.removeprefix(retry_prefix)
            if attempt_dir.parent == expected_base.parent
            else ""
        )
        attempt_path_valid = bool(
            report
            and (
                attempt_dir == expected_base
                or (
                    attempt_dir.parent == expected_base.parent
                    and attempt_dir.name.startswith(retry_prefix)
                    and retry_suffix.isdigit()
                    and int(retry_suffix) >= 1
                )
            )
        )
        receipt_valid, receipt = _receipt_valid(attempt_dir) if report else (False, {})
        receipt_sha256 = str(receipt.get("receipt_sha256") or "")
        batch_identity_sha256 = str(receipt.get("batch_identity_sha256") or "")
        if receipt_sha256:
            receipt_hashes.append(receipt_sha256)
        if batch_identity_sha256:
            batch_identity_hashes.append(batch_identity_sha256)
        expected_identity_valid = bool(
            requested.get("mode") == expected_row.get("mode")
            and requested.get("target_spec") == expected_row.get("runtime_join_key")
            and _int(requested.get("seed")) == _int(expected_row.get("seed"))
            and identity.get("spec_target_id") == expected_row.get("spec_target_id")
            and identity.get("runtime_join_key") == expected_row.get("runtime_join_key")
            and _int(identity.get("seed")) == _int(expected_row.get("seed"))
            and session.get("cohort_id") == expected_row.get("cohort_id")
            and _int(session.get("attempt_index")) == _int(expected_row.get("attempt_index"))
            and session.get("server_process_identity_verified") is True
            and _int(session.get("max_active_cohorts")) == 1
        )
        evaluation_failures = list(evaluation.get("failure_reasons") or [])
        state_result_valid = bool(
            result
            and result.get("spec_target_id") == expected_row.get("spec_target_id")
            and result.get("runtime_join_key") == expected_row.get("runtime_join_key")
            and result.get("class_name") == expected_row.get("class_name")
            and result.get("role") == expected_row.get("role")
            and result.get("mode") == expected_row.get("mode")
            and result.get("cohort_id") == expected_row.get("cohort_id")
            and _int(result.get("attempt_index")) == _int(expected_row.get("attempt_index"))
            and _int(result.get("seed")) == _int(expected_row.get("seed"))
            and result.get("published") is True
            and _int(result.get("returncode")) == 0
            and bool(result.get("passed")) == (evaluation.get("passed") is True)
            and bool(result.get("hard_floor_passed")) == (evaluation.get("hard_floor_passed") is True)
            and bool(result.get("optimization_target_met")) == (evaluation.get("optimization_target_met") is True)
            and abs(_float(result.get("reference_ratio")) - _float(evaluation.get("reference_ratio"))) < 1e-9
            and list(result.get("failure_reasons") or []) == evaluation_failures
            and result.get("record_sha256") == evaluation.get("record_sha256")
            and result.get("receipt_sha256") == receipt.get("receipt_sha256")
        )
        evidence_envelope = report.get("evidence_envelope") or {}
        try:
            validate_evidence_manifest(
                evidence_manifest,
                runtime_identity={
                    **session,
                    "profile_generation": identity.get("profile_generation"),
                    "profile_content_hash": identity.get("profile_content_hash"),
                },
            )
            runtime_manifest_valid = True
        except (TypeError, ValueError):
            runtime_manifest_valid = False
        evidence_identity_complete = bool(
            evidence_envelope.get("identity_complete") is True
            and evidence_envelope.get("identity_manifest_sha256") == evidence_manifest_hash
            and all(
                (evidence_envelope.get("component_hashes") or {}).get(name) == value
                for name, value in evidence_components.items()
            )
            and runtime_manifest_valid
        )
        server_epoch = _int(session.get("server_epoch"))
        server_process_id = _int(session.get("server_process_id"))
        profile_generation = _int(identity.get("profile_generation"))
        if server_epoch:
            server_epochs.add(server_epoch)
        if server_process_id:
            server_process_ids.add(server_process_id)
        if profile_generation:
            profile_generations.add(profile_generation)
        if identity.get("profile_content_hash"):
            profile_hashes.add(str(identity["profile_content_hash"]))
        max_active_cohorts = max(max_active_cohorts, _int(session.get("max_active_cohorts")))
        attempt_rows.append(
            {
                **expected_row,
                "report_path": report_relative,
                "report_sha256": sha256_file(report_path) if report else "",
                "report_in_campaign": report_in_campaign,
                "attempt_path_valid": attempt_path_valid,
                "expected_identity_valid": expected_identity_valid,
                "state_result_valid": state_result_valid,
                "evidence_identity_complete": evidence_identity_complete,
                "record_sha256": evaluation.get("record_sha256"),
                "receipt_sha256": receipt_sha256,
                "batch_identity_sha256": batch_identity_sha256,
                "receipt_valid": receipt_valid,
                "passed": evaluation.get("passed") is True,
                "hard_floor_passed": evaluation.get("hard_floor_passed") is True,
                "optimization_target_met": evaluation.get("optimization_target_met") is True,
                "reference_ratio": _float(evaluation.get("reference_ratio")),
                "failure_reasons": evaluation_failures,
            }
        )

    target_rows: list[dict[str, Any]] = []
    for target in selected_targets:
        target_id = str(target["spec_target_id"])
        rows = [row for row in attempt_rows if row["spec_target_id"] == target_id]
        target_rows.append(
            {
                "spec_target_id": target_id,
                "class_name": target["class_name"],
                "role": target["role"],
                "dps_class_representative": target.get("role") == "dps",
                "attempt_count": len(rows),
                "all_modes_and_seeds_passed": bool(rows) and all(row["passed"] for row in rows),
                "hard_floor_passed": bool(rows) and all(row["hard_floor_passed"] for row in rows),
                "minimum_reference_ratio": min((row["reference_ratio"] for row in rows), default=0.0),
                "optimization_target_met": bool(rows) and all(row["optimization_target_met"] for row in rows),
                "failed_attempt_ids": [row["attempt_id"] for row in rows if not row["passed"]],
            }
        )

    optimization_backlog = [
        {
            "attempt_id": row["attempt_id"],
            "spec_target_id": row["spec_target_id"],
            "mode": row["mode"],
            "seed": row["seed"],
            "reference_ratio": row["reference_ratio"],
        }
        for row in attempt_rows
        if row["hard_floor_passed"] and not row["optimization_target_met"]
    ]
    state_optimization_backlog = [
        {
            "attempt_id": str(row.get("attempt_id") or ""),
            "spec_target_id": str(row.get("spec_target_id") or ""),
            "mode": str(row.get("mode") or ""),
            "seed": _int(row.get("seed")),
            "reference_ratio": _float(row.get("reference_ratio")),
        }
        for row in state.get("optimization_backlog") or []
        if isinstance(row, Mapping)
    ]
    normalized_backlog = sorted(optimization_backlog, key=lambda row: row["attempt_id"])
    normalized_state_backlog = sorted(state_optimization_backlog, key=lambda row: row["attempt_id"])
    expected_attempt_count = 99
    expected_target_count = 19
    state_summary_consistent = bool(
        _int(state.get("attempt_count")) == len(expected) == expected_attempt_count
        and _int(state.get("completed_attempt_count"))
        == len(state_results)
        == expected_attempt_count
        and _int(state.get("remaining_attempt_count")) == 0
        and state.get("active_attempt") is None
        and _int(state.get("published_attempt_count")) == sum(bool(row.get("published")) for row in state_results)
        and _int(state.get("passing_attempt_count")) == sum(bool(row.get("passed")) for row in state_results)
        and _int(state.get("hard_floor_failure_count"))
        == sum(not bool(row.get("hard_floor_passed")) for row in state_results)
        and _int(state.get("optimization_backlog_count")) == len(state_optimization_backlog)
    )
    dps_target_rows = [row for row in target_rows if row["role"] == "dps"]
    support_target_rows = [row for row in target_rows if row["role"] != "dps"]
    checks = {
        "campaign_state_hash_valid": state_hash_valid,
        "evidence_identity_manifest_valid": bool(evidence_manifest_hash),
        "dps_representatives_valid": representatives_valid,
        "unique_state_results": state_results_unique,
        "exact_attempt_coverage": actual_ids == expected_ids
        and len(attempt_rows) == len(expected) == expected_attempt_count,
        "state_summary_consistent": state_summary_consistent,
        "all_reports_inside_campaign": all(row["report_in_campaign"] for row in attempt_rows),
        "all_attempt_paths_valid": all(row["attempt_path_valid"] for row in attempt_rows),
        "all_attempt_identities_valid": all(row["expected_identity_valid"] for row in attempt_rows),
        "all_state_results_match_evidence": all(row["state_result_valid"] for row in attempt_rows),
        "all_evidence_identities_complete": all(row["evidence_identity_complete"] for row in attempt_rows),
        "all_attempt_receipts_verified": all(row["receipt_valid"] for row in attempt_rows),
        "unique_receipt_hashes": len(receipt_hashes)
        == len(set(receipt_hashes))
        == expected_attempt_count,
        "unique_batch_identities": len(batch_identity_hashes)
        == len(set(batch_identity_hashes))
        == expected_attempt_count,
        "all_attempts_pass_role_gates": all(row["passed"] for row in attempt_rows),
        "all_attempts_meet_hard_floor": all(row["hard_floor_passed"] for row in attempt_rows),
        "all_10_dps_classes_qualified": len(dps_target_rows) == len(DPS_CLASSES)
        and {row["class_name"] for row in dps_target_rows} == DPS_CLASSES
        and all(row["all_modes_and_seeds_passed"] for row in dps_target_rows),
        "all_tanks_and_healers_qualified": len(support_target_rows) == 9
        and all(row["all_modes_and_seeds_passed"] for row in support_target_rows),
        "all_19_selected_targets_qualified": len(target_rows) == expected_target_count
        and all(row["all_modes_and_seeds_passed"] for row in target_rows),
        "one_server_epoch": len(server_epochs) == 1,
        "one_server_process": len(server_process_ids) == 1,
        "one_profile_generation": len(profile_generations) == 1,
        "one_profile_content_hash": len(profile_hashes) == 1,
        "one_active_cohort_maximum": max_active_cohorts == 1,
        "optimization_backlog_complete": normalized_backlog == normalized_state_backlog,
    }
    contract = {
        "schema": "all_spec_phase8_live_calibration_contract_v2",
        "dps_qualification_policy": "one_representative_per_class_at_75_percent_floor",
        "dps_representatives_path": _display_path(representatives_path),
        "dps_representatives_file_sha256": sha256_file(representatives_path),
        "dps_representatives_sha256": representatives_sha256,
        "dps_representatives": dict(sorted(dps_representatives.items())),
        "campaign_state_path": _display_path(campaign_state_path),
        "campaign_state_sha256": sha256_file(campaign_state_path),
        "evidence_identity_manifest_path": _display_path(evidence_manifest_path),
        "evidence_identity_manifest_sha256": evidence_manifest_hash,
        "target_count": len(target_rows),
        "attempt_count": len(attempt_rows),
        "seed_count": 3,
        "seeds": [1, 2, 3],
        "server_epochs": sorted(server_epochs),
        "server_process_ids": sorted(server_process_ids),
        "profile_generations": sorted(profile_generations),
        "profile_content_hashes": sorted(profile_hashes),
        "max_active_cohorts": max_active_cohorts,
        "attempt_receipts_sha256": canonical_sha256(sorted(receipt_hashes)),
        "batch_identities_sha256": canonical_sha256(sorted(batch_identity_hashes)),
        "optimization_backlog": optimization_backlog,
        "targets": target_rows,
        "attempts": attempt_rows,
        "checks": checks,
        "passed": all(checks.values()),
    }
    contract["contract_sha256"] = canonical_sha256(contract)
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, default=DEFAULT_CAMPAIGN_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    contract = build_contract(args.campaign_root.resolve())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    contract_path = output_dir / "contract.json"
    write_json(contract_path, contract)
    manifest = {
        "schema": "all_spec_phase8_live_calibration_contract_manifest_v2",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_file_sha256": sha256_file(contract_path),
        "contract_identity_sha256": contract["contract_sha256"],
        "passed": contract["passed"],
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if contract["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
