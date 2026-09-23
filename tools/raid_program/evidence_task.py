"""Read-only diagnostic commands bound to saved assessments, never file recency."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import tarfile

from tools.raid_program.evidence_inputs import load_input
from tools.raid_program.evidence_metrics import native_actors
from tools.raid_program.evidence_paging import command_with


def confined(root, value):
    """Resolve a persisted path and reject traversal or symlink escapes."""
    root = root.resolve()
    try:
        candidate = Path(value)
    except TypeError as exc:
        raise ValueError('receipt path is not a path') from exc
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not path.is_relative_to(root):
        raise ValueError('receipt path escapes repository')
    return path


def checked(root, descriptor):
    path = confined(root, descriptor['path'])
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != descriptor['sha256']:
        raise ValueError('receipt hash mismatch: ' + str(path))
    return json.loads(payload)


def report_input(root, run):
    """Find the report by its recorded content hash, not directory naming."""
    expected = run.get('report_summary', {}).get('actor_report_sha256')
    if not expected:
        raise ValueError('run has no actor_report_sha256; supply explicit reviewed inputs')
    pointers = [d for d in run.get('evidence', []) if d['path'].endswith('.tar.gz.dvc')]
    matches = []
    for descriptor in pointers:
        pointer = confined(root, descriptor['path'])
        if hashlib.sha256(pointer.read_bytes()).hexdigest() != descriptor['sha256']:
            raise ValueError('DVC pointer hash mismatch: ' + str(pointer))
        archive_path = confined(root, pointer.with_suffix(''))
        if not archive_path.is_file():
            raise ValueError('hydrate exact input: ' + shlex.join(['pixi', 'run', 'dvc', 'pull', str(pointer)]))
        with tarfile.open(archive_path) as archive:
            for member in archive:
                if member.isfile() and member.name.endswith('/report.json'):
                    payload = archive.extractfile(member).read()
                    if hashlib.sha256(payload).hexdigest() == expected:
                        matches.append(str(archive_path) + '::' + member.name)
    if len(matches) != 1:
        raise ValueError('run report hash must resolve to exactly one archive member')
    return matches[0]


def task_view(root):
    from tools.raid_program.development_graph import STATE_PATH
    from tools.raid_program.raid_workloop import build_spec_work_unit
    root = root.resolve()
    state_bytes = (root / STATE_PATH).read_bytes()
    graph = json.loads(state_bytes)['development_graph']
    result = {k: graph.get(k) for k in ('objective', 'stage', 'unit', 'claim', 'coordinator_worktree')}
    result.update(schema='evidence_task_v1', state_sha256=hashlib.sha256(state_bytes).hexdigest(),
                  open_requirements={k: v for k, v in graph['requirements'].items() if v['status'] != 'accepted'},
                  commands=[], limitations=['Read-only retained diagnosis. Does not change the active stage or authorize duplicate live work.'])
    assessment_ref = next((h['event']['receipt'] for h in reversed(graph['history'])
                           if h['from'] == 'assess' and h['event']['action'] == 'advance'), None)
    result['assessment'] = assessment_ref
    if assessment_ref is None:
        result['missing'] = 'No retained assessment; bind explicit inputs for compare/admission.'
        return result
    try:
        assessment = checked(root, assessment_ref)
        runs = [(d, checked(root, d)) for d in assessment.get('evidence', [])]
        runs = [(d, r) for d, r in runs if r.get('kind') == 'run' and r.get('unit_id') == assessment.get('unit_id')]
        if len(runs) != 1:
            raise ValueError('assessment must identify exactly one run receipt')
        descriptor, run = runs[0]
        current = report_input(root, run)
        actors = native_actors(load_input(current)[0])
        if len(actors) != 1:
            raise ValueError('multi-actor run needs explicit actor selection; use compare overview')
        actor = next(iter(actors))
        spec = run['target_spec']
        result['retained_run'] = dict(descriptor, unit_id=run['unit_id'], spec=spec, actor=actor)
        result['limitations'].append('The latest assessment belongs to the displayed retained unit. Check its relevance to the current task; it is not a new run.')
        benchmark = build_spec_work_unit(spec, root)['benchmark']
        refs = benchmark.get('rotation_review_reference_artifacts') or {}
        policy = benchmark.get('accepted_dps_reference_class')
        result['reference_catalog'] = {'root': str(root), 'state': benchmark.get('state'),
            'accepted_dps': benchmark.get('accepted_dps'), 'reference_class': policy,
            'generation_receipt': refs.get('generation_receipt'),
            'authority': 'Current promoted catalog projection in the requested root, not embedded run DPS.'}
        if benchmark.get('state') != 'ready' or policy is None:
            raise ValueError('promoted reference is not ready: ' + str(benchmark.get('state')))
        paths = {
            k: str(confined(root, refs[k]))
            for k in ('raid_sim_request', 'raid_sim_result', 'compute_stats')
            if refs.get(k)
        }
        if len(paths) != 3:
            raise ValueError('promoted reference lacks request/result/ComputeStats binding')
        for path in paths.values():
            payload = Path(path).read_bytes()
            if hashlib.sha256(payload).hexdigest() != Path(path).stem:
                raise ValueError('content-addressed reference hash mismatch: ' + path)
        result['reference_class'] = policy
        result['commands'].append({'purpose': 'Check joined setup gates before routing a setup/stat defect',
            'command': command_with(['admission'], current=current, actor=actor, reference_class=policy,
                wowsims_request=paths['raid_sim_request'], wowsims_result=paths['raid_sim_result'], compute_stats=paths['compute_stats'])})
        result['commands'].append({'purpose': 'Rank current versus promoted simulator signed damage gaps',
            'command': command_with(['compare'], current=current, actor=actor, wowsims=paths['raid_sim_result'], top=5)})
        if assessment.get('baseline'):
            baseline = checked(root, assessment['baseline'])
            prior = report_input(root, baseline)
            prior_actors = native_actors(load_input(prior)[0])
            if len(prior_actors) != 1 or baseline.get('target_spec') != spec:
                raise ValueError('baseline actor/spec requires explicit reviewed mapping')
            result['commands'].append({'purpose': 'Compare retained baseline, including setup confounders',
                'command': command_with(['compare'], current=current, baseline=prior, actor=actor,
                                        baseline_actor=next(iter(prior_actors)), top=5)})
    except (ValueError, OSError, KeyError, tarfile.TarError) as exc:
        result['missing'] = str(exc)
    return result


def task_summary(root, section='summary'):
    """Project the validated active graph, not its unbounded requirement history."""
    from tools.raid_program.development_graph import resume
    progress = resume(root)
    return progress_view(progress, root, section)


def progress_view(progress, root, section='summary'):
    """Shared CLI projection; complete graph data stays available explicitly."""
    tier, finish = progress.get('tier') or {}, progress.get('finish_line') or {}
    base = {'schema': 'evidence_task_summary_v1', 'state_sha256': progress['state_sha256'],
            'revision': progress['revision'], 'stage': progress['stage'],
            'coordinator_worktree': progress['coordinator_worktree'],
            'encounter': progress.get('encounter'), 'coordinator_skill': progress.get('coordinator_skill'),
            'dps_acceptance': progress.get('dps_acceptance'),
            # Detail sections share a 6000-character budget: keep these compact there.
            'tier': {k: tier[k] for k in ('risk_tier', 'remaining_steps') if k in tier} or None,
            'finish_line': {k: finish[k] for k in ('target_path', 'target_present', 'work_item') if k in finish} or None,
            'completed_measurement_count': len(progress.get('completed_measurements', []))}
    if section == 'unit':
        return base | {'unit': progress['unit'], 'test_plan': progress.get('test_plan', {}),
                       'test_execution': 'Commit source, then workflow_step tests --owner <claim owner> '
                           '--producer <implementer session ID> --behavior-command <exact declared command>. '
                           'Use workflow_step amend-tests for necessary test dependencies; do not remove them to fit the initial file list.'}
    if section == 'requirements':
        return base | {'open_requirements': progress['open_requirements']}
    if section == 'receipts':
        from tools.raid_program.completed_operation import completed_runs
        completed = completed_runs(root, progress)
        from tools.raid_program.build_handoff import result_path
        build_finish = None
        if progress['stage'] == 'build' and progress.get('claim'):
            saved = result_path(root, progress['claim']['operation_id'])
            if saved.is_file():
                build_finish = 'pixi run python -m tools.raid_program.workflow_build finish'
        return base | {'claim': progress['claim'], 'receipts': progress['receipts'],
                       'build_handoff_command': build_finish,
                       'latest_assessment': progress['latest_assessment'],
                       'completed_run_receipts': completed,
                       'record_completed_commands': [shlex.join(['pixi', 'run', 'python', '-m',
                           'tools.raid_program.workflow_step', 'advance', '--receipt', r['path'],
                           '--owner', progress['claim']['owner'], '--recorded-source', '--dry-run'])
                           for r in completed]}
    if section == 'references':
        retained = task_view(root)
        if retained.get('missing'):
            raise ValueError('task_reference_inputs_invalid: ' + retained['missing'])
        return base | {key: value for key, value in retained.items() if key not in {
            'objective', 'unit', 'claim', 'open_requirements', 'schema', 'stage', 'state_sha256'}}
    unit = progress['unit']
    claim = progress['claim']
    worker_ready = progress['stage'] == 'implement' and not claim
    return base | {
        'tier': progress.get('tier'), 'finish_line': progress.get('finish_line'),
        'objective': progress['objective'],
        'unit': {key: unit.get(key) for key in ('id', 'edge', 'owner_skill', 'risk_tier', 'objective', 'requirements', 'next_action')},
        'claim': claim,
        'blockers': {'claimed_operation_owner': claim.get('owner') if claim else None,
                     'changed_bootstrap_sources': progress['changed_bootstrap_sources'],
                     'same_edge_failures': progress['same_edge_failures']},
        'open_requirement_ids': list(progress['open_requirements']),
        'evidence': {'latest_assessment': progress['latest_assessment'],
                     'reusable_build': progress.get('reusable_build'),
                     'bound_receipt_kinds': list(progress['receipts'])},
        'next_action': progress['next_action'],
        'next_command': shlex.join(['pixi', 'run', 'python', '-m', 'tools.raid_program.workflow_step',
                                   '--root', str(root), 'packet']) if worker_ready else
                        command_with(['task'], root=root, section='receipts' if claim else 'unit', max_chars=6000),
        'next_command_purpose': 'Prepare the bounded worker packet before claiming implementation.' if worker_ready else
                               'Inspect the claimed operation receipts before reconciling ownership.' if claim else
                                'Read the exact work-unit constraints before executing the stage action.',
        'detail_commands': {name: command_with(['task'], root=root, section=name, max_chars=6000)
                            for name in ('unit', 'requirements', 'references')},
        'parent_objective_complete': progress['parent_objective_complete'],
    }
