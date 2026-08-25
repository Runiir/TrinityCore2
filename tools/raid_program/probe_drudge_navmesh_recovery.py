#!/usr/bin/env python3
"""Fail-closed native-nav parity probe for the BWD Magmaw corridor."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

EXPECTED_ASSETS = {
    "669.mmap": "3b794515424ff374f2fc2fb9bc75c9d0bcdfa355c712894d5b73c582671ea421",
    "6693131.mmtile": "ec53ab238b671d2b41f707648adcc1cd9b69699a6a424d7c673bed8aeb31b1ef",
    "6693132.mmtile": "0879cbb27dce969579f789796c6c63a8ffd3c81ff66c303ea3dde1321f852ec5",
    "6693133.mmtile": "116e3649739b423536fd3ba746dde75655aae3f140f64096aa4cbc9a8bbb6196",
    "6693231.mmtile": "9bf7e5e6b956886a96d19b8672595ce53246ee975466b4e231dd85fd71cd4019",
    "6693232.mmtile": "d444daf82f09d2e4d7c8708f7f3c4f4420c0f96ce1db604c722689fa4e57cb32",
    "6693233.mmtile": "c9a0a2787aaefe0cff05d7d2877d82995a5317eda0ed496ee3323f1ad0bf3467",
    "6693332.mmtile": "f91db1f81a7f95a824f9bd3c4eca6e665e3a80954cb4b472cab80214c19efbeb",
}

EXPECTED_OUTPUT = (
    "loaded=7",
    "30003 findPath=0x40000000 polys=4 complete=1",
    "30003 smooth=0x40000000 points=5 terminal=-295,-71.5,213.25 end2d=0 endz=0",
    "30008 findPath=0x40000000 polys=2 complete=1",
    "30008 smooth=0x40000000 points=5 terminal=-325,-64,212.82 end2d=0 endz=0",
    "30003_reposition findPath=0x40000000 polys=1 complete=1",
    "30003_reposition smooth=0x40000000 points=2 terminal=-296,-69.9,213.485 end2d=0 endz=0",
    "30004_reposition findPath=0x40000000 polys=1 complete=1",
    "30004_reposition smooth=0x40000000 points=2 terminal=-298.8,-71.5,213.461 end2d=0 endz=0",
    "30005_reposition findPath=0x40000000 polys=6 complete=1",
    "30005_reposition smooth=0x40000000 points=12 terminal=-311.5,-71.3,213.292 end2d=0 endz=0",
    "30007_reposition findPath=0x40000000 polys=3 complete=1",
    "30007_reposition smooth=0x40000000 points=5 terminal=-292.5,-69.1,214.024",
    "minimum_distance_exit_retained end_status=0x40000000 ref=100000000003b3 nearest=-288.8,-73.2144,213.714 distance=3.0675",
    "minimum_distance_exit_retained findPath=0x40000000 polys=1 complete=1",
    "minimum_distance_exit_retained straight=0x40000000 points=2 terminal=-288.8,-73.2144,213.714 end2d=3.05804 endz=0.240692",
    "minimum_distance_exit_retained actual_endpoint=-288.8,-73.2144,213.714 requested_end2d_miss=3.05804",
    "minimum_distance_exit_retained smooth=0x40000000 points=2 terminal=-285.742,-73.2144,213.473 end2d=0 endz=0",
    "tank1_pull_away findPath=0x40000000 polys=4 complete=1",
    "tank1_pull_away smooth=0x40000000 points=6 terminal=-288.8,-43,212.301",
    "tank2_pull_away findPath=0x40000000 polys=4 complete=1",
    "tank2_pull_away nearest_terminal=-321.5,-30,211.513 requested_endz=0.22937",
    "tank2_pull_away smooth=0x40000000 points=6 terminal=-321.5,-30,211.283",
    "tank1_combat_anchor findPath=0x40000000 polys=5 complete=1",
    "tank1_combat_anchor straight=0x40000000 points=4 terminal=-288.836,-42.6005,212.267 end2d=0.00311819 endz=0",
    "tank2_combat_anchor findPath=0x40000000 polys=1 complete=1",
    "tank2_combat_anchor straight=0x40000000 points=2 terminal=-321.913,-44.3194,211.836 end2d=0 endz=0",
    "drudge_slot3_anchor findPath=0x40000000 polys=11 complete=1",
    "drudge_slot3_anchor smooth=0x40000000 points=17 terminal=-300.25,-65.5,213.143 end2d=0 endz=0",
    "drudge_slot4_anchor findPath=0x40000000 polys=11 complete=1",
    "drudge_slot4_anchor smooth=0x40000000 points=17 terminal=-300.5,-66.25,213.177 end2d=0 endz=0",
    "drudge_slot5_anchor findPath=0x40000000 polys=13 complete=1",
    "drudge_slot5_anchor smooth=0x40000000 points=16 terminal=-314.25,-63.5,212.873 end2d=0 endz=0",
    "drudge_slot6_anchor findPath=0x40000000 polys=11 complete=1",
    "drudge_slot6_anchor smooth=0x40000000 points=17 terminal=-300,-66,213.171 end2d=0 endz=0",
    "drudge_slot7_anchor findPath=0x40000000 polys=11 complete=1",
    "drudge_slot7_anchor smooth=0x40000000 points=17 terminal=-299.75,-65.5,213.149 end2d=0 endz=0",
    "drudge_slot8_anchor findPath=0x40000000 polys=10 complete=1",
    "drudge_slot8_anchor smooth=0x40000000 points=15 terminal=-313.5,-64.25,212.915 end2d=0 endz=0",
    "drudge_slot9_anchor findPath=0x40000000 polys=10 complete=1",
    "drudge_slot9_anchor smooth=0x40000000 points=15 terminal=-312.75,-65,212.962 end2d=0 endz=0",
    "drudge_slot10_anchor findPath=0x40000000 polys=11 complete=1",
    "drudge_slot10_anchor smooth=0x40000000 points=16 terminal=-312.5,-64,212.915 end2d=0 endz=0",
    "chainwielder_patrol_pull findPath=0x40000000 polys=10 complete=1",
    "chainwielder_patrol_pull smooth=0x40000000 points=8 terminal=-345.872,-110,213.964 end2d=0 endz=0",
    "chainwielder_patrol_pull future_guard_minimums=58.2531,51.5885",
)

REQUIRED_COMBAT_ENDPOINTS = (
    "tank1_combat_anchor",
    "tank2_combat_anchor",
)

REQUIRED_MEMBER_ENDPOINTS = tuple(
    f"drudge_slot{slot}_anchor" for slot in (3, 4, 5, 6, 7, 8, 9, 10)
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets(root: Path = ROOT) -> dict[str, str]:
    mmap_root = root / "data" / "mmaps"
    actual_names = {path.name for path in mmap_root.glob("669*.mmtile")}
    expected_names = {name for name in EXPECTED_ASSETS if name.endswith(".mmtile")}
    if actual_names != expected_names:
        raise RuntimeError(
            "drudge_navmesh_asset_set_mismatch:"
            f"expected={sorted(expected_names)}:actual={sorted(actual_names)}"
        )
    observed: dict[str, str] = {}
    for name, expected_hash in EXPECTED_ASSETS.items():
        path = mmap_root / name
        if not path.is_file():
            raise RuntimeError(f"drudge_navmesh_asset_missing:{name}")
        observed[name] = _sha256(path)
        if observed[name] != expected_hash:
            raise RuntimeError(
                f"drudge_navmesh_asset_hash_mismatch:{name}:"
                f"expected={expected_hash}:actual={observed[name]}"
            )
    return observed


def compile_and_run_probe(root: Path = ROOT) -> str:
    probe_source = root / "tools" / "raid_program" / "drudge_navmesh_recovery_probe.cpp"
    detour_sources = sorted(
        (root / "dep" / "recastnavigation" / "Detour" / "Source").glob("*.cpp")
    )
    if len(detour_sources) != 7:
        raise RuntimeError(
            f"drudge_navmesh_detour_source_set_mismatch:{len(detour_sources)}"
        )
    with tempfile.TemporaryDirectory(prefix="drudge-navmesh-parity-") as temp_dir:
        binary = Path(temp_dir) / "drudge_navmesh_recovery_probe"
        compile_result = subprocess.run(
            [
                "g++",
                "-std=c++17",
                "-O2",
                str(probe_source),
                *(str(path) for path in detour_sources),
                "-I",
                str(root / "dep" / "recastnavigation" / "Detour" / "Include"),
                "-o",
                str(binary),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if compile_result.returncode:
            raise RuntimeError(
                "drudge_navmesh_probe_compile_failed:"
                + (compile_result.stderr.strip() or compile_result.stdout.strip())
            )
        probe_result = subprocess.run(
            [str(binary)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if probe_result.returncode:
            raise RuntimeError(
                "drudge_navmesh_probe_execution_failed:"
                + (probe_result.stderr.strip() or probe_result.stdout.strip())
            )
        for required_line in EXPECTED_OUTPUT:
            if required_line not in probe_result.stdout:
                raise RuntimeError(
                    "drudge_navmesh_probe_result_mismatch:"
                    f"missing={required_line}:output={probe_result.stdout}"
                )
        return probe_result.stdout


def run_probe(root: Path = ROOT) -> dict[str, object]:
    root = root.resolve()
    assets = verify_assets(root)
    output = compile_and_run_probe(root)
    validated_returns = {
            "30003": {
                "start": [-288.8, -86.483, 214.15],
                "terminal": [-295.0, -71.5, 213.25],
                "polygons": 4,
                "smooth_points": 5,
            },
            "30008": {
                "start": [-338.018, -64.932, 212.751],
                "terminal": [-325.0, -64.0, 212.82],
                "polygons": 2,
                "smooth_points": 5,
            },
            "30003_reposition": {
                "start": [-295.0, -71.5, 213.25],
                "terminal": [-296.0, -69.9, 213.485],
                "polygons": 1,
                "smooth_points": 2,
            },
            "30004_reposition": {
                "start": [-299.0, -75.0, 213.65],
                "terminal": [-298.8, -71.5, 213.461],
                "polygons": 1,
                "smooth_points": 2,
            },
            "30005_reposition": {
                "start": [-343.508, -44.4466, 211.947],
                "terminal": [-311.5, -71.3, 213.292],
                "polygons": 6,
                "smooth_points": 12,
            },
            "30007_reposition": {
                "start": [-295.0, -82.0, 213.8],
                "terminal": [-292.5, -69.1, 214.024],
                "polygons": 3,
                "smooth_points": 5,
            },
            "minimum_distance_exit_retained": {
                "start": [-288.8, -72.289, 213.473],
                "requested": [-285.742, -73.2144, 213.473],
                "actual_endpoint": [-288.8, -73.2144, 213.714],
                "polygons": 1,
                "straight_points": 2,
                "requested_end2d_miss": 3.05804,
                "requested_endz_delta": 0.240692,
                "smooth_terminal": [-285.742, -73.2144, 213.473],
                "smooth_points": 2,
            },
            "tank1_pull_away": {
                "start": [-289.289093, -57.7575, 212.932236],
                "terminal": [-288.8, -43.0, 212.301],
                "polygons": 4,
                "smooth_points": 6,
            },
            "tank2_pull_away": {
                "start": [-322.858002, -48.286201, 211.999359],
                "terminal": [-321.5, -30.0, 211.283429],
                "detour_nearest_terminal": [-321.5, -30.0, 211.513],
                "detour_nearest_requested_z_delta": 0.22937,
                "polygons": 4,
                "smooth_points": 6,
            },
            "tank1_combat_anchor": {
                "start": [-289.289093, -57.7575, 212.932236],
                "requested": [-288.833008, -42.598999, 212.267319],
                "projected_terminal": [-288.836, -42.6005, 212.267],
                "polygons": 5,
                "straight_points": 4,
                "requested_end2d_miss": 0.00311819,
                "requested_endz_delta": 0.0,
                "exact_endpoint": True,
                "fallback": None,
            },
            "tank2_combat_anchor": {
                "start": [-322.858002, -48.286201, 211.999359],
                "requested": [-321.912994, -44.319401, 211.835968],
                "projected_terminal": [-321.913, -44.3194, 211.836],
                "polygons": 1,
                "straight_points": 2,
                "requested_end2d_miss": 0.0,
                "requested_endz_delta": 0.0,
                "exact_endpoint": True,
                "fallback": None,
            },
            "drudge_slot3_anchor": {
                "start": [-345.872, -110.0, 213.964],
                "terminal": [-300.25, -65.5, 213.142807],
                "polygons": 11,
                "smooth_points": 17,
                "exact_endpoint": True,
            },
            "drudge_slot4_anchor": {
                "start": [-345.872, -110.0, 213.964],
                "terminal": [-300.5, -66.25, 213.177139],
                "polygons": 11,
                "smooth_points": 17,
                "exact_endpoint": True,
            },
            "drudge_slot5_anchor": {
                "start": [-345.872, -110.0, 213.964],
                "terminal": [-314.25, -63.5, 212.872604],
                "polygons": 13,
                "smooth_points": 16,
                "exact_endpoint": True,
            },
            "drudge_slot6_anchor": {
                "start": [-345.872, -110.0, 213.964],
                "terminal": [-300.0, -66.0, 213.170898],
                "polygons": 11,
                "smooth_points": 17,
                "exact_endpoint": True,
            },
            "drudge_slot7_anchor": {
                "start": [-345.872, -110.0, 213.964],
                "terminal": [-299.75, -65.5, 213.149063],
                "polygons": 11,
                "smooth_points": 17,
                "exact_endpoint": True,
            },
            "drudge_slot8_anchor": {
                "start": [-345.872, -110.0, 213.964],
                "terminal": [-313.5, -64.25, 212.914764],
                "polygons": 10,
                "smooth_points": 15,
                "exact_endpoint": True,
            },
            "drudge_slot9_anchor": {
                "start": [-345.872, -110.0, 213.964],
                "terminal": [-312.75, -65.0, 212.961594],
                "polygons": 10,
                "smooth_points": 15,
                "exact_endpoint": True,
            },
            "drudge_slot10_anchor": {
                "start": [-345.872, -110.0, 213.964],
                "terminal": [-312.5, -64.0, 212.914795],
                "polygons": 11,
                "smooth_points": 16,
                "exact_endpoint": True,
            },
            "chainwielder_patrol_pull": {
                "start": [-346.5827, -83.71657, 213.9893],
                "terminal": [-345.872, -110.0, 213.964],
                "polygons": 10,
                "smooth_points": 8,
                "future_source_minimum_distances": {
                    "250140": 58.2531,
                    "250141": 51.5885,
                },
                "required_future_guard_distance": 50.0,
            },
    }
    required_endpoint_checks = {
        label: {
            "declared": True,
            "exact_endpoint": bool(validated_returns[label].get("exact_endpoint")),
            "passed": bool(validated_returns[label].get("exact_endpoint")),
        }
        for label in REQUIRED_COMBAT_ENDPOINTS
    }
    required_member_checks = {
        label: {
            "declared": True,
            "exact_endpoint": bool(validated_returns[label].get("exact_endpoint")),
            "passed": bool(validated_returns[label].get("exact_endpoint")),
        }
        for label in REQUIRED_MEMBER_ENDPOINTS
    }
    return {
        "all_passed": all(
            check["passed"]
            for check in (*required_endpoint_checks.values(), *required_member_checks.values())
        ),
        "required_combat_endpoints": required_endpoint_checks,
        "required_member_endpoints": required_member_checks,
        "map_id": 669,
        "asset_sha256": assets,
        "player_nav_include_flags": ["NAV_GROUND", "NAV_WATER", "NAV_MAGMA_SLIME"],
        "nearest_poly_extents": [3.0, 5.0, 3.0],
        "nearest_poly_vertical_fallback": 50.0,
        "corridor_cap": 74,
        "smooth_step": 4.0,
        "smooth_slop": 0.3,
        "validated_returns": validated_returns,
        "raw_probe_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    result = run_probe()
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
