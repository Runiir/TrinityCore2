#ifndef TRINITY_BOT_ACTION_EXECUTOR_H
#define TRINITY_BOT_ACTION_EXECUTOR_H

#include "Bots/BotTypes.h"
#include "ObjectGuid.h"
#include <map>

class Player;
class Unit;

class BotActionExecutor
{
public:
    BotActionResult Execute(Player* owner, Player* bot, ResolvedBotAction const& action);
    void MoveFollow(Player* owner, Player* bot);
    void MoveStay(Player* bot);
    void ResetThrottle(ObjectGuid botGuid);

private:
    BotActionResult CheckSpell(Player* owner, Player* bot, Unit* target, uint32 spellId) const;
    bool IsThrottled(ObjectGuid botGuid, uint32 spellId, ObjectGuid targetGuid);
    void RecordFailure(ObjectGuid botGuid, uint32 spellId, ObjectGuid targetGuid);
    void RecordSuccess(ObjectGuid botGuid);

    struct FailureState
    {
        uint32 SpellId = 0;
        ObjectGuid TargetGuid;
        uint8 Count = 0;
        uint32 SuppressMs = 0;
    };

    std::map<ObjectGuid, FailureState> _failures;
};

#endif
