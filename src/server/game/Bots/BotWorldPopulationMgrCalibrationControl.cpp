#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotMgr.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Map.h"
#include "MapManager.h"
#include "TemporarySummon.h"

#include <chrono>
#include <limits>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

std::string BotWorldPopulationMgr::StartCombatCalibration(std::string const& mode,
    std::string const& targetSpec, uint32 seed)
{
    if (!Cohort().Active || Cohort().RuntimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy)
        return "{\"ok\":false,\"action\":\"botauto_calibrate_start\",\"failure_reason\":\"autonomy_not_active\"}";
    if (!Party().Bots.empty() || Cohort().Config.TargetPopulation != 0)
        return "{\"ok\":false,\"action\":\"botauto_calibrate_start\",\"failure_reason\":\"fixture_population_not_isolated\"}";

    static std::set<std::string> const SupportedModes = {
        "single_target_300", "aoe_300", "tank_threat_300", "healer_controlled_damage_300"
    };
    if (SupportedModes.find(mode) == SupportedModes.end())
        return "{\"ok\":false,\"action\":\"botauto_calibrate_start\",\"failure_reason\":\"unsupported_mode\"}";
    if (targetSpec.empty())
        return "{\"ok\":false,\"action\":\"botauto_calibrate_start\",\"failure_reason\":\"target_spec_required\"}";

    std::string escapedTargetSpec = targetSpec;
    CharacterDatabase.EscapeString(escapedTargetSpec);
    QueryResult targetResult = CharacterDatabase.PQuery(
        "SELECT cbp.role, cbp.in_use FROM character_bot_pool cbp INNER JOIN characters c ON c.guid = cbp.guid "
        "WHERE cbp.enabled = 1 AND c.level = 85 AND cbp.experiment_tags = 'all_spec_candidate_pool' "
        "AND cbp.class_spec = '%s' ORDER BY cbp.guid LIMIT 1", escapedTargetSpec.c_str());
    if (!targetResult)
        return "{\"ok\":false,\"action\":\"botauto_calibrate_start\",\"failure_reason\":\"unknown_target_spec\"}";

    Field* targetFields = targetResult->Fetch();
    std::string const targetRole = targetFields[0].GetString();
    if (targetFields[1].GetBool())
        return "{\"ok\":false,\"action\":\"botauto_calibrate_start\",\"failure_reason\":\"target_unavailable\"}";
    bool const roleMismatch = (mode == "healer_controlled_damage_300" && targetRole != "healer")
        || (mode == "tank_threat_300" && targetRole != "tank")
        || ((mode == "single_target_300" || mode == "aoe_300") && targetRole == "healer");
    if (roleMismatch)
        return "{\"ok\":false,\"action\":\"botauto_calibrate_start\",\"failure_reason\":\"mode_role_mismatch\"}";

    if (Cohort().CalibrationStopping)
        return "{\"ok\":false,\"action\":\"botauto_calibrate_start\",\"failure_reason\":\"calibration_stopping\"}";
    if (Cohort().CalibrationActive || !Party().CalibrationBots.empty())
        StopCombatCalibration();

    Cohort().RuntimeMode = BotWorldRuntimeMode::CalibrationFixture;
    Cohort().Metrics.Mode = BotWorldRuntimeMode::CalibrationFixture;
    Cohort().NonCertifyingAssistance = true;
    Cohort().CalibrationActive = true;
    Cohort().CalibrationAoePhase = mode == "aoe_300" || mode == "tank_threat_300";
    Cohort().CalibrationWindowComplete = false;
    Cohort().CalibrationFailureReason.clear();
    Cohort().CalibrationMode = mode;
    Cohort().CalibrationTargetSpec = targetSpec;
    Cohort().CalibrationSeed = seed ? seed : 1;
    Cohort().CalibrationTargetGuid.Clear();
    Cohort().CalibrationFixtureTargetGuid.Clear();
    Cohort().CalibrationFixtureTargetEntry = 0;
    Cohort().CalibrationFixtureExpectedTargetLevel = 0;
    Cohort().CalibrationFixtureExpectedTargetArmor = 0;
    Cohort().CalibrationFixtureExpectedTargetCreatureType = 0;
    Cohort().CalibrationFixtureExpectedTargetMaxHealth = 0;
    Cohort().CalibrationFixtureObservedTargetLevel = 0;
    Cohort().CalibrationFixtureObservedTargetArmor = 0;
    Cohort().CalibrationFixtureObservedTargetCreatureType = 0;
    Cohort().CalibrationFixtureObservedTargetCreatureTypeMask = 0;
    Cohort().CalibrationFixtureObservedTargetMaxHealth = 0;
    Cohort().CalibrationFixtureTargetMapId = 0;
    Cohort().CalibrationFixtureTargetX = 0.0f;
    Cohort().CalibrationFixtureTargetY = 0.0f;
    Cohort().CalibrationFixtureTargetZ = 0.0f;
    Cohort().CalibrationFixtureTargetNearestHostileClearance = 0.0f;
    Cohort().CalibrationFixtureTargetProvisionedAtMs = 0;
    Cohort().CalibrationFixtureTargetObservedBeforeScoringAtMs = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetLevel = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetArmor = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetCreatureType = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetCreatureTypeMask = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetMaxHealth = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetMapId = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetGuid.Clear();
    Cohort().CalibrationFixtureBeforeScoringTargetX = 0.0f;
    Cohort().CalibrationFixtureBeforeScoringTargetY = 0.0f;
    Cohort().CalibrationFixtureBeforeScoringTargetZ = 0.0f;
    Cohort().CalibrationFixtureBeforeScoringBotTargetDistance = 0.0f;
    Cohort().CalibrationFixtureBotSpawnX = 0.0f;
    Cohort().CalibrationFixtureBotSpawnY = 0.0f;
    Cohort().CalibrationFixtureBotSpawnZ = 0.0f;
    Cohort().CalibrationFixtureBotTargetDistance = 0.0f;
    Cohort().CalibrationFixtureNativeLineOfSight = false;
    Cohort().CalibrationFixtureNativePathReachable = false;
    Cohort().CalibrationFixtureNativeMeleeReachable = false;
    Cohort().CalibrationFixtureNativeDryLand = false;
    Cohort().CalibrationFixtureGeometryValidated = false;
    Cohort().CalibrationFixtureProfileLane.clear();
    Cohort().CalibrationInterruptTargetGuid.Clear();
    Cohort().CalibrationStartedMs = NowMs();
    Cohort().CalibrationScoredStartedMs = 0;
    Cohort().CalibrationScoredEndedMs = 0;
    Cohort().CalibrationLastPostWindowDrainMs = 0;
    Cohort().CalibrationLastControlledEventSecond = std::numeric_limits<uint64>::max();
    Cohort().CalibrationCrossWindowEventCount = 0;
    Cohort().CalibrationExcludedBoundaryDamageEventCount = 0;
    Cohort().CalibrationFixtureTargetPassiveObservationSampleCount = 0;
    Cohort().CalibrationFixtureTargetVictimObservationSampleCount = 0;
    Cohort().CalibrationFixtureTargetAttackEventCount = 0;
    Cohort().CalibrationFixtureTargetOriginatedDamageEventCount = 0;
    Cohort().CalibrationFixtureTargetFirstPassiveObservedAtMs = 0;
    Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs = 0;
    Cohort().CalibrationFixtureTargetMaximumPassiveObservationGapMs = 0;
    Cohort().CalibrationResetId.clear();
    Cohort().CalibrationCurrentDamagePhase.clear();
    Cohort().CalibrationMetricsByGuid.clear();
    Cohort().CalibrationPreviousMetrics.clear();
    Cohort().CalibrationBestSingleMetrics.clear();
    Cohort().CalibrationBestAoeMetrics.clear();
    Cohort().CalibrationCompletedSingleWindows = 0;
    Cohort().CalibrationCompletedAoeWindows = 0;
    Cohort().CalibrationPreviousWindowValid = false;
    EnsureCalibrationPopulation();
    if (!Cohort().CalibrationFailureReason.empty())
        return "{\"ok\":false,\"action\":\"botauto_calibrate_start\",\"failure_reason\":\""
            + JsonEscape(Cohort().CalibrationFailureReason) + "\"}";
    EnsureCalibrationCohortGroup();
    return GetCombatCalibrationJson();
}

std::string BotWorldPopulationMgr::StopCombatCalibration()
{
    std::string const cohortId = Cohort().Id;
    uint64 const serverEpoch = _serverEpoch;
    uint64 const attemptId = Cohort().AttemptId;
    if (Cohort().CalibrationStopping)
    {
        std::ostringstream stoppingJson;
        stoppingJson << "{\"ok\":true,\"action\":\"botauto_calibrate_stop\""
                     << ",\"cohort_id\":\"" << JsonEscape(cohortId) << "\""
                     << ",\"server_epoch\":" << serverEpoch
                     << ",\"attempt_id\":" << attemptId
                     << ",\"removed\":0,\"failure_reason\":null}";
        return stoppingJson.str();
    }

    Cohort().CalibrationStopping = true;
    std::vector<ObjectGuid> calibrationBotGuids;
    calibrationBotGuids.reserve(Party().CalibrationBots.size());
    for (WorldBotState const& state : Party().CalibrationBots)
        if (!state.Guid.IsEmpty())
            calibrationBotGuids.push_back(state.Guid);

    bool fixtureTargetFound = false;
    bool fixtureCleanupSubmittedOrAbsent = true;
    if (!Cohort().CalibrationFixtureTargetGuid.IsEmpty())
        if (Map* fixtureMap = sMapMgr->FindMap(
            Cohort().CalibrationFixtureTargetMapId, 0))
            if (Creature* target = fixtureMap->GetCreature(
                Cohort().CalibrationFixtureTargetGuid))
            {
                fixtureTargetFound = true;
                if (TempSummon* summon = target->ToTempSummon())
                    summon->UnSummon();
                else
                    fixtureCleanupSubmittedOrAbsent = false;
            }

    uint32 removed = uint32(calibrationBotGuids.size());
    Party().CalibrationBots.clear();
    Cohort().CalibrationMetricsByGuid.clear();
    Cohort().CalibrationPreviousMetrics.clear();
    Cohort().CalibrationBestSingleMetrics.clear();
    Cohort().CalibrationBestAoeMetrics.clear();
    Cohort().CalibrationActive = false;
    Cohort().CalibrationAoePhase = false;
    Cohort().CalibrationWindowComplete = false;
    Cohort().CalibrationFailureReason.clear();
    Cohort().CalibrationMode = "single_target_300";
    Cohort().CalibrationTargetSpec.clear();
    Cohort().CalibrationSeed = 1;
    Cohort().CalibrationTargetGuid.Clear();
    Cohort().CalibrationFixtureTargetGuid.Clear();
    Cohort().CalibrationFixtureTargetEntry = 0;
    Cohort().CalibrationFixtureExpectedTargetLevel = 0;
    Cohort().CalibrationFixtureExpectedTargetArmor = 0;
    Cohort().CalibrationFixtureExpectedTargetCreatureType = 0;
    Cohort().CalibrationFixtureExpectedTargetMaxHealth = 0;
    Cohort().CalibrationFixtureObservedTargetLevel = 0;
    Cohort().CalibrationFixtureObservedTargetArmor = 0;
    Cohort().CalibrationFixtureObservedTargetCreatureType = 0;
    Cohort().CalibrationFixtureObservedTargetCreatureTypeMask = 0;
    Cohort().CalibrationFixtureObservedTargetMaxHealth = 0;
    Cohort().CalibrationFixtureTargetMapId = 0;
    Cohort().CalibrationFixtureTargetX = 0.0f;
    Cohort().CalibrationFixtureTargetY = 0.0f;
    Cohort().CalibrationFixtureTargetZ = 0.0f;
    Cohort().CalibrationFixtureTargetNearestHostileClearance = 0.0f;
    Cohort().CalibrationFixtureTargetProvisionedAtMs = 0;
    Cohort().CalibrationFixtureTargetObservedBeforeScoringAtMs = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetLevel = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetArmor = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetCreatureType = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetCreatureTypeMask = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetMaxHealth = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetMapId = 0;
    Cohort().CalibrationFixtureBeforeScoringTargetGuid.Clear();
    Cohort().CalibrationFixtureBeforeScoringTargetX = 0.0f;
    Cohort().CalibrationFixtureBeforeScoringTargetY = 0.0f;
    Cohort().CalibrationFixtureBeforeScoringTargetZ = 0.0f;
    Cohort().CalibrationFixtureBeforeScoringBotTargetDistance = 0.0f;
    Cohort().CalibrationFixtureBotSpawnX = 0.0f;
    Cohort().CalibrationFixtureBotSpawnY = 0.0f;
    Cohort().CalibrationFixtureBotSpawnZ = 0.0f;
    Cohort().CalibrationFixtureBotTargetDistance = 0.0f;
    Cohort().CalibrationFixtureNativeLineOfSight = false;
    Cohort().CalibrationFixtureNativePathReachable = false;
    Cohort().CalibrationFixtureNativeMeleeReachable = false;
    Cohort().CalibrationFixtureNativeDryLand = false;
    Cohort().CalibrationFixtureGeometryValidated = false;
    Cohort().CalibrationFixtureProfileLane.clear();
    Cohort().CalibrationInterruptTargetGuid.Clear();
    Cohort().CalibrationPreviousWindowValid = false;
    Cohort().CalibrationPreviousAoePhase = false;
    Cohort().CalibrationCompletedSingleWindows = 0;
    Cohort().CalibrationCompletedAoeWindows = 0;
    Cohort().CalibrationStartedMs = 0;
    Cohort().CalibrationScoredStartedMs = 0;
    Cohort().CalibrationScoredEndedMs = 0;
    Cohort().CalibrationLastPostWindowDrainMs = 0;
    Cohort().CalibrationLastControlledEventSecond = std::numeric_limits<uint64>::max();
    Cohort().CalibrationCrossWindowEventCount = 0;
    Cohort().CalibrationExcludedBoundaryDamageEventCount = 0;
    Cohort().CalibrationFixtureTargetPassiveObservationSampleCount = 0;
    Cohort().CalibrationFixtureTargetVictimObservationSampleCount = 0;
    Cohort().CalibrationFixtureTargetAttackEventCount = 0;
    Cohort().CalibrationFixtureTargetOriginatedDamageEventCount = 0;
    Cohort().CalibrationFixtureTargetFirstPassiveObservedAtMs = 0;
    Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs = 0;
    Cohort().CalibrationFixtureTargetMaximumPassiveObservationGapMs = 0;
    Cohort().CalibrationResetId.clear();
    Cohort().CalibrationCurrentDamagePhase.clear();

    // Remove each clone through the normal bot lifecycle. CleanupBot removes the
    // member from its group, and Group::RemoveMember owns any resulting disband;
    // retaining and explicitly disbanding the self-deleting Group here leaves a
    // stale group pointer for subsequent clone cleanup.
    for (ObjectGuid const& guid : calibrationBotGuids)
    {
        BotRaidAreaAuthority::Clear(guid.GetRawValue());
        sBotMgr->RemoveWorldBot(guid);
        if (ReleaseBotGuid(guid.GetCounter()))
            CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", guid.GetCounter());
    }
    Cohort().CalibrationStopping = false;
    Cohort().NonCertifyingAssistance = false;
    if (Cohort().Active)
    {
        Cohort().RuntimeMode = BotWorldRuntimeMode::AlwaysOnAutonomy;
        Cohort().Metrics.Mode = BotWorldRuntimeMode::AlwaysOnAutonomy;
    }

    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_calibrate_stop\""
         << ",\"cohort_id\":\"" << JsonEscape(cohortId) << "\""
         << ",\"server_epoch\":" << serverEpoch
         << ",\"attempt_id\":" << attemptId
         << ",\"removed\":" << removed
         << ",\"fixture_target_found\":" << (fixtureTargetFound ? "true" : "false")
         << ",\"fixture_cleanup_submitted_or_absent\":"
         << (fixtureCleanupSubmittedOrAbsent ? "true" : "false")
         << ",\"failure_reason\":null}";
    return json.str();
}

