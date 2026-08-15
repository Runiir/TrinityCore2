import struct
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
IMPL = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()


def test_timed_marker_window_and_failed_bearing_rotation_compile_and_replay(tmp_path):
    source = tmp_path / "raid_hazard_replay.cpp"
    binary = tmp_path / "raid_hazard_replay"
    source.write_text(
        r'''
#include "Bots/BotRaidHazardState.h"
#include <cassert>

int main()
{
    using namespace BotRaidHazard;

    // Native Chainwielder contract: the marker is a 27-second summon, while
    // Overhead Smash is a 3-second cast plus a 2-second effect and a 1-second
    // observation buffer. The remaining visual is not a second damage window.
    assert(TimedMarkerDangerActive(27000, 27000, 3000, 2000));
    assert(TimedMarkerDangerActive(21000, 27000, 3000, 2000));
    assert(!TimedMarkerDangerActive(20999, 27000, 3000, 2000));
    assert(!TimedMarkerDangerActive(0, 27000, 3000, 2000));

    // Missing or inconsistent summon identity remains fail closed.
    assert(TimedMarkerDangerActive(0, 0, 3000, 2000));
    assert(TimedMarkerDangerActive(28000, 27000, 3000, 2000));

    // Exact d292 counterexample: GUIDs 30004 and 30009 shared bucket four and
    // repeated the same rejected fan. A bounded retry visits every bucket.
    for (unsigned attempt = 0; attempt < 5; ++attempt)
    {
        assert(RotatedBearingBucket(30004, attempt)
            == ((4 + attempt) % 5));
        assert(RotatedBearingBucket(30009, attempt)
            == ((4 + attempt) % 5));
    }
    return 0;
}
'''
    )
    subprocess.run(
        [
            "g++",
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
    )
    subprocess.run([str(binary)], check=True)


def _dbc_rows(path: Path):
    data = path.read_bytes()
    magic, count, field_count, record_size, _ = struct.unpack_from("<4s4I", data)
    assert magic == b"WDBC"
    assert record_size == field_count * 4
    for index in range(count):
        yield struct.unpack_from(
            "<" + "I" * field_count, data, 20 + index * record_size
        )


def test_local_native_dbc_pins_overhead_smash_radius_cast_and_effect_window():
    dbc = ROOT / "data/dbc/enUS"
    required = [
        dbc / "Spell.dbc",
        dbc / "SpellEffect.dbc",
        dbc / "SpellRadius.dbc",
        dbc / "SpellCastTimes.dbc",
        dbc / "SpellDuration.dbc",
    ]
    if not all(path.is_file() for path in required):
        pytest.skip("authoritative local 4.3.4 DBC assets are not materialized")

    spell = next(row for row in _dbc_rows(required[0]) if row[0] == 79580)
    cast_time_index = spell[12]
    duration_index = spell[13]
    effects = [row for row in _dbc_rows(required[1]) if row[24] == 79580]
    radius_indices = {row[15] for row in effects if row[15]}
    radii = {
        row[0]: struct.unpack("<f", struct.pack("<I", row[1]))[0]
        for row in _dbc_rows(required[2])
    }
    cast_times = {
        row[0]: struct.unpack("<i", struct.pack("<I", row[1]))[0]
        for row in _dbc_rows(required[3])
    }
    durations = {
        row[0]: struct.unpack("<i", struct.pack("<I", row[1]))[0]
        for row in _dbc_rows(required[4])
    }

    assert radius_indices == {9}
    assert radii[9] == 20.0
    assert cast_times[cast_time_index] == 3000
    assert durations[duration_index] == 2000


def test_chainwielder_safe_side_healing_and_rotated_exit_are_production_wired():
    movement = IMPL[
        IMPL.index("auto tryValidationRouteMovementCheck") :
        IMPL.index("auto drudgeLandedRushPending")
    ]
    assert '#include "Bots/BotRaidHazardState.h"' in IMPL
    assert "summon->GetTimer(), summon->GetLifetime()" in movement
    assert "TimedMarkerDangerActive" in movement
    assert "RotatedBearingBucket" in movement
    assert "ValidationRouteDodgeBearingAttempt + 1" in movement

    safe_hold = movement[
        movement.index("if (outsideHazard && hazardActive") :
        movement.index("if (!previousHazard->IsAlive()")
    ]
    heal = safe_hold.index(
        "tryRouteGroupHeal(bot, preferredTarget, false, true)"
    )
    hold = safe_hold.index('action = "hold_outside_hazard"')
    assert heal < hold
    assert "MoveBotToPoint" not in safe_hold[heal:hold]
