from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DRUDGE_DIR = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
)
HEALTH_SYNC = DRUDGE_DIR / "BotRaidDrudgeHealthSync.h"
ACTIONS = DRUDGE_DIR / "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"


def test_drudge_health_sync_replays_normal_and_near_death_boundaries(tmp_path):
    source = tmp_path / "drudge_health_sync_replay.cpp"
    binary = tmp_path / "drudge_health_sync_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeHealthSync.h"
#include <cassert>

using namespace BotRaidDrudgeHealthSync;

int main()
{
    // Canary54's 32.73% versus 33.57% source snapshot is ordinary update skew.
    assert(!ShouldHoldLowerLane(0.3273f, 0.3357f));
    // The configured normal tolerance is inclusive at its boundary.
    assert(!ShouldHoldLowerLane(0.90f, 0.95f));
    assert(ShouldHoldLowerLane(0.90f, 0.9501f));

    // Near-death synchronization is stricter and also inclusive at its
    // boundary, so only a real excess over the 1-point ratio is held.
    assert(!ShouldHoldLowerLane(0.10f, 0.11f));
    assert(ShouldHoldLowerLane(0.09f, 0.1001f));
    assert(!ShouldHoldLowerLane(0.09f, 0.10f));
    assert(!ShouldHoldLowerLane(0.90f, 0.80f));
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


def test_drudge_action_uses_one_health_sync_decision_for_evidence_and_hold():
    actions = ACTIONS.read_text(encoding="utf-8")
    assert '#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeHealthSync.h"' in actions
    assert "bool const holdForHealthSync = BotRaidDrudgeHealthSync::ShouldHoldLowerLane(" in actions
    assert actions.count("holdForHealthSync") >= 3
    assert "UnitHealthPct(LaneSource) < UnitHealthPct(OtherSource)" not in actions


def test_drudge_health_sync_header_stays_small():
    assert len(HEALTH_SYNC.read_text(encoding="utf-8").splitlines()) < 1000
