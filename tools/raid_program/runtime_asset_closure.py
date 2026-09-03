from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping, Sequence


ROOT_KEYS = (
    "source-checkout",
    "configured-DataDir",
    "dvc-workspace",
    "sealed-bundle",
)
ISSUE_KINDS = (
    "manifest_invalid",
    "root_mismatch",
    "missing",
    "extra",
    "type_mismatch",
    "symlink",
    "hash_mismatch",
    "size_mismatch",
    "mode_mismatch",
    "dvc_provenance_mismatch",
    "provenance_missing",
    "provenance_invalid",
    "snapshot_mismatch",
)


class DuplicateKeyError(ValueError):
    pass


class ManifestError(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _normal_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError("path_missing")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ManifestError(f"path_traversal:{value}")
    if "\\" in value or value != pure.as_posix():
        raise ManifestError(f"path_invalid:{value}")
    return value


def _check_ancestors(root: Path, relative: str) -> str | None:
    current = root
    try:
        root_stat = current.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(root_stat.st_mode):
        return "."
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        try:
            value = current.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(value.st_mode):
            return current.relative_to(root).as_posix()
    return None


def _read_regular_no_follow(path: Path) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("not_regular_file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise OSError("file_changed_while_reading")
        return b"".join(chunks), after
    finally:
        os.close(descriptor)


def load_json_strict(path: Path) -> dict[str, Any]:
    path = _normal_path(path)
    ancestor = _check_ancestors(path.parent, path.name)
    if ancestor is not None:
        raise ManifestError(f"symlink:{path}")
    try:
        payload, _ = _read_regular_no_follow(path)
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKeyError) as error:
        raise ManifestError(str(error)) from error
    if not isinstance(value, dict):
        raise ManifestError("json_root_not_object")
    return value


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record(path: Path, root: Path, relative: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ancestor = _check_ancestors(root, relative)
    if ancestor is not None:
        return None, {"kind": "symlink", "path": ancestor}
    target = root / relative
    try:
        value = target.lstat()
    except FileNotFoundError:
        return None, {"kind": "missing", "path": relative}
    except OSError as error:
        return None, {"kind": "type_mismatch", "path": relative, "detail": str(error)}
    mode = f"{stat.S_IMODE(value.st_mode):04o}"
    if stat.S_ISLNK(value.st_mode):
        return None, {"kind": "symlink", "path": relative}
    if not stat.S_ISREG(value.st_mode):
        return None, {
            "kind": "type_mismatch", "path": relative,
            "expected": "file", "observed": "directory" if stat.S_ISDIR(value.st_mode) else "other",
        }
    try:
        payload, read_stat = _read_regular_no_follow(target)
    except OSError as error:
        return None, {"kind": "type_mismatch", "path": relative, "detail": str(error)}
    return {
        "path": relative,
        "type": "file",
        "mode": mode,
        "size_bytes": read_stat.st_size,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }, None


def _walk_files(root: Path, relative: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    ancestor = _check_ancestors(root, relative)
    if ancestor is not None:
        return records, [{"kind": "symlink", "path": ancestor}]
    start = root / relative
    try:
        start_stat = start.lstat()
    except FileNotFoundError:
        return records, [{"kind": "missing", "path": relative}]
    if stat.S_ISLNK(start_stat.st_mode):
        return records, [{"kind": "symlink", "path": relative}]
    if not stat.S_ISDIR(start_stat.st_mode):
        return records, [{
            "kind": "type_mismatch", "path": relative,
            "expected": "directory", "observed": "file" if stat.S_ISREG(start_stat.st_mode) else "other",
        }]
    pending = [start]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            issues.append({
                "kind": "type_mismatch",
                "path": directory.relative_to(root).as_posix(),
                "detail": str(error),
            })
            continue
        for entry in entries:
            child = Path(entry.path)
            child_relative = child.relative_to(root).as_posix()
            if entry.is_symlink():
                issues.append({"kind": "symlink", "path": child_relative})
            elif entry.is_dir(follow_symlinks=False):
                pending.append(child)
            elif entry.is_file(follow_symlinks=False):
                record, issue = _record(child, root, child_relative)
                if record is not None:
                    records.append(record)
                if issue is not None:
                    issues.append(issue)
            else:
                issues.append({"kind": "type_mismatch", "path": child_relative})
    return sorted(records, key=lambda row: row["path"]), issues


def _inventory(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [dict(row) for row in sorted(records, key=lambda row: str(row["path"]))]
    return {
        "file_count": len(normalized),
        "size_bytes": sum(int(row["size_bytes"]) for row in normalized),
        "path_set_sha256": canonical_sha256([row["path"] for row in normalized]),
        "inventory_sha256": canonical_sha256(normalized),
    }


def _expected_map_values(asset_class: Mapping[str, Any], map_id: int) -> dict[str, Any]:
    maps = asset_class.get("map_contracts")
    if not isinstance(maps, dict):
        return dict(asset_class)
    selected = maps.get(str(map_id))
    if not isinstance(selected, dict):
        raise ManifestError(f"scenario_map_contract_missing:{map_id}")
    merged = dict(asset_class)
    merged.pop("map_contracts", None)
    merged.update(selected)
    return merged


def _compare_expected_record(
    expected: Mapping[str, Any], observed: Mapping[str, Any], class_id: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field, kind in (
        ("sha256", "hash_mismatch"),
        ("size_bytes", "size_mismatch"),
        ("mode", "mode_mismatch"),
    ):
        if field in expected and observed.get(field) != expected[field]:
            issues.append({
                "kind": kind,
                "class_id": class_id,
                "path": observed["path"],
                "expected": expected[field],
                "observed": observed.get(field),
            })
    return issues


def _verify_class(
    asset_class: Mapping[str, Any], roots: Mapping[str, Path], map_id: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    values = _expected_map_values(asset_class, map_id)
    class_id = str(values.get("id") or "")
    root_key = values.get("root")
    if not class_id or root_key not in roots:
        raise ManifestError(f"asset_class_invalid:{class_id or 'unnamed'}")
    for field in ("consumer", "audience", "provenance", "hydration_source", "eviction_policy"):
        if not isinstance(values.get(field), str) or not values[field]:
            raise ManifestError(f"asset_class_{field}_missing:{class_id}")
    root = roots[str(root_key)]
    rule = values.get("rule")
    expected_files = values.get("expected_files", [])
    if not isinstance(expected_files, list):
        raise ManifestError(f"expected_files_invalid:{class_id}")
    expected_names = values.get("expected_names", [])
    if not isinstance(expected_names, list):
        raise ManifestError(f"expected_names_invalid:{class_id}")
    if expected_names:
        base = _safe_relative(values.get("path"))
        for name in expected_names:
            safe_name = _safe_relative(name)
            if len(PurePosixPath(safe_name).parts) != 1:
                raise ManifestError(f"expected_name_invalid:{class_id}:{safe_name}")
            expected_files.append({"path": f"{base}/{safe_name}"})
    expected_by_path: dict[str, dict[str, Any]] = {}
    for row in expected_files:
        if not isinstance(row, dict):
            raise ManifestError(f"expected_file_invalid:{class_id}")
        relative = _safe_relative(row.get("path"))
        if relative in expected_by_path:
            raise ManifestError(f"duplicate_expected_path:{class_id}:{relative}")
        expected_by_path[relative] = row
    records: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    if rule == "exact-file":
        candidates = sorted(expected_by_path)
    elif rule in {"bounded-pattern", "complete-directory"}:
        base = _safe_relative(values.get("path"))
        all_records, walk_issues = _walk_files(root, base)
        if expected_by_path:
            walk_issues = [
                issue for issue in walk_issues
                if not (issue.get("kind") == "missing" and issue.get("path") == base)
            ]
        walked_by_path = {row["path"]: row for row in all_records}
        issues.extend(walk_issues)
        if rule == "complete-directory":
            candidates = [row["path"] for row in all_records]
        else:
            pattern_text = values.get("pattern")
            if not isinstance(pattern_text, str):
                raise ManifestError(f"pattern_missing:{class_id}")
            try:
                pattern = re.compile(pattern_text)
            except re.error as error:
                raise ManifestError(f"pattern_invalid:{class_id}:{error}") from error
            candidates = [
                row["path"] for row in all_records
                if pattern.fullmatch(PurePosixPath(row["path"]).name)
            ]
        observed_paths = set(candidates)
        expected_paths = set(expected_by_path)
        for relative in sorted(expected_paths - observed_paths):
            issues.append({"kind": "missing", "class_id": class_id, "path": relative})
        for relative in sorted(observed_paths - expected_paths) if expected_paths else []:
            issues.append({"kind": "extra", "class_id": class_id, "path": relative})
    else:
        raise ManifestError(f"rule_invalid:{class_id}:{rule}")
    seen_issue_paths = {
        (issue.get("kind"), issue.get("path")) for issue in issues
    }
    for relative in candidates:
        record = walked_by_path.get(relative) if rule in {
            "bounded-pattern", "complete-directory",
        } else None
        issue = None
        if record is None:
            record, issue = _record(root / relative, root, relative)
        if issue is not None:
            key = (issue.get("kind"), issue.get("path"))
            if key not in seen_issue_paths:
                issues.append({**issue, "class_id": class_id})
                seen_issue_paths.add(key)
            continue
        assert record is not None
        records.append(record)
        expected = expected_by_path.get(relative)
        if expected is not None:
            issues.extend(_compare_expected_record(expected, record, class_id))
    records.sort(key=lambda row: row["path"])
    expected_mode = values.get("expected_mode")
    if expected_mode is not None:
        for record in records:
            if record["mode"] != expected_mode:
                issues.append({
                    "kind": "mode_mismatch", "class_id": class_id,
                    "path": record["path"], "expected": expected_mode,
                    "observed": record["mode"],
                })
    observed_inventory = _inventory(records)
    expected_inventory = values.get("expected_inventory")
    if isinstance(expected_inventory, dict):
        for field, kind in (
            ("size_bytes", "size_mismatch"),
            ("path_set_sha256", "hash_mismatch"),
            ("inventory_sha256", "hash_mismatch"),
        ):
            if field in expected_inventory and observed_inventory[field] != expected_inventory[field]:
                issues.append({
                    "kind": kind, "class_id": class_id,
                    "path": values.get("path", class_id), "field": field,
                    "expected": expected_inventory[field],
                    "observed": observed_inventory[field],
                })
        if "file_count" in expected_inventory:
            expected_count = int(expected_inventory["file_count"])
            observed_count = int(observed_inventory["file_count"])
            has_member_delta = any(
                issue.get("kind") in {"missing", "extra"}
                and issue.get("class_id", class_id) == class_id
                for issue in issues
            )
            if observed_count != expected_count and not has_member_delta:
                issues.append({
                    "kind": "missing" if observed_count < expected_count else "extra",
                    "class_id": class_id, "path": values.get("path", class_id),
                    "field": "file_count", "expected": expected_count,
                    "observed": observed_count,
                    "count_delta": abs(expected_count - observed_count),
                })
    for issue in issues:
        issue.setdefault("class_id", class_id)
        issue.setdefault("root", str(root_key))
    snapshot = {
        f"{class_id}:{row['path']}": {"root": str(root_key), **row}
        for row in records
    }
    result = {
        "id": class_id,
        "consumer": values.get("consumer"),
        "audience": values.get("audience"),
        "root": root_key,
        "rule": rule,
        "passed": not issues,
        "observed_inventory": observed_inventory,
        "audit_inventory_sha256": values.get("audit_inventory_sha256"),
        "issue_count": len(issues),
    }
    return result, issues, snapshot


def data_dir_from_worldserver_config(config: Path) -> Path:
    config = _normal_path(config)
    payload, _ = _read_regular_no_follow(config)
    matches: list[str] = []
    for raw_line in payload.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r'DataDir\s*=\s*(?:"([^"]+)"|([^#\s]+))\s*', line)
        if match:
            matches.append(match.group(1) or match.group(2))
    if len(matches) != 1:
        raise ManifestError(f"configured_DataDir_count:{len(matches)}")
    data_dir = Path(matches[0])
    if not data_dir.is_absolute():
        data_dir = config.parent / data_dir
    return _normal_path(data_dir)


def _dvc_stage_output(workspace: Path, stage_id: str, output_path: str) -> dict[str, Any] | None:
    try:
        import yaml
        lock_bytes, _ = _read_regular_no_follow(workspace / "dvc.lock")
        lock = yaml.safe_load(lock_bytes.decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    stages = lock.get("stages") if isinstance(lock, dict) else None
    stage = stages.get(stage_id) if isinstance(stages, dict) else None
    outputs = stage.get("outs") if isinstance(stage, dict) else None
    if not isinstance(outputs, list):
        return None
    matches = [row for row in outputs if isinstance(row, dict) and row.get("path") == output_path]
    return matches[0] if len(matches) == 1 else None


def _verify_dvc_provenance(
    manifest: Mapping[str, Any], roots: Mapping[str, Path],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    rows = manifest.get("dvc_provenance", [])
    if not isinstance(rows, list):
        raise ManifestError("dvc_provenance_invalid")
    for expected in rows:
        if not isinstance(expected, dict):
            raise ManifestError("dvc_provenance_row_invalid")
        stage = str(expected.get("stage") or "")
        output_path = _safe_relative(expected.get("output_path"))
        observed = _dvc_stage_output(roots["dvc-workspace"], stage, output_path)
        if observed is None:
            issues.append({
                "kind": "dvc_provenance_mismatch", "class_id": expected.get("class_id"),
                "path": output_path, "field": "stage_output", "expected": stage,
                "observed": None, "root": "dvc-workspace",
            })
            continue
        for field in ("md5", "size", "nfiles"):
            if field in expected and observed.get(field) != expected[field]:
                issues.append({
                    "kind": "dvc_provenance_mismatch", "class_id": expected.get("class_id"),
                    "path": output_path, "field": field,
                    "expected": expected[field], "observed": observed.get(field),
                    "root": "dvc-workspace",
                })
    return issues


def _verify_extraction_provenance(
    manifest: Mapping[str, Any], roots: Mapping[str, Path],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    requirement = manifest.get("native_extraction_provenance")
    if not isinstance(requirement, dict):
        raise ManifestError("native_extraction_provenance_invalid")
    relative = _safe_relative(requirement.get("path"))
    target = roots["configured-DataDir"] / relative
    try:
        payload = load_json_strict(target)
    except ManifestError as error:
        kind = "provenance_missing" if not target.exists() else "provenance_invalid"
        return [{
            "kind": kind, "class_id": "native_extraction_provenance",
            "path": relative, "root": "configured-DataDir", "detail": str(error),
        }], None
    issues: list[dict[str, Any]] = []
    for field, expected in (requirement.get("required_fields") or {}).items():
        if payload.get(field) != expected:
            issues.append({
                "kind": "provenance_invalid", "class_id": "native_extraction_provenance",
                "path": relative, "root": "configured-DataDir", "field": field,
                "expected": expected, "observed": payload.get(field),
            })
    return issues, payload


def verify_runtime_asset_closure(
    *, manifest_path: Path, source_checkout: Path, configured_data_dir: Path | None,
    dvc_workspace: Path, sealed_bundle: Path, worldserver_config: Path,
    scenario_map_id: int, previous_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_path = _normal_path(manifest_path)
    manifest_bytes, _ = _read_regular_no_follow(manifest_path)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    try:
        manifest = json.loads(
            manifest_bytes.decode("utf-8"), object_pairs_hook=_strict_object,
        )
        if not isinstance(manifest, dict):
            raise ManifestError("manifest_root_not_object")
        if manifest.get("schema") != "cata_runtime_asset_closure_manifest_v1":
            raise ManifestError("manifest_schema_invalid")
        audit = manifest.get("audit")
        if not isinstance(audit, dict) or not re.fullmatch(
            r"[0-9a-f]{64}", str(audit.get("sha256") or ""),
        ):
            raise ManifestError("audit_binding_invalid")
        derived_data_dir = data_dir_from_worldserver_config(worldserver_config)
    except (UnicodeError, json.JSONDecodeError, DuplicateKeyError, ManifestError, OSError) as error:
        return {
            "schema": "cata_runtime_asset_closure_receipt_v1",
            "complete": False,
            "status": "runtime_asset_closure_incomplete",
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "issues": [{"kind": "manifest_invalid", "detail": str(error)}],
            "issue_counts": {"manifest_invalid": 1},
            "snapshot": {},
        }
    supplied_data_dir = _normal_path(configured_data_dir) if configured_data_dir else derived_data_dir
    roots = {
        "source-checkout": _normal_path(source_checkout),
        "configured-DataDir": derived_data_dir,
        "dvc-workspace": _normal_path(dvc_workspace),
        "sealed-bundle": _normal_path(sealed_bundle),
    }
    issues: list[dict[str, Any]] = []
    if supplied_data_dir != derived_data_dir:
        issues.append({
            "kind": "root_mismatch", "root": "configured-DataDir",
            "expected": str(derived_data_dir), "observed": str(supplied_data_dir),
        })
    for key in ROOT_KEYS:
        try:
            value = roots[key].lstat()
            if stat.S_ISLNK(value.st_mode):
                issues.append({"kind": "symlink", "root": key, "path": "."})
            elif not stat.S_ISDIR(value.st_mode):
                issues.append({"kind": "type_mismatch", "root": key, "path": "."})
        except OSError:
            issues.append({"kind": "missing", "root": key, "path": "."})
    class_results: list[dict[str, Any]] = []
    snapshot: dict[str, dict[str, Any]] = {}
    classes = manifest.get("asset_classes")
    try:
        if not isinstance(classes, list):
            raise ManifestError("asset_classes_invalid")
        for asset_class in classes:
            if not isinstance(asset_class, dict):
                raise ManifestError("asset_class_not_object")
            result, class_issues, class_snapshot = _verify_class(
                asset_class, roots, scenario_map_id,
            )
            class_results.append(result)
            issues.extend(class_issues)
            snapshot.update(class_snapshot)
        issues.extend(_verify_dvc_provenance(manifest, roots))
        provenance_issues, provenance = _verify_extraction_provenance(manifest, roots)
        issues.extend(provenance_issues)
    except ManifestError as error:
        issues.append({"kind": "manifest_invalid", "detail": str(error)})
        provenance = None
    if previous_snapshot is not None:
        previous = dict(previous_snapshot)
        for key in sorted(set(previous) | set(snapshot)):
            if previous.get(key) != snapshot.get(key):
                issues.append({
                    "kind": "snapshot_mismatch", "path": key,
                    "expected": previous.get(key), "observed": snapshot.get(key),
                })
    order = {name: index for index, name in enumerate(ISSUE_KINDS)}
    issues.sort(key=lambda row: (
        order.get(str(row.get("kind")), len(order)),
        str(row.get("class_id") or ""), str(row.get("root") or ""),
        str(row.get("path") or ""), str(row.get("field") or ""),
    ))
    issue_counts = {
        kind: sum(issue.get("kind") == kind for issue in issues)
        for kind in ISSUE_KINDS if any(issue.get("kind") == kind for issue in issues)
    }
    complete = not issues
    return {
        "schema": "cata_runtime_asset_closure_receipt_v1",
        "complete": complete,
        "status": "runtime_asset_closure_complete" if complete else "runtime_asset_closure_incomplete",
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "audit": manifest["audit"],
        "roots": {key: str(value) for key, value in roots.items()},
        "configured_data_dir_binding": {
            "config": str(_normal_path(worldserver_config)),
            "derived": str(derived_data_dir),
            "supplied": str(supplied_data_dir),
            "matched": supplied_data_dir == derived_data_dir,
        },
        "scenario_map_id": scenario_map_id,
        "asset_classes": class_results,
        "native_extraction_provenance": provenance,
        "issues": issues,
        "issue_counts": issue_counts,
        "snapshot_sha256": canonical_sha256(snapshot),
        "snapshot": snapshot,
    }


def require_runtime_asset_closure(**kwargs: Any) -> dict[str, Any]:
    receipt = verify_runtime_asset_closure(**kwargs)
    if not receipt["complete"]:
        kinds = ",".join(sorted(receipt.get("issue_counts", {})))
        raise SystemExit(f"runtime_asset_closure_incomplete:{kinds}")
    return receipt


def add_runtime_asset_closure_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runtime-asset-closure-manifest", type=Path)
    parser.add_argument("--runtime-asset-source-checkout", type=Path)
    parser.add_argument("--runtime-asset-dvc-workspace", type=Path)
    parser.add_argument("--runtime-asset-bundle", type=Path)
    parser.add_argument("--runtime-asset-data-dir", type=Path)
    parser.add_argument("--runtime-asset-map-id", type=int)


def enforce_runtime_asset_closure_from_args(
    args: argparse.Namespace, *, worldserver_config: Path,
) -> dict[str, Any]:
    manifest = getattr(args, "runtime_asset_closure_manifest", None)
    values = {
        "source_checkout": getattr(args, "runtime_asset_source_checkout", None),
        "dvc_workspace": getattr(args, "runtime_asset_dvc_workspace", None),
        "sealed_bundle": getattr(args, "runtime_asset_bundle", None),
        "scenario_map_id": getattr(args, "runtime_asset_map_id", None),
    }
    supplied = manifest is not None or any(value is not None for value in values.values())
    if not supplied:
        return {"required": False, "status": "runtime_asset_closure_not_requested"}
    missing = [name for name, value in {"manifest": manifest, **values}.items() if value is None]
    if missing:
        raise SystemExit("runtime_asset_closure_incomplete:root_arguments_missing:" + ",".join(missing))
    return require_runtime_asset_closure(
        manifest_path=manifest,
        source_checkout=values["source_checkout"],
        configured_data_dir=getattr(args, "runtime_asset_data_dir", None),
        dvc_workspace=values["dvc_workspace"],
        sealed_bundle=values["sealed_bundle"],
        worldserver_config=worldserver_config,
        scenario_map_id=values["scenario_map_id"],
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify one immutable runtime asset closure")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--source-checkout", type=Path, required=True)
    verify.add_argument("--config", type=Path, required=True)
    verify.add_argument("--data-dir", type=Path)
    verify.add_argument("--dvc-workspace", type=Path, required=True)
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--scenario-map-id", type=int, required=True)
    verify.add_argument("--previous-receipt", type=Path)
    verify.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    previous = None
    if args.previous_receipt:
        previous = load_json_strict(args.previous_receipt).get("snapshot")
    receipt = verify_runtime_asset_closure(
        manifest_path=args.manifest,
        source_checkout=args.source_checkout,
        configured_data_dir=args.data_dir,
        dvc_workspace=args.dvc_workspace,
        sealed_bundle=args.bundle,
        worldserver_config=args.config,
        scenario_map_id=args.scenario_map_id,
        previous_snapshot=previous,
    )
    _write_json(args.output, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
