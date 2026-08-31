from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_native_boss_attempt_and_planning_epochs(tmp_path: Path) -> None:
    source = tmp_path / "boss_attempt_epoch.cpp"
    binary = tmp_path / "boss_attempt_epoch"
    source.write_text(
        r'''
#include "Instances/InstanceScript.h"
#include <cassert>

int main()
{
    using InstanceEncounterLifecycle::CurrentOrNextEncounterEpoch;
    using InstanceEncounterLifecycle::NextAttemptEpoch;

    EncounterState state = NOT_STARTED;
    uint64 attempts = 0;
    assert(CurrentOrNextEncounterEpoch(state, attempts) == 1);

    attempts = NextAttemptEpoch(state, IN_PROGRESS, attempts);
    state = IN_PROGRESS;
    assert(attempts == 1);
    assert(CurrentOrNextEncounterEpoch(state, attempts) == 1);

    attempts = NextAttemptEpoch(state, FAIL, attempts);
    state = FAIL;
    assert(attempts == 1);
    assert(CurrentOrNextEncounterEpoch(state, attempts) == 2);

    attempts = NextAttemptEpoch(state, NOT_STARTED, attempts);
    state = NOT_STARTED;
    assert(attempts == 1);
    assert(CurrentOrNextEncounterEpoch(state, attempts) == 2);

    attempts = NextAttemptEpoch(state, IN_PROGRESS, attempts);
    state = IN_PROGRESS;
    assert(attempts == 2);
    assert(CurrentOrNextEncounterEpoch(state, attempts) == 2);

    attempts = NextAttemptEpoch(state, DONE, attempts);
    state = DONE;
    assert(attempts == 2);
    assert(CurrentOrNextEncounterEpoch(state, attempts) == 2);

    assert(NextAttemptEpoch(SPECIAL, IN_PROGRESS, attempts) == attempts);
    assert(NextAttemptEpoch(TO_BE_DECIDED, IN_PROGRESS, attempts) == attempts);
    assert(NextAttemptEpoch(IN_PROGRESS, NOT_STARTED, 3) == 3);
    assert(CurrentOrNextEncounterEpoch(NOT_STARTED, 3) == 4);
    assert(CurrentOrNextEncounterEpoch(DONE, 0) == 0);
    assert(CurrentOrNextEncounterEpoch(SPECIAL, attempts) == 0);
    assert(CurrentOrNextEncounterEpoch(TO_BE_DECIDED, attempts) == 0);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            "-I", str(ROOT / "src/server/game/Maps"),
            "-I", str(ROOT / "src/server/shared"),
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


def test_instance_writer_owns_attempt_counter() -> None:
    header = (ROOT / "src/server/game/Instances/InstanceScript.h").read_text()
    core = (ROOT / "src/server/game/Instances/InstanceScript.cpp").read_text()

    assert "uint64 attemptEpoch;" in header
    assert "GetBossAttemptEpoch(uint32 id)" in header
    assert "GetLifecycleEpoch() const" in header
    assert "InstanceEncounterLifecycle::NextAttemptEpoch(" in core
    assert "BuildInstanceLifecycleEpoch()" in core
    assert core.index("if (bossInfo->state == state)") < core.index(
        "InstanceEncounterLifecycle::NextAttemptEpoch(")
