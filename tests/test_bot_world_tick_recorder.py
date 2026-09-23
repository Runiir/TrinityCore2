"""Native world-tick stall recorder: pure logic compiled with g++."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def compile_and_run(tmp_path: Path, name: str, body: str) -> str:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(body, encoding="utf-8")
    subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    return subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True).stdout


def test_recorder_keeps_cumulative_sequenced_stalls_in_a_bounded_ring(tmp_path: Path) -> None:
    output = compile_and_run(tmp_path, "tick_ring", r'''
#include "Bots/BotWorldTickRecorder.h"
#include <cassert>
#include <iostream>
#include <sstream>

int main()
{
    BotWorldTick::Recorder recorder(500, 3);
    assert(!recorder.Observe(1000, 50));
    assert(!recorder.Observe(1050, 499));
    assert(recorder.Observe(2000, 500));
    assert(recorder.Observe(9000, 7000));
    assert(recorder.Observe(9700, 700));
    assert(recorder.Observe(10300, 600));
    assert(recorder.UpdateCount() == 6);
    assert(recorder.FirstUpdateAtMs() == 1000);
    assert(recorder.StallCount() == 4);
    assert(recorder.DroppedCount() == 1);
    assert(recorder.Stalls().size() == 3);
    assert(recorder.Stalls().front().Sequence == 2);
    assert(recorder.MaxDiffMs() == 7000);
    assert(recorder.MaxDiffAtMs() == 9000);

    // Reading never consumes rows.
    std::ostringstream first;
    std::ostringstream second;
    recorder.WriteJson(first, 11000);
    recorder.WriteJson(second, 11000);
    assert(first.str() == second.str());
    assert(recorder.Stalls().size() == 3);
    std::cout << first.str();

    // The stall start is the previous update's game time, never
    // at_ms - diff_ms: diff comes from the steady world-loop clock.
    assert(recorder.Stalls()[0].StartMs == 2000);
    assert(recorder.LastUpdateAtMs() == 10300);
    BotWorldTick::Recorder fresh(500, 4);
    assert(fresh.Observe(5000, 800));
    assert(fresh.Stalls().front().StartMs == 4200);  // no previous update yet
    assert(fresh.Observe(5900, 850));
    assert(fresh.Stalls().back().StartMs == 5000);

    assert(&BotWorldTick::WorldRecorder() == &BotWorldTick::WorldRecorder());
    assert(BotWorldTick::WorldRecorder().ThresholdMs() == BotWorldTick::StallThresholdMs);
    assert(BotWorldTick::WorldRecorder().Capacity() == BotWorldTick::StallCapacity);
    return 0;
}
''')
    payload = json.loads(output)
    assert payload == {
        "schema": "bot_world_update_ticks_v2",
        "now_ms": 11000,
        "threshold_ms": 500,
        "capacity": 3,
        "update_count": 6,
        "first_update_at_ms": 1000,
        "max_diff_ms": 7000,
        "max_diff_at_ms": 9000,
        "stall_count": 4,
        "dropped_count": 1,
        "stalls": [
            {"sequence": 2, "start_ms": 2000, "at_ms": 9000, "diff_ms": 7000},
            {"sequence": 3, "start_ms": 9000, "at_ms": 9700, "diff_ms": 700},
            {"sequence": 4, "start_ms": 9700, "at_ms": 10300, "diff_ms": 600},
        ],
    }


def test_world_update_and_status_are_wired_to_the_recorder() -> None:
    update = (BOTS / "BotWorldPopulationMgrUpdate.cpp").read_text(encoding="utf-8")
    body = update[update.index("void BotWorldPopulationMgr::Update(uint32 diff)"):]
    body = body[: body.index("\n}\n")]
    assert "BotWorldTick::WorldRecorder().Observe(NowMs(), diff);" in body
    status = (BOTS / "BotWorldPopulationMgrStatus.cpp").read_text(encoding="utf-8")
    get_status = status[status.index("std::string BotWorldPopulationMgr::GetStatusJson() const"):]
    get_status = get_status[: get_status.index("\n}\n")]
    assert '",\\"world_update\\":"' in get_status
    assert "BotWorldTick::WorldRecorder().WriteJson(json, NowMs());" in get_status
    for path in (BOTS / "BotWorldTickRecorder.h", BOTS / "BotWorldPopulationMgrUpdate.cpp", BOTS / "BotWorldPopulationMgrStatus.cpp"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
