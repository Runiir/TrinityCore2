#ifndef TRINITY_BOT_MAGMAW_MANGLE_COOLDOWN_PLAN_H
#define TRINITY_BOT_MAGMAW_MANGLE_COOLDOWN_PLAN_H

#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMangleDefensive.h"

#include <optional>
#include <string_view>
#include <vector>

class Player;
struct BotActionCandidate;

// The Blood tank's profile rows planned around Magmaw's next Mangle (error
// ledger TANK-003).  In b3-0dbce440-k1 the sole tank met the 90 s Mangle at
// 46% health with nothing left: the 70% Vampiric Blood row fired at 50.2 s,
// the 35% emergency release spent Icebound Fortitude at 60.3 s (3 min
// cooldown, so gone for the Mangle), Bone Shield ran out at 86.2 s, and in
// the last 6 s Heart Strike x2 and Rune Strike took the runes and global
// cooldowns while Death Strike failed its rune gate: no Blood Shield at the
// seize.  The surviving b2-fd4ba456-k4 met Mangle at full health with
// Icebound pre-cast and Bone Shield up (37k hit against 86.5k).
//
// Every input is native: Magmaw's own Mangle timer on the encounter
// blackboard (MagmawMangleDefensive::ObserveMangleTimer, the overdue Mangle
// published as 0), the spells' own cooldowns, auras and the profile's native
// preflight.  The plan only rejects rows; it never casts, and it adds no
// aura, cooldown reset, damage or health change.
namespace BotEncounter::MagmawMangleCooldownPlan
{
using MagmawMangleDefensive::BoneShieldSpell;
using MagmawMangleDefensive::DefensiveTrigger;
using MagmawMangleDefensive::DefensiveWindow;
using MagmawMangleDefensive::IceboundFortitudeSpell;
using MagmawMangleDefensive::MangleTimer;
using MagmawMangleDefensive::PreMangleLeadMs;
using MagmawMangleDefensive::VampiricBloodSpell;

constexpr uint32 RuneTapSpell = 48982;
constexpr uint32 DeathStrikeSpell = 49998;
constexpr uint32 HeartStrikeSpell = 55050;
constexpr uint32 RuneStrikeSpell = 56815;
// spell_dk_death_strike_heal casts it from the Death Strike heal in Blood
// Presence; 10 s, physical absorb.
constexpr uint32 BloodShieldAbsorbSpell = 77535;

struct Plan
{
    // A tank on the engaged Magmaw encounter with its native Mangle timer.
    bool Active = false;
    MangleTimer Timer;
    float HealthPct = 1.0f;
    uint32 IceboundCooldownMs = 0;
    uint32 VampiricBloodCooldownMs = 0;
    // Vampiric Blood or Rune Tap passed the native profile preflight now.
    bool ShorterSurvivalCastable = false;
    // Pre-Mangle lead: keep Heart Strike and Rune Strike off the runes and
    // global cooldowns until Death Strike's Blood Shield will last to the
    // seize and Bone Shield is refreshed.
    bool RuneHold = false;
    // Seized by Mangle: Heart Strike waits unless a spare Blood rune pays it
    // (HoldSeizedHeartStrike).  Set without the Mangle timer: the seizure
    // aura alone proves it.
    bool SeizedHeartStrikeHold = false;
    uint32 BoneShieldCooldownMs = 0;

    char const* RejectReason(uint32 spellId) const;
};

// 35% emergency: while Icebound Fortitude would not be back for the next
// Mangle, a castable Vampiric Blood or Rune Tap is spent instead (Death
// Strike already outranks all three in every balance mode).  With neither,
// the existing BossHitDefensiveReservationReason release stands.
inline char const* IceboundEmergencyKeptReason(Plan const& plan)
{
    if (!plan.Active)
        return nullptr;
    return BotRaidCooldownReservation::BossHitEmergencyDefensiveKeptReason(
        { true, plan.Timer.HitInProgress }, plan.Timer.DueInMs,
        PreMangleLeadMs(IceboundFortitudeSpell), plan.HealthPct,
        plan.IceboundCooldownMs, plan.ShorterSurvivalCastable);
}

// The ordinary 70% Vampiric Blood row waits while Vampiric Blood spent now
// would not be back for the next Mangle's pre-cast (1 min cooldown + 1.5 s
// lead, the "~60 s" horizon).  Released at 35% health or less, while the
// Mangle is in progress and without a native timer.  The Mangle helper casts
// it at the pre-cast point when Icebound Fortitude cannot.
inline char const* VampiricBloodReservedReason(Plan const& plan)
{
    if (!plan.Active || plan.Timer.HitInProgress
        || plan.HealthPct <= BotRaidCooldownReservation::BossHitEmergencyHealthPct
        || BotRaidCooldownReservation::ReturnsBeforeNextBigHit(plan.Timer.DueInMs,
            plan.VampiricBloodCooldownMs, PreMangleLeadMs(VampiricBloodSpell)))
        return nullptr;
    return "magmaw_mangle_vampiric_blood_reserved";
}

// Only inside the pre-Mangle lead (6 s, the tank is Magmaw's victim and not
// yet seized): the hold ends at the seize.  It also ends once a Blood Shield
// will still be up when Mangle lands (a Death Strike landed) and Bone Shield
// needs no refresh.  Bone Shield is pending only while its own cooldown is
// ready and it has fewer than 3 charges.
inline bool HoldRuneSpenders(std::optional<DefensiveWindow> const& window,
    uint32 bloodShieldRemainingMs, bool boneShieldRefreshPending)
{
    if (!window || window->Trigger != DefensiveTrigger::PreMangleLead)
        return false;
    bool const bloodShieldAtSeize = bloodShieldRemainingMs
        && bloodShieldRemainingMs >= window->RemainingMs;
    return !bloodShieldAtSeize || boneShieldRefreshPending;
}

// The ordinary Bone Shield row (maintain aura 49222, no early refresh, at 90%
// health or less) fires only once the aura is gone.  In smoke kill
// 2c0ed2d8-k1 it fired at 54.3 s with Mangle 35.5 s away: its 1 min cooldown
// was still running at the 89.8 s seize, the charges ran out at 89.6 s and
// Mangle landed with no Bone Shield.  The tank had no Bone Shield from the
// pull to 54.3 s either (Magmaw's melee after the target modifiers 0.883 of
// the attacker amount, 0.707 = 0.883 x 0.8 from 54.3 s) and stayed at 64% or
// more before every hit.  Mirror of the Vampiric Blood hold: the row waits
// while Bone Shield cast now would not be back for the helper's 6 s pre-cast
// (1 min cooldown + 6 s lead), so the helper refreshes it to 6 charges for
// the seize.  Released at 35% health or less, while the Mangle is in progress
// and without a native timer; the helper's pre-cast is never held.
inline char const* BoneShieldReservedReason(Plan const& plan)
{
    if (!plan.Active || plan.Timer.HitInProgress
        || plan.HealthPct <= BotRaidCooldownReservation::BossHitEmergencyHealthPct
        || BotRaidCooldownReservation::ReturnsBeforeNextBigHit(plan.Timer.DueInMs,
            plan.BoneShieldCooldownMs, PreMangleLeadMs(BoneShieldSpell)))
        return nullptr;
    return "magmaw_mangle_bone_shield_reserved";
}

// Heart Strike while Mangle holds the tank (error ledger TANK-002).
// 2026_09_23_40 held it on the seat aura for the whole seizure: with Blood
// Rites, Heart Strike had eaten the Death runes Death Strike needed
// (bundle1-b8a539b, 5 Heart Strikes, no Death Strike, two deaths).  Heart
// Strike costs one Blood rune, and Spell::TakeRunePower pays with a ready rune
// of the exact type before any Death rune; Death Strike (Frost + Unholy) can
// never use a Blood rune.  A spare ready Blood rune therefore costs Death
// Strike nothing.  In 2c0ed2d8-k1 the seized tank cast one Death Strike and
// two Rune Strikes in 11 s (Rune Tap took the first Blood rune) while Heart
// Strike was rejected 136 times.
// Admitted while seized only when Death Strike itself cannot be cast now (a
// castable Death Strike outranks it in every balance mode anyway) and a ready
// Blood rune is left after keeping one for a castable Rune Tap (off the GCD,
// 1 Blood rune, the seized tank's self-heal).  Death runes stay for Death
// Strike; Icy Touch and Plague Strike keep their seat-aura rows.
inline bool HoldSeizedHeartStrike(bool seized, bool deathStrikeCastable,
    uint8 readyBloodRunes, bool runeTapCastable)
{
    if (!seized)
        return false;
    uint8 const keptForRuneTap = runeTapCastable ? 1 : 0;
    return deathStrikeCastable || readyBloodRunes <= keptForRuneTap;
}

inline char const* Plan::RejectReason(uint32 spellId) const
{
    switch (spellId)
    {
        case IceboundFortitudeSpell:
            return IceboundEmergencyKeptReason(*this);
        case VampiricBloodSpell:
            return VampiricBloodReservedReason(*this);
        case BoneShieldSpell:
            return BoneShieldReservedReason(*this);
        case HeartStrikeSpell:
            if (SeizedHeartStrikeHold)
                return "magmaw_mangle_seized_heart_strike_hold";
            return RuneHold ? "magmaw_mangle_lead_death_strike_hold" : nullptr;
        case RuneStrikeSpell:
            return RuneHold ? "magmaw_mangle_lead_death_strike_hold" : nullptr;
        default:
            return nullptr;
    }
}

// Native observation, BotWorldPopulationMgrMagmawMangleDefensive.cpp.  Only a
// tank role on the engaged Magmaw encounter gets an active plan; the seized
// Heart Strike hold needs only the tank role and its own Mangle aura.
// Vampiric Blood, Rune Tap and Death Strike count as castable when their
// profile candidate passed the native preflight (spellbook, cooldown, running
// aura, rune cost with modifiers such as Will of the Necropolis) and is not
// suppressed for this resolution.  Ready Blood runes are the native rune
// state (BotBloodDecisionObservation::ObserveReadyRunes).
Plan Observe(Player const* bot, std::string_view role, Blackboard const* board,
    std::vector<BotActionCandidate> const& candidates, uint32 excludedSpellId,
    uint32 policyExcludedSpellId);
}

#endif
