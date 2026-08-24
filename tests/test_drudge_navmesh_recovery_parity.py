import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.raid_program.probe_drudge_navmesh_recovery import verify_assets


ROOT = Path(__file__).parents[1]
MMAP = ROOT / "data" / "mmaps" / "669.mmap"


def test_missing_navmesh_assets_fail_closed(tmp_path):
    with pytest.raises(RuntimeError, match="drudge_navmesh_asset_set_mismatch"):
        verify_assets(tmp_path)


def test_capture_runs_navmesh_probe_before_worldserver_start():
    source = (
        ROOT / "tools" / "raid_program" / "capture_phase1_raid_foundation.py"
    ).read_text(encoding="utf-8")
    preflight = source.index("_drudge_navmesh_probe(worktree)")
    process_start = source.index("subprocess.Popen(", preflight)
    assert preflight < process_start
    assert '"drudge_navmesh_preflight": drudge_navmesh_preflight' in source


@pytest.mark.skipif(not MMAP.is_file(), reason="authoritative map-669 mmap assets unavailable")
def test_recorded_drudge_returns_match_native_navmesh(tmp_path):
    report = tmp_path / "drudge_navmesh_recovery.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "raid_program" / "probe_drudge_navmesh_recovery.py"),
            "--json-out",
            str(report),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["all_passed"] is True
    assert payload["map_id"] == 669
    assert payload["player_nav_include_flags"] == [
        "NAV_GROUND",
        "NAV_WATER",
        "NAV_MAGMA_SLIME",
    ]
    assert payload["validated_returns"]["30003"]["terminal"] == [
        -295.0,
        -71.5,
        213.25,
    ]
    assert payload["validated_returns"]["30008"]["terminal"] == [
        -325.0,
        -64.0,
        212.82,
    ]
    assert payload["validated_returns"]["30003_reposition"] == {
        "polygons": 1,
        "smooth_points": 2,
        "start": [-295.0, -71.5, 213.25],
        "terminal": [-296.0, -69.9, 213.485],
    }
    assert payload["validated_returns"]["30004_reposition"] == {
        "polygons": 1,
        "smooth_points": 2,
        "start": [-299.0, -75.0, 213.65],
        "terminal": [-298.8, -71.5, 213.461],
    }
    assert payload["validated_returns"]["30005_reposition"] == {
        "polygons": 6,
        "smooth_points": 12,
        "start": [-343.508, -44.4466, 211.947],
        "terminal": [-311.5, -71.3, 213.292],
    }
    assert payload["validated_returns"]["30007_reposition"] == {
        "polygons": 3,
        "smooth_points": 5,
        "start": [-295.0, -82.0, 213.8],
        "terminal": [-292.5, -69.1, 214.024],
    }
    assert payload["validated_returns"]["minimum_distance_exit_retained"] == {
        "actual_endpoint": [-288.8, -73.2144, 213.714],
        "polygons": 1,
        "requested": [-285.742, -73.2144, 213.473],
        "requested_end2d_miss": 3.05804,
        "requested_endz_delta": 0.240692,
        "smooth_points": 2,
        "smooth_terminal": [-285.742, -73.2144, 213.473],
        "start": [-288.8, -72.289, 213.473],
        "straight_points": 2,
    }
    assert payload["validated_returns"]["tank1_pull_away"] == {
        "polygons": 4,
        "smooth_points": 6,
        "start": [-289.289093, -57.7575, 212.932236],
        "terminal": [-288.8, -43.0, 212.301],
    }
    assert payload["validated_returns"]["tank2_pull_away"] == {
        "polygons": 4,
        "smooth_points": 6,
        "start": [-322.858002, -48.286201, 211.999359],
        "terminal": [-321.5, -30.0, 211.283429],
        "detour_nearest_terminal": [-321.5, -30.0, 211.513],
        "detour_nearest_requested_z_delta": 0.22937,
    }
    assert payload["validated_returns"]["tank1_combat_anchor"] == {
        "exact_endpoint": False,
        "fallback": "tank1_navigation_anchor",
        "polygons": 1,
        "projected_terminal": [-289.289, -57.7575, 212.932],
        "requested": [-286.5, -58.0, 212.2983],
        "requested_end2d_miss": 2.79962,
        "requested_endz_delta": 0.633942,
        "start": [-289.289093, -57.7575, 212.932236],
        "straight_points": 1,
    }
    assert payload["validated_returns"]["tank2_combat_anchor"] == {
        "exact_endpoint": True,
        "fallback": None,
        "polygons": 1,
        "projected_terminal": [-322.858, -48.2862, 212.262],
        "requested": [-322.858, -48.2862, 212.2623],
        "requested_end2d_miss": 0.0,
        "requested_endz_delta": 0.0,
        "start": [-322.858002, -48.286201, 211.999359],
        "straight_points": 2,
    }
    assert payload["validated_returns"]["chainwielder_patrol_pull"] == {
        "start": [-346.5827, -83.71657, 213.9893],
        "terminal": [-345.872, -110.0, 213.964],
        "polygons": 10,
        "smooth_points": 8,
        "future_source_minimum_distances": {
            "250140": 58.2531,
            "250141": 51.5885,
        },
        "required_future_guard_distance": 50.0,
    }
