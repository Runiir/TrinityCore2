#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotLongTermProgressionBrain.h"
#include "Creature.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <sstream>
#include <string>

void BotWorldPopulationMgr::HandleBotDeath(WorldBotState& state, Player* bot, uint32 diff)
{
    if (!bot->IsAlive())
    {
        state.DeadTimer += diff;
        if (!state.DeathEpisodeRecorded)
        {
            state.DeathEpisodeRecorded = true;
            ++Cohort().Metrics.Deaths;
            Unit* lastTarget = state.TargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, state.TargetGuid);
            Creature const* lastCreature = lastTarget ? lastTarget->ToCreature() : nullptr;
            bool bossDeath = lastCreature && (lastCreature->IsDungeonBoss() || lastCreature->isWorldBoss());
            char const* deathSituation = bossDeath ? (bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss") : "corpse_recovery";
            std::string raw = BuildRawJson(bot, lastTarget);
            std::string semantic = BuildSemanticJson(bot, lastTarget, deathSituation);
            MarkDeathDangerZone(state, bot, lastTarget);
            RecordEvent(state, bot, "death", nullptr, "dead", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Metrics.Deaths);
            if (state.RecentDeathCount >= Cohort().Config.MaxDeathsBeforeFallback)
                RecordEvent(state, bot, "repeated_death", nullptr, "danger_zone", raw.c_str(), semantic.c_str(), float(state.RecentDeathCount), Cohort().Metrics.Deaths);
            if (bossDeath)
            {
                BossMechanicFeatures features = BuildBossMechanicFeatures(bot, lastTarget);
                if (features.RaidEncounter)
                {
                    ++state.RaidWipes;
                    BotRolePowerBreakdown deathPower = BotLongTermProgressionBrain::CalculateRolePower(bot);
                    BotProgressionStage deathStage = BotLongTermProgressionBrain::ClassifyStage(bot, deathPower);
                    RaidRoleAssignment assignment = BuildRaidRoleAssignment(bot);
                    RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(bot, lastTarget, assignment, features);
                    RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(bot, lastTarget, assignment, features);
                    RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(bot, deathPower, deathStage);
                    HeroicRaidProgression progression = BuildHeroicRaidProgression(state, bot, deathPower, deathStage);
                    RecordRaidTelemetry(state, bot, lastTarget, "raid_wipe", "death", features, assignment, anchors, adapter, gearPlan, progression, raw.c_str(), semantic.c_str(), features.DangerScore, Cohort().Metrics.Deaths);
                }
                RecordBossReplay(state, bot, lastTarget, features, "boss_mechanic_failure", raw.c_str(), semantic.c_str(), "{\"action\":\"survive_boss_mechanic\"}", "{\"reason\":\"bot_died_during_boss\"}");
            }
        }

        // Preserve the triggering native death edge before entering the
        // shared terminal hold. This keeps the final immutable bundle
        // deterministic without allowing the dead member to enter any
        // release/runback or direct-recovery path.
        if (validationAttemptFailed)
        {
            holdValidationAttemptFailure();
            return;
        }

        uint64 const deathNowMs = NowMs();
        bool const typedApproachIntentCurrent =
            state.NativeBattleResDecision == "reserved_approach"
            && state.NativeBattleResApproachIntentDecisionAtMs
                == state.NativeBattleResDecisionAtMs
            && state.NativeBattleResApproachIntentAcceptedUntilMs
                > deathNowMs;
        bool const nativeBattleResDecisionObserved = state.NativeBattleResDecisionUntilMs > deathNowMs
            && (typedApproachIntentCurrent
                || state.NativeBattleResDecision == "reserved_cast_submitted"
                || state.NativeBattleResDecision.rfind("declined_", 0) == 0);
        // Give the coordinator one short, named observation window to see the
        // native death and publish a CR reservation/decline. An explicit
        // decision opens recovery immediately; it is never hidden behind the
        // legacy five-second free-roam delay.
        bool const nativeDeathDecisionWindowComplete = state.DeadTimer >= 1500;
        bool const deathRecoveryReady = Cohort().Config.ValidationRouteEnable
            ? (nativeBattleResDecisionObserved || nativeDeathDecisionWindowComplete)
            : state.DeadTimer >= 5000;
        if (deathRecoveryReady)
        {
            // Phase 1 Magmaw is a native-encounter smoke, not a tactical
            // recovery exercise.  Keep a dead member in place while any
            // exact cohort member remains alive or the roster cannot be
            // reconstructed.  Only the native all-dead path below may then
            // release corpses and let the encounter script reset/respawn.
            if (Cohort().Config.ValidationRouteBossRecovery == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly)
            {
                RaidRuntime const& raid = Cohort().Raid;
                bool const exactSignalRoster = raid.RosterComplete
                    && raid.ExpectedSize == Cohort().Config.TargetPopulation
                    && raid.RosterByGuid.size() == Cohort().Config.TargetPopulation
                    && raid.NativeSignalsByGuid.size() == raid.RosterByGuid.size()
                    && std::all_of(raid.RosterByGuid.begin(), raid.RosterByGuid.end(),
                        [&raid](auto const& row) { return raid.NativeSignalsByGuid.count(row.first) == 1; });
                // UpdateRaidRuntime latches this identity before UpdateBot is
                // allowed to release the first corpse.  Preserve that latch
                // while ghosts worldport outside BWD: requiring every member
                // to remain in-world here would let the first release block
                // the remaining nine forever.
                bool const nativeFullWipeLatched = raid.Active
                    && raid.AttemptId == Cohort().AttemptId
                    && raid.NativeRecoveryHoldActive
                    && raid.NativeRecoveryRouteGeneration == Party().ValidationRouteGeneration
                    && raid.NativeRecoveryNodeId == Cohort().Config.ValidationRouteNodeId
                    && raid.WipeState == "wiped"
                    && raid.WipeGeneration > 0
                    && exactSignalRoster
                    && std::all_of(raid.NativeSignalsByGuid.begin(), raid.NativeSignalsByGuid.end(),
                        [&raid](auto const& row)
                        {
                            return row.second.WipeGeneration == raid.WipeGeneration
                                && row.second.DeathSequence > 0;
                        });
                uint32 loadedMembers = 0;
                uint32 aliveMembers = 0;
                bool rosterComplete = Party().Bots.size() == Cohort().Config.TargetPopulation;
                for (WorldBotState const& cohortState : Party().Bots)
                {
                    Player* member = GetLoadedBot(cohortState);
                    if (!member || !member->IsInWorld()
                        || member->GetMapId() != Cohort().Config.ValidationRouteMapId
                        || member->GetInstanceId() != bot->GetInstanceId())
                    {
                        rosterComplete = false;
                        continue;
                    }

                    ++loadedMembers;
                    if (member->IsAlive())
                        ++aliveMembers;
                }

                if (!nativeFullWipeLatched)
                {
                    std::string raw = BuildRawJson(bot, nullptr);
                    std::ostringstream gateRaw;
                    gateRaw << "{\"base\":" << raw
                            << ",\"native_recovery_gate\":{\"policy\":\"native_full_wipe_only\""
                            << ",\"authority\":\"native_encounter\""
                            << ",\"assistance\":\"none\""
                            << ",\"direct_respawn\":false"
                            << ",\"direct_state_manufacture\":false"
                            << ",\"loaded_members\":" << loadedMembers
                            << ",\"alive_members\":" << aliveMembers
                            << ",\"expected_members\":" << Cohort().Config.TargetPopulation
                            << ",\"roster_complete\":" << (rosterComplete ? "true" : "false")
                            << ",\"wipe_latched\":false"
                            << ",\"wipe_state\":\"" << JsonEscape(raid.WipeState) << "\""
                            << ",\"wipe_generation\":" << raid.WipeGeneration
                            << ",\"attempt_id\":" << raid.AttemptId << "}}";
                    std::string semantic = BuildSemanticJson(bot, nullptr, "native_raid_recovery");
                    char const* reason = rosterComplete
                        && loadedMembers == Cohort().Config.TargetPopulation && aliveMembers
                            ? "native_full_wipe_wait_partial_death"
                            : "native_full_wipe_wait_unlatched";
                    RecordEvent(state, bot, "validation_route_recovery", nullptr, reason,
                        gateRaw.str().c_str(), semantic.c_str(), float(aliveMembers), loadedMembers);
                    state.LastRecoveryMode = "native_full_wipe_only";
                    state.LastRecoveryResult = reason;
                    state.LastRecoveryMs = NowMs();
                    state.LastNoProgressReason = reason;
                    state.DeadTimer = 0;
                    return;
                }

                std::string raw = BuildRawJson(bot, nullptr);
                std::ostringstream gateRaw;
                gateRaw << "{\"base\":" << raw
                        << ",\"native_recovery_gate\":{\"policy\":\"native_full_wipe_only\""
                        << ",\"authority\":\"native_encounter\""
                        << ",\"assistance\":\"none\""
                        << ",\"direct_respawn\":false"
                        << ",\"direct_state_manufacture\":false"
                        << ",\"wipe_latched\":true"
                        << ",\"wipe_generation\":" << raid.WipeGeneration
                        << ",\"attempt_id\":" << raid.AttemptId << "}}";
                std::string semantic = BuildSemanticJson(bot, nullptr, "native_raid_recovery");
                RecordEvent(state, bot, "validation_route_recovery", nullptr,
                    "native_full_wipe_latched_release_allowed", gateRaw.str().c_str(), semantic.c_str(),
                    float(raid.WipeGeneration), raid.ExpectedSize);
            }

            uint64 const recoveryNowMs = NowMs();
            bool const combatResReservationPresent = state.NativeBattleResDecision == "reserved_approach"
                || state.NativeBattleResDecision == "reserved_cast_submitted";
            bool const acceptedCombatResIntentCurrent =
                state.NativeBattleResDecision == "reserved_cast_submitted"
                || (state.NativeBattleResDecision == "reserved_approach"
                    && state.NativeBattleResApproachIntentDecisionAtMs
                        == state.NativeBattleResDecisionAtMs
                    && state.NativeBattleResApproachIntentAcceptedUntilMs
                        > recoveryNowMs);
            std::string combatResDeclineReason;
            bool const battleResReserved = combatResReservationPresent
                && acceptedCombatResIntentCurrent
                && CurrentCombatResOwnerUsable(state, bot, recoveryNowMs, combatResDeclineReason);
            if (battleResReserved)
            {
                state.LastRecoveryMode = "wait_for_reserved_combat_res";
                state.LastRecoveryResult = state.NativeBattleResDecision;
                state.LastRecoveryMs = recoveryNowMs;
                state.DeadTimer = 0;
                return;
            }
            if (combatResReservationPresent)
            {
                ObjectGuid const declinedOwner = state.NativeBattleResOwnerGuid;
                uint32 const declinedSpell = state.NativeBattleResSpellId;
                PublishNativeBattleResDecision(state, bot,
                    !acceptedCombatResIntentCurrent
                        ? "declined_typed_intent_not_current"
                        : (combatResDeclineReason.empty()
                            ? "declined_owner_unusable"
                            : combatResDeclineReason),
                    declinedOwner, declinedSpell, recoveryNowMs, recoveryNowMs + 5000);
            }
            // Certifying cohorts use one explicit recovery handshake: the
            // combat-res owner either reserves this corpse or declines it.
            // A dead bot observes that decision for 1.5 seconds and waits only
            // while a bounded reservation is current.  Decline, unavailability,
            // expiry, or a missing decision all continue through the same native
            // release, ghost runback, and corpse-recovery path as a player.
            // Non-certifying free-roam bots retain class self-res.
            if (!Cohort().Config.ValidationRouteEnable
                && TryNativeSelfResurrection(state, bot))
            {
                state.DeadTimer = 0;
                return;
            }

            // Raid trash does not necessarily drive InstanceScript's boss
            // state.  Do not release/run back a corpse merely because group
            // members look idle: the exact native instance must have
            // observed either the boss reset or a hostile-pack activity to
            // stable inactivity transition.  This is observation-only; no
            // combat stop, reset, teleport, kill, or resurrection is issued.
            if (Cohort().Config.ValidationRouteBossRecovery == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly)
            {
                RaidRuntime const& raid = Cohort().Raid;
                bool const nativeHostileResetObserved = raid.NativeHostileInactivityObserved
                    && raid.NativeHostileResetGeneration > raid.NativeHostileResetGenerationAtWipe;
                bool const nativeResetObserved = raid.BossResetGeneration > raid.BossResetGenerationAtWipe
                    || nativeHostileResetObserved;
                bool const nativeHostileRecoveryBlocked = raid.NativeHostileActivityActive || !nativeResetObserved;
                if (nativeHostileRecoveryBlocked)
                {
                    std::string raw = BuildRawJson(bot, nullptr);
                    std::ostringstream gateRaw;
                    gateRaw << "{\"base\":" << raw
                            << ",\"native_recovery_reset_gate\":{\"policy\":\"native_full_wipe_only\""
                            << ",\"authority\":\"native_encounter\""
                            << ",\"assistance\":\"none\""
                            << ",\"hostile_activity_active\":" << (raid.NativeHostileActivityActive ? "true" : "false")
                            << ",\"hostile_activity_reason\":\"" << JsonEscape(raid.NativeHostileActivityReason) << "\""
                            << ",\"hostile_reset_observed\":" << (nativeHostileResetObserved ? "true" : "false")
                            << ",\"boss_reset_observed\":" << (raid.BossResetGeneration > raid.BossResetGenerationAtWipe ? "true" : "false")
                            << ",\"direct_respawn\":false"
                            << ",\"direct_state_manufacture\":false}}";
                    std::string semantic = BuildSemanticJson(bot, nullptr, "native_raid_recovery");
                    char const* reason = raid.NativeHostileActivityActive
                        ? "native_recovery_wait_hostile_activity"
                        : "native_recovery_wait_native_reset";
                    RecordEvent(state, bot, "validation_route_recovery", nullptr, reason,
                        gateRaw.str().c_str(), semantic.c_str(),
                        float(raid.NativeHostileActivityEntry), raid.NativeHostileActivityGuid.GetCounter());
                    state.LastRecoveryMode = "native_full_wipe_only";
                    state.LastRecoveryResult = reason;
                    state.LastRecoveryMs = NowMs();
                    state.LastNoProgressReason = reason;
                    state.DeadTimer = 0;
                    return;
                }
            }

            // A critical-role death can make the survivors retreat after combat
            // drops. Do not let the ordinary five-second recovery resurrect the
            // dead member at an individual safe position while that retreat is
            // still moving. Once the survivors arrive, the route handler binds
            // the shared rendezvous override and the existing recovery path
            // resurrects the dead member beside them.
            bool validationRetreatRendezvousPending = false;
            uint64 nowMs = NowMs();
            if (Cohort().Config.ValidationRouteEnable && !state.ValidationRouteAnchorOverrideValid)
                for (WorldBotState const& cohortState : Party().Bots)
                {
                    Player* cohortBot = GetLoadedBot(cohortState);
                    bool recentRetreat = cohortState.LastRecoveryMs && nowMs >= cohortState.LastRecoveryMs
                        && nowMs - cohortState.LastRecoveryMs <= 120000;
                    bool retreatInProgress = cohortState.LastRecoveryResult.rfind("moving_", 0) == 0
                        || cohortState.LastRecoveryResult.rfind("holding_", 0) == 0;
                    if (cohortBot && cohortBot->IsAlive() && recentRetreat
                        && cohortState.LastRecoveryMode == "tactical_retreat_no_combat_res"
                        && retreatInProgress)
                    {
                        validationRetreatRendezvousPending = true;
                        break;
                    }
                }
            if (validationRetreatRendezvousPending)
            {
                state.DeadTimer = 0;
                return;
            }

            state.NativeResurrectionPendingUntilMs = 0;
            state.NativeResurrectionCasterGuid.Clear();
            state.NativeResurrectionSpellId = 0;
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "corpse_recovery");
            RecordEvent(state, bot, "death_recovery_started", nullptr, Cohort().Config.DeathRecoveryMode.c_str(), raw.c_str(), semantic.c_str(), 0.0f, state.RecentDeathCount);
            ++state.RecoveryAttemptCount;
            DeathRecoveryResult recovery = RecoverDeadBot(state, bot);
            state.DeadTimer = 0;
            state.LastRecoveryMode = recovery.Mode.empty() ? Cohort().Config.DeathRecoveryMode : recovery.Mode;
            state.LastRecoveryResult = recovery.Result;
            state.LastRecoveryMs = NowMs();
            raw = BuildRawJson(bot, nullptr);
            semantic = BuildSemanticJson(bot, nullptr, "corpse_recovery");
            if (recovery.Recovered)
            {
                state.DeathEpisodeRecorded = false;
                state.TargetGuid.Clear();
                state.QuestWork.SelectedTargetGuid.Clear();
                state.ConsecutiveSameDecisionCount = 0;
                state.IdleDecisionRepeatCount = 0;
                state.TargetChurnCount = 0;
                state.LoopRecoveryCooldownUntilMs = NowMs() + 10000;
                PersistBotPosition(bot);
                RecordEvent(state, bot, "resurrected", nullptr, recovery.Mode.c_str(), raw.c_str(), semantic.c_str());
                if (recovery.UsedFallback)
                    RecordEvent(state, bot, "teleport_fallback_used", nullptr, recovery.Result.c_str(), raw.c_str(), semantic.c_str(), float(state.RecentDeathCount), Cohort().Metrics.Deaths);
            }
            else if (recovery.InProgress)
                RecordEvent(state, bot, "death_recovery_progress", nullptr,
                    recovery.Result.c_str(), raw.c_str(), semantic.c_str(),
                    float(state.RecentDeathCount), Cohort().Metrics.Deaths);
            else
                RecordEvent(state, bot, "death_recovery_failed", nullptr, recovery.Result.c_str(), raw.c_str(), semantic.c_str(), float(state.RecentDeathCount), Cohort().Metrics.Deaths);
        }
        return;
    }
}

