import json
from pathlib import Path
import subprocess
import pytest

from tools.raid_program import worker_precommit
from tools.raid_program.worker_precommit import staged_checkpoint, main


def test_review_binds_staged_bytes_and_never_unstaged_edits(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])
    git("init", "-q")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "base")
    source = root / "repair.cpp"
    source.write_text("int staged = 1;\n")
    git("add", "repair.cpp")
    source.write_text("int unstaged = 2;\n")
    task = {"task_id": "repair", "allowed_files": ["repair.cpp"], "changed_files": ["false.cpp"]}
    output = tmp_path / "review"
    checkpoint = staged_checkpoint(root, task, output)
    assert checkpoint["changed_files"] == ["repair.cpp"]
    assert "staged = 1" in checkpoint["evidence_excerpts"][0]["text"]
    assert "unstaged = 2" not in checkpoint["evidence_excerpts"][0]["text"]
    manifest = json.loads((output / "index.json").read_text())
    assert manifest["index_tree"] == git("write-tree").decode().strip()
    assert not manifest["unstaged_changes_included"]


def test_outside_task_scope_blocks_before_model_call(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "unowned.cpp").write_text("int value;\n")
    subprocess.run(["git", "-C", str(root), "add", "unowned.cpp"], check=True)
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"allowed_files": ["owned.cpp"]}))
    monkeypatch.chdir(root)
    assert main(["--task", str(task), "--prepare-only"]) == 1
    assert "BLOCKED" in capsys.readouterr().out


@pytest.mark.parametrize("mutation", ["task", "index", "head"])
def test_changed_review_identity_is_rejected(tmp_path, monkeypatch, capsys, mutation):
    root = tmp_path / "repo"
    root.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])
    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("commit", "--allow-empty", "-qm", "base")
    source = root / "repair.cpp"
    source.write_text("int staged;\n")
    git("add", "repair.cpp")
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"allowed_files": ["repair.cpp"]}))
    def review(checkpoint, output, **kwargs):
        output.mkdir()
        (output / "examples.jsonl").write_text("")
        if mutation == "task":
            task.write_text('{}')
        elif mutation == "head":
            git("commit", "--allow-empty", "-qm", "concurrent")
        else:
            source.write_text("int changed;\n")
            git("add", "repair.cpp")
        return {"deterministic": {"status": "pass"}}
    monkeypatch.chdir(root)
    monkeypatch.setattr(worker_precommit, "review_checkpoint", review)
    assert main(["--task", str(task), "--output", str(tmp_path / "review"), "--model-advice"]) == 1
    assert "BLOCKED" in capsys.readouterr().out


def test_default_commit_does_not_call_a_model(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])
    git("init", "-q")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "base")
    (root / "repair.cpp").write_text("int staged;\n")
    git("add", "repair.cpp")
    task = tmp_path / "task.json"
    task.write_text(json.dumps({
        "task_id": "fixture", "objective": "fixture", "first_broken_edge": "fixture",
        "allowed_files": ["repair.cpp"], "forbidden_changes": [], "acceptance_conditions": [],
        "observations": [], "evidence_excerpts": [], "proposed_change": "fixture",
        "acceptance_claim": "none", "stage": "result", "changed_files": [],
        "tests": [], "required_test_commands": [],
    }))
    monkeypatch.chdir(root)
    monkeypatch.setattr(worker_precommit, "review_checkpoint", lambda *a, **k: pytest.fail("network review must be opt-in"))
    assert main(["--task", str(task), "--output", str(tmp_path / "review")]) == 0


def _unit_repo(tmp_path, stage, **graph_fields):
    from tools.raid_program import development_graph as graph
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    state = root / graph.STATE_PATH
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"development_graph": {"stage": stage, "unit": {"id": "u1", "risk_tier": "profile"},
        "assignment": {"owned_files": ["sql/rotation.sql"]}, **graph_fields}}))
    return root


def _stage(root, *paths):
    for path in paths:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        if not (root / path).exists():
            (root / path).write_text("x\n")
        subprocess.run(["git", "-C", str(root), "add", "-f", path], check=True)


def test_coordinator_commit_without_task_is_silent(tmp_path, monkeypatch, capsys):
    from tools.raid_program import development_graph as graph
    root = _unit_repo(tmp_path, "implement")
    _stage(root, str(graph.STATE_PATH), "docs/bot_raids/note.md", "sql/rotation.sql")
    monkeypatch.chdir(root)
    assert main([]) == 0
    assert capsys.readouterr().out == ""
    (root / graph.STATE_PATH).unlink()  # no graph at all: still silent
    assert main([]) == 0 and capsys.readouterr().out == ""


@pytest.mark.parametrize("state", ["{}", "not json", '{"development_graph": {"stage": "implement", "unit": {"id": "u1"}, "assignment": {"owned_files": 7}}}'])
def test_unreadable_graph_state_never_breaks_the_hook(tmp_path, monkeypatch, capsys, state):
    from tools.raid_program import development_graph as graph
    root = _unit_repo(tmp_path, "implement")
    _stage(root, "src/server/game/Bots/Other.cpp")
    (root / graph.STATE_PATH).write_text(state)
    monkeypatch.chdir(root)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Worker checkpoint: unit notice skipped (") and out.count("\n") == 1


def test_implementing_unit_warns_about_code_outside_owned_files(tmp_path, monkeypatch, capsys):
    root = _unit_repo(tmp_path, "implement")
    _stage(root, "src/server/game/Bots/Other.cpp")
    monkeypatch.chdir(root)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Unit u1 (profile, implement)" in out and "src/server/game/Bots/Other.cpp" in out
    assert "NOT REVIEWED" not in out


def test_code_after_tests_warns_with_remaining_tier_steps(tmp_path, monkeypatch, capsys):
    root = _unit_repo(tmp_path, "validate")
    _stage(root, "sql/rotation.sql")
    monkeypatch.chdir(root)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "(profile, validate)" in out and "validate -> assess -> publish -> route" in out
