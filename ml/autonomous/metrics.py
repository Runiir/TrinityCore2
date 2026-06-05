from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def autonomous_metrics(frames_path: Path) -> dict[str, Any]:
    frame_count = 0
    completed = 0
    failures = 0
    recovered = 0
    stuck_frames = 0
    deaths = 0
    manual_interventions = 0
    resource_waste = 0.0
    first_t: float | None = None
    last_t: float | None = None
    selected_tasks: set[str] = set()
    invoked_domains: set[str] = set()
    frames_by_domain: dict[str, int] = {}

    with frames_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            frame = json.loads(line)
            domain = str(frame.get("domain", "unknown"))
            frames_by_domain[domain] = frames_by_domain.get(domain, 0) + 1
            if domain != "autonomous_loop":
                continue
            frame_count += 1
            t = float(frame.get("t", frame_count) or 0.0)
            first_t = t if first_t is None else first_t
            last_t = t
            task = frame.get("task", {})
            outcome = frame.get("outcome", {})
            task_id = task.get("task_id")
            if task_id:
                selected_tasks.add(str(task_id))
            if outcome.get("task_completed"):
                completed += 1
            if outcome.get("blocked_reason"):
                failures += 1
            if outcome.get("recovered"):
                recovered += 1
            if outcome.get("stuck"):
                stuck_frames += 1
            if outcome.get("death"):
                deaths += 1
            manual_interventions += int(outcome.get("manual_intervention_count", 0) or 0)
            resource_waste += float(outcome.get("resource_waste", 0.0) or 0.0)
            invoked = outcome.get("invoked_domain")
            if invoked:
                invoked_domains.add(str(invoked))

    duration_sec = max((last_t or 0.0) - (first_t or 0.0), 1.0)
    hours = duration_sec / 3600.0
    return {
        "autonomous_frame_count": frame_count,
        "tasks_completed": completed,
        "tasks_completed_per_hour": round(completed / hours, 6),
        "failure_recovery_rate": recovered / failures if failures else 1.0,
        "time_lost_to_stuck_states": stuck_frames,
        "deaths_per_hour": round(deaths / hours, 6),
        "manual_intervention_count": manual_interventions,
        "resource_waste": round(resource_waste, 6),
        "progress_toward_selected_goal": completed / len(selected_tasks) if selected_tasks else 0.0,
        "dataset_frames_generated_per_domain": frames_by_domain,
        "domain_tasks_invoked": sorted(invoked_domains),
    }

