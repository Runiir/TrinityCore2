"""Doomguard admission/provisioning only; native guardian behavior requires live proof."""
import json
import sqlite3
import subprocess
from pathlib import Path

from tests.test_survival_remote_trap_admission import loader_rows
from tools.bot_ml.build_validation_provisioning import bot_known_spell_ids, build_character_insert_sql, load_config
from tools.bot_ml.build_all_spec_phase1_catalogs import QUALIFICATION_TUNED_ACTION_SPELL_IDS, action_spell_ids

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/affliction_doomguard_native.json'
SQL=ROOT/'sql/custom/world/2026_09_13_02_affliction_doomguard.sql'


def database():
    data=json.loads(FIXTURE.read_text());db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.create_function('GREATEST',-1,max)
    for table,fields in data['schema'].items():
        definitions=[]
        for f in fields:
            kind='TEXT' if any(t in f['Type'] for t in ('char','text','enum')) else 'REAL' if any(t in f['Type'] for t in ('float','double','decimal')) else 'INTEGER'
            definition=f"`{f['Field']}` {kind}"
            if f['Field']=='id':definition+=' PRIMARY KEY'
            elif f['Default'] is not None:definition+=' DEFAULT '+("'"+str(f['Default']).replace("'","''")+"'" if kind=='TEXT' else str(f['Default']))
            definitions.append(definition)
        db.execute('CREATE TABLE '+table+'('+','.join(definitions)+')')
    for index,changes in enumerate([{}, {'spec_tag':'demonology_warlock'}, {'role':'tank'}, {'class_id':8}, {'enabled':0}]):
        p=dict(data['profile']);p.update(changes);p['id']+=index
        db.execute('INSERT INTO bot_rotation_profile VALUES('+','.join('?' for _ in p)+')',tuple(p.values()))
    db.execute("INSERT INTO bot_rotation_action(profile_id,sort_order,spell_id,category,target_selector,min_range,max_range,max_enemies,requires_ranged_range) VALUES(273,5,18540,'offensive_cooldown','enemy',5,18,1,1)")
    return db


def test_convergent_sql_preserves_identity_and_other_profiles():
    db=database();original=[tuple(r) for r in db.execute('SELECT * FROM bot_rotation_profile ORDER BY id')]
    assert not [r for r in loader_rows(db) if r[0]==272]
    db.executescript(SQL.read_text());rows=[dict(r) for r in db.execute('SELECT * FROM bot_rotation_action WHERE profile_id=272')]
    assert len(rows)==1;row=rows[0]
    assert (row['spell_id'],row['target_selector'],row['min_range'],row['max_range'],row['min_enemies'],row['max_enemies'],row['requires_ranged_range'],row['priority_bucket'])==(18540,'self',0,0,1,0,0,0)
    assert {'guardian','summon_doomguard'}.issubset(row['mechanic_tags'].split(','))
    all_rows=[tuple(r) for r in db.execute('SELECT * FROM bot_rotation_action ORDER BY id')]
    db.executescript(SQL.read_text());assert [tuple(r) for r in db.execute('SELECT * FROM bot_rotation_action ORDER BY id')]==all_rows
    for before,after in zip(original,db.execute('SELECT * FROM bot_rotation_profile ORDER BY id')):
        if after['id']!=272:assert tuple(after)==before
    profile=dict(db.execute('SELECT * FROM bot_rotation_profile WHERE id=272').fetchone())
    expected=json.loads(FIXTURE.read_text())['profile'];expected['version']=max(expected['version'],6);assert profile==expected
    # Repair a stale typed row without delete/reinsert or changing its id.
    db.execute("UPDATE bot_rotation_action SET target_selector='enemy',min_range=5,max_range=18,max_enemies=1,requires_ranged_range=1,enabled=0 WHERE profile_id=272")
    db.executescript(SQL.read_text());assert dict(db.execute('SELECT * FROM bot_rotation_action WHERE profile_id=272').fetchone())==row


def test_native_recorded_chain_and_catalog_provisioning(tmp_path):
    data=json.loads(FIXTURE.read_text());n=data['native'];spells={r[0]:r for r in n['Spell']['rows']};doom=spells[18540];summon=spells[60478]
    assert (doom[12],doom[15],doom[37],doom[43],doom[46])==(1,1,1175,0,0)
    assert n['SpellRange']['rows'][0][1:5]==[0,0,0,0]
    assert n['SpellCastTimes']['rows'][0][1]==0
    assert n['SpellCooldowns']['rows'][0][1]==600000
    effects={r[24]:r for r in n['SpellEffect']['rows']}
    assert (effects[18540][1],effects[18540][21],effects[18540][22])==(64,60478,47)
    assert (effects[60478][1],effects[60478][12],effects[60478][13],summon[13])==(28,11859,61,22)
    assert n['SpellDuration']['rows'][0][1]==45000
    assert n['Spell']['sha256']=='088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f'
    catalog=json.loads((ROOT/'experiments/configs/all_spec_targets_cata_p4_v1.json').read_text())
    row=next(r for r in catalog['targets'] if r['spec_target_id']=='affliction_warlock');bot=row['provisioning_bot']
    profiles=json.loads((ROOT/'experiments/configs/cata_434_action_profiles.json').read_text())
    assert 18540 in QUALIFICATION_TUNED_ACTION_SPELL_IDS['affliction_warlock']
    assert 18540 in action_spell_ids('affliction_warlock',9,row['talent_build'])
    assert row['action_profile_spell_ids']==profiles['action_profile_spells_by_spec']['affliction_warlock']
    assert 18540 in bot_known_spell_ids(bot,profiles)
    old=json.loads(json.dumps(profiles));old['action_profile_spells_by_spec']['affliction_warlock'].remove(18540)
    assert 18540 not in bot_known_spell_ids(bot,old)
    config=load_config(ROOT/'experiments/configs/validation_provisioning_cata_001.json')
    scenario=next(s for s in config['scenarios'] if s['id']=='all_spec_candidate_pool');scenario['bots']=[bot];config['scenarios']=[scenario]
    sql=build_character_insert_sql(config,profiles,dbc_dir=tmp_path)
    assert 'SELECT c.`guid`, 18540, 1, 0 FROM `characters`.`characters`' in sql
    assert 'SELECT c.`guid`, 18540, 1, 0 FROM `characters`.`characters`' not in build_character_insert_sql(config,old,dbc_dir=tmp_path)


def test_production_admission_self_resolution_reservations_and_submission(tmp_path):
    db=database();db.executescript(SQL.read_text())
    loaded=[r for r in loader_rows(db) if r[0]==272];assert len(loaded)==1
    row=dict(db.execute('SELECT * FROM bot_rotation_action WHERE profile_id=272').fetchone())
    bots=ROOT/'src/server/game/Bots'
    candidate=(bots/'BotClassSpecActionProfileCandidates.cpp').read_text()
    unknown=candidate[candidate.index('        else if (spell.SpellId && !spellInfo)'):candidate.index('        else if (spell.Category == BotCombatActionCategory::UseItem')]
    resolver=(bots/'BotWorldPopulationMgrCombatResolver.cpp').read_text()
    count=resolver[resolver.index('        if (candidate.Profile.MinEnemies > hostileCount)'):resolver.index('        if (bot->getClass() == CLASS_DRUID')]
    reservation=resolver[resolver.index('        if (candidate.RejectReason.empty())\n            if (char const* reservationReason'):resolver.index('        if (areaOnly && candidate.Category')]
    combat_spell=(bots/'BotWorldPopulationMgrCombatSpell.cpp').read_text()
    second=combat_spell[combat_spell.index('        if (char const* reservationReason'):combat_spell.index('        if (candidate.Category == BotCombatActionCategory::Taunt')]
    selected=resolver[resolver.rindex('    action.Valid = true;'):resolver.index('    return action;',resolver.rindex('    action.Valid = true;'))]
    executor=(bots/'BotActionExecutor.cpp').read_text()
    target_gate=executor[executor.index('    if (!target || !target->IsAlive() || (target != bot'):executor.index('    // White swings, Auto Shot')]
    submission=executor[executor.index('    SpellCastResult result = spellInfo && (spellInfo->GetExplicitTargetMask()'):executor.index('    _lastSpellCastResult =',executor.index('    SpellCastResult result = spellInfo && (spellInfo->GetExplicitTargetMask()'))]
    range_start=executor.index('    if (!target)', executor.index('BotActionResult BotActionExecutor::CheckHostileSpell'))
    native_range=executor[range_start:executor.index('    // Rerun157 captured',range_start)]
    cpp=r'''
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include "Bots/BotWorldPopulationMgrCombatRange.h"
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>
using uint32=unsigned;
struct Guid {int Value=0;bool IsEmpty()const{return !Value;}bool operator==(Guid b)const{return Value==b.Value;}};
struct Position {float X,Y,Z;};
constexpr unsigned TARGET_FLAG_DEST_LOCATION=1,SPELL_RANGE_MELEE=1,SPELL_RANGE_RANGED=2;
struct NativeRange {unsigned Flags=0;};
using SpellCastResult=int;constexpr int SPELL_CAST_OK=0;
struct CastSpellExtraArgs {explicit CastSpellExtraArgs(int){}};
struct SpellInfo {NativeRange range;NativeRange* RangeEntry=&range;unsigned Id=18540;bool IsPositive()const{return true;}unsigned GetExplicitTargetMask()const{return 0;}float GetMaxRange(bool)const{return 0;}};
struct Unit {Guid Id;bool Alive=true,Known=true;float Distance=40;
 Guid GetGUID()const{return Id;}bool IsAlive()const{return Alive;}bool HasSpell(unsigned)const{return Known;}
 bool IsValidAttackTarget(Unit const* other,SpellInfo const* =nullptr)const{return other!=this;}
 bool IsWithinLOSInMap(Unit const*)const{return true;}
 float GetExactDist(Unit const* other)const{return other==this?0:other->Distance;}
 bool IsWithinDistInMap(Unit const* other,float range)const{return GetExactDist(other)<=range;}
 float GetSpellMinRangeForTarget(Unit const*,SpellInfo const*)const{return 0;}
 float GetSpellMaxRangeForTarget(Unit const*,SpellInfo const*)const{return 0;}
 float GetCombatReach()const{return 1.5f;}
 float GetMeleeRange(Unit const*)const{return 5;}float GetPositionX()const{return 1;}float GetPositionY()const{return 2;}float GetPositionZ()const{return 3;}
 Unit* CastTarget=nullptr;unsigned CastId=0;
 SpellCastResult CastSpell(Unit* target,unsigned id,CastSpellExtraArgs){CastTarget=target;CastId=id;return SPELL_CAST_OK;}
 SpellCastResult CastSpell(Position,unsigned,CastSpellExtraArgs){assert(false);return 1;}
};
void Face(Unit*,Unit*){assert(false);}
enum class BotActionResult {InvalidTarget,DeadTarget,NoLineOfSight,OutOfRange,Ok};
struct Profile {unsigned SpellId=18540;BotCombatActionCategory Category=BotCombatActionCategory::OffensiveCooldown;
 unsigned MinEnemies=MINIMUM,MaxEnemies=MAXIMUM;float MinRange=MINRANGE,MaxRange=MAXRANGE;
 std::string TargetSelector="SELECTOR",MechanicTags="TAGS",MovementDirective="ranged",AutoAttackMode="none";};
struct Candidate {struct Profile Profile;BotCombatActionCategory Category=BotCombatActionCategory::OffensiveCooldown;unsigned SpellId=18540,ResolvedSpellId=18540;bool InterruptCurrentChanneledSpell=false;std::string RejectReason;};
struct Action {bool Valid=false,InterruptCurrentChanneledSpell=false,SuppressAreaDamage=false;unsigned SpellId=0;Guid TargetGuid;float MinRange=35,MaxRange=35;std::string Type,DebugName,MovementDirective,AutoAttackMode;};
struct SpellMgr {SpellInfo info;SpellInfo const* GetSpellInfo(unsigned){return &info;}} mgr;
auto* sSpellMgr=&mgr;
char const* BotCombatActionCatalog::ToString(BotCombatActionCategory){return "offensive_cooldown";}
BotActionResult NativeRangeCheck(Unit* bot,Unit* target,SpellInfo const* spellInfo){
''' + native_range + r'''
 return BotActionResult::Ok;
}
BotActionResult Submit(Unit* bot,Unit* target,Action const& action){
''' + target_gate + r'''
 auto* spellInfo=sSpellMgr->GetSpellInfo(action.SpellId);assert(NativeRangeCheck(bot,target,spellInfo)==BotActionResult::Ok);CastSpellExtraArgs castArgs(0);
''' + submission + r'''
 assert(result==SPELL_CAST_OK);return BotActionResult::Ok;
}
void Replay(unsigned hostileCount,float hostileDistance,bool known,bool inCombat,bool secondConsumer){
 Unit caster,victim;caster.Id={30008};victim.Id={39};caster.Known=known;victim.Distance=hostileDistance;
 auto* bot=&caster;auto* target=&victim;Profile profile,spell;auto* spellInfo=sSpellMgr->GetSpellInfo(18540);
 Candidate candidate;
 if(false){}
''' + unknown + r'''
 BotRaidCooldownReservation::RouteContext cooldownRoute;
 cooldownRoute.ValidationRouteEnabled=true;cooldownRoute.RaidInstance=true;
 cooldownRoute.RouteKind="boss";cooldownRoute.NodeKind="boss";
 cooldownRoute.EncounterInProgress=inCombat;cooldownRoute.EncounterPhase=inCombat?"combat":"formation";
 for(int once=0;once<1;++once){
 if(!candidate.RejectReason.empty())break;
 if(secondConsumer){
''' + second + r'''
 }else{
''' + reservation + r'''
 }
''' + count + r'''
 }
 if(!known){assert(candidate.RejectReason=="unknown_requested_spell");return;}
 if(!inCombat){assert(candidate.RejectReason=="raid_offensive_guardian_reserved");return;}
 assert(candidate.RejectReason.empty());
 Candidate const* best=&candidate;Action action;bool forbidArea=false;
 auto effectiveSpellMinRange=[](Candidate const&,float v){return v;};
 auto effectiveSpellMaxRange=[](Candidate const&,float v){return v;};
''' + selected + r'''
 assert(action.Valid&&action.SpellId==18540&&action.TargetGuid==bot->GetGUID());
 assert(action.MinRange==0&&action.MaxRange==0);
 // Use the executor's native-target validation and exact CastSpell expression.
 Unit* resolvedTarget=action.TargetGuid==bot->GetGUID()?bot:target;
 assert(Submit(bot,resolvedTarget,action)==BotActionResult::Ok);
 assert(bot->CastTarget==bot&&bot->CastId==18540);
}
int main(){for(unsigned count:{1u,3u})for(float distance:{4.f,20.f,40.f})for(bool second:{false,true}){
 Replay(count,distance,false,true,second);Replay(count,distance,true,false,second);Replay(count,distance,true,true,second);
}}
'''
    for key,value in {'MINIMUM':row['min_enemies'],'MAXIMUM':row['max_enemies'],'MINRANGE':row['min_range'],'MAXRANGE':row['max_range'],'SELECTOR':row['target_selector'],'TAGS':row['mechanic_tags']}.items():cpp=cpp.replace(key,str(value))
    path=tmp_path/'doomguard.cpp';path.write_text(cpp);binary=path.with_suffix('')
    subprocess.run(['c++','-std=c++17','-I',str(ROOT/'src/server/game'),'-I',str(ROOT/'src/server/shared'),'-I',str(ROOT/'src/common'),str(path),'-o',str(binary)],check=True,capture_output=True,text=True)
    subprocess.run([str(binary)],check=True)
