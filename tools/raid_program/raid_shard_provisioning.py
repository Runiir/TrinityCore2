"""Guarded provisioning of raid_shard_plan_v1 cohorts before a shard run launches.

The shard coordinator calls `provision_plan_cohorts` from `before_launch`: under
the shared owner lock, before its worldserver starts. It reuses the collision
proof of tools.raid_program.raid_shard_preflight unchanged:

1. the plan's materialization sources must be recorded and current (the
   coordinator first runs `verify_source_plan`: every recorded source file and
   the written outputs against manifest.json);
2. a read-only preflight over the plan's reservation. When the plan's anchor
   cohort (the highest ID of every table) is neither selected nor present, the
   core allocators could later enter an unwritten block, so the anchor cohort
   joins the apply set and is written first;
3. the apply refusals: no worldserver process, renamed copies included
   (raid_shard_preflight.worldserver_processes), and auth/characters on
   one database server. The attestation is the caller's: the coordinator has not
   launched its server yet and holds the owner lock;
4. one transaction per cohort, anchor first (execute_cohort_transactions);
5. a readback: the preflight again (every anchor present, no foreign row) and
   the exact two-spec loadout of every applied character.

Any refusal raises RaidShardProvisioningError before the worldserver starts.
The legacy 110-character validation provisioning is not touched here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Sequence

from tools.raid_program.raid_shard_preflight import (
    Query,
    apply_refusals,
    evaluate_preflight,
    execute_cohort_transactions,
    fetch_preflight_facts,
    order_cohorts,
    plan_reservation,
    server_identity,
    worldserver_processes,
)

SCHEMA = "raid_shard_run_provisioning_v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DBC_DIR = REPO_ROOT / "data/dbc/enUS"
DEFAULT_TRAINERS = REPO_ROOT / "dataset/world_knowledge/trainers.jsonl"
PLAN_SCHEMA = "raid_shard_plan_v1"


class RaidShardProvisioningError(RuntimeError):
    def __init__(self, reason: str, report: dict[str, Any]):
        super().__init__(reason)
        self.report = report


def load_source_plan(path: Path) -> dict[str, Any]:
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if plan.get("schema") != PLAN_SCHEMA:
        raise RaidShardProvisioningError(f"source_plan_schema:{plan.get('schema')}", {"plan": str(path)})
    return plan


def verify_source_plan(plan_path: Path, *, gear_profiles: Path, dbc_dir: Path = DEFAULT_DBC_DIR,
                       trainers: Path = DEFAULT_TRAINERS, root: Path = REPO_ROOT) -> dict[str, Any]:
    """Refuse a generated plan that is not the current, complete DVC output.

    Every recorded source (composition, prerequisites, scenario starts, spec
    catalog and the materialization inputs) must still hash as recorded, and the
    plan directory's written files must equal a regeneration from the plan and
    the output hashes of its manifest.json. A stale or hand-written plan.json
    without its manifest is refused before any preflight or apply.
    """
    from tools.raid_program.raid_loadout_sql import RaidShardSqlError, check_plan_sources, verify_plan_outputs

    plan_path = Path(plan_path)
    plan = load_source_plan(plan_path)
    evidence: dict[str, Any] = {"plan": str(plan_path)}
    try:
        evidence["materialization_inputs"] = check_plan_sources(plan, gear_profiles, trainers)
    except RaidShardSqlError as error:
        raise RaidShardProvisioningError(str(error), evidence) from error
    drift = []
    for name, row in sorted((plan.get("sources") or {}).items()):
        if name in evidence["materialization_inputs"] or not isinstance(row, dict) or "path" not in row:
            continue
        path = Path(row["path"]) if Path(row["path"]).is_absolute() else Path(root) / row["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if actual != row.get("sha256"):
            drift.append(name)
    if drift:
        raise RaidShardProvisioningError(f"plan_source_drift:{','.join(drift)}", evidence)
    failures, outputs = verify_plan_outputs(plan, plan_path.parent, gear_profiles, dbc_dir, trainers)
    evidence["outputs"] = outputs
    if failures:
        evidence["failures"] = failures
        checks = sorted({str(row["check"]) for row in failures})
        raise RaidShardProvisioningError(f"plan_outputs_unverified:{','.join(checks)}", evidence)
    evidence["verified"] = True
    return evidence


def plan_shards(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(shard["scenario_id"]): shard for shard in plan.get("shards") or []}


def run_shard_identity_failures(shard: dict[str, Any], *, cohort_id: str, profile: str, scenario_id: str,
                                pool_tag: str, boss_key: str, precompleted: Sequence[str] | None) -> list[str]:
    """Where a run-plan shard drifted from the generated plan shard it provisions."""
    problems = []
    for field, value in (("cohort_id", cohort_id), ("runtime_profile_id", profile), ("scenario_id", scenario_id),
                         ("pool_tag", pool_tag)):
        if str(shard.get(field)) != value:
            problems.append(field)
    if boss_key and str(shard.get("boss_key")) != boss_key:
        problems.append("boss_key")
    planned = list((shard.get("lockout") or {}).get("precompleted_boss_keys") or [])
    if precompleted is None:
        if planned:
            problems.append("lockout_fresh_but_plan_has_predecessors")
    elif sorted(precompleted) != sorted(planned):
        problems.append("lockout_precompleted_boss_keys")
    return problems


def _reader(url: str) -> Query:
    from tools.bot_ml.extract_world_knowledge import connect_mysql

    def query(sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
        connection = connect_mysql(url)
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()
    return query


def _database_name(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url).path or "/").lstrip("/")


def _loadout_readback(plan: dict[str, Any], scenario_ids: Sequence[str], character_url: str, gear_profiles: Path,
                      dbc_dir: Path, trainers: Path, fetch: Callable[..., dict[str, Any]] | None) -> dict[str, Any]:
    from tools.bot_ml.build_validation_provisioning import gem_item_enchant_map
    from tools.raid_program.raid_loadout_readback import fetch_runtime_loadouts, loadout_readback_failures
    from tools.raid_program.raid_loadout_sql import prepare_config

    config = prepare_config(plan, gear_profiles, dbc_dir, list(scenario_ids), trainers)
    bots = [bot for scenario in config["scenarios"] for bot in scenario["bots"]]
    observed = (fetch or fetch_runtime_loadouts)(character_url, [bot["name"] for bot in bots])
    gems = gem_item_enchant_map(dbc_dir)
    failures = [failure for bot in bots
                for failure in loadout_readback_failures(bot, observed.get(str(bot["name"])) or {},
                                                         config.get("default_consumables", []), gems, dbc_dir)]
    return {"characters": len(bots), "failures": failures, "passed": not failures}


def provision_plan_cohorts(plan_path: Path, scenario_ids: Sequence[str], *, character_url: str, auth_url: str,
                           gear_profiles: Path, dbc_dir: Path = DEFAULT_DBC_DIR, trainers: Path = DEFAULT_TRAINERS,
                           apply: bool = True, output: Path | None = None,
                           readers: tuple[Query, Query] | None = None,
                           connect: Callable[[str], Any] | None = None,
                           pgrep: Callable[[], dict[str, Any]] = worldserver_processes,
                           fetch_loadouts: Callable[..., dict[str, Any]] | None = None,
                           statements: Callable[..., list[tuple[str, list[str]]]] | None = None) -> dict[str, Any]:
    """Preflight, apply (anchor first, one transaction per cohort) and read back the selected cohorts."""
    from tools.raid_program.raid_loadout_sql import RaidShardSqlError, check_plan_sources, cohort_statements

    plan = load_source_plan(plan_path)
    selected = list(dict.fromkeys(scenario_ids))
    report: dict[str, Any] = {"schema": SCHEMA, "plan": str(plan_path), "composition_id": plan.get("composition_id"),
                              "selected_scenario_ids": selected, "applied": None, "passed": False,
                              "database_servers": {"characters": server_identity(character_url),
                                                   "auth": server_identity(auth_url)}}

    def write() -> None:
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    def refuse(reason: str) -> RaidShardProvisioningError:
        report["refusal"] = reason
        write()
        return RaidShardProvisioningError(reason, report)

    unknown = sorted(set(selected) - set(plan_shards(plan)))
    if unknown or not selected:
        raise refuse(f"unknown_plan_cohorts:{unknown}")
    try:
        report["plan_sources"] = check_plan_sources(plan, gear_profiles, trainers)
    except RaidShardSqlError as error:
        raise refuse(str(error)) from error
    reservation = plan_reservation(plan)
    query_characters, query_auth = readers or (_reader(character_url), _reader(auth_url))
    apply_ids = list(selected)
    preflight = evaluate_preflight(plan, fetch_preflight_facts(query_characters, query_auth, reservation), apply_ids)
    anchor = reservation["anchor_scenario_id"]
    if (not preflight["passed"] and anchor not in apply_ids
            and {row["check"] for row in preflight["refusals"]} == {"allocator_can_enter_reservation"}):
        apply_ids = [anchor] + apply_ids
        report["anchor_added"] = anchor
        preflight = evaluate_preflight(plan, fetch_preflight_facts(query_characters, query_auth, reservation),
                                       apply_ids)
    apply_ids = order_cohorts(reservation, apply_ids)
    report.update({"apply_scenario_ids": apply_ids, "anchor_scenario_id": anchor, "preflight": preflight})
    if not preflight["passed"]:
        raise refuse("preflight_refused")
    blocked = apply_refusals(True, pgrep(), character_url, auth_url)
    report["apply_refusals"] = blocked
    if blocked:
        raise refuse("apply_refused:" + ",".join(row["check"] for row in blocked))
    if not apply:
        report["passed"] = True
        write()
        return report
    cohort_sql = (statements or cohort_statements)(plan, apply_ids, gear_profiles, dbc_dir, trainers)
    if connect is None:
        from tools.bot_ml.extract_world_knowledge import connect_mysql as connect
    connection = connect(character_url)
    try:
        report["applied"] = execute_cohort_transactions(connection, cohort_sql, _database_name(character_url),
                                                        _database_name(auth_url))
    finally:
        connection.close()
    if report["applied"]["failed"]:
        raise refuse(f"cohort_apply_failed:{report['applied']['failed']}")
    readback = evaluate_preflight(plan, fetch_preflight_facts(query_characters, query_auth, reservation), apply_ids)
    missing_anchors = sorted(table for table, row in readback["allocators"].items() if not row["anchor_present"])
    report["readback_preflight"] = readback
    if not readback["passed"] or missing_anchors:
        raise refuse(f"readback_refused:{','.join(missing_anchors) or 'preflight'}")
    report["loadout_readback"] = _loadout_readback(plan, apply_ids, character_url, gear_profiles, dbc_dir,
                                                   trainers, fetch_loadouts)
    if not report["loadout_readback"]["passed"]:
        raise refuse("loadout_readback_failed")
    report["passed"] = True
    write()
    return report
