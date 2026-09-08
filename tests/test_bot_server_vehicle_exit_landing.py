from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
HEADER = BOT_DIR / "BotServerVehicleExitLanding.h"
STATE = BOT_DIR / "BotWorldPopulationMgrBotState.h"
PREPARATION = BOT_DIR / "BotWorldPopulationMgrUpdateBotPreparation.cpp"
EXECUTOR = BOT_DIR / "BotWorldPopulationMgrMovementExecutor.cpp"
DIAGNOSIS = BOT_DIR / "BotWorldPopulationMgrDiagnosis.cpp"


def test_vehicle_exit_landing_resolver_compiles_and_replays_native_proof(
    tmp_path: Path,
) -> None:
    source = tmp_path / "bot_server_vehicle_exit_landing.cpp"
    binary = tmp_path / "bot_server_vehicle_exit_landing"
    source.write_text(
        r'''
#include "Bots/BotServerVehicleExitLanding.h"

#include <cassert>
#include <cstdint>

using namespace BotServerVehicleExitLanding;

constexpr std::uint32_t Walking = 0x00000100u;
constexpr std::uint32_t Falling = 0x00000800u;
constexpr std::uint32_t FallingFar = 0x00001000u;

bool ExistingHardcastMovementPredicate(std::uint32_t flags)
{
    return (flags & (Falling | FallingFar)) != 0;
}

struct FakeActor
{
    std::uint32_t Flags = Falling | FallingFar | Walking;
    unsigned SetFallCalls = 0;

    void SetFall(bool enable)
    {
        assert(!enable);
        ++SetFallCalls;
        Flags &= ~(Falling | FallingFar);
    }
};

Scope CurrentScope()
{
    Scope scope;
    scope.AttemptId = 7;
    scope.WipeGeneration = 3;
    scope.RouteGeneration = 11;
    scope.MapId = 669;
    scope.InstanceId = 2;
    return scope;
}

Episode ArmedEpisode()
{
    Episode episode;
    VehicleTransitionObservation mounted;
    mounted.HasVehicle = true;
    mounted.VehicleGuid = 9001;
    mounted.BotGuid = 30008;
    mounted.MapId = 669;
    mounted.InstanceId = 2;
    mounted.ObservedAtMs = 900;
    mounted.ScopeAvailable = true;
    mounted.CurrentScope = CurrentScope();
    ObserveVehicleTransition(episode, mounted);

    VehicleTransitionObservation exited = mounted;
    exited.HasVehicle = false;
    exited.ObservedAtMs = 1000;
    ObserveVehicleTransition(episode, exited);
    assert(episode.VehicleObserved);
    assert(episode.ExitPending);
    assert(episode.ExitObservedAtMs == 1000);
    return episode;
}

ReceiptBindingObservation GroundReceipt()
{
    ReceiptBindingObservation receipt;
    receipt.ActualPointSubmission = true;
    receipt.ProgressReceiptArmed = true;
    receipt.ReceiptId = 637;
    receipt.BotGuid = 30008;
    receipt.MapId = 669;
    receipt.InstanceId = 2;
    receipt.ArmedAtMs = 1000;
    receipt.ScopeAvailable = true;
    receipt.ReceiptScope = CurrentScope();
    receipt.SplineInitialized = true;
    receipt.SplineId = 7777;
    return receipt;
}

LandingEvidence ValidEvidence(Episode const& episode)
{
    LandingEvidence evidence;
    evidence.BotGuid = episode.ExitBotGuid;
    evidence.MapId = episode.ExitMapId;
    evidence.InstanceId = episode.ExitInstanceId;
    evidence.CurrentScopeAvailable = true;
    evidence.CurrentScope = CurrentScope();
    evidence.ActorInWorld = true;
    evidence.ActorAlive = true;
    evidence.FallingFlagsPresent = true;
    evidence.CurrentSplineFinalized = true;
    evidence.MotionSlotsSettled = true;
    evidence.ReceiptAvailable = true;
    evidence.ReceiptId = 637;
    evidence.ReceiptBotGuid = 30008;
    evidence.ReceiptMapId = 669;
    evidence.ReceiptInstanceId = 2;
    evidence.ReceiptArmedAtMs = 1000;
    evidence.ReceiptScopeAvailable = true;
    evidence.ReceiptScope = CurrentScope();
    evidence.ReceiptTerminal = true;
    evidence.ReceiptTerminalOutcome = "selected_endpoint_reached";
    evidence.TerminalSampleAvailable = true;
    evidence.TerminalActorAlive = true;
    evidence.TerminalActorInWorld = true;
    evidence.TerminalEndpointReached = true;
    evidence.TerminalFloorValid = true;
    evidence.TerminalPlatformCompatible = true;
    // Receipt 637's terminal sample reported 0.250376 horizontal and
    // 0.086304 vertical error.  Exercise the production helper with those
    // recorded values instead of manufacturing a matched endpoint boolean.
    evidence.CurrentEndpointMatches =
        BotWorldMovement::NativePathEndpointComponentsMatch(
            0.250376f, 0.086304f);
    evidence.FlagsBefore = Falling | FallingFar | Walking;
    return evidence;
}

void AssertPreserved(Episode const& episode, LandingEvidence evidence)
{
    FakeActor actor;
    std::uint32_t const before = actor.Flags;
    assert(ExistingHardcastMovementPredicate(before));
    ReconciliationResult const result = Reconcile(episode, evidence, &actor);
    assert(result.Decision == Decision::KeepPending);
    assert(actor.Flags == before);
    assert(actor.SetFallCalls == 0);
}

int main()
{
    Episode noEpisode;
    VehicleTransitionObservation noVehicle;
    noVehicle.BotGuid = 30008;
    noVehicle.MapId = 669;
    noVehicle.InstanceId = 2;
    noVehicle.ObservedAtMs = 1000;
    ObserveVehicleTransition(noEpisode, noVehicle);
    LandingEvidence noPriorEvidence;
    noPriorEvidence.BotGuid = 30008;
    noPriorEvidence.MapId = 669;
    noPriorEvidence.InstanceId = 2;
    noPriorEvidence.FallingFlagsPresent = true;
    FakeActor noPriorActor;
    assert(Reconcile(noEpisode, noPriorEvidence, &noPriorActor).Decision
        == Decision::NoEpisode);
    assert(noPriorActor.SetFallCalls == 0);

    Episode episode = ArmedEpisode();
    ReceiptBindingObservation rejected = GroundReceipt();
    rejected.ActualPointSubmission = false;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.ProgressReceiptArmed = false;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.ArmedAtMs = 999;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.BotGuid = 30007;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.MapId = 1;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.InstanceId = 3;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.ReceiptScope.AttemptId = 8;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.ReceiptScope.WipeGeneration = 4;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.ReceiptScope.RouteGeneration = 12;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.SplineInitialized = false;
    assert(!BindGroundingReceipt(episode, rejected));
    rejected = GroundReceipt();
    rejected.ReceiptId = 630;
    rejected.ArmedAtMs = 1001;
    rejected.SplineId = 7776;
    assert(BindGroundingReceipt(episode, rejected));
    assert(episode.BoundGroundingReceiptId == 630);
    assert(episode.BoundGroundingReceiptArmedAtMs == 1001);

    LandingEvidence transitional = ValidEvidence(episode);
    transitional.ReceiptId = 630;
    transitional.ReceiptArmedAtMs = 1001;
    transitional.ReceiptTerminal = false;
    transitional.ReceiptTerminalOutcome = "pending";
    transitional.TerminalSampleAvailable = false;
    transitional.CurrentSplineFinalized = false;
    transitional.NativeFalling = true;
    transitional.MotionSlotsSettled = false;
    FakeActor transitionalActor;
    std::uint32_t const transitionalFlags = transitionalActor.Flags;
    assert(Reconcile(episode, transitional, &transitionalActor).Decision
        == Decision::KeepPending);
    assert(transitionalActor.Flags == transitionalFlags);
    assert(transitionalActor.SetFallCalls == 0);
    RecordEvaluation(episode, transitional, Resolve(episode, transitional),
        1100, transitionalActor.Flags);
    assert(episode.LastObservedAtMs == 1100);
    assert(episode.LastReconciliationAtMs == 0);

    // The first post-exit POINT is still active when a newer native POINT is
    // submitted.  The newer armed receipt replaces the transitional binding;
    // stale/replayed receipts cannot move it backwards.
    ReceiptBindingObservation replacement = GroundReceipt();
    replacement.ArmedAtMs = 1001;
    assert(BindGroundingReceipt(episode, replacement));
    assert(episode.BoundGroundingReceiptId == 637);
    assert(episode.BoundGroundingReceiptArmedAtMs == 1001);
    replacement = GroundReceipt();
    replacement.ArmedAtMs = 1001;
    replacement.ReceiptId = 629;
    assert(!BindGroundingReceipt(episode, replacement));
    assert(episode.BoundGroundingReceiptId == 637);

    LandingEvidence valid = ValidEvidence(episode);
    valid.ReceiptArmedAtMs = 1001;
    FakeActor actor;
    std::uint32_t const before = actor.Flags;
    assert(Resolve(episode, valid).Decision
        == Decision::ClearStaleLandingFlag);
    assert(actor.Flags == before);
    ReconciliationResult const success = Reconcile(episode, valid, &actor);
    assert(success.Decision == Decision::ClearStaleLandingFlag);
    assert(actor.SetFallCalls == 1);
    assert(actor.Flags == Walking);
    assert(!ExistingHardcastMovementPredicate(actor.Flags));
    RecordEvaluation(episode, valid, success, 1200, actor.Flags);
    assert(episode.LastReconciliationAtMs == 1200);
    CloseEpisode(episode);
    assert(!episode.ExitPending);
    assert(episode.BoundGroundingReceiptId == 0);
    assert(episode.LastFlagsBefore == (Falling | FallingFar | Walking));
    assert(episode.LastFlagsAfter == Walking);
    assert(Reconcile(episode, valid, &actor).Decision == Decision::NoEpisode);
    assert(actor.SetFallCalls == 1);

    // Run 88, receipt 772: the latest 100-ms sample can still be pending
    // when the independently observed native spline has already settled.
    Episode secondExit = ArmedEpisode();
    secondExit.ExitObservedAtMs = 1788880339594ULL;
    secondExit.ExitScope.AttemptId = 1;
    secondExit.ExitScope.WipeGeneration = 0;
    secondExit.ExitScope.RouteGeneration = 4;
    ReceiptBindingObservation receipt772 = GroundReceipt();
    receipt772.ReceiptId = 772;
    receipt772.ArmedAtMs = 1788880343233ULL;
    receipt772.SplineId = 10875;
    receipt772.ReceiptScope = secondExit.ExitScope;
    assert(BindGroundingReceipt(secondExit, receipt772));
    LandingEvidence pending772 = ValidEvidence(secondExit);
    pending772.CurrentScope = secondExit.ExitScope;
    pending772.ReceiptScope = secondExit.ExitScope;
    pending772.ReceiptId = 772;
    pending772.ReceiptArmedAtMs = receipt772.ArmedAtMs;
    pending772.ReceiptTerminal = false;
    pending772.ReceiptTerminalOutcome = "pending";
    pending772.TerminalSampleAvailable = false;
    pending772.TerminalEndpointReached =
        BotWorldMovement::NativePathEndpointComponentsMatch(
            0.703745604f, 0.0318603516f);
    assert(!pending772.TerminalEndpointReached);
    // Current position/motion may be newer than that 1788880344933 sample.
    pending772.CurrentEndpointMatches =
        BotWorldMovement::NativePathEndpointComponentsMatch(0.0f, 0.0f);
    FakeActor secondActor;
    auto applyEvaluation = [&](LandingEvidence const& evidence,
        std::uint64_t observedAtMs)
    {
        auto result = Reconcile(secondExit, evidence, &secondActor);
        RecordEvaluation(secondExit, evidence, result, observedAtMs,
            secondActor.Flags);
        // Mirror the production preparation caller's binding lifecycle.
        if (result.DropBoundReceipt)
            ResetBoundReceipt(secondExit);
        if (result.Decision == Decision::CloseEpisode
            || result.Decision == Decision::ClearStaleLandingFlag)
            CloseEpisode(secondExit);
        return result;
    };
    // The between-sample time is a replayed interleaving, not a captured event.
    auto pendingResult = applyEvaluation(pending772, 1788880345000ULL);
    assert(pendingResult.Decision == Decision::KeepPending);
    assert(!pendingResult.DropBoundReceipt);
    assert(secondExit.BoundGroundingReceiptId == 772);
    assert(secondActor.SetFallCalls == 0);
    assert(ExistingHardcastMovementPredicate(secondActor.Flags));
    assert(secondExit.LastReconciliationAtMs == 0);
    LandingEvidence terminal772 = pending772;
    terminal772.ReceiptTerminal = true;
    terminal772.ReceiptTerminalOutcome = "selected_endpoint_reached";
    terminal772.TerminalSampleAvailable = true;
    terminal772.TerminalEndpointReached =
        BotWorldMovement::NativePathEndpointComponentsMatch(0.0f, 0.0f);
    assert(applyEvaluation(terminal772, 1788880345033ULL).Decision
        == Decision::ClearStaleLandingFlag);
    assert(secondActor.SetFallCalls == 1);
    assert(secondActor.Flags == Walking);
    assert(!ExistingHardcastMovementPredicate(secondActor.Flags));
    assert(secondExit.LastReconciliationAtMs == 1788880345033ULL);
    assert(!secondExit.ExitPending);
    assert(secondExit.BoundGroundingReceiptId == 0);
    assert(applyEvaluation(terminal772, 1788880345133ULL).Decision
        == Decision::NoEpisode);
    assert(secondActor.SetFallCalls == 1);

    Episode negativeEpisode = ArmedEpisode();
    ReceiptBindingObservation negativeReceipt = GroundReceipt();
    assert(BindGroundingReceipt(negativeEpisode, negativeReceipt));
    LandingEvidence negative = ValidEvidence(negativeEpisode);
    negative.HasVehicle = true;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.HasTransport = true;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.GravityDisabled = true;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.NativeFlight = true;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.ControlledState = true;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.CurrentSplineFinalized = false;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.NativeFalling = true;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.MotionSlotsSettled = false;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.TerminalFloorValid = false;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.TerminalPlatformCompatible = false;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.CurrentEndpointMatches = false;
    AssertPreserved(negativeEpisode, negative);
    negative = ValidEvidence(negativeEpisode);
    negative.ReceiptTerminalOutcome = "native_spline_replaced";
    AssertPreserved(negativeEpisode, negative);
    assert(Resolve(negativeEpisode, negative).DropBoundReceipt);
    negative = ValidEvidence(negativeEpisode);
    negative.ReceiptSuperseded = true;
    AssertPreserved(negativeEpisode, negative);
    assert(Resolve(negativeEpisode, negative).DropBoundReceipt);
    negative.ReceiptTerminal = false;
    negative.ReceiptTerminalOutcome = "pending";
    AssertPreserved(negativeEpisode, negative);
    assert(Resolve(negativeEpisode, negative).DropBoundReceipt);

    negative = ValidEvidence(negativeEpisode);
    negative.FallingFlagsPresent = false;
    assert(Resolve(negativeEpisode, negative).Decision == Decision::CloseEpisode);

    negative = ValidEvidence(negativeEpisode);
    negative.MapId = 1;
    assert(Resolve(negativeEpisode, negative).Decision == Decision::CloseEpisode);
    negative = ValidEvidence(negativeEpisode);
    negative.InstanceId = 3;
    assert(Resolve(negativeEpisode, negative).Decision == Decision::CloseEpisode);
    negative = ValidEvidence(negativeEpisode);
    negative.ReceiptArmedAtMs = 1001;
    assert(Resolve(negativeEpisode, negative).Decision == Decision::CloseEpisode);
    negative = ValidEvidence(negativeEpisode);
    negative.CurrentScope.AttemptId = 8;
    assert(Resolve(negativeEpisode, negative).Decision == Decision::CloseEpisode);
    negative = ValidEvidence(negativeEpisode);
    negative.CurrentScope.WipeGeneration = 4;
    assert(Resolve(negativeEpisode, negative).Decision == Decision::CloseEpisode);
    negative = ValidEvidence(negativeEpisode);
    negative.CurrentScope.RouteGeneration = 12;
    assert(Resolve(negativeEpisode, negative).Decision == Decision::CloseEpisode);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/common"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_vehicle_exit_landing_production_call_sites_are_receipt_bound() -> None:
    assert HEADER.exists()
    assert len(HEADER.read_text(encoding="utf-8").splitlines()) < 1000
    state = STATE.read_text(encoding="utf-8")
    preparation = PREPARATION.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    diagnosis = DIAGNOSIS.read_text(encoding="utf-8")

    assert "ServerVehicleExitLanding::Episode" in state
    assert "ObserveVehicleTransition" in preparation
    assert "MovementProgressDiagnostics().ForReceipt" in preparation
    assert "ServerVehicleExitLanding::Reconcile" in preparation
    assert "SetFall(false)" in HEADER.read_text(encoding="utf-8")
    assert "BindVehicleExitGroundReceipt" in executor
    assert "ArmMovementProgressReceipt" in executor
    assert "server_vehicle_exit_landing" in preparation
    for marker in (
        "terminal_sample",
        "flags_before",
        "flags_after",
        "receipt_terminal_outcome",
        "current_endpoint_matches",
        "controlled_motion_type",
        "observed_vehicle_guid",
        "vehicle_guid",
        "transport_guid",
    ):
        assert marker in diagnosis
