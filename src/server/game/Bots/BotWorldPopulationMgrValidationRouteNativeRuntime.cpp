#include "Bots/BotWorldPopulationMgrValidationRouteNativeRuntime.h"
#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"

#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "GameObject.h"
#include "GossipDef.h"
#include "InstanceScript.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Transport.h"

#include <algorithm>
#include <cmath>
#include <utility>

namespace
{
using namespace BotValidationRouteNative;
using BotWorldPopulationMgrValidationRouteNative::Callbacks;
using BotWorldPopulationMgrValidationRouteNative::Input;

// Native interaction and transport targets are resolved around the acting
// bot; spawn IDs are resolved map-wide.
constexpr float TargetSearchRadius = 250.0f;

ActorFact FromSnapshot(BotEncounter::ActorSnapshot const& actor)
{
    ActorFact fact;
    fact.Entry = actor.Entry;
    fact.Alive = actor.Alive;
    fact.Spawned = actor.Alive;
    fact.Selectable = actor.Selectable;
    fact.Interactable = actor.Interactable;
    fact.ReactAggressive = actor.ReactAggressive;
    fact.InCombat = actor.InCombat;
    fact.Flying = actor.Flying;
    fact.HasVictim = !actor.VictimGuid.IsEmpty();
    for (BotEncounter::AuraSnapshot const& aura : actor.Auras)
        fact.AuraIds.push_back(aura.SpellId);
    return fact;
}

ActorFact FromCreature(Creature const* creature)
{
    ActorFact fact;
    fact.Entry = creature->GetEntry();
    fact.SpawnId = creature->GetSpawnId();
    fact.Alive = creature->IsAlive();
    fact.Spawned = creature->IsInWorld();
    fact.Selectable = !creature->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
    fact.Interactable = creature->GetUInt32Value(UNIT_NPC_FLAGS) != 0;
    fact.ReactAggressive = creature->GetReactState() == REACT_AGGRESSIVE;
    fact.InCombat = creature->IsInCombat();
    fact.Flying = creature->IsFlying();
    fact.HasVictim = creature->GetVictim() != nullptr;
    for (auto const& applied : creature->GetAppliedAuras())
        fact.AuraIds.push_back(applied.first);
    return fact;
}

ActorFact FromGameObject(GameObject const* object)
{
    ActorFact fact;
    fact.Entry = object->GetEntry();
    fact.SpawnId = object->GetSpawnId();
    fact.Spawned = object->isSpawned();
    fact.Alive = fact.Spawned;
    fact.Selectable = fact.Spawned
        && !object->HasFlag(GAMEOBJECT_FLAGS, GO_FLAG_NOT_SELECTABLE);
    fact.Interactable = fact.Selectable;
    return fact;
}

std::vector<GameObject*> FindGameObjects(Player* bot, uint32 entry, uint64 spawnId)
{
    std::vector<GameObject*> found;
    Map* map = bot->GetMap();
    if (!map)
        return found;
    if (spawnId)
    {
        auto bounds = map->GetGameObjectBySpawnIdStore().equal_range(
            ObjectGuid::LowType(spawnId));
        for (auto itr = bounds.first; itr != bounds.second; ++itr)
            if (GameObject* object = itr->second; object && object->IsInWorld()
                && (!entry || object->GetEntry() == entry))
                found.push_back(object);
        return found;
    }
    std::vector<GameObject*> objects;
    bot->GetGameObjectListWithEntryInGrid(objects, entry, TargetSearchRadius);
    for (GameObject* object : objects)
        if (object && object->IsInWorld())
            found.push_back(object);
    return found;
}

std::vector<Creature*> FindCreatures(Player* bot, uint32 entry, uint64 spawnId)
{
    std::vector<Creature*> found;
    Map* map = bot->GetMap();
    if (!map)
        return found;
    if (spawnId)
    {
        auto bounds = map->GetCreatureBySpawnIdStore().equal_range(
            ObjectGuid::LowType(spawnId));
        for (auto itr = bounds.first; itr != bounds.second; ++itr)
            if (Creature* creature = itr->second; creature && creature->IsInWorld()
                && (!entry || creature->GetEntry() == entry))
                found.push_back(creature);
        return found;
    }
    std::vector<Creature*> creatures;
    bot->GetCreatureListWithEntryInGrid(creatures, entry, TargetSearchRadius);
    for (Creature* creature : creatures)
        if (creature && creature->IsInWorld() && creature->IsAlive())
            found.push_back(creature);
    return found;
}

struct ResolvedTarget
{
    WorldObject* Object = nullptr;
    bool Ambiguous = false;
};

ResolvedTarget ResolveInteractionTarget(Player* bot, InteractionContract const& contract)
{
    ResolvedTarget resolved;
    std::vector<WorldObject*> candidates;
    if (contract.Target == TargetType::GameObject || contract.Target == TargetType::Any)
        for (GameObject* object : FindGameObjects(bot, contract.Entry, contract.SpawnId))
            if (object->isSpawned())
                candidates.push_back(object);
    if (contract.Target == TargetType::Creature || contract.Target == TargetType::Any)
        for (Creature* creature : FindCreatures(bot, contract.Entry, contract.SpawnId))
            if (creature->IsAlive())
                candidates.push_back(creature);
    // A declared target must name exactly one live object; never guess.
    resolved.Ambiguous = candidates.size() > 1;
    if (candidates.size() == 1)
        resolved.Object = candidates.front();
    return resolved;
}

struct TransportTarget
{
    GameObject* Object = nullptr;
    TransportFact Fact;
};

TransportTarget ResolveTransport(Player* bot, uint32 entry, uint64 spawnId)
{
    TransportTarget target;
    std::vector<GameObject*> transports;
    for (GameObject* object : FindGameObjects(bot, entry, spawnId))
        if (object->GetGoType() == GAMEOBJECT_TYPE_TRANSPORT && object->ToTransportBase())
            transports.push_back(object);
    if (transports.size() > 1)
    {
        target.Fact.Present = true;
        target.Fact.Ambiguous = true;
        return target;
    }
    if (transports.empty())
        return target;
    target.Object = transports.front();
    target.Fact = BotValidationRouteBoardingAction::ObserveTransport(target.Object);
    return target;
}

bool OnTransport(Player const* member, GameObject const* transport)
{
    TransportBase const* current = member ? member->GetTransport() : nullptr;
    return current && transport && current->GetTransportGUID() == transport->GetGUID();
}

class ServerFacts final : public FactSource
{
public:
    ServerFacts(Input const& input, uint64 owner) : _input(input), _owner(owner) { }

    std::vector<ActorFact> Creatures(uint32 entry, uint64 spawnId) const override
    {
        std::vector<ActorFact> facts;
        if (spawnId)
        {
            for (Creature* creature : FindCreatures(_input.Bot, entry, spawnId))
                facts.push_back(FromCreature(creature));
            return facts;
        }
        // Entry-based creature facts come from the shared encounter
        // observation, the same view every strategy reads.
        auto add = [&facts, entry](std::vector<BotEncounter::ActorSnapshot> const& actors)
        {
            for (BotEncounter::ActorSnapshot const& actor : actors)
                if (actor.Entry == entry && !actor.Guid.IsGameObject())
                    facts.push_back(FromSnapshot(actor));
        };
        add(_input.Board->Hostiles);
        add(_input.Board->Summons);
        add(_input.Board->Interactables);
        return facts;
    }

    std::vector<ActorFact> GameObjects(uint32 entry, uint64 spawnId) const override
    {
        std::vector<ActorFact> facts;
        for (GameObject* object : FindGameObjects(_input.Bot, entry, spawnId))
            facts.push_back(FromGameObject(object));
        return facts;
    }

    bool BossState(uint32 index, uint32& state) const override
    {
        InstanceScript const* instance = _input.Bot->GetInstanceScript();
        if (!instance || index >= instance->GetEncounterCount())
            return false;
        state = uint32(instance->GetBossState(index));
        return true;
    }

    std::vector<MemberFact> Members() const override
    {
        std::vector<MemberFact> facts;
        Map* map = _input.Bot->GetMap();
        for (Player* member : _input.Members)
        {
            if (!member || !member->IsInWorld())
                continue;
            MemberFact fact;
            fact.Guid = member->GetGUID().GetRawValue();
            fact.Alive = member->IsAlive();
            fact.Owner = fact.Guid == _owner;
            if (TransportBase const* transport = member->GetTransport())
            {
                fact.OnTransport = true;
                if (GameObject const* object = map
                        ? map->GetGameObject(transport->GetTransportGUID()) : nullptr)
                {
                    fact.TransportEntry = object->GetEntry();
                    fact.TransportSpawnId = object->GetSpawnId();
                }
            }
            if (Unit const* vehicle = member->GetVehicleBase())
            {
                fact.VehicleEntry = vehicle->GetEntry();
                fact.Seat = member->GetTransSeat();
            }
            facts.push_back(fact);
        }
        return facts;
    }

    TransportFact Transport(uint32 entry, uint64 spawnId) const override
    {
        return ResolveTransport(_input.Bot, entry, spawnId).Fact;
    }

private:
    Input const& _input;
    uint64 _owner;
};

void Submit(Input const& input, Callbacks const& callbacks, std::string const& mechanic,
    ObjectGuid actor, BotActionArbitration::Priority priority, float utility,
    BotNativeAction::Intent intent, std::string actionLabel,
    std::function<void()> onCommitted = {})
{
    BotNativeAction::Candidate native;
    native.Id.ScopeKey = input.Board->CurrentScope.Key();
    native.Id.Strategy = "native_route_interaction";
    native.Id.Mechanic = mechanic;
    native.Id.Actor = actor;
    native.Id.EventGeneration = input.Board->Revision;
    native.ActionPriority = priority;
    native.Utility = utility;
    native.ExpiresAtMs = input.NowMs + 500;
    native.Action = std::move(intent);

    BotActionArbitration::Candidate candidate;
    candidate.Key = native.Id.Key();
    candidate.Source = native.Id.Strategy;
    candidate.ActionPriority = native.ActionPriority;
    candidate.UtilityScore = native.Utility;
    candidate.RequiredResources = native.Resources();
    candidate.ExpiresAtMs = native.ExpiresAtMs;
    candidate.Attempt = [execute = callbacks.Execute, action = native.Action,
        situation = input.Situation, label = input.Action, state = input.State,
        actionLabel = std::move(actionLabel), onCommitted = std::move(onCommitted)]()
    {
        BotActionArbitration::Outcome outcome = execute(action,
            BotMovementArbitration::Owner::Route,
            BotMovementArbitration::Priority::Route);
        if (outcome.Result == BotActionArbitration::Disposition::Committed)
        {
            *situation = "native_route_interaction";
            *label = actionLabel;
            state->LastDecisionHandler = "native_route_interaction";
            if (onCommitted)
                onCommitted();
        }
        return outcome;
    };
    input.State->DecisionKernel.Submit(std::move(candidate));
}

// Keep the member where it is (on a platform, or at the boarding wait point)
// by owning the movement lane without issuing any movement.
void SubmitHold(Input const& input, std::string const& reason)
{
    BotActionArbitration::Candidate candidate;
    candidate.Key = input.Board->CurrentScope.Key() + ":native_route_transport_hold";
    candidate.Source = "native_route_interaction";
    candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
    candidate.UtilityScore = 1.0f;
    candidate.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    candidate.ExpiresAtMs = input.NowMs + 500;
    candidate.Attempt = [reason, situation = input.Situation, label = input.Action,
        state = input.State]()
    {
        *situation = "native_route_interaction";
        *label = "native_route_" + reason;
        state->LastDecisionHandler = "native_route_interaction";
        return BotActionArbitration::Outcome::Progressed(reason);
    };
    input.State->DecisionKernel.Submit(std::move(candidate));
}

void RecordOnChange(Callbacks const& callbacks, std::string& last,
    std::string const& reason, WorldObject* target, float value, uint32 entry)
{
    if (last == reason)
        return;
    last = reason;
    if (callbacks.Record)
        callbacks.Record(reason, target, value, entry);
}

std::vector<MemberView> MemberViews(Input const& input)
{
    std::vector<MemberView> views;
    for (BotEncounter::ActorSnapshot const& player : input.Board->Players)
    {
        MemberView view;
        view.Guid = player.Guid.GetRawValue();
        view.Alive = player.Alive;
        view.Role = player.Role;
        auto roster = input.Roster.find(view.Guid);
        if (roster != input.Roster.end())
        {
            view.RosterSlot = roster->second.Slot;
            if (!roster->second.Role.empty())
                view.Role = roster->second.Role;
        }
        views.push_back(std::move(view));
    }
    return views;
}

void RunInteraction(Input const& input, Callbacks const& callbacks,
    NodeContract& node, OwnerElection const& election)
{
    InteractionContract const& contract = node.Interaction;
    NodeRuntime& runtime = node.Runtime;
    Player* bot = input.Bot;
    uint64 const self = bot->GetGUID().GetRawValue();
    AttemptGate const gate = EvaluateAttemptGate(contract, runtime.Attempt,
        runtime.StartedAtMs, input.NowMs);
    if (gate == AttemptGate::TimedOut && !runtime.FailureRecorded)
    {
        runtime.FailureRecorded = true;
        if (callbacks.Fail)
            callbacks.Fail(AttemptGateName(gate));
        return;
    }

    if (!election.Owner)
        RecordOnChange(callbacks, runtime.LastDiagnostic, election.Reason, nullptr, 0.0f, 0);
    if (election.Owner != self)
    {
        // Everyone but the owner holds (or gathers) at the node anchor.
        if (contract.Gather && bot->IsAlive()
            && bot->GetExactDist(input.AnchorX, input.AnchorY, input.AnchorZ)
                > contract.GatherRadiusYards)
            Submit(input, callbacks, "gather", bot->GetGUID(),
                BotActionArbitration::Priority::RouteMovement, 1.0f,
                BotNativeAction::Move{ input.AnchorX, input.AnchorY,
                    input.AnchorZ, "native_interaction_gather" },
                "native_route_interaction_gather");
        return;
    }

    InteractionObservation observation;
    WorldObject* target = nullptr;
    float targetX = 0.0f, targetY = 0.0f, targetZ = 0.0f;
    if (contract.Action == InteractionAction::AreaTrigger)
    {
        AreaTriggerEntry const* trigger = sAreaTriggerStore.LookupEntry(contract.AreaTriggerId);
        observation.TargetResolved = trigger && trigger->ContinentID == bot->GetMapId();
        if (observation.TargetResolved)
        {
            targetX = trigger->Pos.X;
            targetY = trigger->Pos.Y;
            targetZ = trigger->Pos.Z;
            observation.InRange = bot->IsInAreaTriggerRadius(trigger);
        }
    }
    else
    {
        ResolvedTarget const resolved = ResolveInteractionTarget(bot, contract);
        target = resolved.Object;
        observation.TargetAmbiguous = resolved.Ambiguous;
        observation.TargetResolved = target != nullptr;
        if (target)
        {
            targetX = target->GetPositionX();
            targetY = target->GetPositionY();
            targetZ = target->GetPositionZ();
            float const range = contract.RangeYards > 0.0f
                ? contract.RangeYards : INTERACTION_DISTANCE;
            GameObject const* object = target->ToGameObject();
            observation.InRange = object && contract.RangeYards <= 0.0f
                ? object->IsAtInteractDistance(bot)
                : bot->IsWithinDistInMap(target, range);
            observation.CurrentGossipMenu =
                bot->PlayerTalkClass->GetGossipMenu().GetMenuId();
            observation.GossipBoundToTarget =
                bot->PlayerTalkClass->GetInteractionData().SourceGuid == target->GetGUID();
        }
    }

    InteractionDecision const decision = DecideInteraction(contract, observation, gate);
    RecordOnChange(callbacks, runtime.LastDiagnostic, decision.Reason, target,
        float(runtime.Attempt.Attempts), contract.Entry);

    ObjectGuid const targetGuid = target ? target->GetGUID() : ObjectGuid::Empty;
    BotNativeAction::Intent intent;
    switch (decision.Step)
    {
        case InteractionStep::Hold:
            return;
        case InteractionStep::Approach:
            intent = BotNativeAction::Move{ targetX, targetY, targetZ,
                "native_interaction_approach" };
            break;
        case InteractionStep::Use:
            intent = BotNativeAction::GameObjectUse{ targetGuid };
            break;
        case InteractionStep::GossipOpen:
            intent = BotNativeAction::GossipOpen{ targetGuid };
            break;
        case InteractionStep::GossipSelect:
            intent = BotNativeAction::GossipSelect{ targetGuid,
                observation.CurrentGossipMenu, contract.Option };
            break;
        case InteractionStep::SpellClick:
            intent = BotNativeAction::SpellClick{ targetGuid };
            break;
        case InteractionStep::VehicleEnter:
            intent = BotNativeAction::VehicleEnter{ targetGuid, int8(contract.Seat) };
            break;
        case InteractionStep::AreaTrigger:
            intent = BotNativeAction::AreaTrigger{ contract.AreaTriggerId };
            break;
    }
    std::function<void()> onCommitted;
    if (decision.CountsAsAttempt)
        onCommitted = [attempt = &runtime.Attempt, now = input.NowMs]()
        {
            RecordAttempt(*attempt, now);
        };
    Submit(input, callbacks, contract.ActionName, targetGuid,
        BotActionArbitration::Priority::Mechanic, 6.0f, std::move(intent),
        "native_route_interaction_submitted", std::move(onCommitted));
}

void RunTransport(Input const& input, Callbacks const& callbacks, NodeContract& node,
    TransportTarget const& transport)
{
    TransportContract const& contract = node.Transport;
    Player* bot = input.Bot;
    TransportMemberState& member =
        node.Runtime.TransportMembers[bot->GetGUID().GetRawValue()];

    TransportMemberObservation observation;
    observation.Alive = bot->IsAlive();
    observation.TransportPresent = transport.Fact.Present;
    observation.TransportAmbiguous = transport.Fact.Ambiguous;
    observation.ReadyToBoard = TransportReadyToBoard(contract, transport.Fact);
    observation.AtExit = TransportAtExit(contract, transport.Fact);
    observation.OnThisTransport = OnTransport(bot, transport.Object);
    observation.OnOtherTransportOrVehicle = (bot->GetTransport() && !observation.OnThisTransport)
        || bot->GetVehicle();
    observation.Moving = bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
    auto distance = [bot](Point3 const& point)
    {
        return point.Valid ? bot->GetExactDist(point.X, point.Y, point.Z) : 0.0f;
    };
    observation.DistanceToWait = distance(contract.WaitPoint);
    observation.DistanceToBoard = distance(contract.BoardPoint);
    observation.DistanceToDisembark = distance(contract.DisembarkPoint);
    observation.DistanceToExit = distance(contract.ExitPoint);
    if (Map* map = bot->GetMap())
    {
        float const staticFloor = map->GetStaticHeight(bot->GetPhaseShift(),
            bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ() + 1.0f,
            true, 4.0f);
        observation.StaticFloorUnderfoot = staticFloor > INVALID_HEIGHT
            && std::fabs(bot->GetPositionZ() - staticFloor) <= 1.5f;
    }

    LocalBox box;
    bool const footprintKnown = transport.Object
        && BotValidationRouteBoardingAction::DisplayFootprint(transport.Object, box);
    if (transport.Object && footprintKnown)
    {
        float x = bot->GetPositionX(), y = bot->GetPositionY(), z = bot->GetPositionZ();
        float o = bot->GetOrientation();
        transport.Object->ToTransportBase()->CalculatePassengerOffset(x, y, z, &o);
        observation.InsideFootprint = InsideFootprint({ x, y, z, true }, box,
            contract.FootprintMarginYards);
    }

    TransportDecision decision = transport.Object && !footprintKnown
        ? TransportDecision{ TransportStep::Blocked, "transport_footprint_unknown" }
        : DecideTransportStep(contract, observation, member);
    RecordOnChange(callbacks, member.LastReason,
        std::string("native_route_transport_") + TransportStepName(decision.Step)
            + ":" + decision.Reason,
        transport.Object, transport.Fact.PositionZ, contract.Entry);

    ObjectGuid const transportGuid = transport.Object
        ? transport.Object->GetGUID() : ObjectGuid::Empty;
    switch (decision.Step)
    {
        case TransportStep::Hold:
        case TransportStep::HoldAboard:
        case TransportStep::Done:
            SubmitHold(input, decision.Reason);
            break;
        case TransportStep::Blocked:
            break;
        case TransportStep::MoveToWait:
            Submit(input, callbacks, "transport_wait", transportGuid,
                BotActionArbitration::Priority::Mechanic, 4.0f,
                BotNativeAction::Move{ contract.WaitPoint.X, contract.WaitPoint.Y,
                    contract.WaitPoint.Z, "native_transport_wait" },
                "native_route_transport_wait");
            break;
        case TransportStep::MoveToBoard:
            Submit(input, callbacks, "transport_board_path", transportGuid,
                BotActionArbitration::Priority::Mechanic, 4.0f,
                BotNativeAction::Move{ contract.BoardPoint.X, contract.BoardPoint.Y,
                    contract.BoardPoint.Z, "native_transport_board_path" },
                "native_route_transport_board_path");
            break;
        case TransportStep::Board:
            Submit(input, callbacks, "transport_board", transportGuid,
                BotActionArbitration::Priority::Mechanic, 6.0f,
                BotNativeAction::TransportBoard{ transportGuid,
                    contract.FootprintMarginYards },
                "native_route_transport_board",
                [&member]() { ++member.BoardSubmissions; });
            break;
        case TransportStep::MoveToDisembark:
            Submit(input, callbacks, "transport_disembark_path", transportGuid,
                BotActionArbitration::Priority::Mechanic, 4.0f,
                BotNativeAction::Move{ contract.DisembarkPoint.X,
                    contract.DisembarkPoint.Y, contract.DisembarkPoint.Z,
                    "native_transport_disembark_path" },
                "native_route_transport_disembark_path");
            break;
        case TransportStep::Leave:
            Submit(input, callbacks, "transport_leave", transportGuid,
                BotActionArbitration::Priority::Mechanic, 6.0f,
                BotNativeAction::TransportLeave{ transportGuid },
                "native_route_transport_leave",
                [&member]() { ++member.LeaveSubmissions; });
            break;
        case TransportStep::MoveToExit:
            Submit(input, callbacks, "transport_exit_path", transportGuid,
                BotActionArbitration::Priority::Mechanic, 4.0f,
                BotNativeAction::Move{ contract.ExitPoint.X, contract.ExitPoint.Y,
                    contract.ExitPoint.Z, "native_transport_exit_path" },
                "native_route_transport_exit_path");
            break;
    }
}

bool TransportNodeDone(Input const& input, NodeContract& node, TransportTarget const& transport)
{
    if (!transport.Object)
        return false;
    uint32 living = 0;
    for (Player* member : input.Members)
    {
        if (!member || !member->IsInWorld() || !member->IsAlive())
            continue;
        ++living;
        TransportMemberState& state =
            node.Runtime.TransportMembers[member->GetGUID().GetRawValue()];
        bool const aboard = OnTransport(member, transport.Object);
        if (aboard)
            state.Boarded = true;
        Point3 const& exit = node.Transport.ExitPoint;
        float const exitDistance = exit.Valid
            ? member->GetExactDist(exit.X, exit.Y, exit.Z) : 0.0f;
        if (!MemberTransportDone(node.Transport, aboard, state.Boarded, exitDistance))
            return false;
    }
    return living > 0;
}
}

namespace BotWorldPopulationMgrValidationRouteNative
{
Result Run(Input const& input, Callbacks const& callbacks)
{
    Result result;
    if (!input.Bot || !input.State || !input.Board || !input.Node
        || !input.Situation || !input.Action || !input.Node->Declared())
        return result;
    result.OwnsNode = true;

    NodeContract& node = *input.Node;
    node.Runtime.Enter(input.Scope, input.NowMs);

    OwnerElection const election = node.Interaction.Declared
        ? ElectOwner(node.Interaction, MemberViews(input)) : OwnerElection();
    ServerFacts const facts(input, election.Owner);

    TransportTarget transport;
    if (node.Transport.Declared)
        transport = ResolveTransport(input.Bot, node.Transport.Entry, node.Transport.SpawnId);

    bool completionSatisfied = true;
    std::string completionLabel = node.Completion.KindName;
    if (node.Completion.Declared)
    {
        Verdict const verdict = EvaluateCompletion(node.Completion, facts,
            node.Runtime.Completion);
        completionSatisfied = verdict.Satisfied;
    }
    if (node.Transport.Declared)
    {
        completionSatisfied = completionSatisfied
            && TransportNodeDone(input, node, transport);
        if (completionLabel.empty())
            completionLabel = "transport_route_complete";
    }

    if (completionSatisfied)
    {
        result.Satisfied = true;
        if (!input.CompletionAlreadyRecorded && !node.Runtime.CompletionRecorded)
        {
            node.Runtime.CompletionRecorded = true;
            if (callbacks.Complete)
                callbacks.Complete(completionLabel, transport.Object);
        }
        // Boarded members stay aboard until the next node takes over.
        if (node.Transport.Declared)
            RunTransport(input, callbacks, node, transport);
        return result;
    }

    if (node.Transport.Declared)
    {
        if (node.Transport.TimeoutMs
            && input.NowMs >= node.Runtime.StartedAtMs + node.Transport.TimeoutMs
            && !node.Runtime.FailureRecorded)
        {
            node.Runtime.FailureRecorded = true;
            if (callbacks.Fail)
                callbacks.Fail("native_transport_timeout");
            return result;
        }
        RunTransport(input, callbacks, node, transport);
    }
    if (node.Interaction.Declared)
        RunInteraction(input, callbacks, node, election);
    return result;
}
}
