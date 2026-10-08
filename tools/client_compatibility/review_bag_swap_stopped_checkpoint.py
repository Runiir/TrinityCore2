"""Stream and prove the excluded UI173 checkpoint without retaining its archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from . import lab_runtime as lab
from .bag_swap_sources import bound, private_json
from .item_actionbar_contract import require
from . import bag_swap_stopped_evidence as evidence


def review(directory, output):
    from urllib.request import urlopen
    from .review_hunter_learn_checkpoint import dvc_object, remote_options, remote_request
    from .bag_swap_source_index import inspect_archive
    directory, output = Path(directory), Path(output)
    require(directory == lab.ROOT / evidence.BATCH.rstrip('/') and directory.is_dir() and
        output.is_absolute() and output.is_relative_to(lab.ROOT / 'evidence') and not output.is_relative_to(directory) and
        not output.exists() and '..' not in output.parts and
        not any(p.is_symlink() for p in (directory, output, *directory.parents, *output.parents)),
        'one new ordinary remote review outside the actual closed UI173 batch required')
    checkpoint_path = directory / 'checkpoint_receipt.json'
    checkpoint_ref = bound(checkpoint_path)
    checkpoint = private_json(checkpoint_path, False)
    require(checkpoint.get('cloud_verified') is True, 'the actual stopped checkpoint must be synchronized')
    pointer, oid = dvc_object(lab.REPO, checkpoint)
    pointer_path = lab.REPO / pointer
    require(pointer_path.stat().st_size <= 1024 * 1024 and
        not any(p.is_symlink() for p in (pointer_path, *pointer_path.parents)), 'ordinary bounded actual pointer required')
    pointer_raw = pointer_path.read_bytes()
    tracking = None
    try:
        with urlopen(remote_request(remote_options(lab.REPO), oid), timeout=60) as stream:
            data, digests, tracking, count = inspect_archive(stream, checkpoint, evidence.BATCH)
        require(tracking.get('compressed_md5') == oid, 'the complete actual compressed DVC object differs')
        computed = evidence.proof(data, digests, tracking)
    finally:
        if tracking is not None and tracking.get('_spool') is not None:
            tracking['_spool'].cleanup()
    require(bound(checkpoint_path) == checkpoint_ref and dvc_object(lab.REPO, checkpoint) == (pointer, oid) and
        pointer_path.read_bytes() == pointer_raw, 'actual checkpoint or pointer changed during streaming proof')
    report = {'schema': 'client442_bag_swap_stopped_remote_review_v1', 'reviewed_at': time.time(),
        'checkpoint_source': checkpoint_ref, 'pointer': pointer,
        'pointer_sha256': hashlib.sha256(pointer_raw).hexdigest(), 'object_md5': oid,
        'archive_sha256': checkpoint['sha256'], 'bytes': count, 'actual_remote_verified': True,
        'complete_manifest_verified': True, 'complete_json_png_jsonl_verified': True,
        'opaque_legacy_authorities_verified': True, 'local_archive_created': False,
        'qualification_added': False, 'operations_admitted': 0, 'excluded_failed_entry': True,
        'json_members': sum(name.endswith('.json') for name in digests),
        'png_members': sum(name.endswith('.png') for name in digests),
        'journal_members': sum(name.endswith('.jsonl') for name in digests), 'proof': computed}
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = (json.dumps(report, indent=2, allow_nan=False) + '\n').encode()
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps({'output': str(output), 'sha256': bound(output)['sha256'],
        'qualified_fixture_operations': 453, 'operations_admitted': 0}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.directory, args.output)


if __name__ == '__main__':
    main()
