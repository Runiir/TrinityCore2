#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Pet.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <sstream>

bool BotWorldPopulationMgr::ConfigureAfflictionPetRequirements(
    WorldBotState::NativePersistentPetSetupReceipt& requiredPet,
    char const*& requiredPetName, std::string const& role,
    std::string const& specTag)
{
    if (role != "dps" || specTag != "affliction_warlock")
        return false;

    requiredPet.RequiredSummonSpellId = 691; // Summon Felhunter
    requiredPet.RequiredCreatedBySpellId = 691;
    requiredPet.RequiredEntry = ENTRY_FELHUNTER;
    requiredPet.RequiredFamilyId = CREATURE_FAMILY_FELHUNTER;
    requiredPet.RequiredPetType = uint32(SUMMON_PET);
    requiredPet.RequiredPowerType = uint32(POWER_MANA);
    requiredPetName = "summon_felhunter";
    return true;
}

void BotWorldPopulationMgr::ObserveAfflictionCalibrationModifiers(
    CalibrationMetrics& metrics, Player* bot, Creature* fixtureTarget)
{
    ++metrics.AfflictionModifierObservationTicks;
    if (bot->HasAura(87339))
        ++metrics.AfflictionShadowMasteryActiveTicks;
    if (bot->HasAura(77215))
        ++metrics.AfflictionPotentAfflictionsActiveTicks;
    if (fixtureTarget->HasAura(48181, bot->GetGUID()))
        ++metrics.AfflictionHauntDebuffActiveTicks;
    if (Aura const* shadowEmbraceCaster = bot->GetAura(32392, bot->GetGUID()))
    {
        ++metrics.AfflictionShadowEmbraceCasterActiveTicks;
        metrics.AfflictionShadowEmbraceCasterEffectMask |=
            shadowEmbraceCaster->GetEffectMask();
        metrics.AfflictionMaximumShadowEmbraceCasterStacks =
            std::max<uint8>(metrics.AfflictionMaximumShadowEmbraceCasterStacks,
                shadowEmbraceCaster->GetStackAmount());
    }
    if (Aura const* shadowEmbrace = fixtureTarget->GetAura(32389,
        bot->GetGUID()))
    {
        ++metrics.AfflictionShadowEmbraceActiveTicks;
        metrics.AfflictionMaximumShadowEmbraceStacks =
            std::max<uint8>(metrics.AfflictionMaximumShadowEmbraceStacks,
                shadowEmbrace->GetStackAmount());
    }
    SpellInfo const* corruption = sSpellMgr->GetSpellInfo(172);
    AuraEffect const* hauntModifier = fixtureTarget->GetAuraEffect(
        48181, EFFECT_2, bot->GetGUID());
    AuraEffect const* shadowEmbraceModifier = fixtureTarget->GetAuraEffect(
        32389, EFFECT_0, bot->GetGUID());
    if (corruption && hauntModifier
        && hauntModifier->IsAffectingSpell(corruption))
    {
        ++metrics.AfflictionHauntAffectsCorruptionTicks;
        metrics.AfflictionMaximumHauntDamageModifierPct = std::max(
            metrics.AfflictionMaximumHauntDamageModifierPct,
            hauntModifier->GetAmount());
    }
    if (corruption && shadowEmbraceModifier
        && shadowEmbraceModifier->IsAffectingSpell(corruption))
    {
        ++metrics.AfflictionShadowEmbraceAffectsCorruptionTicks;
        metrics.AfflictionMaximumShadowEmbraceDamageModifierPct = std::max(
            metrics.AfflictionMaximumShadowEmbraceDamageModifierPct,
            shadowEmbraceModifier->GetAmount());
    }
    if (corruption && hauntModifier && shadowEmbraceModifier)
    {
        uint32 const multiplierPpm = uint32(std::max<int32>(0,
            fixtureTarget->SpellDamageBonusTaken(bot, corruption,
                1000000, DOT)));
        if (!metrics.AfflictionMinimumCorruptionTakenMultiplierPpm)
            metrics.AfflictionMinimumCorruptionTakenMultiplierPpm = multiplierPpm;
        else
            metrics.AfflictionMinimumCorruptionTakenMultiplierPpm = std::min(
                metrics.AfflictionMinimumCorruptionTakenMultiplierPpm,
                multiplierPpm);
        metrics.AfflictionMaximumCorruptionTakenMultiplierPpm = std::max(
            metrics.AfflictionMaximumCorruptionTakenMultiplierPpm,
            multiplierPpm);
    }
}

void BotWorldPopulationMgr::ObserveAfflictionDamageStage(
    CalibrationMetrics& metrics, Player* owner, Unit* victim, uint32 spellId,
    uint32 damage, uint32 unmitigatedDamage, uint32 damageType)
{
    if (!owner || !victim || owner->getClass() != CLASS_WARLOCK)
        return;

    switch (spellId)
    {
        case 172:   // Corruption
        case 30108: // Unstable Affliction
        case 48181: // Haunt
        case 47897: // Shadowflame direct hit
        case 47960: // Shadowflame periodic child
        case 1120:  // Drain Soul
            break;
        default:
            return;
    }

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo)
        return;

    CalibrationMetrics::AfflictionDamageStageObservation& observation =
        metrics.AfflictionDamageStageBySpell[spellId];
    bool const firstEvent = observation.EventCount == 0;
    ++observation.EventCount;
    if (damageType == uint32(DOT))
        ++observation.DotEventCount;
    else
        ++observation.DirectEventCount;
    observation.MeasuredDamage += damage;
    observation.UnmitigatedDamage += unmitigatedDamage;

    DamageEffectType const effectType = damageType == uint32(DOT)
        ? DOT : SPELL_DIRECT_DAMAGE;
    int32 spellmodFlat = 0;
    float spellmodMultiplier = 1.0f;
    owner->GetSpellModValues(spellInfo,
        effectType == DOT ? SpellModOp::PeriodicHealingAndDamage
                          : SpellModOp::HealingAndDamage,
        nullptr, 1000000.0f, &spellmodFlat, &spellmodMultiplier);
    uint32 const spellmodMultiplierPpm = uint32(
        std::max(0.0f, spellmodMultiplier) * 1000000.0f);
    auto observeSpellmod = [&](uint32& count, int32& flatMin, int32& flatMax,
        uint64& multiplierSum, uint32& multiplierMin, uint32& multiplierMax)
    {
        ++count;
        multiplierSum += spellmodMultiplierPpm;
        if (count == 1)
        {
            flatMin = spellmodFlat;
            flatMax = spellmodFlat;
            multiplierMin = spellmodMultiplierPpm;
            multiplierMax = spellmodMultiplierPpm;
            return;
        }
        flatMin = std::min(flatMin, spellmodFlat);
        flatMax = std::max(flatMax, spellmodFlat);
        multiplierMin = std::min(multiplierMin, spellmodMultiplierPpm);
        multiplierMax = std::max(multiplierMax, spellmodMultiplierPpm);
    };
    if (effectType == DOT)
        observeSpellmod(observation.PeriodicSpellmodObservationCount,
            observation.PeriodicSpellmodFlatMin,
            observation.PeriodicSpellmodFlatMax,
            observation.PeriodicSpellmodMultiplierPpmSum,
            observation.PeriodicSpellmodMultiplierPpmMin,
            observation.PeriodicSpellmodMultiplierPpmMax);
    else
        observeSpellmod(observation.DirectSpellmodObservationCount,
            observation.DirectSpellmodFlatMin,
            observation.DirectSpellmodFlatMax,
            observation.DirectSpellmodMultiplierPpmSum,
            observation.DirectSpellmodMultiplierPpmMin,
            observation.DirectSpellmodMultiplierPpmMax);
    uint32 const ownerDamagePctDonePpm = uint32(std::max(0.0f,
        owner->SpellDamagePctDone(victim, spellInfo, effectType)) * 1000000.0f);
    int32 const targetTakenMultiplierPpm = std::max(0,
        victim->SpellDamageBonusTaken(owner, spellInfo, 1000000, effectType));
    observation.OwnerDamagePctDonePpmSum += ownerDamagePctDonePpm;
    observation.TargetTakenMultiplierPpmSum += uint32(targetTakenMultiplierPpm);
    if (firstEvent)
    {
        observation.OwnerDamagePctDonePpmMin = ownerDamagePctDonePpm;
        observation.OwnerDamagePctDonePpmMax = ownerDamagePctDonePpm;
        observation.TargetTakenMultiplierPpmMin = uint32(targetTakenMultiplierPpm);
        observation.TargetTakenMultiplierPpmMax = uint32(targetTakenMultiplierPpm);
    }
    else
    {
        observation.OwnerDamagePctDonePpmMin = std::min(
            observation.OwnerDamagePctDonePpmMin, ownerDamagePctDonePpm);
        observation.OwnerDamagePctDonePpmMax = std::max(
            observation.OwnerDamagePctDonePpmMax, ownerDamagePctDonePpm);
        observation.TargetTakenMultiplierPpmMin = std::min(
            observation.TargetTakenMultiplierPpmMin,
            uint32(targetTakenMultiplierPpm));
        observation.TargetTakenMultiplierPpmMax = std::max(
            observation.TargetTakenMultiplierPpmMax,
            uint32(targetTakenMultiplierPpm));
    }

    auto findAffectingEffect = [spellInfo](Aura const* aura) -> AuraEffect const*
    {
        if (!aura)
            return nullptr;
        for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
            if (AuraEffect const* effect = aura->GetEffect(effectIndex))
                if (effect->IsAffectingSpell(spellInfo))
                    return effect;
        return nullptr;
    };
    auto observeAura = [&](Aura const* aura, uint32& presentEvents,
        uint32& affectingEvents, int32& amountMin, int32& amountMax)
    {
        if (!aura)
            return;
        ++presentEvents;
        AuraEffect const* effect = findAffectingEffect(aura);
        if (!effect)
            return;
        ++affectingEvents;
        if (affectingEvents == 1)
        {
            amountMin = effect->GetAmount();
            amountMax = effect->GetAmount();
        }
        else
        {
            amountMin = std::min(amountMin, effect->GetAmount());
            amountMax = std::max(amountMax, effect->GetAmount());
        }
    };

    observeAura(owner->GetAura(87339), observation.ShadowMasteryPresentEvents,
        observation.ShadowMasteryAffectingEvents,
        observation.ShadowMasteryAmountMin, observation.ShadowMasteryAmountMax);
    observeAura(owner->GetAura(77215), observation.PotentAfflictionsPresentEvents,
        observation.PotentAfflictionsAffectingEvents,
        observation.PotentAfflictionsAmountMin,
        observation.PotentAfflictionsAmountMax);
    observeAura(victim->GetAura(48181, owner->GetGUID()),
        observation.HauntPresentEvents, observation.HauntAffectingEvents,
        observation.HauntModifierAmountMin, observation.HauntModifierAmountMax);
    observeAura(victim->GetAura(32389, owner->GetGUID()),
        observation.ShadowEmbracePresentEvents,
        observation.ShadowEmbraceAffectingEvents,
        observation.ShadowEmbraceModifierAmountMin,
        observation.ShadowEmbraceModifierAmountMax);
}

void BotWorldPopulationMgr::ObserveAfflictionPeriodicOutcome(
    CalibrationMetrics& metrics, Player* owner, uint32 spellId,
    uint32 damage, bool critical, float critChancePct)
{
    if (!owner || owner->getClass() != CLASS_WARLOCK || !damage)
        return;

    auto stage = metrics.AfflictionDamageStageBySpell.find(spellId);
    if (stage == metrics.AfflictionDamageStageBySpell.end())
        return;

    CalibrationMetrics::AfflictionDamageStageObservation& observation =
        stage->second;
    uint32 const critChancePpm = uint32(
        std::max(0.0f, critChancePct) * 10000.0f);
    ++observation.PeriodicOutcomeCount;
    observation.PeriodicCritChancePpmSum += critChancePpm;
    if (observation.PeriodicOutcomeCount == 1)
    {
        observation.PeriodicCritChancePpmMin = critChancePpm;
        observation.PeriodicCritChancePpmMax = critChancePpm;
    }
    else
    {
        observation.PeriodicCritChancePpmMin = std::min(
            observation.PeriodicCritChancePpmMin, critChancePpm);
        observation.PeriodicCritChancePpmMax = std::max(
            observation.PeriodicCritChancePpmMax, critChancePpm);
    }

    if (critical)
    {
        ++observation.PeriodicCriticalCount;
        observation.PeriodicCriticalDamage += damage;
    }
    else
    {
        ++observation.PeriodicNonCriticalCount;
        observation.PeriodicNonCriticalDamage += damage;
    }
}

std::string BotWorldPopulationMgr::AppendAfflictionCalibrationJson(
    CalibrationMetrics const* metrics)
{
    std::ostringstream json;
    json << ",\"affliction_modifier_observation\":{\"sample_count\":"
         << (metrics ? metrics->AfflictionModifierObservationTicks : 0)
         << ",\"shadow_mastery_active_samples\":"
         << (metrics ? metrics->AfflictionShadowMasteryActiveTicks : 0)
         << ",\"potent_afflictions_active_samples\":"
         << (metrics ? metrics->AfflictionPotentAfflictionsActiveTicks : 0)
         << ",\"haunt_debuff_active_samples\":"
         << (metrics ? metrics->AfflictionHauntDebuffActiveTicks : 0)
         << ",\"shadow_embrace_caster_active_samples\":"
         << (metrics ? metrics->AfflictionShadowEmbraceCasterActiveTicks : 0)
         << ",\"shadow_embrace_caster_effect_mask\":"
         << (metrics ? uint32(metrics->AfflictionShadowEmbraceCasterEffectMask) : 0)
         << ",\"maximum_shadow_embrace_caster_stacks\":"
         << (metrics ? uint32(metrics->AfflictionMaximumShadowEmbraceCasterStacks) : 0)
         << ",\"shadow_embrace_active_samples\":"
         << (metrics ? metrics->AfflictionShadowEmbraceActiveTicks : 0)
         << ",\"maximum_shadow_embrace_stacks\":"
         << (metrics ? uint32(metrics->AfflictionMaximumShadowEmbraceStacks) : 0)
         << ",\"haunt_affects_corruption_samples\":"
         << (metrics ? metrics->AfflictionHauntAffectsCorruptionTicks : 0)
         << ",\"shadow_embrace_affects_corruption_samples\":"
         << (metrics ? metrics->AfflictionShadowEmbraceAffectsCorruptionTicks : 0)
         << ",\"maximum_haunt_damage_modifier_pct\":"
         << (metrics ? metrics->AfflictionMaximumHauntDamageModifierPct : 0)
         << ",\"maximum_shadow_embrace_damage_modifier_pct\":"
         << (metrics ? metrics->AfflictionMaximumShadowEmbraceDamageModifierPct : 0)
         << ",\"minimum_corruption_taken_multiplier_ppm\":"
         << (metrics ? metrics->AfflictionMinimumCorruptionTakenMultiplierPpm : 0)
         << ",\"maximum_corruption_taken_multiplier_ppm\":"
         << (metrics ? metrics->AfflictionMaximumCorruptionTakenMultiplierPpm : 0)
         << ",\"damage_stage_by_spell\":[";
    bool firstStage = true;
    if (metrics)
        for (auto const& [spellId, observation] : metrics->AfflictionDamageStageBySpell)
        {
            if (!firstStage)
                json << ',';
            firstStage = false;
            json << "{\"spell_id\":" << spellId
                 << ",\"event_count\":" << observation.EventCount
                 << ",\"dot_event_count\":" << observation.DotEventCount
                 << ",\"direct_event_count\":" << observation.DirectEventCount
                 << ",\"measured_damage\":" << observation.MeasuredDamage
                 << ",\"unmitigated_damage\":" << observation.UnmitigatedDamage
                 << ",\"owner_damage_pct_done_ppm_sum\":"
                 << observation.OwnerDamagePctDonePpmSum
                 << ",\"owner_damage_pct_done_ppm_min\":"
                 << observation.OwnerDamagePctDonePpmMin
                 << ",\"owner_damage_pct_done_ppm_max\":"
                 << observation.OwnerDamagePctDonePpmMax
                 << ",\"target_taken_multiplier_ppm_sum\":"
                 << observation.TargetTakenMultiplierPpmSum
                 << ",\"target_taken_multiplier_ppm_min\":"
                 << observation.TargetTakenMultiplierPpmMin
                 << ",\"target_taken_multiplier_ppm_max\":"
                 << observation.TargetTakenMultiplierPpmMax
                 << ",\"direct_spellmod_observation_count\":"
                 << observation.DirectSpellmodObservationCount
                 << ",\"direct_spellmod_flat_min\":"
                 << observation.DirectSpellmodFlatMin
                 << ",\"direct_spellmod_flat_max\":"
                 << observation.DirectSpellmodFlatMax
                 << ",\"direct_spellmod_multiplier_ppm_sum\":"
                 << observation.DirectSpellmodMultiplierPpmSum
                 << ",\"direct_spellmod_multiplier_ppm_min\":"
                 << observation.DirectSpellmodMultiplierPpmMin
                 << ",\"direct_spellmod_multiplier_ppm_max\":"
                 << observation.DirectSpellmodMultiplierPpmMax
                 << ",\"periodic_spellmod_observation_count\":"
                 << observation.PeriodicSpellmodObservationCount
                 << ",\"periodic_spellmod_flat_min\":"
                 << observation.PeriodicSpellmodFlatMin
                 << ",\"periodic_spellmod_flat_max\":"
                 << observation.PeriodicSpellmodFlatMax
                 << ",\"periodic_spellmod_multiplier_ppm_sum\":"
                 << observation.PeriodicSpellmodMultiplierPpmSum
                 << ",\"periodic_spellmod_multiplier_ppm_min\":"
                 << observation.PeriodicSpellmodMultiplierPpmMin
                 << ",\"periodic_spellmod_multiplier_ppm_max\":"
                 << observation.PeriodicSpellmodMultiplierPpmMax
                 << ",\"periodic_outcome_count\":"
                 << observation.PeriodicOutcomeCount
                 << ",\"periodic_critical_count\":"
                 << observation.PeriodicCriticalCount
                 << ",\"periodic_noncritical_count\":"
                 << observation.PeriodicNonCriticalCount
                 << ",\"periodic_critical_damage\":"
                 << observation.PeriodicCriticalDamage
                 << ",\"periodic_noncritical_damage\":"
                 << observation.PeriodicNonCriticalDamage
                 << ",\"periodic_crit_chance_ppm_sum\":"
                 << observation.PeriodicCritChancePpmSum
                 << ",\"periodic_crit_chance_ppm_min\":"
                 << observation.PeriodicCritChancePpmMin
                 << ",\"periodic_crit_chance_ppm_max\":"
                 << observation.PeriodicCritChancePpmMax
                 << ",\"shadow_mastery_present_events\":"
                 << observation.ShadowMasteryPresentEvents
                 << ",\"shadow_mastery_affecting_events\":"
                 << observation.ShadowMasteryAffectingEvents
                 << ",\"shadow_mastery_amount_min\":"
                 << observation.ShadowMasteryAmountMin
                 << ",\"shadow_mastery_amount_max\":"
                 << observation.ShadowMasteryAmountMax
                 << ",\"potent_afflictions_present_events\":"
                 << observation.PotentAfflictionsPresentEvents
                 << ",\"potent_afflictions_affecting_events\":"
                 << observation.PotentAfflictionsAffectingEvents
                 << ",\"potent_afflictions_amount_min\":"
                 << observation.PotentAfflictionsAmountMin
                 << ",\"potent_afflictions_amount_max\":"
                 << observation.PotentAfflictionsAmountMax
                 << ",\"haunt_present_events\":" << observation.HauntPresentEvents
                 << ",\"haunt_affecting_events\":"
                 << observation.HauntAffectingEvents
                 << ",\"haunt_modifier_amount_min\":"
                 << observation.HauntModifierAmountMin
                 << ",\"haunt_modifier_amount_max\":"
                 << observation.HauntModifierAmountMax
                 << ",\"shadow_embrace_present_events\":"
                 << observation.ShadowEmbracePresentEvents
                 << ",\"shadow_embrace_affecting_events\":"
                 << observation.ShadowEmbraceAffectingEvents
                 << ",\"shadow_embrace_modifier_amount_min\":"
                 << observation.ShadowEmbraceModifierAmountMin
                 << ",\"shadow_embrace_modifier_amount_max\":"
                 << observation.ShadowEmbraceModifierAmountMax
                 << '}';
        }
    json << "]}";
    return json.str();
}
