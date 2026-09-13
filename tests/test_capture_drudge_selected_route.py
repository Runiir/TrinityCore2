"""Exercise capture setup with declared generic and split Drudge routes."""
import json
from pathlib import Path

import pytest

from tools.raid_program import capture_setup as setup
from tools.raid_program.capture_drudge_geometry import _frozen_drudge_member_anchors
from tools.raid_program.probe_drudge_navmesh_recovery import verify_route_anchors

ROOT = Path(__file__).resolve().parents[1]


def test_actual_setup_selects_drudge_preflight_by_declared_mechanic(tmp_path, monkeypatch):
    for name in ("worldserver", "worldserver.conf", "build.json"):
        (tmp_path / name).write_text("fixture")
    document = json.loads((ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text())
    diagnostic = next(row for row in document["diagnostic_scenarios"] if row["id"].endswith("magmaw_diagnostic"))
    canonical = next(row for row in document["scenarios"] if row["id"] == "blackwing_descent_10n")
    route = tmp_path / "routes.jsonl"
    def write_route(nodes):
        route.write_text("".join(json.dumps({**node, "scenario_id": diagnostic["id"]})+"\n" for node in nodes))
    write_route(diagnostic["route"])
    monkeypatch.setattr(setup, "enforce_runtime_asset_closure_from_args", lambda *a, **k: {"complete": True})
    monkeypatch.setattr(setup, "trinity_config_bool", lambda *a, **k: False)
    monkeypatch.setattr(setup, "development_run_canonical_rejections", lambda *a, **k: [])
    monkeypatch.setattr(setup, "preflight_runtime_exclusions", lambda *a, **k: {"passed": True, "reasons": []})
    monkeypatch.setattr(setup, "git_identity", lambda *a, **k: {"clean": True, "commit": "a"*40})
    monkeypatch.setattr(setup, "validate_runtime_profile_assets", lambda *a, **k: {"passed": True, "reasons": [], "route_manifest": str(route)})
    monkeypatch.setattr(setup, "build_policy_path_for_receipt", lambda *a, **k: tmp_path / "policy.json")
    monkeypatch.setattr(setup, "validate_build_receipt", lambda *a, **k: {"valid": True, "rejections": []})
    calls = []
    def probe(worktree):
        calls.append(worktree)
        raise RuntimeError("native_probe_negative")
    monkeypatch.setattr(setup, "_drudge_navmesh_probe", probe)
    args = ["--binary", str(tmp_path/"worldserver"), "--config", str(tmp_path/"worldserver.conf"),
            "--build-receipt", str(tmp_path/"build.json"), "--output", str(tmp_path/"result.json"),
            "--worktree", str(tmp_path), "--runtime-profile", diagnostic["id"], "--scenario-id", diagnostic["id"], "--pool-tag", diagnostic["id"], "--development-run"]
    result = setup.prepare_capture_setup(args, root=tmp_path)
    assert not result.drudge_observed and not calls
    assert result.drudge_frozen_anchors == {}
    write_route(canonical["route"][:4])
    with pytest.raises(SystemExit, match="native_probe_negative"):
        setup.prepare_capture_setup(args, root=tmp_path)
    assert len(calls) == 1
    monkeypatch.setattr(setup, "_drudge_navmesh_probe", lambda _: {"all_passed": True})
    result = setup.prepare_capture_setup(args, root=tmp_path)
    assert result.drudge_observed and set(result.drudge_frozen_anchors) == set(range(1, 11))
    nodes = json.loads(json.dumps(canonical["route"][:4]))
    nodes[2]["split_recovery_member_anchors"] = []
    write_route(nodes)
    with pytest.raises(SystemExit, match="drudge_frozen_member_anchors_missing"):
        setup.prepare_capture_setup(args, root=tmp_path)


def test_canonical_split_navmesh_anchor_checks_survive_generic_diagnostic():
    anchors = verify_route_anchors(ROOT)
    assert set(anchors) == {str(i) for i in range(1, 11)}
    catalog = ROOT / "dataset/validation_scenarios/validation_routes.jsonl"
    assert len(_frozen_drudge_member_anchors(catalog, "blackwing_descent_10n")) == 10
    assert _frozen_drudge_member_anchors(catalog, "blackwing_descent_10n_magmaw_diagnostic") == {}
