"""Risk tiers: which development steps a unit must pass before measurement.

profile        rotation/profile, SQL data, config: tests + one scoreboard batch.
               Builds only when native source differs from the plan's reusable build.
class_native   class/spec C++: + independent review (separate session) + build.
shared_runtime shared bot runtime, arbitration, harness/validation tooling and the
               measurement/acceptance inputs: + review + build + one smoke kill.

The effective tier is the highest of the unit tier, the plan tier and a floor
derived from the unit's owned and supporting files; a plan can raise a tier but
never lower it. Units with no declared tier keep the pre-tier steps
(class_native) unless their files demand more. Plan-drift review and model
advice are never steps.
"""
from __future__ import annotations

from pathlib import PurePosixPath

TIERS = ('profile', 'class_native', 'shared_runtime')
RANK = {tier: rank for rank, tier in enumerate(TIERS)}
DEFAULT_TIER = 'class_native'
ORDER = ('diagnose', 'implement', 'review', 'build', 'smoke', 'validate', 'assess', 'publish', 'route')
SKIPPED = {'profile': ('review', 'smoke'), 'class_native': ('smoke',), 'shared_runtime': ()}
CONDITIONAL = {'profile': {'build': 'only when native source differs from the plan reuse_build (or none is given)'}}
# Operations with side effects or shared resources need an owner before they run.
CLAIMED = ('implement', 'build', 'smoke', 'validate', 'publish')

BOTS = 'src/server/game/Bots/'
# Shared bot runtime: action arbitration, spell queue, the per-bot update loop,
# and movement/recovery execution used by every class.
SHARED_RUNTIME_PREFIXES = tuple(BOTS + name for name in (
    'BotActionArbiter', 'BotActionExecutor', 'BotMovementArbiter', 'BotNativeMovementOutcome',
    'BotSpellQueue', 'BotWorldPopulationMgrSpellQueue', 'BotWorldPopulationMgrUpdateBot',
    'BotWorldPopulationMgrMovement', 'BotWorldPopulationMgrCombatMovement', 'BotControllerMovement',
    'BotWorldPopulationMgrNativeRecovery', 'BotWorldPopulationMgrRecovery',
    'BotWorldPopulationMgrValidationRecovery', 'BotWorldPopulationMgrValidationRoute'))
# Inputs that decide what is measured and accepted.
MEASUREMENT_PREFIXES = ('tools/bot_ml/run_live_bot_validation', 'tools/bot_ml/live_validation_',
                        'tools/raid_program/scoreboard', 'tools/raid_program/graph_acceptance.py',
                        'experiments/configs/raid_targets/')
WCL_MANIFEST_ROOT = 'experiments/configs/cata_raid_encounters/'


def steps(tier: str) -> tuple[str, ...]:
    return tuple(stage for stage in ORDER if stage not in SKIPPED[tier])


def native_path(path: str) -> bool:
    """A path compiled into worldserver; SQL/config/JSON are not."""
    from tools.raid_program.build_control_compatibility import BUILD_ROOT_FILES, NATIVE_ROOTS
    name = PurePosixPath(path)
    return (path.startswith(NATIVE_ROOTS) or path in BUILD_ROOT_FILES
            or name.name == 'CMakeLists.txt' or name.suffix == '.cmake')


def path_tier(path: str) -> str | None:
    """Minimum tier a change to this path requires; None when any tier may own it."""
    if (path.startswith(SHARED_RUNTIME_PREFIXES) or path.startswith(MEASUREMENT_PREFIXES)
            or (path.startswith(WCL_MANIFEST_ROOT) and 'wcl' in PurePosixPath(path).name.lower())):
        return 'shared_runtime'
    return 'class_native' if native_path(path) else None


def path_floor(paths) -> dict:
    """Highest tier demanded by the paths, with the paths that demand it."""
    demands = {path: path_tier(path) for path in paths}
    tiers = [tier for tier in demands.values() if tier]
    if not tiers:
        return {'tier': None, 'paths': []}
    top = max(tiers, key=RANK.__getitem__)
    return {'tier': top, 'paths': sorted(path for path, tier in demands.items() if tier == top)}


def floor_of(g: dict) -> dict:
    assignment = g.get('assignment') or {}
    return path_floor([*assignment.get('owned_files', []), *assignment.get('supporting_files', {})])


def declared_tier(g: dict) -> str:
    """Highest declared unit/plan tier; the legacy default when neither declares one."""
    declared = [t for t in ((g.get('unit') or {}).get('risk_tier'), (g.get('assignment') or {}).get('risk_tier')) if t]
    return max(declared, key=RANK.__getitem__) if declared else DEFAULT_TIER


def tier_of(g: dict) -> str:
    """max(unit tier, plan tier, path floor)."""
    floor = floor_of(g)['tier']
    declared = declared_tier(g)
    return floor if floor and RANK[floor] > RANK[declared] else declared


def successors(stage: str, tier: str) -> tuple[str, ...]:
    """Legal advance targets; a conditional step may be skipped."""
    order = steps(tier) if tier in TIERS else ()
    if stage not in order or stage == order[-1]:
        return ()
    following = order[order.index(stage) + 1]
    if following in CONDITIONAL.get(tier, {}):
        return following, order[order.index(stage) + 2]
    return (following,)


def describe(g: dict, stage: str) -> dict:
    """Effective tier, what raised it, and the steps left from this stage."""
    tier = tier_of(g)
    order = steps(tier)
    left = list(order[order.index(stage):]) if stage in order else []
    result = {'risk_tier': tier, 'remaining_steps': left, 'skipped_steps': list(SKIPPED[tier]),
              'conditional_steps': {k: v for k, v in CONDITIONAL.get(tier, {}).items() if k in left},
              'declared': {'unit': (g.get('unit') or {}).get('risk_tier'),
                           'plan': (g.get('assignment') or {}).get('risk_tier')}}
    if tier != declared_tier(g):
        result['raised_by_paths'] = floor_of(g)['paths'][:8]
    return result
