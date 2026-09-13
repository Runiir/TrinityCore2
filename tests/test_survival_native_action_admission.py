"""Loaded8146 Survival rows through the production count and range consumer."""
import json
import sqlite3
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'tests/fixtures/survival_8146_native_admission.json'
SQL = ROOT/'sql/custom/world/2026_09_13_00_survival_native_action_admission.sql'
SHOTS = {75,1978,2643,3044,3674,53301,77767,53351}
CORE = {53301,3674,3044}


def database():
    data=json.loads(FIXTURE.read_text())
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    for table,rows in [('bot_rotation_profile',data['profiles']),('bot_rotation_action',data['actions'])]:
        row=rows[0]
        db.execute('CREATE TABLE '+table+' ('+','.join(f'`{key}` '+('TEXT' if isinstance(value,str) else 'REAL' if isinstance(value,float) else 'INTEGER') for key,value in row.items())+')')
        db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in row)+')',[tuple(row.values()) for row in rows])
    # Wrong spec, role, class, disabled profile; disabled duplicate action is
    # still migrated just like its enabled counterpart in the MM precedent.
    for index,(field,value) in enumerate([('spec_tag','marksmanship'),('role','tank'),('class_id',8),('enabled',0)],1):
        profile=dict(data['profiles'][0]);profile['id']+=index;profile[field]=value
        db.execute('INSERT INTO bot_rotation_profile VALUES ('+','.join('?' for _ in profile)+')',tuple(profile.values()))
        for original in data['actions']:
            row=dict(original);row['id']+=index*10000;row['profile_id']=profile['id']
            db.execute('INSERT INTO bot_rotation_action VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
    duplicate=dict(data['actions'][4]);duplicate['id']=99999;duplicate['enabled']=0
    db.execute('INSERT INTO bot_rotation_action VALUES ('+','.join('?' for _ in duplicate)+')',tuple(duplicate.values()))
    return db,data


def rows(db,table):
    return [dict(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY id')]


def test_exact_scope_and_idempotence():
    db,_=database();before=rows(db,'bot_rotation_action');profiles=rows(db,'bot_rotation_profile')
    db.executescript(SQL.read_text());after=rows(db,'bot_rotation_action')
    for a,b in zip(before,after):
        expected=dict(a)
        if a['profile_id']==274:
            if a['spell_id'] in SHOTS:expected['max_range']=45 if a['spell_id']==53351 else 40
            if a['spell_id'] in CORE:expected['max_enemies']=0
        assert b==expected
    expected_profiles=[dict(p, max_range=40) if p['id']==274 else p for p in profiles]
    assert rows(db,'bot_rotation_profile')==expected_profiles
    # MySQL FLOAT stores these integer setters exactly (no percentage/decimal
    # equality guard can drift between replay applications).
    for row in after:
        assert struct.unpack('<f',struct.pack('<f',row['max_range']))[0] == row['max_range']
    db.executescript(SQL.read_text())
    assert rows(db,'bot_rotation_action')==after
    assert rows(db,'bot_rotation_profile')==expected_profiles


def test_loaded_rows_through_production_count_and_native_range(tmp_path):
    db,data=database();before=[a for a in rows(db,'bot_rotation_action') if a['profile_id']==274]
    db.executescript(SQL.read_text());after=[a for a in rows(db,'bot_rotation_action') if a['profile_id']==274]
    source=(ROOT/'src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp').read_text()
    native=source[source.index('    auto effectiveSpellMaxRange ='):source.index('    auto effectiveSpellMaxRange =')+source[source.index('    auto effectiveSpellMaxRange ='):].index('\n    };')+7]
    count=source[source.index('        if (candidate.Profile.MinEnemies > hostileCount)'):source.index('        if (bot->getClass() == CLASS_DRUID')]
    maximum=source[source.index('        if (maxRange > 0.0f && distance > maxRange)'):source.index('        if (deferLavaBurstMovementRejection)')]
    ranges={r['spell_id']:r['maximum'] for r in data['native_ranges']}
    cases=[]
    for old,new in zip(before,after):
        if old['spell_id'] not in SHOTS:continue
        count_value=3
        native_max=ranges[old['spell_id']]
        cases.append(f'check({old["min_enemies"]},{old["max_enemies"]},{old["max_range"]}f,{native_max}f,38.4835f,{count_value},false);')
        cases.append(f'check({new["min_enemies"]},{new["max_enemies"]},{new["max_range"]}f,{native_max}f,38.4835f,{count_value},true);')
    cpp=r'''
#include <algorithm>
#include <cassert>
#include <string>
constexpr unsigned SPELL_RANGE_MELEE=1;
struct Range {unsigned Flags=2;};
struct SpellInfo {Range range;Range* RangeEntry=&range;float maximum=40;};
struct SpellMgr {SpellInfo info;SpellInfo const* GetSpellInfo(int){return &info;}} mgr;
auto* sSpellMgr=&mgr;
struct Actor {float GetSpellMaxRangeForTarget(Actor*,SpellInfo const* info){return info->maximum;}
 float GetMeleeRange(Actor*){return 5;} float GetCombatReach(){return 1.5f;}};
struct Profile {unsigned MinEnemies=1,MaxEnemies=0;float MaxRange=40;};
struct BotActionCandidate {struct Profile Profile;int ResolvedSpellId=77767;std::string RejectReason;};
void check(unsigned minimum,unsigned maximum,float cap,float nativeMax,float distance,unsigned hostileCount,bool admitted){
 Actor actor,unit;auto* bot=&actor;auto* target=&unit;
 mgr.info.maximum=nativeMax;
 BotActionCandidate candidate;candidate.Profile={minimum,maximum,cap};
''' + native + r'''
 for(int once=0;once<1;++once){
''' + count + r'''
 float maxRange=effectiveSpellMaxRange(candidate,cap);
''' + maximum + r'''
 }
 assert(candidate.RejectReason.empty()==admitted);
}
int main(){
'''+'\n'.join(cases)+r'''
 check(1,0,40,40,40,3,true);check(1,0,40,40,40.001f,3,false);
 check(1,0,45,45,45,3,true);check(1,0,45,45,45.001f,3,false);
 check(1,0,40,30,38.4835f,3,false); // Native upper range still clamps configured cap.
 check(2,0,40,40,38.4835f,1,false); // Existing Multi-Shot minimum enemy gate survives.
}
'''
    path=tmp_path/'admission.cpp';path.write_text(cpp);binary=path.with_suffix('')
    subprocess.run(['c++','-std=c++17',str(path),'-o',str(binary)],check=True,capture_output=True,text=True)
    subprocess.run([str(binary)],check=True)
