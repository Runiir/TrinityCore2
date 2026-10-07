"""Stream the configured DVC remote and prove the complete UI171 item roundtrip."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import time
from urllib.request import urlopen

from . import lab_runtime as lab
from . import item_actionbar_evidence as evidence
from .item_actionbar_contract import require
from .item_actionbar_sources import private_json
# These shared readers are stdlib-only and perform no action on import.
from .review_hunter_learn_checkpoint import DigestReader, manifest, dvc_object, remote_request, remote_options


def inspect_archive(raw, checkpoint, prefix):
    selected = manifest(checkpoint, prefix)
    data, digests, seen = {}, {}, set()
    tracking = evidence.tracking_state()
    tracking.update(digests=digests, manifest=selected)
    reader = DigestReader(raw)
    with tarfile.open(fileobj=reader, mode='r|gz') as archive:
        for member in archive:
            if member.name.startswith(prefix) and Path(member.name).suffix in ('.json', '.png'):
                require(member.name in selected, 'actual item batch contains unmanifested JSON or PNG')
            if member.name in evidence.TRACKING_MEMBERS:
                require(member.isfile() and member.name not in tracking['members'], 'actual journal is duplicate or not a file')
                with archive.extractfile(member) as handle:
                    evidence.collect(member.name, (json.loads(line) for line in handle), data, tracking)
            if member.name not in selected:
                continue
            row = selected[member.name]
            require(member.isfile() and member.name not in seen and member.size == row['bytes'],
                'actual selected item member type, multiplicity or size differs')
            total, digest, chunks, first = 0, hashlib.sha256(), [], b''
            with archive.extractfile(member) as handle:
                while chunk := handle.read(1024 * 1024):
                    if not first:
                        first = chunk[:8]
                    total += len(chunk)
                    digest.update(chunk)
                    if member.name.endswith('.json'):
                        require(total <= 64 * 1024 * 1024, 'item private JSON exceeds its bounded review size')
                        chunks.append(chunk)
            require(total == row['bytes'] and digest.hexdigest() == row['sha256'], 'actual complete JSON/PNG bytes or SHA256 differ')
            if member.name.endswith('.json'):
                data[member.name] = json.loads(b''.join(chunks))
            else:
                require(first == b'\x89PNG\r\n\x1a\n', 'actual manifest PNG is not a PNG image')
            digests[member.name] = row['sha256']
            seen.add(member.name)
    while reader.read(1024 * 1024):
        pass
    require(seen == set(selected) and reader.bytes == checkpoint['bytes'] and
        reader.digest.hexdigest() == checkpoint['sha256'], 'actual compressed remote identity or complete manifest differs')
    require(tracking['members'] == set(evidence.TRACKING_MEMBERS), 'actual archive lacks one of the two journals')
    return data, digests, tracking, reader.bytes


def review(directory, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    require(directory.parent == lab.ROOT / 'evidence' and output.is_relative_to(lab.ROOT / 'evidence') and
        not output.is_relative_to(directory) and not output.exists(), 'requires a new private review outside the immutable UI171 batch')
    checkpoint = private_json(directory / 'checkpoint_receipt.json', False)
    require(checkpoint.get('cloud_verified') is True, 'UI171 checkpoint has not been synchronized')
    pointer, oid = dvc_object(lab.REPO, checkpoint)
    request = remote_request(remote_options(lab.REPO), oid)
    with urlopen(request, timeout=60) as raw:
        data, digests, tracking, count = inspect_archive(raw, checkpoint, str(directory.relative_to(lab.ROOT)) + '/')
    result = evidence.proof(data, digests, tracking)
    report = {'schema': 'client442_item_actionbar_remote_review_v1', 'reviewed_at': time.time(),
        'pointer': pointer, 'archive_sha256': checkpoint['sha256'], 'bytes': count,
        'actual_remote_verified': True, 'complete_json_png_verified': True,
        'json_members': sum(p.endswith('.json') for p in digests), 'png_members': sum(p.endswith('.png') for p in digests),
        'local_archive_created': False, 'qualification_added': False, 'proof': result}
    lab.private_write(output, json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.directory, args.output)


if __name__ == '__main__':
    main()
