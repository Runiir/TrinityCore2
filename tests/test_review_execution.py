"""Tests for rollout-backed independent review receipts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.raid_program import development_graph as graph
from tools.raid_program import review_execution

from test_workflow_step import workflow_case


def _rollout(root: Path, sessions_root: Path, file_hashes: dict[str, str], *, reviewer: str = "reviewer-id") -> Path:
    path = sessions_root / "2026" / "09" / "21" / "rollout-review.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    final = {
        "verdict": "approved",
        "file_hashes": file_hashes,
        "findings": [],
        "tests": [{"command": "pixi run pytest -q", "exit_status": 0}],
        "limits": ["workflow review only"],
    }
    metadata = {
        "session_id": "coordinator-parent",
        "id": reviewer,
        "cwd": str(root),
        "source": {"subagent": {"thread_spawn": {"agent_nickname": "reviewer"}}},
    }
    lines = [
        {"type": "session_meta", "payload": metadata},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": json.dumps(final, sort_keys=True)}],
            },
        },
    ]
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
