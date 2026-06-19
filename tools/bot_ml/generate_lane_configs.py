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
LANE_PORTS = {
    0: {
        "world": 18085,
        "auth": 18086,
        "soap": 13443,
        "ra": 17878,
    }
}


def upsert_config(text: str, key: str, value: str) -> str:
    line = f"{key} = {value}"
    pattern = re.compile(rf"^(?P<prefix>\s*{re.escape(key)}\s*=\s*).*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip() + "\n" + line + "\n"


def lane_output_root(lane: int, output_root: Path) -> Path:
    return output_root / f"lane_{lane}"


def build_world_config(base: Path, lane: int, ports: dict[str, int], root: Path) -> str:
    text = base.read_text(encoding="utf-8")
    text = text.rstrip() + f"\n# Generated lane {lane} bot autonomy worldserver config.\n"
    for key, value in {
        "WorldServerPort": str(ports["world"]),
        "SOAP.Port": str(ports["soap"]),
        "Ra.Port": str(ports["ra"]),
        "Ra.Enable": "1",
        "SOAP.Enabled": "1",
        "LogsDir": f'"{root / "logs" / "world"}"',
        "PidFile": f'"{root / "run" / "worldserver.pid"}"',
    }.items():
        text = upsert_config(text, key, value)
    return text


def build_auth_config(base: Path, lane: int, ports: dict[str, int], root: Path) -> str:
    text = base.read_text(encoding="utf-8")
    text = text.rstrip() + f"\n# Generated lane {lane} bot autonomy authserver config.\n"
    for key, value in {
        "RealmServerPort": str(ports["auth"]),
        "LogsDir": f'"{root / "logs" / "auth"}"',
        "PidFile": f'"{root / "run" / "authserver.pid"}"',
    }.items():
        text = upsert_config(text, key, value)
    return text


def build_manifest(lane: int, ports: dict[str, int], root: Path, output_dir: Path) -> dict[str, Any]:
    return {
        "schema": "bot_autonomy_lane_config_v1",
        "lane": lane,
        "ports": ports,
        "output_root": str(root),
        "configs": {
            "worldserver": str(output_dir / "trinity-worldserver-lane.conf"),
            "authserver": str(output_dir / "trinity-authserver-lane.conf"),
        },
        "live_validation_output": str(root / "live_validation"),
        "runtime_ml_control": "disabled_teacher_policy_validation_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate isolated bot-autonomy lane configs.")
    parser.add_argument("--lane", type=int, default=0)
    parser.add_argument("--output-root", type=Path, default=Path("generated/bot_autonomy_lanes"))
    parser.add_argument("--world-template", type=Path, default=Path("src/server/worldserver/worldserver.conf.dist"))
    parser.add_argument("--auth-template", type=Path, default=Path("src/server/authserver/authserver.conf.dist"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ports = LANE_PORTS.get(args.lane)
    if not ports:
        raise SystemExit(f"no port allocation for lane {args.lane}")

    world_template = args.world_template if args.world_template.is_absolute() else REPO_ROOT / args.world_template
    auth_template = args.auth_template if args.auth_template.is_absolute() else REPO_ROOT / args.auth_template
    root = lane_output_root(args.lane, args.output_root if args.output_root.is_absolute() else REPO_ROOT / args.output_root)
    output_dir = root / "config"
    manifest = build_manifest(args.lane, ports, root, output_dir)

    if args.dry_run:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    (root / "logs" / "world").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "auth").mkdir(parents=True, exist_ok=True)
    (root / "run").mkdir(parents=True, exist_ok=True)
    (root / "live_validation").mkdir(parents=True, exist_ok=True)
    (output_dir / "trinity-worldserver-lane.conf").write_text(build_world_config(world_template, args.lane, ports, root), encoding="utf-8")
    (output_dir / "trinity-authserver-lane.conf").write_text(build_auth_config(auth_template, args.lane, ports, root), encoding="utf-8")
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
