"""The explicitly admitted checkpoint dialects for the atomic bundle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.raid_program.blocker_recurrence_ledger import (
    _canonical_config_identity,
    _command_sha256,
    _manifest_sha256,
    _result_sha256,
)
from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX,
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
    MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY,
    MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
    MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX,
    MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
    PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
    PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX,
    PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
    RecurrenceAdmissionError,
    chainwielder_checkpoint_seal,
    magmaw_transfer_checkpoint_seal,
    profile_combat_range_checkpoint_seal,
)
from tools.raid_program.recurrence_checkpoint_seals import (
    profile_combat_range_checkpoint_contract,
)


CHAINWIELDER = "chainwielder"
MAGMAW_TRANSFER = "magmaw_transfer"
PROFILE_COMBAT_RANGE = "profile_combat_range"
CHAINWIELDER_ACTOR_GUID = 30008
PROFILE_COMBAT_RANGE_ACTOR_GUID = 30010
PROFILE_COMBAT_RANGE_TARGET_GUID = 39
PROFILE_COMBAT_RANGE_TARGET_ENTRY = 41570
PROFILE_COMBAT_RANGE_CHECKPOINT_CASE_ID = "elemental_magmaw_too_close_v1"
CHAINWIELDER_ROUTE_NODE_IDS = (
    "bwd.magmaw.chainwielder",
    "bwd.magmaw.drudges",
    "bwd.magmaw.encounter",
)
MAGMAW_TRANSFER_ROUTE_NODE_IDS = (
    "bwd.entry.regroup",
    *CHAINWIELDER_ROUTE_NODE_IDS,
)
CHAINWIELDER_LEDGER_RELATIVE_PATH = Path(
    "experiments/configs/cata_raid_magmaw_blocker_recurrence_v1.json"
)
MAGMAW_TRANSFER_LEDGER_RELATIVE_PATH = Path(
    "experiments/configs/cata_raid_magmaw_transfer_lane_checkpoint_recurrence_v1.json"
)
PROFILE_COMBAT_RANGE_LEDGER_RELATIVE_PATH = Path(
    "experiments/configs/cata_raid_magmaw_blocker_recurrence_v1.json"
)
MAGMAW_TRANSFER_ROUTE_FIELDS = (
    ("bwd.entry.regroup", 669, "regroup", 0),
    ("bwd.magmaw.chainwielder", 669, "trash", 42649),
    ("bwd.magmaw.drudges", 669, "trash", 42362),
    ("bwd.magmaw.encounter", 669, "boss", 41570),
)
MAGMAW_TRANSFER_FIXTURE_REVISION = 2
MAGMAW_TRANSFER_FIXTURE_COMMAND = [
    "pixi",
    "run",
    "pytest",
    "-q",
    "tests/test_magmaw_transfer_lane_checkpoint.py",
    "tests/test_magmaw_transfer_checkpoint_capture.py",
]
MAGMAW_TRANSFER_RETAINED_RUNS = [
    {
        "run_id": "magmaw-transfer-lane-offline-capture-dialect-v1",
        "route_completed": False,
        "blockers": {
            "magmaw_transfer_lane_map_bound_checkpoint_missing": "occurred",
        },
        "admission": {"fixture_revisions": {}},
    },
    {
        "run_id": (
            "map669-transfer-checkpoint-1485b51d30-"
            "terrain-projection-false-reject"
        ),
        "route_completed": False,
        "blockers": {
            "magmaw_transfer_lane_map_bound_checkpoint_missing": "occurred",
        },
        "admission": {
            "source_identity": "1485b51d304498f25b02504854b1ffc7c6f6077e",
            "config_identity": _canonical_config_identity(),
            "fixture_revisions": {
                MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID: 1,
            },
        },
        "evidence": (
            "artifacts/cata_raid_program/"
            "map669_transfer_checkpoint_1485b51d30_"
            "terrain_projection_false_reject_20260901.dvc"
        ),
        "first_broken_edge": (
            "magmaw_transfer_checkpoint_planner_receipt_failed_"
            "after_selected_endpoint_reached"
        ),
    },
]
PROFILE_COMBAT_RANGE_ROUTE_NODE_IDS = (
    "bwd.magmaw.encounter",
)
PROFILE_COMBAT_RANGE_ROUTE_FIELDS = (
    ("bwd.entry.regroup", 669, "regroup", 0),
    ("bwd.magmaw.chainwielder", 669, "trash", 42649),
    ("bwd.magmaw.drudges", 669, "trash", 42362),
    ("bwd.magmaw.encounter", 669, "boss", PROFILE_COMBAT_RANGE_TARGET_ENTRY),
)
PROFILE_COMBAT_RANGE_FIXTURE_REVISION = 1
PROFILE_COMBAT_RANGE_FIXTURE_COMMAND = [
    "pixi",
    "run",
    "pytest",
    "-q",
    "tests/test_profile_combat_range_production_fixture.py",
    "tests/test_profile_combat_range_checkpoint_capture.py",
]
PROFILE_COMBAT_RANGE_CAUSAL_SIGNATURE = (
    "generic_non_drudge_too_close_profile_action_has_no_range_movement_owner"
)


class DialectError(RuntimeError):
    pass


def select_dialect(
    *, actor_guid: int, checkpoint_fixture_id: str,
    checkpoint_case_id: str | None,
) -> str:
    """Accept only one of the fully enumerated checkpoint tuples."""

    if (
        actor_guid == CHAINWIELDER_ACTOR_GUID
        and checkpoint_fixture_id == CHAINWIELDER_CHECKPOINT_FIXTURE_ID
        and checkpoint_case_id is None
    ):
        return CHAINWIELDER
    if (
        actor_guid == MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID
        and checkpoint_fixture_id == MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        and checkpoint_case_id == MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
    ):
        return MAGMAW_TRANSFER
    if (
        actor_guid == PROFILE_COMBAT_RANGE_ACTOR_GUID
        and checkpoint_fixture_id == PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID
        and checkpoint_case_id == PROFILE_COMBAT_RANGE_CHECKPOINT_CASE_ID
    ):
        return PROFILE_COMBAT_RANGE
    # Keep the established public failure reason for existing callers.
    raise DialectError("chainwielder_identity_input_mismatch")


def route_node_ids(dialect: str) -> tuple[str, ...]:
    if dialect == CHAINWIELDER:
        return CHAINWIELDER_ROUTE_NODE_IDS
    if dialect == MAGMAW_TRANSFER:
        return MAGMAW_TRANSFER_ROUTE_NODE_IDS
    if dialect == PROFILE_COMBAT_RANGE:
        return PROFILE_COMBAT_RANGE_ROUTE_NODE_IDS
    raise DialectError("checkpoint_dialect_invalid")


def initial_node_id(dialect: str) -> str:
    return route_node_ids(dialect)[0]


def ledger_relative_path(dialect: str) -> Path:
    if dialect == CHAINWIELDER:
        return CHAINWIELDER_LEDGER_RELATIVE_PATH
    if dialect == MAGMAW_TRANSFER:
        return MAGMAW_TRANSFER_LEDGER_RELATIVE_PATH
    if dialect == PROFILE_COMBAT_RANGE:
        return PROFILE_COMBAT_RANGE_LEDGER_RELATIVE_PATH
    raise DialectError("checkpoint_dialect_invalid")


def validate_ledger_manifest(
    dialect: str, *, ledger: Path, decision: Path, suite_receipt: Path,
) -> None:
    """Validate the dedicated transfer registration, not arbitrary fixtures."""

    if dialect == CHAINWIELDER:
        return
    if dialect == PROFILE_COMBAT_RANGE:
        _validate_profile_combat_range_ledger_manifest(
            ledger=ledger, decision=decision, suite_receipt=suite_receipt,
        )
        return
    if dialect != MAGMAW_TRANSFER:
        raise DialectError("checkpoint_dialect_invalid")
    try:
        ledger_value = json.loads(ledger.read_text(encoding="utf-8"))
        decision_value = json.loads(decision.read_text(encoding="utf-8"))
        suite_value = json.loads(suite_receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DialectError("magmaw_transfer_ledger_manifest_invalid") from error
    bank = ledger_value.get("regression_bank") if isinstance(ledger_value, dict) else None
    fixtures = bank.get("fixtures") if isinstance(bank, dict) else None
    ledger_runs = ledger_value.get("runs") if isinstance(ledger_value, dict) else None
    if (
        not isinstance(ledger_value, dict)
        or ledger_value.get("schema") != "trinity_raid_blocker_recurrence_v1"
        or ledger_value.get("route")
            != "blackwing_descent_10n_magmaw_diagnostic"
        or not isinstance(bank, dict)
        or bank.get("schema") != "trinity_raid_regression_bank_v1"
        or bank.get("route")
            != "blackwing_descent_10n_magmaw_diagnostic"
        or bank.get("current_identity") != {
            "config_identity": _canonical_config_identity(),
        }
        or bank.get("fixture_history")
            != [MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID]
        or bank.get("fixture_expansion_requests") != []
        or not isinstance(fixtures, list)
        or len(fixtures) != 1
        or not isinstance(fixtures[0], dict)
        or fixtures[0].get("fixture_id")
            != MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        or fixtures[0].get("revision")
            != MAGMAW_TRANSFER_FIXTURE_REVISION
        or fixtures[0].get("evidence_boundary") != "observation_only"
        or fixtures[0].get("command") != MAGMAW_TRANSFER_FIXTURE_COMMAND
        or not isinstance(ledger_runs, list)
        or ledger_runs != MAGMAW_TRANSFER_RETAINED_RUNS
    ):
        raise DialectError("magmaw_transfer_ledger_manifest_mismatch")
    if (
        not isinstance(decision_value, dict)
        or decision_value.get("fixture_expansion_admitted") is not True
        or decision_value.get("build_admitted") is not False
        or decision_value.get("canary_admitted") is not False
        or decision_value.get("fixture_expansion_target_ids")
            != [MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID]
        or decision_value.get("pending_fixture_ids")
            != [MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID]
        or decision_value.get("fixture_expansion_requests") != []
    ):
        raise DialectError("magmaw_transfer_ledger_decision_mismatch")
    rows = suite_value.get("verifications") if isinstance(suite_value, dict) else None
    expected_manifest_sha256 = _manifest_sha256(bank)
    expected_config_identity = _canonical_config_identity()
    suite_fields = {
        "schema", "manifest_sha256", "source_identity", "config_identity",
        "fixture_ids", "verifications",
    }
    row_fields = {
        "fixture_id", "passed", "returncode", "timed_out", "command_sha256",
        "fixture_revision", "stdout_sha256", "stderr_sha256", "result_sha256",
        "source_identity", "config_identity", "passed_after_run_id",
    }
    if (
        not isinstance(suite_value, dict)
        or set(suite_value) != suite_fields
        or suite_value.get("schema")
            != "trinity_raid_regression_suite_receipt_v1"
        or suite_value.get("fixture_ids")
            != [MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID]
        or suite_value.get("manifest_sha256") != expected_manifest_sha256
        or suite_value.get("config_identity") != expected_config_identity
        or not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], dict)
        or set(rows[0]) != row_fields
        or rows[0].get("fixture_id")
            != MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        or rows[0].get("fixture_revision")
            != MAGMAW_TRANSFER_FIXTURE_REVISION
        or rows[0].get("passed") is not True
        or rows[0].get("returncode") != 0
        or rows[0].get("timed_out") is not False
        or rows[0].get("command_sha256")
            != _command_sha256(fixtures[0]["command"])
        or not isinstance(rows[0].get("stdout_sha256"), str)
        or not isinstance(rows[0].get("stderr_sha256"), str)
        or rows[0].get("result_sha256") != _result_sha256(
            rows[0].get("returncode"), rows[0].get("timed_out"),
            rows[0].get("stdout_sha256"), rows[0].get("stderr_sha256"),
        )
        or rows[0].get("source_identity")
            != suite_value.get("source_identity")
        or rows[0].get("config_identity") != expected_config_identity
        or rows[0].get("passed_after_run_id")
            != ledger_runs[-1]["run_id"]
    ):
        raise DialectError("magmaw_transfer_suite_receipt_mismatch")


def _validate_profile_combat_range_ledger_manifest(
    *, ledger: Path, decision: Path, suite_receipt: Path,
) -> None:
    """Validate the exact pending generic profile-range fixture registration."""

    try:
        ledger_value = json.loads(ledger.read_text(encoding="utf-8"))
        decision_value = json.loads(decision.read_text(encoding="utf-8"))
        suite_value = json.loads(suite_receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DialectError("profile_combat_range_ledger_manifest_invalid") from error
    bank = ledger_value.get("regression_bank") if isinstance(ledger_value, dict) else None
    fixtures = bank.get("fixtures") if isinstance(bank, dict) else None
    history = bank.get("fixture_history") if isinstance(bank, dict) else None
    expected_fixture = {
        "fixture_id": PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        "revision": PROFILE_COMBAT_RANGE_FIXTURE_REVISION,
        "causal_signature": PROFILE_COMBAT_RANGE_CAUSAL_SIGNATURE,
        "evidence_boundary": "observation_only",
        "required_production_boundary": (
            "one sealed exact-current-binary worldserver replay must correlate "
            "an actual hazard producer/release, the exact "
            "world.profile_combat_range candidate, native launch and multi-tick "
            "decreasing progress, and a later ordinary same-target cast under "
            "one verified actor/target/scope/checkpoint generation; this "
            "tools-only repair cannot promote it"
        ),
        "command": PROFILE_COMBAT_RANGE_FIXTURE_COMMAND,
    }
    matching = [
        row for row in fixtures or []
        if isinstance(row, dict)
        and row.get("fixture_id") == PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID
    ]
    if (
        not isinstance(ledger_value, dict)
        or ledger_value.get("schema") != "trinity_raid_blocker_recurrence_v1"
        or ledger_value.get("route") != "blackwing_descent_10n_magmaw_diagnostic"
        or not isinstance(bank, dict)
        or bank.get("schema") != "trinity_raid_regression_bank_v1"
        or bank.get("route") != "blackwing_descent_10n_magmaw_diagnostic"
        or not isinstance(fixtures, list)
        or len(matching) != 1
        or matching[0] != expected_fixture
        or not isinstance(history, list)
        or PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID not in history
    ):
        raise DialectError("profile_combat_range_ledger_manifest_mismatch")
    if not isinstance(decision_value, dict):
        raise DialectError("profile_combat_range_ledger_decision_mismatch")
    try:
        profile_combat_range_checkpoint_contract(
            decision_value, label="profile_combat_range_checkpoint"
        )
    except RecurrenceAdmissionError as error:
        raise DialectError(
            "profile_combat_range_ledger_decision_mismatch"
        ) from error
    if (
        decision_value.get("fixture_expansion_admitted") is not True
        or decision_value.get("build_admitted") is not False
        or decision_value.get("canary_admitted") is not False
    ):
        raise DialectError("profile_combat_range_ledger_decision_mismatch")
    rows = suite_value.get("verifications") if isinstance(suite_value, dict) else None
    expected_manifest_sha256 = _manifest_sha256(bank)
    expected_config_identity = _canonical_config_identity()
    suite_fields = {
        "schema", "manifest_sha256", "source_identity", "config_identity",
        "fixture_ids", "verifications",
    }
    row_fields = {
        "fixture_id", "passed", "returncode", "timed_out", "command_sha256",
        "fixture_revision", "stdout_sha256", "stderr_sha256", "result_sha256",
        "source_identity", "config_identity", "passed_after_run_id",
    }
    if (
        not isinstance(suite_value, dict)
        or set(suite_value) != suite_fields
        or suite_value.get("schema") != "trinity_raid_regression_suite_receipt_v1"
        or suite_value.get("fixture_ids")
            != [row.get("fixture_id") for row in fixtures]
        or suite_value.get("manifest_sha256") != expected_manifest_sha256
        or suite_value.get("config_identity") != expected_config_identity
        or not isinstance(rows, list)
        or len(rows) != len(fixtures)
    ):
        raise DialectError("profile_combat_range_suite_receipt_mismatch")
    fixture_by_id = {
        row.get("fixture_id"): row for row in fixtures if isinstance(row, dict)
    }
    for row in rows:
        fixture_id = row.get("fixture_id") if isinstance(row, dict) else None
        fixture = fixture_by_id.get(fixture_id)
        revision = (
            fixture.get("revision", 1)
            if isinstance(fixture, dict) else None
        )
        command = fixture.get("command") if isinstance(fixture, dict) else None
        if (
            not isinstance(row, dict)
            or set(row) != row_fields
            or not isinstance(fixture_id, str)
            or not isinstance(revision, int)
            or row.get("fixture_revision") != revision
            or row.get("passed") is not True
            or row.get("returncode") != 0
            or row.get("timed_out") is not False
            or not isinstance(command, list)
            or row.get("command_sha256") != _command_sha256(command)
            or not isinstance(row.get("stdout_sha256"), str)
            or not isinstance(row.get("stderr_sha256"), str)
            or row.get("result_sha256") != _result_sha256(
                row.get("returncode"), row.get("timed_out"),
                row.get("stdout_sha256"), row.get("stderr_sha256"),
            )
            or row.get("source_identity") != suite_value.get("source_identity")
            or row.get("config_identity") != expected_config_identity
            or not isinstance(row.get("passed_after_run_id"), str)
            or not row.get("passed_after_run_id")
        ):
            raise DialectError("profile_combat_range_suite_receipt_mismatch")


def validate_route_rows(dialect: str, rows: list[dict[str, Any]]) -> None:
    """Require the reviewed route shape for the selected checkpoint dialect."""

    if dialect == CHAINWIELDER:
        return
    if dialect == PROFILE_COMBAT_RANGE:
        expected_fields = PROFILE_COMBAT_RANGE_ROUTE_FIELDS
    elif dialect == MAGMAW_TRANSFER:
        expected_fields = MAGMAW_TRANSFER_ROUTE_FIELDS
    else:
        raise DialectError("checkpoint_dialect_invalid")
    if len(rows) != len(expected_fields):
        raise DialectError(
            "profile_combat_range_route_shape_mismatch"
            if dialect == PROFILE_COMBAT_RANGE
            else "magmaw_transfer_route_shape_mismatch"
        )
    for step, (row, expected) in enumerate(
        zip(rows, expected_fields), start=1,
    ):
        node_id, map_id, kind, source_entry = expected
        if (
            row.get("step") != step
            or row.get("route_node_id") != node_id
            or row.get("map_id") != map_id
            or row.get("kind") != kind
            or row.get("source_entry") != source_entry
        ):
            raise DialectError(
                "profile_combat_range_route_semantic_mismatch"
                if dialect == PROFILE_COMBAT_RANGE
                else "magmaw_transfer_route_semantic_mismatch"
            )


def config_values(dialect: str) -> dict[str, str]:
    if dialect == CHAINWIELDER:
        return {
            # The composite replay continues from Chainwielder through Magmaw.
            # Its admitted Magmaw fixtures require the persistent task runner;
            # bind that authority in the same authenticated runtime config.
            "BotWorld.Magmaw.TransferLaneTaskAuthority": "1",
            f"{CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX}.Enable": "1",
            f"{CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX}.FixtureId": (
                f'"{CHAINWIELDER_CHECKPOINT_FIXTURE_ID}"'
            ),
        }
    if dialect == MAGMAW_TRANSFER:
        return {
            "BotWorld.Magmaw.TransferLaneTaskAuthority": "0",
            f"{MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX}.Enable": "1",
            f"{MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX}.FixtureId": (
                f'"{MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID}"'
            ),
            f"{MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX}.CaseId": (
                f'"{MAGMAW_TRANSFER_CHECKPOINT_CASE_ID}"'
            ),
        }
    if dialect == PROFILE_COMBAT_RANGE:
        return {
            "BotWorld.Magmaw.TransferLaneTaskAuthority": "0",
            f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.Enable": "1",
            f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.FixtureId": (
                f'"{PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID}"'
            ),
            f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.CaseId": (
                f'"{PROFILE_COMBAT_RANGE_CHECKPOINT_CASE_ID}"'
            ),
            f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.ActorGuid": (
                str(PROFILE_COMBAT_RANGE_ACTOR_GUID)
            ),
            f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.TargetGuid": (
                str(PROFILE_COMBAT_RANGE_TARGET_GUID)
            ),
        }
    raise DialectError("checkpoint_dialect_invalid")


def sealed_config_values(
    dialect: str, *, seal: dict[str, Any], source_commit: str,
) -> dict[str, str]:
    prefix = (
        CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX
        if dialect == CHAINWIELDER
        else MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX
        if dialect == MAGMAW_TRANSFER
        else PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX
        if dialect == PROFILE_COMBAT_RANGE
        else None
    )
    if prefix is None:
        raise DialectError("checkpoint_dialect_invalid")
    return {
        **config_values(dialect),
        f"{prefix}.SealSha256": f'"{seal["seal_sha256"]}"',
        f"{prefix}.SourceCommit": f'"{source_commit}"',
    }


def create_seal(
    dialect: str, *, worktree: Path, binary: Path, build_receipt: Path,
    decision: Path, profile_manifest: Path,
    runtime_profile_overlay: dict[str, Any], expected_runtime_profile_id: str,
) -> dict[str, str]:
    common = {
        "worktree": worktree,
        "binary": binary,
        "build_receipt": build_receipt,
        "decision": decision,
        "profile_manifest": profile_manifest,
        "runtime_profile_overlay": runtime_profile_overlay,
        "expected_runtime_profile_id": expected_runtime_profile_id,
    }
    if dialect == CHAINWIELDER:
        return chainwielder_checkpoint_seal(**common)
    if dialect == MAGMAW_TRANSFER:
        return magmaw_transfer_checkpoint_seal(
            **common, case_id=MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
        )
    if dialect == PROFILE_COMBAT_RANGE:
        return profile_combat_range_checkpoint_seal(
            **common, case_id=PROFILE_COMBAT_RANGE_CHECKPOINT_CASE_ID,
            actor_guid=PROFILE_COMBAT_RANGE_ACTOR_GUID,
            target_guid=PROFILE_COMBAT_RANGE_TARGET_GUID,
        )
    raise DialectError("checkpoint_dialect_invalid")


def identity(dialect: str, *, scenario_id: str) -> dict[str, Any]:
    if dialect == CHAINWIELDER:
        return {
            "scenario_id": scenario_id,
            "runtime_profile_id": scenario_id,
            "pool_tag": scenario_id,
            "actor_guid": CHAINWIELDER_ACTOR_GUID,
            "checkpoint_fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
            "task_authority_enabled": True,
        }
    if dialect == MAGMAW_TRANSFER:
        return {
            "scenario_id": scenario_id,
            "runtime_profile_id": scenario_id,
            "pool_tag": scenario_id,
            "actor_guid": MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
            "map_id": 669,
            "checkpoint_fixture_id": MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
            "checkpoint_case_id": MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
            "task_authority_enabled": False,
        }
    if dialect == PROFILE_COMBAT_RANGE:
        return {
            "scenario_id": scenario_id,
            "runtime_profile_id": scenario_id,
            "pool_tag": scenario_id,
            "actor_guid": PROFILE_COMBAT_RANGE_ACTOR_GUID,
            "target_guid": PROFILE_COMBAT_RANGE_TARGET_GUID,
            "target_entry": PROFILE_COMBAT_RANGE_TARGET_ENTRY,
            "map_id": 669,
            "checkpoint_fixture_id": PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
            "checkpoint_case_id": PROFILE_COMBAT_RANGE_CHECKPOINT_CASE_ID,
            "task_authority_enabled": False,
        }
    raise DialectError("checkpoint_dialect_invalid")


def dialect_from_identity(value: object, *, scenario_id: str) -> str:
    for dialect in (CHAINWIELDER, MAGMAW_TRANSFER, PROFILE_COMBAT_RANGE):
        if value == identity(dialect, scenario_id=scenario_id):
            return dialect
    raise DialectError("launch_identity_mismatch")


def capture_option(dialect: str) -> tuple[str, ...]:
    if dialect == CHAINWIELDER:
        return "--chainwielder-checkpoint-actor-guid", str(CHAINWIELDER_ACTOR_GUID)
    if dialect == MAGMAW_TRANSFER:
        return (
            "--magmaw-transfer-checkpoint-actor-guid",
            str(MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID),
        )
    if dialect == PROFILE_COMBAT_RANGE:
        return (
            "--profile-combat-range-checkpoint-actor-guid",
            str(PROFILE_COMBAT_RANGE_ACTOR_GUID),
            "--profile-combat-range-checkpoint-target-guid",
            str(PROFILE_COMBAT_RANGE_TARGET_GUID),
        )
    raise DialectError("checkpoint_dialect_invalid")


def lifecycle_predicates(dialect: str, *, actor_guid: int) -> dict[str, Any]:
    if dialect == CHAINWIELDER:
        return {
            "stage": "completed", "terminal": True, "injection_count": 1,
            "actor_guid": actor_guid,
            "authority": "chainwielder_fixture_observation_only_not_gameplay",
            "trigger": "active_route_path",
            "triggered_by_active_route_path": True,
            "triggered_by_armed_route_hazard_retry": False,
            "rejection_owner": "hazard",
            "rejection_gate": "future_pack_destination",
            "rejection_reason": "route_destination_future_pack_unsafe",
            "planner_receipt_id": 0,
            "before_after_identity_preserved": True,
            "outcome": "route_identity_preserved_after_receiptless_hazard_rejection",
        }
    if dialect == MAGMAW_TRANSFER:
        return {
            "stage": "completed",
            "terminal": True,
            "actor_guid": actor_guid,
            "map_id": 669,
            "fixture_id": MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
            "case_id": MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
            "authority": MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY,
            "task_authority_enabled": False,
            "certifies_gameplay_success": False,
            "certifies_boss_fidelity": False,
        }
    if dialect == PROFILE_COMBAT_RANGE:
        return {
            "stage": "completed",
            "terminal": True,
            "actor_guid": actor_guid,
            "target_guid": PROFILE_COMBAT_RANGE_TARGET_GUID,
            "map_id": 669,
            "fixture_id": PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
            "case_id": PROFILE_COMBAT_RANGE_CHECKPOINT_CASE_ID,
            "authority": PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
            "task_authority_enabled": False,
            "certifies_gameplay_success": False,
            "certifies_boss_fidelity": False,
        }
    raise DialectError("checkpoint_dialect_invalid")
