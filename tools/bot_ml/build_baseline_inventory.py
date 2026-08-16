from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

try:
    from .build_validation_provisioning import load_config as load_validation_provisioning_config
    from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
except ImportError:
    from build_validation_provisioning import load_config as load_validation_provisioning_config
    from extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url


REPO_ROOT = Path(__file__).resolve().parents[2]
DVC_MD5 = re.compile(r"^[0-9a-f]{32}(?:\.dir)?$")
SENSITIVE_UNTRACKED_PATH = re.compile(
    r"(?:^|[._/-])(?:\.env|config\.local|credentials?|passwords?|secrets?|tokens?|private[_-]?keys?|databaseinfo|database_info)(?:$|[._/-])|\.(?:conf|ini|key|pem|p12|pfx)$",
    re.IGNORECASE,
)
REQUIRED_TEMPORAL_STATES = frozenset({"current_diagnostic", "historical", "superseded", "unusable"})
REQUIRED_ACCEPTANCE_CONTRACT = {
    "hard_floor_ratio": 0.75,
    "optimization_target_ratio": 0.80,
    "single_target_scored_window_seconds": 300,
    "single_target_window_tolerance_seconds": 5,
    "aoe_calibration": "separate_mode_not_mixed_with_single_target",
    "individual_target_floor_enforced": True,
    "healer_qualification": "deterministic_controlled_party_damage",
    "stonecore_certification": "strict_uninterrupted_current_manifest_full_clear",
    "diagnostic_segments_certify_stonecore": False,
    "runtime_rotation_authority": "explicit_sql_rule_profiles",
    "generic_ml_policy": "offline_shadow_only",
    "concurrency_before_pre_concurrency_gate": "prohibited",
}
OUTPUT_RELATIVE_PATH = "dataset/baseline_inventory"
BUNDLE_MEMBER_NAMES = ("identity_snapshot.json", "artifact_classification.json", "reconciliation_report.json", "manifest.json")


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_dvc_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("unsafe DVC pointer path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) in {".", ""}:
        raise ValueError("unsafe DVC pointer path")
    return value


def parse_dvc_pointer(path: Path, *, allow_unusable_checksum: bool = False) -> dict[str, Any]:
    """Parse one DVC pointer; legacy malformed checksums are allowed only as unusable evidence."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read DVC pointer {path}") from exc
    if not isinstance(document, dict) or set(document) != {"outs"} or not isinstance(document["outs"], list) or len(document["outs"]) != 1:
        raise ValueError(f"malformed DVC pointer {path}")
    output = document["outs"][0]
    if not isinstance(output, dict) or set(output) - {"md5", "size", "nfiles", "hash", "path"}:
        raise ValueError(f"malformed DVC pointer {path}")
    checksum = output.get("md5")
    checksum_usable = isinstance(checksum, str) and DVC_MD5.fullmatch(checksum)
    checksum_recordable = allow_unusable_checksum and isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]+(?:\.dir)?", checksum)
    if not (checksum_usable or checksum_recordable) or output.get("hash") != "md5":
        raise ValueError(f"malformed DVC pointer {path}")
    pointer_path = _safe_dvc_path(output.get("path"))
    for name in ("size", "nfiles"):
        if name in output and (isinstance(output[name], bool) or not isinstance(output[name], int) or output[name] < 0):
            raise ValueError(f"malformed DVC pointer {path}")
    if checksum.endswith(".dir") and "nfiles" not in output:
        raise ValueError(f"malformed DVC pointer {path}")
    return {"schema": "dvc_pointer_v1", "md5": checksum, "path": pointer_path, "size": output.get("size"), "nfiles": output.get("nfiles")}


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def directory_identity(path: Path) -> tuple[str, int, int]:
    """Hash a directory structurally; hashes and paths, never its payload, are emitted."""
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    for candidate in sorted(path.rglob("*"), key=lambda item: str(item.relative_to(path))):
        relative = str(candidate.relative_to(path))
        metadata = candidate.lstat()
        if stat.S_ISREG(metadata.st_mode):
            byte_count = metadata.st_size
            total_bytes += byte_count
            rows.append({"path": relative, "type": "file", "bytes": byte_count, "sha256": sha256_file(candidate)})
        elif stat.S_ISLNK(metadata.st_mode):
            rows.append({"path": relative, "type": "symlink", "sha256": hashlib.sha256(os.fsencode(os.readlink(candidate))).hexdigest()})
        elif not stat.S_ISDIR(metadata.st_mode):
            rows.append({"path": relative, "type": "unsupported"})
    return canonical_hash(rows), total_bytes, len(rows)


def load_dvc_pointer_inventory(path: Path) -> dict[str, dict[str, Any]]:
    """Load checked-in identities and classifications for remote evidence pointers."""
    document = load_json(path)
    entries = document.get("pointers")
    if document.get("schema") != "baseline_dvc_pointer_inventory_v2" or not isinstance(entries, list) or not entries:
        raise ValueError("DVC pointer inventory must contain pointer records")
    indexed: dict[str, dict[str, Any]] = {}
    pointer_paths: set[str] = set()
    for entry in entries:
        required = {"artifact_id", "artifact_class", "temporal_state", "pointer_path", "pointer"}
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValueError("malformed DVC pointer inventory record")
        artifact_id = entry["artifact_id"]
        if not isinstance(artifact_id, str) or not artifact_id or artifact_id in indexed:
            raise ValueError("DVC pointer inventory IDs must be unique strings")
        if entry["artifact_class"] not in {"calibration_diagnostic", "calibration_evidence", "stonecore_evidence"}:
            raise ValueError("DVC pointer inventory artifact class is invalid")
        if entry["temporal_state"] not in REQUIRED_TEMPORAL_STATES - {"current_diagnostic"}:
            raise ValueError("remote evidence cannot be classified as current diagnostic")
        pointer_path = _safe_dvc_path(entry["pointer_path"])
        if pointer_path in pointer_paths:
            raise ValueError("DVC pointer inventory paths must be unique")
        pointer_paths.add(pointer_path)
        pointer = entry["pointer"]
        if not isinstance(pointer, dict) or set(pointer) != {"schema", "md5", "path", "size", "nfiles"}:
            raise ValueError("malformed DVC pointer inventory identity")
        checksum = pointer.get("md5")
        checksum_usable = isinstance(checksum, str) and DVC_MD5.fullmatch(checksum)
        checksum_recordable = entry["temporal_state"] == "unusable" and isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]+(?:\.dir)?", checksum)
        if pointer.get("schema") != "dvc_pointer_v1" or not (checksum_usable or checksum_recordable):
            raise ValueError("malformed DVC pointer inventory identity")
        if _safe_dvc_path(pointer.get("path")) != Path(pointer_path).with_suffix("").name:
            raise ValueError("DVC pointer inventory path does not match its pointer")
        for name in ("size", "nfiles"):
            if pointer[name] is not None and (isinstance(pointer[name], bool) or not isinstance(pointer[name], int) or pointer[name] < 0):
                raise ValueError("malformed DVC pointer inventory identity")
        if pointer["md5"].endswith(".dir") != (pointer["nfiles"] is not None):
            raise ValueError("malformed DVC pointer inventory identity")
        indexed[artifact_id] = {
            "artifact_class": entry["artifact_class"],
            "temporal_state": entry["temporal_state"],
            "pointer_path": pointer_path,
            "pointer": pointer,
        }
    return indexed


def classify_declared_artifact(declaration: dict[str, Any], root: Path, pointer_inventory: dict[str, dict[str, Any]]) -> dict[str, Any]:
    logical = root / declaration["path"]
    pointer = logical.with_name(f"{logical.name}.dvc")
    row: dict[str, Any] = {
        "artifact_id": declaration["artifact_id"],
        "artifact_class": declaration["artifact_class"],
        "path": declaration["path"],
        "temporal_state": declaration["temporal_state"],
    }
    expected = pointer_inventory.get(declaration["artifact_id"])
    if expected is not None:
        expected_path = _safe_dvc_path(f"{declaration['path']}.dvc")
        if expected["pointer_path"] != expected_path:
            raise ValueError("DVC pointer inventory record does not match the declared artifact")
        if not pointer.is_file() or parse_dvc_pointer(pointer) != expected["pointer"]:
            raise ValueError("DVC pointer differs from its checked-in identity inventory")
        row["dvc_pointer"] = expected["pointer"]
        row["availability"] = "materialized_unverified" if logical.exists() else "remote_only_unverified"
        row["reason_codes"] = ["artifact_remote_only_unverified"]
        return row
    if logical.is_file():
        row.update({"availability": "available", "content_sha256": sha256_file(logical), "byte_count": logical.stat().st_size})
    elif logical.is_dir():
        content_hash, byte_count, entry_count = directory_identity(logical)
        row.update({"availability": "available", "content_sha256": content_hash, "byte_count": byte_count, "entry_count": entry_count})
    elif pointer.is_file():
        row.update({"availability": "malformed_dvc_pointer", "reason_codes": ["artifact_missing"]})
    else:
        row.update({"availability": "missing", "reason_codes": ["artifact_missing"]})
    return row


def classify_pointer_artifact(artifact_id: str, entry: dict[str, Any], root: Path) -> dict[str, Any]:
    pointer_path = root / entry["pointer_path"]
    if not pointer_path.is_file() or parse_dvc_pointer(pointer_path, allow_unusable_checksum=entry["temporal_state"] == "unusable") != entry["pointer"]:
        raise ValueError("DVC pointer differs from its checked-in identity inventory")
    logical = pointer_path.with_suffix("")
    return {
        "artifact_id": artifact_id,
        "artifact_class": entry["artifact_class"],
        "path": str(logical.relative_to(root)),
        "temporal_state": entry["temporal_state"],
        "dvc_pointer": entry["pointer"],
        "availability": "materialized_unverified" if logical.exists() else "remote_only_unverified",
        "reason_codes": ["artifact_remote_only_unverified"],
    }


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)


def git_identity(repo: Path) -> dict[str, Any]:
    """Bind branch and relevant dirty state while excluding DVC/output cycles."""
    pathspec = (
        "--", ".", ":(exclude)dvc.lock", f":(exclude){OUTPUT_RELATIVE_PATH}",
        ":(exclude)experiments/configs/all_spec_stonecore_program_status_v1.json",
        ":(exclude)artifacts/all_spec_program",
    )
    try:
        head = _git(repo, "rev-parse", "HEAD").decode().strip()
        branch = _git(repo, "branch", "--show-current").decode().strip() or "DETACHED"
        porcelain = _git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z", *pathspec)
        binary_diff = _git(repo, "diff", "--binary", "HEAD", *pathspec)
        untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z", *pathspec).decode().split("\0")
    except (OSError, subprocess.CalledProcessError):
        return {"schema": "git_identity_v3", "available": False, "branch": None, "head": None, "worktree_state": "unavailable", "identity_hash": None}
    entries = []
    sensitive_untracked_present = False
    for relative in sorted(item for item in untracked if item):
        candidate = repo / relative
        try:
            metadata = candidate.lstat()
        except OSError:
            entries.append({"path": relative, "entry_type": "unreadable"})
        else:
            link_target = os.readlink(candidate) if stat.S_ISLNK(metadata.st_mode) else None
            if SENSITIVE_UNTRACKED_PATH.search(relative) or (link_target and SENSITIVE_UNTRACKED_PATH.search(link_target)):
                sensitive_untracked_present = True
                entries.append({"path": relative, "entry_type": "sensitive_unbound"})
            elif stat.S_ISREG(metadata.st_mode):
                entries.append({"path": relative, "entry_type": "regular_file", "content_sha256": sha256_file(candidate)})
            elif stat.S_ISLNK(metadata.st_mode):
                entries.append({"path": relative, "entry_type": "symlink", "content_sha256": hashlib.sha256(os.fsencode(link_target)).hexdigest()})
            else:
                entries.append({"path": relative, "entry_type": "unsupported"})
    payload = {
        "schema": "git_identity_v3",
        "available": True,
        "branch": branch,
        "head": head,
        "worktree_state": "clean" if not porcelain else "dirty",
        "porcelain_sha256": hashlib.sha256(porcelain).hexdigest(),
        "binary_diff_sha256": hashlib.sha256(binary_diff).hexdigest(),
        "untracked_files": entries,
        "untracked_content_sha256": canonical_hash(entries),
        "sensitive_untracked_present": sensitive_untracked_present,
        "identity_complete": not sensitive_untracked_present,
    }
    payload["identity_hash"] = canonical_hash(payload)
    return payload


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _valid_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_policy(policy: dict[str, Any]) -> list[dict[str, Any]]:
    if policy.get("schema") != "bot_acceptance_policy_v1" or not isinstance(policy.get("policy_id"), str) or not policy["policy_id"] or policy.get("version") != 1:
        raise ValueError("policy_id and version 1 are required")
    artifact_classes = policy.get("artifact_class_vocabulary")
    reason_codes = policy.get("reason_code_vocabulary")
    temporal_states = policy.get("temporal_state_vocabulary")
    declarations = policy.get("artifact_declarations")
    if not isinstance(artifact_classes, list) or len(artifact_classes) != len(set(artifact_classes)) or not all(isinstance(item, str) and item for item in artifact_classes):
        raise ValueError("policy artifact-class vocabulary must be unique strings")
    if not isinstance(reason_codes, list) or len(reason_codes) != len(set(reason_codes)) or not all(isinstance(item, str) and item for item in reason_codes):
        raise ValueError("policy reason-code vocabulary must be unique strings")
    if not isinstance(temporal_states, list) or len(temporal_states) != len(set(temporal_states)) or set(temporal_states) != REQUIRED_TEMPORAL_STATES:
        raise ValueError("policy temporal-state vocabulary must declare exactly the required states")
    if not isinstance(declarations, list) or not declarations:
        raise ValueError("policy artifact declarations must be present")
    declaration_ids = [row.get("artifact_id") for row in declarations if isinstance(row, dict)]
    if len(declaration_ids) != len(declarations) or len(set(declaration_ids)) != len(declarations):
        raise ValueError("policy artifact declarations must have unique IDs")
    declared_by_id = {row["artifact_id"]: row for row in declarations}
    for row in declarations:
        if row.get("artifact_class") not in artifact_classes or row.get("temporal_state") not in temporal_states:
            raise ValueError("policy artifact declaration has unknown class or temporal state")
        _safe_dvc_path(row.get("path"))
        predecessor, successor = row.get("predecessor"), row.get("successor")
        if row["temporal_state"] == "superseded":
            if predecessor not in declared_by_id or successor not in declared_by_id or predecessor == successor:
                raise ValueError("superseded artifact needs explicit predecessor and successor")
        elif predecessor is not None or successor is not None:
            raise ValueError("only superseded artifacts may declare supersession metadata")
    graph = {identifier: [] for identifier in declared_by_id}
    for row in declarations:
        if row.get("temporal_state") == "superseded":
            graph[row["predecessor"]].append(row["artifact_id"])
            graph[row["artifact_id"]].append(row["successor"])
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("artifact predecessor/successor graph must be acyclic")
        if node not in visited:
            visiting.add(node)
            for next_node in graph[node]:
                visit(next_node)
            visiting.remove(node)
            visited.add(node)
    for identifier in graph:
        visit(identifier)
    scope = policy.get("scope")
    contract = policy.get("coverage_contract")
    acceptance_contract = policy.get("locked_acceptance_contract")
    if not isinstance(scope, dict) or not isinstance(contract, dict) or not isinstance(scope.get("targets"), list) or not isinstance(policy.get("dvc_pointer_inventory"), str):
        raise ValueError("policy scope, DVC pointer inventory, coverage contract, and targets must be present")
    if acceptance_contract != REQUIRED_ACCEPTANCE_CONTRACT:
        raise ValueError("policy must freeze the complete locked acceptance contract")
    _safe_dvc_path(policy["dvc_pointer_inventory"])
    targets = scope["targets"]
    expected = {"tank": 4, "healer": 5, "dps": 22}
    counts = {role: sum(isinstance(row, dict) and row.get("role") == role for row in targets) for role in expected}
    if scope.get("target_count") != 31 or contract.get("target_count") != 31 or len(targets) != 31 or scope.get("role_counts") != expected or contract.get("role_counts") != expected or counts != expected:
        raise ValueError("policy must contain exactly 4 tanks, 5 healers, 22 DPS, and 31 targets")
    identifiers = []
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get("spec_target_id"), str) or not target["spec_target_id"] or not isinstance(target.get("rotation_spec_tag"), str) or not target["rotation_spec_tag"]:
            raise ValueError("policy target IDs and rotation spec tags must be stable")
        if target.get("role") not in expected or not _valid_int(target.get("class_id")) or target["class_id"] <= 0 or target.get("initial_status") not in {"configured", "unconfigured"}:
            raise ValueError("policy targets must have valid class, role, and status")
        identifiers.append(target["spec_target_id"])
    if len(set(identifiers)) != len(identifiers) or policy.get("runtime_join_key") != "character_bot_pool.class_spec":
        raise ValueError("policy target IDs must be unique and use character_bot_pool.class_spec")
    return sorted(targets, key=lambda row: row["spec_target_id"])


def provisioning_index(provisioning: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    scenarios = provisioning.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("provisioning scenarios must be a list")
    for scenario in scenarios:
        if not isinstance(scenario, dict) or not isinstance(scenario.get("bots"), list) or not isinstance(scenario.get("id"), str):
            raise ValueError("provisioning scenarios must contain identified bot lists")
        for bot in scenario["bots"]:
            if not isinstance(bot, dict) or not isinstance(bot.get("class_spec"), str) or not bot["class_spec"]:
                continue
            if bot.get("role") not in {"tank", "healer", "dps"} or not _valid_int(bot.get("class")):
                raise ValueError("provisioning bot has invalid class or role")
            rows.setdefault(bot["class_spec"], []).append({"scenario_id": scenario["id"], "class_id": bot["class"], "role": bot["role"]})
    return {key: sorted(value, key=canonical_bytes) for key, value in rows.items()}


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(sql):
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in {"'", '"'}:
            quote = character
        elif character == ";":
            statement = sql[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
    if quote:
        raise ValueError("unterminated SQL string in rotation migration")
    statement = sql[start:].strip()
    if statement:
        statements.append(statement)
    return statements


def _extract_parenthesized(text: str, start: int) -> tuple[str, int]:
    if start >= len(text) or text[start] != "(":
        raise ValueError("expected parenthesized SQL expression")
    depth, quote, escaped = 0, None, False
    for index in range(start, len(text)):
        character = text[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
    raise ValueError("unterminated parenthesized SQL expression")


def _split_sql_values(text: str) -> list[str]:
    values: list[str] = []
    start, depth, quote, escaped = 0, 0, None, False
    for index, character in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in {"'", '"'}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            values.append(text[start:index].strip())
            start = index + 1
    values.append(text[start:].strip())
    return values


def _sql_literal(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("\\'", "'").replace("''", "'")
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    raise ValueError(f"unsupported rotation SQL literal: {value}")


def _sql_where_matches(expression: str, profile: dict[str, Any]) -> bool:
    allowed_columns = "class_id|spec_tag|role|enabled|source_note|scope_note"
    pattern = re.compile(rf"(?:(?:`?\w+`?\.)?`?({allowed_columns})`?)\s*=\s*('(?:\\'|''|[^'])*'|[+-]?\d+)", re.IGNORECASE)

    def replace(match: re.Match[str]) -> str:
        return " T " if profile.get(match.group(1).lower()) == _sql_literal(match.group(2)) else " F "

    reduced = pattern.sub(replace, expression)
    reduced = re.sub(r"\bAND\b", " and ", reduced, flags=re.IGNORECASE)
    reduced = re.sub(r"\bOR\b", " or ", reduced, flags=re.IGNORECASE)
    reduced = reduced.replace("`", "").strip()
    if not re.fullmatch(r"[TF\s()andor]+", reduced):
        raise ValueError(f"unsupported rotation SQL predicate: {expression}")
    tokens = re.findall(r"T|F|and|or|[()]", reduced)
    if "".join(tokens) != re.sub(r"\s+", "", reduced):
        raise ValueError(f"unsupported rotation SQL predicate: {expression}")
    position = 0

    def parse_term() -> bool:
        nonlocal position
        if position >= len(tokens):
            raise ValueError("incomplete rotation SQL predicate")
        token = tokens[position]
        position += 1
        if token == "T":
            return True
        if token == "F":
            return False
        if token == "(":
            value = parse_or()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError("unbalanced rotation SQL predicate")
            position += 1
            return value
        raise ValueError("invalid rotation SQL predicate")

    def parse_and() -> bool:
        nonlocal position
        value = parse_term()
        while position < len(tokens) and tokens[position] == "and":
            position += 1
            value = parse_term() and value
        return value

    def parse_or() -> bool:
        nonlocal position
        value = parse_and()
        while position < len(tokens) and tokens[position] == "or":
            position += 1
            value = parse_and() or value
        return value

    result = parse_or()
    if position != len(tokens):
        raise ValueError("invalid rotation SQL predicate")
    return result


def _profile_assignments(text: str, profile: dict[str, Any], *, duplicate_values: dict[str, Any] | None = None) -> None:
    for assignment in _split_sql_values(text):
        match = re.fullmatch(r"\s*(?:`?\w+`?\.)?`?(class_id|spec_tag|role|enabled|source_note|scope_note)`?\s*=\s*(.+?)\s*", assignment, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        column, value = match.group(1).lower(), match.group(2)
        values_match = re.fullmatch(r"VALUES\s*\(\s*`?(\w+)`?\s*\)", value, re.IGNORECASE)
        if values_match:
            if duplicate_values is None or values_match.group(1) not in duplicate_values:
                raise ValueError("unsupported rotation SQL duplicate-key assignment")
            profile[column] = duplicate_values[values_match.group(1)]
        else:
            profile[column] = _sql_literal(value)


def _apply_rotation_statement(statement: str, profiles: list[dict[str, Any]], source_path: str) -> None:
    insert = re.match(r"INSERT\s+INTO\s+`?bot_rotation_profile`?\s*", statement, re.IGNORECASE)
    if insert:
        cursor = insert.end()
        columns_text, cursor = _extract_parenthesized(statement, cursor)
        columns = [column.strip().strip("`") for column in columns_text.split(",")]
        if not {"class_id", "spec_tag", "role"} <= set(columns):
            raise ValueError("rotation profile insert lacks identity columns")
        values_match = re.match(r"\s*VALUES\s*", statement[cursor:], re.IGNORECASE)
        if not values_match:
            raise ValueError("rotation profile insert must use VALUES")
        cursor += values_match.end()
        rows: list[list[str]] = []
        while cursor < len(statement) and statement[cursor] == "(":
            tuple_text, cursor = _extract_parenthesized(statement, cursor)
            rows.append(_split_sql_values(tuple_text))
            while cursor < len(statement) and statement[cursor].isspace():
                cursor += 1
            if cursor < len(statement) and statement[cursor] == ",":
                cursor += 1
                while cursor < len(statement) and statement[cursor].isspace():
                    cursor += 1
            else:
                break
        suffix = statement[cursor:].strip()
        duplicate_match = re.fullmatch(r"ON\s+DUPLICATE\s+KEY\s+UPDATE\s+(.+)", suffix, re.IGNORECASE | re.DOTALL)
        if suffix and not duplicate_match:
            raise ValueError("unsupported rotation profile insert suffix")
        for row in rows:
            if len(row) != len(columns):
                raise ValueError("rotation profile insert has mismatched columns and values")
            inserted = {column: _sql_literal(value) for column, value in zip(columns, row)}
            inserted.setdefault("enabled", 1)
            existing = next((item for item in profiles if all(item[key] == inserted[key] for key in ("class_id", "spec_tag", "role"))), None)
            if existing is None:
                inserted["source_path"] = source_path
                profiles.append(inserted)
            elif duplicate_match:
                _profile_assignments(duplicate_match.group(1), existing, duplicate_values=inserted)
            else:
                raise ValueError("rotation profile insert conflicts without duplicate-key handling")
        return
    update = re.match(r"UPDATE\s+`?bot_rotation_profile`?(?:\s+(?:AS\s+)?`?\w+`?)?\s+SET\s+(.+?)\s+WHERE\s+(.+)$", statement, re.IGNORECASE | re.DOTALL)
    if update:
        assignments, predicate = update.groups()
        for profile in profiles:
            if _sql_where_matches(predicate, profile):
                _profile_assignments(assignments, profile)
        return
    delete = re.match(r"DELETE\s+FROM\s+`?bot_rotation_profile`?\s+WHERE\s+(.+)$", statement, re.IGNORECASE | re.DOTALL)
    if delete:
        profiles[:] = [profile for profile in profiles if not _sql_where_matches(delete.group(1), profile)]


def rotation_tuples(paths: list[Path], repo_root: Path) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    root = repo_root.resolve()
    for path in paths:
        try:
            source_path = str(path.resolve().relative_to(root))
        except ValueError as exc:
            raise ValueError("rotation SQL path must be inside --repo-root") from exc
        if not path.is_file():
            raise ValueError(f"missing declared rotation SQL: {source_path}")
        for statement in _split_sql_statements(_strip_sql_comments(path.read_text(encoding="utf-8"))):
            _apply_rotation_statement(statement, profiles, source_path)
    return sorted(
        ({"class_id": profile["class_id"], "spec_tag": profile["spec_tag"], "role": profile["role"], "enabled": profile.get("enabled", 1), "source_path": profile["source_path"]} for profile in profiles if profile.get("enabled", 1) == 1),
        key=canonical_bytes,
    )


def _layer(name: str, expected: bool, conflicting: bool = False) -> tuple[str | None, str | None]:
    if conflicting:
        return None, f"conflicting_{name}"
    if not expected:
        return f"missing_{name}", None
    return None, None


def reconcile_targets(policy: dict[str, Any], provisioning: dict[str, Any], gear_profiles: dict[str, Any], action_profiles: dict[str, Any], rotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    provisioned = provisioning_index(provisioning)
    profiles = gear_profiles.get("profiles")
    class_actions = action_profiles.get("action_profile_spells_by_class")
    spec_actions = action_profiles.get("action_profile_spells_by_spec")
    if not isinstance(profiles, dict) or not isinstance(class_actions, dict) or not isinstance(spec_actions, dict):
        raise ValueError("gear and action profiles must be objects")
    rows = []
    for target in validate_policy(policy):
        target_id, class_id, role = target["spec_target_id"], target["class_id"], target["role"]
        if target["initial_status"] == "unconfigured":
            rows.append({"spec_target_id": target_id, "class_id": class_id, "role": role, "runtime_join_key": target_id, "status": "unsupported", "gameplay_payload": None, "coverage": {"complete": False, "missing_layers": [], "conflicting_layers": []}})
            continue
        source_bots = provisioned.get(target_id, [])
        gear = profiles.get(target_id)
        matched_rotations = [row for row in rotations if row["class_id"] == class_id and row["role"] == role and row["spec_tag"] == target["rotation_spec_tag"]]
        missing: list[str] = []
        conflicts: list[str] = []
        missing_item, conflict_item = _layer("provisioning", bool(source_bots), bool(source_bots) and any(row["class_id"] != class_id or row["role"] != role for row in source_bots))
        if missing_item: missing.append(missing_item)
        if conflict_item: conflicts.append(conflict_item)
        missing_item, conflict_item = _layer("gear_profile", gear is not None, gear is not None and (not isinstance(gear, dict) or gear.get("class_id") != class_id or gear.get("role") != role))
        if missing_item: missing.append(missing_item)
        if conflict_item: conflicts.append(conflict_item)
        has_actions = str(class_id) in class_actions and target_id in spec_actions
        missing_item, _ = _layer("action_profile", has_actions)
        if missing_item: missing.append(missing_item)
        missing_item, conflict_item = _layer("rotation_profile", len(matched_rotations) == 1, len(matched_rotations) > 1)
        if missing_item: missing.append(missing_item)
        if conflict_item: conflicts.append(conflict_item)
        complete = not missing and not conflicts
        gameplay_payload: dict[str, Any] = {
            "provisioning": {"class_spec": target_id, "bots": source_bots},
            "gear_profile": {"profile": target_id},
            "action_profile": {"class_id": class_id, "spec_target_id": target_id},
        }
        if len(matched_rotations) == 1:
            gameplay_payload["rotation_profile"] = matched_rotations[0]
        rows.append({
            "spec_target_id": target_id, "class_id": class_id, "role": role, "runtime_join_key": target_id,
            "status": "configured" if complete else "incomplete", "gameplay_payload": gameplay_payload,
            "coverage": {"complete": complete, "missing_layers": sorted(missing), "conflicting_layers": sorted(conflicts)},
        })
    if len(rows) != 31 or sum(row["status"] in {"configured", "incomplete"} for row in rows) != 14 or sum(row["status"] == "unsupported" for row in rows) != 17:
        raise ValueError("checked-in inventory must reconcile to 14 configured and 17 unsupported targets")
    if any(row["gameplay_payload"] is not None for row in rows if row["status"] == "unsupported"):
        raise ValueError("unsupported targets must not carry gameplay payloads")
    return rows


def stored_claims(classifications: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    """Record legacy boolean claims as claims only; Phase 0 never treats them as proof."""
    rows = []
    claim_names = ("passed", "all_passed", "acceptable_final_evidence", "clear_complete")
    for artifact in classifications:
        if artifact["artifact_class"] not in {"calibration_diagnostic", "calibration_evidence", "stonecore_evidence"} or artifact["availability"] not in {"available", "materialized_unverified"}:
            continue
        path = root / artifact["path"]
        report = path / "report.json" if path.is_dir() else path
        if not report.is_file():
            continue
        try:
            payload = load_json(report)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        values = {key: payload[key] for key in claim_names if isinstance(payload.get(key), bool)}
        if values:
            rows.append({"artifact_id": artifact["artifact_id"], "temporal_state": artifact["temporal_state"], "claims": values, "comparison": "recorded_only_not_proof"})
    return sorted(rows, key=canonical_bytes)


def reconcile_live_db(configured_targets: list[dict[str, Any]], probe_live_db: bool, database_url: str | None, worldserver_conf: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare policy-configured rotation keys with all enabled world-DB profiles."""
    expected = sorted({(row["class_id"], row["rotation_spec_tag"], row["role"]) for row in configured_targets})

    def records(values: list[tuple[int, str, str]]) -> list[dict[str, Any]]:
        return [{"class_id": class_id, "spec_tag": spec_tag, "role": role} for class_id, spec_tag, role in values]

    if not probe_live_db:
        return ({"available": False, "exact": False, "reason_codes": ["live_db_not_probed"], "expected_profile_keys": records(expected), "observed_profile_keys": []}, {"available": False, "reason_code": "live_db_not_probed"})
    try:
        url = database_url or database_url_from_worldserver_conf(worldserver_conf or REPO_ROOT / "trinity-worldserver-test.conf", "WorldDatabaseInfo")
        db_identity = {"available": True, "source_database": sanitize_database_url(url)}
    except (OSError, SystemExit, ValueError):
        return ({"available": False, "exact": False, "reason_codes": ["live_db_configuration_unavailable"], "expected_profile_keys": records(expected), "observed_profile_keys": []}, {"available": False, "reason_code": "live_db_configuration_unavailable"})
    try:
        query = "SELECT DISTINCT `class_id`, `spec_tag`, `role` FROM `bot_rotation_profile` WHERE `enabled` = 1 ORDER BY `class_id`, `spec_tag`, `role`"
        connection = connect_mysql(url)
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                observed = sorted({(int(row["class_id"]), str(row["spec_tag"]), str(row["role"])) for row in cursor.fetchall()})
        finally:
            connection.close()
    except Exception:
        return ({"available": False, "exact": False, "reason_codes": ["live_db_query_failed"], "expected_profile_keys": records(expected), "observed_profile_keys": []}, {**db_identity, "reason_code": "live_db_query_failed"})
    expected_set, observed_set = set(expected), set(observed)
    missing = sorted(expected_set - observed_set)
    conflicting = sorted(observed_set - expected_set)
    exact = not missing and not conflicting
    return ({
        "available": True, "exact": exact, "reason_codes": ["live_db_exact"] if exact else ["live_db_mismatch"],
        "expected_profile_keys": records(expected),
        "observed_profile_keys": records(observed),
        "missing_profile_keys": records(missing),
        "conflicting_profile_keys": records(conflicting),
    }, db_identity)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _normalized_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{str(key): _json_safe(value) for key, value in sorted(row.items())} for row in rows]


def _file_identity(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"available": False, "path": str(path)}
    return {"available": True, "path": str(path), "sha256": sha256_file(path), "byte_count": path.stat().st_size}


def _schema_identity(connection: Any, tables: list[str]) -> dict[str, Any]:
    placeholders = ", ".join(["%s"] * len(tables))
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, EXTRA "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            f"AND TABLE_NAME IN ({placeholders}) ORDER BY TABLE_NAME, ORDINAL_POSITION",
            tuple(tables),
        )
        rows = _normalized_rows(cursor.fetchall())
    observed = sorted({str(row["TABLE_NAME"]) for row in rows})
    return {
        "requested_tables": sorted(tables),
        "observed_tables": observed,
        "missing_tables": sorted(set(tables) - set(observed)),
        "column_count": len(rows),
        "schema_sha256": canonical_hash(rows),
    }


def probe_runtime_inventory(repo_root: Path, provisioning: dict[str, Any], gear_profiles: dict[str, Any], policy: dict[str, Any], worldserver_conf: Path) -> dict[str, Any]:
    """Capture read-only runtime identities and complete provisioning gap diagnostics."""
    try:
        try:
            from .build_validation_provisioning import apply_gear_profiles
            from .validate_validation_provisioning import validate_database
        except ImportError:
            from build_validation_provisioning import apply_gear_profiles
            from validate_validation_provisioning import validate_database

        world_url = database_url_from_worldserver_conf(worldserver_conf, "WorldDatabaseInfo")
        character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")
        world_connection = connect_mysql(world_url)
        try:
            world_schema = _schema_identity(world_connection, ["bot_rotation_profile", "bot_rotation_action", "version"])
            with world_connection.cursor() as cursor:
                cursor.execute("SELECT `core_version`, `core_revision`, `db_version`, `cache_id` FROM `version` LIMIT 1")
                version_row = cursor.fetchone() or {}
                cursor.execute("SELECT * FROM `bot_rotation_profile` ORDER BY `class_id`, `spec_tag`, `role`, `id`")
                profile_rows = _normalized_rows(cursor.fetchall())
                cursor.execute(
                    "SELECT p.`class_id` AS `profile_class_id`, p.`spec_tag` AS `profile_spec_tag`, "
                    "p.`role` AS `profile_role`, a.* FROM `bot_rotation_action` a "
                    "JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id` "
                    "ORDER BY p.`class_id`, p.`spec_tag`, p.`role`, a.`priority_bucket`, a.`sort_order`, a.`id`"
                )
                action_rows = _normalized_rows(cursor.fetchall())
        finally:
            world_connection.close()

        configured = apply_gear_profiles(provisioning, gear_profiles)
        provisioning_failures, provisioning_evidence = validate_database(configured, worldserver_conf, require_applied=True)
        bots = [bot for scenario in configured.get("scenarios", []) for bot in scenario.get("bots", [])]
        expected_by_name = {str(bot["name"]): bot for bot in bots}
        names = sorted(expected_by_name)
        placeholders = ", ".join(["%s"] * len(names))
        character_connection = connect_mysql(character_url)
        try:
            character_schema = _schema_identity(
                character_connection,
                [
                    "characters", "character_bot_pool", "character_glyphs", "character_talent",
                    "character_spell", "character_inventory", "item_instance", "character_pet", "pet_spell",
                ],
            )
            with character_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT c.`name`, c.`guid`, p.`role`, p.`class_spec`, p.`enabled`, p.`in_use`, p.`experiment_tags`, p.`notes` "
                    "FROM `characters` c LEFT JOIN `character_bot_pool` p ON p.`guid` = c.`guid` "
                    f"WHERE c.`name` IN ({placeholders}) ORDER BY c.`name`",
                    tuple(names),
                )
                pool_rows = _normalized_rows(cursor.fetchall())
                cursor.execute("SELECT DISTINCT `class_spec` FROM `character_bot_pool` WHERE `enabled` = 1 ORDER BY `class_spec`")
                enabled_specs = [str(row["class_spec"]) for row in cursor.fetchall()]
                cursor.execute(
                    "SELECT c.`name`, cp.`id`, cp.`entry`, cp.`active`, cp.`slot`, ps.`spell`, ps.`active` AS `spell_active` "
                    "FROM `characters` c LEFT JOIN `character_pet` cp ON cp.`owner` = c.`guid` "
                    "LEFT JOIN `pet_spell` ps ON ps.`guid` = cp.`id` "
                    f"WHERE c.`name` IN ({placeholders}) ORDER BY c.`name`, cp.`id`, ps.`spell`",
                    tuple(names),
                )
                pet_rows = _normalized_rows(cursor.fetchall())
        finally:
            character_connection.close()

        observed_pool = {str(row["name"]): row for row in pool_rows}
        pool_gaps: list[dict[str, Any]] = []
        for name, bot in sorted(expected_by_name.items()):
            actual = observed_pool.get(name)
            if actual is None or actual.get("class_spec") is None:
                pool_gaps.append({"bot": name, "gap": "missing_pool_entry"})
                continue
            expected = {"role": str(bot["role"]), "class_spec": str(bot["class_spec"]), "enabled": 1}
            mismatches = {key: {"expected": value, "actual": actual.get(key)} for key, value in expected.items() if actual.get(key) != value}
            if mismatches:
                pool_gaps.append({"bot": name, "gap": "pool_value_mismatch", "mismatches": mismatches})

        canonical_targets = {str(row["spec_target_id"]) for row in policy["scope"]["targets"]}
        alias_candidates = sorted(set(enabled_specs) - canonical_targets)
        expected_pets = {str(bot["name"]): bot["pet"] for bot in bots if bot.get("pet")}
        observed_pets: dict[str, dict[str, Any]] = {}
        for row in pet_rows:
            if row.get("id") is None:
                continue
            entry = observed_pets.setdefault(str(row["name"]), {"entry": int(row["entry"]), "spells": []})
            if row.get("spell") is not None:
                entry["spells"].append(int(row["spell"]))
        pet_gaps: list[dict[str, Any]] = []
        for name, expected in sorted(expected_pets.items()):
            actual = observed_pets.get(name)
            if actual is None:
                pet_gaps.append({"bot": name, "gap": "missing_pet"})
                continue
            expected_spells = sorted(int(item["id"] if isinstance(item, dict) else item) for item in expected.get("spells", []))
            missing_spells = sorted(set(expected_spells) - set(actual["spells"]))
            if int(actual["entry"]) != int(expected["entry"]) or missing_spells:
                pet_gaps.append({
                    "bot": name,
                    "gap": "pet_value_mismatch",
                    "expected_entry": int(expected["entry"]),
                    "actual_entry": int(actual["entry"]),
                    "missing_spells": missing_spells,
                })

        return {
            "available": True,
            "complete_report": True,
            "reason_codes": ["runtime_inventory_complete"],
            "runtime_files": {
                "worldserver_binary": _file_identity(repo_root / "build/src/server/worldserver/worldserver"),
                "worldserver_config": _file_identity(worldserver_conf),
            },
            "world_database": {
                "identity": sanitize_database_url(world_url),
                "version": {str(key): _json_safe(value) for key, value in sorted(version_row.items())},
                "schema": world_schema,
                "rotation_profiles": {"row_count": len(profile_rows), "rows_sha256": canonical_hash(profile_rows), "rows": profile_rows},
                "rotation_actions": {"row_count": len(action_rows), "rows_sha256": canonical_hash(action_rows), "rows": action_rows},
            },
            "character_database": {
                "identity": sanitize_database_url(character_url),
                "schema": character_schema,
                "provisioning_gap_count": len(provisioning_failures),
                "provisioning_gaps": provisioning_failures,
                "provisioning_evidence": provisioning_evidence,
                "pool": {"expected_count": len(names), "observed_count": len(observed_pool), "gaps": pool_gaps, "rows_sha256": canonical_hash(pool_rows)},
                "alias_inventory": {"enabled_class_specs": enabled_specs, "unknown_alias_candidates": alias_candidates},
                "pets": {"expected_count": len(expected_pets), "observed_count": len(observed_pets), "gaps": pet_gaps, "rows_sha256": canonical_hash(pet_rows)},
            },
        }
    except Exception as exc:
        return {
            "available": False,
            "complete_report": False,
            "reason_codes": ["runtime_inventory_query_failed"],
            "error_type": type(exc).__name__,
        }


def _input_identity(classifications: list[dict[str, Any]]) -> dict[str, Any]:
    return {row["artifact_id"]: {key: row[key] for key in ("path", "availability", "content_sha256", "byte_count", "entry_count", "dvc_pointer") if key in row} for row in classifications}


def _input_hashes(classifications: list[dict[str, Any]]) -> dict[str, dict[str, str] | None]:
    hashes: dict[str, dict[str, str] | None] = {}
    for row in classifications:
        if "content_sha256" in row:
            hashes[row["artifact_id"]] = {"algorithm": "sha256", "value": row["content_sha256"]}
        elif isinstance(row.get("dvc_pointer"), dict):
            hashes[row["artifact_id"]] = {"algorithm": "dvc-md5", "value": row["dvc_pointer"]["md5"]}
        else:
            hashes[row["artifact_id"]] = None
    return hashes


def build_inventory(repo_root: Path, policy_path: Path, provisioning_path: Path, gear_path: Path, action_path: Path, rotation_path: Path | None = None, rotation_paths: list[Path] | None = None, *, probe_live_db: bool = False, worldserver_conf: Path | None = None, dvc_pointer_inventory_path: Path | None = None) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    policy = load_json(policy_path)
    targets = validate_policy(policy)
    policy_hash = canonical_hash(policy)
    declarations = policy["artifact_declarations"]
    inventory_path = dvc_pointer_inventory_path or repo_root / policy.get("dvc_pointer_inventory", "")
    if not str(inventory_path):
        raise ValueError("policy must declare a DVC pointer inventory")
    pointer_inventory = load_dvc_pointer_inventory(inventory_path)
    declared_ids = {row["artifact_id"] for row in declarations}
    if set(pointer_inventory) & declared_ids:
        raise ValueError("DVC pointer inventory IDs must not collide with declared repository artifacts")
    classifications = [classify_declared_artifact(declaration, repo_root, pointer_inventory) for declaration in declarations]
    classifications.extend(classify_pointer_artifact(artifact_id, entry, repo_root) for artifact_id, entry in sorted(pointer_inventory.items()))
    declared_rotations = [repo_root / row["path"] for row in declarations if row["artifact_class"] == "effective_rotation_sql"]
    effective_rotations = rotation_paths if rotation_paths is not None else ([rotation_path] if rotation_path else declared_rotations)
    if len(effective_rotations) != len(declared_rotations) or any(path.resolve() != declared.resolve() for path, declared in zip(effective_rotations, declared_rotations)):
        raise ValueError("effective rotation inputs must exactly match policy-declared rotation SQL artifacts in declaration order")
    # Use the canonical loader so the content-addressed all-spec candidate pool is
    # part of both provisioning and baseline-inventory reconciliation.
    provisioning = load_validation_provisioning_config(provisioning_path)
    gear_profiles = load_json(gear_path)
    rows = reconcile_targets(policy, provisioning, gear_profiles, load_json(action_path), rotation_tuples(effective_rotations, repo_root))
    configured_rows = [row for row in rows if row["status"] in {"configured", "incomplete"}]
    configured_targets = [row for row in targets if row["initial_status"] == "configured"]
    live_db, database_identity = reconcile_live_db(configured_targets, probe_live_db, None, worldserver_conf)
    runtime_inventory = (
        probe_runtime_inventory(repo_root, provisioning, gear_profiles, policy, worldserver_conf or repo_root / "trinity-worldserver-test.conf")
        if probe_live_db
        else {"available": False, "complete_report": False, "reason_codes": ["runtime_inventory_not_probed"]}
    )
    required_current = [row for row in classifications if row["temporal_state"] == "current_diagnostic"]
    artifact_complete = all(row["availability"] == "available" for row in required_current)
    coverage_complete = all(row["coverage"]["complete"] for row in configured_rows)
    candidate_inventory_complete = len(rows) == 31 and {role: sum(row["role"] == role for row in rows) for role in ("tank", "healer", "dps")} == {"tank": 4, "healer": 5, "dps": 22}
    git = git_identity(repo_root)
    identity_complete = bool(git.get("available") and git.get("identity_complete", True))
    offline_complete = artifact_complete and candidate_inventory_complete and identity_complete
    offline_codes = ["offline_inventory_complete"] if offline_complete else ["offline_inventory_incomplete"]
    if not identity_complete:
        offline_codes.append("worktree_identity_incomplete")
    claims = stored_claims(classifications, repo_root)
    acceptance_code = "legacy_evidence_not_acceptable" if any(row["temporal_state"] == "historical" for row in claims) else "phase0_no_positive_acceptance"
    identity_snapshot = {
        "schema": "baseline_identity_snapshot_v2",
        "policy_id": policy["policy_id"], "policy_version": policy["version"], "policy_hash": policy_hash,
        "branch": git.get("branch"), "worktree_state": git.get("worktree_state"),
        "git": git,
        "input_identities": _input_identity(classifications),
        "stonecore_identities": {row["artifact_id"]: _input_identity([row])[row["artifact_id"]] for row in classifications if row["artifact_class"] in {"stonecore_scenario_config", "stonecore_route_manifest", "stonecore_run_plan"}},
        "sanitized_database_identity": database_identity,
        "runtime_inventory_identity": {
            "available": runtime_inventory.get("available", False),
            "runtime_files": runtime_inventory.get("runtime_files", {}),
            "world_database": {
                "identity": runtime_inventory.get("world_database", {}).get("identity"),
                "version": runtime_inventory.get("world_database", {}).get("version"),
                "schema": runtime_inventory.get("world_database", {}).get("schema"),
            },
            "character_database": {
                "identity": runtime_inventory.get("character_database", {}).get("identity"),
                "schema": runtime_inventory.get("character_database", {}).get("schema"),
            },
        },
    }
    identity_snapshot["identity_hash"] = canonical_hash(identity_snapshot)
    reconciliation = {
        "schema": "baseline_inventory_reconciliation_v2",
        "policy_id": policy["policy_id"], "policy_version": policy["version"], "policy_hash": policy_hash,
        "input_hashes": _input_hashes(classifications),
        "runtime_join_key": policy["runtime_join_key"],
        "coverage": {"target_count": 31, "role_counts": {role: sum(row["role"] == role for row in rows) for role in ("tank", "healer", "dps")}, "configured_count": len(configured_rows), "unsupported_count": sum(row["status"] == "unsupported" for row in rows), "complete": coverage_complete},
        "rows": rows,
        "offline_inventory": {
            "complete": offline_complete,
            "artifact_complete": artifact_complete,
            "candidate_inventory_complete": candidate_inventory_complete,
            "configured_coverage_complete": coverage_complete,
            "identity_complete": identity_complete,
            "reason_codes": offline_codes,
        },
        "live_db_reconciliation": live_db,
        "runtime_inventory": runtime_inventory,
        "stored_claim_comparison": claims,
        "current_acceptance": False,
        "current_acceptance_reason_codes": [acceptance_code],
        "stonecore_gameplay_accepted": False,
        "phase0_gate": {
            "passed": offline_complete and live_db["available"] and live_db["exact"] and runtime_inventory.get("complete_report", False),
            "reason_codes": offline_codes + live_db["reason_codes"] + runtime_inventory.get("reason_codes", []),
        },
    }
    artifact_classification = {"schema": "baseline_artifact_classification_v2", "policy_id": policy["policy_id"], "policy_hash": policy_hash, "artifacts": classifications}
    output_payloads = {"identity_snapshot.json": identity_snapshot, "artifact_classification.json": artifact_classification, "reconciliation_report.json": reconciliation}
    members = [{"path": name, "sha256": hashlib.sha256(json_bytes(payload)).hexdigest(), "byte_count": len(json_bytes(payload))} for name, payload in sorted(output_payloads.items())]
    manifest = {"schema": "baseline_inventory_manifest_v2", "policy_hash": policy_hash, "bundle_members": members, "bundle_hash": canonical_hash(members), "self_reference": "manifest.json is intentionally excluded from bundle_members"}
    return {**output_payloads, "manifest.json": manifest}


def write_bundle(output_dir: Path, artifacts: dict[str, dict[str, Any]]) -> None:
    if set(artifacts) != set(BUNDLE_MEMBER_NAMES):
        raise ValueError("baseline inventory bundle has undeclared members")
    manifest = artifacts["manifest.json"]
    members = manifest.get("bundle_members") if isinstance(manifest, dict) else None
    member_names = [row.get("path") for row in members if isinstance(row, dict)] if isinstance(members, list) else []
    if len(member_names) != len(members or []) or len(member_names) != len(BUNDLE_MEMBER_NAMES) - 1 or set(member_names) != set(BUNDLE_MEMBER_NAMES) - {"manifest.json"}:
        raise ValueError("baseline inventory manifest does not declare the exact bundle members")
    output_dir = output_dir.absolute()
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{output_dir.name}.staging-{uuid.uuid4().hex}"
    backup = parent / f".{output_dir.name}.backup-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        for name in BUNDLE_MEMBER_NAMES:
            (staging / name).write_bytes(json_bytes(artifacts[name]))
        if {item.name for item in staging.iterdir()} != set(BUNDLE_MEMBER_NAMES):
            raise ValueError("staged baseline inventory bundle has undeclared members")
        for member in members:
            data = (staging / member["path"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != member.get("sha256") or len(data) != member.get("byte_count"):
                raise ValueError("staged baseline inventory member does not match manifest")
        if output_dir.exists():
            if not output_dir.is_dir() or output_dir.is_symlink():
                raise ValueError("baseline inventory output must be a directory")
            os.replace(output_dir, backup)
        os.replace(staging, output_dir)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if not output_dir.exists() and backup.exists():
            os.replace(backup, output_dir)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists():
            shutil.rmtree(backup)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic Phase 0 baseline inventory; DB probing is opt-in and read-only.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--policy", type=Path, default=REPO_ROOT / "experiments/configs/bot_acceptance_policy_v1.json")
    parser.add_argument("--provisioning", type=Path, default=REPO_ROOT / "experiments/configs/validation_provisioning_cata_001.json")
    parser.add_argument("--gear-profiles", type=Path, default=REPO_ROOT / "dataset/validation_gear_profiles/profiles.json")
    parser.add_argument("--action-profiles", type=Path, default=REPO_ROOT / "experiments/configs/cata_434_action_profiles.json")
    parser.add_argument("--rotation-sql", type=Path, action="append", help="Repeat only in the exact policy-declared effective rotation SQL declaration order; defaults to that ordered set.")
    parser.add_argument("--dvc-pointer-inventory", type=Path, help="Checked-in non-secret DVC pointer identity inventory; defaults to the policy declaration.")
    parser.add_argument("--probe-live-db", action="store_true", help="Explicitly issue read-only world/character inventory queries using database URLs from the worldserver config.")
    parser.add_argument("--worldserver-conf", type=Path, default=REPO_ROOT / "trinity-worldserver-test.conf")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / OUTPUT_RELATIVE_PATH)
    args = parser.parse_args()
    artifacts = build_inventory(args.repo_root.resolve(), args.policy, args.provisioning, args.gear_profiles, args.action_profiles, rotation_paths=args.rotation_sql, probe_live_db=args.probe_live_db, worldserver_conf=args.worldserver_conf, dvc_pointer_inventory_path=args.dvc_pointer_inventory)
    write_bundle(args.output_dir, artifacts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
