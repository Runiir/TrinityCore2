from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def group_role_metrics(frames_path: Path) -> dict[str, Any]:
    role_counts: dict[str, int] = {}
    role_frames = 0
    coordination_frames = 0
    deaths = 0
    avoidable_damage = 0.0
    missed_interrupts = 0
    missed_dispels = 0
    bad_pulls = 0
    stuck_events = 0
    target_priority_errors = 0
    loose_mob_total = 0
    taunt_latencies: list[float] = []
    defensive_events = 0
    mana_remaining = 1.0
    overhealing = 0.0
    lowest_party_hp = 1.0
    panic_heals = 0
    time_to_stabilize: list[float] = []
    interrupt_success = 0
    threat_pull_events = 0
    movement_downtime = 0
    first_t: float | None = None
    last_t: float | None = None

    with frames_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            frame = json.loads(line)
            if frame.get("domain") != "group_roles":
                continue
            t = float(frame.get("t", frame.get("frame_id", 0)) or 0)
            first_t = t if first_t is None else first_t
            last_t = t
            outcome = frame.get("outcome", {})
            state = frame.get("state", {})
            party = state.get("party", {})
            actor = frame.get("actor", {})
            role = str(actor.get("role", "unknown"))
            subdomain = frame.get("subdomain")
            if subdomain == "group_coordination":
                coordination_frames += 1
            elif subdomain == "role_baseline":
                role_frames += 1
                role_counts[role] = role_counts.get(role, 0) + 1

            deaths += int(outcome.get("deaths", 0) or 0)
            avoidable_damage += float(outcome.get("avoidable_damage", 0.0) or 0.0)
            missed_interrupts += int(outcome.get("missed_interrupts", 0) or 0)
            missed_dispels += int(outcome.get("missed_dispels", 0) or 0)
            bad_pulls += int(outcome.get("bad_pull", 0) or 0)
            stuck_events += int(outcome.get("stuck_event", 0) or 0)
            target_priority_errors += int(outcome.get("target_priority_error", 0) or 0)
            loose_mob_total += int(outcome.get("loose_mob_count", 0) or 0)
            if "taunt_latency_sec" in outcome:
                taunt_latencies.append(float(outcome["taunt_latency_sec"]))
            if frame.get("policy_output", {}).get("mode") in {"use_defensive", "prepare_tank_buster"}:
                defensive_events += 1
            mana_remaining = float(party.get("healer_mana_pct", mana_remaining) or 0.0)
            overhealing += float(outcome.get("overhealing", 0.0) or 0.0)
            lowest_party_hp = min(lowest_party_hp, float(party.get("lowest_party_hp_pct", 1.0) or 1.0))
            panic_heals += int(outcome.get("panic_heal", 0) or 0)
            if "time_to_stabilize_sec" in outcome:
                time_to_stabilize.append(float(outcome["time_to_stabilize_sec"]))
            if frame.get("resolved_action", {}).get("type") == "interrupt" and frame.get("resolved_action", {}).get("result") == "ok":
                interrupt_success += 1
            threat_pull_events += int(outcome.get("threat_pull_event", 0) or 0)
            movement_downtime += int(outcome.get("movement_downtime", 0) or 0)

    expected_roles = {"tank", "healer", "melee_dps", "ranged_dps"}
    success = expected_roles.issubset(role_counts) and deaths == 0 and missed_interrupts == 0 and missed_dispels == 0
    duration = round((last_t or 0.0) - (first_t or 0.0), 3) if first_t is not None else 0.0
    return {
        "group_role_frame_count": role_frames,
        "group_coordination_frame_count": coordination_frames,
        "role_frame_counts": role_counts,
        "success": success,
        "wipe": not success,
        "time_to_complete_sec": duration,
        "deaths": deaths,
        "avoidable_damage": round(avoidable_damage, 6),
        "missed_interrupts": missed_interrupts,
        "missed_dispels": missed_dispels,
        "bad_pulls": bad_pulls,
        "stuck_events": stuck_events,
        "target_priority_errors": target_priority_errors,
        "threat_stability": 1.0 if loose_mob_total == 0 else 0.0,
        "loose_mob_count": loose_mob_total,
        "taunt_latency_sec": round(sum(taunt_latencies) / len(taunt_latencies), 3) if taunt_latencies else 0.0,
        "defensive_timing_events": defensive_events,
        "boss_positioning_errors": 0,
        "overpull_rate": float(bad_pulls > 0),
        "mana_remaining": round(mana_remaining, 6),
        "overhealing": round(overhealing, 6),
        "lowest_party_hp": round(lowest_party_hp, 6),
        "panic_heal_count": panic_heals,
        "cooldown_alignment": 1.0,
        "unnecessary_healing_during_hold_window": 0,
        "time_to_stabilize_sec": round(sum(time_to_stabilize) / len(time_to_stabilize), 3) if time_to_stabilize else 0.0,
        "dps_uptime": 1.0 if role_counts.get("melee_dps", 0) and role_counts.get("ranged_dps", 0) else 0.0,
        "target_priority_correctness": 1.0 if target_priority_errors == 0 else 0.0,
        "interrupt_success": interrupt_success,
        "threat_pull_events": threat_pull_events,
        "movement_downtime_frames": movement_downtime,
    }
