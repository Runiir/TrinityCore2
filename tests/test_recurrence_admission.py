from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from tools.raid_program.build_control_compatibility import (
    compatibility_projection,
    verify_build_control_compatibility,
)

from tools.raid_program.capture_checkpoint_controller import (
    chainwielder_checkpoint_arm_command,
    native_path_checkpoint_arm_command,
)
from tools.raid_program.controller_route_hold import (
    controller_route_hold_launch_identity,
)
from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    FIXTURE_EXPANSION_PURPOSE,
    NATIVE_PATH_CHECKPOINT_CONFIG_PREFIX,
    NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
    NATIVE_PATH_CHECKPOINT_REQUIRED_PENDING_FIXTURE_IDS,
    NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS,
    RecurrenceAdmissionError,
    chainwielder_checkpoint_seal,
    build_runtime_profile_suffix_manifest,
    create_recurrence_admission,
    native_path_checkpoint_seal,
    sha256_file,
    verify_recurrence_admission,
)
from tools.raid_program.recurrence_checkpoint_seals import (
    fixture_expansion_contract,
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
    source_profiles = root / "dataset/bot_runtime_profiles/profiles.json"
    source_profiles.parent.mkdir(parents=True)
    _write_json(source_profiles, {
        "schema": "bot_world_runtime_profiles_v1",
        "profiles": [
            {
                "name": name,
                "target_population": 10,
                "validation_route": {
                    "enable": True,
                    "manifest_path": "canonical/routes.jsonl",
                },
            }
            for name in ("test_profile", "foreign_valid_profile")
        ],
    })
    _git(root, "add", ".")
    _git(root, "commit", "-m", "identity")

    binary = tmp_path / "worldserver"
    build_receipt = tmp_path / "build.json"
    route = tmp_path / "route.json"
    config = tmp_path / "worldserver.conf"
    ledger = tmp_path / "ledger.json"
    decision = tmp_path / "decision.json"
    suite = tmp_path / "suite.json"
    profile_manifest = tmp_path / "runtime_profiles.json"
    binary.write_bytes(b"\x7fELFtest")
    build_commit = _git(root, "rev-parse", "HEAD")
    build_snapshot = {
        "commit": build_commit,
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "clean": True,
        "dirty": False,
        "porcelain_sha256": hashlib.sha256(b"").hexdigest(),
    }
    _write_json(
        build_receipt,
        {
            "classification": "success",
            "exit_code": 0,
            "commit": build_commit,
            "source_identity": {
                stage: dict(build_snapshot)
                for stage in ("request", "admission", "completion")
            },
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
        "pending_fixture_ids": [],
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
    compatibility = verify_build_control_compatibility(
        worktree=root,
        receipt=json.loads(build_receipt.read_text(encoding="utf-8")),
    )
    assert compatibility["valid"] is True
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
            "build_control_compatibility": compatibility_projection(
                compatibility
            ),
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
        "profile_manifest": profile_manifest,
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


def _refresh_admission_for_control_head(
    paths: dict[str, Path | str],
) -> dict[str, object]:
    root = Path(paths["root"])
    suite = Path(paths["suite"])
    admission = Path(paths["admission"])
    build_receipt = Path(paths["build_receipt"])
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["source_identity"] = _git(root, "rev-parse", "HEAD")
    _write_json(suite, suite_value)
    compatibility = verify_build_control_compatibility(
        worktree=root,
        receipt=json.loads(build_receipt.read_text(encoding="utf-8")),
    )
    admission_value = json.loads(admission.read_text(encoding="utf-8"))
    admission_value["source"] = {
        "commit": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "porcelain_sha256": hashlib.sha256(b"").hexdigest(),
    }
    admission_value["bindings"]["suite_receipt"]["sha256"] = sha256_file(suite)
    admission_value["build_control_compatibility"] = compatibility_projection(
        compatibility
    )
    _write_json(admission, admission_value)
    return compatibility


def _replacement_request() -> dict[str, object]:
    return {
        "fixture_id": "native_planner_executor_launch_proof_v1",
        "from_revision": 2,
        "to_revision": 3,
        "causal_signature": "native_planner_executor_launch_divergence",
        "required_production_boundary": (
            "worldserver-backed map-669 planner, executor, MotionMaster, "
            "point generator, and launched spline observed over multiple ticks"
        ),
    }


def test_fixture_expansion_contract_excludes_quarantined_pending_targets() -> None:
    request = _replacement_request()
    value = {
        "pending_fixture_ids": ["quarantined_floor_fixture"],
        "quarantined_fixture_ids": ["quarantined_floor_fixture"],
        "fixture_expansion_target_ids": [request["fixture_id"]],
        "fixture_expansion_requests": [request],
    }

    assert fixture_expansion_contract(value, label="fixture_expansion") == [request]


def _map669_expansion_requests() -> list[dict[str, object]]:
    return [
        {
            "fixture_id": "same_level_floor_observation_v1",
            "from_revision": 4,
            "to_revision": 5,
            "causal_signature": "same_level_floor_observation_false_negative",
            "required_production_boundary": "map_669_native_floor_observation",
        },
        {
            "fixture_id": "same_level_hazard_path_admission_v1",
            "from_revision": 4,
            "to_revision": 5,
            "causal_signature": "same_level_encounter_hazard_path_rejection",
            "required_production_boundary": "map_669_native_hazard_path_admission",
        },
        {
            "fixture_id": "same_level_native_path_proof_v1",
            "from_revision": 4,
            "to_revision": 5,
            "causal_signature": "same_level_native_path_proof_false_negative",
            "required_production_boundary": "map_669_native_path_proof",
        },
    ]


def _runtime_profile_authority(
    paths: dict[str, Path | str],
) -> tuple[Path, dict[str, str]]:
    source_path = (
        Path(paths["root"]) / "dataset/bot_runtime_profiles/profiles.json"
    )
    source_profiles = json.loads(source_path.read_text(encoding="utf-8"))
    profile_manifest = Path(paths["profile_manifest"])
    runtime_profiles, overlay = build_runtime_profile_suffix_manifest(
        source_manifest=source_profiles,
        runtime_profile="test_profile",
        route_manifest_path=Path(paths["route"]),
    )
    _write_json(profile_manifest, runtime_profiles)
    overlay.update({
        "source_profile_manifest_sha256": sha256_file(source_path),
        "runtime_profile_manifest_sha256": sha256_file(profile_manifest),
        "runtime_route_manifest_sha256": sha256_file(Path(paths["route"])),
    })
    return profile_manifest, overlay


def _create_chainwielder_checkpoint_admission(
    paths: dict[str, Path | str],
    *,
    expansion_requests: list[dict[str, object]] | None = None,
    include_checkpoint_target: bool = True,
    checkpoint_fixture_id: str | None = CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
) -> dict[str, str]:
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    suite = Path(paths["suite"])
    config = Path(paths["config"])
    expansion_requests = expansion_requests or []
    target_ids = [
        *(
            [CHAINWIELDER_CHECKPOINT_FIXTURE_ID]
            if include_checkpoint_target else []
        ),
        *(request["fixture_id"] for request in expansion_requests),
    ]
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": target_ids,
            "fixture_expansion_requests": expansion_requests,
            "pending_fixture_ids": target_ids,
        }
    )
    _write_json(decision, decision_value)
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["verifications"] = [
        {
            "fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
            "fixture_revision": 1,
            "passed": True,
        },
        *(
            {
                "fixture_id": request["fixture_id"],
                "fixture_revision": request["from_revision"],
                "passed": True,
            }
            for request in expansion_requests
        ),
    ]
    _write_json(suite, suite_value)
    profile_manifest, overlay = _runtime_profile_authority(paths)
    seal = chainwielder_checkpoint_seal(
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        decision=decision,
        profile_manifest=profile_manifest,
        runtime_profile_overlay=overlay,
        expected_runtime_profile_id="test_profile",
    )
    source_commit = _git(Path(paths["root"]), "rev-parse", "HEAD")
    config.write_text(
        config.read_text(encoding="utf-8")
        + 'BotWorld.RuntimeProfile = "test_profile"\n'
        + f'BotWorld.ProfileManifest = "{profile_manifest.resolve()}"\n'
        + "BotWorld.ValidationRoute.PrepullCheckpointEnable = 1\n"
        + "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable = 1\n"
        + "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint."
        + f'FixtureId = "{CHAINWIELDER_CHECKPOINT_FIXTURE_ID}"\n'
        + "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint."
        + f'SealSha256 = "{seal["seal_sha256"]}"\n'
        + "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint."
        + f'SourceCommit = "{source_commit}"\n',
        encoding="utf-8",
    )
    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=decision,
        suite_receipt=suite,
        profile_manifest=profile_manifest,
        runtime_profile_overlay=overlay,
        expected_runtime_profile_id="test_profile",
        checkpoint_fixture_id=checkpoint_fixture_id,
        purpose=FIXTURE_EXPANSION_PURPOSE,
    )
    return seal


def _create_native_path_checkpoint_admission(
    paths: dict[str, Path | str],
    *, case_id: str = "a506_receipt636_incomplete_same_floor",
) -> dict[str, str]:
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    suite = Path(paths["suite"])
    config = Path(paths["config"])
    requests = _map669_expansion_requests()
    target_ids = list(NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS)
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update({
        "build_admitted": False,
        "canary_admitted": False,
        "fixture_expansion_admitted": True,
        "fixture_expansion_target_ids": target_ids,
        "fixture_expansion_requests": requests,
        "pending_fixture_ids": list(
            NATIVE_PATH_CHECKPOINT_REQUIRED_PENDING_FIXTURE_IDS
        ),
        "invalidated_fixture_ids": ["same_level_floor_observation_v1"],
        "failing_fixture_ids": ["same_level_floor_observation_v1"],
    })
    _write_json(decision, decision_value)
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["verifications"] = [
        {
            "fixture_id": request["fixture_id"],
            "fixture_revision": request["from_revision"],
            "passed": True,
        }
        for request in requests
    ]
    _write_json(suite, suite_value)
    profile_manifest, overlay = _runtime_profile_authority(paths)
    seal = native_path_checkpoint_seal(
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        decision=decision,
        case_id=case_id,
        profile_manifest=profile_manifest,
        runtime_profile_overlay=overlay,
        expected_runtime_profile_id="test_profile",
    )
    source_commit = _git(Path(paths["root"]), "rev-parse", "HEAD")
    prefix = NATIVE_PATH_CHECKPOINT_CONFIG_PREFIX
    config.write_text(
        config.read_text(encoding="utf-8")
        + 'BotWorld.RuntimeProfile = "test_profile"\n'
        + f'BotWorld.ProfileManifest = "{profile_manifest.resolve()}"\n'
        + "BotWorld.ValidationRoute.Enable = 1\n"
        + "BotWorld.ValidationRoute.PrepullCheckpointEnable = 1\n"
        + f"{prefix}.Enable = 1\n"
        + f'{prefix}.FixtureId = "{NATIVE_PATH_CHECKPOINT_FIXTURE_ID}"\n'
        + f'{prefix}.CaseId = "{case_id}"\n'
        + f'{prefix}.SealSha256 = "{seal["seal_sha256"]}"\n'
        + f'{prefix}.SourceCommit = "{source_commit}"\n',
        encoding="utf-8",
    )
    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=decision,
        suite_receipt=suite,
        profile_manifest=profile_manifest,
        runtime_profile_overlay=overlay,
        expected_runtime_profile_id="test_profile",
        purpose=FIXTURE_EXPANSION_PURPOSE,
    )
    return seal


def _verify_chainwielder(
    paths: dict[str, Path | str],
) -> dict[str, object]:
    admission = Path(paths["admission"])
    return verify_recurrence_admission(
        admission_path=admission,
        expected_sha256=sha256_file(admission),
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=Path(paths["config"]),
        profile_manifest=Path(paths["profile_manifest"]),
        expected_runtime_profile_id="test_profile",
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
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


def test_chainwielder_checkpoint_uses_precomputed_non_circular_seal(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    seal = _create_chainwielder_checkpoint_admission(paths)

    result = _verify_chainwielder(paths)

    assert result["valid"] is True
    assert result["checkpoint_seal_sha256"] == seal["seal_sha256"]
    admission = json.loads(
        Path(paths["admission"]).read_text(encoding="utf-8")
    )
    assert admission["checkpoint_seal"] == seal
    assert admission["bindings"]["runtime_config"]["sha256"] == sha256_file(
        Path(paths["config"])
    )
    assert seal["profile_manifest_sha256"] == sha256_file(
        Path(paths["profile_manifest"])
    )
    assert seal["expected_runtime_profile_id"] == "test_profile"
    assert seal["runtime_profile_overlay_sha256"] == hashlib.sha256(
        json.dumps(
            admission["runtime_profile_overlay"],
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert result["runtime_profile_overlay"] == admission["runtime_profile_overlay"]


def test_native_checkpoint_creates_and_verifies_exact_request_pending_projection(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    seal = _create_native_path_checkpoint_admission(paths)

    result = _verify_chainwielder(paths)
    admission = json.loads(
        Path(paths["admission"]).read_text(encoding="utf-8")
    )

    assert result["valid"] is True
    assert result["purpose"] == FIXTURE_EXPANSION_PURPOSE
    assert result["fixture_expansion_target_ids"] == list(
        NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS
    )
    assert result["pending_fixture_ids"] == list(
        NATIVE_PATH_CHECKPOINT_REQUIRED_PENDING_FIXTURE_IDS
    )
    assert admission["invalidated_fixture_ids"] == [
        "same_level_floor_observation_v1"
    ]
    assert admission["failing_fixture_ids"] == [
        "same_level_floor_observation_v1"
    ]
    assert result["checkpoint_fixture_id"] == NATIVE_PATH_CHECKPOINT_FIXTURE_ID
    assert result["checkpoint_seal_sha256"] == seal["seal_sha256"]
    assert seal["binary_sha256"] == sha256_file(Path(paths["binary"]))
    assert seal["profile_manifest_sha256"] == sha256_file(
        Path(paths["profile_manifest"])
    )
    assert result["runtime_profile_overlay"][
        "runtime_route_manifest_sha256"
    ] == sha256_file(Path(paths["route"]))
    assert native_path_checkpoint_arm_command(result, 30007).startswith(
        "botautonativepathcheckpoint arm 30007 "
    )


def test_fixture_replay_can_seal_auxiliary_checkpoint_profile(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    request = _replacement_request()
    seal = _create_chainwielder_checkpoint_admission(
        paths,
        expansion_requests=[request],
        include_checkpoint_target=False,
    )

    result = _verify_chainwielder(paths)

    assert result["valid"] is True
    assert result["fixture_expansion_target_ids"] == [request["fixture_id"]]
    assert result["checkpoint_seal_sha256"] == seal["seal_sha256"]
    assert result["runtime_profile_overlay"] is not None


def test_composite_checkpoint_create_verify_projection_arms_controller(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    requests = _map669_expansion_requests()
    _create_chainwielder_checkpoint_admission(
        paths, expansion_requests=requests
    )

    verified = _verify_chainwielder(paths)

    assert verified["pending_fixture_ids"] == [
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        *(request["fixture_id"] for request in requests),
    ]
    assert chainwielder_checkpoint_arm_command(verified, 30008) == (
        "botautochaincheckpoint arm 30008 "
        f'{verified["checkpoint_seal_sha256"]} {verified["source_commit"]}'
    )
    identity = controller_route_hold_launch_identity(
        recurrence_admission=verified,
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
        actor_guid=30008,
        scenario_id="blackwing_descent_10n_magmaw_diagnostic",
        runtime_profile="test_profile",
        pool_tag="test_pool",
        route_manifest_sha256=sha256_file(Path(paths["route"])),
        route_node_id="bwd.magmaw.chainwielder",
    )
    assert identity is not None
    assert identity.fixture_id == CHAINWIELDER_CHECKPOINT_FIXTURE_ID

    for mutation in ("missing", "not_member"):
        candidate = json.loads(json.dumps(verified))
        if mutation == "missing":
            candidate.pop("checkpoint_fixture_id", None)
        else:
            candidate["checkpoint_fixture_id"] = "not_an_admitted_fixture"
        with pytest.raises(
            ValueError, match="controller_route_hold_verified_admission_invalid"
        ):
            controller_route_hold_launch_identity(
                recurrence_admission=candidate,
                required_purpose=FIXTURE_EXPANSION_PURPOSE,
                actor_guid=30008,
                scenario_id="blackwing_descent_10n_magmaw_diagnostic",
                runtime_profile="test_profile",
                pool_tag="test_pool",
                route_manifest_sha256=sha256_file(Path(paths["route"])),
                route_node_id="bwd.magmaw.chainwielder",
            )

    admission_path = Path(paths["admission"])
    forged = json.loads(admission_path.read_text(encoding="utf-8"))
    forged["checkpoint_seal"]["fixture_id"] = requests[0]["fixture_id"]
    _write_json(admission_path, forged)
    with pytest.raises(
        RecurrenceAdmissionError, match="checkpoint_seal_identity_mismatch"
    ):
        _verify_chainwielder(paths)


def test_multidialect_checkpoint_requires_explicit_selection(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    with pytest.raises(
        RecurrenceAdmissionError,
        match="fixture_expansion_checkpoint_fixture_selection_required",
    ):
        _create_chainwielder_checkpoint_admission(
            paths,
            expansion_requests=_map669_expansion_requests(),
            checkpoint_fixture_id=None,
        )


def test_explicit_checkpoint_selection_must_be_eligible(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    with pytest.raises(
        RecurrenceAdmissionError,
        match="fixture_expansion_checkpoint_fixture_ineligible",
    ):
        _create_chainwielder_checkpoint_admission(
            paths,
            checkpoint_fixture_id=NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
        )


@pytest.mark.parametrize(
    "mutation",
    ["selected", "overlay_hash", "source_identity", "suffix_path",
     "suffix_hash", "foreign_selection", "envelope"],
)
def test_profile_overlay_authority_rejects_coherent_drift(
    tmp_path: Path, mutation: str,
) -> None:
    paths = _fixture(tmp_path)
    _create_chainwielder_checkpoint_admission(paths)
    admission_path = Path(paths["admission"])
    profile_path = Path(paths["profile_manifest"])
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    overlay = admission["runtime_profile_overlay"]

    if mutation == "selected":
        profile["profiles"][0]["target_population"] = 9
    elif mutation == "overlay_hash":
        overlay["runtime_selected_profile_sha256"] = "0" * 64
    elif mutation == "source_identity":
        overlay["source_profile_manifest_sha256"] = "0" * 64
    elif mutation == "suffix_path":
        overlay["runtime_validation_route_manifest_path"] = str(
            tmp_path / "other-route.json"
        )
    elif mutation == "suffix_hash":
        overlay["runtime_route_manifest_sha256"] = "0" * 64
    elif mutation == "foreign_selection":
        profile["profiles"][0]["name"] = "foreign"
        overlay["runtime_profile_id"] = "foreign"
    else:
        profile["schema"] = "mutated"
        overlay["profile_manifest_envelope_sha256"] = hashlib.sha256(
            json.dumps(
                {"schema": "mutated"}, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    if mutation in {"selected", "foreign_selection", "envelope"}:
        _write_json(profile_path, profile)
        overlay["runtime_profile_manifest_sha256"] = sha256_file(profile_path)
        overlay["runtime_selected_profile_sha256"] = hashlib.sha256(
            json.dumps(
                profile["profiles"][0],
                sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        admission["bindings"]["profile_manifest"]["sha256"] = sha256_file(
            profile_path
        )
    admission["runtime_profile_overlay"] = overlay
    _write_json(admission_path, admission)

    with pytest.raises(
        RecurrenceAdmissionError,
        match=(
            "runtime_profile_(overlay|source)|expected_runtime_profile|"
            "source_profile_manifest|checkpoint_seal"
        ),
    ):
        _verify_chainwielder(paths)


def test_expected_runtime_profile_rejects_coherent_valid_profile_substitution(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    original_seal = _create_chainwielder_checkpoint_admission(paths)
    assert _verify_chainwielder(paths)["expected_runtime_profile_id"] == (
        "test_profile"
    )

    root = Path(paths["root"])
    route = Path(paths["route"])
    profile_path = Path(paths["profile_manifest"])
    source_path = root / "dataset/bot_runtime_profiles/profiles.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    runtime, foreign_overlay = build_runtime_profile_suffix_manifest(
        source_manifest=source, runtime_profile="foreign_valid_profile",
        route_manifest_path=route,
    )
    _write_json(profile_path, runtime)
    foreign_overlay.update({
        "source_profile_manifest_sha256": sha256_file(source_path),
        "runtime_profile_manifest_sha256": sha256_file(profile_path),
        "runtime_route_manifest_sha256": sha256_file(route),
    })
    foreign_seal = chainwielder_checkpoint_seal(
        worktree=root, binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        decision=Path(paths["decision"]), profile_manifest=profile_path,
        runtime_profile_overlay=foreign_overlay,
        expected_runtime_profile_id="foreign_valid_profile",
    )
    config = Path(paths["config"])
    config.write_text(
        config.read_text(encoding="utf-8")
        .replace('"test_profile"', '"foreign_valid_profile"')
        .replace(original_seal["seal_sha256"], foreign_seal["seal_sha256"]),
        encoding="utf-8",
    )
    admission = Path(paths["admission"])
    admission.unlink()
    create_kwargs = {
        "output": admission,
        "worktree": root,
        "binary": Path(paths["binary"]),
        "build_receipt": Path(paths["build_receipt"]),
        "runtime_config": config,
        "route_manifest": route,
        "ledger": Path(paths["ledger"]),
        "decision": Path(paths["decision"]),
        "suite_receipt": Path(paths["suite"]),
        "profile_manifest": profile_path,
        "runtime_profile_overlay": foreign_overlay,
        "purpose": FIXTURE_EXPANSION_PURPOSE,
    }
    with pytest.raises(
        RecurrenceAdmissionError, match="expected_runtime_profile_mismatch"
    ):
        create_recurrence_admission(
            **create_kwargs, expected_runtime_profile_id="test_profile"
        )

    create_recurrence_admission(
        **create_kwargs, expected_runtime_profile_id="foreign_valid_profile"
    )
    with pytest.raises(
        RecurrenceAdmissionError, match="expected_runtime_profile_mismatch"
    ):
        verify_recurrence_admission(
            admission_path=admission, expected_sha256=sha256_file(admission),
            worktree=root, binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]), runtime_config=config,
            profile_manifest=profile_path,
            expected_runtime_profile_id="test_profile",
            required_purpose=FIXTURE_EXPANSION_PURPOSE,
        )


def test_expected_runtime_profile_is_absent_for_non_checkpoint_admission(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    assert _verify(paths)["expected_runtime_profile_id"] is None
    admission = Path(paths["admission"])
    with pytest.raises(
        RecurrenceAdmissionError, match="profile_authority_unexpected"
    ):
        verify_recurrence_admission(
            admission_path=admission, expected_sha256=sha256_file(admission),
            worktree=Path(paths["root"]), binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]),
            runtime_config=Path(paths["config"]),
            expected_runtime_profile_id="not_applicable",
        )


@pytest.mark.parametrize(
    ("binding", "reason"),
    [
        ("runtime_config", "runtime_config_hash_mismatch"),
        ("binary", "binary_hash_mismatch"),
        ("build_receipt", "build_receipt_hash_mismatch"),
    ],
)
def test_chainwielder_checkpoint_rejects_bound_input_mutation(
    tmp_path: Path, binding: str, reason: str,
) -> None:
    paths = _fixture(tmp_path)
    _create_chainwielder_checkpoint_admission(paths)
    path = Path(paths["config" if binding == "runtime_config" else binding])
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(RecurrenceAdmissionError, match=reason):
        _verify_chainwielder(paths)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("seal", "checkpoint_seal_identity_mismatch"),
        ("fixture", "fixture_expansion_request_target_mismatch"),
        ("source", "checkpoint_seal_identity_mismatch"),
    ],
)
def test_chainwielder_checkpoint_rejects_admission_identity_tamper(
    tmp_path: Path, mutation: str, reason: str,
) -> None:
    paths = _fixture(tmp_path)
    _create_chainwielder_checkpoint_admission(paths)
    admission = Path(paths["admission"])
    value = json.loads(admission.read_text(encoding="utf-8"))
    if mutation == "seal":
        value["checkpoint_seal"]["seal_sha256"] = "0" * 64
    elif mutation == "fixture":
        value["fixture_expansion_target_ids"] = ["wrong_fixture"]
    else:
        value["checkpoint_seal"]["source_commit"] = "0" * 40
    _write_json(admission, value)

    with pytest.raises(RecurrenceAdmissionError, match=reason):
        _verify_chainwielder(paths)


def test_chainwielder_checkpoint_rejects_final_admission_file_mutation(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    _create_chainwielder_checkpoint_admission(paths)
    admission = Path(paths["admission"])
    admitted_sha = sha256_file(admission)
    admission.write_bytes(admission.read_bytes() + b" ")

    with pytest.raises(RecurrenceAdmissionError, match="admission_hash_mismatch"):
        verify_recurrence_admission(
            admission_path=admission,
            expected_sha256=admitted_sha,
            worktree=Path(paths["root"]),
            binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]),
            runtime_config=Path(paths["config"]),
            required_purpose=FIXTURE_EXPANSION_PURPOSE,
        )


def test_fixture_expansion_admission_is_distinct_from_gameplay_canary(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    config = Path(paths["config"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "invalidated_fixture_ids": ["same_level_native_path_proof_v1"],
            "failing_fixture_ids": ["same_level_native_path_proof_v1"],
            "pending_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
        }
    )
    _write_json(decision, decision_value)
    config.write_text(
        config.read_text(encoding="utf-8")
        + "BotWorld.ValidationRoute.PrepullCheckpointEnable = 1\n",
        encoding="utf-8",
    )

    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=decision,
        suite_receipt=Path(paths["suite"]),
        purpose=FIXTURE_EXPANSION_PURPOSE,
    )

    result = verify_recurrence_admission(
        admission_path=admission,
        expected_sha256=sha256_file(admission),
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
    )
    assert result["valid"] is True
    assert result["purpose"] == FIXTURE_EXPANSION_PURPOSE
    assert result["fixture_expansion_target_ids"] == [
        "native_planner_executor_launch_proof_v1"
    ]
    with pytest.raises(RecurrenceAdmissionError, match="admission_purpose_mismatch"):
        _verify(paths)


def test_invalidated_replacement_request_seals_target_and_revisions(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    suite = Path(paths["suite"])
    config = Path(paths["config"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "fixture_expansion_requests": [_replacement_request()],
            "invalidated_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "failing_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "pending_fixture_ids": [],
        }
    )
    _write_json(decision, decision_value)
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["verifications"] = [
        {
            "fixture_id": "native_planner_executor_launch_proof_v1",
            "fixture_revision": 2,
            "passed": True,
        }
    ]
    _write_json(suite, suite_value)
    config.write_text(
        config.read_text(encoding="utf-8")
        + "BotWorld.ValidationRoute.PrepullCheckpointEnable = 1\n",
        encoding="utf-8",
    )

    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=decision,
        suite_receipt=suite,
        purpose=FIXTURE_EXPANSION_PURPOSE,
    )

    result = verify_recurrence_admission(
        admission_path=admission,
        expected_sha256=sha256_file(admission),
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
    )
    assert result["fixture_expansion_target_ids"] == [
        "native_planner_executor_launch_proof_v1"
    ]
    assert result["fixture_expansion_requests"] == [_replacement_request()]


@pytest.mark.parametrize(
    "target_ids",
    [[], ["native_planner_executor_launch_proof_v1", "extra"]],
)
def test_fixture_expansion_rejects_missing_or_extra_request_target(
    tmp_path: Path, target_ids: list[str]
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": target_ids,
            "fixture_expansion_requests": [_replacement_request()],
            "invalidated_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "failing_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "pending_fixture_ids": [],
        }
    )
    _write_json(decision, decision_value)

    with pytest.raises(
        RecurrenceAdmissionError,
        match="fixture_expansion_(target_invalid|request_target_mismatch)",
    ):
        create_recurrence_admission(
            output=admission,
            worktree=Path(paths["root"]),
            binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]),
            runtime_config=Path(paths["config"]),
            route_manifest=Path(paths["route"]),
            ledger=Path(paths["ledger"]),
            decision=decision,
            suite_receipt=Path(paths["suite"]),
            purpose=FIXTURE_EXPANSION_PURPOSE,
        )


def test_fixture_expansion_creator_rejects_stale_suite_and_dirty_source(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    suite = Path(paths["suite"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "fixture_expansion_requests": [_replacement_request()],
            "invalidated_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "failing_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "pending_fixture_ids": [],
        }
    )
    _write_json(decision, decision_value)
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["source_identity"] = "stale"
    _write_json(suite, suite_value)

    kwargs = {
        "output": admission,
        "worktree": Path(paths["root"]),
        "binary": Path(paths["binary"]),
        "build_receipt": Path(paths["build_receipt"]),
        "runtime_config": Path(paths["config"]),
        "route_manifest": Path(paths["route"]),
        "ledger": Path(paths["ledger"]),
        "decision": decision,
        "suite_receipt": suite,
        "purpose": FIXTURE_EXPANSION_PURPOSE,
    }
    with pytest.raises(RecurrenceAdmissionError, match="suite_receipt_source_stale"):
        create_recurrence_admission(**kwargs)

    suite_value["source_identity"] = _git(Path(paths["root"]), "rev-parse", "HEAD")
    _write_json(suite, suite_value)
    (Path(paths["root"]) / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RecurrenceAdmissionError, match="source_worktree_dirty"):
        create_recurrence_admission(**kwargs)


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


def test_recurrence_admission_accepts_control_only_descendant_build(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    root = Path(paths["root"])
    descriptor = root / "experiments/configs/active.json"
    descriptor.parent.mkdir(parents=True)
    descriptor.write_text("{}\n", encoding="utf-8")
    _git(root, "add", descriptor.relative_to(root).as_posix())
    _git(root, "commit", "-m", "advance control descriptor")
    compatibility = _refresh_admission_for_control_head(paths)
    assert compatibility["valid"] is True

    verified = _verify(paths)

    assert verified["control_commit"] == _git(root, "rev-parse", "HEAD")
    assert verified["build_source_commit"] != verified["control_commit"]
    assert verified["build_control_relationship"] == "control_only_descendant"


def test_recurrence_admission_rejects_native_descendant_build(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    root = Path(paths["root"])
    native = root / "src/server/native.cpp"
    native.parent.mkdir(parents=True)
    native.write_text("int changed;\n", encoding="utf-8")
    _git(root, "add", native.relative_to(root).as_posix())
    _git(root, "commit", "-m", "native change")
    compatibility = _refresh_admission_for_control_head(paths)
    assert compatibility["valid"] is False

    with pytest.raises(
        RecurrenceAdmissionError,
        match="build_source_incompatible:control_path_not_allowed:src/server/native.cpp",
    ):
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
        (
            "pending_fixture_ids",
            ["native_planner_executor_launch_proof_v1"],
            "pending_fixture_ids_present",
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


def test_recurrence_admission_accepts_only_quarantined_stale_fixtures(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update({
        "invalidated_fixture_ids": ["deferred_floor_fixture"],
        "failing_fixture_ids": ["deferred_floor_fixture"],
        "pending_fixture_ids": ["deferred_floor_fixture"],
        "quarantined_fixture_ids": ["deferred_floor_fixture"],
        "blocking_invalidated_fixture_ids": [],
    })
    _write_json(decision, decision_value)

    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=Path(paths["config"]),
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=decision,
        suite_receipt=Path(paths["suite"]),
    )

    result = _verify(paths)
    assert result["valid"] is True
    assert result["quarantined_fixture_ids"] == ["deferred_floor_fixture"]
    assert result["blocking_invalidated_fixture_ids"] == []


def test_recurrence_admission_rejects_nonquarantined_fixture_mixed_with_quarantine(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    value = json.loads(admission.read_text(encoding="utf-8"))
    value.update({
        "invalidated_fixture_ids": ["deferred", "required"],
        "quarantined_fixture_ids": ["deferred"],
        "blocking_invalidated_fixture_ids": ["required"],
    })
    _write_json(admission, value)

    with pytest.raises(
        RecurrenceAdmissionError, match="invalidated_fixture_ids_present"
    ):
        _verify(paths)
