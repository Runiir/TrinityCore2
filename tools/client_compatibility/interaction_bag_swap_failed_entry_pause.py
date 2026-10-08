"""Capture and pause the excluded first bag-swap entry after its actual logout.

Capture reads the current offline state and complete retained wire history. Pause
requires a fresh review of that owned lobby frame and stops only its same child.
Neither command sends game input or admits a bag interaction.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import time

from . import lab_runtime as lab
from .bag_swap_contract import finite, owned_snapshot, require, strict_equal
from .bag_swap_preservation import ACCOUNTING, PRECISION_QUERY, exact_precision, float32_bits
from .bag_swap_sources import bound, private_json, reference

SCHEMA = 'client442_bag_swap_failed_entry_closure_v1'
CAPTURE_PHASE = 'bags_swap_failed_entry_captured'
PAUSE_PHASE = 'bags_swap_failed_entry_closed_paused'
SCRIPT = {'original': '0', 'current_stock_disabled': '1', 'original_restored': False}
STOP_CHECKS = ('scout_launcher_absent', 'owned_game_absent', 'all_retained_saved_state',
    'all_characters_offline', 'primary_still_stopped', 'native_lifetime', 'bridge_lifetime', 'origin_registration')


def continuation():
    from . import interaction_bag_swap_continuation
    return interaction_bag_swap_continuation


def geometry():
    from . import interaction_item_actionbar_parked_selection_capture
    return interaction_item_actionbar_parked_selection_capture


def history_contract():
    from . import bag_swap_failed_contract
    return bag_swap_failed_contract


def epoch_sources():
    from . import bag_swap_failed_sources
    return bag_swap_failed_sources


class LocalSources:
    """Bind only the small closure graph and its exact journal/PNG members."""
    def __init__(self):
        self.data, self.digests, self.raw_journals = {}, {}, {}

    def get(self, ref, successful=False):
        reference(ref)
        require(bound(ref['path']) == ref, 'local closure source bytes changed')
        value = private_json(ref['path'], False, root=lab.ROOT)
        require(bound(ref['path']) == ref, 'local closure source changed during parsing')
        member = str(Path(ref['path']).relative_to(lab.ROOT))
        self.data[member], self.digests[member] = value, ref['sha256']
        for key in ('frame',):
            if type(value.get(key)) is dict:
                path = image_file(ref, value[key])
                self.digests[str(path.relative_to(lab.ROOT))] = bound(path)['sha256']
        image_ref = value.get('original_failed_image')
        if image_ref is not None:
            reference(image_ref)
            path = Path(image_ref['path'])
            require(path.suffix == '.png' and path.is_relative_to(lab.ROOT / 'evidence') and bound(path) == image_ref,
                'original failed-entry PNG bytes changed')
            self.digests[str(path.relative_to(lab.ROOT))] = image_ref['sha256']
        for key, source in value.get('journal_sources', {}).items():
            reference(source)
            require(bound(source['path']) == source, 'local complete closure journal changed')
            name = str(Path(source['path']).relative_to(lab.ROOT))
            with Path(source['path']).open() as handle:
                rows = []
                for line in handle:
                    require(line.endswith('\n'), 'complete closed journal rows required')
                    rows.append(json.loads(line))
            require(bound(source['path']) == source, 'local journal changed during complete replay')
            self.digests[name], self.raw_journals[name] = source['sha256'], rows
        return value


def capture_preflight(value, ref):
    store = LocalSources()
    store.get(ref)
    return epoch_sources().validate_failed_capture(store, value)


def load(ref, successful=None):
    reference(ref)
    require(bound(ref['path']) == ref, 'immutable failed-closure source bytes changed')
    value = private_json(ref['path'], False, root=lab.ROOT)
    require(bound(ref['path']) == ref, 'failed-closure source changed during parsing')
    require(finite(value.get('started_at')) and finite(value.get('finished_at')) and
        0 < value['started_at'] < value['finished_at'], 'closed actual source timestamps required')
    if successful is not None:
        require(value.get('completed') is successful and
            ((value.get('failure') is None) if successful else bool(value.get('failure'))),
            'actual closed source outcome differs')
    return value


def current_sources(t):
    from .bag_swap_projection import source_identities
    require(t.receipt.get('code_commit') == subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip(), 'closure requires actual current committed code')
    t.receipt['committed_sources'] = source_identities(lab.REPO)


def owner(t, ready):
    c = continuation()
    require(t.fixture == ready.get('actor') == c.registration() and t.fixture.get('guid') == 2 and
        t.receipt.get('runtime') == ready.get('runtime') == c.runtime(),
        'closure must retain the original owned scout and native/bridge lifetimes')
    report = c.source_report(ready)
    require(strict_equal(ready.get('all_offline_snapshot'), report['snapshot']),
        'original ready must retain the admitted UI171 offline baseline')
    stopped = c.primary_stopped(Path(report['primary_stop_source']['path']))
    require(stopped.get('after') == ready['all_offline_snapshot']['1'], 'original primary stop differs')
    require(not any((lab.ROOT / 'run' / name).exists() for name in (
        'owned_pet_abandon_probe.json', 'owned_tame_request_probe.json',
        'owned_stable_request_probe.json', 'owned_entry_request_probe.json')),
        'cannot pause with an armed gameplay probe')
    monitor = c.focus()
    require(monitor.get('second_monitor_verified') is True and monitor.get('monitor', {}).get('name') == 'HDMI-1',
        'failed scout must remain on HDMI-1')
    geometry().game_identity(monitor, ready.get('frame'))
    return report, stopped, monitor


def offline_state(ready):
    current = continuation().snapshot()
    before = ready['all_offline_snapshot']
    old, now = owned_snapshot(before), owned_snapshot(current)
    require(all(strict_equal(current[g], before[g]) for g in ('1', '3', '4', '5', '6')) and
        set(old['native']) == set(now['native']) and
        {k for k in old['native'] if not strict_equal(old['native'][k], now['native'][k])} <= ACCOUNTING | {'rest_bonus'} and
        all(type(v['native'].get(k)) is int and v['native'][k] >= 0 for v in (old, now) for k in ACCOUNTING) and
        all(now['native'][k] >= old['native'][k] for k in ('totaltime', 'leveltime', 'logout_time')) and
        strict_equal(old['saved'], now['saved']) and strict_equal(old['inventory'], now['inventory']) and
        now['pets'] == old['pets'] == [], 'failed entry changed complete offline state beyond ordinary accounting/rest')
    return current


def read_precision(before):
    with lab.connection() as con, con.cursor() as q:
        q.execute(PRECISION_QUERY)
        rows = q.fetchall()
        require(len(rows) == 1, 'one actual original-scout exact FLOAT row required')
        row = dict(zip([column[0] for column in q.description], rows[0]))
    row = json.loads(json.dumps(row))
    row['exact_rest_bonus_float32_bits'] = float32_bits(row.get('exact_rest_bonus'))
    exact_precision(row, before)
    return row


def journal_history(t, ready, failed, until):
    from .observation.journal import entries
    paths = {'packets': lab.ROOT / 'evidence/world_packets.jsonl', 'events': lab.ROOT / 'logs/modern_world.jsonl'}
    physical = set()
    for row in entries(paths['events']):
        require(type(row) is dict, 'journal rows must be objects')
        if (row.get('event') == 'instance_authenticated' and row.get('account_id') == 2 and
                finite(row.get('time')) and failed['started_at'] <= row['time'] <= failed['entry_input_finished_at']):
            require(type(row.get('session')) is str and row['session'], 'actual physical login session required')
            physical.add(row['session'])
    sessions = physical | {ready['native_session']}
    data, refs = {}, {}
    for role, path in paths.items():
        rows = []
        for row in entries(path):
            require(type(row) is dict, 'journal rows must be objects')
            if row.get('session') in sessions or row.get('account_id') == 2 or row.get('guid') == 2:
                require(finite(row.get('time')), 'malformed attributable journal time cannot be filtered out')
            if finite(row.get('time')) and failed['started_at'] <= row['time'] <= until:
                rows.append(row)
        target = t.out / (role + '.jsonl')
        require(not target.exists(), 'failed closure must retain new immutable journal copies')
        lab.private_write(target, ''.join(json.dumps(r, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n' for r in rows))
        data[role], refs[role] = rows, bound(target)
    proof = history_contract().failed_history(data['packets'], data['events'], ready, failed, until)
    return proof, refs


def image_file(source, image, *, fresh=False):
    reference(source)
    require(type(image) is dict and type(image.get('file')) is str and Path(image['file']).name == image['file'],
        'source-owned ordinary lobby image required')
    path = Path(source['path']).parent / image['file']
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)) and
        bound(path)['sha256'] == image.get('sha256'), 'actual source-owned lobby PNG bytes changed')
    if fresh:
        require(0 <= time.time() - path.stat().st_mtime < 120, 'fresh lobby review must be less than 120 seconds old')
    return path


def review(t, path, capture_ref, captured):
    path = Path(path)
    require(path.is_absolute() and path.resolve().is_relative_to(lab.ROOT / 'evidence'), 'owned closure review required')
    review_ref = bound(path)
    checked = json.loads(path.read_text())
    require(bound(path) == review_ref and checked.get('reviewed') is True and checked.get('control') == 'Harnesstwo' and
        checked.get('source') == capture_ref and checked.get('frame') == captured.get('frame') and
        type(checked.get('selected_character')) is str and checked['selected_character'] == 'Harnesstwo' and
        type(checked.get('selected_level')) is int and checked['selected_level'] == 1,
        'review must identify the fresh source-owned Harnesstwo lobby selection')
    image_file(capture_ref, captured['frame'], fresh=True)
    copy = path.parent / captured['frame']['file']
    require(copy.is_file() and bound(copy)['sha256'] == captured['frame']['sha256'] and
        0 <= time.time() - copy.stat().st_mtime < 120, 'review PNG copy must retain exact fresh source bytes')
    geometry().game_identity(continuation().focus(), captured['frame'])
    t.receipt.update(review_source=review_ref, screen_review={'path': str(path), 'sha256': review_ref['sha256'],
        'frame': deepcopy(captured['frame'])})
    t.persist()
    return checked


def capture(t, preparation, failed_entry, precision, failed_h, lobby, attestation):
    refs = {key: bound(path) for key, path in {'original_preparation_source': preparation,
        'original_entry_source': failed_entry, 'before_precision_source': precision,
        'lobby_source': lobby, 'no_input_attestation_source': attestation}.items()}
    ready, failed = load(refs['original_preparation_source'], True), load(refs['original_entry_source'], False)
    before_precision = load(refs['before_precision_source'], True)
    require(failed.get('preparation_source') == refs['original_preparation_source'] and
        failed.get('precision_source') == refs['before_precision_source'] and
        before_precision.get('source') == refs['original_preparation_source'], 'original failed login ancestry differs')
    current_sources(t)
    report, _, _ = owner(t, ready)
    before = offline_state(ready)
    t.receipt.update(**refs, failed_housekeeping_sources=[bound(p) for p in failed_h],
        predecessor=ready['predecessor'], authority_source=ready['authority_source'],
        runtime_authority_source=ready['runtime_authority_source'], primary_stop_source=report['primary_stop_source'],
        native_session=ready['native_session'], before=before, all_offline_snapshot=before,
        phase='bags_swap_failed_entry_capture_started')
    t.persist()
    row = read_precision(before)
    until = time.time()
    proof, journals = journal_history(t, ready, failed, until)
    image = continuation().shot(t.out / 'expired_selection.png')
    geometry().frame_identity(image, t.receipt['runtime'], ready['frame'])
    geometry().game_identity(continuation().focus(), ready['frame'])
    after = offline_state(ready)
    require(strict_equal(after, before), 'read-only failed closure capture changed current offline state')
    epochs = epoch_sources().carry_epochs(ready, t.receipt['failed_housekeeping_sources'], t.out / 'code_epochs',
        preparation_ref=refs['original_preparation_source'], current=t.receipt)
    t.receipt.update(after=after, exact_precision={'query': PRECISION_QUERY, 'row': row, 'before': before, 'after': after,
        'source': None, 'input_sent': False, 'mutation_sent': False}, failed_history=proof, journal_sources=journals,
        code_epochs=epochs, frame=image, phase=CAPTURE_PHASE, completed=True)
    t.receipt['finished_at'] = time.time()
    t.persist()
    capture_preflight(t.receipt, bound(t.out / 'episode.json'))


def pause(t, captured_path, review_path):
    capture_ref = bound(captured_path)
    captured = load(capture_ref, True)
    require(captured.get('schema') == SCHEMA and captured.get('phase') == CAPTURE_PHASE and
        captured.get('input_sent') is False and captured.get('mutation_sent') is False and
        captured.get('excluded_failed_entry') is True and captured.get('qualification_added') is False,
        'pause requires the successful excluded read-only failed-entry capture')
    ready = load(captured['original_preparation_source'], True)
    current_sources(t)
    require(t.receipt['code_commit'] == captured.get('code_commit') and
        t.receipt['committed_sources'] == captured.get('committed_sources'), 'capture and pause current code bytes differ')
    capture_preflight(captured, capture_ref)
    _, stopped_primary, monitor = owner(t, ready)
    require(offline_state(ready) == captured['before'], 'reviewed current offline state changed')
    review(t, review_path, capture_ref, captured)
    copied = ('original_preparation_source', 'original_entry_source', 'before_precision_source',
        'failed_housekeeping_sources', 'lobby_source', 'no_input_attestation_source', 'predecessor',
        'authority_source', 'runtime_authority_source', 'primary_stop_source', 'native_session', 'code_epochs')
    t.receipt.update({k: deepcopy(captured[k]) for k in copied})
    game = monitor['input_isolation']['game_pid']
    ticks = lab.proc_start(game)
    require(type(ticks) is str and re.fullmatch('[1-9][0-9]*', ticks), 'owned game start ticks must be canonical positive ASCII')
    image = continuation().shot(t.out / 'expired_selection_paused.png')
    geometry().frame_identity(image, t.receipt['runtime'], captured['frame'])
    geometry().game_identity(continuation().focus(), captured['frame'])
    before = offline_state(ready)
    row = read_precision(before)
    require(row == captured['exact_precision']['row'] and before == captured['before'], 'fresh exact offline FLOAT changed')
    failed = load(captured['original_entry_source'], False)
    proof, journals = journal_history(t, ready, failed, time.time())
    t.receipt.update(capture_source=capture_ref, before=before, all_offline_snapshot=before,
        exact_precision={**deepcopy(captured['exact_precision']), 'source': capture_ref},
        failed_history=proof, journal_sources=journals, frame=image,
        closing_frame_source=bound(t.out / image['file']), game_before={'pid': game, 'start_ticks': ticks},
        action='stop_expired_failed_entry_scout', phase='bags_swap_failed_entry_pause_started', stop_attempted=True)
    t.persist()
    geometry().game_identity(continuation().focus(), captured['frame'])
    require(strict_equal(offline_state(ready), before),
        'all six characters must retain the current offline boundary immediately before stop')
    lab.stop('client')
    after = continuation().snapshot()
    with continuation().scout_peer_primary():
        primary_absent = lab.owned_process('client') is None
    checks = {'scout_launcher_absent': lab.owned_process('client') is None,
        'owned_game_absent': continuation().gone(game, ticks), 'all_retained_saved_state': strict_equal(before, after),
        'all_characters_offline': all(v['native']['online'] == 0 for v in after.values()),
        'primary_still_stopped': primary_absent and after['1'] == stopped_primary['after'],
        'native_lifetime': continuation().identity('worldserver') == ready['runtime']['worldserver'],
        'bridge_lifetime': continuation().identity('modern_world') == ready['runtime']['modern_world'],
        'origin_registration': continuation().registration() == t.fixture}
    t.receipt.update(after=after, shutdown_checks=checks, stop_finished_at=time.time())
    require(all(v is True for v in checks.values()), 'failed-entry shutdown must pass every complete preservation check')
    t.receipt.update(completed=True, phase=PAUSE_PHASE)


def run_trial(t, operation):
    t.receipt.update(schema=SCHEMA, controller='code', model=None, revision=None,
        custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT, qualification_added=False,
        excluded_failed_entry=True, operations_admitted=0, input_sent=False, mutation_sent=False)
    t.persist()
    try:
        operation()
    except BaseException as error:
        t.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        t.receipt['finished_at'] = time.time()
        t.persist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='stage', required=True)
    cap = sub.add_parser('capture')
    for name in ('preparation', 'failed-entry', 'precision', 'failed-h06', 'failed-h07', 'lobby', 'attestation', 'output'):
        cap.add_argument('--' + name, type=Path, required=True)
    stop = sub.add_parser('pause')
    for name in ('capture', 'review', 'output'):
        stop.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    from .interaction_trial import Trial
    with continuation().scout():
        t = Trial(args.output, controller='code')
        run_trial(t, lambda: capture(t, args.preparation, args.failed_entry, args.precision,
            [args.failed_h06, args.failed_h07], args.lobby, args.attestation) if args.stage == 'capture'
            else pause(t, args.capture, args.review))
        print(json.dumps({k: t.receipt.get(k) for k in ('completed', 'phase', 'failure', 'shutdown_checks')}, indent=2))


if __name__ == '__main__':
    main()
