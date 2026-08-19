#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotActionExecutor.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Creature.h"
#include "GameTime.h"
#include "Map.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Totem.h"
#include "Unit.h"

#include <array>
#include <chrono>
#include <cmath>
#include <string>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

bool BotWorldPopulationMgr::TryEnsureCombatTotems(WorldBotState& state, Player* bot, Unit* target, uint32 hostileCount) const
{
    if (!bot || bot->getClass() != CLASS_SHAMAN || !bot->IsInCombat() || !target || !target->IsAlive())
        return false;

    uint64 const nowMs = NowMs();
    // Cataclysm combat totems cannot be placed while moving. Defer setup until
    // route movement stops instead of recording deterministic cast failures on
    // every retry; the ordinary combat action remains free to run this tick.
    if (bot->isMoving())
        return false;

    uint32 const totemSpellIds[] = { 8075, 3599, 5394, 8512 };
    for (uint32 spellId : totemSpellIds)
    {
        if (bot->HasSpell(spellId))
            continue;

        std::string key = "totem_spell_missing:" + std::to_string(spellId);
        state.ReadinessRetryUntilMs[key] = nowMs + 15000;
        ObserveBotCandidateFailure(state, bot,
            "world.setup." + key, key, 1000, 15000, 3, 15000);
        return true;
    }

    uint32 const desiredFireTotemSpell = hostileCount >= 3 && bot->HasSpell(8190) ? 8190 : 3599;
    std::array<std::pair<uint8, uint32>, 4> const desiredTotems = {{
        { SUMMON_SLOT_TOTEM_FIRE, desiredFireTotemSpell },
        { SUMMON_SLOT_TOTEM_EARTH, 8075 },
        { SUMMON_SLOT_TOTEM_WATER, 5394 },
        { SUMMON_SLOT_TOTEM_AIR, 8512 },
    }};
    for (auto const& [slot, spellId] : desiredTotems)
    {
        Creature* creature = bot->m_SummonSlot[slot] && bot->GetMap()
            ? bot->GetMap()->GetCreature(bot->m_SummonSlot[slot]) : nullptr;
        Totem* totem = creature ? creature->ToTotem() : nullptr;
        bool const ready = totem && totem->IsAlive()
            && (slot != SUMMON_SLOT_TOTEM_FIRE
                || totem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == spellId
                || totem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == 2894);
        if (ready)
            continue;

        std::string const attemptKey = "totem:" + std::to_string(spellId);
        auto retryItr = state.ReadinessRetryUntilMs.find(attemptKey);
        if (retryItr != state.ReadinessRetryUntilMs.end() && retryItr->second > nowMs)
            continue;

        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
        if (!bot->HasSpell(spellId) || !spellInfo || bot->HasUnitState(UNIT_STATE_CASTING)
            || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo) || !bot->GetSpellHistory()->IsReady(spellInfo))
            return false;

        ResolvedCombatAction action;
        action.Valid = true;
        action.Type = "cast";
        action.SpellId = spellId;
        action.TargetGuid = bot->GetGUID();
        action.DebugName = slot == SUMMON_SLOT_TOTEM_FIRE
            ? (spellId == 8190 ? "magma_totem" : "searing_totem") : "combat_totem";
        if (bot->CastSpell(bot, spellId, false) == SPELL_CAST_OK)
        {
            RecordCombatAttempt(state, bot, bot, "totems", &action, BotActionResult::Ok,
                spellId == 8190 ? "aoe_fire_totem" : (spellId == 3599 ? "single_target_fire_totem" : "individual_combat_totem"));
            state.ReadinessRetryUntilMs.erase(attemptKey);
            TryResolveBotBlocker(state, bot, "individual_combat_totem");
            return true;
        }

        RecordCombatAttempt(state, bot, bot, "totems", &action, BotActionResult::CastFailed, "totem_cast_failed");
        state.ReadinessRetryUntilMs[attemptKey] = nowMs + 3000;
        std::string const blocker = "totem_cast_failed:" + std::to_string(spellId);
        ObserveBotCandidateFailure(state, bot,
            "world.setup." + attemptKey, blocker, 500, 5000, 3, 5000);
        return true;
    }

    TryResolveBotBlocker(state, bot, "totems_ready");
    return false;
}

BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState* state, Player* bot, Unit* target, ResolvedCombatAction* actionOut, uint32 hostileCount, bool densityOnly, uint32 excludedSpellId, bool areaOnly, bool selfCenteredOnly, bool forbidArea, bool allowMultidot, bool hostileTargetOnly)
{
    if (target && IsImmediateNextValidationRouteEncounterMember(target->ToCreature()))
    {
        ResolvedCombatAction rejected;
        rejected.TargetGuid = target->GetGUID();
        rejected.DebugName = "future_encounter_target_forbidden";
        if (actionOut)
            *actionOut = rejected;
        if (state)
        {
            RecordCombatAttempt(*state, bot, target, "profile_resolve", &rejected,
                BotActionResult::NoAction, rejected.DebugName.c_str());
            state->DecisionKernel.Observe("world.hard_mask.future_encounter",
                BotActionArbitration::Outcome::Unsafe(rejected.DebugName), NowMs(),
                500, 5000, 5);
            state->LastRecoveryMode = "hard_safety_mask";
            state->LastRecoveryResult = rejected.DebugName;
            state->LastNoProgressReason = rejected.DebugName;
            state->TargetGuid.Clear();
            if (state->DecisionKernel.ShouldEscalate(
                    "world.hard_mask.future_encounter", NowMs(), 5000))
                MarkBotBlocked(*state, bot, rejected.DebugName.c_str());
        }
        return BotActionResult::NoAction;
    }

    if (state && bot && target)
    {
        BotClassSpecActionProfile const profile =
            BotClassSpecActionProfileStore::Build(bot, GetDungeonRole(bot));
        if (profile.AutoAttackMode == "melee"
            && target->IsAlive() && bot->IsValidAttackTarget(target))
        {
            SubmitMeleeAutoAttackIntent(*state,
                BotMeleeAutoAttack::Kind::StartOrSwitch,
                target->GetGUID(), BotMeleeAutoAttack::Owner::Profile,
                BotActionArbitration::Priority::TrainedDamage,
                "profile_melee_autoattack");
        }
    }

    if (!hostileTargetOnly && state && TryEnsurePersistentCombatSetup(*state, bot, target))
        return BotActionResult::Casting;

    if (!hostileTargetOnly && state
        && TryEnsureCombatTotems(*state, bot, target, forbidArea ? 1 : hostileCount))
        return BotActionResult::Casting;

    uint64 const nowMs = NowMs();
    if (state && state->ProfileCastSuppressedUntilMs <= nowMs)
    {
        state->ProfileCastSuppressedSpellId = 0;
        state->ProfileCastSuppressedTargetGuid.Clear();
        state->ProfileCastSuppressedUntilMs = 0;
    }
    if (!excludedSpellId && state && target
        && state->ProfileCastSuppressedUntilMs > nowMs
        && state->ProfileCastSuppressedTargetGuid == target->GetGUID())
        excludedSpellId = state->ProfileCastSuppressedSpellId;

    bool const movementCompatibleOnly = state && bot
        && (bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING))
        && state->MovementLease.ExpiresAtMs > nowMs
        && uint8(state->MovementLease.MovementPriority)
            >= uint8(BotMovementArbitration::Priority::Combat);
    ResolvedCombatAction action = ResolveProfileCombatAction(
        bot, target, hostileCount, densityOnly, excludedSpellId, areaOnly,
        selfCenteredOnly, forbidArea, allowMultidot && !forbidArea,
        hostileTargetOnly, movementCompatibleOnly);
    action.MeleeAutoAttackExternallyReconciled = state
        && action.AutoAttackMode == "melee";
    if (actionOut)
        *actionOut = action;
    if (!action.Valid)
    {
        BotActionResult invalidResult = action.DebugName == "global_cooldown"
            ? BotActionResult::GlobalCooldown : BotActionResult::NoAction;
        if (state)
            RecordCombatAttempt(*state, bot, target, "profile_resolve", &action,
                invalidResult, action.DebugName.c_str());
        if (state && invalidResult == BotActionResult::NoAction)
        {
            state->DecisionKernel.Observe("world.profile_resolve",
                BotActionArbitration::Outcome::Retryable(action.DebugName), nowMs,
                100, 3000, 5);
            state->LastRecoveryMode = "candidate_backoff";
            state->LastRecoveryResult = action.DebugName;
            state->LastNoProgressReason = action.DebugName;
            if (state->DecisionKernel.ShouldEscalate(
                    "world.profile_resolve", nowMs, 5000))
                MarkBotBlocked(*state, bot, action.DebugName.c_str());
        }
        return invalidResult;
    }

    if (state)
    {
        state->DecisionKernel.Observe("world.profile_resolve",
            BotActionArbitration::Outcome::Selected("profile_action_valid"),
            nowMs, 100, 3000, 5);
        TryResolveBotBlocker(*state, bot, "profile_action_valid");
    }

    if (state && bot && target && action.SpellId == 5221)
    {
        float nativeFrontArc = float(M_PI);
        if (Creature const* creature = target->ToCreature();
            creature && creature->HasStaticFlag(CREATURE_STATIC_FLAG_5_240_DEGREE_BACK_ARC))
            nativeFrontArc -= float(M_PI) / 3.0f;
        if (target->HasInArc(nativeFrontArc, bot))
        {
            action.MovementDirective = "melee_behind";
            if (actionOut)
                *actionOut = action;
            bool const moved = MoveBotToProfileRange(*state, bot, target, &action);
            RecordCombatAttempt(*state, bot, target, "positional_reposition", &action,
                moved ? BotActionResult::Casting : BotActionResult::NoAction,
                moved ? "shred_behind_required" : "shred_behind_path_rejected");
            if (moved)
            {
                TryResolveBotBlocker(*state, bot, "shred_behind_reposition");
                return BotActionResult::Casting;
            }

            // Do not turn an unavailable rear lane into a native cast failure
            // loop.  Suppress only Shred for a short resolver window so the
            // unchanged profile can choose Mangle or another legal action.
            state->ProfileCastSuppressedSpellId = action.SpellId;
            state->ProfileCastSuppressedTargetGuid = action.TargetGuid;
            state->ProfileCastSuppressedUntilMs = nowMs + 3000;
            return BotActionResult::NoAction;
        }
    }

    bool const selfCenteredHostileRangeAction = state && bot && target
        && target != bot && action.TargetGuid == bot->GetGUID()
        && action.MaxRange > 0.0f;
    if (selfCenteredHostileRangeAction)
    {
        float const distance = bot->GetExactDist(target);
        if (distance > std::max(5.0f, action.MaxRange - 0.25f)
            || !bot->IsWithinLOSInMap(target))
        {
            bool const moved = MoveBotToProfileRange(*state, bot, target,
                &action, !bot->IsWithinLOSInMap(target));
            RecordCombatAttempt(*state, bot, target,
                "self_centered_position_reconcile", &action,
                moved ? BotActionResult::Casting : BotActionResult::NoAction,
                moved ? "native_self_centered_range"
                    : "native_self_centered_path_rejected");
            if (moved)
                return BotActionResult::Casting;
            return BotActionResult::NoAction;
        }
        // The core spell is self-targeted, so explicitly retain the hostile
        // cone/area anchor a player would face before pressing the action.
        bot->SetFacingToObject(target);
    }

    BotActionExecutor executor;
    BotActionResult result = executor.ExecuteCombat(bot, bot, action);
    if (state)
    {
        std::string const castLifecycleKey = "world.profile_cast:"
            + std::to_string(action.SpellId) + ":"
            + std::to_string(action.TargetGuid.GetCounter());
        state->DecisionKernel.Observe(castLifecycleKey,
            BotActionArbitration::FromBotActionResult(result), nowMs,
            100, 3000, 5);
        bool recoverLineOfSight = false;
        std::string castFailureReason;
        if (result == BotActionResult::CastFailed)
        {
            castFailureReason = "spell_cast_result_" + std::to_string(executor.LastSpellCastResult());
            if (executor.LastSpellCastResult() == SPELL_FAILED_LINE_OF_SIGHT)
            {
                // The map-level preflight can succeed immediately before the
                // spell-specific LOS check rejects an interrupt. Suppress only
                // this spell-target pair long enough for the resolver to choose
                // useful fallback combat instead of repeating the same failure.
                state->ProfileCastSuppressedSpellId = action.SpellId;
                state->ProfileCastSuppressedTargetGuid = action.TargetGuid;
                state->ProfileCastSuppressedUntilMs = nowMs + 5000;
                recoverLineOfSight = true;
            }
        }
        RecordCombatAttempt(*state, bot, target, "cast", &action, result,
            castFailureReason.empty() ? nullptr : castFailureReason.c_str());
        // Preserve the real failed submission above, then leave the rejected
        // spell topology so per-spell suppression cannot cycle other actions
        // from the same blocked point.
        if (recoverLineOfSight && target)
            MoveBotToProfileRange(*state, bot, target, &action, true);
    }
    if (state && target
        && (result == BotActionResult::OutOfRange
            || result == BotActionResult::NoLineOfSight))
    {
        bool const moved = result == BotActionResult::NoLineOfSight
            ? MoveBotToProfileRange(*state, bot, target, &action, true)
            : MoveBotToProfileRange(*state, bot, target, &action);
        if (moved)
        {
            // Reconcile native action feedback exactly as a player would: the
            // rejected action does not count as combat progress; it produces a
            // target-aware movement intent and the unchanged action is retried
            // after the core reports a legal position on a later tick.
            state->DecisionKernel.Observe(
                "world.profile_position:" +
                    std::to_string(action.TargetGuid.GetCounter()),
                BotActionArbitration::Outcome::Started(
                    "native_position_reconciled"),
                nowMs, 100, 3000, 5);
            state->LastRecoveryMode = "native_position_reconciliation";
            state->LastRecoveryResult = result == BotActionResult::OutOfRange
                ? "move_to_action_range" : "move_to_action_line_of_sight";
            state->LastNoProgressReason.clear();
            RecordCombatAttempt(*state, bot, target, "position_reconcile",
                &action, BotActionResult::Casting,
                result == BotActionResult::OutOfRange
                    ? "native_out_of_range" : "native_no_line_of_sight");
            TryResolveBotBlocker(*state, bot, "native_position_reconciled");
            return BotActionResult::Casting;
        }
    }
    if (state && result == BotActionResult::Ok)
    {
        TryResolveBotBlocker(*state, bot, action.DebugName.c_str());
        TryResolveBotBlocker(*state, bot, "cast_succeeded");
    }
    else if (state && result != BotActionResult::Casting && result != BotActionResult::GlobalCooldown)
    {
        if (state->Blocked && result == BotActionResult::CastFailed)
        {
            state->LastNoProgressReason = ToString(result);
            state->LastRecoveryResult = state->LastNoProgressReason;
            std::string diagnosticText = BuildBlockedDiagnosticText(*state, state->LastNoProgressReason.c_str());
            if (bot && diagnosticText != state->LastBlockedDiagnosticText)
            {
                bot->Say(diagnosticText, LANG_UNIVERSAL);
                state->LastBlockedDiagnosticText = diagnosticText;
            }
            return result;
        }
        std::string const castLifecycleKey = "world.profile_cast:"
            + std::to_string(action.SpellId) + ":"
            + std::to_string(action.TargetGuid.GetCounter());
        state->LastRecoveryMode = "candidate_backoff";
        state->LastRecoveryResult = ToString(result);
        state->LastNoProgressReason = state->LastRecoveryResult;
        if (state->DecisionKernel.ShouldEscalate(castLifecycleKey, nowMs, 5000))
            MarkBotBlocked(*state, bot, ToString(result));
    }
    return result;
}

BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(Player* bot, Unit* target, ResolvedCombatAction* actionOut, uint32 hostileCount, bool densityOnly, uint32 excludedSpellId, bool areaOnly, bool selfCenteredOnly, bool forbidArea, bool allowMultidot, bool hostileTargetOnly)
{
    return ExecuteProfileCombatAction(nullptr, bot, target, actionOut,
        hostileCount, densityOnly, excludedSpellId, areaOnly,
        selfCenteredOnly, forbidArea, allowMultidot, hostileTargetOnly);
}

