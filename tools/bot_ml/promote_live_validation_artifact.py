from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

try:
    from .common import stable_hash, write_json
    from .live_validation_session import verify_report_acceptance
    from .run_phase9_serial_canaries import verify_operator_state
except ImportError:
    from common import stable_hash, write_json
    from live_validation_session import verify_report_acceptance
    from run_phase9_serial_canaries import verify_operator_state


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def promotion_manifest(
    source_report: Path,
    canonical_report: Path,
    report: dict[str, Any],
    campaign_gate_path: Path | None = None,
) -> dict[str, Any]:
    verification = verify_report_acceptance(report)
    accepted = bool(verification["accepted"])
    rejections = list((verification.get("recomputed") or {}).get("rejections") or [])
    if verification.get("discrepancies"):
        rejections.append("stored_summary_discrepancy")
    if not accepted and not rejections:
        rejections.append("independent_acceptance_failed")
    context = report.get("validation_context") or {}
    route_manifest = report.get("validation_route_manifest") or {}
    requires_joined_gate = bool(
        context.get("scenario_id") == "stonecore_5h"
        or route_manifest.get("scenario_id") == "stonecore_5h"
    )
    campaign_verification: dict[str, Any] = {}
    if campaign_gate_path is not None:
        campaign_verification = verify_operator_state(campaign_gate_path)
    if requires_joined_gate:
        accepted = False
        rejections.append(
            "individual_stonecore_5h_report_not_promotable_use_joined_campaign_artifact"
        )
    return {
        "schema": "bot_live_validation_artifact_promotion_v1",
        "accepted": accepted,
        "source_report": str(source_report),
        "canonical_report": str(canonical_report),
        "completion_reason": report.get("completion_reason"),
        "failure_labels": report.get("failure_labels") or [],
        "final_evidence_rejections": list(dict.fromkeys(rejections)),
        "acceptance_verification": verification,
        "campaign_gate_required": requires_joined_gate,
        "campaign_gate_verification": campaign_verification,
        "canonical_campaign_artifact": "joined_campaign_promotion.json"
        if requires_joined_gate
        else "",
        "source_report_hash": stable_hash(report),
        "db_clone": (report.get("lane_manifest") or {}).get("databases") or (report.get("preparation") or {}).get("db_clone") or {},
    }


def promote(
    source_report: Path,
    canonical_report: Path,
    manifest_path: Path,
    campaign_gate_path: Path | None = None,
) -> dict[str, Any]:
    report = load_report(source_report)
    manifest = promotion_manifest(
        source_report,
        canonical_report,
        report,
        campaign_gate_path=campaign_gate_path,
    )
    if not manifest["accepted"]:
        write_json(manifest_path, manifest)
        raise SystemExit(f"Refusing to promote unacceptable evidence: {', '.join(manifest['final_evidence_rejections'])}")
    canonical_report.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_report, canonical_report)
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote accepted lane-local live validation evidence into a canonical DVC artifact path.")
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--canonical-report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/live_validation_promotion/manifest.json"))
    parser.add_argument("--campaign-gate", type=Path)
    args = parser.parse_args()

    manifest = promote(
        args.source_report,
        args.canonical_report,
        args.manifest,
        campaign_gate_path=args.campaign_gate,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
