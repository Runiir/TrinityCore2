from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotRaidAreaObservation.h"
IMPLEMENTATION = ROOT / "src/server/game/Bots/BotRaidAreaObservation.cpp"
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
SUPPORT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSupport.cpp"
SPELL = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSpell.cpp"


def test_area_observation_first_match_and_absence_fixture(tmp_path: Path) -> None:
    compiler = shutil.which("g++") or shutil.which("c++")
    assert compiler is not None
    source = tmp_path / "area_observation_fixture.cpp"
    binary = tmp_path / "area_observation_fixture"
    source.write_text(
        r'''
#include "Bots/BotRaidAreaObservation.h"

#include <cassert>
#include <string>
#include <vector>

using namespace BotRaidAreaObservation;

int main()
{
    CandidateFacts primary;
    primary.IsCreature = true;
    primary.IsPrimary = true;
    primary.Alive = true;
    primary.ValidAttackTarget = true;
    primary.Protected = true;
    primary.Guid = 10;

    CandidateFacts far;
    far.IsCreature = true;
    far.Alive = true;
    far.ValidAttackTarget = true;
    far.Protected = true;
    far.Guid = 44;
    far.Entry = 41806;
    far.SpawnId = 4400;
    far.PrimaryDistance2d = 44.0f;
    far.PrimaryDistance3d = 44.0f;
    far.PrimaryLineOfSight = false;

    CandidateFacts close = far;
    close.Guid = 4;
    close.SpawnId = 400;
    close.PrimaryDistance2d = 4.0f;
    close.PrimaryDistance3d = 5.0f;
    close.PrimaryLineOfSight = true;

    std::vector<CandidateFacts> ordered = {primary, far, close};
    auto facts = [](CandidateFacts const& candidate) { return candidate; };
    Observation observed = ObserveFirstProtectedTarget(true, true, ordered, facts);
    assert(observed.ProtectedTargetFound);
    assert(observed.FirstProtectedTargetGuid == 44);
    assert(observed.FirstProtectedPrimaryDistance2d == 44.0f);
    assert(!observed.FirstProtectedPrimaryLineOfSight);
    assert(ordered[1].Guid == 44 && ordered[2].Guid == 4);
    std::string json = observed.ObservationJson(true);
    assert(json.find("\"forbid_area\":true") != std::string::npos);
    assert(json.find("\"native_chain_selection_status\":\"not_observed\"") != std::string::npos);

    CandidateFacts ordinary = far;
    ordinary.Protected = false;
    std::vector<CandidateFacts> ordinaryOnly = {primary, ordinary};
    std::vector<CandidateFacts> protectedOnly = {far};
    assert(!ObserveFirstProtectedTarget(true, true, ordinaryOnly, facts).ProtectedTargetFound);
    assert(!ObserveFirstProtectedTarget(false, true, protectedOnly, facts).ProtectedTargetFound);
    assert(!ObserveFirstProtectedTarget(true, false, protectedOnly, facts).ProtectedTargetFound);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            compiler,
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
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_production_gates_share_query_and_resolver_retains_observation() -> None:
    implementation = IMPLEMENTATION.read_text(encoding="utf-8")
    resolver = RESOLVER.read_text(encoding="utf-8")
    assert "return ObserveNearbyProtectedEncounterTarget(owner, target).ProtectedTargetFound;" in implementation
    assert "ObserveFirstProtectedTarget(true, true, nearbyObjects" in implementation
    assert "areaObservation.ProtectedTargetFound" in resolver
    assert "areaObservation.ObservationJson(forbidArea)" in resolver
    for field in (
        "first_protected_target_guid",
        "first_protected_target_entry",
        "first_protected_target_spawn_id",
        "first_protected_primary_distance_2d",
        "first_protected_primary_distance_3d",
        "first_protected_primary_line_of_sight",
        "forbid_area",
        "native_chain_selection_status",
    ):
        assert field in HEADER.read_text(encoding="utf-8")
    for module in (SUPPORT, SPELL):
        text = module.read_text(encoding="utf-8")
        assert 'Bots/BotRaidAreaObservation.h' in text
        assert "using BotRaidAreaObservation::HasNearbyProtectedEncounterTarget;" in text
        assert "AllWorldObjectsInRange check(target, 45.0f)" not in text
