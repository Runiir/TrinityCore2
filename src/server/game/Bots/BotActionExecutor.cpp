#include "Bots/BotActionExecutor.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include <algorithm>
#include <cmath>
#include <utility>
#include <vector>

namespace
{
float GetNominalRange(HealerIntent intent)
{
    return intent == HealerIntent::ExternalDefensive ? 30.0f : 40.0f;
}
}

BotActionResult BotActionExecutor::Execute(Player* owner, Player* bot, ResolvedBotAction const& action)
{
    if (!owner)
        return BotActionResult::NoOwner;
    if (!bot || !bot->IsAlive())
        return BotActionResult::NoBot;
    if (!action.SpellId)
        return BotActionResult::NoAction;

    Unit* target = action.TargetGuid.IsEmpty() ? bot : ObjectAccessor::GetUnit(*bot, action.TargetGuid);
    BotActionResult check = CheckSpell(owner, bot, target, action.SpellId);
    if (check != BotActionResult::Ok)
    {
        RecordFailure(bot->GetGUID(), action.SpellId, action.TargetGuid);
        return check;
    }

    if (IsThrottled(bot->GetGUID(), action.SpellId, action.TargetGuid))
        return BotActionResult::Throttled;

    SpellCastResult result = bot->CastSpell(target, action.SpellId, false);
    if (result != SPELL_CAST_OK)
    {
        RecordFailure(bot->GetGUID(), action.SpellId, action.TargetGuid);
        return BotActionResult::CastFailed;
    }

    RecordSuccess(bot->GetGUID());
    return BotActionResult::Ok;
}

BotActionResult BotActionExecutor::ExecuteCombat(Player* owner, Player* bot, ResolvedCombatAction const& action)
{
    if (!owner)
        return BotActionResult::NoOwner;
    if (!bot || !bot->IsAlive())
        return BotActionResult::NoBot;

    Unit* target = action.TargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, action.TargetGuid);
    if (action.Type == "pull" || action.Type == "move_to_range")
        return Pull(bot, target);
    if (action.Type == "loot")
        return Loot(bot, target);
    if (!action.SpellId)
        return BotActionResult::NoAction;

    BotActionResult check = CheckHostileSpell(owner, bot, target, action.SpellId);
    if (check != BotActionResult::Ok)
    {
        RecordFailure(bot->GetGUID(), action.SpellId, action.TargetGuid);
        return check;
    }

    if (IsThrottled(bot->GetGUID(), action.SpellId, action.TargetGuid))
        return BotActionResult::Throttled;

    SpellCastResult result = bot->CastSpell(target, action.SpellId, false);
    if (result != SPELL_CAST_OK)
    {
        RecordFailure(bot->GetGUID(), action.SpellId, action.TargetGuid);
        return BotActionResult::CastFailed;
    }

    bot->Attack(target, true);
    RecordSuccess(bot->GetGUID());
    return BotActionResult::Ok;
}

BotActionResult BotActionExecutor::CraftRecipe(Player* owner, Player* bot, uint32 recipeSpellId, uint32 count)
{
    if (!count)
        return BotActionResult::NoAction;

    for (uint32 i = 0; i < count; ++i)
    {
        BotActionResult check = CheckRecipe(owner, bot, recipeSpellId);
        if (check != BotActionResult::Ok)
            return check;

        SpellCastResult result = bot->CastSpell(bot, recipeSpellId, false);
        if (result != SPELL_CAST_OK)
            return BotActionResult::CastFailed;
    }

    return BotActionResult::Ok;
}

BotEconomyActionResult BotActionExecutor::VendorTrash(Player* owner, Player* bot)
{
    BotEconomyActionResult result;
    if (!owner)
    {
        result.Result = BotActionResult::NoOwner;
        return result;
    }
    if (!bot || !bot->IsAlive())
    {
        result.Result = BotActionResult::NoBot;
        return result;
    }

    std::vector<std::pair<uint8, uint8>> slots;
    auto considerItem = [&slots](Item* item)
    {
        if (!item || item->IsNotEmptyBag())
            return;

        ItemTemplate const* proto = item->GetTemplate();
        if (!proto || proto->GetQuality() != ITEM_QUALITY_POOR || proto->GetSellPrice() == 0)
            return;

        slots.push_back(std::make_pair(item->GetBagSlot(), item->GetSlot()));
    };

    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        considerItem(bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));

    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
    {
        if (Bag* bag = bot->GetBagByPos(bagSlot))
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                considerItem(bag->GetItemByPos(slot));
    }

    for (auto const& slot : slots)
    {
        Item* item = bot->GetItemByPos(slot.first, slot.second);
        if (!item)
            continue;

        ItemTemplate const* proto = item->GetTemplate();
        if (!proto)
            continue;

        uint32 count = item->GetCount();
        uint64 money = uint64(proto->GetSellPrice()) * count;
        bot->DestroyItem(slot.first, slot.second, true);
        bot->ModifyMoney(money);
        result.ItemCount += count;
        result.Money += money;
    }

    result.Result = result.ItemCount ? BotActionResult::Ok : BotActionResult::NoAction;
    return result;
}

BotEconomyActionResult BotActionExecutor::Repair(Player* owner, Player* bot)
{
    BotEconomyActionResult result;
    if (!owner)
    {
        result.Result = BotActionResult::NoOwner;
        return result;
    }
    if (!bot || !bot->IsAlive())
    {
        result.Result = BotActionResult::NoBot;
        return result;
    }

    uint64 before = bot->GetMoney();
    bot->DurabilityRepairAll(true, 0.0f, false);
    uint64 after = bot->GetMoney();
    result.Money = before > after ? before - after : 0;
    result.Result = BotActionResult::Ok;
    return result;
}

BotActionResult BotActionExecutor::Pull(Player* bot, Unit* target)
{
    if (!bot || !bot->IsAlive())
        return BotActionResult::NoBot;
    if (!target)
        return BotActionResult::InvalidTarget;
    if (!target->IsAlive())
        return BotActionResult::DeadTarget;
    if (!bot->IsValidAttackTarget(target))
        return BotActionResult::InvalidTarget;
    if (!bot->IsWithinLOSInMap(target))
        return BotActionResult::NoLineOfSight;

    Face(bot, target);
    bot->Attack(target, true);
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveChase(target);
    return BotActionResult::Ok;
}

BotActionResult BotActionExecutor::Loot(Player* bot, Unit* target)
{
    if (!bot || !bot->IsAlive())
        return BotActionResult::NoBot;
    if (!target)
        return BotActionResult::InvalidTarget;
    if (target->IsAlive())
        return BotActionResult::InvalidTarget;
    if (!bot->IsWithinDistInMap(target, INTERACTION_DISTANCE))
        return BotActionResult::OutOfRange;

    bot->SendLoot(target->GetGUID(), LOOT_CORPSE);
    return BotActionResult::Ok;
}

void BotActionExecutor::MoveFollow(Player* owner, Player* bot)
{
    if (!owner || !bot || !bot->IsAlive())
        return;

    if (bot->GetMotionMaster()->GetCurrentMovementGeneratorType() == FOLLOW_MOTION_TYPE && bot->IsWithinDistInMap(owner, 8.0f))
        return;

    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveFollow(owner, 3.5f, float(M_PI) / 2.0f);
}

void BotActionExecutor::MoveStay(Player* bot)
{
    if (!bot)
        return;

    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
}

void BotActionExecutor::MoveStop(Player* bot)
{
    if (!bot)
        return;

    bot->StopMoving();
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
}

void BotActionExecutor::MoveTo(Player* bot, float x, float y, float z)
{
    if (!bot || !bot->IsAlive())
        return;

    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MovePoint(0, x, y, z, true);
}

void BotActionExecutor::Face(Player* bot, Unit* target)
{
    if (!bot || !target)
        return;

    bot->SetFacingToObject(target);
}

void BotActionExecutor::MoveUnstuck(Player* owner, Player* bot)
{
    if (!owner || !bot || !bot->IsAlive())
        return;

    float angle = bot->GetAngle(owner);
    float x = bot->GetPositionX() + std::cos(angle) * 2.0f;
    float y = bot->GetPositionY() + std::sin(angle) * 2.0f;
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MovePoint(0, x, y, bot->GetPositionZ(), true);
}

void BotActionExecutor::ResetThrottle(ObjectGuid botGuid)
{
    _failures.erase(botGuid);
}

BotActionResult BotActionExecutor::CheckSpell(Player* owner, Player* bot, Unit* target, uint32 spellId) const
{
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo)
        return BotActionResult::BadSpell;

    if (!target)
        return BotActionResult::InvalidTarget;

    if (!target->IsAlive())
        return BotActionResult::DeadTarget;

    if (!bot->IsValidAssistTarget(target, spellInfo) && target != bot)
        return BotActionResult::NotFriendly;

    if (!bot->IsWithinLOSInMap(target))
        return BotActionResult::NoLineOfSight;

    if (!bot->IsWithinDistInMap(target, GetNominalRange(HealerIntent::EfficientSingleHeal)))
        return BotActionResult::OutOfRange;

    if (bot->HasUnitState(UNIT_STATE_CASTING))
        return BotActionResult::Casting;

    if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
        return BotActionResult::GlobalCooldown;

    if (!bot->GetSpellHistory()->IsReady(spellInfo))
        return BotActionResult::Cooldown;

    int32 powerCost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (powerCost > 0 && bot->GetPower(POWER_MANA) < uint32(powerCost))
        return BotActionResult::NoMana;

    if (owner && bot->GetMap() != owner->GetMap())
        return BotActionResult::NoOwner;

    return BotActionResult::Ok;
}

BotActionResult BotActionExecutor::CheckHostileSpell(Player* owner, Player* bot, Unit* target, uint32 spellId) const
{
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo)
        return BotActionResult::BadSpell;
    if (!target)
        return BotActionResult::InvalidTarget;
    if (!target->IsAlive())
        return BotActionResult::DeadTarget;
    if (!bot->IsValidAttackTarget(target, spellInfo))
        return BotActionResult::InvalidTarget;
    if (!bot->IsWithinLOSInMap(target))
        return BotActionResult::NoLineOfSight;
    if (!bot->IsWithinDistInMap(target, std::max(5.0f, spellInfo->GetMaxRange(false))))
        return BotActionResult::OutOfRange;
    if (bot->HasUnitState(UNIT_STATE_CASTING))
        return BotActionResult::Casting;
    if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
        return BotActionResult::GlobalCooldown;
    if (!bot->GetSpellHistory()->IsReady(spellInfo))
        return BotActionResult::Cooldown;
    int32 powerCost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (powerCost > 0 && bot->GetPower(POWER_MANA) < uint32(powerCost))
        return BotActionResult::NoMana;
    if (owner && bot->GetMap() != owner->GetMap())
        return BotActionResult::NoOwner;
    return BotActionResult::Ok;
}

BotActionResult BotActionExecutor::CheckRecipe(Player* owner, Player* bot, uint32 recipeSpellId) const
{
    if (!owner)
        return BotActionResult::NoOwner;
    if (!bot || !bot->IsAlive())
        return BotActionResult::NoBot;
    if (owner->GetMap() != bot->GetMap())
        return BotActionResult::NoOwner;

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(recipeSpellId);
    if (!spellInfo)
        return BotActionResult::BadSpell;
    if (!bot->HasSpell(recipeSpellId))
        return BotActionResult::BadSpell;
    if (bot->HasUnitState(UNIT_STATE_CASTING))
        return BotActionResult::Casting;
    if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
        return BotActionResult::GlobalCooldown;

    for (uint8 i = 0; i < MAX_SPELL_REAGENTS; ++i)
    {
        if (spellInfo->Reagent[i] <= 0)
            continue;

        if (bot->GetItemCount(uint32(spellInfo->Reagent[i])) < spellInfo->ReagentCount[i])
            return BotActionResult::InvalidTarget;
    }

    return BotActionResult::Ok;
}

bool BotActionExecutor::IsThrottled(ObjectGuid botGuid, uint32 spellId, ObjectGuid targetGuid)
{
    auto itr = _failures.find(botGuid);
    if (itr == _failures.end())
        return false;

    FailureState& state = itr->second;
    if (state.SpellId != spellId || state.TargetGuid != targetGuid || state.SuppressMs == 0)
        return false;

    state.SuppressMs -= std::min<uint32>(state.SuppressMs, 500);
    return state.SuppressMs > 0;
}

void BotActionExecutor::RecordFailure(ObjectGuid botGuid, uint32 spellId, ObjectGuid targetGuid)
{
    FailureState& state = _failures[botGuid];
    if (state.SpellId == spellId && state.TargetGuid == targetGuid)
        ++state.Count;
    else
    {
        state.SpellId = spellId;
        state.TargetGuid = targetGuid;
        state.Count = 1;
    }

    if (state.Count >= 3)
        state.SuppressMs = 2500;
}

void BotActionExecutor::RecordSuccess(ObjectGuid botGuid)
{
    _failures.erase(botGuid);
}
