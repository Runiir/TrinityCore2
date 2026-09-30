/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#include "MoveSplineInit.h"
#include "MovementPackets.h"
#include "MoveSpline.h"
#include "MovementPacketBuilder.h"
#include "Creature.h"
#include "G3DPosition.hpp"
#include "Unit.h"
#include "PathGenerator.h"
#include "Transport.h"
#include "Opcodes.h"
#include "WorldPacket.h"
#include "GameObject.h"
#include "GameObjectModel.h"
#include "Log.h"
#include "Map.h"
#include "ModelIgnoreFlags.h"
#include "PassengerBodyTrajectory.h"
#include "PassengerSplineCollision.h"
#include "PassengerWalkProof.h"

#include <G3D/Ray.h>

namespace
{
    enum class PassengerClip
    {
        NotApplicable,
        Emitted,
        Refused
    };

    // A player passenger's spline (a bot's chase or point path) against its
    // own transport's collision model (PassengerSplineCollision.h), the
    // whole body proved along what is kept (PassengerWalkProof.h); a swept
    // spline is emitted with linear interpolation, as proved; one that moves
    // nothing (an orientation-only facing, Unit::SetFacingTo*) is emitted as
    // it is, with no ray cast. Falls, jumps, knockback arcs and animations are
    // the effects' own trajectories and a vehicle seat is not a surface: those
    // are left alone, as is every creature. Fail closed: a passenger whose
    // transport gameobject or model cannot be resolved emits nothing; a model
    // with collision disabled stops nothing, for a client neither.
    PassengerClip ClipPassengerSpline(Unit* unit, Movement::MoveSplineInitArgs& args)
    {
        if (!unit->IsPlayer() || unit->GetVehicle() || !unit->GetTransport())
            return PassengerClip::NotApplicable;
        if (args.flags.Falling || args.flags.Parabolic || args.flags.Animation
            || args.flags.Cyclic || args.path.size() < 2)
            return PassengerClip::NotApplicable;
        TransportBase const* transport = unit->GetTransport();
        Map* map = unit->IsInWorld() ? unit->GetMap() : nullptr;
        GameObject const* object = map ? map->GetGameObject(transport->GetTransportGUID()) : nullptr;
        if (!object || !object->m_model)
        {
            TC_LOG_DEBUG("movement.spline", "Passenger spline of %s refused: transport model unavailable",
                unit->GetGUID().ToString().c_str());
            return PassengerClip::Refused;
        }
        if (!object->m_model->isCollisionEnabled())
            return PassengerClip::Emitted;

        // The spline's points are transport offsets; the sweep runs in world
        // space at the transport's current position.
        std::vector<G3D::Vector3> world(args.path.begin(), args.path.end());
        for (G3D::Vector3& point : world)
            transport->CalculatePassengerPosition(point.x, point.y, point.z);
        GameObjectModel const& model = *object->m_model;
        PhaseShift const& phase = unit->GetPhaseShift();
        auto nearestHit = [&model, &phase](G3D::Vector3 const& origin, G3D::Vector3 const& direction,
            float maxDistance)
        {
            float distance = maxDistance;
            // Not stopAtFirstHit: the first triangle a bounding interval
            // hierarchy meets need not be the nearest.
            return model.intersectRay(G3D::Ray::fromOriginAndDirection(origin, direction), distance,
                false, phase, VMAP::ModelIgnoreFlags::Nothing) ? distance : -1.0f;
        };
        using namespace Movement::PassengerCollision;
        float const radius = unit->GetFloatValue(UNIT_FIELD_BOUNDINGRADIUS);
        // The whole body along the kept path and at its end
        // (PassengerWalkProof.h): the end moves back until it is proved,
        // or nothing is emitted.
        auto blocked = [&model, &phase](G3D::Vector3 const& origin, G3D::Vector3 const& direction, float length)
        {
            float distance = length;
            return model.intersectRay(G3D::Ray::fromOriginAndDirection(origin, direction), distance,
                true, phase, VMAP::ModelIgnoreFlags::Nothing);
        };
        // A spline that moves nothing (a facing) is neither swept nor proved:
        // no ray, and a unit standing in a wall can still turn.
        Movement::PassengerWalk::Settled const settled = Movement::PassengerWalk::ProveWalk(world, radius,
            unit->GetCollisionHeight(), nearestHit, blocked);
        if (settled.SweepBlocked)
        {
            TC_LOG_DEBUG("movement.spline", "Passenger spline of %s refused: transport collision within %.2f yd",
                unit->GetGUID().ToString().c_str(), settled.SweepYards);
            return PassengerClip::Refused;
        }
        Result const& proved = settled.Clip;
        if (proved.Kind == Verdict::Blocked)
        {
            TC_LOG_DEBUG("movement.spline", "Passenger spline of %s refused: body meets transport collision within %.2f yd (%u rays%s)",
                unit->GetGUID().ToString().c_str(), settled.SweepYards, settled.Rays,
                settled.Escape ? ", standing in it" : "");
            return PassengerClip::Refused;
        }
        // The proof covers the straight segments between the points: the
        // spline (clipped or not) interpolates exactly those, never a
        // Catmull-Rom curve that could leave them.
        EmitProvedPath(args, proved);
        if (proved.Kind == Verdict::Clipped)
            TC_LOG_DEBUG("movement.spline", "Passenger spline of %s clipped at transport collision after %.2f yd (%s, %u rays)",
                unit->GetGUID().ToString().c_str(), proved.KeptYards,
                settled.BackedOff ? "body proof" : "sweep", settled.Rays);
        return PassengerClip::Emitted;
    }

    // A player passenger's fall or jump arc (the Falling and Parabolic
    // splines ClipPassengerSpline leaves alone: the effect owns the
    // trajectory, which is not clipped) is launched only if the whole body
    // stays clear of its transport's model along it and at its end
    // (PassengerBodyTrajectory.h): sampled as the server will run it, from
    // the validated arguments. An obstructed one is refused, fail closed, as
    // an unresolved model is; a fall onto a floor beside a skirt or a wall
    // must be avoided by whoever launched it (the bots' step-off proves it
    // first, BotLedgeDropBodyClearance.h). The falling flag and fall time
    // MotionMaster::MoveFall sets before the launch stay set by a refusal: the
    // bots' fall launches roll them back (BotFallAdmission.h).
    PassengerClip ProvePassengerEffectSpline(Unit* unit, Movement::MoveSplineInitArgs const& args)
    {
        if (!unit->IsPlayer() || unit->GetVehicle() || !unit->GetTransport())
            return PassengerClip::NotApplicable;
        if (!(args.flags.Falling || args.flags.Parabolic) || args.flags.Animation
            || args.flags.Cyclic || args.path.size() < 2)
            return PassengerClip::NotApplicable;
        TransportBase const* transport = unit->GetTransport();
        Map* map = unit->IsInWorld() ? unit->GetMap() : nullptr;
        GameObject const* object = map ? map->GetGameObject(transport->GetTransportGUID()) : nullptr;
        if (!object || !object->m_model)
        {
            TC_LOG_DEBUG("movement.spline", "Passenger effect spline of %s refused: transport model unavailable",
                unit->GetGUID().ToString().c_str());
            return PassengerClip::Refused;
        }
        if (!object->m_model->isCollisionEnabled())
            return PassengerClip::Emitted;

        using namespace Movement::BodyTrajectory;
        Movement::MoveSpline run;
        run.Initialize(args);
        std::vector<G3D::Vector3> samples = SampleSpline<G3D::Vector3>(run);
        for (G3D::Vector3& point : samples)
            transport->CalculatePassengerPosition(point.x, point.y, point.z);
        Chords const chords = ReduceToChords(samples);
        std::vector<G3D::Vector3> trajectory;
        trajectory.reserve(chords.Kept.size());
        for (std::size_t const index : chords.Kept)
            trajectory.push_back(samples[index]);
        GameObjectModel const& model = *object->m_model;
        PhaseShift const& phase = unit->GetPhaseShift();
        auto blocked = [&model, &phase](G3D::Vector3 const& origin, G3D::Vector3 const& direction,
            float length)
        {
            float distance = length;
            return model.intersectRay(G3D::Ray::fromOriginAndDirection(origin, direction), distance,
                true, phase, VMAP::ModelIgnoreFlags::Nothing);
        };
        Proof const proof = ProveTrajectory(trajectory, MakeBody(
            unit->GetFloatValue(UNIT_FIELD_BOUNDINGRADIUS), unit->GetCollisionHeight(),
            chords.InflationYards), blocked);
        if (proof.Clear())
            return PassengerClip::Emitted;
        TC_LOG_DEBUG("movement.spline", "Passenger %s spline of %s refused: body meets transport collision %s (piece %u, %u rays)",
            args.flags.Falling ? "fall" : "jump", unit->GetGUID().ToString().c_str(),
            proof.Kind == Obstruction::Landing ? "at its end" : "on the way", uint32(proof.Piece), proof.Rays);
        return PassengerClip::Refused;
    }
}

namespace Movement
{
    UnitMoveType SelectSpeedType(uint32 moveFlags)
    {
        if (moveFlags & MOVEMENTFLAG_FLYING)
        {
            if (moveFlags & MOVEMENTFLAG_BACKWARD /*&& speed_obj.flight >= speed_obj.flight_back*/)
                return MOVE_FLIGHT_BACK;
            else
                return MOVE_FLIGHT;
        }
        else if (moveFlags & MOVEMENTFLAG_SWIMMING)
        {
            if (moveFlags & MOVEMENTFLAG_BACKWARD /*&& speed_obj.swim >= speed_obj.swim_back*/)
                return MOVE_SWIM_BACK;
            else
                return MOVE_SWIM;
        }
        else if (moveFlags & MOVEMENTFLAG_WALKING)
        {
            //if (speed_obj.run > speed_obj.walk)
            return MOVE_WALK;
        }
        else if (moveFlags & MOVEMENTFLAG_BACKWARD /*&& speed_obj.run >= speed_obj.run_back*/)
            return MOVE_RUN_BACK;

        // Flying creatures use MOVEMENTFLAG_CAN_FLY or MOVEMENTFLAG_DISABLE_GRAVITY
        // Run speed is their default flight speed.
        return MOVE_RUN;
    }

    int32 MoveSplineInit::Launch()
    {
        MoveSpline& move_spline = *unit->movespline;

        bool transport = !unit->GetTransGUID().IsEmpty();
        auto recordLaunch = [&](bool succeeded)
        {
            if (!_launchContext)
                return;
            _launchContext.Observer->OnSplineLaunch(_launchContext,
                args.path, transport
                    ? NativePathLaunchCoordinateSpace::TransportOffset
                    : NativePathLaunchCoordinateSpace::World,
                succeeded, move_spline.Finalized(),
                succeeded && move_spline.Initialized(),
                succeeded ? move_spline.GetId() : 0,
                succeeded ? move_spline.FinalDestination().x : 0.0f,
                succeeded ? move_spline.FinalDestination().y : 0.0f,
                succeeded ? move_spline.FinalDestination().z : 0.0f,
                unit->GetPositionX(),
                unit->GetPositionY(), unit->GetPositionZ());
        };
        Location real_position;
        // there is a big chance that current position is unknown if current state is not finalized, need compute it
        // this also allows calculate spline position and update map position in much greater intervals
        // Don't compute for transport movement if the unit is in a motion between two transports
        if (!move_spline.Finalized() && move_spline.onTransport == transport)
            real_position = move_spline.ComputePosition();
        else
        {
            Position const* pos;
            if (!transport)
                pos = unit;
            else
                pos = &unit->m_movementInfo.transport.pos;

            real_position.x = pos->GetPositionX();
            real_position.y = pos->GetPositionY();
            real_position.z = pos->GetPositionZ();
            real_position.orientation = unit->GetOrientation();
        }

        // should i do the things that user should do? - no.
        if (args.path.empty())
        {
            recordLaunch(false);
            return 0;
        }

        // correct first vertex
        args.path[0] = real_position;
        args.initialOrientation = real_position.orientation;

        // The emitted path, as the unit would walk it from where it is now,
        // respects its transport's collision: a wall ends it, as it stops a
        // client, and a surface in the way at once emits nothing (the unit
        // stops instead of finishing an older spline into it).
        if (transport && ClipPassengerSpline(unit, args) == PassengerClip::Refused)
        {
            unit->StopMoving();
            recordLaunch(false);
            return 0;
        }
        args.flags.Enter_Cycle = args.flags.Cyclic;

        uint32 moveFlags = unit->m_movementInfo.GetMovementFlags();
        if (!args.flags.Backward)
            moveFlags = (moveFlags & ~MOVEMENTFLAG_BACKWARD) | MOVEMENTFLAG_FORWARD;
        else
            moveFlags = (moveFlags & ~MOVEMENTFLAG_FORWARD) | MOVEMENTFLAG_BACKWARD;

        if (moveFlags & MOVEMENTFLAG_ROOT)
            moveFlags &= ~MOVEMENTFLAG_MASK_MOVING;

        if (!args.HasVelocity)
        {
            // If spline is initialized with SetWalk method it only means we need to select
            // walk move speed for it but not add walk flag to unit
            uint32 moveFlagsForSpeed = moveFlags;
            if (args.walk)
                moveFlagsForSpeed |= MOVEMENTFLAG_WALKING;
            else
                moveFlagsForSpeed &= ~MOVEMENTFLAG_WALKING;

            args.velocity = unit->GetSpeed(SelectSpeedType(moveFlagsForSpeed));
            if (Creature* creature = unit->ToCreature())
                if (creature->HasSearchedAssistance())
                    args.velocity *= 0.66f;
        }

        if (!args.Validate(unit))
        {
            recordLaunch(false);
            return 0;
        }

        // A passenger's fall or jump arc, as it will run, keeps the body clear
        // of its transport, or nothing is launched.
        if (transport && ProvePassengerEffectSpline(unit, args) == PassengerClip::Refused)
        {
            unit->StopMoving();
            recordLaunch(false);
            return 0;
        }

        // Every proof and the validation have passed: only now does the unit's
        // spline change, frame included. A refusal above stops the unit's
        // current spline in that spline's own frame (Unit::UpdateSplinePosition
        // reads onTransport: a world-frame spline read as transport offsets
        // relocated the unit, (101, 202, 12) to (201, 402, 22) on a transport
        // at (100, 200, 10)), and a launch that fails leaves it untouched.
        move_spline.onTransport = transport;
        unit->m_movementInfo.SetMovementFlags(moveFlags);
        move_spline.Initialize(args);

        WorldPackets::Movement::MonsterMove packet(transport);
        packet.MoverGUID = unit->GetGUID();
        packet.Pos = Position(real_position.x, real_position.y, real_position.z, real_position.orientation);
        packet.InitializeSplineData(move_spline);

        if (unit->m_movementInfo.HasExtraMovementFlag(MOVEMENTFLAG2_IS_VEHICLE_EXIT_VOLUNTARY))
            packet.SplineData.Move.VehicleExitVoluntary = true;

        if (transport)
        {
            packet.SplineData.Move.TransportGUID = unit->GetTransGUID();
            packet.SplineData.Move.VehicleSeat = unit->GetTransSeat();
        }

        unit->SendMessageToSet(packet.Write(), true);

        recordLaunch(true);

        return move_spline.Duration();
    }

    void MoveSplineInit::Stop()
    {
        MoveSpline& move_spline = *unit->movespline;

        // No need to stop if we are not moving
        if (move_spline.Finalized())
            return;

        bool transport = !unit->GetTransGUID().IsEmpty();
        Location loc;
        if (move_spline.onTransport == transport)
            loc = move_spline.ComputePosition();
        else
        {
            Position const* pos;
            if (!transport)
                pos = unit;
            else
                pos = &unit->m_movementInfo.transport.pos;

            loc.x = pos->GetPositionX();
            loc.y = pos->GetPositionY();
            loc.z = pos->GetPositionZ();
            loc.orientation = unit->GetOrientation();
        }

        args.flags = MoveSplineFlagEnum::Done;
        unit->m_movementInfo.RemoveMovementFlag(MOVEMENTFLAG_FORWARD);
        move_spline.onTransport = transport;
        move_spline.Initialize(args);

        WorldPackets::Movement::MonsterMove packet(transport);
        packet.MoverGUID = unit->GetGUID();
        packet.Pos = Position(loc.x, loc.y, loc.z, loc.orientation);
        packet.SplineData.ID = move_spline.GetId();
        packet.SplineData.Move.Face = MONSTER_MOVE_STOP;

        if (transport)
        {
            packet.SplineData.Move.TransportGUID = unit->GetTransGUID();
            packet.SplineData.Move.VehicleSeat = unit->GetTransSeat();
        }
        unit->SendMessageToSet(packet.Write(), true);
    }

    MoveSplineInit::MoveSplineInit(Unit* m,
        NativePathLaunchContext launchContext) : unit(m),
        _launchContext(launchContext)
    {
        args.splineId = splineIdGen.NewId();
        // Elevators also use MOVEMENTFLAG_ONTRANSPORT but we do not keep track of their position changes
        args.TransformForTransport = !unit->GetTransGUID().IsEmpty();
        // mix existing state into new
        args.walk = unit->HasUnitMovementFlag(MOVEMENTFLAG_WALKING);
        args.flags.CanSwim = unit->CanSwim();
        args.flags.Flying = unit->HasUnitMovementFlag(MovementFlags(MOVEMENTFLAG_CAN_FLY | MOVEMENTFLAG_DISABLE_GRAVITY));
        args.flags.SmoothGroundPath = !args.flags.Flying && !args.flags.Steering; // enabled by default, CatmullRom mode or client config "pathSmoothing" will disable this
    }

    MoveSplineInit::~MoveSplineInit() = default;

    void MoveSplineInit::SetFacing(Vector3 const& spot)
    {
        TransportPathTransform transform(unit, args.TransformForTransport);
        Vector3 finalSpot = transform(spot);
        args.facing.f.x = finalSpot.x;
        args.facing.f.y = finalSpot.y;
        args.facing.f.z = finalSpot.z;
        args.facing.type = MONSTER_MOVE_FACING_SPOT;
    }

    void MoveSplineInit::SetFacing(float x, float y, float z)
    {
        SetFacing({ x, y, z });
    }

    void MoveSplineInit::SetFacing(Unit const* target)
    {
        args.facing.angle = unit->GetAngle(target);
        args.facing.target = target->GetGUID();
        args.facing.type = MONSTER_MOVE_FACING_TARGET;
    }

    void MoveSplineInit::SetFacing(float angle)
    {
        if (args.TransformForTransport)
        {
            if (Unit* vehicle = unit->GetVehicleBase())
                angle -= vehicle->GetOrientation();
            else if (TransportBase* transport = unit->GetTransport())
                angle -= transport->GetTransportOrientation();
        }

        args.facing.angle = G3D::wrap(angle, 0.f, (float)G3D::twoPi());
        args.facing.type = MONSTER_MOVE_FACING_ANGLE;
    }

    void MoveSplineInit::MovebyPath(PointsArray const& controls, int32 path_offset)
    {
        args.path_Idx_offset = path_offset;
        args.path.resize(controls.size());
        std::transform(controls.begin(), controls.end(), args.path.begin(), TransportPathTransform(unit, args.TransformForTransport));
    }

    void MoveSplineInit::MoveTo(Vector3 const& start, Vector3 const& dest, bool generatePath, bool forceDestination)
    {
        if (generatePath)
        {
            PathGenerator path(unit);
            bool result = path.CalculatePath(start, dest, forceDestination);
            bool const useSecondPath = result
                && !(path.GetPathType() & PATHFIND_NOPATH);
            if (_launchContext)
                _launchContext.Observer->OnSplinePreparation(_launchContext,
                    true, result, path.GetPathType(),
                    path.GetPath(), !useSecondPath, !useSecondPath);
            if (useSecondPath)
            {
                MovebyPath(path.GetPath());
                return;
            }
        }
        else if (_launchContext)
            _launchContext.Observer->OnSplinePreparation(_launchContext,
                false, false, 0, {}, true, false);

        args.path_Idx_offset = 0;
        args.path.resize(2);
        TransportPathTransform transform(unit, args.TransformForTransport);
        args.path[1] = transform(dest);
    }

    void MoveSplineInit::MoveTo(float x, float y, float z, bool generatePath, bool forceDestination)
    {
        MoveTo(PositionToVector3(unit->GetPosition()), G3D::Vector3(x, y, z), generatePath, forceDestination);
    }

    void MoveSplineInit::MoveTo(Vector3 const& dest, bool generatePath, bool forceDestination)
    {
        MoveTo(PositionToVector3(unit->GetPosition()), dest, generatePath, forceDestination);
    }

    void MoveSplineInit::SetFall()
    {
        args.flags.Falling = true;
        args.flags.FallingSlow = unit->HasUnitMovementFlag(MOVEMENTFLAG_FALLING_SLOW);
    }

    Vector3 TransportPathTransform::operator()(Vector3 input)
    {
        if (_transformForTransport)
            if (TransportBase* transport = _owner->GetDirectTransport())
                transport->CalculatePassengerOffset(input.x, input.y, input.z);

        return input;
    }
}
