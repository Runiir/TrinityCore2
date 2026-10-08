"""Stream and verify the complete excluded failed-entry DVC checkpoint."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import time
import zlib

from . import bag_swap_failed_evidence as evidence
from .item_actionbar_contract import require, strict_equal

MAX_JSON = MAX_JOURNAL = 256 * 1024 * 1024
MAX_LINE, MAX_UNCOMPRESSED = 4 * 1024 * 1024, 4 * 1024 * 1024 * 1024
REPO = Path(__file__).resolve().parents[2]


def _name(value):
    require(type(value) is str and value and '\\' not in value and
        not PurePosixPath(value).is_absolute() and all(p not in ('', '.', '..') for p in value.split('/')),
        'canonical ordinary relative archive member required')
    return value


class GzipReader:
    """One CRC-checked gzip member, bounded decompression, and actual raw EOF."""
    def __init__(self, stream):
        self.stream, self.decoder = stream, zlib.decompressobj(31)
        self.pending, self.complete = b'', False
        self.digest, self.md5 = hashlib.sha256(), hashlib.md5()
        self.bytes = self.delivered = 0

    def _raw(self, size):
        raw = self.stream.read(size)
        require(type(raw) is bytes, 'actual compressed byte stream required')
        self.digest.update(raw)
        self.md5.update(raw)
        self.bytes += len(raw)
        return raw

    def read(self, size=-1):
        size = 1024 * 1024 if size < 0 else size
        if size == 0 or self.complete:
            return b''
        out = bytearray()
        try:
            while len(out) < size and not self.complete:
                raw = self.pending or self._raw(64 * 1024)
                chunk = self.decoder.decompress(raw, size - len(out))
                self.pending = self.decoder.unconsumed_tail
                out.extend(chunk)
                if self.decoder.eof:
                    require(not self.decoder.unused_data and not self.pending and not self._raw(1),
                        'compressed gzip has a trailing byte or concatenated member')
                    self.complete = True
                elif not raw and not chunk:
                    raise RuntimeError('compressed gzip is truncated before its CRC-checked EOF')
        except zlib.error as error:
            raise RuntimeError('compressed gzip CRC or payload differs') from error
        self.delivered += len(out)
        require(self.delivered <= MAX_UNCOMPRESSED, 'bounded complete archive expansion exceeded')
        return bytes(out)


def manifest(checkpoint, prefix):
    require(type(prefix) is str and prefix.endswith('/'), 'one canonical source batch prefix required')
    _name(prefix[:-1])
    require(type(checkpoint) is dict and type(checkpoint.get('bytes')) is int and checkpoint['bytes'] > 0 and
        type(checkpoint.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', checkpoint['sha256']),
        'actual compressed checkpoint SHA256 and bytes required')
    rows = checkpoint.get('file_manifest')
    require(type(rows) is list and rows and all(type(r) is dict for r in rows), 'complete checkpoint file manifest required')
    selected, paths = {}, set()
    for row in rows:
        path = _name(row.get('path'))
        require(path not in paths and set(row) == {'path', 'bytes', 'sha256'} and type(row['bytes']) is int and
            row['bytes'] >= 0 and type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']),
            'unique typed actual checkpoint manifest row required')
        paths.add(path)
        selected[path] = row
    require(set((*evidence.TRACKING_MEMBERS, 'tracking/checkpoint.json')) <= set(selected) and any(p.endswith('/episode.json') for p in selected) and
        any(p.endswith('.png') for p in selected), 'whole source JSON/PNG and two SHA-bound tracking journals required')
    return selected


def _json(raw):
    def invalid(value): raise RuntimeError('nonfinite JSON constant: ' + value)
    try:
        return json.loads(raw, parse_constant=invalid)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError('source archive contains malformed complete JSON bytes') from error


def _journal(handle, size):
    require(size <= MAX_JOURNAL, 'bounded full journal declared bytes exceeded')
    rows, total, digest, pending = [], 0, hashlib.sha256(), b''
    while chunk := handle.read(1024 * 1024):
        total += len(chunk)
        digest.update(chunk)
        require(total <= MAX_JOURNAL, 'bounded full journal actual bytes exceeded')
        pending += chunk
        lines = pending.split(b'\n')
        pending = lines.pop()
        for line in lines:
            require(len(line) <= MAX_LINE and line and len(rows) < evidence.MAX_ROWS, 'bounded complete JSONL row required')
            row = _json(line)
            require(type(row) is dict, 'whole source journal must contain objects')
            rows.append(row)
        require(len(pending) <= MAX_LINE, 'bounded complete JSONL row required')
    require(not pending, 'whole JSONL must retain its final newline and complete EOF row')
    return rows, total, digest.hexdigest()


def inspect_archive(raw, checkpoint, prefix):
    selected = manifest(checkpoint, prefix)
    data, digests, seen, all_members = {}, {}, set(), set()
    tracking = evidence.tracking_state()
    tracking.update(digests=digests, manifest=selected, batch_prefix=prefix)
    reader, last_end = GzipReader(raw), 0
    try:
        # A 512-byte stream buffer leaves no unread nonzero tar payload hidden
        # behind the first zero header when ordinary tar iteration terminates.
        with tarfile.open(fileobj=reader, mode='r|', bufsize=512) as archive:
            for member in archive:
                name = _name(member.name)
                require(name not in all_members and (member.isfile() or member.isdir()),
                    'actual archive member duplicates or links/special files are forbidden')
                all_members.add(name)
                last_end = member.offset_data + ((member.size + 511) // 512) * 512
                if name.endswith(('.json', '.png', '.jsonl')) or member.isfile() and name.startswith('tracking/'):
                    require(name in selected, 'actual archive has unmanifested JSON/PNG/journal or tracking file')
                if name not in selected:
                    continue
                expected = selected.get(name, {'bytes': member.size})
                require(member.isfile() and name not in seen and member.size == expected['bytes'],
                    'actual complete source type, multiplicity or bytes differ')
                with archive.extractfile(member) as handle:
                    if name.endswith('.jsonl'):
                        rows, total, digest = _journal(handle, member.size)
                        tracking['raw_journals'][name] = rows
                        if name in evidence.TRACKING_MEMBERS:
                            evidence.collect(name, rows, data, tracking)
                            tracking['journal_counts'][name] = {'rows': len(rows), 'bytes': total, 'sha256': digest}
                    else:
                        require(not name.endswith('.json') or member.size <= MAX_JSON, 'bounded source JSON declared bytes exceeded')
                        total, sha, parts, first = 0, hashlib.sha256(), [], b''
                        while chunk := handle.read(1024 * 1024):
                            total += len(chunk)
                            sha.update(chunk)
                            first = first or chunk[:8]
                            if name.endswith('.json'):
                                require(total <= MAX_JSON, 'bounded source JSON actual bytes exceeded')
                                parts.append(chunk)
                        digest = sha.hexdigest()
                        if name.endswith('.json'):
                            data[name] = _json(b''.join(parts))
                        elif name.endswith('.png'):
                            require(first == b'\x89PNG\r\n\x1a\n', 'source-owned image must contain PNG bytes')
                require(total == expected['bytes'] and ('sha256' not in expected or digest == expected['sha256']),
                    'full manifest member SHA256 or bytes differ')
                digests[name] = digest
                if name in selected:
                    seen.add(name)
            require(archive.fileobj.tell() == reader.delivered, 'unread tar stream buffer cannot hide trailing payload')
        while chunk := reader.read(1024 * 1024):
            require(not chunk.strip(b'\0'), 'nonzero hidden tar payload follows logical EOF')
    except (tarfile.TarError, EOFError) as error:
        raise RuntimeError('actual archive tar payload is malformed or truncated') from error
    require(reader.complete and reader.delivered % 512 == 0 and reader.delivered >= last_end + 1024 and
        seen == set(selected) and reader.bytes == checkpoint['bytes'] and reader.digest.hexdigest() == checkpoint['sha256'],
        'actual complete compressed archive, tar EOF or manifest differs')
    require(tracking['members'] == set(evidence.TRACKING_MEMBERS), 'actual archive lacks one complete tracking journal')
    metadata = data.get('tracking/checkpoint.json')
    require(type(metadata) is dict and metadata.get('schema') == 'client442_interaction_checkpoint_v1' and
        strict_equal(metadata.get('files'), [row for row in checkpoint['file_manifest'] if not row['path'].startswith('tracking/')]),
        'external complete manifest must preserve actual archived metadata files and append only actual tracking rows')
    tracking['archived_metadata'] = metadata
    tracking['compressed_md5'] = reader.md5.hexdigest()
    return data, digests, tracking, reader.bytes


def review(directory, output):
    from urllib.request import urlopen
    from .review_hunter_learn_checkpoint import dvc_object, remote_request, remote_options
    from .bag_swap_sources import private_json, bound
    directory, output = Path(directory), Path(output)
    require('..' not in directory.parts and '..' not in output.parts and
        directory.is_absolute() and directory.parent == evidence.ROOT / 'evidence' and
        output.is_absolute() and output.is_relative_to(evidence.ROOT / 'evidence') and not output.is_relative_to(directory) and
        not output.exists() and not any(p.is_symlink() for p in (directory, output, *directory.parents, *output.parents)),
        'new ordinary private remote review outside the immutable batch required')
    checkpoint_path = directory / 'checkpoint_receipt.json'
    checkpoint_source = bound(checkpoint_path)
    checkpoint = private_json(checkpoint_path, False)
    require(checkpoint.get('cloud_verified') is True, 'actual excluded checkpoint must be synchronized')
    pointer, oid = dvc_object(REPO, checkpoint)
    pointer_path = REPO / pointer
    require(pointer_path.stat().st_size <= 1024 * 1024 and
        not any(p.is_symlink() for p in pointer_path.parents), 'ordinary bounded actual DVC pointer required')
    pointer_raw = pointer_path.read_bytes()
    with urlopen(remote_request(remote_options(REPO), oid), timeout=60) as stream:
        data, digests, tracking, count = inspect_archive(stream, checkpoint, str(directory.relative_to(evidence.ROOT)) + '/')
    require(tracking['compressed_md5'] == oid, 'actual complete compressed DVC object MD5 differs')
    result = evidence.proof(data, digests, tracking)
    require(bound(checkpoint_path) == checkpoint_source and dvc_object(REPO, checkpoint) == (pointer, oid) and
        pointer_path.read_bytes() == pointer_raw, 'actual checkpoint or DVC pointer changed during remote verification')
    report = {'schema': 'client442_bag_swap_failed_remote_review_v1', 'reviewed_at': time.time(),
        'checkpoint_source': checkpoint_source,
        'pointer': pointer, 'pointer_sha256': hashlib.sha256(pointer_raw).hexdigest(), 'object_md5': oid,
        'archive_sha256': checkpoint['sha256'], 'bytes': count, 'actual_remote_verified': True,
        'complete_manifest_verified': True,
        'complete_json_png_jsonl_verified': True, 'local_archive_created': False, 'qualification_added': False,
        'operations_admitted': 0, 'json_members': len(data), 'png_members': sum(p.endswith('.png') for p in digests),
        'journal_members': sum(p.endswith('.jsonl') for p in digests), 'proof': result}
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    encoded = (json.dumps(report, indent=2, allow_nan=False) + '\n').encode()
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps(report, allow_nan=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.directory, args.output)


if __name__ == '__main__':
    main()
