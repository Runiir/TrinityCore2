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
ARBITER = BOT_DIR / "BotActionArbiter.h"
PREPARATION = BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"
FALLBACK = BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp"
ROUTE_RUNTIME = BOT_DIR / "BotWorldPopulationMgrValidationRouteRuntime.cpp"
RAID_RUNTIME = BOT_DIR / "BotWorldPopulationMgrRaidRuntime.cpp"


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
    valid.RequestedSealSha256 = std::string(64, 'c');
    assert(RejectionReason(valid)
        == std::string_view("chainwielder_checkpoint_seal_mismatch"));
    valid.RequestedSealSha256 = admission;
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
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_generic_controller_route_hold_crosses_kernel_and_route_gate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "controller_route_hold.cpp"
    binary = tmp_path / "controller_route_hold"
    source.write_text(
r'''
#include "Bots/BotChainwielderOwnerCheckpoint.h"
#include "Bots/BotActionArbiter.h"

#include <cassert>

using namespace BotActionArbitration;
using namespace BotControllerRouteHold;

Identity CompleteIdentity(uint64 generation = 1)
{
    Identity value;
    value.CohortId = "cohort-a";
    value.ServerEpoch = 71;
    value.AttemptId = 9;
    value.ScenarioId = "scenario-a";
    value.RuntimeProfile = "runtime-a";
    value.RouteManifestSha256 = std::string(64, 'a');
    value.RouteGeneration = generation;
    value.RouteNodeId = "route.node.a";
    value.ActorGuid = 77;
    value.FixtureId = "fixture-a";
    value.SealSha256 = std::string(64, 'b');
    value.SourceCommit = std::string(40, 'c');
    return value;
}

Identity BootstrapIdentity()
{
    Identity value = CompleteIdentity(0);
    value.ScenarioId.clear();
    value.RuntimeProfile.clear();
    value.RouteManifestSha256.clear();
    value.RouteNodeId.clear();
    return value;
}

Candidate CandidateFor(char const* key, AdmissionClass classification,
    int& attempts, Kernel& kernel, std::string const& scope = "scope")
{
    Candidate candidate;
    candidate.Key = key;
    candidate.Source = "fixture";
    candidate.ActionPriority = Priority::RouteMovement;
    candidate.Attempt = [&attempts]()
    {
        ++attempts;
        return Outcome::Committed("attempted");
    };
    kernel.SetCandidateAdmission(candidate.Key, classification, scope);
    return candidate;
}

int main()
{
    Identity const identity = CompleteIdentity();
    Identity const bootstrap = BootstrapIdentity();

    // Recorded fail-before boundary: no stateful hold means both the generic
    // route candidate and the next generation are admitted before arm.
    State before;
    assert(GateRouteMutation(before, identity, 2));
    Kernel beforeKernel;
    beforeKernel.Begin(10);
    int beforeAttempts = 0;
    beforeKernel.Submit(CandidateFor("ordinary-route", AdmissionClass::Unknown,
        beforeAttempts, beforeKernel));
    beforeKernel.Resolve();
    assert(beforeAttempts == 1);

    State hold;
    assert(hold.BeginAcquire(bootstrap, 20).Accepted);
    assert(GateRouteMutation(hold, bootstrap, 1));
    assert(hold.CompleteAcquire(identity, 21).Accepted);

    // Held production kernel: setup/safety remains executable while ordinary
    // route work and an early checkpoint path are both suppressed and counted.
    Kernel heldKernel;
    heldKernel.Begin(22);
    InstallAdmissionPolicy(heldKernel, hold, identity, 77);
    int setupAttempts = 0;
    int ordinaryAttempts = 0;
    int earlyCheckpointAttempts = 0;
    heldKernel.Submit(CandidateFor("formation", AdmissionClass::FormationMovement,
        setupAttempts, heldKernel));
    heldKernel.Submit(CandidateFor("ordinary", AdmissionClass::Unknown,
        ordinaryAttempts, heldKernel));
    heldKernel.Submit(CandidateFor("checkpoint-early",
        AdmissionClass::ControllerCheckpointObservation,
        earlyCheckpointAttempts, heldKernel, identity.ScopeKey()));
    heldKernel.Resolve();
    assert(setupAttempts == 1);
    assert(ordinaryAttempts == 0);
    assert(earlyCheckpointAttempts == 0);
    assert(hold.SuppressedRouteActionCount == 2);
    assert(!GateRouteMutation(hold, identity, 2));
    assert(hold.SuppressedRouteAdvanceCount == 1);

    assert(hold.AcknowledgeArm(identity, 23).Accepted);
    Kernel armedKernel;
    armedKernel.Begin(24);
    InstallAdmissionPolicy(armedKernel, hold, identity, 77);
    int routeExecutionCount = 0;
    int routeActionViewAttempts = 0;
    int routeMovementViewAttempts = 0;
    int armedOrdinaryAttempts = 0;
    int foreignActorAttempts = 0;
    Candidate routeAction;
    routeAction.Key = "generic-route-action";
    routeAction.Source = "validation_route_adapter";
    routeAction.ActionPriority = Priority::Mechanic;
    routeAction.UtilityScore = 3.1f;
    routeAction.Attempt = [&routeExecutionCount, &routeActionViewAttempts]()
    {
        ++routeActionViewAttempts;
        ++routeExecutionCount;
        return Outcome::NotApplicable("route_movement_only");
    };
    Candidate routeMovement;
    routeMovement.Key = "generic-route-movement";
    routeMovement.Source = "validation_route_adapter";
    routeMovement.ActionPriority = Priority::Mechanic;
    routeMovement.UtilityScore = 3.0f;
    routeMovement.Attempt = [&routeExecutionCount, &routeMovementViewAttempts]()
    {
        ++routeMovementViewAttempts;
        assert(routeExecutionCount == 1);
        return Outcome::Committed("route_movement_submitted");
    };
    assert(MarkCheckpointObservationCandidate(armedKernel, routeAction.Key,
        hold, 77));
    assert(MarkCheckpointObservationCandidate(armedKernel, routeMovement.Key,
        hold, 77));
    armedKernel.Submit(std::move(routeAction));
    armedKernel.Submit(std::move(routeMovement));
    armedKernel.Submit(CandidateFor("armed-ordinary",
        AdmissionClass::Unknown, armedOrdinaryAttempts, armedKernel));
    // The same typed metadata cannot authorize a different bot.
    State foreignActorHold = hold;
    Kernel foreignKernel;
    foreignKernel.Begin(24);
    InstallAdmissionPolicy(foreignKernel, foreignActorHold, identity, 78);
    Candidate foreign = CandidateFor("checkpoint-foreign",
        AdmissionClass::Unknown, foreignActorAttempts, foreignKernel);
    assert(!MarkCheckpointObservationCandidate(foreignKernel, foreign.Key,
        foreignActorHold, 78));
    foreignKernel.Submit(std::move(foreign));
    armedKernel.Resolve();
    foreignKernel.Resolve();
    assert(routeExecutionCount == 1);
    assert(routeActionViewAttempts == 1);
    assert(routeMovementViewAttempts == 1);
    assert(armedOrdinaryAttempts == 0);
    assert(foreignActorAttempts == 0);

    Kernel wrongScopeKernel;
    wrongScopeKernel.Begin(24);
    InstallAdmissionPolicy(wrongScopeKernel, hold, identity, 77);
    int wrongScopeAttempts = 0;
    Candidate wrongScope = CandidateFor("checkpoint-wrong-scope",
        AdmissionClass::ControllerCheckpointObservation,
        wrongScopeAttempts, wrongScopeKernel, "wrong-scope");
    wrongScopeKernel.Submit(std::move(wrongScope));
    wrongScopeKernel.Resolve();
    assert(wrongScopeAttempts == 0);

    assert(hold.ObserveCheckpointTerminal(identity, "completed", true,
        true, 25).Accepted);
    assert(hold.Release(identity, 26).Accepted);
    assert(hold.ReleaseCount == 1);
    assert(GateRouteMutation(hold, CompleteIdentity(2), 2));

    // Exact negative transitions remain typed and fail closed.
    State duplicateAcquire;
    assert(duplicateAcquire.BeginAcquire(bootstrap, 1).Accepted);
    assert(!duplicateAcquire.BeginAcquire(bootstrap, 2).Accepted);
    assert(duplicateAcquire.FailureReason
        == "controller_route_hold_duplicate_acquire");

    State earlyRelease;
    assert(earlyRelease.BeginAcquire(bootstrap, 1).Accepted);
    assert(earlyRelease.CompleteAcquire(identity, 2).Accepted);
    assert(!earlyRelease.Release(identity, 3).Accepted);
    assert(earlyRelease.FailureReason
        == "controller_route_hold_release_before_terminal");

    State duplicateArm;
    assert(duplicateArm.BeginAcquire(bootstrap, 1).Accepted);
    assert(duplicateArm.CompleteAcquire(identity, 2).Accepted);
    assert(duplicateArm.AcknowledgeArm(identity, 3).Accepted);
    assert(!duplicateArm.AcknowledgeArm(identity, 4).Accepted);
    assert(duplicateArm.FailureReason
        == "controller_route_hold_duplicate_arm");

    State staleTerminal;
    assert(staleTerminal.BeginAcquire(bootstrap, 1).Accepted);
    assert(staleTerminal.CompleteAcquire(identity, 2).Accepted);
    assert(!staleTerminal.ObserveCheckpointTerminal(identity, "completed",
        true, true, 3).Accepted);
    assert(staleTerminal.FailureReason
        == "controller_route_hold_checkpoint_terminal_stale");

    State missingTerminal;
    assert(missingTerminal.BeginAcquire(bootstrap, 1).Accepted);
    assert(missingTerminal.CompleteAcquire(identity, 2).Accepted);
    assert(missingTerminal.AcknowledgeArm(identity, 3).Accepted);
    assert(!missingTerminal.ObserveCheckpointTerminal(identity, "running",
        false, true, 4).Accepted);
    assert(missingTerminal.FailureReason
        == "controller_route_hold_checkpoint_terminal_missing");

    State drift;
    assert(drift.BeginAcquire(bootstrap, 1).Accepted);
    assert(drift.CompleteAcquire(identity, 2).Accepted);
    Identity changed = identity;
    changed.RouteNodeId = "route.node.changed";
    assert(!GateRouteMutation(drift, changed, 2));
    assert(drift.FailureReason == "controller_route_hold_identity_drift");

    State duplicateRelease = hold;
    assert(!duplicateRelease.Release(identity, 27).Accepted);
    assert(duplicateRelease.CurrentPhase
        == BotControllerRouteHold::Phase::Released);
    assert(duplicateRelease.FailureReason
        == "controller_route_hold_duplicate_release");
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
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_generic_controller_hold_is_wired_to_production_boundaries() -> None:
    preparation = PREPARATION.read_text(encoding="utf-8")
    fallback = FALLBACK.read_text(encoding="utf-8")
    route_runtime = ROUTE_RUNTIME.read_text(encoding="utf-8")
    raid_runtime = RAID_RUNTIME.read_text(encoding="utf-8")
    command = COMMAND.read_text(encoding="utf-8")

    assert "InstallControllerRouteHoldAdmissionPolicy(context)" in preparation
    assert fallback.count("MarkCheckpointObservationCandidate(") == 2
    assert "InstallAdmissionPolicy(" in MODULE.read_text(encoding="utf-8")
    assert "GateRouteMutation(" in MODULE.read_text(encoding="utf-8")
    assert "PermitControllerRouteAdvance(index + 1)" in route_runtime
    assert "PermitControllerRouteAdvance(prospectiveGeneration)" in route_runtime
    assert "controller_route_hold" in raid_runtime
    assert 'action == "start-held"' in command
    assert 'action == "release"' in command


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
    assert "ConfigSealSha256 != input.RequestedSealSha256" in header
    assert "ChainwielderOwnerCheckpoint.SealSha256" in config
    assert "ChainwielderOwnerCheckpoint.AdmissionSha256" not in config
    assert "ConfigSourceCommit != input.BinarySourceCommit" in header
    assert "checkpoint.InjectionCount != 1" in module
    assert 'action == "arm"' in command
    assert 'action == "status"' in command


def test_checkpoint_cpp_files_remain_below_repository_limit() -> None:
    for path in (
        HEADER,
        MODULE,
        COMMAND,
        ARBITER,
        PREPARATION,
        FALLBACK,
        ROUTE_RUNTIME,
        RAID_RUNTIME,
    ):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
