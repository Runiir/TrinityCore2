"""Offline audit for immutable normalized raid evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.raid_program.capture_evidence_demux import evidence_demux_report
from tools.raid_program.capture_runtime_acceptance import terminal_runtime_failure_reason
from tools.raid_program.recurrence_checkpoint_seals import (
    MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
    MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
    MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
)


def _expected_fixture_identity(report: dict[str, Any]) -> dict[str, Any] | None:
    recurrence = report.get("recurrence_admission")
    identity = report.get("identity")
    build = report.get("build_provenance")
    assets = report.get("runtime_profile_assets")
    controller = report.get("controller_route_hold")
    if not all(isinstance(value, dict) for value in (
        recurrence, identity, build, assets, controller,
    )):
        return None
    launch = controller.get("launch_identity")
    bindings = recurrence.get("bindings")
    route_binding = bindings.get("route_manifest") if isinstance(bindings, dict) else None
    overlay = recurrence.get("runtime_profile_overlay")
    if not all(isinstance(value, dict) for value in (launch, route_binding, overlay)):
        return None
    source = recurrence.get("source_commit")
    route = route_binding.get("sha256")
    profile = report.get("runtime_profile")
    scenario = report.get("scenario_id")
    seal = recurrence.get("checkpoint_seal_sha256")
    if (
        recurrence.get("valid") is not True
        or identity.get("clean") is not True
        or identity.get("dirty") is not False
        or build.get("valid") is not True
        or assets.get("passed") is not True
        or controller.get("gate_passed") is not True
        or source != identity.get("head")
        or source != build.get("commit")
        or source != launch.get("source_commit")
        or route != overlay.get("runtime_route_manifest_sha256")
        or route != launch.get("route_manifest_sha256")
        or profile != recurrence.get("expected_runtime_profile_id")
        or profile != assets.get("profile_name")
        or profile != launch.get("runtime_profile")
        or scenario != assets.get("scenario_id")
        or scenario != launch.get("scenario_id")
        or seal != launch.get("seal_sha256")
        or launch.get("actor_guid") != MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID
        or recurrence.get("checkpoint_fixture_id") != launch.get("fixture_id")
    ):
        return None
    return {
        "actor_guid": MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
        "fixture_id": recurrence.get("checkpoint_fixture_id"),
        "case_id": recurrence.get("checkpoint_case_id"),
        "runtime_profile": profile,
        "scenario_id": scenario,
        "route_manifest_sha256": route,
        "seal_sha256": seal,
        "source_commit": source,
    }


def offline_demux_audit(
    raw_path: Path, report_path: Path, *, expected_raw_sha256: str,
    expected_report_sha256: str, expected_actor_guid: int,
    expected_source_commit: str, expected_route_sha256: str,
    expected_seal_sha256: str, expected_profile: str,
) -> dict[str, Any]:
    raw_bytes = raw_path.read_bytes()
    report_bytes = report_path.read_bytes()
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    if raw_sha256 != expected_raw_sha256 or report_sha256 != expected_report_sha256:
        raise ValueError("offline_demux_input_sha256_mismatch")
    rows = [json.loads(line) for line in raw_bytes.splitlines() if line.strip()]
    capture_report = json.loads(report_bytes)
    expected_identity = {
        "actor_guid": expected_actor_guid,
        "fixture_id": MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
        "case_id": MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
        "runtime_profile": expected_profile,
        "scenario_id": expected_profile,
        "route_manifest_sha256": expected_route_sha256,
        "seal_sha256": expected_seal_sha256,
        "source_commit": expected_source_commit,
    }
    if (
        expected_actor_guid != MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID
        or _expected_fixture_identity(capture_report) != expected_identity
    ):
        raise ValueError("offline_demux_expected_identity_mismatch")
    audit = evidence_demux_report(
        rows,
        profile_name=str(capture_report.get("runtime_profile", "")),
        controller_terminal=None,
        terminal_failure_validator=terminal_runtime_failure_reason,
        fixture_terminal=capture_report.get("fixture_terminal"),
        fixture_expected_identity=expected_identity,
    )
    return {
        "schema": "cata_raid_offline_evidence_demux_audit_v1",
        "raw_normalized_sha256": raw_sha256,
        "capture_report_sha256": report_sha256,
        "demux": audit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit retained raid evidence demultiplexing")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-raw-sha256", required=True)
    parser.add_argument("--expected-report-sha256", required=True)
    parser.add_argument("--expected-actor-guid", type=int, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-route-sha256", required=True)
    parser.add_argument("--expected-seal-sha256", required=True)
    parser.add_argument("--expected-profile", required=True)
    args = parser.parse_args()
    try:
        result = offline_demux_audit(
            args.raw, args.report,
            expected_raw_sha256=args.expected_raw_sha256,
            expected_report_sha256=args.expected_report_sha256,
            expected_actor_guid=args.expected_actor_guid,
            expected_source_commit=args.expected_source_commit,
            expected_route_sha256=args.expected_route_sha256,
            expected_seal_sha256=args.expected_seal_sha256,
            expected_profile=args.expected_profile,
        )
    except ValueError as error:
        print(json.dumps({"gate_passed": False, "reason": str(error)}, sort_keys=True))
        return 1
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if result["demux"]["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
