#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrConsumables.h"
#include "Bots/BotWorldPopulationMgrRaidConsumables.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"

#include "GameTime.h"
#include "Item.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <string>
#include <string_view>

namespace
{
using BotWorldPopulationMgrRaidConsumables::Contract;
using BotWorldPopulationMgrRaidConsumables::FindContract;
using BotWorldPopulationMgrRaidConsumables::PrepotStageReady;
using BotWorldPopulationMgrConsumables::CountNativeConsumable;
using BotWorldPopulationMgrConsumables::FindNativeConsumable;

constexpr uint64 RaidConsumableAuraWaitMs = 30000;
constexpr uint64 RaidConsumablePendingWaitMs = 30000;
constexpr uint64 RaidConsumableRetryMs = 500;

uint64 RaidConsumableNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

template <typename Receipt>
char const* ReceiptPhase(Receipt const& receipt)
{
    return receipt.Phase.empty() ? "unknown" : receipt.Phase.c_str();
}
}

void BotWorldPopulationMgr::SubmitRaidPrepullConsumableCandidate(
    BotUpdateContext& context)
{
    RaidRuntime const& raid = Cohort().Raid;
    if (!Cohort().Config.ValidationRouteEnable
        || Cohort().Config.ValidationRouteKind != "boss"
        || !raid.RaidInstance || !context.Bot)
        return;

    if (raid.PrepullConsumablesReady)
        return;

    auto const roster = raid.RosterByGuid.find(
        context.Bot->GetGUID().GetCounter());
    if (roster == raid.RosterByGuid.end())
        return;

    // Let trained healing run before preparation owns the healer's cast and
    // target lanes. Non-healers remain held, so no offensive candidate can
    // start the boss while the raid is recovering from the preceding trash.
    if (roster->second.Role == "healer")
        for (WorldBotState const& memberState : Party().Bots)
        {
            if (raid.RosterByGuid.find(memberState.Guid.GetCounter())
                    == raid.RosterByGuid.end())
                continue;
            Player* member = GetLoadedBot(memberState);
            if (member && member->IsInWorld() && member->IsAlive()
                && member->GetMaxHealth()
                && member->GetHealth() < member->GetMaxHealth()
                && !member->IsInCombat())
                return;
        }

    BotActionArbitration::Candidate candidate;
    candidate.Key = "raid.prepull_consumables:" +
        std::to_string(context.Bot->GetGUID().GetCounter());
    candidate.Source = "raid_prepull_consumables";
    candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
    candidate.UtilityScore = 12.0f;
    // Hold the normal cast/GCD/target lanes while a roster member is waiting
    // for exact native consumable evidence. Movement remains independent so a
    // member can still close the declared pre-pot distance window.
    candidate.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::GlobalCooldown,
        BotActionArbitration::Resource::Cast,
        BotActionArbitration::Resource::Target);
    candidate.RetryBaseMs = 100;
    candidate.RetryMaxMs = 1000;
    candidate.Attempt = [&context]()
    {
        // Durable setup can run while Magmaw formation is moving.  The short
        // pre-pot must wait until formation and health staging are complete;
        // otherwise its aura can expire while those independent gates still
        // suppress the pull.
        bool const prepotStageReady = PrepotStageReady(
            context.AdaptiveMagmawOwnsNode,
            context.AdaptiveMagmawSuppressOffense,
            context.AdaptiveMagmawSuppressReason);
        BotActionArbitration::Outcome outcome =
            context.Manager.TryRaidPrepullConsumables(
                context.State, context.Bot, context.Target,
                prepotStageReady);
        if (outcome.Result == BotActionArbitration::Disposition::Committed
            || outcome.Result == BotActionArbitration::Disposition::Terminal)
        {
            context.Situation = "raid_boss_prepull";
            context.Action = outcome.Result == BotActionArbitration::Disposition::Terminal
                ? "raid_prepull_failed"
                : "raid_prepull_consumable";
            context.State.LastDecisionHandler = "raid_prepull_consumables";
        }
        return outcome;
    };
    context.State.DecisionKernel.Submit(std::move(candidate));
}

bool BotWorldPopulationMgr::RaidPrepullConsumablesReadyForPull() const
{
    RaidRuntime const& raid = Cohort().Raid;
    if (!raid.PrepullConsumablesRequired
        || !raid.PrepullConsumablesReady
        || raid.PrepullConsumablesFailed
        || raid.PrepullConsumablesAttemptId != Cohort().AttemptId
        || raid.PrepullConsumablesWipeGeneration != raid.WipeGeneration
        || raid.PrepullConsumablesRouteGeneration
            != Party().ValidationRouteGeneration
        || raid.RosterByGuid.size() != raid.ExpectedSize
        || raid.PrepullConsumablesByGuid.size() != raid.ExpectedSize)
        return false;

    auto receiptReady = [](RaidPrepullConsumableReceipt const& receipt)
    {
        return receipt.ItemId && receipt.SpellId && receipt.AuraSpellId
            && receipt.SuccessfulUseCount >= receipt.RequiredUses
            && receipt.NativeUseFinishedSuccessfully
            && !receipt.NativeUseAwaitingAura
            && receipt.FinishedAtMs >= receipt.SubmittedAtMs
            && receipt.PreUseItemCount > receipt.PostUseItemCount
            && receipt.AuraObservedAtMs && receipt.CooldownObserved;
    };
    for (auto const& [guid, member] : raid.PrepullConsumablesByGuid)
        if (!member.AliveAndHealed || member.Failed
            || !receiptReady(member.Flask) || !receiptReady(member.Food)
            || !receiptReady(member.Prepot)
            || member.CombatPotionReservedCount < 1)
            return false;
    return true;
}

bool BotWorldPopulationMgr::ApplyRaidPrepullBossPullGate(Player* bot,
    Unit* target, std::string& situation, std::string& action) const
{
    RaidRuntime const& raid = Cohort().Raid;
    if (!raid.RaidInstance || RaidPrepullConsumablesReadyForPull()
        || !bot || !target || bot->IsInCombat() || target->IsInCombat())
        return false;
    situation = "raid_boss_prepull";
    action = "raid_prepull_wait_for_consumables";
    return true;
}

void BotWorldPopulationMgr::ReconcileRaidPrepullItemSpellFinished(
    Player* caster, uint32 spellId, bool success, ObjectGuid castItemGuid,
    uint32 castItemEntry)
{
    RaidRuntime& raid = Cohort().Raid;
    if (!caster || !spellId || !castItemGuid
        || !raid.PrepullConsumablesRequired)
        return;

    auto memberItr = raid.PrepullConsumablesByGuid.find(
        caster->GetGUID().GetCounter());
    if (memberItr == raid.PrepullConsumablesByGuid.end())
        return;

    std::array<RaidPrepullConsumableReceipt*, 3> receipts = {{
        &memberItr->second.Flask,
        &memberItr->second.Food,
        &memberItr->second.Prepot,
    }};
    for (RaidPrepullConsumableReceipt* receipt : receipts)
    {
        if (!receipt || receipt->ItemId != castItemEntry
            || receipt->SpellId != spellId
            || receipt->SubmittedItemGuid != castItemGuid
            || receipt->SubmittedAtMs <= receipt->FinishedAtMs)
            continue;

        uint64 const nowMs = RaidConsumableNowMs();
        receipt->FinishedAtMs = nowMs;
        receipt->FinishedItemGuid = castItemGuid;
        receipt->PostUseItemCount = CountNativeConsumable(caster,
            receipt->ItemId);
        receipt->CooldownObserved = true;
        receipt->CooldownObservedAtMs = nowMs;
        if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId))
        {
            receipt->CooldownRemainingMs = caster->GetSpellHistory()
                ->GetRemainingCooldown(spellInfo);
            receipt->GlobalCooldownRemainingMs = caster->GetSpellHistory()
                ->GetRemainingGlobalCooldown(spellInfo);
        }
        if (!success)
        {
            receipt->NativeUseAwaitingAura = false;
            receipt->NativeUseFinishedSuccessfully = false;
            receipt->FailureReason = std::string("raid_prepull_")
                + ReceiptPhase(*receipt) + "_native_use_failed";
            memberItr->second.Failed = true;
            memberItr->second.FailureReason = receipt->FailureReason;
            raid.PrepullConsumablesFailed = true;
            raid.PrepullConsumablesFailureReason = receipt->FailureReason;
            return;
        }

        // Completion is not setup success until the live aura is observed.
        // This preserves the normal food/effect boundary and makes flask and
        // pre-pot completion equally auditable.
        receipt->NativeUseAwaitingAura = true;
        receipt->NativeUseFinishedSuccessfully = false;
        receipt->AuraObservedAtMs = 0;
        receipt->AuraTimedOutAtMs = 0;
        receipt->AuraDeadlineAtMs = nowMs + RaidConsumableAuraWaitMs;
        receipt->NextRetryAtMs = receipt->AuraDeadlineAtMs;
        return;
    }
}

BotActionArbitration::Outcome BotWorldPopulationMgr::TryRaidPrepullConsumables(
    WorldBotState& state, Player* bot, Unit* target,
    bool prepotStageReady)
{
    RaidRuntime& raid = Cohort().Raid;
    if (!Cohort().Config.ValidationRouteEnable
        || Cohort().Config.ValidationRouteKind != "boss"
        || !raid.RaidInstance || !bot)
        return BotActionArbitration::Outcome::NotApplicable(
            "raid_prepull_not_applicable");

    raid.PrepullConsumablesRequired = true;
    if (raid.PrepullConsumablesAttemptId != Cohort().AttemptId
        || raid.PrepullConsumablesWipeGeneration != raid.WipeGeneration
        || raid.PrepullConsumablesRouteGeneration
            != Party().ValidationRouteGeneration)
    {
        raid.PrepullConsumablesAttemptId = Cohort().AttemptId;
        raid.PrepullConsumablesWipeGeneration = raid.WipeGeneration;
        raid.PrepullConsumablesRouteGeneration =
            Party().ValidationRouteGeneration;
        raid.PrepullConsumablesReady = false;
        raid.PrepullConsumablesFailed = false;
        raid.PrepullConsumablesReadyAtMs = 0;
        raid.PrepullConsumablesFailureReason.clear();
        raid.PrepullConsumablesByGuid.clear();
    }

    auto fail = [&](std::string const& reason)
    {
        raid.PrepullConsumablesFailed = true;
        raid.PrepullConsumablesReady = false;
        raid.PrepullConsumablesFailureReason = reason;
        auto current = raid.PrepullConsumablesByGuid.find(
            bot->GetGUID().GetCounter());
        if (current != raid.PrepullConsumablesByGuid.end())
        {
            current->second.Failed = true;
            current->second.FailureReason = reason;
        }
        MarkBotBlocked(state, bot, reason.c_str());
        return BotActionArbitration::Outcome::Terminal(reason);
    };

    if (raid.PrepullConsumablesFailed)
        return BotActionArbitration::Outcome::Terminal(
            raid.PrepullConsumablesFailureReason);

    if (!raid.Active || !raid.BotActionsEnabled
        || !raid.ServerProvisioningComplete || !raid.RosterComplete
        || !raid.RosterCompositionValid || !raid.UniqueLeases
        || raid.ExpectedSize == 0 || raid.RosterByGuid.size() != raid.ExpectedSize)
        return BotActionArbitration::Outcome::Submitted(
            "raid_prepull_wait_exact_roster");

    auto stateForGuid = [this](uint32 guid) -> WorldBotState*
    {
        for (WorldBotState& candidate : Party().Bots)
            if (candidate.Guid.GetCounter() == guid)
                return &candidate;
        return nullptr;
    };
    auto receiptReady = [](RaidPrepullConsumableReceipt const& receipt)
    {
        return receipt.ItemId && receipt.SpellId && receipt.AuraSpellId
            && receipt.SuccessfulUseCount >= receipt.RequiredUses
            && receipt.NativeUseFinishedSuccessfully
            && !receipt.NativeUseAwaitingAura
            && receipt.FinishedAtMs >= receipt.SubmittedAtMs
            && receipt.PreUseItemCount > receipt.PostUseItemCount
            && receipt.AuraObservedAtMs && receipt.CooldownObserved;
    };
    auto observeReceipt = [&](RaidPrepullConsumableMember& member,
        RaidPrepullConsumableReceipt& receipt, Player* memberBot)
        -> std::string
    {
        if (!memberBot || !receipt.ItemId)
            return {};
        uint64 const nowMs = RaidConsumableNowMs();
        if (receipt.SubmittedAtMs > receipt.FinishedAtMs
            && nowMs >= receipt.SubmittedAtMs + RaidConsumablePendingWaitMs)
            return std::string("raid_prepull_") + ReceiptPhase(receipt)
                + "_native_use_timeout";
        if (receipt.NativeUseAwaitingAura)
        {
            if (memberBot->HasAura(receipt.AuraSpellId))
            {
                receipt.AuraObservedAtMs = nowMs;
                receipt.AuraDeadlineAtMs = 0;
                receipt.NativeUseAwaitingAura = false;
                receipt.NativeUseFinishedSuccessfully = true;
                ++receipt.SuccessfulUseCount;
                if (receipt.Phase == "food_before_scoring")
                    memberBot->SetStandState(UNIT_STAND_STATE_STAND);
            }
            else if (receipt.AuraDeadlineAtMs
                && nowMs >= receipt.AuraDeadlineAtMs)
            {
                receipt.AuraTimedOutAtMs = nowMs;
                receipt.AuraDeadlineAtMs = 0;
                receipt.NativeUseAwaitingAura = false;
                return std::string("raid_prepull_") + ReceiptPhase(receipt)
                    + "_aura_timeout";
            }
        }
        if (receipt.NativeUseFinishedSuccessfully
            && receipt.AuraObservedAtMs
            && receipt.Phase == "prepot_before_combat"
            && !memberBot->HasAura(receipt.AuraSpellId))
            return "raid_prepull_prepot_aura_expired_before_pull";
        return {};
    };

    auto initializeReceipt = [](RaidPrepullConsumableReceipt& receipt,
        uint32 itemId, uint32 spellId, uint32 auraSpellId, char const* phase)
    {
        receipt.ItemId = itemId;
        receipt.SpellId = spellId;
        receipt.AuraSpellId = auraSpellId;
        receipt.RequiredUses = 1;
        receipt.Phase = phase;
    };

    // Materialize one state row for every exact admitted roster GUID before
    // submitting any item request. Missing contracts fail closed rather than
    // falling back to a class-only or generic consumable guess.
    for (auto const& [guid, slot] : raid.RosterByGuid)
    {
        RaidPrepullConsumableMember& member =
            raid.PrepullConsumablesByGuid[guid];
        member.AttemptId = Cohort().AttemptId;
        member.WipeGeneration = raid.WipeGeneration;
        member.RouteGeneration = Party().ValidationRouteGeneration;
        member.RosterSlotId = slot.RosterSlotId;
        member.Role = slot.Role;
        member.ClassSpec = slot.ClassSpec;
        Contract const* contract = FindContract(slot.ClassSpec);
        if (!contract)
            return fail("raid_prepull_unknown_spec_contract_" + slot.ClassSpec);
        initializeReceipt(member.Flask, contract->FlaskItemId,
            contract->FlaskItemSpellId, contract->FlaskAuraSpellId,
            "flask_before_scoring");
        initializeReceipt(member.Food, contract->FoodItemId,
            contract->FoodItemSpellId, contract->FoodAuraSpellId,
            "food_before_scoring");
        initializeReceipt(member.Prepot, contract->PrepotItemId,
            contract->PrepotItemSpellId, contract->PrepotAuraSpellId,
            "prepot_before_combat");
    }

    auto current = raid.PrepullConsumablesByGuid.find(
        bot->GetGUID().GetCounter());
    if (current == raid.PrepullConsumablesByGuid.end())
        return BotActionArbitration::Outcome::NotApplicable(
            "raid_prepull_non_roster_bot");

    bool allAliveAndHealed = true;
    bool allSetupReady = true;
    for (auto const& [guid, slot] : raid.RosterByGuid)
    {
        RaidPrepullConsumableMember& member =
            raid.PrepullConsumablesByGuid[guid];
        WorldBotState* memberState = stateForGuid(guid);
        Player* memberBot = memberState ? GetLoadedBot(*memberState) : nullptr;
        bool const aliveAndHealed = memberBot && memberBot->IsInWorld()
            && memberBot->IsAlive()
            && IsValidationCohortMemberInOriginalInstance(
                memberState ? *memberState : state, memberBot)
            && memberBot->GetMaxHealth()
            && memberBot->GetHealth() == memberBot->GetMaxHealth()
            && !memberBot->IsInCombat() && !memberBot->GetVictim()
            && memberBot->getAttackers().empty();
        member.AliveAndHealed = aliveAndHealed;
        allAliveAndHealed = allAliveAndHealed && aliveAndHealed;
        if (!aliveAndHealed)
            continue;

        for (RaidPrepullConsumableReceipt* receipt : {
                &member.Flask, &member.Food, &member.Prepot })
        {
            std::string failure = observeReceipt(member, *receipt, memberBot);
            if (!failure.empty())
                return fail(failure);
        }
        bool const setupReady = receiptReady(member.Flask)
            && receiptReady(member.Food);
        allSetupReady = allSetupReady && setupReady;
        if (setupReady && !member.SetupReadyAtMs)
            member.SetupReadyAtMs = RaidConsumableNowMs();
    }
    if (!allAliveAndHealed)
        return BotActionArbitration::Outcome::Submitted(
            "raid_prepull_wait_alive_and_healed");

    if (!allSetupReady)
    {
        RaidPrepullConsumableMember& member = current->second;
        Contract const* contract = FindContract(member.ClassSpec);
        if (!contract)
            return fail("raid_prepull_unknown_spec_contract_" + member.ClassSpec);

        auto submit = [&](RaidPrepullConsumableReceipt& receipt,
            uint32 minimumCount) -> BotActionArbitration::Outcome
        {
            uint64 const nowMs = RaidConsumableNowMs();
            if (receipt.NativeUseAwaitingAura
                || receipt.SubmittedAtMs > receipt.FinishedAtMs)
                return BotActionArbitration::Outcome::Submitted(
                    std::string("raid_prepull_wait_") + ReceiptPhase(receipt)
                    + "_native_finish");
            if (receipt.NativeUseFinishedSuccessfully)
                return BotActionArbitration::Outcome::Submitted(
                    std::string("raid_prepull_wait_") + ReceiptPhase(receipt)
                    + "_aura");
            if (receipt.NextRetryAtMs > nowMs)
                return BotActionArbitration::Outcome::Submitted(
                    "raid_prepull_native_use_retry_backoff");

            uint32 const availableCount = CountNativeConsumable(bot,
                receipt.ItemId);
            if (availableCount < minimumCount)
                return fail(std::string("raid_prepull_missing_")
                    + ReceiptPhase(receipt) + "_item");
            Item* item = FindNativeConsumable(bot, receipt.ItemId,
                receipt.SpellId);
            if (!item)
                return fail(std::string("raid_prepull_missing_")
                    + ReceiptPhase(receipt) + "_item_effect");
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(
                receipt.SpellId);
            if (!spellInfo)
                return fail(std::string("raid_prepull_")
                    + ReceiptPhase(receipt) + "_spell_unavailable");
            if (bot->HasUnitState(UNIT_STATE_CASTING)
                || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
            {
                receipt.NextRetryAtMs = nowMs + RaidConsumableRetryMs;
                return BotActionArbitration::Outcome::Submitted(
                    "raid_prepull_wait_native_use_resources");
            }
            if (bot->GetSpellHistory()->GetRemainingCooldown(spellInfo) > 0
                || !bot->GetSpellHistory()->IsReady(spellInfo, receipt.ItemId))
                return fail(std::string("raid_prepull_")
                    + ReceiptPhase(receipt) + "_cooldown_not_ready");

            BotNativeAction::UseItem useItem;
            useItem.Item = item->GetGUID();
            useItem.Target = bot->GetGUID();
            useItem.SpellId = receipt.SpellId;
            receipt.SubmittedItemGuid = useItem.Item;
            receipt.SubmittedAtMs = nowMs;
            receipt.FinishedAtMs = 0;
            receipt.FinishedItemGuid.Clear();
            receipt.PreUseItemCount = availableCount;
            receipt.PostUseItemCount = availableCount;
            receipt.NativeUseFinishedSuccessfully = false;
            receipt.NativeUseAwaitingAura = false;
            receipt.AuraObservedAtMs = 0;
            receipt.CooldownObserved = false;
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                state, bot, useItem, BotMovementArbitration::Owner::Support,
                BotMovementArbitration::Priority::Support);
            if (outcome.Result != BotActionArbitration::Disposition::Committed
                || outcome.LifecyclePhase
                    != BotActionArbitration::Phase::Submitted)
            {
                receipt.SubmittedItemGuid.Clear();
                receipt.SubmittedAtMs = 0;
                receipt.NextRetryAtMs = nowMs + RaidConsumableRetryMs;
                return fail(std::string("raid_prepull_")
                    + ReceiptPhase(receipt) + "_native_use_rejected");
            }
            ++receipt.SubmissionCount;
            receipt.NextRetryAtMs = nowMs + RaidConsumablePendingWaitMs;
            return BotActionArbitration::Outcome::Submitted(
                std::string("raid_prepull_") + ReceiptPhase(receipt)
                + "_native_use_submitted");
        };

        if (!receiptReady(member.Flask))
            return submit(member.Flask, 1);
        if (!receiptReady(member.Food))
            return submit(member.Food, 1);
        return BotActionArbitration::Outcome::Submitted(
            "raid_prepull_wait_exact_roster_setup");
    }

    if (!prepotStageReady)
        return BotActionArbitration::Outcome::Submitted(
            "raid_prepull_wait_prepot_formation_ready");

    RaidPrepullConsumableMember& member = current->second;
    if (!member.PrepotEligibleAtMs)
        member.PrepotEligibleAtMs = RaidConsumableNowMs();

    Unit* bossTarget = target;
    if (!bossTarget || bossTarget->GetEntry()
            != Cohort().Config.ValidationRouteTargetEntry)
        if (!Party().ValidationRouteFocusGuid.IsEmpty())
            bossTarget = ObjectAccessor::GetUnit(*bot,
                Party().ValidationRouteFocusGuid);
    if (!bossTarget || bossTarget->GetEntry()
            != Cohort().Config.ValidationRouteTargetEntry)
        bossTarget = FindBossTarget(bot);
    if (!bossTarget || !bossTarget->IsAlive()
        || bossTarget->GetEntry() != Cohort().Config.ValidationRouteTargetEntry)
        return BotActionArbitration::Outcome::Submitted(
            "raid_prepull_wait_boss_target");
    if (bossTarget->IsInCombat() || bot->IsInCombat())
        return fail("raid_prepull_pull_started_before_consumables");
    auto submitPrepot = [&](RaidPrepullConsumableMember& currentMember)
        -> BotActionArbitration::Outcome
    {
        RaidPrepullConsumableReceipt& receipt = currentMember.Prepot;
        uint64 const nowMs = RaidConsumableNowMs();
        if (!receiptReady(receipt))
        {
            Contract const* contract = FindContract(currentMember.ClassSpec);
            if (!contract)
                return fail("raid_prepull_unknown_spec_contract_"
                    + currentMember.ClassSpec);
            if (receipt.NativeUseAwaitingAura
                || receipt.SubmittedAtMs > receipt.FinishedAtMs)
                return BotActionArbitration::Outcome::Submitted(
                    "raid_prepull_wait_prepot_native_finish");
            uint32 const availableCount = CountNativeConsumable(bot,
                contract->PrepotItemId);
            // Two ordinary potion items are required: this request consumes
            // only the pre-pot, while the second remains for combat policy.
            if (availableCount < 2)
                return fail("raid_prepull_missing_prepot_combat_potion_reserve");
            Item* item = FindNativeConsumable(bot, contract->PrepotItemId,
                contract->PrepotItemSpellId);
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(
                contract->PrepotItemSpellId);
            if (!item)
                return fail("raid_prepull_missing_prepot_item_effect");
            if (!spellInfo)
                return fail("raid_prepull_prepot_spell_unavailable");
            if (bot->HasUnitState(UNIT_STATE_CASTING)
                || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
            {
                receipt.NextRetryAtMs = nowMs + RaidConsumableRetryMs;
                return BotActionArbitration::Outcome::Submitted(
                    "raid_prepull_wait_prepot_native_use_resources");
            }
            if (bot->GetSpellHistory()->GetRemainingCooldown(spellInfo) > 0
                || !bot->GetSpellHistory()->IsReady(spellInfo,
                    contract->PrepotItemId))
                return fail("raid_prepull_prepot_cooldown_not_ready");

            BotNativeAction::UseItem useItem;
            useItem.Item = item->GetGUID();
            useItem.Target = bot->GetGUID();
            useItem.SpellId = contract->PrepotItemSpellId;
            receipt.SubmittedItemGuid = useItem.Item;
            receipt.SubmittedAtMs = nowMs;
            receipt.FinishedAtMs = 0;
            receipt.PreUseItemCount = availableCount;
            receipt.PostUseItemCount = availableCount;
            receipt.NativeUseFinishedSuccessfully = false;
            receipt.NativeUseAwaitingAura = false;
            receipt.AuraObservedAtMs = 0;
            receipt.CooldownObserved = false;
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                state, bot, useItem, BotMovementArbitration::Owner::Support,
                BotMovementArbitration::Priority::Support);
            if (outcome.Result != BotActionArbitration::Disposition::Committed
                || outcome.LifecyclePhase
                    != BotActionArbitration::Phase::Submitted)
                return fail("raid_prepull_prepot_native_use_rejected");
            ++receipt.SubmissionCount;
            receipt.NextRetryAtMs = nowMs + RaidConsumablePendingWaitMs;
            return BotActionArbitration::Outcome::Submitted(
                "raid_prepull_prepot_native_use_submitted");
        }
        currentMember.CombatPotionReservedCount = receipt.PostUseItemCount;
        if (currentMember.CombatPotionReservedCount < 1)
            return fail("raid_prepull_combat_potion_reserve_not_observed");
        return BotActionArbitration::Outcome::Submitted(
            "raid_prepull_wait_all_member_prepots");
    };

    if (!receiptReady(member.Prepot))
        return submitPrepot(member);
    member.CombatPotionReservedCount = member.Prepot.PostUseItemCount;

    bool allPrepotsReady = true;
    for (auto const& [guid, ignored] : raid.RosterByGuid)
    {
        RaidPrepullConsumableMember& rosterMember =
            raid.PrepullConsumablesByGuid[guid];
        rosterMember.CombatPotionReservedCount =
            rosterMember.Prepot.PostUseItemCount;
        if (!receiptReady(rosterMember.Prepot)
            || rosterMember.CombatPotionReservedCount < 1)
            allPrepotsReady = false;
    }
    if (!allPrepotsReady)
        return BotActionArbitration::Outcome::Submitted(
            "raid_prepull_wait_all_member_prepots");

    raid.PrepullConsumablesReady = true;
    raid.PrepullConsumablesReadyAtMs = RaidConsumableNowMs();
    return BotActionArbitration::Outcome::Submitted(
        "raid_prepull_ready_for_pull");
}
