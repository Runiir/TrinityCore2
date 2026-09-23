import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.raid_program import scoreboard_run
from tools.raid_program.scoreboard import (
    KILL_SCHEMA, append_record, evaluate_target, load_records, main, party_reference_dps, scoreboard_path,
    spec_targets, load_target,
)
from tools.raid_program.scoreboard_record import death_evidence, is_native_clear, record_from_summary
from tools.raid_program.scoreboard_show import keep_recommendation, noise_verdict, render

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "blackwing_descent_10n_magmaw"
TARGET = f"experiments/configs/raid_targets/{SCENARIO}.json"
SUMMARIES = "artifacts/cata_raid_program/magmaw_spell_queue_{}_summary_20260922.json"
ROSTER = {  # actor id: (spec, role, fraction of the WCL target)
    "30001": ("balance_druid", "dps", 1.0),
    "30002": ("blood_death_knight", "tank", 1.0),
    "30003": ("restoration_druid", "healer", 0.0),
    "30006": ("fire_mage", "dps", 0.96),
}
WCL = {"balance_druid": 41029.1, "blood_death_knight": 26152.0, "fire_mage": 40189.9}


@pytest.fixture
def root(tmp_path):
    target = json.loads((ROOT / TARGET).read_text())
    for relative in (TARGET, target["wcl_reference_manifest"], target["wcl_cast_timelines"]):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / relative, tmp_path / relative)
    return tmp_path


def kill(label, *, scale=1.0, clear=True, window_deaths=0, route_deaths=0, roster=ROSTER, name="k"):
    actors = [{"actor_id": actor_id, "name": f"bot{actor_id}", "spec": spec, "role": role,
               "encounter_window_dps": (WCL.get(spec, 3000.0) * fraction or 3000.0) * scale,
               "damage_uptime": 0.8, "casts_per_minute": 30.0, "hps": 0.0}
              for actor_id, (spec, role, fraction) in roster.items()]
    return {"schema": KILL_SCHEMA, "scenario": SCENARIO, "label": label, "recorded_at": "2026-09-23T00:00:00Z",
            "source_commit": "0" * 40, "worldserver_sha256": "1" * 64, "run_dir": f"/tmp/{name}",
            "evidence_dvc_pointer": None, "native_clear": clear, "completion_reason": "x",
            "route_deaths": route_deaths, "boss_window_deaths": window_deaths, "death_basis": "test", "deaths": [],
            "encounter": {"duration_sec": 120.0, "encounter_window_party_dps": 240000.0 * scale, "party_hps": 20000.0},
            "actors": actors, "ranked_gaps": []}


def record_all(root, *kills):
    for row in kills:
        append_record(root, SCENARIO, row)


def test_committed_target_resolves_matched_wcl_targets():
    target = load_target(ROOT, SCENARIO)
    targets = spec_targets(ROOT, target)
    assert targets["balance_druid"] == 41029.1 and targets["blood_death_knight"] == 26152.0
    assert "survival_hunter" not in targets  # the matched fight has no hunter
    assert party_reference_dps(ROOT, target) == 246232.7
    assert target["kills_per_measurement"] == 3 and target["actor_dps_ratio"] == 0.95
    argv = target["run_plan"]["argv_template"]
    assert "{worldserver}" in argv and "{output_dir}" in argv and "completion-watchdog" in argv
    source = ROOT / target["run_plan"]["argv_template_source"]
    if source.exists():
        assert json.loads(source.read_text())["argv_template"] == argv


def test_three_passing_kills_pass(root):
    record_all(root, *(kill("a", scale=s, name=f"k{i}") for i, s in enumerate((1.0, 1.02, 0.99))))
    verdict = evaluate_target(root, SCENARIO)
    assert verdict["schema"] == "raid_target_verdict_v1" and verdict["label"] == "a" and verdict["kills"] == 3
    assert verdict["status"] == "pass" and verdict["reason"] is None
    assert verdict["encounter"]["status"] == "pass" and verdict["encounter"]["clears"] == 3
    fire = verdict["actors"]["30006"]
    assert fire["target_dps"] == 40189.9 and fire["status"] == "pass" and fire["n"] == 3
    healer = verdict["actors"]["30003"]
    assert healer["target_dps"] is None and healer["ratio"] is None and healer["status"] == "pass"


def test_low_actor_fails_and_insufficient_kills_before_three(root):
    record_all(root, kill("a", scale=0.9, name="k1"), kill("a", scale=0.9, name="k2"))
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["status"] == "insufficient_kills"
    assert {row["status"] for row in verdict["actors"].values()} == {"insufficient_kills"}
    append_record(root, SCENARIO, kill("a", scale=0.9, name="k3"))
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["status"] == "fail" and verdict["actors"]["30001"]["status"] == "fail"
    assert "30001" in verdict["reason"]


def test_missing_reference_is_never_a_pass(root):
    roster = {**ROSTER, "30009": ("survival_hunter", "dps", 1.0)}
    record_all(root, *(kill("a", roster=roster, name=f"k{i}") for i in range(3)))
    verdict = evaluate_target(root, SCENARIO, "a")
    hunter = verdict["actors"]["30009"]
    assert hunter["status"] == "no_reference" and hunter["target_dps"] is None and hunter["ratio"] is None
    assert verdict["status"] == "fail" and "no matched WCL reference" in verdict["reason"]


def test_non_clear_and_boss_window_deaths_fail_the_encounter(root):
    record_all(root, kill("wipe", name="k1"), kill("wipe", clear=False, name="k2"), kill("wipe", name="k3"))
    record_all(root, *(kill("dead", window_deaths=d, name=f"d{i}") for i, d in enumerate((0, 1, 0))))
    record_all(root, *(kill("unknown", window_deaths=d, name=f"u{i}") for i, d in enumerate((0, None, 0))))
    for label, text in (("wipe", "not a native clear"), ("dead", "boss-window deaths"), ("unknown", "unknown")):
        verdict = evaluate_target(root, SCENARIO, label)
        assert verdict["encounter"]["status"] == "fail" and verdict["status"] == "fail"
        assert text in verdict["reason"]
        assert verdict["actors"]["30003"]["status"] == "fail"  # healers follow the encounter
    assert evaluate_target(root, SCENARIO, "wipe")["encounter"]["clears"] == 2


def test_no_kills_is_insufficient(root):
    verdict = evaluate_target(root, SCENARIO)
    assert verdict["kills"] == 0 and verdict["label"] is None and verdict["status"] == "insufficient_kills"
    assert verdict["actors"] == {} and verdict["encounter"]["status"] == "insufficient_kills"


def test_noise_rule():
    assert noise_verdict([1.0, 2.0], [1.0, 2.0, 3.0])["verdict"] == "insufficient_kills"
    base = [100.0, 110.0, 90.0]  # sd 10
    threshold = 2 * (2 * 10 ** 2 / 3) ** 0.5  # 16.33
    assert noise_verdict([x + 20 for x in base], base)["verdict"] == "improved"
    assert noise_verdict([x - 20 for x in base], base)["verdict"] == "regressed"
    change = noise_verdict([x + 10 for x in base], base)
    assert change["verdict"] == "within_noise" and change["threshold"] == pytest.approx(threshold)
    assert change["delta"] == pytest.approx(10.0)


def test_keep_rule():
    up, flat, down = ({"verdict": v} for v in ("improved", "within_noise", "regressed"))
    actors = {"1": {**flat, "gating": True}, "2": {**down, "gating": False}}
    common = dict(new_deaths_per_kill=0.0, old_deaths_per_kill=0.0, new_non_clears=0)
    assert keep_recommendation(up, actors, targeted_actor=None, **common)[0] == "keep"
    assert keep_recommendation(flat, actors, targeted_actor=None, **common)[0] == "revert"
    targeted = {"1": {**up, "gating": True}}
    assert keep_recommendation(flat, targeted, targeted_actor="1", **common)[0] == "keep"
    decision, reasons = keep_recommendation(up, {"1": {**down, "gating": True}}, targeted_actor=None, **common)
    assert decision == "revert" and "regressed" in reasons[0]
    assert keep_recommendation(up, actors, targeted_actor=None, new_deaths_per_kill=1.0,
                               old_deaths_per_kill=0.0, new_non_clears=0)[0] == "revert"
    assert keep_recommendation({"verdict": "insufficient_kills"}, actors, targeted_actor=None,
                               **common)[0] == "insufficient_kills"


def test_show_compares_labels(root):
    record_all(root, *(kill("old", scale=s, name=f"o{i}") for i, s in enumerate((0.80, 0.81, 0.79))))
    record_all(root, *(kill("new", scale=s, name=f"n{i}") for i, s in enumerate((1.00, 1.01, 0.99))))
    text = render(root, SCENARIO, "new", "old")
    assert "keep/revert: keep" in text and "improved" in text and "kill time" in text
    assert "(healer, not gating)" in text


def test_record_from_committed_summary():
    summary = json.loads((ROOT / SUMMARIES.format("base1")).read_text())
    targets = spec_targets(ROOT, load_target(ROOT, SCENARIO))
    deaths = death_evidence(None, "bwd.magmaw.encounter", summary["route_deaths"])
    record = record_from_summary(summary, scenario=SCENARIO, label="base", targets=targets, deaths=deaths)
    assert record["schema"] == KILL_SCHEMA and record["native_clear"] is True
    assert record["boss_window_deaths"] == 0 and record["death_basis"] == "no_route_deaths"
    actor = next(row for row in record["actors"] if row["actor_id"] == "30001")
    assert actor["spec"] == "balance_druid" and actor["encounter_window_dps"] == 23764.92
    assert set(actor) == {"actor_id", "name", "spec", "role", "encounter_window_dps",
                          "damage_uptime", "casts_per_minute", "hps"}
    # base1 shortfalls: balance 17264, fire mage a 15967, blood DK 14608 DPS
    assert [gap["actor_id"] for gap in record["ranked_gaps"]] == ["30001", "30006", "30002"]
    sq1 = json.loads((ROOT / SUMMARIES.format("sq1")).read_text())
    assert death_evidence(None, "bwd.magmaw.encounter", sq1["route_deaths"])["boss_window_deaths"] is None


def test_clear_needs_complete_route_manifest():
    assert is_native_clear({"native_clear": True, "completion_reason": "validation_route_manifest_complete"})
    assert not is_native_clear({"native_clear": True, "completion_reason": "watchdog_no_progress"})
    assert not is_native_clear({"native_clear": False, "completion_reason": "validation_route_manifest_complete"})


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
    unreconciled = death_evidence(tmp_path, "bwd.magmaw.encounter", 3)
    assert unreconciled["boss_window_deaths"] is None


def test_run_dry_run_executes_nothing(root, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry run must not execute anything")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(scoreboard_run.subprocess, "run", forbidden)
    append_record(root, SCENARIO, kill("sq", name="k1"))
    assert main(["--root", str(root), "run", "--scenario", SCENARIO, "--label", "sq", "--kills", "2",
                 "--worldserver", "/opt/ws", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count("bot-live-validate --worldserver /opt/ws") == 2
    assert "--output-dir /tmp/scoreboard-sq-k2-" in out and "--output-dir /tmp/scoreboard-sq-k3-" in out
    assert "experiments.archive_run_evidence --name scoreboard_blackwing_descent_10n_magmaw_sq_k2_" in out
    assert "{output_dir}" not in out and len(load_records(root, SCENARIO)) == 1


def test_ingest_summaries(root, capsys):
    pointer = "artifacts/cata_raid_program/example.tar.gz.dvc"
    (root / pointer).parent.mkdir(parents=True, exist_ok=True)
    (root / pointer).write_text("outs: []\n")
    assert main(["--root", str(root), "ingest", "--scenario", SCENARIO, "--label", "base",
                 "--summary", str(ROOT / SUMMARIES.format("base1")), "--evidence-pointer", pointer,
                 "--source-commit", "f" * 40]) == 0
    record, = load_records(root, SCENARIO)
    assert record["label"] == "base" and record["evidence_dvc_pointer"] == pointer
    assert record["source_commit"] == "f" * 40 and record["worldserver_sha256"].startswith("529ebc")
    assert scoreboard_path(root, SCENARIO).read_text().count("\n") == 1


def test_committed_scoreboard_is_valid():
    records = load_records(ROOT, SCENARIO)
    if not records:
        pytest.skip("scoreboard not backfilled")
    labels = {record["label"] for record in records}
    assert {"base-529ebc", "spellqueue-b8a897"} <= labels
    for record in records:
        assert {"label", "recorded_at", "source_commit", "worldserver_sha256", "run_dir", "evidence_dvc_pointer",
                "native_clear", "route_deaths", "boss_window_deaths", "encounter", "actors"} <= set(record)
        assert all(isinstance(actor["actor_id"], str) for actor in record["actors"])
