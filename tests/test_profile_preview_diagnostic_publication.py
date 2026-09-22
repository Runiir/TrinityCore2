"""Passive range selection preserves execution diagnostic ownership."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_actual_resolver_publication_and_passive_call_sites(tmp_path):
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp").read_text()
    start = source.index("    if (publishDiagnostics)")
    publication = source[start:source.index("    if (!best || !best->SpellId)", start)]
    fallback = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text()
    calls = []
    for marker in ("ResolvedCombatAction profileAction = ResolveProfileCombatAction(",
                   "ResolvedCombatAction const preview = ResolveProfileCombatAction("):
        start = fallback.index(marker)
        calls.append(fallback[start:fallback.index(";", start) + 1])
    program = r'''
#include <cassert>
#include <algorithm>
#include <map>
#include <string>
#include <sstream>
#include <vector>
using uint32=unsigned;
struct Guid {uint32 GetCounter()const{return 1;}};
constexpr int CLASS_MAGE=8;
struct Bot {Guid GetGUID(){return {};} int getClass(){return 9;} bool IsValidAttackTarget(void*){return true;}};
namespace BotWorldPopulationMgrSpellSemantics {unsigned NowMs(){return 100;}}
namespace BotBloodDecisionObservation {template<class... T> bool Attach(T&&...){return true;}}
namespace BotFireCombustionObservation {template<class... T> int Capture(T...){return 0;} std::string ToJson(int){return "observation";}}
struct BotActionCandidate {unsigned SpellId=0;std::string RejectReason;int Category=0;std::string ObservationJson;};
struct Saturation {int RecommendedBalanceMode=0;float ExperimentConfidence=0;std::string ToJson(){return "saturation";}};
struct PartyState {
std::map<unsigned,std::string> LastCombatRejectsByBot,LastCombatMaskByBot,LastChosenCombatByBot,LastActionCategoryByBot;
std::map<unsigned,Saturation> LastSaturationByBot;
} party;
PartyState& Party(){return party;}
std::string JsonEscape(std::string value){return value;}
namespace BotCombatMaskEvaluation {
std::string Quote(std::string v){return v;}
std::string Append(std::string a,int,std::string b){return a+b;}
}
namespace BotRoleSaturationPolicy {char const* ToString(int){return "balance";}}
namespace BotCombatActionCatalog {char const* ToString(int v){return v==1?"execution":"preview";}}
namespace BotClassSpecActionProfileStore {
std::string CandidateMaskJson(std::vector<BotActionCandidate> const& c,int,char const*,char const*){return std::to_string(c[0].SpellId);}
std::string ChosenActionJson(BotActionCandidate const* c,int,char const*,char const*,float){return std::to_string(c->SpellId);}
}
struct ResolvedCombatAction {unsigned SpellId;std::string ObservationJson="{}";};
ResolvedCombatAction ResolveProfileCombatAction(Bot* bot,void* target,unsigned hostileCount=0,bool densityOnly=false,
unsigned excludedSpellId=0,bool areaOnly=false,bool selfCenteredOnly=false,bool forbidArea=false,
bool allowMultidot=true,bool hostileTargetOnly=false,bool movementCompatibleOnly=false,
char const* specTagOverride=nullptr,bool publishDiagnostics=true,unsigned policyExcludedSpellId=0){
// Different resolved results emulate execution contract and passive preview.
std::vector<BotActionCandidate> candidates={{forbidArea?101u:202u,forbidArea?"execution_reject":"preview_reject",forbidArea?1:2}};
auto best=&candidates[0];struct Profile{std::string SpecTag="affliction";operator int()const{return 0;}} profile;int maskEvaluation=0,maskEvaluatedAtMs=100;std::string roleGoal="tank";
Saturation saturation;saturation.ExperimentConfidence=forbidArea?1:2;
unsigned requestedHostileCount=hostileCount;
ResolvedCombatAction action{best->SpellId};
''' + publication + r'''
return action;
}
int main(){Bot bot;int unit;auto target=&unit;
struct {Bot* Bot;void* Target;} context{&bot,target};
struct {bool ForbidAreaDamage=false,AllowMultidot=true;} magmawProfile;
unsigned policyExcludedSpellId=603;
auto execution=ResolveProfileCombatAction(&bot,target,0,false,0,false,false,true);
assert(execution.SpellId==101);
auto previous=party;
''' + '\n'.join(calls) + r'''
assert(profileAction.SpellId==202);assert(preview.SpellId==202);
assert(party.LastCombatRejectsByBot==previous.LastCombatRejectsByBot);
assert(party.LastCombatMaskByBot==previous.LastCombatMaskByBot);
assert(party.LastChosenCombatByBot==previous.LastChosenCombatByBot);
assert(party.LastActionCategoryByBot==previous.LastActionCategoryByBot);
assert(party.LastSaturationByBot.at(1).ExperimentConfidence==previous.LastSaturationByBot.at(1).ExperimentConfidence);
auto normal=ResolveProfileCombatAction(&bot,target);
assert(party.LastCombatRejectsByBot!=previous.LastCombatRejectsByBot);
assert(party.LastCombatMaskByBot!=previous.LastCombatMaskByBot);
assert(normal.SpellId==202);assert(party.LastChosenCombatByBot.at(1)=="202");
assert(party.LastActionCategoryByBot.at(1)=="preview");
assert(party.LastSaturationByBot.at(1).ExperimentConfidence==2);
}
'''
    # Keep production call-site member spelling without a C++ type/member clash.
    program = program.replace("struct Bot {", "struct PlayerStub {").replace("Bot*", "PlayerStub*").replace("Bot bot;", "PlayerStub bot;")
    cpp = tmp_path / "preview.cpp"
    cpp.write_text(program)
    binary = tmp_path / "preview"
    subprocess.run(["g++", "-std=c++17", str(cpp), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_blood_selected_action_retains_pre_submission_state(tmp_path):
    bots = ROOT / "src/server/game/Bots"
    candidates_source = (bots / "BotClassSpecActionProfileCandidates.cpp").read_text()
    serializer_start = candidates_source.index(
        "std::string BotClassSpecActionProfileStore::ChosenActionJson(")
    chosen_serializer = candidates_source[serializer_start:]
    diagnostics_source = (bots / "BotWorldPopulationMgrCombatDiagnostics.cpp").read_text()
    attempt_start = diagnostics_source.index(
        "std::string BotWorldPopulationMgr::BuildCombatAttemptJson(")
    attempt_end = diagnostics_source.index(
        "\nstd::string BotWorldPopulationMgr::BuildRouteProgressJson", attempt_start)
    attempt_serializer = diagnostics_source[attempt_start:attempt_end]

    (tmp_path / "Bots").mkdir()
    (tmp_path / "Define.h").write_text(r'''
#pragma once
#include <cstdint>
using uint8=uint8_t;using uint16=uint16_t;using uint32=uint32_t;using uint64=uint64_t;
constexpr uint8 CLASS_DEATH_KNIGHT=6,MAX_RUNES=6;
constexpr int PLAYER_RUNE_REGEN_1=100;
enum class RuneType:uint8 {Blood,Unholy,Frost,Death};
''')
    (tmp_path / "Player.h").write_text(r'''
#pragma once
#include "Define.h"
struct Player {
 uint8 Class=CLASS_DEATH_KNIGHT;uint64 Health=27035,MaximumHealth=188765;
 float Cooldowns[MAX_RUNES]={0,0.5f,1,0.25f,1,0};
 float Regeneration[4]={0.25f,0.5f,0.25f,0.5f};
 RuneType BaseRunes[MAX_RUNES]={RuneType::Blood,RuneType::Blood,RuneType::Unholy,RuneType::Unholy,RuneType::Frost,RuneType::Frost};
 RuneType Runes[MAX_RUNES]={RuneType::Blood,RuneType::Death,RuneType::Unholy,RuneType::Death,RuneType::Frost,RuneType::Death};
 uint8 getClass()const{return Class;}uint64 GetHealth()const{return Health;}uint64 GetMaxHealth()const{return MaximumHealth;}
 RuneType GetBaseRune(uint8 i)const{return BaseRunes[i];}RuneType GetCurrentRune(uint8 i)const{return Runes[i];}
 float GetRuneCooldown(uint8 i)const{return Cooldowns[i];}
 float GetFloatValue(int field)const{return Regeneration[field-PLAYER_RUNE_REGEN_1];}
};
''')
    (tmp_path / "Bots/BotClassSpecActionProfile.h").write_text(r'''
#pragma once
#include "Define.h"
#include <string>
enum class BotCombatActionCategory:uint8 {Wait,Spender};
struct BotActionProfileSpell {uint16 SortOrder=0;uint8 PriorityBucket=0;std::string MechanicTags;float DamageWeight=0,HealingWeight=0,ThreatWeight=0,MitigationWeight=0;};
struct BotActionCandidate {uint32 ActionId=0,SpellId=0;BotCombatActionCategory Category=BotCombatActionCategory::Spender;uint64 TargetGuid=0;uint32 TargetEntry=0;float Score=0;std::string Reason,RejectReason,ObservationJson="{}";BotActionProfileSpell Profile;};
struct BotClassSpecActionProfile {std::string Role="tank";std::string EmbeddingJson()const{return "{\"spec\":\"blood\"}";}};
struct BotCombatActionCatalog {static uint32 StableActionId(BotCombatActionCategory,uint32=0){return 9;}static char const* ToString(BotCombatActionCategory){return "spender";}};
namespace BotClassSpecActionProfileDetail {inline std::string ClassSpecProfileEscape(std::string const& v){return v;}}
struct BotClassSpecActionProfileStore {static std::string ChosenActionJson(BotActionCandidate const*,BotClassSpecActionProfile const&,char const*,char const*,float);};
''')
    program = r'''
#include "Bots/BotBloodDecisionObservation.h"
#include <iostream>
''' + chosen_serializer + r'''
struct ObjectGuid {uint64 Value=0;uint64 GetCounter()const{return Value;}};
struct WorldBotState {struct CombatAttemptDiagnostic {
 uint64 RecordedAtMs=0;std::string Phase,ActionType;uint32 SpellId=0;std::string DebugName;ObjectGuid TargetGuid;uint32 TargetEntry=0;bool SelfTarget=false;std::string Result;
 bool Casting=false,GlobalCooldown=false,CooldownReady=false,KnownSpell=false,HasPower=false,LineOfSight=false,InRange=false,TargetAlive=false,TargetAttackable=false;
 bool MeleeAutoAttacking=false,RangedAutoActive=false;uint32 RangedAutoSpellId=0;ObjectGuid RangedAutoTargetGuid;uint32 RangedAutoTargetEntry=0;bool PetAttacking=false;
 uint32 PetGuid=0,PetEntry=0,PetCurrentGenericSpellId=0,PetVictimGuid=0;std::string Reason,DiagnosticReason,DetailJson="{}",Summary;
};};
struct BotWorldPopulationMgr {static std::string JsonEscape(std::string const& value){return value;}std::string BuildCombatAttemptJson(WorldBotState::CombatAttemptDiagnostic const&)const;};
''' + attempt_serializer + r'''
int main(){
 Player actor;std::vector<BotActionCandidate> candidates(3);
 Player fuzzyActor=actor;fuzzyActor.Cooldowns[0]=0.00005f;
 if(BotBloodDecisionObservation::ObserveReadyRunes(&fuzzyActor).Total!=1)return 1;
 candidates[0].SpellId=48721;candidates[0].ObservationJson="{\"prior\":true}";
 candidates[1].SpellId=49998;candidates[1].Score=1.25f;candidates[1].Profile.PriorityBucket=1;candidates[1].RejectReason="missing_runes";
 candidates[2].SpellId=55050;candidates[2].Score=7.75f;candidates[2].Profile.PriorityBucket=2;candidates[2].Reason="selected";
 std::string actionObservation="{}";
 bool attached=BotBloodDecisionObservation::Attach(&actor,candidates,&candidates[2],"blood_death_knight",1234,"threat_first",actionObservation);
 std::string maskObservation=candidates.front().ObservationJson;
 actor.Health=1;for(float& cooldown:actor.Cooldowns)cooldown=0;
 BotClassSpecActionProfile profile;
 std::cout<<attached<<'\n'<<maskObservation<<'\n'<<actionObservation<<'\n'
          <<BotClassSpecActionProfileStore::ChosenActionJson(&candidates[2],profile,"tank","threat_first",1)<<'\n';
 std::vector<BotActionCandidate> areaSelected(3);
 areaSelected[0].SpellId=48721;areaSelected[0].Score=8.25f;areaSelected[0].Profile.PriorityBucket=0;
 areaSelected[1].SpellId=49998;areaSelected[1].Score=4.25f;areaSelected[1].Profile.PriorityBucket=1;areaSelected[1].RejectReason="missing_runes";
 areaSelected[2].SpellId=55050;areaSelected[2].Score=3.25f;areaSelected[2].Profile.PriorityBucket=1;
 std::string areaObservation="{}";
 std::cout<<BotBloodDecisionObservation::Attach(&actor,areaSelected,&areaSelected[0],"blood_death_knight",1234,"threat_first",areaObservation)<<'\n'
          <<areaObservation<<'\n';
 std::vector<BotActionCandidate> unrelated(1);unrelated[0].SpellId=48721;unrelated[0].ObservationJson="{\"unchanged\":true}";
 std::cout<<BotBloodDecisionObservation::Attach(&actor,unrelated,&unrelated[0],"blood_death_knight",1235,"role_first",actionObservation)<<'\n'
          <<unrelated[0].ObservationJson<<'\n';
 WorldBotState::CombatAttemptDiagnostic attempt;attempt.SpellId=55050;attempt.Phase="cast";attempt.DetailJson=actionObservation;
 std::cout<<BotWorldPopulationMgr().BuildCombatAttemptJson(attempt)<<'\n';
 std::vector<BotActionCandidate> deathSelected(2);deathSelected[0].SpellId=49998;deathSelected[0].Score=9.5f;deathSelected[0].Profile.PriorityBucket=0;
 deathSelected[1].SpellId=55050;deathSelected[1].Score=2.5f;deathSelected[1].Profile.PriorityBucket=3;deathSelected[1].RejectReason="survival_priority";
 std::string deathObservation="{}";
 BotBloodDecisionObservation::Attach(&actor,deathSelected,&deathSelected[0],"blood",1236,"survival_first",deathObservation);
 std::cout<<deathObservation<<'\n';
 std::string frostObservation="{\"frost\":true}",frostAction="{}";deathSelected[0].ObservationJson=frostObservation;
 BotBloodDecisionObservation::Attach(&actor,deathSelected,&deathSelected[0],"frost_death_knight",1237,"role_first",frostAction);
 std::cout<<deathSelected[0].ObservationJson<<'\n';
}
'''
    cpp = tmp_path / "blood_observation.cpp"
    cpp.write_text(program)
    binary = tmp_path / "blood_observation"
    subprocess.run([
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
        "-I", str(tmp_path), "-I", str(ROOT / "src/server/game"),
        str(cpp), "-o", str(binary)
    ], check=True)
    (attached, mask_json, action_json, chosen_json, area_attached, area_json,
     unrelated, unchanged_json, attempt_json, death_json, frost_json) = subprocess.check_output(
        [str(binary)], text=True).splitlines()
    mask = json.loads(mask_json)
    action = json.loads(action_json)
    chosen = json.loads(chosen_json)
    assert attached == "1" and unrelated == "0"
    assert area_attached == "1"
    area = json.loads(area_json)
    assert area["selected_spell_id"] == 48721
    assert area["candidates"]["death_strike"]["reject_reason"] == "missing_runes"
    assert area["candidates"]["heart_strike"]["valid"] is True
    assert json.loads(unchanged_json) == {"unchanged": True}
    assert chosen["observation"] == mask == action
    assert json.loads(attempt_json)["detail"] == action
    assert mask["schema"] == "blood_survival_candidate_observation_v1"
    assert mask["phase"] == "pre_native_submission"
    assert mask["evaluation_started_at_ms"] == 1234
    assert mask["selected_spell_id"] == 55050
    assert mask["selected_mode"] == "threat_first"
    assert mask["health"] == {"current": 27035, "maximum": 188765}
    assert mask["ready_runes"] == {"total": 2, "blood": 1, "unholy": 0, "frost": 0, "death": 1}
    assert mask["rune_slots"] == [
        {
            "slot_index": 0, "base_rune_type": "blood", "current_rune_type": "blood",
            "cooldown_fraction": 0, "regeneration_rate": 0.25,
            "estimated_ready_in_ms": 0, "estimated_ready_at_ms": 1234,
        },
        {
            "slot_index": 1, "base_rune_type": "blood", "current_rune_type": "death",
            "cooldown_fraction": 0.5, "regeneration_rate": 0.5,
            "estimated_ready_in_ms": 1000, "estimated_ready_at_ms": 2234,
        },
        {
            "slot_index": 2, "base_rune_type": "unholy", "current_rune_type": "unholy",
            "cooldown_fraction": 1, "regeneration_rate": 0.5,
            "estimated_ready_in_ms": 2500, "estimated_ready_at_ms": 3734,
        },
        {
            "slot_index": 3, "base_rune_type": "unholy", "current_rune_type": "death",
            "cooldown_fraction": 0.25, "regeneration_rate": 0.5,
            "estimated_ready_in_ms": 500, "estimated_ready_at_ms": 1734,
        },
        {
            "slot_index": 4, "base_rune_type": "frost", "current_rune_type": "frost",
            "cooldown_fraction": 1, "regeneration_rate": 0.25,
            "estimated_ready_in_ms": 4000, "estimated_ready_at_ms": 5234,
        },
        {
            "slot_index": 5, "base_rune_type": "frost", "current_rune_type": "death",
            "cooldown_fraction": 0, "regeneration_rate": 0.5,
            "estimated_ready_in_ms": 0, "estimated_ready_at_ms": 1234,
        },
    ]
    assert mask["candidates"]["death_strike"] == {
        "present": True, "valid": False, "reject_reason": "missing_runes",
        "priority_bucket": 1, "final_score": 1.25,
    }
    assert mask["candidates"]["heart_strike"] == {
        "present": True, "valid": True, "reject_reason": "",
        "priority_bucket": 2, "final_score": 7.75,
    }
    death = json.loads(death_json)
    assert death["selected_spell_id"] == 49998
    assert death["selected_mode"] == "survival_first"
    assert death["candidates"]["death_strike"] == {
        "present": True, "valid": True, "reject_reason": "",
        "priority_bucket": 0, "final_score": 9.5,
    }
    assert death["candidates"]["heart_strike"] == {
        "present": True, "valid": False, "reject_reason": "survival_priority",
        "priority_bucket": 3, "final_score": 2.5,
    }
    assert json.loads(frost_json) == {"frost": True}

    resolver = (bots / "BotWorldPopulationMgrCombatResolver.cpp").read_text()
    attach_at = resolver.index("BotBloodDecisionObservation::Attach(")
    mask_at = resolver.index("Party().LastCombatMaskByBot", attach_at)
    chosen_at = resolver.index("Party().LastChosenCombatByBot", mask_at)
    assert attach_at < mask_at < chosen_at
    execution = (bots / "BotWorldPopulationMgrCombatExecution.cpp").read_text()
    assert "nullptr, action.ObservationJson.c_str());" in execution
    recording = (bots / "BotWorldPopulationMgrEventRecording.cpp").read_text()
    assert "state.LastChosenActionJson = chosenItr" in recording
    assert ',\\"structured_action\\":' in recording
    helper = (bots / "BotBloodDecisionObservation.h").read_text()
    assert "CalculateSpellDamage" not in helper
    assert "ApplySpellMod" not in helper
