"""Magmaw publishes an overdue Mangle as due now, never as a wrapped uint32.

EventMap::GetTimeUntilEvent returns `itr->first - _time` as uint32. Magmaw's
UpdateAI advances the EventMap and then returns while he casts, so a Mangle
that comes due during a cast stays overdue and GetTimeUntilEvent wraps to
~4.29e9 ms. The Mangle defensive window (and the Heroism lead) read that
timer, so the wrap closed the window just as Mangle was imminent. The
production GetTimeUntilEncounterMechanic is compiled against the real
EventMap here.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOSS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_magmaw.cpp"


def body(source: str, signature: str) -> str:
    start = source.index("{", source.index(signature))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_overdue_mangle_is_due_now_not_wrapped(tmp_path: Path) -> None:
    source = BOSS.read_text(encoding="utf-8")
    events_enum = "enum Events " + body(source, "enum Events") + ";"
    timer = body(source, "uint32 GetTimeUntilEncounterMechanic(uint32 spellId) const override")
    unit = r'''
#include "EventMap.h"
#include "boss_magmaw_shared.h"
#include <cassert>
#include <limits>
using namespace BlackwingDescent::Magmaw;
uint32 urand(uint32 min, uint32) { return min; }
''' + events_enum + r'''
struct Boss {
    EventMap events;
    uint32 GetTimeUntilEncounterMechanic(uint32 spellId) const
''' + timer + r'''
};
int main() {
    constexpr uint32 Max = std::numeric_limits<uint32>::max();
    Boss b;
    assert(b.GetTimeUntilEncounterMechanic(SPELL_MANGLE_1) == Max);
    assert(b.GetTimeUntilEncounterMechanic(SPELL_MASSIVE_CRASH) == Max);

    // Pull: first Mangle 90 s out, counting down.
    b.events.ScheduleEvent(EVENT_MANGLE, 90s);
    b.events.Update(1000);
    assert(b.GetTimeUntilEncounterMechanic(SPELL_MASSIVE_CRASH) == 89000);
    b.events.Update(89000);
    assert(b.GetTimeUntilEncounterMechanic(SPELL_MASSIVE_CRASH) == 0);

    // A cast keeps UpdateAI from executing the due Mangle while the
    // EventMap clock keeps running: the raw subtraction wraps, the boss
    // reports 0.
    b.events.Update(1);
    assert(b.events.GetTimeUntilEvent(EVENT_MANGLE) == Max);
    assert(b.GetTimeUntilEncounterMechanic(SPELL_MASSIVE_CRASH) == 0);
    b.events.Update(1500);
    assert(b.events.GetTimeUntilEvent(EVENT_MANGLE) > 95000u);
    assert(b.GetTimeUntilEncounterMechanic(SPELL_MASSIVE_CRASH) == 0);

    // Mangle fires; the Prepare -> Massive Crash sequence still reports 0.
    assert(b.events.ExecuteEvent() == EVENT_MANGLE);
    b.events.ScheduleEvent(EVENT_PREPARE_MASSIVE_CRASH, 3500ms);
    b.events.ScheduleEvent(EVENT_MANGLE, 95s);
    assert(b.GetTimeUntilEncounterMechanic(SPELL_MASSIVE_CRASH) == 0);
    b.events.Update(3500);
    assert(b.events.ExecuteEvent() == EVENT_PREPARE_MASSIVE_CRASH);
    b.events.ScheduleEvent(EVENT_MASSIVE_CRASH, 5s);
    assert(b.GetTimeUntilEncounterMechanic(SPELL_MASSIVE_CRASH) == 0);
    b.events.Update(5000);
    assert(b.events.ExecuteEvent() == EVENT_MASSIVE_CRASH);
    // Crash done: back to the countdown to the repeat.
    assert(b.GetTimeUntilEncounterMechanic(SPELL_MASSIVE_CRASH) == 95000 - 3500 - 5000);
    return 0;
}
'''
    cpp = tmp_path / "timer_overdue.cpp"
    cpp.write_text(unit, encoding="utf-8")
    exe = tmp_path / "timer_overdue"
    subprocess.run(["g++", "-std=c++17", "-I" + str(ROOT / "src/common"),
                    "-I" + str(ROOT / "src/common/Utilities"), "-I" + str(BOSS.parent),
                    str(cpp), str(ROOT / "src/common/Utilities/EventMap.cpp"), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
