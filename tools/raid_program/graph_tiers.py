"""Risk tiers: which development steps a unit must pass before measurement.

profile        rotation/profile, SQL data, config: tests + one scoreboard batch.
               Builds only when native source differs from the plan's reusable build.
class_native   class/spec C++: + independent review (separate session) + build.
shared_runtime shared bot runtime, arbitration, harness/validation tooling:
               + independent review + build + one smoke kill before measurement.

Units without a tier keep the pre-tier steps (identical to class_native).
Plan-drift review and model advice are never steps.
"""
from __future__ import annotations

from pathlib import PurePosixPath

TIERS = ('profile', 'class_native', 'shared_runtime')
DEFAULT_TIER = 'class_native'
ORDER = ('diagnose', 'implement', 'review', 'build', 'smoke', 'validate', 'assess', 'publish', 'route')
SKIPPED = {'profile': ('review', 'smoke'), 'class_native': ('smoke',), 'shared_runtime': ()}
CONDITIONAL = {'profile': {'build': 'only when native source differs from the plan reuse_build (or none is given)'}}
# Operations with side effects or shared resources need an owner before they run.
CLAIMED = ('implement', 'build', 'smoke', 'validate', 'publish')


def steps(tier: str) -> tuple[str, ...]:
    return tuple(stage for stage in ORDER if stage not in SKIPPED[tier])


def tier_of(g: dict) -> str:
    """The admitted plan may set the tier; otherwise the unit's, then the legacy default."""
    return ((g.get('assignment') or {}).get('risk_tier') or (g.get('unit') or {}).get('risk_tier')
            or DEFAULT_TIER)


def successors(stage: str, tier: str) -> tuple[str, ...]:
    """Legal advance targets; a conditional step may be skipped."""
    order = steps(tier) if tier in TIERS else ()
    if stage not in order or stage == order[-1]:
        return ()
    following = order[order.index(stage) + 1]
    if following in CONDITIONAL.get(tier, {}):
        return following, order[order.index(stage) + 2]
    return (following,)


def remaining(stage: str, tier: str) -> dict:
    order = steps(tier)
    left = list(order[order.index(stage):]) if stage in order else []
    return {'risk_tier': tier, 'remaining_steps': left, 'skipped_steps': list(SKIPPED[tier]),
            'conditional_steps': {k: v for k, v in CONDITIONAL.get(tier, {}).items() if k in left}}


def native_path(path: str) -> bool:
    """A path compiled into worldserver; SQL/config/JSON are not."""
    from tools.raid_program.build_control_compatibility import BUILD_ROOT_FILES, NATIVE_ROOTS
    name = PurePosixPath(path)
    return (path.startswith(NATIVE_ROOTS) or path in BUILD_ROOT_FILES
            or name.name == 'CMakeLists.txt' or name.suffix == '.cmake')
