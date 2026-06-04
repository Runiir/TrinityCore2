#include "Bots/BotController.h"
#include "Bots/BotMgr.h"
#include "Config.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupReference.h"
#include "Log.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Transport.h"
#include "Spell.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include <algorithm>
#include <boost/filesystem.hpp>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>

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
}

BotController::BotController(ObjectGuid ownerGuid, ObjectGuid botGuid, BotRole role)
    : _ownerGuid(ownerGuid), _botGuid(botGuid), _role(role), _policy(new RuleHealerBotPolicy())
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

    if (_movementMode == BotMovementMode::Stop)
    {
        if (_recording || sConfigMgr->GetBoolDefault("PlayerBot.Record.Enable", false))
            RecordMovementFrame(movementFrame, ToString(_movementMode), "stop", "stop", true, owner, bot);
        return;
    }

    BotRecentEvents recentEvents = sBotMgr->ConsumeRecentEvents(_botGuid);
    HealerFrame frame = BuildFrame(owner, bot, recentEvents);
    if (!IsHealerBotRole(_role))
    {
        if (_recording || sConfigMgr->GetBoolDefault("PlayerBot.Record.Enable", false))
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

    if (_recording || sConfigMgr->GetBoolDefault("PlayerBot.Record.Enable", false))
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
       << "\",\"class_spec_tag\":\"" << ToString(_role)
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

void BotController::RecordFrame(HealerFrame const& frame, HealerDecision const& decision, ResolvedBotAction const* action, BotActionResult result, Player* owner, Player* bot) const
{
    std::string path = sConfigMgr->GetStringDefault("PlayerBot.Record.Path", "dataset/raw/healer_frames_playerbot.jsonl");
    boost::filesystem::path outputPath(path);
    if (outputPath.has_parent_path())
        boost::filesystem::create_directories(outputPath.parent_path());

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out)
        return;

    Group* recordGroup = owner ? owner->GetGroup() : nullptr;
    std::string experimentId = sConfigMgr->GetStringDefault("PlayerBot.ExperimentId", "");

    out << "{\"seq\":" << ++_sequence
        << ",\"time\":" << GameTime::GetGameTime()
        << ",\"experiment_id\":\"" << JsonEscape(experimentId)
        << "\",\"party_guid\":\"" << (recordGroup ? recordGroup->GetGUID().ToString() : "")
        << "\",\"owner\":\"" << frame.OwnerGuid.ToString()
        << "\",\"owner_name\":\"" << JsonEscape(owner ? owner->GetName() : "")
        << "\",\"bot\":\"" << frame.BotGuid.ToString()
        << "\",\"bot_name\":\"" << JsonEscape(bot ? bot->GetName() : "")
        << "\",\"role\":\"" << ToString(_role)
        << "\",\"map\":" << frame.MapId
        << ",\"instance\":" << (bot ? bot->GetInstanceId() : 0)
        << ",\"bot_hp\":" << frame.BotHealthPct
        << ",\"bot_mana\":" << frame.BotManaPct
        << ",\"bot_cast\":" << frame.BotCastSpellId
        << ",\"bot_channel\":" << frame.BotChannelSpellId
        << ",\"bot_auras\":" << frame.BotAuraCount
        << ",\"bot_debuffs\":" << frame.BotDebuffCount
        << ",\"recent_damage_taken\":" << frame.RecentDamageTaken
        << ",\"recent_healing_done\":" << frame.RecentHealingDone
        << ",\"recent_healing_received\":" << frame.RecentHealingReceived
        << ",\"mode\":\"" << ToString(decision.Mode)
        << "\",\"intent\":\"" << ToString(decision.Intent)
        << "\",\"target\":\"" << decision.TargetGuid.ToString()
        << "\",\"result\":\"" << ToString(result)
        << "\",\"spell\":" << (action ? action->SpellId : 0)
        << ",\"action\":\"" << JsonEscape(action ? action->DebugName : "")
        << "\""
        << ",\"party\":[";

    for (std::size_t i = 0; i < frame.Party.size(); ++i)
    {
        HealerUnitFrame const& unit = frame.Party[i];
        if (i)
            out << ',';
        out << "{\"guid\":\"" << unit.Guid.ToString()
            << "\",\"name\":\"" << JsonEscape(unit.Name)
            << "\",\"role\":" << uint32(unit.Role)
            << ",\"subgroup\":" << uint32(unit.Subgroup)
            << ",\"hp\":" << uint32(unit.HealthPct)
            << ",\"dist\":" << unit.Distance
            << ",\"cast\":" << unit.CastSpellId
            << ",\"channel\":" << unit.ChannelSpellId
            << ",\"auras\":" << unit.AuraCount
            << ",\"debuffs\":" << unit.DebuffCount
            << ",\"recent_damage\":" << unit.RecentDamageTaken
            << ",\"recent_heal\":" << unit.RecentHealingReceived
            << ",\"alive\":" << (unit.Alive ? "true" : "false")
            << ",\"los\":" << (unit.LineOfSight ? "true" : "false")
            << ",\"owner\":" << (unit.IsOwner ? "true" : "false")
            << "}";
    }

    out << "]}\n";
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

    std::string experimentId = sConfigMgr->GetStringDefault("PlayerBot.ExperimentId", "");
    char const* resolvedAction = action && *action ? action : "wait";
    out << "{\"domain\":\"movement\""
        << ",\"subdomain\":\"follow\""
        << ",\"trigger\":\"movement_tick\""
        << ",\"seq\":" << ++_sequence
        << ",\"time\":" << GameTime::GetGameTime()
        << ",\"experiment_id\":\"" << JsonEscape(experimentId)
        << "\",\"actor\":{\"guid\":" << (bot ? bot->GetGUID().GetCounter() : 0)
        << ",\"is_bot\":true"
        << ",\"role\":\"" << ToString(_role) << "\"}"
        << ",\"task\":{\"task_type\":\"" << JsonEscape(policyMode ? policyMode : "follow")
        << "\",\"leader_guid\":" << (owner ? owner->GetGUID().GetCounter() : 0) << "}"
        << ",\"state\":{\"self\":{\"position\":[" << frame.X << "," << frame.Y << "," << frame.Z << "]"
        << ",\"orientation\":" << frame.Orientation
        << ",\"moving\":" << (frame.Moving ? "true" : "false")
        << ",\"mounted\":" << (frame.Mounted ? "true" : "false")
        << ",\"in_combat\":" << (frame.InCombat ? "true" : "false")
        << ",\"hp_pct\":" << frame.HpPct
        << ",\"distance_to_leader\":" << frame.DistanceToLeader
        << ",\"distance_to_group_center\":" << frame.DistanceToGroupCenter
        << ",\"line_of_sight_to_leader\":" << (frame.LineOfSightToLeader ? "true" : "false")
        << ",\"on_transport\":" << (frame.OnTransport ? "true" : "false")
        << ",\"indoors\":" << (frame.Indoors ? "true" : "false") << "}"
        << ",\"navigation\":{\"current_path_length\":" << frame.CurrentPathLength
        << ",\"path_available\":" << (frame.PathAvailable ? "true" : "false")
        << ",\"stuck_score\":" << frame.StuckScore
        << ",\"last_progress_time_ms\":" << frame.LastProgressTimeMs
        << ",\"nearby_hazard\":" << (frame.NearbyHazard ? "true" : "false")
        << ",\"safe_position_available\":" << (frame.SafePositionAvailable ? "true" : "false") << "}}"
        << ",\"policy_output\":{\"mode\":\"" << JsonEscape(policyMode ? policyMode : "")
        << "\",\"intent\":\"" << JsonEscape(intent ? intent : "") << "\"}"
        << ",\"resolved_action\":{\"type\":\"" << JsonEscape(resolvedAction)
        << "\",\"valid\":" << (valid ? "true" : "false") << "}"
        << ",\"outcome\":{\"distance_to_leader_after_2s\":" << frame.DistanceToLeader
        << ",\"stuck\":" << (frame.StuckScore >= 1.0f ? "true" : "false") << "}"
        << "}\n";
}
