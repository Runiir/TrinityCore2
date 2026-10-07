"""Resume one source-bound scout for ordinary1462 work, or pause its closure."""
import argparse
import json
from pathlib import Path
import time

from . import actors, lab_runtime as lab, owned_input
from .hunter_learn_contract import require
from .hunter_learn_sources import continuation, closed, linked, whole, private_json
from .interaction_bridge_deploy import identity, shot
from .interaction_hunter_stable_slots import bound
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY, origin_checks
from .interaction_parked_client_resource_pause import snapshot, gone
from .interaction_single_scout_bridge_deploy import primary_stopped, review
from .interaction_social import actor
from .interaction_trial import Trial
from .observation.journal import latest
from .review_hunter_revive_prerequisites import absent_clients

SCHEMA = 'client442_hunter_learn_scout_resume_v1'


def persist(directory, report):
    lab.private_write(directory / 'resume.json', json.dumps(report, indent=2) + '\n')


def source_report(report):
    refs = report['sources']
    require(len(refs) == 4, 'resume source chain differs')
    for ref in [*refs, report['remote_source']]:
        require(bound(Path(ref['path'])) == ref, 'resume authority digest changed')
    return continuation(*[Path(ref['path']) for ref in refs], Path(report['remote_source']['path']))


def start(directory, output, preparation, normalization, closure, pause, remote):
    source = continuation(preparation, normalization, closure, pause, remote)
    old, stopped = source['preparation'], source['pause']
    stop_path = Path(source['primary_stop_source']['path'])
    primary_stopped(stop_path)
    absent_clients()
    native, bridge = identity('worldserver'), identity('modern_world')
    require(native == stopped['runtime']['worldserver'] and bridge == stopped['runtime']['modern_world'] and
        snapshot() == source['snapshot'] and actors.load() == old['origin_actor'] and
        gone(stopped['runtime']['client']['pid'], stopped['runtime']['client']['start_ticks']) and
        gone(stopped['game_before']['pid'], stopped['game_before']['start_ticks']),
        'unchanged paused boundary, registration or both old scout processes differ')
    available = next(int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
        if line.startswith('MemAvailable:'))
    require(available >= 6 * 1024 * 1024, 'one scout launch requires6GiB available memory')
    for path in (directory, output):
        require(not path.exists() and path.resolve().is_relative_to(lab.ROOT / 'evidence'),
            'requires new private resume directories')
        path.mkdir(parents=True, mode=0o700)
    report = {'schema': SCHEMA, 'started_at': time.time(), 'sources': source['sources'],
        'remote_source': source['remote_source'], 'checkpoint_source': source['checkpoint_source'],
        'primary_stop_source': source['primary_stop_source'], 'previous_runtime': stopped['runtime'],
        'offline_baselines': source['snapshot'], 'origin_actor': old['origin_actor'], 'class_actor': old['class_actor'],
        'available_memory_kib_before': available, 'installed': False, 'completed': False, 'failure': None,
        'input_sent': False, 'qualification_added': False, 'controller': 'code', 'model': None}
    persist(directory, report)
    try:
        from .auth import accounts, control as auth
        credentials = json.loads((lab.client_root() / 'secrets/game_account.json').read_text())
        account = accounts.check_password(credentials['username'], credentials['password'])
        require(account, 'owned scout local SSO account unavailable')
        auth.launch('launcher', accounts.issue(account, 'launcher'), account['login'])
        runtime = {k: identity(k) for k in ('worldserver', 'modern_world', 'client')}
        monitor = owned_input.focus()
        checks = {'native_unchanged': runtime['worldserver'] == native, 'bridge_unchanged': runtime['modern_world'] == bridge,
            'fresh_scout': runtime['client'] != stopped['runtime']['client'],
            'all_six_saved_snapshots': snapshot() == source['snapshot'], 'primary_stopped': bool(primary_stopped(stop_path)),
            'HDMI_1': monitor['second_monitor_verified'] and monitor['monitor']['name'] == 'HDMI-1',
            'private_input': monitor['input_isolation']['actor'] == 'scout' and
                monitor['input_isolation']['host_activation_sent'] is False}
        report.update(runtime=runtime, launch_monitor=monitor, checks=checks, installed=all(checks.values()))
        require(report['installed'], 'fresh scout HDMI-1, private input or preservation differs')
        report['frame'] = shot(output / 'launched.png')
    except BaseException as error:
        report['completed'] = False
        report['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['launch_finished_at'] = time.time()
        persist(directory, report)


def current(t, directory):
    report = private_json(directory / 'resume.json', False)
    source = source_report(report)
    whole(report, 'checks', 7)
    require(report.get('schema') == SCHEMA and report.get('installed') is True and report.get('failure') is None and
        report.get('offline_baselines') == source['snapshot'] and report.get('runtime') == t.receipt['runtime'] and
        t.fixture == report.get('origin_actor') and actors.load() == t.fixture and
        snapshot() == report['offline_baselines'], 'current resumed scout or offline baseline differs')
    primary_stopped(Path(report['primary_stop_source']['path']))
    return report


def capture(t, directory):
    report = current(t, directory)
    t.receipt.update(resume_source=bound(directory / 'resume.json'), all_offline_snapshot=report['offline_baselines'],
        frame=shot(t.out / 'screen.png'), input_sent=False, completed=True)


def lobby(t, directory, review_path, stage):
    current(t, directory)
    control = {'dismiss': 'Okay', 'reconnect': 'Reconnect', 'realm': 'Client442 Lab', 'character': 'Harnesstwo'}[stage]
    checked, _ = review(t, review_path, control)
    point = checked.get('point', [])
    require(len(point) == 2 and all(type(p) is int for p in point) and 0 <= point[0] < 1280 and 0 <= point[1] < 720,
        'bounded reviewed lobby point differs')
    if stage == 'character':
        require(1040 <= point[0] < 1280 and 70 <= point[1] < 560, 'reviewed roster point differs')
    if stage == 'realm':
        require(checked.get('confirm_selected_realm') is True, 'reviewed realm confirmation missing')
    if stage == 'dismiss':
        t.io.key('Return', hold=1.2)
    else:
        t.io.click(*point, hold=1.2)
        if stage == 'realm':
            time.sleep(1.2)
            t.io.key('Return', hold=1.2)
    time.sleep(12)
    current(t, directory)
    t.receipt.update(stage=stage, input_sent=True, frame=shot(t.out / 'next_screen.png'), completed=True)


def finish(t, directory, review_path):
    report = current(t, directory)
    checked, _ = review(t, review_path, 'Harnesstwo')
    require((checked.get('selected_character'), checked.get('selected_level')) == ('Harnesstwo', 1),
        'reviewed original selection differs')
    authenticated = latest(lab.ROOT / 'logs/modern_world.jsonl', lambda r: r.get('event') == 'world_authenticated' and
        r.get('account_id') == 2 and r.get('time', 0) >= report['started_at'])
    require(authenticated, 'fresh scout authentication absent')
    session = authenticated['session']
    enum = latest(lab.ROOT / 'logs/modern_world.jsonl', lambda r: r.get('session') == session and
        r.get('name') == 'SMSG_ENUM_CHARACTERS_RESULT' and r.get('direction') == 'to_client')
    loss = latest(lab.ROOT / 'logs/modern_world.jsonl', lambda r: r.get('session') == session and
        r.get('event') in ('native_player_created', 'world_connection_closed', 'native_stream_closed'))
    require(enum and not loss, 'fresh original selection connection differs')
    t.receipt.update(checks={'original_selection': True, 'fresh_enumeration': True, 'all_six_offline': True},
        frame=shot(t.out / 'original_restored.png'), completed=True, input_sent=False,
        phase='hunter_learn_scout_original_restored', native_session=session, resume_source=bound(directory / 'resume.json'))
    return report


def prepare(t, directory):
    report = current(t, directory)
    restored = linked(report['restoration_source'])
    source = source_report(report)
    old = source['preparation']
    require(report.get('completed') is True and restored.get('phase') == 'hunter_learn_scout_original_restored' and
        restored.get('runtime') == t.receipt['runtime'] and restored.get('actor') == t.fixture and
        restored.get('native_session') == report.get('native_session') and
        report['launch_finished_at'] < restored['started_at'] < restored['finished_at'] <= report['finished_at'],
        'fresh original selection has not closed')
    whole(restored, 'checks', 3)
    baseline = report['offline_baselines']
    h = baseline['6']
    checks = origin_checks({**old, 'runtime': t.receipt['runtime']})
    checks.update({f'actor_{g}_unchanged': baseline[g] == source['snapshot'][g] for g in ('1', '2', '3', '4', '5')})
    require(all(checks.values()), 'protected actors changed during resume')
    t.receipt.update(origin_actor=old['origin_actor'], origin_native=baseline['2']['native'], origin_saved=baseline['2']['saved'],
        origin_roster=old['origin_roster'], class_actor=old['class_actor'], natural_native=h['native'], natural_saved=h['saved'],
        retained_class_pets=h['pets'], protected_baseline={g: baseline[g] for g in ('1', '2', '3', '4', '5')},
        learn_offline_baseline=baseline, accepted_previous_sources=report['sources'], remote_source=report['remote_source'],
        primary_stop_source=report['primary_stop_source'], sources=[bound(directory / 'resume.json'), report['restoration_source']],
        checks=checks, input_sent=False, qualification_added=False)
    t.persist()
    require(actors.register(6) == old['class_actor'], 'retained Hunter registration differs')
    t.receipt.update(completed=True, phase='await_owned_class_lobby_review', frame=shot(t.out / 'owned_lobby.png'))


def pause(t, source):
    from .hunter_learn_evidence import closure_checks
    e = closed(source)
    closure_checks(e)
    require(t.fixture.get('guid') == 2 and e['actor'] == t.fixture and e['runtime'] == t.receipt['runtime'] and
        actors.load() == t.fixture and snapshot() == e['all_offline_snapshot'], 'learning closure or original registration differs')
    stop = primary_stopped(Path(e['primary_stop_source']['path']))
    require(not any((lab.ROOT / 'run' / n).exists() for n in ('owned_pet_abandon_probe.json',
        'owned_tame_request_probe.json', 'owned_stable_request_probe.json', 'owned_entry_request_probe.json')),
        'cannot pause with an armed gameplay probe')
    before = snapshot()
    monitor = owned_input.focus()
    require(monitor['second_monitor_verified'] and monitor['monitor']['name'] == 'HDMI-1', 'owned scout must remain on HDMI-1')
    game = monitor['input_isolation']['game_pid']
    ticks = lab.proc_start(game)
    t.receipt.update(source=bound(source), primary_stop_source=e['primary_stop_source'], before=before,
        game_before={'pid': game, 'start_ticks': ticks}, frame=shot(t.out / 'scout_parked.png'), input_sent=False,
        qualification_added=False, action='stop_parked_scout_after_learning_restoration')
    t.persist()
    lab.stop('client')
    after = snapshot()
    with actor('primary'):
        primary_absent = lab.owned_process('client') is None
    checks = {'scout_launcher_absent': lab.owned_process('client') is None, 'owned_game_absent': gone(game, ticks),
        'all_retained_saved_state': before == after, 'all_characters_offline': all(v['native']['online'] == 0 for v in after.values()),
        'primary_still_stopped': primary_absent and after['1'] == stop['after'],
        'native_lifetime': identity('worldserver') == e['runtime']['worldserver'],
        'bridge_lifetime': identity('modern_world') == e['runtime']['modern_world'], 'origin_registration': actors.load() == t.fixture}
    t.receipt.update(after=after, checks=checks, completed=all(checks.values()), phase='hunter_learn_scout_resource_paused')
    require(all(checks.values()), 'learning scout shutdown preservation differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'capture', 'lobby', 'finish', 'prepare', 'pause'])
    parser.add_argument('--output', type=Path, required=True)
    for key in ('resume', 'preparation', 'normalization', 'closure', 'pause', 'remote', 'review', 'source'):
        parser.add_argument('--' + key, type=Path)
    parser.add_argument('--stage', choices=['dismiss', 'reconnect', 'realm', 'character'])
    a = parser.parse_args()
    with actor('scout'):
        if a.action == 'start':
            require(all(getattr(a, k) for k in ('resume', 'preparation', 'normalization', 'closure', 'pause', 'remote')),
                'start requires every accepted remote source')
            start(a.resume, a.output, a.preparation, a.normalization, a.closure, a.pause, a.remote)
            return
        t = Trial(a.output, controller='code')
        t.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
        result = None
        try:
            if a.action == 'capture': capture(t, a.resume)
            elif a.action == 'lobby': lobby(t, a.resume, a.review, a.stage)
            elif a.action == 'finish': result = finish(t, a.resume, a.review)
            elif a.action == 'prepare': prepare(t, a.resume)
            else: pause(t, a.source)
        except BaseException as error:
            t.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
            if not isinstance(error, Exception):
                raise
        finally:
            t.receipt['finished_at'] = time.time()
            t.persist()
        if result and t.receipt['completed']:
            result.update(completed=True, finished_at=time.time(), restoration_source=bound(t.out / 'episode.json'),
                native_session=t.receipt['native_session'])
            persist(a.resume, result)
        print(json.dumps({k: t.receipt.get(k) for k in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
