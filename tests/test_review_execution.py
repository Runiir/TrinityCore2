"""Tests for rollout-backed and external JSON independent review receipts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.raid_program import development_graph as graph
from tools.raid_program import review_execution

from test_workflow_step import workflow_case


def _rollout(
    root: Path,
    sessions_root: Path,
    file_hashes: dict[str, str],
    *,
    reviewer: str = "reviewer-id",
    include_final: bool = True,
    cwd: Path | None = None,
    verdict: str = "approved",
) -> Path:
    path = sessions_root / "2026" / "09" / "21" / "rollout-review.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    final = {
        "verdict": verdict,
        "file_hashes": file_hashes,
        "findings": [],
        "tests": [{"command": "pixi run pytest -q", "exit_status": 0}],
        "limits": ["workflow review only"],
    }
    metadata = {
        "session_id": "coordinator-parent",
        "id": reviewer,
        "cwd": str(cwd or root),
        "source": {"subagent": {"thread_spawn": {"agent_nickname": "reviewer"}}},
    }
    lines = [{"type": "session_meta", "payload": metadata}]
    if include_final:
        lines.append({
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": json.dumps(final, sort_keys=True)}],
            },
        })
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in lines), encoding="utf-8")
    return path


def test_build_review_uses_rollout_identity_and_exact_hashes(workflow_case, tmp_path: Path):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    file_hashes = graph.snapshot(root, ["code.py"])
    rollout = _rollout(root, sessions, file_hashes)
    result = review_execution.build_review(
        root,
        rollout,
        ["code.py"],
        "artifacts/review-report.json",
        receipt_path="artifacts/review-receipt.json",
        implementer_session_id="coordinator-parent",
        sessions_root=sessions,
    )
    receipt = json.loads((root / "artifacts/review-receipt.json").read_text())
    report = json.loads((root / "artifacts/review-report.json").read_text())
    assert result["reviewer_session_id"] == "reviewer-id"
    assert receipt["reviewer_session_id"] == "reviewer-id"
    assert report["verdict"] == "approved"
    assert report["file_hashes"] == file_hashes
    assert report["tests"] == [{"command": "pixi run pytest -q", "exit_status": 0}]
    assert report["limits"] == ["workflow review only"]
    assert "transcript" not in report and "text" not in report
    assert review_execution.verify_review(
        root,
        receipt,
        implementer_session_id="coordinator-parent",
        sessions_root=sessions,
    ) == file_hashes


def test_proof_reuses_selected_immutable_prefix_after_append(workflow_case, tmp_path: Path):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    hashes = graph.snapshot(root, ["code.py"])
    rollout = _rollout(root, sessions, hashes)
    review_execution.build_review(root, rollout, ["code.py"], "review.json", sessions_root=sessions)
    receipt = json.loads((root / "review.receipt.json").read_text())
    with rollout.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}}) + "\n")
        stream.write('{"type":"response_item","payload":')
        stream.write(json.dumps({
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "{\"verdict\":\"changes_requested\",\"file_hashes\":{},\"findings\":[]}"}],
            },
        }) + "\n")
    assert review_execution.verify_review(root, receipt, sessions_root=sessions) == hashes


def test_mutated_prefix_and_forged_session_are_rejected(workflow_case, tmp_path: Path):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    hashes = graph.snapshot(root, ["code.py"])
    rollout = _rollout(root, sessions, hashes)
    review_execution.build_review(root, rollout, ["code.py"], "review.json", sessions_root=sessions)
    receipt = json.loads((root / "review.receipt.json").read_text())
    original = rollout.read_bytes()
    rollout.write_bytes(original.replace(b"reviewer-id", b"forged-id", 1))
    with pytest.raises(ValueError, match="prefix|identity"):
        review_execution.verify_review(root, receipt, sessions_root=sessions)


def test_final_hash_mismatch_is_rejected_before_output(workflow_case, tmp_path: Path):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    rollout = _rollout(root, sessions, {"code.py": "0" * 64})
    with pytest.raises(ValueError, match="current files"):
        review_execution.build_review(root, rollout, ["code.py"], "review.json", sessions_root=sessions)


def test_preflight_accepts_fresh_reviewer_transcript_without_final(workflow_case, tmp_path: Path, capsys):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    rollout = _rollout(root, sessions, graph.snapshot(root, ["code.py"]), include_final=False)

    result = review_execution.preflight_review(
        root,
        rollout,
        reviewer_session_id="reviewer-id",
        implementer_session_id="coordinator-parent",
        sessions_root=sessions,
    )
    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["final_present"] is False
    assert result["metadata_count"] == 1
    assert result["prefix_bytes"] == rollout.stat().st_size
    assert len(result["prefix_sha256"]) == 64


def test_identity_preflight_accepts_handshake_followed_by_usage_records(workflow_case, tmp_path: Path, capsys):
    root, _ = workflow_case
    sessions = tmp_path / 'sessions'
    rollout = _rollout(root, sessions, graph.snapshot(root, ['code.py']))
    with rollout.open('a') as stream:
        stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'token_count'}}) + '\n')
    result = review_execution.preflight_review(root, rollout, reviewer_session_id='reviewer-id',
        implementer_session_id='coordinator-parent', sessions_root=sessions)
    assert result['ok'] is True and result['final_present'] is True
    # Final proof verification still requires the exact final-message boundary.
    with pytest.raises(review_execution.ReviewExecutionError, match='proven final prefix'):
        review_execution._read_rollout(rollout, root, result['prefix_bytes'])

    assert review_execution.main([
        "preflight",
        "--root",
        str(root),
        "--rollout",
        str(rollout),
        "--reviewer-session-id",
        "reviewer-id",
        "--implementer-session-id",
        "coordinator-parent",
        "--sessions-root",
        str(sessions),
    ]) == 0
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["prefix_sha256"] == result["prefix_sha256"]


def test_preflight_rejects_inherited_duplicate_session_metadata(workflow_case, tmp_path: Path):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    rollout = _rollout(root, sessions, graph.snapshot(root, ["code.py"]), include_final=False)
    metadata = {
        "session_id": "coordinator-parent",
        "id": "reviewer-id",
        "cwd": str(root),
        "source": {"subagent": {"thread_spawn": {"agent_nickname": "reviewer"}}},
    }
    with rollout.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"type": "session_meta", "payload": metadata}, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match="duplicate session metadata") as failure:
        review_execution.preflight_review(
            root,
            rollout,
            reviewer_session_id="reviewer-id",
            implementer_session_id="coordinator-parent",
            sessions_root=sessions,
        )
    assert getattr(failure.value, "code", None) == "duplicate_session_metadata"


def test_preflight_rejects_wrong_identity_and_self_review(workflow_case, tmp_path: Path):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    rollout = _rollout(root, sessions, graph.snapshot(root, ["code.py"]), include_final=False)

    with pytest.raises(ValueError, match="explicit reviewer identity"):
        review_execution.preflight_review(
            root,
            rollout,
            reviewer_session_id="wrong-reviewer",
            implementer_session_id="coordinator-parent",
            sessions_root=sessions,
        )
    with pytest.raises(ValueError, match="differ from implementer"):
        review_execution.preflight_review(
            root,
            rollout,
            reviewer_session_id="reviewer-id",
            implementer_session_id="reviewer-id",
            sessions_root=sessions,
        )


def test_preflight_rejects_changed_or_malformed_transcript(workflow_case, tmp_path: Path):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    hashes = graph.snapshot(root, ["code.py"])
    rollout = _rollout(root, sessions, hashes, include_final=False)
    captured = review_execution.preflight_review(
        root,
        rollout,
        reviewer_session_id="reviewer-id",
        implementer_session_id="coordinator-parent",
        sessions_root=sessions,
    )
    original = rollout.read_bytes()
    rollout.write_bytes(original.replace(b"reviewer-id", b"reviewer-ix", 1))
    with pytest.raises(ValueError, match="prefix changed"):
        review_execution.preflight_review(
            root,
            rollout,
            reviewer_session_id="reviewer-id",
            implementer_session_id="coordinator-parent",
            sessions_root=sessions,
            prefix_bytes=captured["prefix_bytes"],
            prefix_sha256=captured["prefix_sha256"],
        )

    malformed = _rollout(root, sessions / "malformed", hashes, include_final=False)
    with malformed.open("a", encoding="utf-8") as stream:
        stream.write("{not-json}\n")
    with pytest.raises(ValueError, match="invalid JSON"):
        review_execution.preflight_review(
            root,
            malformed,
            reviewer_session_id="reviewer-id",
            implementer_session_id="coordinator-parent",
            sessions_root=sessions / "malformed",
        )


def test_preflight_does_not_weaken_final_response_requirement(workflow_case, tmp_path: Path):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    rollout = _rollout(root, sessions, graph.snapshot(root, ["code.py"]), include_final=False)
    review_execution.preflight_review(
        root,
        rollout,
        reviewer_session_id="reviewer-id",
        implementer_session_id="coordinator-parent",
        sessions_root=sessions,
    )
    with pytest.raises(ValueError, match="final response"):
        review_execution.build_review(root, rollout, ["code.py"], "review.json", sessions_root=sessions)


def test_preflight_cli_reports_specific_nonzero_error(workflow_case, tmp_path: Path, capsys):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    rollout = _rollout(root, sessions, graph.snapshot(root, ["code.py"]), include_final=False)
    result = review_execution.main([
        "preflight",
        "--root",
        str(root),
        "--rollout",
        str(rollout),
        "--reviewer-session-id",
        "wrong-reviewer",
        "--implementer-session-id",
        "coordinator-parent",
        "--sessions-root",
        str(sessions),
    ])
    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False
    assert error["code"] == "reviewer_identity_mismatch"


def _reviewer_json(root: Path, file_hashes: dict[str, str], *, verdict: str = "approved", name: str = "reviewer-final.json") -> Path:
    path = root / name
    path.write_text(json.dumps({
        "verdict": verdict,
        "file_hashes": file_hashes,
        "findings": [],
        "tests": [{"command": "pixi run pytest -q", "exit_status": 0}],
        "limits": ["workflow review only"],
    }, indent=2) + "\n", encoding="utf-8")
    return path


def _import(root: Path, report: Path, **changes):
    arguments = {
        "reviewer_session_id": "claude-reviewer",
        "implementer_session_id": "worker-tab",
        "receipt_path": "artifacts/review.json",
    } | changes
    return review_execution.import_external_review(root, report, **arguments)


def test_import_json_writes_hash_bound_report_and_rollout_shaped_adapter(workflow_case, tmp_path: Path, capsys):
    root, _ = workflow_case
    hashes = graph.snapshot(root, ["code.py"])
    source = _reviewer_json(root, hashes)
    assert review_execution.main([
        "import-json", "--root", str(root), "--report", str(source),
        "--reviewer-session-id", "claude-reviewer", "--implementer-session-id", "worker-tab",
        "--receipt", "artifacts/review.json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True and result["review_transport"] == "external_json"
    receipt = json.loads((root / "artifacts/review.json").read_text())
    report = json.loads((root / "artifacts/review.report.json").read_text())
    assert result["receipt"]["path"] == "artifacts/review.json"
    assert result["report"] == receipt["review_report"] == {"path": "artifacts/review.report.json",
                                                             "sha256": graph.digest((root / "artifacts/review.report.json").read_bytes())}
    # The adapter mirrors the rollout path's adapter key for key.
    assert set(receipt) == {"authority", "kind", "unit_id", "producer", "reviewer_session_id", "verdict",
                            "file_hashes", "review_report", "evidence"}
    assert receipt["kind"] == "review" and receipt["unit_id"] == "unit-1"
    assert receipt["producer"] == receipt["reviewer_session_id"] == "claude-reviewer"
    assert receipt["evidence"] == [receipt["review_report"]] and receipt["file_hashes"] == hashes
    assert report["schema"] == "cata_raid_review_report_v1" and report["review_transport"] == "external_json"
    assert report["reviewer_session_id"] == "claude-reviewer" and report["implementer_session_id"] == "worker-tab"
    assert report["source_report_sha256"] == graph.digest(source.read_bytes())
    assert report["tests"] == [{"command": "pixi run pytest -q", "exit_status": 0}]
    assert report["limits"] == ["workflow review only"]
    assert review_execution.verify_review(root, receipt, implementer_session_id="worker-tab") == hashes
    with pytest.raises(ValueError, match="implementer identity mismatch"):
        review_execution.verify_review(root, receipt, implementer_session_id="other-implementer")


def test_import_json_rejects_self_review_without_writing(workflow_case, capsys):
    root, _ = workflow_case
    source = _reviewer_json(root, graph.snapshot(root, ["code.py"]))
    with pytest.raises(review_execution.ReviewExecutionError, match="differ from implementer") as failure:
        _import(root, source, reviewer_session_id="worker-tab")
    assert failure.value.code == "self_review"
    assert review_execution.main([
        "import-json", "--root", str(root), "--report", str(source), "--reviewer-session-id", "same",
        "--implementer-session-id", "same", "--receipt", "artifacts/review.json",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "self_review"
    assert not (root / "artifacts").exists()


def test_import_json_rejects_stale_file_hashes(workflow_case):
    root, _ = workflow_case
    source = _reviewer_json(root, graph.snapshot(root, ["code.py"]))
    (root / "code.py").write_text("answer = 2\n", encoding="utf-8")
    with pytest.raises(review_execution.ReviewExecutionError, match="do not match current files") as failure:
        _import(root, source)
    assert failure.value.code == "stale_file_hashes"
    missing = _reviewer_json(root, {"gone.py": "0" * 64}, name="missing.json")
    with pytest.raises(review_execution.ReviewExecutionError, match="new review") as failure:
        _import(root, missing)
    assert failure.value.code == "stale_file_hashes"
    assert not (root / "artifacts").exists()


@pytest.mark.parametrize("verdict", ["changes_requested", "rejected", "APPROVED", ""])
def test_import_json_rejects_unsupported_verdicts(workflow_case, verdict):
    root, _ = workflow_case
    source = _reviewer_json(root, graph.snapshot(root, ["code.py"]), verdict=verdict)
    with pytest.raises(review_execution.ReviewExecutionError, match="verdict") as failure:
        _import(root, source)
    assert failure.value.code in {"verdict_unsupported", "verdict_missing"}
    assert not (root / "artifacts").exists()


def test_import_json_rejects_tampered_report_content(workflow_case):
    root, _ = workflow_case
    source = _reviewer_json(root, graph.snapshot(root, ["code.py"]))
    _import(root, source)
    receipt = json.loads((root / "artifacts/review.json").read_text())
    report = json.loads((root / "artifacts/review.report.json").read_text())
    report["findings"] = [{"severity": "info", "text": "inserted after review"}]
    forged = root / "artifacts/forged.report.json"
    forged.write_text(json.dumps(report), encoding="utf-8")
    ref = {"path": "artifacts/forged.report.json", "sha256": graph.digest(forged.read_bytes())}
    with pytest.raises(ValueError, match="source hash"):
        review_execution.verify_review(root, receipt | {"review_report": ref, "evidence": [ref]})


def test_import_json_adapter_passes_graph_review_stage(workflow_case):
    from tools.raid_program import workflow_step

    root, tests_ref = workflow_case
    workflow_step.apply_step(root, tests_ref["path"], owner="worker-tab")
    state = json.loads((root / graph.STATE_PATH).read_text())["development_graph"]
    assert state["stage"] == "review" and state["implementer"] == "worker-tab"
    hashes = graph.snapshot(root, ["code.py"])

    rejected = _import(root, _reviewer_json(root, hashes, verdict="changes_required", name="rejected.json"),
                       receipt_path="artifacts/rejected-review.json")
    assert rejected["verdict"] == "changes_required"
    with pytest.raises(graph.GraphError, match="independent approving reviewer"):
        workflow_step.apply_step(root, rejected["receipt"]["path"], dry_run=True)

    wrong = _import(root, _reviewer_json(root, hashes, name="wrong.json"), implementer_session_id="someone-else",
                    receipt_path="artifacts/wrong-implementer-review.json")
    with pytest.raises(graph.GraphError, match="implementer identity mismatch"):
        workflow_step.apply_step(root, wrong["receipt"]["path"], dry_run=True)

    approved = _import(root, _reviewer_json(root, hashes))
    preview = workflow_step.apply_step(root, approved["receipt"]["path"], dry_run=True)
    assert preview["from_stage"] == "review" and preview["to_stage"] != "review"
    result = workflow_step.apply_step(root, approved["receipt"]["path"])
    assert result["stage"] == preview["to_stage"]
