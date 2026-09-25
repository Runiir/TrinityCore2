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
    // Pre-pull hold for everyone but the pull tank.
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
