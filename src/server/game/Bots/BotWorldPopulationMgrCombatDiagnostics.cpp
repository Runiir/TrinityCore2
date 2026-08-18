#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "GameTime.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <sstream>
#include <string>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

bool HasPowerForSpell(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    int32 powerCost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (powerCost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > powerCost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(powerCost);
}
}

std::string BotWorldPopulationMgr::BuildCombatAttemptSummary(WorldBotState::CombatAttemptDiagnostic const& diagnostic) const
{
    if (diagnostic.Phase.empty() && diagnostic.Result.empty())
        return "";

    std::ostringstream summary;
    summary << "phase=" << (diagnostic.Phase.empty() ? "unknown" : diagnostic.Phase);
    if (diagnostic.SpellId)
        summary << " spell=" << diagnostic.SpellId;
    if (!diagnostic.DebugName.empty())
        summary << " action=" << diagnostic.DebugName;
    if (!diagnostic.Result.empty())
        summary << " result=" << diagnostic.Result;
    if (!diagnostic.TargetGuid.IsEmpty())
        summary << " target=" << (diagnostic.SelfTarget ? "bot/" : "unit/") << diagnostic.TargetGuid.GetCounter();
    if (!diagnostic.Reason.empty())
        summary << " reason=" << diagnostic.Reason;
    return summary.str();
}

std::string BotWorldPopulationMgr::BuildRouteProgressSummary(WorldBotState::RouteProgressDiagnostic const& diagnostic) const
{
    if (diagnostic.Reason.empty() && diagnostic.Summary.empty())
        return "";

    std::ostringstream summary;
    summary << "reason=" << (diagnostic.Reason.empty() ? "route_no_progress" : diagnostic.Reason);
    if (diagnostic.TargetEntry)
        summary << " target=" << diagnostic.TargetEntry;
    else if (!diagnostic.TargetGuid.IsEmpty())
        summary << " target=" << diagnostic.TargetGuid.GetCounter();
    summary << " hp=" << diagnostic.TargetHealthPct
            << " best=" << diagnostic.BestHealthPct
            << " count=" << diagnostic.NoProgressCount << "/" << diagnostic.NoProgressThreshold;
    if (!diagnostic.LastCombatAttemptSummary.empty())
        summary << " last_cast=" << diagnostic.LastCombatAttemptSummary;
    return summary.str();
}

std::string BotWorldPopulationMgr::BuildCombatAttemptJson(WorldBotState::CombatAttemptDiagnostic const& diagnostic) const
{
    std::ostringstream json;
    json << "{\"recorded_at_ms\":" << diagnostic.RecordedAtMs
         << ",\"phase\":\"" << JsonEscape(diagnostic.Phase) << "\""
         << ",\"action\":{\"spell_id\":" << diagnostic.SpellId
         << ",\"debug_name\":\"" << JsonEscape(diagnostic.DebugName) << "\""
         << ",\"action_type\":\"" << JsonEscape(diagnostic.ActionType) << "\""
         << ",\"target_guid\":" << diagnostic.TargetGuid.GetCounter()
         << ",\"target_entry\":" << diagnostic.TargetEntry
         << ",\"self_target\":" << (diagnostic.SelfTarget ? "true" : "false") << "}"
         << ",\"failure\":{\"result\":\"" << JsonEscape(diagnostic.Result) << "\""
         << ",\"reason\":\"" << JsonEscape(diagnostic.Reason) << "\""
         << ",\"gates\":{\"casting\":" << (diagnostic.Casting ? "true" : "false")
         << ",\"global_cooldown\":" << (diagnostic.GlobalCooldown ? "true" : "false")
         << ",\"cooldown_ready\":" << (diagnostic.CooldownReady ? "true" : "false")
         << ",\"known_spell\":" << (diagnostic.KnownSpell ? "true" : "false")
         << ",\"has_power\":" << (diagnostic.HasPower ? "true" : "false")
         << ",\"line_of_sight\":" << (diagnostic.LineOfSight ? "true" : "false")
         << ",\"in_range\":" << (diagnostic.InRange ? "true" : "false")
         << ",\"target_alive\":" << (diagnostic.TargetAlive ? "true" : "false")
         << ",\"target_attackable\":" << (diagnostic.TargetAttackable ? "true" : "false") << "}}"
         << ",\"uptime\":{\"melee_auto_attacking\":" << (diagnostic.MeleeAutoAttacking ? "true" : "false")
         << ",\"ranged_auto_active\":" << (diagnostic.RangedAutoActive ? "true" : "false")
         << ",\"pet_attacking\":" << (diagnostic.PetAttacking ? "true" : "false") << "}"
         << ",\"summary\":\"" << JsonEscape(diagnostic.Summary) << "\"}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRouteProgressJson(WorldBotState::RouteProgressDiagnostic const& diagnostic) const
{
    std::ostringstream json;
    json << "{\"route\":{\"node_id\":\"" << JsonEscape(diagnostic.NodeId) << "\""
         << ",\"generation\":" << diagnostic.Generation
         << ",\"kind\":\"" << JsonEscape(diagnostic.Kind) << "\"}"
         << ",\"target\":{\"guid\":" << diagnostic.TargetGuid.GetCounter()
         << ",\"entry\":" << diagnostic.TargetEntry
         << ",\"hp_pct\":" << diagnostic.TargetHealthPct
         << ",\"best_hp_pct\":" << diagnostic.BestHealthPct << "}"
         << ",\"no_progress\":{\"count\":" << diagnostic.NoProgressCount
         << ",\"threshold\":" << diagnostic.NoProgressThreshold
         << ",\"reason\":\"" << JsonEscape(diagnostic.Reason) << "\"}"
         << ",\"state\":{\"victim_guid\":" << diagnostic.VictimGuid.GetCounter()
         << ",\"bot_in_combat\":" << (diagnostic.BotInCombat ? "true" : "false")
         << ",\"bot_casting\":" << (diagnostic.BotCasting ? "true" : "false") << "}"
         << ",\"last_combat_attempt_summary\":\"" << JsonEscape(diagnostic.LastCombatAttemptSummary) << "\""
         << ",\"summary\":\"" << JsonEscape(diagnostic.Summary) << "\"}";
    return json.str();
}

void BotWorldPopulationMgr::RecordCombatAttempt(WorldBotState& state, Player* bot, Unit* target, char const* phase, ResolvedCombatAction const* action, BotActionResult result, char const* reason) const
{
    WorldBotState::CombatAttemptDiagnostic diagnostic;
    diagnostic.RecordedAtMs = NowMs();
    diagnostic.Phase = phase ? phase : "cast";
    diagnostic.ActionType = action ? action->Type : "wait";
    diagnostic.SpellId = action ? action->SpellId : 0;
    diagnostic.DebugName = action ? action->DebugName : "";
    Unit* actionTarget = target;
    if (bot && action && !action->TargetGuid.IsEmpty())
        actionTarget = ObjectAccessor::GetUnit(*bot, action->TargetGuid);
    if (!actionTarget && target)
        actionTarget = target;
    if (action)
        diagnostic.TargetGuid = action->TargetGuid;
    if (diagnostic.TargetGuid.IsEmpty() && actionTarget)
        diagnostic.TargetGuid = actionTarget->GetGUID();
    if (Creature const* creature = actionTarget ? actionTarget->ToCreature() : nullptr)
        diagnostic.TargetEntry = creature->GetEntry();
    diagnostic.SelfTarget = bot && diagnostic.TargetGuid == bot->GetGUID();
    diagnostic.Result = ToString(result);

    SpellInfo const* spellInfo = diagnostic.SpellId ? sSpellMgr->GetSpellInfo(diagnostic.SpellId) : nullptr;
    diagnostic.Casting = bot && bot->HasUnitState(UNIT_STATE_CASTING);
    diagnostic.GlobalCooldown = bot && spellInfo && bot->GetSpellHistory()->HasGlobalCooldown(spellInfo);
    diagnostic.CooldownReady = bot && spellInfo && bot->GetSpellHistory()->IsReady(spellInfo);
    diagnostic.KnownSpell = bot && diagnostic.SpellId && bot->HasSpell(diagnostic.SpellId);
    diagnostic.HasPower = bot && spellInfo && HasPowerForSpell(bot, spellInfo);
    diagnostic.LineOfSight = bot && actionTarget && bot->IsWithinLOSInMap(actionTarget);
    if (bot && actionTarget && action && action->Type == "auto_attack"
        && action->AutoAttackMode == "melee")
        diagnostic.InRange = bot->IsWithinMeleeRange(actionTarget);
    else
        diagnostic.InRange = bot && actionTarget && spellInfo
            && bot->IsWithinDistInMap(actionTarget,
                std::max(5.0f, spellInfo->GetMaxRange(false)));
    diagnostic.TargetAlive = actionTarget && actionTarget->IsAlive();
    bool const friendlyAction = bot && actionTarget && spellInfo && spellInfo->IsPositive()
        && bot->IsValidAssistTarget(actionTarget);
    diagnostic.TargetAttackable = friendlyAction
        ? true
        : bot && actionTarget && (actionTarget == bot
            || (spellInfo ? bot->IsValidAttackTarget(actionTarget, spellInfo)
                : bot->IsValidAttackTarget(actionTarget)));
    diagnostic.MeleeAutoAttacking = bot && bot->HasUnitState(UNIT_STATE_MELEE_ATTACKING) && bot->GetVictim();
    diagnostic.RangedAutoActive = bot && bot->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL);
    if (bot)
        if (Pet* pet = bot->GetPet())
            diagnostic.PetAttacking = pet->IsAlive() && pet->GetVictim();
    if (reason && *reason)
        diagnostic.Reason = reason;
    else if (!spellInfo && diagnostic.SpellId)
        diagnostic.Reason = "bad_spell";
    else if (!actionTarget)
        diagnostic.Reason = "target_missing";
    else if (!diagnostic.TargetAlive)
        diagnostic.Reason = "target_dead";
    else if (!diagnostic.TargetAttackable)
        diagnostic.Reason = "target_not_attackable";
    else if (!diagnostic.LineOfSight)
        diagnostic.Reason = "no_line_of_sight";
    else if (!diagnostic.InRange)
        diagnostic.Reason = "out_of_range";
    else if (diagnostic.Casting)
        diagnostic.Reason = "already_casting";
    else if (diagnostic.GlobalCooldown)
        diagnostic.Reason = "global_cooldown";
    else if (!diagnostic.CooldownReady)
        diagnostic.Reason = "cooldown";
    else if (!diagnostic.HasPower)
        diagnostic.Reason = "no_power";
    diagnostic.Summary = BuildCombatAttemptSummary(diagnostic);
    state.LastCombatAttempt = diagnostic;
}

void BotWorldPopulationMgr::RecordRouteProgress(WorldBotState& state, Player* bot, Unit* target, char const* reason, float targetHealthPct, float bestHealthPct, uint32 noProgressCount, uint32 noProgressThreshold) const
{
    WorldBotState::RouteProgressDiagnostic diagnostic;
    diagnostic.RecordedAtMs = NowMs();
    diagnostic.Generation = Party().ValidationRouteGeneration;
    diagnostic.NodeId = Cohort().Config.ValidationRouteNodeId;
    diagnostic.Kind = Cohort().Config.ValidationRouteKind;
    diagnostic.TargetGuid = target ? target->GetGUID() : ObjectGuid::Empty;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        diagnostic.TargetEntry = creature->GetEntry();
    diagnostic.TargetHealthPct = targetHealthPct;
    diagnostic.BestHealthPct = bestHealthPct;
    diagnostic.NoProgressCount = noProgressCount;
    diagnostic.NoProgressThreshold = noProgressThreshold;
    diagnostic.Reason = reason ? reason : "route_no_progress";
    diagnostic.VictimGuid = target && target->GetVictim() ? target->GetVictim()->GetGUID() : ObjectGuid::Empty;
    diagnostic.BotInCombat = bot && bot->IsInCombat();
    diagnostic.BotCasting = bot && bot->HasUnitState(UNIT_STATE_CASTING);
    diagnostic.LastCombatAttemptSummary = state.LastCombatAttempt.Summary;
    diagnostic.Summary = BuildRouteProgressSummary(diagnostic);
    state.LastRouteProgress = diagnostic;
    if (diagnostic.Reason == "route_target_combat_progress" && target && target->IsAlive())
        TryResolveBotBlocker(state, bot, "route_target_combat_progress");
}

std::string BotWorldPopulationMgr::BuildBlockedDiagnosticText(WorldBotState const& state, char const* reason) const
{
    if (!state.LastRouteProgress.Summary.empty() && state.LastRouteProgress.Reason == (reason && *reason ? reason : state.LastRouteProgress.Reason))
        return "Route reset: " + state.LastRouteProgress.Summary;
    if (!state.LastCombatAttempt.Summary.empty())
        return "Blocked: " + state.LastCombatAttempt.Summary;
    return "Blocked: " + std::string(reason && *reason ? reason : "blocked");
}

bool BotWorldPopulationMgr::TryRecoverStuckBot(WorldBotState& state, Player* bot)
{
    if (!bot || !bot->IsInWorld() || !bot->GetMap())
        return false;

    uint64 const nowMs = NowMs();
    if (!state.StuckRecoveryStartedMs)
        state.StuckRecoveryStartedMs = nowMs;
    ++state.RecoveryAttemptCount;
    ++state.StuckRecoveryStage;
    state.LastRecoveryMs = nowMs;

    float const previousX = state.ActivePathToX;
    float const previousY = state.ActivePathToY;
    float const previousZ = state.ActivePathToZ;
    bool const previousPathScoped = state.ActivePathValid
        && (!Cohort().Config.ValidationRouteEnable
            || (state.ActivePathAttemptId == Cohort().AttemptId
                && state.ActivePathWipeGeneration == Cohort().Raid.WipeGeneration
                && state.ActivePathRouteGeneration == Party().ValidationRouteGeneration
                && state.ActivePathRouteNodeId == Cohort().Config.ValidationRouteNodeId));

    state.DecisionKernel.Begin(nowMs);
    auto submitMovement = [&](std::string key, float utility, bool allowed,
        float x, float y, float z, bool invalidateCurrentPath)
    {
        BotActionArbitration::Candidate candidate;
        candidate.Key = std::move(key);
        candidate.Source = "stuck_recovery_supervisor";
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.UtilityScore = utility;
        candidate.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Movement);
        candidate.Allowed = allowed;
        candidate.RejectReason = "recovery_geometry_unavailable";
        candidate.RetryBaseMs = 500;
        candidate.RetryMaxMs = 6000;
        candidate.EscalateAfter = 3;
        candidate.Attempt = [&, x, y, z, invalidateCurrentPath]()
        {
            if (invalidateCurrentPath)
                state.ActivePathValid = false;
            bool const moved = MoveBotToPoint(state, bot, x, y, z, false,
                BotMovementArbitration::Owner::Recovery,
                BotMovementArbitration::Priority::Recovery);
            return moved
                ? BotActionArbitration::Outcome::Progressed("native_repath_submitted")
                : BotActionArbitration::Outcome::Retryable(
                    state.LastPathRejectReason.empty()
                        ? std::string_view("native_repath_rejected")
                        : std::string_view(state.LastPathRejectReason));
        };
        state.DecisionKernel.Submit(std::move(candidate));
    };

    // Rotate the preferred native recovery on each no-progress episode. A
    // successfully submitted-but-ineffective path therefore cannot monopolize
    // every later recovery tick; rejected preferences still fall through to
    // the remaining candidates in this same resolution.
    uint8 const recoveryStrategy = uint8((state.StuckRecoveryStage - 1) % 4);
    submitMovement("world.recovery.revalidate_destination",
        recoveryStrategy == 0 ? 4.0f : 0.5f,
        previousPathScoped, previousX, previousY, previousZ, true);

    bool const routeAnchorAvailable = Cohort().Config.ValidationRouteEnable
        && Cohort().Config.ValidationRouteMapId == bot->GetMapId();
    submitMovement("world.recovery.route_anchor",
        recoveryStrategy == 1 ? 4.0f : 1.0f, routeAnchorAvailable,
        Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY,
        Cohort().Config.ValidationRouteZ, true);

    float const sideDistance = 2.5f + float((state.StuckRecoveryStage - 1) % 2);
    Position const left = bot->GetFirstCollisionPosition(
        sideDistance, bot->GetOrientation() + float(M_PI) / 2.0f);
    Position const right = bot->GetFirstCollisionPosition(
        sideDistance, bot->GetOrientation() - float(M_PI) / 2.0f);
    submitMovement("world.recovery.sidestep_left",
        recoveryStrategy == 2 ? 4.0f : 2.0f, true,
        left.GetPositionX(), left.GetPositionY(), left.GetPositionZ(), true);
    submitMovement("world.recovery.sidestep_right",
        recoveryStrategy == 3 ? 4.0f : 1.0f, true,
        right.GetPositionX(), right.GetPositionY(), right.GetPositionZ(), true);

    BotActionArbitration::Resolution const& resolution = state.DecisionKernel.Resolve();
    state.LastDecisionKernelJson = state.DecisionKernel.LastResolutionJson();
    state.StuckTimer = 0;
    if (resolution.AnyCommitted)
    {
        state.LastRecoveryMode = "native_priority_repath";
        state.LastRecoveryResult = resolution.CommittedCandidates.empty()
            ? "native_repath_submitted" : resolution.CommittedCandidates.front();
        state.LastNoProgressReason = "stuck_recovery_in_progress";
        return true;
    }

    state.LastRecoveryMode = "native_priority_repath_exhausted";
    state.LastRecoveryResult = "all_recovery_candidates_rejected";
    state.LastNoProgressReason = state.LastRecoveryResult;
    return state.StuckRecoveryStage < 3;
}

void BotWorldPopulationMgr::ObserveBotCandidateFailure(WorldBotState& state,
    Player* bot, std::string const& key, std::string const& reason,
    uint32 retryBaseMs, uint32 retryMaxMs, uint8 escalateAfter,
    uint64 minimumFailureDurationMs) const
{
    uint64 const nowMs = NowMs();
    state.DecisionKernel.Observe(key,
        BotActionArbitration::Outcome::Retryable(reason), nowMs,
        retryBaseMs, retryMaxMs, escalateAfter);
    state.LastRecoveryMs = nowMs;
    state.LastRecoveryMode = "candidate_backoff";
    state.LastRecoveryResult = reason;
    state.LastNoProgressReason = reason;
    if (state.DecisionKernel.ShouldEscalate(
            key, nowMs, minimumFailureDurationMs))
        MarkBotBlocked(state, bot, reason.c_str());
}

void BotWorldPopulationMgr::MarkBotBlocked(WorldBotState& state, Player* bot, char const* reason) const
{
    std::string blockedReason = reason && *reason ? reason : "blocked";
    state.LastNoProgressReason = blockedReason;
    state.LastRecoveryMode = "blocked_no_fallback";
    state.LastRecoveryResult = blockedReason;
    if (!state.Blocked)
    {
        state.Blocked = true;
        ++state.BlockedEpisodeId;
        state.BlockedFirstReason = blockedReason;
        state.BlockedReason = blockedReason;
        state.BlockedResolution = blockedReason;
        state.BlockedResolutionCandidate.clear();
        state.BlockedResolutionCandidateCount = 0;
        state.BlockedResolvedBy.clear();
        state.BlockedStartMs = NowMs();
        state.BlockedProgressBaselineMs = std::max(state.LastMovementProgressMs, state.LastRouteProgress.RecordedAtMs);
        state.BlockedResolvedMs = 0;
        state.BlockedMessageEmitted = false;
        state.LastBlockedDiagnosticText.clear();
        state.UnstuckMessageEmitted = false;
    }
    else
    {
        state.BlockedReason = blockedReason;
        state.BlockedResolution = blockedReason;
        // An invalid profile resolution interrupts any pending valid-action
        // streak.  Keep the existing episode and first reason intact so a
        // transient invalid/valid cadence cannot manufacture new episodes.
        state.BlockedResolutionCandidate.clear();
        state.BlockedResolutionCandidateCount = 0;
    }

    std::string diagnosticText = "Blocked: " + state.BlockedFirstReason;
    if (bot && diagnosticText != state.LastBlockedDiagnosticText)
    {
        bot->Say(diagnosticText, LANG_UNIVERSAL);
        state.LastBlockedDiagnosticText = diagnosticText;
        state.BlockedMessageEmitted = true;
    }
}

void BotWorldPopulationMgr::MarkBotUnstuck(WorldBotState& state, Player* bot, char const* reason) const
{
    if (!state.Blocked)
        return;

    std::string unstuckReason = reason && *reason ? reason : state.BlockedReason;
    if (bot && !state.UnstuckMessageEmitted)
        bot->Say("Unstuck: " + unstuckReason, LANG_UNIVERSAL);

    state.BlockedResolvedBy = unstuckReason;
    state.BlockedResolvedMs = NowMs();
    state.Blocked = false;
    state.BlockedReason.clear();
    state.BlockedResolution.clear();
    state.BlockedResolutionCandidate.clear();
    state.BlockedResolutionCandidateCount = 0;
    state.BlockedStartMs = 0;
    state.BlockedProgressBaselineMs = 0;
    state.BlockedMessageEmitted = false;
    state.UnstuckMessageEmitted = true;
}

bool BotWorldPopulationMgr::TryResolveBotBlocker(WorldBotState& state, Player* bot, char const* resolvedBy) const
{
    if (!state.Blocked)
        return false;

    std::string reason = state.BlockedResolution.empty() ? state.BlockedReason : state.BlockedResolution;
    std::string resolver = resolvedBy && *resolvedBy ? resolvedBy : "";
    bool resolved = false;
    if (reason == resolver)
        resolved = true;
    else if ((reason == "stuck_no_fallback" || reason == "validation_route_stuck_no_fallback") && resolver == "movement_progress")
        resolved = state.LastMovementProgressMs > state.BlockedProgressBaselineMs;
    else if ((reason == "stuck_no_fallback" || reason == "validation_route_stuck_no_fallback") && resolver == "route_target_combat_progress")
        resolved = state.LastRouteProgress.RecordedAtMs > state.BlockedProgressBaselineMs;
    else if (reason.rfind("missing_self_buff:", 0) == 0 && resolver == reason.substr(std::string("missing_self_buff:").size()))
        resolved = true;
    else if (reason.rfind("missing_party_buff:", 0) == 0 && resolver == reason.substr(std::string("missing_party_buff:").size()))
        resolved = true;
    else if (reason.rfind("buff_cast_failed:", 0) == 0)
    {
        std::string key = reason.substr(std::string("buff_cast_failed:").size());
        size_t detailPos = key.find(':');
        if (detailPos != std::string::npos)
            key.resize(detailPos);
        resolved = resolver == key;
    }
    else if (reason.rfind("totem_cast_failed:", 0) == 0 && resolver == reason.substr(std::string("totem_cast_failed:").size()))
        resolved = true;
    else if (reason == "hunter_pet_unprovisioned" && resolver == "hunter_pet_ready")
        resolved = true;
    else if (reason.rfind("hunter_pet_db_row_absent:", 0) == 0 && resolver == "hunter_pet_ready")
        resolved = true;
    else if (reason.rfind("hunter_pet_load_failed:", 0) == 0 && resolver == "hunter_pet_ready")
        resolved = true;
    else if (reason.rfind("hunter_pet_call_failed:", 0) == 0 && resolver == "hunter_pet_ready")
        resolved = true;
    else if (reason.rfind("hunter:call_pet:", 0) == 0 && resolver == "hunter_pet_ready")
        resolved = true;
    else if (reason == "hunter_pet_missing" && resolver == "hunter_pet_ready")
        resolved = true;
    else if (reason == "hunter_pet_dead" && resolver == "hunter_pet_ready")
        resolved = true;
    else if (reason == "persistent_setup_preexisting_pet_without_native_receipt"
        && resolver == "persistent_preexisting_affliction_pet_observed")
        resolved = true;
    else if (reason == "cast_failed" && resolver == "cast_succeeded")
        resolved = true;
    else if (reason == "no_valid_profile_action" && resolver == "profile_action_valid")
    {
        // Resolver validity is an observation, not proof that the bot has
        // recovered. Require two consecutive samples; MarkBotBlocked clears
        // this streak whenever the next profile resolution is invalid.
        constexpr uint32 ProfileActionStableSamples = 2;
        if (state.BlockedResolutionCandidate != resolver)
        {
            state.BlockedResolutionCandidate = resolver;
            state.BlockedResolutionCandidateCount = 0;
        }
        ++state.BlockedResolutionCandidateCount;
        resolved = state.BlockedResolutionCandidateCount >= ProfileActionStableSamples;
    }
    else if (reason == "no_valid_profile_action" && resolver == "cast_succeeded")
    {
        // A real successful cast is concrete progress. It is only accepted
        // after this episode has observed at least one valid profile action,
        // so an unrelated resolver cannot clear the blocker by coincidence.
        resolved = state.BlockedResolutionCandidate == "profile_action_valid"
            && state.BlockedResolutionCandidateCount > 0;
    }

    if (resolved)
        MarkBotUnstuck(state, bot, resolver.c_str());
    return resolved;
}
