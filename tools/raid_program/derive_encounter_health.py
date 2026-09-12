"""Derive NPC maximum health from attributable, consecutive WCL resource rows.

Input is the retained list of records with columns and observations. This reads
rendered lost-health percentages, not rounded HP labels or hidden page state.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


COLUMNS = ["displayed_relative_time", "displayed_damage_amount",
           "health_bar_css_right_percent"]


def derive(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError("Each capture must be an attributed record")
    if record.get("columns") != COLUMNS:
        raise ValueError("Expected timestamp, damage and rendered missing-health percent columns")
    if record.get("consecutive_no_healing_or_overkill") is not True:
        raise ValueError("Capture must explicitly establish consecutive health changes without healing/overkill")
    if not all(record.get(k) for k in ("report", "fight", "mode", "actor_id", "url")):
        raise ValueError("Missing report/fight/mode/actor/source attribution")
    observations = record.get("observations", [])
    estimates = []
    previous = 0.0 if record.get("initial_full_health") is True else None
    previous_time = -1.0
    for row in observations:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError("Each observation must contain exactly three columns")
        timestamp, amount, percent = row
        try:
            minute, second = timestamp.split(":")
            elapsed = int(minute) * 60 + float(second)
            valid_time = int(minute) >= 0 and 0 <= float(second) < 60
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Expected WCL minute:second timestamps") from None
        if not valid_time or elapsed < previous_time:
            raise ValueError("Timestamps must be finite, nonnegative and ordered")
        previous_time = elapsed
        if (isinstance(amount, bool) or not isinstance(amount, (int, float))
                or not math.isfinite(amount) or amount <= 0):
            raise ValueError("Use positive health damage; document excluded zero-change rows separately")
        if (isinstance(percent, bool) or not isinstance(percent, (int, float))
                or not math.isfinite(percent) or not 0 < percent < 100):
            raise ValueError("Missing-health percentage must be strictly between zero and 100")
        if previous is not None:
            if percent <= previous:
                raise ValueError("Health loss must increase; inspect healing, max-HP changes or wrong actor joins")
            estimates.append(amount * 100.0 / (percent - previous))
        previous = percent
    if len(estimates) < 3:
        raise ValueError("Need at least three independent health-change estimates")
    if not all(math.isfinite(value) for value in estimates):
        raise ValueError("Non-finite estimate; inspect percentage precision")
    rounded = sorted({round(value) for value in estimates})
    if len(rounded) != 1:
        raise ValueError("Inconsistent maximum-health estimates; inspect gaps, mitigation fields and actor identity")
    result = {k: record.get(k) for k in ("report", "fight", "mode", "actor_id", "npc_id", "date", "url")}
    result.update(derived_max_health=rounded[0], estimates=estimates,
                  observation_kind="derived_from_rendered_resource_changes",
                  initial_full_health_assumed=record.get("initial_full_health") is True,
                  target_cutoff_compatibility="not_established_by_this_calculation")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        records = json.loads(args.input.read_text())
        if not isinstance(records, list):
            raise ValueError("Expected a list of attributed NPC resource captures")
        result = [derive(record) for record in records]
        if not result:
            raise ValueError("No captures supplied")
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
