"""Round state machine of a raid program (core transitions).

    plan -> implement -> build -> run -> (assess) -> plan of the next round
                                              \\-> e2e -> complete

``plan`` freezes one worker packet per open boss unit (plus the shards and
research packets when needed) and the plan-time commit; ``implement`` records
one validated handoff per packet (``reopen`` sends a packet back from build);
``build`` (raid_program_build) configures and builds the committed tree once;
``run`` (raid_program_runs) writes shard run plans and records each run or
batch failure; ``ingest`` (raid_program_ingest) archives and records the kills
of bosses with a raid target; ``assess`` judges every boss and opens the next
round or the end-to-end unit; ``e2e`` accepts one fresh-instance full-route run.
Nothing here launches agents or servers.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from tools.raid_program import raid_program_packets as packets
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError, utc_now
from tools.raid_program.raid_program_inputs import discover_program


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def discover(root: Path, program: dict) -> dict:
    """The one discovery entry point of every round step (tests patch discover_program here)."""
    return discover_program(root, program['raid'], program['mode'])


def active(state: dict) -> dict:
    return state['programs'][state['active_program']]


def current_round(program: dict) -> dict:
    if not program['rounds'] or program['rounds'][-1]['round'] != program['round']:
        raise GraphError('round ' + str(program['round']) + ' has not been planned')
    return program['rounds'][-1]


def require(program: dict, *stages: str) -> None:
    if program['stage'] not in stages:
        raise GraphError(f"program stage is {program['stage']}, not {' or '.join(stages)}; run raid_workloop resume")


def load_active(root: Path) -> tuple[dict, dict, bytes]:
    state, data = store.load(root)
    if state is None:
        raise GraphError('no raid program selected; run raid_workloop start "implement <raid> <mode> bots"')
    store.check(root, state)
    return state, active(state), data


def check_expected(data: bytes, expected_sha256: str | None) -> None:
    """Fail before any side effect when the caller's state hash is stale."""
    if expected_sha256 is not None and store.state_sha256(data) != expected_sha256:
        raise GraphError('raid program state changed; resume before applying this step')


def repo_ref(root: Path, path: Path) -> dict:
    resolved = path.resolve()
    data = resolved.read_bytes()
    shown = resolved.relative_to(root.resolve()).as_posix() if resolved.is_relative_to(root.resolve()) else str(resolved)
    return {'path': shown, 'sha256': sha256_bytes(data)}


def git_head(root: Path) -> str | None:
    completed = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', '-q', 'HEAD'],
                               capture_output=True, text=True, check=False)
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and len(value) == 40 else None


def new_program(discovery: dict) -> dict:
    name, mode = discovery['name'], discovery['mode']
    return {
        'program_id': discovery['program_id'], 'raid': discovery['raid'], 'mode': mode, 'name': name,
        'objective': (f'Carry {name} {mode} bots to completion: every boss shard passes its scoreboard verdict '
                      '(WCL parity, native clears, no boss-window deaths) in parallel seeded lockouts with one build '
                      'per round, then the end-to-end clear of the composed full route with trash and interactions.'),
        'created_utc': utc_now(), 'revision': 0, 'stage': 'plan', 'round': 1,
        'bootstrap_sources': discovery['sources'],
        'units': {unit['boss_key']: unit_record(unit) for unit in discovery['units']},
        'e2e': {'unit_id': discovery['e2e']['unit_id'], 'status': 'open', 'results': []},
        'rounds': [], 'history': []}


def unit_record(unit: dict) -> dict:
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
        if previous and state['active_program'] != key and previous['e2e'].get('status') == 'evidence_pending':
            raise GraphError(f"program {state['active_program']} has an e2e clear awaiting its evidence archive; run "
                             'program e2e --archive-pending (or --evidence-lost REASON) before selecting another program')
        if key not in state['programs']:
            state['programs'][key] = new_program(discovery)
            store.history(state['programs'][key], 'created')
        state['active_program'], state['focus'] = key, 'program'
        return state
    return store.update(root, reducer, expected_sha256)


def plan(root: Path, bosses: list[str] | None = None, expected_sha256: str | None = None) -> dict:
    _, program, data = load_active(root)
    require(program, 'plan')
    check_expected(data, expected_sha256)
    discovery = discover(root, program)
    for unit in discovery['units']:
        program['units'].setdefault(unit['boss_key'], unit_record(unit))
    e2e_due = all(unit['status'] == 'accepted' for unit in program['units'].values())
    failures = [result for result in program['e2e']['results'] if result['outcome'] != 'clear']
    built = packets.build_packets(discovery, program, bosses, e2e_due, failures[-1] if failures and e2e_due else None)
    head = git_head(root)

    def reducer(state: dict) -> dict:
        target = active(state)
        require(target, 'plan')
        for unit in discovery['units']:
            target['units'].setdefault(unit['boss_key'], unit_record(unit))
        if target['rounds'] and target['rounds'][-1]['round'] == target['round']:
            raise GraphError('round already planned')
        target['rounds'].append({'round': target['round'], 'planned_utc': utc_now(), 'plan_commit': head,
                                 'packets': built, 'build': None, 'run_plans': [], 'runs': [], 'assessment': None})
        target['stage'] = 'implement'
        store.history(target, 'plan', round=target['round'], packets=sorted(built))
        return state
    return store.update(root, reducer, expected_sha256)


def record_handoff(root: Path, packet_id: str, handoff_path: Path | None, abandon_reason: str | None = None,
                   expected_sha256: str | None = None, external_reason: str | None = None) -> dict:
    """Record a packet's handoff, an abandoned packet, or work done outside the program (``external``)."""
    _, program, data = load_active(root)
    require(program, 'implement')
    check_expected(data, expected_sha256)
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
            raise GraphError('handoff file required (or --abandon/--external REASON)')
        handoff = json.loads(handoff_path.read_text(encoding='utf-8'))
        packets.validate_handoff(handoff, packet, program['round'])
        record = repo_ref(root, handoff_path) | {
            'recorded_utc': utc_now(), 'patch_requests': len(handoff['patch_requests']),
            'resolved_inputs': [str(name) for name in handoff['resolved_inputs']],
            'changed_files': sorted(set(handoff['changed_files'] + handoff['new_files']))}

    def reducer(state: dict) -> dict:
        target = active(state)
        require(target, 'implement')
        row = current_round(target)['packets'][packet_id]
        row['handoff'] = record
        store.history(target, 'handoff', round=target['round'], packet=packet_id, abandoned=bool(abandon_reason),
                      external=bool(external_reason))
        if all(item['handoff'] for item in current_round(target)['packets'].values()):
            target['stage'] = 'build'
        return state
    return store.update(root, reducer, expected_sha256)


def reopen_packet(root: Path, packet_id: str, reason: str, expected_sha256: str | None = None) -> dict:
    """Send one packet back to implementation (from implement or build; never during run)."""
    if not reason:
        raise GraphError('reopen needs a reason')

    def reducer(state: dict) -> dict:
        target = active(state)
        require(target, 'implement', 'build')
        row = current_round(target)['packets'].get(packet_id)
        if row is None:
            raise GraphError('no packet ' + packet_id + ' in round ' + str(target['round']))
        row.setdefault('reopened', []).append({'reason': reason, 'previous_handoff': row['handoff'], 'utc': utc_now()})
        row['handoff'] = None
        target['stage'] = 'implement'
        store.history(target, 'reopen', round=target['round'], packet=packet_id, reason=reason)
        return state
    return store.update(root, reducer, expected_sha256)


def record_fix(root: Path, reason: str, expected_sha256: str | None = None) -> dict:
    """Record a coordinator fix (for example a build repair) in the current round; the stage is unchanged."""
    if not reason:
        raise GraphError('a coordinator fix needs a reason')
    head = git_head(root)

    def reducer(state: dict) -> dict:
        target = active(state)
        require(target, 'implement', 'build')
        current_round(target).setdefault('coordinator_fixes', []).append(
            {'reason': reason, 'head': head, 'utc': utc_now()})
        store.history(target, 'coordinator_fix', round=target['round'], reason=reason)
        return state
    return store.update(root, reducer, expected_sha256)


def verdict_for(root: Path, unit: dict, label: str | None, build: dict | None) -> dict | None:
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
    if result['status'] == 'pass' and verdict['worldserver_sha256'] != expected:
        result.update(status='build_mismatch', reasons=['kills did not run this round\'s build'])
    return result


def classify(row: dict) -> str:
    if row.get('native_clear'):
        return 'clear'
    if row.get('start_refusal'):
        return 'start_refused'
    if row.get('error'):
        return 'shard_error'
    return str(row.get('completion_reason') or 'incomplete')


def _judge(unit: dict | None, rows: list[dict], verdict: dict | None) -> list[str]:
    """Why a boss unit is not acceptable this round; empty means accepted."""
    if unit is None:
        return ['unit_missing_from_discovery']
    reasons = []
    if not rows:
        reasons.append('not_run')
    elif classify(rows[-1]) != 'clear':
        reasons.append('outcome:' + classify(rows[-1]))
    if unit['acceptance_blocked']:
        reasons.append('missing_inputs:' + ','.join(item['input'] for item in unit['missing_inputs']))
    if verdict is None:
        reasons.append('verdict_missing')
    elif verdict['status'] != 'pass':
        reasons.append('verdict:' + str(verdict['status']))
    return reasons


def assess(root: Path, label: str | None = None, expected_sha256: str | None = None) -> dict:
    """Judge every boss unit; accepted units stay accepted only when they pass again this round."""
    _, program, data = load_active(root)
    require(program, 'run')
    check_expected(data, expected_sha256)
    rounds = current_round(program)
    missing_batches = [plan['batch'] for plan in rounds['run_plans']
                       if not any(run['batch'] == plan['batch'] for run in rounds['runs'])]
    if missing_batches:
        raise GraphError('record a shard run (or --failed-batch) for every planned batch first: '
                         + ', '.join(map(str, missing_batches)))
    if rounds.get('label') and label != rounds['label']:
        raise GraphError(f"this round ingested its kills under label {rounds['label']}; assess with that label")
    discovery = discover(root, program)
    units = {unit['boss_key']: unit for unit in discovery['units']}
    rows_by_key = {key: [shard for run in rounds['runs'] for shard in run['shards'] if shard['cohort_id'] == record['cohort_id']]
                   for key, record in program['units'].items()}
    ran = {shard['cohort_id'] for run in rounds['runs'] if not run.get('failed') for shard in run['shards']}
    if not label and any(record['cohort_id'] in ran and (units.get(key) or {}).get('raid_target', {}).get('present')
                         for key, record in program['units'].items()):
        raise GraphError('bosses with a raid target ran this round: ingest their kills (program ingest --label L) '
                         'and assess with --label L')
    results = {}
    for key, record in program['units'].items():
        unit, rows = units.get(key), rows_by_key[key]
        outcomes = [classify(row) for row in rows]
        verdict = verdict_for(root, unit, label, rounds.get('build')) if unit and rows else None
        reasons = _judge(unit, rows, verdict)
        results[key] = {'round': program['round'], 'runs': len(rows), 'clears': outcomes.count('clear'),
                        'outcome': outcomes[-1] if outcomes else 'not_run', 'verdict': verdict,
                        'missing_inputs': [item['input'] for item in (unit or {}).get('missing_inputs', [])],
                        'status': 'open' if reasons else 'accepted', 'not_accepted_because': reasons,
                        'reopened': record['status'] == 'accepted' and bool(reasons)}
    raid_inputs = [item['input'] for item in discovery['raid_inputs']]

    def reducer(state: dict) -> dict:
        target = active(state)
        require(target, 'run')
        current_round(target)['assessment'] = {'label': label, 'assessed_utc': utc_now(), 'units': results,
                                               'raid_inputs': raid_inputs}
        for key, result in results.items():
            target['units'][key]['results'].append(result)
            target['units'][key]['status'] = result['status']
        assessed = target['round']
        all_accepted = all(unit['status'] == 'accepted' for unit in target['units'].values())
        if all_accepted and not raid_inputs and discovery['e2e']['ready_to_run'] and target['e2e']['status'] != 'accepted':
            target['stage'] = 'e2e'
        else:
            # Open bosses, raid-level inputs or missing e2e inputs need another round (research/shards packets).
            target['stage'], target['round'] = 'plan', target['round'] + 1
        store.history(target, 'assess', round=assessed, label=label,
                      accepted=sorted(k for k, r in results.items() if r['status'] == 'accepted'))
        return state
    return store.update(root, reducer, expected_sha256)


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
