from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TASK_TYPES = {
    "level_character",
    "complete_quest_chain",
    "farm_material",
    "level_profession",
    "run_dungeon",
    "practice_role_scenario",
    "farm_gear",
    "run_raid_module",
    "repair_and_restock",
}

FAILURE_HANDLERS = {
    "death": "corpse_run_or_resurrect_if_supported",
    "stuck": "unstuck_then_repath",
    "bag_full": "vendor_trash_then_bank_if_supported",
    "gear_broken": "repair_at_vendor",
    "missing_reagent": "restock_vendor_reagent_or_block",
    "cannot_reach_target": "unstuck_then_mark_bad_route",
    "quest_objective_bugged": "mark_quest_blocked_and_select_next_task",
    "dungeon_wipe": "recover_party_or_end_dungeon_task",
    "bot_disconnect": "unload_cleanup_and_respawn_if_supported",
    "party_disband": "rebuild_party_or_select_solo_task",
}


@dataclass
class AutonomousTask:
    task_id: str
    task_type: str
    priority: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(cls, value: dict[str, Any]) -> "AutonomousTask":
        task_type = str(value.get("type", ""))
        if task_type not in TASK_TYPES:
            raise ValueError(f"unsupported autonomous task type: {task_type}")
        return cls(
            task_id=str(value.get("task_id") or task_type),
            task_type=task_type,
            priority=int(value.get("priority", 0) or 0),
            config=dict(value),
        )

    def as_frame_value(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "type": self.task_type,
            "priority": self.priority,
            "config": self.config,
        }


def load_tasks(config: dict[str, Any]) -> list[AutonomousTask]:
    tasks = config.get("autonomous", {}).get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("autonomous_tasks_missing")
    return sorted((AutonomousTask.from_config(task) for task in tasks), key=lambda task: (-task.priority, task.task_id))

