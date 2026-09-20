"""Persistent development steps; never launches builds, agents or game servers.

Events are coordinator attestations backed by hash-bound receipts. This checks
identity and workflow prerequisites, not the truth of a model's interpretation.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

STATE_PATH = Path('experiments/configs/cata_raid_active_work_unit_v1.json')
STEPS = ('diagnose', 'implement', 'review', 'build', 'validate', 'assess', 'publish', 'route', 'complete')
RECEIPTS = dict(zip(STEPS[:7], ('plan', 'tests', 'review', 'build', 'run', 'assessment', 'publication')))
NEXT = dict(zip(STEPS, STEPS[1:]))
ACTIONS = {
    'diagnose': 'Read retained evidence; identify one causal mismatch and prepare a bounded worker task.',
    'implement': 'Implement the bounded task, run its required tests, and obtain a result checkpoint.',
    'review': 'Obtain independent review of the exact tested files. Resolve findings before building.',
    'build': 'Commit reviewed code and graph state, then use queued_build with the retained policy; reuse a matching verified build receipt.',
    'validate': 'Reconcile any existing attempt before launching. Use the canonical controller and its ownership locks.',
    'assess': 'Review every actor; compare matched baseline, native outcome, and performance separately.',
    'publish': 'Close evidence, DVC status/push, verify remote bytes and clean exact local duplicates.',
    'route': 'Select the next proven edge, or complete only when every requirement is accepted.',
    'complete': 'All recorded requirements accepted; report the evidence and stop.',
}


class GraphError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise GraphError('JSON object required')
    return value


def file_ref(root: Path, ref: dict) -> Path:
    if not isinstance(ref, dict) or not isinstance(ref.get('path'), str):
        raise GraphError('receipt requires path and sha256')
    path = (root / ref['path']).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise GraphError('receipt must be an existing repository file; restore DVC evidence if needed')
    if digest(path.read_bytes()) != ref.get('sha256'):
        raise GraphError('receipt hash mismatch: ' + ref['path'])
    return path


def check_graph(g: dict) -> None:
    if g.get('version') != 1 or g.get('stage') not in STEPS:
        raise GraphError('invalid development graph')
    requirements = g.get('requirements')
    if not isinstance(requirements, dict) or not requirements:
        raise GraphError('requirements missing')
    if any(v.get('status') not in ('open', 'accepted') for v in requirements.values()):
        raise GraphError('invalid requirement status')
    if not g.get('objective') or not isinstance(g.get('history'), list):
        raise GraphError('objective/history missing')
    if not isinstance(g.get('revision'), int) or isinstance(g['revision'], bool):
        raise GraphError('revision missing')
    unit = g.get('unit', {})
    required(unit, 'id', 'edge', 'requirements', 'next_action')
    if not set(unit['requirements']) <= set(requirements):
        raise GraphError('unit references unknown requirements')
    if not g.get('actor_ids') or len(set(g['actor_ids'])) != len(g['actor_ids']):
        raise GraphError('unique actor IDs required')
    encounter = g.get('encounter', {})
    if any(not isinstance(encounter.get(k), str) or not encounter[k] for k in ('raid', 'boss', 'mode')) or encounter['mode'] not in ('10N', '10H', '25N', '25H'):
        raise GraphError('explicit raid/boss/difficulty identity required')
    inputs = g.get('bootstrap_inputs')
    if inputs is not None:
        required(unit, 'owner_skill')
        roster = inputs.get('roster', {})
        actors = roster.get('actors', [])
        if inputs.get('encounter') != encounter or roster.get('size') != int(encounter['mode'][:-1]) or len(actors) != roster['size'] or [a.get('actor_id') for a in actors] != g['actor_ids']:
            raise GraphError('mixed bootstrap encounter/size/actor identity')
    history = g['history']
    if g['revision'] != len(history):
        raise GraphError('revision/history mismatch')
    previous = 'diagnose'
    for revision, row in enumerate(history):
        if row.get('revision') != revision or row.get('from') != previous:
            raise GraphError('broken transition history')
        event = row.get('event', {})
        action = event.get('action')
        if event.get('revision') != revision or event.get('unit_id') != row.get('unit_id'):
            raise GraphError('history event identity mismatch')
        target = row.get('to')
        legal = (
            (action in ('claim', 'release') and target == previous and previous != 'complete')
            or (action == 'advance' and previous in RECEIPTS and target == NEXT[previous])
            or (action == 'route' and previous == 'route' and target == 'diagnose')
            or (action == 'rework' and previous in ('diagnose','implement','review','build','validate') and target in ('diagnose','route'))
            or (action == 'complete' and previous == 'route' and target == 'complete')
        )
        if not legal:
            raise GraphError('illegal transition in saved history')
        previous = row.get('to')
    if previous != g['stage']:
        raise GraphError('stage does not match saved history')
    for key, requirement in requirements.items():
        if key.startswith('actor_') and requirement.get('actor_id') != key.removeprefix('actor_'):
            raise GraphError('actor requirement identity missing')
        if requirement['status'] == 'accepted':
            revision = requirement.get('accepted_at_revision')
            if type(revision) is not int or revision >= len(history) or revision < 0:
                raise GraphError('accepted requirement lacks publication history')
            row = history[revision]
            if row['from'] != 'publish' or key not in row.get('accepted_requirements', []) or requirement.get('receipt') != row['event'].get('receipt'):
                raise GraphError('accepted requirement lacks publication evidence')
    fields = {
        'implement': ('assignment',), 'review': ('assignment', 'tested_files', 'implementer'),
        'build': ('assignment', 'tested_files', 'implementer'),
        'validate': ('assignment', 'tested_files', 'build_identity'),
        'assess': ('run',), 'publish': ('run', 'outcomes'),
    }
    required(g, *fields.get(g['stage'], ()))
    if g['stage'] == 'publish':
        pending = g.get('pending_acceptance')
        assessment = next((h for h in reversed(history) if h['from'] == 'assess' and h['event']['action'] == 'advance'), {})
        if not isinstance(pending, list) or not set(pending) <= set(unit['requirements']) or pending != assessment.get('proposed_acceptance'):
            raise GraphError('pending acceptance does not match assessment history')
    if g['stage'] == 'complete' and any(r['status'] != 'accepted' for r in requirements.values()):
        raise GraphError('complete graph still has open requirements')


def check_state(root: Path, state: dict) -> None:
    g = state['development_graph']
    check_graph(g)
    if Path(g['coordinator_worktree']).resolve() != root.resolve():
        raise GraphError('use the canonical coordinator worktree; do not fork progress across worktrees')
    active = ':'.join(g['encounter'][k] for k in ('raid', 'boss', 'mode'))
    parked = state.get('parked_scenarios', {})
    if not isinstance(parked, dict) or active in parked:
        raise GraphError('invalid parked registry or duplicate active scenario')
    for key, saved in parked.items():
        if not isinstance(saved, dict) or 'parked_scenarios' in saved:
            raise GraphError('invalid nested parked scenario')
        other = saved['development_graph']
        check_graph(other)
        identity = ':'.join(other['encounter'][k] for k in ('raid', 'boss', 'mode'))
        if key != identity or other.get('claim') or other['stage'] in ('validate', 'assess', 'publish') or Path(other['coordinator_worktree']).resolve() != root.resolve():
            raise GraphError('invalid parked scenario identity/ownership')


def resume(root: Path) -> dict:
    data = (root / STATE_PATH).read_bytes()
    state = json.loads(data)
    g = state['development_graph']
    check_state(root, state)
    unit = g['unit']
    inputs = g.get('bootstrap_inputs')
    input_changes = []
    for path, reference in (inputs or {}).get('sources', {}).items():
        file = (root / path).resolve()
        current_hash = digest(file.read_bytes()) if file.is_relative_to(root.resolve()) and file.is_file() else None
        if current_hash != (reference or {}).get('sha256'):
            input_changes.append(path)
    return {
        'state_sha256': digest(data), 'revision': g['revision'],
        'encounter': g['encounter'],
        'parked_scenarios': sorted(state.get('parked_scenarios', {})),
        'bootstrap_inputs': inputs, 'changed_bootstrap_sources': input_changes,
        'objective': g['objective'], 'stage': g['stage'], 'unit': unit,
        'owner_skill': unit.get('owner_skill'),
        'next_action': ('Initialization inputs have changed; consult current reviewed inputs before reusing that historical snapshot. ' if input_changes else '') + ('Claimed by ' + g['claim']['owner'] + '; reconcile this operation before continuing. ' if g.get('claim') else '') + ACTIONS[g['stage']],
        'open_requirements': {k: v for k, v in g['requirements'].items() if v['status'] != 'accepted'},
        'completed_measurements': g.get('completed_measurements', []),
        'receipts': g.get('receipts', {}), 'outcomes': g.get('outcomes', {}),
        'same_edge_failures': g.get('failures', {}).get(unit['edge'], 0),
        'retry_limit': 10,
        'claim': g.get('claim'), 'coordinator_worktree': g['coordinator_worktree'],
        'model_advice': 'Use worker_checkpoint at plan/result and plan-drift-review at work-unit changes; never auto-accept scores.',
        'execution': 'Resume is read-only. Reconcile queued_build and active controller receipts; it never authorizes duplicate launches.',
    }


def required(value: dict, *keys: str) -> None:
    for key in keys:
        if not value.get(key):
            raise GraphError('required: ' + key)


def snapshot(root: Path, paths: list[str]) -> dict:
    if not isinstance(paths, list) or not paths or len(paths) != len(set(paths)):
        raise GraphError('nonempty unique owned_files required')
    result = {}
    for name in paths:
        p = (root / name).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file():
            raise GraphError('owned file missing: ' + name)
        result[name] = digest(p.read_bytes())
    return result


def git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()
    except subprocess.CalledProcessError as exc:
        raise GraphError('Git identity check failed') from exc


def code_path(path: str) -> bool:
    return path != STATE_PATH.as_posix() and path != 'AGENTS.md' and not path.startswith(('docs/', 'artifacts/', '.agents/skills/'))


def source_binding(root: Path, assignment: dict, expected_commit: str | None = None) -> str:
    head = git(root, 'rev-parse', 'HEAD')
    base = assignment['base_commit']
    git(root, 'merge-base', '--is-ancestor', base, head)
    dirty = git(root, 'ls-files', '--modified', '--others', '--exclude-standard', '-z').split('\0')
    if any(p and code_path(p) for p in dirty):
        raise GraphError('commit source changes before recording tests/review/build')
    # Inspect committed delta, including files omitted by a worker's declaration.
    changed = git(root, 'diff', '--name-only', '--no-renames', '-z', base, head).split('\0')
    if any(p and code_path(p) and p not in assignment['owned_files'] for p in changed):
        raise GraphError('source delta contains files outside bounded assignment')
    if expected_commit is not None:
        git(root, 'merge-base', '--is-ancestor', expected_commit, head)
        delta = git(root, 'diff', '--name-only', '--no-renames', '-z', expected_commit, head).split('\0')
        if any(p and code_path(p) for p in delta):
            raise GraphError('source changed since recorded tests/review/build')
    return head


def _receipt(root: Path, event: dict, kind: str, g: dict) -> dict:
    r = read(file_ref(root, event.get('receipt')))
    if r.get('kind') != kind or r.get('unit_id') != g['unit']['id']:
        raise GraphError('wrong receipt kind/unit')
    required(r, 'producer', 'evidence')
    if r.get('authority') != 'coordinator_attestation':
        raise GraphError('transition requires coordinator attestation, not model advice')
    if not isinstance(r['evidence'], list):
        raise GraphError('evidence must be a list of file references')
    # Actual existing producer outputs remain intact; the adapter only links them.
    for ref in r['evidence']:
        file_ref(root, ref)
    if r.get('producer') in ('jev', 'laya', 'worker_checkpoint'):
        raise GraphError('model advice is not an acceptance receipt')
    return r


def advice(root: Path, r: dict) -> None:
    """Require visible disposition, including legitimate provider unavailability."""
    reviews = r.get('advice', {})
    for provider in ('jev', 'laya'):
        review = reviews.get(provider, {})
        required(review, 'adjudication')
        if review.get('status') == 'reviewed':
            file_ref(root, review.get('receipt'))
        elif review.get('status') == 'not_reviewed':
            required(review, 'reason')
        else:
            raise GraphError('advisory disposition required for ' + provider)


def reduce(root: Path, state: dict, event: dict) -> dict:
    result = copy.deepcopy(state)
    g = result['development_graph']
    check_graph(g)
    if event.get('revision') != g['revision'] or event.get('unit_id') != g['unit']['id']:
        raise GraphError('stale event revision/unit')
    stage = g['stage']
    action = event.get('action')
    accepted_now = []
    claim = g.get('claim')
    if action != 'claim' and claim and event.get('claim_token') != claim['token']:
        raise GraphError('operation is claimed; reconcile owner before continuing')
    if action == 'advance' and stage in ('implement', 'build', 'validate', 'publish') and not claim:
        raise GraphError('claim this operation before executing it')
    if stage == 'complete':
        raise GraphError('completed program; explicit new objective required')
    if action == 'claim':
        if claim:
            raise GraphError('operation already claimed')
        required(event, 'owner')
        token = digest(f"{g['unit']['id']}:{stage}:{g['revision']}:{event['owner']}".encode())
        g['claim'] = {'owner': event['owner'], 'token': token, 'operation_id': token, 'stage': stage}
    elif action == 'release':
        if not claim:
            raise GraphError('no claimed operation')
        reconciliation = read(file_ref(root, event.get('receipt')))
        if reconciliation.get('operation_id') != claim['operation_id'] or reconciliation.get('active_operation') is not False or reconciliation.get('ownership_checked') is not True or reconciliation.get('completed_operation') is not False or reconciliation.get('reusable_receipt_found') is not False:
            raise GraphError('release requires reconciliation; record completed operations instead of repeating them')
        g.pop('claim')
    elif action == 'advance' and stage in RECEIPTS:
        kind = RECEIPTS[stage]
        r = _receipt(root, event, kind, g)
        if claim and r.get('operation_id') != claim['operation_id']:
            raise GraphError('receipt operation identity mismatch')
        if stage == 'diagnose':
            advice(root, r)
            required(r, 'hypothesis', 'forbidden_changes', 'acceptance_conditions', 'required_test_commands', 'base_commit', 'policy', 'validation_identity')
            file_ref(root, r['policy'])
            validation = r['validation_identity']
            for key in ('roster', 'runtime_profile'):
                file_ref(root, validation.get(key))
            if validation.get('scenario_kind') == 'raid':
                if validation.get('encounter') != g['encounter']:
                    raise GraphError('validation must target the program encounter and difficulty')
                file_ref(root, validation.get('route'))
            elif validation.get('scenario_kind') == 'dummy':
                required(validation, 'actor_id', 'spec', 'reference')
                file_ref(root, validation['reference'])
                if validation['actor_id'] not in g['actor_ids']:
                    raise GraphError('dummy actor outside roster')
            else:
                raise GraphError('unknown validation scenario kind')
            if git(root, 'rev-parse', r['base_commit'] + '^{commit}') != r['base_commit']:
                raise GraphError('full base commit required')
            if r['base_commit'] != g.get('source_base_commit', git(root, 'rev-parse', 'HEAD')):
                raise GraphError('plan cannot rebase over unreviewed source changes')
            g.setdefault('source_base_commit', r['base_commit'])
            paths = r.get('owned_files')
            if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or Path(p).is_absolute() or '..' in Path(p).parts for p in paths):
                raise GraphError('invalid owned_files')
            g['assignment'] = {k: r[k] for k in ('hypothesis', 'owned_files', 'forbidden_changes', 'acceptance_conditions', 'required_test_commands', 'base_commit', 'policy', 'validation_identity')}
        elif stage in ('implement', 'review', 'build'):
            current_commit = source_binding(root, g['assignment'], g.get('tested_commit'))
            current = snapshot(root, g['assignment']['owned_files'])
            if r.get('file_hashes') != current:
                raise GraphError('receipt does not bind current owned files')
            if stage != 'implement' and current != g.get('tested_files'):
                raise GraphError('files changed after tests; reroute and retest')
            if stage == 'implement':
                advice(root, r)
                tests = r.get('tests', [])
                for command in g['assignment']['required_test_commands']:
                    if not any(t.get('command') == command and type(t.get('exit_status')) is int and t['exit_status'] == 0 for t in tests):
                        raise GraphError('required test did not pass: ' + command)
                g['tested_files'] = current
                g['tested_commit'] = current_commit
                g['implementer'] = r['producer']
            elif stage == 'review':
                if r['producer'] == g['implementer'] or r.get('verdict') != 'approved':
                    raise GraphError('independent approving reviewer required')
                g['source_base_commit'] = g['tested_commit']
            else:
                required(r, 'source_commit', 'binary_sha256', 'build_receipt')
                if r.get('policy') != g['assignment']['policy']:
                    raise GraphError('build policy differs from reviewed assignment')
                build = read(file_ref(root, r['build_receipt']))
                from tools.raid_program.queued_build import verify_receipt
                try:
                    verified = verify_receipt(file_ref(root, r['build_receipt']), read(file_ref(root, r.get('policy'))), allow_test_mode=False)
                except Exception as exc:
                    raise GraphError('queued-build verification failed: ' + str(exc)) from exc
                if verified.get('classification') != 'success' or verified.get('gate_bearing') is not True:
                    raise GraphError('queued-build receipt is not gate-bearing success')
                if build.get('commit') != r['source_commit'] or build.get('exit_code') != 0 or build.get('source_identity_stable') is not True or build.get('test_mode') is not False:
                    raise GraphError('nested queued-build receipt does not match a successful native build')
                if not any(a.get('kind') == 'worldserver_elf' and a.get('sha256') == r['binary_sha256'] and a.get('produced_by_ticket') is True for a in build.get('output_artifacts', [])):
                    raise GraphError('binary hash missing from queued-build output artifacts')
                source_binding(root, g['assignment'], r['source_commit'])
                g['build_identity'] = {k: r[k] for k in ('source_commit', 'binary_sha256')}
        elif stage == 'validate':
            source_binding(root, g['assignment'], g['build_identity']['source_commit'])
            if r.get('validation_identity') != g['assignment']['validation_identity'] or r.get('scenario_kind') != g['assignment']['validation_identity']['scenario_kind']:
                raise GraphError('run scenario/roster/profile/route differs from assignment')
            if r.get('build_identity') != g['build_identity']:
                raise GraphError('run/build mismatch')
            if snapshot(root, g['assignment']['owned_files']) != g['tested_files']:
                raise GraphError('files changed since tested build')
            required(r, 'attempt_id', 'server_epoch', 'terminal_reason')
            if r.get('closed') is not True or r.get('cleanup_verified') is not True:
                raise GraphError('attempt must be closed and cleaned before assessment')
            terminals = {'clear', 'semantic_stall', 'repeated_decision', 'death_loop', 'infrastructure_loss', 'contamination', 'interruption', 'measurement_complete'}
            if r['terminal_reason'] not in terminals:
                raise GraphError('unknown terminal reason')
            if r.get('scenario_kind') == 'dummy':
                if r['terminal_reason'] == 'measurement_complete' and r.get('scoring_ms') != 300000:
                    raise GraphError('dummy requires exact 300-second scoring')
                if r['terminal_reason'] == 'clear':
                    raise GraphError('dummy completion is not a raid clear')
            elif r.get('scenario_kind') != 'raid' or r.get('clock') != 'completion_watchdog' or r['terminal_reason'] == 'measurement_complete':
                raise GraphError('raid requires completion watchdog')
            g['run'] = {k: r.get(k) for k in ('attempt_id', 'server_epoch', 'scenario_kind', 'terminal_reason')}
        elif stage == 'assess':
            if r.get('attempt_id') != g['run']['attempt_id']:
                raise GraphError('assessment attempt mismatch')
            required(r, 'baseline', 'comparison', 'actor_reviews')
            file_ref(root, r['baseline'])
            file_ref(root, r['comparison'])
            if set(r['actor_reviews']) != set(g['actor_ids']):
                raise GraphError('every roster actor needs a review or explicit not_exercised')
            for actor_review in r['actor_reviews'].values():
                if actor_review.get('status') == 'reviewed':
                    file_ref(root, actor_review.get('receipt'))
                elif actor_review.get('status') == 'not_exercised':
                    required(actor_review, 'reason')
                else:
                    raise GraphError('invalid actor review disposition')
            for key in ('encounter_clear', 'repair_accepted', 'performance_accepted'):
                if type(r.get(key)) is not bool:
                    raise GraphError('separate boolean outcome required: ' + key)
            if r['encounter_clear'] and (g['run']['scenario_kind'] != 'raid' or g['run']['terminal_reason'] != 'clear'):
                raise GraphError('no observed raid clear')
            accepted = r.get('accepted_requirements', [])
            if g['run']['terminal_reason'] in ('infrastructure_loss', 'contamination', 'interruption') and (r['repair_accepted'] or r['performance_accepted']):
                raise GraphError('unattributable/incomplete run cannot accept a repair or performance')
            if r['performance_accepted'] and (r.get('baseline_matched') is not True or r.get('unexplained_material_decline') is not False):
                raise GraphError('performance needs matched baseline and no unexplained decline')
            if not set(accepted) <= set(g['unit']['requirements']):
                raise GraphError('cannot accept requirements outside current unit')
            if accepted and not r['repair_accepted']:
                raise GraphError('requirement acceptance needs end-to-end repair acceptance')
            for key in accepted:
                requirement = g['requirements'][key]
                if requirement.get('needs_raid') and not r['encounter_clear']:
                    raise GraphError('requirement needs raid validation')
                if requirement.get('needs_performance') and not r['performance_accepted']:
                    raise GraphError('requirement needs performance acceptance')
                actor = requirement.get('actor_id')
                if actor and (r['actor_reviews'][actor]['status'] != 'reviewed' or r['actor_reviews'][actor].get('accepted') is not True):
                    raise GraphError('actor acceptance needs an exercised review')
                if requirement.get('needs_all_actors') and not all(v.get('accepted') is True for v in r['actor_reviews'].values()):
                    raise GraphError('encounter performance needs every actor accepted')
            g['pending_acceptance'] = accepted
            g['outcomes'] = {k: r[k] for k in ('encounter_clear', 'repair_accepted', 'performance_accepted')}
            if not accepted:
                edge = g['unit']['edge']
                g['failures'][edge] = g['failures'].get(edge, 0) + 1
        elif stage == 'publish':
            for key in ('dvc_status_checked', 'dvc_push_completed', 'remote_verified', 'cleanup_verified'):
                if r.get(key) is not True:
                    raise GraphError('publication incomplete: ' + key)
            for key in g.get('pending_acceptance', []):
                g['requirements'][key].update(status='accepted', receipt=event['receipt'], accepted_at_revision=g['revision'])
            accepted_now = g.get('pending_acceptance', [])
        g.setdefault('receipts', {})[kind] = event['receipt']
        g['stage'] = NEXT[stage]
    elif action == 'route' and stage == 'route':
        required(event, 'reason', 'unit')
        unit = event['unit']
        required(unit, 'id', 'edge', 'requirements', 'next_action')
        if unit['id'] == g['unit']['id'] or unit['id'] in [h['unit_id'] for h in g['history']]:
            raise GraphError('unit ID already used')
        if not set(unit['requirements']) <= {k for k, v in g['requirements'].items() if v['status'] == 'open'}:
            raise GraphError('unit selects closed or unknown requirements')
        count = g['failures'].get(g['unit']['edge'], 0)
        if count >= 10:
            file_ref(root, event.get('causal_summary'))
            if unit['edge'] == g['unit']['edge']:
                raise GraphError('ten failures: change the causal hypothesis')
        g['unit'] = unit
        g['stage'] = 'diagnose'
        for key in ('assignment', 'tested_files', 'tested_commit', 'implementer', 'build_identity', 'run', 'pending_acceptance', 'outcomes', 'receipts'):
            g.pop(key, None)
    elif action == 'rework' and stage in ('diagnose', 'implement', 'review', 'build', 'validate'):
        required(event, 'reason')
        rework = file_ref(root, event.get('receipt'))
        if claim and stage in ('implement', 'build', 'validate'):
            reconciliation = read(rework)
            if reconciliation.get('ownership_checked') is not True or reconciliation.get('active_operation') is not False or reconciliation.get('operation_id') != claim['operation_id'] or reconciliation.get('completed_operation') is not False or reconciliation.get('reusable_receipt_found') is not False:
                raise GraphError('reconcile controller/worker/build before abandoning claimed operation')
        edge = g['unit']['edge']
        g['failures'][edge] = g['failures'].get(edge, 0) + 1
        g['stage'] = 'route' if g['failures'][edge] >= 10 else 'diagnose'
        for key in ('assignment', 'tested_files', 'tested_commit', 'implementer', 'build_identity', 'receipts'):
            g.pop(key, None)
    elif action == 'complete' and stage == 'route':
        if any(r['status'] != 'accepted' for r in g['requirements'].values()):
            raise GraphError('open requirements prevent completion')
        g['stage'] = 'complete'
    else:
        raise GraphError('invalid action for stage: ' + str(action))
    g['history'].append({'revision': g['revision'], 'unit_id': event['unit_id'], 'from': stage, 'to': g['stage'], 'event': event, 'accepted_requirements': accepted_now, 'proposed_acceptance': g.get('pending_acceptance', []) if stage == 'assess' else []})
    if action not in ('claim', 'release'):
        g.pop('claim', None)
    g['revision'] += 1
    result['next_action'] = ACTIONS[g['stage']] + (' ' + g['unit']['next_action'] if g['stage'] != 'complete' else '')
    result['work_unit'] = g['unit']['id']
    result['owner_skill'] = g['unit'].get('owner_skill')
    return result


def update_state(root: Path, reducer, expected_sha256: str | None = None) -> None:
    """Shared atomic update for transitions and explicit scenario selection."""
    path = root / STATE_PATH
    common = subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=root, text=True).strip()
    lock = (root / common).resolve() / 'raid-development-graph.lock'
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        original = path.read_bytes()
        if expected_sha256 is not None and digest(original) != expected_sha256:
            raise GraphError('state changed; resume before applying this event')
        if Path(json.loads(original)['development_graph']['coordinator_worktree']).resolve() != root.resolve():
            raise GraphError('use the canonical coordinator worktree; do not fork progress across worktrees')
        old = json.loads(original)
        check_state(root, old)
        state = reducer(old)
        check_state(root, state)
        if state == old:
            return
        encoded = (json.dumps(state, indent=2) + '\n').encode()
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
            name = Path(temp.name)
            try:
                temp.write(encoded)
                temp.flush()
                os.fsync(temp.fileno())
                # Detect editors that do not participate in the advisory lock.
                if path.read_bytes() != original:
                    raise GraphError('state changed during transition')
                os.replace(name, path)
            finally:
                name.unlink(missing_ok=True)


def advance(root: Path, event: dict, expected_sha256: str) -> dict:
    update_state(root, lambda state: reduce(root, state, event), expected_sha256)
    return resume(root)
