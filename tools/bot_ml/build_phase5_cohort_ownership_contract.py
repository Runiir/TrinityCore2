from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.bot_ml.build_phase4_rotation_contract import WorldserverSession


REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def static_contract(repository: Path = REPO_ROOT) -> dict[str, Any]:
    header = (repository / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text()
    source = (repository / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()
    commands = (repository / "src/server/scripts/Commands/cs_healerbot.cpp").read_text()
    pool_reset = source[
        source.index("bool BotWorldPopulationMgr::ResetValidationBotPool") :
        source.index("std::string BotWorldPopulationMgr::RuntimeProfilesJson")
    ]
    cohort_start = source[
        source.index("bool BotWorldPopulationMgr::StartAutonomyForCohort") :
        source.index("std::string BotWorldPopulationMgr::StopAutonomyForCohort")
    ]

    legacy_globals = (
        "bool _active = false;",
        "std::vector<WorldBotState> _bots;",
        "std::map<uint64, PendingHealCast> _pendingHealCasts;",
        "std::deque<CombatLogEvent> _combatLogRecentEvents;",
        "std::vector<ValidationRouteManifestNode> _validationRouteManifest;",
    )
    checks = {
        "cohort_runtime_explicit": "struct CohortRuntime" in header,
        "party_runtime_explicit": "struct PartyRuntime" in header,
        "legacy_global_runtime_fields_removed": not any(
            marker in header for marker in legacy_globals
        ),
        "cohort_owns_lifecycle_and_calibration": all(
            marker in header
            for marker in (
                "uint64 AttemptId = 0;",
                "uint32 RecordingWindowElapsedMs = 0;",
                "uint64 CalibrationStartedMs = 0;",
                "BotTelemetryBuffer TelemetryBuffer;",
                "BotExperimentCoordinator ExperimentCoordinator;",
            )
        ),
        "party_owns_route_heals_trace_and_combatlog": all(
            marker in header
            for marker in (
                "std::vector<WorldBotState> Bots;",
                "uint64 ValidationRouteGeneration = 0;",
                "std::map<uint64, PendingHealCast> PendingHealCasts;",
                "std::deque<CombatLogEvent> CombatLogRecentEvents;",
                "std::vector<ValidationRouteEvidence> ValidationRouteTerminalEvidence;",
            )
        ),
        "lease_identity_complete": all(
            marker in header
            for marker in (
                "uint64 ServerEpoch = 0;",
                "std::string CohortId;",
                "uint64 AttemptId = 0;",
                "std::string RoleSlot;",
                "mutable std::mutex _leaseMutex;",
            )
        ),
        "owner_scoped_claim_and_release": all(
            marker in source
            for marker in (
                "BotWorldPopulationMgr::ClaimBotGuid",
                "BotWorldPopulationMgr::ReleaseBotGuid",
                "itr->second.ServerEpoch != _serverEpoch",
                "itr->second.CohortId != Cohort().Id",
                "itr->second.AttemptId != Cohort().AttemptId",
            )
        ),
        "attempt_restart_releases_old_leases_first": (
            "bool reuseActiveAttempt = Cohort().Active" in cohort_start
            and cohort_start.index("StopAutonomy();")
            < cohort_start.index("++Cohort().AttemptId;")
        ),
        "exact_pool_tag_matching": (
            "cbp.experiment_tags = '" in source
            and "cbp.`experiment_tags` = '" in source
            and "experiment_tags LIKE '%" not in source
        ),
        "global_pool_reset_removed": (
            "SET p.`in_use` = 0 WHERE " in source
            and "poolPredicate" in source
            and "ValidationProvisionOnPrepare" in source
        ),
        "pool_reset_holds_lease_guard": (
            "std::lock_guard<std::mutex> guard(_leaseMutex);" in pool_reset
            and pool_reset.index("std::lock_guard<std::mutex> guard(_leaseMutex);")
            < pool_reset.index("CharacterDatabase.DirectExecute")
        ),
        "serial_limit_retained": "MaxActiveCohorts = 1" in header,
        "profile_snapshot_pinned_per_cohort": all(
            marker in source
            for marker in (
                "Cohort().PinnedProfileGeneration = BotClassSpecActionProfileStore::ActiveDbGeneration()",
                "Cohort().PinnedProfileContentHash = BotClassSpecActionProfileStore::ActiveDbContentHash()",
            )
        ),
        "cohort_addressed_commands": all(
            marker in commands
            for marker in (
                '"create"',
                '"prepare"',
                '"start"',
                '"stop"',
                '"status"',
                '"diagnose"',
                '"trace"',
                '"combatlog"',
                '"calibrate"',
                "GetStatusJsonForCohort",
                "GetBotDiagnosisJsonForCohort",
                "GetBotTraceJsonForCohort",
                "GetCombatLogJsonForCohort",
            )
        ),
        "ambiguous_global_operations_rejected": (
            "ambiguous_global_cohort" in commands
            and "ResolveGlobalCohortId" in commands
            and all(
                marker in commands
                for marker in (
                    'ResolveGlobalAutoCohort(handler, "botauto_profiles")',
                    'ResolveGlobalAutoCohort(handler, "botauto_profile")',
                    'ResolveGlobalAutoCohort(handler, "botauto_spawn")',
                    'ResolveGlobalAutoCohort(handler, "botauto_despawn")',
                    'ResolveGlobalAutoCohort(handler, "botauto_debug")',
                )
            )
        ),
        "runtime_isolation_probe_exposed": (
            "GetCohortIsolationContractJson" in source
            and "botauto_ownership" in source
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def _read_combat_log(
    session: WorldserverSession,
    cohort_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    first = session.command(
        f"botauto combatlog {cohort_id}", "botauto_combatlog_chunk"
    )
    chunks = [first]
    for sequence in range(1, first["chunk_count"]):
        line = session.wait_for(
            lambda value, expected=sequence: (
                '"action":"botauto_combatlog_chunk"' in value
                and f'"sequence":{expected}' in value
            ),
            30,
        )
        chunks.append(json.loads(line[line.index("{") :]))
    complete_line = session.wait_for(
        lambda value: '"action":"botauto_combatlog_complete"' in value,
        30,
    )
    complete = json.loads(complete_line[complete_line.index("{") :])
    encoded = b"".join(
        base64.b64decode(chunk["data"])
        for chunk in sorted(chunks, key=lambda chunk: chunk["sequence"])
    )
    return chunks, complete, json.loads(encoded)


def live_contract(binary: Path, worldserver_conf: Path) -> dict[str, Any]:
    session = WorldserverSession(binary, worldserver_conf)
    try:
        session.wait_for(lambda line: " ready..." in line, 300)
        ownership = session.command("botauto ownership", "botauto_ownership")
        cohorts = session.command("botauto cohorts", "botauto_cohorts")
        status_a = session.command("botauto status phase5_probe_a", "botauto_status")
        status_b = session.command("botauto status phase5_probe_b", "botauto_status")
        ambiguous = session.command("botauto status", "botauto_status")
        ambiguous_profile = session.command("botauto profile clear", "botauto_profile")
        ambiguous_spawn = session.command("botauto spawn 1", "botauto_spawn")
        ambiguous_despawn = session.command("botauto despawn all", "botauto_despawn")
        ambiguous_debug = session.command("botauto debug all", "botauto_debug")
        diagnosis = session.command(
            "botauto diagnose phase5_probe_b all", "botauto_diagnose"
        )
        trace = session.command("botauto trace phase5_probe_a 5", "botauto_trace")
        calibration = session.command(
            "botauto calibrate phase5_probe_b status", "botauto_calibrate_status"
        )
        combat_chunks, combat_complete, combat_log = _read_combat_log(
            session, "phase5_probe_a"
        )
    finally:
        session.close()

    isolation_checks = ownership.get("checks", {})
    required_isolation_checks = {
        "atomic_guid_lease_conflict_rejected",
        "owner_scoped_release",
        "group_and_roles_isolated",
        "instance_isolated",
        "route_isolated",
        "calibration_clocks_isolated",
        "recording_windows_isolated",
        "pending_heals_isolated",
        "threat_healing_metrics_isolated",
        "trace_isolated",
        "combat_log_isolated",
        "telemetry_isolated",
        "evidence_isolated",
        "serial_execution_limit",
    }
    checks = {
        "ownership_probe_passed": ownership.get("ok") is True,
        "all_isolation_domains_proved": required_isolation_checks
        <= {key for key, value in isolation_checks.items() if value is True},
        "two_constructed_cohorts_present": {
            "phase5_probe_a",
            "phase5_probe_b",
        }
        <= {row.get("cohort_id") for row in cohorts.get("cohorts", [])},
        "max_active_cohorts_one": cohorts.get("max_active_cohorts") == 1,
        "probe_cleanup_left_empty_parties": all(
            row.get("party_bot_count") == 0
            for row in cohorts.get("cohorts", [])
            if row.get("cohort_id") in {"phase5_probe_a", "phase5_probe_b"}
        ),
        "addressed_status_isolated": (
            status_a.get("cohort_id") == "phase5_probe_a"
            and status_b.get("cohort_id") == "phase5_probe_b"
        ),
        "ambiguous_global_status_rejected": (
            ambiguous.get("ok") is False
            and ambiguous.get("failure_reason") == "ambiguous_global_cohort"
        ),
        "other_global_aliases_rejected": all(
            response.get("ok") is False
            and response.get("failure_reason") == "ambiguous_global_cohort"
            for response in (
                ambiguous_profile,
                ambiguous_spawn,
                ambiguous_despawn,
                ambiguous_debug,
            )
        ),
        "addressed_diagnosis": diagnosis.get("cohort_id") == "phase5_probe_b",
        "addressed_trace": trace.get("cohort_id") == "phase5_probe_a",
        "addressed_calibration": calibration.get("cohort_id")
        == "phase5_probe_b",
        "addressed_combat_log": (
            all(
                chunk.get("cohort_id") == "phase5_probe_a"
                for chunk in combat_chunks
            )
            and combat_complete.get("cohort_id") == "phase5_probe_a"
            and combat_complete.get("chunk_count") == len(combat_chunks)
            and combat_complete.get("total_bytes")
            == sum(
                len(base64.b64decode(chunk["data"]))
                for chunk in combat_chunks
            )
            and combat_log.get("cohort_id") == "phase5_probe_a"
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "server_epoch": ownership.get("server_epoch"),
        "cohort_count": cohorts.get("cohort_count"),
        "isolation_checks": isolation_checks,
    }


def build_contract(
    *,
    repository: Path = REPO_ROOT,
    worldserver_binary: Path,
    worldserver_conf: Path,
) -> dict[str, Any]:
    static = static_contract(repository)
    live = live_contract(worldserver_binary, worldserver_conf)
    payload = {
        "schema": "all_spec_phase5_cohort_ownership_contract_v1",
        "static": static,
        "live": live,
        "gate_passed": static["passed"] and live["passed"],
    }
    payload["contract_sha256"] = _sha256_json(payload)
    return payload


def write_contract(output_dir: Path, contract: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    contract_path = output_dir / "contract.json"
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    manifest = {
        "schema": "all_spec_phase5_cohort_ownership_contract_manifest_v1",
        "gate_passed": contract["gate_passed"],
        "contract_sha256": contract["contract_sha256"],
        "files": {
            "contract.json": hashlib.sha256(contract_path.read_bytes()).hexdigest()
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--worldserver-binary", type=Path, required=True)
    parser.add_argument("--worldserver-conf", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(
        worldserver_binary=args.worldserver_binary.resolve(),
        worldserver_conf=args.worldserver_conf.resolve(),
    )
    write_contract(args.output_dir, contract)
    print(json.dumps(contract, sort_keys=True))
    if not contract["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
