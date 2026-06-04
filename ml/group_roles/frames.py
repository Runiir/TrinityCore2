from __future__ import annotations

from typing import Any


def role_frame(
    *,
    episode_id: str,
    tick: int,
    actor: dict[str, Any],
    party_state: dict[str, Any],
    enemy_state: dict[str, Any],
    mechanic: dict[str, Any],
    coordination: dict[str, Any],
    policy_output: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    return {
        "episode_id": episode_id,
        "frame_id": tick,
        "domain": "group_roles",
        "subdomain": "role_baseline",
        "trigger": "party_combat_tick",
        "actor": actor,
        "task": {
            "type": "dungeon_trash_pull",
            "dungeon_id": party_state.get("dungeon_id"),
            "boss_id": party_state.get("boss_id"),
            "phase_id": party_state.get("phase_id", 1),
            "primary_kill_target": coordination.get("primary_kill_target"),
            "focus_target": coordination.get("focus_target"),
        },
        "state": {
            "party": party_state,
            "enemies": enemy_state,
            "mechanic": mechanic,
            "coordination": coordination,
        },
        "valid_actions": {"modes": policy_output.get("valid_modes", [])},
        "policy_output": {
            "mode": policy_output.get("mode"),
            "intent": policy_output.get("intent"),
            "reserved_action": policy_output.get("reserved_action"),
        },
        "resolved_action": {
            "type": policy_output.get("action_type", "noop"),
            "target_guid": enemy_state.get("primary_target_guid"),
            "valid": True,
            "result": "ok",
        },
        "outcome": outcome,
    }


def coordination_frame(
    *,
    episode_id: str,
    tick: int,
    coordination: dict[str, Any],
    party_state: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    return {
        "episode_id": episode_id,
        "frame_id": tick,
        "domain": "group_roles",
        "subdomain": "group_coordination",
        "trigger": "coordination_tick",
        "actor": {"guid": None, "is_bot": True, "role": "party_controller"},
        "task": {
            "type": "group_coordination",
            "dungeon_id": party_state.get("dungeon_id"),
            "boss_id": party_state.get("boss_id"),
            "phase_id": party_state.get("phase_id", 1),
        },
        "state": {
            "party": party_state,
            "coordination": coordination,
        },
        "valid_actions": {
            "reservation_types": [
                "interrupt",
                "dispel",
                "stun",
                "cc",
                "external_defensive",
                "group_cooldown",
                "primary_kill_target",
                "focus_target",
                "pull_state",
                "stack_assignment",
                "spread_assignment",
            ]
        },
        "policy_output": {"mode": "coordinate_party", "intent": "reserve_group_actions"},
        "resolved_action": {"type": "coordinate", "valid": True, "result": "ok"},
        "outcome": outcome,
    }

