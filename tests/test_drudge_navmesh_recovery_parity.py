import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MMAP = ROOT / "data" / "mmaps" / "669.mmap"


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
