#ifndef TRINITY_BOT_OMNOTRON_CAPABILITIES_H
#define TRINITY_BOT_OMNOTRON_CAPABILITIES_H

#include "Define.h"
#include <optional>
#include <string_view>

// Duty capabilities by class/spec, never by roster slot. Spell IDs, ranges
// and cooldowns are the execution client's rows (4.3.4 Spell/SpellRange/
// SpellCooldowns.dbc, identical in 4.4.2.59185); the native executor still
// checks HasSpell, range and cooldown before it submits anything.
namespace BotEncounter::Omnotron
{
struct InterruptCapability
{
    uint32 SpellId = 0;
    float RangeYards = 0.0f;
    // Base client cooldown row. Only orders the rotation (short cooldowns
    // lead); talents and glyphs change the real one (Reverberation: Wind Shear
    // 15 s to 5 s), so readiness comes from the bot's own spell history at cast
    // (InterruptLedger::RecordUse), never from this value.
    uint32 CooldownMs = 0;
    bool Melee = false;
};

inline bool SpecIs(std::string_view classSpec, std::string_view className)
{
    return classSpec.size() >= className.size()
        && classSpec.substr(classSpec.size() - className.size()) == className;
}

inline bool SpecStarts(std::string_view classSpec, std::string_view prefix)
{
    return classSpec.substr(0, prefix.size()) == prefix;
}

// Only interrupts the shared native interrupt executor submits (6552, 1766,
// 2139, 57994, 96231, 47528, 80964/80965, 15487, 34490). Warlocks need a
// Felhunter's Spell Lock, which that executor does not cast.
inline std::optional<InterruptCapability> InterruptFor(std::string_view classSpec)
{
    if (SpecIs(classSpec, "rogue"))
        return InterruptCapability{ 1766, 5.0f, 10000, true };
    if (SpecIs(classSpec, "warrior"))
        return InterruptCapability{ 6552, 5.0f, 10000, true };
    if (SpecIs(classSpec, "death_knight"))
        return InterruptCapability{ 47528, 5.0f, 10000, true };
    if (SpecIs(classSpec, "paladin"))
        return InterruptCapability{ 96231, 5.0f, 10000, true };
    if (SpecIs(classSpec, "shaman"))
        return InterruptCapability{ 57994, 25.0f, 15000, false };
    if (SpecIs(classSpec, "mage"))
        return InterruptCapability{ 2139, 40.0f, 24000, false };
    if (SpecStarts(classSpec, "marksmanship_hunter"))
        return InterruptCapability{ 34490, 35.0f, 20000, false };
    if (SpecStarts(classSpec, "shadow_priest"))
        return InterruptCapability{ 15487, 30.0f, 45000, false };
    // Skull Bash needs Cat or Bear Form.
    if (SpecStarts(classSpec, "feral_druid"))
        return InterruptCapability{ 80965, 13.0f, 60000, true };
    return std::nullopt;
}

// Soaked In Poison (80011) is a poison. Cleanse (4987) and Remove Corruption
// (2782) dispel poison; Cleanse Spirit does not. A Feral tank stays in Bear
// Form, so it is not a dispeller.
inline bool CanCleansePoison(std::string_view classSpec, std::string_view role)
{
    if (SpecIs(classSpec, "paladin"))
        return true;
    return SpecIs(classSpec, "druid") && role != "tank"
        && !SpecStarts(classSpec, "feral_druid");
}

inline bool IsMeleeSpec(std::string_view classSpec)
{
    return SpecIs(classSpec, "rogue") || SpecIs(classSpec, "warrior")
        || SpecIs(classSpec, "death_knight")
        || SpecStarts(classSpec, "retribution_paladin")
        || SpecStarts(classSpec, "protection_paladin")
        || SpecStarts(classSpec, "feral_druid")
        || SpecStarts(classSpec, "enhancement_shaman");
}

// Ranged damage dealers and every healer stand at range.
inline bool StandsAtRange(std::string_view classSpec, std::string_view role)
{
    if (role == "tank")
        return false;
    if (role == "healer")
        return true;
    return !classSpec.empty() && !IsMeleeSpec(classSpec);
}
}

#endif
