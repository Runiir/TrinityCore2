from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
MOVEMENT = BOT_DIR / "BotWorldPopulationMgrMovement.h"
EXECUTOR = BOT_DIR / "BotWorldPopulationMgrMovementExecutor.cpp"
PRODUCER_CONTRACT = (
    BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.h"
)
PRODUCER = BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.cpp"
SUMMARY = ROOT / (
    "experiments/configs/"
    "cata_raid_magmaw_task_state_canary_a725c82d96_summary_v1.json"
)


def test_recorded_current_pack_hazard_exit_crosses_production_gate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "chainwielder_hazard_exit_admission.cpp"
    binary = tmp_path / "chainwielder_hazard_exit_admission"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrMovement.h"
#include "Bots/BotWorldPopulationMgrValidationRouteMovementCheck.h"

#include <cassert>

int main()
{
    using Owner = BotMovementArbitration::Owner;
    using Authority =
        BotWorldMovement::ValidationRouteDestinationAuthority;
    using Decision = BotWorldMovement::FutureDestinationGateDecision;
    using BotWorldMovement::EvaluateFutureDestinationGate;
    using BotWorldPopulationMgrValidationRoute::
        OwnsActiveCurrentPackHazardExit;

    // magmaw_task_state_canary_a725c82d96 recurrence: actor 30008,
    // bwd.magmaw.chainwielder generation 2, point (-333,-99,214.091).
    // Before the repair the correctly classified Hazard owner had no
    // current-pack authority, so the spatial overlap was terminal here.
    assert(EvaluateFutureDestinationGate(
        Owner::Hazard, Authority::None, false, false)
        == Decision::RejectFuturePack);

    // Entry 42690 is a native marker summon. Its summoner is the enrolled,
    // active generation-2 Chainwielder, so the point exit continues to the
    // ordinary lease and planner boundary after the repair.
    assert(OwnsActiveCurrentPackHazardExit(
        true, true, false, true));
    assert(EvaluateFutureDestinationGate(
        Owner::Hazard, Authority::ActiveCurrentPackHazardExit, false, false)
        == Decision::Continue);

    // Missing/stale ownership cannot manufacture the authority.
    assert(!OwnsActiveCurrentPackHazardExit(
        true, false, false, true));
    assert(!OwnsActiveCurrentPackHazardExit(
        true, true, false, false));
    assert(!OwnsActiveCurrentPackHazardExit(
        false, true, true, true));

    // A future encounter target remains forbidden even if a caller supplies
    // the hazard authority. The exception is point-only and owner-specific.
    assert(EvaluateFutureDestinationGate(
        Owner::Hazard, Authority::ActiveCurrentPackHazardExit, true, false)
        == Decision::RejectFuturePack);
    assert(EvaluateFutureDestinationGate(
        Owner::Route, Authority::ActiveCurrentPackHazardExit, false, false)
        == Decision::RejectFuturePack);
    assert(EvaluateFutureDestinationGate(
        Owner::CombatRange, Authority::None, false, false)
        == Decision::RejectFuturePack);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/server/game"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_recorded_failure_identity_remains_pinned() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    edge = summary["first_broken_edge"]
    assert summary["source_commit"] == (
        "a725c82d96463e185a8a47c98d4cd61e59aa28a2"
    )
    assert summary["terminal"]["bot_guid"] == 30008
    assert summary["terminal"]["route_generation"] == 2
    assert summary["terminal"]["route_node_id"] == (
        "bwd.magmaw.chainwielder"
    )
    assert edge["movement_gate"] == "future_pack_destination"
    assert edge["requested_destination"] == {
        "map": 669,
        "x": -333.0,
        "y": -99.0,
        "z": 214.091,
    }
    assert edge["native_planner_result"] == "unavailable"
    assert edge["native_launch_count"] == 0
    assert edge["progress_sample_count"] == 0


def test_current_pack_authority_is_wired_before_lease_and_planner() -> None:
    producer = PRODUCER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    contract = PRODUCER_CONTRACT.read_text(encoding="utf-8")
    movement = MOVEMENT.read_text(encoding="utf-8")

    assert "OwnsActiveCurrentPackHazardExit" in contract
    assert "hazardSummon->GetSummonerGUID()" in producer
    assert "ValidationRoutePackGeneration" in producer
    assert "ValidationRoutePackMemberGuids.find" in producer
    assert "destinationAuthority" in producer
    assert "DestinationAuthority = destinationAuthority" in (
        BOT_DIR / "BotWorldPopulationMgrMovement.cpp"
    ).read_text(encoding="utf-8")

    gate = executor.index("EvaluateFutureDestinationGate")
    lease = executor.index("BuildMovementRequest", gate)
    planner = executor.index("PlanMovementPath", gate)
    assert gate < lease < planner
    assert "intent.DestinationAuthority" in executor[gate:lease]
    assert "ActiveCurrentPackHazardExit" in movement


def test_changed_cpp_files_remain_below_limit() -> None:
    for path in (
        BOT_DIR / "BotWorldPopulationMgrMovement.cpp",
        BOT_DIR / "BotWorldPopulationMgrMovementExecutor.cpp",
        PRODUCER,
    ):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
