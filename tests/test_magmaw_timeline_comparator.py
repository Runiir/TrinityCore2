from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml.compare_magmaw_timelines import (
    _ability_diffs,
    _damage_classification,
    compare_timelines,
    main,
    normalize_ability,
    parse_time,
    parse_wcl_csv,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_wcl_parser_keeps_completed_casts_and_drops_begin_cast_rows(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "wcl.csv"
    csv_path.write_text(
        "Time,Type,Ability,Source → Target\n"
        "0:00.100,Cast,Starfire 2.00 sec,Inkar → Magmaw\n"
        "0:00.120,Begin Cast,Starfire 2.00 sec,Inkar → Magmaw\n"
        "0:01.500,Cast,Wrath Canceled,Inkar → Magmaw\n",
        encoding="utf-8",
    )

    parsed = parse_wcl_csv(
        csv_path,
        actor_id="source5",
        class_spec="balance_druid",
    )

    assert parse_time("1:02.500") == 62.5
    assert normalize_ability("Starfire 2.00 sec") == "Starfire"
    assert normalize_ability("Wrath Canceled") == "Wrath"
    assert [row["ability"] for row in parsed["casts"]] == ["Starfire", "Wrath"]
    assert parsed["casts"][0]["target"] == "Magmaw"


def test_compare_timelines_covers_all_local_roles_and_marks_missing_wcl(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_json(
        run_dir / "report.json",
        {
            "run_id": "timeline-test",
            "bots": [
                {
                    "guid": 30001,
                    "bot_name": "Balance",
                    "role": "dps",
                    "class_spec": "balance_druid",
                },
                {
                    "guid": 30006,
                    "bot_name": "Fire A",
                    "role": "dps",
                    "class_spec": "fire_mage",
                },
                {
                    "guid": 30007,
                    "bot_name": "Fire B",
                    "role": "dps",
                    "class_spec": "fire_mage",
                },
                {
                    "guid": 30009,
                    "bot_name": "Survival",
                    "role": "dps",
                    "class_spec": "survival_hunter",
                },
                {
                    "guid": 30002,
                    "bot_name": "Blood",
                    "role": "tank",
                    "class_spec": "blood_death_knight",
                },
                {
                    "guid": 30003,
                    "bot_name": "Healer",
                    "role": "healer",
                    "class_spec": "restoration_druid",
                },
            ],
        },
    )
    _write_json(
        run_dir / "combat_analysis.json",
        {
            "encounters": [
                {
                    "route_node_id": "bwd.magmaw.encounter",
                    "first_at_ms": 1000,
                    "duration_sec": 10.0,
                    "actors": [
                        {
                            "actor_guid": 30001,
                            "actor_class_id": 11,
                            "actor_role": "dps",
                            "actor_name": "Balance",
                            "encounter_window_dps": 1000,
                            "active_dps": 1000,
                            "damage_uptime": 0.8,
                            "moving_fraction": 0.1,
                        },
                        {
                            "actor_guid": 30006,
                            "actor_class_id": 8,
                            "actor_role": "dps",
                            "actor_name": "Fire A",
                            "encounter_window_dps": 1000,
                        },
                        {
                            "actor_guid": 30007,
                            "actor_class_id": 8,
                            "actor_role": "dps",
                            "actor_name": "Fire B",
                            "encounter_window_dps": 1000,
                        },
                        {
                            "actor_guid": 30009,
                            "actor_class_id": 3,
                            "actor_role": "dps",
                            "actor_name": "Survival",
                            "encounter_window_dps": 1000,
                        },
                        {
                            "actor_guid": 30002,
                            "actor_class_id": 6,
                            "actor_role": "tank",
                            "actor_name": "Blood",
                            "encounter_window_dps": 500,
                        },
                        {
                            "actor_guid": 30003,
                            "actor_class_id": 11,
                            "actor_role": "healer",
                            "actor_name": "Healer",
                            "encounter_window_dps": 0,
                        },
                    ],
                },
            ],
        },
    )
    _write_json(
        run_dir / "combat_log.json",
        {
            "recent_events": [
                {
                    "kind": "damage",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "actor_guid": 30001,
                    "timestamp_ms": 1100,
                    "spell_id": 2912,
                    "spell_name": "Starfire",
                    "originated_amount": 1000,
                },
                {
                    "kind": "damage",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "actor_guid": 30001,
                    "timestamp_ms": 2100,
                    "spell_id": 2912,
                    "spell_name": "Starfire",
                    "originated_amount": 1000,
                },
                {
                    "kind": "damage",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41806,
                    "actor_guid": 30001,
                    "timestamp_ms": 3100,
                    "spell_id": 8921,
                    "spell_name": "Moonfire",
                    "effect_type": 2,
                    "originated_amount": 100,
                },
                {
                    "kind": "damage",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "actor_guid": 30006,
                    "timestamp_ms": 1200,
                    "spell_id": 133,
                    "spell_name": "Fireball",
                    "originated_amount": 800,
                },
                {
                    "kind": "damage",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "actor_guid": 30001,
                    "timestamp_ms": 7100,
                    "spell_id": 2912,
                    "spell_name": "Starfire",
                    "originated_amount": 700,
                },
                {
                    "kind": "damage",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "actor_guid": 30002,
                    "timestamp_ms": 1500,
                    "spell_id": 45477,
                    "spell_name": "Icy Touch",
                    "originated_amount": 500,
                },
                {
                    "kind": "damage",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "actor_guid": 30001,
                    "timestamp_ms": 2200,
                    "spell_id": 2912,
                    "spell_name": "Starfire",
                    "originated_amount": 0,
                },
                {
                    "kind": "heal",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "actor_guid": 30001,
                    "timestamp_ms": 2300,
                    "spell_id": 2912,
                    "spell_name": "Starfire",
                    "originated_amount": 999,
                },
            ],
        },
    )
    manifest_path = tmp_path / "wcl_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema": "magmaw_wcl_cast_timelines_v1",
            "reference_id": "wcl-test",
            "duration_sec": 5.0,
            "actors": [
                {
                    "actor_id": "wcl-balance",
                    "class_spec": "balance_druid",
                    "source_name": "WCL Balance",
                    "casts": [
                        {"t": 0.1, "ability": "Starfire"},
                        {"t": 1.1, "ability": "Starfire"},
                        {"t": 2.1, "ability": "Wrath"},
                    ],
                },
                {
                    "actor_id": "wcl-fire",
                    "class_spec": "fire_mage",
                    "source_name": "WCL Fire",
                    "casts": [{"t": 0.2, "ability": "Fireball"}],
                },
                {
                    "actor_id": "wcl-blood",
                    "class_spec": "blood_death_knight",
                    "source_name": "WCL Blood",
                    "casts": [{"t": 0.4, "ability": "Icy Touch"}],
                },
            ],
        },
    )

    result = compare_timelines(run_dir, manifest_path)
    actors = {row["bot_guid"]: row for row in result["actors"]}

    assert result["scope"] == {
        "route_node_id": "bwd.magmaw.encounter",
        "actor_roles": ["dps", "healer", "tank"],
        "actor_count": 6,
        "comparable_actor_count": 4,
        "missing_wcl_reference_actor_count": 2,
    }
    assert actors[30001]["comparison_status"] == "comparable"
    assert actors[30001]["bot"]["landed_damage_events"] == 3
    assert actors[30001]["bot"]["direct_or_unknown_cadence"]["event_count"] == 2
    assert actors[30001]["bot_common_window_damage"] == 2100
    assert actors[30001]["bot_common_window_dps"] == 420.0
    assert actors[30001]["bot_native_encounter_window_dps"] == 1000
    assert actors[30001]["wcl_only_abilities"] == [
        {
            "ability": "Wrath",
            "wcl_completed_casts": 1,
        }
    ]
    assert actors[30001]["reference_reuse_index"] == 1
    assert actors[30007]["reference_reused_for_duplicate_local_actor"] is True
    assert actors[30009]["comparison_status"] == "missing_wcl_reference"
    assert actors[30003]["comparison_status"] == "missing_wcl_reference"
    assert result["signal_contract"]["primary_signal"] == (
        "per_actor_wcl_cast_cadence_vs_bot_landed_event_cadence"
    )
    assert result["signal_contract"]["dps_metric"] == "bot_common_window_dps"


def _comparison_fixture(
    tmp_path: Path, *, bot_duration: float = 10.0, wcl_duration: float = 20.0,
    wcl_damage_events: list[dict] | None = None,
) -> tuple[Path, Path]:
    run = tmp_path / "run"
    run.mkdir()
    _write_json(run / "report.json", {})
    _write_json(run / "combat_analysis.json", {
        "encounters": [{
            "route_node_id": "bwd.magmaw.encounter", "first_at_ms": 1000,
            "duration_sec": bot_duration,
            "actors": [{"actor_guid": 1, "actor_class_id": 3, "actor_role": "dps"}],
        }],
    })
    # Continuous pet attacks and owner periodic ticks must not close the
    # owner's 8-second gap between non-periodic landed effects.
    events = [
        {"t": 1, "spell_id": 8921, "spell_name": "Moonfire", "effect_type": 1},
        {"t": 9, "spell_id": 8921, "spell_name": "Moonfire", "is_periodic": False},
        {"t": 3, "spell_id": 8921, "spell_name": "Moonfire", "effect_type": 2},
        {"t": 5, "spell_id": 8921, "spell_name": "Moonfire", "is_periodic": True},
        *[{"t": t, "spell_id": 0, "spell_name": "Melee", "effect_type": 0,
           "source_is_pet": True} for t in (2, 4, 6, 8)],
    ]
    _write_json(run / "combat_log.json", {"recent_events": [
        {**event, "kind": "damage", "route_node_id": "bwd.magmaw.encounter",
         "target_entry": 41570, "actor_guid": 1,
         "timestamp_ms": 1000 + event["t"] * 1000, "originated_amount": 100}
        for event in events
    ]})
    actor = {"actor_id": "hunter", "class_spec": "survival_hunter",
             "observed_dps": 1000, "casts": [
                 {"t": 1, "ability": "Moonfire"}, {"t": 15, "ability": "Moonfire"},
             ]}
    if wcl_damage_events is not None:
        actor["damage_events"] = wcl_damage_events
    manifest = tmp_path / "wcl.json"
    _write_json(manifest, {"duration_sec": wcl_duration, "actors": [actor]})
    return run, manifest


def test_owner_effect_gaps_exclude_pets_and_ticks_but_damage_includes_both(tmp_path):
    result = compare_timelines(*_comparison_fixture(tmp_path))
    actor = result["actors"][0]
    bot = actor["bot"]
    assert actor["bot_common_window_damage"] == 800
    assert bot["landed_damage_events"] == 8
    assert bot["cadence"]["max_gap_sec"] == 2
    assert bot["direct_or_unknown_cadence"]["event_count"] == 2
    assert bot["owner_direct_cadence"]["event_count"] == 2
    assert bot["owner_unknown_cadence"]["event_count"] == 0
    assert bot["largest_gaps"][0] == {
        "gap_sec": 8, "from_t": 1, "to_t": 9,
        "from_ability": "Moonfire", "to_ability": "Moonfire",
        "basis": "owner_direct_or_unknown_landed_damage_not_casts",
    }
    moonfire = next(row for row in bot["ability_summary"] if row["ability"] == "Moonfire")
    assert moonfire["damage_classification_counts"] == {"direct": 2, "periodic": 2}


@pytest.mark.parametrize(("metadata", "expected"), [
    ({"spell_id": 8921}, "unknown"),
    ({"spell_id": 2912}, "unknown"),
    ({"spell_id": 8921, "effect_type": 1}, "direct"),
    ({"effect_type": 0}, "direct"),
    ({"effect_type": 2}, "periodic"),
    ({"effect_type": 5}, "unknown"),
    ({"effect_type": "DOT"}, "periodic"),
    ({"is_periodic": False}, "direct"),
    ({"periodic": True}, "periodic"),
    ({"is_periodic": "false"}, "unknown"),
    ({"effect_type": 1, "is_periodic": True}, "unknown"),
])
def test_effect_classification_uses_metadata_and_marks_unknown(metadata, expected):
    assert _damage_classification(metadata) == expected


def test_unknown_effects_are_labeled_in_owner_gap_summary(tmp_path):
    run, manifest = _comparison_fixture(tmp_path)
    log = json.loads((run / "combat_log.json").read_text())
    for event in log["recent_events"]:
        event.pop("effect_type", None)
        event.pop("is_periodic", None)
    _write_json(run / "combat_log.json", log)
    bot = compare_timelines(run, manifest)["actors"][0]["bot"]
    assert bot["owner_unknown_cadence"]["event_count"] == 4
    assert bot["owner_direct_cadence"]["event_count"] == 0
    assert bot["damage_classification_counts"] == {"unknown": 8}
    assert bot["gap_basis"] == "owner_direct_or_unknown_landed_damage_not_casts"


@pytest.mark.parametrize(("bot_duration", "wcl_duration", "status"), [
    (10, 20, "unmatched_windows_without_wcl_damage_timestamps"),
    (20, 10, "unavailable_wcl_damage_timestamps"),
    (10, 10, "unavailable_wcl_damage_timestamps"),
])
def test_whole_fight_wcl_dps_never_becomes_common_window_dps(
    tmp_path, bot_duration, wcl_duration, status,
):
    result = compare_timelines(*_comparison_fixture(
        tmp_path, bot_duration=bot_duration, wcl_duration=wcl_duration,
    ))
    actor = result["actors"][0]
    assert actor["wcl_observed_dps"] == 1000
    assert actor["wcl_observed_dps_basis"] == "whole_wcl_fight_context_only"
    assert actor["wcl_observed_dps_window_sec"] == wcl_duration
    assert actor["wcl_common_window_dps"] is None
    assert actor["wcl_common_window_damage"] is None
    assert actor["dps_comparison_status"] == status
    assert actor["wcl"]["completed_casts"] == 1
    assert result["comparison_window"]["common_window_sec"] == 10


def test_timestamped_wcl_damage_is_clipped_before_computing_common_window_dps(tmp_path):
    actor = compare_timelines(*_comparison_fixture(tmp_path, wcl_damage_events=[
        {"t": -1, "amount": 10000}, {"t": 0, "amount": 50},
        {"t": 1, "amount": 100}, {"t": 10, "amount": 150},
        {"t": 11, "amount": 10000},
    ]))["actors"][0]
    assert actor["wcl_common_window_damage"] == 300
    assert actor["wcl_common_window_dps"] == 30
    assert actor["bot_common_window_dps"] == 80
    assert actor["dps_comparison_status"] == "timestamped_common_window"


@pytest.mark.parametrize("events", [[{"amount": 100}], [{"t": 1}], [{"t": 1, "amount": -1}]])
def test_incomplete_wcl_damage_export_cannot_produce_comparison_dps(tmp_path, events):
    actor = compare_timelines(*_comparison_fixture(
        tmp_path, wcl_damage_events=events,
    ))["actors"][0]
    assert actor["wcl_common_window_dps"] is None
    assert actor["dps_comparison_status"] != "timestamped_common_window"


def test_ability_counts_stay_side_by_side_without_delta_ranking():
    rows = _ability_diffs(
        {"ability_summary": [{"ability": "A", "cast_count": 2},
                             {"ability": "Z", "cast_count": 1}]},
        {"ability_summary": [{"ability": "A", "landed_damage_events": 2},
                             {"ability": "Z", "landed_damage_events": 1000}]},
    )
    assert [row["ability"] for row in rows] == ["A", "Z"]
    assert rows[1]["wcl_completed_casts"] == 1
    assert rows[1]["bot_landed_damage_events"] == 1000
    for row in rows:
        assert "delta_landed_events_minus_casts" not in row
        assert "event_to_cast_ratio" not in row


def test_cli_distinguishes_cast_reference_from_timestamped_dps_pair(
    tmp_path, monkeypatch, capsys,
):
    run, manifest = _comparison_fixture(tmp_path)
    output = tmp_path / "comparison.json"
    monkeypatch.setattr("sys.argv", [
        "compare_magmaw_timelines", "--bot-run", str(run),
        "--wcl-manifest", str(manifest), "--output", str(output),
    ])
    assert main() == 0
    assert "comparable=1 timestamped_dps_pairs=0" in capsys.readouterr().out
    actor = json.loads(output.read_text())["actors"][0]
    assert actor["wcl_common_window_dps"] is None


@pytest.mark.parametrize("combat_log", [{}, {"recent_events": None}])
def test_missing_raw_event_input_fails_instead_of_reporting_zero_damage(tmp_path, combat_log):
    run, manifest = _comparison_fixture(tmp_path)
    _write_json(run / "combat_log.json", combat_log)
    _write_json(run / "report.json", {
        "combat_log": {},
        "combat_log_summary": {"event_count": 7856, "recent_events_dropped": 0},
    })
    with pytest.raises(ValueError, match="requires a recent_events array"):
        compare_timelines(run, manifest)


@pytest.mark.parametrize(("metadata", "reason"), [
    ({"recent_events_dropped": 2}, "recent_events_dropped"),
    ({"event_count": 12, "recent_events_dropped": 0}, "event_count_differs_from_retained_length"),
    ({"event_count": 7}, "event_count_differs_from_retained_length"),
    ({"event_count_at_export": 12}, "event_count_at_export_differs_from_retained_length"),
])
def test_known_truncation_keeps_retained_effects_but_withholds_native_dps(tmp_path, metadata, reason):
    run, manifest = _comparison_fixture(tmp_path, wcl_damage_events=[{"t": 1, "amount": 100}])
    combat_log = json.loads((run / "combat_log.json").read_text())
    _write_json(run / "combat_log.json", {**combat_log, **metadata})
    result = compare_timelines(run, manifest)
    actor = result["actors"][0]
    assert result["bot_event_input"]["status"] == "incomplete"
    assert reason in result["bot_event_input"]["reasons"]
    assert result["bot_event_input"]["retained_event_count"] == 8
    assert actor["bot"]["landed_damage"] == 800
    assert actor["bot"]["landed_damage_events"] == 8
    assert actor["bot"]["event_input_status"] == "incomplete"
    assert actor["bot_retained_common_window_damage"] == 800
    assert actor["bot_common_window_damage"] is None
    assert actor["bot_common_window_dps"] is None
    assert actor["bot_common_window_dps_basis"] == "unavailable_incomplete_native_event_input"
    assert actor["bot_event_input_status"] == "incomplete"
    assert actor["wcl_common_window_dps"] == 10
    assert actor["dps_comparison_status"] == "incomplete_native_event_input"


def test_matching_retained_event_count_keeps_native_dps_available(tmp_path):
    run, manifest = _comparison_fixture(tmp_path)
    combat_log = json.loads((run / "combat_log.json").read_text())
    _write_json(run / "combat_log.json", {
        **combat_log, "event_count": 8, "recent_events_dropped": 0,
    })
    result = compare_timelines(run, manifest)
    assert result["bot_event_input"]["status"] == "no_known_truncation"
    assert result["actors"][0]["bot_common_window_dps"] == 80
