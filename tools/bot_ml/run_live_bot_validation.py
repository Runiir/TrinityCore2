from __future__ import annotations

import argparse
import base64
import html
import json
import os
import select
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import re

try:
    from .build_validation_provisioning import apply_gear_profiles, build_account_insert_sql, build_character_insert_sql, load_config, load_gear_profiles
    from .common import write_json
    from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
except ImportError:
    from build_validation_provisioning import apply_gear_profiles, build_account_insert_sql, build_character_insert_sql, load_config, load_gear_profiles
    from common import write_json
    from extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url


DEFAULT_LIVE_VALIDATION_TIMEOUT_SEC = 90
DEFAULT_BOSS_ROUTE_OBSERVE_SEC = 300
DEFAULT_BOSS_ROUTE_TIMEOUT_SEC = 900


DEFAULT_STAGES = [
    "movement_smoke",
    "kill_quest",
    "collect_quest",
    "quest_hub_batching",
    "trainer_visit",
    "vendor_repair",
    "profession_recipe_acquisition",
    "material_farming",
    "smart_loot",
    "normal_dungeon_trash",
    "dungeon_boss",
    "full_stonecore_clear",
    "raid_trash",
    "raid_boss",
    "full_blackwing_descent_clear",
]

BOT_MEMORY_TABLES = [
    "bot_memory_daily_cooldowns",
    "bot_memory_danger_zones",
    "bot_memory_decision_fingerprints",
    "bot_memory_failed_paths",
    "bot_memory_material_sources",
    "bot_memory_objective_clusters",
    "bot_memory_pois",
    "bot_memory_recipe_sources",
    "bot_memory_safe_positions",
    "bot_memory_transport_usage",
]

VALIDATION_EVIDENCE_ACTIONS = {
    "party_formation": {"party_formed", "raid_formed", "validation_group_formed"},
    "raid_formation": {"raid_formed", "validation_group_formed"},
    "role_assignments": {"role_assignment", "validation_role_assignment", "tank_assigned", "healer_assigned"},
    "pulls": {"trash_action", "validation_route_trash_action", "boss_started", "boss_action", "validation_route_pull"},
    "target_priority": {"target_priority", "target_switch", "validation_target_priority", "assist_target_search_authoritative_focus"},
    "interrupts": {"interrupt", "interrupt_success", "assigned_interrupt_success", "validation_interrupt"},
    "healer_assignments": {"healer_assignment", "validation_route_group_heal", "trash_heal", "external_defensive"},
    "tank_positioning": {"validation_route_tank_boss", "tank_positioning", "force_tank_focus", "move_to_validation_route_assist_target"},
    "regrouping": {"validation_route_regroup", "regroup", "validation_route_hold_anchor"},
    "recovery": {"stuck_detected", "unstuck", "death", "dead_recovery", "validation_route_recovery"},
    "instance_reset": {"instance_reset", "reset_stale_boss_activation", "bot_pool_reset"},
}


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def database_name(database_url: str) -> str:
    return (urlparse(database_url).path or "/").lstrip("/")


def trinity_config_bool(path: Path, key: str, default: bool = False) -> bool:
    if not path.exists():
        return default
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(?P<value>[^\s#]+)", re.MULTILINE)
    match = pattern.search(path.read_text(encoding="utf-8"))
    if not match:
        return default
    value = match.group("value").strip().strip('"').lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def load_validation_route(scenario_dir: Path, context: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(context.get("scenario_id") or "")
    route_node_id = str(context.get("route_node_id") or "")
    if not scenario_id or not route_node_id:
        return {}
    route_path = scenario_dir / "validation_routes.jsonl"
    if not route_path.exists():
        return {}
    for line in route_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("scenario_id") or "") == scenario_id and str(row.get("route_node_id") or "") == route_node_id:
            return row
    return {}


def upsert_trinity_config(text: str, key: str, value: str) -> str:
    text = text.replace("\\n", "\n")
    line = f"{key} = {value}"
    pattern = re.compile(rf"^(?P<prefix>\s*{re.escape(key)}\s*=\s*).*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip() + "\n" + line + "\n"


def write_validation_config(base_config: Path, output_dir: Path, pool_tag: str = "", validation_route: dict[str, Any] | None = None) -> Path:
    route = validation_route or {}
    if not pool_tag and not route:
        return base_config
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = output_dir / "worldserver.validation.conf"
    text = base_config.read_text(encoding="utf-8") if base_config.exists() else ""
    text = text.rstrip() + "\n# Generated by tools.bot_ml.run_live_bot_validation for scenario-scoped validation.\n"
    text = upsert_trinity_config(text, "BotWorld.AutoStart", "1")
    if pool_tag:
        text = upsert_trinity_config(text, "BotWorld.PoolTagFilter", f'"{pool_tag.replace(chr(34), "")}"')
    if route:
        expected_bot_count = int(route.get("expected_bot_count") or 0)
        if expected_bot_count > 0:
            text = upsert_trinity_config(text, "BotWorld.TargetPopulation", str(expected_bot_count))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Enable", "1")
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ScenarioId", f'"{str(route.get("scenario_id") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.NodeId", f'"{str(route.get("route_node_id") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Label", f'"{str(route.get("label") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Kind", f'"{str(route.get("kind") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.MechanicProfile", f'"{str(route.get("mechanic_profile") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Map", str(int(route.get("map_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.X", str(float(route.get("x") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Y", str(float(route.get("y") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Z", str(float(route.get("z") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.O", str(float(route.get("o") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.TargetEntry", str(int(route.get("source_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerTargetEntry", str(int(route.get("opener_target_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationDataId", str(int(route.get("activation_data_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationDataValue", str(int(route.get("activation_data_value") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSpawnGroupId", str(int(route.get("activation_spawn_group_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationActionEntry", str(int(route.get("activation_action_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationActionId", str(int(route.get("activation_action_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonEntry", str(int(route.get("activation_summon_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonX", str(float(route.get("activation_summon_x") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonY", str(float(route.get("activation_summon_y") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonZ", str(float(route.get("activation_summon_z") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonO", str(float(route.get("activation_summon_o") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonEntry", str(int(route.get("opener_summon_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonX", str(float(route.get("opener_summon_x") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonY", str(float(route.get("opener_summon_y") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonZ", str(float(route.get("opener_summon_z") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonO", str(float(route.get("opener_summon_o") or 0.0)))
        if str(route.get("kind") or "") in {"boss", "trash"}:
            text = upsert_trinity_config(text, "BotProgression.AllowDungeons", "1")
    generated.write_text(text, encoding="utf-8")
    return generated


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    uncommented = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    for char in uncommented:
        current.append(char)
        if escaped:
            escaped = False
            continue
        if quote and char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif char == ";" and quote is None:
            text = "".join(current).strip().rstrip(";").strip()
            if text and not text.startswith("--"):
                statements.append(text)
            current = []
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def execute_sql_text(database_url: str, sql: str) -> int:
    statements = split_sql_statements(sql)
    conn = connect_mysql(database_url)
    try:
        with conn.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()
    return len(statements)


def tag_predicate(tags: list[str]) -> str:
    if not tags:
        return "1 = 1"
    return "(" + " OR ".join(f"p.`experiment_tags` LIKE {sql_quote('%' + tag + '%')}" for tag in tags) + ")"


def build_bot_pool_reset_sql(tags: list[str] | None = None, world_database: str = "world", reset_positions: bool = True, reset_quests: bool = True, reset_memory: bool = True) -> str:
    tags = tags or ["test_account"]
    predicate = tag_predicate(tags)
    guid_select = f"SELECT p.`guid` FROM `characters`.`character_bot_pool` p WHERE p.`enabled` = 1 AND {predicate}"
    lines = [
        "-- Generated by tools.bot_ml.run_live_bot_validation.",
        "-- Resets only enabled bot-pool rows matching the configured experiment_tags predicate.",
        "UPDATE `characters`.`character_bot_pool` p SET p.`in_use` = 0 WHERE p.`enabled` = 1 AND " + predicate + ";",
        "UPDATE `characters`.`characters` c JOIN `characters`.`character_bot_pool` p ON p.`guid` = c.`guid` SET c.`online` = 0 WHERE p.`enabled` = 1 AND " + predicate + ";",
        f"DELETE FROM `characters`.`character_instance` WHERE `guid` IN ({guid_select});",
        "DELETE gi FROM `characters`.`group_instance` gi "
        "JOIN `characters`.`groups` g ON g.`guid` = gi.`guid` "
        f"WHERE g.`leaderGuid` IN ({guid_select}) "
        f"OR g.`guid` IN (SELECT gm.`guid` FROM `characters`.`group_member` gm WHERE gm.`memberGuid` IN ({guid_select}));",
        "DELETE gm FROM `characters`.`group_member` gm "
        f"WHERE gm.`memberGuid` IN ({guid_select}) "
        f"OR gm.`guid` IN (SELECT g.`guid` FROM `characters`.`groups` g WHERE g.`leaderGuid` IN ({guid_select}));",
        "DELETE g FROM `characters`.`groups` g "
        f"WHERE g.`leaderGuid` IN ({guid_select});",
    ]
    if reset_positions:
        lines.append(
            "UPDATE `characters`.`characters` c "
            "JOIN `characters`.`character_bot_pool` p ON p.`guid` = c.`guid` "
            f"JOIN `{world_database}`.`playercreateinfo` pci ON pci.`race` = c.`race` AND pci.`class` = c.`class` "
            "SET c.`map` = pci.`map`, c.`position_x` = pci.`position_x`, c.`position_y` = pci.`position_y`, c.`position_z` = pci.`position_z`, c.`orientation` = pci.`orientation`, c.`health` = 100, c.`power1` = 100 "
            "WHERE p.`enabled` = 1 AND "
            + predicate
            + ";"
        )
    if reset_quests:
        for table in [
            "character_queststatus",
            "character_queststatus_daily",
            "character_queststatus_monthly",
            "character_queststatus_rewarded",
            "character_queststatus_seasonal",
            "character_queststatus_weekly",
            "character_aura",
            "character_spell_cooldown",
        ]:
            lines.append(f"DELETE FROM `characters`.`{table}` WHERE `guid` IN ({guid_select});")
    if reset_memory:
        for table in BOT_MEMORY_TABLES:
            lines.append(f"DELETE FROM `characters`.`{table}` WHERE `bot_guid` IN ({guid_select});")
    return "\n".join(lines) + "\n"


def prepare_validation_provisioning(
    output_dir: Path,
    config_path: Path,
    gear_profiles_path: Path,
    worldserver_conf: Path,
    apply: bool = False,
) -> dict[str, Any]:
    config = apply_gear_profiles(load_config(config_path), load_gear_profiles(gear_profiles_path))
    account_sql = build_account_insert_sql(config)
    character_sql = build_character_insert_sql(config)
    provision_dir = output_dir / "validation_provisioning_apply"
    provision_dir.mkdir(parents=True, exist_ok=True)
    account_path = provision_dir / "provision_accounts.sql"
    character_path = provision_dir / "provision_characters.sql"
    account_path.write_text(account_sql, encoding="utf-8")
    character_path.write_text(character_sql, encoding="utf-8")

    auth_url = database_url_from_worldserver_conf(worldserver_conf, "LoginDatabaseInfo")
    character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")
    report: dict[str, Any] = {
        "schema": "bot_live_validation_provisioning_apply_v1",
        "applied": apply,
        "config": str(config_path),
        "gear_profiles": str(gear_profiles_path),
        "account_sql": str(account_path),
        "character_sql": str(character_path),
        "auth_database": sanitize_database_url(auth_url),
        "character_database": sanitize_database_url(character_url),
        "account_statement_count": len(split_sql_statements(account_sql)),
        "character_statement_count": len(split_sql_statements(character_sql)),
    }
    if apply:
        report["executed_account_statements"] = execute_sql_text(auth_url, account_sql)
        report["executed_character_statements"] = execute_sql_text(character_url, character_sql)
    return report


def prepare_route_bot_start(output_dir: Path, route: dict[str, Any], worldserver_conf: Path, tags: list[str], apply: bool = False) -> dict[str, Any]:
    map_id = int(route.get("bot_start_map_id") or 0)
    x = float(route.get("bot_start_x") or 0.0)
    y = float(route.get("bot_start_y") or 0.0)
    z = float(route.get("bot_start_z") or 0.0)
    o = float(route.get("bot_start_o") or 0.0)
    if not map_id or (x == 0.0 and y == 0.0 and z == 0.0):
        return {"schema": "bot_live_validation_route_start_v1", "applied": False, "reason": "route_start_not_configured"}

    predicate = tag_predicate(tags or ["test_account"])
    sql = (
        "-- Generated by tools.bot_ml.run_live_bot_validation.\n"
        "-- Moves scenario-scoped bot-pool characters to a route-specific validation start.\n"
        "UPDATE `characters`.`characters` c "
        "JOIN `characters`.`character_bot_pool` p ON p.`guid` = c.`guid` "
        f"SET c.`map` = {map_id}, c.`position_x` = {x}, c.`position_y` = {y}, c.`position_z` = {z}, c.`orientation` = {o}, "
        "c.`health` = 100, c.`power1` = 100, c.`online` = 0 "
        "WHERE p.`enabled` = 1 AND "
        + predicate
        + ";\n"
    )
    start_dir = output_dir / "route_bot_start"
    start_dir.mkdir(parents=True, exist_ok=True)
    sql_path = start_dir / "route_bot_start.sql"
    sql_path.write_text(sql, encoding="utf-8")
    statements = 0
    if apply:
        character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")
        statements = execute_sql_text(character_url, sql)
    return {
        "schema": "bot_live_validation_route_start_v1",
        "applied": bool(apply),
        "statements": statements,
        "sql": str(sql_path),
        "map_id": map_id,
        "x": x,
        "y": y,
        "z": z,
        "o": o,
    }


def prepare_bot_pool_reset(
    output_dir: Path,
    worldserver_conf: Path,
    tags: list[str],
    apply: bool = False,
    reset_positions: bool = True,
    reset_quests: bool = True,
    reset_memory: bool = True,
) -> dict[str, Any]:
    world_url = database_url_from_worldserver_conf(worldserver_conf, "WorldDatabaseInfo")
    character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")
    sql = build_bot_pool_reset_sql(tags, database_name(world_url), reset_positions, reset_quests, reset_memory)
    reset_dir = output_dir / "bot_pool_reset"
    reset_dir.mkdir(parents=True, exist_ok=True)
    sql_path = reset_dir / "reset_bot_pool.sql"
    sql_path.write_text(sql, encoding="utf-8")
    report: dict[str, Any] = {
        "schema": "bot_live_validation_bot_pool_reset_v1",
        "applied": apply,
        "tags": tags,
        "reset_positions": reset_positions,
        "reset_quests": reset_quests,
        "reset_memory": reset_memory,
        "sql": str(sql_path),
        "statement_count": len(split_sql_statements(sql)),
        "world_database": sanitize_database_url(world_url),
        "character_database": sanitize_database_url(character_url),
    }
    if apply:
        report["executed_statements"] = execute_sql_text(character_url, sql)
    return report


def command_script(selector: str = "all", trace_limit: int = 20, start: bool = True, stop: bool = False, exit_server: bool = True) -> str:
    commands: list[str] = []
    if start:
        commands.append(".botauto start")
    commands.extend(
        [
            ".botauto status",
            f".botauto diagnose {selector}",
            f".botauto trace {selector} {trace_limit}",
            ".botexp summary",
        ]
    )
    if stop:
        commands.append(".botauto stop")
    if exit_server:
        commands.append("server shutdown force 0")
    return "\n".join(commands) + "\n"


def parse_json_objects(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(output):
        start = output.find("{", index)
        if start == -1:
            break
        try:
            payload, end = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        index = start + max(end, 1)
    return rows


def classify_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    status = next((row for row in reversed(payloads) if row.get("action") in {"botexp_status", "botauto_status"} or {"active", "active_bots", "target_bots"} & set(row)), {})
    diagnosis = next((row for row in reversed(payloads) if row.get("diagnosis_schema_version") or row.get("diagnoses") or row.get("diagnosis")), {})
    trace = next((row for row in reversed(payloads) if row.get("trace_schema_version") or row.get("entries")), {})
    summary = next((row for row in reversed(payloads) if row.get("summary_schema_version") or "duration_minutes" in row or "total_kills" in row or "bot_learning" in row), {})
    return {"status": status, "diagnosis": diagnosis, "trace": trace, "summary": summary}


def command_errors(output: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    current_command = ""
    for line in output.splitlines():
        text = line.strip()
        if text.startswith("$ "):
            current_command = text[2:]
        elif "There is no such subcommand" in text:
            errors.append({"command": current_command, "error": "no_such_subcommand"})
    return errors


def should_observe_before_command(command_text: str) -> bool:
    return (
        command_text == ".botauto status"
        or command_text.startswith(".botauto diagnose")
        or command_text.startswith(".botauto trace")
        or command_text == ".botexp summary"
    )


def bot_status_ready(output: str) -> bool:
    return bot_status_state(output) is True


def bot_status_state(output: str) -> bool | None:
    payloads = parse_json_objects(output)
    for row in reversed(payloads):
        if not isinstance(row, dict):
            continue
        if row.get("action") not in {"botexp_status", "botauto_status"} and not ({"active", "active_bots", "target_bots", "bots"} & set(row)):
            continue
        active_bots = int(row.get("active_bots") or row.get("bots") or row.get("activeBots") or 0)
        target_bots = int(row.get("target_bots") or row.get("targetBots") or 0)
        if active_bots > 0 and (target_bots <= 0 or active_bots >= target_bots):
            return True
        return False
    return None


def wait_for_bot_status_ready(process: subprocess.Popen[str], deadline: float, max_wait_sec: int = 180) -> str:
    if process.stdin is None:
        return ""
    output = []
    ready_deadline = min(deadline, time.monotonic() + max_wait_sec)
    while process.poll() is None and time.monotonic() < ready_deadline:
        process.stdin.write(".botauto status\n")
        process.stdin.flush()
        chunk = read_until_console_prompt(process, ready_deadline, expected_command_output_marker(".botauto status"))
        output.append("$ .botauto status\n")
        output.append(chunk)
        status_state = bot_status_state(chunk)
        if status_state is True:
            break
        if status_state is None:
            break
        time.sleep(2.0)
    return "".join(output)


def count_trace_entries(trace: dict[str, Any]) -> int:
    entries = trace.get("entries")
    if isinstance(entries, list):
        return len(entries)
    bots = trace.get("bots")
    if isinstance(bots, list):
        return sum(len(bot.get("entries") or []) for bot in bots if isinstance(bot, dict))
    return 0


def trace_entries(trace: dict[str, Any]) -> list[dict[str, Any]]:
    entries = trace.get("entries")
    if isinstance(entries, list):
        return [entry for entry in entries if isinstance(entry, dict)]
    bots = trace.get("bots")
    if isinstance(bots, list):
        rows: list[dict[str, Any]] = []
        for bot in bots:
            if isinstance(bot, dict):
                rows.extend(entry for entry in bot.get("entries") or [] if isinstance(entry, dict))
        return rows
    return []


def diagnosis_rows(diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = diagnosis.get("diagnoses") or diagnosis.get("bots") or ([] if not diagnosis else [diagnosis])
    return [row for row in rows if isinstance(row, dict)]


def load_scenario_reports(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    single_file = path.is_file()
    files = [path] if single_file else sorted(path.glob("*.json"))
    reports: dict[str, dict[str, Any]] = {}
    for report_path in files:
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        scenario_id = str(payload.get("scenario_id") or payload.get("id") or (report_path.stem if single_file else ""))
        if scenario_id:
            reports[scenario_id] = payload
    return reports


def validation_context_from_args(args: argparse.Namespace) -> dict[str, Any]:
    context: dict[str, Any] = {
        "scenario_id": args.validation_scenario_id or "",
        "segment_id": args.validation_segment_id or "",
        "route_node_id": args.validation_route_node_id or "",
        "route_label": args.validation_route_label or "",
        "route_kind": args.validation_route_kind or "",
        "route_step": int(args.validation_route_step or 0),
        "mechanic_profile": args.validation_mechanic_profile or "",
    }
    return {key: value for key, value in context.items() if value not in {"", 0}}


def nested_get(row: dict[str, Any], path: list[str], default: Any = None) -> Any:
    value: Any = row
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value is None else value


def scenario_bool(report: dict[str, Any], *keys: str) -> bool:
    return any(bool(report.get(key)) for key in keys)


def scenario_int(report: dict[str, Any], *keys: str) -> int:
    values = []
    for key in keys:
        try:
            values.append(int(report.get(key) or 0))
        except (TypeError, ValueError):
            values.append(0)
    return max(values or [0])


def scenario_group_ready(report: dict[str, Any]) -> bool:
    return scenario_bool(report, "prepared_group", "group_ready", "provisioning_ready")


def scenario_trash_ready(report: dict[str, Any]) -> bool:
    return scenario_bool(report, "trash_cleared", "trash_passed") or scenario_int(report, "trash_pulls", "trash_kills", "trash_packs_cleared") > 0


def scenario_boss_kills(report: dict[str, Any]) -> int:
    return scenario_int(report, "boss_kills", "raid_boss_kills", "bosses_killed")


def scenario_clear_complete(report: dict[str, Any]) -> bool:
    return scenario_bool(report, "clear_complete", "all_passed", "scenario_passed")


def scenario_missing(report: dict[str, Any], missing_name: str) -> list[str]:
    return [] if report else [missing_name]


def scenario_stage_missing(stage: str, scenario_reports: dict[str, dict[str, Any]]) -> list[str]:
    stonecore = scenario_reports.get("stonecore_5n") or {}
    bwd = scenario_reports.get("blackwing_descent_10n") or {}
    if stage == "normal_dungeon_trash":
        missing = scenario_missing(stonecore, "stonecore_live_clear_report")
        if stonecore and not scenario_group_ready(stonecore):
            missing.append("prepared_5man_group")
        if stonecore and not scenario_trash_ready(stonecore):
            missing.append("dungeon_trash_evidence")
        return missing
    if stage == "dungeon_boss":
        missing = scenario_missing(stonecore, "stonecore_live_clear_report")
        if stonecore and not scenario_group_ready(stonecore):
            missing.append("prepared_5man_group")
        if stonecore and scenario_boss_kills(stonecore) <= 0:
            missing.append("dungeon_boss_kill_evidence")
        return missing
    if stage == "full_stonecore_clear":
        missing = scenario_missing(stonecore, "stonecore_live_clear_report")
        if stonecore and not scenario_group_ready(stonecore):
            missing.append("prepared_5man_group")
        if stonecore and not scenario_clear_complete(stonecore):
            missing.append("stonecore_full_clear_evidence")
        return missing
    if stage == "raid_trash":
        missing = scenario_missing(bwd, "blackwing_descent_live_clear_report")
        if bwd and not scenario_group_ready(bwd):
            missing.append("prepared_10man_raid")
        if bwd and not scenario_trash_ready(bwd):
            missing.append("raid_trash_evidence")
        return missing
    if stage == "raid_boss":
        missing = scenario_missing(bwd, "blackwing_descent_live_boss_report")
        if bwd and not scenario_group_ready(bwd):
            missing.append("prepared_10man_raid")
        if bwd and scenario_boss_kills(bwd) <= 0:
            missing.append("raid_boss_kill_evidence")
        return missing
    if stage == "full_blackwing_descent_clear":
        missing = scenario_missing(bwd, "blackwing_descent_live_clear_report")
        if bwd and not scenario_group_ready(bwd):
            missing.append("prepared_10man_raid")
        if bwd and not scenario_clear_complete(bwd):
            missing.append("blackwing_descent_full_clear_evidence")
        return missing
    return []


def live_evidence(status: dict[str, Any], diagnosis: dict[str, Any], trace: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    entries = trace_entries(trace)
    diagnoses = diagnosis_rows(diagnosis)
    non_spawn_trace_entries = sum(1 for entry in entries if str(entry.get("action") or entry.get("situation") or "") != "bot_spawned")
    decisions = max(int(status.get("decisions") or 0), int(summary.get("decisions") or 0), non_spawn_trace_entries)
    failures = max(int(status.get("failures") or 0), int(summary.get("failures_recorded") or 0))
    duration_seconds = int(status.get("duration_seconds") or 0)
    duration_minutes = float(summary.get("duration_minutes") or 0.0)
    moved_diagnoses = sum(1 for row in diagnoses if bool(nested_get(row, ["snapshot", "movement", "is_moving"], False)) or float(nested_get(row, ["snapshot", "movement", "distance_moved_since_last_decision"], 0) or 0) > 0.0)
    non_wait_diagnoses = sum(1 for row in diagnoses if str(nested_get(row, ["snapshot", "decision", "action"], "wait")) not in {"", "wait"})
    diagnosis_codes = Counter(
        str(nested_get(row, ["diagnosis", "diagnosis_code"], nested_get(row, ["diagnosis_code"], "")))
        for row in diagnoses
        if nested_get(row, ["diagnosis", "diagnosis_code"], nested_get(row, ["diagnosis_code"], ""))
    )
    diagnosis_severities = Counter(
        str(nested_get(row, ["diagnosis", "severity"], nested_get(row, ["severity"], "")))
        for row in diagnoses
        if nested_get(row, ["diagnosis", "severity"], nested_get(row, ["severity"], ""))
    )
    action_names = {
        str(entry.get("action") or entry.get("situation") or "")
        for entry in entries
        if entry.get("action") or entry.get("situation")
    }
    action_counts = Counter(str(entry.get("action") or entry.get("situation") or "") for entry in entries if entry.get("action") or entry.get("situation"))
    result_counts = Counter(str(entry.get("result") or "") for entry in entries if entry.get("result"))
    diagnosis_result_counts = Counter()
    stuck_events = int(status.get("stuck") or 0) + int(summary.get("stuck_events") or 0) + action_counts.get("stuck_detected", 0)
    unstuck_failures = sum(1 for entry in entries if str(entry.get("action") or "") == "unstuck" and str(entry.get("result") or "") in {"failed", "failure"})
    repath_events = action_counts.get("stuck_detected", 0) + result_counts.get("repath", 0)
    quest_acceptance_actions = sum(
        1
        for entry in entries
        if str(entry.get("action") or "").startswith("accept_quest") or str(entry.get("action") or "") == "accept_hub_quests"
    )
    quest_completion_actions = sum(
        1
        for entry in entries
        if str(entry.get("action") or "").startswith("complete_quest")
    )
    hub_acceptance_actions = sum(1 for entry in entries if str(entry.get("action") or "") == "accept_hub_quests")
    teacher_assisted_kills = sum(
        1
        for entry in entries
        if str(entry.get("action") or "") == "teacher_kill_assist"
        and str(entry.get("result") or "") == "simple_open_world_quest_mob_target"
    )
    action_names.update(
        str(nested_get(row, ["snapshot", "decision", "action"], ""))
        for row in diagnoses
        if nested_get(row, ["snapshot", "decision", "action"], "")
    )
    diagnosis_action_counts = Counter()
    diagnosis_action_counts = Counter(
        str(nested_get(row, ["snapshot", "decision", "action"], ""))
        for row in diagnoses
        if nested_get(row, ["snapshot", "decision", "action"], "")
    )
    legacy_diagnosis_action_counts = diagnosis_action_counts if not entries else Counter()
    diagnosis_result_counts = Counter(
        str(nested_get(row, ["snapshot", "decision", "result"], ""))
        for row in diagnoses
        if nested_get(row, ["snapshot", "decision", "result"], "")
    )
    action_text = " ".join(sorted(action_names)).lower()
    quest_progress = max(int(status.get("quest_objective_progress") or 0), int(summary.get("quest_objective_progress") or 0))
    quests_accepted = max(int(status.get("quests_accepted") or 0), int(summary.get("quests_accepted") or 0), quest_acceptance_actions)
    quests_completed = max(int(status.get("quests_completed") or 0), int(summary.get("quests_completed") or 0), quest_completion_actions)
    kills = max(int(status.get("kills") or 0), int(summary.get("total_kills") or 0))
    boss_kill_evidence = max(
        int(summary.get("boss_kills") or 0),
        int(summary.get("raid_boss_kills") or 0),
        action_counts.get("boss_killed", 0),
        action_counts.get("raid_boss_killed", 0),
    )
    trash_action_evidence = sum(
        count
        for action, count in action_counts.items()
        if action in {"trash_action", "trash_heal", "validation_route_trash_action", "dungeon_trash_cleared", "raid_trash_cleared"}
    )
    trash_action_evidence += sum(
        count
        for action, count in legacy_diagnosis_action_counts.items()
        if action in {"trash_action", "trash_heal", "validation_route_trash_action", "dungeon_trash_cleared", "raid_trash_cleared"}
    )
    trash_pulls = max(
        int(summary.get("trash_pulls") or 0),
        int(summary.get("trash_kills") or 0),
        int(summary.get("trash_packs_cleared") or 0),
        trash_action_evidence,
    )
    kill_evidence = kills + teacher_assisted_kills
    gear_upgrades = max(int(status.get("gear_upgrades") or 0), int(summary.get("gear_upgrades") or 0))
    role_assignment_evidence = max(
        int(summary.get("role_assignments") or 0),
        action_counts.get("role_assignment", 0) + action_counts.get("validation_role_assignment", 0),
        diagnosis_action_counts.get("role_assignment", 0) + diagnosis_action_counts.get("validation_role_assignment", 0),
    )
    group_formation_evidence = max(
        int(summary.get("group_formations") or 0),
        action_counts.get("party_formed", 0) + action_counts.get("raid_formed", 0) + action_counts.get("validation_group_formed", 0),
        diagnosis_action_counts.get("party_formed", 0) + diagnosis_action_counts.get("raid_formed", 0) + diagnosis_action_counts.get("validation_group_formed", 0),
    )
    target_priority_evidence = max(
        int(summary.get("target_priority_decisions") or 0),
        action_counts.get("target_priority", 0) + action_counts.get("target_switch", 0) + action_counts.get("validation_target_priority", 0),
        diagnosis_action_counts.get("target_priority", 0) + diagnosis_action_counts.get("target_switch", 0) + diagnosis_action_counts.get("validation_target_priority", 0),
    )
    interrupt_evidence = max(
        int(summary.get("interrupt_success") or 0),
        int(summary.get("assigned_interrupt_success") or 0),
        action_counts.get("interrupt", 0) + action_counts.get("interrupt_success", 0) + action_counts.get("assigned_interrupt_success", 0) + action_counts.get("validation_interrupt", 0),
        diagnosis_action_counts.get("interrupt", 0) + diagnosis_action_counts.get("interrupt_success", 0) + diagnosis_action_counts.get("assigned_interrupt_success", 0) + diagnosis_action_counts.get("validation_interrupt", 0),
    )
    healer_assignment_evidence = max(
        int(summary.get("healer_assignments") or 0),
        action_counts.get("healer_assignment", 0) + action_counts.get("validation_route_group_heal", 0) + action_counts.get("trash_heal", 0) + action_counts.get("external_defensive", 0),
        diagnosis_action_counts.get("healer_assignment", 0) + diagnosis_action_counts.get("validation_route_group_heal", 0) + diagnosis_action_counts.get("trash_heal", 0) + diagnosis_action_counts.get("external_defensive", 0),
    )
    tank_positioning_evidence = max(
        int(summary.get("tank_positioning") or 0),
        action_counts.get("validation_route_tank_boss", 0) + result_counts.get("force_tank_focus", 0),
        diagnosis_action_counts.get("validation_route_tank_boss", 0) + diagnosis_result_counts.get("force_tank_focus", 0),
    )
    regrouping_evidence = max(
        int(summary.get("regroups") or 0),
        action_counts.get("validation_route_regroup", 0) + action_counts.get("regroup", 0) + action_counts.get("validation_route_hold_anchor", 0),
        diagnosis_action_counts.get("validation_route_regroup", 0) + diagnosis_action_counts.get("regroup", 0) + diagnosis_action_counts.get("validation_route_hold_anchor", 0),
    )
    recovery_evidence = max(
        int(summary.get("recovery_events") or 0),
        stuck_events + unstuck_failures + repath_events,
        action_counts.get("validation_route_recovery", 0) + action_counts.get("death", 0) + action_counts.get("dead_recovery", 0),
        diagnosis_action_counts.get("validation_route_recovery", 0) + diagnosis_action_counts.get("death", 0) + diagnosis_action_counts.get("dead_recovery", 0),
    )
    instance_reset_evidence = max(
        int(summary.get("instance_resets") or 0),
        action_counts.get("instance_reset", 0) + action_counts.get("reset_stale_boss_activation", 0) + action_counts.get("bot_pool_reset", 0),
        diagnosis_action_counts.get("instance_reset", 0) + diagnosis_action_counts.get("reset_stale_boss_activation", 0) + diagnosis_action_counts.get("bot_pool_reset", 0),
    )
    active_decision_evidence = decisions > 0 or non_spawn_trace_entries > 0 or moved_diagnoses > 0 or non_wait_diagnoses > 0
    validation_route_actions = sum(count for action, count in action_counts.items() if action.startswith("validation_route") or action.startswith("move_to_validation_route"))
    validation_route_actions += sum(count for action, count in legacy_diagnosis_action_counts.items() if action.startswith("validation_route") or action.startswith("move_to_validation_route"))
    boss_engagement_actions = sum(action_counts.get(action, 0) + legacy_diagnosis_action_counts.get(action, 0) for action in ["boss_started", "boss_action", "validation_route_tank_boss", "validation_route_group_heal"])
    trash_route_actions = (
        action_counts.get("trash_action", 0)
        + action_counts.get("validation_route_trash_action", 0)
        + legacy_diagnosis_action_counts.get("trash_action", 0)
        + legacy_diagnosis_action_counts.get("validation_route_trash_action", 0)
    )
    action_evidence_counts = {
        "party_formation": group_formation_evidence,
        "raid_formation": group_formation_evidence,
        "role_assignments": role_assignment_evidence,
        "pulls": max(trash_pulls, boss_engagement_actions),
        "target_priority": target_priority_evidence,
        "interrupts": interrupt_evidence,
        "healer_assignments": healer_assignment_evidence,
        "tank_positioning": tank_positioning_evidence,
        "regrouping": regrouping_evidence,
        "recovery": recovery_evidence,
        "instance_reset": instance_reset_evidence,
    }
    return {
        "decisions": decisions,
        "failures": failures,
        "duration_seconds": duration_seconds,
        "duration_minutes": duration_minutes,
        "moved_diagnoses": moved_diagnoses,
        "non_wait_diagnoses": non_wait_diagnoses,
        "diagnosis_codes": dict(sorted(diagnosis_codes.items())),
        "diagnosis_severities": dict(sorted(diagnosis_severities.items())),
        "bot_not_loaded_diagnoses": diagnosis_codes.get("bot_not_loaded", 0),
        "error_diagnoses": diagnosis_severities.get("error", 0),
        "non_spawn_trace_entries": non_spawn_trace_entries,
        "quest_objective_progress": quest_progress,
        "quests_accepted": quests_accepted,
        "quests_completed": quests_completed,
        "hub_acceptance_actions": hub_acceptance_actions,
        "kills": kills,
        "teacher_assisted_kills": teacher_assisted_kills,
        "kill_evidence": kill_evidence,
        "boss_kill_evidence": boss_kill_evidence,
        "trash_action_evidence": trash_action_evidence,
        "trash_pulls": trash_pulls,
        "gear_upgrades": gear_upgrades,
        "action_names": sorted(action_names),
        "action_counts": dict(sorted(action_counts.items())),
        "result_counts": dict(sorted(result_counts.items())),
        "diagnosis_action_counts": dict(sorted(diagnosis_action_counts.items())),
        "diagnosis_result_counts": dict(sorted(diagnosis_result_counts.items())),
        "role_assignment_evidence": role_assignment_evidence,
        "group_formation_evidence": group_formation_evidence,
        "target_priority_evidence": target_priority_evidence,
        "interrupt_evidence": interrupt_evidence,
        "healer_assignment_evidence": healer_assignment_evidence,
        "tank_positioning_evidence": tank_positioning_evidence,
        "regrouping_evidence": regrouping_evidence,
        "recovery_evidence": recovery_evidence,
        "instance_reset_evidence": instance_reset_evidence,
        "validation_evidence_counts": action_evidence_counts,
        "validation_evidence_ready": {name: count > 0 for name, count in sorted(action_evidence_counts.items())},
        "stuck_events": stuck_events,
        "unstuck_failures": unstuck_failures,
        "repath_events": repath_events,
        "validation_route_actions": validation_route_actions,
        "boss_engagement_actions": boss_engagement_actions,
        "trash_route_actions": trash_route_actions,
        "validation_route_prerequisite_repeats": action_counts.get("validation_route_prerequisite", 0),
        "validation_route_activation_attempts": action_counts.get("validation_route_activation", 0),
        "validation_route_no_visible_target_activations": result_counts.get("activation_applied_no_visible_target", 0),
        "validation_route_force_tank_focus_repeats": result_counts.get("force_tank_focus", 0),
        "vendor_or_trainer_action": any(token in action_text for token in ["vendor", "repair", "train"]),
        "profession_action": any(token in action_text for token in ["profession", "recipe", "craft"]),
        "material_farming_action": any(token in action_text for token in ["material", "farm", "gather", "herb", "mine", "skin"]),
        "loot_action": any(token in action_text for token in ["loot", "roll", "gear_upgrade"]),
        "active_decision_evidence": active_decision_evidence,
    }


def validation_failure_labels(
    returncode: int,
    timed_out: bool,
    active_bots: int,
    target_bots: int,
    trace_count: int,
    diagnosis_count: int,
    errors: list[dict[str, str]],
    evidence: dict[str, Any],
) -> list[str]:
    labels: list[str] = []
    if timed_out:
        labels.append("worldserver_timeout")
    if returncode != 0:
        labels.append("worldserver_nonzero_return")
    if errors:
        labels.append("bot_command_error")
    if target_bots > 0 and active_bots < target_bots:
        labels.append("bot_pool_underfilled")
    if active_bots > 0 and diagnosis_count <= 0:
        labels.append("missing_diagnosis")
    if active_bots > 0 and trace_count <= 0 and not evidence.get("active_decision_evidence"):
        labels.append("missing_trace")

    boss_kills = int(evidence.get("boss_kill_evidence") or 0)
    trash_evidence = int(evidence.get("trash_action_evidence") or 0) + int(evidence.get("trash_pulls") or 0)
    route_actions = int(evidence.get("validation_route_actions") or 0)
    boss_engagement = int(evidence.get("boss_engagement_actions") or 0)
    trash_route_actions = int(evidence.get("trash_route_actions") or 0)
    activation_attempts = int(evidence.get("validation_route_activation_attempts") or 0)
    prerequisite_repeats = int(evidence.get("validation_route_prerequisite_repeats") or 0)
    no_visible_activations = int(evidence.get("validation_route_no_visible_target_activations") or 0)
    force_tank_focus = int(evidence.get("validation_route_force_tank_focus_repeats") or 0)
    stuck_events = int(evidence.get("stuck_events") or 0)
    unstuck_failures = int(evidence.get("unstuck_failures") or 0)
    repath_events = int(evidence.get("repath_events") or 0)
    action_counts = evidence.get("action_counts") if isinstance(evidence.get("action_counts"), dict) else {}
    repeated_deaths = int(action_counts.get("repeated_death") or 0)
    deaths = max(int(evidence.get("deaths") or 0), int(action_counts.get("death") or 0))
    bot_not_loaded_diagnoses = int(evidence.get("bot_not_loaded_diagnoses") or 0)
    error_diagnoses = int(evidence.get("error_diagnoses") or 0)

    if bot_not_loaded_diagnoses > 0:
        labels.append("bot_lifecycle_not_loaded")
    elif error_diagnoses > 0:
        labels.append("bot_diagnosis_error")

    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0:
        if boss_engagement > 0:
            labels.append("boss_attempt_no_kill")
        elif activation_attempts > 0:
            labels.append("validation_route_activation_no_engagement")
        else:
            labels.append("validation_route_no_engagement")
    if route_actions > 0 and trash_route_actions > 0 and trash_evidence <= 0:
        labels.append("trash_route_no_engagement")
    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and prerequisite_repeats >= 4:
        labels.append("validation_route_prerequisite_loop")
    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and no_visible_activations >= 2 and boss_engagement <= 0:
        labels.append("validation_route_activation_target_absent")
    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and force_tank_focus >= 4 and boss_engagement <= 0:
        labels.append("validation_route_assist_focus_loop")
    if route_actions > 0 and (stuck_events >= max(8, active_bots) or unstuck_failures >= 3 or repath_events >= max(8, active_bots)):
        labels.append("validation_route_stuck_loop")
    if route_actions > 0 and (repeated_deaths >= 3 or deaths >= max(8, active_bots)):
        labels.append("validation_route_death_loop")
    if (
        active_bots > 0
        and int(evidence.get("decisions") or 0) > 0
        and int(evidence.get("kill_evidence") or 0) <= 0
        and trash_evidence <= 0
        and int(evidence.get("quest_objective_progress") or 0) <= 0
        and int(evidence.get("quests_accepted") or 0) <= 0
        and int(evidence.get("gear_upgrades") or 0) <= 0
    ):
        labels.append("no_progress_observed")

    unique: list[str] = []
    for label in labels:
        if label not in unique:
            unique.append(label)
    return unique


def live_validation_report(output: str, stages: list[str] | None = None, returncode: int = 0, timed_out: bool = False, command: list[str] | None = None, scenario_reports: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    payloads = parse_json_objects(output)
    classified = classify_payloads(payloads)
    errors = command_errors(output)
    diagnosis = classified["diagnosis"]
    trace = classified["trace"]
    status = classified["status"]
    summary = classified["summary"]

    active_bots = int(status.get("active_bots") or status.get("bots") or status.get("activeBots") or 0)
    target_bots = int(status.get("target_bots") or status.get("targetBots") or 0)
    trace_entries = count_trace_entries(trace)
    diagnosis_count = len(diagnosis_rows(diagnosis))
    evidence = live_evidence(status, diagnosis, trace, summary)
    failure_labels = validation_failure_labels(returncode, timed_out, active_bots, target_bots, trace_entries, diagnosis_count, errors, evidence)
    scenario_reports = scenario_reports or {}

    stage_rows = []
    for stage in stages or DEFAULT_STAGES:
        missing: list[str] = []
        if stage in {"movement_smoke", "kill_quest", "collect_quest", "quest_hub_batching", "trainer_visit", "vendor_repair", "profession_recipe_acquisition", "material_farming", "smart_loot"}:
            if active_bots <= 0:
                missing.append("active_autonomy_bots")
            if not diagnosis:
                missing.append("botauto_diagnose_json")
            if trace_entries <= 0:
                missing.append("botauto_trace_entries")
            if not evidence["active_decision_evidence"]:
                missing.append("active_decision_or_movement_evidence")
            if stage == "kill_quest" and evidence["kill_evidence"] <= 0:
                missing.append("kill_evidence")
            if stage in {"normal_dungeon_trash", "dungeon_boss"} and evidence["kills"] <= 0:
                missing.append("kill_evidence")
            if stage == "collect_quest" and evidence["quest_objective_progress"] <= 0 and evidence["quests_completed"] <= 0:
                missing.append("quest_progress_evidence")
            if stage == "quest_hub_batching" and evidence["quests_accepted"] <= 0:
                missing.append("quest_acceptance_evidence")
            if stage == "quest_hub_batching" and evidence["hub_acceptance_actions"] <= 0:
                missing.append("accept_hub_quests_action_evidence")
            if stage in {"trainer_visit", "vendor_repair"} and not evidence["vendor_or_trainer_action"]:
                missing.append("vendor_or_trainer_action_evidence")
            if stage == "profession_recipe_acquisition" and not evidence["profession_action"]:
                missing.append("profession_or_recipe_action_evidence")
            if stage == "material_farming" and not evidence["material_farming_action"]:
                missing.append("material_farming_action_evidence")
            if stage == "smart_loot" and evidence["gear_upgrades"] <= 0 and not evidence["loot_action"]:
                missing.append("loot_or_gear_upgrade_evidence")
        elif stage in {"normal_dungeon_trash", "dungeon_boss", "full_stonecore_clear", "raid_trash", "raid_boss", "full_blackwing_descent_clear"}:
            missing.extend(scenario_stage_missing(stage, scenario_reports))
        stage_rows.append({"stage": stage, "passed": not missing, "missing": missing})

    passed = sum(1 for row in stage_rows if row["passed"])
    return {
        "schema": "bot_live_validation_report_v1",
        "command": command or [],
        "returncode": returncode,
        "timed_out": timed_out,
        "json_payloads": len(payloads),
        "active_bots": active_bots,
        "target_bots": target_bots,
        "diagnosis_count": diagnosis_count,
        "trace_entries": trace_entries,
        "status": status,
        "diagnosis": diagnosis,
        "trace": trace,
        "summary": summary,
        "scenario_reports": scenario_reports,
        "command_errors": errors,
        "evidence": evidence,
        "failure_labels": failure_labels,
        "failure_reason": failure_labels[0] if failure_labels else None,
        "stages": stage_rows,
        "passed": passed,
        "failed": len(stage_rows) - passed,
        "all_passed": passed == len(stage_rows),
        "runtime_ml_control": "disabled_until_live_validation_passes",
    }


def read_until_console_prompt(process: subprocess.Popen[str], deadline: float, required_text: str = "") -> str:
    if process.stdout is None:
        return ""
    output: list[str] = []
    fd = process.stdout.fileno()
    while process.poll() is None and time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([fd], [], [], min(1.0, remaining))
        if not ready:
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        text = chunk.decode(errors="replace")
        output.append(text)
        joined = "".join(output)
        if required_text and required_text in joined:
            break
        if required_text and "CMD " in joined and "TC>" in joined:
            break
        if not required_text and ("TC>" in text or "TC>" in joined[-16:]):
            break
    return "".join(output)


def expected_command_output_marker(command_text: str) -> str:
    if command_text == ".botauto status":
        return '"target_bots"'
    if command_text.startswith(".botauto diagnose"):
        return '"diagnosis_schema_version"'
    if command_text.startswith(".botauto trace"):
        return '"trace_schema_version"'
    if command_text == ".botexp summary":
        return '"duration_minutes"'
    return ""


def run_worldserver(binary: Path, config: Path, timeout_sec: int, script: str, observe_sec: int = 0) -> tuple[str, int, bool, list[str]]:
    command = [str(binary), "--config", str(config)]
    if observe_sec > 0:
        deadline = time.monotonic() + timeout_sec
        explicit_start = any(line.strip() == ".botauto start" for line in script.splitlines())
        observed_autostart = False
        output_prefix = ""
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdin is not None
        try:
            output_prefix += read_until_console_prompt(process, deadline)
            waited_for_ready = False
            for raw_command in script.splitlines():
                command_text = raw_command.strip()
                if not explicit_start and not observed_autostart and should_observe_before_command(command_text):
                    if not waited_for_ready:
                        output_prefix += wait_for_bot_status_ready(process, deadline)
                        waited_for_ready = True
                    time.sleep(observe_sec)
                    observed_autostart = True
                process.stdin.write(raw_command + "\n")
                process.stdin.flush()
                if command_text == ".botauto start":
                    output_prefix += read_until_console_prompt(process, deadline)
                    if not waited_for_ready:
                        output_prefix += wait_for_bot_status_ready(process, deadline)
                        waited_for_ready = True
                    time.sleep(observe_sec)
                elif command_text.startswith("server shutdown") or command_text == "server exit":
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
                        process.stdin = None
                    shutdown_deadline = min(deadline, time.monotonic() + 10)
                    while process.poll() is None and time.monotonic() < shutdown_deadline:
                        time.sleep(0.25)
                    killed_after_shutdown = False
                    if process.poll() is None:
                        process.kill()
                        killed_after_shutdown = True
                    break
                elif command_text:
                    output_prefix += read_until_console_prompt(process, deadline, expected_command_output_marker(command_text))
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
                process.stdin = None
            remaining = max(1, int(deadline - time.monotonic()))
            output, _ = process.communicate(timeout=remaining)
            returncode = 0 if locals().get("killed_after_shutdown", False) else (process.returncode if process.returncode is not None else 0)
            return output_prefix + output, returncode, False, command
        except (BrokenPipeError, subprocess.TimeoutExpired) as exc:
            process.kill()
            output = (exc.stdout or "") if isinstance(exc, subprocess.TimeoutExpired) else ""
            if not output and process.stdout:
                output = process.stdout.read()
            return output_prefix + output, 124, True, command

    try:
        completed = subprocess.run(command, input=script, text=True, capture_output=True, timeout=timeout_sec, check=False)
        return completed.stdout + completed.stderr, completed.returncode, False, command
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return output, 124, True, command


def soap_envelope(command: str) -> bytes:
    escaped = html.escape(command, quote=True)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="urn:TC">'
        "<SOAP-ENV:Body>"
        f"<ns1:executeCommand><command>{escaped}</command></ns1:executeCommand>"
        "</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    ).encode("utf-8")


def parse_soap_result(payload: str) -> str:
    start = payload.find("<result>")
    end = payload.find("</result>")
    if start == -1 or end == -1 or end <= start:
        return payload
    return html.unescape(payload[start + len("<result>") : end])


def run_soap_commands(soap_url: str, username: str, password: str, script: str, timeout_sec: int, observe_sec: int = 0) -> tuple[str, int, bool, list[str]]:
    output_parts: list[str] = []
    auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    command = ["SOAP", soap_url]
    deadline = time.monotonic() + timeout_sec
    explicit_start = any(line.strip() == ".botauto start" for line in script.splitlines())
    observed_autostart = False
    for raw_command in script.splitlines():
        command_text = raw_command.strip()
        if not command_text:
            continue
        if observe_sec > 0 and not explicit_start and not observed_autostart and should_observe_before_command(command_text):
            output_parts.append(f"$ sleep {observe_sec}")
            time.sleep(observe_sec)
            observed_autostart = True
        remaining_float = deadline - time.monotonic()
        if remaining_float <= 0:
            return "\n".join(output_parts), 124, True, command
        remaining = max(1, int(remaining_float))
        request = urllib.request.Request(
            soap_url,
            data=soap_envelope(command_text),
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "urn:TC#executeCommand",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=remaining) as response:
                payload = response.read().decode("utf-8", errors="replace")
                output_parts.append(f"$ {command_text}")
                output_parts.append(parse_soap_result(payload))
                if observe_sec > 0 and command_text == ".botauto start":
                    output_parts.append(f"$ sleep {observe_sec}")
                    time.sleep(observe_sec)
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            output_parts.append(f"$ {command_text}")
            output_parts.append(payload)
            return "\n".join(output_parts), exc.code, False, command
        except TimeoutError:
            return "\n".join(output_parts), 124, True, command
        except OSError as exc:
            output_parts.append(f"$ {command_text}")
            output_parts.append(str(exc))
            return "\n".join(output_parts), 1, False, command
    return "\n".join(output_parts), 0, False, command


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or prepare live BotWorld validation diagnostics.")
    parser.add_argument("--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver"))
    parser.add_argument("--config", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/live_validation"))
    parser.add_argument("--timeout-sec", type=int, default=None, help="Overall command timeout. Defaults to 90 seconds for smoke checks and 900 seconds for boss-route validations.")
    parser.add_argument("--selector", default="all")
    parser.add_argument("--trace-limit", type=int, default=20)
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--force-start-command", action="store_true", help="Send .botauto start even when BotWorld.AutoStart is enabled in the selected worldserver config.")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--transport", choices=["process", "soap"], default="process")
    parser.add_argument("--soap-url", default="http://127.0.0.1:7878/")
    parser.add_argument("--soap-user")
    parser.add_argument("--soap-password")
    parser.add_argument("--observe-sec", type=int, default=None, help="Sleep after .botauto start before collecting diagnostics. Defaults to 0 seconds for smoke checks and 300 seconds for boss-route validations.")
    parser.add_argument("--reset-bot-pool", action="store_true", help="Before validation, reset volatile state for enabled bot-pool rows matching --bot-pool-tag.")
    parser.add_argument("--bot-pool-tag", action="append", default=[], help="Experiment tag substring for --reset-bot-pool. Defaults to test_account when omitted.")
    parser.add_argument("--keep-bot-pool-position", action="store_true", help="Do not move reset bot-pool characters back to race/class start positions.")
    parser.add_argument("--keep-bot-pool-quests", action="store_true", help="Do not clear quest/aura/cooldown state for reset bot-pool characters.")
    parser.add_argument("--keep-bot-pool-memory", action="store_true", help="Do not clear persistent bot memory tables for reset bot-pool characters.")
    parser.add_argument("--apply-validation-provisioning", action="store_true", help="Apply deterministic Stonecore/BWD validation account and character SQL before running diagnostics.")
    parser.add_argument("--validation-provisioning-config", type=Path, default=Path("experiments/configs/validation_provisioning_cata_001.json"))
    parser.add_argument("--gear-profiles", type=Path, default=Path("dataset/validation_gear_profiles/profiles.json"))
    parser.add_argument("--scenario-report-dir", type=Path, help="Optional directory or JSON file containing scenario live reports such as stonecore_5n.json and blackwing_descent_10n.json.")
    parser.add_argument("--validation-scenario-id", default="", help="Scenario ID this live validation run is measuring.")
    parser.add_argument("--validation-segment-id", default="", help="Boss/route segment ID this live validation run is measuring.")
    parser.add_argument("--validation-route-node-id", default="", help="Route node ID this live validation run is measuring.")
    parser.add_argument("--validation-route-label", default="", help="Human-readable route label this live validation run is measuring.")
    parser.add_argument("--validation-route-kind", default="", help="Route node kind this live validation run is measuring, such as boss or trash.")
    parser.add_argument("--validation-route-step", type=int, default=0, help="Route step number this live validation run is measuring.")
    parser.add_argument("--validation-mechanic-profile", default="", help="Mechanic profile associated with this live validation segment.")
    parser.add_argument("--validation-scenario-dir", type=Path, default=Path("dataset/validation_scenarios"), help="Directory containing validation_routes.jsonl for route-directed live validation.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input-log", type=Path)
    args = parser.parse_args()

    if str(args.validation_route_kind or "").lower() == "boss":
        args.timeout_sec = args.timeout_sec if args.timeout_sec is not None else DEFAULT_BOSS_ROUTE_TIMEOUT_SEC
        args.observe_sec = args.observe_sec if args.observe_sec is not None else DEFAULT_BOSS_ROUTE_OBSERVE_SEC
    else:
        args.timeout_sec = args.timeout_sec if args.timeout_sec is not None else DEFAULT_LIVE_VALIDATION_TIMEOUT_SEC
        args.observe_sec = args.observe_sec if args.observe_sec is not None else 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    bot_pool_tags = args.bot_pool_tag or ["test_account"]
    validation_context = validation_context_from_args(args)
    validation_route = load_validation_route(args.validation_scenario_dir, validation_context)
    pool_tag_filter = str(validation_context.get("scenario_id") or (bot_pool_tags[0] if bot_pool_tags else ""))
    effective_config = args.config
    if args.transport == "process" and not args.input_log:
        effective_config = write_validation_config(args.config, args.output_dir, pool_tag_filter, validation_route)
    config_autostart = trinity_config_bool(effective_config, "BotWorld.AutoStart", False)
    send_start_command = not args.no_start and (args.force_start_command or not config_autostart)
    script = command_script(selector=args.selector, trace_limit=args.trace_limit, start=send_start_command, stop=args.stop, exit_server=args.transport == "process")
    (args.output_dir / "commands.txt").write_text(script, encoding="utf-8")
    preparation: dict[str, Any] = {}
    scenario_reports = load_scenario_reports(args.scenario_report_dir)
    if args.reset_bot_pool:
        preparation["bot_pool_reset"] = prepare_bot_pool_reset(
            args.output_dir,
            args.config,
            bot_pool_tags,
            apply=not args.dry_run,
            reset_positions=not args.keep_bot_pool_position,
            reset_quests=not args.keep_bot_pool_quests,
            reset_memory=not args.keep_bot_pool_memory,
        )
    if args.apply_validation_provisioning:
        preparation["validation_provisioning"] = prepare_validation_provisioning(
            args.output_dir,
            args.validation_provisioning_config,
            args.gear_profiles,
            args.config,
            apply=not args.dry_run,
        )
    if validation_route and int(validation_route.get("bot_start_map_id") or 0):
        preparation["route_bot_start"] = prepare_route_bot_start(
            args.output_dir,
            validation_route,
            args.config,
            bot_pool_tags,
            apply=not args.dry_run,
        )

    if args.dry_run:
        report = {
            "schema": "bot_live_validation_report_v1",
            "dry_run": True,
            "command_script": script,
            "worldserver": str(args.worldserver),
            "config": str(effective_config),
            "base_config": str(args.config),
            "pool_tag_filter": pool_tag_filter,
            "validation_route": validation_route,
            "transport": args.transport,
            "soap_url": args.soap_url if args.transport == "soap" else "",
            "timeout_sec": args.timeout_sec,
            "observe_sec": args.observe_sec,
            "config_autostart": config_autostart,
            "start_command": send_start_command,
            "preparation": preparation,
            "scenario_reports": scenario_reports,
            "validation_context": validation_context,
            "instructions": "Run make host-world-botexp-small for attached diagnostics or execute this script without --dry-run when the worldserver binary and config are ready.",
        }
        write_json(args.output_dir / "report.json", report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.input_log:
        output = args.input_log.read_text(encoding="utf-8")
        returncode = 0
        timed_out = False
        command: list[str] = []
    else:
        if args.transport == "soap":
            if not args.soap_user or not args.soap_password:
                raise SystemExit("--soap-user and --soap-password are required with --transport soap")
            output, returncode, timed_out, command = run_soap_commands(args.soap_url, args.soap_user, args.soap_password, script, args.timeout_sec, args.observe_sec)
        else:
            output, returncode, timed_out, command = run_worldserver(args.worldserver, effective_config, args.timeout_sec, script, args.observe_sec)

    (args.output_dir / "worldserver_output.log").write_text(output, encoding="utf-8")
    report = live_validation_report(output, returncode=returncode, timed_out=timed_out, command=command, scenario_reports=scenario_reports)
    report["generated_at_unix"] = int(time.time())
    report["config_autostart"] = config_autostart
    report["config"] = str(effective_config)
    report["base_config"] = str(args.config)
    report["pool_tag_filter"] = pool_tag_filter
    report["validation_route"] = validation_route
    report["start_command"] = send_start_command
    report["preparation"] = preparation
    report["validation_context"] = validation_context
    write_json(args.output_dir / "report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if returncode == 0 and not timed_out else 1


if __name__ == "__main__":
    raise SystemExit(main())
