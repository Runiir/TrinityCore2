import copy
import json

import pytest

from tools.raid_program import bot_improvement_advice as advice


def comparison():
    return {"schema": "evidence_comparison_v1", "kind": "native", "pairs": [{
        "current": {"actor": "12", "spec": "blood", "role": "tank", "dps": 20000,
                    "window": {"seconds": 300}, "activity": {}},
        "reference": {"actor": "12", "dps": 25000, "window": {"seconds": 300}},
        "context_comparison": {"checks": {"mode": {"status": "missing"}}},
        "components": [{"key": "55050", "apparent_gap_dps": 5000,
                        "current": {"ordinary_casts": None}, "reference": {"ordinary_casts": 30}}],
        "reconciliation": {"unattributed_residual_dps": 1000},
    }]}


def answer(choice):
    return {"answers": {"next_investigation": {"type": "choice", "choice": choice, "confidence": 0.9,
            "probabilities": {k: float(k == choice) for k in advice.OPTIONS}}}}


def test_keeps_unknown_casts_context_and_residual_without_cross_actor_mix():
    doc = comparison()
    other = copy.deepcopy(doc["pairs"][0])
    other["current"]["actor"] = "99"
    other["current"]["activity"] = {"private_to_other_actor": 100}
    doc["pairs"].append(other)
    rows = advice.projections(doc, actor="12")
    assert len(rows) == 1
    state = rows[0]["state"]
    assert state["component"]["current"]["ordinary_casts"] is None
    assert state["context"]["checks"]["mode"]["status"] == "missing"
    assert state["residual_dps"] == 1000
    assert "private_to_other_actor" not in json.dumps(state)


@pytest.mark.parametrize("choice", list(advice.OPTIONS))
def test_every_answer_is_only_a_suggestion(tmp_path, monkeypatch, choice):
    monkeypatch.setattr(advice.jev_shadow, "call_local", lambda *a: answer(choice))
    original = comparison()
    before = copy.deepcopy(original)
    summary = advice.review(original, tmp_path / "review", backend="local")
    assert original == before
    assert summary["acceptance_changed"] is False
    assert summary["training_eligible"] is False
    assert summary["reviews"][0]["status"] == "advisory"
    assert summary["reviews"][0]["suggestion"]["choice"] == choice


def test_oversized_evidence_retained_not_silently_clipped_or_submitted(tmp_path, monkeypatch):
    doc = comparison()
    doc["pairs"][0]["current"]["activity"] = {"essential_constraint": "x" * 5000}
    monkeypatch.setattr(advice.jev_shadow, "call_local", lambda *a: pytest.fail("must not submit"))
    summary = advice.review(doc, tmp_path / "review", backend="local")
    assert summary["reviews"][0]["status"] == "not_reviewed"
    retained = json.loads((tmp_path / "review/examples.jsonl").read_text())
    assert retained["request"]["state"]["activity"]["essential_constraint"] == "x" * 5000


def test_provider_failure_is_not_retried_and_cli_returns_success(tmp_path, monkeypatch):
    calls = []
    def fail(*args):
        calls.append(args)
        raise ValueError("HTTP 422 context_budget_exceeded")
    monkeypatch.setattr(advice.jev_shadow, "call_local", fail)
    path = tmp_path / "input.json"
    path.write_text(json.dumps(comparison()))
    assert advice.main(["--comparison", str(path), "--output", str(tmp_path / "out"), "--backend", "local"]) == 0
    assert len(calls) == 1
    summary = json.loads((tmp_path / "out/summary.json").read_text())
    assert summary["reviews"][0]["suggestion"] is None


def test_provider_facts_identical_and_hosted_has_one_attempt(tmp_path, monkeypatch):
    received = []
    monkeypatch.setattr(advice.jev_shadow, "call_local", lambda p, e: received.append(p["state"]) or answer("insufficient_evidence"))
    monkeypatch.setattr(advice.analyzer, "_jev_key", lambda p: "test-key")
    def hosted(state, key, questions, **kwargs):
        assert kwargs == {"attempts": 1}
        received.append(state)
        return answer("insufficient_evidence")
    monkeypatch.setattr(advice.analyzer, "_call_jev", hosted)
    advice.review(comparison(), tmp_path / "out", backend="both")
    assert received[0] == received[1]


def test_wcl_actor_with_duties_and_no_components_stays_inspectable():
    doc = {"schema": "raid_damage_gap_comparison_v1", "window": {"seconds": 140},
           "actors": [{"actor_guid": 12, "native_dps": 20000, "reference_dps": 25000,
                       "limitations": ["reference has different phase coverage"], "duty_coverage": "partial",
                       "duties": [{"provenance": "observed", "interval_ms": [1000, 2000]}], "components": []}]}
    state = advice.projections(doc)[0]["state"]
    assert state["duties"][0]["provenance"] == "observed"
    assert state["component"] is None
    assert state["dps"] == [20000, 25000]
    assert state["context"]["reference_limitations"] == ["reference has different phase coverage"]
    assert state["context"]["duty_coverage"] == "partial"


def test_output_never_overwrites_a_prior_receipt(tmp_path):
    advice.review(comparison(), tmp_path / "out", prepare_only=True)
    with pytest.raises(FileExistsError):
        advice.review(comparison(), tmp_path / "out", prepare_only=True)
