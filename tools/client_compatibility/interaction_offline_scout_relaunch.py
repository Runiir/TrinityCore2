"""Replace a stuck scout only after proving no character login and unchanged data."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity,shot
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY,origin_checks
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .interaction_parked_client_resource_pause import snapshot,gone
from .interaction_single_scout_bridge_deploy import primary_stopped,verified_report,review
from .observation.journal import entries,latest

SCHEMA='client442_no_login_scout_relaunch_v1'


def no_login(failed,preparation,fixture,runtime,events):
    if (failed.get('completed') is not False or not failed.get('finished_at') or
        failed.get('failure')!='RuntimeError: UI observation did not become decodable' or
        failed.get('phase')!='owned_class_entry_started' or failed.get('actor')!=fixture or
        failed.get('runtime')!=runtime or failed.get('fixture_source')!=preparation or
        any(r.get('name')=='CMSG_PLAYER_LOGIN' or r.get('event')=='native_player_created' for r in events) or
        not any(r.get('event')=='native_stream_closed' for r in events)):
        raise RuntimeError('requires the exact closed no-login failure; no replay or online restart')


def persist(directory,d):lab.private_write(directory/'relaunch.json',json.dumps(d,indent=2)+'\n')


def start(t,directory,preparation,failed_path,deployment):
    failed_path=failed_path.resolve()
    if (failed_path.name!='episode.json' or not failed_path.is_relative_to(lab.ROOT/'evidence') or
        failed_path.is_symlink()):raise ValueError('requires an owned closed failed entry')
    old=closed(preparation);failed=json.loads(failed_path.read_text());d=verified_report(deployment,t.receipt['runtime'])
    events=[{k:r.get(k) for k in ('time','event','name','session','direction','bytes')} for r in
        entries(lab.ROOT/'logs/modern_world.jsonl') if failed['started_at']<=r.get('time',0)<=failed['finished_at'] and
        (r.get('event') in ('native_player_created','native_stream_closed','world_connection_closed') or
            r.get('name') in ('CMSG_PLAYER_LOGIN','CMSG_LOADING_SCREEN_NOTIFY','CMSG_GET_ACCOUNT_CHARACTER_LIST'))]
    no_login(failed,bound(preparation),t.fixture,t.receipt['runtime'],events)
    before=snapshot();primary=Path(d['primary_stop_source']['path']);primary_stopped(primary)
    if (t.fixture!=old.get('class_actor') or t.fixture.get('guid')!=6 or d.get('completed') is not True or
        old.get('runtime')!=t.receipt['runtime'] or before!=d['offline_baselines'] or
        before['6']['native']!=old['natural_native'] or before['6']['saved']!=old['natural_saved'] or
        before['6']['pets']!=old['retained_class_pets'] or any(v['native']['online']!=0 for v in before.values())):
        raise RuntimeError('stuck client must have all six complete offline snapshots unchanged')
    available=next(int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable:'))
    if available<6*1024*1024:raise RuntimeError('scout replacement requires6GiB available memory')
    monitor=owned_input.focus();game=monitor['input_isolation']['game_pid'];ticks=lab.proc_start(game)
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    report={'schema':SCHEMA,'started_at':time.time(),'preparation_source':bound(preparation),
        'failed_entry_source':bound(failed_path),'deployment_source':bound(deployment/'deployment.json'),
        'primary_stop_source':bound(primary),'before_runtime':t.receipt['runtime'],'offline_baselines':before,
        'origin_actor':old['origin_actor'],'class_actor':old['class_actor'],'events':events,
        'old_game':{'pid':game,'start_ticks':ticks},'old_frame':shot(t.out/'stuck_loading.png'),
        'available_memory_kib_before':available,'input_sent':False,'completed':False}
    persist(directory,report);t.receipt.update(relaunch_source=bound(directory/'relaunch.json'),input_sent=False)
    t.persist();lab.stop('client')
    if not gone(game,ticks) or snapshot()!=before:raise RuntimeError('owned scout stop or offline preservation differs')
    if actors.register(2)!=old['origin_actor']:raise RuntimeError('original scout registration differs')
    from .auth import accounts,control as auth
    credentials=json.loads((lab.client_root()/'secrets/game_account.json').read_text())
    account=accounts.check_password(credentials['username'],credentials['password'])
    if not account:raise RuntimeError('owned scout local SSO account unavailable')
    launch_available=next(int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable:'))
    if launch_available<6*1024*1024:raise RuntimeError('scout launch requires6GiB available memory')
    auth.launch('launcher',accounts.issue(account,'launcher'),account['login'])
    after={k:identity(k) for k in ('worldserver','modern_world','client')};m=owned_input.focus()
    primary_stopped(primary)
    checks={'native_unchanged':after['worldserver']==report['before_runtime']['worldserver'],
        'bridge_unchanged':after['modern_world']==report['before_runtime']['modern_world'],
        'new_scout':after['client']!=report['before_runtime']['client'],'old_game_absent':gone(game,ticks),
        'all_six_saved_snapshots':snapshot()==before,'primary_stopped':True,
        'original_registration':actors.load()==old['origin_actor'],
        'HDMI_1':m['second_monitor_verified'] and m['monitor']['name']=='HDMI-1',
        'private_input':m['input_isolation']['actor']=='scout' and m['input_isolation']['host_activation_sent'] is False}
    report.update(after_runtime=after,launch_monitor=m,launch_available_memory_kib=launch_available,
        checks=checks,installed=all(checks.values()))
    persist(directory,report);t.receipt.update(checks=checks,completed=all(checks.values()),
        phase='owned_no_login_scout_replaced',new_runtime=after,qualification_added=False)
    if not all(checks.values()):raise RuntimeError('no-login single scout relaunch differs')


def current(t,directory):
    d=json.loads((directory/'relaunch.json').read_text());primary_stopped(Path(d['primary_stop_source']['path']))
    if (d.get('schema')!=SCHEMA or d.get('installed') is not True or len(d.get('checks',{}))!=9 or
        not all(d['checks'].values()) or t.receipt['runtime']!=d.get('after_runtime') or
        t.fixture!=d['origin_actor'] or actors.load()!=d['origin_actor'] or snapshot()!=d['offline_baselines']):
        raise RuntimeError('no-login relaunch lineage or complete offline state differs')
    return d


def capture(t,directory):
    d=current(t,directory)
    t.receipt.update(relaunch_source=bound(directory/'relaunch.json'),parked_snapshot=d['offline_baselines']['2'],
        all_offline_snapshot=d['offline_baselines'],frame=shot(t.out/'screen.png'),input_sent=False,completed=True)


def lobby(t,directory,path,stage):
    current(t,directory);name={'dismiss':'Okay','reconnect':'Reconnect','realm':'Client442 Lab','character':'Harnesstwo'}[stage]
    d,_=review(t,path,name);point=d.get('point',[])
    if len(point)!=2 or any(type(v) is not int for v in point) or not (0<=point[0]<1280 and 0<=point[1]<720):
        raise RuntimeError('requires a bounded reviewed lobby control')
    if stage=='realm' and d.get('confirm_selected_realm') is not True:raise RuntimeError('reviewed realm confirmation required')
    if stage=='character' and not (1040<=point[0]<1280 and 70<=point[1]<560):raise RuntimeError('roster point differs')
    if stage=='dismiss':t.io.key('Return',hold=1.2)
    else:
        t.io.click(*point,hold=1.2)
        if stage=='realm':time.sleep(1.2);t.io.key('Return',hold=1.2)
    time.sleep(12);current(t,directory)
    t.receipt.update(stage=stage,input_sent=True,frame=shot(t.out/'next_screen.png'),completed=True)


def finish(t,directory,path):
    d=current(t,directory);r,_=review(t,path,'Harnesstwo')
    if (r.get('selected_character'),r.get('selected_level'))!=('Harnesstwo',1):raise RuntimeError('original selection differs')
    auth=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('event')=='world_authenticated' and
        r.get('account_id')==2 and r.get('time',0)>=d['started_at'])
    if not auth:raise RuntimeError('fresh scout realm authentication absent')
    session=auth['session'];enum=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
        r.get('name')=='SMSG_ENUM_CHARACTERS_RESULT' and r.get('direction')=='to_client')
    loss=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
        r.get('event') in ('native_player_created','world_connection_closed','native_stream_closed'))
    if not enum or loss:raise RuntimeError('fresh scout selection connection boundary differs')
    t.receipt.update(restoration_checks=dict.fromkeys(('native_unchanged','bridge_unchanged','new_scout',
        'original_selection','six_offline_snapshots','primary_stopped','new_realm_enumeration'),True),
        session=session,frame=shot(t.out/'original_restored.png'),completed=True,input_sent=False,
        phase='owned_no_login_scout_restored')
    return d


def prepare(t,directory):
    d=current(t,directory);old=closed(Path(d['preparation_source']['path']));h=d['offline_baselines']['6']
    restored=closed(Path(d['restoration_source']['path']))
    if (d.get('completed') is not True or bound(Path(d['restoration_source']['path']))!=d['restoration_source'] or
        restored.get('phase')!='owned_no_login_scout_restored' or len(restored.get('restoration_checks',{}))!=7 or
        not all(restored['restoration_checks'].values())):raise RuntimeError('closed scout restoration missing')
    checks={**origin_checks(old),**protected(old),'all_offline_saved_state':True,'primary_stopped':True,'new_scout_restored':True}
    if not all(checks.values()):raise RuntimeError('protected actors differ after scout replacement')
    t.receipt.update(origin_actor=old['origin_actor'],origin_native=old['origin_native'],origin_saved=old['origin_saved'],
        origin_roster=old['origin_roster'],class_actor=old['class_actor'],natural_native=h['native'],natural_saved=h['saved'],
        retained_class_pets=h['pets'],protected_baseline=old['protected_baseline'],checks=checks,
        sources=[d['preparation_source'],d['failed_entry_source'],bound(directory/'relaunch.json'),d['restoration_source']],
        input_sent=False,qualification_added=False)
    t.persist()
    if actors.register(6)!=old['class_actor']:raise RuntimeError('retained Hunter registration differs')
    t.receipt.update(completed=True,phase='await_owned_class_lobby_review',frame=shot(t.out/'owned_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['start','capture','lobby','finish','prepare'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--relaunch',type=Path,required=True)
    for name in ('preparation','failed-entry','deployment','review'):p.add_argument('--'+name,type=Path)
    p.add_argument('--stage',choices=['dismiss','reconnect','realm','character']);a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');result=None
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='start':start(t,a.relaunch,a.preparation,a.failed_entry,a.deployment)
            elif a.action=='capture':capture(t,a.relaunch)
            elif a.action=='lobby':lobby(t,a.relaunch,a.review,a.stage)
            elif a.action=='finish':result=finish(t,a.relaunch,a.review)
            else:prepare(t,a.relaunch)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        if result and t.receipt['completed']:
            result.update(completed=True,finished_at=time.time(),restoration_source=bound(t.out/'episode.json'))
            persist(a.relaunch,result)
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
