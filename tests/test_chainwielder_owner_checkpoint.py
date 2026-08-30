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
RECORDING_WINDOW = BOT_DIR / "BotWorldPopulationMgrRecordingWindow.cpp"


def test_checkpoint_gate_and_foreign_owner_counterexample_compile(
    tmp_path: Path,
) -> None:
    source = tmp_path / "chainwielder_owner_checkpoint.cpp"
    binary = tmp_path / "chainwielder_owner_checkpoint"
    source.write_text(
        r'''
#include "Bots/BotChainwielderOwnerCheckpoint.h"
#define BOT_RECORDING_WINDOW_IDENTITY_ADAPTER_ONLY
#include "Bots/BotWorldPopulationMgrRecordingWindow.cpp"

#include <cassert>

using namespace BotChainwielderOwnerCheckpoint;

int main()
{
    GateInput disabled;
    assert(RejectionReason(disabled)
        == std::string_view("chainwielder_checkpoint_disabled"));

    std::string const admission(64, 'a');
    std::string const source =
        "6056b52ef4213f701b2c14744b1a98333dd3e302";
    std::string const binaryRevision = "6056b52ef421";
    GateInput valid{
        true, true, ProfileId, ProfileId, PoolTag, ProfileId, NodeId,
        MapId, ActorCount, ActorCount, TargetEntry, true, true, 9,
        FixtureId, admission, admission, source, source, binaryRevision,
    };
    // Exact V17 fail-before: the stale raw equality rejects Trinity's real
    // 12-character generated representation of the same full source.
    assert(valid.ConfigSourceCommit != valid.BinarySourceCommit);
    auto const sourceIdentity = BotControllerRouteHold::CompareSourceIdentity(
        valid.ConfigSourceCommit, valid.RequestedSourceCommit,
        valid.BinarySourceCommit);
    assert(sourceIdentity.Accepted);
    assert(sourceIdentity.AuthoritiesMatch);
    assert(sourceIdentity.BinaryRevisionMatchesSource);
    assert(sourceIdentity.ConfiguredLength == 40);
    assert(sourceIdentity.RequestedLength == 40);
    assert(sourceIdentity.BinaryRevisionLength == 12);
    assert(RejectionReason(valid) == nullptr);

    std::string const selectedRuntimeProfile = ProfileId;
    BotControllerRouteHold::Identity admitted;
    admitted.CohortId = "cohort-v50";
    admitted.ServerEpoch = 51;
    admitted.AttemptId = valid.AttemptId;
    admitted.ScenarioId = valid.ScenarioId;
    admitted.RuntimeProfile = selectedRuntimeProfile;
    admitted.RouteManifestSha256 = admission;
    admitted.RouteGeneration = 1;
    admitted.RouteNodeId = valid.RouteNodeId;
    admitted.ActorGuid = 30008;
    admitted.FixtureId = valid.ConfigFixtureId;
    admitted.SealSha256 = valid.ConfigSealSha256;
    admitted.SourceCommit = valid.ConfigSourceCommit;
    BotControllerRouteHold::Identity bootstrap = admitted;
    bootstrap.ScenarioId.clear();
    bootstrap.RuntimeProfile.clear();
    bootstrap.RouteManifestSha256.clear();
    bootstrap.RouteGeneration = 0;
    bootstrap.RouteNodeId.clear();

    BotControllerRouteHold::State hold;
    assert(hold.BeginAcquire(bootstrap, 1).Accepted);
    assert(hold.CompleteAcquire(admitted, 2).Accepted);

    // Production status boundary one observes the already-admitted scope.
    BotControllerRouteHold::Identity const heldStatusOne =
        BotControllerRouteHold::AdmittedIdentity(hold);
    std::string mutableConfigName = selectedRuntimeProfile;
    std::string mutableMetricsName = selectedRuntimeProfile;

    // Exact V50 mutation happens after admission. Recording changes only the
    // mutable experiment/metrics names and keeps the selected profile value.
    auto const recording = BotRecordingWindowIdentity::BuildNameTransition(
        selectedRuntimeProfile, "autonomy_window_0");
    mutableConfigName = recording.ExperimentName;
    mutableMetricsName = recording.MetricsName;
    assert(mutableConfigName == "autonomy_window_0");
    assert(mutableMetricsName == "autonomy_window_0");
    assert(recording.ImmutableSelectedRuntimeProfile
        == selectedRuntimeProfile);

    // Production status boundary two remains byte-identical across recording.
    BotControllerRouteHold::Identity const heldStatusTwo =
        BotControllerRouteHold::AdmittedIdentity(hold);
    assert(heldStatusOne == heldStatusTwo);
    assert(heldStatusOne.RuntimeProfile
        == recording.ImmutableSelectedRuntimeProfile);

    GateInput staleConfigGate = valid;
    staleConfigGate.AdmittedRuntimeProfile = mutableConfigName;
    assert(RejectionReason(staleConfigGate) == std::string_view(
        "chainwielder_checkpoint_profile_identity_mismatch"));

    // This is the same value-only selector used by the production arm owner;
    // the replay cannot manually substitute the mutable recording name.
    GateInput recordingGate{
        true, true, selectedRuntimeProfile,
        BotControllerRouteHold::AdmittedIdentity(hold).RuntimeProfile,
        PoolTag, ProfileId, NodeId, MapId, ActorCount, ActorCount,
        TargetEntry, true, true, admitted.AttemptId, FixtureId,
        admission, admission, source, source, binaryRevision,
    };
    assert(RejectionReason(recordingGate) == nullptr);
    BotControllerRouteHold::State earlyRelease = hold;
    assert(!earlyRelease.Release(admitted, 3).Accepted);
    assert(earlyRelease.FailureReason
        == "controller_route_hold_release_before_terminal");
    assert(hold.AcknowledgeArm(admitted, 4).Accepted);
    assert(hold.ArmAckCount == 1);
    assert(hold.ObserveCheckpointTerminal(
        admitted, "completed", true, true, 5).Accepted);
    assert(hold.Release(admitted, 6).Accepted);
    assert(hold.ReleaseCount == 1);
    assert(hold.PermitRouteAdvance(admitted, 2));

    // No-recording remains the same exact admitted-profile path.
    GateInput noRecordingGate = recordingGate;
    assert(RejectionReason(noRecordingGate) == nullptr);

    auto expectRejected = [](GateInput input, std::string_view reason)
    {
        assert(RejectionReason(input) == reason);
    };
    GateInput negative = valid;
    negative.SelectedProfile = "wrong-profile";
    expectRejected(negative,
        "chainwielder_checkpoint_profile_identity_mismatch");
    negative = valid;
    negative.AdmittedRuntimeProfile = "wrong-admitted-profile";
    expectRejected(negative,
        "chainwielder_checkpoint_profile_identity_mismatch");
    negative = valid;
    negative.PoolTagFilter = "wrong-pool";
    expectRejected(negative,
        "chainwielder_checkpoint_profile_identity_mismatch");
    negative = valid;
    negative.ScenarioId = "wrong-scenario";
    expectRejected(negative,
        "chainwielder_checkpoint_profile_identity_mismatch");
    negative = valid;
    negative.RouteNodeId = "wrong-node";
    expectRejected(negative,
        "chainwielder_checkpoint_route_identity_mismatch");
    negative = valid;
    negative.RuntimeMapId = 0;
    expectRejected(negative,
        "chainwielder_checkpoint_route_identity_mismatch");
    negative = valid;
    negative.TargetEntry = 0;
    expectRejected(negative,
        "chainwielder_checkpoint_route_identity_mismatch");
    negative = valid;
    negative.ValidationRouteEnabled = false;
    expectRejected(negative,
        "chainwielder_checkpoint_route_identity_mismatch");
    negative = valid;
    negative.AllowRaids = false;
    expectRejected(negative,
        "chainwielder_checkpoint_route_identity_mismatch");
    negative = valid;
    negative.TargetPopulation = 0;
    expectRejected(negative,
        "chainwielder_checkpoint_actor_contract_mismatch");
    negative = valid;
    negative.ActiveActorCount = 0;
    expectRejected(negative,
        "chainwielder_checkpoint_actor_contract_mismatch");
    negative = valid;
    negative.AttemptId = 0;
    expectRejected(negative,
        "chainwielder_checkpoint_attempt_identity_missing");

    valid.ConfigFixtureId = "wrong-fixture";
    assert(RejectionReason(valid) == std::string_view(
        "chainwielder_checkpoint_fixture_identity_mismatch"));
    valid.ConfigFixtureId = FixtureId;
    std::string const otherSeal(64, 'c');
    valid.RequestedSealSha256 = otherSeal;
    assert(RejectionReason(valid)
        == std::string_view("chainwielder_checkpoint_seal_mismatch"));
    valid.RequestedSealSha256 = admission;
    std::string const otherSource(40, 'c');
    valid.RequestedSourceCommit = otherSource;
    assert(RejectionReason(valid) == std::string_view(
        "chainwielder_checkpoint_source_authority_mismatch"));
    valid.RequestedSourceCommit = source;

    std::string const shortRevision(11, 'a');
    valid.BinarySourceCommit = shortRevision;
    assert(RejectionReason(valid) == std::string_view(
        "chainwielder_checkpoint_git_revision_invalid"));
    std::string const nonHexRevision = "6056B52EF421";
    valid.BinarySourceCommit = nonHexRevision;
    assert(RejectionReason(valid) == std::string_view(
        "chainwielder_checkpoint_git_revision_invalid"));
    std::string const wrongPrefix(12, 'd');
    valid.BinarySourceCommit = wrongPrefix;
    assert(RejectionReason(valid) == std::string_view(
        "chainwielder_checkpoint_git_revision_mismatch"));
    std::string const wrongFullRevision(40, 'd');
    valid.BinarySourceCommit = wrongFullRevision;
    assert(RejectionReason(valid) == std::string_view(
        "chainwielder_checkpoint_git_revision_mismatch"));
    valid.BinarySourceCommit = source;
    assert(RejectionReason(valid) == nullptr);

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
#include "Bots/BotWorldPopulationMgrBotState.h"
#include "Bots/BotWorldPopulationMgrValidationRouteMovementCheck.h"
#define BOT_CONTROLLER_ROUTE_HOLD_CONFIG_IDENTITY_ADAPTER_ONLY
#include "Bots/BotWorldPopulationMgrChainwielderOwnerCheckpoint.cpp"
#define BOT_CONTROLLER_ROUTE_HOLD_BOOTSTRAP_ADAPTER_ONLY
#include "Bots/BotWorldPopulationMgrValidationRouteRuntime.cpp"

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

    // Exact V15 fail-before aggregate. Config and command carried the full
    // source identity, while Trinity's generated GitRevision was its exact
    // canonical twelve-character representation. The old raw equality
    // rejected this before CompleteAcquire and retained only bootstrap scope.
    std::string const v15Source =
        "6056b52ef4213f701b2c14744b1a98333dd3e302";
    std::string const v15BinaryRevision = "6056b52ef421";
    assert(v15Source != v15BinaryRevision);
    State v15RecordedFailure;
    Identity v15Bootstrap = bootstrap;
    v15Bootstrap.SourceCommit = v15Source;
    assert(v15RecordedFailure.BeginAcquire(v15Bootstrap, 1).Accepted);
    v15RecordedFailure.Reject("controller_route_hold_config_identity_mismatch");
    assert(v15RecordedFailure.CurrentPhase
        == BotControllerRouteHold::Phase::Failed);
    assert(v15RecordedFailure.Scope.ScenarioId.empty());
    assert(v15RecordedFailure.Scope.RuntimeProfile.empty());
    assert(v15RecordedFailure.Scope.RouteManifestSha256.empty());
    assert(v15RecordedFailure.Scope.RouteGeneration == 0);
    assert(v15RecordedFailure.Scope.RouteNodeId.empty());
    assert(v15RecordedFailure.AcquireCount == 0);

    auto const v15Comparison =
        BotControllerRouteHoldConfigIdentity::Compare(
            identity.FixtureId, identity.FixtureId,
            identity.SealSha256, identity.SealSha256,
            v15Source, v15Source, v15BinaryRevision);
    assert(v15Comparison.Accepted);
    assert(v15Comparison.FailureField == std::string_view("none"));
    assert(v15Comparison.SourceMatches);
    assert(v15Comparison.BinaryRevisionFormatValid);
    assert(v15Comparison.BinaryRevisionMatchesSource);
    assert(v15Comparison.ConfiguredSourceLength == 40);
    assert(v15Comparison.RequestedSourceLength == 40);
    assert(v15Comparison.BinaryRevisionLength == 12);

    // Exact v13 fail-before: configuration has already admitted generation
    // one, but the old 0 -> 1-only gate rejects that canonical 1 -> 1 bind.
    State recordedFailure;
    assert(recordedFailure.BeginAcquire(bootstrap, 10).Accepted);
    assert(!GateRouteMutation(recordedFailure, identity, 1));
    assert(recordedFailure.CurrentPhase == BotControllerRouteHold::Phase::Failed);
    assert(recordedFailure.Scope.ScenarioId.empty());
    assert(recordedFailure.Scope.RuntimeProfile.empty());
    assert(recordedFailure.Scope.RouteManifestSha256.empty());
    assert(recordedFailure.Scope.RouteGeneration == 0);
    assert(recordedFailure.Scope.RouteNodeId.empty());
    assert(recordedFailure.AcquireCount == 0);
    assert(recordedFailure.SuppressedRouteAdvanceCount == 1);
    assert(recordedFailure.FailureReason
        == "controller_route_hold_bootstrap_route_drift");

    // Production bootstrap adapter admits only the complete, identity-matched
    // initial bind. Applying node zero keeps the already admitted generation
    // unchanged and no ordinary action can execute before acknowledgement.
    State hold;
    assert(hold.BeginAcquire(bootstrap, 20).Accepted);
    auto const configComparison =
        BotControllerRouteHoldConfigIdentity::Compare(
            identity.FixtureId, bootstrap.FixtureId,
            identity.SealSha256, bootstrap.SealSha256,
            identity.SourceCommit, bootstrap.SourceCommit,
            std::string(12, 'c'));
    assert(configComparison.Accepted);
    uint64 routeGeneration = 1;
    int ordinaryBeforeAckAttempts = 0;
    assert(AdmitCanonicalInitialRouteBinding(hold, identity, 1)
        == InitialRouteBindingDecision::Admitted);
    routeGeneration = 1;
    assert(routeGeneration == 1);
    assert(ordinaryBeforeAckAttempts == 0);
    assert(hold.SuppressedRouteActionCount == 0);
    assert(hold.SuppressedRouteAdvanceCount == 0);
    assert(hold.CompleteAcquire(identity, 21).Accepted);
    assert(hold.CurrentPhase == BotControllerRouteHold::Phase::Held);
    assert(hold.Scope == identity);
    assert(hold.AcquireCount == 1);

    // Without a hold, the generic route candidate and later route mutation
    // remain ordinary runtime behavior.
    State before;
    assert(GateRouteMutation(before, identity, 2));
    Kernel beforeKernel;
    beforeKernel.Begin(10);
    int beforeAttempts = 0;
    beforeKernel.Submit(CandidateFor("ordinary-route", AdmissionClass::Unknown,
        beforeAttempts, beforeKernel));
    beforeKernel.Resolve();
    assert(beforeAttempts == 1);

    // Held production kernel: setup/safety remains executable while ordinary
    // route work and an early checkpoint path are both suppressed and counted.
    Kernel heldKernel;
    heldKernel.Begin(22);
    InstallAdmissionPolicy(heldKernel, hold, identity, 77);
    int setupAttempts = 0;
    int defensiveAttempts = 0;
    int ordinaryAttempts = 0;
    int earlyCheckpointAttempts = 0;
    heldKernel.Submit(CandidateFor("formation", AdmissionClass::FormationMovement,
        setupAttempts, heldKernel));
    Candidate defensive = CandidateFor("defensive-survival",
        AdmissionClass::Unknown, defensiveAttempts, heldKernel);
    defensive.ActionPriority = Priority::Survival;
    defensive.RequiredResources = Uses(Resource::Cast);
    heldKernel.Submit(std::move(defensive));
    heldKernel.Submit(CandidateFor("ordinary", AdmissionClass::Unknown,
        ordinaryAttempts, heldKernel));
    heldKernel.Submit(CandidateFor("checkpoint-early",
        AdmissionClass::ControllerCheckpointObservation,
        earlyCheckpointAttempts, heldKernel, identity.ScopeKey()));
    heldKernel.Resolve();
    assert(setupAttempts == 1);
    assert(defensiveAttempts == 1);
    assert(ordinaryAttempts == 0);
    assert(earlyCheckpointAttempts == 0);
    assert(hold.SuppressedRouteActionCount == 2);
    assert(!GateRouteMutation(hold, identity, 2));
    assert(hold.SuppressedRouteAdvanceCount == 1);

    assert(hold.AcknowledgeArm(identity, 23).Accepted);
    Kernel armedKernel;
    armedKernel.Begin(24);
    InstallAdmissionPolicy(armedKernel, hold, identity, 77);
    BotMovementArbitration::Lease nativeLease;
    nativeLease.MovementOwner = BotMovementArbitration::Owner::CombatRange;
    nativeLease.MovementPriority = BotMovementArbitration::Priority::Combat;
    nativeLease.ExpiresAtMs = 24;
    nativeLease.MovementScope = { 9, 2, 1, 669, 31 };
    int routeExecutionCount = 0;
    int routeActionViewAttempts = 0;
    int routeMovementViewAttempts = 0;
    int unrelatedHazardAttempts = 0;
    int armedOrdinaryAttempts = 0;
    int foreignActorAttempts = 0;
    int foreignSurvivalMovementAttempts = 0;
    BotChainwielderOwnerCheckpoint::OwnerSnapshot routeIdentity;

    // Exact fail-before scheduler shape: an unrelated Survival-priority
    // movement used to be admitted first, replace the completed combat-range
    // lease with Hazard, and consume the movement lane before Route ran.
    Candidate unrelatedHazard;
    unrelatedHazard.Key = "unrelated-hazard";
    unrelatedHazard.Source = "adaptive_raid_trash";
    unrelatedHazard.ActionPriority = Priority::Survival;
    unrelatedHazard.UtilityScore = 8.0f;
    unrelatedHazard.RequiredResources = Uses(Resource::Movement);
    unrelatedHazard.Attempt = [&nativeLease, &unrelatedHazardAttempts]()
    {
        ++unrelatedHazardAttempts;
        BotMovementArbitration::Request request;
        request.MovementOwner = BotMovementArbitration::Owner::Hazard;
        request.MovementPriority = BotMovementArbitration::Priority::Hazard;
        request.ExpiresAtMs = 100;
        request.MovementScope = { 9, 2, 1, 669, 31 };
        request.X = 5.0f;
        BotMovementArbitration::Apply(nativeLease, request);
        return Outcome::Started("unrelated_hazard_started");
    };
    armedKernel.Submit(std::move(unrelatedHazard));

    Candidate routeAction;
    routeAction.Key = "generic-route-action";
    routeAction.Source = "validation_route_adapter";
    routeAction.ActionPriority = Priority::Mechanic;
    routeAction.UtilityScore = 3.1f;
    routeAction.Attempt = [&nativeLease, &routeIdentity,
        &routeExecutionCount, &routeActionViewAttempts]()
    {
        ++routeActionViewAttempts;
        ++routeExecutionCount;
        BotMovementArbitration::Request request;
        request.MovementOwner = BotMovementArbitration::Owner::Route;
        request.MovementPriority = BotMovementArbitration::Priority::Route;
        request.ExpiresAtMs = 100;
        request.MovementScope = { 9, 2, 1, 669, 31 };
        request.X = 10.0f;
        request.Y = 20.0f;
        request.Z = 30.0f;
        assert(BotMovementArbitration::Evaluate(nativeLease, request, 24)
            == BotMovementArbitration::Decision::Acquire);
        BotMovementArbitration::Apply(nativeLease, request);
        routeIdentity.MovementOwner = nativeLease.MovementOwner;
        routeIdentity.ActivePathValid = true;
        routeIdentity.ActivePathSegmentValid = true;
        routeIdentity.ActivePathTraversalMode = "native_route";
        routeIdentity.ActivePathAttemptId = request.MovementScope.AttemptId;
        routeIdentity.ActivePathWipeGeneration =
            request.MovementScope.WipeGeneration;
        routeIdentity.ActivePathRouteGeneration =
            request.MovementScope.RouteGeneration;
        routeIdentity.ActivePathRouteNodeId = "route.node.a";
        routeIdentity.ActivePathToX = request.X;
        routeIdentity.ActivePathToY = request.Y;
        routeIdentity.ActivePathToZ = request.Z;
        routeIdentity.DodgeCasterGuid = 9001;
        routeIdentity.DodgeSpellId = 9002;
        routeIdentity.DodgeUntilMs = 100;
        return Outcome::NotApplicable("route_movement_only");
    };
    Candidate routeMovement;
    routeMovement.Key = "generic-route-movement";
    routeMovement.Source = "validation_route_adapter";
    routeMovement.ActionPriority = Priority::Mechanic;
    routeMovement.UtilityScore = 3.0f;
    routeMovement.Attempt = [&nativeLease, &routeExecutionCount,
        &routeMovementViewAttempts]()
    {
        ++routeMovementViewAttempts;
        assert(routeExecutionCount == 1);
        assert(nativeLease.MovementOwner
            == BotMovementArbitration::Owner::Route);
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
    Candidate foreignSurvivalMovement = CandidateFor(
        "foreign-survival-movement", AdmissionClass::Unknown,
        foreignSurvivalMovementAttempts, foreignKernel);
    foreignSurvivalMovement.Source = "adaptive_raid_trash";
    foreignSurvivalMovement.ActionPriority = Priority::Survival;
    foreignSurvivalMovement.RequiredResources = Uses(Resource::Movement);
    foreignKernel.Submit(std::move(foreignSurvivalMovement));
    armedKernel.Resolve();
    foreignKernel.Resolve();
    assert(routeExecutionCount == 1);
    assert(routeActionViewAttempts == 1);
    assert(routeMovementViewAttempts == 1);
    assert(unrelatedHazardAttempts == 0);
    assert(armedOrdinaryAttempts == 0);
    assert(foreignActorAttempts == 0);
    assert(foreignSurvivalMovementAttempts == 1);
    assert(nativeLease.MovementOwner == BotMovementArbitration::Owner::Route);
    assert(routeIdentity.ActivePathRouteGeneration == identity.RouteGeneration);
    assert(routeIdentity.ActivePathRouteNodeId == identity.RouteNodeId);

    // Trigger before the separate configured-hazard producer owns a later
    // exit. Hazard identity is deliberately absent at this checkpoint edge.
    routeIdentity.DodgeCasterGuid = 0;
    routeIdentity.DodgeSpellId = 0;
    routeIdentity.DodgeUntilMs = 0;
    auto const routeTrigger =
        BotChainwielderOwnerCheckpoint::SelectInjectionTrigger(
        true, routeIdentity, identity.AttemptId, 2,
        identity.RouteGeneration, identity.RouteNodeId, true, false);
    assert(routeTrigger);
    assert(routeTrigger.ActiveRoutePath);
    assert(!routeTrigger.ArmedRouteHazardRetry);

    auto expectNoActiveRouteTrigger = [&](bool actorMatches,
        BotChainwielderOwnerCheckpoint::OwnerSnapshot snapshot,
        uint64 attemptId, uint32 wipeGeneration,
        uint64 routeGeneration, std::string_view routeNodeId,
        bool nativeRouteMotion)
    {
        auto const trigger =
            BotChainwielderOwnerCheckpoint::SelectInjectionTrigger(
            actorMatches, snapshot, attemptId, wipeGeneration,
            routeGeneration, routeNodeId, nativeRouteMotion, false);
        assert(!trigger);
        assert(!trigger.ActiveRoutePath);
    };
    BotChainwielderOwnerCheckpoint::OwnerSnapshot missingRoutePath =
        routeIdentity;
    missingRoutePath.ActivePathValid = false;
    expectNoActiveRouteTrigger(true, missingRoutePath, identity.AttemptId, 2,
        identity.RouteGeneration, identity.RouteNodeId, true);
    expectNoActiveRouteTrigger(false, routeIdentity, identity.AttemptId, 2,
        identity.RouteGeneration, identity.RouteNodeId, true);
    expectNoActiveRouteTrigger(true, routeIdentity, identity.AttemptId + 1, 2,
        identity.RouteGeneration, identity.RouteNodeId, true);
    expectNoActiveRouteTrigger(true, routeIdentity, identity.AttemptId, 3,
        identity.RouteGeneration, identity.RouteNodeId, true);
    expectNoActiveRouteTrigger(true, routeIdentity, identity.AttemptId, 2,
        identity.RouteGeneration + 1, identity.RouteNodeId, true);
    expectNoActiveRouteTrigger(true, routeIdentity, identity.AttemptId, 2,
        identity.RouteGeneration, "route.node.stale", true);
    expectNoActiveRouteTrigger(true, routeIdentity, identity.AttemptId, 2,
        identity.RouteGeneration, identity.RouteNodeId, false);

    // The production future-pack rejection is receipt-zero and observe-only
    // against the actor's active Route path. Its full identity survives the
    // immediate observation and the next production tick.
    BotChainwielderOwnerCheckpoint::HazardRejectionObservation const rejection{
        false, BotMovementArbitration::Owner::Hazard,
        "future_pack_destination", "rejected",
        "route_destination_future_pack_unsafe", 0 };
    assert(BotChainwielderOwnerCheckpoint::
        IsExactReceiptlessHazardRejection(rejection));
    assert(BotWorldPopulationMgrBotState::MovementRejectionIsolation::
        ClassifyPreAdmissionRejection(
            rejection.MovementOwner, nativeLease.MovementOwner, true, false)
        == BotWorldPopulationMgrBotState::MovementRejectionIsolation::
            Disposition::ObserveOnlyPreserveExistingOwner);
    BotChainwielderOwnerCheckpoint::OwnerSnapshot const
        routeIdentityAfterRejection = routeIdentity;
    assert(BotChainwielderOwnerCheckpoint::SameRouteIdentity(
        routeIdentity, routeIdentityAfterRejection));
    auto const subsequentTickTrigger =
        BotChainwielderOwnerCheckpoint::SelectInjectionTrigger(
        true, routeIdentityAfterRejection, identity.AttemptId, 2,
        identity.RouteGeneration, identity.RouteNodeId, true, false);
    assert(subsequentTickTrigger.ActiveRoutePath);

    // The later accepted configured-hazard exit is independently Hazard at
    // both arbitration dimensions. It is neither a Route trigger nor the
    // receipt-zero rejected observation above.
    auto const configuredHazardOwner =
        BotWorldPopulationMgrValidationRoute::
            SelectValidationRouteMovementOwner(true, true);
    assert(configuredHazardOwner.Owner
        == BotMovementArbitration::Owner::Hazard);
    assert(configuredHazardOwner.Priority
        == BotMovementArbitration::Priority::Hazard);
    BotChainwielderOwnerCheckpoint::OwnerSnapshot acceptedHazardPath =
        routeIdentity;
    acceptedHazardPath.MovementOwner = configuredHazardOwner.Owner;
    expectNoActiveRouteTrigger(true, acceptedHazardPath, identity.AttemptId, 2,
        identity.RouteGeneration, identity.RouteNodeId, true);
    BotChainwielderOwnerCheckpoint::HazardRejectionObservation const
        acceptedHazard{
        true, configuredHazardOwner.Owner, "movement_launch", "submitted", "",
        2 };
    assert(!BotChainwielderOwnerCheckpoint::
        IsExactReceiptlessHazardRejection(acceptedHazard));
    auto const missingConfiguredHazardOwner =
        BotWorldPopulationMgrValidationRoute::
            SelectValidationRouteMovementOwner(false, true);
    assert(missingConfiguredHazardOwner.Owner
        == BotMovementArbitration::Owner::CombatRange);
    assert(missingConfiguredHazardOwner.Priority
        == BotMovementArbitration::Priority::Combat);

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

    Kernel syntheticKernel;
    syntheticKernel.Begin(24);
    InstallAdmissionPolicy(syntheticKernel, hold, identity, 77);
    int syntheticAttempts = 0;
    syntheticKernel.Submit(CandidateFor("checkpoint-synthetic",
        AdmissionClass::ControllerCheckpointObservation,
        syntheticAttempts, syntheticKernel, identity.ScopeKey()));
    syntheticKernel.Resolve();
    assert(syntheticAttempts == 0);

    assert(hold.ObserveCheckpointTerminal(identity,
        "route_identity_preserved_after_receiptless_hazard_rejection", true,
        true, 25).Accepted);
    State duplicateTerminal = hold;
    assert(!duplicateTerminal.ObserveCheckpointTerminal(identity,
        "route_identity_preserved_after_receiptless_hazard_rejection",
        true, true, 26).Accepted);
    assert(duplicateTerminal.FailureReason
        == "controller_route_hold_checkpoint_terminal_stale");
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

    auto expectIdentityDrift = [&](Identity changed)
    {
        State drift;
        assert(drift.BeginAcquire(bootstrap, 1).Accepted);
        assert(drift.CompleteAcquire(identity, 2).Accepted);
        assert(!GateRouteMutation(drift, changed, 2));
        assert(drift.FailureReason
            == "controller_route_hold_identity_drift");
    };
    Identity changed = identity;
    changed.CohortId = "cohort-changed";
    expectIdentityDrift(changed);
    changed = identity;
    ++changed.ServerEpoch;
    expectIdentityDrift(changed);
    changed = identity;
    ++changed.AttemptId;
    expectIdentityDrift(changed);
    changed = identity;
    changed.ScenarioId = "scenario-changed";
    expectIdentityDrift(changed);
    changed = identity;
    changed.RuntimeProfile = "runtime-changed";
    expectIdentityDrift(changed);
    changed = identity;
    changed.RouteManifestSha256 = std::string(64, 'd');
    expectIdentityDrift(changed);
    changed = identity;
    ++changed.RouteGeneration;
    expectIdentityDrift(changed);
    changed = identity;
    changed.RouteNodeId = "route.node.changed";
    expectIdentityDrift(changed);
    changed = identity;
    ++changed.ActorGuid;
    expectIdentityDrift(changed);
    changed = identity;
    changed.FixtureId = "fixture-changed";
    expectIdentityDrift(changed);
    changed = identity;
    changed.SealSha256 = std::string(64, 'd');
    expectIdentityDrift(changed);
    changed = identity;
    changed.SourceCommit = std::string(40, 'd');
    expectIdentityDrift(changed);

    State duplicateRelease = hold;
    assert(!duplicateRelease.Release(identity, 27).Accepted);
    assert(duplicateRelease.CurrentPhase
        == BotControllerRouteHold::Phase::Released);
    assert(duplicateRelease.FailureReason
        == "controller_route_hold_duplicate_release");

    State missingAdmission;
    assert(missingAdmission.BeginAcquire(bootstrap, 1).Accepted);
    Identity missing = identity;
    missing.ScenarioId.clear();
    missing.RuntimeProfile.clear();
    missing.RouteManifestSha256.clear();
    missing.RouteNodeId.clear();
    assert(AdmitCanonicalInitialRouteBinding(missingAdmission, missing, 1)
        == InitialRouteBindingDecision::Rejected);
    assert(missingAdmission.FailureReason
        == "controller_route_hold_admission_identity_missing");

    State partialBootstrap;
    assert(partialBootstrap.BeginAcquire(bootstrap, 1).Accepted);
    Identity partial = identity;
    partial.RouteNodeId.clear();
    assert(AdmitCanonicalInitialRouteBinding(partialBootstrap, partial, 1)
        == InitialRouteBindingDecision::Rejected);
    assert(partialBootstrap.FailureReason
        == "controller_route_hold_bootstrap_identity_partial");

    State bootstrapDrift;
    assert(bootstrapDrift.BeginAcquire(bootstrap, 1).Accepted);
    Identity wrongActor = identity;
    wrongActor.ActorGuid = 78;
    assert(AdmitCanonicalInitialRouteBinding(bootstrapDrift, wrongActor, 1)
        == InitialRouteBindingDecision::Rejected);
    assert(bootstrapDrift.FailureReason
        == "controller_route_hold_acquire_identity_drift");

    // Generation-zero manifests retain the existing exact 0 -> 1 bootstrap.
    State zeroGeneration;
    assert(zeroGeneration.BeginAcquire(bootstrap, 1).Accepted);
    assert(AdmitCanonicalInitialRouteBinding(zeroGeneration, bootstrap, 1)
        == InitialRouteBindingDecision::NotApplicable);
    assert(GateRouteMutation(zeroGeneration, bootstrap, 1));

    auto compare = [](std::string configuredFixture,
        std::string requestedFixture, std::string configuredSeal,
        std::string requestedSeal, std::string configuredSource,
        std::string requestedSource, std::string binaryRevision)
    {
        return BotControllerRouteHoldConfigIdentity::Compare(
            configuredFixture, requestedFixture, configuredSeal,
            requestedSeal, configuredSource, requestedSource,
            binaryRevision);
    };
    auto fixtureMismatch = compare("configured-fixture", "requested-fixture",
        identity.SealSha256, identity.SealSha256, identity.SourceCommit,
        identity.SourceCommit, std::string(12, 'c'));
    assert(!fixtureMismatch.Accepted);
    assert(fixtureMismatch.FailureField == std::string_view("fixture_id"));
    assert(fixtureMismatch.FailureReason == std::string_view(
        "controller_route_hold_config_fixture_id_mismatch"));

    auto sealMismatch = compare(identity.FixtureId, identity.FixtureId,
        std::string(64, 'a'), std::string(64, 'b'), identity.SourceCommit,
        identity.SourceCommit, std::string(12, 'c'));
    assert(!sealMismatch.Accepted);
    assert(sealMismatch.FailureField == std::string_view("seal_sha256"));
    assert(sealMismatch.FailureReason == std::string_view(
        "controller_route_hold_config_seal_mismatch"));

    auto sourceMismatch = compare(identity.FixtureId, identity.FixtureId,
        identity.SealSha256, identity.SealSha256, std::string(40, 'c'),
        std::string(40, 'd'), std::string(12, 'c'));
    assert(!sourceMismatch.Accepted);
    assert(sourceMismatch.FailureField == std::string_view("source_commit"));
    assert(sourceMismatch.FailureReason == std::string_view(
        "controller_route_hold_config_source_commit_mismatch"));

    auto gitMismatch = compare(identity.FixtureId, identity.FixtureId,
        identity.SealSha256, identity.SealSha256, identity.SourceCommit,
        identity.SourceCommit, std::string(12, 'd'));
    assert(!gitMismatch.Accepted);
    assert(gitMismatch.FailureField == std::string_view("git_revision"));
    assert(gitMismatch.FailureReason == std::string_view(
        "controller_route_hold_git_revision_mismatch"));

    auto missingFixture = compare("", identity.FixtureId,
        identity.SealSha256, identity.SealSha256, identity.SourceCommit,
        identity.SourceCommit, std::string(12, 'c'));
    assert(!missingFixture.Accepted);
    assert(!missingFixture.FixtureConfiguredPresent);
    assert(missingFixture.FailureReason == std::string_view(
        "controller_route_hold_config_fixture_id_missing"));

    // A post-bind config change remains a typed failure; the comparison is
    // not refreshed or relaxed after the admission identity is established.
    auto configDrift = compare(identity.FixtureId, identity.FixtureId,
        identity.SealSha256, identity.SealSha256, std::string(40, 'd'),
        identity.SourceCommit, std::string(12, 'd'));
    assert(!configDrift.Accepted);
    assert(configDrift.FailureReason == std::string_view(
        "controller_route_hold_config_source_commit_mismatch"));
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
    recording = RECORDING_WINDOW.read_text(encoding="utf-8")

    assert "InstallControllerRouteHoldAdmissionPolicy(context)" in preparation
    assert fallback.count("MarkCheckpointObservationCandidate(") == 2
    assert "InstallAdmissionPolicy(" in MODULE.read_text(encoding="utf-8")
    assert "GateRouteMutation(" in MODULE.read_text(encoding="utf-8")
    assert "BotControllerRouteHoldConfigIdentity::Compare(" in (
        MODULE.read_text(encoding="utf-8")
    )
    assert "GitRevision::GetHash()" in MODULE.read_text(encoding="utf-8")
    assert r'\"config_identity_comparison\"' in MODULE.read_text(encoding="utf-8")
    assert "PermitControllerRouteAdvance(index + 1)" in route_runtime
    assert "AdmitCanonicalInitialRouteBinding(" in route_runtime
    assert "InitialRouteBindingDecision::Rejected" in route_runtime
    assert "PermitControllerRouteAdvance(prospectiveGeneration)" in route_runtime
    assert "controller_route_hold" in raid_runtime
    assert 'action == "start-held"' in command
    assert 'action == "release"' in command
    assert "BuildNameTransition(" in recording
    assert "AdmittedIdentity(controllerHold)" in MODULE.read_text(
        encoding="utf-8"
    )
    assert "State const& controllerHold" in MODULE.read_text(encoding="utf-8")
    assert "State preservedControllerHold =" in MODULE.read_text(
        encoding="utf-8"
    )
    assert "std::move(checkpoint.ControllerRouteHold)" in MODULE.read_text(
        encoding="utf-8"
    )
    assert "checkpoint = {};" in MODULE.read_text(encoding="utf-8")
    assert "std::move(preservedControllerHold)" in MODULE.read_text(
        encoding="utf-8"
    )
    assert "State controllerHold =" not in MODULE.read_text(encoding="utf-8")
    assert "Cohort().Config.Name," not in MODULE.read_text(encoding="utf-8")


def test_checkpoint_crosses_real_executor_and_production_tick_boundary() -> None:
    header = HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    update = UPDATE.read_text(encoding="utf-8")

    assert "GetCreatureData(sourceId)" in module
    assert "IsValidationRoutePatrolCombatPointSafe" in module
    assert "ExecuteMovementIntent(state, bot, rejected)" in module
    assert "MovementPlannerDiagnostics().Latest" in module
    assert "IsExactReceiptlessHazardRejection" in module
    assert 'observation.Gate == "future_pack_destination"' in header
    assert 'observation.Result == "rejected"' in header
    assert "observation.LaunchReceiptId == 0" in header
    assert "SameRouteIdentity(\n        checkpoint.Before, immediateAfter)" in module
    assert "SameRouteIdentity(\n            checkpoint.Before, checkpoint.After)" in module
    assert "InjectionTriggerDecision const trigger = SelectInjectionTrigger(" in module
    assert "checkpoint.Before = triggerSnapshot" in module
    trigger_source = module[
        module.index("InjectionTriggerDecision const trigger") :
        module.index("if (!trigger)")
    ]
    assert "matchingHazardIdentity" not in trigger_source
    assert '"route_identity_preserved_after_receiptless_hazard_rejection"' in module
    assert '"hazard_exit_completed"' not in module

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
    assert "CompareSourceIdentity(" in header
    assert "ConfigSourceCommit != input.BinarySourceCommit" not in header
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
        RECORDING_WINDOW,
    ):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
