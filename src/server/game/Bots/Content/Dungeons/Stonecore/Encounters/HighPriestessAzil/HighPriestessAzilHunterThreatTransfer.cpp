#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilHunterThreatTransfer.h"

#include "Bots/BotActionExecutor.h"
#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Player.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <string>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
HunterThreatTransferResult Context::Run(
    HunterThreatTransferRequest const& request)
{
    HunterThreatTransferResult transferResult;
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;
    Unit*& add = *request.Add;
    bool& sharedFocusValid = *request.SharedFocusValid;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;
    uint32 addCount = discovery.AddCount;
    std::vector<Creature*> const& localAdds = discovery.LocalAdds;
    Player* densityTank = density.DensityTank;
    Player* densityHealer = density.DensityHealer;
    std::function<size_t(Player const*)> const& observedListedAttackerCount =
        density.ObservedListedAttackerCount;
    static constexpr float PassiveTankDensityClusterRadius = 10.0f;

    bool hunterAoeTransferReady = true;
    bool hunterAoeResourceReady = true;
    float hunterAoeMinRange = 5.0f;
    static constexpr float HunterAoeMinRangeSafety = 3.0f;
    static constexpr float HunterAoeMaxRange = 35.0f;
    if (bot->getClass() == CLASS_HUNTER && addCount >= 2)
    {
        // Cataclysm Multi-Shot costs 40 focus. CalcPowerCost can report
        // zero here because the spell's focus cost is supplied through a
        // secondary effect in this client data, while candidate building
        // correctly rejects it as insufficient_resource. Use the actual
        // gameplay threshold so the gate agrees with the cast validator.
        hunterAoeResourceReady = add && bot->HasSpell(2643)
            && bot->GetPower(POWER_FOCUS) >= 40;
        if (add)
            if (SpellInfo const* multiShot = sSpellMgr->GetSpellInfo(2643))
            {
                float spellMinRange = bot->GetSpellMinRangeForTarget(add, multiShot);
                if (multiShot->RangeEntry && (multiShot->RangeEntry->Flags & SPELL_RANGE_RANGED))
                    spellMinRange += bot->GetMeleeRange(add);
                hunterAoeMinRange = std::max(hunterAoeMinRange, spellMinRange);
            }
        // Keep a bounded buffer above the strict minimum. The selected add
        // can close distance between movement completion and CastSpell.
        hunterAoeMinRange = std::min(HunterAoeMaxRange - 1.0f,
            hunterAoeMinRange + HunterAoeMinRangeSafety);
        hunterAoeTransferReady = hunterAoeResourceReady
            && bot->GetExactDist(add) >= hunterAoeMinRange
            && bot->GetExactDist(add) <= HunterAoeMaxRange
            && bot->IsWithinLOSInMap(add);
    }

    if (bot->getClass() == CLASS_HUNTER && densityTank && densityTank != bot
        && addCount >= 2 && hunterAoeResourceReady && !hunterAoeTransferReady
        && !bot->HasAura(34477))
    {
        ResolvedCombatAction rangeAction;
        rangeAction.MovementDirective = "ranged";
        rangeAction.AutoAttackMode = "ranged";
        rangeAction.MinRange = hunterAoeMinRange;
        rangeAction.MaxRange = HunterAoeMaxRange;
        bool moved = manager.MoveBotToProfileRange(state, bot, add, &rangeAction);
        state.TargetGuid = add->GetGUID();
        target = add;
        situation = "dungeon_boss";
        action = moved ? "move_to_misdirection_aoe_range" : "hold_misdirection_aoe_range";
        transferResult.Handled = true;
        return transferResult;
    }

    // Rerun60 proved that an in-range Multi-Shot transfers a fresh wave
    // inside the acquisition grace, but an overlapping wave can activate
    // after the short Misdirection aura ends while its ordinary cooldown
    // remains. Marksmanship already provisions native Readiness; select it
    // only for an active healer-owned swarm and let the registered spell
    // script perform its normal Hunter cooldown reset.
    transferResult.HunterMisdirectionActive = bot->getClass() == CLASS_HUNTER
        && (bot->HasAura(34477) || bot->HasAura(35079));
    SpellInfo const* misdirectionInfo = sSpellMgr->GetSpellInfo(34477);
    if (bot->getClass() == CLASS_HUNTER && densityTank && densityTank != bot
        && densityHealer && observedListedAttackerCount(densityHealer) >= 3
        && addCount >= 3 && !transferResult.HunterMisdirectionActive
        && misdirectionInfo
        && !bot->GetSpellHistory()->IsReady(misdirectionInfo)
        && bot->HasSpell(23989)
        && manager.TryCastFriendlySpell(bot, bot, 23989))
    {
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(
            bot, add, "dungeon_boss", &power, request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_adds", add,
            "readiness_for_misdirection_swarm_pickup",
            raw.c_str(), semantic.c_str(),
            float(observedListedAttackerCount(densityHealer)), addCount, 23989);
        state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
        target = add;
        situation = "dungeon_boss";
        action = "readiness_for_misdirection_swarm_pickup";
        transferResult.Handled = true;
        return transferResult;
    }

    // Do not start the short Misdirection window until the hunter can pay
    // for its transfer shot. Previously a low-focus hunter activated the
    // aura, then spent most of the window returning no_valid_profile_action
    // while a fresh wave accumulated healing threat.
    if (bot->getClass() == CLASS_HUNTER && densityTank && densityTank != bot
        && hunterAoeTransferReady
        && bot->HasSpell(34477) && !bot->HasAura(34477)
        && manager.TryCastFriendlySpell(bot, densityTank, 34477))
    {
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(
            bot, add, "dungeon_boss", &power, request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_adds", add,
            "misdirection_to_tank", raw.c_str(), semantic.c_str(),
            float(addCount), 0, 34477);
        state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
        target = add;
        situation = "dungeon_boss";
        action = "misdirection_boss_adds";
        transferResult.Handled = true;
        return transferResult;
    }

    // Misdirection is useful for every pull size.  Once it is active, make
    // the transfer attack explicit: use a single-target priority action
    // for one hostile and an area-profile action for two or more.  This
    // prevents an active Misdirection window from being consumed by a
    // low-value single-target filler during an add wave.
    if (transferResult.HunterMisdirectionActive && addCount >= 2)
    {
        Creature* legalTransferTarget = nullptr;
        uint32 legalTransferCoverage = 0;
        float legalTransferDistance = std::numeric_limits<float>::max();
        uint32 legalTransferGuid = std::numeric_limits<uint32>::max();
        for (Creature* candidate : localAdds)
        {
            if (!candidate)
                continue;
            float distance = bot->GetExactDist(candidate);
            if (distance < hunterAoeMinRange || distance > HunterAoeMaxRange
                || !bot->IsWithinLOSInMap(candidate))
                continue;
            uint32 coverage = 0;
            for (Creature* neighbor : localAdds)
                if (neighbor && candidate->GetExactDist2d(neighbor)
                    <= PassiveTankDensityClusterRadius)
                    ++coverage;
            uint32 guid = candidate->GetGUID().GetCounter();
            if (!legalTransferTarget || coverage > legalTransferCoverage
                || (coverage == legalTransferCoverage
                    && (distance < legalTransferDistance
                        || (distance == legalTransferDistance
                            && guid < legalTransferGuid))))
            {
                legalTransferTarget = candidate;
                legalTransferCoverage = coverage;
                legalTransferDistance = distance;
                legalTransferGuid = guid;
            }
        }
        if (legalTransferTarget)
        {
            add = legalTransferTarget;
            sharedFocusValid = false;
        }
    }
    if (transferResult.HunterMisdirectionActive && densityTank && add)
    {
        bool useAreaTransfer = addCount >= 2;
        if (useAreaTransfer && bot->GetPower(POWER_FOCUS) < 40)
        {
            std::string raw = manager.BuildRawJson(bot, add);
            std::string semantic = manager.BuildSemanticJson(
                bot, add, "dungeon_boss", &power, request.Stage, request.Activity);
            manager.RecordEvent(state, bot, "boss_adds", add,
                "misdirection_aoe_wait_for_focus", raw.c_str(), semantic.c_str(),
                float(bot->GetPower(POWER_FOCUS)), addCount, 2643);
            state.TargetGuid = add->GetGUID();
            target = add;
            situation = "dungeon_boss";
            action = "misdirection_aoe_wait_for_focus";
            transferResult.Handled = true;
            return transferResult;
        }
        if (useAreaTransfer && (bot->GetExactDist(add) < hunterAoeMinRange
            || bot->GetExactDist(add) > HunterAoeMaxRange
            || !bot->IsWithinLOSInMap(add)))
        {
            ResolvedCombatAction rangeAction;
            rangeAction.MovementDirective = "ranged";
            rangeAction.AutoAttackMode = "ranged";
            rangeAction.MinRange = hunterAoeMinRange;
            rangeAction.MaxRange = HunterAoeMaxRange;
            bool moved = manager.MoveBotToProfileRange(state, bot, add, &rangeAction);
            state.TargetGuid = add->GetGUID();
            target = add;
            situation = "dungeon_boss";
            action = moved ? "move_to_misdirection_aoe_range" : "hold_misdirection_aoe_range";
            transferResult.Handled = true;
            return transferResult;
        }
        // Cobra Shot and the configured ground-target AoE require the bot
        // to be stationary. Clear residual route movement once it is in a
        // legal ranged band so the active transfer window produces an
        // attack instead of repeated movement-gate rejections.
        if (useAreaTransfer && bot->isMoving()
            && bot->GetExactDist(add) >= hunterAoeMinRange
            && bot->GetExactDist(add) <= HunterAoeMaxRange
            && bot->IsWithinLOSInMap(add))
            bot->StopMoving();
        ResolvedCombatAction transferAction;
        BotActionResult actionResult = BotActionResult::NoAction;
        if (useAreaTransfer)
        {
            // Do not allow the density resolver to fall back to Cobra Shot
            // during an active AoE Misdirection window. The transfer cast
            // must itself be an area attack.
            transferAction.Valid = true;
            transferAction.Type = "cast";
            transferAction.SpellId = 2643;
            transferAction.TargetGuid = add->GetGUID();
            transferAction.DebugName = "cleave";
            transferAction.MovementDirective = "ranged";
            transferAction.AutoAttackMode = "ranged";
            transferAction.MinRange = hunterAoeMinRange;
            transferAction.MaxRange = HunterAoeMaxRange;
            BotActionExecutor executor;
            actionResult = executor.ExecuteCombat(bot, bot, transferAction);
            std::string castFailureReason;
            if (actionResult == BotActionResult::CastFailed)
                castFailureReason = "spell_cast_result_" + std::to_string(executor.LastSpellCastResult());
            manager.RecordCombatAttempt(state, bot, add,
                "misdirection_aoe_transfer", &transferAction, actionResult,
                castFailureReason.empty() ? nullptr : castFailureReason.c_str());
        }
        else
        {
            transferAction = manager.ResolveProfileCombatAction(bot, add, 1, false);
            actionResult = manager.ExecuteProfileCombatAction(
                &state, bot, add, &transferAction, 1, false);
        }
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(
            bot, add, "dungeon_boss", &power, request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_adds", add,
            useAreaTransfer ? "misdirection_aoe_transfer"
                            : "misdirection_single_target_transfer",
            raw.c_str(), semantic.c_str(), float(addCount), 0,
            actionResult == BotActionResult::Ok ? transferAction.SpellId : 0);
        state.TargetGuid = add->GetGUID();
        state.WasInCombat = true;
        target = add;
        situation = "dungeon_boss";
        action = useAreaTransfer ? "misdirection_aoe_transfer"
                                 : "misdirection_single_target_transfer";
        transferResult.Handled = true;
        return transferResult;
    }

    return transferResult;
}

HunterThreatTransferResult TryHunterThreatTransfer(
    HunterThreatTransferRequest const& request)
{
    return Context::Run(request);
}
}
