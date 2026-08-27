from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (
    ROOT
    / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeEntranceMovement.h"
)


def test_drudge_entrance_movement_outcomes_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "drudge_entrance_movement.cpp"
    binary = tmp_path / "drudge_entrance_movement"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeEntranceMovement.h"
#include <cassert>
#include <string>

using namespace BotRaidDrudgeEntranceMovement;

int main()
{
    Observation arrived;
    arrived.Arrived = true;
    assert(Classify(arrived) == Outcome::Arrived);

    Observation retained;
    retained.ActivePathRetained = true;
    retained.MeaningfulDistance = true;
    assert(Classify(retained) == Outcome::ActivePathRetained);
    retained.NativeMovementSubmitted = true;
    assert(Classify(retained) == Outcome::ActivePathRetained);

    Observation submitted;
    submitted.NativeMovementSubmitted = true;
    submitted.MeaningfulDistance = true;
    assert(Classify(submitted) == Outcome::Submitted);

    Observation higherPriority;
    higherPriority.HigherPriorityMovementActive = true;
    higherPriority.MeaningfulDistance = true;
    assert(Classify(higherPriority) == Outcome::HigherPriorityPending);
    // Preserve the arbitration receipt even if the request is at the same
    // point. It must never be relabeled as a native submission.
    higherPriority.MeaningfulDistance = false;
    assert(Classify(higherPriority) == Outcome::HigherPriorityPending);

    Observation rejected;
    rejected.MeaningfulDistance = true;
    assert(Classify(rejected) == Outcome::Rejected);

    Observation noProgress;
    noProgress.NoProgress = true;
    assert(Classify(noProgress) == Outcome::NoProgress);
    assert(Classify(Observation{}) == Outcome::NoProgress);
    noProgress.NativeMovementSubmitted = true;
    assert(Classify(noProgress) == Outcome::NoProgress);

    assert(std::string(Name(Outcome::HigherPriorityPending))
        == "higher_priority_movement_active");
    assert(std::string(Name(Outcome::NoProgress)) == "no_progress");
    assert(std::string(TraceResult(Outcome::Arrived, "move", "wait"))
        == "wait");
    assert(std::string(TraceResult(Outcome::Submitted, "move", "wait"))
        == "move");
    assert(std::string(TraceResult(Outcome::ActivePathRetained,
        "move", "wait")) == "drudge_entrance_native_path_retained");

    assert(!ShouldSubmitNativeMovement(false, true, 40.0f));
    assert(ShouldSubmitNativeMovement(false, false, 40.0f));
    // Canary83 was only 0.17 yd from its anchor but repeatedly resubmitted a
    // native path. Treat that observed tolerance as no progress.
    assert(!ShouldSubmitNativeMovement(false, false, 0.17f));
    assert(!ShouldSubmitNativeMovement(false, false, 0.1f));
    assert(!ShouldSubmitNativeMovement(false, false, 0.0f));

    assert(ContinuePackCombat(Outcome::Arrived, true));
    assert(ContinuePackCombat(Outcome::ActivePathRetained, true));
    assert(ContinuePackCombat(Outcome::Submitted, true));
    assert(ContinuePackCombat(Outcome::HigherPriorityPending, true));
    assert(!ContinuePackCombat(Outcome::Rejected, true));
    // Canary86 reached the fixed anchor physically while tactical arrival was
    // false only because a Drudge entered the safety radius. Keep the typed
    // no-progress observation, but do not suppress linked-pack offense when
    // no movement is actually needed.
    assert(ContinuePackCombat(Outcome::NoProgress, true, true));
    assert(!ContinuePackCombat(Outcome::NoProgress, true, false));
    assert(!ContinuePackCombat(Outcome::Rejected, true, true));
    assert(!ContinuePackCombat(Outcome::Submitted, false));
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
