#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotLongTermProgressionBrain.h"
#include "CellImpl.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <sstream>
#include <string>
#include <vector>

namespace
{
constexpr uint32 DecisionFingerprintPersistHeartbeatMs = 5000;

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

void BotWorldPopulationMgr::PersistDecisionFingerprintDelta(WorldBotState& state, uint32 repeatDelta, uint32 failureDelta) const
{
    if (state.Guid.IsEmpty() || !state.DecisionFingerprintInitialized || (!repeatDelta && !failureDelta))
        return;

    std::ostringstream metadata;
    metadata << "{\"quest_phase\":\"" << JsonEscape(state.QuestWork.Phase)
             << "\",\"objective_type\":\"" << JsonEscape(state.QuestWork.ObjectiveType)
             << "\",\"last_no_progress_reason\":\"" << JsonEscape(state.LastNoProgressReason)
             << "\",\"last_no_quest_reason\":\"" << JsonEscape(state.LastNoQuestReason)
             << "\",\"recommended_balance_mode\":\"" << JsonEscape(state.LastRecommendedBalanceMode)
             << "\",\"repeat_count\":" << state.LastDecisionFingerprintRepeatCount
             << ",\"failure_count\":" << state.LastDecisionFingerprintFailureCount
             << ",\"consecutive_same_decision_count\":" << state.ConsecutiveSameDecisionCount
             << ",\"idle_decision_repeat_count\":" << state.IdleDecisionRepeatCount
             << ",\"target_churn_count\":" << state.TargetChurnCount
             << ",\"loop_guardrail_count\":" << state.LoopGuardrailCount
             << ",\"last_loop_guardrail_action\":\"" << JsonEscape(state.LastLoopGuardrailAction)
             << "\",\"last_loop_guardrail_reason\":\"" << JsonEscape(state.LastLoopGuardrailReason)
             << "\",\"last_recovery_mode\":\"" << JsonEscape(state.LastRecoveryMode)
             << "\",\"last_recovery_result\":\"" << JsonEscape(state.LastRecoveryResult) << "\""
             << ",\"fingerprint_source\":\"decision_context_v1\"}";

    std::string escapedSituation = state.DecisionFingerprintSituation.empty() ? "idle" : state.DecisionFingerprintSituation;
    std::string escapedAction = state.DecisionFingerprintAction.empty() ? "wait" : state.DecisionFingerprintAction;
    std::string escapedActivity = state.DecisionFingerprintActivity.empty() ? "experiment_exploration" : state.DecisionFingerprintActivity;
    std::string result = state.DecisionFingerprintResult.empty() ? "ok" : state.DecisionFingerprintResult;
    std::string metadataJson = metadata.str();
    CharacterDatabase.EscapeString(escapedSituation);
    CharacterDatabase.EscapeString(escapedAction);
    CharacterDatabase.EscapeString(escapedActivity);
    CharacterDatabase.EscapeString(result);
    CharacterDatabase.EscapeString(metadataJson);

    uint32 const questId = state.DecisionFingerprintQuestId;
    uint32 const clusterId = state.DecisionFingerprintClusterId;
    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_decision_fingerprints "
        "(bot_guid, fingerprint_hash, situation_type, action, activity, quest_id, cluster_id, map_id, zone_id, area_id, repeat_count, failure_count, last_result, first_seen_at, last_seen_at, metadata_json) "
        "VALUES (%u, %u, '%s', '%s', '%s', %u, %u, %u, %u, %u, %u, %u, '%s', NOW(), NOW(), '%s') "
        "ON DUPLICATE KEY UPDATE repeat_count = repeat_count + VALUES(repeat_count), failure_count = failure_count + VALUES(failure_count), last_result = VALUES(last_result), last_seen_at = NOW(), metadata_json = VALUES(metadata_json)",
        state.Guid.GetCounter(), state.LastDecisionFingerprintHash, escapedSituation.c_str(), escapedAction.c_str(), escapedActivity.c_str(),
        questId, clusterId, state.DecisionFingerprintMapId, state.DecisionFingerprintZoneId, state.DecisionFingerprintAreaId,
        repeatDelta, failureDelta, result.c_str(), metadataJson.c_str());
    state.LastDecisionFingerprintPersistedRepeatCount = state.LastDecisionFingerprintRepeatCount;
    state.LastDecisionFingerprintPersistedFailureCount = state.LastDecisionFingerprintFailureCount;
    state.LastDecisionFingerprintPersistMs = NowMs();
}

void BotWorldPopulationMgr::FlushDecisionFingerprintMemory(WorldBotState& state) const
{
    if (state.Guid.IsEmpty() || !state.DecisionFingerprintInitialized)
        return;

    // A reset can intentionally discard a stream, but a normal stop must
    // never lose its in-memory tail. Guard subtraction in case an older
    // caller left a stale baseline behind.
    uint32 const repeatDelta = state.LastDecisionFingerprintRepeatCount >= state.LastDecisionFingerprintPersistedRepeatCount
        ? state.LastDecisionFingerprintRepeatCount - state.LastDecisionFingerprintPersistedRepeatCount : 0;
    uint32 const failureDelta = state.LastDecisionFingerprintFailureCount >= state.LastDecisionFingerprintPersistedFailureCount
        ? state.LastDecisionFingerprintFailureCount - state.LastDecisionFingerprintPersistedFailureCount : 0;
    PersistDecisionFingerprintDelta(state, repeatDelta, failureDelta);
}

void BotWorldPopulationMgr::FlushPendingDecisionFingerprintMemory()
{
    for (WorldBotState& state : Party().Bots)
        FlushDecisionFingerprintMemory(state);
}

void BotWorldPopulationMgr::RecordDecisionFingerprintMemory(WorldBotState& state, Player* bot, char const* situation, char const* action, BotActivityScore const& chosenActivity, bool failure) const
{
    if (!bot)
        return;

    std::string situationText = situation && *situation ? situation : "idle";
    std::string actionText = action && *action ? action : "wait";
    std::string activityText = BotLongTermProgressionBrain::ToString(chosenActivity.Activity);
    uint32 questId = state.LastDecisionQuestId ? state.LastDecisionQuestId : state.QuestWork.ActiveQuestId;
    uint32 clusterId = state.ActiveQuestClusterId;
    std::ostringstream fingerprint;
    fingerprint << situationText << "|" << actionText << "|" << activityText << "|" << questId << "|" << clusterId
                << "|" << bot->GetMapId() << "|" << bot->GetZoneId() << "|" << bot->GetAreaId()
                << "|" << state.QuestWork.Phase << "|" << state.QuestWork.ObjectiveType;
    uint32 fingerprintHash = FeatureSchemaHash(fingerprint.str());
    bool const fingerprintChanged = !state.DecisionFingerprintInitialized
        || state.LastDecisionFingerprintHash != fingerprintHash;
    // Track the immediately preceding result, rather than the cumulative
    // failure counter, so every success->failure transition is persisted even
    // after this fingerprint has already accumulated older failures.
    bool const failureEdge = failure && (fingerprintChanged || !state.LastDecisionFingerprintFailure);
    if (fingerprintChanged)
    {
        // Preserve the previous stream's unsent tail before replacing its
        // hash, counters, and persisted baseline with the new identity.
        // This is deliberately one bounded upsert only on a fingerprint edge;
        // steady-state decisions retain the existing heartbeat behavior.
        FlushDecisionFingerprintMemory(state);
        state.LastDecisionFingerprintHash = fingerprintHash;
        state.LastDecisionFingerprintRepeatCount = 0;
        state.LastDecisionFingerprintFailureCount = 0;
        state.LastDecisionFingerprintPersistedRepeatCount = 0;
        state.LastDecisionFingerprintPersistedFailureCount = 0;
        if (QueryResult existing = CharacterDatabase.PQuery("SELECT repeat_count, failure_count FROM bot_memory_decision_fingerprints WHERE bot_guid = %u AND fingerprint_hash = %u", bot->GetGUID().GetCounter(), fingerprintHash))
        {
            Field* fields = existing->Fetch();
            state.LastDecisionFingerprintRepeatCount = fields[0].GetUInt32();
            state.LastDecisionFingerprintFailureCount = fields[1].GetUInt32();
            state.LastDecisionFingerprintPersistedRepeatCount = state.LastDecisionFingerprintRepeatCount;
            state.LastDecisionFingerprintPersistedFailureCount = state.LastDecisionFingerprintFailureCount;
        }
        state.DecisionFingerprintSituation = situationText;
        state.DecisionFingerprintAction = actionText;
        state.DecisionFingerprintActivity = activityText;
        state.DecisionFingerprintResult = "ok";
        state.DecisionFingerprintQuestId = questId;
        state.DecisionFingerprintClusterId = clusterId;
        state.DecisionFingerprintMapId = bot->GetMapId();
        state.DecisionFingerprintZoneId = bot->GetZoneId();
        state.DecisionFingerprintAreaId = bot->GetAreaId();
    }

    ++state.LastDecisionFingerprintRepeatCount;
    if (failure)
        ++state.LastDecisionFingerprintFailureCount;
    state.DecisionFingerprintInitialized = true;
    state.LastDecisionFingerprintFailure = failure;
    state.DecisionFingerprintResult = failure ? "failed" : "ok";

    uint64 const nowMs = NowMs();
    bool const heartbeatDue = !state.LastDecisionFingerprintPersistMs
        || nowMs - state.LastDecisionFingerprintPersistMs >= DecisionFingerprintPersistHeartbeatMs;
    if (!fingerprintChanged && !failureEdge && !heartbeatDue)
        return;

    uint32 const repeatDelta = state.LastDecisionFingerprintRepeatCount >= state.LastDecisionFingerprintPersistedRepeatCount
        ? state.LastDecisionFingerprintRepeatCount - state.LastDecisionFingerprintPersistedRepeatCount : 0;
    uint32 const failureDelta = state.LastDecisionFingerprintFailureCount >= state.LastDecisionFingerprintPersistedFailureCount
        ? state.LastDecisionFingerprintFailureCount - state.LastDecisionFingerprintPersistedFailureCount : 0;
    if (!repeatDelta && !failureDelta)
    {
        state.LastDecisionFingerprintPersistMs = nowMs;
        return;
    }

    // The helper uses the stream-owned result and current counters, updating
    // the persisted baseline only after the delta upsert succeeds.
    PersistDecisionFingerprintDelta(state, repeatDelta, failureDelta);
}

void BotWorldPopulationMgr::RecordDecisionTrace(WorldBotState& state, char const* situation, char const* action, Unit const* target, uint32 questId, char const* result, char const* reasonCode, bool coalesceRepeatable)
{
    if (coalesceRepeatable && !state.DecisionTrace.empty())
    {
        WorldBotState::DecisionTraceEntry& previous = state.DecisionTrace.back();
        uint64 const nowMs = NowMs();
        bool const sameDecision = previous.Situation == (situation ? situation : "unknown")
            && previous.Action == (action ? action : "wait")
            && previous.TargetGuid == (target ? target->GetGUID().GetCounter() : 0)
            && previous.Result == (result ? result : "ok")
            && previous.ReasonCode == (reasonCode ? reasonCode : "")
            && previous.RouteNodeId == Cohort().Config.ValidationRouteNodeId
            && previous.RouteGeneration == state.ValidationRouteGeneration;
        if (sameDecision && nowMs >= previous.TimestampMs
            && nowMs - previous.TimestampMs < 5000)
        {
            ++previous.SuppressedRepeatableDecisionCount;
            return;
        }
    }

    WorldBotState::DecisionTraceEntry entry;
    entry.TimestampMs = NowMs();
    entry.Sequence = ++state.TraceSequence;
    entry.DecisionSequence = state.Sequence;
    entry.Situation = situation ? situation : "unknown";
    entry.Action = action ? action : "wait";
    entry.RouteNodeId = Cohort().Config.ValidationRouteNodeId;
    entry.RouteGeneration = state.ValidationRouteGeneration;
    entry.QuestId = questId;
    entry.TargetGuid = target ? target->GetGUID().GetCounter() : 0;
    if (state.QuestRouteDestination.Valid)
    {
        entry.DestinationMapId = state.QuestRouteDestination.MapId;
        entry.DestinationX = state.QuestRouteDestination.X;
        entry.DestinationY = state.QuestRouteDestination.Y;
        entry.DestinationZ = state.QuestRouteDestination.Z;
    }
    else if (state.QuestSearchDestination.Valid)
    {
        entry.DestinationMapId = state.QuestSearchDestination.MapId;
        entry.DestinationX = state.QuestSearchDestination.X;
        entry.DestinationY = state.QuestSearchDestination.Y;
        entry.DestinationZ = state.QuestSearchDestination.Z;
    }
    else if (state.ActivePathValid)
    {
        entry.DestinationX = state.ActivePathToX;
        entry.DestinationY = state.ActivePathToY;
        entry.DestinationZ = state.ActivePathToZ;
    }
    entry.Result = result ? result : "ok";
    entry.ReasonCode = reasonCode ? reasonCode : "";
    entry.FingerprintHash = state.LastDecisionFingerprintHash;
    entry.FingerprintRepeatCount = state.LastDecisionFingerprintRepeatCount;
    entry.FingerprintFailureCount = state.LastDecisionFingerprintFailureCount;
    entry.ConsecutiveSameDecisionCount = state.ConsecutiveSameDecisionCount;
    entry.IdleDecisionRepeatCount = state.IdleDecisionRepeatCount;
    entry.TargetChurnCount = state.TargetChurnCount;
    entry.SuppressedRepeatableEventCount = state.PendingTraceSuppressedRepeatableEventCount;
    state.PendingTraceSuppressedRepeatableEventCount = 0;
    if (Player* bot = GetLoadedBot(state); bot && bot->IsInWorld())
    {
        entry.TankThreatAuraActive = GetDungeonRole(bot) != "tank"
            || bot->getClass() != CLASS_PALADIN || bot->HasAura(25780);
        if (Pet* pet = bot->GetPet())
            entry.PetAlive = pet->IsAlive();
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 45.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 45.0f);
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!creature || !creature->IsAlive() || !creature->GetHealth()
                || !bot->IsValidAttackTarget(creature) || (!creature->IsInCombat() && !creature->GetVictim()))
                continue;
            Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
            if (!victim || (bot->GetGroup() ? victim->GetGroup() != bot->GetGroup() : victim != bot))
                continue;
            ++entry.EngagedHostileCount;
            entry.EngagedHostileGuids.push_back(creature->GetGUID().GetCounter());
            std::string victimRole = victim ? GetDungeonRole(victim) : "";
            if (victimRole == "tank")
            {
                ++entry.TankOwnedHostileCount;
                entry.TankOwnedHostileGuids.push_back(creature->GetGUID().GetCounter());
            }
            else if (victimRole == "healer")
            {
                ++entry.HealerTargetingHostileCount;
                entry.HealerTargetingHostileGuids.push_back(creature->GetGUID().GetCounter());
            }
        }
        std::sort(entry.EngagedHostileGuids.begin(), entry.EngagedHostileGuids.end());
        std::sort(entry.TankOwnedHostileGuids.begin(), entry.TankOwnedHostileGuids.end());
        std::sort(entry.HealerTargetingHostileGuids.begin(), entry.HealerTargetingHostileGuids.end());
    }
    entry.LoopGuardrailAction = state.LastLoopGuardrailAction;
    entry.LoopGuardrailReason = state.LastLoopGuardrailReason;
    entry.RecoveryMode = state.LastRecoveryMode;
    entry.RecoveryResult = state.LastRecoveryResult;
    entry.NativePathFloor = state.LastNativePathFloorObservation;
    entry.BlockedEpisodeId = state.BlockedEpisodeId;
    entry.BlockedFirstReason = state.BlockedFirstReason;
    entry.BlockedCurrentReason = state.BlockedReason;
    entry.BlockedResolution = state.BlockedResolution;
    entry.BlockedResolvedBy = state.BlockedResolvedBy;
    entry.CombatAttempt = state.LastCombatAttempt;
    entry.RouteProgress = state.LastRouteProgress;
    state.DecisionTrace.push_back(entry);
    while (state.DecisionTrace.size() > 128)
        state.DecisionTrace.pop_front();
}
