#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_LOGIC_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_LOGIC_H

// Pure decision logic for native route contracts: owner election, bounded
// attempts, observed completion evaluation and transport boarding phases.
// The server adapter supplies observations; nothing here touches game state.
// Included only by the route runtime, the encounter observer and tests.

#include "Bots/BotValidationRouteNativeTypes.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <utility>
#include <vector>

namespace BotValidationRouteNative
{
// ---------------------------------------------------------------------------
// Owner election
// ---------------------------------------------------------------------------
struct MemberView
{
    std::uint64_t Guid = 0;
    // Alive and in the route's original instance.
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

// Exhaustion is reported only after the last attempt has had its full retry
// interval to produce the native postcondition.
inline AttemptGate EvaluateAttemptGate(InteractionContract const& contract,
    AttemptState const& state, std::uint64_t startedAtMs, std::uint64_t nowMs)
{
    if (contract.TimeoutMs && nowMs >= startedAtMs + contract.TimeoutMs)
        return AttemptGate::TimedOut;
    bool const retryWindowOpen = contract.RetryIntervalMs && state.Attempts
        && nowMs < state.LastSubmitAtMs + contract.RetryIntervalMs;
    if (contract.MaxAttempts && state.Attempts >= contract.MaxAttempts)
        return retryWindowOpen ? AttemptGate::RetryWait : AttemptGate::AttemptsExhausted;
    return retryWindowOpen ? AttemptGate::RetryWait : AttemptGate::Allowed;
}

// Every native submission counts, whether the handler accepted it or the
// executor rejected it (Retryable/Unsafe): repeated rejections exhaust too.
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
    Fail,
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
    // For area triggers: the trigger exists on the route map.
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
        return { InteractionStep::Fail, false, AttemptGateName(gate) };
    if (contract.Action == InteractionAction::AreaTrigger)
    {
        if (!observation.TargetResolved)
            return { InteractionStep::Hold, false, "native_interaction_area_trigger_invalid" };
    }
    else
    {
        if (observation.TargetAmbiguous)
            return { InteractionStep::Hold, false, "native_interaction_target_ambiguous" };
        if (!observation.TargetResolved)
            return { InteractionStep::Hold, false, "native_interaction_target_missing" };
    }
    // Continuing an open dialogue is part of the attempt that opened it.
    if (contract.IsGossip() && observation.InRange && observation.GossipBoundToTarget
        && std::find(contract.Menus.begin(), contract.Menus.end(),
            observation.CurrentGossipMenu) != contract.Menus.end())
        return { InteractionStep::GossipSelect, false, "native_gossip_select" };
    if (gate == AttemptGate::AttemptsExhausted)
        return { InteractionStep::Fail, false, AttemptGateName(gate) };
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
            commit.Step = InteractionStep::GossipOpen;
            break;
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

struct ObjectQuery
{
    std::vector<ActorFact> Facts;
    // True only when the lookup was the route instance's spawn-id store with
    // the spawn's grid loaded: then "not found" means "not in the world".
    bool AbsenceAuthoritative = false;
};

struct MemberFact
{
    std::uint64_t Guid = 0;
    bool Alive = false;
    // On the route map, in the route's original instance.
    bool OnRouteInstance = false;
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
    float StationaryZ = 0.0f;
};

// GOState values (SharedDefines.h): 25 + n means "stop at stop frame n".
constexpr std::uint32_t GoStateTransportStopped = 25;

class FactSource
{
public:
    virtual ~FactSource() = default;
    virtual std::vector<ActorFact> Creatures(std::uint32_t entry, std::uint64_t spawnId) const = 0;
    virtual ObjectQuery GameObjects(std::uint32_t entry, std::uint64_t spawnId) const = 0;
    virtual bool BossState(std::uint32_t index, std::uint32_t& state) const = 0;
    // Every living cohort member, wherever it is.
    virtual std::vector<MemberFact> Members() const = 0;
    virtual TransportFact Transport(std::uint32_t entry, std::uint64_t spawnId) const = 0;
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
        std::uint32_t considered = 0, satisfied = 0;
        for (MemberFact const& member : facts.Members())
        {
            if (!member.Alive)
                continue;
            if (!member.OnRouteInstance)
            {
                // "All" means every living member; one elsewhere blocks it.
                if (contract.Scope == MemberScope::All)
                    return { false, "members_off_route_map" };
                continue;
            }
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
            for (ActorFact const& object : facts.GameObjects(contract.Entry, contract.SpawnId).Facts)
                if (object.Spawned && object.Selectable && object.Interactable)
                    return verdict(true, "gameobject_selectable");
            return verdict(false, "gameobject_not_selectable");
        }
        case CompletionKind::GameObjectDespawned:
        {
            std::string const key = "go:" + std::to_string(contract.Entry) + ":"
                + std::to_string(contract.SpawnId);
            ObjectQuery const query = facts.GameObjects(contract.Entry, contract.SpawnId);
            bool spawned = false;
            for (ActorFact const& object : query.Facts)
                spawned = spawned || object.Spawned;
            if (spawned)
            {
                memory.Remember(key);
                return verdict(false, "gameobject_still_spawned");
            }
            // Not found is unknown unless the route instance's spawn store
            // says so; a present-but-unspawned object is known despawned.
            if (query.Facts.empty() && !query.AbsenceAuthoritative)
                return verdict(false, "gameobject_absence_unknown");
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
// Transport geometry and timeline
// ---------------------------------------------------------------------------
struct LocalBox
{
    float MinX = 0.0f, MinY = 0.0f, MinZ = 0.0f;
    float MaxX = 0.0f, MaxY = 0.0f, MaxZ = 0.0f;
    bool Valid = false;
};

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

inline bool InsideBox(Point3 const& local, LocalBox const& box, float margin)
{
    return local.Valid && box.Valid
        && local.X >= box.MinX - margin && local.X <= box.MaxX + margin
        && local.Y >= box.MinY - margin && local.Y <= box.MaxY + margin
        && local.Z >= box.MinZ - margin && local.Z <= box.MaxZ + margin;
}

// TransportAnimation Z keyframes (time ms -> offset from the stationary
// origin) of a continuously cycling transport.
struct TransportTimeline
{
    std::vector<std::pair<std::uint32_t, float>> ZKeys;
    std::uint32_t PeriodMs = 0;

    float OffsetAt(std::uint32_t timeMs) const
    {
        if (ZKeys.empty())
            return 0.0f;
        if (timeMs <= ZKeys.front().first)
            return ZKeys.front().second;
        for (std::size_t i = 1; i < ZKeys.size(); ++i)
            if (timeMs <= ZKeys[i].first)
            {
                auto const& [t0, z0] = ZKeys[i - 1];
                auto const& [t1, z1] = ZKeys[i];
                float const f = t1 > t0 ? float(timeMs - t0) / float(t1 - t0) : 1.0f;
                return z0 + (z1 - z0) * f;
            }
        return ZKeys.back().second;
    }
};

constexpr std::uint64_t UnboundedRestMs = std::numeric_limits<std::uint64_t>::max();

// Milliseconds the platform keeps its origin within `tolerance` of
// `levelOffset` from `progressMs` on (0 when not at the level now).
inline std::uint64_t RestRemainingMs(TransportTimeline const& timeline,
    std::uint32_t progressMs, float levelOffset, float tolerance, std::uint32_t stepMs = 25)
{
    if (!timeline.PeriodMs || timeline.ZKeys.empty())
        return 0;
    auto atLevel = [&](std::uint32_t t)
    {
        return std::fabs(timeline.OffsetAt(t % timeline.PeriodMs) - levelOffset) <= tolerance;
    };
    if (!atLevel(progressMs))
        return 0;
    for (std::uint32_t elapsed = stepMs; elapsed <= timeline.PeriodMs; elapsed += stepMs)
        if (!atLevel(progressMs + elapsed))
            return elapsed - stepMs;
    return UnboundedRestMs;
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

// ---------------------------------------------------------------------------
// Transport member phases
// ---------------------------------------------------------------------------
enum class TransportStep : std::uint8_t
{
    Hold,
    Stop,
    MoveToWait,
    MoveToBoard,
    Board,
    HoldAboard,
    MoveToDisembark,
    Leave,
    MoveToExit,
    Done,
    Blocked,
    Fail
};

inline char const* TransportStepName(TransportStep step)
{
    switch (step)
    {
        case TransportStep::Hold: return "hold";
        case TransportStep::Stop: return "stop";
        case TransportStep::MoveToWait: return "move_to_wait";
        case TransportStep::MoveToBoard: return "move_to_board";
        case TransportStep::Board: return "board";
        case TransportStep::HoldAboard: return "hold_aboard";
        case TransportStep::MoveToDisembark: return "move_to_disembark";
        case TransportStep::Leave: return "leave";
        case TransportStep::MoveToExit: return "move_to_exit";
        case TransportStep::Done: return "done";
        case TransportStep::Blocked: return "blocked";
        case TransportStep::Fail: return "fail";
    }
    return "unknown";
}

// Margin between the planned walk and the end of a platform's rest window.
constexpr std::uint64_t BoardWindowMarginMs = 300;
// A member that stood on the platform is stranded only after it has been
// stationary (not walking, not falling) with no floor at all for this many
// consecutive observations spanning at least this long.
constexpr std::uint32_t StrandedConfirmObservations = 3;
constexpr std::uint64_t StrandedConfirmMs = 400;

struct TransportMemberObservation
{
    bool Alive = false;
    bool TransportPresent = false;
    bool TransportAmbiguous = false;
    bool ReadyToBoard = false;
    bool AtExit = false;
    bool OnThisTransport = false;
    bool OnOtherTransportOrVehicle = false;
    bool Moving = false;
    bool Falling = false;
    std::uint64_t NowMs = 0;
    // Floors directly underfoot, within the contract's floor tolerance.
    bool StaticFloorUnderfoot = false;
    // This transport's own model surface (not merely its bounding box).
    bool TransportFloorUnderfoot = false;
    // Remaining rest of the platform at the boarding level (UnboundedRestMs
    // for an arrived script-held stop frame), and the estimated walk time to
    // the board point along the native path.
    std::uint64_t RestRemainingMs = 0;
    std::uint64_t TravelToBoardMs = 0;
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
    if (state.FailedSubmissions >= contract.MaxSubmissions)
        return { TransportStep::Fail, "transport_submissions_exhausted" };

    if (observation.OnThisTransport)
    {
        state.FloorlessObservations = 0;
        state.FloorlessSinceMs = 0;
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

    // Not a passenger. Track the floor it stands on: only a member whose
    // last floor was this platform, and who has since been stationary with
    // no floor at all for a confirmed period, is stranded. A walking or
    // falling member may briefly sit above the vmap floor between path points.
    bool const onPlatformFloor = observation.TransportFloorUnderfoot
        && !observation.StaticFloorUnderfoot;
    bool const floorless = !observation.StaticFloorUnderfoot
        && !observation.TransportFloorUnderfoot;
    if (observation.StaticFloorUnderfoot)
        state.PlatformFloorSeen = false;
    else if (onPlatformFloor)
        state.PlatformFloorSeen = true;
    bool const settled = !observation.Moving && !observation.Falling;
    if (floorless && settled && state.PlatformFloorSeen)
    {
        if (!state.FloorlessObservations)
            state.FloorlessSinceMs = observation.NowMs;
        ++state.FloorlessObservations;
        if (state.FloorlessObservations >= StrandedConfirmObservations
            && observation.NowMs >= state.FloorlessSinceMs + StrandedConfirmMs)
            return { TransportStep::Fail, "transport_member_stranded_without_floor" };
        return { TransportStep::Hold, "transport_member_floor_lost_confirming" };
    }
    state.FloorlessObservations = 0;
    state.FloorlessSinceMs = 0;
    if (floorless && settled)
        return { TransportStep::Hold, "transport_member_floor_unverified" };

    if (state.Boarded && contract.HasExit())
    {
        state.Left = true;
        if (observation.DistanceToExit <= contract.ArrivalToleranceYards)
            return { TransportStep::Done, "transport_exit_reached" };
        return { TransportStep::MoveToExit, "transport_exit_path" };
    }

    bool const windowShort = observation.RestRemainingMs != UnboundedRestMs
        && observation.RestRemainingMs < observation.TravelToBoardMs + BoardWindowMarginMs;
    // Standing on this platform's own surface: board from here. The board
    // point is only the navigation target; the floor proves the stance, so a
    // walk that reached the platform stops and boards before it moves on.
    if (onPlatformFloor)
    {
        if (observation.Moving)
            return { TransportStep::Stop, "transport_board_stop_on_platform" };
        return { TransportStep::Board, "transport_board_ready" };
    }

    if (!observation.ReadyToBoard)
    {
        if (contract.WaitPoint.Valid
            && observation.DistanceToWait > contract.ArrivalToleranceYards)
            return { TransportStep::MoveToWait, "transport_wait_path" };
        if (observation.Moving)
            return { TransportStep::Stop, "transport_not_ready_stop" };
        return { TransportStep::Hold, "transport_waiting" };
    }
    // Board only from this platform's own surface, never from static ground
    // that merely lies inside the model's bounding box.
    if (observation.DistanceToBoard <= contract.ArrivalToleranceYards)
        return { TransportStep::Blocked, "transport_board_point_not_on_platform_floor" };
    if (windowShort)
    {
        // Never let a walk toward the platform outrun its rest window.
        if (observation.Moving)
            return contract.WaitPoint.Valid
                && observation.DistanceToWait > contract.ArrivalToleranceYards
                ? TransportDecision{ TransportStep::MoveToWait, "transport_rest_window_short_retreat" }
                : TransportDecision{ TransportStep::Stop, "transport_rest_window_short_stop" };
        return { TransportStep::Hold, "transport_rest_window_too_short" };
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
// Observation scope
// ---------------------------------------------------------------------------
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

// Creature entries the encounter observer must keep visible for this node.
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
