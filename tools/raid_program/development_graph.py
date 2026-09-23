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
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

from tools.raid_program import graph_tiers as tiers

STATE_PATH = Path('experiments/configs/cata_raid_active_work_unit_v1.json')
STEPS = (*tiers.ORDER, 'complete')
RECEIPTS = dict(zip(tiers.ORDER[:-1], ('plan', 'tests', 'review', 'build', 'smoke', 'run', 'assessment', 'publication')))
ACTIONS = {
    'diagnose': 'Read the latest scoreboard verdict and retained evidence; pick the largest actor gap (optional Jev, shadowed by Laya, may choose between the top two), then record a plan with its risk_tier.',
    'implement': 'Implement the bounded task and run its required tests.',
    'review': 'Obtain independent review (separate session) of the exact tested files. Resolve findings before building.',
    'build': 'Run workflow_build preflight before claiming; commit reviewed code and graph state, then use queued_build with the retained policy. Reuse a verified build across coordination-only commits.',
    'smoke': 'shared_runtime only: one watchdog-bounded kill on the new build before the measurement batch.',
    'validate': 'Reconcile any existing attempt before launching. Run one labelled scoreboard measurement batch with the canonical controller and its ownership locks; record scoreboard_label.',
    'assess': 'Write the scoreboard verdict (graph_acceptance verdict --label) and cite it; actor/encounter requirements close only on pass.',
    'publish': 'Close evidence, DVC status/push, verify remote bytes and clean exact local duplicates.',
    'route': 'Select the next largest verdict gap, or complete only when every requirement is accepted.',
    'complete': 'All recorded requirements accepted; report the evidence and stop.',
}
REWORKABLE = ('diagnose', 'implement', 'review', 'build', 'smoke', 'validate')
STATUSES = ('open', 'accepted', 'deferred')
# Requirement parking happens between units, never with work in flight.
PARKING_STAGES = ('diagnose', 'route')
# Per-unit keys cleared when a unit is routed or reworked.
UNIT_KEYS = ('assignment', 'tested_files', 'tested_commit', 'implementer', 'build_identity', 'reused_build', 'build_reason', 'smoke')


class GraphError(ValueError):
    pass


def utc_now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


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
    if any(v.get('status') not in STATUSES for v in requirements.values()):
        raise GraphError('invalid requirement status')
    if not g.get('objective') or not isinstance(g.get('history'), list):
        raise GraphError('objective/history missing')
    if not isinstance(g.get('revision'), int) or isinstance(g['revision'], bool):
        raise GraphError('revision missing')
    unit = g.get('unit', {})
    required(unit, 'id', 'edge', 'requirements', 'next_action')
    if not set(unit['requirements']) <= set(requirements):
        raise GraphError('unit references unknown requirements')
    if any(requirements[k]['status'] == 'deferred' for k in unit['requirements']):
        raise GraphError('unit cannot select deferred requirements')
    for value in (unit.get('risk_tier'), (g.get('assignment') or {}).get('risk_tier')):
        if value is not None and value not in tiers.TIERS:
            raise GraphError('risk_tier must be one of ' + ', '.join(tiers.TIERS))
    if g['stage'] in tiers.ORDER and g['stage'] not in tiers.steps(tiers.tier_of(g)):
        raise GraphError('stage is skipped by the unit risk tier')
    target = g.get('raid_target')
    if target is not None and (not isinstance(target, dict) or not all(isinstance(target.get(k), str) and target[k] for k in ('scenario', 'path'))):
        raise GraphError('raid_target needs scenario and path')
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
        # Rows without risk_tier predate tiers and followed the class_native order.
        legal = (
            (action in ('claim', 'release') and target == previous and previous != 'complete')
            or (action in ('refresh_support', 'amend_tests') and previous == target == 'implement')
            or (action == 'advance' and previous in RECEIPTS and target in tiers.successors(previous, row.get('risk_tier', tiers.DEFAULT_TIER)))
            or (action == 'route' and previous == 'route' and target == 'diagnose')
            or (action == 'rework' and previous in REWORKABLE and target in ('diagnose','route'))
            or (action == 'supersede' and previous in REWORKABLE and target == 'route')
            or (action in ('defer', 'reopen') and previous == target and previous in PARKING_STAGES)
            or (action == 'complete' and previous == 'route' and target == 'complete')
        )
        if not legal:
            raise GraphError('illegal transition in saved history')
        previous = row.get('to')
    if previous != g['stage']:
        raise GraphError('stage does not match saved history')
    if g.get('run'):
        validation = next((h['event'] for h in reversed(history) if h['unit_id'] == g['unit']['id']
                           and h['from'] == 'validate' and h['event']['action'] == 'advance'), {})
        recorded = validation.get('recorded_source_commit')
        if recorded is not None and (g['run'].get('source_scope') != 'recorded_source_only'
                or g['run'].get('launch_commit') != recorded
                or g['run'].get('build_identity') != g.get('build_identity')):
            raise GraphError('historical run source scope differs from recorded transition')
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
            verdict = requirement.get('verdict')
            if verdict is not None and (verdict.get('status') != 'pass'
                                        or (requirement.get('actor_id') and verdict.get('encounter_status') != 'pass')):
                raise GraphError('accepted requirement verdict is not pass')
        if requirement['status'] == 'deferred':
            parked = requirement.get('deferred') or {}
            revision = parked.get('revision')
            if (not str(parked.get('reason') or '').strip() or not str(parked.get('belongs_to') or '').strip()
                    or type(revision) is not int or not 0 <= revision < len(history)
                    or history[revision]['event'].get('action') != 'defer'
                    or key not in (history[revision]['event'].get('requirements') or {})):
                raise GraphError('deferred requirement lacks its recorded defer transition')
    fields = {
        'implement': ('assignment',), 'review': ('assignment', 'tested_files', 'implementer'),
        'build': ('assignment', 'tested_files', 'implementer'),
        'smoke': ('assignment', 'tested_files', 'build_identity'),
        'validate': ('assignment', 'tested_files', 'build_identity'),
        'assess': ('run',), 'publish': ('run', 'outcomes'),
    }
    required(g, *fields.get(g['stage'], ()))
    if g['stage'] == 'publish':
        pending = g.get('pending_acceptance')
        assessment = next((h for h in reversed(history) if h['from'] == 'assess' and h['event']['action'] == 'advance'), {})
        if not isinstance(pending, list) or not set(pending) <= set(unit['requirements']) or pending != assessment.get('proposed_acceptance'):
            raise GraphError('pending acceptance does not match assessment history')
        if not set(g.get('pending_verdict', {})) <= set(pending):
            raise GraphError('pending verdict does not match pending acceptance')
    if g['stage'] == 'complete' and any(r['status'] == 'open' for r in requirements.values()):
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
    return project(root, json.loads(data), data)


def project(root: Path, state: dict, data: bytes) -> dict:
    """Read-only resume projection of one validated state (data: its exact bytes)."""
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
    from tools.raid_program.graph_acceptance import finish_line
    finish = finish_line(root, g)
    return {
        'state_sha256': digest(data), 'revision': g['revision'],
        'diagnostic_entrypoint': shlex.join(['pixi', 'run', 'python', '-m', 'tools.raid_program.evidence_view', 'task', '--root', str(root.resolve())]),
        'transition_entrypoint': 'pixi run python -m tools.raid_program.workflow_step advance --receipt <receipt.json> --dry-run; repeat without --dry-run after validation, adding --owner for an existing claim',
        'encounter': g['encounter'],
        'parked_scenarios': sorted(state.get('parked_scenarios', {})),
        'bootstrap_inputs': inputs, 'changed_bootstrap_sources': input_changes,
        'objective': g['objective'], 'stage': g['stage'], 'unit': unit,
        'coordinator_skill': 'trinity-orchestrator',
        'parent_objective_complete': g['stage'] == 'complete',
        'owner_skill': unit.get('owner_skill'),
        'next_action': ('Initialization inputs have changed; consult current reviewed inputs before reusing that historical snapshot. ' if input_changes else '') + ('Claimed by ' + g['claim']['owner'] + '; reconcile this operation before continuing. ' if g.get('claim') else '') + (finish['work_item'] + ' ' if finish['work_item'] else '') + ACTIONS[g['stage']],
        'tier': (tiers.describe(g, g['stage']) | ({'build_reason': g['build_reason']} if g.get('build_reason') else {})
                 if g['stage'] != 'complete' else None),
        'finish_line': finish,
        'reusable_build': next((h['event']['receipt'] for h in reversed(g['history'])
                                if h['from'] == 'build' and h['event']['action'] == 'advance'), None),
        'open_requirements': {k: v for k, v in g['requirements'].items() if v['status'] == 'open'},
        # Parked outside this scenario's critical path; they never block completion.
        'deferred_requirements': {k: v for k, v in g['requirements'].items() if v['status'] == 'deferred'},
        'completed_measurements': g.get('completed_measurements', []),
        'receipts': g.get('receipts', {}), 'outcomes': g.get('outcomes', {}),
        'test_plan': {key: g.get('assignment', {}).get(key, [])
                      for key in ('owned_files', 'required_test_commands', 'acceptance_conditions')},
        'latest_assessment': latest_assessment(g),
        'superseded': latest_supersede(g),
        'same_edge_failures': g.get('failures', {}).get(unit['edge'], 0),
        'failure_counts_by_edge': g.get('failures', {}),
        'recent_attempts': recent_attempts(g),
        'retry_limit': 10,
        'claim': g.get('claim'), 'coordinator_worktree': g['coordinator_worktree'],
        'model_advice': ('Never required and never a gate. Optional: ask Jev to choose between the top two ranked damage gaps, '
                         'with Laya shadowing Jev on the same packet (offline Laya is recorded as not reviewed); '
                         'record both picks with tools.raid_program.jev_outcomes append.'),
        'execution': ('Parent objective accepted; report its evidence.' if g['stage'] == 'complete' else
                      'For implementation/resume requests, remain the coordinator and execute this stage, then the next returned stage. '
                      'An assessment, publication, route or specialist handoff does not finish the parent objective. '
                      'Respect explicit user limits or interruption; otherwise stop only for a demonstrated external blocker. ')
                     + ' This command is read-only. Reconcile queued_build and active controller receipts; never duplicate launches.',
    } | ({} if finish['target_present'] else {
        # Legacy dummy gate; the scoreboard verdict is the only finish line once a raid target exists.
        'dps_acceptance': {'minimum_reference_ratio': 0.95, 'scoring_seconds': 300,
                           'reference': 'current_promoted_self_provided', 'dtr_extra_allowance': False}})


def latest_supersede(g: dict) -> dict | None:
    row = next((h for h in reversed(g['history']) if h['event']['action'] == 'supersede'), None)
    if row is None:
        return None
    return {'revision': row['revision'], 'unit_id': row['unit_id'], 'reason': row['event']['reason'],
            **row['event']['superseded_by']}


def latest_assessment(g: dict) -> dict | None:
    """Newest assessment receipt, unless a later supersede replaced that evidence."""
    for row in reversed(g['history']):
        if row['event']['action'] == 'supersede':
            return None
        if row['from'] == 'assess' and row['event']['action'] == 'advance':
            return row['event']['receipt']
    return None


def recent_attempts(g: dict) -> list[dict]:
    """Expose retained failures across renamed units without guessing causality."""
    attempts = []
    for row in g['history']:
        event = row['event']
        if event['action'] in ('rework', 'supersede') or (row['from'] == 'assess' and event['action'] == 'advance'):
            attempts.append({'unit_id': row['unit_id'], 'revision': row['revision'],
                             'stage': row['from'], 'action': event['action'],
                             'reason': event.get('reason'), 'receipt': event.get('receipt'),
                             'proposed_acceptance': row.get('proposed_acceptance', [])})
    return attempts[-10:]


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
    from tools.raid_program.build_control_compatibility import coordination_path
    return not coordination_path(path)


def input_paths(value) -> set[str]:
    if isinstance(value, dict):
        paths = {value['path']} if isinstance(value.get('path'), str) else set()
        for child in value.values():
            paths.update(input_paths(child))
        return paths
    if isinstance(value, list):
        return set().union(*(input_paths(child) for child in value))
    return set()


def source_binding(root: Path, assignment: dict, expected_commit: str | None = None) -> str:
    from tools.raid_program.publication_delta import publication_paths
    head = git(root, 'rev-parse', 'HEAD')
    base = assignment['base_commit']
    git(root, 'merge-base', '--is-ancestor', base, head)
    protected = input_paths(assignment.get('validation_identity', {})) | input_paths(assignment.get('policy', {}))
    dirty = git(root, 'ls-files', '--modified', '--others', '--exclude-standard', '-z').split('\0')
    if any(p and (p in protected or code_path(p)) for p in dirty):
        raise GraphError('commit source changes before recording tests/review/build')
    # Inspect committed delta, including files omitted by a worker's declaration.
    changed = git(root, 'diff', '--name-only', '--no-renames', '-z', base, head).split('\0')
    published = publication_paths(root, base, head)
    # A selected input never becomes bookkeeping by being stored with outputs.
    published -= protected
    support = assignment.get('supporting_files', {})
    if support and (any((root / p).is_symlink() or not git(root, 'ls-tree', head, '--', p).startswith(
                        ('100644 blob ', '100755 blob ') if p == '.githooks/pre-commit' else '100644 blob ')
                        for p in support) or snapshot(root, list(support)) != support):
        raise GraphError('separately reviewed supporting files changed; obtain a new review')
    outside = [p for p in changed if p and (p in protected or (code_path(p) and p not in published
                  and p not in assignment['owned_files'] and p not in support))]
    if outside:
        raise GraphError('source delta contains files outside bounded assignment: ' + ', '.join(outside[:8])
                         + (f' (+{len(outside)-8} more)' if len(outside) > 8 else '')
                         + '; reconcile the plan source before implementation; do not edit its base to hide changes')
    if expected_commit is not None:
        git(root, 'merge-base', '--is-ancestor', expected_commit, head)
        delta = git(root, 'diff', '--name-only', '--no-renames', '-z', expected_commit, head).split('\0')
        published = publication_paths(root, expected_commit, head) - protected
        if any(p and (p in protected or code_path(p)) and p not in published for p in delta):
            raise GraphError('source changed since recorded tests/review/build')
    return head


def supporting_files(root: Path, review: dict, assignment: dict) -> dict:
    """A workflow repair cannot silently add gameplay edits or change inputs."""
    required(review, 'reviewer_session_id', 'review_report', 'file_hashes')
    file_ref(root, review['review_report'])
    if review.get('verdict') != 'approved':
        raise GraphError('separate approving review required for supporting changes')
    from tools.raid_program.review_execution import verify_review
    try:
        verify_review(root, review)
    except ValueError as exc:
        raise GraphError('independent supporting review execution: ' + str(exc)) from exc
    support = {p: sha for p, sha in review['file_hashes'].items() if p not in assignment['owned_files']}
    protected = input_paths(assignment['validation_identity']) | input_paths(assignment['policy'])
    def allowed(path):
        return (path.endswith('.py') and path.startswith(('tools/raid_program/', 'tools/bot_ml/', 'tests/'))
                or path.endswith('.json') and path.startswith('experiments/configs/')
                or path == '.githooks/pre-commit')
    if any(p in protected or not allowed(p) or (root/p).is_symlink() for p in support):
        raise GraphError('supporting changes are limited to workflow Python/tests/configs, excluding selected inputs')
    if not support or snapshot(root, list(support)) != support:
        raise GraphError('supporting review does not bind current files')
    return support


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
    if r.get('producer') in ('jev', 'laya', 'worker_checkpoint', 'bot_improvement_advice'):
        raise GraphError('model advice is not an acceptance receipt')
    return r


def verify_build(root: Path, r: dict, policy: dict) -> dict:
    """A build adapter bound to a gate-bearing queued native build under the plan policy."""
    required(r, 'source_commit', 'binary_sha256', 'build_receipt')
    if r.get('policy') != policy:
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
    return {k: r[k] for k in ('source_commit', 'binary_sha256')}


def reuse_adapter(root: Path, ref: dict, policy: dict) -> dict:
    """A recorded graph build adapter, or the queued-build receipt of the binary on disk."""
    doc = read(file_ref(root, ref))
    if doc.get('kind') == 'build' and doc.get('authority') == 'coordinator_attestation':
        return doc
    if 'ticket_id' not in doc:
        raise GraphError('reuse_build must reference a build adapter or queued-build receipt')
    binaries = [a.get('sha256') for a in doc.get('output_artifacts', [])
                if a.get('kind') == 'worldserver_elf' and a.get('produced_by_ticket') is True]
    if len(binaries) != 1:
        raise GraphError('reuse_build receipt must produce exactly one worldserver binary')
    return {'source_commit': doc.get('commit'), 'binary_sha256': binaries[0], 'build_receipt': ref, 'policy': policy}


def reusable_build(root: Path, g: dict) -> tuple[dict | None, str]:
    """Profile units skip build only when the tested source keeps a verified binary's native tree."""
    ref, policy = g['assignment'].get('reuse_build'), g['assignment']['policy']
    if not ref:
        return None, 'plan has no reuse_build'
    try:
        identity = verify_build(root, reuse_adapter(root, ref, policy), policy)
    except GraphError as exc:
        return None, 'reuse_build no longer verifies: ' + str(exc)
    source, tested = identity['source_commit'], g['tested_commit']
    if subprocess.run(['git', 'merge-base', '--is-ancestor', source, tested], cwd=root, capture_output=True).returncode:
        return None, 'reused build is not an ancestor of the tested source'
    native = native_changes(root, source, tested)
    if native:
        return None, 'native source changed since the reused build: ' + ', '.join(native[:5])
    return identity, ''


def superseded_evidence(root: Path, g: dict, evidence) -> None:
    """Commits in this history and/or a scoreboard label with kills; optional file references."""
    if not isinstance(evidence, dict):
        raise GraphError('superseded_by must be an object')
    commits, label = evidence.get('commits', []), evidence.get('scoreboard_label')
    if not isinstance(commits, list) or not (commits or label):
        raise GraphError('superseded_by needs commits and/or scoreboard_label')
    for commit in commits:
        resolved = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', str(commit) + '^{commit}'],
                                  cwd=root, capture_output=True, text=True).stdout.strip()
        if not isinstance(commit, str) or resolved != commit:
            raise GraphError('superseded_by commits must be full commit hashes')
        if subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=root, capture_output=True).returncode:
            raise GraphError('superseded_by commit is not in the current history: ' + commit)
    if label is not None:
        from tools.raid_program.graph_acceptance import evaluate, target_pointer
        if not isinstance(label, str) or not evaluate(root, target_pointer(g)['scenario'], label).get('kills'):
            raise GraphError('superseded_by scoreboard_label has no recorded kills')
    for ref in evidence.get('evidence', []):
        file_ref(root, ref)


def native_changes(root: Path, old: str, new: str) -> list[str]:
    return [p for p in git(root, 'diff', '--name-only', '--no-renames', '-z', old, new).split('\0') if p and tiers.native_path(p)]


def advice(root: Path, r: dict) -> None:
    """Validate advice if supplied; no provider call or disposition is required."""
    reviews = r.get('advice', {})
    if not isinstance(reviews, dict):
        raise GraphError('advice must be an optional object')
    for provider, review in reviews.items():
        if provider not in ('jev', 'laya'):
            raise GraphError('unknown advisory provider ' + provider)
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
    if event.get('recorded_source_commit') is not None and (action != 'advance' or stage != 'validate'):
        raise GraphError('recorded source is only valid when recording a completed validation')
    accepted_now = []
    claim = g.get('claim')
    if action != 'claim' and claim and event.get('claim_token') != claim['token']:
        raise GraphError('operation is claimed; reconcile owner before continuing')
    if action == 'advance' and stage in tiers.CLAIMED and not claim:
        raise GraphError('claim this operation before executing it')
    if stage == 'complete':
        raise GraphError('completed program; explicit new objective required')
    if action == 'claim':
        if claim:
            raise GraphError('operation already claimed')
        required(event, 'owner')
        if stage == 'implement':
            source_binding(root, g['assignment'])
        if stage == 'build':
            from tools.raid_program.workflow_build import preflight
            try:
                preflight(root, g['assignment'])
            except (ValueError, KeyError, SystemExit) as exc:
                raise GraphError('pre-build validation failed: ' + str(exc)) from exc
        token = digest(f"{g['unit']['id']}:{stage}:{g['revision']}:{event['owner']}".encode())
        g['claim'] = {'owner': event['owner'], 'token': token, 'operation_id': token, 'stage': stage,
                      'claimed_at': utc_now()}
    elif action == 'amend_tests' and stage == 'implement':
        from tools.raid_program.workflow_tests import amend_assignment
        g['assignment'] = amend_assignment(root, g['assignment'], event)
        # The same repair/claim continues. Scope only grows by test dependencies;
        # the original base, production files, obligations and failures survive.
    elif action == 'release':
        if not claim:
            raise GraphError('no claimed operation')
        reconciliation = read(file_ref(root, event.get('receipt')))
        from tools.raid_program.completed_operation import reject_completed_rework
        reject_completed_rework(root, g, reconciliation)
        if reconciliation.get('operation_id') != claim['operation_id'] or reconciliation.get('active_operation') is not False or reconciliation.get('ownership_checked') is not True or reconciliation.get('completed_operation') is not False or reconciliation.get('reusable_receipt_found') is not False:
            raise GraphError('release requires reconciliation; record completed operations instead of repeating them')
        g.pop('claim')
    elif action == 'refresh_support' and stage == 'implement':
        # Paused workflow maintenance must not restart the native hypothesis or
        # hide its source delta. Completed tests of the old support are retained
        # as evidence, but tests/review must run again on the refreshed source.
        r = read(file_ref(root, event.get('receipt')))
        required(r, 'reason', 'supporting_review', 'owned_file_hashes', 'prior_operation', 'prior_commit')
        prior = r['prior_operation']
        if prior.get('ownership_checked') is not True or prior.get('active_operation') is not False:
            raise GraphError('support refresh requires a stopped, reconciled operation')
        if claim and prior.get('operation_id') != claim['operation_id']:
            raise GraphError('support refresh operation mismatch')
        if r['owned_file_hashes'] != snapshot(root, g['assignment']['owned_files']):
            raise GraphError('support refresh cannot change native owned files')
        git(root, 'merge-base', '--is-ancestor', r['prior_commit'], 'HEAD')
        for path, sha in r['owned_file_hashes'].items():
            previous = subprocess.check_output(['git', 'show', r['prior_commit'] + ':' + path], cwd=root)
            if digest(previous) != sha:
                raise GraphError('native files changed since the paused operation')
        review = read(file_ref(root, r['supporting_review']))
        support = supporting_files(root, review, g['assignment'])
        g['assignment']['supporting_review'] = r['supporting_review']
        g['assignment']['supporting_files'] = support
        g.setdefault('support_refreshes', []).append(event['receipt'])
    elif action == 'advance' and stage in RECEIPTS:
        kind = RECEIPTS[stage]
        following = None
        r = _receipt(root, event, kind, g)
        if claim and r.get('operation_id') != claim['operation_id']:
            raise GraphError('receipt operation identity mismatch')
        if stage == 'diagnose':
            advice(root, r)
            required(r, 'hypothesis', 'forbidden_changes', 'acceptance_conditions', 'required_test_commands', 'base_commit', 'policy', 'validation_identity')
            file_ref(root, r['policy'])
            from tools.raid_program.workflow_build import build_commands
            try:
                build_commands(read(file_ref(root, r['policy'])))
            except (ValueError, KeyError, TypeError) as exc:
                raise GraphError('plan requires a frozen build/resource policy: ' + str(exc)) from exc
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
            if r.get('supporting_review'):
                review = read(file_ref(root, r['supporting_review']))
                required(review, 'reviewer_session_id', 'review_report', 'file_hashes')
                file_ref(root, review['review_report'])
                if review.get('verdict') != 'approved' or review['reviewer_session_id'] == r['producer']:
                    raise GraphError('separate approving review required for supporting changes')
                support = supporting_files(root, review, g['assignment'])
                g['assignment']['supporting_review'] = r['supporting_review']
                g['assignment']['supporting_files'] = support
            # Reject stale/out-of-scope source before spending implementation,
            # fixture and review time. Claim repeats this against later drift.
            source_binding(root, g['assignment'])
            if r.get('worker_context') is not None:
                from tools.raid_program.worker_packet import validate_context
                validate_context(root, r['worker_context'])
                g['assignment']['worker_context'] = r['worker_context']
            if r.get('risk_tier') is not None:
                if r['risk_tier'] not in tiers.TIERS:
                    raise GraphError('risk_tier must be one of ' + ', '.join(tiers.TIERS))
                unit_tier = g['unit'].get('risk_tier')
                if unit_tier and tiers.RANK[r['risk_tier']] < tiers.RANK[unit_tier]:
                    raise GraphError(f"plan risk_tier {r['risk_tier']} cannot lower the unit tier {unit_tier}")
                g['assignment']['risk_tier'] = r['risk_tier']
            if r.get('reuse_build') is not None:
                if tiers.tier_of(g) != 'profile':
                    raise GraphError('reuse_build is only for profile units; other tiers build')
                # Fail fast; a later verification failure only falls back to building.
                verify_build(root, reuse_adapter(root, r['reuse_build'], r['policy']), r['policy'])
                g['assignment']['reuse_build'] = r['reuse_build']
        elif stage in ('implement', 'review', 'build'):
            current_commit = source_binding(root, g['assignment'], g.get('tested_commit'))
            current = snapshot(root, g['assignment']['owned_files'])
            if r.get('file_hashes') != current:
                raise GraphError('receipt does not bind current owned files')
            if stage != 'implement' and current != g.get('tested_files'):
                raise GraphError('files changed after tests; reroute and retest')
            if stage == 'implement':
                advice(root, r)
                if r.get('source_and_state_stable') is False:
                    raise GraphError('source or state changed during test execution')
                tests = r.get('tests', [])
                for command in g['assignment']['required_test_commands']:
                    matching = [t for t in tests if t.get('command') == command]
                    if (len(matching) != 1 or type(matching[0].get('exit_status')) is not int
                            or matching[0]['exit_status'] != 0):
                        raise GraphError('required test did not pass: ' + command)
                g['tested_files'] = current
                g['tested_commit'] = current_commit
                g['implementer'] = r['producer']
                # Owned native files already raise the tier (graph_tiers.path_floor); keep a
                # diff check so a profile unit can never skip review for native code.
                if tiers.tier_of(g) == 'profile' and native_changes(root, g['assignment']['base_commit'], current_commit):
                    raise GraphError('profile unit diff touches native paths; own them in the plan (tier floor) and rework')
                if tiers.tier_of(g) == 'profile':
                    identity, reason = reusable_build(root, g)
                    if identity:
                        g['build_identity'] = identity
                        g['reused_build'] = g['assignment']['reuse_build']
                        following = 'validate'
                    else:
                        g['build_reason'] = reason
            elif stage == 'review':
                if r['producer'] == g['implementer'] or r.get('verdict') != 'approved':
                    raise GraphError('independent approving reviewer required')
                required(r, 'reviewer_session_id', 'review_report')
                if r['reviewer_session_id'] == g['implementer']:
                    raise GraphError('reviewer session must differ from implementer')
                report = file_ref(root, r['review_report'])
                if not report.read_text().strip() or r['review_report'] in (g.get('receipts', {}).get('tests'), event['receipt']):
                    raise GraphError('retain the separate reviewer response, not the implementation or adapter')
                from tools.raid_program.review_execution import verify_review
                try:
                    verify_review(root, r, implementer_session_id=g['implementer'])
                except ValueError as exc:
                    raise GraphError('independent review execution: ' + str(exc)) from exc
                g['source_base_commit'] = g['tested_commit']
            else:
                identity = verify_build(root, r, g['assignment']['policy'])
                source_binding(root, g['assignment'], r['source_commit'])
                g['build_identity'] = identity
        elif stage == 'smoke':
            source_binding(root, g['assignment'], g['build_identity']['source_commit'])
            if snapshot(root, g['assignment']['owned_files']) != g['tested_files']:
                raise GraphError('files changed since tested build')
            if r.get('build_identity') != g['build_identity']:
                raise GraphError('smoke/build mismatch')
            required(r, 'attempt_id', 'server_epoch')
            if r.get('closed') is not True or r.get('cleanup_verified') is not True:
                raise GraphError('attempt must be closed and cleaned before measurement')
            if r.get('scenario_kind') != 'raid' or r.get('clock') != 'completion_watchdog' or r.get('encounter') != g['encounter']:
                raise GraphError('smoke kill needs the program encounter under the completion watchdog')
            if r.get('terminal_reason') != 'clear':
                raise GraphError('smoke needs an observed kill; rework the unit on failure')
            g['smoke'] = {k: r[k] for k in ('attempt_id', 'server_epoch')}
        elif stage == 'validate':
            recorded = event.get('recorded_source_commit')
            if recorded is not None:
                if g.get('reused_build'):
                    raise GraphError('--recorded-source needs a unit built by its own build stage')
                from tools.raid_program.completed_operation import verify_recorded_source
                verify_recorded_source(root, g, recorded)
            else:
                # A reused binary predates the unit; its source must not change after tests.
                source_binding(root, g['assignment'], g['tested_commit'] if g.get('reused_build') else g['build_identity']['source_commit'])
            if r.get('validation_identity') != g['assignment']['validation_identity'] or r.get('scenario_kind') != g['assignment']['validation_identity']['scenario_kind']:
                raise GraphError('run scenario/roster/profile/route differs from assignment')
            if r.get('build_identity') != g['build_identity']:
                raise GraphError('run/build mismatch')
            if recorded is None and snapshot(root, g['assignment']['owned_files']) != g['tested_files']:
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
            if claim and claim.get('claimed_at'):
                g['run']['claimed_at'] = claim['claimed_at']
            if r.get('kill_ids') is not None:
                if not isinstance(r['kill_ids'], list) or not r['kill_ids'] or len(set(r['kill_ids'])) != len(r['kill_ids']):
                    raise GraphError('kill_ids must be a nonempty unique list')
                g['run']['kill_ids'] = r['kill_ids']
            label = r.get('scoreboard_label')
            if label is not None:
                if not isinstance(label, str) or not label.strip():
                    raise GraphError('scoreboard_label must be a non-empty string')
                g['run']['scoreboard_label'] = label
            if recorded is not None:
                g['run'].update(source_scope='recorded_source_only', launch_commit=recorded,
                                build_identity=g['build_identity'])
        elif stage == 'assess':
            from tools.raid_program.graph_acceptance import assess
            assess(root, g, r)
        elif stage == 'publish':
            for key in ('dvc_status_checked', 'dvc_push_completed', 'remote_verified', 'cleanup_verified'):
                if r.get(key) is not True:
                    raise GraphError('publication incomplete: ' + key)
            verdicts = g.get('pending_verdict', {})
            if verdicts:
                # The scoreboard may not change between assessment and publication.
                from tools.raid_program.graph_acceptance import verify_verdict
                for ref in {json.dumps(v['receipt'], sort_keys=True) for v in verdicts.values()}:
                    verify_verdict(root, g, json.loads(ref))
            for key in g.get('pending_acceptance', []):
                g['requirements'][key].update(status='accepted', receipt=event['receipt'], accepted_at_revision=g['revision'])
                if key in verdicts:
                    g['requirements'][key]['verdict'] = verdicts[key]
            accepted_now = g.get('pending_acceptance', [])
        g.setdefault('receipts', {})[kind] = event['receipt']
        g['stage'] = following or tiers.successors(stage, tiers.tier_of(g))[0]
    elif action == 'route' and stage == 'route':
        required(event, 'reason', 'unit')
        unit = event['unit']
        required(unit, 'id', 'edge', 'requirements', 'next_action')
        if unit.get('risk_tier') is not None and unit['risk_tier'] not in tiers.TIERS:
            raise GraphError('risk_tier must be one of ' + ', '.join(tiers.TIERS))
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
        # A new unit starts from current source, not the previous unit's base.
        # This establishes a diagnosis boundary; it accepts no code/performance.
        g['source_base_commit'] = git(root, 'rev-parse', 'HEAD')
        for key in (*UNIT_KEYS, 'run', 'pending_acceptance', 'pending_verdict', 'outcomes', 'receipts'):
            g.pop(key, None)
    elif action == 'rework' and stage in REWORKABLE:
        required(event, 'reason')
        rework = file_ref(root, event.get('receipt'))
        if claim and stage in ('implement', 'build', 'smoke', 'validate'):
            reconciliation = read(rework)
            from tools.raid_program.completed_operation import reject_completed_rework
            reject_completed_rework(root, g, reconciliation)
            if reconciliation.get('ownership_checked') is not True or reconciliation.get('active_operation') is not False or reconciliation.get('operation_id') != claim['operation_id'] or reconciliation.get('completed_operation') is not False or reconciliation.get('reusable_receipt_found') is not False:
                raise GraphError('reconcile controller/worker/build before abandoning claimed operation')
        edge = g['unit']['edge']
        g['failures'][edge] = g['failures'].get(edge, 0) + 1
        g['stage'] = 'route' if g['failures'][edge] >= 10 else 'diagnose'
        for key in (*UNIT_KEYS, 'receipts'):
            g.pop(key, None)
    elif action == 'supersede' and stage in REWORKABLE:
        # Work already done outside the graph closes the unit without counting a failure.
        required(event, 'reason', 'superseded_by')
        superseded_evidence(root, g, event['superseded_by'])
        if claim and stage in ('implement', 'build', 'smoke', 'validate'):
            reconciliation = read(file_ref(root, event.get('receipt')))
            from tools.raid_program.completed_operation import reject_completed_rework
            reject_completed_rework(root, g, reconciliation)
            if reconciliation.get('ownership_checked') is not True or reconciliation.get('active_operation') is not False or reconciliation.get('operation_id') != claim['operation_id']:
                raise GraphError('reconcile controller/worker/build before superseding a claimed operation')
        g['stage'] = 'route'
        for key in (*UNIT_KEYS, 'receipts'):
            g.pop(key, None)
    elif action in ('defer', 'reopen') and stage in PARKING_STAGES:
        if claim:
            raise GraphError('reconcile the claimed operation before parking requirements')
        changes = event.get('requirements')
        if not isinstance(changes, dict) or not changes:
            raise GraphError('requirements map {key: {reason, belongs_to}} required')
        for key, detail in changes.items():
            requirement = g['requirements'].get(key)
            if requirement is None:
                raise GraphError('unknown requirement: ' + str(key))
            if not isinstance(detail, dict) or not str(detail.get('reason') or '').strip():
                raise GraphError(key + ': reason required')
            if action == 'defer':
                if requirement['status'] != 'open':
                    raise GraphError(key + ': only open requirements can be deferred')
                if key in g['unit']['requirements']:
                    raise GraphError(key + ': route the current unit away from it before deferring')
                if not str(detail.get('belongs_to') or '').strip():
                    raise GraphError(key + ': belongs_to (where this work lives now) required')
                requirement.update(status='deferred', deferred={'reason': detail['reason'], 'belongs_to': detail['belongs_to'],
                                                                'revision': g['revision']})
            else:
                if requirement['status'] != 'deferred':
                    raise GraphError(key + ': only deferred requirements can be reopened')
                requirement['status'] = 'open'
                requirement['reopened'] = {'reason': detail['reason'], 'revision': g['revision'],
                                           'was_deferred': requirement.pop('deferred')}
    elif action == 'complete' and stage == 'route':
        if any(r['status'] == 'open' for r in g['requirements'].values()):
            raise GraphError('open requirements prevent completion')
        g['stage'] = 'complete'
    else:
        raise GraphError('invalid action for stage: ' + str(action))
    g['history'].append({'revision': g['revision'], 'unit_id': event['unit_id'], 'from': stage, 'to': g['stage'], 'event': event, 'accepted_requirements': accepted_now, 'proposed_acceptance': g.get('pending_acceptance', []) if stage == 'assess' else [],
                         'risk_tier': tiers.tier_of(g)})
    if action not in ('claim', 'release', 'amend_tests'):
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
