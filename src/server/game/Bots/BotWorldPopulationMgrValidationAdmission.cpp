#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include "Bots/BotMgr.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "Config.h"
#include "DatabaseEnv.h"
#include "DataStores/DBCStores.h"
#include "GameTime.h"
#include "Group.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "Player.h"
#include "Random.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <set>
#include <string>
#include <vector>

namespace
{
constexpr uint32 ValidationGhostCharacterFlag = 0x2000;
constexpr uint32 ValidationResurrectAtLoginFlag = 0x0100;
constexpr uint32 ValidationGhostAuraId = 8326;

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

float Distance2d(float ax, float ay, float bx, float by)
{
    float dx = ax - bx;
    float dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}
}

void BotWorldPopulationMgr::EnsureValidationRaidAdmission(
    std::vector<RaidRosterPlanSlot> const& rosterPlan, uint32 expectedPopulation)
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
struct PlannedValidationRaidSpawn
{
    std::string RosterSlotId;
    uint32 Guid = 0;
    SpawnPlacement Placement;
};
std::vector<PlannedValidationRaidSpawn> validationRaidSpawnPlan;
    if (Cohort().ValidationRaidAdmissionFailed)
        return;
    if (Cohort().ValidationRaidAdmissionComplete)
    {
        std::string identityDriftDetail;
        uint32 nativeRecoveryWorldportsDeferred = 0;
        bool exactIdentity = Party().ValidationRouteManifest.size() > 0
            && Party().ValidationRouteManifest.front().ExpectedRoster.size() == expectedPopulation
            && Party().Bots.size() == expectedPopulation
            && Cohort().RosterLeases.size() == expectedPopulation
            && Cohort().Raid.RosterComplete && Cohort().Raid.UniqueLeases
            && Cohort().Raid.RosterByGuid.size() == expectedPopulation;
        ObjectGuid exactGroupGuid = ObjectGuid::Empty;
        Group* exactNativeGroup = nullptr;
        std::set<uint32> expectedGuids;
        if (exactIdentity)
        {
            ValidationRouteManifestNode const& routeStart = Party().ValidationRouteManifest.front();
            for (ValidationRouteManifestNode::RosterIdentity const& expected : routeStart.ExpectedRoster)
            {
                expectedGuids.insert(expected.Guid);
                auto const state = std::find_if(Party().Bots.begin(), Party().Bots.end(),
                    [&expected](WorldBotState const& row)
                    {
                        return row.Guid.GetCounter() == expected.Guid
                            && row.RosterSlotId == expected.RosterSlotId;
                    });
                if (state == Party().Bots.end())
                {
                    exactIdentity = false;
                    identityDriftDetail = "roster_state_missing:" + std::to_string(expected.Guid);
                    break;
                }

                Player* bot = GetLoadedBot(*state);
                if (!bot)
                {
                    exactIdentity = false;
                    identityDriftDetail = "loaded_bot_missing:" + std::to_string(expected.Guid);
                    break;
                }

                Group* group = bot->GetGroup();
                if (!group)
                {
                    exactIdentity = false;
                    identityDriftDetail = "native_group_missing:" + std::to_string(expected.Guid);
                    break;
                }

                // ReleaseSpirit and the canonical BWD entrance both use a
                // native far-worldport.  The player is deliberately out of
                // world until TryReattachValidationBot acknowledges it.
                // Defer only those two already corpse-, destination-,
                // teleport-type-, group-, leader-, map-, and instance-bound
                // transitions.  No generic death or teleport grace window
                // is permitted here.
                bool const nativeRecoveryWorldport = !bot->IsInWorld()
                && (IsNativeReleasedGhostWorldport(*state, bot)
                        || IsNativeValidationRunbackWorldport(*state, bot));
                auto const frozen = Cohort().Raid.RosterByGuid.find(expected.Guid);
                if (!bot->IsInWorld() && !nativeRecoveryWorldport)
                {
                    exactIdentity = false;
                    identityDriftDetail = "not_in_world_without_native_recovery_authority:" + std::to_string(expected.Guid);
                    break;
                }
                if (!LeaseOwnedByCurrentCohort(expected.Guid, expected.RosterSlotId))
                {
                    exactIdentity = false;
                    identityDriftDetail = "lease_identity_mismatch:" + std::to_string(expected.Guid);
                    break;
                }
                if (frozen == Cohort().Raid.RosterByGuid.end()
                    || frozen->second.RosterSlotId != expected.RosterSlotId)
                {
                    exactIdentity = false;
                    identityDriftDetail = "frozen_roster_slot_mismatch:" + std::to_string(expected.Guid);
                    break;
                }
                if (group->GetGUID() != state->ValidationCohortGroupGuid
                    || group->GetLeaderGUID() != state->ValidationCohortLeaderGuid)
                {
                    exactIdentity = false;
                    identityDriftDetail = "frozen_group_or_leader_mismatch:" + std::to_string(expected.Guid);
                    break;
                }
                if (!nativeRecoveryWorldport
                    && !IsValidationCohortMemberInOriginalInstance(*state, bot))
                {
                    exactIdentity = false;
                    identityDriftDetail = "frozen_map_or_instance_mismatch:" + std::to_string(expected.Guid);
                    break;
                }
                if (nativeRecoveryWorldport)
                    ++nativeRecoveryWorldportsDeferred;
                if (exactGroupGuid.IsEmpty())
                    exactGroupGuid = group->GetGUID();
                else if (exactGroupGuid != group->GetGUID())
                {
                    exactIdentity = false;
                    identityDriftDetail = "split_native_group:" + std::to_string(expected.Guid);
                    break;
                }
                exactNativeGroup = group;
            }
            exactIdentity = exactIdentity && !exactGroupGuid.IsEmpty()
                && Cohort().Raid.GroupGuid == exactGroupGuid
                && expectedGuids.size() == expectedPopulation;
            if (!exactIdentity && identityDriftDetail.empty())
                identityDriftDetail = "raid_group_identity_mismatch";

            if (exactIdentity && (!exactNativeGroup
                || exactNativeGroup->GetMembersCount() != expectedPopulation))
            {
                exactIdentity = false;
                identityDriftDetail = "native_group_membership_count_mismatch";
            }
            if (exactIdentity)
                for (Group::MemberSlot const& member : exactNativeGroup->GetMemberSlots())
                {
                    uint32 const memberGuid = member.guid.GetCounter();
                    if (!expectedGuids.count(memberGuid))
                    {
                        exactIdentity = false;
                        identityDriftDetail = "native_group_foreign_member:" + std::to_string(memberGuid);
                        break;
                    }

                    auto const frozen = Cohort().Raid.RosterByGuid.find(memberGuid);
                    if (frozen == Cohort().Raid.RosterByGuid.end()
                        || member.group != frozen->second.SubGroup)
                    {
                        exactIdentity = false;
                        identityDriftDetail = "native_group_subgroup_drift:" + std::to_string(memberGuid);
                        break;
                    }
                }
        }
        if (!exactIdentity)
        {
            if (identityDriftDetail.empty())
                identityDriftDetail = "raid_runtime_shape_mismatch";
            TC_LOG_ERROR("server", "BotWorld validation raid admission identity drift detail=%s",
                identityDriftDetail.c_str());
            FlushPendingDecisionFingerprintMemory();
            std::set<uint32> cleanupGuids = Cohort().RosterLeases;
            for (WorldBotState const& state : Party().Bots)
            {
                cleanupGuids.insert(state.Guid.GetCounter());
                BotRaidAreaAuthority::Clear(state.Guid.GetRawValue());
                sBotMgr->RemoveWorldBot(state.Guid);
            }
            for (uint32 guid : cleanupGuids)
            {
                ReleaseBotGuid(guid);
                CharacterDatabase.DirectPExecute(
                    "UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", guid);
            }
            Party() = PartyRuntime();
            Cohort().Raid = RaidRuntime();
            Cohort().RosterLeases.clear();
            Cohort().Metrics.ActiveBots = 0;
            Cohort().ValidationRaidAdmissionComplete = false;
            Cohort().ValidationRaidAdmissionFailed = true;
            Cohort().LastPopulationFailureReason =
                "validation_raid_admission_identity_drift:" + identityDriftDetail;
        }
        else
        {
            // Admission identity is immutable, but raid state is live.  Rebuild
            // the runtime from the exact native roster on every completed tick
            // so deaths, wipes, and encounter state cannot remain frozen at
            // admission.  EnsureValidationCohortGroup intentionally defers
            // while a native recovery worldport leaves the live formation
            // incomplete; the next reattached tick refreshes the full roster.
            EnsureValidationCohortGroup();
            if (nativeRecoveryWorldportsDeferred)
            {
                uint64 const nowMs = NowMs();
                if (!Cohort().LastNativeWorldportDeferredLogMs
                    || nowMs - Cohort().LastNativeWorldportDeferredLogMs >= 5000)
                {
                    TC_LOG_INFO("server", "BotWorld validation raid admission deferred native recovery worldports count=%u suppressed=%u",
                        nativeRecoveryWorldportsDeferred, Cohort().SuppressedNativeWorldportDeferredLogs);
                    Cohort().LastNativeWorldportDeferredLogMs = nowMs;
                    Cohort().SuppressedNativeWorldportDeferredLogs = 0;
                }
                else
                    ++Cohort().SuppressedNativeWorldportDeferredLogs;
            }
        }
        return;
    }

    auto terminalFailure = [this, &terminateValidationAdmission](char const* reason)
    {
        Cohort().ValidationRaidAdmissionComplete = false;
        Cohort().ValidationRaidAdmissionFailed = true;
        terminateValidationAdmission(reason);
    };

    // An admission transaction may only start from a demonstrably empty
    // cohort. Clean up any inherited partial state, then latch failure
    // instead of treating it as a resumable roster.
    if (!Party().Bots.empty() || !Cohort().RosterLeases.empty())
    {
        FlushPendingDecisionFingerprintMemory();
        std::set<uint32> cleanupGuids = Cohort().RosterLeases;
        for (WorldBotState const& state : Party().Bots)
        {
            cleanupGuids.insert(state.Guid.GetCounter());
            BotRaidAreaAuthority::Clear(state.Guid.GetRawValue());
            sBotMgr->RemoveWorldBot(state.Guid);
        }
        for (uint32 guid : cleanupGuids)
        {
            ReleaseBotGuid(guid);
            CharacterDatabase.DirectPExecute(
                "UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", guid);
        }
        Party() = PartyRuntime();
        Cohort().Raid = RaidRuntime();
        Cohort().RosterLeases.clear();
        Cohort().Metrics.ActiveBots = 0;
        terminalFailure("validation_raid_admission_nonempty_start");
        return;
    }

    // Read and validate every GUID before the first lease or native login.
    // Entrance placement is owned by this inactive server admission
    // transaction and comes directly from the pinned route manifest.  The
    // operator must not pre-relocate characters in SQL, and active bots
    // have no path back to this provisioning capability.
    if (Party().ValidationRouteManifest.empty())
    {
        terminalFailure("validation_raid_preflight_route_start_missing");
        return;
    }

    ValidationRouteManifestNode const& routeStart = Party().ValidationRouteManifest.front();
    static constexpr float RouteStartHorizontalToleranceYards = 5.0f;
    static constexpr float RouteStartVerticalToleranceYards = 3.0f;
    if (!routeStart.BotStartMapId
        || routeStart.ExpectedBotCount != rosterPlan.size()
        || routeStart.ExpectedRoster.size() != rosterPlan.size()
        || !MapManager::IsValidMapCoord(routeStart.BotStartMapId, routeStart.BotStartX,
            routeStart.BotStartY, routeStart.BotStartZ, routeStart.BotStartO))
    {
        terminalFailure("validation_raid_preflight_route_start_invalid");
        return;
    }

    std::set<uint32> plannedGuids;
    validationRaidSpawnPlan.reserve(rosterPlan.size());
    for (RaidRosterPlanSlot const& slot : rosterPlan)
    {
        auto const expected = std::find_if(routeStart.ExpectedRoster.begin(), routeStart.ExpectedRoster.end(),
            [&slot](ValidationRouteManifestNode::RosterIdentity const& row)
            {
                return row.RosterSlotId == slot.RosterSlotId;
            });
        if (expected == routeStart.ExpectedRoster.end() || !expected->Guid || expected->Name.empty()
            || expected->Role != slot.Role || expected->ClassSpec.empty())
        {
            terminalFailure("validation_raid_preflight_roster_identity_invalid");
            return;
        }
        uint32 const candidateGuid = SelectPoolCandidateGuid(slot.RosterSlotId, &plannedGuids,
            expected->Guid, expected->Name, expected->ClassSpec);
        if (!candidateGuid)
        {
            terminalFailure("validation_raid_preflight_exact_roster_missing");
            return;
        }

        QueryResult persistedState = CharacterDatabase.PQuery(
            "SELECT c.health, c.power1, c.characterFlags, c.at_login, "
            "(SELECT COUNT(*) FROM character_aura a WHERE a.guid = c.guid AND a.spell = %u), "
            "(SELECT COUNT(*) FROM corpse cp WHERE cp.guid = c.guid) "
            "FROM characters c WHERE c.guid = %u",
            ValidationGhostAuraId, candidateGuid);
        if (!persistedState)
        {
            terminalFailure("validation_raid_preflight_persisted_state_missing");
            return;
        }
        Field* persistedFields = persistedState->Fetch();
        if (persistedFields[0].GetUInt32() != std::numeric_limits<uint32>::max()
            || persistedFields[1].GetUInt32() != std::numeric_limits<uint32>::max())
        {
            terminalFailure("validation_raid_preflight_full_stat_seed_missing");
            return;
        }
        if ((persistedFields[2].GetUInt32() & ValidationGhostCharacterFlag) != 0
            || (persistedFields[3].GetUInt32() & ValidationResurrectAtLoginFlag) != 0
            || persistedFields[4].GetUInt32() != 0
            || persistedFields[5].GetUInt32() != 0)
        {
            terminalFailure("validation_raid_preflight_initial_recovery_state");
            return;
        }

        SpawnPlacement placement;
        placement.Valid = true;
        placement.MapId = routeStart.BotStartMapId;
        placement.X = routeStart.BotStartX;
        placement.Y = routeStart.BotStartY;
        placement.Z = routeStart.BotStartZ;
        placement.O = routeStart.BotStartO;
        placement.Source = "server_route_manifest_entrance";
        placement.RaceStartFallbackUsed = false;

        plannedGuids.insert(candidateGuid);
        validationRaidSpawnPlan.push_back({ slot.RosterSlotId, candidateGuid, placement });
    }
    if (validationRaidSpawnPlan.size() != rosterPlan.size()
        || plannedGuids.size() != rosterPlan.size())
    {
        terminalFailure("validation_raid_preflight_roster_not_unique");
        return;
    }

    PartyRuntime const partyBeforeAdmission = Party();
    RaidRuntime const raidBeforeAdmission = Cohort().Raid;
    BotWorldStatus const metricsBeforeAdmission = Cohort().Metrics;
    std::set<uint32> const failedSpawnGuidsBeforeAdmission = Cohort().FailedSpawnGuids;
    std::vector<uint32> claimedGuids;
    std::vector<ObjectGuid> spawnedGuids;
    auto rollbackAdmission = [this, &partyBeforeAdmission, &raidBeforeAdmission,
        &metricsBeforeAdmission, &failedSpawnGuidsBeforeAdmission,
        &claimedGuids, &spawnedGuids, &terminalFailure](char const* reason)
    {
        FlushPendingDecisionFingerprintMemory();
        for (auto itr = spawnedGuids.rbegin(); itr != spawnedGuids.rend(); ++itr)
        {
            BotRaidAreaAuthority::Clear(itr->GetRawValue());
            sBotMgr->RemoveWorldBot(*itr);
        }
        if (!spawnedGuids.empty())
        {
            if (Group* ghostCohortGroup = sBotMgr->FindSeedRaidGroupForLeader(spawnedGuids.front()))
            {
                TC_LOG_INFO("server", "BotWorld validation cohort group rollback disband leader=%s group=%s",
                    spawnedGuids.front().ToString().c_str(), ghostCohortGroup->GetGUID().ToString().c_str());
                ghostCohortGroup->Disband();
            }
        }
        for (uint32 guid : claimedGuids)
        {
            ReleaseBotGuid(guid);
            CharacterDatabase.DirectPExecute(
                "UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", guid);
        }
        Party() = partyBeforeAdmission;
        Cohort().Raid = raidBeforeAdmission;
        Cohort().Metrics = metricsBeforeAdmission;
        Cohort().FailedSpawnGuids = failedSpawnGuidsBeforeAdmission;
        Cohort().RosterLeases.clear();
        terminalFailure(reason);
    };

    for (PlannedValidationRaidSpawn const& planned : validationRaidSpawnPlan)
    {
        if (!ClaimBotGuid(planned.Guid, planned.RosterSlotId))
        {
            rollbackAdmission("validation_raid_admission_claim_failed");
            return;
        }
        claimedGuids.push_back(planned.Guid);

        Player* groupAnchor = nullptr;
        for (WorldBotState const& state : Party().Bots)
        {
            Player* candidate = GetLoadedBot(state);
            if (candidate && candidate->IsInWorld() && candidate->GetGroup())
            {
                groupAnchor = candidate;
                break;
            }
        }

        Player* bot = nullptr;
        MapEntry const* placementMap = sMapStore.LookupEntry(planned.Placement.MapId);
        if (!groupAnchor && placementMap && placementMap->IsRaid())
        {
            // The first planned member seeds the cohort raid so its own raid
            // map entry creates the one native instance every later member
            // joins. Ungrouped entry would fail closed on NOT_IN_RAID.
            bot = sBotMgr->ProvisionWorldBotRaidSeed("any", std::to_string(planned.Guid),
                planned.Placement.MapId, planned.Placement.X, planned.Placement.Y,
                planned.Placement.Z, planned.Placement.O, Cohort().Config.RaidDifficulty);
        }
        if (!bot)
            bot = groupAnchor
                ? sBotMgr->ProvisionWorldBotInGroup(groupAnchor, "any", std::to_string(planned.Guid),
                    planned.Placement.MapId, planned.Placement.X, planned.Placement.Y,
                    planned.Placement.Z, planned.Placement.O,
                    BotMgr::NoProvisionedDungeonDifficulty, Cohort().Config.RaidDifficulty)
                : sBotMgr->ProvisionWorldBot("any", std::to_string(planned.Guid),
                    planned.Placement.MapId, planned.Placement.X, planned.Placement.Y,
                    planned.Placement.Z, planned.Placement.O,
                    BotMgr::NoProvisionedDungeonDifficulty, Cohort().Config.RaidDifficulty);
        if (!bot)
        {
            rollbackAdmission("validation_raid_admission_spawn_failed");
            return;
        }
        spawnedGuids.push_back(bot->GetGUID());

        WorldBotState state;
        state.Guid = bot->GetGUID();
        state.ServerProvisioned = true;
        state.ServerBaselineNormalized = true;
        state.RosterSlotId = planned.RosterSlotId;
        for (RaidRosterPlanSlot const& slot : rosterPlan)
            if (slot.RosterSlotId == planned.RosterSlotId)
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
        state.SpawnSource = planned.Placement.Source;
        state.RaceStartFallbackUsed = false;
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
        RecordSpawnResolved(Party().Bots.back(), bot, planned.Placement, planned.Placement.Source.c_str());
        RecordEvent(Party().Bots.back(), bot, "bot_spawned", nullptr, "ok", raw.c_str(), semantic.c_str());
        if (bot->GetMap() && bot->GetMap()->IsRaid())
        {
            RaidRoleAssignment assignment = BuildRaidRoleAssignment(bot);
            BossMechanicFeatures features = BuildBossMechanicFeatures(bot, nullptr);
            RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(bot, nullptr, assignment, features);
            RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(bot, nullptr, assignment, features);
            RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(bot, power, stage);
            HeroicRaidProgression progression = BuildHeroicRaidProgression(Party().Bots.back(), bot, power, stage);
            RecordRaidTelemetry(Party().Bots.back(), bot, nullptr, "raid_role_assignment", "assigned",
                features, assignment, anchors, adapter, gearPlan, progression, raw.c_str(), semantic.c_str());
        }
        EnsureValidationCohortGroup();
    }

    EnsureValidationCohortGroup();
    bool exactNativeGroup = Party().Bots.size() == expectedPopulation
        && Cohort().RosterLeases.size() == expectedPopulation
        && Cohort().Raid.RosterComplete && Cohort().Raid.UniqueLeases;
    ObjectGuid admittedGroupGuid = ObjectGuid::Empty;
    for (WorldBotState const& state : Party().Bots)
    {
        Player* bot = GetLoadedBot(state);
        Group* group = bot ? bot->GetGroup() : nullptr;
        std::string failedConditions;
        auto appendFailedCondition = [&failedConditions](std::string const& detail)
        {
            if (!failedConditions.empty())
                failedConditions += ',';
            failedConditions += detail;
        };
        if (!bot)
            appendFailedCondition("loaded_bot_missing");
        else
        {
            if (!bot->IsInWorld())
                appendFailedCondition("not_in_world");
            if (!bot->IsAlive())
                appendFailedCondition("not_alive");
            if (bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST))
                appendFailedCondition("ghost_flag");
            if (bot->HasCorpse())
                appendFailedCondition("corpse");
            if (!group)
                appendFailedCondition("native_group_missing");
            if (!state.ValidationCohortLocked)
                appendFailedCondition("cohort_not_locked");
            if (bot->GetMapId() != routeStart.BotStartMapId)
                appendFailedCondition("map_mismatch:" + std::to_string(bot->GetMapId()));
            if (!bot->GetInstanceId())
                appendFailedCondition("zero_instance_id");
            float const horizontalDrift = Distance2d(bot->GetPositionX(), bot->GetPositionY(),
                routeStart.BotStartX, routeStart.BotStartY);
            if (horizontalDrift > RouteStartHorizontalToleranceYards)
                appendFailedCondition("horizontal_drift:" + std::to_string(horizontalDrift));
            float const verticalDrift = std::fabs(bot->GetPositionZ() - routeStart.BotStartZ);
            if (verticalDrift > RouteStartVerticalToleranceYards)
                appendFailedCondition("vertical_drift:" + std::to_string(verticalDrift));
            if (state.ValidationCohortMapId != bot->GetMapId())
                appendFailedCondition("frozen_map_mismatch:" + std::to_string(state.ValidationCohortMapId));
            if (state.ValidationCohortInstanceId != bot->GetInstanceId())
                appendFailedCondition("frozen_instance_mismatch:" + std::to_string(state.ValidationCohortInstanceId));
        }
        if (!failedConditions.empty())
        {
            TC_LOG_ERROR("server", "BotWorld validation raid admission exact state failed bot=%s slot=%s expected_map=%u expected_instance_locked=%u expected_pos=%.3f,%.3f,%.3f conditions=%s",
                state.Guid.ToString().c_str(), state.RosterSlotId.c_str(), routeStart.BotStartMapId,
                uint32(state.ValidationCohortLocked), routeStart.BotStartX, routeStart.BotStartY,
                routeStart.BotStartZ, failedConditions.c_str());
            exactNativeGroup = false;
            break;
        }
        if (admittedGroupGuid.IsEmpty())
            admittedGroupGuid = group->GetGUID();
        else if (admittedGroupGuid != group->GetGUID())
        {
            TC_LOG_ERROR("server", "BotWorld validation raid admission exact state failed bot=%s slot=%s conditions=split_native_group",
                state.Guid.ToString().c_str(), state.RosterSlotId.c_str());
            exactNativeGroup = false;
            break;
        }
    }
    if (!exactNativeGroup)
    {
        rollbackAdmission("validation_raid_admission_exact_group_or_alive_state_failed");
        return;
    }

    Cohort().ValidationAdmissionBatchSealed = true;
    EnsureValidationCohortGroup();
    if (Cohort().ValidationAdmission != ValidationAdmissionPhase::Active)
    {
        rollbackAdmission("validation_raid_admission_activation_failed");
        return;
    }
    Cohort().ValidationRaidAdmissionComplete = true;
    Cohort().ValidationRaidAdmissionFailed = false;
    Cohort().LastPopulationFailureReason.clear();
    return;
}
