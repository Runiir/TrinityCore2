from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the master checklist for parallel bot autonomy validation lanes.")
    parser.add_argument("--output", type=Path, default=Path(".codex/plans/auto_bots/master_checklist.json"))
    parser.add_argument("--deliverable", action="append", default=[])
    args = parser.parse_args()

    checklist = build_checklist(args.deliverable or None)
    write_json(args.output, checklist)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
