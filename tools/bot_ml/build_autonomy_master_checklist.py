from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import stable_hash, write_json
except ImportError:
    from common import stable_hash, write_json


DEFAULT_DELIVERABLES = [
    "movement_smoke",
    "kill_quest",
    "collect_quest",
    "quest_hub_batching",
    "trainer_visit",
    "vendor_repair",
    "profession_recipe_acquisition",
    "material_farming",
    "smart_loot",
    "normal_dungeon_trash",
    "dungeon_boss",
    "full_stonecore_clear",
    "raid_trash",
    "raid_boss",
    "full_blackwing_descent_clear",
]

VALID_STATUSES = {"pending", "running", "review", "accepted", "needs_followup"}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def stage_rows(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("stages") or []:
        if isinstance(row, dict) and row.get("stage"):
            rows[str(row["stage"])] = row
    return rows


def joined_missing(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    missing = [str(value) for value in (row.get("missing") or []) if value]
    return ",".join(missing)


def update_row(row: dict[str, Any], *, status: str, evidence_artifact: str, lane: str = "", failure_label: str = "", followup_lane: str = "") -> None:
    row["status"] = status
    row["evidence_artifact"] = evidence_artifact
    if lane:
        row["lane"] = lane
    if failure_label:
        row["failure_label"] = failure_label
    else:
        row["failure_label"] = ""
    if followup_lane:
        row["followup_lane"] = followup_lane


def report_lane(path: Path) -> str:
    parts = path.parts
    for marker in ("artifacts", "dataset"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1]
    return path.parent.name


def apply_stage_evidence(checklist: dict[str, Any], reports: list[Path]) -> None:
    rows = {row["deliverable"]: row for row in checklist["deliverables"]}
    accepted = set()
    fallback_missing: dict[str, tuple[Path, str]] = {}
    for path in reports:
        report = load_json(path)
        if not report:
            continue
        failure_labels = [str(value) for value in (report.get("failure_labels") or []) if value]
        failure_reason = str(report.get("failure_reason") or "")
        report_failed = bool(failure_labels or failure_reason)
        for deliverable, stage in stage_rows(report).items():
            if deliverable not in rows or deliverable in accepted:
                continue
            missing = joined_missing(stage)
            if bool(stage.get("passed")) and not report_failed:
                update_row(
                    rows[deliverable],
                    status="accepted",
                    evidence_artifact=str(path),
                    lane=report_lane(path),
                )
                accepted.add(deliverable)
            elif missing and deliverable not in fallback_missing:
                fallback_missing[deliverable] = (path, missing)

    for deliverable, (path, missing) in fallback_missing.items():
        row = rows.get(deliverable)
        if row and row.get("status") == "pending":
            update_row(
                row,
                status="needs_followup",
                evidence_artifact=str(path),
                lane=report_lane(path),
                failure_label=missing,
            )


def apply_scenario_status(checklist: dict[str, Any], status_report: dict[str, Any], scenario_report_root: Path) -> None:
    rows = {row["deliverable"]: row for row in checklist["deliverables"]}
    for scenario in status_report.get("scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        scenario_id = str(scenario.get("scenario_id") or "")
        scenario_report = load_json(scenario_report_root / f"{scenario_id}.json")
        if not scenario_report:
            continue
        is_raid = "blackwing" in scenario_id or "10" in str(scenario_report.get("difficulty") or "")
        trash_key = "raid_trash" if is_raid else "normal_dungeon_trash"
        boss_key = "raid_boss" if is_raid else "dungeon_boss"
        clear_key = "full_blackwing_descent_clear" if is_raid else "full_stonecore_clear"
        artifact = str(scenario_report_root / f"{scenario_id}.json")
        lane = scenario_id
        blockers = [str(value) for value in (scenario.get("blockers") or scenario_report.get("clear_complete_blockers") or []) if value]
        failure_label = ",".join(blockers)

        if bool(scenario_report.get("trash_cleared")) or int(scenario_report.get("trash_pulls") or 0) > 0:
            row = rows.get(trash_key)
            if row and row.get("status") != "accepted":
                update_row(row, status="review", evidence_artifact=artifact, lane=lane, failure_label=failure_label)
        boss_kills = int(scenario_report.get("raid_boss_kills" if is_raid else "boss_kills") or 0)
        if boss_kills > 0:
            row = rows.get(boss_key)
            if row and row.get("status") != "accepted":
                update_row(row, status="review", evidence_artifact=artifact, lane=lane, failure_label=failure_label)

        row = rows.get(clear_key)
        if row and row.get("status") != "accepted":
            if bool(scenario.get("full_clear_ready")):
                update_row(row, status="accepted", evidence_artifact=artifact, lane=lane)
            else:
                clear_blockers = [str(value) for value in (scenario_report.get("clear_complete_blockers") or blockers) if value]
                update_row(
                    row,
                    status="needs_followup",
                    evidence_artifact=artifact,
                    lane=lane,
                    failure_label=",".join(clear_blockers),
                    followup_lane=f"{scenario_id}_uninterrupted_full_clear",
                )


def build_checklist(deliverables: list[str] | None = None) -> dict[str, Any]:
    rows = [
        {
            "deliverable": name,
            "status": "pending",
            "lane": "",
            "evidence_artifact": "",
            "reviewer": "",
            "followup_lane": "",
            "failure_label": "",
        }
        for name in (deliverables or DEFAULT_DELIVERABLES)
    ]
    return {
        "schema": "bot_autonomy_master_checklist_v1",
        "statuses": sorted(VALID_STATUSES),
        "all_passed": False,
        "deliverables": rows,
        "checklist_hash": stable_hash(rows),
    }


def refresh_checklist_from_evidence(
    *,
    deliverables: list[str] | None = None,
    evidence_reports: list[Path] | None = None,
    validation_status: Path | None = None,
    scenario_report_root: Path = Path("dataset/live_validation_scenario_reports_built"),
) -> dict[str, Any]:
    checklist = build_checklist(deliverables)
    apply_stage_evidence(checklist, evidence_reports or [])
    if validation_status:
        apply_scenario_status(checklist, load_json(validation_status), scenario_report_root)
    rows = checklist["deliverables"]
    checklist["all_passed"] = all(row["status"] == "accepted" for row in rows)
    checklist["checklist_hash"] = stable_hash(rows)
    return checklist


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the master checklist for parallel bot autonomy validation lanes.")
    parser.add_argument("--output", type=Path, default=Path(".codex/plans/auto_bots/master_checklist.json"))
    parser.add_argument("--deliverable", action="append", default=[])
    parser.add_argument("--evidence-report", type=Path, action="append", default=[], help="Live validation report whose stages can satisfy checklist deliverables.")
    parser.add_argument("--validation-status", type=Path, help="Validation run status manifest used to attach dungeon/raid segment evidence.")
    parser.add_argument("--scenario-report-root", type=Path, default=Path("dataset/live_validation_scenario_reports_built"))
    args = parser.parse_args()

    checklist = refresh_checklist_from_evidence(
        deliverables=args.deliverable or None,
        evidence_reports=args.evidence_report,
        validation_status=args.validation_status,
        scenario_report_root=args.scenario_report_root,
    )
    write_json(args.output, checklist)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
