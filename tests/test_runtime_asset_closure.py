from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

from tools.raid_program import capture_phase1_provisioning_readback as readback
from tools.raid_program import capture_setup
from tools.bot_ml import run_live_bot_validation as live_validation
from tools.raid_program.runtime_asset_closure import (
    _inventory,
    _record,
    _write_json,
    build_audit_authority,
    build_native_inventory_authority,
    produce_extraction_receipt,
    verify_runtime_asset_closure,
)


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MANIFEST = ROOT / "experiments/configs/runtime_asset_closure_manifest_v1.json"
NEGATIVE_FIXTURE = ROOT / "tests/fixtures/runtime_asset_closure/retained_stage3_missing_v1.json"
RETAINED = Path("/home/runiir/Games/trinity-generic-min-range-native-build.FzZB61vj/source-control-immutable")
BUNDLE = Path("/home/runiir/Games/trinity-controller-hold-identity-materialization-fast4-v2-build.5YGC4lez/run/prestart_bundle_stage3_integrated_v1")


def _write(path: Path, payload: bytes = b"fixture", mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(mode)


def _file_row(root: Path, relative: str) -> dict[str, object]:
    row, issue = _record(root / relative, root, relative)
    assert issue is None and row is not None
    return row


def _class(
    class_id: str, root: str, rule: str, *, path: str | None = None,
    expected_files: list[dict[str, object]] | None = None,
    expected_inventory: dict[str, object] | None = None,
    pattern: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "id": class_id,
        "consumer": f"{class_id} consumer",
        "audience": "test",
        "root": root,
        "rule": rule,
        "provenance": "deterministic fixture",
        "hydration_source": "fixture builder",
        "eviction_policy": "pytest temporary directory",
        "expected_files": expected_files or [],
        "audit_inventory_sha256": hashlib.sha256(class_id.encode()).hexdigest(),
    }
    if path is not None:
        value["path"] = path
    if pattern is not None:
        value["pattern"] = pattern
    if expected_inventory is not None:
        value["expected_inventory"] = expected_inventory
    return value


def _seal_authorities(paths: dict[str, Path], manifest: dict[str, object]) -> None:
    audit_path = paths["dvc"] / "source-audit.json"
    classes = []
    for raw in manifest["asset_classes"]:
        assert isinstance(raw, dict)
        values = dict(raw)
        maps = values.pop("map_contracts", None)
        if isinstance(maps, dict):
            values.update(maps["100"])
        expected_inventory = values.get("expected_inventory")
        classes.append({
            "id": values["id"],
            "count": expected_inventory["file_count"],
            "inventory_sha256": values["audit_inventory_sha256"],
        })
    audit_inventory_sha256 = "b" * 64
    source_audit = {
        "schema": "cata_raid_immutable_runtime_asset_closure_audit_v1",
        "closure_classes": classes,
        "full_data_tree_inventory": {
            "source": {"inventory_sha256": audit_inventory_sha256, "entries": 7},
        },
    }
    _write_json(audit_path, source_audit)
    audit_sha256 = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    audit_authority_path = paths["dvc"] / "audit-authority.json"
    audit_authority = build_audit_authority(
        manifest=manifest, source_audit_path=audit_path,
        source_audit_sha256=audit_sha256, scenario_map_id=100,
    )
    _write_json(audit_authority_path, audit_authority)
    audit_authority_sha256 = hashlib.sha256(audit_authority_path.read_bytes()).hexdigest()
    inventory_authority_path = paths["dvc"] / "native-inventory.json"
    vmaps_digest = next(
        (row["inventory_sha256"] for row in classes if row["id"] == "vmaps"),
        "d" * 64,
    )
    inventory_authority = build_native_inventory_authority(
        data_dir=paths["data"], source_audit_sha256=audit_sha256,
        audit_source_inventory_sha256=audit_inventory_sha256,
        audit_vmaps_inventory_sha256=vmaps_digest,
        receipt_relative_path="provenance.json",
    )
    _write_json(inventory_authority_path, inventory_authority)
    inventory_authority_sha256 = hashlib.sha256(inventory_authority_path.read_bytes()).hexdigest()
    manifest["audit_authority"] = {
        "path": "audit-authority.json", "sha256": audit_authority_sha256,
    }
    manifest["native_data_inventory_authority"] = {
        "path": "native-inventory.json", "sha256": inventory_authority_sha256,
        "audit_authority_sha256": audit_authority_sha256,
        "canonical_audit_inventory_sha256": audit_inventory_sha256,
    }
    client_identity = {"client_build": "4.3.4.15595", "source": "fixture-client"}
    extractor_identity = {"binary_sha256": "c" * 64, "name": "fixture-extractor"}
    command_inputs = ["fixture-extractor", "--all"]
    receipt = produce_extraction_receipt(
        data_dir=paths["data"], inventory_authority_path=inventory_authority_path,
        receipt_relative_path="provenance.json", client_identity=client_identity,
        extractor_identity=extractor_identity, creation_command_inputs=command_inputs,
    )
    receipt_path = paths["data"] / "provenance.json"
    _write_json(receipt_path, receipt)
    manifest["native_extraction_provenance"] = {
        "path": "provenance.json",
        "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "client_identity": client_identity,
        "extractor_identity": extractor_identity,
        "creation_command_inputs": command_inputs,
    }


def _fixture(tmp_path: Path) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    roots = {
        "source": tmp_path / "source",
        "data": tmp_path / "native-data",
        "dvc": tmp_path / "dvc",
        "bundle": tmp_path / "bundle",
    }
    for root in roots.values():
        root.mkdir()
    _write(roots["source"] / "offline/input.dbc", b"dbc")
    _write(roots["source"] / "map-assets/100.base", b"base")
    _write(roots["source"] / "map-assets/1000001.tile", b"tile")
    _write(roots["source"] / "dvc-output/value.json", b"{}\n")
    _write(roots["data"] / "vmaps/shared.vmo", b"model")
    _write(roots["data"] / "vmaps/100.vmtree", b"tree")
    _write(roots["bundle"] / "bundle.json", b"{}\n")
    dvc_lock = (
        "schema: '2.0'\nstages:\n  fixture_stage:\n    outs:\n"
        "    - path: dvc-output\n      hash: md5\n"
        "      md5: 0123456789abcdef0123456789abcdef.dir\n"
        "      size: 3\n      nfiles: 1\n"
    )
    _write(roots["dvc"] / "dvc.lock", dvc_lock.encode())
    config = tmp_path / "worldserver.conf"
    _write(config, f'DataDir = "{roots["data"]}"\n'.encode())

    exact = [_file_row(roots["source"], "offline/input.dbc")]
    bounded = [
        _file_row(roots["source"], "map-assets/100.base"),
        _file_row(roots["source"], "map-assets/1000001.tile"),
    ]
    vmaps = [
        _file_row(roots["data"], "vmaps/100.vmtree"),
        _file_row(roots["data"], "vmaps/shared.vmo"),
    ]
    bundle = [_file_row(roots["bundle"], "bundle.json")]
    dvc_output = [_file_row(roots["source"], "dvc-output/value.json")]
    manifest = {
        "schema": "cata_runtime_asset_closure_manifest_v1",
        "dvc_provenance": [{
            "class_id": "dvc_output",
            "stage": "fixture_stage",
            "output_path": "dvc-output",
            "md5": "0123456789abcdef0123456789abcdef.dir",
            "size": 3,
            "nfiles": 1,
        }],
        "asset_classes": [
            _class("exact", "source-checkout", "exact-file", expected_files=exact, expected_inventory=_inventory(exact)),
            {
                **_class("bounded", "source-checkout", "bounded-pattern", path="map-assets", expected_files=bounded, expected_inventory=_inventory(bounded)),
                "map_contracts": {"100": {"pattern": r"^100(?:\.base|[0-9]{4}\.tile)$", "expected_files": bounded, "expected_inventory": _inventory(bounded)}},
            },
            {
                **_class("vmaps", "configured-DataDir", "complete-directory", path="vmaps", expected_files=vmaps, expected_inventory=_inventory(vmaps)),
                "inventory_subset": "vmaps",
            },
            _class("bundle", "sealed-bundle", "complete-directory", path=".", expected_files=bundle, expected_inventory=_inventory(bundle)),
            _class("dvc_output", "source-checkout", "complete-directory", path="dvc-output", expected_files=dvc_output, expected_inventory=_inventory(dvc_output)),
        ],
    }
    paths = {**roots, "config": config}
    _seal_authorities(paths, manifest)
    manifest_path = tmp_path / "manifest.json"
    _write(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    return {**paths, "manifest": manifest_path}


def _verify(paths: dict[str, Path], **overrides):
    arguments = {
        "manifest_path": paths["manifest"],
        "source_checkout": paths["source"],
        "configured_data_dir": paths["data"],
        "dvc_workspace": paths["dvc"],
        "sealed_bundle": paths["bundle"],
        "worldserver_config": paths["config"],
        "scenario_map_id": 100,
    }
    arguments.update(overrides)
    return verify_runtime_asset_closure(**arguments)


def _closure_args(paths: dict[str, Path]) -> list[str]:
    return [
        "--runtime-asset-closure-manifest", str(paths["manifest"]),
        "--runtime-asset-source-checkout", str(paths["source"]),
        "--runtime-asset-dvc-workspace", str(paths["dvc"]),
        "--runtime-asset-bundle", str(paths["bundle"]),
        "--runtime-asset-data-dir", str(paths["data"]),
        "--runtime-asset-map-id", "100",
    ]


def test_complete_fixture_binds_all_roots_dvc_and_native_provenance(tmp_path: Path):
    paths = _fixture(tmp_path)
    receipt = _verify(paths)
    assert receipt["complete"] is True
    assert receipt["issues"] == []
    assert receipt["configured_data_dir_binding"]["matched"] is True
    assert {row["id"] for row in receipt["asset_classes"]} == {
        "exact", "bounded", "vmaps", "bundle", "dvc_output",
    }


@pytest.mark.parametrize(
    ("mutation", "issue_kind"),
    [
        ("same_size", "hash_mismatch"),
        ("mode", "mode_mismatch"),
        ("symlink", "symlink"),
        ("extra_pattern", "extra"),
        ("missing_vmap", "missing"),
        ("dvc", "dvc_provenance_mismatch"),
    ],
)
def test_aggregate_verifier_rejects_content_and_closure_drift(
    tmp_path: Path, mutation: str, issue_kind: str,
):
    paths = _fixture(tmp_path)
    if mutation == "same_size":
        _write(paths["source"] / "offline/input.dbc", b"DBc")
    elif mutation == "mode":
        (paths["source"] / "offline/input.dbc").chmod(0o600)
    elif mutation == "symlink":
        target = paths["source"] / "offline/input.dbc"
        target.unlink()
        target.symlink_to(paths["source"] / "map-assets/100.base")
    elif mutation == "extra_pattern":
        _write(paths["source"] / "map-assets/1000002.tile", b"extra")
    elif mutation == "missing_vmap":
        (paths["data"] / "vmaps/shared.vmo").unlink()
    elif mutation == "dvc":
        lock = paths["dvc"] / "dvc.lock"
        lock.write_text(lock.read_text().replace("0123456789abcdef0123456789abcdef", "f" * 32))
    receipt = _verify(paths)
    assert receipt["complete"] is False
    assert issue_kind in receipt["issue_counts"]


def test_complete_directory_reports_every_member_delta_before_aggregate(tmp_path: Path):
    paths = _fixture(tmp_path)
    (paths["data"] / "vmaps/shared.vmo").unlink()
    (paths["data"] / "vmaps/100.vmtree").unlink()
    _write(paths["data"] / "vmaps/substituted.vmo", b"model")
    (paths["data"] / "vmaps/empty").mkdir()
    receipt = _verify(paths)
    member_deltas = {
        (row["kind"], row["path"])
        for row in receipt["issues"] if row.get("class_id") == "vmaps"
        and row["kind"] in {"missing", "extra"}
    }
    assert member_deltas == {
        ("missing", "vmaps/100.vmtree"),
        ("missing", "vmaps/shared.vmo"),
        ("extra", "vmaps/empty"),
        ("extra", "vmaps/substituted.vmo"),
    }
    assert any(
        row.get("class_id") == "vmaps" and row.get("field") == "inventory_sha256"
        for row in receipt["issues"]
    )


@pytest.mark.parametrize("root_name", ["source", "data", "dvc", "bundle"])
def test_root_symlinked_parent_is_rejected_before_authority(
    tmp_path: Path, root_name: str,
):
    paths = _fixture(tmp_path / "real")
    alias_parent = tmp_path / "alias"
    alias_parent.symlink_to(tmp_path / "real", target_is_directory=True)
    override = alias_parent / paths[root_name].relative_to(tmp_path / "real")
    if root_name == "data":
        _write(paths["config"], f'DataDir = "{override}"\n'.encode())
    arguments = {
        "source_checkout": override if root_name == "source" else paths["source"],
        "configured_data_dir": override if root_name == "data" else paths["data"],
        "dvc_workspace": override if root_name == "dvc" else paths["dvc"],
        "sealed_bundle": override if root_name == "bundle" else paths["bundle"],
    }
    receipt = _verify(paths, **arguments)
    assert receipt["issue_counts"] == {"symlink": 1}
    assert "audit_authority" not in receipt


@pytest.mark.parametrize(
    "authority", ["manifest", "config", "audit", "source_audit", "inventory", "receipt"],
)
def test_authority_symlinked_parent_fails_closed(tmp_path: Path, authority: str):
    paths = _fixture(tmp_path / "fixture")
    if authority in {"manifest", "config"}:
        real = paths[authority]
        parent = tmp_path / f"{authority}-alias"
        parent.symlink_to(real.parent, target_is_directory=True)
        replacement = parent / real.name
        receipt = _verify(
            paths,
            **({"manifest_path": replacement} if authority == "manifest" else {"worldserver_config": replacement}),
        )
        assert receipt["issue_counts"] == {"manifest_invalid": 1}
        return
    manifest = json.loads(paths["manifest"].read_text())
    if authority in {"audit", "inventory"}:
        key = "audit_authority" if authority == "audit" else "native_data_inventory_authority"
        source = paths["dvc"] / manifest[key]["path"]
        real_parent = paths["dvc"] / f"real-{authority}"
        real_parent.mkdir()
        moved = real_parent / source.name
        source.rename(moved)
        alias = paths["dvc"] / f"alias-{authority}"
        alias.symlink_to(real_parent, target_is_directory=True)
        manifest[key]["path"] = f"alias-{authority}/{source.name}"
        _write(paths["manifest"], (json.dumps(manifest, sort_keys=True) + "\n").encode())
        receipt = _verify(paths)
        expected = "audit_invalid" if authority == "audit" else "inventory_authority_invalid"
        assert receipt["issue_counts"] == {expected: 1}
        return
    if authority == "source_audit":
        authority_path = paths["dvc"] / manifest["audit_authority"]["path"]
        audit_authority = json.loads(authority_path.read_text())
        source = Path(audit_authority["source_audit"]["path"])
        real_parent = paths["dvc"] / "real-source-audit"
        real_parent.mkdir()
        moved = real_parent / source.name
        source.rename(moved)
        alias = paths["dvc"] / "alias-source-audit"
        alias.symlink_to(real_parent, target_is_directory=True)
        audit_authority["source_audit"]["path"] = str(alias / source.name)
        _write_json(authority_path, audit_authority)
        authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()
        manifest["audit_authority"]["sha256"] = authority_sha256
        manifest["native_data_inventory_authority"]["audit_authority_sha256"] = authority_sha256
        _write(paths["manifest"], (json.dumps(manifest, sort_keys=True) + "\n").encode())
        receipt = _verify(paths)
        assert receipt["issue_counts"] == {"audit_invalid": 1}
        return
    source = paths["data"] / "provenance.json"
    real_parent = paths["data"] / "real-receipt"
    real_parent.mkdir()
    moved = real_parent / source.name
    source.rename(moved)
    alias = paths["data"] / "alias-receipt"
    alias.symlink_to(real_parent, target_is_directory=True)
    manifest["native_extraction_provenance"]["path"] = "alias-receipt/provenance.json"
    _write(paths["manifest"], (json.dumps(manifest, sort_keys=True) + "\n").encode())
    receipt = _verify(paths)
    assert receipt["issue_counts"]["provenance_invalid"] >= 1


@pytest.mark.parametrize("mutation", ["missing", "same_size", "wrong_schema", "class_rule", "digest"])
def test_audit_authority_failures_are_typed(tmp_path: Path, mutation: str):
    paths = _fixture(tmp_path)
    manifest = json.loads(paths["manifest"].read_text())
    authority_path = paths["dvc"] / manifest["audit_authority"]["path"]
    if mutation == "missing":
        authority_path.unlink()
    elif mutation == "same_size":
        payload = bytearray(authority_path.read_bytes())
        payload[-2] = ord(" ") if payload[-2] != ord(" ") else ord("\t")
        authority_path.write_bytes(payload)
    else:
        authority = json.loads(authority_path.read_text())
        if mutation == "wrong_schema":
            authority["schema"] = "wrong"
        elif mutation == "class_rule":
            authority["classes"][0]["rule"] = "complete-directory"
        else:
            authority["source_audit"]["source_inventory_sha256"] = "e" * 64
        _write_json(authority_path, authority)
        manifest["audit_authority"]["sha256"] = hashlib.sha256(authority_path.read_bytes()).hexdigest()
        manifest["native_data_inventory_authority"]["audit_authority_sha256"] = manifest["audit_authority"]["sha256"]
        _write(paths["manifest"], (json.dumps(manifest, sort_keys=True) + "\n").encode())
    receipt = _verify(paths)
    assert receipt["issue_counts"] == {"audit_invalid": 1}


@pytest.mark.parametrize("mutation", ["missing", "same_size", "wrong_schema", "subset_digest"])
def test_inventory_authority_failures_are_typed(tmp_path: Path, mutation: str):
    paths = _fixture(tmp_path)
    manifest = json.loads(paths["manifest"].read_text())
    authority_path = paths["dvc"] / manifest["native_data_inventory_authority"]["path"]
    if mutation == "missing":
        authority_path.unlink()
    elif mutation == "same_size":
        payload = bytearray(authority_path.read_bytes())
        payload[-2] = ord(" ") if payload[-2] != ord(" ") else ord("\t")
        authority_path.write_bytes(payload)
    else:
        authority = json.loads(authority_path.read_text())
        if mutation == "wrong_schema":
            authority["schema"] = "wrong"
        else:
            authority["subsets"]["vmaps"]["record_inventory"]["inventory_sha256"] = "a" * 64
        _write_json(authority_path, authority)
        manifest["native_data_inventory_authority"]["sha256"] = hashlib.sha256(
            authority_path.read_bytes()
        ).hexdigest()
        _write(paths["manifest"], (json.dumps(manifest, sort_keys=True) + "\n").encode())
    receipt = _verify(paths)
    assert receipt["issue_counts"] == {"inventory_authority_invalid": 1}


@pytest.mark.parametrize(
    "mutation",
    ["receipt_bytes", "client_identity", "extractor_identity", "inventory_authority", "data_content"],
)
def test_fabricated_extraction_receipt_fails_closed(tmp_path: Path, mutation: str):
    paths = _fixture(tmp_path)
    manifest = json.loads(paths["manifest"].read_text())
    receipt_path = paths["data"] / "provenance.json"
    receipt = json.loads(receipt_path.read_text())
    if mutation == "receipt_bytes":
        receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
    elif mutation == "data_content":
        _write(paths["data"] / "unrelated.bin", b"changed")
    else:
        if mutation == "client_identity":
            receipt["client_identity"] = {"client_build": "wrong"}
        elif mutation == "extractor_identity":
            receipt["extractor_identity"] = {"name": "wrong"}
        else:
            receipt["inventory_authority_sha256"] = "f" * 64
        _write_json(receipt_path, receipt)
        manifest["native_extraction_provenance"]["receipt_sha256"] = hashlib.sha256(
            receipt_path.read_bytes()
        ).hexdigest()
        _write(paths["manifest"], (json.dumps(manifest, sort_keys=True) + "\n").encode())
    result = _verify(paths)
    assert result["complete"] is False
    assert result["issue_counts"]["provenance_invalid"] >= 1


def test_data_dir_mismatch_is_typed(tmp_path: Path):
    paths = _fixture(tmp_path)
    other = tmp_path / "other-data"
    other.mkdir()
    receipt = _verify(paths, configured_data_dir=other)
    assert receipt["complete"] is False
    assert receipt["issue_counts"]["root_mismatch"] == 1


def test_between_snapshot_drift_is_typed(tmp_path: Path):
    paths = _fixture(tmp_path)
    before = _verify(paths)
    _write(paths["source"] / "offline/input.dbc", b"DBc")
    after = _verify(paths, previous_snapshot=before["snapshot"])
    assert after["issue_counts"]["snapshot_mismatch"] >= 1


def test_duplicate_manifest_key_and_path_traversal_are_rejected(tmp_path: Path):
    paths = _fixture(tmp_path)
    paths["manifest"].write_text(
        '{"schema":"cata_runtime_asset_closure_manifest_v1","schema":"duplicate"}\n'
    )
    duplicate = _verify(paths)
    assert duplicate["issue_counts"] == {"manifest_invalid": 1}
    paths = _fixture(tmp_path / "traversal")
    manifest = json.loads(paths["manifest"].read_text())
    manifest["asset_classes"][0]["expected_files"][0]["path"] = "../escape"
    paths["manifest"].write_text(json.dumps(manifest))
    traversal = _verify(paths)
    assert traversal["issue_counts"]["manifest_invalid"] == 1


def test_exact_thirteen_retained_identities_fail_together_then_pass(tmp_path: Path):
    fixture = json.loads(NEGATIVE_FIXTURE.read_text())
    roots = {name: tmp_path / name for name in ("source", "data", "dvc", "bundle")}
    for root in roots.values():
        root.mkdir()
    config = tmp_path / "worldserver.conf"
    _write(config, f'DataDir = "{roots["data"]}"\n'.encode())
    _write(roots["dvc"] / "dvc.lock", b"schema: '2.0'\nstages: {}\n")
    rows = []
    for relative in fixture["missing_retained_files"]:
        payload = relative.encode()
        rows.append({
            "path": relative, "type": "file", "mode": "0644",
            "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
        })
    manifest = {
        "schema": "cata_runtime_asset_closure_manifest_v1",
        "dvc_provenance": [],
        "asset_classes": [_class("retained_inputs", "source-checkout", "exact-file", expected_files=rows, expected_inventory=_inventory(rows))],
    }
    paths = {**roots, "config": config}
    _seal_authorities(paths, manifest)
    manifest_path = tmp_path / "manifest.json"
    _write(manifest_path, json.dumps(manifest).encode())
    paths["manifest"] = manifest_path
    before = _verify(paths)
    missing = {row["path"] for row in before["issues"] if row["kind"] == "missing"}
    assert missing == set(fixture["missing_retained_files"])
    assert before["issue_counts"]["missing"] == 13
    for row in rows:
        _write(roots["source"] / str(row["path"]), str(row["path"]).encode())
    after = _verify(paths)
    assert after["complete"] is True


@pytest.mark.skipif(not RETAINED.is_dir() or not BUNDLE.is_dir(), reason="retained Stage3 evidence unavailable")
def test_production_manifest_reports_current_full_closure_once():
    fixture = json.loads(NEGATIVE_FIXTURE.read_text())
    receipt = verify_runtime_asset_closure(
        manifest_path=PRODUCTION_MANIFEST,
        source_checkout=RETAINED,
        configured_data_dir=ROOT / "data",
        dvc_workspace=ROOT,
        sealed_bundle=BUNDLE,
        worldserver_config=BUNDLE / "worldserver.validation.conf",
        scenario_map_id=fixture["scenario_map_id"],
    )
    missing = {row["path"] for row in receipt["issues"] if row["kind"] == "missing"}
    assert missing == set(fixture["missing_retained_files"])
    assert receipt["issue_counts"]["missing"] == 13
    assert any(
        row["kind"] == "provenance_missing"
        and row["path"] == fixture["missing_native_provenance"]
        for row in receipt["issues"]
    )
    passed = {row["id"] for row in receipt["asset_classes"] if row["passed"]}
    assert set(fixture["present_classes"]) <= passed


def test_capture_setup_gate_precedes_nav_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    paths = _fixture(tmp_path / "closure")
    (paths["source"] / "offline/input.dbc").unlink()
    binary = tmp_path / "worldserver"
    receipt = tmp_path / "build.json"
    _write(binary)
    _write(receipt)
    monkeypatch.setattr(
        capture_setup, "_drudge_navmesh_probe",
        lambda *_args: (_ for _ in ()).throw(AssertionError("nav probe reached")),
    )
    with pytest.raises(SystemExit, match="runtime_asset_closure_incomplete"):
        capture_setup.prepare_capture_setup([
            "--binary", str(binary), "--config", str(paths["config"]),
            "--output", str(tmp_path / "capture.json"),
            "--build-receipt", str(receipt), "--worktree", str(paths["source"]),
            *_closure_args(paths),
        ], root=tmp_path)


def test_readback_gate_precedes_contract_and_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    paths = _fixture(tmp_path / "closure")
    (paths["source"] / "offline/input.dbc").unlink()
    monkeypatch.setattr(
        readback, "load_materialized_readback_contract",
        lambda *_args: (_ for _ in ()).throw(AssertionError("contract reached")),
    )
    monkeypatch.setattr(sys, "argv", [
        "capture-readback", "--worldserver-conf", str(paths["config"]),
        "--output", str(tmp_path / "readback.json"), *_closure_args(paths),
    ])
    with pytest.raises(SystemExit, match="runtime_asset_closure_incomplete"):
        readback.main()


def test_live_validator_gate_precedes_output_provisioning_and_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    paths = _fixture(tmp_path / "closure")
    (paths["source"] / "offline/input.dbc").unlink()
    monkeypatch.setattr(
        live_validation, "prepare_validation_provisioning",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provisioning reached")),
    )
    output = tmp_path / "live"
    monkeypatch.setattr(sys, "argv", [
        "bot-live-validate", "--config", str(paths["config"]),
        "--output-dir", str(output), "--prepare-only",
        "--apply-validation-provisioning", *_closure_args(paths),
    ])
    with pytest.raises(SystemExit, match="runtime_asset_closure_incomplete"):
        live_validation.main()
    assert not output.exists()
