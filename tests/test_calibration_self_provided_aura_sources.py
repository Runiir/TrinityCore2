"""Compile the actual observation caller against deterministic native aura doubles."""
from pathlib import Path
import re
import json
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_actual_reference_observer_attributes_every_wrath_air_application(tmp_path):
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp").read_text()
    start = source.index("void BotWorldPopulationMgr::ObserveCalibrationReferenceConditions(")
    end = source.index("\nvoid BotWorldPopulationMgr::UpdateCalibrationTargetHealthSchedule", start)
    observer = source[start:end]
    reset_source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationReset.cpp").read_text()
    reset_start = reset_source.index("            auto const selfProvidedPlayerAuras =")
    reset_end = reset_source.index("            bool const selfProvidedConsumablesReady", reset_start)
    reset = reset_source[reset_start:reset_end]
    assert "&& metrics.PreScoreSelfProvidedPlayerAurasCompatible" in reset_source
    assert "&& metrics.PreScoreSelfProvidedTargetAurasAbsent" in reset_source
    pre_score_json = (ROOT / "src/server/game/Bots/BotCalibrationPreScoreStateJson.h").read_text()
    fields = sorted(set(re.findall(r"metrics(?:\.|->)([A-Za-z0-9_]+)", observer + reset + pre_score_json)))
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationMetrics.h").read_text()
    metrics = "\n".join(
        re.search(rf"(bool|std::string|uint\d+|std::map<uint32, uint32>) {field}\b", header)[0] + "{};"
        for field in fields)
    json_source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationReferenceJson.cpp").read_text()
    json_start = json_source.index("            std::set<uint32> observedPlayerAuraSpellIds;")
    json_end = json_source.index('            json << "],\\\"target_auras', json_start)
    serializer = json_source[json_start:json_end]
    cpp = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
#include <sstream>
#include <iostream>
#include <set>
using uint32=uint32_t; using uint64=uint64_t; using uint8=uint8_t;
#include "Bots/BotCalibrationSelfProvidedAuras.h"
#include "Bots/BotCalibrationPreScoreStateJson.h"
struct Guid { uint64 value; bool IsEmpty() const { return !value; } operator uint64() const { return value; } };
struct Unit;
struct Aura { Unit* caster; uint64 guid; Unit* GetCaster() const { return caster; }
Guid GetCasterGUID() const { return {guid}; } uint8 GetStackAmount() const { return 1; } };
struct AuraApplication { Aura* aura; Aura* GetBase() const { return aura; } };
struct Unit {
 uint32 created=3738; uint32 GetUInt32Value(int) const { return created; }
 uint64 guid=1; bool totem=false; Unit* owner=nullptr;
 std::multimap<uint32,AuraApplication*> auras;
 bool HasAura(uint32 id) const { return auras.count(id); }
 auto const& GetAppliedAuras() const { return auras; }
 bool IsTotem() const { return totem; } Unit* ToTotem() { return this; }
 Unit* GetOwner() { return owner; } uint64 GetGUID() const { return guid; }
 Aura* GetAura(uint32 id, uint64 caster) const {
  auto range=auras.equal_range(id); for(auto i=range.first;i!=range.second;++i)
   if(i->second && i->second->aura && i->second->aura->guid==caster) return i->second->aura;
  return nullptr;
 }
};
struct Player:Unit { int tree=261; int GetActiveSpec() const { return 0; }
 int GetPrimaryTalentTree(int) const { return tree; } int classId=7; int getClass() const { return classId; }
 bool known=true; bool HasSpell(uint32) const { return known; }
 uint32 GetLastPotionId() const { return 0; } };
struct CalibrationMetrics { METRICS };
struct BotWorldPopulationMgr {
 struct State { std::string CalibrationTargetSpec="elemental_shaman"; } state;
 State const& Cohort() const { return state; }
 char const* GetDungeonRole(Player*) const { return "dps"; }
 bool IsSelfProvidedCalibrationBaseline() const { return true; }
 void ObserveCalibrationReferenceConditions(CalibrationMetrics&,Player*,Unit*,uint64) const;
 void ObservePreScore(CalibrationMetrics& metrics,Player* bot,Unit* fixtureTarget) const {
 RESET
 }
};
OBSERVER
std::string serialize(CalibrationMetrics const* metrics) {
 std::ostringstream json; json << "[";
 SERIALIZER
 json << "]"; return json.str();
}
int main() {
 BotWorldPopulationMgr manager; Player player; Unit target, other;
 target.guid=2; other.guid=3;
 Unit ownTotem, foreignTotem, unresolvedTotem;
 ownTotem.totem=foreignTotem.totem=unresolvedTotem.totem=true;
 ownTotem.owner=&player; foreignTotem.owner=&other;
 Aura own{&ownTotem,10}, foreign{&foreignTotem,11}, unknown{nullptr,12};
 Aura unresolved{&unresolvedTotem,13}, direct{&player,1};
 AuraApplication a{&own}, b{&foreign}, c{&unknown}, d{&unresolved}, e{&direct};
 Aura emptyGuid{&player,0}; AuraApplication emptyGuidApplication{&emptyGuid};
 auto observe=[&]() { CalibrationMetrics m; manager.ObserveCalibrationReferenceConditions(m,&player,&target,100);
 manager.ObservePreScore(m,&player,&target);
 assert(m.PreScoreSelfProvidedPlayerAurasCompatible == !m.UnexpectedSelfProvidedPlayerAuraActiveSamples);
 assert(m.PreScoreSelfProvidedTargetAurasAbsent == !m.UnexpectedSelfProvidedTargetAuraActiveSamples);
 return m; };
 // Recorded first broken predicate: an already-active native Mage alternate buff.
 player.classId=CLASS_MAGE; manager.state.CalibrationTargetSpec="fire_mage";
 player.auras.emplace(79058,&e);
 assert(observe().PreScoreSelfProvidedPlayerAurasCompatible);
 player.auras.clear(); player.classId=CLASS_SHAMAN;
 manager.state.CalibrationTargetSpec="elemental_shaman";
 auto m=observe(); assert(m.ReferencePlayerAuraInactiveSamples[2895]==1);
 player.auras.emplace(2895,&a); m=observe();
 assert(m.ReferenceWrathOfAirOwnTotemSamples==1 && m.UnexpectedSelfProvidedPlayerAuraActiveSamples==0);
 // Repeated actual samples, including the allowed native totem startup gap.
 CalibrationMetrics window;
 player.auras.clear(); for(int i=0;i<12;++i) manager.ObserveCalibrationReferenceConditions(window,&player,&target,100+i);
 player.auras.emplace(2895,&a); for(int i=0;i<589;++i) manager.ObserveCalibrationReferenceConditions(window,&player,&target,112+i);
 assert(window.ReferenceConditionSampleCount==601 && window.ReferenceWrathOfAirOwnTotemSamples==589);
 assert(window.ReferencePlayerAuraActiveSamples[2895]==589 && window.ReferencePlayerAuraInactiveSamples[2895]==12);
 player.auras.emplace(2895,&b); m=observe();
 assert(m.ReferenceWrathOfAirOwnTotemSamples==0 && m.ReferenceWrathOfAirForeignSourceSamples==1 && m.UnexpectedSelfProvidedPlayerAuraActiveSamples==1);
 player.auras.emplace(2895,&c); m=observe();
 assert(m.ReferenceWrathOfAirUnknownSourceSamples==1 && m.ReferenceWrathOfAirForeignSourceSamples==0 && m.ReferenceWrathOfAirOwnTotemSamples==0);
 for(auto app:{&c,&d,static_cast<AuraApplication*>(nullptr)}) {
  player.auras.clear(); player.auras.emplace(2895,app); m=observe();
  assert(m.ReferenceWrathOfAirUnknownSourceSamples==1 && m.UnexpectedSelfProvidedPlayerAuraActiveSamples==1);
 }
 player.auras.clear(); player.auras.emplace(2895,&e); m=observe();
 assert(m.ReferenceWrathOfAirForeignSourceSamples==1 && m.UnexpectedSelfProvidedPlayerAuraActiveSamples==1);
 player.auras.clear(); player.auras.emplace(2895,&a);
 player.classId=8; assert(observe().UnexpectedSelfProvidedPlayerAuraActiveSamples==1);
 player.classId=7; player.tree=263; assert(observe().UnexpectedSelfProvidedPlayerAuraActiveSamples==1);
 player.tree=261; ownTotem.created=8512; m=observe(); assert(m.ReferenceWrathOfAirForeignSourceSamples==1 && m.UnexpectedSelfProvidedPlayerAuraActiveSamples==1);
 ownTotem.created=0; m=observe(); assert(m.ReferenceWrathOfAirUnknownSourceSamples==1 && m.UnexpectedSelfProvidedPlayerAuraActiveSamples==1);
 ownTotem.created=3738; manager.state.CalibrationTargetSpec="enhancement_shaman";
 assert(observe().UnexpectedSelfProvidedPlayerAuraActiveSamples==1);
 manager.state.CalibrationTargetSpec="elemental_shaman";
 for(uint32 spell:{8076,8515}) { player.auras.emplace(spell,&a); assert(observe().UnexpectedSelfProvidedPlayerAuraActiveSamples==1); player.auras.erase(spell); }
 // Same-class native setup: primary/alternate Mage and Paladin contract rows.
 player.auras.clear(); player.classId=CLASS_MAGE; manager.state.CalibrationTargetSpec="fire_mage";
 player.auras.emplace(79058,&e); m=observe();
 assert(m.PreScoreSelfProvidedPlayerAurasCompatible && !m.PreScoreSelfProvidedPlayerAuraSpellId);
 // Already-active self buff stays admissible across observations; no cast receipt/recast requirement.
 for(int i=0;i<3;++i) assert(observe().PreScoreSelfProvidedPlayerAurasCompatible);
 player.known=false; m=observe(); assert(!m.PreScoreSelfProvidedPlayerAurasCompatible);
 assert(m.PreScoreSelfProvidedPlayerAuraSource=="not_class_setup"); player.known=true;
 for(auto app:{&b,&c,&emptyGuidApplication,static_cast<AuraApplication*>(nullptr)}) {
  player.auras.clear(); player.auras.emplace(79058,app); m=observe();
  assert(!m.PreScoreSelfProvidedPlayerAurasCompatible && m.PreScoreSelfProvidedPlayerAuraSpellId==79058);
 }
 player.auras.clear(); player.auras.emplace(79058,&e); player.auras.emplace(79058,&b);
 m=observe(); assert(m.PreScoreSelfProvidedPlayerAuraSource=="foreign_source");
 std::string failedJson=BotCalibrationPreScoreStateJson(&m);
 player.auras.erase(79058); player.auras.emplace(79058,&e); player.auras.emplace(79058,&c);
 assert(observe().PreScoreSelfProvidedPlayerAuraSource=="unknown_source");
 player.auras.clear(); player.auras.emplace(8076,&e); m=observe();
 assert(m.PreScoreSelfProvidedPlayerAuraSource=="not_class_setup");
 player.classId=CLASS_PALADIN; manager.state.CalibrationTargetSpec="retribution_paladin";
 for(uint32 id:{20217,79063}) { player.auras.clear();player.auras.emplace(id,&e);assert(observe().PreScoreSelfProvidedPlayerAurasCompatible); }
 player.auras.clear(); player.auras.emplace(79058,&e); assert(!observe().PreScoreSelfProvidedPlayerAurasCompatible);
 player.auras.clear();target.auras.emplace(1490,&e); m=observe();
 assert(!m.PreScoreSelfProvidedTargetAurasAbsent && m.PreScoreSelfProvidedTargetAuraSpellId==1490);
 assert(m.PreScoreSelfProvidedTargetAuraSource=="forbidden_target_aura");
 std::cout << "[" << failedJson << "," << BotCalibrationPreScoreStateJson(&m) << "," << window.UnexpectedSelfProvidedPlayerAuraActiveSamples << "," << serialize(&window) << "]";
}
'''.replace("RESET", reset).replace("METRICS", metrics).replace("OBSERVER", observer).replace("SERIALIZER", serializer)
    # Only dependency enums are stubbed; contract and classifier headers are compiled verbatim.
    shared = (ROOT / "src/server/shared/SharedDefines.h").read_text()
    classes = shared[shared.index("enum Classes\n"):shared.index("// max+1 for player class")]
    (tmp_path / "SharedDefines.h").write_text("#pragma once\n" + classes)
    (tmp_path / "UpdateFields.h").write_text("#pragma once\nconstexpr int UNIT_CREATED_BY_SPELL=1;\n")
    path = tmp_path / "observer.cpp"
    path.write_text(cpp)
    binary = tmp_path / "observer"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(tmp_path), "-I", str(ROOT / "src/server/game"), str(path), "-o", str(binary)], check=True)
    failed, target_failed, unexpected, rows = json.loads(subprocess.check_output([str(binary)], text=True))
    assert failed["self_provided_player_auras_compatible"] is False
    assert failed["self_provided_player_aura_spell_id"] == 79058
    assert failed["self_provided_player_aura_source"] == "foreign_source"
    assert target_failed["self_provided_target_auras_absent"] is False
    assert target_failed["self_provided_target_aura_spell_id"] == 1490
    assert target_failed["self_provided_target_aura_source"] == "forbidden_target_aura"
    assert unexpected == 0
    row = next(row for row in rows if row["spell_id"] == 2895)
    assert row == {"spell_id": 2895, "active_samples": 589, "inactive_samples": 12,
                   "own_totem_samples": 589, "foreign_source_samples": 0,
                   "unknown_source_samples": 0}
    fixture = runpy.run_path(str(ROOT / "tests/test_phase8_reference_conditions.py"))
    inputs = fixture["_closed_elemental_816_inputs"]()
    raw = inputs["target_observation"]["reference_condition_observation"]
    raw["player_auras"] = [row if old["spell_id"] == 2895 else old for old in raw["player_auras"]]
    raw["unexpected_player_aura_active_samples"] = unexpected
    result = fixture["derive_reference_condition_compatibility"](**inputs)
    assert result["checks"]["runtime_prepull_setup_receipts_valid"] is True
