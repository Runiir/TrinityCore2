"""Resolve a frozen pair without inventing native instance identities."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.raid_program.shared_instance_observation import InstanceExpectation

SHARDS = "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
PROFILES = "dataset/bot_runtime_profiles/profiles.json"
ROUTES = "dataset/validation_scenarios/validation_routes.jsonl"
BASE_CONFIG = "experiments/configs/cata_raid_tracked_base_runtime_config_contract_v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _one(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    selected = [row for row in rows if row.get(key) == value]
    if len(selected) != 1:
        raise ValueError(f"ambiguous or missing {key}: {value}")
    return selected[0]


def load_fixture(source: Path, fixture_path: Path) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text())
    if (fixture.get("schema") != "cata_shared_instance_fixture_v1"
            or fixture.get("boss_completion_eligible") is not False
            or fixture.get("training_eligible") is not False
            or type(fixture.get("map_update_threads")) is not int
            or fixture["map_update_threads"] != 1
            or type(fixture.get("maximum_active_cohorts")) is not int
            or fixture["maximum_active_cohorts"] != 2
            or fixture.get("start_order") != ["witness", "subject"]
            or fixture.get("stop_order") != ["subject", "witness"]):
        raise ValueError("unsupported isolation fixture contract")
    inputs = fixture.get("inputs", {})
    if not all(path in inputs for path in (SHARDS, PROFILES, ROUTES, BASE_CONFIG)):
        raise ValueError("fixture inputs incomplete")
    for relative, expected in inputs.items():
        path = source / relative
        if (Path(relative).is_absolute() or ".." in Path(relative).parts
                or not path.resolve().is_relative_to(source.resolve())
                or path.is_symlink() or sha256(path) != expected):
            raise ValueError(f"fixture input mismatch: {relative}")
    shards = json.loads((source / SHARDS).read_text())["shards"]
    profiles = json.loads((source / PROFILES).read_text())["profiles"]
    routes = [json.loads(line) for line in (source / ROUTES).read_text().splitlines() if line]
    pair = {}
    for role in ("subject", "witness"):
        shard = _one(shards, "shard_id", fixture[f"{role}_shard_id"])
        profile = _one(profiles, "name", shard["runtime_profile_id"])
        route_config = profile["validation_route"]
        roster = shard["bots"]
        guids = frozenset(row["expected_character_guid"] for row in roster)
        if (len(guids) != len(roster) or len(roster) != profile["target_population"]
                or profile["pool_tag_filter"] != shard["pool_tag"]
                or route_config["manifest_path"] != ROUTES
                or route_config["scenario_id"] != shard["scenario_id"]
                or not any(row.get("scenario_id") == shard["scenario_id"] for row in routes)):
            raise ValueError(f"{role}: profile, route or frozen roster mismatch")
        expected = InstanceExpectation(shard["shard_id"], shard["start_position"]["map_id"],
                                       profile["raid_difficulty"], guids)
        pair[role] = {"expected": expected, "profile": profile["name"], "shard": shard}
    left, right = pair["subject"]["expected"], pair["witness"]["expected"]
    if left.cohort_id == right.cohort_id or left.roster_guids & right.roster_guids:
        raise ValueError("pair shares cohort or roster")
    return {"fixture": fixture, "fixture_sha256": sha256(fixture_path), **pair}


def validate_shared_config(path: Path) -> None:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            raise ValueError(f"duplicate runtime config key: {key}")
        values[key] = value.strip()
    required = {"MapUpdate.Threads": "1", "BotWorld.AutoStart": "0",
                "BotWorld.RuntimeProfile": '""', "BotPolicyModel.Enable": "0"}
    if any(values.get(key) != value for key, value in required.items()):
        raise ValueError("shared runtime config must keep one map worker and addressed admission")
