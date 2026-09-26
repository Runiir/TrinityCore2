#include "Bots/BotWorldPopulationMgrValidationRouteNativeRecovery.h"
#include "Bots/BotValidationRouteNativeRecovery.h"
#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"

#include "GameObject.h"
#include "Player.h"

#include <algorithm>
#include <string>
#include <vector>

namespace
{
using namespace BotValidationRouteNative;
using BotWorldPopulationMgrValidationRouteNative::Callbacks;
using BotWorldPopulationMgrValidationRouteNative::Input;
using BotWorldPopulationMgrValidationRouteNative::MemberInput;
using BotWorldPopulationMgrValidationRouteNative::RecoveryOps;
namespace Facts = BotWorldPopulationMgrValidationRouteNative::Facts;

void FailOnce(NodeRuntime& runtime, Callbacks const& callbacks, std::string const& reason)
{
    if (runtime.FailureRecorded)
        return;
    runtime.FailureRecorded = true;
    if (callbacks.Fail)
        callbacks.Fail(reason);
}

bool TimedOut(std::uint32_t timeoutMs, NodeRuntime const& runtime, std::uint64_t nowMs)
{
    return timeoutMs && nowMs >= runtime.StartedAtMs + timeoutMs;
}

// Every loaded member as a recovery ride sees it (its own runtime state).
std::vector<RecoveryMemberView> RecoveryViews(Input const& input, NodeRuntime const& runtime,
    TransportContract const& ride, GameObject const* platform)
{
    std::vector<RecoveryMemberView> views;
    for (MemberInput const& member : input.Members)
    {
        Player* bot = member.Bot;
        if (!bot)
            continue;
        RecoveryMemberView view;
        view.Guid = bot->GetGUID().GetRawValue();
        view.Alive = bot->IsAlive();
        view.OnRouteInstance = member.OnRouteInstance && bot->IsInWorld();
        view.Aboard = platform && Facts::OnTransport(bot, platform);
        auto const state = runtime.TransportMembers.find(view.Guid);
        bool const known = state != runtime.TransportMembers.end();
        view.InFlight = RecoveryMemberInFlight(known,
            known && ApproachPhaseInFlight(state->second.Approach),
            BotValidationRouteBoardingAction::NativeFallSplineActive(bot));
        view.Released = member.ReleasedThisAttempt;
        view.Boarded = known && state->second.Boarded;
        view.AtExit = !ride.ExitPoint.Valid || bot->GetExactDist(ride.ExitPoint.X,
            ride.ExitPoint.Y, ride.ExitPoint.Z) <= ride.ArrivalToleranceYards;
        view.InCombat = bot->IsInCombat();
        view.Z = bot->GetPositionZ();
        views.push_back(view);
    }
    return views;
}

// Every loaded member as a recovery wake sees it.
std::vector<RecoveryWakeView> WakeViews(Input const& input)
{
    std::vector<RecoveryWakeView> views;
    for (MemberInput const& member : input.Members)
    {
        Player* bot = member.Bot;
        if (!bot)
            continue;
        RecoveryWakeView view;
        view.Guid = bot->GetGUID().GetRawValue();
        view.Alive = bot->IsAlive();
        view.OnRouteInstance = member.OnRouteInstance && bot->IsInWorld();
        view.InCombat = bot->IsInCombat();
        view.DistanceToAnchor = bot->GetExactDist(input.AnchorX, input.AnchorY, input.AnchorZ);
        views.push_back(view);
    }
    return views;
}

// A wake's (or ride's) own failures and events carry the recovery prefix.
Callbacks RecoveryCallbacks(Callbacks const& callbacks, std::string const& id,
    std::string (*failure)(std::string const&, std::string const&))
{
    Callbacks prefixed = callbacks;
    prefixed.Complete = nullptr;
    prefixed.Fail = [fail = callbacks.Fail, id, failure](std::string const& reason)
    {
        if (fail)
            fail(failure(id, reason));
    };
    prefixed.Record = [record = callbacks.Record, id](
        std::string const& result, WorldObject* target, float value, std::uint32_t entry)
    {
        if (record)
            record("route_recovery:" + id + ":" + result, target, value, entry);
    };
    return prefixed;
}

// Recovery wakes (row field recovery_interaction) run after the rides and
// before the node's own contracts. After a wipe (or, on composition raid
// rows, an observed reset) at this node, with the encounter not engaged and
// the whole party back at the node, the first wake whose
// completion does not hold runs as an ordinary interaction contract: its
// elected owner walks to the target and interacts, bounded by the
// contract's attempts and timeout. The completion holding (or the encounter
// engaging) ends it. While the party is not yet assembled the wake names the
// member holding it, and fails the attempt after RecoveryAssemblyTimeoutMs.
// True while a wake owns the node, or after it failed.
bool RunRecoveryWakes(Input const& input, Callbacks const& callbacks, NodeContract& node,
    RecoveryOps const& ops)
{
    Player* const evaluator = Facts::SelectEvaluator(input.Members);
    std::vector<RecoveryWakeView> const views = WakeViews(input);
    bool const encounterEngaged = RecoveryEncounterEngaged(views);
    bool const assembled = evaluator && RecoveryPartyAssembled(views);
    for (RecoveryInteraction& wake : node.RecoveryInteractions)
    {
        NodeRuntime& runtime = wake.Runtime;
        bool const engaged = runtime.Started && runtime.Scope == input.Scope;
        if (!engaged && runtime.Started)
            runtime = NodeRuntime();
        if (engaged && runtime.FailureRecorded)
            return true;
        RecoveryTrigger const trigger = ObserveRecoveryTrigger(wake.Baseline, input.Scope,
            input.BossResetGeneration, input.CompositionRecovery, input.NowMs);
        bool const triggered = trigger == RecoveryTrigger::Triggered;
        if (trigger == RecoveryTrigger::None && !engaged)
            continue;
        OwnerElection const election = ops.Elect(wake.Interaction);
        bool const satisfied = evaluator && Facts::EvaluateCompletion(wake.Completion,
            evaluator, input.Members, election.Owner, runtime.Completion).Satisfied;
        // Without its target usable (Atramedes' bell is selectable only
        // before his intro; after it he respawns by himself) the wake waits.
        bool const ready = !wake.Ready.Declared || (evaluator && Facts::EvaluateCompletion(
            wake.Ready, evaluator, input.Members, election.Owner, wake.ReadyMemory).Satisfied);
        bool const waiting = !engaged && triggered && !encounterEngaged && !satisfied
            && (!assembled || !ready);
        RecoveryWakeHolder const holder = assembled ? RecoveryWakeHolder{ 0, "target_not_ready" }
            : RecoveryAssemblyHolder(views);
        if (RecoveryWaitTimedOut(wake.Waiting, waiting, input.NowMs))
        {
            runtime.Enter(input.Scope, input.NowMs);
            FailOnce(runtime, callbacks, RecoveryInteractionFailure(wake.NodeId,
                assembled ? std::string("target_not_ready")
                    : std::string("party_unassembled:") + holder.Reason + ":"
                        + std::to_string(holder.Guid)));
            return true;
        }
        if (waiting)
        {
            std::string const named = std::string(holder.Reason) + ":"
                + std::to_string(holder.Guid);
            if (wake.Waiting.Holder != named)
            {
                wake.Waiting.Holder = named;
                if (callbacks.Record)
                    callbacks.Record("route_recovery_interaction_waiting:" + wake.NodeId + ":"
                        + named, nullptr, 0.0f, wake.Interaction.Entry);
            }
        }
        RecoveryWakeStep const step = DecideRecoveryWake(triggered, engaged, encounterEngaged,
            satisfied, assembled && ready);
        RetireRecoveryTrigger(wake.Baseline, input.Scope, input.BossResetGeneration, trigger,
            step, satisfied, encounterEngaged);
        switch (step)
        {
            case RecoveryWakeStep::Idle:
                continue;
            case RecoveryWakeStep::Complete:
                runtime = NodeRuntime();
                if (callbacks.Record)
                    callbacks.Record("route_recovery_interaction_complete:" + wake.NodeId,
                        nullptr, 0.0f, wake.Interaction.Entry);
                continue;
            case RecoveryWakeStep::Engage:
                runtime.Enter(input.Scope, input.NowMs);
                if (callbacks.Record)
                    callbacks.Record("route_recovery_interaction_engaged:" + wake.NodeId,
                        nullptr, 0.0f, wake.Interaction.Entry);
                break;
            case RecoveryWakeStep::Wake:
                break;
        }
        // The boss cannot be pulled without its wake: a wake that does not
        // complete in time fails the attempt at once.
        if (TimedOut(wake.Interaction.TimeoutMs, runtime, input.NowMs))
        {
            FailOnce(runtime, callbacks, RecoveryInteractionFailure(wake.NodeId,
                "native_interaction_timeout"));
            return true;
        }
        auto const self = std::find_if(input.Members.begin(), input.Members.end(),
            [&input](MemberInput const& member) { return member.Bot == input.Bot; });
        if (self == input.Members.end() || !self->OnRouteInstance || !input.Bot->IsAlive())
            return true;
        ops.Interact(RecoveryCallbacks(callbacks, wake.NodeId, &RecoveryInteractionFailure),
            wake.Interaction, runtime, election);
        return true;
    }
    return false;
}
}

namespace BotWorldPopulationMgrValidationRouteNative
{
// Recovery rides (row field recovery_transport) run before the node's own
// contracts. The first applicable ride some living member needs (back at its
// boarding end after a wipe's runback) runs as an ordinary transport
// contract: members at the boarding end board, ride and walk to its exit
// point, members already below hold. Nobody needing it ends the ride and the
// next applies. Recovery wakes follow (RunRecoveryWakes). The node's own
// runtime (and its timeouts) starts only after.
// True while a ride or wake owns the node, or after one failed the attempt.
bool RunRecovery(Input const& input, Callbacks const& callbacks, NodeContract& node,
    RecoveryOps const& ops)
{
    Player* const evaluator = Facts::SelectEvaluator(input.Members);
    for (RecoveryTransit& transit : node.Recovery)
    {
        TransportContract const& ride = transit.Transport;
        NodeRuntime& runtime = transit.Runtime;
        bool const engaged = runtime.Started && runtime.Scope == input.Scope;
        if (!engaged && runtime.Started)
            runtime = NodeRuntime();
        if (engaged && runtime.FailureRecorded)
            return true;
        float boardZ = 0.0f;
        float exitZ = 0.0f;
        if (!evaluator || !RecoveryLevels(ride, boardZ, exitZ))
        {
            if (engaged)
                return true;
            continue;
        }
        Facts::TransportTarget const transport =
            Facts::ResolveTransport(evaluator, ride.Entry, ride.SpawnId);
        std::vector<RecoveryMemberView> const views =
            RecoveryViews(input, runtime, ride, transport.Object);
        bool const applies = RecoveryApplies(ride, input.AnchorZ);
        switch (DecideRecoveryRide(applies, engaged, applies && RideNeeded(views, boardZ, exitZ),
            RecoveryMayEngage(views, boardZ, exitZ)))
        {
            case RecoveryStep::Idle:
                continue;
            case RecoveryStep::Complete:
                runtime = NodeRuntime();
                if (callbacks.Record)
                    callbacks.Record("route_recovery_complete:" + transit.NodeId, nullptr,
                        0.0f, ride.Entry);
                continue;
            case RecoveryStep::Engage:
                runtime.Enter(input.Scope, input.NowMs);
                if (callbacks.Record)
                    callbacks.Record("route_recovery_engaged:" + transit.NodeId, nullptr,
                        0.0f, ride.Entry);
                break;
            case RecoveryStep::Ride:
                break;
        }
        // The party cannot reach the node without this ride: no platform, or
        // a ride that does not finish in time, fails the attempt at once.
        if (!transport.Object)
        {
            FailOnce(runtime, callbacks, RecoveryFailure(transit.NodeId,
                transport.Fact.Ambiguous ? "transport_ambiguous" : "transport_missing"));
            return true;
        }
        if (TimedOut(ride.TimeoutMs, runtime, input.NowMs))
        {
            FailOnce(runtime, callbacks, RecoveryFailure(transit.NodeId,
                "native_transport_timeout"));
            return true;
        }
        // A member back at the boarding end after an earlier ride rides afresh.
        for (RecoveryMemberView const& view : views)
        {
            auto const state = runtime.TransportMembers.find(view.Guid);
            if (state != runtime.TransportMembers.end()
                && StaleRiderState(view, state->second, boardZ, exitZ))
                runtime.TransportMembers.erase(state);
        }
        auto const self = std::find_if(views.begin(), views.end(),
            [&input](RecoveryMemberView const& view)
            { return view.Guid == input.Bot->GetGUID().GetRawValue(); });
        if (self == views.end() || !self->Alive || !self->OnRouteInstance)
            return true;
        if (!MemberNeedsRide(*self, boardZ, exitZ))
        {
            ops.Hold("route_recovery_waiting_for_party");
            return true;
        }
        // The ride's own failures and events carry the recovery prefix.
        Callbacks const ridden = RecoveryCallbacks(callbacks, transit.NodeId, &RecoveryFailure);
        ops.Ride(ridden, ride, runtime, transport);
        return true;
    }
    return RunRecoveryWakes(input, callbacks, node, ops);
}
}
