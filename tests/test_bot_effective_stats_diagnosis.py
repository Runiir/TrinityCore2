"""Ordinary diagnosis reuses the native effective-stat collector and serializer."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationStatLedger.cpp"
DIAGNOSIS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrDiagnosis.cpp"


def test_effective_owner_and_persistent_pet_stats_use_production_code(tmp_path):
    production = LEDGER.read_text(encoding="utf-8")
    production = production[production.index("namespace\n{") :]
    diagnosis = DIAGNOSIS.read_text(encoding="utf-8")
    assert '"effective_stats\\":" << BuildEffectiveStatsSnapshotJson(bot, nowMs)' in diagnosis

    fixture = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <tuple>
#include <type_traits>
#include <vector>
using uint8=std::uint8_t;using uint16=std::uint16_t;using uint32=std::uint32_t;
using uint64=std::uint64_t;using int32=std::int32_t;
template<class T> constexpr auto AsUnderlyingType(T value){return static_cast<std::underlying_type_t<T>>(value);}
enum Stats:uint8{STAT_STRENGTH,STAT_AGILITY,STAT_STAMINA,STAT_INTELLECT,STAT_SPIRIT,MAX_STATS};
enum SpellSchools:uint8{SPELL_SCHOOL_NORMAL,SPELL_SCHOOL_HOLY,SPELL_SCHOOL_FIRE,SPELL_SCHOOL_NATURE,SPELL_SCHOOL_FROST,SPELL_SCHOOL_SHADOW,SPELL_SCHOOL_ARCANE,MAX_SPELL_SCHOOL};
using SpellSchoolMask=uint32;
enum WeaponAttackType:uint8{BASE_ATTACK,RANGED_ATTACK};
enum Powers:uint8{POWER_MANA};
enum CombatRating:uint8{CR_HIT_SPELL,CR_CRIT_SPELL,CR_HASTE_SPELL,CR_EXPERTISE,CR_MASTERY,CR_HIT_MELEE};
enum AuraType:uint8{SPELL_AURA_MOD_STAT,SPELL_AURA_MOD_PERCENT_STAT,SPELL_AURA_MOD_TOTAL_STAT_PERCENTAGE,SPELL_AURA_MOD_HIT_CHANCE,SPELL_AURA_MOD_SPELL_HIT_CHANCE};
enum UnitMods:uint8{UNIT_MOD_STAT_START};
enum UnitModifierType:uint8{BASE_VALUE,BASE_PCT,TOTAL_VALUE,TOTAL_PCT};
constexpr uint32 UNIT_FIELD_BASEATTACKTIME=10,UNIT_FIELD_RANGEDATTACKTIME=11,UNIT_MOD_CAST_HASTE=12;
constexpr uint32 PLAYER_FIELD_COMBAT_RATING_1=100,PLAYER_CRIT_PERCENTAGE=200,PLAYER_RANGED_CRIT_PERCENTAGE=201,PLAYER_SPELL_CRIT_PERCENTAGE1=210;
struct Guid{uint64 Value=0;uint32 GetCounter()const{return uint32(Value);}uint64 GetRawValue()const{return Value;}};
struct AuraEffect{AuraType GetAuraType()const{return SPELL_AURA_MOD_STAT;}int GetMiscValueB()const{return 0;}int GetMiscValue()const{return 0;}uint32 GetId()const{return 0;}uint8 GetEffIndex()const{return 0;}int GetAmount()const{return 0;}Guid GetCasterGUID()const{return {};}};
struct SpellInfo{uint32 Id=0;SpellSchoolMask SchoolMask=0;bool Dangerous=false;SpellSchoolMask GetSchoolMask()const{return SchoolMask;}};
struct SpellMgr{std::map<uint32,SpellInfo> Spells;SpellInfo const* GetSpellInfo(uint32 id)const{auto it=Spells.find(id);return it==Spells.end()?nullptr:&it->second;}};
SpellMgr spellMgr;SpellMgr* sSpellMgr=&spellMgr;
struct BotWorldPopulationMgrSpellSemantics{static bool SpellLooksDangerous(SpellInfo const* spell){return spell&&spell->Dangerous;}};
struct Player;struct Pet;
struct Unit{
 Guid GuidValue;uint32 Entry=0;std::array<float,MAX_STATS> StatValues{};float AttackPower=0,RangedAttackPower=0;
 std::array<int32,MAX_SPELL_SCHOOL> SchoolPower{};uint32 Armor=0;uint64 MaxHealth=0;uint32 Mana=0;
 std::map<uint32,float> FloatValues;std::map<uint32,uint32> UIntValues;
 virtual ~Unit()=default;virtual Player const* ToPlayer()const{return nullptr;}virtual Pet const* ToPet()const{return nullptr;}
 Guid GetGUID()const{return GuidValue;}uint32 GetEntry()const{return Entry;}float GetStat(Stats s)const{return StatValues[s];}
 float GetTotalAttackPowerValue(WeaponAttackType type)const{return type==BASE_ATTACK?AttackPower:RangedAttackPower;}
 int32 SpellBaseDamageBonusDone(SpellSchoolMask mask,bool)const{for(uint8 s=1;s<MAX_SPELL_SCHOOL;++s)if(mask&(1u<<s))return SchoolPower[s];return 0;}
 uint32 GetArmor()const{return Armor;}uint64 GetMaxHealth()const{return MaxHealth;}uint32 GetMaxPower(Powers)const{return Mana;}
 float GetFloatValue(uint32 index)const{auto it=FloatValues.find(index);return it==FloatValues.end()?0.0f:it->second;}
 uint32 GetUInt32Value(uint32 index)const{auto it=UIntValues.find(index);return it==UIntValues.end()?0:it->second;}
 uint32 GetBaseAttackTime(WeaponAttackType type)const{return type==BASE_ATTACK?2000:2500;}
 int GetTotalAuraModifier(AuraType)const{return 0;}float GetUnitCriticalChanceDone(WeaponAttackType)const{return 7.5f;}
 float GetCreateStat(Stats s)const{return StatValues[s]-1;}float GetFlatModifierValue(UnitMods,UnitModifierType type)const{return type==BASE_VALUE?10:0;}
 float GetPctModifierValue(UnitMods,UnitModifierType)const{return 1;}float GetTotalStatValue(Stats s)const{return StatValues[s];}
 std::vector<AuraEffect const*> const& GetAuraEffectsByType(AuraType)const{static std::vector<AuraEffect const*> none;return none;}
 virtual float SpellCritChanceDone(SpellInfo const*,SpellSchoolMask)const{return 0;}virtual Unit const* GetOwner()const{return nullptr;}
};
struct Player:Unit{
 Pet* CurrentPet=nullptr;std::array<float,8> RatingBonus{};
 Player const* ToPlayer()const override{return this;}float GetRatingBonusValue(CombatRating rating)const{return RatingBonus[rating];}
 Pet* GetPet()const{return CurrentPet;}
};
struct Pet:Unit{
 Player* Owner=nullptr;bool Permanent=true;int32 BonusDamage=0;float NativeSpellCrit=0;std::vector<uint32> AutoSpells;
 Pet const* ToPet()const override{return this;}int32 GetBonusDamage()const{return BonusDamage;}
 uint8 GetPetAutoSpellSize()const{return uint8(AutoSpells.size());}uint32 GetPetAutoSpellOnPos(uint8 i)const{return AutoSpells[i];}
 float SpellCritChanceDone(SpellInfo const*,SpellSchoolMask)const override{return NativeSpellCrit;}
 Unit const* GetOwner()const override{return Owner;}bool IsPermanentPetFor(Player* owner)const{return Permanent&&owner==Owner;}
};
struct BotWorldPopulationMgr{
 struct CalibrationMetrics{struct EffectiveStatVector{
  struct SpellSchoolObservation{int32 SpellPower=0;float CritPct=0;bool CritObserved=false;uint32 CritSourceSpellId=0;};
  struct AuraContribution{uint16 AuraType=0;uint32 SpellId=0;uint8 EffectIndex=0;int32 Amount=0;int32 MiscValue=0;int32 MiscValueB=0;uint64 CasterGuid=0;};
  struct PrimaryStatLedger{uint8 StatIndex=0;float CreateStat=0,BaseValue=0,BasePct=1,TotalValue=0,TotalPct=1,RecomputedTotal=0,PublishedStat=0;std::vector<AuraContribution>AuraContributions;};
  bool Observed=false;uint64 ObservedAtMs=0;uint32 Guid=0,Entry=0;float Strength=0,Agility=0,Stamina=0,Intellect=0,Spirit=0,AttackPower=0,RangedAttackPower=0;int32 SpellPower=0,BonusDamage=0;uint32 Armor=0;uint64 Health=0;uint32 Mana=0,HitRating=0,CritRating=0,HasteRating=0,ExpertiseRating=0,MasteryRating=0;float PhysicalHitPct=0,SpellHitPct=0,MeleeCritPct=0,RangedCritPct=0,SpellCritPct=0,MasteryPoints=0,MeleeSpeedMultiplier=1,RangedSpeedMultiplier=1,SpellSpeedMultiplier=1;std::array<SpellSchoolObservation,7>SpellSchools;std::array<PrimaryStatLedger,5>PrimaryStatLedgerEntries;
 };};
 static void ObserveCalibrationEffectiveStats(Unit const*,uint64,CalibrationMetrics::EffectiveStatVector&);
 static void AppendCalibrationEffectiveStatsJson(std::ostringstream&,CalibrationMetrics::EffectiveStatVector const&);
 static std::string BuildEffectiveStatsSnapshotJson(Player const*,uint64);
};
''' + production + r'''
int main(){
 spellMgr.Spells.emplace(100,SpellInfo{100,1u<<SPELL_SCHOOL_FIRE,true});
 Player caster;caster.GuidValue={11};caster.Entry=77;caster.StatValues={100,200,300,400,500};caster.AttackPower=900;caster.RangedAttackPower=1100;caster.Armor=2200;caster.MaxHealth=33000;caster.Mana=44000;
 caster.FloatValues[UNIT_FIELD_BASEATTACKTIME]=1000;caster.FloatValues[UNIT_FIELD_RANGEDATTACKTIME]=1250;caster.FloatValues[UNIT_MOD_CAST_HASTE]=0.8f;caster.FloatValues[PLAYER_CRIT_PERCENTAGE]=9.5f;caster.FloatValues[PLAYER_RANGED_CRIT_PERCENTAGE]=17.0f;
 caster.SchoolPower[SPELL_SCHOOL_HOLY]=6800;caster.SchoolPower[SPELL_SCHOOL_FIRE]=7123;caster.SchoolPower[SPELL_SCHOOL_SHADOW]=6900;
 caster.FloatValues[PLAYER_SPELL_CRIT_PERCENTAGE1+SPELL_SCHOOL_FIRE]=18.25f;caster.FloatValues[PLAYER_SPELL_CRIT_PERCENTAGE1+SPELL_SCHOOL_SHADOW]=22.5f;
 Pet pet;pet.GuidValue={21};pet.Entry=416;pet.Owner=&caster;pet.Permanent=true;pet.BonusDamage=1550;pet.NativeSpellCrit=12.5f;pet.AutoSpells={100};pet.SchoolPower[SPELL_SCHOOL_FIRE]=1600;caster.CurrentPet=&pet;
 Player physical;physical.GuidValue={12};physical.Entry=88;physical.StatValues={800,700,600,100,50};physical.AttackPower=5200;physical.RangedAttackPower=300;physical.FloatValues[UNIT_FIELD_BASEATTACKTIME]=2000;physical.FloatValues[UNIT_FIELD_RANGEDATTACKTIME]=2500;physical.FloatValues[UNIT_MOD_CAST_HASTE]=1;
 std::cout<<BotWorldPopulationMgr::BuildEffectiveStatsSnapshotJson(&caster,123456)<<'\n';
 std::cout<<BotWorldPopulationMgr::BuildEffectiveStatsSnapshotJson(&physical,123457)<<'\n';
}
'''
    cpp = tmp_path / "effective_stats.cpp"
    cpp.write_text(fixture, encoding="utf-8")
    binary = tmp_path / "effective_stats"
    subprocess.run(["g++", "-std=c++17", str(cpp), "-o", str(binary)], check=True)
    output = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    caster, physical = [json.loads(line) for line in output.stdout.splitlines()]

    assert caster["observed_at_ms"] == 123456
    assert caster["owner"]["guid"] == 11
    assert caster["owner"]["intellect"] == 400
    assert caster["owner"]["spell_power"] == 7123  # Legacy max-school scalar.
    assert caster["owner"]["spell_crit_pct"] == 22.5  # Legacy Shadow scalar.
    assert caster["owner"]["spell_schools"]["fire"] == {
        "spell_power": 7123,
        "crit_pct": 18.25,
        "crit_observed": True,
        "crit_source_spell_id": 0,
    }
    assert caster["persistent_pet"]["present"] is True
    assert caster["persistent_pet"]["observed_at_ms"] == 123456
    assert caster["persistent_pet"]["guid"] == 21
    assert caster["persistent_pet"]["entry"] == 416
    assert caster["persistent_pet"]["effective_stats"]["bonus_damage"] == 1550
    assert caster["persistent_pet"]["effective_stats"]["spell_schools"]["fire"] == {
        "spell_power": 1600,
        "crit_pct": 12.5,
        "crit_observed": True,
        "crit_source_spell_id": 100,
    }

    assert physical["observed_at_ms"] == 123457
    assert physical["owner"]["guid"] == 12
    assert physical["owner"]["attack_power"] == 5200
    assert physical["persistent_pet"]["present"] is False
    assert physical["persistent_pet"]["guid"] == 0
    assert physical["persistent_pet"]["effective_stats"]["observed"] is False
