"""Raid scoreboard: target, counting rules, verdict contract, Welch comparison and the run path.

Synthetic kills and fake subprocesses only; nothing here launches a server or touches DVC.
"""
import hashlib
import json
import shutil
import signal
import subprocess
from pathlib import Path

import pytest

from tools.raid_program import scoreboard_run
from tools.raid_program.scoreboard import (
    KILL_SCHEMA, append_record, compare_labels, evaluate_target, load_records, load_target, main,
    party_reference_dps, spec_targets,
)
from tools.raid_program.scoreboard_compare import critical_t, keep_recommendation, welch
from tools.raid_program.scoreboard_core import load_lines, scoreboard_path
from tools.raid_program.scoreboard_record import (
    classify_outcome, death_evidence, is_native_clear, record_from_summary,
)
from tools.raid_program.scoreboard_show import render

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "blackwing_descent_10n_magmaw"
TARGET = f"experiments/configs/raid_targets/{SCENARIO}.json"
SUMMARIES = "artifacts/cata_raid_program/magmaw_spell_queue_{}_summary_20260922.json"
CLEAR = "validation_route_manifest_complete"
ROSTER = json.loads((ROOT / TARGET).read_text())["roster"]
WCL = {"balance_druid": 41029.1, "blood_death_knight": 26152.0, "fire_mage": 40189.9,
       "affliction_warlock": 40281.0, "elemental_shaman": 41866.0}


@pytest.fixture
def root(tmp_path):
    """A scratch repository root with the committed target and WCL manifests; the hunter is dropped
    from the roster so a full-strength batch can pass."""
    target = json.loads((ROOT / TARGET).read_text())
    for relative in (target["wcl_reference_manifest"], target["wcl_cast_timelines"]):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / relative, tmp_path / relative)
    target["roster"].pop("30009")
    target["run_plan"]["output_dir_pattern"] = str(tmp_path / "runs" / "scoreboard-{label}-k{kill}-{timestamp}")
    (tmp_path / TARGET).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / TARGET).write_text(json.dumps(target))
    (tmp_path / "runs").mkdir()
    (tmp_path / "artifacts/cata_raid_program").mkdir(parents=True, exist_ok=True)
    return tmp_path


def roster_actors(scale=1.0, skip=()):
    actors = []
    for actor_id, row in ROSTER.items():
        if actor_id in skip or actor_id == "30009":
            continue
        dps = WCL.get(row["spec"], 3000.0) * scale
        actors.append({"actor_id": actor_id, "name": row["name"], "spec": row["spec"], "role": row["role"],
                       "encounter_window_dps": dps, "damage_uptime": 0.8, "casts_per_minute": 30.0, "hps": 0.0})
    return actors


VALID = {"valid_for_dps": True, "reasons": [], "stalled_sec": 0.0, "stall_fraction": 0.0, "max_stall_sec": 0.0,
         "stall_count": 0, "window_duration_sec": 120.0, "unstalled_duration_sec": 120.0, "thresholds": {}}
STALLED = VALID | {"valid_for_dps": False, "reasons": ["boss_window_stall_fraction_exceeded"], "stalled_sec": 18.0,
                   "stall_fraction": 0.15, "max_stall_sec": 9.5, "stall_count": 2, "unstalled_duration_sec": 102.0}
RECONCILED = {"reconciled": True, "mismatch_count": 0, "encounter_mismatch_count": 0, "killed_hostile_count": 5,
              "unlogged_health_loss": 0}


def kill(label, name, *, scale=1.0, clear=True, window_deaths=0, route_deaths=0, sha="1" * 64, commit="0" * 40,
         pointer="artifacts/cata_raid_program/x.tar.gz.dvc", skip=(), validity=VALID, **extra):
    record = {"schema": KILL_SCHEMA, "kill_id": f"{label}-{name}", "scenario": SCENARIO, "label": label,
              "recorded_at": f"2026-09-23T00:00:0{len(name) % 10}Z", "source_commit": commit, "worldserver_sha256": sha,
              "run_dir": f"/tmp/{name}", "evidence_dvc_pointer": pointer, "native_clear": clear,
              "completion_reason": CLEAR if clear else "watchdog_no_progress",
              "outcome": "clear" if clear else "gameplay_failure", "route_deaths": route_deaths,
              "boss_window_deaths": window_deaths, "death_basis": "test", "deaths": [],
              "encounter": {"duration_sec": 120.0, "encounter_window_party_dps": 240000.0 * scale, "party_hps": 2e4},
              "actors": roster_actors(scale, skip), "ranked_gaps": [], "damage_reconciliation": RECONCILED, **extra}
    if validity is not None:
        record["measurement_validity"] = validity
    return record


def record_all(root, *kills):
    for row in kills:
        append_record(root, SCENARIO, row)


def batch(root, label, scales=(1.0, 1.02, 0.99), **options):
    record_all(root, *(kill(label, f"k{i}", scale=s, **options) for i, s in enumerate(scales)))


# --- target -----------------------------------------------------------------------------------

def test_committed_target_resolves_matched_wcl_targets_and_roster():
    target = load_target(ROOT, SCENARIO)
    targets = spec_targets(ROOT, target)
    assert targets["balance_druid"] == 41029.1 and targets["blood_death_knight"] == 26152.0
    assert "survival_hunter" not in targets  # the matched fight has no hunter
    assert party_reference_dps(ROOT, target) == 246232.7
    assert len(target["roster"]) == 10 and target["roster"]["30009"]["spec"] == "survival_hunter"
    assert "Welch" in target["noise_rule"]["test"]
    argv = target["run_plan"]["argv_template"]
    assert "{worldserver}" in argv and "{output_dir}" in argv and "completion-watchdog" in argv
    source = ROOT / target["run_plan"]["argv_template_source"]
    if source.exists():
        assert json.loads(source.read_text())["argv_template"] == argv


# --- verdict ----------------------------------------------------------------------------------

def test_full_batch_passes_with_the_verdict_contract(root):
    batch(root, "a")
    verdict = evaluate_target(root, SCENARIO)
    assert verdict["schema"] == "raid_target_verdict_v1" and verdict["label"] == "a" and verdict["kills"] == 3
    assert verdict["status"] == "pass" and verdict["reason"] is None and verdict["reasons"] == []
    for key in ("target_sha256", "wcl_manifest_sha256", "wcl_timelines_sha256"):
        assert len(verdict[key]) == 64
    assert verdict["worldserver_sha256"] == "1" * 64 and verdict["source_commits"] == ["0" * 40]
    assert verdict["first_recorded_at"] <= verdict["last_recorded_at"]
    assert verdict["roster"] == {"expected": [a for a in ROSTER if a != "30009"], "missing": {}}
    detail = verdict["kills_detail"][0]
    assert set(detail) == {"kill_id", "recorded_at", "worldserver_sha256", "source_commit", "evidence_dvc_pointer",
                           "native_clear", "counted", "exclusion_reason"}
    assert detail["counted"] is True and detail["exclusion_reason"] is None
    assert verdict["actors"]["30006"]["status"] == "pass" and verdict["actors"]["30003"]["status"] == "pass"
    assert verdict["encounter"]["status"] == "pass" and verdict["encounter"]["clears"] == 3


def test_actor_at_target_fails_when_the_encounter_fails(root):
    batch(root, "a", window_deaths=1)
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["encounter"]["status"] == "fail" and "boss_window_deaths" in verdict["reasons"]
    fire = verdict["actors"]["30006"]
    assert fire["ratio"] >= 0.95 and fire["status"] == "fail" and fire["reason"] == "encounter_failed"
    assert verdict["actors"]["30003"]["status"] == "fail"  # healers follow the encounter
    assert "encounter_failed" in verdict["reasons"] and verdict["status"] == "fail"


def test_low_actor_fails_and_insufficient_kills_before_three(root):
    batch(root, "a", scales=(0.9, 0.9))
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["status"] == "insufficient_kills" and "insufficient_kills" in verdict["reasons"]
    append_record(root, SCENARIO, kill("a", "k9", scale=0.9))
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["status"] == "fail" and verdict["actors"]["30001"]["reason"] == "below_target"


def test_missing_reference_is_never_a_pass(root):
    target = json.loads((root / TARGET).read_text())
    target["roster"]["30009"] = ROSTER["30009"]
    (root / TARGET).write_text(json.dumps(target))
    hunter = {"actor_id": "30009", "name": "h", "spec": "survival_hunter", "role": "dps", "encounter_window_dps": 5e4}
    record_all(root, *(kill("a", f"k{i}") | {"actors": roster_actors() + [hunter]} for i in range(3)))
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["actors"]["30009"]["status"] == "no_reference" and verdict["actors"]["30009"]["target_dps"] is None
    assert verdict["status"] == "fail" and "no_reference" in verdict["reasons"]


def test_specs_come_from_the_roster_not_the_run(root):
    rows = [actor | {"spec": "unknown"} for actor in roster_actors()]
    record_all(root, *(kill("a", f"k{i}") | {"actors": rows} for i in range(3)))
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["actors"]["30001"]["spec"] == "balance_druid" and verdict["status"] == "pass"


def test_roster_incomplete_fails(root):
    batch(root, "a")
    append_record(root, SCENARIO, kill("b", "k1", skip=("30007",)))
    record_all(root, kill("b", "k2"), kill("b", "k3"))
    verdict = evaluate_target(root, SCENARIO, "b")
    assert verdict["status"] == "fail" and "roster_incomplete" in verdict["reasons"]
    assert verdict["roster"]["missing"] == {"30007": ["b-k1"]}


@pytest.mark.parametrize("field,value,code", [("worldserver_sha256", "2" * 64, "mixed_binaries"),
                                              ("source_commit", "9" * 40, "mixed_commits")])
def test_mixed_builds_fail(root, field, value, code):
    record_all(root, kill("a", "k1"), kill("a", "k2"), kill("a", "k3") | {field: value})
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["status"] == "fail" and code in verdict["reasons"]
    if code == "mixed_binaries":
        assert verdict["worldserver_sha256"] is None
    else:
        assert verdict["source_commits"] == sorted(["0" * 40, "9" * 40])


def test_exclusions_are_listed_not_counted(root):
    batch(root, "a")
    record_all(root, kill("a", "noev", pointer=None),
               kill("a", "infra", clear=False) | {"outcome": "infrastructure_failure"},
               kill("a", "int", clear=False) | {"interrupted": "KeyboardInterrupt", "outcome": "interrupted"},
               kill("a", "crash") | {"postprocess_error": "boom", "encounter": None})
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["kills"] == 3 and verdict["status"] == "pass"
    reasons = {row["kill_id"]: row["exclusion_reason"] for row in verdict["kills_detail"] if not row["counted"]}
    assert reasons == {"a-noev": "no_evidence", "a-infra": "infrastructure_failure", "a-int": "interrupted",
                       "a-crash": "postprocess_error"}


def test_non_clear_and_unknown_deaths_fail_the_encounter(root):
    record_all(root, kill("wipe", "k1"), kill("wipe", "k2", clear=False), kill("wipe", "k3"))
    batch(root, "unknown", window_deaths=None)
    for label, code in (("wipe", "non_clear_kill"), ("unknown", "boss_window_deaths_unknown")):
        verdict = evaluate_target(root, SCENARIO, label)
        assert verdict["encounter"]["status"] == "fail" and code in verdict["reasons"]


def test_void_excludes_a_kill_with_an_audit_line(root, capsys):
    batch(root, "a")
    append_record(root, SCENARIO, kill("a", "bad", clear=False))
    assert evaluate_target(root, SCENARIO, "a")["status"] == "fail"
    assert main(["--root", str(root), "void", "--scenario", SCENARIO, "--kill-id", "a-bad",
                 "--reason", "server restarted by another agent"]) == 0
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["status"] == "pass" and verdict["voided"][0]["kill_id"] == "a-bad"
    assert verdict["voided"][0]["reason"] == "server restarted by another agent"
    assert load_lines(root, SCENARIO)[-1]["schema"] == "raid_scoreboard_void_v1"
    with pytest.raises(SystemExit):
        main(["--root", str(root), "void", "--scenario", SCENARIO, "--kill-id", "a-bad", "--reason", "again"])
    with pytest.raises(SystemExit):
        main(["--root", str(root), "void", "--scenario", SCENARIO, "--kill-id", "nope", "--reason", "x"])


def test_verdict_is_deterministic_with_ordered_reasons_and_raw_file_hashes(root):
    record_all(root, kill("a", "k1", window_deaths=1), kill("a", "k2", pointer=None),
               kill("a", "k3", clear=False), kill("a", "k4") | {"worldserver_sha256": "2" * 64})
    first = evaluate_target(root, SCENARIO, "a")
    assert json.dumps(first, sort_keys=True) == json.dumps(evaluate_target(root, SCENARIO, "a"), sort_keys=True)
    # two counted clears: actors are insufficient_kills, so no encounter_failed code
    assert first["reasons"] == ["non_clear_kill", "boss_window_deaths", "mixed_binaries", "no_evidence"]
    assert first["encounter"]["reasons"] == ["non_clear_kill", "boss_window_deaths", "mixed_binaries"]
    assert first["roster"]["missing"] == {}
    target = json.loads((root / TARGET).read_text())
    assert first["target_sha256"] == hashlib.sha256((root / TARGET).read_bytes()).hexdigest()
    assert first["wcl_timelines_sha256"] == hashlib.sha256((root / target["wcl_cast_timelines"]).read_bytes()).hexdigest()
    target.pop("wcl_cast_timelines")
    (root / TARGET).write_text(json.dumps(target))
    assert evaluate_target(root, SCENARIO, "a")["wcl_timelines_sha256"] is None


def test_no_kills_lists_the_roster(root):
    verdict = evaluate_target(root, SCENARIO)
    assert verdict["kills"] == 0 and verdict["label"] is None and verdict["status"] == "insufficient_kills"
    assert "no_kills" in verdict["reasons"] and set(verdict["actors"]) == set(ROSTER) - {"30009"}


def test_legacy_lines_get_stable_ids_and_duplicates_are_rejected(root):
    legacy = kill("a", "k1")
    legacy.pop("kill_id")
    legacy.pop("outcome")
    append_record(root, SCENARIO, legacy)
    record, = load_records(root, SCENARIO)
    assert record["kill_id"] == "a-k1" and record["outcome"] == "clear"
    append_record(root, SCENARIO, kill("a", "k1"))
    with pytest.raises(ValueError, match="duplicate kill_id"):
        load_records(root, SCENARIO)


# --- comparison -------------------------------------------------------------------------------

def test_welch_matches_the_textbook_formula():
    new, old = [110.0, 120.0, 130.0], [100.0, 101.0, 99.0, 100.0]
    result = welch(new, old)
    a, b = 100.0 / 3, (2.0 / 3) / 4
    assert result["t"] == pytest.approx(20.0 / (a + b) ** 0.5)
    assert result["df"] == pytest.approx((a + b) ** 2 / (a ** 2 / 2 + b ** 2 / 3))
    assert result["critical_t"] == pytest.approx(critical_t(result["df"]))
    assert critical_t(2.0) == pytest.approx(4.303, abs=1e-3) and critical_t(1e6) == pytest.approx(1.960, abs=1e-3)
    assert result["verdict"] == "within_noise"  # t = 3.46, df = 2.02, t_crit = 4.27
    assert welch([x + 60 for x in new], new)["verdict"] == "improved"
    assert welch(new, [x + 60 for x in new])["verdict"] == "regressed"
    assert welch([1.0, 2.0], [1.0, 2.0, 3.0])["verdict"] == "insufficient_kills"
    assert welch([5.0] * 3, [5.0] * 3)["verdict"] == "within_noise"
    assert welch([6.0] * 3, [5.0] * 3)["verdict"] == "improved"


def test_keep_rule():
    up, flat, down = ({"verdict": v} for v in ("improved", "within_noise", "regressed"))
    actors = {"1": {**flat, "gating": True}, "2": {**down, "gating": False}}
    common = dict(new_deaths_per_kill=0.0, old_deaths_per_kill=0.0, new_non_clears=0)
    assert keep_recommendation(up, actors, targeted_actor=None, **common)[0] == "keep"
    assert keep_recommendation(flat, actors, targeted_actor=None, **common)[0] == "revert"
    assert keep_recommendation(flat, {"1": {**up, "gating": True}}, targeted_actor="1", **common)[0] == "keep"
    decision, reasons = keep_recommendation(up, {"1": {**down, "gating": True}}, targeted_actor=None, **common)
    assert decision == "revert" and "regressed" in reasons[0]
    assert keep_recommendation(up, actors, targeted_actor=None, new_deaths_per_kill=1.0,
                               old_deaths_per_kill=0.0, new_non_clears=0)[0] == "revert"
    assert keep_recommendation({"verdict": "insufficient_kills"}, actors, targeted_actor=None,
                               **common)[0] == "insufficient_kills"


def test_compare_labels_and_show(root):
    batch(root, "old", scales=(0.80, 0.81, 0.79))
    batch(root, "new", scales=(1.00, 1.01, 0.99))
    result = compare_labels(root, SCENARIO, "new", "old")
    assert result["schema"] == "raid_label_comparison_v1" and result["keep"]["decision"] == "keep"
    assert result["party"]["verdict"] == "improved" and result["party"]["delta"] == pytest.approx(48000.0)
    fire = result["actors"]["30006"]
    assert fire["verdict"] == "improved" and fire["gating"] and fire["df"] > 0 and fire["t"] > fire["critical_t"]
    assert result["actors"]["30003"]["gating"] is False
    text = render(root, SCENARIO, "new", "old")
    assert "keep/revert (two-sided 95% Welch t): keep" in text and "t95" in text
    assert "(healer, not gating)" in text and "kill time" in text


def test_recovered_trash_deaths_do_not_gate_but_boss_deaths_do(root):
    batch(root, "old", scales=(0.80, 0.81, 0.79))
    batch(root, "trash", scales=(1.00, 1.01, 0.99), route_deaths=2)
    trash = compare_labels(root, SCENARIO, "trash", "old")
    assert trash["keep"]["decision"] == "keep"
    assert trash["route_deaths_per_kill"]["new"] == 2.0 and trash["boss_window_deaths_per_kill"]["new"] == 0.0
    batch(root, "boss", scales=(1.00, 1.01, 0.99), route_deaths=1, window_deaths=1)
    boss = compare_labels(root, SCENARIO, "boss", "old")
    assert boss["keep"]["decision"] == "revert"
    assert any("boss-window deaths per kill rose" in reason for reason in boss["keep"]["reasons"])


def test_show_lists_each_kill_with_stall_share_and_reconciliation(root):
    batch(root, "a")
    record_all(root, kill("a", "stalled", validity=STALLED,
                          damage_reconciliation=RECONCILED | {"mismatch_count": 2, "unlogged_health_loss": 51234}))
    lines = render(root, SCENARIO, "a").splitlines()
    header = next(line for line in lines if "stall%" in line)
    assert "max stall" in header and "recon mismatch" in header and "unlogged HP" in header
    stalled = next(line for line in lines if line.strip().startswith("a-stalled"))
    assert "no: stalled_boss_window" in stalled and "15.00" in stalled and "9.5s" in stalled
    assert stalled.split()[-2:] == ["2", "51234"]
    counted = next(line for line in lines if line.strip().startswith("a-k0"))
    assert " yes " in counted and "0.00" in counted


def test_compare_keeps_a_numeric_delta_without_clears(root):
    batch(root, "old")
    record_all(root, *(kill("new", f"w{i}", clear=False, scale=0.5) for i in range(2)))
    result = compare_labels(root, SCENARIO, "new", "old")
    assert result["basis"] == "counted_kills_with_encounter_data"
    assert result["party"]["delta"] == pytest.approx(0.5 * 240000.0 - 240000.0 * (1.0 + 1.02 + 0.99) / 3)
    assert result["party"]["verdict"] == "insufficient_kills" and result["actors"]["30001"]["delta"] is not None
    assert result["keep"]["decision"] == "revert"  # candidate kills did not clear


# --- records ----------------------------------------------------------------------------------

def test_record_from_committed_summary():
    summary = json.loads((ROOT / SUMMARIES.format("base1")).read_text())
    target = load_target(ROOT, SCENARIO)
    deaths = death_evidence(None, "bwd.magmaw.encounter", summary["route_deaths"])
    record = record_from_summary(summary, root=ROOT, target=target, scenario=SCENARIO, label="base",
                                 kill_id="base-1", deaths=deaths)
    assert record["schema"] == KILL_SCHEMA and record["native_clear"] is True and record["outcome"] == "clear"
    assert record["boss_window_deaths"] == 0 and record["death_basis"] == "no_route_deaths"
    assert "measurement_validity" not in record and "damage_reconciliation" not in record  # pre-d2393eb5a1 summary
    actor = next(row for row in record["actors"] if row["actor_id"] == "30001")
    assert actor["spec"] == "balance_druid" and actor["encounter_window_dps"] == 23764.92
    # base1 shortfalls: balance 17264, fire mage a 15967, blood DK 14608 DPS
    assert [gap["actor_id"] for gap in record["ranked_gaps"]] == ["30001", "30006", "30002"]
    sq1 = json.loads((ROOT / SUMMARIES.format("sq1")).read_text())
    assert death_evidence(None, "bwd.magmaw.encounter", sq1["route_deaths"])["boss_window_deaths"] is None


def test_clear_and_outcome_classification():
    assert is_native_clear({"native_clear": True, "completion_reason": CLEAR})
    assert not is_native_clear({"native_clear": True, "completion_reason": "watchdog_no_progress"})
    assert classify_outcome(report_present=False, native_clear=False, reached_encounter=True, died=True) == "infrastructure_failure"
    assert classify_outcome(report_present=True, native_clear=False, reached_encounter=False, died=False) == "infrastructure_failure"
    assert classify_outcome(report_present=True, native_clear=False, reached_encounter=False, died=True) == "gameplay_failure"
    assert classify_outcome(report_present=True, native_clear=False, reached_encounter=True, died=False) == "gameplay_failure"
    assert classify_outcome(report_present=True, native_clear=True, reached_encounter=True, died=False) == "clear"


def test_death_evidence_splits_trash_and_boss_window(tmp_path):
    def hit(at, node, target, before):
        return {"kind": "damage", "timestamp_ms": at, "route_node_id": node, "target_guid": target,
                "target_name": f"bot{target}", "actor_guid": 0, "source_name": "mob", "spell_name": "Hit",
                "amount": 500, "landed_damage_observation": {"target_health_before_damage": before}}
    encounters = [{"route_node_id": "bwd.magmaw.encounter", "first_at_ms": 1000, "last_at_ms": 2000,
                   "actors": [{"actor_guid": 1}, {"actor_guid": 2}]}]
    (tmp_path / "combat_analysis.json").write_text(json.dumps({"encounters": encounters}))
    events = [hit(500, "bwd.magmaw.drudges", 1, 400), hit(1500, "bwd.magmaw.encounter", 2, 500),
              hit(1600, "bwd.magmaw.encounter", 1, 9000)]  # the last hit is not lethal
    (tmp_path / "combat_log.json").write_text(json.dumps({"recent_events": events, "recent_events_dropped": 0}))
    result = death_evidence(tmp_path, "bwd.magmaw.encounter", 2)
    assert result["boss_window_deaths"] == 1 and result["death_basis"] == "combat_log_lethal_damage"
    assert [death["in_boss_window"] for death in result["deaths"]] == [False, True]
    assert death_evidence(tmp_path, "bwd.magmaw.encounter", 3)["boss_window_deaths"] is None


def test_ingest_summaries(root):
    pointer = "artifacts/cata_raid_program/example.tar.gz.dvc"
    (root / pointer).write_text("outs: []\n")
    args = ["--root", str(root), "ingest", "--scenario", SCENARIO, "--label", "base",
            "--summary", str(ROOT / SUMMARIES.format("base1")), "--evidence-pointer", pointer, "--source-commit", "f" * 40]
    assert main(args) == 0
    record, = load_records(root, SCENARIO)
    assert record["kill_id"] == "base-cata-magmaw-spellqueue-base1-20260922" and record["outcome"] == "clear"
    assert record["evidence_dvc_pointer"] == pointer and record["worldserver_sha256"].startswith("529ebc")
    with pytest.raises(SystemExit, match="already recorded"):
        main(args)


def test_committed_scoreboard_is_valid():
    records = load_records(ROOT, SCENARIO)
    if not records:
        pytest.skip("scoreboard not backfilled")
    assert {"base-529ebc", "spellqueue-b8a897"} <= {record["label"] for record in records}
    for record in records:
        assert {"kill_id", "label", "recorded_at", "source_commit", "worldserver_sha256", "run_dir", "outcome",
                "evidence_dvc_pointer", "native_clear", "route_deaths", "boss_window_deaths", "encounter", "actors"} <= set(record)
    # Recorded before the harness measured stalls: kept in the file, never counted.
    for label in ("base-529ebc", "spellqueue-b8a897"):
        verdict = evaluate_target(ROOT, SCENARIO, label)
        assert verdict["kills"] == 0 and verdict["status"] != "pass"
        assert {row["exclusion_reason"] for row in verdict["kills_detail"]} == {"no_measurement_validity"}
        assert "no_measurement_validity" in verdict["reasons"]


# --- measurement quality ------------------------------------------------------------------------

def test_measurement_validity_decides_counting(root):
    batch(root, "a")
    record_all(root, kill("a", "legacy", validity=None), kill("a", "stalled", validity=STALLED),
               kill("a", "mismatch") | {"damage_reconciliation": RECONCILED | {"reconciled": False, "mismatch_count": 2}})
    verdict = evaluate_target(root, SCENARIO, "a")
    detail = {row["kill_id"]: row for row in verdict["kills_detail"]}
    assert detail["a-legacy"]["counted"] is False and detail["a-legacy"]["exclusion_reason"] == "no_measurement_validity"
    assert detail["a-stalled"]["counted"] is False and detail["a-stalled"]["exclusion_reason"] == "stalled_boss_window"
    assert detail["a-mismatch"]["counted"] is True and detail["a-mismatch"]["exclusion_reason"] is None
    assert verdict["kills"] == 4 and verdict["status"] == "pass" and verdict["reasons"] == []
    batch(root, "old", validity=None)
    verdict = evaluate_target(root, SCENARIO, "old")
    assert verdict["kills"] == 0 and verdict["status"] == "insufficient_kills"
    assert verdict["reasons"] == ["insufficient_kills", "no_measurement_validity"]


def test_invalid_window_on_a_wipe(root):
    no_window = VALID | {"valid_for_dps": False, "reasons": ["no_boss_window"]}
    record_all(root, kill("trash", "k1", clear=False, route_deaths=3, validity=no_window))
    trash, = evaluate_target(root, SCENARIO, "trash")["kills_detail"]
    assert trash["counted"] is True  # a trash wipe still fails the label
    record_all(root, kill("boss", "k1", clear=False, validity=STALLED))
    boss, = evaluate_target(root, SCENARIO, "boss")["kills_detail"]
    assert boss["exclusion_reason"] == "stalled_boss_window"  # the freeze may have caused the wipe


# --- run path with fake subprocesses ------------------------------------------------------------

def harness_validity(stalled_sec=0.0, max_stall=0.0):
    """measurement_validity as tools/bot_ml/live_validation_stalls.py writes it."""
    window = {"route_node_id": "bwd.magmaw.encounter", "route_generation": 4, "first_at_ms": 1000,
              "last_at_ms": 121000, "duration_sec": 120.0, "stall_count": int(stalled_sec > 0),
              "stalled_sec": stalled_sec, "unstalled_duration_sec": 120.0 - stalled_sec,
              "stall_fraction": round(stalled_sec / 120.0, 6), "max_stall_sec": max_stall, "hitch_sec": 0.0}
    reasons = ["world_stall_overlaps_boss_window"] if stalled_sec else []
    return {"schema": "bot_measurement_validity_v1", "valid_for_dps": not reasons, "reasons": reasons,
            "boss_window_stalled_sec": stalled_sec, "boss_window_stall_count": window["stall_count"],
            "max_boss_window_stall_sec": max_stall, "boss_windows": [window],
            "thresholds": {"stall_min_gap_sec": 1.0}}


def harness_reconciliation(mismatches=0):
    hostiles = [{"target_name": "Magmaw", "route_node_id": "bwd.magmaw.encounter", "flagged": i < mismatches,
                 "unlogged_health_loss": 1000 * (i < mismatches)} for i in range(3)]
    return {"schema": "bot_killed_hostile_damage_reconciliation_v1", "killed_hostile_count": 3,
            "mismatch_count": mismatches, "reconciled": not mismatches,
            "mismatches": [row for row in hostiles if row["flagged"]], "hostiles": hostiles}


def write_run(out, *, clear=True, deaths=0, encounter=True, report=True, heartbeat_node="bwd.magmaw.encounter",
              report_sha=None, stalled_sec=0.0, mismatches=0, validity=True):
    out.mkdir(parents=True)
    if not report:
        return
    completion = CLEAR if clear else "watchdog_no_progress"
    envelope = {"evidence_envelope": {"component_hashes": {"binary_sha256": report_sha}}} if report_sha else {}
    quality = {"measurement_validity": harness_validity(stalled_sec, stalled_sec / 2)} if validity else {}
    (out / "report.json").write_text(json.dumps({
        "native_gameplay_outcome": {"native_clear": clear, "native_reason": "x"},
        "completion_reason": completion, "status": {"deaths": deaths}, **envelope, **quality}))
    heartbeat = {"semantic_liveness": {"route_node_id": heartbeat_node}}
    (out / "heartbeat_events.jsonl").write_text(json.dumps(heartbeat) + "\n")
    actors = [{"actor_guid": int(actor["actor_id"]), "actor_name": actor["name"], "actor_role": actor["role"],
               "encounter_window_dps": actor["encounter_window_dps"], "damage": actor["encounter_window_dps"] * 120,
               "damage_uptime": 0.8} for actor in roster_actors()]
    rows = [{"route_node_id": "bwd.magmaw.encounter", "first_at_ms": 1000, "last_at_ms": 121000, "duration_sec": 120.0,
             "party_damage": 1, "encounter_window_party_dps": 240000.0, "party_hps": 1.0, "action_outcomes": [],
             "actors": actors}] if encounter else []
    reconciliation = {"killed_hostile_damage_reconciliation": harness_reconciliation(mismatches)} if validity else {}
    (out / "combat_analysis.json").write_text(json.dumps({"encounters": rows, **reconciliation}))
    (out / "combat_log.json").write_text(json.dumps({"recent_events": [], "recent_events_dropped": 0}))


class FakeHarness:
    """Stands in for Popen: writes the run dir named by --output-dir and exits 1 like the real harness."""

    def __init__(self, runs, interrupt=False):
        self.runs = list(runs)
        self.interrupt = interrupt
        self.argv = []
        self.killed = []

    def popen(self, argv, cwd=None, stdout=None, stderr=None, start_new_session=False):
        assert start_new_session is True
        self.argv.append(argv)
        write_run(Path(argv[argv.index("--output-dir") + 1]), **self.runs.pop(0))
        harness = self

        class Process:
            pid = 4242
            calls = 0

            def wait(self, timeout=None):
                Process.calls += 1
                if harness.interrupt and Process.calls == 1:
                    raise KeyboardInterrupt
                return 1
        return Process()


class FakeArchive:
    """Stands in for experiments.archive_run_evidence: success writes the pointer and deletes the sources."""

    def __init__(self, root, fail=0):
        self.root, self.fail, self.names = root, fail, []

    def run(self, argv, cwd=None, **kwargs):
        assert "experiments.archive_run_evidence" in argv, argv
        name = argv[argv.index("--name") + 1]
        self.names.append(name)
        folder = self.root / "artifacts/cata_raid_program"
        if self.fail:
            self.fail -= 1
            (folder / f"{name}.tar.gz").write_text("partial")  # a failed push leaves these behind
            (folder / f"{name}.tar.gz.dvc").write_text("outs: []\n")
            return subprocess.CompletedProcess(argv, 1)
        (folder / f"{name}.tar.gz.dvc").write_text("outs: []\n")
        for path in map(Path, argv[argv.index("--name") + 2:]):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        return subprocess.CompletedProcess(argv, 0)


@pytest.fixture
def fakes(root, monkeypatch, tmp_path):
    (tmp_path / "pin").mkdir()
    monkeypatch.setattr(scoreboard_run, "PIN_DIR", tmp_path / "pin")
    worldserver = tmp_path / "worldserver"
    worldserver.write_bytes(b"binary")

    def install(runs, *, interrupt=False, archive_failures=0):
        harness, archive = FakeHarness(runs, interrupt), FakeArchive(root, archive_failures)
        monkeypatch.setattr(scoreboard_run.subprocess, "Popen", harness.popen)
        monkeypatch.setattr(scoreboard_run.subprocess, "run", archive.run)
        monkeypatch.setattr(scoreboard_run.os, "killpg", lambda pid, sig: harness.killed.append((pid, sig)))
        return harness, archive
    return install, worldserver


def run_cli(root, worldserver, label, kills):
    return main(["--root", str(root), "run", "--scenario", SCENARIO, "--label", label, "--kills", str(kills),
                 "--worldserver", str(worldserver), "--source-commit", "c" * 40])


def test_run_clean_clears_count_despite_exit_1(root, fakes):
    install, worldserver = fakes
    harness, archive = install([{}, {"report_sha": "e" * 64}, {}])
    assert run_cli(root, worldserver, "sq", 3) == 0
    pinned = [argv[argv.index("--worldserver") + 1] for argv in harness.argv]
    assert len(set(pinned)) == 1 and Path(pinned[0]).name.startswith("worldserver-") and pinned[0] != str(worldserver)
    file_sha = hashlib.sha256(b"binary").hexdigest()
    assert Path(pinned[0]).read_bytes() == b"binary" and Path(pinned[0]).name == f"worldserver-{file_sha[:12]}"
    records = load_records(root, SCENARIO)
    assert [r["harness_exit_code"] for r in records] == [1, 1, 1] and len({r["kill_id"] for r in records}) == 3
    assert all(r["outcome"] == "clear" and r["evidence_dvc_pointer"] for r in records)
    # The launched file's hash wins; a differing report hash is kept beside it.
    assert {r["worldserver_sha256"] for r in records} == {file_sha}
    assert records[1]["report_binary_sha256"] == "e" * 64 and "report_binary_sha256" not in records[0]
    verdict = evaluate_target(root, SCENARIO, "sq")
    assert verdict["kills"] == 3 and verdict["encounter"]["status"] == "pass" and verdict["status"] == "pass"
    assert verdict["worldserver_sha256"] == file_sha
    for row in verdict["kills_detail"]:
        assert row["recorded_at"].endswith("Z") and isinstance(row["kill_id"], str) and row["counted"] is True
        assert not Path(row["evidence_dvc_pointer"]).is_absolute()
    assert not any((root / "runs").iterdir())  # archived evidence is deleted
    with pytest.raises(SystemExit, match="already has 3 kill"):
        run_cli(root, worldserver, "sq", 1)


def test_run_records_measurement_quality(root, fakes, capsys):
    install, worldserver = fakes
    install([{"mismatches": 1}, {"stalled_sec": 6.0}, {"validity": False}])
    assert run_cli(root, worldserver, "q", 3) == 0  # quality never stops a batch; it decides counting
    clean, stalled, old_harness = load_records(root, SCENARIO)
    assert clean["measurement_validity"] == {
        "schema": "bot_measurement_validity_v1", "valid_for_dps": True, "reasons": [], "window_duration_sec": 120.0,
        "stalled_sec": 0.0, "stall_fraction": 0.0, "max_stall_sec": 0.0, "stall_count": 0,
        "unstalled_duration_sec": 120.0, "thresholds": {"stall_min_gap_sec": 1.0}}
    assert clean["damage_reconciliation"] == {"reconciled": False, "mismatch_count": 1, "encounter_mismatch_count": 1,
                                              "killed_hostile_count": 3, "unlogged_health_loss": 1000}
    assert stalled["measurement_validity"]["valid_for_dps"] is False
    assert stalled["measurement_validity"]["stall_fraction"] == 0.05 and stalled["measurement_validity"]["max_stall_sec"] == 3.0
    assert "measurement_validity" not in old_harness and "damage_reconciliation" not in old_harness
    detail = [row["exclusion_reason"] for row in evaluate_target(root, SCENARIO, "q")["kills_detail"]]
    assert detail == [None, "stalled_boss_window", "no_measurement_validity"]
    out = capsys.readouterr().out
    assert "NOTE: kill q-k2-" in out and "not counted (stalled_boss_window" in out and "STOP" not in out


def test_run_missing_report_is_infrastructure(root, fakes, capsys):
    install, worldserver = fakes
    install([{"report": False}, {}])
    assert run_cli(root, worldserver, "sq", 2) == 1
    record, = load_records(root, SCENARIO)
    assert record["outcome"] == "infrastructure_failure" and record["evidence_dvc_pointer"]
    assert "INFRASTRUCTURE FAILURE" in capsys.readouterr().out
    assert evaluate_target(root, SCENARIO, "sq")["kills_detail"][0]["exclusion_reason"] == "infrastructure_failure"


def test_run_stall_before_the_boss_without_deaths_is_infrastructure(root, fakes):
    install, worldserver = fakes
    install([{"clear": False, "encounter": False, "heartbeat_node": "bwd.magmaw.drudges"}])
    assert run_cli(root, worldserver, "sq", 1) == 1
    assert load_records(root, SCENARIO)[0]["outcome"] == "infrastructure_failure"


def test_run_postprocess_crash_still_records_and_archives(root, fakes, monkeypatch, capsys):
    install, worldserver = fakes
    install([{}])
    monkeypatch.setattr(scoreboard_run, "record_from_run_dir", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert run_cli(root, worldserver, "sq", 1) == 1
    record, = load_records(root, SCENARIO)
    assert "RuntimeError: boom" in record["postprocess_error"] and record["evidence_dvc_pointer"]
    assert record["native_clear"] is True and record["harness_exit_code"] == 1
    assert "POSTPROCESS FAILED" in capsys.readouterr().out
    assert evaluate_target(root, SCENARIO, "sq")["kills_detail"][0]["exclusion_reason"] == "postprocess_error"


def test_run_archive_failure_keeps_evidence_and_archive_pending_retries(root, fakes, capsys):
    install, worldserver = fakes
    _, archive = install([{"clear": False}], archive_failures=1)
    assert run_cli(root, worldserver, "sq", 1) == 1
    out = capsys.readouterr().out
    assert "NOT A NATIVE CLEAR" in out and "ARCHIVE FAILED" in out  # both problems are reported
    record, = load_records(root, SCENARIO)
    assert record["archive_error"] and record["evidence_dvc_pointer"] is None
    assert all(Path(path).exists() for path in record["evidence_paths"])
    assert evaluate_target(root, SCENARIO, "sq")["kills_detail"][0]["exclusion_reason"] == "no_evidence"
    assert main(["--root", str(root), "archive-pending", "--scenario", SCENARIO]) == 0
    out = capsys.readouterr().out
    assert "left behind by an earlier archive attempt" in out
    assert archive.names[1] == archive.names[0] + "_retry1"  # the leftover pointer does not block the retry
    record, = load_records(root, SCENARIO)
    assert record["evidence_dvc_pointer"].endswith("_retry1.tar.gz.dvc")
    assert load_lines(root, SCENARIO)[-1]["schema"] == "raid_scoreboard_evidence_attachment_v1"
    detail, = evaluate_target(root, SCENARIO, "sq")["kills_detail"]
    assert detail["counted"] is True and detail["native_clear"] is False
    assert main(["--root", str(root), "archive-pending", "--scenario", SCENARIO]) == 0  # nothing left


def test_run_keyboard_interrupt_kills_the_process_group(root, fakes, capsys):
    install, worldserver = fakes
    harness, _ = install([{}], interrupt=True)
    assert run_cli(root, worldserver, "sq", 3) == 130
    assert harness.killed == [(4242, signal.SIGTERM)]
    record, = load_records(root, SCENARIO)
    assert record["interrupted"] == "KeyboardInterrupt" and record["evidence_dvc_pointer"] is None
    assert record["evidence_paths"] and "INTERRUPTED" in capsys.readouterr().out
    assert evaluate_target(root, SCENARIO, "sq")["kills_detail"][0]["exclusion_reason"] == "interrupted"


def test_run_dry_run_executes_nothing(root, capsys, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry run must not execute anything")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    worldserver = tmp_path / "ws"
    worldserver.write_bytes(b"x")
    assert main(["--root", str(root), "run", "--scenario", SCENARIO, "--label", "sq", "--kills", "2",
                 "--worldserver", str(worldserver), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count("bot-live-validate --worldserver /tmp/worldserver-") == 2
    assert "scoreboard-sq-k1-" in out and "scoreboard-sq-k2-" in out and "{output_dir}" not in out
    assert "experiments.archive_run_evidence --name scoreboard_blackwing_descent_10n_magmaw_sq-k1-" in out
    assert not list((root / "runs").iterdir()) and not scoreboard_path(root, SCENARIO).exists()
    append_record(root, SCENARIO, kill("sq", "k1"))
    with pytest.raises(SystemExit, match="already has 1 kill"):
        main(["--root", str(root), "run", "--scenario", SCENARIO, "--label", "sq", "--dry-run"])


# --- encounter damage fidelity (informational) --------------------------------------------------

def fidelity_block(blizzlike=False, mean=8683.4, ratio=0.0599):
    """The compact per-kill fidelity status scoreboard_record keeps."""
    return {"blizzlike": blizzlike, "basis": "harness",
            "reasons": [] if blizzlike else ["boss 41570 Magmaw: mismatch (registry DamageModifier 16, DB 1)"],
            "bosses": {"41570": {"name": "Magmaw", "swings": 24, "after_attacker_mean": mean, "wcl_mean": 145035.5,
                                 "wcl_mean_basis": "wcl_envelope_midpoint", "mean_ratio": ratio, "wcl_flags": [],
                                 "runtime_damage_modifier": 1.0, "registry_damage_modifier": 16.0}}}


def test_fidelity_is_shown_but_never_changes_counting_or_the_verdict(root):
    batch(root, "plain")
    batch(root, "fidelity", encounter_fidelity=fidelity_block())
    plain, marked = evaluate_target(root, SCENARIO, "plain"), evaluate_target(root, SCENARIO, "fidelity")
    for key in ("status", "reason", "reasons", "kills", "encounter", "actors"):
        assert plain[key] == marked[key], key
    assert [row["counted"] for row in marked["kills_detail"]] == [True, True, True]
    line = next(line for line in render(root, SCENARIO, "fidelity").splitlines() if line.startswith("encounter fidelity"))
    assert line == ("encounter fidelity (informational): blizzlike true 0, false 3, unknown 0 of 3 kills; "
                    "Magmaw after-attacker mean 8683 = 0.06x WCL 145036 (envelope midpoint); "
                    "boss 41570 Magmaw: mismatch (registry DamageModifier 16, DB 1)")
    assert "encounter fidelity (informational): not recorded" in render(root, SCENARIO, "plain")


def magmaw_run_dir(folder, *, report_extra=None, modifier=1.0):
    """A closed run with a Magmaw route manifest and two native Magmaw swings."""
    from tools.bot_ml.live_validation_fidelity import FIDELITY_SCHEMA  # noqa: F401 - module must import
    folder.mkdir(parents=True)
    (folder / "report.json").write_text(json.dumps({"native_gameplay_outcome": {"native_clear": True},
                                                    "completion_reason": CLEAR, "status": {"deaths": 0},
                                                    **(report_extra or {})}))
    (folder / "validation_route_manifest.json").write_text(json.dumps({"scenario_id": "blackwing_descent_10n_magmaw_diagnostic",
        "routes": [{"route_node_id": "bwd.magmaw.encounter", "kind": "boss", "source_entry": 41570}]}))

    def swing(at, amount):
        return {"kind": "melee_resolution", "event_sequence": at, "melee_resolution_sequence": at, "timestamp_ms": at,
                "route_node_id": "bwd.magmaw.encounter", "source_entry": 41570, "source_guid": 39,
                "source_name": "Magmaw", "source_is_pet": False, "target_guid": 30002,
                "melee_resolution": {"after_attacker_bonus_amount": amount, "hit_outcome_name": "normal",
                                     "attack_type": 0, "attacker_template_damage_modifier": modifier,
                                     "attacker_base_attack_time_ms": 2500}}
    events = [swing(1_000_000, 8000), swing(1_003_000, 9000)]
    (folder / "combat_log.json").write_text(json.dumps({"recent_events": events, "recent_events_dropped": 0}))
    (folder / "combat_analysis.json").write_text(json.dumps({"encounters": []}))
    return folder


def test_record_keeps_fidelity_from_the_harness_or_recomputes_it(tmp_path):
    from tools.bot_ml.live_validation_fidelity import FIDELITY_SCHEMA
    from tools.raid_program.scoreboard_record import outcome_summary
    old = outcome_summary(magmaw_run_dir(tmp_path / "old"), None, "bwd.magmaw.encounter")["encounter_fidelity"]
    assert old["basis"] == "combat_log_recomputed_without_db" and old["blizzlike"] is False
    assert "boss 41570 Magmaw: runtime DamageModifier 1 != registry 16" in old["reasons"]
    magmaw = old["bosses"]["41570"]
    assert magmaw["after_attacker_mean"] == 8500.0 and magmaw["mean_ratio"] == pytest.approx(8500 / 145035.5, abs=1e-4)
    assert magmaw["wcl_mean_basis"] == "wcl_envelope_midpoint" and magmaw["registry_damage_modifier"] == 16.0
    harness = {"schema": FIDELITY_SCHEMA, "basis": "harness", "blizzlike": True, "reasons": [], "boss_melee": {}}
    new = outcome_summary(magmaw_run_dir(tmp_path / "new", report_extra={"encounter_fidelity": harness}), None,
                          "bwd.magmaw.encounter")["encounter_fidelity"]
    assert new == {"blizzlike": True, "reasons": [], "basis": "harness", "bosses": {}}
    target = load_target(ROOT, SCENARIO)
    record = record_from_summary({"native_clear": True, "completion_reason": CLEAR, "actors": [],
                                  "encounter_fidelity": new}, root=ROOT, target=target, scenario=SCENARIO,
                                 label="x", kill_id="x-1", deaths={"boss_window_deaths": 0, "deaths": []})
    assert record["encounter_fidelity"] == new


def test_run_path_records_fidelity_without_affecting_the_batch(root, fakes):
    install, worldserver = fakes
    install([{}, {}, {}])
    assert run_cli(root, worldserver, "fid", 3) == 0
    records = load_records(root, SCENARIO)
    # Fake runs carry no route manifest or melee: the status is unknown, not a failure.
    assert all(record["encounter_fidelity"]["blizzlike"] is None for record in records)
    assert evaluate_target(root, SCENARIO, "fid")["status"] == "pass"


# --- top-up -----------------------------------------------------------------------------------

def _top_up_args(label, source_commit=None, top_up=True, dry_run=False, target_kills=None):
    import argparse
    return argparse.Namespace(scenario=SCENARIO, label=label, kills=None, worldserver=None,
                              source_commit=source_commit, top_up=top_up, dry_run=dry_run,
                              target_kills=target_kills)


def test_top_up_replaces_only_measurement_exclusions(root, tmp_path):
    from tools.raid_program.scoreboard_run import top_up_plan
    binary = tmp_path / "worldserver"
    binary.write_bytes(b"same build")
    sha = hashlib.sha256(b"same build").hexdigest()
    target = load_target(root, SCENARIO)
    clean = [kill("a", f"k{i}", sha=sha) for i in range(2)]
    stalled = kill("a", "k2", sha=sha, validity=STALLED)
    assert top_up_plan(clean + [stalled], target, binary, _top_up_args("a")) == (1, "0" * 40)
    refusals = {
        "counted non-clear": clean + [kill("a", "w", sha=sha, clear=False)],
        "excluded for no_evidence": clean + [kill("a", "n", sha=sha, pointer=None)],
        "mixes binaries": clean + [kill("a", "k2", sha="2" * 64, validity=STALLED)],
        "already has 3 counted native clears": clean + [kill("a", "k9", sha=sha)],
    }
    for message, kills in refusals.items():
        with pytest.raises(SystemExit, match=message):
            top_up_plan(kills, target, binary, _top_up_args("a"))
    other = [kill("a", f"o{i}", sha="2" * 64) for i in range(2)] + [kill("a", "o2", sha="2" * 64, validity=STALLED)]
    with pytest.raises(SystemExit, match="not the label's binary"):
        top_up_plan(other, target, binary, _top_up_args("a"))
    with pytest.raises(SystemExit, match="--source-commit differs"):
        top_up_plan(clean + [stalled], target, binary, _top_up_args("a", source_commit="f" * 40))
    extend = _top_up_args("a")
    extend.target_kills = 5
    assert top_up_plan(clean + [kill("a", "k9", sha=sha)], target, binary, extend) == (2, "0" * 40)


def test_run_refuses_an_existing_label_without_top_up(root):
    batch(root, "a")
    with pytest.raises(SystemExit, match="--top-up"):
        scoreboard_run.run_batch(root, _top_up_args("a", top_up=False, dry_run=True))


# --- encounter RNG (informational) --------------------------------------------------------------

def crash(*sides):
    return {"basis": "harness", "massive_crash": [{"side": side, "side_basis": "source_position", "at_sec": 99.5,
                                                   "players_hit": 9 if side == "raid_wide" else 0, "units_hit": 9}
                                                  for side in sides]}


def rng_batch(root, label, sides, **options):
    record_all(root, *(kill(label, f"k{i}", encounter_rng=crash(side), **options) for i, side in enumerate(sides)))


def rng_lines(text):
    return [line for line in text.splitlines() if "RNG" in line]


def test_show_prints_the_side_mix_and_warns_when_labels_differ(root):
    rng_batch(root, "new", ["raid_wide"] * 4)
    rng_batch(root, "old", ["raid_wide", "far", "raid_wide", "far", "far"])
    record_all(root, kill("old", "stalled", validity=STALLED, encounter_rng=crash("raid_wide")))
    assert rng_lines(render(root, SCENARIO, "new", "old")) == [
        "encounter RNG (informational) new: massive_crash raid_wide 4/4 counted (all kills 4/4)",
        "encounter RNG (informational) old: massive_crash raid_wide 2/5 counted (all kills 3/6)",
        "RNG mix differs: massive_crash raid_wide 4/4 vs 2/5, interpret actor deltas with care"]
    assert rng_lines(render(root, SCENARIO, "new")) == [
        "encounter RNG (informational) new: massive_crash raid_wide 4/4 counted (all kills 4/4)"]


def test_rng_mix_within_one_kill_is_not_a_warning(root):
    rng_batch(root, "new", ["raid_wide", "raid_wide", "far"])
    rng_batch(root, "old", ["raid_wide", "far", "far"])
    record_all(root, kill("new", "legacy"), kill("new", "late", encounter_rng=crash()))
    lines = rng_lines(render(root, SCENARIO, "new", "old"))
    assert not any(line.startswith("RNG mix differs") for line in lines)
    assert lines[0] == ("encounter RNG (informational) new: massive_crash raid_wide 2/3 counted (all kills 2/3), "
                        "no event in 1 kill(s); not recorded for 1 of 5 kills (scoreboard rng-backfill)")


def test_rng_never_changes_counting_the_verdict_or_the_comparison(root):
    batch(root, "a")
    batch(root, "b", scales=(0.9, 0.91, 0.92))
    before = (evaluate_target(root, SCENARIO, "a"), compare_labels(root, SCENARIO, "a", "b"))
    for label in ("a", "b"):
        for record in label_kills_of(root, label):
            append_record(root, SCENARIO, {"schema": "raid_scoreboard_rng_attachment_v1", "kill_id": record["kill_id"],
                                           "encounter_rng": crash("raid_wide" if label == "a" else "far"),
                                           "recorded_at": "2026-09-23T12:00:00Z"})
    assert (evaluate_target(root, SCENARIO, "a"), compare_labels(root, SCENARIO, "a", "b")) == before
    assert "RNG mix differs: massive_crash raid_wide 3/3 vs 0/3" in render(root, SCENARIO, "a", "b")


def label_kills_of(root, label):
    return [record for record in load_records(root, SCENARIO) if record["label"] == label]


def test_rng_attachment_fills_only_kills_without_rng(root):
    record_all(root, kill("a", "k0"), kill("a", "k1", encounter_rng=crash("far")))
    for name in ("k0", "k1", "k0"):
        append_record(root, SCENARIO, {"schema": "raid_scoreboard_rng_attachment_v1", "kill_id": f"a-{name}",
                                       "encounter_rng": crash("raid_wide"), "recorded_at": f"T-{name}"})
    k0, k1 = load_records(root, SCENARIO)
    assert k0["encounter_rng"]["massive_crash"][0]["side"] == "raid_wide" and k0["encounter_rng_attached_at"] == "T-k0"
    assert k1["encounter_rng"]["massive_crash"][0]["side"] == "far" and "encounter_rng_attached_at" not in k1


def test_rng_backfill_appends_one_line_per_kill_and_is_rerunnable(root, tmp_path, capsys):
    evidence = tmp_path / "evidence"
    kills = [kill("old", f"k{i}") | {"run_dir": f"/tmp/scoreboard-old-k{i}"} for i in range(3)]
    record_all(root, *kills)
    for index, dummy in enumerate(([-288.59, -14.847], [-294.736, -11.431])):
        run = evidence / f"old-k{index}" / f"scoreboard-old-k{index}"
        run.mkdir(parents=True)
        (run / "report.json").write_text(json.dumps({"validation_route_manifest": {"routes": [
            {"route_node_id": "bwd.magmaw.encounter", "kind": "boss", "source_entry": 41570}]}}))
        events = [{"kind": "damage", "spell_id": 88287, "timestamp_ms": 1000, "source_entry": 47330, "source_guid": 41,
                   "source_x": dummy[0], "source_y": dummy[1], "target_guid": 30001, "target_entry": 0,
                   "route_node_id": "bwd.magmaw.encounter", "amount": 1}]
        (run / "combat_log.json").write_text(json.dumps({"recent_events": events, "recent_events_dropped": 0}))
    before = len(load_lines(root, SCENARIO))
    args = ["--root", str(root), "rng-backfill", "--scenario", SCENARIO, "--label", "old", "--evidence-root", str(evidence)]
    assert main(args) == 1  # k2 has no extracted evidence
    lines = load_lines(root, SCENARIO)
    assert len(lines) == before + 2 and {line["schema"] for line in lines[before:]} == {"raid_scoreboard_rng_attachment_v1"}
    assert lines[before]["source_run_dir"] == "scoreboard-old-k0" and len(lines[before]["combat_log_sha256"]) == 64
    records = {record["kill_id"]: record for record in load_records(root, SCENARIO)}
    assert [row["side"] for row in records["old-k0"]["encounter_rng"]["massive_crash"]] == ["raid_wide"]
    assert [row["side"] for row in records["old-k1"]["encounter_rng"]["massive_crash"]] == ["far"]
    assert "encounter_rng" not in records["old-k2"]
    assert "old-k2: no run dir with combat_log.json" in capsys.readouterr().out
    assert main(args) == 1 and len(load_lines(root, SCENARIO)) == before + 2  # reruns skip attached kills
    with pytest.raises(SystemExit, match="no kills recorded under nope"):
        main(args[:6] + ["nope"] + args[7:])


def test_record_keeps_rng_from_the_harness_or_recomputes_it(tmp_path):
    from tools.raid_program.scoreboard_record import outcome_summary
    old = outcome_summary(magmaw_run_dir(tmp_path / "old"), None, "bwd.magmaw.encounter")
    assert old["encounter_rng"] == {"basis": "combat_log_recomputed", "massive_crash": []}
    harness = {"schema": "encounter_rng_v1", "massive_crash": [{"side": "far", "side_basis": "source_position",
                                                                "at_sec": 99.7, "players_hit": 0, "units_hit": 1}]}
    new = outcome_summary(magmaw_run_dir(tmp_path / "new", report_extra={"encounter_rng": harness}), None,
                          "bwd.magmaw.encounter")
    assert new["encounter_rng"] == {"basis": "harness", "massive_crash": harness["massive_crash"]}
    target = load_target(ROOT, SCENARIO)
    record = record_from_summary({"native_clear": True, "completion_reason": CLEAR, "actors": [],
                                  "encounter_rng": new["encounter_rng"]}, root=ROOT, target=target, scenario=SCENARIO,
                                 label="x", kill_id="x-1", deaths={"boss_window_deaths": 0, "deaths": []})
    assert record["encounter_rng"] == new["encounter_rng"]
