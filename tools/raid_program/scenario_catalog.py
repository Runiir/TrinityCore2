"""Resolve supported boss/mode requests and bind existing, unpromoted inputs."""
from __future__ import annotations

import re
from pathlib import Path

from tools.raid_program.development_graph import GraphError, digest, read

CONFIG = Path('experiments/configs')
STRATEGIES = CONFIG / 'cata_raid_strategy_catalog_v1.json'
READINESS = CONFIG / 'cata_raid_script_readiness_v1.json'
ROSTER = CONFIG / 'cata_raid_roster_25_v1.json'
SHARDS = CONFIG / 'cata_raid_bwd_diagnostic_shards_v1.json'
TARGETS = CONFIG / 'all_spec_targets_cata_p4_v1.json'
REFERENCES = CONFIG / 'wowsims_cata_dps_reference_requests_v1.json'
ROUTES = CONFIG / 'validation_scenarios_cata_001.json'
COMPOSITIONS = CONFIG / 'raid_compositions'
PREREQUISITES = CONFIG / 'raid_prerequisites'
ALIASES = {'omnotron': 'omnotron_defense_system', 'halfus': 'halfus_wyrmbreaker',
           'beth tilac': 'bethtilac', 'cho gall': 'chogall', 'al akir': 'alakir',
           'zonozz': 'warlord_zonozz', 'yorsahj': 'yorsahj_the_unsleeping'}


def words(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def mode_name(value: str) -> str:
    match = re.fullmatch(r'(10|25)\s*(?:(?:player|man)\s*)?(normal|heroic|hc|n|h)', words(value))
    if not match:
        raise GraphError('explicit supported mode required: 10N, 10HC, 25N or 25HC')
    return match[1] + ('N' if match[2] in ('normal', 'n') else 'H')


def resolve(root: Path, request: str, mode: str | None = None, raid: str | None = None) -> dict:
    catalog = read(root / STRATEGIES)
    text = words(request)
    matches = list(re.finditer(r'(?<!\w)(10|25)\s*(?:(?:player|man)\s*)?(normal|heroic|hc|n|h)(?!\w)', text))
    if len(matches) > 1:
        raise GraphError('request contains multiple difficulties; select one scenario')
    embedded = mode_name(matches[0][0]) if matches else None
    chosen = mode_name(mode) if mode else embedded
    if not chosen or (embedded and embedded != chosen):
        raise GraphError('missing or conflicting raid size/difficulty')
    if matches:
        text = text[:matches[0].start()] + text[matches[0].end():]
    text = re.sub(r'^(implement|continue|resume|start)\s+', '', text.strip())
    text = re.sub(r'\s+bots?$', '', text).strip()
    boss = ALIASES.get(text, text.replace(' ', '_'))
    raids = catalog['raids']
    rows = [(r, b) for r, value in raids.items() for b in value['bosses']
            if b['boss_slug'] == boss and (raid is None or words(r) == words(raid))]
    if len(rows) != 1:
        raise GraphError('unknown or ambiguous boss/raid: ' + text)
    raid_id, strategy = rows[0]
    if chosen not in strategy.get('modes', []):
        raise GraphError('unsupported boss difficulty: ' + boss + ':' + chosen)
    return {'raid': raid_id, 'boss': boss, 'mode': chosen}


def key(encounter: dict) -> str:
    return ':'.join(encounter[k] for k in ('raid', 'boss', 'mode'))


def ref(root: Path, path: str | Path) -> dict | None:
    relative = Path(path)
    resolved = (root / relative).resolve()
    if relative.is_absolute() or not resolved.is_relative_to(root.resolve()):
        raise GraphError('catalog path outside repository')
    if not resolved.is_file():
        return None
    return {'path': relative.as_posix(), 'sha256': digest(resolved.read_bytes())}


def document(root: Path, path: Path) -> dict:
    return read(root / path) if (root / path).is_file() else {}


def composition_roster(root: Path, raid: str, mode: str, boss: str) -> dict | None:
    """Copy-0 actors of the canonical composition that declares this raid/mode/boss.

    Actor IDs are the deterministic raid-shard character GUIDs; the selected
    spec per boss comes from the composition. The cohort and scenario IDs use
    the package-A native boss key (raid_shard_plan.join_bosses), exactly as
    the generated plan does. Presence is not provisioning.
    """
    from tools.raid_program import raid_shard_identity as ids
    from tools.raid_program.raid_shard_plan import ShardPlanError, join_bosses, validate_prerequisites

    directory = root / COMPOSITIONS
    matches = []
    for path in sorted(directory.glob('*.json')) if directory.is_dir() else []:
        composition = read(path)
        if composition.get('raid') != raid or composition.get('mode') != mode:
            continue
        for row in composition.get('bosses', []):
            matches.append((path, composition, row))
    if not matches:
        return None
    prerequisite_path = PREREQUISITES / f'{raid}.json'
    if not (root / prerequisite_path).is_file():
        raise GraphError('raid composition declared without its prerequisite graph: ' + prerequisite_path.as_posix())
    try:
        native_by_path = {}
        for path, composition, _row in matches:
            if path not in native_by_path:
                bosses = validate_prerequisites(read(root / prerequisite_path), raid, mode, int(composition['map_id']))
                native_by_path[path] = {key: value['key'] for key, value in join_bosses(composition, bosses).items()}
    except ShardPlanError as error:
        raise GraphError('raid composition does not bind to its prerequisite graph: ' + str(error)) from error
    matches = [(path, composition, row) for path, composition, row in matches
               if boss in {row['boss_key'], native_by_path[path][row['boss_key']], *row.get('aliases', [])}]
    if not matches:
        return None
    if len(matches) != 1:
        raise GraphError('ambiguous raid composition for ' + raid + ':' + boss + ':' + mode)
    path, composition, row = matches[0]
    native_key = native_by_path[path][row['boss_key']]
    targets = {t['spec_target_id']: t for t in read(root / composition['spec_source']).get('targets', [])}
    selection = row.get('spec_selection', {})
    actors = []
    for character in composition['characters']:
        specs = character['specs']
        spec = selection[character['character_key']] if len(specs) > 1 else specs[0]
        if spec not in specs or spec not in targets:
            raise GraphError('composition spec selection invalid for ' + boss)
        packed = ids.packed_index(raid, mode, int(row['boss_number']), 0, int(character['slot']))
        actors.append({'actor_id': str(ids.character_guid(packed)), 'slot': character['character_key'],
                       'class_spec': spec, 'role': targets[spec]['role']})
    return {'path': path.relative_to(root), 'prerequisites': prerequisite_path, 'actors': actors,
            'native_boss_key': native_key, 'scenario_id': ids.pool_tag(ids.cohort_id(raid, mode, native_key, 0))}


def discover(root: Path, encounter: dict) -> dict:
    """Bind catalog observations. Presence is never research/live acceptance."""
    raid, boss, mode = (encounter[k] for k in ('raid', 'boss', 'mode'))
    strategies = read(root / STRATEGIES)
    strategy = next(b for b in strategies['raids'][raid]['bosses'] if b['boss_slug'] == boss)
    contract_ref = ref(root, strategy['contract'])
    contract = read(root / contract_ref['path']) if contract_ref else {}
    ledger_ref = ref(root, strategy['ledger'])
    readiness = document(root, READINESS)
    raid_scripts = next((r for r in readiness.get('raids', []) if r['raid'] == raid), {})
    native_boss = 'hagara_the_stormbinder' if boss == 'hagara' else boss
    script = next((b for b in raid_scripts.get('encounters', []) if b['boss'] == native_boss), {})
    source = (Path(raid_scripts['instance_source']).parent / script['source']).as_posix() if script.get('source') and raid_scripts.get('instance_source') else None
    native_ref = ref(root, source) if source else None
    # The audit is a snapshot. A stale hash is a work item, not a refreshed claim.
    from tools.raid_program.raid_workloop import script_readiness_source_tree_sha256
    current_audit = script_readiness_source_tree_sha256(readiness, root) if readiness else None
    audit_current = bool(current_audit and current_audit == readiness.get('source_tree_sha256'))
    sources = {str(p): ref(root, p) for p in (STRATEGIES, READINESS, ROSTER, SHARDS, TARGETS, REFERENCES, ROUTES)}
    for p in (strategy['contract'], strategy['ledger'], strategy['dossier']):
        sources[str(p)] = ref(root, p)
    if source:
        sources[source] = native_ref
    if raid_scripts.get('instance_source'):
        sources[raid_scripts['instance_source']] = ref(root, raid_scripts['instance_source'])
    size = int(mode[:-1])
    shard = None
    shard_boss = 'omnotron' if boss == 'omnotron_defense_system' else boss
    # These declared shard records have explicit 10N authority. Never relabel
    # their roster, route, profile or GUIDs as a heroic/25-player scenario.
    if raid == 'blackwing_descent' and mode == '10N':
        shard = next((s for s in document(root, SHARDS).get('shards', []) if s['boss_key'] == shard_boss), None)
    # The accepted legacy BWD 10N shards keep precedence in round 1; other
    # encounters bind the canonical composition when one declares them.
    composition = None if shard else composition_roster(root, raid, mode, boss)
    if shard:
        for bot in shard['bots']:
            if bot.get('pool_tag') != shard.get('pool_tag') or bot.get('runtime_profile_id') != shard.get('runtime_profile_id'):
                raise GraphError('bot identity disagrees with declared shard pool/profile')
        actors = [{'actor_id': str(b['character_guid']), 'slot': b['canonical_roster_slot_id'],
                   'class_spec': b['class_spec'], 'role': b['role']} for b in shard['bots']]
        roster_source = sources[str(SHARDS)]
        roster_state = 'declared_diagnostic_roster_requires_current_readback'
    elif composition:
        actors = composition['actors']
        sources[str(composition['path'])] = ref(root, composition['path'])
        sources[str(composition['prerequisites'])] = ref(root, composition['prerequisites'])
        roster_source = sources[str(composition['path'])]
        roster_state = 'declared_canonical_composition_requires_generated_plan_and_readback'
    elif size == 25 and sources[str(ROSTER)]:
        slots = read(root / ROSTER)['slots']
        actors = [{'actor_id': s['slot'], 'slot': s['slot'], 'class_spec': s['class_spec'], 'role': s['role']} for s in slots]
        roster_source = sources[str(ROSTER)]
        roster_state = 'frozen_logical_slots_need_encounter_assignments_and_native_guid_binding'
    else:
        actors = [{'actor_id': f'unassigned_{i+1:02}', 'slot': f'unassigned_{i+1:02}', 'class_spec': None, 'role': None} for i in range(size)]
        roster_source = None
        roster_state = 'missing_exact_roster_do_not_guess_composition'
    if len(actors) != size or len({a['actor_id'] for a in actors}) != size:
        raise GraphError('catalog roster count/identity does not match requested size')
    requests = document(root, REFERENCES)
    by_spec = {r['target_spec']: r for r in requests.get('requests', [])}
    target_specs = {r['spec_target_id'] for r in document(root, TARGETS).get('targets', [])}
    references = {}
    for actor in actors:
        spec = actor['class_spec']
        if spec in references or spec is None:
            continue
        request = by_spec.get(spec)
        references[spec] = {
            'role': actor['role'], 'target_definition_present': spec in target_specs,
            'reference_class': requests.get('reference_class') if request else None,
            'provider_revision': requests.get('provider_revision') if request else None,
            'request_sha256': request.get('request_sha256') if request else None,
            'source_contract_sha256': request.get('source_contract_sha256') if request else None,
            'status': 'pinned_request_requires_exact_native_setup_match' if request else
                      ('role_harness_required' if actor['role'] in ('tank', 'healer') else 'missing_simulator_reference'),
        }
    runtime = {'status': 'missing_exact_runtime_scenario', 'scenario_id': None, 'profile_id': None, 'pool_tag': None}
    if shard:
        routes = document(root, ROUTES)
        route = next((r for r in routes.get('diagnostic_scenarios', []) if r['id'] == shard['scenario_id']), None)
        if route:
            if (route.get('difficulty') != 'normal_10man'
                or route.get('runtime_profile_id') != shard['runtime_profile_id']
                or route.get('provisioning_scenario_id') != shard['scenario_id']
                or not any(n.get('kind') == 'boss' and n.get('node_id') == f'bwd.{shard_boss}.encounter' for n in route.get('route', []))):
                raise GraphError('route boss/difficulty/profile/provisioning disagrees with shard')
            runtime = {'status': 'declared_requires_generated_assets_and_native_admission', 'scenario_id': shard['scenario_id'],
                       'profile_id': shard['runtime_profile_id'], 'pool_tag': shard['pool_tag']}
    elif composition:
        scenario_id = composition['scenario_id']
        route = next((r for r in document(root, ROUTES).get('diagnostic_scenarios', []) if r['id'] == scenario_id), None)
        runtime = {'status': ('declared_requires_generated_assets_and_native_admission' if route
                              else 'missing_exact_runtime_scenario'),
                   'scenario_id': scenario_id if route else None,
                   'profile_id': scenario_id if route else None,
                   'pool_tag': scenario_id if route else None}
    return {'encounter': encounter, 'sources': sources, 'research': {
        'dossier': strategy['dossier'], 'contract': contract_ref, 'ledger': ledger_ref,
        'fidelity_state': contract.get('fidelity_state', strategy.get('fidelity_state')),
        'unresolved_material_count': contract.get('unresolved_material_count'),
        'mode_observations': contract.get('mode_matrix', {}).get(mode),
        'accepted': False},
        'script': {'source': source, 'source_present': native_ref is not None,
                   'catalog_status': script.get('status', 'missing_audit'), 'audit_current': audit_current,
                   'task': 'implement_missing_boss_script' if native_ref is None or script.get('status') == 'missing_dedicated_implementation' else 'audit_and_validate_existing_script'},
        'roster': {'source': roster_source, 'status': roster_state, 'size': size, 'actors': actors},
        'references': references, 'runtime': runtime,
        'binding_use': 'initialization_provenance_only_current_plans_bind_reviewed_inputs',
        'accepted': False, 'launch_authorized': False}
