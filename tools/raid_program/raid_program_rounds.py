"""Round state machine of a raid program.

    plan -> implement -> build -> run -> (assess) -> plan of the next round
                                              \\-> e2e -> complete

``plan`` freezes one worker packet per open boss unit (plus the shard
infrastructure packet when needed); ``implement`` records one validated handoff
per packet; ``build`` configures and builds the committed tree once through
queued_build with the default policy; ``run`` writes shard run plans (every
ready shard in one worldserver, batches of shard_coordinator.MAX_SHARDS) and
records each shard_coordinator run; ``assess`` judges every boss (scoreboard
verdict where a raid target exists, typed stall otherwise) and opens the next
round, or the end-to-end unit once every boss unit is accepted. ``e2e`` runs
the composed full route on a fresh instance. No step launches agents or
servers; ``build`` is the only step that compiles.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from tools.raid_program import raid_program_packets as packets
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError, utc_now
from tools.raid_program.raid_program_inputs import discover_program

RUN_PLAN_SCHEMA = 'raid_shard_run_plan_v1'
RUN_SCHEMA = 'raid_shard_run_v1'
WORLDSERVER = Path('build/src/server/worldserver/worldserver')
E2E_KEY = 'e2e'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def active(state: dict) -> dict:
    return state['programs'][state['active_program']]


def current_round(program: dict) -> dict:
    if not program['rounds'] or program['rounds'][-1]['round'] != program['round']:
        raise GraphError('round ' + str(program['round']) + ' has not been planned')
    return program['rounds'][-1]


def _require(program: dict, stage: str) -> None:
    if program['stage'] != stage:
        raise GraphError(f"program stage is {program['stage']}, not {stage}; run raid_workloop resume")


def _load_active(root: Path) -> tuple[dict, dict]:
    state, _ = store.load(root)
    if state is None:
        raise GraphError('no raid program selected; run raid_workloop start "implement <raid> <mode> bots"')
    store.check(root, state)
    return state, active(state)


def _repo_ref(root: Path, path: Path) -> dict:
    resolved = path.resolve()
    data = resolved.read_bytes()
    shown = resolved.relative_to(root.resolve()).as_posix() if resolved.is_relative_to(root.resolve()) else str(resolved)
    return {'path': shown, 'sha256': sha256_bytes(data)}


def new_program(discovery: dict) -> dict:
    name, mode = discovery['name'], discovery['mode']
    return {
        'program_id': discovery['program_id'], 'raid': discovery['raid'], 'mode': mode, 'name': name,
        'objective': (f'Carry {name} {mode} bots to completion: every boss shard passes its scoreboard verdict '
                      '(WCL parity, native clears, no boss-window deaths) in parallel seeded lockouts with one build '
                      'per round, then the end-to-end clear of the composed full route with trash and interactions.'),
        'created_utc': utc_now(), 'revision': 0, 'stage': 'plan', 'round': 1,
        'bootstrap_sources': discovery['sources'],
        'units': {unit['boss_key']: _unit_record(unit) for unit in discovery['units']},
        'e2e': {'unit_id': discovery['e2e']['unit_id'], 'status': 'open', 'results': []},
        'rounds': [], 'history': []}


def _unit_record(unit: dict) -> dict:
    return {key: unit[key] for key in ('unit_id', 'boss_key', 'boss_scenario', 'cohort_id', 'scenario_id')} | {
        'status': 'open', 'results': []}


def select(root: Path, discovery: dict, expected_sha256: str | None = None) -> dict:
    """Select or create the program; parks the previous one intact (between rounds only)."""
    key = discovery['program_id']

    def reducer(state: dict | None) -> dict:
        if state is None:
            state = {'schema': store.SCHEMA, 'version': 1, 'coordinator_worktree': str(root.resolve()),
                     'focus': 'program', 'active_program': key, 'programs': {}}
        previous = state['programs'].get(state.get('active_program'))
        if previous and state['active_program'] != key and previous['stage'] not in store.SWITCHABLE_STAGES:
            raise GraphError(f"program {state['active_program']} is mid-round ({previous['stage']}); finish the round "
                             'before selecting another raid program')
        if key not in state['programs']:
            state['programs'][key] = new_program(discovery)
            store.history(state['programs'][key], 'created')
        state['active_program'], state['focus'] = key, 'program'
        return state
    return store.update(root, reducer, expected_sha256)


def plan(root: Path, bosses: list[str] | None = None, expected_sha256: str | None = None) -> dict:
    _, program = _load_active(root)
    _require(program, 'plan')
    discovery = discover_program(root, program['raid'], program['mode'])
    for unit in discovery['units']:
        program['units'].setdefault(unit['boss_key'], _unit_record(unit))
    e2e_due = all(unit['status'] == 'accepted' for unit in program['units'].values())
    failures = [result for result in program['e2e']['results'] if result['outcome'] != 'clear']
    built = packets.build_packets(discovery, program, bosses, e2e_due, failures[-1] if failures and e2e_due else None)

    def reducer(state: dict) -> dict:
        target = active(state)
        _require(target, 'plan')
        for unit in discovery['units']:
            target['units'].setdefault(unit['boss_key'], _unit_record(unit))
        if target['rounds'] and target['rounds'][-1]['round'] == target['round']:
            raise GraphError('round already planned')
        target['rounds'].append({'round': target['round'], 'planned_utc': utc_now(), 'packets': built,
                                 'build': None, 'run_plans': [], 'runs': [], 'assessment': None})
        target['stage'] = 'implement'
        store.history(target, 'plan', round=target['round'], packets=sorted(built))
        return state
    return store.update(root, reducer, expected_sha256)


def record_handoff(root: Path, packet_id: str, handoff_path: Path | None, abandon_reason: str | None = None,
                   expected_sha256: str | None = None, external_reason: str | None = None) -> dict:
    """Record a packet's handoff, an abandoned packet, or work done outside the program (``external``)."""
    _, program = _load_active(root)
    _require(program, 'implement')
    packet = current_round(program)['packets'].get(packet_id)
    if packet is None:
        raise GraphError('no packet ' + packet_id + ' in round ' + str(program['round']))
    if abandon_reason and external_reason:
        raise GraphError('a packet is either abandoned or done externally, not both')
    if abandon_reason or external_reason:
        kind = 'abandoned' if abandon_reason else 'external'
        record = {kind: True, 'reason': abandon_reason or external_reason, 'recorded_utc': utc_now()}
    else:
        if handoff_path is None or not handoff_path.is_file():
            raise GraphError('handoff file required (or --abandon REASON)')
        handoff = json.loads(handoff_path.read_text(encoding='utf-8'))
        packets.validate_handoff(handoff, packet, program['round'])
        record = _repo_ref(root, handoff_path) | {
            'recorded_utc': utc_now(), 'patch_requests': len(handoff['patch_requests']),
            'resolved_inputs': [str(name) for name in handoff['resolved_inputs']],
            'changed_files': sorted(set(handoff['changed_files'] + handoff['new_files']))}

    def reducer(state: dict) -> dict:
        target = active(state)
        _require(target, 'implement')
        row = current_round(target)['packets'][packet_id]
        row['handoff'] = record
        store.history(target, 'handoff', round=target['round'], packet=packet_id, abandoned=bool(abandon_reason),
                      external=bool(external_reason))
        if all(item['handoff'] for item in current_round(target)['packets'].values()):
            target['stage'] = 'build'
        return state
    return store.update(root, reducer, expected_sha256)


def build_policy(root: Path) -> tuple[Path, dict, dict]:
    """queued_build's default policy (never a literal job count) and its exact argv."""
    from tools.raid_program import queued_build as queue
    from tools.raid_program.workflow_build import build_commands
    policy = json.loads((root / queue.DEFAULT_POLICY_RELATIVE).read_text(encoding='utf-8'))
    try:
        return queue.DEFAULT_POLICY_RELATIVE, policy, build_commands(policy)
    except RuntimeError as error:
        raise GraphError('build policy rejected: ' + str(error)) from error


def _queue_runner(root: Path, policy: dict, kind: str, command: list[str]) -> tuple[int, dict, str, bool]:
    from tools.raid_program import queued_build as queue
    with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet):
        code, receipt = queue.run_ticket(root, policy, kind, command, None, None, None)
    path = queue.Paths.for_worktree(root).receipts / (receipt['ticket_id'] + '.json')
    gate = False
    if not code and receipt.get('classification') == 'success':
        gate = queue.verify_receipt(path, policy, allow_test_mode=False).get('gate_bearing') is True
    return code, receipt, str(path), gate


def build(root: Path, expected_sha256: str | None = None, dry_run: bool = False,
          runner: Callable[..., tuple[int, dict, str, bool]] | None = None,
          worktree_state: Callable[[Path], dict] | None = None) -> dict:
    """One configure + worldserver build of the committed tree for the whole round."""
    from tools.raid_program import queued_build as queue
    state, program = _load_active(root)
    _require(program, 'build')
    policy_path, policy, commands = build_policy(root)
    jobs = int(policy['parallelism']['maximum_compiler_jobs'])
    summary = {'policy': {'path': policy_path.as_posix(), 'sha256': sha256_bytes((root / policy_path).read_bytes()),
                          'policy_id': policy.get('policy_id'), 'maximum_compiler_jobs': jobs}, 'commands': commands}
    if dry_run:
        return summary
    _, data = store.load(root)
    if expected_sha256 is not None and store.state_sha256(data) != expected_sha256:
        raise GraphError('raid program state changed; resume before building')
    observe = worktree_state or queue.worktree_state
    identity = observe(root)
    if not identity.get('clean'):
        raise GraphError('commit every handoff, patch request and the program state before building (clean tree)')
    run = runner or _queue_runner
    steps = []
    for kind, command in commands.items():
        if observe(root) != identity:
            raise GraphError('the tree changed during the build; no edits while a build runs')
        try:
            code, receipt, path, gate = run(root, policy, kind, command)
        except RuntimeError as error:
            raise GraphError(f'{kind} failed in the build queue: {error}; inspect queued_build status') from error
        steps.append({'step': kind, 'receipt': path, 'exit_status': code,
                      'classification': receipt.get('classification'), 'gate_bearing': gate})
        if code or not gate:
            break
    success = len(steps) == len(commands) and all(step['gate_bearing'] and not step['exit_status'] for step in steps)
    binary = root / WORLDSERVER
    record = summary | {'source_commit': identity.get('commit'), 'steps': steps, 'success': success,
                        'worldserver_sha256': sha256_bytes(binary.read_bytes()) if success and binary.is_file() else None,
                        'recorded_utc': utc_now()}

    def reducer(current: dict) -> dict:
        target = active(current)
        _require(target, 'build')
        rounds = current_round(target)
        rounds.setdefault('build_attempts', []).append(record)
        if success:
            rounds['build'] = record
            target['stage'] = 'run'
        store.history(target, 'build', round=target['round'], success=success, source_commit=record['source_commit'])
        return current
    store.update(root, reducer, store.state_sha256(data))
    return record


def _shard_row(unit: dict, raid: str, token: str) -> dict:
    lockout = unit['lockout']
    return {'cohort_id': unit['cohort_id'], 'runtime_profile_id': unit['runtime_profile_id'],
            'scenario_id': unit['scenario_id'], 'pool_tag': unit['pool_tag'], 'raid': raid,
            'mode': token, 'boss_key': unit['boss_key'],
            'lockout': None if lockout['fresh_instance'] else {
                'raid': raid, 'difficulty': token,
                'precompleted_boss_keys': lockout['precompleted_boss_keys'],
                'seed_boss_argument': lockout['seed_boss_argument']}}


def run_plans(root: Path, expected_sha256: str | None = None, write: bool = True) -> dict:
    """Write this round's shard run plans (or the e2e plan) and record their hashes."""
    from tools.raid_program.shard_coordinator import MAX_SHARDS, load_run_plan
    _, program = _load_active(root)
    if program['stage'] not in ('run', 'e2e'):
        raise GraphError('run plans are written in the run or e2e stage')
    discovery = discover_program(root, program['raid'], program['mode'])
    token = discovery['mode_token']
    if program['stage'] == 'run':
        ready = [unit for unit in discovery['units'] if unit['ready_to_run']]
        batches = [ready[index:index + MAX_SHARDS] for index in range(0, len(ready), MAX_SHARDS)]
        documents = [{'schema': RUN_PLAN_SCHEMA, 'kind': 'boss_shards', 'program_id': program['program_id'],
                      'round': program['round'], 'shards': [_shard_row(unit, program['raid'], token) for unit in batch]}
                     for batch in batches]
    else:
        e2e = discovery['e2e']
        if not e2e['ready_to_run']:
            raise GraphError('the end-to-end unit is missing inputs: ' + ', '.join(i['input'] for i in e2e['missing_inputs']))
        documents = [{'schema': RUN_PLAN_SCHEMA, 'kind': E2E_KEY, 'program_id': program['program_id'],
                      'round': program['round'], 'shards': [{
                          'cohort_id': e2e['cohort_id'], 'runtime_profile_id': e2e['runtime_profile_id'],
                          'scenario_id': e2e['scenario_id'], 'pool_tag': e2e['pool_tag'],
                          'raid': program['raid'], 'mode': token, 'boss_key': E2E_KEY, 'lockout': None}]}]
    directory = packets.handoff_directory(program)
    rows = []
    for index, document in enumerate(documents, 1):
        name = f"{directory}/{document['kind']}_plan_b{index}.json"
        encoded = (json.dumps(document, indent=2, sort_keys=True) + '\n').encode()
        rows.append({'batch': index, 'kind': document['kind'], 'path': name, 'sha256': sha256_bytes(encoded),
                     'cohorts': [row['cohort_id'] for row in document['shards']], 'document': document})
    if not write:
        return {'plans': rows}
    for row in rows:
        path = root / row['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(row['document'], indent=2, sort_keys=True) + '\n').encode())
        load_run_plan(path)  # the coordinator's own parser must accept the plan before it is recorded

    def reducer(state: dict) -> dict:
        target = active(state)
        if target['stage'] != program['stage'] or target['round'] != program['round']:
            raise GraphError('program advanced; resume before writing run plans')
        rounds = current_round(target) if target['stage'] == 'run' else _e2e_round(target)
        rounds['run_plans'] = [{key: row[key] for key in ('batch', 'kind', 'path', 'sha256', 'cohorts')} for row in rows]
        store.history(target, 'run_plans', round=target['round'], batches=len(rows))
        return state
    store.update(root, reducer, expected_sha256)
    return {'plans': [{key: row[key] for key in ('batch', 'kind', 'path', 'sha256', 'cohorts')} for row in rows]}


def _e2e_round(program: dict) -> dict:
    """The e2e stage records its plan and runs on the last round's record."""
    rounds = program['rounds'][-1]
    rounds.setdefault('e2e', {'run_plans': [], 'runs': []})
    return rounds['e2e']


def _shard_run(root: Path, path: Path) -> tuple[dict, dict]:
    data = path.read_bytes()
    summary = json.loads(data)
    if not isinstance(summary, dict) or summary.get('schema') != RUN_SCHEMA or not isinstance(summary.get('shards'), list):
        raise GraphError(f'{path} is not a {RUN_SCHEMA} shard_run.json')
    shards = [{key: row.get(key) for key in ('cohort_id', 'run_dir', 'instance_id', 'completion_reason', 'native_clear',
                                             'error', 'start_refusal', 'timed_out', 'foreign_payloads',
                                             'cross_cohort_replies')}
              | {'lockout_state': (row.get('lockout') or {}).get('state'), 'seeded': row.get('lockout') is not None}
              for row in summary['shards']]
    record = _repo_ref(root, path) | {'run_id': summary.get('run_id'), 'terminal_reason': summary.get('terminal_reason'),
                                       'isolation': summary.get('isolation'), 'shards': shards, 'recorded_utc': utc_now()}
    return summary, record


def record_run(root: Path, shard_run: Path, expected_sha256: str | None = None) -> dict:
    _, program = _load_active(root)
    _require(program, 'run')
    _, record = _shard_run(root, shard_run)
    cohorts = sorted(row['cohort_id'] for row in record['shards'])
    plans = current_round(program)['run_plans']
    batch = next((plan['batch'] for plan in plans if sorted(plan['cohorts']) == cohorts), None)
    if batch is None:
        raise GraphError('shard run cohorts match no run plan of this round: ' + ', '.join(cohorts))
    if any(run['sha256'] == record['sha256'] for run in current_round(program)['runs']):
        raise GraphError('this shard run is already recorded')

    def reducer(state: dict) -> dict:
        target = active(state)
        _require(target, 'run')
        current_round(target)['runs'].append(record | {'batch': batch})
        store.history(target, 'run', round=target['round'], batch=batch, terminal_reason=record['terminal_reason'])
        return state
    return store.update(root, reducer, expected_sha256)


def classify(row: dict) -> str:
    if row.get('native_clear'):
        return 'clear'
    if row.get('start_refusal'):
        return 'start_refused'
    if row.get('error'):
        return 'shard_error'
    return str(row.get('completion_reason') or 'incomplete')


def _verdict(root: Path, unit: dict, label: str | None, build: dict | None) -> dict | None:
    target = unit['raid_target']
    if not label or not target['present']:
        return None
    from tools.raid_program.scoreboard_verdict import evaluate_target
    try:
        verdict = evaluate_target(root, target['scenario'], label)
    except (SystemExit, ValueError, KeyError, OSError) as error:
        return {'scenario': target['scenario'], 'label': label, 'status': 'error', 'reasons': [str(error)[:200]]}
    result = {'scenario': target['scenario'], 'label': label, 'status': verdict['status'], 'reasons': verdict['reasons'],
              'kills': verdict['kills'], 'target_sha256': verdict['target_sha256'],
              'worldserver_sha256': verdict['worldserver_sha256']}
    expected = (build or {}).get('worldserver_sha256')
    if result['status'] == 'pass' and expected and verdict['worldserver_sha256'] != expected:
        result.update(status='build_mismatch', reasons=['kills did not run this round\'s build'])
    return result


def assess(root: Path, label: str | None = None, expected_sha256: str | None = None) -> dict:
    _, program = _load_active(root)
    _require(program, 'run')
    rounds = current_round(program)
    missing_batches = [plan['batch'] for plan in rounds['run_plans']
                       if not any(run['batch'] == plan['batch'] for run in rounds['runs'])]
    if missing_batches:
        raise GraphError('record a shard run for every planned batch first: ' + ', '.join(map(str, missing_batches)))
    discovery = discover_program(root, program['raid'], program['mode'])
    units = {unit['boss_key']: unit for unit in discovery['units']}
    results = {}
    for key, record in program['units'].items():
        unit = units.get(key)
        rows = [shard for run in rounds['runs'] for shard in run['shards'] if shard['cohort_id'] == record['cohort_id']]
        outcomes = [classify(row) for row in rows]
        verdict = _verdict(root, unit, label, rounds.get('build')) if unit and rows else None
        result = {'round': program['round'], 'runs': len(rows), 'clears': outcomes.count('clear'),
                  'outcome': outcomes[-1] if outcomes else 'not_run', 'verdict': verdict,
                  'missing_inputs': [item['input'] for item in (unit or {}).get('missing_inputs', [])]}
        passed = bool(unit and verdict and verdict['status'] == 'pass' and result['clears']
                      and outcomes[-1] == 'clear' and not unit['acceptance_blocked'])
        if record['status'] == 'accepted':
            regressed = rows and (outcomes[-1] != 'clear' or (verdict and verdict['status'] != 'pass'))
            result['status'] = 'open' if regressed else 'accepted'
            result['reopened'] = bool(regressed)
        else:
            result['status'] = 'accepted' if passed else 'open'
        results[key] = result

    def reducer(state: dict) -> dict:
        target = active(state)
        _require(target, 'run')
        current_round(target)['assessment'] = {'label': label, 'assessed_utc': utc_now(), 'units': results}
        for key, result in results.items():
            target['units'][key]['results'].append(result)
            target['units'][key]['status'] = result['status']
        assessed = target['round']
        all_accepted = all(unit['status'] == 'accepted' for unit in target['units'].values())
        if all_accepted and target['e2e']['status'] != 'accepted' and discovery['e2e']['ready_to_run']:
            target['stage'] = 'e2e'
        else:
            # Open bosses, or an e2e unit whose inputs are missing, need another round.
            target['stage'], target['round'] = 'plan', target['round'] + 1
        store.history(target, 'assess', round=assessed, label=label,
                      accepted=sorted(k for k, r in results.items() if r['status'] == 'accepted'))
        return state
    return store.update(root, reducer, expected_sha256)


def record_e2e(root: Path, shard_run: Path, expected_sha256: str | None = None) -> dict:
    """Accept the end-to-end unit from one fresh-instance full-route shard run."""
    _, program = _load_active(root)
    _require(program, 'e2e')
    plans = (program['rounds'][-1].get('e2e') or {}).get('run_plans') or []
    summary, record = _shard_run(root, shard_run)
    if not plans or [row['cohort_id'] for row in record['shards']] != plans[-1]['cohorts']:
        raise GraphError('write the e2e run plan (program run-plan) and run exactly that shard')
    discovery = discover_program(root, program['raid'], program['mode'])
    shard = record['shards'][0]
    problems = []
    if shard['seeded']:
        problems.append('seeded_lockout_forbidden')
    if summary.get('terminal_reason') != 'completed':
        problems.append('terminal_reason=' + str(summary.get('terminal_reason')))
    if not shard['native_clear']:
        problems.append('outcome=' + classify(shard))
    expected = sorted({node for nodes in discovery['e2e']['boss_nodes'].values() for node in nodes})
    killed = _killed_nodes(Path(str(shard.get('run_dir') or '')))
    absent = [node for node in expected if node not in killed]
    if not expected or absent:
        problems.append('boss_kills_missing:' + ','.join(absent or ['route_has_no_boss_nodes']))
    result = {'round': program['round'], 'outcome': 'clear' if not problems else 'failed', 'problems': problems,
              'run': record, 'boss_nodes_killed': sorted(killed)}

    def reducer(state: dict) -> dict:
        target = active(state)
        _require(target, 'e2e')
        _e2e_round(target)['runs'].append(record)
        target['e2e']['results'].append(result)
        if problems:
            target['e2e']['status'] = 'open'
            target['stage'], target['round'] = 'plan', target['round'] + 1
        else:
            target['e2e']['status'] = 'accepted'
            target['stage'] = 'complete'
        store.history(target, 'e2e', outcome=result['outcome'], problems=problems)
        return state
    return store.update(root, reducer, expected_sha256)


def _killed_nodes(run_dir: Path) -> set[str]:
    try:
        report = json.loads((run_dir / 'report.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return set()
    outcome = report.get('native_gameplay_outcome') or {}
    evidence = outcome.get('real_boss_kill_evidence') or (report.get('evidence') or {}).get('real_boss_kill_evidence') or []
    return {str(row.get('route_node_id')) for row in evidence if isinstance(row, dict) and row.get('route_node_id')}


def status_rows(program: dict, discovery: dict) -> list[dict[str, Any]]:
    rows = []
    for unit in discovery['units']:
        record = program['units'].get(unit['boss_key'], {})
        last = (record.get('results') or [None])[-1] or {}
        rows.append({'boss': unit['boss_key'], 'cohort': unit['cohort_id'], 'status': record.get('status', 'open'),
                     'ready_to_run': unit['ready_to_run'], 'lockout': unit['lockout']['seed_boss_argument'],
                     'last': last.get('outcome'), 'verdict': (last.get('verdict') or {}).get('status'),
                     'missing': [item['input'] for item in unit['missing_inputs']],
                     'owner_skill': packets.boss_task(unit, last or None)[0] if record.get('status') != 'accepted' else None,
                     'boss_graph': (unit.get('boss_graph') or {}).get('stage')})
    return rows
