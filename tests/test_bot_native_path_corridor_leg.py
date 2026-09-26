"""Route moves walk a native corridor longer than the smoothed-path cap in legs.

Round 3 evidence (blackwing_descent_10n atramedes_c0; request in
.git/round4_patches/atramedes/lower_wing_runback_path_request.md): two
resurrected melee at (-193.14, -227.53, 76.65) could not walk to the
south_spirits anchor (146.87, -259.78, 74.91), 341 yd away. For ten minutes
every route move was rejected route_destination_unreachable with planner type
10 (NOPATH | SHORTCUT). PathGenerator smooths a walk into at most 74 points
spaced 4 yd apart (about 296 yd) and refuses anything longer with
PathEndpointResult::Capacity. An offline Detour probe finds a complete
72-polygon corridor of 437.7 yd.

An ordinary route move refused for capacity now asks PathGenerator for the
straight (corner) corridor to the same destination and walks it in legs. Each
leg ends on that corridor, at most 220 yd along it and at least 40 yd from the
actor. Only the planner's existing complete native path proof admits a leg,
and the move itself is an ordinary MovePoint with generatePath=true.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src/server/game/Bots"
HEADER = BOT / "BotWorldPopulationMgrNativePathCorridorLeg.h"
PLANNER = BOT / "BotWorldPopulationMgrMovementPlanner.cpp"
PATH_GENERATOR = ROOT / "src/server/game/Movement/PathGenerator.h"
SMOOTH = ROOT / "src/server/game/Movement/PathGeneratorSmooth.cpp"
DETOUR = ROOT / "dep/recastnavigation/Detour"
# data/ is DVC-managed and not in git; a scratch copy may point at a checkout.
MMAPS = Path(os.environ.get("TRINITY_MMAPS_DIR", ROOT / "data/mmaps"))
INCLUDES = ["src/server/game", "src/common"]


def _compile_and_run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run(
        [str(binary)], check=True, cwd=ROOT, capture_output=True, text=True
    ).stdout


def _path_generator_define(name: str) -> str:
    match = re.search(rf"^#define\s+{name}\s+(\S+)", PATH_GENERATOR.read_text(), re.M)
    assert match, name
    return match.group(1)


def test_header_mirrors_path_generator_point_capacity():
    header = HEADER.read_text(encoding="utf-8")
    capacity = int(_path_generator_define("MAX_POINT_PATH_LENGTH"))
    step = float(_path_generator_define("SMOOTH_PATH_STEP_SIZE").rstrip("f"))
    assert (capacity, step) == (74, 4.0)
    assert f"NativeCorridorSmoothPointCapacity = {capacity};" in header
    assert f"NativeCorridorSmoothStepYards = {step:.1f}f;" in header
    assert "74 x 4 = 296 yd" in header
    distances = re.search(r"NativeCorridorLegDistances\{\s*([^}]*)\}", header).group(1)
    values = [float(value.strip().rstrip("f")) for value in distances.split(",")]
    assert values == sorted(values, reverse=True) and values[0] == 220.0
    assert values[0] < capacity * step
    assert "NativeCorridorLegMinimumYards = 40.0f;" in header
    # Pure header: no Detour, map, or movement dependency.
    assert re.findall(r"#include\s+[<\"]([^>\"]+)", header) == ["array", "cmath", "cstddef", "vector"]
    for path in (HEADER, PLANNER):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000


def test_corridor_leg_sampling_and_candidates(tmp_path):
    output = _compile_and_run(tmp_path, r'''
#include "Bots/BotWorldPopulationMgrNativePathCorridorLeg.h"
#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>
#include <vector>
using namespace BotWorldMovement;
struct P { float x, y, z; };
bool near(float a, float b) { return std::fabs(a - b) < 1e-3f; }
bool near(P a, P b) { return near(a.x, b.x) && near(a.y, b.y) && near(a.z, b.z); }
int main()
{
    // Cumulative polyline distance.
    std::vector<P> const small{ { 0, 0, 0 }, { 3, 4, 0 }, { 3, 4, 12 } };
    std::vector<float> const cumulative = NativeCorridorCumulativeDistances(small);
    assert(cumulative.size() == 3 && near(cumulative[0], 0) && near(cumulative[1], 5)
        && near(cumulative[2], 17));
    assert(NativeCorridorCumulativeDistances(std::vector<P>{}).empty());

    // Interpolation at d, clamped to [0, total]; never extrapolates.
    P out{ 99, 99, 99 };
    assert(NativeCorridorPointAtDistance(small, cumulative, 2.5f, out) && near(out, P{ 1.5f, 2, 0 }));
    assert(NativeCorridorPointAtDistance(small, cumulative, 11.0f, out) && near(out, P{ 3, 4, 6 }));
    assert(NativeCorridorPointAtDistance(small, cumulative, 0.0f, out) && near(out, small.front()));
    assert(NativeCorridorPointAtDistance(small, cumulative, 17.0f, out) && near(out, small.back()));
    out = P{ 99, 99, 99 };
    assert(!NativeCorridorPointAtDistance(small, cumulative, 17.01f, out));
    assert(!NativeCorridorPointAtDistance(small, cumulative, -0.01f, out));
    assert(!NativeCorridorPointAtDistance(small, cumulative,
        std::numeric_limits<float>::quiet_NaN(), out));
    assert(near(out, P{ 99, 99, 99 }));
    assert(!NativeCorridorPointAtDistance(std::vector<P>{ { 0, 0, 0 } },
        std::vector<float>{ 0 }, 0.0f, out));

    // The round-3 Atramedes corridor length: 437.7 yd of corner polyline.
    std::vector<P> const corridor{ { 0, 0, 0 }, { 150, 0, 0 }, { 150, 200, 0 }, { 237.7f, 200, 0 } };
    float const total = NativeCorridorCumulativeDistances(corridor).back();
    assert(near(total, 437.7f) && total > NativeCorridorSmoothCapacityYards);
    auto const candidates = BuildNativeCorridorLegCandidates(corridor);
    assert(candidates.size() == 6);
    assert(!candidates[0].Corner && near(candidates[0].CorridorDistance, 220.0f));
    assert(near(candidates[0].Position, P{ 150, 70, 0 }));
    float const expected[] = { 220, 180, 140, 100, 60 };
    for (int i = 0; i < 5; ++i)
        assert(!candidates[i].Corner && near(candidates[i].CorridorDistance, expected[i]));
    // Interior corners inside [40, 220] follow; the 350 yd corner and the end do not.
    assert(candidates[5].Corner && near(candidates[5].CorridorDistance, 150.0f)
        && near(candidates[5].Position, corridor[1]));

    // Every candidate is strictly inside the corridor, within [min, max] leg,
    // and each group is in decreasing corridor distance.
    std::vector<std::vector<P>> const shapes{
        corridor,
        { { 0, 0, 0 }, { 150, 0, 0 } },
        { { 0, 0, 0 }, { 60, 0, 0 }, { 60, 60, 0 }, { 120, 60, 0 }, { 120, 120, 5 }, { 300, 120, 5 } },
        { { 0, 0, 0 }, { 45, 0, 0 }, { 45, 5, 0 } },
        { { 0, 0, 0 }, { 30, 0, 0 } },
        { { 0, 0, 0 }, { 60, 0, 0 } },
    };
    for (auto const& shape : shapes)
    {
        float const length = NativeCorridorCumulativeDistances(shape).back();
        float lastFixed = std::numeric_limits<float>::infinity();
        float lastCorner = std::numeric_limits<float>::infinity();
        bool cornerSeen = false;
        for (auto const& candidate : BuildNativeCorridorLegCandidates(shape))
        {
            assert(candidate.CorridorDistance < length);
            assert(candidate.CorridorDistance >= NativeCorridorLegMinimumYards);
            assert(candidate.CorridorDistance <= NativeCorridorLegMaximumYards);
            float& last = candidate.Corner ? lastCorner : lastFixed;
            assert(candidate.CorridorDistance < last);
            last = candidate.CorridorDistance;
            assert(!(cornerSeen && !candidate.Corner));
            cornerSeen = cornerSeen || candidate.Corner;
        }
    }
    assert(BuildNativeCorridorLegCandidates(shapes[1]).size() == 3); // 140, 100, 60
    assert(BuildNativeCorridorLegCandidates(shapes[3]).size() == 1); // corner at 45
    assert(BuildNativeCorridorLegCandidates(shapes[4]).empty());     // shorter than a leg
    assert(BuildNativeCorridorLegCandidates(shapes[5]).empty());     // 60 is the end, not inside
    assert(BuildNativeCorridorLegCandidates(std::vector<P>{}).empty());
    assert(BuildNativeCorridorLegCandidates(std::vector<P>{ { 1, 2, 3 } }).empty());

    // Selection tries candidates in order and keeps the first proved leg.
    std::vector<float> order;
    P selected{ -1, -1, -1 };
    assert(!SelectNativeCorridorLeg(corridor, corridor.front(),
        [&](NativeCorridorLegCandidate<P> const& candidate, P&)
        { order.push_back(candidate.CorridorDistance); return false; }, selected));
    assert((order == std::vector<float>{ 220, 180, 140, 100, 60, 150 }));
    assert(near(selected, P{ -1, -1, -1 }));
    assert(SelectNativeCorridorLeg(corridor, corridor.front(),
        [&](NativeCorridorLegCandidate<P> const& candidate, P&)
        { return candidate.CorridorDistance < 200; }, selected));
    assert(near(selected, P{ 150, 30, 0 }));

    // Nothing below the minimum leg: a verified endpoint closer than 40 yd
    // to the actor never counts, whatever its corridor distance.
    selected = P{ -1, -1, -1 };
    assert(!SelectNativeCorridorLeg(corridor, corridor.front(),
        [&](NativeCorridorLegCandidate<P> const&, P& endpoint)
        { endpoint = P{ 39.9f, 0, 0 }; return true; }, selected));
    assert(near(selected, P{ -1, -1, -1 }));
    // A U-turn corridor: the 220 yd point lies 14 yd from the actor and is
    // skipped; the 180 yd point (51 yd away) is the leg.
    std::vector<P> const uturn{ { 0, 0, 0 }, { 110, 0, 0 }, { 110, 10, 0 }, { 0, 10, 0 } };
    order.clear();
    assert(SelectNativeCorridorLeg(uturn, uturn.front(),
        [&](NativeCorridorLegCandidate<P> const& candidate, P&)
        { order.push_back(candidate.CorridorDistance); return true; }, selected));
    assert((order == std::vector<float>{ 220, 180 }) && near(selected, P{ 50, 10, 0 }));
    std::cout << "ok\n";
}
''')
    assert output == "ok\n"


def _planner_block() -> str:
    planner = PLANNER.read_text(encoding="utf-8")
    capacity = planner.index("path.GetEndpointResult() == PathEndpointResult::Capacity")
    start = planner.rindex("    if (", 0, capacity)
    end = planner.index("    auto selectProgressiveLocalMechanicEndpoint", capacity)
    return planner[start:end]


def test_planner_corridor_leg_source_contract():
    planner = PLANNER.read_text(encoding="utf-8")
    assert '#include "Bots/BotWorldPopulationMgrNativePathCorridorLeg.h"' in planner
    block = _planner_block()
    guard = block[: block.index("{")]
    for term in ("!segmentSelected", "progressiveStaticRoute", "!strictNativeDescent",
                 "intent.Owner == BotMovementArbitration::Owner::Route",
                 "intent.AllowCorridorLegs",
                 "path.GetEndpointResult() == PathEndpointResult::Capacity"):
        assert term in guard, term
    # Scope (round 4 review): only route moves on the active node of a
    # composition raid row (row field composition_recovery) may ask for legs.
    movement = (BOT / "BotWorldPopulationMgrMovement.cpp").read_text(encoding="utf-8")
    scope = movement[movement.index("intent.AllowCorridorLegs = "):]
    scope = scope[:scope.index(";")]
    for term in ("movementOwner == BotMovementArbitration::Owner::Route",
                 "Cohort().Config.ValidationRouteEnable", "Cohort().Raid.RaidInstance",
                 "== Cohort().Config.ValidationRouteNodeId", ".CompositionRecovery"):
        assert term in scope, term
    header = (BOT / "BotWorldPopulationMgrMovement.h").read_text(encoding="utf-8")
    assert "    bool AllowCorridorLegs = false;\n" in header
    for term in ("PathGenerator corridor(bot);", "corridor.SetUseStraightPath(true);",
                 "corridor.HasConnectedPolyCorridor()",
                 "BotWorldMovement::NativePathCanProvideProgress(\n                corridor.GetPathType())",
                 "BotWorldMovement::SelectNativeCorridorLeg(corridor.GetPath(),",
                 "bot->GetMap()->GetHeight(\n                bot->GetPhaseShift(), point.x, point.y, point.z + 2.0f, true,\n                8.0f)",
                 "completeNativePathToPoint(", 'traversalMode = "native_corridor_leg";',
                 "nativeProof = legProof;", "plannerControls = legControls;",
                 "segmentSelected = true;"):
        assert term in block, term
    # Ordinary pathing only: no forced destinations or position writes.
    assert not re.search(r"CalculatePath\([^;]*\btrue\)", block)
    for forbidden in ("Teleport", "Relocate", "UpdatePosition", "SetPosition",
                      "MovePoint", "MoveCharge", "MoveJump", "NearTeleportTo"):
        assert forbidden not in block
        assert forbidden not in planner
        assert forbidden not in HEADER.read_text(encoding="utf-8")
    # After the dynamic chase and native long-path returns and the primary
    # endpoint section; before the progressive local/walkable-step fallbacks.
    position = planner.index(block)
    assert planner.index('plan.TraversalMode = "native_target_chase";') < position
    assert planner.index('plan.TraversalMode = "native_long_path";') < position
    assert planner.index('selectProgressEndpoint(path, "native_partial_path_backoff", 3.0f);') < position
    assert position < planner.index("        selectProgressiveLocalMechanicEndpoint();")
    assert position < planner.index("std::array<float, 2> const stepDistances")
    # The final plan carries the traversal mode into planner diagnostics.
    assert "plan.TraversalMode = traversalMode;" in planner


WHOLE_PLANNER_PATH_GENERATOR = r'''
#pragma once
#include "Player.h"
#include "Movement/PathEndpoint.h"
#include <G3D/Vector3.h>
#include <cmath>
#include <vector>
namespace Movement {using PointsArray=std::vector<G3D::Vector3>;}
using PathType=unsigned;
constexpr unsigned PATHFIND_NORMAL=1,PATHFIND_INCOMPLETE=2,PATHFIND_NOPATH=4,PATHFIND_NOT_USING_PATH=8,PATHFIND_SHORTCUT=16,PATHFIND_FARFROMPOLY=32;
// Deterministic native seam: the first path is the primary request, a
// straight-path generator returns the corner corridor, and every other path
// is an independently calculated proof that fails past proofReachYards.
struct PathGenerator {
 inline static PathEndpointResult primaryEndpoint=PathEndpointResult::Capacity;
 inline static unsigned primaryType=PATHFIND_NOPATH|PATHFIND_SHORTCUT,corridorType=PATHFIND_NORMAL;
 inline static Movement::PointsArray corridorPoints;
 inline static bool connected=true;
 inline static float proofReachYards=1.0e9f;
 inline static unsigned calls=0,straightCalls=0,proofCalls=0;
 Player* actor;Movement::PointsArray points;unsigned type=PATHFIND_NORMAL;bool straight=false,corridor=false;
 PathEndpointResult endpoint=PathEndpointResult::ReachedRequested;
 explicit PathGenerator(Player* bot):actor(bot){}
 void SetUseStraightPath(bool value){straight=value;}
 bool CalculatePath(float x,float y,float z,bool){
  G3D::Vector3 const start(actor->x,actor->y,actor->z),target(x,y,z);
  if(calls++==0){points={start,target};type=primaryType;endpoint=primaryEndpoint;return true;}
  if(straight){++straightCalls;points=corridorPoints;type=corridorType;corridor=connected;return true;}
  ++proofCalls;points={start,target};corridor=true;
  float const reach=std::sqrt((x-start.x)*(x-start.x)+(y-start.y)*(y-start.y)+(z-start.z)*(z-start.z));
  if(reach>proofReachYards){type=PATHFIND_NOPATH|PATHFIND_SHORTCUT;endpoint=PathEndpointResult::Capacity;}
  return true;
 }
 PathType GetPathType()const{return type;}
 Movement::PointsArray const& GetPath()const{return points;}
 G3D::Vector3 GetActualEndPosition()const{return points.empty()?G3D::Vector3::zero():points.back();}
 PathEndpointResult GetEndpointResult()const{return endpoint;}
 bool CorridorReachedEndPoly()const{return endpoint==PathEndpointResult::ReachedRequested;}
 bool HasResolvedEndPosition()const{return true;}
 G3D::Vector3 GetResolvedEndPosition()const{return GetActualEndPosition();}
 bool HasConnectedPolyCorridor()const{return corridor;}
};
'''

WHOLE_PLANNER_HARNESS = r'''
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativePathCorridorLeg.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "PathGenerator.h"
#include <cassert>
#include <cmath>
#include <string>
namespace G3D { Vector3 const& Vector3::zero() { static Vector3 value(0,0,0); return value; } }
using namespace BotWorldMovement;
using BotMovementArbitration::Owner;
int main(){
 // Round-3 atramedes_c0: melee stuck past the elevator exit, route anchor
 // 341 yd away; the corner corridor runs via orb_regroup (419 yd).
 Player actor;actor.x=-193.138f;actor.y=-227.532f;
 float const level=actor.map.floor;
 Movement::PointsArray const corridor{{actor.x,actor.y,actor.z},{-27.84f,-224.48f,level},
  {40.0f,-330.0f,level},{146.866f,-259.776f,level}};
 float const length=NativeCorridorCumulativeDistances(corridor).back();
 assert(length>NativeCorridorSmoothCapacityYards);
 auto along=[&](float distance){G3D::Vector3 point;assert(NativeCorridorPointAtDistance(corridor,
  NativeCorridorCumulativeDistances(corridor),distance,point));return point;};
 auto reach=[&](G3D::Vector3 const& point){return std::sqrt((point.x-actor.x)*(point.x-actor.x)
  +(point.y-actor.y)*(point.y-actor.y)+(point.z-actor.z)*(point.z-actor.z));};
 BotWorldPopulationMgr manager;Intent intent;PathPlan plan;
 auto reset=[&](){intent={};intent.Owner=Owner::Route;intent.AllowProgressiveSegments=true;
  intent.AllowCorridorLegs=true;
  intent.X=146.866f;intent.Y=-259.776f;intent.Z=level;PathGenerator::corridorPoints=corridor;
  PathGenerator::primaryEndpoint=PathEndpointResult::Capacity;
  PathGenerator::primaryType=PATHFIND_NOPATH|PATHFIND_SHORTCUT;PathGenerator::corridorType=PATHFIND_NORMAL;
  PathGenerator::connected=true;PathGenerator::proofReachYards=1.0e9f;};
 auto run=[&](){MovementPlannerDiagnostics().ClearAll();PathGenerator::calls=0;
  PathGenerator::straightCalls=0;PathGenerator::proofCalls=0;plan={};
  plan.LaunchReceiptId=BeginMovementPlannerReceipt(30005,669,intent,{},0,actor.x,actor.y,actor.z);
  return manager.PlanMovementPath(&actor,intent,plan);};
 auto at=[&](G3D::Vector3 const& point){return std::fabs(plan.SegmentX-point.x)<1e-3f
  &&std::fabs(plan.SegmentY-point.y)<1e-3f&&std::fabs(plan.SegmentZ-level)<1e-3f;};

 // A capacity-refused route move walks the first 220 yd leg of its corridor.
 reset();assert(run());
 assert(plan.Selected&&plan.Execution.PlannerAccepted&&plan.TraversalMode=="native_corridor_leg");
 assert(PathGenerator::straightCalls==1&&PathGenerator::proofCalls==1&&at(along(220.0f)));
 auto observed=MovementPlannerDiagnostics().Latest(30005);
 assert(observed.FinalTraversalMode=="native_corridor_leg"&&observed.Result=="accepted");
 assert(observed.NativeProof.Complete&&observed.NativeProof.Accepted&&observed.NativeProof.EndpointMatched);
 assert(!observed.PrimaryNativeProof.Complete&&observed.PrimaryPathDisposition==PrimaryDisposition::Forbidden);
 assert(!observed.LocalFallbackAttempted);

 // A longer leg that the native proof refuses falls back to the next one.
 float const reach220=reach(along(220.0f)),reach180=reach(along(180.0f));
 assert(reach180<reach220);
 reset();PathGenerator::proofReachYards=0.5f*(reach180+reach220);assert(run());
 assert(plan.TraversalMode=="native_corridor_leg"&&PathGenerator::proofCalls==2&&at(along(180.0f)));

 // No provable leg: the existing walkable-step fallback still runs.
 reset();PathGenerator::proofReachYards=30.0f;assert(run());
 assert(plan.TraversalMode=="native_walkable_step"&&PathGenerator::straightCalls==1);

 // Corridor evidence is required.
 reset();PathGenerator::connected=false;run();
 assert(plan.TraversalMode!="native_corridor_leg"&&PathGenerator::straightCalls==1&&PathGenerator::proofCalls>0);
 reset();PathGenerator::corridorType=PATHFIND_NOPATH|PATHFIND_SHORTCUT;run();
 assert(plan.TraversalMode!="native_corridor_leg"&&PathGenerator::straightCalls==1);
 reset();PathGenerator::corridorPoints={corridor[0],{actor.x+30.0f,actor.y,level}};run();
 assert(plan.TraversalMode!="native_corridor_leg");

 // Out of scope (no composition raid row): never a corridor, exactly as before.
 reset();intent.AllowCorridorLegs=false;run();
 assert(PathGenerator::straightCalls==0&&plan.TraversalMode!="native_corridor_leg");

 // Only a capacity refusal of an ordinary route move asks for a corridor.
 for(auto result:{PathEndpointResult::Failure,PathEndpointResult::CorridorExhausted,
  PathEndpointResult::NoSteer,PathEndpointResult::Unavailable}){
  reset();PathGenerator::primaryEndpoint=result;run();
  assert(PathGenerator::straightCalls==0&&plan.TraversalMode!="native_corridor_leg");}
 for(auto owner:{Owner::Formation,Owner::CombatRange,Owner::Support,Owner::Mechanic,Owner::Hazard}){
  for(bool progressive:{false,true}){
   reset();intent.Owner=owner;intent.AllowProgressiveSegments=progressive;run();
   assert(PathGenerator::straightCalls==0&&plan.TraversalMode!="native_corridor_leg");}}
 reset();intent.AllowProgressiveSegments=false;assert(!run());
 assert(PathGenerator::straightCalls==0&&plan.RejectReason=="route_destination_unreachable");
 reset();intent.RequireCompletePath=true;assert(!run());
 assert(PathGenerator::straightCalls==0&&!plan.Selected);
 // The recovery native long-path branch is unchanged.
 reset();intent.Owner=Owner::Recovery;intent.AllowNativeLongPath=true;assert(run());
 assert(plan.TraversalMode=="native_long_path"&&PathGenerator::calls==0);
}
'''


def test_whole_planner_walks_capacity_refused_route_in_legs(tmp_path):
    from test_same_level_native_path_controls import STUBS

    stubs = dict(STUBS)
    stubs["PathGenerator.h"] = WHOLE_PLANNER_PATH_GENERATOR
    for name, content in stubs.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    harness = tmp_path / "main.cpp"
    harness.write_text(WHOLE_PLANNER_HARNESS)
    units = [PLANNER] + [BOT / name for name in (
        "BotWorldPopulationMgrMovementPlannerDiagnostics.cpp",
        "BotWorldPopulationMgrMovementReceiptRetention.cpp",
        "BotWorldPopulationMgrMovementProgressDiagnostics.cpp",
        "BotWorldPopulationMgrMovementExecution.cpp")]
    command = ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for path in (tmp_path, ROOT / "src/server/game", ROOT / "src/server/game/Entities/Object",
                 ROOT / "src/common", ROOT / "dep/g3dlite/include"):
        command += ["-I", str(path)]
    binary = tmp_path / "planner"
    result = subprocess.run(command + [str(harness), *map(str, units), "-o", str(binary)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True)


REPLAY_PATH_GENERATOR = r'''
#pragma once
// Replay seam: the members PathGeneratorSmooth.cpp uses, nothing else.
#include "DetourNavMesh.h"
#include "DetourNavMeshQuery.h"
#include "Movement/PathEndpoint.h"
#include <G3D/Vector3.h>
#include <cstdint>
using uint32 = std::uint32_t;
using int32 = std::int32_t;
@DEFINES@
struct ReplaySource { unsigned GetEntry() const { return 0; } };
class PathGenerator
{
public:
    PathEndpointResult _endpointResult = PathEndpointResult::Unavailable;
    bool _corridorReachedEndPoly = false;
    bool _resolvedEndPositionAvailable = false;
    bool _resolvedEndPositionProjected = false;
    G3D::Vector3 _resolvedEndPosition;
    ReplaySource const* _source = nullptr;
    dtNavMesh const* _navMesh = nullptr;
    dtNavMeshQuery const* _navMeshQuery = nullptr;
    dtQueryFilter _filter;
    void ResetEndpointObservation();
    void SetResolvedEndPosition(float const* point, bool projected);
    void MarkResolvedEndPositionReached();
    uint32 FixupCorridor(dtPolyRef* path, uint32 npath, uint32 maxPath, dtPolyRef const* visited, uint32 nvisited);
    bool GetSteerTarget(float const* startPos, float const* endPos, float minTargetDist, dtPolyRef const* path,
        uint32 pathSize, float* steerPos, unsigned char& steerPosFlag, dtPolyRef& steerPosRef);
    dtStatus FindSmoothPath(float const* startPos, float const* endPos, dtPolyRef const* polyPath,
        uint32 polyPathSize, float* smoothPath, int* smoothPathSize, uint32 smoothPathMaxSize);
    bool InRangeYZX(float const* v1, float const* v2, float r, float h) const;
};
'''

REPLAY_PROBE = r'''
#include "PathGenerator.h"
#include "Bots/BotWorldPopulationMgrNativePathCorridorLeg.h"
#include "DetourCommon.h"
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
namespace G3D { Vector3 const& Vector3::zero() { static Vector3 value(0, 0, 0); return value; } }
using namespace BotWorldMovement;
struct TileHeader { uint32 magic, dtVersion, mmapVersion, size; char usesLiquids; char padding[3]; };
struct Corridor
{
    std::vector<dtPolyRef> polys;
    bool complete = false;
    std::vector<G3D::Vector3> corners;
    float length = 0.0f;
};
static dtQueryFilter filter;
static float extents[3] = { 3.0f, 5.0f, 3.0f };
static void yzx(G3D::Vector3 const& p, float* out) { out[0] = p.y; out[1] = p.z; out[2] = p.x; }
static dtPolyRef nearest(dtNavMeshQuery const* query, G3D::Vector3 const& p)
{
    float pos[3]; yzx(p, pos);
    dtPolyRef ref = 0; float closest[3];
    query->findNearestPoly(pos, extents, &filter, &ref, closest);
    if (!ref)
    {
        float wide[3] = { 3.0f, 50.0f, 3.0f };
        query->findNearestPoly(pos, wide, &filter, &ref, closest);
    }
    return ref;
}
// PathGenerator::BuildPolyPath + BuildPointPath(straight), with its limits.
static Corridor corridor(dtNavMeshQuery const* query, G3D::Vector3 const& a, G3D::Vector3 const& b,
    int maxPolys, int maxCorners)
{
    Corridor result;
    dtPolyRef const startRef = nearest(query, a), endRef = nearest(query, b);
    if (!startRef || !endRef)
        return result;
    float start[3], end[3]; yzx(a, start); yzx(b, end);
    result.polys.resize(maxPolys);
    int count = 0;
    query->findPath(startRef, endRef, start, end, &filter, result.polys.data(), &count, maxPolys);
    result.polys.resize(count);
    result.complete = count > 0 && result.polys.back() == endRef;
    std::vector<float> straight(3 * maxCorners);
    std::vector<unsigned char> flags(maxCorners);
    int corners = 0;
    query->findStraightPath(start, end, result.polys.data(), count, straight.data(), flags.data(), nullptr,
        &corners, maxCorners);
    for (int i = 0; i < corners; ++i)
        result.corners.emplace_back(straight[3 * i + 2], straight[3 * i], straight[3 * i + 1]);
    result.length = corners > 1 ? NativeCorridorCumulativeDistances(result.corners).back() : 0.0f;
    return result;
}
struct Smooth { int points = 0; bool failed = true; PathEndpointResult endpoint = PathEndpointResult::Unavailable; G3D::Vector3 last; };
// PathGenerator::BuildPointPath(smooth): the production FindSmoothPath.
static Smooth smooth(dtNavMesh const* mesh, dtNavMeshQuery const* query, Corridor const& c,
    G3D::Vector3 const& a, G3D::Vector3 const& b)
{
    Smooth result;
    if (c.polys.empty())
        return result;
    PathGenerator generator;
    generator._navMesh = mesh;
    generator._navMeshQuery = query;
    generator._filter = filter;
    generator.ResetEndpointObservation();
    float start[3], end[3]; yzx(a, start); yzx(b, end);
    float points[MAX_POINT_PATH_LENGTH * VERTEX_SIZE];
    int count = 0;
    dtStatus const status = generator.FindSmoothPath(start, end, c.polys.data(), uint32(c.polys.size()), points,
        &count, MAX_POINT_PATH_LENGTH);
    result.points = count;
    result.failed = dtStatusFailed(status) || count < 2 || uint32(count) >= MAX_POINT_PATH_LENGTH;
    result.endpoint = generator._endpointResult;
    if (count)
        result.last = G3D::Vector3(points[3 * (count - 1) + 2], points[3 * (count - 1)], points[3 * (count - 1) + 1]);
    return result;
}
int main(int argc, char** argv)
{
    std::string const dir = argv[1];
    std::ifstream mapFile(dir + "/669.mmap", std::ios::binary);
    dtNavMeshParams params{};
    mapFile.read(reinterpret_cast<char*>(&params), sizeof(params));
    dtNavMesh* mesh = dtAllocNavMesh();
    mesh->init(&params);
    for (auto const& entry : std::filesystem::directory_iterator(dir))
    {
        std::string const name = entry.path().filename().string();
        if (name.size() != 14 || name.rfind("669", 0) != 0 || name.substr(name.size() - 7) != ".mmtile")
            continue;
        std::ifstream tileFile(entry.path(), std::ios::binary);
        TileHeader header{};
        tileFile.read(reinterpret_cast<char*>(&header), sizeof(header));
        unsigned char* data = static_cast<unsigned char*>(dtAlloc(header.size, DT_ALLOC_PERM));
        tileFile.read(reinterpret_cast<char*>(data), header.size);
        if (!dtStatusSucceed(mesh->addTile(data, header.size, DT_TILE_FREE_DATA, 0, nullptr)))
            dtFree(data);
    }
    // The server's query (MMapManager: 1024 nodes) and an unbounded one for the full corridor.
    dtNavMeshQuery* server = dtAllocNavMeshQuery();
    server->init(mesh, 1024);
    dtNavMeshQuery* wide = dtAllocNavMeshQuery();
    wide->init(mesh, 65535);
    filter.setIncludeFlags(0x1 | 0x4 | 0x8); // player: NAV_GROUND | NAV_WATER | NAV_MAGMA_SLIME
    filter.setExcludeFlags(0);
    struct Case { char const* label; G3D::Vector3 from, to; };
    G3D::Vector3 const anchor(146.866f, -259.776f, 74.907f);
    Case const cases[] = {
        { "melee_stuck", G3D::Vector3(-193.138f, -227.532f, 76.646f), anchor },
        { "elevator_exit", G3D::Vector3(-224.0f, -224.605f, 76.8211f), anchor },
        { "maloriak_encounter", G3D::Vector3(-105.7865f, -462.5781f, 73.53668f), anchor },
        { "chimaeron", G3D::Vector3(-104.738f, 20.592f, 72.14094f), anchor },
    };
    for (Case const& item : cases)
    {
        Corridor const full = corridor(wide, item.from, item.to, 8192, 512);
        Corridor const primary = corridor(server, item.from, item.to, MAX_PATH_LENGTH, MAX_POINT_PATH_LENGTH);
        Smooth const primarySmooth = smooth(mesh, server, primary, item.from, item.to);
        // Walk leg by leg exactly as the planner does: the first candidate
        // whose own native path (server limits) is complete and smooths
        // within capacity, at least the minimum leg from the actor.
        G3D::Vector3 actor = item.from;
        std::string legs = "[";
        bool reached = false;
        float firstCandidate = -1.0f;
        for (int leg = 0; leg < 8 && !reached; ++leg)
        {
            Corridor const remaining = corridor(server, actor, item.to, MAX_PATH_LENGTH, MAX_POINT_PATH_LENGTH);
            if (!smooth(mesh, server, remaining, actor, item.to).failed && remaining.complete)
            {
                reached = true;
                break;
            }
            G3D::Vector3 endpoint;
            Corridor proof; Smooth proofSmooth; float distance = -1.0f;
            bool const selected = SelectNativeCorridorLeg(remaining.corners, actor,
                [&](NativeCorridorLegCandidate<G3D::Vector3> const& candidate, G3D::Vector3& verified)
                {
                    proof = corridor(server, actor, candidate.Position, MAX_PATH_LENGTH, MAX_POINT_PATH_LENGTH);
                    proofSmooth = smooth(mesh, server, proof, actor, candidate.Position);
                    if (!proof.complete || proofSmooth.failed)
                        return false;
                    verified = proofSmooth.last;
                    distance = candidate.CorridorDistance;
                    return true;
                }, endpoint);
            if (!selected)
                break;
            if (firstCandidate < 0.0f)
                firstCandidate = distance;
            char row[512];
            std::snprintf(row, sizeof(row),
                "%s{\"corridor_distance\":%.1f,\"remaining_corridor_yd\":%.1f,\"remaining_complete\":%s,"
                "\"proof_polys\":%zu,\"proof_straight_yd\":%.1f,\"proof_points_4yd\":%d,\"proof_smooth_points\":%d,"
                "\"proof_endpoint\":\"%s\",\"leg_yd\":%.1f}",
                leg ? "," : "", distance, remaining.length, remaining.complete ? "true" : "false",
                proof.polys.size(), proof.length, int(proof.length / 4.0f) + 1, proofSmooth.points,
                PathEndpointResultName(proofSmooth.endpoint), NativeCorridorPointDistance(actor, endpoint));
            legs += row;
            actor = endpoint;
        }
        legs += "]";
        std::printf("{\"label\":\"%s\",\"full_polys\":%zu,\"full_complete\":%s,\"full_yd\":%.1f,"
            "\"server_polys\":%zu,\"server_complete\":%s,\"server_corners\":%zu,\"server_yd\":%.1f,"
            "\"primary_smooth_points\":%d,\"primary_smooth_failed\":%s,\"primary_endpoint\":\"%s\","
            "\"first_candidate\":%.1f,\"legs\":%s,\"reached\":%s}\n",
            item.label, full.polys.size(), full.complete ? "true" : "false", full.length,
            primary.polys.size(), primary.complete ? "true" : "false", primary.corners.size(), primary.length,
            primarySmooth.points, primarySmooth.failed ? "true" : "false",
            PathEndpointResultName(primarySmooth.endpoint), firstCandidate, legs.c_str(),
            reached ? "true" : "false");
    }
}
'''


def test_bwd_navmesh_replay_walks_atramedes_runback_in_legs(tmp_path):
    detour_sources = [DETOUR / "Source" / name for name in (
        "DetourAlloc.cpp", "DetourAssert.cpp", "DetourCommon.cpp", "DetourNavMesh.cpp",
        "DetourNavMeshQuery.cpp", "DetourNode.cpp")]
    if not (MMAPS / "669.mmap").exists():
        pytest.skip("data/mmaps/669.mmap is not checked out (DVC)")
    if not all(path.exists() for path in detour_sources):
        pytest.skip("dep/recastnavigation Detour sources are missing")
    defines = "\n".join(f"#define {name} {_path_generator_define(name)}" for name in (
        "MAX_PATH_LENGTH", "MAX_POINT_PATH_LENGTH", "SMOOTH_PATH_STEP_SIZE", "SMOOTH_PATH_SLOP",
        "VERTEX_SIZE", "INVALID_POLYREF"))
    (tmp_path / "PathGenerator.h").write_text(REPLAY_PATH_GENERATOR.replace("@DEFINES@", defines))
    (tmp_path / "Creature.h").write_text("#pragma once\n")
    (tmp_path / "Log.h").write_text("#pragma once\n#define TC_LOG_DEBUG(...) ((void)0)\n")
    # The production smoothing unit, compiled against the replay seam.
    (tmp_path / "PathGeneratorSmooth.cpp").write_text(SMOOTH.read_text(encoding="utf-8"))
    (tmp_path / "probe.cpp").write_text(REPLAY_PROBE)
    binary = tmp_path / "probe"
    command = ["nice", "-n", "10", "g++", "-std=c++17", "-O1", "-w"]
    for path in (tmp_path, ROOT / "src/server/game", ROOT / "src/common", DETOUR / "Include",
                 ROOT / "dep/g3dlite/include"):
        command += ["-I", str(path)]
    subprocess.run(command + [str(tmp_path / "probe.cpp"), str(tmp_path / "PathGeneratorSmooth.cpp"),
                              *map(str, detour_sources), "-o", str(binary)], check=True)
    output = subprocess.run(["nice", "-n", "10", str(binary), str(MMAPS)], check=True,
                            capture_output=True, text=True).stdout
    rows = {row["label"]: row for row in map(json.loads, output.splitlines())}
    print(json.dumps(rows, indent=1))

    stuck = rows["melee_stuck"]
    # The round-3 refusal: a connected corridor longer than the smoothed cap.
    assert stuck["full_complete"] and stuck["full_yd"] > 74 * 4.0
    assert stuck["primary_smooth_failed"] and stuck["primary_endpoint"] == "capacity"
    # The first candidate lies at most 220 yd along the corridor, and the
    # leg to it is an ordinary native path inside both caps.
    first = stuck["legs"][0]
    assert stuck["first_candidate"] == first["corridor_distance"] <= 220.0
    assert first["proof_polys"] <= 74 and first["proof_points_4yd"] < 74
    assert first["proof_smooth_points"] < 74
    assert first["proof_endpoint"] in ("reached_requested", "reached_projected_end_poly")
    assert first["leg_yd"] >= 40.0
    # Leg by leg, the member reaches a position whose whole walk fits.
    for row in rows.values():
        assert row["reached"], row
        assert len(row["legs"]) <= 3, row
        for leg in row["legs"]:
            assert leg["proof_polys"] <= 74 and leg["proof_smooth_points"] < 74, row
        distances = [leg["remaining_corridor_yd"] for leg in row["legs"]]
        assert distances == sorted(distances, reverse=True), row


def test_corridor_leg_line_budgets():
    for name in ("BotWorldPopulationMgrMovementPlanner.cpp", "BotWorldPopulationMgrMovement.cpp",
                 "BotWorldPopulationMgrMovement.h", "BotWorldPopulationMgrNativePathCorridorLeg.h"):
        assert len((BOT / name).read_text(encoding="utf-8").splitlines()) < 1000, name
