from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest
import yaml

from tools.raid_program.runtime_asset_closure import (
    _verify_extraction_provenance,
    build_native_inventory_authority,
)
from tools.raid_program.runtime_asset_closure_binding import (
    _materialize_input_manifest,
)
from tools.raid_program.runtime_asset_materialization import (
    DvcTransportRequest,
    DvcTransportResult,
    MaterializationError,
    _extract_and_verify_archive,
    build_materialization_requirement,
    publish_and_reconstruct_dvc,
    produce_verified_materialization_receipt,
)


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _write_json(path: Path, value: object) -> None:
    _write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def _fixture(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "data": tmp_path / "data",
        "dvc": tmp_path / "dvc",
        "reconstruction": tmp_path / "reconstruction",
    }
    paths["data"].mkdir()
    paths["dvc"].mkdir()
    _write(paths["data"] / "dbc/enUS/Map.dbc", b"dbc")
    _write(paths["data"] / "maps/669.map", b"map")
    authority = build_native_inventory_authority(
        data_dir=paths["data"], source_audit_sha256="a" * 64,
        audit_source_inventory_sha256="b" * 64,
        audit_vmaps_inventory_sha256="c" * 64,
        receipt_relative_path="absent-materialization-receipt.json",
    )
    paths["authority"] = paths["dvc"] / "native-inventory.json"
    paths["archive"] = paths["dvc"] / "native-data.tar"
    paths["pointer"] = paths["dvc"] / "native-data.tar.dvc"
    paths["receipt"] = paths["dvc"] / "native-data.materialization.json"
    _write_json(paths["authority"], authority)
    return paths


def _fake_transport(
    mutate_download=None, mutate_source=None, omit_download: bool = False,
):
    def transport(request: DvcTransportRequest) -> DvcTransportResult:
        payload = request.archive_path.read_bytes()
        pointer = {
            "outs": [{
                "md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                "size": len(payload), "hash": "md5",
                "path": request.archive_path.name,
            }],
        }
        _write(request.pointer_path, yaml.safe_dump(pointer, sort_keys=False).encode())
        workspace = request.reconstruction_root / "workspace"
        workspace.mkdir()
        downloaded = workspace / request.archive_path.name
        if not omit_download:
            shutil.copyfile(request.archive_path, downloaded)
            if mutate_download:
                mutate_download(downloaded)
        _write(request.reconstruction_root / "cache/object", b"remote-object")
        if mutate_source:
            mutate_source()
        commands = tuple(
            {"argv": ["dvc", verb, argument], "cwd": str(request.dvc_workspace)}
            for verb, argument in (
                ("add", request.archive_path.name),
                ("push", request.pointer_path.name),
                ("pull", request.pointer_path.name),
            )
        )
        return DvcTransportResult(
            pointer_path=request.pointer_path,
            downloaded_archive_path=downloaded,
            commands=commands,
            isolated_cache_path=request.reconstruction_root / "cache",
        )
    return transport


def _produce(paths: dict[str, Path], transport=None) -> dict:
    return produce_verified_materialization_receipt(
        data_dir=paths["data"],
        inventory_authority_path=paths["authority"],
        archive_path=paths["archive"], dvc_workspace=paths["dvc"],
        pointer_path=paths["pointer"],
        reconstruction_root=paths["reconstruction"],
        receipt_path=paths["receipt"],
        creation_command_inputs=[{
            "argv": ["pixi", "run", "python", "-m", "producer"],
            "cwd": str(paths["dvc"]),
        }],
        dvc_transport=transport or _fake_transport(),
    )


def _requirement(paths: dict[str, Path], receipt: dict) -> dict:
    return {
        "kind": "verified_materialization", "root": "dvc-workspace",
        "path": paths["receipt"].relative_to(paths["dvc"]).as_posix(),
        "receipt_sha256": hashlib.sha256(paths["receipt"].read_bytes()).hexdigest(),
        "historical_extraction_origin": "unknown",
        "inventory_authority_sha256": receipt["inventory_authority_sha256"],
        "archive_sha256": receipt["archive"]["sha256"],
        "dvc_content_address": receipt["dvc"]["content_address"],
        "creation_command_inputs": receipt["creation_command_inputs"],
    }


def test_producer_proves_remote_reconstruction_and_closure_binding(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    receipt = _produce(paths)
    requirement = _requirement(paths, receipt)
    assert build_materialization_requirement(paths["receipt"], paths["dvc"]) == requirement
    authority = json.loads(paths["authority"].read_text())
    issues, observed = _verify_extraction_provenance(
        {"native_extraction_provenance": requirement},
        {"configured-DataDir": paths["data"], "dvc-workspace": paths["dvc"]},
        authority, receipt["inventory_authority_sha256"],
    )
    assert issues == []
    assert observed is not None
    assert observed["historical_extraction_origin"] == "unknown"
    assert observed["remote_reconstruction"]["reconstructed_inventory"] == receipt[
        "source_inventory"
    ]

    paths["pointer"].unlink()
    issues, _observed = _verify_extraction_provenance(
        {"native_extraction_provenance": requirement},
        {"configured-DataDir": paths["data"], "dvc-workspace": paths["dvc"]},
        authority, receipt["inventory_authority_sha256"],
    )
    assert len(issues) == 1
    assert issues[0]["kind"] == "provenance_invalid"
    assert "dvc_pointer" in issues[0]["detail"]


@pytest.mark.parametrize("failure", ["corrupt", "missing"])
def test_producer_rejects_bad_remote_archive(tmp_path: Path, failure: str) -> None:
    paths = _fixture(tmp_path)
    transport = (
        _fake_transport(mutate_download=lambda path: path.write_bytes(b"corrupt"))
        if failure == "corrupt" else _fake_transport(omit_download=True)
    )
    with pytest.raises(MaterializationError):
        _produce(paths, transport)
    assert not paths["receipt"].exists()


def test_producer_rejects_source_drift(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    target = paths["data"] / "maps/669.map"
    with pytest.raises(MaterializationError, match="source_drift"):
        _produce(paths, _fake_transport(mutate_source=lambda: target.write_bytes(b"new")))
    assert not paths["receipt"].exists()


def test_producer_rejects_symlinked_source_member(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    target = paths["data"] / "maps/669.map"
    target.unlink()
    target.symlink_to(paths["data"] / "dbc/enUS/Map.dbc")
    with pytest.raises(MaterializationError, match="source_inventory_invalid:symlink"):
        _produce(paths)
    assert not paths["receipt"].exists()


def test_archive_rejects_traversal_and_unexpected_members(tmp_path: Path) -> None:
    for name, error in (("../escape", "path_invalid"), ("extra", "unexpected")):
        archive = tmp_path / f"{name.replace('/', '-')}.tar"
        with tarfile.open(archive, "w") as output:
            member = tarfile.TarInfo(name)
            member.size = 1
            output.addfile(member, __import__("io").BytesIO(b"x"))
        with pytest.raises(MaterializationError, match=error):
            _extract_and_verify_archive(
                archive_path=archive, output_dir=tmp_path / f"out-{archive.name}",
                expected_records=[],
            )


def test_input_manifest_can_override_only_with_materialization_discriminant(
    tmp_path: Path,
) -> None:
    dvc = tmp_path / "dvc"
    dvc.mkdir()
    historical = {
        "schema": "cata_runtime_asset_closure_manifest_v1",
        "asset_classes": [
            {"id": "input", "root": "configured-DataDir"},
            {"id": "atomic_bundle", "root": "sealed-bundle"},
        ],
        "dvc_provenance": {"stages": []},
        "native_extraction_provenance": {"path": "legacy", "receipt_sha256": None},
    }
    source = dvc / "historical.json"
    _write_json(source, historical)
    override = {"kind": "verified_materialization"}
    current = {
        "schema": "cata_runtime_asset_input_closure_manifest_v1",
        "asset_class_source": {
            "path": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "exclude_class_ids": ["atomic_bundle"],
        },
        "native_extraction_provenance": override,
    }
    materialized = _materialize_input_manifest(current, dvc_workspace=dvc)
    assert materialized["native_extraction_provenance"] is override
    current["native_extraction_provenance"] = {"path": "untyped"}
    with pytest.raises(ValueError, match="input_asset_class_source_field_invalid"):
        _materialize_input_manifest(current, dvc_workspace=dvc)


@pytest.mark.skipif(shutil.which("dvc") is None, reason="dvc executable unavailable")
def test_real_dvc_transport_reconstructs_from_empty_cache(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    remote = tmp_path / "remote"
    remote.mkdir()
    subprocess.run(
        ["dvc", "init", "--no-scm"], cwd=paths["dvc"], check=True,
        capture_output=True, text=True,
    )
    subprocess.run(
        ["dvc", "remote", "add", "-d", "fixture", str(remote)],
        cwd=paths["dvc"], check=True, capture_output=True, text=True,
    )
    receipt = _produce(paths, publish_and_reconstruct_dvc)
    assert receipt["remote_reconstruction"]["isolated_empty_cache"] is True
    assert any((paths["reconstruction"] / "cache").iterdir())
