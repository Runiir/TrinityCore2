"""DPS-047: use the real enabled-action SQL admission and native feedback consumer."""
import ast
import json
import re
import subprocess
from pathlib import Path

from tests.test_survival_native_action_admission import database, rows, SQL as SHOT_SQL

ROOT=Path(__file__).resolve().parents[1]
SQL=ROOT/'sql/custom/world/2026_09_13_01_survival_disable_remote_aoe_trap.sql'


def setup():
    db,data=database()
    db.executescript(SHOT_SQL.read_text())
    original=next(a for a in data['actions'] if a['id']==2149)
    # An exact semantic duplicate is also invalid; nearby distinct rows must
    # stay unchanged (including a sort40 row carrying the scored aura gate).
    for index,change in enumerate([{}, {'sort_order':41}, {'target_selector':'self'}, {'min_enemies':1}, {'required_self_aura':2825}],1):
        row=dict(original,id=88000+index,**change)
        db.execute('INSERT INTO bot_rotation_action VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
    return db


def loader_rows(db):
    source=(ROOT/'src/server/game/Bots/BotClassSpecActionProfileDb.cpp').read_text()
    start=source.index('    QueryResult result = WorldDatabase.Query(',source.index('LoadDbSnapshot('))
    block=source[start:source.index(');',start)]
    query=''.join(ast.literal_eval(token) for token in re.findall(r'"(?:[^"\\]|\\.)*"',block))
    # This is the actual production SELECT including p.enabled/a.enabled,
    # all81 projected fields and ordering, not a copied enabled predicate.
    return [tuple(row) for row in db.execute(query)]


def test_scoped_disable_and_real_loader_idempotence():
    db=setup();before=rows(db,'bot_rotation_action');profiles=rows(db,'bot_rotation_profile')
    loaded_before=loader_rows(db)
    assert any(r[0]==274 and r[11]==40 and r[12]==13813 and r[30]==0 for r in loaded_before)
    db.executescript(SQL.read_text());after=rows(db,'bot_rotation_action')
    for a,b in zip(before,after):
        expected=dict(a)
        if a['id'] in (2149,88001):expected['enabled']=0
        assert b==expected
    assert rows(db,'bot_rotation_profile')==profiles
    loaded=loader_rows(db)
    assert not any(r[0]==274 and r[11]==40 and r[12]==13813 and r[30]==0 and r[24]==2 and r[39]=='enemy' for r in loaded)
    assert any(r[0]==274 and r[11]==17 and r[12]==13813 and r[30]==2825 for r in loaded)
    assert any(r[0]==274 and r[12]==2643 and r[24]==2 and r[43]==40 for r in loaded)
    db.executescript(SQL.read_text())
    assert rows(db,'bot_rotation_action')==after
    assert loader_rows(db)==loaded


def test_loaded_remote_trap_cannot_reach_native_reconciliation_after_disable(tmp_path):
    db=setup()
    # Keep the real loaded roster, not semantic negative controls, for this
    # trace replay. Candidate spell rows originate in the production query.
    db.execute('DELETE FROM bot_rotation_action WHERE id>=88000')
    before=[r for r in loader_rows(db) if r[0]==274]
    db.executescript(SQL.read_text())
    after=[r for r in loader_rows(db) if r[0]==274]
    resolver=(ROOT/'src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp').read_text()
    count=resolver[resolver.index('        if (candidate.Profile.MinEnemies > hostileCount)'):resolver.index('        if (bot->getClass() == CLASS_DRUID')]
    aura=resolver[resolver.index('        if (candidate.Profile.RequiredSelfAura &&'):resolver.index('        if (candidate.Profile.RequiredSelfAuraStacks)')]
    execution=(ROOT/'src/server/game/Bots/BotWorldPopulationMgrCombatExecution.cpp').read_text()
    start=execution.index('    if (state && target\n        && (result == BotActionResult::OutOfRange')
    feedback=execution[start:execution.index('    if (state && result == BotActionResult::Ok)',start)]
    def materialize(values):
        return ','.join('{%d,%d,%d,%d}'%(r[12],r[24],r[25],r[30]) for r in values)
    cpp=r'''
#include <cassert>
#include <string>
#include <vector>
using uint64=unsigned long long;
struct Guid {int GetCounter(){return 39;}};
struct Action {Guid TargetGuid;};
enum class BotActionResult {OutOfRange,NoLineOfSight,Casting,Ok};
namespace BotActionArbitration {struct Outcome {static int Started(char const*){return 1;}};}
struct Kernel {void Observe(std::string,int,uint64,int,int,int){}};
struct State {Kernel DecisionKernel;std::string LastRecoveryMode,LastRecoveryResult,LastNoProgressReason;};
struct Bot {bool HasAura(int){return false;}};
int reconciliations=0;
bool MoveBotToProfileRange(State&,Bot*,Bot*,Action*,bool=false){++reconciliations;return true;}
void RecordCombatAttempt(State&,Bot*,Bot*,char const*,Action*,BotActionResult,char const*){}
void TryResolveBotBlocker(State&,Bot*,char const*){}
BotActionResult NativeFeedback(){
 State storage;auto* state=&storage;Bot actor,victim;auto* bot=&actor;auto* target=&victim;
 Action action;auto result=BotActionResult::OutOfRange;uint64 nowMs=1789302236962ULL;
''' + feedback + r'''
 return result;
}
struct Profile {unsigned MinEnemies,MaxEnemies,RequiredSelfAura;};
struct Candidate {struct Profile Profile;std::string RejectReason;};
struct Row {int Spell;unsigned Minimum,Maximum,Aura;};
void replay(std::vector<Row> const& loaded,bool trapExpected){
 Bot actor;auto* bot=&actor;unsigned hostileCount=2;bool trap=false,multi=false;
 for(auto const& row:loaded){
 Candidate candidate{{row.Minimum,row.Maximum,row.Aura},{}};
''' + count + aura + r'''
 if(row.Spell==13813){trap=true;assert(NativeFeedback()==BotActionResult::Casting);}
 if(row.Spell==2643)multi=true;
 }
 assert(trap==trapExpected);assert(multi);
}
int main(){replay({BEFORE},true);assert(reconciliations==1);reconciliations=0;
 replay({AFTER},false);assert(reconciliations==0);}
'''.replace('BEFORE',materialize(before)).replace('AFTER',materialize(after))
    path=tmp_path/'remote_trap.cpp';path.write_text(cpp);binary=path.with_suffix('')
    subprocess.run(['c++','-std=c++17',str(path),'-o',str(binary)],check=True,capture_output=True,text=True)
    subprocess.run([str(binary)],check=True)
