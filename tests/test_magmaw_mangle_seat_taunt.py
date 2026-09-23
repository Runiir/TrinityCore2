"""The Mangle-seized tank taunts Magmaw only to protect someone he can reach.

Mangle seats the tank in Magmaw's jaws (vehicle 834 seat 2, CAN_ATTACK) and
wipes its threat. Magmaw is rooted (sessile), so a victim outside his melee
reach (combat reach 15 + 1.5 + 4/3 = 17.8 yd) cannot be hit, and a taunt
would only pull his melee onto the seized tank: the gate rejects it. When his
victim is another player inside that reach, the taunt goes through. In all six
base-0891a99 / bundle1-b8a539b kills the top-threat player at the seize was
the Fire mage pincer rider Mgwdpsb, 4.6-18.3 yd from Magmaw's center.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
HEADER = BOTS / "BotTauntVehicleSeat.h"
RESOLVER = BOTS / "BotWorldPopulationMgrCombatResolver.cpp"
SPELL = BOTS / "BotWorldPopulationMgrCombatSpell.cpp"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def inline_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
    raise AssertionError(signature)


def test_gate_rejects_only_a_taunt_that_protects_nobody(tmp_path: Path) -> None:
    body = inline_body(text(HEADER),
        "inline bool TauntWouldOnlyPullHolderOntoSeat(Unit const* bot, Unit const* target)")
    unit = r'''
#include <cassert>
enum : unsigned { UNIT_STATE_ROOT = 0x400 };
struct Unit {
    Unit* vehicleBase = nullptr;
    Unit* victim = nullptr;
    bool rooted = false;
    bool reach = false;   // is the victim inside this unit's melee reach
    Unit* GetVehicleBase() const { return vehicleBase; }
    Unit* GetVictim() const { return victim; }
    bool HasUnitState(unsigned state) const { return state == UNIT_STATE_ROOT && rooted; }
    bool IsWithinMeleeRange(Unit const*) const { return reach; }
};
bool TauntWouldOnlyPullHolderOntoSeat(Unit const* bot, Unit const* target)
''' + body + r'''
int main() {
    Unit magmaw, tank, mage, other;
    magmaw.rooted = true;
    tank.vehicleBase = &magmaw;             // seized: seat 2 of Magmaw
    magmaw.victim = &mage;                  // threat wiped, mage on top

    magmaw.reach = false;                   // mage out of reach: no one hit
    assert(TauntWouldOnlyPullHolderOntoSeat(&tank, &magmaw));
    magmaw.reach = true;                    // mage in reach: protect her
    assert(!TauntWouldOnlyPullHolderOntoSeat(&tank, &magmaw));

    magmaw.reach = false;
    magmaw.victim = &tank;                  // already the victim
    assert(!TauntWouldOnlyPullHolderOntoSeat(&tank, &magmaw));
    magmaw.victim = nullptr;                // passive (Massive Crash)
    assert(!TauntWouldOnlyPullHolderOntoSeat(&tank, &magmaw));

    magmaw.victim = &mage;
    tank.vehicleBase = nullptr;             // released: ordinary taunt rules
    assert(!TauntWouldOnlyPullHolderOntoSeat(&tank, &magmaw));
    tank.vehicleBase = &other;              // another vehicle's seat
    assert(!TauntWouldOnlyPullHolderOntoSeat(&tank, &magmaw));
    tank.vehicleBase = &magmaw;
    magmaw.rooted = false;                  // a mobile holder would chase
    assert(!TauntWouldOnlyPullHolderOntoSeat(&tank, &magmaw));
    assert(!TauntWouldOnlyPullHolderOntoSeat(nullptr, &magmaw));
    assert(!TauntWouldOnlyPullHolderOntoSeat(&tank, nullptr));
    return 0;
}
'''
    cpp = tmp_path / "seat_taunt.cpp"
    exe = tmp_path / "seat_taunt"
    cpp.write_text(unit, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_both_taunt_candidate_paths_apply_the_gate_first() -> None:
    gate = (r"if \(candidate\.Category == BotCombatActionCategory::Taunt\s*"
            r"&& BotTauntVehicleSeat::TauntWouldOnlyPullHolderOntoSeat\(bot, target\)\)\s*"
            r"\{\s*candidate\.RejectReason = BotTauntVehicleSeat::RejectReason;\s*continue;\s*\}")
    for path in (RESOLVER, SPELL):
        source = text(path)
        assert '#include "Bots/BotTauntVehicleSeat.h"' in source
        match = re.search(gate, source)
        assert match, path
        assert match.start() < source.index('candidate.RejectReason = "threat_already_established";')
        assert len(source.splitlines()) < 1000, path
    assert 'RejectReason = "seat_holder_victim_out_of_reach";' in text(HEADER)
