"""Review local Revive evidence without remote access or ledger admission."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from . import lab_runtime as lab
from .hunter_revive_evidence import collect, proof, tracking_state
from .observation.journal import entries
from .review_native_feedback_checkpoint import require


def review(directory, output):
    directory, output = directory.resolve(), output.resolve()
    require(directory.parent == lab.ROOT / 'evidence' and output.is_relative_to(lab.ROOT / 'evidence') and
        not output.is_relative_to(directory) and not output.exists(),
        'requires a new local review outside the immutable Revive batch')
    data, digests = {}, {}
    for path in sorted(directory.rglob('*')):
        if path.suffix not in ('.json', '.png'): continue
        require(path.is_file() and not path.is_symlink(), 'invalid local Revive member')
        key = str(path.relative_to(directory)); body = path.read_bytes()
        digests[key] = hashlib.sha256(body).hexdigest()
        if path.suffix == '.json': data[key] = json.loads(body)
    tracking = tracking_state()
    collect('tracking/events.jsonl', entries(lab.ROOT / 'logs/modern_world.jsonl'), data, tracking)
    collect('tracking/packets.jsonl', entries(lab.ROOT / 'evidence/world_packets.jsonl'), data, tracking)
    outcome = proof(data, digests, tracking)
    # A semantic local pass cannot authorize the operation ledger. The remote
    # verifier recomputes proof from the actual streamed compressed object.
    result = {'schema': 'client442_revive_local_review_v1', 'reviewed_at': time.time(),
        'directory': str(directory), 'actual_remote_verified': False, 'qualification_added': False,
        'proof': outcome, 'member_digests': digests}
    lab.private_write(output, json.dumps(result, indent=2) + '\n')
    print(json.dumps({'local_proof_verified': True, 'actual_remote_verified': False,
        'qualification_added': False, 'operation': outcome['operation']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.directory, args.output)
