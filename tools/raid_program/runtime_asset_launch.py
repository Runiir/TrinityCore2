"""Derive asset arguments from the actual run, before any provisioning/launch."""
from pathlib import Path


def route_input_digest(args):
    if getattr(args, "input_log", None) or not getattr(args, "validation_scenario_id", None):
        return None
    import hashlib
    from tools.raid_program.runtime_asset_safe_io import read_regular_no_follow
    path = Path(args.validation_scenario_dir) / "validation_routes.jsonl"
    return hashlib.sha256(read_regular_no_follow(path)[0]).hexdigest() if path.exists() else None


def require_unchanged_route_input(args, digest):
    if route_input_digest(args) != digest:
        raise SystemExit("runtime_asset_route_input_changed: route changed during asset verification; retry with stable inputs")


def prepare_asset_arguments(args, root, route=None):
    if getattr(args, "input_log", None):
        return
    from tools.raid_program.runtime_asset_closure import data_dir_from_worldserver_config
    selected_map = 0 if getattr(args, "calibration_only", False) else (route or {}).get("map_id")
    if selected_map is None:
        return  # Older callers without a selected scenario still supply explicit arguments.
    if isinstance(selected_map, bool) or not isinstance(selected_map, int) or selected_map < 0:
        raise SystemExit("runtime_asset_scenario_map_invalid")
    supplied = getattr(args, "runtime_asset_map_id", None)
    if supplied is not None and supplied != selected_map:
        raise SystemExit(f"runtime_asset_scenario_map_mismatch: run={selected_map}, supplied={supplied}; do not verify a different map")
    args.config = Path(args.config).absolute()
    defaults = {
        "runtime_asset_map_id": selected_map,
        "runtime_asset_closure_manifest": root / "experiments/configs/runtime_asset_input_closure_manifest_v1.json",
        "runtime_asset_source_checkout": root,
        "runtime_asset_dvc_workspace": root,
        "runtime_asset_bundle": Path(args.output_dir).absolute(),
        "runtime_asset_data_dir": data_dir_from_worldserver_config(args.config),
    }
    for key, value in defaults.items():
        if getattr(args, key, None) is None:
            setattr(args, key, value)
