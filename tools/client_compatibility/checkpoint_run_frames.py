"""Offload explicitly selected old scratch screenshots, then remove verified copies."""
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


def checkpoint(names, name, receipt):
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
    selected = []
    for basename in sorted(set(names)):
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.png', basename):
            raise ValueError('only explicitly named top-level scratch PNGs are allowed')
        file = lab.ROOT / 'run' / basename
        if file.is_symlink() or not file.is_file() or file.stat().st_mtime > time.time() - 3600:
            raise RuntimeError('scratch frame is absent, linked or less than an hour old')
        with file.open('rb') as handle:
            if handle.read(8) != b'\x89PNG\r\n\x1a\n':
                raise RuntimeError('scratch frame is not a PNG')
        selected.append({'path': str(file.relative_to(lab.ROOT)), 'bytes': file.stat().st_size,
                         'mtime': file.stat().st_mtime, 'sha256': lab.sha256(file)})
    if not selected:
        raise ValueError('no frames selected')
    report = {'schema': 'client442_scratch_frames_checkpoint_v1', 'started_at': time.time(),
              'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip(),
              'scope': 'explicit old scratch PNGs; active experiment directories preserved',
              'files': selected, 'raw_bytes': sum(row['bytes'] for row in selected), 'removed': []}
    try:
        with tempfile.TemporaryDirectory(dir=lab.ROOT / 'run/tmp') as staging:
            staging = Path(staging)
            lab.private_write(staging / 'manifest.json', json.dumps(report, indent=2) + '\n')
            with Live(dir=str(staging / 'live'), save_dvc_exp=False, dvcyaml=False, report=None) as live:
                live.log_param('code_commit', report['code_commit'])
                live.log_metric('frames', len(selected)); live.log_metric('raw_bytes', report['raw_bytes']); live.next_step()
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
        for row in selected:
            (lab.ROOT / row['path']).unlink(); report['removed'].append(row['path'])
    finally:
        report['finished_at'] = time.time(); lab.private_write(receipt, json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pointer': pointer, 'frames': len(selected), 'raw_bytes': report['raw_bytes'],
                      'archive_bytes': report['archive_bytes']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frame', action='append', required=True)
    parser.add_argument('--name', required=True); parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(); checkpoint(args.frame, args.name, args.receipt)
