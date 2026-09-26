"""Round 8 live run (Nefarian killed, route incomplete): the two root causes.

1. The Lightning Machine (51089) stayed in combat after Nefarian died, so the
   raid never left combat, the fallen never released (partial-death admission
   waits for native hostile inactivity) and the node never completed. The boss
   script now takes the machine out of combat when the encounter ends.
2. Swimmers at their stations were refused every hop at the lowered stop
   (native_liquid_hop_transport_moving): the lowered stop is GoState
   GO_STATE_TRANSPORT_ACTIVE (24), which the boarding rest rule did not count
   as a stop. Patch .git/round9_patches/nefarian/R9_stop_frame_zero_rest.patch;
   the test below checks the checked-in tree (it fails until the patch is
   applied) and the pure rule's behaviour.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_nefarians_end.cpp"
BOARDING = "src/server/game/Bots/BotWorldPopulationMgrValidationRouteBoardingAction.cpp"


def _code(path: Path) -> str:
    return re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))


def _body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[brace + 1:index]
    raise AssertionError(signature)


def test_lightning_machine_leaves_combat_when_the_encounter_ends() -> None:
    script = _code(SCRIPT)
    nefarian = script[:script.index("struct npc_nefarians_end_onyxia")]
    disengage = _body(nefarian, "void DisengageLightningMachine()")
    assert "instance->GetCreature(DATA_NEFARIANS_LIGHTNING_MACHINE)" in disengage
    assert "machine->CombatStop(true);" in disengage
    assert "machine->InterruptNonMeleeSpells(false);" in disengage
    died = _body(nefarian, "void JustDied(Unit* /*killer*/) override")
    assert died.index("_JustDied();") < died.index("DisengageLightningMachine();")
    evade = _body(nefarian, "void EnterEvadeMode(EvadeReason /*why*/) override")
    assert "DisengageLightningMachine();" in evade
    header = (SCRIPT.parent / "blackwing_descent.h").read_text(encoding="utf-8")
    assert "NPC_NEFARIANS_LIGHTNING_MACHINE         = 51089," in header


def test_core_parks_state_24_at_path_start() -> None:
    core = (ROOT / "src/server/game/Entities/GameObject/GameObject.cpp").read_text(encoding="utf-8")
    assert "if (_owner.GetGoState() == GO_STATE_TRANSPORT_ACTIVE)\n                stopTargetTime = 0;" in core
    assert "newProgress = stopTargetTime;" in core
    script = SCRIPT.read_text(encoding="utf-8")
    assert "transport->SetGoState(GO_STATE_TRANSPORT_ACTIVE);" in script


BEHAVIOUR = r'''
#include "Bots/BotValidationRouteNativeTransportLogic.h"
#include <cstdio>
using namespace BotValidationRouteNative;
int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("FAIL %s\\n", msg); ++failures; } } while (0)
int main()
{
    // State 24 (GO_STATE_TRANSPORT_ACTIVE: parked at path progress 0): moving
    // until its arrival time, then at rest (the Nefarian platform lowered).
    CHECK(StopFrameRestMs(24, 1000, 2000) == 0, "24 before arrival: moving");
    CHECK(StopFrameRestMs(24, 2000, 2000) == UnboundedRestMs, "24 at arrival: resting");
    CHECK(StopFrameRestMs(24, 9000, 2000) == UnboundedRestMs, "24 after arrival: resting");
    // The numbered stops (25 + n): the same, before and after arrival.
    for (std::uint32_t state : { 25u, 26u, 27u })
    {
        CHECK(StopFrameRestMs(state, 1000, 2000) == 0, "numbered stop before arrival: moving");
        CHECK(StopFrameRestMs(state, 3000, 2000) == UnboundedRestMs, "numbered stop after arrival: resting");
    }
    // Other states are never a stop.
    for (std::uint32_t state : { 0u, 1u, 2u, 23u })
        CHECK(StopFrameRestMs(state, 9000, 0) == 0, "not a transport stop state");
    // Cycling transports keep their timeline rest: a 10 s cycle resting at
    // offset 0 for its first 4 s.
    TransportTimeline cycle;
    cycle.PeriodMs = 10000;
    cycle.ZKeys = { { 0, 0.0f }, { 4000, 0.0f }, { 6000, 10.0f }, { 9000, 10.0f }, { 10000, 0.0f } };
    std::uint64_t const early = RestRemainingMs(cycle, 1000, 0.0f, 0.05f);
    CHECK(early >= 2900 && early <= 3025, "a cycling platform early in its rest: about 3 s left");
    CHECK(RestRemainingMs(cycle, 5000, 0.0f, 0.05f) == 0, "a cycling platform between levels: moving");
    CHECK(RestRemainingMs(cycle, 7000, 10.0f, 0.05f) > 1900, "resting at the upper level");
    return failures ? 1 : 0;
}
'''


def test_stop_frame_zero_rest_in_the_tree(tmp_path: Path) -> None:
    """The checked-in boarding rule counts state 24 as a stop (patch
    R9_stop_frame_zero_rest.patch; this fails until the patch is applied)."""
    boarding = _code(ROOT / BOARDING)
    rest = _body(boarding, "std::uint64_t RestRemainingAtLevelMs(")
    assert "return StopFrameRestMs(uint32(transport->GetGoState()), GameTime::GetGameTimeMS(),\n            transport->GetUInt32Value(GAMEOBJECT_LEVEL));" in rest
    assert "static_assert(GoStateTransportActive == GO_STATE_TRANSPORT_ACTIVE" in rest
    source = tmp_path / "behaviour.cpp"
    binary = tmp_path / "behaviour"
    source.write_text(BEHAVIOUR)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
                    str(source), "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
