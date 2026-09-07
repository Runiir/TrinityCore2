"""Exercise the production mover's entry guard; downstream terrain is a spy."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MOVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatMovement.cpp"


def compile_guard_probe(tmp_path: Path, native_source: str) -> Path:
    signature = "bool BotWorldPopulationMgr::MoveBotToProfileRange("
    function = native_source.split(signature, 1)[1]
    # Use the actual production entry bytes. Replace only the downstream
    # geometry/pathing implementation with a movement-call spy.
    prefix = function[function.index("{") + 1:
                      function.index("    auto patrolCombatPointSafe")]
    source = tmp_path / "support_range_guard.cpp"
    binary = tmp_path / "support_range_guard"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawLaneTransition.h"
#include <cassert>

struct Actor
{
    ObjectGuid Guid;
    ObjectGuid GetGUID() const { return Guid; }
};
struct State
{
    BotEncounter::MagmawParasiteCombatContract MagmawParasiteCombat;
};
int movementCalls = 0;
bool MoveEntry(State& state, Actor* bot, Actor* reference)
{
''' + prefix + r'''
    static_cast<void>(state);
    ++movementCalls;
    return true;
}

int main()
{
    Actor support{ObjectGuid(HighGuid::Player, uint32(30007))};
    Actor foreign{ObjectGuid(HighGuid::Player, uint32(30008))};
    Actor parasite{ObjectGuid(HighGuid::Unit, uint32(41806), uint32(9001))};
    Actor other{ObjectGuid(HighGuid::Unit, uint32(41806), uint32(9002))};
    State state;
    state.MagmawParasiteCombat.Active = true;
    state.MagmawParasiteCombat.ActorGuid = support.Guid;
    state.MagmawParasiteCombat.SupportTargetGuid = parasite.Guid;

    // Every range-recovery caller enters here. Exact support ownership must
    // return before any downstream movement, even after native spell failure.
    assert(!MoveEntry(state, &support, &parasite));
    assert(movementCalls == 0);
    assert(!MoveEntry(state, nullptr, &parasite));
    assert(!MoveEntry(state, &support, nullptr));
    assert(movementCalls == 0);

    assert(MoveEntry(state, &foreign, &parasite));
    assert(MoveEntry(state, &support, &other));
    assert(movementCalls == 2);

    // Personal-threat permission alone retains its existing range behavior.
    state.MagmawParasiteCombat.SupportTargetGuid.Clear();
    state.MagmawParasiteCombat.PersonalThreatGuid = parasite.Guid;
    assert(MoveEntry(state, &support, &parasite));
    assert(movementCalls == 3);

    state.MagmawParasiteCombat.SupportTargetGuid = parasite.Guid;
    state.MagmawParasiteCombat.Active = false;
    assert(MoveEntry(state, &support, &parasite));
    assert(movementCalls == 4);
}
''',
        encoding="utf-8",
    )
    include_paths = [
        "src/server/game", "src/server/game/Entities/Object", "src/common",
        "src/common/Utilities", "src/common/Logging", "src/common/Debugging",
        "dep/g3dlite/include",
    ]
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         *[arg for path in include_paths for arg in ("-I", str(ROOT / path))],
         str(source), "-o", str(binary)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return binary


def test_exact_support_target_cannot_reach_native_range_movement(tmp_path: Path) -> None:
    binary = compile_guard_probe(tmp_path, MOVER.read_text(encoding="utf-8"))
    subprocess.run([str(binary)], cwd=tmp_path, check=True)
