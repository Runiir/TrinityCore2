"""The two explicitly admitted checkpoint dialects for the atomic bundle."""

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
    chainwielder_checkpoint_seal,
    magmaw_transfer_checkpoint_seal,
)


CHAINWIELDER = "chainwielder"
MAGMAW_TRANSFER = "magmaw_transfer"
CHAINWIELDER_ACTOR_GUID = 30008
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


class DialectError(RuntimeError):
    pass


def select_dialect(
    *, actor_guid: int, checkpoint_fixture_id: str,
    checkpoint_case_id: str | None,
) -> str:
    """Accept only one of the two fully enumerated checkpoint tuples."""

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
    # Keep the established public failure reason for existing callers.
    raise DialectError("chainwielder_identity_input_mismatch")


def route_node_ids(dialect: str) -> tuple[str, ...]:
    if dialect == CHAINWIELDER:
        return CHAINWIELDER_ROUTE_NODE_IDS
    if dialect == MAGMAW_TRANSFER:
        return MAGMAW_TRANSFER_ROUTE_NODE_IDS
    raise DialectError("checkpoint_dialect_invalid")


def initial_node_id(dialect: str) -> str:
    return route_node_ids(dialect)[0]


def ledger_relative_path(dialect: str) -> Path:
    if dialect == CHAINWIELDER:
        return CHAINWIELDER_LEDGER_RELATIVE_PATH
    if dialect == MAGMAW_TRANSFER:
        return MAGMAW_TRANSFER_LEDGER_RELATIVE_PATH
    raise DialectError("checkpoint_dialect_invalid")


def validate_ledger_manifest(
    dialect: str, *, ledger: Path, decision: Path, suite_receipt: Path,
) -> None:
    """Validate the dedicated transfer registration, not arbitrary fixtures."""

    if dialect == CHAINWIELDER:
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


def validate_route_rows(dialect: str, rows: list[dict[str, Any]]) -> None:
    """Require the one reviewed full-route shape for the transfer dialect."""

    if dialect == CHAINWIELDER:
        return
    if dialect != MAGMAW_TRANSFER:
        raise DialectError("checkpoint_dialect_invalid")
    if len(rows) != len(MAGMAW_TRANSFER_ROUTE_FIELDS):
        raise DialectError("magmaw_transfer_route_shape_mismatch")
    for step, (row, expected) in enumerate(
        zip(rows, MAGMAW_TRANSFER_ROUTE_FIELDS), start=1,
    ):
        node_id, map_id, kind, source_entry = expected
        if (
            row.get("step") != step
            or row.get("route_node_id") != node_id
            or row.get("map_id") != map_id
            or row.get("kind") != kind
            or row.get("source_entry") != source_entry
        ):
            raise DialectError("magmaw_transfer_route_semantic_mismatch")


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
    raise DialectError("checkpoint_dialect_invalid")


def sealed_config_values(
    dialect: str, *, seal: dict[str, Any], source_commit: str,
) -> dict[str, str]:
    prefix = (
        CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX
        if dialect == CHAINWIELDER
        else MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX
        if dialect == MAGMAW_TRANSFER
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
    raise DialectError("checkpoint_dialect_invalid")


def dialect_from_identity(value: object, *, scenario_id: str) -> str:
    for dialect in (CHAINWIELDER, MAGMAW_TRANSFER):
        if value == identity(dialect, scenario_id=scenario_id):
            return dialect
    raise DialectError("launch_identity_mismatch")


def capture_option(dialect: str) -> tuple[str, str]:
    if dialect == CHAINWIELDER:
        return "--chainwielder-checkpoint-actor-guid", str(CHAINWIELDER_ACTOR_GUID)
    if dialect == MAGMAW_TRANSFER:
        return (
            "--magmaw-transfer-checkpoint-actor-guid",
            str(MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID),
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
    raise DialectError("checkpoint_dialect_invalid")
