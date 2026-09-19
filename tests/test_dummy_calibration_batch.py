import json
from pathlib import Path

import pytest

from tools.raid_program import dummy_calibration_batch as batch


class NativeConsole:
    """Addressed protocol fixture. Scoring clocks are independent per cohort."""
    def __init__(self, *, collision=False):
        self.now = 1000.0
        self.cohorts = {}
        self.commands = []
        self.collision = collision

    def sleep(self, seconds):
        self.now += seconds

    def status(self, cohort):
        a = self.cohorts[cohort]
        return dict(action="botauto_status", ok=True, cohort_id=cohort,
                    active=a["active"], lease_count=int(a["calibrating"]), server_epoch=71, attempt_id=1)

    def calibration(self, cohort, *, full=False):
        a = self.cohorts[cohort]
        elapsed = max(0, min(300, self.now - a["start"] - 5))
        complete = elapsed == 300
        row = dict(guid=a["actor"], damage=int(elapsed * 32000), effective_healing=0,
                   attempts=100 if elapsed else 0, details_included=full)
        result = dict(action="botauto_calibrate_status", ok=True, cohort_id=cohort,
            server_epoch=71, attempt_id=1, calibration_phase_id=60100 if self.collision else a["actor"],
            target_spec=a["spec"], target_guid=a["actor"], seed=1, profile_generation=4,
            profile_content_hash="a" * 64, active=True, mode="single_target_300",
            fixture_target={"runtime_guid": a["actor"] + 100}, failure_reason=None,
            calibration_isolation=dict(phase_lease_held=True, phase_match=True,
                observed_bot_phase_id=60100 if self.collision else a["actor"],
                observed_target_phase_id=60100 if self.collision else a["actor"],
                own_target_visibility_observed=True, peer_visibility_observed=False),
            phase="complete" if complete else "scoring" if elapsed else "warmup",
            scored_seconds=elapsed, scored_started_at_ms=int((a["start"] + 5) * 1000) if elapsed else 0,
            scored_ended_at_ms=int((a["start"] + 305) * 1000) if complete else 0,
            runtime_authority="explicit_sql_rule_profiles", generic_ml_runtime_authority=False,
            runtime_mode="calibration_fixture", non_certifying_assistance=True,
            reset_applied=True, reset_id="reset-" + cohort, cross_window_event_count=0,
            window_complete=complete, bots=[row], previous_window={"bots": [row]} if complete else None)
        if not full:
            result["detail_level"] = "progress"
        return result

    def __call__(self, command, timeout):
        self.commands.append(command)
        t = command.split()
        verb = t[1]
        if verb == "cohorts":
            row = dict(ok=True, action="botauto_cohorts", server_epoch=71,
                       cohorts=[dict(cohort_id=c, active=a["active"]) for c,a in self.cohorts.items()])
        else:
            cohort = t[2]
            if verb == "create":
                self.cohorts[cohort] = dict(active=False, calibrating=False, actor=1300 + len(self.cohorts))
                row = dict(ok=True, action="botauto_create", cohort_id=cohort)
            elif verb == "start":
                self.cohorts[cohort]["active"] = True
                row = self.status(cohort)
            elif verb == "stop":
                self.cohorts[cohort]["active"] = False
                row = dict(ok=True, action="botauto_stop", cohort_id=cohort, server_epoch=71, attempt_id=1)
            elif verb == "status":
                row = self.status(cohort)
            elif verb == "calibrate":
                operation = t[3]
                if operation == "start":
                    self.cohorts[cohort].update(start=self.now, spec=t[5], calibrating=True)
                    row = self.calibration(cohort)
                elif operation == "stop":
                    self.cohorts[cohort]["calibrating"] = False
                    row = dict(ok=True, action="botauto_calibrate_stop", cohort_id=cohort, server_epoch=71, attempt_id=1)
                else:
                    row = self.calibration(cohort, full=operation == "status")
            else:
                raise AssertionError(command)
        return json.dumps(row) + "\n", 0, False


def run(console, tmp_path, monkeypatch, *, contaminated=False, **kwargs):
    # The reference/stats evaluator has its own real-fixture tests. This fixture
    # proves lifecycle, transport and scoring; it cannot claim class acceptance.
    def evaluate(report, **_):
        report["role_calibration_evaluation"] = {"checks": dict(
            reference_conditions_compatible=not contaminated, isolated_single_target_fixture=True,
            single_target_damage_isolated=True)}
        return report
    monkeypatch.setattr(batch, "attach_phase8_role_calibration", evaluate)
    return batch.run_batch(execute=console, specs=["fire_mage", "survival_hunter"],
        output=tmp_path, epoch=71, run_id="fixture", heartbeat=5,
        clock=lambda: console.now, sleep=console.sleep, policy_path=Path("unused"), **kwargs)


def test_two_exact_windows_separate_logs_and_stop_preserves_scoring_witness(tmp_path, monkeypatch):
    console = NativeConsole()
    result = run(console, tmp_path, monkeypatch)
    assert result["all_captures_accepted"]
    assert result["concurrent_cleanup_proved"]
    assert result["performance_accepted"] is False
    assert [a["dps"] for a in result["actors"]] == [32000, 32000]
    assert all(not a["active"] and not a["calibrating"] for a in console.cohorts.values())
    for spec, cohort in (("fire_mage", "fixture-1"), ("survival_hunter", "fixture-2")):
        records = [json.loads(s) for s in (tmp_path / spec / "commands.jsonl").read_text().splitlines()]
        addressed = [r["command"].split()[2] for r in records if r["command"] != ".botauto cohorts"]
        assert set(addressed) == {cohort}
        assert sum(r["command"] == f".botauto calibrate {cohort} status" for r in records) == 1
        report = json.loads((tmp_path / spec / "report.json").read_text())
        assert report["exact_window_capture_accepted"] and report["training_eligible"] is False


def test_phase_collision_rejects_before_claiming_concurrency_and_cleans_both(tmp_path, monkeypatch):
    console = NativeConsole(collision=True)
    with pytest.raises(RuntimeError, match="phase collision"):
        run(console, tmp_path, monkeypatch)
    assert all(not a["active"] and not a["calibrating"] for a in console.cohorts.values())


def test_wrong_responder_cannot_be_joined_to_actor(tmp_path, monkeypatch):
    console = NativeConsole()
    original = console.calibration
    def foreign(cohort, **kwargs):
        row = original(cohort, **kwargs)
        row["server_epoch"] = 99
        return row
    console.calibration = foreign
    with pytest.raises(RuntimeError, match="responder identity"):
        run(console, tmp_path, monkeypatch)
    assert all(not a["active"] for a in console.cohorts.values())


def test_serial_mode_does_not_claim_concurrent_cleanup(tmp_path, monkeypatch):
    result = run(NativeConsole(), tmp_path, monkeypatch, concurrency=1)
    assert result["all_captures_accepted"]
    assert not result["concurrent_cleanup_proved"]


def test_reference_contamination_keeps_dps_but_rejects_capture(tmp_path, monkeypatch):
    result = run(NativeConsole(), tmp_path, monkeypatch, contaminated=True)
    assert not result["all_captures_accepted"] and not result["batch_accepted"]
    assert all(row["dps"] == 32000 for row in result["actors"])


def test_missing_native_phase_observation_rejects_scoring(tmp_path, monkeypatch):
    console = NativeConsole()
    original = console.calibration
    def unobserved(cohort, **kwargs):
        row = original(cohort, **kwargs)
        row["calibration_isolation"]["own_target_visibility_observed"] = False
        return row
    console.calibration = unobserved
    with pytest.raises(RuntimeError, match="observed native phase isolation"):
        run(console, tmp_path, monkeypatch)


def test_foreign_cleanup_receipt_cannot_mark_attempt_stopped(tmp_path, monkeypatch):
    class ForeignCleanup(NativeConsole):
        def __call__(self, command, timeout):
            raw, code, expired = super().__call__(command, timeout)
            if command.split()[1] == "stop":
                row = json.loads(raw)
                row["attempt_id"] = 99
                raw = json.dumps(row)
            return raw, code, expired
    with pytest.raises(RuntimeError, match="cleanup failed"):
        run(ForeignCleanup(), tmp_path, monkeypatch)
    assert not (tmp_path / "fire_mage" / "cleanup.json").exists()


def test_native_stop_uses_generic_identity_for_dummy_and_raid():
    path = Path(__file__).resolve().parents[1] / "src/server/game/Bots/BotWorldPopulationMgrCohort.cpp"
    body = path.read_text().split("std::string BotWorldPopulationMgr::StopAutonomyForCohort", 1)[1]
    body = body.split("std::string BotWorldPopulationMgr::SelectRuntimeProfileForCohort", 1)[0]
    assert "uint64 const serverEpoch = _serverEpoch;" in body
    assert "uint64 const attemptId = Cohort().AttemptId;" in body
    assert "Cohort().Raid.ServerEpoch" not in body
