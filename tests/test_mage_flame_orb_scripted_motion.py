"""Native lifecycle functions with deterministic event/generator dependencies.

Does not simulate terrain, periodic target selection, native spell casts or DPS.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / 'src/server/scripts/World'


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def test_world_npc_registration_identity_and_module_limits():
    # Historical split byte-equivalence was verified when that refactor landed.
    # Keep runtime registration identities without forbidding future NPC fixes.
    groups = ['care', 'services', 'toys', 'summons']
    registrations = []
    for group in groups:
        text = (WORLD / f'npcs_special_{group}.cpp').read_text()
        registrations += re.findall(r'^    (?:new \w+\(\);|RegisterCreatureAI\(\w+\);)$', text, re.M)
        assert len(text.splitlines()) < 1000
    expected = '''npc_air_force_bots npc_chicken_cluck npc_dancing_flames
npc_torch_tossing_target_bunny_controller npc_midsummer_bunny_pole npc_doctor
npc_injured_patient npc_garments_of_quests npc_guardian npc_sayge npc_steam_tonk
npc_tonk_mine npc_tournament_mount npc_brewfest_reveler npc_training_dummy
npc_wormhole npc_pet_trainer npc_experience npc_firework npc_spring_rabbit
npc_imp_in_a_ball npc_stable_master npc_train_wrecker npc_argent_squire_gruntling
npc_bountiful_table npc_mage_orb npc_druid_treant npc_darkmoon_island_gnoll'''.split()
    macros = {'npc_training_dummy', 'npc_mage_orb', 'npc_darkmoon_island_gnoll'}
    assert registrations == [f'    RegisterCreatureAI({name});' if name in macros else f'    new {name}();' for name in expected]
    loader = (WORLD / 'npcs_special.cpp').read_text()
    assert re.findall(r'^    AddSC_npcs_special_(\w+)\(\);$', loader, re.M) == groups


def test_actual_orb_and_base_motion_lifecycle(tmp_path):
    ai = (ROOT / 'src/server/game/AI/CreatureAI.cpp').read_text()
    motion = (ROOT / 'src/server/game/Movement/MotionMaster.cpp').read_text()
    motion_header = (ROOT / 'src/server/game/Movement/MotionMaster.h').read_text()
    script = (WORLD / 'npcs_special_summons.cpp').read_text()
    orb = script[script.index('enum MageOrb'):script.index('enum DruidTreant')]
    enums = motion_header[motion_header.index('enum MovementGeneratorType'):motion_header.index('enum MMCleanFlag')]
    functions = '\n'.join(function(motion, signature) for signature in [
        'void MotionMaster::Clear(bool', 'void MotionMaster::DirectClean(bool',
        'void MotionMaster::UpdateMotion(', 'void MotionMaster::MovementExpired(',
        'void MotionMaster::DirectExpire(bool', 'MovementGeneratorType MotionMaster::GetMotionSlotType('])
    base = function(ai, 'static bool ShouldFollowOnSpawn(') + '\n' + function(ai, 'void CreatureAI::JustAppeared()')
    cpp = r'''
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <vector>
using uint32=uint32_t;using uint8=uint8_t;
using Milliseconds=std::chrono::milliseconds;using Seconds=std::chrono::seconds;
#define ASSERT assert
''' + enums + r'''
constexpr unsigned MMCF_UPDATE=1,MMCF_RESET=2;
struct Unit;
struct MovementGenerator {MovementGeneratorType type;bool done=false;virtual ~MovementGenerator()=default;
 virtual bool Update(Unit*,uint32){return !done;}void Reset(Unit*){}
 MovementGeneratorType GetMovementGeneratorType()const{return type;}};
struct Position {float m_positionX=0,m_positionY=0,m_positionZ=0;
 float GetPositionX()const{return m_positionX;}float GetPositionY()const{return m_positionY;}float GetPositionZ()const{return m_positionZ;}};
struct MotionMaster {
 Unit* _owner;unsigned _cleanFlag=0;int _top=0;std::vector<int> _expireList;
 MovementGenerator* _slot[3]{};int pointCalls=0;Position destination;
 explicit MotionMaster(Unit* owner):_owner(owner){Initialize();}
 ~MotionMaster(){for(auto p:_slot)delete p;}
 void Initialize(){_top=0;_slot[0]=new MovementGenerator{ };_slot[0]->type=IDLE_MOTION_TYPE;}
 bool empty()const{return _top<0;}unsigned size()const{return _top+1;}MovementGenerator* top(){return _slot[_top];}
 void pop(){_slot[_top--]=nullptr;}bool NeedInitTop(){return false;}void InitTop(){}
 void DirectDelete(MovementGenerator* p){delete p;}void DelayedClean(){assert(false);}void DelayedExpire(){assert(false);}void ClearExpireList(){assert(false);}
 void Clear(bool reset=true);void DirectClean(bool);void MovementExpired(bool reset=true);void DirectExpire(bool);void UpdateMotion(uint32);
 bool IsInvalidMovementSlot(MovementSlot s)const{return s>=MAX_MOTION_SLOT;}
 MovementGeneratorType GetMotionSlotType(MovementSlot)const;
 void MoveFollow(Unit*){delete _slot[0];_slot[0]=new MovementGenerator{};_slot[0]->type=FOLLOW_MOTION_TYPE;}
 void MovePoint(uint32,Position const& p,bool generatePath=true){assert(!generatePath);++pointCalls;destination=p;delete _slot[1];_slot[1]=new MovementGenerator{};_slot[1]->type=POINT_MOTION_TYPE;_top=1;}
};
''' + functions + r'''
enum { SUMMON_CATEGORY_PET=2,SUMMON_CATEGORY_WILD=0,SUMMON_CATEGORY_ALLY=1,SUMMON_CATEGORY_UNK=3,SUMMON_PROP_FLAG_UNK14=8192,UNIT_FIELD_HOVERHEIGHT=0 };
enum class SummonTitle {None,Pet,Guardian,Runeblade,Minion,Companion};
struct SummonPropertiesEntry {unsigned Control=1,Flags=4866,Title=0;};
struct SpellInfo {int ProcChance=100;};struct Aura {SpellInfo info;SpellInfo const* GetSpellInfo(){return &info;}};
struct TempSummon;
struct Unit {MotionMaster motion{this};Position position;Aura* talent=nullptr;int explosionCasts=0;
 virtual ~Unit()=default;virtual TempSummon* ToTempSummon(){return nullptr;}
 MotionMaster* GetMotionMaster(){return &motion;}Position GetPosition(){return position;}
 void MovePositionToFirstCollision(Position& p,float distance,float angle,bool usePathfinding=true){assert(!usePathfinding);assert(distance==100 && angle==0);p.m_positionX=10;}
 Aura* GetAuraOfRankedSpell(int){return talent;}void CastSpell(Position const&,int,bool){++explosionCasts;}
};
struct Creature:Unit {uint32 entry=44214;bool combat=false;int despawns=0;std::vector<int> casts;std::vector<uint32> auras;
 bool isMoving(){return motion.GetMotionSlotType(MOTION_SLOT_ACTIVE)==POINT_MOTION_TYPE;}
 uint32 GetEntry(){return entry;}bool IsInCombat(){return combat;}float GetFloatValue(int){return 2;}
 bool HasAura(uint32 id){return std::find(auras.begin(),auras.end(),id)!=auras.end();}
 void DespawnOrUnsummon(){++despawns;}
};
struct TempSummon:Creature {Unit* owner;SummonPropertiesEntry properties;SummonPropertiesEntry* m_Properties=&properties;
 TempSummon(Unit* value):owner(value){}TempSummon* ToTempSummon()override{return this;}
 void* GetVehicle(){return nullptr;}Unit* GetCharmerOrOwner(){return owner;}Unit* GetSummoner(){return owner;}
 void FollowTarget(Unit* target){motion.MoveFollow(target);}
};
struct CreatureAI {Creature* me;explicit CreatureAI(Creature* c):me(c){}virtual ~CreatureAI()=default;
 bool IsEngaged(){return false;}virtual void JustAppeared();virtual void AttackStart(Unit*){}virtual void IsSummonedBy(Unit*){}virtual void UpdateAI(uint32){}
};
''' + base + r'''
struct EventMap {uint32 time=0;std::vector<std::pair<uint32,uint32>> rows;
 template<class T>void ScheduleEvent(uint32 id,T delay){rows.push_back({time+std::chrono::duration_cast<Milliseconds>(delay).count(),id});}
 void Update(uint32 diff){time+=diff;}uint32 ExecuteEvent(){auto i=std::min_element(rows.begin(),rows.end());if(i==rows.end()||i->first>time)return 0;uint32 id=i->second;rows.erase(i);return id;}
};
struct ScriptedAI:CreatureAI {using CreatureAI::CreatureAI;void DoCastSelf(int id,bool){me->casts.push_back(id);}};
bool roll_chance_i(int chance){return chance==100;}
''' + r'''namespace WorldObjectMovement { void MovePositionToFirstCollision(Unit& unit,Position& pos,float distance,float angle,bool path) { unit.MovePositionToFirstCollision(pos,distance,angle,path); } }
''' + orb + r'''
int main(){
 Unit owner;
 // Actual generic base and native Clear/UpdateMotion/expiry functions expose
 // the retained idle slot after deterministic point-generator completion.
 TempSummon legacy(&owner);CreatureAI baseAI(&legacy);baseAI.JustAppeared();
 assert(legacy.motion.GetMotionSlotType(MOTION_SLOT_IDLE)==FOLLOW_MOTION_TYPE);
 legacy.motion.Clear();assert(legacy.motion.GetMotionSlotType(MOTION_SLOT_IDLE)==FOLLOW_MOTION_TYPE);
 legacy.motion.MovePoint(0,{},false);legacy.motion.top()->done=true;legacy.motion.UpdateMotion(1);
 assert(legacy.motion.GetMotionSlotType(MOTION_SLOT_ACTIVE)==MAX_MOTION_TYPE);
 assert(legacy.motion.GetMotionSlotType(MOTION_SLOT_IDLE)==FOLLOW_MOTION_TYPE);
 for(uint32 entry:{44214u,45322u}){
  TempSummon orb(&owner);orb.entry=entry;npc_mage_orb ai(&orb);ai.IsSummonedBy(&owner);ai.JustAppeared();
  assert(orb.motion.GetMotionSlotType(MOTION_SLOT_IDLE)==IDLE_MOTION_TYPE);
  ai.UpdateAI(1);assert(orb.motion.pointCalls==1);assert(orb.motion.destination.m_positionX==10 && orb.motion.destination.m_positionZ==2);
  assert(orb.motion.GetMotionSlotType(MOTION_SLOT_ACTIVE)==POINT_MOTION_TYPE);
  ai.AttackStart(&owner);assert(orb.motion.pointCalls==2);
  ai.UpdateAI(398);assert(orb.casts.empty());ai.UpdateAI(1);
  assert(orb.casts.size()==1 && orb.casts[0]==(entry==44214?82690:84717));
  orb.motion.top()->done=true;orb.motion.UpdateMotion(1);
  assert(orb.motion.GetMotionSlotType(MOTION_SLOT_ACTIVE)==MAX_MOTION_TYPE);
  assert(orb.motion.GetMotionSlotType(MOTION_SLOT_IDLE)==IDLE_MOTION_TYPE);
  int points=orb.motion.pointCalls;ai.AttackStart(&owner);assert(orb.motion.pointCalls==points);
  Aura talent;owner.talent=&talent;int casts=owner.explosionCasts;
  ai.UpdateAI(4600);assert(owner.explosionCasts==casts+1 && orb.despawns==1);
  owner.talent=nullptr; // Native removal stops future updates for this summon.
 }
 // Both variants receive native self-snare 82736 on a successful target hit.
 // A successful-hit Orb can remain victimless and out of combat. It must live
 // through the 5s branch and retain the ordinary 15.4s explosion.
 for(uint32 entry:{44214u,45322u}){
  for(bool engaged:{false,true}){
   TempSummon orb(&owner);orb.entry=entry;orb.combat=engaged;
   npc_mage_orb ai(&orb);ai.IsSummonedBy(&owner);ai.JustAppeared();
   ai.UpdateAI(1);ai.UpdateAI(399);
   // The non-combat case supplies the observed native hit receipt. The combat
   // case independently preserves the original exclusion, without a hit aura.
   if(!engaged)orb.auras.push_back(SPELL_ORB_SELF_SNARE);
   Aura talent;owner.talent=&talent;int casts=owner.explosionCasts;
   ai.UpdateAI(4600);assert(orb.despawns==0 && owner.explosionCasts==casts);
   ai.UpdateAI(10399);assert(orb.despawns==0 && owner.explosionCasts==casts);
   ai.UpdateAI(1);assert(orb.despawns==1 && owner.explosionCasts==casts+1);
   owner.talent=nullptr;
  }
 }
}
'''
    source = tmp_path/'orb.cpp';source.write_text(cpp)
    binary = tmp_path/'orb'
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
