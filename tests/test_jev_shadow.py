import copy
import json
from pathlib import Path

import pytest

from tools.bot_ml import jev_shadow as shadow


def laya_review():
    """A producer-shaped one-actor review with explicit unknowns/limitations."""
    return {
        "jev_input": {
            "state": {
                "run_id": "laya-run",
                "segment_id": "magmaw:0",
                "native_gameplay_outcome": {
                    "status": "clear",
                    "certification_status": "uncertified",
                    "native_clear": True,
                },
                "boss_dps_review": {
                    "actor_identity": [
                        {
                            "bot_guid": 7,
                            "bot_name": "Aster",
                            "role": "dps",
                            "class_spec": "hunter",
                            "class_name": "Hunter",
                        }
                    ],
                    "actor_loss_signals": [
                        {
                            "bot_guid": 7,
                            "class_spec": "hunter",
                            "encounter_dps": 1234,
                            "encounter_dps_basis": "wcl_window_dps",
                            "wcl_window_dps": 1234,
                            "wcl_observed_dps": 2000,
                            "dps_delta_vs_wcl": -766,
                            "encounter_dps_gap_vs_wcl": True,
                            "wcl_window_dps_gap_vs_wcl": True,
                            "active_seconds": 50,
                            "damage_uptime": 0.7,
                            "idle_fraction": 0.3,
                            "moving_fraction": 0.02,
                            "distance_avg": 22,
                            "native_outcome_count": 30,
                            "native_actionable_failure_count": 2,
                            "native_actionable_failure_ratio": 0.066,
                            "native_outcome_counts": {
                                "cast_success": 28,
                                "out_of_range": 2,
                            },
                            "candidate_scan_count": 100,
                            "candidate_gate_counts": {
                                "profile_wait": 98,
                                "movement_or_range": 2,
                            },
                            "duty_explains_idle": False,
                            "required_assignment_active": False,
                            "assignment_status": "not_required",
                            "counterfactual_status": "eligible",
                            "damage_cadence_capture": "full_window",
                            "damage_gap_max_seconds": 4.5,
                            "damage_gap_count_ge_3_seconds": 2,
                            "timeline_signal": {
                                "comparison_status": "not_comparable",
                                "reference_actor_id": "unmatched",
                                "dps_comparison_status": "unmatched",
                                "bot_event_input_status": "complete",
                                "wcl_only_abilities": [
                                    {"ability": "A", "wcl_completed_casts": 1}
                                ],
                                "comparison_limitations": ["identity_unmatched"],
                                "gap_overlap_evidence": {
                                    "status": "unavailable",
                                    "reason": "no_timestamped_overlap",
                                },
                            },
                        }
                    ],
                    "combat_metrics": {
                        "actors": [
                            {
                                "bot_guid": 7,
                                "damage": 74000,
                                "pet_damage": 17000,
                                "pet_damage_share": 0.23,
                                "raw_event_pet_damage": 16000,
                                "raw_event_pet_damage_share": 0.22,
                                "pet_active_seconds": 55,
                                "pet_uptime": 0.916,
                            }
                        ]
                    },
                },
            }
        }
    }


def roster_review():
    """Ten admitted actors: six DPS signals plus four role-only identities."""
    review = laya_review()
    state = review["jev_input"]["state"]
    boss = state["boss_dps_review"]
    identities = [
        {"bot_guid": 7, "class_spec": "hunter", "role": "dps", "bot_name": "Aster", "class_name": "Hunter"},
        {"bot_guid": 8, "class_spec": "blood_death_knight", "role": "tank", "bot_name": "Tank-8"},
        {"bot_guid": 9, "class_spec": "restoration_druid", "role": "healer", "bot_name": "Healer-9"},
        {"bot_guid": 10, "class_spec": "holy_paladin", "role": "healer", "bot_name": "Healer-10"},
        {"bot_guid": 11, "class_spec": "discipline_priest", "role": "healer", "bot_name": "Healer-11"},
        {"bot_guid": 12, "class_spec": "fire_mage", "role": "dps", "bot_name": "Dps-12"},
        {"bot_guid": 13, "class_spec": "fire_mage", "role": "dps", "bot_name": "Dps-13"},
        {"bot_guid": 14, "class_spec": "affliction_warlock", "role": "dps", "bot_name": "Dps-14"},
        {"bot_guid": 15, "class_spec": "survival_hunter", "role": "dps", "bot_name": "Dps-15"},
        {"bot_guid": 16, "class_spec": "elemental_shaman", "role": "dps", "bot_name": "Dps-16"},
    ]
    base_actor = boss["actor_loss_signals"][0]
    dps_specs = [(7, "hunter"), (12, "fire_mage"), (13, "fire_mage"),
                 (14, "affliction_warlock"), (15, "survival_hunter"), (16, "elemental_shaman")]
    signals = []
    for guid, class_spec in dps_specs:
        actor = copy.deepcopy(base_actor)
        actor["bot_guid"] = guid
        actor["class_spec"] = class_spec
        signals.append(actor)
    boss["actor_identity"] = identities
    boss["actor_loss_signals"] = signals
    boss["action_outcomes"] = [
        {
            "bot_guid": 8,
            "action_name": "taunt",
            "outcome": "cast_failed",
            "reason_code": "no_line_of_sight",
            "count": 2,
        },
        {
            "bot_guid": 9,
            "action_name": "heal",
            "outcome": "no_action",
            "reason_code": "target_missing",
            "count": 3,
        },
        {"action_name": "foreign_row", "outcome": "cast_failed", "count": 999},
    ]
    boss["candidate_rejections"] = [
        {
            "bot_guid": 9,
            "action_categories": ["heal"],
            "reason": "target_missing",
            "count": 4,
        },
        {"reason": "foreign_row", "count": 999},
    ]
    return review


def packet():
    return {"model": shadow.MODEL, "state": {"run_id": "closed-run", "actor_review": {"bot_guid": 7}},
            "questions": {"actor_action_7": {"type": "choice", "instructions": "Choose a diagnostic.",
                                          "criteria": {"z": "unknown", "a": "known"}}}}


def response():
    return {"model": shadow.MODEL, "answers": {"actor_action_7": {
        "type": "choice", "choice": "z", "confidence": 0.99,
        "probabilities": {"z": 0.99, "a": 0.01}}}}


def test_shadow_preserves_order_and_never_promotes_confidence_to_label():
    row = shadow.make_row(packet(), identity={"run_id": "closed-run", "closed": True},
        backend={"revision": "abc"}, response=response(), latency_sec=1)
    assert row["request_json"].index('"z"') < row["request_json"].index('"a"')
    assert shadow.sha(row["request_json"].encode()) == row["request_sha256"]
    assert row["label"] is None
    assert not row["training_eligible"] and not row["action_authorized"]
    assert row["admission"] == "quarantine"
    assert "adjudicated_label_missing" in row["quarantine_reasons"]


def test_backend_failure_keeps_evidence_and_does_not_abort_other_actors(tmp_path, monkeypatch):
    calls = []
    def call(request, endpoint):
        calls.append(request)
        if len(calls) == 1:
            raise OSError("offline")
        return response()
    monkeypatch.setattr(shadow, "call_local", call)
    second = packet()
    second["state"]["actor_review"]["bot_guid"] = 8
    summary = shadow.write_batch([packet(), second], tmp_path / "batch",
        identity={"run_id": "closed-run", "closed": True}, backend={})
    rows = [json.loads(line) for line in (tmp_path / "batch/examples.jsonl").read_text().splitlines()]
    assert len(calls) == 2
    assert summary["errors"] == 1 and summary["predictions"] == 1
    assert len(rows) == 2 and all(row["split_group"] == "closed-run" for row in rows)
    assert rows[0]["response"] is None and rows[0]["error"]
    with pytest.raises(FileExistsError):
        shadow.write_batch([packet()], tmp_path / "batch",
            identity={"run_id": "closed-run", "closed": True}, backend={})


def test_active_and_wrong_run_rejected_before_inference(tmp_path):
    with pytest.raises(ValueError, match="closed"):
        shadow.write_batch([packet()], tmp_path, identity={"run_id": "closed-run"}, backend={})
    with pytest.raises(ValueError, match="identities"):
        shadow.write_batch([packet()], tmp_path, identity={"run_id": "other", "closed": True}, backend={})
    assert not (tmp_path / "examples.jsonl").exists()


def test_local_does_not_fall_back_to_hosted():
    with pytest.raises(ValueError, match="loopback"):
        shadow.call_local(packet(), "https://api.typesafe.ai/v1/systemone")


@pytest.mark.parametrize("payload", [None, [], {"answers": None}, response()])
def test_actual_http_path_preserves_request_and_validates_answer(payload):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    bodies = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            bodies.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(shadow.encoded(payload))
        def log_message(self, *args):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/v1/systemone"
        if payload == response():
            assert shadow.call_local(packet(), endpoint) == payload
        else:
            with pytest.raises(ValueError, match="typed answer"):
                shadow.call_local(packet(), endpoint)
        assert bodies == [shadow.encoded(packet())]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_unhashable_choice_is_a_captured_model_error():
    bad = response()
    bad["answers"]["actor_action_7"]["choice"] = []
    with pytest.raises(shadow.analyzer.JevError, match="invalid choice"):
        shadow.analyzer._validate_typed_answers(bad["answers"], packet()["questions"])


def test_assignment_prediction_without_required_duty_is_flagged_not_labeled():
    result = response()
    result["answers"]["actor_action_7"]["choice"] = "encounter_assignment"
    verdict = shadow.review_prediction(packet(), result)
    assert verdict["status"] == "review_required"
    assert not verdict["ground_truth_label"]


def test_default_model_is_compact_laya_and_preserves_unknown_limits():
    review = laya_review()
    packets = shadow.actor_packets(review)
    assert shadow.MODEL == "convaiinnovations/laya-typed-decisions"
    assert shadow.ENDPOINT == "http://127.0.0.1:8000/v1/systemone"
    assert len(packets) == 1
    packet = packets[0]
    assert packet["model"] == shadow.MODEL
    question = packet["questions"]["actor_action_7"]
    assert question["type"] == "choice"
    assert max(map(len, question["criteria"].values())) <= 48
    assert shadow.laya_packets.estimated_tokens(question) <= 160
    assert shadow.laya_packets.estimated_tokens(packet["state"]) <= 650

    actor = packet["state"]["actor_review"]
    assert actor["bot_guid"] == 7
    assert actor["actor_identity"]["bot_name"] == "Aster"
    assert actor["native"]["native_actionable_failure_count"] == 2
    assert actor["owner_pet"]["pet_damage"] == 17000
    assert actor["owner_pet"]["pet_damage_share"] == 0.23
    assert actor["timeline_signal"]["dps_comparison_status"] == "unmatched"
    assert actor["timeline_signal"]["gap_overlap_evidence"]["status"] == "unavailable"
    assert "combat_dps" not in actor["observed"]
    assert "pet_active_dps" not in actor["owner_pet"]
    assert "WCL unmatched is context only." in packet["state"]["limitations"]
    assert "Owner gaps exclude pets; unknown stays unknown." in packet["state"]["limitations"]


def test_explicit_qwen_model_keeps_legacy_actor_packet():
    review = laya_review()
    model = "Qwen/Qwen3.5-0.8B"
    packet = shadow.actor_packets(review, model)[0]
    actor = review["jev_input"]["state"]["boss_dps_review"]["actor_loss_signals"][0]
    expected_questions = shadow.analyzer._jev_questions(
        False,
        include_next_fix=False,
        actor_specs=[actor],
        include_timeline=False,
        include_assignment=False,
    )
    expected_questions = {
        key: value
        for key, value in expected_questions.items()
        if key.startswith("actor_action_")
    }
    assert packet["model"] == model
    assert packet["state"]["actor_review"] == actor
    assert packet["questions"] == expected_questions
    assert len(packet["questions"]["actor_action_7"]["instructions"]) > 200


def test_laya_packet_keeps_duty_and_counterfactual_review_restrictions():
    review = laya_review()
    packet = shadow.actor_packets(review)[0]
    packet["state"]["actor_review"]["required_assignment_active"] = True
    packet["state"]["actor_review"]["assignment_status"] = "incomplete"
    packet["state"]["actor_review"]["counterfactual_status"] = "required_assignment"
    result = {
        "model": shadow.MODEL,
        "answers": {
            "actor_action_7": {
                "type": "choice",
                "choice": "uptime_cadence",
                "confidence": 0.9,
                "probabilities": {choice: 0.0 for choice in packet["questions"]["actor_action_7"]["criteria"]},
            }
        },
    }
    result["answers"]["actor_action_7"]["probabilities"]["uptime_cadence"] = 0.9
    verdict = shadow.review_prediction(packet, result)
    assert verdict["status"] == "review_required"
    assert "counterfactual_evidence_unavailable_or_ineligible" in verdict["reasons"]


def test_all_admitted_roster_actors_get_unique_role_scoped_packets():
    review = roster_review()
    packets = shadow.actor_packets(review)
    by_guid = {packet["state"]["actor_review"]["bot_guid"]: packet for packet in packets}
    assert set(by_guid) == set(range(7, 17))
    assert len(by_guid) == 10
    assert len({json.dumps(packet["questions"], sort_keys=True) for packet in packets}) == 10

    baseline = shadow.actor_packets(laya_review())[0]
    assert by_guid[7]["state"] == baseline["state"]
    assert by_guid[7]["questions"] == baseline["questions"]

    for guid in (7, 12, 13, 14, 15, 16):
        packet = by_guid[guid]
        assert packet["questions"][f"actor_action_{guid}"]["criteria"] == shadow.laya_packets.ACTOR_OPTIONS
        assert "encounter_dps" in packet["state"]["actor_review"]["observed"]
        assert "No DPS baseline for this role." not in packet["state"]["limitations"]

    for guid in (8, 9, 10, 11):
        packet = by_guid[guid]
        actor = packet["state"]["actor_review"]
        question = packet["questions"][f"actor_action_{guid}"]
        if guid in (8, 9):
            assert question["criteria"] == {
                "native_action_review": shadow.laya_packets.ROLE_OPTIONS["native_action_review"],
                "insufficient_role_evidence": shadow.laya_packets.ROLE_OPTIONS["insufficient_role_evidence"],
                "collect_more_canaries": shadow.laya_packets.ROLE_OPTIONS["collect_more_canaries"],
            }
        else:
            assert question["criteria"] == {
                "insufficient_role_evidence": shadow.laya_packets.ROLE_OPTIONS["insufficient_role_evidence"],
                "collect_more_canaries": shadow.laya_packets.ROLE_OPTIONS["collect_more_canaries"],
            }
        assert max(map(len, question["criteria"].values())) <= 48
        assert shadow.laya_packets.estimated_tokens(question) <= 160
        assert actor["role"] in {"tank", "healer"}
        assert actor["class_spec"]
        assert actor["observed"] == {
            "damage": {"status": "unavailable", "reason": "role_metric_not_in_review"},
            "healing": {"status": "unavailable", "reason": "role_metric_not_in_review"},
            "threat": {"status": "unavailable", "reason": "role_metric_not_in_review"},
            "mitigation": {"status": "unavailable", "reason": "role_metric_not_in_review"},
        }
        assert "timeline_signal" not in actor
        assert "encounter_dps" not in actor["observed"]
        assert "wcl_observed_dps" not in actor["observed"]
        assert "No DPS baseline for this role." in packet["state"]["limitations"]
        assert "party_damage" not in packet["state"]

    assert by_guid[8]["state"]["actor_review"]["native"]["action_outcomes"]["status"] == "observed"
    assert by_guid[8]["state"]["actor_review"]["native"]["candidate_rejections"]["status"] == "unavailable"
    assert by_guid[9]["state"]["actor_review"]["native"]["action_outcomes"]["status"] == "observed"
    assert by_guid[9]["state"]["actor_review"]["native"]["candidate_rejections"]["status"] == "observed"
    for guid in (10, 11):
        native = by_guid[guid]["state"]["actor_review"]["native"]
        assert native["action_outcomes"]["status"] == "unavailable"
        assert native["candidate_rejections"]["status"] == "unavailable"


def test_role_packets_do_not_turn_unavailable_evidence_into_a_label():
    packet = next(
        packet for packet in shadow.actor_packets(roster_review())
        if packet["state"]["actor_review"]["bot_guid"] == 10
    )
    question = packet["questions"]["actor_action_10"]
    assert set(question["criteria"]) == {
        "insufficient_role_evidence",
        "collect_more_canaries",
    }
    answer = {
        "type": "choice",
        "choice": "collect_more_canaries",
        "confidence": 0.95,
        "probabilities": {choice: 0.0 for choice in question["criteria"]},
    }
    answer["probabilities"]["collect_more_canaries"] = 0.95
    verdict = shadow.review_prediction(
        packet,
        {"model": shadow.MODEL, "answers": {"actor_action_10": answer}},
    )
    assert verdict["status"] == "advisory_only"
    assert not verdict["ground_truth_label"]
