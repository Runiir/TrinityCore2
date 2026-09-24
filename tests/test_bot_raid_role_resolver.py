from __future__ import annotations

import struct
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TALENT_TAB_DBC = ROOT / "data/dbc/enUS/TalentTab.dbc"
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]


def _compile_and_run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run(
        [str(binary)], check=True, cwd=ROOT, capture_output=True, text=True
    ).stdout


def test_declared_role_then_talent_tree_never_class_fallback(tmp_path: Path) -> None:
    _compile_and_run(
        tmp_path,
        r'''
#include "Bots/BotRaidRoleResolver.h"
#include <cstdlib>

using namespace BotRaidRole;

static bool Is(Resolution const& r, char const* role, char const* spec,
    char const* source, bool ambiguous)
{
    return r.Role == role && r.ClassSpec == spec && r.Source == source
        && r.Ambiguous == ambiguous;
}

int main()
{
    // No raid role: the talent tree decides. A Frost DK is dps, not a tank.
    if (!Is(Resolve(0, 399), "dps", "frost_death_knight", "talent_tree", false))
        return 1;
    if (!Is(Resolve(0, 398), "tank", "blood_death_knight", "talent_tree", false))
        return 2;
    if (!Is(Resolve(0, 815), "dps", "fury_warrior", "talent_tree", false))
        return 3;
    if (!Is(Resolve(0, 795), "dps", "shadow_priest", "talent_tree", false))
        return 4;
    if (!Is(Resolve(0, 831), "healer", "holy_paladin", "talent_tree", false))
        return 5;
    // The raid-UI role wins over talents; the LFG leader bit is ignored.
    if (!Is(Resolve(1 | TankMask, 855), "tank", "retribution_paladin", "declared_role", false))
        return 6;
    // Feral: role picks the tag; without a role assume dps and ask.
    if (!Is(Resolve(TankMask, 750), "tank", "feral_druid_tank", "declared_role", false))
        return 7;
    if (!Is(Resolve(0, 750), "dps", "feral_druid_dps", "assumed_dps", true))
        return 8;
    // Several declared roles fall back to the tree.
    if (!Is(Resolve(TankMask | DamageMask, 845), "tank", "protection_warrior", "talent_tree", false))
        return 9;
    // No talents and no role: unknown, never guessed from class.
    if (!Is(Resolve(0, 0), "", "", "unknown", true))
        return 10;
    if (!Is(Resolve(HealerMask, 0), "healer", "", "declared_role", false))
        return 11;
    return 0;
}
''',
    )


def _dbc_player_trees() -> dict[int, tuple[int, int]]:
    data = TALENT_TAB_DBC.read_bytes()
    _, count, fields, record_size, _ = struct.unpack("<4s4I", data[:20])
    trees: dict[int, tuple[int, int]] = {}
    for index in range(count):
        offset = 20 + index * record_size
        row = struct.unpack(f"<{fields}I", data[offset : offset + record_size])
        if row[4]:  # pet talent category
            continue
        trees[row[0]] = (row[3], row[8])
    return trees


@pytest.mark.skipif(not TALENT_TAB_DBC.is_file(), reason="client DBC not extracted")
def test_talent_tree_table_matches_talent_tab_dbc(tmp_path: Path) -> None:
    output = _compile_and_run(
        tmp_path,
        r'''
#include "Bots/BotRaidRoleResolver.h"
#include <cstdio>

int main()
{
    for (BotRaidRole::TalentTree const& tree : BotRaidRole::TalentTrees)
        std::printf("%u %u %u %s\n", tree.TreeId, tree.ClassMask,
            unsigned(tree.RolesMask), tree.ClassSpec);
    return 0;
}
''',
    )
    table = {}
    for line in output.splitlines():
        tree_id, class_mask, roles, spec = line.split()
        table[int(tree_id)] = (int(class_mask), int(roles), spec)
    dbc = _dbc_player_trees()
    assert set(table) == set(dbc)
    for tree_id, (class_mask, roles, _) in table.items():
        assert (class_mask, roles) == dbc[tree_id], tree_id
    assert len({spec for _, _, spec in table.values()}) == len(table)
