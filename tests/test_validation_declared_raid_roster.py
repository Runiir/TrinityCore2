"""Compile the production roster planner with lightweight state dependencies."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_production_planner_preserves_declared_slots_and_rejects_invalid_rosters(tmp_path):
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrRoster.cpp").read_text()
    start = source.index("std::vector<BotWorldPopulationMgr::RaidRosterPlanSlot> BotWorldPopulationMgr::BuildRosterPlan() const")
    end = source.index("\nstd::string BotWorldPopulationMgr::", start)
    method = source[start:end]
    fixture = json.loads((ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json").read_text())
    magmaw = fixture["shards"][0]["bots"]
    initializers = ",".join("{" + json.dumps(bot["canonical_roster_slot_id"]) + "," + json.dumps(bot["role"]) + "}" for bot in magmaw)
    program = r'''
#include <cassert>
#include <cstdint>
#include <set>
#include <string>
#include <utility>
#include <vector>
using uint32 = std::uint32_t;
using uint8 = std::uint8_t;
constexpr uint32 MAXGROUPSIZE = 5;
struct BotWorldPopulationMgr {
 struct RaidRosterPlanSlot { uint32 SlotIndex=0; uint8 SubGroup=0; std::string Role, RosterSlotId; };
 struct Identity { std::string RosterSlotId, Role; };
 struct Node { std::vector<Identity> ExpectedRoster; };
 struct Configuration { bool AllowRaids=true, ValidationRouteEnable=true; uint32 RaidSize=10, TargetPopulation=10; };
 struct CohortState { Configuration Config; } cohort;
 struct PartyState { std::vector<Node> ValidationRouteManifest; } party;
 CohortState const& Cohort() const { return cohort; }
 PartyState const& Party() const { return party; }
 std::vector<RaidRosterPlanSlot> BuildRosterPlan() const;
};
// Validation cohorts: no play slot is ever external.
namespace BotWorldPopulationMgrPlay {
struct Context {
 static bool IsExternalSlot(BotWorldPopulationMgr const&, std::string const&) { return false; }
};
}
'''+method+r'''
int main() {
 BotWorldPopulationMgr mgr;
 auto defaults = mgr.BuildRosterPlan();
 assert(defaults.size()==10 && defaults[0].Role=="tank" && defaults[1].Role=="tank");
 assert(defaults[2].Role=="healer" && defaults[4].Role=="healer" && defaults[5].Role=="dps");
 mgr.party.ValidationRouteManifest.push_back({{'''+initializers+r'''}});
 auto plan = mgr.BuildRosterPlan();
 assert(plan.size()==10 && plan[0].Role=="dps" && plan[0].RosterSlotId=="raid_tank_1");
 uint32 tankCount=0, healerCount=0, dpsCount=0;
 for (uint32 i=0; i<plan.size(); ++i) {
   assert(plan[i].SlotIndex==i && plan[i].SubGroup==i/5);
   if (plan[i].Role=="tank") { ++tankCount; assert(i==1 && plan[i].RosterSlotId=="raid_tank_2"); }
   if (plan[i].Role=="healer") ++healerCount;
   if (plan[i].Role=="dps") ++dpsCount;
 }
 assert(tankCount==1 && healerCount==3 && dpsCount==6);
 auto valid = mgr.party.ValidationRouteManifest.front().ExpectedRoster;
 mgr.party.ValidationRouteManifest.front().ExpectedRoster[0].Role="tank";
 assert(mgr.BuildRosterPlan()[0].Role=="tank");
 mgr.party.ValidationRouteManifest.front().ExpectedRoster=valid;
 mgr.party.ValidationRouteManifest.front().ExpectedRoster[0].RosterSlotId="";
 assert(mgr.BuildRosterPlan().empty());
 mgr.party.ValidationRouteManifest.front().ExpectedRoster=valid;
 mgr.party.ValidationRouteManifest.front().ExpectedRoster[0].RosterSlotId=valid[1].RosterSlotId;
 assert(mgr.BuildRosterPlan().empty());
 mgr.party.ValidationRouteManifest.front().ExpectedRoster=valid;
 mgr.party.ValidationRouteManifest.front().ExpectedRoster[0].Role="unknown";
 assert(mgr.BuildRosterPlan().empty());
 mgr.party.ValidationRouteManifest.front().ExpectedRoster=valid;
 mgr.party.ValidationRouteManifest.front().ExpectedRoster.pop_back();
 assert(mgr.BuildRosterPlan().empty());
 mgr.cohort.Config.ValidationRouteEnable=false;
 assert(mgr.BuildRosterPlan()[0].Role=="tank");
 mgr.cohort.Config.RaidSize=25;
 assert(mgr.BuildRosterPlan().size()==25);
}
'''
    cpp = tmp_path / "planner.cpp"
    cpp.write_text(program)
    binary = tmp_path / "planner"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-variable", str(cpp), "-o", str(binary)], check=True, capture_output=True)
    subprocess.run([str(binary)], check=True, capture_output=True)
