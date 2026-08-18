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
         << '}';
    return json.str();
}
