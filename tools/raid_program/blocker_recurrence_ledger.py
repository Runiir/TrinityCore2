#!/usr/bin/env python3
"""Evaluate recurring causal blockers across deterministic raid canaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


VALID_STATES = {"occurred", "absent", "not_exercised"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def evaluate_ledger(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Return the fail-closed recurrence and acceptance decision.

    One occurrence is counted per causal signature and run. Intervening absence
    never erases occurrence history. Only a completed route can contribute to
    the clean-clear streak used to close an intermittent blocker.
    """

    _require(
        ledger.get("schema") == "trinity_raid_blocker_recurrence_v1",
        "unsupported blocker recurrence ledger schema",
    )
    occurrence_limit = int(ledger.get("occurrence_limit", 10))
    clear_streak_required = int(ledger.get("clear_streak_required", 2))
    _require(occurrence_limit > 0, "occurrence_limit must be positive")
    _require(clear_streak_required > 0, "clear_streak_required must be positive")

    signature_contracts = dict(ledger.get("causal_signatures") or {})
    parents: dict[str, str] = {}
    for signature, contract in signature_contracts.items():
        _require(
            isinstance(contract, Mapping),
            f"signature {signature} contract must be an object",
        )
        parent = str(contract.get("parent") or "").strip()
        if parent:
            _require(
                parent != signature,
                f"signature {signature} cannot parent itself",
            )
            _require(
                parent in signature_contracts,
                f"signature {signature} has unknown parent {parent}",
            )
            parents[str(signature)] = parent

    def ancestors(signature: str) -> list[str]:
        result: list[str] = []
        seen = {signature}
        current = signature
        while current in parents:
            current = parents[current]
            _require(
                current not in seen,
                f"causal signature parent cycle at {current}",
            )
            seen.add(current)
            result.append(current)
        return result

    runs = list(ledger.get("runs") or [])
    seen_run_ids: set[str] = set()
    signatures: set[str] = set()
    normalized_runs: list[dict[str, Any]] = []

    for index, run in enumerate(runs):
        _require(isinstance(run, Mapping), f"run {index} must be an object")
        run_id = str(run.get("run_id") or "").strip()
        _require(bool(run_id), f"run {index} is missing run_id")
        _require(run_id not in seen_run_ids, f"duplicate run_id: {run_id}")
        seen_run_ids.add(run_id)

        observations = dict(run.get("blockers") or {})
        for signature, state in observations.items():
            _require(bool(str(signature).strip()), f"run {run_id} has empty signature")
            _require(
                state in VALID_STATES,
                f"run {run_id} signature {signature} has invalid state {state!r}",
            )
            signatures.add(str(signature))

        # A child occurrence is also one occurrence of every owning parent.
        # Deduplicate at run scope so sibling symptoms cannot inflate the
        # architecture-stop counter. Explicit absence never overrides a child
        # occurrence from the same trace.
        for signature, state in list(observations.items()):
            if state != "occurred":
                continue
            for parent in ancestors(str(signature)):
                observations[parent] = "occurred"
                signatures.add(parent)

        normalized_runs.append(
            {
                "run_id": run_id,
                "route_completed": run.get("route_completed") is True,
                "blockers": observations,
            }
        )

    run_positions = {
        run["run_id"]: index for index, run in enumerate(normalized_runs)
    }

    blocker_rows: list[dict[str, Any]] = []
    stop_signatures: list[str] = []
    open_signatures: list[str] = []

    for signature in sorted(signatures):
        occurrences = [
            run["run_id"]
            for run in normalized_runs
            if run["blockers"].get(signature) == "occurred"
        ]
        clean_clear_streak = 0
        for run in reversed(normalized_runs):
            state = run["blockers"].get(signature, "not_exercised")
            if run["route_completed"] and state == "absent":
                clean_clear_streak += 1
                continue
            break

        occurrence_count = len(occurrences)
        last_observed_run_id = None
        last_observed_state = "not_exercised"
        for run in reversed(normalized_runs):
            if signature not in run["blockers"]:
                continue
            last_observed_run_id = run["run_id"]
            last_observed_state = run["blockers"][signature]
            break
        contract = signature_contracts.get(signature, {})
        reviewed_through = int(
            contract.get("architecture_reviewed_through_occurrence_count", 0)
        )
        _require(
            0 <= reviewed_through <= occurrence_count,
            f"signature {signature} has invalid architecture review count",
        )
        unreviewed_occurrence_count = occurrence_count - reviewed_through
        open_blocker = occurrence_count > 0 and clean_clear_streak < clear_streak_required
        fixture_verifications = list(contract.get("fixture_verifications") or [])
        latest_fixture_verification: Mapping[str, Any] | None = None
        latest_fixture_boundary = -1.0
        for verification_index, verification in enumerate(fixture_verifications):
            _require(
                isinstance(verification, Mapping),
                f"signature {signature} fixture verification "
                f"{verification_index} must be an object",
            )
            before_run_id = str(verification.get("passed_before_run_id") or "").strip()
            after_run_id = str(verification.get("passed_after_run_id") or "").strip()
            _require(
                bool(before_run_id) != bool(after_run_id),
                f"signature {signature} fixture verification "
                f"{verification_index} must declare exactly one of "
                "passed_before_run_id or passed_after_run_id",
            )
            boundary_run_id = before_run_id or after_run_id
            _require(
                boundary_run_id in run_positions,
                f"signature {signature} fixture verification "
                f"{verification_index} has unknown boundary run_id "
                f"{boundary_run_id!r}",
            )
            evidence = str(verification.get("evidence") or "").strip()
            _require(
                bool(evidence),
                f"signature {signature} fixture verification "
                f"{verification_index} is missing evidence",
            )
            boundary = float(run_positions[boundary_run_id])
            boundary += 0.5 if after_run_id else -0.5
            _require(
                boundary >= latest_fixture_boundary,
                f"signature {signature} fixture verifications are not "
                "chronological",
            )
            latest_fixture_boundary = boundary
            latest_fixture_verification = verification

        live_occurrences_after_fixture = [
            run["run_id"]
            for index, run in enumerate(normalized_runs)
            if latest_fixture_verification is not None
            and float(index) > latest_fixture_boundary
            and run["blockers"].get(signature) == "occurred"
        ]
        fixture_invalidated = bool(live_occurrences_after_fixture)
        last_occurrence_position = (
            run_positions[occurrences[-1]] if occurrences else -1
        )
        fixture_verified_after_latest_occurrence = (
            latest_fixture_verification is not None
            and latest_fixture_boundary > float(last_occurrence_position)
        )
        recurrence_limit_stop = unreviewed_occurrence_count >= occurrence_limit
        stop_required = recurrence_limit_stop or fixture_invalidated
        if open_blocker:
            open_signatures.append(signature)
        if stop_required:
            stop_signatures.append(signature)
        blocker_rows.append(
            {
                "causal_signature": signature,
                "occurrence_count": occurrence_count,
                "occurrence_run_ids": occurrences,
                "last_occurrence_run_id": occurrences[-1] if occurrences else None,
                "last_observed_run_id": last_observed_run_id,
                "last_observed_state": last_observed_state,
                "architecture_reviewed_through_occurrence_count": reviewed_through,
                "unreviewed_occurrence_count": unreviewed_occurrence_count,
                "clean_full_clear_streak": clean_clear_streak,
                "latest_fixture_verification": (
                    dict(latest_fixture_verification)
                    if latest_fixture_verification is not None
                    else None
                ),
                "live_occurrences_after_fixture": live_occurrences_after_fixture,
                "retained_fixture_invalidated": fixture_invalidated,
                "fixture_verified_after_latest_occurrence": (
                    fixture_verified_after_latest_occurrence
                ),
                "recurrence_limit_stop": recurrence_limit_stop,
                "open": open_blocker,
                "stop_required": stop_required,
            }
        )

    last_runs = normalized_runs[-clear_streak_required:]
    open_rows = [row for row in blocker_rows if row["open"]]
    repair_rows = [
        row for row in open_rows
        if row["last_observed_state"] == "occurred"
        and not row["fixture_verified_after_latest_occurrence"]
    ]
    next_signature = None
    if repair_rows:
        next_signature = max(
            repair_rows,
            key=lambda row: (
                run_positions.get(row["last_occurrence_run_id"], -1),
                row["occurrence_count"],
            ),
        )["causal_signature"]
    invalid_fixture_rows = [
        row for row in blocker_rows if row["retained_fixture_invalidated"]
    ]
    if invalid_fixture_rows:
        next_signature = max(
            invalid_fixture_rows,
            key=lambda row: run_positions.get(
                row["live_occurrences_after_fixture"][-1], -1
            ),
        )["causal_signature"]
    acceptance = (
        len(last_runs) == clear_streak_required
        and all(run["route_completed"] for run in last_runs)
        and not open_signatures
        and not stop_signatures
    )
    if invalid_fixture_rows:
        required_next_action = "expand_invalid_retained_fixture"
    elif stop_signatures:
        required_next_action = "stop_and_summarize_last_ten_occurrences"
    elif repair_rows:
        required_next_action = "repair_latest_recurring_causal_signature"
    elif not acceptance:
        required_next_action = "run_clean_full_clear"
    else:
        required_next_action = "accept"
    return {
        "schema": "trinity_raid_blocker_recurrence_decision_v1",
        "run_count": len(normalized_runs),
        "occurrence_limit": occurrence_limit,
        "clear_streak_required": clear_streak_required,
        "blockers": blocker_rows,
        "open_causal_signatures": open_signatures,
        "stop_required": bool(stop_signatures),
        "stop_causal_signatures": stop_signatures,
        "next_causal_signature": next_signature,
        "acceptance_admitted": acceptance,
        "required_next_action": required_next_action,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    decision = evaluate_ledger(json.loads(args.ledger.read_text()))
    rendered = json.dumps(decision, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
