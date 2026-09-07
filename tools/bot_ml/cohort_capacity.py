"""Strict native cohort-capacity and idle-registry checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def require_positive_cohort_capacity(value: Any) -> int:
    """Return a native capacity only when it is a strict positive integer."""
    if type(value) is not int or value < 1:
        raise ValueError("max_active_cohorts must be a positive integer")
    return value


def validate_idle_cohort_registry(registry: Any) -> int:
    """Validate the complete native registry and return its exact capacity."""
    if not isinstance(registry, Mapping):
        raise ValueError("cohort registry response is malformed")
    if registry.get("action") != "botauto_cohorts" or registry.get("ok") is not True:
        raise ValueError("cohort registry response is unknown or unsuccessful")

    capacity = require_positive_cohort_capacity(
        registry.get("max_active_cohorts")
    )
    active_count = registry.get("active_cohort_count")
    cohorts = registry.get("cohorts")
    if type(active_count) is not int or active_count != 0:
        raise ValueError("cohort registry is not idle")
    if not isinstance(cohorts, list) or not cohorts:
        raise ValueError("cohort registry response is malformed")
    for cohort in cohorts:
        if (
            not isinstance(cohort, Mapping)
            or not isinstance(cohort.get("cohort_id"), str)
            or not cohort["cohort_id"]
            or type(cohort.get("active")) is not bool
        ):
            raise ValueError("cohort registry response is malformed")
        if cohort["active"]:
            raise ValueError("cohort registry contains an active cohort")
    return capacity
