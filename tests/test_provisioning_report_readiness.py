"""Offline report generation must preserve failed qualification readiness."""

import json
import sys

import pytest

from tools.bot_ml import validate_validation_provisioning as verifier


@pytest.mark.parametrize("allow_unready, failure_kind, expected_exit", [
    (False, None, 1), (True, None, 0),
    (True, "payload", 1), (True, "generated", 1), (True, "database", 1),
])
def test_report_cli_keeps_readiness_false_and_validation_failures_fatal(
    tmp_path, monkeypatch, allow_unready, failure_kind, expected_exit
):
    output = tmp_path / "report.json"
    argv = ["verify", "--output", str(output), "--worldserver-conf",
            str(tmp_path / "absent.conf"), "--check-db"]
    if allow_unready:
        argv.append("--allow-unready")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(verifier, "load_config_with_bwd_diagnostic_shards", lambda *a: {})
    monkeypatch.setattr(verifier, "load_or_build_gear_profiles", lambda *a: {})
    monkeypatch.setattr(verifier, "apply_gear_profiles", lambda *a: {})
    monkeypatch.setattr(verifier, "load_json", lambda *a: {"all_ready": False})
    for name, kind in [("validate_payloads", "payload"),
                       ("validate_generated_artifacts", "generated"),
                       ("validate_database", "database")]:
        failures = [{"check": kind}] if failure_kind == kind else []
        monkeypatch.setattr(verifier, name,
                            lambda *a, _failures=failures, **kw: (_failures, {"checked": True}))
    assert verifier.main() == expected_exit
    report = json.loads(output.read_text())
    assert report["all_passed"] is False
    assert report["provisioning_all_ready"] is False
    assert report["failure_count"] == int(failure_kind is not None)
