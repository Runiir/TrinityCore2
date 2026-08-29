from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotValidationRouteCombatAuthority.h"
RUNTIME = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteActiveCombat.cpp"


def test_current_route_authority_precedes_regroup_in_runtime() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    recovery = source.index("current_pack_authority_recovered_before_regroup")
    regroup = source.index("regroup_anchor_no_focus")

    assert recovery < regroup
    assert "Callbacks.ActivePackTarget()" in source[:regroup]
    assert "&& !currentTrashAuthority" in source[:regroup]


def test_current_route_authority_transition_table_compiles_and_executes(tmp_path: Path) -> None:
    replay = tmp_path / "current_route_authority_replay.cpp"
    binary = tmp_path / "current_route_authority_replay"
    replay.write_text(
        r'''
#include "Bots/BotValidationRouteCombatAuthority.h"

using BotValidationRouteCombatAuthority::Resolve;
using BotValidationRouteCombatAuthority::TargetDecision;

static_assert(Resolve(true, true, true) == TargetDecision::PreserveProposed);
static_assert(Resolve(true, true, false) == TargetDecision::PreserveProposed);
static_assert(Resolve(true, false, true) == TargetDecision::RecoverActivePack);
static_assert(Resolve(true, false, false) == TargetDecision::AllowRegroup);
static_assert(Resolve(false, true, true) == TargetDecision::AllowRegroup);

int main()
{
    return Resolve(true, false, true) == TargetDecision::RecoverActivePack
        ? 0 : 1;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(ROOT / "src/server/game"),
            str(replay),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
