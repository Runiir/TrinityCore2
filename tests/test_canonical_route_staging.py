from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

import tools.raid_program.canonical_route_staging as staging
import tools.raid_program.canonical_route_catalog as catalog
import tools.raid_program.chainwielder_prestart_bundle as prestart_bundle
from tools.bot_ml.run_live_bot_validation import (
    load_validation_routes_for_scenario,
    validation_route_manifest_payload,
)


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


def _route_row(
    scenario_id: str, step: int, node_id: str, *, kind: str = "trash",
    coordinates_valid: bool = True,
) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "runtime_profile_id": scenario_id,
        "step": step,
        "kind": kind,
        "label": node_id.rsplit(".", 1)[-1],
        "route_node_id": node_id,
        "coordinates_valid": coordinates_valid,
        "map_id": 669,
        "source_entry": 42649,
        "expected_bot_count": 10,
    }


def _set_catalog(
    fixture: dict[str, object], rows: list[object], *, raw: bytes | None = None,
) -> None:
    route = fixture["route"]
    route.write_bytes(
        raw if raw is not None else b"".join(
            json.dumps(row, sort_keys=True).encode() + b"\n" for row in rows
        )
    )
    member_md5 = hashlib.md5(
        route.read_bytes(), usedforsecurity=False
    ).hexdigest()
    _replace_manifest(
        fixture,
        [{"md5": member_md5, "relpath": fixture["member"]}],
    )
    fixture["sha256"] = hashlib.sha256(route.read_bytes()).hexdigest()


def _materialize(
    fixture: dict[str, object], staging_receipt: dict[str, object],
    scenario_id: str,
) -> dict[str, object]:
    return catalog.materialize_scenario_route_manifest(
        worktree=fixture["root"],
        staging_receipt_path=Path(staging_receipt["receipt_path"]),
        expected_staging_receipt_sha256=staging_receipt["receipt_sha256"],
        selected_scenario_id=scenario_id,
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


def test_chainwielder_wrapper_failure_is_local_bundle_error_before_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        stage_name="validation_scenarios",
        output_path="dataset/validation_scenarios",
        member="validation_routes.jsonl",
    )
    fixture["route"] = (
        fixture["root"]
        / "dataset/validation_scenarios/missing.jsonl"
    )
    create_calls = 0

    def counted_create(**_values: object) -> dict[str, object]:
        nonlocal create_calls
        create_calls += 1
        return {}

    monkeypatch.setattr(prestart_bundle, "create_bundle", counted_create)
    with pytest.raises(prestart_bundle.BundleError) as caught:
        prestart_bundle.stage_canonical_route(
            worktree=fixture["root"],
            source_route=fixture["route"],
            expected_sha256=fixture["sha256"],
            external_run_root=fixture["external"],
        )

    error_type = type(caught.value)
    assert error_type is prestart_bundle.BundleError
    assert error_type.__module__ == prestart_bundle.__name__
    assert error_type.__name__ == "BundleError"
    assert str(caught.value) == "source_route_location_invalid"
    assert isinstance(caught.value.__cause__, staging.CanonicalRouteStagingError)
    assert create_calls == 0


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


def test_raw_jsonl_fails_before_bundle_shape_validation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _set_catalog(fixture, [
        _route_row("one", 1, "one.first"),
        _route_row("one", 2, "one.second"),
    ])
    staged = _stage(fixture)

    with pytest.raises(prestart_bundle.BundleError, match="route_manifest_invalid"):
        prestart_bundle._validate_route(
            Path(staged["staged_path"]), "one", "one"
        )


def test_catalog_materializes_exact_deterministic_scenario_object(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        stage_name="validation_scenarios",
        output_path="dataset/validation_scenarios",
        member="validation_routes.jsonl",
    )
    scenario = prestart_bundle.SCENARIO_ID
    _set_catalog(fixture, [
        _route_row("another_profile", 1, "another.first"),
        _route_row(scenario, 3, "bwd.magmaw.drudges"),
        _route_row(scenario, 2, prestart_bundle.NODE_ID),
        _route_row(scenario, 4, "bwd.magmaw.encounter", kind="boss"),
        _route_row(scenario, 1, "bwd.entry.regroup", kind="regroup"),
    ])
    staged = _stage(fixture)
    result = _materialize(fixture, staged, scenario)
    manifest_path = Path(result["output_object_path"])
    manifest = json.loads(manifest_path.read_bytes())

    assert manifest["schema"] == catalog.MANIFEST_SCHEMA
    assert manifest["scenario_id"] == scenario
    assert manifest["route_count"] == 4
    assert [row["step"] for row in manifest["routes"]] == [1, 2, 3, 4]
    assert [row["route_generation"] for row in manifest["routes"]] == [1, 2, 3, 4]
    assert manifest["expected_segments"] == [
        "01_regroup", "02_chainwielder", "03_drudges", "04_encounter"
    ]
    assert result["catalog_row_count"] == 5
    assert result["selected_row_count"] == 4
    assert [row["step"] for row in result["selected_row_order"]] == [1, 2, 3, 4]
    assert prestart_bundle._validate_route(
        manifest_path, scenario, scenario
    ) == manifest

    verified = catalog.verify_scenario_route_manifest_receipt(
        worktree=fixture["root"],
        receipt_path=Path(result["receipt_path"]),
        expected_receipt_sha256=result["receipt_sha256"],
        expected_staging_receipt_sha256=staged["receipt_sha256"],
        selected_scenario_id=scenario,
        dvc_stage_name=fixture["stage_name"],
        output_relative_member=fixture["member"],
    )
    assert verified == result

    second_root = tmp_path / "second-run"
    second_root.mkdir()
    second = catalog.materialize_scenario_route_manifest(
        worktree=fixture["root"],
        staging_receipt_path=Path(staged["receipt_path"]),
        expected_staging_receipt_sha256=staged["receipt_sha256"],
        selected_scenario_id=scenario,
        external_run_root=second_root,
        dvc_stage_name=fixture["stage_name"],
        output_relative_member=fixture["member"],
    )
    assert Path(second["output_object_path"]).read_bytes() == manifest_path.read_bytes()
    assert second["output_object_sha256"] == result["output_object_sha256"]


def test_mixed_kind_catalog_matches_canonical_runtime_selection(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        stage_name="validation_scenarios",
        output_path="dataset/validation_scenarios",
        member="validation_routes.jsonl",
    )
    scenario = "blackwing_descent_10n_atramedes_diagnostic"
    rows = [
        _route_row("another_profile", 1, "another.first"),
        _route_row(scenario, 7, "bwd.atramedes.encounter", kind="boss"),
        _route_row(scenario, 3, "bwd.atramedes.bell_ready", kind="interaction"),
        _route_row(scenario, 1, "bwd.atramedes.north_spirits"),
        _route_row(
            scenario, 1, "bwd.atramedes.north_spirits",
            coordinates_valid=False,
        ),
        _route_row(scenario, 4, "bwd.atramedes.bell", kind="interaction"),
        _route_row(scenario, 2, "bwd.atramedes.south_spirits"),
        _route_row(scenario, 5, "bwd.atramedes.intro_wait", kind="interaction"),
        _route_row(scenario, 6, "bwd.atramedes.regroup", kind="regroup"),
    ]
    _set_catalog(fixture, rows)
    canonical_routes = load_validation_routes_for_scenario(
        fixture["route"].parent, scenario
    )
    canonical_payload = validation_route_manifest_payload(
        scenario, canonical_routes
    )
    staged = _stage(fixture)
    result = _materialize(fixture, staged, scenario)
    manifest = json.loads(Path(result["output_object_path"]).read_bytes())

    assert manifest == canonical_payload
    assert [row["step"] for row in manifest["routes"]] == [1, 2, 6, 7]
    assert [row["route_generation"] for row in manifest["routes"]] == [1, 2, 3, 4]
    assert [row["line_number"] for row in result["selected_row_order"]] == [
        4, 7, 9, 2
    ]
    assert result["selected_row_count"] == 4
    excluded = {3, 5, 6, 8}
    assert excluded.isdisjoint(
        row["line_number"] for row in result["selected_row_order"]
    )


@pytest.mark.parametrize(
    ("rows", "raw", "scenario", "reason"),
    [
        ([], b'{"scenario_id":\n', "selected", "route_catalog_jsonl_invalid:1"),
        ([[]], None, "selected", "route_catalog_row_invalid:1"),
        ([_route_row("other", 1, "other.first")], None, "selected", "route_catalog_scenario_missing"),
        ([_route_row("selected", 1, "selected.first", kind="interaction")], None, "selected", "route_catalog_scenario_missing"),
        ([_route_row("selected", 1, "selected.first", coordinates_valid=False)], None, "selected", "route_catalog_scenario_missing"),
        ([_route_row("selected", 1, "selected.first"), _route_row("selected", 1, "selected.second")], None, "selected", "route_catalog_scenario_ambiguous"),
        ([_route_row("selected", 1, "selected.first"), _route_row("selected", 2, "selected.first")], None, "selected", "route_catalog_scenario_ambiguous"),
    ],
)
def test_catalog_selection_fails_closed(
    tmp_path: Path, rows: list[object], raw: bytes | None,
    scenario: str, reason: str,
) -> None:
    fixture = _fixture(tmp_path)
    _set_catalog(fixture, rows, raw=raw)
    staged = _stage(fixture)

    with pytest.raises(catalog.CanonicalRouteCatalogError, match=reason):
        _materialize(fixture, staged, scenario)


def test_catalog_selection_rejects_hash_drift_collision_and_receipt_drift(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _set_catalog(fixture, [_route_row("selected", 1, "selected.first")])
    staged = _stage(fixture)
    result = _materialize(fixture, staged, "selected")

    with pytest.raises(
        catalog.CanonicalRouteCatalogError, match="route_manifest_output_collision"
    ):
        _materialize(fixture, staged, "selected")

    receipt_path = Path(result["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["selected_row_count"] = 2
    drift_path = fixture["external"] / "drifted.receipt.json"
    drift_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    drift_path.write_bytes(drift_bytes)
    with pytest.raises(
        catalog.CanonicalRouteCatalogError, match="route_manifest_receipt_mismatch"
    ):
        catalog.verify_scenario_route_manifest_receipt(
            worktree=fixture["root"],
            receipt_path=drift_path,
            expected_receipt_sha256=hashlib.sha256(drift_bytes).hexdigest(),
            expected_staging_receipt_sha256=staged["receipt_sha256"],
            selected_scenario_id="selected",
            dvc_stage_name=fixture["stage_name"],
            output_relative_member=fixture["member"],
        )

    Path(staged["staged_path"]).write_bytes(b"drift\n")
    with pytest.raises(
        catalog.CanonicalRouteCatalogError,
        match="staging_receipt_catalog_hash_mismatch",
    ):
        catalog.verify_scenario_route_manifest_receipt(
            worktree=fixture["root"],
            receipt_path=receipt_path,
            expected_receipt_sha256=result["receipt_sha256"],
            expected_staging_receipt_sha256=staged["receipt_sha256"],
            selected_scenario_id="selected",
            dvc_stage_name=fixture["stage_name"],
            output_relative_member=fixture["member"],
        )


def test_staging_receipt_replacement_cannot_substitute_valid_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    _set_catalog(fixture, [_route_row("generic", 1, "generic.first")])
    first = _stage(fixture)
    second_root = tmp_path / "second-stage"
    second_root.mkdir()
    fixture["external"] = second_root
    second = _stage(fixture)

    for valid in (first, second):
        verified = staging.verify_staging_receipt(
            worktree=fixture["root"],
            receipt_path=Path(valid["receipt_path"]),
            expected_receipt_sha256=valid["receipt_sha256"],
            dvc_stage_name=fixture["stage_name"],
            output_relative_member=fixture["member"],
        )
        assert verified["staged_path"] == valid["staged_path"]

    first_path = Path(first["receipt_path"])
    replacement = tmp_path / "replacement-receipt.json"
    replacement.write_bytes(Path(second["receipt_path"]).read_bytes())
    real_fstat = staging.os.fstat
    calls = 0

    def replace_after_open(descriptor: int) -> object:
        nonlocal calls
        state = real_fstat(descriptor)
        calls += 1
        if calls == 1:
            staging.os.replace(replacement, first_path)
        return state

    monkeypatch.setattr(staging.os, "fstat", replace_after_open)
    with pytest.raises(
        staging.CanonicalRouteStagingError,
        match="staging_receipt_path_replaced",
    ):
        staging.verify_staging_receipt(
            worktree=fixture["root"],
            receipt_path=first_path,
            expected_receipt_sha256=first["receipt_sha256"],
            dvc_stage_name=fixture["stage_name"],
            output_relative_member=fixture["member"],
        )
    assert calls == 2


def test_post_stat_locator_replacement_preserves_snapshot_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    _set_catalog(fixture, [_route_row("generic", 1, "generic.first")])
    first = _stage(fixture)
    first_receipt_bytes = Path(first["receipt_path"]).read_bytes()
    first_staged_path = first["staged_path"]

    second_root = tmp_path / "second-stage"
    second_root.mkdir()
    fixture["external"] = second_root
    second = _stage(fixture)
    second_receipt_bytes = Path(second["receipt_path"]).read_bytes()
    replacement = tmp_path / "replacement-after-stat.json"
    replacement.write_bytes(second_receipt_bytes)

    output_root = tmp_path / "scenario-output"
    output_root.mkdir()
    fixture["external"] = output_root
    first_path = Path(first["receipt_path"])
    real_stat = staging.os.stat
    swapped = False

    def replace_after_final_stat(
        path: object, *args: object, **kwargs: object,
    ) -> object:
        nonlocal swapped
        state = real_stat(path, *args, **kwargs)
        if (
            not swapped
            and Path(path) == first_path
            and kwargs.get("follow_symlinks") is False
        ):
            staging.os.replace(replacement, first_path)
            swapped = True
        return state

    monkeypatch.setattr(staging.os, "stat", replace_after_final_stat)
    result = _materialize(fixture, first, "generic")
    embedded = base64.b64decode(
        result["staging_receipt_snapshot_base64"], validate=True
    )

    assert swapped is True
    assert first_path.read_bytes() == second_receipt_bytes
    assert embedded == first_receipt_bytes
    assert hashlib.sha256(embedded).hexdigest() == first["receipt_sha256"]
    assert result["staging_receipt_locator"] == str(first_path)
    assert result["staged_catalog_path"] == first_staged_path

    verified = catalog.verify_scenario_route_manifest_receipt(
        worktree=fixture["root"],
        receipt_path=Path(result["receipt_path"]),
        expected_receipt_sha256=result["receipt_sha256"],
        expected_staging_receipt_sha256=first["receipt_sha256"],
        selected_scenario_id="generic",
        dvc_stage_name=fixture["stage_name"],
        output_relative_member=fixture["member"],
    )
    assert verified == result

    drift = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    drift["staging_receipt_snapshot_base64"] = base64.b64encode(
        second_receipt_bytes
    ).decode("ascii")
    drift["staging_receipt_sha256"] = second["receipt_sha256"]
    drift_path = output_root / "mismatched-snapshot.receipt.json"
    drift_bytes = (json.dumps(drift, indent=2, sort_keys=True) + "\n").encode()
    drift_path.write_bytes(drift_bytes)
    with pytest.raises(
        catalog.CanonicalRouteCatalogError,
        match="staging_receipt_sha256_mismatch",
    ):
        catalog.verify_scenario_route_manifest_receipt(
            worktree=fixture["root"],
            receipt_path=drift_path,
            expected_receipt_sha256=hashlib.sha256(drift_bytes).hexdigest(),
            expected_staging_receipt_sha256=first["receipt_sha256"],
            selected_scenario_id="generic",
            dvc_stage_name=fixture["stage_name"],
            output_relative_member=fixture["member"],
        )
