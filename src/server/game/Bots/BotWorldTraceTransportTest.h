#ifndef TRINITY_BOT_WORLD_TRACE_TRANSPORT_TEST_H
#define TRINITY_BOT_WORLD_TRACE_TRANSPORT_TEST_H

#include "Define.h"
#include "Bots/BotWorldTraceExportCursor.h"

#include <string_view>

namespace BotWorldTraceTransportTest
{
constexpr char ProfileName[] = "trace_transport_10";
constexpr char PoolTag[] = "blackwing_descent_10n";
constexpr char Authority[] = "trace_transport_test_only_not_gameplay";
constexpr uint32 ActorCount = 10;
constexpr uint32 MinimumPressureCount = BotWorldTrace::PendingTraceCapacity + 1;
constexpr uint32 MaximumPressureCount = MinimumPressureCount + 63;

struct GateInput
{
    bool Active = false;
    std::string_view SelectedProfile;
    std::string_view ConfigName;
    std::string_view PoolTagFilter;
    uint32 TargetPopulation = 0;
    uint32 ActiveActorCount = 0;
    bool ValidationRouteEnabled = false;
    bool AllowCombat = false;
    bool AllowGrinding = false;
    bool AllowQuesting = false;
    bool AllowDungeons = false;
    bool AllowRaids = false;
    bool EnableProgression = false;
    uint64 AttemptId = 0;
    uint64 PressureAppliedAttemptId = 0;
    uint32 RequestedCount = 0;
};

inline char const* RejectionReason(GateInput const& input)
{
    if (!input.Active)
        return "runtime_inactive";
    if (input.SelectedProfile != ProfileName || input.ConfigName != ProfileName)
        return "trace_transport_test_profile_required";
    if (input.PoolTagFilter != PoolTag || input.TargetPopulation != ActorCount
        || input.ActiveActorCount != ActorCount)
        return "trace_transport_test_actor_contract_mismatch";
    if (input.ValidationRouteEnabled || input.AllowCombat || input.AllowGrinding
        || input.AllowQuesting || input.AllowDungeons || input.AllowRaids
        || input.EnableProgression)
        return "trace_transport_test_non_gameplay_gate_failed";
    if (!input.AttemptId)
        return "trace_transport_test_attempt_identity_missing";
    if (input.PressureAppliedAttemptId == input.AttemptId)
        return "trace_transport_test_pressure_already_applied";
    if (input.RequestedCount < MinimumPressureCount
        || input.RequestedCount > MaximumPressureCount)
        return "trace_transport_test_pressure_count_out_of_bounds";
    return nullptr;
}
}

#endif
