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
    assert main(["--task", str(task), "--output", str(tmp_path / "review")]) == 1
    assert "BLOCKED" in capsys.readouterr().out
