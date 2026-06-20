from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

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

DB_ROLES = {
    "auth": "LoginDatabaseInfo",
    "characters": "CharacterDatabaseInfo",
    "world": "WorldDatabaseInfo",
    "hotfixes": "HotfixDatabaseInfo",
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


def slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "lane"


def lane_name(lane: int, override: str = "") -> str:
    if override:
        return slugify(override)
    if lane not in LANE_NAMES:
        raise ValueError(f"lane must be one of {sorted(LANE_NAMES)} or set --lane-name")
    return LANE_NAMES[lane]


def upsert_config(text: str, key: str, value: str) -> str:
    line = f"{key} = {value}"
    pattern = re.compile(rf"^(?P<prefix>\s*{re.escape(key)}\s*=\s*).*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip() + "\n" + line + "\n"


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def lane_output_root(name: str, output_root: Path) -> Path:
    return resolve_repo_path(output_root) / name


def parse_trinity_db_info(value: str) -> dict[str, str]:
    parts = value.strip().strip('"').split(";")
    if len(parts) == 5:
        return {"host": parts[0], "port": parts[1], "user": parts[2], "password": parts[3], "database": parts[4], "format": "trinity"}
    parsed = urlparse(value)
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": str(parsed.port or 3306),
        "user": parsed.username or "trinity",
        "password": parsed.password or "trinity",
        "database": (parsed.path or "/").lstrip("/") or "world",
        "format": parsed.scheme or "mysql",
    }


def render_trinity_db_info(info: dict[str, str], database: str) -> str:
    if info.get("format") == "trinity":
        return f'"{info["host"]};{info["port"]};{info["user"]};{info["password"]};{database}"'
    netloc = f'{info["user"]}:{info["password"]}@{info["host"]}:{info["port"]}'
    return f'"{urlunparse(("mysql", netloc, "/" + database, "", "", ""))}"'


def db_name_from_source(value: str) -> str:
    return parse_trinity_db_info(value)["database"]


def default_db_sources(base_world_config: Path) -> dict[str, str]:
    text = base_world_config.read_text(encoding="utf-8")
    sources: dict[str, str] = {}
    for role, key in DB_ROLES.items():
        match = re.search(rf"^\s*{re.escape(key)}\s*=\s*(?P<value>.+?)\s*$", text, re.MULTILINE)
        if match:
            sources[role] = match.group("value").strip().strip('"')
    return sources


def build_db_clone_plan(name: str, suffix: str, db_sources: dict[str, str], isolation: str) -> dict[str, Any]:
    effective_suffix = slugify(suffix or f"lane_{name}")
    schemas: dict[str, dict[str, str]] = {}
    for role in DB_ROLES:
        source = db_sources.get(role, f"127.0.0.1;3306;trinity;trinity;{role}")
        source_info = parse_trinity_db_info(source)
        clone_database = source_info["database"] if isolation != "per-lane-clone" else f'{source_info["database"]}_{effective_suffix}'
        schemas[role] = {
            "source_database": source_info["database"],
            "database": clone_database,
            "source": source,
            "config_value": render_trinity_db_info(source_info, clone_database),
        }
    clone_commands = []
    reset_commands = []
    cleanup_commands = []
    if isolation == "per-lane-clone":
        for role, row in schemas.items():
            clone_commands.append(f'mysql -e "CREATE DATABASE IF NOT EXISTS `{row["database"]}`;"')
            clone_commands.append(f'mysqldump `{row["source_database"]}` | mysql `{row["database"]}`')
            reset_commands.append(f'mysql `{row["database"]}` < sql/updates/{role}/4.3.4/*.sql')
            cleanup_commands.append(f'mysql -e "DROP DATABASE IF EXISTS `{row["database"]}`;"')
    return {
        "isolation": isolation,
        "suffix": effective_suffix,
        "schemas": schemas,
        "clone_commands": clone_commands,
        "reset_commands": reset_commands,
        "cleanup_command": " && ".join(cleanup_commands),
    }


def build_world_config(base: Path, lane: int, name: str, ports: dict[str, int], root: Path, db_plan: dict[str, Any]) -> str:
    text = base.read_text(encoding="utf-8")
    text = text.rstrip() + f"\n# Generated lane {lane} ({name}) bot autonomy worldserver config.\n"
    for key, value in {
        "WorldServerPort": str(ports["worldserver"]),
        "InstanceServerPort": str(ports["instance"]),
        "Ra.Port": str(ports["ra"]),
        "SOAP.Port": str(ports["soap"]),
        "Ra.Enable": "1",
        "SOAP.Enabled": "1",
        "LogsDir": f'"{root / "logs" / "world"}"',
        "PidFile": f'"{root / "run" / "worldserver.pid"}"',
        "BotWorld.PoolTagFilter": f'"bot_autonomy_{name}"',
    }.items():
        text = upsert_config(text, key, value)
    for role, key in DB_ROLES.items():
        text = upsert_config(text, key, db_plan["schemas"][role]["config_value"])
    return text


def build_auth_config(base: Path, lane: int, name: str, root: Path) -> str:
    text = base.read_text(encoding="utf-8")
    text = text.rstrip() + f"\n# Generated lane {lane} ({name}) bot autonomy authserver config.\n"
    for key, value in {
        "LogsDir": f'"{root / "logs" / "auth"}"',
        "PidFile": f'"{root / "run" / "authserver.pid"}"',
    }.items():
        text = upsert_config(text, key, value)
    return text


def build_manifest(lane: int, name: str, ports: dict[str, int], root: Path, output_dir: Path, db_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "bot_autonomy_lane_config_v1",
        "lane": lane,
        "lane_name": name,
        "ports": ports,
        "output_root": str(root),
        "configs": {
            "worldserver": str(output_dir / "trinity-worldserver-lane.conf"),
            "authserver": str(output_dir / "trinity-authserver-lane.conf"),
        },
        "dataset_root": str(REPO_ROOT / "dataset" / "live_validation_instances" / name),
        "artifact_root": str(REPO_ROOT / "artifacts" / "live_validation_instances" / name),
        "pool_tag_filter": f"bot_autonomy_{name}",
        "db_isolation": db_plan["isolation"],
        "db_suffix": db_plan["suffix"],
        "databases": db_plan["schemas"],
        "db_clone_commands": db_plan["clone_commands"],
        "db_reset_commands": db_plan["reset_commands"],
        "cleanup_command": db_plan["cleanup_command"],
        "runtime_ml_control": "disabled_teacher_policy_validation_only",
    }


def write_lane_config(
    lane: int,
    output_root: Path,
    world_template: Path,
    auth_template: Path,
    dry_run: bool,
    name_override: str = "",
    db_isolation: str = "per-lane-clone",
    db_suffix: str = "",
    db_sources: dict[str, str] | None = None,
) -> dict[str, Any]:
    ports = lane_ports(lane)
    name = lane_name(lane, name_override)
    root = lane_output_root(name, output_root)
    output_dir = root / "config"
    sources = default_db_sources(world_template)
    sources.update({key: value for key, value in (db_sources or {}).items() if value})
    db_plan = build_db_clone_plan(name, db_suffix, sources, db_isolation)
    manifest = build_manifest(lane, name, ports, root, output_dir, db_plan)
    if dry_run:
        return manifest

    output_dir.mkdir(parents=True, exist_ok=True)
    (root / "logs" / "world").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "auth").mkdir(parents=True, exist_ok=True)
    (root / "run").mkdir(parents=True, exist_ok=True)
    (output_dir / "trinity-worldserver-lane.conf").write_text(build_world_config(world_template, lane, name, ports, root, db_plan), encoding="utf-8")
    (output_dir / "trinity-authserver-lane.conf").write_text(build_auth_config(auth_template, lane, name, root), encoding="utf-8")
    write_json(output_dir / "db_clone_plan.json", db_plan)
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate isolated bot-autonomy lane configs.")
    parser.add_argument("--lane", type=int, action="append", help="Lane number to generate. Omit for all lanes.")
    parser.add_argument("--lane-name", default="", help="Override generated lane name. Only valid with a single --lane.")
    parser.add_argument("--output-root", type=Path, default=Path("generated/bot_autonomy_lanes"))
    parser.add_argument("--world-template", type=Path, default=Path("src/server/worldserver/worldserver.conf.dist"))
    parser.add_argument("--auth-template", type=Path, default=Path("src/server/authserver/authserver.conf.dist"))
    parser.add_argument("--db-isolation", choices=["per-lane-clone", "shared"], default="per-lane-clone")
    parser.add_argument("--db-suffix", default="", help="Suffix for per-lane cloned schemas. Defaults to lane_<lane-name>.")
    parser.add_argument("--auth-db-source-url", default="")
    parser.add_argument("--characters-db-source-url", default="")
    parser.add_argument("--world-db-source-url", default="")
    parser.add_argument("--hotfixes-db-source-url", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lanes = args.lane if args.lane is not None else sorted(LANE_NAMES)
    if args.lane_name and len(lanes) != 1:
        raise SystemExit("--lane-name requires exactly one --lane")
    world_template = resolve_repo_path(args.world_template)
    auth_template = resolve_repo_path(args.auth_template)
    db_sources = {
        "auth": args.auth_db_source_url,
        "characters": args.characters_db_source_url,
        "world": args.world_db_source_url,
        "hotfixes": args.hotfixes_db_source_url,
    }
    manifests = [
        write_lane_config(
            lane,
            args.output_root,
            world_template,
            auth_template,
            args.dry_run,
            name_override=args.lane_name,
            db_isolation=args.db_isolation,
            db_suffix=args.db_suffix,
            db_sources=db_sources,
        )
        for lane in lanes
    ]
    print(json.dumps({"schema": "bot_autonomy_lane_config_set_v1", "lanes": manifests}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
