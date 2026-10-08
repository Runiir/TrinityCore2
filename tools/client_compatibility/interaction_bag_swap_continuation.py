"""Source-bound occupied-swap scout launch, entry, exact rest reads and closed pause.

Runtime dependencies are loaded only by executable helpers. Importing this module
does not open SQL, authenticate, focus a window, or load the UI/protocol stack.
"""
import argparse
import gc
from copy import deepcopy
from contextlib import contextmanager
import json
import os
import subprocess
from pathlib import Path
import time

from . import lab_runtime as lab
from .bag_swap_contract import (ACTOR, REST_CAP, require, finite, owned_snapshot,
    login_packets, native_replay, forbidden_packets)
from .item_actionbar_contract import public_assignments
from .bag_swap_preservation import ACCOUNTING, PRECISION_QUERY, exact_precision, float32_bits

SCHEMA = 'client442_bag_swap_scout_resume_v1'
SCRIPT_BOUNDARY = {'original': '0', 'current_stock_disabled': '1', 'original_restored': False}
PRECISION_CHECKS = ('all_six_offline', 'all_saved_state_unchanged', 'original_identity',
    'snapshot_rest_matches', 'exact_float32')
PARK_CHECKS = ('ordinary_logout', 'native_logout', 'delivered_logout', 'all_six_offline',
    'protected_actors', 'saved_inventory', 'saved_actions', 'native_health_power_pose', 'original_registration')
PAUSE_CHECKS = ('scout_launcher_absent', 'owned_game_absent', 'all_retained_saved_state',
    'all_characters_offline', 'primary_still_stopped', 'native_lifetime', 'bridge_lifetime', 'origin_registration')


def sources():
    from . import bag_swap_sources
    return bag_swap_sources


def identity(kind):
    from .interaction_bridge_deploy import identity as read
    return read(kind)


def snapshot():
    from .interaction_parked_client_resource_pause import snapshot as read
    return read()


def runtime():
    return {k: identity(k) for k in ('worldserver', 'modern_world', 'client')}


def registration():
    from . import actors
    return actors.load()


def session(fixture):
    from . import actors
    return actors.session_entry(fixture)['session']


def shot(path):
    from .interaction_bridge_deploy import shot as capture
    return capture(path)


def focus():
    from . import owned_input
    return owned_input.focus()


def primary_stopped(path):
    from .interaction_single_scout_bridge_deploy import primary_stopped as read
    return read(path)


def gone(pid, ticks):
    from .interaction_parked_client_resource_pause import gone as read
    return read(pid, ticks)


def packets():
    from .observation.journal import entries
    return entries(lab.ROOT / 'evidence/world_packets.jsonl')


def metadata():
    from .observation.journal import entries
    return entries(lab.ROOT / 'logs/modern_world.jsonl')


def oracle(owner_session):
    from .observation.inventory import Inventory
    return Inventory(lab.ROOT, owner_session, 2).poll()


def resources(native):
    from .interaction_spellbook_recon import resources as read
    return read(native)


def bars(t, label):
    from .interaction_actionbar_pages import detail
    return detail(t, label)


def native_baseline(t):
    from .interaction_bridge_restoration import capture
    return capture(t)


def review(t, path, control):
    from .interaction_offline_bridge_deploy import review as read
    return read(t, path, control)


@contextmanager
def scout():
    previous = os.environ.get('CLIENT442_ACTOR')
    os.environ['CLIENT442_ACTOR'] = 'scout'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('CLIENT442_ACTOR', None)
        else:
            os.environ['CLIENT442_ACTOR'] = previous


def persist(directory, report):
    lab.private_write(Path(directory) / 'resume.json', json.dumps(report, indent=2) + '\n')


def source_report(report):
    ref = report.get('authority_source')
    sources().reference(ref)
    compact = report.get('runtime_authority_source')
    sources().reference(compact)
    require(sources().bound(compact['path']) == compact, 'compact UI171 runtime authority bytes changed')
    old = sources().cached_runtime(compact['path'], ref)
    require(report.get('predecessor') == old['predecessor'], 'UI171 predecessor roles differ')
    return {k: old[k] for k in ('closure', 'snapshot', 'predecessor', 'primary_stop_source',
        'dvc_pointer', 'runtime', 'origin_actor')}


def create_resume(directory, output):
    for path in (Path(directory), Path(output)):
        require(not path.exists() and path.resolve().is_relative_to(lab.ROOT / 'evidence'),
            'requires new private continuation directories')
        path.mkdir(parents=True, mode=0o700)


def launch():
    from .auth import accounts, control
    credentials = json.loads((lab.client_root() / 'secrets/game_account.json').read_text())
    account = accounts.check_password(credentials['username'], credentials['password'])
    require(account, 'owned scout local SSO account unavailable')
    control.launch('launcher', accounts.issue(account, 'launcher'), account['login'])


def available_memory_kib():
    return next(int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
        if line.startswith('MemAvailable:'))


def start(directory, output, closure, remote, checkpoint):
    require(available_memory_kib() >= 6 * 1024 * 1024,
        'predecessor streaming requires 6 GiB available memory before parsing')
    old = sources().source_bundle(closure, remote, checkpoint)
    stopped, before = old['closure'], old['snapshot']
    primary_stopped(Path(old['primary_stop_source']['path']))
    from .review_hunter_revive_prerequisites import absent_clients
    absent_clients()
    native, bridge = identity('worldserver'), identity('modern_world')
    require(native == stopped['runtime']['worldserver'] and bridge == stopped['runtime']['modern_world'] and
        snapshot() == before and registration() == old['origin_actor'] and
        gone(stopped['runtime']['client']['pid'], stopped['runtime']['client']['start_ticks']) and
        gone(stopped['game_before']['pid'], stopped['game_before']['start_ticks']),
        'unchanged all-six UI171 pause, owner registration or stopped clients differ')
    memory = available_memory_kib()
    require(memory >= 6 * 1024 * 1024, 'one scout launch requires 6 GiB available memory')
    create_resume(directory, output)
    authority = Path(directory) / 'authority.json'
    lab.private_write(authority, json.dumps({'schema': 'client442_bag_swap_predecessor_authority_v1',
        'values': old['values'], 'refs': old['predecessor'], 'graph': old['graph']}, separators=(',', ':')) + '\n')
    require(Path(directory).parent == Path(output).parent and Path(directory).parent.parent == lab.ROOT / 'evidence',
        'fresh launch and cached authority must share the named ordinary batch')
    from .checkpoint_bag_swap import carry_authority
    authority_ref = sources().bound(authority)
    carry_authority(Path(directory).parent, authority_ref, admitted=old)
    compact = Path(directory) / 'runtime_authority.json'
    lab.private_write(compact, json.dumps(sources().compact_authority(old, authority_ref),
        separators=(',', ':')) + '\n')
    old = {k: old[k] for k in ('closure', 'snapshot', 'predecessor', 'primary_stop_source',
        'dvc_pointer', 'runtime', 'origin_actor')}
    gc.collect()
    memory = available_memory_kib()
    require(memory >= 6 * 1024 * 1024, 'one scout launch requires 6 GiB after predecessor streaming/carry')
    report = {'schema': SCHEMA, 'started_at': time.time(), 'predecessor': old['predecessor'],
        'authority_source': authority_ref, 'runtime_authority_source': sources().bound(compact),
        'predecessor_dvc_pointer': old['dvc_pointer'],
        'previous_runtime': stopped['runtime'], 'all_offline_snapshot': before, 'origin_actor': old['origin_actor'],
        'available_memory_kib_before': memory, 'launch_attempted': False, 'installed': False,
        'completed': False, 'failure': None, 'input_sent': False, 'qualification_added': False,
        'controller': 'code', 'model': None}
    from .bag_swap_projection import source_identities
    report.update(code_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip(),
        committed_sources=source_identities(lab.REPO))
    persist(directory, report)
    try:
        report['launch_attempted'] = True
        persist(directory, report)
        launch()
        current, monitor = runtime(), focus()
        checks = {'native_unchanged': current['worldserver'] == native,
            'bridge_unchanged': current['modern_world'] == bridge,
            'fresh_scout': current['client'] != stopped['runtime']['client'],
            'all_six_saved_snapshots': snapshot() == before,
            'primary_stopped': bool(primary_stopped(Path(old['primary_stop_source']['path']))),
            'HDMI_1': monitor.get('second_monitor_verified') is True and monitor.get('monitor', {}).get('name') == 'HDMI-1',
            'private_input': monitor.get('input_isolation', {}).get('actor') == 'scout' and
                monitor['input_isolation'].get('host_activation_sent') is False}
        report.update(runtime=current, launch_monitor=monitor, checks=checks, installed=all(checks.values()))
        persist(directory, report)
        require(report['installed'], 'fresh scout HDMI-1, private input or six-actor preservation differs')
        report['frame'] = shot(Path(output) / 'launched.png')
    except BaseException as error:
        report.update(completed=False, failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['launch_finished_at'] = time.time()
        report['finished_at'] = report['launch_finished_at']
        report['completed'] = report.get('installed') is True and report.get('failure') is None
        report['phase'] = 'bags_swap_scout_launched' if report['completed'] else 'bags_swap_scout_launch_failed'
        persist(directory, report)
    return report


def current(t, directory):
    report = sources().private_json(Path(directory) / 'resume.json', False)
    old = source_report(report)
    require(report.get('schema') == SCHEMA and report.get('installed') is True and report.get('failure') is None and
        set(report.get('checks', {})) == {'native_unchanged', 'bridge_unchanged', 'fresh_scout',
            'all_six_saved_snapshots', 'primary_stopped', 'HDMI_1', 'private_input'} and
        all(v is True for v in report['checks'].values()) and report.get('all_offline_snapshot') == old['snapshot'] and
        report.get('runtime') == t.receipt['runtime'] and t.fixture == report.get('origin_actor') == registration() and
        t.fixture.get('guid') == 2 and snapshot() == old['snapshot'] and
        report.get('code_commit') == t.receipt.get('code_commit') and
        report.get('committed_sources') == t.receipt.get('committed_sources'), 'current resumed original scout differs')
    primary_stopped(Path(report['predecessor']['primary_stop']['path']))
    from .interaction_item_actionbar_parked_selection_capture import game_identity
    game_identity(focus(), report['frame'])
    return report


def capture(t, directory):
    report = current(t, directory)
    from .interaction_item_actionbar_parked_selection_capture import frame_identity
    image = shot(t.out / 'screen.png')
    frame_identity(image, t.receipt['runtime'], report['frame'])
    t.receipt.update(resume_source=sources().bound(Path(directory) / 'resume.json'),
        all_offline_snapshot=report['all_offline_snapshot'], frame=image,
        phase='bags_swap_scout_captured', input_sent=False, completed=True)


def lobby(t, directory, review_path, stage):
    current(t, directory)
    control = {'dismiss': 'Okay', 'reconnect': 'Reconnect', 'realm': 'Client442 Lab', 'character': 'Harnesstwo'}[stage]
    checked, _ = review(t, review_path, control)
    point = checked.get('point', [])
    require(len(point) == 2 and all(type(p) is int for p in point) and
        0 <= point[0] < 1280 and 0 <= point[1] < 720, 'bounded reviewed lobby point differs')
    if stage == 'character':
        require(1040 <= point[0] < 1280 and 70 <= point[1] < 560, 'reviewed roster point differs')
    if stage == 'realm':
        require(checked.get('confirm_selected_realm') is True, 'reviewed realm confirmation missing')
    t.receipt.update(stage=stage, phase='bags_swap_lobby_started', input_sent=True)
    t.persist()
    if stage == 'dismiss':
        t.io.key('Return', hold=1.2)
    else:
        t.io.click(*point, hold=1.2)
        if stage == 'realm':
            time.sleep(1.2)
            t.io.key('Return', hold=1.2)
    time.sleep(12)
    current(t, directory)
    t.receipt.update(frame=shot(t.out / 'next_screen.png'), phase='bags_swap_lobby_complete', completed=True)


def finish(t, directory, review_path):
    report = current(t, directory)
    checked, selected = review(t, review_path, 'Harnesstwo')
    require((checked.get('selected_character'), checked.get('selected_level')) == ('Harnesstwo', 1),
        'reviewed original selection differs')
    events = list(metadata())
    auth = [r for r in events if r.get('event') == 'world_authenticated' and r.get('account_id') == 2 and
        report['started_at'] <= r.get('time', 0) <= time.time()]
    require(len(auth) == 1 and type(auth[0].get('session')) is str and auth[0]['session'],
        'one fresh scout realm authentication is required')
    owner_session = auth[0]['session']
    owned = [r for r in events if r.get('session') == owner_session and r.get('time', 0) >= report['started_at']]
    require(any(r.get('name') == 'SMSG_ENUM_CHARACTERS_RESULT' and r.get('direction') == 'to_client' for r in owned) and
        not any(r.get('event') in ('native_player_created', 'world_connection_closed', 'native_stream_closed') for r in owned),
        'fresh original selection connection differs')
    from .interaction_item_actionbar_parked_selection_capture import frame_identity
    image = shot(t.out / 'original_selected.png')
    frame_identity(image, t.receipt['runtime'], report['frame'])
    t.receipt.update(phase='bags_swap_scout_ready', native_session=owner_session,
        resume_source=sources().bound(Path(directory) / 'resume.json'), selection_source=checked['source'],
        authority_source=report['authority_source'], runtime_authority_source=report['runtime_authority_source'],
        predecessor=report['predecessor'], all_offline_snapshot=report['all_offline_snapshot'],
        predecessor_dvc_pointer=report['predecessor_dvc_pointer'],
        realm_authentication=auth[0], frame=image, input_sent=False,
        checks={'original_selection': True, 'fresh_enumeration': True, 'all_six_offline': True}, completed=True)
    return report


def prepared(t, preparation, online=False):
    ready = sources().closed(preparation)
    require(type(online) is bool and ready.get('phase') == 'bags_swap_scout_ready' and
        ready.get('actor') == t.fixture == registration() and t.fixture.get('guid') == 2 and
        ready.get('runtime') == t.receipt['runtime'] == runtime() and
        all(v is True for v in ready.get('checks', {}).values()) and len(ready.get('checks', {})) == 3,
        'closed current original scout preparation differs')
    baseline = ready.get('all_offline_snapshot')
    owned_snapshot(baseline)
    old = source_report({'predecessor': ready['predecessor'], 'authority_source': ready['authority_source'],
        'runtime_authority_source': ready['runtime_authority_source']})
    require(baseline == old['snapshot'], 'ready baseline differs from accepted UI171 pause')
    now = snapshot()
    owned_snapshot(now, offline=not online, swapped=online and now['2']['inventory'] != baseline['2']['inventory'])
    require(all(now[g] == baseline[g] for g in ('1', '3', '4', '5', '6')),
        'a protected actor changed after original scout preparation')
    if online:
        from .bag_swap_contract import inventory_rows
        inventory_rows(baseline['2']['inventory'], now['2']['inventory'],
            swapped=now['2']['inventory'] != baseline['2']['inventory'])
        before, after = baseline['2'], now['2']
        require(after['native']['online'] == 1 and set(after['native']) == set(before['native']) and
            {k for k in before['native'] if before['native'][k] != after['native'][k]} <= ACCOUNTING | {'rest_bonus', 'online'} and
            finite(after['native']['rest_bonus']) and 0 <= after['native']['rest_bonus'] < REST_CAP and
            after['pets'] == [] and
            {k: v for k, v in after['saved'].items() if k != 'actions'} ==
                {k: v for k, v in before['saved'].items() if k != 'actions'},
            'online owner resources, native pose/health/power, pets or saved baseline differ')
    else:
        require(now == baseline, 'all six offline resources changed')
    primary_stopped(Path(ready['predecessor']['primary_stop']['path']))
    t.receipt.update(preparation_source=sources().bound(preparation), predecessor=ready['predecessor'],
        all_offline_snapshot=baseline, native_session=ready['native_session'])
    t.persist()
    return ready


def precision(t, source):
    old = sources().closed(source)
    require(old.get('phase') in ('bags_swap_scout_ready', 'bags_swap_parked'),
        'precision requires its exact ready or parked offline boundary')
    before = snapshot()
    require(before == old.get('all_offline_snapshot') and old.get('runtime') == t.receipt['runtime'],
        'precision source or all-six offline snapshot changed')
    owned_snapshot(before)
    ref = sources().bound(source)
    t.receipt.update(phase='bags_swap_rest_precision_started', source=ref, before=before,
        query=PRECISION_QUERY, input_sent=False, mutation_sent=False)
    t.persist()
    with lab.connection() as con, con.cursor() as q:
        q.execute(PRECISION_QUERY)
        rows = q.fetchall()
        require(len(rows) == 1, 'one exact owned actor2 FLOAT row is required')
        row = dict(zip([c[0] for c in q.description], rows[0]))
    row = json.loads(json.dumps(row))
    row['exact_rest_bonus_float32_bits'] = float32_bits(row.get('exact_rest_bonus'))
    exact_precision(row, before)
    after = snapshot()
    require(after == before and runtime() == t.receipt['runtime'] and sources().bound(source) == ref,
        'read-only precision changed state, source or runtime')
    t.receipt.update(row=row, after=after, rest_sources=sources().rest_sources(),
        checks={k: True for k in PRECISION_CHECKS}, completed=True, phase='bags_swap_rest_precision_complete')


def precision_source(path, ref, expected):
    value = sources().closed(path)
    require(value.get('phase') == 'bags_swap_rest_precision_complete' and value.get('source') == ref and
        value.get('query') == PRECISION_QUERY and value.get('before') == value.get('after') == expected and
        value.get('input_sent') is False and value.get('mutation_sent') is False and
        value.get('rest_sources') == sources().rest_sources() and
        set(value.get('checks', {})) == set(PRECISION_CHECKS) and all(v is True for v in value['checks'].values()),
        'exact immutable actor2 FLOAT source differs')
    exact_precision(value['row'], expected)
    return value


def enter(t, preparation, precision_path, review_path):
    ready = prepared(t, preparation)
    exact = precision_source(precision_path, sources().bound(preparation), ready['all_offline_snapshot'])
    checked, selected = review(t, review_path, 'Enter World')
    require(checked.get('source') == sources().bound(preparation) and
        (checked.get('selected_character'), checked.get('selected_level'), checked.get('point')) ==
        ('Harnesstwo', 1, [640, 660]) and exact['finished_at'] <= t.receipt['started_at'],
        'ordinary entry requires the fresh reviewed original ready screen and prior exact FLOAT')
    before, owner_session = ready['all_offline_snapshot']['2']['native'], ready['native_session']
    t.receipt.update(precision_source=sources().bound(precision_path), native_before_entry=before,
        entry_input_started_at=time.time(), input_sent=True, phase='bags_swap_entry_started')
    t.persist()
    try:
        from .interaction_item_actionbar_parked_selection_capture import game_identity, frame_identity
        game_identity(focus(), ready['frame'])
        t.io.click(*checked['point'], hold=1.2)
        time.sleep(8)
        state, frame = t.observe('bags_swap_entered', seconds=120)
        frame_identity(frame, t.receipt['runtime'], ready['frame'])
        require(session(t.fixture) == owner_session, 'ordinary login changed its owned realm session')
        until = time.time()
        raw = [p for p in packets() if p.get('session') == owner_session and
            t.receipt['entry_input_started_at'] <= p.get('time', 0) <= until]
        chain = login_packets(raw, owner_session, t.receipt['entry_input_started_at'], until)
        owner = native_replay(raw, owner_session, t.receipt['entry_input_started_at'], until)
        now = snapshot()
        require(now['2']['native'] == {**before, 'online': 1} and now['2']['saved'] == ready['all_offline_snapshot']['2']['saved'] and
            now['2']['inventory'] == ready['all_offline_snapshot']['2']['inventory'] and now['2']['pets'] == [] and
            all(now[g] == ready['all_offline_snapshot'][g] for g in ('1', '3', '4', '5', '6')),
            'ordinary entry changed saved native/resources or protected actors')
        require(state.get('player') == 'Harnesstwo' and type(state.get('level')) is int and state['level'] == 1 and
            state.get('guid') == t.guid and state.get('xp') == 0 and state.get('xp_max') == 400 and
            type(state.get('xp_exhaustion')) is int and state['xp_exhaustion'] == 2 * owner['rest_threshold'] and
            not state.get('lua_errors') and not state.get('blocked_actions') and not state.get('cursor_info') and
            not state.get('spell_targeting') and not state.get('bags') and not state.get('panels') and
            not frame['movement']['dead'] and not frame['movement']['in_combat'] and
            not frame['movement']['speed'], 'ordinary level1 idle public entry or native rest threshold differs')
        native = oracle(owner_session)
        public = bars(t, 'bags_swap_entry_layout')
        active = before['activeTalentGroup']
        public_assignments(public, now['2']['saved']['actions'], active)
        t.receipt.update(login_packets=[chain[k] for k in ('modern', 'request', 'verify', 'delivered')],
            native_owner_proof=owner, owner_packets=owner['packets'], entered_native=now['2']['native'],
            saved=now['2']['saved'], resources=resources(native), public=public, active_spec=active,
            state=state, frame=frame, native_original=native_baseline(t),
            checks={'ordinary_login': True, 'native_owner': True, 'saved_baseline': True,
                'protected_actors': True, 'public_level1': True, 'empty_cursor': True},
            completed=True, phase='bags_swap_entered')
    except BaseException as error:
        t.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        t.persist()
        raise
    finally:
        until = time.time()
        t.receipt['entry_input_finished_at'] = until
        try:
            complete_rows = [p for p in packets() if p.get('session') == owner_session and
                t.receipt['started_at'] <= p.get('time', 0) <= until]
            t.receipt['raw_entry_packets'] = complete_rows
            if t.receipt.get('completed') is True:
                complete = native_replay(complete_rows, owner_session, t.receipt['started_at'], until,
                    rest_threshold=t.receipt['native_owner_proof']['rest_threshold'])
                t.receipt.update(native_owner_proof=complete, owner_packets=complete['packets'], finished_at=until)
        except BaseException as error:
            t.receipt['entry_finalization_failure'] = f'{type(error).__name__}: {error}'
            if t.receipt.get('completed') is True:
                t.receipt.update(completed=False, failure=t.receipt['entry_finalization_failure'])
                raise
        t.persist()


def logout(t):
    from .interaction_owned_language_fixture import logout as ordinary
    return ordinary(t)


def logout_packets(rows, owner_session, since, until):
    from .bag_swap_contract import packet_rows, body
    scoped = packet_rows(rows, owner_session, since, until)
    relevant = [p for p in scoped if p.get('name') in ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_COMPLETE') and
        p.get('direction') in ('to_native', 'from_native', 'to_client')]
    wanted = [('CMSG_LOGOUT_REQUEST', 'to_native', b''), ('SMSG_LOGOUT_COMPLETE', 'from_native', b''),
        ('SMSG_LOGOUT_COMPLETE', 'to_client', b'\0')]
    match = [[p for p in relevant if (p.get('name'), p.get('direction')) == (n, d) and body(p) == b]
        for n, d, b in wanted]
    require(len(relevant) == 3 and all(len(v) == 1 for v in match), 'one exact ordinary native/client logout triple is required')
    ordered = [v[0] for v in match]
    require(ordered[0]['time'] <= ordered[1]['time'] <= ordered[2]['time'] and
        ordered[2]['time'] - ordered[1]['time'] < 2, 'ordinary logout ordering differs')
    return ordered


def whole_logout_history(rows, entry, owner, ordered, recovery=False):
    from .bag_swap_contract import packet_rows
    until = ordered[1]['time']
    raw = packet_rows(rows, owner, entry['started_at'], until)
    replay = native_replay(raw, owner, entry['started_at'], until,
        rest_threshold=entry['native_owner_proof']['rest_threshold'])
    require(len(replay['native_inventory_transitions']) in ((1, 3) if recovery else (3,)),
        'ordinary logout requires the whole native occupied swap and exact inverse history')
    return raw, replay


def final_logout_history(ready, entry, parked):
    raw, replay = whole_logout_history(list(packets()), entry, ready['native_session'], parked['logout_packets'],
        recovery=parked.get('recovery_only') is True)
    require(raw == parked['raw_native_logout_history'] and replay == parked['native_logout_proof'],
        'actual whole owner/item history through native logout changed before stop')
    return replay


def park(t, preparation, source, recovery=False):
    ready = prepared(t, preparation, online=True)
    restored = sources().closed(source)
    require(restored.get('phase') == 'bags_swap_restored' and restored.get('runtime') == t.receipt['runtime'] and
        restored.get('actor') == t.fixture and restored.get('preparation_source') == sources().bound(preparation) and
        restored.get('native_session') == ready['native_session'] and type(recovery) is bool and
        (restored.get('recovery_only') is True if recovery else restored.get('recovery_only') is not True),
        'ordinary park requires the successful exact item roundtrip restoration')
    if recovery:
        failed = sources().linked(restored.get('first_failure_source'), False)
        require(restored.get('failed_whole_excluded') is True and restored.get('gameplay_input_replayed') is False and
            failed.get('actor') == t.fixture and failed.get('runtime') == t.receipt['runtime'] and
            failed.get('preparation_source') == sources().bound(preparation) and
            restored.get('baseline', {}).get('snapshot') == ready['all_offline_snapshot'] and
            restored.get('after_saved') == ready['all_offline_snapshot']['2']['saved'] and
            restored.get('after_resources') == restored['baseline']['resources'] and
            restored.get('actionbar_restored') is True and
            len(restored.get('layout_restoration_checks', {})) == 9 and
            all(v is True for v in restored['layout_restoration_checks'].values()),
            'failed item housekeeping must preserve the actual first failure and full restored baseline')
        t.receipt.update(recovery_only=True, failed_whole_excluded=True,
            first_failure_source=restored['first_failure_source'], gameplay_input_replayed=False)
    before = snapshot()
    require(before['2']['saved'] == ready['all_offline_snapshot']['2']['saved'],
        'park requires every original saved action row')
    from .bag_swap_contract import inventory_rows, native_resources
    inventory_rows(ready['all_offline_snapshot']['2']['inventory'], before['2']['inventory'],
        swapped=before['2']['inventory'] != ready['all_offline_snapshot']['2']['inventory'])
    native_resources(restored['baseline']['resources'], resources(oracle(ready['native_session'])), swapped=False)
    pre_logout_native = native_baseline(t)
    original = sources().linked(restored['entry_source'])['native_original']
    require(pre_logout_native == original, 'ordinary logout must retain exact original pose, sheath and AFK')
    from .interaction_item_actionbar import native_state
    pre_logout_state = native_state(ready['native_session'])
    require(pre_logout_state == restored['baseline']['native_state'], 'ordinary logout native layout differs from original entry')
    entry = sources().linked(restored['entry_source'])
    raw = list(packets())
    forbidden_packets(raw, ready['native_session'], entry['started_at'], time.time())
    native_replay(raw, ready['native_session'], entry['started_at'], time.time(),
        rest_threshold=entry['native_owner_proof']['rest_threshold'])
    t.receipt.update(source=sources().bound(source), entry_source=restored['entry_source'],
        before=before, logout_started_at=time.time(), input_sent=True, phase='bags_swap_parking_started')
    t.persist()
    try:
        from .interaction_item_actionbar_parked_selection_capture import game_identity, frame_identity
        game_identity(focus(), restored['frame'])
        logout(t)
        after = snapshot()
        owned_snapshot(after)
        t.receipt['all_offline_snapshot'] = after
        t.persist()
        baseline = ready['all_offline_snapshot']
        require(all(after[g] == baseline[g] for g in ('1', '3', '4', '5', '6')) and
            after['2']['saved'] == baseline['2']['saved'] and after['2']['inventory'] == baseline['2']['inventory'] and
            after['2']['pets'] == [] and set(after['2']['native']) == set(baseline['2']['native']) and
            {k for k in baseline['2']['native'] if baseline['2']['native'][k] != after['2']['native'][k]} <= ACCOUNTING | {'rest_bonus'},
            'ordinary logout changed pose, health, power, inventory, pets or protected actors')
        rows = list(packets())
        ordered = logout_packets(rows, ready['native_session'], t.receipt['logout_started_at'], time.time())
        whole, replay = whole_logout_history(rows, entry, ready['native_session'], ordered, recovery=recovery)
        parked_frame = shot(t.out / 'original_selection.png')
        frame_identity(parked_frame, t.receipt['runtime'], restored['frame'])
        t.receipt.update(logout_packets=ordered, frame=parked_frame, raw_native_logout_history=whole,
            native_logout_proof=replay, pre_logout_native_state=pre_logout_state,
            checks={k: True for k in PARK_CHECKS}, completed=True, phase='bags_swap_parked')
    finally:
        t.receipt['logout_finished_at'] = time.time()
        t.receipt['raw_logout_packets'] = [p for p in packets() if p.get('session') == ready['native_session'] and
            t.receipt['logout_started_at'] <= p.get('time', 0) <= t.receipt['logout_finished_at'] and
            p.get('name') in ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_COMPLETE')]
        t.persist()


def pause_recovery(t, preparation, park_path, before_precision, after_precision, review_path):
    """Close a restored failed unit; its retained first failure can never qualify."""
    ready, parked = sources().closed(preparation), sources().closed(park_path)
    require(ready.get('phase') == 'bags_swap_scout_ready' and parked.get('phase') == 'bags_swap_parked' and
        parked.get('recovery_only') is True and parked.get('failed_whole_excluded') is True and
        parked.get('actor') == ready.get('actor') == t.fixture == registration() and
        parked.get('runtime') == ready.get('runtime') == t.receipt['runtime'] == runtime() and
        parked.get('preparation_source') == sources().bound(preparation), 'exact excluded restored park required')
    before = precision_source(before_precision, sources().bound(preparation), ready['all_offline_snapshot'])
    after = precision_source(after_precision, sources().bound(park_path), parked['all_offline_snapshot'])
    entered = sources().linked(parked['entry_source'])
    from .bag_swap_preservation import preserve_six
    preservation = preserve_six(ready['all_offline_snapshot'], parked['all_offline_snapshot'], entered,
        before['row'], after['row'])
    failed = sources().linked(parked['first_failure_source'], False)
    require(failed.get('actor') == t.fixture and failed.get('runtime') == t.receipt['runtime'], 'original immutable failure differs')
    checked, _ = review(t, review_path, 'Harnesstwo')
    require(checked.get('source') == sources().bound(park_path) and
        (checked.get('selected_character'), checked.get('selected_level')) == ('Harnesstwo', 1),
        'excluded pause requires the fresh original selection review')
    stop = primary_stopped(Path(ready['predecessor']['primary_stop']['path']))
    require(snapshot() == parked['all_offline_snapshot'], 'excluded offline projection changed')
    from .interaction_item_actionbar_parked_selection_capture import game_identity, frame_identity
    monitor = focus()
    game_identity(monitor, parked['frame'])
    game = monitor['input_isolation']['game_pid']
    ticks = lab.proc_start(game)
    image = shot(t.out / 'failed_roundtrip_restored.png')
    frame_identity(image, t.receipt['runtime'], parked['frame'])
    t.receipt.update(source=sources().bound(park_path), preparation_source=sources().bound(preparation),
        before=parked['all_offline_snapshot'], first_failure_source=parked['first_failure_source'],
        preservation=preservation, recovery_only=True, failed_whole_excluded=True, gameplay_input_replayed=False,
        input_sent=False, mutation_sent=False, stop_attempted=True, game_before={'pid': game, 'start_ticks': ticks},
        frame=image, phase='bags_swap_recovery_pause_started')
    t.persist()
    try:
        game_identity(focus(), parked['frame'])
        final_logout_history(ready, entered, parked)
        lab.stop('client')
        final = snapshot()
        with scout_peer_primary():
            primary_absent = lab.owned_process('client') is None
        checks = {'scout_launcher_absent': lab.owned_process('client') is None, 'owned_game_absent': gone(game, ticks),
            'all_retained_saved_state': final == parked['all_offline_snapshot'],
            'all_characters_offline': all(v['native']['online'] == 0 for v in final.values()),
            'primary_still_stopped': primary_absent and final['1'] == stop['after'],
            'native_lifetime': identity('worldserver') == ready['runtime']['worldserver'],
            'bridge_lifetime': identity('modern_world') == ready['runtime']['modern_world'],
            'origin_registration': registration() == t.fixture}
        t.receipt.update(after=final, shutdown_checks=checks)
        require(all(v is True for v in checks.values()), 'excluded swap recovery shutdown differs')
        t.receipt.update(completed=True, phase='bags_swap_recovery_closed_paused')
    finally:
        t.receipt['stop_finished_at'] = time.time()
        t.persist()


def close_pause(t, preparation, entry, operation, park_path, before_precision, after_precision, review_path):
    from . import bag_swap_evidence as evidence
    refs = {k: sources().bound(v) for k, v in {'preparation': preparation, 'entry': entry,
        'operation': operation, 'park': park_path, 'before_precision': before_precision,
        'after_precision': after_precision}.items()}
    result, after, current = evidence.local_lifecycle(refs)
    ready, parked = current[0], current[3]
    require(ready.get('runtime') == t.receipt['runtime'] == runtime() and
        ready.get('actor') == t.fixture == registration() and snapshot() == after and
        all(v.get('code_commit') == t.receipt.get('code_commit') for v in current),
        'closed swap pause requires the exact frozen ordinary runtime and saved boundary')
    checked, _ = review(t, review_path, 'Harnesstwo')
    require(checked.get('source') == refs['park'] and
        (checked.get('selected_character'), checked.get('selected_level')) == ('Harnesstwo', 1),
        'closed swap pause requires the actual restored original selection review')
    stop = primary_stopped(Path(ready['predecessor']['primary_stop']['path']))
    require(not any((lab.ROOT / 'run' / n).exists() for n in ('owned_pet_abandon_probe.json',
        'owned_tame_request_probe.json', 'owned_stable_request_probe.json', 'owned_entry_request_probe.json')),
        'cannot pause with an armed gameplay probe')
    monitor = focus()
    require(monitor.get('second_monitor_verified') is True and monitor.get('monitor', {}).get('name') == 'HDMI-1' and
        monitor.get('pid') == ready['runtime']['client']['pid'], 'owned scout must remain on HDMI-1')
    from .interaction_item_actionbar_parked_selection_capture import game_identity, frame_identity
    game_identity(monitor, parked['frame'])
    game = monitor['input_isolation']['game_pid']
    ticks = lab.proc_start(game)
    closing_frame = shot(t.out / 'scout_parked.png')
    frame_identity(closing_frame, t.receipt['runtime'], parked['frame'])
    game_identity(focus(), parked['frame'])
    t.receipt.update(sources=refs, predecessor=ready['predecessor'], authority_source=ready['authority_source'],
        before=after, all_offline_snapshot=after, primary_stop_source=ready['predecessor']['primary_stop'],
        game_before={'pid': game, 'start_ticks': ticks}, frame=closing_frame,
        input_sent=False, mutation_sent=False, action='stop_parked_scout_after_bag_swap_roundtrip',
        proof=result, stop_attempted=True, phase='bags_swap_pause_started')
    t.persist()
    try:
        game_identity(focus(), parked['frame'])
        final_logout_history(ready, current[1], parked)
        lab.stop('client')
        stopped = snapshot()
        with scout_peer_primary():
            primary_absent = lab.owned_process('client') is None
        checks = {'scout_launcher_absent': lab.owned_process('client') is None, 'owned_game_absent': gone(game, ticks),
            'all_retained_saved_state': stopped == after,
            'all_characters_offline': all(v['native']['online'] == 0 for v in stopped.values()),
            'primary_still_stopped': primary_absent and stopped['1'] == stop['after'],
            'native_lifetime': identity('worldserver') == ready['runtime']['worldserver'],
            'bridge_lifetime': identity('modern_world') == ready['runtime']['modern_world'],
            'origin_registration': registration() == t.fixture}
        t.receipt.update(after=stopped, shutdown_checks=checks)
        require(all(v is True for v in checks.values()), 'occupied swap scout shutdown preservation differs')
        t.receipt.update(completed=True, phase='bags_swap_closed_paused')
    finally:
        t.receipt['stop_finished_at'] = time.time()
        t.persist()


@contextmanager
def scout_peer_primary():
    previous = os.environ.get('CLIENT442_ACTOR')
    os.environ['CLIENT442_ACTOR'] = 'primary'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('CLIENT442_ACTOR', None)
        else:
            os.environ['CLIENT442_ACTOR'] = previous


def execute_trial(t, operation):
    """Keep the first closed failure, including interrupts, and any sealed entry."""
    try:
        return operation()
    except BaseException as error:
        t.receipt.update(completed=False, failure=t.receipt.get('failure') or f'{type(error).__name__}: {error}')
        if not isinstance(error, Exception):
            raise
    finally:
        t.receipt.setdefault('finished_at', time.time())
        t.persist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'capture', 'lobby', 'finish', 'precision', 'enter',
        'park', 'park-recovery', 'close-pause', 'pause-recovery'])
    parser.add_argument('--output', type=Path, required=True)
    for name in ('resume', 'closure', 'remote', 'checkpoint', 'review', 'source',
        'preparation', 'entry', 'operation', 'park', 'precision', 'before-precision', 'after-precision'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--stage', choices=['dismiss', 'reconnect', 'realm', 'character'])
    a = parser.parse_args()
    with scout():
        if a.action == 'start':
            require(all(getattr(a, k) for k in ('resume', 'closure', 'remote', 'checkpoint')),
                'start requires actual closed UI171 remote authority')
            start(a.resume, a.output, a.closure, a.remote, a.checkpoint)
            return
        from .interaction_trial import Trial
        t = Trial(a.output, controller='code', chat_key_hold=1.2, chat_open_retry=True)
        from .bag_swap_projection import source_identities
        t.receipt['committed_sources'] = source_identities(lab.REPO)
        t.receipt.update(controller='code', custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY,
            qualification_added=False, input_sent=False, mutation_sent=False)
        def run():
            if a.action == 'capture': capture(t, a.resume)
            elif a.action == 'lobby': lobby(t, a.resume, a.review, a.stage)
            elif a.action == 'finish': finish(t, a.resume, a.review)
            elif a.action == 'precision': precision(t, a.source)
            elif a.action == 'enter': enter(t, a.preparation, a.precision, a.review)
            elif a.action in ('park', 'park-recovery'): park(t, a.preparation, a.source, recovery=a.action == 'park-recovery')
            elif a.action == 'pause-recovery': pause_recovery(t, a.preparation, a.park, a.before_precision, a.after_precision, a.review)
            else: close_pause(t, a.preparation, a.entry, a.operation, a.park, a.before_precision, a.after_precision,
                a.review)
        execute_trial(t, run)
        print(json.dumps({k: t.receipt.get(k) for k in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
