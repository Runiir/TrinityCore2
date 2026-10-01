"""Decode addon-visible movement state from a screenshot, without client memory access."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct


MAGIC = b"TCM1"
PACKET = struct.Struct(">4sIIIHHHHBBH")
COLUMNS, ROWS, CELL_SIZE = 28, 8, 4
FLAGS = {"in_world": 1, "position_available": 2, "in_combat": 4, "dead": 8, "on_taxi": 16}


def checksum(data: bytes) -> int:
    first = second = 0
    for value in data:
        first = (first + value) % 255
        second = (second + first) % 255
    return second * 256 + first


def decode_packet(data: bytes) -> dict:
    if len(data) != PACKET.size:
        raise ValueError("movement telemetry packet has the wrong length")
    magic, sequence, uptime_ms, map_id, x, y, facing, speed, health, flags, check = PACKET.unpack(data)
    if magic != MAGIC:
        raise ValueError("movement telemetry marker is missing")
    if checksum(data[:-2]) != check:
        raise ValueError("movement telemetry checksum mismatch; frame may be incomplete")
    if health > 100 or flags & ~sum(FLAGS.values()):
        raise ValueError("movement telemetry contains invalid flags or health")
    status = {name: bool(flags & mask) for name, mask in FLAGS.items()}
    return {
        "schema": "client_movement_observation_v1",
        "sequence": sequence,
        "client_uptime_ms": uptime_ms,
        "map_id": map_id if status["position_available"] else None,
        "position": {"x": x / 65535, "y": y / 65535, "basis": "normalized_map"}
        if status["position_available"] else None,
        "facing_radians": facing / 65535 * math.tau,
        "speed": speed / 100,
        "health_percent": health,
        **status,
        "source": "addon_rendered_pixels",
    }


def decode_image(image, *, x: float, y: float, cell_size: float = CELL_SIZE) -> dict:
    if x < 0 or y < 0 or cell_size < 1:
        raise ValueError("panel coordinates and cell size must be nonnegative/positive")
    if x + COLUMNS * cell_size > image.width or y + ROWS * cell_size > image.height:
        raise ValueError("telemetry panel falls outside the screenshot")
    rgb = image.convert("RGB")
    bits = []
    for index in range(PACKET.size * 8):
        px = int(x + (index % COLUMNS + .5) * cell_size)
        py = int(y + (index // COLUMNS + .5) * cell_size)
        red, green, blue = rgb.getpixel((px, py))
        if max(red, green, blue) - min(red, green, blue) > 30 or 40 < red < 215:
            raise ValueError("telemetry cell is not black or white; check panel coordinates")
        bits.append(int(red >= 215))
    data = bytes(sum(bits[start + bit] << (7 - bit) for bit in range(8))
                 for start in range(0, len(bits), 8))
    return decode_packet(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--y", type=int, required=True)
    parser.add_argument("--cell-size", type=float, default=CELL_SIZE)
    args = parser.parse_args()
    from PIL import Image
    with Image.open(args.screenshot) as screenshot:
        print(json.dumps(decode_image(screenshot, x=args.x, y=args.y, cell_size=args.cell_size), indent=2))


if __name__ == "__main__":
    main()
