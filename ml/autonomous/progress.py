from __future__ import annotations

from typing import Any


class LongTermProgressStore:
    def __init__(self, *, model_version: str = "scripted_autonomous_v1") -> None:
        self.model_version = model_version
        self.character_goals: list[dict[str, Any]] = []
        self.completed_experiments: list[str] = []
        self.known_bad_routes: list[str] = []
        self.profession_targets: list[dict[str, Any]] = []
        self.quest_progress: dict[str, Any] = {}
        self.gear_upgrades: list[dict[str, Any]] = []
        self.policy_performance_summaries: dict[str, Any] = {}

    def complete(self, task_id: str, task_type: str, summary: dict[str, Any]) -> None:
        self.completed_experiments.append(task_id)
        if task_type == "complete_quest_chain":
            self.quest_progress[str(summary.get("quest_id", task_id))] = summary
        elif task_type == "level_profession":
            self.profession_targets.append(summary)
        elif task_type == "farm_gear":
            self.gear_upgrades.append(summary)
        self.policy_performance_summaries[task_id] = summary

    def mark_bad_route(self, route_id: str) -> None:
        if route_id not in self.known_bad_routes:
            self.known_bad_routes.append(route_id)

    def as_frame_value(self) -> dict[str, Any]:
        return {
            "character_goals": self.character_goals,
            "completed_experiments": self.completed_experiments,
            "known_bad_routes": self.known_bad_routes,
            "profession_targets": self.profession_targets,
            "quest_progress": self.quest_progress,
            "gear_upgrades": self.gear_upgrades,
            "model_version_used": self.model_version,
            "policy_performance_summaries": self.policy_performance_summaries,
        }

