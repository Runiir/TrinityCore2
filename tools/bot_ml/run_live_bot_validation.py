from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import os
import select
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
import re

try:
    from .audit_role_efficiency import build_audit
    from .build_validation_provisioning import apply_gear_profiles, build_account_insert_sql, build_character_insert_sql, load_config, load_gear_profiles
    from .common import write_json
    from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
    from .live_validation_session import build_session, ensure_healthy_matching_session, live_validation_lock, stop_session
except ImportError:
    from audit_role_efficiency import build_audit
    from build_validation_provisioning import apply_gear_profiles, build_account_insert_sql, build_character_insert_sql, load_config, load_gear_profiles
    from common import write_json
    from extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
    from live_validation_session import build_session, ensure_healthy_matching_session, live_validation_lock, stop_session


DEFAULT_LIVE_VALIDATION_TIMEOUT_SEC = 90
DEFAULT_BOSS_ROUTE_OBSERVE_SEC = 300
DEFAULT_BOSS_ROUTE_TIMEOUT_SEC = 900
DEFAULT_COMPLETION_HEARTBEAT_SEC = 30
DEFAULT_NO_PROGRESS_WINDOW_SEC = 180
DEFAULT_MAX_REPEATED_DECISIONS = 20
DEFAULT_MAX_DEATH_LOOPS = 3
REPO_ROOT = Path(__file__).resolve().parents[2]


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
    "role_assignments": {"role_assignment", "validation_role_assignment", "tank_assigned", "healer_assigned", "raid_role_assignment"},
    "pulls": {"trash_action", "validation_route_trash_action", "boss_started", "boss_action", "validation_route_pull"},
    "target_priority": {"target_priority", "target_switch", "validation_target_priority", "assist_target_search_authoritative_focus", "raid_add_wave", "raid_boss_action"},
    "interrupts": {"interrupt", "interrupt_success", "assigned_interrupt_success", "validation_interrupt", "raid_interrupt"},
    "healer_assignments": {"healer_assignment", "validation_route_group_heal", "trash_heal", "external_defensive", "raid_healer_cooldown"},
    "tank_positioning": {"validation_route_tank_boss", "tank_positioning", "force_tank_focus", "move_to_validation_route_assist_target", "raid_position_anchor", "raid_boss_action"},
    "regrouping": {"validation_route_regroup", "regroup", "validation_route_hold_anchor", "move_to_validation_route_focus", "raid_position_anchor", "validation_route_complete"},
    "recovery": {"stuck_detected", "unstuck", "death", "dead_recovery", "validation_route_recovery", "raid_wipe"},
    "instance_reset": {"instance_reset"},
}


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def database_name(database_url: str) -> str:
    return (urlparse(database_url).path or "/").lstrip("/")


def qualify_sql_schema(sql: str, schema: str, database: str) -> str:
    return sql.replace(f"`{schema}`.", f"`{database.replace('`', '``')}`.")


def trinity_config_string(path: Path, key: str, default: str = "") -> str:
    if not path.exists():
        return default
    pattern = re.compile(rf'^\s*{re.escape(key)}\s*=\s*"(?P<value>[^"]*)"', re.MULTILINE)
    match = pattern.search(path.read_text(encoding="utf-8"))
    return match.group("value") if match else default


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
    if not scenario_id:
        return {}
    route_path = scenario_dir / "validation_routes.jsonl"
    if not route_path.exists():
        return {}
    rows: list[dict[str, Any]] = []
    for line in route_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("scenario_id") or "") != scenario_id:
            continue
        rows.append(row)
    rows.sort(key=lambda row: int(row.get("step") or 0))
    for generation, row in enumerate(rows, 1):
        row["route_generation"] = generation
    if route_node_id:
        return next((row for row in rows if str(row.get("route_node_id") or "") == route_node_id), {})
    route_step = int(context.get("route_step") or 0)
    route_kind = str(context.get("route_kind") or "")
    route_label = str(context.get("route_label") or "")
    mechanic_profile = str(context.get("mechanic_profile") or "")
    if not (route_step and route_kind and route_label):
        return {}
    return next(
        (
            row
            for row in rows
            if int(row.get("step") or 0) == route_step
            and str(row.get("kind") or "") == route_kind
            and str(row.get("label") or "") == route_label
            and (not mechanic_profile or str(row.get("mechanic_profile") or "") == mechanic_profile)
        ),
        {},
    )


def load_validation_routes_for_scenario(scenario_dir: Path, scenario_id: str) -> list[dict[str, Any]]:
    route_path = scenario_dir / "validation_routes.jsonl"
    if not scenario_id or not route_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in route_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("scenario_id") or "") == scenario_id and str(row.get("kind") or "") in {"trash", "boss", "travel", "regroup", "descent"} and bool(row.get("coordinates_valid", True)):
            rows.append(row)
    rows.sort(key=lambda row: int(row.get("step") or 0))
    for generation, row in enumerate(rows, 1):
        row["route_generation"] = generation
    return rows


def validation_route_manifest_payload(scenario_id: str, routes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "bot_live_validation_route_manifest_v1",
        "scenario_id": scenario_id,
        "route_count": len(routes),
        "expected_segments": [route_segment_output_name(route) for route in routes],
        "advance_mode": "terminal",
        "routes": routes,
    }


def write_validation_route_manifest(output_dir: Path, scenario_id: str, routes: list[dict[str, Any]]) -> tuple[Path, dict[str, Any]]:
    payload = validation_route_manifest_payload(scenario_id, routes)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "validation_route_manifest.json"
    write_json(manifest_path, payload)
    return manifest_path, payload


def route_segment_output_name(route: dict[str, Any]) -> str:
    step = int(route.get("step") or 0)
    label = str(route.get("label") or route.get("route_node_id") or "segment")
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"{step:02d}_{slug or 'segment'}"


def route_validation_context(scenario_id: str, route: dict[str, Any], *, include_segment: bool = True) -> dict[str, Any]:
    context: dict[str, Any] = {
        "scenario_id": scenario_id,
        "route_node_id": str(route.get("route_node_id") or ""),
        "route_label": str(route.get("label") or ""),
        "route_kind": str(route.get("kind") or ""),
        "route_step": int(route.get("step") or 0),
        "route_generation": int(route.get("route_generation") or 0),
        "mechanic_profile": str(route.get("mechanic_profile") or ""),
    }
    if include_segment:
        context["segment_id"] = route_segment_output_name(route)
    return {key: value for key, value in context.items() if value not in {"", 0}}


def route_segment_complete(report: dict[str, Any], route: dict[str, Any] | None) -> bool:
    if not route:
        return False
    transient_terminal_labels = {
        "boss_attempt_no_kill",
        "no_progress_observed",
        "semantic_progress_plateau",
        "validation_route_assist_focus_loop",
        "validation_route_stuck_loop",
    }
    if any(label not in transient_terminal_labels for label in (report.get("failure_labels") or [])):
        return False
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    context = report.get("validation_context") if isinstance(report.get("validation_context"), dict) else {}
    node_id = str(route.get("route_node_id") or context.get("route_node_id") or "")
    generation = int(route.get("route_generation") or context.get("route_generation") or 0)
    trace = report.get("trace") if isinstance(report.get("trace"), dict) else {}
    counts = scoped_validation_evidence_counts(trace_entries(trace), node_id, generation)
    required = [str(row) for row in (route.get("required_evidence") or []) if row]
    if any(int(counts.get(name) or 0) <= 0 for name in required):
        return False
    terminals = evidence.get("route_terminal_evidence") if isinstance(evidence.get("route_terminal_evidence"), list) else []
    if not any(str(row.get("route_node_id") or "") == node_id and int(row.get("route_generation") or 0) == generation for row in terminals):
        return False
    kind = str(route.get("kind") or "")
    if kind == "boss":
        kills = evidence.get("real_boss_kill_evidence") if isinstance(evidence.get("real_boss_kill_evidence"), list) else []
        return any(str(row.get("route_node_id") or "") == node_id and int(row.get("route_generation") or 0) == generation for row in kills)
    if kind == "trash":
        return int(evidence.get("trash_pulls") or 0) > 0
    return bool(required)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def render_command(command: list[str]) -> str:
    return " ".join(shell_quote(part) for part in command)


def upsert_trinity_config(text: str, key: str, value: str) -> str:
    text = text.replace("\\n", "\n")
    line = f"{key} = {value}"
    pattern = re.compile(rf"^(?P<prefix>\s*{re.escape(key)}\s*=\s*).*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip() + "\n" + line + "\n"


def route_alternate_target_entries(route: dict[str, Any]) -> list[int]:
    entries: list[int] = []
    for entry in route.get("alternate_target_entries") or []:
        entry_id = int(entry or 0)
        if entry_id > 0 and entry_id not in entries:
            entries.append(entry_id)
    return entries


def write_validation_config(
    base_config: Path,
    output_dir: Path,
    pool_tag: str = "",
    validation_route: dict[str, Any] | None = None,
    validation_route_manifest_path: Path | None = None,
) -> Path:
    route = validation_route or {}
    if not pool_tag and not route and not validation_route_manifest_path:
        return base_config
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = output_dir / "worldserver.validation.conf"
    if not base_config.exists() and not base_config.is_absolute():
        rooted = REPO_ROOT / base_config
        if rooted.exists():
            base_config = rooted
    if not base_config.exists():
        base_config = REPO_ROOT / "src/server/worldserver/worldserver.conf.dist"
    text = base_config.read_text(encoding="utf-8") if base_config.exists() else ""
    text = text.rstrip() + "\n# Generated by tools.bot_ml.run_live_bot_validation for scenario-scoped validation.\n"
    text = upsert_trinity_config(text, "BotWorld.AutoStart", "1")
    if pool_tag:
        text = upsert_trinity_config(text, "BotWorld.PoolTagFilter", f'"{pool_tag.replace(chr(34), "")}"')
    if validation_route_manifest_path:
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ManifestPath", f'"{str(validation_route_manifest_path).replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.AdvanceMode", '"terminal"')
    if route:
        expected_bot_count = int(route.get("expected_bot_count") or 0)
        if expected_bot_count > 0:
            text = upsert_trinity_config(text, "BotWorld.TargetPopulation", str(expected_bot_count))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Enable", "1")
        text = upsert_trinity_config(text, "BotWorld.SafePositionMemorySec", "900")
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ScenarioId", f'"{str(route.get("scenario_id") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.NodeId", f'"{str(route.get("route_node_id") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Generation", str(int(route.get("route_generation") or 0)))
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
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.AlternateTargetEntries", f'"{",".join(str(entry) for entry in route_alternate_target_entries(route))}"')
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
        f"DELETE pc FROM `characters`.`pet_spell_cooldown` pc JOIN `characters`.`character_pet` cp ON cp.`id` = pc.`guid` WHERE cp.`owner` IN ({guid_select});",
        f"DELETE pa FROM `characters`.`pet_aura` pa JOIN `characters`.`character_pet` cp ON cp.`id` = pa.`guid` WHERE cp.`owner` IN ({guid_select});",
        f"DELETE ps FROM `characters`.`pet_spell` ps JOIN `characters`.`character_pet` cp ON cp.`id` = ps.`guid` WHERE cp.`owner` IN ({guid_select});",
        f"DELETE FROM `characters`.`mail_items` WHERE `receiver` IN ({guid_select});",
        f"DELETE FROM `characters`.`mail` WHERE `receiver` IN ({guid_select});",
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
    auth_url = database_url_from_worldserver_conf(worldserver_conf, "LoginDatabaseInfo")
    character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")
    account_sql = qualify_sql_schema(build_account_insert_sql(config), "auth", database_name(auth_url))
    character_sql = qualify_sql_schema(build_character_insert_sql(config), "characters", database_name(character_url))
    provision_dir = output_dir / "validation_provisioning_apply"
    provision_dir.mkdir(parents=True, exist_ok=True)
    account_path = provision_dir / "provision_accounts.sql"
    character_path = provision_dir / "provision_characters.sql"
    account_path.write_text(account_sql, encoding="utf-8")
    character_path.write_text(character_sql, encoding="utf-8")

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
    character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")
    sql = qualify_sql_schema(sql, "characters", database_name(character_url))
    start_dir = output_dir / "route_bot_start"
    start_dir.mkdir(parents=True, exist_ok=True)
    sql_path = start_dir / "route_bot_start.sql"
    sql_path.write_text(sql, encoding="utf-8")
    statements = 0
    if apply:
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
    sql = qualify_sql_schema(sql, "characters", database_name(character_url))
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
    status = next(
        (
            row
            for row in reversed(payloads)
            if row.get("action") in {"botexp_status", "botauto_status"}
            or "active" in row
            or ({"active_bots", "target_bots"} <= set(row))
        ),
        {},
    )
    diagnosis = next((row for row in reversed(payloads) if row.get("diagnosis_schema_version") or row.get("diagnoses") or row.get("diagnosis")), {})
    trace_payloads = [row for row in payloads if row.get("trace_schema_version") or row.get("entries")]
    trace = combined_trace_payload(trace_payloads)
    summary = next((row for row in reversed(payloads) if row.get("summary_schema_version") or "duration_minutes" in row or "total_kills" in row or "bot_learning" in row), {})
    return {"status": status, "diagnosis": diagnosis, "trace": trace, "summary": summary}


def combined_trace_payload(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not payloads:
        return {}

    combined: dict[str, Any] = {"trace_schema_version": payloads[-1].get("trace_schema_version", 1), "entries": []}
    seen: set[tuple[Any, ...]] = set()

    def add_entry(entry: dict[str, Any], bot_guid: Any = None, bot_name: Any = None, source_slot: int = 0) -> None:
        row = dict(entry)
        if bot_guid is not None and "bot_guid" not in row:
            row["bot_guid"] = bot_guid
        if bot_name is not None and "bot_name" not in row:
            row["bot_name"] = bot_name
        if row.get("sequence") is not None or row.get("timestamp_ms") is not None:
            key = (
                row.get("bot_guid"),
                row.get("sequence"),
                row.get("timestamp_ms"),
                row.get("action"),
                row.get("situation"),
                row.get("result"),
                row.get("target_id"),
            )
        else:
            key = (
                "unsequenced",
                source_slot,
                row.get("bot_guid"),
                row.get("action"),
                row.get("situation"),
                row.get("result"),
                row.get("target_id"),
            )
        if key in seen:
            return
        seen.add(key)
        combined["entries"].append(row)

    for payload in payloads:
        for source_slot, entry in enumerate(payload.get("entries") or []):
            if isinstance(entry, dict):
                add_entry(entry, payload.get("bot_guid"), payload.get("bot_name"), source_slot)
        for bot in payload.get("bots") or []:
            if not isinstance(bot, dict):
                continue
            for source_slot, entry in enumerate(bot.get("entries") or []):
                if isinstance(entry, dict):
                    add_entry(entry, bot.get("bot_guid"), bot.get("bot_name"), source_slot)

    return combined


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


def bot_status_snapshot(output: str) -> dict[str, Any] | None:
    """Return the latest bot status, preserving an explicit inactive state."""
    payloads = parse_json_objects(output)
    for row in reversed(payloads):
        if not isinstance(row, dict):
            continue
        if row.get("action") not in {"botexp_status", "botauto_status"} and not ({"active", "active_bots", "target_bots", "bots"} & set(row)):
            continue
        active_bots = int(row.get("active_bots") or row.get("bots") or row.get("activeBots") or 0)
        target_bots = int(row.get("target_bots") or row.get("targetBots") or 0)
        active_value = row.get("active")
        active = bool(active_value) if active_value is not None else active_bots > 0
        return {"active": active, "active_bots": active_bots, "target_bots": target_bots, "payload": row}
    return None


def bot_status_ready(output: str) -> bool:
    return bot_status_state(output) is True


def bot_status_state(output: str) -> bool | None:
    status = bot_status_snapshot(output)
    if status is None:
        return None
    if not status["active"] or status["active_bots"] <= 0:
        return False
    target_bots = int(status["target_bots"])
    return target_bots <= 0 or int(status["active_bots"]) >= target_bots


def poll_bot_status(
    execute_command: Callable[[str, int], tuple[str, int, bool]],
    deadline: float,
    *,
    poll_sec: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, dict[str, Any] | None, int, bool]:
    """Poll a transport-neutral status command until it is ready or inactive."""
    output_parts: list[str] = []
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        output, returncode, timed_out = execute_command(".botauto status", remaining)
        output_parts.append("$ .botauto status\n")
        output_parts.append(output)
        last_status = bot_status_snapshot(output)
        if returncode != 0 or timed_out or last_status is None or not last_status["active"] or bot_status_state(output) is True:
            return "".join(output_parts), last_status, returncode, timed_out
        sleep(min(poll_sec, max(0.0, deadline - time.monotonic())))
    return "".join(output_parts), last_status, 124, True


def wait_for_soap_command_available(
    execute_command: Callable[[str, int], tuple[str, int, bool]],
    deadline: float,
    *,
    poll_sec: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    output_parts: list[str] = []
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        output, returncode, timed_out = execute_command(".botauto status", remaining)
        output_parts.extend(("$ .botauto status\n", output))
        if returncode == 0 and not timed_out and bot_status_snapshot(output) is not None:
            return "".join(output_parts)
        sleep(min(poll_sec, max(0.0, deadline - time.monotonic())))
    raise RuntimeError("timed out waiting for reusable worldserver SOAP readiness")


def wait_for_bot_status_state(
    execute_command: Callable[[str, int], tuple[str, int, bool]],
    expected_active: bool,
    deadline: float,
    *,
    poll_sec: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, dict[str, Any] | None]:
    output_parts: list[str] = []
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        output, returncode, timed_out = execute_command(".botauto status", remaining)
        output_parts.extend(("$ .botauto status\n", output))
        status = bot_status_snapshot(output)
        if status is not None:
            last_status = status
            ready = bot_status_state(output) is True
            inactive = not status["active"] and int(status["active_bots"]) == 0
            if returncode == 0 and not timed_out and ((expected_active and ready) or (not expected_active and inactive)):
                return "".join(output_parts), status
        sleep(min(poll_sec, max(0.0, deadline - time.monotonic())))
    expected = "active and ready" if expected_active else "inactive with zero active bots"
    raise RuntimeError(f"timed out waiting for BotWorld to become {expected}")


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


def route_scope(entry: dict[str, Any]) -> tuple[str, int]:
    node_id = str(entry.get("route_node_id") or "")
    generation = int(entry.get("route_generation") or 0)
    if node_id and generation > 0:
        return node_id, generation
    validation_route = entry.get("validation_route") if isinstance(entry.get("validation_route"), dict) else {}
    return str(validation_route.get("route_node_id") or ""), int(validation_route.get("route_generation") or 0)


def scoped_event_evidence(entries: list[dict[str, Any]], actions: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for entry in entries:
        if str(entry.get("action") or "") not in actions:
            continue
        node_id, generation = route_scope(entry)
        if not node_id or generation <= 0:
            continue
        scope = (node_id, generation)
        if scope in seen:
            continue
        seen.add(scope)
        rows.append({"route_node_id": node_id, "route_generation": generation})
    return rows


def scoped_validation_evidence_counts(entries: list[dict[str, Any]], node_id: str, generation: int) -> dict[str, int]:
    return {
        name: sum(
            1
            for entry in entries
            if route_scope(entry) == (node_id, generation)
            and str(entry.get("action") or entry.get("situation") or "") in actions
        )
        for name, actions in VALIDATION_EVIDENCE_ACTIONS.items()
    }


def forbidden_completion_assists(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry in entries:
        action = str(entry.get("action") or "")
        result = str(entry.get("result") or "")
        if action in {"teacher_kill_assist", "validation_route_teacher_assist"} or any(token in result for token in {"teacher_assist", "forced_kill", "force_terminal", "force_damage"}):
            rows.append({"action": action, "result": result})
    return rows


def trace_after(entry: dict[str, Any], reference: dict[str, Any]) -> bool:
    entry_timestamp = int(entry.get("timestamp_ms") or 0)
    reference_timestamp = int(reference.get("timestamp_ms") or 0)
    entry_sequence = int(entry.get("sequence") or 0)
    reference_sequence = int(reference.get("sequence") or 0)
    if entry_timestamp and reference_timestamp:
        if entry_timestamp != reference_timestamp:
            return entry_timestamp > reference_timestamp
        return bool(entry_sequence and reference_sequence and entry_sequence > reference_sequence)
    return bool(entry_sequence and reference_sequence and entry_sequence > reference_sequence)


ROUTE_FAILURE_ACTIONS = {"stuck_detected", "guardrail_repath", "objective_target_lost", "validation_route_target_lost"}
ROUTE_PROGRESS_ACTIONS = {
    "mob_killed",
    "boss_killed",
    "raid_boss_killed",
    "objective_progress",
    "validation_route_pack_terminal",
    "validation_route_terminal",
    "validation_route_segment_advance",
}
ROUTE_PROGRESS_RESOLUTIONS = {"movement_progress", "route_target_combat_progress"}


def route_failure(entry: dict[str, Any]) -> bool:
    action = str(entry.get("action") or "")
    result = str(entry.get("result") or "")
    return action in ROUTE_FAILURE_ACTIONS or (action == "unstuck" and result in {"failed", "failure"}) or "target_lost" in result


BOSS_ATTEMPT_RESET_ACTIONS = {"death", "repeated_death", "raid_wipe", "instance_reset"}
BOSS_HEALTH_PROGRESS_EPSILON = 1e-6


def boss_attempt_reset(entry: dict[str, Any]) -> bool:
    return str(entry.get("action") or "") in BOSS_ATTEMPT_RESET_ACTIONS


def boss_route_health_progress_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[tuple[dict[str, Any], tuple[str, int], tuple[str, int, int, int], float]] = []
    failures: list[tuple[dict[str, Any], tuple[str, int]]] = []
    for entry in entries:
        if boss_attempt_reset(entry):
            scope = route_scope(entry)
            if scope != ("", 0):
                failures.append((entry, scope))
        route_progress = entry.get("route_progress") if isinstance(entry.get("route_progress"), dict) else {}
        route = route_progress.get("route") if isinstance(route_progress.get("route"), dict) else {}
        target = route_progress.get("target") if isinstance(route_progress.get("target"), dict) else {}
        try:
            node_id = str(route.get("node_id") or "")
            generation = int(route.get("generation") or 0)
            target_guid = int(target.get("guid") or 0)
            target_entry = int(target.get("entry") or 0)
            health = float(target.get("hp_pct"))
        except (TypeError, ValueError):
            continue
        if (
            str(route.get("kind") or "") != "boss"
            or not node_id
            or generation <= 0
            or target_guid <= 0
            or target_entry <= 0
            or not math.isfinite(health)
            or not 0.0 < health <= 1.0
        ):
            continue
        scope = (node_id, generation)
        samples.append((entry, scope, (node_id, generation, target_guid, target_entry), health))

    ordered_groups: dict[tuple[str, tuple[str, int, int, int], tuple[int, ...]], list[tuple[dict[str, Any], float]]] = {}
    for entry, scope, target_key, health in samples:
        timestamp = int(entry.get("timestamp_ms") or 0)
        sequence = int(entry.get("sequence") or 0)
        if timestamp:
            clock = "timestamp"
        elif sequence:
            clock = "sequence"
        else:
            continue
        epoch: list[int] = []
        ambiguous = False
        for index, (failure, failure_scope) in enumerate(failures):
            if failure_scope != scope:
                continue
            failure_timestamp = int(failure.get("timestamp_ms") or 0)
            failure_sequence = int(failure.get("sequence") or 0)
            failure_clock = "timestamp" if failure_timestamp else "sequence" if failure_sequence else ""
            if failure_clock != clock:
                continue
            if trace_after(entry, failure):
                epoch.append(index)
            elif not trace_after(failure, entry):
                ambiguous = True
                break
        if not ambiguous:
            ordered_groups.setdefault((clock, target_key, tuple(epoch)), []).append((entry, health))

    progress: list[dict[str, Any]] = []
    for (clock, _target_key, _epoch), rows in ordered_groups.items():
        if clock == "timestamp":
            rows.sort(key=lambda row: (int(row[0].get("timestamp_ms") or 0), int(row[0].get("sequence") or 0)))
        else:
            rows.sort(key=lambda row: int(row[0].get("sequence") or 0))
        best_entry: dict[str, Any] | None = None
        best_health = 0.0
        for entry, health in rows:
            if best_entry is None:
                best_entry, best_health = entry, health
                continue
            if not trace_after(entry, best_entry):
                continue
            if health >= 0.95 and best_health <= 0.90:
                best_entry, best_health = entry, health
                continue
            if health < best_health - BOSS_HEALTH_PROGRESS_EPSILON:
                progress.append(entry)
                best_entry, best_health = entry, health
    return progress


def boss_route_health_progress(entries: list[dict[str, Any]]) -> int:
    return len(boss_route_health_progress_entries(entries))


DEATH_LOOP_ACTIONS = {"repeated_death", "death_loop"}
DEATH_LOOP_DURABLE_PROGRESS_ACTIONS = ROUTE_PROGRESS_ACTIONS | {
    "boss_add_killed",
    "validation_route_pack_complete",
}


def death_loop_scope(entry: dict[str, Any]) -> tuple[str, int]:
    scope = route_scope(entry)
    if scope != ("", 0):
        return scope
    route_progress = entry.get("route_progress") if isinstance(entry.get("route_progress"), dict) else {}
    route = route_progress.get("route") if isinstance(route_progress.get("route"), dict) else {}
    return str(route.get("node_id") or ""), int(route.get("generation") or 0)


def unresolved_route_death_loop_count(entries: list[dict[str, Any]]) -> int:
    progress_entries = boss_route_health_progress_entries(entries) + [
        entry
        for entry in entries
        if str(entry.get("action") or "") in DEATH_LOOP_DURABLE_PROGRESS_ACTIONS
    ]
    unresolved_by_scope: Counter[tuple[str, int]] = Counter()
    seen: set[tuple[Any, ...]] = set()
    for entry in entries:
        if str(entry.get("action") or "") not in DEATH_LOOP_ACTIONS:
            continue
        scope = death_loop_scope(entry)
        if scope == ("", 0):
            continue
        timestamp = int(entry.get("timestamp_ms") or 0)
        sequence = int(entry.get("sequence") or 0)
        if timestamp or sequence:
            key = (
                scope,
                int(entry.get("bot_guid") or 0),
                timestamp,
                sequence,
                str(entry.get("action") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
        if not any(death_loop_scope(progress) == scope and trace_after(progress, entry) for progress in progress_entries):
            unresolved_by_scope[scope] += 1
    return max(unresolved_by_scope.values(), default=0)


def is_route_progress(entry: dict[str, Any], scope: tuple[str, int]) -> bool:
    same_scope = scope == ("", 0) or route_scope(entry) == scope
    return same_scope and (
        str(entry.get("action") or "") in ROUTE_PROGRESS_ACTIONS
        or (
            not str(entry.get("blocked_current_reason") or "")
            and str(entry.get("blocked_resolved_by") or "") in ROUTE_PROGRESS_RESOLUTIONS
        )
    )


def route_failure_resolved(entries: list[dict[str, Any]], failure: dict[str, Any]) -> bool:
    scope = route_scope(failure)
    return any(trace_after(entry, failure) and is_route_progress(entry, scope) for entry in entries)


def progress_after_latest_route_failure(entries: list[dict[str, Any]]) -> bool:
    failures = [entry for entry in entries if route_failure(entry)]
    return all(route_failure_resolved(entries, failure) for failure in failures)


def scripted_activation_wait_pending(entries: list[dict[str, Any]], now_ms: int, max_wait_ms: int = 30000) -> bool:
    unresolved = [
        entry for entry in entries
        if route_failure(entry)
        and route_scope(entry) != ("", 0)
        and not route_failure_resolved(entries, entry)
    ]
    if not unresolved:
        return False
    unresolved_by_scope = Counter(route_scope(entry) for entry in unresolved)
    unscoped_unresolved = sum(
        1 for entry in entries
        if route_failure(entry)
        and route_scope(entry) == ("", 0)
        and not route_failure_resolved(entries, entry)
    )
    max_unresolved = max([unscoped_unresolved, *unresolved_by_scope.values()], default=0)
    if unscoped_unresolved >= max_unresolved:
        return False
    max_scopes = {scope for scope, count in unresolved_by_scope.items() if count == max_unresolved}
    if len(max_scopes) != 1:
        return False
    scope = next(iter(max_scopes))
    latest_failure = max(
        (entry for entry in unresolved if route_scope(entry) == scope),
        key=lambda entry: (int(entry.get("timestamp_ms") or 0), int(entry.get("sequence") or 0)),
    )
    activations = [
        entry for entry in entries
        if route_scope(entry) == scope
        and str(entry.get("action") or "") == "validation_route_activation"
        and int(entry.get("timestamp_ms") or 0) > 0
        and trace_after(entry, latest_failure)
    ]
    return any(
        now_ms >= int(activation.get("timestamp_ms") or 0)
        and now_ms - int(activation.get("timestamp_ms") or 0) <= max_wait_ms
        and route_scope(entry) == scope
        and str(entry.get("action") or "") == "validation_route_target_search"
        and str(entry.get("result") or "") == "target_seen_not_attackable"
        and int(entry.get("target_id") or 0) > 0
        and trace_after(entry, activation)
        for activation in activations
        for entry in entries
    )


def unresolved_route_stuck_count(entries: list[dict[str, Any]]) -> int:
    failures = [entry for entry in entries if route_failure(entry)]
    if not failures:
        return 0
    unresolved_by_scope = Counter(route_scope(failure) for failure in failures if not route_failure_resolved(entries, failure))
    return max(unresolved_by_scope.values(), default=0)


def confirmed_boss_death_event(entry: dict[str, Any]) -> bool:
    return (
        str(entry.get("action") or "") in {"boss_killed", "raid_boss_killed"}
        and str(entry.get("result") or "") in {"ok", "confirmed_unit_death"}
        and int(entry.get("target_id") or 0) > 0
    )


def strict_manifest_evidence(evidence: dict[str, Any], manifest: dict[str, Any]) -> dict[str, list[str]]:
    terminal_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in evidence.get("route_terminal_evidence") or []
        if isinstance(row, dict)
    }
    boss_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in evidence.get("real_boss_kill_evidence") or []
        if isinstance(row, dict)
    }
    missing_terminals = []
    missing_boss_kills = []
    for generation, route in enumerate(manifest.get("routes") or [], 1):
        if not isinstance(route, dict):
            continue
        node_id = str(route.get("route_node_id") or "")
        expected = (node_id, int(route.get("route_generation") or generation))
        if expected not in terminal_scopes:
            missing_terminals.append(node_id)
        if str(route.get("kind") or "") == "boss" and expected not in boss_scopes:
            missing_boss_kills.append(node_id)
    return {"missing_terminal_route_nodes": missing_terminals, "missing_boss_route_nodes": missing_boss_kills}


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
    if not scenario_bool(report, "clear_complete", "all_passed", "scenario_passed"):
        return False
    if not bool(report.get("completion_claim_valid")):
        return False
    mode = str(report.get("completion_evidence_mode") or report.get("scenario_evidence_mode") or "")
    modes = {str(row) for row in (report.get("scenario_evidence_modes") or [])}
    if mode == "route_segment_context" or "route_segment_context" in modes:
        return False
    if report.get("source_segments") and not bool(report.get("strict_completion_evidence")):
        return False
    return True


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


def live_evidence(
    status: dict[str, Any],
    diagnosis: dict[str, Any],
    trace: dict[str, Any],
    summary: dict[str, Any],
    validation_context: dict[str, Any] | None = None,
    raw_output: str = "",
) -> dict[str, Any]:
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
    raw_manifest_complete_count = len(re.findall(r'"action"\s*:\s*"validation_route_manifest_complete"', raw_output or ""))
    if raw_manifest_complete_count:
        action_names.add("validation_route_manifest_complete")
        action_counts["validation_route_manifest_complete"] = max(
            action_counts.get("validation_route_manifest_complete", 0),
            raw_manifest_complete_count,
        )
    diagnosis_result_counts = Counter()
    stuck_events = max(int(status.get("stuck") or 0), int(summary.get("stuck_events") or 0), action_counts.get("stuck_detected", 0))
    unresolved_route_stuck_events = unresolved_route_stuck_count(entries)
    failures = [entry for entry in entries if route_failure(entry)]
    if failures and not any(route_failure_resolved(entries, failure) for failure in failures):
        unresolved_route_stuck_events = max(unresolved_route_stuck_events, stuck_events)
    unstuck_failures = sum(1 for entry in entries if str(entry.get("action") or "") == "unstuck" and str(entry.get("result") or "") in {"failed", "failure"})
    repath_events = result_counts.get("repath", 0)
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
    teacher_assisted_kills = sum(1 for entry in entries if str(entry.get("action") or "") == "teacher_kill_assist")
    forbidden_assists = forbidden_completion_assists(entries)
    route_terminal_evidence = scoped_event_evidence(entries, {"validation_route_terminal"})
    status_route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    terminal_scopes = {(row["route_node_id"], row["route_generation"]) for row in route_terminal_evidence}
    for row in status_route.get("terminal_evidence") or []:
        if not isinstance(row, dict):
            continue
        scope = (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        if not scope[0] or scope[1] <= 0 or scope in terminal_scopes:
            continue
        terminal_scopes.add(scope)
        route_terminal_evidence.append({"route_node_id": scope[0], "route_generation": scope[1]})
    manifest_completion_evidence = scoped_event_evidence(entries, {"validation_route_manifest_complete"})
    if bool(status_route.get("manifest_complete")):
        node_id = str(status_route.get("node_id") or "")
        generation = int(status_route.get("generation") or status_route.get("manifest_count") or 0)
        if node_id and generation > 0:
            manifest_completion_evidence = [{"route_node_id": node_id, "route_generation": generation}]
    real_boss_kill_evidence = scoped_event_evidence(
        [entry for entry in entries if confirmed_boss_death_event(entry)],
        {"boss_killed", "raid_boss_killed"},
    )
    boss_scopes = {(row["route_node_id"], row["route_generation"]) for row in real_boss_kill_evidence}
    for row in status_route.get("boss_death_evidence") or []:
        if not isinstance(row, dict) or not confirmed_boss_death_event({"action": "boss_killed", **row}):
            continue
        scope = (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        if not scope[0] or scope[1] <= 0 or scope in boss_scopes:
            continue
        boss_scopes.add(scope)
        real_boss_kill_evidence.append({"route_node_id": scope[0], "route_generation": scope[1]})
    post_failure_progress = progress_after_latest_route_failure(entries)
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
    def max_diagnosis_evidence(name: str) -> int:
        values: list[int] = []
        for row in diagnoses:
            evidence_rows = nested_get(row, ["diagnosis", "evidence"], [])
            if not isinstance(evidence_rows, list):
                continue
            for item in evidence_rows:
                if not isinstance(item, dict) or str(item.get("name") or "") != name:
                    continue
                value = item.get("value")
                if isinstance(value, bool):
                    values.append(1 if value else 0)
                    continue
                try:
                    values.append(int(value or 0))
                except (TypeError, ValueError):
                    pass
        return max(values, default=0)

    route_no_progress_diagnoses = 0

    def count_route_progress(route_progress: Any) -> None:
        nonlocal route_no_progress_diagnoses
        if not isinstance(route_progress, dict):
            return
        no_progress = route_progress.get("no_progress") if isinstance(route_progress.get("no_progress"), dict) else {}
        try:
            count = int(no_progress.get("count") or 0)
            threshold = int(no_progress.get("threshold") or 0)
        except (TypeError, ValueError):
            return
        if threshold > 0 and count >= threshold:
            route_no_progress_diagnoses += 1

    for row in diagnoses:
        route_progress = nested_get(row, ["diagnosis", "route_progress"], None)
        if not isinstance(route_progress, dict):
            route_progress = nested_get(row, ["snapshot", "route_progress"], None)
        count_route_progress(route_progress)

    for entry in entries:
        count_route_progress(entry.get("route_progress") if isinstance(entry, dict) else None)

    route_combat_progress_diagnoses = boss_route_health_progress(entries)

    action_text = " ".join(sorted(action_names)).lower()
    quest_progress = max(int(status.get("quest_objective_progress") or 0), int(summary.get("quest_objective_progress") or 0))
    quests_accepted = max(int(status.get("quests_accepted") or 0), int(summary.get("quests_accepted") or 0), quest_acceptance_actions)
    quests_completed = max(int(status.get("quests_completed") or 0), int(summary.get("quests_completed") or 0), quest_completion_actions)
    kills = max(
        int(status.get("kills") or 0),
        int(summary.get("total_kills") or 0),
        action_counts.get("mob_killed", 0),
        action_counts.get("dungeon_trash_cleared", 0),
    )
    boss_kill_evidence = len(real_boss_kill_evidence)
    trash_action_evidence = sum(
        count
        for action, count in action_counts.items()
        if action in {"trash_action", "trash_heal", "validation_route_trash_action", "dungeon_trash_cleared", "raid_trash_cleared", "mob_killed"}
    )
    trash_action_evidence += sum(
        count
        for action, count in legacy_diagnosis_action_counts.items()
        if action in {"trash_action", "trash_heal", "validation_route_trash_action", "dungeon_trash_cleared", "raid_trash_cleared"}
    )
    validation_route_actions = sum(count for action, count in action_counts.items() if action.startswith("validation_route") or action.startswith("move_to_validation_route"))
    validation_route_actions += sum(count for action, count in legacy_diagnosis_action_counts.items() if action.startswith("validation_route") or action.startswith("move_to_validation_route"))
    trash_route_actions = (
        action_counts.get("trash_action", 0)
        + action_counts.get("validation_route_trash_action", 0)
        + legacy_diagnosis_action_counts.get("trash_action", 0)
        + legacy_diagnosis_action_counts.get("validation_route_trash_action", 0)
    )
    context = validation_context or {}
    route_kill_trash_evidence = kills if str(context.get("route_kind") or "").lower() == "trash" and validation_route_actions > 0 else 0
    trash_pulls = max(
        int(summary.get("trash_pulls") or 0),
        int(summary.get("trash_kills") or 0),
        int(summary.get("trash_packs_cleared") or 0),
        trash_action_evidence,
        route_kill_trash_evidence,
    )
    kill_evidence = kills + teacher_assisted_kills
    gear_upgrades = max(int(status.get("gear_upgrades") or 0), int(summary.get("gear_upgrades") or 0))
    role_assignment_evidence = max(
        int(summary.get("role_assignments") or 0),
        action_counts.get("role_assignment", 0) + action_counts.get("validation_role_assignment", 0) + action_counts.get("raid_role_assignment", 0),
        diagnosis_action_counts.get("role_assignment", 0) + diagnosis_action_counts.get("validation_role_assignment", 0) + diagnosis_action_counts.get("raid_role_assignment", 0),
    )
    group_formation_evidence = max(
        int(summary.get("group_formations") or 0),
        int(summary.get("raid_formations") or 0),
        action_counts.get("party_formed", 0) + action_counts.get("raid_formed", 0) + action_counts.get("validation_group_formed", 0),
        diagnosis_action_counts.get("party_formed", 0) + diagnosis_action_counts.get("raid_formed", 0) + diagnosis_action_counts.get("validation_group_formed", 0),
    )
    target_priority_evidence = max(
        int(summary.get("target_priority_decisions") or 0),
        action_counts.get("target_priority", 0) + action_counts.get("target_switch", 0) + action_counts.get("validation_target_priority", 0) + action_counts.get("raid_add_wave", 0) + action_counts.get("raid_boss_action", 0),
        diagnosis_action_counts.get("target_priority", 0) + diagnosis_action_counts.get("target_switch", 0) + diagnosis_action_counts.get("validation_target_priority", 0) + diagnosis_action_counts.get("raid_add_wave", 0) + diagnosis_action_counts.get("raid_boss_action", 0),
    )
    interrupt_evidence = max(
        int(summary.get("interrupt_success") or 0),
        int(summary.get("assigned_interrupt_success") or 0),
        action_counts.get("interrupt", 0) + action_counts.get("interrupt_success", 0) + action_counts.get("assigned_interrupt_success", 0) + action_counts.get("validation_interrupt", 0) + action_counts.get("raid_interrupt", 0),
        diagnosis_action_counts.get("interrupt", 0) + diagnosis_action_counts.get("interrupt_success", 0) + diagnosis_action_counts.get("assigned_interrupt_success", 0) + diagnosis_action_counts.get("validation_interrupt", 0) + diagnosis_action_counts.get("raid_interrupt", 0),
    )
    healer_assignment_evidence = max(
        int(summary.get("healer_assignments") or 0),
        action_counts.get("healer_assignment", 0) + action_counts.get("validation_route_group_heal", 0) + action_counts.get("trash_heal", 0) + action_counts.get("external_defensive", 0) + action_counts.get("raid_healer_cooldown", 0),
        diagnosis_action_counts.get("healer_assignment", 0) + diagnosis_action_counts.get("validation_route_group_heal", 0) + diagnosis_action_counts.get("trash_heal", 0) + diagnosis_action_counts.get("external_defensive", 0) + diagnosis_action_counts.get("raid_healer_cooldown", 0),
    )
    if str(context.get("route_kind") or "").lower() == "boss":
        healer_assignment_evidence = max(
            healer_assignment_evidence,
            action_counts.get("validation_target_priority", 0) if result_counts.get("assist_tank_focus", 0) > 0 else 0,
            diagnosis_action_counts.get("validation_target_priority", 0) if diagnosis_result_counts.get("assist_tank_focus", 0) > 0 else 0,
        )
    tank_positioning_evidence = max(
        int(summary.get("tank_positioning") or 0),
        action_counts.get("validation_route_tank_boss", 0)
        + action_counts.get("move_to_validation_route_assist_target", 0)
        + action_counts.get("raid_position_anchor", 0)
        + action_counts.get("raid_boss_action", 0)
        + result_counts.get("force_tank_focus", 0)
        + result_counts.get("assist_tank_focus", 0),
        diagnosis_action_counts.get("validation_route_tank_boss", 0)
        + diagnosis_action_counts.get("move_to_validation_route_assist_target", 0)
        + diagnosis_action_counts.get("raid_position_anchor", 0)
        + diagnosis_action_counts.get("raid_boss_action", 0)
        + diagnosis_result_counts.get("force_tank_focus", 0)
        + diagnosis_result_counts.get("assist_tank_focus", 0),
    )
    regrouping_evidence = max(
        int(summary.get("regroups") or 0),
        action_counts.get("validation_route_regroup", 0) + action_counts.get("regroup", 0) + action_counts.get("validation_route_hold_anchor", 0) + action_counts.get("move_to_validation_route_focus", 0) + action_counts.get("raid_position_anchor", 0) + action_counts.get("validation_route_complete", 0),
        diagnosis_action_counts.get("validation_route_regroup", 0) + diagnosis_action_counts.get("regroup", 0) + diagnosis_action_counts.get("validation_route_hold_anchor", 0) + diagnosis_action_counts.get("move_to_validation_route_focus", 0) + diagnosis_action_counts.get("raid_position_anchor", 0) + diagnosis_action_counts.get("validation_route_complete", 0),
    )
    recovery_evidence = max(
        int(summary.get("recovery_events") or 0),
        stuck_events + unstuck_failures + repath_events,
        action_counts.get("validation_route_recovery", 0) + action_counts.get("death", 0) + action_counts.get("dead_recovery", 0) + action_counts.get("raid_wipe", 0),
        diagnosis_action_counts.get("validation_route_recovery", 0) + diagnosis_action_counts.get("death", 0) + diagnosis_action_counts.get("dead_recovery", 0) + diagnosis_action_counts.get("raid_wipe", 0),
    )
    instance_reset_evidence = max(
        int(summary.get("instance_resets") or 0),
        action_counts.get("instance_reset", 0),
        diagnosis_action_counts.get("instance_reset", 0),
    )
    active_decision_evidence = decisions > 0 or non_spawn_trace_entries > 0 or moved_diagnoses > 0 or non_wait_diagnoses > 0
    boss_engagement_actions = sum(action_counts.get(action, 0) + legacy_diagnosis_action_counts.get(action, 0) for action in ["boss_started", "boss_action", "validation_route_tank_boss", "validation_route_group_heal"])
    action_evidence_counts = {
        "party_formation": group_formation_evidence,
        "raid_formation": group_formation_evidence,
        "role_assignments": role_assignment_evidence,
        "pulls": max(trash_pulls, boss_engagement_actions, boss_kill_evidence),
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
        "forbidden_completion_assists": forbidden_assists,
        "kill_evidence": kill_evidence,
        "boss_kill_evidence": boss_kill_evidence,
        "real_boss_kill_evidence": real_boss_kill_evidence,
        "route_terminal_evidence": route_terminal_evidence,
        "manifest_completion_evidence": manifest_completion_evidence,
        "post_failure_progress": post_failure_progress,
        "scripted_activation_wait_pending": scripted_activation_wait_pending(entries, int(time.time() * 1000)),
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
        "unresolved_route_stuck_events": unresolved_route_stuck_events,
        "unstuck_failures": unstuck_failures,
        "repath_events": repath_events,
        "validation_route_actions": validation_route_actions,
        "validation_route_manifest_complete": action_counts.get("validation_route_manifest_complete", 0),
        "validation_route_no_progress_diagnoses": route_no_progress_diagnoses,
        "validation_route_combat_progress_diagnoses": route_combat_progress_diagnoses,
        "unresolved_route_death_loop_events": unresolved_route_death_loop_count(entries),
        "boss_engagement_actions": boss_engagement_actions,
        "trash_route_actions": trash_route_actions,
        "validation_route_prerequisite_repeats": action_counts.get("validation_route_prerequisite", 0),
        "validation_route_activation_attempts": max(
            action_counts.get("validation_route_activation", 0),
            max_diagnosis_evidence("validation_route_activation_attempts"),
        ),
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
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
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
    kill_evidence = int(evidence.get("kill_evidence") or 0)
    trash_evidence = int(evidence.get("trash_action_evidence") or 0) + int(evidence.get("trash_pulls") or 0)
    route_actions = int(evidence.get("validation_route_actions") or 0)
    boss_engagement = int(evidence.get("boss_engagement_actions") or 0)
    trash_route_actions = int(evidence.get("trash_route_actions") or 0)
    route_no_progress_diagnoses = int(evidence.get("validation_route_no_progress_diagnoses") or 0)
    route_combat_progress_diagnoses = int(evidence.get("validation_route_combat_progress_diagnoses") or 0)
    activation_attempts = int(evidence.get("validation_route_activation_attempts") or 0)
    prerequisite_repeats = int(evidence.get("validation_route_prerequisite_repeats") or 0)
    no_visible_activations = int(evidence.get("validation_route_no_visible_target_activations") or 0)
    force_tank_focus = int(evidence.get("validation_route_force_tank_focus_repeats") or 0)
    unresolved_route_stuck_events = int(evidence.get("unresolved_route_stuck_events") or 0)
    action_counts = evidence.get("action_counts") if isinstance(evidence.get("action_counts"), dict) else {}
    result_counts = evidence.get("result_counts") if isinstance(evidence.get("result_counts"), dict) else {}
    unresolved_death_loop_events = int(evidence.get("unresolved_route_death_loop_events") or 0)
    bot_not_loaded_diagnoses = int(evidence.get("bot_not_loaded_diagnoses") or 0)
    error_diagnoses = int(evidence.get("error_diagnoses") or 0)
    post_failure_progress = bool(evidence.get("post_failure_progress"))
    recovered_route_stuck = (
        action_counts.get("validation_route_recovery", 0) > 0
        and result_counts.get("validation_route_stuck_safe_memory", 0) > 0
        and post_failure_progress
        and (int(evidence.get("kill_evidence") or 0) > 0 or trash_route_actions > 0 or boss_engagement > 0)
    )
    recovered_by_route_progress = (
        post_failure_progress
        and int(evidence.get("moved_diagnoses") or 0) > 0
        and route_no_progress_diagnoses <= 0
        and (int(evidence.get("kill_evidence") or 0) > 0 or trash_route_actions > 0 or boss_engagement > 0)
    )
    recovered_by_active_route_combat = (
        post_failure_progress
        and route_no_progress_diagnoses <= 0
        and (int((evidence.get("diagnosis_codes") or {}).get("normal_combat") or 0) > 0 or route_combat_progress_diagnoses > 0)
        and (int(evidence.get("kill_evidence") or 0) > 0 or trash_evidence > 0 or boss_engagement > 0)
    )

    route_diagnosis_progress = route_actions > 0 and (
        trash_evidence > 0
        or kill_evidence > 0
        or boss_engagement > 0
        or int(evidence.get("moved_diagnoses") or 0) > 0
        or route_combat_progress_diagnoses > 0
    )

    if bot_not_loaded_diagnoses > 0:
        labels.append("bot_lifecycle_not_loaded")
    elif error_diagnoses > 0 and not route_diagnosis_progress:
        labels.append("bot_diagnosis_error")

    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and kill_evidence <= 0:
        if boss_engagement > 0:
            labels.append("boss_attempt_no_kill")
        elif activation_attempts > 0:
            labels.append("validation_route_activation_no_engagement")
        else:
            labels.append("validation_route_no_engagement")
    if route_actions > 0 and trash_route_actions > 0 and trash_evidence <= 0:
        labels.append("trash_route_no_engagement")
    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and kill_evidence <= 0 and prerequisite_repeats >= 4:
        labels.append("validation_route_prerequisite_loop")
    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and kill_evidence <= 0 and no_visible_activations >= 2 and boss_engagement <= 0:
        labels.append("validation_route_activation_target_absent")
    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and kill_evidence <= 0 and force_tank_focus >= 4 and boss_engagement <= 0:
        labels.append("validation_route_assist_focus_loop")
    pending_scripted_activation = bool(evidence.get("scripted_activation_wait_pending"))
    if (route_actions > 0
        and not pending_scripted_activation
        and not post_failure_progress
        and unresolved_route_stuck_events >= max(8, active_bots)
        and not recovered_route_stuck
        and not recovered_by_route_progress
        and not recovered_by_active_route_combat):
        labels.append("validation_route_stuck_loop")
    if route_actions > 0 and unresolved_death_loop_events >= max_death_loops:
        labels.append("validation_route_death_loop")
    if route_actions > 0 and route_no_progress_diagnoses > 0:
        labels.append("no_progress_observed")
    if (
        active_bots > 0
        and int(evidence.get("decisions") or 0) > 0
        and int(evidence.get("kill_evidence") or 0) <= 0
        and boss_kills <= 0
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


def progress_counters_from_evidence(evidence: dict[str, Any]) -> dict[str, int]:
    action_counts = evidence.get("action_counts") if isinstance(evidence.get("action_counts"), dict) else {}
    return {
        "decisions": int(evidence.get("decisions") or 0),
        "moved_diagnoses": int(evidence.get("moved_diagnoses") or 0),
        "non_spawn_trace_entries": int(evidence.get("non_spawn_trace_entries") or 0),
        "quest_objective_progress": int(evidence.get("quest_objective_progress") or 0),
        "quests_accepted": int(evidence.get("quests_accepted") or 0),
        "quests_completed": int(evidence.get("quests_completed") or 0),
        "kills": int(evidence.get("kills") or 0),
        "teacher_assisted_kills": int(evidence.get("teacher_assisted_kills") or 0),
        "boss_kill_evidence": int(evidence.get("boss_kill_evidence") or 0),
        "boss_engagement_actions": int(evidence.get("boss_engagement_actions") or 0),
        "trash_pulls": int(evidence.get("trash_pulls") or 0),
        "gear_upgrades": int(evidence.get("gear_upgrades") or 0),
        "validation_route_actions": int(evidence.get("validation_route_actions") or 0),
        "validation_route_terminal_evidence": len(evidence.get("route_terminal_evidence") or []),
        "validation_route_manifest_complete": int(evidence.get("validation_route_manifest_complete") or 0),
        "validation_route_no_progress_diagnoses": int(evidence.get("validation_route_no_progress_diagnoses") or 0),
        "validation_route_combat_progress_diagnoses": int(evidence.get("validation_route_combat_progress_diagnoses") or 0),
        "repeated_decisions": int(action_counts.get("repeated_decision") or action_counts.get("decision_repeated") or 0),
        "death_loop_events": int(evidence.get("unresolved_route_death_loop_events") or 0),
        "stuck_events": int(evidence.get("stuck_events") or 0),
        "repath_events": int(evidence.get("repath_events") or 0),
    }


def watchdog_state(
    evidence: dict[str, Any],
    failure_labels: list[str],
    *,
    heartbeat_sec: int = DEFAULT_COMPLETION_HEARTBEAT_SEC,
    no_progress_window_sec: int = DEFAULT_NO_PROGRESS_WINDOW_SEC,
    max_repeated_decisions: int = DEFAULT_MAX_REPEATED_DECISIONS,
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
) -> dict[str, Any]:
    counters = progress_counters_from_evidence(evidence)
    progress_total = (
        counters["quest_objective_progress"]
        + counters["quests_accepted"]
        + counters["quests_completed"]
        + counters["kills"]
        + counters["boss_kill_evidence"]
        + counters["gear_upgrades"]
        + counters["validation_route_terminal_evidence"]
        + counters["validation_route_manifest_complete"]
        + counters["validation_route_combat_progress_diagnoses"]
    )
    route_motion_progress = (
        counters["validation_route_actions"] > 0
        and counters["moved_diagnoses"] > 0
        and counters["boss_engagement_actions"] <= 0
    )
    route_terminal_no_progress = counters["validation_route_no_progress_diagnoses"] > 0
    route_semantic_plateau = (
        counters["validation_route_actions"] > 0
        and counters["validation_route_manifest_complete"] <= 0
        and counters["boss_engagement_actions"] <= 0
        and counters["moved_diagnoses"] <= 0
        and counters["validation_route_combat_progress_diagnoses"] <= 0
        and progress_total > 0
    )
    no_progress = (
        route_terminal_no_progress
        or (not route_motion_progress and ("no_progress_observed" in failure_labels or (counters["decisions"] > 0 and progress_total <= 0)))
    )
    repeated_loop = counters["repeated_decisions"] >= max_repeated_decisions
    death_loop = counters["death_loop_events"] >= max_death_loops
    return {
        "policy": "completion-watchdog",
        "heartbeat_sec": heartbeat_sec,
        "no_progress_window_sec": no_progress_window_sec,
        "max_repeated_decisions": max_repeated_decisions,
        "max_death_loops": max_death_loops,
        "progress_total": progress_total,
        "no_progress": no_progress,
        "semantic_progress_plateau": route_semantic_plateau,
        "repeated_decision_loop": repeated_loop,
        "death_loop": death_loop,
        "progress_counters": counters,
    }


def resolved_manifest_failure_labels(
    failure_labels: list[str], evidence: dict[str, Any], manifest: dict[str, Any] | None
) -> list[str]:
    manifest = manifest or {}
    routes = manifest.get("routes") or []
    if not routes or not all(isinstance(route, dict) for route in routes):
        return failure_labels
    final_route = routes[-1]
    final_scope = (
        str(final_route.get("route_node_id") or ""),
        int(final_route.get("route_generation") or len(routes)),
    )
    completion_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in evidence.get("manifest_completion_evidence") or []
        if isinstance(row, dict)
    }
    if final_scope[0] == "" or final_scope not in completion_scopes:
        return failure_labels
    strict = strict_manifest_evidence(evidence, manifest)
    if strict["missing_terminal_route_nodes"] or strict["missing_boss_route_nodes"]:
        return failure_labels
    resolved = {
        "boss_attempt_no_kill",
        "no_progress_observed",
        "semantic_progress_plateau",
        "validation_route_assist_focus_loop",
        "validation_route_stuck_loop",
    }
    return [label for label in failure_labels if label not in resolved]


def terminal_failure_labels(failure_labels: list[str], state: dict[str, Any]) -> list[str]:
    counters = state.get("progress_counters") if isinstance(state.get("progress_counters"), dict) else {}
    route_motion_progress = (
        int(counters.get("validation_route_actions") or 0) > 0
        and int(counters.get("moved_diagnoses") or 0) > 0
        and int(counters.get("boss_engagement_actions") or 0) <= 0
        and int(counters.get("trash_pulls") or 0) <= 0
        and int(counters.get("kills") or 0) <= 0
    )
    nonterminal = {
        "boss_attempt_no_kill",
        "bot_pool_underfilled",
        "no_progress_observed",
        "trash_route_no_engagement",
        "validation_route_activation_no_engagement",
        "validation_route_no_engagement",
    }
    if route_motion_progress:
        nonterminal.add("validation_route_assist_focus_loop")
    progress_total = int(state.get("progress_total") or 0)
    if progress_total <= 0 and not route_motion_progress:
        return failure_labels
    return [label for label in failure_labels if label not in nonterminal]


def completion_reason(
    *,
    all_passed: bool,
    returncode: int,
    timed_out: bool,
    failure_labels: list[str],
    state: dict[str, Any],
    evidence: dict[str, Any] | None = None,
) -> str:
    evidence = evidence or {}
    if evidence.get("manifest_completion_evidence") and not terminal_failure_labels(failure_labels, state):
        return "validation_route_manifest_complete"
    if timed_out:
        return "emergency_wall_clock_timeout"
    if returncode != 0:
        return "worldserver_exited_nonzero"
    if all_passed and not failure_labels:
        return "success_predicates_passed"
    if state.get("death_loop"):
        return "death_loop_watchdog"
    if state.get("repeated_decision_loop"):
        return "repeated_decision_watchdog"
    if state.get("no_progress"):
        return "no_progress_watchdog"
    if terminal_failure_labels(failure_labels, state):
        return "machine_failure_predicate"
    return "incomplete_evidence"


def final_evidence_rejections(
    *,
    all_passed: bool,
    returncode: int,
    timed_out: bool,
    failure_labels: list[str],
    evidence: dict[str, Any],
    validation_context: dict[str, Any] | None = None,
    validation_route_manifest: dict[str, Any] | None = None,
    completion: str = "",
) -> list[str]:
    context = validation_context or {}
    manifest_complete = bool(evidence.get("manifest_completion_evidence"))
    rejections: list[str] = []
    if not all_passed and not manifest_complete:
        rejections.append("not_all_stages_passed")
    if timed_out:
        rejections.append("timeout_is_not_final_evidence")
    if returncode != 0:
        rejections.append("nonzero_return_is_not_final_evidence")
    if failure_labels:
        rejections.append("failure_labels_present")
    if context.get("segment_id") or context.get("route_node_id"):
        rejections.append("segment_or_route_context_is_debug_only")
    if completion in {"emergency_wall_clock_timeout", "no_progress_watchdog", "repeated_decision_watchdog", "death_loop_watchdog"}:
        rejections.append("watchdog_failure_is_not_final_evidence")
    if evidence.get("forbidden_completion_assists"):
        rejections.append("forced_or_teacher_kill_evidence")
        if int(evidence.get("teacher_assisted_kills") or 0) > 0 and not evidence.get("real_boss_kill_evidence"):
            rejections.append("teacher_assisted_only_evidence")
    if manifest_complete:
        manifest = validation_route_manifest or {}
        if not manifest.get("routes"):
            rejections.append("missing_validation_route_manifest")
        else:
            strict = strict_manifest_evidence(evidence, manifest)
            if strict["missing_terminal_route_nodes"]:
                rejections.append("missing_node_terminal_evidence")
            if strict["missing_boss_route_nodes"]:
                rejections.append("missing_real_boss_kill_evidence")
    return list(dict.fromkeys(rejections))


def attach_stonecore_role_quality_audit(
    report: dict[str, Any],
    validation_context: dict[str, Any] | None,
    validation_route_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """Make Stonecore full-clear acceptance depend on the strict role audit."""
    context = validation_context or {}
    manifest = validation_route_manifest or {}
    is_full_stonecore = (
        context.get("scenario_id") == "stonecore_5n"
        and bool(manifest.get("routes"))
        and not context.get("segment_id")
        and not context.get("route_node_id")
    )
    if not is_full_stonecore:
        return report

    source = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    audit = build_audit(report, hashlib.sha256(source).hexdigest())
    report["role_efficiency_audit"] = audit
    if audit.get("passed"):
        return report

    labels = list(report.get("failure_labels") or [])
    for label in audit.get("failure_labels") or []:
        quality_label = f"role_quality:{label}"
        if quality_label not in labels:
            labels.append(quality_label)
    if "stonecore_role_quality_audit_failed" not in labels:
        labels.append("stonecore_role_quality_audit_failed")
    report["failure_labels"] = labels
    report["failure_reason"] = labels[0]
    rejections = list(report.get("final_evidence_rejections") or [])
    for rejection in ("failure_labels_present", "stonecore_role_quality_audit_failed"):
        if rejection not in rejections:
            rejections.append(rejection)
    report["final_evidence_rejections"] = rejections
    report["acceptable_final_evidence"] = False
    report["all_passed"] = False
    report["failed"] = max(1, int(report.get("failed") or 0))
    report["completion_reason"] = "stonecore_role_quality_audit_failed"
    return report


def live_validation_report(
    output: str,
    stages: list[str] | None = None,
    returncode: int = 0,
    timed_out: bool = False,
    command: list[str] | None = None,
    scenario_reports: dict[str, dict[str, Any]] | None = None,
    validation_context: dict[str, Any] | None = None,
    validation_route_manifest: dict[str, Any] | None = None,
    duration_policy: str = "completion-watchdog",
    heartbeat_sec: int = DEFAULT_COMPLETION_HEARTBEAT_SEC,
    no_progress_window_sec: int = DEFAULT_NO_PROGRESS_WINDOW_SEC,
    max_repeated_decisions: int = DEFAULT_MAX_REPEATED_DECISIONS,
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
) -> dict[str, Any]:
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
    evidence = live_evidence(status, diagnosis, trace, summary, validation_context, output)
    failure_labels = validation_failure_labels(
        returncode,
        timed_out,
        active_bots,
        target_bots,
        trace_entries,
        diagnosis_count,
        errors,
        evidence,
        max_death_loops,
    )
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
    all_passed = passed == len(stage_rows)
    state = watchdog_state(
        evidence,
        failure_labels,
        heartbeat_sec=heartbeat_sec,
        no_progress_window_sec=no_progress_window_sec,
        max_repeated_decisions=max_repeated_decisions,
        max_death_loops=max_death_loops,
    )
    effective_failure_labels = resolved_manifest_failure_labels(
        failure_labels, evidence, validation_route_manifest
    )
    reason = completion_reason(
        all_passed=all_passed,
        returncode=returncode,
        timed_out=timed_out,
        failure_labels=effective_failure_labels,
        state=state,
        evidence=evidence,
    )
    rejections = final_evidence_rejections(
        all_passed=all_passed,
        returncode=returncode,
        timed_out=timed_out,
        failure_labels=effective_failure_labels,
        evidence=evidence,
        validation_context=validation_context,
        validation_route_manifest=validation_route_manifest,
        completion=reason,
    )
    return {
        "schema": "bot_live_validation_report_v1",
        "command": command or [],
        "duration_policy": duration_policy,
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
        "progress_counters": state["progress_counters"],
        "watchdog_state": state,
        "completion_reason": reason,
        "acceptable_final_evidence": not rejections,
        "final_evidence_rejections": rejections,
        "failure_labels": effective_failure_labels,
        "superseded_failure_labels": [label for label in failure_labels if label not in effective_failure_labels],
        "failure_reason": effective_failure_labels[0] if effective_failure_labels else None,
        "stages": stage_rows,
        "passed": passed,
        "failed": 0 if not rejections else len(stage_rows) - passed,
        "all_passed": not rejections,
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
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
        if required_text:
            marker_index = joined.find(required_text)
            if marker_index >= 0 and "TC>" in joined[marker_index + len(required_text):]:
                break
        if not required_text and ("TC>" in text or "TC>" in joined[-16:]):
            break
    return "".join(output)


def bounded_console_deadline(deadline: float, max_wait_sec: int | float) -> float:
    return min(deadline, time.monotonic() + max(1.0, float(max_wait_sec)))


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


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def heartbeat_commands_from_script(script: str) -> tuple[list[str], list[str], list[str]]:
    startup: list[str] = []
    heartbeat: list[str] = []
    cleanup: list[str] = []
    for raw_command in script.splitlines():
        command_text = raw_command.strip()
        if not command_text:
            continue
        if command_text == ".botauto start":
            startup.append(command_text)
        elif command_text == ".botauto stop":
            cleanup.append(command_text)
        elif command_text.startswith("server shutdown") or command_text == "server exit":
            continue
        else:
            heartbeat.append(command_text)
    return startup, heartbeat, cleanup


def rolling_heartbeat_report(
    output_dir: Path,
    heartbeat_index: int,
    output: str,
    returncode: int,
    timed_out: bool,
    command: list[str],
    scenario_reports: dict[str, dict[str, Any]],
    validation_context: dict[str, Any],
    duration_policy: str,
    heartbeat_sec: int,
    no_progress_window_sec: int,
    max_repeated_decisions: int,
    max_death_loops: int,
    validation_route_manifest: dict[str, Any] | None = None,
    completion_reason_override: str = "",
) -> dict[str, Any]:
    report = live_validation_report(
        output,
        returncode=returncode,
        timed_out=timed_out,
        command=command,
        scenario_reports=scenario_reports,
        validation_context=validation_context,
        validation_route_manifest=validation_route_manifest,
        duration_policy=duration_policy,
        heartbeat_sec=heartbeat_sec,
        no_progress_window_sec=no_progress_window_sec,
        max_repeated_decisions=max_repeated_decisions,
        max_death_loops=max_death_loops,
    )
    if completion_reason_override:
        report["completion_reason"] = completion_reason_override
    report["heartbeat_index"] = heartbeat_index
    report["heartbeat_generated_at_unix"] = int(time.time())
    heartbeat_path = output_dir / "heartbeats" / f"{heartbeat_index:06d}.json"
    write_json(heartbeat_path, report)
    append_jsonl(
        output_dir / "heartbeat_events.jsonl",
        {
            "heartbeat_index": heartbeat_index,
            "generated_at_unix": report["heartbeat_generated_at_unix"],
            "completion_reason": report["completion_reason"],
            "acceptable_final_evidence": report["acceptable_final_evidence"],
            "all_passed": report["all_passed"],
            "failure_labels": report["failure_labels"],
            "progress_counters": report["progress_counters"],
            "report": str(heartbeat_path),
        },
    )
    write_json(output_dir / "report.json", report)
    return report


def run_transport_completion_watchdog(
    execute_command: Callable[[str, int], tuple[str, int, bool]],
    command: list[str],
    timeout_sec: int,
    script: str,
    output_dir: Path,
    scenario_reports: dict[str, dict[str, Any]],
    validation_context: dict[str, Any],
    *,
    validation_route_manifest: dict[str, Any] | None = None,
    duration_policy: str = "completion-watchdog",
    heartbeat_sec: int = DEFAULT_COMPLETION_HEARTBEAT_SEC,
    no_progress_window_sec: int = DEFAULT_NO_PROGRESS_WINDOW_SEC,
    max_repeated_decisions: int = DEFAULT_MAX_REPEATED_DECISIONS,
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, int, bool, list[str]]:
    """Apply completion evidence watchdog policy to any command transport.

    The callback owns connection and lifecycle details; this function never sends a
    server shutdown command, making it safe for attached sessions and SOAP.
    """
    deadline = time.monotonic() + timeout_sec
    startup_commands, heartbeat_commands, cleanup_commands = heartbeat_commands_from_script(script)
    output_parts: list[str] = []
    heartbeat_index = 0
    last_progress_total = -1
    last_progress_at = time.monotonic()

    def send(command_text: str) -> tuple[int, bool]:
        remaining = max(1, int(deadline - time.monotonic()))
        output, returncode, timed_out = execute_command(command_text, remaining)
        output_parts.extend((f"$ {command_text}\n", output))
        return returncode, timed_out

    def finish(returncode: int, timed_out: bool) -> tuple[str, int, bool, list[str]]:
        if not timed_out:
            for command_text in cleanup_commands:
                cleanup_returncode, cleanup_timed_out = send(command_text)
                if cleanup_returncode != 0 or cleanup_timed_out:
                    return "".join(output_parts), cleanup_returncode, cleanup_timed_out, command
        return "".join(output_parts), returncode, timed_out, command

    for command_text in startup_commands:
        returncode, timed_out = send(command_text)
        if returncode != 0 or timed_out:
            return finish(returncode, timed_out)
    if startup_commands:
        status_output, _status, returncode, timed_out = poll_bot_status(execute_command, deadline, sleep=sleep)
        output_parts.append(status_output)
        if returncode != 0 or timed_out:
            return finish(returncode, timed_out)

    while time.monotonic() < deadline:
        sleep(min(max(1, heartbeat_sec), max(0.0, deadline - time.monotonic())))
        heartbeat_index += 1
        for command_text in heartbeat_commands:
            if time.monotonic() >= deadline:
                break
            returncode, timed_out = send(command_text)
            if returncode != 0 or timed_out:
                return finish(returncode, timed_out)
        report = rolling_heartbeat_report(
            output_dir, heartbeat_index, "".join(output_parts), 0, False, command,
            scenario_reports, validation_context, duration_policy, heartbeat_sec,
            no_progress_window_sec, max_repeated_decisions, max_death_loops,
            validation_route_manifest,
        )
        progress_total = int(report.get("watchdog_state", {}).get("progress_total") or 0)
        if progress_total > last_progress_total:
            last_progress_total = progress_total
            last_progress_at = time.monotonic()
        no_progress_expired = time.monotonic() - last_progress_at >= no_progress_window_sec
        moved_diagnoses = int(report.get("watchdog_state", {}).get("progress_counters", {}).get("moved_diagnoses") or 0)
        semantic_progress_plateau = (
            last_progress_total >= 0
            and progress_total <= last_progress_total
            and no_progress_expired
            and moved_diagnoses <= 0
        )
        if report["acceptable_final_evidence"] or report["completion_reason"] in {"repeated_decision_watchdog", "death_loop_watchdog", "machine_failure_predicate"}:
            return finish(0, False)
        if validation_route_manifest and semantic_progress_plateau:
            report["completion_reason"] = "semantic_progress_plateau_watchdog"
            report["watchdog_state"]["semantic_progress_plateau"] = True
            if "semantic_progress_plateau" not in report["failure_labels"]:
                report["failure_labels"].append("semantic_progress_plateau")
            report["failure_reason"] = report["failure_labels"][0]
            report["failed"] = max(int(report.get("failed") or 0), 1)
            report["all_passed"] = False
            report["acceptable_final_evidence"] = False
            if "failure_labels_present" not in report["final_evidence_rejections"]:
                report["final_evidence_rejections"].append("failure_labels_present")
            write_json(output_dir / "report.json", report)
            return finish(0, False)
        if report["watchdog_state"].get("no_progress") and no_progress_expired:
            report["completion_reason"] = "no_progress_watchdog"
            write_json(output_dir / "report.json", report)
            return finish(0, False)
    return finish(124, True)


def run_worldserver_completion_watchdog(
    binary: Path,
    config: Path,
    timeout_sec: int,
    script: str,
    output_dir: Path,
    scenario_reports: dict[str, dict[str, Any]],
    validation_context: dict[str, Any],
    duration_policy: str = "completion-watchdog",
    heartbeat_sec: int = DEFAULT_COMPLETION_HEARTBEAT_SEC,
    no_progress_window_sec: int = DEFAULT_NO_PROGRESS_WINDOW_SEC,
    max_repeated_decisions: int = DEFAULT_MAX_REPEATED_DECISIONS,
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
    validation_route: dict[str, Any] | None = None,
    validation_route_manifest: dict[str, Any] | None = None,
) -> tuple[str, int, bool, list[str]]:
    command = [str(binary), "--config", str(config)]
    deadline = time.monotonic() + timeout_sec
    startup_commands, heartbeat_commands, cleanup_commands = heartbeat_commands_from_script(script)
    output_parts: list[str] = []
    heartbeat_index = 0
    last_progress_total = -1
    last_progress_at = time.monotonic()
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdin is not None

    def joined_output() -> str:
        return "".join(output_parts)

    def send_command(command_text: str) -> None:
        assert process.stdin is not None
        process.stdin.write(command_text + "\n")
        process.stdin.flush()
        output_parts.append(f"$ {command_text}\n")
        command_deadline = bounded_console_deadline(deadline, max(5, heartbeat_sec))
        output_parts.append(read_until_console_prompt(process, command_deadline, expected_command_output_marker(command_text)))

    try:
        output_parts.append(read_until_console_prompt(process, deadline))
        for command_text in startup_commands:
            if process.poll() is not None:
                break
            send_command(command_text)
            output_parts.append(wait_for_bot_status_ready(process, deadline))

        while time.monotonic() < deadline:
            if process.poll() is not None:
                heartbeat_index += 1
                rolling_heartbeat_report(
                    output_dir,
                    heartbeat_index,
                    joined_output(),
                    process.returncode if process.returncode is not None else 0,
                    False,
                    command,
                    scenario_reports,
                    validation_context,
                    duration_policy,
                    heartbeat_sec,
                    no_progress_window_sec,
                    max_repeated_decisions,
                    max_death_loops,
                    validation_route_manifest,
                    completion_reason_override="worldserver_process_exit",
                )
                return joined_output(), process.returncode if process.returncode is not None else 0, False, command

            sleep_until = min(deadline, time.monotonic() + max(1, heartbeat_sec))
            while process.poll() is None and time.monotonic() < sleep_until:
                time.sleep(min(1.0, sleep_until - time.monotonic()))

            heartbeat_index += 1
            if process.poll() is None:
                for command_text in heartbeat_commands:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        break
                    send_command(command_text)
            report = rolling_heartbeat_report(
                output_dir,
                heartbeat_index,
                joined_output(),
                process.returncode if process.returncode is not None else 0,
                time.monotonic() >= deadline,
                command,
                scenario_reports,
                validation_context,
                duration_policy,
                heartbeat_sec,
                no_progress_window_sec,
                max_repeated_decisions,
                max_death_loops,
                validation_route_manifest,
            )
            progress_total = int(report.get("watchdog_state", {}).get("progress_total") or 0)
            if progress_total > last_progress_total:
                last_progress_total = progress_total
                last_progress_at = time.monotonic()
            no_progress_expired = time.monotonic() - last_progress_at >= no_progress_window_sec
            moved_diagnoses = int(report.get("watchdog_state", {}).get("progress_counters", {}).get("moved_diagnoses") or 0)
            semantic_progress_plateau = (
                last_progress_total >= 0
                and progress_total <= last_progress_total
                and no_progress_expired
                and moved_diagnoses <= 0
            )
            if not validation_route_manifest and route_segment_complete(report, validation_route):
                report["completion_reason"] = "route_segment_complete"
                report["route_segment_complete"] = True
                report["acceptable_final_evidence"] = False
                rejections = list(report.get("final_evidence_rejections") or [])
                if "segment_or_route_context_is_debug_only" not in rejections:
                    rejections.append("segment_or_route_context_is_debug_only")
                report["final_evidence_rejections"] = rejections
                write_json(output_dir / "report.json", report)
                break
            if report["acceptable_final_evidence"]:
                break
            if report["completion_reason"] in {"repeated_decision_watchdog", "death_loop_watchdog", "machine_failure_predicate"}:
                break
            if validation_route_manifest and semantic_progress_plateau:
                report["completion_reason"] = "semantic_progress_plateau_watchdog"
                report["watchdog_state"]["semantic_progress_plateau"] = True
                if "semantic_progress_plateau" not in report["failure_labels"]:
                    report["failure_labels"].append("semantic_progress_plateau")
                report["failure_reason"] = report["failure_labels"][0]
                report["failed"] = max(int(report.get("failed") or 0), 1)
                report["all_passed"] = False
                report["acceptable_final_evidence"] = False
                if "failure_labels_present" not in report["final_evidence_rejections"]:
                    report["final_evidence_rejections"].append("failure_labels_present")
                write_json(output_dir / "report.json", report)
                break
            if report["watchdog_state"].get("no_progress") and no_progress_expired:
                report["completion_reason"] = "no_progress_watchdog"
                write_json(output_dir / "report.json", report)
                break
        timed_out = time.monotonic() >= deadline
        if process.poll() is None:
            for command_text in cleanup_commands:
                send_command(command_text)
        if process.poll() is None and process.stdin and not process.stdin.closed:
            try:
                send_command("server shutdown force 0")
            except BrokenPipeError:
                pass
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
            process.stdin = None
        shutdown_deadline = min(time.monotonic() + 10, deadline + 10)
        while process.poll() is None and time.monotonic() < shutdown_deadline:
            time.sleep(0.25)
        if process.poll() is None:
            process.kill()
            timed_out = True
        if process.stdout:
            output_parts.append(process.stdout.read())
        returncode = process.returncode if process.returncode is not None else (124 if timed_out else 0)
        return joined_output(), returncode, timed_out, command
    except (BrokenPipeError, subprocess.TimeoutExpired) as exc:
        process.kill()
        output = (exc.stdout or "") if isinstance(exc, subprocess.TimeoutExpired) else ""
        if not output and process.stdout:
            output = process.stdout.read()
        output_parts.append(output)
        return joined_output(), 124, True, command


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


def execute_soap_command(soap_url: str, username: str, password: str, command_text: str, timeout_sec: int) -> tuple[str, int, bool]:
    """Execute one SOAP console command without imposing process lifecycle policy."""
    auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
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
        with urllib.request.urlopen(request, timeout=max(1, timeout_sec)) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return parse_soap_result(payload), 0, False
    except urllib.error.HTTPError as exc:
        return exc.read().decode("utf-8", errors="replace"), exc.code, False
    except TimeoutError:
        return "", 124, True
    except OSError as exc:
        return str(exc), 1, False


def run_soap_commands(soap_url: str, username: str, password: str, script: str, timeout_sec: int, observe_sec: int = 0) -> tuple[str, int, bool, list[str]]:
    output_parts: list[str] = []
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
        payload, returncode, timed_out = execute_soap_command(soap_url, username, password, command_text, max(1, int(remaining_float)))
        output_parts.append(f"$ {command_text}")
        output_parts.append(payload)
        if returncode != 0 or timed_out:
            return "\n".join(output_parts), returncode, timed_out, command
        if observe_sec > 0 and command_text == ".botauto start":
            output_parts.append(f"$ sleep {observe_sec}")
            time.sleep(observe_sec)
    return "\n".join(output_parts), 0, False, command


def route_sequence_child_command(args: argparse.Namespace, route: dict[str, Any], output_dir: Path, *, first_route: bool) -> list[str]:
    scenario_id = str(args.validation_scenario_id or "")
    context = route_validation_context(scenario_id, route, include_segment=True)
    command = [
        sys.executable,
        "-m",
        "tools.bot_ml.run_live_bot_validation",
        "--worldserver",
        str(args.worldserver),
        "--config",
        str(args.config),
        "--output-dir",
        str(output_dir),
        "--duration-policy",
        args.duration_policy,
        "--timeout-sec",
        str(args.timeout_sec),
        "--heartbeat-sec",
        str(args.heartbeat_sec),
        "--no-progress-window-sec",
        str(args.no_progress_window_sec),
        "--max-repeated-decision-count",
        str(args.max_repeated_decision_count),
        "--max-death-loop-count",
        str(args.max_death_loop_count),
        "--selector",
        args.selector,
        "--trace-limit",
        str(args.trace_limit),
        "--transport",
        args.transport,
        "--observe-sec",
        str(args.observe_sec),
        "--validation-scenario-dir",
        str(args.validation_scenario_dir),
        "--validation-scenario-id",
        scenario_id,
        "--validation-segment-id",
        str(context.get("segment_id") or ""),
        "--validation-route-node-id",
        str(context.get("route_node_id") or ""),
        "--validation-route-label",
        str(context.get("route_label") or ""),
        "--validation-route-kind",
        str(context.get("route_kind") or ""),
        "--validation-route-step",
        str(context.get("route_step") or 0),
        "--validation-mechanic-profile",
        str(context.get("mechanic_profile") or ""),
    ]
    if args.no_start:
        command.append("--no-start")
    if args.force_start_command:
        command.append("--force-start-command")
    if args.stop:
        command.append("--stop")
    if args.soap_user:
        command.extend(["--soap-user", args.soap_user])
    if args.soap_password:
        command.extend(["--soap-password", args.soap_password])
    if args.soap_url:
        command.extend(["--soap-url", args.soap_url])
    if args.scenario_report_dir:
        command.extend(["--scenario-report-dir", str(args.scenario_report_dir)])
    if first_route and args.apply_validation_provisioning:
        command.extend(
            [
                "--apply-validation-provisioning",
                "--validation-provisioning-config",
                str(args.validation_provisioning_config),
                "--gear-profiles",
                str(args.gear_profiles),
            ]
        )
    if first_route and args.reset_bot_pool:
        command.append("--reset-bot-pool")
    for tag in args.bot_pool_tag:
        command.extend(["--bot-pool-tag", tag])
    if args.keep_bot_pool_position:
        command.append("--keep-bot-pool-position")
    if args.keep_bot_pool_quests:
        command.append("--keep-bot-pool-quests")
    if args.keep_bot_pool_memory:
        command.append("--keep-bot-pool-memory")
    return command


def route_sequence_report(
    args: argparse.Namespace,
    routes: list[dict[str, Any]],
    commands: list[list[str]],
    segment_reports: list[dict[str, Any]],
    failed_command: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failure_labels: list[str] = []
    if not routes:
        failure_labels.append("no_executable_validation_routes")
    for report in segment_reports:
        for label in report.get("failure_labels") or []:
            if label not in failure_labels:
                failure_labels.append(str(label))
    if failed_command and "route_sequence_child_failed" not in failure_labels:
        failure_labels.append("route_sequence_child_failed")
    complete_segments = []
    for report in segment_reports:
        validation_context = report.get("validation_context") if isinstance(report.get("validation_context"), dict) else {}
        if route_segment_complete(report, report.get("validation_route") if isinstance(report.get("validation_route"), dict) else None):
            complete_segments.append(str(validation_context.get("segment_id") or ""))
    expected_segments = [route_segment_output_name(route) for route in routes]
    missing_segments = [segment for segment in expected_segments if segment not in complete_segments]
    return {
        "schema": "bot_live_validation_report_v1",
        "generated_at_unix": int(time.time()),
        "duration_policy": args.duration_policy,
        "validation_context": {"scenario_id": args.validation_scenario_id},
        "route_sequence": {
            "schema": "bot_live_validation_route_sequence_v1",
            "scenario_id": args.validation_scenario_id,
            "route_count": len(routes),
            "expected_segments": expected_segments,
            "complete_segments": complete_segments,
            "missing_segments": missing_segments,
            "commands": commands,
            "segment_reports": [str(args.output_dir / route_segment_output_name(route) / "report.json") for route in routes],
            "failed_command": failed_command or {},
        },
        "command": commands,
        "returncode": int(failed_command.get("returncode", 0)) if failed_command else 0,
        "timed_out": False,
        "json_payloads": 0,
        "active_bots": 0,
        "target_bots": 0,
        "diagnosis_count": 0,
        "trace_entries": sum(int(report.get("trace_entries") or 0) for report in segment_reports),
        "scenario_reports": {},
        "command_errors": [],
        "evidence": {
            "validation_route_actions": sum(int(report.get("evidence", {}).get("validation_route_actions") or 0) for report in segment_reports),
            "validation_evidence_counts": {},
        },
        "progress_counters": {
            "validation_route_actions": sum(int(report.get("progress_counters", {}).get("validation_route_actions") or 0) for report in segment_reports),
            "kills": sum(int(report.get("progress_counters", {}).get("kills") or 0) for report in segment_reports),
            "boss_kill_evidence": sum(int(report.get("progress_counters", {}).get("boss_kill_evidence") or 0) for report in segment_reports),
            "trash_pulls": sum(int(report.get("progress_counters", {}).get("trash_pulls") or 0) for report in segment_reports),
        },
        "watchdog_state": {"policy": "route-sequence", "progress_total": len(complete_segments)},
        "completion_reason": "route_sequence_complete" if not failure_labels and not missing_segments else "route_sequence_incomplete",
        "acceptable_final_evidence": False,
        "final_evidence_rejections": ["route_sequence_context_is_not_uninterrupted_full_clear"],
        "failure_labels": failure_labels,
        "failure_reason": failure_labels[0] if failure_labels else None,
        "stages": [],
        "passed": len(complete_segments),
        "failed": len(missing_segments),
        "all_passed": not failure_labels and not missing_segments,
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
    }


def run_route_sequence(args: argparse.Namespace, routes: list[dict[str, Any]]) -> int:
    commands: list[list[str]] = []
    segment_reports: list[dict[str, Any]] = []
    failed_command: dict[str, Any] | None = None
    for index, route in enumerate(routes):
        segment_dir = args.output_dir / route_segment_output_name(route)
        command = route_sequence_child_command(args, route, segment_dir, first_route=index == 0)
        commands.append(command)
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        (segment_dir / "sequence_child_stdout.log").write_text(completed.stdout, encoding="utf-8")
        (segment_dir / "sequence_child_stderr.log").write_text(completed.stderr, encoding="utf-8")
        report_path = segment_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        if report:
            segment_reports.append(report)
        append_jsonl(
            args.output_dir / "route_sequence_events.jsonl",
            {
                "segment_id": route_segment_output_name(route),
                "route_node_id": route.get("route_node_id") or "",
                "returncode": completed.returncode,
                "report": str(report_path),
                "completion_reason": report.get("completion_reason") if report else "",
                "failure_labels": report.get("failure_labels") if report else ["missing_segment_report"],
            },
        )
        if completed.returncode != 0 or not report or not route_segment_complete(report, route):
            failed_command = {
                "segment_id": route_segment_output_name(route),
                "route_node_id": route.get("route_node_id") or "",
                "returncode": completed.returncode,
                "report": str(report_path),
            }
            break
    report = route_sequence_report(args, routes, commands, segment_reports, failed_command)
    write_json(args.output_dir / "report.json", report)
    (args.output_dir / "commands.txt").write_text("\n".join(render_command(command) for command in commands) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_passed"] else 1


def run_reusable_validation_session(
    args: argparse.Namespace,
    script: str,
    scenario_reports: dict[str, dict[str, Any]],
    validation_context: dict[str, Any],
    validation_route: dict[str, Any],
    validation_route_manifest: dict[str, Any],
    validation_route_manifest_path: Path | None,
    bot_pool_tags: list[str],
) -> tuple[str, int, bool, list[str], dict[str, Any]]:
    if not args.soap_user or not args.soap_password:
        raise SystemExit("--soap-user and --soap-password are required with --transport session")
    profile_manifest = Path(trinity_config_string(args.config, "BotWorld.ProfileManifest", "dataset/bot_runtime_profiles/profiles.json"))
    if not profile_manifest.is_absolute():
        profile_manifest = REPO_ROOT / profile_manifest
    fingerprint_paths = [
        path for path in (
            profile_manifest,
            args.validation_scenario_dir / "validation_routes.jsonl",
            args.validation_provisioning_config,
            args.gear_profiles,
        ) if path.is_file()
    ]
    profile = args.session_profile or str(validation_context.get("scenario_id") or "")
    if validation_route_manifest_path and profile_manifest.is_file():
        profiles = json.loads(profile_manifest.read_text(encoding="utf-8"))
        selected = next((row for row in profiles.get("profiles", []) if str(row.get("name") or "") == profile), None)
        configured_manifest = str(((selected or {}).get("validation_route") or {}).get("manifest_path") or "")
        expected_manifest = args.validation_scenario_dir / "validation_routes.jsonl"
        if not configured_manifest or Path(configured_manifest).resolve() != expected_manifest.resolve():
            raise SystemExit("session runtime profile route manifest does not match --validation-scenario-dir")

    session = build_session(
        REPO_ROOT, args.session_environment, args.worldserver, args.config,
        fingerprint_paths=fingerprint_paths,
    )
    command = ["SESSION", session.unit_name, args.soap_url]
    output_parts: list[str] = []
    lifecycle: dict[str, Any] = {**session.metadata(), "transport": "session"}

    def execute(command_text: str, remaining: int) -> tuple[str, int, bool]:
        return execute_soap_command(args.soap_url, args.soap_user, args.soap_password, command_text, remaining)

    with live_validation_lock(REPO_ROOT, args.session_environment):
        action = ensure_healthy_matching_session(session)
        lifecycle["server_action"] = action.action
        lifecycle["server_pid"] = int(action.status.properties.get("MainPID") or 0)
        deadline = time.monotonic() + args.session_transition_timeout_sec
        try:
            output_parts.append(wait_for_soap_command_available(execute, deadline))
            stop_output, returncode, timed_out = execute(".botauto stop", args.session_transition_timeout_sec)
            output_parts.extend(("$ .botauto stop\n", stop_output))
            if returncode != 0 or timed_out:
                raise RuntimeError("failed to stop BotWorld before reusable validation")
            inactive_output, _ = wait_for_bot_status_state(execute, False, deadline)
            output_parts.append(inactive_output)
            lifecycle["inactive_before_preparation"] = True

            preparation: dict[str, Any] = {}
            if args.reset_bot_pool:
                preparation["bot_pool_reset"] = prepare_bot_pool_reset(
                    args.output_dir, args.config, bot_pool_tags, apply=True,
                    reset_positions=not args.keep_bot_pool_position,
                    reset_quests=not args.keep_bot_pool_quests,
                    reset_memory=not args.keep_bot_pool_memory,
                )
            if args.apply_validation_provisioning:
                preparation["validation_provisioning"] = prepare_validation_provisioning(
                    args.output_dir, args.validation_provisioning_config, args.gear_profiles, args.config, apply=True,
                )
            if validation_route and int(validation_route.get("bot_start_map_id") or 0):
                preparation["route_bot_start"] = prepare_route_bot_start(
                    args.output_dir, validation_route, args.config, bot_pool_tags, apply=True,
                )
            lifecycle["preparation"] = preparation

            start_command = f".botauto start {profile}" if profile else ".botauto start"
            start_output, returncode, timed_out = execute(start_command, args.session_transition_timeout_sec)
            output_parts.extend((f"$ {start_command}\n", start_output))
            if returncode != 0 or timed_out:
                raise RuntimeError("failed to start BotWorld reusable validation")
            ready_output, _ = wait_for_bot_status_state(
                execute, True, time.monotonic() + args.session_transition_timeout_sec,
            )
            output_parts.append(ready_output)
            lifecycle["active_after_start"] = True

            watchdog_script = command_script(
                selector=args.selector, trace_limit=args.trace_limit, start=False, stop=False, exit_server=False,
            )
            output, returncode, timed_out, _ = run_transport_completion_watchdog(
                execute, command, args.timeout_sec, watchdog_script, args.output_dir,
                scenario_reports, validation_context,
                validation_route_manifest=validation_route_manifest,
                duration_policy=args.duration_policy,
                heartbeat_sec=args.heartbeat_sec,
                no_progress_window_sec=args.no_progress_window_sec,
                max_repeated_decisions=args.max_repeated_decision_count,
                max_death_loops=args.max_death_loop_count,
            )
            output_parts.append(output)
            lifecycle["watchdog_completed"] = True
            return "".join(output_parts), returncode, timed_out, command, lifecycle
        finally:
            try:
                output_parts.append(wait_for_soap_command_available(
                    execute, time.monotonic() + args.session_transition_timeout_sec,
                ))
                stop_output, returncode, timed_out = execute(".botauto stop", args.session_transition_timeout_sec)
                output_parts.extend(("$ .botauto stop\n", stop_output))
                if returncode != 0 or timed_out:
                    raise RuntimeError("failed to stop BotWorld after reusable validation")
                inactive_output, _ = wait_for_bot_status_state(
                    execute, False, time.monotonic() + args.session_transition_timeout_sec,
                )
                output_parts.append(inactive_output)
                lifecycle["inactive_after_attempt"] = True
            except Exception as exc:
                lifecycle["inactive_after_attempt"] = False
                lifecycle["cleanup_failure"] = str(exc)
                report_path = args.output_dir / "report.json"
                if report_path.is_file():
                    try:
                        failed_report = json.loads(report_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        failed_report = {}
                    failed_report["acceptable_final_evidence"] = False
                    failed_report["all_passed"] = False
                    failed_report["failure_reason"] = "session_cleanup_failed"
                    labels = list(failed_report.get("failure_labels") or [])
                    if "session_cleanup_failed" not in labels:
                        labels.append("session_cleanup_failed")
                    failed_report["failure_labels"] = labels
                    failed_report["session"] = lifecycle
                    write_json(report_path, failed_report)
                stop_session(session)
                raise
            finally:
                write_json(args.output_dir / "session.json", lifecycle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or prepare live BotWorld validation diagnostics.")
    parser.add_argument("--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver"))
    parser.add_argument("--config", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/live_validation"))
    parser.add_argument("--duration-policy", choices=["completion-watchdog", "fixed-window"], default="completion-watchdog")
    parser.add_argument("--timeout-sec", type=int, default=None, help="Emergency wall-clock cap. Defaults to 90 seconds for fixed smoke checks and 900 seconds for boss-route or watchdog validations.")
    parser.add_argument("--heartbeat-sec", type=int, default=DEFAULT_COMPLETION_HEARTBEAT_SEC)
    parser.add_argument("--no-progress-window-sec", type=int, default=DEFAULT_NO_PROGRESS_WINDOW_SEC)
    parser.add_argument("--max-repeated-decision-count", type=int, default=DEFAULT_MAX_REPEATED_DECISIONS)
    parser.add_argument("--max-death-loop-count", type=int, default=DEFAULT_MAX_DEATH_LOOPS)
    parser.add_argument("--selector", default="all")
    parser.add_argument("--trace-limit", type=int, default=128)
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--force-start-command", action="store_true", help="Send .botauto start even when BotWorld.AutoStart is enabled in the selected worldserver config.")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--transport", choices=["process", "soap", "session"], default="process")
    parser.add_argument("--soap-url", default="http://127.0.0.1:7878/")
    parser.add_argument("--soap-user", default=os.environ.get("TRINITY_SOAP_USER"))
    parser.add_argument("--soap-password", default=os.environ.get("TRINITY_SOAP_PASSWORD"))
    parser.add_argument("--session-environment", default="default", help="Stable identity for the shared validation server and live-attempt lock.")
    parser.add_argument("--session-profile", default="", help="Runtime profile selected by .botauto start in reusable session mode; defaults to the scenario ID.")
    parser.add_argument("--session-transition-timeout-sec", type=int, default=180, help="Bound for reusable-session stop/start state transitions.")
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
    parser.add_argument("--validation-route-manifest", action="store_true", help="For a scenario-level uninterrupted run, write the ordered route manifest and configure the first route without segment context.")
    parser.add_argument("--validation-route-sequence", action="store_true", help="For a scenario-level run, execute executable route nodes in manifest order and write an aggregate sequence report.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input-log", type=Path)
    args = parser.parse_args()

    if args.duration_policy == "completion-watchdog":
        args.timeout_sec = args.timeout_sec if args.timeout_sec is not None else DEFAULT_BOSS_ROUTE_TIMEOUT_SEC
        args.observe_sec = args.observe_sec if args.observe_sec is not None else args.heartbeat_sec
    elif str(args.validation_route_kind or "").lower() == "boss":
        args.timeout_sec = args.timeout_sec if args.timeout_sec is not None else DEFAULT_BOSS_ROUTE_TIMEOUT_SEC
        args.observe_sec = args.observe_sec if args.observe_sec is not None else DEFAULT_BOSS_ROUTE_OBSERVE_SEC
    else:
        args.timeout_sec = args.timeout_sec if args.timeout_sec is not None else DEFAULT_LIVE_VALIDATION_TIMEOUT_SEC
        args.observe_sec = args.observe_sec if args.observe_sec is not None else 0

    output_dir_was_nonempty = args.output_dir.exists() and any(args.output_dir.iterdir())
    if args.transport == "session" and output_dir_was_nonempty and not args.dry_run and not args.input_log:
        raise SystemExit("--transport session requires a new or empty --output-dir")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    bot_pool_tags = args.bot_pool_tag or ["test_account"]

    if args.validation_route_sequence:
        if not args.validation_scenario_id:
            raise SystemExit("--validation-route-sequence requires --validation-scenario-id")
        if args.input_log:
            raise SystemExit("--validation-route-sequence cannot be combined with --input-log")
        sequence_routes = load_validation_routes_for_scenario(args.validation_scenario_dir, args.validation_scenario_id)
        commands = [
            route_sequence_child_command(args, route, args.output_dir / route_segment_output_name(route), first_route=index == 0)
            for index, route in enumerate(sequence_routes)
        ]
        if args.dry_run:
            report = {
                "schema": "bot_live_validation_report_v1",
                "dry_run": True,
                "validation_context": {"scenario_id": args.validation_scenario_id},
                "route_sequence": {
                    "schema": "bot_live_validation_route_sequence_v1",
                    "scenario_id": args.validation_scenario_id,
                    "route_count": len(sequence_routes),
                    "expected_segments": [route_segment_output_name(route) for route in sequence_routes],
                    "commands": commands,
                },
                "runtime_ml_control": "offline_shadow_only",
                "control_eligible": False,
            }
            write_json(args.output_dir / "report.json", report)
            (args.output_dir / "commands.txt").write_text("\n".join(render_command(command) for command in commands) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        return run_route_sequence(args, sequence_routes)

    validation_context = validation_context_from_args(args)
    validation_route = load_validation_route(args.validation_scenario_dir, validation_context)
    if validation_route:
        validation_context = route_validation_context(args.validation_scenario_id, validation_route, include_segment=bool(args.validation_segment_id))
    validation_route_manifest: dict[str, Any] = {}
    validation_route_manifest_path: Path | None = None
    if args.validation_route_manifest:
        if not args.validation_scenario_id:
            raise SystemExit("--validation-route-manifest requires --validation-scenario-id")
        manifest_routes = load_validation_routes_for_scenario(args.validation_scenario_dir, args.validation_scenario_id)
        validation_route_manifest_path, validation_route_manifest = write_validation_route_manifest(args.output_dir, args.validation_scenario_id, manifest_routes)
        if not validation_route and manifest_routes:
            validation_route = manifest_routes[0]
    pool_tag_filter = str(validation_context.get("scenario_id") or (bot_pool_tags[0] if bot_pool_tags else ""))
    effective_config = args.config
    if args.transport == "process" and not args.input_log:
        effective_config = write_validation_config(args.config, args.output_dir, pool_tag_filter, validation_route, validation_route_manifest_path)
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
            apply=not args.dry_run and args.transport != "session",
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
            apply=not args.dry_run and args.transport != "session",
        )
    if validation_route and int(validation_route.get("bot_start_map_id") or 0):
        preparation["route_bot_start"] = prepare_route_bot_start(
            args.output_dir,
            validation_route,
            args.config,
            bot_pool_tags,
            apply=not args.dry_run and args.transport != "session",
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
            "validation_route_manifest": validation_route_manifest,
            "validation_route_manifest_path": str(validation_route_manifest_path or ""),
            "transport": args.transport,
            "soap_url": args.soap_url if args.transport == "soap" else "",
            "duration_policy": args.duration_policy,
            "timeout_sec": args.timeout_sec,
            "observe_sec": args.observe_sec,
            "heartbeat_sec": args.heartbeat_sec,
            "no_progress_window_sec": args.no_progress_window_sec,
            "max_repeated_decision_count": args.max_repeated_decision_count,
            "max_death_loop_count": args.max_death_loop_count,
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

    watchdog_report: dict[str, Any] | None = None
    session_lifecycle: dict[str, Any] = {}
    if args.input_log:
        output = args.input_log.read_text(encoding="utf-8")
        returncode = 0
        timed_out = False
        command: list[str] = []
    else:
        if args.transport == "soap":
            if not args.soap_user or not args.soap_password:
                raise SystemExit("--soap-user and --soap-password are required with --transport soap")
            if args.duration_policy == "completion-watchdog":
                def execute_soap(command_text: str, remaining: int) -> tuple[str, int, bool]:
                    return execute_soap_command(args.soap_url, args.soap_user, args.soap_password, command_text, remaining)

                output, returncode, timed_out, command = run_transport_completion_watchdog(
                    execute_soap,
                    ["SOAP", args.soap_url],
                    args.timeout_sec,
                    script,
                    args.output_dir,
                    scenario_reports,
                    validation_context,
                    duration_policy=args.duration_policy,
                    heartbeat_sec=args.heartbeat_sec,
                    no_progress_window_sec=args.no_progress_window_sec,
                    max_repeated_decisions=args.max_repeated_decision_count,
                    max_death_loops=args.max_death_loop_count,
                )
                existing_report = args.output_dir / "report.json"
                if existing_report.exists():
                    try:
                        watchdog_report = json.loads(existing_report.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        watchdog_report = None
            else:
                output, returncode, timed_out, command = run_soap_commands(args.soap_url, args.soap_user, args.soap_password, script, args.timeout_sec, args.observe_sec)
        elif args.transport == "session":
            output, returncode, timed_out, command, session_lifecycle = run_reusable_validation_session(
                args,
                script,
                scenario_reports,
                validation_context,
                validation_route,
                validation_route_manifest,
                validation_route_manifest_path,
                bot_pool_tags,
            )
            preparation = session_lifecycle.get("preparation") or preparation
            existing_report = args.output_dir / "report.json"
            if existing_report.exists():
                try:
                    watchdog_report = json.loads(existing_report.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    watchdog_report = None
        elif args.duration_policy == "completion-watchdog":
            output, returncode, timed_out, command = run_worldserver_completion_watchdog(
                args.worldserver,
                effective_config,
                args.timeout_sec,
                script,
                args.output_dir,
                scenario_reports,
                validation_context,
                duration_policy=args.duration_policy,
                heartbeat_sec=args.heartbeat_sec,
                no_progress_window_sec=args.no_progress_window_sec,
                max_repeated_decisions=args.max_repeated_decision_count,
                max_death_loops=args.max_death_loop_count,
                validation_route=validation_route,
                validation_route_manifest=validation_route_manifest,
            )
            existing_report = args.output_dir / "report.json"
            if existing_report.exists():
                try:
                    watchdog_report = json.loads(existing_report.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    watchdog_report = None
        else:
            output, returncode, timed_out, command = run_worldserver(args.worldserver, effective_config, args.timeout_sec, script, args.observe_sec)

    (args.output_dir / "worldserver_output.log").write_text(output, encoding="utf-8")
    if watchdog_report:
        report = watchdog_report
        report["returncode"] = returncode
        report["timed_out"] = timed_out
        report["command"] = command
    else:
        report = live_validation_report(
            output,
            returncode=returncode,
            timed_out=timed_out,
            command=command,
            scenario_reports=scenario_reports,
            validation_context=validation_context,
            validation_route_manifest=validation_route_manifest,
            duration_policy=args.duration_policy,
            heartbeat_sec=args.heartbeat_sec,
            no_progress_window_sec=args.no_progress_window_sec,
            max_repeated_decisions=args.max_repeated_decision_count,
            max_death_loops=args.max_death_loop_count,
        )
    report["generated_at_unix"] = int(time.time())
    report["config_autostart"] = config_autostart
    report["config"] = str(effective_config)
    report["base_config"] = str(args.config)
    report["pool_tag_filter"] = pool_tag_filter
    report["validation_route"] = validation_route
    report["validation_route_manifest"] = validation_route_manifest
    report["validation_route_manifest_path"] = str(validation_route_manifest_path or "")
    report["start_command"] = send_start_command
    report["preparation"] = preparation
    if args.transport == "session":
        report["session"] = session_lifecycle
        if not session_lifecycle.get("inactive_after_attempt"):
            report["acceptable_final_evidence"] = False
            report["all_passed"] = False
    report["validation_context"] = validation_context
    attach_stonecore_role_quality_audit(report, validation_context, validation_route_manifest)
    write_json(args.output_dir / "report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    segment_success = route_segment_complete(report, validation_route)
    full_success = bool(report.get("acceptable_final_evidence")) and bool(report.get("all_passed"))
    return 0 if returncode == 0 and not timed_out and (segment_success or full_success) else 1


if __name__ == "__main__":
    raise SystemExit(main())
