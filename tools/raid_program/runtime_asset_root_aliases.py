"""Detect contradictory requirements for files shared by configured roots.

This is a pure contract check, before reading asset bytes. Callers select map
contracts first and retain their normal no-follow filesystem validation.
Distinct paths to hard-linked files are outside this lexical check.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


def find_root_contract_conflicts(
    selected_classes: Iterable[Mapping[str, Any]], roots: Mapping[str, Path],
) -> list[dict[str, Any]]:
    requirements: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for asset_class in selected_classes:
        class_id = asset_class.get("id")
        root_key = asset_class.get("root")
        if not isinstance(class_id, str) or not class_id or not isinstance(root_key, str) or root_key not in roots:
            raise ValueError("asset_class_invalid")
        root = roots[root_key]
        expected_files = asset_class.get("expected_files", [])
        if not isinstance(expected_files, list):
            raise ValueError(f"expected_files_invalid:{class_id}")
        for row in expected_files:
            if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
                raise ValueError(f"expected_file_invalid:{class_id}")
            relative = PurePosixPath(row["path"])
            if (relative.is_absolute() or ".." in relative.parts or not relative.parts
                    or "\\" in row["path"] or row["path"] != relative.as_posix()):
                raise ValueError("unsafe_expected_asset_path")
            # abspath normalizes spelling without following untrusted symlinks.
            path = os.path.abspath(root / relative)
            values = {key: row[key] for key in ("sha256", "size_bytes", "mode") if key in row}
            values["type"] = row.get("type", "file")
            if "mode" not in values and "expected_mode" in asset_class:
                values["mode"] = asset_class["expected_mode"]
            requirements.setdefault(path, []).append((class_id, values))
    issues = []
    for path, rows in sorted(requirements.items()):
        for index, (first_id, first) in enumerate(rows):
            for second_id, second in rows[index + 1:]:
                conflicts = {
                    key: {first_id: first[key], second_id: second[key]}
                    for key in sorted(first.keys() & second.keys())
                    if first[key] != second[key]
                }
                if conflicts:
                    issues.append({
                        "kind": "root_mismatch", "detail": "aliased_root_contract",
                        "path": path, "class_ids": [first_id, second_id],
                        "conflicts": conflicts,
                    })
    return issues
