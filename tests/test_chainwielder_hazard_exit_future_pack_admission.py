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
RAW_REQUESTS = ROOT / (
    "experiments/configs/"
    "cata_raid_chainwielder_hazard_exit_raw_requests_a725c82d96_v1.json"
)


def test_local_authority_and_future_gate_truth_table_compiles(
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

    // Local policy counterexample only. The server-bound writer/consumer
    // chain needs Map, Player, TempSummon, manager, and native movement state
    // and is not claimed by this compiled truth table.
    assert(EvaluateFutureDestinationGate(
        Owner::Hazard, Authority::None, false, false)
        == Decision::RejectFuturePack);

    // A current-generation active summoner admits the narrow typed authority.
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


def test_recorded_raw_movement_requests_remain_pinned() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    raw = json.loads(RAW_REQUESTS.read_text(encoding="utf-8"))
    edge = summary["first_broken_edge"]
    assert raw["source_commit"] == summary["source_commit"]
    assert raw["raw_jsonl_sha256"] == summary["evidence"][
        "raw_jsonl_sha256"
    ]
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
    assert raw["route_level_diagnostic_destination"] == (
        edge["requested_destination"]
    )
    requests = raw["rejected_movement_requests"]
    assert requests == [
        {
            "first_event_sequence": 336,
            "x": -320.384918,
            "y": -92.0700684,
            "z": 213.945786,
        },
        {
            "first_event_sequence": 339,
            "x": -321.650116,
            "y": -90.1487732,
            "z": 213.959915,
        },
        {
            "first_event_sequence": 341,
            "x": -333.321442,
            "y": -84.6103821,
            "z": 213.758911,
        },
        {
            "first_event_sequence": 343,
            "x": -335.609863,
            "y": -84.8453903,
            "z": 213.82692,
        },
        {
            "first_event_sequence": 350,
            "x": -319.441986,
            "y": -94.168396,
            "z": 213.909698,
        },
    ]
    route_destination = tuple(
        raw["route_level_diagnostic_destination"][axis]
        for axis in ("x", "y", "z")
    )
    assert route_destination not in {
        (row["x"], row["y"], row["z"]) for row in requests
    }
    assert raw["shared_observation"] == {
        "movement_owner": "hazard",
        "gate": "future_pack_destination",
        "result": "rejected",
        "reason": "route_destination_future_pack_unsafe",
        "launch_receipt_id": 0,
        "shared_plan_movement_path_reached": False,
        "motion_master_submission_reached": False,
    }
    assert edge["native_planner_result"] == "unavailable"
    assert edge["native_launch_count"] == 0
    assert edge["progress_sample_count"] == 0


def test_current_pack_authority_source_wiring_audit() -> None:
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
