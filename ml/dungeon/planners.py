from __future__ import annotations

from typing import Any


class TankPlanner:
    def plan(self, state: dict[str, Any]) -> dict[str, Any]:
        healer_mana = float(state.get("healer_mana_pct", 1.0) or 0.0)
        mob_count = int(state.get("mob_count", 1) or 1)
        mechanic = str(state.get("mechanic_family", "none"))
        if healer_mana < 0.3:
            mode = "wait_for_healer_mana"
        elif mechanic == "tank_buster":
            mode = "defensive_timing"
        elif mob_count >= 4:
            mode = "small_pull"
        elif mechanic in {"frontal_cone", "cleave"}:
            mode = "boss_positioning"
        else:
            mode = "hold_threat"
        return {"role": "tank", "mode": mode, "intent": mode, "valid_modes": ["pull_size", "line_of_sight_pull", "boss_positioning", "frontal_avoidance", "add_pickup", "hold_threat", "defensive_timing", "kite", "wait_for_healer_mana"]}


class HealerPlanner:
    def plan(self, state: dict[str, Any]) -> dict[str, Any]:
        party_hp = float(state.get("lowest_party_hp_pct", 1.0) or 0.0)
        mechanic = str(state.get("mechanic_family", "none"))
        if party_hp < 0.45:
            mode = "emergency"
        elif mechanic in {"group_aoe", "tank_buster"}:
            mode = "prepare"
        elif state.get("recent_damage"):
            mode = "recover"
        else:
            mode = "hold"
        return {"role": "healer", "mode": mode, "intent": mode, "valid_modes": ["prepare", "hold", "precast", "recover", "conserve", "emergency", "cooldown_alignment", "hot_shield_setup", "cast_cancellation"]}


class DPSPlanner:
    def plan(self, state: dict[str, Any]) -> dict[str, Any]:
        mechanic = str(state.get("mechanic_family", "none"))
        mob_count = int(state.get("mob_count", 1) or 1)
        if mechanic == "interrupt":
            mode = "interrupt_assignment"
        elif mechanic == "target_switch":
            mode = "target_switching"
        elif mob_count >= 3:
            mode = "aoe"
        else:
            mode = "rotation_uptime"
        return {"role": "dps", "mode": mode, "intent": mode, "valid_modes": ["rotation_uptime", "interrupt_assignment", "target_switching", "burst_timing", "aoe", "single_target", "movement_min_dps_loss", "threat_drop", "defensive_use"]}


def planner_for_role(role: str):
    if role == "tank":
        return TankPlanner()
    if role == "healer":
        return HealerPlanner()
    return DPSPlanner()
