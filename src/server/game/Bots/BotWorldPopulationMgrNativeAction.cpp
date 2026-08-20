#include "Bots/BotWorldPopulationMgr.h"

#include "CharmInfo.h"
#include "Corpse.h"
#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "GameClient.h"
#include "GameTime.h"
#include "Item.h"
#include "ItemTemplate.h"
#include "Map.h"
#include "MotionMaster.h"
#include "MovementPackets.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include "Server/Packets/NPCPackets.h"
#include "Server/Packets/SpellPackets.h"

#include <algorithm>
#include <chrono>
#include <limits>
#include <string>
#include <type_traits>
#include <utility>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

bool CancelRemovableShapeshifts(Player* bot)
{
    if (!bot)
        return false;

    Unit::AuraEffectList const& shapeshiftAuras = bot->GetAuraEffectsByType(SPELL_AURA_MOD_SHAPESHIFT);
    std::vector<Aura*> removable;
    for (AuraEffect* effect : shapeshiftAuras)
    {
        Aura* aura = effect ? effect->GetBase() : nullptr;
        SpellInfo const* auraInfo = aura ? aura->GetSpellInfo() : nullptr;
        if (!auraInfo || auraInfo->HasAttribute(SPELL_ATTR0_NO_AURA_CANCEL)
            || !auraInfo->IsPositive() || auraInfo->IsPassive())
            continue;
        if (std::find(removable.begin(), removable.end(), aura) == removable.end())
            removable.push_back(aura);
    }

    for (Aura* aura : removable)
        bot->RemoveOwnedAura(aura, AuraRemoveFlags::ByCancel);
    return !removable.empty();
}

}

BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent(
    WorldBotState& state, Player* bot, BotNativeAction::Intent const& intent,
    BotMovementArbitration::Owner movementOwner,
    BotMovementArbitration::Priority movementPriority)
{
    if (!bot || !bot->IsInWorld() || !bot->GetSession())
        return BotActionArbitration::Outcome::Retryable("native_intent_bot_unavailable");

    auto resolveCombatResTarget = [&](ObjectGuid targetGuid, uint32 spellId,
        uint64 reservationAtMs, uint64 reservationUntilMs,
        WorldBotState*& targetState, Player*& target,
        std::string& declineReason) -> bool
    {
        targetState = nullptr;
        target = nullptr;
        for (WorldBotState& candidate : Party().Bots)
            if (candidate.Guid == targetGuid)
            {
                targetState = &candidate;
                target = GetLoadedBot(candidate);
                break;
            }
        if (!targetState || !target)
        {
            declineReason = "declined_target_unloaded";
            return false;
        }
        if (targetState->NativeBattleResOwnerGuid != bot->GetGUID()
            || targetState->NativeBattleResSpellId != spellId
            || targetState->NativeBattleResDecisionAtMs != reservationAtMs
            || targetState->NativeBattleResDecisionUntilMs != reservationUntilMs)
        {
            declineReason = "declined_typed_intent_identity_drift";
            return false;
        }
        return CurrentCombatResOwnerUsable(*targetState, target, NowMs(),
            declineReason);
    };

    auto declineCombatResIntent = [&](WorldBotState* targetState,
        Player* target, uint32 spellId, uint64 reservationAtMs,
        uint64 reservationUntilMs, std::string const& declineReason)
    {
        if (!targetState || !target
            || targetState->NativeBattleResOwnerGuid != bot->GetGUID()
            || targetState->NativeBattleResSpellId != spellId
            || targetState->NativeBattleResDecisionAtMs != reservationAtMs
            || targetState->NativeBattleResDecisionUntilMs
                != reservationUntilMs)
            return;
        uint64 const nowMs = NowMs();
        PublishNativeBattleResDecision(*targetState, target,
            declineReason.empty() ? "declined_typed_intent_rejected" : declineReason,
            bot->GetGUID(), spellId, nowMs, nowMs + 5000);
    };

    return std::visit([&](auto const& action) -> BotActionArbitration::Outcome
    {
        using T = std::decay_t<decltype(action)>;
        if constexpr (std::is_same_v<T, BotNativeAction::Move>)
        {
            bool moved = MoveBotToPoint(state, bot, action.X, action.Y, action.Z,
                false, movementOwner, movementPriority);
            return moved
                ? BotActionArbitration::Outcome::Submitted("native_move_submitted")
                : BotActionArbitration::Outcome::Retryable("native_move_retryable");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::NativeDescent>)
        {
            return ExecuteNativeDescentIntent(state, bot, action);
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::CombatResApproach>)
        {
            WorldBotState* targetState = nullptr;
            Player* target = nullptr;
            std::string declineReason;
            if (!resolveCombatResTarget(action.Target, action.SpellId,
                    action.ReservationAtMs, action.ReservationUntilMs,
                    targetState, target, declineReason))
            {
                declineCombatResIntent(targetState, target, action.SpellId,
                    action.ReservationAtMs, action.ReservationUntilMs,
                    declineReason);
                return BotActionArbitration::Outcome::Retryable(
                    declineReason.empty() ? "combat_res_approach_invalid"
                        : declineReason);
            }
            if (targetState->NativeBattleResDecision != "reserved_approach")
                return BotActionArbitration::Outcome::Retryable(
                    "combat_res_approach_phase_changed");

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(action.SpellId);
            float const resurrectionRange = spellInfo
                ? std::max(5.0f,
                    bot->GetSpellMaxRangeForTarget(target, spellInfo)) : 5.0f;
            auto acceptCurrentApproach = [&]
            {
                uint64 const acceptedAtMs = NowMs();
                targetState->NativeBattleResApproachIntentDecisionAtMs =
                    targetState->NativeBattleResDecisionAtMs;
                targetState->NativeBattleResApproachIntentAcceptedUntilMs =
                    std::min(targetState->NativeBattleResDecisionUntilMs,
                        acceptedAtMs + 1500);
            };
            if (bot->HasUnitState(UNIT_STATE_CASTING))
            {
                // A player does not start walking in the middle of an
                // ordinary hard cast. Keep the exact reservation receipt
                // bounded and let that cast finish before submitting native
                // movement. Instant/GCD-only actions still move concurrently.
                acceptCurrentApproach();
                return BotActionArbitration::Outcome::Progressed(
                    "typed_combat_res_waiting_for_active_cast");
            }
            if (bot->IsWithinLOSInMap(target)
                && bot->IsWithinDistInMap(target, resurrectionRange))
            {
                // The approach intent owns movement only.  Holding inside the
                // cast envelope while an independent damage cast/GCD finishes
                // is accepted progress; a later idle tick emits CombatResCast.
                acceptCurrentApproach();
                return BotActionArbitration::Outcome::Progressed(
                    "typed_combat_res_cast_resources_pending");
            }

            bool const moved = MoveBotToPoint(state, bot,
                target->GetPositionX(), target->GetPositionY(),
                target->GetPositionZ(), false,
                BotMovementArbitration::Owner::Support,
                BotMovementArbitration::Priority::Support, target);
            if (!moved)
                return BotActionArbitration::Outcome::Retryable(
                    "combat_res_approach_not_submitted");

            acceptCurrentApproach();
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target,
                "validation_route_resurrection");
            RecordEvent(state, bot, "validation_route_resurrection", target,
                "typed_approach_intent_submitted", raw.c_str(),
                semantic.c_str(), bot->GetExactDist(target), 0,
                action.SpellId);
            return BotActionArbitration::Outcome::Submitted(
                "typed_combat_res_approach_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::CombatResCast>)
        {
            WorldBotState* targetState = nullptr;
            Player* target = nullptr;
            std::string declineReason;
            if (!resolveCombatResTarget(action.Target, action.SpellId,
                    action.ReservationAtMs, action.ReservationUntilMs,
                    targetState, target, declineReason))
            {
                declineCombatResIntent(targetState, target, action.SpellId,
                    action.ReservationAtMs, action.ReservationUntilMs,
                    declineReason);
                return BotActionArbitration::Outcome::Retryable(
                    declineReason.empty() ? "combat_res_cast_invalid"
                        : declineReason);
            }
            if (targetState->NativeBattleResDecision
                == "reserved_cast_submitted")
            {
                if (bot->FindCurrentSpellBySpellId(action.SpellId))
                    return BotActionArbitration::Outcome::Started(
                        "typed_combat_res_cast_in_progress");
                if (target->IsResurrectRequestedBy(bot->GetGUID()))
                    return BotActionArbitration::Outcome::Progressed(
                        "typed_combat_res_request_observed");
                declineCombatResIntent(targetState, target, action.SpellId,
                    action.ReservationAtMs, action.ReservationUntilMs,
                    "declined_submitted_cast_identity_drift");
                return BotActionArbitration::Outcome::Retryable(
                    "submitted_combat_res_not_observed");
            }

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(action.SpellId);
            float const resurrectionRange = spellInfo
                ? std::max(5.0f,
                    bot->GetSpellMaxRangeForTarget(target, spellInfo)) : 5.0f;
            if (!spellInfo || !bot->IsWithinLOSInMap(target)
                || !bot->IsWithinDistInMap(target, resurrectionRange))
                return BotActionArbitration::Outcome::Retryable(
                    "combat_res_cast_envelope_lost");

            // Rebirth is a normal player spell and Cataclysm rejects it while
            // the druid is still in cat/bear/travel form.  Let the owner use
            // the same native form-cancel transition a player would use,
            // retain the bounded reservation, and retry the cast on the next
            // decision tick.  This is deliberately cancellation only: no
            // aura is added, no form is manufactured, and native Spell
            // validation remains authoritative for the eventual cast.
            if (bot->HasAuraType(SPELL_AURA_MOD_SHAPESHIFT)
                && CancelRemovableShapeshifts(bot))
                return BotActionArbitration::Outcome::Progressed(
                    "typed_combat_res_cancelled_shapeshift");

            if (spellInfo->CalcCastTime(bot->getLevel()) > 0)
            {
                bot->StopMoving();
                bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                bot->GetMotionMaster()->MoveIdle();
            }
            // Rebirth's DBC target is a corpse ally.  When Trinity has already
            // materialized the player's corpse, preserve that native target
            // object instead of coercing it to a dead Unit; the latter can
            // prepare successfully but never reach EffectResurrect.
            SpellCastResult const castResult = [&]()
            {
                if (Corpse* corpse = target->GetCorpse())
                {
                    SpellCastTargets corpseTargets;
                    corpseTargets.SetCorpseTarget(corpse);
                    return bot->CastSpell(
                        CastSpellTargetArg(std::move(corpseTargets)),
                        action.SpellId, false);
                }
                return bot->CastSpell(target, action.SpellId, false);
            }();
            if (castResult != SPELL_CAST_OK)
            {
                std::string const resultLabel = "spell_cast_result_"
                    + std::to_string(uint32(castResult));
                std::string raw = BuildRawJson(bot, target);
                std::string semantic = BuildSemanticJson(bot, target,
                    "validation_route_resurrection");
                RecordEvent(state, bot, "validation_route_resurrection",
                    target, resultLabel.c_str(), raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(target), 0, action.SpellId);
                declineCombatResIntent(targetState, target, action.SpellId,
                    action.ReservationAtMs, action.ReservationUntilMs,
                    "declined_native_cast_rejected");
                return BotActionArbitration::Outcome::Retryable(
                    "typed_combat_res_cast_rejected");
            }

            state.NativeResurrectionRejectedTargetGuid.Clear();
            state.NativeResurrectionRejectedSpellId = 0;
            state.NativeResurrectionRejectedCastResult = 0;
            state.NativeResurrectionRetryAfterMs = 0;
            state.NativeResurrectionConsecutiveFailures = 0;
            uint64 const submittedAtMs = NowMs();
            targetState->NativeResurrectionPendingUntilMs = submittedAtMs
                + uint64(std::max<int32>(5000,
                    spellInfo->CalcCastTime(bot->getLevel()) + 5000));
            targetState->NativeResurrectionCasterGuid = bot->GetGUID();
            targetState->NativeResurrectionSpellId = action.SpellId;
            PublishNativeBattleResDecision(*targetState, target,
                "reserved_cast_submitted", bot->GetGUID(), action.SpellId,
                submittedAtMs,
                targetState->NativeResurrectionPendingUntilMs);
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target,
                "validation_route_resurrection");
            RecordEvent(state, bot, "validation_route_resurrection", target,
                "typed_native_cast_submitted", raw.c_str(), semantic.c_str(),
                bot->GetExactDist(target), 0, action.SpellId);
            return BotActionArbitration::Outcome::Submitted(
                "typed_combat_res_cast_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::CombatResAccept>)
        {
            WorldBotState* targetState = nullptr;
            Player* target = nullptr;
            std::string declineReason;
            if (!resolveCombatResTarget(action.Target, action.SpellId,
                    action.ReservationAtMs, action.ReservationUntilMs,
                    targetState, target, declineReason))
            {
                declineCombatResIntent(targetState, target, action.SpellId,
                    action.ReservationAtMs, action.ReservationUntilMs,
                    declineReason);
                return BotActionArbitration::Outcome::Retryable(
                    declineReason.empty() ? "combat_res_accept_invalid"
                        : declineReason);
            }
            if (targetState->NativeBattleResDecision
                    != "reserved_cast_submitted"
                || !target->IsResurrectRequestedBy(bot->GetGUID())
                || !target->GetSession()
                || !target->GetSession()->IsBotSession())
            {
                declineCombatResIntent(targetState, target, action.SpellId,
                    action.ReservationAtMs, action.ReservationUntilMs,
                    "declined_native_request_unavailable");
                return BotActionArbitration::Outcome::Retryable(
                    "typed_combat_res_request_unavailable");
            }

            WorldPacket response(CMSG_RESURRECT_RESPONSE, 9);
            response << bot->GetGUID();
            response << uint8(1);
            target->GetSession()->HandleResurrectResponseOpcode(response);
            if (target->IsBeingTeleportedNear())
            {
                GameClient* client = target->GetSession()->GetGameClient();
                if (client)
                {
                    client->SetMovedUnit(target, true);
                    client->SetActivelyMovedUnit(target);
                    WorldPacket ackPayload(MSG_MOVE_TELEPORT_ACK, 0);
                    WorldPackets::Movement::MoveTeleportAck ack(
                        std::move(ackPayload));
                    ack.MoverGUID = target->GetGUID();
                    target->GetSession()->HandleMoveTeleportAck(ack);
                }
            }
            if (target->IsAlive())
            {
                targetState->NativeResurrectionPendingUntilMs = 0;
                targetState->NativeResurrectionCasterGuid.Clear();
                targetState->NativeResurrectionSpellId = 0;
            }
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target,
                "validation_route_resurrection");
            RecordEvent(state, bot, "validation_route_resurrection", target,
                target->IsAlive() ? "typed_native_resurrection_completed"
                    : "typed_native_resurrection_accept_pending",
                raw.c_str(), semantic.c_str(), bot->GetExactDist(target), 0,
                action.SpellId);
            return target->IsAlive()
                ? BotActionArbitration::Outcome::Committed(
                    "typed_combat_res_completed")
                : BotActionArbitration::Outcome::Started(
                    "typed_combat_res_accept_pending");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::CastSpell>)
        {
            Unit* target = action.Target.IsEmpty() ? bot : ObjectAccessor::GetUnit(*bot, action.Target);
            if (!target || !target->IsInWorld())
                return BotActionArbitration::Outcome::Retryable("native_cast_target_unavailable");
            SpellCastResult result = bot->CastSpell(target, action.SpellId, false);
            return result == SPELL_CAST_OK
                ? BotActionArbitration::Outcome::Submitted("native_cast_submitted")
                : BotActionArbitration::Outcome::Retryable("native_cast_rejected");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::SpellClick>
            || std::is_same_v<T, BotNativeAction::VehicleEnter>)
        {
            Creature* clickable = ObjectAccessor::GetCreatureOrPetOrVehicle(
                *bot, action.Target);
            if (!clickable || !clickable->IsInWorld()
                || !clickable->HasFlag(UNIT_NPC_FLAGS,
                    UNIT_NPC_FLAG_SPELLCLICK))
                return BotActionArbitration::Outcome::Unsafe(
                    "native_spellclick_target_invalid");
            if (!bot->IsWithinDistInMap(clickable, INTERACTION_DISTANCE))
                return BotActionArbitration::Outcome::Retryable(
                    "native_spellclick_out_of_range");
            WorldPacket click(CMSG_SPELLCLICK, sizeof(uint64));
            click << action.Target;
            bot->GetSession()->HandleSpellClick(click);
            return BotActionArbitration::Outcome::Submitted("native_spellclick_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::GameObjectUse>)
        {
            WorldPacket use(CMSG_GAMEOBJ_USE, sizeof(uint64));
            use << action.Target;
            bot->GetSession()->HandleGameObjectUseOpcode(use);
            return BotActionArbitration::Outcome::Submitted("native_gameobject_use_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::AreaTrigger>)
        {
            AreaTriggerEntry const* trigger =
                sAreaTriggerStore.LookupEntry(action.TriggerId);
            if (!trigger || trigger->ContinentID != bot->GetMapId())
                return BotActionArbitration::Outcome::Unsafe(
                    "native_area_trigger_invalid");
            if (!bot->IsInAreaTriggerRadius(trigger))
                return BotActionArbitration::Outcome::Retryable(
                    "native_area_trigger_out_of_radius");
            WorldPacket areaTrigger(CMSG_AREATRIGGER, sizeof(uint32));
            areaTrigger << action.TriggerId;
            bot->GetSession()->HandleAreaTriggerOpcode(areaTrigger);
            return BotActionArbitration::Outcome::Submitted(
                "native_area_trigger_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::GossipOpen>)
        {
            if (action.Target.IsCreatureOrVehicle())
            {
                WorldPackets::NPC::Hello hello(
                    WorldPacket(CMSG_GOSSIP_HELLO, sizeof(uint64)));
                hello.Unit = action.Target;
                bot->GetSession()->HandleGossipHelloOpcode(hello);
            }
            else if (action.Target.IsGameObject())
            {
                WorldPacket use(CMSG_GAMEOBJ_USE, sizeof(uint64));
                use << action.Target;
                bot->GetSession()->HandleGameObjectUseOpcode(use);
            }
            else
                return BotActionArbitration::Outcome::Unsafe(
                    "native_gossip_source_invalid");
            return BotActionArbitration::Outcome::Submitted(
                "native_gossip_open_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::GossipSelect>)
        {
            WorldPacket select(CMSG_GOSSIP_SELECT_OPTION, 24);
            select << action.Target << action.MenuId << action.OptionId;
            bot->GetSession()->HandleGossipSelectOptionOpcode(select);
            return BotActionArbitration::Outcome::Submitted("native_gossip_select_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::VehicleAction>)
        {
            Unit* target = action.Target.IsEmpty() ? bot : ObjectAccessor::GetUnit(*bot, action.Target);
            SpellCastResult result = bot->CastSpell(target ? target : bot, action.SpellId, false);
            return result == SPELL_CAST_OK
                ? BotActionArbitration::Outcome::Submitted("native_vehicle_action_submitted")
                : BotActionArbitration::Outcome::Retryable("native_vehicle_action_rejected");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::PetCommand>)
        {
            Unit* pet = ObjectAccessor::GetUnit(*bot, action.Pet);
            Unit* target = ObjectAccessor::GetUnit(*bot, action.Target);
            if (!pet || !target || pet->GetCharmerOrOwnerPlayerOrPlayerItself() != bot
                || !pet->GetCharmInfo())
                return BotActionArbitration::Outcome::Unsafe("native_pet_command_invalid");
            bot->GetSession()->HandlePetActionHelper(pet, pet->GetGUID(), action.Command,
                ACT_COMMAND, target->GetGUID(), target->GetPositionX(),
                target->GetPositionY(), target->GetPositionZ());
            return BotActionArbitration::Outcome::Submitted("native_pet_command_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::UseItem>)
        {
            // Follow the same request boundary as CMSG_USE_ITEM. In
            // particular, item-on-item casts such as rogue poisons and
            // self-target consumables must pass live inventory ownership, item
            // usability, the declared on-use spell, and the session's
            // pending-cast checks. This path never writes an aura, enchantment,
            // or item count itself.
            Item* item = bot->GetItemByGuid(action.Item);
            if (!item || !item->GetTemplate())
                return BotActionArbitration::Outcome::Retryable(
                    "native_use_item_unavailable");
            bool const selfTarget = action.Target.IsEmpty()
                || action.Target == bot->GetGUID();
            Item* itemTarget = action.Target.IsItem()
                ? bot->GetItemByGuid(action.Target) : nullptr;
            if (!selfTarget && (!itemTarget || !itemTarget->GetTemplate()))
                return BotActionArbitration::Outcome::Unsafe(
                    "native_use_item_target_must_be_owned_item_or_self");

            ItemTemplate const* itemTemplate = item->GetTemplate();
            ItemEffect const* selectedEffect = nullptr;
            for (ItemEffect const& effect : itemTemplate->Effects)
                if (effect.SpellID == int32(action.SpellId)
                    && effect.Trigger == ITEM_SPELLTRIGGER_ON_USE)
                {
                    selectedEffect = &effect;
                    break;
                }
            SpellInfo const* spellInfo = selectedEffect
                ? sSpellMgr->GetSpellInfo(action.SpellId) : nullptr;
            if (!spellInfo)
                return BotActionArbitration::Outcome::Unsafe(
                    "native_use_item_spell_contract_mismatch");
            if (bot->CanUseItem(item) != EQUIP_ERR_OK)
                return BotActionArbitration::Outcome::Retryable(
                    "native_use_item_not_usable");
            if (bot->IsInCombat() && !spellInfo->CanBeUsedInCombat())
                return BotActionArbitration::Outcome::Retryable(
                    "native_use_item_not_usable_in_combat");
            if (!bot->CanRequestSpellCast(spellInfo))
                return BotActionArbitration::Outcome::Retryable(
                    "native_use_item_cast_resources_pending");

            WorldPackets::Spells::UseItem request(
                WorldPacket(CMSG_USE_ITEM, 0));
            request.PackSlot = item->GetBagSlot();
            request.Slot = item->GetSlot();
            request.CastItem = item->GetGUID();
            request.Cast.SpellID = int32(action.SpellId);
            if (!selfTarget)
            {
                request.Cast.Target.Flags = TARGET_FLAG_ITEM;
                request.Cast.Target.Item = itemTarget->GetGUID();
            }
            bot->GetSession()->HandleUseItemOpcode(request);
            return BotActionArbitration::Outcome::Submitted(
                "native_use_item_session_request_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::ReleaseSpirit>)
        {
            WorldPacket repop(CMSG_REPOP_REQUEST, 1);
            repop << uint8(0);
            bot->GetSession()->HandleRepopRequestOpcode(repop);
            return BotActionArbitration::Outcome::Submitted("native_release_submitted");
        }
        else if constexpr (std::is_same_v<T, BotNativeAction::ReclaimCorpse>)
        {
            WorldPacket reclaim(CMSG_RECLAIM_CORPSE, sizeof(uint64));
            reclaim << action.Corpse;
            bot->GetSession()->HandleReclaimCorpseOpcode(reclaim);
            return BotActionArbitration::Outcome::Submitted("native_reclaim_submitted");
        }
        else
            return BotActionArbitration::Outcome::Unsafe("native_intent_not_implemented");
    }, intent);
}
