"""Chimaeron: Feud must not consume Mortality's opening Double Attack (10N).

On 10N a Double Attack that comes due while Feud is up is not cast. In phase
one that is the researched behaviour (WCL: no Double Attack inside Feud, the
15 s timer keeps running). At the 20% transition the script schedules the
opening Mortality Double Attack 1 ms out; if Feud is still running the skip
consumed it and rescheduled the 15 s repeat, so the first Mortality Double
Attack landed 10 s after Feud ended instead of at expiry. The fix holds that
attack for ACTION_END_FEUD (Logic::HoldsDoubleAttackForFeudEnd).

The production DamageTaken, DoAction, UpdateAI and Initialize bodies and the
production private members are compiled against the real EventMap; only the
actors and spell execution are stubbed. Three sources run the same scenarios:
the current script, the base commit (c8e8bfe85b) for the difficulties that must
stay byte-identical, and the current script with the hold removed (the
reviewer's defect), which must fail the scenario.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
SCRIPT = SCRIPTS / "boss_chimaeron.cpp"
BASE_COMMIT = "c8e8bfe85b"
BASE_PATH = SCRIPT.relative_to(ROOT).as_posix()

SPELL_BREAK = 82881
SPELL_DOUBLE_ATTACK = 88826
DIFFICULTY_10N, DIFFICULTY_25N, DIFFICULTY_10H, DIFFICULTY_25H = 0, 1, 2, 3
OTHER_MODES = (DIFFICULTY_25N, DIFFICULTY_10H, DIFFICULTY_25H)

# Exactly the block the fix added to EVENT_DOUBLE_ATTACK; removing it restores
# the consumed-opening-attack defect.
HOLD_BLOCK = """                    if (Logic::HoldsDoubleAttackForFeudEnd(IsTenNormal(), _isInFeud, events.IsInPhase(PHASE_2)))
                    {
                        _doubleAttackHeldByFeud = true;
                        break;
                    }
"""


def body(source: str, signature: str, start: int = 0) -> str:
    """The braced block that follows `signature`, braces included."""
    begin = source.index("{", source.index(signature, start))
    depth = 0
    for index in range(begin, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[begin:index + 1]
    raise AssertionError(signature)


HARNESS_HEAD = r'''
#include "EventMap.h"
#include "boss_chimaeron_logic.h"
#include <cstdio>
#include <cstdlib>
#include <vector>

namespace Logic = BlackwingDescent::Chimaeron::Logic;

// EventMap.cpp draws randomized delays through urand; nothing here uses them.
uint32 urand(uint32 min, uint32) { return min; }

constexpr int UNIT_STATE_CASTING = 1, REACT_PASSIVE = 0, REACT_AGGRESSIVE = 1, SELECT_TARGET_RANDOM = 0;
constexpr int DATA_LORD_VICTOR_NEFARIUS_GENERIC = 1;
constexpr int RAID_DIFFICULTY_10MAN_NORMAL = 0, RAID_DIFFICULTY_25MAN_NORMAL = 1,
              RAID_DIFFICULTY_10MAN_HEROIC = 2, RAID_DIFFICULTY_25MAN_HEROIC = 3;

struct Player { };
struct Unit { };
struct AIHandle { void DoAction(int) { } };
struct Creature
{
    bool casting = false;
    bool crossing = false;
    bool IsAIEnabled() const { return true; }
    AIHandle* AI() { static AIHandle handle; return &handle; }
    bool HasUnitState(int) const { return casting; }
    bool HealthBelowPctDamaged(int, uint32) const { return crossing; }
    void InterruptNonMeleeSpells(bool) { }
    void SetReactState(int) { }
    Player* SelectNearestPlayer(float) { return nullptr; }
};
struct Instance { Creature* GetCreature(int) { return nullptr; } };
struct NonTankTargetSelector { explicit NonTankTargetSelector(Creature*) { } };

struct Cast { uint32 at; int spell; };
'''

HARNESS_BOSS = r'''
struct Boss
{
    Creature actor;
    Creature* me = &actor;
    Instance inst;
    Instance* instance = &inst;
    EventMap events;
    int difficulty = 0;
    std::vector<Cast> casts;

    int GetDifficulty() const { return difficulty; }
    bool IsHeroic() const { return false; }
    bool UpdateVictim() { return true; }
    void SetMortalityTauntImmunity(bool) { }
    void Talk(int) { }
    void AttackStart(Player*) { }
    void DoMeleeAttackIfReady() { }
    template <class Selector> Creature* SelectTarget(int, int, Selector const&) { return me; }
    void Record(int spell) { casts.push_back({ events.GetTimer(), spell }); }
    void DoCastAOE(int spell, bool = false) { Record(spell); }
    void DoCastSelf(int spell, bool = false) { Record(spell); }
    void DoCastVictim(int spell) { Record(spell); }

    void Initialize()
'''

HARNESS_MAIN = r'''
static void Run(Boss& boss, uint32 ms)
{
    for (uint32 done = 0; done < ms; done += 100)
        boss.UpdateAI(100);
}

static void Print(char const* scenario, Boss const& boss)
{
    for (Cast const& cast : boss.casts)
        std::printf("%s cast %u %d\n", scenario, cast.at, cast.spell);
}

static void Cross20Percent(Boss& boss)
{
    boss.actor.crossing = true;
    uint32 damage = 1;
    boss.DamageTaken(nullptr, damage);
    boss.actor.crossing = false;
}

int main(int argc, char** argv)
{
    int const difficulty = argc > 1 ? std::atoi(argv[1]) : 0;

    // feud_into_mortality: Feud (30 s) runs from the pull; Mortality starts
    // with 5 s of it left. Feud expires at 30 s.
    {
        Boss b; b.difficulty = difficulty;
        b.events.SetPhase(PHASE_1);
        b.events.ScheduleEvent(EVENT_DOUBLE_ATTACK, 5s, 0, PHASE_1);
        b.DoAction(ACTION_START_FEUD);
        Run(b, 25000);
        Cross20Percent(b);
        Run(b, 5000);
        b.DoAction(ACTION_END_FEUD);
        Run(b, 30000);
        Print("feud_into_mortality", b);
    }

    // mortality_outside_feud: no Feud at the transition.
    {
        Boss b; b.difficulty = difficulty;
        b.events.SetPhase(PHASE_1);
        b.events.ScheduleEvent(EVENT_DOUBLE_ATTACK, 5s, 0, PHASE_1);
        Run(b, 20000);
        Cross20Percent(b);
        Run(b, 40000);
        Print("mortality_outside_feud", b);
    }

    // feud_after_mortality: a Massacre in flight starts Feud after the
    // transition; the 15 s repeat then falls inside it. Feud: 10 s to 40 s.
    {
        Boss b; b.difficulty = difficulty;
        b.events.SetPhase(PHASE_1);
        Cross20Percent(b);
        Run(b, 10000);
        b.DoAction(ACTION_START_FEUD);
        Run(b, 30000);
        b.DoAction(ACTION_END_FEUD);
        Run(b, 30000);
        Print("feud_after_mortality", b);
    }

    // phase_one_feud: Feud from 0 s to 30 s while still in phase one. The
    // phase-one skip and its running timer are the researched 10N behaviour.
    {
        Boss b; b.difficulty = difficulty;
        b.events.SetPhase(PHASE_1);
        b.events.ScheduleEvent(EVENT_BREAK, 5s, 0, PHASE_1);
        b.events.ScheduleEvent(EVENT_DOUBLE_ATTACK, 5s, 0, PHASE_1);
        b.DoAction(ACTION_START_FEUD);
        Run(b, 30000);
        b.DoAction(ACTION_END_FEUD);
        Run(b, 30000);
        Print("phase_one_feud", b);
    }

    // reset_clears_hold: an evade between the held attack and Feud expiry must
    // leave nothing scheduled (Reset() = events.Reset() then Initialize()).
    {
        Boss b; b.difficulty = difficulty;
        b.events.SetPhase(PHASE_1);
        b.DoAction(ACTION_START_FEUD);
        Cross20Percent(b);
        Run(b, 1000);
        b.events.Reset();
        b.Initialize();
        b.DoAction(ACTION_END_FEUD);
        std::printf("reset_clears_hold empty %d\n", b.events.Empty() ? 1 : 0);
    }
    return 0;
}
'''


def enum_block(source: str, name: str) -> str:
    return f"enum {name} " + body(source, f"enum {name}\n") + ";\n"


def harness(source: str) -> str:
    boss = body(source, "struct boss_chimaeron : public BossAI")
    members = boss[boss.rindex("private:"):-1]
    enums = "".join(enum_block(source, name) for name in ("Spells", "Texts", "Phases", "Events", "Actions"))
    return (HARNESS_HEAD + enums + HARNESS_BOSS
            + body(boss, "void Initialize()") + "\n"
            + "    void DamageTaken(Unit*, uint32& damage)\n" + body(boss, "void DamageTaken(") + "\n"
            + "    void DoAction(int32 action)\n" + body(boss, "void DoAction(int32 action) override") + "\n"
            + "    void UpdateAI(uint32 diff)\n" + body(boss, "void UpdateAI(uint32 diff) override") + "\n"
            + members + "};\n" + HARNESS_MAIN)


SANITIZERS = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
              "-g", "-O1"]


def build(source: str, tmp_path: Path, name: str, sanitize: bool = False) -> Path:
    cpp = tmp_path / f"{name}.cpp"
    exe = tmp_path / name
    cpp.write_text(harness(source), encoding="utf-8")
    result = subprocess.run(
        ["g++", "-std=c++17", *(SANITIZERS if sanitize else []),
         "-I" + str(ROOT / "src/common"), "-I" + str(ROOT / "src/common/Utilities"),
         "-I" + str(SCRIPTS), str(cpp), str(ROOT / "src/common/Utilities/EventMap.cpp"), "-o", str(exe)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return exe


def run(exe: Path, difficulty: int) -> dict[str, list]:
    output = subprocess.run([str(exe), str(difficulty)], capture_output=True, text=True, check=True).stdout
    scenarios: dict[str, list] = {}
    for line in output.splitlines():
        scenario, kind, *rest = line.split()
        if kind == "cast":
            scenarios.setdefault(scenario, []).append((int(rest[0]), int(rest[1])))
        else:
            scenarios[scenario] = int(rest[0])
    return scenarios


def double_attacks(scenario: list) -> list[int]:
    return [at for at, spell in scenario if spell == SPELL_DOUBLE_ATTACK]


def base_source() -> str:
    result = subprocess.run(["git", "show", f"{BASE_COMMIT}:{BASE_PATH}"], cwd=ROOT,
                            capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(f"base commit {BASE_COMMIT} is not available in this checkout")
    return result.stdout


@pytest.fixture(scope="module")
def current(tmp_path_factory) -> Path:
    return build(SCRIPT.read_text(encoding="utf-8"), tmp_path_factory.mktemp("current"), "current")


def test_scenarios_run_clean_under_the_sanitizers(current: Path, tmp_path: Path) -> None:
    exe = build(SCRIPT.read_text(encoding="utf-8"), tmp_path, "sanitized", sanitize=True)
    for difficulty in (DIFFICULTY_10N, *OTHER_MODES):
        assert run(exe, difficulty) == run(current, difficulty)


def test_hold_block_is_in_the_script() -> None:
    assert HOLD_BLOCK in SCRIPT.read_text(encoding="utf-8")


def test_feud_running_at_the_transition_gives_one_double_attack_at_feud_expiry(current: Path) -> None:
    scenario = run(current, DIFFICULTY_10N)["feud_into_mortality"]
    # Phase one skipped its Double Attacks inside Feud; the opening Mortality
    # Double Attack (1 ms after the 25 s transition) is held, not cast and not
    # consumed. Feud expires at 30 s (the first tick after it is 30.1 s).
    assert [at for at in double_attacks(scenario) if at < 30000] == []
    # One cast on the first update after Feud ends, then the 15 s cycle.
    assert double_attacks(scenario) == [30100, 45100]


def test_reviewer_defect_is_reproduced_when_the_hold_is_removed(tmp_path: Path) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert HOLD_BLOCK in source
    exe = build(source.replace(HOLD_BLOCK, ""), tmp_path, "prefix")
    scenario = run(exe, DIFFICULTY_10N)["feud_into_mortality"]
    # The opening attack was consumed at 25 s: no cast at Feud expiry, and the
    # first Mortality Double Attack lands ten seconds after Feud ended.
    assert [at for at in double_attacks(scenario) if 30000 <= at < 40000] == []
    assert double_attacks(scenario) == [40100, 55100]


def test_no_feud_at_the_transition_still_casts_the_opening_attack_at_once(current: Path) -> None:
    scenario = run(current, DIFFICULTY_10N)["mortality_outside_feud"]
    # Phase-one Double Attack at 5 s and 20 s; Mortality at 20 s casts the
    # opening attack one tick later and then every 15 s.
    assert double_attacks(scenario) == [5000, 20000, 20100, 35100, 50100]


def test_feud_starting_after_the_transition_holds_the_repeat_to_expiry(current: Path) -> None:
    scenario = run(current, DIFFICULTY_10N)["feud_after_mortality"]
    # Opening attack at 0.1 s; the repeat due at 15.1 s falls inside Feud
    # (10-40 s) and is held; the cycle restarts when Feud ends at 40 s.
    assert double_attacks(scenario) == [100, 40100, 55100]


def test_phase_one_keeps_the_researched_skip_and_running_timers(current: Path) -> None:
    scenario = run(current, DIFFICULTY_10N)["phase_one_feud"]
    # Break and Double Attack at 5 s and 20 s are skipped inside Feud (0-30 s);
    # their timers kept running, so the next ones land on the 15 s grid.
    assert double_attacks(scenario) == [35000, 50000]
    assert [at for at, spell in scenario if spell == SPELL_BREAK] == [35000, 50000]


def test_reset_clears_a_held_double_attack(current: Path) -> None:
    assert run(current, DIFFICULTY_10N)["reset_clears_hold"] == 1


@pytest.mark.parametrize("difficulty", OTHER_MODES)
def test_other_modes_behave_exactly_as_at_the_base_commit(current: Path, tmp_path: Path, difficulty: int) -> None:
    base = build(base_source(), tmp_path, "base")
    new, old = run(current, difficulty), run(base, difficulty)
    assert new == old
    # The control is meaningful: the base script casts inside Feud in these
    # modes (Feud 25-30 s here), including the opening Mortality attack.
    feud_into_mortality = old["feud_into_mortality"]
    assert any(25000 <= at < 30000 for at in double_attacks(feud_into_mortality))
    assert double_attacks(old["phase_one_feud"])[:2] == [5000, 20000]
