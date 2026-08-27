#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotExperienceLearningPolicy.h"
#include "Bots/BotWorldPopulationMgrGhostFlight.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Corpse.h"
#include "DataStores/DBCStructure.h"
#include "GameTime.h"
#include "Group.h"
#include "Map.h"
#include "Pet.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <algorithm>
#include <chrono>
#include <limits>
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

BotWorldPopulationMgr::BotDeathRecoveryPolicy BotWorldPopulationMgr::BuildDeathRecoveryPolicy() const
{
    BotDeathRecoveryPolicy policy;
    // Autonomous recovery must remain achievable by an ordinary client.
    // Legacy configuration names selected direct resurrection/teleport paths;
    // retain the setting for compatibility/telemetry but never execute them.
    policy.Modes = { "native_corpse_run" };
    policy.MaxDeathsBeforeFallback = Cohort().Config.MaxDeathsBeforeFallback;
    return policy;
}

BotWorldPopulationMgr::DeathRecoveryResult BotWorldPopulationMgr::RecoverDeadBot(WorldBotState& state, Player* bot)
{
    DeathRecoveryResult recovery;
    if (!bot || bot->IsAlive())
        return recovery;

    BotDeathRecoveryPolicy policy = BuildDeathRecoveryPolicy();
    recovery.RepeatedDeath = state.RecentDeathCount >= policy.MaxDeathsBeforeFallback;
    struct ScoredMode
    {
        std::string Mode;
        float Score = 0.0f;
    };
    std::vector<ScoredMode> scoredModes;
    for (std::string const& mode : policy.Modes)
    {
        BotLearnedScore learned = BotExperienceLearningPolicy::ScoreRecoveryMode(bot,
            mode.c_str(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(),
            state.RecentDeathCount, Cohort().LearningConfig);
        scoredModes.push_back({ mode, 10.0f + learned.Score });
    }
    std::sort(scoredModes.begin(), scoredModes.end(), [](ScoredMode const& left, ScoredMode const& right)
    {
        if (left.Score == right.Score)
            return left.Mode < right.Mode;
        return left.Score > right.Score;
    });

    for (ScoredMode const& scored : scoredModes)
    {
        std::string const& mode = scored.Mode;
        std::string result;
        bool const ok = mode == "native_corpse_run"
            && TryNativeCorpseRun(state, bot, result);

        if (!ok)
        {
            if (!result.empty())
            {
                recovery.Mode = mode;
                recovery.Result = result;
            }
            continue;
        }

        recovery.Recovered = bot->IsAlive();
        recovery.InProgress = !recovery.Recovered;
        recovery.UsedFallback = false;
        recovery.Mode = mode;
        recovery.Result = result.empty() ? "ok" : result;
        return recovery;
    }

    if (recovery.Result == "failed")
        recovery.Result = "no_recovery_mode_succeeded";
    return recovery;
}

bool BotWorldPopulationMgr::TryNativeCorpseRun(WorldBotState& state, Player* bot, std::string& result)
{
    if (!bot || !bot->GetSession())
    {
        result = "bot_session_unavailable";
        return false;
    }

    constexpr uint64 NativeRecoveryNoProgressMs = 30000;
    constexpr uint32 MaximumReleaseRejections = 5;
    constexpr uint32 MaximumEntranceUnavailableObservations = 3;
    constexpr uint32 MaximumEntranceRejections = 3;
    constexpr uint32 MaximumMovementRejections = 5;
    constexpr uint32 MaximumReclaimRejections = 5;
    constexpr float NativeRecoveryDistanceProgressYards = 0.5f;

    uint64 const nowMs = NowMs();
    uint64 const routeGeneration = Party().ValidationRouteGeneration;
    uint64 const wipeGeneration = Cohort().Raid.WipeGeneration;
    bool const episodeMatches = state.NativeRecoveryEpisodeStartedMs
        && state.NativeRecoveryEpisodeAttemptId == Cohort().AttemptId
        && state.NativeRecoveryEpisodeRouteGeneration == routeGeneration
        && state.NativeRecoveryEpisodeWipeGeneration == wipeGeneration
        && state.NativeRecoveryEpisodeDeathOrdinal == state.RecentDeathCount;
    if (!episodeMatches)
    {
        state.NativeRecoveryEpisodeAttemptId = Cohort().AttemptId;
        state.NativeRecoveryEpisodeRouteGeneration = routeGeneration;
        state.NativeRecoveryEpisodeWipeGeneration = wipeGeneration;
        state.NativeRecoveryEpisodeDeathOrdinal = state.RecentDeathCount;
        state.NativeRecoveryEpisodePhase = "release_pending";
        state.NativeRecoveryEpisodeStartedMs = nowMs;
        state.NativeRecoveryEpisodeLastProgressMs = nowMs;
        state.NativeRecoveryEpisodeDistanceTarget = "none";
        state.NativeRecoveryEpisodeBestDistance =
            std::numeric_limits<float>::max();
        state.NativeRecoveryMovementRetryCount = 0;
        state.NativeRecoveryReleaseRejectionCount = 0;
        state.NativeRecoveryEntranceUnavailableCount = 0;
        state.NativeRecoveryEntranceRejectionCount = 0;
        state.NativeRecoveryReclaimRejectionCount = 0;
        state.NativeRecoveryEntranceRequired = false;
        state.NativeRecoveryEntranceObserved = false;
        state.NativeRecoveryEntranceAvailable = false;
    }

    bool const nativeCorpseAuthority =
        Cohort().Config.ValidationRouteEnable
        && state.ValidationCohortLocked
        && HasNativeRaidCorpseAuthority(state, bot);
    bool const certifyingCrossMapRecovery = nativeCorpseAuthority
        && bot->GetMapId() != state.ValidationCohortMapId;
    bool const nativeRecoveryEpisode = state.NativeRecoveryEpisodeStartedMs
        && state.NativeRecoveryEpisodeAttemptId == Cohort().AttemptId
        && state.NativeRecoveryEpisodeRouteGeneration == routeGeneration
        && state.NativeRecoveryEpisodeWipeGeneration == wipeGeneration
        && state.NativeRecoveryEpisodeDeathOrdinal == state.RecentDeathCount
        && state.NativeRecoveryEpisodePhase != "none"
        && state.NativeRecoveryEpisodePhase != "terminal";
    BotWorldGhostFlight::Eligibility const ghostFlightEligibility{
        bot->GetMapId(),
        bot->GetZoneId(),
        !bot->IsAlive() && bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST),
        bot->IsInWorld(),
        nativeRecoveryEpisode,
        nativeCorpseAuthority,
        certifyingCrossMapRecovery,
        bot->IsOutdoors(),
        bot->GetMap() && bot->GetMap()->IsDungeon(),
        bot->GetTransport() != nullptr,
        bot->IsInFlight()
    };
    auto clearGhostFlight = [&]()
    {
        if (!state.NativeRecoveryGhostFlightEnabled)
            return;
        if (bot->CanFly())
            bot->SetCanFly(false);
        state.NativeRecoveryGhostFlightEnabled = false;
    };
    if (BotWorldGhostFlight::IsEligible(ghostFlightEligibility))
    {
        if (!bot->CanFly())
            bot->SetCanFly(true);
        state.NativeRecoveryGhostFlightEnabled = true;
    }
    else
        clearGhostFlight();

    auto transition = [&](char const* phase)
    {
        if (state.NativeRecoveryEpisodePhase == phase)
            return;
        state.NativeRecoveryEpisodePhase = phase;
        state.NativeRecoveryEpisodeLastProgressMs = nowMs;
    };
    auto observeDistance = [&](char const* target, float distance)
    {
        if (state.NativeRecoveryEpisodeDistanceTarget != target)
        {
            state.NativeRecoveryEpisodeDistanceTarget = target;
            state.NativeRecoveryEpisodeBestDistance = distance;
            state.NativeRecoveryEpisodeLastProgressMs = nowMs;
            return;
        }
        if (distance + NativeRecoveryDistanceProgressYards
            < state.NativeRecoveryEpisodeBestDistance)
        {
            state.NativeRecoveryEpisodeBestDistance = distance;
            state.NativeRecoveryEpisodeLastProgressMs = nowMs;
        }
    };
    auto noProgressExpired = [&]()
    {
        return state.NativeRecoveryEpisodeLastProgressMs
            && nowMs >= state.NativeRecoveryEpisodeLastProgressMs
            && nowMs - state.NativeRecoveryEpisodeLastProgressMs
                >= NativeRecoveryNoProgressMs;
    };
    auto matchingNativeRecoveryPath = [&]()
    {
        return state.NativeRecoveryEntranceRequired
            && state.ActivePathValid
            && state.ActivePathTraversalMode == "native_long_path"
            && state.ActivePathTargetGuid.IsEmpty()
            && state.MovementLease.MovementOwner
                == BotMovementArbitration::Owner::Recovery
            && state.ActivePathAttemptId == Cohort().AttemptId
            && state.ActivePathWipeGeneration == wipeGeneration
            && state.ActivePathRouteGeneration == routeGeneration
            && state.ActivePathRouteNodeId
                == Cohort().Config.ValidationRouteNodeId;
    };
    auto observeNativeRecoveryMovement = [&]()
    {
        if (!matchingNativeRecoveryPath())
            return false;

        // PrepareBotUpdate is the authoritative position sampler. Its
        // LastMovementProgressMs timestamp is episode-safe because a new
        // episode starts by setting its own witness to nowMs above; only a
        // later movement sample can refresh this matching native path.
        if (!state.LastMovementProgressMs
            || state.LastMovementProgressMs
                <= state.NativeRecoveryEpisodeLastProgressMs)
            return false;

        state.NativeRecoveryEpisodeLastProgressMs =
            state.LastMovementProgressMs;
        state.LastNoProgressReason.clear();
        return true;
    };
    observeNativeRecoveryMovement();
    auto terminal = [&](char const* reason)
    {
        // Preserve the timestamp of the last observed native progress.  A
        // terminal receipt must show how long the episode was stalled, not
        // make terminalization itself look like progress.
        state.NativeRecoveryEpisodePhase = "terminal";
        result = reason;
        state.LastRecoveryMode = "native_corpse_run";
        state.LastRecoveryResult = reason;
        state.LastRecoveryMs = nowMs;
        state.LastNoProgressReason = reason;
        clearGhostFlight();
        if (Cohort().Config.ValidationRouteEnable
            && state.ValidationCohortLocked)
            FailValidationAttemptOnce(state, bot, reason,
                state.NativeRecoveryEpisodeRouteGeneration);
        return false;
    };

    if (!bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST))
    {
        transition("release_submitted");
        ExecuteNativeActionIntent(state, bot,
            BotNativeAction::ReleaseSpirit{});
        if (bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
            && Cohort().Config.ValidationRouteEnable && state.ValidationCohortLocked)
        {
            state.NativeReleaseRequested = true;
            state.NativeRunbackAreaTriggerId = 0;
            state.NativeReleaseLandingObserved = false;
            state.NativeReleaseLandingMapId = 0;
            state.NativeReleaseLandingInstanceId = 0;
            state.NativeReleaseLandingWipeGeneration = 0;
            state.NativeReleaseLandingX = 0.0f;
            state.NativeReleaseLandingY = 0.0f;
            state.NativeReleaseLandingZ = 0.0f;
        }
        if (bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST))
        {
            transition("released_ghost_observed");
            result = "native_release_requested";
            return true;
        }
        ++state.NativeRecoveryReleaseRejectionCount;
        result = bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
            ? "native_release_requested"
            : "native_release_pending";
        if (state.NativeRecoveryReleaseRejectionCount
                >= MaximumReleaseRejections
            || noProgressExpired())
            return terminal("native_runback_no_progress");
        return true;
    }

    Corpse* corpse = bot->GetCorpse();
    bool const corpseCrossMap = corpse
        && corpse->GetMapId() != bot->GetMapId();
    if (!corpse || corpseCrossMap)
    {
        if (certifyingCrossMapRecovery)
        {
            state.NativeRecoveryEntranceRequired = true;
            AreaTriggerEntry const* entranceEntry = nullptr;
            AreaTriggerStruct const* entranceDestination = nullptr;
            if (!ResolveNativeValidationEntrance(state.ValidationCohortMapId,
                    bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(),
                    entranceEntry, entranceDestination))
            {
                state.NativeRecoveryEntranceObserved = true;
                state.NativeRecoveryEntranceAvailable = false;
                ++state.NativeRecoveryEntranceUnavailableCount;
                transition("entrance_unavailable");
                result = "native_instance_entrance_unavailable";
                if (state.NativeRecoveryEntranceUnavailableCount
                        >= MaximumEntranceUnavailableObservations
                    || noProgressExpired())
                    return terminal("native_entrance_unavailable");
                return true;
            }

            state.NativeRecoveryEntranceObserved = true;
            state.NativeRecoveryEntranceAvailable = true;
            state.NativeRunbackAreaTriggerId = entranceEntry->ID;
            float const entranceDistance = bot->GetExactDist(
                entranceEntry->Pos.X, entranceEntry->Pos.Y,
                entranceEntry->Pos.Z);
            observeDistance("entrance", entranceDistance);
            if (!bot->IsInAreaTriggerRadius(entranceEntry))
            {
                transition("moving_to_entrance");
                bool const matchingRecoveryPath = matchingNativeRecoveryPath();
                bool const recoveryPathStalled = noProgressExpired();
                if (matchingRecoveryPath && !recoveryPathStalled)
                {
                    // The native generator already owns the exact scoped
                    // recovery path. Re-submitting the same Move intent on
                    // every death tick restarts that generator and can reduce
                    // a corpse run to a few yards of progress per minute.
                    result = "native_instance_runback_in_progress";
                    return true;
                }
                if (recoveryPathStalled && matchingRecoveryPath
                    && state.NativeRecoveryMovementRetryCount == 0)
                {
                    // The existing native generator has stalled. Invalidate
                    // only the evidence, then let the typed movement intent
                    // ask the movement executor for exactly one fresh native
                    // path. The executor remains the sole MotionMaster owner.
                    state.ActivePathValid = false;
                    ++state.NativeRecoveryMovementRetryCount;
                    BotActionArbitration::Outcome const repathOutcome =
                        ExecuteNativeActionIntent(state, bot,
                        BotNativeAction::Move{ entranceEntry->Pos.X,
                            entranceEntry->Pos.Y, entranceEntry->Pos.Z },
                        BotMovementArbitration::Owner::Recovery,
                        BotMovementArbitration::Priority::Recovery);
                    bool const repathed = repathOutcome.Result
                        == BotActionArbitration::Disposition::Committed;
                    result = repathed
                        ? "native_instance_runback_repath_submitted"
                        : "native_instance_runback_repath_rejected";
                    if (repathed)
                    {
                        state.NativeRecoveryEpisodeLastProgressMs = nowMs;
                        return true;
                    }
                    return terminal("native_runback_no_progress");
                }
                if (recoveryPathStalled && matchingRecoveryPath)
                    return terminal("native_runback_no_progress");
                BotActionArbitration::Outcome const moveOutcome =
                    ExecuteNativeActionIntent(state, bot,
                    BotNativeAction::Move{ entranceEntry->Pos.X,
                        entranceEntry->Pos.Y, entranceEntry->Pos.Z },
                    BotMovementArbitration::Owner::Recovery,
                    BotMovementArbitration::Priority::Recovery);
                bool const moving = moveOutcome.Result
                    == BotActionArbitration::Disposition::Committed;
                if (!moving)
                    ++state.NativeRecoveryMovementRetryCount;
                result = moving ? "native_instance_runback_moving"
                    : "native_instance_runback_path_retryable";
                if (state.NativeRecoveryMovementRetryCount
                        >= MaximumMovementRejections
                    || noProgressExpired())
                    return terminal("native_runback_no_progress");
                return true;
            }

            transition("entrance_submitted");
            ExecuteNativeActionIntent(state, bot,
                BotNativeAction::AreaTrigger{ entranceEntry->ID },
                BotMovementArbitration::Owner::Recovery,
                BotMovementArbitration::Priority::Recovery);
            if (bot->IsBeingTeleportedFar())
            {
                transition("entrance_worldport_pending");
                result = "native_instance_entrance_submitted";
                return true;
            }
            ++state.NativeRecoveryEntranceRejectionCount;
            result = "native_instance_entrance_rejected";
            if (state.NativeRecoveryEntranceRejectionCount
                    >= MaximumEntranceRejections
                || noProgressExpired())
                return terminal("native_runback_no_progress");
            return true;
        }

        if (Cohort().Config.ValidationRouteEnable
            && state.ValidationCohortLocked)
        {
            transition("corpse_authority_wait");
            ++state.NativeRecoveryReclaimRejectionCount;
            result = corpseCrossMap
                ? "native_corpse_cross_map_unreachable"
                : "native_corpse_unavailable";
            if (state.NativeRecoveryReclaimRejectionCount
                    >= MaximumReclaimRejections
                || noProgressExpired())
                return terminal("native_runback_no_progress");
            return true;
        }

        result = corpseCrossMap ? "native_corpse_cross_map_unreachable"
            : "native_corpse_unavailable";
        return false;
    }

    state.NativeRecoveryEntranceRequired = false;
    float const corpseDistance = bot->GetExactDist(corpse->GetPositionX(),
        corpse->GetPositionY(), corpse->GetPositionZ());
    observeDistance("corpse", corpseDistance);
    if (!corpse->IsWithinDistInMap(bot, CORPSE_RECLAIM_RADIUS, true))
    {
        transition("moving_to_corpse");
        BotActionArbitration::Outcome const moveOutcome =
            ExecuteNativeActionIntent(state, bot,
            BotNativeAction::Move{ corpse->GetPositionX(),
                corpse->GetPositionY(), corpse->GetPositionZ() },
            BotMovementArbitration::Owner::Recovery,
            BotMovementArbitration::Priority::Recovery);
        bool const moving = moveOutcome.Result
            == BotActionArbitration::Disposition::Committed;
        if (!moving)
            ++state.NativeRecoveryMovementRetryCount;
        result = moving ? "native_corpse_run_moving" : "native_corpse_path_retryable";
        if (state.NativeRecoveryMovementRetryCount
                >= MaximumMovementRejections
            || noProgressExpired())
            return terminal("native_runback_no_progress");
        return true;
    }

    time_t const reclaimReadyAt = corpse->GetGhostTime()
        + bot->GetCorpseReclaimDelay(
            corpse->GetType() == CORPSE_RESURRECTABLE_PVP);
    if (reclaimReadyAt > GameTime::GetGameTime())
    {
        transition("reclaim_delay_pending");
        result = "native_reclaim_delay_pending";
        return true;
    }

    transition("reclaim_submitted");
    ExecuteNativeActionIntent(state, bot,
        BotNativeAction::ReclaimCorpse{ corpse->GetGUID() });
    if (bot->IsAlive())
    {
        transition("completed");
        result = "native_corpse_reclaimed";
        return true;
    }

    ++state.NativeRecoveryReclaimRejectionCount;
    result = "native_reclaim_rejected";
    if (state.NativeRecoveryReclaimRejectionCount
            >= MaximumReclaimRejections
        || noProgressExpired())
        return terminal("native_runback_no_progress");
    return true;
}

bool BotWorldPopulationMgr::AreNativeRaidRecoveryControlledUnitsReady(Player* bot) const
{
    if (!bot)
        return false;

    auto unitReady = [](Unit* unit) -> bool
    {
        return unit && unit->IsInWorld() && unit->IsAlive() && !unit->IsInCombat()
            && !unit->GetVictim() && unit->getAttackers().empty()
            && !unit->HasUnitState(UNIT_STATE_CASTING | UNIT_STATE_MOVING)
            && !unit->GetCurrentSpell(CURRENT_GENERIC_SPELL)
            && !unit->GetCurrentSpell(CURRENT_CHANNELED_SPELL)
            && !unit->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL);
    };

    Pet* pet = bot->GetPet();
    if (bot->getClass() == CLASS_HUNTER)
    {
        bool hasStoredPet = bot->GetPlayerPetDataCurrent() != nullptr;
        if (!hasStoredPet)
            for (uint8 slot = PET_SLOT_FIRST_ACTIVE_SLOT; slot <= PET_SLOT_LAST_ACTIVE_SLOT; ++slot)
                if (PlayerPetData const* stored = bot->GetPlayerPetDataBySlot(slot);
                    stored && stored->Type == HUNTER_PET && stored->PetId && stored->CreatureId)
                {
                    hasStoredPet = true;
                    break;
                }
        if (!hasStoredPet || !unitReady(pet))
            return false;
    }
    else if (pet && !unitReady(pet))
        return false;

    for (Unit* controlled : bot->m_Controlled)
        if (controlled && controlled != pet && !unitReady(controlled))
            return false;
    return true;
}

bool BotWorldPopulationMgr::TryRestoreNativeRaidRecoveryPet(WorldBotState& state, Player* bot)
{
    if (!bot || bot->getClass() != CLASS_HUNTER)
        return false;

    uint64 const nowMs = NowMs();
    PlayerPetData const* petData = bot->GetPlayerPetDataCurrent();
    uint8 petSlot = petData ? petData->Slot : PET_SLOT_FIRST_ACTIVE_SLOT;
    if (!petData)
        for (uint8 slot = PET_SLOT_FIRST_ACTIVE_SLOT; slot <= PET_SLOT_LAST_ACTIVE_SLOT; ++slot)
            if (PlayerPetData const* stored = bot->GetPlayerPetDataBySlot(slot);
                stored && stored->Type == HUNTER_PET && stored->PetId && stored->CreatureId)
            {
                petData = stored;
                petSlot = slot;
                break;
            }

    if (!petData || !petData->PetId || !petData->CreatureId)
    {
        state.LastPetReadinessAction = "hunter_pet_unprovisioned";
        return true;
    }
    state.LastPetReadinessPetId = petData->PetId;
    state.LastPetReadinessPetEntry = petData->CreatureId;

    Pet* pet = bot->GetPet();
    if (!pet)
    {
        static uint32 const callPetSpells[] = { 883, 83242, 83243, 83244, 83245 };
        if (petSlot > PET_SLOT_LAST_ACTIVE_SLOT)
        {
            state.LastPetReadinessAction = "hunter_pet_slot_invalid";
            return true;
        }
        std::string const key = "native_recovery_hunter:call_pet:" + std::to_string(petSlot);
        auto retry = state.ReadinessRetryUntilMs.find(key);
        if (retry != state.ReadinessRetryUntilMs.end() && retry->second > nowMs)
            return true;
        uint32 const spellId = callPetSpells[petSlot - PET_SLOT_FIRST_ACTIVE_SLOT];
        std::string failure;
        if (bot->HasSpell(spellId) && TryCastFriendlySpell(bot, bot, spellId, &failure))
        {
            state.LastPetReadinessAction = key;
            state.ReadinessRetryUntilMs[key] = nowMs + 3000;
            return true;
        }
        state.LastPetReadinessAction = "hunter_pet_call_failed:" +
            (failure.empty() ? std::string("spell_unknown") : failure);
        state.ReadinessRetryUntilMs[key] = nowMs + 3000;
        return true;
    }
    if (pet->IsAlive())
        return false;

    std::string const key = "native_recovery_hunter:revive_pet";
    if (state.HunterPetRevivePendingUntilMs > nowMs)
        return true;
    if (state.HunterPetRevivePendingUntilMs)
    {
        state.HunterPetRevivePendingUntilMs = 0;
        state.ReadinessRetryUntilMs[key] = nowMs + 1000;
    }
    auto retry = state.ReadinessRetryUntilMs.find(key);
    if (retry != state.ReadinessRetryUntilMs.end() && retry->second > nowMs)
        return true;
    std::string failure;
    if (bot->HasSpell(982) && TryCastFriendlySpell(bot, bot, 982, &failure))
    {
        SpellInfo const* reviveInfo = sSpellMgr->GetSpellInfo(982);
        uint64 const castTimeMs = reviveInfo
            ? uint64(std::max<int32>(0, reviveInfo->CalcCastTime(bot->getLevel()))) : 0;
        state.HunterPetReviveStartedMs = nowMs;
        state.HunterPetRevivePendingUntilMs = nowMs + std::max<uint64>(5000, castTimeMs + 3000);
        ++state.HunterPetReviveAttemptCount;
        state.ReadinessRetryUntilMs[key] = state.HunterPetRevivePendingUntilMs;
        state.LastPetReadinessAction = "native_recovery_hunter_pet_revive_submitted";
        return true;
    }
    state.LastPetReadinessAction = "native_recovery_hunter_pet_revive_failed:" +
        (failure.empty() ? std::string("spell_unknown") : failure);
    state.ReadinessRetryUntilMs[key] = nowMs + 3000;
    return true;
}

void BotWorldPopulationMgr::TryRespondNativeRaidReadyCheck(WorldBotState& state, Player* bot)
{
    RaidRuntime& raid = Cohort().Raid;
    if (!bot || !raid.NativeReadyCheckPending
        || raid.NativeReadyCheckActionAttemptId != raid.AttemptId
        || raid.NativeReadyCheckActionWipeGeneration != raid.WipeGeneration
        || raid.NativeReadyCheckAssignmentGeneration != raid.AssignmentGeneration
        || state.NativeReadyCheckRequestGenerationResponded == raid.NativeReadyCheckActionGeneration)
        return;

    if (state.NativeReadyCheckStableGeneration != raid.NativeReadyCheckActionGeneration)
    {
        state.NativeReadyCheckStableGeneration = raid.NativeReadyCheckActionGeneration;
        state.NativeReadyCheckStableSinceMs = 0;
    }
    uint32 const guid = bot->GetGUID().GetCounter();
    auto const roster = raid.RosterByGuid.find(guid);
    bool const postWipeControlledUnitsReady = !raid.WipeGeneration
        || (BotRaidAreaAuthority::IsAllOffenseSuppressed(bot->GetGUID().GetRawValue())
            && AreNativeRaidRecoveryControlledUnitsReady(bot));
    bool const nativeHostileResetObserved = raid.NativeHostileInactivityObserved
        && raid.NativeHostileResetGeneration > raid.NativeHostileResetGenerationAtWipe;
    bool const postWipeNativeResetReady = !raid.WipeGeneration
        || Cohort().Config.ValidationRouteBossRecovery != ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
        || ((raid.BossResetGeneration > raid.BossResetGenerationAtWipe || nativeHostileResetObserved)
            && !raid.NativeHostileActivityActive);
    bool const independentlyReady = raid.RosterComplete && raid.UniqueLeases
        && raid.RosterCompositionValid && raid.DifficultyMatches
        && !raid.EncounterInProgress && raid.AssignmentGeneration > 0
        && roster != raid.RosterByGuid.end()
        && roster->second.Active && roster->second.LeaseOwned
        && bot->IsInWorld() && bot->IsAlive() && !bot->IsInCombat()
        && !bot->GetVictim() && bot->getAttackers().empty()
        && !bot->IsNonMeleeSpellCast(false)
        && postWipeControlledUnitsReady
        && postWipeNativeResetReady
        && bot->GetSession()
        && bot->GetGroup() && bot->GetGroup()->GetGUID() == raid.GroupGuid
        && bot->GetMapId() == raid.MapId && bot->GetInstanceId() == raid.InstanceId;
    if (!independentlyReady)
    {
        state.NativeReadyCheckStableSinceMs = 0;
        return;
    }

    uint64 const nowMs = NowMs();
    if (!state.NativeReadyCheckStableSinceMs)
    {
        state.NativeReadyCheckStableSinceMs = nowMs;
        return;
    }
    if (nowMs - state.NativeReadyCheckStableSinceMs < 5000)
        return;

    WorldPacket response(MSG_RAID_READY_CHECK, 1);
    response << uint8(1);
    bot->GetSession()->HandleRaidReadyCheckOpcode(response);
    state.NativeReadyCheckRequestGenerationResponded = raid.NativeReadyCheckActionGeneration;
    state.NativeReadyCheckStableSinceMs = 0;
    if (raid.NativeReadyCheckResponders.insert(guid).second)
    {
        raid.NativeReadyCheckResponseCount = uint32(raid.NativeReadyCheckResponders.size());
        ++raid.EvidenceSequence;
    }
    if (raid.NativeReadyCheckResponseCount == raid.ExpectedSize)
    {
        raid.NativeReadyCheckPending = false;
        raid.NativeReadyCheckActionObserved = true;
        raid.NativeReadyCheckActionEvidenceSequence = raid.EvidenceSequence;
    }
}
