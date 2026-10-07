"""Resume one scout at a verified offline fixture without restarting servers."""
import argparse
import json
import time
from pathlib import Path
from . import actors, lab_runtime as lab, owned_input
from .interaction_bridge_deploy import identity, shot
from .interaction_hunter_stable_slots import bound
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY, origin_checks
from .interaction_hunter_fixture import protected
from .interaction_parked_client_resource_pause import snapshot, gone
from .interaction_retained_class_fixture import closed
from .interaction_single_scout_bridge_deploy import primary_stopped, review
from .interaction_social import actor
from .interaction_trial import Trial
from .observation.journal import latest
from .review_hunter_revive_prerequisites import absent_clients
from .hunter_revive_fixture import dead_snapshot


def persist(directory, report):
    lab.private_write(directory / 'resume.json', json.dumps(report, indent=2) + '\n')


def start(directory, output, fixture_path):
    fixture = closed(fixture_path)
    if (fixture.get('phase') != 'owned_revive_dead_fixture_staged' or
        len(fixture.get('checks', {})) != 7 or not all(fixture['checks'].values()) or
        fixture.get('after') != dead_snapshot(fixture.get('before', {}))):
        raise RuntimeError('requires the exact staged disposable-pet fixture')
    primary = Path(fixture['primary_stop_source']['path'])
    primary_stopped(primary)
    absent_clients()
    pause = closed(Path(fixture['sources'][0]['path']))
    old = closed(Path(fixture['sources'][2]['path']))
    native, bridge = identity('worldserver'), identity('modern_world')
    if (native != fixture['runtime']['worldserver'] or bridge != fixture['runtime']['modern_world'] or
        snapshot() != fixture['after'] or actors.load() != old['origin_actor'] or
        old['origin_actor']['guid'] != 2 or not gone(pause['runtime']['client']['pid'], pause['runtime']['client']['start_ticks'])):
        raise RuntimeError('current offline fixture, registration or stopped scout differs')
    available = next(int(line.split()[1]) for line in open('/proc/meminfo') if line.startswith('MemAvailable:'))
    if available < 6 * 1024 * 1024:
        raise RuntimeError('one scout launch requires6GiB available memory')
    for path in (directory, output):
        if path.exists() or not path.resolve().is_relative_to(lab.ROOT / 'evidence'):
            raise ValueError('requires new private resume and output directories')
        path.mkdir(parents=True, mode=0o700)
    report = {'schema': 'client442_paused_scout_fixture_resume_v1', 'started_at': time.time(),
        'fixture_source': bound(fixture_path), 'preparation_source': fixture['sources'][2],
        'primary_stop_source': fixture['primary_stop_source'], 'previous_runtime': pause['runtime'],
        'offline_baselines': fixture['after'], 'origin_actor': old['origin_actor'], 'class_actor': old['class_actor'],
        'available_memory_kib_before': available, 'installed': False, 'completed': False,
        'input_sent': False, 'qualification_added': False, 'failure': None}
    persist(directory, report)
    try:
        from .auth import accounts, control as auth
        credentials = json.loads((lab.client_root() / 'secrets/game_account.json').read_text())
        account = accounts.check_password(credentials['username'], credentials['password'])
        if not account:
            raise RuntimeError('owned scout local SSO account unavailable')
        auth.launch('launcher', accounts.issue(account, 'launcher'), account['login'])
        runtime = {k: identity(k) for k in ('worldserver', 'modern_world', 'client')}
        monitor = owned_input.focus()
        checks = {'native_unchanged': runtime['worldserver'] == native,
            'bridge_unchanged': runtime['modern_world'] == bridge,
            'fresh_scout': runtime['client'] != pause['runtime']['client'],
            'all_six_saved_snapshots': snapshot() == fixture['after'],
            'primary_stopped': bool(primary_stopped(primary)),
            'HDMI_1': monitor['second_monitor_verified'] and monitor['monitor']['name'] == 'HDMI-1',
            'private_input': monitor['input_isolation']['actor'] == 'scout' and monitor['input_isolation']['host_activation_sent'] is False}
        report.update(runtime=runtime, launch_monitor=monitor, checks=checks, installed=all(checks.values()))
        if not report['installed']:
            raise RuntimeError('one scout resume preservation or HDMI-1 verification differs')
        report['frame'] = shot(output / 'launched.png')
    except Exception as error:
        report['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['launch_finished_at'] = time.time()
        persist(directory, report)
    print(json.dumps({'installed': True, 'runtime': report['runtime'], 'frame': report['frame']}), flush=True)


def current(t, directory):
    report = json.loads((directory / 'resume.json').read_text())
    fixture_path = Path(report['fixture_source']['path'])
    fixture = closed(fixture_path)
    primary_stopped(Path(report['primary_stop_source']['path']))
    if (report.get('schema') != 'client442_paused_scout_fixture_resume_v1' or
        report.get('installed') is not True or report.get('failure') is not None or
        len(report.get('checks', {})) != 7 or not all(report['checks'].values()) or
        report['fixture_source'] != bound(fixture_path) or
        report['offline_baselines'] != fixture['after'] or report['runtime'] != t.receipt['runtime'] or
        t.fixture != report['origin_actor'] or snapshot() != report['offline_baselines']):
        raise RuntimeError('source-bound resumed scout or exact offline snapshots differ')
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
    if len(point) != 2 or any(type(p) is not int for p in point) or not (0 <= point[0] < 1280 and 0 <= point[1] < 720):
        raise RuntimeError('bounded reviewed lobby point differs')
    if stage == 'character' and not (1040 <= point[0] < 1280 and 70 <= point[1] < 560):
        raise RuntimeError('reviewed roster point differs')
    if stage == 'realm' and checked.get('confirm_selected_realm') is not True:
        raise RuntimeError('reviewed realm confirmation missing')
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
    if (checked.get('selected_character'), checked.get('selected_level')) != ('Harnesstwo', 1):
        raise RuntimeError('reviewed original selection differs')
    auth = latest(lab.ROOT / 'logs/modern_world.jsonl', lambda r: r.get('event') == 'world_authenticated' and
        r.get('account_id') == 2 and r.get('time', 0) >= report['started_at'])
    if not auth:
        raise RuntimeError('fresh scout realm authentication absent')
    session = auth['session']
    enum = latest(lab.ROOT / 'logs/modern_world.jsonl', lambda r: r.get('session') == session and
        r.get('name') == 'SMSG_ENUM_CHARACTERS_RESULT' and r.get('direction') == 'to_client')
    loss = latest(lab.ROOT / 'logs/modern_world.jsonl', lambda r: r.get('session') == session and
        r.get('event') in ('native_player_created', 'world_connection_closed', 'native_stream_closed'))
    if not enum or loss:
        raise RuntimeError('fresh scout selection connection differs')
    t.receipt.update(checks={'original_selection': True, 'fresh_enumeration': True, 'all_six_offline': True},
        frame=shot(t.out / 'original_restored.png'), completed=True, input_sent=False,
        phase='paused_scout_fixture_parked_restored', native_session=session)
    return report


def prepare(t, directory):
    report = current(t, directory)
    restored = closed(Path(report['restoration_source']['path']))
    old = closed(Path(report['preparation_source']['path']))
    if (report.get('completed') is not True or report['restoration_source'] != bound(Path(report['restoration_source']['path'])) or
        restored.get('phase') != 'paused_scout_fixture_parked_restored' or restored.get('runtime') != t.receipt['runtime']):
        raise RuntimeError('resumed scout original selection has not closed')
    hunter = report['offline_baselines']['6']
    checks = {**origin_checks({**old, 'runtime': t.receipt['runtime']}), **protected(old)}
    if not all(checks.values()):
        raise RuntimeError('protected actors changed during offline scout resume')
    t.receipt.update(origin_actor=old['origin_actor'], origin_native=old['origin_native'], origin_saved=old['origin_saved'],
        origin_roster=old['origin_roster'], class_actor=old['class_actor'], natural_native=hunter['native'],
        natural_saved=hunter['saved'], retained_class_pets=hunter['pets'], protected_baseline=old['protected_baseline'],
        fixture_source=report['fixture_source'], sources=[bound(directory / 'resume.json'), report['restoration_source']],
        checks=checks, input_sent=False, qualification_added=False)
    t.persist()
    if actors.register(6) != old['class_actor']:
        raise RuntimeError('retained Hunter registration differs')
    t.receipt.update(completed=True, phase='await_owned_class_lobby_review', frame=shot(t.out / 'owned_lobby.png'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'capture', 'lobby', 'finish', 'prepare'])
    for key in ('output', 'resume'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--stage', choices=['dismiss', 'reconnect', 'realm', 'character'])
    args = parser.parse_args()
    with actor('scout'):
        if args.action == 'start':
            start(args.resume, args.output, args.fixture)
        else:
            trial = Trial(args.output, controller='code')
            trial.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
            result = None
            try:
                if args.action == 'capture': capture(trial, args.resume)
                elif args.action == 'lobby': lobby(trial, args.resume, args.review, args.stage)
                elif args.action == 'finish': result = finish(trial, args.resume, args.review)
                else: prepare(trial, args.resume)
            except Exception as error:
                trial.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
            finally:
                trial.receipt['finished_at'] = time.time()
                trial.persist()
            if result and trial.receipt['completed']:
                result.update(completed=True, finished_at=time.time(), restoration_source=bound(trial.out / 'episode.json'))
                persist(args.resume, result)
            print(json.dumps({k: trial.receipt.get(k) for k in ('completed', 'phase', 'failure')}), flush=True)
