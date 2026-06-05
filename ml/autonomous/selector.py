from __future__ import annotations

from typing import Any

from .tasks import AutonomousTask


def observe_state(config: dict[str, Any], adapter: Any, completed: set[str], failed: dict[str, str]) -> dict[str, Any]:
    profession_goals = config.get("autonomous", {}).get("profession_goals", [])
    dungeon_experiments = [
        task.task_id
        for task in _configured_tasks(config)
        if task.task_type in {"run_dungeon", "practice_role_scenario"}
    ]
    return {
        "level": int(getattr(adapter, "level", config.get("level", 85))),
        "gold": int(getattr(adapter, "gold", 0)),
        "bag_free_slots": int(getattr(adapter, "bag_free_slots", 0)),
        "durability_pct": float(getattr(adapter, "durability_pct", config.get("autonomous", {}).get("durability_pct", 1.0))),
        "active_quests": [task.config.get("quest_id") for task in _configured_tasks(config) if task.task_type == "complete_quest_chain"],
        "profession_goals": profession_goals,
        "available_dungeon_experiments": dungeon_experiments,
        "completed_tasks": sorted(completed),
        "failed_tasks": dict(sorted(failed.items())),
    }


def select_task(
    tasks: list[AutonomousTask],
    state: dict[str, Any],
    completed: set[str],
    failed: dict[str, str],
    *,
    min_bag_slots: int,
    min_durability_pct: float,
) -> tuple[AutonomousTask | None, dict[str, Any]]:
    incomplete = [task for task in tasks if task.task_id not in completed and task.task_id not in failed]
    if not incomplete:
        return None, {"mode": "idle", "intent": "all_tasks_complete", "selected_task": None}

    needs_repair = float(state.get("durability_pct", 1.0) or 0.0) < min_durability_pct
    needs_bags = int(state.get("bag_free_slots", 0) or 0) < min_bag_slots
    if needs_repair or needs_bags:
        preflight = next((task for task in incomplete if task.task_type == "repair_and_restock"), None)
        if preflight:
            reason = "gear_broken" if needs_repair else "bag_full"
            return preflight, {"mode": "prepare_then_run_task", "intent": f"{reason}_preflight", "selected_task": preflight.task_id}

    selected = incomplete[0]
    return selected, {"mode": "run_task", "intent": selected.task_type, "selected_task": selected.task_id}


def _configured_tasks(config: dict[str, Any]) -> list[AutonomousTask]:
    try:
        from .tasks import load_tasks

        return load_tasks(config)
    except ValueError:
        return []

