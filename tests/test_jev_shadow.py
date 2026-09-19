import json
from pathlib import Path

import pytest

from tools.bot_ml import jev_shadow as shadow


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
