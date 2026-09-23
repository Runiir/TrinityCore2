"""Raid scoreboard keep/revert rule (one implementation for compare_labels and show) and the baseline pointer.

Synthetic kills only; fixtures and kill builders come from test_raid_scoreboard.
"""
import json

import pytest

from tests.test_raid_scoreboard import SCENARIO, batch, kill, record_all, roster_actors, root  # noqa: F401
from tools.raid_program.scoreboard import (
    compare_labels, evaluate_target, load_baseline, main, set_baseline, void_kill,
)
from tools.raid_program.scoreboard_compare import batch_shortfall, keep_decision
from tools.raid_program.scoreboard_core import baseline_path, mean_sd
from tools.raid_program.scoreboard_show import MECHANISM_REMINDER, render

FIVE = (1.0, 1.02, 0.99, 1.01, 0.98)  # kills_per_batch counted native clears


def five(root, label, factor=1.0, **options):
    batch(root, label, scales=tuple(scale * factor for scale in FIVE), **options)


def scaled(scale, factors):
    """Roster actors at scale with some actors' DPS multiplied by a factor."""
    actors = roster_actors(scale)
    for actor in actors:
        actor["encounter_window_dps"] *= factors.get(actor["actor_id"], 1.0)
    return actors


def keep_block(root, new, old="old", actor=None, batch_kills=None):
    """The decision line and the four condition lines; the decision is compare_labels' own."""
    lines = render(root, SCENARIO, new, old, actor, batch_kills).splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("keep/revert:"))
    assert lines[start + 5] == MECHANISM_REMINDER  # the reminder follows every decision
    keep = compare_labels(root, SCENARIO, new, old, actor, batch_kills)["keep"]
    assert lines[start].split(" - ")[0].split(" [")[0] == f"keep/revert: {keep['decision']}"
    assert lines[start].endswith(("; ".join(keep["reasons"]) if keep["reasons"] else keep["decision"]))
    return lines[start:start + 5]


def states(block):
    return [line.split()[1] for line in block[1:]]


# --- the rule as a function ---------------------------------------------------------------------

def test_keep_decision_function(root):
    kills = [kill("n", f"k{i}") for i in range(5)]
    old = [kill("o", f"k{i}") for i in range(5)]
    flat_up = {"verdict": "within_noise", "new_mean": 101.0, "old_mean": 100.0, "basis": "counted_native_clears"}
    flat_down = flat_up | {"new_mean": 99.0}
    down = flat_up | {"verdict": "regressed", "new_mean": 80.0}
    unjudged = {"verdict": "insufficient_kills", "new_mean": None, "old_mean": 100.0}
    healer_down = {"1": flat_up | {"gating": True}, "2": down | {"gating": False}}

    def decide(party, actors, **options):
        return keep_decision(party, actors, new_label="n", old_label="o", new_kills=options.pop("new", kills),
                             old_kills=old, batch_kills=5, **options)

    assert decide(flat_up, healer_down)["decision"] == "keep"  # healers never gate
    result = decide(flat_down, healer_down)
    assert result["decision"] == "revert" and result["reasons"] == ["(d) party mean 99 vs o 100 (-1)"]
    assert decide(flat_down, {"1": flat_up | {"gating": True}}, targeted_actor="1")["decision"] == "keep"
    # (c) the party row gates too, also when a targeted actor rose
    result = decide(down, {"1": flat_up | {"gating": True}}, targeted_actor="1")
    assert result["decision"] == "revert" and result["reasons"] == ["(c) regressed (two-sided 95% Welch t): party"]
    # a gating actor without kills on one side, a targeted actor without a mean, an unknown actor: unjudged
    assert decide(flat_up, {"1": unjudged | {"gating": True}})["decision"] == "insufficient_kills"
    assert decide(flat_up, {"1": unjudged | {"gating": False}}, targeted_actor="1")["decision"] == "insufficient_kills"
    result = decide(flat_up, {}, targeted_actor="9")
    assert result["decision"] == "insufficient_kills" and "check --actor" in result["reasons"][0]
    # the batch size: short sides are insufficient_kills unless the override lowers kills_per_batch
    result = decide(flat_up, {}, new=kills[:3])
    assert result["decision"] == "insufficient_kills" and result["reasons"] == [batch_shortfall("n", 3, 5)]
    result = decide(flat_up, {}, new=kills[:3], batch_override=3)
    assert result["decision"] == "keep" and result["kills_per_batch"] == 3 and result["min_kills_override"] == 3
    assert result["target_kills_per_batch"] == 5


# --- compare_labels and show ----------------------------------------------------------------------

def test_compare_labels_and_show(root):
    five(root, "old", 0.8)
    five(root, "new")
    result = compare_labels(root, SCENARIO, "new", "old")
    assert result["schema"] == "raid_label_comparison_v1" and result["keep"]["decision"] == "keep"
    assert result["party"]["verdict"] == "improved" and result["party"]["delta"] == pytest.approx(48000.0)
    fire = result["actors"]["30006"]
    assert fire["verdict"] == "improved" and fire["gating"] and fire["df"] > 0 and fire["t"] > fire["critical_t"]
    assert result["actors"]["30003"]["gating"] is False
    text = render(root, SCENARIO, "new", "old")
    assert "keep/revert: keep" in text and "t95" in text
    assert "(healer, not gating)" in text and "kill time" in text


def test_recovered_trash_deaths_do_not_gate_but_boss_deaths_do(root):
    five(root, "old", 0.8)
    five(root, "trash", route_deaths=2)
    trash = compare_labels(root, SCENARIO, "trash", "old")
    assert trash["keep"]["decision"] == "keep"
    assert trash["route_deaths_per_kill"]["new"] == 2.0 and trash["boss_window_deaths_per_kill"]["new"] == 0.0
    five(root, "boss", route_deaths=1, window_deaths=1)
    boss = compare_labels(root, SCENARIO, "boss", "old")
    assert boss["keep"]["decision"] == "revert"
    assert boss["keep"]["reasons"] == ["(b) boss-window deaths per counted kill old 0.00 -> boss 1.00"]


def test_compare_keeps_a_numeric_delta_without_clears(root):
    batch(root, "old")
    record_all(root, *(kill("new", f"w{i}", clear=False, scale=0.5) for i in range(2)))
    result = compare_labels(root, SCENARIO, "new", "old")
    assert result["basis"] == "counted_kills_with_encounter_data"
    assert result["party"]["delta"] == pytest.approx(0.5 * 240000.0 - 240000.0 * (1.0 + 1.02 + 0.99) / 3)
    assert result["party"]["verdict"] == "insufficient_kills" and result["actors"]["30001"]["delta"] is not None
    assert result["keep"]["decision"] == "revert"  # candidate kills did not clear


def test_keep_rule_conditions_each_fail_alone(root):
    five(root, "old")
    five(root, "wipe", 1.1)
    record_all(root, kill("wipe", "w", clear=False, scale=1.1))
    five(root, "deaths", 1.1, window_deaths=1)
    record_all(root, *(kill("fire", f"k{i}", scale=s, actors=scaled(s, {"30006": 0.5}))
                       for i, s in enumerate(scale * 1.1 for scale in FIVE)))
    five(root, "lower", 0.99)  # party -1%: within noise but a negative point estimate
    record_all(root, *(kill("dk", f"k{i}", scale=s, actors=scaled(s, {"30002": 0.99})) for i, s in enumerate(FIVE)))
    for label, condition in {"wipe": "a", "deaths": "b", "fire": "c", "lower": "d"}.items():
        block = keep_block(root, label)
        assert block[0].startswith(f"keep/revert: revert - ({condition}) "), (label, block[0])
        assert states(block) == ["FAIL" if name == condition else "ok" for name in "abcd"]
    assert "regressed (two-sided 95% Welch t): 30006" in keep_block(root, "fire")[0]
    # a targeted actor whose mean fell reverts even when the party is flat; within noise the sign decides
    assert keep_block(root, "dk")[0] == "keep/revert: keep"
    assert keep_block(root, "dk", actor="30002")[0].startswith("keep/revert: revert - (d) actor 30002 mean ")
    record_all(root, *(kill("dkup", f"k{i}", scale=s, actors=scaled(s, {"30002": 1.01})) for i, s in enumerate(FIVE)))
    assert compare_labels(root, SCENARIO, "dkup", "old")["actors"]["30002"]["verdict"] == "within_noise"
    assert keep_block(root, "dkup", actor="30002")[0] == "keep/revert: keep"
    # the party row regressing reverts a targeted change even though the actor improved
    record_all(root, *(kill("party", f"k{i}", scale=s * 0.8, actors=scaled(s, {"30002": 1.05}))
                       for i, s in enumerate(FIVE)))
    block = keep_block(root, "party", actor="30002")
    assert block[0] == "keep/revert: revert - (c) regressed (two-sided 95% Welch t): party" and states(block)[3] == "ok"


def test_every_candidate_kill_counts_for_native_clears(root):
    five(root, "old")
    blockers = {"no_evidence": dict(pointer=None), "no_measurement_validity": dict(validity=None),
                "postprocess_error": dict(outcome="unknown", postprocess_error="Traceback")}
    for reason, options in blockers.items():
        five(root, reason)
        record_all(root, kill(reason, "bad", clear=False, **options))
        block = keep_block(root, reason)
        assert block[0] == f"keep/revert: revert - (a) 1 kill(s) of {reason} did not clear natively: {reason}-bad"
    five(root, "exempt")
    record_all(root, kill("exempt", "infra", clear=False, outcome="infrastructure_failure"),
               kill("exempt", "stop", clear=False, outcome="interrupted", interrupted="KeyboardInterrupt"),
               kill("exempt", "voided", clear=False))
    void_kill(root, SCENARIO, "exempt-voided", "operator error")
    assert keep_block(root, "exempt")[0] == "keep/revert: keep"
    five(root, "nodata")
    record_all(root, kill("nodata", "empty", encounter=None))  # counted native clear without encounter data
    block = keep_block(root, "nodata")
    assert block[0] == ("keep/revert: insufficient_kills - (a) counted native clear(s) without encounter-window "
                        "data: nodata-empty") and states(block) == ["n/a", "ok", "ok", "ok"]


def test_boss_deaths_unknown_are_unjudged_and_rising_deaths_revert_short_batches(root):
    five(root, "old")
    five(root, "unknown")
    record_all(root, kill("unknown", "k9", scale=1.1, window_deaths=None))
    block = keep_block(root, "unknown")
    assert block[0] == "keep/revert: insufficient_kills - (b) unknown boss-window deaths in counted kill(s): unknown-k9"
    assert compare_labels(root, SCENARIO, "unknown", "old")["boss_window_deaths_per_kill"]["new"] is None
    batch(root, "short", scales=(1.1, 1.12), window_deaths=1)
    block = keep_block(root, "short")
    assert block[0].startswith("keep/revert: revert - (b) boss-window deaths per counted kill old 0.00 -> short 1.00")
    assert states(block) == ["ok", "FAIL", "n/a", "ok"]


def test_kills_per_batch_is_enforced_unless_min_kills_lowers_it(root, capsys):
    batch(root, "old", scales=(0.80, 0.81, 0.79))
    batch(root, "new", scales=(1.00, 1.01, 0.99))
    short = [batch_shortfall("new", 3, 5), batch_shortfall("old", 3, 5)]
    keep = compare_labels(root, SCENARIO, "new", "old")["keep"]
    assert keep["decision"] == "insufficient_kills" and keep["reasons"] == short
    lines = render(root, SCENARIO, "new", "old").splitlines()
    assert "keep/revert: insufficient_kills - " + "; ".join(short) in lines
    assert not any(line.startswith("warning:") for line in lines)  # already in the decision line
    assert compare_labels(root, SCENARIO, "new", "old", batch_kills=3)["keep"]["decision"] == "keep"
    assert main(["--root", str(root), "show", "--scenario", SCENARIO, "--label", "new", "--vs", "old",
                 "--min-kills", "3"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "keep/revert: keep [--min-kills 3 overrides kills_per_batch 5]" in lines
    assert ["warning: " + text for text in short] == [line for line in lines if line.startswith("warning:")]
    with pytest.raises(SystemExit):
        main(["--root", str(root), "show", "--scenario", SCENARIO, "--min-kills", "0"])


def test_show_prints_the_detectable_delta(root):
    old_scales, new_scales = FIVE, (1.03, 1.0, 1.05)
    batch(root, "old", scales=old_scales)
    batch(root, "new", scales=new_scales)
    lines = render(root, SCENARIO, "new", "old").splitlines()
    party = compare_labels(root, SCENARIO, "new", "old")["party"]
    new, old = [240000.0 * s for s in new_scales], [240000.0 * s for s in old_scales]
    expected = party["critical_t"] * (mean_sd(new)[1] ** 2 / 3 + mean_sd(old)[1] ** 2 / 5) ** 0.5
    assert next(line for line in lines if line.startswith("actor ")).split("|")[1].split()[6] == "det95"
    assert next(line for line in lines if line.startswith("party ")).split("|")[1].split()[6] == f"{expected:.0f}"
    assert next(line for line in lines if line.startswith("30003")).split("|")[1].split()[6] == "-"  # healer
    assert any(line.startswith("det95 = detectable delta (95%, these n)") for line in lines)


# --- baseline pointer ---------------------------------------------------------------------------

def test_baseline_set_print_and_verdict_default(root, capsys):
    batch(root, "a")
    batch(root, "b", scales=(0.9, 0.91, 0.92))
    cli = ["--root", str(root)]
    assert main(cli + ["baseline", "--scenario", SCENARIO]) == 0
    assert capsys.readouterr().out.startswith(f"no baseline set for {SCENARIO}")
    assert main(cli + ["verdict", "--scenario", SCENARIO]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["label"] == "b" and "verdict label: b (latest recorded label" in out.err
    assert main(cli + ["baseline", "--scenario", SCENARIO, "--label", "a", "--reason", " kept round 3 "]) == 0
    written = json.loads(baseline_path(root, SCENARIO).read_text())
    assert written == load_baseline(root, SCENARIO) and written["set_at"].endswith("Z")
    assert {key: written[key] for key in written if key != "set_at"} == {
        "schema": "raid_scoreboard_baseline_v1", "scenario": SCENARIO, "label": "a", "source_commit": "0" * 40,
        "worldserver_sha256": "1" * 64, "counted_kills": 3, "reason": "kept round 3"}
    capsys.readouterr()
    assert main(cli + ["baseline", "--scenario", SCENARIO]) == 0
    assert json.loads(capsys.readouterr().out) == written
    assert main(cli + ["verdict", "--scenario", SCENARIO]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["label"] == "a" and out.err.startswith("verdict label: a (baseline set ")
    assert main(cli + ["verdict", "--scenario", SCENARIO, "--label", "b"]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["label"] == "b" and out.err == ""


def test_evaluate_target_defaults_to_the_baseline(root, capsys):
    batch(root, "a")
    batch(root, "b", scales=(0.9, 0.91, 0.92))
    assert evaluate_target(root, SCENARIO)["label"] == "b"
    assert "verdict label: b (latest recorded label; no baseline set)" in capsys.readouterr().err
    set_baseline(root, SCENARIO, "a")
    assert evaluate_target(root, SCENARIO)["label"] == "a"
    assert capsys.readouterr().err.startswith("verdict label: a (baseline set ")
    assert evaluate_target(root, SCENARIO, "b")["label"] == "b" and capsys.readouterr().err == ""


def test_baseline_needs_enough_clears_on_one_build(root):
    batch(root, "short", scales=(1.0, 1.0))
    batch(root, "mixed")
    record_all(root, kill("mixed", "other", sha="2" * 64))
    for label, message in (("short", "has 2 counted native-clear"), ("mixed", "mixes builds"), ("none", "no kills")):
        with pytest.raises(SystemExit, match=message):
            set_baseline(root, SCENARIO, label)
    assert load_baseline(root, SCENARIO) is None


def test_baseline_refuses_non_clears_and_boss_deaths_without_force(root, capsys):
    batch(root, "wiped")
    record_all(root, kill("wiped", "w", clear=False))
    batch(root, "died", window_deaths=1)
    batch(root, "unknown")
    record_all(root, kill("unknown", "u", window_deaths=None))
    for label, problem in (("wiped", "counted kill wiped-w is not a native clear"),
                           ("died", "counted kill died-k0 has 1 boss-window death(s)"),
                           ("unknown", "counted kill unknown-u has unknown boss-window death(s)")):
        with pytest.raises(SystemExit, match="not a clean baseline") as refused:
            set_baseline(root, SCENARIO, label, "why")
        assert problem in str(refused.value) and "--force --reason" in str(refused.value)
    with pytest.raises(SystemExit, match="--force needs --reason"):
        set_baseline(root, SCENARIO, "died", force=True)
    assert load_baseline(root, SCENARIO) is None
    cli = ["--root", str(root), "baseline", "--scenario", SCENARIO]
    assert main(cli + ["--label", "died", "--force", "--reason", "only clean build of the week"]) == 0
    written = load_baseline(root, SCENARIO)
    assert written["label"] == "died" and written["reason"] == "only clean build of the week"
    assert written["forced_over"] == [f"counted kill died-k{i} has 1 boss-window death(s)" for i in range(3)]
    with pytest.raises(SystemExit):
        main(cli + ["--force"])  # --force needs --label


def test_show_compares_against_the_baseline_by_default(root):
    five(root, "old", 0.8)
    five(root, "new")
    assert render(root, SCENARIO).splitlines()[0].endswith("label=new baseline=unset counted=5 of 5 clears=5")
    set_baseline(root, SCENARIO, "old")
    auto = render(root, SCENARIO).splitlines()
    assert auto[0].endswith("label=new baseline=old counted=5 of 5 clears=5  vs old (the baseline; pass --vs to override)")
    assert auto[1:] == render(root, SCENARIO, "new", "old").splitlines()[1:] and "keep/revert: keep" in auto
    same = render(root, SCENARIO, "old")
    assert "baseline=old" in same and " vs " not in same.splitlines()[0] and "keep/revert" not in same
