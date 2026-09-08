from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "src/server/game/Bots/BotProfileCombatRangeCandidate.h"
CHECKPOINT = ROOT / "src/server/game/Bots/BotProfileCombatRangeCheckpoint.h"
FALLBACK = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp"
MOVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatMovement.cpp"
DECISION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotDecision.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
OBSERVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrProfileCombatRangeCheckpoint.cpp"
CONFIG = ROOT / "src/server/game/Bots/BotWorldPopulationMgrConfig.cpp"


def test_production_adapter_value_matrix_and_arbiter_boundary(tmp_path: Path) -> None:
    source = tmp_path / "profile_combat_range_production_fixture.cpp"
    binary = tmp_path / "profile_combat_range_production_fixture"
    source.write_text(
        r'''
#include "Bots/BotProfileCombatRangeCandidate.h"

#include <cassert>

using BotProfileCombatRangeCandidate::Decision;

Decision ValidDecision()
{
    Decision decision;
    decision.TargetPresent = true;
    decision.TargetInWorld = true;
    decision.TargetAlive = true;
    decision.TargetAttackable = true;
    decision.SameMap = true;
    decision.SameInstance = true;
    decision.Distance = 4.0f;
    decision.MinRange = 8.0f;
    return decision;
}

BotActionArbitration::Resolution Run(Decision decision, bool& moved)
{
    decision.Move = [&moved]()
    {
        moved = true;
        return true;
    };
    BotActionArbitration::Kernel kernel;
    kernel.Begin(1000);
    BotProfileCombatRangeCandidate::Request request;
    request.UtilityScore = 0.9f;
    request.Observe = [decision = std::move(decision)]() mutable
    {
        return decision;
    };
    assert(kernel.Submit(BotProfileCombatRangeCandidate::Build(
        std::move(request))));
    kernel.Resolve();
    return kernel.LastResolution();
}

void AssertRejected(Decision decision, char const* reason)
{
    bool moved = false;
    BotActionArbitration::Resolution const resolution = Run(
        std::move(decision), moved);
    assert(!moved);
    assert(!resolution.AnyCommitted);
    assert(resolution.Trace.size() == 1);
    assert(resolution.Trace[0].Key
        == BotProfileCombatRangeCandidate::Key);
    assert(resolution.Trace[0].Reason == reason);
}

int main()
{
    Decision positive = ValidDecision();
    bool moved = false;
    BotActionArbitration::Resolution const positiveResolution = Run(
        std::move(positive), moved);
    assert(moved);
    assert(positiveResolution.AnyCommitted);
    assert(positiveResolution.ClaimedResources
        == BotActionArbitration::Uses(BotActionArbitration::Resource::Movement));
    assert(positiveResolution.Trace[0].Key
        == BotProfileCombatRangeCandidate::Key);
    assert(positiveResolution.Trace[0].Reason
        == "profile_combat_min_range_reconciled");

    for (int field = 0; field != 6; ++field)
    {
        Decision invalid = ValidDecision();
        switch (field)
        {
            case 0: invalid.TargetPresent = false; break;
            case 1: invalid.TargetInWorld = false; break;
            case 2: invalid.TargetAlive = false; break;
            case 3: invalid.TargetAttackable = false; break;
            case 4: invalid.SameMap = false; break;
            case 5: invalid.SameInstance = false; break;
        }
        AssertRejected(std::move(invalid), "profile_combat_target_invalid");
    }

    Decision legalBand = ValidDecision();
    legalBand.Distance = legalBand.MinRange;
    AssertRejected(std::move(legalBand), "profile_min_range_satisfied");

    Decision latchClosed = ValidDecision();
    latchClosed.TypedDrudgeValidationRoute = true;
    latchClosed.AdaptiveDrudgeOwnsNode = true;
    latchClosed.DrudgeCombatAuthorityAllowed = false;
    AssertRejected(std::move(latchClosed), "drudge_activation_latch_closed");

    for (bool noLineOfSight : { false, true })
    {
        Decision drudge = ValidDecision();
        drudge.OwnedDrudge = true;
        drudge.Distance = noLineOfSight ? 10.0f : 40.0f;
        drudge.MaxRange = 30.0f;
        drudge.NoLineOfSight = noLineOfSight;
        bool drudgeMoved = false;
        BotActionArbitration::Resolution const resolution = Run(
            std::move(drudge), drudgeMoved);
        assert(drudgeMoved && resolution.AnyCommitted);
        assert(resolution.Trace[0].Reason
            == (noLineOfSight ? "profile_combat_los_reconciled"
                : "profile_combat_range_reconciled"));
    }

    // The range adapter owns Movement only. An ordinary cast candidate can
    // commit in the same kernel resolution.
    BotActionArbitration::Kernel coexistKernel;
    coexistKernel.Begin(1000);
    bool rangeMoved = false;
    Decision coexistDecision = ValidDecision();
    coexistDecision.Move = [&rangeMoved]()
    {
        rangeMoved = true;
        return true;
    };
    BotProfileCombatRangeCandidate::Request coexistRequest;
    coexistRequest.UtilityScore = 0.9f;
    coexistRequest.Observe = [decision = std::move(coexistDecision)]() mutable
    {
        return decision;
    };
    assert(coexistKernel.Submit(BotProfileCombatRangeCandidate::Build(
        std::move(coexistRequest))));
    bool cast = false;
    BotActionArbitration::Candidate ordinaryCast;
    ordinaryCast.Key = "world.profile_combat";
    ordinaryCast.Source = "db_class_spec_profile";
    ordinaryCast.ActionPriority = BotActionArbitration::Priority::TrainedDamage;
    ordinaryCast.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::GlobalCooldown,
        BotActionArbitration::Resource::Cast,
        BotActionArbitration::Resource::Target);
    ordinaryCast.Attempt = [&cast]()
    {
        cast = true;
        return BotActionArbitration::Outcome::Submitted("cast_submitted");
    };
    assert(coexistKernel.Submit(std::move(ordinaryCast)));
    BotActionArbitration::Resolution const& coexist = coexistKernel.Resolve();
    assert(rangeMoved && cast);
    assert(coexist.CommittedCandidates.size() == 2);

    // This is arbiter-only coverage for a producer-owned higher-priority
    // Movement lane. The production replay must provide the real hazard
    // producer receipt; this test does not certify that live boundary.
    BotActionArbitration::Kernel conflictKernel;
    conflictKernel.Begin(1000);
    bool conflictRangeMoved = false;
    Decision conflictDecision = ValidDecision();
    conflictDecision.Move = [&conflictRangeMoved]()
    {
        conflictRangeMoved = true;
        return true;
    };
    BotProfileCombatRangeCandidate::Request conflictRequest;
    conflictRequest.UtilityScore = 0.9f;
    conflictRequest.Observe = [decision = std::move(conflictDecision)]() mutable
    {
        return decision;
    };
    assert(conflictKernel.Submit(BotProfileCombatRangeCandidate::Build(
        std::move(conflictRequest))));
    bool hazard = false;
    BotActionArbitration::Candidate observedHazard;
    observedHazard.Key = "observed.hazard.movement";
    observedHazard.Source = "observed_hazard_producer";
    observedHazard.ActionPriority = BotActionArbitration::Priority::Survival;
    observedHazard.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    observedHazard.Attempt = [&hazard]()
    {
        hazard = true;
        return BotActionArbitration::Outcome::Started("hazard_started");
    };
    assert(conflictKernel.Submit(std::move(observedHazard)));
    BotActionArbitration::Resolution const& conflict = conflictKernel.Resolve();
    assert(hazard && !conflictRangeMoved);
    assert(conflict.Trace.size() == 2);
    assert(conflict.Trace[1].Key
        == BotProfileCombatRangeCandidate::Key);
    assert(conflict.Trace[1].Status == "resource_conflict");
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_production_wiring_and_observer_are_default_off() -> None:
    adapter = ADAPTER.read_text(encoding="utf-8")
    checkpoint = CHECKPOINT.read_text(encoding="utf-8")
    fallback = FALLBACK.read_text(encoding="utf-8")
    decision = DECISION.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert 'constexpr char Key[] = "world.profile_combat_range"' in adapter
    assert "BotProfileCombatRangeCandidate::Build" in fallback
    assert "rangeRequest.Observe" in fallback
    assert "generic_profile_min_range_production_boundary_v1" in checkpoint
    assert "ProfileCombatRangeCheckpointEnable = false" in (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrConfig.h"
    ).read_text(encoding="utf-8")
    config_header = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrConfig.h"
    ).read_text(encoding="utf-8")
    config_source = CONFIG.read_text(encoding="utf-8")
    for field in (
        "RuntimeTargetGuid", "TargetSpawnId", "TargetEntry", "TargetMapId",
    ):
        assert f"ProfileCombatRangeCheckpoint{field}" in config_header
        assert (
            f"ProfileCombatRangeCheckpoint.{field}\"" in config_source
        )
    assert "ProfileCombatRangeCheckpointTargetGuid" not in config_header
    assert "ProfileCombatRangeCheckpoint.TargetGuid\"" not in config_source
    observer = OBSERVER.read_text(encoding="utf-8")
    assert "context.Target->GetGUID().GetCounter()" in observer
    assert "LastCombatAttempt.TargetGuid.GetCounter()" in observer
    assert "ObserveProfileCombatRangeCheckpoint(context);" in decision
    assert "BotWorldPopulationMgrProfileCombatRangeCheckpoint.cpp" in cmake
    assert "MotionMaster" not in checkpoint
    assert "MoveBotToPoint" not in checkpoint
    assert "Teleport" not in checkpoint


def test_production_checkpoint_transition_value_matrix(tmp_path: Path) -> None:
    source = tmp_path / "profile_combat_range_checkpoint_transition.cpp"
    binary = tmp_path / "profile_combat_range_checkpoint_transition"
    source.write_text(
        r'''
#include "Bots/BotProfileCombatRangeCheckpoint.h"
#include "ObjectGuid.h"

#include <cassert>

using namespace BotProfileCombatRangeCheckpoint;

TransitionEvidence ValidTransition()
{
    TransitionEvidence evidence;
    evidence.CheckpointScope = {
        4, 30010, 39, 7, 0, 1, 669, 123,
    };
    evidence.HazardCandidate = {
        0, 4, 811, "shared_hazard_movement:generic_hazard_exit:12:3",
        "shared_hazard_movement", "attempted", "hazard_exit",
    };
    evidence.HazardReceipt = {
        811, 0,
        "shared_hazard_movement:generic_hazard_exit:12:3", 0x2b,
        evidence.CheckpointScope, 0, true, true, true,
    };
    evidence.HazardDecisionTimestampMs = 800;
    evidence.HazardProgressObservedAtMs = 900;
    evidence.HazardProgressObserved = true;
    evidence.HazardPreemptedRange = true;
    evidence.HazardPreemptionSameResolution = true;
    evidence.HazardPreemptionBeforeRange = true;
    evidence.RangeCandidate = {
        0, 4, 812, "world.profile_combat_range", "db_class_spec_profile",
        "attempted", "profile_combat_min_range_reconciled",
    };
    evidence.RangeReceipt = {
        812, 0, "world.profile_combat_range", 0x1a,
        evidence.CheckpointScope, 39, true, true, true,
    };
    evidence.RangeDecisionTimestampMs = 1000;
    evidence.RangeProgressObservedAtMs = 1200;
    evidence.RangeProgressObserved = true;
    evidence.CastCandidate = {
        1, 4, 0, "world.profile_combat", "db_class_spec_profile",
        "attempted", "profile_cast_submitted",
    };
    evidence.CastScope = evidence.CheckpointScope;
    evidence.CastSpellId = 12345;
    evidence.CastTargetGuid = 39;
    evidence.CastRetryObserved = true;
    evidence.CastRecordedAtMs = 1300;
    evidence.CastBeforeProgressObserved = false;
    return evidence;
}

void AssertRejected(TransitionEvidence evidence)
{
    assert(!IsCompletedTransition(evidence));
}

int main()
{
    ObjectGuid const typedTarget(
        HighGuid::Unit, uint32(41570), uint32(39));
    assert(!typedTarget.IsEmpty());
    assert(typedTarget.GetRawValue() != uint64(39));
    assert(typedTarget.GetCounter() == uint32(39));

    TargetDescriptor const expectedTarget{39, 250051, 41570, 669};
    LiveTargetObservation observedTarget{
        typedTarget.GetCounter(), 250051, typedTarget.GetEntry(),
        669, 123, 669, 123, true,
    };
    assert(TargetIdentityFailure(expectedTarget, observedTarget) == nullptr);
    auto AssertTargetRejected = [&](LiveTargetObservation observed,
                                    char const* reason)
    {
        assert(std::string(TargetIdentityFailure(expectedTarget, observed))
            == reason);
    };
    LiveTargetObservation wrongCounter = observedTarget;
    wrongCounter.RuntimeTargetGuid = 40;
    AssertTargetRejected(wrongCounter,
        "profile_combat_range_checkpoint_runtime_target_guid_drift");
    LiveTargetObservation wrongSpawn = observedTarget;
    wrongSpawn.TargetSpawnId = 250052;
    AssertTargetRejected(wrongSpawn,
        "profile_combat_range_checkpoint_target_spawn_id_drift");
    LiveTargetObservation wrongEntry = observedTarget;
    wrongEntry.TargetEntry = 41571;
    AssertTargetRejected(wrongEntry,
        "profile_combat_range_checkpoint_target_entry_drift");
    LiveTargetObservation wrongMap = observedTarget;
    wrongMap.TargetMapId = 670;
    AssertTargetRejected(wrongMap,
        "profile_combat_range_checkpoint_target_map_id_drift");
    LiveTargetObservation zeroInstance = observedTarget;
    zeroInstance.TargetInstanceId = 0;
    zeroInstance.ActorInstanceId = 0;
    AssertTargetRejected(zeroInstance,
        "profile_combat_range_checkpoint_target_instance_invalid");
    LiveTargetObservation wrongActor = observedTarget;
    wrongActor.ActorInstanceId = 124;
    AssertTargetRejected(wrongActor,
        "profile_combat_range_checkpoint_actor_target_scope_mismatch");
    LiveTargetObservation unavailable = observedTarget;
    unavailable.TargetAvailable = false;
    AssertTargetRejected(unavailable,
        "profile_combat_range_checkpoint_target_unavailable");

    TransitionEvidence positive = ValidTransition();
    assert(IsCompletedTransition(positive));

    TransitionEvidence wrongSource = positive;
    wrongSource.HazardCandidate.Source = "observed_hazard_producer";
    AssertRejected(wrongSource);

    TransitionEvidence noPreemption = positive;
    noPreemption.HazardPreemptionSameResolution = false;
    AssertRejected(noPreemption);

    TransitionEvidence reordered = positive;
    reordered.HazardProgressObservedAtMs = 700;
    AssertRejected(reordered);

    TransitionEvidence staleTarget = positive;
    staleTarget.RangeReceipt.DiagnosticTargetGuid = typedTarget.GetRawValue();
    AssertRejected(staleTarget);

    TransitionEvidence staleReceipt = positive;
    staleReceipt.RangeReceipt.Id = 813;
    AssertRejected(staleReceipt);

    TransitionEvidence staleScope = positive;
    staleScope.RangeReceipt.ReceiptScope.AttemptId = 8;
    AssertRejected(staleScope);

    TransitionEvidence staleActor = positive;
    staleActor.RangeReceipt.ReceiptScope.ActorGuid = 30011;
    AssertRejected(staleActor);

    TransitionEvidence staleWipe = positive;
    staleWipe.RangeReceipt.ReceiptScope.WipeGeneration = 1;
    AssertRejected(staleWipe);

    TransitionEvidence staleRoute = positive;
    staleRoute.RangeReceipt.ReceiptScope.RouteGeneration = 2;
    AssertRejected(staleRoute);

    TransitionEvidence staleMap = positive;
    staleMap.RangeReceipt.ReceiptScope.MapId = 670;
    AssertRejected(staleMap);

    TransitionEvidence staleInstance = positive;
    staleInstance.RangeReceipt.ReceiptScope.InstanceId = 124;
    AssertRejected(staleInstance);

    TransitionEvidence staleReceiptGeneration = positive;
    staleReceiptGeneration.RangeReceipt.ReceiptScope.CheckpointGeneration = 5;
    AssertRejected(staleReceiptGeneration);

    TransitionEvidence staleGeneration = positive;
    staleGeneration.RangeCandidate.CheckpointGeneration = 5;
    AssertRejected(staleGeneration);

    TransitionEvidence noProgress = positive;
    noProgress.RangeProgressObserved = false;
    AssertRejected(noProgress);

    TransitionEvidence earlyCast = positive;
    earlyCast.CastRecordedAtMs = 1200;
    AssertRejected(earlyCast);

    TransitionEvidence wrongCastTarget = positive;
    wrongCastTarget.CastTargetGuid = typedTarget.GetRawValue();
    AssertRejected(wrongCastTarget);

    TransitionEvidence castBeforeProgress = positive;
    castBeforeProgress.CastBeforeProgressObserved = true;
    AssertRejected(castBeforeProgress);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++", "-std=c++17", "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            str(source), "-o", str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_source_has_no_replacement_range_candidate() -> None:
    fallback = FALLBACK.read_text(encoding="utf-8")
    assert "BotActionArbitration::Candidate combatRange" not in fallback
    assert "BotProfileCombatRangeCandidate::Build" in fallback
    assert "magmawSupportTarget" not in fallback


def test_support_range_uses_production_adapter_kernel_and_mover_entry(
    tmp_path: Path,
) -> None:
    native_source = MOVER.read_text(encoding="utf-8")
    signature = "bool BotWorldPopulationMgr::MoveBotToProfileRange("
    function = native_source.split(signature, 1)[1]
    # Keep the production entry predicate and replace only downstream terrain
    # and native movement with a spy. The candidate and arbiter remain real.
    entry_guard = function[function.index("{") + 1:
                           function.index("    auto patrolCombatPointSafe")]
    source = tmp_path / "support_range_production_fixture.cpp"
    binary = tmp_path / "support_range_production_fixture"
    source.write_text(
        r'''
#include "Bots/BotProfileCombatRangeCandidate.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawLaneTransition.h"

#include <cassert>

struct Actor
{
    ObjectGuid Guid;
    float DistanceToTarget = 0.0f;
    bool LineOfSight = true;

    ObjectGuid GetGUID() const { return Guid; }
    float GetExactDist(Actor const*) const { return DistanceToTarget; }
    bool IsWithinLOSInMap(Actor const*) const { return LineOfSight; }
};

struct State
{
    BotEncounter::MagmawParasiteCombatContract MagmawParasiteCombat;
};

int nativeMovementAttempts = 0;

bool ProductionMoveEntry(State& state, Actor* bot, Actor* reference,
    ResolvedCombatAction const* action, bool forceRangedReposition)
{
''' + entry_guard + r'''
    static_cast<void>(state);
    ++nativeMovementAttempts;
    return true;
}

BotProfileCombatRangeCandidate::Decision SupportDecision(
    State& state, Actor& bot, Actor& target,
    ResolvedCombatAction const* action, bool forceRangedReposition)
{
    BotProfileCombatRangeCandidate::Decision decision;
    decision.TargetPresent = true;
    decision.TargetInWorld = true;
    decision.TargetAlive = true;
    decision.TargetAttackable = true;
    decision.SameMap = true;
    decision.SameInstance = true;
    decision.Distance = bot.DistanceToTarget;
    decision.MinRange = action ? action->MinRange : 0.0f;
    decision.MaxRange = action ? action->MaxRange : 0.0f;
    decision.NoLineOfSight = !bot.LineOfSight;
    decision.Move = [&state, &bot, &target, action, forceRangedReposition]()
    {
        return ProductionMoveEntry(state, &bot, &target, action,
            forceRangedReposition);
    };
    return decision;
}

BotActionArbitration::Resolution Resolve(
    BotProfileCombatRangeCandidate::Decision decision)
{
    BotActionArbitration::Kernel kernel;
    kernel.Begin(1000);
    BotProfileCombatRangeCandidate::Request request;
    request.UtilityScore = 0.9f;
    request.Observe = [decision = std::move(decision)]() mutable
    {
        return decision;
    };
    assert(kernel.Submit(BotProfileCombatRangeCandidate::Build(
        std::move(request))));
    kernel.Resolve();
    return kernel.LastResolution();
}

void AssertNoSupportMovement(
    BotProfileCombatRangeCandidate::Decision decision, char const* reason)
{
    nativeMovementAttempts = 0;
    BotActionArbitration::Resolution const resolution = Resolve(
        std::move(decision));
    assert(nativeMovementAttempts == 0);
    assert(!resolution.AnyCommitted);
    assert(resolution.Trace.size() == 1);
    assert(resolution.Trace[0].Reason == reason);
}

int main()
{
    Actor support{ObjectGuid(HighGuid::Player, uint32(30010))};
    Actor parasite{ObjectGuid(HighGuid::Unit, uint32(42321), uint32(235))};
    State state;
    state.MagmawParasiteCombat.Active = true;
    state.MagmawParasiteCombat.ActorGuid = support.Guid;
    state.MagmawParasiteCombat.SupportTargetGuid = parasite.Guid;
    ResolvedCombatAction action;
    action.MinRange = 8.0f;
    action.MaxRange = 40.0f;

    // Historical capture 268: the exact support target is inside the native
    // minimum range, so the real candidate may commit one retreat attempt.
    support.DistanceToTarget = 4.0f;
    support.LineOfSight = true;
    nativeMovementAttempts = 0;
    BotActionArbitration::Resolution const positive = Resolve(
        SupportDecision(state, support, parasite, &action, false));
    assert(nativeMovementAttempts == 1);
    assert(positive.AnyCommitted);
    assert(positive.ClaimedResources
        == BotActionArbitration::Uses(BotActionArbitration::Resource::Movement));
    assert(positive.Trace[0].Reason
        == "profile_combat_min_range_reconciled");

    // Legal-band, remote/max-range, LOS-only, forced, and missing-action
    // cases produce no support chase before downstream geometry.
    support.DistanceToTarget = 8.0f;
    AssertNoSupportMovement(
        SupportDecision(state, support, parasite, &action, false),
        "profile_min_range_satisfied");
    support.DistanceToTarget = 41.0f;
    AssertNoSupportMovement(
        SupportDecision(state, support, parasite, &action, false),
        "profile_min_range_satisfied");
    support.LineOfSight = false;
    // Legal-band with no LOS is a distinct LOS-only case: the minimum-range
    // retreat guard must reject it before the native mover is considered.
    support.DistanceToTarget = 8.0f;
    AssertNoSupportMovement(
        SupportDecision(state, support, parasite, &action, false),
        "profile_min_range_satisfied");
    // Preserve the combined under-minimum plus no-LOS rejection from the
    // original trace-backed regression.
    support.DistanceToTarget = 4.0f;
    AssertNoSupportMovement(
        SupportDecision(state, support, parasite, &action, false),
        "profile_min_range_path_rejected");
    support.LineOfSight = true;
    AssertNoSupportMovement(
        SupportDecision(state, support, parasite, &action, true),
        "profile_min_range_path_rejected");
    AssertNoSupportMovement(
        SupportDecision(state, support, parasite, nullptr, false),
        "profile_min_range_satisfied");

    // A higher-priority hazard owns Movement in the real kernel; the support
    // range callback remains uncalled and therefore cannot preempt it.
    support.DistanceToTarget = 4.0f;
    BotActionArbitration::Kernel conflict;
    conflict.Begin(1000);
    BotProfileCombatRangeCandidate::Request rangeRequest;
    rangeRequest.UtilityScore = 0.9f;
    rangeRequest.Observe = [&state, &support, &parasite, &action]()
    {
        return SupportDecision(state, support, parasite, &action, false);
    };
    assert(conflict.Submit(BotProfileCombatRangeCandidate::Build(
        std::move(rangeRequest))));
    bool hazard = false;
    BotActionArbitration::Candidate hazardCandidate;
    hazardCandidate.Key = "magmaw.hazard.movement";
    hazardCandidate.Source = "adaptive_magmaw_hazard";
    hazardCandidate.ActionPriority = BotActionArbitration::Priority::Survival;
    hazardCandidate.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    hazardCandidate.Attempt = [&hazard]()
    {
        hazard = true;
        return BotActionArbitration::Outcome::Started("hazard_started");
    };
    assert(conflict.Submit(std::move(hazardCandidate)));
    BotActionArbitration::Resolution const& conflictResolution =
        conflict.Resolve();
    assert(hazard);
    assert(nativeMovementAttempts == 0);
    assert(conflictResolution.CommittedCandidates.size() == 1);
    assert(conflictResolution.Trace.size() == 2);
    assert(conflictResolution.Trace[1].Key
        == BotProfileCombatRangeCandidate::Key);
    assert(conflictResolution.Trace[1].Status == "resource_conflict");
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            str(source), "-o", str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
