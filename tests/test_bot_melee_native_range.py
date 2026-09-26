"""Execute the production resolver's range admission and selected-action range."""
from pathlib import Path
import subprocess
import sqlite3
import re
from tests.combat_resolver_source import combat_resolver_source

ROOT = Path(__file__).resolve().parents[1]


def test_unset_melee_cap_uses_native_reach(tmp_path, rune_strike_caps=None):
    source = combat_resolver_source()
    start = source.index("    auto effectiveSpellMaxRange =")
    helper = source[start:source.index("\n    };", start) + 7]
    start = source.index("        float maxRange = candidate.Profile.MaxRange")
    admission = source[start:source.index("        float roleScore", start)]
    start = source.index("    if (!selfTarget && best->Profile.MaxRange <= 0.0f)")
    selected = source[start:source.index("    return action;", start)]
    unit_source = (ROOT / "src/server/game/Entities/Unit/Unit.cpp").read_text()
    start = unit_source.index("float Unit::GetMeleeRange(Unit const* target) const")
    native_melee_body = unit_source[unit_source.index("{", start):unit_source.index("\n}", start) + 2]
    program = r'''
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>
constexpr int SPELL_RANGE_MELEE=1;
constexpr float NOMINAL_MELEE_RANGE=5;
struct Range {int Flags=1;};
struct SpellInfo {Range* RangeEntry;float Raw=5;float GetMaxRange(bool)const{return Raw;}};
struct Unit {float GetCombatReach()const{return 10;}};
struct Player {float GetSpellMaxRangeForTarget(Unit*,SpellInfo const* s){return s->Raw;}
float GetMeleeRange(Unit const* target) const NATIVE_MELEE_BODY
float GetCombatReach()const{return 1.5;}
bool IsWithinMeleeRange(Unit* target){return Distance<=GetMeleeRange(target);}float Distance=8;};
struct SpellProfile {float MaxRange=0;bool RequiresMeleeRange=true;bool RequiresRangedRange=false;std::string TargetSelector="enemy";};
struct BotActionCandidate {int ResolvedSpellId=49998;int SpellId=49998;SpellProfile Profile;std::string RejectReason;};
// Stubs for the admission slice's Elemental Spiritwalker's Grace gates.
namespace BotElementalSpiritwalkersGrace {constexpr char const* MovementRejection="lava_burst_movement";
constexpr char const* ElementalSpec="elemental_shaman";constexpr int SpiritwalkersGraceSpellId=79206;
template<class T> bool HasMovementBlockedDamageOpportunity(T const&){return true;}}
struct ProfileStub {float MaxRange=5;std::string SpecTag="retribution_paladin";};
struct Manager {SpellInfo info;SpellInfo const* GetSpellInfo(int){return &info;}};
Manager* sSpellMgr;
struct Action {float MinRange=0;float MaxRange=5;bool RangeRecoveryRequired=false;};
int main(){Range r;Manager mgr{{&r}};sSpellMgr=&mgr;Player p;auto bot=&p;Unit u;
auto target=&u;auto actionTarget=target;bool selfTarget=false;ProfileStub profile;
// The production helper, built once per scope (it captures raidRotationScope).
auto makeHelper=[&](bool raidRotationScope){
''' + helper + r'''
return effectiveSpellMaxRange;};
constexpr bool Dungeon=false, Raid=true;
auto evaluate=[&](float cap,float distance,bool melee,float raw,bool scope){
auto effectiveSpellMaxRange=makeHelper(scope);
r.Flags=melee?SPELL_RANGE_MELEE:0;mgr.info.Raw=raw;p.Distance=distance;
BotActionCandidate candidate;candidate.Profile.MaxRange=cap;candidate.Profile.RequiresMeleeRange=melee;
Action action;float minRange=0;bool densityOnly=false;bool deferLavaBurstMovementRejection=false;
std::vector<BotActionCandidate> candidates;
for(int once=0;once<1;++once){
''' + admission + r'''
}
auto best=&candidate;action.MaxRange=cap>0?cap:profile.MaxRange;
''' + selected + r'''
return std::make_pair(candidate.RejectReason,action.MaxRange);
};
for(bool scope:{Dungeon,Raid}){
// Native legal at eight yards, outside the five-yard raw DBC default.
auto implicit=evaluate(0,8,true,5,scope);assert(implicit.first.empty());assert(implicit.second==bot->GetMeleeRange(target));
// Only an exact nominal cap is widened, and only in raid scope.
auto shortCap=evaluate(3,8,true,5,scope);assert(shortCap.first=="max_range_exceeded");assert(shortCap.second==3);
auto nearNominal=evaluate(4.99f,8,true,5,scope);assert(nearNominal.first=="max_range_exceeded");
auto policyCap=evaluate(8,10,true,5,scope);assert(policyCap.first=="max_range_exceeded");assert(policyCap.second==8);
auto beyondNative=evaluate(0,14,true,5,scope);assert(beyondNative.first=="melee_range_required");assert(beyondNative.second==bot->GetMeleeRange(target));
auto nominalBeyondNative=evaluate(5,14,true,5,scope);assert(nominalBeyondNative.first=="melee_range_required");
// A non-melee spell never takes the melee rule, in either scope.
auto ranged=evaluate(20,21,false,30,scope);assert(ranged.first=="max_range_exceeded");assert(ranged.second==20);
auto rangedDefault=evaluate(0,31,false,30,scope);assert(rangedDefault.first=="max_range_exceeded");assert(rangedDefault.second==30);
auto nativeRangedCap=evaluate(60,42,false,30,scope);assert(nativeRangedCap.first=="max_range_exceeded");assert(nativeRangedCap.second==41.5f);
auto rangedNominal=evaluate(5,6,false,30,scope);assert(rangedNominal.first=="max_range_exceeded");assert(rangedNominal.second==5);
}
// Dungeon and calibration: an explicit five-yard cap still clips the native
// envelope, exactly as before round 3.
auto dungeonCap=evaluate(5,8,true,5,Dungeon);assert(dungeonCap.first=="max_range_exceeded");assert(dungeonCap.second==5);
auto dungeonInCap=evaluate(5,4,true,5,Dungeon);assert(dungeonInCap.first.empty());assert(dungeonInCap.second==5);
// Raid scope (round 3, 03_melee_profile_native_reach): a declared nominal
// five-yard melee maximum is the approach default, so Mutilate and Crusader
// Strike at 5.4-14 yd from a large boss centre are admitted at native reach.
auto raidCap=evaluate(5,8,true,5,Raid);assert(raidCap.first.empty());assert(raidCap.second==bot->GetMeleeRange(target));
}
'''
    program = program.replace("NATIVE_MELEE_BODY", native_melee_body)
    if rune_strike_caps is not None:
        old_cap, new_cap = rune_strike_caps
        # Outside a raid the old five-yard Rune Strike cap is still rejected
        # at eight yards, which is what the migration fixed; the raid-only
        # nominal-reach rule admits it there as well.
        checks = f"""
        auto oldRuneStrike=evaluate({old_cap},8,true,5,Dungeon);
        assert(oldRuneStrike.first=="max_range_exceeded");
        auto oldRuneStrikeRaid=evaluate({old_cap},8,true,5,Raid);
        assert(oldRuneStrikeRaid.first.empty());
        for(bool scope:{{Dungeon,Raid}}){{
        auto newRuneStrike=evaluate({new_cap},8,true,5,scope);
        assert(newRuneStrike.first.empty());
        assert(newRuneStrike.second==bot->GetMeleeRange(target));
        }}
        """
        end = program.rindex("}")
        program = program[:end] + checks + program[end:]
    cpp = tmp_path / "range.cpp"
    cpp.write_text(program)
    binary = tmp_path / "range"
    subprocess.run(["g++", "-std=c++17", str(cpp), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_rune_strike_migration_preserves_other_action_policy(tmp_path):
    original = (ROOT / "sql/custom/world/2026_07_20_07_phase8_role_qualification_tuning2.sql").read_text()
    start = original.index("INSERT INTO `bot_rotation_action`", original.index("-- Blood Death Knight:"))
    statement = original[start:original.index(";", start) + 1]
    columns = re.search(r"\(([^)]+)\)\s*VALUES", statement, re.S)[1]
    names = [column.strip().strip("`") for column in columns.split(",")]
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE bot_rotation_profile(id,class_id,spec_tag,role)")
    db.execute("INSERT INTO bot_rotation_profile VALUES(267,6,'blood_death_knight','tank')")
    db.execute("CREATE TABLE bot_rotation_action (" + ",".join(names) + ")")
    db.executescript(statement)
    old = dict(db.execute("SELECT * FROM bot_rotation_action").fetchone())
    assert old["spell_id"] == 56815 and old["requires_melee_range"] == 1
    assert old["max_range"] == 5
    # Same spell in another profile and another explicit-cap action must retain
    # their policy. Compare every column, including priority and resource tags.
    db.execute("INSERT INTO bot_rotation_profile VALUES(268,6,'frost','dps')")
    for updates in ({"profile_id": 268}, {"spell_id": 55050}):
        row = {**old, **updates}
        db.execute("INSERT INTO bot_rotation_action VALUES(" + ",".join("?" for _ in names) + ")",
                   [row[name] for name in names])
    migration = (ROOT / "sql/custom/world/2026_09_09_03_blood_rune_strike_native_melee_range.sql").read_text()
    before = [dict(row) for row in db.execute("SELECT * FROM bot_rotation_action ORDER BY rowid")]
    db.executescript(migration)
    after = [dict(row) for row in db.execute("SELECT * FROM bot_rotation_action ORDER BY rowid")]
    assert after == [{**before[0], "max_range": 0}, *before[1:]]
    db.executescript(migration)
    assert [dict(row) for row in db.execute("SELECT * FROM bot_rotation_action ORDER BY rowid")] == after
    test_unset_melee_cap_uses_native_reach(tmp_path, (old["max_range"], after[0]["max_range"]))
