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
bool RotationHasEnoughPower(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    int32 cost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (cost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > cost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(cost);
}

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

uint64 PlayerBotRunId()
{
    int32 runId = sConfigMgr->GetIntDefault("PlayerBot.RunId", 1);
    return runId > 0 ? uint64(runId) : 0;
}

std::string PlayerBotExperimentId()
{
    std::string experimentId = sConfigMgr->GetStringDefault("PlayerBot.ExperimentId", "playerbot");
    return experimentId.empty() ? "playerbot" : experimentId;
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

bool IsHealingCategory(BotCombatActionCategory category)
{
    return category == BotCombatActionCategory::HealFast
        || category == BotCombatActionCategory::HealEfficient
        || category == BotCombatActionCategory::HealAoe
        || category == BotCombatActionCategory::DispelCleanse
        || category == BotCombatActionCategory::ExternalDefensive
        || category == BotCombatActionCategory::Defensive
        || category == BotCombatActionCategory::Mitigation
        || category == BotCombatActionCategory::OffensiveCooldown;
}

float ProfileFollowDistance(BotClassSpecActionProfile const& profile)
{
    if (profile.MinRange > 0.0f)
        return profile.MinRange;
    if (profile.MovementDirective == "ranged")
        return 24.0f;
    if (profile.MovementDirective == "healer_support")
        return 18.0f;
    return 3.5f;
}

uint32 CastTimeMs(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return 0;
    return uint32(std::max<int32>(0, spellInfo->CalcCastTime(bot->getLevel())));
}

bool MeetsCastDirectives(Player const* bot, BotActionProfileSpell const& spell, SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;
    uint32 castTime = CastTimeMs(bot, spellInfo);
    if (spell.RequiresInstantCast && castTime > 0)
        return false;
    if (spell.MaxCastTimeMs && castTime > spell.MaxCastTimeMs)
        return false;
    return true;
}

HealerUnitFrame const* SelectHealerUnit(HealerFrame const& frame, std::string const& selector)
{
    HealerUnitFrame const* selected = nullptr;
    for (HealerUnitFrame const& unit : frame.Party)
    {
        if (!unit.Alive || !unit.Friendly || !unit.LineOfSight)
            continue;

        if (selector == "self")
        {
            if (unit.Guid == frame.BotGuid)
                return &unit;
            continue;
        }

        if (selector == "owner")
        {
            if (unit.Guid == frame.OwnerGuid)
                return &unit;
            continue;
        }

        if (selector == "tank")
        {
            if (!(unit.Role & lfg::PLAYER_ROLE_TANK))
                continue;
            if (!selected || unit.HealthPct < selected->HealthPct)
                selected = &unit;
            continue;
        }

        if (!selected || unit.HealthPct < selected->HealthPct || (unit.IsOwner && unit.HealthPct == selected->HealthPct))
            selected = &unit;
    }
    return selected;
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

BotMovementFrame BotController::BuildMovementFrame(Player* owner, Player* bot, uint32 diff) const
{
    BotMovementFrame frame;
    frame.X = bot->GetPositionX();
    frame.Y = bot->GetPositionY();
    frame.Z = bot->GetPositionZ();
    frame.Orientation = bot->GetOrientation();
    frame.Moving = bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
    frame.Mounted = bot->IsMounted();
    frame.InCombat = bot->IsInCombat() || owner->IsInCombat();
    frame.OnTransport = bot->GetTransport() != nullptr;
    frame.Indoors = false;
    uint32 maxHealth = bot->GetMaxHealth();
    frame.HpPct = maxHealth ? float(bot->GetHealth()) / float(maxHealth) : 0.0f;
    frame.DistanceToLeader = bot->GetExactDist(owner);
    frame.LineOfSightToLeader = bot->IsWithinLOSInMap(owner);
    frame.NearbyHazard = bot->IsFalling() || bot->IsInWater();
    frame.SafePositionAvailable = owner->IsAlive() && bot->GetMap() == owner->GetMap() && !frame.NearbyHazard;

    float centerX = 0.0f;
    float centerY = 0.0f;
    float centerZ = 0.0f;
    uint32 centerCount = 0;
    if (Group* group = owner->GetGroup())
    {
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || member->GetMap() != bot->GetMap())
                continue;
            centerX += member->GetPositionX();
            centerY += member->GetPositionY();
            centerZ += member->GetPositionZ();
            ++centerCount;
        }
    }
    if (!centerCount)
    {
        centerX = owner->GetPositionX();
        centerY = owner->GetPositionY();
        centerZ = owner->GetPositionZ();
        centerCount = 1;
    }
    centerX /= float(centerCount);
    centerY /= float(centerCount);
    centerZ /= float(centerCount);
    frame.DistanceToGroupCenter = bot->GetExactDist(centerX, centerY, centerZ);

    frame.CurrentPathLength = _movementTarget.Active ? bot->GetExactDist(_movementTarget.X, _movementTarget.Y, _movementTarget.Z) : frame.DistanceToLeader;
    frame.PathAvailable = frame.LineOfSightToLeader || frame.CurrentPathLength < 80.0f;

    if (diff > 0)
    {
        float moved = std::sqrt((frame.X - _lastX) * (frame.X - _lastX) + (frame.Y - _lastY) * (frame.Y - _lastY) + (frame.Z - _lastZ) * (frame.Z - _lastZ));
        bool needsProgress = _movementMode == BotMovementMode::Follow || _movementMode == BotMovementMode::MoveTo || _movementMode == BotMovementMode::ReturnToGroup || _movementMode == BotMovementMode::MoveSafe;
        if (!_lastProgressMs || moved > 0.25f || !needsProgress)
        {
            _lastProgressMs = 0;
            _stuckScore = std::max(0.0f, _stuckScore - 0.25f);
        }
        else
        {
            _lastProgressMs += diff;
            if (_lastProgressMs >= 2000)
                _stuckScore = std::min(1.0f, _stuckScore + 0.25f);
        }
        _lastX = frame.X;
        _lastY = frame.Y;
        _lastZ = frame.Z;
    }
    frame.LastProgressTimeMs = _lastProgressMs;
    frame.StuckScore = _stuckScore;
    return frame;
}

BotCombatState BotController::BuildCombatState(Player* owner, Player* bot, BotRecentEvents const& recentEvents) const
{
    BotCombatState frame;
    frame.ClassId = bot->getClass();
    frame.SpecId = 0;
    frame.Moving = bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
    frame.Casting = bot->HasUnitState(UNIT_STATE_CASTING);
    frame.ActiveAuraCount = bot->GetAppliedAuras().size();
    frame.InCombat = bot->IsInCombat() || owner->IsInCombat() || recentEvents.DamageTaken > 0;
    frame.SafePositionAvailable = owner->IsAlive() && bot->GetMap() == owner->GetMap() && !bot->IsFalling() && !bot->IsInWater();

    uint32 maxHealth = bot->GetMaxHealth();
    frame.SelfHpPct = maxHealth ? float(bot->GetHealth()) / float(maxHealth) : 0.0f;
    Powers power = bot->GetPowerType();
    uint32 maxPower = bot->GetMaxPower(power);
    frame.SelfPowerPct = maxPower ? float(bot->GetPower(power)) / float(maxPower) : 1.0f;

    SpellInfo const* gcdProbe = sSpellMgr->GetSpellInfo(6603);
    frame.GcdReady = !gcdProbe || !bot->GetSpellHistory()->HasGlobalCooldown(gcdProbe);

    Unit* target = nullptr;
    if (!_combatTargetGuid.IsEmpty())
        target = ObjectAccessor::GetUnit(*bot, _combatTargetGuid);
    if (!target && bot->GetVictim())
        target = bot->GetVictim();

    if (target)
    {
        frame.TargetGuid = target->GetGUID();
        if (Creature* creature = target->ToCreature())
        {
            frame.TargetEntry = creature->GetEntry();
            frame.TargetLootable = creature->isDead() && creature->hasLootRecipient();
        }

        frame.TargetDead = !target->IsAlive();
        uint32 targetMaxHealth = target->GetMaxHealth();
        frame.TargetHpPct = targetMaxHealth ? float(target->GetHealth()) / float(targetMaxHealth) : 0.0f;
        frame.TargetDistance = bot->GetExactDist(target);
        if (Spell* spell = target->GetCurrentSpell(CURRENT_GENERIC_SPELL))
        {
            frame.TargetCastingSpellId = spell->GetSpellInfo()->Id;
            frame.TargetInterruptible = true;
        }
    }

    if (Unit* nearby = bot->SelectNearbyTarget(target, 8.0f))
    {
        ++frame.NearbyHostileCount;
        if (Creature* creature = nearby->ToCreature())
            if (creature->isElite())
                frame.EliteNearby = true;
    }
    if (Unit* nearby = bot->SelectNearbyTarget(target, 16.0f))
    {
        ++frame.NearbyHostileCount;
        if (Creature* creature = nearby->ToCreature())
            if (creature->isElite())
                frame.EliteNearby = true;
    }
    if (Unit* nearby = bot->SelectNearbyTarget(target, 24.0f))
    {
        ++frame.NearbyHostileCount;
        if (Creature* creature = nearby->ToCreature())
            if (creature->isElite())
                frame.EliteNearby = true;
    }
    frame.ExtraPullRisk = std::min(1.0f, frame.NearbyHostileCount / 3.0f);
    return frame;
}

BotCombatDecision BotController::DecideSoloCombat(BotCombatState const& state) const
{
    BotCombatDecision decision;
    decision.TargetGuid = state.TargetGuid;
    if (state.TargetGuid.IsEmpty())
        decision.Intent = BotCombatIntent::Wait;
    else if (state.TargetLootable)
        decision.Intent = BotCombatIntent::Loot;
    else if (state.TargetDead)
        decision.Intent = BotCombatIntent::Recover;
    else if (state.SelfHpPct < 0.35f && _runtimeRole == "healer")
        decision.Intent = BotCombatIntent::HealSelf;
    else if (state.SelfHpPct < 0.30f)
        decision.Intent = BotCombatIntent::UseDefensive;
    else if (state.TargetCastingSpellId && state.TargetInterruptible)
        decision.Intent = BotCombatIntent::Interrupt;
    else if (state.TargetDistance > 5.0f && CombatArchetypeForClass(state.ClassId, _runtimeRole, _classSpec) != BotCombatArchetype::RangedCaster && CombatArchetypeForClass(state.ClassId, _runtimeRole, _classSpec) != BotCombatArchetype::RangedPhysical)
        decision.Intent = BotCombatIntent::MoveToRange;
    else if (!state.InCombat)
        decision.Intent = BotCombatIntent::PullTarget;
    else
        decision.Intent = BotCombatIntent::MaintainRotation;
    return decision;
}

ResolvedCombatAction BotController::ResolveSoloCombat(BotCombatDecision const& decision, BotCombatState const& state) const
{
    ResolvedCombatAction action;
    action.TargetGuid = decision.TargetGuid;
    action.DebugName = ToString(decision.Intent);
    switch (decision.Intent)
    {
        case BotCombatIntent::Loot:
            action.Type = "loot";
            break;
        case BotCombatIntent::MoveToRange:
        case BotCombatIntent::PullTarget:
            action.Type = "pull";
            break;
        case BotCombatIntent::HealSelf:
            action.Type = "cast";
            action.TargetGuid = _botGuid;
            action.SpellId = _role == BotRole::HolyPaladinHealer ? 635 : 0;
            break;
        case BotCombatIntent::UseDefensive:
            action.Type = "cast";
            action.SpellId = _role == BotRole::Warrior ? 871 : 0;
            break;
        case BotCombatIntent::Interrupt:
            action.Type = "cast";
            action.SpellId = _role == BotRole::Warrior ? 6552 : 0;
            break;
        case BotCombatIntent::MaintainRotation:
            action.Type = "cast";
            if (GetSoloCombatArchetype(_role) == BotCombatArchetype::RangedCaster)
                action.SpellId = _role == BotRole::Mage ? 133 : 585;
            else if (_role == BotRole::Hunter)
                action.SpellId = 75;
            else if (_role == BotRole::HolyPaladinHealer)
                action.SpellId = 20271;
            else
                action.SpellId = 6603;
            break;
        case BotCombatIntent::Recover:
        case BotCombatIntent::Wait:
        default:
            action.Type = "wait";
            break;
    }

    if (!action.SpellId && action.Type == "cast")
        action.Valid = false;
    if (state.TargetGuid.IsEmpty() && action.TargetGuid != _botGuid)
        action.Valid = false;
    return action;
}

BotActionCandidate const* BotController::SelectProfileCombatAction(Player* bot, Unit* target, BotCombatState const& state, BotClassSpecActionProfile const& profile, std::vector<BotActionCandidate>& candidates) const
{
    std::vector<BotActionCandidate*> valid;
    uint8 bestBucket = 255;

    for (BotActionCandidate& candidate : candidates)
    {
        if (IsHealingCategory(candidate.Category))
        {
            candidate.RejectReason = "requires_ally_target";
            continue;
        }
        if (!candidate.RejectReason.empty())
            continue;

        if (candidate.Category == BotCombatActionCategory::Taunt && target && target->GetVictim() == bot)
        {
            candidate.RejectReason = "threat_already_established";
            continue;
        }
        if (candidate.Profile.RequiresTargetNotVictim && target && target->GetVictim() == bot)
        {
            candidate.RejectReason = "target_already_on_bot";
            continue;
        }
        if (candidate.Profile.RequiresTargetVictim && target && target->GetVictim() != bot)
        {
            candidate.RejectReason = "target_not_on_bot";
            continue;
        }
        if (candidate.Profile.MinEnemies > 1 && state.NearbyHostileCount < candidate.Profile.MinEnemies)
        {
            candidate.RejectReason = "enemy_count_too_low";
            continue;
        }
        if (candidate.Profile.MaxEnemies && state.NearbyHostileCount > candidate.Profile.MaxEnemies)
        {
            candidate.RejectReason = "enemy_count_too_high";
            continue;
        }
        if (state.TargetHpPct < candidate.Profile.MinTargetHealthPct || state.TargetHpPct > candidate.Profile.MaxTargetHealthPct)
        {
            candidate.RejectReason = "target_health_gate";
            continue;
        }
        if (state.SelfHpPct < candidate.Profile.MinSelfHealthPct || state.SelfHpPct > candidate.Profile.MaxSelfHealthPct)
        {
            candidate.RejectReason = "self_health_gate";
            continue;
        }
        if (candidate.Profile.RequiresInterruptibleTarget && !state.TargetInterruptible)
        {
            candidate.RejectReason = "target_not_interruptible";
            continue;
        }
        if (candidate.Profile.RequiredSelfAura && !bot->HasAura(candidate.Profile.RequiredSelfAura))
        {
            candidate.RejectReason = "missing_self_aura";
            continue;
        }
        if (candidate.Profile.RequiredSelfAuraStacks)
        {
            Aura const* aura = candidate.Profile.RequiredSelfAura ? bot->GetAura(candidate.Profile.RequiredSelfAura) : nullptr;
            if (!aura || aura->GetStackAmount() < candidate.Profile.RequiredSelfAuraStacks)
            {
                candidate.RejectReason = "insufficient_self_aura_stacks";
                continue;
            }
        }
        if (candidate.Profile.ForbiddenSelfAura && bot->HasAura(candidate.Profile.ForbiddenSelfAura))
        {
            candidate.RejectReason = "forbidden_self_aura";
            continue;
        }
        bool selfTarget = candidate.Profile.TargetSelector == "self";
        Unit* actionTarget = selfTarget ? static_cast<Unit*>(bot) : target;
        float targetDistance = selfTarget ? 0.0f : state.TargetDistance;
        if (actionTarget && candidate.Profile.RequiredTargetAura && !actionTarget->HasAura(candidate.Profile.RequiredTargetAura))
        {
            candidate.RejectReason = "missing_target_aura";
            continue;
        }
        if (actionTarget && candidate.Profile.ForbiddenTargetAura && actionTarget->HasAura(candidate.Profile.ForbiddenTargetAura))
        {
            candidate.RejectReason = "forbidden_target_aura";
            continue;
        }
        if (candidate.Profile.RequiresMeleeRange && actionTarget && !bot->IsWithinMeleeRange(actionTarget))
        {
            candidate.RejectReason = "melee_range_required";
            continue;
        }
        if (candidate.Profile.RequiresRangedRange && targetDistance < 5.0f)
        {
            candidate.RejectReason = "ranged_range_required";
            continue;
        }
        float minRange = candidate.Profile.MinRange > 0.0f ? candidate.Profile.MinRange : profile.MinRange;
        float maxRange = candidate.Profile.MaxRange > 0.0f ? candidate.Profile.MaxRange : profile.MaxRange;
        if (candidate.Profile.MaxRange <= 0.0f)
            if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId))
                maxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
        if (minRange > 0.0f && targetDistance < minRange)
        {
            candidate.RejectReason = "min_range_required";
            continue;
        }
        if (maxRange > 0.0f && targetDistance > maxRange)
        {
            candidate.RejectReason = "max_range_exceeded";
            continue;
        }
        if (candidate.SpellId)
            if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId))
            {
                if (!RotationHasEnoughPower(bot, spellInfo))
                {
                    candidate.RejectReason = "insufficient_spell_power_type_resource";
                    continue;
                }
                if (!MeetsCastDirectives(bot, candidate.Profile, spellInfo))
                {
                    candidate.RejectReason = candidate.Profile.RequiresInstantCast ? "instant_cast_required" : "cast_time_too_long";
                    continue;
                }
            }

        if (!candidate.RejectReason.empty())
            continue;

        float roleScore = candidate.Score;
        if (_runtimeRole == "tank")
        {
            roleScore += candidate.Profile.ThreatWeight * 2.0f + candidate.Profile.MitigationWeight + candidate.Profile.SurvivalWeight * 0.5f;
            if (state.NearbyHostileCount >= 2 && (candidate.Category == BotCombatActionCategory::Aoe || candidate.Category == BotCombatActionCategory::Cleave || candidate.Category == BotCombatActionCategory::ThreatBuild))
                roleScore += 1.25f;
            if (target && target->GetVictim() && target->GetVictim() != bot && candidate.Category == BotCombatActionCategory::Taunt)
                roleScore += 2.0f;
        }
        else if (_runtimeRole == "healer")
            roleScore += candidate.Profile.DamageWeight * 0.65f;
        else
        {
            roleScore += candidate.Profile.DamageWeight;
            if (state.NearbyHostileCount >= 2 && (candidate.Category == BotCombatActionCategory::Aoe || candidate.Category == BotCombatActionCategory::Cleave))
                roleScore += 0.8f;
            if (candidate.Category == BotCombatActionCategory::Interrupt)
                roleScore += state.TargetInterruptible ? 2.0f : -0.4f;
        }

        roleScore += std::max<float>(0.0f, 12.0f - float(candidate.Profile.PriorityBucket)) * 0.35f;
        candidate.Score = roleScore;
        candidate.Reason = "guide_weighted_priority_band";
        if (candidate.Profile.PriorityBucket < bestBucket)
        {
            bestBucket = candidate.Profile.PriorityBucket;
            valid.clear();
        }
        if (candidate.Profile.PriorityBucket == bestBucket)
            valid.push_back(&candidate);
    }

    if (valid.empty())
        return nullptr;

    return *std::max_element(valid.begin(), valid.end(), [](BotActionCandidate const* left, BotActionCandidate const* right)
    {
        if (left->Score != right->Score)
            return left->Score < right->Score;
        if (left->Profile.SortOrder != right->Profile.SortOrder)
            return left->Profile.SortOrder > right->Profile.SortOrder;
        return left->ActionId > right->ActionId;
    });
}

ResolvedCombatAction BotController::ResolveProfileCombat(BotCombatDecision const& decision, BotCombatState const& state, Player* bot, Unit* target) const
{
    ResolvedCombatAction action;
    action.TargetGuid = decision.TargetGuid;
    action.DebugName = ToString(decision.Intent);

    if (decision.Intent == BotCombatIntent::Loot)
    {
        action.Type = "loot";
        return action;
    }
    if (decision.Intent == BotCombatIntent::Recover || decision.Intent == BotCombatIntent::Wait)
    {
        action.Type = "wait";
        action.Valid = false;
        return action;
    }
    if (!bot || !target || !target->IsAlive())
    {
        action.Type = "wait";
        action.Valid = false;
        action.DebugName = "no_valid_target";
        return action;
    }

    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, _runtimeRole.c_str());
    action.MovementDirective = profile.MovementDirective;
    action.AutoAttackMode = profile.AutoAttackMode;
    action.MinRange = profile.MinRange;
    action.MaxRange = profile.MaxRange;

    std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile);
    BotActionCandidate const* best = SelectProfileCombatAction(bot, target, state, profile, candidates);
    if (!best || !best->SpellId)
    {
        action.Type = "wait";
        action.Valid = false;
        action.DebugName = "no_valid_profile_action";
        return action;
    }

    action.Type = "cast";
    action.SpellId = best->SpellId;
    action.TargetGuid = best->Profile.TargetSelector == "self" ? bot->GetGUID() : target->GetGUID();
    action.MovementDirective = best->Profile.MovementDirective.empty() ? profile.MovementDirective : best->Profile.MovementDirective;
    action.AutoAttackMode = best->Profile.AutoAttackMode.empty() ? profile.AutoAttackMode : best->Profile.AutoAttackMode;
    action.MinRange = best->Profile.MinRange > 0.0f ? best->Profile.MinRange : profile.MinRange;
    action.MaxRange = best->Profile.MaxRange > 0.0f ? best->Profile.MaxRange : profile.MaxRange;
    if (best->Profile.MaxRange <= 0.0f)
        if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(best->SpellId))
            action.MaxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    action.DebugName = BotCombatActionCatalog::ToString(best->Category);
    return action;
}

bool BotController::TryExecuteQueuedCombatAction(BotActionExecutor& executor, Player* owner, Player* bot, BotActionResult& result)
{
    if (!_queuedCombatAction.Valid || !_queuedCombatAction.SpellId || !_queuedCombatActionMs)
        return false;

    result = executor.ExecuteCombat(owner, bot, _queuedCombatAction);
    if (result == BotActionResult::Ok)
    {
        _queuedCombatAction = ResolvedCombatAction();
        _queuedCombatActionMs = 0;
        return true;
    }

    if (result == BotActionResult::Casting || result == BotActionResult::GlobalCooldown)
    {
        _queuedCombatActionMs = _queuedCombatActionMs > _updateTimer ? _queuedCombatActionMs - _updateTimer : 0;
        if (!_queuedCombatActionMs)
            _queuedCombatAction = ResolvedCombatAction();
        return true;
    }

    _queuedCombatAction = ResolvedCombatAction();
    _queuedCombatActionMs = 0;
    return false;
}

bool BotController::TryResolveHealerAction(BotActionExecutor& executor, Player* owner, Player* bot, BotRecentEvents const& recentEvents, bool shouldRecord, BotMovementFrame const& movementFrame)
{
    // DB categories, including BotCombatActionCategory::HealFast, are the sole healer action authority.
    _lastHealerCandidateMaskJson = "{}";
    _lastHealerChosenActionJson = "{}";
    HealerFrame frame = BuildFrame(owner, bot, recentEvents);
    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, "healer");
    ResolvedBotAction action;
    action.DebugName = "no_valid_db_healer_action";
    HealerDecision decision;
    struct HealerAttempt
    {
        BotActionProfileSpell const* Spell = nullptr;
        ObjectGuid TargetGuid;
        float Score = 0.0f;
        BotActionCandidate Candidate;
    };
    std::vector<HealerAttempt> attempts;
    std::vector<BotActionCandidate> evaluatedCandidates;
    uint8 attackers = uint8(std::min<size_t>(255, bot->GetThreatManager().GetThreatenedByMeList().size()));

    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        if (!spell.SpellId || !IsHealingCategory(spell.Category))
            continue;
        BotActionCandidate telemetryCandidate;
        telemetryCandidate.ActionId = BotCombatActionCatalog::StableActionId(spell.Category, spell.SpellId);
        telemetryCandidate.SpellId = spell.SpellId;
        telemetryCandidate.Category = spell.Category;
        telemetryCandidate.TargetType = spell.TargetSelector;
        telemetryCandidate.Profile = spell;
        auto rejectCandidate = [&](char const* reason) { telemetryCandidate.RejectReason = reason; evaluatedCandidates.push_back(telemetryCandidate); };
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId);
        if (!spellInfo) { rejectCandidate("missing_spell_info"); continue; }
        if (!bot->GetSpellHistory()->IsReady(spellInfo)) { rejectCandidate("cooldown_not_ready"); continue; }
        if (!RotationHasEnoughPower(bot, spellInfo)) { rejectCandidate("insufficient_power"); continue; }
        uint8 injuredPlayers = 0;
        for (HealerUnitFrame const& partyUnit : frame.Party)
            if (partyUnit.Alive && partyUnit.Friendly && float(partyUnit.HealthPct) / 100.0f <= spell.InjuredHealthPct)
                ++injuredPlayers;
        uint32 castTime = CastTimeMs(bot, spellInfo);
        if (!MeetsCastDirectives(bot, spell, spellInfo)) { rejectCandidate("cast_directive_rejected"); continue; }
        if ((movementFrame.Moving && castTime && !spell.RequiresMoving) || (spell.RequiresStationary && movementFrame.Moving) || (spell.RequiresMoving && !movementFrame.Moving)) { rejectCandidate("movement_gate"); continue; }
        if (spell.MinInjuredPlayers && injuredPlayers < spell.MinInjuredPlayers) { rejectCandidate("injured_player_count_too_low"); continue; }
        if (spell.MaxInjuredPlayers && injuredPlayers > spell.MaxInjuredPlayers) { rejectCandidate("injured_player_count_too_high"); continue; }
        if (spell.MinAttackers && attackers < spell.MinAttackers) { rejectCandidate("attacker_count_too_low"); continue; }
        if (spell.MaxAttackers && attackers > spell.MaxAttackers) { rejectCandidate("attacker_count_too_high"); continue; }
        if (float(frame.BotManaPct) / 100.0f < spell.MinManaPct) { rejectCandidate("mana_too_low"); continue; }
        if (float(frame.BotManaPct) / 100.0f > spell.MaxManaPct) { rejectCandidate("mana_too_high"); continue; }
        bool utility = spell.Category == BotCombatActionCategory::Defensive || spell.Category == BotCombatActionCategory::Mitigation
            || spell.Category == BotCombatActionCategory::OffensiveCooldown;
        Unit* target = nullptr;
        ObjectGuid targetGuid;
        float healthPct = float(frame.BotHealthPct) / 100.0f;
        if (spell.TargetSelector == "enemy")
        {
            target = bot->GetSelectedUnit();
            if (!target || !bot->IsValidAttackTarget(target))
                target = bot->GetVictim();
            if (!target || !bot->IsValidAttackTarget(target))
            { rejectCandidate("missing_enemy_target"); continue; }
            targetGuid = target->GetGUID();
        }
        else
        {
            HealerUnitFrame const* unit = SelectHealerUnit(frame, spell.TargetSelector.empty() ? "lowest_ally" : spell.TargetSelector);
            if (!unit)
            { rejectCandidate("missing_ally_target"); continue; }
            targetGuid = unit->Guid;
            healthPct = float(unit->HealthPct) / 100.0f;
            target = ObjectAccessor::GetUnit(*bot, targetGuid);
            if (!target)
            { rejectCandidate("invalid_ally_target"); continue; }
        }
        if (float(frame.BotHealthPct) / 100.0f < spell.MinSelfHealthPct || float(frame.BotHealthPct) / 100.0f > spell.MaxSelfHealthPct
            || (!utility && (healthPct < spell.MinTargetHealthPct || healthPct > spell.MaxTargetHealthPct
                || (spell.InjuredHealthPct < 1.0f && healthPct > spell.InjuredHealthPct))))
        { rejectCandidate("health_gate"); continue; }
        float distance = bot->GetExactDist(target);
        if ((spell.MaxRange > 0.0f && distance > spell.MaxRange) || (spell.MinRange > 0.0f && distance < spell.MinRange)
            || (spell.MaxRange <= 0.0f && distance > std::max(5.0f, spellInfo->GetMaxRange(false))))
        { rejectCandidate("range_gate"); continue; }
        if ((spell.ForbiddenTargetAura && target->HasAura(spell.ForbiddenTargetAura))
            || (spell.MaintainAuraId && target->HasAura(spell.MaintainAuraId))
            || (spell.RequiredTargetAura && !target->HasAura(spell.RequiredTargetAura))
            || (spell.RequiredSelfAura && !bot->HasAura(spell.RequiredSelfAura))
            || (spell.ForbiddenSelfAura && bot->HasAura(spell.ForbiddenSelfAura)))
        { rejectCandidate("aura_gate"); continue; }

        float missingHealth = float(target->GetMaxHealth() - target->GetHealth());
        float expectedRawHealing = utility ? 0.0f : std::max(0.0f, spell.HealingWeight) * float(target->GetMaxHealth());
        float expectedEffectiveHealing = utility ? 0.0f : std::min(missingHealth, expectedRawHealing);
        float expectedOverheal = utility ? 0.0f : std::max(0.0f, expectedRawHealing - expectedEffectiveHealing);
        float urgency = 1.0f - healthPct;
        float score = utility
            ? (spell.SurvivalWeight + spell.ThreatWeight * float(attackers) + spell.MitigationWeight + spell.MovementWeight) * float(bot->GetMaxHealth())
            : expectedEffectiveHealing - expectedOverheal * 0.35f + spell.SurvivalWeight * urgency * float(target->GetMaxHealth());
        score -= float(spell.PriorityBucket) * 0.03f;
        uint32 manaCost = uint32(std::max<int32>(0, spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask())));
        telemetryCandidate.TargetGuid = targetGuid.GetCounter();
        telemetryCandidate.Score = score;
        telemetryCandidate.Reason = "db_profile_healing_policy";
        telemetryCandidate.PredictedRawHeal = expectedRawHealing;
        telemetryCandidate.PredictedEffectiveHeal = expectedEffectiveHealing;
        telemetryCandidate.PredictedOverheal = expectedOverheal;
        telemetryCandidate.ManaCost = manaCost;
        telemetryCandidate.CastTimeMs = castTime;
        telemetryCandidate.Profile = spell;
        evaluatedCandidates.push_back(telemetryCandidate);
        attempts.push_back(HealerAttempt{ &spell, targetGuid, score, telemetryCandidate });
    }

    std::sort(attempts.begin(), attempts.end(), [](HealerAttempt const& left, HealerAttempt const& right)
    {
        return left.Score > right.Score;
    });

    BotActionResult result = BotActionResult::NoAction;
    for (HealerAttempt const& attempt : attempts)
    {
        action.Intent = HealerIntent::EfficientSingleHeal;
        action.TargetGuid = attempt.TargetGuid;
        action.SpellId = attempt.Spell->SpellId;
        action.DebugName = BotCombatActionCatalog::ToString(attempt.Spell->Category);
        Unit* lifecycleTarget = ObjectAccessor::GetUnit(*bot, attempt.TargetGuid);
        std::string candidateMaskJson = BotClassSpecActionProfileStore::CandidateMaskJson(evaluatedCandidates, profile, "preserve_party", "{}");
        std::string chosenActionJson = BotClassSpecActionProfileStore::ChosenActionJson(&attempt.Candidate, profile, "preserve_party", "role_first", 1.0f);
        _lastHealerCandidateMaskJson = candidateMaskJson;
        _lastHealerChosenActionJson = chosenActionJson;
        uint64 pendingCastId = sBotWorldPopulationMgr->NotifyBotSpellStarted(bot, lifecycleTarget, attempt.Spell->SpellId, candidateMaskJson, chosenActionJson);
        result = executor.Execute(owner, bot, action);
        if (result == BotActionResult::Ok || result == BotActionResult::Casting)
            break;
        sBotWorldPopulationMgr->CancelBotSpellStart(pendingCastId, bot, ToString(result));
        if (result == BotActionResult::GlobalCooldown)
            break;
    }

    if (shouldRecord)
    {
        RecordFrame(frame, decision, &action, result, owner, bot);
        RecordMovementFrame(movementFrame, ToString(_movementMode), ToString(decision.Intent), action.DebugName.c_str(), result != BotActionResult::Disabled, owner, bot);
    }

    return result == BotActionResult::Ok || result == BotActionResult::Casting || result == BotActionResult::GlobalCooldown;
}

bool BotController::ApplyMovementPolicy(BotActionExecutor& executor, Player* owner, Player* bot, BotMovementFrame const& movementFrame)
{
    if (!bot || !bot->IsInWorld())
        return false;

    using namespace BotMovementArbitration;
    uint64 const nowMs = PlayerBotNowMs();
    Request request;
    request.ExpiresAtMs = nowMs + 1500;
    request.MovementScope = Scope{
        PlayerBotRunId(), 0, 0, bot->GetMapId(), bot->GetInstanceId()
    };
    request.X = bot->GetPositionX();
    request.Y = bot->GetPositionY();
    request.Z = bot->GetPositionZ();

    if (_movementMode == BotMovementMode::Stop)
    {
        request.MovementOwner = Owner::Recovery;
        request.MovementPriority = Priority::Recovery;
    }
    else if (movementFrame.StuckScore >= 1.0f || _movementMode == BotMovementMode::Unstuck)
    {
        request.MovementOwner = Owner::Recovery;
        request.MovementPriority = Priority::Recovery;
        if (owner)
        {
            request.X = owner->GetPositionX();
            request.Y = owner->GetPositionY();
            request.Z = owner->GetPositionZ();
        }
    }
    else if (_movementMode == BotMovementMode::Follow || _movementMode == BotMovementMode::ReturnToGroup)
    {
        request.MovementOwner = Owner::Formation;
        request.MovementPriority = Priority::Formation;
        if (owner)
        {
            request.X = owner->GetPositionX();
            request.Y = owner->GetPositionY();
            request.Z = owner->GetPositionZ();
        }
    }
    else if (_movementMode == BotMovementMode::MoveSafe)
    {
        request.MovementOwner = Owner::Hazard;
        request.MovementPriority = Priority::Hazard;
        if (owner)
        {
            request.X = owner->GetPositionX();
            request.Y = owner->GetPositionY();
            request.Z = owner->GetPositionZ();
        }
    }
    else if (_movementMode == BotMovementMode::MoveTo && _movementTarget.Active)
    {
        request.MovementOwner = Owner::Route;
        request.MovementPriority = Priority::Route;
        request.X = _movementTarget.X;
        request.Y = _movementTarget.Y;
        request.Z = _movementTarget.Z;
    }
    else
    {
        request.MovementOwner = Owner::Mechanic;
        request.MovementPriority = Priority::Mechanic;
    }

    Decision const leaseDecision = Evaluate(_movementLease, request, nowMs);
    if (leaseDecision == Decision::RejectInvalid
        || leaseDecision == Decision::PreserveExisting)
        return false;
    Apply(_movementLease, request);

    if (movementFrame.StuckScore >= 1.0f || _movementMode == BotMovementMode::Unstuck)
    {
        executor.MoveUnstuck(owner, bot);
        _movementMode = BotMovementMode::Follow;
        return true;
    }

    if (_movementMode == BotMovementMode::Follow)
    {
        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, _runtimeRole.c_str());
        executor.MoveFollow(owner, bot, ProfileFollowDistance(profile));
    }
    else if (_movementMode == BotMovementMode::Stay)
        executor.MoveStay(bot);
    else if (_movementMode == BotMovementMode::Stop)
        executor.MoveStop(bot);
    else if (_movementMode == BotMovementMode::MoveTo && _movementTarget.Active)
        executor.MoveTo(bot, _movementTarget.X, _movementTarget.Y, _movementTarget.Z);
    else if (_movementMode == BotMovementMode::ReturnToGroup || _movementMode == BotMovementMode::MoveSafe)
        executor.MoveFollow(owner, bot);
    return true;
}

HealerFrame BotController::BuildFrame(Player* owner, Player* bot, BotRecentEvents const& recentEvents) const
{
    HealerFrame frame;
    frame.OwnerGuid = owner->GetGUID();
    frame.BotGuid = bot->GetGUID();
    frame.MapId = bot->GetMapId();
    frame.BotAlive = bot->IsAlive();
    frame.BotCasting = bot->HasUnitState(UNIT_STATE_CASTING);
    if (Spell* spell = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
        frame.BotCastSpellId = spell->GetSpellInfo()->Id;
    if (Spell* spell = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
        frame.BotChannelSpellId = spell->GetSpellInfo()->Id;
    frame.BotAuraCount = bot->GetAppliedAuras().size();
    for (auto const& aura : bot->GetAppliedAuras())
        if (aura.second && !aura.second->IsPositive())
            ++frame.BotDebuffCount;
    frame.InCombat = bot->IsInCombat() || owner->IsInCombat();
    frame.RecentDamageTaken = recentEvents.DamageTaken;
    frame.RecentHealingDone = recentEvents.HealingDone;
    frame.RecentHealingReceived = recentEvents.HealingReceived;
    frame.MovementMode = _movementMode;

    uint32 maxHealth = bot->GetMaxHealth();
    frame.BotHealthPct = maxHealth ? uint32(bot->GetHealth() * 100 / maxHealth) : 0;
    uint32 maxMana = bot->GetMaxPower(POWER_MANA);
    frame.BotManaPct = maxMana ? uint32(bot->GetPower(POWER_MANA) * 100 / maxMana) : 100;

    SpellInfo const* holyLight = sSpellMgr->GetSpellInfo(635);
    frame.GcdReady = !holyLight || !bot->GetSpellHistory()->HasGlobalCooldown(holyLight);

    Group* group = owner->GetGroup();
    auto addUnit = [&](Player* player, bool isOwner)
    {
        if (!player || player->GetMap() != bot->GetMap())
            return;

        HealerUnitFrame unit;
        unit.Guid = player->GetGUID();
        unit.Name = player->GetName();
        unit.Role = group ? group->GetLfgRoles(player->GetGUID()) : 0;
        unit.Subgroup = group ? group->GetMemberGroup(player->GetGUID()) : 0;
        unit.Alive = player->IsAlive();
        unit.Friendly = bot->IsFriendlyTo(player) || bot->IsValidAssistTarget(player);
        unit.LineOfSight = bot->IsWithinLOSInMap(player);
        unit.Distance = bot->GetExactDist(player);
        unit.IsOwner = isOwner;
        if (Spell* spell = player->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            unit.CastSpellId = spell->GetSpellInfo()->Id;
        if (Spell* spell = player->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
            unit.ChannelSpellId = spell->GetSpellInfo()->Id;
        unit.AuraCount = player->GetAppliedAuras().size();
        for (auto const& aura : player->GetAppliedAuras())
            if (aura.second && !aura.second->IsPositive())
                ++unit.DebuffCount;
        auto damageItr = recentEvents.PartyDamageTaken.find(player->GetGUID());
        if (damageItr != recentEvents.PartyDamageTaken.end())
            unit.RecentDamageTaken = damageItr->second;
        auto healingItr = recentEvents.PartyHealingReceived.find(player->GetGUID());
        if (healingItr != recentEvents.PartyHealingReceived.end())
            unit.RecentHealingReceived = healingItr->second;
        uint32 unitMaxHealth = player->GetMaxHealth();
        unit.HealthPct = unitMaxHealth ? uint8(std::min<uint32>(100, player->GetHealth() * 100 / unitMaxHealth)) : 0;
        frame.Party.push_back(unit);
    };

    if (group)
    {
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            addUnit(itr->GetSource(), itr->GetSource() == owner);
    }
    else
        addUnit(owner, true);

    return frame;
}

BotProfessionFrame BotController::BuildProfessionFrame(Player* owner, Player* bot) const
{
    BotProfessionFrame frame;
    frame.OwnerGuid = owner ? owner->GetGUID() : ObjectGuid::Empty;
    frame.BotGuid = bot ? bot->GetGUID() : ObjectGuid::Empty;
    if (!bot)
        return frame;

    frame.ClassId = bot->getClass();
    frame.SpecId = 0;
    frame.Profession.ProfessionId = "cooking";
    frame.Profession.SkillId = SKILL_COOKING;
    frame.Profession.SkillCurrent = bot->HasSkill(SKILL_COOKING) ? bot->GetSkillValue(SKILL_COOKING) : 0;
    frame.Profession.SkillTarget = bot->HasSkill(SKILL_COOKING) ? bot->GetMaxSkillValue(SKILL_COOKING) : 0;
    frame.Profession.BagFreeSlots = bot->GetFreeInventorySpace();
    frame.Inventory.Gold = bot->GetMoney();

    if (std::vector<SkillLineAbilityEntry const*> const* abilities = sDBCManager.GetSkillLineAbilitiesBySkill(SKILL_COOKING))
    {
        for (SkillLineAbilityEntry const* ability : *abilities)
        {
            if (!ability || !ability->Spell)
                continue;

            if (bot->HasSpell(ability->Spell))
                frame.Profession.KnownRecipes.push_back(ability->Spell);
            else if (bot->HasSkill(SKILL_COOKING) && ability->MinSkillLineRank <= frame.Profession.SkillCurrent)
                frame.Profession.TrainableRecipes.push_back(ability->Spell);
        }
    }

    std::map<uint32, uint32> itemCounts;
    auto addItem = [&itemCounts](Item const* item)
    {
        if (!item)
            return;

        itemCounts[item->GetEntry()] += item->GetCount();
    };

    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        addItem(bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));

    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
    {
        if (Bag const* bag = bot->GetBagByPos(bagSlot))
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                addItem(bag->GetItemByPos(slot));
    }

    for (auto const& itemCount : itemCounts)
        frame.Inventory.Materials.push_back(BotInventoryMaterial{ itemCount.first, itemCount.second });

    return frame;
}

void BotController::RecordFrame(HealerFrame const& frame, HealerDecision const& decision, ResolvedBotAction const* action, BotActionResult result, Player* owner, Player* bot) const
{
    std::string path = sConfigMgr->GetStringDefault("PlayerBot.Record.Path", "dataset/raw/healer_frames_playerbot.jsonl");
    boost::filesystem::path outputPath(path);
    if (outputPath.has_parent_path())
        boost::filesystem::create_directories(outputPath.parent_path());

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out)
        return;

    uint64 seq = ++_sequence;
    std::ostringstream observation;
    observation << "{\"owner_guid\":" << frame.OwnerGuid.GetCounter()
                << ",\"map_id\":" << frame.MapId
                << ",\"instance_id\":" << (bot ? bot->GetInstanceId() : 0)
                << ",\"bot_hp_pct\":" << frame.BotHealthPct
                << ",\"bot_mana_pct\":" << frame.BotManaPct
                << ",\"bot_cast_spell_id\":" << frame.BotCastSpellId
                << ",\"bot_channel_spell_id\":" << frame.BotChannelSpellId
                << ",\"bot_aura_count\":" << frame.BotAuraCount
                << ",\"bot_debuff_count\":" << frame.BotDebuffCount
                << ",\"recent_damage_taken\":" << frame.RecentDamageTaken
                << ",\"recent_healing_done\":" << frame.RecentHealingDone
                << ",\"recent_healing_received\":" << frame.RecentHealingReceived
                << ",\"party_size\":" << frame.Party.size() << "}";

    std::ostringstream chosen;
    chosen << "{\"mode\":\"" << JsonEscape(ToString(decision.Mode))
           << "\",\"intent\":\"" << JsonEscape(ToString(decision.Intent))
           << "\",\"target_guid\":" << decision.TargetGuid.GetCounter()
           << ",\"spell_id\":" << (action ? action->SpellId : 0)
           << ",\"action\":\"" << JsonEscape(action ? action->DebugName : "wait") << "\"}";

    BotDatasetEvent dataset;
    dataset.run_id = PlayerBotRunId();
    dataset.experiment_id = PlayerBotExperimentId();
    dataset.episode_id = dataset.run_id;
    dataset.bot_guid = frame.BotGuid;
    dataset.bot_role = ToString(_role);
    dataset.bot_level = bot ? uint32(bot->getLevel()) : 0;
    dataset.policy_source = BotPolicySource::Rule;
    dataset.policy_version = "playerbot_rule_v1";
    dataset.timestamp_ms = PlayerBotNowMs();
    dataset.tick_id = seq;
    dataset.domain = "party_healing";
    dataset.situation = ToString(decision.Intent);
    dataset.observation_json = observation.str();
    dataset.semantic_json = "{\"role\":\"" + std::string(ToString(_role)) + "\"}";
    dataset.valid_action_mask_json = _lastHealerCandidateMaskJson;
    dataset.chosen_action_json = _lastHealerChosenActionJson;
    dataset.action_result = ToString(result);
    dataset.outcome_json = "{\"result\":\"" + std::string(ToString(result)) + "\"}";
    dataset.quality_flags_json = "{\"source\":\"playerbot_jsonl\"}";
    if (dataset.Validate())
        out << dataset.ToJson() << "\n";
}

void BotController::RecordProfessionFrame(BotProfessionFrame const& frame, Player* owner, Player* bot) const
{
    std::string path = sConfigMgr->GetStringDefault("PlayerBot.Record.Path", "dataset/raw/healer_frames_playerbot.jsonl");
    boost::filesystem::path outputPath(path);
    if (outputPath.has_parent_path())
        boost::filesystem::create_directories(outputPath.parent_path());

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out)
        return;

    uint64 seq = ++_sequence;
    std::ostringstream observation;
    observation << "{\"owner_guid\":" << frame.OwnerGuid.GetCounter()
                << ",\"class_id\":" << uint32(frame.ClassId)
                << ",\"spec_id\":" << frame.SpecId
                << ",\"profession_id\":\"" << JsonEscape(frame.Profession.ProfessionId)
                << "\",\"skill_id\":" << frame.Profession.SkillId
                << ",\"skill_current\":" << frame.Profession.SkillCurrent
                << ",\"skill_target\":" << frame.Profession.SkillTarget
                << ",\"known_recipe_count\":" << frame.Profession.KnownRecipes.size()
                << ",\"trainable_recipe_count\":" << frame.Profession.TrainableRecipes.size()
                << ",\"bag_free_slots\":" << frame.Profession.BagFreeSlots
                << ",\"gold\":" << frame.Inventory.Gold
                << ",\"material_count\":" << frame.Inventory.Materials.size() << "}";

    BotDatasetEvent dataset;
    dataset.run_id = PlayerBotRunId();
    dataset.experiment_id = PlayerBotExperimentId();
    dataset.episode_id = dataset.run_id;
    dataset.bot_guid = frame.BotGuid;
    dataset.bot_role = ToString(_role);
    dataset.bot_level = bot ? uint32(bot->getLevel()) : 0;
    dataset.policy_source = BotPolicySource::Rule;
    dataset.policy_version = "playerbot_rule_v1";
    dataset.timestamp_ms = PlayerBotNowMs();
    dataset.tick_id = seq;
    dataset.domain = "profession";
    dataset.situation = "profession_tick";
    dataset.observation_json = observation.str();
    dataset.semantic_json = "{\"profession_id\":\"" + JsonEscape(frame.Profession.ProfessionId) + "\"}";
    dataset.valid_action_mask_json = "{\"wait\":true}";
    dataset.chosen_action_json = "{\"type\":\"wait\",\"valid\":true}";
    dataset.action_result = "observed";
    dataset.outcome_json = "{\"skill_delta\":0,\"materials_spent_value\":0,\"time_spent_sec\":0}";
    dataset.quality_flags_json = "{\"source\":\"playerbot_jsonl\"}";
    if (dataset.Validate())
        out << dataset.ToJson() << "\n";
}

void BotController::RecordCombatFrame(BotCombatState const& frame, BotCombatDecision const& decision, ResolvedCombatAction const& action, BotActionResult result, Player* owner, Player* bot) const
{
    std::string path = sConfigMgr->GetStringDefault("PlayerBot.Record.Path", "dataset/raw/healer_frames_playerbot.jsonl");
    boost::filesystem::path outputPath(path);
    if (outputPath.has_parent_path())
        boost::filesystem::create_directories(outputPath.parent_path());

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out)
        return;

    uint64 seq = ++_sequence;
    std::ostringstream observation;
    observation << "{\"self\":{\"hp_pct\":" << frame.SelfHpPct
                << ",\"power_pct\":" << frame.SelfPowerPct
                << ",\"class_id\":" << uint32(frame.ClassId)
                << ",\"spec_id\":" << frame.SpecId
                << ",\"moving\":" << (frame.Moving ? "true" : "false")
                << ",\"casting\":" << (frame.Casting ? "true" : "false")
                << ",\"gcd_ready\":" << (frame.GcdReady ? "true" : "false") << "}"
                << ",\"target\":{\"guid\":" << frame.TargetGuid.GetCounter()
                << ",\"entry_id\":" << frame.TargetEntry
                << ",\"hp_pct\":" << frame.TargetHpPct
                << ",\"distance\":" << frame.TargetDistance
                << ",\"interruptible\":" << (frame.TargetInterruptible ? "true" : "false")
                << ",\"dead\":" << (frame.TargetDead ? "true" : "false")
                << ",\"lootable\":" << (frame.TargetLootable ? "true" : "false") << "}"
                << ",\"environment\":{\"nearby_hostile_count\":" << frame.NearbyHostileCount
                << ",\"elite_nearby\":" << (frame.EliteNearby ? "true" : "false")
                << ",\"extra_pull_risk\":" << frame.ExtraPullRisk << "}}";
    std::ostringstream chosen;
    chosen << "{\"type\":\"" << JsonEscape(action.Type)
           << "\",\"spell_id\":" << action.SpellId
           << ",\"target_guid\":" << action.TargetGuid.GetCounter()
           << ",\"intent\":\"" << ToString(decision.Intent)
           << "\",\"valid\":" << (action.Valid ? "true" : "false") << "}";

    BotDatasetEvent dataset;
    dataset.run_id = PlayerBotRunId();
    dataset.experiment_id = PlayerBotExperimentId();
    dataset.episode_id = dataset.run_id;
    dataset.bot_guid = bot ? bot->GetGUID() : _botGuid;
    dataset.bot_role = ToString(_role);
    dataset.bot_level = bot ? uint32(bot->getLevel()) : 0;
    dataset.policy_source = BotPolicySource::Rule;
    dataset.policy_version = "playerbot_rule_v1";
    dataset.timestamp_ms = PlayerBotNowMs();
    dataset.tick_id = seq;
    dataset.domain = "combat";
    dataset.situation = ToString(decision.Intent);
    dataset.observation_json = observation.str();
    dataset.semantic_json = "{\"runtime_role\":\"" + JsonEscape(_runtimeRole) + "\",\"class_spec\":\"" + JsonEscape(_classSpec) + "\",\"archetype\":\"" + std::string(ToString(CombatArchetypeForClass(frame.ClassId, _runtimeRole, _classSpec))) + "\"}";
    dataset.valid_action_mask_json = "{\"intents\":[\"pull_target\",\"maintain_rotation\",\"interrupt\",\"use_defensive\",\"heal_self\",\"move_to_range\",\"loot\",\"recover\",\"wait\"]}";
    dataset.chosen_action_json = chosen.str();
    dataset.action_result = ToString(result);
    dataset.outcome_json = "{\"target_dead_10s\":" + std::string(frame.TargetDead ? "true" : "false") + ",\"loot_success\":" + std::string(decision.Intent == BotCombatIntent::Loot && result == BotActionResult::Ok ? "true" : "false") + "}";
    dataset.quality_flags_json = "{\"source\":\"playerbot_jsonl\"}";
    if (dataset.Validate())
        out << dataset.ToJson() << "\n";
}

void BotController::RecordMovementFrame(BotMovementFrame const& frame, char const* policyMode, char const* intent, char const* action, bool valid, Player* owner, Player* bot) const
{
    std::string path = sConfigMgr->GetStringDefault("PlayerBot.Record.Path", "dataset/raw/healer_frames_playerbot.jsonl");
    boost::filesystem::path outputPath(path);
    if (outputPath.has_parent_path())
        boost::filesystem::create_directories(outputPath.parent_path());

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out)
        return;

    char const* resolvedAction = action && *action ? action : "wait";
    uint64 seq = ++_sequence;
    std::ostringstream observation;
    observation << "{\"self\":{\"position\":[" << frame.X << "," << frame.Y << "," << frame.Z << "]"
                << ",\"orientation\":" << frame.Orientation
                << ",\"moving\":" << (frame.Moving ? "true" : "false")
                << ",\"mounted\":" << (frame.Mounted ? "true" : "false")
                << ",\"in_combat\":" << (frame.InCombat ? "true" : "false")
                << ",\"hp_pct\":" << frame.HpPct
                << ",\"distance_to_leader\":" << frame.DistanceToLeader
                << ",\"distance_to_group_center\":" << frame.DistanceToGroupCenter
                << ",\"line_of_sight_to_leader\":" << (frame.LineOfSightToLeader ? "true" : "false") << "}"
                << ",\"navigation\":{\"current_path_length\":" << frame.CurrentPathLength
                << ",\"path_available\":" << (frame.PathAvailable ? "true" : "false")
                << ",\"stuck_score\":" << frame.StuckScore
                << ",\"last_progress_time_ms\":" << frame.LastProgressTimeMs << "}}";

    BotDatasetEvent dataset;
    dataset.run_id = PlayerBotRunId();
    dataset.experiment_id = PlayerBotExperimentId();
    dataset.episode_id = dataset.run_id;
    dataset.bot_guid = bot ? bot->GetGUID() : _botGuid;
    dataset.bot_role = ToString(_role);
    dataset.bot_level = bot ? uint32(bot->getLevel()) : 0;
    dataset.policy_source = BotPolicySource::Rule;
    dataset.policy_version = "playerbot_rule_v1";
    dataset.timestamp_ms = PlayerBotNowMs();
    dataset.tick_id = seq;
    dataset.domain = "movement";
    dataset.situation = intent && *intent ? intent : "movement_tick";
    dataset.observation_json = observation.str();
    dataset.semantic_json = "{\"policy_mode\":\"" + JsonEscape(policyMode ? policyMode : "follow") + "\"}";
    dataset.valid_action_mask_json = "{\"movement_actions\":true}";
    dataset.chosen_action_json = "{\"type\":\"" + JsonEscape(resolvedAction) + "\",\"valid\":" + std::string(valid ? "true" : "false") + "}";
    dataset.action_result = valid ? "ok" : "invalid";
    dataset.outcome_json = "{\"distance_to_leader_after_2s\":" + std::to_string(frame.DistanceToLeader) + ",\"stuck\":" + std::string(frame.StuckScore >= 1.0f ? "true" : "false") + "}";
    dataset.quality_flags_json = "{\"source\":\"playerbot_jsonl\"}";
    if (dataset.Validate())
        out << dataset.ToJson() << "\n";
}
