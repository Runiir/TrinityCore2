"""Deploy opt-in native melee feedback with both owned original actors offline."""
import argparse,json,re,shutil,socket,subprocess,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity,shot
from .interaction_primary_combat_reentry import protected_snapshot
from .interaction_offline_bridge_deploy import snapshot,review,lobby,current,join_completion
from .observation.journal import latest

KEY='Client442.RefreshMeleeFeedbackOnStart'


def stage(out,build_receipt):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    build=json.loads(build_receipt.read_text())
    binary=lab.ROOT/'build/src/server/worldserver/worldserver'
    if (build.get('completed') is not True or build.get('jobs')!=1 or
        build.get('binary_sha256')!=lab.sha256(binary) or
        build.get('combat_source_sha256')!=lab.sha256(lab.REPO/'src/server/game/Handlers/CombatHandler.cpp') or
        f'CMAKE_HOME_DIRECTORY:INTERNAL={lab.REPO}\n' not in (lab.ROOT/'build/CMakeCache.txt').read_text()):
        raise RuntimeError('native build is not the verified current one-job compatibility build')
    d={'schema':'client442_offline_native_feedback_deployment_v1','started_at':time.time(),
        'native_before':identity('worldserver'),'before':identity('modern_world'),
        'binary_sha256':lab.sha256(binary),'previous_binary_sha256':lab.sha256(lab.ROOT/'bin/worldserver'),
        'build_receipt':{'path':str(build_receipt),'sha256':lab.sha256(build_receipt)},
        'config_before_sha256':lab.sha256(lab.ROOT/'config/worldserver.conf'),
        'offline_baselines':{},'client_lifetimes':{},'protected':protected_snapshot(),
        'parked_primary':True,'parked_scout':True,'reconnected':{},'completed':False}
    if any(v['native']['online'] for v in d['protected'].values()):
        raise RuntimeError('all retained alternate actors must remain offline')
    for name in ('primary','scout'):
        with actor(name):
            t=Trial(out/(name+'_before'),controller='code')
            try:
                d['offline_baselines'][name]=snapshot(t);d['client_lifetimes'][name]=identity('client')
                t.receipt.update(parked_snapshot=d['offline_baselines'][name],frame=shot(t.out/'screen.png'),
                    completed=True,input_sent=False,qualified_scope='Read-only complete native deployment baseline.')
            except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}';raise
            finally:t.receipt['finished_at']=time.time();t.persist()
    d.update(staged=True,finished_at=time.time())
    lab.private_write(out/'deployment.json',json.dumps(d,indent=2)+'\n')
    print(json.dumps({'staged':True,'native_before':d['native_before'],'binary_sha256':d['binary_sha256']}),flush=True)


def install(source,batch):
    d=json.loads((source/'deployment.json').read_text());batch=batch.resolve()
    receipt=json.loads((source.parent/'checkpoint_receipt.json').read_text())
    binary=lab.ROOT/'build/src/server/worldserver/worldserver';target=lab.ROOT/'bin/worldserver'
    config=lab.ROOT/'config/worldserver.conf';backup=lab.ROOT/'bin/worldserver.before_repeat_melee_feedback'
    if (batch.exists() or batch.parent!=lab.ROOT/'evidence' or not re.fullmatch(r'[A-Za-z0-9_]+',batch.name) or
        not d.get('staged') or not receipt.get('cloud_verified') or backup.exists() or
        not any(f['path']==str((source/'deployment.json').relative_to(lab.ROOT)) and
            f['sha256']==lab.sha256(source/'deployment.json') for f in receipt['file_manifest']) or
        identity('worldserver')!=d['native_before'] or identity('modern_world')!=d['before'] or
        lab.sha256(binary)!=d['binary_sha256'] or lab.sha256(target)!=d['previous_binary_sha256'] or
        lab.sha256(config)!=d['config_before_sha256'] or protected_snapshot()!=d['protected']):
        raise RuntimeError('staged closed build, checkpoint, process or saved-state authority differs')
    for name in ('primary','scout'):
        with actor(name):
            t=Trial(source.parent.parent/(batch.name+'_install_'+name),controller='code')
            try:
                if snapshot(t)!=d['offline_baselines'][name] or identity('client')!=d['client_lifetimes'][name]:
                    raise RuntimeError('offline native actor or client lifetime changed before install')
                t.receipt.update(frame=shot(t.out/'screen.png'),completed=True,input_sent=False)
            finally:t.receipt['finished_at']=time.time();t.persist()
    text=config.read_text()
    if re.search(r'(?m)^'+re.escape(KEY)+r'\s*=.*$',text):
        text=re.sub(r'(?m)^'+re.escape(KEY)+r'\s*=.*$',KEY+' = 1',text)
    else:text+='\n'+KEY+' = 1\n'
    lab.server_command('saveall');lab.server_command('server shutdown 1')
    deadline=time.monotonic()+45
    while lab.owned_process('worldserver'):
        if time.monotonic()>deadline:raise RuntimeError('owned native graceful shutdown did not complete')
        time.sleep(.2)
    target.rename(backup);shutil.copy2(binary,target);lab.private_write(config,text)
    lab.start_server('worldserver');deadline=time.monotonic()+45
    while True:
        try:
            with socket.create_connection(('127.0.0.1',18085),timeout=1):break
        except OSError:
            if time.monotonic()>deadline:raise RuntimeError('new native listener did not become ready')
            time.sleep(.2)
    subprocess.run(['pixi','run','python','-m','tools.client_compatibility.checkpoint_interactions',
        '--initialize','--directory',str(batch)],cwd=lab.REPO,check=True)
    out=batch/'native_feedback_deploy01';out.mkdir(mode=0o700)
    d.update(started_at=time.time(),native=identity('worldserver'),after=identity('modern_world'),
        source_stage={'path':str(source),'sha256':lab.sha256(source/'deployment.json')},
        native_unchanged=False,native_restarted=True,bridge_unchanged=True,
        config_enabled=KEY,config_sha256=lab.sha256(config),rollback_binary_sha256=lab.sha256(backup),completed=False)
    d.pop('finished_at',None)
    if d['after']!=d['before']:raise RuntimeError('bridge unexpectedly restarted')
    time.sleep(8)
    for name in ('primary','scout'):
        with actor(name):
            if identity('client')!=d['client_lifetimes'][name]:raise RuntimeError('existing client lifetime changed')
            d.setdefault('lobby_frames',{})[name]=shot(out/(name+'_disconnected.png'))
    for name in ('primary','scout'):
        shutil.copytree(source.parent.parent/(batch.name+'_install_'+name),out/(name+'_install_preflight'))
        shutil.rmtree(source.parent.parent/(batch.name+'_install_'+name))
    lab.private_write(out/'deployment.json',json.dumps(d,indent=2)+'\n')
    print(json.dumps({'native':d['native'],'bridge_unchanged':True,'clients_unchanged':True,'batch':str(batch)}),flush=True)


def finish(t,directory,review_path):
    d=current(t,directory);name=t.fixture['actor'];r,_=review(t,review_path,t.fixture['character_name'])
    if (r.get('selected_character'),r.get('selected_level'))!=(t.fixture['character_name'],t.fixture['level']):
        raise RuntimeError('original offline selection differs')
    auth=latest(lab.ROOT/'logs/modern_world.jsonl',lambda p:p.get('event')=='world_authenticated' and
        p.get('account_id')==t.fixture['account_id'] and p.get('time',0)>=d['started_at'])
    if not auth:raise RuntimeError('new owned realm authentication absent')
    session=auth['session'];enum=latest(lab.ROOT/'logs/modern_world.jsonl',lambda p:p.get('session')==session and
        p.get('name')=='SMSG_ENUM_CHARACTERS_RESULT' and p.get('direction')=='to_client')
    entered=latest(lab.ROOT/'logs/modern_world.jsonl',lambda p:p.get('session')==session and
        p.get('event') in ('native_player_created','native_stream_closed','world_connection_closed'))
    checks={'current_native':identity('worldserver')==d['native'],'unchanged_bridge':d['after']==d['before'],
        'same_client':identity('client')==d['client_lifetimes'][name],'new_realm_enumeration':bool(enum and not entered),
        'all_protected':protected_snapshot()==d['protected'],'original_offline_snapshot':snapshot(t)==d['offline_baselines'][name],
        'installed_binary':lab.sha256(lab.ROOT/'bin/worldserver')==d['binary_sha256']}
    t.receipt.update(checks=checks,parked_native=snapshot(t)['native'],session=session,
        parked_frame=shot(t.out/'restored_selection.png'),input_sent=False)
    if not all(checks.values()):raise RuntimeError('native deployment restoration differs')
    t.receipt['completed']=True
    return d,name,session


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','install','lobby','finish'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path)
    p.add_argument('--build-receipt',type=Path);p.add_argument('--actor',choices=['primary','scout'])
    p.add_argument('--deployment',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--stage',choices=['dismiss','reconnect','realm','character']);a=p.parse_args()
    if a.action=='stage':stage(a.output,a.build_receipt)
    elif a.action=='install':install(a.source,a.output)
    else:
        if not (a.actor and a.deployment and a.review):p.error('requires actor, deployment and fresh review')
        with actor(a.actor):
            t=Trial(a.output,controller='code');result=None
            try:
                if a.action=='lobby':lobby(t,a.deployment,a.review,a.stage)
                else:result=finish(t,a.deployment,a.review)
            except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}';raise
            finally:t.receipt['finished_at']=time.time();t.persist()
            if result:join_completion(t,a.deployment,result)
