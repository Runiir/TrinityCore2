import json
import sys
from io import BytesIO

from tools.bot_ml import jev_shadow as shadow


def run_hosted(tmp_path, monkeypatch, *, prepare=False, fail=False):
    review = {"jev_input": {"state": {"run_id": "closed", "boss_dps_review": {
        "actor_identity": [{"bot_guid": 7, "role": "dps", "class_spec": "fire_mage"}],
        "actor_loss_signals": [{"bot_guid": 7, "counterfactual_status": "unavailable"}],
    }}}}
    inputs = {
        "review": review,
        "identity": {"run_id": "closed", "closed": True},
        "backend": {"provider": "typesafe_hosted"},
    }
    for name, value in inputs.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    calls = []
    def key(path):
        assert not prepare
        return "test-key-never-persist"
    def hosted(state, api_key, questions):
        assert api_key == "test-key-never-persist"
        calls.append((state, questions))
        if fail:
            raise shadow.analyzer.JevError("hosted unavailable")
        return {"model": "jev-resolved-test", "answers": {
            name: {"type": "choice", "choice": "collect_more_canaries"}
            for name in questions
        }}
    def local(*args):
        raise AssertionError("hosted batch must not fall back to local")
    monkeypatch.setattr(shadow.analyzer, "_jev_key", key)
    monkeypatch.setattr(shadow.analyzer, "_call_jev", hosted)
    monkeypatch.setattr(shadow, "call_local", local)
    argv = ["shadow", "--review", str(tmp_path / "review.json"), "--identity",
            str(tmp_path / "identity.json"), "--backend-receipt",
            str(tmp_path / "backend.json"), "--output", str(tmp_path / "out"),
            "--backend", "hosted"]
    if prepare:
        argv.append("--prepare-only")
    monkeypatch.setattr(sys, "argv", argv)
    result = shadow.main()
    payload = (tmp_path / "out/examples.jsonl").read_text()
    assert "test-key-never-persist" not in payload
    return result, json.loads(payload), calls


def test_explicit_hosted_batch_retains_request_and_resolved_model(tmp_path, monkeypatch):
    code, row, calls = run_hosted(tmp_path, monkeypatch)
    assert code == 0 and len(calls) == 1
    packet = json.loads(row["request_json"])
    assert packet["model"] == shadow.analyzer.JEV_MODEL
    assert packet["state"] == calls[0][0]
    assert packet["questions"] == calls[0][1]
    assert row["source"] == "hosted_request"
    assert row["response"]["model"] == "jev-resolved-test"
    assert row["admission"] == "quarantine" and row["label"] is None
    assert not row["action_authorized"] and not row["training_eligible"]


def test_hosted_failure_retained_without_local_fallback(tmp_path, monkeypatch):
    code, row, calls = run_hosted(tmp_path, monkeypatch, fail=True)
    assert code == 2 and len(calls) == 1
    assert row["response"] is None and "hosted unavailable" in row["error"]


def test_hosted_prepare_needs_no_key_or_request(tmp_path, monkeypatch):
    code, row, calls = run_hosted(tmp_path, monkeypatch, prepare=True)
    assert code == 0 and calls == []
    assert row["source"] == "prepared" and row["response"] is None


def test_retained_hosted_bytes_match_actual_http_request(monkeypatch):
    packet = {"model": shadow.analyzer.JEV_MODEL,
              "state": {"run_id": "closed", "actor_review": {"bot_guid": 7}, "name": "Å"},
              "questions": {"role": {"type": "choice", "instructions": "Review",
                                     "criteria": {"insufficient_role_evidence": "Unknown"}}}}
    result = {"model": shadow.analyzer.JEV_MODEL, "answers": {"role": {
        "type": "choice", "choice": "insufficient_role_evidence", "confidence": 1.0,
        "probabilities": {"insufficient_role_evidence": 1.0}}}}
    bodies = []
    def request(req, timeout):
        bodies.append(req.data)
        return BytesIO(json.dumps(result).encode())
    monkeypatch.setattr(shadow.analyzer, "urlopen", request)
    response = shadow.analyzer._call_jev(packet["state"], "synthetic-key", packet["questions"])
    row = shadow.make_row(packet, identity={"run_id": "closed", "closed": True},
                          backend={}, response=response, latency_sec=0.1,
                          source="hosted_request")
    assert row["request_json"].encode() == bodies[0]
    assert row["request_sha256"] == shadow.sha(bodies[0])
    assert row["prediction_review"]["status"] == "advisory_only"
    assert not row["training_eligible"] and not row["action_authorized"]
