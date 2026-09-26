#ifndef TRINITY_BOT_MALORIAK_PLAN_H
#define TRINITY_BOT_MALORIAK_PLAN_H

#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotEncounterBlackboard.h"
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
    // The observed boss, and whether its Release Aberrations must finish
    // (Maloriak::ReleaseAdmitted: every release in phase one). The dispatch
    // publishes it as an interrupt veto so generic rotation interrupts cannot
    // cut a release (in the r03 attempt all of them were cut, so the 25%
    // Release All Minions freed 18 Aberrations and 2 Prime Subjects at once).
    ObjectGuid Boss;
    bool ReleaseAdmitted = false;
    // The add switch (Maloriak::AddSwitchWindow), the same for every bot, so
    // the dispatch can latch its start and bound its length.
    bool AddSwitchWindow = false;
    // Inside that window the boss is restricted for this bot at the native
    // edge (everyone but the main tank): no cast, DoT or area spell on him,
    // and its pet and guardians follow that authority onto the adds. Its
    // offensive cooldowns wait for phase two, a cast already running on the
    // boss is stopped. The dispatch applies it from its route-authority hook.
    bool AddSwitchRestricts = false;
    // The latched switch ended on its cap (the dispatch logs it once).
    bool AddSwitchCapReleased = false;
    // Offense hold: pre-pull (everyone but the pull tank), the off-tank's
    // add-spot wait, a blocked melee ring, or an add-switch wait (no loose
    // Aberration to kill yet).
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
    // Misdirection (hunter) or Tricks of the Trade (rogue) onto the off-tank
    // for a release, and the spell.
    ObjectGuid ThreatRedirectTarget;
    uint32 ThreatRedirectSpellId = 0;
    // Shaman Frost Shock on a loose Aberration the off-tank has not picked up.
    ObjectGuid SlowTarget;
    // Hunter trap laid at its own feet at TrapPoint: Freeze Trap for an
    // unhit Aberration running at it, Ice Trap otherwise or for the kited
    // pack at the loop's trap corner.
    ObjectGuid TrapTarget;
    uint32 TrapSpellId = 0;
    Vector3 TrapPoint{};
    // The off-tank's Nature's Grasp while it holds Aberrations.
    bool NaturesGrasp = false;
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
