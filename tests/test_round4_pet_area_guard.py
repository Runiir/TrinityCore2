"""Round-4 coordinator fix 4 (diag_r3 Q2): a commanded pet area spell respects protected targets from the pet.

Round 3 Magmaw, every batch: 1-3 s after the drudge pull the Felguard's Felstorm (89751), commanded by
BotActionExecutor as soon as the pet stood in melee range, hit the Exposed Head of Magmaw from 22-28 yd
off Magmaw's centre. The owner's protected-target check is anchored on the owner or the owner's target;
the Felstorm command checked only ``SuppressAreaDamage``. The pet command now scans around the PET with
the spell's own native radius (triggered whirl included) plus the pet's chase slack, failing closed.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
EXECUTOR = (BOTS / "BotActionExecutor.cpp").read_text(encoding="utf-8")
SEMANTICS = (BOTS / "BotWorldPopulationMgrSpellSemantics.cpp").read_text(encoding="utf-8")
AUTHORITY = (BOTS / "BotWorldPopulationMgrValidationAuthority.cpp").read_text(encoding="utf-8")


def _compile_and_run(tmp_path: Path, name: str, body: str) -> None:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(body, encoding="utf-8")
    result = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
         str(source), "-o", str(binary)],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_the_pet_scan_radius_covers_the_whirl_and_fails_closed(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, "pet_area_guard", r'''
#include "Bots/BotPetAreaGuard.h"
#include <cassert>
#include <cmath>

using namespace BotPetAreaGuard;

// A combat-reach-inclusive 2D test, as Trinity::AllWorldObjectsInRange applies it.
bool Scanned(float centreDistance, float petReach, float partReach, float spellRadius)
{
    return centreDistance <= CollectRadius(spellRadius) + petReach + partReach;
}

int main()
{
    // Felstorm's triggered whirl: 8 yards around the pet, plus one melee range of chase
    assert(std::fabs(CollectRadius(8.0f) - 13.0f) < 1e-6f);
    // unresolved radius: the 45-yard area guard
    assert(CollectRadius(0.0f) == 45.0f && CollectRadius(-1.0f) == 45.0f);
    // Round 3: the pet whirled 22.7-28 yd from Magmaw's centre; the head's and Magmaw's combat
    // reach put them inside the scan, which also covers any unit the whirl itself could reach.
    assert(Scanned(28.0f, 1.5f, 15.0f, 8.0f));
    assert(Scanned(8.0f + 5.0f + 1.5f + 1.0f, 1.5f, 1.0f, 8.0f));
    assert(!Scanned(30.0f, 1.5f, 1.0f, 8.0f));
    // scope: only owners set by the canonical raid route authority are gated
    assert(!IsScoped(42));
    SetScoped(42, true);
    assert(IsScoped(42));
    SetScoped(42, false);
    assert(!IsScoped(42));
    SetScoped(0, true);
    assert(!IsScoped(0));
    return 0;
}
''')


def test_felstorm_is_gated_by_the_pet_centred_guard_and_the_magmaw_guard() -> None:
    block = EXECUTOR[EXECUTOR.index("pet->GetEntry() == FelguardEntry"):]
    block = block[:block.index("pet->CastSpell(pet, FelstormSpellId, false);")]
    assert "!BotPetAreaGuard::PetAreaSpellReachesProtectedTarget(bot, pet, felstorm)" in block
    assert "!BotEncounter::MagmawPreEncounterGuard::EvaluateUnitArea(pet, target, felstorm).Forbidden()" in block
    assert "!action.SuppressAreaDamage" in block
    assert '#include "Bots/BotPetAreaGuard.h"' in EXECUTOR
    assert len(EXECUTOR.splitlines()) < 1000


def test_the_engine_query_is_anchored_on_the_pet_with_the_native_radius() -> None:
    body = SEMANTICS[SEMANTICS.index("bool PetAreaSpellReachesProtectedTarget("):]
    body = body[:body.index("\n}\n") + 3]
    assert "Trinity::AllWorldObjectsInRange check(pet, collectRadius);" in body
    assert "CollectRadius(NativeAreaRadius(spellInfo, pet))" in body
    assert re.search(r"if \(!owner \|\| !pet \|\| !spellInfo \|\| !pet->IsInWorld\(\)\)\s*return true;", body)
    assert "IsProtectedEncounterTarget(" in body
    radius = SEMANTICS[SEMANTICS.index("float NativeAreaRadius("):]
    assert "effect.TriggerSpell" in radius and "effect.HasRadius(index)" in radius
    # scoped to canonical raid cohorts with the owner's route combat authority
    assert re.search(r"BotPetAreaGuard::SetScoped\(raidAuthorityOwner, BotCanonicalRaidScope::IsCanonicalRaid\(",
                     AUTHORITY)
