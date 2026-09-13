"""Observation-only native filter/serializer and the real resolver publication guard.

Native-shaped fixtures replace the server object graph, not the production scan,
math, JSON, or guard. Native build/live validation remains parent-owned.
"""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / 'src/server/game/Bots'

STUB = r'''
#pragma once
#include <cstdint>
#include <vector>
#include <map>
using uint64=uint64_t; using uint32=uint32_t; using int32=int32_t; using int64=int64_t;
constexpr unsigned EFFECT_0=0,MAX_SPELL_EFFECTS=3,SPELL_SCHOOL_FIRE=2,SPELL_SCHOOL_MASK_FIRE=4,SPELLFAMILY_MAGE=3;
constexpr unsigned SPELL_AURA_PERIODIC_DAMAGE=3,SPELL_AURA_MOD_ATTACKER_SPELL_CRIT_CHANCE=4;
constexpr unsigned SPELL_AURA_MOD_ATTACKER_SPELL_AND_WEAPON_CRIT_CHANCE=5,SPELL_AURA_MOD_CRIT_DAMAGE_BONUS=6;
constexpr unsigned PLAYER_SPELL_CRIT_PERCENTAGE1=10,CLASS_MAGE=8;
struct Guid {unsigned value; unsigned GetCounter()const{return value;} bool operator!=(Guid b)const{return value!=b.value;}};
constexpr unsigned SPELL_EFFECT_SCRIPT_EFFECT=77,SPELL_ATTR8_MASTERY_AFFECTS_POINTS=1,SPELL_ATTR1_FINISHING_MOVE_DAMAGE=2;
struct SpellEffectInfo {unsigned Effect=77,ApplyAuraName=0,AuraPeriod=0,SpellClassMask=123;int BasePoints=100,DieSides=0;float RealPointsPerLevel=0,PointsPerComboPoint=0;
 struct {float Coefficient=0,Variance=0,ComboPointsCoefficient=0;} Scaling;};
struct SpellInfo {unsigned Id=0,SpellFamilyName=SPELLFAMILY_MAGE,school=SPELL_SCHOOL_MASK_FIRE;bool affected=true;
 SpellEffectInfo Effects[3];unsigned attributes=0;bool HasAttribute(unsigned a)const{return attributes&a;}
 float CritDamageMultiplier=2.f; int duration=10000;float haste=.8f;
 unsigned GetSchoolMask()const{return school;} bool IsAffected(unsigned family,unsigned mask)const{return affected&&family==SPELLFAMILY_MAGE&&mask==123;}
 int GetDuration()const{return duration;} float CalcPeriodicHasteMod(struct Unit const*)const{return haste;}};
struct Aura {int duration=23000;int GetDuration()const{return duration;}};
struct AuraEffect {SpellInfo const* info;unsigned owner=30006,index=0;int amount=10000;
 Guid GetCasterGUID()const{return {owner};} SpellInfo const* GetSpellInfo()const{return info;}
 unsigned GetEffIndex()const{return index;}int GetAmount()const{return amount;}};
struct Unit {unsigned guid=76,entry=42347;bool hostile=true;std::map<unsigned,Aura> auras;std::vector<AuraEffect const*> effects;
 Guid GetGUID()const{return {guid};}unsigned GetEntry()const{return entry;}
 Aura const* GetAura(unsigned id)const{auto i=auras.find(id);return i==auras.end()?nullptr:&i->second;}
 bool HasAura(unsigned id,Guid owner)const{return owner.value==30006&&GetAura(id);}
 AuraEffect const* GetAuraEffect(unsigned id,unsigned index,Guid owner)const{for(auto e:effects)if(e->info->Id==id&&e->index==index&&e->owner==owner.value)return e;return nullptr;}
 auto const& GetAuraEffectsByType(unsigned type)const{if(type!=SPELL_AURA_PERIODIC_DAMAGE)throw 1;return effects;}
 int GetTotalAuraModifierByMiscMask(unsigned type,unsigned mask)const{if(type!=4||mask!=4)throw 2;return 5;}
 int GetTotalAuraModifier(unsigned type)const{if(type!=5)throw 3;return 3;}};
struct Player:Unit {unsigned klass=CLASS_MAGE;unsigned getClass()const{return klass;}unsigned getRace()const{return 8;}
 bool HasSpell(unsigned id)const{return id==26297;}int CalculateSpellDamage(Unit const*,SpellInfo const*,unsigned)const=delete;
 float GetFloatValue(unsigned field)const{if(field!=12)throw 5;return 20;}
 float GetTotalAuraMultiplierByMiscMask(unsigned type,unsigned mask)const{if(type!=6||mask!=4)throw 6;return 1.1f;}
 bool IsValidAttackTarget(Unit const* t)const{return t&&t->hostile;}};
struct SpellMgr {SpellInfo combustion,periodic;bool haveCombustion=true,havePeriodic=true;
 SpellMgr(){combustion.Id=11129;periodic.Id=83853;periodic.Effects[1].ApplyAuraName=3;periodic.Effects[1].AuraPeriod=1000;}
 SpellInfo const* GetSpellInfo(unsigned id)const{return id==11129?(haveCombustion?&combustion:nullptr):(havePeriodic?&periodic:nullptr);}};
inline SpellMgr manager;inline SpellMgr* sSpellMgr=&manager;
template<class T>T CalculatePct(T v,float p){return T(float(v)*p/100.f);}
'''


def compile_run(tmp_path, body):
    for name in ('Define.h', 'Player.h', 'SpellAuraEffects.h', 'SpellAuras.h', 'SpellInfo.h', 'SpellMgr.h', 'Util.h'):
        (tmp_path / name).write_text('#include "stub.h"\n')
    (tmp_path / 'stub.h').write_text(STUB)
    source = tmp_path / 'main.cpp'
    source.write_text('#include "Bots/BotFireCombustionObservation.h"\n#include "stub.h"\n#include <iostream>\n#include <algorithm>\n' + body)
    binary = tmp_path / 'observe'
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(tmp_path), '-I', str(ROOT / 'src/server/game'), str(source), str(BOTS / 'BotFireCombustionObservation.cpp'), '-o', str(binary)], check=True)
    return subprocess.check_output([str(binary)], text=True).splitlines()


def test_native_filter_gate_inputs_math_and_bounded_serialization(tmp_path):
    lines = compile_run(tmp_path, r'''
using namespace BotFireCombustionObservation;
int main(){
 manager.combustion.Effects[0].BasePoints=50; // Controlled math fixture; native raw effect 0 is 100.
 Player actor;actor.guid=30006;actor.entry=0;actor.auras[2825]={12000};actor.auras[26297]={5000};Unit target;
 SpellInfo info[14];AuraEffect effects[14];
 for(unsigned i=0;i<14;++i){info[i].Id=20000-i;effects[i]={&info[i],30006,0,10000+int(i)};target.effects.push_back(&effects[i]);}
 effects[0].owner=30007; info[1].school=16;info[2].SpellFamilyName=9;info[3].affected=false;
 target.auras[12654]={};target.auras[44457]={};target.auras[92315]={};
 info[4].Id=12654;
 auto print=[&](){std::cout<<ToJson(Capture(&actor,&target,1000,1002))<<'\n';};print();
 effects[4].amount=9999;print();effects[4].amount=10000;
 target.auras.erase(44457);print();target.auras[44457]={};target.auras.erase(92315);print();
 target.auras[11366]={};print();effects[4].index=1;print();
 target.auras.clear();print();
 manager.haveCombustion=false;print();manager.haveCombustion=true;manager.havePeriodic=false;print();manager.havePeriodic=true;
 std::cout<<ToJson(Capture(nullptr,&target,1000,1002))<<'\n'<<ToJson(Capture(&actor,nullptr,1000,1002))<<'\n';
 std::cout<<ToJson(Capture(&actor,&target,1000,999))<<'\n';
}
''')
    values = list(map(json.loads, lines))
    first = values[0]
    assert first['schema'] == 'fire_combustion_candidate_observation_v1'
    assert (first['actor_guid'], first['target_guid'], first['target_entry']) == (30006, 76, 42347)
    assert (first['evaluation_started_at_ms'], first['observed_at_ms']) == (1000, 1002)
    assert first['eligible_component_count'] == 10
    assert first['summed_base_points'] == sum(int((10000 + i) * .5) for i in range(4, 14))
    assert first['components_truncated'] is True
    assert len(first['components']) == 8
    assert first['components'] == sorted(first['components'])
    assert all(row[0] not in (20000, 19999, 19998, 19997) for row in first['components'])
    assert first['scaling_percent'] == 50
    assert first['scaling_kind'] == 'raw_effect0_excluding_spellmods'
    assert first['native_exact'] is False
    assert first['available']['raw_scale'] is True
    assert first['periodic'] == {'effect_index': 1, 'duration_ms': 10000, 'period_ms': 1000, 'haste_mod': pytest.approx(.8), 'hasted_period_ms': 800, 'ticks': 12}
    assert first['crit'] == pytest.approx([20, 5, 3, 2, 1.1])
    assert first['estimated_total'] == pytest.approx(first['summed_base_points'] * 12 * (1 + .28 * 1.2))
    assert first['buffs'] == [[2825, True, 12000], [32182, False, None], [80353, False, None], [26297, True, 5000]]
    assert first['race_id'] == 8 and first['berserking_known']
    assert first['estimate_kind'] == 'derived_candidate_state_not_observed_outcome'
    assert {'spellmods', 'absorbs', 'resistance', 'later_aura_changes', 'landed_RNG'} <= set(first['excluded'].split(','))
    for i, expected in enumerate(({'current_gate_ready'}, {'ignite_below_10000'}, {'missing_living_bomb'}, {'missing_pyro'}, {'current_gate_ready'}, {'missing_ignite_effect0'}, {'missing_ignite_effect0', 'missing_living_bomb', 'missing_pyro'})):
        assert {k for k, v in values[i]['gate'].items() if v} == expected
    for value in values[7:]:
        assert value['estimated_total'] is None
    assert not values[7]['available']['combustion']
    assert not values[8]['available']['periodic']
    assert not values[9]['available']['actor']
    assert not values[10]['available']['target']
    assert not values[11]['clock_valid']
    assert max(map(lambda s: len(s.encode()), lines)) <= 2048


def test_actual_resolver_guard_and_unchanged_admission(tmp_path):
    resolver = (BOTS / 'BotWorldPopulationMgrCombatResolver.cpp').read_text()
    start = resolver.index('    if (publishDiagnostics)')
    end = resolver.index('        uint32 botKey', start)
    block = resolver[start:end] + '    }\n'
    assert block.count('BotFireCombustionObservation::Capture(') == 1
    assert block.count('candidates.front().ObservationJson =') == 1
    assert end < resolver.index('BotClassSpecActionProfileStore::CandidateMaskJson(', start)
    gate = resolver[resolver.index('        if (bot->getClass() == CLASS_MAGE && candidate.SpellId == 11129)'):resolver.index('        if (candidate.Profile.RequiresInterruptibleTarget')]
    assert gate == '''        if (bot->getClass() == CLASS_MAGE && candidate.SpellId == 11129)
        {
            // WoWSims waits for a meaningful Combustion estimate, not merely
            // the presence of three weak DoTs.  Ignite's current periodic
            // amount is the reliable live proxy available to the bot.  A
            // 10k tick is reachable in raid-normalized P4 gear while avoiding
            // the near-empty Combustions observed in calibration run 225.
            AuraEffect const* ignite = target->GetAuraEffect(12654, EFFECT_0, bot->GetGUID());
            if (!ignite || ignite->GetAmount() < 10000 || !target->HasAura(44457, bot->GetGUID())
                || (!target->HasAura(92315, bot->GetGUID()) && !target->HasAura(11366, bot->GetGUID())))
            {
                candidate.RejectReason = "combustion_dot_window_not_ready";
                continue;
            }
        }
'''
    body = r'''
struct BotActionCandidate {unsigned SpellId=11129;std::string ObservationJson="{}";};
namespace BotWorldPopulationMgrSpellSemantics {uint64 NowMs(){return 1002;}}
void publish(Player* bot,Unit* target,bool publishDiagnostics,std::string spec,std::vector<BotActionCandidate>& candidates){
 struct {std::string SpecTag;} profile{spec};uint64 const maskEvaluatedAtMs=1000;
''' + block + r'''
}
int main(){Player actor;actor.guid=30006;Unit enemy,ally;ally.hostile=false;
 for(int i=0;i<8;++i){std::vector<BotActionCandidate> candidates{{123,"{\"frost\":true}"},{11129,"{}"}};
  actor.klass=i==1?9:CLASS_MAGE;if(i==5)candidates.pop_back();if(i==6)candidates.clear();
  publish(&actor,i==3?&actor:i==4?&ally:i==7?nullptr:&enemy,i!=0,i==2?"frost":"fire",candidates);
  std::cout<<(candidates.empty()?"null":candidates.front().ObservationJson)<<'\n';}
 std::vector<BotActionCandidate> yes{{123,"{}"},{11129,"{}"}};actor.klass=CLASS_MAGE;publish(&actor,&enemy,true,"fire",yes);
 std::cout<<yes.front().ObservationJson<<'\n'<<yes.back().ObservationJson<<'\n';}
'''
    rows = list(map(json.loads, compile_run(tmp_path, body)))
    assert rows[:8] == [{'frost': True}] * 6 + [None, {'frost': True}]
    assert rows[8]['schema'] == 'fire_combustion_candidate_observation_v1'
    assert rows[9] == {}


def test_numeric_extremes_nonfinite_and_missing_period_remain_bounded(tmp_path):
    lines = compile_run(tmp_path, r'''
#include <limits>
int main(){
 using namespace BotFireCombustionObservation;
 Snapshot s;s.EvaluationStartedAtMs=s.ObservedAtMs=UINT64_MAX;s.ActorGuid=s.TargetGuid=s.TargetEntry=s.Race=UINT32_MAX;
 s.ActorAvailable=s.TargetAvailable=s.CombustionAvailable=s.PeriodicAvailable=s.RawScalingAvailable=true;
 s.IgnitePresent=s.IgniteEffect0Present=true;s.IgniteAmount=INT32_MIN;
 s.SummedBasePoints=INT64_MIN;s.EligibleComponentCount=UINT32_MAX;
 s.PeriodicEffectIndex=s.DurationMs=s.PeriodMs=s.HastedPeriodMs=s.TickCount=INT32_MIN;
 s.ScalingPercent=s.HasteMod=s.FireCritPct=s.TargetSpellCritPct=s.TargetAllCritPct=s.SpellCritMultiplier=s.FireCritDamageMultiplier=-std::numeric_limits<float>::max();
 s.EstimatedTotal=-std::numeric_limits<double>::max();s.EstimateAvailable=true;
 for(auto& b:s.Buffs)b={true,INT32_MIN};
 for(int i=0;i<8;++i)s.Components.push_back({UINT32_MAX,UINT32_MAX,INT32_MIN,INT32_MIN});
 std::cout<<ToJson(s)<<'\n';
 Player actor;Unit target;
 manager.periodic.haste=std::numeric_limits<float>::quiet_NaN();
 std::cout<<ToJson(Capture(&actor,&target,1000,1002))<<'\n';
 manager.periodic.haste=.8f;manager.periodic.Effects[1].ApplyAuraName=0;
 std::cout<<ToJson(Capture(&actor,&target,1000,1002))<<'\n';
}
''')
    extreme, nonfinite, missing = map(json.loads, lines)
    assert all(len(line.encode()) <= 2048 for line in lines)
    assert extreme['eligible_component_count'] == 2**32 - 1
    assert extreme['summed_base_points'] == -(2**63)
    assert extreme['components_truncated']
    assert len(extreme['components']) <= 8
    assert nonfinite['periodic']['haste_mod'] is None
    assert nonfinite['estimated_total'] is None
    assert missing['periodic']['effect_index'] == -1
    assert missing['estimated_total'] is None


def test_static_raw_scale_and_dynamic_scaling_fail_closed_without_preview_apis(tmp_path):
    # SpellEffect.dbc native row 4721 / 11129 effect 0: script effect 77,
    # base 100, die sides 0, level/resource coefficients 0. The fixture's
    # class-mask predicate is independently exercised above; no DBC hydration.
    lines = compile_run(tmp_path, r'''
int main(){Player actor;actor.guid=30006;Unit target;SpellInfo info;info.Id=12654;
 AuraEffect effect{&info,30006,0,12000};target.effects.push_back(&effect);
 for(int i=0;i<10;++i){manager=SpellMgr();auto& e=manager.combustion.Effects[0];
  if(i==1)e.DieSides=1;if(i==2)e.RealPointsPerLevel=.1f;if(i==3)e.PointsPerComboPoint=.1f;
  if(i==4)e.Scaling.Coefficient=.1f;if(i==5)e.Scaling.Variance=.1f;if(i==6)e.Scaling.ComboPointsCoefficient=.1f;
  if(i==7)manager.combustion.attributes=SPELL_ATTR8_MASTERY_AFFECTS_POINTS;
  if(i==8)manager.combustion.attributes=SPELL_ATTR1_FINISHING_MOVE_DAMAGE;
  if(i==9)e.Effect=2;
  std::cout<<BotFireCombustionObservation::ToJson(BotFireCombustionObservation::Capture(&actor,&target,1000,1002))<<'\n';}
}
'''.replace(';if(', ';\n  if('))
    static, *dynamic = map(json.loads, lines)
    assert static['scaling_percent'] == 100
    assert static['summed_base_points'] == 12000
    assert static['estimated_total'] is not None
    assert static['native_exact'] is False
    for observation in dynamic:
        assert observation['available']['raw_scale'] is False
        assert observation['scaling_percent'] is None
        assert observation['summed_base_points'] is None
        assert observation['estimated_total'] is None
        assert observation['eligible_component_count'] == 1
        assert observation['components'] == [[12654, 0, 12000, None]]
    source = (BOTS / 'BotFireCombustionObservation.cpp').read_text()
    for forbidden in ('CalculateSpellDamage(', 'CalcValue(', 'CalcBaseValue(', 'ApplySpellMod(', 'GetSpellModValues(',
                      'SpellCritChanceDone(', 'CalcPeriod(', 'CalcDuration(', 'SpellCriticalDamageBonus('):
        assert forbidden not in source
