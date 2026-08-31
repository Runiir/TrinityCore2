from __future__ import annotations

import copy
from pathlib import Path
import subprocess

import pytest

import tools.raid_program.composite_fixture_replay_launcher as launcher
from tools.raid_program.chainwielder_prestart_bundle import expected_launch_argv
from tools.raid_program.chainwielder_runtime_config_authority import (
    TRACKED_DERIVED_AUTHORITY,
)


ROOT = Path(__file__).resolve().parents[1]
REAL_SOURCE_AUTHORITY = launcher._source_authority
SOURCE = {
    "commit": "a" * 40,
    "tree": "b" * 40,
    "active_descriptor_path": "experiments/configs/cata_raid_active_work_unit_v1.json",
    "active_descriptor_sha256": "c" * 64,
    "source_handoff_path": "experiments/configs/handoff.json",
    "source_handoff_sha256": "d" * 64,
}


@pytest.fixture(autouse=True)
def _stable_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        launcher, "_source_authority",
        lambda _worktree, _work_unit: dict(SOURCE),
    )


def _request(
    tmp_path: Path, expected_work_unit: str = launcher.EXPECTED_WORK_UNIT,
) -> dict:
    external = tmp_path.resolve()
    return {
        "schema": launcher.REQUEST_SCHEMA,
        "worktree": str(ROOT),
        "run_root": str(external / "run"),
        "expected_work_unit": expected_work_unit,
        "decision": {"path": str(external / "decision.json")},
        "suite_receipt": {"path": str(external / "suite.json")},
        "route_manifest": {"path": str(external / "route.json")},
        "base_runtime_config_receipt": {
            "path": str(external / "runtime.receipt.json"),
        },
        "runtime_config_authorities": [TRACKED_DERIVED_AUTHORITY],
    }


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _prebuild(tmp_path: Path) -> tuple[dict, dict, Path]:
    request = _request(tmp_path)
    plan = launcher.compose_plan(copy.deepcopy(request))
    path = tmp_path / "prebuild.json"
    _write(path, launcher._canonical_bytes(plan))
    return request, plan, path


def test_prebuild_is_deterministic_and_exact(tmp_path: Path) -> None:
    request = _request(tmp_path)
    first = launcher.compose_plan(copy.deepcopy(request))
    second = launcher.compose_plan(copy.deepcopy(request))
    assert first == second
    assert first["schema"] == launcher.PREBUILD_SCHEMA
    assert first["source"] == {"worktree": str(ROOT), **SOURCE}
    assert first["execution"] == {
        "composition_side_effect_free": True,
        "order": ["configure", "build"],
        "postbuild_realization_required": True,
    }
    configure = first["commands"]["configure"]
    build = first["commands"]["build"]
    assert configure["cwd"] == build["cwd"] == str(ROOT)
    child = configure["argv"].index("--") + 1
    assert configure["argv"][child:child + 5] == [
        "/usr/bin/cmake", "-S", ".", "-B", "build",
    ]
    assert build["argv"][-7:] == [
        "/usr/bin/cmake", "--build", "build", "--target", "worldserver",
        "--parallel", "8",
    ]


def test_live_prebuild_uses_live_source_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    selectors: list[str] = []

    def source_authority(_worktree: Path, work_unit: str) -> dict[str, str]:
        selectors.append(work_unit)
        if work_unit != launcher.LIVE_WORK_UNIT:
            raise AssertionError(f"stale selector: {work_unit}")
        return dict(SOURCE)

    monkeypatch.setattr(launcher, "_source_authority", source_authority)
    request = _request(tmp_path, launcher.LIVE_WORK_UNIT)
    plan = launcher.compose_plan(request)
    assert plan["schema"] == launcher.PREBUILD_SCHEMA
    assert selectors == [launcher.LIVE_WORK_UNIT]


def test_live_realization_revalidates_live_source_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    selectors: list[str] = []

    def source_authority(_worktree: Path, work_unit: str) -> dict[str, str]:
        selectors.append(work_unit)
        if work_unit != launcher.LIVE_WORK_UNIT:
            raise AssertionError(f"stale selector: {work_unit}")
        return dict(SOURCE)

    monkeypatch.setattr(launcher, "_source_authority", source_authority)
    request = _request(tmp_path, launcher.LIVE_WORK_UNIT)
    prebuild = launcher.compose_plan(request)
    prebuild_path = tmp_path / "live-prebuild.json"
    _write(prebuild_path, launcher._canonical_bytes(prebuild))
    for label in (
        "decision", "suite_receipt", "route_manifest",
        "base_runtime_config_receipt",
    ):
        _write(Path(request[label]["path"]), label.encode())
    run_root = Path(request["run_root"])
    _write(run_root / "configure_receipt.json", b"configure\n")
    _write(run_root / "worldserver_build_receipt.json", b"receipt\n")
    monkeypatch.setattr(launcher, "_verified_build_artifacts", lambda **_kwargs: {
        "binary": {
            "path": str(ROOT / "build/src/server/worldserver/worldserver"),
            "sha256": "1" * 64,
        },
        "configure_receipt": {
            "path": str(run_root / "configure_receipt.json"),
            "sha256": "2" * 64,
        },
        "build_receipt": {
            "path": str(run_root / "worldserver_build_receipt.json"),
            "sha256": "3" * 64,
        },
    })
    selectors.clear()
    realized = launcher.realize_plan(request, prebuild, prebuild_path)
    assert realized["schema"] == launcher.REALIZED_SCHEMA
    assert selectors == [launcher.LIVE_WORK_UNIT, launcher.LIVE_WORK_UNIT]


def test_target_receipt_prebuild_uses_typed_source_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    selectors: list[str] = []

    def source_authority(_worktree: Path, work_unit: str) -> dict[str, str]:
        selectors.append(work_unit)
        if work_unit != launcher.TARGET_RECEIPT_WORK_UNIT:
            raise AssertionError(f"stale selector: {work_unit}")
        return dict(SOURCE)

    monkeypatch.setattr(launcher, "_source_authority", source_authority)
    request = _request(tmp_path, launcher.TARGET_RECEIPT_WORK_UNIT)
    plan = launcher.compose_plan(request)
    assert plan["schema"] == launcher.PREBUILD_SCHEMA
    assert selectors == [launcher.TARGET_RECEIPT_WORK_UNIT]


def test_realization_binds_fresh_artifacts_after_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    request, prebuild, prebuild_path = _prebuild(tmp_path)
    for label in (
        "decision", "suite_receipt", "route_manifest",
        "base_runtime_config_receipt",
    ):
        _write(Path(request[label]["path"]), label.encode())
    run_root = Path(request["run_root"])
    _write(run_root / "configure_receipt.json", b"configure\n")
    _write(run_root / "worldserver_build_receipt.json", b"receipt\n")
    monkeypatch.setattr(launcher, "_verified_build_artifacts", lambda **_kwargs: {
        "binary": {
            "path": str(ROOT / "build/src/server/worldserver/worldserver"),
            "sha256": "1" * 64,
        },
        "build_receipt": {
            "path": str(run_root / "worldserver_build_receipt.json"),
            "sha256": "2" * 64,
        },
    })
    realized = launcher.realize_plan(request, prebuild, prebuild_path)
    assert realized["schema"] == launcher.REALIZED_SCHEMA
    assert realized["prebuild_plan"] == {
        "path": str(prebuild_path), "sha256": prebuild["plan_sha256"],
    }
    assert realized["execution"]["capture_timer"] == "completion_watchdog"
    assert realized["execution"]["fixed_success_timer_seconds"] is None
    assert realized["execution"]["order"] == [
        "bundle_create", "bundle_verify", "provisioning_apply",
        "strict_readback", "shard_readback", "capture",
    ]
    for command in realized["commands"].values():
        assert command["cwd"] == str(ROOT)
    bundle = realized["commands"]["bundle_create"]["argv"]
    assert bundle[bundle.index("--binary-sha256") + 1] == "1" * 64
    assert bundle[bundle.index("--build-receipt-sha256") + 1] == "2" * 64
    assert bundle[bundle.index("--base-runtime-config-authority") + 1] == (
        TRACKED_DERIVED_AUTHORITY
    )
    assert "--observe-sec" not in realized["commands"]["capture"]["argv"]
    provisioning = realized["commands"]["provisioning_apply"]["argv"]
    assert provisioning[-2:] == [
        "--apply-validation-provisioning", "--prepare-only",
    ]
    assert provisioning[provisioning.index("--config") + 1] == str(
        Path(request["run_root"]) / "prestart_bundle"
        / launcher.BUNDLE_NAMES["runtime_config"]
    )


@pytest.mark.parametrize(
    "authorities",
    [[], [TRACKED_DERIVED_AUTHORITY] * 2, ["tracked_snapshot_v1"], [None]],
)
def test_prebuild_rejects_missing_multiple_or_wrong_runtime_authority(
    tmp_path: Path, authorities: list[object],
) -> None:
    request = _request(tmp_path)
    request["runtime_config_authorities"] = authorities
    with pytest.raises(
        launcher.ReplayPlanError,
        match="runtime_config_authority_selection_invalid",
    ):
        launcher.compose_plan(request)


def test_prebuild_rejects_wrong_work_unit(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request["expected_work_unit"] = "wrong"
    with pytest.raises(launcher.ReplayPlanError, match="expected_work_unit_invalid"):
        launcher.compose_plan(request)


def test_prebuild_rejects_noncanonical_build_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    real = launcher._load_object

    def altered(path: Path) -> dict:
        value = real(path)
        value["mechanical_controls"]["cmake_executable"] = "/usr/bin/false"
        return value

    monkeypatch.setattr(launcher, "_load_object", altered)
    with pytest.raises(launcher.ReplayPlanError):
        launcher.compose_plan(_request(tmp_path))


def test_prebuild_rejects_in_tree_or_existing_outputs(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request["run_root"] = str(ROOT / "artifacts" / "forbidden-live-run")
    with pytest.raises(launcher.ReplayPlanError, match="run_root_must_be_external"):
        launcher.compose_plan(request)
    request = _request(tmp_path)
    _write(Path(request["run_root"]) / "configure_receipt.json", b"old")
    with pytest.raises(launcher.ReplayPlanError, match="declared_output_exists"):
        launcher.compose_plan(request)


def test_prebuild_rejects_material_input_inside_run_root(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request["decision"]["path"] = str(
        Path(request["run_root"]) / "decision.json"
    )
    with pytest.raises(launcher.ReplayPlanError, match="decision_aliases_run_root"):
        launcher.compose_plan(request)


def test_prebuild_rejects_aliased_material_inputs(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request["suite_receipt"]["path"] = request["decision"]["path"]
    with pytest.raises(
        launcher.ReplayPlanError, match="material_input_paths_not_unique"
    ):
        launcher.compose_plan(request)


def test_prebuild_hash_rejects_any_command_edit(tmp_path: Path) -> None:
    request = _request(tmp_path)
    plan = launcher.compose_plan(copy.deepcopy(request))
    plan["commands"]["build"]["argv"][-1] = "7"
    with pytest.raises(launcher.ReplayPlanError, match="plan_sha256_mismatch"):
        launcher.validate_plan(plan, request)


def test_plan_composition_runs_no_external_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        launcher.subprocess, "run",
        lambda *_args, **_kwargs: pytest.fail("compose executed external work"),
    )
    launcher.compose_plan(_request(tmp_path))


def test_prebuild_runner_uses_exact_order_and_cwd(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    plan = launcher.compose_plan(copy.deepcopy(request))
    calls: list[tuple[list[str], bool, Path]] = []

    def runner(
        argv: list[str], *, check: bool, cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((argv, check, cwd))
        return subprocess.CompletedProcess(argv, 0)

    assert launcher.run_plan(plan, request, runner) == 0
    assert [row[0] for row in calls] == [
        plan["commands"]["configure"]["argv"],
        plan["commands"]["build"]["argv"],
    ]
    assert all(row[1:] == (False, ROOT) for row in calls)


def test_capture_runner_consumes_verified_production_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    binary = ROOT / "build/src/server/worldserver/worldserver"
    expected = expected_launch_argv(
        worktree=ROOT, binary=binary, output_dir=bundle,
        admission_sha256="a" * 64,
    )
    monkeypatch.setattr(
        launcher, "verify_bundle", lambda _bundle: {"launch_argv": expected}
    )
    calls: list[tuple[list[str], bool, Path]] = []

    def runner(
        argv: list[str], *, check: bool, cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((argv, check, cwd))
        return subprocess.CompletedProcess(argv, 0)

    assert launcher.run_verified_capture(bundle, runner) == 0
    assert calls == [(expected, False, ROOT)]


def test_realization_requires_exact_parent_plan_path(tmp_path: Path) -> None:
    request, prebuild, prebuild_path = _prebuild(tmp_path)
    prebuild_path.write_bytes(b"tamper\n")
    with pytest.raises(
        launcher.ReplayPlanError, match="prebuild_plan_path_binding_mismatch"
    ):
        launcher.realize_plan(request, prebuild, prebuild_path)


def test_build_realization_verifies_both_external_receipts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    configure_path = run_root / "configure_receipt.json"
    build_path = run_root / "worldserver_build_receipt.json"
    _write(configure_path, b"configure")
    _write(build_path, b"build")
    _policy_path, policy, _policy_sha = launcher._policy(ROOT)
    source = dict(SOURCE)
    configure = {
        "resource_class": "configure",
        "commit": source["commit"],
        "command_sha256": launcher.command_hash(
            launcher._configure_child(policy)
        ),
        "receipt_sha256": "3" * 64,
    }
    build = {
        "resource_class": "worldserver_build",
        "commit": source["commit"],
        "command_sha256": launcher.command_hash(launcher._build_child(policy)),
        "configure_lineage": {"receipt_sha256": "3" * 64},
        "output_artifacts": [{
            "kind": "worldserver_elf",
            "path": str(ROOT / "build/src/server/worldserver/worldserver"),
            "sha256": "4" * 64,
        }],
    }
    calls: list[Path] = []

    def verify(path: Path, _policy: dict) -> dict:
        calls.append(path)
        return {"gate_bearing": True}

    monkeypatch.setattr(launcher, "verify_receipt", verify)
    monkeypatch.setattr(
        launcher, "_load_object",
        lambda path: configure if path == configure_path else build,
    )
    monkeypatch.setattr(
        launcher, "_bound_file",
        lambda path, label: {
            "path": str(path),
            "sha256": "4" * 64 if label == "binary" else "5" * 64,
        },
    )
    result = launcher._verified_build_artifacts(
        worktree=ROOT, run_root=run_root, policy=policy, source=source,
    )
    assert calls == [configure_path, build_path]
    assert result["binary"]["sha256"] == "4" * 64
    assert result["configure_receipt"]["sha256"] == "5" * 64


def test_source_authority_checks_descriptor_and_v112_handoff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.undo()
    root = tmp_path / "source"
    configs = root / "experiments/configs"
    configs.mkdir(parents=True)
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Test"], check=True,
    )
    old_commit = launcher.EXPECTED_V112_COMMIT
    old_tree = launcher.EXPECTED_V112_TREE
    handoff = {
        "schema": "cata_raid_specialist_handoff_v1",
        "work_unit_id": launcher.EXPECTED_HANDOFF_WORK_UNIT,
        "owner_skill": "raid-shard-architecture",
        "classification": launcher.EXPECTED_HANDOFF_CLASSIFICATION,
        "source": {"commit": old_commit, "tree": old_tree},
        "next_work_unit": {
            "id": launcher.EXPECTED_WORK_UNIT,
            "owner_skill": "raid-evidence-lifecycle",
            "required_action": launcher.EXPECTED_REQUIRED_ACTION,
            "required_postcondition": launcher.EXPECTED_REQUIRED_POSTCONDITION,
        },
    }
    handoff_path = root / launcher.EXPECTED_HANDOFF_PATH
    _write(handoff_path, launcher._canonical_bytes(handoff))
    handoff_sha = launcher._sha256_bytes(handoff_path.read_bytes())
    descriptor = {
        "schema": "cata_raid_active_work_unit_v1",
        "work_unit": launcher.EXPECTED_WORK_UNIT,
        "owner_skill": "raid-evidence-lifecycle",
        "classification": "prestart_command_composition_repair_required",
        "next_work_unit": launcher.EXPECTED_WORK_UNIT,
        "next_owner_skill": "raid-evidence-lifecycle",
        "observed_at_commit": old_commit,
        "immutable_input_commit": old_commit,
        "source_handoff": {
            "path": launcher.EXPECTED_HANDOFF_PATH,
            "sha256": handoff_sha,
            "source_commit": old_commit,
            "source_tree": old_tree,
        },
    }
    _write(
        configs / "cata_raid_active_work_unit_v1.json",
        launcher._canonical_bytes(descriptor),
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "fixture"],
        check=True, capture_output=True,
    )
    result = REAL_SOURCE_AUTHORITY(root.resolve(), launcher.EXPECTED_WORK_UNIT)
    assert result["source_handoff_sha256"] == handoff_sha
    handoff_path.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(launcher.ReplayPlanError, match="source_worktree_dirty"):
        REAL_SOURCE_AUTHORITY(root.resolve(), launcher.EXPECTED_WORK_UNIT)
