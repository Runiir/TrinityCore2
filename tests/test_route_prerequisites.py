import json
import sys
from pathlib import Path

import pytest

from tools.bot_ml.route_prerequisites import require_route_prerequisites
from tools.bot_ml import run_live_bot_validation as live
from tools.bot_ml.build_validation_run_plan import build_plan


def routes(scenario="example_raid"):
    return [dict(scenario_id=scenario, runtime_profile_id=scenario,
                 route_node_id=f"node_{i}", step=i, kind=kind, label=kind)
            for i, kind in enumerate(("regroup", "trash", "trash", "boss"), 1)]


def check(rows, **kwargs):
    options = dict(scenario_id=rows[0]["scenario_id"], selected=rows[-1],
                   routes=rows, explicit_selection=True, full_manifest=False,
                   separate_sequence=False)
    options.update(kwargs)
    require_route_prerequisites(**options)


def test_boss_and_later_trash_require_predecessors():
    rows = routes()
    for selected in rows[1:]:
        with pytest.raises(ValueError, match="route prerequisites not established"):
            check(rows, selected=selected)


def test_full_manifest_and_standalone_scenario_are_valid():
    check(routes(), selected={}, explicit_selection=False, full_manifest=True)
    check(routes()[:1])
    check(routes()[-1:])  # A separately defined scenario, not a caller's filtered list.


def test_full_manifest_cannot_keep_boss_only_context():
    with pytest.raises(ValueError, match="cannot be combined"):
        check(routes(), full_manifest=True)


def test_descriptive_prerequisite_claim_does_not_bypass_live_state():
    rows = routes()
    rows[-1]["diagnostic_prerequisite_state"] = {"certifies_predecessors": True}
    with pytest.raises(ValueError, match="route prerequisites not established"):
        check(rows)


def test_offline_report_reparse_preserves_historical_evidence():
    check(routes(), offline=True)


def test_unknown_selector_fails():
    with pytest.raises(ValueError, match="did not resolve"):
        check(routes(), selected={})


def test_plan_does_not_advertise_later_segment_as_executable():
    scenario = "example_raid"
    plan = build_plan([{"scenario_id": scenario}], Path("runs"), Path("reports"),
                      Path("scenarios"), None, 900,
                      routes_by_scenario={scenario: routes(scenario)})
    row = plan["scenarios"][0]
    boss = row["segments"][-1]
    assert boss["coordinates_valid"] is True
    assert boss["executable"] is False
    assert boss["skip_reason"] == "route_prerequisites_not_established"
    assert boss["prerequisite_route_node_ids"] == ["node_1", "node_2", "node_3"]
    assert boss["prerequisite_run_command"] == row["live_validate_command"]
    assert "--validation-route-manifest" in boss["prerequisite_run_command"]
    assert "--validation-segment-id" not in boss["prerequisite_run_command"]


@pytest.mark.parametrize("scenario", ["blackwing_descent_10n_magmaw_diagnostic", "another_dungeon"])
def test_cli_rejects_before_assets_provisioning_or_output(tmp_path, monkeypatch, scenario):
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "validation_routes.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in routes(scenario)))
    output = tmp_path / "run"
    monkeypatch.setattr(sys, "argv", ["bot-live-validate", "--dry-run",
        "--validation-scenario-id", scenario, "--validation-route-node-id", "node_4",
        "--validation-scenario-dir", str(scenario_dir), "--output-dir", str(output)])
    def forbidden(*args, **kwargs):
        pytest.fail("invalid route reached runtime asset admission")
    monkeypatch.setattr(live, "enforce_runtime_asset_closure_from_args", forbidden)
    with pytest.raises(SystemExit, match="route prerequisites not established"):
        live.main()
    assert not output.exists()
