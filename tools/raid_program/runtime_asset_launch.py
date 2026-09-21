"""Derive asset arguments from the actual run, before any provisioning/launch."""
from pathlib import Path


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
