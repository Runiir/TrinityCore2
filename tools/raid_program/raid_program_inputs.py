"""Derive a raid program's boss-shard units and end-to-end unit from data files.

Read-only. Bosses come from the prerequisite DAG
(``experiments/configs/raid_prerequisites/<raid>.json``); each boss is bound to
its strategy-catalog row, script-readiness row, canonical composition boss,
cohort naming (``raid_shard_identity``), seeded-lockout plan
(``raid_prerequisites.seed_plan``), runtime scenario row and profile, raid
target, research contract and damage-fidelity registry. Anything absent is a
typed missing input with an owner skill; nothing here raises for a raid whose
inputs are incomplete. Per-raid facts live in data; this module holds none.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.raid_program import raid_prerequisites as prerequisites
from tools.raid_program import raid_shard_identity as ids
from tools.raid_program.development_graph import STATE_PATH as BOSS_STATE_PATH, digest
from tools.raid_program.scenario_catalog import ALIASES as BOSS_ALIASES
from tools.raid_program.scenario_catalog import READINESS, ROUTES, STRATEGIES, words

CONFIG = Path('experiments/configs')
PREREQUISITES = CONFIG / 'raid_prerequisites'
COMPOSITIONS = CONFIG / 'raid_compositions'
ROUTE_COMPOSITIONS = CONFIG / 'raid_route_compositions'
TARGETS = CONFIG / 'raid_targets'
PROFILES = Path('dataset/bot_runtime_profiles/profiles.json')
# The raid_shard_provisioning DVC stage writes <composition_id>/plan.json; shard_coordinator provisions
# canonical cohorts only when a run plan names it (raid_shard_plan).
PROVISIONING = Path('dataset/raid_shard_provisioning')
CONTENT_ROOT = Path('src/server/game/Bots/Content/Raids')
# Existing shard-infrastructure test modules (the shards packet's focused tests).
SHARD_TEST_GLOBS = ('test_raid_shard_*.py', 'test_raid_route_composer*.py', 'test_raid_prerequisites*.py',
                    'test_raid_composition*.py')
BLOCKS_RUN, BLOCKS_ACCEPTANCE = 'run', 'acceptance'
# Owner priority when a unit has several missing inputs: the earliest blocks most.
OWNER_ORDER = ('raid-encounter-implementation', 'raid-shard-architecture', 'raid-encounter-research',
               'raid-tuning-playbook')


def read_json(root: Path, relative: Path) -> dict:
    try:
        value = json.loads((root / relative).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def mode_token(mode: str) -> str:
    return mode[:-1] + mode[-1].lower()


def camel(key: str) -> str:
    return ''.join(part[:1].upper() + part[1:] for part in re.split(r'[^a-z0-9]+', key.lower()) if part)


def missing(name: str, detail: str, owner: str, blocks: str, **extra: Any) -> dict:
    return {'input': name, 'detail': detail, 'owner_skill': owner, 'blocks': blocks, **extra}


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r'[^a-z0-9]+', value.lower()) if token]


def bind_name(candidates: list[str], names: list[str]) -> str | None:
    """The one name matching any candidate exactly, by token set, or by leading tokens."""
    for rule in ('exact', 'set', 'prefix'):
        found = set()
        for name in names:
            for candidate in candidates:
                left, right = _tokens(candidate), _tokens(name)
                if not left or not right:
                    continue
                if (rule == 'exact' and left == right or rule == 'set' and sorted(left) == sorted(right)
                        or rule == 'prefix' and (right[:len(left)] == left or left[:len(right)] == right)):
                    found.add(name)
        if len(found) == 1:
            return found.pop()
        if found:
            return None
    return None


def _composition(root: Path, raid: str, mode: str) -> tuple[Path | None, dict, list[str]]:
    directory = root / COMPOSITIONS
    matches = []
    for path in sorted(directory.glob('*.json')) if directory.is_dir() else []:
        doc = read_json(root, path.relative_to(root))
        if doc.get('raid') == raid and doc.get('mode') == mode:
            matches.append((path.relative_to(root), doc))
    if len(matches) != 1:
        return None, {}, [p.as_posix() for p, _ in matches]
    return matches[0][0], matches[0][1], []


def _composition_bosses(composition: dict, bosses_by_key: dict) -> tuple[dict, str | None]:
    """native boss key -> composition boss row, or the binding failure."""
    if not composition:
        return {}, None
    from tools.raid_program.raid_shard_plan import ShardPlanError, join_bosses
    try:
        joined = join_bosses(composition, bosses_by_key)
    except (ShardPlanError, KeyError, TypeError, ValueError) as error:
        return {}, str(error)[:300]
    rows = {row['boss_key']: row for row in composition.get('bosses') or []}
    return {native['key']: rows[key] for key, native in joined.items()}, None


def _composition_failure(composition: dict) -> str | None:
    if not composition:
        return None
    from tools.raid_program.raid_composition import CompositionError, load_catalog, validate_composition
    try:
        validate_composition(composition, load_catalog(composition))
    except (CompositionError, OSError, KeyError, TypeError, ValueError) as error:
        return str(error)[:300]
    return None


def _scenario_rows(root: Path) -> dict[str, dict]:
    config = read_json(root, ROUTES)
    return {str(row.get('id')): row for group in ('scenarios', 'diagnostic_scenarios')
            for row in config.get(group) or [] if isinstance(row, dict) and row.get('id')}


def _profiles(root: Path) -> dict[str, dict]:
    profiles = read_json(root, PROFILES).get('profiles') or []
    if isinstance(profiles, dict):
        return {str(name): row for name, row in profiles.items() if isinstance(row, dict)}
    return {str(row['name']): row for row in profiles if isinstance(row, dict) and row.get('name')}


def _boss_graph(root: Path) -> dict[str, dict]:
    """Boss-level development graphs by scenario key (read-only reference)."""
    state = read_json(root, BOSS_STATE_PATH)
    graphs = {}
    for where, saved in [('active', state), *(('parked', value) for value in (state.get('parked_scenarios') or {}).values())]:
        graph = (saved or {}).get('development_graph') if isinstance(saved, dict) else None
        if not isinstance(graph, dict) or not isinstance(graph.get('encounter'), dict):
            continue
        key = ':'.join(str(graph['encounter'].get(k)) for k in ('raid', 'boss', 'mode'))
        open_count = sum(1 for row in (graph.get('requirements') or {}).values()
                         if isinstance(row, dict) and row.get('status') == 'open')
        graphs[key] = {'where': where, 'stage': graph.get('stage'), 'open_requirements': open_count,
                       'unit': (graph.get('unit') or {}).get('id')}
    return graphs


def _raid_target(root: Path, raid: str, token: str, names: list[str]) -> dict:
    scenarios = list(dict.fromkeys(f'{raid}_{token}_{name}' for name in names if name))
    present = [scenario for scenario in scenarios if (root / TARGETS / f'{scenario}.json').is_file()]
    scenario = present[0] if len(present) == 1 else scenarios[0]
    return {'scenario': scenario, 'path': (TARGETS / f'{scenario}.json').as_posix(),
            'present': len(present) == 1, 'ambiguous': len(present) > 1}


def _damage_fidelity(root: Path, raid: str, mode: str, names: list[str]) -> dict:
    from tools.bot_ml.live_validation_fidelity import scenario_damage_fidelity
    result = {'closable': False, 'reason': 'no boss entry of this scenario is in the registry'}
    for name in dict.fromkeys(n for n in names if n):
        result = scenario_damage_fidelity(root, {'raid': raid, 'boss': name, 'mode': mode})
        if result.get('boss_entries'):
            break
    return {'closable': bool(result.get('closable')), 'reason': result.get('reason')}


def _source_refs(root: Path, paths: list[Path]) -> dict[str, str | None]:
    refs = {}
    for relative in paths:
        path = root / relative
        refs[relative.as_posix()] = digest(path.read_bytes()) if path.is_file() else None
    return refs


def discover_program(root: Path, raid: str, mode: str) -> dict:
    """Current per-boss and end-to-end readiness of one raid program (read-only)."""
    token = mode_token(mode)
    prerequisite_path = PREREQUISITES / f'{raid}.json'
    doc = read_json(root, prerequisite_path)
    raid_inputs: list[dict] = []
    failure = prerequisites.validate(doc) if doc else 'prerequisite_graph_missing'
    if failure:
        raid_inputs.append(missing('prerequisite_graph', f'{prerequisite_path.as_posix()}: {failure}',
                                   'raid-shard-architecture', BLOCKS_RUN, path=prerequisite_path.as_posix()))
    elif doc.get('verification_level') != 'native_script_verified':
        # The shards packet owns the prerequisite file, so it verifies it.
        raid_inputs.append(missing('prerequisite_graph_unverified', f"verification_level={doc.get('verification_level')}; "
                                   + '; '.join(map(str, doc.get('unverified') or []))[:600],
                                   'raid-shard-architecture', BLOCKS_ACCEPTANCE, path=prerequisite_path.as_posix()))
    strategy_raid = (read_json(root, STRATEGIES).get('raids') or {}).get(raid) or {}
    strategy_rows = {str(row['boss_slug']): row for row in strategy_raid.get('bosses') or [] if row.get('boss_slug')}
    if not strategy_rows:
        raid_inputs.append(missing('strategy_catalog', f'{STRATEGIES.as_posix()} has no {raid} bosses',
                                   'raid-encounter-research', BLOCKS_ACCEPTANCE))
    readiness = read_json(root, READINESS)
    readiness_raid = next((row for row in readiness.get('raids') or [] if row.get('raid') == raid), {})
    from tools.raid_program.raid_workloop import script_readiness_source_tree_sha256
    audit = script_readiness_source_tree_sha256(readiness, root) if readiness else None
    audit_current = bool(audit and audit == readiness.get('source_tree_sha256'))
    if not audit_current:
        raid_inputs.append(missing('script_readiness_audit', f'{READINESS.as_posix()} source_tree_sha256 is stale; '
                                   're-audit the native scripts', 'raid-encounter-research', BLOCKS_ACCEPTANCE))
    composition_path, composition, duplicates = _composition(root, raid, mode)
    if duplicates:
        raid_inputs.append(missing('composition', 'more than one composition declares this raid/mode: ' + ', '.join(duplicates),
                                   'raid-shard-architecture', BLOCKS_RUN))
    elif not composition:
        raid_inputs.append(missing('composition', f'no {COMPOSITIONS.as_posix()}/*.json declares {raid} {mode} '
                                   '(one canonical composition per raid)', 'raid-shard-architecture', BLOCKS_RUN))
    composition_failure = _composition_failure(composition)
    if composition_failure:
        raid_inputs.append(missing('composition', 'invalid: ' + composition_failure, 'raid-shard-architecture', BLOCKS_RUN,
                                   path=composition_path.as_posix()))
    all_bosses = [] if failure else sorted(doc['bosses'], key=lambda row: row['boss_index'])
    included = [row for row in all_bosses if token in prerequisites.boss_difficulties(doc, row)]
    excluded = [{'boss_key': row['key'], 'reason': f'not available on {token}'} for row in all_bosses if row not in included]
    by_key = {row['key']: row for row in all_bosses}
    composition_bosses, binding_failure = _composition_bosses(composition, by_key)
    if binding_failure:
        raid_inputs.append(missing('composition_binding', binding_failure, 'raid-shard-architecture', BLOCKS_RUN))
    generated_plan, generated = None, None
    if composition and composition.get('composition_id'):
        generated_plan = (PROVISIONING / str(composition['composition_id']) / 'plan.json').as_posix()
        document = read_json(root, Path(generated_plan))
        if document.get('schema') == 'raid_shard_plan_v1':
            generated = {str(row.get('scenario_id')) for row in document.get('shards') or [] if isinstance(row, dict)}
        else:
            raid_inputs.append(missing('generated_plan', f'{generated_plan} is missing or not a raid_shard_plan_v1: '
                                       'reproduce (or dvc pull) the raid_shard_provisioning stage', 'raid-shard-architecture',
                                       BLOCKS_RUN, path=generated_plan))
    scenarios, profiles, graphs = _scenario_rows(root), _profiles(root), _boss_graph(root)
    identity_known = raid in ids.RAID_NUMBERS
    if not identity_known:
        raid_inputs.append(missing('shard_identity', f'{raid} has no raid number in raid_shard_identity.RAID_NUMBERS',
                                   'raid-shard-architecture', BLOCKS_RUN))
    units = [_boss_unit(root, raid, mode, token, doc, row, strategy_rows, readiness_raid, composition,
                        composition_bosses.get(row['key']), scenarios, profiles, graphs, identity_known)
             for row in included]
    for unit in units:
        if generated is not None and unit['scenario_id'] not in generated:
            unit['missing_inputs'].append(missing('generated_plan_cohort', f"{generated_plan} has no cohort "
                                                  f"{unit['scenario_id']}; regenerate the raid_shard_provisioning stage",
                                                  'raid-shard-architecture', BLOCKS_RUN, path=generated_plan))
            unit['ready_to_run'], unit['acceptance_blocked'] = False, True
    sources = [prerequisite_path, STRATEGIES, READINESS, ROUTES, PROFILES]
    if composition_path:
        sources.append(composition_path)
    e2e = _e2e_unit(root, raid, mode, token, composition, units, scenarios, profiles)
    if composition.get('full_raid') and generated is not None and e2e['scenario_id'] not in generated:
        e2e['missing_inputs'].append(missing('e2e_generated_plan_cohort', f"{generated_plan} has no full-raid cohort "
                                             f"{e2e['scenario_id']}; regenerate the raid_shard_provisioning stage",
                                             'raid-shard-architecture', BLOCKS_RUN, path=generated_plan))
        e2e['ready_to_run'] = False
    if e2e.get('route_composition'):
        sources.append(Path(e2e['route_composition']))
    blockers = [item['input'] for item in raid_inputs if item['blocks'] == BLOCKS_RUN]
    for unit in [*units, e2e]:
        unit['raid_run_blockers'] = blockers
        unit['ready_to_run'] = unit['ready_to_run'] and not blockers
    shard_tests = sorted({path.relative_to(root).as_posix() for pattern in SHARD_TEST_GLOBS
                          for path in (root / 'tests').glob(pattern) if path.is_file()})
    return {'program_id': f'{raid}:{mode}', 'raid': raid, 'mode': mode, 'mode_token': token, 'shard_tests': shard_tests,
            'generated_plan': generated_plan,
            'size': int(mode[:-1]), 'name': doc.get('name') or raid, 'map_id': doc.get('map_id'),
            'prerequisites': prerequisite_path.as_posix(), 'composition': composition_path.as_posix() if composition_path else None,
            'raid_inputs': raid_inputs, 'units': units, 'excluded_bosses': excluded, 'e2e': e2e,
            'sources': _source_refs(root, sources)}


def _boss_unit(root, raid, mode, token, doc, row, strategy_rows, readiness_raid, composition, composition_boss,
               scenarios, profiles, graphs, identity_known) -> dict:
    key = row['key']
    inputs: list[dict] = []
    aliases = [*(composition_boss or {}).get('aliases', []), *((composition_boss or {}).get('boss_key'),)]
    candidates = [key, words(str(row.get('name') or '')), *[a for a in aliases if a],
                  *[slug for alias, slug in BOSS_ALIASES.items() if words(alias) == words(key)]]
    slug = bind_name(candidates, list(strategy_rows))
    strategy = strategy_rows.get(slug) if slug else None
    if not strategy:
        inputs.append(missing('strategy_catalog_row', f'no unique {STRATEGIES.as_posix()} row for {key}',
                              'raid-encounter-research', BLOCKS_ACCEPTANCE))
    elif mode not in (strategy.get('modes') or []):
        inputs.append(missing('strategy_mode', f'{slug} does not list {mode}', 'raid-encounter-research', BLOCKS_ACCEPTANCE))
    contract = read_json(root, Path(strategy['contract'])) if strategy and strategy.get('contract') else {}
    fidelity_state = contract.get('fidelity_state', (strategy or {}).get('fidelity_state'))
    if fidelity_state != 'accepted':
        inputs.append(missing('encounter_research', f'research contract fidelity_state={fidelity_state}; follow '
                              'raid-encounter-research (WCL references, unresolved claims)', 'raid-encounter-research',
                              BLOCKS_ACCEPTANCE, path=(strategy or {}).get('contract')))
    scripts = {str(e.get('boss')): e for e in readiness_raid.get('encounters') or [] if e.get('boss')}
    script_name = bind_name([slug or key, key], list(scripts))
    script = scripts.get(script_name) if script_name else None
    instance = Path(str(readiness_raid.get('instance_source') or ''))
    source = (instance.parent / script['source']).as_posix() if script and script.get('source') and readiness_raid else None
    source_present = bool(source and (root / source).is_file())
    if not source_present or (script or {}).get('status') == 'missing_dedicated_implementation':
        inputs.append(missing('native_script', f"native boss script missing ({(script or {}).get('status', 'no audit row')})",
                              'raid-encounter-implementation', BLOCKS_RUN, path=source))
    fidelity = _damage_fidelity(root, raid, mode, [slug, key])
    if not fidelity['closable']:
        inputs.append(missing('encounter_damage_fidelity', str(fidelity['reason']), 'raid-encounter-research', BLOCKS_ACCEPTANCE,
                              path='experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json'))
    target = _raid_target(root, raid, token, [slug, key])
    if not target['present']:
        inputs.append(missing('raid_target', ('more than one target file names this boss' if target['ambiguous'] else
                              f"author {target['path']} (raid_target_v1) from matched WCL kills"),
                              'raid-tuning-playbook', BLOCKS_ACCEPTANCE, path=target['path']))
    closure = prerequisites.predecessor_closure(doc, key)
    lockout = {'precompleted_boss_keys': closure, 'seed_boss_argument': prerequisites.seed_argument(closure),
               'fresh_instance': not closure, 'diagnostic_only_assistance': bool(closure),
               'certifies_predecessors': False, 'seedable': True, 'refusal': None}
    if closure:
        try:
            plan = prerequisites.seed_plan(doc, token, closure)
            lockout.update(boss_states=plan['boss_states'], completed_encounters_mask=plan['completed_encounters_mask'])
        except prerequisites.PrerequisiteError as error:
            lockout.update(seedable=False, refusal=str(error))
            inputs.append(missing('seeded_lockout', f'the seeder refuses {closure}: {error}', 'raid-encounter-research',
                                  BLOCKS_RUN, path=(PREREQUISITES / f'{raid}.json').as_posix()))
    cohort = ids.cohort_id(raid, mode, key, 0)
    scenario_id = ids.pool_tag(cohort)
    if composition and not composition_boss:
        inputs.append(missing('composition_boss', f'the {raid} {mode} composition has no boss row for {key}',
                              'raid-shard-architecture', BLOCKS_RUN))
    scenario = scenarios.get(scenario_id)
    boss_nodes = [str(node.get('node_id')) for node in (scenario or {}).get('route') or [] if node.get('kind') == 'boss']
    if not scenario:
        inputs.append(missing('runtime_scenario', f'no {ROUTES.as_posix()} row {scenario_id} for the canonical cohort',
                              'raid-shard-architecture', BLOCKS_RUN))
    elif not boss_nodes:
        inputs.append(missing('runtime_scenario', f'{scenario_id} route has no boss node', 'raid-shard-architecture', BLOCKS_RUN))
    if scenario_id not in profiles:
        inputs.append(missing('runtime_profile', f'no {PROFILES.as_posix()} profile {scenario_id}', 'raid-shard-architecture', BLOCKS_RUN))
    if not identity_known:
        inputs.append(missing('shard_identity', f'{raid} is not registered for shard identities', 'raid-shard-architecture', BLOCKS_RUN))
    owner = min((i['owner_skill'] for i in inputs), key=OWNER_ORDER.index, default=None)
    boss_scenario = f'{raid}:{slug}:{mode}' if slug else None
    return {'unit_id': f'raid:{raid}:{mode}:{key}', 'boss_key': key, 'boss_index': row['boss_index'],
            'name': row.get('name') or key, 'strategy_slug': slug, 'boss_scenario': boss_scenario,
            'boss_graph': graphs.get(boss_scenario) if boss_scenario else None,
            'cohort_id': cohort, 'scenario_id': scenario_id, 'runtime_profile_id': scenario_id, 'pool_tag': scenario_id,
            'lockout': lockout, 'boss_nodes': boss_nodes,
            'composition_boss': (composition_boss or {}).get('boss_key'),
            'spec_selection_status': (composition_boss or {}).get('selection_status'),
            'research': {'contract': (strategy or {}).get('contract'), 'fidelity_state': fidelity_state},
            'native_script': {'path': source, 'present': source_present, 'catalog_status': (script or {}).get('status')},
            'damage_fidelity': fidelity, 'raid_target': target,
            'files': _boss_files(raid, token, key, slug, strategy, source, target),
            'missing_inputs': inputs,
            'ready_to_run': not any(i['blocks'] == BLOCKS_RUN for i in inputs),
            'acceptance_blocked': bool(inputs), 'input_owner_skill': owner}


def _boss_files(raid, token, key, slug, strategy, source, target) -> dict:
    """Files a boss packet owns; derived from data paths and the repository layout.

    Both the native key and the strategy slug name a boss's research files, raid
    target, staged SQL and tests. The native script owns its split siblings
    (``boss_<stem>_*``) so a script can be divided below the line limit.
    """
    owned = [(CONTENT_ROOT / camel(raid) / 'Encounters' / camel(key)).as_posix() + '/**']
    for name in dict.fromkeys(n for n in (slug, key) if n):
        owned += [f'{CONFIG.as_posix()}/cata_raid_encounters/{raid}/{name}_*',
                  f'{TARGETS.as_posix()}/{raid}_{token}_{name}.json',
                  f'sql/custom/staged/world/*{name}*', f'tests/test_{name}_*.py']
    owned.append(target['path'])
    if source:
        path = Path(source)
        owned += [source, (path.parent / f'{path.stem}_*').as_posix()]
    if strategy and strategy.get('dossier'):
        owned.append(str(strategy['dossier']))
    tests = [f'tests/test_{key}_*.py'] + ([f'tests/test_{slug}_*.py'] if slug and not slug.startswith(key) else [])
    return {'owned': list(dict.fromkeys(owned)), 'focused_tests': 'pixi run python -m pytest -q ' + ' '.join(tests)}


def _e2e_unit(root, raid, mode, token, composition, units, scenarios, profiles) -> dict:
    """The end-to-end unit: the full-raid cohort's own identity, checked against the composed route.

    Scenario, runtime profile and pool tag come from the composition's ``full_raid`` cohort
    (``route_scenario_id``, ``runtime_profile_id``, ``pool_tag``; each defaults to ``cohort_id``)
    and must be one id, as shard_coordinator.preflight requires. The route composition only
    supplies the drift check and the boss nodes every e2e run must kill.
    """
    inputs: list[dict] = []
    path = ROUTE_COMPOSITIONS / f'{raid}_{token}.json'
    route = read_json(root, path)
    template, coverage = route.get('scenario_id'), {}
    expected_nodes: list[str] = []
    if not route:
        inputs.append(missing('route_composition', f'author {path.as_posix()} (raid_route_composition_v1) from the '
                              'reviewed boss node sets', 'raid-shard-architecture', BLOCKS_RUN, path=path.as_posix()))
    else:
        from tools.raid_program.raid_route_composer import RaidRouteCompositionError, compose, drift
        config = read_json(root, ROUTES)
        try:
            composed = compose(config, route)
            differences = drift(config, composed)
            if differences:
                inputs.append(missing('route_materialization', f'{len(differences)} differences between the composed '
                                      f'route and {template}; run raid_route_composer --check',
                                      'raid-shard-architecture', BLOCKS_RUN))
            kinds = {row['node_id']: row.get('kind') for row in composed.route}
            sets = {entry['id']: entry['node_ids'] for entry in composed.node_set_order}
            for unit in units:
                names = [unit['boss_key'], unit.get('composition_boss'), unit.get('strategy_slug')]
                nodes = next((sets[n] for n in names if n in sets), [])
                coverage[unit['boss_key']] = [n for n in nodes if kinds.get(n) == 'boss']
                if not coverage[unit['boss_key']]:
                    inputs.append(missing('route_boss_rows', f"the composed route has no boss node for {unit['boss_key']}",
                                          'raid-shard-architecture', BLOCKS_RUN))
            expected_nodes = sorted({node for nodes in coverage.values() for node in nodes})
        except (RaidRouteCompositionError, KeyError, TypeError, ValueError) as error:
            inputs.append(missing('route_composition', f'does not compose: {str(error)[:300]}', 'raid-shard-architecture', BLOCKS_RUN))
    full = composition.get('full_raid') if isinstance(composition.get('full_raid'), dict) else {}
    cohort = str(full.get('cohort_id') or ids.cohort_id(raid, mode, 'full', 0))
    scenario = str(full.get('route_scenario_id') or cohort)
    profile = str(full.get('runtime_profile_id') or cohort)
    pool = str(full.get('pool_tag') or cohort)
    if not full:
        inputs.append(missing('e2e_roster', 'the composition declares no full_raid entry, so the end-to-end run has no '
                              'canonical-composition cohort, profile or spec selection', 'raid-shard-architecture', BLOCKS_RUN))
    else:
        if len({scenario, profile, pool}) != 1:
            inputs.append(missing('e2e_identity', f'full_raid scenario {scenario}, profile {profile} and pool {pool} must be '
                                  'one id (shard_coordinator preflight)', 'raid-shard-architecture', BLOCKS_RUN))
        if full.get('scenario_id') and template and full['scenario_id'] != template:
            inputs.append(missing('e2e_route_template', f"full_raid.scenario_id {full['scenario_id']} is not the composed "
                                  f'route {template}', 'raid-shard-architecture', BLOCKS_RUN))
        row = scenarios.get(scenario)
        if row is None:
            inputs.append(missing('e2e_runtime_scenario', f'no {ROUTES.as_posix()} row {scenario} for the full-raid cohort',
                                  'raid-shard-architecture', BLOCKS_RUN))
        else:
            present = {str(node.get('node_id')) for node in row.get('route') or [] if node.get('kind') == 'boss'}
            absent = [node for node in expected_nodes if node not in present]
            if absent:
                inputs.append(missing('e2e_route_rows', f'{scenario} lacks composed boss nodes: ' + ', '.join(absent),
                                      'raid-shard-architecture', BLOCKS_RUN))
        if profile not in profiles:
            inputs.append(missing('e2e_runtime_profile', f'no {PROFILES.as_posix()} profile {profile}',
                                  'raid-shard-architecture', BLOCKS_RUN))
    return {'unit_id': f'raid:{raid}:{mode}:e2e', 'route_composition': path.as_posix() if route else None,
            'route_template_scenario_id': template, 'scenario_id': scenario, 'cohort_id': cohort,
            'runtime_profile_id': profile, 'pool_tag': pool, 'boss_nodes': coverage, 'expected_boss_nodes': expected_nodes,
            'missing_inputs': inputs, 'ready_to_run': not inputs, 'owner_skill': 'raid-shard-architecture' if inputs else None}
