#ifndef TRINITY_BOT_CONTROLLER_H
#define TRINITY_BOT_CONTROLLER_H

#include "Bots/BotActionExecutor.h"
#include "Bots/HealerBotPolicy.h"
#include "Bots/HolyPaladinResolver.h"
#include "ObjectGuid.h"
#include <memory>
#include <string>

class Player;

class BotController
{
public:
    BotController(ObjectGuid ownerGuid, ObjectGuid botGuid, BotRole role);

    ObjectGuid GetOwnerGuid() const { return _ownerGuid; }
    ObjectGuid GetBotGuid() const { return _botGuid; }
    BotMovementMode GetMovementMode() const { return _movementMode; }
    BotRole GetRole() const { return _role; }
    bool IsRecording() const { return _recording; }

    void SetMovementMode(BotMovementMode mode);
    void SetRecording(bool recording);
    void Update(uint32 diff, BotActionExecutor& executor, Player* owner, Player* bot);
    std::string GetStatus(Player const* owner, Player const* bot) const;

private:
    HealerFrame BuildFrame(Player* owner, Player* bot, BotRecentEvents const& recentEvents) const;
    void RecordFrame(HealerFrame const& frame, HealerDecision const& decision, ResolvedBotAction const* action, BotActionResult result, Player* owner, Player* bot) const;

    ObjectGuid _ownerGuid;
    ObjectGuid _botGuid;
    BotRole _role;
    BotMovementMode _movementMode = BotMovementMode::Follow;
    uint32 _updateTimer = 0;
    bool _recording = false;
    mutable uint32 _sequence = 0;
    std::unique_ptr<HealerBotPolicy> _policy;
    HolyPaladinResolver _resolver;
};

#endif
