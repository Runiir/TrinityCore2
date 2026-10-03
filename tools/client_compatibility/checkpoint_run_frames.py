"""Offload selected old scratch or closed-episode frames, then prune verified copies."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import time
from dvclive import Live
from . import lab_runtime as lab


def select_frames(names, episodes):
    files = []
    for basename in sorted(set(names)):
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.png', basename):
            raise ValueError('only explicitly named top-level scratch PNGs are allowed')
        files.append((lab.ROOT / 'run' / basename, True))
    for basename in sorted(set(episodes)):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', basename):
            raise ValueError('require explicit top-level episode names')
        directory = lab.ROOT / 'evidence' / basename
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError('episode directory is absent or linked')
        provenance = [directory / 'episode.json']
        closure = directory / 'episode_closure.json'
        if closure.exists():
            provenance.append(closure)
        if any(file.is_symlink() or not file.is_file() for file in provenance):
            raise RuntimeError('episode provenance is absent or linked')
        episode = json.loads(provenance[0].read_text())
        closed = bool(episode.get('finished_at')) or (closure.exists() and
                 json.loads(closure.read_text()).get('closed') is True)
        if not closed:
            raise RuntimeError('active or unclosed episode cannot be pruned')
        frames = sorted(file for file in directory.rglob('*') if file.suffix.lower() in {'.png', '.webp'})
        if not frames:
            raise RuntimeError('selected episode contains no frames')
        files.extend((file, False) for file in provenance)
        files.extend((file, True) for file in frames)
    selected = []
    for file, prune in files:
        if any(parent.is_symlink() for parent in [file, *file.parents]) or not file.is_file():
            raise RuntimeError('selected file is absent or linked')
        if file.stat().st_mtime > time.time() - 3600:
            raise RuntimeError('selected file is less than an hour old')
        if prune:
            with file.open('rb') as handle:
                magic = handle.read(12)
            if not (magic.startswith(b'\x89PNG\r\n\x1a\n') if file.suffix.lower() == '.png'
                    else magic[:4] == b'RIFF' and magic[8:] == b'WEBP'):
                raise RuntimeError('selected frame format is invalid')
        selected.append({'path': str(file.relative_to(lab.ROOT)), 'bytes': file.stat().st_size,
                         'mtime': file.stat().st_mtime, 'sha256': lab.sha256(file), 'prune': prune})
    if not selected:
        raise ValueError('no frames selected')
    return selected


def checkpoint(names, name, receipt, episodes=()):
    receipt = receipt.resolve()
    if not receipt.is_relative_to(lab.ROOT / 'evidence') or receipt.exists():
        raise ValueError('require a new private cleanup receipt')
    if not re.fullmatch(r'442_[A-Za-z0-9_]+', name):
        raise ValueError('invalid checkpoint name')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=lab.REPO, text=True):
        raise RuntimeError('commit cleanup code before checkpointing')
    archive = lab.REPO / 'artifacts/client_harness' / (name + '.tar.gz')
    relative = str(archive.relative_to(lab.REPO)); pointer = relative + '.dvc'
    if archive.exists() or (lab.REPO / pointer).exists():
        raise RuntimeError('checkpoint name exists')
    selected = select_frames(names, episodes)
    frames = [row for row in selected if row['prune']]
    report = {'schema': 'client442_scratch_frames_checkpoint_v1', 'started_at': time.time(),
              'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip(),
              'scope': 'explicit old scratch or closed-episode frames; provenance retained locally',
              'episodes': list(episodes), 'files': selected,
              'raw_bytes': sum(row['bytes'] for row in frames), 'removed': []}
    try:
        with tempfile.TemporaryDirectory(dir=lab.ROOT / 'run/tmp') as staging:
            staging = Path(staging)
            lab.private_write(staging / 'manifest.json', json.dumps(report, indent=2) + '\n')
            with Live(dir=str(staging / 'live'), save_dvc_exp=False, dvcyaml=False, report=None) as live:
                live.log_param('code_commit', report['code_commit'])
                live.log_metric('frames', len(frames)); live.log_metric('raw_bytes', report['raw_bytes']); live.next_step()
            with tarfile.open(archive, 'w:gz', compresslevel=3) as tar:
                for row in selected:
                    tar.add(lab.ROOT / row['path'], arcname=row['path'])
                tar.add(staging, arcname='tracking')
            with tarfile.open(archive, 'r:gz') as tar:
                for row in selected:
                    with tar.extractfile(row['path']) as handle:
                        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
                    if digest != row['sha256']:
                        raise RuntimeError('scratch archive hash mismatch')
        for command in [['dvc', 'add', relative], ['dvc', 'status', pointer], ['dvc', 'push', pointer]]:
            subprocess.run(command, cwd=lab.REPO, check=True)
        if json.loads(subprocess.check_output(['dvc', 'status', '--cloud', '--json', pointer], cwd=lab.REPO, text=True)):
            raise RuntimeError('scratch checkpoint remote is not synchronized')
        report.update(pointer=pointer, archive_sha256=lab.sha256(archive), archive_bytes=archive.stat().st_size,
                      remote_verified=True)
        for row in selected:
            file = lab.ROOT / row['path']
            if (file.is_symlink() or file.stat().st_mtime != row['mtime'] or
                    file.stat().st_size != row['bytes'] or lab.sha256(file) != row['sha256']):
                raise RuntimeError('scratch frame changed before pruning')
        for row in frames:
            (lab.ROOT / row['path']).unlink(); report['removed'].append(row['path'])
    finally:
        report['finished_at'] = time.time(); lab.private_write(receipt, json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pointer': pointer, 'frames': len(frames), 'raw_bytes': report['raw_bytes'],
                      'archive_bytes': report['archive_bytes']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frame', action='append', default=[])
    parser.add_argument('--episode', action='append', default=[])
    parser.add_argument('--name', required=True); parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(); checkpoint(args.frame, args.name, args.receipt, args.episode)
