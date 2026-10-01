#ifndef TRINITY_BOT_OMNOTRON_TANK_SURVIVAL_H
#define TRINITY_BOT_OMNOTRON_TANK_SURVIVAL_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronFacts.h"
#include <algorithm>
#include <array>
#include <initializer_list>
#include <string_view>
#include <vector>

// Tank survival on Omnotron (BWD 10N round 4). At tier-11 gear 3 of 4
// round-3 attempts wiped the same way: a tank fell first, then the loose
// constructs killed the raid.
// - blackwing_descent_10n-r03-a3864fcf6d cd3009: the Feral tank, alone on
//   Arcanotron, fell from 140k to 0 in 14 s. No Barkskin, Survival Instincts
//   or Frenzied Regeneration was cast. The Holy paladin cast nothing on him
//   for the last 13.6 s.
// - acb506: the Feral took over Arcanotron at half health, with no defensive
//   and no external.
// Construct melee is not the cause. The 10N DamageModifier 11.2 is native-exact:
// unreduced swings average 62.6-65.6k against the calibrated 63.6k.
// The 1.12-1.15x ratios against the WCL mean come from two sources:
// - the WCL mean counts -10% swings, and the Feral's constructs never carried a
//   -10% debuff (0 of 170 swings), while the Blood DK's Scarlet Fever did;
// - +50% Power Generator swings on ranged players after a tank died.
// Every action below is an ordinary native cast of a known spell. The
// submission checks the bot's spell book, native cooldown, power and
// movement, and it takes the first castable one (FirstSubmittableSurvival).
namespace BotEncounter::Omnotron
{
// Tank defensives (spell ids from the 4.3.4 client).
inline constexpr uint32 SpellBarkskin = 22812;
inline constexpr uint32 SpellSurvivalInstincts = 61336;
inline constexpr uint32 SpellFrenziedRegeneration = 22842;
inline constexpr uint32 SpellDemoralizingRoar = 99;
inline constexpr uint32 SpellIceboundFortitude = 48792;
inline constexpr uint32 SpellVampiricBlood = 55233;
inline constexpr uint32 SpellRuneTap = 48982;
// Healer externals and tank heals.
inline constexpr uint32 SpellPainSuppression = 33206;
inline constexpr uint32 SpellGuardianSpirit = 47788;
inline constexpr uint32 SpellPowerWordShield = 17;
inline constexpr uint32 SpellWeakenedSoul = 6788;
inline constexpr uint32 SpellPenance = 47540;
inline constexpr uint32 SpellFlashHeal = 2061;
inline constexpr uint32 SpellGreaterHeal = 2060;
inline constexpr uint32 SpellLayOnHands = 633;
inline constexpr uint32 SpellForbearance = 25771;
inline constexpr uint32 SpellHolyShock = 20473;
inline constexpr uint32 SpellFlashOfLight = 19750;
inline constexpr uint32 SpellDivineLight = 82326;
inline constexpr uint32 SpellHolyLight = 635;

// Physical damage done -10% on the attacker. The 10N WCL melee envelope
// counts these rows (the registry lists 81130, 99, 1160, 26017 and 702):
// Scarlet Fever, Demoralizing Roar, Demoralizing Shout, Vindication and
// Curse of Weakness.
inline constexpr std::array<uint32, 5> AttackerWeaknessAuras{ 81130, 99, 1160, 26017, 702 };
// Demoralizing Roar: client SpellRadius 13 (10 yd). Area targets add their
// own size, so a construct counts while its centre is within 10 yd plus its
// bounding radius. One yard is kept as a margin.
inline constexpr float DemoralizingRoarRadius = 10.0f;
inline constexpr float DemoralizingRoarReach = DemoralizingRoarRadius
    + ConstructBoundingRadius - 1.0f;
// A debuff this close to expiry is refreshed (Demoralizing Roar lasts 30 s).
inline constexpr uint64 WeaknessRefreshMs = 3000;
// Direct heals reach 40 yd.
inline constexpr float TankHealRange = 40.0f;

// Tactic thresholds, percent of maximum health. They are not encounter
// values. When a tank holds two constructs (its partner died, or during a
// pickup), the major defensives start earlier.
inline constexpr float BarkskinBelowPct = 70.0f;
inline constexpr float FrenziedRegenerationBelowPct = 50.0f;
inline constexpr float SurvivalInstinctsBelowPct = 35.0f;
inline constexpr float RuneTapBelowPct = 60.0f;
inline constexpr float VampiricBloodBelowPct = 50.0f;
inline constexpr float IceboundFortitudeBelowPct = 35.0f;
inline constexpr float DoubleConstructMajorBelowPct = 55.0f;
inline constexpr float PainSuppressionBelowPct = 35.0f;
inline constexpr float GuardianSpiritBelowPct = 25.0f;
inline constexpr float LayOnHandsBelowPct = 15.0f;
inline constexpr float TankHealUrgentBelowPct = 50.0f;
inline constexpr float ShieldBelowPct = 95.0f;
inline constexpr float PenanceBelowPct = 60.0f;
inline constexpr float FlashHealBelowPct = 45.0f;
inline constexpr float GreaterHealBelowPct = 75.0f;
inline constexpr float HolyShockBelowPct = 90.0f;
inline constexpr float FlashOfLightBelowPct = 45.0f;
inline constexpr float DivineLightBelowPct = 65.0f;
inline constexpr float HolyLightBelowPct = 85.0f;

struct SurvivalDecision
{
    ObjectGuid Target;
    uint32 SpellId = 0;
    std::string_view Reason;
    bool Urgent = false;
};

inline bool HasAnyAuraOf(ActorSnapshot const& actor, std::initializer_list<uint32> spells)
{
    for (uint32 spell : spells)
        if (HasAura(actor, spell))
            return true;
    return false;
}

// Damage-reduction cooldowns already running on a tank. A second one would
// overlap the first, so it waits.
inline bool HasMajorDamageReduction(ActorSnapshot const& tank)
{
    return HasAnyAuraOf(tank, { SpellSurvivalInstincts, SpellIceboundFortitude,
        SpellPainSuppression, SpellGuardianSpirit });
}

// Living fighting constructs whose melee is on this player.
inline std::size_t ConstructsOn(EncounterFacts const& facts, ObjectGuid player)
{
    std::size_t count = 0;
    for (ConstructFact const& fact : facts.Constructs)
        if (fact.Fighting() && fact.Actor->Alive && fact.Actor->VictimGuid == player)
            ++count;
    return count;
}

inline bool CarriesAttackerWeakness(ActorSnapshot const& construct, uint64 nowMs)
{
    for (AuraSnapshot const& aura : construct.Auras)
        for (uint32 spell : AttackerWeaknessAuras)
            if (aura.SpellId == spell
                && (!aura.ExpiresAtMs || aura.ExpiresAtMs > nowMs + WeaknessRefreshMs))
                return true;
    return false;
}

// A Feral tank keeps Demoralizing Roar on the constructs it can reach.
// Only active, unshielded constructs count. The runtime offense restriction
// also keeps the roar off a shielded one.
inline bool WantsDemoralizingRoar(Blackboard const& board, EncounterFacts const& facts,
    ActorSnapshot const& bot)
{
    if (bot.ClassSpec != "feral_druid_tank" || !ConstructsOn(facts, bot.Guid))
        return false;
    for (ConstructFact const& fact : facts.Constructs)
        if (fact.Fighting() && !fact.Shielded() && fact.Actor->Alive
            && PlanarDistance(fact.Actor->Position, bot.Position) <= DemoralizingRoarReach
            && !CarriesAttackerWeakness(*fact.Actor, board.ObservedAtMs))
            return true;
    return false;
}

// A tank that holds a construct: its own defensives, most urgent first.
inline std::vector<SurvivalDecision> DecideTankDefensives(EncounterFacts const& facts,
    ActorSnapshot const& bot)
{
    std::vector<SurvivalDecision> decisions;
    std::size_t const held = ConstructsOn(facts, bot.Guid);
    if (!bot.Alive || bot.Role != "tank" || !held)
        return decisions;
    float const health = bot.HealthPct;
    bool const doubled = held >= 2;
    float const majorBelow = doubled ? DoubleConstructMajorBelowPct : 0.0f;
    bool const covered = HasMajorDamageReduction(bot);
    auto add = [&](uint32 spell, std::string_view reason, bool urgent)
    {
        if (!HasAura(bot, spell))
            decisions.push_back({ bot.Guid, spell, reason, urgent });
    };
    if (bot.ClassSpec == "feral_druid_tank")
    {
        if (!covered && health < std::max(SurvivalInstinctsBelowPct, majorBelow))
            add(SpellSurvivalInstincts, "omnotron_tank_survival_instincts", true);
        if (health < BarkskinBelowPct || doubled)
            add(SpellBarkskin, "omnotron_tank_barkskin", health < TankHealUrgentBelowPct);
        if (health < FrenziedRegenerationBelowPct)
            add(SpellFrenziedRegeneration, "omnotron_tank_frenzied_regeneration", true);
    }
    else if (bot.ClassSpec == "blood_death_knight")
    {
        if (!covered && health < std::max(IceboundFortitudeBelowPct, majorBelow))
            add(SpellIceboundFortitude, "omnotron_tank_icebound_fortitude", true);
        if (health < std::max(VampiricBloodBelowPct, majorBelow))
            add(SpellVampiricBlood, "omnotron_tank_vampiric_blood", true);
        if (health < RuneTapBelowPct)
            add(SpellRuneTap, "omnotron_tank_rune_tap", false);
    }
    return decisions;
}

// The construct victim a healer should hold up: the lowest living player a
// fighting construct is hitting, within heal range.
inline ActorSnapshot const* LowestConstructVictim(Blackboard const& board,
    EncounterFacts const& facts, ActorSnapshot const& healer)
{
    ActorSnapshot const* lowest = nullptr;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || !ConstructsOn(facts, player.Guid)
            || PlanarDistance(player.Position, healer.Position) > TankHealRange)
            continue;
        if (!lowest || player.HealthPct < lowest->HealthPct
            || (player.HealthPct == lowest->HealthPct && player.Guid < lowest->Guid))
            lowest = &player;
    }
    return lowest;
}

// A healer's heal or external on the construct victim, best first. The
// paladin is the main tank healer. The Discipline priest shields, and heals a
// victim directly only when the victim is in danger, so the raid keeps its
// Incineration healing.
inline std::vector<SurvivalDecision> DecideTankHeals(Blackboard const& board,
    EncounterFacts const& facts, ActorSnapshot const& bot, bool moving)
{
    std::vector<SurvivalDecision> decisions;
    if (!bot.Alive || bot.Role != "healer")
        return decisions;
    ActorSnapshot const* victim = LowestConstructVictim(board, facts, bot);
    if (!victim)
        return decisions;
    float const health = victim->HealthPct;
    bool const urgent = health < TankHealUrgentBelowPct;
    auto add = [&](uint32 spell, std::string_view reason, bool castTime, bool pressing)
    {
        if (castTime && moving)
            return;
        decisions.push_back({ victim->Guid, spell, reason, pressing || urgent });
    };
    bool const covered = HasMajorDamageReduction(*victim);
    if (bot.ClassSpec == "discipline_priest")
    {
        if (!covered && health < PainSuppressionBelowPct)
            add(SpellPainSuppression, "omnotron_tank_pain_suppression", false, true);
        if (health < ShieldBelowPct
            && !HasAnyAuraOf(*victim, { SpellPowerWordShield, SpellWeakenedSoul }))
            add(SpellPowerWordShield, "omnotron_tank_shield", false, false);
        if (health < PenanceBelowPct)
            add(SpellPenance, "omnotron_tank_penance", true, false);
        if (health < FlashHealBelowPct)
            add(SpellFlashHeal, "omnotron_tank_flash_heal", true, false);
    }
    else if (bot.ClassSpec == "holy_priest")
    {
        if (!covered && health < GuardianSpiritBelowPct)
            add(SpellGuardianSpirit, "omnotron_tank_guardian_spirit", false, true);
        if (health < FlashHealBelowPct)
            add(SpellFlashHeal, "omnotron_tank_flash_heal", true, false);
        if (health < GreaterHealBelowPct)
            add(SpellGreaterHeal, "omnotron_tank_greater_heal", true, false);
    }
    else if (bot.ClassSpec == "holy_paladin")
    {
        if (health < LayOnHandsBelowPct && !HasAura(*victim, SpellForbearance))
            add(SpellLayOnHands, "omnotron_tank_lay_on_hands", false, true);
        if (health < HolyShockBelowPct)
            add(SpellHolyShock, "omnotron_tank_holy_shock", false, false);
        if (health < FlashOfLightBelowPct)
            add(SpellFlashOfLight, "omnotron_tank_flash_of_light", true, false);
        if (health < DivineLightBelowPct)
            add(SpellDivineLight, "omnotron_tank_divine_light", true, false);
        if (health < HolyLightBelowPct)
            add(SpellHolyLight, "omnotron_tank_holy_light", true, false);
    }
    return decisions;
}

// Everything this bot may cast for tank survival on this snapshot, best
// first: the tank's own defensives, Demoralizing Roar, then a healer's
// external and heals.
inline std::vector<SurvivalDecision> DecideSurvivalActions(Blackboard const& board,
    EncounterFacts const& facts, ActorSnapshot const& bot, bool moving)
{
    std::vector<SurvivalDecision> decisions;
    if (!facts.Engaged || board.Route.NodeId != EncounterNodeId || !bot.Alive)
        return decisions;
    decisions = DecideTankDefensives(facts, bot);
    if (WantsDemoralizingRoar(board, facts, bot))
        decisions.push_back({ bot.Guid, SpellDemoralizingRoar,
            "omnotron_tank_demoralizing_roar", false });
    for (SurvivalDecision const& heal : DecideTankHeals(board, facts, bot, moving))
        decisions.push_back(heal);
    return decisions;
}

// The one decision the runtime submits: the first one the bot can cast now.
// `castable` is the native admission of a decision: the spell is known and
// active, its cooldown is ready, the bot can pay its power cost now, it is
// instant while the bot moves, and its target is alive. An unaffordable or
// cooling spell therefore falls through to the next alternative (a paladin
// short of mana for Flash of Light still casts Holy Light).
// While this bot is the assigned Arcane Annihilator interrupter, only urgent
// survival may take its global cooldown, cast and target: nonurgent
// maintenance (a Demoralizing Roar refresh, early Barkskin, Rune Tap, a top-up
// heal) waits so the interrupt is never displaced.
template <typename Castable>
inline SurvivalDecision const* FirstSubmittableSurvival(
    std::vector<SurvivalDecision> const& decisions, bool assignedInterrupt,
    Castable&& castable)
{
    for (SurvivalDecision const& decision : decisions)
    {
        if (assignedInterrupt && !decision.Urgent)
            continue;
        if (castable(decision))
            return &decision;
    }
    return nullptr;
}
}

#endif
