"""Raid-program state: one file, one active program, parked programs kept intact.

The file is separate from the boss-level development graph
(``cata_raid_active_work_unit_v1.json``) and never writes it: a raid program
references boss scenarios by key. It lives under ``artifacts/cata_raid_program/``,
a recognized coordination path, so committing program progress after a build
keeps that build reusable. Writes take a Git-common-dir lock, compare the prior
state hash when one is given, and replace the file atomically.
"""
from __future__ import annotations

import copy
import fcntl
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from tools.raid_program.development_graph import GraphError, digest, utc_now

STATE_PATH = Path('artifacts/cata_raid_program/raid_program_state_v1.json')
SCHEMA = 'cata_raid_program_state_v1'
LOCK_NAME = 'raid-program-state.lock'
# 'review' (added 2026-09-29) sits between implement and build. Older states never hold it and load unchanged:
# rounds already built are never gated, and the review gate applies from the next build.
STAGES = ('plan', 'implement', 'review', 'build', 'run', 'e2e', 'complete')
FOCUS = ('program', 'boss')
# A program may be parked (another selected) only between rounds.
SWITCHABLE_STAGES = ('plan', 'e2e', 'complete')


def load(root: Path) -> tuple[dict | None, bytes]:
    path = root / STATE_PATH
    if not path.is_file():
        return None, b''
    data = path.read_bytes()
    state = json.loads(data)
    if not isinstance(state, dict):
        raise GraphError('raid program state must be a JSON object')
    return state, data


def state_sha256(data: bytes) -> str:
    return digest(data)


def check(root: Path, state: dict) -> None:
    if state.get('schema') != SCHEMA or state.get('version') != 1:
        raise GraphError('unsupported raid program state schema')
    if Path(str(state.get('coordinator_worktree'))).resolve() != root.resolve():
        raise GraphError('use the canonical coordinator worktree; do not fork raid program progress across worktrees')
    programs = state.get('programs')
    if not isinstance(programs, dict) or state.get('active_program') not in programs:
        raise GraphError('raid program state has no valid active program')
    if state.get('focus') not in FOCUS:
        raise GraphError('raid program focus must be program or boss')
    for key, program in programs.items():
        if not isinstance(program, dict) or program.get('program_id') != key:
            raise GraphError('raid program identity mismatch: ' + str(key))
        if program.get('stage') not in STAGES or type(program.get('round')) is not int or program['round'] < 1:
            raise GraphError('invalid raid program stage/round: ' + key)
        if not isinstance(program.get('units'), dict) or not isinstance(program.get('rounds'), list):
            raise GraphError('raid program units/rounds missing: ' + key)
        if program['stage'] == 'complete' and (
                any(unit.get('status') != 'accepted' for unit in program['units'].values())
                or program.get('e2e', {}).get('status') != 'accepted'):
            raise GraphError('complete raid program still has open units: ' + key)
        if program.get('e2e', {}).get('status') == 'accepted':
            last = (program['e2e'].get('results') or [{}])[-1]
            if last.get('outcome') != 'clear' or not (last.get('evidence') or {}).get('pointer'):
                raise GraphError('an accepted e2e unit needs a clear result with an archived evidence pointer: ' + key)


def _lock_path(root: Path) -> Path:
    try:
        common = subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=root, text=True,
                                         stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise GraphError('raid program state needs a git checkout for its lock') from error
    return (root / common).resolve() / LOCK_NAME


def update(root: Path, reducer: Callable[[dict | None], dict], expected_sha256: str | None = None) -> dict:
    """Apply ``reducer`` under the lock; return the new state. ``reducer`` gets a deep copy."""
    path = root / STATE_PATH
    with _lock_path(root).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        original = path.read_bytes() if path.is_file() else b''
        if expected_sha256 is not None and digest(original) != expected_sha256:
            raise GraphError('raid program state changed; resume before applying this step')
        old = json.loads(original) if original else None
        if old is not None:
            check(root, old)
        state = reducer(copy.deepcopy(old))
        check(root, state)
        if state == old:
            return state
        # Insertion order carries the boss order of the prerequisite DAG.
        encoded = (json.dumps(state, indent=2) + '\n').encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
            name = Path(temp.name)
            try:
                temp.write(encoded)
                temp.flush()
                os.fsync(temp.fileno())
                current = path.read_bytes() if path.is_file() else b''
                if current != original:
                    raise GraphError('raid program state changed during the update')
                os.replace(name, path)
            finally:
                name.unlink(missing_ok=True)
    return state


def history(program: dict, action: str, **details) -> None:
    program['revision'] = int(program.get('revision', 0)) + 1
    program.setdefault('history', []).append({'revision': program['revision'], 'utc': utc_now(),
                                              'action': action, **details})


def set_focus(root: Path, focus: str) -> bool:
    """Record whether ``resume`` continues the raid program or the boss graph; no-op without state."""
    if focus not in FOCUS:
        raise GraphError('focus must be program or boss')
    state, _ = load(root)
    if state is None or state.get('focus') == focus:
        return False

    def reducer(current: dict | None) -> dict:
        if current is None:
            raise GraphError('raid program state disappeared')
        current['focus'] = focus
        return current
    update(root, reducer)
    return True
