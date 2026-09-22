"""Reject fresh route slices whose instance prerequisites were never executed."""

from __future__ import annotations

from typing import Any


def preceding_routes(
    selected: dict[str, Any], routes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use declared route order, including staging and traversal nodes."""
    ordered = sorted(routes, key=lambda row: int(row.get("step") or 0))
    for index, row in enumerate(ordered):
        if row.get("route_node_id") == selected.get("route_node_id"):
            return ordered[:index]
    raise ValueError("selected route node is absent from the scenario")


def require_route_prerequisites(
    *, scenario_id: str, selected: dict[str, Any],
    routes: list[dict[str, Any]], explicit_selection: bool,
    full_manifest: bool, separate_sequence: bool, offline: bool = False,
) -> None:
    """A selector is not proof of a prepared instance. Fail before side effects.

    No saved-instance bypass is supported here. A dedicated isolated scenario
    must encode its own admitted start state; a descriptive prerequisite flag
    or a bot's retained position cannot certify live predecessor clearance.
    """
    if offline or not scenario_id:
        return
    if separate_sequence and len(routes) > 1:
        raise ValueError(
            "route prerequisites require one persistent worldserver; use "
            "--validation-route-manifest instead of --validation-route-sequence"
        )
    if full_manifest and explicit_selection:
        raise ValueError(
            "full route manifest cannot be combined with a segment/node selector; "
            "remove --validation-segment-id and all --validation-route-* selectors "
            "except --validation-route-manifest"
        )
    if not explicit_selection:
        return
    if not selected:
        raise ValueError("validation route selector did not resolve to a scenario node")
    predecessors = preceding_routes(selected, routes)
    if predecessors:
        names = ", ".join(str(row.get("route_node_id") or row.get("label"))
                          for row in predecessors)
        raise ValueError(
            f"route prerequisites not established for {selected.get('route_node_id')}: "
            f"{names}. A selected segment does not clear or certify preceding nodes. "
            "Use --validation-route-manifest with --validation-scenario-id "
            f"{scenario_id}, without segment/node selectors, to execute the route "
            "on one worldserver. For an isolated boss use a separately admitted "
            "scenario with verified instance prerequisites."
        )
