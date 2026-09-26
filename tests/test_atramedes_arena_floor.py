"""Atramedes hall floor heights (BotAtramedesArenaFloor.h).

Round 5: the arena is a bowl (about 75.7 at the centre, 77-77.6 at the shield
ring) but the plan sent every destination at one flat z (75). The movement
planner rejected the moves near the shields (route_destination_path_control_
level_gap and endpoint_mismatch): the gong owner never reached its shield
(311 rejections) and the Searing Flame went ungonged; the air kite's ring
waypoints failed the same way. The table is the server's own navmesh height
on a 2 yd grid; this test regenerates it from data/mmaps and checks the plan
now sends its destinations at the floor.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
          "Atramedes/BotAtramedesArenaFloor.h")
MMAPS = ROOT / "data/mmaps"
DETOUR = ROOT / "dep/recastnavigation/Detour"
INCLUDES = [
    "-I", str(ROOT / "src/server/game"),
    "-I", str(ROOT / "src/server/game/Entities/Object"),
    "-I", str(ROOT / "src/common"),
    "-I", str(ROOT / "src/common/Utilities"),
    "-I", str(ROOT / "src/common/Logging"),
    "-I", str(ROOT / "src/common/Debugging"),
]

GENERATOR = r'''
#include "DetourNavMesh.h"
#include "DetourNavMeshQuery.h"
#include "DetourAlloc.h"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
struct TileHeader { uint32_t magic, dtVersion, mmapVersion, size; char usesLiquids; char padding[3]; };
int main(int, char** argv)
{
    std::string const dir = argv[1];
    std::ifstream mapFile(dir + "/669.mmap", std::ios::binary);
    dtNavMeshParams params{};
    mapFile.read(reinterpret_cast<char*>(&params), sizeof(params));
    dtNavMesh* mesh = dtAllocNavMesh();
    mesh->init(&params);
    for (auto const& entry : std::filesystem::directory_iterator(dir))
    {
        std::string const name = entry.path().filename().string();
        if (name.size() != 14 || name.rfind("669", 0) != 0 || name.substr(name.size() - 7) != ".mmtile")
            continue;
        std::ifstream tile(entry.path(), std::ios::binary);
        TileHeader header{};
        tile.read(reinterpret_cast<char*>(&header), sizeof(header));
        unsigned char* data = static_cast<unsigned char*>(dtAlloc(header.size, DT_ALLOC_PERM));
        tile.read(reinterpret_cast<char*>(data), header.size);
        if (!dtStatusSucceed(mesh->addTile(data, header.size, DT_TILE_FREE_DATA, 0, nullptr)))
            dtFree(data);
    }
    dtNavMeshQuery* query = dtAllocNavMeshQuery();
    query->init(mesh, 4096);
    dtQueryFilter filter;
    filter.setIncludeFlags(0x1 | 0x4 | 0x8);
    filter.setExcludeFlags(0);
    for (int row = 0; row < 61; ++row)
        for (int column = 0; column < 74; ++column)
        {
            float pos[3] = { -284.0f + 2.0f * row, 76.0f, 94.0f + 2.0f * column };
            float extents[3] = { 0.75f, 6.0f, 0.75f };
            dtPolyRef ref = 0;
            float nearest[3] = {};
            float height = 0.0f;
            int value = 0;
            if (dtStatusSucceed(query->findNearestPoly(pos, extents, &filter, &ref, nearest)) && ref
                && dtStatusSucceed(query->getPolyHeight(ref, pos, &height)))
                value = int(std::lround(height * 100.0f)) - 7000;
            std::printf("%d\n", value);
        }
}
'''

PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAdaptiveAtramedesStrategy.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <variant>

using namespace BotEncounter;
namespace A = BotEncounter::Atramedes;
namespace F = BotEncounter::Atramedes::ArenaFloor;

static ObjectGuid PlayerGuid(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }

int main()
{
    // The bowl: the centre about 75.7, the shield ring about 77 (the shields
    // spawn at 76.73), the bell platform about 75.
    float const centre = *F::Height(A::ArenaCenter.X, A::ArenaCenter.Y);
    assert(centre > 75.3f && centre < 76.1f);
    for (A::ShieldSpawn const& spawn : A::ShieldSpawns)
    {
        float const rim = *F::Height(spawn.X, spawn.Y);
        assert(std::fabs(rim - spawn.Z) < 0.8f);
    }
    // Round 5's rejected destinations: the owner's standby at 250130, the
    // air-kite ring waypoints near 250130, 250128 and 250126.
    for (Vector3 const& at : { Vector3{ 179.0f, -250.0f, 75.0f }, Vector3{ 176.69f, -252.93f, 75.0f },
            Vector3{ 164.82f, -260.70f, 75.0f }, Vector3{ 150.28f, -273.07f, 75.0f } })
    {
        Vector3 const floor = F::OnFloor(at);
        assert(floor.X == at.X && floor.Y == at.Y);
        assert(floor.Z > 76.4f && floor.Z < 77.9f);
    }
    // Outside the table: unchanged.
    Vector3 const far = F::OnFloor({ -224.0f, -224.6f, 76.8f });
    assert(far.Z == 76.8f);
    assert(!F::Height(300.0f, -224.0f));

    // The plan's move to the ground standby carries the floor height.
    Blackboard board;
    board.Route.NodeId = std::string(A::EncounterNode);
    board.ObservedAtMs = 5000;
    ActorSnapshot hunter;
    hunter.Guid = PlayerGuid(11003003);
    hunter.Kind = ActorKind::Player;
    hunter.Role = "dps";
    hunter.ClassSpec = "survival_hunter";
    hunter.Position = { 150.0f, -224.5f, 75.7f };
    hunter.Alive = true;
    hunter.InCombat = true;
    ActorSnapshot tank = hunter;
    tank.Guid = PlayerGuid(11003001);
    tank.Role = "tank";
    tank.ClassSpec = "blood_death_knight";
    board.Players = { tank, hunter };
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Vehicle, A::BossEntry, uint32(212));
    boss.Entry = A::BossEntry;
    boss.Kind = ActorKind::Summon;
    boss.Position = { 150.0f, -224.5f, 75.7f };
    boss.Alive = true;
    boss.InCombat = true;
    boss.ReactAggressive = true;
    boss.Attackable = true;
    boss.VictimGuid = tank.Guid;
    board.Summons.push_back(boss);
    for (A::ShieldSpawn const& spawn : A::ShieldSpawns)
    {
        ActorSnapshot shield;
        shield.Guid = ObjectGuid(HighGuid::Unit, spawn.Entry, spawn.SpawnId);
        shield.Entry = spawn.Entry;
        shield.Kind = ActorKind::Interactable;
        shield.Position = { spawn.X, spawn.Y, spawn.Z };
        shield.Alive = shield.Selectable = shield.Interactable = true;
        board.Interactables.push_back(shield);
    }
    AdaptiveAtramedesPlan const plan = AdaptiveAtramedesStrategy().Propose(board, hunter.Guid, "dps");
    assert(plan.Movement && plan.Movement->Id.Mechanic == "gong_owner_standby");
    BotNativeAction::Move const* move = std::get_if<BotNativeAction::Move>(&plan.Movement->Action);
    assert(move);
    assert(std::fabs(move->Z - *F::Height(move->X, move->Y)) < 0.01f);
    assert(move->Z > 76.4f);
    std::puts("atramedes arena floor ok");
    return 0;
}
'''


def test_floor_table_shape_and_size() -> None:
    text = HEADER.read_text(encoding="utf-8")
    assert len(text.splitlines()) < 1000
    body = text[text.index("HeightCenti{{") + len("HeightCenti{{"):text.index("}};")]
    values = [int(v) for v in re.findall(r"\d+", body)]
    assert len(values) == 74 * 61
    assert "Columns = 74" in text and "Rows = 61" in text


def test_floor_table_is_the_navmesh(tmp_path: Path) -> None:
    if not (MMAPS / "669.mmap").is_file():
        pytest.skip("map 669 navmesh tiles are not extracted in this checkout")
    source = tmp_path / "floor_generator.cpp"
    binary = tmp_path / "floor_generator"
    source.write_text(GENERATOR, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-O2", str(source),
                    *sorted(str(p) for p in (DETOUR / "Source").glob("*.cpp")),
                    "-I", str(DETOUR / "Include"), "-o", str(binary)], check=True, cwd=ROOT)
    generated = [int(v) for v in subprocess.run([str(binary), str(MMAPS)], check=True,
                 capture_output=True, text=True).stdout.split()]
    text = HEADER.read_text(encoding="utf-8")
    body = text[text.index("HeightCenti{{") + len("HeightCenti{{"):text.index("}};")]
    assert [int(v) for v in re.findall(r"\d+", body)] == [max(v, 0) for v in generated]


def test_plan_destinations_follow_the_floor(tmp_path: Path) -> None:
    source = tmp_path / "atramedes_floor.cpp"
    binary = tmp_path / "atramedes_floor"
    source.write_text(PROGRAM, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O0",
                    *INCLUDES, str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
    assert "atramedes arena floor ok" in result.stdout
