#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrBossMechanicsSupport.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "CellImpl.h"
#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "GroupReference.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "Totem.h"
#include "Unit.h"
#include "VehicleDefines.h"
#include "WorldPacket.h"

#include <algorithm>
#include <string>
#include <vector>

using BotWorldBossMechanics::IsNativeCombatObserved;
using BotWorldBossMechanics::NowMs;
using BotWorldBossMechanics::SpellHasHostileMultiTargetSemantics;
using BotWorldBossMechanics::UnitHealthPct;

BotWorldPopulationMgr::BossMechanicActionResult BotWorldPopulationMgr::TryBossMechanics(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, Unit* boundRouteTarget)
{
    BossMechanicActionResult result;
    if (!PrepareBossMechanicAction(state, bot, boundRouteTarget, result))
        return result;

    std::string raw = BuildRawJson(bot, result.Target);
    std::string semantic = BuildSemanticJson(bot, result.Target, result.Situation.c_str(), &power, stage, activity);
    char const* role = GetDungeonRole(bot);
    RaidRoleAssignment raidAssignment;
    RaidPositioningAnchors raidAnchors;
    RaidMechanicAdapter raidAdapter;
    RaidGearTargetPlan raidGearPlan;
    HeroicRaidProgression heroicProgression;
    if (result.Features.RaidEncounter)
    {
        raidAssignment = BuildRaidRoleAssignment(bot);
        raidAnchors = BuildRaidPositioningAnchors(bot, result.Target, raidAssignment, result.Features);
        raidAdapter = BuildRaidMechanicAdapter(bot, result.Target, raidAssignment, result.Features);
        raidGearPlan = BuildRaidGearTargetPlan(bot, power, stage);
        heroicProgression = BuildHeroicRaidProgression(state, bot, power, stage);
    }

    if (result.Features.RaidEncounter && !raidAdapter.ContractResolved)
    {
        ReconcileRaidAreaAutocasts(bot, true);
        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Mechanic,
            BotActionArbitration::Priority::Mechanic,
            "raid_contract_unresolved");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
                controlled->AttackStop();
        result.Action = "raid_mechanic_contract_fail_closed";
        result.Failure = true;
        RecordRaidTelemetry(state, bot, result.Target, "raid_mechanic_contract", raidAdapter.ContractError.empty()
                ? "unresolved" : raidAdapter.ContractError.c_str(), result.Features, raidAssignment, raidAnchors,
            raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str());
        return result;
    }

    if (result.Features.RaidEncounter && raidAdapter.ContractResolved)
    {
        // A controlled-AoE contract grants area authority only after the live
        // declared-target/contamination scan below.  Keep that authority closed
        // across every earlier mechanic return (BRez, dispel, cooldown, swap,
        // movement, and soak) instead of treating the contract's eventual
        // allow_area_damage policy as an immediate release.
        bool const suppressAreaDamage = !raidAdapter.AllowAreaDamage
            || raidAdapter.TargetControl == "controlled_aoe";
        ReconcileRaidAreaAutocasts(bot, suppressAreaDamage);
    }

    if (result.Features.RaidEncounter && raidAdapter.ContractResolved && raidAdapter.DispelAuraId)
    {
        bool const primaryOwner = raidAssignment.RoleIndex == raidAdapter.DispelOwnerSlot;
        bool primaryAvailable = false;
        if (raidAdapter.DispelOwnerSlot > 0)
            for (auto const& [guid, slot] : Cohort().Raid.RosterByGuid)
                if (slot.SlotIndex + 1 == raidAdapter.DispelOwnerSlot)
                    if (Player* owner = ObjectAccessor::FindPlayer(slot.Guid))
                        primaryAvailable = owner->IsAlive() && owner->IsInWorld();
        bool const backupOwner = !primaryAvailable && raidAssignment.RoleIndex == raidAdapter.DispelBackupSlot;
        if (primaryOwner || backupOwner)
            if (Group* group = bot->GetGroup())
                for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
                    if (Player* member = itr->GetSource(); member && member->HasAura(raidAdapter.DispelAuraId))
                    {
                        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role);
                        for (BotActionCandidate const& candidate : BotClassSpecActionProfileStore::BuildCandidates(bot, member, profile))
                            if (candidate.Category == BotCombatActionCategory::DispelCleanse
                                && candidate.RejectReason.empty() && TryCastFriendlySpell(bot, member, candidate.SpellId))
                            {
                                result.Target = member;
                                result.SpellId = candidate.SpellId;
                                result.Action = backupOwner ? "raid_dispel_backup" : "raid_dispel_owner";
                                RecordRaidTelemetry(state, bot, member, "raid_dispel_rotation", result.Action.c_str(),
                                    result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                                    raw.c_str(), semantic.c_str(), 0.0f, raidAdapter.DispelAuraId, candidate.SpellId);
                                return result;
                            }
                    }
    }

    if (result.Features.RaidEncounter && raidAdapter.ContractResolved
        && !raidAdapter.CooldownCategory.empty()
        && result.Features.CastSpellId == raidAdapter.CooldownTriggerSpellId)
    {
        bool primaryCooldownAvailable = false;
        for (auto const& [guid, slot] : Cohort().Raid.RosterByGuid)
            if (slot.SlotIndex + 1 == raidAdapter.CooldownOwnerSlot)
                if (Player* owner = ObjectAccessor::FindPlayer(slot.Guid))
                    primaryCooldownAvailable = owner->IsAlive() && owner->IsInWorld()
                        && owner->GetMap() == bot->GetMap();
        bool const cooldownOwner = raidAssignment.RoleIndex == raidAdapter.CooldownOwnerSlot
            || (!primaryCooldownAvailable && raidAssignment.RoleIndex == raidAdapter.CooldownBackupSlot);
        if (!cooldownOwner)
            goto raid_cooldown_complete;
        Unit* cooldownTarget = bot;
        if (Group* group = bot->GetGroup())
        {
            float lowest = 2.0f;
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                    continue;
                bool matches = raidAdapter.CooldownTarget == "lowest"
                    || (raidAdapter.CooldownTarget == "tank" && GetDungeonRole(member) == std::string("tank"))
                    || (raidAdapter.CooldownTarget == "subgroup"
                        && group->GetMemberGroup(member->GetGUID()) == raidAssignment.SubGroup);
                if (matches && UnitHealthPct(member) < lowest)
                {
                    lowest = UnitHealthPct(member);
                    cooldownTarget = member;
                }
            }
        }
        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role);
        for (BotActionCandidate const& candidate : BotClassSpecActionProfileStore::BuildCandidates(bot, cooldownTarget, profile))
        {
            bool const categoryMatches = (raidAdapter.CooldownCategory == "defensive"
                    && candidate.Category == BotCombatActionCategory::Defensive)
                || (raidAdapter.CooldownCategory == "external_defensive"
                    && candidate.Category == BotCombatActionCategory::ExternalDefensive)
                || (raidAdapter.CooldownCategory == "heal_aoe"
                    && candidate.Category == BotCombatActionCategory::HealAoe)
                || (raidAdapter.CooldownCategory == "offensive"
                    && candidate.Category == BotCombatActionCategory::OffensiveCooldown);
            if (categoryMatches && candidate.RejectReason.empty()
                && TryCastFriendlySpell(bot, cooldownTarget, candidate.SpellId))
            {
                result.Target = cooldownTarget;
                result.SpellId = candidate.SpellId;
                result.Action = raidAssignment.RoleIndex == raidAdapter.CooldownOwnerSlot
                    ? "raid_cooldown_schedule" : "raid_cooldown_backup";
                RecordRaidTelemetry(state, bot, cooldownTarget, "raid_cooldown_schedule", result.Action.c_str(),
                    result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                    raw.c_str(), semantic.c_str(), UnitHealthPct(cooldownTarget), raidAdapter.CooldownTriggerSpellId,
                    candidate.SpellId);
                return result;
            }
        }
    }
raid_cooldown_complete:

    auto closeRecallableAreaDamage = [this, bot]() -> bool
    {
        if (!bot)
            return false;
        ReconcileRaidAreaAutocasts(bot, true);
        for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
            if (Spell* current = bot->GetCurrentSpell(spellType))
                if (SpellHasHostileMultiTargetSemantics(current->GetSpellInfo()))
                    bot->InterruptSpell(spellType, false);
        if (bot->HasAura(48505))
        {
            WorldPacket cancel(CMSG_CANCEL_AURA, sizeof(uint32));
            cancel << uint32(48505);
            bot->GetSession()->HandleCancelAuraOpcode(cancel);
        }
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
            {
                if (Spell* current = controlled->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                    if (SpellHasHostileMultiTargetSemantics(current->GetSpellInfo()))
                        controlled->InterruptSpell(CURRENT_GENERIC_SPELL, false);
                if (Spell* channel = controlled->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                    if (SpellHasHostileMultiTargetSemantics(channel->GetSpellInfo()))
                        controlled->InterruptSpell(CURRENT_CHANNELED_SPELL, false);
            }

        BotClassSpecActionProfile const profile = BotClassSpecActionProfileStore::Build(bot, GetDungeonRole(bot));
        for (BotActionProfileSpell const& action : profile.Spells)
            if (SpellHasHostileMultiTargetSemantics(sSpellMgr->GetSpellInfo(action.SpellId)))
                bot->RemoveDynObject(action.SpellId);
        return true;
    };

    if (result.Features.RaidEncounter && raidAdapter.ContractResolved
        && raidAdapter.TargetControl == "do_not_damage" && std::string(role) != "healer"
        && result.Target && std::find(raidAdapter.TargetEntries.begin(), raidAdapter.TargetEntries.end(),
            result.Target->GetEntry()) != raidAdapter.TargetEntries.end()
        && (!raidAnchors.Active || bot->GetExactDist2d(raidAnchors.ResolvedX, raidAnchors.ResolvedY)
            <= raidAnchors.ArrivalToleranceYards))
    {
        if (!closeRecallableAreaDamage())
        {
            result.Action = "raid_area_damage_contamination_fail_closed";
            result.Failure = true;
            return result;
        }
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "raid_area_contamination_fail_closed");
        if (Spell* current = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            if (Unit* castTarget = current->m_targets.GetUnitTarget();
                castTarget && bot->IsValidAttackTarget(castTarget))
                bot->InterruptSpell(CURRENT_GENERIC_SPELL, false);
        if (bot->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
            bot->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
                controlled->AttackStop();
        result.Action = "raid_do_not_damage_hold";
        result.Rare = true;
        RecordRaidTelemetry(state, bot, result.Target, "raid_target_control", "native_damage_held",
            result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
            raw.c_str(), semantic.c_str(), 0.0f, result.Features.CastSpellId);
        return result;
    }

    if (result.Features.RaidEncounter && raidAdapter.ContractResolved
        && raidAdapter.TargetControl == "focus_fire" && std::string(role) != "healer")
    {
        if (!closeRecallableAreaDamage())
        {
            result.Action = "raid_area_damage_contamination_fail_closed";
            result.Failure = true;
            return result;
        }
        Unit* focus = nullptr;
        size_t focusPriority = raidAdapter.TargetEntries.size();
        std::vector<WorldObject*> focusObjects;
        Trinity::AllWorldObjectsInRange focusCheck(bot, 60.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> focusSearcher(bot, focusObjects, focusCheck);
        Cell::VisitAllObjects(bot, focusSearcher, 60.0f);
        for (WorldObject* object : focusObjects)
            if (Creature* candidate = object ? object->ToCreature() : nullptr;
                candidate && candidate->IsAlive() && bot->IsValidAttackTarget(candidate))
            {
                auto entry = std::find(raidAdapter.TargetEntries.begin(), raidAdapter.TargetEntries.end(), candidate->GetEntry());
                if (entry == raidAdapter.TargetEntries.end())
                    continue;
                size_t const priority = size_t(std::distance(raidAdapter.TargetEntries.begin(), entry));
                if (!focus || priority < focusPriority
                    || (priority == focusPriority
                        && candidate->GetGUID().GetRawValue() < focus->GetGUID().GetRawValue()))
                {
                    focus = candidate;
                    focusPriority = priority;
                }
            }
        auto interruptWrongFocusCasts = [focus](Unit* attacker)
        {
            if (!attacker)
                return;
            if (Spell* current = attacker->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                if (!focus || current->m_targets.GetUnitTarget() != focus)
                    attacker->InterruptSpell(CURRENT_GENERIC_SPELL, false);
            if (Spell* repeat = attacker->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
                if (!focus || repeat->m_targets.GetUnitTarget() != focus)
                    attacker->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);
            if (attacker->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                attacker->InterruptSpell(CURRENT_CHANNELED_SPELL, false);
        };
        auto stopWrongControlledFocusTarget = [focus, &interruptWrongFocusCasts](Unit* attacker)
        {
            if (!attacker)
                return;
            if (!focus || (attacker->GetVictim() && attacker->GetVictim() != focus))
                attacker->AttackStop();
            interruptWrongFocusCasts(attacker);
        };
        auto stopWrongPlayerFocusTarget = [&]()
        {
            if (!focus || (bot->GetVictim() && bot->GetVictim() != focus))
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Mechanic,
                    BotActionArbitration::Priority::Mechanic,
                    "raid_focus_target_transition");
            interruptWrongFocusCasts(bot);
        };
        if (!focus)
        {
            for (WorldObject* object : focusObjects)
                if (Unit* candidate = object ? object->ToUnit() : nullptr;
                    candidate && candidate->HasAura(44457, bot->GetGUID()))
                    candidate->RemoveAura(44457, bot->GetGUID());
            if (Creature* fireTotem = bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE] && bot->GetMap()
                    ? bot->GetMap()->GetCreature(bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE]) : nullptr)
                if (fireTotem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == 8190)
                    if (Totem* magma = fireTotem->ToTotem())
                        magma->UnSummon();
            stopWrongPlayerFocusTarget();
            if (Pet* pet = bot->GetPet())
                stopWrongControlledFocusTarget(pet);
            for (Unit* controlled : bot->m_Controlled)
                stopWrongControlledFocusTarget(controlled);
            result.Action = "raid_focus_fire_target_missing";
            result.Failure = true;
            return result;
        }
        for (WorldObject* object : focusObjects)
            if (Unit* candidate = object ? object->ToUnit() : nullptr;
                candidate && candidate != focus && candidate->HasAura(44457, bot->GetGUID()))
                candidate->RemoveAura(44457, bot->GetGUID());
        if (Creature* fireTotem = bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE] && bot->GetMap()
                ? bot->GetMap()->GetCreature(bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE]) : nullptr)
            if (fireTotem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == 8190)
                if (Totem* magma = fireTotem->ToTotem())
                    magma->UnSummon();
        stopWrongPlayerFocusTarget();
        if (Pet* pet = bot->GetPet())
            stopWrongControlledFocusTarget(pet);
        for (Unit* controlled : bot->m_Controlled)
            stopWrongControlledFocusTarget(controlled);
        result.Target = focus;
        state.TargetGuid = focus->GetGUID();
        RecordRaidTelemetry(state, bot, focus, "raid_focus_fire", "declared_target_selected",
            result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
            raw.c_str(), semantic.c_str(), float(focusPriority), focus->GetEntry());
    }

    if (result.Features.RaidEncounter && raidAdapter.ContractResolved)
    {
        bool const declaredDestinationMap = raidAdapter.PlatformDestinationMapId > 0;
        bool const declaredDestinationArea = raidAdapter.PlatformDestinationAreaId > 0;
        bool const declaredDestinationZ = raidAdapter.PlatformMaximumZ > raidAdapter.PlatformMinimumZ;
        bool const destinationZMatches = declaredDestinationZ
            && bot->GetPositionZ() >= raidAdapter.PlatformMinimumZ
            && bot->GetPositionZ() <= raidAdapter.PlatformMaximumZ;
        bool const platformPostcondition = (!declaredDestinationMap
                || bot->GetMapId() == raidAdapter.PlatformDestinationMapId)
            && (!declaredDestinationArea
                || bot->GetAreaId() == raidAdapter.PlatformDestinationAreaId)
            && (!declaredDestinationZ || destinationZMatches);
        bool const altitudePostcondition = raidAdapter.PlatformPolicy != "altitude"
            || destinationZMatches;
        bool const flyingPostcondition = raidAdapter.PlatformPolicy != "flying" || bot->IsFlying();
        bool const regroupPostcondition = raidAdapter.MovementLink == "regroup"
            && raidAnchors.Active
            && bot->GetExactDist2d(raidAnchors.ResolvedX, raidAnchors.ResolvedY)
                <= raidAnchors.ArrivalToleranceYards;
        bool const transferPostcondition = raidAdapter.MovementLink != "none"
            && raidAdapter.MovementLink != "regroup" && raidAdapter.PlatformPolicy != "ground"
            && platformPostcondition && altitudePostcondition && flyingPostcondition
            && (raidAdapter.InteractionKind != "jump_pad"
                || (state.LastRaidJumpPadEntrySubmitted == raidAdapter.JumpPadEntry
                    && state.LastRaidJumpPadRouteGeneration == Party().ValidationRouteGeneration));
        if (regroupPostcondition || transferPostcondition)
        {
            result.Action = raidAdapter.MovementLink == "regroup"
                ? "raid_platform_native_regroup_complete" : "raid_platform_native_transfer_complete";
            RecordRaidTelemetry(state, bot, result.Target, "raid_platform_transfer", "native_postcondition",
                result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                raw.c_str(), semantic.c_str(), bot->GetPositionZ(), bot->GetAreaId());
            return result;
        }
        if (raidAdapter.ExtraActionSpellId && bot->HasAura(raidAdapter.ExtraActionTriggerAuraId))
        {
            SpellCastResult const cast = bot->CastSpell(result.Target, raidAdapter.ExtraActionSpellId, false);
            result.Action = cast == SPELL_CAST_OK
                ? "raid_extra_action_native_cast" : "raid_extra_action_native_cast_rejected";
            result.SpellId = cast == SPELL_CAST_OK ? raidAdapter.ExtraActionSpellId : 0;
            result.Failure = cast != SPELL_CAST_OK;
            RecordRaidTelemetry(state, bot, result.Target, "raid_extra_action", result.Action.c_str(),
                result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                raw.c_str(), semantic.c_str(), 0.0f, raidAdapter.ExtraActionTriggerAuraId, raidAdapter.ExtraActionSpellId);
            return result;
        }
        std::vector<WorldObject*> contractObjects;
        Trinity::AllWorldObjectsInRange contractCheck(bot, 45.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> contractSearcher(bot, contractObjects, contractCheck);
        Cell::VisitAllObjects(bot, contractSearcher, 45.0f);
        for (WorldObject* object : contractObjects)
        {
            if (GameObject* gameObject = object ? object->ToGameObject() : nullptr)
            {
                if (raidAdapter.InteractableEntry && gameObject->GetEntry() == raidAdapter.InteractableEntry
                    && gameObject->IsAtInteractDistance(bot))
                {
                    GOState const before = gameObject->GetGoState();
                    WorldPacket use(CMSG_GAMEOBJ_USE, sizeof(uint64));
                    use << gameObject->GetGUID();
                    bot->GetSession()->HandleGameObjectUseOpcode(use);
                    result.Action = gameObject->GetGoState() != before
                        ? "raid_interactable_native_postcondition" : "raid_interactable_native_submitted";
                    RecordRaidTelemetry(state, bot, result.Target, "raid_interactable", result.Action.c_str(),
                        result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                        raw.c_str(), semantic.c_str(), 0.0f, gameObject->GetEntry());
                    return result;
                }
                if (raidAdapter.JumpPadEntry && gameObject->GetEntry() == raidAdapter.JumpPadEntry
                    && gameObject->IsAtInteractDistance(bot))
                {
                    WorldPacket use(CMSG_GAMEOBJ_USE, sizeof(uint64));
                    use << gameObject->GetGUID();
                    bot->GetSession()->HandleGameObjectUseOpcode(use);
                    state.LastRaidJumpPadEntrySubmitted = gameObject->GetEntry();
                    state.LastRaidJumpPadRouteGeneration = Party().ValidationRouteGeneration;
                    result.Action = "raid_jump_pad_native_submitted";
                    return result;
                }
                if (raidAdapter.TransportEntry && gameObject->GetEntry() == raidAdapter.TransportEntry)
                {
                    if (TransportBase* transport = bot->GetTransport();
                        transport && transport->GetTransportGUID() == gameObject->GetGUID())
                    {
                        result.Action = "raid_transport_native_boarded";
                        RecordRaidTelemetry(state, bot, result.Target, "raid_transport", "native_postcondition",
                            result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                            raw.c_str(), semantic.c_str(), 0.0f, gameObject->GetEntry());
                        return result;
                    }
                    MoveBotToPoint(state, bot, gameObject->GetPositionX(), gameObject->GetPositionY(), gameObject->GetPositionZ());
                    result.Action = "raid_transport_native_boarding_path";
                    return result;
                }
            }
            if (Creature* creature = object ? object->ToCreature() : nullptr)
                if (raidAdapter.VehicleEntry && creature->GetEntry() == raidAdapter.VehicleEntry)
                {
                    if (bot->GetVehicleBase() == creature)
                    {
                        result.Action = "raid_vehicle_native_entered";
                        return result;
                    }
                    if (bot->GetExactDist(creature) <= INTERACTION_DISTANCE)
                    {
                        WorldPacket click(CMSG_SPELLCLICK, sizeof(uint64));
                        click << creature->GetGUID();
                        bot->GetSession()->HandleSpellClick(click);
                        result.Action = "raid_vehicle_native_spellclick_submitted";
                        return result;
                    }
                    MoveBotToPoint(state, bot, creature->GetPositionX(), creature->GetPositionY(), creature->GetPositionZ());
                    result.Action = "raid_vehicle_native_boarding_path";
                    return result;
                }
        }
        if (raidAdapter.TransferAreaTriggerId)
            if (AreaTriggerEntry const* trigger = sAreaTriggerStore.LookupEntry(raidAdapter.TransferAreaTriggerId))
            {
                if (!bot->IsInAreaTriggerRadius(trigger))
                    MoveBotToPoint(state, bot, trigger->Pos.X, trigger->Pos.Y, trigger->Pos.Z);
                else
                {
                    WorldPacket areaTrigger(CMSG_AREATRIGGER, sizeof(uint32));
                    areaTrigger << raidAdapter.TransferAreaTriggerId;
                    bot->GetSession()->HandleAreaTriggerOpcode(areaTrigger);
                    if (raidAdapter.InteractionKind == "jump_pad")
                    {
                        state.LastRaidJumpPadEntrySubmitted = raidAdapter.JumpPadEntry;
                        state.LastRaidJumpPadRouteGeneration = Party().ValidationRouteGeneration;
                    }
                }
                result.Action = "raid_platform_native_transfer_pending_postcondition";
                return result;
            }
    }

    Unit* currentTank = result.Target->GetVictim();
    bool tankSwapConditionActive = false;
    bool tankSwapTimerTrigger = false;
    std::string tankSwapTriggerKey;
    if (result.Features.RaidEncounter && raidAdapter.ContractResolved && currentTank)
    {
        if (raidAdapter.TankSwapTrigger == "debuff_stacks")
            if (Aura const* aura = currentTank->GetAura(raidAdapter.TankSwapAuraId))
                if (aura->GetStackAmount() >= raidAdapter.TankSwapAuraStacks)
                {
                    tankSwapConditionActive = true;
                    tankSwapTriggerKey = "debuff:" + std::to_string(raidAdapter.TankSwapAuraId)
                        + ":" + std::to_string(currentTank->GetGUID().GetCounter());
                }
        if (raidAdapter.TankSwapTrigger == "timer")
            tankSwapTimerTrigger = state.LastRaidTankSwapMs
                && NowMs() >= state.LastRaidTankSwapMs + raidAdapter.TankSwapIntervalMs;
        if (raidAdapter.TankSwapTrigger == "boss_cast")
            if (result.Features.CastSpellId == raidAdapter.TankSwapTriggerSpellId)
            {
                tankSwapConditionActive = true;
                tankSwapTriggerKey = "cast:" + std::to_string(result.Features.CastSpellId);
            }
        if (raidAdapter.TankSwapTrigger == "add_spawn" && !result.Features.PriorityAddGuid.IsEmpty())
            if (Unit* add = ObjectAccessor::GetUnit(*bot, result.Features.PriorityAddGuid))
                if (add->GetEntry() == raidAdapter.TankSwapAddEntry)
                {
                    tankSwapConditionActive = true;
                    tankSwapTriggerKey = "add:" + std::to_string(add->GetGUID().GetCounter());
                }
        if (raidAdapter.TankSwapTrigger == "phase_transition")
            if (Cohort().Raid.EncounterPhase == raidAdapter.TankSwapPhase)
            {
                tankSwapConditionActive = true;
                tankSwapTriggerKey = "phase:" + raidAdapter.TankSwapPhase;
            }
    }
    if (!tankSwapConditionActive && raidAdapter.TankSwapTrigger != "timer")
        state.LastRaidTankSwapTriggerKey.clear();
    bool const tankSwapTriggered = tankSwapTimerTrigger
        || (tankSwapConditionActive && !tankSwapTriggerKey.empty()
            && state.LastRaidTankSwapTriggerKey != tankSwapTriggerKey);
    ObjectGuid nextTankGuid;
    if (currentTank)
    {
        if (currentTank->GetGUID() == raidAssignment.MainTankGuid)
            nextTankGuid = raidAssignment.OffTankGuid;
        else if (currentTank->GetGUID() == raidAssignment.OffTankGuid)
            nextTankGuid = raidAssignment.MainTankGuid;
    }
    if (tankSwapTriggered && std::string(role) == "tank"
        && !nextTankGuid.IsEmpty() && bot->GetGUID() == nextTankGuid && currentTank != bot)
    {
        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role);
        std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates(bot, result.Target, profile);
        for (BotActionCandidate const& candidate : candidates)
        {
            if (candidate.Category != BotCombatActionCategory::Taunt || !candidate.RejectReason.empty())
                continue;
            bool swapped = TryCastCombatSpell(bot, result.Target, candidate.SpellId);
            result.Action = swapped ? "raid_tank_swap_taunt" : "raid_tank_swap_taunt_failed";
            result.SpellId = swapped ? candidate.SpellId : 0;
            result.Failure = !swapped;
            result.Rare = true;
            if (swapped)
            {
                uint64 const swapAtMs = NowMs();
                for (WorldBotState& memberState : Party().Bots)
                    if (memberState.Guid == raidAssignment.MainTankGuid || memberState.Guid == raidAssignment.OffTankGuid)
                    {
                        memberState.LastRaidTankSwapTriggerSpellId = result.Features.CastSpellId;
                        memberState.LastRaidTankSwapTriggerKey = tankSwapTriggerKey;
                        memberState.LastRaidTankSwapWipeGeneration = Cohort().Raid.WipeGeneration;
                        memberState.LastRaidTankSwapMs = swapAtMs;
                    }
            }
            RecordRaidTelemetry(state, bot, result.Target, "raid_tank_swap", swapped ? "native_taunt" : "native_taunt_failed",
                result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.CastSpellId, candidate.SpellId);
            return result;
        }
    }

    if (result.Features.MoveOut && result.Features.DangerScore >= 0.25f)
    {
        Position pos = bot->GetFirstCollisionPosition(8.0f, result.Target->GetAngle(bot) + float(M_PI));
        MoveBotToPoint(state, bot, pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ());
        result.Action = "move_out_ground_danger";
        result.Rare = true;
        RecordEvent(state, bot, "boss_mechanic", result.Target, "move_out", raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.CastSpellId, result.Features.CastSpellId);
        if (result.Features.RaidEncounter)
            RecordRaidTelemetry(state, bot, result.Target, "raid_mechanic", "move_out", result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.CastSpellId, result.Features.CastSpellId);
        return result;
    }

    uint32 interruptSpell = SelectInterruptSpell(bot);
    bool primaryInterruptAvailable = false;
    if (raidAdapter.InterruptOwnerSlot)
        for (auto const& [guid, slot] : Cohort().Raid.RosterByGuid)
            if (slot.SlotIndex + 1 == raidAdapter.InterruptOwnerSlot)
                if (Player* owner = ObjectAccessor::FindPlayer(slot.Guid))
                {
                    uint32 const ownerSpell = SelectInterruptSpell(owner);
                    SpellInfo const* ownerSpellInfo = ownerSpell ? sSpellMgr->GetSpellInfo(ownerSpell) : nullptr;
                    primaryInterruptAvailable = owner->IsAlive() && owner->IsInWorld()
                        && owner->GetMap() == result.Target->GetMap() && owner->IsWithinLOSInMap(result.Target)
                        && ownerSpellInfo && !owner->HasUnitState(UNIT_STATE_CASTING)
                        && !owner->GetSpellHistory()->HasGlobalCooldown(ownerSpellInfo)
                        && owner->GetSpellHistory()->IsReady(ownerSpellInfo);
                }
    bool const interruptOwner = raidAssignment.RoleIndex == raidAdapter.InterruptOwnerSlot
        || (!primaryInterruptAvailable && raidAssignment.RoleIndex == raidAdapter.InterruptBackupSlot);
    bool const interruptTriggerMatches = raidAdapter.InterruptTriggerSpellId
        && result.Features.CastSpellId == raidAdapter.InterruptTriggerSpellId;
    if (result.Features.MustInterrupt && interruptTriggerMatches && interruptOwner && interruptSpell)
    {
        bool interrupted = TryCastCombatSpell(bot, result.Target, interruptSpell);
        result.Action = interrupted ? "interrupt_must_interrupt" : "interrupt_failed";
        result.SpellId = interruptSpell;
        result.Failure = !interrupted;
        result.Rare = true;
        RecordEvent(state, bot, interrupted ? "interrupt_success" : "interrupt_failed", result.Target, interrupted ? "ok" : "failed", raw.c_str(), semantic.c_str(), result.Features.InterruptPriority, result.Features.CastSpellId, interruptSpell);
        if (result.Features.RaidEncounter)
            RecordRaidTelemetry(state, bot, result.Target, "raid_interrupt", interrupted ? "ok" : "failed", result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), result.Features.InterruptPriority, result.Features.CastSpellId, interruptSpell);
        if (!interrupted)
            RecordBossReplay(state, bot, result.Target, result.Features, "boss_mechanic_failure", raw.c_str(), semantic.c_str(), "{\"action\":\"interrupt_must_interrupt\"}", "{\"reason\":\"must_interrupt_failed\"}");
        return result;
    }

    bool const soakActive = raidAdapter.SoakTriggerSpellId
        ? result.Features.CastSpellId == raidAdapter.SoakTriggerSpellId
        : (raidAdapter.SoakTriggerAuraId
            && (bot->HasAura(raidAdapter.SoakTriggerAuraId)
                || (result.Target && result.Target->HasAura(raidAdapter.SoakTriggerAuraId))));
    bool const assignedSoaker = std::find(raidAdapter.SoakRosterSlots.begin(),
        raidAdapter.SoakRosterSlots.end(), raidAssignment.RoleIndex) != raidAdapter.SoakRosterSlots.end();
    if (result.Features.RaidEncounter && soakActive && assignedSoaker)
    {
        uint32 const defensiveSpell = raidAdapter.SoakImmunitySpellId
            ? raidAdapter.SoakImmunitySpellId : raidAdapter.SoakPersonalCooldownSpellId;
        if (defensiveSpell && bot->HasSpell(defensiveSpell)
            && TryCastFriendlySpell(bot, bot, defensiveSpell))
        {
            result.Action = raidAdapter.SoakImmunitySpellId
                ? "raid_soak_immunity" : "raid_soak_personal_cooldown";
            result.SpellId = defensiveSpell;
            RecordRaidTelemetry(state, bot, bot, "raid_soak_defensive", result.Action.c_str(),
                result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                raw.c_str(), semantic.c_str(), 0.0f, result.Features.CastSpellId, defensiveSpell);
            return result;
        }
    }

    if (result.Features.RaidEncounter && raidAnchors.Active
        && bot->GetExactDist2d(raidAnchors.ResolvedX, raidAnchors.ResolvedY) > raidAnchors.ArrivalToleranceYards)
    {
        MoveBotToPoint(state, bot, raidAnchors.ResolvedX, raidAnchors.ResolvedY, raidAnchors.ResolvedZ);
        result.Action = "raid_" + raidAnchors.FormationFamily + "_anchor";
        result.Rare = result.Features.DangerScore >= 0.5f;
        RecordRaidTelemetry(state, bot, result.Target, "raid_position_anchor", result.Action.c_str(),
            result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
            raw.c_str(), semantic.c_str(), raidAnchors.DistanceToAnchor, result.Features.CastSpellId);
        return result;
    }

    if (result.Features.RaidEncounter && raidAdapter.ContractResolved
        && soakActive && assignedSoaker)
    {
        uint32 membersInSoak = 0;
        for (auto const& [guid, slot] : Cohort().Raid.RosterByGuid)
            if (std::find(raidAdapter.SoakRosterSlots.begin(), raidAdapter.SoakRosterSlots.end(), slot.SlotIndex + 1)
                    != raidAdapter.SoakRosterSlots.end())
                if (Player* member = ObjectAccessor::FindPlayer(slot.Guid))
                    if (member->IsAlive() && member->GetMap() == bot->GetMap()
                        && member->GetExactDist2d(raidAnchors.AnchorX, raidAnchors.AnchorY) <= raidAdapter.SoakRadiusYards)
                        ++membersInSoak;
        if (membersInSoak < raidAdapter.SoakMinimumCount)
        {
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Mechanic,
                BotActionArbitration::Priority::Mechanic,
                "raid_soak_wait_for_assigned_count");
            result.Action = "raid_soak_wait_for_assigned_count";
            RecordRaidTelemetry(state, bot, result.Target, "raid_soak", "assigned_count_pending",
                result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                raw.c_str(), semantic.c_str(), float(membersInSoak), raidAdapter.SoakMinimumCount);
            return result;
        }
        RecordRaidTelemetry(state, bot, result.Target, "raid_soak", "native_position_count_satisfied",
            result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
            raw.c_str(), semantic.c_str(), float(membersInSoak), raidAdapter.SoakMinimumCount);
    }

    if (result.Features.RaidEncounter && raidAdapter.ContractResolved
        && raidAdapter.TargetControl == "kill_sync")
    {
        std::vector<WorldObject*> nearby;
        Trinity::AllWorldObjectsInRange syncCheck(bot, 60.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> syncSearcher(bot, nearby, syncCheck);
        Cell::VisitAllObjects(bot, syncSearcher, 60.0f);
        Unit* highest = nullptr;
        float highestPct = -1.0f;
        float lowestPct = 2.0f;
        for (WorldObject* object : nearby)
            if (Creature* candidate = object ? object->ToCreature() : nullptr;
                candidate && candidate->IsAlive() && bot->IsValidAttackTarget(candidate)
                && std::find(raidAdapter.TargetEntries.begin(), raidAdapter.TargetEntries.end(), candidate->GetEntry())
                    != raidAdapter.TargetEntries.end())
            {
                float const pct = UnitHealthPct(candidate);
                lowestPct = std::min(lowestPct, pct);
                if (pct > highestPct)
                {
                    highestPct = pct;
                    highest = candidate;
                }
            }
        bool const peerAboveExecutionFloor = highestPct > raidAdapter.KillSyncExecutionFloorPct;
        if (highest && lowestPct <= raidAdapter.KillSyncExecutionFloorPct && peerAboveExecutionFloor)
        {
            auto isHeldLowTarget = [&](Unit const* target)
            {
                return target && target != highest
                    && std::find(raidAdapter.TargetEntries.begin(), raidAdapter.TargetEntries.end(), target->GetEntry())
                        != raidAdapter.TargetEntries.end()
                    && UnitHealthPct(target) <= raidAdapter.KillSyncExecutionFloorPct;
            };
            Unit* meleeLowTarget = isHeldLowTarget(bot->GetVictim()) ? bot->GetVictim() : nullptr;
            Unit* genericLowTarget = nullptr;
            if (Spell* current = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                if (isHeldLowTarget(current->m_targets.GetUnitTarget()))
                    genericLowTarget = current->m_targets.GetUnitTarget();
            Unit* repeatLowTarget = nullptr;
            if (Spell* repeat = bot->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
                if (isHeldLowTarget(repeat->m_targets.GetUnitTarget()))
                    repeatLowTarget = repeat->m_targets.GetUnitTarget();
            Pet* pet = bot->GetPet();
            bool const petDamagingLow = pet && isHeldLowTarget(pet->GetVictim());
            bool controlledDamagingLow = false;
            for (Unit* controlled : bot->m_Controlled)
                controlledDamagingLow = controlledDamagingLow
                    || (controlled && isHeldLowTarget(controlled->GetVictim()));
            bool const botDamagingLow = meleeLowTarget || genericLowTarget || repeatLowTarget
                || petDamagingLow || controlledDamagingLow;
            if (botDamagingLow)
            {
                if (meleeLowTarget)
                    SubmitMeleeAutoAttackIntent(state,
                        BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                        BotMeleeAutoAttack::Owner::Mechanic,
                        BotActionArbitration::Priority::Mechanic,
                        "raid_damage_stop_low_target");
                if (genericLowTarget)
                    bot->InterruptSpell(CURRENT_GENERIC_SPELL, false);
                if (repeatLowTarget)
                    bot->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);
                if (petDamagingLow)
                    pet->AttackStop();
                for (Unit* controlled : bot->m_Controlled)
                    if (controlled && isHeldLowTarget(controlled->GetVictim()))
                        controlled->AttackStop();
            }
            result.Target = highest;
            state.TargetGuid = highest->GetGUID();
            // Keep damage on the highest-health synchronized target while a
            // peer is at the declared execution floor.  The low target is
            // therefore held without globally stopping progress.
            result.Action = botDamagingLow ? "raid_kill_sync_execution_hold_low_target"
                : "raid_kill_sync_balance_high_target";
            RecordRaidTelemetry(state, bot, highest, "raid_kill_sync", result.Action.c_str(),
                result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression,
                raw.c_str(), semantic.c_str(), highestPct - lowestPct);
        }
        else if (highest && highestPct - lowestPct > raidAdapter.KillSyncTolerancePct)
        {
            result.Target = highest;
            state.TargetGuid = highest->GetGUID();
            result.Action = "raid_kill_sync_balance_high_target";
        }
    }

    Unit* controlledAoeTarget = nullptr;
    uint32 declaredControlledAoeTargets = 0;
    bool undeclaredControlledAoeHostile = false;
    if (raidAdapter.ContractResolved && raidAdapter.TargetControl == "controlled_aoe")
    {
        size_t controlledAoePriority = raidAdapter.TargetEntries.size();
        std::vector<WorldObject*> nearbyObjects;
        Trinity::AllWorldObjectsInRange nearbyCheck(bot, 45.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> nearbySearcher(bot, nearbyObjects, nearbyCheck);
        Cell::VisitAllObjects(bot, nearbySearcher, 45.0f);
        for (WorldObject* object : nearbyObjects)
        {
            Creature* candidate = object ? object->ToCreature() : nullptr;
            if (!candidate || !candidate->IsAlive()
                || !bot->IsValidAttackTarget(candidate) || !bot->IsWithinLOSInMap(candidate))
                continue;
            auto declared = std::find(raidAdapter.TargetEntries.begin(), raidAdapter.TargetEntries.end(),
                candidate->GetEntry());
            if (declared == raidAdapter.TargetEntries.end())
            {
                undeclaredControlledAoeHostile = true;
                if (candidate->HasAura(44457, bot->GetGUID()))
                    candidate->RemoveAura(44457, bot->GetGUID());
                continue;
            }
            ++declaredControlledAoeTargets;
            size_t const priority = size_t(std::distance(raidAdapter.TargetEntries.begin(), declared));
            if (!controlledAoeTarget || priority < controlledAoePriority
                || (priority == controlledAoePriority
                    && candidate->GetGUID().GetRawValue() < controlledAoeTarget->GetGUID().GetRawValue()))
            {
                controlledAoeTarget = candidate;
                controlledAoePriority = priority;
            }
        }
    }

    ObjectGuid const addTargetGuid = controlledAoeTarget
        ? controlledAoeTarget->GetGUID() : result.Features.PriorityAddGuid;
    bool const controlledAoeReleased = raidAdapter.ContractResolved
        && raidAdapter.TargetControl == "controlled_aoe"
        && !undeclaredControlledAoeHostile
        && declaredControlledAoeTargets >= raidAdapter.ControlledAoeMinimumTargets;
    if (raidAdapter.ContractResolved && raidAdapter.TargetControl == "controlled_aoe")
        ReconcileRaidAreaAutocasts(bot, !controlledAoeReleased);
    if (raidAdapter.ContractResolved && raidAdapter.TargetControl == "controlled_aoe"
        && !controlledAoeReleased)
    {
        if (!closeRecallableAreaDamage())
        {
            result.Action = "raid_area_damage_contamination_fail_closed";
            result.Failure = true;
            return result;
        }
        if (Creature* fireTotem = bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE] && bot->GetMap()
                ? bot->GetMap()->GetCreature(bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE]) : nullptr)
            if (fireTotem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == 8190)
                if (Totem* magma = fireTotem->ToTotem())
                    magma->UnSummon();
    }
    if (result.Features.AddsActive && !addTargetGuid.IsEmpty() && std::string(role) != "healer"
        && raidAdapter.TargetControl != "kill_sync" && raidAdapter.TargetControl != "focus_fire")
    {
        if (Unit* add = ObjectAccessor::GetUnit(*bot, addTargetGuid))
        {
            if (std::find(raidAdapter.TargetEntries.begin(), raidAdapter.TargetEntries.end(), add->GetEntry())
                == raidAdapter.TargetEntries.end())
            {
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Safety,
                    BotActionArbitration::Priority::Terminal,
                    "raid_target_not_declared_hold");
                result.Action = "raid_target_not_declared_hold";
                return result;
            }
            ResolvedCombatAction profileAction;
            if (!controlledAoeReleased)
            {
                if (!closeRecallableAreaDamage())
                {
                    result.Action = "raid_area_damage_contamination_fail_closed";
                    result.Failure = true;
                    return result;
                }
                if (Spell* current = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                    if (SpellInfo const* spellInfo = current->GetSpellInfo())
                    {
                        bool chainedDamage = false;
                        for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
                            if (spellInfo->Effects[effectIndex].IsEffect()
                                && spellInfo->Effects[effectIndex].ChainTarget > 1)
                            {
                                chainedDamage = true;
                                break;
                            }
                        if (spellInfo->IsAffectingArea() || chainedDamage)
                            bot->InterruptSpell(CURRENT_GENERIC_SPELL, false);
                    }
                bot->InterruptSpell(CURRENT_CHANNELED_SPELL, false);
                if (Creature* fireTotem = bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE] && bot->GetMap()
                        ? bot->GetMap()->GetCreature(bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE]) : nullptr)
                    if (fireTotem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == 8190)
                        if (Totem* magma = fireTotem->ToTotem())
                            magma->UnSummon();
            }
            bool const forbidArea = raidAdapter.ContractResolved
                && (!raidAdapter.AllowAreaDamage || (raidAdapter.TargetControl == "controlled_aoe" && !controlledAoeReleased));
            uint32 const combatAddCount = raidAdapter.TargetControl == "controlled_aoe"
                ? declaredControlledAoeTargets : result.Features.AddCount;
            BotActionResult actionResult = ExecuteProfileCombatAction(
                &state, bot, add, &profileAction, combatAddCount, controlledAoeReleased,
                0, controlledAoeReleased, false, forbidArea, raidAdapter.AllowMultidot);
            uint32 spellId = profileAction.SpellId;
            result.Target = add;
            result.Action = "switch_to_adds";
            result.SpellId = actionResult == BotActionResult::Ok ? spellId : 0;
            result.Failure = actionResult != BotActionResult::Ok;
            result.Rare = true;
            RecordEvent(state, bot, "boss_adds", add, ToString(actionResult), raw.c_str(), semantic.c_str(), float(combatAddCount), result.Features.CastSpellId, result.SpellId);
            if (result.Features.RaidEncounter)
                RecordRaidTelemetry(state, bot, add, "raid_add_wave", ToString(actionResult), result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), float(combatAddCount), result.Features.CastSpellId, result.SpellId);
            if (result.Failure)
                RecordBossReplay(state, bot, add, result.Features, "boss_mechanic_failure", raw.c_str(), semantic.c_str(), "{\"action\":\"switch_to_adds\"}", "{\"reason\":\"add_switch_failed\"}");
            return result;
        }
    }

    bool const assignedHealer = raidAdapter.HealerOwnerSlots.empty()
        || std::find(raidAdapter.HealerOwnerSlots.begin(), raidAdapter.HealerOwnerSlots.end(),
            raidAssignment.RoleIndex) != raidAdapter.HealerOwnerSlots.end();
    if (std::string(role) == "healer" && assignedHealer)
    {
        Unit* healTarget = nullptr;
        if (Group* group = bot->GetGroup())
        {
            float lowestHp = 2.0f;
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap() || !bot->IsWithinLOSInMap(member))
                    continue;
                bool const tank = GetDungeonRole(member) == std::string("tank");
                bool const sameSubgroup = group->GetMemberGroup(member->GetGUID()) == raidAssignment.SubGroup;
                bool const owned = raidAdapter.HealerOwnership == "raid_triage"
                    || (raidAdapter.HealerOwnership == "tank" && tank)
                    || (raidAdapter.HealerOwnership == "subgroup" && sameSubgroup)
                    || (raidAdapter.HealerOwnership == "tank_and_subgroup" && (tank || sameSubgroup));
                if (!owned)
                    continue;

                float hp = UnitHealthPct(member);
                if (hp < lowestHp)
                {
                    healTarget = member;
                    lowestHp = hp;
                }
            }
        }

        uint32 healSpell = healTarget ? SelectHealSpell(bot, healTarget) : 0;
        if (healSpell && UnitHealthPct(healTarget) < (result.Features.RaidDamage ? 0.9f : 0.75f) && TryCastFriendlySpell(bot, healTarget, healSpell))
        {
            result.Action = result.Features.RaidDamage ? "heal_raid_damage" : "heal_boss_damage";
            result.SpellId = healSpell;
            result.Target = healTarget;
            RecordEvent(state, bot, "boss_heal", result.Target, "ok", raw.c_str(), semantic.c_str(), UnitHealthPct(healTarget), result.Features.CastSpellId, healSpell);
            if (result.Features.RaidEncounter)
                RecordRaidTelemetry(state, bot, result.Target, "raid_healer_cooldown", "ok", result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), UnitHealthPct(healTarget), result.Features.CastSpellId, healSpell);
            return result;
        }
    }

    ResolvedCombatAction profileAction;
    bool const forbidArea = raidAdapter.ContractResolved
        && (!raidAdapter.AllowAreaDamage
            || (raidAdapter.TargetControl == "controlled_aoe" && !controlledAoeReleased));
    BotActionResult actionResult = ExecuteProfileCombatAction(
        &state, bot, result.Target, &profileAction, result.Features.AddCount, false,
        0, false, false, forbidArea, raidAdapter.AllowMultidot);
    uint32 spellId = profileAction.SpellId;
    bool const nativePositionReconciled = actionResult == BotActionResult::Casting
        && state.ActivePathTargetGuid == result.Target->GetGUID()
        && state.LastCombatAttempt.Phase == "position_reconcile";
    if (nativePositionReconciled)
        result.Action = "move_to_boss_action_range";
    else
        result.Action = std::string(role) == "tank"
            ? "tank_boss_position" : "boss_single_target";
    result.SpellId = actionResult == BotActionResult::Ok ? spellId : 0;
    result.Failure = actionResult == BotActionResult::NoOwner
        || actionResult == BotActionResult::NoBot
        || actionResult == BotActionResult::InvalidTarget
        || actionResult == BotActionResult::NotFriendly
        || actionResult == BotActionResult::DeadTarget
        || actionResult == BotActionResult::BadSpell
        || actionResult == BotActionResult::CastFailed;
    result.Rare = result.Features.DangerScore >= 0.5f || result.Features.BossCasting || result.Features.AddsActive;

    RecordEvent(state, bot, "boss_action", result.Target, ToString(actionResult), raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.CastSpellId, result.SpellId);
    if (result.Features.RaidEncounter)
        RecordRaidTelemetry(state, bot, result.Target, "raid_boss_action", ToString(actionResult), result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.CastSpellId, result.SpellId);
    bool const nativeCombatObserved = IsNativeCombatObserved(bot, result.Target);
    if (result.Features.RaidEncounter && !state.WasInCombat
        && nativeCombatObserved)
    {
        ++state.RaidAttempts;
        state.LastRaidTankSwapTriggerKey.clear();
        state.LastRaidTankSwapMs = NowMs();
    }
    if (!state.WasInCombat && nativeCombatObserved)
        RecordEvent(state, bot, "boss_started", result.Target, result.Situation.c_str(), raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.BossEntry);
    if (result.Failure || (result.Features.DangerScore >= 0.85f && result.Features.BossCasting))
        RecordBossReplay(state, bot, result.Target, result.Features, "boss_mechanic_failure", raw.c_str(), semantic.c_str(), "{\"action\":\"boss_single_target\"}", result.Failure ? "{\"reason\":\"boss_action_failed\"}" : "{\"reason\":\"high_danger_boss_state\"}");
    state.WasInCombat = nativeCombatObserved;
    return result;
}
