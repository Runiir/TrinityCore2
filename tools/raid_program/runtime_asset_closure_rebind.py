"""Rebind the runtime asset closure's DVC-produced classes to the current DVC payloads.

After ``dvc repro`` of a stage that produces a closure class (``validation_scenarios``
-> ``validation_routes``, ``validation_gear`` -> ``validation_gear_profiles``; the
manifest's ``dvc_provenance`` rows name them) the closure manifest
(``experiments/configs/runtime_asset_closure_manifest_v1.json``) still names the
previous payload, and shard_coordinator's runtime-asset preflight refuses the
run. ``rebind`` updates, for every ``dvc_provenance`` row:

* the row's md5 ``.dir``, size and nfiles from ``dvc.lock``;
* its class's ``expected_files`` (size and sha256 of each file; a file the
  stage added gets an entry, a file it removed loses its entry; every file must
  already have its recorded mode, normally 0644) and ``expected_inventory``;

then the ``asset_class_source`` sha256 in
``runtime_asset_input_closure_manifest_v1.json``. Both files must round-trip
exactly through ``json.dumps(indent=2)``; nothing is written otherwise.
``write=False`` reports the changes without writing; ``check_modes=False``
ignores file modes (runtime consumers read files whatever their mode; the
manifest's modes, not the disk's, enter the inventory hash).

This is the committed form of the coordinator's former
``/tmp/rebind_validation_routes.py``::

    pixi run python -m tools.raid_program.runtime_asset_closure_rebind [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

CLOSURE = Path('experiments/configs/runtime_asset_closure_manifest_v1.json')
INPUT = Path('experiments/configs/runtime_asset_input_closure_manifest_v1.json')
INVENTORY_KEYS = ('file_count', 'size_bytes', 'path_set_sha256', 'inventory_sha256')
DEFAULT_MODE = '0644'


class RebindError(ValueError):
    """The closure cannot be rebound as it stands (layout, mode or round-trip problem)."""


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2) + '\n'


def _load_roundtrip(path: Path) -> tuple[dict, str]:
    try:
        text = path.read_text(encoding='utf-8')
        value = json.loads(text)
    except (OSError, json.JSONDecodeError) as error:
        raise RebindError(f'{path}: {error}') from error
    if _dump(value) != text:
        raise RebindError(f'{path} does not round-trip through json.dumps(indent=2); refusing to rewrite it')
    return value, text


def _lock_out(lock: dict, stage: str, output: str) -> dict:
    try:
        outs = lock['stages'][stage]['outs']
    except (KeyError, TypeError) as error:
        raise RebindError(f'dvc.lock has no {stage} outs') from error
    for out in outs:
        if isinstance(out, dict) and out.get('path') == output:
            return out
    raise RebindError(f'dvc.lock {stage} does not output {output}')


def dvc_classes(manifest: dict) -> list[tuple[dict, dict]]:
    """(dvc_provenance row, asset class) pairs: every closure class a DVC stage produces."""
    classes = {row.get('id'): row for row in manifest.get('asset_classes') or [] if isinstance(row, dict)}
    pairs = []
    for row in manifest.get('dvc_provenance') or []:
        target = classes.get(row.get('class_id')) if isinstance(row, dict) else None
        if not isinstance(target, dict) or not isinstance(target.get('expected_files'), list) \
                or target.get('rule') != 'complete-directory' or target.get('path') != row.get('output_path'):
            raise RebindError(f'dvc_provenance row {row!r:.200} names no complete-directory class with expected_files')
        pairs.append((row, target))
    if not pairs:
        raise RebindError(f'{CLOSURE} has no dvc_provenance rows')
    return pairs


def output_dirs(root: Path) -> dict[str, dict[str, str]]:
    """{output dir: {file path: manifest mode}} of every DVC-produced closure class (for chmod before rebind)."""
    manifest = json.loads((Path(root) / CLOSURE).read_text(encoding='utf-8'))
    return {row['output_path']: {entry['path']: entry['mode'] for entry in target['expected_files']}
            for row, target in dvc_classes(manifest)}


def file_mode(path: Path) -> str:
    return f'{path.stat().st_mode & 0o7777:04o}'


def _directory_files(root: Path, output: str) -> list[str]:
    folder = root / output
    if not folder.is_dir():
        raise RebindError(f'{output} is missing; reproduce or pull its DVC stage first')
    children = sorted(folder.rglob('*'))
    if any(child.is_dir() or child.is_symlink() for child in children):
        raise RebindError(f'{output} holds subdirectories or symlinks; rebind handles flat directories only')
    return [child.relative_to(root).as_posix() for child in children]


def _sync_files(root: Path, target: dict, output: str, check_modes: bool, assign) -> None:
    present = _directory_files(root, output)
    entries = {entry['path']: entry for entry in target['expected_files']}
    modes = Counter(entry.get('mode') for entry in entries.values())
    default_mode = modes.most_common(1)[0][0] if modes else DEFAULT_MODE
    label = target['id']
    for path in sorted(set(entries) - set(present)):
        assign(target, None, None, f'{label}.expected_files: removed {path}')
    added = sorted(set(present) - set(entries))
    for path in added:
        assign(target, None, None, f'{label}.expected_files: added {path}')
        entries[path] = {'path': path, 'type': 'file', 'mode': default_mode, 'size_bytes': None, 'sha256': None}
    # The manifest's order is kept (an unchanged payload never rewrites the file); new files go last.
    order = [entry['path'] for entry in target['expected_files'] if entry['path'] in present] + added
    rows = []
    for path in order:
        entry = entries[path]
        if check_modes and file_mode(root / path) != entry['mode']:
            raise RebindError(f"{path} has mode {file_mode(root / path)}, not {entry['mode']}; chmod it first "
                              '(program refresh-data does)')
        data = (root / path).read_bytes()
        assign(entry, 'size_bytes', len(data), f'{path}.size_bytes')
        assign(entry, 'sha256', hashlib.sha256(data).hexdigest(), f'{path}.sha256')
        rows.append(entry)
    target['expected_files'] = rows


def rebind(root: Path, *, write: bool = True, check_modes: bool = True) -> dict:
    """Rebind (or with ``write=False`` only report) every DVC-produced closure class; returns the changes."""
    from tools.raid_program.runtime_asset_closure import _inventory
    root = Path(root)
    try:
        lock = yaml.safe_load((root / 'dvc.lock').read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as error:
        raise RebindError(f'dvc.lock: {error}') from error
    manifest, closure_text = _load_roundtrip(root / CLOSURE)
    changes: list[dict] = []

    def assign(block: dict, key: str | None, new: Any, label: str) -> None:
        if key is None:
            changes.append({'field': label, 'old': None, 'new': None})
        elif block.get(key) != new:
            changes.append({'field': label, 'old': block.get(key), 'new': new})
            block[key] = new

    for row, target in dvc_classes(manifest):
        out = _lock_out(lock, row['stage'], row['output_path'])
        for key in ('md5', 'size', 'nfiles'):
            assign(row, key, out.get(key), f"dvc_provenance[{row['class_id']}].{key}")
        _sync_files(root, target, row['output_path'], check_modes, assign)
        inventory = _inventory(target['expected_files'])
        for key in INVENTORY_KEYS:
            assign(target['expected_inventory'], key, inventory[key], f"{target['id']}.expected_inventory.{key}")

    new_closure = _dump(manifest)
    closure_sha = hashlib.sha256(new_closure.encode('utf-8')).hexdigest()
    input_manifest, input_text = _load_roundtrip(root / INPUT)
    source = input_manifest.get('asset_class_source')
    if not isinstance(source, dict) or source.get('path') != CLOSURE.as_posix():
        raise RebindError(f'{INPUT} asset_class_source does not name {CLOSURE}')
    assign(source, 'sha256', closure_sha, 'asset_class_source.sha256')
    new_input = _dump(input_manifest)
    files = [path.as_posix() for path, old, new in ((CLOSURE, closure_text, new_closure), (INPUT, input_text, new_input))
             if old != new]
    if write:
        if new_closure != closure_text:
            (root / CLOSURE).write_text(new_closure, encoding='utf-8')
        if new_input != input_text:
            (root / INPUT).write_text(new_input, encoding='utf-8')
    return {'bound': not changes, 'written': bool(write and files), 'changes': changes, 'files': files,
            'closure_sha256': closure_sha}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--check', action='store_true', help='report the changes without writing (exit 1 when stale)')
    parser.add_argument('--ignore-modes', action='store_true', help='do not require the manifest modes on disk')
    args = parser.parse_args(argv)
    try:
        result = rebind(args.root, write=not args.check, check_modes=not args.ignore_modes)
    except RebindError as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.check and not result['bound'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
