"""Replace only the bridge at a closed six-character boundary; retain the scout."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity,shot
from .interaction_retained_class_fixture import closed
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .interaction_offline_bridge_deploy import review
from .interaction_parked_client_resource_pause import snapshot
from .interaction_hunter_stable_slots import bound
from .interaction_primary_combat_reentry import retained
from .observation.journal import latest
from .world import control

SCHEMA='client442_single_scout_bridge_deployment_v1'


def primary_stopped(path):
    stop=closed(path)
    if (stop.get('phase')!='user_requested_primary_client_stopped' or len(stop.get('checks',{}))!=8 or
        not all(stop['checks'].values()) or stop.get('before')!=stop.get('after')):
        raise RuntimeError('requires the exact successful primary stop')
    with actor('primary'):
        if lab.owned_process('client') or retained(1,1)!=stop['after']:
            raise RuntimeError('primary must remain stopped and completely unchanged')
    return stop


def boundary(t,path,primary):
    e=closed(path);stop=primary_stopped(primary)
    if (e.get('phase')!='owned_tame_diagnostic_parked_boundary' or len(e.get('checks',{}))!=20 or
        not all(e['checks'].values()) or e.get('runtime')!=t.receipt['runtime'] or e.get('actor')!=t.fixture or
        t.fixture.get('guid')!=2 or e.get('primary_stop_source')!=bound(primary) or
        e['runtime']['worldserver']!=stop['runtime']['worldserver'] or
        set(e.get('all_offline_snapshot',{}))!={'1','2','3','4','5','6'} or
        any(v['native']['online']!=0 for v in e['all_offline_snapshot'].values()) or
        snapshot()!=e['all_offline_snapshot']):
        raise RuntimeError('requires the whole unchanged six-actor Tame parked boundary')
    if any((lab.ROOT/'run'/n).exists() for n in ('owned_pet_abandon_probe.json',
        'owned_tame_request_probe.json','owned_stable_request_probe.json')):
        raise RuntimeError('cannot deploy with an armed gameplay probe')
    return e


def tests(path,build):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink():raise ValueError('requires owned test evidence')
    d=json.loads(path.read_text())
    if (d.get('schema')!='client442_single_scout_candidate_tests_v1' or d.get('completed') is not True or
        d.get('build')!=build or set(d.get('runs',{}))!={'abandon_tame','full_bridge'}):
        raise RuntimeError('source-bound candidate tests are incomplete')
    for row in d['runs'].values():
        p=Path(row['path']).resolve()
        if (not p.is_relative_to(path.parent) or p.is_symlink() or row.get('exit_code')!=0 or
            row.get('passed',0)<=0 or lab.sha256(p)!=row.get('sha256') or
            f"{row['passed']} passed" not in p.read_text()):raise RuntimeError('candidate test log differs')


def capture_before(t,source,primary):
    e=boundary(t,source,primary)
    t.receipt.update(boundary_source=bound(source),primary_stop_source=bound(primary),
        parked_snapshot=e['all_offline_snapshot']['2'],all_offline_snapshot=e['all_offline_snapshot'],
        frame=shot(t.out/'screen.png'),input_sent=False,qualification_added=False,completed=True)


def persist(directory,d):lab.private_write(directory/'deployment.json',json.dumps(d,indent=2)+'\n')


def restart(t,directory,source,primary,review_path,tests_path):
    e=boundary(t,source,primary);_,build=control.native_command();tests(tests_path,build)
    d,screen=review(t,review_path,'Harnesstwo')
    if ((d.get('selected_character'),d.get('selected_level'))!=('Harnesstwo',1) or
        screen.get('boundary_source')!=bound(source) or screen.get('primary_stop_source')!=bound(primary) or
        screen.get('all_offline_snapshot')!=e['all_offline_snapshot']):
        raise RuntimeError('fresh original selection is not bound to the complete boundary')
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    report={'schema':SCHEMA,'started_at':time.time(),'boundary_source':bound(source),
        'primary_stop_source':bound(primary),'tests_source':bound(tests_path),'build':build,
        'native':identity('worldserver'),'before':identity('modern_world'),'scout_lifetime':identity('client'),
        'offline_baselines':e['all_offline_snapshot'],'origin_actor':t.fixture,'primary_stopped':True,
        'parked_scout':True,'parked_reconnect_attempt':{},'completed':False,'input_sent':False,
        'custom_script_permission':'blocked_by_user','softTargetInteract':SCRIPT_BOUNDARY}
    persist(directory,report)
    lab.stop('modern_world');control.start();report['after']=identity('modern_world')
    checks={'native_unchanged':identity('worldserver')==report['native'],
        'scout_lifetime_unchanged':identity('client')==report['scout_lifetime'],
        'new_bridge':report['after']!=report['before'],'candidate_build':report['after'].get('build')==build,
        'six_offline_snapshots':snapshot()==report['offline_baselines'],'primary_stopped':bool(primary_stopped(primary))}
    report.update(installation_checks=checks,installed=all(checks.values()));persist(directory,report)
    t.receipt.update(deployment_source=bound(directory/'deployment.json'),checks=checks,completed=all(checks.values()))
    if not all(checks.values()):raise RuntimeError('single-scout bridge replacement preservation differs')


def verified_report(directory,runtime):
    d=json.loads((directory/'deployment.json').read_text())
    if any(not isinstance(d.get(k),dict) or not d[k].get('path') or not d[k].get('sha256') for k in
        ('boundary_source','primary_stop_source','tests_source')):
        raise RuntimeError('single-scout source references are incomplete')
    source=Path(d['boundary_source']['path'])
    e=closed(source);stop=primary_stopped(Path(d['primary_stop_source']['path']))
    if (d.get('schema')!=SCHEMA or d.get('boundary_source')!=bound(source) or
        d.get('primary_stop_source')!=e.get('primary_stop_source') or
        e.get('phase')!='owned_tame_diagnostic_parked_boundary' or len(e.get('checks',{}))!=20 or
        not all(e['checks'].values()) or e.get('actor',{}).get('guid')!=2 or
        set(e.get('all_offline_snapshot',{}))!={'1','2','3','4','5','6'} or
        any(v['native']['online']!=0 for v in e['all_offline_snapshot'].values()) or
        set(d.get('parked_reconnect_attempt',{}))-{'scout'} or d.get('installed') is not True or
        len(d.get('installation_checks',{}))!=6 or not all(d['installation_checks'].values()) or
        d.get('offline_baselines')!=e.get('all_offline_snapshot') or
        d.get('native')!=e['runtime']['worldserver'] or d['native']!=stop['runtime']['worldserver'] or
        runtime['worldserver']!=d['native'] or runtime['modern_world']!=d.get('after') or
        d['before']!=e['runtime']['modern_world'] or d['after']==d['before'] or
        d['after'].get('build')!=d.get('build') or runtime['client']!=d.get('scout_lifetime') or
        d['scout_lifetime']!=e['runtime']['client']):
        raise RuntimeError('single-scout deployment lineage differs')
    tests_path=Path(d['tests_source']['path'])
    if bound(tests_path)!=d['tests_source']:raise RuntimeError('candidate test receipt changed')
    tests(tests_path,d['build']);return d


def current(t,directory):
    d=verified_report(directory,t.receipt['runtime'])
    if actors.load()!=d['origin_actor'] or snapshot()!=d['offline_baselines']:
        raise RuntimeError('single-scout complete offline state differs')
    return d


def capture(t,directory):
    d=current(t,directory)
    t.receipt.update(deployment_source=bound(directory/'deployment.json'),parked_snapshot=d['offline_baselines']['2'],
        all_offline_snapshot=d['offline_baselines'],frame=shot(t.out/'screen.png'),input_sent=False,completed=True)


def lobby(t,directory,path,stage):
    current(t,directory);control_name={'dismiss':'Okay','reconnect':'Reconnect','realm':'Client442 Lab','character':'Harnesstwo'}[stage]
    d,_=review(t,path,control_name);point=d.get('point',[])
    if len(point)!=2 or any(type(v) is not int for v in point) or not (0<=point[0]<1280 and 0<=point[1]<720):
        raise RuntimeError('requires the reviewed bounded lobby point')
    if stage=='character' and not (1040<=point[0]<1280 and 70<=point[1]<560):raise RuntimeError('roster point differs')
    if stage=='realm' and d.get('confirm_selected_realm') is not True:raise RuntimeError('reviewed realm selection required')
    if stage=='dismiss':t.io.key('Return',hold=1.2)
    else:
        t.io.click(*point,hold=1.2)
        if stage=='realm':time.sleep(1.2);t.io.key('Return',hold=1.2)
    time.sleep(12);current(t,directory)
    t.receipt.update(input_sent=True,stage=stage,frame=shot(t.out/'next_screen.png'),completed=True)


def finish(t,directory,path):
    d=current(t,directory);r,_=review(t,path,'Harnesstwo')
    if (r.get('selected_character'),r.get('selected_level'))!=('Harnesstwo',1):raise RuntimeError('original selection differs')
    auth=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('event')=='world_authenticated' and
        r.get('account_id')==2 and r.get('time',0)>=d['started_at'])
    if not auth:raise RuntimeError('fresh scout authentication is missing')
    session=auth['session']
    enum=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
        r.get('name')=='SMSG_ENUM_CHARACTERS_RESULT' and r.get('direction')=='to_client')
    loss=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
        r.get('event') in ('native_player_created','world_connection_closed','native_stream_closed'))
    if not enum or loss:raise RuntimeError('scout enum/world-entry/connection boundary differs')
    checks=dict.fromkeys(('native_unchanged','scout_lifetime_unchanged','fresh_selection',
        'new_realm_enumeration','no_world_entry','all_six_offline_unchanged','primary_stopped'),True)
    t.receipt.update(restoration_checks=checks,session=session,all_offline_snapshot=d['offline_baselines'],
        frame=shot(t.out/'restored_selection.png'),completed=True,input_sent=False,
        phase='single_scout_bridge_parked_reconnected')
    return d,session


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['before','restart','capture','lobby','finish'])
    p.add_argument('--output',type=Path,required=True)
    for name in ('source','primary-stop','review','tests','deployment'):p.add_argument('--'+name,type=Path)
    p.add_argument('--stage',choices=['dismiss','reconnect','realm','character']);a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');result=None
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='before':capture_before(t,a.source,a.primary_stop)
            elif a.action=='restart':restart(t,a.deployment,a.source,a.primary_stop,a.review,a.tests)
            elif a.action=='capture':capture(t,a.deployment)
            elif a.action=='lobby':lobby(t,a.deployment,a.review,a.stage)
            else:result=finish(t,a.deployment,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        if result and t.receipt['completed']:
            d,session=result;d['parked_reconnect_attempt']['scout']={'completed':True,'session':session,
                'episode':str(t.out/'episode.json'),'sha256':lab.sha256(t.out/'episode.json')}
            d.update(completed=True,finished_at=time.time());persist(a.deployment,d)
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
