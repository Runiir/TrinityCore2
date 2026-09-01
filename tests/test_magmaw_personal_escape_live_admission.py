from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "experiments" / "configs"


def _load(name: str) -> dict:
    return json.loads((CONFIGS / name).read_text(encoding="utf-8"))


def test_reviewed_personal_escape_admits_one_bounded_live_diagnostic() -> None:
    handoff_name = (
        "cata_raid_magmaw_personal_escape_episode_rearm_review_"
        "handoff_20260902.json"
    )
    handoff_path = CONFIGS / handoff_name
    handoff = _load(handoff_name)
    active = _load("cata_raid_active_work_unit_v1.json")

    assert handoff["review"]["model"] == "gpt-5.6-sol"
    assert handoff["review"]["reasoning_effort"] == "high"
    assert handoff["review"]["reviewed_commit"] == (
        "38976c172c4deff27b0e0b559d3f641bd3868ce4"
    )
    assert handoff["review"]["verdict"] == "go"
    assert active["source_handoff"]["path"] == (
        f"experiments/configs/{handoff_name}"
    )
    assert active["source_handoff"]["sha256"] == hashlib.sha256(
        handoff_path.read_bytes()
    ).hexdigest()

    scope = active["program_scope"]
    assert active["classification"] == "live_recurrence_quarantined"
    assert scope["configure_admitted"] is True
    assert scope["worldserver_build_admitted"] is True
    assert scope["worldserver_start_admitted"] is True
    assert scope["live_diagnostic_admitted"] is True
    assert scope["authserver_start_admitted"] is False
    assert scope["retry_admitted"] is False
    assert scope["fixture_expansion_replay_admitted"] is True
    assert scope["gameplay_canary_admitted"] is False
    assert scope["acceptance_admitted"] is False
    assert scope["dvc_publication_required_after_terminal"] is True

    assert active["build"] == {
        "policy": (
            "experiments/configs/"
            "cata_raid_build_resource_policy_fast8_v4.json"
        ),
        "compiler_jobs": 8,
        "linker_jobs": 1,
        "configure_receipt": "external_run_root/configure_receipt.json",
        "worldserver_build_receipt": (
            "external_run_root/worldserver_build_receipt.json"
        ),
    }

    clock = active["validation_clock"]
    assert clock == {
        "fixed_success_timer_seconds": None,
        "policy": "completion_watchdog",
        "worldserver_starts": 1,
        "authserver_starts": 0,
        "retries": 0,
    }
    observation = active["live_diagnostic"]["required_observation"]
    for signal in (
        "episode falling and rising edges",
        "task and candidate generations",
        "same-floor progress",
        "DPS/HPS",
    ):
        assert signal in observation


def test_live_diagnostic_keeps_native_terrain_ownership_explicit() -> None:
    active = _load("cata_raid_active_work_unit_v1.json")
    acceptance = "\n".join(active["acceptance"])

    assert "native executor follows terrain" in acceptance
    for forbidden in (
        "Z",
        "coordinate",
        "floor",
        "MMAP",
        "tolerance",
        "planner",
        "executor",
    ):
        assert forbidden in acceptance
