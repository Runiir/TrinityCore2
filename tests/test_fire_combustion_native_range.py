"""DPS-052 SQL rows through the actual resolver envelope and retained dot gate."""
import json
from pathlib import Path
import struct
import subprocess

from test_fire_native_range import _connection, _action_rows

ROOT=Path(__file__).resolve().parents[1]
SQL=ROOT/'sql/custom/world/2026_09_13_04_fire_combustion_native_range.sql'


def database():
    db=_connection()
    # A second enabled Fire profile models independent profile consumers;
    # actor GUIDs do not participate in SQL or native range admission.
    db.execute("INSERT INTO bot_rotation_profile VALUES(5,8,'fire','dps',0,35,1,9,'ranged')")
    db.execute("INSERT INTO bot_rotation_profile VALUES(6,8,'frost','dps',0,35,1,9,'ranged')")
    db.executescript((ROOT/'sql/custom/world/2026_09_08_01_fire_native_range.sql').read_text())
    for profile in range(1,7):
        for offset,cap,enabled in [(0,35,1),(1,35,0),(2,40,1),(3,30,1)]:
            db.execute("INSERT INTO bot_rotation_action VALUES(?,?,?,?,?,?,?,?,?,?,?)",(profile*100+offset,profile,7,11129,'cooldown',1,1,'enemy',0,cap,enabled))
    return db


def test_exact_all_profile_scope_and_mysql_float_idempotence():
    db=database();before=_action_rows(db)
    profiles=db.execute('SELECT * FROM bot_rotation_profile ORDER BY id').fetchall()
    db.executescript(SQL.read_text());after=_action_rows(db)
    changed=[]
    for old,new in zip(before,after):
        expected=list(old)
        if old[1] in (1,5) and old[3]==11129 and old[9]==35:
            expected[9]=40;changed.append(old[0])
        assert tuple(expected)==new
        assert struct.unpack('<f',struct.pack('<f',new[9]))[0]==new[9]
    assert changed==[100,101,500,501]
    assert db.execute('SELECT * FROM bot_rotation_profile ORDER BY id').fetchall()==profiles
    count=db.total_changes;db.executescript(SQL.read_text())
    assert db.total_changes==count and _action_rows(db)==after


def test_migrated_rows_through_actual_resolver_native_envelope_and_dot_gate(tmp_path):
    db=database();before=_action_rows(db);db.executescript(SQL.read_text());after=_action_rows(db)
    source=(ROOT/'src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp').read_text()
    start=source.index('    auto effectiveSpellMaxRange =')
    native=source[start:source.index('\n    };',start)+7]
    start=source.index('        float maxRange = candidate.Profile.MaxRange')
    configured=source[start:source.index('        if (candidate.Profile.RequiresMeleeRange',start)]
    start=source.index('        if (maxRange > 0.0f && distance > maxRange)')
    maximum=source[start:source.index('        if (deferLavaBurstMovementRejection)',start)]
    start=source.index('        if (bot->getClass() == CLASS_MAGE && candidate.SpellId == 11129)')
    dots=source[start:source.index('        if (candidate.Profile.RequiresInterruptibleTarget',start)]
    authority=json.loads((ROOT/'tests/fixtures/fire_combustion_native_contract.json').read_text())
    assert authority['combustion']['range_index']==5 and authority['combustion']['native_max_range']==40
    cases=[]
    for old,new in zip(before,after):
        if old[1] not in (1,5) or old[3]!=11129 or old[9]!=35:continue
        for guid in (30006,130006): # second is an explicit synthetic duplicate-profile actor
            cases.append(f'assert(check({guid},{old[9]}f,40,37.7469f,true)=="max_range_exceeded");')
            cases.append(f'assert(check({guid},{new[9]}f,40,37.7469f,true).empty());')
    cpp=r'''
#include <algorithm>
#include <cassert>
#include <string>
constexpr unsigned SPELL_RANGE_MELEE=1,CLASS_MAGE=8,EFFECT_0=0;
struct Range {unsigned Flags=0;};
struct SpellInfo {Range range;Range* RangeEntry=&range;float maximum=40;float GetMaxRange(bool)const{return maximum;}};
struct SpellMgr {SpellInfo info;SpellInfo const* GetSpellInfo(unsigned){return &info;}}mgr;
auto* sSpellMgr=&mgr;
struct AuraEffect {int GetAmount()const{return 12000;}};
struct Actor {unsigned guid=0;bool dots=true;AuraEffect ignite;
 unsigned getClass()const{return CLASS_MAGE;}unsigned GetGUID()const{return guid;}
 AuraEffect const* GetAuraEffect(unsigned id,unsigned index,unsigned owner)const{return dots&&id==12654&&index==0&&(owner==30006||owner==130006)?&ignite:nullptr;}
 bool HasAura(unsigned id,unsigned owner)const{return dots&&(id==44457||id==92315)&&(owner==30006||owner==130006);}
 float GetSpellMaxRangeForTarget(Actor*,SpellInfo const* info){return info->maximum;}
 float GetMeleeRange(Actor*)const{return 5;}float GetCombatReach()const{return 1.5f;}
};
struct Profile {float MaxRange=40;std::string TargetSelector="enemy";};
struct ResolvedCombatAction {float MinRange=0,MaxRange=0;bool RangeRecoveryRequired=false;};
struct BotActionCandidate {struct Profile Profile;unsigned SpellId=11129,ResolvedSpellId=11129;std::string RejectReason;};
std::string check(unsigned guid,float cap,float nativeMax,float distance,bool ownedDots,unsigned spellId=11129){
 Actor actor,targetUnit;actor.guid=guid;targetUnit.dots=ownedDots;auto* bot=&actor;auto* target=&targetUnit;
 mgr.info.maximum=nativeMax;Profile profile;BotActionCandidate candidate;candidate.Profile.MaxRange=cap;candidate.SpellId=candidate.ResolvedSpellId=spellId;
 // Fixture SQL rows are ordinary enemy actions with zero minimum range.
 bool selfTarget=false,densityOnly=false;float minRange=0;ResolvedCombatAction action;
''' + native + '\nfor(int once=0;once<1;++once){\n' + dots + configured + maximum + '\n}\nreturn candidate.RejectReason;\n}\nint main(){\n' + '\n'.join(cases)+r'''
 assert(check(30006,40,40,40,true).empty());
 assert(check(30006,40,40,40.01f,true)=="max_range_exceeded");
 assert(check(30006,40,30,33.01f,true)=="max_range_exceeded"); // native30 + two1.5yd combat reaches still wins
 assert(check(30006,50,40,43,true).empty());
 assert(check(30006,50,40,43.01f,true)=="max_range_exceeded");
 assert(check(30006,30,40,30.01f,true)=="max_range_exceeded"); // other explicit cap preserved
 assert(check(30006,40,40,37.7469f,false)=="combustion_dot_window_not_ready");
 assert(check(30006,40,40,37.7469f,true).empty());
 assert(check(30006,35,30,33,true,2136).empty());
 assert(check(30006,35,30,33.01f,true,2136)=="max_range_exceeded");
}
'''
    path=tmp_path/'range.cpp';path.write_text(cpp);binary=tmp_path/'range'
    result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(path),'-o',str(binary)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    subprocess.run([str(binary)],check=True)
