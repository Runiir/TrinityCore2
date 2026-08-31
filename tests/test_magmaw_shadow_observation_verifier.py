from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.raid_program.verify_magmaw_shadow_observation import verify


SCOPE = "cohort:1:2:4:bwd.magmaw.encounter:669:42:blackwing_descent.magmaw"
ACTORS = (30007, 30008)


def _summary(actor: int, task_generation: int) -> dict:
    prefix = f"{SCOPE}:adaptive_magmaw:pillar_bait_switch:{actor}"
    destination = {"available": True, "x": -320.0, "y": -30.0, "z": 211.0}
    return {
        "scope_key": SCOPE,
        "actor_guid": actor,
        "episode_generation": 9,
        "task_generation": task_generation,
        "counts": {
            "observed": 3,
            "equivalent": 3,
            "divergent": 0,
            "ambiguous": 0,
            "shadow_only": 0,
            "legacy_only": 0,
        },
        "stable_shadow_candidate_key": f"{prefix}:{task_generation}",
        "stable_legacy_candidate_key": f"{prefix}:44",
        "shadow_key_change_count": 0,
        "legacy_key_change_count": 0,
        "shadow_destination_change_count": 0,
        "legacy_destination_change_count": 0,
        "stable_shadow_destination": copy.deepcopy(destination),
        "stable_legacy_destination": copy.deepcopy(destination),
        "first_failing_comparison": None,
    }


def _task(actor: int, task_generation: int, state: str) -> dict:
    return {
        "lifecycle_scope": SCOPE,
        "episode_generation": 9,
        "actor_guid": actor,
        "task_generation": task_generation,
        "state": state,
        "destination": {"x": -320.0, "y": -30.0, "z": 211.0},
        "initial_distance": 28.0,
        "best_distance": 0.2 if state == "succeeded" else 17.0,
        "progress_samples": 3,
    }


def _shadow(*, active: bool, succeeded: bool) -> dict:
    tasks = [] if succeeded else [_task(actor, index + 70, "running")
                                  for index, actor in enumerate(ACTORS)]
    retired_tasks = (
        [{"task": _task(actor, index + 70, "succeeded")}
         for index, actor in enumerate(ACTORS)] if succeeded else []
    )
    comparisons = []
    for index, actor in enumerate(ACTORS):
        summary = _summary(actor, index + 70)
        accumulator = {"active": summary, "retired": []}
        if succeeded:
            accumulator = {"active": None, "retired": [summary]}
        comparisons.append({
            "actor_guid": actor,
            "comparison": {"observed": False},
            "episode_accumulator": accumulator,
        })
    result = {
        "active": active,
        "source_revision": 12 if active else 0,
        "tasks": tasks,
        "retired_tasks": retired_tasks,
        "retired_task_count": len(retired_tasks),
        "intent_comparisons": comparisons,
    }
    if active:
        result.update({
            "lifecycle_scope": SCOPE,
            "episode_generation": 9,
            "fire_mage_guid": ACTORS[0],
            "hunter_guid": ACTORS[1],
            "immutable_destination": {"x": -320.0, "y": -30.0, "z": 211.0},
        })
    return result


def _receipt(actor: int, key: str) -> dict:
    return {
        "id": actor,
        "identity": {
            "bot_guid": actor,
            "map": 669,
            "diagnostic_candidate_key": key,
            "scope": {
                "attempt_id": 1,
                "wipe_generation": 2,
                "route_generation": 4,
                "map": 669,
                "instance": 42,
            },
        },
        "launches": [{"spline_launch": {"attempted": True, "succeeded": True}}],
        "progress": {
            "available": True,
            "receipt_id": actor,
            "bot_guid": actor,
            "map": 669,
            "instance": 42,
            "scope": {
                "attempt_id": 1,
                "wipe_generation": 2,
                "route_generation": 4,
            },
            "launched_spline": {"initialized": True},
            "armed_at_ms": 50,
            "samples": [
                {
                    "receipt_id": actor,
                    "observed_at_ms": 100,
                    "actor": {
                        "available": True, "alive": True, "in_world": True,
                        "map": 669, "instance": 42,
                        "x": -300.0, "y": -30.0, "z": 211.0,
                    },
                    "endpoint_progress": {
                        "horizontal_distance": 20.0, "vertical_distance": 0.0,
                        "distance": 20.0, "improved": True, "reached": False,
                    },
                },
                {
                    "receipt_id": actor,
                    "observed_at_ms": 200,
                    "actor": {
                        "available": True, "alive": True, "in_world": True,
                        "map": 669, "instance": 42,
                        "x": -319.8, "y": -30.0, "z": 211.0,
                    },
                    "endpoint_progress": {
                        "horizontal_distance": 0.2, "vertical_distance": 0.0,
                        "distance": 0.2, "improved": True, "reached": True,
                    },
                },
            ],
        },
    }


def _actor_binding(action: str, actor: int, *, entry_count: int = 0) -> dict:
    binding = {
        "state": "bound",
        "scope": "telemetry_actor",
        "canonical_identity_sha256": "identity",
        "roster_sha256": "roster",
        "correlation": {
            "capture_sequence": 0,
            "telemetry_channel": action,
            "bot_guid": actor,
            "scenario": "blackwing_descent_10n_magmaw_diagnostic",
            "cohort_id": "cohort",
            "server_epoch": 11,
            "attempt_id": 1,
            "runtime_profile_generation": 3,
            "runtime_profile_hash": "profile",
            "assignment_generation": 5,
            "route_generation": 4,
            "wipe_generation": 2,
        },
        "reasons": [],
    }
    if action == "trace":
        binding["trace_transport"] = {
            "mode": "bounded_full_snapshot",
            "cursor_before": None,
            "cursor_after": None,
            "sequence_first": None,
            "sequence_last": None,
            "entry_count": entry_count,
        }
    return binding


def _bound(action: str, payload: dict) -> dict:
    channel = {
        "botauto_status": "status",
        "botauto_diagnose": "diagnosis",
        "botauto_trace": "trace",
    }[action]
    return {
        "action": action,
        "capture_sequence": 1,
        "evidence_channel": channel,
        "identity_binding": {
            "state": "bound", "canonical_identity_sha256": "identity",
            "roster_sha256": "roster", "cohort_id": "cohort",
        },
        "normalized_schema_version": 2,
        "payload": {"action": action, **payload},
    }


def _canonical_rows() -> list[dict]:
    active = _bound("botauto_status", {
        "magmaw_transfer_lane_shadow": _shadow(active=True, succeeded=False),
    })
    terminal = _bound("botauto_status", {
        "magmaw_transfer_lane_shadow": _shadow(active=False, succeeded=True),
    })
    diagnosis = _bound("botauto_diagnose", {"bots": [
        {
            "identity": {"bot_guid": actor, "bot_name": f"bot-{actor}"},
            "identity_binding": _actor_binding("diagnosis", actor),
        }
        for actor in ACTORS
    ]})
    bots = []
    for index, actor in enumerate(ACTORS):
        key = _summary(actor, index + 70)["stable_legacy_candidate_key"]
        entry = {"movement_planner": {"launch_receipt": _receipt(actor, key)}}
        bots.append({
            "bot_guid": actor,
            "identity_binding": _actor_binding("trace", actor, entry_count=1),
            "entries": [entry],
        })
    trace = _bound("botauto_trace", {"bots": bots})
    return [active, diagnosis, trace, terminal]


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "capture.raw.jsonl"
    for sequence, row in enumerate(rows, 1):
        row["capture_sequence"] = sequence
        for bot in row.get("payload", {}).get("bots", []):
            binding = bot.get("identity_binding") if isinstance(bot, dict) else None
            if isinstance(binding, dict) and isinstance(binding.get("correlation"), dict):
                binding["correlation"]["capture_sequence"] = sequence
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _mutate_summary(rows: list[dict], actor: int, mutation) -> None:
    for row in rows:
        shadow = row.get("payload", {}).get("magmaw_transfer_lane_shadow")
        if not isinstance(shadow, dict):
            continue
        for item in shadow.get("intent_comparisons", []):
            if item.get("actor_guid") != actor:
                continue
            accumulator = item["episode_accumulator"]
            values = ([accumulator["active"]] if accumulator.get("active") else [])
            values += accumulator.get("retired", [])
            for summary in values:
                mutation(summary)


def test_canonical_retired_two_baiter_episode_passes_deterministically(tmp_path: Path) -> None:
    path = _write(tmp_path, _canonical_rows())
    first = verify([path])
    second = verify([path])
    assert first == second
    assert first["verdict"] == "pass"
    assert first["baiter_actor_guids"] == list(ACTORS)
    assert len(first["receipt_joins"]) == 2
    assert "entries" not in json.dumps(first)


def test_actual_diagnosis_actor_shape_and_channel_are_accepted(tmp_path: Path) -> None:
    rows = _canonical_rows()
    diagnosis_actor = rows[1]["payload"]["bots"][0]
    assert "bot_guid" not in diagnosis_actor
    assert diagnosis_actor["identity"]["bot_guid"] == ACTORS[0]
    assert diagnosis_actor["identity_binding"]["correlation"][
        "telemetry_channel"] == "diagnosis"
    assert verify([_write(tmp_path, rows)])["verdict"] == "pass"


def test_no_episode_is_not_exercised(tmp_path: Path) -> None:
    rows = _canonical_rows()
    for row in rows:
        if row["payload"]["action"] == "botauto_status":
            row["payload"]["magmaw_transfer_lane_shadow"] = {
                "active": False, "source_revision": 0, "tasks": [],
                "retired_tasks": [], "retired_task_count": 0,
                "intent_comparisons": [],
            }
    assert verify([_write(tmp_path, rows)])["verdict"] == "not_exercised"


def test_one_baiter_is_not_exercised(tmp_path: Path) -> None:
    rows = _canonical_rows()
    rows[0]["payload"]["magmaw_transfer_lane_shadow"]["hunter_guid"] = 0
    result = verify([_write(tmp_path, rows)])
    assert result["verdict"] == "not_exercised"
    assert result["reason"] == "incomplete_baiter_assignment"


def test_zero_eligible_comparisons_is_not_exercised(tmp_path: Path) -> None:
    rows = _canonical_rows()
    _mutate_summary(rows, ACTORS[0], lambda summary: summary["counts"].update(
        observed=0, equivalent=0))
    result = verify([_write(tmp_path, rows)])
    assert result["verdict"] == "not_exercised"
    assert result["reason"] == "zero_eligible_comparisons"


@pytest.mark.parametrize(
    ("case", "mutator", "reason"),
    [
        ("transient_divergence", lambda s: (
            s["counts"].update(observed=4, equivalent=3, divergent=1),
            s.__setitem__("first_failing_comparison", {"outcome": "divergent"}),
        ), "comparison_not_fully_equivalent"),
        ("ambiguity", lambda s: s["counts"].update(
            observed=4, equivalent=3, divergent=1, ambiguous=1),
         "comparison_not_fully_equivalent"),
        ("destination_change", lambda s: s.__setitem__(
            "legacy_destination_change_count", 1),
         "unstable_candidate_or_destination"),
    ],
)
def test_accumulated_failure_cannot_be_hidden(
    tmp_path: Path, case: str, mutator, reason: str,
) -> None:
    rows = _canonical_rows()
    _mutate_summary(rows, ACTORS[0], mutator)
    result = verify([_write(tmp_path, rows)])
    assert result["verdict"] == "fail", case
    assert result["reason"] == reason


def test_candidate_key_mismatch_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    receipt = rows[2]["payload"]["bots"][0]["entries"][0]["movement_planner"]["launch_receipt"]
    receipt["identity"]["diagnostic_candidate_key"] = "wrong"
    assert verify([_write(tmp_path, rows)])["reason"] == "missing_exact_native_receipt_progress_join"


@pytest.mark.parametrize("mismatch", ["scope", "actor"])
def test_scope_or_actor_mismatch_fails(tmp_path: Path, mismatch: str) -> None:
    rows = _canonical_rows()
    receipt = rows[2]["payload"]["bots"][0]["entries"][0]["movement_planner"]["launch_receipt"]
    if mismatch == "scope":
        receipt["identity"]["scope"]["instance"] = 43
    else:
        receipt["identity"]["bot_guid"] = 999
    assert verify([_write(tmp_path, rows)])["verdict"] == "fail"


def test_missing_receipt_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    rows[2]["payload"]["bots"][0]["entries"] = []
    assert verify([_write(tmp_path, rows)])["verdict"] == "fail"


def test_submission_without_multi_tick_progress_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    receipt = rows[2]["payload"]["bots"][0]["entries"][0]["movement_planner"]["launch_receipt"]
    receipt["progress"]["samples"] = [
        {"observed_at_ms": 100, "endpoint_progress": {"improved": False}},
    ]
    assert verify([_write(tmp_path, rows)])["verdict"] == "fail"


def test_improved_flag_without_numeric_distance_change_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    receipt = rows[2]["payload"]["bots"][0]["entries"][0][
        "movement_planner"]["launch_receipt"]
    receipt["progress"]["samples"][1]["endpoint_progress"].update(
        horizontal_distance=20.0, distance=20.0, improved=True, reached=False)
    result = verify([_write(tmp_path, rows)])
    assert result["reason"] == "missing_exact_native_receipt_progress_join"


def test_shadow_legacy_or_task_destination_mismatch_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    _mutate_summary(rows, ACTORS[0], lambda summary: summary[
        "stable_legacy_destination"].__setitem__("x", -319.0))
    assert verify([_write(tmp_path, rows)])["reason"] == "shadow_legacy_destination_mismatch"


def test_rejected_actor_binding_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    rows[2]["payload"]["bots"][0]["identity_binding"]["state"] = "rejected"
    assert verify([_write(tmp_path, rows)])["reason"] == "unbound_trace_actor"


def test_mixed_canonical_identity_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    rows[2]["identity_binding"]["canonical_identity_sha256"] = "other"
    assert verify([_write(tmp_path, rows)])["reason"] == "mixed_canonical_evidence_identity"


def test_mismatched_normalized_evidence_channel_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    rows[1]["evidence_channel"] = "diagnose"
    assert verify([_write(tmp_path, rows)])["reason"] \
        == "normalized_evidence_channel_mismatch"


def test_partial_assignments_are_not_unioned_across_status_rows(tmp_path: Path) -> None:
    rows = _canonical_rows()
    second = copy.deepcopy(rows[0])
    rows[0]["payload"]["magmaw_transfer_lane_shadow"]["hunter_guid"] = 0
    second["payload"]["magmaw_transfer_lane_shadow"]["fire_mage_guid"] = 0
    rows.insert(1, second)
    result = verify([_write(tmp_path, rows)])
    assert result["verdict"] == "not_exercised"
    assert result["reason"] == "incomplete_baiter_assignment"


def test_partial_assignment_after_complete_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    partial = copy.deepcopy(rows[0])
    partial["payload"]["magmaw_transfer_lane_shadow"]["hunter_guid"] = 0
    rows.insert(1, partial)
    assert verify([_write(tmp_path, rows)])["reason"] \
        == "incomplete_assignment_during_active_episode"


def test_ordered_baiter_swap_or_immutable_destination_change_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    changed = copy.deepcopy(rows[0])
    shadow = changed["payload"]["magmaw_transfer_lane_shadow"]
    shadow["fire_mage_guid"], shadow["hunter_guid"] = (
        shadow["hunter_guid"], shadow["fire_mage_guid"])
    rows.insert(1, changed)
    assert verify([_write(tmp_path, rows)])["reason"] == "mixed_transfer_lane_episodes"


def test_retained_failure_cannot_disappear(tmp_path: Path) -> None:
    rows = _canonical_rows()
    active_summary = rows[0]["payload"]["magmaw_transfer_lane_shadow"][
        "intent_comparisons"][0]["episode_accumulator"]["active"]
    active_summary["counts"].update(observed=4, equivalent=3, divergent=1)
    active_summary["first_failing_comparison"] = {"outcome": "divergent"}
    terminal_summary = rows[3]["payload"]["magmaw_transfer_lane_shadow"][
        "intent_comparisons"][0]["episode_accumulator"]["retired"][0]
    terminal_summary["counts"].update(observed=4, equivalent=3, divergent=1)
    result = verify([_write(tmp_path, rows)])
    assert result["reason"] == "retained_first_failure_disappeared"


def test_task_failure_or_invalid_lifecycle_scope_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    rows[3]["payload"]["magmaw_transfer_lane_shadow"][
        "retired_tasks"][0]["task"]["state"] = "failed"
    assert verify([_write(tmp_path, rows)])["reason"] == "failed_or_aborted_task_history"


def test_internal_receipt_progress_identity_mismatch_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    receipt = rows[2]["payload"]["bots"][0]["entries"][0][
        "movement_planner"]["launch_receipt"]
    receipt["progress"]["samples"][1]["receipt_id"] = 999
    assert verify([_write(tmp_path, rows)])["reason"] \
        == "native_progress_sample_receipt_mismatch"


def test_trace_actor_correlation_or_gap_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    binding = rows[2]["payload"]["bots"][0]["identity_binding"]
    binding["trace_transport"]["missing_sequence_start"] = 12
    assert verify([_write(tmp_path, rows)])["reason"] == "trace_actor_delta_gap"


def test_both_baiters_require_diagnosis_envelopes(tmp_path: Path) -> None:
    rows = _canonical_rows()
    rows[1]["payload"]["bots"] = rows[1]["payload"]["bots"][:1]
    assert verify([_write(tmp_path, rows)])["reason"] \
        == "missing_baiter_diagnosis_envelope"


def test_prior_route_telemetry_does_not_poison_exact_episode_join(tmp_path: Path) -> None:
    rows = _canonical_rows()
    prior = copy.deepcopy(rows[1])
    for bot in prior["payload"]["bots"]:
        bot["identity_binding"]["correlation"]["route_generation"] = 3
    rows.insert(1, prior)
    assert verify([_write(tmp_path, rows)])["verdict"] == "pass"


def test_multiple_inputs_require_one_monotonic_capture_sequence(tmp_path: Path) -> None:
    rows = _canonical_rows()
    first = _write(tmp_path, rows[:2])
    second = tmp_path / "second.raw.jsonl"
    second.write_text("".join(json.dumps(row) + "\n" for row in rows[2:]), encoding="utf-8")
    assert verify([first, second])["reason"] == "non_monotonic_capture_sequence"


def test_mixed_scope_fails(tmp_path: Path) -> None:
    rows = _canonical_rows()
    extra = copy.deepcopy(rows[0])
    shadow = extra["payload"]["magmaw_transfer_lane_shadow"]
    shadow["lifecycle_scope"] = SCOPE.replace(":42:", ":43:")
    rows.append(extra)
    result = verify([_write(tmp_path, rows)])
    assert result["reason"] == "mixed_transfer_lane_episodes"


@pytest.mark.parametrize("contents", ["not-json\n", json.dumps({"normalized_schema_version": 1}) + "\n"])
def test_malformed_or_mixed_schema_fails(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "bad.raw.jsonl"
    path.write_text(contents, encoding="utf-8")
    assert verify([path])["verdict"] == "fail"


@pytest.mark.parametrize(("mutation", "expected"), [
    (None, 0),
    ("no_episode", 2),
    ("bad", 1),
])
def test_cli_exit_semantics(tmp_path: Path, mutation: str | None, expected: int) -> None:
    rows = _canonical_rows()
    if mutation == "no_episode":
        for row in rows:
            if row["payload"]["action"] == "botauto_status":
                row["payload"]["magmaw_transfer_lane_shadow"].update(
                    active=False, tasks=[], retired_tasks=[], intent_comparisons=[])
                for name in ("lifecycle_scope", "episode_generation", "fire_mage_guid", "hunter_guid"):
                    row["payload"]["magmaw_transfer_lane_shadow"].pop(name, None)
    path = _write(tmp_path, rows)
    if mutation == "bad":
        path.write_text("bad\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "tools.raid_program.verify_magmaw_shadow_observation", str(path)],
        cwd=Path(__file__).parents[1], text=True, capture_output=True, check=False,
    )
    assert completed.returncode == expected
    payload = json.loads(completed.stdout)
    assert payload["verdict"] == {0: "pass", 1: "fail", 2: "not_exercised"}[expected]
