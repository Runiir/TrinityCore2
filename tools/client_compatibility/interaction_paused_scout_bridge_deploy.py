"""Deploy from a closed resource pause and reconnect only the owned scout."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity,shot
from .interaction_retained_class_fixture import closed
from .interaction_parked_client_resource_pause import snapshot,gone
from .interaction_hunter_stable_slots import bound
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .interaction_offline_bridge_deploy import review
from .observation.journal import latest
from .world import control


SCHEMA='client442_resource_paused_scout_deployment_v1'


def absent():
    for name in ('primary','scout'):
        with actor(name):
            if lab.owned_process('client'):raise RuntimeError('both owned clients must remain stopped')


def primary_absent():
    with actor('primary'):
        if lab.owned_process('client'):raise RuntimeError('user-stopped primary must remain stopped')


def pause_source(path):
    e=closed(path);stop=closed(Path(e.get('primary_stop_source',{}).get('path','')))
    if (e.get('phase')!='parked_scout_resource_paused' or e.get('actor',{}).get('guid')!=2 or
        len(e.get('checks',{}))!=8 or not all(e['checks'].values()) or e.get('before')!=e.get('after') or
        e.get('primary_stop_source')!=bound(Path(e['primary_stop_source']['path'])) or
        stop.get('phase')!='user_requested_primary_client_stopped' or
        len(stop.get('checks',{}))!=8 or not all(stop['checks'].values()) or
        stop.get('before')!=stop.get('after') or e['after'].get('1')!=stop['after'] or
        set(e['after'])!={'1','2','3','4','5','6'} or
        any(v['native']['online']!=0 for v in e['after'].values())):
        raise RuntimeError('requires the whole six-character pause and bound primary stop')
    return e


def tests_source(path,build):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink():raise ValueError('requires owned test evidence')
    d=json.loads(path.read_text())
    if (d.get('schema')!='client442_bridge_candidate_tests_v1' or d.get('completed') is not True or
        d.get('build')!=build or set(d.get('runs',{}))!={'abandon','full_bridge'}):
        raise RuntimeError('candidate has no complete source-bound protocol and bridge test receipt')
    for row in d['runs'].values():
        log=Path(row.get('path','')).resolve()
        if (not log.is_relative_to(path.parent) or log.is_symlink() or row.get('exit_code')!=0 or
            row.get('passed',0)<=0 or not log.is_file() or row.get('sha256')!=lab.sha256(log) or
            f"{row['passed']} passed" not in log.read_text()):
            raise RuntimeError('candidate test log differs')
    return d


def persist(directory,report):
    lab.private_write(directory/'deployment.json',json.dumps(report,indent=2)+'\n')


def install(directory,pause_path,tests_path):
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    e=pause_source(pause_path);absent();_,build=control.native_command();tests_source(tests_path,build)
    baseline=snapshot();native=identity('worldserver');before=identity('modern_world')
    if (baseline!=e['after'] or native!=e['runtime']['worldserver'] or
        before!=e['runtime']['modern_world'] or not gone(e['game_before']['pid'],e['game_before']['start_ticks']) or
        actors.load()!=e['actor']):raise RuntimeError('closed resource pause state or lifetime differs')
    report={'schema':SCHEMA,'started_at':time.time(),'source':bound(pause_path),
        'tests_source':bound(tests_path),'primary_stop_source':e['primary_stop_source'],
        'native':native,'before':before,'previous_scout':e['runtime']['client'],
        'offline_baselines':baseline,'origin_actor':e['actor'],'build':build,
        'primary_stopped':True,'parked_scout':True,'input_sent':False,'qualification_added':False,
        'custom_script_permission':'blocked_by_user','softTargetInteract':SCRIPT_BOUNDARY,'completed':False}
    persist(directory,report)
    try:
        lab.stop('modern_world');control.start();report['after']=identity('modern_world');absent()
        checks={'native_unchanged':identity('worldserver')==native,'new_bridge':report['after']!=before,
            'compiled_candidate':report['after'].get('build')==build,'all_saved_state':snapshot()==baseline}
        report.update(installation_checks=checks,native_unchanged=checks['native_unchanged'],installed=all(checks.values()))
        if not report['installed']:raise RuntimeError('paused deployment preservation differs')
    except Exception as error:report['failure']=f'{type(error).__name__}: {error}';raise
    finally:persist(directory,report)


def current(directory,require_client=False):
    report=json.loads((directory/'deployment.json').read_text());e=pause_source(Path(report['source']['path']))
    if report.get('schema')=='client442_stopped_native_tame_deployment_v1':
        from .interaction_stopped_native_tame_deploy import current as native_current
        return native_current(directory,require_client)
    primary_absent()
    if (report.get('schema')!=SCHEMA or report.get('source')!=bound(Path(report['source']['path'])) or
        report.get('primary_stop_source')!=e['primary_stop_source'] or report.get('installed') is not True or
        report.get('failure') or len(report.get('installation_checks',{}))!=4 or
        not all(report['installation_checks'].values()) or report.get('native')!=e['runtime']['worldserver'] or
        report.get('before')!=e['runtime']['modern_world'] or report.get('previous_scout')!=e['runtime']['client'] or
        report.get('after',{}).get('build')!=report.get('build') or
        report.get('offline_baselines')!=e['after'] or snapshot()!=e['after'] or actors.load()!=e['actor'] or
        identity('worldserver')!=report['native'] or identity('modern_world')!=report['after']):
        raise RuntimeError('resource-paused deployment state or source differs')
    tests_path=Path(report['tests_source']['path'])
    if bound(tests_path)!=report['tests_source']:raise RuntimeError('candidate test receipt changed')
    tests_source(tests_path,report['build'])
    if require_client and identity('client')!=report.get('scout_lifetime'):
        raise RuntimeError('restarted scout lifetime differs')
    return report


def launch(directory,output):
    report=current(directory);absent()
    available=next(int(line.split()[1]) for line in open('/proc/meminfo') if line.startswith('MemAvailable:'))
    if available<6*1024*1024:raise RuntimeError('scout relaunch requires at least6GiB available memory')
    from .auth import accounts,control as auth
    credentials=json.loads((lab.client_root()/'secrets/game_account.json').read_text())
    account=accounts.check_password(credentials['username'],credentials['password'])
    if not account:raise RuntimeError('owned scout local SSO account is unavailable')
    auth.launch('launcher',accounts.issue(account,'launcher'),account['login'])
    try:
        report['scout_lifetime']=identity('client');monitor=owned_input.focus()
        if (report['scout_lifetime']==report['previous_scout'] or
            not monitor.get('second_monitor_verified') or monitor.get('monitor',{}).get('name')!='HDMI-1' or
            monitor['input_isolation'].get('actor')!='scout' or
            monitor['input_isolation'].get('host_activation_sent') is not False):
            raise RuntimeError('restarted scout must be verified on HDMI-1 with private input')
        report.update(launch_available_memory_kib=available,launch_monitor=monitor)
        persist(directory,report);current(directory,True)
        t=Trial(output,controller='code')
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        capture(t,directory)
        t.receipt['finished_at']=time.time();t.persist()
    except Exception:
        lab.stop('client');raise


def capture(t,directory):
    report=current(directory,True)
    t.receipt.update(deployment=bound(directory/'deployment.json'),parked_snapshot=report['offline_baselines']['2'],
        all_offline_snapshot=report['offline_baselines'],frame=shot(t.out/'screen.png'),completed=True,
        input_sent=False,qualification_added=False,qualified_scope='Owned scout lobby inspection; primary remains stopped.')


def lobby(t,directory,review_path,stage):
    current(directory,True)
    name={'dismiss':'Okay','reconnect':'Reconnect','realm':'Client442 Lab','character':'Harnesstwo'}[stage]
    d,_=review(t,review_path,name);point=d.get('point',[])
    if len(point)!=2 or any(type(v) is not int for v in point) or not (0<=point[0]<1280 and 0<=point[1]<720):
        raise RuntimeError('reviewed stock lobby control has no bounded point')
    if stage=='character' and not (1040<=point[0]<1280 and 70<=point[1]<560):
        raise RuntimeError('character selection must be inside the roster')
    if stage=='realm' and d.get('confirm_selected_realm') is not True:raise RuntimeError('realm selection review required')
    t.receipt.update(input_sent=True,stage=stage,ordinary_input={'point':point,'hold':1.2});t.persist()
    if stage=='dismiss':t.io.key('Return',hold=1.2)
    else:
        t.io.click(*point,hold=1.2)
        if stage=='realm':time.sleep(1.2);t.io.key('Return',hold=1.2)
    time.sleep(12);current(directory,True)
    t.receipt.update(frame=shot(t.out/'next_screen.png'),completed=True,requires_next_screen_review=True)


def finish(t,directory,review_path):
    report=current(directory,True);d,_=review(t,review_path,'Harnesstwo')
    if (d.get('selected_character'),d.get('selected_level'))!=('Harnesstwo',1):
        raise RuntimeError('requires freshly reviewed original scout selection')
    authenticated=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('event')=='world_authenticated' and
        r.get('account_id')==2 and r.get('time',0)>=report['started_at'])
    if not authenticated:raise RuntimeError('new scout realm authentication is absent')
    session=authenticated['session']
    enumeration=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
        r.get('name')=='SMSG_ENUM_CHARACTERS_RESULT' and r.get('direction')=='to_client')
    entered=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
        r.get('event') in ('native_player_created','world_connection_closed','native_stream_closed'))
    if not enumeration or entered:raise RuntimeError('scout entered the world or lost its fresh realm connection')
    checks=dict.fromkeys(('native_unchanged','new_scout_lifetime','fresh_owned_selection_review',
        'new_realm_enumeration','no_world_entry','all_six_saved_state','primary_stopped'),True)
    t.receipt.update(restoration_checks=checks,parked_native=report['offline_baselines']['2']['native'],
        all_offline_snapshot=report['offline_baselines'],session=session,input_sent=False,
        completed=True,frame=shot(t.out/'restored_selection.png'),phase='single_scout_parked_reconnected')
    return report,session


def join(t,directory,result):
    report,session=result;path=t.out/'episode.json';closed(path)
    if current(directory,True)!=report:raise RuntimeError('deployment changed before closed scout join')
    report.update(completed=True,finished_at=time.time(),parked_reconnect_attempt={
        'scout':{'completed':True,'failure':None,'episode':str(path),'sha256':lab.sha256(path),'session':session}})
    persist(directory,report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['install','launch','capture','lobby','finish'])
    p.add_argument('--deployment',type=Path,required=True);p.add_argument('--output',type=Path)
    p.add_argument('--pause',type=Path);p.add_argument('--tests',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--stage',choices=['dismiss','reconnect','realm','character']);a=p.parse_args()
    with actor('scout'):
        if a.action=='install':
            if not a.pause or not a.tests:p.error('install requires pause and candidate tests')
            install(a.deployment,a.pause,a.tests)
        elif a.action=='launch':
            if not a.output:p.error('launch requires output')
            launch(a.deployment,a.output)
        else:
            if not a.output:p.error('requires output')
            if a.action in ('lobby','finish') and not a.review:p.error('requires fresh review')
            if a.action=='lobby' and not a.stage:p.error('requires stage')
            t=Trial(a.output,controller='code');result=None
            t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
            try:
                if a.action=='capture':capture(t,a.deployment)
                elif a.action=='lobby':lobby(t,a.deployment,a.review,a.stage)
                else:result=finish(t,a.deployment,a.review)
            except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
            finally:t.receipt['finished_at']=time.time();t.persist()
            if result and t.receipt['completed']:join(t,a.deployment,result)
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
