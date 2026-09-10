"""Actual callback and retained trace payload; native dependencies are value stubs."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_native_finish_callback_retained_observation(tmp_path):
    source = (ROOT / 'src/server/game/Bots/BotWorldPopulationMgrSemantic.cpp').read_text()
    callback = source[source.index('void BotWorldPopulationMgr::NotifyBotSpellFinished('):source.index('void BotWorldPopulationMgr::NotifyBotItemSpellFinished(')]
    cpp = r'''
#include <array>
#include <algorithm>
#include <cstdint>
#include <vector>
#include <map>
#include <string>
#include <sstream>
#include <iostream>
using uint32=uint32_t;using uint64=uint64_t;
uint64 NowMs(){return 1788917145824ULL;}
std::string JsonEscape(std::string const& s){return s;}
struct ObjectGuid{uint64 raw=0;uint64 GetRawValue()const{return raw;}uint32 GetCounter()const{return raw;}bool operator!=(ObjectGuid const& b)const{return raw!=b.raw;}bool operator==(ObjectGuid const& b)const{return raw==b.raw;}};
struct SpellInfo{uint32 Id=133;};struct Targets{ObjectGuid guid{42347};ObjectGuid GetUnitTargetGUID()const{return guid;}};
struct Spell{SpellInfo info;Targets m_targets;uint32 state=3;SpellInfo const* GetSpellInfo()const{return &info;}uint32 getState()const{return state;}};
constexpr int POWER_MANA=0,CURRENT_GENERIC_SPELL=0,CURRENT_CHANNELED_SPELL=1,CURRENT_AUTOREPEAT_SPELL=2;
struct Threat{float GetThreat(){return 7;}};struct ThreatManager{std::map<int,Threat*> refs;auto const& GetThreatenedByMeList(){return refs;}};
struct Player{ObjectGuid guid{30006};Spell* current[3]={};ThreatManager threat;ObjectGuid GetGUID()const{return guid;}uint32 GetMapId(){return 669;}uint32 GetInstanceId(){return 2;}Spell* GetCurrentSpell(int slot){return current[slot];}int GetPower(int){return 123;}ThreatManager& GetThreatManager(){return threat;}};
struct WorldBotState{
 ObjectGuid Guid{30006};uint32 ValidationRouteGeneration=4;uint64 TraceSequence=0;
 struct NativePersistentPetSetupReceipt{uint32 RequiredSummonSpellId=0;uint64 NativeCastSubmittedAtMs=0,NativeCastFinishedAtMs=0,NativeCastObservedAtMs=0,PreScoreResummonRequestedAtMs=0,PreScoreResummonSubmittedAtMs=0,PreScoreResummonObservedAtMs=0,PreScoreResummonFinishedAtMs=0;bool NativeCastFinishedSuccessfully=false,PreScoreResummonFailed=false,PreScoreResummonFinishedSuccessfully=false;} PersistentPetSetup;
 struct Entry{std::string NativeSpellFinishJson,Result,Action;uint64 Sequence=0;};std::vector<Entry> DecisionTrace;
};
struct PendingHealCast{ObjectGuid BotGuid{30006};uint32 SpellId=133;uint64 StartedAtMs=1,FinishedAtMs=0,DeadlineMs=0;bool SpellFinished=false;int ManaAfterCast=0;uint32 AttackersAfterCast=0;float ThreatAfterCast=0;};
struct BotWorldPopulationMgr{
 struct CohortScope{bool valid;explicit operator bool()const{return valid;}};bool scoped=true,declineTrace=false;
 struct Metrics{uint32 ScoredRacialUseCount=0,ScoredTinkerSpellUseCount=0;};
 struct CohortData{bool CalibrationActive=false,CalibrationWindowComplete=false;uint64 CalibrationScoredStartedMs=0,AttemptId=1;std::string Id="default";struct{uint32 WipeGeneration=0;}Raid;struct{std::string ValidationRouteNodeId="bwd.magmaw.encounter";}Config;std::map<uint32,Metrics> CalibrationMetricsByGuid;}cohort;
 struct PartyData{std::vector<WorldBotState>Bots{WorldBotState{}},CalibrationBots;std::map<int,PendingHealCast>PendingHealCasts;uint32 ValidationRouteGeneration=4;}party;
 uint64 _serverEpoch=11023397024538487ULL;int flushed=0;
 CohortScope ScopeCallbackCohort(Player*){return {scoped};}CohortData& Cohort(){return cohort;}PartyData& Party(){return party;}
 void RecordDecisionTrace(WorldBotState& s,char const*,char const*,void const*,uint32,char const* result,char const*,bool=false){if(declineTrace)return;s.DecisionTrace.push_back({"",result,"native_spell_finished",++s.TraceSequence});}
 void FlushPendingHealCast(PendingHealCast const&,Player*,char const*,char const*){++flushed;}
 void NotifyBotSpellFinished(Player*,uint32,bool);
};
'''+callback+r'''
int main(){
 BotWorldPopulationMgr mgr;Player caster;Spell original;caster.current[0]=&original;
 mgr.party.Bots[0].PersistentPetSetup.RequiredSummonSpellId=133;mgr.party.Bots[0].PersistentPetSetup.NativeCastSubmittedAtMs=1;
 mgr.party.PendingHealCasts[1]={};mgr.NotifyBotSpellFinished(&caster,133,true);
 if(!mgr.party.PendingHealCasts[1].SpellFinished || !mgr.party.Bots[0].PersistentPetSetup.NativeCastFinishedSuccessfully)return 2;
 original.info.Id=116;mgr.NotifyBotSpellFinished(&caster,133,false);
 if(mgr.flushed!=1 || !mgr.party.PendingHealCasts.empty())return 3;
 caster.current[0]=nullptr;mgr.NotifyBotSpellFinished(&caster,133,true);
 // Same spell ID cannot prove callback/current cast object identity.
 original.info.Id=133;original.m_targets.guid.raw=999;caster.current[0]=&original;mgr.NotifyBotSpellFinished(&caster,133,false);
 auto before=mgr.party.Bots[0].DecisionTrace.back().NativeSpellFinishJson;
 mgr.declineTrace=true;mgr.NotifyBotSpellFinished(&caster,116,true);mgr.declineTrace=false;
 if(mgr.party.Bots[0].DecisionTrace.back().NativeSpellFinishJson!=before)return 5;
 auto n=mgr.party.Bots[0].DecisionTrace.size();mgr.scoped=false;mgr.NotifyBotSpellFinished(&caster,133,true);mgr.scoped=true;
 mgr.NotifyBotSpellFinished(nullptr,133,true);mgr.NotifyBotSpellFinished(&caster,0,true);caster.guid.raw=40000;mgr.NotifyBotSpellFinished(&caster,133,true);
 if(mgr.party.Bots[0].DecisionTrace.size()!=n)return 4;
 mgr.party.Bots[0].DecisionTrace.push_back({}); // ordinary trace has no finish observation
 for(auto const& row:mgr.party.Bots[0].DecisionTrace)
  std::cout<<(row.NativeSpellFinishJson.empty()?"null":row.NativeSpellFinishJson)<<'\n';
}
'''
    path=tmp_path/'callback.cpp';path.write_text(cpp);binary=tmp_path/'callback'
    built=subprocess.run(['c++','-std=c++17',str(path),'-o',str(binary)],capture_output=True,text=True)
    assert built.returncode==0,built.stderr
    run=subprocess.run([str(binary)],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    callback_rows = list(map(json.loads, run.stdout.splitlines()))
    assert len(callback_rows) == 5

    payloads = ",\n".join(
        json.dumps("" if row is None else json.dumps(row, separators=(",", ":")))
        for row in callback_rows
    )
    encoder_cpp = r'''
#include "Bots/BotWorldPopulationMgrDecisionTraceJson.h"
#include <iostream>
#include <sstream>
#include <string>

namespace BotWorldMovement
{
std::string MovementPlannerObservationJson(MovementPlannerObservation const&)
{
    return "{}";
}
}

using BotWorldPopulationMgrBotState::WorldBotState;

std::string Encode(WorldBotState::DecisionTraceEntry const& entry)
{
    std::ostringstream json;
    BotWorldTrace::AppendDecisionTraceEntryJson(json, entry,
        [](std::string const& value) { return value; },
        [](WorldBotState::CombatAttemptDiagnostic const&) { return "{}"; },
        [](WorldBotState::RouteProgressDiagnostic const&) { return "{}"; });
    return json.str();
}

int main()
{
    char const* payloads[] = {
''' + payloads + r'''
    };
    for (bool delta : {false, true})
    {
        (void)delta;
        for (char const* payload : payloads)
        {
            WorldBotState::DecisionTraceEntry row;
            row.NativeSpellFinishJson = payload;
            std::cout << Encode(row) << '\n';
        }
    }
}
'''
    encoder_path = tmp_path / "native_finish_encoder.cpp"
    encoder_binary = tmp_path / "native_finish_encoder"
    encoder_path.write_text(encoder_cpp, encoding="utf-8")
    encoded_build = subprocess.run(
        [
            "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            "-I", str(ROOT / "dep/g3dlite/include"),
            str(encoder_path), "-o", str(encoder_binary),
        ],
        capture_output=True, text=True,
    )
    assert encoded_build.returncode == 0, encoded_build.stderr
    encoded_run = subprocess.run(
        [str(encoder_binary)], capture_output=True, text=True
    )
    assert encoded_run.returncode == 0, encoded_run.stderr
    exported = list(map(json.loads, encoded_run.stdout.splitlines()))
    full, delta = exported[:5], exported[5:]
    assert len(full)==len(delta)==5
    assert all('native_spell_finish' in row for row in delta)
    assert full == delta
    rows=[row['native_spell_finish'] for row in full]
    assert rows.pop() is None
    assert len(rows)==4
    assert [r['success'] for r in rows]==[True,False,True,False]
    for r in rows:
        assert r['caster_guid']==30006 and r['spell_id']==133
        assert r['observed_at_ms']==1788917145824
        assert r['attempt_id']==1 and r['server_epoch']==11023397024538487
        assert r['route_generation']==4 and r['cohort_id']=='default'
        assert r['wipe_generation']==0 and r['route_node_id']=='bwd.magmaw.encounter'
        assert r['map_id']==669 and r['instance_id']==2
        assert r['cast_instance_correlation']=='unavailable'
    assert rows[0]['current_spells'][0]['spell_id']==133
    assert rows[0]['current_spells'][0]['state']==3
    assert rows[0]['current_spells'][0]['slot']==0
    assert rows[0]['current_spells'][0]['target_guid']==42347
    assert rows[1]['current_spells'][0]['spell_id']==116
    assert rows[2]['current_spells']==[]
    assert rows[3]['current_spells'][0]['target_guid']==999
