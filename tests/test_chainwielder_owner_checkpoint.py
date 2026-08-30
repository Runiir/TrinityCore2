from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
HEADER = BOT_DIR / "BotChainwielderOwnerCheckpoint.h"
MODULE = BOT_DIR / "BotWorldPopulationMgrChainwielderOwnerCheckpoint.cpp"
UPDATE = BOT_DIR / "BotWorldPopulationMgrUpdateBot.cpp"
CONFIG = BOT_DIR / "BotWorldPopulationMgrConfig.cpp"
COMMAND = (
    ROOT
    / "src/server/scripts/Commands/cs_chainwielder_owner_checkpoint.cpp"
)


def test_checkpoint_gate_and_foreign_owner_counterexample_compile(
    tmp_path: Path,
) -> None:
    source = tmp_path / "chainwielder_owner_checkpoint.cpp"
    binary = tmp_path / "chainwielder_owner_checkpoint"
    source.write_text(
        r'''
#include "Bots/BotChainwielderOwnerCheckpoint.h"

#include <cassert>

using namespace BotChainwielderOwnerCheckpoint;

int main()
{
    GateInput disabled;
    assert(RejectionReason(disabled)
        == std::string_view("chainwielder_checkpoint_disabled"));

    std::string const admission(64, 'a');
    std::string const source(40, 'b');
    GateInput valid{
        true, true, ProfileId, ProfileId, PoolTag, ProfileId, NodeId,
        MapId, ActorCount, ActorCount, TargetEntry, true, true, 9,
        FixtureId, admission, admission, source, source, source,
    };
    assert(RejectionReason(valid) == nullptr);
    valid.RequestedSourceCommit = std::string(40, 'c');
    assert(RejectionReason(valid)
        == std::string_view("chainwielder_checkpoint_source_identity_mismatch"));

    OwnerSnapshot before;
    before.MovementOwner = BotMovementArbitration::Owner::Route;
    before.ActivePathValid = true;
    before.ActivePathSegmentValid = true;
    before.ActivePathTraversalMode = "native_long_path";
    before.ActivePathAttemptId = 9;
    before.ActivePathWipeGeneration = 2;
    before.ActivePathRouteGeneration = 4;
    before.ActivePathRouteNodeId = NodeId;
    before.ActivePathToX = -333.0f;
    before.ActivePathToY = -99.0f;
    before.ActivePathToZ = 214.154f;
    before.DodgeCasterGuid = 27;
    before.DodgeSpellId = 79580;
    before.DodgeUntilMs = 8000;
    before.LastPathRejectReason = "route_owner_previous_reason";

    // Recorded pre-fix mutation must fail the checkpoint.
    OwnerSnapshot preFixAfter = before;
    preFixAfter.ActivePathValid = false;
    preFixAfter.LastPathRejectReason =
        "route_destination_future_pack_unsafe";
    assert(!SameRouteIdentity(before, preFixAfter));

    // The repaired production transition preserves the complete foreign
    // owner identity until the next production tick.
    OwnerSnapshot repairedAfter = before;
    assert(SameRouteIdentity(before, repairedAfter));
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


def test_checkpoint_crosses_real_executor_and_production_tick_boundary() -> None:
    module = MODULE.read_text(encoding="utf-8")
    update = UPDATE.read_text(encoding="utf-8")

    assert "GetCreatureData(sourceId)" in module
    assert "IsValidationRoutePatrolCombatPointSafe" in module
    assert "ExecuteMovementIntent(state, bot, rejected)" in module
    assert "MovementPlannerDiagnostics().Latest" in module
    assert 'observation.Gate == "future_pack_destination"' in module
    assert 'observation.Result == "rejected"' in module
    assert "observation.LaunchReceipt.Id == 0" in module
    assert "SameRouteIdentity(\n        checkpoint.Before, immediateAfter)" in module
    assert "SameRouteIdentity(\n            checkpoint.Before, checkpoint.After)" in module

    observe = update.index("ObserveChainwielderOwnerCheckpointBeforeUpdate")
    progress = update.index("ObserveReceiptTaggedMovementProgress")
    finalize = update.index("FinalizeBotUpdate(context)")
    inject = update.index("MaybeInjectChainwielderOwnerCheckpointAfterUpdate")
    assert observe < progress
    assert finalize < inject


def test_checkpoint_is_default_off_and_exactly_admission_bound() -> None:
    header = HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    command = COMMAND.read_text(encoding="utf-8")

    assert "ChainwielderOwnerCheckpointEnable = false" in (
        BOT_DIR / "BotWorldPopulationMgrConfig.h"
    ).read_text(encoding="utf-8")
    assert (
        '"BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable", false'
        in config
    )
    assert "ConfigAdmissionSha256 != input.RequestedAdmissionSha256" in header
    assert "ConfigSourceCommit != input.BinarySourceCommit" in header
    assert "checkpoint.InjectionCount != 1" in module
    assert 'action == "arm"' in command
    assert 'action == "status"' in command


def test_checkpoint_cpp_files_remain_below_repository_limit() -> None:
    for path in (HEADER, MODULE, COMMAND):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
