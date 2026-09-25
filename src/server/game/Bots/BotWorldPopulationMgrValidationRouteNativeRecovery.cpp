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
        view.InFlight = BotValidationRouteBoardingAction::NativeFallInProgress(bot)
            || (known && ApproachPhaseInFlight(state->second.Approach));
        view.Boarded = known && state->second.Boarded;
        view.AtExit = !ride.ExitPoint.Valid || bot->GetExactDist(ride.ExitPoint.X,
            ride.ExitPoint.Y, ride.ExitPoint.Z) <= ride.ArrivalToleranceYards;
        view.InCombat = bot->IsInCombat();
        view.Z = bot->GetPositionZ();
        views.push_back(view);
    }
    return views;
}
}

namespace BotWorldPopulationMgrValidationRouteNative
{
// Recovery rides (row field recovery_transport) run before the node's own
// contracts. The first applicable ride some living member needs (back at its
// boarding end after a wipe's runback) runs as an ordinary transport
// contract: members at the boarding end board, ride and walk to its exit
// point, members already below hold. Nobody needing it ends the ride and the
// next applies. The node's own runtime (and its timeouts) starts only after.
// True while a ride owns the node, or after it failed the attempt.
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
        Callbacks ridden = callbacks;
        ridden.Complete = nullptr;
        ridden.Fail = [fail = callbacks.Fail, id = transit.NodeId](std::string const& reason)
        {
            if (fail)
                fail(RecoveryFailure(id, reason));
        };
        ridden.Record = [record = callbacks.Record, id = transit.NodeId](
            std::string const& result, WorldObject* target, float value, std::uint32_t entry)
        {
            if (record)
                record("route_recovery:" + id + ":" + result, target, value, entry);
        };
        ops.Ride(ridden, ride, runtime, transport);
        return true;
    }
    return false;
}
}
