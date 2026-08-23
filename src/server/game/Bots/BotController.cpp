#include "Bots/BotController.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotDatasetEvent.h"
#include "Bots/BotMgr.h"
#include "Config.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupReference.h"
#include "Log.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "DataStores/DBCStructure.h"
#include "DungeonFinding/LFG.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "Transport.h"
#include "Spell.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include <algorithm>
#include <boost/filesystem.hpp>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <map>
#include <sstream>
#include <utility>

namespace
{
std::string JsonEscape(std::string const& value)
{
    std::ostringstream escaped;
    for (char c : value)
    {
        switch (c)
        {
            case '\\': escaped << "\\\\"; break;
            case '"': escaped << "\\\""; break;
            case '\b': escaped << "\\b"; break;
            case '\f': escaped << "\\f"; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20)
                    escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0') << uint32(static_cast<unsigned char>(c)) << std::dec;
                else
                    escaped << c;
                break;
        }
    }

    return escaped.str();
}

uint64 PlayerBotNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

BotCombatArchetype CombatArchetypeForClass(uint8 classId, std::string const& runtimeRole, std::string const& classSpec = "")
{
    if (runtimeRole == "tank")
        return BotCombatArchetype::TankLikeMelee;
    if (runtimeRole == "healer")
        return BotCombatArchetype::HealerSolo;
    if (classSpec == "enhancement_shaman")
        return BotCombatArchetype::MeleeDps;

    switch (classId)
    {
        case CLASS_HUNTER:
            return BotCombatArchetype::RangedPhysical;
        case CLASS_MAGE:
        case CLASS_PRIEST:
        case CLASS_SHAMAN:
            return BotCombatArchetype::RangedCaster;
        case CLASS_WARLOCK:
            return BotCombatArchetype::PetClass;
        default:
            return BotCombatArchetype::MeleeDps;
    }
}
}

BotController::BotController(ObjectGuid ownerGuid, ObjectGuid botGuid, BotRole role)
    : _ownerGuid(ownerGuid), _botGuid(botGuid), _role(role), _runtimeRole(NormalizeBotRole(ToString(role))), _policy(new RuleHealerBotPolicy())
{
}

BotController::BotController(ObjectGuid ownerGuid, ObjectGuid botGuid, BotRole role, std::string runtimeRole, std::string classSpec)
    : _ownerGuid(ownerGuid), _botGuid(botGuid), _role(role), _runtimeRole(NormalizeBotRole(runtimeRole.empty() ? ToString(role) : runtimeRole)), _classSpec(std::move(classSpec)), _policy(new RuleHealerBotPolicy())
{
}

uint64 BotController::PlayerBotRunId()
{
    int32 runId = sConfigMgr->GetIntDefault("PlayerBot.RunId", 1);
    return runId > 0 ? uint64(runId) : 0;
}

void BotController::SetMovementMode(BotMovementMode mode)
{
    _movementMode = mode;
}

void BotController::SetMoveTarget(float x, float y, float z)
{
    _movementMode = BotMovementMode::MoveTo;
    _movementTarget.X = x;
    _movementTarget.Y = y;
    _movementTarget.Z = z;
    _movementTarget.Active = true;
}

void BotController::SetCombatTarget(ObjectGuid targetGuid)
{
    _combatTargetGuid = targetGuid;
}

void BotController::ClearCombatTarget()
{
    _combatTargetGuid.Clear();
}

void BotController::SetRecording(bool recording)
{
    _recording = recording;
}

void BotController::Update(uint32 diff, BotActionExecutor& executor, Player* owner, Player* bot)
{
    if (_updateTimer > diff)
    {
        _updateTimer -= diff;
        return;
    }

    uint32 updateMs = std::max(100, sConfigMgr->GetIntDefault("PlayerBot.UpdateMs", 500));
    _updateTimer = updateMs;

    if (!owner || !bot || !bot->IsAlive())
        return;

    BotMovementFrame movementFrame = BuildMovementFrame(owner, bot, updateMs);
    bool shouldRecord = _recording || sConfigMgr->GetBoolDefault("PlayerBot.Record.Enable", false);
    if (shouldRecord)
        RecordProfessionFrame(BuildProfessionFrame(owner, bot), owner, bot);

    if (_movementMode == BotMovementMode::Stop)
    {
        ApplyMovementPolicy(executor, owner, bot, movementFrame);
        if (shouldRecord)
            RecordMovementFrame(movementFrame, ToString(_movementMode), "stop", "stop", true, owner, bot);
        return;
    }

    BotRecentEvents recentEvents = sBotMgr->ConsumeRecentEvents(_botGuid);
    BotCombatState combatState = BuildCombatState(owner, bot, recentEvents);

    if (!_combatTargetGuid.IsEmpty() || combatState.InCombat || combatState.TargetLootable)
    {
        uint32 combatUpdateMs = _runtimeRole == "dps" && _classSpec == "frost_death_knight" ? 50 : 100;
        _updateTimer = std::min(_updateTimer, combatUpdateMs);
        BotCombatDecision combatDecision = DecideSoloCombat(combatState);
        Unit* target = combatState.TargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, combatState.TargetGuid);
        BotActionResult combatResult = BotActionResult::NoAction;
        ResolvedCombatAction combatAction;
        bool healerCommitted = false;
        bool combatAttempted = false;
        _decisionKernel.Begin(PlayerBotNowMs());

        if (_runtimeRole == "healer")
        {
            BotActionArbitration::Candidate healer;
            healer.Key = "attached.healer_profile";
            healer.Source = "db_class_spec_profile";
            healer.ActionPriority = BotActionArbitration::Priority::Support;
            healer.UtilityScore = 1.0f;
            healer.RequiredResources = BotActionArbitration::Uses(
                BotActionArbitration::Resource::GlobalCooldown,
                BotActionArbitration::Resource::Cast,
                BotActionArbitration::Resource::Movement,
                BotActionArbitration::Resource::Target);
            healer.Attempt = [&]()
            {
                healerCommitted = TryResolveHealerAction(executor, owner, bot,
                    recentEvents, shouldRecord, movementFrame);
                return healerCommitted
                    ? BotActionArbitration::Outcome::Committed("healer_action_committed")
                    : BotActionArbitration::Outcome::NotApplicable("no_valid_healer_action");
            };
            _decisionKernel.Submit(std::move(healer));
        }

        BotActionArbitration::Candidate combat;
        combat.Key = "attached.profile_combat";
        combat.Source = "db_class_spec_profile";
        combat.ActionPriority = combatDecision.Intent == BotCombatIntent::Recover
            ? BotActionArbitration::Priority::Survival
            : BotActionArbitration::Priority::TrainedDamage;
        combat.UtilityScore = combatState.TargetCastingSpellId ? 2.0f : 1.0f;
        combat.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Movement,
            BotActionArbitration::Resource::Target);
        combat.Attempt = [&]()
        {
            combatAttempted = true;
            bool hadQueuedAction = _queuedCombatAction.Valid && _queuedCombatAction.SpellId;
            if (hadQueuedAction)
                combatAction = _queuedCombatAction;
            if (!TryExecuteQueuedCombatAction(executor, owner, bot, combatResult))
            {
                combatAction = ResolveProfileCombat(combatDecision, combatState, bot, target);
                combatResult = executor.ExecuteCombat(owner, bot, combatAction);
                if (combatResult == BotActionResult::Casting || combatResult == BotActionResult::GlobalCooldown)
                {
                    _queuedCombatAction = combatAction;
                    _queuedCombatActionMs = 1500;
                }
            }
            return BotActionArbitration::FromBotActionResult(combatResult);
        };
        _decisionKernel.Submit(std::move(combat));

        BotActionArbitration::Candidate movement;
        movement.Key = "attached.movement";
        movement.Source = "movement_mode_adapter";
        movement.ActionPriority = _movementMode == BotMovementMode::MoveSafe
                || _movementMode == BotMovementMode::Unstuck
                || movementFrame.StuckScore >= 1.0f
            ? BotActionArbitration::Priority::Survival
            : BotActionArbitration::Priority::CombatMovement;
        movement.UtilityScore = movementFrame.NearbyHazard ? 3.0f : 0.5f;
        movement.RequiredResources = BotActionArbitration::Uses(BotActionArbitration::Resource::Movement);
        movement.Attempt = [&]()
        {
            return ApplyMovementPolicy(executor, owner, bot, movementFrame)
                ? BotActionArbitration::Outcome::Committed("movement_policy_applied")
                : BotActionArbitration::Outcome::NotApplicable("movement_lease_preserved");
        };
        _decisionKernel.Submit(std::move(movement));
        _decisionKernel.Resolve();
        _lastDecisionKernelTraceJson = _decisionKernel.LastResolutionJson();

        if (combatDecision.Intent == BotCombatIntent::Loot && combatResult == BotActionResult::Ok)
            ClearCombatTarget();

        if (shouldRecord && combatAttempted && !healerCommitted)
        {
            RecordCombatFrame(combatState, combatDecision, combatAction, combatResult, owner, bot);
            RecordMovementFrame(movementFrame, ToString(_movementMode), ToString(combatDecision.Intent), combatAction.DebugName.c_str(), combatResult != BotActionResult::Disabled, owner, bot);
        }

        return;
    }

    _decisionKernel.Begin(PlayerBotNowMs());
    BotActionArbitration::Candidate movement;
    movement.Key = "attached.movement";
    movement.Source = "movement_mode_adapter";
    movement.ActionPriority = _movementMode == BotMovementMode::MoveSafe
            || _movementMode == BotMovementMode::Unstuck
            || movementFrame.StuckScore >= 1.0f
        ? BotActionArbitration::Priority::Survival
        : BotActionArbitration::Priority::RouteMovement;
    movement.UtilityScore = movementFrame.NearbyHazard ? 3.0f : 0.5f;
    movement.RequiredResources = BotActionArbitration::Uses(BotActionArbitration::Resource::Movement);
    movement.Attempt = [&]()
    {
        return ApplyMovementPolicy(executor, owner, bot, movementFrame)
            ? BotActionArbitration::Outcome::Committed("movement_policy_applied")
            : BotActionArbitration::Outcome::NotApplicable("movement_lease_preserved");
    };
    _decisionKernel.Submit(std::move(movement));
    _decisionKernel.Resolve();
    _lastDecisionKernelTraceJson = _decisionKernel.LastResolutionJson();

    HealerFrame frame = BuildFrame(owner, bot, recentEvents);
    if (_runtimeRole != "healer")
    {
        if (shouldRecord)
        {
            HealerDecision decision;
            ResolvedBotAction action;
            action.DebugName = "generic_class_controller";
            RecordFrame(frame, decision, &action, BotActionResult::NoAction, owner, bot);
            RecordMovementFrame(movementFrame, ToString(_movementMode), "wait", action.DebugName.c_str(), true, owner, bot);
        }

        return;
    }

    HealerDecision decision = _policy->Decide(frame);
    std::vector<ResolvedBotAction> actions = _resolver.Resolve(decision);

    BotActionResult result = BotActionResult::NoAction;
    ResolvedBotAction const* resolved = nullptr;
    for (ResolvedBotAction const& action : actions)
    {
        if (action.Intent == HealerIntent::MoveSafe)
        {
            executor.MoveFollow(owner, bot);
            result = BotActionResult::Ok;
            resolved = &action;
            break;
        }

        result = executor.Execute(owner, bot, action);
        if (result == BotActionResult::Ok || result == BotActionResult::NoAction)
        {
            resolved = &action;
            break;
        }
    }

    if (shouldRecord)
    {
        RecordFrame(frame, decision, resolved, result, owner, bot);
        RecordMovementFrame(movementFrame, ToString(_movementMode), ToString(decision.Intent), resolved ? resolved->DebugName.c_str() : "wait", result != BotActionResult::Disabled, owner, bot);
    }

    if (sConfigMgr->GetBoolDefault("PlayerBot.Debug", false) && result != BotActionResult::NoAction)
        TC_LOG_DEBUG("entities.unit", "PlayerBot %s decision=%s result=%s", _botGuid.ToString().c_str(), ToString(decision.Intent), ToString(result));
}

std::string BotController::GetStatus(Player const* owner, Player const* bot) const
{
    BotMovementFrame movement = owner && bot ? BuildMovementFrame(const_cast<Player*>(owner), const_cast<Player*>(bot), 0) : BotMovementFrame();
    std::ostringstream ss;
    ss << "{\"bot_guid\":" << _botGuid.GetCounter()
       << ",\"name\":\"" << JsonEscape(bot ? bot->GetName() : "offline")
       << "\",\"role\":\"" << ToString(_role)
       << "\",\"runtime_role\":\"" << JsonEscape(_runtimeRole)
       << "\",\"class_spec_tag\":\"" << JsonEscape(_classSpec.empty() ? ToString(_role) : _classSpec)
       << "\",\"combat_archetype\":\"" << ToString(bot ? CombatArchetypeForClass(bot->getClass(), _runtimeRole, _classSpec) : GetSoloCombatArchetype(_role))
       << "\",\"state\":\"" << (bot && bot->IsInWorld() ? "online" : "offline")
       << "\",\"owner_guid\":" << _ownerGuid.GetCounter()
       << ",\"owner_name\":\"" << JsonEscape(owner ? owner->GetName() : "offline")
       << "\",\"mode\":\"" << ToString(_movementMode)
       << "\",\"recording\":\"" << (_recording ? "on" : "off")
       << "\",\"movement\":{\"distance_to_leader\":" << movement.DistanceToLeader
       << ",\"distance_to_group_center\":" << movement.DistanceToGroupCenter
       << ",\"line_of_sight_to_leader\":" << (movement.LineOfSightToLeader ? "true" : "false")
       << ",\"stuck_score\":" << movement.StuckScore
       << ",\"path_available\":" << (movement.PathAvailable ? "true" : "false")
       << ",\"nearby_hazard\":" << (movement.NearbyHazard ? "true" : "false")
       << ",\"safe_position_available\":" << (movement.SafePositionAvailable ? "true" : "false") << "}"
       << ",\"combat\":{\"target_guid\":" << (_combatTargetGuid.IsEmpty() ? 0 : _combatTargetGuid.GetCounter())
       << ",\"archetype\":\"" << ToString(bot ? CombatArchetypeForClass(bot->getClass(), _runtimeRole, _classSpec) : GetSoloCombatArchetype(_role)) << "\"}"
       << ",\"decision_kernel\":" << _lastDecisionKernelTraceJson
       << "}";
    return ss.str();
}
