from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
UNIT = GAME / "Entities/Unit/Unit.cpp"
UNIT_MELEE = GAME / "Entities/Unit/UnitMeleeDamage.cpp"
MGR = GAME / "Bots/BotWorldPopulationMgrCombatNotifications.cpp"
STATUS = GAME / "Bots/BotWorldPopulationMgrStatus.cpp"
SERIALIZER = GAME / "Bots/BotMeleeResolutionEventJson.h"
CMAKE = GAME / "CMakeLists.txt"


def test_melee_resolution_serializer_compiles_available_and_missing_stages(
    tmp_path: Path,
) -> None:
    source = r'''
#include "Bots/BotMeleeResolutionEventJson.h"

#include <cassert>
#include <sstream>
#include <string>

int main()
{
    MeleeDamageResolutionObservation complete;
    complete.StageMask = MeleeDamageResolutionObservation::Inputs
        | MeleeDamageResolutionObservation::WeaponRoll
        | MeleeDamageResolutionObservation::AttackerBonus
        | MeleeDamageResolutionObservation::TargetBonus
        | MeleeDamageResolutionObservation::ScriptHook
        | MeleeDamageResolutionObservation::Armor
        | MeleeDamageResolutionObservation::HitOutcomeStage
        | MeleeDamageResolutionObservation::Resilience
        | MeleeDamageResolutionObservation::Resolution;
    complete.WeaponRollAmount = 12000;
    complete.AfterAttackerBonusAmount = 12000;
    complete.AfterTargetBonusAmount = 10000;
    complete.AfterScriptHookAmount = 10000;
    complete.TargetArmor = 40530;
    complete.ArmorApplied = true;
    complete.EffectiveArmor = 30530.5f;
    complete.AfterArmorAmount = 4456;
    complete.AfterHitOutcomeAmount = 4456;
    complete.AfterResilienceAmount = 4456;
    complete.ResolvedDamageAmount = 0;
    complete.AbsorbedAmount = 4456;
    complete.AttackType = 0;
    complete.HitOutcome = 8;
    complete.AttackerPublishedMinDamage = 7588.0f;
    complete.AttackerPublishedMaxDamage = 11273.0f;
    complete.AttackerTemplateInputsAvailable = true;
    complete.AttackerRank = 3;

    std::ostringstream completeJson;
    BotMeleeResolutionEventJson::Append(completeJson, 41, complete);
    std::string const row = completeJson.str();
    assert(row.find("\"melee_resolution_sequence\":41") != std::string::npos);
    assert(row.find("\"weapon_roll_amount\":12000") != std::string::npos);
    assert(row.find("\"effective_armor\":30530.5") != std::string::npos);
    assert(row.find("\"resolved_damage_amount\":0") != std::string::npos);
    assert(row.find("\"absorbed_amount\":4456") != std::string::npos);
    assert(row.find("\"hit_outcome_name\":\"normal\"") != std::string::npos);
    assert(row.find("\"attacker_published_min_damage\":7588") != std::string::npos);
    assert(row.find("\"attacker_rank\":3") != std::string::npos);

    MeleeDamageResolutionObservation early;
    early.StageMask = MeleeDamageResolutionObservation::Inputs
        | MeleeDamageResolutionObservation::Resolution;
    early.TargetArmor = 40530;
    early.TargetState = 7;
    std::ostringstream earlyJson;
    BotMeleeResolutionEventJson::Append(earlyJson, 42, early);
    std::string const missing = earlyJson.str();
    assert(missing.find("\"weapon_roll_amount\":null") != std::string::npos);
    assert(missing.find("\"effective_armor\":null") != std::string::npos);
    assert(missing.find("\"hit_outcome\":null") != std::string::npos);
    assert(missing.find("\"target_armor\":40530") != std::string::npos);
    assert(missing.find("\"resolved_damage_amount\":0") != std::string::npos);
    assert(missing.find("\"attacker_rank\":null") != std::string::npos);
}
'''
    path = tmp_path / "melee_resolution_serializer.cpp"
    binary = tmp_path / "melee_resolution_serializer"
    path.write_text(source, encoding="utf-8")
    compiled = subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(GAME),
            str(path),
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert compiled.returncode == 0, compiled.stderr
    ran = subprocess.run(
        [str(binary)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert ran.returncode == 0, ran.stderr


def test_melee_resolution_is_non_aggregate_and_explicitly_correlated() -> None:
    unit = UNIT.read_text(encoding="utf-8")
    melee = UNIT_MELEE.read_text(encoding="utf-8")
    manager = MGR.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert "Entities/Unit/UnitMeleeDamage.cpp" in cmake
    assert "void Unit::CalculateMeleeDamage" not in unit
    assert "void Unit::DealMeleeDamage" not in unit

    calculate = melee.split("void Unit::CalculateMeleeDamage", 1)[1].split(
        "void Unit::DealMeleeDamage", 1
    )[0]
    assert calculate.index("CalculateDamage(") < calculate.index(
        "observation.WeaponRollAmount = damage"
    )
    assert calculate.index("MeleeDamageBonusDone(") < calculate.index(
        "observation.AfterAttackerBonusAmount = damage"
    )
    assert calculate.index("MeleeDamageBonusTaken(") < calculate.index(
        "observation.AfterTargetBonusAmount = damage"
    )
    assert calculate.index("ModifyMeleeDamage(") < calculate.index(
        "observation.AfterScriptHookAmount = damage"
    )
    assert calculate.index("CalcArmorReducedDamage(") < calculate.index(
        "observation.AfterArmorAmount = damageInfo->Damage"
    )
    assert calculate.index("RollMeleeOutcomeAgainst(") < calculate.index(
        "observation.AfterHitOutcomeAmount = damageInfo->Damage"
    )
    assert calculate.index("ApplyResilience(") < calculate.index(
        "observation.AfterResilienceAmount = damageInfo->Damage"
    )
    assert calculate.index("CalcAbsorbResist(") < calculate.index(
        "observation.ResolvedDamageAmount = damageInfo->Damage"
    )

    resolution = manager.split(
        "uint64 BotWorldPopulationMgr::NotifyCombatMeleeResolution", 1
    )[1].split("void BotWorldPopulationMgr::NotifyCombatDamage", 1)[0]
    assert "AddCombatLogAggregate" not in resolution
    assert 'AddCombatLogEvent("melee_resolution"' in resolution
    assert "0, 0, 0, nowMs" in resolution
    assert "return resolutionEventSequence;" in resolution

    attack = unit.split("void Unit::AttackerStateUpdate", 1)[1].split(
        "void Unit::HandleProcExtraAttackFor", 1
    )[0]
    assert attack.index("NotifyCombatMeleeResolution(damageInfo)") < attack.index(
        "DealMeleeDamage(&damageInfo, true, meleeResolutionEventSequence)"
    )
    deal = melee.split("void Unit::DealMeleeDamage", 1)[1]
    assert "durabilityLoss, resolutionEventSequence" in deal
    assert "relatedCombatEventSequence" in unit.split(
        "uint32 Unit::DealDamage", 1
    )[1].split("uint32 Unit::CalcMeleeAttackRageGain", 1)[0]
    damage = manager.split("void BotWorldPopulationMgr::NotifyCombatDamage", 1)[1]
    assert "sharedDamage, relatedEventSequence" in damage

    assert status.count('"combat_log_schema_version\\":4') == 2
    assert "AppendCombatLogEventJson(json, event);" in status
    assert "AppendCombatLogEventJson(" in status.split(
        "std::string BotWorldPopulationMgr::GetCombatLogDeltaJson", 1
    )[1]
    assert "BotMeleeResolutionEventJson::Append" in status
