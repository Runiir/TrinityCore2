#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_RETURN_TRASH_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_RETURN_TRASH_H

#include "Bots/BotValidationRouteRecoveryReturn.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Player.h"
#include "Unit.h"

// Server observation for BotValidationRouteRecoveryReturn::ReturnTrashAdmitted:
// a boss node's trash gates (TrashThreatControl, TankFocusAssist) let a member
// that is walking back after a wipe (its return memory's verdict this tick)
// fight a hostile that attacks a raid member (or a raid member's pet) far
// from the node's anchor, as between any two nodes, and its pack mates. An
// admitted hostile stays admitted while it lives and stays in combat, until
// the return ends; each admission refreshes the return clock's bounded trash
// pause.
namespace BotValidationRouteRecoveryReturn
{
inline bool AdmitsReturnTrash(Memory& memory, Player const* bot, Unit const* hostile)
{
    if (!memory.Returning || !bot || !hostile)
        return false;
    std::uint64_t const guid = hostile->GetGUID().GetRawValue();
    bool admitted = RememberedReturnTrash(memory, guid) && hostile->IsAlive()
        && hostile->IsInCombat();
    if (!admitted)
    {
        Unit const* victim = hostile->GetVictim();
        Player const* attacked = victim ? victim->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;
        admitted = ReturnTrashAdmitted(memory.Returning,
            attacked && (attacked == bot || attacked->IsInSameRaidWith(bot)),
            hostile->GetExactDist(memory.AnchorX, memory.AnchorY, memory.AnchorZ),
            ReturnTrashPackMate(memory, hostile->GetPositionX(), hostile->GetPositionY(),
                hostile->GetPositionZ()));
    }
    if (admitted)
        AdmitReturnTrash(memory, guid, BotWorldPopulationMgrSpellSemantics::NowMs(),
            hostile->GetPositionX(), hostile->GetPositionY(), hostile->GetPositionZ());
    return admitted;
}
}

#endif
