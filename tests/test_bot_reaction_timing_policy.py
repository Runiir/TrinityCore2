from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"


def function(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_production_reaction_policy_and_both_timer_callers(tmp_path):
    profile = (BOT_DIR / "BotClassSpecActionProfile.cpp").read_text()
    internal = (BOT_DIR / "BotClassSpecActionProfileInternal.h").read_text()
    calibration = (BOT_DIR / "BotWorldPopulationMgrCalibrationBot.cpp").read_text()
    preparation = (BOT_DIR / "BotWorldPopulationMgrUpdateBotPreparation.cpp").read_text()
    canonical = function(internal, "inline std::string CanonicalSpecTag")
    policy = function(profile, "uint32 BotClassSpecActionProfileStore::ReactionTimeMsForSpec")
    # Compile the actual caller statements; stubs supply observations only.
    calibration_timer = calibration[calibration.index("    uint32 const reactionTimeMs ="):
                                    calibration.index("\n\n    if (!bot", calibration.index("    uint32 const reactionTimeMs ="))]
    start = preparation.index("    uint32 decisionTickMs =")
    ordinary_timer = preparation[start:preparation.index("\n\n    context.EnsureProgressionScored", start)]
    source = tmp_path / "reaction.cpp"
    source.write_text('''
#include <algorithm>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <map>
#include <string>
using uint32 = uint32_t;
namespace BotClassSpecActionProfileDetail {
''' + canonical + '''
}
struct Bot { bool combat; std::string spec; bool IsInCombat() const { return combat; } };
struct BotClassSpecActionProfile { std::string SpecTag; };
struct BotClassSpecActionProfileStore {
 static uint32 ReactionTimeMsForSpec(char const*);
 static BotClassSpecActionProfile Build(Bot* b, char const*) { return {b->spec}; }
};
''' + policy + '''
struct State { uint32 DecisionTimer = 0; };
struct CohortState { std::string CalibrationTargetSpec; std::string CalibrationMode;
 struct { bool ValidationRouteEnable = false; } Config; } cohort;
CohortState& Cohort() { return cohort; }
struct Config { uint32 tick; uint32 GetIntDefault(char const*, uint32) { return tick; } } config;
Config* sConfigMgr = &config;
char const* GetDungeonRole(Bot*) { return "dps"; }
uint32 Calibration(std::string spec, std::string mode = "single_target") {
 cohort.CalibrationTargetSpec = spec; cohort.CalibrationMode = mode; State state;
''' + calibration_timer + '''
 return state.DecisionTimer;
}
uint32 Ordinary(std::string spec, bool combat, uint32 tick, bool validation = false) {
 Bot bot{combat,spec}; config.tick = tick; cohort.Config.ValidationRouteEnable = validation;
 struct { struct Bot* Bot; struct State State; } context{&bot,{}};
''' + ordinary_timer + '''
 return context.State.DecisionTimer;
}
int main() {
 for (auto spec : {"elemental_shaman", "Elemental-Shaman", "Elemental Shaman",
                   "affliction_warlock", "shadow_priest", "balance_druid"}) {
  assert(BotClassSpecActionProfileStore::ReactionTimeMsForSpec(spec) == 100);
  assert(Calibration(spec) == 100);
  assert(Ordinary(spec,true,3000) == 100);
  assert(Ordinary(spec,true,1) == 100);
  assert(Ordinary(spec,false,3000) == 3000);
  assert(Ordinary(spec,false,3000,true) == 1000);
  assert(Ordinary(spec,false,1) == 500);
 }
 for (auto spec : {"fire_mage", "Fire-Mage", "unknown", ""}) {
  assert(BotClassSpecActionProfileStore::ReactionTimeMsForSpec(spec) == 500);
  assert(Calibration(spec) == 500);
  assert(Ordinary(spec,true,3000) == 1000);
  assert(Ordinary(spec,true,1) == 500);
  assert(Ordinary(spec,false,3000) == 3000);
 }
 assert(BotClassSpecActionProfileStore::ReactionTimeMsForSpec(nullptr) == 500);
 assert(Calibration("survival_hunter") == 250);
 assert(Calibration("fire_mage","healer_controlled_damage_300") == 250);
 assert(Calibration("fire_mage","tank_threat_300") == 250);
}
''')
    binary = tmp_path / "reaction"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_tracked_elemental_rows_do_not_enable_channel_interrupt_timing():
    # Bind this scheduling change to the current profile's channel scope.
    statements = [statement
                  for path in (ROOT / "sql/custom/world").glob("*.sql")
                  for statement in path.read_text().split(";")
                  if "elemental_shaman" in statement]
    assert statements
    assert all("interruptible_channel" not in statement for statement in statements)
    candidates = (BOT_DIR / "BotClassSpecActionProfileCandidates.cpp").read_text()
    assert 'HasMechanicTag(profileSpell.MechanicTags, "interruptible_channel")' in candidates
