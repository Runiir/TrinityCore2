from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "src/server/game/Entities/Unit"


def extract(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_native_fire_elemental_stat_owner_and_repeated_updates(tmp_path):
    summon = (ROOT / "src/server/game/Entities/Creature/TemporarySummon.cpp").read_text()
    stats = (UNIT / "GuardianStatSystem.cpp").read_text()
    functions = extract(summon, "Unit* Guardian::GetStatOwner() const") + "\n"
    header = (ROOT / "src/server/game/Entities/Creature/TemporarySummon.h").read_text()
    getters = extract(header, "int32 GetBonusDamage() const") + "\n"
    getters += extract(header, "int32 GetOwnerSpellDamageBonus() const")
    assert ", m_ownerSpellDamageBonus(0)" in summon
    for signature in ["bool Guardian::UpdateAllStats()", "void Guardian::UpdateAttackPowerAndDamage(bool ranged)",
                      "void Guardian::UpdateDamagePhysical(WeaponAttackType attType)",
                      "void Guardian::SetBonusDamage(int32 damage)"]:
        functions += extract(stats, signature) + "\n"
    source = tmp_path / "owner_stats.cpp"
    source.write_text(r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <vector>
using uint32=uint32_t; using int32=int32_t; using uint8=uint8_t;
using UnitMods=int; using WeaponAttackType=int; using Stats=int; using Powers=int;
constexpr int TYPEID_PLAYER=4, ENTRY_FIRE_ELEMENTAL=15438, ENTRY_TREANT=1964;
constexpr int STAT_STRENGTH=0, MAX_STATS=5, POWER_MANA=0, MAX_POWERS=5;
constexpr int UNIT_MOD_ATTACK_POWER=0, UNIT_MOD_DAMAGE_MAINHAND=1;
constexpr int BASE_VALUE=0, TOTAL_VALUE=1, BASE_PCT=0, TOTAL_PCT=1;
constexpr int BASE_ATTACK=0, MINDAMAGE=0, MAXDAMAGE=1;
constexpr int UNIT_FIELD_ATTACK_POWER=1, UNIT_FIELD_ATTACK_POWER_MOD_POS=2;
constexpr int UNIT_FIELD_ATTACK_POWER_MOD_NEG=3, UNIT_FIELD_ATTACK_POWER_MULTIPLIER=4;
constexpr int UNIT_FIELD_MINDAMAGE=5, UNIT_FIELD_MAXDAMAGE=6, PLAYER_PET_SPELL_POWER=7;
constexpr int PLAYER_FIELD_MOD_DAMAGE_DONE_POS=100, PLAYER_FIELD_MOD_DAMAGE_DONE_NEG=200;
constexpr int SPELL_SCHOOL_FIRE=2, SPELL_SCHOOL_NATURE=3, SPELL_SCHOOL_MASK_FIRE=4;
constexpr int SPELL_AURA_MOD_DAMAGE_DONE=0, SPELL_AURA_MOD_ATTACKSPEED=1;
int AsUnderlyingType(int value) { return value; }
void AddPct(float& value, float pct) { value *= 1.0f+pct/100.0f; }
struct SpellInfo { uint32 Id=0; };
struct Aura { int amount=0; SpellInfo spell; int GetAmount() const { return amount; }
 SpellInfo const* GetSpellInfo() const { return &spell; } };
struct Totem;
struct Unit {
 using AuraEffectList=std::vector<Aura*>;
 Unit* genericOwner=nullptr; bool totem=false, alive=true; int type=TYPEID_PLAYER;
 int32 fireSP=1000; uint32 firePositive=1000, fireNegative=0, natureSP=1000;
 Unit* GetOwner() const { return genericOwner; } // nonvirtual native generic path
 bool IsTotem() const { return totem; }
 Totem* ToTotem();
 int GetTypeId() const { return type; }
 int32 SpellBaseDamageBonusDone(int school) const { assert(school==SPELL_SCHOOL_MASK_FIRE); return fireSP; }
 uint32 GetUInt32Value(int field) const {
  if(field==PLAYER_FIELD_MOD_DAMAGE_DONE_POS+SPELL_SCHOOL_FIRE) return firePositive;
  if(field==PLAYER_FIELD_MOD_DAMAGE_DONE_NEG+SPELL_SCHOOL_FIRE) return fireNegative;
  if(field==PLAYER_FIELD_MOD_DAMAGE_DONE_POS+SPELL_SCHOOL_NATURE) return natureSP;
  return 0;
 }
 void SetUInt32Value(int, int32) {}
};
struct Totem: Unit { Unit* nativeOwner=nullptr; Totem(){totem=true;type=3;}
 Unit* GetOwner() const { return nativeOwner; } };
Totem* Unit::ToTotem(){return static_cast<Totem*>(this);}
struct Minion: Unit { Unit* m_owner=nullptr; Unit* GetOwner() const {return m_owner;} };
struct Guardian: Minion {
 int entry=ENTRY_FIRE_ELEMENTAL; int32 m_bonusSpellDamage=0, m_ownerSpellDamageBonus=0;
 float attackPower=0, minimum=0, maximum=0;
 float flats[2][2]={{0,0},{3,4}}, percentages[2][2]={{1,1},{1.2f,1.1f}};
 Aura local{17,{}}, slow{10,{61682}}; AuraEffectList damage{&local}, speed{&slow};
''' + getters + r'''
 Unit* GetStatOwner() const;
 bool UpdateAllStats(); void UpdateAttackPowerAndDamage(bool ranged=false);
 void UpdateDamagePhysical(WeaponAttackType); void SetBonusDamage(int32);
 int GetEntry()const{return entry;} float GetStat(int)const{return 120;}
 void UpdateMaxHealth(){} void UpdateMaxPower(int){} void UpdateAllResistances(){}
 void UpdateStats(int stat){if(stat==STAT_STRENGTH)UpdateAttackPowerAndDamage();}
 void SetStatFlatModifier(int mod,int kind,float value){flats[mod][kind]=value;}
 float GetFlatModifierValue(int mod,int kind)const{return flats[mod][kind];}
 float GetPctModifierValue(int mod,int kind)const{return percentages[mod][kind];}
 void SetInt32Value(int field,int32 value){if(field==UNIT_FIELD_ATTACK_POWER)attackPower=value;}
 void SetFloatValue(int,float){} void SetStatFloatValue(int field,float value){
  if(field==UNIT_FIELD_MINDAMAGE)minimum=value;else if(field==UNIT_FIELD_MAXDAMAGE)maximum=value;
 }
 float GetTotalAttackPowerValue(int)const{return attackPower;}
 uint32 GetBaseAttackTime(int)const{return 2000;}
 float GetWeaponDamageRange(int,int kind)const{return kind==MINDAMAGE?10:20;}
 AuraEffectList const& GetAuraEffectsByType(int type)const{return type==SPELL_AURA_MOD_DAMAGE_DONE?damage:speed;}
};
''' + functions + r'''
float Expected(float bonus, float weapon) {
 return (((3+200.0f/14*2+bonus+weapon)*1.2f+4)*1.1f)*0.9f;
}
void Check(Guardian& guardian, int spellBonus, float meleeBonus) {
 Unit* immediate=guardian.GetOwner();
 for(int i=0;i<3;++i){
  assert(guardian.UpdateAllStats());
  assert(guardian.GetBonusDamage()==17);
  assert(guardian.GetOwnerSpellDamageBonus()==spellBonus);
  assert(std::fabs(guardian.minimum-Expected(meleeBonus,10))<0.001f);
  assert(std::fabs(guardian.maximum-Expected(meleeBonus,20))<0.001f);
  assert(guardian.GetOwner()==immediate);
 }
}
int main(){
 Unit player; Totem totem; totem.nativeOwner=&player;
 assert(static_cast<Unit*>(&totem)->GetOwner()==nullptr);
 Guardian fire; fire.m_owner=&totem;
 assert(fire.GetStatOwner()==&player); Check(fire,500,400);
 player.alive=false; Check(fire,500,400); // persistent stat identity is not combat eligibility
 player.alive=true; player.fireSP=1200; player.firePositive=1200; Check(fire,600,480);
 Guardian direct; direct.m_owner=&player; Check(direct,600,480);
 Guardian other; other.entry=999; other.m_owner=&totem; Check(other,0,0);
 Guardian treant; treant.entry=ENTRY_TREANT; treant.m_owner=&player; Check(treant,0,90);
 totem.nativeOwner=nullptr; Check(fire,0,0);
 Unit npc; npc.type=3; totem.nativeOwner=&npc; Check(fire,0,0);
 Totem second; second.nativeOwner=&player; totem.nativeOwner=&second;
 assert(fire.GetStatOwner()==&second); Check(fire,0,0); // exactly one hop
 Guardian ownerless; assert(ownerless.GetStatOwner()==nullptr);
 // The native SetBonusDamage contract requires an immediate Minion owner;
 // exercise only resolution for an uninitialized ownerless guardian.
}
''')
    binary = tmp_path / "owner_stats"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
