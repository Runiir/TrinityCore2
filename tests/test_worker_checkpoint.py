import copy
import json
from pathlib import Path

from tools.bot_ml import analyze_magmaw_trace as analyzer
from tools.bot_ml import laya_packets
from tools.raid_program import worker_checkpoint as worker


def make_checkpoint(tmp_path: Path, *, stage="result"):
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("resolver block extracted; execution claim remains separate\n")
    return {
        "task_id": "potion-resolver-pilot",
        "objective": "Repair the assigned potion resolver edge.",
        "first_broken_edge": "dual_resolver_potion_exclusion",
        "allowed_files": ["tools/raid_program/worker_checkpoint.py", "tests/test_worker_checkpoint.py"],
        "forbidden_changes": ["native gameplay", "server configuration", "global BloodFury deletion"],
        "acceptance_conditions": [
            {"id": "unit", "claim": "resolver unit test proves one scored potion use"},
            {"id": "scope", "claim": "only assigned files change"},
        ],
        "observations": [
            "The resolver block is extracted from the assigned source.",
            "No native callback execution is shown by this checkpoint.",
        ],
        "evidence_excerpts": [{
            "path": str(evidence),
            "sha256": worker.sha(evidence.read_bytes()),
            "excerpt": "resolver block extracted; execution claim remains separate",
        }],
        "proposed_change": "Add the bounded resolver fixture and retain native execution as a separate acceptance step.",
        "acceptance_claim": "The resolver unit fixture passes; live native execution remains pending.",
        "stage": stage,
        "changed_files": ["tools/raid_program/worker_checkpoint.py", "tests/test_worker_checkpoint.py"] if stage == "result" else [],
        "changed_files_source": "coordinator_observed",
        "tests": [{"command": "pixi run pytest tests/test_worker_checkpoint.py -q", "exit_status": 0}],
        "required_test_commands": ["pixi run pytest tests/test_worker_checkpoint.py -q"],
    }


def typed_response(packet):
    answers = {}
    for question_id in packet["questions"]:
        answers[question_id] = {
            "type": "choice",
            "choice": "supported",
            "confidence": 0.61,
            "probabilities": {"supported": 0.61, "contradicted": 0.09, "insufficient_evidence": 0.30},
        }
    return {"model": packet["model"], "answers": answers}


def test_deterministic_findings_are_separate_and_fail_closed(tmp_path):
    checkpoint = make_checkpoint(tmp_path)
    checkpoint["changed_files"].append("src/server/game/Forbidden.cpp")
    checkpoint["tests"][0]["exit_status"] = 7
    checkpoint["evidence_excerpts"][0]["sha256"] = "0" * 64

    result = worker.deterministic_findings(checkpoint, tmp_path)
    assert result["status"] == "fail"
    assert {finding["kind"] for finding in result["findings"]} == {
        "outside_allowed_files", "failed_required_test", "cited_artifact_sha256_mismatch",
    }


def test_result_without_required_tests_is_deterministic_failure(tmp_path):
    checkpoint = make_checkpoint(tmp_path)
    checkpoint["tests"] = []
    result = worker.deterministic_findings(checkpoint, tmp_path)
    assert result == {
        "status": "fail",
        "test_receipts_basis": "reported command and exit status; execution is not independently verified",
        "findings": [{
            "kind": "missing_required_tests",
            "status": "fail",
            "command": "pixi run pytest tests/test_worker_checkpoint.py -q",
            "detail": "required command has no receipt",
        }],
    }


def test_orchestrator_requires_goal_and_preserves_latest_direction(tmp_path):
    import pytest
    checkpoint = make_checkpoint(tmp_path, stage="plan")
    checkpoint["subject"] = "orchestrator"
    with pytest.raises(ValueError, match="parent goal"):
        worker.validate_checkpoint(checkpoint)
    checkpoint["goal_context"] = {
        "parent_objective": "Calibrate every represented class.",
        "latest_user_direction": "Improve the worker review workflow first.",
        "current_plan": ["Test the staged diff hook", "Retain class findings"],
        "remaining_requirements": ["Balance passives", "Live potion validation"],
        "completed_work": ["Five isolated windows captured"],
    }
    result = worker.validate_checkpoint(checkpoint)
    packet = worker.build_packet(result, laya_packets.MODEL)
    assert packet["state"]["checkpoint"]["goal_context"] == checkpoint["goal_context"]
    checkpoint["stage"] = "result"
    checkpoint["tests"] = []
    checkpoint["required_test_commands"] = []  # Explicit non-code review task.
    assert worker.deterministic_findings(checkpoint, tmp_path)["status"] == "pass"


def test_local_supported_advice_remains_coordinator_review(tmp_path, monkeypatch):
    checkpoint = make_checkpoint(tmp_path)
    monkeypatch.setattr(worker.jev_shadow, "call_local", lambda packet, endpoint: typed_response(packet))
    output = tmp_path / "review"

    summary = worker.review_checkpoint(checkpoint, output, backend="local", base_dir=tmp_path)

    assert summary["deterministic"]["status"] == "pass"
    assert summary["responses"] == 1 and summary["errors"] == 0
    assert summary["model_status"] == {"local_laya": "advisory"}
    assert summary["coordinator_review_required"] is True
    assert summary["automatic_pass"] is False
    row = json.loads((output / "examples.jsonl").read_text().splitlines()[0])
    assert row["backend"]["action_authority"] is False
    assert row["response"]["answers"]["scope_fit"]["choice"] == "supported"
    assert row["request_sha256"] == worker.sha(row["request_json"].encode())
    assert "worker_checkpoint" in row["backend"]["execution_source"]
    state = json.loads(row["request_json"])["state"]["checkpoint"]
    assert state["acceptance_claim"].startswith("The resolver unit fixture")
    assert state["evidence_excerpts"] == [{"id": "0", "excerpt": "resolver block extracted; execution claim remains separate"}]
    assert "path" not in state["evidence_excerpts"][0]


def test_packet_compaction_preserves_paths_commands_failures_and_input(tmp_path):
    checkpoint = make_checkpoint(tmp_path)
    checkpoint["changed_files"].append("outside.cpp")
    checkpoint["tests"][0]["exit_status"] = 9
    checkpoint["tests"].append({"command": "extra check", "exit_status": 1})
    original = copy.deepcopy(checkpoint)
    packet = worker.build_packet(checkpoint, laya_packets.MODEL)
    state = packet["state"]["checkpoint"]
    files = state["changed_files"]
    assert [state["allowed_files"][i] for i in files["allowed_files_indices"]] + files["other_paths"] == checkpoint["changed_files"]
    restored = []
    for test in state["tests"]:
        test = dict(test)
        if "required_test_commands_index" in test:
            test["command"] = state["required_test_commands"][test.pop("required_test_commands_index")]
        restored.append(test)
    assert restored == checkpoint["tests"]
    assert checkpoint == original
    assert worker.build_packet(checkpoint, analyzer.JEV_MODEL)["state"] == packet["state"]


def test_provider_failure_is_unknown_and_not_a_pass(tmp_path, monkeypatch):
    checkpoint = make_checkpoint(tmp_path)
    def fail(packet, endpoint):
        raise ValueError("local token budget rejected without truncation")
    monkeypatch.setattr(worker.jev_shadow, "call_local", fail)
    output = tmp_path / "failed-review"

    summary = worker.review_checkpoint(checkpoint, output, backend="local", base_dir=tmp_path)

    assert summary["deterministic"]["status"] == "pass"
    assert summary["responses"] == 0 and summary["errors"] == 1
    assert summary["model_status"] == {"local_laya": "unknown"}
    row = json.loads((output / "examples.jsonl").read_text().splitlines()[0])
    assert row["response"] is None
    assert "token budget" in row["error"]
    assert row["response_sha256"] is None
    assert summary["automatic_pass"] is False


def test_local_422_retains_budget_receipt_without_retry(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace
    from urllib.error import HTTPError

    calls = []
    detail = {"detail": {"error": "context_budget_exceeded", "token_budget": {
        "scope_fit": {"state_tokens": 1288, "state_budget": 894,
                      "truncated_fields": ["state"]}}}}

    def reject(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 422, "Unprocessable Content", {},
                        io.BytesIO(json.dumps(detail).encode()))

    monkeypatch.setattr(worker.jev_shadow, "build_opener",
                        lambda *args: SimpleNamespace(open=reject))
    output = tmp_path / "rejected"
    summary = worker.review_checkpoint(make_checkpoint(tmp_path), output,
                                       backend="local", base_dir=tmp_path)
    row = json.loads((output / "examples.jsonl").read_text().splitlines()[0])
    assert len(calls) == 1
    assert row["response"] is None and row["model_status"] == "unknown"
    assert json.loads(row["error"].split("local HTTP 422: ", 1)[1]) == detail
    assert summary["responses"] == 0 and summary["automatic_pass"] is False


def test_local_http_error_body_is_bounded(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace
    from urllib.error import HTTPError
    import pytest

    def reject(request, timeout):
        raise HTTPError(request.full_url, 500, "Server Error", {},
                        io.BytesIO(b"x" * 10000))

    monkeypatch.setattr(worker.jev_shadow, "build_opener",
                        lambda *args: SimpleNamespace(open=reject))
    packet = worker.build_packet(make_checkpoint(tmp_path), laya_packets.MODEL)
    with pytest.raises(ValueError, match="local HTTP 500") as caught:
        worker.jev_shadow.call_local(packet, worker.jev_shadow.ENDPOINT)
    assert str(caught.value).count("x") == 8192
    assert "error body truncated" in str(caught.value)


def test_hosted_backend_uses_jev_and_retains_provider_failure(tmp_path, monkeypatch):
    checkpoint = make_checkpoint(tmp_path)
    monkeypatch.setattr(worker.analyzer, "_jev_key", lambda env_file: "test-key")
    def fail(state, key, questions):
        raise analyzer.JevError("provider unavailable")
    monkeypatch.setattr(worker.analyzer, "_call_jev", fail)
    output = tmp_path / "hosted-review"

    summary = worker.review_checkpoint(checkpoint, output, backend="hosted", base_dir=tmp_path)

    assert summary["responses"] == 0 and summary["errors"] == 1
    row = json.loads((output / "examples.jsonl").read_text().splitlines()[0])
    assert row["provider"] == "hosted_jev"
    assert row["backend"]["requested_model"] == analyzer.JEV_MODEL
    assert row["model_status"] == "unknown"
    assert row["response"] is None


def test_prepare_only_makes_no_provider_call_and_refuses_overwrite(tmp_path, monkeypatch):
    checkpoint = make_checkpoint(tmp_path, stage="plan")
    called = []
    monkeypatch.setattr(worker.jev_shadow, "call_local", lambda *args: called.append(args))
    output = tmp_path / "prepared"

    summary = worker.review_checkpoint(checkpoint, output, backend="local",
                                       prepare_only=True, base_dir=tmp_path)
    assert summary["responses"] == 0 and summary["errors"] == 0
    assert summary["model_status"] == {"local_laya": "prepared"}
    assert called == []
    try:
        worker.review_checkpoint(checkpoint, output, backend="local", base_dir=tmp_path)
    except FileExistsError as exc:
        assert "refusing to overwrite" in str(exc)
    else:
        raise AssertionError("existing output was overwritten")
