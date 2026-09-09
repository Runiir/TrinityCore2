"""Whole production planner with deterministic native path/map dependencies.

No MMAP producer or executor is simulated. The unchanged executor rejection
fence is checked separately; this proves planner admission containment only.
"""
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / 'src/server/game/Bots'
PLANNER = BOT / 'BotWorldPopulationMgrMovementPlanner.cpp'

STUBS = {
'Map.h': r'''
#pragma once
constexpr float INVALID_HEIGHT=-100000;
struct Map {float floor=211.580536f;float GetHeight(int,float,float,float,bool,float)const{return floor;}};
''',
'Unit.h': r'''
#pragma once
#include "Map.h"
#include <cmath>
#include <cstdint>
struct Guid {std::uint64_t GetCounter()const{return 30005;}};
struct Unit {float x=-311.962738f,y=-32.2660828f,z=211.064941f;Map map;
 bool IsAlive()const{return true;}bool IsInWorld()const{return true;}
 Map* GetMap(){return &map;}Map const* GetMap()const{return &map;}
 float GetPositionX()const{return x;}float GetPositionY()const{return y;}float GetPositionZ()const{return z;}
 float GetExactDist(float a,float b,float c)const{return std::sqrt((x-a)*(x-a)+(y-b)*(y-b)+(z-c)*(z-c));}
 float GetAngle(float a,float b)const{return std::atan2(b-y,a-x);}
 int GetPhaseShift()const{return 0;}Guid GetGUID()const{return {};}
 std::uint32_t GetMapId()const{return 669;}bool IsInCombat()const{return true;}
};
''',
'Player.h': '#pragma once\n#include "Unit.h"\nstruct Player:Unit {};\n',
'PathGenerator.h': r'''
#pragma once
#include "Player.h"
#include "Movement/PathEndpoint.h"
#include <G3D/Vector3.h>
#include <vector>
namespace Movement {using PointsArray=std::vector<G3D::Vector3>;}
using PathType=unsigned;
constexpr unsigned PATHFIND_NORMAL=1,PATHFIND_INCOMPLETE=2,PATHFIND_NOPATH=4,PATHFIND_NOT_USING_PATH=8,PATHFIND_SHORTCUT=16,PATHFIND_FARFROMPOLY=32;
struct PathGenerator {
 inline static Movement::PointsArray primary;
 inline static unsigned calls=0,primaryType=PATHFIND_NORMAL;
 inline static bool connected=true,unsafeSecondary=false;
 Player* actor;Movement::PointsArray points;unsigned type=PATHFIND_NORMAL;
 explicit PathGenerator(Player* bot):actor(bot){}
 bool CalculatePath(float x,float y,float z,bool){
  if(calls++==0){points=primary;type=primaryType;}
  else {points={{actor->x,actor->y,actor->z},{x,y,z}};
   if(unsafeSecondary)points.insert(points.begin()+1,G3D::Vector3(x,y,-105.142822f));}
  return !points.empty();
 }
 PathType GetPathType()const{return type;}
 Movement::PointsArray const& GetPath()const{return points;}
 G3D::Vector3 GetActualEndPosition()const{return points.empty()?G3D::Vector3::zero():points.back();}
 PathEndpointResult GetEndpointResult()const{return PathEndpointResult::ReachedRequested;}
 bool CorridorReachedEndPoly()const{return true;}bool HasResolvedEndPosition()const{return true;}
 G3D::Vector3 GetResolvedEndPosition()const{return GetActualEndPosition();}
 bool HasConnectedPolyCorridor()const{return connected;}
};
''',
'Bots/BotExperienceLearningPolicy.h': r'''
#pragma once
struct LearningSettings {float RecentFailurePenaltyWeight=10;};
struct BotLearnedScore {float Penalty=0;};
struct BotExperienceLearningPolicy {template<class... T>static BotLearnedScore ScorePath(T...){return {};}};
''',
'Bots/BotWorldPopulationMgr.h': r'''
#pragma once
#include "Define.h"
#include "Player.h"
#include "Bots/BotWorldPopulationMgrMovement.h"
#include "Bots/BotExperienceLearningPolicy.h"
struct BotWorldPopulationMgr {
 struct State {LearningSettings LearningConfig;} state;
 State const& Cohort()const{return state;}
 template<class... T>bool IsFailedPathRecently(T...)const{return false;}
 bool PlanMovementPath(Player*,BotWorldMovement::Intent const&,BotWorldMovement::PathPlan&)const;
};
''',
'Util.h': '#pragma once\n',
}

HARNESS = r'''
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativePathValidation.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include <cassert>
#include <limits>
#include <string>
namespace G3D { Vector3 const& Vector3::zero() { static Vector3 value(0,0,0); return value; } }
using namespace BotWorldMovement;
using BotMovementArbitration::Owner;
int main(){
 // Frozen9423 receipt453: native control itself is on the lower floor.
 Movement::PointsArray unsafe{{-311.962738f,-32.2660828f,211.389923f},
 {-309.765839f,-35.6087761f,-105.142822f},{-307.568909f,-38.9514618f,211.694321f},
 {-308.909851f,-36.4524231f,211.580536f}};
 Movement::PointsArray safe{{-300.069733f,-52.1566391f,212.297195f},
 {-302.031860f,-48.6709518f,212.137726f},{-303.994019f,-45.1852684f,211.978928f},
 {-305.956146f,-41.6995811f,211.819595f},{-307.918304f,-38.2138977f,211.660751f},
 {-308.909851f,-36.4524231f,211.580536f}};
 Player actor;BotWorldPopulationMgr manager;Intent intent;intent.Owner=Owner::Hazard;
 intent.X=-308.909851f;intent.Y=-36.4524231f;intent.Z=211.815002f;
 HazardEscapeBasis hazard;hazard.HazardGuid=42;hazard.HazardX=actor.x;hazard.HazardY=actor.y;hazard.HazardZ=actor.z;
 intent.HazardEscape=hazard;
 PathPlan plan;
 auto run=[&](Movement::PointsArray const& points,unsigned type=PATHFIND_NORMAL){
  MovementPlannerDiagnostics().ClearAll();PathGenerator::primary=points;PathGenerator::primaryType=type;PathGenerator::calls=0;
  plan={};plan.LaunchReceiptId=BeginMovementPlannerReceipt(30005,669,intent,{},0,actor.x,actor.y,actor.z);
  return manager.PlanMovementPath(&actor,intent,plan);
 };
#ifdef HISTORICAL_ENDPOINT_ONLY
 // Explicit historical adapter: the full planner below has only the new
 // primary-control terminal return disabled. This reproduces endpoint-only
 // admission, not a missing-symbol/marker failure in the baseline test.
 assert(run(unsafe));assert(plan.Selected);assert(PathGenerator::calls==1);
 return 0;
#endif
 assert(!run(unsafe));assert(plan.RejectReason=="route_destination_path_control_level_gap");
 assert(!plan.Selected && !plan.Execution.PlannerAccepted && !plan.HazardEscapeProgress.ProofQualified);
 assert(PathGenerator::calls==1); // no recalculated path or progressive fallback
 auto observed=MovementPlannerDiagnostics().Latest(30005);
 assert(observed.Gate=="path_controls" && observed.NativeProof.Complete);
 assert(observed.PrimaryPathDisposition==PrimaryDisposition::Forbidden && !observed.LocalFallbackAttempted);
 assert(observed.LaunchReceipt.PlannerControls.ControlCount==4);
 assert(observed.LaunchReceipt.PlannerControls.OrderedControls[1].z==-105.142822f);
 // Safe376 preserves full production normal admission.
 actor.x=safe.front().x;actor.y=safe.front().y;actor.z=safe.front().z;intent.HazardEscape.reset();
 assert(run(safe));assert(plan.Selected && plan.Execution.PlannerAccepted);
 // Full primary connected-surface exception still accepts safe376 for a
 // cross-level request with the unrelated lower-floor height sample.
 actor.z=193;actor.map.floor=-105.142822f;
 assert(run(safe));assert(plan.TraversalMode=="native_connected_surface_path");
 // Same-level declared-floor fallback + small endpoint mismatch uses the
 // actual bounded primary admission, retaining all six safe controls.
 actor.z=safe.front().z;intent.X+=0.8f;
 assert(run(safe));assert(plan.TraversalMode=="native_bounded_same_level_mechanic_endpoint");
 intent.X-=0.8f;actor.map.floor=211.580536f;
 // Primary incomplete -> independently recalculated safe prefix.
 intent.AllowProgressiveSegments=true;
 assert(run(safe,PATHFIND_INCOMPLETE));assert(plan.Selected && PathGenerator::calls>1);
 // Missing primary points bypass prefix selection; the whole planner then
 // independently calculates and admits a bounded local mechanic candidate.
 actor.map.floor=-105.142822f;
 assert(run({},PATHFIND_INCOMPLETE));assert(plan.Selected && PathGenerator::calls>1);
 assert(plan.TraversalMode=="native_bounded_same_level_local_step");
 // Without the declared-floor fallback, the same absent primary reaches
 // the complete walkable-step family and independently verifies its endpoint.
 actor.map.floor=211.580536f;
 assert(run({},PATHFIND_INCOMPLETE));assert(plan.Selected && PathGenerator::calls>1);
 assert(plan.TraversalMode=="native_walkable_step");
 // Unsafe recalculated prefixes/local/step paths cannot salvage an
 // incomplete primary: all actual candidate families reject their controls.
 PathGenerator::unsafeSecondary=true;
 assert(!run(safe,PATHFIND_INCOMPLETE));assert(!plan.Selected);
 actor.map.floor=-105.142822f;
 assert(!run({},PATHFIND_INCOMPLETE));assert(!plan.Selected);
 PathGenerator::unsafeSecondary=false;
 // Scope exceptions use the same production adapter, not a parallel predicate.
 for(auto owner:{Owner::Route,Owner::Recovery})assert(AdmitNativePathControls(unsafe,owner,211,211,false,false,true).Accepted);
 assert(AdmitNativePathControls(unsafe,Owner::Hazard,193,211,false,false,true).Accepted);
 assert(AdmitNativePathControls(unsafe,Owner::Hazard,211,211,true,false,true).Accepted);
 assert(AdmitNativePathControls(unsafe,Owner::Recovery,211,211,false,true,true).Accepted);
 for(auto owner:{Owner::Mechanic,Owner::Hazard}){
  assert(!AdmitNativePathControls(unsafe,owner,211,211,false,false).Accepted);
  assert(AdmitNativePathControls(unsafe,owner,211,211,false,false,true).Terminal);
  assert(!AdmitNativePathControls(unsafe,owner,211,211,false,false).Terminal);
  assert(AdmitNativePathControls(safe,owner,211,211,false,false).Accepted);
 }
 assert(!NativePathControlsMatchReferenceLevel({},211));
 Movement::PointsArray bounds{{0,0,207},{0,0,215}};assert(NativePathControlsMatchReferenceLevel(bounds,211));
 bounds[1].z=std::nextafter(215.f,216.f);assert(!NativePathControlsMatchReferenceLevel(bounds,211));
 for(int axis=0;axis<3;++axis)for(float bad:{std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}){
  Movement::PointsArray points{{0,0,211}};if(axis==0)points[0].x=bad;else if(axis==1)points[0].y=bad;else points[0].z=bad;
  assert(!NativePathControlsMatchReferenceLevel(points,211));}
 assert(!NativePathControlsMatchReferenceLevel(safe,std::numeric_limits<float>::quiet_NaN()));
 assert(!NativePathFloorObservationBlocksCompleteProof(MakeNativePathFloorObservation(NativePathFloorFailure::SampleFloorGap,1,2,0,0,211,-105,211)));
}
'''

@pytest.mark.parametrize('historical', [False, True])
def test_whole_production_planner_and_historical_endpoint_only_admission(tmp_path, historical):
    for name, content in STUBS.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    source=PLANNER
    if historical:
        # A documented historical adapter retains the entire production caller,
        # native dependency seam, proof and endpoint classifiers. Disable only
        # this new terminal guard to expose the prior endpoint-only decision.
        source=tmp_path/'historical_planner.cpp'
        source.write_text(PLANNER.read_text().replace('if (primaryControls.Terminal)', 'if (false && primaryControls.Terminal)'))
    harness=tmp_path/'main.cpp';harness.write_text(HARNESS);binary=tmp_path/'planner'
    units=[source]+[BOT/name for name in (
        'BotWorldPopulationMgrMovementPlannerDiagnostics.cpp','BotWorldPopulationMgrMovementReceiptRetention.cpp',
        'BotWorldPopulationMgrMovementProgressDiagnostics.cpp','BotWorldPopulationMgrMovementExecution.cpp')]
    command=['c++','-std=c++17','-Wall','-Wextra','-Werror']
    if historical:command+=['-DHISTORICAL_ENDPOINT_ONLY']
    for path in (tmp_path,ROOT/'src/server/game',ROOT/'src/server/game/Entities/Object',ROOT/'src/common',ROOT/'dep/g3dlite/include'):
        command+=['-I',str(path)]
    result=subprocess.run(command+[str(harness),*[str(p) for p in units],'-o',str(binary)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    subprocess.run([str(binary)],check=True)


def test_early_guard_and_existing_executor_rejection_fence():
    source=PLANNER.read_text()
    guard=source.index('if (primaryControls.Terminal)')
    assert source.index('primaryNativeProof = nativeProof;') < guard
    for marker in ('if (intent.HazardEscape)', 'path.HasConnectedPolyCorridor()',
                   'ClassifyPrimaryDisposition(', 'ClassifyNativePrimaryEndpointAdmission('):
        assert guard < source.index(marker)
    # Wiring only: the executor is deliberately not replaced with a fake
    # MovePoint implementation. Its existing early return precedes submission.
    executor=(BOT/'BotWorldPopulationMgrMovementExecutor.cpp').read_text()
    assert executor.index('bool const planned = PlanMovementPath(') < executor.index('if (!planned)')
    assert executor.index('if (!planned)') < executor.index('return RejectMovementPath(state, bot, intent,',executor.index('if (!planned)')) < executor.index('CommitMovementEvidence(') < executor.index('->MovePoint(')
