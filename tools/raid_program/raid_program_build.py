"""The single build of a raid-program round, and adoption of an interrupted one.

``build`` configures and builds the committed tree once through queued_build
with its default policy; the job count comes from the policy. Before building,
every file changed since the round's plan commit is matched against the
packets' owned patterns: a file two packets can own stops the build. The build
is also refused while a user decision is open, without an accepted review of
exactly the committed round diff, or while the raid DVC data is stale (see
``gates``). Rounds built before these gates existed are never re-gated. Step
results are persisted after each step in the queue's receipt directory
(outside the worktree, so no edit touches the tree mid-build). ``finish``
adopts a completed, gate-bearing worldserver ticket (like ``workflow_build
finish --queue-receipt``) without compiling again. A success always records the
worldserver's sha256; runs are later bound to it.
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
from pathlib import Path
from typing import Callable

from tools.raid_program import raid_program_packets as packets
from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError, utc_now

WORLDSERVER = Path('build/src/server/worldserver/worldserver')


def build_policy(root: Path) -> tuple[Path, dict, dict]:
    """queued_build's default policy (never a literal job count) and its exact argv."""
    from tools.raid_program import queued_build as queue
    from tools.raid_program.workflow_build import build_commands
    policy = json.loads((root / queue.DEFAULT_POLICY_RELATIVE).read_text(encoding='utf-8'))
    try:
        return queue.DEFAULT_POLICY_RELATIVE, policy, build_commands(policy)
    except RuntimeError as error:
        raise GraphError('build policy rejected: ' + str(error)) from error


def _policy_summary(root: Path) -> dict:
    path, policy, commands = build_policy(root)
    return {'policy': {'path': path.as_posix(), 'sha256': rounds.sha256_bytes((root / path).read_bytes()),
                       'policy_id': policy.get('policy_id'),
                       'maximum_compiler_jobs': int(policy['parallelism']['maximum_compiler_jobs'])},
            'commands': commands, '_policy': policy}


def progress_path(root: Path, program: dict) -> Path:
    from tools.raid_program import queued_build as queue
    slug = program['program_id'].replace(':', '_').lower()
    return queue.Paths.for_worktree(root).receipts / f"raid-program-{slug}-r{program['round']:02d}.json"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=False)


def ownership_check(root: Path, program: dict) -> dict:
    """Files changed since the plan commit, by owning packet; conflicts stop the build."""
    holder = rounds.current_round(program)
    base, head = holder.get('plan_commit'), rounds.git_head(root)
    if not base or not head:
        return {'checked': False, 'reason': 'no plan commit or HEAD to compare'}
    completed = _git(root, 'diff', '--name-only', '-z', '--no-renames', base, head, '--')
    if completed.returncode:
        raise GraphError('cannot diff the round since its plan commit ' + base)
    files = sorted(name.decode() for name in completed.stdout.split(b'\0') if name)
    owners = packets.changed_file_owners(holder['packets'], files)
    return {'checked': True, 'base': base, 'head': head, **owners}


def gates(root: Path, program: dict, commit: str = 'HEAD', data_status: Callable[[Path], dict] | None = None) -> dict:
    """Build gates for ``commit``: every user decision answered, an accepted review of exactly its round diff,
    and current raid DVC data (stages and closure). Each row has ``ok`` and its problem.

    The data gate reads the workspace (DVC status and payloads), so it speaks for ``commit`` only while the
    data-defining files (dvc.lock and both closure manifests) in the workspace equal those of ``commit``."""
    from tools.raid_program import raid_program_data as data, raid_program_review as review
    return {'decisions': review.decision_gate(program), 'review': review.review_gate(root, program, commit),
            'data': _data_at(root, commit, (data_status or data.data_gate)(root))}


def _data_at(root: Path, commit: str, gate: dict) -> dict:
    """The workspace data gate, refused when the workspace's data-defining files differ from ``commit``'s."""
    from tools.raid_program.raid_program_data import DATA_FILES
    from tools.raid_program.raid_program_review import EMPTY_TREE
    if not gate.get('ok'):
        return gate
    resolved = commit if commit != 'HEAD' or rounds.git_head(root) else EMPTY_TREE  # no commit yet: the empty tree
    completed = _git(root, 'diff', '--quiet', resolved, '--', *DATA_FILES)
    if completed.returncode == 1:
        problem = (f"the raid data files ({', '.join(DATA_FILES)}) in the workspace differ from {commit[:12]} "
                   '(an uncommitted refresh-data?), so the data gate does not speak for that commit')
    elif completed.returncode:
        problem = f'cannot compare the raid data files with {commit[:12]}: ' + completed.stderr.decode(errors='replace')[-200:]
    else:
        return gate
    return gate | {'ok': False, 'problems': [*gate.get('problems', []), problem]}


GATE_FIXES = {
    'decisions': 'ASK THE USER each open decision (resume lists them) and record it with program decide',
    'review': ('program review-diff --output <file outside the tree>, a reviewer in a separate session, then program '
               'review --verdict ... (reject: reopen the owning packet or fix coordinator files, then re-review)'),
    'data': 'program refresh-data --expect <state_sha256>, then commit the files it lists',
}
# --finish adopts a ticket only when its commit already holds current data; refreshed data needs a new build.
FINISH_FIXES = GATE_FIXES | {
    'data': ('program refresh-data --expect <state_sha256>, commit the files it lists, have the new round diff '
             'reviewed if it changed, then program build (a new build of that commit): --finish only adopts a ticket '
             'whose commit already holds current raid data'),
}


def refuse_on_gates(checks: dict, action: str = 'build', fixes: dict | None = None) -> None:
    failed = {name: row for name, row in checks.items() if not row.get('ok')}
    if failed:
        raise GraphError(f'program {action} refused: ' + ' | '.join(
            f"{name}: {row.get('problem') or '; '.join(row.get('problems') or [])} -> {(fixes or GATE_FIXES)[name]}"
            for name, row in failed.items()))


def _gate_record(checks: dict) -> dict:
    """What the build record keeps of its gates: the reviewed diff it built and each gate's outcome."""
    review = checks.get('review') or {}
    return {'ok': all(row.get('ok') for row in checks.values()),
            'review_diff_sha256': review.get('committed_diff_sha256'),
            'reviewer': (review.get('review') or {}).get('reviewer')}


def _binary_sha(receipt: dict) -> str | None:
    produced = [artifact for artifact in receipt.get('output_artifacts') or []
                if artifact.get('kind') == 'worldserver_elf' and artifact.get('produced_by_ticket') is True]
    return produced[0].get('sha256') if len(produced) == 1 else None


def _queue_runner(root: Path, policy: dict, kind: str, command: list[str]) -> tuple[int, dict, str, bool]:
    from tools.raid_program import queued_build as queue
    with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet):
        code, receipt = queue.run_ticket(root, policy, kind, command, None, None, None)
    path = queue.Paths.for_worktree(root).receipts / (receipt['ticket_id'] + '.json')
    gate = False
    if not code and receipt.get('classification') == 'success':
        gate = queue.verify_receipt(path, policy, allow_test_mode=False).get('gate_bearing') is True
    return code, receipt, str(path), gate


def _record(root: Path, data: bytes, record: dict) -> dict:
    def reducer(current: dict) -> dict:
        target = rounds.active(current)
        rounds.require(target, 'build')
        holder = rounds.current_round(target)
        holder.setdefault('build_attempts', []).append(record)
        if record['success']:
            holder['build'] = record
            target['stage'] = 'run'
        store.history(target, 'build', round=target['round'], success=record['success'],
                      source_commit=record['source_commit'], adopted=record.get('adopted', False))
        return current
    store.update(root, reducer, store.state_sha256(data))
    return record


def build(root: Path, expected_sha256: str | None = None, dry_run: bool = False,
          runner: Callable[..., tuple[int, dict, str, bool]] | None = None,
          worktree_state: Callable[[Path], dict] | None = None,
          data_status: Callable[[Path], dict] | None = None) -> dict:
    """One configure + worldserver build of the committed tree for the whole round.

    Refused (before compiling) on an ownership conflict, a dirty tree, an open user decision, a missing or
    stale accepted review of the committed round diff, or stale raid DVC data. ``--dry-run`` (review or
    build stage) shows the argv, the ownership check and every gate.
    """
    from tools.raid_program import queued_build as queue
    _, program, data = rounds.load_active(root)
    rounds.require(program, *(('review', 'build') if dry_run else ('build',)))
    summary = _policy_summary(root)
    policy = summary.pop('_policy')
    ownership = ownership_check(root, program)
    if dry_run:
        return summary | {'ownership': ownership, 'gates': gates(root, program, data_status=data_status)}
    rounds.check_expected(data, expected_sha256)
    if ownership.get('conflicts'):
        raise GraphError('files changed since the plan match two packets; reopen or fix before building: '
                         + json.dumps(ownership['conflicts'])[:600])
    observe = worktree_state or queue.worktree_state
    identity = observe(root)
    if not identity.get('clean'):
        raise GraphError('commit every handoff, patch request and the program state before building (clean tree)')
    checks = gates(root, program, data_status=data_status)
    refuse_on_gates(checks)
    run = runner or _queue_runner
    progress = progress_path(root, program)
    progress.parent.mkdir(parents=True, exist_ok=True)
    steps, binary_sha = [], None
    for kind, command in summary['commands'].items():
        if observe(root) != identity:
            raise GraphError('the tree changed during the build; no edits while a build runs')
        try:
            code, receipt, path, gate = run(root, policy, kind, command)
        except RuntimeError as error:
            raise GraphError(f'{kind} failed in the build queue: {error}; inspect queued_build status, then '
                             'program build --finish if a ticket completed') from error
        steps.append({'step': kind, 'receipt': path, 'exit_status': code,
                      'classification': receipt.get('classification'), 'gate_bearing': gate})
        if kind == 'worldserver_build':
            binary_sha = _binary_sha(receipt)
        progress.write_text(json.dumps({'source_commit': identity.get('commit'), 'steps': steps}, indent=2))
        if code or not gate:
            break
    complete = len(steps) == len(summary['commands']) and all(s['gate_bearing'] and not s['exit_status'] for s in steps)
    if complete and not binary_sha:
        binary = root / WORLDSERVER
        binary_sha = rounds.sha256_bytes(binary.read_bytes()) if binary.is_file() else None
    record = summary | {'source_commit': identity.get('commit'), 'steps': steps, 'ownership': ownership,
                        'success': bool(complete and binary_sha), 'worldserver_sha256': binary_sha if complete else None,
                        'gates': _gate_record(checks), 'recorded_utc': utc_now()}
    if complete and not binary_sha:
        record['error'] = 'the build produced no worldserver sha256; a success cannot be recorded'
    return _record(root, data, record)


def _launch_program(root: Path, commit: str, program_id: str) -> dict | None:
    shown = _git(root, 'show', f'{commit}:{store.STATE_PATH.as_posix()}')
    if shown.returncode:
        return None
    try:
        return (json.loads(shown.stdout).get('programs') or {}).get(program_id)
    except json.JSONDecodeError:
        return None


def finish(root: Path, queue_receipt: Path | None = None, expected_sha256: str | None = None,
           verifier: Callable[[Path, dict], dict] | None = None,
           data_status: Callable[[Path], dict] | None = None) -> dict:
    """Adopt a completed worldserver ticket of this round's build without compiling again.

    The ticket must be gate-bearing, belong to this worktree, build the worldserver from a
    commit whose program state was this round's build stage, and HEAD may have advanced
    from it only through coordination paths.
    """
    from tools.raid_program import queued_build as queue
    from tools.raid_program.build_control_compatibility import coordination_path
    _, program, data = rounds.load_active(root)
    rounds.require(program, 'build')
    rounds.check_expected(data, expected_sha256)
    summary = _policy_summary(root)
    policy = summary.pop('_policy')
    if queue_receipt is None:
        progress = progress_path(root, program)
        saved = json.loads(progress.read_text()) if progress.is_file() else {}
        done = [step for step in saved.get('steps') or [] if step['step'] == 'worldserver_build' and step['exit_status'] == 0]
        if len(done) != 1:
            raise GraphError('no completed worldserver ticket was saved for this round; pass --queue-receipt or rebuild')
        queue_receipt = Path(done[0]['receipt'])
    path = queue_receipt if queue_receipt.is_absolute() else root / queue_receipt
    queued = json.loads(path.read_bytes())
    verified = (verifier or (lambda file, rules: queue.verify_receipt(file, rules, allow_test_mode=False)))(path, policy)
    if verified.get('gate_bearing') is not True or verified.get('classification') != 'success':
        raise GraphError('the ticket is not a verified gate-bearing success')
    if Path(str(queued.get('worktree') or '')).resolve() != root.resolve():
        raise GraphError('the ticket belongs to another worktree')
    if queued.get('resource_class') != 'worldserver_build':
        raise GraphError('finish needs a worldserver_build ticket, not ' + str(queued.get('resource_class')))
    commit, head = str(queued.get('commit') or ''), rounds.git_head(root)
    launch = _launch_program(root, commit, program['program_id'])
    if not launch or launch.get('stage') != 'build' or launch.get('round') != program['round']:
        raise GraphError('the ticket was not built from this round\'s build stage')
    if _git(root, 'merge-base', '--is-ancestor', commit, str(head)).returncode:
        raise GraphError('the ticket commit is not an ancestor of HEAD')
    changed = _git(root, 'diff', '--name-only', '-z', '--no-renames', commit, str(head), '--')
    later = [name.decode() for name in changed.stdout.split(b'\0') if name]
    foreign = [name for name in later if not coordination_path(name)]
    if changed.returncode or foreign:
        raise GraphError('HEAD changed more than coordination files since the ticket: ' + ', '.join(foreign[:10]))
    binary_sha = _binary_sha(queued)
    if not binary_sha:
        raise GraphError('the ticket names no produced worldserver binary')
    ownership = ownership_check(root, program)
    if ownership.get('conflicts'):
        raise GraphError('files changed since the plan match two packets; reopen or fix before adopting the build: '
                         + json.dumps(ownership['conflicts'])[:600])
    # The ticket's own commit must carry the accepted review, the answered decisions and current raid data. HEAD
    # differs from it only in coordination files (checked above), none of which define DVC data, and the data gate
    # also requires the workspace's data-defining files to equal the ticket commit's.
    checks = gates(root, program, commit, data_status=data_status)
    refuse_on_gates(checks, 'build --finish', FINISH_FIXES)
    record = summary | {'source_commit': commit, 'adopted': True, 'success': True, 'worldserver_sha256': binary_sha,
                        'steps': [{'step': 'worldserver_build', 'receipt': str(path), 'exit_status': 0,
                                   'classification': 'success', 'gate_bearing': True}],
                        'ownership': ownership, 'gates': _gate_record(checks), 'recorded_utc': utc_now()}
    return _record(root, data, record)
