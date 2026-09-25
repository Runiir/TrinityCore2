#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_LOGIC_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_LOGIC_H

// Pure decision logic for native route contracts: owner election, bounded
// attempts, observed completion evaluation and transport boarding phases.
// The server adapter supplies observations; nothing here touches game state.

#include "Bots/BotValidationRouteNativeContract.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <string>
#include <tuple>
#include <vector>

namespace BotValidationRouteNative
{
// ---------------------------------------------------------------------------
// Owner election
// ---------------------------------------------------------------------------
struct MemberView
{
    std::uint64_t Guid = 0;
    bool Alive = false;
    std::string Role;
    // 1-based frozen roster slot; 0 when the member has no roster slot.
    std::uint32_t RosterSlot = 0;
};

struct OwnerElection
{
    std::uint64_t Owner = 0;
    bool UsedBackup = false;
    std::string Reason;
};

inline OwnerElection ElectOwner(InteractionContract const& contract,
    std::vector<MemberView> const& members)
{
    auto lowestAlive = [&members](auto accept) -> std::uint64_t
    {
        std::uint64_t best = 0;
        for (MemberView const& member : members)
            if (member.Alive && accept(member) && (!best || member.Guid < best))
                best = member.Guid;
        return best;
    };
    auto slotOwner = [&members](std::uint32_t slot) -> std::uint64_t
    {
        if (!slot)
            return 0;
        for (MemberView const& member : members)
            if (member.Alive && member.RosterSlot == slot)
                return member.Guid;
        return 0;
    };

    OwnerElection election;
    if (contract.LegacyOwner())
    {
        election.Owner = lowestAlive([](MemberView const&) { return true; });
        election.Reason = election.Owner
            ? "lowest_guid_default" : "interaction_owner_unavailable";
        return election;
    }
    if (contract.OwnerRosterSlot)
    {
        election.Owner = slotOwner(contract.OwnerRosterSlot);
        election.Reason = "owner_roster_slot";
    }
    else
    {
        election.Owner = lowestAlive([&contract](MemberView const& member)
            { return member.Role == contract.OwnerRole; });
        election.Reason = "owner_role";
    }
    if (!election.Owner)
    {
        election.Owner = slotOwner(contract.BackupRosterSlot);
        election.UsedBackup = election.Owner != 0;
        election.Reason = election.Owner
            ? "backup_roster_slot" : "interaction_owner_unavailable";
    }
    return election;
}

// ---------------------------------------------------------------------------
// Bounded attempts
// ---------------------------------------------------------------------------
struct AttemptState
{
    std::uint64_t LastSubmitAtMs = 0;
    std::uint32_t Attempts = 0;
};

enum class AttemptGate : std::uint8_t { Allowed, RetryWait, AttemptsExhausted, TimedOut };

inline char const* AttemptGateName(AttemptGate gate)
{
    switch (gate)
    {
        case AttemptGate::Allowed: return "allowed";
        case AttemptGate::RetryWait: return "native_interaction_retry_wait";
        case AttemptGate::AttemptsExhausted: return "native_interaction_attempts_exhausted";
        case AttemptGate::TimedOut: return "native_interaction_timeout";
    }
    return "unknown";
}

inline AttemptGate EvaluateAttemptGate(InteractionContract const& contract,
    AttemptState const& state, std::uint64_t startedAtMs, std::uint64_t nowMs)
{
    if (contract.TimeoutMs && nowMs >= startedAtMs + contract.TimeoutMs)
        return AttemptGate::TimedOut;
    if (contract.MaxAttempts && state.Attempts >= contract.MaxAttempts)
        return AttemptGate::AttemptsExhausted;
    if (contract.RetryIntervalMs && state.Attempts
        && nowMs < state.LastSubmitAtMs + contract.RetryIntervalMs)
        return AttemptGate::RetryWait;
    return AttemptGate::Allowed;
}

inline void RecordAttempt(AttemptState& state, std::uint64_t nowMs)
{
    ++state.Attempts;
    state.LastSubmitAtMs = nowMs;
}

// ---------------------------------------------------------------------------
// Interaction step
// ---------------------------------------------------------------------------
enum class InteractionStep : std::uint8_t
{
    Hold,
    Approach,
    Use,
    GossipOpen,
    GossipSelect,
    SpellClick,
    VehicleEnter,
    AreaTrigger
};

struct InteractionObservation
{
    bool TargetResolved = false;
    bool TargetAmbiguous = false;
    bool InRange = false;
    // Gossip menu currently open on the owner, bound to the resolved target.
    bool GossipBoundToTarget = false;
    std::uint32_t CurrentGossipMenu = 0;
};

struct InteractionDecision
{
    InteractionStep Step = InteractionStep::Hold;
    // True when the step starts a new native attempt (counted and gated).
    bool CountsAsAttempt = false;
    std::string Reason;
};

inline InteractionDecision DecideInteraction(InteractionContract const& contract,
    InteractionObservation const& observation, AttemptGate gate)
{
    if (gate == AttemptGate::TimedOut)
        return { InteractionStep::Hold, false, AttemptGateName(gate) };
    if (contract.Action != InteractionAction::AreaTrigger)
    {
        if (observation.TargetAmbiguous)
            return { InteractionStep::Hold, false, "native_interaction_target_ambiguous" };
        if (!observation.TargetResolved)
            return { InteractionStep::Hold, false, "native_interaction_target_missing" };
    }
    if (!observation.InRange)
        return { InteractionStep::Approach, false, "native_interaction_approach" };

    InteractionDecision commit;
    commit.CountsAsAttempt = true;
    switch (contract.Action)
    {
        case InteractionAction::GameObjectUse:
            commit.Step = InteractionStep::Use;
            break;
        case InteractionAction::SpellClick:
            commit.Step = InteractionStep::SpellClick;
            break;
        case InteractionAction::VehicleEnter:
            commit.Step = InteractionStep::VehicleEnter;
            break;
        case InteractionAction::AreaTrigger:
            commit.Step = InteractionStep::AreaTrigger;
            break;
        case InteractionAction::GossipSelect:
        case InteractionAction::GossipSelectSequence:
        {
            bool const configuredMenu = observation.GossipBoundToTarget
                && std::find(contract.Menus.begin(), contract.Menus.end(),
                    observation.CurrentGossipMenu) != contract.Menus.end();
            // Continuing an open dialogue is part of the current attempt.
            if (configuredMenu)
                return { InteractionStep::GossipSelect, false, "native_gossip_select" };
            commit.Step = InteractionStep::GossipOpen;
            break;
        }
        case InteractionAction::None:
            return { InteractionStep::Hold, false, "native_interaction_action_unknown" };
    }
    if (gate != AttemptGate::Allowed)
        return { InteractionStep::Hold, false, AttemptGateName(gate) };
    commit.Reason = "native_interaction_commit";
    return commit;
}

// ---------------------------------------------------------------------------
// Completion evaluation
// ---------------------------------------------------------------------------
struct ActorFact
{
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    bool Alive = false;
    bool Spawned = false;
    bool Selectable = false;
    bool Interactable = false;
    bool ReactAggressive = false;
    bool InCombat = false;
    bool Flying = false;
    bool HasVictim = false;
    std::vector<std::uint32_t> AuraIds;
};

struct MemberFact
{
    std::uint64_t Guid = 0;
    bool Alive = false;
    bool Owner = false;
    bool OnTransport = false;
    std::uint32_t TransportEntry = 0;
    std::uint64_t TransportSpawnId = 0;
    std::uint32_t VehicleEntry = 0;
    std::int32_t Seat = -1;
};

struct TransportFact
{
    bool Present = false;
    bool Ambiguous = false;
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    std::uint32_t GoState = 0;
    // The native arrival time for the requested stop frame has passed.
    bool ArrivedAtStop = false;
    float PositionX = 0.0f;
    float PositionY = 0.0f;
    float PositionZ = 0.0f;
    float Orientation = 0.0f;
};

// GOState values (SharedDefines.h): 25 + frame means "stop at frame".
constexpr std::uint32_t GoStateTransportStopped = 25;

class FactSource
{
public:
    virtual ~FactSource() = default;
    virtual std::vector<ActorFact> Creatures(std::uint32_t entry, std::uint64_t spawnId) const = 0;
    virtual std::vector<ActorFact> GameObjects(std::uint32_t entry, std::uint64_t spawnId) const = 0;
    virtual bool BossState(std::uint32_t index, std::uint32_t& state) const = 0;
    virtual std::vector<MemberFact> Members() const = 0;
    virtual TransportFact Transport(std::uint32_t entry, std::uint64_t spawnId) const = 0;
};

struct CompletionMemory
{
    std::vector<std::string> ObservedPresent;

    bool Seen(std::string const& key) const
    {
        return std::find(ObservedPresent.begin(), ObservedPresent.end(), key)
            != ObservedPresent.end();
    }

    void Remember(std::string const& key)
    {
        if (!Seen(key))
            ObservedPresent.push_back(key);
    }
};

struct Verdict
{
    bool Satisfied = false;
    std::string Reason;
};

inline bool TransportAtStop(TransportFact const& fact, std::int32_t frame)
{
    return fact.Present && !fact.Ambiguous && frame >= 0
        && fact.GoState == GoStateTransportStopped + std::uint32_t(frame)
        && fact.ArrivedAtStop;
}

inline bool TransportAtLevel(TransportFact const& fact, float levelZ, float tolerance)
{
    return fact.Present && !fact.Ambiguous
        && std::fabs(fact.PositionZ - levelZ) <= tolerance;
}

inline Verdict EvaluateCompletion(CompletionContract const& contract,
    FactSource const& facts, CompletionMemory& memory)
{
    auto verdict = [](bool satisfied, std::string reason)
    {
        return Verdict{ satisfied, std::move(reason) };
    };
    auto aliveCreatures = [&facts, &contract]()
    {
        std::vector<ActorFact> alive;
        for (ActorFact const& actor : facts.Creatures(contract.Entry, contract.SpawnId))
            if (actor.Alive)
                alive.push_back(actor);
        return alive;
    };
    auto members = [&facts, &contract](auto predicate) -> Verdict
    {
        std::vector<MemberFact> const all = facts.Members();
        std::uint32_t considered = 0, satisfied = 0;
        for (MemberFact const& member : all)
        {
            if (!member.Alive)
                continue;
            if (contract.Scope == MemberScope::Owner && !member.Owner)
                continue;
            ++considered;
            if (predicate(member))
                ++satisfied;
        }
        bool const ok = considered > 0 && (contract.Scope == MemberScope::Any
            ? satisfied > 0 : satisfied == considered);
        return { ok, ok ? "members_satisfied"
            : "members_pending:" + std::to_string(satisfied) + "/" + std::to_string(considered) };
    };

    switch (contract.Kind)
    {
        case CompletionKind::GameObjectSelectable:
        {
            for (ActorFact const& object : facts.GameObjects(contract.Entry, contract.SpawnId))
                if (object.Spawned && object.Selectable && object.Interactable)
                    return verdict(true, "gameobject_selectable");
            return verdict(false, "gameobject_not_selectable");
        }
        case CompletionKind::GameObjectDespawned:
        {
            std::string const key = "go:" + std::to_string(contract.Entry) + ":"
                + std::to_string(contract.SpawnId);
            bool spawned = false;
            for (ActorFact const& object : facts.GameObjects(contract.Entry, contract.SpawnId))
                spawned = spawned || object.Spawned;
            if (spawned)
            {
                memory.Remember(key);
                return verdict(false, "gameobject_still_spawned");
            }
            if (contract.RequireObservedPresent && !memory.Seen(key))
                return verdict(false, "gameobject_never_observed_spawned");
            return verdict(true, "gameobject_despawned");
        }
        case CompletionKind::BossSummoned:
        case CompletionKind::CreatureSummoned:
            return verdict(!aliveCreatures().empty(), "creature_present");
        case CompletionKind::AuraPresent:
        {
            for (ActorFact const& actor : aliveCreatures())
                if (std::find(actor.AuraIds.begin(), actor.AuraIds.end(), contract.SpellId)
                    != actor.AuraIds.end())
                    return verdict(true, "aura_present");
            return verdict(false, "aura_absent");
        }
        case CompletionKind::CreatureAggressiveWithVictim:
        {
            for (ActorFact const& actor : aliveCreatures())
                if (actor.ReactAggressive && actor.HasVictim)
                    return verdict(true, "creature_aggressive_with_victim");
            return verdict(false, "creature_not_aggressive");
        }
        case CompletionKind::CreatureGroundedAggressiveOrEngaged:
        {
            for (ActorFact const& actor : aliveCreatures())
                if (!actor.Flying
                    && (actor.ReactAggressive || actor.InCombat || actor.HasVictim))
                    return verdict(true, "creature_grounded_engaged");
            return verdict(false, "creature_not_grounded_engaged");
        }
        case CompletionKind::InstanceBossState:
        {
            std::uint32_t state = 0;
            if (!facts.BossState(std::uint32_t(contract.BossIndex), state))
                return verdict(false, "instance_script_unavailable");
            return verdict(state == contract.BossState,
                "boss_state_" + std::to_string(state));
        }
        case CompletionKind::OnTransport:
        {
            TransportFact const transport =
                facts.Transport(contract.TransportEntry, contract.TransportSpawnId);
            if (!transport.Present || transport.Ambiguous)
                return verdict(false, transport.Ambiguous ? "transport_ambiguous" : "transport_missing");
            return members([&transport](MemberFact const& member)
            {
                return member.OnTransport && member.TransportEntry == transport.Entry
                    && (!transport.SpawnId || member.TransportSpawnId == transport.SpawnId);
            });
        }
        case CompletionKind::VehicleSeated:
            return members([&contract](MemberFact const& member)
            {
                return member.VehicleEntry == contract.VehicleEntry
                    && (contract.Seat < 0 || member.Seat == contract.Seat);
            });
        case CompletionKind::TransportAtStop:
        {
            TransportFact const transport =
                facts.Transport(contract.TransportEntry, contract.TransportSpawnId);
            return verdict(TransportAtStop(transport, contract.StopFrame),
                "transport_state_" + std::to_string(transport.GoState));
        }
        case CompletionKind::AnyOf:
        case CompletionKind::AllOf:
        {
            bool const any = contract.Kind == CompletionKind::AnyOf;
            std::string reasons;
            bool result = !any;
            // Evaluate every child so despawn memory is kept current.
            for (CompletionContract const& child : contract.Children)
            {
                Verdict const childVerdict = EvaluateCompletion(child, facts, memory);
                reasons += (reasons.empty() ? "" : ",") + child.KindName + "="
                    + (childVerdict.Satisfied ? "1" : "0");
                result = any ? (result || childVerdict.Satisfied)
                    : (result && childVerdict.Satisfied);
            }
            return verdict(result, (any ? "any_of[" : "all_of[") + reasons + "]");
        }
        case CompletionKind::None:
            break;
    }
    return verdict(false, "completion_kind_unknown");
}

// ---------------------------------------------------------------------------
// Transport geometry and phases
// ---------------------------------------------------------------------------
struct LocalBox
{
    float MinX = 0.0f, MinY = 0.0f, MinZ = 0.0f;
    float MaxX = 0.0f, MaxY = 0.0f, MaxZ = 0.0f;
    bool Valid = false;
};

// Largest passenger offset the native movement handler accepts.
constexpr float MaxTransportOffset = 75.0f;

// World point to transport-local offset (rotation about Z by -orientation),
// matching TransportBase::CalculatePassengerOffset.
inline Point3 LocalOffset(float x, float y, float z, TransportFact const& transport)
{
    float const dx = x - transport.PositionX;
    float const dy = y - transport.PositionY;
    float const c = std::cos(transport.Orientation);
    float const s = std::sin(transport.Orientation);
    return { dx * c + dy * s, dy * c - dx * s, z - transport.PositionZ, true };
}

inline bool InsideFootprint(Point3 const& local, LocalBox const& box, float margin)
{
    if (!local.Valid || !box.Valid)
        return false;
    if (std::fabs(local.X) > MaxTransportOffset || std::fabs(local.Y) > MaxTransportOffset
        || std::fabs(local.Z) > MaxTransportOffset)
        return false;
    return local.X >= box.MinX - margin && local.X <= box.MaxX + margin
        && local.Y >= box.MinY - margin && local.Y <= box.MaxY + margin
        && local.Z >= box.MinZ - margin && local.Z <= box.MaxZ + margin;
}

inline bool TransportReadyToBoard(TransportContract const& contract, TransportFact const& fact)
{
    return contract.BoardStopFrame >= 0
        ? TransportAtStop(fact, contract.BoardStopFrame)
        : TransportAtLevel(fact, contract.BoardTransportZ, contract.LevelToleranceYards);
}

inline bool TransportAtExit(TransportContract const& contract, TransportFact const& fact)
{
    if (!contract.HasExit())
        return false;
    return contract.ExitStopFrame >= 0
        ? TransportAtStop(fact, contract.ExitStopFrame)
        : TransportAtLevel(fact, contract.ExitTransportZ, contract.LevelToleranceYards);
}

enum class TransportStep : std::uint8_t
{
    Hold,
    MoveToWait,
    MoveToBoard,
    Board,
    HoldAboard,
    MoveToDisembark,
    Leave,
    MoveToExit,
    Done,
    Blocked
};

inline char const* TransportStepName(TransportStep step)
{
    switch (step)
    {
        case TransportStep::Hold: return "hold";
        case TransportStep::MoveToWait: return "move_to_wait";
        case TransportStep::MoveToBoard: return "move_to_board";
        case TransportStep::Board: return "board";
        case TransportStep::HoldAboard: return "hold_aboard";
        case TransportStep::MoveToDisembark: return "move_to_disembark";
        case TransportStep::Leave: return "leave";
        case TransportStep::MoveToExit: return "move_to_exit";
        case TransportStep::Done: return "done";
        case TransportStep::Blocked: return "blocked";
    }
    return "unknown";
}

struct TransportMemberState
{
    bool Boarded = false;
    bool Left = false;
    std::uint32_t BoardSubmissions = 0;
    std::uint32_t LeaveSubmissions = 0;
    std::string LastReason;
};

struct TransportMemberObservation
{
    bool Alive = false;
    bool TransportPresent = false;
    bool TransportAmbiguous = false;
    bool ReadyToBoard = false;
    bool AtExit = false;
    bool OnThisTransport = false;
    bool OnOtherTransportOrVehicle = false;
    bool InsideFootprint = false;
    bool Moving = false;
    // Static (non-transport) ground directly under the member.
    bool StaticFloorUnderfoot = false;
    float DistanceToWait = 0.0f;
    float DistanceToBoard = 0.0f;
    float DistanceToDisembark = 0.0f;
    float DistanceToExit = 0.0f;
};

struct TransportDecision
{
    TransportStep Step = TransportStep::Hold;
    std::string Reason;
};

inline TransportDecision DecideTransportStep(TransportContract const& contract,
    TransportMemberObservation const& observation, TransportMemberState& state)
{
    if (!observation.Alive)
        return { TransportStep::Hold, "transport_member_dead" };
    if (observation.OnThisTransport)
        state.Boarded = true;
    if (observation.TransportAmbiguous)
        return { TransportStep::Blocked, "transport_ambiguous" };
    if (!observation.TransportPresent)
        return { TransportStep::Blocked, "transport_missing" };
    if (observation.OnOtherTransportOrVehicle && !observation.OnThisTransport)
        return { TransportStep::Blocked, "transport_member_on_other_transport" };

    if (observation.OnThisTransport)
    {
        if (!contract.HasExit())
            return { TransportStep::Done, "transport_boarded" };
        if (!observation.AtExit)
            return { TransportStep::HoldAboard, "transport_riding" };
        // The platform rests flush with the destination floor. Leave while
        // stationary over static ground, then walk off on the static navmesh
        // as a non-passenger.
        if (!observation.StaticFloorUnderfoot)
        {
            if (!contract.DisembarkPoint.Valid)
                return { TransportStep::Blocked, "transport_exit_no_static_floor" };
            if (observation.DistanceToDisembark > contract.ArrivalToleranceYards)
                return { TransportStep::MoveToDisembark, "transport_disembark_path" };
        }
        if (observation.Moving)
            return { TransportStep::HoldAboard, "transport_exit_settling" };
        if (!observation.StaticFloorUnderfoot)
            return { TransportStep::Blocked, "transport_disembark_no_static_floor" };
        return { TransportStep::Leave, "transport_exit_level_reached" };
    }

    if (state.Boarded && contract.HasExit())
    {
        state.Left = true;
        if (observation.DistanceToExit <= contract.ArrivalToleranceYards)
            return { TransportStep::Done, "transport_exit_reached" };
        return { TransportStep::MoveToExit, "transport_exit_path" };
    }

    if (!observation.ReadyToBoard)
    {
        // Never stand where the platform will arrive while it is away.
        if (observation.InsideFootprint && contract.WaitPoint.Valid)
            return { TransportStep::MoveToWait, "transport_not_ready_clear_footprint" };
        if (contract.WaitPoint.Valid
            && observation.DistanceToWait > contract.ArrivalToleranceYards)
            return { TransportStep::MoveToWait, "transport_wait_path" };
        return { TransportStep::Hold, "transport_waiting" };
    }
    if (observation.InsideFootprint
        && observation.DistanceToBoard <= contract.ArrivalToleranceYards)
    {
        if (observation.Moving)
            return { TransportStep::Hold, "transport_board_settling" };
        return { TransportStep::Board, "transport_board_ready" };
    }
    return { TransportStep::MoveToBoard, "transport_board_path" };
}

// Node-level completion for one living member.
inline bool MemberTransportDone(TransportContract const& contract,
    bool onThisTransport, bool boarded, float distanceToExit)
{
    if (!contract.HasExit())
        return onThisTransport;
    return boarded && !onThisTransport
        && distanceToExit <= contract.ArrivalToleranceYards;
}

// ---------------------------------------------------------------------------
// Per-node aggregate stored on the manifest node
// ---------------------------------------------------------------------------
struct RuntimeScope
{
    std::uint64_t AttemptId = 0;
    std::uint64_t WipeGeneration = 0;
    std::uint64_t RouteGeneration = 0;

    bool operator==(RuntimeScope const& other) const
    {
        return std::tie(AttemptId, WipeGeneration, RouteGeneration)
            == std::tie(other.AttemptId, other.WipeGeneration, other.RouteGeneration);
    }
    bool operator!=(RuntimeScope const& other) const { return !(*this == other); }
};

struct NodeRuntime
{
    RuntimeScope Scope;
    bool Started = false;
    std::uint64_t StartedAtMs = 0;
    AttemptState Attempt;
    CompletionMemory Completion;
    std::map<std::uint64_t, TransportMemberState> TransportMembers;
    bool CompletionRecorded = false;
    bool FailureRecorded = false;
    std::string LastDiagnostic;

    // Reset on any change of attempt, wipe or route generation.
    void Enter(RuntimeScope const& scope, std::uint64_t nowMs)
    {
        if (Started && Scope == scope)
            return;
        *this = NodeRuntime();
        Scope = scope;
        Started = true;
        StartedAtMs = nowMs;
    }
};

struct NodeContract
{
    InteractionContract Interaction;
    CompletionContract Completion;
    TransportContract Transport;
    NodeRuntime Runtime;

    bool Declared() const
    {
        return Interaction.Declared || Completion.Declared || Transport.Declared;
    }
};

// Creature entries the encounter observer must keep visible for this node.
inline void CollectObservedCreatureEntries(CompletionContract const& completion,
    std::vector<std::uint32_t>& entries)
{
    switch (completion.Kind)
    {
        case CompletionKind::BossSummoned:
        case CompletionKind::CreatureSummoned:
        case CompletionKind::AuraPresent:
        case CompletionKind::CreatureAggressiveWithVictim:
        case CompletionKind::CreatureGroundedAggressiveOrEngaged:
            entries.push_back(completion.Entry);
            break;
        default:
            break;
    }
    for (CompletionContract const& child : completion.Children)
        CollectObservedCreatureEntries(child, entries);
}

inline std::vector<std::uint32_t> ObservedCreatureEntries(NodeContract const& node)
{
    std::vector<std::uint32_t> entries;
    if (node.Interaction.Declared && node.Interaction.Entry
        && node.Interaction.Target != TargetType::GameObject)
        entries.push_back(node.Interaction.Entry);
    CollectObservedCreatureEntries(node.Completion, entries);
    std::sort(entries.begin(), entries.end());
    entries.erase(std::unique(entries.begin(), entries.end()), entries.end());
    entries.erase(std::remove(entries.begin(), entries.end(), 0u), entries.end());
    return entries;
}
}

#endif
