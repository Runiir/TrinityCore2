"""Decision-time feature filtering, separate from general dataset I/O helpers."""
from __future__ import annotations

import math
from typing import Any, Iterable


def numeric_features(row: dict[str, Any], labels: Iterable[str]) -> dict[str, float]:
    # These fields are recorded after selection or belong only to dataset
    # attribution. They are unavailable to a policy deciding what to do next.
    metadata = {
        "split", "trace", "label_observed", "is_chosen", "reward_observed",
        "imitate_teacher", "imitation_weight", "run_id", "decision_id",
        "clip_id", "replay_id", "bot_guid", "candidate_index",
        "time_to_outcome_sec", "no_future_events", "ambiguous_label",
        "runtime_model_score", "runtime_model_rank", "runtime_model_features_hash",
        "decision_fingerprint_hash", "decision_fingerprint_repeat_count",
        "decision_fingerprint_failure_count",
    }
    features: dict[str, float] = {}
    for key, value in row.items():
        # stat_* comes from the final exported outcome-stat table, without a
        # decision-time snapshot. It can include this run's future outcomes.
        if key in labels or key in metadata or key.startswith(("json_outcome_", "json_chosen_", "stat_")):
            continue
        if isinstance(value, bool):
            features[key] = 1.0 if value else 0.0
        elif isinstance(value, (int, float)) and math.isfinite(float(value)):
            features[key] = float(value)
    return features
