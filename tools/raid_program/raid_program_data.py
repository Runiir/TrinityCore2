"""Raid DVC data of a raid-program round: ``program refresh-data`` and the build's data gate.

The raid data stages are derived from ``dvc.yaml``: ``raid_shard_provisioning``
and ``validation_scenarios`` plus every stage upstream of them (a stage is
upstream when one of its outputs, ``outs``/``metrics``/``plots``, overlaps a
dependency), in dependency order: today ``validation_gear``,
``validation_provisioning``, ``validation_provisioning_verify``,
``raid_shard_provisioning`` and ``validation_scenarios``. The walk stops at the
world-database extracts (``world_knowledge`` reads the live world DB and
``world_planner`` is built from it; coordinator decision 2026-09-29): they are
reported when stale, never reproduced or gated here.

``refresh-data`` replaces the coordinator's manual sequence after shard data
changed (compositions, scenario rows, profiles, prerequisites, provisioning or
gear configs, overlays):

1. ``dvc status`` of the raid stages;
2. ``dvc repro --single-item`` of each stale stage in dependency order (a
   reproduced stage can make the next one stale, so the status is re-read before
   each stage);
3. the manifest file modes (0644) on every DVC-produced closure directory
   (``dataset/validation_scenarios`` and ``dataset/validation_gear_profiles``);
4. the runtime asset closure rebind (``runtime_asset_closure_rebind``);
5. ``dvc push`` of the raid stages' outputs;
6. the files the coordinator must commit.

It records one ``data_refreshes`` row in the current round. The build gate
(``data_gate``) refuses while a raid stage is stale or the closure does not
match the payload; file modes are a warning there (runtime consumers read
files whatever their mode). DVC runs through an injectable runner so tests
never touch the real remote.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

import yaml

from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError, utc_now
from tools.raid_program.runtime_asset_closure_rebind import CLOSURE, INPUT, RebindError, output_dirs, rebind

TERMINAL_STAGES = ('raid_shard_provisioning', 'validation_scenarios')
# World-database extracts: excluded from the raid data closure (coordinator decision 2026-09-29).
BOUNDARY_STAGES = ('world_knowledge', 'world_planner')
REFRESH_STAGES = ('implement', 'review', 'build')
# The files that define the raid data of a commit (the build gate compares them with the workspace).
DATA_FILES = ('dvc.lock', CLOSURE.as_posix(), INPUT.as_posix())
COMMIT_FILES = (*DATA_FILES, store.STATE_PATH.as_posix())
# (root, dvc argv, stream) -> CompletedProcess; ``stream`` sends output to stderr (repro and push are long).
DvcRunner = Callable[[Path, list[str], bool], subprocess.CompletedProcess]


def dvc_runner(root: Path, args: list[str], stream: bool = False) -> subprocess.CompletedProcess:
    executable = shutil.which('dvc')
    command = [executable] if executable else [sys.executable, '-m', 'dvc']
    if stream:
        sys.stdout.flush()
        return subprocess.run([*command, *args], cwd=root, stdout=sys.stderr, stderr=sys.stderr, text=True,
                              check=False, timeout=3600)
    return subprocess.run([*command, *args], cwd=root, capture_output=True, text=True, check=False, timeout=900)


def _paths(entries) -> list[str]:
    return [str(next(iter(entry))) if isinstance(entry, dict) else str(entry) for entry in entries or []]


def _overlaps(dependency: str, output: str) -> bool:
    return dependency == output or dependency.startswith(output + '/') or output.startswith(dependency + '/')


def raid_stages(root: Path) -> dict:
    """{'stages': the raid data stages in dependency order, 'boundary': reached boundary stages, 'upstream': edges}."""
    try:
        document = yaml.safe_load((Path(root) / 'dvc.yaml').read_text(encoding='utf-8'))
        stages = document['stages']
    except (OSError, KeyError, TypeError, yaml.YAMLError) as error:
        raise GraphError(f'dvc.yaml has no readable stages: {error}') from error
    missing = [name for name in TERMINAL_STAGES if name not in stages]
    if missing:
        raise GraphError('dvc.yaml lacks the raid stages ' + ', '.join(missing))
    outputs = {name: _paths(stage.get('outs')) + _paths(stage.get('metrics')) + _paths(stage.get('plots'))
               for name, stage in stages.items() if isinstance(stage, dict)}
    upstream = {name: sorted(other for other, produced in outputs.items() if other != name and any(
        _overlaps(dep, out) for dep in _paths(stage.get('deps')) for out in produced))
        for name, stage in stages.items() if isinstance(stage, dict)}
    closure, boundary, queue = set(), set(), list(TERMINAL_STAGES)
    while queue:
        name = queue.pop()
        if name in closure:
            continue
        closure.add(name)
        for parent in upstream.get(name, []):
            (boundary.add(parent) if parent in BOUNDARY_STAGES else queue.append(parent))
    order, placed = [], set()
    while len(order) < len(closure):  # dependency order, ties in dvc.yaml order
        ready = [name for name in stages if name in closure and name not in placed
                 and all(parent in placed or parent not in closure for parent in upstream[name])]
        if not ready:
            raise GraphError('the raid DVC stages form a cycle')
        order.append(ready[0])
        placed.add(ready[0])
    return {'stages': order, 'boundary': sorted(boundary),
            'upstream': {name: [parent for parent in upstream[name] if parent in closure] for name in order}}


def stage_status(root: Path, stages: list[str], dvc: DvcRunner | None = None) -> dict:
    """{'stale': [stage...] in the given order, 'detail': {...}}; GraphError when dvc cannot tell."""
    completed = (dvc or dvc_runner)(root, ['status', *stages, '--json'], False)
    if completed.returncode:
        raise GraphError('dvc status failed: ' + (completed.stderr or completed.stdout or '')[-600:])
    text = (completed.stdout or '').strip()
    try:
        detail = json.loads(text[text.index('{'):]) if '{' in text else {}
    except json.JSONDecodeError as error:
        raise GraphError('dvc status printed no JSON: ' + text[-300:]) from error
    return {'stale': [name for name in stages if name in detail or f'dvc.yaml:{name}' in detail], 'detail': detail}


def wrong_modes(root: Path) -> list[str]:
    try:
        expected = {path: mode for files in output_dirs(root).values() for path, mode in files.items()}
    except (OSError, ValueError, KeyError) as error:
        return [f'unreadable closure: {error}']
    return sorted(path for path, mode in expected.items()
                  if (root / path).is_file() and f'{(root / path).stat().st_mode & 0o7777:04o}' != mode)


def set_modes(root: Path, writable_only: bool = False) -> list[str]:
    """Give every file of the DVC-produced closure directories its manifest mode (a new file 0644);
    ``writable_only`` just adds user write (before a repro rewrites them)."""
    changed = []
    for folder, modes in output_dirs(root).items():
        directory = root / folder
        for path in sorted(directory.iterdir()) if directory.is_dir() else []:
            if not path.is_file() or path.is_symlink():
                continue
            current = path.stat().st_mode & 0o7777
            relative = path.relative_to(root).as_posix()
            wanted = current | 0o200 if writable_only else int(modes.get(relative, '0644'), 8)
            if current != wanted:
                path.chmod(wanted)
                changed.append(relative)
    return changed


def data_gate(root: Path, dvc: DvcRunner | None = None) -> dict:
    """Build gate: every raid DVC stage current and the closure matching the payloads. ``ok`` False names the fix."""
    problems, warnings = [], []
    try:
        graph = raid_stages(root)
        status = stage_status(root, graph['stages'] + graph['boundary'], dvc)
    except (GraphError, OSError, subprocess.SubprocessError) as error:
        graph, status = {'stages': [], 'boundary': []}, {'stale': []}
        problems.append('dvc status unavailable: ' + str(error)[:300])
    stale = [name for name in status['stale'] if name in graph['stages']]
    boundary = [name for name in status['stale'] if name in graph['boundary']]
    if stale:
        problems.append('stale raid DVC stages: ' + ', '.join(stale))
    if boundary:
        warnings.append('stale world-database stages (not reproduced by refresh-data): ' + ', '.join(boundary))
    try:
        closure = rebind(root, write=False, check_modes=False)
        if not closure['bound']:
            problems.append('the runtime asset closure does not match the DVC payloads ('
                            + ', '.join(change['field'] for change in closure['changes'][:4]) + ')')
    except (RebindError, OSError) as error:
        closure = {'error': str(error)[:400]}
        problems.append('runtime asset closure: ' + str(error)[:300])
    modes = wrong_modes(root)
    if modes:
        warnings.append(f'{len(modes)} closure file(s) differ from their manifest mode (refresh-data sets them)')
    return {'ok': not problems, 'problems': problems, 'warnings': warnings, 'stages': graph['stages'],
            'stale_stages': stale, 'stale_boundary_stages': boundary, 'closure_bound': closure.get('bound'),
            'wrong_modes': modes[:10],
            'fix': None if not problems else 'pixi run python -m tools.raid_program.raid_workloop program refresh-data '
                                             '--expect <state_sha256>, then commit the files it lists'}


def changed_files(root: Path, paths: tuple[str, ...] = COMMIT_FILES) -> list[str]:
    completed = subprocess.run(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=all', '--', *paths],
                               capture_output=True, text=True, check=False)
    return sorted(line[3:] for line in completed.stdout.splitlines() if len(line) > 3)


def reproduce(root: Path, stages: list[str], run: DvcRunner) -> tuple[list[str], dict]:
    """``dvc repro --single-item`` of each stale stage in dependency order; returns (reproduced, first status)."""
    first = stage_status(root, stages, run)
    status, reproduced = first, []
    for _ in range(len(stages) + 1):
        pending = [name for name in status['stale'] if name not in reproduced]
        if not pending:
            break
        stage = pending[0]
        set_modes(root, writable_only=True)  # DVC checkouts can be read-only; persist outputs are rewritten in place
        completed = run(root, ['repro', '--single-item', stage], True)
        if completed.returncode:
            raise GraphError(f'dvc repro --single-item {stage} failed (exit {completed.returncode}); read its output '
                             'on stderr, fix the stage inputs, and run program refresh-data again')
        reproduced.append(stage)
        status = stage_status(root, stages, run)
    if status['stale']:
        raise GraphError('raid DVC stages are still stale after dvc repro: ' + ', '.join(status['stale']))
    return reproduced, first


def refresh_data(root: Path, expected_sha256: str | None = None, dvc: DvcRunner | None = None) -> dict:
    """Reproduce stale raid stages, fix modes, rebind the closure, push, and list the files to commit."""
    _, program, data = rounds.load_active(root)
    rounds.require(program, *REFRESH_STAGES)
    rounds.check_expected(data, expected_sha256)
    run = dvc or dvc_runner
    graph = raid_stages(root)
    reproduced, before = reproduce(root, graph['stages'], run)
    report: dict = {'stages': graph['stages'], 'stale_before': before['stale'], 'reproduced': reproduced,
                    'status_detail': before['detail']}
    boundary = stage_status(root, graph['boundary'], run)['stale'] if graph['boundary'] else []
    report['stale_boundary_stages'] = boundary
    report['modes_fixed'] = set_modes(root)
    try:
        report['rebind'] = rebind(root)
    except RebindError as error:
        raise GraphError('runtime asset closure rebind failed: ' + str(error)) from error
    pushed = run(root, ['push', *graph['stages']], True)
    report['push'] = {'targets': graph['stages'], 'exit_status': pushed.returncode}
    if pushed.returncode:
        raise GraphError(f'dvc push failed (exit {pushed.returncode}); the data is refreshed locally: fix the remote '
                         'and run program refresh-data again (current stages are not reproduced again)')
    row = {'utc': utc_now(), 'stale_before': before['stale'], 'reproduced': reproduced,
           'modes_fixed': len(report['modes_fixed']), 'rebind_changes': len(report['rebind']['changes']),
           'stale_boundary_stages': boundary, 'pushed': True, 'head': rounds.git_head(root)}

    def reducer(state: dict) -> dict:
        target = rounds.active(state)
        rounds.require(target, *REFRESH_STAGES)
        rounds.current_round(target).setdefault('data_refreshes', []).append(row)
        store.history(target, 'refresh_data', round=target['round'], reproduced=reproduced,
                      rebind_changes=row['rebind_changes'])
        return state
    store.update(root, reducer, expected_sha256)
    files = changed_files(root)
    report['files_to_commit'] = files
    report['commit'] = (f"git add {' '.join(files)} && git commit -m '{program['name']} {program['mode']} round "
                        f"{program['round']}: refresh raid DVC data'") if files else None
    if boundary:
        report['warning'] = ('stale world-database stages were not reproduced: ' + ', '.join(boundary)
                             + '. They read the live world DB; reproduce them deliberately (dvc repro <stage>) only '
                               'when the world data itself changed, then run refresh-data again.')
    return report
