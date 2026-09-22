"""Extend necessary test coverage and execute a claimed unit's declared tests.

Uses the existing graph and tests receipt. Execution records do not certify that
a test proves the hypothesis; the independent reviewer must inspect that claim.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

from tools.raid_program import development_graph as graph


def amend_assignment(root: Path, assignment: dict, event: dict) -> dict:
    """Add test dependencies without rebasing, dropping tests or changing scope."""
    reason = event.get('reason')
    files, commands = event.get('add_files', []), event.get('add_commands', [])
    if not isinstance(reason, str) or not reason.strip():
        raise graph.GraphError('test amendment requires the dependency reason')
    if not isinstance(files, list) or not isinstance(commands, list) or not commands:
        raise graph.GraphError('test amendment requires added test commands')
    for name in files:
        if not isinstance(name, str):
            raise graph.GraphError('test dependency must be a file under tests/')
        path = Path(name)
        if (path.is_absolute() or '..' in path.parts or len(path.parts) < 2
                or path.parts[0] != 'tests' or path.as_posix() != name
                or (root/path).is_symlink()):
            raise graph.GraphError('test dependency must be a regular file under tests/')
    if files:
        graph.snapshot(root, files)
    if any(not isinstance(c, str) or not c.strip() for c in commands):
        raise graph.GraphError('test commands must be nonempty strings')
    result = copy.deepcopy(assignment)
    result['owned_files'] = list(dict.fromkeys(assignment['owned_files'] + files))
    result['required_test_commands'] = list(dict.fromkeys(assignment['required_test_commands'] + commands))
    if result == assignment:
        raise graph.GraphError('test amendment adds no file or command')
    return result


def amend(root: Path, *, files: list[str], commands: list[str], reason: str,
          owner: str | None, expected: str | None = None, dry_run: bool = False) -> dict:
    from tools.raid_program.workflow_step import _state_snapshot, _claimed_token, _dry_run_result
    state, sha = _state_snapshot(root)
    if expected is not None and sha != expected:
        raise graph.GraphError('state changed; resume before amending tests')
    g = state['development_graph']
    event = {'action': 'amend_tests', 'revision': g['revision'], 'unit_id': g['unit']['id'],
             'reason': reason, 'add_files': files, 'add_commands': commands}
    token = _claimed_token(g, owner)
    if token:
        event['claim_token'] = token
    result = _dry_run_result(root, event, sha, state)
    if not dry_run:
        result['new_state_sha256'] = graph.advance(root, event, sha)['state_sha256']
    return dict(result, dry_run=dry_run,
                next_action='Keep the repair and required fixture support. Commit affected source, then run workflow_step tests.')


def run_tests(root: Path, *, owner: str, producer: str, behavior_command: str,
              timeout: float = 300) -> dict:
    """Capture real command results with bounded stdout and immutable raw logs."""
    from tools.raid_program.workflow_step import _state_snapshot, _claimed_token, apply_step
    root = root.resolve()
    state, sha = _state_snapshot(root)
    g = state['development_graph']
    if g['stage'] != 'implement' or not g.get('claim'):
        raise graph.GraphError('tests require a claimed implementation')
    _claimed_token(g, owner)
    assignment = g['assignment']
    commands = assignment['required_test_commands']
    if not commands or behavior_command not in commands:
        raise graph.GraphError('select the declared command that exercises the claimed behavior')
    if not isinstance(producer, str) or not producer.strip() or timeout <= 0:
        raise graph.GraphError('implementer session identity and positive command timeout required')
    source = graph.source_binding(root, assignment)
    before = graph.snapshot(root, assignment['owned_files'])
    folder = root / 'artifacts/cata_raid_program' / ('tests-' + g['claim']['operation_id'] + '-' + source[:12] + '-' + sha[:12])
    target = folder / 'receipt.json'
    if folder.exists():
        if not target.is_file():
            raise graph.GraphError('test capture interrupted; inspect ' + str(folder) + ' before another execution')
        receipt = graph.read(target)
        if (receipt.get('producer') != producer or receipt.get('behavior_command') != behavior_command
                or receipt.get('source_commit') != source or receipt.get('file_hashes') != before):
            raise graph.GraphError('retained test identity differs; do not overwrite it')
        for ref in receipt['evidence']:
            graph.file_ref(root, ref)
        return _result(root, target, receipt, sha, owner)
    folder.mkdir(parents=True, exist_ok=False)
    evidence, results = [], []
    for index, command in enumerate(commands):
        raw_log = folder / f'{index:02d}.tmp'
        log = folder / f'{index:02d}.json'
        started = time.monotonic()
        timed_out = False
        with raw_log.open('xb') as stream:
            proc = subprocess.Popen(['bash', '-o', 'pipefail', '-c', command], cwd=root,
                                    stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                code = 124
            except BaseException:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise
        # Stream the output into the existing JSON evidence boundary. Raw test
        # output never enters model context, including a single enormous line.
        with raw_log.open('r', errors='backslashreplace') as src, log.open('x') as dst:
            dst.write('{"output_chunks":[')
            first = True
            while chunk := src.read(65536):
                if not first:
                    dst.write(',')
                dst.write(json.dumps(chunk))
                first = False
            dst.write(']}\n')
        raw_log.unlink()
        ref = {'path': log.relative_to(root).as_posix(), 'sha256': graph.digest(log.read_bytes())}
        evidence.append(ref)
        results.append({'command': command, 'exit_status': code, 'timed_out': timed_out,
                        'elapsed_seconds': round(time.monotonic()-started, 3), 'log': ref})
    stable = graph.digest((root/graph.STATE_PATH).read_bytes()) == sha
    try:
        stable = stable and graph.source_binding(root, assignment) == source and graph.snapshot(root, assignment['owned_files']) == before
    except graph.GraphError:
        stable = False
    receipt = {'kind': 'tests', 'authority': 'coordinator_attestation', 'unit_id': g['unit']['id'],
               'producer': producer, 'operation_id': g['claim']['operation_id'], 'source_commit': source,
               'file_hashes': before, 'tests': results, 'evidence': evidence,
               'source_and_state_stable': stable, 'behavior_command': behavior_command,
               'limits': 'Command execution is observed. Reviewer must verify behavior coverage; no native performance acceptance.'}
    target.write_text(json.dumps(receipt, indent=2) + '\n')
    return _result(root, target, receipt, sha, owner)


def _result(root, target, receipt, sha, owner):
    from tools.raid_program.workflow_step import apply_step
    stable = receipt['source_and_state_stable']
    results = receipt['tests']
    success = stable and all(r['exit_status'] == 0 for r in results)
    result = {'success': success, 'source_and_state_stable': stable,
              'receipt': target.relative_to(root).as_posix(),
              'tests': [{k: r[k] for k in ('command', 'exit_status', 'timed_out')} for r in results],
              'logs': target.parent.relative_to(root).as_posix(), 'next_command': None}
    if success:
        apply_step(root, target, owner=owner, expected_sha256=sha, dry_run=True)
        result['next_command'] = shlex.join(['pixi', 'run', 'python', '-m', 'tools.raid_program.workflow_step',
            '--root', str(root), 'advance', '--receipt', result['receipt'], '--owner', owner, '--expect', sha])
    else:
        result['next_action'] = 'Inspect the failed command log; repair or amend the dependency. Keep failed results; do not record a passing subset.'
    return result
