"""Actual PetAI/TotemAI selectors and native predicates skip protected first targets."""
from pathlib import Path
import subprocess

from tests.test_warlock_doomguard_guardian import function

ROOT = Path(__file__).resolve().parents[1]


def test_pet_and_totem_production_selection_continues_after_protected_candidate(tmp_path):
    pet = (ROOT/'src/server/game/AI/CoreAI/PetAI.cpp').read_text()
    totem = (ROOT/'src/server/game/AI/CoreAI/TotemAI.cpp').read_text()
    checks = (ROOT/'src/server/game/Grids/Notifiers/GridNotifiers.h').read_text()
    definitions = '\n'.join([function(pet, 'bool ProtectedEncounterTarget('), function(pet, 'bool ControlledOffenseSuppressed('),
                            function(totem, 'bool TotemSpellHasHostileMultiTargetSemantics('), function(totem, 'bool ProtectedTotemTarget(')])
    native_checks = '\n'.join(function(checks, 'class '+name)+';' for name in ('NearestHostileUnitInAggroRangeCheck', 'NearestAttackableUnitInObjectRangeCheck'))
    source = tmp_path/'selection.cpp'
    source.write_text(r'''
#include "Bots/BotRaidAreaAuthority.h"
#include "ObjectGuid.h"
#include <cassert>
#include <cmath>
#include <vector>
#include <map>
inline ObjectGuid const ObjectGuid::Empty;
constexpr uint32 REACT_PASSIVE=0,REACT_ASSIST=1,REACT_AGGRESSIVE=2,REACT_DEFENSIVE=3;
constexpr float MAX_AGGRO_RADIUS=45;
constexpr uint32 TOTEM_ACTIVE=1,UNIT_FIELD_FLAGS=0,UNIT_FLAG_PLAYER_CONTROLLED=1,MAX_SPELL_EFFECTS=3;
constexpr uint32 SPELL_EFFECT_PERSISTENT_AREA_AURA=27;
enum TriggerCastFlags{TRIGGERED_NONE,TRIGGERED_IGNORE_TARGET_CHECK};
enum SpellCastResult{SPELL_CAST_OK};struct CastSpellExtraArgs{TriggerCastFlags Flags;explicit CastSpellExtraArgs(TriggerCastFlags f):Flags(f){}};
struct SpellEffectInfo{uint32 ChainTarget=0,TriggerSpell=0;bool IsEffect(uint32 id=0)const{return !id;}bool IsTargetingArea()const{return false;}bool IsAreaAuraEffect()const{return false;}};
struct SpellInfo{uint32 Id=3606;SpellEffectInfo Effects[3];bool IsPositiveEffect(uint32)const{return false;}float GetMaxRange(bool)const{return 30;}};
struct SpellMgr{SpellInfo spell;SpellInfo const* GetSpellInfo(uint32)const{return &spell;}}manager;
SpellMgr* sSpellMgr=&manager;
struct Creature;struct Totem;
struct Unit{virtual ~Unit()=default;ObjectGuid guid{HighGuid::Player,30010u};uint32 entry=0,type=TYPEID_PLAYER;
 Unit* owner=nullptr;Unit* helper=nullptr;Unit* victim=nullptr;float pos=0;bool alive=true,valid=true,visible=true,hostile=true,los=true,cc=false,inert=false,casting=false;
 ObjectGuid GetGUID()const{return guid;}uint32 GetEntry()const{return entry;}uint32 GetTypeId()const{return type;}
 Creature const* ToCreature()const;Creature* ToCreature();Totem* ToTotem();
 Unit* GetCharmerOrOwner()const{return owner;}Unit* GetVictim()const{return victim;}Unit* getAttackerForHelper()const{return helper;}
 bool IsAlive()const{return alive;}bool HasBreakableByDamageCrowdControlAura()const{return cc;}
 bool isTargetableForAttack()const{return alive&&valid;}
 float GetDistance(Unit const* u)const{return std::fabs(pos-u->pos);}
 bool IsWithinDistInMap(Unit const* u,float dist)const{return GetDistance(u)<=dist;}
 bool CanSeeOrDetect(Unit const* u)const{return u->visible;}bool IsHostileTo(Unit const* u)const{return u->hostile;}
 bool IsInCombatWith(Unit const*)const{return false;}bool IsWithinLOSInMap(Unit const* u)const{return los&&u->los;}
 bool IsValidAttackTarget(Unit const* u,SpellInfo const* =nullptr)const{return !inert&&u&&u->alive&&u->valid&&u->hostile;}
 bool IsNonMeleeSpellCast(bool)const{return casting;}void InterruptNonMeleeSpells(bool){casting=false;}
 void SetFlag(uint32,uint32){}
};
using WorldObject=Unit;
struct Creature:Unit{uint32 react=REACT_DEFENSIVE;bool civilian=false;uint32 spawn=0;
 struct Charm{bool IsReturning()const{return false;}bool IsFollowing()const{return true;}bool IsAtStay()const{return false;}}charm;
 Creature(uint32 e,uint32 id){entry=e;guid=ObjectGuid(HighGuid::Unit,e,id);type=TYPEID_UNIT;}
 uint32 GetSpawnId()const{return spawn;}bool HasReactState(uint32 r)const{return react==r;}Charm const* GetCharmInfo()const{return &charm;}
 Unit* SelectNearestHostileUnitInAggroRange(bool,bool)const;
 float GetAggroRange(Unit*)const{return 30;}bool IsCivilian()const{return civilian;}
 struct Cast{ObjectGuid target;TriggerCastFlags flags;};std::vector<Cast> casts;
 SpellCastResult CastSpell(Unit* u,uint32,CastSpellExtraArgs const& args){casts.push_back({u->guid,args.Flags});return SPELL_CAST_OK;}
};
struct Totem:Creature{Unit* realOwner=nullptr;Totem():Creature(2523,100){}uint32 GetTotemType()const{return TOTEM_ACTIVE;}uint32 GetSpell()const{return manager.spell.Id;}Unit* GetOwner()const{return realOwner;}};
Creature const* Unit::ToCreature()const{return dynamic_cast<Creature const*>(this);}Creature* Unit::ToCreature(){return dynamic_cast<Creature*>(this);}Totem* Unit::ToTotem(){return dynamic_cast<Totem*>(this);}
inline std::vector<Unit*> candidates;
namespace ObjectAccessor{Unit* GetUnit(Unit const&,ObjectGuid guid){for(auto u:candidates)if(u->guid==guid)return u;return nullptr;}}
namespace Trinity{
''' + native_checks + r'''
template<class Check>struct UnitSearcher{Unit*& target;Check& check;UnitSearcher(Unit const*,Unit*&t,Check&c):target(t),check(c){}void Visit(Unit*u){if(!target&&check(u))target=u;}};
template<class Check>struct UnitLastSearcher{Unit*& target;Check& check;UnitLastSearcher(Unit const*,Unit*&t,Check&c):target(t),check(c){}void Visit(Unit*u){if(check(u))target=u;}};
}
namespace Cell{template<class Search>void VisitGridObjects(Unit const*,Search& search,float){for(auto u:candidates)search.Visit(u);}template<class Search>void VisitAllObjects(Unit const*u,Search&search,float range){VisitGridObjects(u,search,range);}}
Unit* Creature::SelectNearestHostileUnitInAggroRange(bool los,bool civilian)const{Unit* target=nullptr;Trinity::NearestHostileUnitInAggroRangeCheck check(this,los,civilian);Trinity::UnitSearcher<decltype(check)> searcher(this,target,check);Cell::VisitGridObjects(this,searcher,MAX_AGGRO_RADIUS);return target;}
struct PetAI{Creature* me;Unit* SelectNextTarget(bool)const;};
struct TotemAI{Creature* me;ObjectGuid _victimGUID;uint32 _updateCalls=0,_castingSkips=0,_missingSpellSkips=0,_noTargetSkips=0,_castAttempts=0,_castSuccesses=0;bool _lastTotemTargetValid=false,_lastOwnerTargetValid=false;SpellCastResult _lastCastResult=SPELL_CAST_OK;void UpdateAI(uint32);};
''' + definitions + '\n' + function(pet, 'Unit* PetAI::SelectNextTarget(') + '\n' + function(totem, 'void TotemAI::UpdateAI(') + r'''
int main(){using namespace BotRaidAreaAuthority;Unit owner;auto key=owner.guid.GetRawValue();Creature pet(417,2),blocked(41806,191),body(41570,39),head(42347,76);
 pet.owner=&owner;PetAI ai{&pet};blocked.pos=5;body.pos=10;head.pos=12;
 SetCurrentEncounterRestrictions(key,{41806,42321},{});
 pet.helper=owner.helper=&blocked;owner.victim=&body;assert(ai.SelectNextTarget(false)==&body);
 owner.victim=&head;assert(ai.SelectNextTarget(false)==&head);
 owner.victim=nullptr;pet.react=REACT_AGGRESSIVE;candidates={&blocked,&body};assert(ai.SelectNextTarget(true)==&body);
 candidates={&body,&blocked};assert(ai.SelectNextTarget(true)==&body);
 body.los=false;assert(!ai.SelectNextTarget(true));body.los=true;body.civilian=true;assert(!ai.SelectNextTarget(true));body.civilian=false;
 SetCurrentEncounterRestrictions(key,{41806,42321},{blocked.guid.GetRawValue()});assert(ai.SelectNextTarget(false)==&blocked);
 SetProtectedEncounterEntries(key,{41806});owner.victim=&body;assert(ai.SelectNextTarget(false)==&body);
 SetAllOffenseSuppressed(key,true);assert(!ai.SelectNextTarget(true));SetAllOffenseSuppressed(key,false);
 SetProtectedEncounterEntries(key,{});SetCurrentEncounterRestrictions(key,{41806,42321},{});
 Totem totem;totem.realOwner=&owner;TotemAI t{&totem};candidates={&blocked,&body};t.UpdateAI(1);assert(!totem.casts.empty()&&totem.casts.back().target==body.guid);
 // The blocked 5yd candidate must not shrink the native check below legal 10yd body.
 t._victimGUID.Clear();candidates={&body,&blocked};t.UpdateAI(1);assert(!totem.casts.empty()&&totem.casts.back().target==body.guid);
 SetProtectedEncounterEntries(key,{41570});t._victimGUID.Clear();candidates={&blocked,&body,&head};t.UpdateAI(1);assert(totem.casts.back().target==head.guid);
 auto count=totem.casts.size();SetProtectedEncounterEntries(key,{41570,42347});t._victimGUID.Clear();t.UpdateAI(1);assert(totem.casts.size()==count&&!t._victimGUID);
 SetProtectedEncounterEntries(key,{});SetCurrentEncounterRestrictions(key,{41806,42321},{blocked.guid.GetRawValue()});t.UpdateAI(1);assert(totem.casts.back().target==blocked.guid);
 // Native owner-legality fallback and area suppression are preserved.
 totem.inert=true;t._victimGUID.Clear();t.UpdateAI(1);assert(totem.casts.back().flags==TRIGGERED_IGNORE_TARGET_CHECK);
 count=totem.casts.size();manager.spell.Effects[0].ChainTarget=2;t.UpdateAI(1);assert(totem.casts.size()==count);
 manager.spell.Effects[0].ChainTarget=0;SetAllOffenseSuppressed(key,true);t.UpdateAI(1);assert(totem.casts.size()==count);Clear(key);
 pet.helper=&blocked;assert(ai.SelectNextTarget(false)==&blocked);
}
''')
    binary = tmp_path/'selection'
    subprocess.run(['g++', '-std=c++17', '-I', str(ROOT/'src/server/game'), '-I', str(ROOT/'src/common'), '-I', str(ROOT/'src/server/game/Entities/Object'), str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
