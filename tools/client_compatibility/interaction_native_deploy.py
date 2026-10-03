"""Stage a private native build, then deploy and reconnect reviewed owned clients."""
import argparse,json,re,shutil,subprocess,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_mail import mailbox_state
from .interaction_auction import auction_state
from .interaction_bridge_deploy import identity,shot,reconnect


def stage(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    binary=lab.ROOT/'build/src/server/worldserver/worldserver'
    cache=(lab.ROOT/'build/CMakeCache.txt').read_text()
    if f'CMAKE_HOME_DIRECTORY:INTERNAL={lab.REPO}\n' not in cache:
        raise RuntimeError('native build does not belong to this compatibility worktree')
    config=lab.ROOT/'config/worldserver.conf'
    report={'schema':'client442_native_deployment_v1','started_at':time.time(),
        'native_before':identity('worldserver'),'bridge_before':identity('modern_world'),
        'binary_sha256':lab.sha256(binary),'previous_binary_sha256':lab.sha256(lab.ROOT/'bin/worldserver'),
        'config_sha256':lab.sha256(config),'observer_version':29,'baselines':{},'reconnected':{}}
    if auction_state()['auctions']:raise RuntimeError('recover outstanding native auctions before deployment')
    report['native_resources']=mailbox_state()
    for name in ['primary','scout']:
        with actor(name):
            t=Trial(out/name,controller='code')
            try:
                t.clean_panels();state,frame=t.observe('native_deployment_baseline')
                report['baselines'][name]={key:state.get(key) for key in ['guid','money','equipment','group','raid_profile']}
                t.receipt['baseline']={'state':state,'frame':frame};t.receipt['completed']=True
            finally:t.receipt['finished_at']=time.time();t.persist()
    report['finished_at']=time.time()
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'staged':True,'native_before':report['native_before'],'binary_sha256':report['binary_sha256']}),flush=True)


def install(source,batch):
    report=json.loads((source/'deployment.json').read_text())
    checkpoint=source.parent/'checkpoint_receipt.json'
    if not checkpoint.is_file() or not json.loads(checkpoint.read_text()).get('cloud_verified'):
        raise RuntimeError('offload the closed pre-deployment batch before restarting native')
    if identity('worldserver')!=report['native_before'] or identity('modern_world')!=report['bridge_before']:
        raise RuntimeError('staged deployment process identities changed')
    binary=lab.ROOT/'build/src/server/worldserver/worldserver';target=lab.ROOT/'bin/worldserver'
    config=lab.ROOT/'config/worldserver.conf'
    if (lab.sha256(binary)!=report['binary_sha256'] or lab.sha256(target)!=report['previous_binary_sha256'] or
            lab.sha256(config)!=report['config_sha256'] or auction_state()['auctions'] or
            json.loads(json.dumps(mailbox_state()))!=report['native_resources']):
        raise RuntimeError('staged build, configuration or native resources changed')
    text=config.read_text();key='Client442.AuctionDepositRules'
    if re.search(r'(?m)^'+re.escape(key)+r'\s*=.*$',text):
        text=re.sub(r'(?m)^'+re.escape(key)+r'\s*=.*$',key+' = 1',text)
    else:text+='\n'+key+' = 1\n'
    lab.server_command('saveall');lab.server_command('server shutdown 1')
    deadline=time.monotonic()+30
    while lab.owned_process('worldserver'):
        if time.monotonic()>deadline:raise RuntimeError('owned native graceful shutdown did not finish')
        time.sleep(.2)
    # Keep one rollback binary until the first successful new native trial.
    backup=lab.ROOT/'bin/worldserver.before_auction_deposit'
    if backup.exists():raise RuntimeError('an earlier native rollback binary requires review')
    target.rename(backup);shutil.copy2(binary,target);lab.private_write(config,text)
    lab.start('worldserver')
    deadline=time.monotonic()+45
    import socket
    while True:
        try:
            with socket.create_connection(('127.0.0.1',18085),timeout=1):break
        except OSError:
            if time.monotonic()>deadline:raise RuntimeError('new owned native listener did not become ready')
            time.sleep(.2)
    subprocess.run(['pixi','run','python','-m','tools.client_compatibility.checkpoint_interactions',
        '--initialize','--directory',str(batch)],cwd=lab.REPO,check=True)
    out=batch/'native_deposit_deployment';out.mkdir(mode=0o700)
    report.update(started_at=time.time(),source_stage=str(source),native=identity('worldserver'),
        after=identity('modern_world'),reconnected={},native_restarted=True,
        config_flag=key,config_enabled=True,rollback_binary_sha256=lab.sha256(backup))
    if report['after']!=report['bridge_before']:raise RuntimeError('owned bridge changed during native deployment')
    report.pop('finished_at',None)
    for name in ['primary','scout']:
        with actor(name):report.setdefault('lobby_frames',{})[name]=shot(out/(name+'_disconnected.png'))
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'native_restarted':True,'bridge_unchanged':True,'lobby_frames':report['lobby_frames']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','install','reconnect'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path)
    p.add_argument('--actor',choices=['primary','scout']);a=p.parse_args()
    if a.action=='stage':stage(a.output)
    elif a.action=='install':
        if not a.source:p.error('install requires the closed staged source')
        install(a.source,a.output)
    else:
        if not a.actor:p.error('reconnect requires the visually reviewed actor')
        reconnect(a.output,a.actor)
