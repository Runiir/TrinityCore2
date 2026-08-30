"""Materialize one authenticated runtime route manifest from a route catalog."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from tools.bot_ml.run_live_bot_validation import (
    validation_route_manifest_payload,
)
from tools.raid_program.canonical_route_staging import (
    CanonicalRouteStagingError,
    atomic_write_new,
    verify_staging_receipt,
    verify_staging_receipt_snapshot,
)


CATALOG_RECEIPT_SCHEMA = "cata_raid_scenario_route_manifest_receipt_v1"
MANIFEST_SCHEMA = "bot_live_validation_route_manifest_v1"
ALLOWED_ROUTE_KINDS = {"trash", "boss", "travel", "regroup", "descent"}
SHA256_RE = re.compile(r"[0-9a-f]{64}")
SAFE_SCENARIO_RE = re.compile(r"[A-Za-z0-9_.-]+")
CATALOG_RECEIPT_FIELDS = {
    "schema",
    "source_commit",
    "dvc_stage_name",
    "output_relative_member",
    "staging_receipt_locator",
    "staging_receipt_snapshot_base64",
    "staging_receipt_sha256",
    "source_catalog_path",
    "source_catalog_sha256",
    "staged_catalog_path",
    "staged_catalog_sha256",
    "catalog_row_count",
    "selected_scenario_id",
    "selected_row_count",
    "selected_row_order",
    "selected_rows_sha256",
    "output_object_path",
    "output_object_sha256",
}


class CanonicalRouteCatalogError(RuntimeError):
    pass


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _outside_worktree(path: Path, worktree: Path, reason: str) -> Path:
    lexical = Path(os.path.abspath(path))
    resolved = path.resolve()
    try:
        resolved.relative_to(worktree)
    except ValueError:
        pass
    else:
        raise CanonicalRouteCatalogError(reason)
    if lexical != resolved or path.is_symlink():
        raise CanonicalRouteCatalogError(reason)
    return resolved


def _diagnostic_locator(value: object, worktree: Path) -> str:
    if not isinstance(value, str) or not value:
        raise CanonicalRouteCatalogError("staging_receipt_locator_invalid")
    path = Path(value)
    lexical = Path(os.path.abspath(path))
    if path != lexical:
        raise CanonicalRouteCatalogError("staging_receipt_locator_invalid")
    try:
        lexical.relative_to(worktree)
    except ValueError:
        return str(lexical)
    raise CanonicalRouteCatalogError("staging_receipt_locator_invalid")


def _verified_staging(
    *, worktree: Path, staging_receipt_path: Path,
    expected_staging_receipt_sha256: str, dvc_stage_name: str,
    output_relative_member: str,
    staging_receipt_snapshot_base64: str | None = None,
) -> dict[str, Any]:
    try:
        if staging_receipt_snapshot_base64 is not None:
            return verify_staging_receipt_snapshot(
                worktree=worktree,
                receipt_snapshot_base64=staging_receipt_snapshot_base64,
                expected_receipt_sha256=expected_staging_receipt_sha256,
                dvc_stage_name=dvc_stage_name,
                output_relative_member=output_relative_member,
            )
        return verify_staging_receipt(
            worktree=worktree,
            receipt_path=staging_receipt_path,
            expected_receipt_sha256=expected_staging_receipt_sha256,
            dvc_stage_name=dvc_stage_name,
            output_relative_member=output_relative_member,
        )
    except CanonicalRouteStagingError as error:
        raise CanonicalRouteCatalogError(str(error)) from error


def _parse_catalog(
    catalog_bytes: bytes, selected_scenario_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        lines = catalog_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise CanonicalRouteCatalogError("route_catalog_utf8_invalid") from error

    all_rows: list[dict[str, Any]] = []
    selected: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise CanonicalRouteCatalogError(
                f"route_catalog_jsonl_invalid:{line_number}"
            ) from error
        if not isinstance(row, dict):
            raise CanonicalRouteCatalogError(
                f"route_catalog_row_invalid:{line_number}"
            )
        all_rows.append(row)
        if (
            str(row.get("scenario_id") or "") == selected_scenario_id
            and str(row.get("kind") or "") in ALLOWED_ROUTE_KINDS
            and bool(row.get("coordinates_valid", True))
        ):
            selected.append((line_number, row))

    if not selected:
        raise CanonicalRouteCatalogError("route_catalog_scenario_missing")

    sortable: list[tuple[int, int, dict[str, Any]]] = []
    steps: set[int] = set()
    node_ids: set[str] = set()
    for line_number, row in selected:
        try:
            step = int(row.get("step") or 0)
        except (TypeError, ValueError) as error:
            raise CanonicalRouteCatalogError(
                f"route_catalog_step_invalid:{line_number}"
            ) from error
        node_id = str(row.get("route_node_id") or "")
        if step <= 0 or step in steps or not node_id or node_id in node_ids:
            raise CanonicalRouteCatalogError("route_catalog_scenario_ambiguous")
        steps.add(step)
        node_ids.add(node_id)
        sortable.append((step, line_number, row))

    sortable.sort(key=lambda item: item[0])
    routes: list[dict[str, Any]] = []
    identities: list[dict[str, Any]] = []
    for generation, (step, line_number, original) in enumerate(sortable, 1):
        row = copy.deepcopy(original)
        row["route_generation"] = generation
        routes.append(row)
        identities.append({
            "line_number": line_number,
            "step": step,
            "route_node_id": str(original["route_node_id"]),
            "row_sha256": _sha256_bytes(_canonical_json_bytes(original)),
        })
    return all_rows, routes, identities


def _derive(
    *, worktree: Path, staging_receipt_path: Path,
    expected_staging_receipt_sha256: str, selected_scenario_id: str,
    dvc_stage_name: str, output_relative_member: str,
    staging_receipt_snapshot_base64: str | None = None,
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    if not SAFE_SCENARIO_RE.fullmatch(selected_scenario_id):
        raise CanonicalRouteCatalogError("selected_scenario_id_invalid")
    staging = _verified_staging(
        worktree=worktree,
        staging_receipt_path=staging_receipt_path,
        expected_staging_receipt_sha256=expected_staging_receipt_sha256,
        dvc_stage_name=dvc_stage_name,
        output_relative_member=output_relative_member,
        staging_receipt_snapshot_base64=staging_receipt_snapshot_base64,
    )
    catalog_path = Path(staging["staged_path"])
    before = catalog_path.read_bytes()
    catalog_sha = _sha256_bytes(before)
    if catalog_sha != staging["staged_sha256"]:
        raise CanonicalRouteCatalogError("staged_catalog_hash_mismatch")
    all_rows, routes, identities = _parse_catalog(before, selected_scenario_id)
    manifest = validation_route_manifest_payload(selected_scenario_id, routes)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise CanonicalRouteCatalogError("runtime_manifest_schema_mismatch")
    manifest_bytes = _canonical_json_bytes(manifest)
    if catalog_path.read_bytes() != before:
        raise CanonicalRouteCatalogError("staged_catalog_mutated_during_selection")
    derived = {
        "catalog_row_count": len(all_rows),
        "selected_row_count": len(routes),
        "selected_row_order": identities,
        "selected_rows_sha256": _sha256_bytes(_canonical_json_bytes(identities)),
    }
    return staging, manifest_bytes, derived


def materialize_scenario_route_manifest(
    *, worktree: Path, staging_receipt_path: Path,
    expected_staging_receipt_sha256: str, selected_scenario_id: str,
    external_run_root: Path, dvc_stage_name: str = "validation_scenarios",
    output_relative_member: str = "validation_routes.jsonl",
) -> dict[str, Any]:
    worktree = worktree.resolve()
    root = _outside_worktree(
        external_run_root, worktree, "route_manifest_output_root_invalid"
    )
    if not root.is_dir():
        raise CanonicalRouteCatalogError("route_manifest_output_root_invalid")
    staging, manifest_bytes, derived = _derive(
        worktree=worktree,
        staging_receipt_path=staging_receipt_path,
        expected_staging_receipt_sha256=expected_staging_receipt_sha256,
        selected_scenario_id=selected_scenario_id,
        dvc_stage_name=dvc_stage_name,
        output_relative_member=output_relative_member,
    )
    suffix = f"{selected_scenario_id}-{staging['staged_sha256'][:16]}"
    output_path = root / f"{suffix}.route.json"
    receipt_path = root / f"{suffix}.route.receipt.json"
    if output_path.exists() or output_path.is_symlink():
        raise CanonicalRouteCatalogError("route_manifest_output_collision")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise CanonicalRouteCatalogError("route_manifest_receipt_collision")
    try:
        atomic_write_new(output_path, manifest_bytes)
    except CanonicalRouteStagingError as error:
        raise CanonicalRouteCatalogError("route_manifest_output_collision") from error

    receipt = {
        "schema": CATALOG_RECEIPT_SCHEMA,
        "source_commit": staging["source_commit"],
        "dvc_stage_name": dvc_stage_name,
        "output_relative_member": output_relative_member,
        "staging_receipt_locator": staging["receipt_locator"],
        "staging_receipt_snapshot_base64": staging[
            "receipt_snapshot_base64"
        ],
        "staging_receipt_sha256": staging["receipt_sha256"],
        "source_catalog_path": staging["source_path"],
        "source_catalog_sha256": staging["source_sha256"],
        "staged_catalog_path": staging["staged_path"],
        "staged_catalog_sha256": staging["staged_sha256"],
        **derived,
        "selected_scenario_id": selected_scenario_id,
        "output_object_path": str(output_path),
        "output_object_sha256": _sha256_bytes(manifest_bytes),
    }
    receipt_bytes = _canonical_json_bytes(receipt)
    try:
        atomic_write_new(receipt_path, receipt_bytes)
    except CanonicalRouteStagingError as error:
        output_path.unlink(missing_ok=True)
        raise CanonicalRouteCatalogError("route_manifest_receipt_collision") from error
    return {
        **receipt,
        "receipt_path": str(receipt_path),
        "receipt_sha256": _sha256_bytes(receipt_bytes),
    }


def verify_scenario_route_manifest_receipt(
    *, worktree: Path, receipt_path: Path, expected_receipt_sha256: str,
    expected_staging_receipt_sha256: str, selected_scenario_id: str,
    dvc_stage_name: str = "validation_scenarios",
    output_relative_member: str = "validation_routes.jsonl",
) -> dict[str, Any]:
    worktree = worktree.resolve()
    receipt_path = _outside_worktree(
        receipt_path, worktree, "route_manifest_receipt_location_invalid"
    )
    if not receipt_path.is_file() or not SHA256_RE.fullmatch(
        expected_receipt_sha256
    ):
        raise CanonicalRouteCatalogError("route_manifest_receipt_invalid")
    receipt_bytes = receipt_path.read_bytes()
    if _sha256_bytes(receipt_bytes) != expected_receipt_sha256:
        raise CanonicalRouteCatalogError("route_manifest_receipt_hash_mismatch")
    try:
        receipt = json.loads(receipt_bytes)
    except json.JSONDecodeError as error:
        raise CanonicalRouteCatalogError("route_manifest_receipt_invalid") from error
    if (
        not isinstance(receipt, dict)
        or set(receipt) != CATALOG_RECEIPT_FIELDS
        or receipt.get("schema") != CATALOG_RECEIPT_SCHEMA
        or receipt_bytes != _canonical_json_bytes(receipt)
    ):
        raise CanonicalRouteCatalogError("route_manifest_receipt_invalid")
    staging_receipt_locator = _diagnostic_locator(
        receipt.get("staging_receipt_locator"), worktree
    )

    staging, manifest_bytes, derived = _derive(
        worktree=worktree,
        staging_receipt_path=Path(),
        expected_staging_receipt_sha256=expected_staging_receipt_sha256,
        selected_scenario_id=selected_scenario_id,
        dvc_stage_name=dvc_stage_name,
        output_relative_member=output_relative_member,
        staging_receipt_snapshot_base64=str(
            receipt.get("staging_receipt_snapshot_base64") or ""
        ),
    )
    output_path = _outside_worktree(
        Path(str(receipt.get("output_object_path") or "")),
        worktree,
        "route_manifest_output_location_invalid",
    )
    expected = {
        "schema": CATALOG_RECEIPT_SCHEMA,
        "source_commit": staging["source_commit"],
        "dvc_stage_name": dvc_stage_name,
        "output_relative_member": output_relative_member,
        "staging_receipt_locator": staging_receipt_locator,
        "staging_receipt_snapshot_base64": staging[
            "receipt_snapshot_base64"
        ],
        "staging_receipt_sha256": staging["receipt_sha256"],
        "source_catalog_path": staging["source_path"],
        "source_catalog_sha256": staging["source_sha256"],
        "staged_catalog_path": staging["staged_path"],
        "staged_catalog_sha256": staging["staged_sha256"],
        **derived,
        "selected_scenario_id": selected_scenario_id,
        "output_object_path": str(output_path),
        "output_object_sha256": _sha256_bytes(manifest_bytes),
    }
    if receipt != expected:
        raise CanonicalRouteCatalogError("route_manifest_receipt_mismatch")
    if not output_path.is_file() or output_path.read_bytes() != manifest_bytes:
        raise CanonicalRouteCatalogError("route_manifest_output_mismatch")
    return {
        **receipt,
        "receipt_path": str(receipt_path),
        "receipt_sha256": expected_receipt_sha256,
    }
