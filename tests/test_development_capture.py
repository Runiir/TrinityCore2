from argparse import Namespace
from pathlib import Path

import pytest

from tools.raid_program.capture_finalization import development_run_claim
from tools.raid_program.capture_setup import (
    build_capture_parser,
    development_run_argument_rejections,
    development_run_canonical_rejections,
    prepare_capture_setup,
)


PROFILE = "blackwing_descent_10n_magmaw_diagnostic"


def _parser_args(*extra: str) -> Namespace:
    return build_capture_parser().parse_args([
        "--binary", "/tmp/worldserver",
        "--config", "/tmp/worldserver.conf",
        "--output", "/tmp/report.json",
        "--build-receipt", "/tmp/build.json",
        "--development-run",
        "--scenario-id", PROFILE,
        "--runtime-profile", PROFILE,
        "--pool-tag", PROFILE,
        *extra,
    ])


@pytest.mark.parametrize(
    ("extra", "reason"),
    [
        (("--recurrence-admission", "/tmp/admission.json"),
         "development_run_incompatible_recurrence_admission"),
        (("--recurrence-admission-sha256", "a" * 64),
         "development_run_incompatible_recurrence_admission_sha256"),
        (("--fixture-expansion-replay",),
         "development_run_incompatible_fixture_expansion_replay"),
        (("--chainwielder-checkpoint-actor-guid", "30008"),
         "development_run_incompatible_chainwielder_checkpoint_actor"),
        (("--magmaw-transfer-checkpoint-actor-guid", "30008"),
         "development_run_incompatible_magmaw_transfer_checkpoint_actor"),
        (("--profile-combat-range-checkpoint-actor-guid", "30010"),
         "development_run_incompatible_profile_combat_range_checkpoint_actor"),
        (("--trace-transport-smoke",),
         "development_run_incompatible_trace_transport_smoke"),
    ],
)
def test_development_run_rejects_auxiliary_authorities(
    extra: tuple[str, ...], reason: str,
) -> None:
    assert reason in development_run_argument_rejections(_parser_args(*extra))


def test_development_run_requires_explicit_canonical_identity() -> None:
    args = build_capture_parser().parse_args([
        "--binary", "/tmp/worldserver",
        "--config", "/tmp/worldserver.conf",
        "--output", "/tmp/report.json",
        "--build-receipt", "/tmp/build.json",
        "--development-run",
    ])
    assert development_run_argument_rejections(args) == [
        "development_run_scenario_id_required",
        "development_run_runtime_profile_required",
        "development_run_pool_tag_required",
    ]


def _canonical_assets(root: Path) -> dict[str, object]:
    return {
        "passed": True,
        "reasons": [],
        "profile_name": PROFILE,
        "profile_manifest": str(root / "dataset/bot_runtime_profiles/profiles.json"),
        "route_manifest": str(root / "dataset/validation_scenarios/validation_routes.jsonl"),
        "route_sha256": "c" * 64,
        "reference_route_sha256": "c" * 64,
        "matching_route_rows": 4,
        "scenario_id": PROFILE,
        "pool_tag_filter": PROFILE,
        "route_partition": {
            "scenario_id": PROFILE,
            "profile_name": PROFILE,
            "node_count": 4,
            "terminal_index": 3,
            "terminal_kind": "boss",
            "terminal_target_entry": 41570,
            "node_ids": [
                "bwd.entry.regroup",
                "bwd.magmaw.chainwielder",
                "bwd.magmaw.drudges",
                "bwd.magmaw.encounter",
            ],
            "diagnostic_only": True,
            "boss_node_count": 1,
            "passed": True,
            "reasons": [],
        },
    }


def _write_base_config(root: Path, *, extra: str = "") -> Path:
    config = root / "worldserver.conf"
    config.write_text(
        extra
        + "BotWorld.AutoStart = 0\n"
        'BotWorld.ProfileManifest = "dataset/bot_runtime_profiles/profiles.json"\n'
        'BotWorld.RuntimeProfile = ""\n'
        "BotWorld.ValidationRoute.Enable = 0\n"
        'BotWorld.ValidationRoute.ManifestPath = ""\n',
        encoding="utf-8",
    )
    return config


def test_development_run_requires_canonical_profile_and_unmodified_route(
    tmp_path: Path,
) -> None:
    config = _write_base_config(tmp_path)
    assert development_run_canonical_rejections(
        _parser_args(), config=config, worktree=tmp_path,
        runtime_assets=_canonical_assets(tmp_path),
    ) == []

    overlay = _write_base_config(
        tmp_path, extra='BotWorld.ValidationRoute.ManifestPath = "/tmp/overlay.json"\n',
    )
    assert "development_run_route_overlay_forbidden" in (
        development_run_canonical_rejections(
            _parser_args(), config=overlay, worktree=tmp_path,
            runtime_assets=_canonical_assets(tmp_path),
        )
    )

    checkpoint = _write_base_config(
        tmp_path,
        extra="BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable = 1\n",
    )
    assert any(
        reason.startswith("development_run_checkpoint_authority_forbidden:")
        for reason in development_run_canonical_rejections(
            _parser_args(), config=checkpoint, worktree=tmp_path,
            runtime_assets=_canonical_assets(tmp_path),
        )
    )

    sealed = _write_base_config(
        tmp_path,
        extra=(
            "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable = 0\n"
            'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.FixtureId = "sealed"\n'
        ),
    )
    assert any(
        reason.startswith("development_run_checkpoint_identity_forbidden:")
        for reason in development_run_canonical_rejections(
            _parser_args(), config=sealed, worktree=tmp_path,
            runtime_assets=_canonical_assets(tmp_path),
        )
    )

    targeted = _write_base_config(
        tmp_path,
        extra=(
            "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint.Enable = 0\n"
            "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint.ActorGuid = 30010\n"
        ),
    )
    assert (
        "development_run_checkpoint_identity_forbidden:"
        "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint.ActorGuid"
    ) in development_run_canonical_rejections(
        _parser_args(), config=targeted, worktree=tmp_path,
        runtime_assets=_canonical_assets(tmp_path),
    )


def _stub_development_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, build_valid: bool,
) -> list[str]:
    binary = tmp_path / "build/src/server/worldserver/worldserver"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"worldserver")
    config = _write_base_config(tmp_path)
    receipt = tmp_path / "build-receipt.json"
    receipt.write_text("{}\n", encoding="utf-8")
    (tmp_path / "dataset/bot_runtime_profiles").mkdir(parents=True)
    (tmp_path / "dataset/validation_scenarios").mkdir(parents=True)

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.enforce_runtime_asset_closure_from_args",
        lambda *_args, **_kwargs: {
            "complete": True, "status": "runtime_asset_closure_complete",
        },
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.verify_recurrence_admission",
        lambda *args, **kwargs: pytest.fail("development run read recurrence admission"),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.preflight_runtime_exclusions",
        lambda worktree: {"passed": True, "reasons": []},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.git_identity",
        lambda worktree: {
            "clean": True, "head": "a" * 40, "tree": "b" * 40,
        },
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_runtime_profile_assets",
        lambda *args, **kwargs: _canonical_assets(tmp_path),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup._drudge_navmesh_probe",
        lambda worktree: {"all_passed": True},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup._frozen_drudge_member_anchors",
        lambda route: {member: (0.0, 0.0, 0.0) for member in range(1, 11)},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.build_policy_path_for_receipt",
        lambda build_receipt, worktree: tmp_path / "build-policy.json",
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_build_receipt",
        lambda *args, **kwargs: {
            "valid": build_valid,
            "rejections": [] if build_valid else ["build_receipt_not_success"],
        },
    )
    return [
        "--binary", str(binary),
        "--config", str(config),
        "--output", str(tmp_path / "report.json"),
        "--build-receipt", str(receipt),
        "--worktree", str(tmp_path),
        "--development-run",
        "--scenario-id", PROFILE,
        "--runtime-profile", PROFILE,
        "--pool-tag", PROFILE,
    ]


def test_development_magmaw_setup_skips_recurrence_but_keeps_strict_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv = _stub_development_preflight(tmp_path, monkeypatch, build_valid=True)
    setup = prepare_capture_setup(argv, root=tmp_path)
    assert setup.args.development_run is True
    assert setup.recurrence_admission is None
    assert setup.checkpoint_arm_command is None
    assert setup.controller_route_hold_scheduler is None
    assert setup.runtime_asset_closure["complete"] is True
    assert setup.build_provenance["valid"] is True
    assert setup.runtime_assets["route_partition"]["terminal_kind"] == "boss"


def test_development_run_cannot_pass_with_source_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv = _stub_development_preflight(tmp_path, monkeypatch, build_valid=False)
    with pytest.raises(SystemExit, match="build_receipt_not_success"):
        prepare_capture_setup(argv, root=tmp_path)


def _terminal_status(*, include_death: bool) -> dict[str, object]:
    identity = {
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 4,
        "route_kind": "boss",
    }
    route = {
        "node_id": "bwd.magmaw.encounter",
        "kind": "boss",
        "generation": 4,
        "manifest_index": 3,
        "manifest_count": 4,
        "manifest_complete": True,
        "terminal_evidence": [identity],
        "boss_death_evidence": [],
    }
    if include_death:
        route["boss_death_evidence"] = [{
            **identity,
            "target_entry": 41570,
            "target_id": 1234,
            "result": "confirmed_unit_death",
        }]
    return {"validation_route": route}


def test_development_claim_is_ineligible_and_requires_native_boss_death() -> None:
    partition = _canonical_assets(Path("/tmp"))["route_partition"]
    missing = development_run_claim(
        requested=True,
        stable_statuses=[_terminal_status(include_death=False)],
        route_partition=partition,
    )
    assert missing["native_boss_death_accepted"] is False
    assert missing["accepted_boss_identity"] is None

    accepted = development_run_claim(
        requested=True,
        stable_statuses=[_terminal_status(include_death=True)],
        route_partition=partition,
    )
    assert accepted == {
        "requested": True,
        "claim_class": "development_diagnostic",
        "training_eligible": False,
        "qualification_eligible": False,
        "native_boss_death_required": True,
        "native_boss_death_accepted": True,
        "accepted_boss_identity": {
            "route_node_id": "bwd.magmaw.encounter",
            "route_generation": 4,
            "target_entry": 41570,
        },
    }
