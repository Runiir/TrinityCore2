#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_DECISION_TRACE_COALESCING_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_DECISION_TRACE_COALESCING_H

#include "Bots/BotWorldPopulationMgrBotState.h"

namespace BotWorldTrace
{
using DecisionTraceEntry =
    BotWorldPopulationMgrBotState::WorldBotState::DecisionTraceEntry;

inline bool SameTargetState(DecisionTraceEntry::TargetObservation const& left,
    DecisionTraceEntry::TargetObservation const& right)
{
    return left.Guid == right.Guid && left.GuidRaw == right.GuidRaw
        && left.Entry == right.Entry
        && left.NativePresent == right.NativePresent
        && left.Alive == right.Alive
        && left.ValidAttackTarget == right.ValidAttackTarget
        && left.DistanceAvailable == right.DistanceAvailable
        && left.DistanceWithin45Yd == right.DistanceWithin45Yd
        && left.LineOfSightAvailable == right.LineOfSightAvailable
        && left.LineOfSight == right.LineOfSight;
}

inline bool SameNativeActor(
    DecisionTraceEntry::NativeActorObservation const& left,
    DecisionTraceEntry::NativeActorObservation const& right)
{
    bool const positionMatches = !left.PositionAvailable
        || (left.Moving && right.Moving
            && left.SplineInitialized && right.SplineInitialized
            && left.SplineId == right.SplineId)
        || (left.X == right.X && left.Y == right.Y && left.Z == right.Z);
    return left.NativePresent == right.NativePresent
        && left.InWorld == right.InWorld && left.Alive == right.Alive
        && left.PositionAvailable == right.PositionAvailable
        && positionMatches
        && left.Moving == right.Moving
        && left.SplineInitialized == right.SplineInitialized
        && left.SplineFinalized == right.SplineFinalized
        && left.SplineId == right.SplineId
        && left.CurrentGenericSpellId == right.CurrentGenericSpellId;
}

inline bool SameTargetReturn(
    std::optional<BotEncounter::MagmawTargetReturnObservation::Record> const& left,
    std::optional<BotEncounter::MagmawTargetReturnObservation::Record> const& right)
{
    auto sameActor = [](auto const& a, auto const& b)
    {
        return a.Bucket == b.Bucket && a.Guid == b.Guid
            && a.SnapshotPresent == b.SnapshotPresent
            && a.Alive == b.Alive && a.Selectable == b.Selectable
            && a.Attackable == b.Attackable
            && a.NativePresent == b.NativePresent
            && a.NativeAlive == b.NativeAlive
            && a.NativeValidAttackTarget == b.NativeValidAttackTarget;
    };
    if (!left || !right)
        return !left && !right;
    return left->ObservedAtMs == right->ObservedAtMs
        && left->AttemptId == right->AttemptId
        && left->RouteGeneration == right->RouteGeneration
        && left->SnapshotRevision == right->SnapshotRevision
        && left->RouteNodeId == right->RouteNodeId
        && sameActor(left->Body, right->Body)
        && sameActor(left->Head, right->Head)
        && left->HeadFact == right->HeadFact
        && left->OwnsNode == right->OwnsNode
        && left->ProposedTargetGuid == right->ProposedTargetGuid
        && left->ProposedNativePresent == right->ProposedNativePresent
        && left->ProposedNativeAlive == right->ProposedNativeAlive
        && left->ProposedNativeValidAttackTarget
            == right->ProposedNativeValidAttackTarget
        && left->BeforeStateTargetGuid == right->BeforeStateTargetGuid
        && left->BeforeContextTargetGuid == right->BeforeContextTargetGuid
        && left->DesiredMeleeTargetGuid == right->DesiredMeleeTargetGuid
        && left->AfterStateTargetGuid == right->AfterStateTargetGuid
        && left->AfterContextTargetGuid == right->AfterContextTargetGuid
        && left->Result == right->Result;
}

inline bool CanCoalesceDecisionTrace(DecisionTraceEntry const& previous,
    DecisionTraceEntry const& current, std::uint64_t exportedCursor,
    bool movementPlannerPending)
{
    return !movementPlannerPending && previous.Sequence > exportedCursor
        && current.TimestampMs >= previous.TimestampMs
        && current.TimestampMs - previous.TimestampMs < 5000
        && previous.ServerEpoch == current.ServerEpoch
        && previous.AttemptId == current.AttemptId
        && previous.WipeGeneration == current.WipeGeneration
        && previous.CohortId == current.CohortId
        && previous.ActorGuidRaw == current.ActorGuidRaw
        && previous.ActorMapId == current.ActorMapId
        && previous.ActorInstanceId == current.ActorInstanceId
        && previous.ActorRole == current.ActorRole
        && previous.Situation == current.Situation
        && previous.Action == current.Action
        && previous.TargetGuid == current.TargetGuid
        && previous.Result == current.Result
        && previous.ReasonCode == current.ReasonCode
        && previous.RouteNodeId == current.RouteNodeId
        && previous.RouteGeneration == current.RouteGeneration
        && previous.QuestId == current.QuestId
        && previous.DestinationMapId == current.DestinationMapId
        && previous.DestinationX == current.DestinationX
        && previous.DestinationY == current.DestinationY
        && previous.DestinationZ == current.DestinationZ
        && previous.BlockedEpisodeId == current.BlockedEpisodeId
        && previous.BlockedFirstReason == current.BlockedFirstReason
        && previous.BlockedCurrentReason == current.BlockedCurrentReason
        && previous.BlockedResolution == current.BlockedResolution
        && previous.BlockedResolvedBy == current.BlockedResolvedBy
        && previous.LoopGuardrailAction == current.LoopGuardrailAction
        && previous.LoopGuardrailReason == current.LoopGuardrailReason
        && previous.RecoveryMode == current.RecoveryMode
        && previous.RecoveryResult == current.RecoveryResult
        && previous.ActionCategory == current.ActionCategory
        && previous.RoleGoal == current.RoleGoal
        && previous.RecommendedBalanceMode == current.RecommendedBalanceMode
        && previous.SaturationReason == current.SaturationReason
        && previous.MechanicFamily == current.MechanicFamily
        && previous.EncounterRoleResponsibility
            == current.EncounterRoleResponsibility
        && previous.NextExpectedAction == current.NextExpectedAction
        && SameTargetState(previous.EventTarget, current.EventTarget)
        && SameTargetState(previous.NativeSelectedTarget,
            current.NativeSelectedTarget)
        && SameTargetState(previous.StateBoundTarget,
            current.StateBoundTarget)
        && SameNativeActor(previous.NativeActor, current.NativeActor)
        && SameTargetReturn(previous.TargetReturn, current.TargetReturn)
        && previous.TargetReturnCurrentAtRecord
            == current.TargetReturnCurrentAtRecord
        && previous.TargetReturnAgeAvailable == current.TargetReturnAgeAvailable;
}
}

#endif
