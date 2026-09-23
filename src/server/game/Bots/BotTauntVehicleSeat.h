#ifndef TRINITY_BOT_TAUNT_VEHICLE_SEAT_H
#define TRINITY_BOT_TAUNT_VEHICLE_SEAT_H

#include "Unit.h"

namespace BotTauntVehicleSeat
{
constexpr char const* RejectReason = "seat_holder_victim_out_of_reach";

// A tank held in a rooted creature's own vehicle seat does not taunt that
// creature while its victim is out of its melee reach.  Magmaw's Mangle seats
// the tank in his jaws and wipes its threat.  Rooted Magmaw then cannot swing
// at an out-of-reach victim, so a taunt would only pull his melee onto the
// seized tank.  When the victim is another player inside his reach, the taunt
// protects that player: the Blizzlike one-tank Mangle play.  Everything
// lifts when the seat releases the tank.
inline bool TauntWouldOnlyPullHolderOntoSeat(Unit const* bot, Unit const* target)
{
    if (!bot || !target || bot->GetVehicleBase() != target
        || !target->HasUnitState(UNIT_STATE_ROOT))
        return false;
    Unit const* victim = target->GetVictim();
    return victim && victim != bot && !target->IsWithinMeleeRange(victim);
}
}

#endif
