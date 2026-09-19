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
#include <deque>
#include <vector>
#include <map>
#include <string>
#include <sstream>
#include <iostream>
#include "Bots/BotWorldTraceExportCursor.h"
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
    struct RetainedRow{uint64 Sequence=0;};
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
     void NotifyBotSpellFinishedWithObservation(Player*,Spell const*,bool);
     void NotifyBotSpellFinishedInternal(Player*,uint32,bool,bool);
     void RecordNativeSpellFinishObservation(Spell const*,bool){}
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
    std::deque<RetainedRow> retained;
    for(uint64 n=1;n<=200;++n){retained.push_back({n});BotWorldTrace::TrimExportedTrace(retained,0);}
    std::vector<uint64> sequences;for(auto const& row:retained)sequences.push_back(row.Sequence);
    auto transition=BotWorldTrace::BuildExportCursorTransition(sequences,0,false,128);
    if(!transition.EntryCount || transition.CursorAfter!=128)return 6;
    for(auto const& row:mgr.party.Bots[0].DecisionTrace)
  std::cout<<(row.NativeSpellFinishJson.empty()?"null":row.NativeSpellFinishJson)<<'\n';
}
'''
    path=tmp_path/'callback.cpp';path.write_text(cpp);binary=tmp_path/'callback'
    built=subprocess.run(['c++','-std=c++17','-I',str(ROOT / 'src/server/game'),str(path),'-o',str(binary)],capture_output=True,text=True)
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
#include "Bots/BotWorldTraceExportCursor.h"
#include <deque>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace BotWorldMovement
{
std::string MovementPlannerObservationJson(MovementPlannerObservation const&)
{
    return "{}";
}
}

using BotWorldPopulationMgrBotState::WorldBotState;
struct CursorRow { std::uint64_t Sequence=0; };

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
    std::vector<WorldBotState::DecisionTraceEntry> entries;
    for (char const* payload : payloads)
    {
        WorldBotState::DecisionTraceEntry row;
        row.NativeSpellFinishJson = payload;
        entries.push_back(row);
    }
    entries.front().NativeSpellPreparedJson =
        "{\"schema\":\"native_spell_prepared_v1\",\"cast_instance_id\":7}";
    WorldBotState::DecisionTraceEntry initialLifecycle;
    initialLifecycle.NativeSpellFinishJson =
        "{\"schema\":\"native_spell_finish_v2\",\"cast_instance_id\":7,"
        "\"terminal_ordinal\":1,\"prepared\":true,\"success\":true}";
    entries.insert(entries.end() - 1, initialLifecycle);
    std::deque<CursorRow> retained;
    for (std::uint64_t sequence=1; sequence<=entries.size(); ++sequence)
    {
        retained.push_back({sequence});
        BotWorldTrace::TrimExportedTrace(retained, 0);
    }
    auto sequenceValues = [&retained]
    {
        std::vector<std::uint64_t> values;
        for (auto const& row : retained)
            values.push_back(row.Sequence);
        return values;
    };
    auto sequences = sequenceValues();
    auto fullTransition = BotWorldTrace::BuildExportCursorTransition(
        sequences, 0, false, 128);
    if (!fullTransition.EntryCount || fullTransition.CursorAfter != entries.size())
        return 2;
    for (std::size_t index=fullTransition.FirstEntryIndex;
         index<fullTransition.FirstEntryIndex+fullTransition.EntryCount; ++index)
        std::cout << Encode(entries[index]) << '\n';

    WorldBotState::DecisionTraceEntry deltaLifecycle;
    deltaLifecycle.NativeSpellPreparedJson =
        "{\"schema\":\"native_spell_prepared_v1\",\"cast_instance_id\":8}";
    deltaLifecycle.NativeSpellFinishJson =
        "{\"schema\":\"native_spell_finish_v2\",\"cast_instance_id\":8,"
        "\"terminal_ordinal\":1,\"prepared\":true,\"success\":false}";
    entries.push_back(deltaLifecycle);
    retained.push_back({static_cast<std::uint64_t>(entries.size())});
    BotWorldTrace::TrimExportedTrace(retained, fullTransition.CursorAfter);
    sequences = sequenceValues();
    auto deltaTransition = BotWorldTrace::BuildExportCursorTransition(
        sequences, fullTransition.CursorAfter, true, 128);
    if (!deltaTransition.EntryCount
        || deltaTransition.CursorAfter != entries.size())
        return 3;
    for (std::size_t index=deltaTransition.FirstEntryIndex;
         index<deltaTransition.FirstEntryIndex+deltaTransition.EntryCount; ++index)
        std::cout << Encode(entries[index]) << '\n';
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
    full, delta = exported[:6], exported[6:]
    assert len(full)==6 and len(delta)==1
    assert all('native_spell_finish' in row for row in full)
    assert all('native_spell_finish' in row for row in delta)
    assert full[0]['native_spell_prepared']['cast_instance_id'] == 7
    assert full[4]['native_spell_finish']['cast_instance_id'] == 7
    assert delta[0]['native_spell_prepared']['cast_instance_id'] == 8
    assert delta[0]['native_spell_finish']['cast_instance_id'] == 8
    assert delta[0]['native_spell_finish']['terminal_ordinal'] == 1
    rows=[row['native_spell_finish'] for row in full]
    assert rows.pop() is None
    assert len(rows)==5
    assert [r['success'] for r in rows[:4]]==[True,False,True,False]
    for r in rows[:4]:
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
    assert rows[4]['terminal_ordinal'] == 1
    assert rows[4]['prepared'] is True


def test_production_observation_transition_preserves_instance_and_terminal_facts(tmp_path):
    cpp = r'''
#include "SpellNativeCastObservation.h"
#include <cassert>
#include <cstdint>
#include <string>
#include <utility>
using uint32=uint32_t;using uint64=uint64_t;
constexpr uint32 SPELL_CAST_OK=0;
struct NativeSpellFixture {
 SpellNativeCastObservation observation;
public:
 void Submitted(ObjectGuid guid) { SpellNativeCastObservationOps::SetSubmittedTarget(observation,guid); }
 void Prepared(std::string scope,uint64 at) { SpellNativeCastObservationOps::MarkPrepared(observation,std::move(scope),at); }
 void Result(uint32 result) { SpellNativeCastObservationOps::RecordResult(observation,result,255); }
 void Update(char const* source,uint32 result=0) { SpellNativeCastObservationOps::MarkUpdate(observation,source,result); }
 void Cancel() { SpellNativeCastObservationOps::MarkCancelled(observation); }
 void Finish(bool success,ObjectGuid target,bool present,bool aliveAvailable,bool alive,
             bool attackabilityAvailable,bool attackable,uint32 prior,std::string scope,uint64 at) {
  SpellNativeCastObservationOps::MarkFinishing(observation,success,target,present,aliveAvailable,alive,
                                               attackabilityAvailable,attackable,prior,std::move(scope),at);
 }
};
int main() {
 NativeSpellFixture first; NativeSpellFixture second;
 NativeSpellFixture rejected; rejected.Result(12);
 assert(!rejected.observation.Prepared && rejected.observation.NativeFailureResultAvailable
        && rejected.observation.LastNativeFailureResult==12);
 for(char const* source : {"update_pointers_failed","target_unavailable","movement_check_failed"}) {
  NativeSpellFixture branch; branch.Update(source); assert(branch.observation.TerminalSource==source);
 }
 first.Submitted(ObjectGuid(HighGuid::Unit,uint32(41570)));
 first.Prepared("{\"route_generation\":4}",100);
 second.Prepared("{\"route_generation\":4}",100);
 second.Finish(true,ObjectGuid(HighGuid::Unit,uint32(41570)),true,true,true,true,true,1,"",100);
 first.Result(17); first.Update("movement_check_failed",55); first.Cancel(); first.Result(19);
 first.Finish(false,ObjectGuid(HighGuid::Unit,uint32(999)),true,true,true,true,true,1,
             "{\"route_generation\":5}",200);
 auto const& a=first.observation; auto const& b=second.observation;
 assert(a.InstanceId!=b.InstanceId); assert(a.Prepared && a.PreparedAtMs==100);
 assert(a.SubmittedTargetGuid.GetRawValue()!=a.TerminalTargetGuid.GetRawValue());
 assert(a.NativeFailureResultAvailable && a.LastNativeFailureResult==19);
 assert(a.MovementCheckAvailable && a.MovementCheckResult==55);
 assert(a.TerminalSource=="movement_check_failed" && a.CancellationOwner=="unknown");
 assert(a.TerminalTargetPresenceAvailable && a.TerminalTargetAliveAvailable && a.TerminalTargetAlive);
 assert(a.PriorState==1 && a.Finished && !a.Success);
 assert(b.Prepared && b.Finished && b.PreparedAtMs==100 && b.FinishedAtMs==100);
 NativeSpellFixture generic; generic.Cancel(); generic.Result(23);
 assert(generic.observation.TerminalSource=="cancel"
        && generic.observation.CancellationOwner=="unknown"
        && generic.observation.LastNativeFailureResult==23);
 NativeSpellFixture repeat; repeat.Prepared("",100);
 repeat.Finish(true,ObjectGuid(HighGuid::Unit,uint32(41570)),true,true,true,true,true,1,"",100);
 repeat.Cancel(); repeat.Finish(false,ObjectGuid(),false,false,false,false,false,5,"",100);
 assert(repeat.observation.TerminalOrdinal==2 && repeat.observation.InstanceId!=0
        && repeat.observation.PriorState==5 && !repeat.observation.Success
        && repeat.observation.TerminalSource=="cancel"
        && !repeat.observation.MovementCheckAvailable);
 NativeSpellFixture direct; direct.Finish(false,ObjectGuid(),false,false,false,false,false,2,"",300);
 auto const& c=direct.observation;
 assert(!c.NativeFailureResultAvailable && c.TerminalSource=="finish");
 assert(c.TerminalTargetPresenceAvailable && !c.TerminalTargetPresent);
 assert(!c.TerminalTargetAliveAvailable && !c.TerminalTargetAttackabilityAvailable);
}
'''
    path = tmp_path / 'native_observation.cpp'
    path.write_text(cpp)
    binary = tmp_path / 'native_observation'
    built = subprocess.run([
        'c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
        '-I', str(ROOT / 'src/common'),
        '-I', str(ROOT / 'src/server/shared'),
        '-I', str(ROOT / 'src/server/game/Entities/Object'),
        '-I', str(ROOT / 'src/server/game/Spells'),
        str(path), str(ROOT / 'src/server/game/Spells/SpellNativeCastObservation.cpp'),
        '-o', str(binary)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr

    spell_source = (ROOT / 'src/server/game/Spells/Spell.cpp').read_text()
    assert spell_source.index('ObserveNativeCastSubmittedTarget(targets.GetUnitTargetGUID())') < spell_source.index('m_spellState = SPELL_STATE_PREPARING')
    assert spell_source.index('NotifyNativeSpellPrepared(this)') < spell_source.index('cast(true);')
    assert spell_source.index('NotifyNativeSpellCastResult(this, uint32(result))') < spell_source.index('result = SPELL_FAILED_DONT_REPORT')
