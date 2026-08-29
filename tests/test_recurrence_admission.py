from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from tools.raid_program.recurrence_admission import (
    RecurrenceAdmissionError,
    create_recurrence_admission,
    sha256_file,
    verify_recurrence_admission,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    tracked = root / "tracked.txt"
    tracked.write_text("identity\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "identity")

    binary = tmp_path / "worldserver"
    build_receipt = tmp_path / "build.json"
    route = tmp_path / "route.json"
    config = tmp_path / "worldserver.conf"
    ledger = tmp_path / "ledger.json"
    decision = tmp_path / "decision.json"
    suite = tmp_path / "suite.json"
    binary.write_bytes(b"\x7fELFtest")
    _write_json(
        build_receipt,
        {
            "classification": "success",
            "exit_code": 0,
            "commit": _git(root, "rev-parse", "HEAD"),
            "output_artifacts": [
                {
                    "kind": "worldserver_elf",
                    "path": str(binary.resolve()),
                    "sha256": sha256_file(binary),
                    "produced_by_ticket": True,
                }
            ],
        },
    )
    _write_json(route, {"scenario_id": "blackwing_descent_10n_magmaw_diagnostic"})
    config.write_text(
        f'BotWorld.ValidationRoute.ManifestPath = "{route}"\n', encoding="utf-8"
    )
    _write_json(ledger, {"schema": "ledger"})
    clear_lists = {
        "invalidated_fixture_ids": [],
        "failing_fixture_ids": [],
        "missing_fixture_ids": [],
        "stale_fixture_ids": [],
    }
    _write_json(
        decision,
        {"build_admitted": True, "canary_admitted": True, **clear_lists},
    )
    _write_json(
        suite,
        {
            "schema": "trinity_raid_regression_suite_receipt_v1",
            "source_identity": _git(root, "rev-parse", "HEAD"),
            "verifications": [
                {
                    "fixture_id": "magmaw_parasite_control_full_runtime_v1",
                    "fixture_revision": 4,
                    "passed": True,
                }
            ],
        },
    )
    bindings = {}
    for name, path in {
        "binary": binary,
        "build_receipt": build_receipt,
        "runtime_config": config,
        "route_manifest": route,
        "ledger": ledger,
        "decision": decision,
        "suite_receipt": suite,
    }.items():
        bindings[name] = {"path": str(path.resolve()), "sha256": sha256_file(path)}
    admission = tmp_path / "admission.json"
    _write_json(
        admission,
        {
            "schema": "cata_raid_recurrence_admission_v1",
            "build_admitted": True,
            "canary_admitted": True,
            **clear_lists,
            "source": {
                "commit": _git(root, "rev-parse", "HEAD"),
                "tree": _git(root, "rev-parse", "HEAD^{tree}"),
                "porcelain_sha256": hashlib.sha256(b"").hexdigest(),
            },
            "bindings": bindings,
            "fixture_revisions": {
                "magmaw_parasite_control_full_runtime_v1": 4,
            },
        },
    )
    return {
        "root": root,
        "binary": binary,
        "build_receipt": build_receipt,
        "config": config,
        "admission": admission,
        "route": route,
        "ledger": ledger,
        "decision": decision,
        "suite": suite,
    }


def _verify(paths: dict[str, Path | str]) -> dict[str, object]:
    admission = Path(paths["admission"])
    return verify_recurrence_admission(
        admission_path=admission,
        expected_sha256=sha256_file(admission),
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=Path(paths["config"]),
    )


def test_exact_recurrence_admission_passes(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    assert _verify(paths)["valid"] is True


def test_creator_seals_a_verifiable_admission(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    admission.unlink()

    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=Path(paths["config"]),
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=Path(paths["decision"]),
        suite_receipt=Path(paths["suite"]),
    )

    assert _verify(paths)["valid"] is True


def test_recurrence_admission_rejects_wrong_hash(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    with pytest.raises(RecurrenceAdmissionError, match="admission_hash_mismatch"):
        verify_recurrence_admission(
            admission_path=Path(paths["admission"]),
            expected_sha256="0" * 64,
            worktree=Path(paths["root"]),
            binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]),
            runtime_config=Path(paths["config"]),
        )


def test_recurrence_admission_rejects_missing_file(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    with pytest.raises(RecurrenceAdmissionError, match="admission_missing"):
        verify_recurrence_admission(
            admission_path=tmp_path / "missing.json",
            expected_sha256="0" * 64,
            worktree=Path(paths["root"]),
            binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]),
            runtime_config=Path(paths["config"]),
        )


def test_recurrence_admission_rejects_new_head(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    root = Path(paths["root"])
    (root / "tracked.txt").write_text("new identity\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "new identity")

    with pytest.raises(RecurrenceAdmissionError, match="source_identity_stale"):
        _verify(paths)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("canary_admitted", False, "canary_not_admitted"),
        (
            "invalidated_fixture_ids",
            ["magmaw_parasite_control_full_runtime_v1"],
            "invalidated_fixture_ids_present",
        ),
    ],
)
def test_recurrence_admission_rejects_closed_gate(
    tmp_path: Path, field: str, value: object, reason: str
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    value_json = json.loads(admission.read_text(encoding="utf-8"))
    value_json[field] = value
    _write_json(admission, value_json)

    with pytest.raises(RecurrenceAdmissionError, match=reason):
        _verify(paths)
