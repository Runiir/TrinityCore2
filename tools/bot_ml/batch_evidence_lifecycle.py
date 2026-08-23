from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

try:
    from .live_validation_session import (
        canonical_sha256,
        dvc_repository_lock,
        sha256_file,
        verify_report_acceptance,
    )
    from .raw_evidence_binding import (
        RawEvidenceBindingError,
        build_transport_receipt,
        calibration_reference_thresholds,
        parse_json_objects as parse_raw_json_objects,
        projection_from_raw,
        projection_from_report,
        semantic_binding,
        validate_transport_receipt,
    )
except ImportError:
    from live_validation_session import (
        canonical_sha256,
        dvc_repository_lock,
        sha256_file,
        verify_report_acceptance,
    )
    from raw_evidence_binding import (
        RawEvidenceBindingError,
        build_transport_receipt,
        calibration_reference_thresholds,
        parse_json_objects as parse_raw_json_objects,
        projection_from_raw,
        projection_from_report,
        semantic_binding,
        validate_transport_receipt,
    )


CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]
DEFAULT_MAX_PENDING_RAW_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_RAW_PARTS = 16


class BatchLifecycleError(RuntimeError):
    pass


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _checked(
    command: Sequence[str],
    cwd: Path,
    *,
    runner: CommandRunner,
    description: str,
) -> subprocess.CompletedProcess[str]:
    completed = runner(command, cwd)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise BatchLifecycleError(f"{description} failed{': ' + detail if detail else ''}")
    return completed


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _encoded_jsonl(row: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(row), sort_keys=True, default=str) + "\n").encode("utf-8")


def _write_zstd_jsonl(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    max_uncompressed_bytes: int = DEFAULT_MAX_PENDING_RAW_BYTES,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with pa.output_stream(path) as sink:
            with pa.CompressedOutputStream(sink, "zstd") as compressed:
                for row in rows:
                    encoded = _encoded_jsonl(row)
                    if written + len(encoded) > max_uncompressed_bytes:
                        raise BatchLifecycleError(
                            f"raw capture exceeds {max_uncompressed_bytes} pending bytes"
                        )
                    compressed.write(encoded)
                    written += len(encoded)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return len(rows)


def _write_zstd_jsonl_parts(
    folder: Path,
    stem: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    max_uncompressed_bytes: int = DEFAULT_MAX_PENDING_RAW_BYTES,
    max_parts: int = DEFAULT_MAX_RAW_PARTS,
) -> dict[str, int]:
    """Write bounded Zstandard parts without imposing one-file limits on a batch."""
    if max_uncompressed_bytes <= 0 or max_parts <= 0:
        raise BatchLifecycleError("raw part limits must be positive")

    folder.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    pending: list[Mapping[str, Any]] = []
    pending_bytes = 0
    total_bytes = 0
    row_count = 0

    def flush() -> None:
        nonlocal pending, pending_bytes
        if len(parts) >= max_parts:
            raise BatchLifecycleError(f"raw capture exceeds {max_parts} bounded parts")
        suffix = "" if not parts else f"-{len(parts):05d}"
        path = folder / f"{stem}{suffix}.jsonl.zst"
        _write_zstd_jsonl(
            path,
            pending,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        parts.append(path)
        pending = []
        pending_bytes = 0

    try:
        for row in rows:
            encoded_size = len(_encoded_jsonl(row))
            if encoded_size > max_uncompressed_bytes:
                raise BatchLifecycleError(
                    f"single raw row exceeds {max_uncompressed_bytes} pending bytes"
                )
            if pending and pending_bytes + encoded_size > max_uncompressed_bytes:
                flush()
            pending.append(row)
            pending_bytes += encoded_size
            total_bytes += encoded_size
            row_count += 1
        if pending or not parts:
            flush()
    except Exception:
        for path in parts:
            path.unlink(missing_ok=True)
        raise

    return {
        "row_count": row_count,
        "part_count": len(parts),
        "uncompressed_bytes": total_bytes,
    }


def _read_zstd_jsonl(path: Path) -> list[dict[str, Any]]:
    with pa.input_stream(path) as source:
        with pa.CompressedInputStream(source, "zstd") as compressed:
            payload = compressed.read().decode("utf-8")
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _write_zstd_bytes(
    path: Path, payload: bytes, *, max_uncompressed_bytes: int
) -> None:
    if len(payload) > max_uncompressed_bytes:
        raise BatchLifecycleError(
            f"raw transport exceeds {max_uncompressed_bytes} pending bytes"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pa.output_stream(path) as sink:
            with pa.CompressedOutputStream(sink, "zstd") as compressed:
                compressed.write(payload)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _read_zstd_bytes(path: Path) -> bytes:
    with pa.input_stream(path) as source:
        with pa.CompressedInputStream(source, "zstd") as compressed:
            return compressed.read()


def _jsonl_part_paths(folder: Path, stem: str) -> list[Path]:
    primary = folder / f"{stem}.jsonl.zst"
    paths = [primary] if primary.is_file() else []
    paths.extend(sorted(folder.glob(f"{stem}-*.jsonl.zst")))
    return paths


def _write_parquet(path: Path, rows: Sequence[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([dict(row) for row in rows])
    pq.write_table(table, path, compression="zstd")
    return table.num_rows


def _tree_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _tree_manifest(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path.relative_to(root)),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        for path in _tree_files(root)
    ]


def _manifest_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256([dict(row) for row in rows])


def _calibration_scoring_contract(report: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze only the external reference input needed to score raw DPS."""
    record = report.get("role_calibration_record")
    record = record if isinstance(record, Mapping) else {}
    evaluation = report.get("role_calibration_evaluation")
    evaluation = evaluation if isinstance(evaluation, Mapping) else {}
    metrics = record.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    identity = record.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    compatibility = record.get("reference_condition_compatibility")
    compatibility = compatibility if isinstance(compatibility, Mapping) else {}
    runtime_reference_facts = compatibility.get("runtime_reference_facts")
    runtime_reference_facts = (
        runtime_reference_facts
        if isinstance(runtime_reference_facts, Mapping)
        else {}
    )
    record_sha256 = canonical_sha256(record) if record else ""
    reported_record_sha256 = str(evaluation.get("record_sha256") or "")
    if record and reported_record_sha256 != record_sha256:
        raise BatchLifecycleError(
            "role calibration record hash does not match its evaluation"
        )
    try:
        reference_value = float(metrics.get("reference_value") or 0.0)
    except (TypeError, ValueError) as exc:
        raise BatchLifecycleError("invalid calibration reference value") from exc
    if record and reference_value <= 0:
        raise BatchLifecycleError("calibration record has no positive reference value")
    policy_sha256 = str(evaluation.get("policy_sha256") or "")
    if record and not re.fullmatch(r"[0-9a-f]{64}", policy_sha256):
        raise BatchLifecycleError("calibration evaluation has no exact policy hash")
    hard_reference_ratio, optimization_reference_ratio, _, _ = (
        calibration_reference_thresholds(policy_sha256 if record else None)
    )
    return {
        "schema": "bot_calibration_scoring_contract_v1",
        "reference_value": reference_value,
        "reference_basis": str(metrics.get("reference_basis") or ""),
        "reference_id": str(identity.get("reference_id") or ""),
        "hard_reference_ratio": hard_reference_ratio,
        "optimization_reference_ratio": optimization_reference_ratio,
        "record_sha256": record_sha256,
        "policy_sha256": policy_sha256,
        "reference_condition_contract": {
            "reference_conditions": compatibility.get("reference_conditions") or {},
            "expected_manifest": compatibility.get("expected_manifest") or {},
            "gear_source_sha256": runtime_reference_facts.get(
                "gear_source_sha256"
            ),
            "reference_gear_manifest_sha256": runtime_reference_facts.get(
                "reference_gear_manifest_sha256"
            ),
            "gear_transform_schema": runtime_reference_facts.get(
                "gear_transform_schema"
            ),
            "gear_transform_authority": runtime_reference_facts.get(
                "gear_transform_authority"
            ),
            "reference_result_key": runtime_reference_facts.get(
                "reference_result_key"
            ),
            "reference_value": runtime_reference_facts.get("reference_value"),
            "source_contract_sha256": runtime_reference_facts.get(
                "source_contract_sha256"
            ),
            "request_sha256": runtime_reference_facts.get("request_sha256"),
            "fixture_contract_sha256": runtime_reference_facts.get(
                "fixture_contract_sha256"
            ),
            "fixture_contract_binding_valid": runtime_reference_facts.get(
                "fixture_contract_binding_valid"
            ),
            "result_status": runtime_reference_facts.get("result_status"),
            "reference_request_binding_valid": runtime_reference_facts.get(
                "reference_request_binding_valid"
            ),
            "reference_request_catalog_sha256": runtime_reference_facts.get(
                "reference_request_catalog_sha256"
            ),
        },
    }


def _raw_event_envelope_identity(
    raw_rows: Sequence[Mapping[str, Any]], *, batch_id: str
) -> dict[str, Any]:
    cohort_ids = {
        str(row.get("cohort_id") or "")
        for row in raw_rows
        if isinstance(row, Mapping)
    }
    attempt_indices = {
        row.get("attempt_index")
        for row in raw_rows
        if isinstance(row, Mapping)
    }
    if (
        cohort_ids == {""}
        or len(cohort_ids) != 1
        or len(attempt_indices) != 1
    ):
        raise BatchLifecycleError(
            "raw event envelopes do not have one cohort/attempt identity"
        )
    attempt_index = next(iter(attempt_indices))
    if (
        isinstance(attempt_index, bool)
        or not isinstance(attempt_index, int)
        or attempt_index <= 0
    ):
        raise BatchLifecycleError("raw event envelope attempt index is invalid")
    return {
        "schema": "bot_raw_event_envelope_identity_v1",
        "batch_id": batch_id,
        "cohort_id": next(iter(cohort_ids)),
        "attempt_index": attempt_index,
        "row_count": len(raw_rows),
    }


def capture_batch(
    batch_root: Path,
    *,
    batch_id: str,
    raw_rows: Sequence[Mapping[str, Any]],
    compact_rows: Sequence[Mapping[str, Any]],
    exact_manifests: Mapping[str, Any],
    summary: Mapping[str, Any],
    acceptance_report: Mapping[str, Any],
    database_rows: Sequence[Mapping[str, Any]] | None = None,
    measurement_window_ids: Sequence[str] = (),
    max_pending_raw_bytes: int = DEFAULT_MAX_PENDING_RAW_BYTES,
    max_raw_parts: int = DEFAULT_MAX_RAW_PARTS,
    raw_transport_output: str | None = None,
    transport_outcome: Mapping[str, Any] | None = None,
    semantic_evidence_kind: str | None = None,
) -> dict[str, Any]:
    """Capture one bounded raw stream and one compact analytical representation."""
    if not batch_id.strip():
        raise BatchLifecycleError("batch_id is required")
    semantic_contract: dict[str, Any] | None = None
    transport_receipt: dict[str, Any] | None = None
    raw_projection: dict[str, Any] | None = None
    materialized_compact_rows = [dict(row) for row in compact_rows]
    materialized_exact_manifests = dict(exact_manifests)
    requested_semantic_binding = any(
        value is not None
        for value in (raw_transport_output, transport_outcome, semantic_evidence_kind)
    )
    if requested_semantic_binding:
        if (
            raw_transport_output is None
            or not isinstance(transport_outcome, Mapping)
            or not semantic_evidence_kind
        ):
            raise BatchLifecycleError(
                "raw semantic binding requires output, transport outcome, and evidence kind"
            )
        if len(raw_transport_output.encode("utf-8")) > max_pending_raw_bytes:
            raise BatchLifecycleError(
                f"raw transport exceeds {max_pending_raw_bytes} pending bytes"
            )
        try:
            transport_receipt = build_transport_receipt(
                raw_transport_output,
                returncode=transport_outcome.get("returncode"),
                timed_out=transport_outcome.get("timed_out"),
            )
        except RawEvidenceBindingError as exc:
            raise BatchLifecycleError(str(exc)) from exc
        parsed_payloads = parse_raw_json_objects(raw_transport_output)
        retained_payloads: list[dict[str, Any]] = []
        for sequence, row in enumerate(raw_rows):
            retained_sequence = row.get("sequence")
            if (
                row.get("batch_id") != batch_id
                or isinstance(retained_sequence, bool)
                or not isinstance(retained_sequence, int)
                or retained_sequence != sequence
                or not isinstance(row.get("payload"), Mapping)
            ):
                raise BatchLifecycleError(
                    "raw event envelopes do not match the batch sequence contract"
                )
            retained_payloads.append(dict(row["payload"]))
        if retained_payloads != parsed_payloads:
            raise BatchLifecycleError(
                "parsed raw event envelopes do not match retained console bytes"
            )
        materialized_exact_manifests["raw_event_envelope_identity"] = (
            _raw_event_envelope_identity(raw_rows, batch_id=batch_id)
        )
        if semantic_evidence_kind == "dps_calibration":
            materialized_exact_manifests["calibration_scoring_contract"] = (
                _calibration_scoring_contract(acceptance_report)
            )
        try:
            raw_projection = projection_from_raw(
                evidence_kind=semantic_evidence_kind,
                payloads=parsed_payloads,
                transport_receipt=transport_receipt,
                exact_manifests=materialized_exact_manifests,
            )
            report_projection = projection_from_report(
                acceptance_report, evidence_kind=semantic_evidence_kind
            )
            semantic_contract = semantic_binding(raw_projection, report_projection)
        except RawEvidenceBindingError as exc:
            raise BatchLifecycleError(f"raw semantic binding failed: {exc}") from exc
        if len(materialized_compact_rows) != 1:
            raise BatchLifecycleError(
                "raw semantic binding requires exactly one compact projection row"
            )
        materialized_compact_rows[0].update(
            {
                "semantic_evidence_kind": semantic_contract["evidence_kind"],
                "semantic_decisive_projection_sha256": semantic_contract[
                    "decisive_projection_sha256"
                ],
                "semantic_raw_projection_sha256": semantic_contract[
                    "raw_projection_sha256"
                ],
                "semantic_transport_returncode": transport_receipt["returncode"],
                "semantic_transport_timed_out": transport_receipt["timed_out"],
            }
        )
    raw_dir = batch_root / "raw"
    compact_dir = batch_root / "compact"
    retained_dir = batch_root / "retained"
    if raw_dir.exists() or compact_dir.exists():
        raise BatchLifecycleError("immutable batch paths already exist")
    # The exact console bytes are the primary record. Persist them before any
    # parsed/normalized representation so an interrupted capture cannot leave
    # only a derived view of what the server emitted.
    if raw_transport_output is not None and transport_receipt is not None:
        _write_zstd_bytes(
            raw_dir / "worldserver_output.log.zst",
            raw_transport_output.encode("utf-8"),
            max_uncompressed_bytes=max_pending_raw_bytes,
        )
        _write_json(raw_dir / "transport_receipt.json", transport_receipt)
    raw_capture = _write_zstd_jsonl_parts(
        raw_dir,
        "events",
        raw_rows,
        max_uncompressed_bytes=max_pending_raw_bytes,
        max_parts=max_raw_parts,
    )
    raw_count = raw_capture["row_count"]
    database_export: dict[str, Any] | None = None
    if database_rows is not None:
        window_ids = sorted({str(value) for value in measurement_window_ids if str(value)})
        if not window_ids:
            raise BatchLifecycleError("database export requires measurement_window_ids")
        for row in database_rows:
            if str(row.get("batch_id") or "") != batch_id:
                raise BatchLifecycleError("database export row has an incompatible batch_id")
            if str(row.get("measurement_window_id") or "") not in window_ids:
                raise BatchLifecycleError("database export row has an incompatible measurement_window_id")
        database_row_count = _write_zstd_jsonl(
            raw_dir / "database_rows.jsonl.zst",
            database_rows,
            max_uncompressed_bytes=max_pending_raw_bytes,
        )
        database_export = {
            "batch_id": batch_id,
            "measurement_window_ids": window_ids,
            "row_count": database_row_count,
        }
    if raw_projection is not None:
        _write_json(raw_dir / "decisive_projection.json", raw_projection)
    _write_json(raw_dir / "exact_manifests.json", materialized_exact_manifests)
    _write_json(raw_dir / "acceptance_source_report.json", acceptance_report)
    compact_count = _write_parquet(
        compact_dir / "evidence.parquet", materialized_compact_rows
    )
    acceptance = verify_report_acceptance(acceptance_report)
    _write_json(retained_dir / "summary.json", summary)
    _write_json(retained_dir / "acceptance.json", acceptance)

    raw_files = _tree_manifest(raw_dir)
    compact_files = _tree_manifest(compact_dir)
    manifest = {
        "schema": "bot_immutable_batch_manifest_v1",
        "batch_id": batch_id,
        "state": "closed_unpublished",
        "raw": {
            "format": "chunked_jsonl_zst",
            "row_count": raw_count,
            "part_count": raw_capture["part_count"],
            "uncompressed_bytes": raw_capture["uncompressed_bytes"],
            "files": raw_files,
            "bundle_sha256": _manifest_hash(raw_files),
        },
        "compact": {
            "format": "parquet_zstd",
            "row_count": compact_count,
            "files": compact_files,
            "bundle_sha256": _manifest_hash(compact_files),
        },
        "acceptance": acceptance,
        "database_export": database_export,
        "semantic_binding": semantic_contract,
        "max_pending_raw_bytes": max_pending_raw_bytes,
        "max_raw_parts": max_raw_parts,
        "duplicate_uncompressed_jsonl_retained": False,
    }
    manifest["identity_sha256"] = canonical_sha256(manifest)
    _write_json(retained_dir / "final_manifest.json", manifest)
    return manifest


def validate_capture(batch_root: Path) -> dict[str, Any]:
    manifest_path = batch_root / "retained" / "final_manifest.json"
    if not manifest_path.is_file():
        raise BatchLifecycleError("missing final batch manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest_self_identity(manifest)
    for bundle in ("raw", "compact"):
        root = batch_root / bundle
        expected = manifest.get(bundle) or {}
        actual_files = _tree_manifest(root)
        if actual_files != expected.get("files"):
            raise BatchLifecycleError(f"{bundle} bundle content hash mismatch")
        if _manifest_hash(actual_files) != expected.get("bundle_sha256"):
            raise BatchLifecycleError(f"{bundle} bundle identity mismatch")
    raw_manifest = manifest.get("raw") or {}
    event_parts = _jsonl_part_paths(batch_root / "raw", "events")
    expected_parts = int(raw_manifest.get("part_count") or 1)
    if len(event_parts) != expected_parts:
        raise BatchLifecycleError("raw part count mismatch")
    raw_row_count = sum(len(_read_zstd_jsonl(path)) for path in event_parts)
    if raw_row_count != int(raw_manifest.get("row_count") or 0):
        raise BatchLifecycleError("raw row count mismatch")
    parquet_table = pq.read_table(batch_root / "compact" / "evidence.parquet")
    parquet_rows = parquet_table.num_rows
    if parquet_rows != int((manifest.get("compact") or {}).get("row_count") or 0):
        raise BatchLifecycleError("compact row count mismatch")
    source_report = json.loads(
        (batch_root / "raw" / "acceptance_source_report.json").read_text(encoding="utf-8")
    )
    if verify_report_acceptance(source_report) != manifest.get("acceptance"):
        raise BatchLifecycleError("independent acceptance recomputation mismatch")
    semantic_contract = manifest.get("semantic_binding")
    if semantic_contract is not None:
        if not isinstance(semantic_contract, Mapping):
            raise BatchLifecycleError("malformed raw semantic binding")
        raw_output_path = batch_root / "raw" / "worldserver_output.log.zst"
        transport_path = batch_root / "raw" / "transport_receipt.json"
        projection_path = batch_root / "raw" / "decisive_projection.json"
        if not all(
            path.is_file()
            for path in (raw_output_path, transport_path, projection_path)
        ):
            raise BatchLifecycleError("raw semantic binding artifact is missing")
        try:
            raw_output = _read_zstd_bytes(raw_output_path).decode("utf-8")
            transport_receipt = validate_transport_receipt(
                json.loads(transport_path.read_text(encoding="utf-8")), raw_output
            )
            parsed_payloads = parse_raw_json_objects(raw_output)
            retained_rows = [
                row
                for path in event_parts
                for row in _read_zstd_jsonl(path)
            ]
            retained_payloads: list[dict[str, Any]] = []
            for sequence, row in enumerate(retained_rows):
                retained_sequence = row.get("sequence")
                if (
                    row.get("batch_id") != manifest.get("batch_id")
                    or isinstance(retained_sequence, bool)
                    or not isinstance(retained_sequence, int)
                    or retained_sequence != sequence
                    or not isinstance(row.get("payload"), Mapping)
                ):
                    raise RawEvidenceBindingError(
                        "raw event envelopes do not match the batch sequence contract"
                    )
                retained_payloads.append(dict(row["payload"]))
            if retained_payloads != parsed_payloads:
                raise RawEvidenceBindingError(
                    "parsed raw event envelopes do not match retained console bytes"
                )
            exact_manifests = json.loads(
                (batch_root / "raw" / "exact_manifests.json").read_text(
                    encoding="utf-8"
                )
            )
            recomputed_envelope_identity = _raw_event_envelope_identity(
                retained_rows, batch_id=str(manifest.get("batch_id") or "")
            )
            if exact_manifests.get("raw_event_envelope_identity") != (
                recomputed_envelope_identity
            ):
                raise RawEvidenceBindingError(
                    "raw event envelope identity does not match retained rows"
                )
            raw_projection = projection_from_raw(
                evidence_kind=str(semantic_contract.get("evidence_kind") or ""),
                payloads=parsed_payloads,
                transport_receipt=transport_receipt,
                exact_manifests=exact_manifests,
            )
            stored_projection = json.loads(
                projection_path.read_text(encoding="utf-8")
            )
            if stored_projection != raw_projection:
                raise RawEvidenceBindingError(
                    "stored decisive projection does not match raw telemetry"
                )
            report_projection = projection_from_report(
                source_report,
                evidence_kind=str(semantic_contract.get("evidence_kind") or ""),
            )
            recomputed_contract = semantic_binding(
                raw_projection, report_projection
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            RawEvidenceBindingError,
        ) as exc:
            raise BatchLifecycleError(f"raw semantic binding failed: {exc}") from exc
        if recomputed_contract != dict(semantic_contract):
            raise BatchLifecycleError("raw semantic binding identity mismatch")
        compact_rows = parquet_table.to_pylist()
        expected_compact = {
            "semantic_evidence_kind": semantic_contract["evidence_kind"],
            "semantic_decisive_projection_sha256": semantic_contract[
                "decisive_projection_sha256"
            ],
            "semantic_raw_projection_sha256": semantic_contract[
                "raw_projection_sha256"
            ],
            "semantic_transport_returncode": transport_receipt["returncode"],
            "semantic_transport_timed_out": transport_receipt["timed_out"],
        }
        if len(compact_rows) != 1 or any(
            compact_rows[0].get(field) != value
            for field, value in expected_compact.items()
        ):
            raise BatchLifecycleError(
                "compact Parquet semantic projection binding mismatch"
            )
    publication_path = batch_root / "retained" / "publication_receipt.json"
    if publication_path.is_file():
        publication = _load_publication_receipt(publication_path, manifest)
        _validate_embedded_publication_pointers(batch_root, publication)
    return manifest


def _validate_manifest_self_identity(manifest: Mapping[str, Any]) -> str:
    identity = dict(manifest) if isinstance(manifest, Mapping) else {}
    stored_identity = str(identity.pop("identity_sha256", ""))
    if not stored_identity or canonical_sha256(identity) != stored_identity:
        raise BatchLifecycleError("final batch manifest self-identity mismatch")
    return stored_identity


def _pointer_document_identity(document: str, pointer_name: str) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(document)
    except yaml.YAMLError as exc:
        raise BatchLifecycleError(
            f"malformed DVC pointer document: {pointer_name}"
        ) from exc
    rows = payload.get("outs") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise BatchLifecycleError(f"malformed DVC pointer document: {pointer_name}")
    row = rows[0]
    checksum = str(row.get("md5") or "")
    if not checksum:
        raise BatchLifecycleError(f"missing DVC checksum: {pointer_name}")
    expected_output = Path(pointer_name).name.removesuffix(".dvc")
    output_path = Path(str(row.get("path") or ""))
    if output_path.is_absolute() or output_path.parts != (expected_output,):
        raise BatchLifecycleError(
            f"DVC pointer output is outside the batch contract: {pointer_name}"
        )
    try:
        size = int(row.get("size") or 0)
        nfiles = int(row.get("nfiles") or 0)
    except (TypeError, ValueError) as exc:
        raise BatchLifecycleError(
            f"invalid DVC pointer metadata: {pointer_name}"
        ) from exc
    if size < 0 or nfiles < 0:
        raise BatchLifecycleError(f"invalid DVC pointer metadata: {pointer_name}")
    return {
        "dvc_md5": checksum,
        "size": size,
        "nfiles": nfiles,
    }


def _pointer_identity(path: Path, repository: Path) -> dict[str, Any]:
    document = path.read_text(encoding="utf-8")
    document_identity = _pointer_document_identity(document, path.name)
    return {
        "path": str(path.relative_to(repository)),
        "pointer_sha256": sha256_file(path),
        **document_identity,
        # The small pointer document is retained in the signed publication
        # receipt so a clean verifier can recreate it before `dvc pull`.
        "pointer_document": document,
    }


def _publication_pointer_rows(
    publication: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows = publication.get("pointers")
    if not isinstance(rows, list) or len(rows) != 2:
        raise BatchLifecycleError("publication must bind exactly two DVC pointers")
    by_name: dict[str, Mapping[str, Any]] = {}
    pointer_parents: set[Path] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise BatchLifecycleError(
                "publication contains a malformed DVC pointer identity"
            )
        pointer_path = Path(str(row.get("path") or ""))
        if pointer_path.is_absolute() or ".." in pointer_path.parts:
            raise BatchLifecycleError(
                "publication DVC pointer path is outside the batch contract"
            )
        name = pointer_path.name
        if name not in {"raw.dvc", "compact.dvc"} or name in by_name:
            raise BatchLifecycleError(
                "publication DVC pointer path is outside the batch contract"
            )
        pointer_parents.add(pointer_path.parent)
        document = str(row.get("pointer_document") or "")
        if not document or hashlib.sha256(document.encode("utf-8")).hexdigest() != str(
            row.get("pointer_sha256") or ""
        ):
            raise BatchLifecycleError("publication DVC pointer document hash mismatch")
        document_identity = _pointer_document_identity(document, name)
        if any(row.get(field) != value for field, value in document_identity.items()):
            raise BatchLifecycleError(
                "publication DVC pointer document metadata mismatch"
            )
        by_name[name] = row
    if set(by_name) != {"raw.dvc", "compact.dvc"}:
        raise BatchLifecycleError("publication DVC pointer set is incomplete")
    if len(pointer_parents) != 1:
        raise BatchLifecycleError("publication DVC pointers do not share one batch root")
    return by_name


def _load_publication_receipt(
    path: Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        publication = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchLifecycleError("missing or malformed publication receipt") from exc
    identity = dict(publication) if isinstance(publication, Mapping) else {}
    stored_hash = str(identity.pop("receipt_sha256", ""))
    if not stored_hash or canonical_sha256(identity) != stored_hash:
        raise BatchLifecycleError("publication receipt hash mismatch")
    if publication.get("schema") != "bot_immutable_batch_publication_receipt_v1":
        raise BatchLifecycleError("publication receipt schema mismatch")
    if publication.get("remote_verified") is not True:
        raise BatchLifecycleError("publication is not remote verified")
    expected_bindings = {
        "batch_id": manifest.get("batch_id"),
        "batch_identity_sha256": manifest.get("identity_sha256"),
        "raw_bundle_sha256": (manifest.get("raw") or {}).get("bundle_sha256"),
        "compact_bundle_sha256": (manifest.get("compact") or {}).get(
            "bundle_sha256"
        ),
    }
    if any(publication.get(key) != value for key, value in expected_bindings.items()):
        raise BatchLifecycleError("publication receipt manifest binding mismatch")
    _publication_pointer_rows(publication)
    return publication


def _validate_embedded_publication_pointers(
    batch_root: Path, publication: Mapping[str, Any]
) -> None:
    for name, expected in _publication_pointer_rows(publication).items():
        pointer = batch_root / name
        if not pointer.is_file():
            raise BatchLifecycleError("published DVC pointer is missing")
        document = pointer.read_text(encoding="utf-8")
        if document != str(expected.get("pointer_document") or ""):
            raise BatchLifecycleError("published DVC pointer document mismatch")
        if sha256_file(pointer) != str(expected.get("pointer_sha256") or ""):
            raise BatchLifecycleError("published DVC pointer identity mismatch")


def _validate_or_restore_publication_pointers(
    repository: Path,
    batch_root: Path,
    publication: Mapping[str, Any],
    *,
    restore_missing: bool,
) -> None:
    expected_rows = _publication_pointer_rows(publication)
    expected_batch = batch_root.resolve().relative_to(repository.resolve())
    for name, expected in expected_rows.items():
        expected_path = (expected_batch / name).as_posix()
        if str(expected.get("path") or "") != expected_path:
            raise BatchLifecycleError("publication DVC pointer repository path mismatch")
        pointer = batch_root / name
        if not pointer.is_file():
            if not restore_missing:
                raise BatchLifecycleError("published DVC pointer is missing")
            pointer.write_text(str(expected["pointer_document"]), encoding="utf-8")
        observed = _pointer_identity(pointer, repository)
        if observed != dict(expected):
            raise BatchLifecycleError("published DVC pointer identity mismatch")


@contextlib.contextmanager
def _batch_cache(repository: Path, cache_dir: Path, *, runner: CommandRunner) -> Iterator[None]:
    local_config = repository / ".dvc" / "config.local"
    existed = local_config.exists()
    original = local_config.read_bytes() if existed else b""
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        _checked(
            ["dvc", "config", "--local", "cache.dir", str(cache_dir)],
            repository,
            runner=runner,
            description="configure batch-specific DVC cache",
        )
        yield
    finally:
        if existed:
            local_config.write_bytes(original)
        else:
            local_config.unlink(missing_ok=True)


@contextlib.contextmanager
def _temporarily_unignore_pointers(
    repository: Path,
    pointer_paths: Sequence[Path],
    *,
    runner: CommandRunner,
) -> Iterator[None]:
    """Expose only exact generated DVC pointer ancestry, then restore ignores."""
    ignore_files: dict[Path, tuple[bool, bytes, Path]] = {}
    for pointer_path in pointer_paths:
        pointer_relative = pointer_path.resolve().relative_to(repository)
        completed = runner(
            ["git", "check-ignore", "-v", "--no-index", str(pointer_relative)],
            repository,
        )
        if completed.returncode == 1:
            continue
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise BatchLifecycleError(
                f"inspect DVC pointer ignore source failed{': ' + detail if detail else ''}"
            )
        ignore_record = completed.stdout.rstrip("\n").split("\t", 1)[0]
        ignore_fields = ignore_record.rsplit(":", 2)
        if len(ignore_fields) != 3 or not ignore_fields[0]:
            raise BatchLifecycleError("git check-ignore returned an invalid pointer record")
        ignore_source = Path(ignore_fields[0])
        if not ignore_source.is_absolute():
            ignore_source = (repository / ignore_source).resolve()
        repository_git_dir = (repository / ".git").resolve()
        if ignore_source == repository_git_dir / "info" / "exclude":
            pattern_base = repository
        else:
            try:
                ignore_source.relative_to(repository)
            except ValueError as exc:
                raise BatchLifecycleError(
                    "DVC pointer is ignored by an external Git exclude file"
                ) from exc
            pattern_base = ignore_source.parent
        if ignore_source not in ignore_files:
            ignore_files[ignore_source] = (
                ignore_source.exists(),
                ignore_source.read_bytes() if ignore_source.exists() else b"",
                pattern_base,
            )

    try:
        for ignore_source, (_, original, pattern_base) in ignore_files.items():
            additions: list[str] = []
            for pointer_path in pointer_paths:
                try:
                    relative = pointer_path.resolve().relative_to(pattern_base)
                except ValueError:
                    continue
                parts = relative.parts
                for depth in range(1, len(parts)):
                    additions.append("!/" + "/".join(parts[:depth]) + "/")
                additions.append("!/" + relative.as_posix())
            unique_additions = list(dict.fromkeys(additions))
            if unique_additions:
                separator = b"" if not original or original.endswith(b"\n") else b"\n"
                ignore_source.parent.mkdir(parents=True, exist_ok=True)
                ignore_source.write_bytes(
                    original + separator
                    + ("\n".join(unique_additions) + "\n").encode("utf-8")
                )
        yield
    finally:
        for ignore_source, (existed, original, _) in ignore_files.items():
            if existed:
                ignore_source.write_bytes(original)
            else:
                ignore_source.unlink(missing_ok=True)


def publish_batch(
    repository: Path,
    batch_root: Path,
    *,
    runner: CommandRunner = _run,
    evict_after_verify: bool = True,
) -> dict[str, Any]:
    """Publish raw and compact identities, then target-evict only after verification."""
    repository = repository.resolve()
    batch_root = batch_root.resolve()
    try:
        relative_batch = batch_root.relative_to(repository)
    except ValueError as exc:
        raise BatchLifecycleError("batch_root must be inside the DVC repository") from exc
    raw_relative = relative_batch / "raw"
    compact_relative = relative_batch / "compact"
    cache_dir = batch_root / ".batch-dvc-cache"
    retained_dir = batch_root / "retained"
    receipt_path = retained_dir / "publication_receipt.json"
    raw_pointer = batch_root / "raw.dvc"
    compact_pointer = batch_root / "compact.dvc"

    with dvc_repository_lock(repository):
        manifest = validate_capture(batch_root)
        with _temporarily_unignore_pointers(
            repository, [raw_pointer, compact_pointer], runner=runner
        ), _batch_cache(repository, cache_dir, runner=runner):
            _checked(
                ["dvc", "add", str(raw_relative), str(compact_relative)],
                repository,
                runner=runner,
                description="DVC-add immutable batch bundles",
            )
            pointers = [
                _pointer_identity(raw_pointer, repository),
                _pointer_identity(compact_pointer, repository),
            ]
            _checked(
                ["dvc", "status", str(raw_pointer.relative_to(repository)), str(compact_pointer.relative_to(repository))],
                repository,
                runner=runner,
                description="check local DVC batch status",
            )
            _checked(
                ["dvc", "push", str(raw_pointer.relative_to(repository)), str(compact_pointer.relative_to(repository))],
                repository,
                runner=runner,
                description="push immutable batch bundles",
            )
            remote = _checked(
                [
                    "dvc",
                    "status",
                    "-q",
                    "-c",
                    str(raw_pointer.relative_to(repository)),
                    str(compact_pointer.relative_to(repository)),
                ],
                repository,
                runner=runner,
                description="verify remote DVC batch status",
            )
            verified_manifest = validate_capture(batch_root)
            if verified_manifest.get("identity_sha256") != manifest.get("identity_sha256"):
                raise BatchLifecycleError("batch identity changed during publication")
            receipt = {
                "schema": "bot_immutable_batch_publication_receipt_v1",
                "batch_id": manifest["batch_id"],
                "batch_identity_sha256": manifest["identity_sha256"],
                "raw_bundle_sha256": manifest["raw"]["bundle_sha256"],
                "compact_bundle_sha256": manifest["compact"]["bundle_sha256"],
                "pointers": pointers,
                "remote_verified": True,
                "remote_status_sha256": hashlib.sha256((remote.stdout + remote.stderr).encode("utf-8")).hexdigest(),
                "cache_scope": "batch_specific",
            }
            receipt["receipt_sha256"] = canonical_sha256(receipt)
            _write_json(receipt_path, receipt)
            stored_receipt = _load_publication_receipt(receipt_path, manifest)
            _validate_embedded_publication_pointers(batch_root, stored_receipt)

        if evict_after_verify:
            shutil.rmtree(batch_root / "raw")
            shutil.rmtree(batch_root / "compact")
            shutil.rmtree(cache_dir, ignore_errors=True)
    return receipt


def cleanup_exported_database_rows(
    connection: Any,
    batch_root: Path,
    *,
    tables: Sequence[str],
) -> dict[str, Any]:
    """Delete only immutable exported rows after remote publication is proven."""
    manifest_path = batch_root / "retained" / "final_manifest.json"
    receipt_path = batch_root / "retained" / "publication_receipt.json"
    if not manifest_path.is_file() or not receipt_path.is_file():
        raise BatchLifecycleError("database cleanup requires manifest and publication receipt")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_identity = dict(receipt)
    stored_receipt_sha256 = str(receipt_identity.pop("receipt_sha256", ""))
    if not stored_receipt_sha256 or canonical_sha256(receipt_identity) != stored_receipt_sha256:
        raise BatchLifecycleError("database cleanup receipt hash mismatch")
    if not receipt.get("remote_verified"):
        raise BatchLifecycleError("database cleanup requires remote verification")
    if receipt.get("batch_identity_sha256") != manifest.get("identity_sha256"):
        raise BatchLifecycleError("database cleanup batch identity mismatch")
    export = manifest.get("database_export")
    if not isinstance(export, Mapping) or not export.get("measurement_window_ids"):
        raise BatchLifecycleError("database cleanup requires an immutable database export")
    batch_id = str(export["batch_id"])
    window_ids = [str(value) for value in export["measurement_window_ids"]]
    deleted: dict[str, int] = {}
    cursor = connection.cursor()
    try:
        placeholders = ", ".join(["%s"] * len(window_ids))
        for table in tables:
            if not table or not table.replace("_", "").isalnum():
                raise BatchLifecycleError(f"unsafe database table name: {table}")
            cursor.execute(
                f"DELETE FROM `{table}` WHERE batch_id = %s "
                f"AND measurement_window_id IN ({placeholders})",
                [batch_id, *window_ids],
            )
            deleted[table] = int(cursor.rowcount)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return {
        "schema": "bot_immutable_database_cleanup_receipt_v1",
        "batch_id": batch_id,
        "measurement_window_ids": window_ids,
        "deleted_rows": deleted,
        "remote_publication_receipt_sha256": stored_receipt_sha256,
    }


def hydrate_batch(
    repository: Path,
    batch_root: Path,
    *,
    runner: CommandRunner = _run,
) -> dict[str, Any]:
    repository = repository.resolve()
    batch_root = batch_root.resolve()
    receipt_path = batch_root / "retained" / "publication_receipt.json"
    if not receipt_path.is_file():
        raise BatchLifecycleError("hydration requires a publication receipt")
    manifest_path = batch_root / "retained" / "final_manifest.json"
    if not manifest_path.is_file():
        raise BatchLifecycleError("hydration requires a final batch manifest")
    try:
        retained_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchLifecycleError("hydration final manifest is malformed") from exc
    _validate_manifest_self_identity(retained_manifest)
    receipt = _load_publication_receipt(receipt_path, retained_manifest)
    _validate_or_restore_publication_pointers(
        repository, batch_root, receipt, restore_missing=True
    )
    cache_dir = batch_root / ".hydrate-dvc-cache"
    pointers = [batch_root / "raw.dvc", batch_root / "compact.dvc"]
    with dvc_repository_lock(repository):
        with _temporarily_unignore_pointers(
            repository, pointers, runner=runner
        ), _batch_cache(repository, cache_dir, runner=runner):
            _checked(
                ["dvc", "pull", *(str(path.relative_to(repository)) for path in pointers)],
                repository,
                runner=runner,
                description="hydrate immutable batch",
            )
            manifest = validate_capture(batch_root)
    if manifest.get("identity_sha256") != receipt.get("batch_identity_sha256"):
        raise BatchLifecycleError("hydrated batch identity does not match receipt")
    shutil.rmtree(cache_dir, ignore_errors=True)
    return {
        "schema": "bot_immutable_batch_hydration_v1",
        "batch_id": manifest["batch_id"],
        "batch_identity_sha256": manifest["identity_sha256"],
        "hydrated": True,
    }


def valid_reconstruction_receipt(
    batch_root: Path,
    *,
    required_domain_verification_id: str = "",
) -> tuple[bool, dict[str, Any]]:
    """Validate the retained proof that both DVC bundles were reconstructed."""
    receipt_path = batch_root / "retained" / "reconstruction_receipt.json"
    publication_path = batch_root / "retained" / "publication_receipt.json"
    manifest_path = batch_root / "retained" / "final_manifest.json"
    if not all(path.is_file() for path in (receipt_path, publication_path, manifest_path)):
        return False, {}
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, {}
    try:
        _validate_manifest_self_identity(manifest)
        publication = _load_publication_receipt(publication_path, manifest)
        _validate_embedded_publication_pointers(batch_root, publication)
    except (BatchLifecycleError, OSError, ValueError):
        return False, {}
    identity = dict(receipt) if isinstance(receipt, Mapping) else {}
    stored_hash = str(identity.pop("receipt_sha256", ""))
    publication_hash = str(publication.get("receipt_sha256") or "")
    valid = bool(
        receipt.get("schema") == "bot_immutable_batch_reconstruction_receipt_v1"
        and stored_hash
        and canonical_sha256(identity) == stored_hash
        and publication_hash
        and receipt.get("remote_reconstructed") is True
        and receipt.get("targeted_eviction_complete") is True
        and (
            not required_domain_verification_id
            or receipt.get("domain_verification_id")
            == required_domain_verification_id
        )
        and receipt.get("batch_identity_sha256") == manifest.get("identity_sha256")
        and receipt.get("publication_receipt_sha256") == publication_hash
        and not (batch_root / "raw").exists()
        and not (batch_root / "compact").exists()
        and not (batch_root / ".hydrate-dvc-cache").exists()
        and not (batch_root / ".batch-dvc-cache").exists()
    )
    return valid, receipt if valid else {}


def _evict_exact_reconstruction_payloads(batch_root: Path) -> None:
    """Remove only materialized batch payloads and their two private caches."""
    for name in ("raw", "compact", ".hydrate-dvc-cache", ".batch-dvc-cache"):
        target = batch_root / name
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise BatchLifecycleError(
                f"targeted reconstruction path is not a directory: {name}"
            )
        if target.is_dir():
            shutil.rmtree(target)
        if target.exists() or target.is_symlink():
            raise BatchLifecycleError(
                f"targeted reconstruction eviction incomplete: {name}"
            )


def verify_remote_reconstruction_and_evict(
    repository: Path,
    batch_root: Path,
    *,
    runner: CommandRunner = _run,
    domain_verification_id: str = "",
    verify_hydrated: Callable[[Path], Mapping[str, Any]] | None = None,
    force_reconstruct: bool = False,
) -> dict[str, Any]:
    """Round-trip one published batch from DVC, verify it, then evict only it."""
    if not force_reconstruct:
        valid, receipt = valid_reconstruction_receipt(
            batch_root,
            required_domain_verification_id=domain_verification_id,
        )
        if valid:
            return receipt
    publication_path = batch_root / "retained" / "publication_receipt.json"
    manifest_path = batch_root / "retained" / "final_manifest.json"
    if not publication_path.is_file() or not manifest_path.is_file():
        raise BatchLifecycleError(
            "remote reconstruction requires publication and manifest receipts"
        )
    try:
        retained_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchLifecycleError("remote reconstruction manifest is malformed") from exc
    _validate_manifest_self_identity(retained_manifest)
    publication = _load_publication_receipt(publication_path, retained_manifest)
    if force_reconstruct:
        _validate_or_restore_publication_pointers(
            repository.resolve(), batch_root.resolve(), publication, restore_missing=True
        )
        _evict_exact_reconstruction_payloads(batch_root)
    try:
        hydration = hydrate_batch(repository, batch_root, runner=runner)
        raw = batch_root / "raw"
        compact = batch_root / "compact"
        if not raw.is_dir() or not compact.is_dir():
            raise BatchLifecycleError(
                "remote reconstruction did not hydrate both batch bundles"
            )
        domain_verification: dict[str, Any] = {}
        if verify_hydrated is not None:
            domain_verification = dict(verify_hydrated(batch_root))
            if domain_verification.get("verified") is not True:
                raise BatchLifecycleError(
                    "domain-specific remote reconstruction failed"
                )
    except BaseException as original_error:
        if force_reconstruct:
            try:
                _evict_exact_reconstruction_payloads(batch_root)
            except Exception as cleanup_error:
                original_error.add_note(
                    f"forced reconstruction cleanup also failed: {cleanup_error}"
                )
        raise
    _evict_exact_reconstruction_payloads(batch_root)
    receipt = {
        "schema": "bot_immutable_batch_reconstruction_receipt_v1",
        "batch_id": hydration["batch_id"],
        "batch_identity_sha256": hydration["batch_identity_sha256"],
        "publication_receipt_sha256": publication.get("receipt_sha256"),
        "remote_reconstructed": True,
        "targeted_eviction_complete": True,
        "domain_verification_id": domain_verification_id,
        "domain_verification": domain_verification,
        "force_reconstructed": force_reconstruct,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    _write_json(batch_root / "retained" / "reconstruction_receipt.json", receipt)
    valid, stored = valid_reconstruction_receipt(
        batch_root,
        required_domain_verification_id=domain_verification_id,
    )
    if not valid:
        raise BatchLifecycleError("remote reconstruction receipt failed validation")
    return stored


def finalize_heartbeat(output_dir: Path, heartbeat: Mapping[str, Any]) -> dict[str, Any]:
    latest_path = output_dir / "latest.json"
    stream = output_dir / "heartbeat_events.jsonl"
    _write_json(latest_path, dict(heartbeat))
    manifest = {
        "schema": "bot_compact_heartbeat_manifest_v1",
        "heartbeat_count": sum(1 for line in stream.read_text(encoding="utf-8").splitlines() if line.strip()) if stream.is_file() else 0,
        "latest_sha256": sha256_file(latest_path),
        "stream_sha256": sha256_file(stream) if stream.is_file() else "",
        "one_file_per_heartbeat": False,
    }
    manifest["identity_sha256"] = canonical_sha256(manifest)
    _write_json(output_dir / "heartbeat_manifest.json", manifest)
    return manifest


def append_heartbeat(output_dir: Path, heartbeat: Mapping[str, Any]) -> None:
    """Keep one latest heartbeat plus one compact append-only stream."""
    latest = dict(heartbeat)
    stream = output_dir / "heartbeat_events.jsonl"
    stream.parent.mkdir(parents=True, exist_ok=True)
    compact = {
        "heartbeat_index": int(latest.get("heartbeat_index") or 0),
        "generated_at_unix": int(latest.get("heartbeat_generated_at_unix") or 0),
        "completion_reason": str(latest.get("completion_reason") or ""),
        "failure_labels": list(latest.get("failure_labels") or []),
        "progress_counters": dict(latest.get("progress_counters") or {}),
        "acceptance_result_sha256": str(((latest.get("acceptance_verification") or {}).get("result_sha256") or "")),
    }
    with stream.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(compact, sort_keys=True) + "\n")
    finalize_heartbeat(output_dir, latest)


def _init_synthetic_repository(root: Path, *, runner: CommandRunner) -> tuple[Path, Path]:
    repository = root / "repo"
    remote = root / "remote"
    repository.mkdir(parents=True)
    remote.mkdir(parents=True)
    _checked(["git", "init"], repository, runner=runner, description="initialize synthetic Git repository")
    _checked(["dvc", "init"], repository, runner=runner, description="initialize synthetic DVC repository")
    _checked(["dvc", "remote", "add", "-d", "synthetic", str(remote)], repository, runner=runner, description="configure synthetic DVC remote")
    return repository, remote


def _accepted_report() -> dict[str, Any]:
    return {
        "schema": "bot_live_validation_report_v1",
        "returncode": 0,
        "timed_out": False,
        "stages": [{"stage": "synthetic", "missing": []}],
        "failure_labels": [],
        "validation_context": {},
        "evidence": {},
        "validation_route_manifest": {},
        "watchdog_state": {},
    }


def synthetic_round_trip_contract() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="bot-phase3-") as temporary:
        root = Path(temporary)
        repository, _ = _init_synthetic_repository(root / "success", runner=_run)
        # Phase 9 keeps generated campaign payloads ignored in Git. Exercise
        # the production topology where the immutable DVC pointers inherit
        # that parent ignore rule and publication must explicitly force-add.
        (repository / ".gitignore").write_text("/batches/\n", encoding="utf-8")
        batch = repository / "batches" / "synthetic-success"
        capture_batch(
            batch,
            batch_id="synthetic-success",
            raw_rows=[{"event": "start"}, {"event": "complete"}],
            compact_rows=[{"metric": "damage", "value": 1.0}],
            exact_manifests={"config_sha256": hashlib.sha256(b"config").hexdigest()},
            summary={"closed": True},
            acceptance_report=_accepted_report(),
        )
        receipt = publish_batch(repository, batch)
        evicted = not (batch / "raw").exists() and not (batch / "compact").exists() and not (batch / ".batch-dvc-cache").exists()
        reconstruction = verify_remote_reconstruction_and_evict(repository, batch)
        hydration = {
            "schema": "bot_immutable_batch_hydration_v1",
            "batch_id": reconstruction["batch_id"],
            "batch_identity_sha256": reconstruction["batch_identity_sha256"],
            "hydrated": bool(reconstruction.get("remote_reconstructed")),
            "targeted_eviction_complete": bool(
                reconstruction.get("targeted_eviction_complete")
            ),
            "reconstruction_receipt_sha256": reconstruction.get(
                "receipt_sha256"
            ),
        }

        corrupt_repository, _ = _init_synthetic_repository(root / "corrupt", runner=_run)
        corrupt_batch = corrupt_repository / "batches" / "synthetic-corrupt"
        capture_batch(
            corrupt_batch,
            batch_id="synthetic-corrupt",
            raw_rows=[{"event": "original"}],
            compact_rows=[{"metric": "value", "value": 2.0}],
            exact_manifests={"config": "v1"},
            summary={"closed": True},
            acceptance_report=_accepted_report(),
        )
        with (corrupt_batch / "raw" / "events.jsonl.zst").open("ab") as handle:
            handle.write(b"corruption")
        corruption_blocked = False
        try:
            publish_batch(corrupt_repository, corrupt_batch)
        except BatchLifecycleError:
            corruption_blocked = (corrupt_batch / "raw").exists() and (corrupt_batch / "compact").exists()

        failed_repository, _ = _init_synthetic_repository(root / "failed-push", runner=_run)
        failed_batch = failed_repository / "batches" / "synthetic-failed-push"
        capture_batch(
            failed_batch,
            batch_id="synthetic-failed-push",
            raw_rows=[{"event": "retained"}],
            compact_rows=[{"metric": "value", "value": 3.0}],
            exact_manifests={"config": "v1"},
            summary={"closed": True},
            acceptance_report=_accepted_report(),
        )

        def fail_push(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            if list(command[:2]) == ["dvc", "push"]:
                return subprocess.CompletedProcess(command, 1, "", "synthetic push failure")
            return _run(command, cwd)

        failed_push_blocked = False
        try:
            publish_batch(failed_repository, failed_batch, runner=fail_push)
        except BatchLifecycleError:
            failed_push_blocked = (
                (failed_batch / "raw").exists()
                and (failed_batch / "compact").exists()
                and not (failed_batch / "retained" / "publication_receipt.json").exists()
            )

        gate_passed = bool(
            receipt.get("remote_verified")
            and evicted
            and hydration.get("hydrated")
            and corruption_blocked
            and failed_push_blocked
        )
        return {
            "schema": "all_spec_phase3_batch_lifecycle_contract_v1",
            "gate_passed": gate_passed,
            "capture": {
                "raw_format": "jsonl.zst",
                "compact_format": "parquet_zstd",
                "duplicate_representation_retained": False,
            },
            "publication": {
                "separate_raw_compact_pointers": len(receipt.get("pointers") or []) == 2,
                "remote_verified": bool(receipt.get("remote_verified")),
                "receipt_present_before_cleanup": bool(receipt.get("receipt_sha256")),
                "targeted_eviction": evicted,
            },
            "hydration": hydration,
            "failure_guards": {
                "corruption_blocks_cleanup": corruption_blocked,
                "failed_push_blocks_cleanup": failed_push_blocked,
            },
        }


def write_contract(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = synthetic_round_trip_contract()
    _write_json(output_dir / "contract.json", contract)
    manifest = {
        "schema": "all_spec_phase3_batch_lifecycle_manifest_v1",
        "gate_passed": bool(contract["gate_passed"]),
        "contract_sha256": sha256_file(output_dir / "contract.json"),
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Phase 3 immutable batch lifecycle contract")
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/all_spec_phase3_batch_lifecycle"))
    args = parser.parse_args()
    manifest = write_contract(args.output_dir)
    print(json.dumps(manifest, sort_keys=True))
    return 0 if manifest["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
