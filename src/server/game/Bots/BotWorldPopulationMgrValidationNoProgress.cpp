#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "GameTime.h"
#include "MotionMaster.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <functional>
#include <string>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;
    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
}
}

bool BotWorldPopulationMgr::MaybeValidationPrerequisiteNoProgressAssist(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity,
    std::function<bool(Creature const*)> const& isValidationRouteScriptTarget,
    std::function<bool(uint32)> const& isValidationRoutePackEntry,
    std::function<bool(Unit*, char const*)> const& recordValidationRouteTrashKill,
    Unit* prerequisiteTarget, char const* context)
{
    if (!prerequisiteTarget || !prerequisiteTarget->IsAlive() || !bot || !bot->IsValidAttackTarget(prerequisiteTarget))
        return false;

    Creature* creature = prerequisiteTarget->ToCreature();
    if (!creature || ((creature->IsDungeonBoss() || creature->isWorldBoss()) && !isValidationRouteScriptTarget(creature)))
        return false;

    bool listedBossAdd = Cohort().Config.ValidationRouteKind == "boss"
        && std::find(Cohort().Config.ValidationRouteAddTargetEntries.begin(), Cohort().Config.ValidationRouteAddTargetEntries.end(), creature->GetEntry())
            != Cohort().Config.ValidationRouteAddTargetEntries.end();
    if (listedBossAdd)
    {
        // Boss adds legitimately churn through shared focus and may have no
        // legal action during their final global cooldown or range step.
        // Their dedicated add handler and the external watchdog own
        // progress; never let that transient handoff latch a route failure.
        state.ValidationRouteCombatNoProgressCount = 0;
        state.ValidationRouteCombatNoProgressSinceMs = 0;
        state.ValidationRoutePackNoProgressCount = 0;
        state.ValidationRoutePackNoProgressSinceMs = 0;
        return false;
    }

    float routeProximity = prerequisiteTarget->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
    if (!isValidationRouteScriptTarget(creature) && routeProximity > 120.0f)
        return false;

    float healthPct = UnitHealthPct(prerequisiteTarget);
    std::string contextText = context ? context : "";
    // Trash route liveness is a party-level contract owned by the tank. A
    // ranged bot can reject several tactical candidate paths in one second;
    // letting that decision frequency terminalize the shared pack made a
    // still-viable corridor pull fail before the tank could reapproach it.
    if (Cohort().Config.ValidationRouteKind != "boss" && std::string(GetDungeonRole(bot)) != "tank")
    {
        state.ValidationRouteCombatNoProgressCount = 0;
        state.ValidationRouteCombatNoProgressSinceMs = 0;
        state.ValidationRoutePackNoProgressCount = 0;
        state.ValidationRoutePackNoProgressSinceMs = 0;
        return false;
    }

    constexpr uint64 noProgressSampleIntervalMs = 5000;
    uint64 nowMs = NowMs();
    auto elapsedNoProgressSamples = [nowMs, noProgressSampleIntervalMs](uint64& sinceMs) -> uint32
    {
        if (!sinceMs)
        {
            sinceMs = nowMs;
            return 0;
        }
        return uint32((nowMs - sinceMs) / noProgressSampleIntervalMs);
    };
    auto resetCombatNoProgress = [&state, nowMs]() -> void
    {
        state.ValidationRouteCombatNoProgressCount = 0;
        state.ValidationRouteCombatNoProgressSinceMs = nowMs;
    };
    auto resetPackNoProgress = [&state, nowMs]() -> void
    {
        state.ValidationRoutePackNoProgressCount = 0;
        state.ValidationRoutePackNoProgressSinceMs = nowMs;
    };
    auto lastCombatAttemptTargetsDifferentPackMob = [&state, prerequisiteTarget, &isValidationRoutePackEntry]() -> bool
    {
        return !state.LastCombatAttempt.TargetGuid.IsEmpty()
            && state.LastCombatAttempt.TargetGuid != prerequisiteTarget->GetGUID()
            && isValidationRoutePackEntry(state.LastCombatAttempt.TargetEntry);
    };
    bool bossRouteContext = Cohort().Config.ValidationRouteKind == "boss"
        && (contextText.rfind("boss_route_", 0) == 0
            || (isValidationRouteScriptTarget(creature) && contextText.rfind("route_target_", 0) == 0)
            || contextText.find("force_tank_focus") != std::string::npos
            || contextText.find("assist_focus") != std::string::npos);
    bool unengagedBossPrerequisite = Cohort().Config.ValidationRouteKind == "boss"
        && !isValidationRouteScriptTarget(creature)
        && !prerequisiteTarget->IsInCombat()
        && !prerequisiteTarget->GetVictim();
    auto refreshRouteProgress = [&](char const* reason, uint32 threshold) -> void
    {
        RecordRouteProgress(state, bot, prerequisiteTarget, reason ? reason : "route_target_observed",
            healthPct, state.ValidationRouteCombatBestHealthPct, state.ValidationRouteCombatNoProgressCount, threshold);
    };
    // A boss node may expose an ordinary prerequisite before the tank has
    // reached or pulled it. Full health while out of combat is navigation
    // state, not failed combat progress; do not latch a trash terminal that
    // can suppress the boss pull for the rest of this route generation.
    if (unengagedBossPrerequisite)
    {
        state.ValidationRouteCombatProgressTargetGuid = prerequisiteTarget->GetGUID();
        state.ValidationRouteCombatBestHealthPct = healthPct;
        resetCombatNoProgress();
        state.ValidationRoutePackProgressTargetGuid = prerequisiteTarget->GetGUID();
        state.ValidationRoutePackBestHealthPct = healthPct;
        resetPackNoProgress();
        refreshRouteProgress("unengaged_boss_prerequisite_observed", 0);
        return false;
    }
    if (bossRouteContext
        && isValidationRouteScriptTarget(creature)
        && healthPct > 0.05f)
    {
        if (state.ValidationRouteCombatProgressTargetGuid != prerequisiteTarget->GetGUID())
        {
            state.ValidationRouteCombatProgressTargetGuid = prerequisiteTarget->GetGUID();
            state.ValidationRouteCombatBestHealthPct = healthPct;
            resetCombatNoProgress();
            state.ValidationRouteBossSlowProgressCount = 0;
            refreshRouteProgress(context, 2);
        }
        if (Party().ValidationRouteBossProgressTargetGuid != prerequisiteTarget->GetGUID())
        {
            Party().ValidationRouteBossProgressTargetGuid = prerequisiteTarget->GetGUID();
            Party().ValidationRouteBossSlowProgressCount = 0;
        }

        ++Party().ValidationRouteBossSlowProgressCount;
        ++state.ValidationRouteBossSlowProgressCount;
        refreshRouteProgress(context, 2);
        return true;
    }

    if (Cohort().Config.ValidationRouteKind != "boss"
        && isValidationRoutePackEntry(creature->GetEntry())
        && recordValidationRouteTrashKill(prerequisiteTarget, "validation_route_recovery"))
        return true;

    auto maybeRoutePackNoProgressAssist = [&]() -> bool
    {
        if (isValidationRouteScriptTarget(creature))
            return false;

        if (state.ValidationRoutePackProgressTargetGuid.IsEmpty())
        {
            state.ValidationRoutePackProgressTargetGuid = prerequisiteTarget->GetGUID();
            state.ValidationRoutePackBestHealthPct = healthPct;
            resetPackNoProgress();
            return false;
        }

        if (state.ValidationRoutePackProgressTargetGuid == prerequisiteTarget->GetGUID())
        {
            if (healthPct + 0.02f < state.ValidationRoutePackBestHealthPct)
            {
                state.ValidationRoutePackBestHealthPct = healthPct;
                resetPackNoProgress();
                return false;
            }
        }
        else
        {
            state.ValidationRoutePackProgressTargetGuid = prerequisiteTarget->GetGUID();
            state.ValidationRoutePackBestHealthPct = healthPct;
            // A prerequisite switch is fresh progress context. Carrying the
            // previous mob's counter into this target can immediately trip
            // the pack failure threshold while the tank is only pathing into
            // range, especially during the final pull before a boss.
            resetPackNoProgress();
            return false;
        }

        uint32 packNoProgressThreshold = Cohort().Config.ValidationRouteKind == "boss" ? 5 : 15;
        state.ValidationRoutePackNoProgressCount = elapsedNoProgressSamples(state.ValidationRoutePackNoProgressSinceMs);
        if (state.ValidationRoutePackNoProgressCount < packNoProgressThreshold)
            return false;

        std::string raw = BuildRawJson(bot, prerequisiteTarget);
        std::string semantic = BuildSemanticJson(bot, prerequisiteTarget, "validation_route_pack_no_progress", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_failed", prerequisiteTarget, "validation_trash_no_progress", raw.c_str(), semantic.c_str(), healthPct, Cohort().Config.ValidationRouteTargetEntry);
        MarkValidationRouteTrashFailed(state, bot, power, stage, activity, prerequisiteTarget, "validation_trash_no_progress", "validation_route_pack_no_progress", healthPct, Cohort().Config.ValidationRouteTargetEntry, state.ValidationRoutePackBestHealthPct, state.ValidationRoutePackNoProgressCount, packNoProgressThreshold);
        state.ValidationRoutePackBestHealthPct = UnitHealthPct(prerequisiteTarget);
        resetPackNoProgress();
        state.LastNoProgressReason = "validation_trash_no_progress";
        return true;
    };

    bool trashRouteTargetContext = Cohort().Config.ValidationRouteKind != "boss"
        && isValidationRouteScriptTarget(creature)
        && contextText.rfind("route_target_", 0) == 0;
    if (trashRouteTargetContext)
    {
        if (std::string(GetDungeonRole(bot)) != "tank")
            return false;

        if (lastCombatAttemptTargetsDifferentPackMob())
            return false;

        if (state.ValidationRoutePackProgressTargetGuid != prerequisiteTarget->GetGUID())
        {
            state.ValidationRoutePackProgressTargetGuid = prerequisiteTarget->GetGUID();
            state.ValidationRoutePackBestHealthPct = healthPct;
            resetPackNoProgress();
            return false;
        }
        if (healthPct < state.ValidationRoutePackBestHealthPct)
        {
            state.ValidationRoutePackBestHealthPct = healthPct;
            resetPackNoProgress();
        }

        bool unengagedRouteTarget = !prerequisiteTarget->IsInCombat() && !prerequisiteTarget->GetVictim();
        if (unengagedRouteTarget)
            resetPackNoProgress();
        else
        {
            uint32 routeTargetNoProgressThreshold = Cohort().Config.ValidationRouteKind == "boss" ? 5 : 20;
            state.ValidationRoutePackNoProgressCount = elapsedNoProgressSamples(state.ValidationRoutePackNoProgressSinceMs);
            if (state.ValidationRoutePackNoProgressCount >= routeTargetNoProgressThreshold)
            {
                std::string raw = BuildRawJson(bot, prerequisiteTarget);
                std::string semantic = BuildSemanticJson(bot, prerequisiteTarget, "validation_route_trash_slow_progress", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_failed", prerequisiteTarget, "validation_trash_no_progress", raw.c_str(), semantic.c_str(), healthPct, Cohort().Config.ValidationRouteTargetEntry);
                MarkValidationRouteTrashFailed(state, bot, power, stage, activity, prerequisiteTarget, "validation_trash_no_progress", "validation_route_trash_slow_progress", healthPct, Cohort().Config.ValidationRouteTargetEntry, state.ValidationRoutePackBestHealthPct, state.ValidationRoutePackNoProgressCount, routeTargetNoProgressThreshold);
                state.ValidationRoutePackBestHealthPct = UnitHealthPct(prerequisiteTarget);
                resetPackNoProgress();
                state.LastNoProgressReason = "validation_trash_no_progress";
                return true;
            }
        }
    }

    if (state.ValidationRouteCombatProgressTargetGuid != prerequisiteTarget->GetGUID())
    {
        state.ValidationRouteCombatProgressTargetGuid = prerequisiteTarget->GetGUID();
        state.ValidationRouteCombatBestHealthPct = healthPct;
        resetCombatNoProgress();
        state.ValidationRouteBossSlowProgressCount = 0;
        refreshRouteProgress(context, Cohort().Config.ValidationRouteKind == "boss" ? 4 : 12);
        maybeRoutePackNoProgressAssist();
        return false;
    }

    if (healthPct < state.ValidationRouteCombatBestHealthPct)
    {
        state.ValidationRouteCombatBestHealthPct = healthPct;
        resetCombatNoProgress();
        state.ValidationRouteBossSlowProgressCount = 0;
        refreshRouteProgress(context, Cohort().Config.ValidationRouteKind == "boss" ? 4 : 12);
        if (!trashRouteTargetContext)
        {
            state.ValidationRoutePackProgressTargetGuid = prerequisiteTarget->GetGUID();
            state.ValidationRoutePackBestHealthPct = healthPct;
            resetPackNoProgress();
        }
        return false;
    }

    if (!bossRouteContext && maybeRoutePackNoProgressAssist())
        return true;

    bool bossRouteNoProgress = bossRouteContext && isValidationRouteScriptTarget(creature);
    uint32 noProgressThreshold = bossRouteNoProgress ? 2 : (Cohort().Config.ValidationRouteKind == "boss" ? 4 : 12);
    state.ValidationRouteCombatNoProgressCount = elapsedNoProgressSamples(state.ValidationRouteCombatNoProgressSinceMs);
    refreshRouteProgress(context, noProgressThreshold);
    if (state.ValidationRouteCombatNoProgressCount < noProgressThreshold)
        return false;

    // A trash route can expose the next target after an earlier pack was
    // cleared but before the tank has reached or pulled it. Treat any such
    // out-of-combat observation as a navigation retry, not failed combat
    // evidence, regardless of prior engagement elsewhere in the node.
    if (Cohort().Config.ValidationRouteKind != "boss"
        && !prerequisiteTarget->IsInCombat()
        && !prerequisiteTarget->GetVictim())
    {
        if (std::string(GetDungeonRole(bot)) != "tank")
        {
            state.ValidationRouteCombatNoProgressCount = 0;
            state.ValidationRouteCombatNoProgressSinceMs = 0;
            state.ValidationRoutePackNoProgressCount = 0;
            state.ValidationRoutePackNoProgressSinceMs = 0;
            return false;
        }

        std::string raw = BuildRawJson(bot, prerequisiteTarget);
        std::string semantic = BuildSemanticJson(bot, prerequisiteTarget, "validation_route_unengaged_trash_repath", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_recovery", prerequisiteTarget, "unengaged_trash_target_repath", raw.c_str(), semantic.c_str(), healthPct, Cohort().Config.ValidationRouteTargetEntry);
        uint64 nowMs = NowMs();
        for (WorldBotState& cohortState : Party().Bots)
        {
            if (Player* member = GetLoadedBot(cohortState))
                member->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            cohortState.TargetGuid.Clear();
            cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
            cohortState.ValidationRoutePackProgressTargetGuid.Clear();
            cohortState.ValidationRouteCombatBestHealthPct = 1.0f;
            cohortState.ValidationRoutePackBestHealthPct = 1.0f;
            cohortState.ValidationRouteCombatNoProgressCount = 0;
            cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
            cohortState.ValidationRoutePackNoProgressCount = 0;
            cohortState.ValidationRoutePackNoProgressSinceMs = 0;
            cohortState.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();
            cohortState.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();
            cohortState.ActivePathValid = false;
            cohortState.LastNoProgressReason = "unengaged_trash_target_repath";
            cohortState.LoopRecoveryCooldownUntilMs = nowMs + 3000;
        }
        return true;
    }

    std::string raw = BuildRawJson(bot, prerequisiteTarget);
    std::string semantic = BuildSemanticJson(bot, prerequisiteTarget, "validation_route_prerequisite_no_progress", &power, stage, activity);
    RecordEvent(state, bot, "validation_route_recovery", prerequisiteTarget, context ? context : "prerequisite_no_health_progress", raw.c_str(), semantic.c_str(), healthPct, Cohort().Config.ValidationRouteTargetEntry);
    if (bossRouteNoProgress)
        state.LastNoProgressReason = context ? context : "boss_route_no_health_progress";
    else
        MarkValidationRouteTrashFailed(state, bot, power, stage, activity, prerequisiteTarget, "validation_trash_no_progress", "validation_route_prerequisite_no_progress", healthPct, Cohort().Config.ValidationRouteTargetEntry, state.ValidationRouteCombatBestHealthPct, state.ValidationRouteCombatNoProgressCount, noProgressThreshold);
    state.ValidationRouteCombatBestHealthPct = UnitHealthPct(prerequisiteTarget);
    resetCombatNoProgress();
    state.ValidationRoutePackBestHealthPct = UnitHealthPct(prerequisiteTarget);
    resetPackNoProgress();
    return true;
}

