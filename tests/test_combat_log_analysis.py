import base64
from copy import deepcopy
import json

import pytest

from tools.bot_ml.analyze_combat_log import analyze_combat_log
from tools.bot_ml.combat_log_event_stream import CombatLogEventStream
from tools.bot_ml.run_live_bot_validation import (
    combined_combat_log,
    combat_log_transport_status,
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


def _combat_delta_frames(
    sequences: list[int], *, cursor_before: int, cursor_after: int,
    event_count: int, run_id: int = 1, combat_log_epoch: int = 1,
    server_epoch: int = 88, attempt_id: int = 4,
    profile_generation: int | None = 2,
    profile_content_hash: str | None = "profile-hash",
    chunk_size: int = 13,
) -> list[dict]:
    payload = {
        "ok": True,
        "action": "botauto_combatlog_delta",
        "combat_log_schema_version": 3,
        "cohort_id": "raid",
        "server_epoch": server_epoch,
        "attempt_id": attempt_id,
        "combat_log_epoch": combat_log_epoch,
        "profile_generation": profile_generation,
        "profile_content_hash": profile_content_hash,
        "experiment_id": 7,
        "run_id": run_id,
        "event_count_at_export": event_count,
        "cursor_before": cursor_before,
        "cursor_after": cursor_after,
        "gap": False,
        "recent_events": [
            {"event_sequence": sequence, "kind": "damage", "amount": sequence}
            for sequence in sequences
        ],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    parts = [raw[index : index + chunk_size] for index in range(0, len(raw), chunk_size)]
    return [
        {
            "ok": True,
            "action": "botauto_combatlog_chunk",
            "cohort_id": "raid",
            "combat_log_chunk_schema_version": 1,
            "sequence": index,
            "chunk_count": len(parts),
            "encoding": "base64",
            "data": base64.b64encode(part).decode(),
        }
        for index, part in enumerate(parts)
    ] + [{
        "ok": True,
        "action": "botauto_combatlog_complete",
        "cohort_id": "raid",
        "combat_log_chunk_schema_version": 1,
        "chunk_count": len(parts),
        "total_bytes": len(raw),
    }]


def test_analyze_combat_log_reports_dps_rotation_and_positioning():
    report = analyze_combat_log(combat_log_fixture())

    assert report["schema"] == "bot_combat_analysis_v3"
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


def test_shared_damage_copies_are_raw_but_not_originated_dps():
    abilities = []
    for index, originated_amount in enumerate((100, 0, 0)):
        abilities.append(
            {
                "route_generation": 4,
                "route_node_id": "magmaw",
                "route_label": "Magmaw",
                "perspective": "damage_done",
                "actor_guid": 10,
                "actor_name": "Felmake",
                "actor_role": "dps",
                "actor_class_id": 9,
                "source_entry": 416,
                "source_name": "Felhunter",
                "source_is_pet": True,
                "spell_id": 12345,
                "spell_name": "Shadow Bite",
                "target_entry": 41570,
                "target_name": "Magmaw",
                "first_at_ms": 1000,
                "last_at_ms": 1000,
                "event_count": 1,
                "amount": 100,
                "originated_amount": originated_amount,
                "shared_damage": index > 0,
            }
        )
    abilities.append(
        {
            "route_generation": 4,
            "route_node_id": "magmaw",
            "route_label": "Magmaw",
            "perspective": "healing_done",
            "actor_guid": 10,
            "actor_name": "Felmake",
            "actor_role": "dps",
            "actor_class_id": 9,
            "source_entry": 10,
            "source_name": "Felmake",
            "source_is_pet": False,
            "spell_id": 999,
            "spell_name": "A Test Heal",
            "target_entry": 10,
            "target_name": "Felmake",
            "first_at_ms": 1000,
            "last_at_ms": 1000,
            "event_count": 1,
            "amount": 50,
            "originated_amount": 50,
        }
    )
    report = analyze_combat_log(
        {
            "combat_log_schema_version": 2,
            "event_count": 4,
            "abilities": abilities,
            "second_buckets": [
                {
                    "route_generation": 4,
                    "perspective": "damage_done",
                    "actor_guid": 10,
                    "source_is_pet": True,
                    "second": 1,
                    "amount": 300,
                    "originated_amount": 100,
                },
                {
                    "route_generation": 4,
                    "perspective": "healing_done",
                    "actor_guid": 10,
                    "source_is_pet": False,
                    "second": 1,
                    "amount": 50,
                    "originated_amount": 50,
                },
            ],
        }
    )

    encounter = report["encounters"][0]
    assert encounter["party_damage"] == 100
    assert encounter["party_dps"] == 100
    assert encounter["raw_event_damage"] == 300
    assert encounter["raw_event_dps"] == 300
    assert encounter["party_healing"] == 50
    assert encounter["party_hps"] == 50
    actor = encounter["actors"][0]
    assert actor["damage"] == 100
    assert actor["raw_event_damage"] == 300
    assert actor["dps"] == 100
    assert actor["raw_event_dps"] == 300
    assert actor["pet_damage"] == 100
    assert actor["raw_event_pet_damage"] == 300
    assert actor["pet_damage_share"] == 1.0
    assert actor["raw_event_pet_damage_share"] == 1.0
    assert actor["abilities"][0]["damage"] == 100
    assert actor["abilities"][0]["raw_event_damage"] == 300
    assert actor["abilities"][0]["originated_damage"] == 100


def test_schema3_splits_hostile_and_friendly_damage_without_losing_raw_callbacks():
    def row(
        perspective,
        amount,
        originated,
        *,
        spell_id,
        spell_name,
        source_is_pet=False,
        target_entry=41570,
    ):
        return {
            "route_generation": 5,
            "route_node_id": "magmaw",
            "route_label": "Magmaw",
            "perspective": perspective,
            "actor_guid": 10,
            "actor_name": "Felmake",
            "actor_role": "dps",
            "actor_class_id": 9,
            "source_entry": 416,
            "source_name": "Felhunter" if source_is_pet else "Felmake",
            "source_is_pet": source_is_pet,
            "spell_id": spell_id,
            "spell_name": spell_name,
            "target_entry": target_entry,
            "target_name": "Magmaw" if target_entry else "Felmake",
            "first_at_ms": 1000,
            "last_at_ms": 1000,
            "event_count": 1,
            "amount": amount,
            "originated_amount": originated,
            "shared_amount": amount - originated,
            "raw_amount": amount,
            "moving_events": 0,
            "distance_avg": 4,
        }

    abilities = [
        row("damage_done", 1000, 1000, spell_id=1, spell_name="Hostile Bolt"),
        row("damage_done", 200, 0, spell_id=2, spell_name="Shared Copy"),
        row("friendly_damage_done", 300, 300, spell_id=3, spell_name="Friendly Fire"),
        row(
            "friendly_damage_done", 400, 400, spell_id=0, spell_name="Melee",
            source_is_pet=True, target_entry=28017,
        ),
        row(
            "damage_taken", 700, 700, spell_id=4, spell_name="Cohort Hit",
            target_entry=0,
        ),
    ]
    report = analyze_combat_log({
        "combat_log_schema_version": 3,
        "damage_attribution_schema": "originated_amount_v2_friendly_split",
        "event_count": 5,
        "abilities": abilities,
        "second_buckets": [
            {
                "route_generation": 5, "perspective": "damage_done",
                "actor_guid": 10, "source_is_pet": False, "second": 1,
                "amount": 1200, "originated_amount": 1000,
            },
            {
                "route_generation": 5, "perspective": "friendly_damage_done",
                "actor_guid": 10, "source_is_pet": False, "second": 2,
                "amount": 300, "originated_amount": 300,
            },
            {
                "route_generation": 5, "perspective": "friendly_damage_done",
                "actor_guid": 10, "source_is_pet": True, "second": 3,
                "amount": 400, "originated_amount": 400,
            },
        ],
    })

    encounter = report["encounters"][0]
    assert encounter["party_damage"] == 1000
    assert encounter["party_friendly_damage"] == 700
    assert encounter["party_raw_event_friendly_damage"] == 700
    assert encounter["raw_event_damage"] == 1900
    assert encounter["raw_event_dps"] == round(1900 / 3, 3)
    actor = encounter["actors"][0]
    assert actor["damage"] == 1000
    assert actor["friendly_damage"] == 700
    assert actor["raw_event_friendly_damage"] == 700
    assert actor["raw_event_damage"] == 1900
    assert actor["damage_taken"] == 700
    assert actor["pet_damage"] == 0
    assert actor["raw_event_pet_damage"] == 400
    assert sum(row["damage_share"] for row in actor["abilities"]) == 1.0
    assert {row["spell_name"] for row in actor["friendly_abilities"]} == {
        "Friendly Fire", "Melee",
    }
    assert {
        (row["spell_name"], row["target_entry"])
        for row in actor["friendly_abilities"]
    } == {("Friendly Fire", 41570), ("Melee", 28017)}


def test_legacy_schema_does_not_invent_friendly_split():
    report = analyze_combat_log({
        "combat_log_schema_version": 2,
        "abilities": [{
            "route_generation": 1,
            "perspective": "damage_done",
            "actor_guid": 10,
            "amount": 300,
            "originated_amount": 300,
            "event_count": 1,
        }],
        "second_buckets": [{
            "route_generation": 1,
            "perspective": "damage_done",
            "actor_guid": 10,
            "source_is_pet": False,
            "second": 1,
            "amount": 300,
            "originated_amount": 300,
        }],
    })
    encounter = report["encounters"][0]
    assert encounter["party_damage"] == 300
    assert encounter["party_friendly_damage"] == 0
    assert encounter["raw_event_damage"] == 300


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


def test_combined_combat_log_reassembles_schema3_friendly_perspective():
    payload = {
        "action": "botauto_combatlog",
        "combat_log_schema_version": 3,
        "damage_attribution_schema": "originated_amount_v2_friendly_split",
        "event_count": 0,
        "recent_events_dropped": 0,
        "abilities": [{
            "perspective": "friendly_damage_done",
            "actor_guid": 10,
            "amount": 400,
            "originated_amount": 400,
        }],
        "recent_events": [],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    parts = [raw[index : index + 11] for index in range(0, len(raw), 11)]
    chunk_rows = [
        {
            "action": "botauto_combatlog_chunk",
            "ok": True,
            "cohort_id": "subject",
            "combat_log_chunk_schema_version": 1,
            "sequence": sequence,
            "chunk_count": len(parts),
            "encoding": "base64",
            "data": base64.b64encode(part).decode(),
        }
        for sequence, part in enumerate(parts)
    ]
    chunk_rows.append({
        "action": "botauto_combatlog_complete",
        "ok": True,
        "cohort_id": "subject",
        "combat_log_chunk_schema_version": 1,
        "chunk_count": len(parts),
        "total_bytes": len(raw),
    })

    combined = combined_combat_log(chunk_rows)

    assert combined["combat_log_schema_version"] == 3
    assert combined["damage_attribution_schema"] == "originated_amount_v2_friendly_split"
    assert combined["abilities"][0]["perspective"] == "friendly_damage_done"


def test_combat_event_stream_merges_overlap_replay_and_reports_gap():
    stream = CombatLogEventStream(expected_cohort_id="raid")
    status_identity = {
        "cohort_id": "raid",
        "server_epoch": 88,
        "attempt_id": 4,
        "profile_generation": 2,
        "profile_content_hash": "profile-hash",
    }
    stream.bind_identity(status_identity)

    first = _combat_delta_frames(
        [1, 2, 3], cursor_before=0, cursor_after=3, event_count=5,
        run_id=48,
    )
    second = _combat_delta_frames(
        [3, 4, 5], cursor_before=3, cursor_after=5, event_count=5,
        run_id=49,
    )
    missing = _combat_delta_frames(
        [7, 8], cursor_before=5, cursor_after=8, event_count=8,
        run_id=49,
    )
    assert stream.observe_rows(first)[0].accepted is True
    assert stream.observe_rows(second)[0].accepted is True
    assert stream.observe_rows(second)[0].accepted is True
    assert stream.observe_rows(missing)[0].accepted is True

    receipt = stream.receipt()
    assert [row["event_sequence"] for row in stream.events()] == [1, 2, 3, 4, 5, 7, 8]
    assert receipt["namespace"]["duplicate_count"] == 4
    assert receipt["namespace"]["gap_ranges"] == [{"start": 6, "end": 6}]
    assert {row["run_id"] for row in receipt["namespace"]["labels"]} == {48, 49}
    assert receipt["complete"] is False

    conflict = _combat_delta_frames(
        [3, 4, 5], cursor_before=3, cursor_after=5, event_count=8,
        run_id=49,
    )
    # Rebuild the decoded event with a changed sequence-3 row and assert the
    # response is rejected without replacing the accepted copy.
    changed = json.loads(
        b"".join(
            base64.b64decode(row["data"], validate=True)
            for row in conflict[:-1]
        )
    )
    changed["recent_events"][0]["amount"] = 999
    changed_raw = json.dumps(changed, separators=(",", ":")).encode()
    changed_parts = [
        changed_raw[index : index + 13]
        for index in range(0, len(changed_raw), 13)
    ]
    changed_rows = [
        {
            "ok": True,
            "action": "botauto_combatlog_chunk",
            "cohort_id": "raid",
            "combat_log_chunk_schema_version": 1,
            "sequence": index,
            "chunk_count": len(changed_parts),
            "encoding": "base64",
            "data": base64.b64encode(part).decode(),
        }
        for index, part in enumerate(changed_parts)
    ] + [{
        "ok": True,
        "action": "botauto_combatlog_complete",
        "cohort_id": "raid",
        "combat_log_chunk_schema_version": 1,
        "chunk_count": len(changed_parts),
        "total_bytes": len(changed_raw),
    }]
    assert stream.observe_rows(changed_rows)[0].accepted is False
    assert 3 in stream.receipt()["namespace"]["conflict_sequences"]
    assert stream.events()[2]["amount"] == 3


def test_combat_event_stream_rejects_foreign_stable_identity_and_missing_profile():
    bound = {
        "cohort_id": "raid",
        "server_epoch": 88,
        "attempt_id": 4,
        "profile_generation": 2,
        "profile_content_hash": "profile-hash",
    }
    stream = CombatLogEventStream()
    stream.bind_identity(bound)
    foreign_server = _combat_delta_frames(
        [1], cursor_before=0, cursor_after=1, event_count=1,
        server_epoch=89,
    )
    foreign_attempt = _combat_delta_frames(
        [1], cursor_before=0, cursor_after=1, event_count=1,
        attempt_id=5,
    )
    missing_profile = _combat_delta_frames(
        [1], cursor_before=0, cursor_after=1, event_count=1,
        profile_generation=None, profile_content_hash=None,
    )
    assert stream.observe_rows(foreign_server)[0].accepted is False
    assert stream.observe_rows(foreign_attempt)[0].accepted is False
    assert stream.observe_rows(missing_profile)[0].accepted is False
    assert stream.receipt()["namespace"] is None
    assert "delta_stable_identity_conflict" in stream.receipt()["transport_rejections"]
    assert "delta_profile_context_conflict" in stream.receipt()["transport_rejections"]


def test_combined_combat_log_merges_delta_tail_without_touching_aggregates():
    deltas = [
        *_combat_delta_frames(
            [1, 2, 3], cursor_before=0, cursor_after=3, event_count=5,
            run_id=48,
        ),
        *_combat_delta_frames(
            [3, 4, 5], cursor_before=3, cursor_after=5, event_count=5,
            run_id=49,
        ),
    ]
    full = {
        "ok": True,
        "action": "botauto_combatlog",
        "combat_log_schema_version": 3,
        "cohort_id": "raid",
        "server_epoch": 88,
        "attempt_id": 4,
        "combat_log_epoch": 1,
        "profile_generation": 2,
        "profile_content_hash": "profile-hash",
        "experiment_id": 7,
        "run_id": 49,
        "event_count": 5,
        "aggregate_count": 1,
        "second_bucket_count": 1,
        "recent_events_dropped": 0,
        "abilities": [{"spell_id": 20473, "amount": 321}],
        "second_buckets": [{"second": 4, "amount": 321}],
        "recent_events": [
            {"event_sequence": 3, "kind": "damage", "amount": 3},
            {"event_sequence": 4, "kind": "damage", "amount": 4},
            {"event_sequence": 5, "kind": "damage", "amount": 5},
        ],
    }
    aggregate_snapshot = {
        key: deepcopy(full[key])
        for key in ("event_count", "aggregate_count", "second_bucket_count", "abilities", "second_buckets")
    }
    combined = combined_combat_log([*deltas, full])

    assert {
        key: combined[key]
        for key in aggregate_snapshot
    } == aggregate_snapshot
    assert [row["event_sequence"] for row in combined["recent_events"]] == [1, 2, 3, 4, 5]
    assert combined["event_stream_receipt"]["merged_with_full"] is True
    assert combined["event_stream_receipt"]["namespace"]["duplicate_count"] == 1


def test_combat_event_epoch_reset_uses_distinct_namespace():
    stream = CombatLogEventStream()
    stream.bind_identity({
        "cohort_id": "raid", "server_epoch": 88, "attempt_id": 4,
        "profile_generation": 2, "profile_content_hash": "profile-hash",
    })
    assert stream.observe_rows(_combat_delta_frames(
        [1, 2], cursor_before=0, cursor_after=2, event_count=2,
        combat_log_epoch=1,
    ))[0].accepted is True
    assert stream.observe_rows(_combat_delta_frames(
        [1], cursor_before=0, cursor_after=1, event_count=1,
        combat_log_epoch=2,
    ))[0].accepted is True
    assert stream.receipt()["namespace_count"] == 2
    assert [row["event_sequence"] for row in stream.events()] == [1]
    assert stream.receipt()["identity"]["combat_log_epoch"] == 2


def test_live_validation_reports_missing_combat_log_sequence_fail_closed():
    raw = json.dumps(combat_log_fixture(), separators=(",", ":")).encode()
    parts = [raw[index : index + 97] for index in range(0, len(raw), 97)]
    missing_sequence = 1
    rows = [
        {
            "action": "botauto_combatlog_chunk",
            "combat_log_chunk_schema_version": 1,
            "sequence": sequence,
            "chunk_count": len(parts),
            "encoding": "base64",
            "data": base64.b64encode(part).decode(),
        }
        for sequence, part in enumerate(parts)
        if sequence != missing_sequence
    ]
    rows.append(
        {
            "action": "botauto_combatlog_complete",
            "combat_log_chunk_schema_version": 1,
            "chunk_count": len(parts),
            "total_bytes": len(raw),
        }
    )
    output = "\n".join(json.dumps(row) for row in rows)

    status = combat_log_transport_status(parse_json_objects(output))
    report = live_validation_report(output)

    assert status["reassembled"] is False
    assert status["missing_sequences"] == [missing_sequence]
    assert status["reason"] == "missing_sequences"
    assert report["combat_log"] == {}
    assert report["combat_analysis"] == {}
    assert "combat_log_transport_incomplete" in report["failure_labels"]
    assert "failure_labels_present" in report["final_evidence_rejections"]


def test_live_validation_uses_latest_complete_combat_log_retry():
    raw = json.dumps(combat_log_fixture(), separators=(",", ":")).encode()
    parts = [raw[index : index + 97] for index in range(0, len(raw), 97)]

    def transfer(skip: int | None) -> list[dict]:
        rows = [
            {
                "action": "botauto_combatlog_chunk",
                "combat_log_chunk_schema_version": 1,
                "sequence": sequence,
                "chunk_count": len(parts),
                "encoding": "base64",
                "data": base64.b64encode(part).decode(),
            }
            for sequence, part in enumerate(parts)
            if sequence != skip
        ]
        rows.append(
            {
                "action": "botauto_combatlog_complete",
                "combat_log_chunk_schema_version": 1,
                "chunk_count": len(parts),
                "total_bytes": len(raw),
            }
        )
        return rows

    output = "\n".join(
        json.dumps(row) for row in [*transfer(1), *transfer(None)]
    )
    report = live_validation_report(output)

    assert report["combat_log_transport"]["attempt_count"] == 2
    assert report["combat_log_transport"]["reassembled"] is True
    assert report["combat_log"]["event_count"] == 42
    assert "combat_log_transport_incomplete" not in report["failure_labels"]


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
        "attempted": True,
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


def _framed_combat_payload(payload, export_id=1, kind="delta"):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    common = {"ok": True, "cohort_id": "raid", "export_id": export_id,
              "export_kind": kind, "combat_log_chunk_schema_version": 1, "chunk_count": 1}
    return [dict(common, action="botauto_combatlog_chunk", sequence=0,
                 encoding="base64", data=base64.b64encode(raw).decode()),
            dict(common, action="botauto_combatlog_complete", total_bytes=len(raw))]


def _decoded_delta(sequences, **kwargs):
    frames = _combat_delta_frames(sequences, **kwargs)
    return json.loads(b"".join(base64.b64decode(row["data"]) for row in frames[:-1]))


def test_combat_event_rejects_unframed_cursor_mismatch_and_internal_conflict():
    payload = _decoded_delta([1, 2, 3], cursor_before=0, cursor_after=5, event_count=5)
    stream = CombatLogEventStream()
    assert stream.observe(payload).accepted is False
    assert stream.cursor == 0
    stream = CombatLogEventStream()
    assert stream.observe_rows(_framed_combat_payload(payload))[0].accepted is False
    assert stream.cursor == 0
    assert stream.receipt()["complete"] is False
    payload["cursor_after"] = 3
    payload["recent_events"].append(dict(payload["recent_events"][0], amount=999))
    stream = CombatLogEventStream()
    assert stream.observe_rows(_framed_combat_payload(payload))[0].accepted is False
    assert stream.receipt()["conflict_sequences"] == [1]


def test_combat_event_final_full_count_and_abandoned_export_boundary():
    delta = _decoded_delta([1, 2, 3], cursor_before=0, cursor_after=3, event_count=3)
    full = dict(delta, action="botauto_combatlog", event_count=8,
                abilities=[{"amount": 123}], second_buckets=[], recent_events=[])
    combined = combined_combat_log([*_framed_combat_payload(delta), full])
    assert combined["event_count"] == 8
    assert combined["abilities"] == full["abilities"]
    assert combined["event_stream_receipt"]["complete"] is False
    assert combined["event_stream_receipt"]["final_missing_sequence_ranges"] == [{"start": 4, "end": 8}]
    partial = _framed_combat_payload(delta, 2)
    terminal = _framed_combat_payload(full, 3, "full")
    rows = [*_framed_combat_payload(delta), partial[0], terminal[0], *partial, terminal[1]]
    combined = combined_combat_log(rows)
    assert combined["event_count"] == 8
    assert combined["abilities"] == full["abilities"]
    assert combined["event_stream_receipt"]["complete"] is False


@pytest.mark.parametrize("new_count", [1, 2, 3])
def test_combat_event_controller_epoch_reset_retries_zero_without_contamination(new_count):
    from tools.bot_ml.combat_log_event_stream import CombatLogDeltaController
    controller = CombatLogDeltaController(send_commands=lambda rows: None,
        read_rows=lambda: [], command_counts={})
    delta = _decoded_delta([1, 2], cursor_before=0, cursor_after=2, event_count=2)
    controller.bind_status(delta)
    commands = []
    controller.append_command(commands, now=0)
    controller.observe_rows(_framed_combat_payload(delta, 1))
    controller.append_command(commands, now=2)
    assert commands[-1] == "botauto combatlog raid delta 2 4096"
    reset = _decoded_delta(list(range(3, new_count + 1)), cursor_before=2,
        cursor_after=max(2, new_count), event_count=new_count, combat_log_epoch=2)
    controller.observe_rows(_framed_combat_payload(reset, 2))
    controller.append_command(commands, now=2)
    assert commands[-1] == "botauto combatlog raid delta 0 4096"
    reset = _decoded_delta(list(range(1, new_count + 1)), cursor_before=0,
        cursor_after=new_count, event_count=new_count, combat_log_epoch=2)
    controller.observe_rows(_framed_combat_payload(reset, 3))
    assert controller.stream.receipt()["complete"] is True
    assert controller.stream.receipt()["transport_rejections"] == []


def test_combat_event_rejects_frame_kind_payload_conflict():
    payload = _decoded_delta([1], cursor_before=0, cursor_after=1, event_count=1)
    stream = CombatLogEventStream()
    result = stream.observe_rows(_framed_combat_payload(payload, kind="full"))[0]
    assert result.accepted is False
    assert stream.cursor == 0
    assert "chunk_payload_kind_conflict" in stream.receipt()["transport_rejections"]


def test_combat_log_transport_status_isolates_abandoned_delta_from_final_full():
    delta = _decoded_delta([1], cursor_before=0, cursor_after=1, event_count=1)
    partial = _framed_combat_payload(delta, 1)[0]
    partial["chunk_count"] = 2
    full = dict(delta, action="botauto_combatlog", event_count=1, abilities=[])
    rows = [partial, *_framed_combat_payload(full, 2, "full")]
    status = combat_log_transport_status(rows)
    assert status["complete_marker"] is True
    assert status["reassembled"] is True
    assert status["expected_chunks"] == status["received_chunks"] == 1
    assert combined_combat_log(rows)["event_count"] == 1
    # A later complete delta cannot stand in for the final aggregate export.
    assert combat_log_transport_status(_framed_combat_payload(delta, 3))["reassembled"] is False


def test_combat_event_finalization_binds_accepted_status_before_first_delta():
    delta = _decoded_delta([1], cursor_before=0, cursor_after=1, event_count=1)
    full = dict(delta, action="botauto_combatlog", event_count=1, abilities=[])
    foreign = dict(delta, server_epoch=99)
    foreign_full = dict(full, server_epoch=99, event_count=999)
    rows = [*_framed_combat_payload(foreign, 1), *_framed_combat_payload(delta, 2),
            full, foreign_full]
    result = combined_combat_log(rows, expected_status=delta)
    assert result["server_epoch"] == 88
    assert result["event_count"] == 1
    assert result["event_stream_receipt"]["identity"]["server_epoch"] == 88
    assert combined_combat_log([foreign_full], expected_status=delta) == {}
