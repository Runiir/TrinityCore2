from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.bot_ml.build_validation_provisioning import (
    VALIDATION_FULL_STAT_SEED,
    VALIDATION_GHOST_CHARACTER_FLAG,
    VALIDATION_RESURRECT_AT_LOGIN_FLAG,
    load_config_with_bwd_diagnostic_shards,
    load_config,
)
from tools.bot_ml.common import write_json
from tools.bot_ml.extract_world_knowledge import (
    connect_mysql,
    database_url_from_worldserver_conf,
    sanitize_database_url,
)
from tools.raid_program.bwd_shard_fixtures import CANONICAL_SCENARIO_ID, validate_shard_fixture


ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_readback(
    expected: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    *,
    start: dict[str, Any],
    character_instance_rows: int,
    group_member_rows: int,
    ghost_aura_rows: int,
    corpse_rows: int,
    corpse_phase_rows: int,
    group_instance_rows: int = 0,
    group_rows: int = 0,
) -> list[str]:
    reasons: list[str] = []
    expected_by_name = {str(row["name"]): row for row in expected}
    observed_by_name = {str(row["name"]): row for row in observed}
    if len(expected_by_name) != 10 or len(observed_by_name) != 10:
        reasons.append("exact_ten_names")
    if set(expected_by_name) != set(observed_by_name):
        reasons.append("exact_names")
    if len({int(row.get("guid") or 0) for row in observed}) != len(observed):
        reasons.append("unique_guids")
    role_counts = {role: sum(str(row.get("role")) == role for row in observed) for role in ("tank", "healer", "dps")}
    if role_counts != {"tank": 2, "healer": 3, "dps": 5}:
        reasons.append("exact_roles")
    for name, expected_row in expected_by_name.items():
        row = observed_by_name.get(name)
        if row is None:
            continue
        if int(row.get("guid") or 0) != int(expected_row.get("guid") or 0):
            reasons.append(f"{name}:guid")
        if str(row.get("role")) != str(expected_row.get("role")):
            reasons.append(f"{name}:role")
        if str(row.get("class_spec")) != str(expected_row.get("class_spec")):
            reasons.append(f"{name}:class_spec")
        if int(row.get("class_id") or 0) != int(expected_row.get("class") or 0):
            reasons.append(f"{name}:class_id")
        for observed_key, expected_key in (
            ("account_id", "expected_account_id"),
            ("account_registry_id", "expected_account_id"),
            ("account", "account"),
            ("canonical_roster_slot_id", "canonical_roster_slot_id"),
            ("roster_slot_id", "roster_slot_id"),
            ("runtime_profile_id", "runtime_profile_id"),
            ("pool_tag", "pool_tag"),
        ):
            if expected_key not in expected_row:
                continue
            expected_value = expected_row[expected_key]
            actual_value = row.get(observed_key)
            if observed_key == "account_id":
                try:
                    matches = int(actual_value or 0) == int(expected_value)
                except (TypeError, ValueError):
                    matches = False
            else:
                matches = str(actual_value) == str(expected_value)
            if not matches:
                reasons.append(f"{name}:{observed_key}")
        if int(row.get("map_id") or 0) != int(start["map_id"]):
            reasons.append(f"{name}:map")
        if any(abs(float(row[key]) - float(start[source])) > tolerance for key, source, tolerance in (
            ("x", "x", 0.001), ("y", "y", 0.001), ("z", "z", 0.001), ("o", "o", 0.001)
        )):
            reasons.append(f"{name}:position")
        if int(row.get("online") or 0) != 0:
            reasons.append(f"{name}:online")
        if int(row.get("health") or 0) != VALIDATION_FULL_STAT_SEED:
            reasons.append(f"{name}:health_seed")
        if int(row.get("power1") or 0) != VALIDATION_FULL_STAT_SEED:
            reasons.append(f"{name}:power1_seed")
        if int(row.get("character_flags") or 0) & VALIDATION_GHOST_CHARACTER_FLAG:
            reasons.append(f"{name}:ghost_character_flag")
        if int(row.get("at_login") or 0) & VALIDATION_RESURRECT_AT_LOGIN_FLAG:
            reasons.append(f"{name}:resurrect_at_login_flag")
        if int(row.get("enabled") or 0) != 1 or int(row.get("in_use") or 0) != 0:
            reasons.append(f"{name}:pool_state")
        expected_tag = str(expected_row.get("experiment_tags") or expected_row.get("pool_tag") or CANONICAL_SCENARIO_ID)
        if str(row.get("experiment_tags")) != expected_tag:
            reasons.append(f"{name}:tag")
    if character_instance_rows != 0:
        reasons.append("character_instance_rows")
    if group_member_rows != 0:
        reasons.append("group_member_rows")
    if ghost_aura_rows != 0:
        reasons.append("ghost_aura_rows")
    if corpse_rows != 0:
        reasons.append("corpse_rows")
    if corpse_phase_rows != 0:
        reasons.append("corpse_phase_rows")
    if group_instance_rows != 0:
        reasons.append("group_instance_rows")
    if group_rows != 0:
        reasons.append("group_rows")
    return sorted(set(reasons))


def _single(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    matches = [row for row in rows if str(row.get(key)) == value]
    if len(matches) != 1:
        raise ValueError(f"expected_one_{key}:{value}:got_{len(matches)}")
    return matches[0]


def load_materialized_readback_contract(
    provisioning_config: Path,
    scenario_config: Path,
    fixture_path: Path,
    scenario_id: str = CANONICAL_SCENARIO_ID,
) -> dict[str, Any]:
    """Load one canonical or diagnostic roster from the tracked BWD materialization."""
    base_config = load_config(provisioning_config)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    validate_shard_fixture(fixture, base_config)
    materialized = load_config_with_bwd_diagnostic_shards(provisioning_config, fixture_path)
    scenario = _single(materialized.get("scenarios", []), "id", scenario_id)
    scenario_document = json.loads(scenario_config.read_text(encoding="utf-8"))
    if scenario_id == CANONICAL_SCENARIO_ID:
        frozen = _single(scenario_document.get("scenarios", []), "id", scenario_id).get("roster_identity") or []
        if len(frozen) != 10:
            raise ValueError("canonical_bwd_roster_identity_must_have_exactly_10_rows")
        provisioned_by_name = {str(row["name"]): row for row in scenario["bots"]}
        expected = []
        for frozen_row in frozen:
            name = str(frozen_row["name"])
            source = provisioned_by_name.get(name)
            if source is None:
                raise ValueError(f"canonical_bwd_roster_name_missing:{name}")
            expected.append({
                **frozen_row,
                "class": int(source["class"]),
                "account": str(source["account"]),
                "canonical_roster_slot_id": str(frozen_row.get("roster_slot_id") or ""),
                "roster_slot_id": str(frozen_row.get("roster_slot_id") or ""),
                "runtime_profile_id": scenario_id,
                "pool_tag": scenario_id,
                "experiment_tags": scenario_id,
            })
        shard = None
        source_start = scenario["start_position"]
    else:
        shard = _single(fixture.get("shards", []), "scenario_id", scenario_id)
        if str(scenario.get("runtime_profile_id")) != scenario_id or str(scenario.get("pool_tag")) != scenario_id:
            raise ValueError(f"diagnostic_scenario_binding:{scenario_id}")
        expected = []
        for bot in shard.get("bots", []):
            expected.append({
                **bot,
                "guid": int(bot["expected_character_guid"]),
                "expected_account_id": int(bot["expected_account_id"]),
                "canonical_roster_slot_id": str(bot["canonical_roster_slot_id"]),
                "experiment_tags": scenario_id,
            })
        if len(expected) != 10:
            raise ValueError(f"diagnostic_bwd_roster_must_have_exactly_10_rows:{scenario_id}")
        source_start = shard["start_position"]
    return {
        "scenario_id": scenario_id,
        "fixture": fixture,
        "scenario": scenario,
        "shard": shard,
        "expected": expected,
        "start": source_start,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture an exact DB-backed BWD Phase 1 roster readback")
    parser.add_argument("--provisioning-config", type=Path, default=ROOT / "experiments/configs/validation_provisioning_cata_001.json")
    parser.add_argument("--scenario-config", type=Path, default=ROOT / "experiments/configs/validation_scenarios_cata_001.json")
    parser.add_argument("--bwd-shard-fixture", type=Path, default=ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json")
    parser.add_argument("--scenario-id", default=CANONICAL_SCENARIO_ID)
    parser.add_argument("--worldserver-conf", type=Path, default=ROOT / "trinity-worldserver-test.conf")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_materialized_readback_contract(
        args.provisioning_config,
        args.scenario_config,
        args.bwd_shard_fixture,
        args.scenario_id,
    )
    expected = contract["expected"]
    scenario = contract["scenario"]
    expected_by_name = {str(row["name"]): row for row in expected}
    names = [str(row["name"]) for row in expected]
    character_url = database_url_from_worldserver_conf(args.worldserver_conf, "CharacterDatabaseInfo")
    connection = connect_mysql(character_url)
    character_instance_rows = group_member_rows = ghost_aura_rows = corpse_rows = corpse_phase_rows = 0
    group_instance_rows = group_rows = 0
    try:
        placeholders = ", ".join(["%s"] * len(names))
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.guid, c.account AS account_id, c.name, c.class AS class_id, c.map AS map_id, c.health, c.power1, "
                "c.characterFlags AS character_flags, c.at_login, "
                "c.position_x AS x, c.position_y AS y, c.position_z AS z, c.orientation AS o, c.online, "
                "p.role, p.class_spec, p.enabled, p.in_use, p.experiment_tags "
                "FROM characters c JOIN character_bot_pool p ON p.guid = c.guid "
                f"WHERE c.name IN ({placeholders}) ORDER BY c.name",
                tuple(names),
            )
            observed = [dict(row) for row in cursor.fetchall()]
            guids = [int(row["guid"]) for row in observed]
            if guids:
                guid_placeholders = ", ".join(["%s"] * len(guids))
                cursor.execute(f"SELECT COUNT(*) AS count FROM character_instance WHERE guid IN ({guid_placeholders})", tuple(guids))
                character_instance_rows = int(cursor.fetchone()["count"])
                cursor.execute(f"SELECT COUNT(*) AS count FROM group_member WHERE memberGuid IN ({guid_placeholders})", tuple(guids))
                group_member_rows = int(cursor.fetchone()["count"])
                cursor.execute(f"SELECT COUNT(*) AS count FROM character_aura WHERE guid IN ({guid_placeholders})", tuple(guids))
                ghost_aura_rows = int(cursor.fetchone()["count"])
                cursor.execute(f"SELECT COUNT(*) AS count FROM corpse WHERE guid IN ({guid_placeholders})", tuple(guids))
                corpse_rows = int(cursor.fetchone()["count"])
                cursor.execute(f"SELECT COUNT(*) AS count FROM corpse_phases WHERE OwnerGuid IN ({guid_placeholders})", tuple(guids))
                corpse_phase_rows = int(cursor.fetchone()["count"])
                cursor.execute("SELECT COUNT(*) AS count FROM group_instance gi JOIN group_member gm ON gm.guid = gi.guid " + f"WHERE gm.memberGuid IN ({guid_placeholders})", tuple(guids))
                group_instance_rows = int(cursor.fetchone()["count"])
                cursor.execute("SELECT COUNT(*) AS count FROM groups g LEFT JOIN group_member gm ON gm.guid = g.guid " + f"WHERE g.leaderGuid IN ({guid_placeholders}) OR gm.memberGuid IN ({guid_placeholders})", tuple(guids) + tuple(guids))
                group_rows = int(cursor.fetchone()["count"])
    finally:
        connection.close()

    login_url = database_url_from_worldserver_conf(args.worldserver_conf, "LoginDatabaseInfo")
    expected_accounts = [str(row["account"]) for row in expected]
    account_placeholders = ", ".join(["%s"] * len(expected_accounts))
    account_connection = connect_mysql(login_url)
    try:
        with account_connection.cursor() as cursor:
            cursor.execute(f"SELECT id AS account_id, username AS account FROM account WHERE username IN ({account_placeholders})", tuple(expected_accounts))
            account_rows = [dict(row) for row in cursor.fetchall()]
    finally:
        account_connection.close()
    account_by_name = {str(row.get("account", "")).upper(): row for row in account_rows}
    for row in observed:
        expected_row = expected_by_name.get(str(row.get("name")))
        if expected_row is None:
            continue
        account_row = account_by_name.get(str(expected_row["account"]).upper(), {})
        row["account"] = account_row.get("account")
        row["account_registry_id"] = account_row.get("account_id")
        row["canonical_roster_slot_id"] = expected_row.get("canonical_roster_slot_id")
        row["roster_slot_id"] = expected_row.get("roster_slot_id")
        row["runtime_profile_id"] = expected_row.get("runtime_profile_id")
        row["pool_tag"] = row.get("experiment_tags")

    reasons = validate_readback(
        expected,
        observed,
        start=contract["start"],
        character_instance_rows=character_instance_rows,
        group_member_rows=group_member_rows,
        ghost_aura_rows=ghost_aura_rows,
        corpse_rows=corpse_rows,
        corpse_phase_rows=corpse_phase_rows,
        group_instance_rows=group_instance_rows,
        group_rows=group_rows,
    )
    payload = {
        "schema": "cata_raid_phase1_bwd_provisioning_readback_v5",
        "scenario_id": args.scenario_id,
        "passed": not reasons,
        "reasons": reasons,
        "database": sanitize_database_url(character_url),
        "login_database": sanitize_database_url(login_url),
        "source_sha256": {
            "provisioning_config": sha256_file(args.provisioning_config),
            "scenario_config": sha256_file(args.scenario_config),
            "bwd_shard_fixture": sha256_file(args.bwd_shard_fixture),
        },
        "expected_roster": expected,
        "observed_roster": observed,
        "character_instance_rows": character_instance_rows,
        "group_member_rows": group_member_rows,
        "ghost_aura_rows": ghost_aura_rows,
        "corpse_rows": corpse_rows,
        "corpse_phase_rows": corpse_phase_rows,
        "group_instance_rows": group_instance_rows,
        "group_rows": group_rows,
        "selected_name_count": len(names),
        "query_contract": "exact selected ten names joined to character_bot_pool plus exact selected ten auth usernames; ordered; exact character-instance/group/ghost-aura/corpse/corpse-phase residue counts",
    }
    write_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if not reasons else 1


if __name__ == "__main__":
    raise SystemExit(main())
