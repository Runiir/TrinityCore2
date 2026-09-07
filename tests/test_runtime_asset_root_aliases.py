import json
from pathlib import Path

import pytest

from tools.raid_program.runtime_asset_closure import _expected_map_values
from tools.raid_program.runtime_asset_root_aliases import find_root_contract_conflicts


ROOT = Path(__file__).resolve().parents[1]


def _classes():
    return [
        {"id": "offline", "root": "source", "expected_mode": "0444",
         "expected_files": [{"path": "data/mmaps/669.mmap", "sha256": "same"}]},
        {"id": "native", "root": "data", "expected_mode": "0664",
         "expected_files": [{"path": "mmaps/669.mmap", "sha256": "same"}]},
    ]


def test_contradictory_alias_is_reported_before_files_exist(tmp_path):
    issues = find_root_contract_conflicts(_classes(), {"source": tmp_path, "data": tmp_path / "data"})
    assert len(issues) == 1
    assert issues[0]["detail"] == "aliased_root_contract"
    assert issues[0]["conflicts"] == {"mode": {"offline": "0444", "native": "0664"}}
    assert not list(tmp_path.iterdir())


def test_independent_source_and_native_copies_allow_different_modes(tmp_path):
    assert not find_root_contract_conflicts(_classes(), {"source": tmp_path / "source", "data": tmp_path / "data"})


def test_equivalent_alias_requirements_are_allowed(tmp_path):
    classes = _classes()
    classes[0]["expected_mode"] = "0664"
    assert not find_root_contract_conflicts(classes, {"source": tmp_path, "data": tmp_path / "data"})


@pytest.mark.parametrize("field,value", [("sha256", "different"), ("size_bytes", 2), ("type", "directory")])
def test_conflicting_explicit_content_requirements(tmp_path, field, value):
    classes = _classes()
    classes[0]["expected_mode"] = "0664"
    classes[0]["expected_files"][0][field] = 1 if field == "size_bytes" else "file" if field == "type" else "same"
    classes[1]["expected_files"][0][field] = value
    assert field in find_root_contract_conflicts(classes, {"source": tmp_path, "data": tmp_path / "data"})[0]["conflicts"]


def test_current_map_contract_exposes_all_eight_permission_conflicts(tmp_path):
    manifest = json.loads((ROOT / "experiments/configs/runtime_asset_closure_manifest_v1.json").read_text())
    selected = [_expected_map_values(row, 669) for row in manifest["asset_classes"]]
    roots = {"source-checkout": tmp_path, "configured-DataDir": tmp_path / "data",
             "dvc-workspace": tmp_path, "sealed-bundle": tmp_path / "bundle"}
    issues = find_root_contract_conflicts(selected, roots)
    assert len(issues) == 8
    assert all(set(row["conflicts"]) == {"mode"} for row in issues)
    assert all(set(row["class_ids"]) == {"selected_map_navmesh_offline", "selected_map_navmesh_native"} for row in issues)


@pytest.mark.parametrize("path", ["../escape", "/absolute", "."])
def test_unsafe_relative_paths_rejected(tmp_path, path):
    classes = _classes()
    classes[0]["expected_files"][0]["path"] = path
    with pytest.raises(ValueError, match="unsafe_expected_asset_path"):
        find_root_contract_conflicts(classes, {"source": tmp_path, "data": tmp_path / "data"})


@pytest.mark.parametrize("rows", [None, {}, "file", [{}], [None], [{"path": 4}]])
def test_malformed_manifest_returns_catchable_validation_error(tmp_path, rows):
    classes = _classes()
    classes[0]["expected_files"] = rows
    with pytest.raises(ValueError, match="expected_file"):
        find_root_contract_conflicts(classes, {"source": tmp_path, "data": tmp_path / "data"})
