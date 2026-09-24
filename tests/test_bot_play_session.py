from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]


def test_play_roster_replaces_the_least_disruptive_trained_slots(tmp_path: Path) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(
        r'''
#include "Bots/BotPlaySession.h"
#include <cstdio>
#include <string>
#include <vector>

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

using namespace BotPlayRoster;

// The accepted Magmaw 10N roster (validation_routes.jsonl).
static std::vector<TemplateSlot> const Roster = {
    { "raid_tank_1", "dps", "balance_druid" },
    { "raid_tank_2", "tank", "blood_death_knight" },
    { "raid_healer_1", "healer", "restoration_druid" },
    { "raid_healer_2", "healer", "holy_paladin" },
    { "raid_healer_3", "healer", "discipline_priest" },
    { "raid_dps_1", "dps", "fire_mage" },
    { "raid_dps_2", "dps", "fire_mage" },
    { "raid_dps_3", "dps", "affliction_warlock" },
    { "raid_dps_4", "dps", "survival_hunter" },
    { "raid_dps_5", "dps", "elemental_shaman" },
};

static int failures = 0;

static void Expect(std::vector<std::string> roles, std::vector<std::string> expected,
    char const* expectedFailure = "")
{
    std::string failure;
    std::vector<std::string> const chosen = ChooseExternalSlots(Roster, roles,
        DisruptionOrder("blackwing_descent_10n_magmaw_diagnostic"), &failure);
    if (chosen != expected || failure != expectedFailure)
    {
        std::fprintf(stderr, "FAIL: %zu roles -> %zu slots (%s)\n", roles.size(),
            chosen.size(), failure.c_str());
        ++failures;
    }
}

int main()
{
    // One human dps takes the Elemental Shaman, whose only duty is lust.
    Expect({ "dps" }, { "raid_dps_5" });
    Expect({ "dps", "dps" }, { "raid_dps_5", "raid_dps_3" });
    Expect({ "healer" }, { "raid_healer_3" });
    Expect({ "tank" }, { "raid_tank_2" });
    // A second tank has no tank slot left: it replaces the next dps bot.
    Expect({ "tank", "tank" }, { "raid_tank_2", "raid_dps_5" });
    Expect({ "dps", "healer", "tank" }, { "raid_dps_5", "raid_healer_3", "raid_tank_2" });
    // Nine humans leave exactly one bot; ten leave none and are refused.
    Expect(std::vector<std::string>(9, "dps"),
        { "raid_dps_5", "raid_dps_3", "raid_dps_1", "raid_dps_2", "raid_dps_4",
          "raid_tank_1", "raid_healer_3", "raid_healer_1", "raid_healer_2" });
    Expect(std::vector<std::string>(10, "dps"), {}, "play_requires_at_least_one_bot");
    Expect({}, {});

    // Without a scenario table, roster order decides.
    std::string failure;
    std::vector<std::string> const plain = ChooseExternalSlots(Roster, { "dps" }, {}, &failure);
    if (plain != std::vector<std::string>{ "raid_tank_1" })
        ++failures;

    BotPlaySession session;
    if (session.Active || session.PermittedGeneration != 1 || !session.Externals.empty())
        ++failures;
    return failures == 0 ? 0 : 1;
}
'''
    )
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
