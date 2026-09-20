"""Recognize added DVC evidence outputs without exempting runtime inputs.

This applies to graph bookkeeping, not native build or launch admission.
Existing pointers, arbitrary ignore rules and executable/symlink files remain
source changes. No archive contents are trusted by this classification.
"""
from pathlib import Path, PurePosixPath
import subprocess

import yaml


PREFIX = 'artifacts/cata_raid_program/'


def publication_paths(root: Path, base: str, head: str) -> set[str]:
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True)

    changes = git('diff', '--name-status', '--no-renames', '-z', base, head).split('\0')
    added = {changes[i+1] for i in range(0, len(changes)-1, 2) if changes[i] == 'A'}
    result, outputs = set(), set()
    for name in added:
        path = PurePosixPath(name)
        if not name.startswith(PREFIX) or path.suffix != '.dvc':
            continue
        entry = git('ls-tree', head, '--', name)
        if not entry.startswith('100644 blob '):
            continue
        try:
            pointer = yaml.safe_load(git('show', f'{head}:{name}'))
            # A single adjacent output as produced by dvc add; no stages,
            # dependencies, path traversal or arbitrary ignore exceptions.
            if not isinstance(pointer, dict) or set(pointer) != {'outs'} or len(pointer['outs']) != 1:
                continue
            output = pointer['outs'][0]
            if not isinstance(output, dict) or output.get('path') != path.name[:-4]:
                continue
            if not isinstance(output.get('md5'), str) or not output['md5']:
                continue
        except (ValueError, TypeError, KeyError, yaml.YAMLError):
            continue
        result.add(name)
        outputs.add(str(path.with_suffix('')))
    ignores = {changes[i+1] for i in range(0, len(changes)-1, 2)
               if changes[i] in ('A', 'M') and changes[i+1].startswith(PREFIX)
               and PurePosixPath(changes[i+1]).name == '.gitignore'}
    for name in ignores:
        if not git('ls-tree', head, '--', name).startswith('100644 blob '):
            continue
        old = '' if name in added else git('show', f'{base}:{name}')
        new = git('show', f'{head}:{name}')
        # DVC appends anchored exact names; removal or editing older rules
        # cannot be used to hide source inputs.
        if not new.startswith(old):
            continue
        lines = new[len(old):].splitlines()
        parent = PurePosixPath(name).parent
        if lines and all(line.startswith('/') and '/' not in line[1:]
                         and not any(c in line for c in '*?[]!\\')
                         and str(parent / line[1:]) in outputs for line in lines):
            result.add(name)
    return result
