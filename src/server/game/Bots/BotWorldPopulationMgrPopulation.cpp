#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include "Bots/BotMgr.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "Config.h"
#include "GameTime.h"
#include "Group.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "Player.h"
#include "Random.h"

#include <algorithm>
#include <chrono>
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

void BotWorldPopulationMgr::EnsurePopulation()
{
    auto terminateValidationAdmission = [this](std::string const& reason)
    {
        Cohort().ValidationAdmission = ValidationAdmissionPhase::Terminal;
        Cohort().ValidationAdmissionBatchSealed = false;
        Cohort().Raid.BotActionsEnabled = false;
        Cohort().Raid.AdmissionActionGateEnabled = false;
        for (WorldBotState const& member : Party().Bots)
            BotRaidAreaAuthority::SetAllOffenseSuppressed(
                member.Guid.GetRawValue(), true);
        Cohort().LastPopulationFailureReason = reason;
        if (Cohort().ValidationAttemptFailureReason.empty()
            || Cohort().ValidationAttemptFailureAttemptId != Cohort().AttemptId)
        {
            Cohort().ValidationAttemptFailureReason = reason;
            Cohort().ValidationAttemptFailureAttemptId = Cohort().AttemptId;
            Cohort().ValidationAttemptFailureRouteGeneration = Party().ValidationRouteGeneration;
        }
    };
    auto rejectPopulation = [this, &terminateValidationAdmission](std::string const& reason)
    {
        if (Cohort().Config.ValidationRouteEnable)
            terminateValidationAdmission(reason);
        else
            Cohort().LastPopulationFailureReason = reason;
    };

    std::vector<RaidRosterPlanSlot> const rosterPlan = BuildRosterPlan();
    bool const raidMode = Cohort().Config.AllowRaids;
    if (raidMode && rosterPlan.empty())
    {
        rejectPopulation("unsupported_exact_raid_size");
        return;
    }
    if (raidMode && Cohort().Config.TargetPopulation != rosterPlan.size())
    {
        rejectPopulation("raid_target_population_mismatch");
        return;
    }
    if (!Cohort().Config.PoolClassSpecFilter.empty()
        && Cohort().Config.PoolClassSpecFilter.size() != rosterPlan.size())
    {
        rejectPopulation("roster_class_spec_plan_mismatch");
        return;
    }

    uint32 const expectedPopulation = raidMode ? uint32(rosterPlan.size()) : Cohort().Config.TargetPopulation;
    if (Cohort().Config.ValidationRouteEnable)
    {
        if (Cohort().ValidationAdmission == ValidationAdmissionPhase::Terminal)
            return;
        if (Cohort().ValidationAdmission == ValidationAdmissionPhase::Active)
        {
            // The active phase is observation-only. It can fail closed, but it
            // can never form, refill, replace, relocate, or re-admit a member.
            EnsureValidationCohortGroup();
            return;
        }
        if (Cohort().ValidationAdmissionStarted)
        {
            terminateValidationAdmission("validation_admission_reentry_before_activation");
            return;
        }
        Cohort().ValidationAdmissionStarted = true;
    }
    // Validation-raid admission is a one-shot transaction. A failed attempt is
    // terminal for this cohort attempt: later ticks may neither reselect an
    // unpinned candidate nor enter the generic placement/fallback path.
    if (raidMode && Cohort().Config.ValidationRouteEnable)
    {
        EnsureValidationRaidAdmission(rosterPlan, expectedPopulation);
        return;
    }

    uint32 attempts = 0;
    uint32 maxAttempts = std::max<uint32>(1, expectedPopulation * 2);
    while (Cohort().Active && Party().Bots.size() < expectedPopulation && attempts < maxAttempts)
    {
        ++attempts;
        std::string rosterSlotId = SelectNextRosterSlot();
        if (rosterSlotId.empty())
        {
            Cohort().LastPopulationFailureReason = "no_unoccupied_roster_slot";
            break;
        }

        uint32 candidateGuid = SelectPoolCandidateGuid(rosterSlotId);
        if (!candidateGuid)
        {
            Cohort().LastPopulationFailureReason = Cohort().Config.PoolTagFilter.empty() ? "no_available_pool_candidate" : "no_available_pool_candidate_for_tag";
            break;
        }

        if (!ClaimBotGuid(candidateGuid, rosterSlotId))
        {
            Cohort().LastPopulationFailureReason = "bot_guid_lease_conflict";
            Cohort().FailedSpawnGuids.insert(candidateGuid);
            continue;
        }

        SpawnPlacement placement;
        if (Cohort().Config.ValidationRouteEnable)
        {
            if (Party().ValidationRouteManifest.empty())
            {
                Cohort().LastPopulationFailureReason =
                    "validation_admission_route_start_missing";
                Cohort().FailedSpawnGuids.insert(candidateGuid);
                ReleaseBotGuid(candidateGuid);
                continue;
            }
            ValidationRouteManifestNode const& routeStart =
                Party().ValidationRouteManifest.front();
            if (!routeStart.BotStartMapId
                || !MapManager::IsValidMapCoord(routeStart.BotStartMapId,
                    routeStart.BotStartX, routeStart.BotStartY,
                    routeStart.BotStartZ, routeStart.BotStartO))
            {
                Cohort().LastPopulationFailureReason =
                    "validation_admission_route_start_invalid";
                Cohort().FailedSpawnGuids.insert(candidateGuid);
                ReleaseBotGuid(candidateGuid);
                continue;
            }
            placement.Valid = true;
            placement.MapId = routeStart.BotStartMapId;
            placement.X = routeStart.BotStartX;
            placement.Y = routeStart.BotStartY;
            placement.Z = routeStart.BotStartZ;
            placement.O = routeStart.BotStartO;
            placement.Source = "server_route_manifest_entrance";
            placement.RaceStartFallbackUsed = false;
        }
        else if (!ResolveSpawnPlacement(candidateGuid, placement))
        {
            TC_LOG_ERROR("server", "BotWorld spawn skipped bot_guid=%u spawn_mode=%s fallback=%u reason=no_saved_or_local_spawn",
                candidateGuid, Cohort().Config.SpawnMode.c_str(), Cohort().Config.AllowConfiguredCenterFallback ? 1 : 0);
            Cohort().LastPopulationFailureReason = "no_saved_or_local_spawn";
            Cohort().FailedSpawnGuids.insert(candidateGuid);
            ReleaseBotGuid(candidateGuid);
            continue;
        }

        Player* groupAnchor = nullptr;
        if (Cohort().Config.ValidationRouteEnable && !Party().Bots.empty())
        {
            for (WorldBotState const& state : Party().Bots)
            {
                Player* candidate = GetLoadedBot(state);
                if (candidate && candidate->IsInWorld() && candidate->GetGroup())
                {
                    groupAnchor = candidate;
                    break;
                }
            }
        }

        Player* bot = nullptr;
        if (Cohort().Config.ValidationRouteEnable && groupAnchor)
            bot = sBotMgr->ProvisionWorldBotInGroup(groupAnchor, "any", std::to_string(candidateGuid),
                placement.MapId, placement.X, placement.Y, placement.Z, placement.O,
                Cohort().Config.DungeonDifficulty);
        else if (Cohort().Config.ValidationRouteEnable)
            bot = sBotMgr->ProvisionWorldBot("any", std::to_string(candidateGuid),
                placement.MapId, placement.X, placement.Y, placement.Z, placement.O,
                Cohort().Config.DungeonDifficulty);
        else if (groupAnchor)
            bot = sBotMgr->SpawnWorldBotInGroup(groupAnchor, "any", std::to_string(candidateGuid),
                placement.MapId, placement.X, placement.Y, placement.Z, placement.O);
        else
            bot = placement.Source != "saved_position"
                ? sBotMgr->SpawnWorldBot("any", std::to_string(candidateGuid), placement.MapId, placement.X, placement.Y, placement.Z, placement.O)
                : sBotMgr->SpawnWorldBotAtSavedPosition("any", std::to_string(candidateGuid));
        if (!bot)
        {
            Cohort().LastPopulationFailureReason = "spawn_world_bot_failed";
            Cohort().FailedSpawnGuids.insert(candidateGuid);
            ReleaseBotGuid(candidateGuid);
            continue;
        }
        TC_LOG_INFO("server", "BotWorld spawn selected bot=%s source=%s map=%u position=%f,%f,%f",
            bot->GetGUID().ToString().c_str(), placement.Source.c_str(), bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());

        WorldBotState state;
        state.Guid = bot->GetGUID();
        state.ServerProvisioned = Cohort().Config.ValidationRouteEnable;
        state.ServerBaselineNormalized = Cohort().Config.ValidationRouteEnable;
        state.RosterSlotId = rosterSlotId;
        for (RaidRosterPlanSlot const& slot : rosterPlan)
            if (slot.RosterSlotId == rosterSlotId)
            {
                state.RosterRole = slot.Role;
                break;
            }
        state.RosterClassSpec = GetBotClassSpec(bot);
        state.RosterAverageItemLevel = bot->GetAverageItemLevel();
        state.ValidationRouteGeneration = Party().ValidationRouteGeneration;
        state.DecisionTimer = urand(0, sConfigMgr->GetIntDefault("BotWorld.DecisionTickMs", 3000));
        state.LastX = bot->GetPositionX();
        state.LastY = bot->GetPositionY();
        state.LastZ = bot->GetPositionZ();
        state.SpawnedMs = NowMs();
        state.SpawnSource = placement.Source;
        state.RaceStartFallbackUsed = placement.RaceStartFallbackUsed;
        state.SpawnMapId = bot->GetMapId();
        state.SpawnX = bot->GetPositionX();
        state.SpawnY = bot->GetPositionY();
        state.SpawnZ = bot->GetPositionZ();
        state.SpawnO = bot->GetOrientation();
        Party().Bots.push_back(state);
        Cohort().Metrics.ActiveBots = uint32(Party().Bots.size());

        RecordActivityStart(Party().Bots.back(), bot);
        BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
        BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "idle", &power, stage);
        RecordSpawnResolved(Party().Bots.back(), bot, placement, placement.Source.c_str());
        RecordEvent(Party().Bots.back(), bot, "bot_spawned", nullptr, "ok", raw.c_str(), semantic.c_str());
        if (Cohort().Config.AllowRaids && bot->GetMap() && bot->GetMap()->IsRaid())
        {
            RaidRoleAssignment assignment = BuildRaidRoleAssignment(bot);
            BossMechanicFeatures features = BuildBossMechanicFeatures(bot, nullptr);
            RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(bot, nullptr, assignment, features);
            RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(bot, nullptr, assignment, features);
            RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(bot, power, stage);
            HeroicRaidProgression progression = BuildHeroicRaidProgression(Party().Bots.back(), bot, power, stage);
            RecordRaidTelemetry(Party().Bots.back(), bot, nullptr, "raid_role_assignment", "assigned", features, assignment, anchors, adapter, gearPlan, progression, raw.c_str(), semantic.c_str());
        }

        EnsureValidationCohortGroup();
    }

    if (!Cohort().Config.ValidationRouteEnable)
    {
        EnsureValidationCohortGroup();
        return;
    }

    if (Party().Bots.size() != expectedPopulation
        || Cohort().RosterLeases.size() != expectedPopulation)
    {
        terminateValidationAdmission(Cohort().LastPopulationFailureReason.empty()
            ? "validation_admission_incomplete_batch"
            : "validation_admission_incomplete_batch:" + Cohort().LastPopulationFailureReason);
        return;
    }

    Cohort().ValidationAdmissionBatchSealed = true;
    EnsureValidationCohortGroup();
    if (Cohort().ValidationAdmission != ValidationAdmissionPhase::Active)
        terminateValidationAdmission(Cohort().LastPopulationFailureReason.empty()
            ? "validation_admission_activation_failed"
            : "validation_admission_activation_failed:" + Cohort().LastPopulationFailureReason);
}


