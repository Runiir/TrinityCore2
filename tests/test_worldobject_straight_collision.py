"""Actual collision helper with deterministic native collision/path dependencies."""
from pathlib import Path
import subprocess
from test_mage_flame_orb_scripted_motion import function

ROOT = Path(__file__).resolve().parents[1]


def test_actual_first_collision_default_and_straight_modes(tmp_path):
    source = (ROOT/'src/server/game/Entities/Object/WorldObjectMovement.cpp').read_text()
    body = function(source, 'void WorldObjectMovement::MovePositionToFirstCollision(') + '\n' + function(source, 'void WorldObject::MovePositionToFirstCollision(')
    header = (ROOT/'src/server/game/Entities/Object/Object.h').read_text()
    declaration = next(line.strip() for line in header.splitlines() if 'void MovePositionToFirstCollision(' in line)
    cpp = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>
using uint32=uint32_t;
#define TC_LOG_FATAL(...) do {} while(false)
constexpr float CONTACT_DISTANCE=0.5f,VMAP_INVALID_HEIGHT_VALUE=-100000,INVALID_HEIGHT=-100000;
constexpr unsigned PATHFIND_NORMAL=1,PATHFIND_SHORTCUT=2,PATHFIND_INCOMPLETE=4,PATHFIND_FARFROMPOLY_END=8,PATHFIND_NOT_USING_PATH=16,PATHFIND_NOPATH=32;
namespace Trinity {bool IsValidMapCoord(float x,float y){return std::isfinite(x)&&std::isfinite(y)&&std::abs(x)<17000&&std::abs(y)<17000;}void NormalizeMapCoord(float&) {}}
namespace G3D {struct Vector3 {float x,y,z;};}
struct Position {float m_positionX=0,m_positionY=0,m_positionZ=2,o=0;void SetOrientation(float a){o=a;}void Relocate(float x,float y,float z){m_positionX=x;m_positionY=y;m_positionZ=z;}};
struct Collision {bool hit=false;float clip=20;int calls=0;float inputX=0;
 bool getObjectHitPos(int,float,float,float,float x,float y,float z,float& ox,float& oy,float& oz,float){++calls;inputX=x;ox=hit?clip:x;oy=y;oz=z;return hit;}};
struct Map:Collision {int GetTerrain(){return 0;}float GetGridHeight(int,float,float){return 7;}};
Collision wall;
namespace VMAP {struct VMapFactory {static Collision* createOrGetVMapManager(){return &wall;}};}
struct PhasingHandler {static uint32 GetTerrainMapId(int,uint32,int,float,float){return 0;}};
struct Unit {bool fly=false;bool CanFly()const{return fly;}float GetHoverOffset()const{return 2;}};
struct WorldObject {Map map;float orientation=0;int finalized=0;float ground=5;Unit* unit=nullptr;
 float GetOrientation(){return orientation;}float GetCollisionHeight(){return 4;}int GetPhaseShift(){return 0;}uint32 GetMapId(){return 0;}Map* GetMap(){return &map;}Unit const* ToUnit(){return unit;}
 void UpdateAllowedPositionZ(float,float,float& z,float* g){++finalized;*g=ground;z+=1;}
''' + declaration + r'''
};
struct PathGenerator {inline static int calls=0;inline static unsigned flags=PATHFIND_NORMAL;std::vector<G3D::Vector3> points{{3,4,6}};
 explicit PathGenerator(WorldObject*){++calls;}void SetUseRaycast(bool b){assert(b);}void CalculatePath(float,float,float,bool b){assert(!b);}
 unsigned GetPathType(){return flags;}auto const& GetPath(){return points;}};
''' + r'''namespace WorldObjectMovement { void MovePositionToFirstCollision(WorldObject&,Position&,float,float,bool); }
''' + body + r'''
int main(){
 auto reset=[](){wall={};PathGenerator::calls=0;PathGenerator::flags=PATHFIND_NORMAL;};
 reset();WorldObject obj;Position p;obj.MovePositionToFirstCollision(p,100,0);
 assert(PathGenerator::calls==1 && wall.calls==0 && obj.map.calls==1 && obj.finalized==1);
 assert(p.m_positionX==3 && p.m_positionY==4 && p.m_positionZ==7);
 reset();WorldObject flying;Position q;PathGenerator::flags=PATHFIND_NOT_USING_PATH;
 flying.MovePositionToFirstCollision(q,100,0);
 assert(wall.calls==1 && flying.map.calls==1 && flying.finalized==1);
 assert(q.m_positionX==3 && q.m_positionY==4 && q.m_positionZ==7);
 reset();WorldObject straight;Position r;WorldObjectMovement::MovePositionToFirstCollision(straight,r,100,0,false);
 assert(PathGenerator::calls==0 && wall.calls==1 && straight.map.calls==1 && straight.finalized==1);
 assert(r.m_positionX==100 && r.m_positionY==0 && r.m_positionZ==3);
 reset();wall.hit=true;WorldObject clipped;Position t;
 clipped.map.hit=true;clipped.map.clip=12;WorldObjectMovement::MovePositionToFirstCollision(clipped,t,100,0,false);
 assert(wall.inputX==100 && clipped.map.inputX==19.5f && t.m_positionX==11.5f);
 assert(wall.calls==1 && clipped.map.calls==1 && clipped.finalized==1);
 reset();WorldObject invalidPath;Position unchanged;PathGenerator::flags=PATHFIND_NOPATH;
 invalidPath.MovePositionToFirstCollision(unchanged,100,0);
 assert(unchanged.m_positionX==0 && unchanged.m_positionZ==2 && invalidPath.finalized==0 && wall.calls==0 && invalidPath.map.calls==0);
 for(bool path:{true,false})for(float invalid:{std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN(),20000.f}){
  reset();WorldObject invalidObject;Position pos;WorldObjectMovement::MovePositionToFirstCollision(invalidObject,pos,invalid,0,path);
  assert(pos.m_positionX==0 && pos.m_positionY==0 && pos.m_positionZ==2);
  assert(PathGenerator::calls==0 && wall.calls==0 && invalidObject.map.calls==0 && invalidObject.finalized==0);
 }
 // Existing final grid-height/hover fallback and flying exemption stay shared.
 for(bool path:{true,false})for(bool fly:{true,false}){
  reset();WorldObject fall;Unit unit;unit.fly=fly;fall.unit=&unit;fall.ground=INVALID_HEIGHT;Position pos;
  WorldObjectMovement::MovePositionToFirstCollision(fall,pos,100,0,path);
  assert(pos.m_positionZ==(fly?(path?7:3):9));
 }
}
'''
    path=tmp_path/'collision.cpp';path.write_text(cpp);binary=tmp_path/'collision'
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(path),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
