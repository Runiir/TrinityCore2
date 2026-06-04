from __future__ import annotations

from typing import Any


WINDOWS = (2, 4, 6, 8)


def future_labels(state: dict[str, Any]) -> dict[str, Any]:
    damage = float(state.get("expected_damage", 0.12) or 0.0)
    tank_hp = float(state.get("tank_hp_pct", 1.0) or 0.0)
    party_hp = float(state.get("lowest_party_hp_pct", 1.0) or 0.0)
    mechanic = str(state.get("mechanic_family", "none"))
    labels: dict[str, Any] = {}
    for seconds in WINDOWS:
        labels[f"party_damage_next_{seconds}s"] = round(min(1.0, damage * seconds / 2.0), 6)
        labels[f"self_damage_next_{seconds}s"] = round(min(1.0, damage * seconds / 3.0), 6)
    labels.update({
        "death_risk_next_6s": round(max(0.0, 0.55 - min(tank_hp, party_hp)), 6),
        "threat_change_risk": 0.35 if mechanic in {"add_spawn", "target_switch"} else 0.05,
        "major_aoe_risk": 0.8 if mechanic == "group_aoe" else 0.05,
        "tank_burst_risk": 0.85 if mechanic == "tank_buster" else 0.05,
        "movement_risk": 0.7 if mechanic in {"ground_hazard", "frontal_cone"} else 0.05,
        "interrupt_required_risk": 0.9 if mechanic == "interrupt" else 0.05,
        "target_switch_required_risk": 0.9 if mechanic == "target_switch" else 0.05,
    })
    return labels
