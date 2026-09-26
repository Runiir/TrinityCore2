"""Round 10: the Drudge lane contract accepts a canonical-composition roster (BotRaidDrudgeRosterIdentity.h).

The first BWD 10N end-to-end run (blackwing_descent_10n_full_c0) held every bot at bwd.magmaw.drudges with
drudge_lane_roster_slot_identity_mismatch: the lane selection proved each slot by the legacy generated ids
raid_tank_1 .. raid_dps_5, which a canonical roster ("<cohort>:<character_key>") never carries.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRUDGE = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
SCENARIOS = ROOT / "experiments/configs/validation_scenarios_cata_001.json"

PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRosterIdentity.h"
#include <cassert>
#include <string>
namespace R = BotRaidDrudgeRosterIdentity;
int main()
{
    std::vector<uint32> const tanks = { 2, 1 }, healers = { 5, 3, 4 };
    // Legacy: the exact generated id, whatever the role (raid_tank_1 is the Balance druid there).
    assert(R::Matches(false, 0, "raid_tank_1", "dps", tanks, healers));
    assert(!R::Matches(false, 0, "blackwing_descent_10n_full_c0:death_knight", "tank", tanks, healers));
    assert(!R::Matches(false, 10, "raid_dps_6", "dps", tanks, healers));
    // Canonical: the role the route row assigns to the slot.
    char const* roles[] = { "tank", "tank", "healer", "healer", "healer", "dps", "dps", "dps", "dps", "dps" };
    for (uint32 index = 0; index < 10; ++index)
    {
        assert(R::Matches(true, index, "blackwing_descent_10n_full_c0:x", roles[index], tanks, healers));
        assert(!R::Matches(true, index, "blackwing_descent_10n_full_c0:x", index < 2 ? "dps" : "tank", tanks, healers));
    }
    assert(!R::Matches(true, 0, "", "tank", tanks, healers));
    return 0;
}
'''


def test_the_identity_rule(tmp_path):
    source, binary = tmp_path / "identity.cpp", tmp_path / "identity"
    source.write_text(PROGRAM)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src/server/game"),
                    "-I", str(ROOT / "src/common"), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_the_lane_selection_uses_it_and_the_full_route_satisfies_it():
    selection = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp").read_text()
    assert "BotRaidDrudgeRosterIdentity::Matches(" in selection and "exactSlotIds" not in selection
    assert "BotCanonicalRaidScope::IsCanonicalRaid(" in selection
    config = json.loads(SCENARIOS.read_text())
    full = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n_full_c0")
    drudges = next(step for step in full["route"] if step["node_id"] == "bwd.magmaw.drudges")
    from tools.raid_program.raid_shard_scenarios import build_plan
    shard = next(row for row in build_plan(ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json")[
        "shards"] if row["cohort_id"] == "blackwing_descent_10n_full_c0")
    roles = [bot["role"] for bot in shard["bots"]]
    for slot, role in enumerate(roles, 1):
        expected = ("tank" if slot in drudges["split_lane_tank_slots"]
                    else "healer" if slot in drudges["split_healer_roster_slots"] else "dps")
        assert role == expected, (slot, role, expected)
