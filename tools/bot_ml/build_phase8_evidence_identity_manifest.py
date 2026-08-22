"""Build the current live Phase 8 database and runtime identity manifest."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from .build_baseline_inventory import _normalized_rows, _schema_identity, git_identity
from .common import write_json
from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf
from .live_validation_session import (
    build_session,
    canonical_sha256,
    ensure_healthy_matching_session,
    sha256_file,
    live_validation_lock,
)
from .phase8_evidence_identity import (
    SCHEMA,
    build_projection,
    profile_generation_identity,
    server_epoch_identity,
    validate_manifest,
)
from .run_live_bot_validation import (
    execute_soap_command,
    parse_json_objects,
    trinity_config_string,
    write_validation_config,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "artifacts/all_spec_program/phase8_live_calibration_20260719/evidence_identity_manifest.json"
)
WORLD_TABLES = (
    "bot_rotation_profile",
    "bot_rotation_action",
    "spell_threat",
    "spell_proc",
    "spell_script_names",
    "version",
)
CHARACTER_TABLES = (
    "characters",
    "character_bot_pool",
    "character_glyphs",
    "character_talent",
    "character_spell",
    "character_inventory",
    "item_instance",
    "character_pet",
    "pet_spell",
)


def _clean_source_identity(repository: Path, worldserver: Path) -> dict[str, Any]:
    """Fail closed unless the executable belongs to one exact clean Git tree."""
    source = git_identity(repository)
    commit = str(source.get("head") or "").lower()
    if (
        source.get("available") is not True
        or source.get("identity_complete") is not True
        or source.get("worktree_state") != "clean"
        or len(commit) not in (40, 64)
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise RuntimeError("evidence identity requires a clean, complete Git source tree")
    return {
        "git_commit": commit,
        "source_tree_clean": True,
        "worldserver_binary_sha256": sha256_file(worldserver.resolve()),
    }


def _query_rows(connection: Any, query: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, tuple(parameters))
        return _normalized_rows(cursor.fetchall())


def _database_identity(config: Path) -> dict[str, Any]:
    world_connection = connect_mysql(database_url_from_worldserver_conf(config, "WorldDatabaseInfo"))
    try:
        world_schema = _schema_identity(world_connection, list(WORLD_TABLES))
        profiles = _query_rows(
            world_connection,
            "SELECT * FROM `bot_rotation_profile` ORDER BY `class_id`, `spec_tag`, `role`, `id`",
        )
        actions = _query_rows(
            world_connection,
            "SELECT p.`class_id` AS `profile_class_id`, p.`spec_tag` AS `profile_spec_tag`, "
            "p.`role` AS `profile_role`, a.* FROM `bot_rotation_action` a "
            "JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id` "
            "ORDER BY p.`class_id`, p.`spec_tag`, p.`role`, a.`priority_bucket`, a.`sort_order`, a.`id`",
        )
        spell_threat = _query_rows(
            world_connection,
            "SELECT * FROM `spell_threat` ORDER BY `entry`",
        )
        spell_proc = _query_rows(
            world_connection,
            "SELECT * FROM `spell_proc` ORDER BY `SpellId`",
        )
        spell_script_names = _query_rows(
            world_connection,
            "SELECT * FROM `spell_script_names` ORDER BY `spell_id`, `ScriptName`",
        )
        version = _query_rows(world_connection, "SELECT * FROM `version` ORDER BY `core_version` LIMIT 1")
    finally:
        world_connection.close()

    character_connection = connect_mysql(database_url_from_worldserver_conf(config, "CharacterDatabaseInfo"))
    try:
        character_schema = _schema_identity(character_connection, list(CHARACTER_TABLES))
        pool = _query_rows(
            character_connection,
            "SELECT c.`guid`, c.`account`, c.`name`, c.`race`, c.`class`, c.`gender`, c.`level`, "
            "p.`role`, p.`class_spec`, p.`enabled`, p.`experiment_tags`, p.`notes` "
            "FROM `characters` c JOIN `character_bot_pool` p ON p.`guid` = c.`guid` "
            "WHERE p.`experiment_tags` = %s ORDER BY p.`class_spec`, c.`guid`",
            ("all_spec_candidate_pool",),
        )
        guids = sorted({int(row["guid"]) for row in pool})
        target_catalog = json.loads(
            (REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json").read_text(encoding="utf-8")
        )
        expected_specs = sorted(
            str(row.get("runtime_join_key") or "")
            for row in target_catalog.get("targets") or []
        )
        observed_specs = sorted(str(row.get("class_spec") or "") for row in pool)
        if (
            len(pool) != 31
            or len(guids) != 31
            or observed_specs != expected_specs
        ):
            raise ValueError("Phase 8 candidate pool does not exactly match the 31-target catalog")
        placeholders = ", ".join(["%s"] * len(guids))
        table_rows: dict[str, list[dict[str, Any]]] = {}
        queries = {
            "character_glyphs": f"SELECT * FROM `character_glyphs` WHERE `guid` IN ({placeholders}) ORDER BY `guid`, `talentGroup`",
            "character_talent": f"SELECT * FROM `character_talent` WHERE `guid` IN ({placeholders}) ORDER BY `guid`, `talentGroup`, `spell`",
            "character_spell": f"SELECT * FROM `character_spell` WHERE `guid` IN ({placeholders}) ORDER BY `guid`, `spell`",
            "character_inventory": f"SELECT * FROM `character_inventory` WHERE `guid` IN ({placeholders}) ORDER BY `guid`, `bag`, `slot`, `item`",
            "item_instance": f"SELECT i.* FROM `item_instance` i JOIN `character_inventory` ci ON ci.`item` = i.`guid` WHERE ci.`guid` IN ({placeholders}) ORDER BY i.`guid`",
            "character_pet": f"SELECT * FROM `character_pet` WHERE `owner` IN ({placeholders}) ORDER BY `owner`, `id`",
            "pet_spell": f"SELECT ps.* FROM `pet_spell` ps JOIN `character_pet` cp ON cp.`id` = ps.`guid` WHERE cp.`owner` IN ({placeholders}) ORDER BY ps.`guid`, ps.`spell`",
        }
        for name, query in queries.items():
            table_rows[name] = _query_rows(character_connection, query, guids)
    finally:
        character_connection.close()

    schema_payload = {"world": world_schema, "characters": character_schema}
    snapshot_payload = {
        "world": {
            "version": version,
            "profiles": profiles,
            "actions": actions,
            "spell_threat": spell_threat,
            "spell_proc": spell_proc,
            "spell_script_names": spell_script_names,
        },
        "characters": {"pool": pool, **table_rows},
    }
    return {
        "database_schema_sha256": canonical_sha256(schema_payload),
        "database_snapshot_sha256": canonical_sha256(snapshot_payload),
        "summary": {
            "world_profile_count": len(profiles),
            "world_action_count": len(actions),
            "world_spell_threat_count": len(spell_threat),
            "world_spell_proc_count": len(spell_proc),
            "world_spell_script_name_count": len(spell_script_names),
            "candidate_count": len(pool),
            "candidate_specs": observed_specs,
            "world_schema_sha256": world_schema["schema_sha256"],
            "character_schema_sha256": character_schema["schema_sha256"],
            "character_table_row_counts": {
                name: len(rows) for name, rows in sorted(table_rows.items())
            },
        },
    }


def _soap_payload(
    *,
    soap_url: str,
    soap_user: str,
    soap_password: str,
    command: str,
    action: str,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        output, returncode, timed_out = execute_soap_command(
            soap_url,
            soap_user,
            soap_password,
            command,
            min(15, max(1, int(deadline - time.monotonic()))),
        )
        payload = next(
            (
                row
                for row in reversed(parse_json_objects(output))
                if row.get("action") == action
            ),
            None,
        )
        if returncode == 0 and not timed_out and payload is not None:
            return payload
        time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
    raise RuntimeError(f"failed to read live runtime identity: {action}")


def _profile_target(catalog: Mapping[str, Any], target_spec: str | None) -> dict[str, Any]:
    targets = [row for row in catalog.get("targets") or [] if isinstance(row, Mapping)]
    if target_spec:
        targets = [row for row in targets if row.get("spec_target_id") == target_spec]
    if len(targets) != 1 and target_spec:
        raise RuntimeError(f"profile target must resolve exactly once: {target_spec}")
    if not targets:
        raise RuntimeError("profile target catalog is empty")
    return dict(targets[0])


def build_manifest(
    *,
    worldserver: Path,
    config: Path,
    session_environment: str,
    soap_url: str,
    soap_user: str,
    soap_password: str,
    identity_config_dir: Path,
    calibration_self_provided_baseline: bool = False,
    profile_target_spec: str | None = None,
) -> dict[str, Any]:
    initial_source_identity = _clean_source_identity(REPO_ROOT, worldserver)
    effective_config = write_validation_config(
        config,
        identity_config_dir,
        pool_tag="all_spec_candidate_pool",
        autostart=False,
        calibration_only=True,
        calibration_reference_conditions=not calibration_self_provided_baseline,
        calibration_self_provided_baseline=calibration_self_provided_baseline,
        console_enabled=False,
    )
    database = _database_identity(effective_config)
    profile_manifest = Path(
        trinity_config_string(effective_config, "BotWorld.ProfileManifest", "dataset/bot_runtime_profiles/profiles.json")
    )
    if not profile_manifest.is_absolute():
        profile_manifest = REPO_ROOT / profile_manifest
    fingerprint_paths = [
        path
        for path in (
            profile_manifest,
            REPO_ROOT / "dataset/validation_scenarios/validation_routes.jsonl",
            REPO_ROOT / "experiments/configs/validation_provisioning_cata_001.json",
            REPO_ROOT / "experiments/configs/phase8_dps_representatives_cata_p4_v1.json",
            REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json",
            REPO_ROOT / "dataset/validation_gear_profiles/profiles.json",
            REPO_ROOT / "dataset/validation_provisioning/manifest.json",
        )
        if path.is_file()
    ]
    restart_components = {
        name: database[name]
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
            raise RuntimeError("live SOAP responder does not match the owned worldserver process")
        if (
            int(cohort_payload.get("max_active_cohorts") or 0) != 1
            or int(cohort_payload.get("active_cohort_count") or 0) != 0
        ):
            raise RuntimeError("Phase 8 identity requires an idle serial worldserver owner")
        target_catalog = json.loads(
            (REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json").read_text(encoding="utf-8")
        )
        target = _profile_target(target_catalog, profile_target_spec)
        dump_command = "botauto rotations dump {class_id} {spec_tag} {role}".format(
            class_id=int(target["class_id"]),
            spec_tag=str(target.get("rotation_spec_tag") or target["runtime_join_key"]),
            role=str(target["role"]),
        )
        dump_payload = _soap_payload(
            soap_url=soap_url,
            soap_user=soap_user,
            soap_password=soap_password,
            command=dump_command,
            action="botauto_rotations_dump",
        )
        if dump_payload.get("ok") is not True:
            raise RuntimeError("failed to read live rotation snapshot identity")

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
        raise RuntimeError("owned worldserver session does not match the clean build identity")
    build_identity = {
        **initial_source_identity,
        "database_snapshot_sha256": str(database["database_snapshot_sha256"]),
        "database_schema_sha256": str(database["database_schema_sha256"]),
        "profile_content_hash": profile_identity["profile_content_hash"],
    }
    projection_sha256 = canonical_sha256(build_projection({"build_identity": build_identity}))
    manifest = {
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
        "build_identity": build_identity,
        "runtime_identity": {**server_identity, **profile_identity},
        "database_summary": database["summary"],
        "rotation_profile_snapshot": dump_payload,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return validate_manifest(manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver"))
    parser.add_argument("--config", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--session-environment", default="phase8-calibration")
    parser.add_argument("--soap-url", default="http://127.0.0.1:7878/")
    parser.add_argument("--soap-user", default=os.environ.get("TRINITY_SOAP_USER"))
    parser.add_argument("--soap-password", default=os.environ.get("TRINITY_SOAP_PASSWORD"))
    parser.add_argument(
        "--calibration-self-provided-baseline",
        action="store_true",
        help=(
            "Bind the identity to the self-provided flask, food, pre-pot, and "
            "combat-potion calibration config instead of full reference conditions."
        ),
    )
    parser.add_argument(
        "--profile-target-spec",
        help="Exact all-spec target whose runtime rotation dump is retained.",
    )
    parser.add_argument(
        "--profile-output",
        type=Path,
        help="Write the exact runtime rotation dump as a standalone review input.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.soap_user or not args.soap_password:
        raise SystemExit("TRINITY_SOAP_USER and TRINITY_SOAP_PASSWORD are required")
    output_path = args.output.resolve()
    manifest = build_manifest(
        worldserver=args.worldserver.resolve(),
        config=args.config.resolve(),
        session_environment=args.session_environment,
        soap_url=args.soap_url,
        soap_user=args.soap_user,
        soap_password=args.soap_password,
        identity_config_dir=output_path.parent / "identity_runtime_config",
        calibration_self_provided_baseline=(
            args.calibration_self_provided_baseline
        ),
        profile_target_spec=args.profile_target_spec,
    )
    write_json(output_path, manifest)
    if args.profile_output:
        write_json(args.profile_output.resolve(), manifest["rotation_profile_snapshot"])
    print(json.dumps({
        "schema": manifest["schema"],
        "output": str(args.output.resolve()),
        "manifest_sha256": manifest["manifest_sha256"],
        "runtime_identity": manifest["runtime_identity"],
        "database_summary": manifest["database_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
