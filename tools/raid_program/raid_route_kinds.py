"""Route kinds executed by the worldserver validation route runtime.

Dependency-free on purpose: ``canonical_route_catalog`` imports the live
validation runner, so the runner must import this constant from here (or
through ``canonical_route_catalog`` lazily) to avoid an import cycle.

``interaction`` rows carry native interaction/completion contracts and
``transport`` rows board an elevator-style platform; the worldserver manifest
loader parses both fail-closed.
"""

from __future__ import annotations


ALLOWED_ROUTE_KINDS: frozenset[str] = frozenset(
    {"trash", "boss", "travel", "regroup", "descent", "interaction", "transport"}
)
