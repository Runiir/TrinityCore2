from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import tools.bot_ml.run_live_bot_validation as live_validation


SCENARIO_ID = "blackwing_descent_10n_magmaw_diagnostic"


def test_stale_default_route_stage_is_rejected_before_provisioning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stale_dvc_status(command, **_kwargs):
        assert list(command) == [
            "pixi",
            "run",
            "dvc",
            "status",
            "validation_scenarios",
            "--json",
        ]
        return live_validation.subprocess.CompletedProcess(
            command, 0, '{"validation_scenarios": {"changed outs": true}}', ""
        )

    monkeypatch.setattr(live_validation.subprocess, "run", stale_dvc_status)
    provisioning_called = False

    def unexpected_provisioning(*_args, **_kwargs):
        nonlocal provisioning_called
        provisioning_called = True
        raise AssertionError("provisioning started before route-stage preflight")

    monkeypatch.setattr(
        live_validation, "prepare_validation_provisioning", unexpected_provisioning
    )
    output_dir = tmp_path / "preparation"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bot-live-validate",
            "--prepare-only",
            "--apply-validation-provisioning",
            "--validation-route-manifest",
            "--validation-scenario-id",
            SCENARIO_ID,
            "--output-dir",
            str(output_dir),
        ],
    )

    with pytest.raises(SystemExit, match="runtime_route_dvc_lineage_dirty"):
        live_validation.main()

    assert provisioning_called is False
    assert output_dir.exists() is False


def test_fresh_default_route_stage_passes_without_reproduction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def clean_dvc_status(command, **_kwargs):
        assert list(command) == [
            "pixi",
            "run",
            "dvc",
            "status",
            "validation_scenarios",
            "--json",
        ]
        assert "repro" not in command
        return live_validation.subprocess.CompletedProcess(command, 0, "{}", "")

    monkeypatch.setattr(live_validation.subprocess, "run", clean_dvc_status)

    result = live_validation.preflight_validation_scenario_stage(
        Path("dataset/validation_scenarios"),
        SCENARIO_ID,
        profile_name=SCENARIO_ID,
    )

    assert result["required"] is True
    assert result["valid"] is True
    assert result["dvc_stage_current"] is True
    assert result["assets"]["dvc_stage"] == "validation_scenarios"
    assert result["assets"]["dvc_status"] == "{}"


def test_custom_route_fixture_does_not_require_dvc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.raid_program.capture_phase1_raid_foundation as foundation

    def unexpected_dvc_validation(*_args, **_kwargs):
        raise AssertionError("custom fixture unexpectedly consulted repository DVC")

    monkeypatch.setattr(
        foundation,
        "validate_runtime_profile_assets",
        unexpected_dvc_validation,
    )
    fixture_dir = tmp_path / "validation_scenarios"
    fixture_dir.mkdir()
    (fixture_dir / "validation_routes.jsonl").write_text(
        json.dumps({"scenario_id": "fixture"}) + "\n", encoding="utf-8"
    )

    result = live_validation.preflight_validation_scenario_stage(
        fixture_dir,
        "fixture",
        profile_name="fixture",
    )

    assert result["required"] is False
    assert result["valid"] is True
    assert result["reason"] == "custom_scenario_dir"
