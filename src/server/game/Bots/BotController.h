#ifndef TRINITY_BOT_CONTROLLER_H
#define TRINITY_BOT_CONTROLLER_H

#include "Bots/BotActionExecutor.h"
#include "Bots/BotClassSpecActionProfile.h"
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
    BotController(ObjectGuid ownerGuid, ObjectGuid botGuid, BotRole role, std::string runtimeRole, std::string classSpec);

    ObjectGuid GetOwnerGuid() const { return _ownerGuid; }
    ObjectGuid GetBotGuid() const { return _botGuid; }
    BotMovementMode GetMovementMode() const { return _movementMode; }
    BotRole GetRole() const { return _role; }
    std::string const& GetRuntimeRole() const { return _runtimeRole; }
    std::string const& GetClassSpec() const { return _classSpec; }
    bool IsRecording() const { return _recording; }

    void SetMovementMode(BotMovementMode mode);
    void SetMoveTarget(float x, float y, float z);
    void SetCombatTarget(ObjectGuid targetGuid);
    void ClearCombatTarget();
    void SetRecording(bool recording);
    void Update(uint32 diff, BotActionExecutor& executor, Player* owner, Player* bot);
    std::string GetStatus(Player const* owner, Player const* bot) const;

private:
    HealerFrame BuildFrame(Player* owner, Player* bot, BotRecentEvents const& recentEvents) const;
    BotMovementFrame BuildMovementFrame(Player* owner, Player* bot, uint32 diff) const;
    BotCombatState BuildCombatState(Player* owner, Player* bot, BotRecentEvents const& recentEvents) const;
    BotProfessionFrame BuildProfessionFrame(Player* owner, Player* bot) const;
    BotCombatDecision DecideSoloCombat(BotCombatState const& state) const;
    ResolvedCombatAction ResolveSoloCombat(BotCombatDecision const& decision, BotCombatState const& state) const;
    BotActionCandidate const* SelectProfileCombatAction(Player* bot, Unit* target, BotCombatState const& state, BotClassSpecActionProfile const& profile, std::vector<BotActionCandidate>& candidates) const;
    ResolvedCombatAction ResolveProfileCombat(BotCombatDecision const& decision, BotCombatState const& state, Player* bot, Unit* target) const;
    bool TryResolveHealerAction(BotActionExecutor& executor, Player* owner, Player* bot, BotRecentEvents const& recentEvents, bool shouldRecord, BotMovementFrame const& movementFrame);
    void ApplyMovementPolicy(BotActionExecutor& executor, Player* owner, Player* bot, BotMovementFrame const& movementFrame);
    void RecordFrame(HealerFrame const& frame, HealerDecision const& decision, ResolvedBotAction const* action, BotActionResult result, Player* owner, Player* bot) const;
    void RecordMovementFrame(BotMovementFrame const& frame, char const* policyMode, char const* intent, char const* action, bool valid, Player* owner, Player* bot) const;
    void RecordCombatFrame(BotCombatState const& frame, BotCombatDecision const& decision, ResolvedCombatAction const& action, BotActionResult result, Player* owner, Player* bot) const;
    void RecordProfessionFrame(BotProfessionFrame const& frame, Player* owner, Player* bot) const;

    ObjectGuid _ownerGuid;
    ObjectGuid _botGuid;
    BotRole _role;
    std::string _runtimeRole;
    std::string _classSpec;
    BotMovementMode _movementMode = BotMovementMode::Follow;
    BotMovementTarget _movementTarget;
    ObjectGuid _combatTargetGuid;
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
