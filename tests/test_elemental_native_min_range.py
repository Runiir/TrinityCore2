from pathlib import Path
import sqlite3
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SQL=ROOT/'sql/custom/world/2026_09_12_01_elemental_native_min_range.sql'
ROLLBACK=ROOT/'sql/custom/rollback/world/2026_09_12_01_elemental_native_min_range_rollback.sql'


def migrated_rows():
    db=sqlite3.connect(':memory:')
    db.create_function('CONCAT',-1,lambda *s: ''.join(s))
    db.executescript('''
    CREATE TABLE bot_rotation_profile(id INTEGER,class_id INTEGER,spec_tag TEXT,role TEXT,enabled INTEGER);
    INSERT INTO bot_rotation_profile VALUES
    (1,7,'elemental_shaman','dps',1),(2,7,'elemental_shaman','dps',0),
    (3,8,'elemental_shaman','dps',1),(4,7,'enhancement','dps',1),(5,7,'elemental_shaman','healer',1);
    CREATE TABLE bot_rotation_action(id INTEGER,profile_id INTEGER,spell_id INTEGER,enabled INTEGER,
    min_range REAL,max_range REAL,mechanic_tags TEXT);
    ''')
    for i,spell in enumerate([8050,421,403,8042,51505,2894,57994,79206],1):
        db.execute('INSERT INTO bot_rotation_action VALUES(?,1,?,1,12,35,\'original\')',(i,spell))
    for i,profile in enumerate([2,3,4,5],20):
        db.execute('INSERT INTO bot_rotation_action VALUES(?,?,403,1,12,35,\'original\')',(i,profile))
    db.executescript("INSERT INTO bot_rotation_action VALUES(30,1,403,0,12,35,'original'),(31,1,403,1,8,35,'original'),(32,1,403,1,0,35,'original');")
    before=db.execute('SELECT * FROM bot_rotation_action ORDER BY id').fetchall()
    db.executescript(SQL.read_text());after=db.execute('SELECT * FROM bot_rotation_action ORDER BY id').fetchall()
    assert sum(a!=b for a,b in zip(before,after))==5
    for a,b in zip(before,after):
        if a[0]<=5:
            assert b==(*a[:4],0,a[5],a[6]+',native_min_range_20260912')
        else: assert a==b
    db.executescript(SQL.read_text())
    assert db.execute('SELECT * FROM bot_rotation_action ORDER BY id').fetchall()==after
    db.executescript(ROLLBACK.read_text())
    assert db.execute('SELECT * FROM bot_rotation_action ORDER BY id').fetchall()==before
    return after[:5]


def test_exact_sql_scope_idempotence_and_rollback():
    migrated_rows()


def test_production_resolver_range_gate_uses_migrated_rows(tmp_path):
    rows=migrated_rows()
    source=(ROOT/'src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp').read_text()
    native=source[source.index('    auto effectiveSpellMinRange ='):source.index('    auto effectiveSpellMaxRange =')]
    gate=source[source.index('        float distance = selfCenteredHostileAction'):source.index('        if (deferLavaBurstMovementRejection)')]
    cpp=r'''
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>
constexpr int SPELL_RANGE_RANGED=1;
struct Range { int Flags=0; };
struct SpellInfo { Range range; Range* RangeEntry=&range; float GetMaxRange(bool) const { return 30; } };
struct SpellMgr { SpellInfo info; SpellInfo const* GetSpellInfo(int) { return &info; } } store;
auto* sSpellMgr=&store;
struct Actor {
 float distance=8.03f, nativeMin=0;
 float GetSpellMinRangeForTarget(Actor*,SpellInfo const*) { return nativeMin; }
 float GetMeleeRange(Actor*) { return 5; }
 float GetExactDist(Actor*) { return distance; }
 bool IsWithinMeleeRange(Actor*) { return distance<=5; }
};
struct Profile { float MinRange=0, MaxRange=35; bool RequiresMeleeRange=false,RequiresRangedRange=false; };
struct BotActionCandidate { struct Profile Profile; int ResolvedSpellId=0; std::string RejectReason; };
std::string check(float configuredMin,float distance,float nativeMin=0,bool requiresRanged=false) {
 Actor actor; actor.distance=distance;actor.nativeMin=nativeMin;
 Actor* bot=&actor;Actor* target=&actor;Actor* actionTarget=target;
 Profile profile,action;std::vector<BotActionCandidate> candidates(1);
 candidates[0].Profile.MinRange=configuredMin;
 candidates[0].Profile.RequiresRangedRange=requiresRanged;
 bool selfCenteredHostileAction=false,selfTarget=false;
'''+native+r'''
 auto effectiveSpellMaxRange=[](BotActionCandidate const&,float configured) { return std::min(configured,30.0f); };
 for(auto& candidate:candidates) {
'''+gate+r'''
 }
 return candidates[0].RejectReason;
}
int main() {
 assert(check(12,8.03f)=="min_range_required");
'''+''.join(f' assert(check({r[4]},8.03f).empty());\n' for r in rows)+r'''
 assert(check(0,31)=="max_range_exceeded");
 assert(check(0,4).empty()); // These five rows have no configured ranged-only floor.
 assert(check(0,4,0,true)=="ranged_range_required");
 assert(check(0,8,10)=="min_range_required"); // A real native minimum still wins.
}
'''
    path=tmp_path/'range.cpp';path.write_text(cpp)
    binary=tmp_path/'range'
    subprocess.run(['g++','-std=c++17',str(path),'-o',str(binary)],check=True,capture_output=True,text=True)
    subprocess.run([str(binary)],check=True)
