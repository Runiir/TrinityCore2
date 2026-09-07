from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

from tools.raid_program.runtime_asset_safe_io import (
    SafePathError,
    absolute_path,
    read_regular_no_follow,
    require_directory_no_follow,
)


BINDING_SCHEMA = "cata_runtime_asset_closure_argument_binding_v1"
INPUT_MANIFEST_SCHEMA = "cata_runtime_asset_input_closure_manifest_v1"
ARGUMENTS = (
    ("runtime_asset_closure_manifest", "--runtime-asset-closure-manifest"),
    ("runtime_asset_source_checkout", "--runtime-asset-source-checkout"),
    ("runtime_asset_dvc_workspace", "--runtime-asset-dvc-workspace"),
    ("runtime_asset_bundle", "--runtime-asset-bundle"),
    ("runtime_asset_data_dir", "--runtime-asset-data-dir"),
    ("runtime_asset_map_id", "--runtime-asset-map-id"),
)
PATH_ARGUMENTS = frozenset(name for name, _flag in ARGUMENTS if name != "runtime_asset_map_id")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class RuntimeAssetClosureBindingError(ValueError):
    pass


class _DuplicateKeyError(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKeyError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _safe_relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeAssetClosureBindingError(f"{label}_path_missing")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise RuntimeAssetClosureBindingError(f"{label}_path_invalid")
    if "\\" in value or value != pure.as_posix():
        raise RuntimeAssetClosureBindingError(f"{label}_path_invalid")
    return value


def _canonical_absolute(value: object, label: str) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise RuntimeAssetClosureBindingError(f"{label}_path_missing")
    supplied = Path(value)
    canonical = absolute_path(supplied)
    if not supplied.is_absolute() or supplied != canonical:
        raise RuntimeAssetClosureBindingError(f"{label}_path_not_canonical_absolute")
    return canonical


def _read_json(path: Path, schema: str, label: str) -> tuple[dict[str, Any], str]:
    try:
        payload, _stat = read_regular_no_follow(path)
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except (SafePathError, OSError, UnicodeError, json.JSONDecodeError, _DuplicateKeyError) as error:
        raise RuntimeAssetClosureBindingError(f"{label}_invalid:{error}") from error
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise RuntimeAssetClosureBindingError(f"{label}_schema_invalid")
    return value, hashlib.sha256(payload).hexdigest()


def _require_input_only_manifest(manifest: Mapping[str, Any]) -> None:
    """Reject launch authorities whose identity depends on generated outputs."""

    classes = manifest.get("asset_classes")
    if not isinstance(classes, list):
        raise RuntimeAssetClosureBindingError("input_asset_classes_invalid")
    for asset_class in classes:
        if not isinstance(asset_class, dict):
            raise RuntimeAssetClosureBindingError("input_asset_class_invalid")
        roots = {asset_class.get("root")}
        map_contracts = asset_class.get("map_contracts")
        if isinstance(map_contracts, dict):
            roots.update(
                contract.get("root")
                for contract in map_contracts.values()
                if isinstance(contract, dict)
            )
        if "sealed-bundle" in roots:
            raise RuntimeAssetClosureBindingError(
                f"input_manifest_output_root_forbidden:{asset_class.get('id') or 'unnamed'}"
            )
    root_contract = manifest.get("root_contract")
    if isinstance(root_contract, dict) and "sealed-bundle" in root_contract:
        raise RuntimeAssetClosureBindingError(
            "input_manifest_output_root_contract_forbidden"
        )


def _materialize_input_manifest(
    manifest: Mapping[str, Any], *, dvc_workspace: Path,
) -> dict[str, Any]:
    """Resolve a hash-bound historical inventory into an input-only view."""

    result = dict(manifest)
    source = result.pop("asset_class_source", None)
    if source is None:
        _require_input_only_manifest(result)
        return result
    if "asset_classes" in result or not isinstance(source, dict) or set(source) != {
        "path", "sha256", "exclude_class_ids",
    }:
        raise RuntimeAssetClosureBindingError("input_asset_class_source_invalid")
    relative = _safe_relative(source.get("path"), "input_asset_class_source")
    expected_sha256 = source.get("sha256")
    if not isinstance(expected_sha256, str) or not SHA256_RE.fullmatch(expected_sha256):
        raise RuntimeAssetClosureBindingError("input_asset_class_source_sha256_invalid")
    historical, observed_sha256 = _read_json(
        dvc_workspace / relative,
        "cata_runtime_asset_closure_manifest_v1",
        "input_asset_class_source",
    )
    if observed_sha256 != expected_sha256:
        raise RuntimeAssetClosureBindingError("input_asset_class_source_sha256_mismatch")
    excluded = source.get("exclude_class_ids")
    if excluded != ["atomic_bundle"]:
        raise RuntimeAssetClosureBindingError("input_asset_class_exclusion_invalid")
    classes = historical.get("asset_classes")
    if not isinstance(classes, list) or not any(
        isinstance(row, dict) and row.get("id") == "atomic_bundle"
        for row in classes
    ):
        raise RuntimeAssetClosureBindingError("input_asset_class_source_invalid")
    result["asset_classes"] = [
        dict(row) for row in classes
        if isinstance(row, dict) and row.get("id") != "atomic_bundle"
    ]
    for field in ("dvc_provenance", "native_extraction_provenance"):
        if field in result or field not in historical:
            raise RuntimeAssetClosureBindingError(
                f"input_asset_class_source_field_invalid:{field}"
            )
        result[field] = historical[field]
    _require_input_only_manifest(result)
    return result


def _bound_authority(
    *, root: Path, binding: object, schema: str, label: str,
) -> dict[str, str]:
    if not isinstance(binding, dict) or set(binding) < {"path", "sha256"}:
        raise RuntimeAssetClosureBindingError(f"{label}_binding_invalid")
    relative = _safe_relative(binding.get("path"), label)
    expected_sha256 = binding.get("sha256")
    if not isinstance(expected_sha256, str) or not SHA256_RE.fullmatch(expected_sha256):
        raise RuntimeAssetClosureBindingError(f"{label}_sha256_invalid")
    _value, observed_sha256 = _read_json(root / relative, schema, label)
    if observed_sha256 != expected_sha256:
        raise RuntimeAssetClosureBindingError(f"{label}_sha256_mismatch")
    return {"path": str(root / relative), "sha256": observed_sha256}


def _data_dir_from_config(payload: bytes, config_path: Path) -> Path:
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise RuntimeAssetClosureBindingError("worldserver_config_invalid") from error
    values: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r'DataDir\s*=\s*(?:"([^"]+)"|([^#\s]+))\s*', line)
        if match:
            values.append(match.group(1) or match.group(2))
    if len(values) != 1:
        raise RuntimeAssetClosureBindingError(
            f"configured_DataDir_count:{len(values)}"
        )
    value = Path(values[0])
    if not value.is_absolute():
        value = config_path.parent / value
    return absolute_path(value)


def argument_values_from_namespace(
    args: argparse.Namespace, *, required: bool = True,
) -> dict[str, object] | None:
    values = {name: getattr(args, name, None) for name, _flag in ARGUMENTS}
    supplied = [name for name, value in values.items() if value is not None]
    if not supplied:
        if required:
            raise RuntimeAssetClosureBindingError("runtime_asset_closure_not_supplied")
        return None
    missing = [name for name, value in values.items() if value is None]
    if missing:
        raise RuntimeAssetClosureBindingError(
            "runtime_asset_closure_arguments_missing:" + ",".join(missing)
        )
    normalized: dict[str, object] = {}
    for name, value in values.items():
        if name in PATH_ARGUMENTS:
            normalized[name] = _canonical_absolute(value, name)
        elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RuntimeAssetClosureBindingError("runtime_asset_map_id_invalid")
        else:
            normalized[name] = value
    return normalized


def argument_argv(values: Mapping[str, object]) -> list[str]:
    missing = [name for name, _flag in ARGUMENTS if name not in values]
    if missing:
        raise RuntimeAssetClosureBindingError(
            "runtime_asset_closure_arguments_missing:" + ",".join(missing)
        )
    argv: list[str] = []
    for name, flag in ARGUMENTS:
        value = values[name]
        if name in PATH_ARGUMENTS:
            value = _canonical_absolute(value, name)
        elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RuntimeAssetClosureBindingError("runtime_asset_map_id_invalid")
        argv.extend([flag, str(value)])
    return argv


def argument_argv_from_namespace(args: argparse.Namespace) -> list[str]:
    values = argument_values_from_namespace(args, required=True)
    assert values is not None
    return argument_argv(values)


def build_binding(
    *, manifest_path: Path, source_checkout: Path, dvc_workspace: Path,
    sealed_bundle: Path, configured_data_dir: Path, worldserver_config: Path,
    scenario_map_id: int, config_payload: bytes | None = None,
    require_bundle: bool = True,
) -> dict[str, Any]:
    values: dict[str, object] = {
        "runtime_asset_closure_manifest": manifest_path,
        "runtime_asset_source_checkout": source_checkout,
        "runtime_asset_dvc_workspace": dvc_workspace,
        "runtime_asset_bundle": sealed_bundle,
        "runtime_asset_data_dir": configured_data_dir,
        "runtime_asset_map_id": scenario_map_id,
    }
    namespace = argparse.Namespace(**values)
    normalized = argument_values_from_namespace(namespace, required=True)
    assert normalized is not None
    manifest_path = normalized["runtime_asset_closure_manifest"]
    source_checkout = normalized["runtime_asset_source_checkout"]
    dvc_workspace = normalized["runtime_asset_dvc_workspace"]
    sealed_bundle = normalized["runtime_asset_bundle"]
    configured_data_dir = normalized["runtime_asset_data_dir"]
    scenario_map_id = normalized["runtime_asset_map_id"]
    config_path = _canonical_absolute(worldserver_config, "worldserver_config")
    assert isinstance(manifest_path, Path)
    assert isinstance(source_checkout, Path)
    assert isinstance(dvc_workspace, Path)
    assert isinstance(sealed_bundle, Path)
    assert isinstance(configured_data_dir, Path)
    assert isinstance(scenario_map_id, int)
    try:
        require_directory_no_follow(source_checkout)
        require_directory_no_follow(dvc_workspace)
        require_directory_no_follow(configured_data_dir)
        if require_bundle:
            require_directory_no_follow(sealed_bundle)
    except SafePathError as error:
        raise RuntimeAssetClosureBindingError(f"root_invalid:{error}") from error
    manifest, manifest_sha256 = _read_json(
        manifest_path, INPUT_MANIFEST_SCHEMA, "manifest",
    )
    manifest = _materialize_input_manifest(
        manifest, dvc_workspace=dvc_workspace,
    )
    audit = _bound_authority(
        root=dvc_workspace, binding=manifest.get("audit_authority"),
        schema="cata_runtime_asset_closure_audit_authority_v1",
        label="audit_authority",
    )
    inventory = _bound_authority(
        root=dvc_workspace,
        binding=manifest.get("native_data_inventory_authority"),
        schema="cata_runtime_asset_native_data_inventory_v1",
        label="native_data_inventory_authority",
    )
    extraction = manifest.get("native_extraction_provenance")
    if not isinstance(extraction, dict):
        raise RuntimeAssetClosureBindingError("native_extraction_provenance_binding_invalid")
    extraction_path = configured_data_dir / _safe_relative(
        extraction.get("path"), "native_extraction_provenance",
    )
    expected_extraction_sha256 = extraction.get("receipt_sha256")
    if not isinstance(expected_extraction_sha256, str) or not SHA256_RE.fullmatch(
        expected_extraction_sha256
    ):
        raise RuntimeAssetClosureBindingError("native_extraction_provenance_sha256_invalid")
    _receipt, extraction_sha256 = _read_json(
        extraction_path, "cata_client_asset_extraction_receipt_v1",
        "native_extraction_provenance",
    )
    if extraction_sha256 != expected_extraction_sha256:
        raise RuntimeAssetClosureBindingError(
            "native_extraction_provenance_sha256_mismatch"
        )
    if config_payload is None:
        try:
            config_payload, _stat = read_regular_no_follow(config_path)
        except (SafePathError, OSError) as error:
            raise RuntimeAssetClosureBindingError(
                f"worldserver_config_invalid:{error}"
            ) from error
    derived_data_dir = _data_dir_from_config(config_payload, config_path)
    if derived_data_dir != configured_data_dir:
        raise RuntimeAssetClosureBindingError("configured_DataDir_mismatch")
    return {
        "schema": BINDING_SCHEMA,
        "manifest": {"path": str(manifest_path), "sha256": manifest_sha256},
        "roots": {
            "source-checkout": str(source_checkout),
            "configured-DataDir": str(configured_data_dir),
            "dvc-workspace": str(dvc_workspace),
            "sealed-bundle": str(sealed_bundle),
        },
        "worldserver_config": str(config_path),
        "scenario_map_id": scenario_map_id,
        "audit_authority": audit,
        "native_data_inventory_authority": inventory,
        "native_extraction_provenance": {
            "path": str(extraction_path), "sha256": extraction_sha256,
        },
        "argv": argument_argv(normalized),
    }


def verify_binding(
    binding: object, *, expected_bundle: Path, expected_config: Path,
    config_payload: bytes | None = None, require_bundle: bool = True,
) -> dict[str, Any]:
    if not isinstance(binding, dict) or set(binding) != {
        "schema", "manifest", "roots", "worldserver_config",
        "scenario_map_id", "audit_authority",
        "native_data_inventory_authority", "native_extraction_provenance",
        "argv",
    } or binding.get("schema") != BINDING_SCHEMA:
        raise RuntimeAssetClosureBindingError("runtime_asset_closure_binding_invalid")
    roots = binding.get("roots")
    manifest = binding.get("manifest")
    if not isinstance(roots, dict) or not isinstance(manifest, dict):
        raise RuntimeAssetClosureBindingError("runtime_asset_closure_binding_invalid")
    expected_bundle = _canonical_absolute(expected_bundle, "expected_bundle")
    expected_config = _canonical_absolute(expected_config, "expected_config")
    if roots.get("sealed-bundle") != str(expected_bundle):
        raise RuntimeAssetClosureBindingError("sealed_bundle_identity_mismatch")
    if binding.get("worldserver_config") != str(expected_config):
        raise RuntimeAssetClosureBindingError("worldserver_config_identity_mismatch")
    rebuilt = build_binding(
        manifest_path=Path(str(manifest.get("path") or "")),
        source_checkout=Path(str(roots.get("source-checkout") or "")),
        dvc_workspace=Path(str(roots.get("dvc-workspace") or "")),
        sealed_bundle=expected_bundle,
        configured_data_dir=Path(str(roots.get("configured-DataDir") or "")),
        worldserver_config=expected_config,
        scenario_map_id=binding.get("scenario_map_id"),
        config_payload=config_payload,
        require_bundle=require_bundle,
    )
    if rebuilt != binding:
        raise RuntimeAssetClosureBindingError("runtime_asset_closure_binding_mismatch")
    return rebuilt


def argv_values(argv: Sequence[str]) -> dict[str, object]:
    values: dict[str, object] = {}
    for name, flag in ARGUMENTS:
        if argv.count(flag) != 1:
            raise RuntimeAssetClosureBindingError(
                f"runtime_asset_closure_argument_count:{flag}"
            )
        index = argv.index(flag)
        if index + 1 >= len(argv):
            raise RuntimeAssetClosureBindingError(
                f"runtime_asset_closure_argument_value_missing:{flag}"
            )
        raw = argv[index + 1]
        if name in PATH_ARGUMENTS:
            values[name] = _canonical_absolute(raw, name)
        else:
            try:
                values[name] = int(raw)
            except ValueError as error:
                raise RuntimeAssetClosureBindingError(
                    "runtime_asset_map_id_invalid"
                ) from error
    if argument_argv(values) != [
        token
        for name, flag in ARGUMENTS
        for token in (flag, str(values[name]))
    ]:
        raise RuntimeAssetClosureBindingError("runtime_asset_closure_arguments_invalid")
    return values
