from __future__ import annotations

from typing import Any


RAID_MECHANIC_FAMILIES = [
    "tank_swap",
    "raid_wide_aoe",
    "stack",
    "spread",
    "soak",
    "assigned_soak",
    "interrupt_rotation",
    "dispel_rotation",
    "healer_cooldown_assignment",
    "burn_phase",
    "add_wave",
    "boss_immunity",
    "phase_transition",
    "enrage_timer",
]


def raid_module_frame(
    *,
    episode_id: str,
    tick: int,
    subdomain: str,
    raid_state: dict[str, Any],
    assignment: dict[str, Any],
    scheduler_state: dict[str, Any],
    group_intent: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    mechanic_family = str(assignment.get("mechanic_family", subdomain))
    return {
        "episode_id": episode_id,
        "frame_id": tick,
        "domain": "raid",
        "subdomain": subdomain,
        "trigger": "raid_mechanic_event",
        "actor": {"guid": None, "is_bot": True, "role": "raid_controller"},
        "task": {
            "type": "raid_mechanic_module",
            "boss_id": raid_state.get("boss_id"),
            "phase_id": raid_state.get("phase_id", 1),
            "mechanic_event_id": assignment.get("mechanic_event_id"),
            "mechanic_family": mechanic_family,
        },
        "state": {
            "raid_state": raid_state,
            "assignment_scheduler": scheduler_state,
            "assignment": assignment,
        },
        "valid_actions": {
            "assignment_types": [
                "tank_swap",
                "interrupt",
                "healer_cooldown",
                "soak",
                "subgroup_move",
                "target_switch",
            ],
            "mechanic_families": RAID_MECHANIC_FAMILIES,
        },
        "policy_output": group_intent,
        "resolved_action": {"type": assignment.get("type"), "valid": True, "result": "ok"},
        "outcome": outcome,
    }

