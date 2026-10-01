"""Round-4 coordinator fix 2 (diag_r3 Q3/Q5): a native full wipe ends the attempt; nothing revives into it.

Round 3 Nefarian (batch 2): the 10th bot died at 1790802369973 and all ten were resurrected at
1790802369978. Every bot stood on the lair's transport, and Player::RepopAtGraveyard resurrects a
released player in place there; the full-wipe latch had opened the release. The revived raid sat in
the still-engaged encounter and died again (the death loop), the boss window ran on through a second
attempt (Chimaeron 514 s and Omnotron 476 s merged the same way), and the observer, whose reporter is a
living bot, stopped at the wipe: ``observation_ended_before_window``.

The fix ends the attempt at the wipe: the server records the full-wipe edge (raid_runtime.full_wipes),
the boss window closes there and the attempt is judged a wipe, observation coverage is required only up
to the wipe, and a canonical raid never releases a member into an in-place resurrection after a full
wipe (the attempt ends as a typed wipe instead; a ghost runback keeps the native re-pull).
"""
from __future__ import annotations

import copy
import re
import subprocess
from pathlib import Path

from tools.bot_ml.analyze_combat_log import close_encounters_at_full_wipes, full_wipes_from_status
from tools.bot_ml.live_validation_stalls import boss_windows
from tools.raid_program.run_sanity_inputs import BossWindow, observation_window_coverage
from tools.raid_program.scoreboard_core import load_target
from tools.raid_program.scoreboard_record import record_from_summary

from tests.test_raid_scoreboard import CLEAR, SCENARIO as MAGMAW, root  # noqa: F401 - root is a fixture

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
NODE = "bwd.nefarian.encounter"
PULL = 1_790_802_318_600          # batch 2: first party damage of the window
WIPE = 1_790_802_369_973          # the 10th death: +51.4 s
LAST_DAMAGE = PULL + 87_600       # the merged window ran on to +87.6 s
STATUS = {"raid_runtime": {"wipe_generation": 1, "full_wipes": [
    {"wipe_generation": 1, "at_ms": WIPE, "route_generation": 4, "route_node_id": NODE,
     "route_node_kind": "boss", "encounter_in_progress": True}]}}
MANIFEST = {"routes": [{"kind": "boss", "route_node_id": NODE}]}


def _encounter(node: str = NODE, generation: int = 4) -> dict:
    return {"route_generation": generation, "route_node_id": node, "first_at_ms": PULL,
            "last_at_ms": LAST_DAMAGE, "duration_sec": round((LAST_DAMAGE - PULL) / 1000.0, 3),
            "encounter_window_boundary_basis": "first_to_last_positive_originated_damage_done"}


def test_the_boss_window_closes_at_the_full_wipe_and_is_judged_a_wipe():
    encounters = [_encounter(), _encounter(node="bwd.maloriak.encounter", generation=2)]
    untouched = copy.deepcopy(encounters[1])
    close_encounters_at_full_wipes(encounters, full_wipes_from_status(STATUS))
    wiped = encounters[0]
    assert wiped["last_at_ms"] == WIPE and wiped["unclipped_last_at_ms"] == LAST_DAMAGE
    assert wiped["attempt_outcome"] == "full_wipe" and wiped["full_wipe_at_ms"] == WIPE
    assert wiped["duration_sec"] == 51.373
    assert encounters[1] == untouched  # another node's window is byte-identical


def test_a_run_without_a_full_wipe_keeps_its_windows_byte_identical():
    encounters = [_encounter()]
    before = copy.deepcopy(encounters)
    close_encounters_at_full_wipes(encounters, full_wipes_from_status({"raid_runtime": {"wipe_generation": 0}}))
    close_encounters_at_full_wipes(encounters, None)
    assert encounters == before
    # a wipe before the pull (a trash wipe) is not inside the window
    close_encounters_at_full_wipes(encounters, [{"at_ms": PULL - 1, "route_node_id": NODE}])
    assert encounters == before


def test_the_measurement_window_and_observation_coverage_end_at_the_wipe():
    encounters = [_encounter()]
    unclipped = BossWindow(copy.deepcopy(encounters[0]), NODE)
    close_encounters_at_full_wipes(encounters, full_wipes_from_status(STATUS))
    (window,) = boss_windows({"encounters": encounters}, MANIFEST)
    assert window["last_at_ms"] == WIPE and window["attempt_outcome"] == "full_wipe"
    boss = BossWindow(encounters[0], NODE)
    # the observer's reporter is a living bot: it last observed at +51.3 s, 0.1 s before the 10th death
    block = {"first_observed_at_ms": PULL - 500, "last_observed_at_ms": WIPE - 100}
    assert observation_window_coverage(block, unclipped, 5_000) == "observation_ended_before_window"
    assert observation_window_coverage(block, boss, 5_000) is None
    # a revived bot hit on the encounter node after the wipe belongs to no attempt
    after = {"timestamp_ms": WIPE + 30_000, "route_node_id": NODE}
    assert unclipped.has_event(after) and not boss.has_event(after)
    assert boss.has_event({"timestamp_ms": WIPE - 1, "route_node_id": NODE})


def test_a_full_wipe_window_is_never_a_clear(root):  # noqa: F811
    summary = {"native_clear": True, "completion_reason": CLEAR, "actors": [],
               "measurement_validity": {"valid_for_dps": True, "reasons": [], "full_wipe_at_ms": WIPE}}
    record = record_from_summary(summary, root=root, target=load_target(root, MAGMAW), scenario=MAGMAW,
                                 label="l", kill_id="k1", deaths={})
    assert record["native_clear"] is False and record["outcome"] == "gameplay_failure"
    assert record["boss_window_full_wipe_at_ms"] == WIPE
    del summary["measurement_validity"]["full_wipe_at_ms"]
    clear = record_from_summary(summary, root=root, target=load_target(root, MAGMAW), scenario=MAGMAW,
                                label="l", kill_id="k2", deaths={})
    assert clear["native_clear"] is True and "boss_window_full_wipe_at_ms" not in clear


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


def test_a_canonical_full_wipe_never_releases_into_an_in_place_resurrection(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, "full_wipe_release", r'''
#include "Bots/BotFullWipeRelease.h"
#include <cassert>
#include <cstring>

using namespace BotFullWipeRelease;

int main()
{
    // Player::RepopAtGraveyard's own conditions
    assert(ReleaseRevivesInPlace(true, false, false));
    assert(ReleaseRevivesInPlace(false, true, false));
    assert(ReleaseRevivesInPlace(false, false, true));
    assert(!ReleaseRevivesInPlace(false, false, false));
    // Nefarian: canonical raid, full-wipe recovery pending, on the transport, not yet released
    char const* reason = TerminalReason(true, true, false, true);
    assert(reason && std::strcmp(reason, "native_full_wipe_release_revives_in_place") == 0);
    // a release that makes a ghost keeps the native runback and re-pull
    assert(!TerminalReason(true, true, false, false));
    // an already released ghost, no pending full-wipe recovery, or a legacy scope: unchanged
    assert(!TerminalReason(true, true, true, true));
    assert(!TerminalReason(true, false, false, true));
    assert(!TerminalReason(false, true, false, true));
    return 0;
}
''')


def test_the_full_wipe_ledger_is_scoped_and_absent_without_a_wipe(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, "full_wipe_ledger", r'''
#include "Bots/BotNativeLifeEvents.h"
#include <cassert>
#include <string>

using namespace BotNativeLifeEvents;

int main()
{
    Scope const first{ 7, 1 };
    assert(FullWipesJsonField("c0", first).empty());   // no wipe: the status bytes are unchanged
    ObserveFullWipe("c0", first, { 1, 1790802369973ULL, 4, "bwd.nefarian.encounter", "boss", true });
    std::string const json = FullWipesJsonField("c0", first);
    assert(json == ",\"full_wipes\":[{\"wipe_generation\":1,\"at_ms\":1790802369973,\"route_generation\":4,"
        "\"route_node_id\":\"bwd.nefarian.encounter\",\"route_node_kind\":\"boss\",\"encounter_in_progress\":true}]");
    assert(FullWipesJsonField("c1", first).empty());    // another cohort
    Scope const next{ 8, 1 };
    assert(FullWipesJsonField("c0", next).empty());     // a new lifecycle starts clean
    ObserveFullWipe("c0", next, { 1, 5, 1, "n", "trash", false });
    assert(FullWipes("c0", next).size() == 1 && FullWipes("c0", first).empty());
    for (int index = 0; index < 40; ++index)
        ObserveFullWipe("c2", first, { uint64(index), 1, 1, "n", "boss", false });
    assert(FullWipes("c2", first).size() == MaxFullWipesPerLifecycle);
    return 0;
}
''')


def _function(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_the_server_records_exports_and_gates_the_full_wipe_edge() -> None:
    cohort = (BOTS / "BotWorldPopulationMgrValidationCohortRuntime.cpp").read_text(encoding="utf-8")
    edge = cohort.index("++raid.WipeGeneration;")
    assert "BotNativeLifeEvents::ObserveFullWipe(" in cohort[edge:edge + 600]
    runtime = (BOTS / "BotWorldPopulationMgrRaidRuntime.cpp").read_text(encoding="utf-8")
    assert "BotNativeLifeEvents::FullWipesJsonField(Cohort().Id" in runtime
    recovery = _function((BOTS / "BotWorldPopulationMgrRecovery.cpp").read_text(encoding="utf-8"),
                         "bool BotWorldPopulationMgr::TryNativeCorpseRun(")
    gate = recovery.index("BotFullWipeRelease::TerminalReason(")
    release = recovery.index("BotNativeAction::ReleaseSpirit{}")
    assert gate < release and "return terminal(inPlace);" in recovery[gate:release]
    assert re.search(r"IsCanonicalRaid\(Cohort\(\)\.Raid\.RaidInstance,\s*Cohort\(\)\.Config\.ValidationRouteScenarioId\)",
                     recovery[gate:release])
    for name in ("BotWorldPopulationMgrRaidRuntime.cpp", "BotWorldPopulationMgrValidationCohortRuntime.cpp",
                 "BotWorldPopulationMgrRecovery.cpp", "BotNativeLifeEvents.h", "BotFullWipeRelease.h"):
        assert len((BOTS / name).read_text(encoding="utf-8").splitlines()) < 1000, name


# --- round-4 review findings 1 and 2: the wipe is matched by native boundaries and the evidence is
# split at the wipe before aggregation.

def _log(abilities: list[dict], buckets: list[dict], attempt_id: int | None = None) -> dict:
    log = {"combat_log_schema_version": 8,
           "damage_attribution_schema": "originated_amount_v2_friendly_split",
           "abilities": abilities, "second_buckets": buckets}
    if attempt_id is not None:
        log["attempt_id"] = attempt_id
    return log


def _ability(first: int, last: int, amount: int, *, perspective: str = "damage_done", actor: int = 7,
             role: str = "dps", events: int = 10) -> dict:
    return {"route_generation": 4, "route_node_id": NODE, "perspective": perspective, "actor_guid": actor,
            "actor_name": f"Bot{actor}", "actor_role": role, "spell_id": 100, "spell_name": "Bolt",
            "target_entry": 41376, "first_at_ms": first, "last_at_ms": last, "event_count": events,
            "amount": amount, "originated_amount": amount, "distance_samples": events}


def _buckets(seconds: list[int], amount: int, *, perspective: str = "damage_done", actor: int = 7) -> list[dict]:
    return [{"route_generation": 4, "perspective": perspective, "actor_guid": actor, "source_is_pet": False,
             "second": second, "amount": amount, "originated_amount": amount} for second in seconds]


REVIEW_WIPE = [{"wipe_generation": 1, "at_ms": 10_000, "route_generation": 4, "route_node_id": NODE,
                "route_node_kind": "boss", "encounter_in_progress": True}]
REVIEW_BUCKETS = _buckets(list(range(1, 10)) + list(range(15, 21)), 1_000)


def test_reviewer_case_post_wipe_damage_is_split_off_before_aggregation():
    """9,000 damage over 1-9 s, wipe at 10 s, 6,000 more over 15-20 s: 9,000 over 9 s, 1,000 DPS."""
    from tools.bot_ml.analyze_combat_log import analyze_combat_log

    separate = [_ability(1_000, 9_000, 9_000), _ability(15_000, 20_000, 6_000)]
    spanning = [_ability(1_000, 20_000, 15_000, events=15)]  # one aggregate across the boundary
    for abilities, evidence in ((separate, {"excluded_after_wipe": 1, "spanning_wipe": 0}),
                                (spanning, {"excluded_after_wipe": 0, "spanning_wipe": 1,
                                            "spanning_split_by_own_second_buckets": 1,
                                            "spanning_unresolved": 0})):
        report = analyze_combat_log(_log(abilities, REVIEW_BUCKETS), None, REVIEW_WIPE)
        (encounter,) = report["encounters"]
        (actor,) = encounter["actors"]
        assert encounter["attempt_outcome"] == "full_wipe" and encounter["full_wipe_at_ms"] == 10_000
        assert encounter["last_at_ms"] == 10_000 and encounter["duration_sec"] == 9.0
        assert encounter["unclipped_last_at_ms"] == 20_000
        assert encounter["party_damage"] == 9_000 and encounter["encounter_window_party_dps"] == 1_000.0
        assert actor["damage"] == 9_000 and actor["encounter_window_dps"] == 1_000.0
        assert sum(row["damage"] for row in actor["abilities"]) == 9_000
        assert encounter["combat_duration_sec"] == 9  # post-wipe seconds left the active-combat denominator
        for key, value in evidence.items():
            assert encounter["full_wipe_evidence_split"][key] == value
        assert report["second_bucket_count"] == len(REVIEW_BUCKETS)  # log-level counts stay the log's


def _spell(ability: dict, spell_id: int) -> dict:
    return dict(ability, spell_id=spell_id, spell_name=f"Spell{spell_id}")


def test_reviewer_v2_case_a_spanning_ability_is_split_by_its_own_evidence_only():
    """Re-review (finding 2, v2): wipe at 10 s; ability A spans 1-20 s with 1,000 before the wipe and
    5,000 after; ability B is confined to 1-9 s with 9,000. A is credited 1,000 (not an actor-wide
    4,000): 10,000 over 9 s, 1,111.111 DPS."""
    from tools.bot_ml.analyze_combat_log import analyze_combat_log

    abilities = [_spell(_ability(1_000, 20_000, 6_000), 1), _spell(_ability(1_000, 9_000, 9_000), 2)]
    buckets = (_buckets([1, 2, 3, 4, 6, 7, 8, 9], 1_000) + _buckets([5], 2_000)   # B 1,000/s, A 1,000 at 5 s
               + _buckets([15, 16, 17, 18, 20], 1_000))                         # A after the wipe
    (encounter,) = analyze_combat_log(_log(abilities, buckets), None, REVIEW_WIPE)["encounters"]
    (actor,) = encounter["actors"]
    by_spell = {row["spell_id"]: row["damage"] for row in actor["abilities"]}
    assert by_spell == {1: 1_000, 2: 9_000}
    assert encounter["party_damage"] == 10_000 and encounter["duration_sec"] == 9.0
    assert encounter["encounter_window_party_dps"] == 1_111.111 and actor["encounter_window_dps"] == 1_111.111
    assert encounter["full_wipe_evidence_split"]["spanning_split_by_own_second_buckets"] == 1
    assert "full_wipe_split_unresolved" not in encounter


def test_a_spanning_record_without_attributable_evidence_is_unresolved_never_estimated():
    from tools.bot_ml.analyze_combat_log import analyze_combat_log
    from tools.bot_ml.live_validation_stalls import measurement_validity

    two_spanning = [_spell(_ability(1_000, 20_000, 6_000), 1), _spell(_ability(2_000, 19_000, 9_000), 2)]
    cases = (([_ability(1_000, 21_000, 20_000)], []),                       # no buckets at all
             (two_spanning, REVIEW_BUCKETS),                                # two spanning records of one key
             ([_ability(1_000, 20_000, 15_000)], REVIEW_BUCKETS[:12]))      # buckets do not reconcile
    for abilities, buckets in cases:
        (encounter,) = analyze_combat_log(_log(abilities, buckets), None, REVIEW_WIPE)["encounters"]
        assert encounter["attempt_outcome"] == "full_wipe"
        assert encounter["full_wipe_split_unresolved"] is True
        assert encounter["full_wipe_split_unresolved_actor_guids"] == [7]
        assert encounter["full_wipe_evidence_split"]["spanning_unresolved"] == len(abilities)
        assert encounter["party_damage"] == 0  # nothing estimated, nothing credited in full
        (window,) = boss_windows({"encounters": [encounter]}, MANIFEST)
        assert window["full_wipe_split_unresolved"] is True
        validity = measurement_validity({"event_window": {"first_ms": 1}}, [window], combat_log_available=True)
        assert validity["valid_for_dps"] is False and "full_wipe_split_unresolved" in validity["reasons"]


def test_healing_and_damage_taken_after_the_wipe_leave_the_attempt():
    from tools.bot_ml.analyze_combat_log import analyze_combat_log

    abilities = [_ability(1_000, 9_000, 9_000),
                 _ability(1_000, 9_000, 4_000, perspective="healing_done", actor=8, role="healer"),
                 _ability(16_000, 18_000, 3_000, perspective="healing_done", actor=8, role="healer"),
                 _ability(2_000, 17_000, 8_000, perspective="damage_taken", actor=8, role="healer")]
    buckets = (REVIEW_BUCKETS + _buckets(list(range(1, 9)), 500, perspective="healing_done", actor=8)
               + _buckets([16, 17, 18], 1_000, perspective="healing_done", actor=8)
               + _buckets([2, 5, 9, 15, 17], 1_600, perspective="damage_taken", actor=8))
    (encounter,) = analyze_combat_log(_log(abilities, buckets), None, REVIEW_WIPE)["encounters"]
    healer = next(actor for actor in encounter["actors"] if actor["actor_guid"] == 8)
    assert healer["healing"] == 4_000 and encounter["party_healing"] == 4_000
    assert healer["damage_taken"] == 4_800  # 3 of the 5 damage-taken seconds precede the wipe


def test_reviewer_case_a_wipe_after_the_last_outgoing_damage_ends_the_attempt():
    """The raid stops dealing damage at 9 s; the surviving healer dies at 10 s. The native edge names
    the node and route generation, so it ends this attempt although it follows the last damage."""
    from tools.bot_ml.analyze_combat_log import analyze_combat_log

    abilities = [_ability(1_000, 9_000, 9_000),
                 _ability(1_000, 9_800, 2_000, perspective="healing_done", actor=8, role="healer")]
    (encounter,) = analyze_combat_log(_log(abilities, REVIEW_BUCKETS[:9]), None, REVIEW_WIPE)["encounters"]
    assert encounter["attempt_outcome"] == "full_wipe" and encounter["full_wipe_at_ms"] == 10_000
    assert encounter["last_at_ms"] == 10_000 and encounter["unclipped_last_at_ms"] == 9_000
    (window,) = boss_windows({"encounters": [encounter]}, MANIFEST)
    assert window["attempt_outcome"] == "full_wipe" and window["full_wipe_at_ms"] == 10_000
    # the already-aggregated window marker follows the same native boundaries
    plain = _encounter()
    plain["last_at_ms"] = WIPE - 1_000
    close_encounters_at_full_wipes([plain], full_wipes_from_status(STATUS))
    assert plain["attempt_outcome"] == "full_wipe" and plain["last_at_ms"] == WIPE


def test_a_wipe_of_another_attempt_node_or_generation_never_closes_the_window():
    from tools.bot_ml.analyze_combat_log import analyze_combat_log

    log = _log([_ability(1_000, 9_000, 9_000), _ability(15_000, 20_000, 6_000)], REVIEW_BUCKETS, attempt_id=3)
    baseline = analyze_combat_log(log)
    status = {"attempt_id": 2, "raid_runtime": {"full_wipes": REVIEW_WIPE}}
    assert full_wipes_from_status(status)[0]["attempt_id"] == 2
    for wipes in (full_wipes_from_status(status),                      # another native attempt
                  [dict(REVIEW_WIPE[0], route_node_id="bwd.maloriak.encounter")],
                  [dict(REVIEW_WIPE[0], route_generation=5)],
                  [dict(REVIEW_WIPE[0], at_ms=500)],                   # before the pull
                  [dict(REVIEW_WIPE[0], route_generation=0, at_ms=25_000)]):  # unnamed, after the capture
        assert analyze_combat_log(log, None, wipes) == baseline
    same_attempt = full_wipes_from_status(dict(status, attempt_id=3))
    assert analyze_combat_log(log, None, same_attempt)["encounters"][0]["party_damage"] == 9_000


def test_final_pass_case_a_record_after_the_wipe_in_the_same_second_is_excluded():
    """Final pass (finding 2, v3): wipe at 10,000 ms; a separate 6,000-damage record at 10,500-10,900 ms
    falls in the wipe's own second but after the wipe. Records are classified by exact milliseconds:
    9,000 over 9 s, 1,000 DPS, one post-wipe record excluded, still measurable."""
    from tools.bot_ml.analyze_combat_log import analyze_combat_log
    from tools.bot_ml.live_validation_stalls import measurement_validity

    abilities = [_spell(_ability(1_000, 9_000, 9_000), 1), _spell(_ability(10_500, 10_900, 6_000), 2)]
    buckets = _buckets(list(range(1, 10)), 1_000) + _buckets([10], 6_000)
    (encounter,) = analyze_combat_log(_log(abilities, buckets), None, REVIEW_WIPE)["encounters"]
    assert encounter["party_damage"] == 9_000 and encounter["encounter_window_party_dps"] == 1_000.0
    assert encounter["full_wipe_evidence_split"]["excluded_after_wipe"] == 1
    assert encounter["combat_duration_sec"] == 9  # the wipe second held only post-wipe damage
    assert "full_wipe_split_unresolved" not in encounter
    (window,) = boss_windows({"encounters": [encounter]}, MANIFEST)
    assert measurement_validity({"event_window": {"first_ms": 1}}, [window],
                                combat_log_available=True)["valid_for_dps"] is True


def test_a_spanning_record_with_an_occupied_wipe_second_is_unresolved():
    """The wipe second's bucket mixes pre- and post-wipe events: the spanning record is not separable,
    so it is never credited (not even the whole second) and the window is not measurable."""
    from tools.bot_ml.analyze_combat_log import analyze_combat_log

    abilities = [_spell(_ability(1_000, 9_000, 9_000), 1), _spell(_ability(5_000, 15_000, 3_000), 2)]
    buckets = _buckets([1, 2, 3, 4, 6, 7, 8, 9], 1_000) + _buckets([5], 2_000) + _buckets([10, 15], 1_000)
    (encounter,) = analyze_combat_log(_log(abilities, buckets), None, REVIEW_WIPE)["encounters"]
    assert encounter["party_damage"] == 9_000 and encounter["full_wipe_split_unresolved"] is True
    assert encounter["full_wipe_evidence_split"]["unresolved_records"][0]["spell_id"] == 2
    # a kept record that ends exactly at the wipe keeps the wipe second as an active second
    ends_at_wipe = [_spell(_ability(1_000, 10_000, 10_000), 1)]
    (encounter,) = analyze_combat_log(
        _log(ends_at_wipe, _buckets(list(range(1, 11)), 1_000)), None, REVIEW_WIPE)["encounters"]
    assert encounter["party_damage"] == 10_000 and encounter["combat_duration_sec"] == 10
