"""Shard run plans, run records, batch failures and the end-to-end record of a raid program.

Every recorded shard run must have run the round's binary: ``_shard_run`` reads
``shard_run.json``'s ``worldserver.sha256`` and it must equal the round build's
``worldserver_sha256``. Plans are written once per round (``--replan`` replaces
plans before any run exists); the state update is hash-checked before the plan
files are written.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tools.raid_program import raid_program_packets as packets
from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError, utc_now

RUN_PLAN_SCHEMA = 'raid_shard_run_plan_v1'
RUN_SCHEMA = 'raid_shard_run_v1'
E2E_KEY = 'e2e'
PLAN_KEYS = ('batch', 'kind', 'path', 'sha256', 'cohorts')


def _shard_row(unit: dict, raid: str, token: str) -> dict:
    lockout = unit['lockout']
    return {'cohort_id': unit['cohort_id'], 'runtime_profile_id': unit['runtime_profile_id'],
            'scenario_id': unit['scenario_id'], 'pool_tag': unit['pool_tag'], 'raid': raid,
            'mode': token, 'boss_key': unit['boss_key'],
            'lockout': None if lockout['fresh_instance'] else {
                'raid': raid, 'difficulty': token,
                'precompleted_boss_keys': lockout['precompleted_boss_keys'],
                'seed_boss_argument': lockout['seed_boss_argument']}}


def e2e_round(program: dict) -> dict:
    """The e2e stage records its plans and runs on the last round's record."""
    holder = program['rounds'][-1]
    holder.setdefault('e2e', {'run_plans': [], 'runs': []})
    return holder['e2e']


def last_build(program: dict) -> dict | None:
    return next((row['build'] for row in reversed(program['rounds']) if row.get('build')), None)


def _holder(program: dict) -> dict:
    return rounds.current_round(program) if program['stage'] == 'run' else e2e_round(program)


def _documents(program: dict, discovery: dict) -> list[dict]:
    from tools.raid_program.shard_coordinator import MAX_SHARDS
    token = discovery['mode_token']
    if program['stage'] == 'run':
        ready = [unit for unit in discovery['units'] if unit['ready_to_run']]
        batches = [ready[index:index + MAX_SHARDS] for index in range(0, len(ready), MAX_SHARDS)]
        return [{'schema': RUN_PLAN_SCHEMA, 'kind': 'boss_shards', 'program_id': program['program_id'],
                 'round': program['round'], 'shards': [_shard_row(unit, program['raid'], token) for unit in batch]}
                for batch in batches]
    e2e = discovery['e2e']
    if not e2e['ready_to_run']:
        raise GraphError('the end-to-end unit is missing inputs (' + ', '.join(i['input'] for i in e2e['missing_inputs'])
                         + '); leave the e2e stage with program e2e --failed REASON')
    return [{'schema': RUN_PLAN_SCHEMA, 'kind': E2E_KEY, 'program_id': program['program_id'], 'round': program['round'],
             'shards': [{'cohort_id': e2e['cohort_id'], 'runtime_profile_id': e2e['runtime_profile_id'],
                         'scenario_id': e2e['scenario_id'], 'pool_tag': e2e['pool_tag'], 'raid': program['raid'],
                         'mode': token, 'boss_key': E2E_KEY, 'lockout': None}]}]


def run_plans(root: Path, expected_sha256: str | None = None, replan: bool = False) -> dict:
    """Write this round's shard run plans (or the e2e plan) once; ``replan`` replaces plans before any run."""
    from tools.raid_program.shard_coordinator import load_run_plan
    _, program, data = rounds.load_active(root)
    rounds.require(program, 'run', 'e2e')
    rounds.check_expected(data, expected_sha256)
    holder = _holder(program)
    if holder.get('runs'):
        raise GraphError('runs are recorded for these plans; record the remaining batches (or --failed-batch) instead of replanning')
    if holder.get('plans_written') and not replan:
        raise GraphError('run plans are already written for this round; use program run-plan --replan to replace them')
    documents = _documents(program, rounds.discover(root, program))
    directory = packets.handoff_directory(program)
    rows = []
    with tempfile.TemporaryDirectory(prefix='raid-program-plan-') as temp:
        for index, document in enumerate(documents, 1):
            encoded = (json.dumps(document, indent=2, sort_keys=True) + '\n').encode()
            probe = Path(temp) / f'b{index}.json'
            probe.write_bytes(encoded)
            load_run_plan(probe)  # shard_coordinator must accept the plan before it is recorded
            rows.append({'batch': index, 'kind': document['kind'], 'path': f"{directory}/{document['kind']}_plan_b{index}.json",
                         'sha256': rounds.sha256_bytes(encoded), 'cohorts': [row['cohort_id'] for row in document['shards']],
                         'encoded': encoded})

    def reducer(state: dict) -> dict:
        target = rounds.active(state)
        if target['stage'] != program['stage'] or target['round'] != program['round']:
            raise GraphError('program advanced; resume before writing run plans')
        current = _holder(target)
        if current.get('runs'):
            raise GraphError('runs were recorded meanwhile; resume')
        current['run_plans'] = [{key: row[key] for key in PLAN_KEYS} for row in rows]
        current['plans_written'] = True
        store.history(target, 'run_plans', round=target['round'], batches=len(rows), replan=replan)
        return state
    store.update(root, reducer, expected_sha256)
    for row in rows:  # only after the hash-checked state update
        path = root / row['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(row['encoded'])
    return {'plans': [{key: row[key] for key in PLAN_KEYS} for row in rows]}


def shard_run(root: Path, path: Path) -> tuple[dict, dict]:
    summary = json.loads(path.read_bytes())
    if not isinstance(summary, dict) or summary.get('schema') != RUN_SCHEMA or not isinstance(summary.get('shards'), list):
        raise GraphError(f'{path} is not a {RUN_SCHEMA} shard_run.json')
    shards = [{key: row.get(key) for key in ('cohort_id', 'run_dir', 'instance_id', 'completion_reason', 'native_clear',
                                             'error', 'start_refusal', 'timed_out', 'foreign_payloads',
                                             'cross_cohort_replies')}
              | {'lockout_state': (row.get('lockout') or {}).get('state'), 'seeded': row.get('lockout') is not None}
              for row in summary['shards']]
    worldserver = summary.get('worldserver') if isinstance(summary.get('worldserver'), dict) else {}
    record = rounds.repo_ref(root, path) | {
        'run_id': summary.get('run_id'), 'terminal_reason': summary.get('terminal_reason'),
        'worldserver_sha256': worldserver.get('sha256'), 'isolation': summary.get('isolation'), 'shards': shards,
        'recorded_utc': utc_now()}
    return summary, record


def _require_binary(record: dict, build: dict | None) -> None:
    expected = (build or {}).get('worldserver_sha256')
    if not expected or record['worldserver_sha256'] != expected:
        raise GraphError(f"the shard run used worldserver {record['worldserver_sha256']}, not this round's build "
                         f'{expected}; rerun on the round binary')


def record_run(root: Path, path: Path | None, expected_sha256: str | None = None,
               failed_batch: int | None = None, reason: str | None = None) -> dict:
    """Record one shard_coordinator run, or a batch that produced no shard_run.json."""
    _, program, data = rounds.load_active(root)
    rounds.require(program, 'run')
    rounds.check_expected(data, expected_sha256)
    holder = rounds.current_round(program)
    plans = holder['run_plans']
    if failed_batch is not None:
        plan = next((row for row in plans if row['batch'] == failed_batch), None)
        if plan is None or not reason:
            raise GraphError('--failed-batch needs a planned batch number and --reason')
        record = {'failed': True, 'reason': reason, 'sha256': None, 'run_id': None, 'terminal_reason': 'no_shard_run',
                  'worldserver_sha256': None, 'recorded_utc': utc_now(),
                  'shards': [{'cohort_id': cohort, 'native_clear': False, 'completion_reason': 'batch_failed',
                              'batch_failure_reason': reason, 'run_dir': None} for cohort in plan['cohorts']]}
        batch = failed_batch
    else:
        if path is None:
            raise GraphError('program run needs --shard-run FILE or --failed-batch N --reason TEXT')
        _, record = shard_run(root, path)
        _require_binary(record, holder.get('build'))
        cohorts = sorted(row['cohort_id'] for row in record['shards'])
        batch = next((row['batch'] for row in plans if sorted(row['cohorts']) == cohorts), None)
        if batch is None:
            raise GraphError('shard run cohorts match no run plan of this round: ' + ', '.join(cohorts))
        if any(run['sha256'] == record['sha256'] for run in holder['runs']):
            raise GraphError('this shard run is already recorded')

    def reducer(state: dict) -> dict:
        target = rounds.active(state)
        rounds.require(target, 'run')
        rounds.current_round(target)['runs'].append(record | {'batch': batch})
        store.history(target, 'run', round=target['round'], batch=batch, terminal_reason=record['terminal_reason'])
        return state
    return store.update(root, reducer, expected_sha256)


def record_e2e(root: Path, path: Path | None, expected_sha256: str | None = None,
               failed_reason: str | None = None) -> dict:
    """Accept the end-to-end unit from one fresh-instance full-route run, or leave the e2e stage on failure."""
    _, program, data = rounds.load_active(root)
    rounds.require(program, 'e2e')
    rounds.check_expected(data, expected_sha256)
    record = None
    if failed_reason:
        problems, killed = ['no_run:' + failed_reason], set()
    else:
        plans = e2e_round(program).get('run_plans') or []
        if path is None:
            raise GraphError('program e2e needs --shard-run FILE or --failed REASON')
        summary, record = shard_run(root, path)
        if not plans or [row['cohort_id'] for row in record['shards']] != plans[-1]['cohorts']:
            raise GraphError('write the e2e run plan (program run-plan) and run exactly that shard')
        _require_binary(record, last_build(program))
        discovery = rounds.discover(root, program)
        shard = record['shards'][0]
        problems = []
        if shard['seeded']:
            problems.append('seeded_lockout_forbidden')
        if summary.get('terminal_reason') != 'completed':
            problems.append('terminal_reason=' + str(summary.get('terminal_reason')))
        if not shard['native_clear']:
            problems.append('outcome=' + rounds.classify(shard))
        expected = discovery['e2e'].get('expected_boss_nodes') or []
        killed = killed_nodes(Path(str(shard.get('run_dir') or '')))
        absent = [node for node in expected if node not in killed]
        if not expected or absent:
            problems.append('boss_kills_missing:' + ','.join(absent or ['route_has_no_boss_nodes']))
        if discovery['raid_inputs']:
            problems.append('raid_inputs_open:' + ','.join(item['input'] for item in discovery['raid_inputs']))
        if discovery['e2e']['missing_inputs']:
            problems.append('e2e_inputs_missing:' + ','.join(item['input'] for item in discovery['e2e']['missing_inputs']))
    result = {'round': program['round'], 'outcome': 'clear' if not problems else 'failed', 'problems': problems,
              'run': record, 'boss_nodes_killed': sorted(killed)}

    def reducer(state: dict) -> dict:
        target = rounds.active(state)
        rounds.require(target, 'e2e')
        if record is not None:
            e2e_round(target)['runs'].append(record)
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


def killed_nodes(run_dir: Path) -> set[str]:
    try:
        report = json.loads((run_dir / 'report.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return set()
    outcome = report.get('native_gameplay_outcome') or {}
    evidence = outcome.get('real_boss_kill_evidence') or (report.get('evidence') or {}).get('real_boss_kill_evidence') or []
    return {str(row.get('route_node_id')) for row in evidence if isinstance(row, dict) and row.get('route_node_id')}
