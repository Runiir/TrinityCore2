"""Chimaeron: the round-3 WCL rules apply to 10N only.

The 2026-09-30 research resolved three rules for Normal 10 player alone: the
Bile-O-Tron knockout cycle (0/50/100%), the 6 s Caustic Slime repeat and Feud
skipping Break and Double Attack. 25N, 10H and 25H must behave exactly as they
did at base c8e8bfe85b. The no-berserk decision is separate (every mode) and is
covered in test_chimaeron_research_data.py.

Three layers:
- source structure: every gated site asks IsTenNormal(), the idiom the other
  BWD scripts use (boss_maloriak.cpp, boss_nefarians_end.cpp);
- mutation: putting any of the three ungated sites back makes the structure
  check fail, so the check catches the defect it was written for;
- base parity: the previous rules are read out of the base commit and compared
  with what the compiled logic header returns for every mode but 10N.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
SCRIPT = SCRIPTS / "boss_chimaeron.cpp"
BASE_COMMIT = "c8e8bfe85b"
BASE_PATH = SCRIPT.relative_to(ROOT).as_posix()

TEN_NORMAL_PREDICATE = "bool IsTenNormal() const { return GetDifficulty() == RAID_DIFFICULTY_10MAN_NORMAL; }"
KNOCKOUT_ROLL = "roll_chance_i(Logic::KnockoutChancePct(IsTenNormal(), _massacresInCycle))"
SLIME_REPEAT = "events.Repeat(Logic::CausticSlimeRepeatMs(IsTenNormal()));"
FEUD_GATE = "if (!Logic::SkipsBreakAndDoubleAttack(IsTenNormal(), _isInFeud))"
# Mortality holds a Double Attack that comes due inside Feud until Feud ends
# (test_chimaeron_mortality_double_attack.py); the hold is 10N-gated too.
HOLD_GATE = "if (Logic::HoldsDoubleAttackForFeudEnd(IsTenNormal(), _isInFeud, events.IsInPhase(PHASE_2)))"
FEUD_CASTS = (("EVENT_BREAK", "DoCastVictim(SPELL_BREAK);"),
              ("EVENT_DOUBLE_ATTACK", "DoCastSelf(SPELL_DOUBLE_ATTACK, true);"))

# Each entry puts one round-3 rule back to its ungated, all-mode form.
UNGATED_VARIANTS = {
    "knockout": (KNOCKOUT_ROLL, "roll_chance_i(Logic::KnockoutChancePct(_massacresInCycle))"),
    "slime_repeat": (SLIME_REPEAT, "events.Repeat(CausticSlimeRepeat);"),
    "feud_skip": (FEUD_GATE, "if (!_isInFeud)"),
    "mortality_hold": (HOLD_GATE, "if (_isInFeud && events.IsInPhase(PHASE_2))"),
}


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[brace + 1:index]
    raise AssertionError(signature)


def case_body(update: str, name: str) -> str:
    """The text of one `case` label up to the next label (or the end of the switch)."""
    start = update.index(f"case {name}:")
    following = [update.find(marker, start + 1) for marker in ("\n                case ", "\n                default:")]
    return update[start:min(index for index in following if index != -1)]


def assert_ten_normal_gating(source: str) -> None:
    """Raise AssertionError unless all three rules are gated to 10N."""
    assert TEN_NORMAL_PREDICATE in source
    # The only difficulty the script compares is 10N; no size or heroic gate
    # stands in for it.
    assert re.findall(r"RAID_DIFFICULTY_\w+", source) == ["RAID_DIFFICULTY_10MAN_NORMAL"]

    finished = function_body(source, "void OnSpellCastFinished(SpellInfo const* spell, SpellFinishReason reason) override")
    assert KNOCKOUT_ROLL in finished
    assert finished.count("roll_chance_i(") == 1

    update = function_body(source, "void UpdateAI(uint32 diff) override")
    slime = case_body(update, "EVENT_CAUSTIC_SLIME")
    assert SLIME_REPEAT in slime and slime.count("Repeat(") == 1

    for case, cast in FEUD_CASTS:
        body = case_body(update, case)
        assert body[:body.index(cast)].rstrip().endswith(FEUD_GATE), case
        rest = body.replace(FEUD_GATE, "")
        if case == "EVENT_DOUBLE_ATTACK":
            # The Mortality hold sits in front of the skip and asks the same
            # 10N predicate; nothing else may look at Feud.
            assert HOLD_GATE in body and body.index(HOLD_GATE) < body.index(FEUD_GATE)
            rest = rest.replace(HOLD_GATE, "")
        assert "_isInFeud" not in rest, case


def test_ten_normal_gating_holds_in_the_native_script() -> None:
    assert_ten_normal_gating(SCRIPT.read_text(encoding="utf-8"))


@pytest.mark.parametrize("rule", sorted(UNGATED_VARIANTS))
def test_gating_check_rejects_an_all_mode_variant(rule: str) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    gated, ungated = UNGATED_VARIANTS[rule]
    assert gated in source
    with pytest.raises(AssertionError):
        assert_ten_normal_gating(source.replace(gated, ungated))


def test_the_script_matches_the_difficulty_idiom_of_the_other_bwd_scripts() -> None:
    maloriak = (SCRIPTS / "boss_maloriak.cpp").read_text(encoding="utf-8")
    assert TEN_NORMAL_PREDICATE in maloriak
    assert "GetDifficulty() == RAID_DIFFICULTY_10MAN_NORMAL" in (SCRIPTS / "boss_nefarians_end.cpp").read_text(encoding="utf-8")


def test_the_no_berserk_decision_stays_for_every_mode() -> None:
    # A user decision for all modes: the difficulty gate must not creep into it.
    assert "berserk" not in SCRIPT.read_text(encoding="utf-8").lower()


# --- base parity -----------------------------------------------------------------

PARITY_PROGRAM = r'''
#include "boss_chimaeron_logic.h"
#include <cstdio>

using namespace BlackwingDescent::Chimaeron::Logic;

int main()
{
    for (unsigned n = 0; n <= 6; ++n)
        std::printf("knockout other %u %d\n", n, KnockoutChancePct(false, n));
    std::printf("slime other %u\n", CausticSlimeRepeatMs(false));
    for (int feud = 0; feud <= 1; ++feud)
    {
        std::printf("feud other %d %d\n", feud, SkipsBreakAndDoubleAttack(false, feud != 0) ? 1 : 0);
        for (int mortality = 0; mortality <= 1; ++mortality)
            std::printf("hold other %d %d %d\n", feud, mortality,
                HoldsDoubleAttackForFeudEnd(false, feud != 0, mortality != 0) ? 1 : 0);
    }
    return 0;
}
'''


def base_source() -> str:
    result = subprocess.run(["git", "show", f"{BASE_COMMIT}:{BASE_PATH}"], cwd=ROOT,
                            capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(f"base commit {BASE_COMMIT} is not available in this checkout")
    return result.stdout


def compiled_other_mode_rules(tmp_path: Path) -> dict[str, int]:
    source = tmp_path / "chimaeron_parity.cpp"
    binary = tmp_path / "chimaeron_parity"
    source.write_text(PARITY_PROGRAM)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(SCRIPTS),
                    str(source), "-o", str(binary)], check=True, cwd=ROOT)
    output = subprocess.run([str(binary)], capture_output=True, text=True, check=True).stdout
    return {" ".join(line.split()[:-1]): int(line.split()[-1]) for line in output.splitlines()}


def test_other_modes_keep_the_base_knockout_progression(tmp_path: Path) -> None:
    base = base_source()
    start = int(re.search(r"_knockOutChance = (\d+);", base).group(1))
    step = int(re.search(r"_knockOutChance \+= (\d+);", base).group(1))
    assert (start, step) == (40, 20)
    rules = compiled_other_mode_rules(tmp_path)

    # Base script: the chance starts at `start`, grows by `step` on a miss and
    # returns to `start` after a knockout; 100% cannot miss. Walk every
    # miss/knockout history of ten Massacres and compare each roll's chance
    # with the cycle-count rule (position = Massacres since the last knockout).
    for history in range(1 << 10):
        chance, position = start, 0
        for massacre in range(10):
            position += 1
            assert chance <= 100 and rules[f"knockout other {position}"] == chance, (history, massacre)
            if chance >= 100 or history >> massacre & 1:
                chance, position = start, 0
            else:
                chance += step
    assert [rules[f"knockout other {n}"] for n in range(1, 6)] == [40, 60, 80, 100, 100]
    assert rules["knockout other 0"] == start


def test_other_modes_keep_the_base_slime_repeat_and_feud_casts(tmp_path: Path) -> None:
    base = base_source()
    rules = compiled_other_mode_rules(tmp_path)
    slime = base[base.index("case EVENT_CAUSTIC_SLIME:"):]
    slime = slime[:slime.index("break;")]
    assert rules["slime other"] == int(re.search(r"events\.Repeat\((\d+)s\);", slime).group(1)) * 1000
    # Base script: Break and Double Attack were cast unconditionally, Feud or not.
    for case, cast in FEUD_CASTS:
        body = base[base.index(f"case {case}:"):]
        body = body[:body.index("break;")]
        assert cast in body and "_isInFeud" not in body, case
    assert rules["feud other 0"] == 0 and rules["feud other 1"] == 0
    # The Mortality hold is new since the base commit and must never engage outside 10N.
    assert [value for key, value in rules.items() if key.startswith("hold other")] == [0, 0, 0, 0]
