"""Deploy the owned bridge while both existing clients stay at character selection."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity,shot
from .interaction_owned_class_fixture import character,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_reentry import install_observer
from .observation.journal import latest
from .world import control


def native(t):
    if (t.fixture['actor'],t.fixture['guid'],t.fixture['character_name'],t.fixture['level']) not in (
        ('primary',1,'Harnessone',85),('scout',2,'Harnesstwo',1)):
        raise RuntimeError('requires the exact original owned offline actor')
    row=character(t.fixture['guid'],t.fixture['account_id'])
    if row['online']!=0:raise RuntimeError('owned actor must already be offline')
    return row


def snapshot(t):
    guid=t.fixture['guid']
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT ci.*,ii.* FROM client442_characters.character_inventory ci '
            'JOIN client442_characters.item_instance ii ON ii.guid=ci.item '
            'WHERE ci.guid=%s ORDER BY ci.bag,ci.slot',(guid,))
        inventory=json.loads(json.dumps(q.fetchall()))
    return {'native':native(t),'saved':saved(guid),'pets':pets(guid),'inventory':inventory}


def capture(t):
    t.receipt.update(parked_snapshot=snapshot(t),frame=shot(t.out/'screen.png'),completed=True,
        qualified_scope='Read-only owned offline screen and native-state inspection; no input or gameplay qualification.')


def review(t,path,control_name):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink():raise ValueError('requires an owned review')
    d=json.loads(path.read_text());source=Path(d.get('source',{}).get('path','')).resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json' or source.is_symlink():
        raise RuntimeError('review source is outside owned closed evidence')
    e=json.loads(source.read_text());f=d.get('frame',{});p=path.parent/f.get('file','');m=f.get('monitor',{})
    current=owned_input.focus()
    if (d.get('reviewed') is not True or d.get('control')!=control_name or
        d['source'].get('sha256')!=lab.sha256(source) or e.get('completed') is not True or
        e.get('failure') is not None or not e.get('finished_at') or e.get('actor')!=t.fixture or
        e.get('runtime')!=t.receipt['runtime'] or f!=e.get('frame') or
        not p.resolve().is_relative_to(lab.ROOT/'evidence') or not p.is_file() or
        lab.sha256(p)!=f.get('sha256') or not 0<=time.time()-p.stat().st_mtime<120 or
        not m.get('second_monitor_verified') or m.get('pid')!=t.receipt['runtime']['client']['pid'] or
        m.get('input_isolation',{}).get('actor')!=t.fixture['actor'] or
        m.get('input_isolation',{}).get('game_pid')!=current['input_isolation']['game_pid']):
        raise RuntimeError('fresh owned offline review differs')
    t.receipt['screen_review']={'path':str(path),'sha256':lab.sha256(path),'frame':f};t.persist()
    return d,e


def restart(out,reviews,version):
    out.mkdir(exist_ok=False,parents=True,mode=0o700)
    control.native_command();before=identity('modern_world');world=identity('worldserver')
    report={'schema':'client442_bridge_deployment_v1','started_at':time.time(),'before':before,
        'native':world,'parked_scout':True,'parked_primary':True,'reconnected':{},'completed':False,
        'observer_version':version,'offline_baselines':{},'client_lifetimes':{}}
    for name in ('primary','scout'):
        with actor(name):
            t=Trial(out/(name+'_before'),controller='code')
            try:
                d,e=review(t,reviews[name],t.fixture['character_name'])
                if (d.get('selected_character'),d.get('selected_level'))!=(t.fixture['character_name'],t.fixture['level']):
                    raise RuntimeError('predeployment selected offline identity differs')
                base=snapshot(t)
                if base!=e.get('parked_snapshot'):raise RuntimeError('reviewed offline native baseline changed')
                report['offline_baselines'][name]=base;report['client_lifetimes'][name]=identity('client')
                install_observer(t,version);capture(t)
            except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}';raise
            finally:t.receipt['finished_at']=time.time();t.persist()
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    lab.stop('modern_world');control.start();report['after']=identity('modern_world')
    if identity('worldserver')!=world:raise RuntimeError('native world lifetime changed')
    report['native_unchanged']=True;time.sleep(12)
    for name in ('primary','scout'):
        with actor(name):
            if identity('client')!=report['client_lifetimes'][name]:raise RuntimeError('owned client lifetime changed')
            report.setdefault('lobby_frames',{})[name]=shot(out/(name+'_disconnected.png'))
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'native_unchanged':True,'both_original_actors_remain_offline':True}),flush=True)


def current(t,directory):
    report=json.loads((directory/'deployment.json').read_text());name=t.fixture['actor']
    if (report.get('parked_primary') is not True or report.get('parked_scout') is not True or
        identity('worldserver')!=report['native'] or identity('modern_world')!=report['after'] or
        identity('client')!=report['client_lifetimes'][name] or snapshot(t)!=report['offline_baselines'][name]):
        raise RuntimeError('offline deployment native state or lifetimes differ')
    return report


def lobby(t,directory,review_path,stage):
    current(t,directory)
    name={'dismiss':'Okay','reconnect':'Reconnect','realm':'Client442 Lab','character':t.fixture['character_name']}[stage]
    d,_=review(t,review_path,name);point=d.get('point',[])
    if len(point)!=2 or any(type(v) is not int for v in point) or not (0<=point[0]<1280 and 0<=point[1]<720):
        raise RuntimeError('reviewed stock lobby control has no bounded point')
    if stage=='character' and not (1040<=point[0]<1280 and 70<=point[1]<560):
        raise RuntimeError('character selection point is outside the roster')
    if stage=='realm' and d.get('confirm_selected_realm') is not True:
        raise RuntimeError('stock realm confirmation requires a reviewed selection')
    if stage=='dismiss':t.io.key('Return',hold=1.2)
    else:
        t.io.click(*point,hold=1.2)
        if stage=='realm':time.sleep(1.2);t.io.key('Return',hold=1.2)
    time.sleep(12);current(t,directory)
    t.receipt.update(frame=shot(t.out/'next_screen.png'),stage=stage,completed=True,requires_next_screen_review=True,
        qualified_scope='One reviewed stock lobby input; both original actors remain offline. No world-entry input.')


def finish(t,directory,review_path):
    report=current(t,directory);name=t.fixture['actor'];d,_=review(t,review_path,t.fixture['character_name'])
    if (d.get('selected_character'),d.get('selected_level'))!=(t.fixture['character_name'],t.fixture['level']):
        raise RuntimeError('restored offline selected identity differs')
    authenticated=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('event')=='world_authenticated' and
        r.get('account_id')==t.fixture['account_id'] and r.get('time',0)>=report['started_at'])
    if not authenticated:raise RuntimeError('new owned realm authentication is absent')
    session=authenticated['session']
    enumerated=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
        r.get('name')=='SMSG_ENUM_CHARACTERS_RESULT' and r.get('direction')=='to_client')
    entered=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
        r.get('event') in ('native_player_created','world_connection_closed','native_stream_closed'))
    if not enumerated or entered:raise RuntimeError('owned client entered the world or lost its realm connection')
    checks=dict.fromkeys(('native_unchanged','same_client_lifetime','fresh_owned_selection_review',
        'new_realm_enumeration','no_world_entry'),True)
    t.receipt.update(parked_native=native(t),parked_frame=shot(t.out/'restored_selection.png'),
        restoration_checks=checks,completed=True,session=session,input_sent=False,
        qualified_scope='Original owned offline identity and complete persisted state preserved across bridge-only deployment.')
    if name=='primary':
        base=report['offline_baselines'][name];after=snapshot(t)
        native_checks={k:after[k]==base[k] for k in ('native','saved','pets','inventory')}
        native_checks.update(offline=after['native']['online']==0,registration=actors.load()==t.fixture,
            client_lifetime=True,selected_identity=True,native_world_lifetime=True)
        t.receipt['bridge_native_restoration']={'checks':native_checks,'offline':True,'frame':t.receipt['parked_frame']}
    # Bind only the final closed episode digest. The caller persists it first.
    return report,name,session


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['capture','restart','lobby','finish'])
    p.add_argument('--actor',choices=['primary','scout']);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--deployment',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--primary-review',type=Path);p.add_argument('--scout-review',type=Path)
    p.add_argument('--version',type=int,default=138);p.add_argument('--stage',choices=['dismiss','reconnect','realm','character'])
    a=p.parse_args()
    if a.action=='restart':
        if not a.primary_review or not a.scout_review:p.error('restart requires both fresh offline identity reviews')
        restart(a.output,{'primary':a.primary_review,'scout':a.scout_review},a.version)
    else:
        if not a.actor:p.error('requires an owned actor')
        if a.action in ('lobby','finish') and (not a.deployment or not a.review):p.error('requires deployment and review')
        if a.action=='lobby' and not a.stage:p.error('requires one reviewed lobby stage')
        with actor(a.actor):
            t=Trial(a.output,controller='code');result=None
            t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
            try:
                if a.action=='capture':capture(t)
                elif a.action=='lobby':lobby(t,a.deployment,a.review,a.stage)
                else:result=finish(t,a.deployment,a.review)
            except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
            finally:t.receipt['finished_at']=time.time();t.persist()
            if result and t.receipt['completed']:
                report,name,session=result;report['reconnected'][name]={'completed':True,'parked':True,'session':session}
                report.setdefault('parked_reconnect_attempt',{})[name]={'completed':True,'failure':None,
                    'episode':str(t.out/'episode.json'),'sha256':lab.sha256(t.out/'episode.json')}
                if set(report['reconnected'])=={'primary','scout'}:report.update(completed=True,finished_at=time.time())
                lab.private_write(a.deployment/'deployment.json',json.dumps(report,indent=2)+'\n')
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)
