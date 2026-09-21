from pathlib import Path
import subprocess

import pytest

from tools.raid_program.build_control_compatibility import coordination_path
from tools.raid_program.development_graph import GraphError, source_binding


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _commit(root: Path) -> str:
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    return _git(root, "rev-parse", "HEAD")


def test_worker_checkpoint_jsonl_is_coordination_and_not_source(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "code.cpp").write_text("source")
    artifacts = tmp_path / "artifacts/cata_raid_program/review"
    artifacts.mkdir(parents=True)
    base = _commit(tmp_path)

    output = artifacts / "examples.jsonl"
    output.write_text('{"provider":"jev"}\n')
    head = _commit(tmp_path)

    assert coordination_path("artifacts/cata_raid_program/review/examples.jsonl")
    assert not coordination_path("artifacts/cata_raid_program/review/source.cpp")
    assignment = {"base_commit": base, "owned_files": ["code.cpp"]}
    assert source_binding(tmp_path, assignment, base) == head

    source_like = artifacts / "source.cpp"
    source_like.write_text("unreviewed source")
    source_head = _commit(tmp_path)
    assert source_head != head
    with pytest.raises(GraphError, match="source delta"):
        source_binding(tmp_path, assignment, base)

    selected_base = _git(tmp_path, "rev-parse", "HEAD")
    selected = artifacts / "selected.jsonl"
    selected.write_text('{"input":true}\n')
    _commit(tmp_path)
    selected_assignment = {
        "base_commit": selected_base,
        "owned_files": ["code.cpp"],
        "validation_identity": {
            "route": {"path": "artifacts/cata_raid_program/review/selected.jsonl"}
        },
    }
    with pytest.raises(GraphError, match="source delta"):
        source_binding(tmp_path, selected_assignment, selected_base)
