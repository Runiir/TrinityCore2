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
uint64 PlayerBotNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
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

bool HasNativeMotion(MotionMaster* motion, MovementGeneratorType expected)
{
    if (!motion)
        return false;

    return motion->GetMotionSlotType(MOTION_SLOT_ACTIVE) == expected
        || motion->GetCurrentMovementGeneratorType() == expected;
}

bool NativeMovementGeneratorActive(Player* bot, BotMovementMode mode)
{
    if (!bot)
        return false;

    MotionMaster* motion = bot->GetMotionMaster();
    switch (mode)
    {
        case BotMovementMode::Follow:
        case BotMovementMode::ReturnToGroup:
        case BotMovementMode::MoveSafe:
            return HasNativeMotion(motion, FOLLOW_MOTION_TYPE);
        case BotMovementMode::MoveTo:
        case BotMovementMode::Unstuck:
            return HasNativeMotion(motion, POINT_MOTION_TYPE);
        case BotMovementMode::Stay:
        case BotMovementMode::Stop:
            return HasNativeMotion(motion, IDLE_MOTION_TYPE);
    }

    return false;
}
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

bool BotController::ApplyMovementPolicy(BotActionExecutor& executor, Player* owner, Player* bot, BotMovementFrame const& movementFrame)
{
    if (!bot || !bot->IsInWorld())
        return false;
    if (_movementMode != BotMovementMode::Stop
        && bot->HasUnitState(UNIT_STATE_CASTING))
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
            request.DynamicTargetGuid = owner->GetGUID().GetRawValue();
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
            request.DynamicTargetGuid = owner->GetGUID().GetRawValue();
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

    // The lease is intentionally short, but the generator it admitted is
    // native and set-and-forget. Reconcile that receipt before evaluating a
    // fresh lease so expiry at the next decision cadence cannot resubmit the
    // same path or let a lower-priority request replace active hazard motion.
    bool const nativePathObserved = _nativeMovementPath.Active
        && SameScope(_nativeMovementPath.Path.MovementScope,
            request.MovementScope)
        && NativeMovementGeneratorActive(bot, _nativeMovementMode);
    if (_nativeMovementPath.Active && !nativePathObserved)
        _nativeMovementPath.Active = false;

    Lease arbitrationLease = _movementLease;
    if (nativePathObserved)
    {
        arbitrationLease = _nativeMovementPath.Path;
        arbitrationLease.ExpiresAtMs = request.ExpiresAtMs;
    }

    Decision const leaseDecision = Evaluate(arbitrationLease, request, nowMs);
    if (leaseDecision == Decision::RejectInvalid
        || leaseDecision == Decision::PreserveExisting)
        return false;

    BotMovementMode const submittedMode = _movementMode;
    if (nativePathObserved && MatchesNativePath(_nativeMovementPath, request))
    {
        Apply(_movementLease, request);
        return true;
    }

    Apply(_movementLease, request);
    bool commandSubmitted = false;

    auto rememberNativePath = [&]
    {
        _nativeMovementPath.Active = true;
        Apply(_nativeMovementPath.Path, request);
        // ExpiresAtMs belongs to the arbitration lease, not the native
        // generator. Keep the receipt explicitly independent of that clock.
        _nativeMovementPath.Path.ExpiresAtMs = 0;
        _nativeMovementMode = submittedMode;
    };

    if (movementFrame.StuckScore >= 1.0f || _movementMode == BotMovementMode::Unstuck)
    {
        executor.MoveUnstuck(owner, bot);
        commandSubmitted = true;
        rememberNativePath();
        _movementMode = BotMovementMode::Follow;
        return true;
    }

    if (_movementMode == BotMovementMode::Follow)
    {
        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, _runtimeRole.c_str());
        executor.MoveFollow(owner, bot, ProfileFollowDistance(profile));
        commandSubmitted = true;
    }
    else if (_movementMode == BotMovementMode::Stay)
    {
        executor.MoveStay(bot);
        commandSubmitted = true;
    }
    else if (_movementMode == BotMovementMode::Stop)
    {
        executor.MoveStop(bot);
        commandSubmitted = true;
    }
    else if (_movementMode == BotMovementMode::MoveTo && _movementTarget.Active)
    {
        executor.MoveTo(bot, _movementTarget.X, _movementTarget.Y, _movementTarget.Z);
        commandSubmitted = true;
    }
    else if (_movementMode == BotMovementMode::ReturnToGroup || _movementMode == BotMovementMode::MoveSafe)
    {
        executor.MoveFollow(owner, bot);
        commandSubmitted = true;
    }
    if (commandSubmitted)
        rememberNativePath();
    return true;
}
