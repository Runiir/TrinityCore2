#include "Bots/BotController.h"
#include "Bots/BotClassSpecActionProfile.h"
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

BotCombatArchetype CombatArchetypeForClass(uint8 classId, std::string const& runtimeRole)
{
    if (runtimeRole == "tank")
        return BotCombatArchetype::TankLikeMelee;
    if (runtimeRole == "healer")
        return BotCombatArchetype::HealerSolo;

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
    ApplyMovementPolicy(executor, owner, bot, movementFrame);
    bool shouldRecord = _recording || sConfigMgr->GetBoolDefault("PlayerBot.Record.Enable", false);
    if (shouldRecord)
        RecordProfessionFrame(BuildProfessionFrame(owner, bot), owner, bot);

    if (_movementMode == BotMovementMode::Stop)
    {
        if (shouldRecord)
            RecordMovementFrame(movementFrame, ToString(_movementMode), "stop", "stop", true, owner, bot);
        return;
    }

    BotRecentEvents recentEvents = sBotMgr->ConsumeRecentEvents(_botGuid);
    BotCombatState combatState = BuildCombatState(owner, bot, recentEvents);
    if (_runtimeRole == "healer" && TryResolveHealerAction(executor, owner, bot, recentEvents, shouldRecord, movementFrame))
        return;

    if (!_combatTargetGuid.IsEmpty() || combatState.InCombat || combatState.TargetLootable)
    {
        BotCombatDecision combatDecision = DecideSoloCombat(combatState);
        Unit* target = combatState.TargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, combatState.TargetGuid);
        ResolvedCombatAction combatAction = ResolveProfileCombat(combatDecision, combatState, bot, target);
        BotActionResult combatResult = executor.ExecuteCombat(owner, bot, combatAction);
        if (combatDecision.Intent == BotCombatIntent::Loot && combatResult == BotActionResult::Ok)
            ClearCombatTarget();

        if (shouldRecord)
        {
            RecordCombatFrame(combatState, combatDecision, combatAction, combatResult, owner, bot);
            RecordMovementFrame(movementFrame, ToString(_movementMode), ToString(combatDecision.Intent), combatAction.DebugName.c_str(), combatResult != BotActionResult::Disabled, owner, bot);
        }

        return;
    }

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
       << "\",\"combat_archetype\":\"" << ToString(bot ? CombatArchetypeForClass(bot->getClass(), _runtimeRole) : GetSoloCombatArchetype(_role))
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
       << ",\"archetype\":\"" << ToString(bot ? CombatArchetypeForClass(bot->getClass(), _runtimeRole) : GetSoloCombatArchetype(_role)) << "\"}"
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
    else if (state.TargetDistance > 5.0f && CombatArchetypeForClass(state.ClassId, _runtimeRole) != BotCombatArchetype::RangedCaster && CombatArchetypeForClass(state.ClassId, _runtimeRole) != BotCombatArchetype::RangedPhysical)
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
    BotActionCandidate* best = nullptr;
    for (BotActionCandidate& candidate : candidates)
    {
        if (candidate.Category == BotCombatActionCategory::HealFast
            || candidate.Category == BotCombatActionCategory::HealEfficient
            || candidate.Category == BotCombatActionCategory::HealAoe
            || candidate.Category == BotCombatActionCategory::DispelCleanse
            || candidate.Category == BotCombatActionCategory::ExternalDefensive)
        {
            candidate.RejectReason = "requires_ally_target";
            continue;
        }

        if (candidate.Category == BotCombatActionCategory::Taunt && target && target->GetVictim() == bot)
        {
            candidate.RejectReason = "threat_already_established";
            continue;
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

        candidate.Score = roleScore;
        candidate.Reason = "runtime_profile_role";
        if (!best || candidate.Score > best->Score)
            best = &candidate;
    }

    return best;
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
    action.TargetGuid = target->GetGUID();
    if ((best->Category == BotCombatActionCategory::Aoe || best->Category == BotCombatActionCategory::Cleave) && best->SpellId)
        if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(best->SpellId))
            if (spellInfo->GetMaxRange(false) <= 5.0f)
                action.TargetGuid = bot->GetGUID();
    action.DebugName = BotCombatActionCatalog::ToString(best->Category);
    return action;
}

bool BotController::TryResolveHealerAction(BotActionExecutor& executor, Player* owner, Player* bot, BotRecentEvents const& recentEvents, bool shouldRecord, BotMovementFrame const& movementFrame)
{
    HealerFrame frame = BuildFrame(owner, bot, recentEvents);
    HealerDecision decision = _policy->Decide(frame);
    if (decision.Intent == HealerIntent::Wait || decision.TargetGuid.IsEmpty())
        return false;

    Unit* target = ObjectAccessor::GetUnit(*bot, decision.TargetGuid);
    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, "healer");
    ResolvedBotAction action;
    action.Intent = decision.Intent;
    action.TargetGuid = decision.TargetGuid;
    action.DebugName = "no_valid_healer_action";

    auto acceptsIntent = [&decision](BotCombatActionCategory category)
    {
        switch (decision.Intent)
        {
            case HealerIntent::AoeHeal:
                return category == BotCombatActionCategory::HealAoe || category == BotCombatActionCategory::HealFast || category == BotCombatActionCategory::HealEfficient;
            case HealerIntent::FastSingleHeal:
            case HealerIntent::InstantSingleHeal:
            case HealerIntent::BigSingleHeal:
            case HealerIntent::ExternalDefensive:
                return category == BotCombatActionCategory::HealFast || category == BotCombatActionCategory::ExternalDefensive || category == BotCombatActionCategory::HealEfficient;
            case HealerIntent::EfficientSingleHeal:
                return category == BotCombatActionCategory::HealEfficient || category == BotCombatActionCategory::HealFast;
            case HealerIntent::Dispel:
                return category == BotCombatActionCategory::DispelCleanse;
            default:
                return false;
        }
    };

    BotActionProfileSpell const* best = nullptr;
    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        if (!spell.SpellId || !acceptsIntent(spell.Category))
            continue;
        if (!best || spell.HealingWeight + spell.SurvivalWeight > best->HealingWeight + best->SurvivalWeight)
            best = &spell;
    }

    if (best)
    {
        action.SpellId = best->SpellId;
        action.DebugName = BotCombatActionCatalog::ToString(best->Category);
    }

    BotActionResult result = best ? executor.Execute(owner, bot, action) : BotActionResult::NoAction;
    if (shouldRecord)
    {
        RecordFrame(frame, decision, &action, result, owner, bot);
        RecordMovementFrame(movementFrame, ToString(_movementMode), ToString(decision.Intent), action.DebugName.c_str(), result != BotActionResult::Disabled, owner, bot);
    }

    return result == BotActionResult::Ok || (target && best);
}

void BotController::ApplyMovementPolicy(BotActionExecutor& executor, Player* owner, Player* bot, BotMovementFrame const& movementFrame)
{
    if (movementFrame.StuckScore >= 1.0f || _movementMode == BotMovementMode::Unstuck)
    {
        executor.MoveUnstuck(owner, bot);
        _movementMode = BotMovementMode::Follow;
        return;
    }

    if (_movementMode == BotMovementMode::Follow)
        executor.MoveFollow(owner, bot);
    else if (_movementMode == BotMovementMode::Stay)
        executor.MoveStay(bot);
    else if (_movementMode == BotMovementMode::Stop)
        executor.MoveStop(bot);
    else if (_movementMode == BotMovementMode::MoveTo && _movementTarget.Active)
        executor.MoveTo(bot, _movementTarget.X, _movementTarget.Y, _movementTarget.Z);
    else if (_movementMode == BotMovementMode::ReturnToGroup || _movementMode == BotMovementMode::MoveSafe)
        executor.MoveFollow(owner, bot);
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
    dataset.valid_action_mask_json = "{\"healer_actions\":true}";
    dataset.chosen_action_json = chosen.str();
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
    dataset.semantic_json = "{\"runtime_role\":\"" + JsonEscape(_runtimeRole) + "\",\"class_spec\":\"" + JsonEscape(_classSpec) + "\",\"archetype\":\"" + std::string(ToString(CombatArchetypeForClass(frame.ClassId, _runtimeRole))) + "\"}";
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
