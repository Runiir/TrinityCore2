#ifndef TRINITY_BOT_NEFARIAN_CAPABILITIES_H
#define TRINITY_BOT_NEFARIAN_CAPABILITIES_H

// Class/spec capabilities Nefarian duties are chosen by. Spell identities and
// cooldowns are the 4.3.4 client rows this server loads (SpellCooldowns.dbc
// category or recovery time). Native legality stays with the executor: a
// candidate names a spell, and ExecuteNativeActionIntent refuses an unknown
// spell, a spell on cooldown or an invalid target.

#include "Define.h"
#include <string_view>

namespace BotEncounter::Nefarian
{
inline bool SpecStartsWith(std::string_view spec, std::string_view prefix)
{
    return spec.substr(0, prefix.size()) == prefix;
}

inline bool SpecEndsWith(std::string_view spec, std::string_view suffix)
{
    return spec.size() >= suffix.size()
        && spec.substr(spec.size() - suffix.size()) == suffix;
}

struct InterruptCapability
{
    uint32 SpellId = 0;
    uint32 CooldownMs = 0;
    float RangeYards = 0.0f;

    bool Known() const { return SpellId != 0; }
};

// Blast Nova (80734) is a 4.0 s cast in 10N/25N and repeats every 13 s
// natively, so a 10 s interrupt covers one prototype alone.
inline InterruptCapability InterruptFor(std::string_view spec)
{
    if (SpecEndsWith(spec, "death_knight"))
        return { 47528, 10000, 5.0f };  // Mind Freeze
    if (SpecEndsWith(spec, "rogue"))
        return { 1766, 10000, 5.0f };   // Kick
    if (SpecEndsWith(spec, "paladin"))
        return { 96231, 10000, 5.0f };  // Rebuke
    if (SpecEndsWith(spec, "warrior"))
        return { 6552, 10000, 5.0f };   // Pummel
    if (SpecEndsWith(spec, "shaman"))
        return { 57994, 15000, 25.0f }; // Wind Shear
    if (SpecEndsWith(spec, "mage"))
        return { 2139, 24000, 40.0f };  // Counterspell
    // Skull Bash: 60 s client cooldown; Brutal Impact 2/2 lowers it to 10 s,
    // which the bot talent build does not prove, so rank it as 60 s.
    if (spec == "feral_druid_tank")
        return { 80964, 60000, 13.0f }; // Skull Bash (Bear)
    if (spec == "feral_druid")
        return { 80965, 60000, 13.0f }; // Skull Bash (Cat)
    if (spec == "marksmanship_hunter")
        return { 34490, 20000, 35.0f }; // Silencing Shot
    if (spec == "shadow_priest")
        return { 15487, 45000, 30.0f }; // Silence
    return {};
}

inline bool IsMeleeInterrupt(InterruptCapability const& capability)
{
    return capability.Known() && capability.RangeYards <= 5.0f;
}

struct TauntCapability
{
    uint32 SpellId = 0;
    bool Known() const { return SpellId != 0; }
};

inline TauntCapability TauntFor(std::string_view spec)
{
    if (SpecEndsWith(spec, "death_knight"))
        return { 56222 }; // Dark Command
    if (spec == "feral_druid_tank")
        return { 6795 };  // Growl
    if (SpecEndsWith(spec, "paladin"))
        return { 62124 }; // Hand of Reckoning
    if (SpecEndsWith(spec, "warrior"))
        return { 355 };   // Taunt
    return {};
}

enum class ControlKind : uint8
{
    None,
    Shackle, // Shackle Undead: 50 s stun on undead, breaks on damage
    Stun,
    Root,
    Snare
};

struct ControlCapability
{
    uint32 SpellId = 0;
    ControlKind Kind = ControlKind::None;
    float RangeYards = 0.0f;
    // Area spells centred on the caster (Frost Nova) need the warrior close.
    bool SelfCentred = false;

    bool Known() const { return SpellId != 0; }
};

// Animated Bone Warriors (mechanic_immune_mask 8462871) are immune to charm,
// disorient, disarm, fear, sleep, knockout, polymorph and horror, but not to
// stun, root, snare or shackle. A stunned warrior also cannot trigger its
// Empowering Strikes stack (the trigger does not ignore caster auras).
inline ControlCapability ControlFor(std::string_view spec)
{
    if (SpecEndsWith(spec, "priest"))
        return { 9484, ControlKind::Shackle, 30.0f, false }; // Shackle Undead
    if (SpecEndsWith(spec, "hunter"))
        return { 5116, ControlKind::Snare, 40.0f, false };   // Concussive Shot
    if (SpecEndsWith(spec, "shaman"))
        return { 8056, ControlKind::Snare, 25.0f, false };   // Frost Shock
    if (SpecEndsWith(spec, "warlock"))
        return { 18223, ControlKind::Snare, 40.0f, false };  // Curse of Exhaustion
    if (SpecEndsWith(spec, "death_knight"))
        return { 45524, ControlKind::Snare, 20.0f, false };  // Chains of Ice
    if (SpecEndsWith(spec, "paladin"))
        return { 853, ControlKind::Stun, 10.0f, false };     // Hammer of Justice
    if (SpecEndsWith(spec, "mage"))
        return { 122, ControlKind::Root, 10.0f, true };      // Frost Nova
    return {};
}

inline bool IsHealerSpec(std::string_view spec, std::string_view role)
{
    return role == "healer" || SpecStartsWith(spec, "holy_")
        || SpecStartsWith(spec, "discipline_")
        || SpecStartsWith(spec, "restoration_");
}

inline bool IsMeleeDamageSpec(std::string_view spec)
{
    return SpecEndsWith(spec, "rogue") || spec == "retribution_paladin"
        || spec == "feral_druid" || spec == "enhancement_shaman"
        || spec == "arms_warrior" || spec == "fury_warrior"
        || spec == "frost_death_knight" || spec == "unholy_death_knight";
}

// Preference for the Nefarian tank: the longest-lived dragon and the phase 3
// boss. Lower is better.
inline int NefarianTankRank(std::string_view spec)
{
    if (spec == "blood_death_knight")
        return 0;
    if (spec == "protection_paladin")
        return 1;
    if (spec == "protection_warrior")
        return 2;
    if (spec == "feral_druid_tank")
        return 3;
    return 9;
}
}

#endif
