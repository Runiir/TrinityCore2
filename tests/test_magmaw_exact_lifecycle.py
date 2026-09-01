from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_magmaw_blackboard_uses_exact_native_lifecycle_source() -> None:
    header = (ROOT / "src/server/game/Instances/InstanceScript.h").read_text()
    board_header = (ROOT / "src/server/game/Bots/BotEncounterBlackboard.h").read_text()
    publisher = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrEncounterBlackboard.cpp").read_text()
    bwd_header = (ROOT / "src/server/scripts/EasternKingdoms/"
        "BlackrockMountain/BlackwingDescent/blackwing_descent.h").read_text()
    bwd_instance = (ROOT / "src/server/scripts/EasternKingdoms/"
        "BlackrockMountain/BlackwingDescent/instance_blackwing_descent.cpp").read_text()

    assert "CurrentOrNextEncounterEpoch" in header
    assert "GetBossAttemptEpoch(uint32 id)" in header
    assert "std::optional<NativeEncounterLifecycle> NativeEncounter;" in board_header
    assert "ObserveMagmawLifecycle(*observer, _serverEpoch," in publisher
    assert "instance->GetBossState(MagmawBossId)" in publisher
    assert "instance->GetBossAttemptEpoch(MagmawBossId)" in publisher
    assert "instance->GetLifecycleEpoch()" in publisher
    assert "lifecycle.ServerEpoch = serverEpoch;" in publisher
    assert "lifecycle.InstanceLifecycleEpoch = instanceLifecycleEpoch;" in publisher
    assert "lifecycle.EncounterEpoch = encounterEpoch;" in publisher
    assert "BotMagmawLifecycleIdentity::EncounterId" in publisher
    assert "lifecycle.EncounterEpoch = Cohort().Raid.BossResetGeneration" not in publisher
    assert "attemptEpoch = Cohort().Raid.BossResetGeneration" not in publisher

    assert "DATA_MAGMAW                     = 0" in bwd_header
    assert "{ BOSS_MAGMAW,                              DATA_MAGMAW" in bwd_instance


def test_lifecycle_identity_changes_across_restart_and_recreation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "magmaw_lifecycle_identity.cpp"
    binary = tmp_path / "magmaw_lifecycle_identity"
    source.write_text(
        r'''
#include "Bots/BotEncounterBlackboard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawLifecycleIdentity.h"
#include <cassert>

int main()
{
    assert(BotMagmawLifecycleIdentity::OwnsRoute(
        669, "bwd.magmaw.encounter"));
    assert(!BotMagmawLifecycleIdentity::OwnsRoute(
        669, "bwd.atramedes.encounter"));
    assert(!BotMagmawLifecycleIdentity::OwnsRoute(
        670, "bwd.magmaw.encounter"));

    BotEncounter::NativeEncounterLifecycle first;
    first.Id = "blackwing_descent.magmaw";
    first.BossId = 0;
    first.BossEntry = 41570;
    first.ServerEpoch = 100;
    first.InstanceLifecycleEpoch = 7;
    first.EncounterEpoch = 1;
    first.Authoritative = true;
    assert(first.HasExactIdentity());

    auto restarted = first;
    restarted.ServerEpoch = 101;
    assert(!first.SameEpochIdentity(restarted));

    auto recreated = first;
    recreated.InstanceLifecycleEpoch = 8;
    assert(!first.SameEpochIdentity(recreated));

    auto nextAttempt = first;
    nextAttempt.EncounterEpoch = 2;
    assert(!first.SameEpochIdentity(nextAttempt));

    auto same = first;
    same.AttemptEpoch = 1;
    assert(first.SameEpochIdentity(same));
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/common/Utilities"),
            "-I", str(ROOT / "src/common/Logging"),
            "-I", str(ROOT / "src/common/Debugging"),
            str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_raw_exact_lifecycle_is_reduced_before_task_consumption() -> None:
    consumers = []
    for path in (ROOT / "src/server").rglob("*"):
        if path.suffix not in {".cpp", ".h"}:
            continue
        text = path.read_text()
        if "->NativeEncounter =" in text or "board.NativeEncounter" in text:
            consumers.append(path.relative_to(ROOT).as_posix())
    assert consumers == [
        "src/server/game/Bots/BotWorldPopulationMgrEncounterBlackboard.cpp",
        "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.cpp",
    ]
