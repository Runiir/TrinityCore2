from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotWorldDecisionRepeatCounter.h"
CALLER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrEventRecording.cpp"


def test_outcome_aware_decision_repeat_counter_and_production_caller() -> None:
    compiler = shutil.which("g++") or shutil.which("c++")
    assert compiler is not None

    source = r'''
#include "Bots/BotWorldDecisionRepeatCounter.h"

#include <cassert>
#include <cstdint>
#include <string_view>

int main()
{
    using BotWorldDecisionRepeatCounter::Next;

    std::uint32_t count = 22;
    std::string_view previousResult = "ok";
    for (std::string_view currentResult : {"failed", "ok", "failed", "ok"})
    {
        count = Next(count, "combat", "wait_for_candidate_backoff", previousResult,
            "combat", "wait_for_candidate_backoff", currentResult);
        assert(count == 1);
        previousResult = currentResult;
    }

    count = 22;
    previousResult = "ok";
    for (int observation = 1; observation <= 20; ++observation)
    {
        count = Next(count, "combat", "wait_for_candidate_backoff", previousResult,
            "combat", "wait_for_candidate_backoff", "failed");
        assert(count == static_cast<std::uint32_t>(observation));
        previousResult = "failed";
    }

    count = Next(7, "combat", "wait_for_candidate_backoff", "ok",
        "combat", "wait_for_candidate_backoff", "ok");
    assert(count == 8);
    count = Next(count, "combat", "wait_for_candidate_backoff", "ok",
        "combat", "wait_for_candidate_backoff", "ok");
    assert(count == 9);

    // The old action/situation-only expression would incorrectly return 23 here.
    bool const oldSameDecision = std::string_view("combat") == "combat"
        && std::string_view("wait_for_candidate_backoff") == "wait_for_candidate_backoff";
    assert(oldSameDecision ? 22 + 1 == 23 : false);
    assert(Next(22, "combat", "wait_for_candidate_backoff", "ok",
        "combat", "wait_for_candidate_backoff", "failed") == 1);

    assert(Next(9, "combat", "wait_for_candidate_backoff", "ok",
        "travel", "wait_for_candidate_backoff", "ok") == 1);
}
'''

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        fixture = temp / "decision_repeat_counter.cpp"
        binary = temp / "decision_repeat_counter"
        fixture.write_text(source, encoding="utf-8")
        subprocess.run(
            [
                compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(ROOT / "src/server/game"),
                str(fixture),
                "-o",
                str(binary),
            ],
            check=True,
            cwd=ROOT,
        )
        subprocess.run([str(binary)], check=True, cwd=ROOT)

    caller = CALLER.read_text(encoding="utf-8")
    assert '#include "Bots/BotWorldDecisionRepeatCounter.h"' in caller
    call = re.search(
        r"state\.ConsecutiveSameDecisionCount\s*=\s*"
        r"BotWorldDecisionRepeatCounter::Next\((.*?)\);",
        caller,
        re.DOTALL,
    )
    assert call is not None
    assert "state.LastDecisionResult" in call.group(1)
    assert "currentResult" in call.group(1)
    assert "state.LastDecisionResult = currentResult;" in caller
    assert "bool sameDecision = previousSituation" not in caller
