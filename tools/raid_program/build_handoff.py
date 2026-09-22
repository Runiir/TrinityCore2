"""Turn a verified queue result into a ready-to-advance graph build receipt."""
from pathlib import Path
import json
import shlex

from tools.raid_program import development_graph as graph


def write_once(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError('refusing to overwrite different build evidence: ' + str(path))
        return
    with path.open('xb') as stream:
        stream.write(payload)


def result_path(root, operation_id):
    from tools.raid_program.queued_build import Paths
    return Paths.for_worktree(root).receipts / ('workflow-' + operation_id + '.json')


def finish_build(root: Path, queue_receipt: Path | None = None) -> dict:
    from tools.raid_program.queued_build import verify_receipt
    from tools.raid_program.workflow_step import apply_step
    state = graph.read(root / graph.STATE_PATH)
    graph.check_state(root, state)
    g = state['development_graph']
    claim = g.get('claim') or {}
    if g['stage'] != 'build' or claim.get('stage') != 'build':
        raise ValueError('finish requires the original claimed build stage')
    if queue_receipt is None:
        saved = graph.read(result_path(root, claim['operation_id']))
        matches = [r for r in saved['steps'] if r['step'] == 'worldserver_build' and r['exit_status'] == 0]
        if len(matches) != 1:
            raise ValueError('no completed worldserver ticket; reconcile saved queue operation, do not rebuild blindly')
        queue_receipt = Path(matches[0]['receipt'])
    queue_receipt = queue_receipt if queue_receipt.is_absolute() else root / queue_receipt
    raw = queue_receipt.read_bytes()
    queued = json.loads(raw)
    assignment = g['assignment']
    verified = verify_receipt(queue_receipt, graph.read(graph.file_ref(root, assignment['policy'])), allow_test_mode=False)
    if verified.get('gate_bearing') is not True or verified.get('classification') != 'success':
        raise ValueError('build ticket is not a verified gate-bearing success')
    if queued.get('resource_class') != 'worldserver_build':
        raise ValueError('finish requires a worldserver_build ticket, not configure')
    source = queued['commit']
    launch = json.loads(graph.git(root, 'show', source + ':' + str(graph.STATE_PATH)))['development_graph']
    if launch.get('claim') != claim or launch['unit']['id'] != g['unit']['id']:
        raise ValueError('queue ticket belongs to a different build operation')
    graph.source_binding(root, assignment, source)
    if graph.snapshot(root, assignment['owned_files']) != g['tested_files']:
        raise ValueError('owned files changed after review')
    binaries = [a for a in queued.get('output_artifacts', [])
                if a.get('kind') == 'worldserver_elf' and a.get('produced_by_ticket') is True]
    if len(binaries) != 1:
        raise ValueError('expected exactly one produced worldserver binary')
    folder = root / 'artifacts/cata_raid_program'
    nested = folder / ('queued-build-' + claim['operation_id'] + '.json')
    write_once(nested, raw)
    ref = {'path': str(nested.relative_to(root)), 'sha256': graph.digest(raw)}
    receipt = {'kind': 'build', 'authority': 'coordinator_attestation',
               'unit_id': g['unit']['id'], 'producer': claim['owner'],
               'operation_id': claim['operation_id'], 'policy': assignment['policy'],
               'source_commit': source, 'binary_sha256': binaries[0]['sha256'],
               'file_hashes': g['tested_files'], 'build_receipt': ref, 'evidence': [ref]}
    target = folder / ('workflow-build-' + claim['operation_id'] + '.json')
    write_once(target, (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode())
    preview = apply_step(root, target, owner=claim['owner'], dry_run=True)
    argv = ['pixi', 'run', 'python', '-m', 'tools.raid_program.workflow_step', 'advance',
            '--receipt', str(target.relative_to(root)), '--owner', claim['owner'],
            '--expect', preview['state_sha256']]
    return {'success': True, 'source_commit': source, 'binary_sha256': receipt['binary_sha256'],
            'receipt': {'path': str(target.relative_to(root)), 'sha256': graph.digest(target.read_bytes())},
            'validated_transition': {'from': preview['from_stage'], 'to': preview['to_stage']},
            'next_command': shlex.join(argv),
            'next_action': 'Execute next_command; it records this build without compiling again.'}
