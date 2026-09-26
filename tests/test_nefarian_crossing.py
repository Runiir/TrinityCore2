"""The cross-pillar help's step into the lava (round 8 review).

The departure from a healer pillar's top into the lava needs the ledge-drop
contract's liquid variant: the dry-ground contract rejects a landing under
liquid (ledge_drop_lands_in_liquid) and must keep doing so. Package T's files
carry it as .git/round8_patches/nefarian/R8_ledge_drop_into_liquid.patch
(TransportSurfaceMove::LandInLiquid, ApproachContract::LandInLiquid,
ValidateLedgeDrop's two liquid verdicts, the executor's pass-through). These
checks apply the patch to copies of those files and:
- run the whole strategy program against them (the crossing departure: rim,
  defensive first, step-off with LandInLiquid, and its arbitration);
- run native ledge-drop admission (ValidateLedgeDrop and ChooseStepOff, the
  executor's own rules) over the lowered pillar's geometry for both
  contracts.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_nefarian_strategy import INCLUDES, PROGRAM, ROOT

PATCH = ROOT / ".git/round8_patches/nefarian/R8_ledge_drop_into_liquid.patch"
FILES = [
    "src/server/game/Bots/BotNativeActionIntent.h",
    "src/server/game/Bots/BotValidationRouteNativeTypes.h",
    "src/server/game/Bots/BotValidationRouteNativeApproach.h",
    "src/server/game/Bots/BotWorldPopulationMgrNativePathTransportSurface.cpp",
]


def _patched(tmp_path: Path) -> Path:
    tree = tmp_path / "patched"
    for name in FILES:
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, tree / name)
    already = "LandInLiquid" in (ROOT / FILES[0]).read_text(encoding="utf-8")
    if not already:
        if not PATCH.exists():
            pytest.skip("no round 8 liquid ledge-drop patch")
        subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
        result = subprocess.run(["git", "apply", str(PATCH)], cwd=tree, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    return tree


def _run(tmp_path: Path, program: str, tree: Path) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(tree / "src/server/game")]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


def test_patch_keeps_the_dry_ground_safeguard(tmp_path: Path) -> None:
    tree = _patched(tmp_path)
    approach = (tree / FILES[2]).read_text(encoding="utf-8")
    assert "if (probe.LandingInLiquid && !contract.LandInLiquid)\n        return { false, \"ledge_drop_lands_in_liquid\" };" in approach
    assert "return { false, \"ledge_drop_into_liquid_lands_dry\" };" in approach
    assert "drop.LandInLiquid = action.LandInLiquid;" in (tree / FILES[3]).read_text(encoding="utf-8")
    assert "bool LandInLiquid = false;" in (tree / FILES[0]).read_text(encoding="utf-8")
    assert "bool LandInLiquid = false;" in (tree / FILES[1]).read_text(encoding="utf-8")


def test_strategy_crossing_against_the_patched_executor(tmp_path: Path) -> None:
    out = _run(tmp_path, PROGRAM, _patched(tmp_path))
    assert "CROSSING departure checks skipped" not in out


ADMISSION = r'''
#include "Bots/BotValidationRouteNativeApproach.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianMagma.h"
#include <cstdio>
using namespace BotEncounter::Nefarian;
namespace Route = BotValidationRouteNative;

int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("FAIL %s\n", msg); ++failures; } } while (0)

// Native ledge-drop admission over the lowered pillar: the member stands at
// the rim (DescentRimRadius) on a slot heading; the step goes out level at
// its feet; the top ends at the slot's wall; under the step lies the sunken
// skirt, then the ring, both under the lava.
static Route::LedgeDropProbe Probe(uint8 pillar, uint8 slot, float step)
{
    PillarSlotProfile const& profile = SlotProfile(pillar, slot);
    float const origin = PlatformFrame::LoweredOriginZ;
    float const rimLocal = PlatformFrame::PillarTopLocalZ
        - PillarRimSlope * (DescentRimRadius - profile.FlatRadius);
    Route::LedgeDropProbe probe;
    probe.StepLengthYards = step;
    probe.StepZ = origin + rimLocal;
    probe.StepCollisionFree = true;
    for (float along = 0.0f; along <= step + 1e-3f; along += Route::SurfaceSampleStepYards)
    {
        Route::SurfaceSample sample;
        sample.Along = along;
        sample.TransportFloor = DescentRimRadius + along <= profile.WallRadius;
        probe.Step.push_back(sample);
    }
    float const radius = DescentRimRadius + step;
    probe.FootprintSupported = radius - BodyRadiusYards <= profile.WallRadius ? 1u : 0u;
    probe.LandingFound = true;
    probe.LandingZ = origin + (radius <= PillarSkirtRadius ? PillarSkirtLocalZ : 1.439f);
    probe.LandingOnTransport = true;
    probe.LandingInLiquid = probe.LandingZ < MagmaSurfaceZ;
    probe.HealthPct = 1.0f;
    probe.PredictedDamagePct = 0.05f;
    return probe;
}

int main()
{
    int checked = 0;
    for (uint8 pillar = 0; pillar < 3; ++pillar)
        for (uint8 slot = 0; slot < 6; ++slot)
        {
            Route::ApproachContract contract;
            contract.Mode = Route::ApproachMode::LedgeDrop;
            contract.LandingZ = PlatformFrame::LoweredOriginZ + 1.439f;
            contract.LandingToleranceYards = 1.0f;
            contract.LandOnTransport = true;
            contract.MinHealthAfterFallPct = 0.2f;
            auto probeAt = [pillar, slot](float step) { return Probe(pillar, slot, step); };
            Route::StepOffChoice const dry = Route::ChooseStepOff(contract, probeAt);
            CHECK(!dry.Verdict.Ok && dry.Verdict.Reason == "ledge_drop_lands_in_liquid",
                "the dry-ground contract still refuses the lava");
            contract.LandInLiquid = true;
            Route::StepOffChoice const wet = Route::ChooseStepOff(contract, probeAt);
            CHECK(wet.Verdict.Ok, "the liquid contract admits the step into the lava");
            CHECK(wet.StepYards > 0.0f && DescentRimRadius + wet.StepYards
                <= DescentStepOffRadius + 0.01f, "within the declared step-off");
            ++checked;
        }
    // The liquid contract refuses a dry landing.
    Route::ApproachContract contract;
    contract.Mode = Route::ApproachMode::LedgeDrop;
    contract.LandingZ = PlatformFrame::LoweredOriginZ + 1.439f;
    contract.LandInLiquid = true;
    Route::LedgeDropProbe dryLanding = Probe(0, 0, 2.0f);
    dryLanding.LandingInLiquid = false;
    CHECK(Route::ValidateLedgeDrop(contract, dryLanding).Reason == "ledge_drop_into_liquid_lands_dry",
        "the liquid contract refuses a dry landing");
    std::printf("ADMISSION %d slot headings\n", checked);
    return failures ? 1 : 0;
}
'''


def test_native_admission_of_the_step_into_the_lava(tmp_path: Path) -> None:
    out = _run(tmp_path, ADMISSION, _patched(tmp_path))
    assert "ADMISSION 18 slot headings" in out
