import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / 'src/server/game/Bots'
SOURCE = BOT / 'BotWorldPopulationMgrCalibrationAuraObservation.cpp'


def test_actual_owner_aura_aggregation_and_serialization(tmp_path):
    metrics = (BOT/'BotWorldPopulationMgrCalibrationMetrics.h').read_text()
    observation = metrics[metrics.index('        struct OwnerAuraObservation'):
                          metrics.index('        EffectiveStatVector ScoringStartPlayerStats;')]
    production = SOURCE.read_text()
    production = production[production.index('namespace\n{'):]
    source = tmp_path/'aura.cpp'
    source.write_text('''
#include <algorithm>
#include <array>
#include <sstream>
#include <string>
#include <iostream>
#include <cassert>
using uint32=unsigned; using uint64=unsigned long long; using int32=int; using uint8=unsigned char;
struct Guid { uint64 value; uint64 GetRawValue()const{return value;} };
struct AuraEffect { unsigned type=290; int amount=5; unsigned GetAuraType()const{return type;} int GetAmount()const{return amount;} };
struct Aura { Guid caster; AuraEffect* effect; Guid GetCasterGUID()const{return caster;} AuraEffect* GetEffect(int)const{return effect;} };
struct AuraApplication { Aura* aura; uint8 mask=1; Aura* GetBase()const{return aura;} uint8 GetEffectMask()const{return mask;} };
struct Pet { Guid GetGUID()const{return {22};} };
struct Player { AuraApplication* howl=nullptr; AuraApplication* mastery=nullptr; AuraApplication* ready=nullptr; AuraApplication* fire=nullptr; Pet pet;
 AuraApplication* GetAuraApplication(unsigned id){return id==24604 ? howl : id==76659 ? mastery : id==82925 ? ready : id==82926 ? fire : nullptr;}
 Guid GetGUID()const{return {11};} Pet* GetPet(){return &pet;} };
class BotWorldPopulationMgr { public:
 struct CalibrationMetrics {
 struct EffectiveStatVector { bool Observed=false; uint64 ObservedAtMs=0; };
''' + observation + '''
 EffectiveStatVector ScoringStartPlayerStats;
 };
 static int statsWalks;
 static void ObserveCalibrationEffectiveStats(Player*,uint64 now,CalibrationMetrics::EffectiveStatVector& stats){++statsWalks;stats={true,now};}
 static void AppendCalibrationEffectiveStatsJson(std::ostringstream& json,CalibrationMetrics::EffectiveStatVector const& stats){json<<"{\\\"observed\\\":"<<(stats.Observed?"true":"false")<<",\\\"observed_at_ms\\\":"<<stats.ObservedAtMs<<"}";}
 static void ObserveCalibrationOwnerAuras(CalibrationMetrics&,Player*,uint64,bool=false);
 static void AppendCalibrationOwnerAurasJson(std::ostringstream&,CalibrationMetrics const*);
};
int BotWorldPopulationMgr::statsWalks=0;
''' + production + '''
int main(){
 using M=BotWorldPopulationMgr; M::CalibrationMetrics metrics; Player owner;
 AuraEffect effect; Aura howl{{22},&effect}, mastery{{11},&effect};
 AuraApplication howlApplication{&howl,1}, masteryApplication{&mastery,1};
 owner.mastery=&masteryApplication; metrics.ScoringStartPlayerStats={true,0};
 M::ObserveCalibrationOwnerAuras(metrics,&owner,0,true);
 assert(M::statsWalks==0);
 owner.howl=&howlApplication; M::ObserveCalibrationOwnerAuras(metrics,&owner,100);
 assert(M::statsWalks==1);
 howl.caster={33}; M::ObserveCalibrationOwnerAuras(metrics,&owner,100);
 M::ObserveCalibrationOwnerAuras(metrics,&owner,90);
 howlApplication.mask=2; owner.ready=&masteryApplication; M::ObserveCalibrationOwnerAuras(metrics,&owner,200);
 howl.caster={11}; howlApplication.mask=1; effect.amount=6;
 owner.ready=nullptr; owner.fire=&masteryApplication; M::ObserveCalibrationOwnerAuras(metrics,&owner,300);
 howl.caster={0}; howl.effect=nullptr; owner.fire=nullptr; M::ObserveCalibrationOwnerAuras(metrics,&owner,400);
 owner.howl=nullptr; M::ObserveCalibrationOwnerAuras(metrics,&owner,500);
 owner.howl=&howlApplication; howl.caster={22}; howl.effect=&effect; effect.type=291; effect.amount=4;
 M::ObserveCalibrationOwnerAuras(metrics,&owner,600);
 M::ObserveCalibrationOwnerAuras(metrics,nullptr,700);
 assert(M::statsWalks==3);
 std::ostringstream json; json<<"{\\\"fixture\\\":true";
 M::AppendCalibrationOwnerAurasJson(json,&metrics); json<<"}"; std::cout<<json.str()<<"\\n";
 for(uint64 now=700;now<=300000;now+=100) M::ObserveCalibrationOwnerAuras(metrics,&owner,now);
 assert(M::statsWalks==3 && metrics.OwnerAuraObservations.size()==4);
 std::ostringstream full; full<<"{\\\"fixture\\\":true"; M::AppendCalibrationOwnerAurasJson(full,&metrics);full<<"}";
 assert(full.str().size()<json.str().size()+300);
 std::ostringstream empty;empty<<"{\\\"fixture\\\":true";M::AppendCalibrationOwnerAurasJson(empty,nullptr);empty<<"}";std::cout<<empty.str()<<"\\n";
}
''')
    binary = tmp_path/'aura'
    subprocess.run(['c++','-std=c++17',str(source),'-o',str(binary)],check=True)
    lines = subprocess.check_output([str(binary)],text=True).splitlines()
    observed, empty = [json.loads(line)['owner_aura_observation'] for line in lines]
    assert observed['scoring_start_stats_path'] == 'scoring_start_stats.player'
    howl, mastery, ready, fire = observed['auras']
    assert [row['spell_id'] for row in observed['auras']] == [24604, 76659, 82925, 82926]
    assert (howl['sample_count'],howl['active_samples'],howl['inactive_samples']) == (7,5,2)
    assert howl['non_increasing_timestamp_samples'] == 2
    assert (howl['first_sample_at_ms'],howl['last_sample_at_ms'],howl['maximum_sample_gap_ms']) == (0,600,100)
    assert not howl['scoring_start_active'] and howl['scoring_start_observed']
    assert (howl['first_active_at_ms'],howl['last_active_at_ms']) == (100,600)
    assert (howl['activation_transition_count'],howl['deactivation_transition_count']) == (2,1)
    assert (howl['owner_caster_samples'],howl['primary_pet_caster_samples'],howl['other_or_missing_caster_samples']) == (1,2,2)
    assert (howl['first_caster_guid'],howl['last_caster_guid']) == (22,22)
    assert (howl['effect0_samples'],howl['missing_effect0_samples']) == (3,2)
    assert (howl['minimum_aura_type'],howl['maximum_aura_type'],howl['minimum_amount'],howl['maximum_amount']) == (290,291,4,6)
    assert howl['first_active_stats']['observed_at_ms'] == 100
    assert mastery['scoring_start_active'] and mastery['scoring_start_caster_guid'] == 11
    assert mastery['scoring_start_effect0_present'] and mastery['scoring_start_active_effect_mask'] == 1
    assert mastery['scoring_start_aura_type'] == 290 and mastery['scoring_start_amount'] == 5
    assert mastery['first_active_stats']['observed_at_ms'] == 0
    for row, at_ms in ((ready, 200), (fire, 300)):
        assert row['sample_count'] == 7 and row['active_samples'] == 1
        assert row['inactive_samples'] == 6 and not row['scoring_start_active']
        assert row['owner_caster_samples'] == 1
        assert row['activation_transition_count'] == row['deactivation_transition_count'] == 1
        assert row['first_active_at_ms'] == row['last_active_at_ms'] == at_ms
        assert row['first_active_stats']['observed_at_ms'] == at_ms
    assert all(row['sample_count']==0 for row in empty['auras'])


def test_observer_has_start_update_close_and_shared_row_serializer_hooks():
    for name in ('BotWorldPopulationMgrCalibrationReset.cpp','BotWorldPopulationMgrCalibrationBot.cpp',
                 'BotWorldPopulationMgrCalibrationCompletion.cpp'):
        assert 'ObserveCalibrationOwnerAuras(' in (BOT/name).read_text()
    reset = (BOT/'BotWorldPopulationMgrCalibrationReset.cpp').read_text()
    assert reset.index('metrics.ScoringStartPlayerStats);') < reset.index('ObserveCalibrationOwnerAuras(')
    rows = (BOT/'BotWorldPopulationMgrCalibrationRows.cpp').read_text()
    assert rows.count('AppendCalibrationOwnerAurasJson(json, metrics)') == 1
    assert SOURCE.name in (ROOT/'src/server/game/CMakeLists.txt').read_text()
    assert SOURCE.read_text().startswith('#include "Common.h"\n')
    for token in ('CastSpell(', 'AddAura(', 'RemoveAura(', 'RefreshDuration(', 'DecisionTimeline'):
        assert token not in SOURCE.read_text()
    for name in (SOURCE.name,'BotWorldPopulationMgr.h','BotWorldPopulationMgrCalibrationMetrics.h',
                 'BotWorldPopulationMgrCalibrationReset.cpp','BotWorldPopulationMgrCalibrationBot.cpp',
                 'BotWorldPopulationMgrCalibrationCompletion.cpp','BotWorldPopulationMgrCalibrationRows.cpp'):
        assert len((BOT/name).read_text().splitlines()) < 1000
