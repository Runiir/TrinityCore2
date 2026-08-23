from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotRouteCombatTargetPolicy.h"
FALLBACK = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp"


def test_owned_route_target_gate_replays_safe_admission(tmp_path: Path) -> None:
    source = tmp_path / "route_target_policy.cpp"
    binary = tmp_path / "route_target_policy"
    source.write_text(
        r'''
#include "Bots/BotRouteCombatTargetPolicy.h"
#include <cassert>

int main()
{
    using BotRouteCombatTargetPolicy::IsOwnedNativeEncounterTarget;
    assert(IsOwnedNativeEncounterTarget(true, true, true, true, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(false, true, true, true, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, false, true, true, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, false, true, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, true, false, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, true, true, false, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, true, true, true, 42649, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, true, true, true, 0, 42362));
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(ROOT / "src/server/game"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_route_target_allow_list_is_used_only_for_declared_drudge_entry() -> None:
    header = HEADER.read_text(encoding="utf-8")
    fallback = FALLBACK.read_text(encoding="utf-8")
    assert "targetEntry == declaredEntry" in header
    assert "BotRouteCombatTargetPolicy::IsOwnedNativeEncounterTarget" in fallback
    assert "BotEncounter::AdaptiveDrudgeStrategy::DrudgeEntry" in fallback
    assert "context.AdaptiveDrudgeOwnsNode" in fallback
