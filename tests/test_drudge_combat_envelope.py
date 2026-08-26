from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
DRUDGE = (
    ROOT
    / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
)


def test_seed_combat_envelope_replays_canary35_and_exact_boundary(tmp_path: Path) -> None:
    source = tmp_path / "drudge_combat_envelope.cpp"
    binary = tmp_path / "drudge_combat_envelope"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeCombatEnvelope.h"
#include <cassert>
#include <string>
#include <vector>

int main()
{
    using namespace BotRaidDrudgeCombatEnvelope;
    std::vector<std::uint32_t> seeds{ 8, 6 };
    std::vector<std::uint32_t> laneA{ 1, 3, 4, 6, 7 };
    std::vector<std::uint32_t> laneB{ 2, 5, 8, 9, 10 };
    Point2d source0{ -297.355f, -80.0307f };
    Point2d source1{ -329.248f, -61.8282f };

    assert(!AcceptsConfiguredSeed(8, seeds, laneA, laneB, source0, source1,
        35.0f, { -343.177f, -126.937f }));
    assert(AcceptsConfiguredSeed(8, seeds, laneA, laneB, source0, source1,
        35.0f, { source1.X + 34.99f, source1.Y }));
    assert(!AcceptsConfiguredSeed(8, seeds, laneA, laneB, source0, source1,
        35.0f, { source1.X + 35.01f, source1.Y }));
    assert(AcceptsConfiguredSeed(7, seeds, laneA, laneB, source0, source1,
        35.0f, { -500.0f, -500.0f }));
    assert(AcceptsConfiguredSeed(8, seeds, laneA, laneB, source0, source1,
        35.0f, { -311.5f, -78.0f }));
    assert(std::string(RejectionReason()) == "drudge_anchor_combat_range_unsafe");
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_seed_envelope_precedes_cache_and_native_path_admission() -> None:
    geometry = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
        encoding="utf-8"
    )
    group = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGroupSafety.cpp").read_text(
        encoding="utf-8"
    )
    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text(encoding="utf-8")

    assert "SeedCombatEnvelopeSafe" in group
    assert group.index("SeedCombatEnvelopeSafe(") < group.index(
        "DynamicGroupPositionSafe("
    )
    cache = geometry[geometry.index("auto cacheUsable"):geometry.index("if (cacheUsable())")]
    assert "SeedCombatEnvelopeSafe" in cache
    selector = geometry[
        geometry.index("for (size_t candidateIndex = 0;"):
        geometry.index("State.ValidationRouteDrudgeAnchorX =")
    ]
    assert selector.index("combatEnvelopeSafe") < selector.index("SelectAnchorPathSearch")
    assert '"drudge_anchor_combat_range_unsafe"' in selector
    assert selector.index('"drudge_anchor_combat_range_unsafe"') < selector.index(
        "StrictNativePath"
    )
    assert "BotWorldPopulationMgrValidationRouteDrudgeGroupSafety.cpp" in cmake


def test_drudge_cpp_files_remain_below_one_thousand_lines() -> None:
    for path in DRUDGE.glob("*.[ch]*"):
        if path.suffix in {".c", ".cc", ".cpp", ".h", ".hpp"}:
            assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path
