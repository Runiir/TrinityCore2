#ifndef TRINITY_BOT_OMNOTRON_PET_SHIELD_GUARD_H
#define TRINITY_BOT_OMNOTRON_PET_SHIELD_GUARD_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronFacts.h"

// A Felguard's running Felstorm next to a shielded construct (BWD 10N round 4).
// In round 3 (blackwing_descent_10n-r03-a3864fcf6d acb506 and 6a0efb), Static
// Shock (79912) hit 2-3 players about once a second for 6 s: 12 and 17 hits,
// 280-400k damage and, in acb506, two damage-dealer deaths at 149.6 s. Every
// burst followed a Felstorm tick on Electron under Unstable Shield. The
// whirl (89753, 8 yd around the pet) keeps hitting whatever stands beside the
// pet for its 6 s, even after the construct next to it raises its shield. A
// start-time guard cannot stop a whirl that is already running.
// The owner cancels the pet's Felstorm aura with the client's pet
// cancel-aura request (CMSG_PET_CANCEL_AURA), as a player right-clicks the
// pet buff. Felstorm 89751 is a positive self aura without
// SPELL_ATTR0_CANT_CANCEL. Every shield punishes the whirl: Static Shock,
// Soaked In Poison on the pet, Converted Power stacks, and a Barrier break
// into Backdraft.
namespace BotEncounter::Omnotron
{
inline constexpr uint32 FelguardEntry = 17252;
inline constexpr uint32 FelstormAura = 89751;
// 89753 client SpellRadius 14 (8 yd). Area targets add their own size. The
// pet keeps chasing its victim while it whirls, so one yard of travel is added.
inline constexpr float FelstormRadius = 8.0f;
inline constexpr float FelstormPetTravel = 1.0f;
inline constexpr float FelstormShieldReach = FelstormRadius + ConstructBoundingRadius
    + FelstormPetTravel;

// True when a whirl centred at petPosition reaches an active construct whose
// shield is up or being cast.
inline bool FelstormReachesShieldedConstruct(EncounterFacts const& facts,
    Vector3 const& petPosition)
{
    for (ConstructFact const& fact : facts.Constructs)
        if (fact.Active && fact.Shielded() && fact.Actor->Alive
            && PlanarDistance(fact.Actor->Position, petPosition) <= FelstormShieldReach)
            return true;
    return false;
}
}

#endif
