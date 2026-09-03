from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

from tools.raid_program.runtime_asset_safe_io import (
    SafePathError,
    absolute_path,
    read_regular_no_follow,
    require_directory_no_follow,
    walk_inventory_no_follow,
)


ROOT_KEYS = (
    "source-checkout",
    "configured-DataDir",
    "dvc-workspace",
    "sealed-bundle",
)
ISSUE_KINDS = (
    "manifest_invalid",
    "audit_invalid",
    "inventory_authority_invalid",
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
    "path_drift",
)


class DuplicateKeyError(ValueError):
    pass


class ManifestError(ValueError):
    pass


class AuthorityError(ValueError):
    def __init__(self, kind: str, detail: str) -> None:
        self.kind = kind
        self.detail = detail
        super().__init__(detail)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _normal_path(path: Path) -> Path:
    return absolute_path(path)


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError("path_missing")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ManifestError(f"path_traversal:{value}")
    if "\\" in value or value != pure.as_posix():
        raise ManifestError(f"path_invalid:{value}")
    return value


def _read_regular_no_follow(path: Path) -> tuple[bytes, Any]:
    return read_regular_no_follow(path)


def load_json_strict(path: Path) -> dict[str, Any]:
    path = _normal_path(path)
    try:
        payload, _ = _read_regular_no_follow(path)
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except (SafePathError, OSError, UnicodeError, json.JSONDecodeError, DuplicateKeyError) as error:
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
    target = root / relative
    try:
        payload, read_stat = _read_regular_no_follow(target)
    except SafePathError as error:
        return None, {"kind": error.kind, "path": relative, "detail": error.detail}
    return {
        "path": relative,
        "type": "file",
        "mode": f"{read_stat.st_mode & 0o7777:04o}",
        "size_bytes": read_stat.st_size,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }, None


def _walk_files(root: Path, relative: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        return walk_inventory_no_follow(root, relative, include_directories=True), []
    except SafePathError as error:
        try:
            issue_path = error.path.relative_to(_normal_path(root)).as_posix()
        except ValueError:
            issue_path = relative
        return [], [{"kind": error.kind, "path": issue_path, "detail": error.detail}]


def _inventory(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [dict(row) for row in sorted(records, key=lambda row: str(row["path"]))]
    files = [row for row in normalized if row.get("type", "file") == "file"]
    directories = [row for row in normalized if row.get("type") == "directory"]
    return {
        "entry_count": len(normalized),
        "file_count": len(files),
        "directory_count": len(directories),
        "size_bytes": sum(int(row["size_bytes"]) for row in files),
        "path_set_sha256": canonical_sha256([row["path"] for row in normalized]),
        "inventory_sha256": canonical_sha256(normalized),
    }


def _strict_json_bytes(payload: bytes, *, schema: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError, DuplicateKeyError) as error:
        raise ManifestError(str(error)) from error
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise ManifestError(f"schema_invalid:{schema}")
    return value


def _load_bound_json(path: Path, expected_sha256: object, *, schema: str) -> tuple[dict[str, Any], str]:
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ManifestError("authority_sha256_invalid")
    payload, _ = _read_regular_no_follow(path)
    observed_sha256 = hashlib.sha256(payload).hexdigest()
    if observed_sha256 != expected_sha256:
        raise ManifestError(
            f"authority_sha256_mismatch:{expected_sha256}:{observed_sha256}"
        )
    return _strict_json_bytes(payload, schema=schema), observed_sha256


def _validate_inventory_records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ManifestError("inventory_records_invalid")
    records: list[dict[str, Any]] = []
    previous = ""
    for item in value:
        if not isinstance(item, dict):
            raise ManifestError("inventory_record_invalid")
        relative = _safe_relative(item.get("path"))
        if relative <= previous:
            raise ManifestError(f"inventory_record_order_invalid:{relative}")
        previous = relative
        member_type = item.get("type")
        if member_type not in {"file", "directory"}:
            raise ManifestError(f"inventory_record_type_invalid:{relative}")
        if not re.fullmatch(r"[0-7]{4}", str(item.get("mode") or "")):
            raise ManifestError(f"inventory_record_mode_invalid:{relative}")
        if not isinstance(item.get("size_bytes"), int) or int(item["size_bytes"]) < 0:
            raise ManifestError(f"inventory_record_size_invalid:{relative}")
        expected_keys = {"path", "type", "mode", "size_bytes"}
        if member_type == "file":
            expected_keys.add("sha256")
            if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256") or "")):
                raise ManifestError(f"inventory_record_sha256_invalid:{relative}")
        if set(item) != expected_keys:
            raise ManifestError(f"inventory_record_fields_invalid:{relative}")
        records.append(dict(item))
    return records


def build_native_inventory_authority(
    *, data_dir: Path, source_audit_sha256: str,
    audit_source_inventory_sha256: str, audit_vmaps_inventory_sha256: str,
    receipt_relative_path: str,
) -> dict[str, Any]:
    records = walk_inventory_no_follow(
        data_dir, ".", include_directories=True,
        excluded_paths=[_safe_relative(receipt_relative_path)],
    )
    vmaps = [row for row in records if str(row["path"]).startswith("vmaps/")]
    return {
        "schema": "cata_runtime_asset_native_data_inventory_v1",
        "source_audit_sha256": source_audit_sha256,
        "canonical_audit_inventory_sha256": audit_source_inventory_sha256,
        "record_inventory": _inventory(records),
        "subsets": {
            "vmaps": {
                "path": "vmaps",
                "audit_inventory_sha256": audit_vmaps_inventory_sha256,
                "record_inventory": _inventory(vmaps),
            }
        },
        "records": records,
    }


def build_audit_authority(
    *, manifest: Mapping[str, Any], source_audit_path: Path,
    source_audit_sha256: str, scenario_map_id: int,
) -> dict[str, Any]:
    audit_bytes, _ = _read_regular_no_follow(source_audit_path)
    if hashlib.sha256(audit_bytes).hexdigest() != source_audit_sha256:
        raise ManifestError("source_audit_sha256_mismatch")
    audit = _strict_json_bytes(
        audit_bytes, schema="cata_raid_immutable_runtime_asset_closure_audit_v1",
    )
    audit_classes = audit.get("closure_classes")
    if not isinstance(audit_classes, list):
        raise ManifestError("source_audit_classes_invalid")
    by_digest: dict[str, list[dict[str, Any]]] = {}
    for row in audit_classes:
        if isinstance(row, dict):
            digest = row.get("inventory_sha256") or row.get("source_inventory_sha256")
            by_digest.setdefault(str(digest or ""), []).append(row)
    classes: list[dict[str, Any]] = []
    manifest_classes = manifest.get("asset_classes")
    if not isinstance(manifest_classes, list):
        raise ManifestError("asset_classes_invalid")
    for raw_class in manifest_classes:
        if not isinstance(raw_class, dict):
            raise ManifestError("asset_class_not_object")
        values = _expected_map_values(raw_class, scenario_map_id)
        digest = str(values.get("audit_inventory_sha256") or "")
        matches = by_digest.get(digest, [])
        if len(matches) != 1:
            raise ManifestError(f"source_audit_class_digest_invalid:{values.get('id')}")
        source = matches[0]
        expected_inventory = values.get("expected_inventory")
        count = expected_inventory.get("file_count") if isinstance(expected_inventory, dict) else None
        classes.append({
            "id": values.get("id"),
            "source_audit_class_id": source.get("id"),
            "consumer": values.get("consumer"),
            "audience": values.get("audience"),
            "root": values.get("root"),
            "rule": values.get("rule"),
            "count": count,
            "audit_inventory_sha256": digest,
        })
    source_inventory = audit.get("full_data_tree_inventory", {}).get("source", {})
    return {
        "schema": "cata_runtime_asset_closure_audit_authority_v1",
        "source_audit": {
            "path": str(_normal_path(source_audit_path)),
            "sha256": source_audit_sha256,
            "schema": audit.get("schema"),
            "source_inventory_sha256": source_inventory.get("inventory_sha256"),
            "source_entry_count": source_inventory.get("entries"),
        },
        "classes": classes,
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
    if expected.get("type", "file") != observed.get("type"):
        issues.append({
            "kind": "type_mismatch", "class_id": class_id,
            "path": observed["path"], "expected": expected.get("type", "file"),
            "observed": observed.get("type"),
        })
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
    inventory_authority: Mapping[str, Any],
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
    raw_expected_files = values.get("expected_files", [])
    if not isinstance(raw_expected_files, list):
        raise ManifestError(f"expected_files_invalid:{class_id}")
    expected_files = list(raw_expected_files)
    inventory_subset = values.get("inventory_subset")
    if inventory_subset is not None:
        if rule != "complete-directory" or not isinstance(inventory_subset, str):
            raise ManifestError(f"inventory_subset_invalid:{class_id}")
        subset = inventory_authority.get("subsets", {}).get(inventory_subset)
        if not isinstance(subset, dict):
            raise ManifestError(f"inventory_subset_missing:{class_id}:{inventory_subset}")
        records = inventory_authority.get("records")
        if not isinstance(records, list):
            raise ManifestError("inventory_authority_records_invalid")
        base_prefix = f"{_safe_relative(values.get('path'))}/"
        expected_files = [
            dict(row) for row in records
            if isinstance(row, dict) and str(row.get("path", "")).startswith(base_prefix)
        ]
        if _inventory(expected_files) != subset.get("record_inventory"):
            raise ManifestError(f"inventory_subset_digest_invalid:{class_id}")
        if subset.get("audit_inventory_sha256") != values.get("audit_inventory_sha256"):
            raise ManifestError(f"inventory_subset_audit_digest_invalid:{class_id}")
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


def _manifest_authority_rows(
    manifest: Mapping[str, Any], scenario_map_id: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    classes = manifest.get("asset_classes")
    if not isinstance(classes, list):
        raise ManifestError("asset_classes_invalid")
    for raw_class in classes:
        if not isinstance(raw_class, dict):
            raise ManifestError("asset_class_not_object")
        values = _expected_map_values(raw_class, scenario_map_id)
        expected_inventory = values.get("expected_inventory")
        count = expected_inventory.get("file_count") if isinstance(expected_inventory, dict) else None
        rows.append({
            "id": values.get("id"),
            "consumer": values.get("consumer"),
            "audience": values.get("audience"),
            "root": values.get("root"),
            "rule": values.get("rule"),
            "count": count,
            "audit_inventory_sha256": values.get("audit_inventory_sha256"),
        })
    return rows


def _verify_audit_authority(
    manifest: Mapping[str, Any], dvc_workspace: Path, scenario_map_id: int,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    binding = manifest.get("audit_authority")
    if not isinstance(binding, dict):
        raise AuthorityError("audit_invalid", "audit_authority_missing")
    try:
        relative = _safe_relative(binding.get("path"))
        authority, authority_sha256 = _load_bound_json(
            dvc_workspace / relative, binding.get("sha256"),
            schema="cata_runtime_asset_closure_audit_authority_v1",
        )
        if set(authority) != {"schema", "source_audit", "classes"}:
            raise ManifestError("audit_authority_fields_invalid")
        source_binding = authority.get("source_audit")
        if not isinstance(source_binding, dict):
            raise ManifestError("source_audit_binding_missing")
        if set(source_binding) != {
            "path", "sha256", "schema", "source_inventory_sha256",
            "source_entry_count",
        }:
            raise ManifestError("source_audit_binding_fields_invalid")
        source_path = Path(str(source_binding.get("path") or ""))
        if not source_path.is_absolute():
            raise ManifestError("source_audit_path_not_absolute")
        source_audit, _ = _load_bound_json(
            source_path, source_binding.get("sha256"),
            schema="cata_raid_immutable_runtime_asset_closure_audit_v1",
        )
        if source_binding.get("schema") != source_audit.get("schema"):
            raise ManifestError("source_audit_schema_disagreement")
        source_inventory = source_audit.get("full_data_tree_inventory", {}).get("source")
        if not isinstance(source_inventory, dict):
            raise ManifestError("source_audit_inventory_missing")
        for field, observed in (
            ("source_inventory_sha256", source_inventory.get("inventory_sha256")),
            ("source_entry_count", source_inventory.get("entries")),
        ):
            if source_binding.get(field) != observed:
                raise ManifestError(f"source_audit_{field}_disagreement")
        authority_rows = authority.get("classes")
        if not isinstance(authority_rows, list):
            raise ManifestError("audit_authority_classes_invalid")
        by_id = {
            str(row.get("id")): row for row in authority_rows if isinstance(row, dict)
        }
        if any(
            not isinstance(row, dict) or set(row) != {
                "id", "source_audit_class_id", "consumer", "audience", "root",
                "rule", "count", "audit_inventory_sha256",
            }
            for row in authority_rows
        ):
            raise ManifestError("audit_authority_class_fields_invalid")
        expected_rows = _manifest_authority_rows(manifest, scenario_map_id)
        if len(by_id) != len(authority_rows) or set(by_id) != {
            str(row["id"]) for row in expected_rows
        }:
            raise ManifestError("audit_authority_class_ids_disagree")
        source_classes = source_audit.get("closure_classes")
        if not isinstance(source_classes, list):
            raise ManifestError("source_audit_classes_invalid")
        source_by_id = {
            str(row.get("id")): row for row in source_classes if isinstance(row, dict)
        }
        for expected in expected_rows:
            authority_row = by_id[str(expected["id"])]
            for field, value in expected.items():
                if authority_row.get(field) != value:
                    raise ManifestError(
                        f"audit_authority_class_disagreement:{expected['id']}:{field}"
                    )
            source = source_by_id.get(str(authority_row.get("source_audit_class_id")))
            if not isinstance(source, dict):
                raise ManifestError(f"source_audit_class_missing:{expected['id']}")
            source_digest = source.get("inventory_sha256") or source.get(
                "source_inventory_sha256"
            )
            if source_digest != expected["audit_inventory_sha256"]:
                raise ManifestError(f"source_audit_class_digest_disagree:{expected['id']}")
            if source.get("count") != expected["count"]:
                raise ManifestError(f"source_audit_class_count_disagree:{expected['id']}")
        return authority, source_audit, authority_sha256
    except (ManifestError, SafePathError, OSError) as error:
        raise AuthorityError("audit_invalid", str(error)) from error


def _verify_inventory_authority(
    manifest: Mapping[str, Any], dvc_workspace: Path,
    audit_authority: Mapping[str, Any], audit_authority_sha256: str,
) -> tuple[dict[str, Any], str]:
    binding = manifest.get("native_data_inventory_authority")
    if not isinstance(binding, dict):
        raise AuthorityError("inventory_authority_invalid", "inventory_authority_missing")
    try:
        relative = _safe_relative(binding.get("path"))
        authority, authority_sha256 = _load_bound_json(
            dvc_workspace / relative, binding.get("sha256"),
            schema="cata_runtime_asset_native_data_inventory_v1",
        )
        if set(authority) != {
            "schema", "source_audit_sha256", "canonical_audit_inventory_sha256",
            "record_inventory", "subsets", "records",
        }:
            raise ManifestError("inventory_authority_fields_invalid")
        records = _validate_inventory_records(authority.get("records"))
        if authority.get("record_inventory") != _inventory(records):
            raise ManifestError("inventory_authority_record_digest_disagree")
        source_audit = audit_authority.get("source_audit", {})
        if authority.get("source_audit_sha256") != source_audit.get("sha256"):
            raise ManifestError("inventory_authority_source_audit_disagree")
        if authority.get("canonical_audit_inventory_sha256") != source_audit.get(
            "source_inventory_sha256"
        ):
            raise ManifestError("inventory_authority_canonical_audit_digest_disagree")
        if binding.get("canonical_audit_inventory_sha256") != authority.get(
            "canonical_audit_inventory_sha256"
        ):
            raise ManifestError("manifest_inventory_audit_digest_disagree")
        if binding.get("audit_authority_sha256") != audit_authority_sha256:
            raise ManifestError("manifest_inventory_audit_authority_disagree")
        subsets = authority.get("subsets")
        if not isinstance(subsets, dict):
            raise ManifestError("inventory_authority_subsets_invalid")
        for subset_id, subset in subsets.items():
            if not isinstance(subset_id, str) or not isinstance(subset, dict):
                raise ManifestError("inventory_authority_subset_invalid")
            if set(subset) != {
                "path", "audit_inventory_sha256", "record_inventory",
            }:
                raise ManifestError(f"inventory_authority_subset_fields_invalid:{subset_id}")
            prefix = f"{_safe_relative(subset.get('path'))}/"
            subset_records = [row for row in records if str(row["path"]).startswith(prefix)]
            if subset.get("record_inventory") != _inventory(subset_records):
                raise ManifestError(f"inventory_authority_subset_digest_disagree:{subset_id}")
        return authority, authority_sha256
    except (ManifestError, SafePathError, OSError) as error:
        raise AuthorityError("inventory_authority_invalid", str(error)) from error


def produce_extraction_receipt(
    *, data_dir: Path, inventory_authority_path: Path,
    receipt_relative_path: str, client_identity: Mapping[str, Any],
    extractor_identity: Mapping[str, Any], creation_command_inputs: Sequence[str],
) -> dict[str, Any]:
    relative = _safe_relative(receipt_relative_path)
    authority_bytes, _ = _read_regular_no_follow(inventory_authority_path)
    authority_sha256 = hashlib.sha256(authority_bytes).hexdigest()
    authority = _strict_json_bytes(
        authority_bytes, schema="cata_runtime_asset_native_data_inventory_v1",
    )
    expected = _validate_inventory_records(authority.get("records"))
    observed = walk_inventory_no_follow(
        data_dir, ".", include_directories=True, excluded_paths=[relative],
    )
    if observed != expected:
        raise ManifestError("extraction_receipt_inventory_mismatch")
    if not client_identity or not extractor_identity or not creation_command_inputs:
        raise ManifestError("extraction_receipt_identity_missing")
    return {
        "schema": "cata_client_asset_extraction_receipt_v1",
        "inventory_authority_sha256": authority_sha256,
        "canonical_audit_inventory_sha256": authority.get(
            "canonical_audit_inventory_sha256"
        ),
        "data_inventory": _inventory(observed),
        "client_identity": dict(client_identity),
        "extractor_identity": dict(extractor_identity),
        "creation_command_inputs": list(creation_command_inputs),
    }


def _validate_extraction_receipt(payload: Mapping[str, Any]) -> None:
    expected_keys = {
        "schema", "inventory_authority_sha256",
        "canonical_audit_inventory_sha256", "data_inventory",
        "client_identity", "extractor_identity", "creation_command_inputs",
    }
    if set(payload) != expected_keys:
        raise ManifestError("extraction_receipt_fields_invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("inventory_authority_sha256") or "")):
        raise ManifestError("extraction_receipt_inventory_authority_invalid")
    if not re.fullmatch(
        r"[0-9a-f]{64}", str(payload.get("canonical_audit_inventory_sha256") or ""),
    ):
        raise ManifestError("extraction_receipt_audit_inventory_invalid")
    inventory = payload.get("data_inventory")
    if not isinstance(inventory, dict) or set(inventory) != {
        "entry_count", "file_count", "directory_count", "size_bytes",
        "path_set_sha256", "inventory_sha256",
    }:
        raise ManifestError("extraction_receipt_data_inventory_invalid")
    if not isinstance(payload.get("client_identity"), dict) or not payload["client_identity"]:
        raise ManifestError("extraction_receipt_client_identity_invalid")
    if not isinstance(payload.get("extractor_identity"), dict) or not payload["extractor_identity"]:
        raise ManifestError("extraction_receipt_extractor_identity_invalid")
    command = payload.get("creation_command_inputs")
    if not isinstance(command, list) or not command or not all(
        isinstance(item, str) and item for item in command
    ):
        raise ManifestError("extraction_receipt_command_inputs_invalid")


def _verify_extraction_provenance(
    manifest: Mapping[str, Any], roots: Mapping[str, Path],
    inventory_authority: Mapping[str, Any], inventory_authority_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    requirement = manifest.get("native_extraction_provenance")
    if not isinstance(requirement, dict):
        raise ManifestError("native_extraction_provenance_invalid")
    relative = _safe_relative(requirement.get("path"))
    target = roots["configured-DataDir"] / relative
    pinned_sha256 = requirement.get("receipt_sha256")
    if pinned_sha256 is None:
        return [{
            "kind": "provenance_missing", "class_id": "native_extraction_provenance",
            "path": relative, "root": "configured-DataDir",
            "detail": "receipt_sha256_not_pinned",
        }], None
    try:
        payload, observed_sha256 = _load_bound_json(
            target, pinned_sha256, schema="cata_client_asset_extraction_receipt_v1",
        )
        _validate_extraction_receipt(payload)
    except (ManifestError, SafePathError, OSError) as error:
        kind = "provenance_missing" if isinstance(error, SafePathError) and error.kind == "missing" else "provenance_invalid"
        return [{
            "kind": kind, "class_id": "native_extraction_provenance",
            "path": relative, "root": "configured-DataDir", "detail": str(error),
        }], None
    issues: list[dict[str, Any]] = []
    for field, expected in (
        ("inventory_authority_sha256", inventory_authority_sha256),
        ("canonical_audit_inventory_sha256", inventory_authority.get("canonical_audit_inventory_sha256")),
        ("client_identity", requirement.get("client_identity")),
        ("extractor_identity", requirement.get("extractor_identity")),
        ("creation_command_inputs", requirement.get("creation_command_inputs")),
    ):
        if payload.get(field) != expected:
            issues.append({
                "kind": "provenance_invalid", "class_id": "native_extraction_provenance",
                "path": relative, "root": "configured-DataDir", "field": field,
                "expected": expected, "observed": payload.get(field),
            })
    expected_records = _validate_inventory_records(inventory_authority.get("records"))
    try:
        observed_records = walk_inventory_no_follow(
            roots["configured-DataDir"], ".", include_directories=True,
            excluded_paths=[relative],
        )
    except SafePathError as error:
        issues.append({
            "kind": "provenance_invalid", "class_id": "native_extraction_provenance",
            "path": relative, "root": "configured-DataDir", "field": "data_inventory",
            "detail": str(error),
        })
        return issues, {**payload, "receipt_sha256": observed_sha256}
    if observed_records != expected_records or payload.get("data_inventory") != _inventory(observed_records):
        issues.append({
            "kind": "provenance_invalid", "class_id": "native_extraction_provenance",
            "path": relative, "root": "configured-DataDir", "field": "data_inventory",
            "expected": _inventory(expected_records), "observed": _inventory(observed_records),
        })
    return issues, {**payload, "receipt_sha256": observed_sha256}


def verify_runtime_asset_closure(
    *, manifest_path: Path, source_checkout: Path, configured_data_dir: Path | None,
    dvc_workspace: Path, sealed_bundle: Path, worldserver_config: Path,
    scenario_map_id: int, previous_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_path = _normal_path(manifest_path)
    manifest_sha256: str | None = None
    try:
        manifest_bytes, _ = _read_regular_no_follow(manifest_path)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        manifest = _strict_json_bytes(
            manifest_bytes, schema="cata_runtime_asset_closure_manifest_v1",
        )
        derived_data_dir = data_dir_from_worldserver_config(worldserver_config)
    except (ManifestError, SafePathError, OSError) as error:
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
            require_directory_no_follow(roots[key])
        except SafePathError as error:
            issues.append({
                "kind": error.kind, "root": key, "path": ".", "detail": error.detail,
            })
    if issues:
        issue_counts = {
            kind: sum(issue.get("kind") == kind for issue in issues)
            for kind in ISSUE_KINDS if any(issue.get("kind") == kind for issue in issues)
        }
        return {
            "schema": "cata_runtime_asset_closure_receipt_v1",
            "complete": False,
            "status": "runtime_asset_closure_incomplete",
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "roots": {key: str(value) for key, value in roots.items()},
            "issues": issues,
            "issue_counts": issue_counts,
            "snapshot": {},
        }
    try:
        audit_authority, source_audit, audit_authority_sha256 = _verify_audit_authority(
            manifest, roots["dvc-workspace"], scenario_map_id,
        )
        inventory_authority, inventory_authority_sha256 = _verify_inventory_authority(
            manifest, roots["dvc-workspace"], audit_authority,
            audit_authority_sha256,
        )
    except AuthorityError as error:
        return {
            "schema": "cata_runtime_asset_closure_receipt_v1",
            "complete": False,
            "status": "runtime_asset_closure_incomplete",
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "roots": {key: str(value) for key, value in roots.items()},
            "issues": [{"kind": error.kind, "detail": error.detail}],
            "issue_counts": {error.kind: 1},
            "snapshot": {},
        }
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
                asset_class, roots, scenario_map_id, inventory_authority,
            )
            class_results.append(result)
            issues.extend(class_issues)
            snapshot.update(class_snapshot)
        issues.extend(_verify_dvc_provenance(manifest, roots))
        provenance_issues, provenance = _verify_extraction_provenance(
            manifest, roots, inventory_authority, inventory_authority_sha256,
        )
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
        "audit_authority": {
            "path": manifest["audit_authority"]["path"],
            "sha256": audit_authority_sha256,
            "source_audit_sha256": audit_authority["source_audit"]["sha256"],
            "source_audit_schema": source_audit["schema"],
        },
        "native_data_inventory_authority": {
            "path": manifest["native_data_inventory_authority"]["path"],
            "sha256": inventory_authority_sha256,
            "record_inventory": inventory_authority["record_inventory"],
        },
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
