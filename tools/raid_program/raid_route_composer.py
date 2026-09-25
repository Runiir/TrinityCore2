"""Compose a full-raid validation route from reviewed per-boss node sets.

Each boss shard in ``validation_scenarios_cata_001.json`` owns the reviewed
node set for its boss (entrance/preparation, prerequisite trash, native
interactions and the encounter). The full-raid scenario is not hand-written:
it is composed from those node sets in one authoritative order, plus
full-raid-only transit nodes (for example an elevator between wings), plus
declared variants where the full raid intentionally differs from a shard
(for example a two-tank composition). Node IDs are preserved because boss
strategies look them up exactly.

The composer is fail-closed:

* a node ID that appears in two node sets must be identical (reported as a
  duplicate and emitted once) or composition stops with a conflict;
* every variant must name an existing node and change it (stale variants are
  errors), and carries a written reason;
* every mechanic profile referenced by the composed route must be defined,
  with no conflicting definitions;
* every row kind must be executable by the runtime.

``--check`` compares the composed route with the materialized full-raid
scenario in the config and exits non-zero on drift. ``--write`` rewrites only
that scenario's ``route`` and ``mechanic_profiles`` blocks in place; every
other line of the config (including the accepted Magmaw shard) is untouched.
"""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys
from typing import Any

from tools.raid_program.raid_route_kinds import ALLOWED_ROUTE_KINDS


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_SCHEMA = "raid_route_composition_v1"
DEFAULT_CONFIG = REPO_ROOT / "experiments/configs/validation_scenarios_cata_001.json"
DEFAULT_COMPOSITION = (
    REPO_ROOT / "experiments/configs/raid_route_compositions/blackwing_descent_10n.json"
)
NODE_ID_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{2,95}")
NODE_SET_FIELDS = {"id", "source_scenario_id", "node_ids", "rows", "reason"}
VARIANT_FIELDS = {"node_id", "reason", "set", "unset"}
COMPOSITION_FIELDS = {
    "schema", "scenario_id", "description", "node_sets", "variants",
    "mechanic_profiles",
}


class RaidRouteCompositionError(ValueError):
    pass


@dataclass
class ComposedRoute:
    scenario_id: str
    route: list[dict[str, Any]]
    mechanic_profiles: dict[str, list[str]]
    node_set_order: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    variants: list[dict[str, Any]] = field(default_factory=list)

    def report(self) -> dict[str, Any]:
        return {
            "schema": "raid_route_composition_report_v1",
            "scenario_id": self.scenario_id,
            "node_count": len(self.route),
            "node_ids": [row["node_id"] for row in self.route],
            "node_sets": self.node_set_order,
            "duplicates": self.duplicates,
            "variants": self.variants,
            "mechanic_profiles": sorted(self.mechanic_profiles),
        }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scenarios_by_id(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for group in ("scenarios", "diagnostic_scenarios"):
        for scenario in config.get(group) or []:
            scenario_id = str(scenario.get("id") or "")
            if not scenario_id or scenario_id in index:
                raise RaidRouteCompositionError(
                    f"scenario_id_invalid_or_duplicate:{scenario_id}"
                )
            index[scenario_id] = scenario
    return index


def _row_without_step(row: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in row.items() if key != "step"}


def _validate_row(row: dict[str, Any], origin: str) -> str:
    node_id = str(row.get("node_id") or "")
    if not NODE_ID_RE.fullmatch(node_id):
        raise RaidRouteCompositionError(f"node_id_invalid:{origin}:{node_id}")
    kind = str(row.get("kind") or "")
    if kind not in ALLOWED_ROUTE_KINDS:
        raise RaidRouteCompositionError(
            f"route_kind_not_executable:{origin}:{node_id}:{kind}"
        )
    return node_id


def _node_set_rows(
    node_set: dict[str, Any], scenario_id: str,
    scenarios: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    set_id = str(node_set.get("id") or "")
    source_id = str(node_set.get("source_scenario_id") or "")
    inline = node_set.get("rows")
    if bool(source_id) == (inline is not None):
        raise RaidRouteCompositionError(f"node_set_source_ambiguous:{set_id}")
    if not source_id:
        if not isinstance(inline, list) or not inline:
            raise RaidRouteCompositionError(f"node_set_rows_invalid:{set_id}")
        if not str(node_set.get("reason") or "").strip():
            raise RaidRouteCompositionError(f"node_set_reason_missing:{set_id}")
        if any("step" in row for row in inline):
            raise RaidRouteCompositionError(f"inline_row_declares_step:{set_id}")
        return inline, f"composition:{set_id}", {}

    source = scenarios.get(source_id)
    if source is None or source_id == scenario_id:
        raise RaidRouteCompositionError(f"node_set_source_invalid:{set_id}:{source_id}")
    rows = sorted(source.get("route") or [], key=lambda row: int(row.get("step") or 0))
    wanted = node_set.get("node_ids")
    if wanted is not None:
        by_id = {str(row.get("node_id") or ""): row for row in rows}
        missing = [node_id for node_id in wanted if node_id not in by_id]
        if missing:
            raise RaidRouteCompositionError(f"node_set_node_missing:{set_id}:{missing[0]}")
        rows = [by_id[node_id] for node_id in wanted]
    return rows, source_id, source.get("mechanic_profiles") or {}


def compose(config: dict[str, Any], composition: dict[str, Any]) -> ComposedRoute:
    if composition.get("schema") != COMPOSITION_SCHEMA:
        raise RaidRouteCompositionError("composition_schema")
    unknown = set(composition) - COMPOSITION_FIELDS
    if unknown:
        raise RaidRouteCompositionError(f"composition_unknown_field:{sorted(unknown)[0]}")
    scenario_id = str(composition.get("scenario_id") or "")
    scenarios = scenarios_by_id(config)
    if scenario_id not in scenarios:
        raise RaidRouteCompositionError(f"composition_target_missing:{scenario_id}")

    rows: list[dict[str, Any]] = []
    origin_by_node: dict[str, str] = {}
    profile_sources: dict[str, tuple[list[str], str]] = {}
    duplicates: list[dict[str, Any]] = []
    node_set_order: list[dict[str, Any]] = []
    set_ids: set[str] = set()

    def add_profiles(profiles: dict[str, Any], origin: str) -> None:
        for name, families in profiles.items():
            normalized = [str(item) for item in families]
            previous = profile_sources.get(name)
            if previous and previous[0] != normalized:
                raise RaidRouteCompositionError(
                    f"mechanic_profile_conflict:{name}:{previous[1]}:{origin}"
                )
            profile_sources.setdefault(name, (normalized, origin))

    for node_set in composition.get("node_sets") or []:
        unknown = set(node_set) - NODE_SET_FIELDS
        if unknown:
            raise RaidRouteCompositionError(f"node_set_unknown_field:{sorted(unknown)[0]}")
        set_id = str(node_set.get("id") or "")
        if not set_id or set_id in set_ids:
            raise RaidRouteCompositionError(f"node_set_id_invalid_or_duplicate:{set_id}")
        set_ids.add(set_id)
        source_rows, origin, profiles = _node_set_rows(node_set, scenario_id, scenarios)
        add_profiles(profiles, origin)

        emitted: list[str] = []
        for source_row in source_rows:
            row = _row_without_step(source_row)
            node_id = _validate_row(row, origin)
            previous_origin = origin_by_node.get(node_id)
            if previous_origin is not None:
                previous = next(item for item in rows if item["node_id"] == node_id)
                if previous != row:
                    raise RaidRouteCompositionError(
                        f"conflicting_rows:{node_id}:{previous_origin}:{origin}"
                    )
                duplicates.append({
                    "node_id": node_id, "kept_from": previous_origin,
                    "duplicate_in": origin,
                })
                continue
            origin_by_node[node_id] = origin
            rows.append(row)
            emitted.append(node_id)
        node_set_order.append({"id": set_id, "source": origin, "node_ids": emitted})

    variant_reports: list[dict[str, Any]] = []
    seen_variant_nodes: set[str] = set()
    for variant in composition.get("variants") or []:
        unknown = set(variant) - VARIANT_FIELDS
        if unknown:
            raise RaidRouteCompositionError(f"variant_unknown_field:{sorted(unknown)[0]}")
        node_id = str(variant.get("node_id") or "")
        reason = str(variant.get("reason") or "").strip()
        if not reason:
            raise RaidRouteCompositionError(f"variant_reason_missing:{node_id}")
        if node_id in seen_variant_nodes:
            raise RaidRouteCompositionError(f"variant_duplicate:{node_id}")
        seen_variant_nodes.add(node_id)
        target = next((row for row in rows if row["node_id"] == node_id), None)
        if target is None:
            raise RaidRouteCompositionError(f"variant_node_missing:{node_id}")
        changes = variant.get("set") or {}
        removals = [str(key) for key in variant.get("unset") or []]
        if {"node_id", "step"} & (set(changes) | set(removals)):
            raise RaidRouteCompositionError(f"variant_identity_field:{node_id}")
        before = copy.deepcopy(target)
        for key in removals:
            if key not in target:
                raise RaidRouteCompositionError(f"variant_unset_missing:{node_id}:{key}")
            del target[key]
        for key, value in changes.items():
            target[key] = copy.deepcopy(value)
        if target == before:
            raise RaidRouteCompositionError(f"variant_noop:{node_id}")
        _validate_row(target, f"variant:{node_id}")
        variant_reports.append({
            "node_id": node_id,
            "reason": reason,
            "changed_fields": sorted(
                key for key in set(before) | set(target)
                if before.get(key) != target.get(key)
            ),
        })

    add_profiles(composition.get("mechanic_profiles") or {}, "composition")
    referenced: list[str] = []
    for row in rows:
        name = str(row.get("mechanic_profile") or "")
        if name and name not in referenced:
            referenced.append(name)
    missing_profiles = [name for name in referenced if name not in profile_sources]
    if missing_profiles:
        raise RaidRouteCompositionError(f"mechanic_profile_missing:{missing_profiles[0]}")
    mechanic_profiles = {name: list(profile_sources[name][0]) for name in referenced}

    route = [{"step": index, **row} for index, row in enumerate(rows, 1)]
    return ComposedRoute(
        scenario_id=scenario_id,
        route=route,
        mechanic_profiles=mechanic_profiles,
        node_set_order=node_set_order,
        duplicates=duplicates,
        variants=variant_reports,
    )


def drift(config: dict[str, Any], composed: ComposedRoute) -> list[dict[str, Any]]:
    """Field-level differences between the materialized scenario and the composition."""

    scenario = scenarios_by_id(config)[composed.scenario_id]
    materialized_rows = scenario.get("route") or []
    materialized = {str(row.get("node_id") or ""): row for row in materialized_rows}
    composed_rows = {row["node_id"]: row for row in composed.route}
    differences: list[dict[str, Any]] = []
    materialized_order = [str(row.get("node_id") or "") for row in materialized_rows]
    composed_order = [row["node_id"] for row in composed.route]
    if materialized_order != composed_order:
        differences.append({
            "kind": "node_order", "materialized": materialized_order,
            "composed": composed_order,
        })
    for node_id in sorted(set(materialized) | set(composed_rows)):
        left = materialized.get(node_id)
        right = composed_rows.get(node_id)
        if left is None or right is None:
            differences.append({
                "kind": "node_presence", "node_id": node_id,
                "materialized": left is not None, "composed": right is not None,
            })
            continue
        fields = sorted(
            key for key in set(left) | set(right) if left.get(key) != right.get(key)
        )
        if fields:
            differences.append({"kind": "node_fields", "node_id": node_id, "fields": fields})
    if (scenario.get("mechanic_profiles") or {}) != composed.mechanic_profiles:
        differences.append({"kind": "mechanic_profiles"})
    return differences


def _render_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def render_row(row: dict[str, Any]) -> str:
    return "{ " + ", ".join(
        f"{json.dumps(key)}: {_render_value(value)}" for key, value in row.items()
    ) + " }"


def _block_bounds(lines: list[str], start: int, name: str, opener: str) -> tuple[int, int, str]:
    """Locate the `"<name>": <opener>` block that follows line `start`."""

    closer = "]" if opener == "[" else "}"
    pattern = re.compile(r'^(\s*)' + re.escape(json.dumps(name)) + r": " + re.escape(opener) + r"\s*$")
    for index in range(start, len(lines)):
        match = pattern.match(lines[index])
        if not match:
            continue
        indent = match.group(1)
        for end in range(index + 1, len(lines)):
            if lines[end].rstrip("\r\n") in (indent + closer, indent + closer + ","):
                return index, end, indent
        break
    raise RaidRouteCompositionError(f"materialized_block_missing:{name}")


def materialize_text(config_text: str, composed: ComposedRoute) -> str:
    """Rewrite only the target scenario's route and mechanic_profiles blocks."""

    lines = config_text.splitlines(keepends=True)
    id_pattern = re.compile(
        r'^\s*"id": ' + re.escape(json.dumps(composed.scenario_id)) + r",\s*$"
    )
    id_line = next(
        (index for index, line in enumerate(lines) if id_pattern.match(line)), None
    )
    if id_line is None:
        raise RaidRouteCompositionError("materialized_scenario_missing")

    route_start, route_end, route_indent = _block_bounds(lines, id_line, "route", "[")
    row_indent = route_indent + "  "
    lines[route_start + 1:route_end] = [
        row_indent + render_row(row) + ("," if index + 1 < len(composed.route) else "") + "\n"
        for index, row in enumerate(composed.route)
    ]
    profiles_start, profiles_end, profiles_indent = _block_bounds(
        lines, route_start, "mechanic_profiles", "{"
    )
    names = list(composed.mechanic_profiles)
    lines[profiles_start + 1:profiles_end] = [
        profiles_indent + "  " + json.dumps(name) + ": "
        + _render_value(composed.mechanic_profiles[name])
        + ("," if index + 1 < len(names) else "") + "\n"
        for index, name in enumerate(names)
    ]
    new_text = "".join(lines)

    # Prove the rewrite changed nothing but the target blocks.
    before = json.loads(config_text)
    after = json.loads(new_text)
    target = scenarios_by_id(after)[composed.scenario_id]
    if (target.get("route") != composed.route
            or target.get("mechanic_profiles") != composed.mechanic_profiles):
        raise RaidRouteCompositionError("materialized_rewrite_mismatch")

    def strip_target(document: dict[str, Any]) -> dict[str, Any]:
        stripped = copy.deepcopy(document)
        for group in ("scenarios", "diagnostic_scenarios"):
            for scenario in stripped.get(group) or []:
                if scenario.get("id") == composed.scenario_id:
                    scenario.pop("route", None)
                    scenario.pop("mechanic_profiles", None)
        return stripped

    if strip_target(before) != strip_target(after):
        raise RaidRouteCompositionError("materialized_rewrite_touched_other_content")
    return new_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--composition", type=Path, default=DEFAULT_COMPOSITION)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="exit 1 when the materialized route drifts from the composition")
    mode.add_argument("--write", action="store_true",
                      help="rewrite the materialized full-raid route in place")
    args = parser.parse_args(argv)

    config_text = args.config.read_text(encoding="utf-8")
    config = json.loads(config_text)
    composed = compose(config, load_json(args.composition))
    differences = drift(config, composed)
    if args.write and differences:
        args.config.write_text(materialize_text(config_text, composed), encoding="utf-8")
        differences = drift(load_json(args.config), composed)
    print(json.dumps({**composed.report(), "drift": differences}, indent=2, sort_keys=True))
    return 1 if args.check and differences else 0


if __name__ == "__main__":
    sys.exit(main())
