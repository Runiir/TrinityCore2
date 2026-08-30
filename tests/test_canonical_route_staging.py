from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

import tools.raid_program.canonical_route_staging as staging
import tools.raid_program.chainwielder_prestart_bundle as prestart_bundle


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _manifest_bytes(rows: list[dict[str, str]]) -> bytes:
    return json.dumps(
        rows, sort_keys=True, separators=(",", ":")
    ).encode()


def _write_lock(
    root: Path, *, stage_name: str, output_path: str, digest: str
) -> None:
    (root / "dvc.lock").write_text(
        "schema: '2.0'\nstages:\n"
        f"  {stage_name}:\n    outs:\n"
        f"    - path: {output_path}\n"
        f"      hash: md5\n      md5: {digest}\n",
        encoding="utf-8",
    )


def _replace_manifest(
    fixture: dict[str, object], rows: list[dict[str, str]]
) -> None:
    root = fixture["root"]
    manifest = _manifest_bytes(rows)
    digest = hashlib.md5(
        manifest, usedforsecurity=False
    ).hexdigest() + ".dir"
    cache = root / ".dvc/cache/files/md5" / digest[:2] / digest[2:]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(manifest)
    _write_lock(
        root,
        stage_name=fixture["stage_name"],
        output_path=fixture["output_path"],
        digest=digest,
    )
    _git(root, "add", "dvc.lock")
    _git(root, "commit", "-m", "update locked manifest")


def _fixture(
    tmp_path: Path, *, stage_name: str = "raid_routes",
    output_path: str = "dataset/raid_routes",
    member: str = "routes.jsonl",
) -> dict[str, object]:
    root = tmp_path / "source"
    route = root / output_path / member
    route.parent.mkdir(parents=True)
    route.write_bytes(b'{"scenario_id":"generic","routes":[]}\n')
    member_md5 = hashlib.md5(
        route.read_bytes(), usedforsecurity=False
    ).hexdigest()
    manifest = _manifest_bytes([{"md5": member_md5, "relpath": member}])
    digest = hashlib.md5(
        manifest, usedforsecurity=False
    ).hexdigest() + ".dir"
    cache = root / ".dvc/cache/files/md5" / digest[:2] / digest[2:]
    cache.parent.mkdir(parents=True)
    cache.write_bytes(manifest)
    (root / ".gitignore").write_text("/dataset/*\n", encoding="utf-8")
    (root / ".dvc/.gitignore").write_text("/cache\n", encoding="utf-8")
    (root / "dvc.yaml").write_text(
        f"stages:\n  {stage_name}:\n    outs:\n    - {output_path}\n",
        encoding="utf-8",
    )
    _write_lock(
        root, stage_name=stage_name, output_path=output_path, digest=digest
    )
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", ".gitignore", ".dvc/.gitignore", "dvc.yaml", "dvc.lock")
    _git(root, "commit", "-m", "source")
    external = tmp_path / "run"
    external.mkdir()
    return {
        "root": root,
        "route": route,
        "external": external,
        "sha256": hashlib.sha256(route.read_bytes()).hexdigest(),
        "stage_name": stage_name,
        "output_path": output_path,
        "member": member,
    }


def _stage(fixture: dict[str, object]) -> dict[str, object]:
    return staging.stage_canonical_route(
        worktree=fixture["root"],
        source_route=fixture["route"],
        expected_sha256=fixture["sha256"],
        external_run_root=fixture["external"],
        dvc_stage_name=fixture["stage_name"],
        output_relative_member=fixture["member"],
    )


def test_generic_route_staging_authenticates_dvc_and_writes_receipt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    before = fixture["route"].read_bytes()
    receipt = _stage(fixture)
    staged = Path(receipt["staged_path"])
    receipt_path = Path(receipt["receipt_path"])

    assert receipt["schema"] == staging.STAGING_RECEIPT_SCHEMA
    assert receipt["source_commit"] == _git(
        fixture["root"], "rev-parse", "HEAD"
    )
    assert staged.parent == fixture["external"].resolve()
    assert staged.read_bytes() == before == fixture["route"].read_bytes()
    assert receipt["source_sha256"] == receipt["staged_sha256"]
    assert receipt["staged_sha256"] == fixture["sha256"]
    assert hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest() == receipt["receipt_sha256"]


def test_chainwielder_public_staging_wrapper_preserves_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        stage_name="validation_scenarios",
        output_path="dataset/validation_scenarios",
        member="validation_routes.jsonl",
    )
    create_calls = 0

    def counted_create(**_values: object) -> dict[str, object]:
        nonlocal create_calls
        create_calls += 1
        return {}

    monkeypatch.setattr(prestart_bundle, "create_bundle", counted_create)
    receipt = prestart_bundle.stage_canonical_route(
        worktree=fixture["root"],
        source_route=fixture["route"],
        expected_sha256=fixture["sha256"],
        external_run_root=fixture["external"],
    )

    assert create_calls == 0
    assert receipt["schema"] == prestart_bundle.STAGING_RECEIPT_SCHEMA


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing", "source_route_location_invalid"),
        ("source_drift", "source_route_dvc_member_hash_mismatch"),
        ("caller_hash_drift", "source_route_sha256_mismatch"),
        ("dirty_yaml", "source_worktree_dirty"),
        ("cache_missing", "source_route_dvc_authority_invalid"),
        ("cache_drift", "dvc_directory_manifest_hash_mismatch"),
        ("copy_drift", "external_staging_copy_hash_mismatch"),
        ("destination_conflict", "external_staging_destination_conflict"),
        ("worktree_root", "external_staging_root_invalid"),
        ("symlink_root", "external_staging_root_invalid"),
    ],
)
def test_generic_route_staging_preserves_fail_closed_rejections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    mutation: str, reason: str,
) -> None:
    fixture = _fixture(tmp_path)
    root = fixture["root"]
    if mutation == "missing":
        fixture["route"] = root / fixture["output_path"] / "missing.jsonl"
    elif mutation == "source_drift":
        fixture["route"].write_bytes(b"drift\n")
    elif mutation == "caller_hash_drift":
        fixture["sha256"] = "0" * 64
    elif mutation == "dirty_yaml":
        (root / "dvc.yaml").write_text("dirty\n", encoding="utf-8")
    elif mutation == "cache_missing":
        next((root / ".dvc/cache/files/md5").glob("*/*.dir")).unlink()
    elif mutation == "cache_drift":
        cache = next((root / ".dvc/cache/files/md5").glob("*/*.dir"))
        cache.write_bytes(cache.read_bytes() + b" ")
    elif mutation == "copy_drift":
        monkeypatch.setattr(
            staging,
            "_copy_exact",
            lambda _source, destination: destination.write_bytes(b"drift"),
        )
    elif mutation == "destination_conflict":
        route = fixture["route"]
        expected = fixture["sha256"]
        (fixture["external"] / f"{route.stem}-{expected}{route.suffix}").write_bytes(
            b"occupied"
        )
    elif mutation == "worktree_root":
        fixture["external"] = root / "external"
        fixture["external"].mkdir()
    elif mutation == "symlink_root":
        alias = tmp_path / "run-alias"
        alias.symlink_to(fixture["external"], target_is_directory=True)
        fixture["external"] = alias

    with pytest.raises(staging.CanonicalRouteStagingError, match=reason):
        _stage(fixture)


def test_dirty_tracked_dvc_lock_rejects_directly(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    lock = fixture["root"] / "dvc.lock"
    lock.write_text(lock.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")

    with pytest.raises(
        staging.CanonicalRouteStagingError, match="source_worktree_dirty"
    ):
        _stage(fixture)


def test_hash_consistent_manifest_missing_requested_member_rejects(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _replace_manifest(
        fixture,
        [{"md5": "0" * 32, "relpath": "another-route.jsonl"}],
    )

    with pytest.raises(
        staging.CanonicalRouteStagingError,
        match="source_route_dvc_member_identity_invalid",
    ):
        _stage(fixture)


def test_preexisting_destination_symlink_rejects(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    route = fixture["route"]
    destination = fixture["external"] / (
        f"{route.stem}-{fixture['sha256']}{route.suffix}"
    )
    destination.symlink_to(tmp_path / "outside-target")

    with pytest.raises(
        staging.CanonicalRouteStagingError,
        match="external_staging_destination_conflict",
    ):
        _stage(fixture)
