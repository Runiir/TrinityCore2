"""Tests for the state-bound workflow transition adapter."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from tools.raid_program import development_graph as graph
from tools.raid_program import workflow_step


def _write(root: Path, relative: str, value: object) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": relative, "sha256": graph.digest(path.read_bytes())}


def _git(root: Path, *args: str) -> str:
    return graph.git(root, *args)


@pytest.fixture
def workflow_case(tmp_path: Path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("*.json\n", encoding="utf-8")
    (tmp_path / "code.py").write_text("answer = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", ".gitignore", "code.py"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        check=True,
    )
    evidence = _write(tmp_path, "evidence.json", {"fixture": "workflow"})
    policy_path = tmp_path / "policy.json"
    from tools.raid_program.queued_build import DEFAULT_POLICY

    policy_path.write_bytes(DEFAULT_POLICY.read_bytes())
    policy = {"path": "policy.json", "sha256": graph.digest(policy_path.read_bytes())}
    roster = _write(tmp_path, "roster.json", {"roster": "fixture"})
    runtime = _write(tmp_path, "runtime.json", {"runtime": "fixture"})
    route = _write(tmp_path, "route.json", {"route": "fixture"})
    development = {
        "version": 1,
        "coordinator_worktree": str(tmp_path),
        "revision": 0,
        "objective": "fixture workflow",
        "stage": "diagnose",
        "unit": {"id": "unit-1", "edge": "edge-1", "requirements": ["setup"], "next_action": "implement"},
        "encounter": {"raid": "fixture", "boss": "fixture", "mode": "10N"},
        "actor_ids": ["actor-1"],
        "requirements": {"setup": {"status": "open"}},
        "history": [],
        "failures": {},
    }
    state = {"development_graph": development}
    (tmp_path / graph.STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / graph.STATE_PATH).write_text(json.dumps(state) + "\n", encoding="utf-8")

    plan = {
        "authority": "coordinator_attestation",
        "kind": "plan",
        "unit_id": "unit-1",
        "producer": "coordinator",
        "evidence": [evidence],
        "advice": {
            "jev": {"status": "not_reviewed", "reason": "fixture", "adjudication": "local test"},
            "laya": {"status": "not_reviewed", "reason": "fixture", "adjudication": "local test"},
        },
        "hypothesis": "fixture hypothesis",
        "owned_files": ["code.py"],
        "forbidden_changes": ["no unrelated change"],
        "acceptance_conditions": ["focused test passes"],
        "required_test_commands": ["pixi run pytest -q tests/test_fixture.py"],
        "base_commit": _git(tmp_path, "rev-parse", "HEAD"),
        "policy": policy,
        "validation_identity": {
            "scenario_kind": "raid",
            "encounter": development["encounter"],
            "roster": roster,
            "runtime_profile": runtime,
            "route": route,
        },
    }
    plan_ref = _write(tmp_path, "plan.json", plan)
    plan_event = {"revision": 0, "unit_id": "unit-1", "action": "advance", "receipt": plan_ref}
    graph.advance(tmp_path, plan_event, graph.digest((tmp_path / graph.STATE_PATH).read_bytes()))
    state = json.loads((tmp_path / graph.STATE_PATH).read_text())
    claim_event = {"revision": 1, "unit_id": "unit-1", "action": "claim", "owner": "worker-tab"}
    graph.advance(tmp_path, claim_event, graph.digest((tmp_path / graph.STATE_PATH).read_bytes()))
    state = json.loads((tmp_path / graph.STATE_PATH).read_text())
    claim = state["development_graph"]["claim"]
    tests_receipt = {
        "authority": "coordinator_attestation",
        "kind": "tests",
        "unit_id": "unit-1",
        "producer": "worker-tab",
        "evidence": [evidence],
        "file_hashes": graph.snapshot(tmp_path, ["code.py"]),
        "tests": [{"command": "pixi run pytest -q tests/test_fixture.py", "exit_status": 0}],
        "advice": plan["advice"],
        "operation_id": claim["operation_id"],
    }
    tests_ref = _write(tmp_path, "tests-receipt.json", tests_receipt)
    return tmp_path, tests_ref


def test_wrong_claim_owner_cannot_obtain_token(workflow_case):
    root, receipt = workflow_case
    before = (root / graph.STATE_PATH).read_bytes()
    with pytest.raises(graph.GraphError, match="claim owner mismatch"):
        workflow_step.apply_step(root, receipt["path"], owner="other-tab")
    assert (root / graph.STATE_PATH).read_bytes() == before


def test_stale_expected_state_preserves_state(workflow_case):
    root, receipt = workflow_case
    stale = graph.digest((root / graph.STATE_PATH).read_bytes())
    changed = json.loads((root / graph.STATE_PATH).read_text())
    changed["note"] = "concurrent writer"
    (root / graph.STATE_PATH).write_text(json.dumps(changed) + "\n", encoding="utf-8")
    before = (root / graph.STATE_PATH).read_bytes()
    with pytest.raises(graph.GraphError, match="state changed"):
        workflow_step.apply_step(root, receipt["path"], owner="worker-tab", expected_sha256=stale)
    assert (root / graph.STATE_PATH).read_bytes() == before


def test_reducer_failure_preserves_state(workflow_case):
    root, receipt = workflow_case
    broken = json.loads((root / receipt["path"]).read_text())
    broken["operation_id"] = "stale-operation"
    broken_ref = _write(root, "broken-receipt.json", broken)
    before = (root / graph.STATE_PATH).read_bytes()
    with pytest.raises(graph.GraphError, match="operation identity"):
        workflow_step.apply_step(root, broken_ref["path"], owner="worker-tab")
    assert (root / graph.STATE_PATH).read_bytes() == before


def test_dry_run_validates_real_reducer_without_writing(workflow_case):
    root, receipt = workflow_case
    before = (root / graph.STATE_PATH).read_bytes()
    preview = workflow_step.apply_step(root, receipt["path"], owner="worker-tab", dry_run=True)
    assert preview["dry_run"] is True
    assert preview["from_stage"] == "implement"
    assert preview["to_stage"] == "review"
    assert (root / graph.STATE_PATH).read_bytes() == before


def test_successful_transition_matches_reducer(workflow_case):
    root, receipt = workflow_case
    event, _, state = workflow_step.prepare_event(root, receipt["path"], owner="worker-tab")
    expected = graph.reduce(root, copy.deepcopy(state), event)
    result = workflow_step.apply_step(root, receipt["path"], owner="worker-tab")
    saved = json.loads((root / graph.STATE_PATH).read_text())
    assert saved["development_graph"] == expected["development_graph"]
    assert result["stage"] == "review"
    assert result["revision"] == expected["development_graph"]["revision"]
    assert result["state_sha256"] == graph.digest((root / graph.STATE_PATH).read_bytes())


def test_refresh_support_event_uses_current_claim_token(workflow_case):
    root, _ = workflow_case
    reconciliation = _write(root, "refresh.json", {"fixture": "reconciliation"})
    event, _, state = workflow_step.prepare_event(root, reconciliation["path"], owner="worker-tab", action="refresh_support")
    assert event["action"] == "refresh_support"
    assert event["revision"] == state["development_graph"]["revision"]
    assert event["unit_id"] == "unit-1"
    assert event["claim_token"] == state["development_graph"]["claim"]["token"]
