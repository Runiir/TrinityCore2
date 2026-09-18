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
    assert '"combat_log_schema_version\\":7' in status
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


def test_actual_periodic_prepare_and_consumption_survive_nested_share(tmp_path):
    text = MODULE.read_text()
    pending = text[text.index("struct PendingPeriodicOutcome"):text.index("struct CalibrationExecuteHealthWindow")]
    prepare = text[text.index("void BotWorldPopulationMgr::PrepareCombatPeriodicOutcome"):text.index("uint64 BotWorldPopulationMgr::NotifyCombatMeleeResolution")]
    consume = text[text.index("void BotWorldPopulationMgr::NotifyCombatDamage"):]
    consume = consume[:consume.index("    if (!Cohort().Active")]
    consume = consume.replace("void BotWorldPopulationMgr::NotifyCombatDamage", "CombatLogLandedDamageObservation Consume").replace("        return;", "        return {};")
    consume += "    return landedDamage;\n}\n"
    prepare = prepare.replace("BotWorldPopulationMgr::", "")
    contract = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCohortScopeContract.cpp").read_text()
    ownership = contract[contract.index("bool MatchesPendingOwnership"):].rsplit("}", 1)[0]
    planning = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrPlanningContracts.h").read_text()
    observation = planning[planning.index("    struct CombatLogLandedDamageObservation"):planning.index("    struct CombatLogEvent")]
    unit = (ROOT / "src/server/game/Entities/Unit/Unit.cpp").read_text()
    deal = unit[unit.index("uint32 Unit::DealDamage("):unit.index("uint32 Unit::DealDamage(") + 24000]
    assert deal.index("NotifyCombatDamage") < deal.index("ModifyHealth(-(int32)damage)")
    assert deal.index("SPELL_AURA_SHARE_DAMAGE_PCT") < deal.index("NotifyCombatDamage")
    source = '''#include <cassert>
#include <cstdint>
#include <string>
#include <string_view>
#include <utility>
using uint32=std::uint32_t; using uint64=std::uint64_t;
constexpr uint32 DOT=2, NODAMAGE=3;
struct Unit { uint32 health=200, max=1000; uint32 GetHealth(){return health;} uint32 GetMaxHealth(){return max;} };
struct State { std::string Id="raid"; uint64 AttemptId=1; } state;
State& Cohort(){return state;}
using CohortScope=bool;
bool ScopeCallbackCohort(Unit*,Unit*){return true;}
namespace BotWorldCohortScope { ''' + ownership + "}\n" + observation + pending + prepare + consume + '''
int main() {
 Unit a,v,share,other; auto arm=[&]{PrepareCombatPeriodicOutcome(&a,&v,1120,true,27.5f);};
 auto original=[&]{return Consume(&a,&v,1120,42,84,DOT,32,0);};
 arm(); auto nested=Consume(&a,&share,999,12,12,NODAMAGE,32,0);
 assert(!nested.CriticalOutcomeAvailable && PendingOutcome.Armed);
 auto result=original(); assert(result.CriticalOutcomeAvailable && result.Critical && result.CritChancePct==27.5f);
 assert(result.TargetHealthBeforeDamage==200 && result.TargetMaxHealth==1000);
 assert(!original().CriticalOutcomeAvailable);
 for(int mismatch=0;mismatch<6;++mismatch) {
  arm(); if(mismatch==0)state.Id="other"; if(mismatch==1)state.AttemptId=2;
  auto r=Consume(mismatch==2?&other:&a,mismatch==3?&other:&v,mismatch==4?999:1120,42,84,mismatch==5?NODAMAGE:DOT,32,0);
  assert(!r.CriticalOutcomeAvailable && PendingOutcome.Armed);
  state.Id="raid";state.AttemptId=1; assert(original().CriticalOutcomeAvailable);
 }
 arm(); PrepareCombatPeriodicOutcome(&a,&share,999,false,12.5f);
 assert(!original().CriticalOutcomeAvailable);
 auto next=Consume(&a,&share,999,10,10,DOT,32,0);
 assert(next.CriticalOutcomeAvailable && !next.Critical && next.CritChancePct==12.5f);
}
'''
    cpp = tmp_path / "pending.cpp"
    cpp.write_text(source)
    binary = tmp_path / "pending"
    subprocess.run(["g++", "-std=c++17", str(cpp), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

    # Recompile the actual previous consumption predicate: the nested callback
    # steals the slot before its tuple is checked. It must fail this same fixture.
    old = source.replace("        && PendingOutcome.Attacker == attacker && PendingOutcome.Victim == victim\n        && PendingOutcome.SpellId == spellId && damageType == uint32(DOT)\n", "")
    assert old != source
    cpp.write_text(old)
    subprocess.run(["g++", "-std=c++17", str(cpp), "-o", str(binary)], check=True)
    assert subprocess.run([str(binary)], capture_output=True).returncode != 0
