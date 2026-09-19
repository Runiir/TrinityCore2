from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml import run_magmaw_jev_canary as canary


def test_build_runner_command_owns_output_directory() -> None:
    command = canary.build_runner_command(
        Path("/tmp/magmaw-next"),
        ["--duration-policy", "completion-watchdog"],
    )

    assert command[-4:] == [
        "--output-dir",
        "/tmp/magmaw-next",
        "--duration-policy",
        "completion-watchdog",
    ]


def test_build_runner_command_rejects_output_override() -> None:
    with pytest.raises(ValueError, match="must not override"):
        canary.build_runner_command(
            Path("/tmp/magmaw-next"),
            ["--output-dir", "/tmp/other"],
        )


def test_build_jev_command_includes_baseline_and_route_scope(tmp_path: Path) -> None:
    command = canary.build_jev_command(
        run_dir=tmp_path / "run",
        output=tmp_path / "run" / "jev_report.json",
        ledger=tmp_path / "ledger.json",
        baseline=tmp_path / "baseline.json",
        env_file=Path(".env"),
        wcl_reference=Path("wcl.json"),
        native_log=tmp_path / "native_mushroom.log",
        run_id="run-1",
        segment_id="magmaw_10n",
        change_id="change-1",
        change_note="test",
        scope_route_prefix="bwd.magmaw.",
        expected_route=["bwd.magmaw.encounter"],
    )

    assert "--baseline-report" in command
    assert "--native-log" in command
    assert command[command.index("--scope-route-prefix") + 1] == "bwd.magmaw."
    assert command[-2:] == ["--expected-route-node", "bwd.magmaw.encounter"]


def test_build_jev_command_includes_all_actor_timeline_comparison(
    tmp_path: Path,
) -> None:
    timeline = tmp_path / "timeline_comparison.json"
    command = canary.build_jev_command(
        run_dir=tmp_path / "run",
        output=tmp_path / "run" / "jev_report.json",
        ledger=None,
        baseline=None,
        env_file=Path(".env"),
        wcl_reference=Path("wcl.json"),
        native_log=None,
        run_id="run-1",
        segment_id="magmaw_10n",
        change_id="change-1",
        change_note="timeline",
        scope_route_prefix="bwd.magmaw.",
        expected_route=["bwd.magmaw.encounter"],
        timeline_comparison=timeline,
    )

    assert command[command.index("--timeline-comparison") + 1] == str(timeline)


def test_stage_external_route_catalog_restores_original_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    external = tmp_path / "external"
    branch_routes = repo / "dataset" / "validation_scenarios"
    external_routes = external / "dataset" / "validation_scenarios"
    branch_routes.mkdir(parents=True)
    external_routes.mkdir(parents=True)
    (branch_routes / "manifest.json").write_text("branch-manifest\n", encoding="utf-8")
    (branch_routes / "validation_routes.jsonl").write_text(
        "branch-route\n", encoding="utf-8"
    )
    (external_routes / "manifest.json").write_text("old-manifest\n", encoding="utf-8")
    (external_routes / "validation_routes.jsonl").write_text(
        "old-route\n", encoding="utf-8"
    )

    original_root = canary.REPO_ROOT
    canary.REPO_ROOT = repo
    try:
        arguments = [
            "--validation-scenario-dir",
            "dataset/validation_scenarios",
            "--runtime-asset-source-checkout",
            str(external),
        ]
        with canary.stage_external_route_catalog(arguments):
            assert (external_routes / "manifest.json").read_text() == "branch-manifest\n"
            assert (external_routes / "validation_routes.jsonl").read_text() == "branch-route\n"
        assert (external_routes / "manifest.json").read_text() == "old-manifest\n"
        assert (external_routes / "validation_routes.jsonl").read_text() == "old-route\n"
    finally:
        canary.REPO_ROOT = original_root


def test_native_outcome_requires_manifest_boss_kill_and_watchdogs() -> None:
    report = {
        "completion_reason": "validation_route_manifest_complete",
        "evidence": {
            "manifest_completion_evidence": [{"route_node_id": "bwd.magmaw.encounter"}],
            "real_boss_kill_evidence": [{"route_node_id": "bwd.magmaw.encounter"}],
        },
        "watchdog_state": {},
        "acceptance_verification": {"accepted": True},
        "acceptable_final_evidence": True,
        "final_evidence_rejections": [],
    }

    outcome = canary._native_outcome(report)

    assert outcome == {
        "status": "clear",
        "native_clear": True,
        "certification_status": "accepted",
        "completion_reason": "validation_route_manifest_complete",
    }


def test_capture_native_mushroom_log_keeps_only_the_new_run(tmp_path: Path) -> None:
    source = tmp_path / "Server.log"
    source.write_text("old MagmawWildMushroomNative record\n", encoding="utf-8")
    offset = canary.native_log_offset(source)
    source.write_text(
        "old MagmawWildMushroomNative record\n"
        "new ordinary server line\n"
        "new MagmawWildMushroomNative event=detonate\n",
        encoding="utf-8",
    )
    output = tmp_path / "run" / "native_mushroom.log"

    assert canary.capture_native_mushroom_log(source, output, offset)
    assert output.read_text(encoding="utf-8") == (
        "new MagmawWildMushroomNative event=detonate\n"
    )


def test_capture_native_mushroom_log_handles_equal_size_log_recreation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Server.log"
    source.write_text("old MagmawWildMushroomNative record\n", encoding="utf-8")
    snapshot = canary.native_log_snapshot(source)
    assert snapshot is not None
    source.write_text("new MagmawWildMushroomNative event=detonate\n", encoding="utf-8")
    output = tmp_path / "run" / "native_mushroom.log"

    assert canary.capture_native_mushroom_log(source, output, snapshot)
    assert output.read_text(encoding="utf-8") == (
        "new MagmawWildMushroomNative event=detonate\n"
    )


def test_write_status_never_serializes_a_secret(tmp_path: Path) -> None:
    status_path = tmp_path / "canary_status.json"
    status = canary.write_status(
        status_path,
        run_dir=tmp_path / "run",
        run_id="run-1",
        change_id="change-1",
        runner_command=["python", "-m", "runner"],
        runner_returncode=0,
        jev_command=["python", "-m", "analyzer"],
        jev_returncode=0,
        jev_report=tmp_path / "jev_report.json",
        live_report={
            "completion_reason": "validation_route_manifest_complete",
            "evidence": {
                "manifest_completion_evidence": [{"route_node_id": "bwd.magmaw.encounter"}],
                "real_boss_kill_evidence": [{"route_node_id": "bwd.magmaw.encounter"}],
            },
            "watchdog_state": {},
            "acceptance_verification": {"accepted": True},
            "acceptable_final_evidence": True,
            "final_evidence_rejections": [],
        },
    )

    loaded = json.loads(status_path.read_text(encoding="utf-8"))
    assert loaded == status
    assert "secret-value" not in status_path.read_text(encoding="utf-8")
    assert status["promotion"]["status"] == "eligible_for_human_review"
