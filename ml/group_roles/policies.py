from __future__ import annotations

from typing import Any


TANK_MODES = [
    "pull_setup",
    "pull_now",
    "hold_threat",
    "reposition",
    "kite",
    "prepare_tank_buster",
    "use_defensive",
    "group_mobs",
    "interrupt_or_stun",
    "recover_aggro",
    "wait_for_healer_mana",
]

HEALER_MODES = [
    "conserve",
    "prepare_tank_burst",
    "prepare_group_aoe",
    "hold_until_damage",
    "precast",
    "stabilize",
    "recover_after_damage",
    "emergency",
    "movement_healing",
    "mana_recovery",
    "cooldown_window",
    "dispel_priority",
]

MELEE_DPS_MODES = [
    "single_target",
    "cleave",
    "aoe",
    "burst_window",
    "interrupt_duty",
    "stun_duty",
    "target_switch",
    "avoid_mechanic",
    "threat_drop",
    "defensive",
]

RANGED_DPS_MODES = [
    "single_target",
    "aoe",
    "burst_window",
    "interrupt_duty",
    "cc_duty",
    "target_switch",
    "spread",
    "stack",
    "movement_casting",
    "defensive",
    "threat_drop",
]


def policy_for_role(role: str, state: dict[str, Any]) -> dict[str, Any]:
    tick = int(state.get("tick", 0))
    mob_count = int(state.get("mob_count", 1))
    tank_hp = float(state.get("tank_hp_pct", 1.0))
    party_low_hp = float(state.get("lowest_party_hp_pct", 1.0))
    healer_mana = float(state.get("healer_mana_pct", 1.0))
    mechanic = str(state.get("mechanic_family", "none"))

    if role == "tank":
        if healer_mana < 0.25:
            return _decision("wait_for_healer_mana", "wait_for_healer_mana", "wait", TANK_MODES)
        if mechanic == "tank_buster":
            return _decision("prepare_tank_buster", "use_defensive", "defensive", TANK_MODES)
        if tick == 0:
            return _decision("pull_setup", "pull_setup", "wait", TANK_MODES)
        if tick == 1:
            return _decision("pull_now", "pull_now", "pull", TANK_MODES)
        if mob_count > 2:
            return _decision("group_mobs", "hold_threat", "taunt", TANK_MODES)
        if tank_hp < 0.35:
            return _decision("use_defensive", "use_defensive", "defensive", TANK_MODES)
        return _decision("hold_threat", "hold_threat", "damage", TANK_MODES)

    if role == "healer":
        if mechanic == "dispel":
            return _decision("dispel_priority", "dispel_priority", "dispel", HEALER_MODES)
        if mechanic == "group_aoe":
            return _decision("prepare_group_aoe", "prepare_group_aoe", "group_cooldown", HEALER_MODES)
        if tank_hp < 0.45:
            return _decision("emergency", "stabilize", "heal", HEALER_MODES)
        if party_low_hp < 0.7:
            return _decision("recover_after_damage", "recover_after_damage", "heal", HEALER_MODES)
        if healer_mana < 0.35:
            return _decision("mana_recovery", "mana_recovery", "wait", HEALER_MODES)
        return _decision("conserve", "hold_until_damage", "heal", HEALER_MODES)

    if role == "melee_dps":
        if mechanic == "interrupt":
            return _decision("interrupt_duty", "interrupt_duty", "interrupt", MELEE_DPS_MODES)
        if mechanic == "stun":
            return _decision("stun_duty", "stun_duty", "stun", MELEE_DPS_MODES)
        if mechanic in {"ground_hazard", "frontal_cone"}:
            return _decision("avoid_mechanic", "avoid_mechanic", "reposition", MELEE_DPS_MODES)
        if mob_count > 1:
            return _decision("cleave", "cleave", "damage", MELEE_DPS_MODES)
        return _decision("single_target", "single_target", "damage", MELEE_DPS_MODES)

    if role == "ranged_dps":
        if mechanic == "cc_required":
            return _decision("cc_duty", "cc_duty", "cc", RANGED_DPS_MODES)
        if mechanic == "spread":
            return _decision("spread", "spread", "spread", RANGED_DPS_MODES)
        if mechanic == "stack":
            return _decision("stack", "stack", "stack", RANGED_DPS_MODES)
        if mob_count > 2:
            return _decision("aoe", "aoe", "damage", RANGED_DPS_MODES)
        return _decision("single_target", "single_target", "damage", RANGED_DPS_MODES)

    return _decision("unknown", "unknown", "noop", ["unknown"])


def _decision(mode: str, intent: str, action_type: str, valid_modes: list[str]) -> dict[str, Any]:
    return {
        "mode": mode,
        "intent": intent,
        "action_type": action_type,
        "valid_modes": valid_modes,
    }

