"""Stream the configured DVC remote and review a whole ordinary1462 lifecycle.

This standalone entry point is for the coordinator after checkpoint publication.
It never loads a local archive, creates one, operates a client, or admits ledger
qualification. Only the report is written to a new private evidence path.
"""
import argparse
import configparser
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tarfile
import time
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from . import lab_runtime as lab
from . import hunter_learn_evidence as evidence
from .hunter_learn_sources import require, private_json


class DigestReader:
    """Hash every compressed byte while tarfile consumes a forward-only stream."""
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes = 0
        self.progress = 0

    def read(self, size=-1):
        data = self.stream.read(1024 * 1024 if size < 0 else size)
        self.digest.update(data)
        self.bytes += len(data)
        if self.bytes - self.progress >= 128 * 1024 * 1024:
            self.progress = self.bytes
            print(json.dumps({'bytes_read': self.bytes}), flush=True)
        return data


def manifest(checkpoint, prefix):
    rows = checkpoint.get('file_manifest', [])
    require(isinstance(rows, list) and rows, 'checkpoint manifest is empty')
    require(len({r.get('path') for r in rows}) == len(rows), 'checkpoint manifest contains duplicate paths')
    selected = {}
    for row in rows:
        path = row.get('path', '')
        require(isinstance(path, str) and not Path(path).is_absolute() and '..' not in Path(path).parts and
            type(row.get('bytes')) is int and row['bytes'] >= 0 and
            re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')), 'checkpoint manifest row differs')
        if path.startswith(prefix) and Path(path).suffix in ('.json', '.png'):
            selected[path] = row
    require(selected and any(p.endswith('.png') for p in selected) and
        any(p.endswith('/episode.json') for p in selected), 'complete JSON and PNG evidence manifest is required')
    require(type(checkpoint.get('bytes')) is int and checkpoint['bytes'] > 0 and
        re.fullmatch('[0-9a-f]{64}', checkpoint.get('sha256', '')), 'compressed checkpoint digest or size differs')
    return selected


def inspect_archive(raw, checkpoint, prefix):
    """Verify complete manifest bytes/hashes and parse bounded actual journals."""
    selected = manifest(checkpoint, prefix)
    data, digests, seen = {}, {}, set()
    tracking = evidence.tracking_state()
    tracking['digests'] = digests
    tracking['manifest'] = selected
    reader = DigestReader(raw)
    with tarfile.open(fileobj=reader, mode='r|gz') as archive:
        for member in archive:
            if member.name.startswith(prefix) and Path(member.name).suffix in ('.json', '.png'):
                require(member.name in selected, 'actual batch contains JSON/PNG absent from the complete checkpoint manifest')
            if member.name in evidence.TRACKING_MEMBERS:
                require(member.isfile() and member.name not in tracking['members'],
                    'actual tracking journal is duplicate or not a file')
                with archive.extractfile(member) as handle:
                    evidence.collect(member.name, (json.loads(line) for line in handle), data, tracking)
            if member.name not in selected:
                continue
            row = selected[member.name]
            require(member.isfile() and member.name not in seen and member.size == row['bytes'],
                'selected archive member type, multiplicity or size differs')
            digest, total, chunks = hashlib.sha256(), 0, []
            first = b''
            with archive.extractfile(member) as handle:
                while chunk := handle.read(1024 * 1024):
                    if not first:
                        first = chunk[:8]
                    digest.update(chunk)
                    total += len(chunk)
                    if member.name.endswith('.json'):
                        require(total <= 64 * 1024 * 1024, 'private JSON member exceeds its review bound')
                        chunks.append(chunk)
            require(total == row['bytes'] and digest.hexdigest() == row['sha256'],
                'selected JSON/PNG complete bytes or SHA256 differs')
            if member.name.endswith('.json'):
                data[member.name] = json.loads(b''.join(chunks))
            else:
                require(first == b'\x89PNG\r\n\x1a\n', 'manifest PNG is not a PNG image')
            digests[member.name] = row['sha256']
            seen.add(member.name)
    while reader.read(1024 * 1024):
        pass
    require(seen == set(selected) and reader.bytes == checkpoint['bytes'] and
        reader.digest.hexdigest() == checkpoint['sha256'],
        'actual remote compressed bytes, SHA256 or complete JSON/PNG manifest differs')
    require(tracking['members'] == set(evidence.TRACKING_MEMBERS), 'actual archive lacks one of the two packet journals')
    return data, digests, tracking, reader.bytes


def dvc_object(repo, checkpoint):
    """Read only the configured DVC pointer; no DVC SDK or protocol imports."""
    archive = checkpoint.get('file', '')
    path = Path(archive)
    require(not path.is_absolute() and '..' not in path.parts and
        path.parts[:2] == ('artifacts', 'client_harness') and path.suffixes[-2:] == ['.tar', '.gz'],
        'checkpoint is not a repository client-harness archive')
    pointer = repo / (archive + '.dvc')
    require(pointer.is_file() and not pointer.is_symlink(), 'published DVC pointer is absent')
    text = pointer.read_text()
    hashes = re.findall(r'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', text, re.MULTILINE)
    sizes = re.findall(r'^\s*size:\s*([0-9]+)\s*$', text, re.MULTILINE)
    paths = re.findall(r'^\s*path:\s*(\S+)\s*$', text, re.MULTILINE)
    require(len(hashes) == len(sizes) == len(paths) == 1 and int(sizes[0]) == checkpoint['bytes'] and
        paths[0] == path.name and re.search(r'^\s*hash:\s*md5\s*$', text, re.MULTILINE),
        'DVC pointer object identity differs from checkpoint')
    return archive + '.dvc', hashes[0]


def remote_options(repo):
    parser = configparser.RawConfigParser()
    parser.read([repo / '.dvc/config', repo / '.dvc/config.local'])
    require(parser.has_option('core', 'remote'), 'DVC root has no selected remote')
    name = parser.get('core', 'remote').strip('"\'')
    matches = [section for section in parser.sections() if section.strip("'") == 'remote "' + name + '"']
    require(len(matches) == 1, 'DVC selected remote configuration is ambiguous')
    options = dict(parser.items(matches[0]))
    require('url' in options, 'DVC selected remote URL is absent')
    return options


def aws_credentials(options):
    """Use the same explicit/environment/profile sources without logging keys."""
    key = options.get('access_key_id') or os.environ.get('AWS_ACCESS_KEY_ID')
    secret = options.get('secret_access_key') or os.environ.get('AWS_SECRET_ACCESS_KEY')
    token = options.get('session_token') or os.environ.get('AWS_SESSION_TOKEN')
    if not key and not secret:
        parser = configparser.RawConfigParser()
        parser.read(Path(os.environ.get('AWS_SHARED_CREDENTIALS_FILE', str(Path.home() / '.aws/credentials'))))
        profile = options.get('profile') or os.environ.get('AWS_PROFILE', 'default')
        if parser.has_section(profile):
            key = parser.get(profile, 'aws_access_key_id', fallback=None)
            secret = parser.get(profile, 'aws_secret_access_key', fallback=None)
            token = parser.get(profile, 'aws_session_token', fallback=None)
    require(bool(key) == bool(secret), 'configured DVC remote credentials are incomplete')
    return key, secret, token


def remote_request(options, oid, now=None):
    """Create a direct configured HTTP request, signing S3 when keys exist."""
    remote = urlsplit(options['url'])
    object_path = 'files/md5/' + oid[:2] + '/' + oid[2:]
    if remote.scheme in ('http', 'https'):
        require(not remote.query and not remote.fragment and not remote.username and not remote.password,
            'DVC HTTP remote must be an explicit object root')
        return Request(options['url'].rstrip('/') + '/' + object_path)
    require(remote.scheme == 's3' and remote.netloc and not remote.query and not remote.fragment,
        'standalone reviewer supports the configured S3 or HTTP DVC object root')
    endpoint = options.get('endpointurl', 'https://s3.' + options.get('region', 'us-east-1') + '.amazonaws.com').rstrip('/')
    parsed = urlsplit(endpoint)
    require(parsed.scheme in ('http', 'https') and parsed.netloc and not parsed.query and not parsed.fragment and
        not parsed.username and not parsed.password, 'DVC S3 endpoint is not an explicit HTTP endpoint')
    suffix = '/' + remote.netloc + remote.path.rstrip('/') + '/' + object_path
    url = endpoint + quote(suffix, safe='/~')
    key, secret, token = aws_credentials(options)
    if not key:
        return Request(url)
    stamp = (now or datetime.now(timezone.utc)).strftime('%Y%m%dT%H%M%SZ')
    day, region = stamp[:8], options.get('region', 'us-east-1')
    payload = hashlib.sha256(b'').hexdigest()
    headers = {'host': parsed.netloc, 'x-amz-content-sha256': payload, 'x-amz-date': stamp}
    if token:
        headers['x-amz-security-token'] = token
    names = ';'.join(sorted(headers))
    canonical_headers = ''.join(k + ':' + headers[k].strip() + '\n' for k in sorted(headers))
    canonical = 'GET\n' + urlsplit(url).path + '\n\n' + canonical_headers + '\n' + names + '\n' + payload
    scope = day + '/' + region + '/s3/aws4_request'
    signing = 'AWS4-HMAC-SHA256\n' + stamp + '\n' + scope + '\n' + hashlib.sha256(canonical.encode()).hexdigest()
    def sign(value, text): return hmac.new(value, text.encode(), hashlib.sha256).digest()
    signing_key = sign(sign(sign(sign(('AWS4' + secret).encode(), day), region), 's3'), 'aws4_request')
    signature = hmac.new(signing_key, signing.encode(), hashlib.sha256).hexdigest()
    headers['Authorization'] = 'AWS4-HMAC-SHA256 Credential=' + key + '/' + scope + ', SignedHeaders=' + names + ', Signature=' + signature
    return Request(url, headers=headers)


def review(directory, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    require(directory.parent == lab.ROOT / 'evidence' and output.is_relative_to(lab.ROOT / 'evidence') and
        not output.is_relative_to(directory) and not output.exists(), 'requires a new review outside the immutable batch')
    checkpoint = private_json(directory / 'checkpoint_receipt.json', False)
    require(checkpoint.get('cloud_verified') is True, 'checkpoint has not been published and synchronized')
    pointer, oid = dvc_object(lab.REPO, checkpoint)
    request = remote_request(remote_options(lab.REPO), oid)
    prefix = str(directory.relative_to(lab.ROOT)) + '/'
    with urlopen(request, timeout=60) as raw:
        data, digests, tracking, count = inspect_archive(raw, checkpoint, prefix)
    result = evidence.proof(data, digests, tracking)
    report = {'schema': 'client442_hunter_learn_remote_review_v1', 'reviewed_at': time.time(),
        'pointer': pointer, 'archive_sha256': checkpoint['sha256'], 'bytes': count,
        'actual_remote_verified': True, 'complete_json_png_verified': True,
        'json_members': sum(p.endswith('.json') for p in digests),
        'png_members': sum(p.endswith('.png') for p in digests),
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
