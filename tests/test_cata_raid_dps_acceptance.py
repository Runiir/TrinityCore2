from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.bot_ml.run_cata_raid_dps_acceptance import (
    acceptance_targets,
    campaign_attempts,
    child_command,
    targeted_eviction_complete,
)
from tools.bot_ml.verify_cata_raid_dps_acceptance import verify


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/cata_raid_dps_acceptance_v1.json"


def test_current_25h_dps_contract_has_exact_75_85_gates() -> None:
    report = verify(CONFIG)

    assert report["passed"] is True
    assert report["supported_dps_spec_count"] == 16
    assert report["supported_specialization_target_count"] == 24
    assert report["attempt_count"] == 96
    assert report["hard_reference_ratio"] == 0.75
    assert report["optimization_reference_ratio"] == 0.85
    assert len(report["targets"]) == 16
    assert all(row["hard_floor_dps"] > 0 for row in report["targets"])
    assert all(
        row["optimization_target_dps"] > row["hard_floor_dps"]
        for row in report["targets"]
    )


def test_acceptance_plan_covers_every_dps_mode_and_seed() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    targets = acceptance_targets(config)
    attempts = campaign_attempts(targets, config["modes"], config["seeds"])

    assert len(attempts) == 96
    assert {row["spec_target_id"] for row in attempts} == set(
        config["dps_targets"]
    )
    assert {row["mode"] for row in attempts} == {
        "single_target_300",
        "aoe_300",
    }
    assert {row["seed"] for row in attempts} == {1, 2, 3}


def test_live_acceptance_command_forces_publish_and_eviction(tmp_path: Path) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    attempt = campaign_attempts(
        acceptance_targets(config), config["modes"], config["seeds"]
    )[0]
    args = argparse.Namespace(
        worldserver=Path("build/src/server/worldserver/worldserver"),
        worldserver_config=Path("trinity-worldserver-test.conf"),
        timeout_sec=900,
        heartbeat_sec=30,
        session_transition_timeout_sec=360,
        session_environment="test-dps85",
    )
    command = child_command(
        args,
        attempt,
        tmp_path / "attempt",
        ROOT / "experiments/configs/all_spec_role_calibration_policy_v2.json",
        tmp_path / "identity.json",
    )

    assert "--publish-batch" in command
    assert "--retain-published-batch" not in command
    assert command[command.index("--role-calibration-policy") + 1].endswith(
        "all_spec_role_calibration_policy_v2.json"
    )


def test_targeted_eviction_requires_receipt_and_no_bulk_payload(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    (batch / "retained").mkdir(parents=True)
    (batch / "retained/publication_receipt.json").write_text(
        "{}", encoding="utf-8"
    )
    assert targeted_eviction_complete(tmp_path)

    (batch / "raw").mkdir()
    assert not targeted_eviction_complete(tmp_path)


def test_world_validation_path_uses_kernel_and_recovery_supervisor() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    update_start = source.index("void BotWorldPopulationMgr::UpdateBot(")
    update_end = source.index("\nPlayer* BotWorldPopulationMgr::GetLoadedBot", update_start)
    update = source[update_start:update_end]

    assert "validationKernelOwnsTick" in update
    assert "state.DecisionKernel.Resolve()" in update
    assert "TryRecoverStuckBot(state, bot)" in update
    assert "validation_route_stuck_no_fallback" not in update
    assert "stuck_no_fallback" not in update

    recovery_start = source.index("bool BotWorldPopulationMgr::TryRecoverStuckBot(")
    recovery_end = source.index("void BotWorldPopulationMgr::ObserveBotCandidateFailure", recovery_start)
    recovery = source[recovery_start:recovery_end]
    assert "recoveryStrategy" in recovery
    assert "world.recovery.sidestep_left" in recovery
    assert "world.recovery.sidestep_right" in recovery

    prepare_start = source.index(
        "std::string BotWorldPopulationMgr::PrepareValidationProfile("
    )
    prepare_end = source.index(
        "bool BotWorldPopulationMgr::PrepareCurrentValidationProfile", prepare_start
    )
    prepare = source[prepare_start:prepare_end]
    assert "exactPartyRequested" in prepare
    assert "!exactPartyRequested" in prepare
    assert "invalid_exact_party_contract" in prepare

    record_start = source.index("void BotWorldPopulationMgr::RecordDecision(")
    record_end = source.index("void BotWorldPopulationMgr::RecordDecisionFingerprintMemory", record_start)
    record = source[record_start:record_end]
    assert "bot_decision_mask_v3" in record
    assert "decision_kernel" in record
    assert "state.LastDecisionKernelJson" in record
