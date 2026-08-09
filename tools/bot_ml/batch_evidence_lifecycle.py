from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
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
except ImportError:
    from live_validation_session import (
        canonical_sha256,
        dvc_repository_lock,
        sha256_file,
        verify_report_acceptance,
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
) -> dict[str, Any]:
    """Capture one bounded raw stream and one compact analytical representation."""
    if not batch_id.strip():
        raise BatchLifecycleError("batch_id is required")
    raw_dir = batch_root / "raw"
    compact_dir = batch_root / "compact"
    retained_dir = batch_root / "retained"
    if raw_dir.exists() or compact_dir.exists():
        raise BatchLifecycleError("immutable batch paths already exist")
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
    _write_json(raw_dir / "exact_manifests.json", exact_manifests)
    _write_json(raw_dir / "acceptance_source_report.json", acceptance_report)
    compact_count = _write_parquet(compact_dir / "evidence.parquet", compact_rows)
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
    parquet_rows = pq.read_table(batch_root / "compact" / "evidence.parquet").num_rows
    if parquet_rows != int((manifest.get("compact") or {}).get("row_count") or 0):
        raise BatchLifecycleError("compact row count mismatch")
    source_report = json.loads(
        (batch_root / "raw" / "acceptance_source_report.json").read_text(encoding="utf-8")
    )
    if verify_report_acceptance(source_report) != manifest.get("acceptance"):
        raise BatchLifecycleError("independent acceptance recomputation mismatch")
    return manifest


def _pointer_identity(path: Path, repository: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = payload.get("outs") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise BatchLifecycleError(f"malformed DVC pointer: {path}")
    row = rows[0]
    checksum = str(row.get("md5") or "")
    if not checksum:
        raise BatchLifecycleError(f"missing DVC checksum: {path}")
    return {
        "path": str(path.relative_to(repository)),
        "pointer_sha256": sha256_file(path),
        "dvc_md5": checksum,
        "size": int(row.get("size") or 0),
        "nfiles": int(row.get("nfiles") or 0),
    }


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
                ["dvc", "status", "-c", str(raw_pointer.relative_to(repository)), str(compact_pointer.relative_to(repository))],
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
            stored_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            stored_receipt_sha256 = str(stored_receipt.pop("receipt_sha256", ""))
            if stored_receipt_sha256 != receipt["receipt_sha256"] or canonical_sha256(stored_receipt) != stored_receipt_sha256:
                raise BatchLifecycleError("missing or invalid publication receipt")

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
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
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
        hydration = hydrate_batch(repository, batch)

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
