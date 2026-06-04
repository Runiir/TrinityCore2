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
    void SetMoveTarget(float x, float y, float z);
    void SetRecording(bool recording);
    void Update(uint32 diff, BotActionExecutor& executor, Player* owner, Player* bot);
    std::string GetStatus(Player const* owner, Player const* bot) const;

private:
    HealerFrame BuildFrame(Player* owner, Player* bot, BotRecentEvents const& recentEvents) const;
    BotMovementFrame BuildMovementFrame(Player* owner, Player* bot, uint32 diff) const;
    void ApplyMovementPolicy(BotActionExecutor& executor, Player* owner, Player* bot, BotMovementFrame const& movementFrame);
    void RecordFrame(HealerFrame const& frame, HealerDecision const& decision, ResolvedBotAction const* action, BotActionResult result, Player* owner, Player* bot) const;
    void RecordMovementFrame(BotMovementFrame const& frame, char const* policyMode, char const* intent, char const* action, bool valid, Player* owner, Player* bot) const;

    ObjectGuid _ownerGuid;
    ObjectGuid _botGuid;
    BotRole _role;
    BotMovementMode _movementMode = BotMovementMode::Follow;
    BotMovementTarget _movementTarget;
    uint32 _updateTimer = 0;
    bool _recording = false;
    mutable uint32 _sequence = 0;
    mutable float _lastX = 0.0f;
    mutable float _lastY = 0.0f;
    mutable float _lastZ = 0.0f;
    mutable uint32 _lastProgressMs = 0;
    mutable float _stuckScore = 0.0f;
    std::unique_ptr<HealerBotPolicy> _policy;
    HolyPaladinResolver _resolver;
};

#endif
