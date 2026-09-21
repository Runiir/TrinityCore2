import argparse
import hashlib
import os
import re

import pytest

from tools.raid_program.runtime_asset_hash_cache import cached_hashes
from tools.raid_program.runtime_asset_launch import prepare_asset_arguments
from tools.raid_program.runtime_asset_safe_io import SafePathError, walk_inventory_no_follow


def test_map_filter_precedes_payload_hashing(tmp_path):
    (tmp_path / "0000001.map").write_bytes(b"selected")
    (tmp_path / "6690001.map").write_bytes(b"other" * 1000)
    with cached_hashes() as cache:
        rows = walk_inventory_no_follow(tmp_path, file_name_pattern=re.compile(r"000.*"))
    assert [r["path"] for r in rows] == ["0000001.map"]
    assert cache["bytes_hashed"] == len(b"selected")


@pytest.mark.parametrize("change", ["content", "restored_mtime", "replace", "mode"])
def test_persistent_hash_reuse_invalidates_changes(tmp_path, change):
    data = tmp_path / "data"
    data.mkdir()
    p = data / "tile"
    p.write_bytes(b"before")
    cache_path = tmp_path / "cache.sqlite"
    with cached_hashes(cache_path) as cold:
        walk_inventory_no_follow(data)
    with cached_hashes(cache_path) as warm:
        walk_inventory_no_follow(data)
    assert cold["bytes_hashed"] == 6
    assert warm["bytes_hashed"] == 0 and warm["hits"] == 1
    previous = p.stat()
    if change == "replace":
        q = data / "replacement"
        q.write_bytes(b"after!")
        q.replace(p)
    elif change == "mode":
        p.chmod(0o444)
    else:
        p.write_bytes(b"after!")
        if change == "restored_mtime":
            os.utime(p, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    with cached_hashes(cache_path) as changed:
        rows = walk_inventory_no_follow(data)
    assert changed["bytes_hashed"] == 6
    assert rows[0]["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()


def test_cached_tree_still_detects_added_removed_and_symlink_files(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    p = data / "a"
    p.write_bytes(b"original")
    with cached_hashes(tmp_path / "cache.sqlite"):
        walk_inventory_no_follow(data)
        p.unlink()
        (data / "b").write_bytes(b"new")
        assert [r["path"] for r in walk_inventory_no_follow(data)] == ["b"]
        p.symlink_to(data / "b")
        with pytest.raises(SafePathError, match="symlink"):
            walk_inventory_no_follow(data)


def test_calibration_derives_map_zero_and_defaults_without_temp_copies(tmp_path):
    config = tmp_path / "world.conf"
    config.write_text('DataDir = "data"\n')
    args = argparse.Namespace(calibration_only=True, config=config, output_dir=tmp_path / "out")
    prepare_asset_arguments(args, tmp_path)
    assert args.runtime_asset_map_id == 0
    assert args.runtime_asset_source_checkout == tmp_path
    assert args.runtime_asset_data_dir == tmp_path / "data"
    assert not args.output_dir.exists()
    args.runtime_asset_map_id = 669
    with pytest.raises(SystemExit, match="scenario_map_mismatch"):
        prepare_asset_arguments(args, tmp_path)


def test_encounter_uses_selected_route_map_and_rejects_conflicting_override(tmp_path):
    config = tmp_path / "world.conf"
    config.write_text('DataDir = "data"\n')
    args = argparse.Namespace(config=config, output_dir=tmp_path / "out")
    prepare_asset_arguments(args, tmp_path, {"map_id": 967})
    assert args.runtime_asset_map_id == 967
    with pytest.raises(SystemExit, match="scenario_map_mismatch"):
        prepare_asset_arguments(args, tmp_path, {"map_id": 669})


def test_unrelated_ancestor_sibling_change_does_not_invalidate_a_file(tmp_path, monkeypatch):
    from tools.raid_program import runtime_asset_safe_io as safe
    data = tmp_path / "data"
    data.mkdir()
    p = data / "tile"
    p.write_bytes(b"data")
    original = safe._recheck_path
    def recheck(path, **kwargs):
        (tmp_path / "unrelated").write_text("sibling")
        original(path, **kwargs)
    monkeypatch.setattr(safe, "_recheck_path", recheck)
    assert safe.read_regular_no_follow(p)[0] == b"data"


@pytest.mark.parametrize("map_id", [None, 669])
def test_production_cli_resolves_calibration_before_asset_or_server_work(tmp_path, monkeypatch, map_id):
    import sys
    from tools.bot_ml import run_live_bot_validation as live
    config = tmp_path / "world.conf"
    config.write_text('DataDir = "data"\n')
    output = tmp_path / "output"
    argv = ["run_live_bot_validation", "--config", str(config), "--output-dir", str(output),
            "--calibration-only", "--calibration-mode", "healer_controlled_damage_300",
            "--calibration-target-spec", "holy_paladin"]
    if map_id is not None:
        argv.extend(["--runtime-asset-map-id", str(map_id)])
    monkeypatch.setattr(sys, "argv", argv)
    def verify(args, **kwargs):
        assert map_id is None, "wrong map must fail before asset verification"
        assert args.runtime_asset_map_id == 0
        assert args.runtime_asset_data_dir == tmp_path / "data"
        assert args.runtime_asset_bundle.is_dir()
        raise SystemExit("fixture stops at real asset boundary")
    monkeypatch.setattr(live, "enforce_runtime_asset_closure_from_args", verify)
    with pytest.raises(SystemExit, match="scenario_map_mismatch" if map_id else "real asset boundary"):
        live.main()
    assert output.exists() is (map_id is None)


def test_production_cli_rejects_route_change_during_asset_verification(tmp_path, monkeypatch):
    import json
    import sys
    from tools.bot_ml import run_live_bot_validation as live
    config = tmp_path / "world.conf"
    config.write_text('DataDir = "data"\n')
    path = tmp_path / "validation_routes.jsonl"
    row = {"scenario_id": "fixture", "route_node_id": "boss", "map_id": 669}
    path.write_text(json.dumps(row) + "\n")
    monkeypatch.setattr(sys, "argv", ["run_live_bot_validation", "--config", str(config),
        "--output-dir", str(tmp_path / "out"), "--validation-scenario-dir", str(tmp_path),
        "--validation-scenario-id", "fixture", "--validation-route-node-id", "boss",
        "--duration-policy", "completion-watchdog"])
    def verify(args, **kwargs):
        assert args.runtime_asset_map_id == 669
        row["map_id"] = 967
        path.write_text(json.dumps(row) + "\n")
        return {}
    monkeypatch.setattr(live, "enforce_runtime_asset_closure_from_args", verify)
    with pytest.raises(SystemExit, match="route_input_changed"):
        live.main()
