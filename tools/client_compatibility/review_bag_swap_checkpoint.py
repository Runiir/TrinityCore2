"""Stream the actual DVC object and verify the whole occupied-swap closure."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import time
from urllib.request import urlopen

from . import lab_runtime as lab
from . import bag_swap_evidence as evidence
from .bag_swap_sources import private_json, bound
from .item_actionbar_contract import require
from .review_hunter_learn_checkpoint import DigestReader, manifest, dvc_object, remote_request, remote_options


def inspect_archive(raw, checkpoint, prefix):
    if any(row.get('path') == 'tracking/checkpoint.json' for row in checkpoint.get('file_manifest', [])
        if type(row) is dict):
        from .review_bag_swap_failed_checkpoint import inspect_archive as inspect_complete
        data, digests, whole, count = inspect_complete(raw, checkpoint, prefix)
        tracking = evidence.tracking_state()
        tracking.update(digests=digests, manifest=whole['manifest'], raw_journals=whole['raw_journals'],
            archived_metadata=whole['archived_metadata'], compressed_md5=whole['compressed_md5'],
            complete_manifest_verified=True)
        for member in evidence.TRACKING_MEMBERS:
            evidence.collect(member, whole['raw_journals'][member], data, tracking)
        return data, digests, tracking, count
    selected = manifest(checkpoint, prefix)
    selected.update({row['path']: row for row in checkpoint['file_manifest'] if row['path'].startswith(prefix) and
        row['path'].endswith('.jsonl')})
    data, digests, seen = {}, {}, set()
    tracking = evidence.tracking_state()
    tracking.update(digests=digests, manifest=selected, raw_journals={})
    reader = DigestReader(raw)
    with tarfile.open(fileobj=reader, mode='r|gz') as archive:
        for member in archive:
            if member.name.startswith(prefix) and Path(member.name).suffix in ('.json', '.png', '.jsonl'):
                require(member.name in selected, 'actual swap batch contains unmanifested source JSON/PNG/journal')
            if member.name in evidence.TRACKING_MEMBERS:
                require(member.isfile() and member.name not in tracking['members'], 'actual current journal duplicate or not a file')
                with archive.extractfile(member) as handle:
                    evidence.collect(member.name, (json.loads(line) for line in handle), data, tracking)
            if member.name not in selected:
                continue
            row = selected[member.name]
            require(member.isfile() and member.name not in seen and member.size == row['bytes'],
                'actual swap source member type, multiplicity or size differs')
            total, digest, chunks, first = 0, hashlib.sha256(), [], b''
            with archive.extractfile(member) as handle:
                while chunk := handle.read(1024 * 1024):
                    first = first or chunk[:8]
                    total += len(chunk)
                    digest.update(chunk)
                    if member.name.endswith(('.json', '.jsonl')):
                        require(total <= 256 * 1024 * 1024, 'source-owned swap JSON/journal exceeds its bounded size')
                        chunks.append(chunk)
            require(total == row['bytes'] and digest.hexdigest() == row['sha256'], 'actual full swap source bytes or SHA256 differ')
            if member.name.endswith('.json'):
                data[member.name] = json.loads(b''.join(chunks))
            elif member.name.endswith('.jsonl'):
                lines = b''.join(chunks).splitlines()
                require(len(lines) <= 250000, 'actual swap source journal exceeds bounded rows')
                tracking['raw_journals'][member.name] = [json.loads(line) for line in lines]
            else:
                require(first == b'\x89PNG\r\n\x1a\n', 'actual source-owned swap PNG is not a PNG')
            digests[member.name] = row['sha256']
            seen.add(member.name)
    while reader.read(1024 * 1024):
        pass
    require(seen == set(selected) and reader.bytes == checkpoint['bytes'] and
        reader.digest.hexdigest() == checkpoint['sha256'], 'actual compressed swap archive or full manifest differs')
    require(tracking['members'] == set(evidence.TRACKING_MEMBERS), 'actual archive lacks one current journal')
    return data, digests, tracking, reader.bytes


def review(directory, output):
    directory, output = Path(directory), Path(output)
    require(directory.is_absolute() and output.is_absolute() and '..' not in directory.parts and '..' not in output.parts and
        directory.parent == lab.ROOT / 'evidence' and output.is_relative_to(lab.ROOT / 'evidence') and
        not output.is_relative_to(directory) and not output.exists() and
        not any(path.is_symlink() for path in (directory, output, *directory.parents, *output.parents)),
        'new ordinary private review outside the immutable swap batch required')
    checkpoint_path = directory / 'checkpoint_receipt.json'
    checkpoint_ref = bound(checkpoint_path)
    checkpoint = private_json(checkpoint_path, False)
    require(checkpoint.get('cloud_verified') is True, 'swap checkpoint has not been synchronized')
    require(all(any(row.get('path') == member for row in checkpoint.get('file_manifest', []) if type(row) is dict)
        for member in (*evidence.TRACKING_MEMBERS, 'tracking/checkpoint.json')),
        'new swap checkpoint requires complete source-bound generic tracking manifest')
    pointer, oid = dvc_object(lab.REPO, checkpoint)
    pointer_path = lab.REPO / pointer
    require(pointer_path.stat().st_size <= 1024 * 1024 and
        not any(path.is_symlink() for path in (pointer_path, *pointer_path.parents)), 'ordinary actual DVC pointer required')
    pointer_raw = pointer_path.read_bytes()
    md5 = hashlib.md5()

    class ObjectReader:
        def __init__(self, stream):
            self.stream = stream

        def read(self, size=-1):
            raw = self.stream.read(size)
            md5.update(raw)
            return raw

    with urlopen(remote_request(remote_options(lab.REPO), oid), timeout=60) as raw:
        data, digests, tracking, count = inspect_archive(ObjectReader(raw), checkpoint,
            str(directory.relative_to(lab.ROOT)) + '/')
    require(md5.hexdigest() == oid, 'actual swap compressed DVC object key differs')
    result = evidence.proof(data, digests, tracking)
    require(bound(checkpoint_path) == checkpoint_ref and dvc_object(lab.REPO, checkpoint) == (pointer, oid) and
        pointer_path.read_bytes() == pointer_raw, 'actual checkpoint or pointer changed during complete remote verification')
    report = {'schema': 'client442_bag_swap_remote_review_v1', 'reviewed_at': time.time(),
        'checkpoint_source': checkpoint_ref, 'pointer_sha256': hashlib.sha256(pointer_raw).hexdigest(), 'object_md5': oid,
        'pointer': pointer, 'archive_sha256': checkpoint['sha256'], 'bytes': count,
        'actual_remote_verified': True, 'complete_json_png_verified': True,
        'complete_manifest_verified': tracking.get('complete_manifest_verified') is True,
        'complete_json_png_jsonl_verified': True,
        'json_members': sum(p.endswith('.json') for p in digests), 'png_members': sum(p.endswith('.png') for p in digests),
        'journal_members': sum(p.endswith('.jsonl') for p in digests), 'local_archive_created': False,
        'qualification_added': False, 'proof': result}
    lab.private_write(output, json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    review(a.directory, a.output)


if __name__ == '__main__':
    main()
