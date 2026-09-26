#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_LOGIC_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_LOGIC_H

// Pure decision logic for native route contracts: owner election, bounded
// attempts, observed completion evaluation and transport boarding phases.
// The server adapter supplies observations; nothing here touches game state.
// Included only by the route runtime, the encounter observer and tests.
// Transport state and member phases live in the transport logic header.

#include "Bots/BotValidationRouteNativeTransportLogic.h"
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
// Interaction approach point
// ---------------------------------------------------------------------------
// Horizontal distance the owner keeps from the target's position: clear of a
// small prop the target stands on, and well inside every native reach
// (INTERACTION_DISTANCE is 5 yd before both combat reaches are added).
constexpr float InteractionStandOffYards = 2.5f;

// Where the owner walks to reach a creature or gameobject. The native path to
// the target's position ends on the walkable floor, which is not the
// target's own height when it stands on a prop the navmesh leaves out
// (Finkle Einhorn stands 1.6 yd above the chamber floor on a soapbox
// gameobject). The movement planner only admits a destination its path ends
// at, so asking for the target's own position is rejected on every tick.
// The owner walks along that complete native path instead: to its first
// point InteractionStandOffYards from the target (horizontally), or to its
// end when it stops farther out, and only when the target is within
// `reachYards` of that point in exact 3D distance (stricter than the native
// check, which adds both combat reaches). Otherwise, and when the path
// already starts inside the stand-off, the target's position is kept.
inline Point3 SelectInteractionApproachPoint(Point3 const& target,
    std::vector<Point3> const& completePath, float reachYards)
{
    if (!target.Valid || completePath.size() < 2)
        return target;
    auto horizontal = [&target](Point3 const& point)
    {
        return std::hypot(point.X - target.X, point.Y - target.Y);
    };
    if (horizontal(completePath.front()) <= InteractionStandOffYards)
        return target;

    Point3 stand = completePath.back();
    for (std::size_t i = 1; i < completePath.size(); ++i)
    {
        Point3 const& from = completePath[i - 1];
        Point3 const& to = completePath[i];
        if (horizontal(to) > InteractionStandOffYards)
            continue;
        // `from` is outside the stand-off circle and `to` inside it: the
        // smaller root is where this leg first crosses the circle.
        float const dx = to.X - from.X;
        float const dy = to.Y - from.Y;
        float const fx = from.X - target.X;
        float const fy = from.Y - target.Y;
        float const a = dx * dx + dy * dy;
        float const b = 2.0f * (fx * dx + fy * dy);
        float const c = fx * fx + fy * fy
            - InteractionStandOffYards * InteractionStandOffYards;
        float const discriminant = b * b - 4.0f * a * c;
        float t = 1.0f;
        if (a > 0.0f && discriminant >= 0.0f)
            t = std::clamp((-b - std::sqrt(discriminant)) / (2.0f * a), 0.0f, 1.0f);
        stand = { from.X + dx * t, from.Y + dy * t, from.Z + (to.Z - from.Z) * t, true };
        break;
    }
    stand.Valid = true;
    float const dx = stand.X - target.X;
    float const dy = stand.Y - target.Y;
    float const dz = stand.Z - target.Z;
    return std::sqrt(dx * dx + dy * dy + dz * dz) <= reachYards ? stand : target;
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
    // A recovery wake's target and completion creatures too.
    for (RecoveryInteraction const& wake : node.RecoveryInteractions)
    {
        if (wake.Interaction.Entry && wake.Interaction.Target != TargetType::GameObject)
            entries.push_back(wake.Interaction.Entry);
        CollectObservedCreatureEntries(wake.Completion, entries);
        CollectObservedCreatureEntries(wake.Ready, entries);
    }
    std::sort(entries.begin(), entries.end());
    entries.erase(std::unique(entries.begin(), entries.end()), entries.end());
    entries.erase(std::remove(entries.begin(), entries.end(), 0u), entries.end());
    return entries;
}
}

#endif
