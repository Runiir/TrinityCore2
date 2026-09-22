"""Tests for rollout-backed independent review receipts."""

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
