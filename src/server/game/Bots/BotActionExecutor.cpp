#include "Bots/BotActionExecutor.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "CharmInfo.h"
#include "DataStores/DBCStores.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "Entities/Pet/Pet.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Server/WorldSession.h"
#include "WorldPacket.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Creature.h"
#include "Loot/Loot.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <utility>
#include <vector>

namespace
{
constexpr uint32 ActionDarkTransformationSpellId = 63560;
constexpr uint32 FelguardEntry = 17252;
constexpr uint32 FelstormSpellId = 89751;
constexpr uint32 ShadowfiendSpellId = 34433;

bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth = 0)
{
    if (!spellInfo || depth > 4)
        return false;
    if (spellInfo->Id == 48505 || spellInfo->Id == FelstormSpellId)
        return true;
    for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[effectIndex];
        if (!effect.IsEffect())
            continue;
        if (!spellInfo->IsPositiveEffect(effectIndex)
            && (effect.ChainTarget > 1 || effect.IsTargetingArea()
                || effect.IsEffect(SPELL_EFFECT_PERSISTENT_AREA_AURA)
                || effect.IsAreaAuraEffect()))
            return true;
        if (effect.TriggerSpell
            && SpellHasHostileMultiTargetSemantics(sSpellMgr->GetSpellInfo(effect.TriggerSpell), depth + 1))
            return true;
    }
    return false;
}

float GetNominalRange(HealerIntent intent)
{
    return intent == HealerIntent::ExternalDefensive ? 30.0f : 40.0f;
}

bool HasEnoughPowerForSpell(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    // Dark Transformation consumes the ghoul's Shadow Infusion stacks.  The
    // owner-side ready aura and native spell script validate that pet resource;
    // its DBC power fields are not a player-power cost.
    if (spellInfo->Id == ActionDarkTransformationSpellId)
        return true;

    if (spellInfo->PowerType == POWER_RUNE && spellInfo->RuneCostID && bot->getClass() == CLASS_DEATH_KNIGHT)
    {
        SpellRuneCostEntry const* runeCost = sSpellRuneCostStore.LookupEntry(spellInfo->RuneCostID);
        if (runeCost && !runeCost->NoRuneCost())
        {
            std::array<int32, 3> required = { int32(runeCost->RuneCost[0]), int32(runeCost->RuneCost[1]), int32(runeCost->RuneCost[2]) };
            uint8 deathRunes = 0;
            for (uint8 i = 0; i < MAX_RUNES; ++i)
            {
                if (std::abs(bot->GetRuneCooldown(i)) > 0.0001f)
                    continue;

                switch (bot->GetCurrentRune(i))
                {
                    case RuneType::Blood:
                        if (required[0] > 0)
                            --required[0];
                        break;
                    case RuneType::Unholy:
                        if (required[1] > 0)
                            --required[1];
                        break;
                    case RuneType::Frost:
                        if (required[2] > 0)
                            --required[2];
                        break;
                    case RuneType::Death:
                        ++deathRunes;
                        break;
                    default:
                        break;
                }
            }

            int32 deficit = 0;
            for (int32 count : required)
                deficit += std::max<int32>(0, count);
            if (deficit > deathRunes)
                return false;
        }
    }

    int32 powerCost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (powerCost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > powerCost;
    Powers powerType = Powers(spellInfo->PowerType);
    if (powerType != bot->GetPowerType())
        return bot->GetPower(powerType) >= uint32(powerCost);
    return bot->GetPower(bot->GetPowerType()) >= uint32(powerCost);
}

bool IsSchedulingResult(BotActionResult result)
{
    return result == BotActionResult::Casting || result == BotActionResult::GlobalCooldown;
}

Item* FindOnUseItemForSpell(Player* player, uint32 spellId)
{
    if (!player || !spellId)
        return nullptr;

    auto matches = [player, spellId](Item* item) -> bool
    {
        ItemTemplate const* itemTemplate = item ? item->GetTemplate() : nullptr;
        if (!itemTemplate || (item->IsPotion() && player->GetLastPotionId()))
            return false;
        for (uint8 index = 0; index < itemTemplate->Effects.size(); ++index)
        {
            ItemEffect const& effect = itemTemplate->Effects[index];
            if (effect.SpellID == int32(spellId) && effect.Trigger == ITEM_SPELLTRIGGER_ON_USE
                && (!effect.Charges || item->GetSpellCharges(index)
                    || (itemTemplate->GetClass() == ITEM_CLASS_CONSUMABLE && item->GetCount())))
                return true;
        }
        return false;
    };

    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot); matches(item))
            return item;
    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        if (Bag* bag = player->GetBagByPos(bagSlot))
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                if (Item* item = bag->GetItemByPos(slot); matches(item))
                    return item;
    return nullptr;
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

    uint64 const ownerGuid = bot->GetGUID().GetRawValue();
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(action.SpellId);
    Unit* target = action.TargetGuid.IsEmpty() ? bot : ObjectAccessor::GetUnit(*bot, action.TargetGuid);
    if (BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid)
        && spellInfo && !spellInfo->IsPositive())
        return BotActionResult::NoAction;
    if (Creature const* creature = target ? target->ToCreature() : nullptr;
        creature && BotRaidAreaAuthority::IsProtectedEncounterTarget(
            ownerGuid, creature->GetEntry(), creature->GetSpawnId(),
            creature->GetGUID().GetRawValue()))
        return BotActionResult::NoAction;
    if (BotRaidAreaAuthority::HasProtectedEncounterEntries(ownerGuid)
        && SpellHasHostileMultiTargetSemantics(spellInfo))
        return BotActionResult::NoAction;
    BotActionResult check = CheckSpell(owner, bot, target, action.SpellId);
    if (check != BotActionResult::Ok)
    {
        if (!IsSchedulingResult(check))
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
    _lastSpellCastResult = 0;
    if (!owner)
        return BotActionResult::NoOwner;
    if (!bot || !bot->IsAlive())
        return BotActionResult::NoBot;
    if (!action.Valid)
        return BotActionResult::NoAction;

    uint64 const ownerGuid = bot->GetGUID().GetRawValue();
    if (BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid))
        return BotActionResult::NoAction;

    BotRaidAreaAuthority::Set(ownerGuid, action.SuppressAreaDamage);

    Unit* target = action.TargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, action.TargetGuid);
    if (Creature const* creature = target ? target->ToCreature() : nullptr;
        creature && BotRaidAreaAuthority::IsProtectedEncounterTarget(
            ownerGuid, creature->GetEntry(), creature->GetSpawnId(),
            creature->GetGUID().GetRawValue()))
        return BotActionResult::NoAction;
    if (action.Type == "pull" || action.Type == "move_to_range")
    {
        if (action.MovementDirective == "melee")
            return Pull(bot, target);
        if (!target)
            return BotActionResult::InvalidTarget;
        Face(bot, target);
        return BotActionResult::Ok;
    }
    if (action.Type == "loot")
        return Loot(bot, target);
    if (action.Type == "auto_attack")
    {
        if (!target || !target->IsAlive() || !bot->IsValidAttackTarget(target))
            return BotActionResult::InvalidTarget;
        Face(bot, target);
        if (action.AutoAttackMode == "melee")
        {
            bot->Attack(target, true);
            return BotActionResult::Ok;
        }
        return BotActionResult::NoAction;
    }
    if (!action.SpellId)
        return BotActionResult::NoAction;
    if ((action.SuppressAreaDamage
            || BotRaidAreaAuthority::HasProtectedEncounterEntries(ownerGuid))
        && SpellHasHostileMultiTargetSemantics(sSpellMgr->GetSpellInfo(action.SpellId)))
        return BotActionResult::NoAction;

    if (!target || !target->IsAlive() || (target != bot && !bot->IsValidAttackTarget(target)))
        return BotActionResult::InvalidTarget;
    if (target != bot)
        Face(bot, target);

    // White swings, Auto Shot, and pet attacks are independent sources of role
    // uptime. Start them before checking the selected ability so a GCD or
    // cooldown does not leave a tank, melee DPS, hunter, or pet class idle.
    if (target != bot && bot->IsValidAttackTarget(target))
    {
        if (action.AutoAttackMode == "melee")
            bot->Attack(target, true);
        else if (action.AutoAttackMode == "ranged" && bot->getClass() == CLASS_HUNTER
            && !bot->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
            bot->CastSpell(target, 75, false); // Auto Shot

        // Command the player's primary pet through the same validated handler
        // used by CMSG_PET_ACTION. Guardians and totems retain their native AI;
        // autonomous runtime never writes their victim/react/movement state.
        if (Unit* controlled = bot->GetFirstControlled(); controlled
            && controlled->IsAlive() && controlled->GetCharmInfo()
            && controlled->IsValidAttackTarget(target)
            && bot->GetSession())
            bot->GetSession()->HandlePetActionHelper(controlled,
                controlled->GetGUID(), COMMAND_ATTACK, ACT_COMMAND,
                target->GetGUID(), target->GetPositionX(),
                target->GetPositionY(), target->GetPositionZ());

        if (Pet* pet = bot->GetPet())
            if (pet->GetEntry() == FelguardEntry && pet->IsWithinMeleeRange(target)
                && !action.SuppressAreaDamage
                && !pet->HasUnitState(UNIT_STATE_CASTING) && pet->HasSpell(FelstormSpellId))
                if (SpellInfo const* felstorm = sSpellMgr->GetSpellInfo(FelstormSpellId))
                    if (pet->GetSpellHistory()->IsReady(felstorm))
                        pet->CastSpell(pet, FelstormSpellId, false);
    }

    // Auto Shot is an autorepeat state, not a spell that should be resubmitted
    // every time the rotation reaches its fallback action.  The uptime block
    // above has already started it, so treat the active state as success.  A
    // second CastSpell(75) returns SPELL_FAILED_DONT_REPORT and otherwise
    // pollutes cast-failure telemetry without representing lost damage.
    if (action.SpellId == 75 && bot->getClass() == CLASS_HUNTER
        && bot->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
    {
        RecordSuccess(bot->GetGUID());
        return BotActionResult::Ok;
    }

    if (action.Type == "use_item")
    {
        Item* item = FindOnUseItemForSpell(bot, action.SpellId);
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(action.SpellId);
        if (!item || !spellInfo)
            return BotActionResult::NoAction;
        if (bot->HasUnitState(UNIT_STATE_CASTING))
            return BotActionResult::Casting;
        if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
            return BotActionResult::GlobalCooldown;
        if (!bot->GetSpellHistory()->IsReady(spellInfo))
            return BotActionResult::Cooldown;
        if (IsThrottled(bot->GetGUID(), action.SpellId, action.TargetGuid))
            return BotActionResult::Throttled;

        SpellCastTargets targets;
        Spell* spell = new Spell(bot, spellInfo, TRIGGERED_NONE);
        spell->m_CastItem = item;
        SpellCastResult result = spell->prepare(targets);
        _lastSpellCastResult = uint32(result);
        if (result != SPELL_CAST_OK)
        {
            RecordFailure(bot->GetGUID(), action.SpellId, action.TargetGuid);
            return BotActionResult::CastFailed;
        }

        RecordSuccess(bot->GetGUID());
        return BotActionResult::Ok;
    }

    BotActionResult check = CheckHostileSpell(owner, bot, target, action.SpellId);
    if (check != BotActionResult::Ok)
    {
        if (!IsSchedulingResult(check))
            RecordFailure(bot->GetGUID(), action.SpellId, action.TargetGuid);
        return check;
    }

    if (IsThrottled(bot->GetGUID(), action.SpellId, action.TargetGuid))
        return BotActionResult::Throttled;

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(action.SpellId);
    if (spellInfo && spellInfo->CalcCastTime(bot->getLevel()) > 0
        && (bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING)))
    {
        // Rerun138 proved that stopping and submitting a cast-time offensive
        // spell in the same decision can still be rejected as moving. Yield
        // this tick after stopping so the next profile decision submits only
        // after the movement state has settled.
        bot->StopMoving();
        bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        bot->GetMotionMaster()->MoveIdle();
        return BotActionResult::Casting;
    }

    // The client normally has an enemy selected when Shadowfiend is summoned.
    // Preserve that contract for server-driven bots so the new guardian can
    // acquire the intended target in its summon callback.
    if (action.SpellId == ShadowfiendSpellId && target != bot)
        bot->SetTarget(target->GetGUID());

    CastSpellExtraArgs castArgs(TRIGGERED_NONE);
    SpellCastResult result = spellInfo && (spellInfo->GetExplicitTargetMask() & TARGET_FLAG_DEST_LOCATION)
        ? bot->CastSpell(Position{ target->GetPositionX(), target->GetPositionY(), target->GetPositionZ() }, action.SpellId, castArgs)
        : bot->CastSpell(target, action.SpellId, castArgs);
    _lastSpellCastResult = uint32(result);
    if (result != SPELL_CAST_OK)
    {
        RecordFailure(bot->GetGUID(), action.SpellId, action.TargetGuid);
        return BotActionResult::CastFailed;
    }

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

    // This command has no vendor parameter.  Selling without a visible,
    // interactable vendor bypasses the client and must not mutate inventory or
    // money.  A future native VendorIntent supplies the vendor GUID and uses
    // the normal sell-item opcode handler.
    result.Result = BotActionResult::NoAction;
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

    // Repair also requires a real visible vendor and the native repair opcode.
    // Do not grant a vendorless repair from an administrative bot command.
    result.Result = BotActionResult::NoAction;
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
    return AutoLoot(bot, target).Result;
}

BotActionExecutor::LootResult BotActionExecutor::AutoLoot(Player* bot, Unit* target)
{
    LootResult result;
    if (!bot || !bot->IsAlive())
    {
        result.Result = BotActionResult::NoBot;
        result.Reason = "bot_unavailable";
        return result;
    }
    if (!target)
    {
        result.Result = BotActionResult::InvalidTarget;
        result.Reason = "target_unavailable";
        return result;
    }
    if (target->IsAlive())
    {
        result.Result = BotActionResult::InvalidTarget;
        result.Reason = "target_alive";
        return result;
    }
    if (!bot->IsWithinDistInMap(target, INTERACTION_DISTANCE))
    {
        result.Result = BotActionResult::OutOfRange;
        result.Reason = "corpse_out_of_range";
        return result;
    }

    Creature* creature = target->ToCreature();
    if (!creature)
    {
        result.Result = BotActionResult::InvalidTarget;
        result.Reason = "target_not_creature";
        return result;
    }

    ::Loot* loot = &creature->loot;
    if (!creature->HasFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_LOOTABLE) && loot->isLooted())
    {
        result.Result = BotActionResult::NoAction;
        result.Reason = "already_looted";
        return result;
    }

    WorldSession* session = bot->GetSession();
    if (!session)
    {
        result.Result = BotActionResult::NoAction;
        result.Reason = "session_unavailable";
        return result;
    }

    WorldPacket lootRequest(CMSG_LOOT, 8);
    lootRequest << creature->GetGUID();
    session->HandleLootOpcode(lootRequest);
    if (bot->GetLootGUID() != creature->GetGUID())
    {
        result.Result = BotActionResult::InvalidTarget;
        result.Reason = "loot_permission_denied";
        result.LootStateCleared = bot->GetLootGUID().IsEmpty() && !bot->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_LOOTING);
        return result;
    }

    uint8 beforeUnlooted = loot->unlootedCount;
    uint32 beforeGold = loot->gold;
    uint64 beforeMoney = bot->GetMoney();
    if (loot->gold)
    {
        WorldPacket moneyRequest(CMSG_LOOT_MONEY, 0);
        session->HandleLootMoneyOpcode(moneyRequest);
        result.Money = bot->GetMoney() >= beforeMoney ? bot->GetMoney() - beforeMoney : 0;
    }

    uint32 const maxSlot = loot->GetMaxSlotInLootFor(bot);
    for (uint32 slot = 0; slot < maxSlot; ++slot)
    {
        LootItem* item = loot->LootItemInSlot(slot, bot);
        if (!item)
            continue;

        uint8 const unlootedBeforeSlot = loot->unlootedCount;
        uint8 const count = item->count;
        WorldPacket storeRequest(CMSG_AUTOSTORE_LOOT_ITEM, 1);
        storeRequest << uint8(slot);
        session->HandleAutostoreLootItemOpcode(storeRequest);
        if (loot->unlootedCount < unlootedBeforeSlot)
            result.ItemsCount += count;
    }

    WorldPacket releaseRequest(CMSG_LOOT_RELEASE, 8);
    releaseRequest << creature->GetGUID();
    session->HandleLootReleaseOpcode(releaseRequest);

    result.LootStateCleared = bot->GetLootGUID().IsEmpty() && !bot->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_LOOTING);
    if (result.ItemsCount || result.Money)
    {
        result.Result = BotActionResult::Ok;
        result.Reason = "looted";
    }
    else if (!beforeUnlooted && !beforeGold)
    {
        result.Result = BotActionResult::NoAction;
        result.Reason = "empty";
    }
    else
    {
        result.Result = BotActionResult::NoAction;
        result.Reason = "no_transfer";
    }
    return result;
}

void BotActionExecutor::MoveFollow(Player* owner, Player* bot)
{
    MoveFollow(owner, bot, 3.5f);
}

void BotActionExecutor::MoveFollow(Player* owner, Player* bot, float followDistance)
{
    if (!owner || !bot || !bot->IsAlive())
        return;

    followDistance = std::max(1.5f, followDistance);
    if (bot->GetMotionMaster()->GetCurrentMovementGeneratorType() == FOLLOW_MOTION_TYPE && bot->IsWithinDistInMap(owner, followDistance + 4.0f))
        return;

    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveFollow(owner, followDistance, float(M_PI) / 2.0f);
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

    if (!HasEnoughPowerForSpell(bot, spellInfo))
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
    if (target != bot && !bot->IsValidAttackTarget(target, spellInfo))
        return BotActionResult::InvalidTarget;
    if (!bot->IsWithinLOSInMap(target))
        return BotActionResult::NoLineOfSight;
    if (!bot->IsWithinDistInMap(target, std::max(5.0f, spellInfo->GetMaxRange(false))))
        return BotActionResult::OutOfRange;
    // Rerun157 captured eight spell_cast_result_150 submissions when scripted
    // control landed between profile resolution and CastSpell. Repeat the
    // resolver's native controlled-state preflight at the executor boundary;
    // this is a scheduling wait, so use the existing throttled result rather
    // than recording a rejected cast.
    if (bot->HasUnitState(UNIT_STATE_CONTROLLED))
        return BotActionResult::Throttled;
    if (bot->HasUnitState(UNIT_STATE_CASTING))
        return BotActionResult::Casting;
    if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
        return BotActionResult::GlobalCooldown;
    if (!bot->GetSpellHistory()->IsReady(spellInfo))
        return BotActionResult::Cooldown;
    if (spellInfo->NeedsComboPoints()
        && (!bot->GetComboPoints() || (target != bot && bot->GetComboTarget() != target->GetGUID())))
        return BotActionResult::NoMana;
    if (!HasEnoughPowerForSpell(bot, spellInfo))
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
