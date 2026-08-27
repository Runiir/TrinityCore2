import base64
import json

from tools.bot_ml.analyze_combat_log import analyze_combat_log
from tools.bot_ml.run_live_bot_validation import (
    heartbeat_commands_from_script,
    live_validation_report,
    parse_json_objects,
    strip_calibration_status_chunks,
    strip_combat_log_chunks,
)


def combat_log_fixture() -> dict:
    return {
        "action": "botauto_combatlog",
        "combat_log_schema_version": 1,
        "event_count": 42,
        "aggregate_count": 3,
        "second_bucket_count": 2,
        "recent_events_dropped": 7,
        "abilities": [
            {
                "route_generation": 2,
                "route_node_id": "corborus",
                "route_label": "Corborus",
                "perspective": "damage_done",
                "actor_guid": 10,
                "actor_name": "Firemake",
                "actor_role": "dps",
                "actor_class_id": 8,
                "source_entry": 0,
                "source_name": "Firemake",
                "source_is_pet": False,
                "spell_id": 133,
                "spell_name": "Fireball",
                "target_entry": 43438,
                "target_name": "Corborus",
                "first_at_ms": 1000,
                "last_at_ms": 11000,
                "event_count": 30,
                "amount": 9000,
                "moving_events": 0,
                "moving_fraction": 0,
                "distance_avg": 4,
            },
            {
                "route_generation": 2,
                "route_node_id": "corborus",
                "route_label": "Corborus",
                "perspective": "damage_done",
                "actor_guid": 10,
                "actor_name": "Firemake",
                "actor_role": "dps",
                "actor_class_id": 8,
                "source_entry": 0,
                "source_name": "Firemake",
                "source_is_pet": False,
                "spell_id": 44457,
                "spell_name": "Living Bomb",
                "target_entry": 43438,
                "target_name": "Corborus",
                "first_at_ms": 2000,
                "last_at_ms": 10000,
                "event_count": 5,
                "amount": 1000,
                "moving_events": 2,
                "moving_fraction": 0.4,
                "distance_avg": 4,
            },
            {
                "route_generation": 2,
                "route_node_id": "corborus",
                "route_label": "Corborus",
                "perspective": "damage_taken",
                "actor_guid": 10,
                "actor_name": "Firemake",
                "actor_role": "dps",
                "actor_class_id": 8,
                "source_entry": 43438,
                "source_name": "Corborus",
                "source_is_pet": False,
                "spell_id": 80803,
                "spell_name": "Lava Fissure",
                "target_entry": 0,
                "target_name": "Firemake",
                "first_at_ms": 5000,
                "last_at_ms": 6000,
                "event_count": 2,
                "amount": 2500,
                "moving_events": 0,
                "moving_fraction": 0,
                "distance_avg": 0,
            },
        ],
        "second_buckets": [
            {"route_generation": 2, "perspective": "damage_done", "actor_guid": 10, "source_is_pet": False, "second": 1, "amount": 5000},
            {"route_generation": 2, "perspective": "damage_done", "actor_guid": 10, "source_is_pet": False, "second": 10, "amount": 5000},
            *[
                {"route_generation": 2, "perspective": "damage_done", "actor_guid": 20, "source_is_pet": False, "second": second, "amount": 1}
                for second in range(2, 10)
            ],
        ],
        "recent_events": [{"kind": "damage"}],
    }


def test_analyze_combat_log_reports_dps_rotation_and_positioning():
    report = analyze_combat_log(combat_log_fixture())

    assert report["schema"] == "bot_combat_analysis_v2"
    assert report["tracked_event_count"] == 42
    assert report["recent_events_dropped"] == 7
    encounter = report["encounters"][0]
    assert encounter["route_node_id"] == "corborus"
    assert encounter["party_damage"] == 10000
    assert encounter["party_dps"] == 1000
    assert encounter["party_healing"] == 0
    assert encounter["party_hps"] == 0
    assert encounter["elapsed_party_hps"] == 0
    actor = encounter["actors"][0]
    assert actor["dps"] == 1000
    assert actor["elapsed_dps"] == 1000
    assert actor["active_dps"] == 5000
    assert actor["damage_uptime"] == 0.2
    assert actor["abilities"][0]["spell_name"] == "Fireball"
    assert actor["abilities"][0]["damage_share"] == 0.9
    assert {row["kind"] for row in report["diagnostics"]} >= {
        "rotation_low_variety",
        "single_ability_damage_dominance",
        "low_damage_uptime",
        "ranged_damage_too_close",
        "known_avoidable_damage_taken",
    }


def test_live_validation_attaches_combat_analysis_and_logs_only_at_cleanup():
    combat_log = combat_log_fixture()
    output = "\n".join(
        [
            '{"action":"botauto_status","active_bots":1,"target_bots":1}',
            '{"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":10}}]}',
            '{"trace_schema_version":1,"entries":[{"action":"move"}]}',
            json.dumps(combat_log),
        ]
    )
    report = live_validation_report(output)

    assert report["combat_log"]["event_count"] == 42
    assert report["combat_analysis"]["encounters"][0]["party_dps"] == 1000
    startup, heartbeat, cleanup = heartbeat_commands_from_script(
        ".botauto start\n.botauto status\n.botauto combatlog\n.botauto stop\n"
    )
    assert startup == [".botauto start"]
    assert heartbeat == [".botauto status"]
    assert cleanup == [".botauto combatlog", ".botauto stop"]


def test_live_validation_reassembles_bounded_combat_log_chunks():
    raw = json.dumps(combat_log_fixture(), separators=(",", ":")).encode()
    chunk_size = 97
    parts = [raw[index : index + chunk_size] for index in range(0, len(raw), chunk_size)]
    chunk_rows = [
        json.dumps(
            {
                "action": "botauto_combatlog_chunk",
                "combat_log_chunk_schema_version": 1,
                "sequence": sequence,
                "chunk_count": len(parts),
                "encoding": "base64",
                "data": base64.b64encode(part).decode(),
            }
        )
        for sequence, part in enumerate(parts)
    ]
    chunk_rows.append(json.dumps({
        "ok": True,
        "action": "botauto_combatlog_complete",
        "combat_log_chunk_schema_version": 1,
        "chunk_count": len(parts),
        "total_bytes": len(raw),
    }))
    output = "\n".join(chunk_rows)

    report = live_validation_report(output)

    assert report["combat_log"]["event_count"] == 42
    assert report["combat_analysis"]["encounters"][0]["party_damage"] == 10000
    assert report["combat_log_transport"]["complete_marker"] is True
    assert report["combat_log_transport"]["reassembled"] is True
    stripped = strip_combat_log_chunks("prefix\n" + output + "\nsuffix\n")
    assert "botauto_combatlog_chunk" not in stripped
    assert stripped == "prefix\nsuffix\n"


def test_live_validation_reassembles_bounded_calibration_status_chunks():
    status = {
        "ok": True,
        "action": "botauto_calibrate_status",
        "cohort_id": "phase8-affliction",
        "active": True,
        "phase": "complete",
        "window_complete": True,
        "bots": [{"name": "Affliction", "damage": 5_382_659, "dps": 17_942.2}],
    }
    raw = json.dumps(status, separators=(",", ":")).encode()
    parts = [raw[index : index + 31] for index in range(0, len(raw), 31)]
    rows = [
        {
            "ok": True,
            "action": "botauto_calibrate_status_chunk",
            "cohort_id": "phase8-affliction",
            "calibration_status_chunk_schema_version": 1,
            "sequence": sequence,
            "chunk_count": len(parts),
            "encoding": "base64",
            "data": base64.b64encode(part).decode(),
        }
        for sequence, part in enumerate(parts)
    ]
    rows.append(
        {
            "ok": True,
            "action": "botauto_calibrate_status_complete",
            "cohort_id": "phase8-affliction",
            "calibration_status_chunk_schema_version": 1,
            "chunk_count": len(parts),
            "total_bytes": len(raw),
            "payload_ok": True,
        }
    )
    output = "\n".join(json.dumps(row) for row in rows)

    report = live_validation_report(output)

    assert report["combat_calibration"]["window_complete"] is True
    assert report["combat_calibration"]["bots"][0]["damage"] == 5_382_659
    assert report["combat_calibration_transport"] == {
        "direct": False,
        "complete_marker": True,
        "expected_chunks": len(parts),
        "received_chunks": len(parts),
        "total_bytes": len(raw),
        "reassembled": True,
    }
    stripped = strip_calibration_status_chunks("prefix\n" + output + "\nsuffix\n")
    assert "botauto_calibrate_status_chunk" not in stripped
    assert "botauto_calibrate_status_complete" not in stripped
    assert stripped == "prefix\nsuffix\n"

    rows[-1]["total_bytes"] = len(raw) + 1
    corrupt = live_validation_report("\n".join(json.dumps(row) for row in rows))
    assert corrupt["combat_calibration"] == {}
    assert corrupt["combat_calibration_transport"]["reassembled"] is False


def test_live_validation_ignores_nested_action_objects_but_keeps_combatlog_rows():
    nested_payload = json.dumps([{"action": {"nested": "not-a-telemetry-action"}}])
    direct_output = "\n".join([nested_payload, json.dumps(combat_log_fixture())])

    assert parse_json_objects(direct_output) == [combat_log_fixture()]
    direct_report = live_validation_report(direct_output)

    assert direct_report["combat_log"]["event_count"] == 42

    raw = json.dumps(combat_log_fixture(), separators=(",", ":")).encode()
    chunk_size = 113
    parts = [raw[index : index + chunk_size] for index in range(0, len(raw), chunk_size)]
    chunk_rows = [
        {
            "action": "botauto_combatlog_chunk",
            "combat_log_chunk_schema_version": 1,
            "sequence": sequence,
            "chunk_count": len(parts),
            "encoding": "base64",
            "data": base64.b64encode(part).decode(),
        }
        for sequence, part in enumerate(parts)
    ]
    chunk_rows.append(
        {
            "action": "botauto_combatlog_complete",
            "combat_log_chunk_schema_version": 1,
            "chunk_count": len(parts),
            "total_bytes": len(raw),
        }
    )
    chunk_output = "\n".join([nested_payload, *(json.dumps(row) for row in chunk_rows)])

    chunk_report = live_validation_report(chunk_output)

    assert chunk_report["combat_log"]["event_count"] == 42
    assert chunk_report["combat_log_transport"]["reassembled"] is True
