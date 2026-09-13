"""Missing Fire/Survival potion branches; remaining-time OR is intentionally absent."""
from pathlib import Path
import sqlite3
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
BOTS=ROOT/'src/server/game/Bots'
SQL=ROOT/'sql/custom/world/2026_09_13_05_fire_survival_combat_potions.sql'


def test_missing_rows_insert_idempotently_without_touching_other_profiles():
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE bot_rotation_profile(id,class_id,spec_tag,role,enabled)')
    db.execute('''CREATE TABLE bot_rotation_action(profile_id,sort_order,spell_id,category,mechanic_tags,
        damage_weight,survival_weight,priority_bucket,min_enemies,max_enemies,target_selector,
        movement_directive,auto_attack_mode,min_range,max_range,max_hostile_target_health_pct,enabled)''')
    profiles=[(1,8,'fire','dps',1),(2,8,'fire','dps',1),(3,3,'survival','dps',1),
        (4,8,'fire','dps',0),(5,3,'survival','dps',0),(6,3,'marksmanship','dps',1),
        (7,8,'frost','dps',1),(8,8,'fire','healer',1),(9,9,'affliction_warlock','dps',1)]
    db.executemany('INSERT INTO bot_rotation_profile VALUES(?,?,?,?,?)',profiles)
    existing=(9,75,79476,'use_item','existing',1.1,0,7,1,0,'self','ranged','none',0,0,.25,1)
    db.execute('INSERT INTO bot_rotation_action VALUES('+','.join('?'*17)+')',existing)
    assert db.execute('SELECT COUNT(*) FROM bot_rotation_action WHERE profile_id<4').fetchone()[0]==0
    db.executescript(SQL.read_text()); before=db.execute('SELECT * FROM bot_rotation_action ORDER BY profile_id').fetchall()
    db.executescript(SQL.read_text()); assert db.execute('SELECT * FROM bot_rotation_action ORDER BY profile_id').fetchall()==before
    assert [r[0] for r in before]==[1,2,3,9]
    assert before[-1]==existing
    assert before[0][2:]==before[1][2:]
    for r in before[:3]:
        assert r[3]=='use_item' and r[10:15]==('self','hold','none',0,0)
        assert r[7]==0 and r[8:10]==(1,0)
    assert before[0][2]==79476 and 'combustion_ready' in before[0][4]
    assert before[2][2]==79633 and before[2][15]==.20
    assert 'partial' in before[2][4]
    assert db.execute('SELECT * FROM bot_rotation_profile').fetchall()==profiles


def test_actual_compiled_combustion_condition(tmp_path):
    source=(BOTS/'BotClassSpecActionProfileCandidates.cpp').read_text()
    start=source.index('std::string EvaluateCompiledConditions(')
    prefix=source[start:source.index('    Aura const* selfAura',start)]
    program=r'''
#include <cassert>
#include <string>
using uint32=unsigned;
struct Unit{};
struct SpellInfo{};
struct History{bool ready=true;bool IsReady(SpellInfo const*)const{return ready;}};
struct Player:Unit{bool known=true;History history;bool HasSpell(uint32 id)const{return known&&id==11129;}
 History const* GetSpellHistory()const{return &history;}};
struct Manager{SpellInfo info;bool present=true;SpellInfo const* GetSpellInfo(uint32 id)const{return present&&id==11129?&info:nullptr;}} manager;
auto sSpellMgr=&manager;
struct BotActionProfileSpell{std::string MechanicTags;};
bool HasMechanicTag(std::string const& tags,char const* tag){return tags==tag;}
'''+prefix+r'''
 return "";
}
int main(){Player fire1,fire2;BotActionProfileSpell potion{"combustion_ready"},ordinary{"filler"};
 for(auto* bot:{&fire1,&fire2}){
  assert(EvaluateCompiledConditions(bot,bot,nullptr,potion).empty());
  bot->history.ready=false;assert(EvaluateCompiledConditions(bot,bot,nullptr,potion)=="combustion_not_ready");
  assert(EvaluateCompiledConditions(bot,bot,nullptr,ordinary).empty());
  bot->history.ready=true;bot->known=false;assert(EvaluateCompiledConditions(bot,bot,nullptr,potion)=="combustion_not_ready");
  bot->known=true;manager.present=false;assert(EvaluateCompiledConditions(bot,bot,nullptr,potion)=="combustion_not_ready");manager.present=true;
 }
 assert(EvaluateCompiledConditions(nullptr,nullptr,nullptr,potion)=="missing_bot");
}
'''
    cpp=tmp_path/'ready.cpp';cpp.write_text(program);binary=tmp_path/'ready'
    subprocess.run(['g++','-std=c++17',str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)


def test_actual_comparator_potion_before_combat_with_native_safety_owners(tmp_path):
    resolver=(BOTS/'BotWorldPopulationMgrCombatResolver.cpp').read_text()
    start=resolver.index('    auto candidatePreferred =')
    comparator=resolver[start:resolver.index('\n    };',start)+7]
    execution=(BOTS/'BotWorldPopulationMgrCombatExecution.cpp').read_text()
    execution=execution[execution.index('BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState*'):]
    assert execution.index('TryEnsurePersistentCombatSetup') < execution.index('ResolveProfileCombatAction(')
    assert 'if (bestInterrupt)\n        best = bestInterrupt;' in resolver
    program=r'''
#include <cassert>
struct Profile{unsigned PriorityBucket,SortOrder;};
struct BotActionCandidate{::Profile Profile;float Score;unsigned ActionId;};
int main(){
'''+comparator+r'''
 BotActionCandidate potion{{0,24},.01f,1},combustion{{1,25},999.f,2},survivalShot{{1,20},999.f,3};
 assert(candidatePreferred(potion,&combustion));assert(candidatePreferred(potion,&survivalShot));
 assert(!candidatePreferred(combustion,&potion));
 // A same-bucket sort adjustment alone fails when another action scores higher.
 potion.Profile.PriorityBucket=1;assert(!candidatePreferred(potion,&combustion));
}
'''
    cpp=tmp_path/'priority.cpp';cpp.write_text(program);binary=tmp_path/'priority'
    subprocess.run(['g++','-std=c++17',str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
