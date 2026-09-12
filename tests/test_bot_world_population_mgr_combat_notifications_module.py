from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatNotifications.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
ATTRIBUTION = ROOT / "src/server/game/Bots/BotCombatDamageAttribution.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "NotifyCombatAttackAttempt",
    "NotifyCombatDamage",
    "NotifyCombatHeal",
)


def test_combat_notifications_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCombatNotifications.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_combat_notifications_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_combat_notifications_keep_calibration_and_party_log_contract():
    text = MODULE.read_text()
    for marker in (
        "CalibrationFixtureTargetAttackEventCount",
        "CalibrationFixtureTargetGuid",
        "HealResponseLatenciesMs",
        "HealingDone",
        "HealingReceived",
        "CombatOwnerPlayer",
        "FindCombatLogCohortPlayer",
        "CalibrationSingleTargetDurationMs",
        "CalibrationExecuteHealthWindowIndex",
        "UpdateCalibrationTargetHealthSchedule",
        "CalibrationExcludedBoundaryDamageEventCount",
        "PrimaryTargetDamage",
        "OffTargetDamageEvents",
        "DamageEventSampleCount",
        "AddCombatLogEvent",
        "FriendlyDamageDone",
        "BotCombatDamageAttribution::NativeRelationship",
        "IsFriendlyOrCohortTarget",
    ):
        assert marker in text


def test_combat_damage_perspective_schema_keeps_legacy_values_and_adds_friendly_split():
    planning = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrPlanningContracts.h").read_text()
    status = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrStatus.cpp").read_text()
    assert "DamageDone = 0" in planning
    assert "DamageTaken = 1" in planning
    assert "HealingDone = 2" in planning
    assert "HealingReceived = 3" in planning
    assert "FriendlyDamageDone = 4" in planning
    assert '"friendly_damage_done"' in status
    assert '"combat_log_schema_version\\":4' in status
    assert '"damage_attribution_schema\\":\\"originated_amount_v2_friendly_split\\"' in status


def test_native_damage_attribution_fixture_compiles_and_classifies_relationships():
    source = r'''
#include "BotCombatDamageAttribution.h"

int main()
{
    using BotCombatDamageAttribution::IsFriendlyOrCohortTarget;
    using BotCombatDamageAttribution::NativeRelationship;
    struct Case { NativeRelationship relation; bool friendly; };
    Case cases[] = {
        // Hostile creature, neutral attackable creature, boss body, exposed
        // head, and parasite: native friendship is false, so all remain DPS.
        {{false, false, false, false}, false},
        {{false, false, false, false}, false},
        {{false, false, false, false}, false},
        {{false, false, false, false}, false},
        {{false, false, false, false}, false},
        // Cohort player, another actor's pet, own pet, and self damage.
        {{false, true, false, false}, true},
        {{false, true, false, false}, true},
        {{false, true, false, false}, true},
        {{true, false, false, false}, true},
        // A charmed cohort target stays cohort-relative even when native
        // charm makes the units hostile in one direction.
        {{false, true, false, false}, true},
        // Trinity's relationship is symmetric: either direction is enough.
        {{false, false, true, false}, true},
        {{false, false, false, true}, true},
    };
    for (Case const& test : cases)
        if (IsFriendlyOrCohortTarget(test.relation) != test.friendly)
            return 1;
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as directory:
        source_path = Path(directory) / "damage_attribution_fixture.cpp"
        binary_path = Path(directory) / "damage_attribution_fixture"
        source_path.write_text(source, encoding="utf-8")
        compile_result = subprocess.run(
            [
                "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-I", str(ATTRIBUTION.parent), str(source_path),
                "-o", str(binary_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert compile_result.returncode == 0, compile_result.stderr
        run_result = subprocess.run(
            [str(binary_path)], capture_output=True, text=True, check=False,
        )
        assert run_result.returncode == 0, run_result.stderr
