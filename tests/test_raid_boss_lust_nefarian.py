"""Round 7: the canonical boss lust on Nefarian (BotRaidBossLust*).

Round 6 Nefarian c0 re-pulled about 26 times on one node. Time Warp came once,
about 38.9 s into the first pull, and never again.

1. No recast: the latch was keyed on attempt, wipe and route generation, and
   these resets never raised wipe_generation. It is now also keyed on
   RaidRuntime::BossResetGeneration (a boss state leaving IN_PROGRESS other
   than to DONE, once per pull), so each pull gets one lust, still gated by the
   owner's cooldown. This is the fix.
2. The late first cast is not fixed here: the r06 combat log shows Onyxia on
   DPS for about 34.4 s before her first melee on the Feral tank. The lust
   waits for a living tank to hold a boss, so it fires 5 s after that hold
   (test_nefarian_lust_waits_for_the_feral_hold documents the dependency). The
   tank pickup is the Nefarian strategy's.

The selectable-boss filter and hold retention are generic multi-boss hygiene
(test_multi_boss_hold_keeps_its_clock_and_skips_untargetable_bosses).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
INCLUDES = ["src/server/game", "src/server/game/Entities/Object", "src/server/shared", "src/common",
            "src/common/Utilities", "src/common/Logging", "src/common/Debugging",
            "dep/recastnavigation/Detour/Include"]


PRELUDE = r'''
#include "Bots/BotRaidBossLust.h"
#include <cassert>
#include <cstdio>
#include <string>
using namespace BotEncounter;
namespace L = BotRaidBossLust;
std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }
static ObjectGuid G(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }
static ActorSnapshot Member(uint32 guid, char const* role, char const* spec) {
    ActorSnapshot player; player.Guid = G(guid); player.Kind = ActorKind::Player;
    player.Role = role; player.ClassSpec = spec; player.Alive = true; return player;
}
static ActorSnapshot Boss(uint32 entry, uint32 counter, uint32 victim, bool selectable) {
    ActorSnapshot boss; boss.Guid = ObjectGuid(HighGuid::Unit, entry, counter); boss.Entry = entry;
    boss.Alive = boss.InCombat = true; boss.Attackable = boss.Selectable = selectable;
    boss.VictimGuid = G(victim); return boss;
}
'''


def _run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "lust.cpp"
    binary = tmp_path / "lust"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


def test_multi_boss_hold_keeps_its_clock_and_skips_untargetable_bosses(tmp_path: Path) -> None:
    out = _run(tmp_path, PRELUDE + r'''
int main() {
    Blackboard board;
    board.Players = { Member(1, "tank", "blood_death_knight"), Member(2, "tank", "feral_druid_tank"),
        Member(4, "dps", "fire_mage"), Member(7, "healer", "discipline_priest") };
    // Generic: an untargetable boss (sorting first) with a tank victim, and a
    // targetable boss on the other tank. Entries are arbitrary.
    ActorSnapshot nefarian = Boss(40000, 100, 1, false);
    ActorSnapshot onyxia = Boss(41270, 200, 2, true);
    board.Summons = { nefarian, onyxia };
    auto isBoss = [](ObjectGuid) { return true; };
    L::TankHold hold = L::FindTankHold(board, isBoss);
    assert(hold.Boss == onyxia.Guid && hold.Tank == G(2));

    L::Latch latch;
    L::Rebind(latch, 1, 0, 40, 0);
    L::ObserveTankHold(latch, hold.Boss, hold.Tank, 1000);
    // The first boss becomes targetable and held by the other tank: the hold
    // in progress keeps its clock.
    board.Summons[0] = Boss(40000, 100, 1, true);
    assert(board.Summons[0].Guid.GetRawValue() < onyxia.Guid.GetRawValue());
    assert(L::FindTankHold(board, isBoss).Boss == board.Summons[0].Guid);  // no hold yet: GUID first
    hold = L::FindTankHold(board, isBoss, &latch);
    assert(hold.Boss == onyxia.Guid && hold.Tank == G(2));
    L::ObserveTankHold(latch, hold.Boss, hold.Tank, 3000);
    assert(!L::TankHeld(latch, 5999) && L::TankHeld(latch, 6000));
    latch.Submitted = true;

    // Same pull: no second lust. Next pull on the same node (wipe_generation 0,
    // the encounter reset raises BossResetGeneration): a fresh latch.
    L::Rebind(latch, 1, 0, 40, 0);
    assert(latch.Submitted);
    L::Rebind(latch, 1, 0, 40, 1);
    assert(!latch.Submitted && !latch.Holding && latch.ResetGeneration == 1);
    // The older call form keeps its meaning (reset generation 0).
    L::Latch legacy; L::Rebind(legacy, 1, 0, 40);
    assert(legacy.ResetGeneration == 0);
    std::puts("ok");
}
''')
    assert out.strip() == "ok"


def test_nefarian_lust_waits_for_the_feral_hold(tmp_path: Path) -> None:
    """Real entries and native flags: Onyxia hits a DPS first, then the Feral takes her."""
    out = _run(tmp_path, PRELUDE + r'''
int main() {
    Blackboard board;
    board.Players = { Member(1, "tank", "blood_death_knight"), Member(2, "tank", "feral_druid_tank"),
        Member(4, "dps", "fire_mage"), Member(8, "dps", "assassination_rogue"),
        Member(7, "healer", "discipline_priest") };
    // Nefarian 41376 circles in phase 1: selectable (the script clears
    // NOT_SELECTABLE before liftoff), not tanked. Onyxia 41270 opens on the rogue.
    ActorSnapshot nefarian = Boss(41376, 250200, 8, true);
    nefarian.InCombat = false;
    ActorSnapshot onyxia = Boss(41270, 250100, 8, true);
    assert(onyxia.Guid.GetRawValue() < nefarian.Guid.GetRawValue());  // entry above counter
    board.Hostiles = { onyxia, nefarian };
    auto isBoss = [](ObjectGuid guid) { return guid.GetEntry() == 41270 || guid.GetEntry() == 41376; };
    L::Latch latch;
    L::Rebind(latch, 1, 0, 40, 0);
    uint64 const pull = 100000;
    for (uint64 now = pull; now < pull + 34400; now += 400) {
        L::TankHold hold = L::FindTankHold(board, isBoss, &latch);
        L::ObserveTankHold(latch, hold.Boss, hold.Tank, now);
        assert(!L::TankHeld(latch, now));  // Onyxia on DPS: no hold, no lust
    }
    // The Feral takes Onyxia 34.4 s in: the lust fires 5 s later.
    board.Hostiles[0].VictimGuid = G(2);
    uint64 const pickup = pull + 34400;
    L::TankHold hold = L::FindTankHold(board, isBoss, &latch);
    assert(hold.Boss == onyxia.Guid && hold.Tank == G(2));
    L::ObserveTankHold(latch, hold.Boss, hold.Tank, pickup);
    for (uint64 now = pickup; now < pickup + L::TankHoldMs; now += 400) {
        L::ObserveTankHold(latch, hold.Boss, hold.Tank, now);
        assert(std::string(L::BlockedReason(board, latch, now)) == "raid_boss_lust_tank_hold_pending");
    }
    assert(L::BlockedReason(board, latch, pickup + L::TankHoldMs) == nullptr);
    latch.Submitted = true;
    // The next pull on the same node (wipe_generation still 0): a fresh latch,
    // again 5 s after the Feral hold (the owner's cooldown is the runtime's gate).
    L::Rebind(latch, 1, 0, 40, 1);
    assert(!latch.Submitted && !latch.Holding);
    L::ObserveTankHold(latch, hold.Boss, hold.Tank, 500000);
    assert(!L::TankHeld(latch, 504999) && L::TankHeld(latch, 505000));
    std::puts("ok");
}
''')
    assert out.strip() == "ok"


def test_runtime_keys_the_lust_on_the_encounter_reset() -> None:
    runtime = (BOTS / "BotWorldPopulationMgrRaidBossLust.cpp").read_text()
    assert "uint64 const resetGeneration = cohort.Raid.BossResetGeneration;" in runtime
    assert ("BotRaidBossLust::Rebind(latch, attemptId, wipeGeneration, routeGeneration,\n"
            "        resetGeneration);") in runtime
    assert "}, &latch);" in runtime
    assert "|| current.ResetGeneration != resetGeneration)" in runtime
    assert '+ std::to_string(resetGeneration);' in runtime
    # The owner's cooldown still gates each pull's cast.
    assert runtime.index("!bot->GetSpellHistory()->IsReady(spellInfo)") < runtime.index("BotActionArbitration::Candidate lust;")
    increments = (BOTS / "BotWorldPopulationMgrValidationCohortRuntime.cpp").read_text()
    assert "previousBossStates[bossId] == uint8(IN_PROGRESS)" in increments
    assert "++raid.BossResetGeneration;" in increments
    for name in ("BotRaidBossLust.h", "BotRaidBossLustLatch.h", "BotWorldPopulationMgrRaidBossLust.cpp"):
        assert len((BOTS / name).read_text().splitlines()) < 1000
