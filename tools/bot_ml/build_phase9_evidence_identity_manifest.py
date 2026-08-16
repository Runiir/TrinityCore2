"""Build the current Phase 9 database, route, and live runtime identity manifest."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .build_phase8_evidence_identity_manifest import (
    _clean_source_identity,
    _database_identity,
    _soap_payload,
)
from .common import write_json
from .live_validation_session import (
    build_session,
    canonical_sha256,
    ensure_healthy_matching_session,
    live_validation_lock,
    sha256_file,
)
from .phase9_evidence_identity import (
    SCHEMA,
    build_projection,
    profile_generation_identity,
    server_epoch_identity,
    validate_manifest,
)
from .run_live_bot_validation import (
    load_validation_routes_for_scenario,
    trinity_config_string,
    write_validation_config,
    write_validation_route_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "artifacts/all_spec_program/phase9_serial_canaries_20260728/evidence_identity_manifest.json"
)
TARGET_CATALOG = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
PAIR_POLICY = REPO_ROOT / "experiments/configs/stonecore_phase9_pair_policy_v1.json"
PAIRWISE_MATRIX = REPO_ROOT / "experiments/configs/stonecore_phase9_pairwise_matrix_v1.json"
ROUTE_SOURCE = REPO_ROOT / "dataset/validation_scenarios/validation_routes.jsonl"


def build_manifest(
    *,
    worldserver: Path,
    config: Path,
    session_environment: str,
    soap_url: str,
    soap_user: str,
    soap_password: str,
    output_path: Path,
) -> dict[str, object]:
    initial_source_identity = _clean_source_identity(REPO_ROOT, worldserver)
    runtime_dir = output_path.parent / "session_runtime"
    routes = load_validation_routes_for_scenario(
        REPO_ROOT / "dataset/validation_scenarios",
        "stonecore_5h",
    )
    if len(routes) != 14:
        raise ValueError("Phase 9 identity requires the complete 14-node Stonecore route")
    route_manifest_path, route_manifest = write_validation_route_manifest(
        runtime_dir,
        "stonecore_5h",
        routes,
    )
    effective_config = write_validation_config(
        config,
        runtime_dir,
        pool_tag="all_spec_candidate_pool",
        validation_route=routes[0],
        validation_route_manifest_path=route_manifest_path,
        autostart=False,
        calibration_only=False,
        console_enabled=False,
    )
    database = _database_identity(effective_config)
    profile_manifest = Path(
        trinity_config_string(
            effective_config,
            "BotWorld.ProfileManifest",
            "dataset/bot_runtime_profiles/profiles.json",
        )
    )
    if not profile_manifest.is_absolute():
        profile_manifest = REPO_ROOT / profile_manifest
    fingerprint_paths = [
        path
        for path in (
            profile_manifest,
            ROUTE_SOURCE,
            REPO_ROOT / "experiments/configs/validation_provisioning_cata_001.json",
            REPO_ROOT / "experiments/configs/phase8_dps_representatives_cata_p4_v1.json",
            REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json",
            REPO_ROOT / "dataset/validation_gear_profiles/profiles.json",
            REPO_ROOT / "dataset/validation_provisioning/manifest.json",
            PAIRWISE_MATRIX,
            PAIR_POLICY,
        )
        if path.is_file()
    ]
    restart_components = {
        name: str(database[name])
        for name in ("database_snapshot_sha256", "database_schema_sha256")
    }
    session = build_session(
        REPO_ROOT,
        session_environment,
        worldserver,
        effective_config,
        fingerprint_paths=fingerprint_paths,
        restart_components=restart_components,
    )
    with live_validation_lock(REPO_ROOT, session_environment):
        action = ensure_healthy_matching_session(session)
        metadata = session.metadata()
        main_pid = int(action.status.properties.get("MainPID") or 0)
        cohort_payload = _soap_payload(
            soap_url=soap_url,
            soap_user=soap_user,
            soap_password=soap_password,
            command=".botauto cohorts",
            action="botauto_cohorts",
        )
        responder_pid = int(cohort_payload.get("server_process_id") or 0)
        if main_pid <= 0 or responder_pid != main_pid:
            raise RuntimeError("live SOAP responder does not match the owned Phase 9 worldserver process")
        if (
            int(cohort_payload.get("max_active_cohorts") or 0) != 1
            or int(cohort_payload.get("active_cohort_count") or 0) != 0
        ):
            raise RuntimeError("Phase 9 identity requires an idle serial worldserver owner")
        target_catalog = json.loads(TARGET_CATALOG.read_text(encoding="utf-8"))
        target = (target_catalog.get("targets") or [])[0]
        dump_payload = _soap_payload(
            soap_url=soap_url,
            soap_user=soap_user,
            soap_password=soap_password,
            command="botauto rotations dump {class_id} {spec_tag} {role}".format(
                class_id=int(target["class_id"]),
                spec_tag=str(target.get("rotation_spec_tag") or target["runtime_join_key"]),
                role=str(target["role"]),
            ),
            action="botauto_rotations_dump",
        )
        if dump_payload.get("ok") is not True:
            raise RuntimeError("failed to read the live Phase 9 rotation snapshot identity")

    server_identity = server_epoch_identity(
        server_epoch=int(cohort_payload.get("server_epoch") or 0),
        server_process_id=responder_pid,
        session_fingerprint=str(metadata.get("session_fingerprint") or ""),
        max_active_cohorts=int(cohort_payload.get("max_active_cohorts") or 0),
    )
    profile_identity = profile_generation_identity(
        profile_generation=int(dump_payload.get("snapshot_generation") or 0),
        profile_content_hash=str(dump_payload.get("snapshot_content_hash") or ""),
    )
    final_source_identity = _clean_source_identity(REPO_ROOT, worldserver)
    if final_source_identity != initial_source_identity:
        raise RuntimeError("source commit or worldserver binary changed while building evidence identity")
    final_database = _database_identity(effective_config)
    if any(
        final_database[name] != database[name]
        for name in ("database_snapshot_sha256", "database_schema_sha256")
    ):
        raise RuntimeError("database snapshot or schema changed while building evidence identity")
    if (
        str(metadata.get("git_head") or "").lower() != initial_source_identity["git_commit"]
        or str(metadata.get("binary_sha256") or "").lower()
        != initial_source_identity["worldserver_binary_sha256"]
    ):
        raise RuntimeError("owned Phase 9 worldserver session does not match the clean build identity")
    build_identity = {
        **initial_source_identity,
        "database_snapshot_sha256": str(database["database_snapshot_sha256"]),
        "database_schema_sha256": str(database["database_schema_sha256"]),
        "profile_content_hash": profile_identity["profile_content_hash"],
    }
    projection_sha256 = canonical_sha256(build_projection({"build_identity": build_identity}))
    artifact_hashes = {
        "target_catalog_sha256": sha256_file(TARGET_CATALOG),
        "pair_policy_sha256": sha256_file(PAIR_POLICY),
        "pairwise_matrix_sha256": sha256_file(PAIRWISE_MATRIX),
        "route_manifest_sha256": sha256_file(route_manifest_path),
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "component_hashes": {
            **restart_components,
            "source_identity_sha256": canonical_sha256(
                {
                    "git_commit": build_identity["git_commit"],
                    "source_tree_clean": True,
                }
            ),
            "worldserver_binary_sha256": build_identity["worldserver_binary_sha256"],
            "server_epoch_sha256": canonical_sha256(server_identity),
            "profile_generation_sha256": canonical_sha256(profile_identity),
            "build_projection_sha256": projection_sha256,
        },
        "artifact_hashes": artifact_hashes,
        "build_identity": build_identity,
        "runtime_identity": {**server_identity, **profile_identity},
        "database_summary": database["summary"],
        "route_summary": {
            "scenario_id": "stonecore_5h",
            "route_node_count": len(routes),
            "route_manifest_path": str(route_manifest_path.relative_to(REPO_ROOT)),
        },
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return validate_manifest(manifest, artifact_hashes=artifact_hashes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver"))
    parser.add_argument("--config", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--session-environment", default="phase9-serial-stonecore")
    parser.add_argument("--soap-url", default="http://127.0.0.1:7878/")
    parser.add_argument("--soap-user", default=os.environ.get("TRINITY_SOAP_USER"))
    parser.add_argument("--soap-password", default=os.environ.get("TRINITY_SOAP_PASSWORD"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.soap_user or not args.soap_password:
        raise SystemExit("TRINITY_SOAP_USER and TRINITY_SOAP_PASSWORD are required")
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(
        worldserver=args.worldserver.resolve(),
        config=args.config.resolve(),
        session_environment=args.session_environment,
        soap_url=args.soap_url,
        soap_user=args.soap_user,
        soap_password=args.soap_password,
        output_path=output_path,
    )
    write_json(output_path, manifest)
    print(
        json.dumps(
            {
                "schema": manifest["schema"],
                "output": str(output_path),
                "manifest_sha256": manifest["manifest_sha256"],
                "runtime_identity": manifest["runtime_identity"],
                "database_summary": manifest["database_summary"],
                "route_summary": manifest["route_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
