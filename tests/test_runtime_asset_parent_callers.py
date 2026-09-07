from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.bot_ml import build_phase6_serial_soak_contract as phase6
from tools.bot_ml import build_phase9_serial_run_plan as phase9
from tools.bot_ml import build_validation_run_plan as validation_plan
from tools.bot_ml import run_cata_raid_dps_acceptance as dps_acceptance
from tools.bot_ml import run_phase8_all_spec_calibration as phase8
from tools.raid_program.runtime_asset_closure_binding import (
    ARGUMENTS,
    argument_argv_from_namespace,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def closure_namespace(tmp_path: Path, **values: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "runtime_asset_closure_manifest": (tmp_path / "closure.json").resolve(),
        "runtime_asset_source_checkout": (tmp_path / "source").resolve(),
        "runtime_asset_dvc_workspace": (tmp_path / "dvc").resolve(),
        "runtime_asset_bundle": (tmp_path / "bundle").resolve(),
        "runtime_asset_data_dir": (tmp_path / "data").resolve(),
        "runtime_asset_map_id": 725,
    }
    defaults.update(values)
    return argparse.Namespace(**defaults)


def closure_values(command: list[str]) -> dict[str, str]:
    return {
        name: command[command.index(flag) + 1]
        for name, flag in ARGUMENTS
    }


def expected_closure_values(namespace: argparse.Namespace) -> dict[str, str]:
    argv = argument_argv_from_namespace(namespace)
    return closure_values(argv)


def with_closure(namespace: argparse.Namespace, closure: argparse.Namespace) -> argparse.Namespace:
    for name, _flag in ARGUMENTS:
        setattr(namespace, name, getattr(closure, name))
    return namespace


def test_phase8_child_forwards_runtime_asset_closure(tmp_path: Path) -> None:
    closure = closure_namespace(tmp_path)
    args = with_closure(
        argparse.Namespace(
            worldserver=Path("worldserver"),
            config=Path("worldserver.conf"),
            timeout_sec=900,
            heartbeat_sec=30,
            session_transition_timeout_sec=360,
            session_environment="phase8-test",
            evidence_identity_manifest=None,
            retain_published_batch=False,
        ),
        closure,
    )
    attempt = {
        "cohort_id": "phase8-cohort",
        "attempt_index": 1,
        "mode": "single_target_300",
        "runtime_join_key": "arms_warrior",
        "seed": 1,
    }

    command = phase8.child_command(args, attempt, tmp_path / "attempt")

    assert closure_values(command) == expected_closure_values(closure)


def test_dps_acceptance_child_forwards_runtime_asset_closure(tmp_path: Path) -> None:
    closure = closure_namespace(tmp_path)
    args = with_closure(
        argparse.Namespace(
            worldserver=Path("worldserver"),
            worldserver_config=Path("worldserver.conf"),
            timeout_sec=900,
            heartbeat_sec=30,
            session_transition_timeout_sec=360,
            session_environment="dps-test",
        ),
        closure,
    )
    attempt = {
        "cohort_id": "dps-cohort",
        "attempt_index": 1,
        "mode": "single_target_300",
        "runtime_join_key": "arms_warrior",
        "seed": 1,
    }

    command = dps_acceptance.child_command(
        args,
        attempt,
        tmp_path / "attempt",
        tmp_path / "policy.json",
        tmp_path / "identity.json",
    )

    assert closure_values(command) == expected_closure_values(closure)


def test_phase6_live_attempt_forwards_runtime_asset_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closure = closure_namespace(tmp_path)
    expected = expected_closure_values(closure)
    observed: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        observed.append(command)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(phase6.subprocess, "run", fake_run)
    phase6._run_attempt(
        tmp_path / "attempt",
        cohort_id="phase6-cohort",
        attempt_index=1,
        profile="stonecore_5n",
        scenario_id="stonecore_5n",
        environment="phase6-test",
        timeout_sec=900,
        no_progress_window_sec=180,
        heartbeat_sec=30,
        runtime_asset_closure_argv=argument_argv_from_namespace(closure),
    )

    assert closure_values(observed[0]) == expected


def test_phase9_plan_forwards_runtime_asset_closure(tmp_path: Path) -> None:
    closure = closure_namespace(tmp_path)
    dps_state = tmp_path / "campaign_state.json"
    dps_state.write_text("{}\n", encoding="utf-8")

    plan = phase9.build_plan(
        REPO_ROOT / "experiments/configs/stonecore_phase9_pairwise_matrix_v1.json",
        REPO_ROOT / "artifacts/all_spec_program/runtime_asset_parent_test",
        REPO_ROOT / "artifacts/all_spec_program/runtime_asset_identity_test.json",
        "phase9-test",
        "phase9-cohort",
        dps_state,
        argument_argv_from_namespace(closure),
    )

    assert plan["attempts"]
    assert all(
        closure_values(attempt["command"]) == expected_closure_values(closure)
        for attempt in plan["attempts"]
    )


def test_generic_validation_plan_defers_paths_and_binds_each_scenario_map() -> None:
    scenarios = [
        {"scenario_id": "stonecore_5n", "map_id": 725},
        {"scenario_id": "blackwing_descent_10n", "map_id": 669},
    ]

    plan = validation_plan.build_plan(
        scenarios,
        Path("dataset/live"),
        Path("dataset/reports"),
        Path("dataset/scenarios"),
        None,
        900,
    )
    rows = {row["scenario_id"]: row for row in plan["scenarios"]}

    assert plan["runtime_asset_closure"]["binding_mode"] == "deferred_shell_environment"
    assert closure_values(rows["stonecore_5n"]["live_validate_command"])[
        "runtime_asset_map_id"
    ] == "725"
    assert closure_values(rows["blackwing_descent_10n"]["live_validate_command"])[
        "runtime_asset_map_id"
    ] == "669"
    assert "${RUNTIME_ASSET_CLOSURE_MANIFEST:?" in rows["stonecore_5n"][
        "live_validate_shell"
    ]


@pytest.mark.parametrize(
    ("entrypoint", "argv"),
    [
        (phase8.main, ["phase8", "--output-root", "{output}"]),
        (
            phase9.main,
            [
                "phase9",
                "--output-root",
                "{output}",
                "--evidence-identity-manifest",
                "{identity}",
                "--dps-acceptance-state",
                "{state}",
            ],
        ),
        (
            phase6.main,
            [
                "phase6",
                "--run-soak",
                "--attempt-root",
                "{output}",
                "--output-dir",
                "{contract}",
            ],
        ),
    ],
)
def test_parent_mains_reject_missing_closure_before_creating_output(
    entrypoint: object,
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    replacements = {
        "{output}": str(output),
        "{identity}": str(tmp_path / "identity.json"),
        "{state}": str(tmp_path / "state.json"),
        "{contract}": str(tmp_path / "contract"),
    }
    monkeypatch.setattr(
        sys,
        "argv",
        [replacements.get(value, value) for value in argv],
    )

    with pytest.raises(SystemExit, match="runtime_asset_closure_incomplete"):
        entrypoint()  # type: ignore[operator]

    assert not output.exists()


def test_dps_main_rejects_missing_closure_before_controller_lock(
    tmp_path: Path,
) -> None:
    output = tmp_path / "campaign"

    with pytest.raises(SystemExit, match="runtime_asset_closure_incomplete"):
        dps_acceptance.main(["--output-root", str(output)])

    assert not output.exists()


def test_make_live_validation_has_no_heavy_prerequisite_before_admission() -> None:
    source = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = source[source.index("bot-live-validate:") : source.index("\nbot-ml-export:")]

    assert recipe.startswith("bot-live-validate:\n")
    assert "local-configure" not in recipe
    assert "cmake --build" not in recipe
    assert "$(COMPOSE)" not in recipe
    assert all(flag in recipe for _name, flag in ARGUMENTS)


def test_generic_validation_plan_only_expands_exact_runtime_asset_bindings() -> None:
    adversarial = "${RUNTIME_ASSET_FAKE:?$(touch /tmp/should-not-run)}"

    assert validation_plan.shell_quote(adversarial) == f"'{adversarial}'"


def test_generated_validation_script_rejects_missing_binding_before_launch(
    tmp_path: Path,
) -> None:
    plan = validation_plan.build_plan(
        [{"scenario_id": "stonecore_5n", "map_id": 725}],
        tmp_path / "live",
        tmp_path / "reports",
        tmp_path / "scenarios",
        None,
        900,
    )
    script = tmp_path / "run.sh"
    validation_plan.write_shell_script(script, plan)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "pixi-launched"
    fake_pixi = fake_bin / "pixi"
    fake_pixi.write_text('#!/bin/sh\ntouch "$MARKER"\n', encoding="utf-8")
    fake_pixi.chmod(0o755)

    completed = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=tmp_path,
        env={"PATH": f"{fake_bin}:/usr/bin:/bin", "MARKER": str(marker)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "RUNTIME_ASSET_CLOSURE_MANIFEST" in completed.stderr
    assert not marker.exists()


def test_map_zero_remains_a_valid_calibration_map(tmp_path):
    from tools.raid_program.runtime_asset_closure_binding import argv_values
    namespace = closure_namespace(tmp_path, runtime_asset_map_id=0)
    argv = argument_argv_from_namespace(namespace)
    assert argv_values(argv)['runtime_asset_map_id'] == 0
    # Map zero is explicitly present, so it must not become an unbound env input.
    command = validation_plan.live_validate_command(
        {'id': 'combat_calibration', 'map_id': 0},
        output_root=tmp_path / 'output',
        timeout_sec=300, no_progress_window_sec=60,
    )
    assert command[command.index('--runtime-asset-map-id') + 1] == '0'
