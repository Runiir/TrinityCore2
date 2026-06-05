from __future__ import annotations

from typing import Any

from .tasks import FAILURE_HANDLERS, AutonomousTask


def autonomous_frame(
    *,
    actor: dict[str, Any],
    task: AutonomousTask | None,
    state: dict[str, Any],
    policy_output: dict[str, Any],
    resolved_action: dict[str, Any],
    outcome: dict[str, Any],
    progress: dict[str, Any],
) -> dict[str, Any]:
    return {
        "domain": "autonomous_loop",
        "subdomain": "task_selection",
        "trigger": "autonomous_loop_tick",
        "actor": actor,
        "task": task.as_frame_value() if task else {"type": "idle"},
        "state": {
            **state,
            "long_term_progress": progress,
            "failure_handlers": FAILURE_HANDLERS,
        },
        "valid_actions": {
            "task_types": [
                "level_character",
                "complete_quest_chain",
                "farm_material",
                "level_profession",
                "run_dungeon",
                "practice_role_scenario",
                "farm_gear",
                "run_raid_module",
                "repair_and_restock",
            ],
            "failure_handlers": FAILURE_HANDLERS,
        },
        "policy_output": policy_output,
        "resolved_action": resolved_action,
        "outcome": outcome,
    }

