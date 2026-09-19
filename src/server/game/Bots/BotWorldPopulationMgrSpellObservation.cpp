#include "Bots/BotWorldPopulationMgr.h"

#include "GameTime.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "Unit.h"

#include <chrono>
#include <sstream>
#include <string>
#include <utility>

namespace
{
uint64 NativeObservationNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

char const* SpellStateName(uint32 state)
{
    switch (SpellState(state))
    {
        case SPELL_STATE_NULL: return "null";
        case SPELL_STATE_PREPARING: return "preparing";
        case SPELL_STATE_LAUNCHED: return "launched";
        case SPELL_STATE_FINISHED: return "finished";
        case SPELL_STATE_IDLE: return "idle";
        case SPELL_STATE_CHANNELING: return "channeling";
        default: return "unknown";
    }
}

void AppendNullableBool(std::ostringstream& json, bool available, bool value)
{
    if (available)
        json << (value ? "true" : "false");
    else
        json << "null";
}
}

std::string BotWorldPopulationMgr::BuildNativeSpellScopeJson(
    Player const* caster) const
{
    std::ostringstream scope;
    scope << "{\"server_epoch\":" << _serverEpoch
        << ",\"cohort_id\":\"" << JsonEscape(Cohort().Id) << "\""
        << ",\"attempt_id\":" << Cohort().AttemptId
        << ",\"wipe_generation\":" << Cohort().Raid.WipeGeneration
        << ",\"route_node_id\":\""
        << JsonEscape(Cohort().Config.ValidationRouteNodeId) << "\""
        << ",\"route_generation\":" << Party().ValidationRouteGeneration
        << ",\"map_id\":" << (caster ? caster->GetMapId() : 0)
        << ",\"instance_id\":" << (caster ? caster->GetInstanceId() : 0)
        << "}";
    return scope.str();
}

void BotWorldPopulationMgr::NotifyNativeSpellPrepared(Spell* spell)
{
    if (!spell)
        return;

    Player* caster = spell->GetCaster() ? spell->GetCaster()->ToPlayer() : nullptr;
    CohortScope scope = caster ? ScopeCallbackCohort(caster) : CohortScope(nullptr);
    std::string sourceScope = scope
        ? BuildNativeSpellScopeJson(caster) : std::string();
    uint64 const observedAtMs = NativeObservationNowMs();
    spell->ObserveNativeCastPrepared(std::move(sourceScope), observedAtMs);
    if (!scope || !caster)
        return;

    SpellNativeCastObservation const& observation =
        spell->GetNativeCastObservation();
    std::ostringstream raw;
    raw << "{\"schema\":\"native_spell_prepared_v1\",\"observed_at_ms\":"
        << observedAtMs
        << ",\"caster_guid\":" << observation.CasterGuid.GetRawValue()
        << ",\"original_caster_guid\":"
        << observation.OriginalCasterGuid.GetRawValue()
        << ",\"spell_id\":" << observation.SpellId
        << ",\"cast_instance_id\":" << observation.InstanceId
        << ",\"cast_instance_correlation\":\"exact\""
        << ",\"submitted_target_guid\":"
        << observation.SubmittedTargetGuid.GetRawValue()
        << ",\"source_scope\":"
        << (observation.SourceScopeJson.empty() ? "null"
                                                : observation.SourceScopeJson)
        << "}";

    auto record = [&](std::vector<WorldBotState>& states)
    {
        for (WorldBotState& state : states)
        {
            if (state.Guid != caster->GetGUID())
                continue;
            uint64 const previousSequence = state.TraceSequence;
            RecordDecisionTrace(state, "native_callback", "native_spell_prepared",
                nullptr, 0, "native_prepare_accepted", "native_prepare_accepted",
                false);
            if (state.TraceSequence != previousSequence
                && !state.DecisionTrace.empty()
                && state.DecisionTrace.back().Sequence == state.TraceSequence
                && state.DecisionTrace.back().Action == "native_spell_prepared")
                state.DecisionTrace.back().NativeSpellPreparedJson = raw.str();
            return true;
        }
        return false;
    };
    if (!record(Party().Bots))
        record(Party().CalibrationBots);
}

void BotWorldPopulationMgr::NotifyNativeSpellCastResult(Spell const* spell,
    uint32 result)
{
    if (spell)
        spell->ObserveNativeCastResult(result);
}

void BotWorldPopulationMgr::NotifyNativeSpellUpdate(Spell* spell,
    char const* source, uint32 movementResult)
{
    if (spell)
        spell->ObserveNativeCastUpdate(source, movementResult);
}

void BotWorldPopulationMgr::NotifyNativeSpellCancelled(Spell* spell)
{
    if (spell)
        spell->ObserveNativeCastCancelled();
}

void BotWorldPopulationMgr::NotifyNativeSpellFinishing(Spell* spell,
    bool success)
{
    if (!spell)
        return;
    Player* caster = spell->GetCaster() ? spell->GetCaster()->ToPlayer() : nullptr;
    CohortScope scope = caster ? ScopeCallbackCohort(caster) : CohortScope(nullptr);
    spell->ObserveNativeCastFinishing(success,
        scope ? BuildNativeSpellScopeJson(caster) : std::string(),
        NativeObservationNowMs());
}

void BotWorldPopulationMgr::RecordNativeSpellFinishObservation(
    Spell const* spell, bool success)
{
    if (!spell || !spell->GetSpellInfo())
        return;
    Player* caster = spell->GetCaster() ? spell->GetCaster()->ToPlayer() : nullptr;
    if (!caster)
        return;
    CohortScope scope = ScopeCallbackCohort(caster);
    if (!scope)
        return;

    SpellNativeCastObservation const& observation =
        spell->GetNativeCastObservation();
    std::ostringstream raw;
    raw << "{\"schema\":\"native_spell_finish_v2\",\"observed_at_ms\":"
        << observation.FinishedAtMs
        << ",\"caster_guid\":" << observation.CasterGuid.GetRawValue()
        << ",\"original_caster_guid\":"
        << observation.OriginalCasterGuid.GetRawValue()
        << ",\"spell_id\":" << observation.SpellId
        << ",\"cast_instance_id\":" << observation.InstanceId
        << ",\"terminal_ordinal\":" << observation.TerminalOrdinal
        << ",\"cast_instance_correlation\":\"exact\""
        << ",\"prepared\":" << (observation.Prepared ? "true" : "false")
        << ",\"prepared_at_ms\":"
        << (observation.Prepared ? std::to_string(observation.PreparedAtMs) : "null")
        << ",\"success\":" << (success ? "true" : "false")
        << ",\"submitted_target_guid\":"
        << observation.SubmittedTargetGuid.GetRawValue()
        << ",\"terminal_target_guid\":"
        << observation.TerminalTargetGuid.GetRawValue()
        << ",\"terminal_target_present\":";
    AppendNullableBool(raw, observation.TerminalTargetPresenceAvailable,
        observation.TerminalTargetPresent);
    raw << ",\"terminal_target_alive\":";
    AppendNullableBool(raw, observation.TerminalTargetAliveAvailable,
        observation.TerminalTargetAlive);
    raw << ",\"terminal_target_attackable\":";
    AppendNullableBool(raw, observation.TerminalTargetAttackabilityAvailable,
        observation.TerminalTargetAttackable);
    raw << ",\"prior_native_state\":" << observation.PriorState
        << ",\"prior_native_state_name\":\""
        << SpellStateName(observation.PriorState) << "\""
        << ",\"terminal_source\":\""
        << JsonEscape(observation.TerminalSource) << "\""
        << ",\"cancellation_owner\":\""
        << JsonEscape(observation.CancellationOwner) << "\""
        << ",\"cancellation_owner_available\":"
        << (observation.CancellationOwnerAvailable ? "true" : "false")
        << ",\"last_observed_native_failure_result\":"
        << (observation.NativeFailureResultAvailable
                ? std::to_string(observation.LastNativeFailureResult) : "null")
        << ",\"movement_check_result\":"
        << (observation.MovementCheckAvailable
                ? std::to_string(observation.MovementCheckResult) : "null")
        << ",\"unsuccessful_reason\":"
        << (success ? "null" : (observation.TerminalSource == "finish"
                ? "\"unavailable\"" : "\"observed_terminal_source\""))
        << ",\"source_scope\":"
        << (observation.SourceScopeJson.empty() ? "null"
                                                : observation.SourceScopeJson)
        << ",\"terminal_scope\":"
        << (observation.TerminalScopeJson.empty() ? "null"
                                                  : observation.TerminalScopeJson)
        << "}";

    auto record = [&](std::vector<WorldBotState>& states)
    {
        for (WorldBotState& state : states)
        {
            if (state.Guid != caster->GetGUID())
                continue;
            uint64 const previousSequence = state.TraceSequence;
            RecordDecisionTrace(state, "native_callback", "native_spell_finished",
                nullptr, 0, success ? "native_finish_success"
                                    : "native_finish_unsuccessful",
                success ? "native_finish_exact" : "native_finish_observed", false);
            if (state.TraceSequence != previousSequence
                && !state.DecisionTrace.empty()
                && state.DecisionTrace.back().Sequence == state.TraceSequence
                && state.DecisionTrace.back().Action == "native_spell_finished")
                state.DecisionTrace.back().NativeSpellFinishJson = raw.str();
            return true;
        }
        return false;
    };
    if (!record(Party().Bots))
        record(Party().CalibrationBots);
}
