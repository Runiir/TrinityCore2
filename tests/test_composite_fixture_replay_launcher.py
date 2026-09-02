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
TEST_WORK_UNIT = "shard:future_composite_fixture_replay_v999"
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
    tmp_path: Path, expected_work_unit: str = TEST_WORK_UNIT,
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


def _personal_threat_target() -> dict:
    return {
        "actor_guid": 30008,
        "scope_key": (
            "{cohort_id}:{attempt_id}:{wipe_generation}:3:"
            "bwd.magmaw.encounter:669:{instance_id}:tank_swap_adds_raid_aoe"
        ),
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 3,
        "parent_wave_generation": (1 << 63) | 1,
        "parent_generation_authoritative": False,
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


def test_personal_threat_target_is_hash_bound_and_emitted_to_bundle_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    request["personal_threat_episode_target"] = _personal_threat_target()
    plan = launcher.compose_plan(copy.deepcopy(request))
    assert plan["personal_threat_episode_target"] == request[
        "personal_threat_episode_target"
    ]
    changed = copy.deepcopy(request)
    changed["personal_threat_episode_target"]["parent_wave_generation"] += 1
    with pytest.raises(
        launcher.ReplayPlanError, match="target_parent_wave_generation_mismatch"
    ):
        launcher.validate_plan(plan, changed)

    argv = launcher._bundle_create(
        worktree=ROOT,
        source=SOURCE,
        run_root=tmp_path / "run",
        policy_path=ROOT / launcher.POLICY_RELATIVE_PATH,
        policy_sha256="a" * 64,
        artifacts={
            "binary": {"sha256": "b" * 64},
            "build_receipt": {"sha256": "c" * 64},
            "decision": {"path": str(tmp_path / "decision"), "sha256": "d" * 64},
            "suite_receipt": {"path": str(tmp_path / "suite"), "sha256": "e" * 64},
            "route_manifest": {"path": str(tmp_path / "route"), "sha256": "f" * 64},
            "base_runtime_config_receipt": {
                "path": str(tmp_path / "config"), "sha256": "0" * 64,
            },
            "ledger": {"path": str(tmp_path / "ledger"), "sha256": "1" * 64},
        },
        personal_threat_episode_target=request[
            "personal_threat_episode_target"
        ],
    )
    for field, value in (
        ("actor-guid", "30008"),
        ("scope-key", request["personal_threat_episode_target"]["scope_key"]),
        ("route-node-id", "bwd.magmaw.encounter"),
        ("route-generation", "3"),
        ("parent-wave-generation", str((1 << 63) | 1)),
    ):
        flag = "--personal-threat-episode-" + field
        assert argv[argv.index(flag) + 1] == value
    assert "--no-personal-threat-episode-parent-generation-authoritative" in argv


def test_prebuild_passes_generic_work_unit_to_source_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    selectors: list[str] = []

    def source_authority(_worktree: Path, work_unit: str) -> dict[str, str]:
        selectors.append(work_unit)
        if work_unit != TEST_WORK_UNIT:
            raise AssertionError(f"stale selector: {work_unit}")
        return dict(SOURCE)

    monkeypatch.setattr(launcher, "_source_authority", source_authority)
    request = _request(tmp_path, TEST_WORK_UNIT)
    plan = launcher.compose_plan(request)
    assert plan["schema"] == launcher.PREBUILD_SCHEMA
    assert selectors == [TEST_WORK_UNIT]


def test_realization_revalidates_generic_source_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    selectors: list[str] = []

    def source_authority(_worktree: Path, work_unit: str) -> dict[str, str]:
        selectors.append(work_unit)
        if work_unit != TEST_WORK_UNIT:
            raise AssertionError(f"stale selector: {work_unit}")
        return dict(SOURCE)

    monkeypatch.setattr(launcher, "_source_authority", source_authority)
    request = _request(tmp_path, TEST_WORK_UNIT)
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
    assert selectors == [TEST_WORK_UNIT, TEST_WORK_UNIT]


def test_second_future_work_unit_uses_same_source_authority_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    selectors: list[str] = []

    def source_authority(_worktree: Path, work_unit: str) -> dict[str, str]:
        selectors.append(work_unit)
        if work_unit != "shard:another_future_fixture_v1000":
            raise AssertionError(f"stale selector: {work_unit}")
        return dict(SOURCE)

    monkeypatch.setattr(launcher, "_source_authority", source_authority)
    request = _request(tmp_path, "shard:another_future_fixture_v1000")
    plan = launcher.compose_plan(request)
    assert plan["schema"] == launcher.PREBUILD_SCHEMA
    assert selectors == ["shard:another_future_fixture_v1000"]


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


def _authority_fixture(source_commit: str, source_tree: str) -> tuple[dict, dict]:
    required_action = "Run one future fixture through the canonical launcher."
    required_postcondition = (
        "One hash-bound future fixture reaches its typed completion watchdog."
    )
    handoff = {
        "schema": "cata_raid_specialist_handoff_v1",
        "work_unit_id": "evidence:future_fixture_review_v998",
        "owner_skill": "raid-evidence-lifecycle",
        "classification": "fixture_authority_reviewed",
        "source": {"commit": source_commit, "tree": source_tree},
        "next_work_unit": {
            "id": TEST_WORK_UNIT,
            "owner_skill": "raid-shard-architecture",
            "required_action": required_action,
            "required_postcondition": required_postcondition,
        },
    }
    authority = {
        "schema": launcher.LAUNCHER_AUTHORITY_SCHEMA,
        "expected_work_unit": TEST_WORK_UNIT,
        "descriptor_owner_skill": launcher.FIXTURE_DESCRIPTOR_OWNER,
        "descriptor_classification": launcher.FIXTURE_DESCRIPTOR_CLASSIFICATION,
        "source_handoff_schema": handoff["schema"],
        "source_handoff_work_unit": handoff["work_unit_id"],
        "source_handoff_owner_skill": handoff["owner_skill"],
        "source_handoff_classification": handoff["classification"],
        "required_action_sha256": launcher._sha256_bytes(
            required_action.encode()
        ),
        "required_postcondition_sha256": launcher._sha256_bytes(
            required_postcondition.encode()
        ),
        "scenario": dict(launcher.FIXTURE_SCENARIO),
        "fixture_expansion": {
            "purpose": "fixture_expansion_replay",
            "attempts": 1,
            "retries": 0,
            "authserver_starts": 0,
            "worldserver_starts": 1,
            "duration_policy": "completion_watchdog",
        },
        "program_scope": dict(launcher.FIXTURE_PROGRAM_SCOPE),
        "validation_clock": {
            "fixed_success_timer_seconds": None,
            "policy": "completion_watchdog",
            "worldserver_starts": 1,
            "authserver_starts": 0,
            "retries": 0,
        },
    }
    descriptor = {
        "schema": "cata_raid_active_work_unit_v1",
        "work_unit": TEST_WORK_UNIT,
        "owner_skill": authority["descriptor_owner_skill"],
        "classification": authority["descriptor_classification"],
        "raid": authority["scenario"]["raid"],
        "boss": authority["scenario"]["boss"],
        "mode": authority["scenario"]["mode"],
        "observed_at_commit": source_commit,
        "immutable_input_commit": source_commit,
        "fixture_expansion": dict(authority["fixture_expansion"]),
        "program_scope": dict(authority["program_scope"]),
        "validation_clock": dict(authority["validation_clock"]),
        "launcher_authority": authority,
        "source_handoff": {
            "path": "experiments/configs/future_fixture_handoff.json",
            "sha256": "0" * 64,
            "source_commit": source_commit,
            "source_tree": source_tree,
        },
    }
    return descriptor, handoff


def _commit_authority_fixture(
    root: Path, descriptor: dict, handoff: dict, *, bind_hash: bool = True,
) -> None:
    configs = root / "experiments/configs"
    handoff_path = root / descriptor["source_handoff"]["path"]
    _write(handoff_path, launcher._canonical_bytes(handoff))
    if bind_hash:
        descriptor["source_handoff"]["sha256"] = launcher._sha256_bytes(
            handoff_path.read_bytes()
        )
    _write(
        configs / "cata_raid_active_work_unit_v1.json",
        launcher._canonical_bytes(descriptor),
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "fixture"],
        check=True, capture_output=True,
    )


def _init_source_repo(root: Path) -> tuple[str, str]:
    subprocess.run(
        ["git", "init", "-b", "main", str(root)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Test"], check=True,
    )
    policy = ROOT / launcher.POLICY_RELATIVE_PATH
    _write(root / launcher.POLICY_RELATIVE_PATH, policy.read_bytes())
    _write(root / "provenance.txt", b"reviewed source\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "reviewed source"],
        check=True, capture_output=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return commit, tree


def _divergent_source(root: Path) -> tuple[str, str]:
    subprocess.run(
        ["git", "-C", str(root), "checkout", "--orphan", "divergent"],
        check=True, capture_output=True,
    )
    _write(root / "divergent.txt", b"unrelated source\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "divergent source"],
        check=True, capture_output=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(root), "checkout", "main"],
        check=True, capture_output=True,
    )
    return commit, tree


def _production_request(tmp_path: Path, root: Path) -> dict:
    external = tmp_path / "external"
    request = _request(external, TEST_WORK_UNIT)
    request["worktree"] = str(root.resolve())
    return request


def test_generic_authority_composes_nonhistorical_fixture_through_production_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.undo()
    root = (tmp_path / "source").resolve()
    source_commit, source_tree = _init_source_repo(root)
    descriptor, handoff = _authority_fixture(source_commit, source_tree)
    _commit_authority_fixture(root, descriptor, handoff)
    monkeypatch.setattr(launcher, "ROOT", root)
    plan = launcher.compose_plan(_production_request(tmp_path, root))
    assert plan["schema"] == launcher.PREBUILD_SCHEMA
    assert plan["source"]["active_descriptor_sha256"] == launcher._sha256_bytes(
        (root / "experiments/configs/cata_raid_active_work_unit_v1.json").read_bytes()
    )
    assert plan["source"]["source_handoff_sha256"] == descriptor[
        "source_handoff"
    ]["sha256"]
    assert not (root / "build").exists()
    assert not Path(_production_request(tmp_path, root)["run_root"]).exists()


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("dirty", "source_worktree_dirty"),
        ("stale", "source_handoff_identity_invalid"),
        ("hash", "source_handoff_identity_invalid"),
        ("owner", "active_work_unit_mismatch"),
        ("classification", "active_work_unit_mismatch"),
        ("budget", "launcher_authority_scope_invalid"),
        ("scenario", "launcher_authority_scope_invalid"),
        ("clock", "launcher_authority_scope_invalid"),
        ("handoff", "source_handoff_identity_invalid"),
        ("prose", "source_handoff_identity_invalid"),
        ("request", "active_work_unit_mismatch"),
        ("nonexistent_source", "source_handoff_provenance_invalid"),
        ("wrong_source_tree", "source_handoff_provenance_invalid"),
        ("nonancestor_source", "source_handoff_provenance_invalid"),
        ("coherent_owner", "launcher_authority_scope_invalid"),
        ("coherent_classification", "launcher_authority_scope_invalid"),
        ("coherent_scenario", "launcher_authority_scope_invalid"),
        ("coherent_gameplay", "launcher_authority_scope_invalid"),
        ("coherent_acceptance", "launcher_authority_scope_invalid"),
    ],
)
def test_generic_authority_mismatches_fail_before_plan_or_runner_action(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str, reason: str,
) -> None:
    monkeypatch.undo()
    root = (tmp_path / "source").resolve()
    source_commit, source_tree = _init_source_repo(root)
    if case == "nonancestor_source":
        source_commit, source_tree = _divergent_source(root)
    descriptor, handoff = _authority_fixture(source_commit, source_tree)
    bind_hash = case != "hash"
    if case == "stale":
        descriptor["observed_at_commit"] = "3" * 40
    elif case == "owner":
        descriptor["owner_skill"] = "raid-evidence-lifecycle"
    elif case == "classification":
        descriptor["classification"] = "historical_fixture"
    elif case == "budget":
        descriptor["fixture_expansion"]["worldserver_starts"] = 2
    elif case == "scenario":
        descriptor["boss"] = "historical_boss"
    elif case == "clock":
        descriptor["validation_clock"]["policy"] = "fixed_timer"
    elif case == "handoff":
        handoff["work_unit_id"] = "evidence:substituted_handoff"
    elif case == "prose":
        handoff["next_work_unit"]["required_action"] = (
            "Use a historical canary's caller-authored prose instead."
        )
    elif case == "nonexistent_source":
        nonexistent = "3" * 40
        descriptor["observed_at_commit"] = nonexistent
        descriptor["immutable_input_commit"] = nonexistent
        descriptor["source_handoff"]["source_commit"] = nonexistent
        handoff["source"]["commit"] = nonexistent
    elif case == "wrong_source_tree":
        wrong_tree = "4" * 40
        descriptor["source_handoff"]["source_tree"] = wrong_tree
        handoff["source"]["tree"] = wrong_tree
    elif case == "coherent_owner":
        wrong_owner = "raid-evidence-lifecycle"
        descriptor["owner_skill"] = wrong_owner
        descriptor["launcher_authority"]["descriptor_owner_skill"] = wrong_owner
        handoff["next_work_unit"]["owner_skill"] = wrong_owner
    elif case == "coherent_classification":
        wrong_classification = "historical_fixture"
        descriptor["classification"] = wrong_classification
        descriptor["launcher_authority"][
            "descriptor_classification"
        ] = wrong_classification
    elif case == "coherent_scenario":
        descriptor["raid"] = "historical_raid"
        descriptor["launcher_authority"]["scenario"][
            "raid"
        ] = "historical_raid"
    elif case == "coherent_gameplay":
        descriptor["program_scope"]["gameplay_mutations_allowed"] = True
        descriptor["launcher_authority"]["program_scope"][
            "gameplay_mutations_allowed"
        ] = True
    elif case == "coherent_acceptance":
        descriptor["program_scope"]["acceptance_admitted"] = True
        descriptor["launcher_authority"]["program_scope"][
            "acceptance_admitted"
        ] = True
    _commit_authority_fixture(root, descriptor, handoff, bind_hash=bind_hash)
    if case == "dirty":
        (root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "ROOT", root)
    request = _production_request(tmp_path, root)
    if case == "request":
        request["expected_work_unit"] = "shard:different_future_fixture"
    with pytest.raises(launcher.ReplayPlanError, match=reason):
        launcher.compose_plan(request)
    assert not (root / "build").exists()
    assert not Path(request["run_root"]).exists()
