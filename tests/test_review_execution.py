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



@pytest.mark.parametrize("verdict", ["changes_requested", "changes_required"])
def test_rollout_path_records_either_rejection_spelling(workflow_case, tmp_path: Path, verdict):
    root, _ = workflow_case
    sessions = tmp_path / "sessions"
    rollout = _rollout(root, sessions, graph.snapshot(root, ["code.py"]), verdict=verdict)
    result = review_execution.build_review(root, rollout, ["code.py"], "review.json", sessions_root=sessions)
    assert result["verdict"] == verdict


REVIEWER = "a0123456789abcdef"


def _document(file_hashes: dict[str, str], verdict: str = "approved") -> dict:
    return {
        "verdict": verdict,
        "file_hashes": file_hashes,
        "findings": [],
        "tests": [{"command": "pixi run pytest -q", "exit_status": 0}],
        "limits": ["workflow review only"],
    }


def _reviewer_json(root: Path, document: dict, *, name: str = "reviewer-final.json") -> Path:
    path = root / name
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def _transcript(
    transcripts: Path,
    root: Path,
    final_document: dict,
    *,
    agent: str = REVIEWER,
    file_agent: str | None = None,
    trailing: list[dict] | None = None,
) -> Path:
    """Write a Claude Code subagent transcript with the observed record shape."""

    # <transcripts-root>/<project-slug>/<session-id>/subagents/agent-<id>.jsonl (+ .meta.json), as Claude Code writes it
    path = transcripts / str(root.resolve()).replace("/", "-") / "parent-session" / "subagents" / f"agent-{file_agent or agent}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".meta.json").write_text(json.dumps({"agentType": "general-purpose", "model": "opus"}))
    common = {"agentId": agent, "isSidechain": True, "cwd": str(root), "sessionId": "parent-session", "userType": "external"}
    answer = "My verdict is **approved**.\n\n```json\n" + json.dumps(final_document, indent=2) + "\n```"
    rows = [
        {"type": "user", "message": {"role": "user", "content": "Review code.py and end with the final JSON."}},
        {"type": "attachment", "attachment": {"type": "total_tokens_reminder"}},
        {"type": "assistant", "message": {"id": "msg_1", "role": "assistant", "stop_reason": "tool_use",
                                           "content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "cat code.py"}}]}},
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "answer = 1"}]}},
        {"type": "assistant", "message": {"id": "msg_2", "role": "assistant", "stop_reason": None,
                                           "content": [{"type": "thinking", "thinking": "", "signature": "x"}]}},
        {"type": "assistant", "message": {"id": "msg_2", "role": "assistant", "stop_reason": "end_turn",
                                           "content": [{"type": "text", "text": answer}]}},
        {"type": "attachment", "attachment": {"type": "total_tokens_reminder"}},
        *(trailing or []),
    ]
    path.write_text("".join(json.dumps(common | row) + "\n" for row in rows), encoding="utf-8")
    return path


@pytest.fixture
def external_case(workflow_case, tmp_path_factory):
    root, tests_ref = workflow_case
    transcripts = tmp_path_factory.mktemp("claude-projects")
    document = _document(graph.snapshot(root, ["code.py"]))
    return root, tests_ref, transcripts, document


def _import(root: Path, report: Path, transcript: Path, transcripts: Path, **changes):
    arguments = {
        "reviewer_session_id": REVIEWER,
        "implementer_session_id": "worker-tab",
        "receipt_path": "artifacts/review.json",
        "transcript_path": transcript,
        "transcripts_root": transcripts,
    } | changes
    return review_execution.import_external_review(root, report, **arguments)


def test_import_json_binds_transcript_and_writes_rollout_shaped_adapter(external_case, capsys):
    root, _, transcripts, document = external_case
    source = _reviewer_json(root, document)
    transcript = _transcript(transcripts, root, document)
    assert review_execution.main([
        "import-json", "--root", str(root), "--report", str(source),
        "--transcript", str(transcript), "--transcripts-root", str(transcripts),
        "--reviewer-session-id", REVIEWER, "--implementer-session-id", "worker-tab",
        "--receipt", "artifacts/review.json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True and result["review_transport"] == "external_json"
    receipt = json.loads((root / "artifacts/review.json").read_text())
    report = json.loads((root / "artifacts/review.report.json").read_text())
    assert result["report"] == receipt["review_report"] == {"path": "artifacts/review.report.json",
                                                             "sha256": graph.digest((root / "artifacts/review.report.json").read_bytes())}
    # The adapter mirrors the rollout path's adapter key for key.
    assert set(receipt) == {"authority", "kind", "unit_id", "producer", "reviewer_session_id", "verdict",
                            "file_hashes", "review_report", "evidence"}
    assert receipt["kind"] == "review" and receipt["unit_id"] == "unit-1"
    assert receipt["producer"] == receipt["reviewer_session_id"] == REVIEWER
    assert receipt["evidence"] == [receipt["review_report"]] and receipt["file_hashes"] == document["file_hashes"]
    assert report["review_transport"] == "external_json" and report["implementer_session_id"] == "worker-tab"
    assert report["source_report_sha256"] == graph.digest(source.read_bytes())
    assert report["source_report_path"] == str(source.resolve())
    proof = report["proof"]
    final_end = transcript.read_bytes().rfind(b'"end_turn"')
    prefix_bytes = transcript.read_bytes().index(b"\n", final_end) + 1
    assert proof["transcript_path"] == str(transcript.resolve()) and proof["session_id"] == REVIEWER
    assert proof["prefix_bytes"] == prefix_bytes < transcript.stat().st_size
    assert proof["prefix_sha256"] == graph.digest(transcript.read_bytes()[:prefix_bytes])
    assert report["tests"] == document["tests"] and report["limits"] == document["limits"]
    hashes = document["file_hashes"]
    assert review_execution.verify_review(root, receipt, implementer_session_id="worker-tab", transcripts_root=transcripts) == hashes
    with pytest.raises(ValueError, match="implementer identity mismatch"):
        review_execution.verify_review(root, receipt, implementer_session_id="other-implementer", transcripts_root=transcripts)
    # A resumed reviewer may append records; the proven prefix is unchanged.
    with transcript.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"type": "user", "agentId": REVIEWER, "isSidechain": True, "message": {"role": "user", "content": "more"}}) + "\n")
    assert review_execution.verify_review(root, receipt, transcripts_root=transcripts) == hashes


def test_forged_external_report_without_transcript_is_rejected(external_case, monkeypatch):
    from tools.raid_program import workflow_step

    root, tests_ref, transcripts, document = external_case
    monkeypatch.setattr(review_execution, "TRANSCRIPTS_ROOT", transcripts)
    workflow_step.apply_step(root, tests_ref["path"], owner="worker-tab")
    source = _reviewer_json(root, document)
    with pytest.raises(review_execution.ReviewExecutionError, match="transcript") as failure:
        _import(root, source, transcripts / "missing" / "subagents" / f"agent-{REVIEWER}.jsonl", transcripts)
    assert failure.value.code == "transcript_missing"
    # A hand-written report and adapter with a made-up reviewer id cannot advance review.
    report = {"schema": "cata_raid_review_report_v1", "reviewer_session_id": "made-up", "verdict": "approved",
              "file_hashes": document["file_hashes"], "findings": [], "review_transport": "external_json",
              "implementer_session_id": "worker-tab", "source_report_sha256": "0" * 64, "source_report_path": "x",
              "proof": {"schema": "claude_transcript_review_proof_v1", "review_transport": "external_json",
                        "session_id": "made-up", "implementer_session_id": "worker-tab", "prefix_bytes": 1,
                        "prefix_sha256": "0" * 64, "transcript_path": str(transcripts / "made-up.jsonl")}}
    (root / "forged.report.json").write_text(json.dumps(report), encoding="utf-8")
    ref = {"path": "forged.report.json", "sha256": graph.digest((root / "forged.report.json").read_bytes())}
    adapter = {"authority": "coordinator_attestation", "kind": "review", "unit_id": "unit-1", "producer": "made-up",
               "reviewer_session_id": "made-up", "verdict": "approved", "file_hashes": document["file_hashes"],
               "review_report": ref, "evidence": [ref]}
    (root / "forged.json").write_text(json.dumps(adapter), encoding="utf-8")
    with pytest.raises(graph.GraphError, match="independent review execution: reviewer transcript"):
        workflow_step.apply_step(root, "forged.json", dry_run=True)


def test_import_json_rejects_transcript_of_another_agent(external_case):
    root, _, transcripts, document = external_case
    source = _reviewer_json(root, document)
    foreign = _transcript(transcripts, root, document, agent="a-other-agent", file_agent=REVIEWER)
    with pytest.raises(review_execution.ReviewExecutionError, match="another agent") as failure:
        _import(root, source, foreign, transcripts)
    assert failure.value.code == "transcript_identity_mismatch"
    with pytest.raises(review_execution.ReviewExecutionError, match="this reviewer") as failure:
        _import(root, source, foreign, transcripts, reviewer_session_id="a-other-agent")
    assert failure.value.code == "transcript_identity_mismatch"
    assert not (root / "artifacts").exists()


def test_import_json_rejects_final_message_that_differs_from_report(external_case):
    root, _, transcripts, document = external_case
    source = _reviewer_json(root, document)
    transcript = _transcript(transcripts, root, document | {"findings": [{"severity": "high", "text": "real finding"}]})
    with pytest.raises(review_execution.ReviewExecutionError, match="does not contain this report") as failure:
        _import(root, source, transcript, transcripts)
    assert failure.value.code == "final_response_mismatch"
    assert not (root / "artifacts").exists()


def test_import_json_requires_json_to_be_the_final_answer(external_case):
    root, _, transcripts, document = external_case
    source = _reviewer_json(root, document)
    followed = {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": ""}]}}
    transcript = _transcript(transcripts, root, document, trailing=[followed])
    with pytest.raises(review_execution.ReviewExecutionError, match="after its final assistant") as failure:
        _import(root, source, transcript, transcripts)
    assert failure.value.code == "final_response_not_last"


@pytest.mark.parametrize("mutation", ["edit", "truncate"])
def test_tampered_transcript_fails_verification(external_case, mutation):
    root, _, transcripts, document = external_case
    transcript = _transcript(transcripts, root, document)
    _import(root, _reviewer_json(root, document), transcript, transcripts)
    receipt = json.loads((root / "artifacts/review.json").read_text())
    original = transcript.read_bytes()
    if mutation == "edit":
        transcript.write_bytes(original.replace(b"cat code.py", b"cat code.px", 1))
    else:
        transcript.write_bytes(original[: original.rfind(b'"end_turn"')])
    with pytest.raises(ValueError, match="transcript"):
        review_execution.verify_review(root, receipt, transcripts_root=transcripts)


def test_import_json_rejects_self_review_without_writing(external_case, capsys):
    root, _, transcripts, document = external_case
    source = _reviewer_json(root, document)
    transcript = _transcript(transcripts, root, document)
    with pytest.raises(review_execution.ReviewExecutionError, match="differ from implementer") as failure:
        _import(root, source, transcript, transcripts, implementer_session_id=REVIEWER)
    assert failure.value.code == "self_review"
    assert review_execution.main([
        "import-json", "--root", str(root), "--report", str(source), "--transcript", str(transcript),
        "--transcripts-root", str(transcripts), "--reviewer-session-id", REVIEWER,
        "--implementer-session-id", REVIEWER, "--receipt", "artifacts/review.json",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "self_review"
    assert not (root / "artifacts").exists()


def test_import_json_rejects_stale_file_hashes(external_case):
    root, _, transcripts, document = external_case
    source = _reviewer_json(root, document)
    transcript = _transcript(transcripts, root, document)
    (root / "code.py").write_text("answer = 2\n", encoding="utf-8")
    with pytest.raises(review_execution.ReviewExecutionError, match="do not match current files") as failure:
        _import(root, source, transcript, transcripts)
    assert failure.value.code == "stale_file_hashes"
    missing = _reviewer_json(root, _document({"gone.py": "0" * 64}), name="missing.json")
    # a reviewed file that no longer exists snapshots as "deleted" and therefore mismatches the report
    with pytest.raises(review_execution.ReviewExecutionError, match="do not match current files") as failure:
        _import(root, missing, transcript, transcripts)
    assert failure.value.code == "stale_file_hashes"
    assert not (root / "artifacts").exists()


@pytest.mark.parametrize("verdict", ["rejected", "APPROVED", "approve", ""])
def test_import_json_rejects_unsupported_verdicts(external_case, verdict):
    root, _, transcripts, document = external_case
    bad = document | {"verdict": verdict}
    with pytest.raises(review_execution.ReviewExecutionError, match="verdict") as failure:
        _import(root, _reviewer_json(root, bad), _transcript(transcripts, root, bad), transcripts)
    assert failure.value.code in {"verdict_unsupported", "verdict_missing"}
    assert not (root / "artifacts").exists()


def test_import_json_leaves_no_partial_report_on_failure(external_case):
    root, _, transcripts, document = external_case
    (root / "artifacts").mkdir()
    (root / "artifacts/review.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(review_execution.ReviewExecutionError, match="overwrite"):
        _import(root, _reviewer_json(root, document), _transcript(transcripts, root, document), transcripts)
    assert not (root / "artifacts/review.report.json").exists()
    assert (root / "artifacts/review.json").read_text() == "{}\n"


def test_import_json_rejects_tampered_report_content(external_case):
    root, _, transcripts, document = external_case
    _import(root, _reviewer_json(root, document), _transcript(transcripts, root, document), transcripts)
    receipt = json.loads((root / "artifacts/review.json").read_text())
    report = json.loads((root / "artifacts/review.report.json").read_text())
    report["findings"] = [{"severity": "info", "text": "inserted after review"}]
    forged = root / "artifacts/forged.report.json"
    forged.write_text(json.dumps(report), encoding="utf-8")
    ref = {"path": "artifacts/forged.report.json", "sha256": graph.digest(forged.read_bytes())}
    with pytest.raises(ValueError, match="does not match the review report"):
        review_execution.verify_review(root, receipt | {"review_report": ref, "evidence": [ref]}, transcripts_root=transcripts)


def test_import_json_adapter_passes_graph_review_stage(external_case, monkeypatch):
    from tools.raid_program import workflow_step

    root, tests_ref, transcripts, document = external_case
    monkeypatch.setattr(review_execution, "TRANSCRIPTS_ROOT", transcripts)
    workflow_step.apply_step(root, tests_ref["path"], owner="worker-tab")
    state = json.loads((root / graph.STATE_PATH).read_text())["development_graph"]
    assert state["stage"] == "review" and state["implementer"] == "worker-tab"

    for index, verdict in enumerate(("changes_required", "changes_requested")):
        rejected_doc = document | {"verdict": verdict}
        rejected = _import(root, _reviewer_json(root, rejected_doc, name=f"rejected{index}.json"),
                           _transcript(transcripts, root, rejected_doc, agent=f"a-rejecting-{index}"), transcripts,
                           reviewer_session_id=f"a-rejecting-{index}", receipt_path=f"artifacts/rejected-{index}.json")
        assert rejected["verdict"] == verdict
        with pytest.raises(graph.GraphError, match="independent approving reviewer"):
            workflow_step.apply_step(root, rejected["receipt"]["path"], dry_run=True)

    transcript = _transcript(transcripts, root, document)
    wrong = _import(root, _reviewer_json(root, document, name="wrong.json"), transcript, transcripts,
                    implementer_session_id="someone-else", receipt_path="artifacts/wrong-implementer-review.json")
    with pytest.raises(graph.GraphError, match="implementer identity mismatch"):
        workflow_step.apply_step(root, wrong["receipt"]["path"], dry_run=True)

    approved = _import(root, _reviewer_json(root, document), transcript, transcripts)
    preview = workflow_step.apply_step(root, approved["receipt"]["path"], dry_run=True)
    assert preview["from_stage"] == "review" and preview["to_stage"] != "review"
    result = workflow_step.apply_step(root, approved["receipt"]["path"])
    assert result["stage"] == preview["to_stage"]


def test_file_hashes_accept_deleted_for_absent_files_only(workflow_case):
    root, _ = workflow_case
    current = graph.snapshot(root, ["code.py"])
    assert review_execution._validated_file_hashes(root, current | {"gone.py": graph.DELETED}) == current | {"gone.py": graph.DELETED}
    with pytest.raises(review_execution.ReviewExecutionError):
        review_execution._validated_file_hashes(root, {"code.py": graph.DELETED})
