"""Observe a fresh parked selection while retaining the completed runtime code.

The source-linked proof code may change after gameplay has ended. This command
only fingerprints committed source bytes, checks the six offline characters,
and captures an owned screenshot for a later fresh human selection review.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from . import lab_runtime as lab
from .item_actionbar_contract import require, finite
from .item_actionbar_sources import bound, closed, linked, reference
from .item_actionbar_preservation import owned_snapshot

PHASE = 'item_actionbar_parked_selection_captured'
TRANSITION_SCHEMA = 'client442_item_actionbar_pure_proof_code_transition_v1'
FAILURE = 'RuntimeError: actual observed item icon and empty action destination review differs'
ROLES = frozenset(('preparation', 'park', 'after_precision', 'operation', 'entry_screen', 'failed_close'))
SOURCE_FIELDS = {'preparation': 'preparation_source', 'park': 'park_source',
    'after_precision': 'precision_source', 'operation': 'operation_source',
    'entry_screen': 'entry_screen_source', 'failed_close': 'failed_close_source'}
PROOF_FILES = (
    'tools/client_compatibility/interaction_item_actionbar_parked_selection_capture.py',
    'tools/client_compatibility/world/tests/test_item_actionbar_parked_selection_capture.py',
    'tools/client_compatibility/interaction_item_actionbar_continuation.py',
    'tools/client_compatibility/world/tests/test_item_actionbar_continuation.py',
    'tools/client_compatibility/item_actionbar_evidence.py',
    'tools/client_compatibility/world/tests/test_item_actionbar_evidence.py')
NEW_PROOF_FILES = frozenset(PROOF_FILES[:2])
HEX40, HEX64 = '[0-9a-f]{40}', '[0-9a-f]{64}'


def game_identity(monitor, original_frame):
    original = original_frame.get('monitor', {}).get('input_isolation', {}) if type(original_frame) is dict else {}
    current = monitor.get('input_isolation', {}) if type(monitor) is dict else {}
    require(type(original.get('game_pid')) is int and original['game_pid'] > 0 and
        type(original.get('display')) is str and re.fullmatch(':[0-9]+(?:\\.[0-9]+)?', original['display']) and
        type(original.get('window_id')) is int and original['window_id'] > 0 and
        original.get('actor') == current.get('actor') == 'scout' and
        original.get('host_activation_sent') is current.get('host_activation_sent') is False and
        all(type(current.get(k)) is type(original[k]) and current[k] == original[k]
            for k in ('game_pid', 'display', 'window_id')),
        'fresh parked observer must retain the original game PID, private display and window')


def frame_identity(image, runtime, original_frame=None):
    require(type(image) is dict and type(image.get('file')) is str and Path(image['file']).name == image['file'] and
        type(image.get('sha256')) is str and re.fullmatch(HEX64, image['sha256']), 'fresh owned parked frame identity differs')
    monitor = image.get('monitor', {})
    isolation = monitor.get('input_isolation', {})
    require(monitor.get('second_monitor_verified') is True and monitor.get('monitor', {}).get('name') == 'HDMI-1' and
        monitor.get('pid') == runtime['client']['pid'] and isolation.get('actor') == 'scout' and
        isolation.get('host_activation_sent') is False, 'fresh parked capture must own the original scout on HDMI-1')
    if original_frame is not None:
        game_identity(monitor, original_frame)


def source_bytes(raw_hex, digest):
    require(type(raw_hex) is str and 0 < len(raw_hex) <= 800_000 and len(raw_hex) % 2 == 0 and
        re.fullmatch('[0-9a-f]+', raw_hex) and type(digest) is str and re.fullmatch(HEX64, digest),
        'bounded exact proof source bytes are required')
    raw = bytes.fromhex(raw_hex)
    require(hashlib.sha256(raw).hexdigest() == digest, 'proof source raw bytes differ from their actual SHA256')
    return raw


def validate_transition(transition, park, precision, screen, refs):
    require(type(refs) is dict and set(refs) == ROLES, 'complete immutable parked selection source roles are required')
    for ref in refs.values():
        reference(ref)
    fields = {'schema', 'runtime_code_commit', 'code_commit', 'read_only', 'gameplay_input_replayed',
        'source_changes', 'changed_paths', 'unchanged_runtime_sources', *SOURCE_FIELDS.values()}
    runtime_code, proof_code = park.get('code_commit'), transition.get('code_commit') if type(transition) is dict else None
    require(type(transition) is dict and set(transition) == fields and transition.get('schema') == TRANSITION_SCHEMA and
        type(runtime_code) is str and re.fullmatch(HEX40, runtime_code) and type(proof_code) is str and
        re.fullmatch(HEX40, proof_code) and proof_code != runtime_code and
        precision.get('code_commit') == screen.get('code_commit') == transition.get('runtime_code_commit') == runtime_code and
        transition.get('read_only') is True and transition.get('gameplay_input_replayed') is False and
        all(transition.get(field) == refs[role] for role, field in SOURCE_FIELDS.items()),
        'only the exact truthful C runtime to D pure proof transition is permitted')
    rows = transition.get('source_changes')
    paths = [str(lab.REPO / name) for name in PROOF_FILES]
    require(type(rows) is list and len(rows) == len(paths) and all(type(row) is dict for row in rows) and
        [row.get('path') for row in rows] == paths,
        'all six proof-only source files must retain their actual C and D bytes')
    total = 0
    changed = []
    for row, relative in zip(rows, PROOF_FILES):
        require(type(row) is dict and set(row) == {'path', 'before_sha256', 'before_raw_hex', 'sha256', 'raw_hex'},
            'exact proof-only before and after source record fields are required')
        total += len(source_bytes(row['raw_hex'], row['sha256']))
        if relative in NEW_PROOF_FILES:
            require(row['before_sha256'] is None and row['before_raw_hex'] is None,
                'new read-only capture files cannot invent runtime C source bytes')
        else:
            total += len(source_bytes(row['before_raw_hex'], row['before_sha256']))
        require(total <= 2_000_000, 'pure proof code package exceeds its bounded raw size')
        if row['before_sha256'] != row['sha256']:
            changed.append(relative)
    require(transition.get('changed_paths') == sorted(changed) and
        NEW_PROOF_FILES <= set(changed) and 'tools/client_compatibility/item_actionbar_evidence.py' in changed,
        'actual C to D changes must be confined to this exact proof-only package')
    evidence_path = str(lab.REPO / 'tools/client_compatibility/item_actionbar_evidence.py')
    runtime_sources = screen.get('committed_sources')
    require(type(runtime_sources) is list and runtime_sources and all(type(row) is dict for row in runtime_sources) and
        transition.get('unchanged_runtime_sources') == [row for row in runtime_sources if row.get('path') != evidence_path],
        'every frozen C runtime source must remain unchanged outside the explicit pure reader')
    old_proof = next((row for row in screen.get('code_source_bytes', []) if row.get('path') == evidence_path), None)
    source = next(row for row in rows if row['path'] == evidence_path)
    require(old_proof is not None and {'path': source['path'], 'sha256': source['before_sha256']} in runtime_sources and
        source['before_sha256'] == old_proof.get('sha256') and source['before_raw_hex'] == old_proof.get('raw_hex'),
        'pure reader C bytes must be the actual frozen bytes retained by the runtime capture')
    return deepcopy(transition)


def validate_capture(value, ready, park, precision, operation, screen, failed_close, refs):
    from . import item_actionbar_evidence as evidence
    evidence.accepted(value, PHASE)
    evidence.accepted(ready, 'item_actionbar_scout_ready')
    evidence.accepted(park, 'item_actionbar_parked')
    evidence.accepted(operation, 'item_actionbar_restored')
    evidence.accepted(screen, 'item_actionbar_entry_screen_captured')
    snapshot = park.get('all_offline_snapshot')
    owned_snapshot(snapshot)
    evidence.precision(precision, refs['park'], snapshot)
    transition = validate_transition(value.get('proof_code_transition'), park, precision, screen, refs)
    require(value.get('source') == value.get('park_source') == refs['park'] and
        all(value.get(field) == refs[role] for role, field in SOURCE_FIELDS.items()) and
        value.get('code_commit') == transition['code_commit'] and operation.get('code_commit') == park['code_commit'] and
        park.get('source') == refs['operation'] and operation.get('entry_screen_source') == refs['entry_screen'] and
        park.get('preparation_source') == operation.get('preparation_source') == refs['preparation'] and
        value.get('actor') == ready.get('actor') == park.get('actor') == operation.get('actor') == screen.get('actor') and
        value.get('runtime') == ready.get('runtime') == park.get('runtime') == operation.get('runtime') == screen.get('runtime') and
        value.get('native_session') == ready.get('native_session') == park.get('native_session') and
        value.get('all_offline_snapshot') == snapshot and value.get('controller') == 'code' and
        value.get('model') is None and value.get('revision') is None and value.get('cases') == value.get('cleanup') == [] and
        value.get('custom_script_permission') == 'blocked_by_user' and value.get('softTargetInteract') == evidence.SCRIPT_BOUNDARY and
        value.get('observer_only') is True and value.get('read_only') is True and
        value.get('requires_fresh_selection_review') is True and
        all(value.get(k) is False for k in ('input_sent', 'mutation_sent', 'qualification_added', 'stop_attempted')),
        'fresh parked capture must preserve the completed original runtime and all six offline characters')
    require(type(failed_close) is dict and failed_close.get('completed') is False and failed_close.get('failure') == FAILURE and
        failed_close.get('phase') is None and failed_close.get('code_commit') == park['code_commit'] and
        failed_close.get('actor') == ready['actor'] and failed_close.get('runtime') == ready['runtime'] and
        failed_close.get('controller') == 'code' and failed_close.get('model') is None and failed_close.get('revision') is None and
        failed_close.get('cases') == [] and all(failed_close.get(k) is False for k in
            ('input_sent', 'mutation_sent', 'qualification_added')) and failed_close.get('stop_attempted') is not True and
        'stop_finished_at' not in failed_close and 'game_before' not in failed_close and
        finite(failed_close.get('started_at')) and finite(failed_close.get('finished_at')) and
        precision['finished_at'] <= failed_close['started_at'] < failed_close['finished_at'] <= value['started_at'],
        'only the immutable C pure-proof failure before any stop may precede this fresh parked capture')
    frame_identity(value.get('frame'), value['runtime'], park.get('frame'))
    return transition


def proof_transition(t, refs, park, precision, screen):
    runtime_code = park['code_commit']
    proof_code = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip()
    require(t.receipt.get('code_commit') == proof_code and proof_code != runtime_code,
        'fresh parked capture must retain the truthful current proof code commit')
    changed = subprocess.check_output(['git', 'diff', '--name-only', runtime_code, proof_code], cwd=lab.REPO, text=True).splitlines()
    require(changed and set(changed) <= set(PROOF_FILES), 'pure-proof repair cannot alter a runtime implementation or unrelated source')
    rows = []
    for relative in PROOF_FILES:
        path = lab.REPO / relative
        require(path.is_file() and all(not p.is_symlink() for p in (path, *path.parents)), 'proof source must be an ordinary committed file')
        after = subprocess.check_output(['git', 'show', proof_code + ':' + relative], cwd=lab.REPO)
        require(path.read_bytes() == after, 'pure-proof working source differs from its actual committed D bytes')
        before = None if relative in NEW_PROOF_FILES else subprocess.check_output(['git', 'show', runtime_code + ':' + relative], cwd=lab.REPO)
        if relative in NEW_PROOF_FILES:
            exists = subprocess.run(['git', 'cat-file', '-e', runtime_code + ':' + relative], cwd=lab.REPO,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            require(exists.returncode != 0, 'new proof capture file already existed in the declared runtime C commit')
        rows.append({'path': str(path), 'before_sha256': None if before is None else hashlib.sha256(before).hexdigest(),
            'before_raw_hex': None if before is None else before.hex(), 'sha256': hashlib.sha256(after).hexdigest(), 'raw_hex': after.hex()})
    evidence_path = str(lab.REPO / 'tools/client_compatibility/item_actionbar_evidence.py')
    unchanged = [row for row in screen['committed_sources'] if row['path'] != evidence_path]
    for row in unchanged:
        relative = str(Path(row['path']).relative_to(lab.REPO))
        c_raw = subprocess.check_output(['git', 'show', runtime_code + ':' + relative], cwd=lab.REPO)
        d_raw = subprocess.check_output(['git', 'show', proof_code + ':' + relative], cwd=lab.REPO)
        require(c_raw == d_raw == Path(row['path']).read_bytes() and hashlib.sha256(c_raw).hexdigest() == row['sha256'],
            'completed C runtime source bytes changed outside the pure reader')
    result = {'schema': TRANSITION_SCHEMA, 'runtime_code_commit': runtime_code, 'code_commit': proof_code,
        'read_only': True, 'gameplay_input_replayed': False, 'source_changes': rows,
        'changed_paths': sorted(changed), 'unchanged_runtime_sources': unchanged,
        **{field: refs[role] for role, field in SOURCE_FIELDS.items()}}
    return validate_transition(result, park, precision, screen, refs)


def sources(preparation, park_path, precision_path, failed_close_path):
    ready, park, precision = [closed(path) for path in (preparation, park_path, precision_path)]
    failed = linked(bound(failed_close_path), successful=False)
    operation_ref = park.get('source'); reference(operation_ref)
    require(bound(Path(operation_ref['path'])) == operation_ref, 'completed item restoration source bytes changed')
    operation = closed(Path(operation_ref['path']))
    screen_ref = operation.get('entry_screen_source'); reference(screen_ref)
    require(bound(Path(screen_ref['path'])) == screen_ref, 'completed C entry screen bytes changed')
    screen = closed(Path(screen_ref['path']))
    refs = {'preparation': bound(preparation), 'park': bound(park_path), 'after_precision': bound(precision_path),
        'failed_close': bound(failed_close_path), 'operation': operation_ref, 'entry_screen': screen_ref}
    return ready, park, precision, operation, screen, failed, refs


def capture(t, preparation, park_path, precision_path, failed_close_path):
    from . import interaction_item_actionbar_continuation as continuation
    ready, park, precision, operation, screen, failed, refs = sources(preparation, park_path, precision_path, failed_close_path)
    require(t.fixture == ready['actor'] == continuation.registration() and
        t.receipt['runtime'] == ready['runtime'] == continuation.runtime() and
        continuation.snapshot() == park['all_offline_snapshot'], 'fresh parked observer runtime, original selection or offline resources differ')
    game_identity(continuation.focus(), park.get('frame'))
    transition = proof_transition(t, refs, park, precision, screen)
    t.receipt.update(source=refs['park'], **{field: refs[role] for role, field in SOURCE_FIELDS.items()},
        native_session=ready['native_session'], all_offline_snapshot=deepcopy(park['all_offline_snapshot']),
        proof_code_transition=transition, observer_only=True, read_only=True, requires_fresh_selection_review=True,
        input_sent=False, mutation_sent=False, qualification_added=False, stop_attempted=False,
        phase='item_actionbar_parked_selection_capture_started')
    t.persist()
    frame = continuation.shot(t.out / 'parked_selection.png')
    t.receipt['frame'] = frame
    t.persist()
    frame_identity(frame, t.receipt['runtime'], park.get('frame'))
    path = t.out / frame['file']
    require(path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == frame['sha256'],
        'fresh parked screenshot must belong to its actual current output directory')
    require(continuation.snapshot() == park['all_offline_snapshot'] and continuation.runtime() == t.receipt['runtime'] and
        continuation.registration() == t.fixture and proof_transition(t, refs, park, precision, screen) == transition and
        all(bound(Path(ref['path'])) == ref for ref in refs.values()),
        'fresh read-only parked observation changed an immutable source, lifetime or offline resource')
    game_identity(continuation.focus(), park.get('frame'))
    t.receipt.update(frame=frame, completed=True, phase=PHASE)
    return ready, park, precision, operation, screen, failed, refs


def run(t, preparation, park_path, precision_path, failed_close_path):
    chain = None
    try:
        chain = capture(t, preparation, park_path, precision_path, failed_close_path)
    except BaseException as error:
        t.receipt.update(completed=False, failure=t.receipt.get('failure') or type(error).__name__ + ': ' + str(error))
        if not isinstance(error, Exception):
            raise
    finally:
        t.receipt['finished_at'] = time.time()
        if chain is not None and t.receipt.get('completed') is True:
            try:
                validate_capture(t.receipt, *chain)
            except BaseException as error:
                t.receipt.update(completed=False, failure=type(error).__name__ + ': ' + str(error))
                if not isinstance(error, Exception):
                    t.persist()
                    raise
        t.persist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('preparation', 'park', 'after-precision', 'failed-close', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    from .interaction_item_actionbar_continuation import scout
    from .interaction_trial import Trial
    from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
    with scout():
        trial = Trial(args.output, controller='code')
        trial.receipt.update(controller='code', custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY,
            input_sent=False, mutation_sent=False, qualification_added=False, stop_attempted=False)
        run(trial, args.preparation, args.park, args.after_precision, args.failed_close)
        print(json.dumps({key: trial.receipt.get(key) for key in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
