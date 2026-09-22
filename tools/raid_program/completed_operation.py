"""Keep operation completion separate from source admission and performance."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.raid_program import development_graph as graph


def completed_runs(root: Path, g: dict, reconciliation: dict | None = None) -> list[dict]:
    """Inspect compact receipts, including ones omitted by a reconciliation author."""
    claim = g.get('claim')
    if not claim or claim['stage'] != 'validate':
        return []
    candidates = {}
    for ref in (reconciliation or {}).get('evidence', []):
        path = graph.file_ref(root, ref)
        if path.suffix == '.json':
            candidates[path] = path.read_bytes()
    # This is the existing compact receipt directory, never raw report/log data.
    token = claim['operation_id'].encode()
    for path in (root / 'artifacts/cata_raid_program').glob('*.json'):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if token in payload:
            candidates[path] = payload
    found = []
    for path, payload in candidates.items():
        try:
            receipt = json.loads(payload)
        except (ValueError, UnicodeError) as exc:
            raise graph.GraphError('invalid operation evidence: ' + str(path)) from exc
        if not isinstance(receipt, dict) or receipt.get('kind') != 'run':
            continue
        if receipt.get('operation_id') != claim['operation_id'] or receipt.get('unit_id') != g['unit']['id']:
            continue
        if receipt.get('closed') is True:
            ref = {'path': str(path.relative_to(root)), 'sha256': graph.digest(payload)}
            graph.file_ref(root, ref)
            found.append(ref)
    return sorted(found, key=lambda r: r['path'])


def reject_completed_rework(root: Path, g: dict, reconciliation: dict) -> None:
    found = completed_runs(root, g, reconciliation)
    if found:
        raise graph.GraphError('operation already completed: ' + found[0]['path'] +
            '; record that run with workflow_step advance (use --recorded-source for a changed checkout). '
            'Performance rejection or missing cleanup is not permission to repeat the operation.')


def git_document(root: Path, commit: str, path: str) -> dict:
    try:
        return json.loads(subprocess.check_output(['git', 'show', commit + ':' + path], cwd=root,
                                                 stderr=subprocess.PIPE))
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise graph.GraphError('recorded source lacks valid ' + path) from exc


def launch_snapshot(root: Path, g: dict, commit: str) -> dict:
    if graph.git(root, 'rev-parse', commit + '^{commit}') != commit:
        raise graph.GraphError('recorded source requires a full commit identity')
    graph.git(root, 'merge-base', '--is-ancestor', commit, 'HEAD')
    state = git_document(root, commit, str(graph.STATE_PATH))
    graph.check_state(root, state)
    old = state['development_graph']
    if old['stage'] != 'validate' or old['unit']['id'] != g['unit']['id']:
        raise graph.GraphError('recorded source is not this validation operation')
    for key in ('claim', 'assignment', 'tested_files', 'tested_commit', 'build_identity'):
        if old.get(key) != g.get(key):
            raise graph.GraphError('recorded source identity mismatch: ' + key)
    return old


def find_launch_commit(root: Path, g: dict) -> str:
    if g['stage'] != 'validate' or not g.get('claim'):
        raise graph.GraphError('--recorded-source requires the original claimed validation')
    # Pickaxe limits candidates to commits changing this operation's occurrence
    # count. No branch checkout, source rewrite or arbitrary latest-run lookup.
    commits = graph.git(root, 'log', '--format=%H', '-S' + g['claim']['operation_id'],
                        '--', str(graph.STATE_PATH)).splitlines()
    for commit in reversed(commits):
        try:
            launch_snapshot(root, g, commit)
        except graph.GraphError:
            continue
        return commit
    raise graph.GraphError('no committed launch snapshot matches this claimed operation; retain evidence, do not rerun')


def verify_recorded_source(root: Path, g: dict, commit: str) -> None:
    old = launch_snapshot(root, g, commit)
    source = old['build_identity']['source_commit']
    graph.git(root, 'merge-base', '--is-ancestor', source, commit)
    # A stored claim cannot cover source changes made between build and launch.
    from tools.raid_program.publication_delta import publication_paths
    protected = graph.input_paths(old['assignment']['validation_identity']) | graph.input_paths(old['assignment']['policy'])
    published = publication_paths(root, source, commit) - protected
    changed = graph.git(root, 'diff', '--name-only', source, commit).splitlines()
    if any(p in protected or (graph.code_path(p) and p not in published) for p in changed):
        raise graph.GraphError('source changed between recorded build and launch')
    expected = dict(old['tested_files'])
    expected.update(old['assignment'].get('supporting_files', {}))
    for path, sha in expected.items():
        try:
            content = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=root, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            raise graph.GraphError('recorded file missing: ' + path) from exc
        if graph.digest(content) != sha:
            raise graph.GraphError('recorded file hash mismatch: ' + path)
    build = graph.read(graph.file_ref(root, old['receipts']['build']))
    if any(build.get(k) != v for k, v in old['build_identity'].items()):
        raise graph.GraphError('recorded build receipt identity mismatch')
