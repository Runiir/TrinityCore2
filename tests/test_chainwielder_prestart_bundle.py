from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

import tools.raid_program.canonical_route_staging as canonical_staging
import tools.raid_program.chainwielder_prestart_bundle as prestart_bundle
import tools.raid_program.tracked_runtime_config_derivation as runtime_config
from tools.raid_program.canonical_route_staging import stage_tracked_snapshot
from tools.raid_program.chainwielder_prestart_bundle import (
    ACTOR_GUID,
    BUNDLE_NAMES,
    BundleError,
    SCENARIO_ID,
    TRACKED_LEDGER_RELATIVE_PATH,
    create_bundle,
    verify_bundle,
)
from tools.raid_program.chainwielder_prestart_bundle import (
    PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE,
)
from tools.raid_program.capture_setup import controller_route_hold_runtime_manifest_identity
from tools.raid_program.controller_route_hold import (
    ControllerRouteHoldScheduler,
    controller_route_hold_launch_identity,
)
from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    FIXTURE_EXPANSION_PURPOSE,
    RecurrenceAdmissionError,
    chainwielder_checkpoint_seal,
    build_runtime_profile_suffix_manifest,
    create_recurrence_admission,
    sha256_file,
    verify_recurrence_admission,
)

def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, text=True,
        capture_output=True,
    ).stdout.strip()

def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _gate(_receipt: Path, _policy: Path) -> dict[str, object]:
    return {"valid": True, "gate_bearing": True}

def _profile_authority(
    root: Path, route: Path, profile_path: Path, *, recorded_route: Path | None = None,
) -> dict[str, str]:
    source_path = root / prestart_bundle.PROFILE_MANIFEST_RELATIVE_PATH
    source = json.loads(source_path.read_text(encoding="utf-8"))
    runtime, overlay = build_runtime_profile_suffix_manifest(
        source_manifest=source, runtime_profile=SCENARIO_ID,
        route_manifest_path=recorded_route or route,
    )
    _write_json(profile_path, runtime)
    overlay.update({
        "source_profile_manifest_sha256": sha256_file(source_path),
        "runtime_profile_manifest_sha256": sha256_file(profile_path),
        "runtime_route_manifest_sha256": sha256_file(route),
    })
    return overlay


@pytest.fixture(autouse=True)
def _stub_external_build_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        prestart_bundle, "_verify_gate_bearing_build_receipt", _gate
    )

def _fixture(
    tmp_path: Path,
    *, base_text: str = 'BotWorld.RuntimeProfile = "old"\nBotWorld.AutoStart = 1\n',
) -> dict[str, object]:
    root = tmp_path / "source"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "tracked.txt").write_text("source\n", encoding="utf-8")
    profile_manifest = root / "dataset/bot_runtime_profiles/profiles.json"
    profile_manifest.parent.mkdir(parents=True)
    _write_json(profile_manifest, {
        "schema": "bot_world_runtime_profiles_v1",
        "profiles": [
            {
                "name": SCENARIO_ID,
                "description": "selected diagnostic profile",
                "target_population": 10,
                "pool_tag_filter": SCENARIO_ID,
                "allow_raids": True,
                "diagnostic_only": True,
                "validation_route": {
                    "enable": True,
                    "manifest_path": "dataset/validation_scenarios/routes.jsonl",
                    "advance_mode": "terminal",
                    "scenario_id": SCENARIO_ID,
                },
            },
            {"name": "foreign", "validation_route": {"enable": False}},
        ],
    })
    base_source = root / "base.conf"
    base_source.write_text(base_text, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "source")
    external = tmp_path / "inputs"
    external.mkdir()
    binary = tmp_path / "worldserver"
    binary.write_bytes(b"\x7fELFchainwielder")
    receipt = external / "build.json"
    source_commit = _git(root, "rev-parse", "HEAD")
    source_tree = _git(root, "rev-parse", "HEAD^{tree}")
    source_snapshot = {
        "commit": source_commit,
        "tree": source_tree,
        "clean": True,
        "dirty": False,
        "porcelain_sha256": hashlib.sha256(b"").hexdigest(),
    }
    _write_json(receipt, {
        "classification": "success",
        "exit_code": 0,
        "commit": source_commit,
        "source_identity": {
            stage: dict(source_snapshot)
            for stage in ("request", "admission", "completion")
        },
        "output_artifacts": [{
            "kind": "worldserver_elf", "path": str(binary.resolve()),
            "sha256": sha256_file(binary), "produced_by_ticket": True,
        }],
    })
    policy = external / "policy.json"
    _write_json(policy, {"test": "policy"})
    decision = external / "decision.json"
    _write_json(decision, {
        "build_admitted": False,
        "canary_admitted": False,
        "fixture_expansion_admitted": True,
        "fixture_expansion_target_ids": [CHAINWIELDER_CHECKPOINT_FIXTURE_ID],
        "fixture_expansion_requests": [],
        "invalidated_fixture_ids": [],
        "failing_fixture_ids": [],
        "missing_fixture_ids": [],
        "pending_fixture_ids": [CHAINWIELDER_CHECKPOINT_FIXTURE_ID],
        "stale_fixture_ids": [],
    })
    suite = external / "suite.json"
    _write_json(suite, {
        "schema": "trinity_raid_regression_suite_receipt_v1",
        "source_identity": _git(root, "rev-parse", "HEAD"),
        "verifications": [{
            "fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
            "fixture_revision": 1,
            "passed": True,
        }],
    })
    route = external / "route.json"
    roster = [{
        "roster_slot_id": f"slot-{index}",
        "guid": 30000 + index,
        "name": f"Bot{index}",
        "class_spec": "test_spec",
        "role": "dps" if index > 5 else "support",
    } for index in range(1, 11)]
    shared = {
        "scenario_id": SCENARIO_ID,
        "runtime_profile_id": SCENARIO_ID,
        "map_id": 669,
        "expected_bot_count": 10,
        "bot_start_map_id": 669,
        "bot_start_x": -345.872,
        "bot_start_y": -224.344,
        "bot_start_z": 193.127,
        "bot_start_o": 0.0,
        "roster_identity": roster,
        "diagnostic_only": True,
        "diagnostic_parent_scenario_id": "blackwing_descent_10n",
        "diagnostic_prerequisite_state": {
            "certifies_predecessors": False,
            "precompleted_boss_entries": [],
        },
    }
    _write_json(route, {
        "schema": "bot_live_validation_route_manifest_v1",
        "scenario_id": SCENARIO_ID,
        "routes": [
            {**shared, "step": 1, "route_node_id": "bwd.entry.regroup",
             "kind": "regroup", "source_entry": 0},
            {**shared, "step": 2,
             "route_node_id": "bwd.magmaw.chainwielder", "kind": "trash",
             "source_entry": 42649},
            {**shared, "step": 3,
             "route_node_id": "bwd.magmaw.drudges", "kind": "trash",
             "source_entry": 42362},
            {**shared, "step": 4,
             "route_node_id": "bwd.magmaw.encounter", "kind": "boss",
             "source_entry": 41570},
        ],
    })
    base_root = tmp_path / "base-snapshot"
    base_root.mkdir()
    base_stage = stage_tracked_snapshot(
        worktree=root,
        source_path=base_source,
        expected_sha256=sha256_file(base_source),
        external_run_root=base_root,
        artifact_label="base-runtime-config",
    )
    base = Path(base_stage["snapshot_path"])
    ledger = external / "ledger.json"
    _write_json(ledger, {"schema": "recurrence_ledger_test_v1"})
    paths = {
        "binary": binary,
        "build_receipt": receipt,
        "build_policy": policy,
        "decision": decision,
        "suite_receipt": suite,
        "route_manifest": route,
        "base_runtime_config": base,
        "base_runtime_config_source": base_source,
        "base_runtime_config_receipt": Path(base_stage["receipt_path"]),
        "ledger": ledger,
    }
    return {
        "root": root,
        "external": external,
        "output": tmp_path / "bundle",
        "paths": paths,
        "kwargs": {
            "worktree": root,
            "output_dir": tmp_path / "bundle",
            "source_commit": _git(root, "rev-parse", "HEAD"),
            "source_tree": _git(root, "rev-parse", "HEAD^{tree}"),
            **{
                key: path for key, path in paths.items()
                if key not in {"base_runtime_config", "base_runtime_config_source"}
            },
            **{
                f"{key}_sha256": sha256_file(path)
                for key, path in paths.items()
                if key not in {"base_runtime_config", "base_runtime_config_source"}
            },
            "scenario_id": SCENARIO_ID,
            "runtime_profile_id": SCENARIO_ID,
            "pool_tag": SCENARIO_ID,
            "actor_guid": ACTOR_GUID,
            "checkpoint_fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        },
    }

def _create(fixture: dict[str, object]) -> dict[str, object]:
    return create_bundle(**fixture["kwargs"])  # type: ignore[arg-type]

def _restage_base_runtime_config(fixture: dict[str, object]) -> None:
    root = fixture["root"]
    source = fixture["paths"]["base_runtime_config_source"]
    stage_root = fixture["external"].parent / (
        "base-snapshot-" + _git(root, "rev-parse", "HEAD")[:12]
    )
    stage_root.mkdir()
    staged = stage_tracked_snapshot(
        worktree=root, source_path=source,
        expected_sha256=sha256_file(source), external_run_root=stage_root,
        artifact_label="base-runtime-config",
    )
    fixture["paths"]["base_runtime_config"] = Path(staged["snapshot_path"])
    fixture["paths"]["base_runtime_config_receipt"] = Path(
        staged["receipt_path"]
    )
    fixture["kwargs"]["base_runtime_config_receipt"] = Path(
        staged["receipt_path"]
    )
    fixture["kwargs"]["base_runtime_config_receipt_sha256"] = str(
        staged["receipt_sha256"]
    )

def _use_tracked_ledger(fixture: dict[str, object]) -> Path:
    root = fixture["root"]
    paths = fixture["paths"]
    kwargs = fixture["kwargs"]
    ledger = root / TRACKED_LEDGER_RELATIVE_PATH
    ledger.parent.mkdir(parents=True)
    shutil.copyfile(paths["ledger"], ledger)
    _git(root, "add", TRACKED_LEDGER_RELATIVE_PATH.as_posix())
    _git(root, "commit", "-m", "track recurrence ledger")

    source_commit = _git(root, "rev-parse", "HEAD")
    receipt = paths["build_receipt"]
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    receipt_value["commit"] = source_commit
    source_tree = _git(root, "rev-parse", "HEAD^{tree}")
    source_snapshot = {
        "commit": source_commit,
        "tree": source_tree,
        "clean": True,
        "dirty": False,
        "porcelain_sha256": hashlib.sha256(b"").hexdigest(),
    }
    receipt_value["source_identity"] = {
        stage: dict(source_snapshot)
        for stage in ("request", "admission", "completion")
    }
    _write_json(receipt, receipt_value)
    suite = paths["suite_receipt"]
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["source_identity"] = source_commit
    _write_json(suite, suite_value)

    paths["ledger"] = ledger
    kwargs.update({
        "source_commit": source_commit,
        "source_tree": source_tree,
        "ledger": ledger,
        "ledger_sha256": sha256_file(ledger),
        "build_receipt_sha256": sha256_file(receipt),
        "suite_receipt_sha256": sha256_file(suite),
    })
    _restage_base_runtime_config(fixture)
    return ledger

def test_v6_manual_missing_flag_fails_before_atomic_bundle_passes_after(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    root = fixture["root"]
    manual = tmp_path / "manual"
    manual.mkdir()
    route = manual / "route.json"
    shutil.copyfile(paths["route_manifest"], route)
    config = manual / "worldserver.conf"
    profile = manual / "runtime_profiles.json"
    overlay = _profile_authority(root, route, profile)
    seal = chainwielder_checkpoint_seal(
        worktree=root, binary=paths["binary"],
        build_receipt=paths["build_receipt"], decision=paths["decision"],
        profile_manifest=profile, runtime_profile_overlay=overlay,
        expected_runtime_profile_id=SCENARIO_ID,
    )
    config.write_text(
        f'BotWorld.ValidationRoute.ManifestPath = "{route.resolve()}"\n'
        f'BotWorld.ProfileManifest = "{profile.resolve()}"\n'
        f'BotWorld.RuntimeProfile = "{SCENARIO_ID}"\n'
        "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable = 1\n"
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.FixtureId = "{CHAINWIELDER_CHECKPOINT_FIXTURE_ID}"\n'
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.SealSha256 = "{seal["seal_sha256"]}"\n'
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.SourceCommit = "{fixture["kwargs"]["source_commit"]}"\n',
        encoding="utf-8",
    )
    admission = manual / "admission.json"
    create_recurrence_admission(
        output=admission, worktree=root, binary=paths["binary"],
        build_receipt=paths["build_receipt"], runtime_config=config,
        route_manifest=route, ledger=paths["ledger"], decision=paths["decision"],
        suite_receipt=paths["suite_receipt"], purpose=FIXTURE_EXPANSION_PURPOSE,
        profile_manifest=profile, runtime_profile_overlay=overlay,
        expected_runtime_profile_id=SCENARIO_ID,
    )
    with pytest.raises(
        RecurrenceAdmissionError, match="fixture_expansion_checkpoint_disabled"
    ):
        verify_recurrence_admission(
            admission_path=admission, expected_sha256=sha256_file(admission),
            worktree=root, binary=paths["binary"],
                build_receipt=paths["build_receipt"], runtime_config=config,
                profile_manifest=profile,
                expected_runtime_profile_id=SCENARIO_ID,
                required_purpose=FIXTURE_EXPANSION_PURPOSE,
        )

    result = _create(fixture)
    assert result["valid"] is True
    assert result["pre_rename_verified"] is True

def test_bundle_is_deterministic_and_does_not_mutate_inputs(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    before = {key: sha256_file(path) for key, path in paths.items()}
    _create(fixture)
    output = fixture["output"]
    first = {path.name: path.read_bytes() for path in output.iterdir()}
    shutil.rmtree(output)
    _create(fixture)
    second = {path.name: path.read_bytes() for path in output.iterdir()}
    assert first == second
    assert before == {key: sha256_file(path) for key, path in paths.items()}


def test_expected_launch_argv_binds_the_complete_personal_threat_target(
    tmp_path: Path,
) -> None:
    target = {
        "actor_guid": 30008,
        "scope_key": PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE,
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 3,
        "parent_wave_generation": (1 << 63) | 1,
        "parent_generation_authoritative": False,
    }
    argv = prestart_bundle.expected_launch_argv(
        worktree=tmp_path, binary=tmp_path / "worldserver",
        output_dir=tmp_path / "bundle", admission_sha256="a" * 64,
        personal_threat_episode_target=target,
    )
    assert argv[argv.index("--personal-threat-episode-actor-guid") + 1] == "30008"
    assert argv[argv.index("--personal-threat-episode-scope-key") + 1] == target[
        "scope_key"
    ]
    assert argv[argv.index("--personal-threat-episode-route-node-id") + 1] == (
        "bwd.magmaw.encounter"
    )
    assert argv[argv.index("--personal-threat-episode-route-generation") + 1] == "3"
    assert argv[argv.index("--personal-threat-episode-parent-wave-generation") + 1] == str(
        (1 << 63) | 1
    )
    assert "--no-personal-threat-episode-parent-generation-authoritative" in argv
    with pytest.raises(BundleError, match="scope_template_invalid"):
        prestart_bundle.expected_launch_argv(
            worktree=tmp_path, binary=tmp_path / "worldserver",
            output_dir=tmp_path / "bundle", admission_sha256="a" * 64,
            personal_threat_episode_target={**target, "scope_key": "attempt3"},
        )

def _native_hold(identity, *, route_node_id: str, route_sha256: str) -> dict:
    return {
        "ok": True,
        "phase": "held",
        "cohort_id": "cohort-a",
        "server_epoch": 71,
        "attempt_id": 9,
        "scenario_id": identity.scenario_id,
        "runtime_profile": identity.runtime_profile,
        "route_manifest_sha256": route_sha256,
        "route_generation": 1,
        "route_node_id": route_node_id,
        "actor_guid": identity.actor_guid,
        "fixture_id": identity.fixture_id,
        "seal_sha256": identity.seal_sha256,
        "source_commit": identity.source_commit,
        "acquire_count": 1,
        "arm_ack_count": 0,
        "checkpoint_terminal": False,
        "release_count": 0,
    }

def test_target_suffix_reproduces_v19_and_binds_runtime_identity(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    result = _create(fixture)
    output = fixture["output"]
    source = json.loads((output / BUNDLE_NAMES["source_route_manifest"])
                        .read_text(encoding="utf-8"))
    runtime = json.loads((output / BUNDLE_NAMES["route_manifest"])
                         .read_text(encoding="utf-8"))
    source_rows = source["routes"]
    runtime_rows = runtime["routes"]
    assert [row["route_node_id"] for row in source_rows] == [
        "bwd.entry.regroup", "bwd.magmaw.chainwielder",
        "bwd.magmaw.drudges", "bwd.magmaw.encounter",
    ]
    assert [row["route_node_id"] for row in runtime_rows] == [
        "bwd.magmaw.chainwielder", "bwd.magmaw.drudges",
        "bwd.magmaw.encounter",
    ]
    assert [row["step"] for row in runtime_rows] == [1, 2, 3]
    for source_row, runtime_row in zip(source_rows[1:], runtime_rows):
        assert {key: value for key, value in source_row.items() if key != "step"} \
            == {key: value for key, value in runtime_row.items() if key != "step"}

    launch = json.loads((output / BUNDLE_NAMES["launch_contract"])
                        .read_text(encoding="utf-8"))
    route_identity = launch["route_identity"]
    assert route_identity == result["route_identity"]
    assert route_identity["source_initial_node_id"] == "bwd.entry.regroup"
    assert route_identity["runtime_initial_node_id"] \
        == route_identity["checkpoint_target_node_id"] \
        == "bwd.magmaw.chainwielder"
    assert route_identity["source_route_sha256"] == sha256_file(
        output / BUNDLE_NAMES["source_route_manifest"]
    )
    assert route_identity["runtime_route_sha256"] == sha256_file(
        output / BUNDLE_NAMES["route_manifest"]
    )
    profile_manifest = json.loads(
        (output / BUNDLE_NAMES["profile_manifest"]).read_text(encoding="utf-8")
    )
    assert [row["name"] for row in profile_manifest["profiles"]] == [SCENARIO_ID]
    selected = profile_manifest["profiles"][0]
    assert selected["description"] == "selected diagnostic profile"
    assert selected["target_population"] == 10
    assert selected["diagnostic_only"] is True
    assert selected["validation_route"]["manifest_path"] == str(
        (output / BUNDLE_NAMES["route_manifest"]).resolve()
    )
    assert launch["runtime_profile_overlay"][
        "runtime_profile_manifest_sha256"
    ] == sha256_file(output / BUNDLE_NAMES["profile_manifest"])

    # V23 fail-before: native applies the selected profile after config, so a
    # canonical profile manifest would overwrite the suffix route in config.
    canonical_config = tmp_path / "canonical-overlay.conf"
    config_text = (output / BUNDLE_NAMES["runtime_config"]).read_text(
        encoding="utf-8"
    )
    source_profiles = fixture["root"] / prestart_bundle.PROFILE_MANIFEST_RELATIVE_PATH
    canonical_profiles = tmp_path / "canonical-selected-profile.json"
    canonical_payload = json.loads(source_profiles.read_text(encoding="utf-8"))
    canonical_payload["profiles"] = [
        row for row in canonical_payload["profiles"]
        if row.get("name") == SCENARIO_ID
    ]
    _write_json(canonical_profiles, canonical_payload)
    canonical_config.write_text(
        config_text.replace(
            str((output / BUNDLE_NAMES["profile_manifest"]).resolve()),
            str(canonical_profiles.resolve()),
        ),
        encoding="utf-8",
    )
    canonical_admission = tmp_path / "canonical-overlay-admission.json"
    admission_payload = json.loads(
        (output / BUNDLE_NAMES["admission"]).read_text(encoding="utf-8")
    )
    admission_payload["bindings"]["profile_manifest"] = {
        "path": str(canonical_profiles.resolve()),
        "sha256": sha256_file(canonical_profiles),
    }
    admission_payload["bindings"]["runtime_config"] = {
        "path": str(canonical_config.resolve()),
        "sha256": sha256_file(canonical_config),
    }
    _write_json(canonical_admission, admission_payload)
    with pytest.raises(
        RecurrenceAdmissionError, match="runtime_profile_overlay_identity_mismatch"
    ):
        verify_recurrence_admission(
            admission_path=canonical_admission,
            expected_sha256=sha256_file(canonical_admission),
            worktree=fixture["root"], binary=fixture["paths"]["binary"],
            build_receipt=output / BUNDLE_NAMES["build_receipt"],
            runtime_config=canonical_config, profile_manifest=canonical_profiles,
            expected_runtime_profile_id=SCENARIO_ID,
            required_purpose=FIXTURE_EXPANSION_PURPOSE,
        )

    admission = verify_recurrence_admission(
        admission_path=output / BUNDLE_NAMES["admission"],
        expected_sha256=sha256_file(output / BUNDLE_NAMES["admission"]),
        worktree=fixture["root"], binary=fixture["paths"]["binary"],
        build_receipt=output / BUNDLE_NAMES["build_receipt"],
        runtime_config=output / BUNDLE_NAMES["runtime_config"],
        profile_manifest=output / BUNDLE_NAMES["profile_manifest"],
        expected_runtime_profile_id=SCENARIO_ID,
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
    )
    projected = controller_route_hold_runtime_manifest_identity(
        config=output / BUNDLE_NAMES["runtime_config"],
        recurrence_admission=admission,
        scenario_id=SCENARIO_ID,
        runtime_profile=SCENARIO_ID,
    )
    identity = controller_route_hold_launch_identity(
        recurrence_admission=admission,
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
        actor_guid=ACTOR_GUID,
        scenario_id=SCENARIO_ID,
        runtime_profile=SCENARIO_ID,
        pool_tag=SCENARIO_ID,
        route_manifest_sha256=projected["route_manifest_sha256"],
        route_node_id=projected["initial_route_node_id"],
    )
    assert identity is not None
    assert projected["profile_manifest_sha256"] == sha256_file(
        output / BUNDLE_NAMES["profile_manifest"]
    )
    assert verify_bundle(output)["valid"] is True

    fail_before_identity = controller_route_hold_launch_identity(
        recurrence_admission=admission,
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
        actor_guid=ACTOR_GUID,
        scenario_id=SCENARIO_ID,
        runtime_profile=SCENARIO_ID,
        pool_tag=SCENARIO_ID,
        route_manifest_sha256=route_identity["source_route_sha256"],
        route_node_id=route_identity["checkpoint_target_node_id"],
    )
    assert fail_before_identity is not None
    old = ControllerRouteHoldScheduler(fail_before_identity)
    old.start()
    assert old.observe(_native_hold(
        fail_before_identity,
        route_node_id=route_identity["source_initial_node_id"],
        route_sha256=route_identity["source_route_sha256"],
    )) == []
    assert old.failure_reason == "controller_route_hold_route_node_id_mismatch"

    repaired = ControllerRouteHoldScheduler(identity)
    repaired.start()
    assert repaired.observe(_native_hold(
        identity,
        route_node_id=route_identity["runtime_initial_node_id"],
        route_sha256=route_identity["runtime_route_sha256"],
    )) == ["botauto status"]
    assert repaired.failure_reason is None

@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing_target", "route_checkpoint_node_missing_or_ambiguous"),
        ("duplicate_target", "route_checkpoint_node_missing_or_ambiguous"),
        ("missing_drudges", "route_checkpoint_required_suffix_mismatch"),
        ("invariant_drift", "route_suffix_invariant_drift"),
    ],
)
def test_target_suffix_fails_closed_on_contract_drift(
    tmp_path: Path, mutation: str, reason: str,
) -> None:
    fixture = _fixture(tmp_path)
    route = fixture["paths"]["route_manifest"]
    payload = json.loads(route.read_text(encoding="utf-8"))
    rows = payload["routes"]
    if mutation == "missing_target":
        rows.pop(1)
    elif mutation == "duplicate_target":
        rows.insert(2, dict(rows[1]))
    elif mutation == "missing_drudges":
        rows.pop(2)
    else:
        rows[2]["bot_start_x"] += 1.0
    _write_json(route, payload)
    fixture["kwargs"]["route_manifest_sha256"] = sha256_file(route)
    with pytest.raises(BundleError, match=reason):
        _create(fixture)

def test_profile_suffix_rejects_ambiguous_selection_and_non_route_mutation(
    tmp_path: Path,
) -> None:
    source = {
        "schema": "bot_world_runtime_profiles_v1",
        "profiles": [
            {
                "name": "selected",
                "target_population": 10,
                "validation_route": {"manifest_path": "canonical.jsonl"},
            },
            {"name": "foreign", "validation_route": {"enable": False}},
        ],
    }
    route_path = tmp_path / "suffix.json"
    runtime, identity = build_runtime_profile_suffix_manifest(
        source_manifest=source, runtime_profile="selected",
        route_manifest_path=route_path,
    )
    assert [row["name"] for row in runtime["profiles"]] == ["selected"]

    duplicate = json.loads(json.dumps(source))
    duplicate["profiles"].append(dict(duplicate["profiles"][0]))
    with pytest.raises(
        ValueError, match="runtime_profile_source_selection_missing_or_duplicate"
    ):
        build_runtime_profile_suffix_manifest(
            source_manifest=duplicate, runtime_profile="selected",
            route_manifest_path=route_path,
        )
    with pytest.raises(
        ValueError, match="runtime_profile_source_selection_missing_or_duplicate"
    ):
        build_runtime_profile_suffix_manifest(
            source_manifest=source, runtime_profile="missing",
            route_manifest_path=route_path,
        )

    runtime["profiles"][0]["target_population"] = 9
    assert identity["runtime_selected_profile_sha256"] != hashlib.sha256(
        json.dumps(
            runtime["profiles"][0], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()

def test_exact_clean_tracked_ledger_is_copied_byte_identically(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    ledger = _use_tracked_ledger(fixture)

    result = _create(fixture)

    assert result["valid"] is True
    copied = fixture["output"] / BUNDLE_NAMES["ledger"]
    assert copied.read_bytes() == ledger.read_bytes()
    assert sha256_file(copied) == fixture["kwargs"]["ledger_sha256"]

def test_untracked_in_worktree_ledger_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["root"] / TRACKED_LEDGER_RELATIVE_PATH
    ledger.parent.mkdir(parents=True)
    shutil.copyfile(fixture["paths"]["ledger"], ledger)
    fixture["kwargs"].update({
        "ledger": ledger,
        "ledger_sha256": sha256_file(ledger),
    })

    with pytest.raises(BundleError, match="ledger_not_tracked_read_only_source"):
        _create(fixture)

def test_tracked_ledger_alias_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    ledger = _use_tracked_ledger(fixture)
    alias = fixture["external"] / "ledger-alias.json"
    alias.symlink_to(ledger)
    fixture["kwargs"].update({
        "ledger": alias,
        "ledger_sha256": sha256_file(alias),
    })

    with pytest.raises(BundleError, match="ledger_source_path_mismatch"):
        _create(fixture)

def test_dirty_tracked_ledger_is_rejected_even_with_matching_input_hash(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    ledger = _use_tracked_ledger(fixture)
    ledger.write_bytes(ledger.read_bytes() + b"dirty")
    fixture["kwargs"]["ledger_sha256"] = sha256_file(ledger)

    with pytest.raises(BundleError, match="source_worktree_dirty"):
        _create(fixture)

def test_clean_tracked_ledger_wrong_hash_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _use_tracked_ledger(fixture)
    fixture["kwargs"]["ledger_sha256"] = "0" * 64

    with pytest.raises(BundleError, match="ledger_hash_mismatch"):
        _create(fixture)

def test_existing_empty_output_directory_is_atomically_replaced(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["output"].mkdir()

    assert _create(fixture)["valid"] is True
    assert (fixture["output"] / BUNDLE_NAMES["launch_contract"]).is_file()

@pytest.mark.parametrize(
    "name",
    [
        "source_route_manifest", "route_manifest", "profile_manifest",
        "runtime_config",
        "build_receipt", "ledger",
        "decision", "suite_receipt", "checkpoint_seal", "admission",
        "launch_contract",
        "base_runtime_config", "build_policy",
    ],
)
def test_verify_rejects_each_internal_material_tamper(
    tmp_path: Path, name: str,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    path = fixture["output"] / BUNDLE_NAMES[name]
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(BundleError, match="bundle_file_hash_mismatch"):
        verify_bundle(fixture["output"])

@pytest.mark.parametrize("name", ["binary"])
def test_verify_rejects_each_external_material_tamper(
    tmp_path: Path, name: str,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    path = fixture["paths"][name]
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(BundleError, match=f"{name}_hash_mismatch"):
        verify_bundle(fixture["output"])

def test_verify_rejects_partial_bundle(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    (fixture["output"] / BUNDLE_NAMES["admission"]).unlink()
    with pytest.raises(BundleError, match="bundle_partial_or_extra_files"):
        verify_bundle(fixture["output"])

def test_verify_reconstructs_the_complete_capture_argv(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    output = fixture["output"]
    launch_path = output / BUNDLE_NAMES["launch_contract"]
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    launch["launch_argv"].append("--observe-sec=300")
    _write_json(launch_path, launch)
    manifest_path = output / BUNDLE_NAMES["bundle_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        if row["path"] == BUNDLE_NAMES["launch_contract"]:
            row["sha256"] = sha256_file(launch_path)
    _write_json(manifest_path, manifest)
    with pytest.raises(BundleError, match="launch_argv_exact_binding_mismatch"):
        verify_bundle(output)

def test_verify_rejects_extra_directory_and_duplicate_manifest_rows(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    output = fixture["output"]
    (output / "unexpected").mkdir()
    with pytest.raises(BundleError, match="bundle_partial_or_extra_files"):
        verify_bundle(output)
    (output / "unexpected").rmdir()
    manifest_path = output / BUNDLE_NAMES["bundle_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].append(dict(manifest["files"][0]))
    _write_json(manifest_path, manifest)
    with pytest.raises(BundleError, match="bundle_manifest_incomplete"):
        verify_bundle(output)

def test_verify_rejects_non_object_manifest_row_as_typed_error(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    manifest_path = fixture["output"] / BUNDLE_NAMES["bundle_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0] = "invalid"
    _write_json(manifest_path, manifest)
    with pytest.raises(BundleError, match="bundle_manifest_incomplete"):
        verify_bundle(fixture["output"])

@pytest.mark.parametrize("mutation", ["reorder", "extra_key"])
def test_verify_requires_exact_manifest_rows(
    tmp_path: Path, mutation: str,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    manifest_path = fixture["output"] / BUNDLE_NAMES["bundle_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "reorder":
        manifest["files"][0], manifest["files"][1] = (
            manifest["files"][1], manifest["files"][0]
        )
    else:
        manifest["files"][0]["extra"] = True
    _write_json(manifest_path, manifest)
    with pytest.raises(BundleError, match="bundle_manifest_incomplete"):
        verify_bundle(fixture["output"])

def test_conflicting_duplicate_required_config_fails_closed(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        base_text="BotWorld.AutoStart = 0\nBotWorld.AutoStart = 1\n",
    )
    with pytest.raises(BundleError, match="config_duplicate_key:BotWorld.AutoStart"):
        _create(fixture)
    assert not fixture["output"].exists()
    failure = fixture["output"].with_name("bundle.failure.json")
    assert json.loads(failure.read_text(encoding="utf-8"))["launchable"] is False

def test_tracked_base_config_fail_before_then_verified_snapshot_passes(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    source = fixture["paths"]["base_runtime_config_source"]
    with pytest.raises(
        BundleError, match="base_runtime_config_inside_mutable_worktree",
    ):
        prestart_bundle._validate_locations(
            worktree=fixture["root"], output_dir=fixture["output"],
            material_inputs={"base_runtime_config": source},
            binary=fixture["paths"]["binary"], capture_paths=[],
        )

    assert _create(fixture)["valid"] is True
    assert (
        fixture["output"] / BUNDLE_NAMES["base_runtime_config"]
    ).read_bytes() == source.read_bytes()

def test_bundle_cannot_bypass_verified_base_config_receipt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    source = fixture["paths"]["base_runtime_config_source"]
    fixture["kwargs"]["base_runtime_config_receipt"] = source
    fixture["kwargs"]["base_runtime_config_receipt_sha256"] = sha256_file(source)

    with pytest.raises(
        BundleError, match="tracked_snapshot_receipt_location_invalid",
    ):
        _create(fixture)
    assert not fixture["output"].exists()

def test_bundle_rejects_verified_snapshot_mutation_before_copy(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["paths"]["base_runtime_config"].write_bytes(b"mutated\n")

    with pytest.raises(BundleError, match="tracked_snapshot_binding_mismatch"):
        _create(fixture)
    assert not fixture["output"].exists()

def test_output_inside_worktree_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["kwargs"]["output_dir"] = fixture["root"] / "bundle"
    with pytest.raises(BundleError, match="output_inside_worktree"):
        _create(fixture)

def test_launch_contract_is_exact_one_start_completion_watchdog(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    result = _create(fixture)
    launch = json.loads(
        (fixture["output"] / BUNDLE_NAMES["launch_contract"]).read_text(encoding="utf-8")
    )
    assert launch["start_budget"] == {
        "owner": "capture_controller", "worldserver_starts": 1,
    }
    assert launch["completion_watchdog"]["duration_policy"] == "completion-watchdog"
    assert launch["fixed_success_timer_seconds"] is None
    assert launch["expected_arm_predicates"]["emission_count"] == 1
    assert launch["expected_lifecycle_predicates"]["trigger"] == (
        "active_route_path"
    )
    assert launch["expected_lifecycle_predicates"][
        "triggered_by_active_route_path"
    ] is True
    assert launch["expected_lifecycle_predicates"][
        "triggered_by_armed_route_hazard_retry"
    ] is False
    assert launch["expected_lifecycle_predicates"]["outcome"] == (
        "route_identity_preserved_after_receiptless_hazard_rejection"
    )
    assert "--observe-sec" not in result["launch_argv"]

def test_wrong_actor_fixture_or_source_and_dirty_source_fail_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["kwargs"]["actor_guid"] = ACTOR_GUID + 1
    with pytest.raises(BundleError, match="chainwielder_identity_input_mismatch"):
        _create(fixture)
    fixture["kwargs"]["actor_guid"] = ACTOR_GUID
    fixture["kwargs"]["checkpoint_fixture_id"] = "wrong"
    with pytest.raises(BundleError, match="chainwielder_identity_input_mismatch"):
        _create(fixture)
    fixture["kwargs"]["checkpoint_fixture_id"] = CHAINWIELDER_CHECKPOINT_FIXTURE_ID
    fixture["kwargs"]["source_commit"] = "0" * 40
    with pytest.raises(BundleError, match="source_identity_mismatch"):
        _create(fixture)
    fixture["kwargs"]["source_commit"] = _git(fixture["root"], "rev-parse", "HEAD")
    (fixture["root"] / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(BundleError, match="source_worktree_dirty"):
        _create(fixture)

def test_atomic_relocation_is_sibling_only_and_default_verifier_unchanged(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    root = fixture["root"]
    final = tmp_path / "relocated"
    staging = tmp_path / ".relocated.staging-test"
    staging.mkdir()
    for key, name in {
        "build_receipt": "build.json", "route_manifest": "route.json",
        "ledger": "ledger.json", "decision": "decision.json",
        "suite_receipt": "suite.json",
    }.items():
        shutil.copyfile(paths[key], staging / name)
    overlay = _profile_authority(
        root, staging / "route.json", staging / "runtime_profiles.json",
        recorded_route=final / "route.json",
    )
    seal = chainwielder_checkpoint_seal(
        profile_manifest=staging / "runtime_profiles.json",
        runtime_profile_overlay=overlay,
        expected_runtime_profile_id=SCENARIO_ID,
        worktree=root, binary=paths["binary"], build_receipt=staging / "build.json",
        decision=staging / "decision.json",
    )
    config = staging / "config.conf"
    config.write_text(
        f'BotWorld.ValidationRoute.ManifestPath = "{final / "route.json"}"\n'
        f'BotWorld.ProfileManifest = "{final / "runtime_profiles.json"}"\n'
        f'BotWorld.RuntimeProfile = "{SCENARIO_ID}"\n'
        "BotWorld.ValidationRoute.PrepullCheckpointEnable = 1\n"
        "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable = 1\n"
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.FixtureId = "{CHAINWIELDER_CHECKPOINT_FIXTURE_ID}"\n'
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.SealSha256 = "{seal["seal_sha256"]}"\n'
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.SourceCommit = "{fixture["kwargs"]["source_commit"]}"\n',
        encoding="utf-8",
    )
    admission = staging / "admission.json"
    create_recurrence_admission(
        output=admission, worktree=root, binary=paths["binary"],
        build_receipt=staging / "build.json", runtime_config=config,
        route_manifest=staging / "route.json", ledger=staging / "ledger.json",
        decision=staging / "decision.json", suite_receipt=staging / "suite.json",
        purpose=FIXTURE_EXPANSION_PURPOSE,
        profile_manifest=staging / "runtime_profiles.json",
        runtime_profile_overlay=overlay,
        expected_runtime_profile_id=SCENARIO_ID,
        atomic_bundle_roots=(final, staging),
    )
    with pytest.raises(RecurrenceAdmissionError, match="build_receipt_path_mismatch"):
        verify_recurrence_admission(
            admission_path=admission, expected_sha256=sha256_file(admission),
            worktree=root, binary=paths["binary"], build_receipt=staging / "build.json",
            runtime_config=config, required_purpose=FIXTURE_EXPANSION_PURPOSE,
            profile_manifest=staging / "runtime_profiles.json",
            expected_runtime_profile_id=SCENARIO_ID,
        )
    assert verify_recurrence_admission(
        admission_path=admission, expected_sha256=sha256_file(admission),
        worktree=root, binary=paths["binary"], build_receipt=staging / "build.json",
        runtime_config=config, required_purpose=FIXTURE_EXPANSION_PURPOSE,
        profile_manifest=staging / "runtime_profiles.json",
        expected_runtime_profile_id=SCENARIO_ID,
        atomic_bundle_roots=(final, staging),
    )["valid"] is True
    with pytest.raises(RecurrenceAdmissionError, match="atomic_bundle_roots_invalid"):
        verify_recurrence_admission(
            admission_path=admission, expected_sha256=sha256_file(admission),
            worktree=root, binary=paths["binary"], build_receipt=staging / "build.json",
            runtime_config=config, required_purpose=FIXTURE_EXPANSION_PURPOSE,
            profile_manifest=staging / "runtime_profiles.json",
            expected_runtime_profile_id=SCENARIO_ID,
            atomic_bundle_roots=(final, tmp_path / "arbitrary" / "stage"),
        )

def test_snapshot_boundary_consumes_only_verified_derived_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "derived-source"
    root.mkdir()
    for relative in (runtime_config.TEMPLATE_PATH, runtime_config.RECIPE_PATH):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(Path(relative).read_bytes())
    contract_relative = "experiments/configs/runtime-contract.json"
    contract = root / contract_relative
    contract.parent.mkdir(parents=True)
    contract.write_bytes(Path(
        "experiments/configs/cata_raid_tracked_base_runtime_config_contract_v1.json"
    ).read_bytes())
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "derived source")
    output = tmp_path / "derived-output"
    output.mkdir()
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    derived = runtime_config.derive_runtime_config(
        worktree=root, contract_relative_path=contract_relative,
        expected_source_commit=commit, expected_source_tree=tree,
        external_run_root=output, destination_name="base-runtime.conf",
    )
    arguments = {
        "worktree": root, "receipt_path": Path(derived["receipt_path"]),
        "expected_receipt_sha256": derived["receipt_sha256"],
        "contract_relative_path": contract_relative,
        "expected_source_commit": commit, "expected_source_tree": tree,
    }
    verified = canonical_staging.verify_derived_runtime_config_snapshot(
        **arguments)
    assert hashlib.sha256(base64.b64decode(
        verified["snapshot_bytes_base64"])).hexdigest() == runtime_config.OUTPUT_SHA256

    with pytest.raises(
        canonical_staging.CanonicalRouteStagingError,
        match="derivation_receipt_hash_mismatch",
    ):
        canonical_staging.verify_derived_runtime_config_snapshot(
            **{**arguments, "expected_receipt_sha256": "0" * 64})
    receipt_path = Path(derived["receipt_path"])
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    receipt["substitution_inventory_sha256"] = "0" * 64
    drift = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    receipt_path.write_bytes(drift)
    with pytest.raises(
        canonical_staging.CanonicalRouteStagingError,
        match="derivation_receipt_binding_mismatch",
    ):
        canonical_staging.verify_derived_runtime_config_snapshot(**{
            **arguments, "expected_receipt_sha256": hashlib.sha256(drift).hexdigest(),
        })
    receipt_path.write_bytes(receipt_bytes)

    snapshot = Path(verified["snapshot_path"])
    exact_bytes = snapshot.read_bytes()
    snapshot.unlink()
    snapshot.write_bytes(exact_bytes)
    with pytest.raises(
        canonical_staging.CanonicalRouteStagingError,
        match="derived_snapshot_binding_mismatch",
    ):
        canonical_staging.verify_derived_runtime_config_snapshot(**arguments)
