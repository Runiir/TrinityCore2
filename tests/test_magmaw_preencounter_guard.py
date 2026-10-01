"""Magmaw pre-engagement guard (BWD 10N round 4).

Round 3 (label blackwing_descent_10n-r03-a3864fcf6d) never engaged Magmaw at its boss step: the
Felguard's Felstorm at the drudge spawn struck the Exposed Head during bwd.magmaw.drudges in all
four runs (~/.cache/r3pk/diag_r3.md, Q2). The positions below are the retained combat-log
coordinates of those casts and of the r02 Felstorm that did not reach Magmaw; the combat reaches are
the world DB creature_model_info values of the Magmaw parts.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAGMAW = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw"
GUARD = MAGMAW / "BotMagmawPreEncounterGuard.h"
UNITS = MAGMAW / "BotMagmawPreEncounterGuardUnits.h"
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"


def test_guard_entries_match_the_native_magmaw_parts() -> None:
    instance = (SCRIPTS / "blackwing_descent.h").read_text(encoding="utf-8")
    guard = GUARD.read_text(encoding="utf-8")
    for native, constant, entry in (
        ("BOSS_MAGMAW", "BossEntry", 41570),
        ("NPC_EXPOSED_HEAD_OF_MAGMAW ", "ExposedHeadEntry", 42347),
        ("NPC_EXPOSED_HEAD_OF_MAGMAW_2", "ExposedHeadMirrorEntry", 48270),
        ("NPC_MAGMAWS_PINCER_1", "PincerLeftEntry", 41620),
        ("NPC_MAGMAWS_PINCER_2", "PincerRightEntry", 41789),
    ):
        line = next(row for row in instance.splitlines() if native in row)
        assert f"= {entry}," in line, native
        assert f"constexpr std::uint32_t {constant} = {entry};" in guard
    # Exposed head 42347 is summoned at this fixed position; 48270 at Magmaw.
    assert "ExposedHeadOfMagmawPos   = { -299.0f,    -28.9861f,  191.0293f" in (
        SCRIPTS / "boss_magmaw.cpp"
    ).read_text(encoding="utf-8")
    for path in (GUARD, UNITS):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000


def test_guard_refuses_the_round3_felstorm_and_admits_the_r02_hold(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_preencounter_guard.cpp"
    binary = tmp_path / "magmaw_preencounter_guard"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPreEncounterGuard.h"

#include <cassert>
#include <string_view>
#include <vector>

using namespace BotEncounter::MagmawPreEncounterGuard;

int main()
{
    // world DB: Magmaw 41570 at its spawn, CombatReach 15; Exposed Head 48270
    // rides Magmaw's position and 42347 sits at ExposedHeadOfMagmawPos, both
    // CombatReach 18.75.
    Part const body{ BossEntry, { -302.467f, -31.7101f, 210.848f }, 15.0f, true };
    Part const mirror{ ExposedHeadMirrorEntry, { -302.467f, -31.7101f, 210.848f }, 18.75f, true };
    Part const head{ ExposedHeadEntry, { -299.0f, -28.9861f, 191.0293f }, 18.75f, true };
    std::vector<Part> const parts = { body, mirror, head };
    float const felstormRadius = 8.0f;

    // Round 3: Felguard positions at the Felstorm casts (batches 4, 1, 2).
    std::vector<Point> const r03 = {
        { -301.8f, -54.4f, 212.3f }, { -305.7f, -58.0f, 212.3f },
        { -310.2f, -58.6f, 212.3f } };
    for (Point const& pet : r03)
    {
        Decision const decision = EvaluateAreaReach(false, { pet },
            felstormRadius, parts);
        assert(decision.Result == Verdict::ForbiddenAreaReach);
        assert(decision.Reason == "magmaw_part_in_area_reach_before_pull");
    }
    // The drudge home spawn itself: any area around a drudge standing there
    // reaches Magmaw's body and heads.
    Point const drudgeSpawn{ -298.833f, -50.349f, 212.298f };
    assert(EvaluateAreaReach(false, { drudgeSpawn }, 0.0f, parts).Forbidden());

    // r02: the first drudge Felstorm (35 yd from Magmaw) and the tank's hold
    // point it was dragged to did not reach Magmaw; the guard admits both.
    assert(!EvaluateAreaReach(false, { { -309.8f, -66.0f, 212.3f } },
        felstormRadius, parts).Forbidden());
    assert(!EvaluateAreaReach(false, { { -310.9f, -63.2f, 212.3f } },
        felstormRadius, parts).Forbidden());
    // ...but not when the pet's target still stands at the spawn.
    assert(EvaluateAreaReach(false, { { -310.9f, -63.2f, 212.3f }, drudgeSpawn },
        felstormRadius, parts).Forbidden());

    // Once Magmaw is engaged the guard never refuses (fighting back).
    for (Point const& pet : r03)
        assert(!EvaluateAreaReach(true, { pet }, felstormRadius, parts).Forbidden());
    // Dead parts and non-Magmaw creatures never refuse; no area, no refusal.
    Part deadBody = body;
    deadBody.Alive = false;
    Part drudge{ 42362, drudgeSpawn, 5.0f, true };
    assert(!EvaluateAreaReach(false, { r03[0] }, felstormRadius,
        { deadBody, drudge }).Forbidden());
    assert(!EvaluateAreaReach(false, { r03[0] }, -1.0f, parts).Forbidden());

    // Direct offense on any Magmaw part before the boss step is refused; at
    // the boss step the designated pull tank may open; after the pull it is
    // always allowed; other targets are never touched.
    for (std::uint32_t entry : { BossEntry, ExposedHeadEntry,
             ExposedHeadMirrorEntry, PincerLeftEntry, PincerRightEntry })
    {
        for (std::string_view node : { "bwd.magmaw.chainwielder",
                 "bwd.magmaw.drudges", "bwd.entrance.regroup", "" })
        {
            Decision const decision = EvaluateDirectTarget(node, false, entry);
            assert(decision.Result == Verdict::ForbiddenDirectTarget);
            assert(decision.PartEntry == entry);
            assert(decision.Reason == "magmaw_part_target_before_boss_step");
            assert(!EvaluateDirectTarget(node, true, entry).Forbidden());
        }
        assert(!EvaluateDirectTarget(EncounterNode, false, entry).Forbidden());
    }
    assert(!EvaluateDirectTarget("bwd.magmaw.drudges", false, 42362).Forbidden());
    assert(!EvaluateDirectTarget("bwd.magmaw.chainwielder", false, 42362).Forbidden());
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src/server/game"),
         str(source), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_units_adapter_reads_native_reach_engagement_and_trigger_radius() -> None:
    units = UNITS.read_text(encoding="utf-8")
    # Live parts, runtime combat reach and the boss's own engagement state.
    assert "creature->IsAlive()" in units
    assert "creature->GetCombatReach()" in units
    assert "entry == BossEntry && creature->IsEngaged()" in units
    # Felstorm's radius lives on its periodic trigger spell.
    assert "spellInfo->Effects[index].TriggerSpell" in units
    assert "effect.CalcRadius(caster)" in units
    # Both the caster and the unit it attacks are area centres.
    assert "centers.push_back({ target->GetPositionX()" in units
    # Read-only: the adapter never moves, casts or changes flags.
    for forbidden in ("CastSpell", "GetMotionMaster", "SetFlag", "RemoveFlag", "AttackStop"):
        assert forbidden not in units
