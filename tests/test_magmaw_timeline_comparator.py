from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml.compare_magmaw_timelines import (
    compare_timelines,
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
    assert actors[30001]["reference_reuse_index"] == 1
    assert actors[30007]["reference_reused_for_duplicate_local_actor"] is True
    assert actors[30009]["comparison_status"] == "missing_wcl_reference"
    assert actors[30003]["comparison_status"] == "missing_wcl_reference"
    assert result["signal_contract"]["primary_signal"] == (
        "per_actor_wcl_cast_cadence_vs_bot_landed_event_cadence"
    )
