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
    assert "&& metrics.PreScoreSelfProvidedTargetAurasCompatible" in reset_source
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
    target_start = json_source.index("            std::set<uint32> observedTargetAuraSpellIds;")
    target_end = json_source.index('            json << "],\\\"target_stacked_auras', target_start)
    target_serializer = json_source[target_start:target_end]
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
 std::set<uint32> unavailableApplications;
 bool HasAura(uint32 id) const { return auras.count(id) || unavailableApplications.count(id); }
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
std::string serializeTargets(CalibrationMetrics const* metrics) {
 struct { struct { uint32 GetCounter() const { return 1304; } } Guid; } state;
 std::ostringstream json; json << "["; bool firstReferenceAura=true;
 TARGET_SERIALIZER
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
 assert(m.PreScoreSelfProvidedTargetAurasCompatible == !m.UnexpectedSelfProvidedTargetAuraActiveSamples);
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
 player.auras.clear(); player.classId=CLASS_MAGE; manager.state.CalibrationTargetSpec="fire_mage";
 player.guid=1304; direct.guid=1304; player.auras.emplace(79058,&e);
 target.auras.emplace(22959,&e);
 assert(observe().PreScoreSelfProvidedTargetAurasCompatible);
 CalibrationMetrics fireWindow;
 for(int i=0;i<601;++i) {
  target.auras.clear(); if(i>=111) target.auras.emplace(22959,&e);
  manager.ObserveCalibrationReferenceConditions(fireWindow,&player,&target,1000+i);
  manager.ObservePreScore(fireWindow,&player,&target);
  assert(fireWindow.PreScoreSelfProvidedTargetAurasCompatible);
 }
 assert(fireWindow.ReferenceTargetAuraActiveSamples[22959]==490);
 assert(fireWindow.ReferenceTargetAuraOwnerMatchSamples[22959]==490);
 assert(!fireWindow.ReferenceTargetAuraOwnerMismatchSamples[22959]);
 assert(!fireWindow.UnexpectedSelfProvidedTargetAuraActiveSamples);
 std::ostringstream badWindows; badWindows << "[";
 bool firstBad=true;
 for(auto app:{&b,&c}) {
  CalibrationMetrics bad;
  for(int i=0;i<601;++i) { target.auras.clear(); target.auras.emplace(22959,app);
   manager.ObserveCalibrationReferenceConditions(bad,&player,&target,1000+i); }
  if(!firstBad) badWindows << ",";
  firstBad=false;
  badWindows << "[" << bad.UnexpectedSelfProvidedTargetAuraActiveSamples << "," << serializeTargets(&bad) << "]";
 }
 CalibrationMetrics mixedWindow;
 target.auras.clear(); target.auras.emplace(22959,&e); target.auras.emplace(22959,&b);
 for(int i=0;i<601;++i) manager.ObserveCalibrationReferenceConditions(mixedWindow,&player,&target,1000+i);
 badWindows << ",[" << mixedWindow.UnexpectedSelfProvidedTargetAuraActiveSamples << "," << serializeTargets(&mixedWindow) << "]]";
 std::ostringstream badPlayerCounts; badPlayerCounts << "[";
 for(int source=0;source<3;++source) {
  player.auras.clear(); player.auras.emplace(79058, source==1 ? &c : &b);
  if(source==2) player.auras.emplace(79058,&e);
  CalibrationMetrics bad;
  for(int i=0;i<601;++i) manager.ObserveCalibrationReferenceConditions(bad,&player,&target,1000+i);
  if(source) badPlayerCounts << ",";
  badPlayerCounts << bad.UnexpectedSelfProvidedPlayerAuraActiveSamples;
 }
 badPlayerCounts << "]"; player.auras.clear();
 Aura forgedGuid{&other,1304}, wrongGuid{&player,42};
 AuraApplication forged{&forgedGuid}, wrong{&wrongGuid}, noBase{nullptr};
 for(uint32 id:{1490,22959,81326,58567}) {
  target.auras.clear(); target.auras.emplace(id,&e);
  assert(observe().PreScoreSelfProvidedTargetAurasCompatible);
  for(auto app:{&b,&c,&forged,&wrong,&noBase,&emptyGuidApplication,static_cast<AuraApplication*>(nullptr)}) {
   target.auras.clear(); target.auras.emplace(id,app);
   m=observe(); assert(!m.PreScoreSelfProvidedTargetAurasCompatible && m.PreScoreSelfProvidedTargetAuraSpellId==id);
   target.auras.emplace(id,&e); // Mixed own/foreign or own/unknown remains rejected.
   assert(!observe().PreScoreSelfProvidedTargetAurasCompatible);
  }
  target.auras.clear(); target.unavailableApplications.insert(id);
  m=observe(); assert(!m.PreScoreSelfProvidedTargetAurasCompatible && m.PreScoreSelfProvidedTargetAuraSource=="unknown_source");
  target.unavailableApplications.clear();
 }
 assert(!BotCalibrationSelfProvidedAuras::TargetAuras(static_cast<Player*>(nullptr),&target).Compatible);
 assert(!BotCalibrationSelfProvidedAuras::TargetAuras(&player,static_cast<Unit*>(nullptr)).Compatible);
 target.auras.clear(); target.auras.emplace(1490,&b); m=observe();
 assert(!m.PreScoreSelfProvidedTargetAurasCompatible && m.PreScoreSelfProvidedTargetAuraSpellId==1490);
 assert(m.PreScoreSelfProvidedTargetAuraSource=="foreign_source");
 std::cout << "[" << failedJson << "," << BotCalibrationPreScoreStateJson(&m) << "," << window.UnexpectedSelfProvidedPlayerAuraActiveSamples << "," << serialize(&window) << "," << fireWindow.UnexpectedSelfProvidedTargetAuraActiveSamples << "," << serializeTargets(&fireWindow) << "," << badWindows.str() << "," << badPlayerCounts.str() << "]";
}
'''.replace("RESET", reset).replace("METRICS", metrics).replace("OBSERVER", observer).replace("TARGET_SERIALIZER", target_serializer).replace("SERIALIZER", serializer)
    # Only dependency enums are stubbed; contract and classifier headers are compiled verbatim.
    shared = (ROOT / "src/server/shared/SharedDefines.h").read_text()
    classes = shared[shared.index("enum Classes\n"):shared.index("// max+1 for player class")]
    (tmp_path / "SharedDefines.h").write_text("#pragma once\n" + classes)
    (tmp_path / "UpdateFields.h").write_text("#pragma once\nconstexpr int UNIT_CREATED_BY_SPELL=1;\n")
    path = tmp_path / "observer.cpp"
    path.write_text(cpp)
    binary = tmp_path / "observer"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(tmp_path), "-I", str(ROOT / "src/server/game"), str(path), "-o", str(binary)], check=True)
    failed, target_failed, unexpected, rows, fire_unexpected, fire_rows, bad_windows, bad_player_counts = json.loads(subprocess.check_output([str(binary)], text=True))
    assert failed["self_provided_player_auras_compatible"] is False
    assert failed["self_provided_player_aura_spell_id"] == 79058
    assert failed["self_provided_player_aura_source"] == "foreign_source"
    assert target_failed["self_provided_target_auras_compatible"] is False
    assert target_failed["self_provided_target_aura_spell_id"] == 1490
    assert target_failed["self_provided_target_aura_source"] == "foreign_source"
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

    fire_inputs = fixture["_closed_fire_090f_inputs"]()
    fire_raw = fire_inputs["target_observation"]["reference_condition_observation"]
    assert fire_raw["unexpected_target_aura_active_samples"] == 490
    fire_raw["target_auras"] = fire_rows
    fire_raw["unexpected_target_aura_active_samples"] = fire_unexpected
    assert fire_unexpected == 0
    fire_row = next(row for row in fire_rows if row["spell_id"] == 22959)
    assert fire_row == dict(spell_id=22959, caster_guid=1304, active_samples=490,
                           inactive_samples=111, owner_match_samples=490, owner_mismatch_samples=0)
    fixture["_assert_fire_reference_gate"](fire_inputs, True)
    import copy
    for counter, target_rows in bad_windows:
        rejected = copy.deepcopy(fire_inputs)
        rejected_raw = rejected["target_observation"]["reference_condition_observation"]
        rejected_raw["target_auras"] = target_rows
        rejected_raw["unexpected_target_aura_active_samples"] = counter
        assert counter == 601
        fixture["_assert_fire_reference_gate"](rejected, False)
    fixture["_assert_malformed_owned_target_rows_rejected"](fire_inputs)
    fixture["_assert_synthetic_owned_aura_projection_variants"](fire_inputs)

    for counter in bad_player_counts:
        assert counter == 601
        rejected = copy.deepcopy(fire_inputs)
        rejected["target_observation"]["reference_condition_observation"]["unexpected_player_aura_active_samples"] = counter
        fixture["_assert_fire_reference_gate"](rejected, False)
    for counter in (None, True, False, "0", 0.0, -1):
        rejected = copy.deepcopy(fire_inputs)
        rejected_raw = rejected["target_observation"]["reference_condition_observation"]
        if counter is None:
            del rejected_raw["unexpected_player_aura_active_samples"]
        else:
            rejected_raw["unexpected_player_aura_active_samples"] = counter
        fixture["_assert_fire_reference_gate"](rejected, False)
    for spell_id in (1126, 79061, 57669, 79102):
        rejected = copy.deepcopy(fire_inputs)
        raw = rejected["target_observation"]["reference_condition_observation"]
        row = next(row for row in raw["player_auras"] if row["spell_id"] == spell_id)
        row.update(active_samples=1, inactive_samples=600)
        fixture["_assert_fire_reference_gate"](rejected, False)
