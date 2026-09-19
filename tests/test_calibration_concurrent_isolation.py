"""Bounded native phase-isolation contract for concurrent dummy calibration."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
HELPER = BOT_DIR / "BotCalibrationIsolation.h"
POPULATION = BOT_DIR / "BotWorldPopulationMgrCalibrationPopulation.cpp"
CONTROL = BOT_DIR / "BotWorldPopulationMgrCalibrationControl.cpp"
SUMMARY = BOT_DIR / "BotWorldPopulationMgrCalibrationSummaryJson.cpp"
PHASING = ROOT / "src/server/game/Phasing/PhasingHandler.cpp"
PLAYER = ROOT / "src/server/game/Entities/Player/Player.cpp"


def test_production_path_phases_before_native_fixture_admission() -> None:
    population = POPULATION.read_text()
    control = CONTROL.read_text()
    summary = SUMMARY.read_text()
    phasing = PHASING.read_text()
    player = PLAYER.read_text()

    assert len(HELPER.read_text().splitlines()) < 1000
    assert "BotCalibrationIsolation::AcquirePhase" in control
    assert "sPhaseStore.LookupEntry(phaseId)" in control
    assert "BotCalibrationIsolation::Hold" in control
    assert 'if (mode == "single_target_300")' in control
    assert "PhasingHandler::AddPhase(bot, calibrationPhaseId, true);" in population
    assert "PhasingHandler::InheritPhaseShift(fixtureTarget, bot);" in population
    assert "fixtureTarget->UpdateObjectVisibility(true);" in population
    assert "BotCalibrationIsolation::Observe" in population
    assert "bot->UpdateZoneAndAreaId();" in population
    assert "BotCalibrationIsolation::Release(Cohort().CalibrationPhaseLease);" in control
    assert "PhasingHandler::RemovePhase(bot, calibrationPhaseId, true);" in control
    assert "PhasingHandler::RemovePhase(target, calibrationPhaseId, true);" in control
    assert '\\"calibration_phase_id\\"' in summary
    assert '\\"calibration_isolation\\"' in summary
    assert '\\"own_target_visibility_observed\\"' in summary
    assert '\\"own_target_visibility_observation_missing\\"' in summary
    assert '\\"observed_at_ms\\"' in summary
    assert "currentCalibrationBot = GetLoadedBot(state);" in summary
    assert "currentFixtureTarget = fixtureMap->GetCreature" in summary
    assert "currentCalibrationBot && currentFixtureTarget ? nowMs : 0" in summary
    assert '\\"provisioning_observed_bot_phase_id\\"' in summary
    assert '\\"provisioning_observed_target_phase_id\\"' in summary
    assert '\\"peer_visibility_observed\\":false' in summary
    assert '\\"peer_visibility_observation_missing\\":true' in summary

    # The reserved phase is installed before the map summon and before the
    # unchanged clearance/LOS/path gates. A foreign phase cannot be admitted by
    # moving a target or widening any existing radius.
    assert population.index("PhasingHandler::AddPhase(bot, calibrationPhaseId, true);") < population.index(
        "fixtureTarget = map->SummonCreature"
    )
    phase_add = population.index("PhasingHandler::AddPhase(bot, calibrationPhaseId, true);")
    zone_init = population.index("bot->UpdateZoneAndAreaId();")
    assert population.index("Player* bot = sBotMgr->SpawnWorldBot") < zone_init < phase_add
    assert population.rfind("if (isolatedSingleTargetMode)", 0, phase_add) > population.index(
        "uint16 const calibrationPhaseId"
    )
    assert population.index("PhasingHandler::InheritPhaseShift(fixtureTarget, bot);") < population.index(
        "float nearestHostileClearance"
    )
    assert "MinimumIsolatedDummyClearance" in population
    assert "120.0f" in population

    # Bind the fixture to the native recursion and inheritance bodies rather
    # than recreating a private target-visibility rule in the test.
    assert "AddPhase(controlled, phaseId, updateVisibility);" in phasing
    assert "target->GetPhaseShift() = source->GetPhaseShift();" in phasing
    assert "target->GetSuppressedPhaseShift() = source->GetSuppressedPhaseShift();" in phasing

    # Bind the lifecycle regression to the native path that caused the live
    # loss: placement is followed by one explicit zone/area initialization,
    # and that native area update rebuilds phase state before our AddPhase.
    update_zone = player.index("void Player::UpdateZoneAndAreaId()")
    update_area = player.index("void Player::UpdateArea(uint32 newArea)")
    area_change = player.index("PhasingHandler::OnAreaChange(this);", update_area)
    assert "UpdateArea(newarea);" in player[update_zone:update_zone + 700]
    assert update_zone < area_change
    assert "ClearPhases();" in phasing[phasing.index("void PhasingHandler::OnAreaChange"):
        phasing.index("void PhasingHandler::OnAreaChange") + 1000]


def test_allocator_and_native_phase_visibility_fixture(tmp_path: Path) -> None:
    source = r'''
#include "BotCalibrationIsolation.h"
#include "PhaseShift.h"

#include <cassert>
#include <cstdint>

struct NativeObject
{
    PhaseShift phase;
};

// This is the exact state copy used by the native InheritPhaseShift body; the
// production source assertion above binds the fixture to that implementation.
void InheritPhaseShift(NativeObject* target, NativeObject const* source)
{
    target->phase = source->phase;
}

int main()
{
    using namespace BotCalibrationIsolation;
    bool occupied[2] = { false, false };
    auto isOccupied = [&](std::uint16_t phaseId)
    {
        return phaseId == ReservedPhaseIds[0] ? occupied[0] : occupied[1];
    };
    auto noNativePhase = [](std::uint16_t) { return false; };

    PhaseLease first;
    PhaseAllocation firstAllocation = AcquirePhase(isOccupied, noNativePhase);
    assert(firstAllocation && firstAllocation.PhaseId == ReservedPhaseIds[0]);
    Hold(first, firstAllocation, 41);
    occupied[0] = true;

    PhaseLease witness;
    PhaseAllocation witnessAllocation = AcquirePhase(isOccupied, noNativePhase);
    assert(witnessAllocation && witnessAllocation.PhaseId == ReservedPhaseIds[1]);
    Hold(witness, witnessAllocation, 42);
    occupied[1] = true;

    PhaseAllocation exhausted = AcquirePhase(isOccupied, noNativePhase);
    assert(!exhausted && exhausted.Exhausted && !exhausted.NativeCollision);

    auto firstNativeCollision = [](std::uint16_t) { return true; };
    PhaseAllocation collision = AcquirePhase(
        [](std::uint16_t) { return false; }, firstNativeCollision);
    assert(!collision && collision.NativeCollision);

    NativeObject bot;
    NativeObject controlled;
    NativeObject ownTarget;
    NativeObject foreignTarget;
    NativeObject foreignBot;
    bot.phase.AddPhase(first.PhaseId, PhaseFlags::None, nullptr);
    InheritPhaseShift(&controlled, &bot);
    InheritPhaseShift(&ownTarget, &bot);
    foreignBot.phase.AddPhase(witness.PhaseId, PhaseFlags::None, nullptr);
    InheritPhaseShift(&foreignTarget, &foreignBot);

    // Native PhaseShift semantics retain the verified map/coordinate contract:
    // the same phase is visible, while an unphased or peer phase is hidden.
    assert(bot.phase.CanSee(controlled.phase));
    assert(bot.phase.CanSee(ownTarget.phase));
    assert(!bot.phase.CanSee(foreignTarget.phase));
    NativeObject unphased;
    assert(!bot.phase.CanSee(unphased.phase));

    // The first Player heartbeat's native area refresh clears explicit
    // phases. The production order restores the reserved phase only after
    // that refresh; no per-tick phase reapplication is involved.
    NativeObject lifecycle;
    lifecycle.phase.AddPhase(first.PhaseId, PhaseFlags::None, nullptr);
    lifecycle.phase.ClearPhases();
    assert(!lifecycle.phase.HasPhase(first.PhaseId));
    lifecycle.phase.AddPhase(first.PhaseId, PhaseFlags::None, nullptr);
    assert(lifecycle.phase.HasPhase(first.PhaseId));

    auto observation = Observe(first.PhaseId,
        [&](std::uint16_t phaseId) { return bot.phase.HasPhase(phaseId); });
    assert(observation.Matches());
    auto foreignObservation = Observe(first.PhaseId,
        [&](std::uint16_t phaseId) { return foreignBot.phase.HasPhase(phaseId); });
    assert(foreignObservation.ForeignPhase && !foreignObservation.Matches());

    // Addressed release removes only the first lease; the witness phase and
    // its native visibility remain available for the overlapping cohort.
    Release(first);
    assert(!first.Held && witness.Held && witness.PhaseId == ReservedPhaseIds[1]);
    assert(foreignBot.phase.CanSee(foreignTarget.phase));
}
'''
    cpp = tmp_path / "calibration_phase_fixture.cpp"
    binary = tmp_path / "calibration_phase_fixture"
    cpp.write_text(source)
    result = subprocess.run(
        [
            "c++",
            "-std=c++20",
            "-Isrc/server/game/Bots",
            "-Isrc/server/game/Phasing",
            "-Isrc/server/game",
            "-Isrc/server/game/Entities/Object",
            "-Isrc/common",
            "-Isrc/common/Utilities",
            "-Isrc/common/Containers",
            "-Idep/g3dlite/include",
            str(cpp),
            "src/server/game/Phasing/PhaseShift.cpp",
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], cwd=ROOT, check=True)


def test_non_isolated_calibration_modes_keep_the_native_path() -> None:
    control = CONTROL.read_text()
    population = POPULATION.read_text()
    phase_gate = control.index('if (mode == "single_target_300")')
    phase_acquire = control.index("BotCalibrationIsolation::AcquirePhase")
    assert phase_gate < phase_acquire
    population_gate = population.index("if (isolatedSingleTargetMode)")
    population_add = population.index(
        "PhasingHandler::AddPhase(bot, calibrationPhaseId, true);"
    )
    assert population_gate < population_add
    for mode in (
        '"aoe_300"',
        '"tank_threat_300"',
        '"healer_controlled_damage_300"',
    ):
        assert mode in control
    # The non-isolated modes retain their existing cluster/target setup; no
    # private phase operation is reachable from their production guards.
    assert "Cohort().CalibrationPhaseId = phaseAllocation.PhaseId;" in control
