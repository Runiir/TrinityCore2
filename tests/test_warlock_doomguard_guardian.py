"""DPS-053: real guardian script, UnitAI authority/submission and EventMap.

Object graph, native CastSpell outcome and movement execution are controlled
boundaries. This proves AI requests/ownership, not native landed damage/lifetime.
"""
import json
from pathlib import Path
import sqlite3
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'src/server/scripts/Pet/pet_warlock.cpp'
SQL = ROOT / 'sql/custom/world/2026_09_13_03_warlock_doomguard_native_cast.sql'
FIXTURE = ROOT / 'tests/fixtures/warlock_doomguard_63d_native.json'


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def native_inputs():
    n = json.loads(FIXTURE.read_text())['native']
    spell = n['Spell']['rows'][0]
    ranges = n['SpellRange']['rows'][0]
    return dict(max_range=struct.unpack('<f', struct.pack('<I', ranges[3]))[0],
                cast_time=n['SpellCastTimes']['rows'][0][1], family=n['SpellClassOptions']['rows'][0][5],
                school=spell[25], target=n['SpellEffect']['rows'][0][22])


STUB = r'''
#pragma once
#include "Define.h"
#include "ObjectGuid.h"
#include "EventMap.h"
#include <algorithm>
#include <cassert>
#include <map>
#include <string>
#include <vector>
inline ObjectGuid const ObjectGuid::Empty;
constexpr uint32 CLASS_WARLOCK=9,UNIT_STATE_CASTING=1,TRIGGERED_IGNORE_CAST_IN_PROGRESS=1;
constexpr uint32 MAX_SPELL_EFFECTS=3,SPELL_EFFECT_PERSISTENT_AREA_AURA=27,SPELL_EFFECT_APPLY_AURA=6;
constexpr uint32 TARGET_UNIT_TARGET_ENEMY=6,TARGET_DEST_TARGET_ENEMY=53,TARGET_UNIT_DEST_AREA_ENEMY=16;
constexpr uint32 SPELL_ATTR0_ALLOW_CAST_WHILE_DEAD=1,SPELLFAMILY_WARLOCK=5;
enum SpellCastResult{SPELL_CAST_OK,SPELL_FAILED_BAD_TARGETS,SPELL_FAILED_SPELL_IN_PROGRESS,SPELL_FAILED_OUT_OF_RANGE,SPELL_FAILED_LINE_OF_SIGHT};
struct CastSpellExtraArgs{uint32 TriggerFlags=0;};
struct SpellEffectInfo{uint32 Effect=2,ChainTarget=0,TriggerSpell=0;struct Target{uint32 GetTarget()const{return 6;}}TargetA;
 bool IsEffect(uint32 kind=0)const{return !kind||kind==Effect;}bool IsTargetingArea()const{return false;}bool IsAreaAuraEffect()const{return false;}};
struct SpellInfo{uint32 Id=85692,RecoveryTime=0,StartRecoveryTime=0,SpellFamilyName=5;SpellEffectInfo Effects[3];
 float MaxRange=NATIVE_RANGE;bool Positive=false;
 bool IsPositive()const{return Positive;}bool IsPositiveEffect(uint32)const{return Positive;}
 bool HasAttribute(uint32)const{return false;}bool IsPassive()const{return false;}int32 GetDuration()const{return 0;}
 float GetMaxRange(bool)const{return MaxRange;}uint32 GetSchoolMask()const{return 32;}};
struct SpellMgr{SpellInfo spell;bool available=true;SpellInfo const* GetSpellInfo(uint32 id)const{return available&&id==85692?&spell:nullptr;}uint32 GetSpellInfoStoreSize()const{return 85693;}};
inline SpellMgr manager;inline SpellMgr* sSpellMgr=&manager;
struct Player;struct Creature;struct Unit;
struct CombatRef{Unit* target;bool suppressed=false;Unit* GetOther(Unit const*)const{return target;}bool IsSuppressedFor(Unit const*)const{return suppressed;}};
struct CombatManager{std::vector<std::pair<int,CombatRef*>> pve,pvp;auto const& GetPvECombatRefs()const{return pve;}auto const& GetPvPCombatRefs()const{return pvp;}};
struct AuraApplication{};
struct MotionMaster{Unit* chase=nullptr;float range=0;uint32 follows=0,clears=0;
 void MoveChase(Unit* t,float r){chase=t;range=r;}void Clear(){++clears;chase=nullptr;}};
struct Request{uint32 spell;ObjectGuid target;SpellCastResult result;uint32 flags;};
inline std::map<ObjectGuid,Unit*> world;
struct Unit{CombatManager combat;std::map<std::pair<uint32,ObjectGuid>,AuraApplication> auras;
 CombatManager& GetCombatManager(){return combat;}
 AuraApplication const* GetAuraApplication(uint32 spell,ObjectGuid caster)const{auto it=auras.find({spell,caster});return it==auras.end()?nullptr:&it->second;}
 ObjectGuid guid;uint32 entry=0,map=1;bool alive=true,inWorld=true,hostile=true,inCombat=true,cc=false,los=true;
 Unit* owner=nullptr;Unit* victim=nullptr;float distance=20,shadowPower=0;bool minion=false;uint32 casting=0,interrupts=0,stops=0,melee=0;MotionMaster motion;std::vector<Request> requests;
 virtual ~Unit()=default;
 ObjectGuid GetGUID()const{return guid;}uint32 GetEntry()const{return entry;}Unit* GetOwner()const{return owner;}
 bool IsAlive()const{return alive;}bool IsInWorld()const{return inWorld;}bool IsInCombat()const{return inCombat;}
 bool IsInMap(Unit const* t)const{return t&&map==t->map;}
 bool IsValidAttackTarget(Unit const* t)const{return t&&t!=this&&t->hostile&&t->alive&&IsInMap(t);}
 bool HasBreakableByDamageCrowdControlAura(Unit const*)const{return cc;}
 bool HasUnitState(uint32 state)const{return state==UNIT_STATE_CASTING&&casting;}
 Unit* GetVictim()const{return victim;}Player* ToPlayer();Creature* ToCreature();Creature const* ToCreature()const;
 Player* GetCharmerOrOwnerPlayerOrPlayerItself();
 bool Attack(Unit* t,bool melee){assert(!melee);victim=t;return true;}
 MotionMaster* GetMotionMaster(){return &motion;}void AttackStop(){++stops;victim=nullptr;}
 void InterruptNonMeleeSpells(bool){++interrupts;casting=0;}void FollowTarget(Unit*){++motion.follows;motion.chase=nullptr;}void StopMoving(){}
 int32 GetCurrentSpellCastTime(uint32 id)const{return id==85692&&casting?NATIVE_CAST_TIME:0;}
 SpellCastResult CastSpell(Unit* target,uint32 id,CastSpellExtraArgs const& args){
  auto result=!target?SPELL_FAILED_BAD_TARGETS:distance>manager.spell.MaxRange?SPELL_FAILED_OUT_OF_RANGE:!target->los?SPELL_FAILED_LINE_OF_SIGHT:SPELL_CAST_OK;
  requests.push_back({id,target?target->guid:ObjectGuid::Empty,result,args.TriggerFlags});if(result==SPELL_CAST_OK)casting=NATIVE_CAST_TIME;return result;}
 bool IsMinion()const{return minion;}float SpellBaseDamageBonusDone(uint32 mask,bool)const{assert(mask==32);return shadowPower;}
 float InheritanceBranch(SpellInfo const* spellProto,float local);
};
struct Player:Unit{uint32 klass=9;Player(uint32 id){guid=ObjectGuid(HighGuid::Player,id);world[guid]=this;}uint32 getClass()const{return klass;}};
struct Creature:Unit{uint32 spawn=0;Creature(uint32 e,uint32 id){entry=e;guid=ObjectGuid(HighGuid::Unit,e,id);world[guid]=this;}uint32 GetSpawnId()const{return spawn;}};
inline Player* Unit::ToPlayer(){return dynamic_cast<Player*>(this);}inline Creature* Unit::ToCreature(){return dynamic_cast<Creature*>(this);}
inline Creature const* Unit::ToCreature()const{return dynamic_cast<Creature const*>(this);}
inline Player* Unit::GetCharmerOrOwnerPlayerOrPlayerItself(){return owner?owner->ToPlayer():ToPlayer();}
namespace ObjectAccessor{inline Unit* GetUnit(Unit const&,ObjectGuid id){auto it=world.find(id);return it==world.end()?nullptr:it->second;}}
AISPELL_STRUCTS
struct UnitAI{Unit* me;explicit UnitAI(Unit* u):me(u){}static AISpellInfoType* AISpellInfo;
 static void FillAISpellInfo();void AttackStartCaster(Unit*,float);SpellCastResult DoCast(Unit*,uint32,CastSpellExtraArgs const& args={});};
inline AISpellInfoType* UnitAI::AISpellInfo=nullptr;
inline AISpellInfoType* GetAISpellInfo(uint32 i){return &UnitAI::AISpellInfo[i];}
struct CreatureAI:UnitAI{Creature* me;explicit CreatureAI(Creature* c):UnitAI(c),me(c){}virtual ~CreatureAI()=default;
 virtual void Reset(){}virtual void IsSummonedBy(Unit*){}virtual void MoveInLineOfSight(Unit*){}virtual void OwnerAttackedBy(Unit*){}
 virtual void JustEngagedWith(Unit*){}virtual void OwnerAttacked(Unit*){}virtual void AttackStart(Unit*){}virtual void UpdateAI(uint32){}
 virtual void SpellInterrupted(uint32,uint32){} };
struct AggressorAI:CreatureAI{explicit AggressorAI(Creature*c):CreatureAI(c){}bool UpdateVictim(){return me->GetVictim()!=nullptr;}void DoMeleeAttackIfReady(){++me->melee;}void UpdateAI(uint32)override;};
struct CombatAI:CreatureAI{EventMap events;explicit CombatAI(Creature* c):CreatureAI(c){}void Reset()override{events.Reset();}};
struct CasterAI:CombatAI{explicit CasterAI(Creature* c):CombatAI(c){}void UpdateAI(uint32)override{assert(false&&"inherited autonomous victim selection invoked");}};
inline std::string registered;
#define RegisterCreatureAI(type) do{registered=#type;}while(false)
'''


def compile_guardian(tmp_path, main):
    inputs = native_inputs()
    info = (ROOT / 'src/server/game/AI/CreatureAIImpl.h').read_text()
    structs = info[info.index('enum AITarget'):info.index('AISpellInfoType* GetAISpellInfo')]
    stub = STUB.replace('NATIVE_RANGE', repr(inputs['max_range'])+'f').replace('NATIVE_CAST_TIME', str(inputs['cast_time'])).replace('AISPELL_STRUCTS', structs)
    (tmp_path / 'stub.h').write_text(stub)
    for name in ('ScriptMgr.h', 'CombatAI.h', 'CombatManager.h', 'Creature.h', 'CreatureAIImpl.h', 'MotionMaster.h', 'ObjectAccessor.h', 'Player.h', 'SpellInfo.h', 'SpellMgr.h'):
        (tmp_path / name).write_text('#include "stub.h"\n')
    unit_ai = (ROOT / 'src/server/game/AI/CoreAI/UnitAI.cpp').read_text()
    guards = '\n'.join(function(unit_ai, sig) for sig in (
        'bool SpellHasHostileMultiTargetSemantics(', 'bool RaidControlledOffenseRejected(',
        'void UnitAI::AttackStartCaster(', 'SpellCastResult UnitAI::DoCast(Unit*', 'void UnitAI::FillAISpellInfo('))
    guards += '\n' + function((ROOT/'src/server/game/AI/CoreAI/CombatAI.cpp').read_text(), 'void AggressorAI::UpdateAI(')
    unit = (ROOT / 'src/server/game/Entities/Unit/Unit.cpp').read_text()
    start = unit.index('        case SPELLFAMILY_WARLOCK:', unit.index('// Custom scripted damage'))
    end = unit.index('        case SPELLFAMILY_MAGE:', start)
    inheritance = 'float Unit::InheritanceBranch(SpellInfo const* spellProto,float local){Unit* owner=GetOwner();float DoneAdvertisedBenefit=local;switch(spellProto->SpellFamilyName){\n'+unit[start:end]+'default:break;}return DoneAdvertisedBenefit;}\n'
    source = tmp_path / 'guardian.cpp'
    source.write_text('#include "stub.h"\n#include "Bots/BotRaidAreaAuthority.h"\n#define UPDATE_TARGET(a) {if (AIInfo->target<a) AIInfo->target=a;}\n' + guards + '\n' + inheritance + '\n#include "'+str(SCRIPT)+'"\n'+main)
    binary = tmp_path / 'guardian'
    subprocess.run(['g++', '-std=c++17', '-ffunction-sections', '-fdata-sections', '-I', str(tmp_path), '-I', str(ROOT/'src/server/game'), '-I', str(ROOT/'src/common'), '-I', str(ROOT/'src/common/Utilities'), '-I', str(ROOT/'src/server/game/Entities/Object'), str(source), str(ROOT/'src/common/Utilities/EventMap.cpp'), '-Wl,--gc-sections', '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_owned_bane_targets_actual_unitai_guards_and_native_event_schedule(tmp_path):
    compile_guardian(tmp_path, r'''
int main(){using namespace BotRaidAreaAuthority;using Pets::Warlock::npc_pet_warlock_doomguard;
 UnitAI::FillAISpellInfo();assert(GetAISpellInfo(85692)->target==AITARGET_VICTIM);assert(GetAISpellInfo(85692)->maxRange==22.5f);
 EventMap eventMap;eventMap.ScheduleEvent(85692,0);assert(eventMap.ExecuteEvent()==20156);
 Player owner(30008),foreign(30007);Creature guardian(11859,172),primary(417,2),body(41570,39),head(42347,76),optional(41806,191),arbitrary(41806,192),nearby(99999,193);
 guardian.owner=primary.owner=&owner;guardian.minion=primary.minion=true;
 Creature before(11859,171);before.owner=&owner;before.victim=&body;AggressorAI oldAI(&before);oldAI.UpdateAI(1);
 assert(before.melee==1&&before.requests.empty()); // Actual old producer: no Doom Bolt.

 auto key=owner.guid.GetRawValue();SetCurrentEncounterRestrictions(key,{41806,42321},{optional.guid.GetRawValue()});
 CombatRef bodyRef{&body},headRef{&head},optionalRef{&optional},arbitraryRef{&arbitrary};
 npc_pet_warlock_doomguard ai(&guardian);ai.Reset();ai.IsSummonedBy(&owner);
 auto bane=[&](Unit& target,uint32 spell){target.auras[{spell,owner.guid}]={};};
 auto advance=[&](uint32 diff){guardian.casting=diff>=guardian.casting?0:guardian.casting-diff;ai.UpdateAI(diff);};
 auto clearCombat=[&](){guardian.InterruptNonMeleeSpells(false);guardian.AttackStop();ai.Reset();};
 ai.MoveInLineOfSight(&nearby);ai.OwnerAttackedBy(&nearby);ai.JustEngagedWith(&nearby);ai.AttackStart(&nearby);ai.UpdateAI(1);
 assert(guardian.requests.empty()&&!guardian.victim);
 // Real player callback occurs before aura application. Pending identity is not eligibility.
 ai.OwnerAttacked(&body);ai.UpdateAI(1);assert(guardian.requests.empty());
 bane(body,603);ai.UpdateAI(1);assert(guardian.requests.size()==1&&guardian.requests.back().spell==85692&&guardian.requests.back().target==body.guid);
 assert(guardian.requests.back().flags==0&&guardian.motion.range==22.5f);
 advance(1699);assert(guardian.requests.size()==1);advance(1);assert(guardian.requests.size()==2);
 ai.OwnerAttacked(&nearby);advance(1700);assert(guardian.requests.back().target==body.guid);
 head.auras[{603,foreign.guid}]={};head.auras[{980,foreign.guid}]={};bane(head,80240);
 ai.OwnerAttacked(&head);advance(1700);assert(guardian.requests.back().target==body.guid);
 // Multiple eligible Banes retain the current target, irrespective of owner callbacks.
 bane(optional,980);ai.OwnerAttacked(&optional);advance(1700);assert(guardian.requests.back().target==body.guid);
 auto interrupted=guardian.interrupts;body.auras.clear();advance(1700);
 assert(guardian.requests.back().target==optional.guid&&guardian.interrupts==interrupted+1);
 // Pre-existing aura discovery uses combat references, no selected target/grid scan.
 owner.combat.pvp={{1,&headRef}};bane(head,980);ai.OwnerAttacked(&nearby);advance(1700);assert(guardian.requests.back().target==optional.guid);
 optional.auras.clear();advance(1700);assert(guardian.requests.back().target==head.guid);
 owner.combat.pve={{1,&bodyRef}};bane(body,603);head.alive=false;advance(1700);assert(guardian.requests.back().target==body.guid);
 // Bane replacement by Havoc, removal/dispel, and foreign ownership all exclude.
 body.auras.clear();bane(body,80240);auto count=guardian.requests.size();ai.UpdateAI(1);assert(!guardian.victim&&!guardian.casting&&guardian.requests.size()==count);
 head.alive=true;head.auras.clear();head.auras[{603,foreign.guid}]={};head.auras[{980,foreign.guid}]={};advance(1700);assert(guardian.requests.size()==count);
 // Lowest raw GUID is an explicitly inferred tie-break, NOT boss preference.
 bane(head,980);bane(optional,980);owner.combat.pve={{1,&headRef},{2,&optionalRef}};owner.combat.pvp.clear();clearCombat();ai.IsSummonedBy(&owner);ai.UpdateAI(1);
 assert(optional.guid<head.guid&&guardian.requests.back().target==optional.guid);
 std::reverse(owner.combat.pve.begin(),owner.combat.pve.end());clearCombat();ai.UpdateAI(1);assert(guardian.requests.back().target==optional.guid);
 optional.auras.clear();clearCombat();ai.UpdateAI(1);assert(guardian.requests.back().target==head.guid);
 bane(optional,980);ai.OwnerAttacked(&optional);advance(1700);assert(guardian.requests.back().target==head.guid);
 // A current eligible target survives a lower GUID appearing, but not authority loss.
 clearCombat();ai.UpdateAI(1);assert(guardian.requests.back().target==optional.guid);
 SetCurrentEncounterRestrictions(key,{41806,42321},{});advance(1700);assert(guardian.requests.back().target==head.guid);
 count=guardian.requests.size();SetProtectedEncounterEntries(key,{42347});ai.UpdateAI(1);assert(!guardian.victim&&!guardian.casting&&guardian.requests.size()==count);
 SetProtectedEncounterEntries(key,{});advance(1700);assert(guardian.requests.size()==count+1);
 count=guardian.requests.size();SetAllOffenseSuppressed(key,true);ai.UpdateAI(1);assert(!guardian.victim&&!guardian.casting&&guardian.requests.size()==count);
 SetAllOffenseSuppressed(key,false);advance(1700);assert(guardian.requests.size()==count+1);
 // Do not discard an eligible out-of-range Bane: native caster movement owns approach.
 guardian.distance=31;advance(1700);assert(guardian.victim==&head&&guardian.motion.range==22.5f&&guardian.requests.back().result==SPELL_FAILED_OUT_OF_RANGE);
 guardian.distance=20;advance(500);assert(guardian.requests.back().result==SPELL_CAST_OK);
 head.los=false;advance(1700);assert(guardian.requests.back().result==SPELL_FAILED_LINE_OF_SIGHT);head.los=true;advance(500);
 count=guardian.requests.size();guardian.casting=0;ai.SpellInterrupted(85692,3000);ai.UpdateAI(2999);assert(guardian.requests.size()==count);ai.UpdateAI(1);assert(guardian.requests.size()==count+1);
 // Native final submission guards remain independently effective.
 UnitAI sink(&guardian);SetProtectedEncounterEntries(key,{42347});count=guardian.requests.size();guardian.casting=0;
 assert(sink.DoCast(&head,85692)==SPELL_FAILED_BAD_TARGETS&&guardian.requests.size()==count);guardian.AttackStop();sink.AttackStartCaster(&head,22.5f);assert(!guardian.victim);
 SetProtectedEncounterEntries(key,{});guardian.casting=1;assert(sink.DoCast(&head,85692)==SPELL_FAILED_SPELL_IN_PROGRESS);guardian.casting=0;
 head.cc=true;ai.UpdateAI(1);assert(!guardian.victim);head.cc=false;
 head.hostile=false;ai.UpdateAI(1);assert(!guardian.victim);head.hostile=true;
 manager.available=false;ai.UpdateAI(1);assert(!guardian.victim);manager.available=true;
 owner.inCombat=false;ai.UpdateAI(1);assert(!guardian.victim&&!guardian.casting);owner.inCombat=true;
 owner.klass=8;ai.OwnerAttacked(&head);ai.UpdateAI(1);assert(!guardian.victim);owner.klass=9;
 owner.alive=false;ai.UpdateAI(1);assert(!guardian.victim);owner.alive=true;
 owner.map=2;ai.UpdateAI(1);assert(!guardian.victim);owner.map=1;
 // Native existing minion branch, including nonzero local contribution, unchanged.
 owner.shadowPower=1000;assert(guardian.InheritanceBranch(&manager.spell,123)==500);
 owner.shadowPower=2000;assert(guardian.InheritanceBranch(&manager.spell,123)==1000);
 guardian.minion=false;assert(guardian.InheritanceBranch(&manager.spell,123)==123);
 assert(primary.alive&&primary.owner==&owner&&primary.requests.empty());
 AddSC_warlock_pet_scripts();assert(registered=="npc_pet_warlock_doomguard");Clear(key);delete[] UnitAI::AISpellInfo;
}
''')


def test_template_migration_idempotence_binding_and_native_identity():
    fixture = json.loads(FIXTURE.read_text())
    before = fixture['template_before']
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE creature_template('+','.join(f'`{k}` '+('TEXT' if isinstance(v, str) else 'INTEGER') for k, v in before.items())+')')
    for entry in (11859, 417, 15438):
        row = dict(before, entry=entry)
        db.execute('INSERT INTO creature_template VALUES('+','.join('?' for _ in row)+')', tuple(row.values()))
    old = [dict(r) for r in db.execute('SELECT * FROM creature_template ORDER BY entry')]
    assert before['ScriptName'] == before['AIName'] == '' and 85692 not in [before[f'spell{i}'] for i in range(1, 9)]
    db.executescript(SQL.read_text())
    after = [dict(r) for r in db.execute('SELECT * FROM creature_template ORDER BY entry')]
    expected = dict(before, AIName='', ScriptName='npc_pet_warlock_doomguard', spell1=85692,
                    **{f'spell{i}': 0 for i in range(2, 9)})
    assert next(r for r in after if r['entry'] == 11859) == expected
    assert [r for r in after if r['entry'] != 11859] == [r for r in old if r['entry'] != 11859]
    db.executescript(SQL.read_text())
    assert [dict(r) for r in db.execute('SELECT * FROM creature_template ORDER BY entry')] == after
    assert native_inputs() == dict(max_range=30.0, cast_time=1700, family=5, school=32, target=6)
    assert fixture['native']['SummonProperties']['rows'] == [[61, 1, 0, 2, 0, 2]]
    # Existing approved summon fixture binds the unchanged 18540 -> 60478 ->11859.
    previous = json.loads((ROOT/'tests/fixtures/affliction_doomguard_native.json').read_text())['native']
    effects = {row[24]: row for row in previous['SpellEffect']['rows']}
    assert effects[18540][21] == 60478
    assert (effects[60478][12], effects[60478][13]) == (11859, 61)
    assert previous['SpellDuration']['rows'][0][1] == 45000
    assert fixture['doom_bolt_event_count'] == 0 and fixture['landed_melee_count'] == 21
    assert fixture['landed_melee_damage'] == 8287


def test_native_bane_identity_callback_order_and_script_registration():
    fixture = json.loads(FIXTURE.read_text())
    bane = {r['spell_id']: r for r in fixture['bane_authority']['rows']}
    assert bane[603]['name'] == 'Bane of Doom'
    assert bane[980]['name'] == 'Bane of Agony'
    assert bane[80240]['name'] == 'Bane of Havoc'
    assert 'your Bane of Doom or Bane of Agony' in bane[18540]['description']
    assert bane[603]['attributes'][5] & 0x20
    assert not bane[980]['attributes'][5] & 0x20
    assert fixture['bane_authority']['spell_dbc_sha256'] == fixture['native']['Spell']['sha256']
    spell = (ROOT/'src/server/game/Spells/Spell.cpp').read_text()
    start = spell.index('// As of 3.0.2 pets begin attacking')
    end = spell.index('SetExecutedCurrently(true)', start)
    callback = spell[start:end]
    assert 'DmgClass != SPELL_DAMAGE_CLASS_NONE' in callback
    assert 'for (Unit* controlled : playerCaster->m_Controlled)' in callback
    assert 'controlledAI->OwnerAttacked(unitTarget);' in callback
    source = SCRIPT.read_text()
    assert 'target->GetAuraApplication(603, Owner()->GetGUID())' in source
    assert 'target->GetAuraApplication(980, Owner()->GetGUID())' in source
    assert 'CasterAI::UpdateAI(' not in source and 'UpdateVictim(' not in source
    assert 'IsCurrentEncounterRestrictedEntry' not in source
    assert all(str(entry) not in source for entry in (41570, 42347, 41806, 42321))
    assert 'Stable raw-GUID fallback is inferred' in source
    loader = (ROOT/'src/server/scripts/Pet/pet_script_loader.cpp').read_text()
    assert 'void AddSC_warlock_pet_scripts();' in loader
    assert '    AddSC_warlock_pet_scripts();' in loader
    assert 'RegisterCreatureAI(npc_pet_warlock_doomguard);' in source
    selection = (ROOT/'src/server/game/AI/CreatureAISelector.cpp').read_text()
    assert selection.index('sScriptMgr->GetCreatureAI(creature)') < selection.index('return SelectFactory<CreatureAI>(creature)->Create(creature)')
    # Temporary guardian construction/control/lifetime and primary-pet ownership
    # are intentionally untouched; live attribution is required for landed bolts.
    assert not any(call in source for call in ('SetMinion(', 'DespawnOrUnsummon(', 'InitStatsForLevel(', 'SummonCreature('))
