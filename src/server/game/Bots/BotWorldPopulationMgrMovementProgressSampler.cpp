#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"

#include "GameTime.h"
#include "Map.h"
#include "MotionMaster.h"
#include "Movement/Spline/MoveSpline.h"
#include "Player.h"

#include <chrono>

namespace
{
std::uint64_t ProgressNowMs()
{
    return std::uint64_t(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

namespace BotWorldMovement
{
void ObserveReceiptTaggedMovementProgress(Player const* bot)
{
    if (!bot)
        return;
    std::uint64_t const botGuid = bot->GetGUID().GetCounter();
    std::uint64_t const observedAtMs = ProgressNowMs();
    if (!MovementProgressDiagnostics().ObservationDue(botGuid, observedAtMs))
        return;

    NativeMovementProgressProbe probe;
    probe.ObservedAtMs = observedAtMs;
    probe.BotGuid = botGuid;
    probe.ActorAvailable = true;
    probe.ActorInWorld = bot->IsInWorld() && bot->GetMap();
    probe.ActorAlive = bot->IsAlive();
    probe.MapId = bot->GetMapId();
    probe.InstanceId = bot->GetInstanceId();
    probe.X = bot->GetPositionX();
    probe.Y = bot->GetPositionY();
    probe.Z = bot->GetPositionZ();
    probe.Moving = bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
    if (probe.ActorInWorld)
    {
        probe.FloorSampled = true;
        probe.FloorZ = bot->GetMap()->GetHeight(bot->GetPhaseShift(),
            probe.X, probe.Y, probe.Z + 2.0f, true, 8.0f);
        probe.FloorValid = probe.FloorZ > INVALID_HEIGHT;
    }
    MotionMaster const* motion = bot->GetMotionMaster();
    probe.CurrentMotionType = motion
        ? std::uint32_t(motion->GetCurrentMovementGeneratorType())
        : std::uint32_t(MAX_MOTION_TYPE);
    probe.ActiveMotionType = motion
        ? std::uint32_t(motion->GetMotionSlotType(MOTION_SLOT_ACTIVE))
        : std::uint32_t(MAX_MOTION_TYPE);
    probe.PointGeneratorActive = motion
        && motion->GetMotionSlotType(MOTION_SLOT_ACTIVE) == POINT_MOTION_TYPE;
    probe.SplineInitialized = bot->movespline
        && bot->movespline->Initialized();
    probe.SplineId = probe.SplineInitialized
        ? bot->movespline->GetId() : 0;
    probe.SplineFinalized = !bot->movespline
        || bot->movespline->Finalized();
    MovementProgressDiagnostics().Observe(probe);
}
}
