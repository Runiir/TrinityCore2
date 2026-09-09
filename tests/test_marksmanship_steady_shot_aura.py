"""The paired Steady Shot upkeep rows observe the native triggered haste."""
from pathlib import Path
import sqlite3
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_scoped_migration_and_actual_aura_condition_evaluator(tmp_path):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE bot_rotation_profile(id,class_id,spec_tag,role)")
    db.executemany("INSERT INTO bot_rotation_profile VALUES(?,?,?,?)", [
        (1,3,"marksmanship","dps"), (2,3,"survival","dps"),
        (3,3,"marksmanship","tank"), (4,8,"marksmanship","dps")])
    db.execute("CREATE TABLE bot_rotation_action(profile_id,spell_id,sort_order,required_self_aura DEFAULT 0,forbidden_self_aura DEFAULT 0,max_self_aura_remaining_ms DEFAULT 0,priority_bucket,requires_stationary,max_range)")
    rows = [(profile,56641,order,53221 if order==71 else 0,
             53221 if order==70 else 0,3000 if order==71 else 0,5,1,40)
            for profile in (1,2,3,4) for order in (70,71,73)]
    rows += [(1,777,70,0,53221,0,5,1,40)]
    db.executemany("INSERT INTO bot_rotation_action VALUES(?,?,?,?,?,?,?,?,?)",rows)
    for name, default in (("category", "'resource_generator'"), ("mechanic_tags", "''"),
                          ("damage_weight", "0.74"), ("min_enemies", "1"),
                          ("target_selector", "'enemy'"), ("movement_directive", "'ranged'"),
                          ("auto_attack_mode", "'ranged'"), ("min_range", "5")):
        db.execute(f"ALTER TABLE bot_rotation_action ADD COLUMN {name} DEFAULT {default}")
    rows = db.execute("SELECT * FROM bot_rotation_action ORDER BY rowid").fetchall()
    migration = (ROOT / "sql/custom/world/2026_09_09_04_marksmanship_steady_shot_haste_aura.sql").read_text()
    # MySQL requires whitespace after --; SQLite accepts invalid native comments.
    assert not re.search(r"(?m)^\s*--\S", migration)
    expected = list(rows)
    expected[0] = (*rows[0][:4],53220,*rows[0][5:])
    expected[1] = (*rows[1][:3],53220,*rows[1][4:])
    for _ in range(2):
        db.executescript(migration)
        after = db.execute("SELECT * FROM bot_rotation_action ORDER BY rowid").fetchall()
        assert after[:-1] == expected
        assert len(after) == len(expected) + 1
    filler = after[-1]
    assert filler == (1,56641,72,0,0,0,5,1,40,"resource_generator",
                      "steady_shot,focus_builder,apl_final_filler",0.74,1,"enemy","ranged","ranged",5)
    inactive, expiring = expected[:2]
    source = (ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp").read_text()
    start = source.index("    if (!bot)",source.index("std::string EvaluateCompiledConditions"))
    end = source.index("    if (spell.RequiredTargetAura",start)
    evaluator = source[start:end]
    start = source.index("    int32 cost = spellInfo->CalcPowerCost", source.index("bool HasEnoughPowerForProfileSpell"))
    native_power = source[start:source.index("\n}", start)]
    resolver = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp").read_text()
    begin = resolver.index("    auto candidatePreferred =")
    comparator = resolver[begin:resolver.index("\n    };", begin)+7]
    program = r'''
#include <cassert>
#include <map>
#include <string>
#include <vector>
using uint32=unsigned;using int32=int;using int64=long long;
using Powers=int;constexpr int MAX_POWERS=10,POWER_HEALTH=-2;
struct Aura {int duration;int GetDuration()const{return duration;}unsigned GetStackAmount()const{return 1;}unsigned GetCharges()const{return 0;}};
struct Player {unsigned Focus=10;unsigned GetPower(int)const{return Focus;}unsigned GetHealth()const{return 100;}std::map<unsigned,Aura> auras;Aura const* GetAura(unsigned id)const{auto it=auras.find(id);return it==auras.end()?nullptr:&it->second;}bool HasAura(unsigned id)const{return GetAura(id);}};
struct SpellProfile {unsigned RequiredSelfAura=0,ForbiddenSelfAura=0,RequiredSelfAuraStacks=0,MaxSelfAuraStacks=0,RequiredSelfAuraCharges=0,MaxSelfAuraCharges=0,MinSelfAuraRemainingMs=0,MaxSelfAuraRemainingMs=0;unsigned PriorityBucket=5,SortOrder=0;};
struct BotActionCandidate {SpellProfile Profile;float Score=0.74f;unsigned ActionId=0;bool NativePowerReady=true;};
std::string evaluate(Player const* bot,SpellProfile const& spell){
''' + evaluator + r'''
return "";
}
struct SpellInfo {int PowerType=2;int CalcPowerCost(Player const*,int)const{return 50;}int GetSchoolMask()const{return 1;}};
bool powerReady(Player const* bot,SpellInfo const* spellInfo){
NATIVE_POWER
}
int main(){Player player;SpellProfile inactive,expiring;
''' + f'inactive.ForbiddenSelfAura={inactive[4]};expiring.RequiredSelfAura={expiring[3]};expiring.MaxSelfAuraRemainingMs={expiring[5]};\n' + r'''
NATIVE_COMPARATOR
inactive.SortOrder=70;expiring.SortOrder=71;
SpellProfile filler;filler.SortOrder=72;
auto select=[&](){
std::vector<BotActionCandidate> candidates={{inactive},{expiring},{filler}};
// Higher-priority spender is native-power-ineligible; preserve the legal
// fallback without altering the production comparator or aura predicates.
BotActionCandidate spender;spender.Profile.PriorityBucket=1;SpellInfo spenderSpell;spender.NativePowerReady=powerReady(&player,&spenderSpell);
candidates.push_back(spender);
BotActionCandidate const* best=nullptr;
for(auto const& candidate:candidates)
 if(candidate.NativePowerReady && evaluate(&player,candidate.Profile).empty()
    && candidatePreferred(candidate,best))best=&candidate;
assert(best);return best->Profile.SortOrder;
};
// Missing triggered haste: upkeep precedes the equally scored final filler.
assert(select()==70);
assert(evaluate(&player,inactive).empty());assert(evaluate(&player,expiring)=="missing_required_self_aura");
// A permanent passive talent is not the triggered haste, at any rank duration.
player.auras[53221]={-1};player.auras[53224]={-1};assert(select()==70);
assert(evaluate(&player,inactive).empty());assert(evaluate(&player,expiring)=="missing_required_self_aura");
player.auras[53220]={3001};assert(select()==72);
player.Focus=60;assert(select()==0);player.Focus=10;assert(select()==72);
assert(evaluate(&player,inactive)=="forbidden_self_aura_active");
assert(evaluate(&player,expiring)=="self_aura_duration_too_high");
for(int duration:{3000,1,0}){player.auras[53220]={duration};assert(select()==71);
assert(evaluate(&player,inactive)=="forbidden_self_aura_active");assert(evaluate(&player,expiring).empty());}
// Old identity cannot observe triggered haste even at the refresh boundary.
SpellProfile old=expiring;old.RequiredSelfAura=53221;player.auras.erase(53221);
assert(evaluate(&player,old)=="missing_required_self_aura");
}
'''
    program = program.replace("NATIVE_COMPARATOR", comparator).replace("NATIVE_POWER",native_power)
    cpp = tmp_path / "steady.cpp"
    cpp.write_text(program)
    binary = tmp_path / "steady"
    subprocess.run(["g++","-std=c++17",str(cpp),"-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
