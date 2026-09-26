#ifndef TRINITY_BOT_MALORIAK_PLAN_H
#define TRINITY_BOT_MALORIAK_PLAN_H

#include "Bots/BotNativeActionIntent.h"
#include "ObjectGuid.h"

#include <optional>
#include <string_view>

namespace BotEncounter
{
// One bot's Maloriak proposal for one blackboard snapshot. Every field is a
// request for an ordinary native action (target, cast, move); the runtime
// dispatch revalidates each one before submission.
struct AdaptiveMaloriakPlan
{
    bool OwnsNode = false;
    // The observed boss, and whether its next Release Aberrations should be
    // allowed to finish (Maloriak::ReleaseAdmitted). The dispatch publishes
    // it as an interrupt veto so generic rotation interrupts cannot cut an
    // admitted release (in the r03 attempt all of them were cut, so the 25%
    // Release All Minions freed 18 Aberrations and 2 Prime Subjects at once).
    ObjectGuid Boss;
    bool ReleaseAdmitted = false;
    // The phase-two push hold condition, the same for every bot (tanks
    // included), so the dispatch can latch its start and cap its length.
    bool PushHoldWindow = false;
    // Offense hold: pre-pull (everyone but the pull tank), the off-tank's
    // add-spot wait, a blocked melee ring, or the phase-two push hold.
    bool SuppressOffense = false;
    std::string_view SuppressReason;
    ObjectGuid DamageTarget;
    // Boss cast this bot is assigned to interrupt (Arcane Storm or Release
    // Aberrations) and the spell being interrupted.
    ObjectGuid InterruptTarget;
    uint32 InterruptSpellId = 0;
    std::string_view InterruptLane;
    // Remedy on the boss: purge, spellsteal or offensive dispel.
    ObjectGuid DispelTarget;
    // Tank taunt of the boss or of a loose add.
    ObjectGuid TauntTarget;
    // Healer focus: frozen, Consuming Flames or Biting Chill player.
    ObjectGuid PriorityHealTarget;
    // Raid haste owner in the phase-two burn window.
    bool LustWindow = false;
    std::string_view Phase;
    std::string_view Duty;
    std::optional<BotNativeAction::Candidate> Movement;
};
}

#endif
