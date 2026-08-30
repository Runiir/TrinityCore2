#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldTraceTransportTest.h"

#include "Player.h"

#include <sstream>
#include <string>

void BotWorldPopulationMgr::AppendGenericRuntimeIdentityJson(std::ostringstream& json) const
{
    json << ",\"cohort_id\":\"" << JsonEscape(Cohort().Id)
         << "\",\"server_epoch\":" << _serverEpoch
         << ",\"attempt_id\":" << Cohort().AttemptId
         << ",\"profile_generation\":" << Cohort().PinnedProfileGeneration
         << ",\"profile_content_hash\":\"" << JsonEscape(Cohort().PinnedProfileContentHash)
         << "\",\"active_profile\":"
         << (Cohort().SelectedProfileName.empty()
             ? "null" : ("\"" + JsonEscape(Cohort().SelectedProfileName) + "\""));
}

std::string BotWorldPopulationMgr::ApplyTraceTransportTestPressureForCohort(
    std::string const& cohortId, uint32 requestedCount)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_trace_pressure", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = ApplyTraceTransportTestPressure(requestedCount);
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::ApplyTraceTransportTestPressure(uint32 requestedCount)
{
    auto receipt = [this, requestedCount](bool ok, char const* failureReason,
        WorldBotState const* state, std::string const& actorName, uint32 emittedCount,
        uint64 sequenceBefore, uint64 sequenceAfter)
    {
        std::ostringstream json;
        json << "{\"ok\":" << (ok ? "true" : "false")
             << ",\"action\":\"botauto_trace_pressure\"";
        AppendGenericRuntimeIdentityJson(json);
        json << ",\"authority\":\"" << BotWorldTraceTransportTest::Authority << "\""
             << ",\"actor_guid\":" << (state ? state->Guid.GetCounter() : 0)
             << ",\"actor_name\":\"" << JsonEscape(actorName) << "\""
             << ",\"requested_count\":" << requestedCount
             << ",\"emitted_count\":" << emittedCount
             << ",\"sequence_before\":" << sequenceBefore
             << ",\"sequence_after\":" << sequenceAfter
             << ",\"failure_reason\":"
             << (failureReason ? ("\"" + JsonEscape(failureReason) + "\"") : "null")
             << "}";
        return json.str();
    };

    BotWorldTraceTransportTest::GateInput const input{
        Cohort().Active,
        Cohort().SelectedProfileName,
        Cohort().Config.Name,
        Cohort().Config.PoolTagFilter,
        Cohort().Config.TargetPopulation,
        uint32(Party().Bots.size()),
        Cohort().Config.ValidationRouteEnable,
        Cohort().Config.AllowCombat,
        Cohort().Config.AllowGrinding,
        Cohort().Config.AllowQuesting,
        Cohort().Config.AllowDungeons,
        Cohort().Config.AllowRaids,
        Cohort().Config.EnableProgression,
        Cohort().AttemptId,
        Cohort().TraceTransportTestPressureAttemptId,
        requestedCount,
    };
    if (char const* reason = BotWorldTraceTransportTest::RejectionReason(input))
        return receipt(false, reason, nullptr, "", 0, 0, 0);

    WorldBotState& state = Party().Bots.front();
    Player* actor = GetLoadedBot(state);
    std::string const actorName = actor ? actor->GetName() : "";
    uint64 const sequenceBefore = state.TraceSequence;
    for (uint32 index = 0; index < requestedCount; ++index)
    {
        RecordDecisionTrace(state, "trace_transport_test_pressure",
            "append_inert_trace_record", nullptr, 0, "ok",
            BotWorldTraceTransportTest::Authority, false);
    }
    Cohort().TraceTransportTestPressureAttemptId = Cohort().AttemptId;
    uint64 const sequenceAfter = state.TraceSequence;
    return receipt(true, nullptr, &state, actorName, requestedCount,
        sequenceBefore, sequenceAfter);
}
