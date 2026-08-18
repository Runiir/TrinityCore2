#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotActionExecutor.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupReference.h"
#include "Map.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <initializer_list>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;
    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
}
}

BotWorldPopulationMgr::DungeonTrashActionResult BotWorldPopulationMgr::TryDungeonTrash(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity)
{
    DungeonTrashActionResult result;
    if (!Cohort().Config.AllowDungeons || !bot || !bot->GetMap() || !bot->GetMap()->IsNonRaidDungeon())
        return result;

    result.Handled = true;
    Player* anchor = FindDungeonAnchor(bot);
    char const* role = GetDungeonRole(bot);
    Unit* groupTarget = FindGroupCombatTarget(bot, anchor);
    if (std::string(role) == "tank" && bot->GetGroup())
    {
        Unit* endangeredTarget = nullptr;
        uint8 bestVictimPriority = 0;
        float bestDistance = std::numeric_limits<float>::max();
        for (GroupReference* itr = bot->GetGroup()->GetFirstMember(); itr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap() || member == bot)
                continue;
            std::string memberRole = GetDungeonRole(member);
            uint8 victimPriority = memberRole == "healer" ? 3 : 2;
            for (Unit* attacker : member->getAttackers())
            {
                if (!attacker || !attacker->IsAlive() || !bot->IsValidAttackTarget(attacker) || !bot->IsWithinLOSInMap(attacker))
                    continue;
                float distance = bot->GetExactDist(attacker);
                if (!endangeredTarget || victimPriority > bestVictimPriority
                    || (victimPriority == bestVictimPriority && distance < bestDistance))
                {
                    endangeredTarget = attacker;
                    bestVictimPriority = victimPriority;
                    bestDistance = distance;
                }
            }
        }
        if (endangeredTarget)
            groupTarget = endangeredTarget;
    }
    if (!groupTarget && !state.TargetGuid.IsEmpty())
        groupTarget = ObjectAccessor::GetUnit(*bot, state.TargetGuid);

    result.Pack = BuildDungeonTrashPackFeatures(bot, groupTarget);
    if (!groupTarget && !result.Pack.PriorityTargetGuid.IsEmpty())
        groupTarget = ObjectAccessor::GetUnit(*bot, result.Pack.PriorityTargetGuid);
    result.Target = groupTarget;

    if (anchor && !groupTarget && bot->GetExactDist(anchor) > 7.0f)
    {
        BotActionExecutor executor;
        executor.MoveFollow(anchor, bot);
        result.Action = "formation_follow";
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, result.Situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, "move_started", nullptr, "dungeon_formation", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), result.Pack.PackSize);
        return result;
    }

    if (!groupTarget)
    {
        result.Action = "wait_for_pull";
        return result;
    }

    if (TryValidationRouteReadiness(state, bot, groupTarget, power, stage, activity, result))
        return result;

    state.TargetGuid = groupTarget->GetGUID();

    uint32 interruptSpell = SelectInterruptSpell(bot);
    if (result.Pack.InterruptPriority >= 0.5f && interruptSpell && TryCastCombatSpell(bot, groupTarget, interruptSpell))
    {
        result.Action = "interrupt_priority_cast";
        result.SpellId = interruptSpell;
        std::string raw = BuildRawJson(bot, groupTarget);
        std::string semantic = BuildSemanticJson(bot, groupTarget, result.Situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, "interrupt_success", groupTarget, "ok", raw.c_str(), semantic.c_str(), result.Pack.InterruptPriority, result.Pack.PackSize, interruptSpell);
        return result;
    }

    if (std::string(role) == "healer")
    {
        Unit* healTarget = nullptr;
        if (Group* group = bot->GetGroup())
        {
            float lowestHp = 1.0f;
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap() || !bot->IsWithinLOSInMap(member))
                    continue;

                float hp = UnitHealthPct(member);
                if (!healTarget || hp < lowestHp)
                {
                    healTarget = member;
                    lowestHp = hp;
                }
            }
        }
        if (!healTarget)
            healTarget = bot;

        uint32 healSpell = SelectHealSpell(bot, healTarget);
        if (healSpell && UnitHealthPct(healTarget) < 0.75f && TryCastFriendlySpell(bot, healTarget, healSpell))
        {
            result.Action = "heal_lowest_ally";
            result.SpellId = healSpell;
            result.Target = healTarget;
            std::string raw = BuildRawJson(bot, groupTarget);
            std::string semantic = BuildSemanticJson(bot, groupTarget, result.Situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, "trash_heal", groupTarget, "ok", raw.c_str(), semantic.c_str(), UnitHealthPct(healTarget), result.Pack.PackSize, healSpell);
            return result;
        }

        if (anchor && bot->GetExactDist(anchor) > 18.0f)
        {
            BotActionExecutor executor;
            executor.MoveFollow(anchor, bot);
            result.Action = "healer_follow_tank";
            return result;
        }
    }

    if (std::string(role) != "tank" && anchor && anchor->GetVictim() == nullptr && !bot->IsInCombat())
    {
        BotActionExecutor executor;
        executor.MoveFollow(anchor, bot);
        result.Action = "avoid_extra_pull";
        result.Target = nullptr;
        return result;
    }

    ResolvedCombatAction profileAction;
    BotActionResult actionResult = ExecuteProfileCombatAction(&state, bot, groupTarget, &profileAction);
    uint32 spellId = profileAction.SpellId;
    result.Action = std::string(role) == "tank" ? "tank_establish_threat" : (result.Pack.AoeValue >= 0.6f ? "dps_aoe_pack" : "dps_focus_target");
    result.SpellId = actionResult == BotActionResult::Ok ? spellId : 0;
    result.Failure = actionResult != BotActionResult::Ok;
    result.Rare = result.Pack.DangerousCasts > 0 || result.Pack.PullRisk >= 0.75f;

    std::string raw = BuildRawJson(bot, groupTarget);
    std::string semantic = BuildSemanticJson(bot, groupTarget, result.Situation.c_str(), &power, stage, activity);
    RecordEvent(state, bot, "trash_action", groupTarget, ToString(actionResult), raw.c_str(), semantic.c_str(), result.Pack.PullRisk, result.Pack.PackSize, result.SpellId);
    if (!state.WasInCombat)
        RecordEvent(state, bot, "combat_started", groupTarget, "dungeon_trash", raw.c_str(), semantic.c_str(), result.Pack.PullRisk, result.Pack.PackSize);
    state.WasInCombat = true;
    return result;
}

bool BotWorldPopulationMgr::TryValidationRouteReadiness(WorldBotState& state, Player* bot, Unit* pullTarget, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, DungeonTrashActionResult& result)
{
    if (!bot)
        return false;

    uint64 const nowMs = NowMs();
    bool hunterHasStoredPet = bot->GetPlayerPetDataCurrent() != nullptr;
    if (bot->getClass() == CLASS_HUNTER && !hunterHasStoredPet)
        for (uint8 slot = PET_SLOT_FIRST_ACTIVE_SLOT; slot <= PET_SLOT_LAST_ACTIVE_SLOT; ++slot)
            if (PlayerPetData const* stored = bot->GetPlayerPetDataBySlot(slot);
                stored && stored->Type == HUNTER_PET && stored->PetId && stored->CreatureId)
            {
                hunterHasStoredPet = true;
                break;
            }
    bool healerUnderSwarmPressure = false;
    if (bot->getClass() == CLASS_HUNTER)
        if (Group* group = bot->GetGroup())
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (member && member->IsAlive() && member->IsInWorld()
                    && std::string(GetDungeonRole(member)) == "healer"
                    && member->getAttackers().size() >= 3)
                {
                    healerUnderSwarmPressure = true;
                    break;
                }
            }
    bool hunterPetRecoveryDeferred = bot->getClass() == CLASS_HUNTER
        && hunterHasStoredPet && (!bot->GetPet() || !bot->GetPet()->IsAlive())
        && healerUnderSwarmPressure;
    if (hunterPetRecoveryDeferred)
    {
        // A pending Revive Pet occupied eight complete decisions during the
        // longest rerun71 healer-threat episode. Interrupt only that cast while
        // a real healer-owned swarm needs Misdirection; recovery becomes urgent
        // again as soon as the pressure clears.
        if (bot->FindCurrentSpellBySpellId(982))
            bot->InterruptNonMeleeSpells(false, 982);
        state.HunterPetRevivePendingUntilMs = 0;
        state.HunterPetReviveStartedMs = 0;
        state.ReadinessRetryUntilMs["hunter:revive_pet"] = nowMs + 1000;
        state.LastPetReadinessAction =
            "hunter_pet_revive_deferred_for_healer_swarm";
    }
    bool urgentHunterPetRecovery = bot->getClass() == CLASS_HUNTER
        && hunterHasStoredPet && (!bot->GetPet() || !bot->GetPet()->IsAlive())
        && !healerUnderSwarmPressure;
    if (bot->IsInCombat())
    {
        // A completed combat invalidates the old stability window. The next
        // pull must not start until persistent stances and buffs have been
        // verified again.
        state.GroupReadinessStableSinceMs = 0;
        if (!urgentHunterPetRecovery)
            return false;
    }
    bool groupStable = true;
    if (Group* group = bot->GetGroup())
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || !member->IsInWorld() || !member->IsAlive() || member->IsInCombat()
                || member->GetVictim() || !member->getAttackers().empty())
            {
                groupStable = false;
                break;
            }
        }
    if (!groupStable && !urgentHunterPetRecovery)
    {
        state.GroupReadinessStableSinceMs = 0;
        return false;
    }
    if (!state.GroupReadinessStableSinceMs)
    {
        state.GroupReadinessStableSinceMs = nowMs;
        if (!urgentHunterPetRecovery)
        {
            result.Action = "validation_route_readiness_wait";
            result.Target = bot;
            return true;
        }
    }
    if (!urgentHunterPetRecovery && nowMs - state.GroupReadinessStableSinceMs < 10000)
    {
        result.Action = "validation_route_readiness_wait";
        result.Target = bot;
        return true;
    }

    // Persistent combat setup is a pre-pull player action. In particular,
    // rogue poisons cannot be retrofitted after a native pull has entered
    // combat. Hold the ordinary readiness barrier until native item-use casts
    // and their later exact weapon-enchant observations have completed.
    if (TryEnsurePersistentCombatSetup(state, bot, pullTarget))
    {
        result.Action = "validation_route_readiness_persistent_setup";
        result.Target = bot;
        return true;
    }

    struct ActiveBuffRequirement
    {
        uint8 ClassId;
        char const* Role;
        uint32 SpellId;
        std::initializer_list<uint32> AuraIds;
        char const* Key;
        bool PartyWide;
    };

    // Keep this list to persistent Cataclysm setup only. Temporary combat
    // effects such as shaman totems are handled on combat entry.
    static ActiveBuffRequirement const requirements[] =
    {
        { CLASS_WARRIOR, nullptr, 6673, { 6673, 57330, 19740 }, "battle_shout_ready", true },
        { CLASS_WARRIOR, nullptr, 469, { 469 }, "commanding_shout_ready", true },
        { CLASS_PALADIN, "tank", 25780, { 25780 }, "righteous_fury_ready", false },
        { CLASS_PALADIN, "tank", 31801, { 31801 }, "seal_of_truth_ready", false },
        { CLASS_PALADIN, "tank", 465, { 465 }, "devotion_aura_ready", false },
        { CLASS_PALADIN, nullptr, 20217, { 20217, 79063 }, "blessing_of_kings_ready", true },
        { CLASS_HUNTER, nullptr, 13165, { 13165 }, "aspect_of_the_hawk_ready", false },
        { CLASS_PRIEST, nullptr, 21562, { 21562 }, "power_word_fortitude_ready", true },
        { CLASS_PRIEST, nullptr, 27683, { 27683 }, "shadow_protection_ready", true },
        { CLASS_DEATH_KNIGHT, nullptr, 57330, { 57330, 6673, 19740 }, "horn_of_winter_ready", true },
        { CLASS_MAGE, nullptr, 1459, { 1459, 79058 }, "arcane_brilliance_ready", true },
        { CLASS_DRUID, nullptr, 1126, { 1126, 20217 }, "mark_of_the_wild_ready", true },
    };

    auto hasAnyAura = [](Unit const* unit, std::initializer_list<uint32> auraIds) -> bool
    {
        if (!unit)
            return false;
        for (uint32 auraId : auraIds)
            if (auraId && unit->HasAura(auraId))
                return true;
        return false;
    };

    auto canAttempt = [&](std::string const& key) -> bool
    {
        auto itr = state.ReadinessRetryUntilMs.find(key);
        return itr == state.ReadinessRetryUntilMs.end() || itr->second <= nowMs;
    };

    auto deferAttempt = [&](std::string const& key, char const* blockedReason)
    {
        ++state.ReadinessAttemptCount[key];
        state.ReadinessRetryUntilMs[key] = nowMs + 15000;
        ObserveBotCandidateFailure(state, bot,
            "world.readiness." + key,
            blockedReason && *blockedReason ? blockedReason : "readiness_retryable",
            1000, 15000, 3, 15000);
    };

    auto targetLabel = [](Unit const* unit) -> std::string
    {
        if (!unit)
            return "none/0";
        std::ostringstream label;
        if (Player const* player = unit->ToPlayer())
            label << player->GetName() << "/";
        else
            label << unit->GetName() << "/";
        label << unit->GetGUID().GetCounter();
        return label.str();
    };

    auto buffFailureReason = [&](char const* readyReason, uint32 spellId, Unit const* target) -> std::string
    {
        std::ostringstream reason;
        reason << "buff_cast_failed:" << readyReason << ":spell=" << spellId << ":target=" << targetLabel(target);
        return reason.str();
    };

    auto castSelf = [&](uint32 spellId, std::initializer_list<uint32> auraIds, char const* readyReason, char const* blockedReason) -> bool
    {
        if (hasAnyAura(bot, auraIds))
        {
            state.ReadinessPartyCoverageSignature.erase(std::string("self:") + readyReason);
            TryResolveBotBlocker(state, bot, readyReason);
            return false;
        }
        std::string attemptKey = std::string("self:") + readyReason;
        if (!bot->HasSpell(spellId))
        {
            ObserveBotCandidateFailure(state, bot,
                "world.readiness." + attemptKey,
                blockedReason && *blockedReason ? blockedReason : "self_buff_missing",
                1000, 15000, 3, 15000);
            return true;
        }
        if (!canAttempt(attemptKey))
            return true;
        if (TryCastFriendlySpell(bot, bot, spellId))
        {
            result.Action = "validation_route_readiness_buff";
            result.SpellId = spellId;
            result.Target = bot;
            std::string raw = BuildRawJson(bot, pullTarget);
            std::string semantic = BuildSemanticJson(bot, pullTarget, "validation_route_readiness", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_readiness", bot, readyReason, raw.c_str(), semantic.c_str(), 0.0f, 0, spellId);
            // The aura itself is the source of truth. A short retry delay avoids
            // duplicate submissions while the cast is applied, but still lets
            // persistent tank stances and seals be restored after a route
            // transition or encounter removes them.
            state.ReadinessRetryUntilMs[attemptKey] = nowMs + 5000;
            return true;
        }
        std::string failedReason = buffFailureReason(readyReason, spellId, bot);
        deferAttempt(attemptKey, failedReason.c_str());
        return true;
    };

    auto castParty = [&](uint32 spellId, std::initializer_list<uint32> auraIds, char const* readyReason, char const* blockedReason) -> bool
    {
        std::string attemptKey = std::string("party:") + readyReason;
        if (state.ReadinessPartyCoverageSignature[attemptKey] == "cast_once")
        {
            TryResolveBotBlocker(state, bot, readyReason);
            return false;
        }
        if (!bot->HasSpell(spellId))
        {
            ObserveBotCandidateFailure(state, bot,
                "world.readiness." + attemptKey,
                blockedReason && *blockedReason ? blockedReason : "party_buff_missing",
                1000, 15000, 3, 15000);
            return true;
        }
        if (!canAttempt(attemptKey))
            return false;

        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
        float maxRange = spellInfo ? std::max(5.0f, spellInfo->GetMaxRange(false)) : 5.0f;
        std::ostringstream coverageSignature;
        std::vector<Player*> eligibleMembers;

        if (Group* group = bot->GetGroup())
        {
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap() || !bot->IsWithinDistInMap(member, maxRange))
                    continue;
                eligibleMembers.push_back(member);
                coverageSignature << member->GetGUID().GetCounter() << ":alive:range;";
            }

            std::string signature = coverageSignature.str();
            if (state.ReadinessPartyCoverageSignature[attemptKey] == signature)
            {
                TryResolveBotBlocker(state, bot, readyReason);
                return false;
            }

            for (Player* member : eligibleMembers)
            {
                if (hasAnyAura(member, auraIds))
                    continue;
                if (TryCastFriendlySpell(bot, member, spellId))
                {
                    result.Action = "validation_route_readiness_party_buff";
                    result.SpellId = spellId;
                    result.Target = member;
                    std::string raw = BuildRawJson(bot, pullTarget);
                    std::string semantic = BuildSemanticJson(bot, pullTarget, "validation_route_readiness", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_readiness", member, readyReason, raw.c_str(), semantic.c_str(), bot->GetExactDist(member), 0, spellId);
                    state.ReadinessPartyCoverageSignature[attemptKey] = "cast_once";
                    return true;
                }
                std::string failedReason = buffFailureReason(readyReason, spellId, member);
                state.ReadinessPartyCoverageSignature[attemptKey] = signature;
                std::string raw = BuildRawJson(bot, pullTarget);
                std::string semantic = BuildSemanticJson(bot, pullTarget, "validation_route_readiness", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_readiness", member, failedReason.c_str(), raw.c_str(), semantic.c_str(), bot->GetExactDist(member), 0, spellId);
                TryResolveBotBlocker(state, bot, readyReason);
                return false;
            }

            state.ReadinessPartyCoverageSignature[attemptKey] = signature;
        }
        else if (!hasAnyAura(bot, auraIds))
            return castSelf(spellId, auraIds, readyReason, blockedReason);

        TryResolveBotBlocker(state, bot, readyReason);
        return false;
    };

    std::string role = GetDungeonRole(bot);
    if (!urgentHunterPetRecovery)
        for (ActiveBuffRequirement const& requirement : requirements)
        {
            if (requirement.ClassId != bot->getClass())
                continue;
            if (requirement.Role && role != requirement.Role)
                continue;
            if (!bot->HasSpell(requirement.SpellId))
                continue;

            std::string missing = std::string(requirement.PartyWide ? "missing_party_buff:" : "missing_self_buff:") + requirement.Key;
            if (requirement.PartyWide)
            {
                if (castParty(requirement.SpellId, requirement.AuraIds, requirement.Key, missing.c_str()))
                    return true;
            }
            else
            {
                if (castSelf(requirement.SpellId, requirement.AuraIds, requirement.Key, missing.c_str()))
                    return true;
            }
        }

    switch (bot->getClass())
    {
        case CLASS_PALADIN:
            break;
        case CLASS_HUNTER:
            if (!bot->GetPet())
            {
                static uint32 const callPetSpells[] = { 883, 83242, 83243, 83244, 83245 };
                PlayerPetData const* petData = bot->GetPlayerPetDataCurrent();
                uint8 petSlot = PET_SLOT_FIRST_ACTIVE_SLOT;
                if (!petData)
                    for (uint8 slot = PET_SLOT_FIRST_ACTIVE_SLOT; slot <= PET_SLOT_LAST_ACTIVE_SLOT; ++slot)
                        if (PlayerPetData const* stored = bot->GetPlayerPetDataBySlot(slot); stored && stored->Type == HUNTER_PET && stored->PetId && stored->CreatureId)
                        {
                            petData = stored;
                            petSlot = slot;
                            break;
                        }
                else
                    petSlot = petData->Slot;

                if (petData && petSlot <= PET_SLOT_LAST_ACTIVE_SLOT)
                {
                    state.LastPetReadinessPetId = petData->PetId;
                    state.LastPetReadinessPetEntry = petData->CreatureId;
                    std::string attemptKey = "hunter:call_pet:" + std::to_string(petSlot);
                    uint32 callPetSpell = callPetSpells[petSlot - PET_SLOT_FIRST_ACTIVE_SLOT];
                    if (!canAttempt(attemptKey))
                        return true;
                    std::string castFailureReason;
                    if (bot->HasSpell(callPetSpell) && TryCastFriendlySpell(bot, bot, callPetSpell, &castFailureReason))
                    {
                        result.Action = "validation_route_readiness_call_pet";
                        result.SpellId = callPetSpell;
                        result.Target = bot;
                        state.LastPetReadinessAction = attemptKey;
                        state.ReadinessRetryUntilMs[attemptKey] = nowMs + 3000;
                        RecordEvent(state, bot, "validation_route_readiness", bot, attemptKey.c_str(), "{}", "{}", 0.0f, petData->CreatureId, callPetSpell);
                        return true;
                    }
                    std::ostringstream failedReason;
                    failedReason << "hunter_pet_call_failed:" << petData->PetId << ":entry=" << petData->CreatureId << ":slot=" << uint32(petSlot) << ":spell=" << callPetSpell << ":reason=" << (castFailureReason.empty() ? "spell_unknown" : castFailureReason);
                    state.LastPetReadinessAction = failedReason.str();
                    deferAttempt(attemptKey, state.LastPetReadinessAction.c_str());
                    return true;
                }

                state.LastPetReadinessAction = "hunter_pet_missing";
                ObserveBotCandidateFailure(state, bot,
                    "world.readiness.hunter_pet_missing",
                    state.LastPetReadinessAction, 1000, 15000, 3, 15000);
                return true;
            }
            state.LastPetReadinessPetEntry = bot->GetPet()->GetEntry();
            if (!bot->GetPet()->IsAlive())
            {
                std::string attemptKey = "hunter:revive_pet";
                if (state.HunterPetRevivePendingUntilMs > nowMs)
                {
                    bot->StopMoving();
                    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                    bot->GetMotionMaster()->MoveIdle();
                    result.Action = bot->FindCurrentSpellBySpellId(982)
                        ? "validation_route_readiness_revive_pet_casting"
                        : "validation_route_readiness_revive_pet_verifying";
                    result.SpellId = 982;
                    result.Target = bot;
                    return true;
                }
                if (state.HunterPetRevivePendingUntilMs)
                {
                    state.HunterPetRevivePendingUntilMs = 0;
                    state.ReadinessRetryUntilMs[attemptKey] = nowMs + 1000;
                    state.LastPetReadinessAction = "hunter_pet_revive_not_observed";
                    RecordEvent(state, bot, "validation_route_readiness", bot, state.LastPetReadinessAction.c_str(),
                        "{}", "{}", float(state.HunterPetReviveAttemptCount), state.LastPetReadinessPetEntry, 982);
                }
                std::string castFailureReason;
                if (bot->HasSpell(982) && canAttempt(attemptKey) && TryCastFriendlySpell(bot, bot, 982, &castFailureReason))
                {
                    SpellInfo const* reviveInfo = sSpellMgr->GetSpellInfo(982);
                    uint64 castTimeMs = reviveInfo ? uint64(std::max<int32>(0, reviveInfo->CalcCastTime(bot->getLevel()))) : 0;
                    state.HunterPetReviveStartedMs = nowMs;
                    state.HunterPetRevivePendingUntilMs = nowMs + std::max<uint64>(5000, castTimeMs + 3000);
                    ++state.HunterPetReviveAttemptCount;
                    state.ReadinessRetryUntilMs[attemptKey] = state.HunterPetRevivePendingUntilMs;
                    state.LastPetReadinessAction = "hunter_pet_revive_submitted";
                    result.Action = "validation_route_readiness_revive_pet";
                    result.SpellId = 982;
                    result.Target = bot;
                    RecordEvent(state, bot, "validation_route_readiness", bot, state.LastPetReadinessAction.c_str(),
                        "{}", "{}", float(castTimeMs), state.LastPetReadinessPetEntry, 982);
                    return true;
                }
                state.LastPetReadinessAction = "hunter_pet_revive_failed:" + (castFailureReason.empty() ? std::string("spell_unknown") : castFailureReason);
                state.ReadinessRetryUntilMs[attemptKey] = nowMs + 3000;
                ObserveBotCandidateFailure(state, bot,
                    "world.readiness.hunter_pet_dead",
                    state.LastPetReadinessAction, 500, 5000, 3, 5000);
                return true;
            }
            if (state.HunterPetReviveStartedMs)
            {
                uint64 reviveLatencyMs = nowMs - state.HunterPetReviveStartedMs;
                state.LastPetReadinessAction = "hunter_pet_revived";
                RecordEvent(state, bot, "validation_route_readiness", bot, state.LastPetReadinessAction.c_str(),
                    "{}", "{}", float(reviveLatencyMs), state.LastPetReadinessPetEntry, 982);
                state.HunterPetRevivePendingUntilMs = 0;
                state.HunterPetReviveStartedMs = 0;
                state.ReadinessRetryUntilMs.erase("hunter:revive_pet");
            }
            TryResolveBotBlocker(state, bot, "hunter_pet_ready");
            if (Player* tank = FindDungeonAnchor(bot))
                if (tank != bot && bot->HasSpell(34477) && !bot->HasAura(34477) && TryCastFriendlySpell(bot, tank, 34477))
                {
                    result.Action = "validation_route_readiness_misdirection";
                    result.SpellId = 34477;
                    result.Target = tank;
                    return true;
                }
            if (pullTarget && bot->HasSpell(1130) && !pullTarget->HasAura(1130) && bot->IsValidAttackTarget(pullTarget))
                if (TryCastCombatSpell(bot, pullTarget, 1130))
                {
                    result.Action = "validation_route_readiness_hunters_mark";
                    result.SpellId = 1130;
                    result.Target = pullTarget;
                    return true;
                }
            break;
        default:
            break;
    }

    return false;
}
 #include "Bots/BotWorldPopulationMgr.h"

 #include "Bots/BotActionExecutor.h"
 #include "GameTime.h"
 #include "Group.h"
 #include "GroupReference.h"
 #include "Map.h"
 #include "ObjectAccessor.h"
 #include "Player.h"
 #include "Spell.h"
 #include "SpellInfo.h"
 #include "SpellMgr.h"
 #include "Unit.h"

 #include <algorithm>
 #include <chrono>
 #include <initializer_list>
 #include <limits>
 #include <sstream>
 #include <string>
 #include <vector>

 namespace
 {
 uint64 NowMs()
 {
     return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
         GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
 }

 float UnitHealthPct(Unit const* unit)
 {
     if (!unit || !unit->GetMaxHealth())
         return 0.0f;
     return float(unit->GetHealth()) / float(unit->GetMaxHealth());
 }
 }
