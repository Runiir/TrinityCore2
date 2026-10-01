#ifndef TRINITY_BOT_NEFARIAN_DRAGON_TANK_CARE_H
#define TRINITY_BOT_NEFARIAN_DRAGON_TANK_CARE_H

// Round 4 (BWD 10N round 3, tier-11 phase gear, label
// blackwing_descent_10n-r03-a3864fcf6d): all four attempts wiped in phase 1.
// The Feral Onyxia tank died first every time (Onyxia melee at +32-38 s, once
// her Shadowflame Breath at +12 s), and the untanked dragons then killed the
// raid. Disc priest output fell to 1.9-4.2k HPS, almost all Power Word:
// Shield and Prayer of Mending: the shared heal candidate triages the lowest
// member at Support priority (below the plan's own formation walks, which
// claim the cast lanes), and a protected walk lets it choose instant heals
// only. Nothing in the plan kept the dragon tanks up on the floor: their
// self-care (BotNefarianTankSelfCare.h) ran only on the pillars.
//
// On the floor (phase 1 and phase 3) this adds, as typed native casts:
// - a dragon's current victim uses its own defensives: the Feral Barkskin
//   (on a breath at it, or hurt), Frenzied Regeneration and Survival
//   Instincts; the Blood DK Anti-Magic Shell on a breath at it (Shadowflame
//   is magic), Rune Tap, Vampiric Blood, Icebound Fortitude and Death Strike
//   on the dragon it holds;
// - each healer heals the dragons' victims first: the lowest one in range and
//   sight, with an instant heal while it walks and a cast-time heal while it
//   stands (Discipline: Pain Suppression, Power Word: Shield, Penance, Flash
//   Heal, Greater Heal; Holy paladin: Lay on Hands, Holy Shock, Flash of
//   Light, Divine Light, Holy Light).
// Every spell is the bot's own, named only when the native facts say it is
// known and ready (a healer's heal also affordable with its current mana); the
// executor keeps every native rule (range, sight, mana, cooldown, Forbearance).

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianTankSelfCare.h"
#include <algorithm>
#include <array>
#include <vector>

namespace BotEncounter::Nefarian
{
constexpr uint32 SpellBarkskin = 22812;
constexpr uint32 SpellAntiMagicShell = 48707;
constexpr uint32 SpellRuneTap = 48982;
constexpr uint32 SpellVampiricBlood = 55233;
constexpr uint32 SpellIceboundFortitude = 48792;
constexpr uint32 SpellPenance = 47540;
constexpr uint32 SpellFlashHeal = 2061;
constexpr uint32 SpellGreaterHeal = 2060;
constexpr uint32 SpellHolyShock = 20473;
constexpr uint32 SpellFlashOfLight = 19750;
constexpr uint32 SpellDivineLight = 82326;
constexpr uint32 SpellHolyLight = 635;
constexpr uint32 SpellLayOnHands = 633;

// Feral.
constexpr float BarkskinBelowPct = 70.0f;
constexpr float FloorSurvivalInstinctsBelowPct = 35.0f;
// Blood.
constexpr float RuneTapBelowPct = 60.0f;
constexpr float VampiricBloodBelowPct = 50.0f;
constexpr float IceboundFortitudeBelowPct = 35.0f;
constexpr float FloorDeathStrikeBelowPct = 70.0f;
// Healers, on a dragon's victim.
constexpr float TankHealRangeYards = 40.0f;
constexpr float PainSuppressionBelowPct = 30.0f;
constexpr float PenanceBelowPct = 75.0f;
constexpr float FlashHealBelowPct = 50.0f;
constexpr float GreaterHealBelowPct = 85.0f;
constexpr float LayOnHandsBelowPct = 15.0f;
constexpr float HolyShockBelowPct = 90.0f;
constexpr float FlashOfLightBelowPct = 40.0f;
constexpr float DivineLightBelowPct = 65.0f;
constexpr float HolyLightBelowPct = 90.0f;
// Below this a victim's heal outranks a normal mechanic (Survival lane,
// under every escape).
constexpr float TankHealUrgentBelowPct = 50.0f;

inline bool FloorFightPhase(Phase phase)
{
    return phase == Phase::OnyxiaOnly || phase == Phase::BothDragons
        || phase == Phase::NefarianGround;
}

// The spells the floor care names, for the native readiness facts.
inline std::array<uint32, 8> DragonTankCareSpellsFor(std::string_view spec)
{
    if (spec == "feral_druid_tank")
        return { SpellBarkskin, SpellFrenziedRegeneration, SpellSurvivalInstincts, 0, 0, 0, 0, 0 };
    if (spec == "blood_death_knight")
        return { SpellAntiMagicShell, SpellRuneTap, SpellVampiricBlood,
            SpellIceboundFortitude, SpellDeathStrike, 0, 0, 0 };
    if (spec == "discipline_priest")
        return { SpellPainSuppression, SpellPowerWordShield, SpellPenance, SpellFlashHeal,
            SpellGreaterHeal, 0, 0, 0 };
    if (spec == "holy_paladin")
        return { SpellLayOnHands, SpellHolyShock, SpellFlashOfLight, SpellDivineLight,
            SpellHolyLight, 0, 0, 0 };
    return {};
}

struct CareDecision
{
    ObjectGuid Target;
    uint32 SpellId = 0;
    std::string_view Reason;
    bool Urgent = false;
};

// The dragons fighting on the floor now: Onyxia in combat, Nefarian landed
// and in combat.
inline std::array<ActorSnapshot const*, 2> FloorDragons(EncounterView const& view)
{
    std::array<ActorSnapshot const*, 2> dragons{ nullptr, nullptr };
    if (view.OnyxiaAlive() && view.Onyxia->InCombat)
        dragons[0] = view.Onyxia;
    if (view.NefarianLanded() && view.Nefarian->InCombat)
        dragons[1] = view.Nefarian;
    return dragons;
}

// The living players a floor dragon attacks now (whoever holds it: its tank,
// or anyone it turned to).
inline std::vector<ActorSnapshot const*> DragonVictims(Blackboard const& board,
    EncounterView const& view)
{
    std::vector<ActorSnapshot const*> victims;
    for (ActorSnapshot const* dragon : FloorDragons(view))
    {
        if (!dragon || dragon->VictimGuid.IsEmpty())
            continue;
        ActorSnapshot const* victim = board.FindActor(dragon->VictimGuid);
        if (victim && victim->Kind == ActorKind::Player && victim->Alive
            && std::find(victims.begin(), victims.end(), victim) == victims.end())
            victims.push_back(victim);
    }
    return victims;
}

// The floor dragon attacking this bot now, or none.
inline ActorSnapshot const* DragonOn(EncounterView const& view, ObjectGuid guid)
{
    for (ActorSnapshot const* dragon : FloorDragons(view))
        if (dragon && dragon->VictimGuid == guid)
            return dragon;
    return nullptr;
}

// A Shadowflame Breath under way at this bot (its caster breathes at its
// victim natively: DoCastVictim).
inline bool BreathAt(EncounterView const& view, ObjectGuid guid)
{
    for (ActorSnapshot const* dragon : FloorDragons(view))
        if (dragon && dragon->Cast && IsShadowflameBreath(dragon->Cast->SpellId)
            && (dragon->Cast->TargetGuid == guid
                || (dragon->Cast->TargetGuid.IsEmpty() && dragon->VictimGuid == guid)))
            return true;
    return false;
}

inline std::vector<CareDecision> DecideDragonTankDefensives(EncounterView const& view,
    ActorSnapshot const& bot, NativeFacts const* facts)
{
    std::vector<CareDecision> decisions;
    if (!bot.Alive || !FloorFightPhase(view.CurrentPhase))
        return decisions;
    ActorSnapshot const* dragon = DragonOn(view, bot.Guid);
    if (!dragon)
        return decisions;
    auto usable = [&](uint32 spell)
    {
        return !HasAura(bot, spell) && (!facts || facts->SpellUsable(bot.Guid, spell));
    };
    bool const breath = BreathAt(view, bot.Guid);
    float const health = bot.HealthPct;
    if (bot.ClassSpec == "feral_druid_tank")
    {
        if (health < FloorSurvivalInstinctsBelowPct && usable(SpellSurvivalInstincts))
            decisions.push_back({ bot.Guid, SpellSurvivalInstincts,
                "dragon_tank_survival_instincts", true });
        if ((breath || health < BarkskinBelowPct) && usable(SpellBarkskin))
            decisions.push_back({ bot.Guid, SpellBarkskin,
                breath ? "dragon_tank_barkskin_breath" : "dragon_tank_barkskin", true });
        bool const glyphed = !facts || facts->FrenziedRegenerationGlyphed(bot.Guid);
        if (health < (glyphed ? FrenziedRegenerationBelowPct : UnglyphedRegenerationBelowPct)
            && usable(SpellFrenziedRegeneration))
            decisions.push_back({ bot.Guid, SpellFrenziedRegeneration,
                "dragon_tank_frenzied_regeneration", true });
        return decisions;
    }
    if (bot.ClassSpec == "blood_death_knight")
    {
        if (health < IceboundFortitudeBelowPct && usable(SpellIceboundFortitude))
            decisions.push_back({ bot.Guid, SpellIceboundFortitude,
                "dragon_tank_icebound_fortitude", true });
        if (breath && usable(SpellAntiMagicShell))
            decisions.push_back({ bot.Guid, SpellAntiMagicShell,
                "dragon_tank_anti_magic_shell_breath", true });
        if (health < VampiricBloodBelowPct && usable(SpellVampiricBlood))
            decisions.push_back({ bot.Guid, SpellVampiricBlood,
                "dragon_tank_vampiric_blood", true });
        if (health < RuneTapBelowPct && usable(SpellRuneTap))
            decisions.push_back({ bot.Guid, SpellRuneTap, "dragon_tank_rune_tap", false });
        if (health < FloorDeathStrikeBelowPct
            && (!facts || facts->SpellUsable(bot.Guid, SpellDeathStrike)))
            decisions.push_back({ dragon->Guid, SpellDeathStrike,
                "dragon_tank_death_strike", false });
    }
    return decisions;
}

// A healer's heal on the dragons' victims: the lowest one in reach and sight
// (the healer itself counts), with an instant heal while the healer walks.
inline CareDecision DecideDragonTankHeal(Blackboard const& board, EncounterView const& view,
    ActorSnapshot const& bot, NativeFacts const* facts)
{
    CareDecision decision;
    if (!bot.Alive || !FloorFightPhase(view.CurrentPhase)
        || !IsHealerSpec(bot.ClassSpec, bot.Role))
        return decision;
    ActorSnapshot const* lowest = nullptr;
    for (ActorSnapshot const* victim : DragonVictims(board, view))
        if ((victim->Guid == bot.Guid
                || (Distance3(victim->Position, bot.Position) <= TankHealRangeYards
                    && (!facts || facts->InSight(victim->Guid))))
            && (!lowest || victim->HealthPct < lowest->HealthPct))
            lowest = victim;
    if (!lowest)
        return decision;
    bool const moving = facts && facts->FindMotion(bot.Guid)
        && facts->FindMotion(bot.Guid)->Moving;
    // Known, ready and affordable now (review r4 finding 8): the heal is the
    // one decision submitted, so an unaffordable choice would hide the
    // affordable alternatives behind it.
    auto usable = [&](uint32 spell)
    {
        return !facts || (facts->SpellUsable(bot.Guid, spell)
            && facts->SpellAffordable(bot.Guid, spell));
    };
    float const health = lowest->HealthPct;
    auto pick = [&](uint32 spell, std::string_view reason, bool urgent)
    {
        decision.Target = lowest->Guid;
        decision.SpellId = spell;
        decision.Reason = reason;
        decision.Urgent = urgent || health < TankHealUrgentBelowPct;
        return decision;
    };
    if (bot.ClassSpec == "discipline_priest")
    {
        if (health < PainSuppressionBelowPct && usable(SpellPainSuppression)
            && !HasAura(*lowest, SpellPainSuppression))
            return pick(SpellPainSuppression, "dragon_tank_pain_suppression", true);
        if (!HasAnyAura(*lowest, { SpellPowerWordShield, SpellWeakenedSoul })
            && usable(SpellPowerWordShield))
            return pick(SpellPowerWordShield, "dragon_tank_shield", false);
        if (moving)
            return decision;
        if (health < FlashHealBelowPct && usable(SpellFlashHeal))
            return pick(SpellFlashHeal, "dragon_tank_flash_heal", false);
        if (health < PenanceBelowPct && usable(SpellPenance))
            return pick(SpellPenance, "dragon_tank_penance", false);
        if (health < GreaterHealBelowPct && usable(SpellGreaterHeal))
            return pick(SpellGreaterHeal, "dragon_tank_greater_heal", false);
        return decision;
    }
    if (bot.ClassSpec == "holy_paladin")
    {
        if (health < LayOnHandsBelowPct && usable(SpellLayOnHands)
            && !HasAura(*lowest, SpellForbearance))
            return pick(SpellLayOnHands, "dragon_tank_lay_on_hands", true);
        if (health < HolyShockBelowPct && usable(SpellHolyShock))
            return pick(SpellHolyShock, "dragon_tank_holy_shock", false);
        if (moving)
            return decision;
        if (health < FlashOfLightBelowPct && usable(SpellFlashOfLight))
            return pick(SpellFlashOfLight, "dragon_tank_flash_of_light", false);
        if (health < DivineLightBelowPct && usable(SpellDivineLight))
            return pick(SpellDivineLight, "dragon_tank_divine_light", false);
        if (health < HolyLightBelowPct && usable(SpellHolyLight))
            return pick(SpellHolyLight, "dragon_tank_holy_light", false);
    }
    return decision;
}
}

#endif
