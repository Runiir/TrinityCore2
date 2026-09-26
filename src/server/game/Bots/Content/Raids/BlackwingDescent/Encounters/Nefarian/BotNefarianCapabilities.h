#ifndef TRINITY_BOT_NEFARIAN_CAPABILITIES_H
#define TRINITY_BOT_NEFARIAN_CAPABILITIES_H

// Class/spec capabilities Nefarian duties are chosen by. Spell identities and
// cooldowns are the 4.3.4 client rows this server loads (SpellCooldowns.dbc
// category or recovery time). Every entry is learnable by the spec it is keyed
// on: a class spell (SkillLineAbility.dbc class mask) for any spec of that
// class, a talent (Talent.dbc) only for its own tree, so Silencing Shot is
// Marksmanship's, Silence Shadow's and Curse of Exhaustion Affliction's
// (tests/test_nefarian_capabilities.py checks every spec against the DBCs).
// At run time the native observer also reports whether each bot knows the
// spell (NativeFacts::SpellKnown), and a duty is never handed to a bot that
// does not. Native legality stays with the executor: a candidate names a
// spell, and ExecuteNativeActionIntent refuses an unknown spell, a spell on
// cooldown or an invalid target.

#include "Define.h"
#include <array>
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
    uint32 CooldownMs = 0; // client recovery or category cooldown

    bool Known() const { return SpellId != 0; }
};

// Animated Bone Warriors (mechanic_immune_mask 8462871) are immune to charm,
// disorient, disarm, fear, sleep, knockout, polymorph and horror, but not to
// stun, root, snare or shackle. A stunned warrior also cannot trigger its
// Empowering Strikes stack (the trigger does not ignore caster auras).
inline ControlCapability ControlFor(std::string_view spec)
{
    if (SpecEndsWith(spec, "priest"))
        return { 9484, ControlKind::Shackle, 30.0f, false, 0 };      // Shackle Undead
    if (SpecEndsWith(spec, "hunter"))
        return { 5116, ControlKind::Snare, 40.0f, false, 5000 };     // Concussive Shot
    if (SpecEndsWith(spec, "shaman"))
        return { 8056, ControlKind::Snare, 25.0f, false, 6000 };     // Frost Shock
    // Curse of Exhaustion is an Affliction talent. Demonology and Destruction
    // have no bone-warrior control this table can name (Shadowfury is
    // ground-targeted; fears, Death Coil and Seduction are immune mechanics).
    if (spec == "affliction_warlock")
        return { 18223, ControlKind::Snare, 40.0f, false, 0 };       // Curse of Exhaustion
    if (SpecEndsWith(spec, "death_knight"))
        return { 45524, ControlKind::Snare, 20.0f, false, 0 };       // Chains of Ice
    if (SpecEndsWith(spec, "paladin"))
        return { 853, ControlKind::Stun, 10.0f, false, 60000 };      // Hammer of Justice
    if (SpecEndsWith(spec, "mage"))
        return { 122, ControlKind::Root, 10.0f, true, 25000 };       // Frost Nova
    return {};
}

// Nature's Grasp 16689, the warrior handler's root (user raid experience
// 2026-09-26: the Feral druid kites the bone warriors and roots them with it).
// A baseline druid spell (SkillLineAbility.dbc skill line 574, class mask
// 1024, no talent), usable in bear, cat and moonkin form (SpellShapeshift 162,
// mask 0x40000091), 3 charges for 45 s, 60 s cooldown: an enemy that strikes
// the druid is rooted by Entangling Roots 19975 for 27 s. Bone warriors are
// not immune to roots.
constexpr uint32 SpellNaturesGrasp = 16689;
constexpr uint32 SpellNaturesGraspRoot = 19975;

inline uint32 WarriorRootFor(std::string_view spec)
{
    return SpecEndsWith(spec, "druid") || SpecEndsWith(spec, "druid_tank")
        ? SpellNaturesGrasp : 0;
}

// Off-heal for a pillar team without a healer (coordinator default, pending
// the user's answer): a hybrid DPS casts its native single-target heal on its
// team. Healing Surge 8004 is in the Elemental and Enhancement action
// profiles; Flash of Light 19750 is a baseline paladin spell. Healing Rain is
// ground-targeted and not named here.
inline uint32 OffHealFor(std::string_view spec)
{
    if (spec == "elemental_shaman" || spec == "enhancement_shaman")
        return 8004;  // Healing Surge
    if (spec == "retribution_paladin")
        return 19750; // Flash of Light
    return 0;
}

// Before the floor goes under, the healers shield and top up everyone:
// Power Word: Shield 17 (both priest healers), Flash of Light 19750 (Holy).
constexpr uint32 SpellPowerWordShield = 17;
constexpr uint32 SpellWeakenedSoul = 6788;

inline uint32 PreAscentShieldFor(std::string_view spec)
{
    return spec == "discipline_priest" || spec == "holy_priest" ? SpellPowerWordShield : 0;
}

inline uint32 PreAscentTopUpFor(std::string_view spec)
{
    return spec == "holy_paladin" ? 19750u : 0u;
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
// The tanks heal themselves on the healerless pillar (round 8, user raid
// experience 2026-09-26). Blood: Death Strike (49998, heals at least 7% of
// maximum health). Feral: Enrage (5229) for rage, Frenzied Regeneration
// (22842: +30% maximum health, health raised to 30% if below; unglyphed it
// converts up to 10 rage a second at 0.30% of maximum health each - the
// canonical Glyph of Frenzied Regeneration, item 40896 / spell 54810,
// replaces that with +30% healing received) and Survival Instincts (61336).
constexpr uint32 SpellDeathStrike = 49998;
constexpr uint32 SpellEnrage = 5229;
constexpr uint32 SpellFrenziedRegeneration = 22842;
constexpr uint32 SpellSurvivalInstincts = 61336;
constexpr uint32 SpellGlyphOfFrenziedRegeneration = 54810;

inline std::array<uint32, 3> TankSelfCareSpellsFor(std::string_view spec)
{
    if (spec == "blood_death_knight")
        return { SpellDeathStrike, 0, 0 };
    if (spec == "feral_druid_tank")
        return { SpellEnrage, SpellFrenziedRegeneration, SpellSurvivalInstincts };
    return { 0, 0, 0 };
}

// A crossing helper's magma defensive (round 8), cast as it drops into the
// lava: Divine Shield (paladins; Forbearance 25771 blocks it) or Pain
// Suppression (Discipline). A damage dealer crosses only with one.
constexpr uint32 SpellDivineShield = 642;
constexpr uint32 SpellPainSuppression = 33206;
constexpr uint32 SpellForbearance = 25771;

inline uint32 CrossingDefensiveFor(std::string_view spec)
{
    if (spec.size() >= 7 && spec.substr(spec.size() - 7) == "paladin")
        return SpellDivineShield;
    if (spec == "discipline_priest")
        return SpellPainSuppression;
    return 0;
}

// A member's share of its pillar's prototype damage (round 8 pillar
// balance): damage dealers 1, a tank about half, a healer nothing.
inline float PillarDamageWeight(std::string_view spec, std::string_view role)
{
    if (role == "healer" || IsHealerSpec(spec, role))
        return 0.0f;
    if (role == "tank")
        return spec == "blood_death_knight" ? 0.5f : 0.4f;
    return 1.0f;
}

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
