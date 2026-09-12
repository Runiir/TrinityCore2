/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 */

#ifndef TRINITY_MELEE_DAMAGE_RESOLUTION_OBSERVATION_H
#define TRINITY_MELEE_DAMAGE_RESOLUTION_OBSERVATION_H

#include <cstdint>

// Value-only observation of one native auto-attack calculation. These values
// describe calculation stages. They do not claim that health was changed;
// actual health damage remains authoritative in the linked combat damage event.
struct MeleeDamageResolutionObservation
{
    enum Stage : std::uint32_t
    {
        Inputs = 1u << 0,
        WeaponRoll = 1u << 1,
        AttackerBonus = 1u << 2,
        TargetBonus = 1u << 3,
        ScriptHook = 1u << 4,
        Armor = 1u << 5,
        HitOutcomeStage = 1u << 6,
        Resilience = 1u << 7,
        Resolution = 1u << 8,
    };

    std::uint32_t StageMask = 0;
    std::uint32_t WeaponRollAmount = 0;
    std::uint32_t AfterAttackerBonusAmount = 0;
    std::uint32_t AfterTargetBonusAmount = 0;
    std::uint32_t AfterScriptHookAmount = 0;
    std::uint32_t TargetArmor = 0;
    float EffectiveArmor = 0.0f;
    bool ArmorApplied = false;
    std::uint32_t AfterArmorAmount = 0;
    std::uint32_t AfterHitOutcomeAmount = 0;
    std::uint32_t AfterResilienceAmount = 0;
    std::uint32_t ResolvedDamageAmount = 0;
    std::uint32_t BlockedAmount = 0;
    std::uint32_t AbsorbedAmount = 0;
    std::uint32_t ResistedAmount = 0;
    std::uint32_t HitInfo = 0;
    std::uint32_t TargetState = 0;
    std::uint8_t AttackType = 0;
    std::uint8_t HitOutcome = 0;
    std::uint8_t AttackerLevel = 0;
    float AttackerAttackPower = 0.0f;
    std::uint32_t AttackerBaseAttackTimeMs = 0;
    float AttackerBaseWeaponMinDamage = 0.0f;
    float AttackerBaseWeaponMaxDamage = 0.0f;
    float AttackerPublishedMinDamage = 0.0f;
    float AttackerPublishedMaxDamage = 0.0f;
    bool AttackerTemplateInputsAvailable = false;
    std::uint32_t AttackerRank = 0;
    float AttackerTemplateDamageModifier = 0.0f;
    float AttackerTemplateBaseVariance = 0.0f;
};

#endif
