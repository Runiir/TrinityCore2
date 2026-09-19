"""Production Flame Orb target filtering with native explicit-target legality.

The fixture executes the production script bodies with deterministic spell and
unit dependencies. It does not simulate the grid search, LOS, spell launch, or
the Magmaw encounter.
"""
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def function(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def fixture_source(script: str) -> str:
    spell_info = (ROOT / "src/server/game/Spells/SpellInfo.cpp").read_text()
    explicit_target = function(spell_info, "SpellCastResult SpellInfo::CheckExplicitTarget(")
    attack_target = function(
        (ROOT / "src/server/game/Entities/Object/WorldObjectSpells.cpp").read_text(),
        "bool WorldObject::IsValidAttackTarget(",
    )
    match = re.search(
        r"    // check flags\n"
        r"    if \(unitTarget && unitTarget->HasFlag\(UNIT_FIELD_FLAGS, "
        r"UNIT_FLAG_NON_ATTACKABLE \| UNIT_FLAG_ON_TAXI \| "
        r"UNIT_FLAG_NOT_ATTACKABLE_1 \| UNIT_FLAG_NON_ATTACKABLE_2\)\)\n"
        r"        return false;",
        attack_target,
    )
    assert match
    attack_flag_check = match.group()

    # Access changes only let this focused fixture invoke the actual production
    # callbacks and helper; their bodies remain byte-for-byte production text.
    script = script.replace("{", "{\npublic:", 1).replace("private:", "public:")
    return r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <initializer_list>
#include <list>
#include <map>
#include <utility>
#include <vector>
using uint32=uint32_t;
using SpellEffIndex=unsigned;
enum SpellCastResult { SPELL_CAST_OK=0, SPELL_FAILED_BAD_TARGETS=13, SPELL_FAILED_TARGET_AURASTATE=21 };
constexpr uint32 TARGET_FLAG_UNIT_ENEMY=1, TARGET_FLAG_UNIT_ALLY=2, TARGET_FLAG_UNIT_RAID=4,
 TARGET_FLAG_UNIT_PARTY=8, TARGET_FLAG_UNIT_MINIPET=16, TARGET_FLAG_UNIT_PASSENGER=32,
 TARGET_FLAG_UNIT_MASK=63, TARGET_FLAG_GAMEOBJECT_MASK=64, TARGET_FLAG_CORPSE_MASK=128,
 TARGET_FLAG_GAMEOBJECT_ITEM=256;
constexpr uint32 UNIT_FIELD_FLAGS=1, UNIT_FLAG_NON_ATTACKABLE=1, UNIT_FLAG_ON_TAXI=2,
 UNIT_FLAG_NOT_ATTACKABLE_1=4, UNIT_FLAG_NON_ATTACKABLE_2=8;
constexpr uint32 SPELL_MAGE_FLAME_ORB_AOE=82734, SPELL_MAGE_FLAME_ORB_BEAM_DUMMY=86719,
 SPELL_MAGE_FLAME_ORB_DAMAGE=82739, SPELL_MAGE_FLAME_ORB_SELF_SNARE=82736,
 SPELL_MAGE_FROSTFIRE_ORB_AOE=84718, SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R1=95969,
 SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R2=84721, SPELL_MAGE_FROSTFIRE_ORB_RANK_R2=84727;
constexpr unsigned EFFECT_0=0, TARGET_UNIT_DEST_AREA_ENEMY=1, SPELL_EFFECT_DUMMY=3;
struct SpellInfo; struct Unit; struct TempSummon; struct Item {};
struct WorldObject {
 float distance=0;
 virtual ~WorldObject()=default;
 virtual Unit const* ToUnit() const { return nullptr; }
 bool IsValidAttackTarget(WorldObject const*,SpellInfo const* =nullptr) const;
 bool IsValidAssistTarget(WorldObject const*,SpellInfo const* =nullptr) const { return false; }
};
struct Cast { Unit* target; uint32 id; };
struct Unit : WorldObject {
 uint32 flags=0; bool targetOk=true, rank2=false; int guid=0; std::vector<Cast> casts;
 Unit const* ToUnit() const override { return this; }
 virtual TempSummon* ToTempSummon() { return nullptr; }
 bool HasFlag(uint32 field,uint32 mask) const { return field==UNIT_FIELD_FLAGS && (flags&mask)!=0; }
 bool IsInPartyWith(Unit const*) const { return false; }
 bool IsInRaidWith(Unit const*) const { return false; }
 int GetGUID() const { return guid; }
 int GetCritterGUID() const { return -1; }
 bool IsOnVehicle(Unit const*) const { return false; }
 bool HasAura(uint32 id) const { return id==SPELL_MAGE_FROSTFIRE_ORB_RANK_R2 && rank2; }
 void CastSpell(Unit* target,uint32 id,bool) { casts.push_back({target,id}); }
};
struct TempSummon : Unit {
 Unit* summoner=nullptr;
 TempSummon* ToTempSummon() override { return this; }
 Unit* GetSummoner() { return summoner; }
};
struct SpellInfo {
 uint32 Id=0,mask=TARGET_FLAG_UNIT_ENEMY;
 uint32 GetExplicitTargetMask() const { return mask; }
 SpellCastResult CheckTarget(WorldObject const*,WorldObject const* target,bool) const {
  Unit const* unit=target?target->ToUnit():nullptr;
  return unit&&unit->targetOk?SPELL_CAST_OK:SPELL_FAILED_TARGET_AURASTATE;
 }
 SpellCastResult CheckExplicitTarget(WorldObject const*,WorldObject const*,Item const* =nullptr) const;
};
bool WorldObject::IsValidAttackTarget(WorldObject const* target,SpellInfo const*) const {
 Unit const* unitTarget=target?target->ToUnit():nullptr;
''' + attack_flag_check + r'''
 return true;
}
''' + explicit_target + r'''
struct SpellMgr {
 std::map<uint32,SpellInfo> infos;
 SpellInfo const* GetSpellInfo(uint32 id) const { auto i=infos.find(id);return i==infos.end()?nullptr:&i->second; }
};
SpellMgr* sSpellMgr=nullptr;
namespace Trinity { struct ObjectDistanceOrderPred {
 ObjectDistanceOrderPred(WorldObject const*,bool){}
 bool operator()(WorldObject const* a,WorldObject const* b) const { return a->distance<b->distance; }
}; }
struct Hook { template<class... T>void Register(T...){} };
struct SpellScript {
 Unit* caster=nullptr;Unit* hit=nullptr;SpellInfo const* current=nullptr;
 Hook OnObjectAreaTargetSelect,OnEffectHitTarget;
 virtual ~SpellScript()=default;virtual bool Validate(SpellInfo const*){return true;}virtual bool Load(){return true;}virtual void Register(){}
 bool ValidateSpellInfo(std::initializer_list<uint32> ids){for(uint32 id:ids)if(!sSpellMgr->GetSpellInfo(id))return false;return true;}
 Unit* GetCaster(){return caster;}Unit* GetHitUnit(){return hit;}SpellInfo const* GetSpellInfo(){return current;}
};
''' + script + r''';
void clear(Unit& orb,Unit& owner){orb.casts.clear();owner.casts.clear();}
int main(){
 SpellMgr manager;sSpellMgr=&manager;
 for(uint32 id:{SPELL_MAGE_FLAME_ORB_AOE,SPELL_MAGE_FROSTFIRE_ORB_AOE,SPELL_MAGE_FLAME_ORB_BEAM_DUMMY,
     SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R1,SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R2,SPELL_MAGE_FLAME_ORB_DAMAGE,
     SPELL_MAGE_FLAME_ORB_SELF_SNARE,SPELL_MAGE_FROSTFIRE_ORB_RANK_R2})manager.infos[id]={id,TARGET_FLAG_UNIT_ENEMY};
 Unit owner;TempSummon orb;orb.summoner=&owner;SpellInfo flame{SPELL_MAGE_FLAME_ORB_AOE,TARGET_FLAG_UNIT_ENEMY};
 spell_mage_flame_orb_aoe_dummy script;script.caster=&orb;script.current=&flame;assert(script.Load());
 Unit head,body;head.distance=1;head.flags=UNIT_FLAG_NON_ATTACKABLE;head.targetOk=true;body.distance=5;
 assert(manager.infos[SPELL_MAGE_FLAME_ORB_DAMAGE].CheckTarget(&owner,&head,true)==SPELL_CAST_OK);
 assert(manager.infos[SPELL_MAGE_FLAME_ORB_DAMAGE].CheckExplicitTarget(&owner,&head)==SPELL_FAILED_BAD_TARGETS);
 assert(!script.IsLegalDamageTarget(&owner,&head,&manager.infos[SPELL_MAGE_FLAME_ORB_DAMAGE]));
 std::list<WorldObject*> targets{&head,&body};script.FilterTargets(targets);
 assert(targets.size()==1&&targets.front()==&body);
 script.hit=&body;script.HandleDummy(0);
 assert(orb.casts.size()==2&&orb.casts[0].id==SPELL_MAGE_FLAME_ORB_SELF_SNARE&&orb.casts[1].id==SPELL_MAGE_FLAME_ORB_BEAM_DUMMY);
 assert(owner.casts.size()==1&&owner.casts[0].target==&body&&owner.casts[0].id==SPELL_MAGE_FLAME_ORB_DAMAGE);

 // Selection can become illegal before effect handling: nothing may cast.
 clear(orb,owner);body.flags=UNIT_FLAG_NON_ATTACKABLE;script.HandleDummy(0);assert(orb.casts.empty()&&owner.casts.empty());
 targets={&head,&body};script.FilterTargets(targets);assert(targets.empty());
 body.flags=0;body.targetOk=false;targets={&body};script.FilterTargets(targets);assert(targets.empty());

 // Existing nearest-by-orb ordering is preserved among legal units.
 body.targetOk=true;Unit farther;farther.distance=9;body.distance=4;targets={&farther,&body};script.FilterTargets(targets);
 assert(targets.size()==1&&targets.front()==&body);

 // Resolve and cast both Frostfire ranks from the exact damage SpellInfo.
 SpellInfo frost{SPELL_MAGE_FROSTFIRE_ORB_AOE,TARGET_FLAG_UNIT_ENEMY};script.current=&frost;assert(script.Load());script.hit=&body;
 clear(orb,owner);owner.rank2=false;script.HandleDummy(0);assert(owner.casts.size()==1&&owner.casts[0].id==SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R1);
 clear(orb,owner);owner.rank2=true;script.HandleDummy(0);assert(owner.casts.size()==1&&owner.casts[0].id==SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R2);

 // Missing summon, summoner, unit target, or exact SpellInfo fails closed.
 Unit ordinary;script.caster=&ordinary;targets={&body};script.FilterTargets(targets);assert(targets.empty());
 script.caster=&orb;orb.summoner=nullptr;targets={&body};script.FilterTargets(targets);assert(targets.empty());
 orb.summoner=&owner;WorldObject nonunit;targets={&nonunit};script.FilterTargets(targets);assert(targets.empty());
 manager.infos.erase(SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R2);targets={&body};script.FilterTargets(targets);assert(targets.empty());
 clear(orb,owner);script.hit=&body;script.HandleDummy(0);assert(orb.casts.empty()&&owner.casts.empty());
}
'''


def compile_fixture(tmp_path: Path, name: str, script: str) -> Path:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(fixture_source(script))
    result = subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return binary


def test_actual_flame_orb_filters_by_summoner_damage_legality(tmp_path):
    source = (ROOT / "src/server/scripts/Spells/spell_mage.cpp").read_text()
    script = function(source, "class spell_mage_flame_orb_aoe_dummy")
    binary = compile_fixture(tmp_path, "flame_orb_legality", script)
    subprocess.run([str(binary)], check=True)

    # The historical CheckTarget-only behavior must select the nearer
    # nonattackable head and fail the same executable counterexample.
    explicit_clause = (
        "            && damageInfo->CheckExplicitTarget(summoner, unitTarget) == SPELL_CAST_OK\n"
    )
    mutant = script.replace(explicit_clause, "")
    assert mutant != script
    mutant_binary = compile_fixture(tmp_path, "flame_orb_checktarget_only", mutant)
    assert subprocess.run([str(mutant_binary)], capture_output=True).returncode != 0
