from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def raid_metrics(frames_path: Path) -> dict[str, Any]:
    frame_count = 0
    module_counts: dict[str, int] = {}
    survival_events = 0
    survived_events = 0
    cooldown_quality: list[float] = []
    tank_swap_timings: list[float] = []
    interrupt_attempts = 0
    interrupt_successes = 0
    soak_events = 0
    soak_successes = 0
    phase_events = 0
    phase_correct = 0
    dps_checks: list[float] = []
    healer_mana_values: list[float] = []
    avoidable_damage = 0.0
    wipe_reasons: dict[str, int] = {}

    with frames_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            frame = json.loads(line)
            if frame.get("domain") != "raid":
                continue
            frame_count += 1
            subdomain = str(frame.get("subdomain", "unknown"))
            module_counts[subdomain] = module_counts.get(subdomain, 0) + 1
            outcome = frame.get("outcome", {})
            raid_state = frame.get("state", {}).get("raid_state", {})
            assignment = frame.get("state", {}).get("assignment", {})

            if "raid_survived_mechanic" in outcome:
                survival_events += 1
                survived_events += int(bool(outcome["raid_survived_mechanic"]))
            if "cooldown_overlap_quality" in outcome:
                cooldown_quality.append(float(outcome["cooldown_overlap_quality"]))
            if "tank_swap_timing_sec" in outcome:
                tank_swap_timings.append(float(outcome["tank_swap_timing_sec"]))
            if assignment.get("type") == "interrupt":
                interrupt_attempts += 1
                interrupt_successes += int(bool(outcome.get("assigned_interrupt_success", False)))
            if assignment.get("type") == "soak":
                soak_events += 1
                soak_successes += int(bool(outcome.get("soak_success", False)))
            if "phase_transition_correct" in outcome:
                phase_events += 1
                phase_correct += int(bool(outcome["phase_transition_correct"]))
            if "dps_check_quality" in outcome:
                dps_checks.append(float(outcome["dps_check_quality"]))
            if "healer_mana_distribution" in outcome:
                healer_mana_values.append(float(outcome["healer_mana_distribution"]))
            elif "healer_mana_distribution" in raid_state:
                healer_mana_values.append(float(raid_state["healer_mana_distribution"]))
            avoidable_damage += float(outcome.get("avoidable_raid_damage", 0.0) or 0.0)
            wipe_reason = outcome.get("wipe_reason")
            if wipe_reason:
                wipe_reasons[str(wipe_reason)] = wipe_reasons.get(str(wipe_reason), 0) + 1

    return {
        "raid_frame_count": frame_count,
        "raid_module_counts": module_counts,
        "mechanic_survival": survived_events / survival_events if survival_events else 0.0,
        "cooldown_overlap_quality": round(sum(cooldown_quality) / len(cooldown_quality), 6) if cooldown_quality else 0.0,
        "tank_swap_timing": round(sum(tank_swap_timings) / len(tank_swap_timings), 6) if tank_swap_timings else 0.0,
        "assigned_interrupt_success": interrupt_successes / interrupt_attempts if interrupt_attempts else 0.0,
        "soak_success": soak_successes / soak_events if soak_events else 0.0,
        "phase_transition_correctness": phase_correct / phase_events if phase_events else 0.0,
        "dps_check_quality": round(sum(dps_checks) / len(dps_checks), 6) if dps_checks else 0.0,
        "healer_mana_distribution": round(sum(healer_mana_values) / len(healer_mana_values), 6) if healer_mana_values else 0.0,
        "avoidable_raid_damage": round(avoidable_damage, 6),
        "wipe_reason_classification": wipe_reasons or {"none": frame_count},
    }

