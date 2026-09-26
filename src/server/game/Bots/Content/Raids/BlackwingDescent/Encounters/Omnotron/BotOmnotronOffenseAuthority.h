#ifndef TRINITY_BOT_OMNOTRON_OFFENSE_AUTHORITY_H
#define TRINITY_BOT_OMNOTRON_OFFENSE_AUTHORITY_H

#include "Bots/BotEncounterOffenseRestriction.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronFacts.h"
#include <vector>

// Per-bot offensive authority over the four constructs, applied through the
// shared current-encounter restriction (BotRaidAreaAuthority::
// SetCurrentEncounterRestrictions, via BotEncounterOffenseRestriction.h):
// every construct entry is restricted and only the plan's active, unshielded
// constructs are allowed. Direct casts on a restricted construct are refused
// and area spells are refused next to one (HasNearbyProtectedEncounterTarget).
//
// A single interrupt or taunt may still target a shielded construct. That
// exception is scoped to the one native cast (SingleCastAllowance) and never
// enters the tick's allowed set: an allowed GUID lifts the restriction for
// every offense path of the bot, including area spells beside it.
namespace BotEncounter::Omnotron
{
using BotEncounterOffense::OffenseRestriction;
using BotEncounterOffense::Allows;
using BotEncounterOffense::ApplyOffenseRestriction;
// Of the four shields only Power Conversion procs on the allowance's
// no-damage hit (spell_proc 79729, SpellTypeMask 0): one Converted Power
// stack, a live signal. Unstable Shield and Poison Soaked Shell have
// SpellTypeMask 1 (damage) rows and do not proc.
using BotEncounterOffense::SingleCastAllowance;

inline OffenseRestriction BuildOffenseRestriction(std::vector<ObjectGuid> const& allowed)
{
    OffenseRestriction restriction;
    restriction.Entries = { ArcanotronEntry, MagmatronEntry, ElectronEntry, ToxitronEntry };
    for (ObjectGuid guid : allowed)
        if (!guid.IsEmpty())
            restriction.AllowedGuids.push_back(guid.GetRawValue());
    return restriction;
}
}

#endif
