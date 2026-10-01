#ifndef TRINITY_BOT_RAID_HEAL_TRIAGE_LIVE_H
#define TRINITY_BOT_RAID_HEAL_TRIAGE_LIVE_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotRaidHealTriage.h"

#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <optional>

// The live input of BotRaidHealTriage::SelectFromBoard for one healer: the
// native heal range and, for the ranked candidates only, the native line of
// sight. The snapshot walk (players, attackers of a tank) is the pure part.
namespace BotRaidHealTriage
{
inline std::optional<Choice> SelectForHealer(Player const* healer,
    BotEncounter::Blackboard const& board)
{
    return SelectFromBoard(board,
        [healer](ObjectGuid guid)
        {
            Unit const* unit = ObjectAccessor::GetUnit(*healer, guid);
            return unit && unit->IsInWorld()
                && healer->IsWithinDistInMap(unit, HealRangeYards);
        },
        [healer](uint64 guid)
        {
            Unit const* unit = ObjectAccessor::GetUnit(*healer, ObjectGuid(guid));
            return unit && healer->IsWithinLOSInMap(unit);
        });
}
}

#endif
