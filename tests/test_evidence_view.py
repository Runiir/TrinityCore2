import copy
import io
import json
import tarfile

import pytest

from tools.raid_program.evidence_events import query_events
from tools.raid_program.evidence_inputs import load_input, select_path
from tools.raid_program.evidence_metrics import native_actors, simulator_actor
from tools.raid_program.evidence_view import comparison, compact_comparison, main


def calibration(damage=1000, spell_damage=800, guid=1):
    return {"combat_calibration": {"window_complete": True, "scored_seconds": 300,
        "scored_started_at_ms": 10000, "scored_ended_at_ms": 310000,
        "server_epoch": 7, "attempt_id": 1, "cohort_id": "a", "target_spec": "test_spec",
        "bots": [{"guid": guid, "damage": damage, "dps": 99999, "pet_damage": 200,
            "spell_damage": [{"spell_id": 10, "damage": spell_damage, "event_count": 4}],
            "action_attempts": [{"spell_id": 10, "count": 999}],
            "decision_timeline": [{"elapsed_ms": 0, "spell_id": 10, "result": "ok"},
                                  {"elapsed_ms": 1000, "spell_id": 10, "result": "casting"}],
            "scoring_start_stats": {"player": {"intellect": 100, "observed_at_ms": 10000}},
            "healer_metrics": {"effective_hps": 2}}]}}


def sim():
    return {"schema": "rotation_review_wowsims_result_v1", "avg_iteration_duration_seconds": 300,
        "player_dps": {"avg": 5}, "iterations_done": 2000,
        "action_metrics": [{"identity": {"kind": "spell", "id": 10, "tag": tag},
            "source": {"kind": source}, "per_iteration_target_metric_sums": {"damage": damage, "casts": casts}}
            for tag, source, damage, casts in [(0, "player", 900, 10), (71086, "player", 100, 1),
                                              (123, "player", 50, 2), (0, "pet", 150, 5)]]}


def timeline():
    return {"identity": {"server_epoch": 7},
        "window": {"complete": True, "elapsed_seconds": 10, "first_hostile_at_ms": 1000,
                   "native_boss_death_at_ms": 11000},
        "summary": {"actors": {"1": {"class_spec": "example", "damage": {"hostile_originated": 1000}, "effective_hps": 5}}},
        "events": [dict(actor_guid=1, kind="landed", at_ms=2000, amount=600, spell_id=10, source_is_pet=False),
                   dict(actor_guid=1, kind="landed", at_ms=8000, amount=400, spell_id=10, source_is_pet=True)]}


def test_actual_window_ignores_embedded_dps_and_selections_are_not_casts():
    a = native_actors(calibration())["1"]
    assert a["dps"] == 1000 / 300
    row = a["components"]["10"]
    assert row["ordinary_casts"] is None
    assert row["observed_successful_submissions"] == 1
    assert a["activity"]["pet_damage"] == 200
    assert sum(c["damage"] for c in a["components"].values()) == 800


def test_signed_components_and_unknown_reconcile_without_claiming_recovery():
    d = comparison(calibration(), calibration(1600, 1200), "native")["pairs"][0]
    r = d["reconciliation"]
    assert r["total_gap_dps"] == pytest.approx(2)
    assert r["signed_component_gap_dps"] == pytest.approx(400 / 300)
    assert r["unattributed_residual_dps"] == pytest.approx(200 / 300)
    assert d["components"][0]["recoverable_dps"] is None


def test_sim_copies_pets_other_tags_separate_from_ordinary_casts():
    row = simulator_actor(sim())["components"]["10"]
    assert row["ordinary_casts"] == 10
    assert row["triggered_copies"] == 1
    assert row["other_tagged_casts"] == 2
    assert row["pet_casts"] == 5
    assert row["damage"] == 1200
    d = comparison(calibration(), sim(), "wowsims")["pairs"][0]
    assert d["reconciliation"]["total_gap_dps"] == pytest.approx(500/300)
    assert d["reference"]["gates"]["effective_stat_parity"] == {}
    assert d["status"] == "diagnostic_only"


def test_missing_simulator_fields_propagate_unknown_not_zero():
    result = sim()
    result["action_metrics"][0]["per_iteration_target_metric_sums"].pop("damage")
    result["action_metrics"][0]["per_iteration_target_metric_sums"].pop("casts")
    row = simulator_actor(result)["components"]["10"]
    assert row["damage"] is None and row["ordinary_casts"] is None
    assert row["hits"] is None and row["ticks"] is None and row["crit_ticks"] is None
    assert row["triggered_copies"] == 1
    p = comparison(calibration(), result, "wowsims")["pairs"][0]
    assert p["components"][0]["apparent_gap_dps"] is None


def test_same_guid_different_spec_or_mode_is_explicitly_incompatible():
    ref = calibration()
    ref["combat_calibration"].update(target_spec="other_spec", mode="aoe", cohort_id="other")
    p = comparison(calibration(), ref, "native")["pairs"][0]
    assert p["status"] == "incompatible_context"
    assert p["context_comparison"]["checks"]["spec"]["status"] == "mismatch"
    assert p["context_comparison"]["checks"]["mode"]["status"] == "missing"
    assert p["context_comparison"]["identity_differences"]
    current = calibration();current["combat_calibration"]["mode"] = "single_target_300"
    ref["combat_calibration"]["target_spec"] = "test_spec"
    assert comparison(current, ref, "native")["pairs"][0]["status"] == "incompatible_context"


def test_missing_component_is_unknown_not_zero():
    ref = calibration(1000)
    ref["combat_calibration"]["bots"][0]["spell_damage"][0]["spell_id"] = 11
    d = comparison(calibration(), ref, "native")["pairs"][0]
    assert all(r["apparent_gap_dps"] is None for r in d["components"])
    assert d["reconciliation"]["signed_component_gap_dps"] == 0


def test_setup_difference_kept_and_incomplete_window_rejected():
    ref = calibration()
    ref["combat_calibration"]["bots"][0]["scoring_start_stats"]["player"]["intellect"] = 680
    d = comparison(calibration(), ref, "native")["pairs"][0]
    assert {"field": "stats.intellect", "current": 100, "reference": 680} in d["setup_differences"]
    ref["combat_calibration"]["window_complete"] = False
    with pytest.raises(ValueError, match="completed"):
        native_actors(ref)


def test_completed_current_window_precedes_legacy_previous_without_clock():
    doc = calibration()
    doc["combat_calibration"]["previous_window"] = {"bots": [], "mode": "single_target_300"}
    assert native_actors(doc)["1"]["dps"] == 1000/300
    assert query_events(doc)["matching_records"] == 2


def test_timeline_pet_attribution_and_wcl_duty_not_removed_from_denominator():
    t = timeline()
    a = native_actors(t)["1"]
    assert a["components"]["10"]["pet_damage"] == 400
    refs = {"native_identity": t["identity"], "actors": {"1": {
        "url": "https://example.test/report", "dps": 130, "limitations": "unmatched gear",
        "next_check": "stats", "duties": [{"provenance": "observed", "interval_ms": [6000, 11000]}],
        "components": [{"name": "owner", "spell_ids": [10], "dps": 80}]}}}
    d = comparison(t, refs, "wcl")["actors"][0]
    assert d["native_dps"] == 100
    assert d["observed_duty_union_seconds"] == 5
    assert d["reconciliation"]["unattributed_residual_dps"] == 10
    refs["native_identity"] = {"server_epoch": 8}
    with pytest.raises(ValueError, match="identity"):
        comparison(t, refs, "wcl")


def test_all_actor_overview_pages_without_silently_matching_specs():
    current, baseline = calibration(), calibration()
    current["combat_calibration"]["bots"] *= 1
    for i in range(2, 26):
        b = copy.deepcopy(current["combat_calibration"]["bots"][0]);b["guid"] = i
        current["combat_calibration"]["bots"].append(b)
    baseline = copy.deepcopy(current)
    d = comparison(current, baseline, "native")
    view = compact_comparison(d)
    assert len(view["pairs"]) == 10 and view["pair_count"] == 25
    assert view["next_offset"] == 10
    assert len(json.dumps(view)) < 16000
    with pytest.raises(ValueError, match="requires --actor"):
        comparison(current, sim(), "wowsims")


def test_event_page_preserves_equal_time_order_and_records_missing_fields():
    t = timeline()
    t["events"] = [{"at_ms": 2000, "actor_guid": 1, "kind": k, "spell_id": 10,
        "sequence": i, "cast_instance_id": 42} for i, k in enumerate(("finish", "prepare", "landed"))]
    t["events"].append({"actor_guid": 1, "kind": "landed", "spell_id": 10})
    page = query_events(t, actor="1", spell="10", start_ms=0, end_ms=2000, limit=2)
    assert [r["kind"] for r in page["records"]] == ["finish", "prepare"]
    assert page["next_offset"] == 2 and page["matching_records"] == 3
    assert page["excluded_missing_observations"] == {"missing_relative_clock": 1}
    assert page["records"][0]["elapsed_ms"] == 1000
    assert "phase" in page["records"][0]["missing_observations"]
    assert query_events(t, phase="head")["excluded_missing_observations"]["missing_phase"] == 4


def test_calibration_events_do_not_emit_nested_snapshots():
    c = calibration()
    c["combat_calibration"]["bots"][0]["decision_timeline"][0]["summon_observation"] = {"large": "x"*100000}
    page = query_events(c, actor="1", limit=1)
    assert page["records"][0]["at_ms"] == 10000
    assert len(json.dumps(page)) < 2000


def test_exact_archive_member_no_extraction_and_cli(tmp_path, capsys):
    archive = tmp_path / "data.tar.gz"
    payload = json.dumps(calibration()).encode()
    with tarfile.open(archive, "w:gz") as t:
        info = tarfile.TarInfo("nested/report.json");info.size = len(payload)
        t.addfile(info, io.BytesIO(payload))
    spec = f"{archive}::nested/report.json"
    d, receipt = load_input(spec)
    assert receipt["payload_bytes"] == len(payload)
    assert not (tmp_path / "nested").exists()
    assert main(["compare", "--current", spec, "--baseline", spec]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["pairs"][0]["delta_dps_current_minus_reference"] == 0
    with pytest.raises(ValueError, match="exactly one"):
        load_input(f"{archive}::report.json")


def test_native_mapping_is_explicit_for_changed_actor_ids():
    d = comparison(calibration(guid=1), calibration(guid=2), "native", actor="1", reference_actor="2")
    assert d["pairs"][0]["reference"]["actor"] == "2"
    with pytest.raises(ValueError, match="baseline-actor"):
        comparison(calibration(guid=1), calibration(guid=2), "native")


def test_wcl_catalog_requires_reference_and_leaves_unavailable_spell_damage_unknown():
    r = {"id": "r1", "url": "https://example.test/r1", "duration_sec": 100,
         "mode": "10N", "actor_dps": {"test_spec": 9}, "limitations": ["different gear"]}
    catalog = {"references": [r, {**r, "id": "r2"}]}
    with pytest.raises(ValueError, match="reference-id"):
        comparison(calibration(), catalog, "wcl")
    p = comparison(calibration(), catalog, "wcl", reference_id="r1")["pairs"][0]
    assert p["reference"]["dps"] == 9
    assert p["reconciliation"]["unattributed_residual_dps"] == pytest.approx(9-1000/300)
    assert all(c["reference_dps"] is None for c in p["components"])


def test_wcl_manifest_casts_remain_separate_from_native_landed_events():
    manifest = {"reference_id": "r1", "duration_sec": 100, "actors": [
        {"actor_id": "wcl1", "class_spec": "test_spec", "observed_dps": 9,
         "casts": [{"ability": "a", "t": 0}, {"ability": "a", "t": 3}]}]}
    p = comparison(calibration(), manifest, "wcl")["pairs"][0]
    assert p["reference"]["activity"]["completed_casts_by_ability"] == {"a": 2}
    assert p["reconciliation"]["unattributed_residual_dps"] == pytest.approx(9-1000/300)


def test_event_target_filter_retains_binding_distinction():
    t = timeline()
    t["events"] = [{"actor_guid": 1, "kind": "decision", "at_ms": 2000,
                    "native_selected_target": {"guid": 10}, "state_bound_target": {"guid": 20}}]
    page = query_events(t, target="20")
    assert page["matching_records"] == 1
    assert page["records"][0]["native_selected_target"]["guid"] == 10
    assert "target_guid" not in page["records"][0]


def test_output_budget_errors_instead_of_truncating_json(tmp_path, capsys):
    p = tmp_path / "t.json"
    t = timeline();t["events"][0]["reason"] = "x" * 20000
    p.write_text(json.dumps(t))
    with pytest.raises(SystemExit) as exc:
        main(["events", str(p)])
    captured = capsys.readouterr()
    assert exc.value.code == 2 and not captured.out
    assert "stdout budget" in captured.err


def test_event_locator_resolves_original_record_and_select_paginates():
    doc = calibration()
    row = query_events(doc, limit=1)["records"][0]
    selected = select_path(doc, row["locator"])
    assert selected["value"]["result"] == "ok"
    assert select_path(doc, "/combat_calibration/bots/0/decision_timeline", limit=1)["next_offset"] == 1
    assert select_path({"a/b": {"~": 3}}, "/a~1b/~0")["value"] == 3
    with pytest.raises(ValueError, match="Pointer"):
        select_path(doc, "")
