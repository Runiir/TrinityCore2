#ifndef TRINITY_BOT_MAGMAW_TARGET_RETURN_OBSERVATION_H
#define TRINITY_BOT_MAGMAW_TARGET_RETURN_OBSERVATION_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"

#include <algorithm>
#include <sstream>
#include <string>
#include <string_view>

namespace BotEncounter::MagmawTargetReturnObservation
{
enum class ActorBucket : uint8
{
    Absent,
    Hostiles,
    Summons,
    Interactables
};

enum class BindResult : uint8
{
    NotEvaluated,
    PlanTargetEmpty,
    NativeMissing,
    NativeDead,
    NativeInvalid,
    Bound,
    InvalidPayload
};

struct Actor
{
    ActorBucket Bucket = ActorBucket::Absent;
    ObjectGuid Guid;
    bool SnapshotPresent = false;
    bool Alive = false;
    bool Selectable = false;
    bool Attackable = false;
    bool NativePresent = false;
    bool NativeAlive = false;
    bool NativeValidAttackTarget = false;
};

struct Record
{
    bool Evaluated = false;
    uint64 ObservedAtMs = 0;
    uint64 AttemptId = 0;
    uint64 RouteGeneration = 0;
    uint64 SnapshotRevision = 0;
    std::string RouteNodeId;
    Actor Body;
    Actor Head;
    MagmawTruth HeadFact = MagmawTruth::Unknown;
    bool OwnsNode = false;
    ObjectGuid ProposedTargetGuid;
    bool ProposedNativePresent = false;
    bool ProposedNativeAlive = false;
    bool ProposedNativeValidAttackTarget = false;
    ObjectGuid BeforeStateTargetGuid;
    ObjectGuid BeforeContextTargetGuid;
    ObjectGuid DesiredMeleeTargetGuid;
    ObjectGuid AfterStateTargetGuid;
    ObjectGuid AfterContextTargetGuid;
    BindResult Result = BindResult::NotEvaluated;
};

inline char const* Name(ActorBucket bucket)
{
    switch (bucket)
    {
        case ActorBucket::Hostiles: return "hostiles";
        case ActorBucket::Summons: return "summons";
        case ActorBucket::Interactables: return "interactables";
        default: return "absent";
    }
}

inline char const* Name(BindResult result)
{
    switch (result)
    {
        case BindResult::PlanTargetEmpty: return "plan_target_empty";
        case BindResult::NativeMissing: return "native_missing";
        case BindResult::NativeDead: return "native_dead";
        case BindResult::NativeInvalid: return "native_invalid";
        case BindResult::Bound: return "bound";
        case BindResult::InvalidPayload: return "invalid_payload";
        default: return "not_evaluated";
    }
}

inline char const* Name(MagmawTruth truth)
{
    switch (truth)
    {
        case MagmawTruth::True: return "true";
        case MagmawTruth::False: return "false";
        default: return "unknown";
    }
}

inline Actor ObserveActor(Blackboard const& board, uint32 entry)
{
    Actor observed;
    auto inspect = [entry, &observed](std::vector<ActorSnapshot> const& actors,
        ActorBucket bucket)
    {
        auto itr = std::find_if(actors.begin(), actors.end(),
            [entry](ActorSnapshot const& actor) { return actor.Entry == entry; });
        if (itr == actors.end())
            return false;
        observed.Bucket = bucket;
        observed.Guid = itr->Guid;
        observed.SnapshotPresent = true;
        observed.Alive = itr->Alive;
        observed.Selectable = itr->Selectable;
        observed.Attackable = itr->Attackable;
        return true;
    };
    if (inspect(board.Hostiles, ActorBucket::Hostiles)
        || inspect(board.Summons, ActorBucket::Summons))
        return observed;
    inspect(board.Interactables, ActorBucket::Interactables);
    return observed;
}

inline Record Begin(Blackboard const& board, MagmawFacts const* facts,
    uint64 attemptId, uint64 routeGeneration, bool ownsNode,
    ObjectGuid proposedTargetGuid, ObjectGuid beforeStateTargetGuid,
    ObjectGuid beforeContextTargetGuid, ObjectGuid desiredMeleeTargetGuid)
{
    Record record;
    record.Evaluated = true;
    record.ObservedAtMs = board.ObservedAtMs;
    record.AttemptId = attemptId;
    record.RouteGeneration = routeGeneration;
    record.SnapshotRevision = board.Revision;
    record.RouteNodeId = board.Route.NodeId;
    record.Body = ObserveActor(board, 41570);
    record.Head = ObserveActor(board, 42347);
    record.HeadFact = facts ? facts->HeadExposed : MagmawTruth::Unknown;
    record.OwnsNode = ownsNode;
    record.ProposedTargetGuid = proposedTargetGuid;
    record.BeforeStateTargetGuid = beforeStateTargetGuid;
    record.BeforeContextTargetGuid = beforeContextTargetGuid;
    record.DesiredMeleeTargetGuid = desiredMeleeTargetGuid;
    record.Result = proposedTargetGuid.IsEmpty()
        ? BindResult::PlanTargetEmpty : BindResult::NotEvaluated;
    return record;
}

inline void ObserveNative(Actor& actor, bool present, bool alive,
    bool validAttackTarget)
{
    actor.NativePresent = present;
    actor.NativeAlive = alive;
    actor.NativeValidAttackTarget = validAttackTarget;
}

inline void ObserveProposedNative(Record& record, bool present, bool alive,
    bool validAttackTarget)
{
    record.ProposedNativePresent = present;
    record.ProposedNativeAlive = alive;
    record.ProposedNativeValidAttackTarget = validAttackTarget;
}

inline void Finish(Record& record, BindResult result,
    ObjectGuid afterStateTargetGuid, ObjectGuid afterContextTargetGuid)
{
    record.Result = result;
    record.AfterStateTargetGuid = afterStateTargetGuid;
    record.AfterContextTargetGuid = afterContextTargetGuid;
}

inline void AppendActorJson(std::ostringstream& json, Actor const& actor)
{
    json << "{\"bucket\":\"" << Name(actor.Bucket)
         << "\",\"guid\":" << actor.Guid.GetCounter()
         << ",\"snapshot_present\":" << (actor.SnapshotPresent ? "true" : "false")
         << ",\"alive\":" << (actor.Alive ? "true" : "false")
         << ",\"selectable\":" << (actor.Selectable ? "true" : "false")
         << ",\"attackable\":" << (actor.Attackable ? "true" : "false")
         << ",\"native_present\":" << (actor.NativePresent ? "true" : "false")
         << ",\"native_alive\":" << (actor.NativeAlive ? "true" : "false")
         << ",\"native_valid_attack_target\":"
         << (actor.NativeValidAttackTarget ? "true" : "false") << "}";
}

inline std::string BuildJson(Record const& record, uint64 currentAttemptId,
    uint64 currentRouteGeneration, uint64 currentSnapshotRevision,
    std::string_view currentRouteNodeId)
{
    bool const current = record.Evaluated
        && record.AttemptId == currentAttemptId
        && record.RouteGeneration == currentRouteGeneration
        && record.SnapshotRevision == currentSnapshotRevision
        && record.RouteNodeId == currentRouteNodeId;
    bool valid = record.Evaluated;
    switch (record.Result)
    {
        case BindResult::PlanTargetEmpty:
            valid = valid && record.ProposedTargetGuid.IsEmpty();
            break;
        case BindResult::NativeMissing:
            valid = valid && !record.ProposedTargetGuid.IsEmpty()
                && !record.ProposedNativePresent;
            break;
        case BindResult::NativeDead:
            valid = valid && record.ProposedNativePresent
                && !record.ProposedNativeAlive;
            break;
        case BindResult::NativeInvalid:
            valid = valid && record.ProposedNativePresent
                && record.ProposedNativeAlive
                && !record.ProposedNativeValidAttackTarget;
            break;
        case BindResult::Bound:
            valid = valid && record.OwnsNode
                && !record.ProposedTargetGuid.IsEmpty()
                && record.ProposedNativePresent && record.ProposedNativeAlive
                && record.ProposedNativeValidAttackTarget
                && record.AfterStateTargetGuid == record.ProposedTargetGuid
                && record.AfterContextTargetGuid == record.ProposedTargetGuid;
            break;
        default:
            valid = false;
            break;
    }
    BindResult const serializedResult = !record.Evaluated
        ? BindResult::NotEvaluated
        : valid ? record.Result : BindResult::InvalidPayload;
    std::ostringstream json;
    json << "{\"evaluated\":" << (record.Evaluated ? "true" : "false")
         << ",\"current\":" << (current ? "true" : "false")
         << ",\"valid\":" << (valid ? "true" : "false")
         << ",\"observed_at_ms\":" << record.ObservedAtMs
         << ",\"attempt_id\":" << record.AttemptId
         << ",\"route_generation\":" << record.RouteGeneration
         << ",\"snapshot_revision\":" << record.SnapshotRevision
         << ",\"route_node_id\":\"" << record.RouteNodeId << "\""
         << ",\"body\":";
    AppendActorJson(json, record.Body);
    json << ",\"head\":";
    AppendActorJson(json, record.Head);
    json << ",\"head_fact\":\"" << Name(record.HeadFact)
         << "\",\"owns_node\":" << (record.OwnsNode ? "true" : "false")
         << ",\"proposed_target_guid\":" << record.ProposedTargetGuid.GetCounter()
         << ",\"proposed_native_present\":" << (record.ProposedNativePresent ? "true" : "false")
         << ",\"proposed_native_alive\":" << (record.ProposedNativeAlive ? "true" : "false")
         << ",\"proposed_native_valid_attack_target\":" << (record.ProposedNativeValidAttackTarget ? "true" : "false")
         << ",\"before_state_target_guid\":" << record.BeforeStateTargetGuid.GetCounter()
         << ",\"before_context_target_guid\":" << record.BeforeContextTargetGuid.GetCounter()
         << ",\"desired_melee_target_guid\":" << record.DesiredMeleeTargetGuid.GetCounter()
         << ",\"after_state_target_guid\":" << record.AfterStateTargetGuid.GetCounter()
         << ",\"after_context_target_guid\":" << record.AfterContextTargetGuid.GetCounter()
         << ",\"bind_result\":\"" << Name(serializedResult) << "\"}";
    return json.str();
}
}

#endif
