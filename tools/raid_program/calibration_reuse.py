"""Index qualified class calibrations independently of encounter progress."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

CATALOG = 'experiments/configs/class_calibration_catalog_v1.json'
UNCHANGED = {'gear', 'talents_glyphs', 'professions_race', 'pets', 'consumables_buffs',
             'class_policy', 'class_mechanics', 'shared_runtime', 'scoring_contract', 'reference'}


def verify_compatibility(root, proof_ref, *, packet_ref, source_build, target_build,
                         validation_identity, actor_id, spec):
    """A different build needs a real independent review of its exact delta.

    This is a reviewed compatibility statement, not automatic dependency analysis.
    Unknown or relevant behavior/setup changes require affected-class calibration.
    """
    from tools.raid_program.development_graph import file_ref, read
    from tools.raid_program.review_execution import verify_review
    proof = read(file_ref(root, proof_ref))
    statement_ref = proof['statement']
    statement = read(file_ref(root, statement_ref))
    expected = {'calibration_packet': packet_ref, 'source_build': source_build,
                'target_build': target_build, 'validation_identity': validation_identity,
                'actor_id': actor_id, 'spec': spec}
    if any(statement.get(k) != v for k, v in expected.items()):
        raise ValueError('calibration reuse identity mismatch')
    unchanged = statement.get('unchanged', {})
    if set(unchanged) != UNCHANGED or any(v is not True for v in unchanged.values()):
        raise ValueError('recalibrate affected class: relevant inputs changed or unknown')
    if not statement.get('rationale'):
        raise ValueError('calibration reuse requires a compatibility rationale')
    if not validation_identity:
        raise ValueError('calibration reuse needs current encounter/setup identity')
    base, target = source_build['source_commit'], target_build['source_commit']
    subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', base, target],
                   check=True, capture_output=True)
    changed = sorted(filter(None, subprocess.check_output(
        ['git', '-C', str(root), 'diff', '--name-only', '--no-renames', '-z', base, target]
    ).decode().split('\0')))
    if statement.get('changed_paths') != changed:
        raise ValueError('calibration reuse omits source changes')
    if not statement.get('current_setup_evidence'):
        raise ValueError('calibration reuse needs current provisioning/setup evidence')
    for ref in statement['current_setup_evidence']:
        file_ref(root, ref)
    review = read(file_ref(root, proof['review']))
    if review.get('verdict') != 'approved':
        raise ValueError('calibration reuse requires independent approval')
    author = statement.get('author_session_id')
    if not author:
        raise ValueError('calibration reuse author session missing')
    hashes = verify_review(root, review, implementer_session_id=author)
    if hashes.get(statement_ref['path']) != statement_ref['sha256']:
        raise ValueError('independent review does not cover compatibility statement')
    return {'status': 'reviewed_compatible', 'calibration_packet': packet_ref,
            'source_build': source_build, 'target_build': target_build}


def candidates(root: Path, spec: str, actor_id: str | None = None):
    from tools.raid_program.development_graph import file_ref, read
    path = root / CATALOG
    catalog = read(path) if path.exists() else {'entries': []}
    rows = []
    for row in catalog['entries']:
        if row['spec'] != spec or (actor_id is not None and row['actor_id'] != actor_id):
            continue
        file_ref(root, row['packet'])
        rows.append(row)
    return {'spec': spec, 'candidates': rows,
            'instruction': 'Verify the retained packet and current compatibility before reuse. '
                           'A catalog entry alone is not current acceptance. Missing local evidence '
                           'requires DVC hydration, not a replacement experiment.'}


def register(root: Path, packet_path: str, spec: str, actor_id: str):
    from tools.raid_program.development_graph import snapshot
    from tools.raid_program.evidence_task import confined
    from tools.raid_program.dps_gate import verify_packet
    path = confined(root, packet_path).relative_to(root).as_posix()
    ref = {'path': path, 'sha256': snapshot(root, [path])[path]}
    result = verify_packet(root, ref, actor_id=actor_id, spec=spec)
    catalog_path = root / CATALOG
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {
        'schema': 'class_calibration_catalog_v1', 'entries': []}
    row = {'spec': spec, 'actor_id': actor_id, 'packet': ref}
    if row not in catalog['entries']:
        catalog['entries'].append(row)
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(json.dumps(catalog, indent=2) + '\n')
    return {'registered': row, 'gate': result, 'encounter_accepted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('list', 'register'):
        p = sub.add_parser(name)
        p.add_argument('--spec', required=True)
        p.add_argument('--actor-id', required=name == 'register')
        if name == 'register':
            p.add_argument('--packet', required=True)
    args = parser.parse_args()
    result = (register(args.root, args.packet, args.spec, args.actor_id)
              if args.command == 'register' else candidates(args.root, args.spec, args.actor_id))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
