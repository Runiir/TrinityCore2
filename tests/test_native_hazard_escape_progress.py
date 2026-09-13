import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_native_hazard_escape_progress_predicate_counterexamples(tmp_path):
    source = tmp_path / "native_hazard_escape_progress.cpp"
    binary = tmp_path / "native_hazard_escape_progress"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativePathAdmission.h"

#include <cassert>

using namespace BotWorldMovement;
using BotMovementArbitration::Owner;

static NativePathProofObservation CompleteProjectedEndpoint()
{
    NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.PathType = 1; // PATHFIND_NORMAL.
    proof.Complete = true;
    proof.EndpointResult = PathEndpointResult::ReachedProjectedEndPoly;
    proof.CorridorReachedEndPoly = true;
    proof.ResolvedEndpointAvailable = true;
    proof.ActualEndpointMatchedResolved = true;
    proof.EndpointMatched = false;
    proof.EndpointFloorValid = true;
    proof.FloorObservation = {};
    return proof;
}

int main()
{
    NativePathProofObservation const complete = CompleteProjectedEndpoint();
    HazardEscapeBasis const behind{ 9001, -5.0f, 0.0f, 210.0f };

    // A complete native projection on the same surface is useful when its
    // actual endpoint increases clearance from the exact bound hazard.
    HazardEscapeProgressObservation away = ObserveHazardEscapeProgress(
        behind, 0.0f, 0.0f, 210.0f, 8.0f, 0.0f, 210.4f);
    assert(away.Available);
    assert(away.HazardGuid == 9001);
    assert(away.ClearanceProgress == 8.0f);
    assert(NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, behind, away));

    // Goal-directed progress is not hazard progress. This endpoint could be
    // closer to an arbitrary request while moving directly toward the source.
    HazardEscapeBasis const ahead{ 9001, 10.0f, 0.0f, 210.0f };
    HazardEscapeProgressObservation closer = ObserveHazardEscapeProgress(
        ahead, 0.0f, 0.0f, 210.0f, 7.5f, 0.0f, 210.4f);
    assert(closer.ClearanceProgress < 0.0f);
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, ahead, closer));

    HazardEscapeProgressObservation tooSmall = ObserveHazardEscapeProgress(
        behind, 0.0f, 0.0f, 210.0f, 0.5f, 0.0f, 210.0f);
    assert(tooSmall.ClearanceProgress > 0.0f);
    assert(tooSmall.ClearanceProgress
        < NativeHazardEscapeMinimumClearanceProgress);
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, behind, tooSmall));

    NativePathProofObservation wrongFloor = complete;
    wrongFloor.EndpointFloorValid = false;
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, wrongFloor, behind, away));
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, false, true, false, complete, behind, away));

    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, true, complete, behind, away));

    NativePathProofObservation noPath = complete;
    noPath.Calculated = false;
    noPath.Complete = false;
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, false, false, noPath, behind, away));

    HazardEscapeBasis const missing{};
    HazardEscapeProgressObservation unavailable = ObserveHazardEscapeProgress(
        missing, 0.0f, 0.0f, 210.0f, 8.0f, 0.0f, 210.0f);
    assert(!unavailable.Available);
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, missing, unavailable));

    HazardEscapeBasis const otherHazard{ 9002, -5.0f, 0.0f, 210.0f };
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, otherHazard, away));

    HazardEscapeProgressObservation wrongLevel = ObserveHazardEscapeProgress(
        HazardEscapeBasis{ 9001, -5.0f, 0.0f, 180.0f },
        0.0f, 0.0f, 210.0f, 8.0f, 0.0f, 210.0f);
    assert(!wrongLevel.ActorHazardSameLevel);
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete,
        HazardEscapeBasis{ 9001, -5.0f, 0.0f, 180.0f }, wrongLevel));

    HazardEscapeProgressObservation tampered = away;
    tampered.RequiredProgress = 0.0f;
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, behind, tampered));

    // The semantic proof cannot widen ordinary movement admission.
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Formation, true, true, false, complete, behind, away));
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/common"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_hazard_basis_reaches_native_planner_admission():
    native_action = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrNativeAction.cpp").read_text(encoding="utf-8")
    movement = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrMovement.cpp").read_text(encoding="utf-8")
    planner = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrMovementPlanner.cpp").read_text(encoding="utf-8")
    diagnostics = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrMovementPlannerDiagnosticsJson.cpp").read_text(
            encoding="utf-8")
    parasite = (ROOT / "src/server/game/Bots/Content/Raids/"
        "BlackwingDescent/Encounters/Magmaw/"
        "BotAdaptiveMagmawParasitePolicy.h").read_text(encoding="utf-8")

    assert "action.HazardEscape" in native_action
    assert "intent.HazardEscape = hazardEscape;" in movement
    assert "ObserveHazardEscapeProgress(" in planner
    assert "NativePathProvesSameSurfaceHazardEscape(" in planner
    assert '\\"hazard_escape_progress\\"' in diagnostics
    assert '\\"primary_resolved_endpoint\\"' in diagnostics
    assert "hazardState->Begin(danger.Guid, danger.Position" in parasite
    assert "move->HazardEscape = BotWorldMovement::HazardEscapeBasis" in parasite

    assert "plan.HazardEscapeProgress.ProofQualified);" in planner
    assert 'traversalMode = "native_same_surface_hazard_escape";' in planner


def test_touched_native_headers_remain_below_repository_limit():
    for relative in (
        "src/server/game/Bots/BotHazardEscapeEvidence.h",
        "src/server/game/Bots/BotWorldPopulationMgrMovement.h",
        "src/server/game/Bots/BotWorldPopulationMgrNativePathAdmission.h",
        "src/server/game/Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h",
        "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
        "Magmaw/BotMagmawLaneTransition.h",
        "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
        "Magmaw/BotAdaptiveMagmawParasitePolicy.h",
    ):
        assert len((ROOT / relative).read_text(encoding="utf-8").splitlines()) < 1000


def test_recorded_receipts_through_whole_planner_and_executor_submission(tmp_path, historical=False):
    """Compile full planner and actual executor post-lease admission/submission.

    Native path/map results and MotionMaster launch are controlled boundaries;
    this proves submitted destination, not native spline traversal or arrival.
    """
    from test_same_level_native_path_controls import STUBS, BOT, PLANNER
    fixture = json.loads((ROOT / "tests/fixtures/native_hazard_escape_db67.json").read_text())
    stubs = dict(STUBS)
    stubs["PathGenerator.h"] = stubs["PathGenerator.h"].replace(
        "inline static bool connected=true,unsafeSecondary=false;",
        "inline static bool connected=true,unsafeSecondary=false; inline static PathEndpointResult terminal=PathEndpointResult::ReachedProjectedEndPoly; inline static G3D::Vector3 resolved; inline static bool corridor=true;")
    stubs["PathGenerator.h"] = stubs["PathGenerator.h"].replace(
        "return PathEndpointResult::ReachedRequested;", "return terminal;").replace(
        "bool CorridorReachedEndPoly()const{return true;}", "bool CorridorReachedEndPoly()const{return corridor;}").replace(
        "G3D::Vector3 GetResolvedEndPosition()const{return GetActualEndPosition();}",
        "G3D::Vector3 GetResolvedEndPosition()const{return resolved;}")
    stubs["Unit.h"] = stubs["Unit.h"].replace("return 30005;", "return 30010;")
    stubs["Player.h"] = r'''
#pragma once
#include "Unit.h"
#include "Movement/NativePathLaunchObserver.h"
#include <G3D/Vector3.h>
struct Spline {bool Initialized()const{return false;}bool Finalized()const{return false;}unsigned GetId()const{return 0;}G3D::Vector3 FinalDestination()const{return {};}};
constexpr int MOTION_SLOT_ACTIVE=0,POINT_MOTION_TYPE=1;
struct Motion {unsigned calls=0;float x=0,y=0,z=0;bool path=false;
 void Clear(int){}int GetMotionSlotType(int)const{return POINT_MOTION_TYPE;}
 void MoveChase(Unit*,float=0){}
 void MovePoint(int,float a,float b,float c,bool generate,float,Movement::NativePathLaunchContext const&){++calls;x=a;y=b;z=c;path=generate;}
};
struct Player:Unit {Motion motion;Spline spline;Spline* movespline=&spline;
 Motion* GetMotionMaster(){return &motion;}
 bool CanFly()const{return false;}void SetCanFly(bool){}bool IsGravityDisabled()const{return false;}void SetDisableGravity(bool){}
 unsigned GetInstanceId()const{return 2;}
};
'''
    stubs["Bots/BotWorldPopulationMgr.h"] = r'''
#pragma once
#include "Define.h"
#include "Player.h"
#include "Bots/BotWorldPopulationMgrMovement.h"
#include "Bots/BotExperienceLearningPolicy.h"
struct WorldBotState {
 BotWorldMovement::ExecutionObservation LastMovementExecution;
 bool IsMoving=false,NativeRecoveryGhostFlightEnabled=false,NativeRecoveryGhostGravityDisabled=false,ServerProvisioned=false,ActivePathPurposeValid=false;
 std::string ActivePathPurpose;int ServerVehicleExitLanding=0;
};
struct BotWorldPopulationMgr {
 struct State {LearningSettings LearningConfig;struct Configuration{bool ValidationRouteEnable=false;}Config;}state;
 State const& Cohort()const{return state;}
 template<class... T>bool IsFailedPathRecently(T...)const{return false;}
 bool PlanMovementPath(Player*,BotWorldMovement::Intent const&,BotWorldMovement::PathPlan&)const;
 bool ExecuteSelected(WorldBotState&,Player*,BotWorldMovement::Intent const&);
 template<class... T>bool RejectMovementPath(T...){return false;}
 template<class... T>void CommitMovementEvidence(T...){}
};
'''
    for name, content in stubs.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    executor=(BOT/"BotWorldPopulationMgrMovementExecutor.cpp").read_text()
    # Actual caller from planning through rejection, evidence commit and MovePoint.
    executor=executor[executor.index("    BotWorldMovement::PathPlan plan;"):]
    prefix=r'''
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
#include "PathGenerator.h"
#include <cassert>
#include <cmath>
namespace G3D {Vector3 const& Vector3::zero(){static Vector3 value(0,0,0);return value;}}
uint64 MovementExecutorBotGuid(Player* actor){return actor->GetGUID().GetCounter();}
uint32 MovementExecutorMapId(Player* actor){return actor->GetMapId();}
namespace BotServerVehicleExitLanding {template<class... T>void RememberGroundPointSubmission(T...){}}
template<class... T>void BindVehicleExitGroundReceipt(T...){}
bool BotWorldPopulationMgr::ExecuteSelected(WorldBotState& state,Player* bot,BotWorldMovement::Intent const& intent){
 uint64 nowMs=1789312915493ULL;BotMovementArbitration::Request request;
'''
    cases=[]
    for row in fixture["receipts"]:
        def xyz(value):
            return ",".join(f"{value[k]}f" for k in ("x","y","z"))
        basis=row["hazard_escape_progress"]
        controls=",".join("{"+xyz(v)+"}" for v in row["controls"]["ordered_controls"])
        cases.append("{\n" + f"actor.x={row['actor']['x']}f;actor.y={row['actor']['y']}f;actor.z={row['actor']['z']}f;actor.map.floor={row['target_floor']['z']}f;\n"
            +f"intent.X={row['request']['x']}f;intent.Y={row['request']['y']}f;intent.Z={row['request']['z']}f;\n"
            +f"intent.HazardEscape=HazardEscapeBasis{{{basis['hazard_guid']}ULL,{xyz(basis['hazard'])}}};\n"
            +f"PathGenerator::primary={{{controls}}};PathGenerator::resolved={{{xyz(row['native_proof']['endpoint_resolution']['resolved'])}}};\n"
            +r'''
 auto run=[&](){PathGenerator::calls=0;actor.motion.calls=0;state={};return manager.ExecuteSelected(state,&actor,intent);};
#ifdef HISTORICAL_UNUSED_PROOF
 assert(!run());assert(actor.motion.calls==0&&!state.LastMovementExecution.NativeSubmitted);
 auto old=MovementPlannerDiagnostics().Latest(30010);
 assert(old.HazardEscapeProgress.ProofQualified);
 assert(old.Reason=="route_destination_endpoint_mismatch");
#else
 assert(run());assert(actor.motion.calls==1&&actor.motion.path);
 assert(state.LastMovementExecution.NativeSubmitted&&state.LastMovementExecution.PlannerAccepted);
 assert(!state.LastMovementExecution.RequestedEndpointMatched);
 assert(state.LastMovementExecution.ActualEndpointMatchedResolved);
 auto observed=MovementPlannerDiagnostics().Latest(30010);
 assert(observed.HazardEscapeProgress.ProofQualified);
 assert(observed.FinalTraversalMode=="native_same_surface_hazard_escape");
 assert(!observed.NativeProof.EndpointMatched); // never forge logical arrival
 assert(actor.motion.x==PathGenerator::primary.back().x&&actor.motion.y==PathGenerator::primary.back().y&&actor.motion.z==PathGenerator::primary.back().z);
 assert(std::fabs(actor.motion.z-intent.Z)>1.5f); // actual native height, no bot-Z steering
 assert(PathGenerator::calls==1); // no fallback/recalculation in planner
 auto hazard=intent.HazardEscape;
 intent.HazardEscape.reset();assert(!run()&&actor.motion.calls==0);intent.HazardEscape=hazard;
 intent.Owner=Owner::Formation;assert(!run()&&actor.motion.calls==0);intent.Owner=Owner::Hazard;
 for(unsigned type:{PATHFIND_INCOMPLETE,PATHFIND_SHORTCUT,PATHFIND_FARFROMPOLY,PATHFIND_NOT_USING_PATH,PATHFIND_NOPATH}){
  PathGenerator::primaryType=type;assert(!run()&&actor.motion.calls==0);
 }PathGenerator::primaryType=PATHFIND_NORMAL;
 auto endpoint=PathGenerator::primary.back();PathGenerator::primary.back().z=-105.0f;
 assert(!run()&&actor.motion.calls==0);PathGenerator::primary.back()=endpoint;
 auto floor=actor.map.floor;actor.map.floor=INVALID_HEIGHT;assert(!run()&&actor.motion.calls==0);actor.map.floor=floor;
 PathGenerator::corridor=false;assert(!run()&&actor.motion.calls==0);PathGenerator::corridor=true;
 PathGenerator::terminal=PathEndpointResult::ReachedRequested;assert(!run()&&actor.motion.calls==0);PathGenerator::terminal=PathEndpointResult::ReachedProjectedEndPoly;
 auto resolved=PathGenerator::resolved;PathGenerator::resolved.z+=10;assert(!run()&&actor.motion.calls==0);PathGenerator::resolved=resolved;
 intent.HazardEscape->HazardX=endpoint.x;intent.HazardEscape->HazardY=endpoint.y;
 assert(!run()&&actor.motion.calls==0);intent.HazardEscape=hazard;
 intent.HazardEscape->HazardGuid=0;assert(!run()&&actor.motion.calls==0);intent.HazardEscape=hazard;
 // Ordinary exact endpoint remains on its preexisting native admission.
 auto saved=intent;intent.Owner=Owner::Formation;intent.HazardEscape.reset();
 intent.X=endpoint.x;intent.Y=endpoint.y;intent.Z=endpoint.z;
 PathGenerator::terminal=PathEndpointResult::ReachedRequested;PathGenerator::resolved=endpoint;
 assert(run()&&actor.motion.calls==1);assert(state.LastMovementExecution.RequestedEndpointMatched);
 intent=saved;PathGenerator::terminal=PathEndpointResult::ReachedProjectedEndPoly;

#endif
}
''')
    harness=tmp_path/"caller.cpp"
    harness.write_text(prefix+executor+"\nusing namespace BotWorldMovement;using BotMovementArbitration::Owner;\nint main(){Player actor;BotWorldPopulationMgr manager;WorldBotState state;Intent intent;intent.Owner=Owner::Hazard;\n"+"".join(cases)+"}\n")
    source=PLANNER
    if historical:
        source=tmp_path/"old_planner.cpp"
        source.write_text(PLANNER.read_text().replace("plan.HazardEscapeProgress.ProofQualified);", "false);"))
    units=[source]+[BOT/name for name in (
        "BotWorldPopulationMgrMovementPlannerDiagnostics.cpp", "BotWorldPopulationMgrMovementReceiptRetention.cpp",
        "BotWorldPopulationMgrMovementProgressDiagnostics.cpp", "BotWorldPopulationMgrMovementExecution.cpp")]
    command=["c++","-std=c++17","-Wall","-Wextra","-Werror"]
    if historical:command+=["-DHISTORICAL_UNUSED_PROOF"]
    for path in (tmp_path,ROOT/"src/server/game",ROOT/"src/server/game/Entities/Object",ROOT/"src/common",ROOT/"dep/g3dlite/include"):
        command += ["-I",str(path)]
    binary=tmp_path/"caller"
    result=subprocess.run(command+[str(harness),*[str(p) for p in units],"-o",str(binary)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    subprocess.run([str(binary)],check=True)
