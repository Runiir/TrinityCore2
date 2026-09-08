import base64
from copy import deepcopy
import json

import pytest

from tools.bot_ml.run_live_bot_validation import CohortCommandExecutor
from tools.raid_program.shared_instance_observation import InstanceExpectation
from tools.raid_program.shared_instance_validation import (
    _Identity,
    _RawRecorder,
    _combat_log,
    run_shared_instance_validation,
)


class Clock:
    def __init__(self):
        self.value = 100.0
        self.interrupt = False

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        if self.interrupt:
            self.interrupt = False
            raise KeyboardInterrupt
        self.value += seconds


class NativeFixture:
    def __init__(self, failure=""):
        self.failure = failure
        self.commands = []
        self.epoch = 91
        self.roles = {
            "subject": {
                "id": "subject", "profile": "subject_profile",
                "guids": [1, 2], "instance": 101, "group": 201,
            },
            "witness": {
                "id": "witness", "profile": "witness_profile",
                "guids": [3, 4], "instance": 102, "group": 202,
            },
        }
        if failure == "shared_instance":
            self.roles["witness"]["instance"] = 101
        self.state = {
            role: {
                "created": False, "active": False, "attempt": 0,
                "profile": "", "leases": 0, "progress": 0,
                "stopped_subject": False,
            }
            for role in self.roles
        }
        self.subject_has_stopped = False
        if failure == "preexisting_cohort":
            self.state["witness"]["created"] = True

    def _role(self, cohort):
        return next(role for role, row in self.roles.items() if row["id"] == cohort)

    def registry(self):
        cohorts = []
        for role, identity in self.roles.items():
            state = self.state[role]
            if state["created"]:
                cohorts.append({
                    "cohort_id": identity["id"], "active": state["active"],
                    "attempt_id": state["attempt"], "lease_count": state["leases"],
                    "party_bot_count": state["leases"],
                })
        active = sum(1 for row in cohorts if row["active"])
        return {
            "ok": True, "action": "botauto_cohorts", "server_epoch": self.epoch,
            "server_process_id": 778 if self.failure == "wrong_pid" else 777, "max_active_cohorts": 2,
            "active_cohort_count": active, "cohort_count": len(cohorts),
            "cohorts": cohorts, "failure_reason": None,
        }

    def status(self, role):
        identity, state = self.roles[role], self.state[role]
        active = state["active"]
        leases = state["leases"]
        raid = {
            "server_epoch": self.epoch, "attempt_id": state["attempt"],
            "map_id": 669, "map_difficulty": 0,
            "instance_id": identity["instance"] if active else 0,
            "group_guid": identity["group"] if active else 0,
            "bot_actions_enabled": active, "roster_complete": active,
            "difficulty_readback_complete": active, "difficulty_matches": active,
        }
        return {
            "ok": True, "action": "botauto_status", "cohort_id": identity["id"],
            "server_epoch": self.epoch, "attempt_id": state["attempt"],
            "profile_generation": 7, "profile_content_hash": "a" * 64,
            "active_profile": state["profile"] or None,
            "active": active, "bots": leases, "target_bots": 2,
            "lease_count": leases, "decisions": state["progress"], "deaths": 0,
            "raid_runtime": raid,
            "validation_route": {"generation": 1, "manifest_complete": False},
            "failure_reason": None,
        }

    def diagnosis(self, role):
        identity, state = self.roles[role], self.state[role]
        status = self.status(role)
        bots = []
        for guid in identity["guids"] if state["active"] else []:
            movement_available = not (
                self.failure == "movement_loss" and self.subject_has_stopped
            ) and self.failure != "movement_empty"
            receipt = {
                "receipt_id": 100 + guid + (1000 if self.failure == "movement_repopulate" and self.subject_has_stopped else 0),
                "bot_guid": guid, "map": 669, "instance": identity["instance"],
                "scope": {"attempt_id": state["attempt"], "route_generation": 1, "wipe_generation": 0},
                "armed_at_ms": 1, "selected_endpoint": {"x": 1, "y": 2, "z": 3},
                "actor_at_launch": {"x": 0, "y": 0, "z": 0},
                "launched_spline": {"id": 1}, "samples": [{}] * state["progress"],
                "dropped_sample_count": 0,
            }
            snapshot = {
                "validation_cohort": {
                    "locked": True, "in_world": True, "matches_cohort": True,
                    "violation": False, "current_map_id": 669,
                    "current_instance_id": identity["instance"],
                    "current_position": {
                        "x": float(state["progress"]), "y": 2.0, "z": 3.0, "o": 0.0,
                    },
                },
                "movement": {"is_moving": bool(state["progress"] % 2)},
                "movement_planner": {
                    "available": movement_available, "bot_guid": 999 if self.failure == "movement_foreign_owner" else guid,
                    "intent_reason": "route",
                },
                "movement_receipt_progress": {
                    "available": movement_available, "bot_guid": guid,
                    "receipts": [receipt] if movement_available else [],
                },
            }
            bots.append({
                "identity": {"bot_guid": guid, "bot_name": f"bot{guid}"},
                "snapshot": snapshot,
                "diagnosis": {"state": "running", "reason_code": "ok"},
            })
        return {
            "ok": True, "action": "botauto_diagnose", "cohort_id": identity["id"],
            "diagnosis_schema_version": 1, "bots": bots,
            "combat_metrics": {
                "schema": (
                    "bot_combat_metrics_v3"
                    if self.failure == "friendly_only"
                    else "bot_combat_metrics_v2"
                ),
                "measurement_basis": (
                    "hostile_originated_damage"
                    if self.failure == "friendly_only"
                    else "originated_damage"
                ),
                "party_damage": (
                    0 if self.failure == "friendly_only"
                    else state["progress"] * 10
                ),
                "party_friendly_damage": (
                    state["progress"] * 10
                    if self.failure == "friendly_only" else 0
                ),
                "party_dps": float(state["progress"] * 10),
                "party_healing": 0, "party_hps": 0.0,
            },
            "raid_runtime": status["raid_runtime"], "failure_reason": None,
        }

    def trace(self, role):
        identity, state = self.roles[role], self.state[role]
        epoch = self.epoch + (1 if self.failure == "stale_trace" and state["progress"] else 0)
        row = {
            "ok": True, "action": "botauto_trace", "cohort_id": identity["id"],
            "server_epoch": epoch, "attempt_id": state["attempt"],
            "profile_generation": 7, "profile_content_hash": "a" * 64,
            "active_profile": state["profile"], "trace_schema_version": 1,
            "bots": [
                {"bot_guid": guid, "entries": ([{
                    "sequence": state["progress"], "timestamp_ms": state["progress"] + 1,
                    "action": "raid_boss_action", "result": "submitted",
                }] if state["progress"] else [])}
                for guid in identity["guids"]
            ],
            "failure_reason": None,
        }
        return row

    def combat(self, role):
        identity, state = self.roles[role], self.state[role]
        can_advance = state["active"] and not (
            self.failure == "post_stop_stale"
            and role == "witness" and self.subject_has_stopped
        )
        if self.failure == "stalled_subject" and role == "subject":
            can_advance = False
        if can_advance:
            state["progress"] += 5000 if self.failure == "unseen_events" and state["progress"] else 1
        count = state["progress"]
        perspective = (
            "damage_taken" if self.failure == "incoming_only"
            else "friendly_damage_done" if self.failure == "friendly_only"
            else "damage_done"
        )
        outgoing = 0 if perspective == "damage_taken" else count * 10
        actor = identity["guids"][0]
        event_actor = 999 if self.failure == "foreign_actor" else actor
        events = []
        for sequence in range(count):
            if perspective == "damage_done":
                source_guid, source_entry = actor, 0
                # This creature low GUID collides with the other cohort's
                # player counter. Its nonzero entry keeps the types distinct.
                target_guid, target_entry = 3, 41570
            else:
                source_guid, source_entry = 1, 41570
                target_guid, target_entry = actor, 0
            if self.failure == "foreign_source_player":
                source_guid, source_entry = 999, 0
            if self.failure == "foreign_target_player":
                target_guid, target_entry = 999, 0
            events.append({
                "timestamp_ms": sequence + 1, "kind": "damage",
                "actor_guid": event_actor, "source_guid": source_guid,
                "source_entry": source_entry, "target_guid": target_guid,
                "target_entry": target_entry, "amount": 10,
                "originated_amount": 10, "source_is_pet": False,
            })
        visible = events[-4096:]
        observed_count = count
        if self.failure == "same_count_growth" and count:
            visible = events[-1:]
            observed_count = 1
        return {
            "ok": True, "action": "botauto_combatlog", "cohort_id": identity["id"],
            "server_epoch": self.epoch, "attempt_id": state["attempt"],
            "profile_generation": 7, "profile_content_hash": "a" * 64,
            "active_profile": state["profile"],
            "combat_log_schema_version": 3 if self.failure == "friendly_only" else 2,
            "damage_attribution_schema": (
                "originated_amount_v2_friendly_split"
                if self.failure == "friendly_only" else "originated_amount_v1"
            ),
            "event_count": observed_count + (1 if self.failure == "event_accounting" else 0),
            "recent_events_dropped": observed_count - len(visible),
            "recent_events": visible,
            "abilities": ([{
                "perspective": perspective, "actor_guid": actor,
                "originated_amount": outgoing, "amount": count * 10,
                "event_count": count,
            }] if count else []),
            "failure_reason": None,
        }

    def chunks(self, role):
        identity = self.roles[role]
        payload = json.dumps(self.combat(role), separators=(",", ":")).encode()
        chunk = {
            "ok": True, "action": "botauto_combatlog_chunk",
            "cohort_id": identity["id"], "combat_log_chunk_schema_version": 1,
            "sequence": 0, "chunk_count": 1, "encoding": "base64",
            "data": base64.b64encode(payload).decode(),
        }
        if self.failure == "transport_gap":
            return json.dumps(chunk) + "\n"
        completion = {
            "ok": True, "action": "botauto_combatlog_complete",
            "cohort_id": identity["id"], "combat_log_chunk_schema_version": 1,
            "chunk_count": 1, "total_bytes": len(payload),
        }
        return json.dumps(chunk) + "\n" + json.dumps(completion) + "\n"

    def execute(self, command, _timeout):
        self.commands.append(command)
        tokens = command.split()
        if tokens == [".botauto", "cohorts"]:
            return json.dumps(self.registry()), 0, False
        role = self._role(tokens[2])
        state = self.state[role]
        verb = tokens[1]
        if verb == "create":
            created = not state["created"]
            state["created"] = True
            row = {"ok": True, "action": "botauto_create", "cohort_id": tokens[2],
                   "created": created, "failure_reason": None}
            if self.failure == "create_false":
                row["created"] = False
            if self.failure == "create_lost":
                return "lost reply", 1, True
        elif verb == "prepare":
            state["profile"] = tokens[3]
            row = {"ok": True, "action": "botauto_prepare", "profile": tokens[3],
                   "pool_tag_filter": tokens[3], "failure_reason": None}
        elif verb == "start":
            state["active"] = True
            state["attempt"] += 1
            state["leases"] = len(self.roles[role]["guids"])
            row = self.status(role)
        elif verb == "stop":
            if role == "subject" and state["active"]:
                self.subject_has_stopped = True
            cleanup_fails = self.failure == "cleanup_failure" and role == "witness" and self.subject_has_stopped
            if not cleanup_fails:
                state["active"] = False
                state["leases"] = 0
            row = {
                "ok": True, "action": "botauto_stop", "cohort_id": tokens[2],
                "server_epoch": self.epoch, "attempt_id": state["attempt"],
                "post_cleanup": {"active": state["active"], "bots": state["leases"],
                                 "lease_count": state["leases"]},
                "failure_reason": None,
            }
        elif verb == "status":
            row = self.status(role)
        elif verb == "diagnose":
            row = self.diagnosis(role)
        elif verb == "trace":
            row = self.trace(role)
            text = json.dumps(row)
            if self.failure == "ambiguous_trace":
                text += "\n" + json.dumps(deepcopy(row))
            return text, 0, False
        elif verb == "combatlog":
            return self.chunks(role), 0, False
        else:
            raise AssertionError(command)
        return json.dumps(row), 0, False


def fixture():
    return {
        "schema": "cata_shared_instance_fixture_v1",
        "fixture_id": "pair",
        "boss_completion_eligible": False,
        "training_eligible": False,
        "maximum_active_cohorts": 2,
        "map_update_threads": 1,
        "subject_shard_id": "subject",
        "witness_shard_id": "witness",
        "start_order": ["witness", "subject"],
        "stop_order": ["subject", "witness"],
        "watchdog": {
            "duration_policy": "completion-watchdog", "heartbeat_sec": 5,
            "no_progress_window_sec": 15, "max_repeated_decisions": 20,
            "max_death_loops": 3, "emergency_timeout_sec": 40,
            "transition_timeout_sec": 10,
        },
    }


def run(tmp_path, failure="", clock=None, fixture_value=None):
    native = NativeFixture(failure)
    clock = clock or Clock()
    executors = {
        role: CohortCommandExecutor(native.execute, row["id"], exclusive=False)
        for role, row in native.roles.items()
    }
    expectations = {
        role: InstanceExpectation(
            row["id"], 669, 0, frozenset(row["guids"]),
        )
        for role, row in native.roles.items()
    }
    report = run_shared_instance_validation(
        fixture=fixture_value or fixture(),
        session={
            "server_epoch": native.epoch,
            "server_process_id": 777,
            "server_process_identity_verified": True,
        },
        coordinator_command=native.execute,
        executors=executors,
        expectations=expectations,
        profile_ids={role: row["profile"] for role, row in native.roles.items()},
        output_path=tmp_path / "report.json",
        clock=clock,
        sleep=clock.sleep,
    )
    return report, native


def test_proves_both_active_progress_then_fresh_post_stop_witness_progress(tmp_path):
    report, native = run(tmp_path)
    assert report["isolation_passed"] is True
    assert report["terminal_reason"] == "interruption"
    assert report["terminal_detail"] == "isolation_fixture_passed"
    assert report["failure_reason"] is None
    assert report["boss_clear_claimed"] is False
    assert report["training_eligible"] is False
    assert report["ml_admission_eligible"] is False
    assert report["cleanup"]["passed"] is True
    assert all(not state["active"] and state["leases"] == 0 for state in native.state.values())
    proof = report["proof"]
    assert proof["both_active"]["subject"]["outgoing_amount"] > 0
    assert proof["both_active"]["witness"]["outgoing_amount"] > 0
    assert (proof["witness_after_subject_stop_progress"]["outgoing_amount"]
            > proof["witness_after_subject_stop_baseline"]["outgoing_amount"])
    assert (tmp_path / "report.raw.jsonl").is_file()
    assert report["raw_command_count"] > 0


def test_shared_validator_retains_friendly_perspective_without_counting_outgoing(tmp_path):
    native = NativeFixture("friendly_only")
    native.state["subject"]["created"] = True
    native.state["subject"]["active"] = True
    native.state["subject"]["attempt"] = 1
    native.state["subject"]["profile"] = "subject_profile"
    native.state["subject"]["leases"] = 2
    executor = CohortCommandExecutor(native.execute, "subject", exclusive=False)
    expected = InstanceExpectation("subject", 669, 0, frozenset({1, 2}))
    anchor = _Identity(
        "subject", 91, 1, "subject_profile", 7, "a" * 64,
        669, 101, 201, 2, (1, 2),
    )
    recorder = _RawRecorder(tmp_path / "combat.raw.jsonl", Clock())
    try:
        combat, _ = _combat_log(
            executor, expected, "subject_profile", recorder, anchor,
            role="subject", phase="friendly_fixture",
        )
    finally:
        recorder.close()

    assert combat["combat_log_schema_version"] == 3
    assert any(
        row.get("perspective") == "friendly_damage_done"
        for row in combat["abilities"]
    )
    assert combat["validated_outgoing_amount"] == 0


@pytest.mark.parametrize("failure,reason", [
    ("shared_instance", "pair_instance_identity_invalid"),
    ("stale_trace", "trace_identity_stale"),
    ("ambiguous_trace", "botauto_trace_envelope_ambiguous"),
    ("foreign_actor", "combat_actor_foreign"),
    ("foreign_source_player", "combat_source_player_foreign"),
    ("foreign_target_player", "combat_target_player_foreign"),
    ("event_accounting", "combat_event_accounting_mismatch"),
    ("transport_gap", "combat_log_export_incomplete"),
])
def test_rejects_foreign_stale_ambiguous_or_transport_invalid_evidence(
    tmp_path, failure, reason,
):
    report, _ = run(tmp_path, failure)
    assert report["isolation_passed"] is False
    assert report["terminal_reason"] == "contamination"
    assert report["terminal_detail"] == reason
    assert report["cleanup"]["passed"] is True
    diagnostic = report["failure_diagnostic"]
    records = [json.loads(line) for line in (tmp_path / "report.raw.jsonl").read_text().splitlines()]
    context = diagnostic["last_command"]
    recorded = records[context["sequence"] - 1]
    assert all(recorded[key] == value for key, value in context.items())
    assert context["phase"] != "final_cleanup"
    if failure == "shared_instance":
        assert diagnostic["cause_type"] == "ValueError"
        assert diagnostic["cause"] == "cohorts share instance, group, or roster ownership"


def test_rejects_spectator_or_incoming_only_activity(tmp_path):
    report, _ = run(tmp_path, "incoming_only")
    assert report["isolation_passed"] is False
    assert report["terminal_reason"] in {"semantic_stall", "infrastructure_loss"}
    assert report["terminal_detail"] in {"no_progress_watchdog", "emergency_wall_clock_timeout"}


def test_rejects_false_post_stop_progress(tmp_path):
    report, _ = run(tmp_path, "post_stop_stale")
    assert report["isolation_passed"] is False
    assert report["terminal_reason"] in {"semantic_stall", "infrastructure_loss"}
    assert report["terminal_detail"] in {"no_progress_watchdog", "emergency_wall_clock_timeout"}


def test_rejects_movement_record_loss(tmp_path):
    report, _ = run(tmp_path, "movement_loss")
    assert report["isolation_passed"] is False
    assert report["terminal_reason"] == "contamination"
    assert report["terminal_detail"] == "movement_record_lost"


def test_cleanup_failure_invalidates_completed_proof(tmp_path):
    report, native = run(tmp_path, "cleanup_failure")
    assert report["isolation_passed"] is False
    assert report["terminal_reason"] == "infrastructure_loss"
    assert report["terminal_detail"] == "cleanup_failure"
    assert report["cleanup"]["passed"] is False
    assert native.state["witness"]["active"] is True


def test_operator_interrupt_is_typed_and_owned_cleanup_still_runs(tmp_path):
    clock = Clock()
    clock.interrupt = True
    report, native = run(tmp_path, clock=clock)
    assert report["isolation_passed"] is False
    assert report["terminal_reason"] == "interruption"
    assert report["terminal_detail"] == "operator_interrupt"
    assert report["cleanup"]["passed"] is True
    assert all(not state["active"] for state in native.state.values())


def test_nonfinite_watchdog_value_fails_before_cohort_mutation(tmp_path):
    value = fixture()
    value["watchdog"]["heartbeat_sec"] = float("nan")
    report, native = run(tmp_path, fixture_value=value)
    assert report["isolation_passed"] is False
    assert report["terminal_reason"] == "infrastructure_loss"
    assert report["terminal_detail"] == "heartbeat_sec_invalid"
    assert all(not state["created"] for state in native.state.values())


def test_one_progressing_role_cannot_keep_stalled_role_alive(tmp_path):
    clock = Clock()
    value = fixture()
    value["watchdog"].update(heartbeat_sec=5, no_progress_window_sec=12, emergency_timeout_sec=100)
    report, _ = run(tmp_path, "stalled_subject", clock=clock, fixture_value=value)
    assert report["terminal_reason"] == "semantic_stall"
    assert clock.value == 112


@pytest.mark.parametrize("failure,detail", [
    ("movement_empty", "movement_receipt_witness_missing"),
    ("movement_repopulate", "movement_receipt_identity_lost"),
    ("movement_foreign_owner", "movement_owner_mismatch"),
])
def test_movement_requires_attributed_receipt_survival(tmp_path, failure, detail):
    report, _ = run(tmp_path, failure)
    assert report["isolation_passed"] is False
    assert report["terminal_detail"] == detail


def test_wrong_registry_pid_rejects_before_creation(tmp_path):
    report, native = run(tmp_path, "wrong_pid")
    assert report["isolation_passed"] is False
    assert not any(" create " in command for command in native.commands)


def test_denied_create_does_not_take_over_existing_cohort(tmp_path):
    report, native = run(tmp_path, "create_false")
    assert report["terminal_detail"] == "create_ownership_rejected"
    assert report["cleanup"]["passed"] is False
    assert not any(" stop " in command or " prepare " in command for command in native.commands)


def test_lost_create_reply_attempts_cleanup_without_claiming_certain_ownership(tmp_path):
    report, native = run(tmp_path, "create_lost")
    assert report["isolation_passed"] is False
    assert report["cleanup"]["passed"] is False
    assert report["cleanup"]["uncertain_cohorts"] == ["witness"]
    assert ".botauto stop witness" in native.commands


@pytest.mark.parametrize("failure,detail", [
    ("same_count_growth", "combat_outgoing_delta_mismatch"),
    ("unseen_events", "combat_event_visibility_gap"),
])
def test_driver_rejects_uninspectable_native_progress(tmp_path, failure, detail):
    report, _ = run(tmp_path, failure)
    assert report["isolation_passed"] is False
    assert report["terminal_detail"] == detail


def test_preexisting_fixture_identity_never_reaches_create_or_stop(tmp_path):
    report, native = run(tmp_path, "preexisting_cohort")
    assert report["terminal_detail"] == "create_cohort_preexisting"
    assert all(command == ".botauto cohorts" for command in native.commands)
