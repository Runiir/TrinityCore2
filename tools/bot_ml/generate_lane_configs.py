from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from .common import write_json
except ImportError:
    from common import write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
LANE_NAMES = {
    0: "foundation",
    1: "world-planner",
    2: "runtime-recovery",
    3: "quest-profession",
    4: "combat-loot",
    5: "group-validation",
    6: "ml-data",
}


def lane_ports(lane: int) -> dict[str, int]:
    if lane not in LANE_NAMES:
        raise ValueError(f"lane must be one of {sorted(LANE_NAMES)}")
    return {
        "worldserver": 18085 + 100 * lane,
        "instance": 18086 + 100 * lane,
        "ra": 13443 + 100 * lane,
        "soap": 17878 + 100 * lane,
    }


def upsert_config(text: str, key: str, value: str) -> str:
    line = f"{key} = {value}"
    pattern = re.compile(rf"^(?P<prefix>\s*{re.escape(key)}\s*=\s*).*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip() + "\n" + line + "\n"


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def lane_output_root(lane: int, output_root: Path) -> Path:
    return resolve_repo_path(output_root) / LANE_NAMES[lane]


def build_world_config(base: Path, lane: int, ports: dict[str, int], root: Path) -> str:
    text = base.read_text(encoding="utf-8")
    text = text.rstrip() + f"\n# Generated lane {lane} ({LANE_NAMES[lane]}) bot autonomy worldserver config.\n"
    for key, value in {
        "WorldServerPort": str(ports["worldserver"]),
        "InstanceServerPort": str(ports["instance"]),
        "Ra.Port": str(ports["ra"]),
        "SOAP.Port": str(ports["soap"]),
        "Ra.Enable": "1",
        "SOAP.Enabled": "1",
        "LogsDir": f'"{root / "logs" / "world"}"',
        "PidFile": f'"{root / "run" / "worldserver.pid"}"',
        "BotWorld.PoolTagFilter": f'"bot_autonomy_{LANE_NAMES[lane]}"',
    }.items():
        text = upsert_config(text, key, value)
    return text


def build_auth_config(base: Path, lane: int, root: Path) -> str:
    text = base.read_text(encoding="utf-8")
    text = text.rstrip() + f"\n# Generated lane {lane} ({LANE_NAMES[lane]}) bot autonomy authserver config.\n"
    for key, value in {
        "LogsDir": f'"{root / "logs" / "auth"}"',
        "PidFile": f'"{root / "run" / "authserver.pid"}"',
    }.items():
        text = upsert_config(text, key, value)
    return text


def build_manifest(lane: int, ports: dict[str, int], root: Path, output_dir: Path) -> dict[str, Any]:
    return {
        "schema": "bot_autonomy_lane_config_v1",
        "lane": lane,
        "lane_name": LANE_NAMES[lane],
        "ports": ports,
        "output_root": str(root),
        "configs": {
            "worldserver": str(output_dir / "trinity-worldserver-lane.conf"),
            "authserver": str(output_dir / "trinity-authserver-lane.conf"),
        },
        "dataset_root": str(REPO_ROOT / "dataset" / "live_validation_instances" / LANE_NAMES[lane]),
        "artifact_root": str(REPO_ROOT / "artifacts" / "live_validation_instances" / LANE_NAMES[lane]),
        "pool_tag_filter": f"bot_autonomy_{LANE_NAMES[lane]}",
        "runtime_ml_control": "disabled_teacher_policy_validation_only",
    }


def write_lane_config(lane: int, output_root: Path, world_template: Path, auth_template: Path, dry_run: bool) -> dict[str, Any]:
    ports = lane_ports(lane)
    root = lane_output_root(lane, output_root)
    output_dir = root / "config"
    manifest = build_manifest(lane, ports, root, output_dir)
    if dry_run:
        return manifest

    output_dir.mkdir(parents=True, exist_ok=True)
    (root / "logs" / "world").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "auth").mkdir(parents=True, exist_ok=True)
    (root / "run").mkdir(parents=True, exist_ok=True)
    (output_dir / "trinity-worldserver-lane.conf").write_text(build_world_config(world_template, lane, ports, root), encoding="utf-8")
    (output_dir / "trinity-authserver-lane.conf").write_text(build_auth_config(auth_template, lane, root), encoding="utf-8")
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate isolated bot-autonomy lane configs.")
    parser.add_argument("--lane", type=int, action="append", help="Lane number to generate. Omit for all lanes.")
    parser.add_argument("--output-root", type=Path, default=Path("generated/bot_autonomy_lanes"))
    parser.add_argument("--world-template", type=Path, default=Path("src/server/worldserver/worldserver.conf.dist"))
    parser.add_argument("--auth-template", type=Path, default=Path("src/server/authserver/authserver.conf.dist"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lanes = args.lane if args.lane is not None else sorted(LANE_NAMES)
    world_template = resolve_repo_path(args.world_template)
    auth_template = resolve_repo_path(args.auth_template)
    manifests = [
        write_lane_config(lane, args.output_root, world_template, auth_template, args.dry_run)
        for lane in lanes
    ]
    print(json.dumps({"schema": "bot_autonomy_lane_config_set_v1", "lanes": manifests}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
