from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from .common import write_json
    from .validate_world_planner import load_manifest_dir, validate_manifest_coverage
except ImportError:
    from common import write_json
    from validate_world_planner import load_manifest_dir, validate_manifest_coverage


QUEST_PROFESSION_STAGES = [
    "kill_quest",
    "collect_quest",
    "quest_hub_batching",
    "quest_chain_routing",
    "unsupported_quest_fallback",
    "cross_zone_routing",
    "trainer_visit",
    "vendor_repair",
    "class_skill_visit",
    "profession_recipe_acquisition",
    "all_profession_recipe_acquisition",
    "material_farming",
    "material_planning",
    "crafting_surface",
    "smart_loot",
]


def build_report(planner_dir: Path) -> dict[str, Any]:
    validation = validate_manifest_coverage(load_manifest_dir(planner_dir))
    gates = [gate for gate in validation["gates"] if gate["gate"] in QUEST_PROFESSION_STAGES]
    passed = sum(1 for gate in gates if gate["passed"])
    missing = sorted({item for gate in gates for item in gate.get("missing", [])})
    return {
        "schema": "bot_quest_profession_report_v1",
        "planner_dir": str(planner_dir),
        "stages": gates,
        "passed": passed,
        "failed": len(gates) - passed,
        "total": len(gates),
        "all_passed": passed == len(gates),
        "missing": missing,
        "evidence": validation["evidence"],
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a no-server staged quest/profession planner report.")
    parser.add_argument("--planner-dir", type=Path, default=Path("dataset/world_planner"))
    parser.add_argument("--report", type=Path, default=Path("dataset/quest_profession_reports/report.json"))
    parser.add_argument("--fail-on-missing", action="store_true")
    args = parser.parse_args()

    report = build_report(args.planner_dir)
    write_json(args.report, report)
    if args.fail_on_missing and not report["all_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
