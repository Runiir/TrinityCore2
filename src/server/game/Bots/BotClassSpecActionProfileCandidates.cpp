#include "Bots/BotClassSpecActionProfile.h"
#include "Cryptography/CryptoHash.h"
#include "DataStores/DBCStores.h"
#include "DatabaseEnv.h"
#include "Bag.h"
#include "Item.h"
#include "Pet.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Util.h"
#include "Creature.h"
#include "Group.h"
#include "DataStores/DBCEnums.h"
#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>

#include "Bots/BotClassSpecActionProfileInternal.h"

namespace
{
constexpr uint32 ProfileDarkTransformationSpellId = 63560;

bool MaintainedAuraBlocksRefresh(Unit const* target, uint32 auraId, uint32 refreshBelowMs)
{
    Aura const* aura = target && auraId ? target->GetAura(auraId) : nullptr;
    if (!aura)
        return false;
    int32 durationMs = aura->GetDuration();
    return !refreshBelowMs || durationMs < 0 || uint32(durationMs) > refreshBelowMs;
}

bool HasMechanicTag(std::string const& tags, char const* required)
{
    size_t start = 0;
    while (start <= tags.size())
    {
        size_t end = tags.find(',', start);
        if (tags.compare(start, (end == std::string::npos ? tags.size() : end) - start, required) == 0)
            return true;
        if (end == std::string::npos)
            break;
        start = end + 1;
    }
    return false;
}

bool IsPostPeriodicTickInterruptWindow(Player const* bot, Unit const* target,
    uint32 channelSpellId, uint32 reactionWindowMs)
{
    if (!bot || !target || !channelSpellId)
        return false;

    AuraEffect const* channelEffect = target->GetAuraEffect(
        channelSpellId, EFFECT_0, bot->GetGUID());
    if (!channelEffect || !channelEffect->IsPeriodic()
        || !channelEffect->GetTickNumber() || channelEffect->GetPeriod() <= 0)
        return false;

    // AuraEffect::Update lands the periodic tick before the bot manager runs.
    // WoWSims evaluates interruptIf at that same boundary.  Keep the native
    // channel alive between boundaries, and expose only the short post-tick
    // window to the higher-priority action.
    return channelEffect->GetPeriodicTimer() <= int32(reactionWindowMs);
}

Item* FindOnUseItemForSpell(Player const* player, uint32 spellId)
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

bool HasEnoughPowerForProfileSpell(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    // Dark Transformation consumes the ghoul's Shadow Infusion stacks.  Its
    // SQL profile requires the owner-side ready aura before this resource check.
    if (spellInfo->Id == ProfileDarkTransformationSpellId)
        return true;

    if (spellInfo->PowerType == POWER_RUNE && spellInfo->RuneCostID && bot->getClass() == CLASS_DEATH_KNIGHT)
    {
        SpellRuneCostEntry const* runeCost = sSpellRuneCostStore.LookupEntry(spellInfo->RuneCostID);
        if (runeCost && !runeCost->NoRuneCost())
        {
            std::array<int32, 3> required = { int32(runeCost->RuneCost[0]), int32(runeCost->RuneCost[1]), int32(runeCost->RuneCost[2]) };
            // Native rune validation applies the player's current spell-cost
            // modifiers (for example a free-rune proc) before examining ready
            // runes.  Candidate preflight must observe the same player-visible
            // state or it can reject a cast that Spell::CheckRuneCost accepts.
            if (Player* modOwner = bot->GetSpellModOwner())
                for (int32& runeRequirement : required)
                    modOwner->ApplySpellMod(spellInfo, SpellModOp::PowerCost0, runeRequirement);
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

    int32 cost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (cost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > cost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(cost);
}

uint32 ProfileSpellCastTimeMs(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return 0;
    return uint32(std::max<int32>(0, spellInfo->CalcCastTime(bot->getLevel())));
}

float ProfileSpellMaximumRange(Player const* bot, Unit const* target,
    SpellInfo const* spellInfo)
{
    if (!bot || !target || !spellInfo)
        return 0.0f;

    float maximumRange = bot->GetSpellMaxRangeForTarget(target, spellInfo);
    if (spellInfo->RangeEntry
        && (spellInfo->RangeEntry->Flags & SPELL_RANGE_MELEE))
        return std::max(maximumRange, bot->GetMeleeRange(target));

    // Spell::GetMinMaxRange adds both units' combat reach for a hostile unit
    // target. Mirror that native envelope here so a legal edge-range spell is
    // not discarded before BotActionExecutor can ask the core to cast it.
    return maximumRange + bot->GetCombatReach() + target->GetCombatReach();
}

struct ReadyRuneObservation
{
    uint8 Total = 0;
    uint8 Blood = 0;
    uint8 Unholy = 0;
    uint8 Frost = 0;
    uint8 Death = 0;
};

ReadyRuneObservation ObserveReadyRunes(Player const* bot)
{
    ReadyRuneObservation observation;
    if (!bot || bot->getClass() != CLASS_DEATH_KNIGHT)
        return observation;
    for (uint8 rune = 0; rune < MAX_RUNES; ++rune)
        if (std::abs(bot->GetRuneCooldown(rune)) <= 0.0001f)
        {
            ++observation.Total;
            switch (bot->GetCurrentRune(rune))
            {
                case RuneType::Blood: ++observation.Blood; break;
                case RuneType::Unholy: ++observation.Unholy; break;
                case RuneType::Frost: ++observation.Frost; break;
                case RuneType::Death: ++observation.Death; break;
                default: break;
            }
        }
    return observation;
}

uint8 ReadyRuneCount(Player const* bot)
{
    return ObserveReadyRunes(bot).Total;
}

uint32 EquippedTemporaryEnchant(Player const* bot, uint8 slot)
{
    Item const* item = bot ? bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot) : nullptr;
    return item ? item->GetEnchantmentId(TEMP_ENCHANTMENT_SLOT) : 0;
}

std::string EvaluateCompiledConditions(Player const* bot, Unit const* target, Unit const* comboTarget, BotActionProfileSpell const& spell)
{
    if (!bot)
        return "missing_bot";
    Aura const* selfAura = spell.RequiredSelfAura ? bot->GetAura(spell.RequiredSelfAura) : nullptr;
    if (spell.RequiredSelfAura && !selfAura)
        return "missing_required_self_aura";
    if (spell.ForbiddenSelfAura && bot->HasAura(spell.ForbiddenSelfAura))
        return "forbidden_self_aura_active";
    if (spell.RequiredSelfAuraStacks && (!selfAura || selfAura->GetStackAmount() < spell.RequiredSelfAuraStacks))
        return "insufficient_self_aura_stacks";
    if (spell.MaxSelfAuraStacks && selfAura && selfAura->GetStackAmount() > spell.MaxSelfAuraStacks)
        return "self_aura_stacks_too_high";
    if (selfAura && (spell.MinSelfAuraRemainingMs || spell.MaxSelfAuraRemainingMs))
    {
        int32 remaining = selfAura->GetDuration();
        if (remaining >= 0 && spell.MinSelfAuraRemainingMs && uint32(remaining) < spell.MinSelfAuraRemainingMs)
            return "self_aura_duration_too_low";
        if ((remaining < 0 && spell.MaxSelfAuraRemainingMs)
            || (remaining >= 0 && spell.MaxSelfAuraRemainingMs && uint32(remaining) > spell.MaxSelfAuraRemainingMs))
            return "self_aura_duration_too_high";
    }
    if (spell.RequiredTargetAura && (!target || !target->HasAura(spell.RequiredTargetAura)))
        return "missing_required_target_aura";
    if (spell.ForbiddenTargetAura && target && target->HasAura(spell.ForbiddenTargetAura))
        return "forbidden_target_aura_active";
    Aura const* lacerate = target ? target->GetAura(33745, bot->GetGUID()) : nullptr;
    if (HasMechanicTag(spell.MechanicTags, "lacerate_spender")
        && (!lacerate || lacerate->GetStackAmount() < 3))
        return "insufficient_lacerate_stacks";
    if (HasMechanicTag(spell.MechanicTags, "lacerate")
        && !HasMechanicTag(spell.MechanicTags, "lacerate_spender")
        && lacerate && lacerate->GetStackAmount() >= 3 && lacerate->GetDuration() > 3000)
        return "lacerate_stacks_ready";
    if (spell.RequiredOwnedTargetAura && (!target || !target->HasAura(spell.RequiredOwnedTargetAura, bot->GetGUID())))
        return "missing_required_owned_target_aura";
    if (spell.ForbiddenOwnedTargetAura && target && target->HasAura(spell.ForbiddenOwnedTargetAura, bot->GetGUID()))
        return "forbidden_owned_target_aura_active";
    if (HasMechanicTag(spell.MechanicTags, "holy_power_3") && bot->GetPower(POWER_HOLY_POWER) < 3)
        return "insufficient_holy_power";
    if (HasMechanicTag(spell.MechanicTags, "soul_shard")
        && bot->GetPower(POWER_SOUL_SHARDS) < 1)
        return "insufficient_soul_shards";
    if (spell.MaintainAuraId && !spell.RequiredOwnedTargetAura
        && !spell.ForbiddenOwnedTargetAura)
    {
        if (HasMechanicTag(spell.MechanicTags, "maintain_owned_aura"))
        {
            Aura const* ownedAura = target
                ? target->GetAura(spell.MaintainAuraId, bot->GetGUID()) : nullptr;
            if (ownedAura)
            {
                int32 const remainingMs = ownedAura->GetDuration();
                if (!spell.RefreshAuraBelowMs || remainingMs < 0
                    || uint32(remainingMs) > spell.RefreshAuraBelowMs)
                    return "maintain_owned_aura_active";
            }
        }
        else if (MaintainedAuraBlocksRefresh(target, spell.MaintainAuraId,
                spell.RefreshAuraBelowMs))
            return "maintain_aura_active";
    }

    uint8 comboPoints = bot->GetComboTarget() == (comboTarget ? comboTarget->GetGUID() : ObjectGuid::Empty)
        ? bot->GetComboPoints() : 0;
    if (comboPoints < spell.MinComboPoints || (spell.MaxComboPoints && comboPoints > spell.MaxComboPoints))
        return "combo_point_gate";
    if (spell.MinReadyRunes && ReadyRuneCount(bot) < spell.MinReadyRunes)
        return "ready_rune_gate";
    if (spell.RequiredShapeshiftForm && uint8(bot->GetShapeshiftForm()) != spell.RequiredShapeshiftForm)
        return "shapeshift_form_gate";
    if (spell.RequiresPet && (!bot->GetPet() || !bot->GetPet()->IsAlive()))
        return "living_pet_required";
    if (spell.ForbidsPet && bot->GetPet())
        return "pet_forbidden";
    if (spell.RequiredMainHandEnchant
        && EquippedTemporaryEnchant(bot, EQUIPMENT_SLOT_MAINHAND) != spell.RequiredMainHandEnchant)
        return "main_hand_enchant_gate";
    if (spell.RequiredOffHandEnchant
        && EquippedTemporaryEnchant(bot, EQUIPMENT_SLOT_OFFHAND) != spell.RequiredOffHandEnchant)
        return "off_hand_enchant_gate";
    if (spell.TargetCreatureTypeMask && (!target || !(target->GetCreatureTypeMask() & spell.TargetCreatureTypeMask)))
        return "target_creature_type_gate";

    float manaPct = bot->GetMaxPower(POWER_MANA)
        ? float(bot->GetPower(POWER_MANA)) / float(bot->GetMaxPower(POWER_MANA)) : 0.0f;
    if (manaPct < spell.MinManaPct || manaPct > spell.MaxManaPct)
        return "mana_gate";
    Powers primaryPower = bot->GetPowerType();
    uint32 maxPrimaryPower = bot->GetMaxPower(primaryPower);
    float primaryPowerPct = maxPrimaryPower ? float(bot->GetPower(primaryPower)) / float(maxPrimaryPower) : 0.0f;
    if (primaryPowerPct < spell.MinPrimaryPowerPct || primaryPowerPct > spell.MaxPrimaryPowerPct)
        return "primary_power_gate";
    uint32 attackers = uint32(bot->getAttackers().size());
    if (attackers < spell.MinAttackers || (spell.MaxAttackers && attackers > spell.MaxAttackers))
        return "attacker_count_gate";
    if ((spell.RequiresStationary && bot->isMoving()) || (spell.RequiresMoving && !bot->isMoving()))
        return "movement_gate";
    return "";
}

}

std::vector<BotActionCandidate> BotClassSpecActionProfileStore::BuildCandidates(Player const* bot, Unit const* target, BotClassSpecActionProfile const& profile)
{
    std::vector<BotActionCandidate> candidates;
    if (!bot)
        return candidates;

    // Route-directed dungeon combat also consumes this low-level candidate
    // builder, bypassing BotController's richer healer frame. Keep the same
    // live triage contract here: a healer must not spend a GCD on damage while
    // an ally is below the normal healing threshold, and profile-declared
    // Min/MaxInjuredPlayers gates must apply to utility cooldowns as well.
    uint8 healerTriageInjuredPlayers = 0;
    if (profile.Role == "healer")
    {
        auto countTriageInjury = [&healerTriageInjuredPlayers](Player const* member)
        {
            if (member && member->IsAlive() && member->GetMaxHealth()
                && float(member->GetHealth()) / float(member->GetMaxHealth()) <= 0.94f)
                ++healerTriageInjuredPlayers;
        };
        if (Group const* group = bot->GetGroup())
            for (GroupReference const* itr = group->GetFirstMember(); itr; itr = itr->next())
                countTriageInjury(itr->GetSource());
        else
            countTriageInjury(bot);
    }

    std::map<std::string, bool> cooldownGroupsReady;
    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        if (spell.CooldownGroup.empty() || !spell.SpellId)
            continue;
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId);
        bool ready = spellInfo && bot->GetSpellHistory()->IsReady(spellInfo);
        auto [itr, inserted] = cooldownGroupsReady.emplace(spell.CooldownGroup, ready);
        if (!inserted)
            itr->second = itr->second && ready;
    }

    // A channel may be clipped only when the active channel is itself an
    // explicitly tagged profile action.  Keep the active action's profile
    // priority as the sole policy input; the resolver and executor carry the
    // resulting decision as typed state instead of inferring it from a spell
    // id or class.
    Spell const* currentChanneledSpell = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
    uint32 currentChanneledSpellId = currentChanneledSpell && currentChanneledSpell->GetSpellInfo()
        ? currentChanneledSpell->GetSpellInfo()->Id : 0;
    BotActionProfileSpell const* currentChanneledProfileSpell = nullptr;
    if (currentChanneledSpellId)
        for (BotActionProfileSpell const& profileSpell : profile.Spells)
            if (profileSpell.SpellId == currentChanneledSpellId
                && HasMechanicTag(profileSpell.MechanicTags, "interruptible_channel"))
            {
                currentChanneledProfileSpell = &profileSpell;
                break;
            }

    bool const postChannelTickInterruptWindow = currentChanneledProfileSpell
        && IsPostPeriodicTickInterruptWindow(bot, target, currentChanneledSpellId,
            ReactionTimeMsForSpec(profile.SpecTag.c_str()));

    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        bool selfTarget = spell.TargetSelector == "self";
        bool allyTarget = spell.TargetSelector == "party" || spell.TargetSelector == "lowest_ally" || spell.TargetSelector == "tank";
        Unit const* actionTarget = selfTarget ? static_cast<Unit const*>(bot) : target;
        uint64 targetGuid = actionTarget ? actionTarget->GetGUID().GetCounter() : 0;
        uint32 targetEntry = 0;
        if (Creature const* creature = actionTarget ? actionTarget->ToCreature() : nullptr)
            targetEntry = creature->GetEntry();

        BotActionCandidate candidate;
        candidate.ActionId = BotCombatActionCatalog::StableActionId(spell.Category, spell.SpellId);
        candidate.SpellId = spell.SpellId;
        candidate.Category = spell.Category;
        candidate.TargetType = selfTarget ? "self" : (allyTarget ? "ally" : "enemy");
        candidate.TargetGuid = targetGuid;
        candidate.TargetEntry = targetEntry;
        candidate.Profile = spell;
        candidate.Score = spell.DamageWeight + spell.HealingWeight + spell.ThreatWeight
            + spell.MitigationWeight + spell.SurvivalWeight + spell.ProgressionWeight
            - float(spell.PriorityBucket) * 0.03f;
        candidate.Reason = "observed_profile_priority";

        // The detailed observation is currently consumed by the Frost
        // compatibility fixture. Keep it scoped to that spec so the shared
        // decision stream does not repeat irrelevant proc/rune payloads for
        // every other class.
        if (profile.SpecTag == "frost_death_knight")
        {
            ReadyRuneObservation const runes = ObserveReadyRunes(bot);
            Powers const primaryPowerType = bot->GetPowerType();
            uint32 const currentPrimaryPower = bot->GetPower(primaryPowerType);
            uint32 const maximumPrimaryPower = bot->GetMaxPower(primaryPowerType);
            Aura const* maintainedAura = actionTarget && spell.MaintainAuraId
                ? actionTarget->GetAura(spell.MaintainAuraId) : nullptr;
            Aura const* ownedMaintainedAura = actionTarget && spell.MaintainAuraId
                ? actionTarget->GetAura(spell.MaintainAuraId, bot->GetGUID()) : nullptr;
            Aura const* ownedBloodPlague = target
                ? target->GetAura(55078, bot->GetGUID()) : nullptr;
            Aura const* ownedFrostFever = target
                ? target->GetAura(55095, bot->GetGUID()) : nullptr;
            std::ostringstream observation;
            observation << "{\"schema\":\"bot_action_observation_v1\""
                        << ",\"primary_power_type\":\"" << BotClassSpecActionProfileDetail::PowerName(primaryPowerType) << "\""
                        << ",\"current_primary_power\":" << currentPrimaryPower
                        << ",\"maximum_primary_power\":" << maximumPrimaryPower
                        << ",\"primary_power_ratio\":"
                        << (maximumPrimaryPower
                                ? float(currentPrimaryPower) / float(maximumPrimaryPower)
                                : 0.0f)
                        << ",\"ready_runes\":{\"total\":" << uint32(runes.Total)
                        << ",\"blood\":" << uint32(runes.Blood)
                        << ",\"unholy\":" << uint32(runes.Unholy)
                        << ",\"frost\":" << uint32(runes.Frost)
                        << ",\"death\":" << uint32(runes.Death) << '}'
                        << ",\"required_self_aura\":{\"spell_id\":"
                        << spell.RequiredSelfAura << ",\"active\":"
                        << (spell.RequiredSelfAura && bot->HasAura(spell.RequiredSelfAura)
                                ? "true" : "false") << '}'
                        << ",\"forbidden_self_aura\":{\"spell_id\":"
                        << spell.ForbiddenSelfAura << ",\"active\":"
                        << (spell.ForbiddenSelfAura && bot->HasAura(spell.ForbiddenSelfAura)
                                ? "true" : "false") << '}'
                        << ",\"maintained_aura\":{\"spell_id\":"
                        << spell.MaintainAuraId << ",\"active\":"
                        << (maintainedAura ? "true" : "false")
                        << ",\"remaining_ms\":"
                        << (maintainedAura ? maintainedAura->GetDuration() : 0)
                        << ",\"owned_active\":"
                        << (ownedMaintainedAura ? "true" : "false")
                        << ",\"owned_remaining_ms\":"
                        << (ownedMaintainedAura ? ownedMaintainedAura->GetDuration() : 0)
                        << ",\"refresh_below_ms\":" << spell.RefreshAuraBelowMs << '}'
                        << ",\"observed_aura_flags\":{\"48265\":"
                        << (bot->HasAura(48265) ? "true" : "false")
                        << ",\"51124\":" << (bot->HasAura(51124) ? "true" : "false")
                        << ",\"59052\":" << (bot->HasAura(59052) ? "true" : "false")
                        << ",\"owned_55078\":" << (ownedBloodPlague ? "true" : "false")
                        << ",\"owned_55078_remaining_ms\":"
                        << (ownedBloodPlague ? ownedBloodPlague->GetDuration() : 0)
                        << ",\"owned_55095\":" << (ownedFrostFever ? "true" : "false")
                        << ",\"owned_55095_remaining_ms\":"
                        << (ownedFrostFever ? ownedFrostFever->GetDuration() : 0)
                        << "}}";
            candidate.ObservationJson = observation.str();
        }

        SpellInfo const* spellInfo = spell.SpellId ? sSpellMgr->GetSpellInfo(spell.SpellId) : nullptr;
        Unit const* comboTarget = selfTarget ? target : actionTarget;
        std::string conditionRejection = EvaluateCompiledConditions(bot, actionTarget, comboTarget, spell);
        bool const interruptsCurrentChanneledSpell = postChannelTickInterruptWindow
            && spell.SpellId != currentChanneledSpellId
            && spell.PriorityBucket < currentChanneledProfileSpell->PriorityBucket
            && !bot->GetCurrentSpell(CURRENT_GENERIC_SPELL);
        if (!selfTarget && !actionTarget)
            candidate.RejectReason = allyTarget ? "missing_ally_target" : "missing_enemy_target";
        else if (spell.SpellId && !spellInfo)
            candidate.RejectReason = "missing_spell_info";
        else if (spell.Category == BotCombatActionCategory::UseItem
            && !FindOnUseItemForSpell(bot, spell.SpellId))
            candidate.RejectReason = "missing_or_depleted_item";
        else if (!conditionRejection.empty())
            candidate.RejectReason = conditionRejection;
        else if (!MeetsHostileTargetHealthGate(
                spell,
                target && target->GetMaxHealth()
                    ? float(target->GetHealth()) / float(target->GetMaxHealth())
                    : 0.0f))
            candidate.RejectReason = "hostile_target_health_gate";
        else if (profile.Role == "healer"
            && healerTriageInjuredPlayers
            && spell.DamageWeight > 0.0f
            && spell.Category != BotCombatActionCategory::HealFast
            && spell.Category != BotCombatActionCategory::HealEfficient
            && spell.Category != BotCombatActionCategory::HealAoe
            && spell.Category != BotCombatActionCategory::DispelCleanse
            && spell.Category != BotCombatActionCategory::Defensive
            && spell.Category != BotCombatActionCategory::ExternalDefensive
            && spell.Category != BotCombatActionCategory::Mitigation)
            candidate.RejectReason = "healer_triage_required";
        else if (profile.Role == "healer" && spell.MinInjuredPlayers
            && healerTriageInjuredPlayers < spell.MinInjuredPlayers)
            candidate.RejectReason = "injured_player_count_too_low";
        else if (profile.Role == "healer" && spell.MaxInjuredPlayers
            && healerTriageInjuredPlayers > spell.MaxInjuredPlayers)
            candidate.RejectReason = "injured_player_count_too_high";
        else if (bot->HasUnitState(UNIT_STATE_CASTING) && !interruptsCurrentChanneledSpell)
            candidate.RejectReason = "already_casting";
        else if (spellInfo && bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
            candidate.RejectReason = "global_cooldown";
        else if (spellInfo && !bot->GetSpellHistory()->IsReady(spellInfo))
            candidate.RejectReason = "cooldown_not_ready";
        else if (spellInfo && spellInfo->CasterAuraState
            && !bot->HasAuraState(AuraStateType(spellInfo->CasterAuraState), spellInfo, bot))
            candidate.RejectReason = "missing_caster_aura_state";
        else if (spellInfo && spellInfo->CasterAuraStateNot
            && bot->HasAuraState(AuraStateType(spellInfo->CasterAuraStateNot), spellInfo, bot))
            candidate.RejectReason = "forbidden_caster_aura_state";
        else if (spellInfo && spellInfo->CasterAuraSpell && !bot->HasAura(spellInfo->CasterAuraSpell))
            candidate.RejectReason = "missing_caster_aura";
        else if (spellInfo && spellInfo->ExcludeCasterAuraSpell && bot->HasAura(spellInfo->ExcludeCasterAuraSpell))
            candidate.RejectReason = "forbidden_caster_aura";
        else if (spellInfo && actionTarget && spellInfo->TargetAuraState
            && !actionTarget->HasAuraState(AuraStateType(spellInfo->TargetAuraState), spellInfo, bot))
            candidate.RejectReason = "missing_target_aura_state";
        else if (spellInfo && actionTarget && spellInfo->TargetAuraStateNot
            && actionTarget->HasAuraState(AuraStateType(spellInfo->TargetAuraStateNot), spellInfo, bot))
            candidate.RejectReason = "forbidden_target_aura_state";
        else if (spellInfo && actionTarget && spellInfo->TargetAuraSpell
            && !actionTarget->HasAura(spellInfo->TargetAuraSpell))
            candidate.RejectReason = "missing_spell_target_aura";
        else if (spellInfo && actionTarget && spellInfo->ExcludeTargetAuraSpell
            && actionTarget->HasAura(spellInfo->ExcludeTargetAuraSpell))
            candidate.RejectReason = "forbidden_spell_target_aura";
        else if (!spell.CooldownGroup.empty() && !cooldownGroupsReady[spell.CooldownGroup])
            candidate.RejectReason = "cooldown_group_not_aligned";
        else if (spell.RequiresInterruptibleTarget && actionTarget
            && !actionTarget->GetCurrentSpell(CURRENT_GENERIC_SPELL)
            && !actionTarget->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
            candidate.RejectReason = "target_not_interruptible";
        else if (spell.RequiresTargetNotVictim && actionTarget && actionTarget->GetVictim() == bot)
            candidate.RejectReason = "target_already_on_bot";
        else if (spell.RequiresTargetVictim && actionTarget && actionTarget->GetVictim() != bot)
            candidate.RejectReason = "target_not_on_bot";
        else if (spell.RequiresMeleeRange && actionTarget && !bot->IsWithinMeleeRange(actionTarget))
            candidate.RejectReason = "melee_range_required";
        else if (spell.RequiresRangedRange && actionTarget && bot->GetExactDist(actionTarget) < 5.0f)
            candidate.RejectReason = "ranged_range_required";
        else if (spellInfo && spellInfo->NeedsComboPoints()
            && (!comboTarget || bot->GetComboTarget() != comboTarget->GetGUID() || !bot->GetComboPoints()))
            candidate.RejectReason = "insufficient_combo_points";
        else if (spellInfo && spell.RequiresInstantCast && ProfileSpellCastTimeMs(bot, spellInfo) > 0)
            candidate.RejectReason = "instant_cast_required";
        else if (spellInfo && spell.MaxCastTimeMs && ProfileSpellCastTimeMs(bot, spellInfo) > spell.MaxCastTimeMs)
            candidate.RejectReason = "cast_time_too_long";
        else if (spellInfo && actionTarget
            && !bot->IsWithinDistInMap(actionTarget,
                std::max(5.0f, ProfileSpellMaximumRange(
                    bot, actionTarget, spellInfo))))
            candidate.RejectReason = "out_of_range";
        else if (spellInfo && !HasEnoughPowerForProfileSpell(bot, spellInfo))
            candidate.RejectReason = "insufficient_resource";

        if (candidate.RejectReason.empty() && interruptsCurrentChanneledSpell)
            candidate.InterruptCurrentChanneledSpell = true;

        candidates.push_back(candidate);
    }
    return candidates;
}

std::string BotClassSpecActionProfileStore::CandidateMaskJson(std::vector<BotActionCandidate> const& candidates, BotClassSpecActionProfile const& profile, char const* roleGoal, char const* saturationJson, char const* profileSourceOverride)
{
    std::ostringstream json;
    json << "{\"schema\":\"bot_valid_action_mask_v2\""
         << ",\"profile\":" << profile.EmbeddingJson()
         << ",\"profile_source\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(profileSourceOverride ? profileSourceOverride : profile.ProfileSource) << "\""
         << ",\"role_goal\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(roleGoal ? roleGoal : profile.Role) << "\""
         << ",\"role_saturation_state\":" << (saturationJson && *saturationJson ? saturationJson : "{}")
         << ",\"observation\":"
         << (candidates.empty() || candidates.front().ObservationJson.empty()
                ? "{}" : candidates.front().ObservationJson)
         << ",\"actions\":[";
    bool first = true;
    for (BotActionCandidate const& candidate : candidates)
    {
        if (!first)
            json << ",";
        first = false;
        json << "{\"action_id\":" << candidate.ActionId
             << ",\"spell_id\":" << candidate.SpellId
             << ",\"action_category\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(BotCombatActionCatalog::ToString(candidate.Category)) << "\""
             << ",\"target_guid\":" << candidate.TargetGuid
             << ",\"target_entry\":" << candidate.TargetEntry
             << ",\"score\":" << candidate.Score
             << ",\"sort_order\":" << candidate.Profile.SortOrder
             << ",\"priority_bucket\":" << uint32(candidate.Profile.PriorityBucket)
             << ",\"score_inputs\":{\"damage_weight\":" << candidate.Profile.DamageWeight
             << ",\"healing_weight\":" << candidate.Profile.HealingWeight
             << ",\"threat_weight\":" << candidate.Profile.ThreatWeight
             << ",\"mitigation_weight\":" << candidate.Profile.MitigationWeight
             << ",\"survival_weight\":" << candidate.Profile.SurvivalWeight
             << ",\"movement_weight\":" << candidate.Profile.MovementWeight
             << ",\"progression_weight\":" << candidate.Profile.ProgressionWeight
             << ",\"profession_weight\":" << candidate.Profile.ProfessionWeight << "}"
             << ",\"mechanic_tags\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(candidate.Profile.MechanicTags) << "\""
             << ",\"target_selector\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(candidate.Profile.TargetSelector) << "\""
             << ",\"movement_directive\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(candidate.Profile.MovementDirective) << "\""
             << ",\"auto_attack_mode\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(candidate.Profile.AutoAttackMode) << "\""
             << ",\"valid\":" << (candidate.RejectReason.empty() ? "true" : "false")
             << ",\"predicted_raw_heal\":" << candidate.PredictedRawHeal
             << ",\"predicted_effective_heal\":" << candidate.PredictedEffectiveHeal
             << ",\"predicted_overheal\":" << candidate.PredictedOverheal
             << ",\"mana_cost\":" << candidate.ManaCost
             << ",\"cast_time_ms\":" << candidate.CastTimeMs
             << ",\"reject_reason\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(candidate.RejectReason) << "\""
             << ",\"role_goal\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(roleGoal ? roleGoal : profile.Role) << "\"}";
    }
    json << "]}";
    return json.str();
}
std::string BotClassSpecActionProfileStore::ChosenActionJson(BotActionCandidate const* candidate, BotClassSpecActionProfile const& profile, char const* roleGoal, char const* balanceMode, float confidence)
{
    std::ostringstream json;
    json << "{\"action\":\"" << (candidate && candidate->SpellId ? "cast_combat_spell" : "attack") << "\""
         << ",\"action_id\":" << (candidate ? candidate->ActionId : BotCombatActionCatalog::StableActionId(BotCombatActionCategory::Wait))
         << ",\"spell_id\":" << (candidate ? candidate->SpellId : 0)
         << ",\"action_category\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(candidate ? BotCombatActionCatalog::ToString(candidate->Category) : "wait") << "\""
         << ",\"target_guid\":" << (candidate ? candidate->TargetGuid : 0)
         << ",\"target_entry\":" << (candidate ? candidate->TargetEntry : 0)
         << ",\"class_spec_profile\":" << profile.EmbeddingJson()
         << ",\"role_goal\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(roleGoal ? roleGoal : profile.Role) << "\""
         << ",\"adaptive_balance_mode\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(balanceMode ? balanceMode : "role_first") << "\""
         << ",\"experiment_confidence\":" << confidence
         << ",\"reason\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(candidate ? candidate->Reason : "no_valid_action") << "\""
         << ",\"sort_order\":" << (candidate ? candidate->Profile.SortOrder : 0)
         << ",\"priority_bucket\":" << (candidate ? uint32(candidate->Profile.PriorityBucket) : 0)
         << ",\"mechanic_tags\":\""
         << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(candidate ? candidate->Profile.MechanicTags : "") << "\""
         << ",\"expected_damage\":" << (candidate ? candidate->Profile.DamageWeight : 0.0f)
         << ",\"expected_heal\":" << (candidate ? candidate->Profile.HealingWeight : 0.0f)
         << ",\"expected_threat\":" << (candidate ? candidate->Profile.ThreatWeight : 0.0f)
         << ",\"expected_mitigation\":" << (candidate ? candidate->Profile.MitigationWeight : 0.0f)
         << ",\"observation\":"
         << (candidate && !candidate->ObservationJson.empty()
                ? candidate->ObservationJson : "{}")
         << ",\"reject_reason\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(candidate ? candidate->RejectReason : "no_valid_action") << "\"}";
    return json.str();
}
