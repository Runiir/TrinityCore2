"""Transport board points checked against client DBC geometry at the ready frame.

A transport route row boards a GAMEOBJECT_TYPE_TRANSPORT platform. Its board
point must lie on the platform at the frame the contract waits for: stop
frame n means GoState 25 + n (GO_STATE_TRANSPORT_STOPPED + n; scripts write
GO_STATE_TRANSPORT_ACTIVE + (n + 1)), which parks the platform at the
template's n-th stop time; a level contract names the origin height directly.
The platform origin at that frame is the stationary spawn plus the
TransportAnimation.dbc offset, and the model bounds come from
GameObjectDisplayInfo.dbc.
"""

from __future__ import annotations

import json
import math
import mmap
import struct
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
DBC = ROOT / "data/dbc/enUS"
TDB = ROOT / "data/TDB_full_434.22011_2022_01_09/TDB_full_world_434.22011_2022_01_09.sql"

# World DB rows (TDB 434.22011; no later sql/updates touch them). The live
# spawn z of the Onyxia platform is -6.86794: the 2016 sql/old row (+6.867935)
# was superseded. Summon data agrees: Onyxia (creature_summon_groups 41376,
# group 0) stands at -7.330293 on the lowered platform and group 1 at 6.571427
# on the raised one, both 0.46235 below the origin.
TRANSPORTS = {
    207834: {
        "template": b"(207834,11,10363,'Doodad_BlackWingV2_Elevator_Onyxia01','','','',1,13333,",
        "spawn": b"(235179,207834,669,5094,5094,15,0,1,169,0,-1,-107.213,-224.62,-6.86794,3.14159,",
        "spawn_id": 235179,
        "stationary": (-107.213, -224.62, -6.86794),
        "orientation": 3.14159,
        "display_id": 10363,
        "scale": 1.0,
        "stop_frame_times": [13333],
        "floor_offset": -7.330293 - -6.86794,
    },
    203716: {
        "template": b"(203716,11,10407,'Blackwing Descent Elevator','','','',1,0,",
        "spawn": b"(235178,203716,669,5094,5094,15,0,1,169,0,-1,-241.349,-224.605,186.551,0,",
        "spawn_id": 235178,
        "stationary": (-241.349, -224.605, 186.551),
        "orientation": 0.0,
        "display_id": 10407,
        "scale": 1.0,
        "stop_frame_times": [],
        # Flat elevator car: its walkable top is the model's upper bound.
        "floor_offset": None,
    },
}


def _dbc_records(name: str) -> tuple[int, int, bytes]:
    path = DBC / name
    if not path.exists():
        pytest.skip(f"{name} is not materialized locally")
    data = path.read_bytes()
    magic, count, fields, size, _ = struct.unpack("<4s4I", data[:20])
    assert magic == b"WDBC"
    return count, size, data[20:20 + count * size]


def _animation(entry: int) -> list[tuple[int, float]]:
    count, size, records = _dbc_records("TransportAnimation.dbc")
    keys = []
    for index in range(count):
        _, transport, time_index, _, _, z, _ = struct.unpack(
            "<IIIfffI", records[index * size:index * size + 28])
        if transport == entry:
            keys.append((time_index, z))
    return sorted(keys)


def _offset_at(keys: list[tuple[int, float]], time_ms: int) -> float:
    if time_ms <= keys[0][0]:
        return keys[0][1]
    for (t0, z0), (t1, z1) in zip(keys, keys[1:]):
        if time_ms <= t1:
            return z0 + (z1 - z0) * ((time_ms - t0) / (t1 - t0) if t1 > t0 else 1.0)
    return keys[-1][1]


def _geo_box(display_id: int) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    count, size, records = _dbc_records("GameObjectDisplayInfo.dbc")
    for index in range(count):
        record = records[index * size:(index + 1) * size]
        if struct.unpack("<I", record[:4])[0] == display_id:
            box = struct.unpack("<6f", record[12 * 4:18 * 4])
            return box[:3], box[3:]
    raise AssertionError(f"display {display_id} missing")


def _transport_rows() -> list[tuple[str, dict]]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    return [
        (scenario["id"], row)
        for group in ("scenarios", "diagnostic_scenarios")
        for scenario in config[group]
        for row in scenario["route"]
        if "transport_contract" in row
    ]


def test_pinned_transport_rows_match_the_world_database() -> None:
    if not TDB.exists():
        pytest.skip("TDB world dump is not materialized locally")
    with TDB.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as dump:
        for entry, source in TRANSPORTS.items():
            assert dump.find(source["template"]) >= 0, entry
            assert dump.find(source["spawn"]) >= 0, entry


def test_every_transport_board_point_lies_on_its_platform_at_the_ready_frame() -> None:
    rows = _transport_rows()
    # Full raid: lower-wing elevator and Nefarian platform; Nefarian shard.
    assert len(rows) == 3
    for scenario_id, row in rows:
        contract = row["transport_contract"]
        source = TRANSPORTS[contract["entry"]]
        assert contract["spawn_id"] == source["spawn_id"], scenario_id
        keys = _animation(contract["entry"])
        assert keys, contract["entry"]
        stationary_z = source["stationary"][2]
        if "board_stop_frame" in contract:
            frame = contract["board_stop_frame"]
            assert frame < len(source["stop_frame_times"]), (scenario_id, frame)
            ready_offset = _offset_at(keys, source["stop_frame_times"][frame])
        else:
            assert not source["stop_frame_times"]
            ready_offset = contract["board_transport_z"] - stationary_z
            assert any(abs(z - ready_offset) <= 1e-3 for _, z in keys), scenario_id
        origin = (source["stationary"][0], source["stationary"][1], stationary_z + ready_offset)

        (min_x, min_y, min_z), (max_x, max_y, max_z) = _geo_box(source["display_id"])
        bx, by, bz = contract["board_point"]
        dx, dy = bx - origin[0], by - origin[1]
        cos_o, sin_o = math.cos(source["orientation"]), math.sin(source["orientation"])
        local = (dx * cos_o + dy * sin_o, dy * cos_o - dx * sin_o, bz - origin[2])
        scale = source["scale"]
        assert min_x * scale <= local[0] <= max_x * scale, (scenario_id, local)
        assert min_y * scale <= local[1] <= max_y * scale, (scenario_id, local)
        assert min_z * scale <= local[2] <= max_z * scale, (scenario_id, local)

        floor = source["floor_offset"] if source["floor_offset"] is not None else max_z * scale
        assert bz == pytest.approx(origin[2] + floor, abs=0.01), (scenario_id, bz, origin[2] + floor)
        # The row anchor is where the node ends: the exit point of a ride,
        # otherwise the board point.
        anchor = contract.get("exit_point") or contract["board_point"]
        assert (row["x"], row["y"], row["z"]) == pytest.approx(tuple(anchor), abs=1e-4)


def test_nefarian_ready_frame_is_the_raised_platform() -> None:
    keys = _animation(207834)
    raised = TRANSPORTS[207834]["stationary"][2] + _offset_at(keys, 13333)
    assert raised == pytest.approx(7.03378, abs=1e-3)
    # Nefarian lands on the raised platform surface in phase one.
    assert raised + TRANSPORTS[207834]["floor_offset"] == pytest.approx(6.571427, abs=1e-3)


def test_lower_wing_elevator_exit_level_is_the_animation_bottom() -> None:
    keys = _animation(203716)
    bottom = min(z for _, z in keys)
    row = next(row for _, row in _transport_rows() if row["transport_contract"]["entry"] == 203716)
    contract = row["transport_contract"]
    assert contract["exit_transport_z"] == pytest.approx(
        TRANSPORTS[203716]["stationary"][2] + bottom, abs=1e-3)
