#ifndef TRINITY_BOT_MALORIAK_ADD_SWITCH_H
#define TRINITY_BOT_MALORIAK_ADD_SWITCH_H

#include "Bots/BotEncounterOffenseRestriction.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakDuties.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFacts.h"
#include "ObjectGuid.h"


// The add switch at the native edge (the plan's AddSwitchRestricts; user
// tactic 2026-09-26, threshold 50% since 2026-09-27: from the switch health
// every damage dealer kills Aberrations until
// the chambers are empty, the Blood DK main tank alone stays on Maloriak).
// The dispatch's route-authority hook (SubmitMaloriakRouteAuthority) runs
// after ConfigureValidationRouteCombatAuthority clears the bot's restriction,
// every tick, and while the latched switch (BotMaloriakLatches.h) holds it
//  - restricts Maloriak for the bot (AddSwitchRestriction): no cast, DoT or
//    area spell on him, and the bot's pet, guardians and totems follow that
//    authority (PetAI, the shaman elemental and Doomguard scripts, UnitAI
//    casts and every controlled unit's melee), so they turn to the adds;
//  - holds the bot's offensive cooldowns, guardian summons, combat potions
//    and raid haste for phase two (BotEncounterCooldownHold);
//  - stops a cast already running that would still reach him (aimed at him,
//    or a hostile area such as Blizzard or Hellfire over him; generic,
//    channeled or auto-repeat) and sends the pet back if it attacks him;
//  - keeps the shaman's Greater Fire Elemental's area spells off him
//    (BotEncounterOffense::SetGuardianAreaSparing).
// DoTs already ticking are left alone (the tactic allows them). In the r05
// holds, with only the target cleared, Maloriak still took 62-73k DPS:
// casts in flight, the Greater Fire Elemental, a Doomguard, the Felguard, a
// Tentacle of the Old Ones, and DoT ticks (about 55%).
namespace BotEncounter::Maloriak
{
inline BotEncounterOffense::OffenseRestriction AddSwitchRestriction()
{
    return { { BossEntry }, {} };
}

// One Arcane Storm interrupt or taunt on Maloriak stays allowed for a restricted
// bot, for its native cast only (BotEncounterOffense::SingleCastAllowance).
inline bool AddSwitchAllowanceApplies(bool restricted, uint32 targetEntry)
{
    return restricted && targetEntry == BossEntry;
}

// A cast still running when the switch holds (hook, restricted bots only):
// stopped when it is hostile and would reach the boss, aimed at him or as an
// area over him (a Hellfire the bot aims at itself included), whatever its
// explicit target; a helpful spell never. Slot by slot, only the slots that
// reach him.
inline bool AddSwitchStopsCast(bool positive, bool aimedAtBoss, bool areaOverBoss)
{
    return !positive && (aimedAtBoss || areaOverBoss);
}
}

#endif
