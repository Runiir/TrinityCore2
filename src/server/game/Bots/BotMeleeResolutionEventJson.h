/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 */

#ifndef TRINITY_BOT_MELEE_RESOLUTION_EVENT_JSON_H
#define TRINITY_BOT_MELEE_RESOLUTION_EVENT_JSON_H

#include "Entities/Unit/MeleeDamageResolutionObservation.h"

#include <cstdint>
#include <ostream>

namespace BotMeleeResolutionEventJson
{
inline char const* AttackTypeName(std::uint8_t attackType)
{
    switch (attackType)
    {
        case 0: return "base";
        case 1: return "off_hand";
        case 2: return "ranged";
        default: return "unknown";
    }
}

inline char const* HitOutcomeName(std::uint8_t hitOutcome)
{
    switch (hitOutcome)
    {
        case 0: return "evade";
        case 1: return "miss";
        case 2: return "dodge";
        case 3: return "block";
        case 4: return "parry";
        case 5: return "glancing";
        case 6: return "critical";
        case 7: return "crushing";
        case 8: return "normal";
        default: return "unknown";
    }
}

inline void Append(std::ostream& json, std::uint64_t eventSequence,
    MeleeDamageResolutionObservation const& observation)
{
    auto hasStage = [&observation](MeleeDamageResolutionObservation::Stage stage)
    {
        return (observation.StageMask & std::uint32_t(stage)) != 0;
    };
    auto appendUint = [&json](bool available, std::uint32_t value)
    {
        if (available)
            json << value;
        else
            json << "null";
    };
    auto appendFloat = [&json](bool available, float value)
    {
        if (available)
            json << value;
        else
            json << "null";
    };
    bool const inputsAvailable = hasStage(MeleeDamageResolutionObservation::Inputs);
    bool const armorAvailable = hasStage(MeleeDamageResolutionObservation::Armor);
    bool const outcomeAvailable = hasStage(MeleeDamageResolutionObservation::HitOutcomeStage);
    bool const resolutionAvailable = hasStage(MeleeDamageResolutionObservation::Resolution);
    json << ",\"melee_resolution_sequence\":" << eventSequence
         << ",\"melee_resolution\":{\"stage_mask\":" << observation.StageMask
         << ",\"weapon_roll_amount\":";
    appendUint(hasStage(MeleeDamageResolutionObservation::WeaponRoll), observation.WeaponRollAmount);
    json << ",\"after_attacker_bonus_amount\":";
    appendUint(hasStage(MeleeDamageResolutionObservation::AttackerBonus), observation.AfterAttackerBonusAmount);
    json << ",\"after_target_bonus_amount\":";
    appendUint(hasStage(MeleeDamageResolutionObservation::TargetBonus), observation.AfterTargetBonusAmount);
    json << ",\"after_script_hook_amount\":";
    appendUint(hasStage(MeleeDamageResolutionObservation::ScriptHook), observation.AfterScriptHookAmount);
    json << ",\"target_armor\":";
    appendUint(inputsAvailable, observation.TargetArmor);
    json << ",\"armor_applied\":";
    if (armorAvailable)
        json << (observation.ArmorApplied ? "true" : "false");
    else
        json << "null";
    json << ",\"effective_armor\":";
    appendFloat(armorAvailable && observation.ArmorApplied, observation.EffectiveArmor);
    json << ",\"after_armor_amount\":";
    appendUint(armorAvailable, observation.AfterArmorAmount);
    json << ",\"after_hit_outcome_amount\":";
    appendUint(outcomeAvailable, observation.AfterHitOutcomeAmount);
    json << ",\"after_resilience_amount\":";
    appendUint(hasStage(MeleeDamageResolutionObservation::Resilience), observation.AfterResilienceAmount);
    json << ",\"resolved_damage_amount\":";
    appendUint(resolutionAvailable, observation.ResolvedDamageAmount);
    json << ",\"blocked_amount\":";
    appendUint(resolutionAvailable, observation.BlockedAmount);
    json << ",\"absorbed_amount\":";
    appendUint(resolutionAvailable, observation.AbsorbedAmount);
    json << ",\"resisted_amount\":";
    appendUint(resolutionAvailable, observation.ResistedAmount);
    json << ",\"attack_type\":";
    appendUint(inputsAvailable, observation.AttackType);
    json << ",\"attack_type_name\":";
    if (inputsAvailable)
        json << '\"' << AttackTypeName(observation.AttackType) << '\"';
    else
        json << "null";
    json << ",\"hit_outcome\":";
    appendUint(outcomeAvailable, observation.HitOutcome);
    json << ",\"hit_outcome_name\":";
    if (outcomeAvailable)
        json << '\"' << HitOutcomeName(observation.HitOutcome) << '\"';
    else
        json << "null";
    json << ",\"hit_info\":";
    appendUint(resolutionAvailable, observation.HitInfo);
    json << ",\"target_state\":";
    appendUint(resolutionAvailable, observation.TargetState);
    json << ",\"attacker_level\":";
    appendUint(inputsAvailable, observation.AttackerLevel);
    json << ",\"attacker_attack_power\":";
    appendFloat(inputsAvailable, observation.AttackerAttackPower);
    json << ",\"attacker_base_attack_time_ms\":";
    appendUint(inputsAvailable, observation.AttackerBaseAttackTimeMs);
    json << ",\"attacker_base_weapon_min_damage\":";
    appendFloat(inputsAvailable, observation.AttackerBaseWeaponMinDamage);
    json << ",\"attacker_base_weapon_max_damage\":";
    appendFloat(inputsAvailable, observation.AttackerBaseWeaponMaxDamage);
    json << ",\"attacker_published_min_damage\":";
    appendFloat(inputsAvailable, observation.AttackerPublishedMinDamage);
    json << ",\"attacker_published_max_damage\":";
    appendFloat(inputsAvailable, observation.AttackerPublishedMaxDamage);
    json << ",\"attacker_rank\":";
    appendUint(inputsAvailable && observation.AttackerTemplateInputsAvailable, observation.AttackerRank);
    json << ",\"attacker_template_damage_modifier\":";
    appendFloat(inputsAvailable && observation.AttackerTemplateInputsAvailable, observation.AttackerTemplateDamageModifier);
    json << ",\"attacker_template_base_variance\":";
    appendFloat(inputsAvailable && observation.AttackerTemplateInputsAvailable, observation.AttackerTemplateBaseVariance);
    json << '}';
}
}

#endif
