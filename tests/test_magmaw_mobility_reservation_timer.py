from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MAGMAW_DIR = ROOT / (
    "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
)
BOSS = MAGMAW_DIR / "boss_magmaw.cpp"
SPELLS = MAGMAW_DIR / "boss_magmaw_encounter_spells.cpp"
SHARED = MAGMAW_DIR / "boss_magmaw_shared.h"
UNIT_AI = ROOT / "src/server/game/AI/CoreAI/UnitAI.h"
BLACKBOARD = ROOT / "src/server/game/Bots/BotEncounterBlackboard.h"
PUBLISHER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrEncounterBlackboard.cpp"
RESERVATION = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/"
    "BotMagmawMobilityReservation.h"
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def test_magmaw_script_split_preserves_registration_and_size_contract() -> None:
    boss = text(BOSS)
    spells = text(SPELLS)
    shared = text(SHARED)

    assert len(boss.splitlines()) < 1000
    assert len(spells.splitlines()) < 1000
    assert len(shared.splitlines()) < 1000
    assert '#include "boss_magmaw_shared.h"' in boss
    assert "void AddSC_boss_magmaw_encounter_spells();" in boss
    assert "AddSC_boss_magmaw_encounter_spells();" in boss

    registration = function_body(spells, "void AddSC_boss_magmaw_encounter_spells()")
    expected = (
        "spell_magmaw_pillar_of_flame_forcecast",
        "spell_magmaw_ride_vehicle",
        "spell_magmaw_launch_hook",
        "spell_magmaw_eject_passenger",
        "spell_magmaw_lava_parasite",
        "spell_magmaw_lava_parasite_summon",
        "spell_magmaw_blazing_inferno_targeting",
        "spell_magmaw_shadow_breath_targeting",
        "spell_magmaw_massive_crash",
        "spell_magmaw_impale_self",
        "spell_magmaw_captured",
    )
    offsets = [registration.index(name) for name in expected]
    assert offsets == sorted(offsets)

    missile_module = text(MAGMAW_DIR / "spell_magmaw_magma_spit.cpp")
    assert "void AddSC_boss_magmaw_spells()" in missile_module
    assert "RegisterSpellScript(spell_magmaw_magma_spit_missile);" in missile_module


def test_magmaw_publishes_the_authoritative_native_sequence_timer() -> None:
    boss = text(BOSS)
    timer = function_body(boss, "GetTimeUntilEncounterMechanic(")
    assert "spellId != SPELL_MASSIVE_CRASH" in timer
    assert "events.GetTimeUntilEvent(EVENT_MANGLE)" in timer
    assert "events.GetTimeUntilEvent(EVENT_PREPARE_MASSIVE_CRASH)" in timer
    assert "events.GetTimeUntilEvent(EVENT_MASSIVE_CRASH)" in timer
    assert "return 0;" in timer
    assert "_nextMangle" not in boss
    assert "_mangleTimer" not in boss

    unit_ai = text(UNIT_AI)
    assert "GetTimeUntilEncounterMechanic" in unit_ai
    assert "std::numeric_limits<uint32>::max()" in unit_ai

    blackboard = text(BLACKBOARD)
    assert "struct MechanicTimerSnapshot" in blackboard
    assert "std::vector<MechanicTimerSnapshot> MechanicTimers" in blackboard
    assert "FindMechanicTimer" in blackboard

    publisher = text(PUBLISHER)
    observation = function_body(publisher, "AppendNativeMechanicTimers(")
    assert 'route.NodeId != "bwd.magmaw.encounter"' in observation
    assert "creature.GetEntry() != MagmawEntry" in observation
    assert "GetTimeUntilEncounterMechanic" in observation
    assert "MagmawMassiveCrashSpell" in observation
    assert "remainingMs == 0" in observation


def test_reservation_uses_caller_supplied_native_reuse_cooldown(
    tmp_path: Path,
) -> None:
    source = tmp_path / "magmaw_mobility_reservation.cpp"
    binary = tmp_path / "magmaw_mobility_reservation"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMobilityReservation.h"
#include <cassert>
#include <limits>

using namespace BotEncounter;

int main()
{
    MechanicTimerSnapshot distant{ 88253, 15000, false,
        FactSource::NativeInstanceState };
    assert(EvaluateMagmawMobilityReservation(&distant, 15000, false)
        == MagmawMobilityDecision::AllowRoutine);

    MechanicTimerSnapshot soon = distant;
    soon.RemainingMs = 14999;
    assert(EvaluateMagmawMobilityReservation(&soon, 15000, false)
        == MagmawMobilityDecision::ReserveForMassiveCrash);

    MechanicTimerSnapshot active = distant;
    active.RemainingMs = 0;
    active.SequenceActive = true;
    assert(EvaluateMagmawMobilityReservation(&active, 15000, false)
        == MagmawMobilityDecision::ReserveForMassiveCrash);
    assert(EvaluateMagmawMobilityReservation(&active, 15000, true)
        == MagmawMobilityDecision::AllowEmergency);

    assert(EvaluateMagmawMobilityReservation(nullptr, 15000, false)
        == MagmawMobilityDecision::ReserveMissingNativeTimer);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/common/Utilities"),
            "-I",
            str(ROOT / "src/common/Logging"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)

    helper = text(RESERVATION)
    assert "nativeReuseCooldownMs" in helper
    assert "1953" not in helper
    assert "781" not in helper
    assert "15000" not in helper
