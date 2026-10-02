"""Remove only remote-verified client442 archives and their exact DVC cache objects."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import yaml
from . import lab_runtime as lab


def references():
    roots = [Path(line[9:]) for line in subprocess.check_output(
        ['git', 'worktree', 'list', '--porcelain'], cwd=lab.REPO, text=True).splitlines()
        if line.startswith('worktree ')]
    found = {}
    for root in roots:
        scan = subprocess.run(['rg', '--files', '--hidden', '-g', '*.dvc', str(root)],
                              capture_output=True, text=True)
        if scan.returncode not in [0, 1]:
            raise RuntimeError('cannot inspect worktree DVC references')
        for raw in scan.stdout.splitlines():
            path = Path(raw)
            for out in (yaml.safe_load(path.read_text()) or {}).get('outs', []):
                if out.get('md5'):
                    found.setdefault(out['md5'], []).append(path)
    return found


def evict(names, receipt):
    receipt = receipt.resolve()
    if not receipt.is_relative_to(lab.ROOT / 'evidence') or receipt.exists():
        raise ValueError('require a new private lab evidence receipt')
    cache = Path(subprocess.check_output(['dvc', 'cache', 'dir'], cwd=lab.REPO, text=True).strip()) / 'files/md5'
    refs = references()
    report = {'schema': 'client442_checkpoint_eviction_v1', 'started_at': time.time(),
              'scope': 'remote-verified client442 archives only; no global cache GC', 'rows': []}
    try:
        for name in names:
            if not re.fullmatch(r'442_[A-Za-z0-9_]+\.tar\.gz', name):
                raise ValueError('invalid client442 archive name')
            archive = lab.REPO / 'artifacts/client_harness' / name
            pointer = Path(str(archive) + '.dvc')
            outs = yaml.safe_load(pointer.read_text())['outs']
            if len(outs) != 1 or outs[0]['path'] != name or not re.fullmatch(r'[0-9a-f]{32}', outs[0].get('md5', '')):
                raise ValueError('unsupported checkpoint pointer')
            md5 = outs[0]['md5']; obj = cache / md5[:2] / md5[2:]
            row = {'pointer': str(pointer.relative_to(lab.REPO)), 'md5': md5}
            report['rows'].append(row)
            if any(p.parent.name != 'client_harness' or not p.name.startswith('442_') for p in refs.get(md5, [])):
                row['status'] = 'other_artifact_reference_preserved'; continue
            linked = False
            if not archive.exists():
                if not obj.exists():
                    row['status'] = 'already_absent'; continue
                os.link(obj, archive); linked = True
            try:
                if archive.is_symlink():
                    raise ValueError('checkpoint must be a regular archive')
                with archive.open('rb') as file:
                    if hashlib.file_digest(file, 'md5').hexdigest() != md5:
                        raise RuntimeError('archive differs from committed checkpoint')
                cloud = json.loads(subprocess.check_output(
                    ['dvc', 'status', '--cloud', '--json', row['pointer']], cwd=lab.REPO, text=True))
                if cloud:
                    row['status'] = 'remote_not_verified_preserved'; continue
                row.update(status='remote_verified_evicted', archive_bytes=archive.stat().st_size,
                           cache_bytes=obj.stat().st_size if obj.exists() else 0)
                archive.unlink()
                if obj.exists(): obj.unlink()
            finally:
                if linked and archive.exists(): archive.unlink()
            print(json.dumps(row), flush=True)
        pointers = [r['pointer'] for r in report['rows'] if r['status'] == 'remote_verified_evicted']
        if pointers:
            subprocess.run(['dvc', 'status', *pointers], cwd=lab.REPO, check=True)
            subprocess.run(['dvc', 'push', *pointers], cwd=lab.REPO, check=True)
    finally:
        report['finished_at'] = time.time()
        lab.private_write(receipt, json.dumps(report, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='+')
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(); evict(args.archives, args.receipt)


if __name__ == '__main__': main()
