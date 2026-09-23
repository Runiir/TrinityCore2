from __future__ import annotations

import re
import struct
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
DBC = ROOT / "data/dbc/enUS"
PINCER_SEATS = (7909, 8104)  # Vehicle 833/910, Magmaw's Pincer 41789/41620.
SEAT_CAN_ATTACK = 0x00004000
SEAT_CAN_ENTER_OR_EXIT = 0x02000000


def _heal_attempt_body() -> str:
    source = CANDIDATES.read_text(encoding="utf-8")
    start = source.index("support.Attempt = [this, &context, healTargetGuid,")
    end = source.index("context.State.DecisionKernel.Submit(std::move(support));",
        start)
    return source[start:end]


def test_seated_heal_attempt_declines_before_spell_selection() -> None:
    source = CANDIDATES.read_text(encoding="utf-8")
    helper = source[source.index("bool PassengerSeatForbidsCasting("):]
    helper = helper[:helper.index("\n}\n")]
    # The gate mirrors SpellInfo::CheckVehicle: the seat must carry the
    # native can-attack flag, and a missing seat also forbids casting.
    assert "bot->GetVehicle()" in helper
    assert "GetSeatForPassenger(bot)" in helper
    assert "!seat || !seat->HasFlag(VEHICLE_SEAT_FLAG_CAN_ATTACK)" in helper

    body = _heal_attempt_body()
    gate = body.index("if (PassengerSeatForbidsCasting(context.Bot))")
    decline = body.index(
        'Outcome::NotApplicable(\n                            "heal_vehicle_seat_forbids_casting")')
    assert gate < decline
    # Nothing that records a failure, selects a spell or casts may run first.
    for later in ("ScheduleNativeLockWait(", "SelectHealSpell(",
                  "RecordCombatAttempt(", "TryCastFriendlySpell(",
                  'Retryable(\n                            "heal_target_stale")'):
        assert decline < body.index(later), later


def test_declined_seat_attempts_leave_no_heal_backoff(tmp_path: Path) -> None:
    source = tmp_path / "seat_heal_backoff.cpp"
    binary = tmp_path / "seat_heal_backoff"
    source.write_text(
        r'''
#include "Bots/BotActionArbiter.h"
#include <cassert>

using namespace BotActionArbitration;

// Replays the heal candidate across a pincer ride: several ticks seated,
// then the first tick back on the ground. Returns whether that first ground
// tick reached the attempt, and records the lifecycle it left behind.
static bool FirstGroundTickAttempts(Outcome seatedOutcome)
{
    Kernel kernel;
    std::string const key = "raid.support.heal.30002";
    bool seated = true;
    bool attemptedOnGround = false;
    uint64 nowMs = 100000;
    for (int tick = 0; tick < 13; ++tick, nowMs += 250)
    {
        if (tick == 12)
            seated = false;
        kernel.Begin(nowMs);
        Candidate heal;
        heal.Key = key;
        heal.Source = "adaptive_raid_support";
        heal.ActionPriority = Priority::Mechanic;
        heal.UtilityScore = 0.6f;
        heal.RequiredResources = Uses(Resource::GlobalCooldown, Resource::Cast);
        heal.Attempt = [&]()
        {
            if (seated)
                return seatedOutcome;
            attemptedOnGround = true;
            return Outcome::Started("trained_heal_submitted");
        };
        kernel.Submit(std::move(heal));
        kernel.Resolve();
    }
    return attemptedOnGround;
}

int main()
{
    // Before the gate every seated attempt failed at the cast. The streak
    // backs the heal key off, so the first tick after the ride is skipped.
    assert(!FirstGroundTickAttempts(
        Outcome::Retryable("heal_cast_retryable")));
    // With the gate, a seated attempt is NotApplicable: no streak, and the
    // first ground tick heals at once.
    assert(FirstGroundTickAttempts(
        Outcome::NotApplicable("heal_vehicle_seat_forbids_casting")));
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/common/Utilities"),
            "-I", str(ROOT / "src/common/Logging"),
            "-I", str(ROOT / "src/common/Debugging"),
            str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def _dbc_records(name: str) -> list[tuple[int, ...]]:
    raw = (DBC / name).read_bytes()
    _, count, _, size, _ = struct.unpack("<4s4I", raw[:20])
    return [struct.unpack(f"<{size // 4}I", raw[20 + i * size:20 + (i + 1) * size])
            for i in range(count)]


@pytest.mark.skipif(not (DBC / "VehicleSeat.dbc").exists(),
                    reason="client DBC data not extracted")
def test_pincer_seat_forbids_casting_and_permits_voluntary_exit() -> None:
    seats = {record[0]: record[1] for record in _dbc_records("VehicleSeat.dbc")
             if record[0] in PINCER_SEATS}
    assert set(seats) == set(PINCER_SEATS)
    for flags in seats.values():
        # No-cast seat: the reason a seated healer cannot heal (fix 2).
        assert not flags & SEAT_CAN_ATTACK
        # Voluntary exit is native, so a released healer can leave (fix 1).
        assert flags & SEAT_CAN_ENTER_OR_EXIT


def test_release_uses_the_native_exit_intent() -> None:
    hook = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotAdaptiveMagmawStrategyHook.h").read_text(
                encoding="utf-8")
    release = hook[hook.index("BuildSeatReleaseCandidate("):]
    release = release[:release.index("return release;")]
    assert '"release_pincer_seat"' in release
    assert "BotNativeAction::VehicleExit{}" in release
    assert re.search(r"HookHealerCriticalTankHealthPct = 35\.0f;", hook)
