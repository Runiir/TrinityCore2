"""Exercise the production mover's bounded support-target entry guard."""

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
    float DistanceToTarget = 0.0f;
    bool LineOfSight = true;

    ObjectGuid GetGUID() const { return Guid; }
    float GetExactDist(Actor const*) const { return DistanceToTarget; }
    bool IsWithinLOSInMap(Actor const*) const { return LineOfSight; }
};
struct State
{
    BotEncounter::MagmawParasiteCombatContract MagmawParasiteCombat;
};
struct ResolvedCombatAction
{
    float MinRange = 0.0f;
    float MaxRange = 0.0f;
};
int movementCalls = 0;
bool MoveEntry(State& state, Actor* bot, Actor* reference,
    ResolvedCombatAction const* action, bool forceRangedReposition)
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
    ResolvedCombatAction supportAction;
    supportAction.MinRange = 8.0f;
    supportAction.MaxRange = 40.0f;
    State state;
    state.MagmawParasiteCombat.Active = true;
    state.MagmawParasiteCombat.ActorGuid = support.Guid;
    state.MagmawParasiteCombat.SupportTargetGuid = parasite.Guid;

    // The exact support assignment may use the existing native range mover
    // only for a visible target inside its resolved minimum range.
    support.DistanceToTarget = 4.0f;
    support.LineOfSight = true;
    assert(MoveEntry(state, &support, &parasite, &supportAction, false));
    assert(movementCalls == 1);

    // Legal-band and truly remote/max-range cases remain closed before
    // geometry.
    support.DistanceToTarget = 8.0f;
    assert(!MoveEntry(state, &support, &parasite, &supportAction, false));
    support.LineOfSight = false;
    assert(!MoveEntry(state, &support, &parasite, &supportAction, false));
    support.LineOfSight = true;
    support.DistanceToTarget = 41.0f;
    assert(!MoveEntry(state, &support, &parasite, &supportAction, false));
    assert(movementCalls == 1);

    // LOS-only repair and forced ranged repositioning cannot turn support into
    // a chase, even when the target is inside the minimum range.
    support.DistanceToTarget = 4.0f;
    support.LineOfSight = false;
    assert(!MoveEntry(state, &support, &parasite, &supportAction, false));
    support.LineOfSight = true;
    assert(!MoveEntry(state, &support, &parasite, &supportAction, true));
    assert(movementCalls == 1);

    // Missing or zero-range resolved actions stay rejected for exact support.
    assert(!MoveEntry(state, &support, &parasite, nullptr, false));
    ResolvedCombatAction noMinimum;
    assert(!MoveEntry(state, &support, &parasite, &noMinimum, false));
    assert(movementCalls == 1);

    // Non-support targets and actors retain their existing range behavior.
    assert(MoveEntry(state, &foreign, &parasite, &supportAction, false));
    assert(MoveEntry(state, &support, &other, &supportAction, false));
    assert(movementCalls == 3);

    // Personal-threat permission alone retains its existing range behavior.
    state.MagmawParasiteCombat.SupportTargetGuid.Clear();
    state.MagmawParasiteCombat.PersonalThreatGuid = parasite.Guid;
    assert(MoveEntry(state, &support, &parasite, &supportAction, false));
    assert(movementCalls == 4);

    state.MagmawParasiteCombat.SupportTargetGuid = parasite.Guid;
    state.MagmawParasiteCombat.Active = false;
    assert(MoveEntry(state, &support, &parasite, &supportAction, false));
    assert(movementCalls == 5);

    // Null inputs remain safe and do not enter native movement.
    assert(!MoveEntry(state, nullptr, &parasite, &supportAction, false));
    assert(!MoveEntry(state, &support, nullptr, &supportAction, false));
    assert(movementCalls == 5);
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


def test_exact_support_target_only_under_min_range_can_reach_native_movement(
    tmp_path: Path,
) -> None:
    binary = compile_guard_probe(tmp_path, MOVER.read_text(encoding="utf-8"))
    subprocess.run([str(binary)], cwd=tmp_path, check=True)
