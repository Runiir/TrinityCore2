#include "Bots/BotActionExecutor.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include <algorithm>
#include <cmath>

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
