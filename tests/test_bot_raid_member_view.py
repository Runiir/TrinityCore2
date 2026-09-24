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


def test_member_view_orders_tanks_bots_first_and_classifies_externals(
    tmp_path: Path,
) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(
        r'''
#include "Bots/BotRaidMember.h"
#include <string>

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

using namespace BotRaidMember;

static Member Make(uint32 guid, Kind kind, char const* role, int32 slot)
{
    Member member;
    member.Guid = ObjectGuid(HighGuid::Player, guid);
    member.MemberKind = kind;
    member.Role = role;
    member.ClassSpec = "x";
    member.SlotIndex = slot;
    return member;
}

int main()
{
    // Validation-shaped raid: only bots; tank order is slot then GUID.
    View bots({ Make(30002, Kind::Bot, "tank", 1),
        Make(30001, Kind::Bot, "dps", 0),
        Make(30011, Kind::Bot, "tank", -1) });
    auto tanks = bots.DeclaredTanks();
    if (tanks.size() != 2 || tanks[0]->Guid.GetCounter() != 30002
        || tanks[1]->Guid.GetCounter() != 30011)
        return 1;
    if (!bots.Externals().empty() || bots.Bots().size() != 3)
        return 2;

    // A human tank in slot 0 still follows every bot tank.
    Member human = Make(50001, Kind::External, "tank", 0);
    Member sim = Make(50002, Kind::External, "healer", 3);
    sim.Source = ExternalSource::Sim;
    sim.Alive = false;
    View mixed({ human, Make(30002, Kind::Bot, "tank", 1), sim });
    tanks = mixed.DeclaredTanks();
    if (tanks.size() != 2 || !tanks[0]->IsBot() || !tanks[1]->IsExternal())
        return 3;
    if (!mixed.IsExternal(human.Guid) || mixed.IsExternal(tanks[0]->Guid))
        return 4;
    if (mixed.Externals().size() != 2 || mixed.Bots().size() != 1)
        return 5;
    if (mixed.CountRole("healer", false) != 1 || mixed.CountRole("healer", true) != 0)
        return 6;
    if (mixed.Find(ObjectGuid(HighGuid::Player, uint32(1))) != nullptr)
        return 7;

    // Only human tanks: they own pulls in slot order.
    View humans({ Make(50003, Kind::External, "tank", 5),
        Make(50001, Kind::External, "tank", 2) });
    tanks = humans.DeclaredTanks();
    if (tanks.size() != 2 || tanks[0]->SlotIndex != 2)
        return 8;
    return 0;
}
'''
    )
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
