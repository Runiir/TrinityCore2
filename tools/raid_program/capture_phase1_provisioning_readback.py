from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.bot_ml.build_validation_provisioning import VALIDATION_FULL_STAT_SEED, load_config
from tools.bot_ml.common import write_json
from tools.bot_ml.extract_world_knowledge import (
    connect_mysql,
    database_url_from_worldserver_conf,
    sanitize_database_url,
)


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
        if int(row.get("enabled") or 0) != 1 or int(row.get("in_use") or 0) != 0:
            reasons.append(f"{name}:pool_state")
        if str(row.get("experiment_tags")) != "blackwing_descent_10n":
            reasons.append(f"{name}:tag")
    if character_instance_rows != 0:
        reasons.append("character_instance_rows")
    if group_member_rows != 0:
        reasons.append("group_member_rows")
    return sorted(set(reasons))


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture an exact DB-backed BWD Phase 1 roster readback")
    parser.add_argument("--provisioning-config", type=Path, default=ROOT / "experiments/configs/validation_provisioning_cata_001.json")
    parser.add_argument("--scenario-config", type=Path, default=ROOT / "experiments/configs/validation_scenarios_cata_001.json")
    parser.add_argument("--worldserver-conf", type=Path, default=ROOT / "trinity-worldserver-test.conf")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    provisioning = load_config(args.provisioning_config)
    provisioned = next(row for row in provisioning["scenarios"] if row.get("id") == "blackwing_descent_10n")
    scenario_document = json.loads(args.scenario_config.read_text(encoding="utf-8"))
    scenario = next(row for row in scenario_document["scenarios"] if row.get("id") == "blackwing_descent_10n")
    frozen = scenario.get("roster_identity") or []
    provisioned_by_name = {str(row["name"]): row for row in provisioned["bots"]}
    expected = [
        {
            **row,
            "class": int(provisioned_by_name[str(row["name"])]["class"]),
        }
        for row in frozen
    ]
    names = [str(row["name"]) for row in expected]
    character_url = database_url_from_worldserver_conf(args.worldserver_conf, "CharacterDatabaseInfo")
    connection = connect_mysql(character_url)
    try:
        placeholders = ", ".join(["%s"] * len(names))
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.guid, c.name, c.class AS class_id, c.map AS map_id, c.health, c.power1, "
                "c.position_x AS x, c.position_y AS y, c.position_z AS z, c.orientation AS o, c.online, "
                "p.role, p.class_spec, p.enabled, p.in_use, p.experiment_tags "
                "FROM characters c JOIN character_bot_pool p ON p.guid = c.guid "
                f"WHERE c.name IN ({placeholders}) ORDER BY c.name",
                tuple(names),
            )
            observed = [dict(row) for row in cursor.fetchall()]
            guids = [int(row["guid"]) for row in observed]
            guid_placeholders = ", ".join(["%s"] * len(guids))
            cursor.execute(f"SELECT COUNT(*) AS count FROM character_instance WHERE guid IN ({guid_placeholders})", tuple(guids))
            character_instance_rows = int(cursor.fetchone()["count"])
            cursor.execute(f"SELECT COUNT(*) AS count FROM group_member WHERE memberGuid IN ({guid_placeholders})", tuple(guids))
            group_member_rows = int(cursor.fetchone()["count"])
    finally:
        connection.close()

    reasons = validate_readback(
        expected,
        observed,
        start=scenario["start_position"],
        character_instance_rows=character_instance_rows,
        group_member_rows=group_member_rows,
    )
    payload = {
        "schema": "cata_raid_phase1_bwd_provisioning_readback_v2",
        "passed": not reasons,
        "reasons": reasons,
        "database": sanitize_database_url(character_url),
        "source_sha256": {
            "provisioning_config": sha256_file(args.provisioning_config),
            "scenario_config": sha256_file(args.scenario_config),
        },
        "expected_roster": expected,
        "observed_roster": observed,
        "character_instance_rows": character_instance_rows,
        "group_member_rows": group_member_rows,
        "query_contract": "exact frozen names joined to character_bot_pool; ordered; exact instance/group residue counts",
    }
    write_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if not reasons else 1


if __name__ == "__main__":
    raise SystemExit(main())
